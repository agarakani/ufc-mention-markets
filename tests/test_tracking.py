import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.tracking.live_paper import read_csv, record_live_entries
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

    def test_live_paper_records_watch_once_at_side_price(self):
        with TemporaryDirectory() as tmp:
            rows = [{
                "watch": "yes",
                "ticker": "TEST-CHOKE",
                "event_ticker": "TEST",
                "event_title": "Blue vs Red",
                "fighter_1": "Blue",
                "fighter_2": "Red",
                "phrase": "Choke",
                "side": "no",
                "side_price": "0.43",
                "yes_ask": "0.62",
                "no_ask": "0.43",
                "edge": "0.32",
                "hurdle": "0.17",
                "data_risk": "yes",
                "model_probability": "0.25",
            }]

            first = record_live_entries(
                rows,
                card="UFC Test Card",
                out_root=Path(tmp),
                entered_at="2026-06-20T23:00:00+00:00",
            )
            second = record_live_entries(
                rows,
                card="UFC Test Card",
                out_root=Path(tmp),
                entered_at="2026-06-20T23:01:00+00:00",
            )

            self.assertEqual(first["new_entries"], 1)
            self.assertEqual(second["new_entries"], 0)
            positions = read_csv(Path(tmp) / "ufc_test_card" / "paper_positions.csv")
            self.assertEqual(len(positions), 1)
            self.assertEqual(positions[0]["paper_side"], "no")
            self.assertEqual(positions[0]["paper_price"], "0.43")
            self.assertIn("data-risk", positions[0]["paper_reason"])


if __name__ == "__main__":
    unittest.main()
