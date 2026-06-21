#!/usr/bin/env python3
"""Settle a saved paper-tracking card after outcomes are known."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRACKING_ROOT_DEFAULT = ROOT / "data" / "tracking"
SUMMARY_DEFAULT = ROOT / "data" / "tracking" / "weekly_summary.csv"

SETTLED_FIELDS = [
    "card",
    "paper_action",
    "paper_side",
    "outcome",
    "paper_price",
    "paper_contracts",
    "paper_pnl",
    "event_title",
    "phrase",
    "ticker",
    "model_probability",
    "yes_ask",
    "no_ask",
    "side_price",
    "yes_edge",
    "no_edge",
    "side",
    "edge",
    "watch",
    "confidence_note",
    "notes",
]

SUMMARY_FIELDS = [
    "card",
    "settled_at",
    "prediction_rows",
    "outcomes_filled",
    "official_trades",
    "official_wins",
    "official_cost",
    "official_pnl",
    "official_roi",
    "leans",
    "lean_wins",
    "lean_cost",
    "lean_pnl",
    "lean_roi",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def number(value) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_outcome(value: str) -> str:
    text = str(value or "").strip().lower()
    if text in {"yes", "y", "1", "true", "hit", "win"}:
        return "yes"
    if text in {"no", "n", "0", "false", "miss", "loss"}:
        return "no"
    return ""


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "_", str(value).strip().lower()).strip("_")
    return text or "card"


def contract_pnl(side: str, price: float, outcome: str, contracts: float = 1.0) -> float:
    side = str(side or "").strip().lower()
    if side not in {"yes", "no"}:
        raise ValueError(f"Unknown side: {side!r}")
    if outcome not in {"yes", "no"}:
        raise ValueError(f"Unknown outcome: {outcome!r}")
    if side == outcome:
        return (1.0 - price) * contracts
    return -price * contracts


def money(value: float) -> str:
    return f"{value:.4f}"


def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}"


def summarize(rows: list[dict], action: str) -> dict:
    selected = [row for row in rows if row.get("paper_action") == action and row.get("outcome") in {"yes", "no"}]
    cost = sum(number(row.get("paper_price")) or 0.0 for row in selected)
    pnl = sum(number(row.get("paper_pnl")) or 0.0 for row in selected)
    wins = sum(row.get("paper_side") == row.get("outcome") for row in selected)
    roi = None if cost <= 0 else pnl / cost
    return {
        "count": len(selected),
        "wins": wins,
        "cost": cost,
        "pnl": pnl,
        "roi": roi,
    }


def upsert_summary(path: Path, summary: dict) -> None:
    rows = []
    if path.exists():
        rows = [row for row in read_csv(path) if row.get("card") != summary.get("card")]
    rows.append(summary)
    rows.sort(key=lambda row: row.get("card", ""))
    write_csv(path, rows, SUMMARY_FIELDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate paper P/L after outcomes are filled in.")
    parser.add_argument("--card", required=True, help="card folder name under data/tracking")
    parser.add_argument("--tracking-root", default=str(TRACKING_ROOT_DEFAULT))
    parser.add_argument("--summary", default=str(SUMMARY_DEFAULT))
    args = parser.parse_args()

    card = slug(args.card)
    card_dir = Path(args.tracking_root) / card
    predictions_path = card_dir / "predictions.csv"
    outcomes_path = card_dir / "outcomes.csv"
    if not predictions_path.exists():
        raise SystemExit(f"Missing {predictions_path}. Run snapshot_card.py first.")
    if not outcomes_path.exists():
        raise SystemExit(f"Missing {outcomes_path}.")

    predictions = read_csv(predictions_path)
    outcomes_by_ticker = {
        row.get("ticker", ""): {
            "outcome": normalize_outcome(row.get("outcome", "")),
            "notes": row.get("notes", ""),
        }
        for row in read_csv(outcomes_path)
    }

    settled = []
    outcomes_filled = 0
    for row in predictions:
        result = outcomes_by_ticker.get(row.get("ticker", ""), {})
        outcome = result.get("outcome", "")
        if outcome:
            outcomes_filled += 1
        side = str(row.get("paper_side") or row.get("side") or "").strip().lower()
        fallback_price = row.get("yes_ask") if side == "yes" else row.get("no_ask") if side == "no" else ""
        price = number(row.get("paper_price")) or number(row.get("side_price")) or number(fallback_price)
        contracts = number(row.get("paper_contracts")) or 0.0
        pnl = ""
        if row.get("paper_action") in {"trade", "lean"} and outcome and price is not None and side in {"yes", "no"}:
            pnl = money(contract_pnl(side, price, outcome, contracts))

        enriched = dict(row)
        enriched["paper_side"] = side
        enriched["outcome"] = outcome
        enriched["notes"] = result.get("notes", "")
        enriched["paper_pnl"] = pnl
        settled.append(enriched)

    official = summarize(settled, "trade")
    leans = summarize(settled, "lean")
    summary = {
        "card": card,
        "settled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "prediction_rows": str(len(predictions)),
        "outcomes_filled": str(outcomes_filled),
        "official_trades": str(official["count"]),
        "official_wins": str(official["wins"]),
        "official_cost": money(official["cost"]),
        "official_pnl": money(official["pnl"]),
        "official_roi": pct(official["roi"]),
        "leans": str(leans["count"]),
        "lean_wins": str(leans["wins"]),
        "lean_cost": money(leans["cost"]),
        "lean_pnl": money(leans["pnl"]),
        "lean_roi": pct(leans["roi"]),
    }

    write_csv(card_dir / "settled_predictions.csv", settled, SETTLED_FIELDS)
    (card_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    upsert_summary(Path(args.summary), summary)

    print(f"Settled card: {card}")
    print(f"Outcomes filled: {outcomes_filled}/{len(predictions)}")
    print(f"Official trades: {official['count']}, P/L: {official['pnl']:.4f}")
    print(f"Leans: {leans['count']}, P/L: {leans['pnl']:.4f}")
    print(f"Summary: {Path(args.summary).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
