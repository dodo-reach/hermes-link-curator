---
name: link-curator-dashboard
description: Maintain and debug the link-curator web dashboard (port 8090). Separate process from the official Hermes dashboard.
triggers:
  - archive dashboard not loading
  - port 8090
  - archive-dashboard
  - graph view
  - d3 force graph
---

# Link Curator Dashboard — Maintenance Skill

## Service overview

The link-curator dashboard is a FastAPI app running on **port 8090**, separate from the official Hermes dashboard (`hermes dashboard`, default port 9119). It reads from the vault at `<profile-dir>/vault/` and exposes a read-only web UI.

## Process inventory

```bash
# Find all dashboard processes
lsof -nP -iTCP:8090 -sTCP:LISTEN

# Check the command
ps -p <pid> -o pid,command

# Check working directory (macOS)
lsof -a -p <pid> -d cwd

# Check working directory (Linux)
readlink /proc/<pid>/cwd
```

**Current layout (verify with `ps aux | grep "8090"`):**
- The dashboard process typically runs `uvicorn main:app --port 8090` from `<profile-dir>/dashboard/`
- The process working directory is authoritative — do not assume the path matches the skill's description if multiple dashboard instances exist
- This dashboard is a **separate process** from the official Hermes dashboard (the `hermes dashboard` command, default port 9119). They are independent and can run side-by-side.

## Key paths

| Component | Path |
|-----------|------|
| Dashboard app | `<profile-dir>/dashboard/` |
| Main app entry | `<profile-dir>/dashboard/main.py` |
| Vault parser | `<profile-dir>/dashboard/archive.py` |
| Templates | `<profile-dir>/dashboard/templates/` |
| Vault | `<profile-dir>/vault/` |

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /` | Dashboard UI |
| `GET /health` | Health check + entry count |
| `GET /stats` | Tag counts, date distribution |
| `GET /reload-cache` | Force-clear and reload vault cache |
| `GET /calendar` | Calendar view |
| `GET /search?q=...` | Search and filter entries |
| `GET /tag/{tag}` | Entries for a specific tag |
| `GET /day/YYYY-MM-DD` | Entries for a specific day |
| `GET /day-json/YYYY-MM-DD` | JSON feed for a day |
| `GET /graph` | Force-directed graph view (HTML + D3.js) |
| `GET /graph-json` | Graph dataset as `{nodes, links}` JSON |

## Optional entry metadata

Support these optional canonical lines anywhere in an entry:

```markdown
- **Shared by**: Ibby
- **Context**: `work`
```

Context is exactly `work` or `personal`. Missing metadata is valid. Every collapsed card displays available Context and `Shared by <name>` metadata, including a text-only circular sender initial. Omit either element cleanly when absent. Search both fields. `/day-json` and graph entry nodes expose stable `shared_by` and `context` keys; `/stats` exposes `by_context`.

Never guess `Shared by`; use it only when the user names the person. Set or infer Context only from unambiguous framing: QSIC, Jira, pull requests, or employment tasks → `work`; family, travel, hobbies, or personal activities → `personal`. A technical article alone is not work context. If unclear, omit it and do not interrupt archiving to ask.

## Filtering and responsive cards

The list and search pages accept `q`, `context`, `shared_by`, `tag`, and `type` query parameters. Structured filters are independent, combinable, exact, and case-insensitive; `q` remains a case-insensitive substring search across the supported fields. Forms must preserve the other active parameters. Unknown values return an empty result set. Clear/reset actions remove every search and filter parameter.

Filter dropdown options and counts come from parsed Markdown entries. Deduplicate people, topics, and types case-insensitively. Show only the three most-used topic tags above the results; the complete tag set belongs in the topic selector. Render active filters as removable chips with the filtered result count.

Cards in list, search, tag, day, and calendar-generated results share this collapsed order: type, optional context, optional sender initial/name, title, collapsed summary, and tags. Normalize whitespace and truncate only the collapsed summary to at most 100 characters including `…`, at a word boundary when possible. Preserve full source and JSON summaries, and show the full summary when a card expands. Escape Jinja values normally and use DOM `textContent` for generated cards.

Below 768px, use full-width segmented primary navigation, a compact search-plus-Filters row, horizontally scrolling top topics, one card column, two visible tags plus `+N`, and controls at least 44px high. The native-dialog filter sheet contains Context, Shared by, Topic, and Type controls; it traps focus, closes with its close button or Escape, prevents background scrolling, and restores focus to its trigger.

## Tag semantics

Tags describe link subjects, not type, context, or sender metadata. Automatic generation uses at most three lowercase tags, prefers existing tags, and hyphenates multiple words. Never automatically generate `#article`, `#github`, `#shared`, `#work`, `#personal`, or equivalents that duplicate structured fields. Explicit CLI tags are still accepted.

## Caching — automatic

`archive.py` uses **mtime-based invalidation** — no `lru_cache`, no manual invalidation needed:

1. On every request, `get_all_entries()` checks the `mtime` of `INDEX.md`
2. If the file hasn't changed → returns cached entries (fast)
3. If the file was modified (new entries saved) → silently re-reads and rebuilds the cache

This means the dashboard always reflects the current vault state without any manual intervention. The only time you need to act is when the file can't be read (permissions, disk error) — in that case the last valid cache is served and a warning is logged.

**`/reload-cache`** still exists for edge cases (corrupted mtime, network mounts with broken stat) — it's a manual force-refresh that clears the cache and re-reads immediately.

## Dashboard went offline — restart procedure

The dashboard has **no watchdog** and dies silently (e.g. after a system reboot). Unlike the official Hermes dashboard which can be supervised by `hermes gateway install`, the link-curator dashboard must be manually restarted when the process exits. See "Dashboard went offline — restart procedure" below.

```bash
cd <profile-dir>/dashboard
./start.sh 8090
```

For a background process:

```bash
cd <profile-dir>/dashboard
mkdir -p ../logs
nohup ./start.sh 8090 > ../logs/dashboard.log 2>&1 &
```

After starting, verify readiness:
```bash
sleep 2 && curl -s --max-time 3 http://localhost:8090/health
```
Expected: `{"status":"healthy","total_entries":N,...}`

If health fails, check the background process output:
```bash
tail -50 <profile-dir>/logs/dashboard.log
```

## Validate

```bash
cd <profile-dir>/dashboard && python3 validate.py
```

> **Pitfall:** The profile root at `<profile-dir>/` also has a `validate.py` — it is a DIFFERENT file. Running `python3 validate.py` from the wrong directory gives wrong results or errors. See `references/validate-path.md` for the correct path, common wrong paths, and exit code meanings.

## Double-`---` separator trap

When removing a malformed entry from `INDEX.md` (e.g. one with a wrong header level like `# Index` instead of `### Title`), you may leave behind a dangling `---` separator. Combined with the next entry's `---`, this creates a **double separator** pattern (`---\n\n---`) which produces an empty entry chunk. The validator reports it as `ERROR: Missing or malformed ### title line` at chunk N.

**Fix**: After removing a bad entry, check the surrounding context in both `INDEX.md` and the relevant daily note file (e.g. `vault/2026-MM-DD.md`). Ensure only ONE `---` separates entries, not two. The validator will catch this (`Has errors: 1`, `ERROR: Missing or malformed ### title line`) — re-check and patch the orphaned separator.

**Why `patch` misses it**: The malformed entry sits in a section of the file where many entries share identical string patterns (e.g. `- **Summary**: ...` lines). `patch` reports `Found N matches for old_string` and refuses to guess. Use Python direct file manipulation instead:

```python
python3 - <<'EOF'
path = "<profile-dir>/vault/INDEX.md"
with open(path) as f:
    lines = f.readlines()
# Find the target line and insert/delete as needed
for i, line in enumerate(lines):
    if line.startswith("### TARGET ENTRY"):
        # remove: del lines[i-1:i+6]  (separator + entry)
        # insert: lines.insert(i, new_entry_text)
        break
with open(path, "w") as f:
    f.writelines(lines)
EOF
```

## Diagnostic checklist — "dashboard shows fewer entries than expected"

Use this sequence before assuming server-side problems:

1. **`curl http://localhost:8090/health`** — get total_entries count
2. **`curl http://localhost:8090/day-json/YYYY-MM-DD`** — check specific days; returns JSON array of entries
3. **`curl http://localhost:8090/` | grep 'entry-card'`** — count entry cards in raw HTML
4. If API returns correct count but browser UI doesn't → **browser cache**, try `Ctrl+Shift+R` or incognito window
5. If health count is fine but dashboard still shows fewer entries → possible INDEX.md chunk corruption. See `obsidian` skill → **INDEX.md Health Check** section for the Python chunk analysis one-liner that catches merged entries and double-`---` separators in seconds.

**Quick health check (always run after INDEX.md edits):**
```bash
cd <profile-dir>/dashboard && python3 validate.py
```
Expected: `Has errors: 0`, `Fully valid: N` matching vault entry count.

**Key signal**: `total_entries` from `/health` matches vault count → server is fine, client cache is the issue.

## Graph view

The `/graph` endpoint renders a D3.js force-directed graph over the vault. Data
is built by `get_graph_data()` in `archive.py` and exposed via `/graph-json`.

**Data shape** (tag-graph, two node kinds):
- `nodes`: `{id, label, kind: "tag"|"entry", count, type?, url?, shared_by?, context?}`
- `links`: `{source: tag_id, target: entry_id}` — bipartite, no entry↔entry edges

**Why tag-graph instead of entry-graph**: with 100+ entries, an entry↔entry
similarity graph becomes a hairball. Tag hubs collapse shared topics into a
readable cluster, the way Obsidian's native graph view does. Entry count is
`O(entries × avg_tags)`, link count is `O(tag_appearances)`.

**Filtering rule**: tags with `count < 2` are dropped (reduces noise from
one-off tags) and entries that share zero active tags are omitted as orphans.
With 103 entries this produces ~78 tag nodes + ~101 entry nodes + ~400 links.

**Front-end interactions** (D3 v7 via CDN, no npm install):
- drag to reposition, scroll to zoom (0.3×–5×), background dblclick to reset
- click a tag node → highlight that cluster, dim the rest (click again to clear)
- dblclick an entry node → open its URL in a new tab

See `references/graph-view.md` for the full D3 template, force tuning, color
map, and a reusable starter at `templates/force-graph.html` (copy + change the
data endpoint to reuse for a different graph).

## Adding new routes (pattern)

For any new page that needs the same nav + footer as the rest of the dashboard:

1. Add the route in `main.py` (HTML response) + matching `-json` for data
2. Add `current_page` string in the template context
3. Add a nav link in `templates/base.html` (use `{% if current_page == '<name>' %}`)
4. Add CSS to the bottom of `base.html` if it needs styles
5. Add a function in `archive.py` if it parses the vault
6. Validate + restart

## Common failure modes

1. **Dashboard shows fewer entries than expected** — run validate.py; if health count matches vault count, the server is fine — the issue is browser-side
2. **Old process still running on 8090** — new start fails because port is occupied. Always kill first.
3. **Browser cache** — after any fix, always try `Ctrl+Shift+R` or incognito. The dashboard is read-heavy and browsers aggressively cache it.
4. **INDEX.md entries missing** — use the explicit `rebuild_index.py` tool below. It locks the vault and creates a timestamped backup before replacing an existing index. Prevention: use `save_entry.py` for all new saves; it journals the two-file update and atomically replaces each file.

## Rebuild INDEX.md from daily notes

If INDEX.md is damaged or missing, explicitly rebuild it from canonical dated notes:

```bash
cd <profile-dir>/skills/note-taking/obsidian/scripts
python3 rebuild_index.py
```

The tool refuses to run while an unresolved save journal exists and backs up an
existing index before replacement.

Then validate:
```bash
cd <profile-dir>/dashboard && python3 validate.py
curl http://localhost:8090/reload-cache
```

## Related skills

- `obsidian` — vault entry format, save workflow, validate.py

## References

- `references/validate-path.md` — validate.py location, exit codes, what it checks
- `references/proc_pid_working_dir.md` — how to resolve "which process is actually running on this port"
- `references/vault-dashboard-discrepancy.md` — troubleshooting missing entries: always verify INDEX.md `Added` field vs dashboard grouping
- `references/graph-view.md` — D3 force-directed graph: data shape, force tuning, color map, interaction patterns
