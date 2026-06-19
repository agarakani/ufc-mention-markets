import base64
import unittest

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ufc_mentions.kalshi_client import KalshiClient, TopOfBook, top_of_book
from ufc_mentions.kalshi_context_model import ContextPrediction
from ufc_mentions.kalshi_mentions import (
    RuleParseError,
    TranscriptCorpus,
    TranscriptFight,
    grouped_matcher,
    phrase_forms_from_rules,
    wilson_lower_bound,
)
from scripts.live.price_fight import price_market
from scripts.live.refresh_dashboard import add_price_changes, event_snapshot
from scripts.model.audit_grouped_rules import parse_forms


class KalshiClientTests(unittest.TestCase):
    def test_auth_signature_uses_timestamp_method_and_path_without_query(self):
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        client = KalshiClient(key_id="key-id", private_key=private_key)
        headers = client.request_headers(
            "GET",
            "/trade-api/v2/markets?limit=10",
            timestamp_ms=1700000000123,
        )
        signature = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
        private_key.public_key().verify(
            signature,
            b"1700000000123GET/trade-api/v2/markets",
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )

    def test_orderbook_bids_are_converted_to_executable_asks(self):
        book = top_of_book({
            "orderbook_fp": {
                "yes_dollars": [["0.2200", "5"], ["0.2500", "2"]],
                "no_dollars": [["0.6500", "4"], ["0.6700", "1"]],
            }
        })
        self.assertAlmostEqual(book.yes_bid, 0.25)
        self.assertAlmostEqual(book.yes_ask, 0.33)
        self.assertAlmostEqual(book.no_bid, 0.67)
        self.assertAlmostEqual(book.no_ask, 0.75)
        self.assertAlmostEqual(book.spread, 0.08)

    def test_legacy_cent_orderbook_is_supported(self):
        book = top_of_book({"orderbook": {"yes": [[25, 2]], "no": [[67, 1]]}})
        self.assertAlmostEqual(book.yes_ask, 0.33)
        self.assertAlmostEqual(book.no_ask, 0.75)


class RuleTests(unittest.TestCase):
    def market(self, word, rule_word=None):
        return {
            "ticker": "KX-TEST",
            "custom_strike": {"Word": word},
            "rules_primary": f"If the commentator says {rule_word or word} as part of the fight, resolves Yes.",
        }

    def test_forms_come_from_rules_and_preserve_grouping(self):
        forms = phrase_forms_from_rules(self.market("Choke / Choked / Chokehold"))
        self.assertEqual(forms, ("Choke", "Choked", "Chokehold"))
        matcher = grouped_matcher(forms)
        self.assertTrue(matcher("He was choked against the fence."))
        self.assertTrue(matcher("Several chokeholds were attempted."))
        self.assertFalse(matcher("The choker is in the crowd."))

    def test_rule_and_strike_disagreement_is_rejected(self):
        with self.assertRaises(RuleParseError):
            phrase_forms_from_rules(self.market("Blood / Bloody", "Blood"))

    def test_event_does_not_qualify_is_not_treated_as_language(self):
        with self.assertRaises(RuleParseError):
            phrase_forms_from_rules(self.market("Event does not qualify"))

    def test_audit_forms_accept_pipe_and_slash_group_separators(self):
        self.assertEqual(
            parse_forms({"forms": "Choke | Choked | Chokehold"}),
            ("Choke", "Choked", "Chokehold"),
        )
        self.assertEqual(
            parse_forms({"forms": "Choke / Choked / Chokehold"}),
            ("Choke", "Choked", "Chokehold"),
        )


def fight(identifier, f1, f2, text, nick1="", nick2="", event_date="2025-01-01"):
    return TranscriptFight(identifier, event_date, f1, f2, nick1, nick2, text)


class EstimateTests(unittest.TestCase):
    def test_unambiguous_extended_and_parenthetical_names_resolve(self):
        corpus = TranscriptCorpus([
            fight("1", "Andre Lima", "B", "nothing"),
            fight("2", "Vinicius Oliveira", "C", "nothing"),
        ])
        self.assertEqual(corpus.resolve_fighter("Andre (Bra) Lima"), corpus.resolve_fighter("Andre Lima"))
        self.assertEqual(
            corpus.resolve_fighter("Vinicius De Oliveira Prestes De Matos"),
            corpus.resolve_fighter("Vinicius Oliveira"),
        )

    def test_generic_group_uses_league_rate_not_small_fighter_rate(self):
        corpus = TranscriptCorpus([
            fight("1", "A", "B", "they train hard"),
            fight("2", "A", "C", "nothing"),
            fight("3", "D", "E", "trained all year"),
            fight("4", "F", "G", "nothing"),
        ])
        estimate = corpus.estimate(("Train", "Trained", "Training"), "A", "B", min_fighter_fights=3)
        self.assertEqual(estimate.word_type, "generic")
        self.assertAlmostEqual(estimate.league_rate, 0.5)
        self.assertAlmostEqual(estimate.probability, 0.5)
        self.assertFalse(estimate.confidence_ok)

    def test_missing_fighter_history_keeps_generic_estimate_low_confidence(self):
        corpus = TranscriptCorpus([
            fight("1", "A", "B", "they train hard"),
            fight("2", "C", "D", "nothing"),
            fight("3", "E", "F", "trained all year"),
            fight("4", "G", "H", "nothing"),
        ])
        estimate = corpus.estimate(("Train", "Trained", "Training"), "Unknown One", "Unknown Two")
        self.assertEqual(estimate.word_type, "generic")
        self.assertAlmostEqual(estimate.probability, 0.5)
        self.assertEqual(estimate.missing_fighters, ("Unknown One", "Unknown Two"))
        self.assertIn("missing transcript history", estimate.confidence_note)
        self.assertFalse(estimate.confidence_ok)

    def test_ambiguous_fighter_history_falls_back_low_confidence(self):
        corpus = TranscriptCorpus([
            fight("1", "Alpha Magomedov", "B", "they train hard"),
            fight("2", "Beta Magomedov", "C", "nothing"),
            fight("3", "D", "E", "trained all year"),
            fight("4", "F", "G", "nothing"),
        ])
        with self.assertRaises(ValueError):
            corpus.resolve_fighter("Murtazali Magomedov")
        estimate = corpus.estimate(("Train", "Trained", "Training"), "Alpha Magomedov", "Murtazali Magomedov")
        self.assertEqual(estimate.word_type, "generic")
        self.assertEqual(estimate.missing_fighters, ("Murtazali Magomedov",))
        self.assertFalse(estimate.confidence_ok)

    def test_fighter_specific_term_gets_small_empirical_bayes_prior(self):
        corpus = TranscriptCorpus([
            fight("1", "Sean O'Malley", "B", "Suga lands", "Suga", ""),
            fight("2", "Sean O'Malley", "C", "Suga again", "Suga", ""),
        ] + [
            fight(f"x{i}", f"X{i}", f"Y{i}", "nothing") for i in range(8)
        ])
        estimate = corpus.estimate(("Suga",), "Sean O'Malley", "B", min_fighter_fights=2)
        self.assertEqual(estimate.word_type, "fighter_specific")
        self.assertEqual(estimate.prior_strength, 4.0)
        self.assertAlmostEqual(estimate.probability, (2 + 4 * 0.2) / (2 + 4))
        self.assertTrue(estimate.confidence_ok)

    def test_cutoff_excludes_target_and_future_fights(self):
        corpus = TranscriptCorpus([
            fight("past", "A", "B", "Suga lands", "Suga", "", "2025-01-01"),
            fight("target", "A", "C", "Suga lands", "Suga", "", "2026-06-20"),
            fight("future", "A", "D", "Suga lands", "Suga", "", "2026-07-01"),
            fight("other", "X", "Y", "nothing", "", "", "2025-02-01"),
        ])
        estimate = corpus.estimate(
            ("Suga",), "A", "B", cutoff_date="2026-06-20", min_fighter_fights=1
        )
        self.assertEqual(estimate.league_fights, 2)
        self.assertEqual(estimate.fighter_fights, 1)
        self.assertEqual(estimate.fighter_hits, 1)

    def test_wilson_lower_bound_is_conservative(self):
        self.assertLess(wilson_lower_bound(16, 16), 1.0)
        self.assertIsNone(wilson_lower_bound(0, 0))


class GateTests(unittest.TestCase):
    def test_watch_must_clear_spread_fee_confidence_and_conservative_bound(self):
        corpus = TranscriptCorpus([
            fight(str(i), "A", f"B{i}", "Suga lands", "Suga", "") for i in range(16)
        ] + [
            fight(f"x{i}", f"X{i}", f"Y{i}", "nothing") for i in range(64)
        ])
        market = {
            "ticker": "KX-TEST",
            "custom_strike": {"Word": "Suga"},
            "rules_primary": "If the commentator says Suga as part of the fight, resolves Yes.",
        }
        row = price_market(
            market,
            TopOfBook(yes_bid=0.73, yes_ask=0.75, no_bid=0.25, no_ask=0.27),
            corpus,
            "A",
            "B0",
            cutoff_date="2026-01-01",
            fee_buffer=0.02,
            min_fighter_fights=15,
        )
        self.assertTrue(row.estimate.confidence_ok)
        self.assertGreater(row.edge, row.hurdle)
        self.assertGreater(row.conservative_edge, row.hurdle)
        self.assertTrue(row.watch)

        point_only = price_market(
            market,
            TopOfBook(yes_bid=0.77, yes_ask=0.79, no_bid=0.21, no_ask=0.23),
            corpus,
            "A",
            "B0",
            cutoff_date="2026-01-01",
            fee_buffer=0.02,
            min_fighter_fights=15,
        )
        self.assertGreater(point_only.edge, point_only.hurdle)
        self.assertLessEqual(point_only.conservative_edge, point_only.hurdle)
        self.assertFalse(point_only.watch)

        low_confidence = price_market(
            market,
            TopOfBook(yes_bid=0.73, yes_ask=0.75, no_bid=0.25, no_ask=0.27),
            corpus,
            "A",
            "B0",
            cutoff_date="2026-01-01",
            fee_buffer=0.02,
            min_fighter_fights=30,
        )
        self.assertFalse(low_confidence.watch)

    def test_required_fight_model_blocks_simple_history_watch(self):
        corpus = TranscriptCorpus([
            fight(str(i), "A", f"B{i}", "Suga lands", "Suga", "") for i in range(16)
        ] + [
            fight(f"x{i}", f"X{i}", f"Y{i}", "nothing") for i in range(64)
        ])
        market = {
            "ticker": "KX-TEST",
            "custom_strike": {"Word": "Suga"},
            "rules_primary": "If the commentator says Suga as part of the fight, resolves Yes.",
        }
        row = price_market(
            market,
            TopOfBook(yes_bid=0.73, yes_ask=0.75, no_bid=0.25, no_ask=0.27),
            corpus,
            "A",
            "B0",
            cutoff_date="2026-01-01",
            fee_buffer=0.02,
            min_fighter_fights=15,
            require_context_model=True,
        )
        self.assertEqual(row.estimate.probability_source, "simple_history")
        self.assertFalse(row.watch)

    def test_fight_model_prediction_drives_watch_when_required(self):
        class FakeFightModel:
            def predict(self, forms, fighter_1, fighter_2, event_date):
                return ContextPrediction(
                    probability=0.9,
                    status="ok",
                    note="fake fight model for test",
                    profile="stats_only_history",
                    training_rows=100,
                    validation_rows=50,
                    positive_rate=0.2,
                    validation_log_loss=0.5,
                    base_log_loss=0.6,
                    log_loss_improvement=0.1,
                    best_c=0.01,
                    calibrated=True,
                    row_source="test",
                )

        corpus = TranscriptCorpus([
            fight(str(i), "A", f"B{i}", "Suga lands", "Suga", "") for i in range(16)
        ] + [
            fight(f"x{i}", f"X{i}", f"Y{i}", "nothing") for i in range(64)
        ])
        market = {
            "ticker": "KX-TEST",
            "custom_strike": {"Word": "Suga"},
            "rules_primary": "If the commentator says Suga as part of the fight, resolves Yes.",
        }
        row = price_market(
            market,
            TopOfBook(yes_bid=0.30, yes_ask=0.40, no_bid=0.60, no_ask=0.70),
            corpus,
            "A",
            "B0",
            cutoff_date="2026-01-01",
            fee_buffer=0.02,
            min_fighter_fights=15,
            context_model=FakeFightModel(),
            require_context_model=True,
        )
        self.assertEqual(row.estimate.probability_source, "fight_context_model")
        self.assertAlmostEqual(row.estimate.probability, 0.9)
        self.assertTrue(row.watch)


class DashboardFeedTests(unittest.TestCase):
    def test_event_snapshot_contains_live_edge_and_price_movement(self):
        corpus = TranscriptCorpus([
            fight(str(i), "A", f"B{i}", "Suga lands", "Suga", "") for i in range(16)
        ] + [
            fight(f"x{i}", f"X{i}", f"Y{i}", "nothing") for i in range(64)
        ])

        class Client:
            def get_markets(self, *, event_ticker):
                return [{
                    "ticker": f"{event_ticker}-SUGA",
                    "title": "What will announcers say during A vs B0 UFC Fight?",
                    "custom_strike": {"Word": "Suga"},
                    "rules_primary": "If the commentator says Suga as part of the fight, resolves Yes.",
                }]

            def get_orderbook(self, ticker):
                return TopOfBook(yes_bid=0.30, yes_ask=0.40, no_bid=0.60, no_ask=0.70)

        rows = event_snapshot(
            Client(),
            corpus,
            {
                "event_ticker": "KXFIGHTMENTION-26JUN20AB",
                "series_ticker": "KXFIGHTMENTION",
                "title": "A vs B0",
            },
            fee_buffer=0.02,
            min_fighter_fights=15,
            snapshot_timestamp="2026-06-18T12:00:00+00:00",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["watch"], "yes")
        self.assertEqual(rows[0]["probability_source"], "simple_history")
        self.assertIn("conservative_probability", rows[0])
        self.assertEqual(rows[0]["event_date"], "2026-06-20")
        add_price_changes(rows, [{"ticker": rows[0]["ticker"], "yes_ask": "0.45"}])
        self.assertAlmostEqual(float(rows[0]["ask_change"]), -0.05)


if __name__ == "__main__":
    unittest.main()
