from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.inline import back_keyboard
from services.loan_service import get_or_create_user
from utils.media import send_section

router = Router(name="guide")

FULL_GUIDE = """📖 <b>Marcenzo Loan Bot — User Guide</b>

🛡️ <b>Entry</b>
Advanced captcha on /start. Optional password (Profile → Security).

🚀 <b>Request Loan</b>
0.10 USDT up to your limit. Principal + <b>1% interest</b>.
Admin must approve before xRocket payout.

🏅 <b>Levels</b>
Every <b>3 successful full repayments</b> → level +1
(Bronze → Silver → Gold → Platinum → Diamond → Master → Legend)
Credit limit can also double on the same schedule (max 100).

⚡ <b>My Loans</b>
Pending / active loans and installment payments.

💎 <b>Invest</b>
Fund deposits; share of borrower interest by stake.

⭐ <b>Profile</b> · ❤️ <b>Support</b> · ⚙️ <b>Admin</b>

Open <b>@xRocket</b> at least once for payouts."""


@router.callback_query(F.data == "guide")
async def show_guide(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(session, callback.from_user.id)
    await send_section(
        callback,
        FULL_GUIDE,
        section="guide",
        reply_markup=back_keyboard(user.language),
    )
    await callback.answer()
