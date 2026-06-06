# AGENT_GUIDE.md — How to set up the link-curator profile

> This file is for the **agent**, not the user. The user has sent you the link to this repository. Your job: read this file, follow it step by step, and end with a working link-curator profile + dashboard.

## What you're installing

A **link-curator profile** for the current Hermes install:
- 2 skills (auto-save links to a markdown vault, maintain the dashboard)
- 1 SOUL template (gives the agent a "librarian" personality)
- 1 standalone FastAPI dashboard on port 8090 (Obsidian-style UI over the vault)

## Phase 0 — Sanity check the environment

Before anything, confirm the basics. If anything fails, STOP and tell the user what's wrong.

```bash
# 1. Hermes CLI works
hermes --version

# 2. Python 3 is available (Hermes requires it)
python3 --version

# 3. The repo is reachable (it should be, the user gave you the link)
test -d "$REPO_DIR" || echo "REPO_DIR not set or doesn't exist"
```

Set `REPO_DIR` to wherever this repo was cloned (the user likely cloned it before sending the link, or you'll clone it now).

If you had to clone it yourself:

```bash
git clone https://github.com/dodo-reach/hermes-link-curator.git /tmp/hermes-link-curator
REPO_DIR=/tmp/hermes-link-curator
```

## Phase 1 — Ask the user 2 questions

You need two pieces of info. Ask ONCE, with both questions in one message (this is the only time the user is interrupted).

1. **What should the profile be called?** (default suggestion: `link-curator`)
2. **Where do you want the dashboard to listen?** (default: `8090` — only ask if they care; otherwise just use 8090)

Store the answers:
- `PROFILE_NAME` (e.g. `link-curator`)
- `DASHBOARD_PORT` (e.g. `8090`)

The profile will live at `~/.hermes/profiles/<PROFILE_NAME>/`.

## Phase 2 — Create the profile

Clone from the default profile so the new one inherits the user's existing config, tools, and any skills they already had:

```bash
hermes profile create "$PROFILE_NAME" --clone-all
```

Verify:
```bash
hermes profile list | grep "$PROFILE_NAME"
test -d "$HOME/.hermes/profiles/$PROFILE_NAME" && echo "Profile dir OK"
```

## Phase 3 — Install the 2 skills

The skills live in the repo under `note-taking/obsidian/` and `note-taking/link-curator-dashboard/`. Install them inside the new profile's `skills/` directory:

```bash
PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
mkdir -p "$PROFILE_DIR/skills/note-taking"
cp -r "$REPO_DIR/skill-obsidian"          "$PROFILE_DIR/skills/note-taking/obsidian"
cp -r "$REPO_DIR/skill-link-curator-dashboard" "$PROFILE_DIR/skills/note-taking/link-curator-dashboard"
```

Verify:
```bash
ls "$PROFILE_DIR/skills/note-taking/"
# expected: obsidian  link-curator-dashboard
```

## Phase 4 — Install the dashboard

```bash
cp -r "$REPO_DIR/dashboard" "$PROFILE_DIR/dashboard"
mkdir -p "$PROFILE_DIR/vault"
if [ ! -f "$PROFILE_DIR/vault/INDEX.md" ]; then
    printf '# Index\n---\n' > "$PROFILE_DIR/vault/INDEX.md"
fi
```

Install Python dependencies. The dashboard needs `fastapi`, `uvicorn`, `jinja2`, `pydantic`. We try to reuse the user's existing Python environment first to avoid yet another venv:

```bash
PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"

# Best path: reuse hermes-agent's venv (it already has fastapi/uvicorn)
HERMES_VENV="$HOME/.hermes/hermes-agent/venv/bin/python"
if [ -x "$HERMES_VENV" ] && "$HERMES_VENV" -c "import fastapi, uvicorn, jinja2, pydantic" 2>/dev/null; then
    echo "Reusing hermes-agent venv at $HERMES_VENV"
    # Use that venv's python in start.sh — see Phase 5
else
    # Fallback: create a venv just for the dashboard
    python3 -m venv "$PROFILE_DIR/dashboard/venv"
    "$PROFILE_DIR/dashboard/venv/bin/pip" install -r "$PROFILE_DIR/dashboard/requirements.txt"
fi
```

## Phase 5 — Adjust the dashboard launcher (path to Python)

The repo's `start.sh` uses `python3` (system). After Phase 4, you know which Python interpreter to use. Patch the launcher accordingly:

```bash
PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
START_SH="$PROFILE_DIR/dashboard/start.sh"

if [ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]; then
    PY="$HOME/.hermes/hermes-agent/venv/bin/python"
else
    PY="$PROFILE_DIR/dashboard/venv/bin/python"
fi

# Rewrite the python invocation in start.sh
python3 - "$START_SH" "$PY" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
python = sys.argv[2]
content = path.read_text()
path.write_text(content.replace("exec python3 -m uvicorn", f"exec {python} -m uvicorn"))
PY
chmod +x "$START_SH"
cat "$START_SH"
```

## Phase 6 — Write the SOUL

The repo ships a `SOUL.template.md`. Copy it into the profile and **personalize** it. Ask the user 1-2 quick customization questions (or use sensible defaults):

1. **What's the agent's name?** (default: leave `{{AGENT_NAME}}` as `Curator` — a librarian)
2. **What tag categories matter?** (default: keep the suggested `#ai #design #dev-tools #productivity` — user can edit later)

```bash
PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
cp "$REPO_DIR/SOUL.template.md" "$PROFILE_DIR/SOUL.md"
```

Tell the user: *"Open `~/.hermes/profiles/<PROFILE_NAME>/SOUL.md` and adjust if you want — defaults are sane."*

## Phase 7 — Start the dashboard

```bash
PROFILE_DIR="$HOME/.hermes/profiles/$PROFILE_NAME"
mkdir -p "$PROFILE_DIR/logs"
nohup "$PROFILE_DIR/dashboard/start.sh" "$DASHBOARD_PORT" \
    > "$PROFILE_DIR/logs/dashboard.log" 2>&1 &
echo "Dashboard PID: $!"
```

Wait ~3 seconds, then health check:

```bash
sleep 3
curl -s --max-time 3 "http://localhost:$DASHBOARD_PORT/health"
# expected: {"status":"healthy", ...}
```

If unhealthy, check the log:
```bash
tail -30 "$PROFILE_DIR/logs/dashboard.log"
```

Common fixes:
- Port in use → try a different port (e.g. `8091`)
- `ModuleNotFoundError: fastapi` → Phase 4 venv wasn't created; redo

## Phase 8 — Verify the round-trip

Tell the user:

> *Setup complete. Test it:*
> *1. Open http://localhost:8090 — dashboard should be empty*
> *2. In the agent chat, send: `archive https://github.com/dodo-reach/hermes-link-curator`*
> *3. Refresh the dashboard — your test entry should appear*

If the test save fails, the most common cause is the agent not picking up the SOUL. Verify with `cat ~/.hermes/profiles/<PROFILE_NAME>/SOUL.md` — it should describe a librarian. If needed, the user can `/reset` to reload the skill + SOUL.

## Phase 9 — Report

Tell the user:
- Profile name created
- Dashboard URL: `http://localhost:<DASHBOARD_PORT>`
- Where the vault will live: `~/.hermes/profiles/<PROFILE_NAME>/vault/`
- Where to find logs: `~/.hermes/profiles/<PROFILE_NAME>/logs/dashboard.log`
- "The agent picks up the SOUL and skills on the next `/reset` or new session. Restart the agent profile (`hermes -p <PROFILE_NAME>`) to test."

## ─── Optional upgrades ───

The base install works. Two more levels, on demand.

### Level 1 — Fetch context from any link

The base `obsidian` skill has web search and `web_extract`. If the user wants to archive X/Twitter posts, login-gated pages, or JS-heavy sites, they need:

- **Camofox local mode** — browser-based fetching through Hermes' built-in Browser Automation support. Camofox is not a Hermes skill; install the browser server from the upstream repo:
  ```bash
  git clone https://github.com/jo-inc/camofox-browser
  cd camofox-browser
  make up
  ```
  Then set `CAMOFOX_URL=http://localhost:9377` in `~/.hermes/.env`, or choose **Browser Automation -> Camofox** in `hermes tools`. See the Hermes browser guide: https://hermes-agent.nousresearch.com/docs/user-guide/features/browser
- **Playwright MCP** — JS rendering. Install: `hermes mcp add playwright -- npx -y @playwright/mcp@latest`

Then ask the user to test by sending an X post URL.

### Level 2 — Send links from a messaging app

Most users already have a Hermes gateway configured for another profile. The user has two options:

**A) Reuse an existing gateway channel.** Ask which platform and chat they use, then forward incoming messages to the link-curator profile (manual forward, or a routing rule in `~/.hermes/gateway.yaml`).

**B) Set up a fresh gateway for the link-curator profile.** Run:

```bash
hermes gateway setup
# Pick the platform (telegram/discord/slack/etc.)
# Use the SAME bot token they already have, or create a new one
# Set the "home" channel to the chat where they want to send links
```

Most users have option A. Just add the chat to the existing home channel list. The exact command depends on their platform — ask them to share the chat ID or handle if you can't infer it.

---

## End of guide

You should now have:
- `~/.hermes/profiles/<PROFILE_NAME>/SOUL.md`
- `~/.hermes/profiles/<PROFILE_NAME>/skills/note-taking/obsidian/`
- `~/.hermes/profiles/<PROFILE_NAME>/skills/note-taking/link-curator-dashboard/`
- `~/.hermes/profiles/<PROFILE_NAME>/dashboard/` (running on port `DASHBOARD_PORT`)
- `~/.hermes/profiles/<PROFILE_NAME>/vault/` (empty, ready for first archive)

If anything is missing, re-run the relevant phase.
