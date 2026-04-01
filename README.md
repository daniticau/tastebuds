# Tastebuds

An invisible food recommendation engine, deployed as an [MCP](https://modelcontextprotocol.io) server.

People talk to their AI assistant about food. Tastebuds captures the signal — anonymously — and uses it to surface better recommendations over time. No reviews. No ratings. No UI. Just conversation.

## How it works

1. User asks "where should I eat?" — the assistant queries Tastebuds
2. Tastebuds returns ranked recommendations based on community sentiment
3. Later, user says "the ramen was incredible" — the assistant silently logs anonymous feedback
4. The collective knowledge grows with every conversation

See [VISION.md](VISION.md) for the full philosophy.

## MCP Tools

| Tool | Purpose |
|------|---------|
| `search_recommendations` | Find top-rated places by city, cuisine, neighborhood |
| `log_feedback` | Record anonymized dining feedback |
| `get_trending` | See what's buzzing recently |

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- PostgreSQL with `pg_trgm` extension
- A [Neon](https://neon.com/) Postgres database
- A [Railway](https://railway.com/) project for hosting the MCP server

### Install

```bash
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env with your Neon connection string
```

Use your Neon connection string in `TASTEBUDS_DATABASE_URL`. Neon requires SSL, so keep the query parameters Neon gives you, such as `sslmode=require` and `channel_binding=require`.

### Run migrations

```bash
psql $TASTEBUDS_DATABASE_URL -f migrations/001_initial.sql
psql $TASTEBUDS_DATABASE_URL -f migrations/002_taste_affinity.sql
psql $TASTEBUDS_DATABASE_URL -f migrations/003_places_uniqueness.sql
```

### Seed (optional)

```bash
python -m scripts.seed
```

### Run

```bash
uvicorn tastebuds.main:app --reload
```

### Test

```bash
pytest
```

## Deploy

Configured for [Railway](https://railway.com/) via [railway.json](C:\Users\danit\dev\tastebuds\railway.json) and the root [Dockerfile](C:\Users\danit\dev\tastebuds\Dockerfile).

Deployment flow:

1. Create a Neon project and copy the connection string.
2. In Railway, create a service from this GitHub repo.
3. Set `TASTEBUDS_DATABASE_URL` to the Neon connection string.
4. Set `FASTMCP_STATELESS_HTTP=true`.
5. In Railway service settings, ensure the public domain is enabled.
6. Railway runs `python -m tastebuds.db.migrate` before each deploy, so pending SQL migrations are applied automatically.
7. Use `https://<your-railway-domain>/mcp` as the MCP server URL.

## Architecture

- **Server**: FastAPI + [FastMCP](https://github.com/jlowin/fastmcp) v3, mounted at `/mcp`
- **Database**: Neon PostgreSQL with `pg_trgm` for fuzzy name matching
- **Deploy**: Railway via Dockerfile + `railway.json`
- **Privacy**: Fully anonymized — no user IDs, no PII, only aggregate sentiment
- **Ranking**: Weighted by sentiment, review volume, and recency

See [CLAUDE.md](CLAUDE.md) for detailed architecture notes.
