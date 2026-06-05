# Dashboard (link-curator)

FastAPI app that serves a read-only Obsidian-style web UI over a markdown vault.

## What it does

- **List** (`/`) — all entries, grouped by date, newest first
- **Calendar** (`/calendar`) — month view with entry-count heatmap
- **Search** (`/search?q=...`) — substring search across titles, summaries, tags
- **Tag pages** (`/tag/{tag}`) — entries for a specific tag
- **Day pages** (`/day/YYYY-MM-DD`) — entries for a specific day
- **Graph** (`/graph`) — D3 force-directed tag↔entry graph
- **Stats** (`/stats`) — JSON: total entries, days, type counts, top tags
- **Health** (`/health`) — JSON: server status + entry count

## How it finds the vault

Auto-discovery: the script computes the vault path as `<this-file>/../../vault`. So if you copy the dashboard to `<profile-dir>/dashboard/`, the vault is automatically `<profile-dir>/vault/`.

Override with `$HERMES_ARCHIVE_VAULT` if the vault lives somewhere else.

## Run

```bash
./start.sh 8090
# → open http://localhost:8090
```

## Validate the vault

```bash
python3 validate.py
```

Checks every entry in `INDEX.md` for missing fields, malformed dates, double-`---` separators, and other parse-breaking issues. Run this from inside the dashboard directory.

## Caching

The parser uses mtime-based invalidation: every request checks if `INDEX.md` was modified since last read. If yes, the cache rebuilds silently. The endpoint `GET /reload-cache` forces a manual refresh (rarely needed).
