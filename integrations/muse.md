# Tastebuds on Muse

Muse is the main target. Muse has no settings page for MCP servers. The person
describes the server in a message, and Muse does the rest on its cloud VM:

1. It writes an MCP client with the official SDK.
2. It connects over streamable HTTP and lists the tools.
3. It calls each tool to test it.
4. It saves the integration as a skill for later conversations.

## The message to send

```text
Build a custom integration to Tastebuds. Its MCP server URL is
https://tastebuds-production.up.railway.app/mcp and it needs no auth.
When you test the tools, set dry_run=true. Then call start_taste_profile
for me and follow the playbook it returns.
```

The landing page at `/` shows this message with a copy button.

## Why the server is built the way it is

Each choice below answers one Muse behavior.

| Muse behavior | What Tastebuds does about it |
|---|---|
| Muse tests every tool during setup. | `start_taste_profile` and `log_feedback` take `dry_run=true`. `delete_taste_profile` does nothing without `confirm=true`. Test calls store no junk. |
| Muse writes its own client and may skip the MCP `instructions` field. | The playbook also comes back in the `start_taste_profile` result. Muse sees it during setup and keeps it in the skill. Tool descriptions carry the key rules too. |
| Muse keeps the integration as a skill file. | The server mints the `taste_id`. The skill stores it. The model never has to invent a UUID and recall it. |
| Muse favors API keys over OAuth. | No auth is needed. As an option, Muse can store the `taste_id` as a bearer key in its Secure Credentials Store. The server reads `Authorization: Bearer <taste_id>`, so the token never appears in a tool call. |
| The Muse VM is in the cloud. | The server is a public HTTPS endpoint. Both `/mcp` and `/mcp/` answer without a redirect. |
| Custom connectors use the same usage meter as everything else. | Responses stay small: at most 10 places, 3 dishes, and 2 notes per place. |
| Muse links Instagram, Facebook, and Threads through Accounts Center, and chats in WhatsApp. It may see who the person messages most (not verified, see below). | The playbook tells Muse to offer friend links once, call `invite_friend` for about five top contacts, and set closeness from 1 to 3 by messaging activity. Muse sends each friend the invite over the channel they already use, after the person agrees. Only the level reaches the server. |
| Muse makes unprompted suggestions and has reminders. | Search results carry an `agent_note` that asks for a follow-up in a day or two. `get_follow_ups` lists what still needs a question. |

## Check a connection by hand

Ask Muse: "What do you remember about my food taste?" Muse calls
`get_taste_profile` and answers in plain words. That proves the token is stored
and the profile exists.

## Not verified yet

- Whether Muse can read how often the person messages each contact on Instagram
  and WhatsApp. Public sources confirm the account links and a contacts permission,
  not message frequency. If Muse cannot see it, Muse can ask the person:
  "Who are the five people you eat out with most?" The closeness levels work the same.
- Whether Muse will send a WhatsApp or Instagram message for the person. If not,
  Muse hands the invite text to the person to send.
