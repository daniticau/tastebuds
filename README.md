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
- PostgreSQL with `pg_trgm` extension ([Neon](https://neon.tech) recommended)

### Install

```bash
uv sync
```

### Configure

```bash
cp .env.example .env
# Edit .env with your database URL
```

### Run migrations

```bash
psql $TASTEBUDS_DATABASE_URL -f migrations/001_initial.sql
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

Configured for [Render](https://render.com) via `render.yaml`. Push to GitHub and connect the repo in Render — it picks up the config automatically.

## Architecture

- **Server**: FastAPI + [FastMCP](https://github.com/jlowin/fastmcp) v3, mounted at `/mcp`
- **Database**: Neon PostgreSQL with `pg_trgm` for fuzzy name matching
- **Privacy**: Fully anonymized — no user IDs, no PII, only aggregate sentiment
- **Ranking**: Weighted by sentiment, review volume, and recency

See [CLAUDE.md](CLAUDE.md) for detailed architecture notes.
