from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder as Builder


class KeyboardBuilder:

    @staticmethod
    def steps_review_keyboard() -> InlineKeyboardMarkup:
        b = Builder()
        b.row(
            InlineKeyboardButton(text="✅ Оставить всё", callback_data="steps_confirm_all"),
        )
        b.row(
            InlineKeyboardButton(text="🗑️ Удалить", callback_data="steps_delete"),
            InlineKeyboardButton(text="✏️ Добавить свой", callback_data="steps_add"),
        )
        b.row(
            InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="steps_regenerate"),
        )
        return b.as_markup()

    @staticmethod
    def steps_select_keyboard(steps: list[str], action: str) -> InlineKeyboardMarkup:
        b = Builder()
        for i, step in enumerate(steps):
            short = step[:40] + "…" if len(step) > 40 else step
            b.row(
                InlineKeyboardButton(
                    text=f"✖ {short}",
                    callback_data=f"{action}_step_{i}",
                )
            )
        b.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="steps_back"),
        )
        return b.as_markup()

    @staticmethod
    def daily_count_keyboard(max_count: int) -> InlineKeyboardMarkup:
        b = Builder()
        buttons = []
        for i in range(1, max_count + 1):
            buttons.append(
                InlineKeyboardButton(text=str(i), callback_data=f"take_{i}")
            )
        buttons.append(InlineKeyboardButton(text="🙅 Не сегодня", callback_data="take_0"))
        b.row(*buttons)
        return b.as_markup()

    @staticmethod
    def reflection_keyboard() -> InlineKeyboardMarkup:
        b = Builder()
        b.row(
            InlineKeyboardButton(text="😊 Всё ок", callback_data="reflection_ok"),
            InlineKeyboardButton(text="🔥 Супер!", callback_data="reflection_great"),
            InlineKeyboardButton(text="😰 Было трудно", callback_data="reflection_hard"),
        )
        return b.as_markup()

    @staticmethod
    def settings_keyboard() -> InlineKeyboardMarkup:
        b = Builder()
        b.row(
            InlineKeyboardButton(text="⏰ 09:00", callback_data="set_reminder_09:00"),
            InlineKeyboardButton(text="⏰ 10:00", callback_data="set_reminder_10:00"),
            InlineKeyboardButton(text="⏰ 11:00", callback_data="set_reminder_11:00"),
        )
        b.row(
            InlineKeyboardButton(text="📦 1 шаг", callback_data="set_limit_1"),
            InlineKeyboardButton(text="📦 3 шага", callback_data="set_limit_3"),
            InlineKeyboardButton(text="📦 5 шагов", callback_data="set_limit_5"),
        )
        return b.as_markup()
