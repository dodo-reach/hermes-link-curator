# Hermes Link Curator

A **link curator profile pack** for [Hermes Agent](https://github.com/NousResearch/hermes-agent) — turn any Hermes agent into a librarian. Send a URL, get it archived, tagged, summarized, and browsable in a fast Obsidian-style dashboard.

## What this is

- **2 skills** (`obsidian` + `link-curator-dashboard`) — drop into any Hermes profile
- **1 dashboard** — standalone FastAPI app, Obsidian-style web UI (port 8090)
- **1 SOUL template** — gives the agent a "librarian" personality (archive, don't summarize)

The agent receives links → fetches content → writes entries to a local markdown vault → the dashboard reads the vault and serves a search/tag/graph view.

## Install (30 seconds, agent-guided)

Send your Hermes agent a message like:

> *Install https://github.com/dodo-reach/hermes-link-curator — follow the AGENT_GUIDE.md.*

The agent will read `AGENT_GUIDE.md`, create a new profile, copy the pieces, and start the dashboard. You can then start archiving:

> *archive https://github.com/some/repo*

or use the dashboard at `http://localhost:8090`.

**Prefer the manual path?** Run `./install.sh` from this repo — it asks one question (profile name) and does the same thing.

## Repo layout

```
hermes-link-curator/
├── README.md                          # you are here
├── AGENT_GUIDE.md                     # instructions for the agent
├── install.sh                         # self-service installer
├── SOUL.template.md                   # paste into your profile's SOUL.md
├── skill-obsidian/                    # the save-link skill
├── skill-link-curator-dashboard/      # the dashboard maintenance skill
└── dashboard/                         # standalone FastAPI web app
```

## Architecture

Everything lives under `~/.hermes/profiles/<profile-name>/`. Path auto-discovery — no env vars to set, no config files to edit:

```
~/.hermes/profiles/link-curator/
├── SOUL.md                            # personality + triggers
├── vault/                             # the archive (auto-created on first save)
│   ├── INDEX.md                       # master list, newest first
│   └── YYYY-MM-DD.md                  # daily notes
├── skills/note-taking/
│   ├── obsidian/                      # the save workflow
│   └── link-curator-dashboard/        # dashboard maintenance
└── dashboard/                         # the FastAPI web app
    ├── main.py
    ├── archivio.py                    # vault parser
    ├── validate.py                    # integrity checker
    └── start.sh                       # launcher
```

The dashboard reads the vault and exposes: list, calendar, search, tag pages, day pages, a D3 force-directed tag graph, and a JSON stats endpoint.

## Optional upgrades

The base install gets you archiving. Two more steps are documented in `AGENT_GUIDE.md`:

- **Fetch context from any link** — add `camofox` (anti-detection browser) and the Playwright MCP server so the agent can fetch X/Twitter, paywalled articles, and JS-heavy sites
- **Send links from messaging apps** — add a Telegram/Discord/Slack gateway and forward URLs to the link-curator agent

## Acknowledgments

Built by [dodo-reach](https://github.com/dodo-reach) as a personal system, packaged for the Hermes community. Powered by [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research.

## License

MIT
