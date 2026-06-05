"""Validation utilities for link curator entries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]

    @property
    def is_valid(self) -> bool:
        return self.valid


def validate_entry(block: str) -> ValidationResult:
    """
    Check a raw entry block (markdown) for format correctness.
    Returns ValidationResult with errors (must fix) and warnings (should fix).
    """
    errors = []
    warnings = []

    # 1. Title line
    if not re.search(r'^###\s+\S', block, re.MULTILINE):
        errors.append("Missing or malformed ### title line")

    # 2. URL
    if not re.search(r'\*\*URL\*\*:\s*\S+', block):
        errors.append("Missing **URL** field or empty URL")

    # 3. Added date
    added_m = re.search(r'\*\*Added\*\*:\s*(\d{4}-\d{2}-\d{2})', block)
    if not added_m:
        errors.append("Missing **Added**: YYYY-MM-DD")
    else:
        date_str = added_m.group(1)
        try:
            from datetime import datetime
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            errors.append(f"Invalid date format: {date_str} (expected YYYY-MM-DD)")

    # 4. Type
    if not re.search(r'\*\*Type\*\*:\s*`[^`]+`', block):
        warnings.append("Missing **Type** field (defaults to 'other')")

    # 5. Tags
    tags = re.findall(r'#\w[-\w]*', block)
    if not tags:
        warnings.append("No tags found (should have at least 1)")

    # 6. Summary
    if not re.search(r'\*\*Summary\*\*:', block):
        warnings.append("Missing **Summary** field")

    # 7. Trailing separator check
    lines = block.strip().split('\n')
    if lines and lines[-1].strip() == '---':
        warnings.append("Entry has trailing --- separator (should not end with ---)")

    # 8. Check for em-dash vs hyphen-minus in title line
    title_lines = [l for l in lines if l.startswith('### ')]
    for tl in title_lines:
        if '—' in tl:
            warnings.append(f"Title uses em-dash (U+2014) instead of hyphen-minus (-): '{tl[:60]}...'")
        if '–' in tl:
            warnings.append(f"Title uses en-dash (U+2013) instead of hyphen-minus (-): '{tl[:60]}...'")

    return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)


# Auto-discover vault path:
# This file lives at <profile>/dashboard/validate.py
# Vault lives at <profile>/vault
# Override with $HERMES_ARCHIVE_VAULT env var if needed.
import os

DEFAULT_VAULT = os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    str(Path(__file__).resolve().parent.parent / "vault")
)


def validate_vault(vault_path: str = None) -> dict:
    """
    Run full validation on the vault.
    Returns a report dict.
    """
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    if vault_path is None:
        vault_path = DEFAULT_VAULT
    vault = Path(vault_path)
    index_path = vault / "INDEX.md"

    results = {
        "total_entries": 0,
        "valid": 0,
        "errors_only": 0,
        "warnings": 0,
        "broken": [],
        "warnings_list": [],
    }

    if not index_path.exists():
        results["error"] = "INDEX.md not found"
        return results

    content = index_path.read_text()
    chunks = re.split(r'\n---\n', content)

    # Import parser
    from archive import _parse_entry, get_all_entries

    for i, chunk in enumerate(chunks):
        if not re.search(r'\*\*URL\*\*', chunk):
            continue

        results["total_entries"] += 1

        # Parse test
        entry = _parse_entry(chunk.strip())
        val = validate_entry(chunk)

        if val.valid:
            results["valid"] += 1
        elif len(val.errors) > 0 and len(val.warnings) == 0:
            results["errors_only"] += 1
        else:
            results["warnings"] += 1

        if val.errors:
            title_match = re.search(r'^###\s+(.+?)\s*$', chunk, re.MULTILINE)
            title = title_match.group(1)[:60] if title_match else f"chunk {i}"
            results["broken"].append({
                "index": i,
                "title": title,
                "errors": val.errors,
            })

        if val.warnings:
            title_match = re.search(r'^###\s+(.+?)\s*$', chunk, re.MULTILINE)
            title = title_match.group(1)[:60] if title_match else f"chunk {i}"
            for w in val.warnings:
                results["warnings_list"].append({"title": title, "warning": w})

    return results


if __name__ == "__main__":
    import json, sys

    vault_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VAULT
    report = validate_vault(vault_path)

    print(f"\n=== Vault Validation Report ===")
    print(f"Total entries: {report['total_entries']}")
    print(f"Fully valid:    {report['valid']}")
    print(f"Has errors:     {report['errors_only']}")
    print(f"Has warnings:   {report['warnings']}")

    if report.get("broken"):
        print(f"\n=== Entries with ERRORS ({len(report['broken'])}) ===")
        for item in report["broken"]:
            print(f"\n  [{item['index']}] {item['title']}")
            for e in item["errors"]:
                print(f"    ERROR: {e}")

    if report.get("warnings_list"):
        print(f"\n=== WARNINGS ({len(report['warnings_list'])}) ===")
        seen = set()
        for item in report["warnings_list"]:
            key = item["warning"]
            if key not in seen:
                print(f"  - {item['title']}: {item['warning']}")
                seen.add(key)

    if not report.get("broken") and not report.get("warnings_list"):
        print("\nAll entries are well-formed.")
