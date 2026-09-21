from functools import lru_cache

from pydantic import ValidationError
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables."""

    database_url: str
    # Neon can take a moment to wake up, so a failed connect is tried again with backoff.
    db_connect_attempts: int = 3

    # Public origin of this deployment. The landing page and the agent playbook print it.
    public_base_url: str = "https://tastebuds-production.up.railway.app"

    # Place dedup. At or above auto-merge, the name match alone decides.
    # Between the review floor and auto-merge, Jev decides when it is configured.
    # Without Jev, the fuzzy threshold decides, as before.
    fuzzy_match_threshold: float = 0.6
    dedup_auto_merge_similarity: float = 0.85
    dedup_review_floor: float = 0.25

    # Jev (TypeSafe AI) for quick typed decisions. Optional: with no key, fixed rules apply.
    typesafe_api_key: str | None = None
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 1.5
    jev_same_place_threshold: float = 0.7
    jev_cuisine_confidence: float = 0.5
    # Off by default: this one sends comment text to TypeSafe. Read their data policy first.
    jev_check_comments: bool = False
    jev_comment_threshold: float = 0.6

    # Ranking
    recency_halflife_days: int = 120
    min_reviews_for_ranking: int = 1
    quality_prior_mean: float = 0.6
    quality_prior_weight: float = 3.0
    candidate_pool_size: int = 400

    # Circles only show a signal when the circle has this many members.
    # Below that, "one person in your circle" would name the person.
    circle_min_members: int = 3

    # Friend signals need this many linked friends, for the same reason.
    friend_min_ties: int = 2
    friend_invite_days: int = 14

    # Follow-ups
    followup_min_age_hours: int = 3
    followup_max_age_days: int = 21

    # Abuse limits
    max_feedback_per_token_per_day: int = 40
    rate_limit_per_minute: int = 300
    trust_proxy_headers: bool = True

    model_config = {"env_prefix": "TASTEBUDS_", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    """Lazy singleton; validate env vars only on first call."""
    return Settings()


def public_base_url() -> str:
    """The origin to print in links. Works even when no database URL is configured."""
    try:
        return get_settings().public_base_url.rstrip("/")
    except ValidationError:
        return "http://localhost:8000"
