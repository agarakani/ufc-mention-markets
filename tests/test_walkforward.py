import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.model.walkforward_update import (
    calibrated_holdout_means,
    fit_platt,
    forms_from_phrase,
    loss_from_pairs,
    pick_best_variant,
    pick_best_weight,
)
from ufc_mentions.kalshi_context_model import (
    TARGET,
    KalshiFightContextModel,
    load_label_weight,
)
from ufc_mentions.kalshi_mentions import TranscriptCorpus


class FormsFromPhraseTests(unittest.TestCase):
    def test_grouped_phrase_splits_on_slashes(self):
        self.assertEqual(
            forms_from_phrase("Choke / Choked / Chokehold"),
            ("Choke", "Choked", "Chokehold"),
        )

    def test_single_word_stays_whole(self):
        self.assertEqual(forms_from_phrase("Dana"), ("Dana",))


class PickBestWeightTests(unittest.TestCase):
    def test_lowest_log_loss_wins(self):
        self.assertEqual(pick_best_weight({0.0: 0.62, 5.0: 0.58, 10.0: 0.60}), 5.0)

    def test_tie_goes_to_smaller_weight(self):
        self.assertEqual(pick_best_weight({0.0: 0.60, 5.0: 0.60}), 0.0)

    def test_all_none_returns_zero(self):
        self.assertEqual(pick_best_weight({0.0: None, 5.0: None}), 0.0)


class VariantGateTests(unittest.TestCase):
    def test_gate_keeps_v1_when_v2_worse(self):
        self.assertEqual(
            pick_best_variant({"v1": 0.50, "v2": 0.52, "v1+calib": 0.51, "v2+calib": 0.53}),
            "v1",
        )

    def test_gate_adopts_winner(self):
        self.assertEqual(
            pick_best_variant({"v1": 0.52, "v2": 0.50, "v1+calib": 0.51, "v2+calib": 0.53}),
            "v2",
        )
        self.assertEqual(
            pick_best_variant({"v1": 0.52, "v2": 0.51, "v1+calib": 0.49, "v2+calib": 0.53}),
            "v1+calib",
        )

    def test_tie_goes_to_simpler_variant(self):
        self.assertEqual(pick_best_variant({"v1": 0.50, "v2+calib": 0.50}), "v1")

    def test_all_none_returns_v1(self):
        self.assertEqual(pick_best_variant({"v1": None, "v2": None}), "v1")

    def test_fit_platt_needs_enough_two_sided_pairs(self):
        self.assertIsNone(fit_platt([(0.6, 1)] * 10))
        self.assertIsNone(fit_platt([(0.6, 1)] * 40))
        pairs = [(0.55, 1)] * 25 + [(0.45, 0)] * 25
        calibration = fit_platt(pairs)
        self.assertIsNotNone(calibration)
        self.assertIn("a", calibration)

    def test_calibrated_holdout_uses_only_earlier_cards(self):
        # First card scores raw (no earlier data); a compressed model on the
        # second card improves once calibrated on the first card's pairs.
        compressed = [(0.55, 1)] * 30 + [(0.45, 0)] * 30
        per_holdout = {"card1": compressed, "card2": compressed}
        raw_mean = loss_from_pairs(compressed)
        mean = calibrated_holdout_means(per_holdout, ["card1", "card2"])
        self.assertIsNotNone(mean)
        # card1 is raw, card2 is calibrated-better, so the mean must not be worse
        self.assertLessEqual(mean, raw_mean + 1e-9)


class LoadLabelWeightTests(unittest.TestCase):
    def test_missing_file_means_zero(self):
        self.assertEqual(load_label_weight("/nonexistent/config.json"), 0.0)

    def test_reads_valid_weight(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"label_weight": 5.0}, fh)
        self.assertEqual(load_label_weight(fh.name), 5.0)
        Path(fh.name).unlink()

    def test_junk_means_zero(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("not json")
        self.assertEqual(load_label_weight(fh.name), 0.0)
        Path(fh.name).unlink()


class LabelRowTests(unittest.TestCase):
    def make_model(self, weight=5.0):
        history = pd.DataFrame([{
            "transcript_id": "h1", "fighter_1": "A", "fighter_2": "B",
            "fighter_1_last": "A", "fighter_2_last": "B",
            "event_date": "2020-01-01", "weight_class": "", "event_title": "",
            "duration_s": "",
        }])
        labels = pd.DataFrame([
            {"event_date": "2026-06-20", "ticker": "T-1", "fighter_1": "Manel Kape",
             "fighter_2": "Kyoji Horiguchi", "phrase": "Choke / Choked / Chokehold",
             "outcome": "no"},
            {"event_date": "2026-07-11", "ticker": "T-2", "fighter_1": "Conor McGregor",
             "fighter_2": "Max Holloway", "phrase": "Choke / Choked / Chokehold",
             "outcome": "yes"},
            {"event_date": "2026-07-11", "ticker": "T-3", "fighter_1": "Conor McGregor",
             "fighter_2": "Max Holloway", "phrase": "Dana", "outcome": "no"},
        ])
        return KalshiFightContextModel(
            history, TranscriptCorpus([]), labels=labels, label_weight=weight,
        )

    def test_labels_become_target_rows_for_matching_group(self):
        model = self.make_model()
        rows = model._label_rows_for(("Choke", "Choked", "Chokehold"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(rows[TARGET].tolist()), [False, True])

    def test_cutoff_holds_out_the_newest_card(self):
        model = self.make_model()
        model.label_cutoff_date = "2026-07-11"
        rows = model._label_rows_for(("Choke", "Choked", "Chokehold"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0]["event_date"], "2026-06-20")

    def test_weight_zero_disables_labels(self):
        model = self.make_model(weight=0.0)
        self.assertEqual(len(model._label_rows_for(("Choke", "Choked", "Chokehold"))), 0)

    def test_other_phrase_groups_do_not_leak_in(self):
        model = self.make_model()
        rows = model._label_rows_for(("Dana",))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.iloc[0][TARGET], False)


if __name__ == "__main__":
    unittest.main()
