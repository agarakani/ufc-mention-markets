#!/usr/bin/env python3
"""Save a pre-fight paper-tracking snapshot from the latest live model board."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LIVE_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
META_DEFAULT = ROOT / "market_data" / "kalshi_live_meta.json"
OUT_ROOT_DEFAULT = ROOT / "data" / "tracking"

TRACKING_FIELDS = [
    "card",
    "tracked_at",
    "paper_action",
    "paper_reason",
    "paper_side",
    "paper_contracts",
    "paper_price",
]

OUTCOME_FIELDS = [
    "ticker",
    "event_ticker",
    "event_title",
    "fighter_1",
    "fighter_2",
    "phrase",
    "outcome",
    "resolution_status",
    "checked_at",
    "resolved_at",
    "market_status",
    "market_result",
    "market_expiration_value",
    "notes",
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


def slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9-]+", "_", str(value).strip().lower()).strip("_")
    return text or "card"


def default_card_name(meta_path: Path) -> str:
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stamp = datetime.fromisoformat(str(meta.get("snapshot_timestamp", "")).replace("Z", "+00:00"))
            return f"{stamp.date().isoformat()}_ufc_mentions"
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return f"{datetime.now(timezone.utc).date().isoformat()}_ufc_mentions"


def classify_row(row: dict, min_lean_edge: float) -> tuple[str, str]:
    side = str(row.get("side", "")).strip().lower()
    if side not in {"yes", "no"}:
        return "pass", "no side"

    if str(row.get("watch", "")).strip().lower() == "yes":
        if str(row.get("data_risk", "")).strip().lower() in {"1", "true", "yes", "y"}:
            return "trade", f"data-risk watch {side}"
        return "trade", f"watch {side}"

    edge = number(row.get("edge"))
    if edge is not None and edge > min_lean_edge:
        return "lean", f"positive model edge on {side}, below watch bar"

    return "pass", "no edge"


def build_tracking_rows(rows: list[dict], *, card: str, min_lean_edge: float) -> list[dict]:
    tracked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for row in rows:
        action, reason = classify_row(row, min_lean_edge)
        enriched = dict(row)
        enriched.update({
            "card": card,
            "tracked_at": tracked_at,
            "paper_action": action,
            "paper_reason": reason,
            "paper_side": row.get("side", ""),
            "paper_contracts": "1" if action in {"trade", "lean"} else "0",
            "paper_price": row.get("side_price", ""),
        })
        out.append(enriched)
    return out


def outcome_template(rows: list[dict]) -> list[dict]:
    return [{field: row.get(field, "") for field in OUTCOME_FIELDS} for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Save the current live board for weekly paper tracking.")
    parser.add_argument("--card", help="card name, for example 2026-06-20_main_card")
    parser.add_argument("--source", default=str(LIVE_DEFAULT), help="live model CSV to snapshot")
    parser.add_argument("--meta", default=str(META_DEFAULT), help="live meta JSON used for the default card name")
    parser.add_argument("--out-root", default=str(OUT_ROOT_DEFAULT), help="where local tracking files are written")
    parser.add_argument(
        "--min-lean-edge-cents",
        type=float,
        default=0.0,
        help="minimum positive edge to save as a lean; official trades still require WATCH",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Missing {source}. Run scripts/live/refresh_dashboard.py first.")

    card = slug(args.card or default_card_name(Path(args.meta)))
    rows = read_csv(source)
    tracking_rows = build_tracking_rows(
        rows,
        card=card,
        min_lean_edge=args.min_lean_edge_cents / 100.0,
    )

    out_dir = Path(args.out_root) / card
    source_fields = list(rows[0].keys()) if rows else []
    prediction_fields = TRACKING_FIELDS + [field for field in source_fields if field not in TRACKING_FIELDS]
    write_csv(out_dir / "predictions.csv", tracking_rows, prediction_fields)
    write_csv(
        out_dir / "paper_positions.csv",
        [row for row in tracking_rows if row.get("paper_action") in {"trade", "lean"}],
        prediction_fields,
    )
    write_csv(out_dir / "outcomes.csv", outcome_template(tracking_rows), OUTCOME_FIELDS)

    counts = Counter(row.get("paper_action", "") for row in tracking_rows)
    (out_dir / "README.txt").write_text(
        "\n".join([
            f"card: {card}",
            f"source: {source}",
            f"rows: {len(tracking_rows)}",
            f"official paper trades: {counts.get('trade', 0)}",
            f"leans: {counts.get('lean', 0)}",
            "",
            "After the fights, fill outcomes.csv with yes/no in the outcome column.",
            "Then run: python3 scripts/tracking/settle_card.py --card " + card,
            "",
        ]),
        encoding="utf-8",
    )

    print(f"Saved tracking card: {out_dir.relative_to(ROOT)}")
    print(f"Rows: {len(tracking_rows)}")
    print(f"Official paper trades: {counts.get('trade', 0)}")
    print(f"Leans: {counts.get('lean', 0)}")
    print(f"Fill outcomes here: {(out_dir / 'outcomes.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
