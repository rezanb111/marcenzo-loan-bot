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
    back_keyboard,
    confirm_loan_keyboard,
    installments_keyboard,
    main_menu_keyboard,
)
from locales import menu_kwargs, t
from services.loan_service import (
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
    text = t(
        "loan_guide",
        user.language,
        limit=user.credit_limit,
        min_a=settings.min_loan_amount,
    )
    await send_section(
        callback,
        text,
        section="loan",
        reply_markup=amount_keyboard(float(user.credit_limit), user.language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("loan:amount:"), LoanFSM.amount)
async def choose_amount_btn(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    amount = float(callback.data.split(":")[2])
    await state.update_data(amount=amount)
    await state.set_state(LoanFSM.installments)
    user = await get_or_create_user(session, callback.from_user.id)
    try:
        await callback.message.edit_text(
            t("choose_installments", user.language),
            reply_markup=installments_keyboard(user.language),
        )
    except Exception:
        await callback.message.answer(
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


@router.callback_query(F.data.startswith("loan:installments:"), LoanFSM.installments)
async def choose_installments(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    count = int(callback.data.split(":")[2])
    data = await state.get_data()
    amount = Decimal(str(data["amount"]))
    interest = (amount * Decimal(str(settings.loan_interest_percent)) / Decimal("100")).quantize(
        Decimal("0.01")
    )
    total = amount + interest
    each = (total / count).quantize(Decimal("0.01"))
    await state.update_data(installments=count)
    await state.set_state(LoanFSM.confirm)

    user = await get_or_create_user(session, callback.from_user.id)
    text = t(
        "confirm_loan",
        user.language,
        amount=amount,
        interest=interest,
        total=total,
        count=count,
        each=each,
    )
    await callback.message.edit_text(
        text + "\n\n⏳ After confirm → waiting for <b>admin approval</b>.",
        reply_markup=confirm_loan_keyboard(user.language),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "loan:confirm", LoanFSM.confirm)
async def confirm_loan(callback: CallbackQuery, session: AsyncSession, state: FSMContext, bot: Bot):
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
        loan = await create_loan_request(session, user, amount, count)
        await session.commit()
        await state.clear()

        await callback.message.edit_text(
            f"⏳ <b>Loan request #{loan.id} submitted</b>\n\n"
            f"Principal: <b>{amount} USDT</b>\n"
            f"Interest 1%: <b>{loan.interest_amount} USDT</b>\n"
            f"Total repay: <b>{loan.total_repay} USDT</b>\n"
            f"Installments: <b>{count}</b> × {loan.installment_amount}\n\n"
            f"Waiting for admin approval.",
            parse_mode="HTML",
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
            f"Principal: <b>{amount} USDT</b> + 1% interest\n"
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
            t("main_menu", user.language, **menu_kwargs(user)),
            reply_markup=main_menu_keyboard(user.language, is_admin=is_admin),
            parse_mode="HTML",
        )
    except ValueError as e:
        await callback.answer(str(e)[:180], show_alert=True)
    except Exception as e:
        logger.exception("loan confirm error")
        await callback.answer(f"Error: {str(e)[:120]}", show_alert=True)

    await callback.answer()


@router.callback_query(F.data == "loan:list")
async def list_loans(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    loans = await get_active_loans(session, user.id)

    if not loans:
        await callback.message.edit_text(
            "⚡ <b>My Loans</b>\n\n" + t("no_active_loans", user.language),
            reply_markup=back_keyboard(user.language),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    lines = [
        "⚡ <b>My Loans</b>\n\n"
        "Pending = waiting admin. Active = repay (principal + 1% interest).\n"
    ]
    for loan in loans:
        paid = sum(1 for i in loan.installments if i.status.value == "paid")
        st = loan.status.value
        lines.append(
            f"#{loan.id} — {loan.amount} (+{loan.interest_amount or 0} int) [{st}] "
            f"({paid}/{loan.installments_count})"
        )
        if st == "active":
            builder.row(
                InlineKeyboardButton(
                    text=f"Loan #{loan.id} — Pay",
                    callback_data=f"repay:loan:{loan.id}",
                )
            )

    builder.row(InlineKeyboardButton(text=t("back", user.language), callback_data="menu:main"))
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()
