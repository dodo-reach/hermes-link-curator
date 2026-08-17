from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SAVE_SCRIPT = ROOT / "skill-obsidian" / "scripts" / "save_entry.py"
DATE = "2026-08-17"


def run_save(vault: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HERMES_ARCHIVE_VAULT"] = str(vault)
    command = [
        sys.executable,
        str(SAVE_SCRIPT),
        "--url",
        "https://example.com",
        "--title",
        "Example entry",
        "--type",
        "article",
        "--tags",
        "testing productivity",
        "--added",
        DATE,
        "--summary",
        "Example summary.",
        *extra,
    ]
    return subprocess.run(command, env=env, text=True, capture_output=True, check=False)


def expected_entry(*metadata: str) -> str:
    lines = [
        "### Example entry",
        "- **URL**: https://example.com",
        "- **Type**: `article`",
        "- **Tags**: #testing #productivity",
        f"- **Added**: {DATE}",
        *metadata,
        "- **Summary**: Example summary.",
    ]
    return "\n".join(lines)


@pytest.mark.parametrize(
    ("arguments", "metadata"),
    [
        ((), ()),
        (("--shared-by", "Ibby"), ("- **Shared by**: Ibby",)),
        (("--context", "work"), ("- **Context**: `work`",)),
        (
            ("--shared-by", "Ibby", "--context", "personal"),
            ("- **Shared by**: Ibby", "- **Context**: `personal`"),
        ),
    ],
)
def test_save_optional_field_combinations(
    tmp_path: Path, arguments: tuple[str, ...], metadata: tuple[str, ...]
) -> None:
    vault = tmp_path / "vault"

    result = run_save(vault, *arguments)

    assert result.returncode == 0, result.stderr
    entry = expected_entry(*metadata)
    assert (vault / "INDEX.md").read_text() == f"# Index\n---\n{entry}\n---\n"
    assert (vault / f"{DATE}.md").read_text() == f"# {DATE}\n\n{entry}\n---\n"


def test_shared_by_is_trimmed_and_empty_value_is_omitted(tmp_path: Path) -> None:
    trimmed_vault = tmp_path / "trimmed"
    result = run_save(trimmed_vault, "--shared-by", "  Ibby  ")
    assert result.returncode == 0
    assert "- **Shared by**: Ibby\n" in (trimmed_vault / "INDEX.md").read_text()

    empty_vault = tmp_path / "empty"
    result = run_save(empty_vault, "--shared-by", "  \t  ")
    assert result.returncode == 0
    assert "**Shared by**" not in (empty_vault / "INDEX.md").read_text()


@pytest.mark.parametrize(
    "value",
    ["Ibby\n- **Context**: `work`", "Ibby\rInjected", "Ibby **URL**: https://evil.example"],
)
def test_invalid_shared_by_is_rejected_before_writes(tmp_path: Path, value: str) -> None:
    vault = tmp_path / "vault"

    result = run_save(vault, "--shared-by", value)

    assert result.returncode != 0
    assert not vault.exists()


def test_invalid_context_is_rejected_before_writes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"

    result = run_save(vault, "--context", "Work")

    assert result.returncode != 0
    assert "invalid choice" in result.stderr
    assert not vault.exists()


def test_metadata_order_and_separators_with_multiple_saves(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    first = run_save(vault, "--shared-by", "Ibby", "--context", "work")
    second = run_save(vault)
    assert first.returncode == second.returncode == 0

    index = (vault / "INDEX.md").read_text()
    daily = (vault / f"{DATE}.md").read_text()
    metadata_entry = expected_entry("- **Shared by**: Ibby", "- **Context**: `work`")

    assert metadata_entry in index
    assert metadata_entry in daily
    assert index.count("\n---\n") == 3
    assert index.endswith("\n---\n")
    assert daily.count("\n---\n") == 2
    assert daily.endswith("\n---\n")
    assert metadata_entry.index("**Added**") < metadata_entry.index("**Shared by**")
    assert metadata_entry.index("**Shared by**") < metadata_entry.index("**Context**")
    assert metadata_entry.index("**Context**") < metadata_entry.index("**Summary**")
