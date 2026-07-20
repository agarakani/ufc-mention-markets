import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.build_dashboard_data import build_performance


TRADES = [
    {"cohort": "official", "event_date": "2026-06-20", "phrase": "Choke", "won": "False", "pnl": "-0.2"},
    {"cohort": "official", "event_date": "2026-06-20", "phrase": "Choke", "won": "True", "pnl": "0.5"},
    {"cohort": "official", "event_date": "2026-07-11", "phrase": "Blood", "won": "True", "pnl": "0.44"},
    {"cohort": "lean", "event_date": "2026-07-11", "phrase": "Blood", "won": "True", "pnl": "0.9"},
]


def test_performance_payload_from_trades():
    perf = build_performance(TRADES)
    equity = perf["equity"]
    assert [e["date"] for e in equity] == ["2026-06-20", "2026-07-11"]
    assert equity[0]["card_pnl"] == 0.3
    assert equity[1]["cumulative_pnl"] == 0.74
    phrases = {p["phrase"]: p for p in perf["by_phrase"]}
    assert phrases["Choke"]["trades"] == 2
    assert phrases["Choke"]["wins"] == 1
    assert phrases["Blood"]["trades"] == 1
    assert perf["official_trades"] == 3


def test_performance_empty():
    perf = build_performance([])
    assert perf == {"equity": [], "by_phrase": [], "official_trades": 0}
