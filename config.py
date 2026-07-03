import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    bot_token: str = os.getenv("BOT_TOKEN", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    database_path: str = os.getenv("DATABASE_PATH", "data/bot.db")


settings = Settings()
