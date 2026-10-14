"""Section banners: local media/ files or public HTTPS URLs."""

from pathlib import Path
from typing import Optional

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message, URLInputFile

MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"

# Local filenames (optional override)
BANNERS = {
    "welcome": "welcome.jpg",
    "main": "main_menu.jpg",
    "loan": "loan.jpg",
    "profile": "profile.jpg",
    "support": "support.jpg",
    "admin": "admin.jpg",
    "success": "success.jpg",
    "invest": "invest.jpg",
    "guide": "guide.jpg",
}

# Ready public images (Unsplash / picsum-style stable CDN)
BANNER_URLS = {
    "welcome": "https://images.unsplash.com/photo-1639763483222-ebb83d7c8e5d?w=1200&q=80",
    "main": "https://images.unsplash.com/photo-1642790106117-e829e14a795f?w=1200&q=80",
    "loan": "https://images.unsplash.com/photo-1621761191319-c6fb62004040?w=1200&q=80",
    "profile": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    "support": "https://images.unsplash.com/photo-1556745757-8d76bdb6984b?w=1200&q=80",
    "admin": "https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=1200&q=80",
    "success": "https://images.unsplash.com/photo-1618044733300-9472054094ee?w=1200&q=80",
    "invest": "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=1200&q=80",
    "guide": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1200&q=80",
}


def banner_path(key: str) -> Optional[Path]:
    name = BANNERS.get(key)
    if not name:
        return None
    p = MEDIA_DIR / name
    return p if p.is_file() else None


def banner_url(key: str) -> Optional[str]:
    return BANNER_URLS.get(key)


async def send_section(
    target: Message | CallbackQuery,
    text: str,
    *,
    section: str = "main",
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str = "HTML",
    edit: bool = True,
) -> None:
    path = banner_path(section)
    url = banner_url(section)
    msg = target.message if isinstance(target, CallbackQuery) else target

    photo = None
    if path:
        photo = FSInputFile(path)
    elif url:
        photo = URLInputFile(url)

    if photo is not None:
        if isinstance(target, CallbackQuery) and edit:
            try:
                await msg.delete()
            except Exception:
                pass
        await msg.answer_photo(
            photo,
            caption=text[:1024],
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
