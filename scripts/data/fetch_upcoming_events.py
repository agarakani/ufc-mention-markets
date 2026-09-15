#!/usr/bin/env python3
"""Read upcoming cards and preliminary start times from UFC's own schedule."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_URL = "https://www.ufc.com/events"
USER_AGENT = "ufc-mention-markets/1.0 (local research dashboard)"
OUT_DEFAULT = ROOT / "data" / "processed" / "upcoming_events.json"
EASTERN = ZoneInfo("America/New_York")
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
         "meta", "param", "source", "track", "wbr"}


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str]
    children: list[_Element | str] = field(default_factory=list)


class _Page(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root", {})
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Element(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _nodes(node: _Element, *, tag: str = "", cls: str = "") -> Iterator[_Element]:
    if (not tag or node.tag == tag) and (not cls or cls in node.attrs.get("class", "").split()):
        yield node
    for child in node.children:
        if isinstance(child, _Element):
            yield from _nodes(child, tag=tag, cls=cls)


def _text(node: _Element | None) -> str:
    if node is None or node.tag in {"script", "style", "svg"}:
        return ""
    text = " ".join(child if isinstance(child, str) else _text(child) for child in node.children)
    return re.sub(r"\s+([,.;:])", r"\1", " ".join(text.split()))


def _first(node: _Element, *, tag: str = "", cls: str = "") -> _Element | None:
    return next(_nodes(node, tag=tag, cls=cls), None)


def _timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), timezone.utc) if value else None
    except (ValueError, OverflowError, OSError):
        return None


def _official_url(href: str, base: str, path: str) -> str:
    url = urljoin(base, href)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"www.ufc.com", "ufc.com"}:
        return ""
    return url if parsed.path.startswith(path) else ""


def parse_schedule(html: str) -> list[dict]:
    """Extract dated schedule entries, retaining provenance and unknown starts."""
    root = _Page(html).root
    events = []
    seen = set()
    for article in _nodes(root, tag="article", cls="c-card-event--result"):
        headline = _first(article, cls="c-card-event--result__headline")
        timing = _first(article, cls="c-card-event--result__date")
        link = _first(headline, tag="a") if headline else None
        url = _official_url(link.attrs.get("href", ""), SCHEDULE_URL, "/event/") if link else ""
        main = _timestamp(timing.attrs.get("data-main-card-timestamp", "")) if timing else None
        if not url or not main or url in seen:
            continue
        seen.add(url)
        prelims = [_timestamp(timing.attrs.get(key, "")) for key in
                   ("data-early-card-timestamp", "data-prelims-card-timestamp")]
        deadlines = [stamp for stamp in prelims if stamp and stamp <= main]
        deadline = min(deadlines).isoformat() if deadlines else None
        location = _first(article, cls="c-card-event--result__location")
        events.append({
            "name": _text(headline),
            "date": main.astimezone(EASTERN).date().isoformat(),
            "venue": _text(_first(location, tag="h5")) if location else "",
            "location": _text(_first(location, cls="address")) if location else "",
            "source_url": url,
            "entry_deadline": deadline,
            "entry_deadline_source": SCHEDULE_URL if deadline else None,
        })
    return events


def parse_event_page(html: str, source_url: str) -> dict:
    """Use UFC's Unix timestamps, not its local-clock <time datetime> labels."""
    root = _Page(html).root
    title = _text(_first(root, tag="h1"))
    matchup = _text(_first(root, cls="c-hero__headline"))
    name = f"{title}: {matchup}" if title and matchup and matchup not in title else title or matchup
    deadlines = []
    for timing in _nodes(root, cls="c-event-fight-card-broadcaster__time"):
        if not any(_first(timing, cls=cls) for cls in
                   ("field--name-fight-card-time-early", "field--name-fight-card-time-prelims")):
            continue
        stamp = _timestamp(timing.attrs.get("data-timestamp", ""))
        if stamp:
            deadlines.append(stamp)
    update_urls = []
    for link in _nodes(root, tag="a"):
        if "update" not in _text(link).lower():
            continue
        url = _official_url(link.attrs.get("href", ""), source_url, "/news/")
        if url and url not in update_urls:
            update_urls.append(url)
    deadline = min(deadlines).isoformat() if deadlines else None
    return {
        "name": name,
        "entry_deadline": deadline,
        "entry_deadline_source": source_url if deadline else None,
        "update_urls": update_urls,
    }


def parse_update_deadline(html: str, event_name: str, event_date: str) -> str | None:
    """Read an explicit early-prelim time only for the matching card and date."""
    root = _Page(html).root
    headline = _text(_first(root, tag="h1"))
    identity = re.sub(r"[^a-z0-9]", "", event_name.lower())
    if not identity or identity not in re.sub(r"[^a-z0-9]", "", headline.lower()):
        return None
    day = date.fromisoformat(event_date)
    text = _text(root)
    date_pattern = rf"\b{day.strftime('%B')}\s+{day.day},?\s+{day.year}\b"
    if not re.search(date_pattern, text, re.I):
        return None
    time_pattern = r"\bearly\s+prelims\b[^\d.!?,;:/]{0,80}?\b(?:at|begin|start|kickoff)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s*(ET|EDT|EST)\b"
    starts = []
    for match in re.finditer(time_pattern, text, re.I):
        hour, minute, period, zone = match.groups()
        hour, minute = int(hour), int(minute or 0)
        if not 1 <= hour <= 12 or not 0 <= minute < 60:
            continue
        hour = hour % 12 + (12 if period.lower() == "pm" else 0)
        tz = EASTERN if zone.upper() == "ET" else timezone(timedelta(hours=-4 if zone.upper() == "EDT" else -5))
        starts.append(datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz))
    return min(starts).astimezone(timezone.utc).isoformat() if starts else None


def future_only(events: list[dict], today: date) -> list[dict]:
    return sorted((event for event in events if event.get("date", "") >= today.isoformat()),
                  key=lambda event: (event["date"], event.get("name", "")))


def default_fetch_html(url: str) -> str:
    response = requests.get(url, timeout=20, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def fetch_schedule(
    *,
    fetch_html: Callable[[str], str] = default_fetch_html,
    today: date | None = None,
) -> dict:
    """Fetch a sourced schedule without writing files or creating fight markets."""
    today = today or datetime.now(timezone.utc).date()
    url = SCHEDULE_URL
    seen_pages = set()
    events = {}
    while url:
        if url in seen_pages:
            raise ValueError("UFC schedule repeated a pagination link")
        seen_pages.add(url)
        html = fetch_html(url)
        page_events = future_only(parse_schedule(html), today)
        for event in page_events:
            events[event["source_url"]] = event
        root = _Page(html).root
        next_link = next((link for link in _nodes(root, tag="a")
                          if "next" in link.attrs.get("rel", "").split()), None)
        url = _official_url(next_link.attrs.get("href", ""), url, "/events") if next_link and page_events else ""
        if len(seen_pages) >= 20 and url:
            raise ValueError("UFC schedule pagination did not finish")
    if not events:
        raise ValueError("no upcoming UFC events parsed")

    warnings = []
    for event in events.values():
        source_url = event["source_url"]
        try:
            detail = parse_event_page(fetch_html(source_url), source_url)
        except Exception as exc:
            event.update(entry_deadline=None, entry_deadline_source=None,
                         entry_deadline_note="Could not verify the event's current start time.")
            warnings.append(f"{source_url}: {exc}")
            continue
        if detail["name"]:
            event["name"] = detail["name"]
        starts = [(event["entry_deadline"], event["entry_deadline_source"]),
                  (detail["entry_deadline"], detail["entry_deadline_source"])]
        update_failed = False
        for update_url in detail["update_urls"]:
            try:
                stamp = parse_update_deadline(fetch_html(update_url), event["name"], event["date"])
                if stamp:
                    starts.append((stamp, update_url))
            except Exception as exc:
                update_failed = True
                warnings.append(f"{update_url}: {exc}")
        candidates = [(stamp, source) for stamp, source in starts if stamp]
        if update_failed:
            event.update(entry_deadline=None, entry_deadline_source=None,
                         entry_deadline_note="Could not verify a linked schedule update.")
        elif candidates:
            stamp, source = min(candidates, key=lambda pair: pair[0])
            event.update(entry_deadline=stamp, entry_deadline_source=source)
            if len({value for value, _ in candidates}) > 1:
                event["entry_deadline_note"] = "Official start times differ; using the earlier verified time."
        else:
            event.update(entry_deadline=None, entry_deadline_source=None,
                         entry_deadline_note="Preliminary start time not published.")
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": SCHEDULE_URL,
        "events": future_only(list(events.values()), today),
    }
    if warnings:
        payload["warnings"] = warnings
    return payload


def refresh(
    out_path: Path,
    *,
    fetch_html: Callable[[str], str] = default_fetch_html,
    today: date | None = None,
) -> str:
    out_path = Path(out_path)
    try:
        payload = fetch_schedule(fetch_html=fetch_html, today=today)
    except Exception as exc:
        prefix = "kept previous upcoming events" if out_path.exists() else "no upcoming events available"
        return f"{prefix} ({exc})"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=out_path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2)
        temporary = Path(handle.name)
    try:
        temporary.replace(out_path)
    finally:
        temporary.unlink(missing_ok=True)
    return f"{len(payload['events'])} upcoming events saved"


def main() -> None:
    print(refresh(OUT_DEFAULT))


if __name__ == "__main__":
    main()
