from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import SupportTicket, TicketStatus
from keyboards.inline import EMOJI, back_keyboard
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
            text="📝 New ticket",
            callback_data="support:new",
            style="success",
            icon_custom_emoji_id=EMOJI.get("heart"),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📩 Message admin directly",
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
        "🆘 <b>Marcenzo Support</b>\n\n"
        "Open a ticket and an admin will reply,\n"
        "or message the admin directly.\n\n"
        f"Admin: @{settings.support_username}"
    )
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "support:new")
async def support_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportFSM.message)
    await callback.message.edit_text(
        "📝 Describe your issue or question:\n\n(After you send it, a ticket is created for admins.)"
    )
    await callback.answer()


@router.message(SupportFSM.message)
async def support_save(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("Message is too short. Please add more details.")
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
        f"✅ Ticket #{ticket.id} created.\nWe will reply soon.",
        reply_markup=back_keyboard(user.language),
    )
