import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from scripts.live import refresh_dashboard as refresh


@pytest.mark.parametrize("failure", ["quote", "schedule"])
def test_refresh_error_blocks_new_entries_but_still_settles(tmp_path, monkeypatch, failure):
    now = datetime.now(timezone.utc).isoformat()
    good = {"ticker": "GOOD", "event_date": "2099-09-19", "status": "ok",
            "quote_timestamp": now, "market_status": "active", "watch": "yes",
            "side": "yes", "yes_ask": "0.3", "side_price": "0.3"}
    bad = {"ticker": "BAD", "event_date": "2099-09-19", "status": "error",
           "error": "price request failed", "watch": "no"}
    event = {"event_ticker": "EVENT", "series_ticker": "SERIES"}
    monkeypatch.setenv("UFC_PUBLISH", "0")
    monkeypatch.setattr(refresh, "maybe_fetch_upcoming", lambda: "fresh")
    if failure == "schedule":
        def schedule_failed():
            raise RuntimeError("Official schedule unavailable")
        monkeypatch.setattr(refresh, "maybe_fetch_upcoming", schedule_failed)
        bad.update(status="ok", error="")
    monkeypatch.setattr(refresh, "build_upcoming_events", lambda: [{"date": "2099-09-19",
                        "entry_deadline": "2099-09-19T21:00:00Z", "entry_deadline_source": "https://example.test/official", "fetched_at": now}])
    monkeypatch.setattr(refresh, "discover_open_fight_events", lambda *a, **kw: [event])
    monkeypatch.setattr(refresh, "event_snapshot", lambda *a, **kw: [good, bad])
    monkeypatch.setattr(refresh, "event_metadata", lambda *a, **kw: event)
    monkeypatch.setattr(refresh, "load_phrase_trust", lambda: {})
    monkeypatch.setattr(refresh, "paper_card_groups", lambda *a: [("Test", [good, bad])])
    entries = []
    monkeypatch.setattr(refresh, "record_live_entries", lambda rows, **kw: entries.append(kw) or {})
    monkeypatch.setattr(refresh, "combine_paper_results", lambda *a: {})
    settlements = []
    monkeypatch.setattr(refresh, "settle_finished_paper_cards", lambda *a, **kw: settlements.append(kw))
    monkeypatch.setattr(refresh, "maybe_check_coverage", lambda: "")
    monkeypatch.setattr(refresh, "build_payload", lambda: {})
    monkeypatch.setattr(refresh, "write_data", lambda *a: None)

    def no_historical_work():
        raise AssertionError("Live refresh must not retrain or rewrite historical P/L")

    monkeypatch.setattr(refresh, "maybe_retrain_walkforward", no_historical_work)
    monkeypatch.setattr(refresh, "maybe_settle_money_backtest", no_historical_work)
    meta_path = tmp_path / "meta.json"
    refresh.refresh_once(SimpleNamespace(authenticated=False), None, series_ticker="SERIES",
                         event_ticker=None, fee_buffer=0.02, min_fighter_fights=15, poll_seconds=30,
                         live_path=tmp_path / "live.csv", history_path=tmp_path / "history.csv",
                         meta_path=meta_path, paper_card="auto", paper_out_root=tmp_path / "paper")
    meta = json.loads(meta_path.read_text())
    assert meta["errors"] == (["BAD: price request failed"] if failure == "quote" else ["Official schedule unavailable"])
    assert meta["paper_enabled"] is False
    assert meta["refresh_ok"] is False
    assert entries[0]["allow_entries"] is False
    assert settlements
    assert good["paper_eligible"] == "no"
    assert good["paper_block_reason"] == ("refresh_error" if failure == "quote" else "start_time_unverified")


def test_failed_schedule_fetch_does_not_advance_retry_marker(tmp_path, monkeypatch):
    from scripts.data import fetch_upcoming_events
    marker = tmp_path / "fetch-stamp"
    monkeypatch.setattr(refresh, "UPCOMING_FETCH_MARKER", marker)

    def fail(path):
        raise OSError("official schedule unavailable")

    monkeypatch.setattr(fetch_upcoming_events, "refresh", fail)
    with pytest.raises(RuntimeError, match="official schedule unavailable"):
        refresh.maybe_fetch_upcoming()
    assert not marker.exists()


def test_old_schedule_deadline_is_not_current():
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    assert not refresh.schedule_is_current({"fetched_at": "2026-08-15T00:00:00Z"}, now)
    assert not refresh.schedule_is_current({}, now)
    assert not refresh.schedule_is_current({"fetched_at": "2026-09-16T00:00:00Z"}, now)
    assert refresh.schedule_is_current({"fetched_at": "2026-09-15T00:00:00Z"}, now)
