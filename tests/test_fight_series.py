from ufc_mentions.fight_series import (
    is_fight_mention_event, discover_series_from_events, merge_series,
    series_of, SEED_SERIES,
)


def test_real_ufc_mention_event_matches():
    # A real event we recorded
    ev = {"series_ticker": "KXFIGHTMENTION",
          "event_ticker": "KXFIGHTMENTION-26JUL25ANKGUS",
          "title": "What will the announcers say during Ankalaev vs. Guskov Fight"}
    assert is_fight_mention_event(ev)


def test_renamed_series_still_caught():
    # Same market, hypothetical new series name
    ev = {"series_ticker": "KXUFCMENTION",
          "event_ticker": "KXUFCMENTION-26AUG15MAKGAR",
          "title": "What will announcers say during Makhachev vs. Garry"}
    assert is_fight_mention_event(ev)
    assert discover_series_from_events([ev]) == ["KXUFCMENTION"]


def test_false_positives_rejected():
    # These are the actual look-alikes Kalshi's live listing returns
    for title in [
        "Euphoria: New season announcement date",
        "When will Bloomberg officially announce an IPO?",
        "Will there be an announcement that The Simpsons is ending",
        "Who will be the first Democrat listed to announce a presidential run",
    ]:
        assert not is_fight_mention_event({"title": title, "event_ticker": "KX-X"})


def test_march_madness_mention_is_not_ufc():
    # A real different-sport mention series; should not be treated as UFC.
    ev = {"series_ticker": "KXMMMENTION",
          "title": "What will announcers say during the Duke vs. Alabama basketball game"}
    assert series_of(ev) == "KXMMMENTION"
    assert not is_fight_mention_event(ev)


def test_versus_and_announcers_do_not_identify_ufc():
    for series, title in [
        ("KXNFLMENTION", "What will announcers say during Packers vs. Bears?"),
        ("KXBOXINGMENTION", "What will announcers say during Boxing Fight Night: One vs. Two?"),
        ("KXMMAMENTION", "What will announcers say during PFL MMA: One vs. Two?"),
    ]:
        assert not is_fight_mention_event({"series_ticker": series, "event_ticker": series + "-26SEP19", "title": title})


def test_explicit_ufc_sport_identifies_an_unknown_series():
    assert is_fight_mention_event({"series_ticker": "NEW", "title": "UFC: What will announcers say during One vs Two?"})


def test_series_of_falls_back_to_ticker_prefix():
    assert series_of({"event_ticker": "KXFIGHTMENTION-26JUL25X"}) == "KXFIGHTMENTION"


def test_merge_keeps_seed_first_and_dedups():
    out = merge_series(["KXNEW", "KXFIGHTMENTION"], ["KXNEW", "KXNEWER"])
    assert out[0] == SEED_SERIES[0]
    assert out.count("KXNEW") == 1
    assert "KXNEWER" in out
