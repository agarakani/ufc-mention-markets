import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions import build_dashboard_data as bdd


DIRECTORY_ROW = {
    "name": "Max Holloway", "name_lower": "max holloway", "nickname": "Blessed",
    "n_fights": "23", "last_event_date": "2025-04-12", "record_wins": "22",
    "record_losses": "8", "stance": "Orthodox", "height_cms": "180.34",
    "reach_cms": "175.26", "rate_submission": "0.3", "rate_knockout_family": "0.6",
    "rate_decision_family": "0.4", "rate_choke": "0.2",
    "style_tags": "FINISHER", "marquee_score": "95",
}


def write_directory(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(DIRECTORY_ROW.keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_build_fighter_identities(tmp_path, monkeypatch):
    directory = tmp_path / "fighter_directory.csv"
    write_directory(directory, [DIRECTORY_ROW])
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", directory)

    fighters = bdd.build_fighter_identities()
    ident = fighters["max holloway"]
    assert ident["nickname"] == "Blessed"
    assert ident["marquee_score"] == 95
    assert ident["style_tags"] == ["FINISHER"]
    assert ident["record"] == "22-8"


def test_missing_directory_is_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", tmp_path / "missing.csv")
    assert bdd.build_fighter_identities() == {}


def test_fight_marquee_score(tmp_path, monkeypatch):
    directory = tmp_path / "fighter_directory.csv"
    other = dict(DIRECTORY_ROW, name="Ilia Topuria", name_lower="ilia topuria",
                 nickname="El Matador", marquee_score="26")
    write_directory(directory, [DIRECTORY_ROW, other])
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", directory)

    fighters = bdd.build_fighter_identities()
    assert bdd.fight_marquee_score("Max Holloway", "Ilia Topuria", fighters) == 121
    assert bdd.fight_marquee_score("Max Holloway", "Unknown Person", fighters) == 95
    assert bdd.fight_marquee_score("", "", fighters) == 0


def test_cards_take_their_name_from_the_schedule():
    cards = [{
        "card_id": "KXFIGHTMENTION:2026-07-25",
        "card_title": "UFC card · 2026-07-25",
        "event_date": "2026-07-25",
        "has_kalshi_card_title": False,
    }]
    upcoming = [{
        "date": "2026-07-25",
        "name": "UFC Fight Night: Ankalaev vs. Guskov",
        "venue": "Etihad Arena",
        "location": "Abu Dhabi, United Arab Emirates",
    }]
    bdd.name_cards_from_schedule(cards, upcoming)
    assert cards[0]["card_title"] == "UFC Fight Night: Ankalaev vs. Guskov"
    assert cards[0]["card_venue"] == "Etihad Arena"


def test_kalshi_card_title_is_never_overwritten():
    cards = [{
        "card_title": "Kalshi's own name",
        "event_date": "2026-07-25",
        "has_kalshi_card_title": True,
    }]
    upcoming = [{"date": "2026-07-25", "name": "UFC Fight Night: Ankalaev vs. Guskov"}]
    bdd.name_cards_from_schedule(cards, upcoming)
    assert cards[0]["card_title"] == "Kalshi's own name"


def test_price_tracks_downsample_and_cache(tmp_path, monkeypatch):
    import csv as _csv
    history = tmp_path / "history.csv"
    with history.open("w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=["ticker", "yes_ask", "model_probability"])
        writer.writeheader()
        for i in range(200):
            writer.writerow({"ticker": "A", "yes_ask": 0.10 + i * 0.001, "model_probability": 0.2})
        for i in range(2):
            writer.writerow({"ticker": "B", "yes_ask": 0.4, "model_probability": 0.4})

    bdd._spark_cache["key"] = None
    tracks = bdd.build_price_tracks({"A", "B"}, history)
    assert "A" in tracks
    assert len(tracks["A"]) <= bdd.SPARK_POINTS
    # the newest point is always kept, whatever the sampling stride
    assert tracks["A"][-1][0] == round(0.10 + 199 * 0.001, 4)
    # a market with almost no history gets no line rather than a misleading one
    assert "B" not in tracks


def test_price_tracks_ignore_unlisted_markets(tmp_path):
    import csv as _csv
    history = tmp_path / "history.csv"
    with history.open("w", newline="", encoding="utf-8") as fh:
        writer = _csv.DictWriter(fh, fieldnames=["ticker", "yes_ask", "model_probability"])
        writer.writeheader()
        for i in range(10):
            writer.writerow({"ticker": "OLD", "yes_ask": 0.3, "model_probability": 0.3})
    bdd._spark_cache["key"] = None
    assert bdd.build_price_tracks({"LIVE"}, history) == {}
