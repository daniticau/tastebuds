# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A food memory and recommendation engine for personal AI agents. Muse is the main target. Instinct, Grok Bot, and Poke are secondary.
Assistants reach it over MCP or a REST bridge. It works in the background: the person rarely sees Tastebuds, and picks come with a friend's name.
See VISION.md for the philosophy, `integrations/muse.md` for how it lives in the Muse app, and `integrations/muse-submission.md` for Meta's connector form.

## Commands

```bash
uv sync                              # install dependencies
uv sync --extra dev                  # install with test dependencies
uvicorn tastebuds.main:app --reload  # run dev server
pytest                               # run all tests (integration tests skip without DB)
pytest tests/test_ranking.py         # run a single test file
pytest tests/test_ranking.py::TestQuality::test_one_rave_does_not_beat_a_proven_place  # single test
pytest -m integration                # run only integration tests (needs TASTEBUDS_DATABASE_URL)
python -m tastebuds.db.migrate       # apply pending SQL migrations
```

Local Postgres for integration tests (throwaway):

```bash
docker run -d --name tastebuds-dev-pg -e POSTGRES_PASSWORD=tastebuds -e POSTGRES_DB=tastebuds -p 127.0.0.1:55432:5432 postgres:16-alpine
export TASTEBUDS_DATABASE_URL=postgresql://postgres:tastebuds@127.0.0.1:55432/tastebuds
```

## Environment

- `TASTEBUDS_DATABASE_URL` — Neon PostgreSQL connection string (required for server and integration tests)
- `TASTEBUDS_PUBLIC_BASE_URL` — public origin; the landing page, `/llms.txt`, and friend invite links print it
- `TASTEBUDS_TYPESAFE_API_KEY` — optional; turns on Jev quick decisions. `python -m scripts.check_jev` tests the live connection.
- All env vars are prefixed `TASTEBUDS_` (loaded by pydantic-settings from env or `.env`). `config.py` lists every tunable: ranking prior, half-life, circle size, follow-up window, limits.
- Integration tests auto-skip when `TASTEBUDS_DATABASE_URL` is not set. Never point them at production: they write and delete rows.

## Architecture

- **Server**: Python 3.12, FastAPI + FastMCP v4.x
- **Database**: Neon PostgreSQL with `pg_trgm` for fuzzy name matching
- **Deploy**: Railway via Dockerfile + `railway.json`, pre-deploy runs migrations automatically

### Surfaces

| Route | What |
|---|---|
| `/mcp` and `/mcp/` | MCP over streamable HTTP. Stateless, plain JSON answers, any `Accept` header. Both paths answer without a redirect. |
| `POST /api/v1/<tool>` | REST bridge. Calls `mcp.call_tool`, so REST and MCP share tools and validation. |
| `/openapi.json` | Built at request time from the MCP tool schemas. |
| `/llms.txt` | Plain-text setup guide plus playbook, for agents that read pages. |
| `/` | Landing page for people. It speaks of "your agent", never of one platform. The platform buttons only pick the connect message. One self-contained file, `web/landing.html`. The look takes its feel from poke.com (paper, serif headline, tactile buttons, a text thread) with its own warm palette and inline SVG food drawings. The mark is a lip with the tongue out. The two shapes form a T. When the mark changes, raise the `?v=` number on the icon links, because the icon is cached for a day. Keep small captions rare: a heading should stand without a line of grey text under it. Fonts load from Google Fonts. |
| `/logos/<platform>.<svg,png,webp>` | Platform logos for the connect buttons, served from `web/logos/`. The site owner supplied the four files. Each logo belongs to its platform and is there only to name it. A platform with no file shows its first letter. |
| `/docs`, `/privacy`, `/terms`, `/icon.svg` | Pages the Muse connector form asks for. Content lives in `pages.py`, on the shared template `web/page.html`. |
| `/health` | DB connectivity check. Exempt from the rate limit. |

### Request flow

1. A tool call arrives by MCP or the REST bridge → handler in `src/tastebuds/tools/`
2. The handler resolves identity (`identity.resolve_taste_id`: explicit arg, then bearer token) and calls `service.py`
3. `service.py` normalizes and scrubs input, then calls `db/queries.py` and `db/profiles.py`
4. Search: SQL gathers candidates and signals, `ranking.py` scores them in pure Python

### Key modules

- `main.py` — app factory `create_app()`, REST bridge, OpenAPI, landing page, `/llms.txt`, health
- `server.py` — FastMCP instance; instructions come from `playbook.py`
- `playbook.py` — every word agents read: playbook, connect messages, `/llms.txt`. One source, three outlets.
- `tools/` — thin MCP wrappers. `_common.py` holds shared param types and `safe_tool` (errors → short agent-safe messages)
- `service.py` — orchestration: onboarding, recommend, record feedback, input cleaning
- `ranking.py` — pure scoring functions and their constants. No DB. Unit-tested in `tests/test_ranking.py`.
- `db/queries.py` — places, feedback, candidate search SQL, trending
- `db/profiles.py` — taste profiles, circles, follow-ups, delete
- `db/friends.py` — one-to-one friend links: single-use invites, directional closeness (1-3), each side's choice to share picks, friend opinions per place, friends' finds with the nudge bar
- `pages.py` — privacy, terms, docs, and the icon. Every privacy claim must match the code. Change the page in the same commit as the behavior.
- `decisions.py` — Jev (TypeSafe AI) client over plain `httpx`: same-place check, cuisine of a new place, optional comment check. Every function returns None when Jev is off or fails.
- `identity.py` — mint and validate taste tokens (`tb_` + 20 base32 chars; legacy UUIDs still valid), circle codes (two groups), and friend codes (three groups, so the two never mix)
- `taxonomy.py` — cuisine synonyms and parents, dietary and occasion vocab, cuisine inference from place names
- `privacy.py` — scrubs emails, phones, links, handles from free text
- `normalizer.py` — place, city, dish normalization; `is_generic_name` rejects "that thai place"
- `ratelimit.py` — ASGI rate limit keyed by `X-Real-IP`, then the last `X-Forwarded-For` hop (the one the proxy appends). A hashed `X-Poke-User-Id` gives each Poke user a bucket; a tenfold per-address cap stops faked ids.
- `migrations/` — sequential SQL files. `migrate.py` backfill detection only covers 001-003.

### Data flow for feedback

`log_feedback` → `service.record_feedback` → `find_or_create_place` (exact → strong fuzzy ≥ 0.85 → Jev in the gray zone 0.25-0.85 → fixed 0.6 rule when Jev gives no answer → insert; every mention can enrich the place) → `insert_feedback` in one transaction: lock place row, per-token daily limit, supersede the person's older opinion, insert, update aggregates, upsert `place_tags` and `place_dishes`, resolve follow-ups.

`places` holds precomputed aggregates. They count **active** opinions only (`feedback.superseded_at IS NULL`).

## Design Decisions

- **Anonymity**: the only key for a person is the taste token. The server mints it; agents store it. Any well-formed token is valid, and it grants nothing but access to its own profile.
- **Background first**: the person should rarely see Tastebuds. Three layers, from silent to visible: better picks in chat, a rare nudge from `get_friend_finds`, and a food board on request. Do not add features that make the agent talk about Tastebuds more.
- **A friend's name carries the pick**: agents lead with a linked friend ("Maya loved the spicy miso there"). They credit Tastebuds at most once per conversation, and only for places the engine returned. They do not recite counts or scores, and feedback logging stays silent. The rule lives in the playbook and in the `agent_note` of each result. Agents answer plainly when the person asks what is remembered.
- **The nudge bar lives on the server**: `get_friend_finds` decides `worth_a_nudge` (two friends, or one closest friend), allows one nudge per `friend_nudge_cooldown_days`, and tells each find once. Never move that decision to the agent.
- **One person, one opinion per place**: a new opinion supersedes the old row. History stays; the vote is replaced. This is the main defense against ballot stuffing.
- **Agents test tools on setup** (Muse calls every tool): writes take `dry_run`, delete needs `confirm=true`. Keep this for any new write tool.
- **Behavior text must survive any client**: some agents ignore MCP `instructions`. So the playbook also returns from `start_taste_profile`, and tool descriptions carry the key rules.
- **Place dedup**: exact match on `(city, name_normalized)`, then `pg_trgm` above a threshold (default 0.6). Test data needs clearly different names or the fuzzy matcher merges them.
- **Ranking**: `quality × confidence × freshness × (1 + personal_fit)`; see the docstring in `ranking.py`. Bayesian prior keeps one rave from winning. Neighborhood is a boost, not a filter, because data is sparse.
- **Cuisine search**: a broad term matches its children at query time ("japanese" finds "ramen"). Places also store parent tags at write time.
- **Friends**: the agent derives closeness from messaging activity (Instagram and WhatsApp on Muse, iMessage elsewhere) and sends only a level from 1 to 3. Never add fields for names, handles, phone numbers, hashes of them, or message counts. Each direction has its own closeness. Friend weight in ranking (0.6) is the largest personal signal.
- **Friends you can see, names you cannot**: a linked friend who shares picks (`friend_ties.friend_shares_picks`) appears in results by `friend_ref`, with verdict, dishes, and comment. The agent turns the code into a name from its own notes. The server must never store a name or a label for a friend. Sharing is each side's own choice, asked at link time, and links made before migration 006 default to not sharing. A friend who does not share counts only in totals, and only with `friend_min_ties` (2) friends.
- **Circles**: signals only show when the circle has `circle_min_members` (3) or more. Counts only.
- **Jev is optional and never blocking**: one request, no retry, 1.5 s timeout, any failure → None → fixed rule. Tests use `httpx.MockTransport`; the wire format comes from docs.typesafe.ai and was not checked against the live API. The comment check is off by default because it sends comment text to a third party.
- **Degraded mode**: app starts even if DB is unreachable (logs warning, `/health` returns 503).
- **Stateless, plain JSON MCP**: set in code in `create_app()` (`stateless_http=True, json_response=True`), not by env var. Instinct keeps one `Mcp-Session-Id` forever, and a stateful server would answer 404 to it after every deploy. Do not make the endpoint stateful.
- **Forgive hand-written clients**: `McpClientToleranceMiddleware` rewrites the `Accept` header and the trailing slash. Tool inputs accept `"a, b"` for a list and `"Tajima"` for `{"name": "Tajima"}` through `BeforeValidator`, while the advertised schema stays simple: no `$ref`, no unions inside arrays.
- **Tool hints**: every tool has a title and annotations (`READS`, `WRITES`, `DELETES` in `tools/_common.py`). Platforms use them to decide when to ask the person first. Only `delete_taste_profile` is destructive. A wrong hint would make silent logging prompt the person.
- **Platform user headers are not identity**: `X-Poke-User-Id` reaches every integration a person installs, so it is not a secret. It feeds the rate limit only, hashed and in memory. Never store it or derive the taste token from it.
- **Locked builds**: the Dockerfile runs `uv sync --frozen`. Before this, the image installed the newest `fastmcp`, which jumped a major version past what the tests covered. Upgrade with `uv lock --upgrade-package`, run the suite, then deploy.

## Testing

- Unit tests run without a database: ranking, taxonomy, identity, privacy, profile merge, normalizer, Jev client (`test_decisions.py`), HTTP surface (`test_http.py` uses dry runs), smoke.
- Integration tests (`test_integration.py`) are marked `@pytest.mark.integration`. Each test gets a `world` fixture: one random city plus tokens, all deleted afterward.
- `pytest-asyncio` with `asyncio_mode = "auto"` — async tests just work
- `tests/test_connectors.py` starts the server as a subprocess and replays Muse, Instinct, Grok Bot, and Poke over real HTTP. Set `TASTEBUDS_TEST_SERVER_URL` to aim it at a running server such as the Docker image. When a platform's behavior changes, change its class there first.
- The MCP session manager runs once per app instance. Tests that need a running app call `create_app()`; do not reuse `main.app` across `TestClient` contexts.
