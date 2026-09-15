const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync, existsSync } = require('node:fs');
const { resolve } = require('node:path');
const { JSDOM } = require('jsdom');

function setup(payload = {}) {
  const dom = new JSDOM('<div id="host"></div>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.UFC_MENTION_DASHBOARD_DATA = payload;
  for (const file of ['select.js', 'book.js', 'model.js', 'ledger.js']) {
    w.eval(readFileSync(resolve(__dirname, '../../dashboard/src', file), 'utf8'));
  }
  w.MM.motion = { reduced: () => true, countUp: (el, value, opts) => { el.textContent = opts.format(value); } };
  w.MM.charts = { bars: () => {}, reliability: () => {} };
  w.MM.board = { splitPhrase: phrase => ({ word: phrase }) };
  return { w, host: w.document.querySelector('#host'), close: () => w.close() };
}

test('book caveat uses the number of recorded nights', () => {
  const { w, host, close } = setup({ performance: { equity: [
    { date: '2026-07-11', card_pnl: 3 }, { date: '2026-07-18', card_pnl: -1 },
  ] } });
  w.MM.book.mount(host);
  assert.match(host.querySelector('.book-note').textContent, /2 settled nights/);
  assert.doesNotMatch(host.textContent, /Four nights|nothing is edited/);
  close();
});

test('book without a record explains its empty charts', () => {
  const { w, host, close } = setup();
  w.MM.book.mount(host);
  assert.match(host.querySelector('#bookNights').textContent, /No settled nights/);
  assert.match(host.querySelector('#bookPhrases').textContent, /No paper trades/);
  assert.match(host.querySelector('.book-note').textContent, /No settled paper record/);
  close();
});

test('model conclusions, group counts and gate caption follow their payload', () => {
  const { w, host, close } = setup({ model_health: {
    calibration: { head_to_head: { model_log_loss: 0.4, base_log_loss: 0.3, market_log_loss: 0.5, markets: 20, cards: 2 } },
    groups: [{ phrase: 'Dana', scored_fights: 100 }, { phrase: 'Choke', scored_fights: 200 }],
    prediction: { folds: 3 },
    v2_gate: { chosen_variant: 'v2+calib', variant_means: { v1: 0.6, v2: 0.5, 'v2+calib': 0.4 }, holdout_cards: ['2026-07-11'] },
  } });
  w.MM.model.mount(host);
  assert.match(host.querySelector('.h2h-read').textContent, /trails the base rate and beats the market/);
  assert.doesNotMatch(host.textContent, /storylines the transcripts cannot see|gate refused them/);
  assert.doesNotMatch(host.textContent, /Fighter history only/);
  assert.match(host.textContent, /100 to 200 historical fights per phrase, 3 folds/);
  assert.match(host.querySelector('.figure-table .figure-note').textContent, /Event tier, recalibrated/);
  close();
});

test('missing model scores stay unavailable instead of counting to zero', () => {
  const { w, host, close } = setup();
  w.MM.model.mount(host);
  for (const value of host.querySelectorAll('.h2h-value')) assert.equal(value.textContent, 'Unavailable');
  assert.match(host.querySelector('.h2h-read').textContent, /No pre-fight comparison/);
  assert.match(host.querySelector('#modelReliability').textContent, /No calibration results/);
  assert.match(host.querySelector('#modelGroups').textContent, /No phrase test results/);
  assert.match(host.querySelector('.gate-table tbody').textContent, /No model comparison/);
  assert.doesNotMatch(host.textContent, /5 folds/);
  close();
});

test('ledger explains a zero-trade night', () => {
  const { w, host, close } = setup({ tapes: [{ card: 'EMPTY', event_date: '2026-07-11', markets: [] }] });
  w.MM.ledger.mount(host);
  assert.match(host.querySelector('#ledgerBody').textContent, /No paper trades recorded/);
  host.querySelector('[data-sort="event_date"]').click();
  assert.doesNotMatch(host.querySelector('.section-sub').textContent, /newest first/);
  host.querySelector('[data-value="2026-07-11"]').click();
  assert.match(host.querySelector('#ledgerBody').textContent, /No paper trades recorded for this night/);
  close();
});

test('unresolved contracts read pending and never appear as losses', () => {
  const { w, host, close } = setup({ trades: [{ ticker: 'PENDING', event_date: '2026-07-11', entered_at: '2026-07-11T11:00:00Z', phrase: 'Dana', fighter_1: 'First Fighter', fighter_2: 'Second Fighter', side: 'yes', price: 0.3, model_probability: 0.4, result: null, won: null, pnl: null }] });
  w.MM.ledger.mount(host);
  assert.match(host.querySelector('#ledgerBody').textContent, /Pending/);
  assert.doesNotMatch(host.querySelector('#ledgerBody').textContent, /Open|Lost/);
  host.querySelector('[data-value="lost"]').click();
  assert.equal(host.querySelector('.ledger-row'), null);
  assert.match(host.querySelector('#ledgerBody').textContent, /No contracts match these filters/);
  close();
});

test('README documents the pre-fight comparison and current page', () => {
  const text = readFileSync(resolve(__dirname, '../../README.md'), 'utf8');
  for (const value of ['0.4918', '0.4770', '0.5435', '364', '0.066', '0.045', 'Current', 'Past cards', 'Model', 'Record']) assert.ok(text.includes(value), value);
  assert.doesNotMatch(text, /0\.129|—|The disagreement grid/);
  assert.match(text, /observed said rate in that same sample/);
  assert.match(text, /requirements\.lock/);
  assert.match(text, /make install\nmake test\nmake lint/);
  assert.match(text, /http:\/\/127\.0\.0\.1:8766/);
  assert.ok(text.includes('cannot place trades'));
  assert.equal(existsSync(resolve(__dirname, '../../docs/superpowers')), false);
});

test('run instructions separate local paper recording from cloud price updates', () => {
  const text = readFileSync(resolve(__dirname, '../../README.md'), 'utf8');
  assert.match(text, /PAPER_CARD=auto \.\/start_live_dashboard\.command/);
  assert.match(text, /http:\/\/127\.0\.0\.1:8765/);
  assert.match(text, /30 seconds/);
  assert.match(text, /scheduled every 10 minutes/);
  assert.match(text, /does not record paper trades/);
  assert.match(text, /Without a verified start time, no new entries are allowed/);
  assert.match(text, /separate from the historical test/);
  assert.match(text, /No mention market/);
  const tracking = readFileSync(resolve(__dirname, '../../tracking/README.md'), 'utf8');
  assert.match(tracking, /PAPER_CARD=auto \.\/start_live_dashboard\.command/);
  assert.match(tracking, /before fees/);
  assert.match(tracking, /pending/);
  assert.doesNotMatch(tracking, /UFC Vegas 119|leans tell us/);
});

test('page description does not hardcode a sample size', () => {
  const html = readFileSync(resolve(__dirname, '../../dashboard/index.html'), 'utf8');
  const dom = new JSDOM(html);
  const description = dom.window.document.querySelector('meta[name="description"]').content;
  assert.equal(description, 'UFC announcer-mention markets on Kalshi: saved phrase prices, model estimates, and paper-trade results.');
  dom.window.close();
});
