# 🚀 Marcenzo Loan Bot

Professional multi-language Telegram loan bot integrated with **xRocket Pay**.

## Features

- 🌍 **Multi-language** (EN / FA / RU / AR / TR / ES / DE / FR / ZH / HI) — language selection on first start
- 💳 **xRocket Pay** integration (payout for loan disbursement + invoices for repayments)
- 📈 **Progressive credit system**
  - First loan max **5 USDT**
  - After every **3 successful on-time loans** → limit **doubles**
  - Hard cap **100 USDT**
- 📅 Installment payments (3 / 5 / 7 / 10)
- 🎨 **Colored buttons** (primary / success / danger) + **Premium custom emoji** icons (Bot API 9.4+)
- 👑 Admin panel ready for `@marcenzo` and `@shibainuo`
- 🗄 Async SQLAlchemy + SQLite (easy switch to PostgreSQL)
- 🔒 Secrets only via `.env` (never committed)

## Quick Start

1. Clone the private repo
2. Copy `.env.example` → `.env` and fill:
   - `BOT_TOKEN`
   - `XROCKET_API_KEY`
   - `ADMINS=marcenzo,shibainuo`
3. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. Run:
   ```bash
   python main.py
   ```

## Project Structure

```
marcenzo-loan-bot/
├── config.py
├── main.py
├── database/
│   ├── models.py          # User, Loan, Installment
│   └── session.py
├── services/
│   ├── xrocket.py         # xRocket Pay client
│   └── loan_service.py    # Credit & loan logic
├── handlers/
│   ├── start.py
│   └── loan.py
├── keyboards/
│   └── inline.py          # Colored + premium emoji buttons
├── locales/
│   └── __init__.py        # i18n
├── middlewares/
│   └── db.py
└── requirements.txt
```

## Credit Rules (configurable in `.env`)

| Setting                        | Default |
|--------------------------------|---------|
| Initial credit limit           | 5 USDT  |
| Multiplier after 3 successes   | ×2      |
| Max limit                      | 100 USDT|
| Successful loans for upgrade   | 3       |

## Security Notes

- **Never** commit `.env`
- Rotate the bot token and xRocket key if they were ever exposed
- For production use PostgreSQL + Redis FSM storage + webhook mode

## Admins

- @marcenzo
- @shibainuo

---

Built with ❤️ for professional peer-to-peer lending inside Telegram.
