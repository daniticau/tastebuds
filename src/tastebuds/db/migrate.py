from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg

from tastebuds.config import get_settings

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "migrations"


def get_migration_files() -> list[Path]:
    """Return migration files in lexicographic order."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Create the migrations bookkeeping table if it does not exist."""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
    )


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(
        await conn.fetchval("SELECT to_regclass($1)", table_name),
    )


async def _column_exists(
    conn: asyncpg.Connection,
    table_name: str,
    column_name: str,
) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
              AND column_name = $2
            """,
            table_name,
            column_name,
        ),
    )


async def _index_exists(conn: asyncpg.Connection, index_name: str) -> bool:
    return bool(
        await conn.fetchval(
            "SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = $1",
            index_name,
        ),
    )


async def migration_already_reflected(
    conn: asyncpg.Connection,
    migration_name: str,
) -> bool:
    """Detect whether a legacy manual migration is already present in schema state."""
    if migration_name == "001_initial.sql":
        return await _table_exists(conn, "places") and await _table_exists(conn, "feedback")

    if migration_name == "002_taste_affinity.sql":
        return await _column_exists(conn, "feedback", "taste_id")

    if migration_name == "003_places_uniqueness.sql":
        return await _index_exists(conn, "idx_places_city_name_normalized_unique")

    return False


async def apply_migrations() -> list[str]:
    """Apply pending SQL migrations exactly once."""
    conn = await asyncpg.connect(dsn=get_settings().database_url)
    applied: list[str] = []
    backfilled: list[str] = []

    try:
        await ensure_migrations_table(conn)

        for migration_path in get_migration_files():
            already_applied = await conn.fetchval(
                "SELECT 1 FROM schema_migrations WHERE filename = $1",
                migration_path.name,
            )
            if already_applied:
                continue

            if await migration_already_reflected(conn, migration_path.name):
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)",
                    migration_path.name,
                )
                backfilled.append(migration_path.name)
                continue

            sql = migration_path.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)",
                    migration_path.name,
                )

            applied.append(migration_path.name)
    finally:
        await conn.close()

    return backfilled + applied


async def _main() -> None:
    applied = await apply_migrations()
    if applied:
        print("Applied migrations:")
        for migration in applied:
            print(f"- {migration}")
        return

    print("No pending migrations.")


if __name__ == "__main__":
    asyncio.run(_main())
