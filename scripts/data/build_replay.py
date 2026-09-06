#!/usr/bin/env python3
"""Turn every settled card's recorded price history into a compact tape.

Kalshi's fight-mention markets are only open a few nights a month. The rest
of the time the record is the product: every phrase we priced, how the market
moved on it through the week, whether the word was said, and what our paper
trade did. This reads the raw snapshot history, downsamples each card to a
fixed number of frames, joins the settled outcome and any official paper
trade, and writes one tape per card.

Outputs:
  data/processed/tapes.json         every card, oldest first
  data/processed/replay_tape.json   the most recent card alone (older readers)

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
LABELS = ROOT / "data" / "processed" / "kalshi_results_labels.csv"
TRADES = ROOT / "model_outputs" / "pl_backtest_trades.csv"
OUT_ALL = ROOT / "data" / "processed" / "tapes.json"
OUT_LAST = ROOT / "data" / "processed" / "replay_tape.json"
DEFAULT_FRAMES = 72

MONTHS = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05", "JUN": "06",
          "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}


def _float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def card_of(ticker: str) -> str:
    """KXFIGHTMENTION-26JUL18DUUSM-DECI -> 26JUL18"""
    parts = ticker.split("-")
    return parts[1][:7] if len(parts) > 1 else ""


def card_date(card: str) -> str:
    """26JUL18 -> 2026-07-18; empty when the code does not parse."""
    if len(card) == 7 and card[2:5].upper() in MONTHS:
        return f"20{card[:2]}-{MONTHS[card[2:5].upper()]}-{card[5:7]}"
    return ""


def sample_stamps(stamps: list[str], frames: int) -> list[str]:
    """Even sampling across the recording, always keeping the final frame."""
    ordered = sorted(stamps)
    if not ordered:
        return []
    step = max(1, len(ordered) // max(1, frames))
    keep = ordered[::step][:frames]
    if keep[-1] != ordered[-1]:
        keep[-1] = ordered[-1]
    return keep


def read_labels(path: Path | None = None) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """Settled outcomes by ticker, and fighter names by event ticker."""
    path = path or LABELS
    outcomes: dict[str, str] = {}
    names: dict[str, tuple[str, str]] = {}
    if not path.exists():
        return outcomes, names
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            outcome = str(row.get("outcome", "")).strip().lower()
            if ticker and outcome in ("yes", "no"):
                outcomes[ticker] = outcome
            event = str(row.get("event_ticker", "")).strip()
            f1 = str(row.get("fighter_1", "")).strip()
            f2 = str(row.get("fighter_2", "")).strip()
            if event and f1 and f2 and event not in names:
                names[event] = (f1, f2)
    return outcomes, names


def read_trades(path: Path | None = None) -> dict[str, dict]:
    """The official paper trade on each ticker, if we took one."""
    path = path or TRADES
    trades: dict[str, dict] = {}
    if not path.exists():
        return trades
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("cohort", "")).strip() != "official":
                continue
            ticker = str(row.get("ticker", "")).strip()
            if not ticker or ticker in trades:
                continue
            won = str(row.get("won", "")).strip().lower() == "true"
            trades[ticker] = {
                "entered_at": str(row.get("entered_at", "")).strip(),
                "side": str(row.get("side", "")).strip().lower(),
                "price": _float(row.get("price")),
                "edge": _float(row.get("edge")),
                "pnl": _float(row.get("pnl")),
                "won": won,
            }
    return trades


def build_all(frames: int = DEFAULT_FRAMES, history_path: Path | None = None,
              labels_path: Path | None = None, trades_path: Path | None = None) -> dict:
    """One tape per recorded card, oldest first."""
    history_path = history_path or HISTORY
    if not history_path.exists():
        return {"cards": []}

    # Pass one: which snapshots exist per card. The history is tens of
    # megabytes, so we never hold every row at once.
    stamps_by_card: dict[str, set] = defaultdict(set)
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            stamp = str(row.get("snapshot_timestamp", ""))
            card = card_of(ticker)
            if ticker and stamp and card:
                stamps_by_card[card].add(stamp)
    if not stamps_by_card:
        return {"cards": []}

    keep_by_card = {card: sample_stamps(stamps, frames) for card, stamps in stamps_by_card.items()}
    slots_by_card = {card: {stamp: i for i, stamp in enumerate(keep)} for card, keep in keep_by_card.items()}

    # Pass two: fill the sampled frames.
    markets_by_card: dict[str, dict[str, dict]] = defaultdict(dict)
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            card = card_of(ticker)
            if not ticker or card not in slots_by_card:
                continue
            slot = slots_by_card[card].get(str(row.get("snapshot_timestamp", "")))
            if slot is None:
                continue
            width = len(keep_by_card[card])
            entry = markets_by_card[card].setdefault(ticker, {
                "ticker": ticker,
                "phrase": str(row.get("phrase", "")).strip(),
                "fighter_1": str(row.get("fighter_1", "") or "").strip(),
                "fighter_2": str(row.get("fighter_2", "") or "").strip(),
                "event_ticker": str(row.get("event_ticker", "")).strip(),
                "event_date": str(row.get("event_date", "") or "").strip(),
                "ask": [None] * width,
                "bid": [None] * width,
                "model": [None] * width,
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

    outcomes, names = read_labels(labels_path)
    trades = read_trades(trades_path)

    cards = []
    for card, markets in markets_by_card.items():
        keep = keep_by_card[card]
        usable = []
        for entry in markets.values():
            # carry the last known value forward so a frame is never a hole
            for field in ("ask", "bid", "model"):
                last = None
                for index, value in enumerate(entry[field]):
                    if value is None:
                        entry[field][index] = last
                    else:
                        last = value
            if entry["ask"][-1] is None or entry["model"][-1] is None:
                continue
            if not entry["fighter_1"]:
                entry["fighter_1"], entry["fighter_2"] = names.get(entry["event_ticker"], ("", ""))
            entry["result"] = outcomes.get(entry["ticker"])
            entry["trade"] = trades.get(entry["ticker"])
            usable.append(entry)
        if not usable:
            continue
        usable.sort(key=lambda m: (m["event_ticker"], m["phrase"]))
        date = card_date(card) or usable[0]["event_date"]
        cards.append({
            "card": card,
            "event_date": date,
            "frames": len(keep),
            "stamps": keep,
            "markets": usable,
            "fights": len({m["event_ticker"] for m in usable}),
            "said": sum(1 for m in usable if m["result"] == "yes"),
            "settled": sum(1 for m in usable if m["result"] in ("yes", "no")),
            "trades": sum(1 for m in usable if m["trade"]),
        })
    cards.sort(key=lambda c: (c["event_date"], c["card"]))
    return {"cards": cards}


def build(frames: int = DEFAULT_FRAMES, history_path: Path | None = None) -> dict:
    """The most recent card's tape alone, for readers of replay_tape.json."""
    cards = build_all(frames, history_path).get("cards") or []
    return cards[-1] if cards else {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    args = parser.parse_args()
    tapes = build_all(args.frames)
    cards = tapes.get("cards") or []
    if not cards:
        print("No recorded history to tape yet.")
        return
    OUT_ALL.parent.mkdir(parents=True, exist_ok=True)
    OUT_ALL.write_text(json.dumps(tapes, separators=(",", ":")) + "\n", encoding="utf-8")
    OUT_LAST.write_text(json.dumps(cards[-1], separators=(",", ":")) + "\n", encoding="utf-8")
    for tape in cards:
        print(f"card {tape['card']} ({tape['event_date']}): {len(tape['markets'])} markets, "
              f"{tape['fights']} fights, {tape['said']} said, {tape['trades']} trades, {tape['frames']} frames")
    print(f"Wrote {OUT_ALL} ({OUT_ALL.stat().st_size // 1024} KB) and {OUT_LAST.name}")


if __name__ == "__main__":
    main()
