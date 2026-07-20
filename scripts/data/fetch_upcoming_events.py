#!/usr/bin/env python3
"""Fetch the scheduled UFC events table from Wikipedia into a local JSON cache."""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "ufc-mention-markets/1.0 (local research dashboard)"
OUT_DEFAULT = ROOT / "data" / "processed" / "upcoming_events.json"

MONTHS = {name.lower(): i for i, name in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}
MONTHS.update({name.lower(): i for i, name in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)})

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
DTS = re.compile(r"\{\{dts\|([^}]+)\}\}", re.IGNORECASE)


def strip_links(text: str) -> str:
    return LINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), str(text or ""))


def clean_cell(text: str) -> str:
    text = REF.sub("", str(text or ""))
    text = strip_links(text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,")
    return text.strip()


def parse_dts(cell: str) -> str:
    """{{dts|2026|Oct|17}} or {{dts|2026|10|17}} -> ISO date. Order is Y|M|D."""
    match = DTS.search(str(cell or ""))
    if not match:
        return ""
    parts = [p.strip() for p in match.group(1).split("|") if "=" not in p and p.strip()]
    if len(parts) < 3:
        return ""
    year_text, month_text, day_text = parts[0], parts[1], parts[2]
    if not re.fullmatch(r"\d{4}", year_text) or not re.fullmatch(r"\d{1,2}", day_text):
        return ""
    month = MONTHS.get(month_text.lower()) if not month_text.isdigit() else int(month_text)
    if not month:
        return ""
    try:
        return date(int(year_text), month, int(day_text)).isoformat()
    except ValueError:
        return ""


def parse_scheduled_events(wikitext: str) -> list[dict]:
    events = []
    rows = re.split(r"^\|-.*$", str(wikitext or ""), flags=re.MULTILINE)
    for row in rows:
        cells = [line[1:].strip() for line in row.splitlines()
                 if line.startswith("|") and not line.startswith("|}")]
        if len(cells) < 4:
            continue
        name = clean_cell(cells[0])
        event_date = parse_dts(cells[1])
        if not name or not event_date:
            continue
        events.append({
            "name": name,
            "date": event_date,
            "venue": clean_cell(cells[2]),
            "location": clean_cell(cells[3]),
        })
    return events


def future_only(events: list[dict], today: date) -> list[dict]:
    kept = [e for e in events if e.get("date", "") >= today.isoformat()]
    return sorted(kept, key=lambda e: e["date"])


def default_fetch_wikitext() -> str:
    import requests

    for attempt in range(3):
        response = requests.get(API, params={
            "action": "parse", "page": "List_of_UFC_events",
            "prop": "wikitext", "format": "json", "section": 3,
        }, timeout=15, headers={"User-Agent": USER_AGENT})
        if response.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()["parse"]["wikitext"]["*"]
    response.raise_for_status()


def refresh(out_path: Path, *, fetch_wikitext=default_fetch_wikitext, today: date | None = None) -> str:
    out_path = Path(out_path)
    today = today or datetime.now(timezone.utc).date()
    try:
        wikitext = fetch_wikitext()
        events = future_only(parse_scheduled_events(wikitext), today)
        if not events:
            raise ValueError("no scheduled events parsed")
    except Exception as exc:
        if out_path.exists():
            return f"kept previous upcoming events ({exc})"
        return f"no upcoming events available ({exc})"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "events": events,
    }, indent=2), encoding="utf-8")
    return f"{len(events)} upcoming events saved"


def main():
    print(refresh(OUT_DEFAULT))


if __name__ == "__main__":
    main()
