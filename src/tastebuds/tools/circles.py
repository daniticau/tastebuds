from typing import Annotated

from pydantic import Field

from tastebuds.config import get_settings
from tastebuds.db import profiles
from tastebuds.db.models import CircleInfo
from tastebuds.identity import (
    resolve_taste_id,
    sanitize_friend_invite_code,
    sanitize_invite_code,
)
from tastebuds.privacy import scrub_text
from tastebuds.server import mcp
from tastebuds.tools._common import NEEDS_TASTE_ID, TasteId, WRITES, safe_tool

InviteCode = Annotated[
    str,
    Field(description="Circle invite code, for example 'k7m2-9xqd'.", max_length=20),
]

_BAD_CODE = "That invite code does not look right. A code looks like 'k7m2-9xqd'."
_FRIEND_CODE_HINT = "That is a friend code, not a circle code. Call accept_friend_invite with it."


def _clean_circle_code(code: str) -> str:
    clean = sanitize_invite_code(code)
    if clean:
        return clean
    raise ValueError(_FRIEND_CODE_HINT if sanitize_friend_invite_code(code) else _BAD_CODE)


def _circle_message(circle: CircleInfo) -> str:
    if circle.active:
        return "The circle is active. Its picks now shape this person's recommendations."

    missing = get_settings().circle_min_members - circle.member_count
    return (
        f"The circle needs {missing} more member(s) before it shapes recommendations. "
        "Small circles stay silent so no one can tell who said what."
    )


@mcp.tool(title="Create a circle", annotations=WRITES)
@safe_tool
async def create_circle(
    taste_id: TasteId = None,
    name: Annotated[
        str | None,
        Field(description="Optional circle name, for example 'roommates'.", max_length=60),
    ] = None,
    dry_run: Annotated[
        bool,
        Field(description="Set true when you only test the connection. Nothing is stored."),
    ] = False,
) -> dict:
    """Create a circle: a friend group whose taste shapes each other's recommendations.

    Returns an invite code. The person texts the code to friends.
    Each friend gives the code to their own agent, which calls join_circle.
    Circle signals stay anonymous: counts only, never who said what.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)
    if dry_run:
        return {"success": True, "dry_run": True, "message": "Dry run. No circle was created."}

    circle = await profiles.create_circle(token, scrub_text(name, max_length=60))
    return {
        "success": True,
        "circle": circle.model_dump(),
        "share_text": (
            f"Join my food circle. Tell your assistant: "
            f"\"join the Tastebuds circle {circle.invite_code}\""
        ),
        "message": _circle_message(circle),
    }


@mcp.tool(title="Join a circle", annotations=WRITES)
@safe_tool
async def join_circle(invite_code: InviteCode, taste_id: TasteId = None) -> dict:
    """Join a friend's circle with the invite code the friend sent."""
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_circle_code(invite_code)

    circle = await profiles.join_circle(token, code)
    return {"success": True, "circle": circle.model_dump(), "message": _circle_message(circle)}


@mcp.tool(title="Leave a circle", annotations=WRITES)
@safe_tool
async def leave_circle(invite_code: InviteCode, taste_id: TasteId = None) -> dict:
    """Leave a circle. Use get_taste_profile to see the person's circles and their codes."""
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_circle_code(invite_code)

    left = await profiles.leave_circle(token, code)
    if not left:
        return {"success": False, "message": "This person is not in that circle."}
    return {"success": True, "message": "Left the circle."}
