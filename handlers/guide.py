from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.inline import back_keyboard
from services.loan_service import get_or_create_user

router = Router(name="guide")

FULL_GUIDE = """📖 <b>Marcenzo Loan Bot — User Guide</b>

🚀 <b>Request Loan</b>
Borrow from 0.10 USDT up to your credit limit.
You receive the principal; you repay principal + <b>1% interest</b> in installments.
Every request needs <b>admin approval</b> before money is sent to your xRocket wallet.
Credit limit starts at 5 USDT and can double after every 3 successful on-time loans (max 100).

⚡ <b>My Loans</b>
See pending and active loans, installment progress, and pay open installments via xRocket invoice.

💎 <b>Invest</b>
Deposit USDT into the community fund. When borrowers repay, the <b>1% interest</b> is shared among investors proportional to their stake.

⭐ <b>Profile</b>
Your ID, credit limit, borrowed/repaid totals, invested amount and earned interest.

❤️ <b>Support</b>
Open a ticket or message admins directly.

⚙️ <b>Admin</b> (admins only)
Approve/reject loans, block users, set limits, answer tickets.

⚠️ Always open <b>@xRocket</b> at least once so payouts can reach you."""


@router.callback_query(F.data == "guide")
async def show_guide(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    await callback.message.edit_text(
        FULL_GUIDE,
        reply_markup=back_keyboard(user.language),
        parse_mode="HTML",
    )
    await callback.answer()
