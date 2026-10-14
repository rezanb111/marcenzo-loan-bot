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
            "Your credit limit: <b>{limit} USDT</b>\n"
            "Successful loans: <b>{success}</b>\n\n"
            "💡 Tip: open <b>Guide</b> for full help. Loans include <b>1% interest</b> for investors."
        ),
        "request_loan": "Request Loan",
        "my_loans": "My Loans",
        "profile": "Profile",
        "support": "Support",
        "invest": "Invest",
        "guide": "Guide",
        "admin_panel": "Admin Panel",
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
            "• Limit grows after 3 successful loans\n\n"
            "Your limit: <b>{limit} USDT</b> · Min: <b>{min_a} USDT</b>\n"
            "Type an amount or use quick buttons:"
        ),
    },
    "fa": {
        "welcome": "به ربات وام <b>Marcenzo</b> خوش آمدید!\n\nزبان خود را انتخاب کنید:",
        "language_set": "زبان به فارسی تنظیم شد ✅",
        "main_menu": (
            "🏠 <b>منوی اصلی</b>\n\n"
            "سقف اعتبار: <b>{limit} USDT</b>\n"
            "وام موفق: <b>{success}</b>\n\n"
            "💡 راهنما را بخوانید. روی هر وام <b>۱٪ سود</b> برای سرمایه‌گذاران است."
        ),
        "request_loan": "درخواست وام",
        "my_loans": "وام‌های من",
        "profile": "پروفایل",
        "support": "پشتیبانی",
        "invest": "سرمایه‌گذاری",
        "guide": "راهنما",
        "admin_panel": "پنل ادمین",
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
            "• بازپرداخت اصل + <b>۱٪ سود</b>\n"
            "• سود برای صندوق سرمایه‌گذاران\n"
            "• نیاز به تأیید ادمین\n\n"
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
