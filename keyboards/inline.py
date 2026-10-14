"""Inline keyboards — plain text + emoji (compatible with all aiogram versions)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from locales import t

LANG_NAMES = {
    "en": "🇬🇧 English",
    "fa": "🇮🇷 فارسی",
    "ru": "🇷🇺 Русский",
    "ar": "🇸🇦 العربية",
    "tr": "🇹🇷 Türkçe",
    "es": "🇪🇸 Español",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "zh": "🇨🇳 中文",
    "hi": "🇮🇳 हिन्दी",
}


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, name in LANG_NAMES.items():
        builder.button(text=name, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "en", is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚀 " + t("request_loan", lang), callback_data="loan:request")
    )
    builder.row(
        InlineKeyboardButton(text="⚡ " + t("my_loans", lang), callback_data="loan:list"),
        InlineKeyboardButton(text="⭐ " + t("profile", lang), callback_data="profile"),
    )
    builder.row(
        InlineKeyboardButton(text="❤️ " + t("support", lang), callback_data="support")
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="⚙️ " + t("admin_panel", lang), callback_data="admin:panel")
        )
    return builder.as_markup()


def amount_keyboard(limit: float, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    candidates = [0.1, 0.5, 1, 2, 3, 5, 10, 20, 50, 100]
    for a in candidates:
        if a <= limit + 1e-9:
            builder.button(text=f"{a:g} USDT", callback_data=f"loan:amount:{a}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="🔙 " + t("back", lang), callback_data="menu:main"))
    return builder.as_markup()


def installments_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in (3, 5, 7, 10):
        builder.button(text=f"{n}", callback_data=f"loan:installments:{n}")
    builder.adjust(4)
    builder.row(InlineKeyboardButton(text="🔙 " + t("back", lang), callback_data="loan:request"))
    return builder.as_markup()


def confirm_loan_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Confirm", callback_data="loan:confirm"),
                InlineKeyboardButton(text="❌ " + t("cancel", lang), callback_data="menu:main"),
            ]
        ]
    )


def back_keyboard(lang: str = "en", callback: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 " + t("back", lang), callback_data=callback)]
        ]
    )
