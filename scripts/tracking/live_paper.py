#!/usr/bin/env python3
"""Record paper entries when the live board crosses the watch bar."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tracking.snapshot_card import OUTCOME_FIELDS, outcome_template, slug, write_csv
from scripts.tracking.settle_card import settle_card
from ufc_mentions.kalshi_client import KalshiClient, MARKETS_PATH


LIVE_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
OUT_ROOT_DEFAULT = ROOT / "data" / "tracking"

TRACKING_FIELDS = [
    "card",
    "tracked_at",
    "entered_at",
    "entry_source",
    "paper_action",
    "paper_reason",
    "paper_side",
    "paper_contracts",
    "paper_price",
]

OUTCOME_AUTO_FIELDS = OUTCOME_FIELDS


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def number(value) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def moneyish(value: float) -> str:
    return f"{value:.8f}".rstrip("0").rstrip(".")


def is_yes(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def normalize_outcome(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes", "y", "true", "hit", "win"}:
        return "yes"
    if text in {"no", "n", "false", "miss", "loss"}:
        return "no"
    if text in {"1", "1.0", "100", "100.0"}:
        return "yes"
    if text in {"0", "0.0"}:
        return "no"
    return ""


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def field_order(existing_rows: list[dict], new_rows: list[dict]) -> list[str]:
    fields: list[str] = []
    for field in TRACKING_FIELDS:
        if field not in fields:
            fields.append(field)
    for row in existing_rows + new_rows:
        for field in row.keys():
            if field not in fields:
                fields.append(field)
    return fields


def existing_trade_tickers(rows: list[dict]) -> set[str]:
    return {
        row.get("ticker", "")
        for row in rows
        if row.get("ticker") and str(row.get("paper_action", "")).strip().lower() == "trade"
    }


def build_entry(row: dict, *, card: str, entered_at: str, contracts: float) -> dict | None:
    side = str(row.get("side", "")).strip().lower()
    if side not in {"yes", "no"}:
        return None

    price = number(row.get("side_price"))
    if price is None:
        price = number(row.get("yes_ask") if side == "yes" else row.get("no_ask"))
    if price is None:
        return None

    reason = f"live watch {side}"
    if is_yes(row.get("data_risk")):
        reason = f"live data-risk watch {side}"

    entry = dict(row)
    entry.update({
        "card": card,
        "tracked_at": entered_at,
        "entered_at": entered_at,
        "entry_source": "live_watch",
        "paper_action": "trade",
        "paper_reason": reason,
        "paper_side": side,
        "paper_contracts": moneyish(contracts),
        "paper_price": moneyish(price),
        "entry_snapshot_timestamp": row.get("snapshot_timestamp", ""),
        "entry_model_probability": row.get("model_probability", ""),
        "entry_yes_price": row.get("yes_ask", ""),
        "entry_no_price": row.get("no_ask", ""),
        "entry_edge": row.get("edge", ""),
        "entry_hurdle": row.get("hurdle", ""),
    })
    return entry


def market_field(row: dict, market: dict | None, field: str) -> str:
    if market is not None:
        value = market.get(field)
        if value not in ("", None):
            return str(value)
    value = row.get(field)
    return "" if value in ("", None) else str(value)


def event_date_has_passed(value: str, checked_at: str) -> bool:
    if not value:
        return False
    try:
        event_day = date.fromisoformat(str(value)[:10])
    except ValueError:
        return False
    try:
        checked_day = datetime.fromisoformat(checked_at.replace("Z", "+00:00")).date()
    except ValueError:
        checked_day = datetime.now(timezone.utc).date()
    return event_day < checked_day


def resolution_from_market(row: dict, market: dict | None, checked_at: str) -> dict:
    result = market_field(row, market, "result") or market_field(row, market, "market_result")
    expiration_value = (
        market_field(row, market, "expiration_value")
        or market_field(row, market, "market_expiration_value")
    )
    outcome = normalize_outcome(result) or normalize_outcome(expiration_value)
    market_status = market_field(row, market, "status") or market_field(row, market, "market_status")

    if outcome:
        return {
            "outcome": outcome,
            "resolution_status": "resolved",
            "resolved_at": checked_at,
            "market_status": market_status,
            "market_result": result,
            "market_expiration_value": expiration_value,
            "notes": "auto-filled from Kalshi result",
        }

    status_text = market_status.strip().lower()
    closed_statuses = {"closed", "settled", "resolved", "finalized", "expired"}
    resolution_status = "pending" if status_text in closed_statuses else "open"
    if resolution_status == "open" and event_date_has_passed(row.get("event_date", ""), checked_at):
        resolution_status = "pending"

    notes = "waiting for Kalshi result" if resolution_status == "pending" else "market still open"
    return {
        "outcome": "",
        "resolution_status": resolution_status,
        "resolved_at": "",
        "market_status": market_status,
        "market_result": result,
        "market_expiration_value": expiration_value,
        "notes": notes,
    }


def fetch_tracked_markets(client, positions: list[dict]) -> dict[str, dict]:
    if client is None:
        return {}
    by_ticker: dict[str, dict] = {}
    event_tickers = sorted({row.get("event_ticker", "") for row in positions if row.get("event_ticker")})
    for event_ticker in event_tickers:
        try:
            for market in client.get_markets(event_ticker=event_ticker):
                ticker = market.get("ticker", "")
                if ticker:
                    by_ticker[ticker] = market
        except Exception:
            continue

    for row in positions:
        ticker = row.get("ticker", "")
        if not ticker or ticker in by_ticker:
            continue
        try:
            payload = client.get(f"{MARKETS_PATH}/{ticker}")
            market = payload.get("market") or {}
        except Exception:
            market = {}
        if market:
            by_ticker[ticker] = market
    return by_ticker


def update_outcomes(
    card_dir: Path,
    positions: list[dict],
    existing_outcomes: list[dict],
    live_rows: list[dict],
    *,
    checked_at: str,
    client=None,
) -> dict:
    live_by_ticker = {row.get("ticker", ""): row for row in live_rows if row.get("ticker")}
    markets_by_ticker = fetch_tracked_markets(client, positions)
    existing_by_ticker = {row.get("ticker", ""): row for row in existing_outcomes if row.get("ticker")}
    rows = []
    counts = {"resolved": 0, "pending": 0, "open": 0}

    for position in positions:
        ticker = position.get("ticker", "")
        existing = dict(existing_by_ticker.get(ticker, {}))
        source_row = live_by_ticker.get(ticker, position)
        market = markets_by_ticker.get(ticker)
        resolution = resolution_from_market(source_row, market, checked_at)
        previous_outcome = normalize_outcome(existing.get("outcome", ""))
        if previous_outcome and not resolution["outcome"]:
            resolution["outcome"] = previous_outcome
            resolution["resolution_status"] = existing.get("resolution_status") or "resolved"
            resolution["resolved_at"] = existing.get("resolved_at", "")
            resolution["notes"] = existing.get("notes", "")

        status = resolution.get("resolution_status") or "open"
        if status in counts:
            counts[status] += 1

        row = {
            "ticker": ticker,
            "event_ticker": position.get("event_ticker", ""),
            "event_title": position.get("event_title", ""),
            "fighter_1": position.get("fighter_1", ""),
            "fighter_2": position.get("fighter_2", ""),
            "phrase": position.get("phrase", ""),
            "outcome": resolution.get("outcome", ""),
            "resolution_status": status,
            "checked_at": checked_at,
            "resolved_at": resolution.get("resolved_at", ""),
            "market_status": resolution.get("market_status", ""),
            "market_result": resolution.get("market_result", ""),
            "market_expiration_value": resolution.get("market_expiration_value", ""),
            "notes": resolution.get("notes", ""),
        }
        rows.append(row)

    write_csv(card_dir / "outcomes.csv", rows, OUTCOME_AUTO_FIELDS)
    return counts


def update_readme(card_dir: Path, *, card: str, entries: int) -> None:
    (card_dir / "README.txt").write_text(
        "\n".join([
            f"card: {card}",
            "mode: live paper entries",
            f"official paper trades: {entries}",
            "",
            "This folder records the first time each market became a WATCH row.",
            "Each entry uses the buy price that was live at that moment.",
            "Outcomes are auto-filled from Kalshi when a market resolves.",
            "Before Kalshi posts a final result, finished-date rows show pending.",
            "",
            "You can still run this manually if needed:",
            "python3 scripts/tracking/settle_card.py --card " + card,
            "",
        ]),
        encoding="utf-8",
    )


def record_live_entries(
    rows: list[dict],
    *,
    card: str,
    out_root: Path = OUT_ROOT_DEFAULT,
    contracts: float = 1.0,
    entered_at: str | None = None,
    client=None,
) -> dict:
    card_slug = slug(card)
    card_dir = out_root / card_slug
    positions_path = card_dir / "paper_positions.csv"
    predictions_path = card_dir / "predictions.csv"
    outcomes_path = card_dir / "outcomes.csv"

    existing_positions = read_csv(positions_path)
    existing_predictions = read_csv(predictions_path)
    existing_outcomes = read_csv(outcomes_path)
    already_traded = existing_trade_tickers(existing_positions)

    stamp = entered_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_entries: list[dict] = []
    for row in rows:
        ticker = row.get("ticker", "")
        if not ticker or ticker in already_traded:
            continue
        if not is_yes(row.get("watch")):
            continue
        entry = build_entry(row, card=card_slug, entered_at=stamp, contracts=contracts)
        if entry is None:
            continue
        new_entries.append(entry)
        already_traded.add(ticker)

    card_dir.mkdir(parents=True, exist_ok=True)
    if new_entries:
        all_positions = existing_positions + new_entries
        all_predictions = existing_predictions + new_entries
        write_csv(positions_path, all_positions, field_order(existing_positions, new_entries))
        write_csv(predictions_path, all_predictions, field_order(existing_predictions, new_entries))

        known_outcomes = {row.get("ticker", "") for row in existing_outcomes}
        existing_outcomes = existing_outcomes + [
            row for row in outcome_template(new_entries)
            if row.get("ticker", "") not in known_outcomes
        ]
    else:
        if not positions_path.exists():
            write_csv(positions_path, existing_positions, TRACKING_FIELDS)
        if not predictions_path.exists():
            write_csv(predictions_path, existing_predictions, TRACKING_FIELDS)

    final_positions = read_csv(positions_path)
    outcome_counts = update_outcomes(
        card_dir,
        final_positions,
        existing_outcomes,
        rows,
        checked_at=stamp,
        client=client,
    )
    if final_positions:
        settle_card(card_slug, tracking_root=out_root, summary_path=out_root / "weekly_summary.csv")

    final_positions = read_csv(positions_path)
    total_entries = len(existing_trade_tickers(final_positions))
    update_readme(card_dir, card=card_slug, entries=total_entries)
    return {
        "card": card_slug,
        "path": display_path(card_dir),
        "new_entries": len(new_entries),
        "total_entries": total_entries,
        "resolved": outcome_counts.get("resolved", 0),
        "pending": outcome_counts.get("pending", 0),
        "open": outcome_counts.get("open", 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record paper entries from the latest live WATCH rows.")
    parser.add_argument("--card", required=True, help="card name, for example UFC Vegas 119 main card")
    parser.add_argument("--source", default=str(LIVE_DEFAULT), help="live model CSV to read")
    parser.add_argument("--out-root", default=str(OUT_ROOT_DEFAULT), help="where local tracking files are written")
    parser.add_argument("--contracts", type=float, default=1.0, help="paper contracts per entry")
    parser.add_argument("--no-auto-settle", action="store_true", help="skip checking Kalshi for resolved outcomes")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Missing {source}. Run scripts/live/refresh_dashboard.py first.")

    rows = read_csv(source)
    result = record_live_entries(
        rows,
        card=args.card,
        out_root=Path(args.out_root),
        contracts=args.contracts,
        client=None if args.no_auto_settle else KalshiClient(),
    )
    print(f"Paper card: {result['card']}")
    print(f"New entries: {result['new_entries']}")
    print(f"Total entries: {result['total_entries']}")
    print(f"Resolved: {result['resolved']}, pending: {result['pending']}, open: {result['open']}")
    print(f"Folder: {result['path']}")


if __name__ == "__main__":
    main()
