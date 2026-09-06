from ufc_mentions import build_dashboard_data as bdd


def test_official_trades_named_and_newest_first():
    trades = [
        {"cohort": "official", "ticker": "T1", "event_ticker": "E1", "event_date": "2026-07-11",
         "phrase": "Choke", "entered_at": "2026-07-09T00:00:00+00:00", "side": "no", "price": "0.56",
         "model_probability": "0.25", "edge": "0.18", "result": "no", "won": "True", "pnl": "0.44"},
        {"cohort": "lean", "ticker": "T2", "event_ticker": "E1", "event_date": "2026-07-11",
         "phrase": "Choke", "entered_at": "2026-07-09T00:00:00+00:00", "side": "no", "price": "0.5",
         "model_probability": "0.25", "edge": "0.1", "result": "no", "won": "True", "pnl": "0.5"},
        {"cohort": "official", "ticker": "T3", "event_ticker": "E2", "event_date": "2026-07-18",
         "phrase": "Slip", "entered_at": "2026-07-16T00:00:00+00:00", "side": "yes", "price": "0.3",
         "model_probability": "0.5", "edge": "0.2", "result": "no", "won": "False", "pnl": "-0.3"},
    ]
    labels = [{"event_ticker": "E1", "fighter_1": "A", "fighter_2": "B"}]
    out = bdd.build_trades(trades, labels)
    assert [t["ticker"] for t in out] == ["T3", "T1"]
    assert out[1]["fighter_1"] == "A" and out[1]["fighter_2"] == "B"
    assert out[0]["fighter_1"] == "" and out[0]["won"] is False and out[0]["pnl"] == -0.3
    assert out[1]["won"] is True and out[1]["price"] == 0.56


def test_no_trades_is_soft():
    assert bdd.build_trades([], []) == []
