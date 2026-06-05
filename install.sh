#!/bin/bash
# install.sh — Self-service installer for hermes-link-curator
# Use this if you don't want to ask your agent to do the setup.
# Equivalent to what AGENT_GUIDE.md does, but interactive.
set -e

# Resolve repo root (the dir containing this script)
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "═══════════════════════════════════════════"
echo " Hermes Link Curator — Self-Service Installer"
echo "═══════════════════════════════════════════"
echo

# 1. Sanity check
if ! command -v hermes >/dev/null 2>&1; then
    echo "ERROR: 'hermes' command not found. Install Hermes Agent first:"
    echo "  curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
    exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: 'python3' not found. Python 3.10+ required."
    exit 1
fi

# 2. Ask questions
read -rp "Profile name [link-curator]: " PROFILE_NAME
PROFILE_NAME=${PROFILE_NAME:-link-curator}

read -rp "Dashboard port [8090]: " DASHBOARD_PORT
DASHBOARD_PORT=${DASHBOARD_PORT:-8090}

PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
if [ -d "$PROFILE_DIR" ]; then
    echo "ERROR: profile '$PROFILE_NAME' already exists at $PROFILE_DIR"
    echo "Choose a different name, or run: hermes profile delete $PROFILE_NAME"
    exit 1
fi

echo
echo "Profile:   $PROFILE_DIR"
echo "Dashboard: http://localhost:$DASHBOARD_PORT"
echo
read -rp "Proceed? [y/N] " CONFIRM
[ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ] || { echo "Aborted."; exit 1; }

# 3. Create the profile (clones from default so existing config/skills carry over)
echo
echo "→ Creating profile '$PROFILE_NAME'..."
hermes profile create "$PROFILE_NAME" --clone-all

# 4. Install the 2 skills
echo "→ Installing skills..."
mkdir -p "$PROFILE_DIR/skills/note-taking"
cp -r "$REPO_DIR/skill-obsidian"               "$PROFILE_DIR/skills/note-taking/obsidian"
cp -r "$REPO_DIR/skill-link-curator-dashboard" "$PROFILE_DIR/skills/note-taking/link-curator-dashboard"

# 5. Install the dashboard
echo "→ Installing dashboard..."
cp -r "$REPO_DIR/dashboard" "$PROFILE_DIR/dashboard"
mkdir -p "$PROFILE_DIR/vault"
if [ ! -f "$PROFILE_DIR/vault/INDEX.md" ]; then
    printf '# Index\n---\n' > "$PROFILE_DIR/vault/INDEX.md"
fi

# 6. Choose Python interpreter
HERMES_VENV="$HOME/.hermes/hermes-agent/venv/bin/python"
if [ -x "$HERMES_VENV" ] && "$HERMES_VENV" -c "import fastapi, uvicorn, jinja2, pydantic" 2>/dev/null; then
    PY="$HERMES_VENV"
    echo "→ Reusing hermes-agent venv"
else
    echo "→ Creating dashboard venv..."
    python3 -m venv "$PROFILE_DIR/dashboard/venv"
    "$PROFILE_DIR/dashboard/venv/bin/pip" install -q -r "$PROFILE_DIR/dashboard/requirements.txt"
    PY="$PROFILE_DIR/dashboard/venv/bin/python"
fi

# 7. Patch start.sh
START_SH="$PROFILE_DIR/dashboard/start.sh"
python3 - "$START_SH" "$PY" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
python = sys.argv[2]
content = path.read_text()
path.write_text(content.replace("exec python3 -m uvicorn", f"exec {python} -m uvicorn"))
PY
chmod +x "$START_SH"

# 8. Install SOUL
echo "→ Installing SOUL template..."
cp "$REPO_DIR/SOUL.template.md" "$PROFILE_DIR/SOUL.md"

# 9. Start the dashboard
echo "→ Starting dashboard on port $DASHBOARD_PORT..."
mkdir -p "$PROFILE_DIR/logs"
nohup "$START_SH" "$DASHBOARD_PORT" > "$PROFILE_DIR/logs/dashboard.log" 2>&1 &
DASH_PID=$!
echo "  PID: $DASH_PID"

# 10. Health check
sleep 3
if curl -s --max-time 3 "http://localhost:$DASHBOARD_PORT/health" | grep -q "healthy"; then
    echo
    echo "═══════════════════════════════════════════"
    echo " ✓ Setup complete"
    echo "═══════════════════════════════════════════"
    echo " Dashboard: http://localhost:$DASHBOARD_PORT"
    echo " Vault:     $PROFILE_DIR/vault"
    echo " Logs:      $PROFILE_DIR/logs/dashboard.log"
    echo
    echo " Next steps:"
    echo "   1. (Optional) Edit $PROFILE_DIR/SOUL.md to customize"
    echo "   2. Start the link-curator agent:  hermes -p $PROFILE_NAME"
    echo "   3. Send: archive https://github.com/dodo-reach/hermes-link-curator"
    echo "   4. Refresh the dashboard to see your first entry"
else
    echo
    echo "⚠ Dashboard health check failed. Check logs:"
    echo "   tail -30 $PROFILE_DIR/logs/dashboard.log"
    exit 1
fi
