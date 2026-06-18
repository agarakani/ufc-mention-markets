#!/usr/bin/env python3
"""Fetch official Polymarket token and resolution metadata for mention markets.

The output is intentionally separate from Oddpool prices:

* Polymarket identifies the YES/NO token IDs and the winning token.
* Oddpool supplies historical executable quotes for those token IDs.

No outcome is inferred from a last trade price.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CLASSIFIED_DEFAULT = Path("market_data/classified_markets.csv")
OUT_DEFAULT = Path("market_data/polymarket_metadata.csv")
GAMMA_URL = "https://gamma-api.polymarket.com/markets"
CLOB_URL = "https://clob.polymarket.com/clob-markets"

OUT_FIELDS = [
    "market_id",
    "question",
    "slug",
    "yes_asset_id",
    "no_asset_id",
    "resolved_yes",
    "resolution_source",
    "market_open_iso",
    "event_start_iso",
    "market_close_iso",
    "closed",
    "fees_enabled",
    "fetch_status",
    "fetch_error",
]


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def parse_json_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def request_json(url: str, *, retries: int = 3):
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ufc-mention-markets/0.2"},
    )
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(0.5 * (2**attempt))
    raise RuntimeError(f"request failed for {url}: {last_error}")


def fetch_gamma_market(condition_id: str) -> dict:
    # Gamma defaults to closed=false, so settled markets need an explicit query.
    for closed in (True, False):
        query = urllib.parse.urlencode({
            "condition_ids": condition_id,
            "closed": str(closed).lower(),
            "limit": 1,
        })
        payload = request_json(f"{GAMMA_URL}?{query}")
        if isinstance(payload, list) and payload:
            return payload[0]
    raise RuntimeError("Gamma returned no market in closed or active results")


def fetch_clob_market(condition_id: str) -> dict:
    return request_json(f"{CLOB_URL}/{condition_id}")


def token_map(gamma: dict, clob: dict) -> dict[str, dict]:
    mapped = {}
    for token in clob.get("tokens", []) if isinstance(clob, dict) else []:
        outcome = str(token.get("outcome") or "").strip().lower()
        if outcome in {"yes", "no"}:
            mapped[outcome] = token

    outcomes = [str(value).strip().lower() for value in parse_json_list(gamma.get("outcomes"))]
    token_ids = [str(value) for value in parse_json_list(gamma.get("clobTokenIds"))]
    for outcome, token_id in zip(outcomes, token_ids):
        if outcome in {"yes", "no"} and outcome not in mapped:
            mapped[outcome] = {"token_id": token_id}
    return mapped


def extract_metadata(condition_id: str, gamma: dict, clob: dict) -> dict:
    tokens = token_map(gamma, clob)
    yes = tokens.get("yes", {})
    no = tokens.get("no", {})

    resolved_yes = ""
    resolution_source = ""
    if yes.get("winner") is True:
        resolved_yes = "True"
        resolution_source = "polymarket_clob_winner"
    elif no.get("winner") is True:
        resolved_yes = "False"
        resolution_source = "polymarket_clob_winner"

    events = gamma.get("events") if isinstance(gamma.get("events"), list) else []
    event = events[0] if events and isinstance(events[0], dict) else {}

    return {
        "market_id": condition_id,
        "question": gamma.get("question", ""),
        "slug": gamma.get("slug", ""),
        "yes_asset_id": yes.get("token_id", ""),
        "no_asset_id": no.get("token_id", ""),
        "resolved_yes": resolved_yes,
        "resolution_source": resolution_source,
        "market_open_iso": (
            gamma.get("acceptingOrdersTimestamp")
            or gamma.get("startDate")
            or gamma.get("createdAt")
            or ""
        ),
        "event_start_iso": (
            gamma.get("eventStartTime")
            or gamma.get("gameStartTime")
            or event.get("eventStartTime")
            or event.get("startTime")
            or event.get("eventDate")
            or ""
        ),
        "market_close_iso": gamma.get("closedTime") or gamma.get("endDate") or "",
        "closed": gamma.get("closed", ""),
        "fees_enabled": gamma.get("feesEnabled", ""),
        "fetch_status": "ok",
        "fetch_error": "",
    }


def eligible_market_rows(rows: list[dict]) -> list[dict]:
    unique = {}
    for row in rows:
        if (row.get("exchange") or "").lower() != "polymarket":
            continue
        if row.get("market_type") and row.get("market_type") != "mention_announcers":
            continue
        if row.get("market_complexity") and row.get("market_complexity") != "simple_binary":
            continue
        market_id = (row.get("market_id") or "").strip()
        if market_id:
            unique[market_id] = row
    return list(unique.values())


def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in OUT_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", default=str(CLASSIFIED_DEFAULT))
    parser.add_argument("--out", default=str(OUT_DEFAULT))
    parser.add_argument("--force", action="store_true", help="refetch rows already cached successfully")
    args = parser.parse_args()

    existing = {row.get("market_id"): row for row in read_csv(Path(args.out))} if Path(args.out).exists() else {}
    output = []
    for row in eligible_market_rows(read_csv(Path(args.markets))):
        market_id = row["market_id"]
        cached = existing.get(market_id, {})
        if cached.get("fetch_status") == "ok" and not args.force:
            output.append(cached)
            print(f"cached {market_id} {row.get('mapped_phrase', '')}")
            continue
        try:
            gamma = fetch_gamma_market(market_id)
            clob = fetch_clob_market(market_id)
            output.append(extract_metadata(market_id, gamma, clob))
            print(f"ok {market_id} {row.get('mapped_phrase', '')}")
        except Exception as exc:
            if cached.get("fetch_status") == "ok":
                output.append(cached)
            else:
                output.append({
                    "market_id": market_id,
                    "question": row.get("question", ""),
                    "fetch_status": "error",
                    "fetch_error": str(exc),
                })
            print(f"ERROR {market_id}: {exc}")

    write_csv(Path(args.out), output)
    resolved = sum(row.get("resolved_yes") in {"True", "False"} for row in output)
    tokenized = sum(bool(row.get("yes_asset_id") and row.get("no_asset_id")) for row in output)
    print(f"Wrote {len(output)} markets to {args.out}")
    print(f"Markets with both token IDs: {tokenized}")
    print(f"Markets with official resolution: {resolved}")


if __name__ == "__main__":
    main()
