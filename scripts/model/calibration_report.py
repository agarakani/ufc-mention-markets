#!/usr/bin/env python3
"""How well the live numbers have held up on settled Kalshi markets.

The walk-forward gate answers "which model is best". This answers a different
and blunter question: when the board said 30%, did it happen 30% of the time?

It joins every settled market's outcome to the last live prediction recorded
before that card, then reports expected calibration error (ECE) plus a bin
table. Both are computed on real out-of-sample predictions the board actually
showed — no refitting, no hindsight.

Written at settle time to model_outputs/calibration_report.json.

Usage:
  python3 scripts/model/calibration_report.py
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LABELS = ROOT / "data" / "processed" / "kalshi_results_labels.csv"
HISTORY = ROOT / "market_data" / "kalshi_price_history.csv"
OUT_PATH = ROOT / "model_outputs" / "calibration_report.json"

BIN_EDGES = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.60, 1.01]
PREFIGHT_CUTOFF_UTC = "12:00:00+00:00"


def _float(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result else None


def _mid(row) -> float | None:
    """Mid of the book: the ask alone overstates what the market believes."""
    ask = _float(row.get("yes_ask"))
    bid = _float(row.get("yes_bid"))
    if ask is None:
        return bid
    if bid is None:
        return ask
    return (ask + bid) / 2


def collect_pairs(labels_path: Path = LABELS, history_path: Path = HISTORY) -> list[dict]:
    """Last recorded prediction for every settled market, with its outcome."""
    if not labels_path.exists() or not history_path.exists():
        return []
    labels = {}
    with labels_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            outcome = str(row.get("outcome", "")).strip().lower()
            if ticker and outcome in ("yes", "no"):
                labels[ticker] = row

    # Only snapshots taken before the card started. Markets stay open during
    # the fights, so a later price already knows whether the word was said —
    # scoring against that would flatter the market with hindsight the model
    # never had. Every card in this set starts after noon UTC on its date.
    cutoffs = {
        ticker: f"{str(row.get('event_date', '')).strip()}T{PREFIGHT_CUTOFF_UTC}"
        for ticker, row in labels.items()
    }

    latest: dict[str, tuple[str, dict]] = {}
    with history_path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            ticker = str(row.get("ticker", "")).strip()
            if ticker not in labels:
                continue
            stamp = str(row.get("snapshot_timestamp", ""))
            cutoff = cutoffs.get(ticker)
            if cutoff and stamp > cutoff:
                continue
            if ticker not in latest or stamp > latest[ticker][0]:
                latest[ticker] = (stamp, row)

    pairs = []
    for ticker, (_stamp, row) in latest.items():
        probability = _float(row.get("model_probability"))
        if probability is None:
            continue
        label = labels[ticker]
        pairs.append({
            "ticker": ticker,
            "phrase": label.get("phrase", ""),
            "event_date": label.get("event_date", ""),
            "probability": probability,
            "outcome": 1 if label.get("outcome", "").strip().lower() == "yes" else 0,
            "market": _mid(row),
        })
    return pairs


def calibration_bins(pairs: list[dict], edges: list[float] | None = None) -> list[dict]:
    edges = edges or BIN_EDGES
    buckets: dict[int, list[dict]] = defaultdict(list)
    for pair in pairs:
        for index in range(len(edges) - 1):
            if edges[index] <= pair["probability"] < edges[index + 1]:
                buckets[index].append(pair)
                break
    out = []
    for index in sorted(buckets):
        rows = buckets[index]
        out.append({
            "low": edges[index],
            "high": min(1.0, edges[index + 1]),
            "count": len(rows),
            "mean_prediction": sum(r["probability"] for r in rows) / len(rows),
            "actual_rate": sum(r["outcome"] for r in rows) / len(rows),
        })
    return out


def expected_calibration_error(bins: list[dict]) -> float | None:
    total = sum(b["count"] for b in bins)
    if not total:
        return None
    return sum(b["count"] * abs(b["actual_rate"] - b["mean_prediction"]) for b in bins) / total


def log_loss(pairs: list[tuple[float, int]]) -> float | None:
    """Mean log loss. Lower is better; guessing the base rate is the floor."""
    if not pairs:
        return None
    total = 0.0
    for probability, outcome in pairs:
        clipped = min(max(probability, 1e-4), 1 - 1e-4)
        total += -(outcome * math.log(clipped) + (1 - outcome) * math.log(1 - clipped))
    return total / len(pairs)


def discrimination(pairs: list[tuple[float, int]]) -> float | None:
    """AUC: the chance a market that happened was priced above one that did not.
    0.5 is a coin flip. This is ranking skill, separate from calibration."""
    positives = [p for p, y in pairs if y == 1]
    negatives = [p for p, y in pairs if y == 0]
    if not positives or not negatives:
        return None
    wins = sum((a > b) + 0.5 * (a == b) for a in positives for b in negatives)
    return wins / (len(positives) * len(negatives))


def head_to_head(pairs: list[dict]) -> dict:
    """The model against the market, on the same pre-fight markets."""
    both = [p for p in pairs if p["market"] is not None]
    if not both:
        return {}
    ours = [(p["probability"], p["outcome"]) for p in both]
    theirs = [(p["market"], p["outcome"]) for p in both]
    base_rate = sum(p["outcome"] for p in both) / len(both)
    by_card = {}
    for card in sorted({p["event_date"] for p in both if p["event_date"]}):
        rows = [p for p in both if p["event_date"] == card]
        by_card[card] = {
            "markets": len(rows),
            "model_log_loss": log_loss([(r["probability"], r["outcome"]) for r in rows]),
            "market_log_loss": log_loss([(r["market"], r["outcome"]) for r in rows]),
        }
    return {
        "markets": len(both),
        "model_log_loss": log_loss(ours),
        "market_log_loss": log_loss(theirs),
        "base_log_loss": log_loss([(base_rate, y) for _, y in ours]),
        "model_auc": discrimination(ours),
        "market_auc": discrimination(theirs),
        "cards_model_won": sum(
            1 for c in by_card.values()
            if c["model_log_loss"] is not None and c["market_log_loss"] is not None
            and c["model_log_loss"] < c["market_log_loss"]
        ),
        "cards": by_card,
    }


def build(labels_path: Path = LABELS, history_path: Path = HISTORY) -> dict:
    pairs = collect_pairs(labels_path, history_path)
    bins = calibration_bins(pairs)
    ece = expected_calibration_error(bins)
    scored_market = [p for p in pairs if p["market"] is not None]
    market_bins = calibration_bins([
        {**p, "probability": p["market"]} for p in scored_market
    ])
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets": len(pairs),
        "cards": sorted({p["event_date"] for p in pairs if p["event_date"]}),
        "ece": ece,
        "market_ece": expected_calibration_error(market_bins),
        "mean_prediction": (sum(p["probability"] for p in pairs) / len(pairs)) if pairs else None,
        "actual_rate": (sum(p["outcome"] for p in pairs) / len(pairs)) if pairs else None,
        "bins": bins,
        "head_to_head": head_to_head(pairs),
        "note": (
            "Each settled market scored against the last prediction the live "
            "board recorded before its card. ECE is the average gap between "
            "what we said and what happened, weighted by how many markets sat "
            "in each band. Lower is better."
        ),
    }


def main() -> None:
    report = build()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if report["ece"] is None:
        print("No settled markets with recorded predictions yet.")
        return
    print(f"{report['markets']} settled markets across {len(report['cards'])} cards")
    print(f"  we said {report['mean_prediction']:.1%} on average, {report['actual_rate']:.1%} happened")
    print(f"  ECE {report['ece']:.3f}" + (
        f" (market {report['market_ece']:.3f})" if report["market_ece"] is not None else ""))
    for row in report["bins"]:
        print(f"  {row['low']:.0%}-{row['high']:.0%}: n={row['count']:>3} "
              f"said {row['mean_prediction']:.1%} happened {row['actual_rate']:.1%}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
