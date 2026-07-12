import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.live.refresh_dashboard import cards_needing_settle


def write_outcomes(card_dir: Path, rows: list[dict]) -> None:
    card_dir.mkdir(parents=True, exist_ok=True)
    fields = ["ticker", "outcome", "resolution_status", "checked_at"]
    with (card_dir / "outcomes.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class CardsNeedingSettleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)
        self.stale = (self.now - timedelta(hours=2)).isoformat(timespec="seconds")
        self.fresh = (self.now - timedelta(minutes=2)).isoformat(timespec="seconds")

    def tearDown(self):
        self.tmp.cleanup()

    def test_finished_card_with_pending_outcomes_is_due(self):
        write_outcomes(self.root / "ufc_card_2026-07-11", [
            {"ticker": "T-A", "outcome": "", "resolution_status": "pending", "checked_at": self.stale},
        ])
        self.assertEqual(
            cards_needing_settle(self.root, active_cards=set(), now=self.now),
            ["ufc_card_2026-07-11"],
        )

    def test_active_card_is_skipped(self):
        write_outcomes(self.root / "ufc_card_2026-07-18", [
            {"ticker": "T-A", "outcome": "", "resolution_status": "open", "checked_at": self.stale},
        ])
        self.assertEqual(
            cards_needing_settle(self.root, active_cards={"ufc_card_2026-07-18"}, now=self.now),
            [],
        )

    def test_fully_settled_card_is_skipped(self):
        write_outcomes(self.root / "ufc_card_2026-06-20", [
            {"ticker": "T-A", "outcome": "yes", "resolution_status": "resolved", "checked_at": self.stale},
            {"ticker": "T-B", "outcome": "no", "resolution_status": "resolved", "checked_at": self.stale},
        ])
        self.assertEqual(cards_needing_settle(self.root, active_cards=set(), now=self.now), [])

    def test_recently_checked_card_waits(self):
        write_outcomes(self.root / "ufc_card_2026-07-11", [
            {"ticker": "T-A", "outcome": "", "resolution_status": "pending", "checked_at": self.fresh},
        ])
        self.assertEqual(cards_needing_settle(self.root, active_cards=set(), now=self.now), [])

    def test_card_without_outcomes_file_is_skipped(self):
        (self.root / "empty_card").mkdir(parents=True)
        self.assertEqual(cards_needing_settle(self.root, active_cards=set(), now=self.now), [])


if __name__ == "__main__":
    unittest.main()
