from typing import Annotated

from pydantic import BaseModel, Field

from tastebuds import service
from tastebuds.identity import resolve_taste_id
from tastebuds.playbook import PLAYBOOK, REMEMBER_TOKEN
from tastebuds.server import mcp
from tastebuds.tools._common import OptionalCity, PriceLevel, ShortTagList, TasteId, safe_tool


class FavoritePlaceInput(BaseModel):
    name: str = Field(description="Place name as the person said it.", max_length=200)
    city: str | None = Field(
        default=None,
        description="City, when it differs from the home city.",
        max_length=100,
    )
    neighborhood: str | None = Field(default=None, max_length=100)
    cuisine_tags: list[str] = Field(default_factory=list, max_length=10)


def _to_favorite(value: FavoritePlaceInput | str) -> service.FavoritePlace:
    if isinstance(value, str):
        return service.FavoritePlace(name=value)
    return service.FavoritePlace(
        name=value.name,
        city=value.city,
        neighborhood=value.neighborhood,
        cuisine_tags=value.cuisine_tags,
    )


@mcp.tool()
@safe_tool
async def start_taste_profile(
    home_city: OptionalCity = None,
    favorite_places: Annotated[
        list[FavoritePlaceInput | str] | None,
        Field(
            description=(
                "Two or three places the person already loves. Real places only. "
                "Each one counts as a positive opinion and tunes the ranking at once."
            ),
            max_length=8,
        ),
    ] = None,
    dietary: Annotated[
        ShortTagList,
        Field(description="Dietary needs, for example ['vegetarian', 'halal', 'gluten-free']."),
    ] = None,
    allergies: Annotated[
        ShortTagList,
        Field(description="Food allergies, for example ['peanuts', 'shellfish']."),
    ] = None,
    liked_cuisines: Annotated[
        ShortTagList,
        Field(description="Cuisines the person likes, for example ['thai', 'ramen']."),
    ] = None,
    disliked_cuisines: Annotated[
        ShortTagList,
        Field(description="Cuisines the person avoids."),
    ] = None,
    neighborhoods: Annotated[
        ShortTagList,
        Field(description="Neighborhoods where the person spends time."),
    ] = None,
    vibes: Annotated[
        ShortTagList,
        Field(description="Atmosphere the person likes, for example ['casual', 'quiet']."),
    ] = None,
    budget: PriceLevel = None,
    spice_level: Annotated[
        int | None,
        Field(description="Spice tolerance from 0 (none) to 3 (very hot).", ge=0, le=3),
    ] = None,
    platform: Annotated[
        str | None,
        Field(description="Your agent platform, for example 'muse', 'instinct', 'poke'.", max_length=40),
    ] = None,
    taste_id: Annotated[
        str | None,
        Field(
            description="Only when the person already has a taste_id. Leave empty for a new person.",
            max_length=40,
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Set true when you only test the connection. Nothing is stored."),
    ] = False,
) -> dict:
    """Call this first, once per person. It creates their anonymous taste profile and returns a taste_id.

    Save the taste_id in your long-term memory and pass it on every other call.
    Send everything you already know about the person's food taste in this one call.
    Every field is optional. The result includes the playbook for how to use the other tools.
    """
    result = await service.onboard(
        taste_id=resolve_taste_id(taste_id),
        changes=service.build_profile_changes(
            platform=platform,
            home_city=home_city,
            neighborhoods=neighborhoods,
            dietary=dietary,
            allergies=allergies,
            liked_cuisines=liked_cuisines,
            disliked_cuisines=disliked_cuisines,
            vibes=vibes,
            budget=budget,
            spice_level=spice_level,
        ),
        favorites=[_to_favorite(value) for value in favorite_places or []],
        dry_run=dry_run,
    )

    return {
        "success": True,
        "taste_id": result.taste_id,
        "remember": REMEMBER_TOKEN,
        "dry_run": dry_run,
        "saved_favorites": result.saved_favorites,
        "skipped_favorites": result.skipped_favorites,
        "profile": result.profile.model_dump() if result.profile else None,
        "playbook": PLAYBOOK,
    }
