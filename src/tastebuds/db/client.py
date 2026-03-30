import asyncio
import logging

import asyncpg

from tastebuds.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_MAX_CONNECT_ATTEMPTS = 3
_POOL_MIN_SIZE = 1
_POOL_MAX_SIZE = 10


async def init_db_pool() -> None:
    """Initialize the asyncpg connection pool with retry for cold starts."""
    global _pool
    dsn = get_settings().database_url
    for attempt in range(_MAX_CONNECT_ATTEMPTS):
        try:
            _pool = await asyncpg.create_pool(
                dsn=dsn,
                min_size=_POOL_MIN_SIZE,
                max_size=_POOL_MAX_SIZE,
            )
            return
        except (OSError, asyncpg.PostgresError) as exc:
            if attempt < _MAX_CONNECT_ATTEMPTS - 1:
                wait = 2 ** attempt
                logger.warning(
                    "DB connect attempt %d failed, retrying in %ds: %s",
                    attempt + 1,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
            else:
                raise


async def get_pool() -> asyncpg.Pool:
    """Get the active connection pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def close_db_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
