# Tastebuds on Poke

Poke was the first home of Tastebuds. Poke reads the MCP server instructions, so
the playbook reaches it without extra work.

## Connect

In Poke: Settings, then Connections, then add an MCP integration.

- Name: `Tastebuds`
- MCP server URL: `https://tastebuds-production.up.railway.app/mcp`
- Auth: none

Or from a terminal:

```bash
npx poke@latest mcp add https://tastebuds-production.up.railway.app/mcp -n "Tastebuds"
```

## What Poke sends

Poke tries streamable HTTP first and falls back to SSE. It reads the MCP server
instructions, so the playbook reaches it directly. It uses tools only.

Poke adds `X-Poke-User-Id` to every request. Tastebuds does not use it as the
person's identity. Every integration the person installs sees that same id, so it
is not a secret, and anyone who held it could read the person's food profile.
Identity stays the taste token that only Poke and Tastebuds know. The header has one
job: fair rate limits. All Poke users arrive from a few addresses, so each user id
gets its own bucket. The id is hashed, kept in memory only, and never stored or logged.

## Recipe fields for Kitchen

- Name: `Tastebuds`
- Description: `Restaurant picks that fit your taste and get better each time you eat out.`
- `inputContext`:
  `I'll remember where you like to eat. Tell me a couple of spots you love and anything you don't eat.`
- `prefilledFirstText`:
  `I'm in San Diego. I love Tajima Ramen and Tacos El Gordo. I don't eat shellfish. Where should I go tonight?`
- Required integration: `Tastebuds`

Publish the recipe and share the `poke.com/r/...` link.

## Upgrade notes for the old recipe

The old recipe told Poke to invent a UUID for `taste_id`. Old UUID tokens still
work. New users get a server-minted token from `start_taste_profile`. The three
old tool names did not change: `search_recommendations`, `log_feedback`, and
`get_trending`. `city` is now optional when the profile has a home city.

Poke docs: https://poke.com/docs/creating-recipes and
https://poke.com/docs/managing-integrations
