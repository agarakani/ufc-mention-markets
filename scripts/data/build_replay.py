#!/usr/bin/env python3
"""Turn a settled card's recorded price history into a replayable tape.

The board only moves when Kalshi has markets open, which is a couple of nights
a month. Every other night it sits still and says nothing about itself. This
takes a card we already recorded, downsamples it to a fixed number of frames,
and lets the board play that night back at speed: prices move, edges open and
close, the model line holds where it was.

Usage:
  python3 scripts/data/build_replay.py [--frames 72]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HISTORY = ROOT / "market_data" / "kalshi_price_history.csv"
OUT_PATH = ROOT / "data" / "processed" / "replay_tape.json"
DEFAULT_FRAMES = 72


def _float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def card_of(ticker: str) -> str:
    parts = ticker.split("-")
    return parts[1][:7] if len(parts) > 1 else ""


def build(frames: int = DEFAULT_FRAMES, history_path: Path = HISTORY) -> dict:
    if not history_path.exists():
        return {}

    by_card: dict[str, set] = defaultdict(set)
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            stamp = str(row.get("snapshot_timestamp", ""))
            if ticker and stamp:
                by_card[card_of(ticker)].add(stamp)
    if not by_card:
        return {}
    card = max(by_card, key=lambda key: len(by_card[key]))
    stamps = sorted(by_card[card])

    # even sampling across the night, always keeping the final frame
    step = max(1, len(stamps) // frames)
    keep = stamps[::step][:frames]
    if keep[-1] != stamps[-1]:
        keep[-1] = stamps[-1]
    slots = {stamp: index for index, stamp in enumerate(keep)}

    markets: dict[str, dict] = {}
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            if not ticker or card_of(ticker) != card:
                continue
            slot = slots.get(str(row.get("snapshot_timestamp", "")))
            if slot is None:
                continue
            entry = markets.setdefault(ticker, {
                "ticker": ticker,
                "phrase": row.get("phrase", ""),
                "fighter_1": row.get("fighter_1", ""),
                "fighter_2": row.get("fighter_2", ""),
                "event_ticker": row.get("event_ticker", ""),
                "event_date": row.get("event_date", ""),
                "ask": [None] * len(keep),
                "bid": [None] * len(keep),
                "model": [None] * len(keep),
            })
            ask = _float(row.get("yes_ask"))
            bid = _float(row.get("yes_bid"))
            model = _float(row.get("model_probability"))
            if ask is not None:
                entry["ask"][slot] = round(ask, 3)
            if bid is not None:
                entry["bid"][slot] = round(bid, 3)
            if model is not None:
                entry["model"][slot] = round(model, 3)

    # carry the last known value forward so a frame is never a hole
    for entry in markets.values():
        for field in ("ask", "bid", "model"):
            last = None
            for index, value in enumerate(entry[field]):
                if value is None:
                    entry[field][index] = last
                else:
                    last = value

    # Kalshi's ticker carries the card date (26JUL18), and the history rows do
    # not always fill event_date, so read it from the code we already have.
    months = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
              "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}
    card_date = ""
    if len(card) == 7 and card[2:5].upper() in months:
        card_date = f"20{card[:2]}-{months[card[2:5].upper()]}-{card[5:7]}"

    # The price history never carried fighter names; the settled-results
    # labels do. Join them in so the replay can name its fights.
    names: dict[str, tuple[str, str]] = {}
    labels_path = ROOT / "data" / "processed" / "kalshi_results_labels.csv"
    if labels_path.exists():
        with labels_path.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                event = str(row.get("event_ticker", "")).strip()
                f1 = str(row.get("fighter_1", "")).strip()
                f2 = str(row.get("fighter_2", "")).strip()
                if event and f1 and f2 and event not in names:
                    names[event] = (f1, f2)
    for entry in markets.values():
        if not entry["fighter_1"]:
            f1, f2 = names.get(entry["event_ticker"], ("", ""))
            entry["fighter_1"] = f1
            entry["fighter_2"] = f2

    usable = [m for m in markets.values() if m["ask"][-1] is not None and m["model"][-1] is not None]
    usable.sort(key=lambda m: -(abs((m["model"][-1] or 0) - (m["ask"][-1] or 0))))
    return {
        "card": card,
        "event_date": card_date or (usable[0]["event_date"] if usable else ""),
        "frames": len(keep),
        "stamps": keep,
        "markets": usable,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    args = parser.parse_args()
    tape = build(args.frames)
    if not tape:
        print("No recorded history to replay yet.")
        return
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(tape, separators=(",", ":")) + "\n", encoding="utf-8")
    size = OUT_PATH.stat().st_size
    print(f"card {tape['card']} ({tape['event_date']}): {len(tape['markets'])} markets over {tape['frames']} frames")
    print(f"Wrote {OUT_PATH} ({size // 1024} KB)")


if __name__ == "__main__":
    main()
