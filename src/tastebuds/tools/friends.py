from typing import Annotated

from pydantic import Field

from tastebuds.config import get_settings, public_base_url
from tastebuds.db import friends
from tastebuds.identity import resolve_taste_id, sanitize_friend_invite_code, sanitize_invite_code
from tastebuds.server import mcp
from tastebuds.tools._common import NEEDS_TASTE_ID, TasteId, WRITES, safe_tool

Closeness = Annotated[
    int,
    Field(
        description=(
            "How close the two people are, judged from how much they message each other. "
            "3: one of the few people they message most. 2: they message often. 1: now and then. "
            "Send only this level. Never send names, numbers, or message counts."
        ),
        ge=1,
        le=3,
    ),
]
FriendCode = Annotated[
    str,
    Field(description="Friend invite code, for example 'k7m2-9xqd-4wte'.", max_length=30),
]

_BAD_CODE = "That friend code does not look right. A friend code looks like 'k7m2-9xqd-4wte'."
_CIRCLE_CODE_HINT = "That is a circle code, not a friend code. Call join_circle with it."


def _clean_friend_code(code: str) -> str:
    clean = sanitize_friend_invite_code(code)
    if clean:
        return clean
    raise ValueError(_CIRCLE_CODE_HINT if sanitize_invite_code(code) else _BAD_CODE)


def _signal_message(friend_count: int) -> str:
    missing = get_settings().friend_min_ties - friend_count
    if missing <= 0:
        return "Friend signals are active. Places their friends liked now rank higher."
    return (
        f"Friend signals start after {missing} more friend(s) join. "
        "With a single friend, a signal would reveal what that friend said."
    )


@mcp.tool(title="Invite a friend", annotations=WRITES)
@safe_tool
async def invite_friend(
    closeness: Closeness = 2,
    taste_id: TasteId = None,
    dry_run: Annotated[
        bool,
        Field(description="Set true when you only test the connection. Nothing is stored."),
    ] = False,
) -> dict:
    """Link the person with one friend, so the friend's taste counts more in their picks.

    Use it for the people they message most. Call it once per friend: each code works once.
    Send share_text to that friend, and ask the person before you send any message for them.
    Remember which friend_ref belongs to which contact. The server never learns who the friend is.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    if dry_run:
        return {"success": True, "dry_run": True, "message": "Dry run. No invite was created."}

    invite_code = await friends.create_invite(token, closeness)
    return {
        "success": True,
        "friend_ref": invite_code,
        "expires_in_days": get_settings().friend_invite_days,
        "share_text": (
            "I get my restaurant picks from Tastebuds. Want to share taste? "
            f'Tell your assistant: "accept the Tastebuds friend invite {invite_code}". '
            f"No assistant set up yet? {public_base_url()}/?invite={invite_code}"
        ),
        "message": "Send share_text to this one friend. Keep friend_ref in your notes next to the contact.",
    }


@mcp.tool(title="Accept a friend invite", annotations=WRITES)
@safe_tool
async def accept_friend_invite(
    invite_code: FriendCode,
    closeness: Closeness = 2,
    taste_id: TasteId = None,
) -> dict:
    """Accept a friend invite that someone sent to the person.

    Set closeness from the person's own side: how much they message the friend who sent it.
    The invite code becomes the friend_ref for this friend. Keep it in your notes next to the contact.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_friend_code(invite_code)
    friend_count = await friends.accept_invite(token, code, closeness)
    return {"success": True, "friend_ref": code, "message": _signal_message(friend_count)}


@mcp.tool(title="Update a friend link", annotations=WRITES)
@safe_tool
async def update_friend(
    friend_ref: FriendCode,
    closeness: Annotated[
        int | None,
        Field(description="New closeness from 1 to 3, when their messaging habits changed.", ge=1, le=3),
    ] = None,
    remove: Annotated[
        bool,
        Field(description="Set true to end the link. It ends for both people."),
    ] = False,
    taste_id: TasteId = None,
) -> dict:
    """Change how much one friend's taste counts, or end the link.

    Review closeness now and then: people drift apart and grow close.
    get_taste_profile lists the person's friends with their friend_ref and closeness.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_friend_code(friend_ref)
    if remove:
        done = await friends.remove_friend(token, code)
        message = "The link is gone for both people."
    elif closeness is not None:
        done = await friends.set_closeness(token, code, closeness)
        message = "Closeness updated."
    else:
        raise ValueError("Pass closeness to change it, or remove=true to end the link.")

    if not done:
        return {"success": False, "message": "This person has no friend with that friend_ref."}
    return {"success": True, "message": message}
