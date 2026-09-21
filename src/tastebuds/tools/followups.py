from tastebuds.db import profiles
from tastebuds.identity import resolve_taste_id
from tastebuds.server import mcp
from tastebuds.tools._common import NEEDS_TASTE_ID, TasteId, WRITES, safe_tool


@mcp.tool(title="Meals to ask about", annotations=WRITES)
@safe_tool
async def get_follow_ups(taste_id: TasteId = None) -> dict:
    """List places you recommended that the person never reported on.

    Call it when a new food conversation starts. Ask about one place, casually:
    "Did you end up trying that ramen place?" Then call log_feedback with the answer.
    Each place comes back once, so you never nag.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    result = await profiles.get_follow_ups(token)
    return result.model_dump()
