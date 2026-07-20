#!/usr/bin/env python3
"""Build the local dashboard feed for live Kalshi UFC mention prices."""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .kalshi_mentions import event_date_from_ticker, fighters_from_market_title
except ImportError:  # pragma: no cover - direct script execution
    from ufc_mentions.kalshi_mentions import event_date_from_ticker, fighters_from_market_title

OUT_DEFAULT = ROOT / "dashboard" / "data.js"

KALSHI_LIVE = ROOT / "market_data" / "kalshi_live_edges.csv"
KALSHI_META = ROOT / "market_data" / "kalshi_live_meta.json"
KALSHI_AUDIT_SUMMARY = ROOT / "model_outputs" / "kalshi_grouped_rule_audit_summary.json"
KALSHI_CONTEXT_BACKTEST_SUMMARY = ROOT / "model_outputs" / "kalshi_context_model_backtest_summary.json"
KALSHI_CONTEXT_BACKTEST_GROUPS = ROOT / "model_outputs" / "kalshi_context_model_backtest.csv"
PL_BACKTEST_SUMMARY = ROOT / "model_outputs" / "pl_backtest_summary.json"
PL_BACKTEST_TRADES = ROOT / "model_outputs" / "pl_backtest_trades.csv"
WALKFORWARD_REPORT = ROOT / "model_outputs" / "walkforward_report.json"
V2_GATE_REPORT = ROOT / "model_outputs" / "v2_gate_report.json"
FIGHTER_DIRECTORY = ROOT / "data" / "processed" / "fighter_directory.csv"
FIGHTER_ASSETS = ROOT / "dashboard" / "assets" / "fighters"
UPCOMING_EVENTS = ROOT / "data" / "processed" / "upcoming_events.json"
TRACKING_ROOT = ROOT / "data" / "tracking"
TRACKING_WEEKLY_SUMMARY = TRACKING_ROOT / "weekly_summary.csv"
TRACKING_HIDDEN_MARKERS = {".dashboard_hidden", ".practice_card"}


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


def hidden_tracking_card(path: Path) -> bool:
    return any((path / marker).exists() for marker in TRACKING_HIDDEN_MARKERS)


def hidden_tracking_card_name(card: str) -> bool:
    return bool(card) and hidden_tracking_card(TRACKING_ROOT / card)


def hidden_event_tickers() -> set[str]:
    if not TRACKING_ROOT.exists():
        return set()
    tickers: set[str] = set()
    for card_dir in sorted(path for path in TRACKING_ROOT.iterdir() if path.is_dir() and hidden_tracking_card(path)):
        for filename in ("paper_positions.csv", "predictions.csv", "outcomes.csv"):
            for row in read_csv(card_dir / filename):
                event_ticker = str(row.get("event_ticker", "")).strip()
                if event_ticker:
                    tickers.add(event_ticker)
    return tickers


def build_fighter_identities() -> dict[str, dict]:
    rows = read_csv(FIGHTER_DIRECTORY)
    if not rows:
        return {}
    manifest_file = FIGHTER_ASSETS / "manifest.json"
    manifest = read_json(manifest_file) if manifest_file.exists() else {}

    fighters: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("name_lower", "")).strip()
        if not key:
            continue
        wins = as_int(row.get("record_wins"))
        losses = as_int(row.get("record_losses"))
        photo_entry = manifest.get(key) or {}
        photo = None
        if photo_entry.get("status") == "ok" and photo_entry.get("file"):
            if (FIGHTER_ASSETS / photo_entry["file"]).exists():
                photo = f"assets/fighters/{photo_entry['file']}"
        fighters[key] = {
            "name": row.get("name", ""),
            "nickname": row.get("nickname", ""),
            "photo": photo,
            "record": f"{wins}-{losses}" if wins is not None and losses is not None else "",
            "stance": row.get("stance", ""),
            "height_cms": number(row.get("height_cms")),
            "reach_cms": number(row.get("reach_cms")),
            "n_fights": as_int(row.get("n_fights")) or 0,
            "last_event_date": row.get("last_event_date", ""),
            "style_tags": [tag for tag in str(row.get("style_tags", "")).split("|") if tag],
            "marquee_score": as_int(row.get("marquee_score")) or 0,
            "rates": {
                "submission": number(row.get("rate_submission")),
                "knockout_family": number(row.get("rate_knockout_family")),
                "decision_family": number(row.get("rate_decision_family")),
                "choke": number(row.get("rate_choke")),
            },
        }
    return fighters


def build_upcoming_events(today: str | None = None) -> list[dict]:
    payload = read_json(UPCOMING_EVENTS)
    events = payload.get("events") or []
    if today is None:
        today = datetime.now(timezone.utc).date().isoformat()
    out = []
    for event in events:
        event_date = str(event.get("date", ""))
        if not event_date or event_date < today:
            continue
        name = str(event.get("name", ""))
        matchup = re.search(r":\s*(.+?)\s+vs\.?\s+(.+)$", name)
        out.append({
            "name": name,
            "date": event_date,
            "venue": str(event.get("venue", "")),
            "location": str(event.get("location", "")),
            "fighter_1": matchup.group(1).strip() if matchup else "",
            "fighter_2": matchup.group(2).strip() if matchup else "",
        })
    return sorted(out, key=lambda e: e["date"])


def fight_marquee_score(fighter_1: str, fighter_2: str, fighters: dict[str, dict]) -> int:
    total = 0
    for name in (fighter_1, fighter_2):
        ident = fighters.get(str(name or "").strip().lower())
        if ident:
            total += ident.get("marquee_score") or 0
    return total


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
            "market_status",
            "market_result",
            "market_expiration_value",
            "market_close_time",
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
            "trust_note",
            "block_reason",
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
            "edge_cap",
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
        item["gap_blocked"] = as_bool(row.get("gap_blocked"))
        item["trust_ok"] = str(row.get("trust_ok", "")).strip() == "" or as_bool(row.get("trust_ok"))
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
    for card_dir in sorted(path for path in TRACKING_ROOT.iterdir() if path.is_dir() and not hidden_tracking_card(path)):
        card = card_dir.name
        predictions = read_csv(card_dir / "predictions.csv")
        positions = read_csv(card_dir / "paper_positions.csv")
        outcomes = read_csv(card_dir / "outcomes.csv")
        summary = read_json(card_dir / "summary.json")
        weekly = summary_by_card.get(card, {})
        official_rows = [row for row in positions if row.get("paper_action") == "trade"]
        lean_rows = [row for row in positions if row.get("paper_action") == "lean"]
        outcomes_filled = sum(str(row.get("outcome", "")).strip().lower() in {"yes", "no"} for row in outcomes)
        pending = sum(str(row.get("resolution_status", "")).strip().lower() == "pending" for row in outcomes)

        cards.append({
            "card": card,
            "label": card.replace("_", " ").title(),
            "prediction_rows": as_int(weekly.get("prediction_rows")) or len(predictions),
            "outcomes_filled": as_int(weekly.get("outcomes_filled")) or outcomes_filled,
            "pending": pending,
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
    for card_dir in sorted(path for path in TRACKING_ROOT.iterdir() if path.is_dir() and not hidden_tracking_card(path)):
        outcomes_by_ticker = {
            row.get("ticker", ""): row
            for row in read_csv(card_dir / "outcomes.csv")
        }
        for row in read_csv(card_dir / "paper_positions.csv"):
            item = trim(row, [
                "card",
                "tracked_at",
                "entered_at",
                "entry_source",
                "paper_action",
                "paper_reason",
                "event_title",
                "event_ticker",
                "fighter_1",
                "fighter_2",
                "ticker",
                "phrase",
                "watch",
                "confidence_note",
            ])
            if not item.get("event_ticker"):
                item["event_ticker"] = "-".join(str(row.get("ticker", "")).split("-")[:2])
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
            item["resolution_status"] = str(outcome_row.get("resolution_status", "")).strip().lower()
            item["checked_at"] = outcome_row.get("checked_at", "")
            item["resolved_at"] = outcome_row.get("resolved_at", "")
            item["market_status"] = outcome_row.get("market_status", "")
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
        "tracking_pending_count": sum(card.get("pending") or 0 for card in cards),
        "tracking_official_pnl": sum(card.get("official_pnl") or 0 for card in cards),
        "tracking_lean_pnl": sum(card.get("lean_pnl") or 0 for card in cards),
    }


def build_backtest_groups(rows: list[dict]) -> list[dict]:
    """One row per phrase group from the fight-level prediction backtest.

    Shows a single model number per group; internal diagnostics such as the
    "safe" clipped probability stay out of the dashboard feed on purpose.
    """
    groups = []
    for row in rows:
        phrase = str(row.get("phrase", "")).strip()
        if not phrase:
            continue
        groups.append({
            "phrase": phrase,
            "scored_fights": as_int(row.get("scored_fights")),
            "positives": as_int(row.get("positives")),
            "actual_rate": number(row.get("actual_rate")),
            "log_loss_improvement": number(row.get("log_loss_improvement")),
            "auc": number(row.get("auc")),
            "beats_base": str(row.get("status", "")).strip() == "beats_base",
        })
    groups.sort(key=lambda item: item.get("log_loss_improvement") or -999, reverse=True)
    return groups


def build_performance(trade_rows: list[dict]) -> dict:
    official = [row for row in trade_rows if str(row.get("cohort", "")).strip() == "official"]
    if not official:
        return {"equity": [], "by_phrase": [], "official_trades": 0}

    by_date: dict[str, float] = {}
    by_phrase: dict[str, dict] = {}
    for row in official:
        pnl = number(row.get("pnl")) or 0.0
        date = str(row.get("event_date", "")).strip() or "unknown"
        by_date[date] = by_date.get(date, 0.0) + pnl
        phrase = str(row.get("phrase", "")).strip() or "unknown"
        entry = by_phrase.setdefault(phrase, {"phrase": phrase, "trades": 0, "wins": 0, "pnl": 0.0})
        entry["trades"] += 1
        entry["wins"] += str(row.get("won", "")).strip().lower() == "true"
        entry["pnl"] += pnl

    equity = []
    cumulative = 0.0
    for date in sorted(by_date):
        cumulative += by_date[date]
        equity.append({
            "date": date,
            "card_pnl": round(by_date[date], 4),
            "cumulative_pnl": round(cumulative, 4),
        })
    phrases = sorted(by_phrase.values(), key=lambda item: -item["pnl"])
    for entry in phrases:
        entry["pnl"] = round(entry["pnl"], 4)
    return {"equity": equity, "by_phrase": phrases, "official_trades": len(official)}


def build_walkforward(report: dict) -> dict:
    if not report:
        return {"available": False}
    return {
        "available": True,
        "labels_count": as_int(report.get("labels_count")),
        "cards": report.get("cards") or [],
        "chosen_weight": number(report.get("chosen_weight")),
        "baseline_log_loss": number(report.get("baseline_log_loss")),
        "chosen_log_loss": number(report.get("chosen_log_loss")),
        "generated_at": report.get("generated_at", ""),
    }


def build_v2_gate(report: dict) -> dict:
    if not report:
        return {"available": False}
    return {
        "available": True,
        "chosen_variant": report.get("chosen_variant", "v1"),
        "variant_means": {
            name: number(value)
            for name, value in (report.get("variant_means") or {}).items()
        },
        "calibrated": bool(report.get("calibration")),
        "generated_at": report.get("generated_at", ""),
    }


def build_model_health(
    context_summary: dict,
    groups: list[dict],
    pl_summary: dict,
    walkforward: dict | None = None,
) -> dict:
    weakest = None
    measured = [g for g in groups if g.get("log_loss_improvement") is not None]
    if measured:
        weakest = min(measured, key=lambda item: item["log_loss_improvement"])

    official = pl_summary.get("official") or {}
    lean = pl_summary.get("lean") or {}
    measured_sorted = sorted(
        (g for g in groups if g.get("log_loss_improvement") is not None),
        key=lambda item: item["log_loss_improvement"],
        reverse=True,
    )
    rule_comparison = pl_summary.get("rule_comparison") or {}
    current_rule = rule_comparison.get("current_rule_official") or {}
    return {
        "prediction": {
            "status": context_summary.get("status", ""),
            "claim": context_summary.get("claim", ""),
            "prediction_rows": as_int(context_summary.get("prediction_rows")),
            "groups": as_int(context_summary.get("groups")),
            "measured_groups": as_int(context_summary.get("measured_groups")),
            "groups_beating_base": as_int(context_summary.get("groups_beating_base_log_loss")),
            "folds": as_int(context_summary.get("folds")),
            "weakest_phrase": (weakest or {}).get("phrase", ""),
            "weakest_improvement": (weakest or {}).get("log_loss_improvement"),
            "strongest": [g["phrase"] for g in measured_sorted[:3]],
            "weakest": [g["phrase"] for g in measured_sorted[-3:]][::-1],
            "trusted_groups": sum(1 for g in groups if g.get("beats_base")),
            "generated_at": context_summary.get("generated_at", ""),
        },
        "groups": groups,
        "pl": {
            "available": bool(pl_summary),
            "is_money_backtest": bool(pl_summary.get("is_money_backtest")),
            "latest_settled_event_date": pl_summary.get("latest_settled_event_date", ""),
            "entry_rule": pl_summary.get("entry_rule", ""),
            "markets_with_results": as_int(pl_summary.get("markets_with_results")),
            "resolved_event_count": as_int(pl_summary.get("resolved_event_count")),
            "official_trades": as_int(official.get("trades")),
            "official_wins": as_int(official.get("wins")),
            "official_staked": number(official.get("total_staked")),
            "official_pnl": number(official.get("total_pnl")),
            "official_return": number(official.get("return_on_stake")),
            "lean_trades": as_int(lean.get("trades")),
            "lean_wins": as_int(lean.get("wins")),
            "lean_staked": number(lean.get("total_staked")),
            "lean_pnl": number(lean.get("total_pnl")),
            "lean_return": number(lean.get("return_on_stake")),
            "minimum_trades_for_claim": as_int(pl_summary.get("minimum_trades_for_claim")),
            "claim_status": pl_summary.get("claim_status", ""),
            "note": pl_summary.get("note", ""),
            "current_rule_trades": as_int(current_rule.get("trades")),
            "current_rule_wins": as_int(current_rule.get("wins")),
            "current_rule_pnl": number(current_rule.get("total_pnl")),
            "rule_note": rule_comparison.get("note", ""),
            "generated_at": pl_summary.get("generated_at", ""),
        },
        "walkforward": walkforward or {"available": False},
        "v2_gate": build_v2_gate(read_json(V2_GATE_REPORT)),
    }


def keep_best(item: dict, field: str, value) -> None:
    if value is None:
        return
    if item[field] is None or value > item[field]:
        item[field] = value


def parse_event_fighters(title: str) -> tuple[str, str]:
    try:
        return fighters_from_market_title(title)
    except Exception:
        match = re.search(r"^(.+?)\s+vs\.?\s+(.+?)\s+(?:UFC\s+)?Fight\b", title or "", re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "", ""


def event_display_title(event: dict) -> str:
    return (
        event.get("sub_title")
        or event.get("event_title")
        or event.get("title")
        or event.get("event_ticker")
        or ""
    )


def event_catalog(events: list[dict], rows: list[dict], hidden_events: set[str]) -> dict[str, dict]:
    catalog: dict[str, dict] = {}

    for event in events:
        event_ticker = str(event.get("event_ticker", "")).strip()
        if not event_ticker or event_ticker in hidden_events:
            continue
        title = event_display_title(event)
        fighter_1 = str(event.get("fighter_1") or "").strip()
        fighter_2 = str(event.get("fighter_2") or "").strip()
        if not fighter_1 or not fighter_2:
            fighter_1, fighter_2 = parse_event_fighters(title)
        catalog[event_ticker] = {
            "event_ticker": event_ticker,
            "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
            "event_date": event.get("event_date") or event_date_from_ticker(event_ticker) or "",
            "event_title": title,
            "fighter_1": fighter_1,
            "fighter_2": fighter_2,
            "available_on_brokers": as_bool(event.get("available_on_brokers")),
            "last_updated_ts": event.get("last_updated_ts", ""),
            "market_count": 0,
            "priced_count": 0,
            "meta_market_count": as_int(event.get("market_rows")) or 0,
            "meta_priced_count": as_int(event.get("priced_rows")) or 0,
            "meta_watch_count": as_int(event.get("watch_rows")) or 0,
            "model_ready_count": 0,
            "error_count": 1 if event.get("error") else 0,
            "watch_count": 0,
            "best_edge": None,
        }

    for row in rows:
        event_ticker = str(row.get("event_ticker", "")).strip()
        if not event_ticker or event_ticker in hidden_events:
            continue
        item = catalog.setdefault(event_ticker, {
            "event_ticker": event_ticker,
            "series_ticker": row.get("series_ticker", "KXFIGHTMENTION"),
            "event_date": row.get("event_date") or event_date_from_ticker(event_ticker) or "",
            "event_title": row.get("event_title", ""),
            "fighter_1": row.get("fighter_1", ""),
            "fighter_2": row.get("fighter_2", ""),
            "available_on_brokers": False,
            "last_updated_ts": "",
            "market_count": 0,
            "priced_count": 0,
            "meta_market_count": 0,
            "meta_priced_count": 0,
            "meta_watch_count": 0,
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
    for item in catalog.values():
        if not item.get("market_count"):
            item["market_count"] = item.get("meta_market_count") or 0
            item["priced_count"] = item.get("meta_priced_count") or 0
            item["watch_count"] = item.get("meta_watch_count") or 0
    return catalog


def card_id_for_event(event: dict) -> str:
    event_date = event.get("event_date") or "date-tbd"
    series = event.get("series_ticker") or "KXFIGHTMENTION"
    return f"{series}:{event_date}"


def build_kalshi_cards(kalshi_meta: dict, rows: list[dict], hidden_events: set[str]) -> list[dict]:
    events = event_catalog(kalshi_meta.get("events") or [], rows, hidden_events)
    cards: dict[str, dict] = {}
    for event in events.values():
        card_id = card_id_for_event(event)
        event_date = event.get("event_date", "")
        event_title = event.get("event_title", "")
        has_fighters = bool(event.get("fighter_1") and event.get("fighter_2"))
        market_count = event.get("market_count") or 0
        has_card_title = bool(event_title and not has_fighters and not market_count)
        card = cards.setdefault(card_id, {
            "card_id": card_id,
            "card_title": event_title if has_card_title else f"UFC card · {event_date}" if event_date else "UFC card · date TBD",
            "event_date": event_date,
            "source_note": "Kalshi event title; fights not listed yet." if has_card_title else "Grouped by Kalshi fight-event date. No card name is guessed.",
            "has_kalshi_card_title": has_card_title,
            "fight_count": 0,
            "tradable_fight_count": 0,
            "phrase_count": 0,
            "priced_count": 0,
            "model_ready_count": 0,
            "watch_count": 0,
            "best_edge": None,
            "fights": [],
        })
        if has_card_title and not card.get("has_kalshi_card_title"):
            card["card_title"] = event_title
            card["source_note"] = "Kalshi event title; fights not listed yet."
            card["has_kalshi_card_title"] = True
        matchup = (
            f"{event.get('fighter_1')} vs {event.get('fighter_2')}"
            if has_fighters
            else "TBD fights" if not market_count else event_title or "TBD fight"
        )
        fight = {
            "event_ticker": event.get("event_ticker", ""),
            "event_title": event.get("event_title", ""),
            "event_date": event_date,
            "fighter_1": event.get("fighter_1", ""),
            "fighter_2": event.get("fighter_2", ""),
            "matchup": matchup,
            "market_count": market_count,
            "priced_count": event.get("priced_count") or 0,
            "model_ready_count": event.get("model_ready_count") or 0,
            "watch_count": event.get("watch_count") or 0,
            "best_edge": event.get("best_edge"),
            "odds_status": "live" if market_count else "tbd",
            "tradable": bool(market_count),
            "available_on_brokers": bool(event.get("available_on_brokers")),
            "last_updated_ts": event.get("last_updated_ts", ""),
        }
        card["fights"].append(fight)
        card["fight_count"] += 1
        if market_count:
            card["tradable_fight_count"] += 1
        card["phrase_count"] += market_count
        card["priced_count"] += event.get("priced_count") or 0
        card["model_ready_count"] += event.get("model_ready_count") or 0
        card["watch_count"] += event.get("watch_count") or 0
        keep_best(card, "best_edge", event.get("best_edge"))

    for card in cards.values():
        card["fights"].sort(key=lambda item: (
            not item.get("tradable"),
            item.get("matchup", ""),
            item.get("event_ticker", ""),
        ))
    return sorted(cards.values(), key=lambda item: (item.get("event_date", ""), item.get("card_id", "")))


def flatten_card_fights(cards: list[dict]) -> list[dict]:
    rows = []
    for card in cards:
        for fight in card.get("fights", []):
            item = dict(fight)
            item["card_id"] = card.get("card_id", "")
            item["card_title"] = card.get("card_title", "")
            rows.append(item)
    return rows


def summarize(
    kalshi_rows: list[dict],
    kalshi_events: list[dict],
    kalshi_cards: list[dict],
    kalshi_meta: dict,
    kalshi_audit_summary: dict,
    kalshi_context_backtest_summary: dict,
    tracking_cards: list[dict],
    tracking_positions: list[dict],
) -> dict:
    paper_tracking = kalshi_meta.get("paper_tracking") or {}
    if hidden_tracking_card_name(str(paper_tracking.get("card", ""))):
        paper_tracking = {}
    summary = {
        "kalshi_card_count": len(kalshi_cards),
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
        "kalshi_gap_blocked_count": sum(bool(row.get("gap_blocked")) for row in kalshi_rows),
        "kalshi_low_trust_count": sum(
            row.get("status") == "ok" and not bool(row.get("trust_ok", True)) for row in kalshi_rows
        ),
        "kalshi_data_risk_count": sum(
            row.get("status") == "ok" and bool(row.get("data_risk")) for row in kalshi_rows
        ),
        "kalshi_model_error_count": sum(row.get("status") == "error" for row in kalshi_rows),
        "kalshi_snapshot_timestamp": kalshi_meta.get("snapshot_timestamp", ""),
        "kalshi_poll_seconds": number(kalshi_meta.get("poll_seconds")) or 0,
        "kalshi_authenticated": bool(kalshi_meta.get("authenticated")),
        "kalshi_fight_model_required": bool(kalshi_meta.get("fight_model_required")),
        "paper_tracking_card": paper_tracking.get("card", ""),
        "paper_tracking_path": paper_tracking.get("path", ""),
        "paper_tracking_new_entries": as_int(paper_tracking.get("new_entries")),
        "paper_tracking_total_entries": as_int(paper_tracking.get("total_entries")),
        "paper_tracking_resolved": as_int(paper_tracking.get("resolved")),
        "paper_tracking_pending": as_int(paper_tracking.get("pending")),
        "paper_tracking_open": as_int(paper_tracking.get("open")),
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
    backtest_groups = build_backtest_groups(read_csv(KALSHI_CONTEXT_BACKTEST_GROUPS))
    model_health = build_model_health(
        kalshi_context_backtest_summary,
        backtest_groups,
        read_json(PL_BACKTEST_SUMMARY),
        build_walkforward(read_json(WALKFORWARD_REPORT)),
    )
    hidden_events = hidden_event_tickers()
    kalshi_source_rows = [
        row for row in read_csv(KALSHI_LIVE)
        if str(row.get("event_ticker", "")).strip() not in hidden_events
    ]
    kalshi_rows = build_kalshi_rows(kalshi_source_rows)
    kalshi_cards = build_kalshi_cards(kalshi_meta, kalshi_rows, hidden_events)
    fighters = build_fighter_identities()
    for card in kalshi_cards:
        for fight in card.get("fights", []):
            fight["marquee_score"] = fight_marquee_score(
                fight.get("fighter_1", ""), fight.get("fighter_2", ""), fighters
            )
    kalshi_events = flatten_card_fights(kalshi_cards) or build_kalshi_event_rows(kalshi_rows)
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
            kalshi_cards,
            kalshi_meta,
            kalshi_audit_summary,
            kalshi_context_backtest_summary,
            tracking_cards,
            tracking_positions,
        ),
        "kalshi": kalshi_rows,
        "fighters": fighters,
        "upcoming_events": build_upcoming_events(),
        "performance": build_performance(read_csv(PL_BACKTEST_TRADES)),
        "kalshi_cards": kalshi_cards,
        "kalshi_events": kalshi_events,
        "kalshi_meta": kalshi_meta,
        "kalshi_audit_summary": kalshi_audit_summary,
        "kalshi_context_backtest_summary": kalshi_context_backtest_summary,
        "model_health": model_health,
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
