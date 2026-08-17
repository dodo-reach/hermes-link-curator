#!/bin/bash
# install.sh — Self-service installer for hermes-link-curator
# Creates a fresh, isolated Hermes profile and installs only this repository's
# link-curator components into it.
set -Eeuo pipefail

umask 077

readonly DEFAULT_PROFILE_NAME="link-curator"
readonly DEFAULT_DASHBOARD_PORT="8090"
readonly DASHBOARD_BIND_ADDRESS="127.0.0.1"
readonly REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

PROFILE_NAME=""
DASHBOARD_PORT=""
PROFILE_DIR=""
VAULT_DIR=""
PROFILE_CREATION_STARTED=0
INSTALL_COMPLETE=0
DASH_PID=""

error() {
    printf 'ERROR: %s\n' "$*" >&2
}

validate_profile_name() {
    local name="$1"

    [[ -n "$name" ]] || return 1
    [[ "$name" =~ ^[a-z0-9-]+$ ]] || return 1
    [[ "$name" != -* && "$name" != *- ]] || return 1
}

validate_dashboard_port() {
    local port="$1"
    local port_number

    [[ "$port" =~ ^[0-9]+$ ]] || return 1
    ((${#port} <= 5)) || return 1
    port_number=$((10#$port))
    ((port_number >= 1 && port_number <= 65535))
}

profile_exists() {
    [[ -e "$PROFILE_DIR" || -L "$PROFILE_DIR" ]]
}

refuse_existing_profile() {
    if profile_exists; then
        error "Hermes profile '$PROFILE_NAME' already exists at:"
        printf '  %s\n' "$PROFILE_DIR" >&2
        printf '%s\n' \
            "Choose another profile name, or remove the existing profile manually before retrying." >&2
        exit 1
    fi
}

on_exit() {
    local status=$?

    if ((status != 0 && PROFILE_CREATION_STARTED == 1 && INSTALL_COMPLETE == 0)) && profile_exists; then
        printf '\n%s\n' "Installation stopped after the new profile was created." >&2
        printf '%s\n' "No cleanup was performed automatically." >&2
        printf '%s\n' "Review this exact profile directory before removing anything:" >&2
        printf '  %s\n' "$PROFILE_DIR" >&2
        if [[ -n "$DASH_PID" ]]; then
            printf '%s\n' "If the dashboard process is still running, stop only that process with:" >&2
            printf '  kill %q\n' "$DASH_PID" >&2
        fi
        printf '%s\n' "To remove only this failed profile with Hermes, run:" >&2
        printf '  hermes profile delete %q\n' "$PROFILE_NAME" >&2
        printf '%s\n' "Then rerun this installer." >&2
    fi

    return "$status"
}

trap on_exit EXIT

echo "═══════════════════════════════════════════"
echo " Hermes Link Curator — Self-Service Installer"
echo "═══════════════════════════════════════════"
echo

# Preflight checks are read-only and happen before the profile is created.
if ! command -v hermes >/dev/null 2>&1; then
    error "'hermes' command not found. Install Hermes separately, then rerun this installer."
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    error "'python3' not found. Python 3.10+ is required."
    exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
    error "'curl' not found. It is required for the local dashboard health check."
    exit 1
fi
if [[ -z "${HOME:-}" || "$HOME" != /* ]]; then
    error "HOME must be set to an absolute path."
    exit 1
fi

required_files=(
    "$REPO_DIR/SOUL.template.md"
    "$REPO_DIR/skill-obsidian/SKILL.md"
    "$REPO_DIR/skill-obsidian/scripts/save_entry.py"
    "$REPO_DIR/skill-obsidian/scripts/rebuild_index.py"
    "$REPO_DIR/skill-link-curator-dashboard/SKILL.md"
    "$REPO_DIR/dashboard/main.py"
    "$REPO_DIR/dashboard/archive.py"
    "$REPO_DIR/dashboard/validate.py"
    "$REPO_DIR/dashboard/start.sh"
    "$REPO_DIR/dashboard/requirements.txt"
)
for required_file in "${required_files[@]}"; do
    if [[ ! -f "$required_file" || -L "$required_file" ]]; then
        error "required repository file is missing or is not a regular file: $required_file"
        exit 1
    fi
done

required_directories=(
    "$REPO_DIR/skill-obsidian"
    "$REPO_DIR/skill-link-curator-dashboard"
    "$REPO_DIR/dashboard"
)
for required_directory in "${required_directories[@]}"; do
    if [[ ! -d "$required_directory" || -L "$required_directory" ]]; then
        error "required repository directory is missing or is not a directory: $required_directory"
        exit 1
    fi
    if find "$required_directory" -type l -print -quit | grep -q .; then
        error "repository component contains a symbolic link and will not be installed: $required_directory"
        exit 1
    fi
done

if ! IFS= read -r -p "Profile name [$DEFAULT_PROFILE_NAME]: " PROFILE_NAME; then
    error "could not read a profile name."
    exit 1
fi
PROFILE_NAME=${PROFILE_NAME:-$DEFAULT_PROFILE_NAME}
if ! validate_profile_name "$PROFILE_NAME"; then
    error "invalid profile name '$PROFILE_NAME'. Use lowercase letters, numbers, and hyphens only; do not use leading or trailing hyphens."
    exit 1
fi

if ! IFS= read -r -p "Dashboard port [$DEFAULT_DASHBOARD_PORT]: " DASHBOARD_PORT; then
    error "could not read a dashboard port."
    exit 1
fi
DASHBOARD_PORT=${DASHBOARD_PORT:-$DEFAULT_DASHBOARD_PORT}
if ! validate_dashboard_port "$DASHBOARD_PORT"; then
    error "invalid dashboard port '$DASHBOARD_PORT'. Enter digits only, from 1 through 65535."
    exit 1
fi
DASHBOARD_PORT=$((10#$DASHBOARD_PORT))

readonly PROFILE_NAME
readonly DASHBOARD_PORT
readonly PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
readonly VAULT_DIR="$PROFILE_DIR/vault"

# Refuse before confirmation and recheck immediately before profile creation.
refuse_existing_profile

echo
printf 'Selected profile name:     %s\n' "$PROFILE_NAME"
printf 'Absolute profile directory: %s\n' "$PROFILE_DIR"
printf 'Vault directory:            %s\n' "$VAULT_DIR"
printf 'Dashboard bind address:     %s\n' "$DASHBOARD_BIND_ADDRESS"
printf 'Dashboard port:             %s\n' "$DASHBOARD_PORT"
printf 'Repository source directory: %s\n' "$REPO_DIR"
echo

CONFIRM=""
if ! IFS= read -r -p "Proceed? [y/N] " CONFIRM; then
    error "could not read confirmation."
    exit 1
fi
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Aborted."
    exit 1
fi

refuse_existing_profile

echo
printf "→ Creating isolated profile '%s'...\n" "$PROFILE_NAME"
PROFILE_CREATION_STARTED=1
hermes profile create "$PROFILE_NAME" --no-skills

if [[ ! -d "$PROFILE_DIR" || -L "$PROFILE_DIR" ]]; then
    error "Hermes reported success, but the expected profile directory was not created: $PROFILE_DIR"
    exit 1
fi
chmod 700 "$PROFILE_DIR"

echo "→ Installing repository-owned skills..."
mkdir -p "$PROFILE_DIR/skills/note-taking"
if [[ -e "$PROFILE_DIR/skills/note-taking/obsidian" || -L "$PROFILE_DIR/skills/note-taking/obsidian" ||
      -e "$PROFILE_DIR/skills/note-taking/link-curator-dashboard" || -L "$PROFILE_DIR/skills/note-taking/link-curator-dashboard" ]]; then
    error "Hermes created an unexpected skill destination; refusing to merge or overwrite it."
    exit 1
fi
cp -R "$REPO_DIR/skill-obsidian" "$PROFILE_DIR/skills/note-taking/obsidian"
cp -R "$REPO_DIR/skill-link-curator-dashboard" "$PROFILE_DIR/skills/note-taking/link-curator-dashboard"

echo "→ Installing repository-owned dashboard..."
if [[ -e "$PROFILE_DIR/dashboard" || -L "$PROFILE_DIR/dashboard" ]]; then
    error "Hermes created an unexpected dashboard destination; refusing to merge or overwrite it."
    exit 1
fi
cp -R "$REPO_DIR/dashboard" "$PROFILE_DIR/dashboard"

if [[ -d "$VAULT_DIR" ]]; then
    if find "$VAULT_DIR" -mindepth 1 -print -quit | grep -q .; then
        error "Hermes created a non-empty vault unexpectedly; refusing to overwrite it: $VAULT_DIR"
        exit 1
    fi
elif [[ -e "$VAULT_DIR" || -L "$VAULT_DIR" ]]; then
    error "the expected vault path exists but is not an empty directory: $VAULT_DIR"
    exit 1
else
    mkdir -p "$VAULT_DIR"
fi
printf '# Index\n---\n' > "$VAULT_DIR/INDEX.md"

echo "→ Installing and rendering SOUL and component documentation..."
cp "$REPO_DIR/SOUL.template.md" "$PROFILE_DIR/SOUL.md"

# Render only the copies under the newly created profile. Repository templates
# remain untouched. The installed dashboard defaults are pinned to loopback and
# to the selected port, while start.sh continues to accept an explicit port.
python3 - "$PROFILE_DIR" "$VAULT_DIR" "$PROFILE_NAME" "$DASHBOARD_PORT" <<'PY'
from pathlib import Path
import sys

profile_dir = Path(sys.argv[1])
vault_dir = Path(sys.argv[2])
profile_name = sys.argv[3]
dashboard_port = sys.argv[4]

roots = [
    profile_dir / "SOUL.md",
    profile_dir / "skills" / "note-taking" / "obsidian",
    profile_dir / "skills" / "note-taking" / "link-curator-dashboard",
    profile_dir / "dashboard",
]

replacements = {
    b"<profile-dir>": str(profile_dir).encode(),
    b"<PROFILE_NAME>": profile_name.encode(),
    b"{{DASHBOARD_PORT}}": dashboard_port.encode(),
    b"{{AGENT_NAME}}": b"Link Curator",
}

installed_files = []
for root in roots:
    paths = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
    for path in paths:
        installed_files.append(path)
        content = path.read_bytes()
        rendered = content
        for placeholder, value in replacements.items():
            rendered = rendered.replace(placeholder, value)
        if path.suffix == ".md":
            rendered = rendered.replace(b"8090", dashboard_port.encode())
        if rendered != content:
            path.write_bytes(rendered)

start_path = profile_dir / "dashboard" / "start.sh"
start_content = start_path.read_text()
start_replacements = {
    '# Usage: ./start.sh [PORT]   (default port: 8090, or $ARCHIVE_PORT)':
        f'# Usage: ./start.sh [PORT]   (default port: {dashboard_port})',
    'PORT="${1:-${ARCHIVE_PORT:-8090}}"': f'PORT="${{1:-{dashboard_port}}}"',
    'HOST="${ARCHIVE_HOST:-127.0.0.1}"': 'HOST="127.0.0.1"',
}
for old, new in start_replacements.items():
    if old not in start_content:
        raise SystemExit(f"expected dashboard launcher setting not found: {old}")
    start_content = start_content.replace(old, new, 1)
start_path.write_text(start_content)

vault_literal = repr(str(vault_dir))

main_path = profile_dir / "dashboard" / "main.py"
main_content = main_path.read_text()
main_replacements = {
    '''VAULT_PATH = os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    str(Path(__file__).resolve().parent.parent / "vault")
)''': f"VAULT_PATH = {vault_literal}",
    'PORT = int(os.environ.get("ARCHIVE_PORT", "8090"))': f"PORT = {dashboard_port}",
    'HOST = os.environ.get("ARCHIVE_HOST", "127.0.0.1")': 'HOST = "127.0.0.1"',
}
for old, new in main_replacements.items():
    if old not in main_content:
        raise SystemExit(f"expected dashboard configuration setting not found: {old}")
    main_content = main_content.replace(old, new, 1)
main_path.write_text(main_content)

vault_replacements = {
    profile_dir / "dashboard" / "archive.py": (
        '''VAULT_PATH = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent / "vault"
))''',
        f"VAULT_PATH = Path({vault_literal})",
    ),
    profile_dir / "dashboard" / "validate.py": (
        '''DEFAULT_VAULT = os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    str(Path(__file__).resolve().parent.parent / "vault")
)''',
        f"DEFAULT_VAULT = {vault_literal}",
    ),
    profile_dir / "skills" / "note-taking" / "obsidian" / "scripts" / "save_entry.py": (
        '''VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))''',
        f"VAULT = Path({vault_literal})",
    ),
    profile_dir / "skills" / "note-taking" / "obsidian" / "scripts" / "rebuild_index.py": (
        '''VAULT = Path(os.environ.get(
    "HERMES_ARCHIVE_VAULT",
    Path(__file__).resolve().parent.parent.parent.parent.parent / "vault"
))''',
        f"VAULT = Path({vault_literal})",
    ),
}
for path, (old, new) in vault_replacements.items():
    content = path.read_text()
    if old not in content:
        raise SystemExit(f"expected vault configuration not found in {path}")
    path.write_text(content.replace(old, new, 1))

unresolved = []
for path in installed_files:
    content = path.read_bytes()
    for placeholder in replacements:
        if placeholder in content:
            unresolved.append(f"{path}: {placeholder.decode()}")
if unresolved:
    raise SystemExit("unresolved installed placeholders:\n" + "\n".join(unresolved))

if b'HOST="127.0.0.1"' not in start_path.read_bytes():
    raise SystemExit("installed dashboard launcher is not pinned to 127.0.0.1")
PY

# Choose a Python interpreter without installing or replacing Hermes itself.
HERMES_VENV="$HOME/.hermes/hermes-agent/venv/bin/python"
if [[ -x "$HERMES_VENV" ]] && "$HERMES_VENV" -c "import fastapi, uvicorn, jinja2, pydantic" 2>/dev/null; then
    PY="$HERMES_VENV"
    echo "→ Reusing the existing Hermes Python environment"
else
    echo "→ Creating an isolated dashboard Python environment..."
    python3 -m venv "$PROFILE_DIR/dashboard/venv"
    "$PROFILE_DIR/dashboard/venv/bin/pip" install -q -r "$PROFILE_DIR/dashboard/requirements.txt"
    PY="$PROFILE_DIR/dashboard/venv/bin/python"
fi

# Patch only the installed launcher and shell-quote the interpreter path.
START_SH="$PROFILE_DIR/dashboard/start.sh"
python3 - "$START_SH" "$PY" <<'PY'
from pathlib import Path
import shlex
import sys

path = Path(sys.argv[1])
python = shlex.quote(sys.argv[2])
content = path.read_text()
old = "exec python3 -m uvicorn"
if old not in content:
    raise SystemExit("expected Python invocation not found in installed dashboard launcher")
path.write_text(content.replace(old, f"exec {python} -m uvicorn", 1))
PY

mkdir -p "$PROFILE_DIR/logs"
chmod 700 \
    "$PROFILE_DIR" \
    "$PROFILE_DIR/skills" \
    "$PROFILE_DIR/skills/note-taking" \
    "$VAULT_DIR" \
    "$PROFILE_DIR/logs"
chmod 600 "$PROFILE_DIR/SOUL.md" "$VAULT_DIR/INDEX.md"
chmod 700 "$START_SH"
find \
    "$PROFILE_DIR" \
    -type d -exec chmod 700 {} +
find \
    "$PROFILE_DIR" \
    -type f -exec chmod go-rwx {} +

echo "→ Starting dashboard on $DASHBOARD_BIND_ADDRESS:$DASHBOARD_PORT..."
nohup "$START_SH" "$DASHBOARD_PORT" > "$PROFILE_DIR/logs/dashboard.log" 2>&1 &
DASH_PID=$!
printf '  PID: %s\n' "$DASH_PID"

sleep 3
if curl -fsS --max-time 3 "http://$DASHBOARD_BIND_ADDRESS:$DASHBOARD_PORT/health" 2>/dev/null | grep -q "healthy"; then
    INSTALL_COMPLETE=1
    echo
    echo "═══════════════════════════════════════════"
    echo " ✓ Setup complete"
    echo "═══════════════════════════════════════════"
    printf ' Dashboard: http://%s:%s\n' "$DASHBOARD_BIND_ADDRESS" "$DASHBOARD_PORT"
    printf ' Vault:     %s\n' "$VAULT_DIR"
    printf ' Logs:      %s\n' "$PROFILE_DIR/logs/dashboard.log"
    echo
    echo " This isolated profile did not inherit credentials or model configuration."
    echo " Configure it before use:"
    printf '   %q setup\n' "$PROFILE_NAME"
    echo
    echo " Start the profile:"
    printf '   hermes -p %q\n' "$PROFILE_NAME"
    echo " Start or restart the dashboard with its installed launcher:"
    printf '   %q %q\n' "$START_SH" "$DASHBOARD_PORT"
else
    error "dashboard health check failed at http://$DASHBOARD_BIND_ADDRESS:$DASHBOARD_PORT/health"
    printf '%s\n' "Check the local log without exposing it publicly:" >&2
    printf '  tail -30 %q\n' "$PROFILE_DIR/logs/dashboard.log" >&2
    exit 1
fi
