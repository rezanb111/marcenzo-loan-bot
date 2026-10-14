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
        f"👤 <b>پروفایل</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"یوزرنیم: @{user.username or '-'}\n"
        f"زبان: {user.language}\n\n"
        f"💳 سقف اعتبار: <b>{user.credit_limit} USDT</b>\n"
        f"✅ وام موفق: <b>{user.successful_loans}</b>\n"
        f"📤 کل وام گرفته: <b>{user.total_borrowed} USDT</b>\n"
        f"📥 کل بازپرداخت: <b>{user.total_repaid} USDT</b>\n"
    )
    if user.is_blocked:
        text += f"\n🚫 <b>مسدود</b>: {user.block_reason or '-'}"

    await callback.message.edit_text(
        text,
        reply_markup=back_keyboard(user.language),
        parse_mode="HTML",
    )
    await callback.answer()
