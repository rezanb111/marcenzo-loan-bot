"""
Inline keyboards with colored buttons (style) + premium custom emoji icons.
Requires Bot API 9.4+ and aiogram 3.20+.
Owner of the bot needs Telegram Premium for custom emoji to render.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from locales import SUPPORTED_LANGUAGES, t

# Example premium emoji IDs (replace with real ones from @get_emoji_id_robot or similar)
# These are placeholders – replace with actual custom_emoji_id from your premium stickers
EMOJI = {
    "money": "5471952986970267163",      # 💰 style
    "check": "5870633910337015697",      # ✅
    "cross": "5870657884844462243",      # ❌
    "back": "5870982283724328568",       # 🔙 / settings style
    "profile": "5453969572354878595",    # ⭐
    "support": "6039422865189638057",    # 📣
    "admin": "5368324170671202286",      # 🔥
}


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, title in SUPPORTED_LANGUAGES.items():
        builder.button(text=title, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "en", is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text=t("request_loan", lang),
            callback_data="loan:request",
            style="success",
            icon_custom_emoji_id=EMOJI["money"],
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("my_loans", lang),
            callback_data="loan:list",
            style="primary",
        ),
        InlineKeyboardButton(
            text=t("profile", lang),
            callback_data="profile",
            icon_custom_emoji_id=EMOJI["profile"],
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=t("support", lang),
            callback_data="support",
            icon_custom_emoji_id=EMOJI["support"],
        )
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text=t("admin_panel", lang),
                callback_data="admin:panel",
                style="danger",
                icon_custom_emoji_id=EMOJI["admin"],
            )
        )
    return builder.as_markup()


def amount_keyboard(limit: float, lang: str = "en") -> InlineKeyboardMarkup:
    """Quick amount buttons based on current credit limit."""
    builder = InlineKeyboardBuilder()
    amounts = []
    if limit >= 5:
        amounts.append(5)
    if limit >= 10:
        amounts.append(10)
    if limit >= 20:
        amounts.append(20)
    if limit >= 50:
        amounts.append(50)
    if limit >= 100:
        amounts.append(100)

    for a in amounts:
        if a <= limit:
            builder.button(
                text=f"{a} USDT",
                callback_data=f"loan:amount:{a}",
                style="primary",
            )
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text=t("back", lang),
            callback_data="menu:main",
            style="danger",
            icon_custom_emoji_id=EMOJI["cross"],
        )
    )
    return builder.as_markup()


def installments_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in (3, 5, 7, 10):
        builder.button(
            text=f"{n}",
            callback_data=f"loan:installments:{n}",
            style="primary",
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(
            text=t("back", lang),
            callback_data="loan:request",
            style="danger",
        )
    )
    return builder.as_markup()


def confirm_loan_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("confirm_loan", lang)[:20] if False else "✅ Confirm",
                    callback_data="loan:confirm",
                    style="success",
                    icon_custom_emoji_id=EMOJI["check"],
                ),
                InlineKeyboardButton(
                    text=t("cancel", lang),
                    callback_data="menu:main",
                    style="danger",
                    icon_custom_emoji_id=EMOJI["cross"],
                ),
            ]
        ]
    )


def back_keyboard(lang: str = "en", callback: str = "menu:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("back", lang),
                    callback_data=callback,
                    style="danger",
                    icon_custom_emoji_id=EMOJI["back"],
                )
            ]
        ]
    )
