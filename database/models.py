from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class LoanStatus(str, PyEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    DEFAULTED = "defaulted"
    CANCELLED = "cancelled"


class InstallmentStatus(str, PyEnum):
    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    PARTIAL = "partial"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(8), default="en")

    # Credit system
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5.00"))
    successful_loans: Mapped[int] = mapped_column(Integer, default=0)
    total_borrowed: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_repaid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    block_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    loans: Mapped[list["Loan"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.telegram_id} limit={self.credit_limit}>"


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(16), default="USDT")
    installments_count: Mapped[int] = mapped_column(Integer, default=5)
    installment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    status: Mapped[LoanStatus] = mapped_column(
        Enum(LoanStatus), default=LoanStatus.PENDING, index=True
    )

    # xRocket references
    payout_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    client_payout_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    issued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="loans")
    installments: Mapped[list["Installment"]] = relationship(
        back_populates="loan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Loan {self.id} {self.amount} {self.status}>"


class Installment(Base):
    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    loan_id: Mapped[int] = mapped_column(ForeignKey("loans.id"), index=True)

    number: Mapped[int] = mapped_column(Integer)  # 1, 2, 3...
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))

    status: Mapped[InstallmentStatus] = mapped_column(
        Enum(InstallmentStatus), default=InstallmentStatus.PENDING, index=True
    )

    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # xRocket invoice for repayment
    invoice_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    invoice_link: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    loan: Mapped["Loan"] = relationship(back_populates="installments")

    def __repr__(self) -> str:
        return f"<Installment {self.loan_id}-{self.number} {self.amount} {self.status}>"
