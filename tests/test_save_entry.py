from __future__ import annotations

import os
import json
import importlib
import fcntl
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SAVE_SCRIPT = ROOT / "skill-obsidian" / "scripts" / "save_entry.py"
DATE = "2026-08-17"


def run_save(
    vault: Path,
    *extra: str,
    url: str = "https://example.com",
    title: str = "Example entry",
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HERMES_ARCHIVE_VAULT"] = str(vault)
    command = [
        sys.executable,
        str(SAVE_SCRIPT),
        "--url",
        url,
        "--title",
        title,
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


def expected_entry(*metadata: str, url: str = "https://example.com", title: str = "Example entry") -> str:
    lines = [
        f"### {title}",
        f"- **URL**: {url}",
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
    second = run_save(vault, url="https://example.com/second", title="Second entry")
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


def test_normal_save_uses_restrictive_files_and_leaves_no_transaction_temps(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    result = run_save(vault)

    assert result.returncode == 0, result.stderr
    assert (vault / f"{DATE}.md").stat().st_mode & 0o777 == 0o600
    assert (vault / "INDEX.md").stat().st_mode & 0o777 == 0o600
    assert not (vault / ".link-curator-transaction.json").exists()
    assert not list(vault.glob(".*.tmp"))


def test_two_concurrent_distinct_saves_are_both_preserved(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda item: run_save(vault, url=item[0], title=item[1]),
                [
                    ("https://example.com/one", "Entry one"),
                    ("https://example.com/two", "Entry two"),
                ],
            )
        )

    assert [result.returncode for result in results] == [0, 0]
    for filename in (f"{DATE}.md", "INDEX.md"):
        content = (vault / filename).read_text()
        assert content.count("https://example.com/one") == 1
        assert content.count("https://example.com/two") == 1


def test_two_concurrent_duplicate_saves_store_exactly_one(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_save(vault), range(2)))

    assert sorted(result.returncode for result in results) == [0, 1]
    assert "DUPLICATE" in next(result.stderr for result in results if result.returncode)
    for filename in (f"{DATE}.md", "INDEX.md"):
        assert (vault / filename).read_text().count("https://example.com") == 1


def test_duplicate_does_not_modify_markdown_files(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    assert run_save(vault).returncode == 0
    before = {path.name: path.read_bytes() for path in vault.glob("*.md")}

    result = run_save(vault, url="HTTPS://EXAMPLE.COM:443")

    assert result.returncode == 1
    assert "DUPLICATE" in result.stderr
    assert {path.name: path.read_bytes() for path in vault.glob("*.md")} == before


def load_save_modules(monkeypatch: pytest.MonkeyPatch, vault: Path):
    scripts = SAVE_SCRIPT.parent
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.setenv("HERMES_ARCHIVE_VAULT", str(vault))
    for name in ("save_entry", "vault_ops"):
        sys.modules.pop(name, None)
    vault_ops = importlib.import_module("vault_ops")
    save_entry = importlib.import_module("save_entry")
    return vault_ops, save_entry


def default_argv(*extra: str) -> list[str]:
    return [
        "--url", "https://example.com",
        "--title", "Example entry",
        "--type", "article",
        "--tags", "testing productivity",
        "--added", DATE,
        "--summary", "Example summary.",
        *extra,
    ]


def assert_lock_is_held(vault_ops, vault: Path) -> None:
    descriptor = os.open(vault / vault_ops.LOCK_NAME, os.O_RDWR)
    try:
        with pytest.raises(BlockingIOError):
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def test_lock_covers_duplicate_check_and_both_markdown_replacements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, save_entry = load_save_modules(monkeypatch, vault)
    observed: list[str] = []
    original_duplicate = vault_ops.find_duplicate_url_locked
    original_replace = vault_ops.atomic_replace_text

    def checked_duplicate(*args, **kwargs):
        assert_lock_is_held(vault_ops, vault)
        observed.append("duplicate")
        return original_duplicate(*args, **kwargs)

    def checked_replace(target, *args, **kwargs):
        if target.name in {f"{DATE}.md", "INDEX.md"}:
            assert_lock_is_held(vault_ops, vault)
            observed.append(target.name)
        return original_replace(target, *args, **kwargs)

    monkeypatch.setattr(vault_ops, "find_duplicate_url_locked", checked_duplicate)
    monkeypatch.setattr(vault_ops, "atomic_replace_text", checked_replace)

    assert save_entry.main(default_argv()) == 0
    assert observed == ["duplicate", f"{DATE}.md", "INDEX.md"]


def simulate_interruption(monkeypatch: pytest.MonkeyPatch, vault: Path, fail_target: str):
    vault_ops, save_entry = load_save_modules(monkeypatch, vault)
    original_replace = vault_ops.atomic_replace_text

    def interrupted(target, *args, **kwargs):
        if target.name == fail_target:
            raise OSError(f"simulated failure replacing {fail_target}")
        return original_replace(target, *args, **kwargs)

    monkeypatch.setattr(vault_ops, "atomic_replace_text", interrupted)
    assert save_entry.main(default_argv()) == 1
    monkeypatch.setattr(vault_ops, "atomic_replace_text", original_replace)
    return vault_ops, save_entry


def test_failure_before_first_markdown_replacement_recovers_prewrite_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, _ = simulate_interruption(monkeypatch, vault, f"{DATE}.md")
    assert (vault / vault_ops.JOURNAL_NAME).exists()
    assert not (vault / f"{DATE}.md").exists()
    assert not (vault / "INDEX.md").exists()

    with vault_ops.vault_lock(vault):
        assert vault_ops.recover_pending_locked(vault)
        assert not vault_ops.recover_pending_locked(vault)
    assert not (vault / vault_ops.JOURNAL_NAME).exists()


def test_failure_after_daily_replacement_repairs_only_pending_index_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, _ = simulate_interruption(monkeypatch, vault, "INDEX.md")
    daily_before = (vault / f"{DATE}.md").read_bytes()
    assert not (vault / "INDEX.md").exists()

    with vault_ops.vault_lock(vault):
        assert vault_ops.recover_pending_locked(vault)
    assert (vault / f"{DATE}.md").read_bytes() == daily_before
    assert (vault / "INDEX.md").read_text().count("https://example.com") == 1
    assert not (vault / vault_ops.JOURNAL_NAME).exists()


def test_recovery_repairs_index_only_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, _ = simulate_interruption(monkeypatch, vault, f"{DATE}.md")
    journal = json.loads((vault / vault_ops.JOURNAL_NAME).read_text())
    index_after = vault_ops.prepend_entry_to_index(None, journal["entry_block"])
    vault_ops.atomic_replace_text(vault / "INDEX.md", index_after)

    with vault_ops.vault_lock(vault):
        assert vault_ops.recover_pending_locked(vault)
    assert (vault / f"{DATE}.md").read_text().count("https://example.com") == 1
    assert not (vault / vault_ops.JOURNAL_NAME).exists()


def test_recovery_clears_journal_when_both_files_reached_expected_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, save_entry = load_save_modules(monkeypatch, vault)
    original_clear = vault_ops._clear_completed_journal

    def interrupted_clear(*_args, **_kwargs):
        raise OSError("simulated interruption before journal removal")

    monkeypatch.setattr(vault_ops, "_clear_completed_journal", interrupted_clear)
    assert save_entry.main(default_argv()) == 1
    daily_before = (vault / f"{DATE}.md").read_bytes()
    index_before = (vault / "INDEX.md").read_bytes()
    assert (vault / vault_ops.JOURNAL_NAME).exists()

    monkeypatch.setattr(vault_ops, "_clear_completed_journal", original_clear)
    with vault_ops.vault_lock(vault):
        assert vault_ops.recover_pending_locked(vault)
    assert (vault / f"{DATE}.md").read_bytes() == daily_before
    assert (vault / "INDEX.md").read_bytes() == index_before
    assert not (vault / vault_ops.JOURNAL_NAME).exists()


def test_malformed_or_ambiguous_transaction_is_preserved(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    marker = vault / ".link-curator-transaction.json"
    marker.write_text("{not-json\n")
    original = marker.read_bytes()

    result = run_save(vault)

    assert result.returncode == 1
    assert "preserve" in result.stderr
    assert marker.read_bytes() == original
    assert not list(vault.glob("*.md"))


def test_changed_prewrite_state_preserves_transaction(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    vault_ops, _ = simulate_interruption(monkeypatch, vault, f"{DATE}.md")
    marker = vault / vault_ops.JOURNAL_NAME
    (vault / "INDEX.md").write_text("# manually changed\n---\n")

    with vault_ops.vault_lock(vault), pytest.raises(vault_ops.RecoveryError):
        vault_ops.recover_pending_locked(vault)
    assert marker.exists()


def test_manual_rebuild_backs_up_existing_index_and_matches_dated_notes(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    assert run_save(vault, url="https://example.com/one", title="One").returncode == 0
    assert run_save(vault, url="https://example.com/two", title="Two").returncode == 0
    old_index = (vault / "INDEX.md").read_bytes()
    (vault / "INDEX.md").write_text("# Custom index\n---\n### index-only\n- **URL**: https://index.example\n---\n")
    replaced = (vault / "INDEX.md").read_bytes()

    env = os.environ.copy()
    env["HERMES_ARCHIVE_VAULT"] = str(vault)
    result = subprocess.run(
        [sys.executable, str(SAVE_SCRIPT.parent / "rebuild_index.py")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    backups = list(vault.glob("INDEX.md.backup-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == replaced
    rebuilt = (vault / "INDEX.md").read_text()
    assert rebuilt.startswith("# Custom index\n---\n")
    assert rebuilt.count("https://example.com/one") == 1
    assert rebuilt.count("https://example.com/two") == 1
    assert "https://index.example" not in rebuilt
    assert old_index != replaced


def test_manual_rebuild_refuses_pending_transaction_without_changing_index(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    assert run_save(vault).returncode == 0
    index_before = (vault / "INDEX.md").read_bytes()
    marker = vault / ".link-curator-transaction.json"
    marker.write_text("{unresolved\n")
    env = os.environ.copy()
    env["HERMES_ARCHIVE_VAULT"] = str(vault)

    result = subprocess.run(
        [sys.executable, str(SAVE_SCRIPT.parent / "rebuild_index.py")],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "pending transaction" in result.stderr
    assert (vault / "INDEX.md").read_bytes() == index_before
    assert marker.exists()


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_http_and_https_urls_are_accepted(tmp_path: Path, scheme: str) -> None:
    result = run_save(tmp_path / scheme, url=f"{scheme}://example.com/path?a=1")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,hello", "file:///tmp/a", "https:///missing-host", "https://example.com/line\nfeed"],
)
def test_unsafe_urls_are_rejected_before_writes(tmp_path: Path, url: str) -> None:
    vault = tmp_path / "vault"
    result = run_save(vault, url=url)
    assert result.returncode != 0
    assert not vault.exists()


@pytest.mark.parametrize("tag", ["AI", "bad_tag", "bad/tag", "-leading", "trailing-", "##double"])
def test_unsafe_tags_are_rejected_before_writes(tmp_path: Path, tag: str) -> None:
    vault = tmp_path / "vault"
    result = run_save(vault, "--tags", tag)
    assert result.returncode != 0
    assert not vault.exists()


def test_valid_hyphenated_and_explicit_extra_tags_are_preserved(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    result = run_save(vault, "--tags", "ai-security dev-tools local-ai fourth-tag")
    assert result.returncode == 0
    assert "#ai-security #dev-tools #local-ai #fourth-tag" in (vault / "INDEX.md").read_text()


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--title", "Title\n### injected"),
        ("--added", f"{DATE}\n---"),
        ("--shared-by", "Ibby\n- **Context**: `work`"),
        ("--source", "source\r- **URL**: https://evil.example"),
        ("--status", "done\n### injected"),
    ],
)
def test_single_line_fields_reject_structure_injection_before_writes(
    tmp_path: Path, flag: str, value: str
) -> None:
    vault = tmp_path / "vault"
    result = run_save(vault, flag, value)
    assert result.returncode != 0
    assert not vault.exists()


def test_summary_and_note_whitespace_is_normalized_without_structure(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    result = run_save(
        vault,
        "--summary", "A long\n but benign\t summary.",
        "--note", "Some\n benign note.",
    )
    assert result.returncode == 0, result.stderr
    content = (vault / "INDEX.md").read_text()
    assert "- **Summary**: A long but benign summary." in content
    assert "- **Note**: Some benign note." in content
