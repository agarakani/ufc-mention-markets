import unittest

from scripts.live.refresh_dashboard import combine_paper_results, paper_card_groups


def row(event_date, ticker):
    return {"event_date": event_date, "ticker": ticker}


class PaperCardGroupTests(unittest.TestCase):
    def test_explicit_card_keeps_all_rows_together(self):
        rows = [row("2026-07-11", "T-A"), row("2026-07-11", "T-B")]
        groups = paper_card_groups("My card", rows)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0][0], "My card")
        self.assertEqual(len(groups[0][1]), 2)

    def test_auto_groups_by_event_date(self):
        rows = [
            row("2026-07-11", "T-A"),
            row("2026-07-18", "T-B"),
            row("2026-07-11", "T-C"),
        ]
        groups = paper_card_groups("auto", rows)
        self.assertEqual([name for name, _ in groups],
                         ["ufc_card_2026-07-11", "ufc_card_2026-07-18"])
        self.assertEqual(len(groups[0][1]), 2)
        self.assertEqual(len(groups[1][1]), 1)

    def test_auto_skips_rows_without_a_date(self):
        groups = paper_card_groups("auto", [row("", "T-A")])
        self.assertEqual(groups, [])

    def test_no_rows_means_no_groups(self):
        self.assertEqual(paper_card_groups("My card", []), [])


class CombinePaperResultTests(unittest.TestCase):
    def test_single_explicit_result_passes_through(self):
        result = {"card": "My card", "path": "p", "new_entries": 2, "total_entries": 5}
        self.assertEqual(combine_paper_results("My card", [result]), result)

    def test_auto_results_are_summed(self):
        combined = combine_paper_results("auto", [
            {"card": "ufc_card_2026-07-11", "path": "a", "new_entries": 2,
             "total_entries": 5, "resolved": 1, "pending": 0, "open": 4},
            {"card": "ufc_card_2026-07-18", "path": "b", "new_entries": 1,
             "total_entries": 3, "resolved": 0, "pending": 2, "open": 1},
        ])
        self.assertEqual(combined["new_entries"], 3)
        self.assertEqual(combined["total_entries"], 8)
        self.assertEqual(combined["pending"], 2)
        self.assertIn("ufc_card_2026-07-11", combined["card"])
        self.assertIn("ufc_card_2026-07-18", combined["card"])

    def test_empty_results_return_none(self):
        self.assertIsNone(combine_paper_results("auto", []))


if __name__ == "__main__":
    unittest.main()
