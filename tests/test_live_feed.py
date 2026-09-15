import copy

import pytest

from ufc_mentions import build_dashboard_data as bd


def test_schedule_card_without_markets_keeps_real_name_and_no_invented_fights():
    schedule = [{"name": "UFC 999: Example", "date": "2099-09-19", "source_url": "https://example.test/schedule"}]
    cards = bd.merge_scheduled_cards([], schedule)
    assert len(cards) == 1
    assert cards[0]["card_title"] == "UFC 999: Example"
    assert cards[0]["fights"] == []
    assert cards[0]["phrase_count"] == 0
    assert cards[0]["odds_status"] == "awaiting_markets"
    assert cards[0]["source_url"] == schedule[0]["source_url"]


def test_schedule_does_not_duplicate_card_already_on_kalshi():
    cards = [{"card_id": "KX:2099-09-19", "event_date": "2099-09-19", "card_title": "UFC card", "fights": [{"event_ticker": "E"}]}]
    merged = bd.merge_scheduled_cards(cards, [{"name": "UFC 999", "date": "2099-09-19"}])
    assert len(merged) == 1
    assert merged[0]["card_title"] == "UFC 999"
    assert merged[0]["fights"] == [{"event_ticker": "E"}]


def test_presentation_survives_both_scheduled_and_kalshi_card_paths(monkeypatch):
    presentation = {"source_url": "https://www.ufc.com/event/example",
                    "artwork": {"url": "https://ufc.com/images/card.jpg", "alt": "Official art"},
                    "headliners": [{"name": "Fighter One"}, {"name": "Fighter Two"}],
                    "bout_label": "Flyweight Title Bout", "is_title_bout": True}
    monkeypatch.setattr(bd, "read_json", lambda path: {"events": [{"name": "UFC 999", "date": "2099-09-19", "presentation": presentation}]})
    upcoming = bd.build_upcoming_events(today="2099-09-01")
    assert upcoming[0]["presentation"] == presentation
    scheduled = bd.merge_scheduled_cards([], upcoming)
    assert scheduled[0]["presentation"] == presentation
    assert scheduled[0]["fights"] == []
    existing = [{"card_id": "KX:2099-09-19", "event_date": "2099-09-19", "card_title": "UFC 999", "has_kalshi_card_title": True, "fights": [{"event_ticker": "E"}]}]
    merged = bd.merge_scheduled_cards(existing, upcoming)
    assert merged[0]["presentation"] == presentation
    assert merged[0]["fights"] == existing[0]["fights"]


def test_cloud_schedule_keeps_official_art_when_no_mentions_are_listed(monkeypatch):
    from types import SimpleNamespace

    from scripts.live import cloud_refresh

    presentation = {"source_url": "https://www.ufc.com/event/example",
                    "artwork": {"url": "https://ufc.com/images/card.jpg", "alt": "Official art"}}
    schedule = {"events": [{"name": "UFC 999", "date": "2099-09-19", "presentation": presentation}]}
    monkeypatch.setattr(cloud_refresh, "fetch_schedule", lambda: schedule)
    client = SimpleNamespace(scan_events=lambda **kwargs: [])
    payload = {"kalshi": [], "fighters": {}, "tapes": [], "trades": []}
    result = cloud_refresh.refresh_catalog(payload, client, "2099-09-15T00:00:00Z")
    assert result["upcoming_events"][0]["presentation"] == presentation
    assert result["kalshi_cards"][0]["presentation"] == presentation
    assert result["kalshi_cards"][0]["fights"] == []


def test_missing_identity_adds_only_recorded_name_never_guessed_stats():
    fighters = {"known": {"name": "Known", "wins": 3}}
    before = copy.deepcopy(fighters)
    tapes = [{"markets": [{"fighter_1": "Known", "fighter_2": "New Fighter"}]}]
    out = bd.complete_fighter_identities(fighters, tapes, [], [{"fighter_1": "Live Fighter", "fighter_2": "Known"}])
    assert out["new fighter"] == {"name": "New Fighter", "identity_status": "name_only", "source": "market_record"}
    assert "wins" not in out["live fighter"] and "n_fights" not in out["live fighter"]
    assert out["known"] == before["known"]
    assert fighters == before


def test_live_fighters_are_not_removed_when_old_nights_exist():
    identities = {name: {"name": name} for name in ["old", "new", "unused"]}
    out = bd.trim_fighters(identities, [{"markets": [{"fighter_1": "old"}]}], [], [{"fighter_1": "new"}])
    assert set(out) == {"old", "new"}


def test_data_write_leaves_previous_feed_intact_until_replacement(tmp_path, monkeypatch):
    path = tmp_path / "data.js"
    path.write_text("previous valid feed")
    replacements = []

    def fail_replace(source, target):
        assert path.read_text() == "previous valid feed"
        assert source.read_text().startswith("window.UFC_MENTION_DASHBOARD_DATA = ")
        replacements.append(target)
        raise OSError("replacement failed")

    monkeypatch.setattr(type(path), "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        bd.write_data(path, {"generated_at": "test"})
    assert replacements == [path]
    assert path.read_text() == "previous valid feed"
    assert list(tmp_path.iterdir()) == [path]
