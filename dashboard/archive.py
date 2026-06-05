"""Archive parser for the lightweight link curator web app."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Auto-discover vault path:
# This file lives at <profile>/dashboard/archive.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
VAULT_PATH = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent / "vault"
))


@dataclass
class ArchiveEntry:
    title: str
    url: str
    entry_type: str
    tags: list[str]
    added: str
    summary: str
    status: Optional[str] = None
    note: Optional[str] = None
    source: Optional[str] = None


@dataclass
class ArchiveDay:
    date: str
    label: str
    entries: list[ArchiveEntry] = field(default_factory=list)


def _parse_entry(block: str, file: str = "INDEX.md") -> Optional[ArchiveEntry]:
    """Parse a single entry block. Returns None if critical fields are missing."""
    title_m = re.search(r'^###\s+([^\n—]+?)\s+—\s+', block, re.MULTILINE)
    if not title_m:
        title_m = re.search(r'^###\s+(.+?)\s*$', block, re.MULTILINE)

    url_m = re.search(r'\*\*URL\*\*:\s*([^\s]+)', block)
    type_m = re.search(r'\*\*Type\*\*:\s*`([^`]+)`', block)
    tags_m = re.findall(r'#\w[-\w]*', block)
    added_m = re.search(r'\*\*Added\*\*:\s*(\d{4}-\d{2}-\d{2})', block)
    summary_m = re.search(r'\*\*Summary\*\*:\s*(.+?)(?=\n---|\n\*\*Note|\Z)', block, re.DOTALL)
    status_m = re.search(r'\*\*Status\*\*:\s*`([^`]+)`', block)
    note_m = re.search(r'\*\*Note\*\*:\s*(.+?)(?=\n---|\Z)', block, re.DOTALL)
    source_m = re.search(r'\*\*Source\*\*:\s*(.+?)(?=\n---|\Z)', block, re.DOTALL)

    if not (title_m and added_m):
        return None

    title = title_m.group(1).strip()
    if title.startswith('[') and '](' in title:
        m = re.search(r'\[([^\]]+)\]', title)
        if m:
            title = m.group(1)

    summary = summary_m.group(1).strip() if summary_m else ""
    summary = re.sub(r'^\s+', '', summary)

    return ArchiveEntry(
        title=title,
        url=url_m.group(1).strip() if url_m else "",
        entry_type=type_m.group(1).strip() if type_m else "other",
        tags=[t.strip() for t in tags_m],
        added=added_m.group(1).strip(),
        summary=summary,
        status=status_m.group(1).strip() if status_m else None,
        note=note_m.group(1).strip() if note_m else None,
        source=source_m.group(1).strip() if source_m else None,
    )


# ─── Cache with explicit mtime-based invalidation ─────────────────────────────────

_cache: list[ArchiveEntry] = []
_cache_mtime: float = 0.0
_cache_valid: bool = False


def get_all_entries() -> list[ArchiveEntry]:
    """Get all entries from INDEX.md.
    
    Automatically reloads when INDEX.md mtime changes.
    Thread-safe for concurrent requests under FastAPI (the GIL serialises access;
    the worst case is a single redundant re-read if two requests arrive simultaneously
    while the cache is stale — harmless and rare in practice).
    """
    global _cache, _cache_mtime, _cache_valid

    index_path = VAULT_PATH / "INDEX.md"
    if not index_path.exists():
        logger.error(f"INDEX.md not found at {index_path}")
        _cache_valid = False
        return []

    try:
        current_mtime = index_path.stat().st_mtime
    except OSError as e:
        logger.warning(f"Could not stat INDEX.md: {e}")
        return _cache if _cache_valid else []

    if _cache_valid and current_mtime == _cache_mtime:
        return _cache

    # ── Cache miss or stale — rebuild ────────────────────────────────────────────
    with open(index_path) as f:
        content = f.read()

    chunks = re.split(r'\n---\n', content)
    entries = []
    skipped = 0
    for i, chunk in enumerate(chunks):
        if not re.search(r'\*\*URL\*\*', chunk):
            continue
        entry = _parse_entry(chunk.strip())
        if entry:
            entries.append(entry)
        else:
            skipped += 1
            title_m = re.search(r'^###\s+(.+?)\s*$', chunk, re.MULTILINE)
            title = title_m.group(1)[:50] if title_m else f"chunk {i}"
            logger.warning(f"Skipped malformed entry #{i}: {title}")

    if skipped:
        logger.warning(f"Total skipped malformed entries: {skipped}")

    _cache = entries
    _cache_mtime = current_mtime
    _cache_valid = True
    return _cache


def get_entries_by_date() -> list[ArchiveDay]:
    """Get entries grouped by date. Uses cached get_all_entries()."""
    entries = get_all_entries()
    by_date: dict[str, list[ArchiveEntry]] = {}
    for e in entries:
        by_date.setdefault(e.added, []).append(e)

    days = []
    for date in sorted(by_date.keys(), reverse=True):
        d = datetime.strptime(date, "%Y-%m-%d")
        label = d.strftime("%d %b %Y").lstrip("0")  # "14 May 2026"
        days.append(ArchiveDay(date=date, label=label, entries=by_date[date]))

    return days


def get_tags() -> list[tuple[str, int]]:
    """Get all tags with counts, sorted by frequency. Uses cached get_all_entries()."""
    entries = get_all_entries()
    counts: dict[str, int] = {}
    for e in entries:
        for t in e.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])


def search_entries(query: str) -> list[ArchiveEntry]:
    """Search entries by title, summary, or tags. Uses cached entries."""
    q = query.lower()
    results = []
    for e in get_all_entries():
        if (q in e.title.lower() or q in e.summary.lower() or
            q in " ".join(e.tags).lower() or
            any(q in t for t in e.tags)):
            results.append(e)
    return results


def get_graph_data() -> dict:
    """Build a force-graph dataset: tag nodes (big) + entry nodes (small),
    edges connect entries to their tags. Tag size proportional to entry count.

    Returns:
        {"nodes": [{"id", "label", "type", "count"}],
         "links": [{"source", "target"}]}
    """
    entries = get_all_entries()
    tag_counts: dict[str, int] = {}
    for e in entries:
        for t in e.tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    # Keep repeated tags by default to reduce noise. For a fresh/small archive,
    # fall back to all tags so the graph view is not blank for first-time users.
    active_tags = {t for t, c in tag_counts.items() if c >= 2}
    if not active_tags:
        active_tags = set(tag_counts)

    nodes: list[dict] = []
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        if tag not in active_tags:
            continue
        nodes.append({
            "id": f"tag:{tag}",
            "label": tag,
            "kind": "tag",
            "count": count,
        })

    for e in entries:
        # Skip entries with no active-tag overlap — they'd be orphan nodes
        if not any(t in active_tags for t in e.tags):
            continue
        nodes.append({
            "id": f"entry:{e.url}",
            "label": e.title,
            "kind": "entry",
            "type": e.entry_type,
            "url": e.url,
            "count": 1,
        })

    links: list[dict] = []
    for e in entries:
        if not any(t in active_tags for t in e.tags):
            continue
        for t in e.tags:
            if t in active_tags:
                links.append({
                    "source": f"tag:{t}",
                    "target": f"entry:{e.url}",
                })

    return {"nodes": nodes, "links": links}


def clear_cache() -> None:
    """Manually invalidate the entries cache (useful for tests or force-refresh)."""
    global _cache, _cache_mtime, _cache_valid
    _cache_valid = False
    _cache = []
    _cache_mtime = 0.0
