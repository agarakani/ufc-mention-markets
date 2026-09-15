"""Replay consecutive public event pages without making network calls in CI."""

import copy
import json
from pathlib import Path

import pytest

from ufc_mentions.kalshi_client import EVENTS_PATH, KalshiClient, KalshiError


@pytest.fixture
def recorded_pages():
    path = Path(__file__).parent / "fixtures" / "kalshi_events_pages.json"
    return json.loads(path.read_text(encoding="utf-8"))["pages"]


def replay_client(monkeypatch, pages):
    # Bypass credential loading. Only scan_events and its injected GET are used.
    client = object.__new__(KalshiClient)
    calls = []

    def get(path, params):
        page = pages[len(calls)]
        calls.append((path, params))
        assert path == EVENTS_PATH
        assert {k: v for k, v in params.items() if v is not None} == page["request"]
        return copy.deepcopy(page["response"])

    monkeypatch.setattr(client, "get", get)
    return client, calls


def test_scan_follows_recorded_cursor_and_preserves_all_events(monkeypatch, recorded_pages):
    client, calls = replay_client(monkeypatch, recorded_pages)
    rows = client.scan_events(max_pages=2)
    expected = [event for page in recorded_pages for event in page["response"]["events"]]
    assert rows == expected
    assert len(rows) == 400
    assert len(calls) == 2
    assert calls[1][1]["cursor"] == recorded_pages[0]["response"]["cursor"]


def test_scan_stops_at_page_limit(monkeypatch, recorded_pages):
    client, calls = replay_client(monkeypatch, recorded_pages)
    assert client.scan_events(max_pages=1) == recorded_pages[0]["response"]["events"]
    assert len(calls) == 1


def test_scan_stops_without_a_cursor(monkeypatch, recorded_pages):
    # Deliberately synthetic termination; the recorded API still had more pages.
    recorded_pages[0]["response"]["cursor"] = ""
    client, calls = replay_client(monkeypatch, recorded_pages)
    assert client.scan_events() == recorded_pages[0]["response"]["events"]
    assert len(calls) == 1


def test_zero_page_limit_makes_no_request(monkeypatch, recorded_pages):
    client, calls = replay_client(monkeypatch, recorded_pages)
    assert client.scan_events(max_pages=0) == []
    assert calls == []


def test_complete_discovery_does_not_silently_stop_at_page_limit(monkeypatch, recorded_pages):
    client, calls = replay_client(monkeypatch, recorded_pages)
    with pytest.raises(KalshiError, match="incomplete"):
        client.scan_events(max_pages=1, require_complete=True)
    assert len(calls) == 1


def test_default_scan_includes_page_65(monkeypatch):
    client = object.__new__(KalshiClient)
    calls = []

    def get(path, params):
        calls.append(params)
        return {"events": [{"event_ticker": f"EVENT-{len(calls)}"}], "cursor": str(len(calls)) if len(calls) < 65 else ""}

    monkeypatch.setattr(client, "get", get)
    assert len(client.scan_events(require_complete=True)) == 65
