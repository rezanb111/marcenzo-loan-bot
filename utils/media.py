"""Send section banners if media files exist, else plain text."""

from pathlib import Path
from typing import Optional

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message
from aiogram.types import CallbackQuery

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

# Map logical section -> filename (put PNG/JPG in media/)
BANNERS = {
    "welcome": "welcome.jpg",
    "main": "main_menu.jpg",
    "loan": "loan.jpg",
    "profile": "profile.jpg",
    "support": "support.jpg",
    "admin": "admin.jpg",
    "success": "success.jpg",
}


def banner_path(key: str) -> Optional[Path]:
    name = BANNERS.get(key)
    if not name:
        return None
    p = MEDIA_DIR / name
    return p if p.is_file() else None


async def send_section(
    target: Message | CallbackQuery,
    text: str,
    *,
    section: str = "main",
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
    edit: bool = True,
) -> None:
    """Prefer photo+caption; fall back to text."""
    path = banner_path(section)
    msg = target.message if isinstance(target, CallbackQuery) else target

    if path and isinstance(target, Message):
        await msg.answer_photo(
            FSInputFile(path),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return

    if path and isinstance(target, CallbackQuery) and edit:
        try:
            await msg.delete()
        except Exception:
            pass
        await msg.answer_photo(
            FSInputFile(path),
            caption=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return

    if isinstance(target, CallbackQuery) and edit:
        try:
            await msg.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return

    await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
