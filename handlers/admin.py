from decimal import Decimal, InvalidOperation

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from database.models import Loan, LoanStatus, SupportTicket, TicketStatus, User
from services.loan_service import (
    approve_and_disburse,
    get_or_create_user,
    get_pending_loans,
    is_admin_user,
    reject_loan,
)
from services.xrocket import XRocketError

router = Router(name="admin")
settings = get_settings()


def _is_admin(event) -> bool:
    u = event.from_user
    if not u:
        return False
    return is_admin_user(u.username, u.id)


async def _deny(callback: CallbackQuery) -> bool:
    """Return True if denied (and answered)."""
    if _is_admin(callback):
        return False
    await callback.answer(
        "⛔ Access denied. Admins: @marcenzo / @shibainuo only. "
        "Set ADMIN_IDS in .env if your username is hidden.",
        show_alert=True,
    )
    return True


class AdminFSM(StatesGroup):
    block_id = State()
    block_reason = State()
    unblock_id = State()
    setlimit_id = State()
    setlimit_amount = State()
    reply_ticket = State()


@router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery, session: AsyncSession, state: FSMContext):
    if await _deny(callback):
        return
    await state.clear()
    total_users = await session.scalar(select(func.count(User.id))) or 0
    total_loans = await session.scalar(select(func.count(Loan.id))) or 0
    active_loans = (
        await session.scalar(select(func.count(Loan.id)).where(Loan.status == LoanStatus.ACTIVE))
        or 0
    )
    pending_loans = (
        await session.scalar(select(func.count(Loan.id)).where(Loan.status == LoanStatus.PENDING))
        or 0
    )
    open_tickets = (
        await session.scalar(
            select(func.count(SupportTicket.id)).where(SupportTicket.status == TicketStatus.OPEN)
        )
        or 0
    )
    total_volume = await session.scalar(select(func.sum(Loan.amount))) or Decimal("0")

    text = (
        "👑 <b>Admin Panel — Marcenzo</b>\n\n"
        f"👥 Users: <b>{total_users}</b>\n"
        f"📋 Total loans: <b>{total_loans}</b>\n"
        f"⏳ Pending approval: <b>{pending_loans}</b>\n"
        f"🟢 Active loans: <b>{active_loans}</b>\n"
        f"💬 Open tickets: <b>{open_tickets}</b>\n"
        f"💰 Total volume: <b>{total_volume} USDT</b>\n\n"
        f"You: @{callback.from_user.username or '-'} / <code>{callback.from_user.id}</code>"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"⏳ Pending ({pending_loans})", callback_data="admin:pending"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Users", callback_data="admin:users:0"),
        InlineKeyboardButton(text="📋 Active loans", callback_data="admin:loans:0"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Block", callback_data="admin:block"),
        InlineKeyboardButton(text="✅ Unblock", callback_data="admin:unblock"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Set credit limit", callback_data="admin:setlimit"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 Support tickets", callback_data="admin:tickets:0"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Main menu", callback_data="menu:main"),
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin:pending")
async def admin_pending(callback: CallbackQuery, session: AsyncSession):
    if await _deny(callback):
        return
    loans = await get_pending_loans(session)
    if not loans:
        await callback.answer("No pending loans", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    lines = ["⏳ <b>Pending loan requests</b>\n"]
    for loan in loans[:15]:
        uname = loan.user.username if loan.user else "-"
        tg = loan.user.telegram_id if loan.user else "-"
        lines.append(
            f"#{loan.id} @{uname} (<code>{tg}</code>) — <b>{loan.amount}</b> USDT / {loan.installments_count} inst"
        )
        builder.row(
            InlineKeyboardButton(
                text=f"✅ Approve #{loan.id}",
                callback_data=f"admin:loan_approve:{loan.id}",
            ),
            InlineKeyboardButton(
                text=f"❌ Reject #{loan.id}",
                callback_data=f"admin:loan_reject:{loan.id}",
            ),
        )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel"))

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:loan_approve:"))
async def admin_loan_approve(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    if await _deny(callback):
        return
    loan_id = int(callback.data.split(":")[2])
    result = await session.execute(
        select(Loan).where(Loan.id == loan_id).options(selectinload(Loan.user))
    )
    loan = result.scalar_one_or_none()
    if not loan:
        await callback.answer("Loan not found", show_alert=True)
        return
    if loan.status != LoanStatus.PENDING:
        await callback.answer(f"Already {loan.status.value}", show_alert=True)
        return

    try:
        await approve_and_disburse(session, loan)
        await session.commit()
        await callback.message.edit_text(
            f"✅ Loan #{loan.id} <b>approved & paid</b>\n"
            f"{loan.amount} USDT → @{loan.user.username or loan.user.telegram_id}",
            parse_mode="HTML",
        )
        try:
            await bot.send_message(
                loan.user.telegram_id,
                f"✅ Your loan #{loan.id} of <b>{loan.amount} USDT</b> was approved and sent to your xRocket wallet!",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer("Approved")
    except XRocketError as e:
        logger.error("Approve payout failed: {}", e)
        await callback.answer(f"xRocket: {str(e)[:100]}", show_alert=True)
        try:
            await callback.message.answer(f"⚠️ Payout failed:\n<code>{e}</code>", parse_mode="HTML")
        except Exception:
            pass
    except Exception as e:
        logger.exception("approve error")
        await callback.answer(str(e)[:120], show_alert=True)


@router.callback_query(F.data.startswith("admin:loan_reject:"))
async def admin_loan_reject(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    if await _deny(callback):
        return
    loan_id = int(callback.data.split(":")[2])
    result = await session.execute(
        select(Loan).where(Loan.id == loan_id).options(selectinload(Loan.user))
    )
    loan = result.scalar_one_or_none()
    if not loan:
        await callback.answer("Loan not found", show_alert=True)
        return
    if loan.status != LoanStatus.PENDING:
        await callback.answer(f"Already {loan.status.value}", show_alert=True)
        return

    await reject_loan(session, loan)
    await session.commit()
    await callback.message.edit_text(f"❌ Loan #{loan.id} rejected.")
    try:
        await bot.send_message(
            loan.user.telegram_id,
            f"❌ Your loan request #{loan.id} was rejected by admin.",
        )
    except Exception:
        pass
    await callback.answer("Rejected")


@router.callback_query(F.data.startswith("admin:users:"))
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    if await _deny(callback):
        return
    page = int(callback.data.split(":")[2])
    result = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(page * 10).limit(10)
    )
    users = result.scalars().all()
    if not users:
        await callback.answer("No more users", show_alert=True)
        return

    lines = []
    for u in users:
        st = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{st} <code>{u.telegram_id}</code> @{u.username or '-'} "
            f"| limit {u.credit_limit} | ok {u.successful_loans}"
        )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Prev", callback_data=f"admin:users:{page - 1}")
    builder.button(text="Next ➡️", callback_data=f"admin:users:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel"))

    await callback.message.edit_text(
        f"👥 <b>Users</b> (page {page + 1})\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:loans:"))
async def admin_loans(callback: CallbackQuery, session: AsyncSession):
    if await _deny(callback):
        return
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
        await callback.answer("No active loans", show_alert=True)
        return

    lines = []
    for loan in loans:
        uname = loan.user.username if loan.user else "-"
        lines.append(
            f"#{loan.id} @{uname} | {loan.amount} {loan.currency} | {loan.installments_count} inst"
        )

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Prev", callback_data=f"admin:loans:{page - 1}")
    builder.button(text="Next ➡️", callback_data=f"admin:loans:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel"))

    await callback.message.edit_text(
        f"📋 <b>Active loans</b>\n\n" + "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "admin:block")
async def admin_block_start(callback: CallbackQuery, state: FSMContext):
    if await _deny(callback):
        return
    await state.set_state(AdminFSM.block_id)
    await callback.message.edit_text(
        "🚫 <b>Block user</b>\n\nSend Telegram numeric ID:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(AdminFSM.block_id)
async def admin_block_id(message: Message, state: FSMContext):
    if not _is_admin(message):
        return
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Send a valid numeric ID.")
        return
    await state.update_data(block_tg_id=tg_id)
    await state.set_state(AdminFSM.block_reason)
    await message.answer("Reason (or - for none):")


@router.message(AdminFSM.block_reason)
async def admin_block_reason(message: Message, session: AsyncSession, state: FSMContext):
    if not _is_admin(message):
        return
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
    await message.answer(
        f"✅ User <code>{tg_id}</code> blocked.\nReason: {reason}",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "admin:unblock")
async def admin_unblock_start(callback: CallbackQuery, state: FSMContext):
    if await _deny(callback):
        return
    await state.set_state(AdminFSM.unblock_id)
    await callback.message.edit_text("✅ Send Telegram numeric ID to unblock:")
    await callback.answer()


@router.message(AdminFSM.unblock_id)
async def admin_unblock_id(message: Message, session: AsyncSession, state: FSMContext):
    if not _is_admin(message):
        return
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Invalid ID")
        return
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = False
    user.block_reason = None
    await session.commit()
    await state.clear()
    await message.answer(f"✅ User <code>{tg_id}</code> unblocked.", parse_mode="HTML")


@router.callback_query(F.data == "admin:setlimit")
async def admin_setlimit_start(callback: CallbackQuery, state: FSMContext):
    if await _deny(callback):
        return
    await state.set_state(AdminFSM.setlimit_id)
    await callback.message.edit_text("📈 Send Telegram numeric ID:")
    await callback.answer()


@router.message(AdminFSM.setlimit_id)
async def admin_setlimit_id(message: Message, state: FSMContext):
    if not _is_admin(message):
        return
    try:
        tg_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("Invalid ID")
        return
    await state.update_data(limit_tg_id=tg_id)
    await state.set_state(AdminFSM.setlimit_amount)
    await message.answer("Credit limit amount (e.g. 10 or 25.5):")


@router.message(AdminFSM.setlimit_amount)
async def admin_setlimit_amount(message: Message, session: AsyncSession, state: FSMContext):
    if not _is_admin(message):
        return
    data = await state.get_data()
    tg_id = data["limit_tg_id"]
    try:
        amount = Decimal((message.text or "").strip().replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        await message.answer("Invalid amount")
        return
    user = await get_or_create_user(session, tg_id)
    user.credit_limit = amount
    await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Credit limit for <code>{tg_id}</code> = <b>{amount} USDT</b>",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("admin:tickets:"))
async def admin_tickets(callback: CallbackQuery, session: AsyncSession):
    if await _deny(callback):
        return
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
        await callback.answer("No open tickets", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    lines = ["💬 <b>Open tickets</b>\n"]
    for tk in tickets:
        uname = tk.user.username if tk.user else "-"
        lines.append(f"#{tk.id} @{uname}\n{(tk.message or '')[:80]}...")
        builder.row(
            InlineKeyboardButton(text=f"Reply #{tk.id}", callback_data=f"admin:reply:{tk.id}")
        )
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel"))

    await callback.message.edit_text(
        "\n".join(lines), reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:reply:"))
async def admin_reply_start(callback: CallbackQuery, state: FSMContext):
    if await _deny(callback):
        return
    ticket_id = int(callback.data.split(":")[2])
    await state.set_state(AdminFSM.reply_ticket)
    await state.update_data(reply_ticket_id=ticket_id)
    await callback.message.edit_text(f"Write reply for ticket #{ticket_id}:")
    await callback.answer()


@router.message(AdminFSM.reply_ticket)
async def admin_reply_send(message: Message, session: AsyncSession, state: FSMContext, bot: Bot):
    if not _is_admin(message):
        return
    data = await state.get_data()
    ticket_id = data["reply_ticket_id"]
    result = await session.execute(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.user))
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        await message.answer("Ticket not found")
        await state.clear()
        return

    ticket.admin_reply = message.text
    ticket.status = TicketStatus.ANSWERED
    await session.commit()
    await state.clear()

    try:
        await bot.send_message(
            ticket.user.telegram_id,
            f"💬 <b>Support reply (ticket #{ticket.id})</b>\n\n{message.text}",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.answer(f"✅ Reply to ticket #{ticket_id} sent.")


@router.message(F.text.startswith("/block"))
async def cmd_block(message: Message, session: AsyncSession):
    if not _is_admin(message):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /block <id> [reason]")
        return
    tg_id = int(parts[1])
    reason = parts[2] if len(parts) > 2 else "Blocked by admin"
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = True
    user.block_reason = reason
    await session.commit()
    await message.answer(f"✅ Blocked {tg_id}")


@router.message(F.text.startswith("/unblock"))
async def cmd_unblock(message: Message, session: AsyncSession):
    if not _is_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unblock <id>")
        return
    tg_id = int(parts[1])
    user = await get_or_create_user(session, tg_id)
    user.is_blocked = False
    user.block_reason = None
    await session.commit()
    await message.answer(f"✅ Unblocked {tg_id}")


@router.message(F.text.startswith("/setlimit"))
async def cmd_setlimit(message: Message, session: AsyncSession):
    if not _is_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /setlimit <id> <amount>")
        return
    tg_id = int(parts[1])
    amount = Decimal(parts[2])
    user = await get_or_create_user(session, tg_id)
    user.credit_limit = amount
    await session.commit()
    await message.answer(f"✅ Limit {tg_id} = {amount}")


@router.message(F.text == "/admin")
async def cmd_admin(message: Message, session: AsyncSession, state: FSMContext):
    """Open admin panel via command — always works for admins."""
    if not _is_admin(message):
        await message.answer("⛔ Not an admin.")
        return
    # Reuse panel text via fake callback path: send message with same keyboard
    await state.clear()
    total_users = await session.scalar(select(func.count(User.id))) or 0
    pending_loans = (
        await session.scalar(select(func.count(Loan.id)).where(Loan.status == LoanStatus.PENDING))
        or 0
    )
    text = (
        f"👑 <b>Admin Panel</b>\n\nUsers: {total_users} | Pending: {pending_loans}\n"
        f"ID: <code>{message.from_user.id}</code>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Open full panel", callback_data="admin:panel"))
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
