from __future__ import annotations

import importlib
import hashlib
import re
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
    entry_type: str = "article",
    added: str = DATE,
) -> str:
    lines = [
        f"### {title}",
        f"- **URL**: {url}",
        f"- **Type**: `{entry_type}`",
        f"- **Tags**: {tags}",
        f"- **Added**: {added}",
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


def test_parser_keeps_summary_note_source_and_status_separate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive, validate, _ = load_modules(monkeypatch, tmp_path / "vault")
    block = entry_block(summary="Full summary with\na second line.") + (
        "\n- **Note**: A preserved note."
        "\n- **Source**: User supplied source."
        "\n- **Status**: `reviewed`"
    )

    parsed = archive._parse_entry(block)

    assert parsed is not None
    assert parsed.summary == "Full summary with\na second line."
    assert parsed.note == "A preserved note."
    assert parsed.source == "User supplied source."
    assert parsed.status == "reviewed"
    assert validate.validate_entry(block).valid


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


def make_dashboard_client(monkeypatch: pytest.MonkeyPatch, vault: Path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    archive, _, main = load_modules(monkeypatch, vault)
    return archive, main, TestClient(main.app)


def filter_fixture(vault: Path) -> None:
    write_index(
        vault,
        entry_block(
            "Prompt defense",
            shared_by="Ibby",
            context="work",
            summary="A practical prompt security guide.",
            tags="#ai #ai-security #python #extra",
            url="https://example.com/work",
        ),
        entry_block(
            "Personal photos",
            shared_by="Mario",
            context="personal",
            summary="A private photo organizer.",
            tags="#photography #open-source #ai",
            url="https://example.com/photos",
            entry_type="github",
        ),
        entry_block(
            "More work",
            shared_by="ibby",
            context="work",
            summary="Python automation notes.",
            tags="#AI #python",
            url="https://example.com/more-work",
            entry_type="tool",
        ),
        entry_block(
            "Plain travel link",
            summary="No optional metadata.",
            tags="#travel #ai",
            url="https://example.com/plain",
        ),
    )


def test_collapsed_cards_show_sender_and_omit_missing_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Shared", shared_by="Ibby", context="work"),
        entry_block("Plain", url="https://example.com/plain"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    html = client.get("/").text

    assert 'class="entry-card is-collapsed"' in html
    assert 'class="sender-initial" aria-hidden="true">I</span>' in html
    assert "Shared by Ibby" in html
    assert html.count('class="entry-sender"') == 1
    assert html.count('class="entry-context"') == 1
    assert "Shared by:" not in html


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("context=work", ["Prompt defense", "More work"]),
        ("shared_by=MARIO", ["Personal photos"]),
        ("tag=PYTHON", ["Prompt defense", "More work"]),
        ("type=GITHUB", ["Personal photos"]),
        (
            "q=PrOmPt&context=WORK&shared_by=IBBY&tag=AI-SECURITY&type=ARTICLE",
            ["Prompt defense"],
        ),
    ],
)
def test_filters_are_independent_combinable_and_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    query: str,
    expected: list[str],
) -> None:
    vault = tmp_path / "vault"
    filter_fixture(vault)
    _, _, client = make_dashboard_client(monkeypatch, vault)

    response = client.get(f"/?{query}")

    assert response.status_code == 200
    for title in expected:
        assert title in response.text
    for title in {"Prompt defense", "Personal photos", "More work", "Plain travel link"} - set(expected):
        assert title not in response.text
    assert f"{len(expected)} result" in response.text


@pytest.mark.parametrize(
    "query",
    ["context=workish", "shared_by=Nobody", "tag=missing", "type=video"],
)
def test_unknown_or_non_exact_filters_return_zero_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, query: str
) -> None:
    vault = tmp_path / "vault"
    filter_fixture(vault)
    _, _, client = make_dashboard_client(monkeypatch, vault)

    response = client.get(f"/?{query}")

    assert response.status_code == 200
    assert "0 results" in response.text
    assert "No links match" in response.text


def test_selected_filters_clear_links_counts_top_topics_and_active_chips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    filter_fixture(vault)
    archive, main, client = make_dashboard_client(monkeypatch, vault)

    options = archive.get_filter_options()
    assert options["people"] == [("Ibby", 2), ("Mario", 1)]
    assert options["tags"][:4] == [("#ai", 4), ("#python", 2), ("#ai-security", 1), ("#extra", 1)]

    context = main.build_dashboard_context("/", tag="#ai")
    assert [(item["name"], item["count"]) for item in context["top_topics"]] == [
        ("#ai", 4),
        ("#python", 2),
        ("#ai-security", 1),
    ]

    html = client.get(
        "/?q=prompt&context=work&shared_by=Ibby&tag=%23ai-security&type=article"
    ).text
    assert 'value="prompt"' in html
    assert 'id="desktop-context-work" type="radio" name="context" value="work" checked' in html
    assert 'id="desktop-shared-by" name="shared_by" value="Ibby"' in html
    assert 'id="desktop-topic" name="tag" value="#ai-security"' in html
    assert 'id="desktop-type" name="type" value="article"' in html
    assert 'href="/" class="clear-filters"' in html
    assert html.count("active-filter-chip") >= 5
    assert "Search: prompt" in html
    assert "Context: work" in html
    assert "Shared by: Ibby" in html
    assert "Topic: #ai-security" in html
    assert "Type: article" in html
    assert html.count('class="topic-chip') == 4
    assert "More topics" in html
    assert "shared_by=Ibby" in html and "tag=%23ai-security" in html


def test_filter_comboboxes_support_typeahead_and_keyboard_navigation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    filter_fixture(vault)
    _, _, client = make_dashboard_client(monkeypatch, vault)

    html = client.get("/").text

    assert html.count('aria-autocomplete="list"') == 6
    assert html.count('class="combobox-listbox" role="listbox"') == 6
    assert 'autocomplete="off"' in html
    assert "function filterOptions()" in html
    assert "option.dataset.search.toLocaleLowerCase().includes(term)" in html
    assert "event.key === 'ArrowDown'" in html
    assert "event.key === 'ArrowUp'" in html
    assert "event.key === 'Enter'" in html
    assert "event.key === 'Escape'" in html
    assert "No matching options" in html
    assert "<select" not in html


def test_summary_display_truncation_preserves_full_source_and_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    short = "Short   summary with\nrepeated whitespace."
    long = (
        "This is a deliberately long summary with repeated    whitespace that must be truncated at a sensible "
        "word boundary while its complete original value remains available everywhere else."
    )
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Short", summary=short),
        entry_block("Long", summary=long, url="https://example.com/long"),
    )
    archive, _, client = make_dashboard_client(monkeypatch, vault)

    short_display = archive.collapsed_summary(short)
    long_display = archive.collapsed_summary(long)
    assert short_display == "Short summary with repeated whitespace."
    assert len(short_display) < 100
    assert long_display.endswith("…")
    assert len(long_display) <= 100
    assert long_display == "This is a deliberately long summary with repeated whitespace that must be truncated at a sensible…"

    source = (vault / "INDEX.md").read_text()
    assert long in source
    parsed_long = next(entry for entry in archive.get_all_entries() if entry.title == "Long")
    assert parsed_long.summary == long

    html = client.get("/").text
    assert short_display in html
    assert long_display in html
    assert long in html
    assert "entry-collapsed-summary" in html
    assert "entry-full-summary" in html

    day_entries = client.get(f"/day-json/{DATE}").json()
    assert next(entry for entry in day_entries if entry["title"] == "Long")["summary"] == long


def test_malicious_card_values_are_escaped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    write_index(vault, entry_block())
    archive, main, _ = make_dashboard_client(monkeypatch, vault)
    malicious = archive.ArchiveEntry(
        title='<img src=x onerror="alert(1)">',
        url="",
        entry_type="article",
        tags=['#<svg onload="alert(4)">'],
        added=DATE,
        summary='<script>alert("summary")</script>',
        shared_by='<script>alert("sender")</script>',
        context="work",
    )

    html = str(main.templates.env.get_template("_components.html").module.entry_card(malicious))

    assert "<script>" not in html
    assert "<img src=" not in html
    assert "<svg onload=" not in html
    assert "&lt;script&gt;alert" in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;" in html
    assert "&lt;svg onload=&#34;alert(4)&#34;&gt;" in html


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,hello", "file:///tmp/private", "not-a-url"],
)
def test_unsafe_manual_url_is_invalid_and_not_clickable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, url: str
) -> None:
    vault = tmp_path / "vault"
    block = entry_block(url=url)
    write_index(vault, block)
    archive, validate, main = load_modules(monkeypatch, vault)

    result = validate.validate_entry(block)
    parsed = archive._parse_entry(block)

    assert not result.valid
    assert any("Unsafe **URL**" in error for error in result.errors)
    assert parsed is not None
    assert parsed.url == url
    assert parsed.clickable_url is None
    html = str(main.templates.env.get_template("_components.html").module.entry_card(parsed))
    assert f'href="{url}"' not in html


def test_external_dashboard_dependencies_are_forbidden_and_d3_is_local() -> None:
    templates = list((DASHBOARD / "templates").glob("*.html"))
    templates.extend((ROOT / "skill-link-curator-dashboard" / "templates").glob("*.html"))
    external_resource = re.compile(
        r'<(?:script|link)\b[^>]*(?:src|href)=["\']https?://', re.IGNORECASE
    )
    for path in templates:
        assert not external_resource.search(path.read_text()), path

    css = "\n".join(path.read_text() for path in (DASHBOARD / "static").glob("*.css"))
    assert not re.search(r"@import\s+url\([^)]*https?://|url\([^)]*https?://", css, re.I)
    assert '/static/vendor/d3.v7.min.js' in (DASHBOARD / "templates" / "graph.html").read_text()
    assert 'https://d3js.org' not in (DASHBOARD / "templates" / "graph.html").read_text()


def test_vendored_d3_version_and_checksum() -> None:
    bundle = DASHBOARD / "static" / "vendor" / "d3.v7.min.js"
    content = bundle.read_bytes()
    assert content.startswith(b"// https://d3js.org v7.9.0")
    assert hashlib.sha256(content).hexdigest() == "f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539"
    assert (bundle.parent / "LICENSE.d3.txt").is_file()


def test_graph_keeps_singleton_only_entry_but_hides_its_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(vault, entry_block("Bananas", tags="#bananas"))
    _, _, client = make_dashboard_client(monkeypatch, vault)

    graph = client.get("/graph-json")

    assert graph.status_code == 200
    data = graph.json()
    assert [node["label"] for node in data["nodes"] if node["kind"] == "entry"] == ["Bananas"]
    assert [node for node in data["nodes"] if node["kind"] == "tag"] == []
    assert data["links"] == []


def test_graph_returns_all_entries_when_all_tags_are_singletons_or_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Bananas", tags="#bananas", url="https://example.com/bananas"),
        entry_block("Pears", tags="#pears", url="https://example.com/pears"),
        entry_block("Untagged", tags="", url="https://example.com/untagged"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    data = client.get("/graph-json").json()

    entry_nodes = [node for node in data["nodes"] if node["kind"] == "entry"]
    assert [node["label"] for node in entry_nodes] == ["Bananas", "Pears", "Untagged"]
    assert [node for node in data["nodes"] if node["kind"] == "tag"] == []
    assert data["links"] == []


def test_graph_shared_urls_get_distinct_opaque_ids_and_occurrence_specific_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    shared_url = "https://example.com/shared"
    write_index(
        vault,
        entry_block("First", tags="#common #alpha", url=shared_url),
        entry_block("Second", tags="#common #beta", url=shared_url),
        entry_block("Third", tags="#alpha #beta", url="https://example.com/third"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    data = client.get("/graph-json").json()
    entries = {node["label"]: node for node in data["nodes"] if node["kind"] == "entry"}
    sources_by_target = {
        entry_id: {link["source"] for link in data["links"] if link["target"] == entry_id}
        for entry_id in (node["id"] for node in entries.values())
    }

    assert entries["First"]["id"] != entries["Second"]["id"]
    assert sources_by_target[entries["First"]["id"]] == {"tag:#common", "tag:#alpha"}
    assert sources_by_target[entries["Second"]["id"]] == {"tag:#common", "tag:#beta"}
    assert sources_by_target[entries["Third"]["id"]] == {"tag:#alpha", "tag:#beta"}
    for node in entries.values():
        assert re.fullmatch(r"entry:[0-9a-f]{64}:\d+", node["id"])
        assert shared_url not in node["id"]
        assert node["id"] != f"entry:{node['url']}"


def test_graph_identical_occurrences_have_distinct_deterministic_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    identical = entry_block("Identical", tags="#shared")
    write_index(vault, identical, identical)
    _, _, client = make_dashboard_client(monkeypatch, vault)

    first = client.get("/graph-json").json()
    second = client.get("/graph-json").json()
    first_ids = [node["id"] for node in first["nodes"] if node["kind"] == "entry"]
    second_ids = [node["id"] for node in second["nodes"] if node["kind"] == "entry"]

    assert len(first_ids) == len(set(first_ids)) == 2
    assert first_ids == second_ids
    assert {link["target"] for link in first["links"]} == set(first_ids)


def test_graph_duplicate_tag_token_does_not_activate_singleton_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(vault, entry_block("Repeated token", tags="#bananas #bananas"))
    _, _, client = make_dashboard_client(monkeypatch, vault)

    data = client.get("/graph-json").json()

    assert len([node for node in data["nodes"] if node["kind"] == "entry"]) == 1
    assert [node for node in data["nodes"] if node["kind"] == "tag"] == []
    assert data["links"] == []


def test_graph_duplicate_tag_tokens_do_not_create_duplicate_links(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("First", tags="#shared #shared", url="https://example.com/first"),
        entry_block("Second", tags="#shared", url="https://example.com/second"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    data = client.get("/graph-json").json()
    tag_nodes = [node for node in data["nodes"] if node["kind"] == "tag"]

    assert tag_nodes == [{"id": "tag:#shared", "label": "#shared", "kind": "tag", "count": 2}]
    assert len(data["links"]) == 2
    assert len({(link["source"], link["target"]) for link in data["links"]}) == 2


def test_graph_mixed_entries_have_expected_counts_links_and_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block(
            "Connected one",
            tags="#repeat #one-off",
            shared_by="Ibby",
            context="work",
            url="https://example.com/connected-one",
        ),
        entry_block("Connected two", tags="#repeat #another", url="https://example.com/connected-two"),
        entry_block("Standalone", tags="#unique", url="https://example.com/standalone"),
        entry_block("Untagged", tags="", url="https://example.com/untagged"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    data = client.get("/graph-json").json()
    entry_nodes = [node for node in data["nodes"] if node["kind"] == "entry"]
    tag_nodes = [node for node in data["nodes"] if node["kind"] == "tag"]

    assert len(data["nodes"]) == 5
    assert len(entry_nodes) == 4
    assert tag_nodes == [{"id": "tag:#repeat", "label": "#repeat", "kind": "tag", "count": 2}]
    assert len(data["links"]) == 2
    assert {link["source"] for link in data["links"]} == {"tag:#repeat"}
    connected = next(node for node in entry_nodes if node["label"] == "Connected one")
    assert connected["type"] == "article"
    assert connected["url"] == "https://example.com/connected-one"
    assert connected["shared_by"] == "Ibby"
    assert connected["context"] == "work"
    assert connected["count"] == 1


def test_graph_empty_archive_returns_empty_dataset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(vault)
    _, _, client = make_dashboard_client(monkeypatch, vault)

    response = client.get("/graph-json")

    assert response.status_code == 200
    assert response.json() == {"nodes": [], "links": []}


def test_graph_templates_guard_standalone_forces_drag_and_double_click_behavior() -> None:
    paths = [
        DASHBOARD / "templates" / "graph.html",
        ROOT / "skill-link-curator-dashboard" / "templates" / "force-graph.html",
    ]

    for path in paths:
        template = path.read_text()
        assert "new Set(data.links.map(d => d.target))" in template
        assert "d3.forceX(width / 2)" in template
        assert "d3.forceY(height / 2)" in template
        assert "d.kind === 'entry' && !linkedEntryIds.has(d.id)" in template
        assert ".force('standalone-x', standaloneX)" in template
        assert ".force('standalone-y', standaloneY)" in template
        assert "window.addEventListener('resize', resizeGraph)" in template
        assert "centerForce.x(width / 2).y(height / 2)" in template
        assert "standaloneX.x(width / 2)" in template
        assert "standaloneY.y(height / 2)" in template
        assert "node.call(drag)" in template
        assert "if (d.kind === 'tag') { d.fx = null; d.fy = null; }" in template
        assert "node.filter(d => d.kind === 'entry').on('dblclick'" in template
        assert "window.open(d.url, '_blank', 'noopener')" in template


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_loopback_bind_values_are_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str
) -> None:
    _, _, main = load_modules(monkeypatch, tmp_path / "vault")
    assert main.validate_bind_host(host) == host


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com"])
def test_remote_bind_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str
) -> None:
    _, _, main = load_modules(monkeypatch, tmp_path / "vault")
    with pytest.raises(RuntimeError, match="ARCHIVE_ALLOW_REMOTE_BIND=1"):
        main.validate_bind_host(host)
    assert main.validate_bind_host(host, "1") == host


def test_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARCHIVE_HOST", raising=False)
    monkeypatch.delenv("ARCHIVE_ALLOW_REMOTE_BIND", raising=False)
    _, _, main = load_modules(monkeypatch, tmp_path / "vault")
    assert main.HOST == "127.0.0.1"


def test_all_card_views_and_existing_json_endpoints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    vault = tmp_path / "vault"
    write_index(
        vault,
        entry_block("Work link", shared_by="Ibby", context="work", tags="#testing #shared-topic"),
        entry_block(
            "Personal link",
            shared_by="Mario",
            context="personal",
            url="https://example.com/personal",
            tags="#testing #personal-topic",
            entry_type="github",
        ),
        entry_block("Plain link", url="https://example.com/plain", tags="#testing #plain"),
    )
    _, _, client = make_dashboard_client(monkeypatch, vault)

    for path in ("/", "/search?q=link", "/tag/testing", f"/day/{DATE}"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Shared by Ibby" in response.text
        assert "entry-collapsed-summary" in response.text

    calendar = client.get("/calendar")
    assert calendar.status_code == 200
    assert "if (entry.context)" in calendar.text
    assert "if (entry.shared_by)" in calendar.text
    assert "senderLabel.textContent = 'Shared by ' + entry.shared_by" in calendar.text
    assert "collapsed.textContent = truncateSummary(entry.summary)" in calendar.text
    assert "innerHTML" not in calendar.text

    day_json = client.get(f"/day-json/{DATE}")
    assert day_json.status_code == 200
    entries = day_json.json()
    assert entries[0]["shared_by"] == "Ibby"
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
