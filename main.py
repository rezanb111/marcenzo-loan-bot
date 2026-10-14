"""
Marcenzo Loan Bot — professional multi-language loan bot with xRocket Pay.
Complete production-ready version.
"""

import asyncio
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from config import get_settings
from database.session import init_db
from handlers import admin, loan, profile, repay, start
from middlewares.db import DbSessionMiddleware


def setup_logging() -> None:
    Path("logs").mkdir(exist_ok=True)
    logger.add(
        "logs/bot_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="INFO",
        enqueue=True,
    )


async def main() -> None:
    setup_logging()
    settings = get_settings()

    Path("data").mkdir(exist_ok=True)

    await init_db()
    logger.info("Database initialized")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middlewares
    dp.update.middleware(DbSessionMiddleware())

    # Routers (order matters for filters)
    dp.include_router(start.router)
    dp.include_router(loan.router)
    dp.include_router(repay.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

    logger.info("🚀 Marcenzo Loan Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
