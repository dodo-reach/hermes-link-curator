#!/usr/bin/env python3
"""
Atomic save for link curator vault entries.
Appends to daily note AND prepends to INDEX.md using read+patch (never overwrite).

Usage:
    python3 save_entry.py --url "https://..." --title "Title" --type "article" \
        --tags "ai dev-tools" --added "2026-06-04" --summary "What it is"

Tags are space-separated, with # prefix optional.
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Auto-discover vault path:
# This script lives at <profile>/skills/note-taking/obsidian/scripts/save_entry.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))
INDEX = VAULT / "INDEX.md"
INDEX_HEADER = "# Index\n---\n"


def parse_args():
    p = argparse.ArgumentParser(description="Atomically save an entry to the link curator vault.")
    p.add_argument("--url", required=True, help="Entry URL")
    p.add_argument("--title", required=True, help="Entry title")
    p.add_argument("--type", required=True, help="Entry type: github|x-post|article|tool|video|paper|other")
    p.add_argument("--tags", required=True, help="Space-separated tags, # prefix optional")
    p.add_argument("--added", required=True, help="Date: YYYY-MM-DD")
    p.add_argument("--summary", required=True, help="Entry summary")
    p.add_argument("--note", default=None, help="Optional note")
    p.add_argument("--source", default=None, help="Optional source field")
    p.add_argument("--status", default=None, help="Optional status field")
    return p.parse_args()


def format_tags(tag_str: str) -> str:
    """Normalize tags: ensure # prefix, lowercase, deduplicate."""
    seen = set()
    parts = tag_str.split()
    formatted = []
    for t in parts:
        t = t.lower().lstrip("#")
        if t and t not in seen:
            seen.add(t)
            formatted.append(f"#{t}")
    return " ".join(formatted)


def build_entry_block(args) -> str:
    """Build the full markdown entry block."""
    tags = format_tags(args.tags)
    lines = [
        f"### {args.title}",
        f"- **URL**: {args.url}",
        f"- **Type**: `{args.type}`",
        f"- **Tags**: {tags}",
        f"- **Added**: {args.added}",
        f"- **Summary**: {args.summary}",
    ]
    if args.note:
        lines.append(f"- **Note**: {args.note}")
    if args.source:
        lines.append(f"- **Source**: {args.source}")
    if args.status:
        lines.append(f"- **Status**: `{args.status}`")
    return "\n".join(lines) + "\n"


def append_to_daily(entry_block: str, date: str) -> Path:
    """Append entry to YYYY-MM-DD.md daily note, creating it if needed."""
    VAULT.mkdir(parents=True, exist_ok=True)
    daily = VAULT / f"{date}.md"
    header = f"# {date}\n\n"
    entry_with_sep = entry_block.rstrip("\n") + "\n---\n"
    if daily.exists():
        content = daily.read_text().rstrip("\n")
        if not content.endswith("---"):
            content += "\n---\n"
        else:
            content += "\n"
        daily.write_text(content + entry_with_sep)
    else:
        daily.write_text(header + entry_with_sep)
    return daily


def prepend_to_index(entry_block: str) -> None:
    """
    Prepend entry to INDEX.md using read+patch.
    Creates the vault and INDEX.md on first use.
    """
    VAULT.mkdir(parents=True, exist_ok=True)
    if not INDEX.exists():
        INDEX.write_text(INDEX_HEADER)

    content = INDEX.read_text()
    lines = content.splitlines()

    # Find the first "---" separator (after any header line)
    sep_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "---":
            sep_idx = i
            break

    if sep_idx is None:
        raise ValueError("INDEX.md missing '---' separator")

    # Insert the new entry block after the first separator.
    # Using [:sep_idx+1] consumes the first --- so it acts as the closing
    # boundary for the previous chunk, and the new entry + its trailing ---
    # becomes the first independent chunk.
    entry_with_sep = entry_block.rstrip("\n") + "\n---"
    new_lines = lines[:sep_idx + 1] + [entry_with_sep] + lines[sep_idx + 1:]
    INDEX.write_text("\n".join(new_lines) + "\n")


def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main():
    args = parse_args()

    if not validate_date(args.added):
        print(f"ERROR: Invalid date '{args.added}' (expected YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)

    if not validate_url(args.url):
        print("ERROR: Invalid URL (expected http:// or https://)", file=sys.stderr)
        sys.exit(1)

    valid_types = {"github", "x-post", "article", "tool", "video", "paper", "other"}
    if args.type not in valid_types:
        print(f"ERROR: Invalid type '{args.type}' (must be one of {valid_types})", file=sys.stderr)
        sys.exit(1)

    entry_block = build_entry_block(args)

    # Write to daily note first
    daily = append_to_daily(entry_block, args.added)
    print(f"Appended to {daily.name}")

    # Then prepend to INDEX (the safety-critical step)
    prepend_to_index(entry_block)
    print(f"Prepended to INDEX.md")

    print(f"\nDone. {args.added}: {args.title[:60]}")


if __name__ == "__main__":
    main()
