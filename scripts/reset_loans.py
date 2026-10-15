#!/usr/bin/env python3
"""Wipe all loans/installments and reset user loan stats to day-one defaults."""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, update

from config import get_settings
from database.models import Installment, Loan, User
from database.session import async_session, init_db


async def reset_all() -> None:
    settings = get_settings()
    initial = Decimal(str(settings.initial_credit_limit))

    await init_db()
    async with async_session() as session:
        r1 = await session.execute(delete(Installment))
        r2 = await session.execute(delete(Loan))
        await session.execute(
            update(User).values(
                level=1,
                credit_limit=initial,
                successful_loans=0,
                total_borrowed=Decimal("0.00"),
                total_repaid=Decimal("0.00"),
            )
        )
        await session.commit()
        print(
            f"OK: deleted installments={r1.rowcount} loans={r2.rowcount}; "
            f"all users reset (level=1, limit={initial}, successful_loans=0)"
        )


if __name__ == "__main__":
    asyncio.run(reset_all())
