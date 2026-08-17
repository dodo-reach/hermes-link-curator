from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
DATE = "2026-08-17"


def load_modules(monkeypatch: pytest.MonkeyPatch, vault: Path) -> tuple[ModuleType, ModuleType, ModuleType]:
    monkeypatch.setenv("HERMES_ARCHIVE_VAULT", str(vault))
    monkeypatch.syspath_prepend(str(DASHBOARD))
    for name in ("main", "validate", "archive"):
        sys.modules.pop(name, None)
    archive = importlib.import_module("archive")
    validate = importlib.import_module("validate")
    main = importlib.import_module("main")
    return archive, validate, main


def entry_block(
    title: str = "Example entry",
    *,
    shared_by: str | None = None,
    context: str | None = None,
    summary: str = "Example summary.",
    tags: str = "#testing #productivity",
    url: str = "https://example.com",
) -> str:
    lines = [
        f"### {title}",
        f"- **URL**: {url}",
        "- **Type**: `article`",
        f"- **Tags**: {tags}",
        f"- **Added**: {DATE}",
    ]
    if shared_by is not None:
        lines.append(f"- **Shared by**: {shared_by}")
    if context is not None:
        lines.append(f"- **Context**: `{context}`")
    lines.append(f"- **Summary**: {summary}")
    return "\n".join(lines)


def write_index(vault: Path, *entries: str) -> None:
    vault.mkdir(parents=True)
    body = "\n---\n".join(entries)
    (vault / "INDEX.md").write_text(f"# Index\n---\n{body}\n---\n")


@pytest.mark.parametrize(
    ("shared_by", "context"),
    [(None, None), ("Ibby", "work"), ("Ibby", None), (None, "personal")],
)
def test_parser_optional_field_combinations(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shared_by: str | None,
    context: str | None,
) -> None:
    archive, _, _ = load_modules(monkeypatch, tmp_path / "vault")

    parsed = archive._parse_entry(entry_block(shared_by=shared_by, context=context))

    assert parsed is not None
    assert parsed.shared_by == shared_by
    assert parsed.context == context


def test_parser_trims_shared_by_and_fields_are_position_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive, _, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block().replace(
        "- **Type**: `article`",
        "- **Context**: `work`\n- **Type**: `article`\n- **Shared by**:   Ibby   ",
    )

    parsed = archive._parse_entry(block)

    assert parsed is not None
    assert parsed.shared_by == "Ibby"
    assert parsed.context == "work"


def test_search_includes_shared_by_and_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Work link", shared_by="Ibby", context="work"),
        entry_block(
            "Weekend link",
            context="personal",
            url="https://example.com/personal",
            tags="#testing #weekend",
        ),
    )
    archive, _, _ = load_modules(monkeypatch, vault)

    assert [entry.title for entry in archive.search_entries("IBBY")] == ["Work link"]
    assert [entry.title for entry in archive.search_entries("WoRk")] == ["Work link"]
    assert [entry.title for entry in archive.search_entries("PERSONAL")] == ["Weekend link"]


@pytest.mark.parametrize(
    "line",
    [
        "- **Context**: work",
        "- **Context**: ``",
        "- **Context**: `Work`",
        "- **Context**: `social`",
        "- **Context**:",
        "- Context: `work`",
        "- *Context*: `work`",
        "- **Context** `work`",
        " - **Context**: `work`",
    ],
)
def test_validation_rejects_malformed_context_lines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, line: str
) -> None:
    _, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block().replace(f"- **Added**: {DATE}", f"- **Added**: {DATE}\n{line}")

    result = validate.validate_entry(block)

    assert not result.valid
    assert any("Context" in error for error in result.errors)


def test_validation_rejects_duplicate_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block(context="work").replace(
        "- **Context**: `work`", "- **Context**: `work`\n- **Context**: `personal`"
    )

    result = validate.validate_entry(block)

    assert not result.valid
    assert any("Context" in error for error in result.errors)


def test_validation_accepts_missing_fields_and_natural_context_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block(
        title="Context in distributed systems",
        summary="This summary discusses context and says it was shared by a colleague.",
    )

    result = validate.validate_entry(block)

    assert result.valid
    assert not result.errors
    assert not [warning for warning in result.warnings if "Context" in warning or "Shared by" in warning]


@pytest.mark.parametrize(
    "line",
    [
        "- **Shared by**:",
        "- Shared by: Ibby",
        "- *Shared by*: Ibby",
        "- **Shared by**:  Ibby",
        "- **Shared by**: Ibby ",
        "- **Shared by**: Ibby **URL**: https://evil.example",
        "- **Shared by**: Ibby\rInjected",
    ],
)
def test_validation_rejects_malformed_shared_by(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, line: str
) -> None:
    _, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block().replace(f"- **Added**: {DATE}", f"- **Added**: {DATE}\n{line}")

    result = validate.validate_entry(block)

    assert not result.valid
    assert any("Shared by" in error for error in result.errors)


def test_validation_rejects_duplicate_shared_by(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block(shared_by="Ibby").replace(
        "- **Shared by**: Ibby", "- **Shared by**: Ibby\n- **Shared by**: Alice"
    )

    result = validate.validate_entry(block)

    assert not result.valid
    assert any("Shared by" in error for error in result.errors)


def test_dashboard_views_and_json_endpoints(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Work link", shared_by="Ibby <script>", context="work"),
        entry_block(
            "Personal link",
            context="personal",
            url="https://example.com/personal",
            tags="#testing #personal-tag",
        ),
        entry_block(
            "Plain link",
            url="https://example.com/plain",
            tags="#testing #plain",
        ),
    )
    _, _, main = load_modules(monkeypatch, vault)
    client = TestClient(main.app)

    for path in ("/", "/search?q=Ibby", "/tag/testing", f"/day/{DATE}"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Work" in response.text
        assert "Shared by: Ibby &lt;script&gt;" in response.text
        assert "Ibby <script>" not in response.text
        assert "card.classList.toggle('is-expanded')" in response.text

    list_html = client.get("/").text
    assert list_html.count('class="entry-context"') == 2
    assert list_html.count('class="entry-shared-by"') == 1

    calendar = client.get("/calendar")
    assert calendar.status_code == 200
    assert "if (entry.context)" in calendar.text
    assert "if (entry.shared_by)" in calendar.text
    assert "sharedBy.textContent = 'Shared by: ' + entry.shared_by" in calendar.text

    day_json = client.get(f"/day-json/{DATE}")
    assert day_json.status_code == 200
    entries = day_json.json()
    assert entries[0]["shared_by"] == "Ibby <script>"
    assert entries[0]["context"] == "work"
    assert entries[2]["shared_by"] is None
    assert entries[2]["context"] is None

    graph = client.get("/graph-json")
    assert graph.status_code == 200
    nodes = graph.json()["nodes"]
    entry_nodes = [node for node in nodes if node["kind"] == "entry"]
    tag_nodes = [node for node in nodes if node["kind"] == "tag"]
    assert entry_nodes
    assert all("shared_by" in node and "context" in node for node in entry_nodes)
    assert all("shared_by" not in node and "context" not in node for node in tag_nodes)

    stats = client.get("/stats")
    assert stats.status_code == 200
    assert stats.json()["by_context"] == {"work": 1, "personal": 1}

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {
        "status": "healthy",
        "vault_path": str(vault),
        "total_entries": 3,
        "total_days": 1,
    }
