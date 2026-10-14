from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Installment, InstallmentStatus, Loan, LoanStatus
from keyboards.inline import back_keyboard
from locales import t
from services.loan_service import get_or_create_user, mark_installment_paid
from services.xrocket import get_xrocket, XRocketError

router = Router(name="repay")


@router.callback_query(F.data.startswith("repay:loan:"))
async def show_loan_installments(callback: CallbackQuery, session: AsyncSession):
    loan_id = int(callback.data.split(":")[2])
    user = await get_or_create_user(session, callback.from_user.id)

    result = await session.execute(
        select(Loan)
        .where(Loan.id == loan_id, Loan.user_id == user.id)
        .options(selectinload(Loan.installments))
    )
    loan = result.scalar_one_or_none()
    if not loan:
        await callback.answer("Loan not found", show_alert=True)
        return

    lines = [f"📋 Loan #{loan.id} — {loan.amount} {loan.currency}\n"]
    builder = InlineKeyboardBuilder()

    for inst in sorted(loan.installments, key=lambda x: x.number):
        status_emoji = "✅" if inst.status == InstallmentStatus.PAID else "⏳"
        if inst.status == InstallmentStatus.OVERDUE:
            status_emoji = "🔴"
        lines.append(
            f"{status_emoji} #{inst.number}: {inst.amount} USDT — due {inst.due_date.date()}"
        )
        if inst.status in (InstallmentStatus.PENDING, InstallmentStatus.OVERDUE):
            builder.row(
                InlineKeyboardButton(
                    text=f"Pay installment #{inst.number}",
                    callback_data=f"repay:inst:{inst.id}",
                    style="success",
                )
            )

    builder.row(
        InlineKeyboardButton(text=t("back", user.language), callback_data="loan:list", style="danger")
    )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("repay:inst:"))
async def create_repayment_invoice(callback: CallbackQuery, session: AsyncSession):
    inst_id = int(callback.data.split(":")[2])
    user = await get_or_create_user(session, callback.from_user.id)

    result = await session.execute(
        select(Installment)
        .where(Installment.id == inst_id)
        .options(selectinload(Installment.loan).selectinload(Loan.user))
    )
    inst = result.scalar_one_or_none()
    if not inst or inst.loan.user_id != user.id:
        await callback.answer("Installment not found", show_alert=True)
        return

    if inst.status == InstallmentStatus.PAID:
        await callback.answer("Already paid", show_alert=True)
        return

    xrocket = get_xrocket()
    try:
        invoice = await xrocket.create_invoice(
            amount=str(inst.amount),
            currency="USDT",
            description=f"Repayment Loan #{inst.loan_id} Installment #{inst.number}",
            client_invoice_id=f"repay-{inst.id}-{user.telegram_id}",
            telegram_id=user.telegram_id,
            expires_in=86400 * 3,
        )
        link = None
        if isinstance(invoice, dict):
            links = invoice.get("links") or {}
            link = links.get("webLink") or links.get("botLink") or invoice.get("link")
            inst.invoice_id = str(invoice.get("id") or "")
            inst.invoice_link = link
            await session.commit()

        text = (
            f"💳 <b>Pay Installment #{inst.number}</b>\n\n"
            f"Amount: <b>{inst.amount} USDT</b>\n\n"
            f"Click the button below to pay via xRocket."
        )
        builder = InlineKeyboardBuilder()
        if link:
            builder.row(
                InlineKeyboardButton(text="💸 Pay Now", url=link, style="success")
            )
        builder.row(
            InlineKeyboardButton(
                text="🔄 I paid — Check", callback_data=f"repay:check:{inst.id}", style="primary"
            )
        )
        builder.row(
            InlineKeyboardButton(text=t("back", user.language), callback_data=f"repay:loan:{inst.loan_id}", style="danger")
        )

        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except XRocketError as e:
        logger.error("Invoice creation failed: {}", e)
        await callback.answer("Payment system error", show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("repay:check:"))
async def check_payment(callback: CallbackQuery, session: AsyncSession):
    inst_id = int(callback.data.split(":")[2])
    user = await get_or_create_user(session, callback.from_user.id)

    result = await session.execute(
        select(Installment)
        .where(Installment.id == inst_id)
        .options(selectinload(Installment.loan).selectinload(Loan.user))
    )
    inst = result.scalar_one_or_none()
    if not inst or inst.loan.user_id != user.id:
        await callback.answer("Not found", show_alert=True)
        return

    if inst.status == InstallmentStatus.PAID:
        await callback.answer("Already marked as paid ✅", show_alert=True)
        return

    if not inst.invoice_id:
        await callback.answer("No invoice", show_alert=True)
        return

    xrocket = get_xrocket()
    try:
        inv = await xrocket.get_invoice(inst.invoice_id)
        # Heuristic: check status / payments
        status = (inv.get("status") or "").lower() if isinstance(inv, dict) else ""
        payments = inv.get("payments") or []
        paid = status in ("paid", "completed", "success") or len(payments) > 0

        if paid:
            await mark_installment_paid(session, inst)
            await session.commit()
            await callback.answer("Payment confirmed! ✅", show_alert=True)
            await callback.message.edit_text(
                f"✅ Installment #{inst.number} paid successfully!",
                reply_markup=back_keyboard(user.language, f"repay:loan:{inst.loan_id}"),
            )
        else:
            await callback.answer("Payment not detected yet. Try again in a minute.", show_alert=True)
    except Exception as e:
        logger.exception("Check payment failed")
        await callback.answer("Error checking payment", show_alert=True)
