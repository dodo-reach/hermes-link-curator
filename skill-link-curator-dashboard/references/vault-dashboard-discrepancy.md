# Vault vs Dashboard — Discrepancy Troubleshooting

## The question: "Entries are missing from the dashboard"

Before assuming cache/server bug, verify the ACTUAL vault state.

### Step 1 — Check dashboard JSON endpoint (bypasses UI rendering)

```bash
# Check entries for a specific date
curl -s "http://localhost:8090/day-json/YYYY-MM-DD" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{len(d)} entries')"

# Check health endpoint
curl -s http://localhost:8090/health
```

### Step 2 — Count entries by date in INDEX.md

```bash
grep "Added.*YYYY-MM-DD" <profile-dir>/vault/INDEX.md | wc -l
```

### Step 3 — Check daily note file (may have entries INDEX.md is missing)

```bash
grep "Added" <profile-dir>/vault/YYYY-MM-DD.md
```

### Step 4 — Compare with dashboard count

| Scenario | Cause | Fix |
|----------|-------|-----|
| Dashboard JSON shows fewer than `grep` in INDEX.md | Entry has `Added` date different from daily note filename | Correct the `**Added**: YYYY-MM-DD` field in INDEX.md |
| INDEX.md and dashboard JSON match but user expects more | Entry was saved to wrong date | Move entry to correct date in INDEX.md |
| Dashboard cache stale | mtime not detecting change | `curl http://localhost:8090/reload-cache` |
| Browser cache | UI shows old data | `Ctrl+Shift+R` or incognito |

## Key insight from this session

**Entries are grouped by the `Added` field, NOT by the daily note filename.**

- `2026-05-31.md` contained an entry with `Added: 2026-06-01` → it appeared under June 1 in dashboard
- `INDEX.md` had MarkItDown and DeepakNess with `Added: 2026-05-31` → correctly under May 31, not June 1
- User expected them under June 1 because they were discussing them on June 1 — but the actual save used May 31

**The dashboard is always right. Check INDEX.md.**

## Workflow when user reports missing entries

1. `curl /day-json/<date>` to see what dashboard actually serves
2. `grep "Added" vault/INDEX.md` to see what's actually in the vault
3. If counts differ → find the entry with wrong `Added` date in INDEX.md and patch it
4. Run validate.py after any fix
5. Reload cache or hard-refresh browser