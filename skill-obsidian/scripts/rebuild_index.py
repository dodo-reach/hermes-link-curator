#!/usr/bin/env python3
"""Explicitly rebuild INDEX.md from canonical dated notes, with a backup."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from vault_ops import (
    JOURNAL_NAME,
    VaultError,
    atomic_replace_text,
    build_index_from_dated_notes_locked,
    create_index_backup_locked,
    ensure_vault_directory,
    vault_lock,
)


# Auto-discover vault path:
# This script lives at <profile>/skills/note-taking/obsidian/scripts/rebuild_index.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))
INDEX = VAULT / "INDEX.md"


def main() -> int:
    try:
        ensure_vault_directory(VAULT)
        with vault_lock(VAULT):
            journal = VAULT / JOURNAL_NAME
            if journal.exists():
                raise VaultError(
                    f"pending transaction exists at {journal}; reconcile it with save_entry.py "
                    "or inspect it before rebuilding"
                )

            existing = INDEX.read_text(encoding="utf-8") if INDEX.exists() else None
            rebuilt, count = build_index_from_dated_notes_locked(VAULT, existing)
            backup = create_index_backup_locked(VAULT, existing) if existing is not None else None
            atomic_replace_text(INDEX, rebuilt)
    except (OSError, VaultError) as exc:
        print(f"ERROR: INDEX.md rebuild failed: {exc}", file=sys.stderr)
        return 1

    if backup is not None:
        print(f"Backed up previous INDEX.md to {backup.name}")
    print(f"INDEX.md rebuilt from dated notes: {count} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
