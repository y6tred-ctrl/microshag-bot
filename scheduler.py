from datetime import datetime

from aiogram import Bot

from database import get_today_steps, get_user
from texts import REMINDER_MESSAGE


async def send_reminder(bot: Bot, tg_id: int):
    user = await get_user(tg_id)
    if not user or user["is_paused"]:
        return

    today = datetime.now().date().isoformat()
    today_steps = await get_today_steps(tg_id, today)

    if not today_steps:
        return

    done_count = sum(1 for s in today_steps if s["status"] == "done")
    if done_count < len(today_steps):
        await bot.send_message(
            tg_id,
            REMINDER_MESSAGE.format(name=user["name"]),
        )


async def morning_prompt(bot: Bot, tg_id: int):
    user = await get_user(tg_id)
    if not user or user["is_paused"]:
        return

    from texts import MORNING_PROMPT
    await bot.send_message(
        tg_id,
        MORNING_PROMPT.format(name=user["name"]),
    )
