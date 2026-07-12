#!/usr/bin/env python3
"""Turn settled Kalshi results into labeled training data, automatically.

Every settled mention market is a ground-truth label for exactly what the
model predicts: was this phrase group said during this fight, yes or no.
Transcripts are not needed for this — Kalshi's own resolutions are the
answer key, they cover the live cards and current broadcast teams the
transcript corpus cannot see, and they arrive on their own after each card.

This script assembles them into data/processed/kalshi_results_labels.csv:
one row per settled market with the fight date, both fighter names, the
phrase group, and the yes/no outcome. Fight metadata (fighters, phrase) is
read from the recorded price history; anything not covered there is
backfilled once from Kalshi, read-only, and cached in
market_data/kalshi_results_meta.csv.

The labels are collected now so the model can be retrained on them; the
retraining step itself is not wired up yet and nothing here changes live
predictions.

Usage:
  python3 scripts/model/build_results_labels.py [--offline]
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.model.backtest_pl import PRICE_HISTORY, RESULTS_CACHE, read_csv  # noqa: E402
from ufc_mentions.kalshi_mentions import (  # noqa: E402
    event_date_from_ticker,
    fighters_from_market_title,
)

META_CACHE = ROOT / "market_data" / "kalshi_results_meta.csv"
OUT_LABELS = ROOT / "data" / "processed" / "kalshi_results_labels.csv"

LABEL_FIELDS = [
    "event_date", "event_ticker", "ticker",
    "fighter_1", "fighter_2", "phrase", "forms", "outcome",
]
META_FIELDS = ["ticker", "event_ticker", "fighter_1", "fighter_2", "phrase", "forms"]


def load_meta() -> dict[str, dict]:
    return {row["ticker"]: row for row in read_csv(META_CACHE) if row.get("ticker")}


def save_meta(meta: dict[str, dict]) -> None:
    META_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with META_CACHE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=META_FIELDS)
        writer.writeheader()
        for ticker in sorted(meta):
            writer.writerow({field: meta[ticker].get(field, "") for field in META_FIELDS})


def meta_from_history(history: list[dict]) -> dict[str, dict]:
    """Phrase metadata per ticker from recorded snapshots (no network)."""
    meta: dict[str, dict] = {}
    for row in history:
        ticker = str(row.get("ticker", "")).strip()
        if not ticker or ticker in meta:
            continue
        meta[ticker] = {
            "ticker": ticker,
            "event_ticker": str(row.get("event_ticker", "")).strip(),
            "fighter_1": "",
            "fighter_2": "",
            "phrase": str(row.get("phrase", "")).strip(),
            "forms": "",
        }
    return meta


def backfill_from_kalshi(missing_events: set[str], meta: dict[str, dict]) -> int:
    """One-time, read-only fill of fighters/phrase for uncached events."""
    from ufc_mentions.kalshi_client import KalshiClient

    client = KalshiClient()
    added = 0
    for event_ticker in sorted(missing_events):
        try:
            markets = client.get_markets(event_ticker=event_ticker)
        except Exception as exc:
            print(f"  could not backfill {event_ticker}: {exc}")
            continue
        fighter_1 = fighter_2 = ""
        if markets:
            try:
                fighter_1, fighter_2 = fighters_from_market_title(markets[0].get("title", ""))
            except Exception:
                pass
        for market in markets:
            ticker = str(market.get("ticker", "")).strip()
            if not ticker:
                continue
            entry = meta.setdefault(ticker, {
                "ticker": ticker,
                "event_ticker": event_ticker,
                "phrase": "",
                "forms": "",
                "fighter_1": "",
                "fighter_2": "",
            })
            entry["fighter_1"] = entry.get("fighter_1") or fighter_1
            entry["fighter_2"] = entry.get("fighter_2") or fighter_2
            word = str((market.get("custom_strike") or {}).get("Word")
                       or market.get("yes_sub_title") or "").strip()
            entry["phrase"] = entry.get("phrase") or word
            added += 1
    return added


def assemble_labels(results: dict[str, str], meta: dict[str, dict]) -> list[dict]:
    labels = []
    for ticker, outcome in sorted(results.items()):
        if outcome not in ("yes", "no"):
            continue
        entry = meta.get(ticker, {})
        event_ticker = entry.get("event_ticker", "")
        labels.append({
            "event_date": event_date_from_ticker(event_ticker) or "",
            "event_ticker": event_ticker,
            "ticker": ticker,
            "fighter_1": entry.get("fighter_1", ""),
            "fighter_2": entry.get("fighter_2", ""),
            "phrase": entry.get("phrase", ""),
            "forms": entry.get("forms", ""),
            "outcome": outcome,
        })
    return labels


def build(offline: bool = False, quiet: bool = False) -> list[dict]:
    results = {
        row["ticker"]: row["result"]
        for row in read_csv(RESULTS_CACHE)
        if row.get("result") in ("yes", "no")
    }
    meta = load_meta()
    for ticker, entry in meta_from_history(read_csv(PRICE_HISTORY)).items():
        existing = meta.setdefault(ticker, entry)
        for field in ("event_ticker", "phrase"):
            if not existing.get(field):
                existing[field] = entry.get(field, "")

    missing_fighters = {
        meta[t]["event_ticker"] for t in results
        if t in meta and meta[t].get("event_ticker") and not meta[t].get("fighter_1")
    }
    missing_entirely = {
        t for t in results if t not in meta
    }
    if not offline and (missing_fighters or missing_entirely):
        events = set(missing_fighters)
        # tickers with no metadata at all: their event id prefixes the ticker
        for ticker in missing_entirely:
            events.add(ticker.rsplit("-", 1)[0])
        backfill_from_kalshi(events, meta)
        save_meta(meta)
    elif meta and not META_CACHE.exists():
        save_meta(meta)

    labels = assemble_labels(results, meta)
    OUT_LABELS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_LABELS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        writer.writerows(labels)

    if not quiet:
        with_fighters = sum(1 for row in labels if row["fighter_1"])
        dates = sorted({row["event_date"] for row in labels if row["event_date"]})
        span = f"{dates[0]} to {dates[-1]}" if dates else "none"
        print(f"Wrote {len(labels)} settled-market labels to {OUT_LABELS.relative_to(ROOT)}")
        print(f"  {with_fighters} with fighter names, covering {span}.")
        print("  These are ground-truth phrase outcomes for live cards; model retraining on them is the next step.")
    return labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="no network; use caches only")
    args = parser.parse_args()
    build(offline=args.offline)


if __name__ == "__main__":
    main()
