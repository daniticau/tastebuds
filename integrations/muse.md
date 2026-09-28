# Tastebuds on Muse

Muse is the main target. Everything else is secondary.

## Two ways onto Muse

| Path | Who can use it | Review | Status |
|---|---|---|---|
| Custom Connector | One person, on their own Muse | None | Works as soon as the server is live |
| Directory connector | Everyone, from Settings, then Connectors | Meta reviews it. Weeks, not days | Form answers are in [muse-submission.md](muse-submission.md) |

Meta opened the connector platform on September 18, 2026 at `muse.ai/platform`.
A directory connector is an existing MCP server or a raw API. Tastebuds is an MCP server.

## The message for a Custom Connector

```text
Create a Custom Connector for Tastebuds. Its MCP server is
https://<your-domain>/mcp with no sign-in, and its API docs are at
https://<your-domain>/llms.txt for you to read. When you test the tools,
set dry_run=true. Then call start_taste_profile for me and follow the
playbook it returns.
```

The landing page at `/` shows this message with a copy button. The message gives Muse
two entry points, the MCP server and the docs, because public sources disagree on which
one Muse prefers.

## Where Tastebuds lives in the Muse app

The person should rarely see Tastebuds. They should notice that the picks are good.
So the design has three layers, from silent to visible.

| Layer | Muse surface | How often | What happens |
|---|---|---|---|
| 1. Background | Chat | Every food question | Muse calls `search_recommendations` and `log_feedback`. It leads with a friend: "Maya loved the spicy miso there." It credits Tastebuds at most once per conversation. |
| 2. A quiet nudge | Goals, proactive message | About once a week at most | Under a goal, Muse calls `get_friend_finds`. It messages the person only when `worth_a_nudge` is true. |
| 3. On request | Ideas, dashboard | When the person asks | Muse calls `get_food_board` and builds a dashboard: favorites, friends' picks with names, places to try. |

### Why a connector cannot post to the Ideas tab

Muse writes the Ideas tab itself, from the person's goals, patterns, and chats. No connector
can put a card there. Tastebuds shapes what Muse writes in three ways:

- The playbook tells Muse to make food ideas concrete with `get_food_board`: a real place,
  a real friend, a real dish.
- The example prompts on the submission form show Muse what people ask for.
- A food goal gives Muse a reason to keep food ideas coming.

### The nudge bar lives on the server

Muse holds a high bar for messages that arrive out of turn. Tastebuds holds its own bar too,
so that no agent can nag:

- A find is worth a nudge when two friends loved the place, or one of the closest friends did.
- A person gets at most one nudge in six days.
- A find that was told once never comes back.

## Why the server is built the way it is

Each choice below answers one Muse behavior.

| Muse behavior | What Tastebuds does about it |
|---|---|
| Muse tests every tool during setup. | Every write tool that can succeed on made-up input takes `dry_run=true`. `get_friend_finds` takes `peek=true`. `delete_taste_profile` does nothing without `confirm=true`. `tests/test_connectors.py` replays this setup. |
| Muse splits actions into reads and writes. By default it asks the person before a write. | Every tool carries MCP hints. Lookups are reads, so they never prompt. The playbook tells Muse to explain the first write in one sentence. If the person picks "Always allow", logging stays quiet from then on. |
| A connector comes with a skill: instructions for how to use it well. | The playbook is that skill. It returns from `start_taste_profile`, as the MCP instructions, at `/llms.txt`, and on `/docs`. |
| Muse may skip the MCP `instructions` field. | Tool descriptions and tool results carry the key rules too. |
| Muse keeps memory and skill notes. | The server mints the `taste_id`. Muse stores it, and stores each `friend_ref` next to the friend's name. Tastebuds never learns a name. |
| Credentials stay in the person's VM. A separate process, Sentinel, decides what may happen. | No sign-in is needed. As an option, the `taste_id` can be stored as a bearer key. The server reads `Authorization: Bearer <taste_id>`. |
| Muse writes the client itself, so small protocol slips can happen. | Any `Accept` header works, answers are plain JSON, the server is stateless, and `/mcp/` works like `/mcp`. |
| Custom connectors use the same usage meter as everything else. | Responses stay small: at most 10 places, 3 dishes, 3 friends, and 2 notes per place. |
| Muse links Instagram, Facebook, and Threads through Accounts Center, and chats in WhatsApp. | The playbook tells Muse to set closeness from 1 to 3 by who the person messages most, and to send each invite over the channel the two friends already use, after the person agrees. |
| Muse sees posts the person saved on Instagram. | The playbook treats a saved restaurant post as "wants to try", never as an opinion. |
| Muse works toward goals in the background and has recurring tasks. | The weekly check runs under a food goal. Search results ask for a follow-up a day or two after a pick. |
| Muse has a dashboard skill. | `get_food_board` returns data shaped for one dashboard. |

## Check a connection by hand

1. Ask Muse: "What do you remember about my food taste?" Muse calls `get_taste_profile`.
   That proves the token is stored and the profile exists.
2. Ask: "Where should I eat tonight?" Then look at the Activity log under the Muse avatar.
   It should show a Tastebuds read.
3. Say: "The ramen at Tajima was great." The Activity log should show a Tastebuds write.
   The first time, Muse asks for approval.
4. Ask: "Show me my food board."

## Not verified yet

No one has run Tastebuds on a real Muse account. These points come from public sources:

- Whether Muse reads an MCP server directly for a Custom Connector, or wants a raw API.
  The message above offers both.
- Whether Muse maps MCP read and write hints to its own read and write prompts.
- Whether Muse can see how often the person messages each contact. If it cannot, it asks:
  "Who are the five people you eat out with most?"
- Whether Muse will send a WhatsApp or Instagram message for the person. If not, Muse hands
  the invite text to the person.
- Whether Muse keeps a `friend_ref` next to a name for months. If it loses one, it says
  "a friend" and never guesses.
