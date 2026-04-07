# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Invisible food recommendation engine, deployed as a Poke recipe (MCP server).
Tastebuds is a black box — users never know it exists. See VISION.md for the philosophy.

## Commands

```bash
uv sync                              # install dependencies
uv sync --extra dev                  # install with test dependencies
uvicorn tastebuds.main:app --reload  # run dev server
pytest                               # run all tests (integration tests skip without DB)
pytest tests/test_normalizer.py      # run a single test file
pytest tests/test_normalizer.py::TestNormalizeName::test_basic_lowercase  # single test
pytest -m integration                # run only integration tests (needs TASTEBUDS_DATABASE_URL)
python -m tastebuds.db.migrate       # apply pending SQL migrations
```

## Environment

- `TASTEBUDS_DATABASE_URL` — Neon PostgreSQL connection string (required for server and integration tests)
- All env vars are prefixed `TASTEBUDS_` (loaded by pydantic-settings from env or `.env`)
- Integration tests auto-skip when `TASTEBUDS_DATABASE_URL` is not set

## Architecture

- **Server**: Python 3.12, FastAPI + FastMCP v3.x, MCP mounted at `/mcp`
- **Database**: Neon PostgreSQL with `pg_trgm` for fuzzy name matching
- **Deploy**: Railway via Dockerfile + `railway.json`, pre-deploy runs migrations automatically

### Request flow

1. MCP client hits `/mcp/` → FastMCP routes to tool handler in `src/tastebuds/tools/`
2. Tool handler calls query functions in `src/tastebuds/db/queries.py`
3. Queries use the asyncpg connection pool from `src/tastebuds/db/client.py`
4. Health check at `/health` verifies DB connectivity

### Key modules

- `src/tastebuds/main.py` — FastAPI app, lifespans (DB pool + MCP), health endpoint
- `src/tastebuds/server.py` — FastMCP instance + server instructions (LLM behavioral prompt)
- `src/tastebuds/tools/` — Three MCP tools: `search_recommendations`, `log_feedback`, `get_trending`
- `src/tastebuds/db/queries.py` — All SQL (search ranking, find-or-create place, feedback, trending)
- `src/tastebuds/db/client.py` — asyncpg pool with retry logic and lazy init
- `src/tastebuds/db/migrate.py` — Migration runner with idempotent backfill detection
- `src/tastebuds/normalizer.py` — Place name and city normalization for dedup
- `src/tastebuds/config.py` — pydantic-settings `Settings` singleton
- `migrations/` — Sequential SQL migration files (001, 002, 003...)

### MCP tools (the three entry points)

| Tool | File | Purpose |
|------|------|---------|
| `search_recommendations` | `tools/search.py` | Ranked place search with optional taste affinity |
| `log_feedback` | `tools/feedback.py` | Record anonymized dining feedback, find-or-create place |
| `get_trending` | `tools/trending.py` | Recent buzz by feedback volume × sentiment |

### Data flow for feedback

`log_feedback` → `find_or_create_place` (exact match → fuzzy match → insert) → `insert_feedback` (insert row + atomically update place aggregates in one transaction)

Reads never touch the `feedback` table directly — `places` has precomputed aggregates (`positive_count`, `negative_count`, `neutral_count`, `avg_rating`).

## Design Decisions

- **Anonymity**: No user IDs, only anonymous taste tokens (UUIDs). The `_validation.py` module silently drops invalid taste IDs.
- **Place dedup**: Exact match on `(city, name_normalized)` first, then `pg_trgm` fuzzy match above configurable threshold (default 0.6). Not pgvector.
- **Ranking formula**: `avg_rating * ln(review_count) * recency_decay * (1 + affinity_boost)`. Affinity boost clamped to [-0.3, +0.5], computed via SQL CTEs from overlapping taste profiles.
- **Degraded mode**: App starts even if DB is unreachable (logs warning, `/health` returns 503).
- **Migrations**: Runner detects already-applied schema state (backfill), so it's safe against re-runs and legacy databases.
- **Stateless HTTP**: `FASTMCP_STATELESS_HTTP=true` in production (set in Dockerfile).

## Testing

- Unit tests (`test_normalizer.py`, `test_sentiment.py`, `test_migrate.py`, `test_smoke.py`) run without a database
- Integration tests (`test_integration.py`) are marked `@pytest.mark.integration` and auto-skip without `TASTEBUDS_DATABASE_URL`
- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests just work
- Smoke tests monkeypatch the DB pool to verify degraded-mode startup and lazy pool init
