"""Entry captcha + optional password lock."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from keyboards.inline import language_keyboard, main_menu_keyboard
from locales import t
from services.loan_service import get_or_create_user, is_admin_user
from services.security import hash_password, make_captcha, verify_password

router = Router(name="auth")


class AuthFSM(StatesGroup):
    captcha = State()
    password_unlock = State()
    set_password = State()
    set_password2 = State()
    remove_password = State()


def captcha_keyboard(options: list[str]) -> object:
    builder = InlineKeyboardBuilder()
    for opt in options:
        # encode answer in callback (short)
        builder.button(text=str(opt), callback_data=f"captcha:ans:{opt}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔄 New challenge", callback_data="captcha:refresh"))
    return builder.as_markup()


async def send_captcha(target: Message, state: FSMContext) -> None:
    ch = make_captcha()
    await state.set_state(AuthFSM.captcha)
    await state.update_data(captcha_answer=ch.answer, captcha_fails=0)
    await target.answer(ch.question, reply_markup=captcha_keyboard(ch.options), parse_mode="HTML")


async def show_main(message_or_cb, session: AsyncSession, user) -> None:
    is_admin = is_admin_user(
        getattr(message_or_cb.from_user, "username", None),
        getattr(message_or_cb.from_user, "id", None),
    )
    text = t(
        "main_menu",
        user.language or "en",
        limit=user.credit_limit,
        success=user.successful_loans,
    )
    kb = main_menu_keyboard(user.language or "en", is_admin=is_admin)
    if isinstance(message_or_cb, CallbackQuery):
        try:
            await message_or_cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await message_or_cb.message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message_or_cb.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    await session.commit()

    await message.answer(
        "🛡️ <b>Marcenzo Security Gate</b>\n\n"
        "Complete the captcha to enter the bot.",
        parse_mode="HTML",
    )
    await send_captcha(message, state)


@router.callback_query(F.data == "captcha:refresh", AuthFSM.captcha)
async def captcha_refresh(callback: CallbackQuery, state: FSMContext):
    ch = make_captcha()
    await state.update_data(captcha_answer=ch.answer)
    await callback.message.edit_text(
        ch.question, reply_markup=captcha_keyboard(ch.options), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("captcha:ans:"), AuthFSM.captcha)
async def captcha_answer(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    correct = str(data.get("captcha_answer", ""))
    chosen = callback.data.split("captcha:ans:", 1)[1]
    fails = int(data.get("captcha_fails", 0))

    if chosen != correct:
        fails += 1
        await state.update_data(captcha_fails=fails)
        if fails >= 5:
            await state.clear()
            await callback.message.edit_text(
                "❌ Too many failed attempts. Send /start to try again."
            )
            await callback.answer("Locked", show_alert=True)
            return
        ch = make_captcha()
        await state.update_data(captcha_answer=ch.answer)
        await callback.message.edit_text(
            f"❌ Wrong. Try again ({fails}/5)\n\n" + ch.question,
            reply_markup=captcha_keyboard(ch.options),
            parse_mode="HTML",
        )
        await callback.answer("Wrong", show_alert=True)
        return

    user = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
    )

    # If optional password is set → ask unlock
    if user.has_password:
        await state.set_state(AuthFSM.password_unlock)
        await state.update_data(session_unlocked=False)
        await callback.message.edit_text(
            "🔑 <b>Password required</b>\n\n"
            "You set an optional password. Send it now to unlock.\n"
            "(If you forgot it, contact support / admin.)",
            parse_mode="HTML",
        )
        await callback.answer("Captcha OK")
        return

    await state.clear()
    await state.update_data(session_unlocked=True)
    await callback.message.edit_text("✅ Captcha passed.")
    await show_main(callback, session, user)
    await callback.message.answer("🌐 Language:", reply_markup=language_keyboard())
    await callback.answer()


@router.message(AuthFSM.password_unlock)
async def password_unlock(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(session, message.from_user.id)
    pwd = (message.text or "").strip()
    # try delete password message for privacy
    try:
        await message.delete()
    except Exception:
        pass

    if not user.has_password:
        await state.clear()
        await show_main(message, session, user)
        return

    if verify_password(pwd, user.password_hash, user.password_salt):
        await state.clear()
        await state.update_data(session_unlocked=True)
        await message.answer("✅ Unlocked.")
        await show_main(message, session, user)
        return

    await message.answer("❌ Wrong password. Try again or /start.")


# ---------- Optional password management (Profile) ----------
@router.callback_query(F.data == "security:menu")
async def security_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(session, callback.from_user.id)
    status = "ON ✅" if user.has_password else "OFF (optional)"
    builder = InlineKeyboardBuilder()
    if user.has_password:
        builder.row(InlineKeyboardButton(text="🔄 Change password", callback_data="security:set"))
        builder.row(InlineKeyboardButton(text="🗑 Remove password", callback_data="security:remove"))
    else:
        builder.row(InlineKeyboardButton(text="🔑 Set password (optional)", callback_data="security:set"))
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="profile"))
    await callback.message.edit_text(
        f"🔐 <b>Security</b>\n\n"
        f"Optional password: <b>{status}</b>\n\n"
        f"If you set a password, every /start (after captcha) will ask for it.\n"
        f"You can skip this forever — it is 100% optional.",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "security:set")
async def security_set(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthFSM.set_password)
    await callback.message.edit_text(
        "🔑 Send a new password (4–32 characters).\n"
        "Or send /cancel to abort."
    )
    await callback.answer()


@router.message(AuthFSM.set_password)
async def security_set1(message: Message, state: FSMContext):
    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await message.answer("Cancelled.")
        return
    pwd = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass
    if len(pwd) < 4 or len(pwd) > 32:
        await message.answer("Password must be 4–32 characters.")
        return
    await state.update_data(new_pwd=pwd)
    await state.set_state(AuthFSM.set_password2)
    await message.answer("Send the same password again to confirm:")


@router.message(AuthFSM.set_password2)
async def security_set2(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    pwd2 = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass
    if pwd2 != data.get("new_pwd"):
        await state.set_state(AuthFSM.set_password)
        await message.answer("Mismatch. Send a new password:")
        return
    user = await get_or_create_user(session, message.from_user.id)
    digest, salt = hash_password(pwd2)
    user.password_hash = digest
    user.password_salt = salt
    await session.commit()
    await state.clear()
    await message.answer("✅ Password saved. It will be asked after captcha on /start.")


@router.callback_query(F.data == "security:remove")
async def security_remove_ask(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AuthFSM.remove_password)
    await callback.message.edit_text("Send your current password to remove it:")
    await callback.answer()


@router.message(AuthFSM.remove_password)
async def security_remove(message: Message, session: AsyncSession, state: FSMContext):
    user = await get_or_create_user(session, message.from_user.id)
    pwd = (message.text or "").strip()
    try:
        await message.delete()
    except Exception:
        pass
    if not user.has_password or not verify_password(pwd, user.password_hash, user.password_salt):
        await message.answer("❌ Wrong password.")
        return
    user.password_hash = None
    user.password_salt = None
    await session.commit()
    await state.clear()
    await message.answer("✅ Password removed. Entry only needs captcha now.")
