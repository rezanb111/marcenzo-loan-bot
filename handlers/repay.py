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
from services.loan_service import get_or_create_user, mark_installment_paid, payable_installment_amount
from services.polygon_pay import (
    PolygonError,
    async_get_usdt_balance,
    async_sweep_deposit_to_treasury,
    get_deposit_wallet,
    payment_instructions,
)

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
            f"Pay on <b>Polygon</b> USDT · each installment has its own deposit address\n",
            f"Base interest: {loan.interest_percent}% · "
            f"late +{settings.late_increase_percent:g}% / {settings.interest_period_days}d\n",
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
async def show_deposit_address(callback: CallbackQuery, session: AsyncSession):
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
        wallet = get_deposit_wallet(inst.id, user.telegram_id)
        # Store address in invoice_link field for reference
        inst.invoice_link = wallet.address
        inst.invoice_id = f"poly-dep-{inst.id}"
        await session.commit()

        text = payment_instructions(inst.id, user.telegram_id, pay_amt)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(
                text="✅ I paid — Verify & Sweep",
                callback_data=f"repay:check:{inst.id}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔄 Refresh balance",
                callback_data=f"repay:bal:{inst.id}",
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
    except PolygonError as e:
        await callback.answer(str(e)[:120], show_alert=True)
    except Exception as e:
        logger.exception("repay:inst")
        await callback.answer(str(e)[:120], show_alert=True)


@router.callback_query(F.data.startswith("repay:bal:"))
async def refresh_balance(callback: CallbackQuery, session: AsyncSession):
    try:
        inst_id = int(callback.data.split(":")[2])
        user = await get_or_create_user(session, callback.from_user.id)
        result = await session.execute(
            select(Installment)
            .where(Installment.id == inst_id)
            .options(selectinload(Installment.loan))
        )
        inst = result.scalar_one_or_none()
        if not inst or inst.loan.user_id != user.id:
            await callback.answer("Not found", show_alert=True)
            return
        w = get_deposit_wallet(inst.id, user.telegram_id)
        bal = await async_get_usdt_balance(w.address)
        need = payable_installment_amount(inst)
        await callback.answer(
            f"Deposit {w.address[:10]}… balance: {bal} USDT (need {need})",
            show_alert=True,
        )
    except Exception as e:
        await callback.answer(str(e)[:100], show_alert=True)


@router.callback_query(F.data.startswith("repay:check:"))
async def verify_and_sweep(callback: CallbackQuery, session: AsyncSession):
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

        need = payable_installment_amount(inst)
        # Allow small underpay tolerance 0.01
        min_ok = need - Decimal("0.01")

        await callback.answer("Checking chain & sweeping…")
        sweep = await async_sweep_deposit_to_treasury(
            installment_id=inst.id,
            user_telegram_id=user.telegram_id,
            min_amount=min_ok,
        )

        if not sweep.get("ok"):
            reason = sweep.get("reason")
            got = sweep.get("usdt")
            if reason == "no_usdt":
                await callback.answer(
                    "No USDT on your deposit address yet. Send payment and retry.",
                    show_alert=True,
                )
            elif reason == "below_min":
                await callback.answer(
                    f"Received {got} USDT but need ≥ {need}. Send the rest and retry.",
                    show_alert=True,
                )
            else:
                await callback.answer(f"Not confirmed: {reason}", show_alert=True)
            return

        paid_amt = Decimal(str(sweep["usdt"]))
        inst.invoice_link = sweep.get("deposit")
        # reuse invoice_id field for sweep tx if model has no repay_tx_hash column
        inst.invoice_id = str(sweep.get("sweep_tx") or sweep.get("gas_tx") or "")
        await mark_installment_paid(session, inst, paid_amount=paid_amt)
        await session.commit()

        await _safe_text(
            callback,
            f"✅ <b>Installment #{inst.number} paid</b>\n\n"
            f"Amount: <b>{paid_amt} USDT</b>\n"
            f"Swept to treasury.\n"
            f"Tx: <code>{sweep.get('sweep_tx', '-')}</code>",
            InlineKeyboardBuilder()
            .row(
                InlineKeyboardButton(
                    text="🔙 Installments",
                    callback_data=f"repay:loan:{inst.loan_id}",
                )
            )
            .as_markup(),
        )
    except PolygonError as e:
        logger.error("sweep polygon error: {}", e)
        await callback.answer(str(e)[:120], show_alert=True)
    except Exception as e:
        logger.exception("verify_and_sweep failed")
        await callback.answer(f"Error: {str(e)[:100]}", show_alert=True)
