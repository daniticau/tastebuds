# Tastebuds

Good food recs from personal agents.

You text your AI assistant about food like you normally would. Tastebuds runs in the background: it remembers how you eat, learns from every meal you mention, and ranks places for you using what your friends and people with similar taste liked. There are no reviews, no ratings, and no app.

It works with Muse, Instinct, Grok Bot, Poke, or any MCP client.

## How it works

1. You send your assistant one message to connect. The landing page has the message.
2. The assistant asks for a couple of spots you love and anything you don't eat.
3. You ask "where should I eat?" and get picks ranked for you, with dishes to order, dishes to skip, and what your friends thought. For example: "Tajima Ramen. Maya loved the spicy miso there."
4. You mention how the meal went ("the broth was unreal"), and the assistant logs it quietly. The next pick gets better for everyone.

## Friends

Your assistant can link you with the people you message most. Closer friends count more: a best friend's opinion weighs four times a casual friend's. Linked friends can see which places each other liked, and either side can turn that off.

The server never sees names, phone numbers, or messages. Each friend is a random code, and your own assistant turns that code back into a name.

## Ranking

```
score = quality x confidence x freshness x (1 + personal fit)
```

- **Quality** is the share of good opinions, so one rave doesn't beat nine raves and one complaint.
- **Confidence** gives a small boost to places with more opinions.
- **Freshness** makes old praise count less, but never below 70%.
- **Personal fit** covers your friends, people with similar taste, cuisines you like or avoid, diet, occasion, vibe, neighborhood, price, and distance.

Each person gets one opinion per place, and a place you disliked never comes back. The ranking lives in [ranking.py](src/tastebuds/ranking.py).

## Privacy

- The only thing tied to you is a random `taste_id`.
- Personal details get stripped from comments twice, once by the assistant and once by the server.
- Friends see your places only if you share them. Group circles only show counts.
- `delete_taste_profile` deletes your profile, friend links, and circles. Your past opinions stay in the totals, but nothing links them to you.

## Running it locally

You need Python 3.12+, [uv](https://docs.astral.sh/uv/), and Postgres with `pg_trgm`. I use [Neon](https://neon.com/) in production.

```bash
uv sync --extra dev
cp .env.example .env    # set TASTEBUDS_DATABASE_URL
python -m tastebuds.db.migrate
uvicorn tastebuds.main:app --reload
```

`python -m scripts.seed` adds some San Diego places to start with.

The server exposes MCP at `/mcp`, a REST version of the same tools at `/api/v1/<tool_name>`, and setup docs for agents at `/llms.txt` and `/openapi.json`.

## Tests

```bash
pytest
```

The integration tests skip unless `TASTEBUDS_DATABASE_URL` is set. A throwaway Postgres works:

```bash
docker run -d --name tastebuds-dev-pg -e POSTGRES_PASSWORD=tastebuds -e POSTGRES_DB=tastebuds -p 127.0.0.1:55432:5432 postgres:16-alpine
export TASTEBUDS_DATABASE_URL=postgresql://postgres:tastebuds@127.0.0.1:55432/tastebuds
python -m tastebuds.db.migrate
pytest
```

`tests/test_connectors.py` replays how each assistant actually connects. Point it at a live server with `TASTEBUDS_TEST_SERVER_URL`.

## Optional: Jev

If you set `TASTEBUDS_TYPESAFE_API_KEY`, Tastebuds asks [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) for a few quick calls, like whether two place names are the same restaurant. Without a key, or if Jev is slow, it falls back to simple rules. Run `python -m scripts.check_jev` to test the connection.

## Deploying

It deploys to [Railway](https://railway.com/) from the [Dockerfile](Dockerfile), and Railway runs migrations before each deploy. Set `TASTEBUDS_DATABASE_URL`, then point a custom domain at the service.
