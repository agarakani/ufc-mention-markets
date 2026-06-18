#!/usr/bin/env python3
"""Run the complete historical market backtest pipeline in order."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "market_data" / "historical_market_ledger.csv"
PREDICTIONS = ROOT / "model_outputs" / "historical_market_predictions.csv"
QUOTES = ROOT / "market_data" / "historical_top_of_book.csv"
QUOTE_REQUESTS = ROOT / "market_data" / "historical_quote_requests.csv"


def run(script: str, *args: str):
    command = [sys.executable, str(ROOT / script), *args]
    print(f"\n== {script} ==")
    subprocess.run(command, cwd=ROOT, check=True)


def count_rows(path: Path, predicate=None) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return sum(predicate(row) for row in rows) if predicate else len(rows)


def write_quote_requests() -> int:
    with PREDICTIONS.open(newline="", encoding="utf-8-sig") as fh:
        prediction_rows = list(csv.DictReader(fh))
    predicted_ids = {
        row.get("market_id")
        for row in prediction_rows
        if row.get("prediction_status") == "ok" and row.get("resolved_yes") in {"True", "False"}
    }
    with LEDGER.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        ledger_rows = list(reader)
        fields = reader.fieldnames or []
    requests = [row for row in ledger_rows if row.get("market_id") in predicted_ids]
    QUOTE_REQUESTS.parent.mkdir(parents=True, exist_ok=True)
    with QUOTE_REQUESTS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(requests)
    return len(requests)


def main():
    run("fetch_polymarket_metadata.py")
    run("build_historical_market_ledger.py")
    run("predict_historical_markets.py")

    ready = count_rows(LEDGER, lambda row: row.get("data_ready") == "yes")
    predicted = count_rows(PREDICTIONS, lambda row: row.get("prediction_status") == "ok")
    print(f"\nData-ready historical markets: {ready}")
    print(f"Leakage-safe historical predictions: {predicted}")

    quote_requests = write_quote_requests()
    if quote_requests:
        run(
            "fetch_oddpool_top_of_book.py",
            "--markets", str(QUOTE_REQUESTS),
            "--out", str(QUOTES),
            "--granularity", "5m",
            "--pages", "100",
        )
    else:
        print("Skipping Oddpool quote pull: no resolved markets have usable predictions yet.")

    if QUOTES.exists():
        run("backtest_historical_markets.py", "--quotes", str(QUOTES))
    else:
        print("Skipping backtest: no historical quote file exists yet.")


if __name__ == "__main__":
    main()
