"""Archive parser for the lightweight link curator web app."""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def is_safe_http_url(value: str) -> bool:
    """Return whether a raw vault URL is safe to expose as a clickable link."""
    if not value or any(character.isspace() for character in value):
        return False
    if any(unicodedata.category(character).startswith("C") for character in value):
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)

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
    shared_by: Optional[str] = None
    context: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None
    source: Optional[str] = None

    @property
    def clickable_url(self) -> Optional[str]:
        return self.url if is_safe_http_url(self.url) else None


@dataclass
class ArchiveDay:
    date: str
    label: str
    entries: list[ArchiveEntry] = field(default_factory=list)


def collapsed_summary(summary: str, max_length: int = 100) -> str:
    """Normalize and truncate text for a collapsed card without mutating source data."""
    normalized = " ".join(summary.split())
    if len(normalized) <= max_length:
        return normalized

    content_limit = max_length - 1
    candidate = normalized[:content_limit]
    boundary = candidate.rfind(" ")
    if boundary > 0:
        candidate = candidate[:boundary]
    return candidate.rstrip() + "…"


def sender_initial(shared_by: Optional[str]) -> str:
    """Return the first alphanumeric sender character for the card avatar."""
    if not shared_by:
        return ""
    return next((character.upper() for character in shared_by if character.isalnum()), "")


def _parse_entry(block: str, file: str = "INDEX.md") -> Optional[ArchiveEntry]:
    """Parse a single entry block. Returns None if critical fields are missing."""
    title_m = re.search(r'^###\s+([^\n—]+?)\s+—\s+', block, re.MULTILINE)
    if not title_m:
        title_m = re.search(r'^###\s+(.+?)\s*$', block, re.MULTILINE)

    url_m = re.search(r'^- \*\*URL\*\*:\s*([^\s]+)\s*$', block, re.MULTILINE)
    type_m = re.search(r'^- \*\*Type\*\*: `([^`]+)`$', block, re.MULTILINE)
    tags_line_m = re.search(r'^- \*\*Tags\*\*:\s*(.*)$', block, re.MULTILINE)
    tags_m = re.findall(r'#[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', tags_line_m.group(1)) if tags_line_m else []
    added_m = re.search(r'^- \*\*Added\*\*: (\d{4}-\d{2}-\d{2})$', block, re.MULTILINE)
    summary_m = re.search(
        r'^- \*\*Summary\*\*:\s*(.*?)(?=^- \*\*(?:Note|Source|Status)\*\*:|\Z)',
        block,
        re.DOTALL | re.MULTILINE,
    )
    shared_by_m = re.search(r'^- \*\*Shared by\*\*:\s*([^\r\n]+?)\s*$', block, re.MULTILINE)
    context_m = re.search(r'^- \*\*Context\*\*: `(work|personal)`$', block, re.MULTILINE)
    status_m = re.search(r'^- \*\*Status\*\*: `([^`]+)`$', block, re.MULTILINE)
    note_m = re.search(
        r'^- \*\*Note\*\*:\s*(.*?)(?=^- \*\*(?:Source|Status)\*\*:|\Z)',
        block,
        re.DOTALL | re.MULTILINE,
    )
    source_m = re.search(
        r'^- \*\*Source\*\*:\s*(.*?)(?=^- \*\*Status\*\*:|\Z)',
        block,
        re.DOTALL | re.MULTILINE,
    )

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
        shared_by=shared_by_m.group(1).strip() if shared_by_m else None,
        context=context_m.group(1) if context_m else None,
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
    return group_entries_by_date(get_all_entries())


def group_entries_by_date(entries: list[ArchiveEntry]) -> list[ArchiveDay]:
    """Group an entry list by date, newest first."""
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
    """Get topic tags with case-insensitive entry counts, sorted by popularity."""
    return get_filter_options()["tags"]


def _count_values(values_by_entry: list[list[str]]) -> list[tuple[str, int]]:
    """Count one occurrence per entry and retain the first useful display form."""
    display: dict[str, str] = {}
    counts: dict[str, int] = {}
    for values in values_by_entry:
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            key = cleaned.casefold()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            display.setdefault(key, cleaned)
            counts[key] = counts.get(key, 0) + 1
    return sorted(
        ((display[key], count) for key, count in counts.items()),
        key=lambda item: (-item[1], item[0].casefold()),
    )


def get_filter_options() -> dict[str, list[tuple[str, int]]]:
    """Build filter options and entry counts directly from the parsed vault."""
    entries = get_all_entries()
    return {
        "people": _count_values([[entry.shared_by] if entry.shared_by else [] for entry in entries]),
        "tags": _count_values([entry.tags for entry in entries]),
        "types": _count_values([[entry.entry_type] for entry in entries]),
    }


def filter_entries(
    entries: list[ArchiveEntry],
    *,
    query: str = "",
    context: str = "",
    shared_by: str = "",
    tag: str = "",
    entry_type: str = "",
) -> list[ArchiveEntry]:
    """Apply independent, combinable, case-insensitive dashboard filters."""
    query_key = query.strip().casefold()
    context_key = context.strip().casefold()
    sender_key = shared_by.strip().casefold()
    tag_key = tag.strip().lstrip("#").casefold()
    type_key = entry_type.strip().casefold()

    results: list[ArchiveEntry] = []
    for entry in entries:
        if context_key and (entry.context or "").casefold() != context_key:
            continue
        if sender_key and (entry.shared_by or "").casefold() != sender_key:
            continue
        if tag_key and not any(value.lstrip("#").casefold() == tag_key for value in entry.tags):
            continue
        if type_key and entry.entry_type.casefold() != type_key:
            continue
        if query_key and not _entry_matches_search(entry, query_key):
            continue
        results.append(entry)
    return results


def _entry_matches_search(entry: ArchiveEntry, query_key: str) -> bool:
    """Match the same fields supported by the original dashboard search."""
    return (
        query_key in entry.title.casefold()
        or query_key in entry.summary.casefold()
        or query_key in " ".join(entry.tags).casefold()
        or query_key in (entry.shared_by or "").casefold()
        or query_key in (entry.context or "").casefold()
        or any(query_key in tag.casefold() for tag in entry.tags)
    )


def search_entries(query: str) -> list[ArchiveEntry]:
    """Search entries by title, summary, tags, sharer, or context."""
    return filter_entries(get_all_entries(), query=query)


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
            "shared_by": e.shared_by,
            "context": e.context,
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
