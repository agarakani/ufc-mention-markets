import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live import cloud_refresh
from scripts.live.cloud_refresh import is_fresh, repriced_payload
from ufc_mentions.kalshi_client import TopOfBook

NOW = "2026-07-19T22:00:00+00:00"


def payload_with_row(**overrides):
    row = {
        "ticker": "KXFIGHTMENTION-26JUL25ANKGUS-CHOKE",
        "event_ticker": "KXFIGHTMENTION-26JUL25ANKGUS",
        "phrase": "Choke",
        "model_probability": 0.30,
        "probability_source": "fight_context_model",
        "fee_buffer": 0.02,
        "data_buffer": 0.0,
        "data_risk": False,
        "trust_ok": True,
        "edge_cap": 0.15,
        "yes_ask": 0.5,
        "no_ask": 0.55,
        "watch": False,
        "snapshot_timestamp": "2026-07-19T20:00:00+00:00",
    }
    row.update(overrides)
    return {
        "generated_at": "2026-07-19T20:00:00+00:00",
        "summary": {"kalshi_snapshot_timestamp": "2026-07-19T20:00:00+00:00", "kalshi_watch_count": 0},
        "kalshi": [row],
    }


def test_repriced_payload_recomputes_edges_and_watch():
    payload = payload_with_row()
    # NO side: 1 - 0.30 = 0.70 vs no_ask 0.60 -> edge 0.10; spread 0.05; hurdle 0.07
    book = TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)
    out, updated = repriced_payload(payload, lambda ticker: book, NOW)
    assert updated == 1
    row = out["kalshi"][0]
    assert row["yes_ask"] == 0.40
    assert row["side"] == "no"
    assert abs(row["edge"] - 0.10) < 1e-9
    assert row["watch"] is True
    assert row["snapshot_timestamp"] == NOW
    assert out["summary"]["kalshi_watch_count"] == 1
    assert out["refreshed_by"] == "cloud"
    assert out["generated_at"] == NOW


def test_repriced_payload_skips_missing_books_and_history_rows():
    payload = payload_with_row(probability_source="history", model_probability=None)
    out, updated = repriced_payload(payload, lambda ticker: None, NOW)
    assert updated == 0
    assert out["kalshi"][0]["snapshot_timestamp"] == "2026-07-19T20:00:00+00:00"


def test_big_gap_stays_blocked():
    payload = payload_with_row(model_probability=0.05)
    # NO: 0.95 - 0.60 = 0.35 edge > cap 0.15 -> gap blocked, not watch
    book = TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)
    out, _ = repriced_payload(payload, lambda ticker: book, NOW)
    row = out["kalshi"][0]
    assert row["watch"] is False
    assert row["block_reason"] == "big_gap"
    assert row["gap_blocked"] is True


def test_is_fresh():
    assert is_fresh("2026-07-19T21:55:00+00:00", NOW, max_age_seconds=600)
    assert not is_fresh("2026-07-19T21:40:00+00:00", NOW, max_age_seconds=600)
    assert not is_fresh("", NOW, max_age_seconds=600)


@pytest.fixture
def published_site(tmp_path, monkeypatch):
    payload = payload_with_row()
    payload.update({
        "generated_at": "2000-01-01T00:00:00+00:00",
        "tapes": [], "trades": [], "fighters": {},
        "performance": {"equity": [], "official_trades": 0},
    })
    data = tmp_path / "data.js"
    data.write_text(cloud_refresh.serialize_data_js(payload))
    monkeypatch.setattr(sys, "argv", ["cloud_refresh.py", "--site-dir", str(tmp_path)])
    book = TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)
    monkeypatch.setattr(cloud_refresh, "KalshiClient", lambda: SimpleNamespace(get_orderbook=lambda ticker: book))
    monkeypatch.setattr(cloud_refresh, "refresh_catalog", lambda payload, client, now_iso: payload)
    return data


def test_cloud_publish_keeps_file_unchanged_when_input_is_invalid(published_site):
    payload = cloud_refresh.parse_data_js(published_site.read_text())
    payload["performance"]["official_trades"] = 10
    published_site.write_text(cloud_refresh.serialize_data_js(payload))
    before = published_site.read_bytes()
    with pytest.raises(ValueError, match="official_trades"):
        cloud_refresh.main()
    assert published_site.read_bytes() == before


def test_cloud_publish_validates_candidate_not_only_input(published_site, monkeypatch):
    before = published_site.read_bytes()

    def bad_candidate(payload, fetch_book, now_iso):
        payload["performance"]["official_trades"] = 10
        return payload, 1

    monkeypatch.setattr(cloud_refresh, "repriced_payload", bad_candidate)
    with pytest.raises(ValueError, match="official_trades"):
        cloud_refresh.main()
    assert published_site.read_bytes() == before


def test_cloud_publish_writes_valid_candidate(published_site):
    assert cloud_refresh.main() == 0
    payload = cloud_refresh.parse_data_js(published_site.read_text())
    assert payload["kalshi"][0]["yes_ask"] == 0.40
    assert payload["refreshed_by"] == "cloud"
    assert payload["performance"] == {"equity": [], "official_trades": 0}


def test_cloud_can_discover_new_markets_without_inventing_model_predictions(monkeypatch):
    schedule = {"events": [{"name": "UFC 999", "date": "2026-09-19", "source_url": "https://example.test"}]}
    monkeypatch.setattr(cloud_refresh, "fetch_schedule", lambda: schedule)
    event = {"event_ticker": "KXFIGHTMENTION-26SEP19ONETWO", "series_ticker": "KXFIGHTMENTION",
             "title": "What will announcers say during One vs Two UFC Fight?"}
    market = {"ticker": "KXFIGHTMENTION-26SEP19ONETWO-CHOK", "status": "active", "yes_sub_title": "Choke"}
    client = SimpleNamespace(scan_events=lambda **kwargs: [event], get_markets=lambda **kwargs: [market])
    payload = {"kalshi": [], "fighters": {}, "tapes": [], "trades": []}
    out = cloud_refresh.refresh_catalog(payload, client, "2026-09-15T00:00:00Z")
    assert out["kalshi_cards"][0]["card_title"] == "UFC 999"
    assert out["kalshi"][0]["model_probability"] is None
    assert out["kalshi"][0]["watch"] is False
    assert out["fighters"]["one"]["name"] == "One"
    assert out["live_status"]["source"] == "cloud"
    assert out["live_status"]["paper_enabled"] is False


def test_unmodeled_market_still_gets_real_buy_prices():
    payload = payload_with_row(model_probability=None, probability_source="unavailable")
    book = TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)
    out, updated = repriced_payload(payload, lambda ticker: book, NOW)
    assert updated == 1 and out["kalshi"][0]["yes_ask"] == 0.40
    assert out["kalshi"][0]["model_probability"] is None
    assert out["kalshi"][0]["watch"] is False


def test_missing_live_book_cannot_keep_an_old_watch_call():
    payload = payload_with_row(watch=True)
    out, _ = repriced_payload(payload, lambda ticker: None, NOW)
    assert out["kalshi"][0]["watch"] is False
    assert out["kalshi"][0]["yes_ask"] is None


def test_cloud_card_totals_follow_new_quotes_and_do_not_fake_collector_heartbeat():
    payload = payload_with_row(event_date="2026-07-25", fighter_1="One", fighter_2="Two")
    payload["live_status"] = {"collector_checked_at": "2026-07-18T00:00:00Z", "paper_enabled": True}
    payload["kalshi_meta"] = {"events": []}
    payload["upcoming_events"] = [{"name": "UFC Test", "date": "2026-07-25"}]
    book = TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)
    out, _ = repriced_payload(payload, lambda ticker: book, NOW)
    assert out["kalshi_cards"][0]["watch_count"] == 1
    assert out["kalshi_cards"][0]["priced_count"] == 1
    assert out["live_status"]["collector_checked_at"] == "2026-07-18T00:00:00Z"
    assert out["live_status"]["paper_enabled"] is False


@pytest.mark.parametrize("failed_tickers", [{"BAD"}, {"BAD", "GOOD"}])
def test_cloud_quote_failures_are_visible_not_reported_as_ready(failed_tickers):
    payload = payload_with_row(ticker="BAD")
    payload["kalshi"].append(dict(payload["kalshi"][0], ticker="GOOD"))
    payload["live_status"] = {"state": "ready", "error": ""}

    def fetch(ticker):
        if ticker in failed_tickers:
            raise OSError("price service unavailable")
        return TopOfBook(yes_bid=0.35, yes_ask=0.40, no_bid=0.55, no_ask=0.60)

    out, _ = repriced_payload(payload, fetch, NOW)
    assert out["live_status"]["state"] == "error"
    assert str(len(failed_tickers)) in out["live_status"]["error"]
    for row in out["kalshi"]:
        if row["ticker"] in failed_tickers:
            assert row["yes_ask"] is None and row["watch"] is False
