# Muse connector submission

The form is at `muse.ai/platform`, behind "Submit a connector". It has three steps.
The answers below are ready to paste. Replace each value in `<angle brackets>`.
The domain is `tastebuds.daniticau.com`.

Review takes weeks, not days. Until approval, people add Tastebuds as a Custom Connector
with the message on the landing page. That path needs no review.

## Before you submit

1. Deploy the server. The form needs live URLs.
2. Check that `https://tastebuds.daniticau.com/health` answers `ok`. That domain is the default public origin.
3. Set `TASTEBUDS_SUPPORT_EMAIL`. The privacy, terms, and docs pages print it.
4. Read `/privacy` and `/terms` once. They are plain-language drafts that match the code.
   They are not legal advice. Have a lawyer check them before a wide launch.
5. Run the connector tests against the live server:

```bash
TASTEBUDS_TEST_SERVER_URL=https://tastebuds.daniticau.com pytest tests/test_connectors.py
```

## Step 1: Overview

| Field | Answer |
|---|---|
| Connector name | Tastebuds |
| Company or developer | `<your name or company>` |
| Product website | `https://tastebuds.daniticau.com/` |
| Connector icon | `https://tastebuds.daniticau.com/icon.svg` (512 by 512, SVG) |
| Payments | Does not accept payments |
| Your name | `<your name>` |
| Work email | `<your email>` |
| Support email or URL | `<support email>` |
| Privacy policy URL | `https://tastebuds.daniticau.com/privacy` |
| Terms of service URL | `https://tastebuds.daniticau.com/terms` |

**What the connector does**

```text
Tastebuds gives Muse a memory for food. It remembers how a person eats, learns from each
meal they mention, and ranks places to eat for them. Friends who link up see where each
other like to eat, and which dish to order there. It works in the background: the person
just gets better picks. It stores no name, no phone number, and no messages.
```

**Example prompts**

```text
Where should I eat tonight?
Find me a date night spot my friends like.
Somewhere like Tajima Ramen, but closer to me.
The tacos at Casa Verde were amazing. The salsa was too mild.
Where do my friends like to eat?
Show me my food board.
I went vegetarian. Remember that.
What do you remember about my food taste?
```

**Anything else**

```text
Tastebuds needs no account. The first tool call returns an anonymous token, which Muse keeps.
Every tool carries MCP read, write, or delete hints. No tool sends a message, spends money,
or acts outside Tastebuds. Writes accept dry_run=true for testing.
```

## Step 2: Technical specs

| Field | Answer |
|---|---|
| Connection type | Existing MCP |
| Hosted MCP endpoint | `https://tastebuds.daniticau.com/mcp` |
| Documentation | `https://tastebuds.daniticau.com/docs` |
| Authentication methods | Other |

**Access requirements**

```text
None. Anyone can use it, in any region. There is no sign-in and no paid tier.
Auth type "Other": the tool start_taste_profile returns a random token (taste_id) on first use.
Muse stores it and passes it on later calls, as the taste_id argument or as
"Authorization: Bearer <taste_id>". The token holds no personal data.
Limits: 300 requests per minute per client, 40 opinions per person per day.
A REST route with the same tools exists at POST /api/v1/<tool_name>, with an OpenAPI
document at /openapi.json.
```

## Step 3: Review

Read the summary back. Tick the three confirmations. Submit.

## What review will likely check, and where the answer is

| Question | Answer |
|---|---|
| Does it work end to end? | `tests/test_connectors.py` replays Muse setup: it calls all 16 tools once. |
| Which tools write? | `/docs` lists each tool as read, write, or delete. |
| Can a test call leave junk behind? | No. Writes take `dry_run`, finds take `peek`, delete needs `confirm=true`. |
| What personal data does it hold? | `/privacy`. No names, numbers, or messages. |
| Can one person read another's data? | Only with the other person's token, or as a linked friend who was given access. |
| How does a person delete their data? | They ask Muse. Muse calls `delete_taste_profile` with `confirm=true`. |
