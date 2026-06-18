#!/usr/bin/env python3
"""Backtest historical mention predictions against executable pre-event asks.

The backtest uses the latest quoted ask at or before a fixed cutoff. It never
uses midpoint, last trade, post-cutoff quotes, or a synthetic complementary
price. YES and NO asks must be present as actual token quotes.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


PREDICTIONS_DEFAULT = Path("model_outputs/historical_market_predictions.csv")
QUOTES_DEFAULT = Path("market_data/historical_top_of_book.csv")
TRADES_DEFAULT = Path("model_outputs/historical_backtest_trades.csv")
SUMMARY_DEFAULT = Path("model_outputs/historical_backtest_summary.json")

TRADE_FIELDS = [
    "market_id", "exchange", "event_date", "scope", "phrase", "question", "model_probability",
    "resolved_yes", "entry_cutoff_iso", "quote_side", "quote_timestamp_iso",
    "quote_age_minutes", "ask", "all_in_price", "model_edge", "trade_status",
    "side", "stake", "shares", "fees", "won", "payout", "pnl", "return_on_stake",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def as_float(value):
    try:
        if value in (None, ""):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def as_bool(value):
    lowered = str(value).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def timestamp_ms(row: dict) -> int | None:
    raw = as_float(row.get("timestamp"))
    if raw is not None:
        return int(raw)
    parsed = parse_iso(row.get("timestamp_iso", ""))
    return int(parsed.timestamp() * 1000) if parsed else None


def quote_side(row: dict) -> str:
    return str(row.get("quote_side") or row.get("token_side") or "").strip().upper()


def quote_ask(row: dict, side: str):
    field = "yes_ask" if side == "YES" else "no_ask"
    return as_float(row.get(field)) if row.get(field) not in (None, "") else as_float(row.get("best_ask"))


def select_quote(rows: list[dict], side: str, cutoff: datetime, max_age_minutes: float):
    cutoff_ms = int(cutoff.timestamp() * 1000)
    candidates = []
    for row in rows:
        if quote_side(row) != side:
            continue
        timestamp = timestamp_ms(row)
        ask = quote_ask(row, side)
        if timestamp is None or ask is None or not (0 < ask < 1):
            continue
        if timestamp <= cutoff_ms:
            candidates.append((timestamp, ask, row))
    if not candidates:
        return None
    timestamp, ask, row = max(candidates, key=lambda item: item[0])
    age_minutes = (cutoff_ms - timestamp) / 60_000
    if age_minutes > max_age_minutes:
        return None
    return {"timestamp": timestamp, "ask": ask, "row": row, "age_minutes": age_minutes}


def trade_candidate(probability: float, side: str, ask: float, fee_rate: float, slippage: float):
    side_probability = probability if side == "YES" else 1.0 - probability
    execution_price = min(ask + slippage, 0.999999)
    all_in_price = execution_price * (1.0 + fee_rate)
    return {
        "side": side,
        "side_probability": side_probability,
        "ask": ask,
        "execution_price": execution_price,
        "all_in_price": all_in_price,
        "edge": side_probability - all_in_price,
    }


def settle_trade(candidate: dict, resolved_yes: bool, stake: float, fee_rate: float):
    shares = stake / candidate["execution_price"]
    fees = stake * fee_rate
    won = resolved_yes if candidate["side"] == "YES" else not resolved_yes
    payout = shares if won else 0.0
    pnl = payout - stake - fees
    return {
        **candidate,
        "stake": stake,
        "shares": shares,
        "fees": fees,
        "won": won,
        "payout": payout,
        "pnl": pnl,
        "return_on_stake": pnl / stake,
    }


def max_drawdown(pnls: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054):
    if trials == 0:
        return None, None
    rate = successes / trials
    denominator = 1.0 + z * z / trials
    center = (rate + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt((rate * (1 - rate) + z * z / (4 * trials)) / trials) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def build_summary(rows: list[dict], min_claim_markets: int) -> dict:
    trades = [row for row in rows if row.get("trade_status") == "traded"]
    pnls = [float(row["pnl"]) for row in trades]
    stake = sum(float(row["stake"]) for row in trades)
    wins = sum(row.get("won") == "True" for row in trades)
    hit_rate_low, hit_rate_high = wilson_interval(wins, len(trades))
    return {
        "markets_evaluated": len(rows),
        "trades": len(trades),
        "wins": wins,
        "hit_rate": wins / len(trades) if trades else None,
        "hit_rate_95pct_low": hit_rate_low,
        "hit_rate_95pct_high": hit_rate_high,
        "total_staked": stake,
        "total_pnl": sum(pnls),
        "roi": sum(pnls) / stake if stake else None,
        "average_model_edge": (
            sum(float(row["model_edge"]) for row in trades) / len(trades) if trades else None
        ),
        "max_drawdown": max_drawdown(pnls),
        "claim_status": "reportable" if len(trades) >= min_claim_markets else "insufficient_sample",
        "minimum_trades_for_claim": min_claim_markets,
    }


def run_backtest(
    predictions: list[dict],
    quotes: list[dict],
    *,
    entry_minutes: int,
    max_quote_age_minutes: int,
    min_edge: float,
    stake: float,
    fee_rate: float,
    slippage: float,
):
    quote_index = defaultdict(list)
    for row in quotes:
        quote_index[((row.get("exchange") or "").lower(), row.get("market_id", ""))].append(row)

    output = []
    for prediction in predictions:
        base = {field: prediction.get(field, "") for field in TRADE_FIELDS}
        market_id = prediction.get("market_id", "")
        probability = as_float(prediction.get("model_probability"))
        resolved_yes = as_bool(prediction.get("resolved_yes"))
        event_start = parse_iso(prediction.get("event_start_iso", ""))
        if prediction.get("prediction_status") != "ok" or probability is None:
            output.append({**base, "trade_status": "no_prediction"})
            continue
        if resolved_yes is None:
            output.append({**base, "trade_status": "unresolved"})
            continue
        if event_start is None:
            output.append({**base, "trade_status": "missing_event_start"})
            continue

        cutoff = event_start - timedelta(minutes=entry_minutes)
        market_quotes = quote_index[((prediction.get("exchange") or "polymarket").lower(), market_id)]
        selected = {
            side: select_quote(market_quotes, side, cutoff, max_quote_age_minutes)
            for side in ("YES", "NO")
        }
        candidates = []
        for side, quote in selected.items():
            if quote:
                candidate = trade_candidate(probability, side, quote["ask"], fee_rate, slippage)
                candidate["quote"] = quote
                candidates.append(candidate)
        if not candidates:
            output.append({
                **base,
                "entry_cutoff_iso": cutoff.isoformat().replace("+00:00", "Z"),
                "trade_status": "no_fresh_executable_ask",
            })
            continue

        best = max(candidates, key=lambda candidate: candidate["edge"])
        quote = best.pop("quote")
        common = {
            **base,
            "entry_cutoff_iso": cutoff.isoformat().replace("+00:00", "Z"),
            "quote_side": best["side"],
            "quote_timestamp_iso": quote["row"].get("timestamp_iso", ""),
            "quote_age_minutes": f"{quote['age_minutes']:.3f}",
            "ask": f"{best['ask']:.8f}",
            "all_in_price": f"{best['all_in_price']:.8f}",
            "model_edge": f"{best['edge']:.8f}",
        }
        if best["edge"] < min_edge:
            output.append({**common, "trade_status": "edge_below_threshold"})
            continue

        settled = settle_trade(best, resolved_yes, stake, fee_rate)
        output.append({
            **common,
            "trade_status": "traded",
            "side": settled["side"],
            "stake": f"{settled['stake']:.2f}",
            "shares": f"{settled['shares']:.8f}",
            "fees": f"{settled['fees']:.8f}",
            "won": str(settled["won"]),
            "payout": f"{settled['payout']:.8f}",
            "pnl": f"{settled['pnl']:.8f}",
            "return_on_stake": f"{settled['return_on_stake']:.8f}",
        })
    return output


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=TRADE_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in TRADE_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default=str(PREDICTIONS_DEFAULT))
    parser.add_argument("--quotes", default=str(QUOTES_DEFAULT))
    parser.add_argument("--entry-minutes", type=int, default=60)
    parser.add_argument("--max-quote-age-minutes", type=int, default=30)
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument("--stake", type=float, default=100.0)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--min-claim-markets", type=int, default=30)
    parser.add_argument("--trades-out", default=str(TRADES_DEFAULT))
    parser.add_argument("--summary-out", default=str(SUMMARY_DEFAULT))
    args = parser.parse_args()

    rows = run_backtest(
        read_csv(Path(args.predictions)),
        read_csv(Path(args.quotes)),
        entry_minutes=args.entry_minutes,
        max_quote_age_minutes=args.max_quote_age_minutes,
        min_edge=args.min_edge,
        stake=args.stake,
        fee_rate=args.fee_rate,
        slippage=args.slippage,
    )
    summary = build_summary(rows, args.min_claim_markets)
    summary["assumptions"] = {
        "entry_minutes_before_event": args.entry_minutes,
        "max_quote_age_minutes": args.max_quote_age_minutes,
        "minimum_probability_edge": args.min_edge,
        "fixed_stake": args.stake,
        "fee_rate": args.fee_rate,
        "slippage_probability_points": args.slippage,
    }
    write_csv(Path(args.trades_out), rows)
    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote trade audit to {args.trades_out}")
    print(f"Wrote summary to {args.summary_out}")


if __name__ == "__main__":
    main()
