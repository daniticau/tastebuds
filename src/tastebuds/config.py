from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables."""

    database_url: str

    fuzzy_match_threshold: float = 0.6
    recency_halflife_days: int = 30
    min_reviews_for_ranking: int = 1

    model_config = {"env_prefix": "TASTEBUDS_", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    """Lazy singleton; validate env vars only on first call."""
    return Settings()
