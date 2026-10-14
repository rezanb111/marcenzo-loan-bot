"""
Inline keyboards with colored buttons (style) + premium custom emoji.
Requires Bot API 9.4+ / aiogram with style + icon_custom_emoji_id support.
Bot owner needs Telegram Premium for custom emoji to render for users.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from locales import t

# Premium emoji IDs from owner
EMOJI = {
    "rocket": "6147654280112248427",  # 🚀
    "green": "6084384451154941172",  # 🟢
    "red": "6082387218347857432",  # 🔴
    "check": "5328210112429438491",  # ✅
    "cross": "5330561452405176521",  # ❎
    "check3": "6113832658196762761",  # ✅
    "star": "4990453424710485047",  # ⭐️
    "down": "4990226723451699964",  # ⬇️
    "heart": "4987775237723522533",  # ❤️
    "lightning": "4990074969372230665",  # ⚡️
    "settings": "5929098607192969118",  # ⚙
    "hourglass": "4990168118622946000",  # ⏳
}

FLAG = {
    "en": "5913463998522592692",  # 🇺🇸
    "fa": "5866040533008261990",  # 🇮🇷
    "ru": "5913274246867456342",  # 🇷🇺
    "ar": "5911387497799094470",
    "tr": "5910995113881901195",  # 🇹🇷
    "de": "5911096835887337583",  # 🇩🇪
    "fr": "5913605586414473124",  # 🇫🇷
    "zh": "5913371673905598425",
    "gb": "5913443365499703513",  # 🇬🇧
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


def _btn(text: str, callback_data: str | None = None, **extra) -> InlineKeyboardButton:
    """Build button; drop unsupported kwargs if aiogram is older."""
    kwargs = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    kwargs.update(extra)
    try:
        return InlineKeyboardButton(**kwargs)
    except TypeError:
        # Older aiogram: strip style / icon_custom_emoji_id
        kwargs.pop("style", None)
        kwargs.pop("icon_custom_emoji_id", None)
        return InlineKeyboardButton(**kwargs)


def language_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    order = ["en", "fa", "ru", "tr", "de", "fr", "ar", "es", "zh", "hi"]
    for code in order:
        name = LANG_NAMES.get(code, code)
        extra = {}
        if FLAG.get(code):
            extra["icon_custom_emoji_id"] = FLAG[code]
        try:
            builder.button(text=name, callback_data=f"lang:{code}", **extra)
        except TypeError:
            builder.button(text=name, callback_data=f"lang:{code}")
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(lang: str = "en", is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn(
                t("request_loan", lang),
                "loan:request",
                style="success",
                icon_custom_emoji_id=EMOJI["rocket"],
            )
        ],
        [
            _btn(
                t("my_loans", lang),
                "loan:list",
                style="primary",
                icon_custom_emoji_id=EMOJI["lightning"],
            ),
            _btn(
                t("profile", lang),
                "profile",
                icon_custom_emoji_id=EMOJI["star"],
            ),
        ],
        [
            _btn(
                t("support", lang),
                "support",
                icon_custom_emoji_id=EMOJI["heart"],
            )
        ],
    ]
    if is_admin:
        rows.append(
            [
                _btn(
                    t("admin_panel", lang),
                    "admin:panel",
                    style="danger",
                    icon_custom_emoji_id=EMOJI["settings"],
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def amount_keyboard(limit: float, lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    candidates = [0.1, 0.5, 1, 2, 3, 5, 10, 20, 50, 100]
    for a in candidates:
        if a <= limit + 1e-9:
            try:
                builder.button(
                    text=f"{a:g} USDT",
                    callback_data=f"loan:amount:{a}",
                    style="primary",
                    icon_custom_emoji_id=EMOJI["green"],
                )
            except TypeError:
                builder.button(text=f"{a:g} USDT", callback_data=f"loan:amount:{a}")
    builder.adjust(2)
    builder.row(
        _btn(
            t("back", lang),
            "menu:main",
            style="danger",
            icon_custom_emoji_id=EMOJI["cross"],
        )
    )
    return builder.as_markup()


def installments_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for n in (3, 5, 7, 10):
        try:
            builder.button(
                text=str(n),
                callback_data=f"loan:installments:{n}",
                style="primary",
                icon_custom_emoji_id=EMOJI["check"],
            )
        except TypeError:
            builder.button(text=str(n), callback_data=f"loan:installments:{n}")
    builder.adjust(4)
    builder.row(
        _btn(
            t("back", lang),
            "loan:request",
            style="danger",
            icon_custom_emoji_id=EMOJI["cross"],
        )
    )
    return builder.as_markup()


def confirm_loan_keyboard(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(
                    "Confirm",
                    "loan:confirm",
                    style="success",
                    icon_custom_emoji_id=EMOJI["check3"],
                ),
                _btn(
                    t("cancel", lang),
                    "menu:main",
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
                _btn(
                    t("back", lang),
                    callback,
                    style="danger",
                    icon_custom_emoji_id=EMOJI["down"],
                )
            ]
        ]
    )
