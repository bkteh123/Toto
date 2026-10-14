from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://royal:royal@localhost:5432/royal_yellow"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, v: str) -> str:
        # Hosting platforms (Railway, Heroku, ...) hand out plain postgres:// or postgresql://
        # URLs, which SQLAlchemy would resolve to psycopg2; this project ships psycopg 3.
        for scheme in ("postgres://", "postgresql://"):
            if v.startswith(scheme):
                return "postgresql+psycopg://" + v[len(scheme):]
        return v

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
