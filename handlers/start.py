from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from keyboards.inline import language_keyboard, main_menu_keyboard
from locales import t
from services.loan_service import get_or_create_user

router = Router(name="start")
settings = get_settings()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # First time → force language selection
    if user.language == "en" and not user.username:  # simple heuristic, can improve
        await message.answer(
            t("welcome", "en"),
            reply_markup=language_keyboard(),
            parse_mode="HTML",
        )
        return

    is_admin = (message.from_user.username or "").lower() in settings.admin_list
    text = t(
        "main_menu",
        user.language,
        limit=user.credit_limit,
        success=user.successful_loans,
    )
    await message.answer(
        text,
        reply_markup=main_menu_keyboard(user.language, is_admin=is_admin),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("lang:"))
async def set_language(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    lang = callback.data.split(":")[1]
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        language=lang,
    )
    user.language = lang
    await session.commit()

    await callback.message.edit_text(t("language_set", lang))

    is_admin = (callback.from_user.username or "").lower() in settings.admin_list
    text = t(
        "main_menu",
        lang,
        limit=user.credit_limit,
        success=user.successful_loans,
    )
    await callback.message.answer(
        text,
        reply_markup=main_menu_keyboard(lang, is_admin=is_admin),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "menu:main")
async def back_to_main(callback: CallbackQuery, session: AsyncSession):
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    is_admin = (callback.from_user.username or "").lower() in settings.admin_list
    text = t(
        "main_menu",
        user.language,
        limit=user.credit_limit,
        success=user.successful_loans,
    )
    await callback.message.edit_text(
        text,
        reply_markup=main_menu_keyboard(user.language, is_admin=is_admin),
        parse_mode="HTML",
    )
    await callback.answer()
