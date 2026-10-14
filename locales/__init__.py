from __future__ import annotations

from typing import Any

# Supported languages (common ones)
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

# Simple in-code translations (can be moved to JSON later)
TEXTS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Welcome to <b>Marcenzo Loan Bot</b>!\n\nChoose your language:",
        "language_set": "Language set to English ✅",
        "main_menu": "🏠 <b>Main Menu</b>\n\nYour credit limit: <b>{limit} USDT</b>\nSuccessful loans: <b>{success}</b>",
        "request_loan": "Request Loan",
        "my_loans": "My Loans",
        "profile": "Profile",
        "support": "Support",
        "admin_panel": "Admin Panel",
        "choose_amount": "How much do you want to borrow?\n\nYour available limit: <b>{limit} USDT</b>",
        "choose_installments": "Choose number of installments:",
        "confirm_loan": "Confirm loan of <b>{amount} USDT</b> in <b>{count}</b> installments of <b>{each} USDT</b>?",
        "loan_issued": "✅ Loan of <b>{amount} USDT</b> has been sent to your xRocket wallet!",
        "no_active_loans": "You have no active loans.",
        "pay_installment": "Pay Installment",
        "back": "Back",
        "cancel": "Cancel",
        "blocked": "🚫 Your account is blocked.\nReason: {reason}",
        "limit_reached": "You have reached your current credit limit.",
    },
    "fa": {
        "welcome": "به ربات وام <b>Marcenzo</b> خوش آمدید!\n\nزبان خود را انتخاب کنید:",
        "language_set": "زبان به فارسی تنظیم شد ✅",
        "main_menu": "🏠 <b>منوی اصلی</b>\n\nسقف اعتبار شما: <b>{limit} USDT</b>\nوام‌های موفق: <b>{success}</b>",
        "request_loan": "درخواست وام",
        "my_loans": "وام‌های من",
        "profile": "پروفایل",
        "support": "پشتیبانی",
        "admin_panel": "پنل ادمین",
        "choose_amount": "چقدر می‌خوای وام بگیری؟\n\nسقف موجود شما: <b>{limit} USDT</b>",
        "choose_installments": "تعداد اقساط را انتخاب کنید:",
        "confirm_loan": "تأیید وام <b>{amount} USDT</b> در <b>{count}</b> قسط <b>{each} USDT</b>؟",
        "loan_issued": "✅ مبلغ <b>{amount} USDT</b> به کیف پول xRocket شما واریز شد!",
        "no_active_loans": "شما وام فعالی ندارید.",
        "pay_installment": "پرداخت قسط",
        "back": "بازگشت",
        "cancel": "لغو",
        "blocked": "🚫 حساب شما مسدود شده است.\nدلیل: {reason}",
        "limit_reached": "به سقف اعتبار فعلی خود رسیده‌اید.",
    },
    "ru": {
        "welcome": "Добро пожаловать в <b>Marcenzo Loan Bot</b>!\n\nВыберите язык:",
        "language_set": "Язык установлен на русский ✅",
        "main_menu": "🏠 <b>Главное меню</b>\n\nВаш кредитный лимит: <b>{limit} USDT</b>\nУспешных займов: <b>{success}</b>",
        "request_loan": "Запросить займ",
        "my_loans": "Мои займы",
        "profile": "Профиль",
        "support": "Поддержка",
        "admin_panel": "Админ-панель",
        "choose_amount": "Сколько хотите взять?\n\nДоступный лимит: <b>{limit} USDT</b>",
        "choose_installments": "Выберите количество платежей:",
        "confirm_loan": "Подтвердить займ <b>{amount} USDT</b> на <b>{count}</b> платежей по <b>{each} USDT</b>?",
        "loan_issued": "✅ Займ <b>{amount} USDT</b> отправлен на ваш xRocket кошелёк!",
        "no_active_loans": "У вас нет активных займов.",
        "pay_installment": "Оплатить платёж",
        "back": "Назад",
        "cancel": "Отмена",
        "blocked": "🚫 Ваш аккаунт заблокирован.\nПричина: {reason}",
        "limit_reached": "Вы достигли текущего кредитного лимита.",
    },
}

# Fallback to English for missing languages
for lang in SUPPORTED_LANGUAGES:
    if lang not in TEXTS:
        TEXTS[lang] = TEXTS["en"].copy()


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Translate key for given language with optional formatting."""
    text = TEXTS.get(lang, TEXTS["en"]).get(key) or TEXTS["en"].get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
