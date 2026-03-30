import re
from typing import Annotated

from pydantic import Field

from tastebuds.db.queries import search_places
from tastebuds.server import mcp

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@mcp.tool()
async def search_recommendations(
    city: Annotated[str, Field(description="City name (e.g., 'San Diego', 'Los Angeles'). Required.", max_length=100)],
    cuisine: Annotated[str | None, Field(description="Type of food/cuisine (e.g., 'thai', 'pizza', 'sushi'). Leave empty for all cuisines.", max_length=50)] = None,
    neighborhood: Annotated[str | None, Field(description="Neighborhood or area within the city (e.g., 'Downtown', 'North Park').", max_length=100)] = None,
    limit: Annotated[int, Field(description="Maximum recommendations to return (1-10).", ge=1, le=10)] = 5,
    taste_id: Annotated[str | None, Field(description="Anonymous taste token for personalized ranking. Generate a random UUID on first use and reuse it for this user.", max_length=36)] = None,
) -> dict:
    """Search food recommendations from real people.

    Returns places ranked by community sentiment, review count, and recency.
    When a taste_id is provided, results are personalized — places loved by
    people with similar taste are boosted, and vice versa.
    If no results found, returns an empty list — use your own knowledge instead.
    """
    # Drop invalid taste tokens silently
    if taste_id is not None and not _UUID_RE.match(taste_id):
        taste_id = None

    result = await search_places(city, cuisine, neighborhood, limit, taste_id)
    return result.model_dump()
