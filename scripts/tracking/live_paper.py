#!/usr/bin/env python3
"""Record paper entries when the live board crosses the watch bar."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from scripts.tracking.snapshot_card import OUTCOME_FIELDS, outcome_template, slug, write_csv


ROOT = Path(__file__).resolve().parents[2]
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


def update_readme(card_dir: Path, *, card: str, entries: int) -> None:
    (card_dir / "README.txt").write_text(
        "\n".join([
            f"card: {card}",
            "mode: live paper entries",
            f"official paper trades: {entries}",
            "",
            "This folder records the first time each market became a WATCH row.",
            "Each entry uses the buy price that was live at that moment.",
            "",
            "After the fights, fill outcomes.csv with yes/no in the outcome column.",
            "Then run: python3 scripts/tracking/settle_card.py --card " + card,
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
        outcome_rows = existing_outcomes + [
            row for row in outcome_template(new_entries)
            if row.get("ticker", "") not in known_outcomes
        ]
        write_csv(outcomes_path, outcome_rows, OUTCOME_FIELDS)
    else:
        if not positions_path.exists():
            write_csv(positions_path, existing_positions, TRACKING_FIELDS)
        if not predictions_path.exists():
            write_csv(predictions_path, existing_predictions, TRACKING_FIELDS)
        if not outcomes_path.exists():
            write_csv(outcomes_path, existing_outcomes, OUTCOME_FIELDS)

    final_positions = read_csv(positions_path)
    total_entries = len(existing_trade_tickers(final_positions))
    update_readme(card_dir, card=card_slug, entries=total_entries)
    return {
        "card": card_slug,
        "path": display_path(card_dir),
        "new_entries": len(new_entries),
        "total_entries": total_entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Record paper entries from the latest live WATCH rows.")
    parser.add_argument("--card", required=True, help="card name, for example UFC Vegas 119 main card")
    parser.add_argument("--source", default=str(LIVE_DEFAULT), help="live model CSV to read")
    parser.add_argument("--out-root", default=str(OUT_ROOT_DEFAULT), help="where local tracking files are written")
    parser.add_argument("--contracts", type=float, default=1.0, help="paper contracts per entry")
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
    )
    print(f"Paper card: {result['card']}")
    print(f"New entries: {result['new_entries']}")
    print(f"Total entries: {result['total_entries']}")
    print(f"Folder: {result['path']}")


if __name__ == "__main__":
    main()
