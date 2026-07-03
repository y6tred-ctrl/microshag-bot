import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from database import init_db
from handlers import router
from scheduler import send_reminder, morning_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def morning_job(bot: Bot):
    import aiosqlite
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT tg_id FROM users WHERE is_paused = 0"
        )
        users = await cursor.fetchall()

    for user in users:
        try:
            await morning_prompt(bot, user["tg_id"])
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Morning prompt error for {user['tg_id']}: {e}")


async def reminder_job(bot: Bot):
    import aiosqlite
    async with aiosqlite.connect(settings.database_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT tg_id FROM users WHERE is_paused = 0"
        )
        users = await cursor.fetchall()

    for user in users:
        try:
            await send_reminder(bot, user["tg_id"])
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Reminder error for {user['tg_id']}: {e}")


async def on_startup(bot: Bot):
    os.makedirs("data", exist_ok=True)
    await init_db()
    logger.info("Database initialized")

    scheduler = AsyncIOScheduler()

    scheduler.add_job(morning_job, trigger="cron", hour=10, minute=0, kwargs={"bot": bot})
    scheduler.add_job(reminder_job, trigger="cron", hour=15, minute=0, kwargs={"bot": bot})
    scheduler.add_job(reminder_job, trigger="cron", hour=19, minute=0, kwargs={"bot": bot})

    scheduler.start()
    logger.info("Scheduler started")


async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()

    dp.include_router(router)
    dp.startup.register(on_startup)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
