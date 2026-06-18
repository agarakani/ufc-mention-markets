#!/usr/bin/env python3
"""Predict simple binary mention-market probabilities for upcoming UFC cards.

This script bridges the model to real market structure:

  fight-level model probabilities
      -> event/card-level probability that a phrase appears at least once

For a simple binary market like:
  "Will the announcers say 'Guillotine' during UFC 250?"

the event-level probability is aggregated as:
  P(any fight says phrase) = 1 - product(1 - P(fight_i says phrase))

This uses an independence assumption across fights. It is a baseline aggregation
rule and should be tested against historical event-level markets.

Inputs:
  joined_fights.csv                         historical training data
  kaggle_data/ultimate_ufc_dataset/upcoming.csv  Kaggle-style upcoming card rows

Outputs:
  model_outputs/upcoming_fight_predictions.csv
  model_outputs/upcoming_event_predictions.csv

Run:
  python predict_upcoming_mentions.py
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from fighter_history_features import add_prior_fighter_features
from mention_counts import last_name
from train_baseline_models import (
    TARGETS,
    TARGET_LABELS,
    add_date_features,
    bool_series,
    calibrate_from_validation,
    chronological_split,
    feature_columns,
    make_pipeline,
    split_feature_types,
    tune_c,
)


PROJECT_ROOT = Path(__file__).resolve().parent
JOINED_DEFAULT = PROJECT_ROOT / "joined_fights.csv"
UPCOMING_DEFAULT = PROJECT_ROOT / "kaggle_data" / "ultimate_ufc_dataset" / "upcoming.csv"
METRICS_DEFAULT = PROJECT_ROOT / "model_outputs" / "baseline_metrics.csv"
OUT_DIR_DEFAULT = PROJECT_ROOT / "model_outputs"


def slug(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def normalize_upcoming(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in raw.iterrows():
        r_name = row.get("R_fighter", "")
        b_name = row.get("B_fighter", "")
        date = row.get("date", "")
        out = {
            "transcript_id": f"upcoming_{slug(date)}_{slug(r_name)}_vs_{slug(b_name)}",
            "fighter_1": r_name,
            "fighter_2": b_name,
            "fighter_1_last": last_name(r_name),
            "fighter_2_last": last_name(b_name),
            "event_date": date,
            "weight_class": row.get("weight_class", ""),
            "event_title": row.get("event_title", "") or f"Upcoming UFC card {date}",
            "duration_s": "",
        }
        for col, value in row.items():
            out[f"kaggle_{col}"] = value
        rows.append(out)
    return pd.DataFrame(rows)


def best_profiles(metrics_path: Path) -> dict[str, str]:
    if not metrics_path.exists():
        return {target: "prefight_odds_history" for target in TARGETS}
    metrics = pd.read_csv(metrics_path)
    profiles = {}
    for target, part in metrics.groupby("target"):
        part = part.sort_values(["log_loss_improvement", "auc"], ascending=[False, False])
        profiles[target] = part.iloc[0]["profile"]
    return {target: profiles.get(target, "prefight_odds_history") for target in TARGETS}


def train_predict_target(history, upcoming, target, profile):
    combined = pd.concat([history, upcoming], ignore_index=False, sort=False)
    cols = feature_columns(combined, profile=profile, include_identity=False, target=target)
    numeric_cols, categorical_cols, prepared = split_feature_types(combined, cols)
    x_hist = prepared.loc[history.index]
    x_upcoming = prepared.loc[upcoming.index]

    fit_train, val, _first_val_date = chronological_split(history, test_frac=0.20)
    x_fit = x_hist.loc[fit_train.index]
    x_val = x_hist.loc[val.index]
    y_fit = bool_series(fit_train[target]).astype(int)
    y_val = bool_series(val[target]).astype(int)

    if len(set(y_fit)) < 2:
        return np.repeat(bool_series(history[target]).astype(int).mean(), len(upcoming)), False, ""

    best_c, _val_loss = tune_c(x_fit, y_fit, x_val, y_val, numeric_cols, categorical_cols)
    pipe = make_pipeline(numeric_cols, categorical_cols, best_c)
    pipe.fit(x_fit, y_fit)
    val_prob = pipe.predict_proba(x_val)[:, 1]
    raw_upcoming = pipe.predict_proba(x_upcoming)[:, 1]
    calibrated, used_calibration = calibrate_from_validation(y_val, val_prob, raw_upcoming)
    return calibrated, used_calibration, best_c


def aggregate_event_probability(probs):
    probs = [min(max(float(p), 0.0), 1.0) for p in probs if pd.notna(p)]
    if not probs:
        return float("nan")
    return 1.0 - math.prod(1.0 - p for p in probs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", default=str(JOINED_DEFAULT))
    parser.add_argument("--upcoming", default=str(UPCOMING_DEFAULT))
    parser.add_argument("--metrics", default=str(METRICS_DEFAULT))
    parser.add_argument("--out-dir", default=str(OUT_DIR_DEFAULT))
    parser.add_argument(
        "--profile",
        choices=["best", "stats_only", "prefight_odds", "stats_only_history", "prefight_odds_history"],
        default="best",
    )
    args = parser.parse_args()

    history_path = Path(args.history)
    upcoming_path = Path(args.upcoming)
    out_dir = Path(args.out_dir)
    if not history_path.exists():
        raise SystemExit(f"Missing {history_path}. Run python3 join_kaggle_outcomes.py first.")
    if not upcoming_path.exists():
        raise SystemExit(f"Missing {upcoming_path}. Download/update Kaggle upcoming.csv first.")

    out_dir.mkdir(parents=True, exist_ok=True)
    history = add_date_features(pd.read_csv(history_path)).reset_index(drop=True)
    history.index = [f"h_{i}" for i in range(len(history))]
    upcoming_raw = pd.read_csv(upcoming_path)
    upcoming = add_date_features(normalize_upcoming(upcoming_raw)).reset_index(drop=True)
    upcoming.index = [f"u_{i}" for i in range(len(upcoming))]
    history, upcoming = add_prior_fighter_features(history, TARGETS, upcoming)

    profile_map = best_profiles(Path(args.metrics))
    if args.profile != "best":
        profile_map = {target: args.profile for target in TARGETS}

    fight_out = upcoming[[
        "event_date", "transcript_id", "fighter_1", "fighter_2", "weight_class",
        "kaggle_location", "kaggle_title_bout", "kaggle_no_of_rounds",
    ]].copy()

    metadata_rows = []
    for target in TARGETS:
        if target not in history.columns:
            continue
        profile = profile_map[target]
        probs, calibrated, best_c = train_predict_target(history, upcoming, target, profile)
        fight_out[f"{target}_prob"] = probs
        metadata_rows.append({
            "target": target,
            "label": TARGET_LABELS[target],
            "profile": profile,
            "calibrated": calibrated,
            "best_c": best_c,
            "historical_positive_rate": bool_series(history[target]).astype(int).mean(),
        })

    fight_path = out_dir / "upcoming_fight_predictions.csv"
    fight_out.to_csv(fight_path, index=False, quoting=csv.QUOTE_MINIMAL)

    event_rows = []
    group_cols = ["event_date", "kaggle_location"]
    for (event_date, location), part in fight_out.groupby(group_cols, dropna=False):
        for target in TARGETS:
            prob_col = f"{target}_prob"
            if prob_col not in part.columns:
                continue
            event_rows.append({
                "event_date": event_date,
                "location": location,
                "target": target,
                "phrase": TARGET_LABELS[target],
                "fight_count": len(part),
                "event_probability_any_fight": aggregate_event_probability(part[prob_col]),
                "mean_fight_probability": part[prob_col].mean(),
                "max_fight_probability": part[prob_col].max(),
                "profile": profile_map[target],
            })
    event_out = pd.DataFrame(event_rows).sort_values(
        ["event_date", "event_probability_any_fight"], ascending=[True, False]
    )
    event_path = out_dir / "upcoming_event_predictions.csv"
    event_out.to_csv(event_path, index=False, quoting=csv.QUOTE_MINIMAL)
    pd.DataFrame(metadata_rows).to_csv(out_dir / "upcoming_model_metadata.csv", index=False)

    print(f"Wrote fight-level predictions: {fight_path}")
    print(f"Wrote event-level predictions: {event_path}")
    print(f"Upcoming fights: {len(upcoming)}")
    print("\nTop event-level phrase probabilities:")
    for _, row in event_out.head(15).iterrows():
        print(
            f"  {row['event_date']} | {row['phrase']:<18} "
            f"event={row['event_probability_any_fight']:.3f} "
            f"max_fight={row['max_fight_probability']:.3f} "
            f"n={int(row['fight_count'])}"
        )


if __name__ == "__main__":
    main()
