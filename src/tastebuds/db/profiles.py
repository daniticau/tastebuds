"""Taste profiles, circles, and follow-ups. All keyed by the anonymous taste token."""

from dataclasses import dataclass, field

import asyncpg

from tastebuds.config import get_settings
from tastebuds.db import friends as friends_db
from tastebuds.db.client import get_pool
from tastebuds.db.models import (
    CircleInfo,
    FollowUp,
    FollowUpsResult,
    LearnedTaste,
    TasteProfile,
)
from tastebuds.identity import mint_invite_code
from tastebuds.normalizer import normalize_city
from tastebuds.ranking import TasteContext, learned_cuisine_affinity

_LIST_FIELDS = (
    "neighborhoods",
    "dietary",
    "allergies",
    "liked_cuisines",
    "disliked_cuisines",
    "vibes",
)
_MAX_LIST_ITEMS = 25
_MAX_CIRCLES_PER_TOKEN = 10
_HISTORY_LIMIT = 200
_INVITE_CODE_ATTEMPTS = 5
# A cuisine must clear this learned affinity before the profile calls it a favorite.
_TOP_CUISINE_THRESHOLD = 0.2


class CircleError(ValueError):
    """The circle request cannot be done. The message is safe to show to the agent."""


@dataclass
class ProfileChanges:
    """One update to a profile. Lists merge in. Scalars overwrite. Nothing else changes."""

    platform: str | None = None
    home_city: str | None = None
    neighborhoods: list[str] = field(default_factory=list)
    dietary: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    liked_cuisines: list[str] = field(default_factory=list)
    disliked_cuisines: list[str] = field(default_factory=list)
    vibes: list[str] = field(default_factory=list)
    budget: int | None = None
    spice_level: int | None = None
    notes: str | None = None
    # Values to take out of every list: the person is "not vegetarian anymore".
    remove: list[str] = field(default_factory=list)


def merge_list(current: list[str], added: list[str], removed: list[str]) -> list[str]:
    """Union in order, drop removed values, cap the size."""
    dropped = set(removed)
    merged: dict[str, None] = {}
    for value in [*current, *added]:
        if value and value not in dropped:
            merged.setdefault(value)
    return list(merged)[:_MAX_LIST_ITEMS]


def apply_changes(current: dict, changes: ProfileChanges) -> dict:
    """Compute the new profile row from the stored row and one update."""
    updated = dict(current)
    for name in _LIST_FIELDS:
        updated[name] = merge_list(current.get(name) or [], getattr(changes, name), changes.remove)

    # A cuisine cannot be both liked and disliked. The newest statement wins.
    newly_liked = set(changes.liked_cuisines)
    newly_disliked = set(changes.disliked_cuisines)
    updated["disliked_cuisines"] = [c for c in updated["disliked_cuisines"] if c not in newly_liked]
    updated["liked_cuisines"] = [
        c for c in updated["liked_cuisines"] if c not in newly_disliked or c in newly_liked
    ]

    if changes.home_city:
        updated["home_city"] = normalize_city(changes.home_city)
        updated["home_city_display"] = changes.home_city.strip()
    for name in ("platform", "budget", "spice_level", "notes"):
        value = getattr(changes, name)
        if value is not None:
            updated[name] = value
    return updated


async def upsert_profile(taste_id: str, changes: ProfileChanges) -> None:
    """Create the profile when it is new, then merge the changes in."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO taste_profiles (taste_id) VALUES ($1) ON CONFLICT DO NOTHING",
                taste_id,
            )
            current = await conn.fetchrow(
                "SELECT * FROM taste_profiles WHERE taste_id = $1 FOR UPDATE",
                taste_id,
            )
            updated = apply_changes(dict(current), changes)
            await conn.execute(
                """
                UPDATE taste_profiles SET
                    platform = $2, home_city = $3, home_city_display = $4,
                    neighborhoods = $5, dietary = $6, allergies = $7,
                    liked_cuisines = $8, disliked_cuisines = $9, vibes = $10,
                    budget = $11, spice_level = $12, notes = $13,
                    updated_at = now(), last_seen_at = now()
                WHERE taste_id = $1
                """,
                taste_id,
                updated["platform"],
                updated["home_city"],
                updated["home_city_display"],
                updated["neighborhoods"],
                updated["dietary"],
                updated["allergies"],
                updated["liked_cuisines"],
                updated["disliked_cuisines"],
                updated["vibes"],
                updated["budget"],
                updated["spice_level"],
                updated["notes"],
            )


async def _fetch_history(pool: asyncpg.Pool, taste_id: str) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT p.canonical_name, p.cuisine_tags, f.sentiment
        FROM feedback f
        JOIN places p ON p.id = f.place_id
        WHERE f.taste_id = $1 AND f.superseded_at IS NULL
        ORDER BY f.created_at DESC
        LIMIT $2
        """,
        taste_id,
        _HISTORY_LIMIT,
    )


async def _fetch_circles(pool: asyncpg.Pool, taste_id: str) -> list[CircleInfo]:
    rows = await pool.fetch(
        """
        SELECT c.name, c.invite_code,
            (SELECT COUNT(*) FROM circle_members x WHERE x.circle_id = c.id) AS member_count
        FROM circles c
        JOIN circle_members cm ON cm.circle_id = c.id
        WHERE cm.taste_id = $1
        ORDER BY cm.joined_at
        """,
        taste_id,
    )
    min_members = get_settings().circle_min_members
    return [
        CircleInfo(
            name=row["name"],
            invite_code=row["invite_code"],
            member_count=row["member_count"],
            active=row["member_count"] >= min_members,
        )
        for row in rows
    ]


async def load_taste_context(taste_id: str | None) -> TasteContext:
    """Load what the ranking needs to know about the person who asks."""
    if not taste_id:
        return TasteContext()

    pool = await get_pool()
    profile = await pool.fetchrow("SELECT * FROM taste_profiles WHERE taste_id = $1", taste_id)
    history = await _fetch_history(pool, taste_id)
    learned = learned_cuisine_affinity(
        [(row["cuisine_tags"] or [], row["sentiment"]) for row in history],
    )

    if profile is None:
        return TasteContext(learned_cuisines=learned)

    return TasteContext(
        dietary=profile["dietary"],
        liked_cuisines=profile["liked_cuisines"],
        disliked_cuisines=profile["disliked_cuisines"],
        vibes=profile["vibes"],
        budget=profile["budget"],
        learned_cuisines=learned,
    )


async def get_home_city(taste_id: str) -> str | None:
    pool = await get_pool()
    return await pool.fetchval(
        "SELECT home_city_display FROM taste_profiles WHERE taste_id = $1",
        taste_id,
    )


async def get_profile(taste_id: str) -> TasteProfile:
    """Everything the engine remembers about one person."""
    pool = await get_pool()
    row = await pool.fetchrow("SELECT * FROM taste_profiles WHERE taste_id = $1", taste_id)
    history = await _fetch_history(pool, taste_id)
    circles = await _fetch_circles(pool, taste_id)
    friends = await friends_db.list_friends(taste_id)
    friends_active = len(friends) >= get_settings().friend_min_ties

    affinity = learned_cuisine_affinity(
        [(entry["cuisine_tags"] or [], entry["sentiment"]) for entry in history],
    )
    top_cuisines = sorted(
        (tag for tag, value in affinity.items() if value >= _TOP_CUISINE_THRESHOLD),
        key=lambda tag: affinity[tag],
        reverse=True,
    )
    learned = LearnedTaste(
        opinion_count=len(history),
        top_cuisines=top_cuisines[:5],
        loved_places=[e["canonical_name"] for e in history if e["sentiment"] == "positive"][:10],
        avoided_places=[e["canonical_name"] for e in history if e["sentiment"] == "negative"][:10],
    )

    if row is None:
        return TasteProfile(
            taste_id=taste_id,
            exists=False,
            learned=learned,
            circles=circles,
            friends=friends,
            friend_signals_active=friends_active,
        )

    return TasteProfile(
        taste_id=taste_id,
        home_city=row["home_city_display"],
        neighborhoods=row["neighborhoods"],
        dietary=row["dietary"],
        allergies=row["allergies"],
        liked_cuisines=row["liked_cuisines"],
        disliked_cuisines=row["disliked_cuisines"],
        vibes=row["vibes"],
        budget=row["budget"],
        spice_level=row["spice_level"],
        notes=row["notes"],
        learned=learned,
        circles=circles,
        friends=friends,
        friend_signals_active=friends_active,
    )


async def delete_profile(taste_id: str) -> None:
    """Forget a person. Their past opinions stay in the totals, with no link to anyone."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM taste_profiles WHERE taste_id = $1", taste_id)
            await conn.execute("DELETE FROM circle_members WHERE taste_id = $1", taste_id)
            await friends_db.delete_all_for(conn, taste_id)
            await conn.execute("DELETE FROM recommendation_events WHERE taste_id = $1", taste_id)
            await conn.execute("UPDATE feedback SET taste_id = NULL WHERE taste_id = $1", taste_id)
            # A circle with no members has no way back in. Remove it.
            await conn.execute(
                """
                DELETE FROM circles c
                WHERE NOT EXISTS (SELECT 1 FROM circle_members cm WHERE cm.circle_id = c.id)
                """,
            )


async def create_circle(taste_id: str, name: str | None) -> CircleInfo:
    pool = await get_pool()
    joined = await pool.fetchval(
        "SELECT COUNT(*) FROM circle_members WHERE taste_id = $1",
        taste_id,
    )
    if joined >= _MAX_CIRCLES_PER_TOKEN:
        raise CircleError("This person is already in the maximum number of circles.")

    async with pool.acquire() as conn:
        async with conn.transaction():
            circle_id = None
            invite_code = ""
            for _attempt in range(_INVITE_CODE_ATTEMPTS):
                invite_code = mint_invite_code()
                circle_id = await conn.fetchval(
                    """
                    INSERT INTO circles (invite_code, name) VALUES ($1, $2)
                    ON CONFLICT (invite_code) DO NOTHING
                    RETURNING id
                    """,
                    invite_code,
                    name,
                )
                if circle_id:
                    break
            if circle_id is None:
                raise RuntimeError("Could not mint a unique circle invite code")

            await conn.execute(
                "INSERT INTO circle_members (circle_id, taste_id) VALUES ($1, $2)",
                circle_id,
                taste_id,
            )

    return CircleInfo(name=name, invite_code=invite_code, member_count=1, active=False)


async def join_circle(taste_id: str, invite_code: str) -> CircleInfo:
    pool = await get_pool()
    circle = await pool.fetchrow(
        "SELECT id, name, invite_code FROM circles WHERE invite_code = $1",
        invite_code,
    )
    if circle is None:
        raise CircleError("No circle matches that invite code. Check the code with your friend.")

    joined = await pool.fetchval(
        "SELECT COUNT(*) FROM circle_members WHERE taste_id = $1",
        taste_id,
    )
    if joined >= _MAX_CIRCLES_PER_TOKEN:
        raise CircleError("This person is already in the maximum number of circles.")

    await pool.execute(
        """
        INSERT INTO circle_members (circle_id, taste_id) VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        circle["id"],
        taste_id,
    )
    member_count = await pool.fetchval(
        "SELECT COUNT(*) FROM circle_members WHERE circle_id = $1",
        circle["id"],
    )
    return CircleInfo(
        name=circle["name"],
        invite_code=circle["invite_code"],
        member_count=member_count,
        active=member_count >= get_settings().circle_min_members,
    )


async def leave_circle(taste_id: str, invite_code: str) -> bool:
    """Leave a circle. Return False when the person was not a member."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            removed = await conn.fetchval(
                """
                DELETE FROM circle_members cm
                USING circles c
                WHERE c.id = cm.circle_id AND c.invite_code = $2 AND cm.taste_id = $1
                RETURNING c.id
                """,
                taste_id,
                invite_code,
            )
            if removed is None:
                return False
            await conn.execute(
                """
                DELETE FROM circles c
                WHERE c.id = $1
                  AND NOT EXISTS (SELECT 1 FROM circle_members cm WHERE cm.circle_id = c.id)
                """,
                removed,
            )
    return True


async def get_follow_ups(taste_id: str, limit: int = 2) -> FollowUpsResult:
    """Places the engine recommended a while ago that the person never reported on.

    Each place comes back once. After that the engine marks it as asked,
    so the agent does not nag.
    """
    pool = await get_pool()
    settings = get_settings()

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                """
                SELECT DISTINCT ON (e.place_id)
                    e.id, e.place_id, e.created_at, p.canonical_name, p.city
                FROM recommendation_events e
                JOIN places p ON p.id = e.place_id
                WHERE e.taste_id = $1
                  AND e.resolved_at IS NULL
                  AND e.followup_asked_at IS NULL
                  AND e.rank <= 2
                  AND e.created_at < now() - MAKE_INTERVAL(hours := $2)
                  AND e.created_at > now() - MAKE_INTERVAL(days := $3)
                  AND NOT EXISTS (
                      SELECT 1 FROM feedback f
                      WHERE f.taste_id = $1
                        AND f.place_id = e.place_id
                        AND f.created_at > e.created_at
                  )
                ORDER BY e.place_id, e.created_at DESC
                """,
                taste_id,
                settings.followup_min_age_hours,
                settings.followup_max_age_days,
            )
            due = sorted(rows, key=lambda row: row["created_at"], reverse=True)[:limit]
            await conn.execute(
                """
                UPDATE recommendation_events SET followup_asked_at = now()
                WHERE taste_id = $1 AND place_id = ANY($2::UUID[]) AND resolved_at IS NULL
                """,
                taste_id,
                [row["place_id"] for row in due],
            )
            now = await conn.fetchval("SELECT now()")

    follow_ups = [
        FollowUp(
            place_name=row["canonical_name"],
            city=row["city"],
            recommended_days_ago=(now - row["created_at"]).days,
        )
        for row in due
    ]
    if follow_ups:
        message = (
            "Ask casually if they went, one place at a time. "
            "If they share an opinion, call log_feedback. If they did not go, drop it."
        )
    else:
        message = "Nothing to follow up on."
    return FollowUpsResult(follow_ups=follow_ups, message=message)
