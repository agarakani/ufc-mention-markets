import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.data.build_fighter_directory import (
    build_directory,
    league_rates,
    marquee_score,
    style_tags,
)


def fight(f1, f2, date, **mentions):
    row = {
        "fighter_1": f1,
        "fighter_2": f2,
        "fighter_1_nickname": mentions.pop("nick1", ""),
        "fighter_2_nickname": mentions.pop("nick2", ""),
        "event_date": date,
        "event_title": mentions.pop("event_title", "UFC Fight Night"),
        "mention_submission": "False",
        "mention_knockout": "False",
        "mention_ko": "False",
        "mention_tko": "False",
        "mention_knocked_out": "False",
        "mention_split_decision": "False",
        "mention_unanimous_decision": "False",
        "mention_choke": "False",
    }
    for key, value in mentions.items():
        row[f"mention_{key}"] = "True" if value else "False"
    return row


def joined(f1, f2, date, r_fighter, b_fighter, **kw):
    return {
        "fighter_1": f1,
        "fighter_2": f2,
        "event_date": date,
        "kaggle_R_fighter": r_fighter,
        "kaggle_B_fighter": b_fighter,
        "kaggle_R_wins": kw.get("r_wins", ""),
        "kaggle_R_losses": kw.get("r_losses", ""),
        "kaggle_R_Stance": kw.get("r_stance", ""),
        "kaggle_R_Height_cms": kw.get("r_height", ""),
        "kaggle_R_Reach_cms": kw.get("r_reach", ""),
        "kaggle_B_wins": kw.get("b_wins", ""),
        "kaggle_B_losses": kw.get("b_losses", ""),
        "kaggle_B_Stance": kw.get("b_stance", ""),
        "kaggle_B_Height_cms": kw.get("b_height", ""),
        "kaggle_B_Reach_cms": kw.get("b_reach", ""),
        "kaggle_title_bout": kw.get("title_bout", "False"),
    }


def test_directory_aggregates_fighter_rates():
    fights = [
        fight("Ada Lovelace", "Grace Hopper", "2024-01-01", submission=True, choke=True),
        fight("Ada Lovelace", "Alan Turing", "2024-06-01", submission=True),
        fight("Grace Hopper", "Alan Turing", "2024-03-01", knockout=True),
    ]
    directory = {row["name"]: row for row in build_directory(fights, [])}
    ada = directory["Ada Lovelace"]
    assert ada["n_fights"] == 2
    assert ada["rate_submission"] == 1.0
    assert ada["last_event_date"] == "2024-06-01"
    grace = directory["Grace Hopper"]
    assert grace["n_fights"] == 2
    assert grace["rate_submission"] == 0.5
    assert grace["rate_knockout_family"] == 0.5


def test_style_tags_thresholds():
    league = {"rate_submission": 0.5, "rate_knockout_family": 0.4, "rate_decision_family": 0.1}
    assert style_tags({"rate_submission": 0.9, "rate_knockout_family": 0.4, "rate_decision_family": 0.1}, league) == ["GRAPPLER"]
    assert style_tags({"rate_submission": 0.6, "rate_knockout_family": 0.4, "rate_decision_family": 0.1}, league) == []
    tags = style_tags(
        {"rate_submission": 0.9, "rate_knockout_family": 0.9, "rate_decision_family": 0.6},
        league,
    )
    assert len(tags) == 2
    assert "DISTANCE FIGHTER" in tags


def test_nickname_and_stats_from_latest_fight():
    fights = [
        fight("Ada Lovelace", "Grace Hopper", "2024-01-01", nick1="The Analyst"),
        fight("Alan Turing", "Ada Lovelace", "2024-06-01", nick2="The Analyst"),
    ]
    rows = [
        joined("Ada Lovelace", "Grace Hopper", "2024-01-01", "Ada Lovelace", "Grace Hopper",
               r_wins="10", r_losses="2", r_stance="Orthodox", r_height="170", r_reach="175"),
        joined("Alan Turing", "Ada Lovelace", "2024-06-01", "Alan Turing", "Ada Lovelace",
               b_wins="11", b_losses="2", b_stance="Southpaw", b_height="170", b_reach="175"),
    ]
    directory = {row["name"]: row for row in build_directory(fights, rows)}
    ada = directory["Ada Lovelace"]
    assert ada["nickname"] == "The Analyst"
    assert ada["record_wins"] == 11
    assert ada["stance"] == "Southpaw"
    assert ada["height_cms"] == 170.0


def test_marquee_score_counts_fights_and_titles():
    assert marquee_score(n_fights=3, title_bouts=0) == 3
    assert marquee_score(n_fights=30, title_bouts=2) == 15 + 20


def test_league_rates_are_means():
    fights = [
        fight("A B", "C D", "2024-01-01", submission=True),
        fight("E F", "G H", "2024-01-02"),
    ]
    league = league_rates(fights)
    assert league["rate_submission"] == 0.5
