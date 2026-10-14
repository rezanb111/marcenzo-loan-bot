from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from services.loan_service import get_or_create_user
from utils.media import send_section

router = Router(name="profile")


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    success = int(user.successful_loans or 0)
    to_next = 3 - (success % 3) if success % 3 else 3
    pwd = "ON ✅" if user.has_password else "OFF (optional)"
    text = (
        f"⭐ <b>Profile</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Username: @{user.username or '-'}\n"
        f"Language: {user.language}\n"
        f"Password: <b>{pwd}</b>\n\n"
        f"🏅 Level: <b>{user.level}</b> — {user.level_name}\n"
        f"📊 Next level after <b>{to_next}</b> more full repayments\n\n"
        f"💳 Credit limit: <b>{user.credit_limit} USDT</b>\n"
        f"✅ Successful loans: <b>{user.successful_loans}</b>\n"
        f"📤 Total borrowed: <b>{user.total_borrowed} USDT</b>\n"
        f"📥 Total repaid: <b>{user.total_repaid} USDT</b>\n"
        f"💎 Invested: <b>{getattr(user, 'invested_amount', 0)} USDT</b>\n"
        f"📈 Earned interest: <b>{getattr(user, 'earned_interest', 0)} USDT</b>\n"
    )
    if user.is_blocked:
        text += f"\n🚫 <b>Blocked</b>: {user.block_reason or '-'}"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔐 Security / Password", callback_data="security:menu"))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="menu:main"))

    await send_section(
        callback, text, section="profile", reply_markup=builder.as_markup()
    )
    await callback.answer()
