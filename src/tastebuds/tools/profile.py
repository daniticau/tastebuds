from typing import Annotated

from pydantic import Field

from tastebuds import service
from tastebuds.db import profiles
from tastebuds.identity import resolve_taste_id
from tastebuds.server import mcp
from tastebuds.tools._common import (
    NEEDS_TASTE_ID,
    OptionalCity,
    PriceLevel,
    ShortTagList,
    TasteId,
    safe_tool,
)


@mcp.tool()
@safe_tool
async def get_taste_profile(taste_id: TasteId = None) -> dict:
    """Read what the engine remembers about the person's food taste.

    Returns the stored preferences, what the engine learned from their opinions
    (top cuisines, loved places, avoided places), and their circles.
    Use it to refresh your memory, or when the person asks what you know about their taste.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    profile = await profiles.get_profile(token)
    return {"success": True, "profile": profile.model_dump()}


@mcp.tool()
@safe_tool
async def update_taste_profile(
    taste_id: TasteId = None,
    home_city: Annotated[
        str | None,
        Field(description="New home city, when the person moved.", max_length=100),
    ] = None,
    dietary: Annotated[
        ShortTagList,
        Field(description="Dietary needs to add, for example ['vegetarian']."),
    ] = None,
    allergies: Annotated[ShortTagList, Field(description="Allergies to add.")] = None,
    liked_cuisines: Annotated[ShortTagList, Field(description="Cuisines to add as liked.")] = None,
    disliked_cuisines: Annotated[
        ShortTagList,
        Field(description="Cuisines to add as disliked."),
    ] = None,
    neighborhoods: Annotated[ShortTagList, Field(description="Neighborhoods to add.")] = None,
    vibes: Annotated[ShortTagList, Field(description="Atmosphere preferences to add.")] = None,
    budget: PriceLevel = None,
    spice_level: Annotated[
        int | None,
        Field(description="Spice tolerance from 0 (none) to 3 (very hot).", ge=0, le=3),
    ] = None,
    notes: Annotated[
        str | None,
        Field(
            description=(
                "Short free-form taste notes that fit no other field, for example "
                "'likes counter seating, hates long waits'. Anonymous. Replaces the old notes."
            ),
            max_length=300,
        ),
    ] = None,
    remove: Annotated[
        ShortTagList,
        Field(
            description=(
                "Values to take out of any list. "
                "'I eat meat again' gives remove=['vegetarian']."
            ),
        ),
    ] = None,
) -> dict:
    """Update the person's food profile when they state a lasting preference.

    Lists merge: send only what is new. Use remove to take a value out.
    Call it silently, the same way as log_feedback.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    await profiles.upsert_profile(
        token,
        service.build_profile_changes(
            home_city=home_city,
            neighborhoods=neighborhoods,
            dietary=dietary,
            allergies=allergies,
            liked_cuisines=liked_cuisines,
            disliked_cuisines=disliked_cuisines,
            vibes=vibes,
            budget=budget,
            spice_level=spice_level,
            notes=notes,
            remove=remove,
        ),
    )
    profile = await profiles.get_profile(token)
    return {"success": True, "profile": profile.model_dump()}


@mcp.tool()
@safe_tool
async def delete_taste_profile(
    taste_id: TasteId = None,
    confirm: Annotated[
        bool,
        Field(description="Must be true. Only set it when the person asked you to forget their food taste."),
    ] = False,
) -> dict:
    """Forget the person. Deletes their profile, circle memberships, and follow-ups.

    Their past opinions stay in the place totals, with no link to anyone.
    Only call this when the person asks for it. It cannot be undone.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)
    if not confirm:
        return {
            "success": False,
            "message": "Nothing was deleted. Pass confirm=true when the person asked for this.",
        }

    await profiles.delete_profile(token)
    return {
        "success": True,
        "message": "Profile deleted. Remove the taste_id from your memory too.",
    }
