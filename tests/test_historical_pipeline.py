import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backtest_historical_markets import (
    build_summary,
    run_backtest,
    select_quote,
    settle_trade,
    trade_candidate,
)
from build_historical_market_ledger import build
from fetch_polymarket_metadata import extract_metadata, fetch_gamma_market
from fetch_oddpool_top_of_book import normalize_snapshot, read_csv, write_rows


class PolymarketMetadataTests(unittest.TestCase):
    @patch("fetch_polymarket_metadata.request_json")
    def test_active_market_lookup_falls_back_after_closed_query(self, request_json):
        request_json.side_effect = [[], [{"conditionId": "condition"}]]
        result = fetch_gamma_market("condition")
        self.assertEqual(result["conditionId"], "condition")
        self.assertIn("closed=true", request_json.call_args_list[0].args[0])
        self.assertIn("closed=false", request_json.call_args_list[1].args[0])

    def test_official_winner_and_token_ids_are_preserved(self):
        gamma = {
            "question": "Will announcers say Choke?",
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "eventStartTime": "2026-06-20T23:00:00Z",
            "closed": True,
        }
        clob = {
            "tokens": [
                {"token_id": "yes-token", "outcome": "Yes", "winner": False},
                {"token_id": "no-token", "outcome": "No", "winner": True},
            ]
        }
        result = extract_metadata("condition", gamma, clob)
        self.assertEqual(result["yes_asset_id"], "yes-token")
        self.assertEqual(result["no_asset_id"], "no-token")
        self.assertEqual(result["resolved_yes"], "False")
        self.assertEqual(result["resolution_source"], "polymarket_clob_winner")

    def test_event_start_can_come_from_embedded_event(self):
        gamma = {
            "outcomes": '["Yes", "No"]',
            "clobTokenIds": '["yes-token", "no-token"]',
            "events": [{"eventDate": "2026-06-20T23:00:00Z"}],
        }
        result = extract_metadata("condition", gamma, {"tokens": []})
        self.assertEqual(result["event_start_iso"], "2026-06-20T23:00:00Z")


class LedgerTests(unittest.TestCase):
    def market(self):
        return {
            "market_id": "condition",
            "exchange": "polymarket",
            "status": "closed",
            "market_type": "mention_announcers",
            "market_complexity": "simple_binary",
            "mapped_phrase": "ufc history",
            "mapped_target": "mention_ufc_history",
            "question": 'Will the announcers say "UFC History" during Holloway vs. Oliveira 2?',
        }

    def metadata(self, event_start):
        return {
            "market_id": "condition",
            "event_start_iso": event_start,
            "yes_asset_id": "yes-token",
            "no_asset_id": "no-token",
            "resolved_yes": "True",
            "resolution_source": "polymarket_clob_winner",
        }

    def test_rematch_does_not_map_to_old_fight(self):
        mentions = [{
            "event_date": "2015-08-23",
            "transcript_id": "old-fight",
            "fighter_1": "Max Holloway",
            "fighter_2": "Charles Oliveira",
        }]
        row = build([self.market()], [self.metadata("2026-03-07T23:00:00Z")], mentions)[0]
        self.assertEqual(row["mapping_status"], "no_exact_fight_match")
        self.assertEqual(row["data_ready"], "no")

    def test_exact_pair_and_date_maps(self):
        mentions = [{
            "event_date": "2026-03-07",
            "transcript_id": "rematch",
            "fighter_1": "Max Holloway",
            "fighter_2": "Charles Oliveira",
        }]
        row = build([self.market()], [self.metadata("2026-03-07T23:00:00Z")], mentions)[0]
        self.assertEqual(row["mapping_status"], "matched_fight")
        self.assertEqual(row["transcript_id"], "rematch")
        self.assertEqual(row["data_ready"], "yes")


class QuoteTests(unittest.TestCase):
    def test_polymarket_yes_and_no_quotes_stay_separate(self):
        mapping = {"exchange": "polymarket", "market_id": "condition"}
        yes = normalize_snapshot(mapping, {"timestamp": 1, "best_bid": 0.4, "best_ask": 0.45}, "YES")
        no = normalize_snapshot(mapping, {"timestamp": 1, "best_bid": 0.5, "best_ask": 0.55}, "NO")
        self.assertEqual(yes["yes_ask"], 0.45)
        self.assertEqual(yes["no_ask"], "")
        self.assertEqual(no["no_ask"], 0.55)
        self.assertEqual(no["yes_ask"], "")

    def test_quote_selection_rejects_lookahead_and_stale_quotes(self):
        cutoff = datetime(2026, 6, 20, 22, 0, tzinfo=timezone.utc)
        rows = [
            {"quote_side": "YES", "timestamp_iso": "2026-06-20T21:50:00Z", "yes_ask": "0.40"},
            {"quote_side": "YES", "timestamp_iso": "2026-06-20T22:01:00Z", "yes_ask": "0.10"},
        ]
        selected = select_quote(rows, "YES", cutoff, max_age_minutes=15)
        self.assertEqual(selected["ask"], 0.40)
        self.assertIsNone(select_quote(rows, "YES", cutoff, max_age_minutes=5))

    def test_quote_downloads_merge_without_losing_existing_rows(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.csv"
            first = normalize_snapshot(
                {"exchange": "polymarket", "market_id": "condition", "asset_id": "yes"},
                {"timestamp": 1, "best_bid": 0.4, "best_ask": 0.45},
                "YES",
            )
            second = normalize_snapshot(
                {"exchange": "polymarket", "market_id": "condition", "asset_id": "no"},
                {"timestamp": 2, "best_bid": 0.5, "best_ask": 0.55},
                "NO",
            )
            write_rows(path, [first])
            existing, stored = write_rows(path, [second])
            self.assertEqual(existing, 1)
            self.assertEqual(stored, 2)
            self.assertEqual(len(read_csv(path)), 2)


class BacktestTests(unittest.TestCase):
    def test_fixed_stake_pnl_includes_explicit_fee(self):
        candidate = trade_candidate(0.70, "YES", 0.50, fee_rate=0.01, slippage=0.01)
        self.assertAlmostEqual(candidate["all_in_price"], 0.5151)
        settled = settle_trade(candidate, resolved_yes=True, stake=100.0, fee_rate=0.01)
        self.assertAlmostEqual(settled["fees"], 1.0)
        self.assertAlmostEqual(settled["pnl"], 100 / 0.51 - 101)

    def test_pipeline_refuses_post_cutoff_only_quote(self):
        predictions = [{
            "market_id": "condition",
            "exchange": "polymarket",
            "prediction_status": "ok",
            "model_probability": "0.70",
            "resolved_yes": "True",
            "event_start_iso": "2026-06-20T23:00:00Z",
        }]
        quotes = [{
            "market_id": "condition",
            "exchange": "polymarket",
            "quote_side": "YES",
            "timestamp_iso": "2026-06-20T22:01:00Z",
            "yes_ask": "0.20",
        }]
        rows = run_backtest(
            predictions,
            quotes,
            entry_minutes=60,
            max_quote_age_minutes=30,
            min_edge=0.05,
            stake=100,
            fee_rate=0,
            slippage=0,
        )
        self.assertEqual(rows[0]["trade_status"], "no_fresh_executable_ask")

    def test_pipeline_trades_on_real_pre_cutoff_ask(self):
        predictions = [{
            "market_id": "condition",
            "exchange": "polymarket",
            "prediction_status": "ok",
            "model_probability": "0.70",
            "resolved_yes": "True",
            "event_start_iso": "2026-06-20T23:00:00Z",
        }]
        quotes = [{
            "market_id": "condition",
            "exchange": "polymarket",
            "quote_side": "YES",
            "timestamp_iso": "2026-06-20T21:55:00Z",
            "yes_ask": "0.50",
        }]
        rows = run_backtest(
            predictions,
            quotes,
            entry_minutes=60,
            max_quote_age_minutes=30,
            min_edge=0.05,
            stake=100,
            fee_rate=0,
            slippage=0,
        )
        self.assertEqual(rows[0]["trade_status"], "traded")
        self.assertEqual(rows[0]["side"], "YES")
        self.assertAlmostEqual(float(rows[0]["pnl"]), 100.0)

    def test_small_backtest_is_marked_insufficient(self):
        summary = build_summary([{
            "trade_status": "traded",
            "stake": "100",
            "pnl": "20",
            "won": "True",
            "model_edge": "0.10",
        }], min_claim_markets=30)
        self.assertEqual(summary["claim_status"], "insufficient_sample")
        self.assertEqual(summary["trades"], 1)


if __name__ == "__main__":
    unittest.main()
