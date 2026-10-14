from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import SupportTicket, TicketStatus
from keyboards.inline import back_keyboard, EMOJI
from locales import t
from services.loan_service import get_or_create_user

router = Router(name="support")
settings = get_settings()


class SupportFSM(StatesGroup):
    message = State()


@router.callback_query(F.data == "support")
async def support_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(session, callback.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📝 ارسال تیکت جدید",
            callback_data="support:new",
            style="success",
            icon_custom_emoji_id=EMOJI.get("heart"),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📩 تماس مستقیم ادمین",
            url=f"https://t.me/{settings.support_username}",
            style="primary",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("back", user.language),
            callback_data="menu:main",
            style="danger",
            icon_custom_emoji_id=EMOJI.get("down"),
        )
    )

    text = (
        "🆘 <b>پشتیبانی Marcenzo</b>\n\n"
        "می‌تونی تیکت بسازی تا ادمین جواب بده،\n"
        "یا مستقیم به ادمین پیام بدی.\n\n"
        f"ادمین: @{settings.support_username}"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "support:new")
async def support_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportFSM.message)
    await callback.message.edit_text(
        "📝 مشکلت یا سوالت را کامل بنویس:\n\n(بعد از ارسال، تیکت برای ادمین می‌رود)"
    )
    await callback.answer()


@router.message(SupportFSM.message)
async def support_save(message: Message, session: AsyncSession, state: FSMContext, bot):
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("پیام خیلی کوتاه است. بیشتر توضیح بده.")
        return

    ticket = SupportTicket(
        user_id=user.id,
        subject="User support",
        message=text,
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ تیکت #{ticket.id} ثبت شد.\nبه زودی پاسخ می‌دهیم.",
        reply_markup=back_keyboard(user.language),
    )

    # Notify admins (best-effort via username not possible; use known admin chat if they messaged bot)
    # Admins will see tickets in admin panel.
