const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

// Synthetic presentation data. Never used in the dashboard feed.
function fixture() {
  return { upcoming_events: [{
    date: '2026-09-19', name: 'UFC 999: First vs Second', venue: 'Test arena',
    source_url: 'https://www.ufc.com/event/test-card',
    presentation: {
      source_url: 'https://www.ufc.com/event/test-card',
      artwork: { url: 'https://ufc.com/images/test-event.jpg', alt: 'Test event artwork' },
      headliners: [
        { name: 'First Fighter', image_url: 'https://ufc.com/images/first.png', image_alt: 'First Fighter' },
        { name: 'Second Fighter', image_url: 'https://ufc.com/images/second.png', image_alt: 'Second Fighter' },
      ],
      is_title_bout: true, bout_label: 'Flyweight Title Bout',
    },
  }] };
}
function setup(t, data = fixture()) {
  const dom = new JSDOM('<section id="live"></section>', { url: 'https://example.test/', runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.UFC_MENTION_DASHBOARD_DATA = data;
  dom.window.eval(fs.readFileSync(path.resolve(__dirname, '../../dashboard/src/live.js'), 'utf8'));
  const view = dom.window.MM.live.mount(dom.window.document.querySelector('#live'), { now: () => Date.parse('2026-09-15T21:00:00Z'), autoStart: false });
  return { d: dom.window.document, w: dom.window, view };
}

test('verified title cards use their real headliners and official event artwork', t => {
  const { d } = setup(t);
  const card = d.querySelector('.event-card');
  assert.equal(card.dataset.kind, 'numbered');
  assert.equal(card.dataset.featured, 'true');
  assert.equal(card.dataset.championship, 'true');
  assert.equal(card.dataset.tone, 'amber');
  assert.match(card.querySelector('.event-card-title').textContent, /First Fighter.*Second Fighter/);
  assert.match(card.querySelector('.event-title-bout').textContent, /Flyweight Title Bout/);
  assert.equal(card.querySelectorAll('.event-poster-art img').length, 1);
  assert.equal(card.querySelector('.event-poster-art img').src, 'https://ufc.com/images/test-event.jpg');
  assert.equal(card.querySelectorAll('.live-markets').length, 0);
});

test('a numbered event alone does not invent a championship or any fighters', t => {
  const data = fixture(); delete data.upcoming_events[0].presentation;
  const { d } = setup(t, data);
  assert.equal(d.querySelector('.event-card').dataset.kind, 'numbered');
  assert.equal(d.querySelector('.event-title-bout'), null);
  assert.equal(d.querySelector('img'), null);
  assert.match(d.querySelector('.event-card-title').textContent, /UFC 999: First vs Second/);
});

test('fight nights have stable art direction when the schedule order changes', t => {
  const data = fixture();
  data.upcoming_events.push({ date: '2026-09-26', name: 'UFC Fight Night: Third vs Fourth' });
  const { d, view } = setup(t, data);
  const night = d.querySelector('[data-kind="fight-night"]');
  const tone = night.dataset.tone;
  assert.equal(night.querySelector('.event-poster-number').textContent, 'FN');
  view.update({ upcoming_events: data.upcoming_events.slice(1) });
  assert.equal(d.querySelector('.event-card').dataset.tone, tone);
});

test('untrusted artwork and unsourced title labels are not rendered', t => {
  const data = fixture();
  data.upcoming_events[0].presentation.source_url = 'https://example.test/event/fake';
  const { d } = setup(t, data);
  assert.equal(d.querySelector('img'), null);
  assert.equal(d.querySelector('.event-title-bout'), null);
});

test('failed event art falls back to fighter portraits, then a readable typography poster', t => {
  const { d, w, view } = setup(t);
  assert.equal(d.querySelector('.event-poster-art img').src, 'https://ufc.com/images/test-event.jpg');
  d.querySelector('.event-poster-art img').dispatchEvent(new w.Event('error'));
  assert.equal(d.querySelectorAll('.event-portrait').length, 2);
  assert.equal(d.querySelector('.event-portrait').src, 'https://ufc.com/images/first.png');
  d.querySelector('.event-portrait').dispatchEvent(new w.Event('error'));
  assert.equal(d.querySelector('img'), null);
  assert.match(d.querySelector('.event-card-title').textContent, /First Fighter/);
  view.update(fixture());
  assert.equal(d.querySelector('img'), null, 'A failed URL must not reload every polling cycle');
});

test('presentation survives merging schedule metadata into Kalshi cards', t => {
  const data = fixture();
  data.kalshi_cards = [{ card_id: 'TEST', card_title: data.upcoming_events[0].name, event_date: '2026-09-19', fights: [] }];
  const { d } = setup(t, data);
  assert.equal(d.querySelectorAll('.event-card').length, 1);
  assert.equal(d.querySelector('.event-poster-art img').src, 'https://ufc.com/images/test-event.jpg');
});

test('external image hosts and credential-bearing URLs cannot enter a poster', t => {
  const data = fixture();
  const p = data.upcoming_events[0].presentation;
  p.headliners[0].image_url = 'https://ufc.com.evil.test/images/first.png';
  p.artwork.url = 'https://user:password@ufc.com/images/test-event.jpg';
  const { d } = setup(t, data);
  assert.equal(d.querySelector('img'), null);
});

test('poster names retain surname suffixes and a sourced rematch number', t => {
  const data = fixture();
  data.upcoming_events[0].name = 'UFC 999: Rosas Jr. vs Fighter 2';
  data.upcoming_events[0].presentation.headliners[0].name = 'Raul Rosas Jr.';
  const { d } = setup(t, data);
  const fighters = [...d.querySelectorAll('.event-fighter')];
  assert.equal(fighters[0].querySelector('.event-fighter-given').textContent.trim(), 'Raul');
  assert.match(fighters[0].lastChild.textContent, /^Rosas Jr\.$/);
  assert.match(fighters[1].textContent, /Second Fighter 2$/);
});

test('cards without markets start closed and their control follows the open state', t => {
  const { d, w, view } = setup(t);
  const card = d.querySelector('.event-card');
  assert.equal(card.open, false);
  assert.equal(card.querySelector('.event-card-cta-label').textContent, 'Explore card');
  card.open = true;
  card.dispatchEvent(new w.Event('toggle'));
  assert.equal(card.querySelector('.event-card-cta-label').textContent, 'Close card');
  view.update(fixture());
  assert.equal(d.querySelector('.event-card').open, true);
  assert.equal(d.querySelector('.event-card-cta-label').textContent, 'Close card');
});

test('the page headline retains a space when its line break is hidden', t => {
  const { d } = setup(t);
  assert.equal(d.querySelector('.live-title').textContent, 'Fight night, word by word.');
});

test('headline emphasis follows the official matchup name, not a guessed family name', t => {
  const data = fixture();
  data.upcoming_events[0].presentation.headliners[1] = { name: 'Wang Cong', display_name: 'Wang' };
  const { d } = setup(t, data);
  const fighter = d.querySelectorAll('.event-fighter')[1];
  assert.equal(fighter.querySelector('.event-fighter-given').textContent.trim(), 'Wang Cong');
  assert.equal(fighter.lastChild.textContent, 'Wang');
});

test('unannounced headliners get an honest placeholder without repeating the card number', t => {
  const data = fixture();
  data.upcoming_events[0].name = 'UFC 999: TBD vs TBD';
  delete data.upcoming_events[0].presentation;
  const { d } = setup(t, data);
  assert.equal(d.querySelector('.event-card-title').textContent, 'Main event to be announced');
  assert.match(d.querySelector('.event-poster').getAttribute('aria-label'), /UFC 999: TBD vs TBD/);
  assert.equal(d.querySelector('.event-title-bout'), null);
});

test('incomplete optional fighter metadata does not break the card or claim a title bout', t => {
  const data = fixture();
  data.upcoming_events[0].presentation.headliners[1] = null;
  const { d } = setup(t, data);
  assert.match(d.querySelector('.event-card-title').textContent, /UFC 999/);
  assert.equal(d.querySelector('.event-title-bout'), null);
  assert.equal(d.querySelector('.event-poster-art img').src, 'https://ufc.com/images/test-event.jpg');
});
