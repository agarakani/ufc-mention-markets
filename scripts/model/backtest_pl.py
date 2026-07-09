#!/usr/bin/env python3
"""Money backtest: replay recorded live snapshots against final Kalshi results.

What this does, in plain terms:
  1. Reads the price history the live refresher already saved
     (market_data/kalshi_price_history.csv). Every snapshot row holds the
     model number, the live YES/NO buy prices, and the watch decision the
     live rule made at that moment. Nothing is recomputed with hindsight.
  2. Fetches the final result (yes/no) for every market whose event day has
     passed, read-only from Kalshi. Results are cached locally so reruns
     do not refetch.
  3. Simulates what paper tracking would have done:
       official trade: 1 contract at the buy price, at the FIRST snapshot
                       where the row was a WATCH.
       lean:           1 contract at the first positive-edge snapshot, for
                       markets that never reached WATCH. Tracked separately,
                       for information only.
  4. Reports wins, P/L, and return on stake — and refuses to claim anything
     until there are at least MIN_TRADES_FOR_CLAIM settled official trades.

This cannot place orders. It only reads.

Usage:
  python3 scripts/model/backtest_pl.py
  python3 scripts/model/backtest_pl.py --offline   # cached results only
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.tracking.settle_card import contract_pnl  # noqa: E402
from ufc_mentions.kalshi_mentions import event_date_from_ticker  # noqa: E402

PRICE_HISTORY = ROOT / "market_data" / "kalshi_price_history.csv"
RESULTS_CACHE = ROOT / "market_data" / "kalshi_results_cache.csv"
OUT_SUMMARY = ROOT / "model_outputs" / "pl_backtest_summary.json"
OUT_TRADES = ROOT / "model_outputs" / "pl_backtest_trades.csv"

MIN_TRADES_FOR_CLAIM = 30

TRADE_FIELDS = [
    "cohort", "ticker", "event_ticker", "event_date", "phrase",
    "entered_at", "side", "price", "model_probability", "edge", "hurdle",
    "data_risk", "result", "won", "pnl",
]


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


def truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def load_results_cache() -> dict[str, str]:
    return {
        row["ticker"]: row["result"]
        for row in read_csv(RESULTS_CACHE)
        if row.get("ticker") and row.get("result") in ("yes", "no")
    }


def save_results_cache(results: dict[str, str]) -> None:
    RESULTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_CACHE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "result"])
        writer.writeheader()
        for ticker in sorted(results):
            writer.writerow({"ticker": ticker, "result": results[ticker]})


def past_event_tickers(history: list[dict], today: str) -> set[str]:
    """Event tickers whose event day (from the ticker) is before today."""
    out = set()
    for row in history:
        event_ticker = str(row.get("event_ticker", "")).strip()
        if not event_ticker:
            continue
        event_date = event_date_from_ticker(event_ticker) or ""
        if event_date and event_date < today:
            out.add(event_ticker)
    return out


def fetch_results(event_tickers: set[str], cached: dict[str, str]) -> dict[str, str]:
    """Read-only fetch of finalized results for events not fully cached."""
    from ufc_mentions.kalshi_client import KalshiClient

    client = KalshiClient()
    results = dict(cached)
    for event_ticker in sorted(event_tickers):
        try:
            markets = client.get_markets(event_ticker=event_ticker)
        except Exception as exc:  # network or API problem: keep going with cache
            print(f"  could not fetch {event_ticker}: {exc}")
            continue
        for market in markets:
            ticker = str(market.get("ticker", "")).strip()
            result = str(market.get("result", "")).strip().lower()
            if ticker and result in ("yes", "no"):
                results[ticker] = result
    return results


def first_entries(history: list[dict]) -> dict[str, dict]:
    """First WATCH snapshot per ticker (official) or first positive-edge one (lean).

    History is replayed in snapshot order, exactly as the live tracker would
    have seen it. A market that reaches WATCH at any point counts as official,
    entered at its first WATCH snapshot.
    """
    ordered = sorted(history, key=lambda row: str(row.get("snapshot_timestamp", "")))
    entries: dict[str, dict] = {}
    for row in ordered:
        ticker = str(row.get("ticker", "")).strip()
        if not ticker:
            continue
        price = number(row.get("side_price"))
        side = str(row.get("side", "")).strip().lower()
        if price is None or side not in ("yes", "no"):
            continue
        is_watch = truthy(row.get("watch"))
        edge = number(row.get("edge"))
        current = entries.get(ticker)
        if is_watch and (current is None or current["cohort"] != "official"):
            entries[ticker] = make_entry(row, "official", side, price)
        elif current is None and edge is not None and edge > 0:
            entries[ticker] = make_entry(row, "lean", side, price)
    return entries


def make_entry(row: dict, cohort: str, side: str, price: float) -> dict:
    event_ticker = str(row.get("event_ticker", "")).strip()
    return {
        "cohort": cohort,
        "ticker": str(row.get("ticker", "")).strip(),
        "event_ticker": event_ticker,
        "event_date": event_date_from_ticker(event_ticker) or "",
        "phrase": row.get("phrase", ""),
        "entered_at": row.get("snapshot_timestamp", ""),
        "side": side,
        "price": price,
        "model_probability": number(row.get("model_probability")),
        "edge": number(row.get("edge")),
        "hurdle": number(row.get("hurdle")),
        "data_risk": truthy(row.get("data_risk")),
    }


def settle(entries: dict[str, dict], results: dict[str, str]) -> list[dict]:
    trades = []
    for ticker, entry in sorted(entries.items()):
        result = results.get(ticker, "")
        if result not in ("yes", "no"):
            continue  # no final result: not a settled trade, never counted
        pnl = contract_pnl(entry["side"], entry["price"], result)
        won = (entry["side"] == result)
        trade = dict(entry)
        trade["result"] = result
        trade["won"] = won
        trade["pnl"] = round(pnl, 4)
        trades.append(trade)
    return trades


def cohort_stats(trades: list[dict], cohort: str) -> dict:
    rows = [t for t in trades if t["cohort"] == cohort]
    staked = sum(t["price"] for t in rows)
    pnl = sum(t["pnl"] for t in rows)
    return {
        "trades": len(rows),
        "wins": sum(t["won"] for t in rows),
        "total_staked": round(staked, 4),
        "total_pnl": round(pnl, 4),
        "return_on_stake": round(pnl / staked, 4) if staked else None,
    }


def build_summary(trades: list[dict], history_rows: int, snapshots: int,
                  results_count: int, resolved_events: set[str]) -> dict:
    official = cohort_stats(trades, "official")
    lean = cohort_stats(trades, "lean")
    enough = official["trades"] >= MIN_TRADES_FOR_CLAIM
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "is_money_backtest": True,
        "entry_rule": (
            "1 contract at the live buy price, at the first snapshot where the "
            "live rule said WATCH. Leans use the first positive-edge snapshot "
            "and are informational only."
        ),
        "price_source": "recorded live snapshots (no hindsight prices)",
        "fees_included": False,
        "history_rows": history_rows,
        "snapshots": snapshots,
        "markets_with_results": results_count,
        "resolved_event_count": len(resolved_events),
        "official": official,
        "lean": lean,
        "minimum_trades_for_claim": MIN_TRADES_FOR_CLAIM,
        "claim_status": "sufficient_sample" if enough else "insufficient_sample",
        "note": (
            "Only markets with both recorded pre-fight snapshots and a final "
            "Kalshi result are counted. One resolved card so far; this sample "
            "is far too small to prove or disprove an edge."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="use cached results only; no network")
    args = parser.parse_args()

    history = read_csv(PRICE_HISTORY)
    if not history:
        raise SystemExit(f"No price history at {PRICE_HISTORY}. Run the live refresher first.")

    today = datetime.now(timezone.utc).date().isoformat()
    resolved_events = past_event_tickers(history, today)
    cached = load_results_cache()
    if args.offline:
        results = cached
    else:
        results = fetch_results(resolved_events, cached)
        if results != cached:
            save_results_cache(results)

    entries = first_entries(history)
    trades = settle(entries, results)

    snapshots = len({row.get("snapshot_timestamp", "") for row in history})
    summary = build_summary(trades, len(history), snapshots, len(results), resolved_events)

    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with OUT_TRADES.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRADE_FIELDS)
        writer.writeheader()
        writer.writerows(trades)

    official = summary["official"]
    lean = summary["lean"]
    print(f"History: {summary['history_rows']} rows over {summary['snapshots']} snapshots.")
    print(f"Final results known for {summary['markets_with_results']} markets "
          f"across {summary['resolved_event_count']} past fight events.")
    print(f"Official trades: {official['trades']} "
          f"({official['wins']} wins, P/L ${official['total_pnl']:+.2f} "
          f"on ${official['total_staked']:.2f} staked)")
    print(f"Leans:           {lean['trades']} "
          f"({lean['wins']} wins, P/L ${lean['total_pnl']:+.2f} "
          f"on ${lean['total_staked']:.2f} staked)")
    print(f"Claim status: {summary['claim_status']} "
          f"(needs {MIN_TRADES_FOR_CLAIM} official trades)")
    print(f"Wrote {OUT_SUMMARY.relative_to(ROOT)} and {OUT_TRADES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
