#!/usr/bin/env python3
"""Build local dashboard data from generated model and market CSVs."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path

from phrase_targets import phrase_columns


ROOT = Path(__file__).resolve().parent
OUT_DEFAULT = ROOT / "dashboard" / "data.js"

FIGHT_PREDICTIONS = ROOT / "model_outputs" / "upcoming_fight_predictions.csv"
EVENT_PREDICTIONS = ROOT / "model_outputs" / "upcoming_event_predictions.csv"
METRICS = ROOT / "model_outputs" / "baseline_metrics.csv"
EVENT_METRICS = ROOT / "model_outputs" / "baseline_event_metrics.csv"
CALIBRATION = ROOT / "model_outputs" / "baseline_calibration.csv"
EVENT_CALIBRATION = ROOT / "model_outputs" / "baseline_event_calibration.csv"
TOP_FEATURES = ROOT / "model_outputs" / "baseline_top_features.csv"
BACKTEST_SUMMARY = ROOT / "model_outputs" / "historical_backtest_summary.json"
EDGE_TABLE = ROOT / "market_data" / "edge_table.csv"
MARKET_CANDIDATES = ROOT / "market_data" / "classified_markets.csv"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def number(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def as_int(value):
    parsed = number(value)
    return None if parsed is None else int(parsed)


def trim(row: dict, fields: list[str]) -> dict:
    return {field: row.get(field, "") for field in fields}


def build_fight_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        base = {
            "event_date": row.get("event_date", ""),
            "transcript_id": row.get("transcript_id", ""),
            "fighter_1": row.get("fighter_1", ""),
            "fighter_2": row.get("fighter_2", ""),
            "weight_class": row.get("weight_class", ""),
            "location": row.get("kaggle_location", ""),
            "title_bout": row.get("kaggle_title_bout", ""),
            "rounds": as_int(row.get("kaggle_no_of_rounds")),
        }
        for target, phrase in phrase_columns():
            probability = number(row.get(f"{target}_prob"))
            if probability is None:
                continue
            out.append({
                **base,
                "phrase": phrase,
                "target": target,
                "probability": probability,
            })
    out.sort(key=lambda item: item["probability"], reverse=True)
    return out


def build_event_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        out.append({
            "event_date": row.get("event_date", ""),
            "location": row.get("location", ""),
            "phrase": row.get("phrase", ""),
            "target": row.get("target", ""),
            "profile": row.get("profile", ""),
            "fight_count": as_int(row.get("fight_count")),
            "event_probability": number(row.get("event_probability_any_fight")),
            "mean_fight_probability": number(row.get("mean_fight_probability")),
            "max_fight_probability": number(row.get("max_fight_probability")),
        })
    out.sort(key=lambda item: item.get("event_probability") or -1, reverse=True)
    return out


def build_metric_rows(rows: list[dict], scope: str = "fight") -> list[dict]:
    best_by_target = {}
    for row in rows:
        target = row.get("target", "")
        if not target:
            continue
        candidate = {
            "profile": row.get("profile", ""),
            "scope": scope,
            "target": target,
            "phrase": row.get("label", ""),
            "auc": number(row.get("auc")),
            "average_precision": number(row.get("average_precision")),
            "test_positive_rate": number(row.get("test_positive_rate")),
            "top_decile_actual_rate": number(row.get("top_decile_actual_rate")),
            "log_loss_improvement": number(row.get("log_loss_improvement")),
            "test_rows": as_int(row.get("test_rows") or row.get("test_events")),
            "test_positives": as_int(row.get("test_positives")),
        }
        current = best_by_target.get(target)
        current_score = current.get("log_loss_improvement") if current else None
        candidate_score = candidate.get("log_loss_improvement")
        if current is None or (candidate_score or -999) > (current_score or -999):
            best_by_target[target] = candidate

    out = list(best_by_target.values())
    out.sort(key=lambda item: item.get("log_loss_improvement") or -999, reverse=True)
    return out


def build_calibration_rows(rows: list[dict], metrics: list[dict], scope: str) -> list[dict]:
    selected = {
        (row.get("target"), row.get("profile"))
        for row in metrics
        if row.get("scope") == scope
    }
    out = []
    for row in rows:
        if (row.get("target"), row.get("profile")) not in selected:
            continue
        target = row.get("target", "")
        out.append({
            "scope": scope,
            "profile": row.get("profile", ""),
            "target": target,
            "phrase": dict(phrase_columns()).get(target, target.removeprefix("mention_").replace("_", " ")),
            "bin": as_int(row.get("bin")),
            "rows": as_int(row.get("rows")),
            "mean_predicted": number(row.get("mean_predicted")),
            "actual_rate": number(row.get("actual_rate")),
        })
    return out


def build_feature_rows(rows: list[dict], metrics: list[dict]) -> list[dict]:
    selected = {
        row.get("target"): row.get("profile")
        for row in metrics
        if row.get("scope") == "fight"
    }
    labels = dict(phrase_columns())
    out = []
    for row in rows:
        target = row.get("target", "")
        if row.get("profile") != selected.get(target):
            continue
        out.append({
            "profile": row.get("profile", ""),
            "target": target,
            "phrase": labels.get(target, target),
            "feature": row.get("feature", ""),
            "coefficient": number(row.get("coefficient")),
        })
    return out


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_market_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if row.get("market_type") != "mention_announcers":
            continue
        out.append(trim(row, [
            "status",
            "mapped_phrase",
            "mapped_target",
            "market_complexity",
            "usable_as_binary_phrase",
            "needs_manual_review",
            "exchange",
            "market_id",
            "question",
            "event_title",
            "volume",
            "liquidity",
            "last_yes_price",
            "last_no_price",
            "settled_at",
            "slug",
        ]))
    out.sort(key=lambda row: (row.get("status") != "active", row.get("mapped_phrase", "")))
    return out


def build_edge_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        item = trim(row, [
            "scope",
            "profile",
            "transcript_id",
            "event_date",
            "location",
            "fighter_1",
            "fighter_2",
            "phrase",
            "target",
            "actual",
            "exchange",
            "market_id",
            "asset_id",
            "token_side",
            "question",
            "snapshot_timestamp_iso",
        ])
        item["model_probability"] = number(row.get("model_probability"))
        item["yes_bid"] = number(row.get("yes_bid"))
        item["yes_ask"] = number(row.get("yes_ask"))
        item["mid"] = number(row.get("mid"))
        item["spread"] = number(row.get("spread"))
        item["edge_to_yes_ask"] = number(row.get("edge_to_yes_ask"))
        out.append(item)
    out.sort(key=lambda item: item.get("edge_to_yes_ask") or -999, reverse=True)
    return out


def summarize(fight_predictions: list[dict], event_rows: list[dict], market_rows: list[dict], edge_rows: list[dict]) -> dict:
    fight_ids = {row.get("transcript_id") for row in fight_predictions if row.get("transcript_id")}
    event_dates = {row.get("event_date") for row in fight_predictions if row.get("event_date")}
    active_markets = [row for row in market_rows if row.get("status") == "active"]
    priced_edges = [row for row in edge_rows if row.get("edge_to_yes_ask") is not None]
    sorted_event_dates = sorted(event_dates)
    max_event_date = sorted_event_dates[-1] if sorted_event_dates else ""
    return {
        "fight_count": len(fight_ids),
        "event_count": len(event_dates),
        "min_event_date": sorted_event_dates[0] if sorted_event_dates else "",
        "max_event_date": max_event_date,
        "upcoming_input_is_stale": bool(max_event_date and max_event_date < date.today().isoformat()),
        "phrase_count": len(phrase_columns()),
        "event_prediction_count": len(event_rows),
        "market_candidate_count": len(market_rows),
        "active_market_candidate_count": len(active_markets),
        "edge_count": len(edge_rows),
        "priced_edge_count": len(priced_edges),
    }


def build_payload() -> dict:
    fight_predictions = read_csv(FIGHT_PREDICTIONS)
    event_predictions = read_csv(EVENT_PREDICTIONS)
    market_candidates = read_csv(MARKET_CANDIDATES)
    edge_table = read_csv(EDGE_TABLE)
    metric_rows = read_csv(METRICS)
    event_metric_rows = read_csv(EVENT_METRICS)
    fight_metrics = build_metric_rows(metric_rows, "fight")
    event_metrics = build_metric_rows(event_metric_rows, "event")
    metrics = fight_metrics + event_metrics

    event_rows = build_event_rows(event_predictions)
    fight_rows = build_fight_rows(fight_predictions)
    market_rows = build_market_rows(market_candidates)
    edge_rows = build_edge_rows(edge_table)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "fight_predictions": str(FIGHT_PREDICTIONS.relative_to(ROOT)),
            "event_predictions": str(EVENT_PREDICTIONS.relative_to(ROOT)),
            "metrics": str(METRICS.relative_to(ROOT)),
            "event_metrics": str(EVENT_METRICS.relative_to(ROOT)),
            "edge_table": str(EDGE_TABLE.relative_to(ROOT)),
            "market_candidates": str(MARKET_CANDIDATES.relative_to(ROOT)),
        },
        "summary": summarize(fight_predictions, event_rows, market_rows, edge_rows),
        "edges": edge_rows,
        "events": event_rows,
        "fights": fight_rows,
        "markets": market_rows,
        "metrics": metrics,
        "calibration": (
            build_calibration_rows(read_csv(CALIBRATION), metrics, "fight")
            + build_calibration_rows(read_csv(EVENT_CALIBRATION), metrics, "event")
        ),
        "features": build_feature_rows(read_csv(TOP_FEATURES), metrics),
        "backtest": read_json(BACKTEST_SUMMARY),
    }


def write_data(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(f"window.UFC_MENTION_DASHBOARD_DATA = {encoded};\n", encoding="utf-8")


def main():
    payload = build_payload()
    write_data(OUT_DEFAULT, payload)
    summary = payload["summary"]
    print(f"Wrote {OUT_DEFAULT.relative_to(ROOT)}")
    print(
        f"{summary['fight_count']} fights, {summary['phrase_count']} phrases, "
        f"{summary['market_candidate_count']} mention markets, {summary['priced_edge_count']} priced edges"
    )


if __name__ == "__main__":
    main()
