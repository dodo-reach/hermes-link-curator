#!/usr/bin/env python3
"""
Rebuild INDEX.md from all daily note files.
Use when INDEX.md was overwritten and entries are missing.

Auto-discovers the vault path. Optionally override with $HERMES_ARCHIVE_VAULT.
"""
import re
from pathlib import Path

# Auto-discover vault path:
# This script lives at <profile>/skills/note-taking/obsidian/scripts/rebuild_index.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
import os
VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))
INDEX = VAULT / "INDEX.md"

days = sorted(
    [p for p in VAULT.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.md", p.name)],
    reverse=True,
)
print(f"Found {len(days)} daily files")

all_entries = []
for day in days:
    content = day.read_text().replace('\r\n', '\n').replace('\r', '\n')
    segments = re.split(r'(?=\n### )', content)
    for seg in segments:
        seg = seg.strip()
        if not seg or not seg.startswith('### ') or '**URL**' not in seg:
            continue
        while seg.endswith('\n---'):
            seg = seg[:-4]
        all_entries.append(seg.rstrip('\n'))

def get_date(entry):
    m = re.search(r'\*\*Added\*\*:\s*(\d{4}-\d{2}-\d{2})', entry)
    return m.group(1) if m else "0000-00-00"

all_entries.sort(key=get_date, reverse=True)

lines = ["# Index"]
for e in all_entries:
    lines.append(e)
    lines.append("---")

INDEX.write_text("\n".join(lines).rstrip() + "\n")
print(f"INDEX.md rebuilt: {len(all_entries)} entries")
