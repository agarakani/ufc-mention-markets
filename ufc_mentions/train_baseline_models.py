#!/usr/bin/env python3
"""Train leakage-safe baseline models for UFC literal mention markets.

Goal:
  Predict P(strict phrase is mentioned) before a fight starts.

Inputs:
  data/processed/joined_fights.csv, produced by:
    python3 scripts/data/build_match_csv.py
    python3 scripts/data/join_kaggle_outcomes.py

Targets:
  Loaded from market_phrases.txt. Each phrase becomes mention_<slug>.

Leakage policy:
  Features must be knowable before the fight. We explicitly exclude:
    - transcript text / transcript duration / transcript IDs
    - the mention target columns themselves
    - actual winner
    - actual finish, finish details, finish round/time, fight duration

Validation:
  Chronological split by event date. All fights on the same event date stay in the
  same split, so the model cannot learn from one fight on an event and test on
  another fight from that same event.

Feature profiles:
  stats_only     Pre-fight fighter/event stats, no betting odds.
  prefight_odds  stats_only plus pre-fight moneyline / method odds from Kaggle.

Outputs:
  model_outputs/baseline_metrics.csv
  model_outputs/baseline_calibration.csv
  model_outputs/baseline_top_features.csv
  model_outputs/baseline_predictions.csv

Run:
  python train_baseline_models.py
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


try:
    import numpy as np
    import pandas as pd
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import (
        average_precision_score,
        brier_score_loss,
        log_loss,
        roc_auc_score,
    )
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing ML dependencies. Install them with:\n"
        "  pip install -r requirements.txt\n\n"
        f"Original import error: {exc}"
    )

from .phrase_targets import phrase_columns
from .fighter_history_features import FEATURE_PREFIX, add_prior_fighter_features, feature_names


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOINED_DEFAULT = PROJECT_ROOT / "data" / "processed" / "joined_fights.csv"
OUT_DIR_DEFAULT = PROJECT_ROOT / "model_outputs"

PHRASE_COLUMNS = phrase_columns()
TARGETS = [column for column, _phrase in PHRASE_COLUMNS]
TARGET_LABELS = {column: phrase for column, phrase in PHRASE_COLUMNS}

# Columns that are definitely not allowed into any predictive feature set.
ALWAYS_EXCLUDE = {
    # Transcript identifiers / metadata / post-fight transcript artifacts.
    "transcript_id",
    "fighter_1",
    "fighter_2",
    "fighter_1_last",
    "fighter_2_last",
    "event_title",
    "duration_s",
    # Dates are used to split and are converted into coarse pre-fight date features.
    "event_date",
    "kaggle_date",
    # Actual fight outcome / post-fight information.
    "kaggle_Winner",
    "kaggle_finish",
    "kaggle_finish_details",
    "kaggle_finish_round",
    "kaggle_finish_round_time",
    "kaggle_total_fight_time_secs",
}

IDENTITY_COLUMNS = {
    # Useful in principle, but high-cardinality and easy to overfit. Disabled by default.
    "kaggle_R_fighter",
    "kaggle_B_fighter",
}

ODDS_COLUMNS = {
    "kaggle_R_odds",
    "kaggle_B_odds",
    "kaggle_R_ev",
    "kaggle_B_ev",
    "kaggle_r_dec_odds",
    "kaggle_b_dec_odds",
    "kaggle_r_sub_odds",
    "kaggle_b_sub_odds",
    "kaggle_r_ko_odds",
    "kaggle_b_ko_odds",
}

PREFIGHT_OUTCOME_MARKET_COLUMNS = {
    "kaggle_r_dec_odds",
    "kaggle_b_dec_odds",
    "kaggle_r_sub_odds",
    "kaggle_b_sub_odds",
    "kaggle_r_ko_odds",
    "kaggle_b_ko_odds",
}

C_GRID = [0.01, 0.03, 0.1, 0.3, 1.0]


def bool_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().map({"true": 1, "false": 0})


def parse_boolish(series: pd.Series) -> pd.Series:
    lowered = series.astype(str).str.strip().str.lower()
    mapped = lowered.map({"true": 1.0, "false": 0.0})
    return mapped.where(lowered.isin({"true", "false"}), series)


def add_date_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dates = pd.to_datetime(out["event_date"], errors="coerce")
    out["event_year"] = dates.dt.year
    out["event_month"] = dates.dt.month
    out["event_quarter"] = dates.dt.quarter
    return out


def chronological_split(df: pd.DataFrame, test_frac: float) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    dates = pd.to_datetime(df["event_date"], errors="coerce")
    valid = df.loc[dates.notna()].copy()
    valid["_event_date_dt"] = dates.loc[dates.notna()]
    unique_dates = sorted(valid["_event_date_dt"].dt.date.unique())
    if len(unique_dates) < 5:
        raise SystemExit("Not enough unique event dates for a chronological split.")

    cutoff_idx = max(1, min(len(unique_dates) - 1, math.floor(len(unique_dates) * (1 - test_frac))))
    first_test_date = unique_dates[cutoff_idx]
    train = valid.loc[valid["_event_date_dt"].dt.date < first_test_date].drop(columns=["_event_date_dt"])
    test = valid.loc[valid["_event_date_dt"].dt.date >= first_test_date].drop(columns=["_event_date_dt"])
    return train, test, first_test_date.isoformat()


def feature_columns(
    df: pd.DataFrame,
    profile: str,
    include_identity: bool,
    target: str | None = None,
) -> list[str]:
    use_history = profile.endswith("_history")
    base_profile = profile.removesuffix("_history")
    excluded = set(ALWAYS_EXCLUDE) | set(TARGETS)
    if not include_identity:
        excluded |= IDENTITY_COLUMNS
    if base_profile == "stats_only":
        excluded |= ODDS_COLUMNS
    elif base_profile == "prefight_odds":
        pass
    else:
        raise ValueError(f"unknown profile: {profile}")

    cols = []
    for col in df.columns:
        if col in excluded:
            continue
        if col.startswith("mention_"):
            continue
        # The joined file prefixes all Kaggle fields with kaggle_, plus we add date features.
        if (
            col.startswith("kaggle_")
            or col in {"weight_class", "event_year", "event_month", "event_quarter"}
            or (
                use_history
                and target is not None
                and col.startswith(FEATURE_PREFIX)
                and col in feature_names(target)
            )
        ):
            cols.append(col)
    return cols


def split_feature_types(df: pd.DataFrame, cols: list[str]) -> tuple[list[str], list[str], pd.DataFrame]:
    prepared = df[cols].copy()
    numeric_cols = []
    categorical_cols = []

    for col in cols:
        values = parse_boolish(prepared[col])
        as_num = pd.to_numeric(values.replace("", np.nan), errors="coerce")
        non_empty = prepared[col].astype(str).str.strip().ne("").sum()
        numeric_ratio = as_num.notna().sum() / max(non_empty, 1)

        if numeric_ratio >= 0.85:
            prepared[col] = as_num
            numeric_cols.append(col)
        else:
            prepared[col] = prepared[col].fillna("").astype(str)
            categorical_cols.append(col)

    return numeric_cols, categorical_cols, prepared


def make_pipeline(numeric_cols: list[str], categorical_cols: list[str], c_value: float) -> Pipeline:
    numeric_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical_pipe = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=10)),
    ])
    preprocessor = ColumnTransformer([
        ("num", numeric_pipe, numeric_cols),
        ("cat", categorical_pipe, categorical_cols),
    ])
    model = LogisticRegression(
        max_iter=5000,
        C=c_value,
        solver="lbfgs",
    )
    return Pipeline([
        ("prep", preprocessor),
        ("model", model),
    ])


def safe_auc(y_true, y_prob):
    return roc_auc_score(y_true, y_prob) if len(set(y_true)) == 2 else float("nan")


def safe_ap(y_true, y_prob):
    return average_precision_score(y_true, y_prob) if len(set(y_true)) == 2 else float("nan")


def top_decile_stats(y_true: pd.Series, y_prob: np.ndarray) -> tuple[float, float, int]:
    if len(y_true) == 0:
        return float("nan"), float("nan"), 0
    n = max(1, math.ceil(len(y_true) * 0.10))
    order = np.argsort(-y_prob)[:n]
    actual_rate = float(np.mean(np.asarray(y_true)[order]))
    predicted_rate = float(np.mean(y_prob[order]))
    return actual_rate, predicted_rate, n


def logit(prob):
    clipped = np.clip(prob, 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def calibrate_from_validation(y_val, val_prob, test_prob):
    """Platt-calibrate probabilities using only the inner validation window."""
    if len(set(y_val)) < 2:
        return test_prob, False
    calibrator = LogisticRegression(max_iter=1000, C=1_000_000.0, solver="lbfgs")
    calibrator.fit(logit(val_prob), y_val)
    calibrated = calibrator.predict_proba(logit(test_prob))[:, 1]
    return calibrated, True


def tune_c(x_fit, y_fit, x_val, y_val, numeric_cols, categorical_cols):
    if len(set(y_val)) < 2:
        return C_GRID[0], float("nan")
    best_c = None
    best_loss = float("inf")
    for c_value in C_GRID:
        pipe = make_pipeline(numeric_cols, categorical_cols, c_value)
        pipe.fit(x_fit, y_fit)
        val_prob = pipe.predict_proba(x_val)[:, 1]
        loss = log_loss(y_val, val_prob, labels=[0, 1])
        if loss < best_loss:
            best_c = c_value
            best_loss = loss
    return best_c, best_loss


def calibration_rows(profile, target, y_true, y_prob, bins=5):
    df = pd.DataFrame({"actual": np.asarray(y_true), "pred": y_prob})
    try:
        df["bin"] = pd.qcut(df["pred"], q=bins, duplicates="drop")
    except ValueError:
        df["bin"] = "all"
    rows = []
    for i, (_bin, part) in enumerate(df.groupby("bin", observed=False), start=1):
        rows.append({
            "profile": profile,
            "target": target,
            "bin": i,
            "rows": len(part),
            "mean_predicted": part["pred"].mean(),
            "actual_rate": part["actual"].mean(),
        })
    return rows


def event_evaluation(predictions: pd.DataFrame, train: pd.DataFrame):
    """Evaluate the fight-to-event independence aggregation on held-out cards."""
    metric_rows = []
    calibration = []
    for profile, part in predictions.groupby("profile"):
        for target in TARGETS:
            actual_col = f"{target}_actual"
            prob_col = f"{target}_prob"
            if actual_col not in part or prob_col not in part:
                continue
            event_rows = []
            for event_date, event in part.groupby("event_date"):
                probs = np.clip(pd.to_numeric(event[prob_col], errors="coerce").dropna(), 0, 1)
                actual = pd.to_numeric(event[actual_col], errors="coerce").dropna()
                if probs.empty or actual.empty:
                    continue
                event_rows.append({
                    "event_date": event_date,
                    "actual": int(actual.max()),
                    "probability": float(1.0 - np.prod(1.0 - probs)),
                    "fight_count": len(event),
                })
            if not event_rows:
                continue
            event_df = pd.DataFrame(event_rows)
            y_true = event_df["actual"].astype(int)
            y_prob = event_df["probability"].to_numpy()

            train_events = pd.DataFrame({
                "event_date": train["event_date"],
                "actual": bool_series(train[target]).astype(int),
            }).groupby("event_date")["actual"].max()
            base_rate = float(train_events.mean())
            base_prob = np.repeat(base_rate, len(event_df))
            model_loss = log_loss(y_true, y_prob, labels=[0, 1])
            base_loss = log_loss(y_true, base_prob, labels=[0, 1])
            model_brier = brier_score_loss(y_true, y_prob)
            base_brier = brier_score_loss(y_true, base_prob)
            metric_rows.append({
                "profile": profile,
                "target": target,
                "label": TARGET_LABELS[target],
                "test_events": len(event_df),
                "test_positive_rate": float(y_true.mean()),
                "test_positives": int(y_true.sum()),
                "train_event_positive_rate": base_rate,
                "auc": safe_auc(y_true, y_prob),
                "average_precision": safe_ap(y_true, y_prob),
                "model_log_loss": model_loss,
                "base_log_loss": base_loss,
                "log_loss_improvement": base_loss - model_loss,
                "model_brier": model_brier,
                "base_brier": base_brier,
                "brier_improvement": base_brier - model_brier,
                "mean_fights_per_event": float(event_df["fight_count"].mean()),
                "aggregation_method": "independence_baseline",
            })
            calibration.extend(calibration_rows(profile, target, y_true, y_prob))
    return pd.DataFrame(metric_rows), pd.DataFrame(calibration)


def get_feature_names(pipe: Pipeline) -> np.ndarray:
    try:
        return pipe.named_steps["prep"].get_feature_names_out()
    except Exception:
        return np.array([])


def coefficient_rows(profile, target, pipe: Pipeline, limit=20):
    names = get_feature_names(pipe)
    if len(names) == 0:
        return []
    coefs = pipe.named_steps["model"].coef_[0]
    order = np.argsort(-np.abs(coefs))[:limit]
    rows = []
    for idx in order:
        rows.append({
            "profile": profile,
            "target": target,
            "feature": names[idx],
            "coefficient": coefs[idx],
        })
    return rows


def fmt_pct(value):
    if pd.isna(value):
        return "n/a"
    return f"{100 * value:.1f}%"


def train_profile(df, train, test, profile, include_identity):
    fit_train, val, first_val_date = chronological_split(train, test_frac=0.20)

    metrics = []
    all_calibration = []
    all_coefficients = []
    all_predictions = pd.DataFrame({
        "event_date": test["event_date"].values,
        "transcript_id": test["transcript_id"].values,
        "fighter_1": test["fighter_1"].values,
        "fighter_2": test["fighter_2"].values,
        "profile": profile,
    })

    for target in TARGETS:
        cols = feature_columns(
            df,
            profile=profile,
            include_identity=include_identity,
            target=target,
        )
        numeric_cols, categorical_cols, prepared = split_feature_types(df, cols)
        # Hard assertion against accidental leakage. If this trips, fail loudly.
        forbidden = set(cols) & (ALWAYS_EXCLUDE | set(TARGETS))
        if forbidden:
            raise RuntimeError(f"Leakage columns entered feature set: {sorted(forbidden)}")
        x_test = prepared.loc[test.index]
        x_fit = prepared.loc[fit_train.index]
        x_val = prepared.loc[val.index]

        y_train = bool_series(train[target])
        y_fit = bool_series(fit_train[target])
        y_val = bool_series(val[target])
        y_test = bool_series(test[target])
        if y_train.isna().any() or y_fit.isna().any() or y_val.isna().any() or y_test.isna().any():
            raise RuntimeError(f"Target {target} contains non-boolean values.")
        y_train = y_train.astype(int)
        y_fit = y_fit.astype(int)
        y_val = y_val.astype(int)
        y_test = y_test.astype(int)

        train_rate = y_train.mean()
        test_rate = y_test.mean()
        base_prob = np.repeat(train_rate, len(y_test))

        pipe = None
        if len(set(y_fit)) < 2:
            # Very rare phrases can be all-zero in the fit window. Keep the target
            # in outputs with a base-rate fallback instead of crashing the run.
            best_c = ""
            val_loss = float("nan")
            prob = base_prob
            calibrated = False
        else:
            best_c, val_loss = tune_c(x_fit, y_fit, x_val, y_val, numeric_cols, categorical_cols)
            pipe = make_pipeline(numeric_cols, categorical_cols, best_c)
            pipe.fit(x_fit, y_fit)
            val_prob = pipe.predict_proba(x_val)[:, 1]
            raw_prob = pipe.predict_proba(x_test)[:, 1]
            prob, calibrated = calibrate_from_validation(y_val, val_prob, raw_prob)

        model_log_loss = log_loss(y_test, prob, labels=[0, 1])
        base_log_loss = log_loss(y_test, base_prob, labels=[0, 1])
        model_brier = brier_score_loss(y_test, prob)
        base_brier = brier_score_loss(y_test, base_prob)
        top_actual, top_pred, top_n = top_decile_stats(y_test, prob)

        metrics.append({
            "profile": profile,
            "target": target,
            "label": TARGET_LABELS[target],
            "train_rows": len(train),
            "fit_rows": len(fit_train),
            "validation_rows": len(val),
            "test_rows": len(test),
            "first_validation_date": first_val_date,
            "train_positive_rate": train_rate,
            "validation_positive_rate": y_val.mean(),
            "test_positive_rate": test_rate,
            "test_positives": int(y_test.sum()),
            "best_c": best_c,
            "validation_log_loss": val_loss,
            "calibrated": calibrated,
            "auc": safe_auc(y_test, prob),
            "average_precision": safe_ap(y_test, prob),
            "model_log_loss": model_log_loss,
            "base_log_loss": base_log_loss,
            "log_loss_improvement": base_log_loss - model_log_loss,
            "model_brier": model_brier,
            "base_brier": base_brier,
            "brier_improvement": base_brier - model_brier,
            "top_decile_rows": top_n,
            "top_decile_predicted_rate": top_pred,
            "top_decile_actual_rate": top_actual,
            "numeric_features": len(numeric_cols),
            "categorical_features": len(categorical_cols),
        })
        all_calibration.extend(calibration_rows(profile, target, y_test, prob))
        if pipe is not None:
            all_coefficients.extend(coefficient_rows(profile, target, pipe))
        all_predictions[f"{target}_actual"] = y_test.values
        all_predictions[f"{target}_prob"] = prob

    return (
        pd.DataFrame(metrics),
        pd.DataFrame(all_calibration),
        pd.DataFrame(all_coefficients),
        all_predictions,
        cols,
        numeric_cols,
        categorical_cols,
    )


def print_summary(metrics: pd.DataFrame, first_test_date: str):
    print(f"Chronological test period starts: {first_test_date}")
    print("\nBaseline model results (positive improvement means model beat train-base-rate baseline)")
    print("--------------------------------------------------------------------------------------")
    display_cols = [
        "profile",
        "label",
        "test_positive_rate",
        "auc",
        "average_precision",
        "log_loss_improvement",
        "brier_improvement",
        "top_decile_actual_rate",
        "best_c",
    ]
    rows = []
    for _, row in metrics.sort_values(["profile", "target"]).iterrows():
        rows.append([
            row["profile"],
            row["label"],
            fmt_pct(row["test_positive_rate"]),
            "n/a" if pd.isna(row["auc"]) else f"{row['auc']:.3f}",
            "n/a" if pd.isna(row["average_precision"]) else f"{row['average_precision']:.3f}",
            f"{row['log_loss_improvement']:.4f}",
            f"{row['brier_improvement']:.4f}",
            fmt_pct(row["top_decile_actual_rate"]),
            row["best_c"],
        ])

    widths = [len(c) for c in display_cols]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))

    def fmt(row):
        return "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row))

    print(fmt(display_cols))
    print(fmt(["-" * w for w in widths]))
    for row in rows:
        print(fmt(row))


def write_manifest(out_dir, args, first_test_date, feature_info):
    with open(out_dir / "feature_manifest.txt", "w", encoding="utf-8") as fh:
        fh.write("Leakage-safe baseline model feature manifest\n")
        fh.write("============================================\n\n")
        fh.write(f"input: {args.input}\n")
        fh.write(f"test_frac: {args.test_frac}\n")
        fh.write(f"first_test_date: {first_test_date}\n")
        fh.write(f"include_identity: {args.include_identity}\n\n")
        fh.write("Modeling note:\n")
        fh.write("  Each target tunes logistic-regression C on an inner chronological validation\n")
        fh.write("  split, then Platt-calibrates probabilities on that validation window before\n")
        fh.write("  scoring the final chronological test window.\n\n")
        fh.write("Forbidden leakage columns:\n")
        for col in sorted(ALWAYS_EXCLUDE | set(TARGETS)):
            fh.write(f"  - {col}\n")
        fh.write("\n")
        for profile, info in feature_info.items():
            fh.write(f"Profile: {profile}\n")
            fh.write(f"  numeric_features: {len(info['numeric'])}\n")
            fh.write(f"  categorical_features: {len(info['categorical'])}\n")
            fh.write("  columns:\n")
            for col in info["columns"]:
                fh.write(f"    - {col}\n")
            fh.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(JOINED_DEFAULT), help="joined_fights.csv path")
    parser.add_argument("--out-dir", default=str(OUT_DIR_DEFAULT), help="where generated model outputs go")
    parser.add_argument("--test-frac", type=float, default=0.20, help="fraction of event dates reserved for test")
    parser.add_argument(
        "--profile",
        choices=["all", "stats_only", "prefight_odds", "stats_only_history", "prefight_odds_history"],
        default="all",
    )
    parser.add_argument(
        "--include-identity",
        action="store_true",
        help="include fighter-name one-hot features; disabled by default to reduce overfit",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    out_dir = Path(args.out_dir)
    if not input_path.exists():
        raise SystemExit(f"Missing {input_path}. Run python3 scripts/data/join_kaggle_outcomes.py first.")
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(input_path)
    df = add_date_features(df)
    missing_targets = [t for t in TARGETS if t not in df.columns]
    if missing_targets:
        raise SystemExit(f"Missing target columns in {input_path}: {missing_targets}")

    df, _ = add_prior_fighter_features(df, TARGETS)
    train, test, first_test_date = chronological_split(df, args.test_frac)
    profiles = (
        ["stats_only", "prefight_odds", "stats_only_history", "prefight_odds_history"]
        if args.profile == "all"
        else [args.profile]
    )

    metric_frames = []
    calibration_frames = []
    coefficient_frames = []
    prediction_frames = []
    feature_info = {}

    for profile in profiles:
        metrics, calibration, coefficients, predictions, cols, num_cols, cat_cols = train_profile(
            df=df,
            train=train,
            test=test,
            profile=profile,
            include_identity=args.include_identity,
        )
        metric_frames.append(metrics)
        calibration_frames.append(calibration)
        coefficient_frames.append(coefficients)
        prediction_frames.append(predictions)
        feature_info[profile] = {
            "columns": cols,
            "numeric": num_cols,
            "categorical": cat_cols,
        }

    metrics = pd.concat(metric_frames, ignore_index=True)
    calibration = pd.concat(calibration_frames, ignore_index=True)
    coefficients = pd.concat(coefficient_frames, ignore_index=True)
    predictions = pd.concat(prediction_frames, ignore_index=True)
    event_metrics, event_calibration = event_evaluation(predictions, train)

    metrics.to_csv(out_dir / "baseline_metrics.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    calibration.to_csv(out_dir / "baseline_calibration.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    coefficients.to_csv(out_dir / "baseline_top_features.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    predictions.to_csv(out_dir / "baseline_predictions.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    event_metrics.to_csv(out_dir / "baseline_event_metrics.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    event_calibration.to_csv(out_dir / "baseline_event_calibration.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    write_manifest(out_dir, args, first_test_date, feature_info)

    print(f"Rows: train={len(train)}, test={len(test)}, total={len(df)}")
    print(f"Wrote model outputs to: {out_dir}")
    for profile, info in feature_info.items():
        print(
            f"Feature profile {profile}: "
            f"{len(info['numeric'])} numeric + {len(info['categorical'])} categorical "
            f"({len(info['columns'])} raw columns)"
        )
    print_summary(metrics, first_test_date)


if __name__ == "__main__":
    main()
