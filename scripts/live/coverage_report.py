#!/usr/bin/env python3
"""Did we record every card that actually had markets?

A blank card is ambiguous on its own: either Kalshi never opened mention
markets for it, or our recorder was down and we lost the card. Those are very
different problems and the product should never confuse them.

This asks Kalshi directly which cards ever had mention markets (its settled
events are the ground truth, retrospective and public), compares that against
the snapshots we hold, and labels every card:

  recorded      Kalshi ran markets and we captured them
  MISSED        Kalshi ran markets and we captured nothing  <- the real alarm
  no markets    Kalshi never opened markets for that card

Usage:
  python3 scripts/live/coverage_report.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HISTORY = ROOT / "market_data" / "kalshi_price_history.csv"
UPCOMING = ROOT / "data" / "processed" / "upcoming_events.json"
OUT_PATH = ROOT / "model_outputs" / "coverage_report.json"

KALSHI_EVENTS = "https://api.elections.kalshi.com/trade-api/v2/events"
SERIES = "KXFIGHTMENTION"
TICKER_DATE = re.compile(r"-(\d{2})([A-Z]{3})(\d{2})")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


def date_from_ticker(ticker: str) -> str:
    match = TICKER_DATE.search(str(ticker or ""))
    if not match:
        return ""
    year, month, day = match.groups()
    return f"20{year}-{MONTHS[month]:02d}-{day}"


def kalshi_card_dates(*, timeout: int = 30, opener=urllib.request.urlopen) -> set[str]:
    """Every card date Kalshi has ever run mention markets on."""
    dates: set[str] = set()
    for status in ("settled", "closed", "open", "unopened"):
        url = f"{KALSHI_EVENTS}?series_ticker={SERIES}&status={status}&limit=200"
        try:
            with opener(url, timeout=timeout) as response:
                payload = json.load(response)
        except Exception:
            continue
        for event in payload.get("events") or []:
            card_date = date_from_ticker(event.get("event_ticker", ""))
            if card_date:
                dates.add(card_date)
    return dates


def recorded_cards(history_path: Path = HISTORY) -> dict[str, dict]:
    """Snapshot counts per card date, from the prices we actually stored."""
    if not history_path.exists():
        return {}
    seen: dict[str, dict] = defaultdict(lambda: {"snapshots": 0, "markets": set(), "first": "", "last": ""})
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            card_date = date_from_ticker(row.get("ticker", ""))
            if not card_date:
                continue
            entry = seen[card_date]
            entry["snapshots"] += 1
            entry["markets"].add(row.get("ticker", ""))
            stamp = str(row.get("snapshot_timestamp", ""))
            if not entry["first"] or stamp < entry["first"]:
                entry["first"] = stamp
            if stamp > entry["last"]:
                entry["last"] = stamp
    return {
        date: {
            "snapshots": entry["snapshots"],
            "markets": len(entry["markets"]),
            "first_seen": entry["first"],
            "last_seen": entry["last"],
        }
        for date, entry in seen.items()
    }


def build(*, kalshi_dates: set[str] | None = None, history_path: Path = HISTORY) -> dict:
    recorded = recorded_cards(history_path)
    listed = kalshi_card_dates() if kalshi_dates is None else set(kalshi_dates)
    reachable = bool(listed)

    # Cards that ran before this recorder existed are not misses. Recording
    # starts at the first card we ever captured.
    recording_since = min(recorded, default="")

    cards = []
    for card_date in sorted(set(recorded) | listed, reverse=True):
        had_markets = card_date in listed
        entry = recorded.get(card_date)
        if entry:
            state = "recorded"
        elif recording_since and card_date < recording_since:
            state = "before_recording"
        elif had_markets:
            state = "missed"
        else:
            state = "no_markets"
        cards.append({
            "date": card_date,
            "state": state,
            "kalshi_listed": had_markets,
            "snapshots": (entry or {}).get("snapshots", 0),
            "markets": (entry or {}).get("markets", 0),
            "first_seen": (entry or {}).get("first_seen", ""),
            "last_seen": (entry or {}).get("last_seen", ""),
        })

    missed = [c["date"] for c in cards if c["state"] == "missed"]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kalshi_reachable": reachable,
        "recording_since": recording_since,
        "cards_with_markets": sum(
            1 for c in cards if c["kalshi_listed"] and c["state"] != "before_recording"),
        "cards_recorded": sum(1 for c in cards if c["state"] == "recorded"),
        "cards_missed": len(missed),
        "missed_dates": missed,
        "latest_recorded": max((c["date"] for c in cards if c["state"] == "recorded"), default=""),
        "cards": cards[:24],
        "note": (
            "Kalshi does not open mention markets for every UFC card. A card "
            "with no markets is not a gap in our recording; a card Kalshi ran "
            "that we hold no snapshots for is."
        ),
    }


def main() -> None:
    report = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not report["kalshi_reachable"]:
        print("Could not reach Kalshi; coverage not verified.")
        return
    print(f"Since {report['recording_since']}: Kalshi ran markets on "
          f"{report['cards_with_markets']} cards; we recorded {report['cards_recorded']}.")
    if report["cards_missed"]:
        print(f"  MISSED: {', '.join(report['missed_dates'])}")
    else:
        print("  No missed cards.")
    for card in report["cards"][:8]:
        label = {"recorded": "recorded", "missed": "MISSED", "no_markets": "no markets",
                 "before_recording": "pre-recorder"}[card["state"]]
        print(f"  {card['date']}  {label:<11} {card['markets'] or '':>4} markets "
              f"{card['snapshots'] or '':>7} snapshots")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
