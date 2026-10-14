"""Core loan & credit logic — loans need admin approval before payout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database.models import Installment, InstallmentStatus, Loan, LoanStatus, User
from services.xrocket import XRocketClient, get_xrocket

settings = get_settings()


async def get_or_create_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None = None,
    full_name: str | None = None,
    language: str = "en",
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        if username and user.username != username:
            user.username = username
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        return user

    user = User(
        telegram_id=telegram_id,
        username=username,
        full_name=full_name,
        language=language,
        credit_limit=Decimal(str(settings.initial_credit_limit)),
    )
    session.add(user)
    await session.flush()
    return user


def is_admin_user(username: str | None, telegram_id: int | None = None) -> bool:
    uname = (username or "").lower().lstrip("@")
    if uname and uname in settings.admin_list:
        return True
    admin_ids = getattr(settings, "admin_ids", "") or ""
    if telegram_id and admin_ids:
        ids = {int(x.strip()) for x in str(admin_ids).split(",") if x.strip().isdigit()}
        if telegram_id in ids:
            return True
    return False


async def get_admin_telegram_ids(session: AsyncSession) -> list[int]:
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [u.telegram_id for u in users if is_admin_user(u.username, u.telegram_id)]


def calculate_next_limit(current: Decimal, successful: int) -> Decimal:
    if successful > 0 and successful % settings.successful_loans_for_upgrade == 0:
        new_limit = current * Decimal(str(settings.credit_multiplier))
        return min(new_limit, Decimal(str(settings.max_loan_amount)))
    return current


async def create_loan_request(
    session: AsyncSession,
    user: User,
    amount: Decimal,
    installments_count: int,
) -> Loan:
    if user.is_blocked:
        raise ValueError("User is blocked")
    if amount > user.credit_limit:
        raise ValueError("Amount exceeds credit limit")
    if amount < Decimal(str(settings.min_loan_amount)):
        raise ValueError("Amount below minimum")

    existing = await session.execute(
        select(Loan).where(
            Loan.user_id == user.id,
            Loan.status.in_([LoanStatus.PENDING, LoanStatus.ACTIVE]),
        )
    )
    if existing.scalars().first():
        raise ValueError("You already have a pending or active loan")

    installment_amount = (amount / installments_count).quantize(Decimal("0.01"))
    now = datetime.now(timezone.utc)

    loan = Loan(
        user_id=user.id,
        amount=amount,
        currency=settings.default_currency,
        installments_count=installments_count,
        installment_amount=installment_amount,
        status=LoanStatus.PENDING,
    )
    session.add(loan)
    await session.flush()

    for i in range(1, installments_count + 1):
        session.add(
            Installment(
                loan_id=loan.id,
                number=i,
                amount=installment_amount,
                due_date=now + timedelta(days=7 * i),
                status=InstallmentStatus.PENDING,
            )
        )
    await session.flush()
    logger.info("Loan request #{} PENDING for user {}", loan.id, user.telegram_id)
    return loan


async def approve_and_disburse(
    session: AsyncSession,
    loan: Loan,
    xrocket: XRocketClient | None = None,
) -> Loan:
    if loan.status != LoanStatus.PENDING:
        raise ValueError(f"Loan is not pending (status={loan.status})")

    user = loan.user
    if user is None:
        result = await session.execute(select(User).where(User.id == loan.user_id))
        user = result.scalar_one()

    client = xrocket or get_xrocket()
    cid = f"l{loan.id}u{user.telegram_id}"[:50]
    now = datetime.now(timezone.utc)

    payout = await client.create_payout(
        telegram_user_id=user.telegram_id,
        amount=str(loan.amount),
        asset=loan.currency or settings.default_currency,
        description=f"Loan #{loan.id} Marcenzo",
        client_payout_id=cid,
    )
    payout = payout or {}
    loan.payout_id = str(
        payout.get("payoutId") or payout.get("id") or payout.get("transferId") or ""
    )
    loan.client_payout_id = cid
    loan.status = LoanStatus.ACTIVE
    loan.issued_at = now
    loan.due_date = now + timedelta(days=7 * loan.installments_count)
    user.total_borrowed += loan.amount
    await session.flush()
    logger.info("Loan {} APPROVED & disbursed to {}", loan.id, user.telegram_id)
    return loan


async def reject_loan(session: AsyncSession, loan: Loan) -> Loan:
    if loan.status != LoanStatus.PENDING:
        raise ValueError("Loan is not pending")
    loan.status = LoanStatus.CANCELLED
    await session.flush()
    return loan


async def mark_installment_paid(
    session: AsyncSession,
    installment: Installment,
    paid_amount: Decimal | None = None,
) -> None:
    paid = paid_amount or installment.amount
    installment.paid_amount = paid
    installment.status = InstallmentStatus.PAID
    installment.paid_at = datetime.now(timezone.utc)
    loan = installment.loan
    user = loan.user
    user.total_repaid += paid
    if all(i.status == InstallmentStatus.PAID for i in loan.installments):
        loan.status = LoanStatus.COMPLETED
        loan.completed_at = datetime.now(timezone.utc)
        user.successful_loans += 1
        user.credit_limit = calculate_next_limit(user.credit_limit, user.successful_loans)
    await session.flush()


async def get_active_loans(session: AsyncSession, user_id: int) -> list[Loan]:
    result = await session.execute(
        select(Loan)
        .where(
            Loan.user_id == user_id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.PENDING]),
        )
        .options(selectinload(Loan.installments))
        .order_by(Loan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_pending_loans(session: AsyncSession) -> list[Loan]:
    result = await session.execute(
        select(Loan)
        .where(Loan.status == LoanStatus.PENDING)
        .options(selectinload(Loan.user))
        .order_by(Loan.created_at.asc())
    )
    return list(result.scalars().all())
