import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ufc_mentions.kalshi_context_model import (
    apply_live_calibration,
    load_model_config,
)
from ufc_mentions.train_baseline_models import add_date_features, feature_columns


def test_event_tier_derivation():
    frame = pd.DataFrame({
        "event_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "event_title": [
            "UFC 300: Pereira vs Hill",
            "UFC Fight Night: Kape vs Almabayev",
            "UFC on ESPN: Someone vs Someone",
            "",
        ],
    })
    out = add_date_features(frame)
    assert list(out["event_tier"]) == ["ppv", "fight_night", "other", "other"]


def test_feature_set_v2_includes_event_tier():
    frame = pd.DataFrame({
        "event_date": ["2026-01-01"],
        "event_title": ["UFC 300"],
        "kaggle_R_wins": [10],
        "mention_choke": [True],
    })
    frame = add_date_features(frame)
    v1 = feature_columns(frame, profile="stats_only_history", include_identity=False)
    v2 = feature_columns(frame, profile="stats_only_history", include_identity=False, feature_set="v2")
    assert "event_tier" not in v1
    assert "event_tier" in v2
    assert set(v1) <= set(v2)


def test_apply_live_calibration_identity_and_shift():
    # identity coefficients leave probabilities alone
    assert abs(apply_live_calibration(0.3, {"a": 1.0, "b": 0.0}) - 0.3) < 1e-9
    # a slope over 1 expands away from 0.5 (fixes compression)
    expanded = apply_live_calibration(0.6, {"a": 2.0, "b": 0.0})
    assert expanded > 0.6
    squeezed = apply_live_calibration(0.4, {"a": 2.0, "b": 0.0})
    assert squeezed < 0.4
    # disabled/missing calibration is a no-op
    assert apply_live_calibration(0.6, None) == 0.6
    assert apply_live_calibration(0.6, {}) == 0.6


def test_load_model_config_defaults_and_values(tmp_path):
    missing = load_model_config(tmp_path / "nope.json")
    assert missing == {"label_weight": 0.0, "feature_set": "v1", "calibration": None}

    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "label_weight": 3.0,
        "feature_set": "v2",
        "calibration": {"a": 1.4, "b": -0.1},
    }))
    loaded = load_model_config(path)
    assert loaded["label_weight"] == 3.0
    assert loaded["feature_set"] == "v2"
    assert loaded["calibration"]["a"] == 1.4

    path.write_text("not json")
    assert load_model_config(path)["feature_set"] == "v1"
