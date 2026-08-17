# Operations

Examples use the default `link-curator` profile and port `8090`. Substitute the
profile name and port selected during installation.

## Restart after a reboot

The installer starts the dashboard with `nohup`, which keeps it running after the
installing shell exits but does not start it again after a machine reboot.

Start it manually with:

```bash
nohup "$HOME/.hermes/profiles/<profile-name>/dashboard/start.sh" <dashboard-port> \
  > "$HOME/.hermes/profiles/<profile-name>/logs/dashboard.log" 2>&1 &
```

For the defaults, replace `<profile-name>` with `link-curator` and
`<dashboard-port>` with `8090`.

### Optional Linux user service

Create `~/.config/systemd/user/hermes-link-curator-dashboard.service`:

```ini
[Unit]
Description=Hermes Link Curator dashboard
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/.hermes/profiles/link-curator/dashboard
ExecStart=%h/.hermes/profiles/link-curator/dashboard/start.sh 8090
Restart=on-failure

[Install]
WantedBy=default.target
```

Then run:

```bash
systemctl --user daemon-reload
systemctl --user enable --now hermes-link-curator-dashboard.service
```

Review and replace the example profile name and port before enabling it.

### Optional macOS LaunchAgent

Create `~/Library/LaunchAgents/com.hermes.link-curator-dashboard.plist`, replacing
every `/Users/YOU` and the example profile/port with exact absolute values:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.hermes.link-curator-dashboard</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.hermes/profiles/link-curator/dashboard/start.sh</string>
    <string>8090</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/YOU/.hermes/profiles/link-curator/dashboard</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>StandardOutPath</key><string>/Users/YOU/.hermes/profiles/link-curator/logs/dashboard.log</string>
  <key>StandardErrorPath</key><string>/Users/YOU/.hermes/profiles/link-curator/logs/dashboard.log</string>
</dict>
</plist>
```

Load it for the current GUI session:

```bash
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.hermes.link-curator-dashboard.plist"
```

## Vault-only backup

Back up only the selected profile's `vault/` directory. Never put API keys,
`.env` files, model configuration, or other credentials in a vault backup.

```bash
tar -C "$HOME/.hermes/profiles/<profile-name>" \
  -czf "link-curator-vault-$(date +%Y%m%d).tar.gz" vault
```

## Rebuild, restore, and validate

`INDEX.md` is derived from the canonical dated notes. Rebuild it explicitly with:

```bash
python3 "$HOME/.hermes/profiles/<profile-name>/skills/note-taking/obsidian/scripts/rebuild_index.py"
```

The rebuild tool refuses unresolved save journals and creates a timestamped
backup before replacing an existing index.

To restore, stop the dashboard writer/agent, restore the backed-up `vault/`
directory into the same profile, rebuild the index if necessary, and validate:

```bash
python3 "$HOME/.hermes/profiles/<profile-name>/dashboard/validate.py" \
  "$HOME/.hermes/profiles/<profile-name>/vault"
```

Review any errors before restarting the curator or dashboard.
