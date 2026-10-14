"""Investment fund — users deposit USDT; earn share of 1% loan interest."""

from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

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
from keyboards.inline import EMOJI, _btn, back_keyboard
from services.loan_service import fund_stats, get_or_create_user
from services.xrocket import get_xrocket

router = Router(name="invest")
settings = get_settings()

GUIDE = (
    "💎 <b>Investment Fund</b>\n\n"
    "• Deposit USDT into the community fund.\n"
    "• Borrowers pay <b>1% interest</b> on each loan.\n"
    "• That interest is shared among investors by stake size.\n"
    "• Example: you hold 10% of the pool → you get 10% of each loan's interest.\n\n"
    "Min deposit: <b>{min_inv} USDT</b>\n"
    "Pool size: <b>{pool} USDT</b> · Investors: <b>{n}</b>\n"
    "Your stake: <b>{mine} USDT</b> · Earned: <b>{earned} USDT</b>"
)


class InvestFSM(StatesGroup):
    amount = State()


@router.callback_query(F.data == "invest")
async def invest_home(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(session, callback.from_user.id)
    stats = await fund_stats(session)
    text = GUIDE.format(
        min_inv=settings.min_invest_amount,
        pool=stats["pool"],
        n=stats["investors"],
        mine=user.invested_amount,
        earned=user.earned_interest,
    )
    builder = InlineKeyboardBuilder()
    builder.row(
        _btn("💵 Deposit to fund", "invest:deposit", style="success",
             icon_custom_emoji_id=EMOJI.get("green"))
    )
    builder.row(
        _btn("✅ I paid — activate", "invest:activate", style="primary",
             icon_custom_emoji_id=EMOJI.get("check"))
    )
    builder.row(_btn("🔙 Back", "menu:main", style="danger", icon_custom_emoji_id=EMOJI.get("down")))
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "invest:deposit")
async def invest_deposit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(InvestFSM.amount)
    await callback.message.edit_text(
        f"💵 Enter deposit amount in USDT (min {settings.min_invest_amount}):"
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
            link = (
                invoice.get("link")
                or invoice.get("paymentLink")
                or invoice.get("url")
                or (invoice.get("data") or {}).get("link")
            )
            inv.invoice_id = str(
                invoice.get("invoiceId") or invoice.get("id") or ""
            )
            inv.invoice_link = link
        await session.commit()
        await state.clear()

        kb = InlineKeyboardBuilder()
        if link:
            kb.row(InlineKeyboardButton(text="💳 Pay invoice", url=link))
        kb.row(InlineKeyboardButton(text="✅ I paid — activate", callback_data="invest:activate"))
        kb.row(InlineKeyboardButton(text="🔙 Back", callback_data="invest"))

        await message.answer(
            f"💎 Deposit <b>{amount} USDT</b> created (#{inv.id}).\n"
            f"Pay the invoice, then tap <b>I paid — activate</b>.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("invest invoice")
        inv.status = InvestmentStatus.PENDING
        await session.commit()
        await state.clear()
        await message.answer(
            f"Deposit #{inv.id} recorded as pending.\n"
            f"Invoice error: {e}\n"
            f"Pay manually to the fund wallet / admin, then activate."
        )


@router.callback_query(F.data == "invest:activate")
async def invest_activate(callback: CallbackQuery, session: AsyncSession):
    """Mark newest pending investment as active (admin can later verify invoice)."""
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
    await callback.answer("Activated!", show_alert=True)
    await invest_home(callback, session, await callback.bot.get_current())  # type: ignore
