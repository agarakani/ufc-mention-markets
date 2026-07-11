import unittest

from scripts.model.backtest_pl import current_rule_entry
from ufc_mentions.entry_rules import (
    load_phrase_trust,
    normalize_forms,
    phrase_trust,
    watch_decision,
)


class NormalizeFormsTests(unittest.TestCase):
    def test_pipe_slash_and_list_all_match(self):
        expected = frozenset({"choke", "choked", "chokehold"})
        self.assertEqual(normalize_forms("Choke | Choked | Chokehold"), expected)
        self.assertEqual(normalize_forms("Choke / Choked / Chokehold"), expected)
        self.assertEqual(normalize_forms(("Choke", "choked ", "CHOKEHOLD")), expected)


class PhraseTrustTests(unittest.TestCase):
    TRUST = {
        frozenset({"championship"}): {"auc": 0.75, "beats_base": True, "trusted": True},
        frozenset({"tired", "tiring"}): {"auc": 0.53, "beats_base": True, "trusted": False},
        frozenset({"lights out"}): {"auc": 0.53, "beats_base": False, "trusted": False},
    }

    def test_trusted_group(self):
        trusted, note = phrase_trust("Championship", self.TRUST)
        self.assertTrue(trusted)
        self.assertEqual(note, "")

    def test_low_skill_group_is_lean_only(self):
        trusted, note = phrase_trust("Tired / Tiring", self.TRUST)
        self.assertFalse(trusted)
        self.assertIn("lean but never watch", note)

    def test_failed_group_is_lean_only(self):
        trusted, note = phrase_trust("Lights Out", self.TRUST)
        self.assertFalse(trusted)
        self.assertIn("failed the old-fight prediction test", note)

    def test_unknown_group_is_trusted_with_note(self):
        trusted, note = phrase_trust("Brand New Phrase", self.TRUST)
        self.assertTrue(trusted)
        self.assertIn("no prediction-backtest record", note)

    def test_empty_map_trusts_everything(self):
        self.assertEqual(phrase_trust("Anything", {}), (True, ""))

    def test_load_from_real_backtest_csv_if_present(self):
        trust = load_phrase_trust()
        if not trust:
            self.skipTest("no backtest csv on this machine")
        self.assertTrue(any(entry["trusted"] for entry in trust.values()))


class WatchDecisionTests(unittest.TestCase):
    def kwargs(self, **overrides):
        base = dict(edge=0.08, hurdle=0.05, side="no", model_ready=True,
                    require_model=True, trusted=True, edge_cap=0.15)
        base.update(overrides)
        return base

    def test_normal_watch(self):
        self.assertEqual(watch_decision(**self.kwargs()), (True, ""))

    def test_edge_over_cap_is_big_gap(self):
        watch, blocker = watch_decision(**self.kwargs(edge=0.30))
        self.assertFalse(watch)
        self.assertEqual(blocker, "big_gap")

    def test_edge_exactly_at_cap_still_watches(self):
        self.assertEqual(watch_decision(**self.kwargs(edge=0.15)), (True, ""))

    def test_untrusted_phrase_blocks(self):
        watch, blocker = watch_decision(**self.kwargs(trusted=False))
        self.assertFalse(watch)
        self.assertEqual(blocker, "low_trust")

    def test_below_bar(self):
        watch, blocker = watch_decision(**self.kwargs(edge=0.04))
        self.assertFalse(watch)
        self.assertEqual(blocker, "below_bar")

    def test_missing_model(self):
        watch, blocker = watch_decision(**self.kwargs(model_ready=False))
        self.assertFalse(watch)
        self.assertEqual(blocker, "no_model")

    def test_missing_prices(self):
        watch, blocker = watch_decision(**self.kwargs(edge=None))
        self.assertFalse(watch)
        self.assertEqual(blocker, "no_prices")


class CurrentRuleEntryTests(unittest.TestCase):
    TRUST = {
        frozenset({"championship"}): {"auc": 0.75, "beats_base": True, "trusted": True},
        frozenset({"tired", "tiring"}): {"auc": 0.53, "beats_base": True, "trusted": False},
    }

    def row(self, **overrides):
        base = {"phrase": "Championship", "edge": "0.10", "hurdle": "0.05"}
        base.update(overrides)
        return base

    def test_in_band_trusted_enters(self):
        self.assertTrue(current_rule_entry(self.row(), self.TRUST))

    def test_over_cap_does_not_enter(self):
        self.assertFalse(current_rule_entry(self.row(edge="0.40"), self.TRUST))

    def test_untrusted_phrase_does_not_enter(self):
        self.assertFalse(current_rule_entry(self.row(phrase="Tired / Tiring"), self.TRUST))

    def test_below_hurdle_does_not_enter(self):
        self.assertFalse(current_rule_entry(self.row(edge="0.03"), self.TRUST))


if __name__ == "__main__":
    unittest.main()
