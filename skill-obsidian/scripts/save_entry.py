#!/usr/bin/env python3
"""Safely add one validated link to a curator vault."""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

from vault_ops import (
    DuplicateURLError,
    RecoveryError,
    VaultError,
    ensure_vault_directory,
    normalize_http_url,
    save_entry_locked,
    vault_lock,
)


# Auto-discover vault path:
# This script lives at <profile>/skills/note-taking/obsidian/scripts/save_entry.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))

VALID_TYPES = {"github", "x-post", "article", "tool", "video", "paper", "other"}
VALID_CONTEXTS = {"work", "personal"}
TAG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FIELD_MARKER_RE = re.compile(r"\*\*[^*\r\n]+\*\*\s*:")
STRUCTURAL_LINE_RE = re.compile(r"^(?:#{1,6}\s|---\s*$|-\s+\*\*[^*]+\*\*\s*:)")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely save an entry to the link curator vault.")
    parser.add_argument("--url", required=True, help="HTTP or HTTPS entry URL")
    parser.add_argument("--title", required=True, help="Entry title")
    parser.add_argument("--type", required=True, choices=sorted(VALID_TYPES))
    parser.add_argument("--tags", required=True, help="Space-separated lowercase topic tags")
    parser.add_argument("--added", required=True, help="Date in YYYY-MM-DD form")
    parser.add_argument("--summary", required=True, help="Single-line entry summary")
    parser.add_argument("--shared-by", default=None, help="Optional person who shared the entry")
    parser.add_argument("--context", choices=sorted(VALID_CONTEXTS), default=None)
    parser.add_argument("--note", default=None, help="Optional single-line note")
    parser.add_argument("--source", default=None, help="Optional single-line source")
    parser.add_argument("--status", default=None, help="Optional single-line status")
    return parser.parse_args(argv)


def _has_control(value: str) -> bool:
    return any(unicodedata.category(character).startswith("C") for character in value)


def _reject_structural_lines(name: str, value: str) -> None:
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if STRUCTURAL_LINE_RE.match(line.strip()):
            raise ValueError(f"{name} contains a Markdown structural line")


def _plain_single_line(
    name: str,
    value: str | None,
    *,
    required: bool = False,
    reject_backticks: bool = False,
    reject_field_markers: bool = False,
) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{name} must not be empty")
        return None
    if not value.strip() and not required:
        return None
    if "\r" in value or "\n" in value or _has_control(value):
        raise ValueError(f"{name} must be a single line without control characters")
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ValueError(f"{name} must not be empty")
        return None
    _reject_structural_lines(name, cleaned)
    if reject_field_markers and FIELD_MARKER_RE.search(cleaned):
        raise ValueError(f"{name} must not contain a Markdown field marker")
    if reject_backticks and "`" in cleaned:
        raise ValueError(f"{name} must not contain backticks")
    return cleaned


def _normalized_prose(name: str, value: str | None, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{name} must not be empty")
        return None
    if any(
        unicodedata.category(character).startswith("C") and character not in "\r\n\t"
        for character in value
    ):
        raise ValueError(f"{name} contains a control character")
    _reject_structural_lines(name, value)
    cleaned = " ".join(value.split())
    if not cleaned:
        if required:
            raise ValueError(f"{name} must not be empty")
        return None
    return cleaned


def _validated_url(value: str) -> tuple[str, str]:
    if not value or any(character.isspace() for character in value) or _has_control(value):
        raise ValueError("URL must not contain whitespace or control characters")
    normalized = normalize_http_url(value)
    return value, normalized


def _validated_tags(value: str) -> list[str]:
    if "\r" in value or "\n" in value or _has_control(value):
        raise ValueError("Tags must be a single line without control characters")
    raw_tokens = value.split()
    if not raw_tokens:
        raise ValueError("Tags must contain at least one topic tag")

    tags: list[str] = []
    seen: set[str] = set()
    for raw_token in raw_tokens:
        token = raw_token[1:] if raw_token.startswith("#") else raw_token
        if not TAG_RE.fullmatch(token):
            raise ValueError(
                f"unsafe tag {raw_token!r}; use lowercase letters, numbers, and internal hyphens"
            )
        if token not in seen:
            tags.append(token)
            seen.add(token)
    return tags


def validate_args(args: argparse.Namespace) -> tuple[argparse.Namespace, str]:
    """Validate and normalize every field without touching the filesystem."""
    args.url, normalized_url = _validated_url(args.url)
    args.title = _plain_single_line("Title", args.title, required=True)
    args.tags = _validated_tags(args.tags)
    args.summary = _normalized_prose("Summary", args.summary, required=True)
    args.shared_by = _plain_single_line("Shared by", args.shared_by, reject_field_markers=True)
    args.note = _normalized_prose("Note", args.note)
    args.source = _plain_single_line("Source", args.source)
    args.status = _plain_single_line("Status", args.status, reject_backticks=True)

    if args.type not in VALID_TYPES:
        raise ValueError(f"Type must be one of: {', '.join(sorted(VALID_TYPES))}")
    if args.context is not None and args.context not in VALID_CONTEXTS:
        raise ValueError("Context must be work or personal")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.added):
        raise ValueError("Added date must use YYYY-MM-DD")
    try:
        datetime.strptime(args.added, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Added date must be a real date in YYYY-MM-DD form") from exc
    return args, normalized_url


def format_tags(tags: list[str]) -> str:
    return " ".join(f"#{tag}" for tag in tags)


def build_entry_block(args: argparse.Namespace) -> str:
    lines = [
        f"### {args.title}",
        f"- **URL**: {args.url}",
        f"- **Type**: `{args.type}`",
        f"- **Tags**: {format_tags(args.tags)}",
        f"- **Added**: {args.added}",
    ]
    if args.shared_by:
        lines.append(f"- **Shared by**: {args.shared_by}")
    if args.context:
        lines.append(f"- **Context**: `{args.context}`")
    lines.append(f"- **Summary**: {args.summary}")
    if args.note:
        lines.append(f"- **Note**: {args.note}")
    if args.source:
        lines.append(f"- **Source**: {args.source}")
    if args.status:
        lines.append(f"- **Status**: `{args.status}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    try:
        args, normalized_url = validate_args(parse_args(argv))
        entry_block = build_entry_block(args)

        # Filesystem work starts only after every user-controlled field is valid.
        ensure_vault_directory(VAULT)
        with vault_lock(VAULT):
            daily, _ = save_entry_locked(VAULT, args.added, entry_block, normalized_url)
    except (ValueError, VaultError, OSError) as exc:
        prefix = "DUPLICATE" if isinstance(exc, DuplicateURLError) else "ERROR"
        print(f"{prefix}: {exc}", file=sys.stderr)
        if isinstance(exc, RecoveryError):
            print("Inspect the preserved transaction journal before retrying.", file=sys.stderr)
        return 1

    print(f"Saved to {daily.name} and INDEX.md")
    print(f"Done. {args.added}: {args.title[:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
