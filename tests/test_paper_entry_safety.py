from datetime import datetime, timezone

import pytest

from scripts.tracking.live_paper import entry_block_reason, record_live_entries, read_csv, resolution_from_market

NOW = datetime(2099, 9, 19, 20, 0, tzinfo=timezone.utc)


def candidate(**updates):
    row = {
        "ticker": "TEST-WORD", "event_ticker": "TEST", "event_date": "2099-09-19",
        "fighter_1": "One", "fighter_2": "Two", "watch": "yes", "status": "ok",
        "market_status": "active", "market_result": "", "side": "no",
        "no_ask": "0.40", "yes_ask": "0.65", "side_price": "0.40",
        "quote_timestamp": "2099-09-19T19:59:45+00:00",
        "entry_deadline": "2099-09-19T21:00:00+00:00",
        "entry_deadline_source": "https://example.test/official-start",
    }
    row.update(updates)
    return row


def test_fresh_prefight_quote_is_eligible():
    assert entry_block_reason(candidate(), NOW) == ""


@pytest.mark.parametrize("updates,reason", [
    ({"entry_deadline": "2099-09-19T20:00:00+00:00"}, "card_started"),
    ({"entry_deadline": "", "entry_deadline_source": ""}, "start_time_unverified"),
    ({"entry_deadline_source": ""}, "start_time_unverified"),
    ({"quote_timestamp": "2099-09-19T19:55:00+00:00"}, "stale_quote"),
    ({"quote_timestamp": ""}, "stale_quote"),
    ({"quote_timestamp": "2099-09-19T20:01:00+00:00"}, "stale_quote"),
    ({"market_status": "closed"}, "market_not_open"),
    ({"market_result": "yes"}, "market_resolved"),
    ({"no_ask": ""}, "no_buy_price"),
    ({"no_ask": "nan"}, "no_buy_price"),
    ({"side_price": "0.30"}, "price_changed"),
    ({"status": "error"}, "model_unavailable"),
])
def test_unsafe_entry_is_blocked(updates, reason):
    assert entry_block_reason(candidate(**updates), NOW) == reason


def test_future_date_without_verified_start_time_is_blocked():
    row = candidate(entry_deadline="", entry_deadline_source="", event_date="2099-09-20")
    assert entry_block_reason(row, NOW) == "start_time_unverified"


def test_repeated_and_concurrent_candidates_do_not_duplicate_or_reprice_entry(tmp_path):
    row = candidate()
    first = record_live_entries([row, row], card="test", out_root=tmp_path, entered_at=NOW.isoformat())
    row.update(no_ask="0.41", side_price="0.41")
    second = record_live_entries([row], card="test", out_root=tmp_path, entered_at=NOW.isoformat())
    assert first["new_entries"] == 1 and second["new_entries"] == 0
    positions = read_csv(tmp_path / "test" / "paper_positions.csv")
    assert len(positions) == 1 and positions[0]["paper_price"] == "0.4"


def test_started_fight_cannot_create_trade_even_with_watch_flag(tmp_path):
    result = record_live_entries(
        [candidate(entry_deadline="2099-09-19T19:59:00+00:00")],
        card="test", out_root=tmp_path, entered_at=NOW.isoformat(),
    )
    assert result["new_entries"] == 0


def test_closed_market_waiting_for_result_is_pending_even_when_model_status_is_ok():
    resolution = resolution_from_market(candidate(market_status="closed"), None, NOW.isoformat())
    assert resolution["resolution_status"] == "pending"
