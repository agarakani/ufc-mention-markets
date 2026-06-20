import unittest

from scripts.tracking.settle_card import yes_contract_pnl
from scripts.tracking.snapshot_card import classify_row, slug


class TrackingTests(unittest.TestCase):
    def test_watch_row_is_an_official_paper_trade(self):
        action, reason = classify_row({"watch": "yes", "conservative_edge": "0.01"}, 0.0)
        self.assertEqual(action, "trade")
        self.assertIn("watch", reason)

    def test_positive_safe_edge_below_watch_bar_is_a_lean(self):
        action, reason = classify_row({"watch": "no", "conservative_edge": "0.03"}, 0.0)
        self.assertEqual(action, "lean")
        self.assertIn("safe edge", reason)

    def test_no_edge_is_a_pass(self):
        action, reason = classify_row({"watch": "no", "conservative_edge": "-0.01", "edge": "-0.01"}, 0.0)
        self.assertEqual(action, "pass")
        self.assertEqual(reason, "no edge")

    def test_yes_contract_pnl(self):
        self.assertAlmostEqual(yes_contract_pnl(0.23, "yes"), 0.77)
        self.assertAlmostEqual(yes_contract_pnl(0.23, "no"), -0.23)

    def test_card_slug_keeps_dates_readable(self):
        self.assertEqual(slug("2026-06-20 main card"), "2026-06-20_main_card")


if __name__ == "__main__":
    unittest.main()
