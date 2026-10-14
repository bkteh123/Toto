from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://royal:royal@localhost:5432/royal_yellow"
    collector_min_interval_seconds: float = 5.0
    collector_user_agent: str = (
        "RoyalYellowAnalyzer/0.1 (+https://codencode.my; historical-analysis research tool)"
    )
    collector_cache_dir: str = ".collector_cache"
    scheduler_enabled: bool = True
    timezone: str = "Asia/Ho_Chi_Minh"


@lru_cache
def get_settings() -> Settings:
    return Settings()
