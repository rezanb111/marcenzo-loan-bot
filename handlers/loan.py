from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from keyboards.inline import (
    amount_keyboard,
    back_keyboard,
    confirm_loan_keyboard,
    installments_keyboard,
    main_menu_keyboard,
)
from locales import t
from services.loan_service import create_loan, get_active_loans, get_or_create_user
from services.xrocket import XRocketError

router = Router(name="loan")
settings = get_settings()


class LoanFSM(StatesGroup):
    amount = State()
    installments = State()
    confirm = State()


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
    min_a = settings.min_loan_amount
    text = (
        f"💰 <b>درخواست وام</b>\n\n"
        f"سقف اعتبار شما: <b>{user.credit_limit} USDT</b>\n"
        f"حداقل مبلغ: <b>{min_a} USDT</b>\n\n"
        f"مبلغ دلخواه را بنویس (مثلاً 0.5 یا 2.25)\n"
        f"یا از دکمه‌های سریع استفاده کن:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=amount_keyboard(float(user.credit_limit), user.language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("loan:amount:"), LoanFSM.amount)
async def choose_amount_btn(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    amount = float(callback.data.split(":")[2])
    await state.update_data(amount=amount)
    await state.set_state(LoanFSM.installments)
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t("choose_installments", user.language),
        reply_markup=installments_keyboard(user.language),
    )
    await callback.answer()


@router.message(LoanFSM.amount)
async def choose_amount_text(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(session, message.from_user.id)
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("❌ مبلغ نامعتبر. مثال: 0.50 یا 1.25")
        return

    min_a = Decimal(str(settings.min_loan_amount))
    if amount < min_a:
        await message.answer(f"❌ حداقل مبلغ {min_a} USDT است.")
        return
    if amount > user.credit_limit:
        await message.answer(f"❌ سقف اعتبار شما {user.credit_limit} USDT است.")
        return

    await state.update_data(amount=float(amount))
    await state.set_state(LoanFSM.installments)
    await message.answer(
        t("choose_installments", user.language),
        reply_markup=installments_keyboard(user.language),
    )


@router.callback_query(F.data.startswith("loan:installments:"), LoanFSM.installments)
async def choose_installments(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    count = int(callback.data.split(":")[2])
    data = await state.get_data()
    amount = Decimal(str(data["amount"]))
    each = (amount / count).quantize(Decimal("0.01"))

    await state.update_data(installments=count)
    await state.set_state(LoanFSM.confirm)

    user = await get_or_create_user(session, callback.from_user.id)
    text = t(
        "confirm_loan",
        user.language,
        amount=amount,
        count=count,
        each=each,
    )
    await callback.message.edit_text(
        text,
        reply_markup=confirm_loan_keyboard(user.language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "loan:confirm", LoanFSM.confirm)
async def confirm_and_issue(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    amount = Decimal(str(data["amount"]))
    count = int(data["installments"])

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    try:
        await create_loan(session, user, amount, count)
        await session.commit()
        await state.clear()

        text = t("loan_issued", user.language, amount=amount)
        await callback.message.edit_text(text, parse_mode="HTML")
        is_admin = (callback.from_user.username or "").lower() in settings.admin_list
        await callback.message.answer(
            t("main_menu", user.language, limit=user.credit_limit, success=user.successful_loans),
            reply_markup=main_menu_keyboard(user.language, is_admin=is_admin),
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
    except XRocketError as e:
        logger.error("xRocket payout failed: {}", e)
        await callback.answer("خطای سیستم پرداخت. بعداً دوباره امتحان کن.", show_alert=True)
    except Exception:
        logger.exception("Unexpected error issuing loan")
        await callback.answer("خطای داخلی", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "loan:list")
async def list_loans(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    loans = await get_active_loans(session, user.id)

    if not loans:
        await callback.message.edit_text(
            t("no_active_loans", user.language),
            reply_markup=back_keyboard(user.language),
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    lines = ["📋 <b>وام‌های فعال</b>\n"]
    for loan in loans:
        paid = sum(1 for i in loan.installments if i.status.value == "paid")
        lines.append(
            f"#{loan.id} — {loan.amount} {loan.currency} ({paid}/{loan.installments_count})"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"وام #{loan.id} — پرداخت",
                callback_data=f"repay:loan:{loan.id}",
                style="success",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text=t("back", user.language),
            callback_data="menu:main",
            style="danger",
        )
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()
