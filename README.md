# Hermes Link Curator

A secure, profile-isolated link curator for Hermes Agent. Send a URL and the
curator stores a validated Markdown entry in a local vault that can be browsed
through a responsive FastAPI dashboard.

## Dashboard preview

[![Link Curator dashboard showing responsive cards, metadata, and filters](assets/dashboard-preview.gif)](assets/dashboard-preview.mp4)

The dashboard includes list, calendar, day, search, tag, and graph views. Cards
support optional `Shared by` and `Context` metadata, combinable filters, compact
mobile layouts, and collapsed summaries without changing the full Markdown or
JSON data.

## Requirements

- An existing Hermes installation
- Python 3.10 or newer
- Bash on macOS, Linux, or WSL

Native Windows installation is not currently supported.

## Installation

```bash
git clone https://github.com/dodo-reach/hermes-link-curator.git
cd hermes-link-curator
bash install.sh
link-curator setup
hermes -p link-curator
```

`link-curator` is the default profile name. If you select a different safe name
in the installer, use that name for the final commands:

```bash
<profile-name> setup
hermes -p <profile-name>
```

`install.sh` creates a fresh isolated profile. It does not clone or inherit
credentials, memories, configuration, tools, skills, sessions, or other content
from another Hermes profile. It installs only this repository's curator skills,
dashboard, rendered SOUL, and new empty vault. Model and API credentials are
configured afterward with `<profile-name> setup`.

The dashboard receives its own virtual environment inside the selected profile;
it does not modify or reuse Hermes's Python environment.

## Dashboard security and access

The dashboard binds to `127.0.0.1` by default and has no authentication. Do not
expose it directly to the public internet or recommend binding it to all network
interfaces.

Open the default installation locally at:

```text
http://127.0.0.1:8090
```

For remote access, keep the dashboard on loopback and use either:

- an SSH tunnel, for example
  `ssh -N -L 8090:127.0.0.1:8090 user@hermes-host`, then open
  `http://127.0.0.1:8090` locally; or
- an existing Tailscale Serve proxy configured to forward to
  `http://127.0.0.1:8090` and protected by the tailnet.

The standalone source dashboard rejects a non-loopback `ARCHIVE_HOST` unless the
operator also sets `ARCHIVE_ALLOW_REMOTE_BIND=1`. That escape hatch is for
informed standalone operation; tunnels and authenticated proxies remain the
recommended approach. Installed profiles are pinned more strictly to loopback.

## Vault and entry format

The default vault is:

```text
~/.hermes/profiles/link-curator/vault/
```

For another selected name, replace `link-curator` with that profile name. Dated
notes are the canonical archive. `INDEX.md` provides the dashboard's newest-first
view and can be rebuilt manually from dated notes.

Each entry includes a URL, title, type, topic tags, date, and summary. `Shared by`
and `Context` (`work` or `personal`) remain optional. Explicit safe CLI tags are
not limited to the curator's automatic three-topic recommendation.

The save tool validates all fields before filesystem changes, serializes writers
with a vault lock, replaces each Markdown file atomically, rejects duplicate
URLs, and uses a hidden journal to reconcile an interrupted two-file save. A
dated note and `INDEX.md` cannot be replaced as one filesystem transaction; the
journal makes that two-step operation recoverable without silently rebuilding or
discarding unrelated index content.

## Repository layout

```text
hermes-link-curator/
├── install.sh
├── SOUL.template.md
├── skill-obsidian/
├── skill-link-curator-dashboard/
├── dashboard/
├── docs/operations.md
└── tests/
```

The dashboard is self-contained when opened: D3 is vendored and the styles use
system fonts, so it does not fetch scripts, stylesheets, or fonts from external
services.

## Operations, restart, and backup

See [docs/operations.md](docs/operations.md) for restart-after-reboot options,
vault-only backups, explicit index rebuilding, restore, and validation.

## Development

Create a development environment outside Hermes and run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
bash -n install.sh
.venv/bin/python -m pytest -q
```

Tests use temporary vaults and do not run Hermes or the installer.

## License

Project code is MIT licensed. The vendored D3 7.9.0 bundle is ISC licensed; see
`dashboard/static/vendor/README.md` and `LICENSE.d3.txt`.
