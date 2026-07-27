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
