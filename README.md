# Tastebuds

A food memory and a crowd-taught recommendation engine for AI assistants.

People text their assistant about food. Tastebuds remembers how each person eats, learns from every meal they mention, and ranks places for them. All of it is anonymous. No reviews. No ratings. No app. See [VISION.md](VISION.md).

Built and tested for four personal agents: [Muse](integrations/muse.md), [Instinct](integrations/instinct.md), [Grok Bot](integrations/grokbot.md), and [Poke](integrations/poke.md). Any MCP client works.

## How it works

1. The person sends their assistant one message to connect. The landing page at `/` has the message.
2. The assistant asks one question: "What are a couple of spots you love, and is there anything you don't eat?" One `start_taste_profile` call stores the answer and returns an anonymous `taste_id`.
3. "Where should I eat?" The assistant calls `search_recommendations`. Results come ranked for this person, with dishes to order and dishes to skip. The assistant credits the pick: "Tastebuds recommends Tajima Ramen."
4. "The ramen was incredible." The assistant calls `log_feedback` silently. The next pick gets better for everyone.

## Three ways in

| Surface | URL | For |
|---|---|---|
| MCP (streamable HTTP, no auth) | `/mcp` | Muse, Instinct, Grok Bot, Poke, any MCP client |
| REST bridge | `POST /api/v1/<tool_name>` | Agents with a computer and no MCP client |
| Agent guide and OpenAPI | `/llms.txt`, `/openapi.json` | Agents that read a page to set themselves up |

The REST bridge runs the MCP tools themselves, so the surfaces cannot drift apart.

## Tools

| Tool | Purpose |
|------|---------|
| `start_taste_profile` | Onboard a person in one call. Returns the `taste_id` and the playbook. |
| `search_recommendations` | Ranked places. Filters: cuisine, neighborhood, occasion, vibes, price, location, `similar_to`, `place_name`. |
| `log_feedback` | One opinion about one real meal: sentiment, dishes, occasion, price, vibes, dietary fit. |
| `get_trending` | Places with the most good opinions lately. |
| `get_taste_profile` / `update_taste_profile` | Read and change what the engine remembers. |
| `delete_taste_profile` | Forget a person. Needs `confirm=true`. |
| `get_follow_ups` | Recommended places the person never reported on. |
| `invite_friend` / `accept_friend_invite` / `update_friend` | One-to-one links with the people they message most. Closeness from 1 to 3 sets how much a friend's taste counts. |
| `create_circle` / `join_circle` / `leave_circle` | Named groups that shape each other's picks. Counts only, never names. |

## Ranking

`score = quality x confidence x freshness x (1 + personal fit)`

- **Quality**: share of good opinions, pulled toward a prior when opinions are few. One rave does not beat nine raves and one complaint.
- **Confidence**: a small bonus for volume.
- **Freshness**: old praise counts less, but never less than 70%.
- **Personal fit**: friends weighted by closeness, taste neighbors, circle, liked and disliked cuisines, cuisines learned from history, dietary fit, occasion, vibe, neighborhood, price, and distance.

One person holds one opinion per place. A new opinion replaces the old one. A place the person disliked never comes back. The ranking is pure Python in [ranking.py](src/tastebuds/ranking.py) and has its own unit tests.

## Connector compatibility

Each platform talks to an MCP server in its own way. `tests/test_connectors.py` starts the real server and replays each one over real HTTP:

| Platform | How it connects | What the tests replay |
|---|---|---|
| Muse | Writes a client with the official MCP SDK, tests every tool, saves a skill | The SDK client calls all 14 tools once. Every call comes back clean and stores nothing. |
| Instinct | One text names the server. Keeps one `Mcp-Session-Id` for all calls | A stale session id with no new `initialize`, a bare `Accept` header, loose input, and the REST route |
| Grok Bot | A name, a URL, optional headers. Probes for OAuth | OAuth probes get 404, no credential challenge, junk headers ignored, old and future protocol versions |
| Poke | Streamable HTTP, `X-Poke-User-Id` on every request, reads instructions | The playbook arrives as instructions, the user id never comes back, the first recipe's calls still work |

The MCP endpoint is stateless and answers in plain JSON, so a deploy never breaks a client that holds an old session. Tool hints mark reads, writes, and the one delete, so platforms keep silent logging silent.

Aim the same tests at any running server, such as the production image or a staging deploy:

```bash
TASTEBUDS_TEST_SERVER_URL=https://tastebuds-production.up.railway.app pytest tests/test_connectors.py
```

Against production this is safe: every write is a dry run, except the one full conversation, which cleans up after itself and only runs when `TASTEBUDS_DATABASE_URL` is set.

## Friends and closeness

The assistant sees who the person messages most: Instagram and WhatsApp on Muse, iMessage on Instinct and Poke. An assistant with no view of messages, such as Grok Bot, asks who they eat out with most. It offers once to link those friends. Each link starts with a one-time invite code that the assistant sends to the friend. The assistant then sends a closeness level: 3 for the few people they message most, 2 for often, 1 for now and then. A level 3 friend's opinion weighs four times a level 1 friend's.

The server stores two tokens and a level. It never sees names, numbers, handles, or message counts. Tastebuds does not match contacts by hashed phone numbers, because such hashes are easy to reverse. Friend signals stay off until two friends have joined.

## Quick decisions with Jev

[Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) is a System One model from TypeSafe AI. It answers typed questions in about 100 ms and writes no text. Tastebuds asks it where a fixed rule is too blunt:

| Decision | Without Jev | With Jev |
|---|---|---|
| Same restaurant? | Trigram similarity above 0.6 merges, then a short-form rule: "Nonna Pia" finds "Nonna Pia Trattoria" when only one place fits. "Pho Hoa" and "Pho Hoa Binh" (0.75) still merge. | Jev decides for name matches between 0.25 and 0.85. |
| Cuisine of a new place with no tags | Words in the name only | Jev picks from the cuisine list, using the name and the dishes mentioned |
| Comment identifies a private person? | Regex scrub for emails, phones, links, handles | Jev flags names and the comment is dropped. Off by default. |

Set `TASTEBUDS_TYPESAFE_API_KEY` to turn it on. With no key, a slow answer, or an error, the fixed rule applies, so Jev can never stop a request. Check the live connection with:

```bash
python -m scripts.check_jev
```

The comment check sends comment text to TypeSafe, so it has its own switch: `TASTEBUDS_JEV_CHECK_COMMENTS=true`. Read their data policy first.

## Setup

Prerequisites: Python 3.12+, [uv](https://docs.astral.sh/uv/), and PostgreSQL with the `pg_trgm` extension. Production uses [Neon](https://neon.com/).

```bash
uv sync --extra dev
```

```bash
cp .env.example .env
```

Put your connection string in `TASTEBUDS_DATABASE_URL`. Neon requires SSL, so keep the query parameters Neon gives you.

```bash
python -m tastebuds.db.migrate
```

```bash
uvicorn tastebuds.main:app --reload
```

Optional seed data for San Diego:

```bash
python -m scripts.seed
```

## Test

```bash
pytest
```

Integration tests skip when `TASTEBUDS_DATABASE_URL` is not set. For a full local run, use a throwaway Postgres:

```bash
docker run -d --name tastebuds-dev-pg -e POSTGRES_PASSWORD=tastebuds -e POSTGRES_DB=tastebuds -p 127.0.0.1:55432:5432 postgres:16-alpine
```

```bash
TASTEBUDS_DATABASE_URL=postgresql://postgres:tastebuds@127.0.0.1:55432/tastebuds python -m tastebuds.db.migrate
```

```bash
TASTEBUDS_DATABASE_URL=postgresql://postgres:tastebuds@127.0.0.1:55432/tastebuds pytest
```

## Deploy

Configured for [Railway](https://railway.com/) through [railway.json](railway.json) and the [Dockerfile](Dockerfile).

1. Create a Neon project and copy the connection string.
2. In Railway, create a service from this repo.
3. Set `TASTEBUDS_DATABASE_URL` to the Neon connection string.
4. Set `TASTEBUDS_PUBLIC_BASE_URL` to the public origin of the service. The landing page and `/llms.txt` print it.
5. Enable the public domain.

Railway runs `python -m tastebuds.db.migrate` before each deploy, so pending migrations apply on their own. The Docker image installs exactly what `uv.lock` pins, so production runs the versions the tests ran.

Live endpoints:

- Landing page: `https://tastebuds-production.up.railway.app/`
- MCP: `https://tastebuds-production.up.railway.app/mcp`
- Health: `https://tastebuds-production.up.railway.app/health`

## Privacy

- The only key for a person is a random `taste_id`. No names, phone numbers, emails, or messages.
- The assistant strips personal details from comments. The server scrubs emails, phone numbers, links, and handles again.
- Friend links hold two tokens and a closeness level from 1 to 3. No names, numbers, or message counts.
- Friend and circle signals show counts only. They stay silent under two friends or three circle members.
- With Jev on, place names, city, and dish names go to TypeSafe for matching. Comments go only when the comment check is on.
- `delete_taste_profile` removes the profile, friend links, circle memberships, and follow-ups. Past opinions stay in the totals with no link to anyone.

See [CLAUDE.md](CLAUDE.md) for architecture notes.
