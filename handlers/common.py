from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import (
    get_user, create_user, update_user,
    get_pool_steps, get_today_steps, schedule_steps,
    complete_step, add_steps, create_goal, get_stats, reset_unscheduled,
)
from ai_service import generate_steps
from keyboards import KeyboardBuilder
from texts import *

router = Router()


class BotStates(StatesGroup):
    waiting_name = State()
    waiting_goal = State()
    reviewing_steps = State()
    waiting_custom_step = State()
    choosing_daily_count = State()
    waiting_reflection = State()


TODAY = lambda: datetime.now().date().isoformat()


# ─── Start / Onboarding ────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = await get_user(tg_id)

    if user and user["is_paused"]:
        await update_user(tg_id, is_paused=0, pause_until=None)
        await message.answer(PAUSE_OFF)
        return

    if user and user["name"]:
        await message.answer(
            f"С возвращением, {user['name']}! 👋\n"
            "/goal — добавить цель\n"
            "/today — планы на сегодня\n"
            "/stats — статистика"
        )
        return

    await message.answer(WELCOME)
    await state.set_state(BotStates.waiting_name)


@router.message(BotStates.waiting_name)
async def handle_name(message: Message, state: FSMContext):
    name = message.text.strip()
    tg_id = message.from_user.id
    await create_user(tg_id, name)
    await state.update_data(user_name=name)
    await message.answer(NAME_SAVED.format(name=name))
    await state.set_state(BotStates.waiting_goal)


# ─── Help ──────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного действия")
        return
    await state.clear()
    await message.answer("Действие отменено ✅")


# ─── Goals & Micro-steps ──────────────────────────────

@router.message(Command("goal"))
async def cmd_goal(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    user = await get_user(tg_id)
    if not user:
        await message.answer("Сначала напиши /start ❤️")
        return

    await message.answer(
        "О чём расскажешь? Что хочется начать менять?\n\n"
        "Напиши одной фразой, например:\n"
        "• «хочу больше отдыхать»\n"
        "• «хочу навести порядок на столе»\n"
        "• «хочу научиться новому»"
    )
    await state.set_state(BotStates.waiting_goal)


@router.message(BotStates.waiting_goal)
async def handle_goal(message: Message, state: FSMContext):
    await _generate_and_show_steps(message, state, message.text.strip())


async def _generate_and_show_steps(message: Message, state: FSMContext, goal_text: str):
    tg_id = message.from_user.id
    sent = await message.answer("Придумываю шаги... это может занять до 2 минут 🤔")

    try:
        steps = await generate_steps(goal_text)
    except Exception as e:
        error_text = str(e)
        if "timeout" in error_text.lower() or "timed out" in error_text.lower():
            await sent.edit_text(
                "Сервер генерации отвечает слишком долго 😔\n"
                "Попробуй ещё раз — иногда это занимает меньше минуты.\n"
                "Или напиши шаги сама: нажми /goal, а потом «добавить свой»."
            )
        else:
            await sent.edit_text(
                "Что-то пошло не так с генерацией. "
                "Попробуй ещё раз или опиши цель иначе."
            )
        return

    if not steps:
        await sent.edit_text(
            "Не получилось придумать шаги. Попробуй переформулировать цель."
        )
        return

    await state.update_data(generated_steps=steps, goal_text=goal_text)

    steps_text = format_steps_for_review(steps)
    await sent.edit_text(
        STEPS_READY.format(steps=steps_text),
        reply_markup=KeyboardBuilder.steps_review_keyboard(),
    )
    await state.set_state(BotStates.reviewing_steps)


@router.callback_query(F.data == "steps_confirm_all")
async def confirm_all_steps(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    data = await state.get_data()
    steps_texts = data.get("generated_steps", [])
    goal_text = data.get("goal_text", "")

    goal_id = await create_goal(tg_id, goal_text)
    await add_steps([{"tg_id": tg_id, "goal_id": goal_id, "text": s} for s in steps_texts])

    await callback.message.edit_text(ALL_CONFIRMED)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "steps_regenerate")
async def regenerate_steps(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    goal_text = data.get("goal_text", "")
    if goal_text:
        await callback.message.edit_text("Пробую ещё раз... 🤔")
        await _generate_and_show_steps(callback.message, state, goal_text)
    await callback.answer()


@router.callback_query(F.data == "steps_delete")
async def start_delete_step(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    steps = data.get("generated_steps", [])
    if not steps:
        await callback.answer("Нечего удалять")
        return

    await callback.message.edit_text(
        "Выбери, какой шаг удалить:",
        reply_markup=KeyboardBuilder.steps_select_keyboard(steps, "delete"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("delete_step_"))
async def handle_delete_step(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[-1])
    data = await state.get_data()
    steps = data.get("generated_steps", [])
    if 0 <= idx < len(steps):
        steps.pop(idx)
        await state.update_data(generated_steps=steps)

        if not steps:
            await callback.message.edit_text(
                "Все шаги удалены. Хочешь сгенерировать заново?",
                reply_markup=KeyboardBuilder.steps_review_keyboard(),
            )
        else:
            await callback.message.edit_text(
                STEPS_READY.format(steps=format_steps_for_review(steps)),
                reply_markup=KeyboardBuilder.steps_review_keyboard(),
            )
    await callback.answer()


@router.callback_query(F.data == "steps_back")
async def steps_back(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    steps = data.get("generated_steps", [])
    await callback.message.edit_text(
        STEPS_READY.format(steps=format_steps_for_review(steps)),
        reply_markup=KeyboardBuilder.steps_review_keyboard(),
    )
    await state.set_state(BotStates.reviewing_steps)
    await callback.answer()


@router.callback_query(F.data == "steps_add")
async def start_add_step(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Напиши свой шаг (одной фразой, что конкретно сделать):"
    )
    await state.set_state(BotStates.waiting_custom_step)
    await callback.answer()


@router.message(BotStates.waiting_custom_step)
async def handle_custom_step(message: Message, state: FSMContext):
    step_text = message.text.strip()
    if not step_text:
        await message.answer("Напиши, что за шаг ты хочешь добавить")
        return

    data = await state.get_data()
    steps = data.get("generated_steps", [])
    steps.append(step_text)
    await state.update_data(generated_steps=steps)

    await message.answer(
        STEPS_READY.format(steps=format_steps_for_review(steps)),
        reply_markup=KeyboardBuilder.steps_review_keyboard(),
    )
    await state.set_state(BotStates.reviewing_steps)


# ─── Daily flow ──────────────────────────────────────────

@router.message(Command("today"))
async def cmd_today(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    today = TODAY()
    await reset_unscheduled(tg_id, today)

    today_steps = await get_today_steps(tg_id, today)

    if today_steps:
        await _show_today_steps(message, today_steps)
        return

    pool = await get_pool_steps(tg_id)
    if not pool:
        await message.answer(NO_STEPS_IN_POOL)
        return

    await message.answer(NOTHING_SCHEDULED)
    await _ask_daily_count(message, state, tg_id)


async def _show_today_steps(message: Message, steps: list[dict]):
    done = [s for s in steps if s["status"] == "done"]
    pending = [s for s in steps if s["status"] == "scheduled"]

    text = "📋 Твои шаги на сегодня:\n\n"
    for s in done:
        text += f"✅ {s['text']}\n"
    for s in pending:
        text += f"⬜ {s['text']}\n"

    if not pending:
        text += "\nНа сегодня всё готово! 🎉"

    await message.answer(text)


async def _ask_daily_count(message: Message, state: FSMContext, tg_id: int):
    user = await get_user(tg_id)
    pool = await get_pool_steps(tg_id)
    if not pool:
        await message.answer(NO_STEPS_IN_POOL)
        return

    max_count = min(len(pool), user["daily_limit"])
    await message.answer(
        f"Сколько шагов возьмёшь на сегодня?\n"
        f"(в копилке {len(pool)}, лимит — {user['daily_limit']} в день)",
        reply_markup=KeyboardBuilder.daily_count_keyboard(max_count),
    )
    await state.update_data(pool_steps=pool)
    await state.set_state(BotStates.choosing_daily_count)


@router.callback_query(F.data.startswith("take_"))
async def handle_take_steps(callback: CallbackQuery, state: FSMContext):
    tg_id = callback.from_user.id
    count = int(callback.data.split("_")[1])
    today = TODAY()
    await reset_unscheduled(tg_id, today)

    data = await state.get_data()
    pool = data.get("pool_steps", [])
    if not pool:
        pool = await get_pool_steps(tg_id)

    if count == 0:
        await callback.message.edit_text(
            "Хорошо, в другой раз ❤️\n"
            "Когда будешь готова — нажми /today"
        )
        await state.clear()
        await callback.answer()
        return

    selected = pool[:count]
    step_ids = [s["id"] for s in selected]
    await schedule_steps(tg_id, step_ids, today)

    steps_text = "\n".join(f"{i+1}. {s['text']}" for i, s in enumerate(selected))
    await callback.message.edit_text(
        STEP_ASSIGNED.format(count=count, steps=steps_text)
    )

    await state.update_data(
        pending_steps=selected,
        completed_ids=set(),
        current_pending_idx=0,
    )
    await state.set_state(BotStates.waiting_reflection)
    await callback.answer()


# ─── Reflection flow ─────────────────────────────────────

@router.message(BotStates.waiting_reflection)
async def handle_reflection(message: Message, state: FSMContext):
    data = await state.get_data()
    pending = data.get("pending_steps", [])
    idx = data.get("current_pending_idx", 0)
    completed_ids = data.get("completed_ids", set())

    if idx >= len(pending):
        await state.clear()
        await message.answer("Все шаги на сегодня уже отмечены! 🎉")
        return

    step = pending[idx]

    if step["id"] in completed_ids:
        await message.answer("Спасибо, что поделилась ❤️")
        return

    await complete_step(step["id"])
    completed_ids.add(step["id"])
    await state.update_data(completed_ids=completed_ids)

    await message.answer(
        f"✅ «{step['text']}» — готово!\n\n"
        "Как ощущения? Напиши пару слов или нажми кнопку",
        reply_markup=KeyboardBuilder.reflection_keyboard(),
    )


async def _move_to_next_step(callback: CallbackQuery, state: FSMContext, message_text: str):
    data = await state.get_data()
    pending = data.get("pending_steps", [])
    idx = data.get("current_pending_idx", 0)

    idx += 1
    await state.update_data(current_pending_idx=idx)
    await callback.message.edit_text(message_text)

    if idx < len(pending):
        next_step = pending[idx]
        await callback.message.answer(
            f"Следующий шаг: «{next_step['text']}»\n"
            "Когда сделаешь — напиши об этом!",
        )
    else:
        await callback.message.answer(ALL_DONE_TODAY.format(count=idx))
        await state.clear()


@router.callback_query(F.data == "reflection_ok")
async def reflection_ok(callback: CallbackQuery, state: FSMContext):
    await _move_to_next_step(callback, state, STEP_DONE_REPLY)
    await callback.answer()


@router.callback_query(F.data == "reflection_great")
async def reflection_great(callback: CallbackQuery, state: FSMContext):
    await _move_to_next_step(callback, state, "Супер! Ты большая молодец ❤️")
    await callback.answer()


@router.callback_query(F.data == "reflection_hard")
async def reflection_hard(callback: CallbackQuery, state: FSMContext):
    await _move_to_next_step(
        callback, state,
        "То, что было трудно — делает тебя сильнее. "
        "Но ты всё равно сделала. Это важно ❤️"
    )
    await callback.answer()


# ─── Stats ───────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    tg_id = message.from_user.id
    user = await get_user(tg_id)
    if not user:
        await message.answer("Сначала напиши /start ❤️")
        return

    stats = await get_stats(tg_id)
    last = stats["last_active"] or "—"

    await message.answer(
        STATS_HEADER.format(
            total_done=stats["total_done"],
            today_done=stats["today_done"],
            week_done=stats["week_done"],
            in_pool=stats["in_pool"],
            last_active=last,
            encouragement=encouragement_text(stats["total_done"]),
        )
    )


# ─── Rest day ────────────────────────────────────────────

@router.message(Command("rest"))
async def cmd_rest(message: Message):
    tg_id = message.from_user.id
    user = await get_user(tg_id)
    if not user:
        await message.answer("Сначала напиши /start ❤️")
        return

    if user["is_paused"]:
        await update_user(tg_id, is_paused=0, pause_until=None)
        await message.answer(PAUSE_OFF)
    else:
        await update_user(tg_id, is_paused=1, pause_until=None)
        await message.answer(PAUSE_ON)


# ─── Settings ────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: Message):
    tg_id = message.from_user.id
    user = await get_user(tg_id)
    if not user:
        await message.answer("Сначала напиши /start ❤️")
        return

    await message.answer(
        SETTINGS_TEXT.format(
            count=user["daily_limit"],
            time=user["reminder_time"],
        ),
        reply_markup=KeyboardBuilder.settings_keyboard(),
    )


@router.callback_query(F.data.startswith("set_reminder_"))
async def set_reminder_time(callback: CallbackQuery):
    tg_id = callback.from_user.id
    time_str = callback.data.split("_")[-1]
    await update_user(tg_id, reminder_time=time_str)
    await callback.message.edit_text(
        f"Напоминания будут приходить в {time_str} ⏰"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_limit_"))
async def set_daily_limit(callback: CallbackQuery):
    tg_id = callback.from_user.id
    limit = int(callback.data.split("_")[-1])
    await update_user(tg_id, daily_limit=limit)
    await callback.message.edit_text(
        f"Буду предлагать до {limit} шагов в день ✅"
    )
    await callback.answer()
