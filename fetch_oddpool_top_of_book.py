#!/usr/bin/env python3
"""Fetch real historical top-of-book snapshots from Oddpool.

For Kalshi, Oddpool returns best_yes_bid / best_yes_ask directly.
For Polymarket, Oddpool returns best_bid / best_ask for a token. To compute a YES
price, provide the YES token asset_id and token_side=YES in your market mappings.

Inputs:
  Either direct CLI args:
    --exchange polymarket --market-id 0x... --asset-id ...

  Or a CSV:
    --markets market_data/market_mappings.csv

Outputs:
  market_data/oddpool_top_of_book.csv by default.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from oddpool_client import OddpoolError, historical_top_of_book, iso_from_ms


OUT_DEFAULT = Path("market_data/oddpool_top_of_book.csv")
MAPPING_DEFAULT = Path("market_data/market_mappings.csv")

CONTEXT_FIELDS = [
    "transcript_id",
    "event_date",
    "fighter_1",
    "fighter_2",
    "phrase",
    "question",
    "exchange",
    "market_id",
    "asset_id",
    "token_side",
]

SNAPSHOT_FIELDS = [
    "timestamp",
    "timestamp_iso",
    "best_bid",
    "best_ask",
    "best_yes_bid",
    "best_yes_ask",
    "yes_bid",
    "yes_ask",
    "mid",
    "spread",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def direct_market_row(args) -> dict:
    return {
        "exchange": args.exchange,
        "market_id": args.market_id,
        "asset_id": args.asset_id or "",
        "token_side": args.token_side or "",
        "phrase": args.phrase or "",
        "question": args.question or "",
        "price_start_iso": args.start or "",
        "price_end_iso": args.end or "",
    }


def mapping_time(row, cli_value, field):
    return cli_value or row.get(field) or ""


def normalize_snapshot(row: dict, snapshot: dict) -> dict:
    exchange = (row.get("exchange") or "").lower()
    token_side = (row.get("token_side") or "").strip().upper()

    out = {field: row.get(field, "") for field in CONTEXT_FIELDS}
    out["timestamp"] = snapshot.get("timestamp", "")
    out["timestamp_iso"] = iso_from_ms(snapshot.get("timestamp"))
    out["best_bid"] = snapshot.get("best_bid", "")
    out["best_ask"] = snapshot.get("best_ask", "")
    out["best_yes_bid"] = snapshot.get("best_yes_bid", "")
    out["best_yes_ask"] = snapshot.get("best_yes_ask", "")
    out["mid"] = snapshot.get("mid", "")
    out["spread"] = snapshot.get("spread", "")

    # Use actual venue fields only. No inferred prices.
    if exchange == "kalshi":
        out["yes_bid"] = snapshot.get("best_yes_bid", "")
        out["yes_ask"] = snapshot.get("best_yes_ask", "")
    elif exchange == "polymarket" and token_side == "YES" and row.get("asset_id"):
        out["yes_bid"] = snapshot.get("best_bid", "")
        out["yes_ask"] = snapshot.get("best_ask", "")
    else:
        out["yes_bid"] = ""
        out["yes_ask"] = ""
    return out


def write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = CONTEXT_FIELDS + SNAPSHOT_FIELDS
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", default="", help=f"CSV of mapped markets; default direct args only")
    parser.add_argument("--exchange", choices=["polymarket", "kalshi"], help="direct fetch venue")
    parser.add_argument("--market-id", help="direct fetch market id / ticker")
    parser.add_argument("--asset-id", help="Polymarket token id; use the YES asset id for YES pricing")
    parser.add_argument("--token-side", choices=["YES", "NO", "yes", "no"], help="token side for direct fetch")
    parser.add_argument("--phrase", help="phrase label for direct fetch")
    parser.add_argument("--question", help="market question for direct fetch")
    parser.add_argument("--start", help="ISO timestamp or Unix ms")
    parser.add_argument("--end", help="ISO timestamp or Unix ms")
    parser.add_argument("--granularity", choices=["1m", "5m"], default="5m")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    if args.markets:
        market_rows = read_csv(Path(args.markets))
    else:
        if not args.exchange or not args.market_id:
            raise SystemExit("Provide --markets CSV or both --exchange and --market-id.")
        market_rows = [direct_market_row(args)]

    out_rows = []
    for row in market_rows:
        exchange = (row.get("exchange") or "").strip().lower()
        market_id = (row.get("market_id") or "").strip()
        asset_id = (row.get("asset_id") or "").strip() or None
        if not exchange or not market_id:
            continue
        try:
            snapshots = historical_top_of_book(
                exchange=exchange,
                market_id=market_id,
                asset_id=asset_id,
                start_time=mapping_time(row, args.start, "price_start_iso"),
                end_time=mapping_time(row, args.end, "price_end_iso"),
                granularity=args.granularity,
                limit=args.limit,
                max_pages=args.pages,
            )
        except OddpoolError as exc:
            print(f"ERROR {exchange} {market_id}: {exc}")
            continue
        for snapshot in snapshots:
            out_rows.append(normalize_snapshot(row, snapshot))

    out = Path(args.out)
    write_rows(out, out_rows)
    quoted_yes = sum(1 for row in out_rows if row.get("yes_ask") not in ("", None))
    print(f"Wrote {len(out_rows)} top-of-book snapshots to {out}")
    print(f"Rows with usable YES ask: {quoted_yes}")


if __name__ == "__main__":
    main()
