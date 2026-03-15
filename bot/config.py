from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    telegram_bot_token: str
    anthropic_api_key: str
    groq_api_key: str
    database_url: str

    # Rate limiting
    max_messages_per_window: int = 5
    rate_limit_window_seconds: int = 600

    # Scheduler
    morning_nudge_hour: int = 8
    evening_reflection_hour: int = 20

    # Monthly audit cooldown (days)
    monthly_cooldown_days: int = 21

    # Admin
    admin_telegram_id: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
