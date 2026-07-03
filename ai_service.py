from openai import AsyncOpenAI

from config import settings

client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
    timeout=120.0,
    max_retries=1,
)


SYSTEM_PROMPT = (
    "Ты — добрый поддерживающий коуч. "
    "Пользователь хочет начать изменения в какой-то сфере жизни. "
    "Твоя задача — разбить эту большую цель на очень маленькие, конкретные шаги, "
    "каждый из которых занимает 2–10 минут.\n\n"
    "Правила:\n"
    "- Каждый шаг начинается с глагола в повелительном наклонении (сделай, открой, напиши, выброси, отожмись)\n"
    "- Шаги должны быть максимально простыми и безопасными — никакого давления\n"
    "- Не использовать отговорки вроде «подумай о...», только конкретные действия\n"
    "- 8–10 шагов\n"
    "- Ответить строго в формате: каждый шаг с новой строки, нумерованный\n\n"
    "Пример для «хочу начать бегать»:\n"
    "1. Достать кроссовки и поставить их на видное место\n"
    "2. Надеть спортивную одежду\n"
    "3. Выйти на улицу и пройтись 5 минут\n"
    "4. Пробежать 100 метров до того дерева\n"
    "5. Сделать 3 глубоких вдоха после\n"
    "6. Принять душ\n"
    "7. Написать в заметку «я сделала это»\n"
    "8. Поставить будильник на завтра"
)


async def generate_steps(goal: str) -> list[str]:
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Пользователь хочет: {goal}"},
        ],
        temperature=0.7,
        max_tokens=1000,
    )

    text = response.choices[0].message.content.strip()

    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        cleaned = line.lstrip("0123456789.)·-–—•▪▸➤ \t")
        if cleaned:
            lines.append(cleaned)

    return lines[:10]
