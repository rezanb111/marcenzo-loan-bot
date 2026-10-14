from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database.models import Loan, LoanStatus, SupportTicket, TicketStatus, User
from services.loan_service import get_or_create_user

router = Router(name="admin")
settings = get_settings()


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        username = (event.from_user.username or "").lower()
        return username in settings.admin_list


class AdminFSM(StatesGroup):
    block_id = State()
    block_reason = State()
    unblock_id = State()
    setlimit_id = State()
    setlimit_amount = State()
    reply_ticket = State()


@router.callback_query(F.data == "admin:panel", IsAdmin())
async def admin_panel(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    await state.clear()
    total_users = await session.scalar(select(func.count(User.id))) or 0
    total_loans = await session.scalar(select(func.count(Loan.id))) or 0
    active_loans = await session.scalar(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.ACTIVE)
    ) or 0
    open_tickets = await session.scalar(
        select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.OPEN)
    ) or 0
    total_volume = await session.scalar(select(func.sum(Loan.amount))) or Decimal("0")

    text = (
        "👑 <b>پنل ادمین — Marcenzo</b>\n\n"
        f"👥 کاربران: <b>{total_users}</b>\n"
        f"📋 کل وام‌ها: <b>{total_loans}</b>\n"
        f"🟢 وام فعال: <b>{active_loans}</b>\n"
        f"💬 تیکت باز: <b>{open_tickets}</b>\n"
        f"💰 حجم کل: <b>{total_volume} USDT</b>\n"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 کاربران", callback_data="admin:users:0", style="primary"),
        InlineKeyboardButton(text="📋 وام‌ها", callback_data="admin:loans:0", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 بلاک", callback_data="admin:block", style="danger"),
        InlineKeyboardButton(text="✅ آنبلاک", callback_data="admin:unblock", style="success"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 تعیین سقف اعتبار", callback_data="admin:setlimit", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 تیکت‌های پشتیبانی", callback_data="admin:tickets:0", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 منوی اصلی", callback_data="menu:main", style="danger"),
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:users:"), IsAdmin())
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[2])
    limit, offset = 10, page * 10
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    if not users:
        await callback.answer("کاربر بیشتری نیست", show_alert=True)
        return

    lines = []
    for u in users:
        st = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{st} <code>{u.telegram_id}</code> @{u.username or '-'} "
            f"| سقف {u.credit_limit} | موفق {u.successful_loans}"
        )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ قبل", callback_data=f"admin:users:{page - 1}")
    builder.button(text="بعد ➡️", callback_data=f"admin:users:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel", style="danger"))

    await callback.message.edit_text(
        f"👥 <b>کاربران</b> (صفحه {page + 1})\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:loans:"), IsAdmin())
async def admin_loans(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[2])
    result = await session.execute(
        select(Loan)
        .where(Loan.status == LoanStatus.ACTIVE)
        .options(selectinload(Loan.user))
        .order_by(Loan.created_at.desc())
        .offset(page * 8)
        .limit(8)
    )
    loans = result.scalars().all()
    if not loans:
        await callback.answer("وام فعالی نیست", show_alert=True)
        return

    lines = []
    for loan in loans:
        uname = loan.user.username if loan.user else "-"
        lines.append(
            f"#{loan.id} @{uname} | {loan.amount} {loan.currency} | {loan.installments_count} قسط"
        )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ قبل", callback_data=f"admin:loans:{page - 1}")
    builder.button(text="بعد ➡️", callback_data=f"admin:loans:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel", style="danger"))

    await callback.message.edit_text(
        f"📋 <b>وام‌های فعال</b>\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------- Block (FSM) ----------
@router.callback_query(F.data == "admin:block", IsAdmin())
async def admin_block_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.block_id)
    await callback.message.edit_text(
        "🚫 <b>بلاک کاربر</b>\n\nآیدی عددی تلگرام را بفرست:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminFSM.block_id, IsAdmin())
async def admin_block_id(message: Message, state: FSMContext):
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("آیدی عددی معتبر بفرست.")
        return
    await state.update_data(block_tg_id=tg_id)
    await state.set_state(AdminFSM.block_reason)
    await message.answer("دلیل بلاک را بنویس (یا - برای بدون دلیل):")


@router.message(AdminFSM.block_reason, IsAdmin())
async def admin_block_reason(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    tg_id = data["block_tg_id"]
    reason = (message.text or "-").strip()
    if reason == "-":
        reason = "Blocked by admin"

    user = await get_or_create_user(session, tg_id)
    user.is_blocked = True
    user.block_reason = reason
    await session.commit()
    await state.clear()
    await message.answer(f"✅ کاربر <code>{tg_id}</code> بلاک شد.\nدلیل: {reason}", parse_mode="HTML")


# ---------- Unblock ----------
@router.callback_query(F.data == "admin:unblock", IsAdmin())
async def admin_unblock_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.unblock_id)
    await callback.message.edit_text("✅ آیدی عددی کاربر برای آنبلاک:")
    await callback.answer()


@router.message(AdminFSM.unblock_id, IsAdmin())
async def admin_unblock_id(message: Message, session: AsyncSession, state: FSMContext):
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("آیدی نامعتبر")
        return
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = False
    user.block_reason = None
    await session.commit()
    await state.clear()
    await message.answer(f"✅ کاربر <code>{tg_id}</code> آنبلاک شد.", parse_mode="HTML")


# ---------- Set limit ----------
@router.callback_query(F.data == "admin:setlimit", IsAdmin())
async def admin_setlimit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.setlimit_id)
    await callback.message.edit_text("📈 آیدی عددی کاربر:")
    await callback.answer()


@router.message(AdminFSM.setlimit_id, IsAdmin())
async def admin_setlimit_id(message: Message, state: FSMContext):
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("آیدی نامعتبر")
        return
    await state.update_data(limit_tg_id=tg_id)
    await state.set_state(AdminFSM.setlimit_amount)
    await message.answer("مبلغ سقف اعتبار (مثلاً 10 یا 25.5):")


@router.message(AdminFSM.setlimit_amount, IsAdmin())
async def admin_setlimit_amount(message: Message, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    tg_id = data["limit_tg_id"]
    try:
        amount = Decimal((message.text or "").strip().replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("مبلغ نامعتبر")
        return
    user = await get_or_create_user(session, tg_id)
    user.credit_limit = amount
    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ سقف اعتبار <code>{tg_id}</code> = <b>{amount} USDT</b>",
        parse_mode="HTML",
    )


# ---------- Tickets ----------
@router.callback_query(F.data.startswith("admin:tickets:"), IsAdmin())
async def admin_tickets(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[2])
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.status == TicketStatus.OPEN)
        .options(selectinload(SupportTicket.user))
        .order_by(SupportTicket.created_at.desc())
        .offset(page * 5)
        .limit(5)
    )
    tickets = result.scalars().all()
    if not tickets:
        await callback.answer("تیکت بازی نیست", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    lines = ["💬 <b>تیکت‌های باز</b>\n"]
    for tk in tickets:
        uname = tk.user.username if tk.user else "-"
        lines.append(f"#{tk.id} @{uname}\n{tk.message[:80]}...")
        builder.row(
            InlineKeyboardButton(
                text=f"پاسخ #{tk.id}",
                callback_data=f"admin:reply:{tk.id}",
                style="success",
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin:panel", style="danger"))

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:reply:"), IsAdmin())
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split(":")[2])
    await state.set_state(AdminFSM.reply_ticket)
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.edit_text(f"پاسخ تیکت #{ticket_id} را بنویس:")
    await callback.answer()


@router.message(AdminFSM.reply_ticket, IsAdmin())
async def admin_reply_send(message: Message, session: AsyncSession, state: FSMContext, bot):
    data = await state.get_data()
    ticket_id = data["reply_ticket_id"]
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.user))
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        await message.answer("تیکت پیدا نشد")
        await state.clear()
        return

    ticket.admin_reply = message.text
    ticket.status = TicketStatus.ANSWERED
    await session.commit()
    await state.clear()

    try:
        await bot.send_message(
            ticket.user.telegram_id,
            f"💬 <b>پاسخ پشتیبانی (تیکت #{ticket.id})</b>\n\n{message.text}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(f"✅ پاسخ تیکت #{ticket_id} ارسال شد.")


# Commands still work
@router.message(F.text.startswith("/block"), IsAdmin())
async def cmd_block(message: Message, session: AsyncSession):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /block <id> [reason]", parse_mode="HTML")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("Invalid id")
        return
    reason = parts[2] if len(parts) > 2 else "Blocked by admin"
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = True
    user.block_reason = reason
    await session.commit()
    await message.answer(f"✅ Blocked {tg_id}")


@router.message(F.text.startswith("/unblock"), IsAdmin())
async def cmd_unblock(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unblock <id>", parse_mode="HTML")
        return
    tg_id = int(parts[1])
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = False
    user.block_reason = None
    await session.commit()
    await message.answer(f"✅ Unblocked {tg_id}")


@router.message(F.text.startswith("/setlimit"), IsAdmin())
async def cmd_setlimit(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /setlimit <id> <amount>", parse_mode="HTML")
        return
    tg_id = int(parts[1])
    amount = Decimal(parts[2])
    user = await get_or_create_user(session, tg_id)
    user.credit_limit = amount
    await session.commit()
    await message.answer(f"✅ Limit {tg_id} = {amount}")
