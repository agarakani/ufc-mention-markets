import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data.fetch_upcoming_events import (
    future_only,
    parse_scheduled_events,
    refresh,
)

WIKITEXT = """==Scheduled events==
{| id="Scheduled events" class="sortable wikitable succession-box" style="font-size:90%; "
! scope="col" | Event
! scope="col" | Date
! scope="col" | Venue
! scope="col" | Location
! scope="col" | Ref.
|-
|[[UFC Fight Night 290]]
|{{dts|2026|Oct|17}}
|[[Rogers Place]]
|[[Edmonton, Alberta]], Canada
|<ref>ignored</ref>
|-
|[[UFC Fight Night 289]]
|{{dts|2026|Sep|26}}
|[[UFC Apex|Meta Apex]]
|[[Las Vegas]], [[Nevada]], U.S.
|<ref>ignored</ref>
|-
|[[UFC 331]]
|{{dts|2026|Sep|19}}
|[[Crypto.com Arena]]
|[[Los Angeles]], [[California]], U.S.
|<ref>ignored</ref>
|}
"""


def test_parse_scheduled_events_wikitext():
    events = parse_scheduled_events(WIKITEXT)
    assert len(events) == 3
    first = events[0]
    assert first["name"] == "UFC Fight Night 290"
    assert first["date"] == "2026-10-17"
    assert first["venue"] == "Rogers Place"
    assert first["location"] == "Edmonton, Alberta, Canada"
    apex = events[1]
    assert apex["venue"] == "Meta Apex"
    assert apex["location"] == "Las Vegas, Nevada, U.S."


def test_future_only_sorted_ascending():
    events = parse_scheduled_events(WIKITEXT)
    kept = future_only(events, today=date(2026, 9, 20))
    assert [e["name"] for e in kept] == ["UFC Fight Night 289", "UFC Fight Night 290"]
    assert future_only(events, today=date(2027, 1, 1)) == []


def test_refresh_error_keeps_old_file(tmp_path):
    out = tmp_path / "upcoming_events.json"
    out.write_text(json.dumps({"events": [{"name": "OLD"}]}))

    def broken_fetch():
        raise RuntimeError("network down")

    note = refresh(out, fetch_wikitext=broken_fetch, today=date(2026, 7, 19))
    assert "kept" in note
    assert json.loads(out.read_text())["events"][0]["name"] == "OLD"


def test_refresh_writes_events(tmp_path):
    out = tmp_path / "upcoming_events.json"
    note = refresh(out, fetch_wikitext=lambda: WIKITEXT, today=date(2026, 7, 19))
    assert "3 upcoming" in note
    saved = json.loads(out.read_text())
    assert saved["events"][0]["name"] == "UFC 331"
    assert saved["fetched_at"].startswith("2026")
