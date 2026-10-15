from datetime import datetime, timezone
from decimal import Decimal

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database.models import Installment, InstallmentStatus, Loan
from locales import t
from services.loan_service import get_or_create_user, mark_installment_paid, payable_installment_amount
from services.xrocket import XRocketError, get_xrocket

router = Router(name="repay")
settings = get_settings()


async def _safe_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data.startswith("repay:loan:"))
async def show_loan_installments(callback: CallbackQuery, session: AsyncSession):
    try:
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

        now = datetime.now(timezone.utc)
        lines = [
            f"📋 <b>Loan #{loan.id}</b> — principal {loan.amount} {loan.currency}\n",
            f"Base interest: {loan.interest_percent}% · "
            f"late +{settings.late_increase_percent:g}% per {settings.interest_period_days}d past due\n",
        ]
        builder = InlineKeyboardBuilder()

        for inst in sorted(loan.installments or [], key=lambda x: x.number):
            pay_amt = payable_installment_amount(inst, now)
            if inst.status == InstallmentStatus.PAID:
                status_emoji = "✅"
            else:
                due = inst.due_date
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                status_emoji = "🔴" if now > due else "⏳"
            extra = ""
            if pay_amt > Decimal(str(inst.amount)) and inst.status != InstallmentStatus.PAID:
                extra = f" (now <b>{pay_amt}</b> incl. late)"
            lines.append(
                f"{status_emoji} #{inst.number}: {inst.amount} USDT{extra} — due {inst.due_date.date()}"
            )
            if inst.status != InstallmentStatus.PAID:
                builder.row(
                    InlineKeyboardButton(
                        text=f"💳 Pay #{inst.number} ({pay_amt} USDT)",
                        callback_data=f"repay:inst:{inst.id}",
                    )
                )

        builder.row(InlineKeyboardButton(text="⚡ My Loans", callback_data="loan:list"))
        builder.row(InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"))

        await _safe_text(callback, "\n".join(lines), builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.exception("repay:loan")
        await callback.answer(str(e)[:120], show_alert=True)


@router.callback_query(F.data.startswith("repay:inst:"))
async def create_repayment_invoice(callback: CallbackQuery, session: AsyncSession):
    try:
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

        pay_amt = payable_installment_amount(inst)
        xrocket = get_xrocket()
        try:
            invoice = await xrocket.create_invoice(
                amount=str(pay_amt),
                currency="USDT",
                description=f"Repay Loan #{inst.loan_id} Inst #{inst.number}",
                client_invoice_id=f"rp{inst.id}u{user.telegram_id}"[:50],
                telegram_id=user.telegram_id,
                expires_in=86400 * 3,
            )
        except XRocketError as e:
            logger.error("Invoice creation failed: {}", e)
            await callback.answer(f"Payment error: {str(e)[:100]}", show_alert=True)
            return

        link = None
        if isinstance(invoice, dict):
            links = invoice.get("links") or {}
            link = (
                links.get("webLink")
                or links.get("botLink")
                or invoice.get("link")
                or invoice.get("paymentLink")
                or invoice.get("url")
            )
            inst.invoice_id = str(
                invoice.get("invoiceId") or invoice.get("id") or ""
            )
            inst.invoice_link = link
            await session.commit()

        text = (
            f"💳 <b>Pay Installment #{inst.number}</b>\n\n"
            f"Amount due: <b>{pay_amt} USDT</b>\n"
            f"(base {inst.amount}"
            + (f" + late to {pay_amt}" if pay_amt != Decimal(str(inst.amount)) else "")
            + ")\n\n"
            f"Pay via xRocket, then tap <b>I paid — Check</b>."
        )
        builder = InlineKeyboardBuilder()
        if link:
            builder.row(InlineKeyboardButton(text="💸 Open Pay Link", url=link))
        builder.row(
            InlineKeyboardButton(
                text="✅ I paid — Check",
                callback_data=f"repay:check:{inst.id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 Installments",
                callback_data=f"repay:loan:{inst.loan_id}",
            )
        )
        await _safe_text(callback, text, builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.exception("repay:inst")
        await callback.answer(str(e)[:120], show_alert=True)


@router.callback_query(F.data.startswith("repay:check:"))
async def check_payment(callback: CallbackQuery, session: AsyncSession):
    try:
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
            await callback.answer("Already paid ✅", show_alert=True)
            return

        if not inst.invoice_id:
            await callback.answer("No invoice yet — create pay link first", show_alert=True)
            return

        xrocket = get_xrocket()
        inv = await xrocket.get_invoice(inst.invoice_id)
        status = ""
        payments = []
        if isinstance(inv, dict):
            status = str(inv.get("status") or "").lower()
            payments = inv.get("payments") or []
        paid = status in ("paid", "completed", "success", "finished") or len(payments) > 0

        if paid:
            await mark_installment_paid(session, inst)
            await session.commit()
            await callback.answer("Payment confirmed! ✅", show_alert=True)
            await _safe_text(
                callback,
                f"✅ Installment #{inst.number} paid successfully!",
                InlineKeyboardBuilder()
                .row(
                    InlineKeyboardButton(
                        text="🔙 Installments",
                        callback_data=f"repay:loan:{inst.loan_id}",
                    )
                )
                .as_markup(),
            )
        else:
            await callback.answer(
                "Payment not detected yet. Wait ~1 min and try again.",
                show_alert=True,
            )
    except Exception as e:
        logger.exception("Check payment failed")
        await callback.answer(f"Check error: {str(e)[:80]}", show_alert=True)
