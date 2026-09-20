"""Quick decisions from Jev, the System One model from TypeSafe AI.

Jev reads program state and answers typed questions in about 100 ms. It writes no text.
The engine asks it where a fixed rule is too blunt:

- Is this new mention the same restaurant as one we already know?
- What cuisine is a new place that arrived without tags?
- Does a comment identify a private person? (off by default)

Every decision is optional. With no API key, a slow answer, or any error, the function
returns None and the caller uses its fixed rule. Jev can make the engine better.
It can never stop the engine.

API reference: https://docs.typesafe.ai/api
"""

import logging
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from tastebuds.config import Settings, get_settings
from tastebuds.taxonomy import cuisine_choices

logger = logging.getLogger(__name__)

_API_URL = "https://api.typesafe.ai/v1/systemone"
_UNKNOWN = "unknown"
_MAX_CANDIDATES = 3

_client: httpx.AsyncClient | None = None


@dataclass
class KnownPlace:
    """An existing place that might be the one the person means."""

    name: str
    neighborhood: str | None = None
    cuisine_tags: list[str] | None = None


@dataclass
class PlaceDecision:
    # True when Jev answered the sameness questions. False means: use the fixed rule.
    answered_sameness: bool = False
    # Index into the candidates when one of them is the same place.
    same_as: int | None = None
    cuisine: str | None = None


def _settings() -> Settings | None:
    try:
        settings = get_settings()
    except ValidationError:
        return None
    return settings if settings.typesafe_api_key else None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def ask(state: dict | str, questions: dict[str, dict]) -> dict | None:
    """Send one request to Jev. Return the answers, or None when there is no usable answer."""
    settings = _settings()
    if settings is None or not questions:
        return None

    try:
        response = await _get_client().post(
            _API_URL,
            json={"model": settings.jev_model, "state": state, "questions": questions},
            headers={"Authorization": f"Bearer {settings.typesafe_api_key}"},
            timeout=settings.jev_timeout_seconds,
        )
        response.raise_for_status()
        answers = response.json()["answers"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        # No retry: a quick decision that is late is worth less than the fixed rule now.
        logger.warning("Jev gave no usable answer (%s). Using the fixed rule.", type(exc).__name__)
        return None

    return answers if isinstance(answers, dict) else None


def _noul(answers: dict, key: str) -> float | None:
    value = (answers.get(key) or {}).get("noul")
    return float(value) if isinstance(value, (int, float)) else None


async def decide_place(
    *,
    name: str,
    city: str,
    neighborhood: str | None,
    hints: list[str],
    candidates: list[KnownPlace],
    need_cuisine: bool,
) -> PlaceDecision | None:
    """Ask both place questions in one round trip.

    candidates are known places with similar names, in the zone where the name
    match alone cannot tell. hints are dish names the person mentioned.
    """
    candidates = candidates[:_MAX_CANDIDATES]
    questions: dict[str, dict] = {}

    for index, _candidate in enumerate(candidates):
        questions[f"same_as_{index}"] = {
            "type": "noul",
            "instructions": (
                f"The new mention and known place {index} are the same restaurant or food business."
            ),
            "criteria": {
                "true": (
                    "Same business: spelling variants, a shortened name, an added word such as "
                    "'restaurant', or another branch of the same chain in this city."
                ),
                "false": "Different businesses, even when the names share words or a cuisine.",
            },
        }

    if need_cuisine:
        criteria: dict[str, str | None] = {cuisine: None for cuisine in cuisine_choices()}
        criteria[_UNKNOWN] = "The name and the dishes do not tell what food this place serves."
        questions["cuisine"] = {
            "type": "choice",
            "instructions": "What is the main type of food this place serves?",
            "criteria": criteria,
        }

    state = {
        "city": city,
        "new_mention": {"name": name, "neighborhood": neighborhood, "dishes_mentioned": hints},
        "known_places": [
            {
                "index": index,
                "name": candidate.name,
                "neighborhood": candidate.neighborhood,
                "cuisine_tags": candidate.cuisine_tags or [],
            }
            for index, candidate in enumerate(candidates)
        ],
    }

    answers = await ask(state, questions)
    if answers is None:
        return None

    settings = get_settings()
    decision = PlaceDecision()

    scores = [_noul(answers, f"same_as_{index}") for index in range(len(candidates))]
    if candidates and all(score is not None for score in scores):
        decision.answered_sameness = True
        best = max(range(len(scores)), key=lambda index: scores[index])
        if scores[best] >= settings.jev_same_place_threshold:
            decision.same_as = best

    cuisine = answers.get("cuisine") or {}
    choice = cuisine.get("choice")
    confidence = cuisine.get("confidence")
    if (
        choice in cuisine_choices()
        and isinstance(confidence, (int, float))
        and confidence >= settings.jev_cuisine_confidence
    ):
        decision.cuisine = choice

    return decision


async def comment_identifies_someone(comment: str) -> float | None:
    """Probability that a comment could identify a private person. None when Jev is off."""
    settings = _settings()
    if settings is None or not settings.jev_check_comments:
        return None

    answers = await ask(
        comment,
        {
            "identifies_someone": {
                "type": "noul",
                "instructions": "The text could identify a private person.",
                "criteria": {
                    "true": (
                        "It names a person, or gives a detail such as a workplace, a home address, "
                        "or a family event that points at a specific individual."
                    ),
                    "false": "It only describes food, service, price, or atmosphere. Staff roles are fine.",
                },
            },
        },
    )
    return _noul(answers, "identifies_someone") if answers else None
