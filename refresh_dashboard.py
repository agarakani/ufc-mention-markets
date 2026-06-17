#!/usr/bin/env python3
"""Refresh upcoming-card predictions and local dashboard data."""

from __future__ import annotations

import csv
import subprocess
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
UPCOMING = ROOT / "kaggle_data" / "ultimate_ufc_dataset" / "upcoming.csv"
MARKET_MAPPINGS = ROOT / "market_data" / "market_mappings.csv"
TOP_OF_BOOK = ROOT / "market_data" / "oddpool_top_of_book.csv"


def run(args: list[str]):
    print("$", " ".join(args))
    subprocess.run(args, cwd=ROOT, check=True)


def upcoming_dates() -> list[str]:
    if not UPCOMING.exists():
        return []
    with UPCOMING.open(newline="", encoding="utf-8-sig") as fh:
        return sorted({row.get("date", "") for row in csv.DictReader(fh) if row.get("date")})


def warn_if_stale():
    dates = upcoming_dates()
    if not dates:
        print(f"Missing or empty {UPCOMING.relative_to(ROOT)}")
        return
    latest = dates[-1]
    if latest < date.today().isoformat():
        print(
            f"Warning: latest upcoming.csv date is {latest}, which is before today. "
            "Refresh the Kaggle dataset or replace upcoming.csv with the current card."
        )
    else:
        print(f"Upcoming card dates: {', '.join(dates)}")


def main():
    warn_if_stale()
    run([sys.executable, "predict_upcoming_mentions.py"])

    if MARKET_MAPPINGS.exists() and TOP_OF_BOOK.exists():
        run([sys.executable, "build_edge_table.py"])
    else:
        print("Skipping edge table: market mappings or top-of-book prices are not present yet.")

    run([sys.executable, "build_dashboard_data.py"])
    print("Open dashboard/index.html to view the refreshed board.")


if __name__ == "__main__":
    main()
