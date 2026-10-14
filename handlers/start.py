from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.inline import main_menu_keyboard
from locales import t
from services.loan_service import get_or_create_user, is_admin_user

router = Router(name="start")


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

    is_admin = is_admin_user(callback.from_user.username, callback.from_user.id)
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
async def back_to_main(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )
    is_admin = is_admin_user(callback.from_user.username, callback.from_user.id)
    text = t(
        "main_menu",
        user.language or "en",
        limit=user.credit_limit,
        success=user.successful_loans,
    )
    try:
        await callback.message.edit_text(
            text,
            reply_markup=main_menu_keyboard(user.language or "en", is_admin=is_admin),
            parse_mode="HTML",
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=main_menu_keyboard(user.language or "en", is_admin=is_admin),
            parse_mode="HTML",
        )
    await callback.answer()
