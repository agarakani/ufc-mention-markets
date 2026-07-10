#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-/Users/aryog/anaconda3/bin/python}"
POLL_SECONDS="${POLL_SECONDS:-30}"
PAPER_CARD="${PAPER_CARD:-}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "Starting UFC mention dashboard."
echo "This is read-only. It updates prices but cannot place trades."

set -- --poll-seconds "$POLL_SECONDS" --open-browser
if [[ -n "$PAPER_CARD" && "$PAPER_CARD" != "off" ]]; then
  set -- "$@" --paper-card "$PAPER_CARD"
  echo "Paper tracking: on for ${PAPER_CARD}"
else
  echo "Paper tracking: off. Set PAPER_CARD=\"Card name\" to turn it on."
fi
echo
echo "First refresh can take a couple minutes while the fight models load..."
echo
echo "Dashboard will open in your browser and auto-update every ${POLL_SECONDS}s."
echo "Leave this window open while using it."
if [[ -n "$PAPER_CARD" && "$PAPER_CARD" != "off" ]]; then
  echo "New WATCH rows will be recorded as one paper contract at the live buy price."
fi
echo "Press Control-C to stop."
echo

exec "$PYTHON_BIN" -u scripts/live/dashboard_server.py "$@"
