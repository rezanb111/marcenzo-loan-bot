"""
Inline keyboards with colored buttons (style) + premium custom emoji icons.
Requires Bot API 9.4+ and aiogram 3.20+.
Owner of the bot needs Telegram Premium for custom emoji to render.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from locales import t

# Real Premium Emoji IDs provided by owner
EMOJI = {
    "rocket": "6147654280112248427",      # 🚀
    "green": "6084384451154941172",       # 🟢
    "red": "6082387218347857432",         # 🔴
    "angry": "5318947044793006041",       # 😡
    "shrug": "5472131451451349048",       # 🤷‍♂
    "moon": "5328128662669637866",        # 🌙
    "check": "5328210112429438491",       # ✅
    "cross": "5330561452405176521",       # ❎
    "check2": "4990224133586420590",      # ✅
    "check3": "6113832658196762761",      # ✅
    "check4": "6291694847426303062",      # ✅
    "star": "4990453424710485047",        # ⭐️
    "star2": "4990036306076632013",       # ⭐️
    "down": "4990226723451699964",        # ⬇️
    "heart": "4987775237723522533",       # ❤️
    "lightning": "4990074969372230665",   # ⚡️
    "hourglass": "4990168118622946000",   # ⏳
    "settings": "5929098607192969118",    # ⚙
    "link": "6113813004426416777",        # 🔗
    "shop": "6077678113125306912",        # 🛍
    "pc": "5929314699882532260",          # 🖥
    "phone": "5958293913675501329",       # 📱
}

# Flag premium emoji IDs for language selection
FLAG_EMOJI = {
    "en": "5913463998522592692",   # 🇺🇸
    "fa": "5866040533008261990",   # 🇮🇷
    "ru": "5913274246867456342",   # 🇷🇺
    "ar": "5911387497799094470",   # 🇸🇩 (closest available) / can use other
    "tr": "5910995113881901195",   # 🇹🇷
    "es": None,                    # no Spain flag in list
    "de": "5911096835887337583",   # 🇩🇪
    "fr": "5913605586414473124",   # 🇫🇷
    "zh": "5913371673905598425",   # 🇰🇷 used as placeholder if no CN
    "hi": None,
    "gb": "5913443365499703513",   # 🇬🇧
    "it": "5913688444923547525",   # 🇮🇹
    "br": "5911148568768418614",   # 🇧🇷
    "ca": "5913623736946265914",   # 🇨🇦
    "kr": "5913371673905598425",   # 🇰🇷
}

# Language display names (text only — flag goes via icon_custom_emoji_id)
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
    """Language selection with premium flag emojis."""
    builder = InlineKeyboardBuilder()

    # Primary languages with real flags first
    order = ["en", "fa", "ru", "tr", "de", "fr", "ar", "es", "zh", "hi"]

    for code in order:
        name = LANG_NAMES.get(code, code)
        flag_id = FLAG_EMOJI.get(code)
        kwargs = {
            "text": name,
            "callback_data": f"lang:{code}",
        }
        if flag_id:
            kwargs["icon_custom_emoji_id"] = flag_id
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
