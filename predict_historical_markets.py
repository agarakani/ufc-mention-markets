#!/usr/bin/env python3
"""Create leakage-safe predictions for mapped historical mention markets.

For every market, the model is refit using fights strictly before the market's
event date. The market's own fight/event is never present in training.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd

from fighter_history_features import add_prior_fighter_features
from predict_upcoming_mentions import aggregate_event_probability, train_predict_target
from train_baseline_models import TARGETS, add_date_features


LEDGER_DEFAULT = Path("market_data/historical_market_ledger.csv")
HISTORY_DEFAULT = Path("joined_fights.csv")
OUT_DEFAULT = Path("model_outputs/historical_market_predictions.csv")

OUT_FIELDS = [
    "market_id", "exchange", "scope", "event_date", "event_start_iso", "transcript_id",
    "fighter_1", "fighter_2", "phrase", "target", "question", "profile",
    "model_probability", "training_rows", "training_end_date", "predicted_fights",
    "calibrated", "best_c", "aggregation_method", "resolved_yes",
    "resolution_source", "prediction_status", "prediction_error",
]


def read_ledger(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def prediction_rows(history: pd.DataFrame, market: dict) -> pd.DataFrame:
    event_date = market.get("event_date", "")
    rows = history.loc[history["event_date"].astype(str) == event_date]
    if market.get("scope") == "fight":
        rows = rows.loc[rows["transcript_id"].astype(str) == market.get("transcript_id", "")]
    return rows.copy()


def predict_market(history: pd.DataFrame, market: dict, profile: str, min_training_rows: int) -> dict:
    base = {field: market.get(field, "") for field in OUT_FIELDS}
    event_date = market.get("event_date", "")
    target = market.get("target", "")
    if not event_date:
        return {**base, "profile": profile, "prediction_status": "missing_event_date"}
    if target not in history.columns:
        return {**base, "profile": profile, "prediction_status": "missing_target"}

    event_dt = pd.to_datetime(event_date, errors="coerce")
    all_dates = pd.to_datetime(history["event_date"], errors="coerce")
    train = history.loc[all_dates < event_dt].copy()
    predict = prediction_rows(history, market)
    if len(train) < min_training_rows:
        return {**base, "profile": profile, "prediction_status": "insufficient_training_rows"}
    if predict.empty:
        return {**base, "profile": profile, "prediction_status": "missing_prediction_rows"}
    if not (pd.to_datetime(train["event_date"]).max() < event_dt):
        raise RuntimeError("chronology assertion failed: training includes market date or later")

    train = train.reset_index(drop=True)
    train.index = [f"h_{i}" for i in range(len(train))]
    predict = predict.reset_index(drop=True)
    predict.index = [f"p_{i}" for i in range(len(predict))]

    probabilities, calibrated, best_c = train_predict_target(train, predict, target, profile)
    if market.get("scope") == "event":
        probability = aggregate_event_probability(probabilities)
        aggregation = "independence_baseline"
    else:
        probability = float(probabilities[0])
        aggregation = "fight_direct"

    return {
        **base,
        "profile": profile,
        "model_probability": f"{probability:.8f}",
        "training_rows": len(train),
        "training_end_date": str(pd.to_datetime(train["event_date"]).max().date()),
        "predicted_fights": len(predict),
        "calibrated": calibrated,
        "best_c": best_c,
        "aggregation_method": aggregation,
        "prediction_status": "ok",
        "prediction_error": "",
    }


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", default=str(LEDGER_DEFAULT))
    parser.add_argument("--history", default=str(HISTORY_DEFAULT))
    parser.add_argument(
        "--profile",
        choices=["stats_only", "prefight_odds", "stats_only_history", "prefight_odds_history"],
        default="stats_only_history",
    )
    parser.add_argument("--min-training-rows", type=int, default=500)
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    history = add_date_features(pd.read_csv(args.history))
    history, _ = add_prior_fighter_features(history, TARGETS)
    output = []
    for market in read_ledger(Path(args.ledger)):
        try:
            output.append(predict_market(history, market, args.profile, args.min_training_rows))
        except Exception as exc:
            row = {field: market.get(field, "") for field in OUT_FIELDS}
            row.update({
                "profile": args.profile,
                "prediction_status": "error",
                "prediction_error": str(exc),
            })
            output.append(row)

    write_csv(Path(args.out), output)
    print(f"Wrote {len(output)} historical market prediction rows to {args.out}")
    print(f"  predicted: {sum(row.get('prediction_status') == 'ok' for row in output)}")
    for row in output:
        if row.get("prediction_status") != "ok":
            print(f"  skip {row.get('market_id')}: {row.get('prediction_status')}")


if __name__ == "__main__":
    main()
