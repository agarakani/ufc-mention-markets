#!/usr/bin/env python3
"""Backtest exact Kalshi phrase models on individual historical fights.

Each test fold trains only on fights before the fold starts, predicts later
individual fights, and checks those predictions against the transcript labels.
No event-level aggregation is used here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

from scripts.model.audit_grouped_rules import load_rule_groups
from ufc_mentions.fighter_history_features import add_prior_fighter_features
from ufc_mentions.kalshi_context_model import TARGET, _prepare_with_types
from ufc_mentions.kalshi_mentions import TranscriptCorpus, grouped_matcher, wilson_lower_bound
from ufc_mentions.train_baseline_models import (
    add_date_features,
    bool_series,
    calibrate_from_validation,
    chronological_split,
    feature_columns,
    make_pipeline,
    split_feature_types,
    tune_c,
)


HISTORY_DEFAULT = ROOT / "data" / "processed" / "joined_fights.csv"
DATA_DEFAULT = ROOT / "ufc_cleaned_export"
RULES_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
OUT_DEFAULT = ROOT / "model_outputs" / "kalshi_context_model_backtest.csv"
PREDICTIONS_DEFAULT = ROOT / "model_outputs" / "kalshi_context_model_backtest_predictions.csv"
CALIBRATION_DEFAULT = ROOT / "model_outputs" / "kalshi_context_model_backtest_calibration.csv"
SUMMARY_DEFAULT = ROOT / "model_outputs" / "kalshi_context_model_backtest_summary.json"

SUMMARY_FIELDS = [
    "phrase", "forms", "profile", "folds", "scored_fights", "positives",
    "actual_rate", "mean_model_probability", "mean_safe_probability",
    "mean_base_probability", "model_log_loss", "base_log_loss",
    "log_loss_improvement", "safe_log_loss", "model_brier", "base_brier",
    "brier_improvement", "safe_brier", "auc", "average_precision",
    "calibration_ece", "top_decile_rows", "top_decile_model_probability",
    "top_decile_actual_rate", "first_test_date", "last_test_date", "status",
]

PREDICTION_FIELDS = [
    "phrase", "forms", "profile", "fold", "event_date", "transcript_id",
    "fighter_1", "fighter_2", "actual", "model_probability",
    "safe_probability", "base_probability", "training_rows",
    "validation_rows", "train_positive_rate", "train_wilson_lower_95",
    "best_c", "calibrated",
]

CALIBRATION_FIELDS = [
    "phrase", "forms", "profile", "bin", "rows", "mean_predicted",
    "actual_rate", "min_predicted", "max_predicted",
]


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in fields})


def format_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.8f}"
    return str(value)


def clipped(probability: float) -> float:
    return min(1.0 - 1e-6, max(1e-6, float(probability)))


def safe_auc(y_true: list[int], y_prob: list[float]) -> float | None:
    return roc_auc_score(y_true, y_prob) if len(set(y_true)) == 2 else None


def safe_average_precision(y_true: list[int], y_prob: list[float]) -> float | None:
    return average_precision_score(y_true, y_prob) if len(set(y_true)) == 2 else None


def calibration_rows(records: list[dict], *, bins: int) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for record in records:
        probability = max(0.0, min(1.0, float(record["model_probability"])))
        bin_index = min(bins, int(probability * bins) + 1)
        grouped.setdefault(bin_index, []).append(record)
    rows = []
    for bin_index in range(1, bins + 1):
        part = grouped.get(bin_index, [])
        if not part:
            continue
        probs = [float(row["model_probability"]) for row in part]
        actuals = [int(row["actual"]) for row in part]
        rows.append({
            "bin": bin_index,
            "rows": len(part),
            "mean_predicted": sum(probs) / len(probs),
            "actual_rate": sum(actuals) / len(actuals),
            "min_predicted": min(probs),
            "max_predicted": max(probs),
        })
    return rows


def calibration_ece(records: list[dict], *, bins: int) -> float | None:
    if not records:
        return None
    rows = calibration_rows(records, bins=bins)
    total = len(records)
    return sum(
        row["rows"] / total * abs(row["mean_predicted"] - row["actual_rate"])
        for row in rows
    )


def fold_ranges(dates: list[pd.Timestamp], *, folds: int, initial_train_frac: float) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    unique_dates = sorted({date for date in dates if pd.notna(date)})
    if len(unique_dates) < folds + 2:
        raise SystemExit("Not enough unique event dates for requested backtest folds.")
    first_test = max(1, min(len(unique_dates) - 1, int(len(unique_dates) * initial_train_frac)))
    test_dates = unique_dates[first_test:]
    chunks = np.array_split(np.array(test_dates, dtype=object), folds)
    ranges = []
    for chunk in chunks:
        if len(chunk):
            ranges.append((chunk[0], chunk[-1]))
    return ranges


def label_history(history: pd.DataFrame, corpus: TranscriptCorpus, forms: tuple[str, ...]) -> pd.DataFrame:
    text_by_id = {fight.transcript_id: fight.text for fight in corpus.fights}
    matcher = grouped_matcher(forms)
    out = history.loc[history["transcript_id"].astype(str).isin(text_by_id)].copy()
    out[TARGET] = out["transcript_id"].map(lambda value: bool(matcher(text_by_id[str(value)])))
    return out


def predict_fold(
    featured: pd.DataFrame,
    *,
    forms: tuple[str, ...],
    phrase: str,
    profile: str,
    fold_number: int,
    fold_start: pd.Timestamp,
    fold_end: pd.Timestamp,
    min_training_rows: int,
) -> list[dict]:
    dates = pd.to_datetime(featured["event_date"], errors="coerce")
    train = featured.loc[dates < fold_start].copy()
    test = featured.loc[(dates >= fold_start) & (dates <= fold_end)].copy()
    if len(train) < min_training_rows or test.empty:
        return []

    fit, validation, _first_validation_date = chronological_split(train, test_frac=0.20)
    y_fit = bool_series(fit[TARGET]).astype(int)
    y_validation = bool_series(validation[TARGET]).astype(int)
    y_test = bool_series(test[TARGET]).astype(int)
    if len(set(y_fit)) < 2 or len(set(y_validation)) < 2:
        return []

    columns = feature_columns(
        train,
        profile=profile,
        include_identity=False,
        target=TARGET,
    )
    numeric_columns, categorical_columns, prepared_fit_source = split_feature_types(train, columns)
    x_fit = prepared_fit_source.loc[fit.index]
    x_validation = prepared_fit_source.loc[validation.index]
    x_test = _prepare_with_types(test, columns, numeric_columns, categorical_columns)

    best_c, _validation_loss = tune_c(
        x_fit,
        y_fit,
        x_validation,
        y_validation,
        numeric_columns,
        categorical_columns,
    )
    pipe = make_pipeline(numeric_columns, categorical_columns, best_c)
    pipe.fit(x_fit, y_fit)
    validation_probability = pipe.predict_proba(x_validation)[:, 1]
    raw_test = pipe.predict_proba(x_test)[:, 1]
    model_probability, calibrated = calibrate_from_validation(
        y_validation,
        validation_probability,
        raw_test,
    )

    train_rate = float(y_fit.mean())
    train_hits = int(y_fit.sum())
    train_wilson = wilson_lower_bound(train_hits, len(y_fit)) or train_rate
    rows = []
    for position, (index, row) in enumerate(test.iterrows()):
        probability = clipped(float(model_probability[position]))
        rows.append({
            "phrase": phrase,
            "forms": " | ".join(forms),
            "profile": profile,
            "fold": fold_number,
            "event_date": row.get("event_date", ""),
            "transcript_id": row.get("transcript_id", ""),
            "fighter_1": row.get("fighter_1", ""),
            "fighter_2": row.get("fighter_2", ""),
            "actual": int(y_test.loc[index]),
            "model_probability": probability,
            "safe_probability": min(probability, train_wilson),
            "base_probability": train_rate,
            "training_rows": len(fit),
            "validation_rows": len(validation),
            "train_positive_rate": train_rate,
            "train_wilson_lower_95": train_wilson,
            "best_c": best_c,
            "calibrated": calibrated,
        })
    return rows


def summarize_predictions(records: list[dict], *, phrase: str, forms: tuple[str, ...], profile: str, bins: int) -> dict:
    actuals = [int(row["actual"]) for row in records]
    model_probs = [clipped(float(row["model_probability"])) for row in records]
    safe_probs = [clipped(float(row["safe_probability"])) for row in records]
    base_probs = [clipped(float(row["base_probability"])) for row in records]
    positives = sum(actuals)
    top_n = max(1, math.ceil(len(records) * 0.10))
    top_indices = sorted(range(len(records)), key=lambda i: model_probs[i], reverse=True)[:top_n]
    model_loss = log_loss(actuals, model_probs, labels=[0, 1])
    base_loss = log_loss(actuals, base_probs, labels=[0, 1])
    model_brier = brier_score_loss(actuals, model_probs)
    base_brier = brier_score_loss(actuals, base_probs)
    return {
        "phrase": phrase,
        "forms": " | ".join(forms),
        "profile": profile,
        "folds": len({row["fold"] for row in records}),
        "scored_fights": len(records),
        "positives": positives,
        "actual_rate": positives / len(records),
        "mean_model_probability": sum(model_probs) / len(model_probs),
        "mean_safe_probability": sum(safe_probs) / len(safe_probs),
        "mean_base_probability": sum(base_probs) / len(base_probs),
        "model_log_loss": model_loss,
        "base_log_loss": base_loss,
        "log_loss_improvement": base_loss - model_loss,
        "safe_log_loss": log_loss(actuals, safe_probs, labels=[0, 1]),
        "model_brier": model_brier,
        "base_brier": base_brier,
        "brier_improvement": base_brier - model_brier,
        "safe_brier": brier_score_loss(actuals, safe_probs),
        "auc": safe_auc(actuals, model_probs),
        "average_precision": safe_average_precision(actuals, model_probs),
        "calibration_ece": calibration_ece(records, bins=bins),
        "top_decile_rows": top_n,
        "top_decile_model_probability": sum(model_probs[i] for i in top_indices) / len(top_indices),
        "top_decile_actual_rate": sum(actuals[i] for i in top_indices) / len(top_indices),
        "first_test_date": min(row["event_date"] for row in records),
        "last_test_date": max(row["event_date"] for row in records),
        "status": "beats_base" if base_loss > model_loss else "underperforms_base",
    }


def run_backtest(
    history: pd.DataFrame,
    corpus: TranscriptCorpus,
    groups: list[dict],
    *,
    profile: str,
    folds: int,
    initial_train_frac: float,
    min_training_rows: int,
    bins: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    history = add_date_features(history).reset_index(drop=True)
    history.index = [f"h_{index}" for index in range(len(history))]
    date_values = pd.to_datetime(history["event_date"], errors="coerce")
    ranges = fold_ranges(list(date_values), folds=folds, initial_train_frac=initial_train_frac)

    summary_rows = []
    prediction_rows = []
    calibration = []
    for group in groups:
        forms = group["forms"]
        phrase = group["phrase"]
        labeled = label_history(history, corpus, forms)
        featured, _ = add_prior_fighter_features(labeled, [TARGET])

        group_predictions = []
        for fold_number, (fold_start, fold_end) in enumerate(ranges, start=1):
            group_predictions.extend(predict_fold(
                featured,
                forms=forms,
                phrase=phrase,
                profile=profile,
                fold_number=fold_number,
                fold_start=fold_start,
                fold_end=fold_end,
                min_training_rows=min_training_rows,
            ))
        if not group_predictions:
            summary_rows.append({
                "phrase": phrase,
                "forms": " | ".join(forms),
                "profile": profile,
                "status": "insufficient_sample",
            })
            continue

        summary_rows.append(summarize_predictions(
            group_predictions,
            phrase=phrase,
            forms=forms,
            profile=profile,
            bins=bins,
        ))
        prediction_rows.extend(group_predictions)
        for row in calibration_rows(group_predictions, bins=bins):
            calibration.append({
                "phrase": phrase,
                "forms": " | ".join(forms),
                "profile": profile,
                **row,
            })

    summary_rows.sort(key=lambda row: row.get("log_loss_improvement") or -999, reverse=True)
    prediction_rows.sort(key=lambda row: (row["phrase"], row["event_date"], row["transcript_id"]))
    return summary_rows, prediction_rows, calibration


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest exact Kalshi phrase models on individual historical fights.")
    parser.add_argument("--history", default=str(HISTORY_DEFAULT))
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--rules-csv", default=str(RULES_DEFAULT))
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--predictions-out", default=str(PREDICTIONS_DEFAULT))
    parser.add_argument("--calibration-out", default=str(CALIBRATION_DEFAULT))
    parser.add_argument("--summary-out", default=str(SUMMARY_DEFAULT))
    parser.add_argument("--profile", default="stats_only_history", choices=["stats_only", "prefight_odds", "stats_only_history", "prefight_odds_history"])
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--initial-train-frac", type=float, default=0.55)
    parser.add_argument("--min-training-rows", type=int, default=1000)
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args()

    history = pd.read_csv(args.history)
    corpus = TranscriptCorpus.load(args.data_dir)
    groups = load_rule_groups(Path(args.rules_csv))
    summary_rows, prediction_rows, calibration_rows_out = run_backtest(
        history,
        corpus,
        groups,
        profile=args.profile,
        folds=args.folds,
        initial_train_frac=args.initial_train_frac,
        min_training_rows=args.min_training_rows,
        bins=args.bins,
    )

    write_csv(Path(args.out), summary_rows, SUMMARY_FIELDS)
    write_csv(Path(args.predictions_out), prediction_rows, PREDICTION_FIELDS)
    write_csv(Path(args.calibration_out), calibration_rows_out, CALIBRATION_FIELDS)

    measured = [row for row in summary_rows if row.get("status") in {"beats_base", "underperforms_base"}]
    beats = [row for row in measured if row.get("status") == "beats_base"]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "history": str(Path(args.history)),
        "data_dir": str(Path(args.data_dir)),
        "rules_csv": str(Path(args.rules_csv)),
        "profile": args.profile,
        "folds": args.folds,
        "initial_train_frac": args.initial_train_frac,
        "min_training_rows": args.min_training_rows,
        "groups": len(summary_rows),
        "measured_groups": len(measured),
        "groups_beating_base_log_loss": len(beats),
        "prediction_rows": len(prediction_rows),
        "status": "fight_level_backtest_generated",
        "claim": "This tests prediction quality on old individual fights. It is not a money/profit backtest.",
    }
    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {Path(args.out).relative_to(ROOT)}")
    print(f"Wrote {Path(args.predictions_out).relative_to(ROOT)}")
    print(f"Wrote {Path(args.calibration_out).relative_to(ROOT)}")
    print(
        f"Backtested {len(measured)} exact phrase groups with {len(prediction_rows)} "
        f"individual fight predictions; {len(beats)} beat the simple base rate on log loss."
    )
    print("No profit claim is made by this output.")


if __name__ == "__main__":
    main()
