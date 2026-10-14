"""Colored buttons + premium custom emoji."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from locales import t

EMOJI = {
    "rocket": "6147654280112248427",
    "green": "6084384451154941172",
    "red": "6082387218347857432",
    "check": "5328210112429438491",
    "cross": "5330561452405176521",
    "check3": "6113832658196762761",
    "star": "4990453424710485047",
    "down": "4990226723451699964",
    "heart": "4987775237723522533",
    "lightning": "4990074969372230665",
    "settings": "5929098607192969118",
}

FLAG_EMOJI = {
    "en": "5913463998522592692",
    "fa": "5866040533008261990",
    "ru": "5913274246867456342",
    "ar": "5911387497799094470",
    "tr": "5910995113881901195",
    "de": "5911096835887337583",
    "fr": "5913605586414473124",
    "zh": "5913371673905598425",
}

LANG_NAMES = {
    "en": "English",
    "fa": "فارسی",
    "ru": "Русский",
    "ar": "العربية",
    "tr": "Türkçe",
    "es": "Español",
    "de": "Deutsch",
    "fr": "Français",
    "zh": "中文",
    "hi": "हिन्दी",
}


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code in ["en", "fa", "ru", "tr", "de", "fr", "ar", "es", "zh", "hi"]:
        kwargs = {"text": LANG_NAMES.get(code, code), "callback_data": f"lang:{code}"}
        if FLAG_EMOJI.get(code):
            kwargs["icon_custom_emoji_id"] = FLAG_EMOJI[code]
        builder.button(**kwargs)
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "en", is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=t("request_loan", lang),
            callback_data="loan:request",
            style="success",
            icon_custom_emoji_id=EMOJI["rocket"],
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=t("my_loans", lang),
            callback_data="loan:list",
            style="primary",
            icon_custom_emoji_id=EMOJI["lightning"],
        ),
        InlineKeyboardButton(
            text=t("profile", lang),
            callback_data="profile",
            icon_custom_emoji_id=EMOJI["star"],
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text=t("support", lang),
            callback_data="support",
            icon_custom_emoji_id=EMOJI["heart"],
        )
    )
    if is_admin:
        builder.row(
            InlineKeyboardButton(
                text=t("admin_panel", lang),
                callback_data="admin:panel",
                style="danger",
                icon_custom_emoji_id=EMOJI["settings"],
            )
        )
    return builder.as_markup()


def amount_keyboard(limit: float, lang: str = "en") -> InlineKeyboardMarkup:
    """Quick picks from 0.10 up to limit."""
    builder = InlineKeyboardBuilder()
    candidates = [0.1, 0.5, 1, 2, 3, 5, 10, 20, 50, 100]
    shown = [a for a in candidates if a <= limit + 1e-9]
    for a in shown:
        label = f"{a:g} USDT"
        builder.button(
            text=label,
            callback_data=f"loan:amount:{a}",
            style="primary",
            icon_custom_emoji_id=EMOJI["green"],
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
            icon_custom_emoji_id=EMOJI["check"],
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(
            text=t("back", lang),
            callback_data="loan:request",
            style="danger",
            icon_custom_emoji_id=EMOJI["cross"],
        )
    )
    return builder.as_markup()


def confirm_loan_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Confirm",
                    callback_data="loan:confirm",
                    style="success",
                    icon_custom_emoji_id=EMOJI["check3"],
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
                    icon_custom_emoji_id=EMOJI["down"],
                )
            ]
        ]
    )
