from typing import Annotated

from pydantic import Field

from tastebuds import service
from tastebuds.config import get_settings, public_base_url
from tastebuds.db import friends, profiles
from tastebuds.identity import resolve_taste_id, sanitize_friend_invite_code, sanitize_invite_code
from tastebuds.server import mcp
from tastebuds.tools._common import (
    NEEDS_TASTE_ID,
    READS,
    WRITES,
    OptionalCity,
    TasteId,
    safe_tool,
)

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
SharePicks = Annotated[
    bool,
    Field(
        description=(
            "True: this friend may see which places the person liked, and why. "
            "False: the person's opinions only count in anonymous totals. "
            "Tell the person what true means before you link them."
        ),
    ),
]

_BAD_CODE = "That friend code does not look right. A friend code looks like 'k7m2-9xqd-4wte'."
_CIRCLE_CODE_HINT = "That is a circle code, not a friend code. Call join_circle with it."
_KEEP_THE_REF = (
    "Keep friend_ref in your notes next to the contact's name. "
    "Results name friends by friend_ref only. You turn it into the name."
)


def _clean_friend_code(code: str) -> str:
    clean = sanitize_friend_invite_code(code)
    if clean:
        return clean
    raise ValueError(_CIRCLE_CODE_HINT if sanitize_invite_code(code) else _BAD_CODE)


@mcp.tool(title="Invite a friend", annotations=WRITES)
@safe_tool
async def invite_friend(
    closeness: Closeness = 2,
    share_my_picks: SharePicks = True,
    taste_id: TasteId = None,
    dry_run: Annotated[
        bool,
        Field(description="Set true when you only test the connection. Nothing is stored."),
    ] = False,
) -> dict:
    """Link the person with one friend, so they each see where the other likes to eat.

    Use it for the people they message most. Call it once per friend: each code works once.
    Send share_text to that friend, and ask the person before you send any message for them.
    The server never learns who the friend is. You keep the name. It keeps the friend_ref.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    if dry_run:
        return {"success": True, "dry_run": True, "message": "Dry run. No invite was created."}

    invite_code = await friends.create_invite(token, closeness, share_my_picks)
    return {
        "success": True,
        "friend_ref": invite_code,
        "expires_in_days": get_settings().friend_invite_days,
        "share_text": (
            "I keep my favorite places to eat in Tastebuds. Link up with me "
            "and we each see where the other likes to eat. "
            f'Tell your assistant: "accept the Tastebuds friend invite {invite_code}". '
            f"No assistant set up yet? {public_base_url()}/?invite={invite_code}"
        ),
        "message": f"Send share_text to this one friend. {_KEEP_THE_REF}",
    }


@mcp.tool(title="Accept a friend invite", annotations=WRITES)
@safe_tool
async def accept_friend_invite(
    invite_code: FriendCode,
    closeness: Closeness = 2,
    share_my_picks: SharePicks = True,
    taste_id: TasteId = None,
) -> dict:
    """Accept a friend invite that someone sent to the person.

    Before you call it, tell the person in one sentence: the two of them will each see
    which places the other liked. Set closeness from the person's own side.
    The invite code becomes the friend_ref for this friend.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_friend_code(invite_code)
    await friends.accept_invite(token, code, closeness, share_my_picks)
    return {
        "success": True,
        "friend_ref": code,
        "message": f"Linked. Their picks now shape this person's recommendations. {_KEEP_THE_REF}",
    }


@mcp.tool(title="Update a friend link", annotations=WRITES)
@safe_tool
async def update_friend(
    friend_ref: FriendCode,
    closeness: Annotated[
        int | None,
        Field(description="New closeness from 1 to 3, when their messaging habits changed.", ge=1, le=3),
    ] = None,
    share_my_picks: Annotated[
        bool | None,
        Field(description="Change whether this friend may see the person's picks."),
    ] = None,
    remove: Annotated[
        bool,
        Field(description="Set true to end the link. It ends for both people."),
    ] = False,
    taste_id: TasteId = None,
) -> dict:
    """Change how much one friend's taste counts, stop sharing picks with them, or end the link.

    Review closeness now and then: people drift apart and grow close.
    get_taste_profile lists the person's friends with their friend_ref and closeness.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    code = _clean_friend_code(friend_ref)
    if remove:
        done = await friends.remove_friend(token, code)
        return _update_result(done, "The link is gone for both people.")
    if closeness is None and share_my_picks is None:
        raise ValueError("Pass closeness, share_my_picks, or remove=true.")

    done = True
    if closeness is not None:
        done = await friends.set_closeness(token, code, closeness)
    if done and share_my_picks is not None:
        done = await friends.set_sharing(token, code, share_my_picks)
    return _update_result(done, "Friend link updated.")


def _update_result(done: bool, message: str) -> dict:
    if not done:
        return {"success": False, "message": "This person has no friend with that friend_ref."}
    return {"success": True, "message": message}


@mcp.tool(title="New finds from friends", annotations=WRITES)
@safe_tool
async def get_friend_finds(
    city: OptionalCity = None,
    taste_id: TasteId = None,
    peek: Annotated[
        bool,
        Field(description="Set true to look without marking anything as told. Use it for tests."),
    ] = False,
) -> dict:
    """Check in the background for new places the person's friends loved.

    Run it about once a week from a goal or a routine, never in the middle of a chat.
    Message the person only when worth_a_nudge is true, and send one short message.
    The server holds the bar: two friends loved a place, or one of their closest friends did,
    and the person got no nudge in the last week. A find that was told once never comes back.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    city = city or await profiles.get_home_city(token)
    if not city:
        raise ValueError(service.NO_CITY_MESSAGE)

    result = await friends.friend_finds(token, city, peek=peek)
    return result.model_dump()


@mcp.tool(title="Food board", annotations=READS)
@safe_tool
async def get_food_board(city: OptionalCity = None, taste_id: TasteId = None) -> dict:
    """Get one snapshot of the person's food world, shaped for a dashboard or an idea card.

    It holds their favorites, what their friends love, and places to try next.
    Use it when the person asks to see their places or their friends' places, and when
    you write food ideas for them. Build the view yourself. Fill in friend names from your notes.
    """
    token = resolve_taste_id(taste_id)
    if not token:
        raise ValueError(NEEDS_TASTE_ID)

    board = await service.food_board(token, city)
    return board.model_dump()
