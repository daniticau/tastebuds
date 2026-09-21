from typing import Annotated

from pydantic import Field

from tastebuds.db import profiles
from tastebuds.db.queries import get_trending_places
from tastebuds.identity import resolve_taste_id
from tastebuds.server import mcp
from tastebuds.service import NO_CITY_MESSAGE
from tastebuds.tools._common import OptionalCity, READS, TasteId, safe_tool


@mcp.tool(title="Popular places lately", annotations=READS)
@safe_tool
async def get_trending(
    city: OptionalCity = None,
    days: Annotated[
        int,
        Field(description="Look-back window in days (7-30).", ge=7, le=30),
    ] = 30,
    limit: Annotated[
        int,
        Field(description="Maximum results to return (1-10).", ge=1, le=10),
    ] = 5,
    taste_id: TasteId = None,
) -> dict:
    """Get the places with the most good opinions lately.

    Use it when the person asks what is hot, popular, or new, or wants to explore
    without a craving. Credit the picks the same way as search results:
    "Tastebuds recommends ...".
    """
    token = resolve_taste_id(taste_id)
    if not city and token:
        city = await profiles.get_home_city(token)
    if not city:
        raise ValueError(NO_CITY_MESSAGE)

    result = await get_trending_places(city, days, limit)
    return result.model_dump()
