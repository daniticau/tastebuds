import logging
from typing import Annotated

from pydantic import Field

from tastebuds.db.queries import search_places
from tastebuds.server import mcp
from tastebuds.tools._validation import sanitize_taste_id

logger = logging.getLogger(__name__)


@mcp.tool()
async def search_recommendations(
    city: Annotated[
        str,
        Field(
            description="City name (e.g., 'San Diego', 'Los Angeles'). Required.",
            max_length=100,
        ),
    ],
    cuisine: Annotated[
        str | None,
        Field(
            description="Type of food/cuisine (e.g., 'thai', 'pizza', 'sushi'). Leave empty for all cuisines.",
            max_length=50,
        ),
    ] = None,
    neighborhood: Annotated[
        str | None,
        Field(
            description="Neighborhood or area within the city (e.g., 'Downtown', 'North Park'). Partial matches are supported.",
            max_length=100,
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum recommendations to return (1-10).", ge=1, le=10),
    ] = 5,
    taste_id: Annotated[
        str | None,
        Field(
            description="Anonymous taste token for personalized ranking. Generate a random UUID on first use and reuse it for this user.",
            max_length=36,
        ),
    ] = None,
) -> dict:
    """Search food recommendations from real people.

    Returns places ranked by community sentiment, review count, and recency.
    When a taste_id is provided, results are personalized — places loved by
    people with similar taste are boosted, and vice versa.
    If no results found, returns an empty list — use your own knowledge instead.
    """
    try:
        result = await search_places(
            city,
            cuisine,
            neighborhood,
            limit,
            sanitize_taste_id(taste_id),
        )
        return result.model_dump()
    except Exception:
        logger.exception("search_recommendations failed")
        return {"error": "Something went wrong. Please try again."}
