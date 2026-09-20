"""Friends: one-to-one links weighted by closeness.

The agent sees who the person messages most and sends a closeness level from 1 to 3.
This module never sees a name, a number, or a message count.
"""

from tastebuds.config import get_settings
from tastebuds.db.client import get_pool
from tastebuds.db.models import FriendInfo
from tastebuds.identity import mint_friend_invite_code

_MAX_FRIENDS = 50
_MAX_PENDING_INVITES = 20
_INVITE_CODE_ATTEMPTS = 5


class FriendError(ValueError):
    """The friend request cannot be done. The message is safe to show to the agent."""


async def create_invite(taste_id: str, closeness: int) -> str:
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
            INSERT INTO friend_invites (invite_code, inviter_taste_id, inviter_closeness, expires_at)
            VALUES ($1, $2, $3, now() + MAKE_INTERVAL(days := $4))
            ON CONFLICT (invite_code) DO NOTHING
            RETURNING invite_code
            """,
            invite_code,
            taste_id,
            closeness,
            settings.friend_invite_days,
        )
        if created:
            return created
    raise RuntimeError("Could not mint a unique friend invite code")


async def accept_invite(taste_id: str, invite_code: str, closeness: int) -> int:
    """Link two people. Each side keeps its own closeness. Returns the accepter's friend count."""
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

            # Two rows, one per direction. A repeat link between the same two people
            # takes the newer code and closeness: the newest code is the one the agents remember.
            await conn.executemany(
                """
                INSERT INTO friend_ties (taste_id, friend_taste_id, closeness, friend_ref)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (taste_id, friend_taste_id)
                DO UPDATE SET
                    closeness = EXCLUDED.closeness,
                    friend_ref = EXCLUDED.friend_ref,
                    updated_at = now()
                """,
                [
                    (invite["inviter_taste_id"], taste_id, invite["inviter_closeness"], invite_code),
                    (taste_id, invite["inviter_taste_id"], closeness, invite_code),
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
        SELECT friend_ref, closeness FROM friend_ties
        WHERE taste_id = $1
        ORDER BY closeness DESC, created_at
        """,
        taste_id,
    )
    return [FriendInfo(friend_ref=row["friend_ref"], closeness=row["closeness"]) for row in rows]


async def delete_all_for(conn, taste_id: str) -> None:
    """Remove every link and open invite of a person who asked to be forgotten."""
    await conn.execute(
        "DELETE FROM friend_ties WHERE taste_id = $1 OR friend_taste_id = $1",
        taste_id,
    )
    await conn.execute("DELETE FROM friend_invites WHERE inviter_taste_id = $1", taste_id)
