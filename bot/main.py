"""
Main entry point for the 10,000 Telegram bot.
"""
import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import settings
from bot.db.database import init_db
from bot.services.scheduler import scheduler
from bot.handlers import commands, onboarding, assessment, daily_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=settings.telegram_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp = Dispatcher(storage=MemoryStorage())

dp.include_router(commands.router)
dp.include_router(onboarding.router)
dp.include_router(assessment.router)
dp.include_router(daily_loop.router)


async def main():
    logger.info("Initializing database...")
    await init_db()

    logger.info("Starting scheduler...")
    scheduler.start()

    logger.info("Restoring daily jobs for active users...")
    from bot.services.scheduler import restore_all_jobs
    await restore_all_jobs(bot)

    logger.info("Starting bot polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
