import unittest

from scripts.model.backtest_pl import (
    build_summary,
    cohort_stats,
    first_entries,
    pending_result_events,
    settle,
)


def snap(ts, ticker, *, watch="false", edge="", side="yes", price="0.20",
         event="KXFIGHTMENTION-26JUN20AAABBB", phrase="Choke / Choked / Chokehold"):
    return {
        "snapshot_timestamp": ts,
        "ticker": ticker,
        "event_ticker": event,
        "phrase": phrase,
        "watch": watch,
        "edge": edge,
        "side": side,
        "side_price": price,
        "model_probability": "0.30",
        "hurdle": "0.10",
        "data_risk": "false",
    }


class FirstEntryTests(unittest.TestCase):
    def test_official_entry_is_first_watch_snapshot(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-CHOK", watch="false", edge="0.02", price="0.30"),
            snap("2026-06-20T02:00:00+00:00", "T-CHOK", watch="true", edge="0.12", price="0.25"),
            snap("2026-06-20T03:00:00+00:00", "T-CHOK", watch="true", edge="0.15", price="0.20"),
        ]
        entries = first_entries(history)
        self.assertEqual(entries["T-CHOK"]["cohort"], "official")
        self.assertEqual(entries["T-CHOK"]["price"], 0.25)
        self.assertEqual(entries["T-CHOK"]["entered_at"], "2026-06-20T02:00:00+00:00")

    def test_lean_entry_when_never_watch(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-TRIA", watch="false", edge="-0.01"),
            snap("2026-06-20T02:00:00+00:00", "T-TRIA", watch="false", edge="0.03", price="0.22"),
        ]
        entries = first_entries(history)
        self.assertEqual(entries["T-TRIA"]["cohort"], "lean")
        self.assertEqual(entries["T-TRIA"]["price"], 0.22)

    def test_watch_upgrades_earlier_lean(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-X", watch="false", edge="0.04", price="0.30"),
            snap("2026-06-20T02:00:00+00:00", "T-X", watch="true", edge="0.12", price="0.28"),
        ]
        entries = first_entries(history)
        self.assertEqual(entries["T-X"]["cohort"], "official")
        self.assertEqual(entries["T-X"]["price"], 0.28)

    def test_rows_without_price_or_side_are_skipped(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-Y", watch="true", edge="0.2", price=""),
            snap("2026-06-20T02:00:00+00:00", "T-Y", watch="true", edge="0.2", side=""),
        ]
        self.assertEqual(first_entries(history), {})


class SettleTests(unittest.TestCase):
    def test_pnl_math_yes_and_no_sides(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-WIN", watch="true", side="yes", price="0.20"),
            snap("2026-06-20T01:00:00+00:00", "T-LOSE", watch="true", side="no", price="0.60"),
            snap("2026-06-20T01:00:00+00:00", "T-OPEN", watch="true", side="yes", price="0.10"),
        ]
        entries = first_entries(history)
        trades = settle(entries, {"T-WIN": "yes", "T-LOSE": "yes"})

        by_ticker = {t["ticker"]: t for t in trades}
        self.assertEqual(len(trades), 2)  # unresolved market is never counted
        self.assertAlmostEqual(by_ticker["T-WIN"]["pnl"], 0.80)
        self.assertTrue(by_ticker["T-WIN"]["won"])
        self.assertAlmostEqual(by_ticker["T-LOSE"]["pnl"], -0.60)
        self.assertFalse(by_ticker["T-LOSE"]["won"])

    def test_cohort_stats_and_claim_gate(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-A", watch="true", side="yes", price="0.20"),
            snap("2026-06-20T01:00:00+00:00", "T-B", watch="false", edge="0.05", side="no", price="0.50"),
        ]
        trades = settle(first_entries(history), {"T-A": "yes", "T-B": "no"})
        official = cohort_stats(trades, "official")
        lean = cohort_stats(trades, "lean")
        self.assertEqual(official["trades"], 1)
        self.assertAlmostEqual(official["total_pnl"], 0.80)
        self.assertEqual(lean["trades"], 1)
        self.assertAlmostEqual(lean["total_pnl"], 0.50)

        summary = build_summary(trades, history_rows=2, snapshots=1,
                                results_count=2, resolved_events={"E1"})
        self.assertTrue(summary["is_money_backtest"])
        self.assertEqual(summary["claim_status"], "insufficient_sample")
        self.assertEqual(summary["official"]["trades"], 1)
        self.assertFalse(summary["fees_included"])
        self.assertEqual(summary["latest_settled_event_date"], "2026-06-20")


class PendingResultTests(unittest.TestCase):
    def test_past_event_with_unknown_result_is_pending(self):
        history = [
            snap("2026-06-20T01:00:00+00:00", "T-A", event="KXFIGHTMENTION-26JUN20AAA"),
            snap("2026-07-11T01:00:00+00:00", "T-B", event="KXFIGHTMENTION-26JUL11BBB"),
        ]
        pending = pending_result_events(history, {}, today="2026-07-08")
        self.assertEqual(pending, {"KXFIGHTMENTION-26JUN20AAA"})

    def test_fully_cached_past_event_is_not_pending(self):
        history = [snap("2026-06-20T01:00:00+00:00", "T-A", event="KXFIGHTMENTION-26JUN20AAA")]
        pending = pending_result_events(history, {"T-A": "no"}, today="2026-07-08")
        self.assertEqual(pending, set())

    def test_upcoming_event_never_pending_even_without_results(self):
        history = [snap("2026-07-11T01:00:00+00:00", "T-B", event="KXFIGHTMENTION-26JUL11BBB")]
        pending = pending_result_events(history, {}, today="2026-07-08")
        self.assertEqual(pending, set())


if __name__ == "__main__":
    unittest.main()
