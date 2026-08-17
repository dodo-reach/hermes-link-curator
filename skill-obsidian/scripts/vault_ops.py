"""Concurrency-safe vault writes and targeted transaction recovery."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlsplit, urlunsplit


INDEX_HEADER = "# Index\n---\n"
LOCK_NAME = ".link-curator.lock"
JOURNAL_NAME = ".link-curator-transaction.json"
JOURNAL_VERSION = 1
DATE_FILE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\.md")
URL_LINE_RE = re.compile(r"^- \*\*URL\*\*:\s*(\S+)\s*$", re.MULTILINE)


class VaultError(RuntimeError):
    """Base class for actionable vault-operation errors."""


class DuplicateURLError(VaultError):
    """Raised when a normalized URL is already present in the vault."""


class RecoveryError(VaultError):
    """Raised when a pending transaction cannot be reconciled safely."""


def normalize_http_url(value: str) -> str:
    """Normalize only URL components that are safe for duplicate comparison."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"invalid URL: {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https and include a hostname")

    hostname = parsed.hostname.lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    userinfo = ""
    if parsed.username is not None:
        userinfo = parsed.username
        if parsed.password is not None:
            userinfo += f":{parsed.password}"
        userinfo += "@"

    return urlunsplit((scheme, f"{userinfo}{host}", parsed.path or "/", parsed.query, parsed.fragment))


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ensure_vault_directory(vault: Path) -> None:
    vault.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not vault.is_dir() or vault.is_symlink():
        raise VaultError(f"vault path is not a safe directory: {vault}")
    vault.chmod(0o700)


@contextmanager
def vault_lock(vault: Path) -> Iterator[None]:
    """Acquire the one vault-scoped advisory lock used by all writers."""
    lock_path = vault / LOCK_NAME
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "r+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            yield
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def atomic_replace_text(target: Path, content: str, temporary_name: str | None = None) -> None:
    """Durably replace one text file without writing through the final path."""
    if temporary_name is None:
        temporary_name = f".{target.name}.{uuid.uuid4().hex}.tmp"
    if Path(temporary_name).name != temporary_name:
        raise VaultError("temporary filename must be a basename")

    temporary = target.parent / temporary_name
    fd = -1
    replaced = False
    try:
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        replaced = True
        target.chmod(0o600)
        _fsync_directory(target.parent)
    finally:
        if fd >= 0:
            os.close(fd)
        if not replaced:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _read_optional(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _state(content: str | None) -> dict[str, object]:
    return {
        "exists": content is not None,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content is not None else None,
    }


def _state_matches(content: str | None, expected: object) -> bool:
    return isinstance(expected, dict) and expected == _state(content)


def append_entry_to_daily(content: str | None, date: str, entry_block: str) -> str:
    entry_with_separator = entry_block.rstrip("\n") + "\n---\n"
    if content is None:
        return f"# {date}\n\n{entry_with_separator}"

    base = content.rstrip("\n")
    if not base.endswith("---"):
        base += "\n---"
    return base + "\n" + entry_with_separator


def prepend_entry_to_index(content: str | None, entry_block: str) -> str:
    if content is None:
        content = INDEX_HEADER
    lines = content.splitlines()
    separator_index = next((i for i, line in enumerate(lines) if line.strip() == "---"), None)
    if separator_index is None:
        raise VaultError("INDEX.md is missing its first '---' separator")
    entry_with_separator = entry_block.rstrip("\n") + "\n---"
    new_lines = lines[: separator_index + 1] + [entry_with_separator] + lines[separator_index + 1 :]
    return "\n".join(new_lines) + "\n"


def _normalized_urls(content: str | None) -> list[str]:
    if content is None:
        return []
    normalized: list[str] = []
    for match in URL_LINE_RE.finditer(content):
        try:
            normalized.append(normalize_http_url(match.group(1)))
        except ValueError:
            continue
    return normalized


def _entry_count(content: str | None, normalized_url: str) -> int:
    return _normalized_urls(content).count(normalized_url)


def find_duplicate_url_locked(vault: Path, normalized_url: str) -> Path | None:
    """Find a URL while the caller holds the vault lock."""
    candidates = sorted(
        (path for path in vault.glob("*.md") if DATE_FILE_RE.fullmatch(path.name)),
        key=lambda path: path.name,
    )
    index = vault / "INDEX.md"
    if index.exists():
        candidates.append(index)
    for path in candidates:
        if normalized_url in _normalized_urls(_read_optional(path)):
            return path
    return None


def _write_journal(vault: Path, journal: dict[str, object]) -> None:
    transaction_id = str(journal["transaction_id"])
    content = json.dumps(journal, sort_keys=True, indent=2) + "\n"
    atomic_replace_text(vault / JOURNAL_NAME, content, f".{JOURNAL_NAME}.{transaction_id}.tmp")


def _load_journal(vault: Path) -> dict[str, object] | None:
    path = vault / JOURNAL_NAME
    content = _read_optional(path)
    if content is None:
        return None
    try:
        journal = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RecoveryError(
            f"cannot parse pending transaction {path}; preserve it for inspection: {exc}"
        ) from exc

    required = {
        "version",
        "transaction_id",
        "date",
        "daily_file",
        "normalized_url",
        "entry_block",
        "daily_before",
        "daily_after",
        "index_before",
        "index_after",
        "daily_temp",
        "index_temp",
    }
    if not isinstance(journal, dict) or set(journal) != required:
        raise RecoveryError(f"pending transaction {path} has an unsupported schema; preserve it")
    if journal["version"] != JOURNAL_VERSION:
        raise RecoveryError(f"pending transaction {path} has unsupported version {journal['version']!r}")

    transaction_id = journal["transaction_id"]
    date = journal["date"]
    if not isinstance(transaction_id, str) or not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise RecoveryError(f"pending transaction {path} has an invalid transaction ID")
    if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise RecoveryError(f"pending transaction {path} has an invalid date")
    if journal["daily_file"] != f"{date}.md":
        raise RecoveryError(f"pending transaction {path} has an unsafe daily filename")
    for name in ("daily_temp", "index_temp"):
        value = journal[name]
        if not isinstance(value, str) or Path(value).name != value:
            raise RecoveryError(f"pending transaction {path} has an unsafe temporary filename")
    if not isinstance(journal["entry_block"], str) or not isinstance(journal["normalized_url"], str):
        raise RecoveryError(f"pending transaction {path} has invalid entry data")
    entry_urls = _normalized_urls(journal["entry_block"])
    if entry_urls != [journal["normalized_url"]]:
        raise RecoveryError(f"pending transaction {path} entry data does not match its URL")
    for name in ("daily_before", "daily_after", "index_before", "index_after"):
        state = journal[name]
        if not isinstance(state, dict) or set(state) != {"exists", "sha256"}:
            raise RecoveryError(f"pending transaction {path} has invalid state metadata")
    return journal


def _clear_completed_journal(vault: Path, journal: dict[str, object]) -> None:
    for name in ("daily_temp", "index_temp"):
        try:
            (vault / str(journal[name])).unlink()
        except FileNotFoundError:
            pass
    (vault / JOURNAL_NAME).unlink()
    _fsync_directory(vault)


def recover_pending_locked(vault: Path) -> bool:
    """Reconcile exactly one journaled entry while the caller holds the lock."""
    journal = _load_journal(vault)
    if journal is None:
        return False

    daily_path = vault / str(journal["daily_file"])
    index_path = vault / "INDEX.md"
    daily_content = _read_optional(daily_path)
    index_content = _read_optional(index_path)
    normalized_url = str(journal["normalized_url"])
    daily_count = _entry_count(daily_content, normalized_url)
    index_count = _entry_count(index_content, normalized_url)

    if daily_count > 1 or index_count > 1:
        raise RecoveryError(
            f"pending transaction is ambiguous: {normalized_url} appears more than once; "
            f"journal preserved at {vault / JOURNAL_NAME}"
        )

    daily_has = daily_count == 1
    index_has = index_count == 1
    entry_block = str(journal["entry_block"])

    if daily_has and not index_has:
        if not _state_matches(daily_content, journal["daily_after"]) or not _state_matches(
            index_content, journal["index_before"]
        ):
            raise RecoveryError("dated note/index no longer match the pending transaction; journal preserved")
        repaired = prepend_entry_to_index(index_content, entry_block)
        if not _state_matches(repaired, journal["index_after"]):
            raise RecoveryError("pending index repair does not match the journal; journal preserved")
        atomic_replace_text(index_path, repaired, str(journal["index_temp"]))
    elif index_has and not daily_has:
        if not _state_matches(index_content, journal["index_after"]) or not _state_matches(
            daily_content, journal["daily_before"]
        ):
            raise RecoveryError("index/dated note no longer match the pending transaction; journal preserved")
        repaired = append_entry_to_daily(daily_content, str(journal["date"]), entry_block)
        if not _state_matches(repaired, journal["daily_after"]):
            raise RecoveryError("pending dated-note repair does not match the journal; journal preserved")
        atomic_replace_text(daily_path, repaired, str(journal["daily_temp"]))
    elif daily_has and index_has:
        if not _state_matches(daily_content, journal["daily_after"]) or not _state_matches(
            index_content, journal["index_after"]
        ):
            raise RecoveryError("completed files differ from the pending transaction; journal preserved")
    else:
        if not _state_matches(daily_content, journal["daily_before"]) or not _state_matches(
            index_content, journal["index_before"]
        ):
            raise RecoveryError("files do not match the journaled pre-write state; journal preserved")

    daily_content = _read_optional(daily_path)
    index_content = _read_optional(index_path)
    if daily_has or index_has:
        if not _state_matches(daily_content, journal["daily_after"]) or not _state_matches(
            index_content, journal["index_after"]
        ):
            raise RecoveryError("transaction reconciliation did not reach its expected state; journal preserved")

    _clear_completed_journal(vault, journal)
    return True


def save_entry_locked(vault: Path, date: str, entry_block: str, normalized_url: str) -> tuple[Path, Path]:
    """Save one entry while the caller holds the vault lock."""
    recover_pending_locked(vault)
    duplicate_path = find_duplicate_url_locked(vault, normalized_url)
    if duplicate_path is not None:
        raise DuplicateURLError(f"URL already exists in {duplicate_path.name}: {normalized_url}")

    daily_path = vault / f"{date}.md"
    index_path = vault / "INDEX.md"
    daily_before = _read_optional(daily_path)
    index_before = _read_optional(index_path)
    daily_after = append_entry_to_daily(daily_before, date, entry_block)
    index_after = prepend_entry_to_index(index_before, entry_block)
    transaction_id = uuid.uuid4().hex
    journal: dict[str, object] = {
        "version": JOURNAL_VERSION,
        "transaction_id": transaction_id,
        "date": date,
        "daily_file": daily_path.name,
        "normalized_url": normalized_url,
        "entry_block": entry_block,
        "daily_before": _state(daily_before),
        "daily_after": _state(daily_after),
        "index_before": _state(index_before),
        "index_after": _state(index_after),
        "daily_temp": f".{daily_path.name}.{transaction_id}.tmp",
        "index_temp": f".{index_path.name}.{transaction_id}.tmp",
    }
    _write_journal(vault, journal)
    atomic_replace_text(daily_path, daily_after, str(journal["daily_temp"]))
    atomic_replace_text(index_path, index_after, str(journal["index_temp"]))
    _clear_completed_journal(vault, journal)
    return daily_path, index_path


def _daily_entry_blocks(content: str) -> list[str]:
    blocks: list[str] = []
    for segment in re.split(r"(?=^### )", content.replace("\r\n", "\n").replace("\r", "\n"), flags=re.MULTILINE):
        segment = segment.strip()
        if not segment.startswith("### ") or not URL_LINE_RE.search(segment):
            continue
        segment = re.sub(r"\n---\s*$", "", segment).rstrip("\n")
        blocks.append(segment)
    return blocks


def build_index_from_dated_notes_locked(vault: Path, existing_index: str | None) -> tuple[str, int]:
    """Build index content from dated notes while the caller holds the lock."""
    entries: list[str] = []
    days = sorted(
        (path for path in vault.glob("*.md") if DATE_FILE_RE.fullmatch(path.name)),
        key=lambda path: path.name,
        reverse=True,
    )
    for day in days:
        entries.extend(reversed(_daily_entry_blocks(day.read_text(encoding="utf-8"))))

    header = INDEX_HEADER
    if existing_index is not None:
        lines = existing_index.splitlines()
        separator_index = next((i for i, line in enumerate(lines) if line.strip() == "---"), None)
        if separator_index is not None:
            header = "\n".join(lines[: separator_index + 1]) + "\n"
    body = "".join(f"{entry}\n---\n" for entry in entries)
    return header + body, len(entries)


def create_index_backup_locked(vault: Path, content: str) -> Path:
    """Durably back up an existing index while the caller holds the lock."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = vault / f"INDEX.md.backup-{timestamp}"
    counter = 1
    while candidate.exists():
        candidate = vault / f"INDEX.md.backup-{timestamp}-{counter}"
        counter += 1

    fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            fd = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(vault)
    finally:
        if fd >= 0:
            os.close(fd)
    return candidate
