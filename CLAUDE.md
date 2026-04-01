# Tastebuds

Invisible food recommendation engine, deployed as a Poke recipe (MCP server).
Tastebuds is a black box — users never know it exists. See VISION.md for the philosophy.

## Architecture
- **Server**: Python FastAPI + FastMCP v3.x, mounted at `/mcp`
- **Database**: Neon PostgreSQL (pg_trgm for fuzzy name matching)
- **Deploy**: Railway via Dockerfile + railway.json

## Key Files
- `src/tastebuds/main.py` — FastAPI entry point, mounts MCP at `/mcp`
- `src/tastebuds/server.py` — FastMCP instance with server instructions
- `src/tastebuds/tools/` — MCP tools (search, feedback, trending)
- `src/tastebuds/db/queries.py` — All SQL queries (asyncpg)
- `src/tastebuds/normalizer.py` — Place name normalization + dedup
- `migrations/001_initial.sql` — Database schema
- `migrations/002_taste_affinity.sql` — Adds taste_id for collaborative filtering

## Commands
- `uv sync` — install dependencies
- `uvicorn tastebuds.main:app --reload` — run dev server
- `pytest` — run tests

## Design Decisions
- All data anonymized — no user IDs, only anonymous taste tokens
- Precomputed aggregates on `places` table (reads never touch `feedback`)
- pg_trgm fuzzy matching for place name dedup (not pgvector)
- asyncpg connection to Neon via `TASTEBUDS_DATABASE_URL`
- Three separate MCP tools, not one omnibus tool

## Ranking Algorithm
- **Base score**: avg_rating * ln(review_count) * recency_decay
- **Taste affinity**: When a taste_id is provided, the base score is multiplied by
  `(1 + affinity_boost)` where boost is clamped to [-0.3, +0.5]. Affinity is computed
  on-the-fly via SQL CTEs — finds other taste_ids that overlap on 2+ places, measures
  agreement rate, then weights their sentiment on the candidate place.
