#!/usr/bin/env python3
"""Small stdlib Oddpool API client.

This project uses Oddpool only as a market-data source. It does not trade.

Docs:
  Authentication: X-API-Key header
  Search markets: /search/markets
  Historical top-of-book:
    /historical/polymarket/top-of-book
    /historical/kalshi/top-of-book
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


BASE_URL = "https://api.oddpool.com"


class OddpoolError(RuntimeError):
    pass


def _key_from_dotenv() -> str:
    path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            if name.strip() == "ODDPOOL_API_KEY":
                return value.strip().strip("'\"")
    return ""


def api_key() -> str:
    key = os.environ.get("ODDPOOL_API_KEY", "").strip() or _key_from_dotenv()
    if not key:
        raise OddpoolError(
            "Missing ODDPOOL_API_KEY. Create one in Oddpool account settings, then run:\n"
            "  export ODDPOOL_API_KEY='oddpool_...'\n"
            "or copy .env.example to .env and put the key there."
        )
    return key


def _clean_params(params: dict) -> dict:
    return {k: v for k, v in params.items() if v not in (None, "", [])}


def request_json(path: str, params: dict | None = None, *, sleep_s: float = 0.0):
    query = urllib.parse.urlencode(_clean_params(params or {}))
    url = f"{BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": api_key(),
            "Accept": "application/json",
            "User-Agent": "ufc-mention-markets/0.1",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OddpoolError(f"Oddpool HTTP {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise OddpoolError(f"Oddpool request failed for {url}: {exc}") from exc

    if sleep_s:
        time.sleep(sleep_s)
    return json.loads(payload)


def parse_time_ms(value: str | int | None) -> int | None:
    """Accept Unix-ms strings/ints or ISO timestamps and return Unix ms."""
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    raw = str(value).strip()
    if raw.isdigit():
        return int(raw)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def iso_from_ms(value) -> str:
    if value in (None, ""):
        return ""
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def next_pagination_key(payload) -> str | None:
    pagination = payload.get("pagination") if isinstance(payload, dict) else None
    if not isinstance(pagination, dict):
        return None
    for key in ("pagination_key", "next_pagination_key", "next", "next_cursor"):
        value = pagination.get(key)
        if value:
            return value
    return None


def search_markets(
    *,
    q=None,
    series_id=None,
    exchange=None,
    status="active",
    category=None,
    min_volume=None,
    min_liquidity=None,
    settled_after=None,
    settled_before=None,
    discovered_after=None,
    sort_by="volume",
    limit=100,
    max_pages=5,
):
    if not q and not series_id:
        raise OddpoolError("search_markets requires q or series_id.")
    rows = []
    offset = 0
    for _page in range(max_pages):
        batch = request_json(
            "/search/markets",
            {
                "q": q,
                "series_id": series_id,
                "exchange": exchange,
                "status": status,
                "category": category,
                "min_volume": min_volume,
                "min_liquidity": min_liquidity,
                "settled_after": settled_after,
                "settled_before": settled_before,
                "discovered_after": discovered_after,
                "sort_by": sort_by,
                "limit": limit,
                "offset": offset,
            },
            sleep_s=0.15,
        )
        if not batch:
            break
        if not isinstance(batch, list):
            raise OddpoolError(f"Expected search response list, got {type(batch).__name__}")
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return rows


def historical_top_of_book(
    *,
    exchange: str,
    market_id: str,
    asset_id: str | None = None,
    start_time=None,
    end_time=None,
    granularity="5m",
    limit=200,
    max_pages=20,
):
    exchange = exchange.lower().strip()
    if exchange not in {"polymarket", "kalshi"}:
        raise OddpoolError("exchange must be polymarket or kalshi")

    path = f"/historical/{exchange}/top-of-book"
    params = {
        "market_id": market_id,
        "asset_id": asset_id if exchange == "polymarket" else None,
        "start_time": parse_time_ms(start_time),
        "end_time": parse_time_ms(end_time),
        "granularity": granularity,
        "limit": limit,
    }

    snapshots = []
    pagination_key = None
    for _page in range(max_pages):
        if pagination_key:
            params["pagination_key"] = pagination_key
        payload = request_json(path, params, sleep_s=0.15)
        batch = payload.get("snapshots", []) if isinstance(payload, dict) else []
        if not isinstance(batch, list):
            raise OddpoolError("Expected top-of-book response with snapshots list.")
        snapshots.extend(batch)
        pagination_key = next_pagination_key(payload)
        if not pagination_key or len(batch) < limit:
            break
    return snapshots
