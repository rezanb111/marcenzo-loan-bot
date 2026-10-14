from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.inline import back_keyboard
from services.loan_service import get_or_create_user

router = Router(name="profile")


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    text = (
        f"⭐ <b>Profile</b>\n\n"
        f"Your account overview. Credit grows after 3 successful loans.\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: @{user.username or '-'}\n"
        f"Language: {user.language}\n\n"
        f"💳 Credit limit: <b>{user.credit_limit} USDT</b>\n"
        f"✅ Successful loans: <b>{user.successful_loans}</b>\n"
        f"📤 Total borrowed: <b>{user.total_borrowed} USDT</b>\n"
        f"📥 Total repaid: <b>{user.total_repaid} USDT</b>\n"
        f"💎 Invested: <b>{getattr(user, 'invested_amount', 0)} USDT</b>\n"
        f"📈 Earned interest: <b>{getattr(user, 'earned_interest', 0)} USDT</b>\n"
    )
    if user.is_blocked:
        text += f"\n🚫 <b>Blocked</b>: {user.block_reason or '-'}"

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(user.language),
        parse_mode="HTML",
    )
    await callback.answer()
