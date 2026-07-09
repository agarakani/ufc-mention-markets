import unittest

from ufc_mentions.build_dashboard_data import build_backtest_groups, build_model_health


class BacktestGroupTests(unittest.TestCase):
    def test_groups_are_parsed_and_sorted_by_improvement(self):
        groups = build_backtest_groups([
            {
                "phrase": "Triangle",
                "scored_fights": "3368",
                "positives": "959",
                "actual_rate": "0.2847",
                "log_loss_improvement": "0.0302",
                "auc": "0.6378",
                "status": "beats_base",
            },
            {
                "phrase": "Championship",
                "scored_fights": "3368",
                "positives": "384",
                "actual_rate": "0.1140",
                "log_loss_improvement": "0.0635",
                "auc": "0.7491",
                "status": "beats_base",
            },
            {
                "phrase": "Lights Out",
                "scored_fights": "3368",
                "positives": "40",
                "actual_rate": "0.0119",
                "log_loss_improvement": "-0.0011",
                "auc": "0.5100",
                "status": "worse_than_base",
            },
        ])

        self.assertEqual([g["phrase"] for g in groups], ["Championship", "Triangle", "Lights Out"])
        self.assertTrue(groups[0]["beats_base"])
        self.assertFalse(groups[2]["beats_base"])
        self.assertEqual(groups[0]["scored_fights"], 3368)

    def test_rows_without_phrase_are_skipped(self):
        groups = build_backtest_groups([{"phrase": "", "status": "beats_base"}, {}])
        self.assertEqual(groups, [])


class ModelHealthTests(unittest.TestCase):
    def test_weakest_group_and_pl_scaffold(self):
        groups = build_backtest_groups([
            {"phrase": "A", "log_loss_improvement": "0.05", "status": "beats_base"},
            {"phrase": "B", "log_loss_improvement": "-0.002", "status": "worse_than_base"},
        ])
        health = build_model_health(
            {
                "status": "fight_level_backtest_generated",
                "claim": "Prediction quality only.",
                "prediction_rows": "50520",
                "groups": "15",
                "measured_groups": "15",
                "groups_beating_base_log_loss": "14",
                "folds": "5",
            },
            groups,
            {
                "is_money_backtest": True,
                "entry_rule": "first WATCH snapshot",
                "markets_with_results": 98,
                "resolved_event_count": 7,
                "official": {
                    "trades": 22, "wins": 2,
                    "total_staked": 4.25, "total_pnl": -2.25, "return_on_stake": -0.5294,
                },
                "lean": {
                    "trades": 51, "wins": 27,
                    "total_staked": 24.11, "total_pnl": 2.89, "return_on_stake": 0.1199,
                },
                "minimum_trades_for_claim": 30,
                "claim_status": "insufficient_sample",
                "note": "small sample",
            },
        )

        self.assertEqual(health["prediction"]["weakest_phrase"], "B")
        self.assertEqual(health["prediction"]["prediction_rows"], 50520)
        self.assertEqual(health["prediction"]["groups_beating_base"], 14)
        self.assertTrue(health["pl"]["is_money_backtest"])
        self.assertEqual(health["pl"]["official_trades"], 22)
        self.assertEqual(health["pl"]["official_wins"], 2)
        self.assertEqual(health["pl"]["official_pnl"], -2.25)
        self.assertEqual(health["pl"]["lean_trades"], 51)
        self.assertEqual(health["pl"]["minimum_trades_for_claim"], 30)
        self.assertEqual(health["pl"]["claim_status"], "insufficient_sample")
        self.assertTrue(health["pl"]["note"])

    def test_empty_inputs_do_not_crash(self):
        health = build_model_health({}, [], {})
        self.assertEqual(health["prediction"]["weakest_phrase"], "")
        self.assertFalse(health["pl"]["available"])
        self.assertEqual(health["groups"], [])


if __name__ == "__main__":
    unittest.main()
