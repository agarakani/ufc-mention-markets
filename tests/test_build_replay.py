"""Tapes: one per recorded card, outcomes and trades joined, frames capped."""

import csv
import json
from pathlib import Path

from scripts.data import build_replay as br


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _history(tmp_path: Path) -> Path:
    rows = []
    # two cards, two tickers each, six snapshots per card
    for card, day in (("26JUL11", "2026-07-11"), ("26JUL18", "2026-07-18")):
        for i in range(6):
            stamp = f"{day}T0{i}:00:00+00:00"
            for suffix, ask in (("AAA-CHOK", 0.30 + i * 0.05), ("AAA-LIGH", 0.80 - i * 0.05)):
                rows.append({
                    "snapshot_timestamp": stamp,
                    "event_ticker": f"KXFIGHTMENTION-{card}AAA",
                    "ticker": f"KXFIGHTMENTION-{card}{suffix}",
                    "phrase": "Choke" if suffix.endswith("CHOK") else "Lights Out",
                    "yes_bid": round(ask - 0.02, 3),
                    "yes_ask": round(ask, 3),
                    "model_probability": 0.42,
                    "fighter_1": "",
                    "fighter_2": "",
                    "event_date": "",
                })
    path = tmp_path / "history.csv"
    _write_csv(path, rows)
    return path


def _labels(tmp_path: Path) -> Path:
    path = tmp_path / "labels.csv"
    _write_csv(path, [
        {"event_date": "2026-07-18", "event_ticker": "KXFIGHTMENTION-26JUL18AAA",
         "ticker": "KXFIGHTMENTION-26JUL18AAA-CHOK", "fighter_1": "A One", "fighter_2": "B Two",
         "phrase": "Choke", "forms": "", "outcome": "yes"},
        {"event_date": "2026-07-18", "event_ticker": "KXFIGHTMENTION-26JUL18AAA",
         "ticker": "KXFIGHTMENTION-26JUL18AAA-LIGH", "fighter_1": "A One", "fighter_2": "B Two",
         "phrase": "Lights Out", "forms": "", "outcome": "no"},
    ])
    return path


def _trades(tmp_path: Path) -> Path:
    path = tmp_path / "trades.csv"
    _write_csv(path, [
        {"cohort": "official", "ticker": "KXFIGHTMENTION-26JUL18AAA-CHOK", "event_ticker": "x",
         "event_date": "2026-07-18", "phrase": "Choke", "entered_at": "2026-07-17T00:00:00+00:00",
         "side": "yes", "price": "0.35", "model_probability": "0.42", "edge": "0.07", "hurdle": "0.1",
         "data_risk": "False", "result": "yes", "won": "True", "pnl": "0.65"},
        {"cohort": "lean", "ticker": "KXFIGHTMENTION-26JUL18AAA-LIGH", "event_ticker": "x",
         "event_date": "2026-07-18", "phrase": "Lights Out", "entered_at": "2026-07-17T00:00:00+00:00",
         "side": "no", "price": "0.3", "model_probability": "0.42", "edge": "0.1", "hurdle": "0.1",
         "data_risk": "False", "result": "no", "won": "True", "pnl": "0.7"},
    ])
    return path


def test_every_card_gets_a_tape_oldest_first(tmp_path):
    out = br.build_all(frames=4, history_path=_history(tmp_path),
                       labels_path=_labels(tmp_path), trades_path=_trades(tmp_path))
    cards = out["cards"]
    assert [c["card"] for c in cards] == ["26JUL11", "26JUL18"]
    assert [c["event_date"] for c in cards] == ["2026-07-11", "2026-07-18"]
    for card in cards:
        assert card["frames"] == 4
        assert len(card["stamps"]) == 4
        assert card["stamps"][-1].startswith(card["event_date"] + "T05")  # last frame kept
        assert card["fights"] == 1
        for market in card["markets"]:
            assert len(market["ask"]) == 4 and None not in market["ask"]


def test_outcomes_trades_and_names_are_joined(tmp_path):
    out = br.build_all(frames=4, history_path=_history(tmp_path),
                       labels_path=_labels(tmp_path), trades_path=_trades(tmp_path))
    jul18 = out["cards"][1]
    by_ticker = {m["ticker"]: m for m in jul18["markets"]}
    choke = by_ticker["KXFIGHTMENTION-26JUL18AAA-CHOK"]
    lights = by_ticker["KXFIGHTMENTION-26JUL18AAA-LIGH"]
    assert choke["result"] == "yes" and lights["result"] == "no"
    assert choke["fighter_1"] == "A One" and choke["fighter_2"] == "B Two"
    assert choke["trade"]["side"] == "yes" and choke["trade"]["won"] is True
    assert choke["trade"]["pnl"] == 0.65
    assert lights["trade"] is None  # lean cohort is not an official trade
    assert jul18["said"] == 1 and jul18["settled"] == 2 and jul18["trades"] == 1
    # the older card has no labels yet: result stays None, never a guess
    assert all(m["result"] is None for m in out["cards"][0]["markets"])


def test_single_card_build_returns_the_most_recent(tmp_path):
    tape = br.build(frames=4, history_path=_history(tmp_path))
    assert tape["card"] == "26JUL18"


def test_missing_history_is_soft(tmp_path):
    assert br.build_all(history_path=tmp_path / "nope.csv") == {"cards": []}
    assert br.build(history_path=tmp_path / "nope.csv") == {}
