"""Friends: one-to-one links weighted by closeness.

The agent sees who the person messages most and sends a closeness level from 1 to 3.
This module never sees a name, a number, or a message count.

Friends who agree can see which places each other liked, and why. The server returns
the friend_ref. The person's own agent turns it into a name from its private notes.
"""

import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from tastebuds.config import get_settings
from tastebuds.db.client import get_pool
from tastebuds.db.models import FriendFind, FriendFindsResult, FriendInfo, FriendOpinion
from tastebuds.identity import mint_friend_invite_code
from tastebuds.normalizer import normalize_city

_MAX_FRIENDS = 50
_MAX_PENDING_INVITES = 20
_INVITE_CODE_ATTEMPTS = 5
_MAX_FRIENDS_PER_PLACE = 3
_MAX_FINDS = 3
_MAX_DISHES_PER_OPINION = 3

_VERDICTS = {
    "positive": "loved it",
    "neutral": "found it just okay",
    "negative": "did not like it",
}
# Closeness 3, 2, 1 as a weight. The ranking uses the same numbers.
_CLOSENESS_WEIGHT_SQL = "CASE ft.closeness WHEN 3 THEN 2.0 WHEN 2 THEN 1.0 ELSE 0.5 END"


class FriendError(ValueError):
    """The friend request cannot be done. The message is safe to show to the agent."""


@dataclass
class FoundPlace:
    """A place friends like, before it becomes a response model."""

    place_id: UUID
    name: str
    city: str
    neighborhood: str | None
    cuisine_tags: list[str]
    friend_count: int
    closest: int


async def create_invite(taste_id: str, closeness: int, shares_picks: bool = True) -> str:
    """Create a single-use invite for one friend. Returns the invite code."""
    pool = await get_pool()
    settings = get_settings()

    friends = await pool.fetchval("SELECT COUNT(*) FROM friend_ties WHERE taste_id = $1", taste_id)
    if friends >= _MAX_FRIENDS:
        raise FriendError("This person already has the maximum number of friends.")

    pending = await pool.fetchval(
        """
        SELECT COUNT(*) FROM friend_invites
        WHERE inviter_taste_id = $1 AND accepted_at IS NULL AND expires_at > now()
        """,
        taste_id,
    )
    if pending >= _MAX_PENDING_INVITES:
        raise FriendError("Too many open invites. Wait for friends to accept some first.")

    for _attempt in range(_INVITE_CODE_ATTEMPTS):
        invite_code = mint_friend_invite_code()
        created = await pool.fetchval(
            """
            INSERT INTO friend_invites (
                invite_code, inviter_taste_id, inviter_closeness, inviter_shares_picks, expires_at
            )
            VALUES ($1, $2, $3, $4, now() + MAKE_INTERVAL(days := $5))
            ON CONFLICT (invite_code) DO NOTHING
            RETURNING invite_code
            """,
            invite_code,
            taste_id,
            closeness,
            shares_picks,
            settings.friend_invite_days,
        )
        if created:
            return created
    raise RuntimeError("Could not mint a unique friend invite code")


async def accept_invite(
    taste_id: str,
    invite_code: str,
    closeness: int,
    shares_picks: bool = True,
) -> int:
    """Link two people. Each side keeps its own closeness and its own choice to share picks.

    Returns the accepter's friend count.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            invite = await conn.fetchrow(
                "SELECT * FROM friend_invites WHERE invite_code = $1 FOR UPDATE",
                invite_code,
            )
            if invite is None:
                raise FriendError("No invite matches that code. Check the code with your friend.")
            if invite["inviter_taste_id"] == taste_id:
                raise FriendError("This is the person's own invite. A friend has to accept it.")
            if invite["accepted_at"] is not None:
                raise FriendError("That invite was already used. Ask your friend for a new one.")
            expired = await conn.fetchval("SELECT $1::TIMESTAMPTZ < now()", invite["expires_at"])
            if expired:
                raise FriendError("That invite expired. Ask your friend for a new one.")

            friends = await conn.fetchval(
                "SELECT COUNT(*) FROM friend_ties WHERE taste_id = $1",
                taste_id,
            )
            if friends >= _MAX_FRIENDS:
                raise FriendError("This person already has the maximum number of friends.")

            # Two rows, one per direction. Each row carries the friend's own choice to share.
            # A repeat link between the same two people takes the newer values:
            # the newest code is the one the agents remember.
            inviter = invite["inviter_taste_id"]
            await conn.executemany(
                """
                INSERT INTO friend_ties (
                    taste_id, friend_taste_id, closeness, friend_ref, friend_shares_picks
                )
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (taste_id, friend_taste_id)
                DO UPDATE SET
                    closeness = EXCLUDED.closeness,
                    friend_ref = EXCLUDED.friend_ref,
                    friend_shares_picks = EXCLUDED.friend_shares_picks,
                    updated_at = now()
                """,
                [
                    (inviter, taste_id, invite["inviter_closeness"], invite_code, shares_picks),
                    (taste_id, inviter, closeness, invite_code, invite["inviter_shares_picks"]),
                ],
            )
            await conn.execute(
                "UPDATE friend_invites SET accepted_at = now() WHERE invite_code = $1",
                invite_code,
            )
            return await conn.fetchval(
                "SELECT COUNT(*) FROM friend_ties WHERE taste_id = $1",
                taste_id,
            )


async def set_closeness(taste_id: str, friend_ref: str, closeness: int) -> bool:
    """Change how much one friend's taste counts. Return False when there is no such friend."""
    pool = await get_pool()
    updated = await pool.fetchval(
        """
        UPDATE friend_ties SET closeness = $3, updated_at = now()
        WHERE taste_id = $1 AND friend_ref = $2
        RETURNING 1
        """,
        taste_id,
        friend_ref,
        closeness,
    )
    return updated is not None


async def set_sharing(taste_id: str, friend_ref: str, shares_picks: bool) -> bool:
    """Change whether one friend may see this person's picks.

    The choice lives on the friend's row, because that row shapes what the friend sees.
    """
    pool = await get_pool()
    updated = await pool.fetchval(
        """
        UPDATE friend_ties SET friend_shares_picks = $3, updated_at = now()
        WHERE friend_taste_id = $1 AND friend_ref = $2
        RETURNING 1
        """,
        taste_id,
        friend_ref,
        shares_picks,
    )
    return updated is not None


async def remove_friend(taste_id: str, friend_ref: str) -> bool:
    """Unlink two people in both directions. Either side can end the link."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            friend_taste_id = await conn.fetchval(
                """
                DELETE FROM friend_ties WHERE taste_id = $1 AND friend_ref = $2
                RETURNING friend_taste_id
                """,
                taste_id,
                friend_ref,
            )
            if friend_taste_id is None:
                return False
            await conn.execute(
                "DELETE FROM friend_ties WHERE taste_id = $1 AND friend_taste_id = $2",
                friend_taste_id,
                taste_id,
            )
    return True


async def list_friends(taste_id: str) -> list[FriendInfo]:
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT mine.friend_ref, mine.closeness,
            mine.friend_shares_picks AS they_share,
            COALESCE(theirs.friend_shares_picks, FALSE) AS i_share
        FROM friend_ties mine
        LEFT JOIN friend_ties theirs
            ON theirs.taste_id = mine.friend_taste_id AND theirs.friend_taste_id = mine.taste_id
        WHERE mine.taste_id = $1
        ORDER BY mine.closeness DESC, mine.created_at
        """,
        taste_id,
    )
    return [
        FriendInfo(
            friend_ref=row["friend_ref"],
            closeness=row["closeness"],
            they_share_picks=row["they_share"],
            you_share_picks=row["i_share"],
        )
        for row in rows
    ]


async def delete_all_for(conn: asyncpg.Connection, taste_id: str) -> None:
    """Remove every link and open invite of a person who asked to be forgotten."""
    await conn.execute(
        "DELETE FROM friend_ties WHERE taste_id = $1 OR friend_taste_id = $1",
        taste_id,
    )
    await conn.execute("DELETE FROM friend_invites WHERE inviter_taste_id = $1", taste_id)
    await conn.execute("DELETE FROM friend_find_events WHERE taste_id = $1", taste_id)


def _opinion_from_row(row: asyncpg.Record) -> FriendOpinion:
    dishes = json.loads(row["dishes"]) if isinstance(row["dishes"], str) else (row["dishes"] or [])
    loved = [dish["name"] for dish in dishes if dish.get("sentiment") == "positive"]
    skipped = [dish["name"] for dish in dishes if dish.get("sentiment") == "negative"]
    return FriendOpinion(
        friend_ref=row["friend_ref"],
        closeness=row["closeness"],
        verdict=_VERDICTS[row["sentiment"]],
        loved_dishes=loved[:_MAX_DISHES_PER_OPINION],
        skipped_dishes=skipped[:_MAX_DISHES_PER_OPINION],
        note=row["comment"],
        good_for=row["occasion"],
        days_ago=int(row["days_ago"]),
    )


async def friend_opinions(
    pool: asyncpg.Pool,
    taste_id: str | None,
    place_ids: list[UUID],
) -> dict[UUID, list[FriendOpinion]]:
    """What sharing friends think of these places. Closest friends first."""
    if not taste_id or not place_ids:
        return {}

    rows = await pool.fetch(
        """
        SELECT f.place_id, ft.friend_ref, ft.closeness, f.sentiment, f.dishes, f.comment,
            f.occasion, EXTRACT(EPOCH FROM (now() - f.created_at)) / 86400.0 AS days_ago
        FROM friend_ties ft
        JOIN feedback f ON f.taste_id = ft.friend_taste_id AND f.superseded_at IS NULL
        WHERE ft.taste_id = $1
          AND ft.friend_shares_picks
          AND f.place_id = ANY($2::UUID[])
        ORDER BY ft.closeness DESC, f.created_at DESC
        """,
        taste_id,
        place_ids,
    )
    opinions: dict[UUID, list[FriendOpinion]] = {}
    for row in rows:
        per_place = opinions.setdefault(row["place_id"], [])
        if len(per_place) < _MAX_FRIENDS_PER_PLACE:
            per_place.append(_opinion_from_row(row))
    return opinions


async def places_friends_love(
    pool: asyncpg.Pool,
    taste_id: str,
    city_norm: str,
    *,
    fresh_days: int | None,
    skip_already_told: bool,
    limit: int,
) -> list[FoundPlace]:
    """Places that sharing friends loved and this person has no opinion on yet."""
    rows = await pool.fetch(
        f"""
        SELECT p.id, p.canonical_name, p.city, p.neighborhood, p.cuisine_tags,
            COUNT(*) AS friend_count,
            MAX(ft.closeness) AS closest,
            SUM({_CLOSENESS_WEIGHT_SQL}) AS weight,
            MAX(f.created_at) AS latest
        FROM friend_ties ft
        JOIN feedback f
            ON f.taste_id = ft.friend_taste_id
            AND f.superseded_at IS NULL
            AND f.sentiment = 'positive'
        JOIN places p ON p.id = f.place_id
        WHERE ft.taste_id = $1
          AND ft.friend_shares_picks
          AND p.city = $2
          AND ($3::INTEGER IS NULL OR f.created_at > now() - MAKE_INTERVAL(days := $3))
          AND NOT EXISTS (
              SELECT 1 FROM feedback own
              WHERE own.taste_id = $1 AND own.place_id = p.id AND own.superseded_at IS NULL
          )
          AND (
              NOT $4::BOOLEAN
              OR NOT EXISTS (
                  SELECT 1 FROM friend_find_events told
                  WHERE told.taste_id = $1 AND told.place_id = p.id
              )
          )
        GROUP BY p.id
        ORDER BY weight DESC, latest DESC
        LIMIT $5
        """,
        taste_id,
        city_norm,
        fresh_days,
        skip_already_told,
        limit,
    )
    return [
        FoundPlace(
            place_id=row["id"],
            name=row["canonical_name"],
            city=row["city"],
            neighborhood=row["neighborhood"],
            cuisine_tags=row["cuisine_tags"] or [],
            friend_count=row["friend_count"],
            closest=row["closest"],
        )
        for row in rows
    ]


async def friend_finds(taste_id: str, city: str, peek: bool = False) -> FriendFindsResult:
    """Fresh places that friends loved, for the agent's quiet background check.

    The server holds the bar for a message, so no agent can nag:
    - A find is worth a nudge when two friends loved it, or one of the closest friends did.
    - A person gets at most one nudge per cooldown.
    - A find that was told once never comes back.
    """
    pool = await get_pool()
    settings = get_settings()

    found = await places_friends_love(
        pool,
        taste_id,
        normalize_city(city),
        fresh_days=settings.friend_find_fresh_days,
        skip_already_told=True,
        limit=_MAX_FINDS,
    )
    opinions = await friend_opinions(pool, taste_id, [place.place_id for place in found])

    recently_nudged = await pool.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM friend_find_events
            WHERE taste_id = $1 AND nudged
              AND shown_at > now() - MAKE_INTERVAL(days := $2)
        )
        """,
        taste_id,
        settings.friend_nudge_cooldown_days,
    )
    strong = [place for place in found if place.friend_count >= 2 or place.closest == 3]
    worth_a_nudge = bool(strong) and not recently_nudged

    if worth_a_nudge and not peek:
        # Only the finds the person is told about count as told.
        found = strong
        await pool.executemany(
            """
            INSERT INTO friend_find_events (taste_id, place_id, nudged)
            VALUES ($1, $2, TRUE)
            ON CONFLICT (taste_id, place_id) DO NOTHING
            """,
            [(taste_id, place.place_id) for place in found],
        )

    finds = [
        FriendFind(
            name=place.name,
            city=place.city,
            neighborhood=place.neighborhood,
            cuisine_tags=place.cuisine_tags,
            friends=opinions.get(place.place_id, []),
        )
        for place in found
    ]

    if worth_a_nudge:
        message = (
            "Worth one short message. Name the friend from your notes and say what they loved. "
            "Send one message, not one per place. Then stay quiet about finds for a week."
        )
    elif finds:
        message = (
            "Nothing here is worth a message. Do not notify the person. "
            "Keep these for when they ask where to eat."
        )
    else:
        message = "No new finds from friends. Do not notify the person."
    return FriendFindsResult(finds=finds, worth_a_nudge=worth_a_nudge, message=message)
