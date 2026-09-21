# Tastebuds on Instinct

Instinct is invite-only and publishes no developer docs. What is public: it
lives in iMessage and WhatsApp, it runs a persistent cloud computer with a
browser, it keeps credentials, and it follows up on its own. It has no settings
screen for MCP. The person texts one message that names the server.

## The message to send

```text
Add my Tastebuds connector: https://tastebuds-production.up.railway.app/mcp
(standard MCP over HTTP, no sign-in needed). When you test the tools, set
dry_run=true. Then call start_taste_profile for me and follow the playbook it
returns. If you cannot use MCP, read https://tastebuds-production.up.railway.app/llms.txt
and follow it.
```

## Why the server is built the way it is

| Instinct behavior | What Tastebuds does about it |
|---|---|
| It keeps one `Mcp-Session-Id` for every call. | The server is stateless. A session id from before a deploy still gets an answer, with no new `initialize`. |
| It writes its own client on its cloud computer. | The server forgives a bare `Accept: application/json`, a trailing slash, and loose input such as `"ramen, japanese"` for a list. Answers are plain JSON, not an event stream. |
| Connectors with OAuth need a sign-in link that the person approves. | Tastebuds needs no sign-in, so that step never happens. |
| It can fall back to a browser and a terminal. | `/llms.txt` explains a REST route: `POST /api/v1/<tool_name>`. It runs the same tools. |

## What Instinct finds at /llms.txt, if it cannot use MCP

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

- The exact setup phrasing. The message above follows the pattern that public
  connector guides use for Instinct.
- Where Instinct keeps long-term notes. The `taste_id` must survive between
  conversations. If it gets lost, `start_taste_profile` makes a new one, but the
  person's history stays with the old token.
