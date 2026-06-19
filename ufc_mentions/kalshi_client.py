#!/usr/bin/env python3
"""Read-only Kalshi REST client for live mention-market data.

Authentication follows Kalshi's RSA-PSS scheme. This module intentionally
implements GET requests only; it cannot place, modify, or cancel orders.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_URL_DEFAULT = "https://api.elections.kalshi.com"
MARKETS_PATH = "/trade-api/v2/markets"
EVENTS_PATH = "/trade-api/v2/events"


class KalshiError(RuntimeError):
    pass


@dataclass(frozen=True)
class TopOfBook:
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None

    @property
    def spread(self) -> float | None:
        if self.yes_ask is None or self.no_ask is None:
            return None
        return max(0.0, self.yes_ask + self.no_ask - 1.0)


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def load_private_key(path: str | Path) -> rsa.RSAPrivateKey:
    key_path = Path(path).expanduser()
    if not key_path.is_absolute():
        key_path = PROJECT_ROOT / key_path
    try:
        data = key_path.read_bytes()
    except OSError as exc:
        raise KalshiError(f"Could not read Kalshi private key: {key_path}") from exc
    try:
        key = serialization.load_pem_private_key(data, password=None)
    except (TypeError, ValueError) as exc:
        raise KalshiError(f"Invalid unencrypted PEM private key: {key_path}") from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise KalshiError("Kalshi private key must be RSA.")
    return key


def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
    signature = private_key.sign(
        text.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        ),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("ascii")


def _price_decimal(value, *, dollars: bool) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not dollars:
        price /= 100.0
    return price if 0 <= price <= 1 else None


def top_of_book(payload: dict) -> TopOfBook:
    book = payload.get("orderbook_fp") or payload.get("orderbook") or payload
    dollars = "yes_dollars" in book or "no_dollars" in book
    yes_levels = book.get("yes_dollars") if dollars else book.get("yes")
    no_levels = book.get("no_dollars") if dollars else book.get("no")

    def best(levels) -> float | None:
        prices = []
        for level in levels or []:
            if not isinstance(level, (list, tuple)) or not level:
                continue
            parsed = _price_decimal(level[0], dollars=dollars)
            if parsed is not None:
                prices.append(parsed)
        return max(prices) if prices else None

    yes_bid = best(yes_levels)
    no_bid = best(no_levels)
    return TopOfBook(
        yes_bid=yes_bid,
        yes_ask=None if no_bid is None else 1.0 - no_bid,
        no_bid=no_bid,
        no_ask=None if yes_bid is None else 1.0 - yes_bid,
    )


class KalshiClient:
    """Minimal read-only client with optional authenticated headers."""

    def __init__(
        self,
        key_id: str | None = None,
        private_key: rsa.RSAPrivateKey | None = None,
        private_key_path: str | Path | None = None,
        base_url: str = BASE_URL_DEFAULT,
        session: requests.Session | None = None,
    ):
        load_dotenv()
        self.key_id = (
            key_id
            or os.getenv("KALSHI_KEY_ID")
            or os.getenv("KALSHI_API_KEY_ID")
            or os.getenv("PROD_KEYID")
            or ""
        ).strip()
        key_path = (
            private_key_path
            or os.getenv("KALSHI_PRIVATE_KEY_PATH")
            or os.getenv("PROD_KEYFILE")
        )
        self.private_key = private_key or (load_private_key(key_path) if key_path else None)
        if bool(self.key_id) != bool(self.private_key):
            raise KalshiError(
                "Kalshi credentials are incomplete. Set both KALSHI_KEY_ID and "
                "KALSHI_PRIVATE_KEY_PATH, or neither for public market-data reads."
            )
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self._last_read = 0.0

    @property
    def authenticated(self) -> bool:
        return bool(self.key_id and self.private_key)

    def request_headers(self, method: str, path: str, timestamp_ms: int | None = None) -> dict[str, str]:
        if not self.authenticated:
            return {"Accept": "application/json", "User-Agent": "ufc-mention-markets/0.3"}
        timestamp = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        sign_path = path.split("?", 1)[0]
        signature = sign_pss_text(self.private_key, timestamp + method.upper() + sign_path)
        return {
            "Accept": "application/json",
            "User-Agent": "ufc-mention-markets/0.3",
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        elapsed = time.monotonic() - self._last_read
        if elapsed < 0.06:
            time.sleep(0.06 - elapsed)
        last_error = None
        for attempt in range(4):
            try:
                response = self.session.get(
                    self.base_url + path,
                    params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                    headers=self.request_headers("GET", path),
                    timeout=30,
                )
                self._last_read = time.monotonic()
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = KalshiError(
                        f"Kalshi HTTP {response.status_code}: {response.text[:300]}"
                    )
                    if attempt < 3:
                        time.sleep(0.5 * (2**attempt))
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise KalshiError(f"Expected JSON object from {path}.")
                return payload
            except (requests.RequestException, ValueError, KalshiError) as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(0.5 * (2**attempt))
                    continue
        raise KalshiError(f"Kalshi GET failed for {path}: {last_error}") from last_error

    def get_markets(
        self,
        *,
        event_ticker: str | None = None,
        series_ticker: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        rows = []
        cursor = None
        while True:
            payload = self.get(MARKETS_PATH, {
                "limit": 1000,
                "cursor": cursor,
                "event_ticker": event_ticker,
                "series_ticker": series_ticker,
                "status": status,
                "mve_filter": "exclude",
            })
            rows.extend(payload.get("markets") or [])
            cursor = payload.get("cursor")
            if not cursor:
                return rows

    def get_events(self, *, series_ticker: str, status: str | None = None) -> list[dict]:
        rows = []
        cursor = None
        while True:
            payload = self.get(EVENTS_PATH, {
                "limit": 200,
                "cursor": cursor,
                "series_ticker": series_ticker,
                "status": status,
            })
            rows.extend(payload.get("events") or [])
            cursor = payload.get("cursor")
            if not cursor:
                return rows

    def get_orderbook(self, ticker: str) -> TopOfBook:
        payload = self.get(f"{MARKETS_PATH}/{ticker}/orderbook")
        return top_of_book(payload)

    def find_event(
        self,
        fighter_1: str,
        fighter_2: str,
        event_date: str | None = None,
        series_ticker: str = "KXFIGHTMENTION",
    ) -> str:
        wanted = [re.sub(r"[^a-z0-9]+", "", name.lower().split()[-1]) for name in (fighter_1, fighter_2)]
        date_token = ""
        if event_date:
            date_token = datetime.strptime(event_date, "%Y-%m-%d").strftime("%y%b%d").upper()
        matches = []
        for event in self.get_events(series_ticker=series_ticker, status="open"):
            haystack = re.sub(r"[^a-z0-9]+", "", f"{event.get('title', '')} {event.get('sub_title', '')}".lower())
            ticker = event.get("event_ticker", "")
            if all(token in haystack for token in wanted) and (not date_token or date_token in ticker):
                matches.append(ticker)
        if len(matches) != 1:
            raise KalshiError(
                f"Expected one matching {series_ticker} event, found {len(matches)}: {matches[:8]}"
            )
        return matches[0]


def _money(value: float | None) -> str:
    return "--" if value is None else f"{value * 100:.1f}c"


def main() -> None:
    parser = argparse.ArgumentParser(description="Print live Kalshi mention markets and order-book asks.")
    parser.add_argument("--event-ticker")
    parser.add_argument("--fighter-1")
    parser.add_argument("--fighter-2")
    parser.add_argument("--date", help="fight date as YYYY-MM-DD for event discovery")
    parser.add_argument("--series", default="KXFIGHTMENTION")
    args = parser.parse_args()

    client = KalshiClient()
    event_ticker = args.event_ticker
    if not event_ticker:
        if not args.fighter_1 or not args.fighter_2:
            parser.error("use --event-ticker or provide --fighter-1 and --fighter-2")
        event_ticker = client.find_event(args.fighter_1, args.fighter_2, args.date, args.series)
    markets = client.get_markets(event_ticker=event_ticker)
    print(f"{event_ticker}: {len(markets)} markets ({'authenticated' if client.authenticated else 'public read'})")
    for market in markets:
        book = client.get_orderbook(market["ticker"])
        phrase = (market.get("custom_strike") or {}).get("Word") or market.get("yes_sub_title") or ""
        print(f"{market['ticker']:<47} YES {_money(book.yes_ask):>7}  NO {_money(book.no_ask):>7}  {phrase}")
        print(f"  rules: {market.get('rules_primary', '')}")


if __name__ == "__main__":
    main()
