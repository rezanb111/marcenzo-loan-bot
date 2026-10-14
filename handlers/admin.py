from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database.models import Loan, LoanStatus, User
from keyboards.inline import back_keyboard
from locales import t
from services.loan_service import get_or_create_user

router = Router(name="admin")
settings = get_settings()


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        username = (event.from_user.username or "").lower()
        return username in settings.admin_list


@router.callback_query(F.data == "admin:panel", IsAdmin())
async def admin_panel(callback: CallbackQuery, session: AsyncSession):
    total_users = await session.scalar(select(func.count(User.id))) or 0
    total_loans = await session.scalar(select(func.count(Loan.id))) or 0
    active_loans = await session.scalar(
        select(func.count(Loan.id)).where(Loan.status == LoanStatus.ACTIVE)
    ) or 0
    total_volume = await session.scalar(select(func.sum(Loan.amount))) or Decimal("0")

    text = (
        "👑 <b>Admin Panel — Marcenzo Loan Bot</b>\n\n"
        f"👥 Users: <b>{total_users}</b>\n"
        f"📋 Total loans: <b>{total_loans}</b>\n"
        f"🟢 Active loans: <b>{active_loans}</b>\n"
        f"💰 Total volume: <b>{total_volume} USDT</b>\n"
    )

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Users", callback_data="admin:users:0", style="primary"),
        InlineKeyboardButton(text="📋 Active Loans", callback_data="admin:loans:0", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Block User", callback_data="admin:block", style="danger"),
        InlineKeyboardButton(text="✅ Unblock", callback_data="admin:unblock", style="success"),
    )
    builder.row(
        InlineKeyboardButton(text="📈 Set Credit Limit", callback_data="admin:setlimit", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main", style="danger"),
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:users:"), IsAdmin())
async def admin_users(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[2])
    limit = 10
    offset = page * limit

    result = await session.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()

    if not users:
        await callback.answer("No more users", show_alert=True)
        return

    lines = []
    for u in users:
        status = "🚫" if u.is_blocked else "✅"
        lines.append(
            f"{status} <code>{u.telegram_id}</code> @{u.username or '-'} "
            f"| limit {u.credit_limit} | ok {u.successful_loans}"
        )

    text = f"👥 <b>Users</b> (page {page + 1})\n\n" + "\n".join(lines)

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Prev", callback_data=f"admin:users:{page - 1}")
    builder.button(text="Next ➡️", callback_data=f"admin:users:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel", style="danger"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin:loans:"), IsAdmin())
async def admin_loans(callback: CallbackQuery, session: AsyncSession):
    page = int(callback.data.split(":")[2])
    limit = 8
    offset = page * limit

    result = await session.execute(
        select(Loan)
        .where(Loan.status == LoanStatus.ACTIVE)
        .order_by(Loan.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    loans = result.scalars().all()

    if not loans:
        await callback.answer("No active loans", show_alert=True)
        return

    lines = []
    for loan in loans:
        lines.append(
            f"#{loan.id} user={loan.user_id} | {loan.amount} {loan.currency} | "
            f"{loan.installments_count} inst"
        )

    text = f"📋 <b>Active Loans</b> (page {page + 1})\n\n" + "\n".join(lines)

    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(text="⬅️ Prev", callback_data=f"admin:loans:{page - 1}")
    builder.button(text="Next ➡️", callback_data=f"admin:loans:{page + 1}")
    builder.row(InlineKeyboardButton(text="🔙 Back", callback_data="admin:panel", style="danger"))

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.message(F.text.startswith("/block"), IsAdmin())
async def cmd_block(message: Message, session: AsyncSession):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /block <telegram_id> [reason]")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("Invalid telegram_id")
        return
    reason = parts[2] if len(parts) > 2 else "Blocked by admin"

    user = await get_or_create_user(session, tg_id)
    user.is_blocked = True
    user.block_reason = reason
    await session.commit()
    await message.answer(f"✅ User {tg_id} blocked.\nReason: {reason}")


@router.message(F.text.startswith("/unblock"), IsAdmin())
async def cmd_unblock(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /unblock <telegram_id>")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("Invalid telegram_id")
        return

    user = await get_or_create_user(session, tg_id)
    user.is_blocked = False
    user.block_reason = None
    await session.commit()
    await message.answer(f"✅ User {tg_id} unblocked.")


@router.message(F.text.startswith("/setlimit"), IsAdmin())
async def cmd_setlimit(message: Message, session: AsyncSession):
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /setlimit <telegram_id> <amount>")
        return
    try:
        tg_id = int(parts[1])
        amount = Decimal(parts[2])
    except Exception:
        await message.answer("Invalid arguments")
        return

    user = await get_or_create_user(session, tg_id)
    user.credit_limit = amount
    await session.commit()
    await message.answer(f"✅ Credit limit of {tg_id} set to {amount} USDT")
