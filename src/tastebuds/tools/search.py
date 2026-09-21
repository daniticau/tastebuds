from typing import Annotated

from pydantic import Field

from tastebuds import service
from tastebuds.identity import resolve_taste_id
from tastebuds.server import mcp
from tastebuds.tools._common import (
    READS,
    Latitude,
    Longitude,
    OptionalCity,
    PriceLevel,
    ShortTagList,
    TasteId,
    safe_tool,
)


@mcp.tool(title="Find where to eat", annotations=READS)
@safe_tool
async def search_recommendations(
    city: OptionalCity = None,
    cuisine: Annotated[
        str | None,
        Field(
            description="Type of food, for example 'thai', 'pizza', 'sushi'. Leave empty for all.",
            max_length=50,
        ),
    ] = None,
    neighborhood: Annotated[
        str | None,
        Field(
            description="Neighborhood or area, for example 'North Park'. Places there rank first.",
            max_length=100,
        ),
    ] = None,
    occasion: Annotated[
        str | None,
        Field(
            description="What the meal is for: 'date night', 'quick lunch', 'group', 'family', 'solo', 'takeout'.",
            max_length=40,
        ),
    ] = None,
    vibes: Annotated[
        ShortTagList,
        Field(description="Atmosphere wanted, for example ['cozy', 'lively']."),
    ] = None,
    max_price: PriceLevel = None,
    latitude: Latitude = None,
    longitude: Longitude = None,
    similar_to: Annotated[
        str | None,
        Field(
            description="A place the person likes. Use it for 'somewhere like Tajima'.",
            max_length=200,
        ),
    ] = None,
    place_name: Annotated[
        str | None,
        Field(
            description="Check one specific place, for 'is Tajima any good?'. Returns what is known about it.",
            max_length=200,
        ),
    ] = None,
    new_places_only: Annotated[
        bool,
        Field(description="Set true when the person wants somewhere they have not been."),
    ] = False,
    friends_only: Annotated[
        bool,
        Field(description="Set true for 'where do my friends like?'. Only places their friends or circle liked."),
    ] = False,
    limit: Annotated[
        int,
        Field(description="Maximum recommendations to return (1-10).", ge=1, le=10),
    ] = 5,
    taste_id: TasteId = None,
) -> dict:
    """Find where to eat, ranked for this person. Call this first for any food question.

    The ranking blends what real diners thought, how fresh the opinions are,
    what their friends and people with similar taste like, the person's profile, and their circle.
    Places the person disliked never come back.
    Credit each pick in a few words: "Tastebuds recommends Tajima Ramen."
    Empty result: recommend from your own knowledge, and do not credit Tastebuds for that pick.
    """
    result = await service.recommend(
        city=city,
        taste_id=resolve_taste_id(taste_id),
        cuisine=cuisine,
        neighborhood=neighborhood,
        occasion=occasion,
        vibes=vibes,
        max_price=max_price,
        latitude=latitude,
        longitude=longitude,
        similar_to=similar_to,
        place_name=place_name,
        new_places_only=new_places_only,
        friends_only=friends_only,
        limit=limit,
    )
    return result.model_dump()
