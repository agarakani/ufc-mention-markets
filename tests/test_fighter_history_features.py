import unittest

import pandas as pd

from fighter_history_features import add_prior_fighter_features, feature_names


class FighterHistoryFeatureTests(unittest.TestCase):
    def test_same_event_labels_never_leak_between_fights(self):
        rows = pd.DataFrame([
            {"event_date": "2025-01-01", "fighter_1": "A", "fighter_2": "B", "mention_choke": True},
            {"event_date": "2025-01-01", "fighter_1": "A", "fighter_2": "C", "mention_choke": False},
        ])
        featured, _ = add_prior_fighter_features(rows, ["mention_choke"])
        mean_rate = feature_names("mention_choke")[0]
        self.assertEqual(featured.loc[0, mean_rate], featured.loc[1, mean_rate])

    def test_later_fight_uses_only_prior_results(self):
        rows = pd.DataFrame([
            {"event_date": "2025-01-01", "fighter_1": "A", "fighter_2": "B", "mention_choke": True},
            {"event_date": "2025-02-01", "fighter_1": "A", "fighter_2": "C", "mention_choke": False},
        ])
        featured, _ = add_prior_fighter_features(rows, ["mention_choke"])
        max_rate = feature_names("mention_choke")[1]
        support = feature_names("mention_choke")[2]
        self.assertGreater(featured.loc[1, max_rate], featured.loc[0, max_rate])
        self.assertEqual(featured.loc[1, support], 1)

    def test_future_rows_use_full_history_without_updating_each_other(self):
        history = pd.DataFrame([
            {"event_date": "2025-01-01", "fighter_1": "A", "fighter_2": "B", "mention_choke": True},
        ])
        future = pd.DataFrame([
            {"event_date": "2025-02-01", "fighter_1": "A", "fighter_2": "C"},
            {"event_date": "2025-03-01", "fighter_1": "A", "fighter_2": "D"},
        ])
        _, featured = add_prior_fighter_features(history, ["mention_choke"], future)
        max_rate = feature_names("mention_choke")[1]
        self.assertEqual(featured.loc[0, max_rate], featured.loc[1, max_rate])


if __name__ == "__main__":
    unittest.main()
