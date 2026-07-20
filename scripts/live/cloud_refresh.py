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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.entry_rules import EDGE_CAP_DEFAULT, watch_decision
from ufc_mentions.kalshi_client import KalshiClient

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
    return (now - generated).total_seconds() < max_age_seconds


def repriced_payload(payload: dict, fetch_book, now_iso: str) -> tuple[dict, int]:
    rows = payload.get("kalshi") or []
    updated = 0
    watch_count = 0
    for row in rows:
        model_p = row.get("model_probability")
        if model_p is None or row.get("probability_source") != "fight_context_model":
            continue
        try:
            book = fetch_book(row.get("ticker", ""))
        except Exception:
            book = None
        if book is None or book.yes_ask is None or book.no_ask is None:
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
    if not payload.get("kalshi"):
        print("no live markets in the published data; nothing to reprice")
        return 0

    client = KalshiClient()
    payload, updated = repriced_payload(payload, client.get_orderbook, now_iso)
    if not updated:
        print("no markets could be repriced")
        return 0
    data_path.write_text(serialize_data_js(payload), encoding="utf-8")
    print(f"repriced {updated} markets; data.js rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
