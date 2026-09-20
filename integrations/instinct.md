# Tastebuds on Instinct

Instinct is invite-only and publishes no developer docs. What is public: it
lives in iMessage, it runs a persistent cloud computer with a browser, it keeps
credentials, and it follows up on its own. It uses a computer the way a person
does. So Tastebuds gives it a page to read instead of a settings screen.

## The message to send

```text
Set up Tastebuds for me. Read https://tastebuds-production.up.railway.app/llms.txt
and follow it. Use it from now on whenever I talk about food.
```

## What Instinct finds at /llms.txt

- The MCP URL, if Instinct can use MCP servers.
- A REST API for the same tools: `POST /api/v1/<tool_name>` with a JSON body.
  One `curl` from its cloud computer is enough.
- The OpenAPI document at `/openapi.json`.
- The full playbook: identity, the one onboarding question, how to recommend,
  how to log feedback silently, follow-ups, circles, and the rules.

The REST bridge runs the MCP tools themselves. The two surfaces cannot drift apart.

## Friends

Instinct lives in iMessage, so it can see who the person texts most. The playbook
tells it to offer friend links once and to set closeness from 1 to 3 by that activity.
It sends the invite text as an iMessage after the person agrees.

## Unknowns to verify with a real account

- Whether Instinct supports MCP servers directly. If it does, use the MCP URL
  and skip REST.
- Where Instinct keeps long-term notes. The `taste_id` must survive between
  conversations. If it gets lost, `start_taste_profile` makes a new one, but the
  person's history stays with the old token.
