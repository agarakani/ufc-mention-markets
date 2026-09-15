import copy
import json

import pytest

from scripts.live import publish_site
from ufc_mentions.payload_validation import load_payload, validate_payload


@pytest.fixture
def payload():
    return {
        "fighters": {"a one": {"name": "A One"}, "b two": {"name": "B Two"}},
        "tapes": [{"card": "26JUL11", "markets": [{
            "ticker": "E-WORD", "fighter_1": "A One", "fighter_2": "B Two",
            "result": None,
        }]}],
        "trades": [
            {"ticker": "E-WORD", "fighter_1": "A One", "fighter_2": "B Two",
             "event_date": "2026-07-11", "pnl": 0.3},
            {"ticker": "F-WORD", "fighter_1": "A One", "fighter_2": "B Two",
             "event_date": "2026-07-18", "pnl": -0.1},
        ],
        "performance": {
            "official_trades": 2,
            "equity": [
                {"date": "2026-07-11", "card_pnl": 0.3, "cumulative_pnl": 0.3},
                {"date": "2026-07-18", "card_pnl": -0.1, "cumulative_pnl": 0.2},
            ],
        },
    }


def test_valid_payload_is_not_modified(payload):
    before = copy.deepcopy(payload)
    validate_payload(payload)
    assert payload == before


@pytest.mark.parametrize("field", ["fighter_1", "fighter_2"])
def test_tape_market_must_name_both_fighters(payload, field):
    payload["tapes"][0]["markets"][0][field] = "  "
    with pytest.raises(ValueError, match=f"E-WORD.*{field}"):
        validate_payload(payload)


@pytest.mark.parametrize("source", ["tape", "trade"])
def test_referenced_fighter_must_have_an_identity(payload, source):
    row = payload["tapes"][0]["markets"][0] if source == "tape" else payload["trades"][0]
    row["fighter_1"] = "Missing Fighter"
    with pytest.raises(ValueError, match="Missing Fighter.*fighters"):
        validate_payload(payload)


@pytest.mark.parametrize("field", ["card_pnl", "cumulative_pnl"])
def test_ledger_must_match_each_equity_amount(payload, field):
    payload["performance"]["equity"][0][field] += 0.01
    with pytest.raises(ValueError, match=f"2026-07-11.*{field}"):
        validate_payload(payload)


def test_ledger_total_matching_does_not_hide_per_night_errors(payload):
    payload["performance"]["equity"][0]["card_pnl"] += 0.1
    payload["performance"]["equity"][1]["card_pnl"] -= 0.1
    with pytest.raises(ValueError, match="card_pnl"):
        validate_payload(payload)


def test_ledger_count_must_match(payload):
    payload["performance"]["official_trades"] += 1
    with pytest.raises(ValueError, match="official_trades"):
        validate_payload(payload)


def test_equity_dates_must_match_ledger(payload):
    payload["performance"]["equity"].pop()
    with pytest.raises(ValueError, match="equity dates"):
        validate_payload(payload)


def test_equity_must_be_in_date_order(payload):
    payload["performance"]["equity"].reverse()
    with pytest.raises(ValueError, match="equity dates"):
        validate_payload(payload)


def test_empty_history_and_pending_result_are_valid(payload):
    payload["trades"] = []
    payload["performance"] = {"equity": [], "official_trades": 0}
    validate_payload(payload)
    payload["tapes"] = []
    payload["fighters"] = {}
    validate_payload(payload)


def test_rounded_equity_allows_only_four_decimal_rounding(payload):
    payload["trades"][0]["pnl"] = 0.30004
    validate_payload(payload)
    payload["trades"][0]["pnl"] = 0.3001
    with pytest.raises(ValueError, match="card_pnl"):
        validate_payload(payload)


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), "not a number"])
def test_nonfinite_or_invalid_money_is_rejected(payload, amount):
    payload["trades"][0]["pnl"] = amount
    with pytest.raises(ValueError, match="pnl"):
        validate_payload(payload)


def test_load_data_file_without_executing_javascript(tmp_path, payload):
    source = tmp_path / "data.js"
    source.write_text("window.UFC_MENTION_DASHBOARD_DATA = " + json.dumps(payload) + ";\n")
    assert load_payload(source) == payload
    source.write_text("window.UFC_MENTION_DASHBOARD_DATA = {}; alert('unexpected');")
    with pytest.raises(ValueError):
        load_payload(source)


def test_stage_rejects_bad_payload_before_copying_anything(tmp_path, monkeypatch, payload):
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    payload["tapes"][0]["markets"][0]["fighter_1"] = ""
    (dashboard / "data.js").write_text("window.UFC_MENTION_DASHBOARD_DATA = " + json.dumps(payload) + ";")
    monkeypatch.setattr(publish_site, "DASHBOARD", dashboard)
    site = tmp_path / "site"
    site.mkdir()
    with pytest.raises(ValueError, match="fighter_1"):
        publish_site.stage_site(site)
    assert list(site.iterdir()) == []


def test_stage_uses_exact_validated_bytes_when_recorder_changes_source(tmp_path, monkeypatch, payload):
    dashboard = tmp_path / "dashboard"
    dashboard.mkdir()
    original = ("window.UFC_MENTION_DASHBOARD_DATA = " + json.dumps(payload) + ";\r\n").encode()
    (dashboard / "data.js").write_bytes(original)
    (dashboard / "index.html").write_text(publish_site.LOADER_LINE)
    (dashboard / "app.js").write_text("// Test application\n")
    monkeypatch.setattr(publish_site, "DASHBOARD", dashboard)
    monkeypatch.setattr(publish_site, "SITE_FILES", ["app.js", "data.js"])
    copyfile = publish_site.shutil.copyfile

    def copy_with_concurrent_refresh(source, target):
        if source.name == "app.js":
            (dashboard / "data.js").write_text("window.UFC_MENTION_DASHBOARD_DATA = {};")
        return copyfile(source, target)

    monkeypatch.setattr(publish_site.shutil, "copyfile", copy_with_concurrent_refresh)
    site = tmp_path / "site"
    site.mkdir()
    publish_site.stage_site(site)
    assert (site / "data.js").read_bytes() == original
    assert load_payload(site / "data.js") == payload
