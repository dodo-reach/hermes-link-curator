---
name: obsidian
description: Link curator vault at <profile-dir>/vault/
triggers:
  - save link
  - archive URL
  - add to vault
  - link curator
  - user sends an URL/link
  - user says save/archive/add to vault
---

# Obsidian Vault — Link Curator Skill

## Behavior — do not summarize, archive

When the user sends a URL or asks to save/archive something: **archive it immediately, do not summarize**. Your job is that of a librarian: receive → process → file. Not a chatbot to give impressions.

Do NOT respond with a summary of the content unless the user explicitly asks for one. Archive first, then say only "Salvato." (or the error, if any).

## Vault
`<profile-dir>/vault/`

## Entry format

```
### [Title]
- **URL**: https://...
- **Type**: `github` | `x-post` | `article` | `tool` | `video` | `paper` | `other`
- **Tags**: #tag1 #tag2 #tag3
- **Added**: YYYY-MM-DD
- **Shared by**: Ibby
- **Context**: `work`
- **Summary**: What is this? Why does it matter? What do you do with it?

---

[next entry]
```

`---` between every entry. No `---` = merged entry in dashboard. Parse splits on `\n---\n`.

`Shared by` and `Context` are optional. Omit missing fields completely. When present, put them after `Added` and before `Summary`; Context must be exactly `work` or `personal`.

Never guess `Shared by`. Include it only when the user identifies the person. Set Context when the user says the link is for work or personal. Infer Context only when the framing is unambiguous: QSIC, Jira, pull requests, or employment tasks mean `work`; family, travel, hobbies, or personal activities mean `personal`. A technical article is not automatically work-related. If unclear, omit Context and continue archiving without asking.

Examples:
- “Ibby shared this with me” → `shared_by=Ibby`
- “Save this for work” → `context=work`
- “Ibby sent me this for work” → `shared_by=Ibby`, `context=work`
- “Archive this link” → omit both unless the framing clearly provides them

## Topic tags

Tags describe the subject of a link; they do not repeat structured metadata. When generating tags automatically:

- Add no more than three topic tags.
- Prefer an existing vault tag instead of creating a synonym.
- Use lowercase and hyphens for multiple words, such as `#ai-security`.
- Never generate tags for type, context, or sender metadata. In particular, do not generate `#article`, `#github`, `#shared`, `#work`, or `#personal`.
- Do not reject or remove tags explicitly supplied through the CLI. These rules govern automatic tag generation only.

## Save workflow

**Use `save_entry.py`** — atomic read+patch, never overwrites INDEX.md.

```bash
python3 <profile-dir>/skills/note-taking/obsidian/scripts/save_entry.py \
  --url "https://..." \
  --title "Entry Title" \
  --type "article" \
  --tags "ai dev-tools" \
  --added "2026-06-04" \
  --shared-by "Ibby" \
  --context work \
  --summary "What it is and why it matters."
```

Both flags are optional. The dashboard displays them on entry cards and includes them in search.

The script:
1. Reads INDEX.md in memory (never overwrites without reading)
2. Finds the first `---` separator
3. **Inserts the new entry AFTER the first `---` separator** (each entry gets its own chunk)
4. Also appends to the daily note `vault/YYYY-MM-DD.md`
5. Runs validate.py automatically

> **⚠️ Prepend bug (fixed):** Old versions of `save_entry.py` inserted new entries BETWEEN the header and the first `---`. When two entries from the same day were saved consecutively, they ended up in the same chunk. The dashboard parser uses `re.findall(r'\*\*URL\*\*', chunk)[0]` — only the first URL per chunk was read. Symptoms: entry appears in INDEX.md but not in dashboard (or dashboard shows fewer entries than vault count). Fix was to change `lines[:sep_idx]` → `lines[:sep_idx+1]` so insertion happens AFTER the separator, not before. Run `rebuild_index.py` to fix retroactively affected vaults.

**Validate** after save is automatic via the script. Manual validate (if needed):
```bash
cd <profile-dir>/dashboard && python3 validate.py
```

**Manual workflow** (only if script unavailable): fetch → append to daily → read INDEX first, then `patch` to prepend. Never use `write_file` on INDEX.md.

## X/Twitter — optional browser-session fetch

`web_extract` and `browser_navigate` may return login walls on X. If camofox is installed and the content is important, use its local REST API:

```bash
CAMOFOX_USER_ID="${CAMOFOX_USER_ID:-link-curator}"
TAB=$(curl -s -X POST http://localhost:9377/tabs \
  -H "Content-Type: application/json" \
  -d "{\"userId\":\"$CAMOFOX_USER_ID\",\"sessionKey\":\"link-curator\",\"url\":\"https://x.com/USERNAME/status/POST_ID\"}")
TAB_ID=$(echo "$TAB" | python3 -c "import sys,json; print(json.load(sys.stdin)['tabId'])")
sleep 3
curl -s "http://localhost:9377/tabs/$TAB_ID/snapshot?userId=$CAMOFOX_USER_ID" > /tmp/snap.json
python3 -c "import sys,json; d=json.load(open('/tmp/snap.json')); print(d.get('snapshot','')[:6000])"
curl -s -X DELETE "http://localhost:9377/tabs/$TAB_ID?userId=$CAMOFOX_USER_ID"
```

Content is in `.snapshot`, NOT `.accessibilityTree.content`. **jq is not available** — always use python3 for JSON parsing.

If camofox fails: web_search fallback, then save URL + `[content unavailable]` in Summary.

**Quick probe before long fetch** — when the URL is an X post and you need content for the Summary:
1. `curl -s --max-time 8 "https://x.com/USER/status/ID"` — if it returns HTML login page, X is blocking
2. If blocked → skip camofox, go straight to `web_search` or save with `[content unavailable]`
3. Only use camofox (tab + sleep + snapshot) when you have reason to believe it will succeed and the content is high-value

## User-provided context shortcut

When the user says "this link is about X" or provides the summary framing directly, **trust it and stop digging**. Do not spend extra tool calls trying to extract more context from the page — the user already told you what matters. Supplement with whatever minimal snapshot data is readily available, then save. Examples:

- `"é un video che spiega che codex può lanciare, pinnare e gestire worktrees"` → use that framing, add minimal post metadata (author, engagement) from snapshot, done.
- `"save this, it's about local LLMs"` → accept the user's framing, don't try to fetch deeper content.

Only fall back to `[content unavailable]` if camofox itself fails AND no user context was provided.

## Search vault

```bash
# By content
grep -ri "keyword" <profile-dir>/vault/ --include="*.md"

# By date
ls <profile-dir>/vault/2026-05-*.md
```

## validate.py path

The validate script lives in the **dashboard directory**, NOT in the profile vault. In a standard install the dashboard is at `~/.hermes/profiles/<profile>/dashboard/` and the vault is at `~/.hermes/profiles/<profile>/vault/`.

**Always check the actual path before running:**
```bash
# Find validate.py
find ~ -name "validate.py" 2>/dev/null | grep -i dashboard
```

Never hardcode a path you haven't verified. The `cd` must target the dashboard directory, not the vault.

## Tag normalization conventions

Keep tags consistent across the vault. When saving new entries, follow these rules:
- `#open-source` — never use `#open` alone
- `#dev-tools` — for developer tooling entries (CLI, agents, utility scripts). Use `#dev-tools` consistently, not `#tooling` or `#tools` (except for entries that are genuinely about design/general tools)
- `#local-ai` — for local inference, Apple Silicon, on-device ML
- Merge `#local` and `#local-ai` → always use `#local-ai`

## Status field

Do NOT use `**Status**: 'unread'` or any other status markers. The vault stores processed entries only. For items to revisit later, use a bookmarking tool outside the vault (read-later app, pin board, etc.).
```

## Dashboard (port 8090) — separate process

The link-curator dashboard runs at `http://localhost:8090`. It is a standalone FastAPI app, not part of the official Hermes dashboard (`hermes dashboard`, default port 9119). The two are independent and can run side-by-side. See the `link-curator-dashboard` skill for full maintenance and restart procedures.

## Architecture rules (critical — never violate)

**Entry blocks do NOT contain `---`. The separator is added at write time.**

`build_entry_block()` returns text ending in `\n` (no `---`). Both `append_to_daily()` and `prepend_to_index()` add `\n---\n` or `\n---` as a separator when writing. If you put `---` inside `build_entry_block`, you get double `---` on prepend, which corrupts the dashboard parse.

**Never use `write_file` on INDEX.md.** The only safe operations are `read_file` first, then `patch`. Even for "quick edits" — read first, patch, never overwrite. The script enforces this; manual workflow must follow it too.

**INDEX.md headers differ by profile.** The `prepend_to_index` function finds the first `---` separator regardless of what header text precedes it:
- Default: `# Index` followed by `---`
- Custom profile headers are also fine as long as the first separator is `---`

Do NOT look for a specific header string — find the first `---` and insert after it.

**Validate after every save.** Run `validate.py` from the dashboard directory, not the vault.

## validate.py — common fixes

**Empty entry error ("Missing or malformed ### title line")**:  
Usually caused by a double `---` separator creating an empty chunk. Fix: remove the duplicate `---` between two consecutive entries in INDEX.md, leaving only one.

**Title uses em-dash (—) instead of hyphen-minus (-)**:
The parser accepts both in titles, but the `validate.py` script warns on em-dashes. More importantly, some edge cases in the title regex (`^###\s+[^\n—]+?\s+—\s+`) can fail to parse a title that has an em-dash mid-string. **Always use hyphen-minus (`-`) as the title separator in vault entries.** Example: `### Claude Code + Screen Recording Workflow - UI Bug Fixing` not `—`.

**Title validation fails for `# Index` header**:  
The title check `r'^###\s+\S'` rejects `# Heading` (single `#`). Chunk 5 (`# Index`) was a valid non-entry header — the URL filter already correctly skips non-entry blocks. Working title regex: `r'^#{1,3}\s+\S'` accepts h1–h3. The URL filter is the primary guard; the title regex is secondary.

---

## INDEX.md Health Check — when to run + manual verification

Run `validate.py` and do a manual chunk split when:
- Entries saved via `save_entry.py` appear in INDEX.md but not in the dashboard
- Dashboard shows fewer entries than vault count suggests
- You made manual edits to INDEX.md (patch, rebuild, etc.)

### validate.py output thresholds

| Result | Meaning |
|--------|---------|
| `Has errors: 0` | Vault is parse-safe. Dashboard will show all entries. |
| `Has errors: >0` | Structural corruption — entries may be missing from dashboard |
| `Fully valid: N` | Entries that pass all field checks |
| `Has warnings: M` | Non-fatal (em-dashes in titles, missing optional fields) — dashboard still works |

**Always run validate.py after any INDEX.md edit.** It's the only way to catch double-`---` chunks and merged entries before the user sees wrong counts.

### Manual chunk analysis (Python one-liner for ad-hoc checks)

```python
content = open('<profile-dir>/vault/INDEX.md').read()
chunks = content.split('\n---\n')
for i, chunk in enumerate(chunks):
    titles = [l for l in chunk.split('\n') if l.strip().startswith('###')]
    if len(titles) > 1:
        print(f"⚠️  Chunk {i}: MERGED {len(titles)} entries")
    if '\n---\n' in chunk:
        print(f"⚠️  Chunk {i}: double separator")
print(f"✅ {len(chunks)} chunks total, {sum(1 for c in chunks if '**URL**' in c)} with URLs")
```

This catches the prepend bug (two entries in same chunk) and orphaned `---` separators (empty chunks) faster than re-reading by eye.

---

## DISASTER RECOVERY

### INDEX.md missing or overwritten

**Root cause**: `write_file` on INDEX.md without reading first wipes all entries. If only recent dates appear in dashboard (e.g. June only, May gone), INDEX.md was overwritten.

**Fix** — run the rebuild script:
```bash
cd <profile-dir>/skills/note-taking/obsidian/scripts
python3 rebuild_index.py
```

**Prevention**: ALWAYS use `save_entry.py` for new saves. Never `write_file` directly on INDEX.md.
```bash
grep -c '^### ' <profile-dir>/vault/INDEX.md
# must equal sum of grep -c '^### ' vault/2026-05-*.md
```

### Reconciliation (INDEX vs daily notes out of sync)

If counts don't match: extract missing entries from INDEX and patch into the daily file.

### Common failure mode
`write_file` on INDEX.md without reading first = overwrite destroys all entries. Always `read_file` first, then `patch`.

## Related skills

- `camofox` — for browser-session fetching on sites that block simple extraction
