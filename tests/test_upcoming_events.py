import json
from datetime import date

from scripts.data.fetch_upcoming_events import (
    fetch_schedule,
    future_only,
    parse_event_page,
    parse_schedule,
    parse_update_deadline,
    refresh,
)

# Reduced excerpts from ufc.com/events and /event/cryptocom-ufc-331,
# checked September 15, 2026. The site's <time> labels differ from its epochs.
SOURCE = "https://www.ufc.com/events"
EVENT_URL = "https://www.ufc.com/event/cryptocom-ufc-331"
UPDATE_URL = "https://www.ufc.com/news/updates-cryptocom-ufc-331-van-vs-pantoja-2"
SCHEDULE = """
<article class="c-card-event--result">
<h3 class="c-card-event--result__headline"><a href="/event/cryptocom-ufc-331">Van vs Pantoja 2</a></h3>
<div class="c-card-event--result__date" data-main-card-timestamp="1789866000"
 data-prelims-card-timestamp="1789858800" data-early-card-timestamp="1789853400"></div>
<div class="c-card-event--result__location">
<h5>Crypto.com Arena</h5><p class="address"><span class="locality">Los Angeles</span>,
<span class="administrative-area">CA</span><br><span class="country">United States</span></p>
</div></article>
"""
DETAIL = """
<h1>Crypto.com UFC 331</h1>
<div class="c-hero__headline"><span>Van</span> <span>vs</span> <span>Pantoja 2</span></div>
<div class="c-event-fight-card-broadcaster__time" data-timestamp="1789866000">
<div class="field--name-fight-card-time-main"><time datetime="2026-09-19T21:00:00Z">9:00 PM</time></div></div>
<div class="c-event-fight-card-broadcaster__time" data-timestamp="1789858800">
<div class="field--name-fight-card-time-prelims"><time datetime="2026-09-19T19:00:00Z">7:00 PM</time></div></div>
<div class="c-event-fight-card-broadcaster__time" data-timestamp="1789853400">
<div class="field--name-fight-card-time-early"><time datetime="2026-09-19T17:30:00Z">5:30 PM</time></div></div>
<a href="/news/updates-cryptocom-ufc-331-van-vs-pantoja-2">Updates To Crypto.com UFC 331</a>
"""
PRESENTATION = """
<div class="c-hero__image"><img src="https://ufc.com/images/styles/background_image_sm/s3/2026-08/card.jpg?itok=verified"
 alt="Joshua Van &amp; Alexandre Pantoja side by side" /></div>
<div class="c-listing-fight">
<div class="c-listing-fight__class-text">Flyweight Title Bout</div>
<div class="c-listing-fight__corner-name--red"><a href="/athlete/joshua-van">
<span>Joshua</span> <span>Van</span></a></div>
<div class="c-listing-fight__corner-image--red"><img src="https://ufc.com/images/styles/portrait/s3/van.png" alt="Joshua Van" /></div>
<div class="c-listing-fight__corner-name--blue"><a href="/athlete/alexandre-pantoja">
<span>Alexandre</span> <span>Pantoja</span></a></div>
<div class="c-listing-fight__corner-image--blue"><img src="https://ufc.com/images/styles/portrait/s3/pantoja.png" alt="Alexandre Pantoja" /></div>
</div>
"""
UPDATE = """
<h1>Updates To Crypto.com UFC 331: Van vs Pantoja 2</h1>
<article><p>Don't miss a moment of Crypto.com UFC 331: Van vs Pantoja 2,
live from Crypto.com Arena in Los Angeles, California on September 19, 2026.
The Early Prelims begin at 5pm ET/2pm PT, followed by the Prelims at 7pm ET/4pm PT
and Main Card at 9pm ET/6pm PT.</p></article>
"""


def test_primary_schedule_keeps_sources_and_source_calendar_date():
    event, = parse_schedule(SCHEDULE)
    assert event["name"] == "Van vs Pantoja 2"
    assert event["date"] == "2026-09-19"
    assert event["venue"] == "Crypto.com Arena"
    assert event["location"] == "Los Angeles, CA United States"
    assert event["source_url"] == EVENT_URL
    assert event["entry_deadline"] == "2026-09-19T21:30:00+00:00"
    assert event["entry_deadline_source"] == SOURCE


def test_listing_rejects_unverified_links_and_bad_timestamps():
    assert parse_schedule(SCHEDULE.replace("/event/cryptocom-ufc-331", "https://example.com/event/fake")) == []
    assert parse_schedule(SCHEDULE.replace('data-main-card-timestamp="1789866000"', 'data-main-card-timestamp="invalid"')) == []


def test_detail_uses_earliest_prelim_epoch_never_local_clock_marked_z():
    detail = parse_event_page(DETAIL, EVENT_URL)
    assert detail["name"] == "Crypto.com UFC 331: Van vs Pantoja 2"
    assert detail["entry_deadline"] == "2026-09-19T21:30:00+00:00"
    assert detail["entry_deadline_source"] == EVENT_URL
    assert detail["update_urls"] == [UPDATE_URL]


def test_event_art_and_headliners_come_from_the_matching_official_fight():
    presentation = parse_event_page(DETAIL + PRESENTATION, EVENT_URL)["presentation"]
    assert presentation["source_url"] == EVENT_URL
    assert presentation["artwork"] == {
        "url": "https://ufc.com/images/styles/background_image_sm/s3/2026-08/card.jpg?itok=verified",
        "alt": "Joshua Van & Alexandre Pantoja side by side",
    }
    assert [fighter["name"] for fighter in presentation["headliners"]] == ["Joshua Van", "Alexandre Pantoja"]
    assert [fighter["display_name"] for fighter in presentation["headliners"]] == ["Van", "Pantoja"]
    assert presentation["headliners"][0]["athlete_url"] == "https://www.ufc.com/athlete/joshua-van"
    assert presentation["headliners"][1]["image_url"] == "https://ufc.com/images/styles/portrait/s3/pantoja.png"
    assert presentation["bout_label"] == "Flyweight Title Bout"
    assert presentation["is_title_bout"] is True


def test_numbered_card_is_not_itself_evidence_of_a_title_bout():
    detail = parse_event_page(DETAIL, EVENT_URL)
    assert detail["presentation"] == {}
    presentation = parse_event_page(DETAIL + PRESENTATION.replace("Flyweight Title Bout", "Flyweight Bout"), EVENT_URL)["presentation"]
    assert presentation["is_title_bout"] is False
    assert presentation["bout_label"] == "Flyweight Bout"


def test_unmatched_card_headline_does_not_borrow_other_fighters_or_titles():
    presentation = parse_event_page(DETAIL.replace("Pantoja 2", "Silva") + PRESENTATION, EVENT_URL)["presentation"]
    assert "artwork" in presentation
    assert "headliners" not in presentation
    assert "is_title_bout" not in presentation
    assert "bout_label" not in presentation


def test_untrusted_or_malformed_art_is_omitted_without_losing_start_time():
    for replacement in ("https://ufc.com.evil.test/images/", "https://evil.test/images/", "http://ufc.com/images/", "javascript:alert(1)/", "https://ufc.com@evil.test/images/", "https://[broken/images/", "https://ufc.com:999/images/"):
        detail = parse_event_page(DETAIL + PRESENTATION.replace("https://ufc.com/images/", replacement), EVENT_URL)
        assert "artwork" not in detail["presentation"]
        assert all("image_url" not in fighter for fighter in detail["presentation"]["headliners"])
        assert detail["entry_deadline"] == "2026-09-19T21:30:00+00:00"


def test_mixed_official_page_keeps_images_scoped_to_the_hero_and_headliners():
    unrelated = '<img src="https://ufc.com/images/unrelated.jpg" alt="Other fighter" />'
    detail = parse_event_page(unrelated + DETAIL + PRESENTATION, EVENT_URL)
    assert "card.jpg" in detail["presentation"]["artwork"]["url"]
    assert "unrelated" not in json.dumps(detail["presentation"])


def test_artwork_uses_an_actual_desktop_srcset_url_not_a_guessed_variant():
    sources = """<source width="2000" srcset="https://ufc.com/images/large.jpg?itok=a 1x, https://ufc.com/images/large2.jpg 2x" />
    <source width="1200" srcset="https://ufc.com/images/desktop.jpg?itok=b 1x, https://ufc.com/images/desktop2.jpg 2x" />
    <source width="992" srcset="https://ufc.com/images/tablet.jpg 1x" />"""
    html = PRESENTATION.replace('<div class="c-hero__image">', '<div class="c-hero__image">' + sources)
    presentation = parse_event_page(DETAIL + html, EVENT_URL)["presentation"]
    assert presentation["artwork"]["url"] == "https://ufc.com/images/desktop.jpg?itok=b"


def test_missing_portraits_do_not_create_placeholder_people():
    html = PRESENTATION.replace('src="https://ufc.com/images/styles/portrait/s3/van.png"', "")
    presentation = parse_event_page(DETAIL + html, EVENT_URL)["presentation"]
    assert presentation["headliners"][0] == {"name": "Joshua Van", "display_name": "Van", "athlete_url": "https://www.ufc.com/athlete/joshua-van"}


def test_headliner_display_name_uses_the_ufc_billing_not_assumed_name_order():
    html = (DETAIL + PRESENTATION).replace("Pantoja 2", "Wang 2").replace(
        "<span>Alexandre</span> <span>Pantoja</span>", "<span>Wang</span> <span>Cong</span>")
    presentation = parse_event_page(html, EVENT_URL)["presentation"]
    assert presentation["headliners"][1]["name"] == "Wang Cong"
    assert presentation["headliners"][1]["display_name"] == "Wang"


def test_headliner_display_name_keeps_suffix_punctuation_and_full_billing():
    html = (DETAIL + PRESENTATION).replace("Van", "Rosas Jr.").replace("Joshua", "Raul")
    presentation = parse_event_page(html, EVENT_URL)["presentation"]
    assert presentation["headliners"][0]["name"] == "Raul Rosas Jr."
    assert presentation["headliners"][0]["display_name"] == "Rosas Jr."


def test_malformed_optional_athlete_link_does_not_break_the_card_deadline():
    html = PRESENTATION.replace('href="/athlete/joshua-van"', 'href="https://[broken/athlete/joshua-van"')
    detail = parse_event_page(DETAIL + html, EVENT_URL)
    assert detail["entry_deadline"] == "2026-09-19T21:30:00+00:00"
    assert "athlete_url" not in detail["presentation"]["headliners"][0]
    assert detail["presentation"]["headliners"][0]["name"] == "Joshua Van"


def test_headline_matching_is_whole_words_not_part_of_someone_elses_name():
    presentation = parse_event_page(DETAIL.replace("Pantoja 2", "Pant") + PRESENTATION, EVENT_URL)["presentation"]
    assert "headliners" not in presentation


def test_headliner_matching_allows_published_given_name_and_accents():
    html = (DETAIL + PRESENTATION).replace("Van", "V\u00e1n").replace("Pantoja 2", "Alexandre")
    presentation = parse_event_page(html, EVENT_URL)["presentation"]
    assert [fighter["name"] for fighter in presentation["headliners"]] == ["Joshua V\u00e1n", "Alexandre Pantoja"]


def test_schedule_refresh_passes_through_presentation_without_creating_markets():
    pages = {SOURCE: SCHEDULE, EVENT_URL: DETAIL + PRESENTATION, UPDATE_URL: UPDATE}
    event, = fetch_schedule(fetch_html=pages.__getitem__, today=date(2026, 9, 15))["events"]
    assert event["presentation"]["is_title_bout"] is True
    assert "fights" not in event


def test_main_card_time_alone_is_not_an_entry_deadline():
    html = '<h1>UFC</h1><div class="c-event-fight-card-broadcaster__time" data-timestamp="1789866000"><div class="field--name-fight-card-time-main"></div></div>'
    assert parse_event_page(html, EVENT_URL)["entry_deadline"] is None
    listing = SCHEDULE.replace('data-prelims-card-timestamp="1789858800"', "").replace('data-early-card-timestamp="1789853400"', "")
    assert parse_schedule(listing)[0]["entry_deadline"] is None


def test_update_deadline_requires_same_card_and_explicit_date_and_zone():
    name = "Crypto.com UFC 331: Van vs Pantoja 2"
    assert parse_update_deadline(UPDATE, name, "2026-09-19") == "2026-09-19T21:00:00+00:00"
    assert parse_update_deadline(UPDATE, name, "2026-09-26") is None
    assert parse_update_deadline(UPDATE, "UFC 332: Silva vs Wang", "2026-09-19") is None
    assert parse_update_deadline(UPDATE.replace("5pm ET", "5pm"), name, "2026-09-19") is None


def test_future_only_sorted_ascending():
    events = [{"date": "2026-10-17"}, {"date": "2026-09-19"}, {"date": "2026-09-26"}]
    assert [e["date"] for e in future_only(events, date(2026, 9, 20))] == ["2026-09-26", "2026-10-17"]
    assert future_only(events, date(2027, 1, 1)) == []


def test_refresh_uses_earlier_sourced_update_without_inventing_fights(tmp_path):
    pages = {SOURCE: SCHEDULE, EVENT_URL: DETAIL, UPDATE_URL: UPDATE}
    out = tmp_path / "upcoming_events.json"
    note = refresh(out, fetch_html=pages.__getitem__, today=date(2026, 9, 15))
    assert "1 upcoming" in note
    saved = json.loads(out.read_text())
    assert saved["source_url"] == SOURCE
    assert saved["fetched_at"]
    event, = saved["events"]
    assert event["name"] == "Crypto.com UFC 331: Van vs Pantoja 2"
    assert event["entry_deadline"] == "2026-09-19T21:00:00+00:00"
    assert event["entry_deadline_source"] == UPDATE_URL
    assert "earlier" in event["entry_deadline_note"]
    assert "fights" not in event


def test_unreadable_linked_update_blocks_a_new_deadline(tmp_path):
    pages = {SOURCE: SCHEDULE, EVENT_URL: DETAIL}
    out = tmp_path / "upcoming_events.json"
    refresh(out, fetch_html=pages.__getitem__, today=date(2026, 9, 15))
    event, = json.loads(out.read_text())["events"]
    assert event["name"] == "Crypto.com UFC 331: Van vs Pantoja 2"
    assert event["entry_deadline"] is None
    assert "verify" in event["entry_deadline_note"]


def test_refresh_error_keeps_previous_cache_byte_for_byte(tmp_path):
    out = tmp_path / "upcoming_events.json"
    original = '{"fetched_at":"old","events":[{"name":"OLD"}]}'
    out.write_text(original)

    def broken_fetch(url):
        raise RuntimeError("network down")

    assert "kept previous" in refresh(out, fetch_html=broken_fetch)
    assert out.read_text() == original


def test_empty_primary_response_never_replaces_previous_cache(tmp_path):
    out = tmp_path / "upcoming_events.json"
    out.write_text('{"events":[{"name":"OLD"}]}')
    assert "kept previous" in refresh(out, fetch_html=lambda url: "<html></html>")
    assert json.loads(out.read_text())["events"][0]["name"] == "OLD"


def test_schedule_follows_official_pagination_and_deduplicates_events():
    next_url = SOURCE + "?page=1"
    pages = {SOURCE: SCHEDULE + '<a rel="next" href="?page=1">Load more</a>',
             next_url: SCHEDULE, EVENT_URL: DETAIL, UPDATE_URL: UPDATE}
    called = []

    def fetch(url):
        called.append(url)
        return pages[url]

    payload = fetch_schedule(fetch_html=fetch, today=date(2026, 9, 15))
    assert next_url in called
    assert len(payload["events"]) == 1


def test_repeated_pagination_is_a_failure_not_a_complete_empty_scan(tmp_path):
    out = tmp_path / "upcoming_events.json"
    html = SCHEDULE + '<a rel="next" href="/events">Load more</a>'
    note = refresh(out, fetch_html=lambda url: html, today=date(2026, 9, 15))
    assert "repeated a pagination link" in note
    assert not out.exists()


def test_detail_failure_keeps_known_event_visible_without_a_deadline(tmp_path):
    out = tmp_path / "upcoming_events.json"
    refresh(out, fetch_html={SOURCE: SCHEDULE}.__getitem__, today=date(2026, 9, 15))
    payload = json.loads(out.read_text())
    event, = payload["events"]
    assert event["name"] == "Van vs Pantoja 2"
    assert event["source_url"] == EVENT_URL
    assert event["entry_deadline"] is None
    assert payload["warnings"]
