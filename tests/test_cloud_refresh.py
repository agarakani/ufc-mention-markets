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
