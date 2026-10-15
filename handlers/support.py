from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import SupportTicket, TicketStatus
from keyboards.inline import back_keyboard
from locales import t
from services.loan_service import get_admin_telegram_ids, get_or_create_user

router = Router(name="support")
settings = get_settings()


class SupportFSM(StatesGroup):
    message = State()


async def _safe_text(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


@router.callback_query(F.data == "support")
async def support_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    try:
        await state.clear()
        user = await get_or_create_user(session, callback.from_user.id)

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📝 New ticket", callback_data="support:new"))
        builder.row(
            InlineKeyboardButton(
                text="📩 Message admin",
                url=f"https://t.me/{settings.support_username.lstrip('@')}",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text="🔙 " + t("back", user.language or "en"),
                callback_data="menu:main",
            )
        )

        text = (
            "🆘 <b>Marcenzo Support</b>\n\n"
            "Open a ticket and an admin will reply,\n"
            "or message the admin directly.\n\n"
            f"Admin: @{settings.support_username.lstrip('@')}"
        )
        await _safe_text(callback, text, builder.as_markup())
        await callback.answer()
    except Exception as e:
        logger.exception("support menu")
        await callback.answer(str(e)[:100], show_alert=True)


@router.callback_query(F.data == "support:new")
async def support_new(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportFSM.message)
    await _safe_text(
        callback,
        "📝 Describe your issue or question:\n\n"
        "(Send one message; a ticket is created for admins.)",
    )
    await callback.answer()


@router.message(SupportFSM.message)
async def support_save(message: Message, session: AsyncSession, state: FSMContext, bot: Bot):
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
        reply_markup=back_keyboard(user.language or "en"),
    )

    # Notify admins
    note = (
        f"🎫 <b>New support ticket #{ticket.id}</b>\n"
        f"From: @{user.username or '-'} (<code>{user.telegram_id}</code>)\n\n"
        f"{text[:500]}"
    )
    for aid in await get_admin_telegram_ids(session):
        try:
            await bot.send_message(aid, note, parse_mode="HTML")
        except Exception:
            pass
