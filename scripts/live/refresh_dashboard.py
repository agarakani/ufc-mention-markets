#!/usr/bin/env python3
"""Refresh live Kalshi UFC mention prices and dashboard data, read-only."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.build_dashboard_data import build_payload, write_data, OUT_DEFAULT as DASHBOARD_DATA
from ufc_mentions.kalshi_client import KalshiClient
from ufc_mentions.kalshi_context_model import KalshiFightContextModel
from ufc_mentions.kalshi_mentions import (
    TranscriptCorpus,
    event_date_from_ticker,
    fighters_from_market_title,
)
from scripts.live.price_fight import price_market


DATA_DEFAULT = ROOT / "ufc_cleaned_export"
LIVE_DEFAULT = ROOT / "market_data" / "kalshi_live_edges.csv"
HISTORY_DEFAULT = ROOT / "market_data" / "kalshi_price_history.csv"
META_DEFAULT = ROOT / "market_data" / "kalshi_live_meta.json"

FIELDS = [
    "snapshot_timestamp", "series_ticker", "event_ticker", "event_date",
    "event_title", "fighter_1", "fighter_2", "ticker", "phrase", "forms",
    "rules_primary", "model_probability", "history_probability", "probability_source",
    "context_probability", "context_status", "context_note", "context_profile",
    "context_training_rows", "context_validation_rows", "context_positive_rate",
    "context_validation_log_loss", "context_base_log_loss",
    "context_log_loss_improvement", "context_best_c", "context_calibrated",
    "context_row_source", "league_rate", "league_hits",
    "league_fights", "fighter_rate", "fighter_hits", "fighter_fights",
    "word_type", "prior_strength", "confidence_ok", "confidence_note",
    "yes_bid", "yes_ask", "no_bid", "no_ask", "spread", "fee_buffer",
    "hurdle", "edge", "watch", "validation_status",
    "previous_yes_ask", "ask_change", "status", "error",
]

HISTORY_FIELDS = [
    "snapshot_timestamp", "event_ticker", "ticker", "phrase", "yes_bid",
    "yes_ask", "no_bid", "no_ask", "spread", "model_probability",
    "history_probability", "probability_source",
    "context_status", "edge", "hurdle", "watch",
]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    temporary.replace(path)


def append_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(newline="", encoding="utf-8-sig") as fh:
            existing_fields = next(csv.reader(fh), [])
        if existing_fields != fields:
            legacy_rows = read_csv(path)
            write_csv(path, legacy_rows, fields)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def value(value) -> str:
    return "" if value is None else f"{float(value):.8f}"


def bool_text(value: bool) -> str:
    return "yes" if value else "no"


def event_snapshot(
    client: KalshiClient,
    corpus: TranscriptCorpus,
    event: dict,
    *,
    fee_buffer: float,
    min_fighter_fights: int,
    snapshot_timestamp: str,
    context_model=None,
    require_context_model: bool = False,
) -> list[dict]:
    event_ticker = event.get("event_ticker", "")
    markets = client.get_markets(event_ticker=event_ticker)
    if not markets:
        return []
    title = event.get("title") or markets[0].get("title", "")
    fighter_1, fighter_2 = fighters_from_market_title(markets[0].get("title", title))
    event_date = event_date_from_ticker(event_ticker) or ""
    rows = []
    for market in markets:
        phrase = str((market.get("custom_strike") or {}).get("Word") or market.get("yes_sub_title") or "")
        book = client.get_orderbook(market["ticker"])
        try:
            priced = price_market(
                market,
                book,
                corpus,
                fighter_1,
                fighter_2,
                cutoff_date=event_date or None,
                fee_buffer=fee_buffer,
                min_fighter_fights=min_fighter_fights,
                context_model=context_model,
                require_context_model=require_context_model,
            )
        except Exception as exc:
            rows.append({
                "snapshot_timestamp": snapshot_timestamp,
                "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
                "event_ticker": event_ticker,
                "event_date": event_date,
                "event_title": title,
                "fighter_1": fighter_1,
                "fighter_2": fighter_2,
                "ticker": market.get("ticker", ""),
                "phrase": phrase,
                "forms": phrase,
                "rules_primary": market.get("rules_primary", ""),
                "yes_bid": value(book.yes_bid),
                "yes_ask": value(book.yes_ask),
                "no_bid": value(book.no_bid),
                "no_ask": value(book.no_ask),
                "spread": value(book.spread),
                "fee_buffer": value(fee_buffer),
                "watch": bool_text(False),
                "validation_status": "unvalidated",
                "probability_source": "unavailable",
                "status": "error",
                "error": str(exc),
            })
            continue
        if priced is None:
            continue
        estimate = priced.estimate
        rows.append({
            "snapshot_timestamp": snapshot_timestamp,
            "series_ticker": event.get("series_ticker", "KXFIGHTMENTION"),
            "event_ticker": event_ticker,
            "event_date": event_date,
            "event_title": title,
            "fighter_1": fighter_1,
            "fighter_2": fighter_2,
            "ticker": priced.ticker,
            "phrase": priced.label,
            "forms": " | ".join(priced.forms),
            "rules_primary": priced.rules,
            "model_probability": value(estimate.probability),
            "history_probability": value(estimate.history_probability),
            "probability_source": estimate.probability_source,
            "context_probability": value(estimate.context_probability),
            "context_status": estimate.context_status,
            "context_note": estimate.context_note,
            "context_profile": estimate.context_profile,
            "context_training_rows": estimate.context_training_rows,
            "context_validation_rows": estimate.context_validation_rows,
            "context_positive_rate": value(estimate.context_positive_rate),
            "context_validation_log_loss": value(estimate.context_validation_log_loss),
            "context_base_log_loss": value(estimate.context_base_log_loss),
            "context_log_loss_improvement": value(estimate.context_log_loss_improvement),
            "context_best_c": estimate.context_best_c,
            "context_calibrated": bool_text(estimate.context_calibrated),
            "context_row_source": estimate.context_row_source,
            "league_rate": value(estimate.league_rate),
            "league_hits": estimate.league_hits,
            "league_fights": estimate.league_fights,
            "fighter_rate": value(estimate.fighter_rate),
            "fighter_hits": estimate.fighter_hits,
            "fighter_fights": estimate.fighter_fights,
            "word_type": estimate.word_type,
            "prior_strength": "" if estimate.prior_strength is None else value(estimate.prior_strength),
            "confidence_ok": bool_text(estimate.confidence_ok),
            "confidence_note": estimate.confidence_note,
            "yes_bid": value(book.yes_bid),
            "yes_ask": value(book.yes_ask),
            "no_bid": value(book.no_bid),
            "no_ask": value(book.no_ask),
            "spread": value(book.spread),
            "fee_buffer": value(fee_buffer),
            "hurdle": value(priced.hurdle),
            "edge": value(priced.edge),
            "watch": bool_text(priced.watch),
            "validation_status": priced.validation_status,
            "status": "ok",
            "error": "",
        })
    return rows


def add_price_changes(rows: list[dict], previous: list[dict]) -> None:
    previous_by_ticker = {row.get("ticker"): row for row in previous}
    for row in rows:
        old = previous_by_ticker.get(row.get("ticker"), {})
        prior = old.get("yes_ask", "")
        row["previous_yes_ask"] = prior
        try:
            row["ask_change"] = value(float(row["yes_ask"]) - float(prior))
        except (KeyError, TypeError, ValueError):
            row["ask_change"] = ""


def refresh_once(
    client: KalshiClient,
    corpus: TranscriptCorpus,
    *,
    series_ticker: str,
    event_ticker: str | None,
    exclude_event_tickers: set[str] | None = None,
    fee_buffer: float,
    min_fighter_fights: int,
    poll_seconds: float,
    context_model=None,
    require_context_model: bool = True,
    verbose: bool = False,
    live_path: Path = LIVE_DEFAULT,
    history_path: Path = HISTORY_DEFAULT,
    meta_path: Path = META_DEFAULT,
) -> list[dict]:
    snapshot_timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if event_ticker:
        events = [{
            "event_ticker": event_ticker,
            "series_ticker": series_ticker,
            "title": "",
        }]
    else:
        events = client.get_events(series_ticker=series_ticker, status="open")
        excluded = {ticker.upper() for ticker in (exclude_event_tickers or set())}
        if excluded:
            events = [
                event for event in events
                if str(event.get("event_ticker") or "").upper() not in excluded
            ]

    if verbose:
        print(f"Found {len(events)} open Kalshi fight event(s). Pricing phrases now...", flush=True)

    rows = []
    errors = []
    for index, event in enumerate(events, start=1):
        event_name = event.get("title") or event.get("event_ticker") or "fight"
        if verbose:
            print(f"  {index}/{len(events)} {event_name}", flush=True)
        try:
            rows.extend(event_snapshot(
                client,
                corpus,
                event,
                context_model=context_model,
                require_context_model=require_context_model,
                fee_buffer=fee_buffer,
                min_fighter_fights=min_fighter_fights,
                snapshot_timestamp=snapshot_timestamp,
            ))
        except Exception as exc:
            errors.append(f"{event.get('event_ticker', '')}: {exc}")
            if verbose:
                print(f"    skipped: {exc}", flush=True)

    rows.sort(key=lambda row: (
        row.get("watch") != "yes",
        -(float(row.get("edge") or -999)),
        row.get("event_date", ""),
        row.get("phrase", ""),
    ))
    previous = read_csv(live_path)
    add_price_changes(rows, previous)
    write_csv(live_path, rows, FIELDS)
    append_csv(history_path, rows, HISTORY_FIELDS)
    meta = {
        "snapshot_timestamp": snapshot_timestamp,
        "series_ticker": series_ticker,
        "poll_seconds": poll_seconds,
        "events_discovered": len(events),
        "excluded_event_tickers": sorted(exclude_event_tickers or []),
        "markets_priced": len(rows),
        "watch_rows": sum(row.get("watch") == "yes" for row in rows),
        "fight_model_required": require_context_model,
        "authenticated": client.authenticated,
        "errors": errors,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    payload = build_payload()
    write_data(DASHBOARD_DATA, payload)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Continuously refresh the read-only Kalshi dashboard feed.")
    parser.add_argument("--series", default="KXFIGHTMENTION")
    parser.add_argument("--event-ticker", help="restrict refresh to one event")
    parser.add_argument(
        "--exclude-event-ticker",
        action="append",
        default=[],
        help="skip an event, useful after a fight has started; can be repeated",
    )
    parser.add_argument("--data-dir", default=str(DATA_DEFAULT))
    parser.add_argument("--fee-buffer-cents", type=float, default=2.0)
    parser.add_argument("--min-fighter-fights", type=int, default=15)
    parser.add_argument("--no-fight-model", action="store_true", help="use simple history only")
    parser.add_argument("--poll-seconds", type=float, default=0, help="0 refreshes once")
    parser.add_argument("--iterations", type=int, default=0, help="0 polls until interrupted")
    args = parser.parse_args()

    client = KalshiClient()
    print(f"Loading transcript corpus from {args.data_dir} ...")
    corpus = TranscriptCorpus.load(args.data_dir)
    print(f"Loaded {len(corpus.fights)} valid fights. Kalshi access: {'authenticated' if client.authenticated else 'public read'}.")
    print("READ-ONLY: this process cannot place trades.\n")
    context_model = None
    if not args.no_fight_model:
        print("Loading fight-level phrase model ...")
        context_model = KalshiFightContextModel.load(corpus)
        print("Live rows will use fight-specific model probabilities when available.\n")

    iteration = 0
    while True:
        iteration += 1
        try:
            rows = refresh_once(
                client,
                corpus,
                context_model=context_model,
                require_context_model=not args.no_fight_model,
                series_ticker=args.series,
                event_ticker=args.event_ticker,
                exclude_event_tickers={ticker.upper() for ticker in args.exclude_event_ticker},
                fee_buffer=args.fee_buffer_cents / 100.0,
                min_fighter_fights=args.min_fighter_fights,
                poll_seconds=args.poll_seconds,
                verbose=True,
            )
            print(
                f"Refreshed {len({row.get('event_ticker') for row in rows})} fights, "
                f"{len(rows)} phrase markets, {sum(row.get('watch') == 'yes' for row in rows)} watch rows."
            )
        except Exception as exc:
            print(f"Refresh failed; previous dashboard snapshot was preserved: {exc}")
        if args.poll_seconds <= 0 or (args.iterations and iteration >= args.iterations):
            break
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
