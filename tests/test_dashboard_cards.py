import unittest

from ufc_mentions.build_dashboard_data import build_kalshi_cards, build_kalshi_rows


class DashboardCardTests(unittest.TestCase):
    def test_event_without_priced_rows_still_appears_as_tbd(self):
        live_rows = build_kalshi_rows([
            {
                "event_ticker": "KXFIGHTMENTION-26JUL11AAA",
                "series_ticker": "KXFIGHTMENTION",
                "event_date": "2026-07-11",
                "event_title": "What will the announcers say during Alpha One vs Beta Two Fight",
                "fighter_1": "Alpha One",
                "fighter_2": "Beta Two",
                "ticker": "KXFIGHTMENTION-26JUL11AAA-CHOK",
                "phrase": "Choke / Choked / Chokehold",
                "probability_source": "fight_context_model",
                "yes_ask": "0.40",
                "edge": "0.04",
                "watch": "no",
                "status": "ok",
            }
        ])
        meta = {
            "events": [
                {
                    "event_ticker": "KXFIGHTMENTION-26JUL11AAA",
                    "series_ticker": "KXFIGHTMENTION",
                    "event_date": "2026-07-11",
                    "sub_title": "Alpha One vs Beta Two Fight",
                    "market_rows": 1,
                    "priced_rows": 1,
                },
                {
                    "event_ticker": "KXFIGHTMENTION-26JUL11TBD",
                    "series_ticker": "KXFIGHTMENTION",
                    "event_date": "2026-07-11",
                    "title": "UFC 999",
                    "market_rows": 0,
                    "priced_rows": 0,
                },
            ]
        }

        cards = build_kalshi_cards(meta, live_rows, hidden_events=set())

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["card_title"], "UFC 999")
        self.assertEqual(cards[0]["fight_count"], 2)
        self.assertEqual(cards[0]["tradable_fight_count"], 1)
        fights = {fight["event_ticker"]: fight for fight in cards[0]["fights"]}
        self.assertEqual(fights["KXFIGHTMENTION-26JUL11AAA"]["odds_status"], "live")
        self.assertEqual(fights["KXFIGHTMENTION-26JUL11TBD"]["odds_status"], "tbd")
        self.assertEqual(fights["KXFIGHTMENTION-26JUL11TBD"]["matchup"], "TBD fights")
        self.assertFalse(fights["KXFIGHTMENTION-26JUL11TBD"]["tradable"])


if __name__ == "__main__":
    unittest.main()
