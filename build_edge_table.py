#!/usr/bin/env python3
"""Join model probabilities to real market prices and compute YES edge.

This script does not fetch prices and does not invent prices. It consumes:
  - model_outputs/baseline_predictions.csv
  - market_data/market_mappings.csv
  - market_data/oddpool_top_of_book.csv

The market mapping file is intentionally manual/reviewed because matching a
prediction-market question to a fight and literal phrase is a high-risk step.

Edge definition for buying YES:
  edge_to_yes_ask = model_probability - real_yes_ask

Rows without a real YES ask remain blank; that is safer than pretending a price.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from phrase_targets import phrase_to_column_map


PRED_DEFAULT = Path("model_outputs/baseline_predictions.csv")
MAPPING_DEFAULT = Path("market_data/market_mappings.csv")
BOOK_DEFAULT = Path("market_data/oddpool_top_of_book.csv")
OUT_DEFAULT = Path("market_data/edge_table.csv")

PHRASE_TO_TARGET = phrase_to_column_map()

OUT_FIELDS = [
    "profile",
    "transcript_id",
    "event_date",
    "fighter_1",
    "fighter_2",
    "phrase",
    "target",
    "model_probability",
    "actual",
    "exchange",
    "market_id",
    "asset_id",
    "token_side",
    "question",
    "snapshot_timestamp_iso",
    "yes_bid",
    "yes_ask",
    "mid",
    "spread",
    "edge_to_yes_ask",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def float_or_none(value):
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def market_key(row):
    return (
        (row.get("exchange") or "").lower(),
        row.get("market_id") or "",
        row.get("asset_id") or "",
        (row.get("token_side") or "").upper(),
    )


def latest_snapshot_by_market(rows):
    latest = {}
    for row in rows:
        key = market_key(row)
        timestamp = float_or_none(row.get("timestamp")) or -1
        current = latest.get(key)
        current_timestamp = float_or_none(current.get("timestamp")) if current else -1
        if current is None or timestamp > current_timestamp:
            latest[key] = row
    return latest


def index_predictions(rows, profile):
    out = {}
    for row in rows:
        if profile and row.get("profile") != profile:
            continue
        out[(row.get("profile"), row.get("transcript_id"))] = row
    return out


def choose_profiles(predictions, requested):
    if requested:
        return [requested]
    return sorted({row.get("profile") for row in predictions if row.get("profile")})


def build(predictions, mappings, snapshots, profile):
    snap_index = latest_snapshot_by_market(snapshots)
    pred_index = index_predictions(predictions, profile)
    profiles = choose_profiles(predictions, profile)
    rows = []

    for mapping in mappings:
        phrase = (mapping.get("phrase") or "").strip()
        target = PHRASE_TO_TARGET.get(phrase) or PHRASE_TO_TARGET.get(phrase.lower())
        if not target:
            continue
        for prof in profiles:
            pred = pred_index.get((prof, mapping.get("transcript_id")))
            if not pred:
                continue
            snapshot = snap_index.get(market_key(mapping), {})
            model_prob = float_or_none(pred.get(f"{target}_prob"))
            yes_ask = float_or_none(snapshot.get("yes_ask"))
            edge = model_prob - yes_ask if model_prob is not None and yes_ask is not None else None
            rows.append({
                "profile": prof,
                "transcript_id": mapping.get("transcript_id", ""),
                "event_date": mapping.get("event_date", "") or pred.get("event_date", ""),
                "fighter_1": mapping.get("fighter_1", "") or pred.get("fighter_1", ""),
                "fighter_2": mapping.get("fighter_2", "") or pred.get("fighter_2", ""),
                "phrase": phrase,
                "target": target,
                "model_probability": "" if model_prob is None else f"{model_prob:.6f}",
                "actual": pred.get(f"{target}_actual", ""),
                "exchange": mapping.get("exchange", ""),
                "market_id": mapping.get("market_id", ""),
                "asset_id": mapping.get("asset_id", ""),
                "token_side": mapping.get("token_side", ""),
                "question": mapping.get("question", ""),
                "snapshot_timestamp_iso": snapshot.get("timestamp_iso", ""),
                "yes_bid": snapshot.get("yes_bid", ""),
                "yes_ask": snapshot.get("yes_ask", ""),
                "mid": snapshot.get("mid", ""),
                "spread": snapshot.get("spread", ""),
                "edge_to_yes_ask": "" if edge is None else f"{edge:.6f}",
            })
    rows.sort(key=lambda r: float_or_none(r.get("edge_to_yes_ask")) or -999, reverse=True)
    return rows


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default=str(PRED_DEFAULT))
    parser.add_argument("--mappings", default=str(MAPPING_DEFAULT))
    parser.add_argument("--book", default=str(BOOK_DEFAULT))
    parser.add_argument("--profile", help="optional profile filter, e.g. prefight_odds")
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    for path in [args.predictions, args.mappings, args.book]:
        if not Path(path).exists():
            raise SystemExit(f"Missing {path}")

    rows = build(
        predictions=read_csv(Path(args.predictions)),
        mappings=read_csv(Path(args.mappings)),
        snapshots=read_csv(Path(args.book)),
        profile=args.profile,
    )
    write_csv(Path(args.out), rows)
    priced = sum(1 for row in rows if row.get("edge_to_yes_ask") not in ("", None))
    print(f"Wrote {len(rows)} edge rows to {args.out}")
    print(f"Rows with real YES ask and computed edge: {priced}")
    if rows[:10]:
        print("\nTop rows by edge:")
        for row in rows[:10]:
            print(
                f"  {row['edge_to_yes_ask'] or 'n/a':>8} | {row['phrase']:<18} | "
                f"{row['fighter_1']} vs {row['fighter_2']} | model={row['model_probability']} ask={row['yes_ask']}"
            )


if __name__ == "__main__":
    main()
