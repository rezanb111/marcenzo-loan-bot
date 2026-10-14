from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = {
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

TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome to <b>Marcenzo Loan Bot</b>!\n\nChoose your language:",
        "language_set": "Language set to English ✅",
        "main_menu": (
            "🏠 <b>Main Menu</b>\n\n"
            "🏅 Level: <b>{level}</b> ({level_name})\n"
            "💳 Credit limit: <b>{limit} USDT</b>\n"
            "✅ Successful loans: <b>{success}</b>\n"
            "📊 Next level in: <b>{to_next}</b> successful repayments\n\n"
            "💡 Guide · 1% interest · Admin approval · Optional password"
        ),
        "request_loan": "Request Loan",
        "my_loans": "My Loans",
        "profile": "Profile",
        "support": "Support",
        "invest": "Invest",
        "guide": "Guide",
        "website": "Website",
        "admin_panel": "Admin Panel",
        "terms_accept": "I Agree",
        "terms_decline": "Decline",
        "choose_amount": "How much do you want to borrow?\n\nYour available limit: <b>{limit} USDT</b>",
        "choose_installments": "Choose number of installments:",
        "confirm_loan": (
            "Confirm loan of <b>{amount} USDT</b>\n"
            "Interest 1%: <b>{interest} USDT</b>\n"
            "Total repay: <b>{total} USDT</b>\n"
            "in <b>{count}</b> installments of <b>{each} USDT</b>?"
        ),
        "loan_issued": "✅ Loan of <b>{amount} USDT</b> has been sent to your xRocket wallet!",
        "no_active_loans": "You have no active loans.",
        "pay_installment": "Pay Installment",
        "back": "Back",
        "cancel": "Cancel",
        "blocked": "🚫 Your account is blocked.\nReason: {reason}",
        "limit_reached": "You have reached your current credit limit.",
        "loan_guide": (
            "🚀 <b>Request a loan</b>\n\n"
            "• Min amount: from 0.10 USDT\n"
            "• You repay principal + <b>1% interest</b>\n"
            "• Interest goes to the investment fund\n"
            "• Admin must approve before payout\n"
            "• Every <b>3</b> successful loans → level up + credit boost\n\n"
            "Your limit: <b>{limit} USDT</b> · Min: <b>{min_a} USDT</b>\n"
            "Type an amount or use quick buttons:"
        ),
    },
    "fa": {
        "welcome": "به ربات وام <b>Marcenzo</b> خوش آمدید!\n\nزبان خود را انتخاب کنید:",
        "language_set": "زبان به فارسی تنظیم شد ✅",
        "main_menu": (
            "🏠 <b>منوی اصلی</b>\n\n"
            "🏅 لول: <b>{level}</b> ({level_name})\n"
            "💳 سقف اعتبار: <b>{limit} USDT</b>\n"
            "✅ وام موفق: <b>{success}</b>\n"
            "📊 تا لول بعدی: <b>{to_next}</b> تسویه موفق\n\n"
            "💡 راهنما · سود ۱٪ · تأیید ادمین · رمز اختیاری"
        ),
        "request_loan": "درخواست وام",
        "my_loans": "وام‌های من",
        "profile": "پروفایل",
        "support": "پشتیبانی",
        "invest": "سرمایه‌گذاری",
        "guide": "راهنما",
        "website": "وبسایت",
        "admin_panel": "پنل ادمین",
        "terms_accept": "موافقم",
        "terms_decline": "رد می‌کنم",
        "choose_amount": "چقدر وام می‌خوای؟\n\nسقف: <b>{limit} USDT</b>",
        "choose_installments": "تعداد اقساط:",
        "confirm_loan": (
            "تأیید وام <b>{amount} USDT</b>\n"
            "سود ۱٪: <b>{interest} USDT</b>\n"
            "کل بازپرداخت: <b>{total} USDT</b>\n"
            "در <b>{count}</b> قسط <b>{each} USDT</b>؟"
        ),
        "loan_issued": "✅ مبلغ <b>{amount} USDT</b> واریز شد!",
        "no_active_loans": "وام فعالی ندارید.",
        "pay_installment": "پرداخت قسط",
        "back": "بازگشت",
        "cancel": "لغو",
        "blocked": "🚫 مسدود.\nدلیل: {reason}",
        "limit_reached": "به سقف رسیده‌اید.",
        "loan_guide": (
            "🚀 <b>درخواست وام</b>\n\n"
            "• از ۰.۱۰ تا سقف اعتبار\n"
            "• اصل + <b>۱٪ سود</b>\n"
            "• هر <b>۳</b> تسویه موفق → لول بالاتر\n"
            "• تأیید ادمین قبل از پرداخت\n\n"
            "سقف شما: <b>{limit} USDT</b>"
        ),
    },
}

for lang in SUPPORTED_LANGUAGES:
    if lang not in TEXTS:
        TEXTS[lang] = TEXTS["en"].copy()


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def menu_kwargs(user) -> dict:
    success = int(getattr(user, "successful_loans", 0) or 0)
    level = int(getattr(user, "level", 1) or 1)
    n = 3
    to_next = n - (success % n) if success % n != 0 else n
    name = getattr(user, "level_name", None) or f"Level {level}"
    return {
        "limit": user.credit_limit,
        "success": success,
        "level": level,
        "level_name": name,
        "to_next": to_next,
    }
