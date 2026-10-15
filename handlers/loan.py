from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from keyboards.inline import (
    amount_keyboard,
    confirm_loan_keyboard,
    installments_keyboard,
    main_menu_keyboard,
)
from locales import menu_kwargs, t
from services.loan_service import (
    base_interest,
    create_loan_request,
    get_active_loans,
    get_admin_telegram_ids,
    get_or_create_user,
    is_admin_user,
)
from utils.media import send_section

router = Router(name="loan")
settings = get_settings()


class LoanFSM(StatesGroup):
    amount = State()
    installments = State()
    confirm = State()


async def _safe_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    """edit_text fails on photo messages — always fall back to answer."""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data == "loan:request")
async def request_loan(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    if user.is_blocked:
        await callback.answer(
            t("blocked", user.language, reason=user.block_reason or "-"),
            show_alert=True,
        )
        return

    await state.set_state(LoanFSM.amount)
    text = (
        f"🚀 <b>Request a loan</b>\n\n"
        f"• Interest: <b>{settings.loan_interest_percent:g}%</b> for first "
        f"<b>{settings.interest_period_days}</b> days\n"
        f"• After due: <b>+{settings.late_increase_percent:g}%</b> each extra "
        f"{settings.interest_period_days} days\n"
        f"• Installments every {settings.installment_period_days} days\n"
        f"• Admin approval required before payout\n\n"
        f"Your limit: <b>{user.credit_limit} USDT</b> · Min: <b>{settings.min_loan_amount} USDT</b>\n"
        f"Type an amount or use buttons:"
    )
    await send_section(
        callback,
        text,
        section="loan",
        reply_markup=amount_keyboard(float(user.credit_limit), user.language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("loan:amount:"))
async def choose_amount_btn(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    amount = float(callback.data.split(":")[2])
    await state.update_data(amount=amount)
    await state.set_state(LoanFSM.installments)
    user = await get_or_create_user(session, callback.from_user.id)
    await _safe_text(
        callback,
        t("choose_installments", user.language),
        installments_keyboard(user.language),
    )
    await callback.answer()


@router.message(LoanFSM.amount)
async def choose_amount_text(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(session, message.from_user.id)
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("❌ Invalid amount. Example: 0.50 or 1.25")
        return

    min_a = Decimal(str(settings.min_loan_amount))
    if amount < min_a:
        await message.answer(f"❌ Minimum amount is {min_a} USDT.")
        return
    if amount > user.credit_limit:
        await message.answer(f"❌ Your credit limit is {user.credit_limit} USDT.")
        return

    await state.update_data(amount=float(amount))
    await state.set_state(LoanFSM.installments)
    await message.answer(
        t("choose_installments", user.language),
        reply_markup=installments_keyboard(user.language),
    )


@router.callback_query(F.data.startswith("loan:installments:"))
async def choose_installments(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    count = int(callback.data.split(":")[2])
    data = await state.get_data()
    if "amount" not in data:
        await callback.answer("Start again from Request Loan", show_alert=True)
        return
    amount = Decimal(str(data["amount"]))
    _pct, interest, total = base_interest(amount)
    each = (total / count).quantize(Decimal("0.01"))
    await state.update_data(installments=count)
    await state.set_state(LoanFSM.confirm)

    user = await get_or_create_user(session, callback.from_user.id)
    text = (
        f"Confirm loan of <b>{amount} USDT</b>\n"
        f"Interest {settings.loan_interest_percent:g}% / {settings.interest_period_days}d: "
        f"<b>{interest} USDT</b>\n"
        f"Total repay (on time): <b>{total} USDT</b>\n"
        f"in <b>{count}</b> installments of <b>{each} USDT</b>\n"
        f"(every {settings.installment_period_days} days)\n\n"
        f"⚠️ After due date: +{settings.late_increase_percent:g}% per extra "
        f"{settings.interest_period_days} days.\n\n"
        f"⏳ After confirm → waiting for <b>admin approval</b>."
    )
    await _safe_text(callback, text, confirm_loan_keyboard(user.language))
    await callback.answer()


@router.callback_query(F.data == "loan:confirm")
async def confirm_loan(callback: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot):
    data = await state.get_data()
    if "amount" not in data or "installments" not in data:
        await callback.answer("Session expired. Start again.", show_alert=True)
        return
    amount = Decimal(str(data["amount"]))
    count = int(data["installments"])

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    try:
        loan = await create_loan_request(session, user, amount, count)
        await session.commit()
        await state.clear()

        await _safe_text(
            callback,
            f"⏳ <b>Loan request #{loan.id} submitted</b>\n\n"
            f"Principal: <b>{amount} USDT</b>\n"
            f"Interest {loan.interest_percent}%: <b>{loan.interest_amount} USDT</b>\n"
            f"Total repay: <b>{loan.total_repay} USDT</b>\n"
            f"Installments: <b>{count}</b> × {loan.installment_amount}\n\n"
            f"Waiting for admin approval.",
        )

        admin_ids = await get_admin_telegram_ids(session)
        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="✅ Approve", callback_data=f"admin:loan_approve:{loan.id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"admin:loan_reject:{loan.id}"),
        )
        note = (
            f"🔔 <b>New loan request #{loan.id}</b>\n\n"
            f"User: @{user.username or '-'} (<code>{user.telegram_id}</code>)\n"
            f"Level: {user.level} ({user.level_name})\n"
            f"Principal: <b>{amount} USDT</b> + {loan.interest_percent}%\n"
            f"Total repay: {loan.total_repay} · {count} inst\n"
            f"Limit: {user.credit_limit} · Success: {user.successful_loans}"
        )
        for aid in admin_ids:
            try:
                await bot.send_message(aid, note, reply_markup=kb.as_markup(), parse_mode="HTML")
            except Exception as e:
                logger.warning("notify admin {}: {}", aid, e)

        is_admin = is_admin_user(callback.from_user.username, callback.from_user.id)
        await callback.message.answer(
            t("main_menu", user.language or "en", **menu_kwargs(user)),
            reply_markup=main_menu_keyboard(user.language or "en", is_admin=is_admin),
            parse_mode="HTML",
        )
        await callback.answer("Submitted")
    except ValueError as e:
        await callback.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        logger.exception("loan confirm error")
        await callback.answer(f"Error: {str(e)[:120]}", show_alert=True)


@router.callback_query(F.data == "loan:list")
async def list_loans(callback: CallbackQuery, session: AsyncSession):
    try:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            full_name=callback.from_user.full_name,
        )
        loans = await get_active_loans(session, user.id)

        builder = InlineKeyboardBuilder()
        if not loans:
            text = (
                "⚡ <b>My Loans</b>\n\n"
                + t("no_active_loans", user.language or "en")
                + "\n\nUse <b>Request Loan</b> to start."
            )
            builder.row(InlineKeyboardButton(text="🚀 Request Loan", callback_data="loan:request"))
            builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
            await _safe_text(callback, text, builder.as_markup())
            await callback.answer()
            return

        lines = [
            "⚡ <b>My Loans</b>\n",
            f"Interest: {settings.loan_interest_percent:g}% / {settings.interest_period_days}d · "
            f"late +{settings.late_increase_percent:g}% / week\n",
        ]
        for loan in loans:
            paid = sum(1 for i in (loan.installments or []) if i.status.value == "paid")
            st = loan.status.value
            lines.append(
                f"\n#{loan.id} — <b>{loan.amount}</b> USDT (+{loan.interest_amount or 0}) "
                f"[{st}] ({paid}/{loan.installments_count})"
            )
            if st == "active":
                builder.row(
                    InlineKeyboardButton(
                        text=f"💳 Loan #{loan.id} — Pay installments",
                        callback_data=f"repay:loan:{loan.id}",
                    )
                )
            elif st == "pending":
                lines.append("  ⏳ Waiting admin approval")

        builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))
        await _safe_text(callback, "\n".join(lines), builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.exception("loan:list failed")
        await callback.answer(f"Error: {str(e)[:100]}", show_alert=True)
