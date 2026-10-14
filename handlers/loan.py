from decimal import Decimal

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

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
    text = t("choose_amount", user.language, limit=user.credit_limit)
    await callback.message.edit_text(
        text,
        reply_markup=amount_keyboard(float(user.credit_limit), user.language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("loan:amount:"), LoanFSM.amount)
async def choose_amount(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    amount = float(callback.data.split(":")[2])
    await state.update_data(amount=amount)
    await state.set_state(LoanFSM.installments)

    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        t("choose_installments", user.language),
        reply_markup=installments_keyboard(user.language),
    )
    await callback.answer()


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
        loan = await create_loan(session, user, amount, count)
        await session.commit()
        await state.clear()

        text = t("loan_issued", user.language, amount=amount)
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.message.answer(
            t("main_menu", user.language, limit=user.credit_limit, success=user.successful_loans),
            reply_markup=main_menu_keyboard(user.language),
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
    except XRocketError as e:
        logger.error("xRocket payout failed: {}", e)
        await callback.answer("Payment system error. Try again later.", show_alert=True)
    except Exception:
        logger.exception("Unexpected error issuing loan")
        await callback.answer("Internal error", show_alert=True)

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
    lines = ["📋 <b>Active loans</b>\n"]
    for loan in loans:
        paid = sum(1 for i in loan.installments if i.status.value == "paid")
        lines.append(
            f"#{loan.id} — {loan.amount} {loan.currency} ({paid}/{loan.installments_count})"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"Loan #{loan.id} — Pay",
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
