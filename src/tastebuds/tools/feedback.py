import re
from typing import Annotated

from pydantic import Field

from tastebuds.db.queries import find_or_create_place, insert_feedback
from tastebuds.server import mcp

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@mcp.tool()
async def log_feedback(
    place_name: Annotated[str, Field(description="Name of the restaurant or food place as the user mentioned it.", max_length=200)],
    city: Annotated[str, Field(description="City where the place is located.", max_length=100)],
    sentiment: Annotated[str, Field(description="Overall sentiment: 'positive', 'negative', or 'neutral'. Infer from the user's description.")],
    neighborhood: Annotated[str | None, Field(description="Neighborhood if known.", max_length=100)] = None,
    cuisine_tags: Annotated[list[str] | None, Field(description="Cuisine types (e.g., ['thai', 'noodles']). Infer from conversation.", max_length=10)] = None,
    comment: Annotated[str | None, Field(description="Brief summary of feedback (1 sentence max). Anonymize: no names, no identifying details.", max_length=500)] = None,
    visit_context: Annotated[str | None, Field(description="Context: 'dinner', 'lunch', 'brunch', 'takeout', 'delivery', 'date night', etc.", max_length=100)] = None,
    taste_id: Annotated[str | None, Field(description="Anonymous taste token. Generate a random UUID on first use and reuse it for this user. Enables personalized recommendations over time.", max_length=36)] = None,
) -> dict:
    """Log anonymized feedback about a food place from a real visit.

    Call this after a user shares how their dining experience went.
    The feedback is fully anonymized — no user identity is stored.
    If the place doesn't exist in the database yet, it will be created.
    When a taste_id is provided, the feedback contributes to collaborative
    filtering — the system learns whose taste aligns with whose.
    """
    if sentiment not in ("positive", "negative", "neutral"):
        return {"success": False, "message": "Sentiment must be 'positive', 'negative', or 'neutral'."}

    # Drop invalid taste tokens silently
    if taste_id is not None and not _UUID_RE.match(taste_id):
        taste_id = None

    place_id, canonical_name = await find_or_create_place(
        name=place_name,
        city=city,
        neighborhood=neighborhood,
        cuisine_tags=cuisine_tags,
    )

    result = await insert_feedback(
        place_id=place_id,
        sentiment=sentiment,
        comment=comment,
        visit_context=visit_context,
        taste_id=taste_id,
    )
    return result.model_dump()
