#!/usr/bin/env bash
# Installs the UFC mention dashboard as a background service on this Mac.
# After this runs once, the dashboard is always on at http://127.0.0.1:8765
# — it starts by itself at login, restarts if it crashes, and needs no terminal.
# Double-click this file (or run it) once. Run uninstall_autostart.command to remove.
set -euo pipefail

cd "$(dirname "$0")"
REPO_DIR="$(pwd)"

PYTHON_BIN="${PYTHON_BIN:-/Users/aryog/anaconda3/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

# UFC_PUBLISH=1 keeps the public GitHub Pages copy fresh; 0 turns sharing off.
PUBLISH_FLAG="${UFC_PUBLISH:-1}"

LABEL="com.ufc-mention-markets.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/ufc-mention-dashboard.log"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>-u</string>
    <string>$REPO_DIR/scripts/live/dashboard_server.py</string>
    <string>--poll-seconds</string><string>30</string>
    <string>--paper-card</string><string>auto</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>UFC_PUBLISH</key><string>$PUBLISH_FLAG</string>
  </dict>
  <key>WorkingDirectory</key><string>$REPO_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
PLIST_EOF

# reload cleanly if it was already installed
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

# desktop shortcut that opens the dashboard in the browser
cat > "$HOME/Desktop/UFC Dashboard.webloc" <<'WEBLOC_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>URL</key>
  <string>http://127.0.0.1:8765</string>
</dict>
</plist>
WEBLOC_EOF

echo "Installed. The dashboard now runs by itself in the background."
echo "It is loading the fight models now (takes a couple of minutes the first time)."
echo
echo "Open it any time: double-click 'UFC Dashboard' on your Desktop,"
echo "or go to http://127.0.0.1:8765 in your browser."
echo
echo "Paper tracking is on automatically for every card (read-only, no real money)."
if [[ "$PUBLISH_FLAG" == "1" ]]; then
  echo "Public sharing: on — https://agarakani.github.io/ufc-mention-markets/ stays current."
  echo "Turn it off with: UFC_PUBLISH=0 ./install_autostart.command"
fi
echo "Logs: $LOG"
