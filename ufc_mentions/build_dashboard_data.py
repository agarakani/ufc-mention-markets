#!/usr/bin/env python3
"""Build the local dashboard feed for live Kalshi UFC mention prices."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DEFAULT = ROOT / "dashboard" / "data.js"

KALSHI_LIVE = ROOT / "market_data" / "kalshi_live_edges.csv"
KALSHI_META = ROOT / "market_data" / "kalshi_live_meta.json"
KALSHI_AUDIT_SUMMARY = ROOT / "model_outputs" / "kalshi_grouped_rule_audit_summary.json"
KALSHI_CONTEXT_BACKTEST_SUMMARY = ROOT / "model_outputs" / "kalshi_context_model_backtest_summary.json"
TRACKING_ROOT = ROOT / "data" / "tracking"
TRACKING_WEEKLY_SUMMARY = TRACKING_ROOT / "weekly_summary.csv"


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def build_kalshi_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        item = trim(row, [
            "snapshot_timestamp",
            "series_ticker",
            "event_ticker",
            "event_date",
            "event_title",
            "fighter_1",
            "fighter_2",
            "ticker",
            "phrase",
            "forms",
            "rules_primary",
            "word_type",
            "confidence_note",
            "status",
            "validation_status",
            "error",
            "probability_source",
            "context_status",
            "context_note",
            "context_profile",
            "context_best_c",
            "context_calibrated",
            "context_row_source",
        ])
        for field in [
            "model_probability",
            "history_probability",
            "context_probability",
            "context_positive_rate",
            "context_validation_log_loss",
            "context_base_log_loss",
            "context_log_loss_improvement",
            "league_rate",
            "fighter_rate",
            "yes_bid",
            "yes_ask",
            "no_bid",
            "no_ask",
            "spread",
            "fee_buffer",
            "data_buffer",
            "hurdle",
            "yes_edge",
            "no_edge",
            "side_price",
            "edge",
            "previous_yes_ask",
            "ask_change",
        ]:
            item[field] = number(row.get(field))
        for field in [
            "league_hits",
            "league_fights",
            "fighter_hits",
            "fighter_fights",
            "context_training_rows",
            "context_validation_rows",
        ]:
            item[field] = as_int(row.get(field))

        item["confidence_ok"] = as_bool(row.get("confidence_ok"))
        item["data_risk"] = as_bool(row.get("data_risk"))
        item["side"] = str(row.get("side", "")).strip().lower()
        item["watch"] = as_bool(row.get("watch")) or legacy_watch(row, item)
        if item["watch"] and not item.get("validation_status"):
            item["validation_status"] = "unvalidated"
        out.append(item)

    out.sort(key=kalshi_sort_key)
    return out


def legacy_watch(row: dict, item: dict) -> bool:
    return bool(
        row.get("qualified") == "yes"
        and item.get("confidence_ok")
        and item.get("edge") is not None
        and item.get("hurdle") is not None
        and item["edge"] > item["hurdle"]
    )


def kalshi_sort_key(item: dict):
    best_edge = item.get("edge")
    if best_edge is None:
        best_edge = -999
    return (
        not item.get("watch", False),
        -best_edge,
        item.get("event_date", ""),
        item.get("phrase", ""),
    )


def build_kalshi_event_rows(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        event_ticker = row.get("event_ticker", "")
        if not event_ticker:
            continue
        item = grouped.setdefault(event_ticker, {
            "event_ticker": event_ticker,
            "event_date": row.get("event_date", ""),
            "event_title": row.get("event_title", ""),
            "fighter_1": row.get("fighter_1", ""),
            "fighter_2": row.get("fighter_2", ""),
            "snapshot_timestamp": row.get("snapshot_timestamp", ""),
            "market_count": 0,
            "priced_count": 0,
            "model_ready_count": 0,
            "error_count": 0,
            "watch_count": 0,
            "best_edge": None,
        })
        item["market_count"] += 1
        if row.get("yes_ask") is not None:
            item["priced_count"] += 1
        if row.get("probability_source") == "fight_context_model":
            item["model_ready_count"] += 1
        if row.get("status") == "error":
            item["error_count"] += 1
        if row.get("watch"):
            item["watch_count"] += 1
        keep_best(item, "best_edge", row.get("edge"))
    return sorted(grouped.values(), key=lambda item: (item.get("event_date", ""), item["event_ticker"]))


def build_tracking_cards() -> list[dict]:
    cards = []
    if not TRACKING_ROOT.exists():
        return cards

    summary_by_card = {row.get("card", ""): row for row in read_csv(TRACKING_WEEKLY_SUMMARY)}
    for card_dir in sorted(path for path in TRACKING_ROOT.iterdir() if path.is_dir()):
        card = card_dir.name
        predictions = read_csv(card_dir / "predictions.csv")
        positions = read_csv(card_dir / "paper_positions.csv")
        outcomes = read_csv(card_dir / "outcomes.csv")
        summary = read_json(card_dir / "summary.json")
        weekly = summary_by_card.get(card, {})
        official_rows = [row for row in positions if row.get("paper_action") == "trade"]
        lean_rows = [row for row in positions if row.get("paper_action") == "lean"]
        outcomes_filled = sum(str(row.get("outcome", "")).strip().lower() in {"yes", "no"} for row in outcomes)

        cards.append({
            "card": card,
            "label": card.replace("_", " ").title(),
            "prediction_rows": as_int(weekly.get("prediction_rows")) or len(predictions),
            "outcomes_filled": as_int(weekly.get("outcomes_filled")) or outcomes_filled,
            "official_trades": as_int(weekly.get("official_trades")) or len(official_rows),
            "official_wins": as_int(weekly.get("official_wins")),
            "official_pnl": number(weekly.get("official_pnl")),
            "official_roi": number(weekly.get("official_roi")),
            "leans": len(lean_rows),
            "lean_wins": as_int(weekly.get("lean_wins")),
            "lean_pnl": number(weekly.get("lean_pnl")),
            "lean_roi": number(weekly.get("lean_roi")),
            "settled_at": summary.get("settled_at", weekly.get("settled_at", "")),
            "path": str(card_dir.relative_to(ROOT)),
        })
    cards.sort(key=lambda item: item.get("settled_at") or item.get("card", ""), reverse=True)
    return cards


def build_tracking_positions() -> list[dict]:
    if not TRACKING_ROOT.exists():
        return []
    positions = []
    for card_dir in sorted(path for path in TRACKING_ROOT.iterdir() if path.is_dir()):
        outcomes_by_ticker = {
            row.get("ticker", ""): row
            for row in read_csv(card_dir / "outcomes.csv")
        }
        for row in read_csv(card_dir / "paper_positions.csv"):
            item = trim(row, [
                "card",
                "paper_action",
                "paper_reason",
                "event_title",
                "fighter_1",
                "fighter_2",
                "ticker",
                "phrase",
                "watch",
                "confidence_note",
            ])
            for field in [
                "paper_price",
                "model_probability",
                "yes_ask",
                "no_ask",
                "yes_edge",
                "no_edge",
                "side_price",
                "data_buffer",
                "edge",
                "hurdle",
            ]:
                item[field] = number(row.get(field))
            item["paper_side"] = str(row.get("paper_side") or row.get("side") or "").strip().lower()
            item["side"] = str(row.get("side", "")).strip().lower()
            item["data_risk"] = as_bool(row.get("data_risk"))
            outcome_row = outcomes_by_ticker.get(row.get("ticker", ""), {})
            item["outcome"] = str(outcome_row.get("outcome", "")).strip().lower()
            item["notes"] = outcome_row.get("notes", "")
            item["matchup"] = (
                f"{row.get('fighter_1')} vs {row.get('fighter_2')}"
                if row.get("fighter_1") and row.get("fighter_2")
                else row.get("event_title", "")
            )
            positions.append(item)
    positions.sort(key=lambda item: (
        item.get("card", ""),
        item.get("paper_action") != "trade",
        item.get("edge") if item.get("edge") is not None else -999,
    ), reverse=True)
    return positions


def summarize_tracking(cards: list[dict], positions: list[dict]) -> dict:
    return {
        "tracking_card_count": len(cards),
        "tracking_position_count": len(positions),
        "tracking_official_trade_count": sum(card.get("official_trades") or 0 for card in cards),
        "tracking_lean_count": sum(card.get("leans") or 0 for card in cards),
        "tracking_outcomes_filled": sum(card.get("outcomes_filled") or 0 for card in cards),
        "tracking_official_pnl": sum(card.get("official_pnl") or 0 for card in cards),
        "tracking_lean_pnl": sum(card.get("lean_pnl") or 0 for card in cards),
    }


def keep_best(item: dict, field: str, value) -> None:
    if value is None:
        return
    if item[field] is None or value > item[field]:
        item[field] = value


def summarize(
    kalshi_rows: list[dict],
    kalshi_events: list[dict],
    kalshi_meta: dict,
    kalshi_audit_summary: dict,
    kalshi_context_backtest_summary: dict,
    tracking_cards: list[dict],
    tracking_positions: list[dict],
) -> dict:
    summary = {
        "kalshi_event_count": len(kalshi_events),
        "kalshi_market_count": len(kalshi_rows),
        "kalshi_priced_count": sum(row.get("yes_ask") is not None for row in kalshi_rows),
        "kalshi_watch_count": sum(bool(row.get("watch")) for row in kalshi_rows),
        "kalshi_fight_model_count": sum(
            row.get("probability_source") == "fight_context_model" for row in kalshi_rows
        ),
        "kalshi_history_fallback_count": sum(
            row.get("status") == "ok" and row.get("probability_source") != "fight_context_model"
            for row in kalshi_rows
        ),
        "kalshi_low_confidence_count": sum(
            row.get("status") == "ok" and not bool(row.get("confidence_ok")) for row in kalshi_rows
        ),
        "kalshi_model_error_count": sum(row.get("status") == "error" for row in kalshi_rows),
        "kalshi_snapshot_timestamp": kalshi_meta.get("snapshot_timestamp", ""),
        "kalshi_poll_seconds": number(kalshi_meta.get("poll_seconds")) or 0,
        "kalshi_authenticated": bool(kalshi_meta.get("authenticated")),
        "kalshi_fight_model_required": bool(kalshi_meta.get("fight_model_required")),
        "kalshi_audit_status": kalshi_audit_summary.get("status", ""),
        "kalshi_backtest_status": kalshi_context_backtest_summary.get("status", ""),
        "kalshi_backtest_measured_groups": as_int(kalshi_context_backtest_summary.get("measured_groups")),
        "kalshi_backtest_groups_beating_base": as_int(
            kalshi_context_backtest_summary.get("groups_beating_base_log_loss")
        ),
        "kalshi_backtest_prediction_rows": as_int(
            kalshi_context_backtest_summary.get("prediction_rows")
        ),
    }
    summary.update(summarize_tracking(tracking_cards, tracking_positions))
    return summary


def build_payload() -> dict:
    kalshi_meta = read_json(KALSHI_META)
    kalshi_audit_summary = read_json(KALSHI_AUDIT_SUMMARY)
    kalshi_context_backtest_summary = read_json(KALSHI_CONTEXT_BACKTEST_SUMMARY)
    kalshi_rows = build_kalshi_rows(read_csv(KALSHI_LIVE))
    kalshi_events = build_kalshi_event_rows(kalshi_rows)
    tracking_cards = build_tracking_cards()
    tracking_positions = build_tracking_positions()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {
            "kalshi_live": str(KALSHI_LIVE.relative_to(ROOT)),
            "kalshi_meta": str(KALSHI_META.relative_to(ROOT)),
            "kalshi_audit_summary": str(KALSHI_AUDIT_SUMMARY.relative_to(ROOT)),
            "kalshi_context_backtest_summary": str(KALSHI_CONTEXT_BACKTEST_SUMMARY.relative_to(ROOT)),
            "tracking_root": str(TRACKING_ROOT.relative_to(ROOT)),
        },
        "summary": summarize(
            kalshi_rows,
            kalshi_events,
            kalshi_meta,
            kalshi_audit_summary,
            kalshi_context_backtest_summary,
            tracking_cards,
            tracking_positions,
        ),
        "kalshi": kalshi_rows,
        "kalshi_events": kalshi_events,
        "kalshi_meta": kalshi_meta,
        "kalshi_audit_summary": kalshi_audit_summary,
        "kalshi_context_backtest_summary": kalshi_context_backtest_summary,
        "tracking_cards": tracking_cards,
        "tracking_positions": tracking_positions,
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
        f"{summary['kalshi_event_count']} live Kalshi fights, "
        f"{summary['kalshi_priced_count']} live phrases, "
        f"{summary['kalshi_fight_model_count']} fight-level rows, "
        f"{summary['kalshi_watch_count']} watch rows"
    )


if __name__ == "__main__":
    main()
