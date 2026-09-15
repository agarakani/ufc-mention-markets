#!/usr/bin/env python3
"""Freshen the published site's prices/edges from the cloud while the Mac sleeps.

Reads the published data.js (the site is its own feed), fetches current Kalshi
order books for every fight-model market, recomputes edges and watch calls with
the SAME entry rules as the live refresher, and rewrites data.js. Display-only:
never records price history, paper entries, or anything on main.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.entry_rules import EDGE_CAP_DEFAULT, watch_decision
from ufc_mentions.kalshi_client import KalshiClient, TopOfBook
from ufc_mentions.payload_validation import validate_payload
from ufc_mentions.build_dashboard_data import (
    build_kalshi_cards, complete_fighter_identities, flatten_card_fights,
    merge_scheduled_cards, parse_event_fighters,
)
from ufc_mentions.fight_series import is_fight_mention_event
from ufc_mentions.kalshi_mentions import event_date_from_ticker
from scripts.data.fetch_upcoming_events import fetch_schedule

DATA_PREFIX = "window.UFC_MENTION_DASHBOARD_DATA = "
MAX_AGE_SECONDS = 10 * 60


def parse_data_js(text: str) -> dict:
    body = text.strip()
    if body.startswith(DATA_PREFIX):
        body = body[len(DATA_PREFIX):]
    return json.loads(body.rstrip().rstrip(";"))


def serialize_data_js(payload: dict) -> str:
    return f"{DATA_PREFIX}{json.dumps(payload, indent=2, sort_keys=True)};\n"


def is_fresh(generated_at: str, now_iso: str, *, max_age_seconds: int = MAX_AGE_SECONDS) -> bool:
    try:
        generated = datetime.fromisoformat(str(generated_at))
        now = datetime.fromisoformat(now_iso)
    except ValueError:
        return False
    if generated.tzinfo is None or now.tzinfo is None:
        return False
    return 0 <= (now - generated).total_seconds() < max_age_seconds


def refresh_catalog(payload: dict, client: KalshiClient, now_iso: str) -> dict:
    """Cloud discovery can list markets, but cannot train models or record paper fills."""
    schedule = fetch_schedule()
    upcoming = schedule["events"]
    events = [event for event in client.scan_events(require_complete=True)
              if is_fight_mention_event(event)
              and (event_date_from_ticker(event.get("event_ticker", "")) or now_iso[:10]) >= now_iso[:10]]
    previous = {row.get("ticker"): row for row in payload.get("kalshi") or []}
    rows = []
    for event in events:
        event_date = event_date_from_ticker(event.get("event_ticker", "")) or ""
        if event_date and event_date < now_iso[:10]:
            continue
        markets = client.get_markets(event_ticker=event["event_ticker"])
        for market in markets:
            if market.get("status") not in {"open", "active"} or market.get("result"):
                continue
            ticker = market.get("ticker", "")
            fighter_1, fighter_2 = parse_event_fighters(market.get("title") or event.get("title", ""))
            row = dict(previous.get(ticker) or {})
            row.update({
                "ticker": ticker, "event_ticker": event["event_ticker"],
                "series_ticker": event.get("series_ticker", ""), "event_date": event_date,
                "event_title": event.get("title", ""), "fighter_1": fighter_1, "fighter_2": fighter_2,
                "phrase": (market.get("custom_strike") or {}).get("Word") or market.get("yes_sub_title") or "",
                "rules_primary": market.get("rules_primary", ""),
                "market_status": market.get("status", ""), "market_result": market.get("result", ""),
                "market_close_time": market.get("close_time", ""), "paper_eligible": False,
                "paper_block_reason": "collector_offline",
            })
            if not previous.get(ticker):
                row.update(model_probability=None, probability_source="unavailable", watch=False,
                           status="unavailable", context_note="This market has not been priced by the local model yet.")
            rows.append(row)
    payload["kalshi"] = rows
    payload.setdefault("kalshi_meta", {}).update(events=events, source="cloud")
    payload["upcoming_events"] = upcoming
    payload["kalshi_cards"] = merge_scheduled_cards(build_kalshi_cards({"events": events}, rows, set()), upcoming)
    payload["kalshi_events"] = flatten_card_fights(payload["kalshi_cards"])
    payload["fighters"] = complete_fighter_identities(payload.get("fighters") or {}, payload.get("tapes") or [], payload.get("trades") or [], rows)
    status = payload.setdefault("live_status", {})
    status.update(state="ready", source="cloud", checked_at=now_iso, refresh_seconds=600,
                  market_count=len(rows), paper_enabled=False, paper_mode="paper", error="")
    payload["generated_at"] = now_iso
    payload["refreshed_by"] = "cloud"
    return payload


def repriced_payload(
    payload: dict, fetch_book: Callable[[str], TopOfBook | None], now_iso: str,
) -> tuple[dict, int]:
    rows = payload.get("kalshi") or []
    updated = 0
    watch_count = 0
    quote_failures = 0
    for row in rows:
        model_p = row.get("model_probability")
        try:
            book = fetch_book(row.get("ticker", ""))
        except Exception:
            book = None
        if book is None:
            quote_failures += 1
        if book is None or book.yes_ask is None or book.no_ask is None:
            row.update(watch=False, yes_bid=None, yes_ask=None, no_bid=None, no_ask=None,
                       edge=None, side_price=None, block_reason="no_prices", paper_eligible=False)
            continue
        row.update(yes_bid=book.yes_bid, yes_ask=book.yes_ask, no_bid=book.no_bid, no_ask=book.no_ask,
                   quote_timestamp=now_iso, snapshot_timestamp=now_iso, paper_eligible=False)
        if model_p is None or row.get("probability_source") != "fight_context_model":
            row.update(watch=False, side="", side_price=None, edge=None, block_reason="no_model")
            updated += 1
            continue
        fee_buffer = row.get("fee_buffer") or 0.02
        data_buffer = row.get("data_buffer") or 0.0
        edge_cap = row.get("edge_cap") or EDGE_CAP_DEFAULT
        yes_edge = model_p - book.yes_ask
        no_edge = (1.0 - model_p) - book.no_ask
        side, side_price, edge = max(
            [("yes", book.yes_ask, yes_edge), ("no", book.no_ask, no_edge)],
            key=lambda candidate: candidate[2],
        )
        spread = book.spread
        hurdle = None if spread is None else spread + fee_buffer + data_buffer
        watch, block_reason = watch_decision(
            edge=edge,
            hurdle=hurdle,
            side=side,
            model_ready=True,
            require_model=True,
            trusted=bool(row.get("trust_ok", True)),
            edge_cap=edge_cap,
        )
        row.update({
            "yes_bid": book.yes_bid,
            "yes_ask": book.yes_ask,
            "no_bid": book.no_bid,
            "no_ask": book.no_ask,
            "spread": spread,
            "hurdle": hurdle,
            "yes_edge": yes_edge,
            "no_edge": no_edge,
            "side": side,
            "side_price": side_price,
            "edge": edge,
            "watch": watch,
            "block_reason": block_reason or "",
            "gap_blocked": block_reason == "big_gap",
            "snapshot_timestamp": now_iso,
        })
        updated += 1
    for row in rows:
        if row.get("watch"):
            watch_count += 1
    if updated:
        summary = payload.setdefault("summary", {})
        summary["kalshi_snapshot_timestamp"] = now_iso
        summary["kalshi_watch_count"] = watch_count
        payload["generated_at"] = now_iso
        payload["refreshed_by"] = "cloud"
    status = payload.setdefault("live_status", {})
    status.update(source="cloud", paper_enabled=False, market_count=len(rows))
    status.update(state="error" if quote_failures else "ready",
                  error=f"Could not refresh {quote_failures} market quote(s)." if quote_failures else "")
    status["quotes_at"] = max((row.get("quote_timestamp") or "" for row in rows), default="")
    payload["kalshi_cards"] = merge_scheduled_cards(
        build_kalshi_cards(payload.get("kalshi_meta") or {}, rows, set()),
        payload.get("upcoming_events") or [],
    )
    payload["kalshi_events"] = flatten_card_fights(payload["kalshi_cards"])
    return payload, updated


def main() -> int:
    parser = argparse.ArgumentParser(description="Reprice the published site from the cloud.")
    parser.add_argument("--site-dir", required=True, help="checkout of the gh-pages branch")
    args = parser.parse_args()

    data_path = Path(args.site_dir) / "data.js"
    if not data_path.exists():
        print("no data.js in site dir; nothing to do")
        return 0
    payload = parse_data_js(data_path.read_text(encoding="utf-8"))
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if is_fresh(str(payload.get("generated_at", "")), now_iso):
        print("published data is fresh; the Mac is handling it")
        return 0
    client = KalshiClient()
    payload = refresh_catalog(payload, client, now_iso)
    payload, updated = repriced_payload(payload, client.get_orderbook, now_iso)
    validate_payload(payload)
    data_path.write_text(serialize_data_js(payload), encoding="utf-8")
    print(f"repriced {updated} markets; data.js rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
