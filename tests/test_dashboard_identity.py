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
    assets = tmp_path / "fighters"
    assets.mkdir()
    (assets / "manifest.json").write_text(json.dumps({
        "max holloway": {"status": "ok", "file": "max_holloway.jpg"},
    }))
    (assets / "max_holloway.jpg").write_bytes(b"\xff\xd8fake")
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", directory)
    monkeypatch.setattr(bdd, "FIGHTER_ASSETS", assets)

    fighters = bdd.build_fighter_identities()
    ident = fighters["max holloway"]
    assert ident["photo"] == "assets/fighters/max_holloway.jpg"
    assert ident["nickname"] == "Blessed"
    assert ident["marquee_score"] == 95
    assert ident["style_tags"] == ["FINISHER"]
    assert ident["record"] == "22-8"


def test_missing_directory_is_soft(tmp_path, monkeypatch):
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", tmp_path / "missing.csv")
    monkeypatch.setattr(bdd, "FIGHTER_ASSETS", tmp_path / "missing_assets")
    assert bdd.build_fighter_identities() == {}


def test_fight_marquee_score(tmp_path, monkeypatch):
    directory = tmp_path / "fighter_directory.csv"
    other = dict(DIRECTORY_ROW, name="Ilia Topuria", name_lower="ilia topuria",
                 nickname="El Matador", marquee_score="26")
    write_directory(directory, [DIRECTORY_ROW, other])
    assets = tmp_path / "fighters"
    assets.mkdir()
    (assets / "manifest.json").write_text("{}")
    monkeypatch.setattr(bdd, "FIGHTER_DIRECTORY", directory)
    monkeypatch.setattr(bdd, "FIGHTER_ASSETS", assets)

    fighters = bdd.build_fighter_identities()
    assert bdd.fight_marquee_score("Max Holloway", "Ilia Topuria", fighters) == 121
    assert bdd.fight_marquee_score("Max Holloway", "Unknown Person", fighters) == 95
    assert bdd.fight_marquee_score("", "", fighters) == 0
