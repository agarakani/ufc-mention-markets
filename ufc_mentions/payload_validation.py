"""Reject incomplete identities or conflicting paper records before publication."""

from __future__ import annotations

import json
import math
from pathlib import Path

DATA_PREFIX = "window.UFC_MENTION_DASHBOARD_DATA = "


def load_payload(path: Path) -> dict:
    """Read the JSON assignment without executing the dashboard's JavaScript."""
    return parse_payload(path.read_text(encoding="utf-8"))


def parse_payload(text: str) -> dict:
    """Validate the same data snapshot that a publisher will write."""
    text = text.strip()
    if not text.startswith(DATA_PREFIX):
        raise ValueError("expected the dashboard data assignment")
    payload = json.loads(text[len(DATA_PREFIX):].removesuffix(";").strip())
    validate_payload(payload)
    return payload


def _amount(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: expected a finite dollar amount")
    return float(value)


def validate_payload(payload: dict) -> None:
    """Check recorded-night identities and ledger totals; never repair the feed."""
    if not isinstance(payload, dict):
        raise ValueError("dashboard payload must be an object")
    fighters = payload.get("fighters")
    tapes = payload.get("tapes")
    trades = payload.get("trades")
    performance = payload.get("performance")
    if not isinstance(fighters, dict) or not isinstance(tapes, list):
        raise ValueError("dashboard payload needs fighters and tapes")
    if not isinstance(trades, list) or not isinstance(performance, dict):
        raise ValueError("dashboard payload needs trades and performance")

    def check_fighters(row: dict, location: str) -> None:
        ticker = row.get("ticker") or location
        for field in ("fighter_1", "fighter_2"):
            name = row.get(field)
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"{ticker}: missing {field}")
            identity = fighters.get(name.strip().lower())
            if not isinstance(identity, dict) or not identity.get("name"):
                raise ValueError(f"{ticker}: {name} is missing from fighters")

    for tape in tapes:
        for market in tape.get("markets") or []:
            check_fighters(market, str(tape.get("card", "tape")))

    by_date: dict[str, list[float]] = {}
    for trade in trades:
        check_fighters(trade, "trade")
        date = trade.get("event_date")
        if not isinstance(date, str) or not date.strip():
            raise ValueError(f"{trade.get('ticker')}: missing event_date")
        pnl = trade.get("pnl")
        # Pending entries have no realized P/L, as in build_performance.
        by_date.setdefault(date, []).append(
            0.0 if pnl is None else _amount(pnl, f"{trade.get('ticker')} pnl")
        )
    if performance.get("official_trades") != len(trades):
        raise ValueError("performance.official_trades does not match the ledger")
    equity = performance.get("equity")
    if not isinstance(equity, list) or [row.get("date") for row in equity] != sorted(by_date):
        raise ValueError("performance.equity dates do not match the ledger in date order")
    cumulative = 0.0
    for row in equity:
        date = row["date"]
        card_pnl = math.fsum(by_date[date])
        cumulative += card_pnl
        for field, expected in (("card_pnl", card_pnl), ("cumulative_pnl", cumulative)):
            actual = _amount(row.get(field), f"{date} {field}")
            # The builder publishes four decimal places. A larger mismatch is an error.
            if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=0.00005):
                raise ValueError(f"{date} {field}: equity {actual} does not match ledger {expected:.4f}")
