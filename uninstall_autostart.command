#!/usr/bin/env bash
# Removes the background dashboard service and the Desktop shortcut.
set -euo pipefail

LABEL="com.ufc-mention-markets.dashboard"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST" "$HOME/Desktop/UFC Dashboard.webloc"
echo "Removed. The dashboard no longer runs in the background."
echo "You can still start it by hand with ./start_live_dashboard.command"
