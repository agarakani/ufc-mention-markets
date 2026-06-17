#!/usr/bin/env python3
"""Search Oddpool for real Polymarket/Kalshi markets.

This does not create prices. It only saves market metadata returned by Oddpool.

Examples:
  export ODDPOOL_API_KEY='oddpool_...'

  python3 search_oddpool_markets.py --q "UFC mention" --exchange polymarket
  python3 search_oddpool_markets.py --q "submission mentioned" --status closed
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from oddpool_client import OddpoolError, search_markets


OUT_DEFAULT = Path("market_data/oddpool_markets.csv")
FIELDS = [
    "market_id",
    "exchange",
    "series_id",
    "question",
    "category",
    "status",
    "volume",
    "liquidity",
    "last_yes_price",
    "last_no_price",
    "event_id",
    "event_title",
    "slug",
    "discovered_at",
    "settled_at",
]


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    extras = sorted({k for row in rows for k in row.keys()} - set(FIELDS))
    fields = FIELDS + extras
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--q", help="free-text search query, e.g. 'UFC mention'")
    parser.add_argument("--series-id", help="Oddpool/Kalshi/Polymarket series id")
    parser.add_argument("--exchange", choices=["polymarket", "kalshi"], help="optional venue filter")
    parser.add_argument("--status", choices=["active", "closed"], default="active")
    parser.add_argument("--category", help="exact category filter")
    parser.add_argument("--min-volume", type=int)
    parser.add_argument("--min-liquidity", type=int)
    parser.add_argument("--settled-after", help="ISO timestamp, useful with --status closed")
    parser.add_argument("--settled-before", help="ISO timestamp, useful with --status closed")
    parser.add_argument("--discovered-after", help="ISO timestamp for polling new listings")
    parser.add_argument("--sort-by", choices=["relevance", "newest", "volume", "liquidity"], default="volume")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    args = parser.parse_args()

    try:
        rows = search_markets(
            q=args.q,
            series_id=args.series_id,
            exchange=args.exchange,
            status=args.status,
            category=args.category,
            min_volume=args.min_volume,
            min_liquidity=args.min_liquidity,
            settled_after=args.settled_after,
            settled_before=args.settled_before,
            discovered_after=args.discovered_after,
            sort_by=args.sort_by,
            limit=args.limit,
            max_pages=args.pages,
        )
    except OddpoolError as exc:
        raise SystemExit(str(exc))

    out = Path(args.out)
    write_csv(out, rows)
    print(f"Wrote {len(rows)} real market rows to {out}")
    if rows[:5]:
        print("\nTop results:")
        for row in rows[:5]:
            print(f"  [{row.get('exchange')}] {row.get('market_id')} | {row.get('question')}")


if __name__ == "__main__":
    main()
