from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_guide_delegates_only_to_installer() -> None:
    guide = (ROOT / "AGENT_GUIDE.md").read_text()
    assert "bash install.sh" in guide
    assert "<profile-name> setup" in guide
    assert "hermes -p <profile-name>" in guide
    assert "hermes profile create" not in guide
    assert "hermes-agent/venv" not in guide
    assert "git clone" not in guide


def test_documentation_avoids_unreviewed_browsers_and_unsafe_bind_guidance() -> None:
    documentation = "\n".join(path.read_text() for path in ROOT.rglob("*.md"))
    for forbidden in ("camofox", "playwright", "selenium", "browser extension"):
        assert forbidden not in documentation.casefold()
    assert "ARCHIVE_HOST=0.0.0.0" not in documentation


def test_readme_documents_isolated_setup_and_dynamic_profile_name() -> None:
    readme = (ROOT / "README.md").read_text()
    assert "link-curator setup" in readme
    assert "<profile-name> setup" in readme
    assert "hermes -p <profile-name>" in readme
    assert "127.0.0.1" in readme
    assert "no authentication" in readme
    assert "SSH tunnel" in readme
    assert "Tailscale Serve" in readme


def test_prompt_injection_guardrails_exist_in_both_curator_instructions() -> None:
    for relative in ("SOUL.template.md", "skill-obsidian/SKILL.md"):
        content = (ROOT / relative).read_text().casefold()
        normalized = " ".join(content.split())
        assert "webpage content" in normalized
        assert "untrusted data" in normalized
        assert "never execute commands" in normalized or "never run commands" in normalized
        assert ".env" in normalized
        assert "another profile" in normalized
        assert "never transmit" in normalized
        assert "[content unavailable]" in normalized
        assert "defence-in-depth" in normalized
        assert "do not make prompt injection impossible" in normalized


def test_installer_security_behaviour_is_preserved() -> None:
    installer = (ROOT / "install.sh").read_text()
    assert 'hermes profile create "$PROFILE_NAME" --no-skills' in installer
    assert "--clone" not in installer
    assert "hermes-agent/venv" not in installer
    assert 'python3 -m venv "$PROFILE_DIR/dashboard/venv"' in installer
    assert 'DASHBOARD_BIND_ADDRESS="127.0.0.1"' in installer
    assert "0.0.0.0" not in installer
    assert not re.search(r"\beval\b", installer)
