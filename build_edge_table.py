#!/usr/bin/env python3
"""Join model probabilities to market prices and compute YES edge.

Inputs:
  - model_outputs/upcoming_fight_predictions.csv
  - model_outputs/upcoming_event_predictions.csv
  - market_data/market_mappings.csv
  - market_data/oddpool_top_of_book.csv

Edge definition for buying YES:
  edge_to_yes_ask = model_probability - real_yes_ask
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from phrase_targets import phrase_to_column_map


FIGHT_PRED_DEFAULT = Path("model_outputs/upcoming_fight_predictions.csv")
EVENT_PRED_DEFAULT = Path("model_outputs/upcoming_event_predictions.csv")
MAPPING_DEFAULT = Path("market_data/market_mappings.csv")
BOOK_DEFAULT = Path("market_data/oddpool_top_of_book.csv")
OUT_DEFAULT = Path("market_data/edge_table.csv")

PHRASE_TO_TARGET = phrase_to_column_map()

OUT_FIELDS = [
    "scope",
    "profile",
    "transcript_id",
    "event_date",
    "location",
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


def index_fight_predictions(rows):
    out = {}
    for row in rows:
        out[row.get("transcript_id")] = row
    return out


def index_event_predictions(rows):
    out = {}
    for row in rows:
        out[(row.get("event_date"), (row.get("phrase") or "").lower())] = row
    return out


def build(fight_predictions, event_predictions, mappings, snapshots, profile):
    snap_index = latest_snapshot_by_market(snapshots)
    fight_index = index_fight_predictions(fight_predictions)
    event_index = index_event_predictions(event_predictions)
    rows = []

    for mapping in mappings:
        scope = (mapping.get("scope") or "fight").strip().lower()
        phrase = (mapping.get("phrase") or "").strip()
        target = PHRASE_TO_TARGET.get(phrase) or PHRASE_TO_TARGET.get(phrase.lower())
        if not target:
            continue

        pred = None
        model_prob = None
        actual = ""
        selected_profile = profile or ""
        location = mapping.get("location", "")

        if scope == "fight":
            pred = fight_index.get(mapping.get("transcript_id"))
            if not pred:
                continue
            model_prob = float_or_none(pred.get(f"{target}_prob"))
            actual = pred.get(f"{target}_actual", "")
            location = location or pred.get("kaggle_location", "")
        elif scope == "event":
            pred = event_index.get((mapping.get("event_date"), phrase.lower()))
            if not pred:
                continue
            model_prob = float_or_none(pred.get("event_probability_any_fight"))
            selected_profile = pred.get("profile", "") or selected_profile
            location = location or pred.get("location", "")
        else:
            continue

        snapshot = snap_index.get(market_key(mapping), {})
        yes_ask = float_or_none(snapshot.get("yes_ask"))
        edge = model_prob - yes_ask if model_prob is not None and yes_ask is not None else None
        rows.append({
            "scope": scope,
            "profile": selected_profile,
            "transcript_id": mapping.get("transcript_id", ""),
            "event_date": mapping.get("event_date", "") or (pred or {}).get("event_date", ""),
            "location": location,
            "fighter_1": mapping.get("fighter_1", "") or (pred or {}).get("fighter_1", ""),
            "fighter_2": mapping.get("fighter_2", "") or (pred or {}).get("fighter_2", ""),
            "phrase": phrase,
            "target": target,
            "model_probability": "" if model_prob is None else f"{model_prob:.6f}",
            "actual": actual,
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
    parser.add_argument("--fight-predictions", default=str(FIGHT_PRED_DEFAULT))
    parser.add_argument("--event-predictions", default=str(EVENT_PRED_DEFAULT))
    parser.add_argument("--mappings", default=str(MAPPING_DEFAULT))
    parser.add_argument("--book", default=str(BOOK_DEFAULT))
    parser.add_argument("--profile", help="optional profile label to include in fight rows")
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    for path in [args.fight_predictions, args.event_predictions, args.mappings, args.book]:
        if not Path(path).exists():
            raise SystemExit(f"Missing {path}")

    rows = build(
        fight_predictions=read_csv(Path(args.fight_predictions)),
        event_predictions=read_csv(Path(args.event_predictions)),
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
                f"  {row['edge_to_yes_ask'] or 'n/a':>8} | {row['scope']:<5} | {row['phrase']:<18} | "
                f"{row['fighter_1']} vs {row['fighter_2']} | model={row['model_probability']} ask={row['yes_ask']}"
            )


if __name__ == "__main__":
    main()
