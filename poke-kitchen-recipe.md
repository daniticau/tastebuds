# Tastebuds Poke Recipe Draft

This is a copy/paste-ready draft for creating a Poke recipe in Kitchen.

Poke's public docs describe recipe fields and CLI flows, but do not publish a stable import file schema.
Use this document to create the recipe manually in Kitchen or to mirror the same values when using the CLI.

## Recipe Basics

- Name: `Tastebuds`
- Description: `Get invisible food recommendations from Tastebuds and quietly learn from what worked.`

## Onboarding

- `inputContext`:

  `I'll help you find places to eat using Tastebuds. Tell me the city you're usually in, any neighborhoods you spend time in, and the kinds of food you like or avoid.`

- `prefilledFirstText`:

  `I'm in San Diego a lot. I like Thai, ramen, tacos, and coffee shops. Help me find good spots and remember what I end up liking.`

## Required Integration

- Integration name: `Tastebuds`
- MCP server URL: `https://tastebuds-production.up.railway.app/mcp/`
- Auth: none
- Share credentials: no

## Suggested Positioning

Use these lines in Kitchen if you want a clearer user-facing setup:

- Short pitch: `Restaurant recommendations that get smarter from natural feedback.`
- What it does:
  - `Finds places to eat based on city, cuisine, neighborhood, recency, and aggregated sentiment.`
  - `Quietly logs follow-up feedback from normal conversation so recommendations improve over time.`
  - `Falls back gracefully when data is sparse.`

## CLI Equivalent

If you want to expose the integration to your Poke account first:

```bash
npx poke@latest login
npx poke@latest mcp add https://tastebuds-production.up.railway.app/mcp/ -n "Tastebuds"
```

If you want the CLI to bootstrap a recipe flow, Poke documents `--recipe` on `tunnel`, but that example is specifically for local tunneled servers.
For a hosted Railway MCP server, the public docs clearly support adding the MCP server URL and then selecting that integration in Kitchen.

## Install / Share Flow

Once the recipe is created in Kitchen:

1. Select the `Tastebuds` integration as required.
2. Publish the recipe.
3. Share the resulting `poke.com/r/...` or `poke.com/p/...` link.

## Official References

- Poke docs: https://poke.com/docs/creating-recipes
- Poke integrations docs: https://poke.com/docs/managing-integrations
- Poke MCP docs: https://interaction.mintlify.dev/docs/developers/integrations/mcp-in-poke
