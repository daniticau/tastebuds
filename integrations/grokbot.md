# Tastebuds on Grok Bot

Grok Bot is xAI's builder for personal agents. A bot keeps memory, files, and
preferences across turns, and it can own up to 50 routines that run on a schedule.
It runs on xAI's cloud with desktop and iOS apps. Connectors are shared by every
bot on the account.

## Connect

Send this in a chat with the bot:

```text
Add a custom MCP server called Tastebuds at https://tastebuds-production.up.railway.app/mcp
with no auth and no headers. When you test the tools, set dry_run=true.
Then call start_taste_profile for me and follow the playbook it returns.
```

Or use the form: Settings, then Plugins, then add a custom connector. The form takes
a name, a URL, and optional headers. Leave the headers empty.

On grok.com the same server works as a custom connector: grok.com/connectors, then
New Connector, then Custom, then paste the URL.

## Why the server is built the way it is

| Grok Bot behavior | What Tastebuds does about it |
|---|---|
| The form has no field for an OAuth client ID. | Tastebuds needs no auth. OAuth discovery paths answer 404, so the bot learns at once that no sign-in exists. No response carries `WWW-Authenticate`. |
| A person may paste some key into the optional headers anyway. | An `Authorization` header that is not a taste token is ignored. |
| The bot confirms the server name and URL before it adds the server. | The server name is `Tastebuds` and the URL is short. |
| Platforms read tool hints to decide when to ask the person first. | Reads carry `readOnlyHint`. Writes carry `destructiveHint: false`, so logging stays silent. Only `delete_taste_profile` is marked destructive. |
| Bots have routines. | The playbook tells the bot to set a routine for the follow-up question a day or two after a pick. |
| The bot cannot see the person's messages. | For friend links the playbook tells it to ask: "Who are the five people you eat out with most?" |
| Setup can start from a browser on grok.com. | A request with `Origin: https://grok.com` is not blocked. |

## Not verified yet

- The exact model-facing schema rules. The tests keep every tool schema free of
  `$ref`, `$defs`, and unions inside arrays, which are the usual trouble spots.
- Whether Grok Bot reads the MCP `instructions` field. The playbook also returns
  from `start_taste_profile`, so it arrives either way.
- Plan limits. Public guides say custom connectors need a paid tier.
