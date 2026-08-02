"""The per-phrase-group bias correction and its walk-forward gate."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ufc_mentions.kalshi_context_model import apply_group_bias, group_bias_key, load_model_config
from scripts.model.walkforward_update import fit_group_bias, group_adjusted_pairs


def test_key_is_order_and_separator_stable():
    assert group_bias_key("Blood / Bloody") == group_bias_key("Bloody | Blood")
    assert group_bias_key(group_bias_key("Blood / Bloody")) == group_bias_key("Blood / Bloody")


def test_shift_only_moves_its_own_group():
    bias = {group_bias_key("Blood"): 0.5}
    assert apply_group_bias(0.2, "Blood", bias) > 0.2
    assert apply_group_bias(0.2, "Dana", bias) == 0.2
    assert apply_group_bias(0.2, "Blood", None) == 0.2


def test_group_that_settles_high_gets_pushed_up():
    # 40 markets predicted at 20% that actually happened 50% of the time.
    rows = [(0.2, 1 if i % 2 == 0 else 0, "blood") for i in range(40)]
    bias = fit_group_bias(rows)
    assert bias["blood"] > 0
    assert apply_group_bias(0.2, "Blood", bias) > 0.2


def test_thin_group_is_ignored():
    rows = [(0.2, 1, "blood") for _ in range(4)]
    assert fit_group_bias(rows) == {}


def test_shrinkage_keeps_a_small_group_timid():
    small = fit_group_bias([(0.2, 1 if i % 2 == 0 else 0, "g") for i in range(10)])
    large = fit_group_bias([(0.2, 1 if i % 2 == 0 else 0, "g") for i in range(200)])
    assert 0 < small["g"] < large["g"]


def test_shift_is_capped():
    rows = [(0.001, 1, "g") for _ in range(400)]
    assert abs(fit_group_bias(rows)["g"]) <= 1.2


def test_adjusted_pairs_pass_through_without_bias():
    rows = [(0.3, 1, "g"), (0.4, 0, "h")]
    assert group_adjusted_pairs(rows, None) == [(0.3, 1), (0.4, 0)]


def test_config_round_trips_group_bias(tmp_path):
    import json
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"group_bias": {"blood|bloody": 0.4, "bad": "x", "huge": 99}}))
    loaded = load_model_config(path)["group_bias"]
    assert loaded == {"blood|bloody": 0.4}   # non-numeric and out-of-range dropped


def test_missing_config_has_no_bias(tmp_path):
    assert load_model_config(tmp_path / "nope.json")["group_bias"] is None


def test_calibration_bins_and_ece():
    from scripts.model.calibration_report import calibration_bins, expected_calibration_error

    # Two bands: one perfectly calibrated, one badly off.
    pairs = (
        [{"probability": 0.05, "outcome": 0} for _ in range(19)]
        + [{"probability": 0.05, "outcome": 1}]
        + [{"probability": 0.25, "outcome": 1} for _ in range(10)]
    )
    bins = calibration_bins(pairs)
    bands = {(round(b["low"], 2), round(b["high"], 2)): b for b in bins}
    low = bands[(0.0, 0.05)] if (0.0, 0.05) in bands else bands[(0.05, 0.1)]
    assert low["count"] == 20
    assert abs(low["actual_rate"] - 0.05) < 1e-9

    ece = expected_calibration_error(bins)
    assert ece is not None and ece > 0        # the 25% band went 100%
    assert expected_calibration_error([]) is None


def test_calibration_report_is_empty_without_data(tmp_path):
    from scripts.model.calibration_report import build

    report = build(tmp_path / "labels.csv", tmp_path / "history.csv")
    assert report["markets"] == 0
    assert report["ece"] is None


def test_head_to_head_scores_model_against_market():
    from scripts.model.calibration_report import head_to_head, discrimination

    # Market is right every time; model is right but less confident.
    pairs = [{"probability": 0.6, "market": 0.9, "outcome": 1, "event_date": "2026-01-01"} for _ in range(5)]
    pairs += [{"probability": 0.4, "market": 0.1, "outcome": 0, "event_date": "2026-01-01"} for _ in range(5)]
    h2h = head_to_head(pairs)
    assert h2h["markets"] == 10
    assert h2h["market_log_loss"] < h2h["model_log_loss"]
    assert h2h["cards_model_won"] == 0
    assert h2h["model_auc"] == 1.0


def test_discrimination_is_half_when_ranking_is_random():
    from scripts.model.calibration_report import discrimination

    assert discrimination([(0.5, 1), (0.5, 0)]) == 0.5
    assert discrimination([(0.9, 1), (0.1, 0)]) == 1.0
    assert discrimination([(0.9, 1)]) is None


def test_prefight_cutoff_excludes_in_fight_prices(tmp_path):
    from scripts.model.calibration_report import collect_pairs

    labels = tmp_path / "labels.csv"
    labels.write_text(
        "event_date,ticker,phrase,outcome\n2026-07-25,T1,Blood,yes\n", encoding="utf-8"
    )
    history = tmp_path / "history.csv"
    history.write_text(
        "snapshot_timestamp,ticker,model_probability,yes_ask,yes_bid\n"
        "2026-07-25T09:00:00+00:00,T1,0.20,0.25,0.15\n"
        "2026-07-25T19:00:00+00:00,T1,0.20,0.99,0.97\n",   # mid-fight, must be ignored
        encoding="utf-8",
    )
    pairs = collect_pairs(labels, history)
    assert len(pairs) == 1
    assert pairs[0]["market"] == 0.20   # the pre-fight mid, not the in-fight price


def _fake_kalshi(dates):
    class R:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.payload
    import io, json as _json
    def opener(url, timeout=None):
        if "status=settled" in url:
            events = [{"event_ticker": f"KXFIGHTMENTION-{d}XX"} for d in dates]
        else:
            events = []
        return R(io.BytesIO(_json.dumps({"events": events}).encode()))
    return opener


def test_coverage_flags_a_card_kalshi_ran_that_we_did_not_record(tmp_path):
    from scripts.live import coverage_report as cov

    history = tmp_path / "history.csv"
    history.write_text(
        "snapshot_timestamp,ticker\n"
        "2026-07-25T09:00:00+00:00,KXFIGHTMENTION-26JUL25AAA-BLOOD\n",
        encoding="utf-8",
    )
    # Kalshi ran two cards; we only hold snapshots for the first.
    report = cov.build(kalshi_dates={"2026-07-25", "2026-08-01"}, history_path=history)
    assert report["cards_missed"] == 1
    assert report["missed_dates"] == ["2026-08-01"]


def test_coverage_is_clean_when_kalshi_ran_no_markets(tmp_path):
    from scripts.live import coverage_report as cov

    history = tmp_path / "history.csv"
    history.write_text(
        "snapshot_timestamp,ticker\n"
        "2026-07-25T09:00:00+00:00,KXFIGHTMENTION-26JUL25AAA-BLOOD\n",
        encoding="utf-8",
    )
    report = cov.build(kalshi_dates={"2026-07-25"}, history_path=history)
    assert report["cards_missed"] == 0
    assert report["cards_recorded"] == 1


def test_cards_before_the_recorder_existed_are_not_misses(tmp_path):
    from scripts.live import coverage_report as cov

    history = tmp_path / "history.csv"
    history.write_text(
        "snapshot_timestamp,ticker\n"
        "2026-07-25T09:00:00+00:00,KXFIGHTMENTION-26JUL25AAA-BLOOD\n",
        encoding="utf-8",
    )
    report = cov.build(kalshi_dates={"2026-07-25", "2026-01-24"}, history_path=history)
    assert report["cards_missed"] == 0
    states = {c["date"]: c["state"] for c in report["cards"]}
    assert states["2026-01-24"] == "before_recording"


def test_date_from_ticker():
    from scripts.live.coverage_report import date_from_ticker

    assert date_from_ticker("KXFIGHTMENTION-26JUL25VAGIZA-BLOOD") == "2026-07-25"
    assert date_from_ticker("nonsense") == ""
