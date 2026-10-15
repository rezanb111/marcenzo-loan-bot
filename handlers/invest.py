"""Investment fund — deposit USDT; earn share of borrower interest (10%/7d model)."""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import Investment, InvestmentStatus
from services.loan_service import fund_stats, get_or_create_user
from services.xrocket import get_xrocket

router = Router(name="invest")
settings = get_settings()


class InvestFSM(StatesGroup):
    amount = State()


async def _safe_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


async def _show_invest_home(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    stats = await fund_stats(session)
    text = (
        "💎 <b>Investment Fund</b>\n\n"
        f"• Borrowers pay <b>{settings.loan_interest_percent:g}%</b> for each "
        f"{settings.interest_period_days}-day period.\n"
        f"• Late loans add +{settings.late_increase_percent:g}% per extra week "
        f"(system/admin side).\n"
        f"• Base interest is shared among investors by stake size.\n"
        f"• Example: 10% of pool → 10% of each loan’s base interest.\n\n"
        f"Min deposit: <b>{settings.min_invest_amount} USDT</b>\n"
        f"Pool size: <b>{stats['pool']} USDT</b> · Investors: <b>{stats['investors']}</b>\n"
        f"Your stake: <b>{user.invested_amount} USDT</b> · Earned: <b>{user.earned_interest} USDT</b>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💵 Deposit to fund", callback_data="invest:deposit"))
    builder.row(InlineKeyboardButton(text="✅ I paid — activate", callback_data="invest:activate"))
    builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
    await _safe_text(callback, text, builder.as_markup())


@router.callback_query(F.data == "invest")
async def invest_home(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    try:
        await state.clear()
        await _show_invest_home(callback, session)
        await callback.answer()
    except Exception as e:
        logger.exception("invest home")
        await callback.answer(str(e)[:100], show_alert=True)


@router.callback_query(F.data == "invest:deposit")
async def invest_deposit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(InvestFSM.amount)
    await _safe_text(
        callback,
        f"💵 Enter deposit amount in USDT (min {settings.min_invest_amount}):\n\n"
        f"After paying the invoice, return and tap <b>I paid — activate</b>.",
    )
    await callback.answer()


@router.message(InvestFSM.amount)
async def invest_deposit_amount(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("Invalid amount")
        return
    if amount < Decimal(str(settings.min_invest_amount)):
        await message.answer(f"Minimum is {settings.min_invest_amount} USDT")
        return

    inv = Investment(
        user_id=user.id,
        amount=amount,
        status=InvestmentStatus.PENDING,
    )
    session.add(inv)
    await session.flush()

    try:
        client = get_xrocket()
        invoice = await client.create_invoice(
            amount=str(amount),
            currency=settings.default_currency,
            description=f"Fund deposit #{inv.id}",
            client_invoice_id=f"inv{inv.id}u{user.telegram_id}"[:50],
            telegram_id=user.telegram_id,
        )
        link = None
        if isinstance(invoice, dict):
            links = invoice.get("links") or {}
            link = (
                links.get("webLink")
                or links.get("botLink")
                or invoice.get("link")
                or invoice.get("paymentLink")
                or invoice.get("url")
                or (invoice.get("data") or {}).get("link")
            )
            inv.invoice_id = str(invoice.get("invoiceId") or invoice.get("id") or "")
            inv.invoice_link = link
        await session.commit()
        await state.clear()

        kb = InlineKeyboardBuilder()
        if link:
            kb.row(InlineKeyboardButton(text="💳 Pay invoice", url=link))
        kb.row(InlineKeyboardButton(text="✅ I paid — activate", callback_data="invest:activate"))
        kb.row(InlineKeyboardButton(text="🔙 Fund", callback_data="invest"))

        await message.answer(
            f"💎 Deposit <b>{amount} USDT</b> created (#{inv.id}).\n"
            f"Pay the invoice, then tap <b>I paid — activate</b>.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("invest invoice")
        await session.commit()
        await state.clear()
        await message.answer(
            f"Deposit #{inv.id} saved as pending.\nInvoice error: <code>{e}</code>\n"
            f"Contact admin or try Activate after manual payment.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "invest:activate")
async def invest_activate(callback: CallbackQuery, session: AsyncSession):
    try:
        user = await get_or_create_user(session, callback.from_user.id)
        result = await session.execute(
            select(Investment)
            .where(
                Investment.user_id == user.id,
                Investment.status == InvestmentStatus.PENDING,
            )
            .order_by(Investment.created_at.desc())
            .limit(1)
        )
        inv = result.scalar_one_or_none()
        if not inv:
            await callback.answer("No pending deposit", show_alert=True)
            return

        inv.status = InvestmentStatus.ACTIVE
        inv.activated_at = datetime.now(timezone.utc)
        user.invested_amount += inv.amount
        await session.commit()
        await callback.answer("Deposit activated! ✅", show_alert=True)
        await _show_invest_home(callback, session)
    except Exception as e:
        logger.exception("invest activate")
        await callback.answer(str(e)[:100], show_alert=True)
