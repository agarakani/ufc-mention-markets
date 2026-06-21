import unittest

from scripts.tracking.settle_card import contract_pnl
from scripts.tracking.snapshot_card import classify_row, slug


class TrackingTests(unittest.TestCase):
    def test_watch_row_is_an_official_paper_trade(self):
        action, reason = classify_row({"watch": "yes", "side": "yes", "edge": "0.01"}, 0.0)
        self.assertEqual(action, "trade")
        self.assertIn("watch", reason)

    def test_data_risk_watch_is_labeled(self):
        action, reason = classify_row({"watch": "yes", "side": "no", "edge": "0.20", "data_risk": "yes"}, 0.0)
        self.assertEqual(action, "trade")
        self.assertIn("data-risk", reason)

    def test_positive_model_edge_below_watch_bar_is_a_lean(self):
        action, reason = classify_row({"watch": "no", "side": "no", "edge": "0.03"}, 0.0)
        self.assertEqual(action, "lean")
        self.assertIn("model edge", reason)
        self.assertIn("no", reason)

    def test_no_edge_is_a_pass(self):
        action, reason = classify_row({"watch": "no", "side": "yes", "edge": "-0.01"}, 0.0)
        self.assertEqual(action, "pass")
        self.assertEqual(reason, "no edge")

    def test_contract_pnl_uses_selected_side(self):
        self.assertAlmostEqual(contract_pnl("yes", 0.23, "yes"), 0.77)
        self.assertAlmostEqual(contract_pnl("yes", 0.23, "no"), -0.23)
        self.assertAlmostEqual(contract_pnl("no", 0.31, "no"), 0.69)
        self.assertAlmostEqual(contract_pnl("no", 0.31, "yes"), -0.31)

    def test_card_slug_keeps_dates_readable(self):
        self.assertEqual(slug("2026-06-20 main card"), "2026-06-20_main_card")


if __name__ == "__main__":
    unittest.main()
