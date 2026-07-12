import unittest

from scripts.model.build_results_labels import assemble_labels, meta_from_history


class ResultsLabelTests(unittest.TestCase):
    META = {
        "KXFIGHTMENTION-26JUL11ABC-CHOK": {
            "ticker": "KXFIGHTMENTION-26JUL11ABC-CHOK",
            "event_ticker": "KXFIGHTMENTION-26JUL11ABC",
            "fighter_1": "Alpha One",
            "fighter_2": "Beta Two",
            "phrase": "Choke / Choked / Chokehold",
            "forms": "",
        },
    }

    def test_settled_result_becomes_label_with_date_and_fighters(self):
        labels = assemble_labels({"KXFIGHTMENTION-26JUL11ABC-CHOK": "no"}, self.META)
        self.assertEqual(len(labels), 1)
        row = labels[0]
        self.assertEqual(row["event_date"], "2026-07-11")
        self.assertEqual(row["fighter_1"], "Alpha One")
        self.assertEqual(row["phrase"], "Choke / Choked / Chokehold")
        self.assertEqual(row["outcome"], "no")

    def test_unresolved_results_are_skipped(self):
        labels = assemble_labels({"KXFIGHTMENTION-26JUL11ABC-CHOK": ""}, self.META)
        self.assertEqual(labels, [])

    def test_unknown_ticker_still_labels_with_blanks(self):
        labels = assemble_labels({"KXFIGHTMENTION-26AUG01XYZ-DANA": "yes"}, {})
        self.assertEqual(len(labels), 1)
        self.assertEqual(labels[0]["outcome"], "yes")
        self.assertEqual(labels[0]["fighter_1"], "")

    def test_meta_from_history_keeps_first_phrase_per_ticker(self):
        history = [
            {"ticker": "T-A", "event_ticker": "E-1", "phrase": "Dana"},
            {"ticker": "T-A", "event_ticker": "E-1", "phrase": "changed later"},
        ]
        meta = meta_from_history(history)
        self.assertEqual(meta["T-A"]["phrase"], "Dana")


if __name__ == "__main__":
    unittest.main()
