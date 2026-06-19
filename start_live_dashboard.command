#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-/Users/aryog/anaconda3/bin/python}"
POLL_SECONDS="${POLL_SECONDS:-30}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "Starting UFC mention dashboard."
echo "This is read-only. It updates prices but cannot place trades."
echo
echo "First refresh can take a couple minutes while the fight models load..."
"$PYTHON_BIN" -u scripts/live/refresh_dashboard.py --poll-seconds "$POLL_SECONDS" --iterations 1

open dashboard/index.html

echo
echo "Dashboard is open. Leave this window open to keep updating every ${POLL_SECONDS}s."
echo "Press Control-C to stop."
echo

exec "$PYTHON_BIN" -u scripts/live/refresh_dashboard.py --poll-seconds "$POLL_SECONDS"
