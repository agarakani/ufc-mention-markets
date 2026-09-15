const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const NOW = Date.parse('2026-09-15T21:00:00Z');
function setup(t, payload = {}, url = 'https://example.test/') {
  const dom = new JSDOM('<section id="live"></section>', { url, runScripts: 'outside-only' });
  t.after(() => dom.window.close());
  dom.window.UFC_MENTION_DASHBOARD_DATA = payload;
  dom.window.eval(fs.readFileSync(path.resolve(__dirname, '../../dashboard/src/live.js'), 'utf8'));
  const view = dom.window.MM.live.mount(dom.window.document.querySelector('#live'), { now: () => NOW, autoStart: false });
  return { w: dom.window, d: dom.window.document, view };
}
function fixture() {
  return {
    live_status: { state: 'ready', checked_at: '2026-09-15T20:59:50Z', paper_enabled: true, refresh_seconds: 30 },
    upcoming_events: [{ date: '2026-09-19', name: 'UFC test card', source_url: 'https://www.ufc.com/event/test', entry_deadline: '2026-09-19T21:00:00Z' }],
    kalshi_cards: [{ card_id: 'TEST', event_date: '2026-09-19', card_title: 'UFC test card', entry_deadline: '2026-09-19T21:00:00Z', fights: [
      { event_ticker: 'TEST-FIGHT', matchup: 'First Fighter vs Second Fighter' },
      { event_ticker: 'SECOND-FIGHT', matchup: 'Third Fighter vs Fourth Fighter' },
    ] }],
    kalshi: [{ ticker: 'TEST-WORD', event_ticker: 'TEST-FIGHT', phrase: 'Choke / Choked', model_probability: .25, probability_source: 'fight_context_model', yes_ask: .62, no_ask: .43, watch: true, hurdle: .14, market_status: 'active', snapshot_timestamp: '2026-09-15T20:59:50Z' }],
  };
}

test('the schedule is visible even before mention markets are listed', t => {
  const { d } = setup(t, { upcoming_events: [{ date: '2026-09-19', name: 'UFC test card' }] });
  assert.match(d.querySelector('.event-card-title').textContent, /UFC test card/);
  assert.match(d.querySelector('.event-card').textContent, /Mention markets not listed/);
  assert.match(d.querySelector('.event-card').textContent, /Fights and phrases will appear/);
  assert.equal(d.querySelector('.live-markets'), null);
  assert.equal(d.querySelector('h1').id, 'liveTitle');
});

test('only current cards are shown and no card name or fight is invented', t => {
  const { d } = setup(t, { upcoming_events: [{ date: '2026-07-25', name: 'Old card' }, { date: '2026-09-19', name: 'Known card' }] });
  assert.equal(d.querySelectorAll('.event-card').length, 1);
  assert.doesNotMatch(d.querySelector('.live-cards').textContent, /Old card/);
});

test('edges use the actual YES and NO buy prices, not the last trade percentage', t => {
  const { d } = setup(t, fixture());
  const row = d.querySelector('.live-markets tbody tr');
  assert.match(row.textContent, /62¢/);
  assert.match(row.textContent, /43¢/);
  assert.match(row.textContent, /25%/);
  assert.match(row.querySelector('.live-edge').textContent, /32\.0 pts/);
  assert.equal(row.querySelector('.live-side').textContent, 'NO');
  assert.match(row.querySelector('.live-call').textContent, /Meets entry rule/);
  assert.doesNotMatch(row.textContent, /Bought/);
});

test('stale quotes never look like fresh paper entry signals', t => {
  const data = fixture();
  data.kalshi[0].snapshot_timestamp = '2026-09-14T21:00:00Z';
  const { d } = setup(t, data);
  assert.match(d.querySelector('.live-call').textContent, /Old quote/);
  assert.doesNotMatch(d.querySelector('.live-call').textContent, /Meets entry/);
});

test('card start, closed books and missing fight models block entry labels', t => {
  for (const patch of [{ market_status: 'closed' }, { model_probability: null }, { paper_eligible: false, paper_block_reason: 'card_started' }]) {
    const data = fixture();
    Object.assign(data.kalshi[0], patch);
    const { d } = setup(t, data);
    assert.doesNotMatch(d.querySelector('.live-call').textContent, /Meets entry/);
  }
});

test('updates keep the selected fight and open card without stealing focus', t => {
  const data = fixture();
  const { d, view } = setup(t, data);
  const button = d.querySelector('[data-fight="SECOND-FIGHT"]');
  button.click();
  d.querySelector('.event-card').open = true;
  d.querySelector('[data-fight="SECOND-FIGHT"]').focus();
  view.update({ ...data, generated_at: '2026-09-15T21:00:00Z' });
  assert.equal(d.querySelector('.event-card').open, true);
  assert.equal(d.activeElement.dataset.fight, 'SECOND-FIGHT');
  assert.equal(d.querySelector('[data-fight="SECOND-FIGHT"]').getAttribute('aria-pressed'), 'true');
});

test('cloud price updates do not claim that the paper collector is running', t => {
  const data = fixture();
  data.live_status = { ...data.live_status, source: 'cloud', paper_enabled: false };
  const { d } = setup(t, data);
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
  assert.doesNotMatch(d.querySelector('.live-call').textContent, /Meets entry/);
});

test('a rejected update keeps the last snapshot and shows the failure', async t => {
  const { d, w, view } = setup(t, fixture());
  w.fetch = async () => { throw new Error('network unavailable'); };
  await view.refresh();
  assert.match(d.querySelector('.live-status').textContent, /Update failed/);
  assert.equal(d.querySelectorAll('.event-card').length, 1);
  assert.doesNotMatch(d.querySelector('.live-call').textContent, /Meets entry/);
});

test('a successful refresh replaces prices and clears stale UI without reloading the page', async t => {
  const data = fixture();
  const { d, w, view } = setup(t, data);
  const next = fixture();
  next.kalshi[0].no_ask = .5;
  w.fetch = async () => ({ ok: true, text: async () => 'window.UFC_MENTION_DASHBOARD_DATA = ' + JSON.stringify(next) + ';' });
  await view.refresh();
  assert.match(d.querySelector('.live-markets tbody tr').textContent, /50¢/);
  assert.match(d.querySelector('.live-edge').textContent, /25\.0 pts/);
});

test('phrase calculations expand across the table and keep focus through updates', t => {
  const data = fixture();
  const { d, view } = setup(t, data);
  const button = d.querySelector('button.phrase-rule');
  assert.ok(button, 'phrase expansion is a keyboard-operable button');
  button.focus();
  button.click();
  const panel = d.getElementById(d.activeElement.getAttribute('aria-controls'));
  assert.equal(panel.hidden, false);
  assert.equal(panel.querySelector('td').colSpan, 7);
  assert.match(panel.textContent, /YES a 25% chance and NO a 75% chance/);
  view.update(data);
  assert.equal(d.activeElement.dataset.word, 'TEST-WORD');
  assert.equal(d.activeElement.getAttribute('aria-expanded'), 'true');
  d.activeElement.click();
  assert.equal(d.getElementById(d.activeElement.getAttribute('aria-controls')).hidden, true);
});

test('refresh keeps keyboard focus on its button during and after loading', async t => {
  const { d, w, view } = setup(t, fixture());
  let finish;
  w.fetch = () => new Promise(resolve => { finish = resolve; });
  d.querySelector('#liveRefresh').focus();
  const pending = view.refresh();
  assert.equal(d.activeElement.id, 'liveRefresh');
  assert.equal(d.activeElement.disabled, false);
  assert.equal(d.activeElement.getAttribute('aria-disabled'), 'true');
  finish({ ok: true, text: async () => 'window.UFC_MENTION_DASHBOARD_DATA = ' + JSON.stringify(fixture()) + ';' });
  await pending;
  assert.equal(d.activeElement.id, 'liveRefresh');
  assert.equal(d.activeElement.getAttribute('aria-disabled'), 'false');
});

test('updates preserve horizontal quote position and focus on a card source link', t => {
  const data = fixture();
  const { d, view } = setup(t, data);
  const source = d.querySelector('.event-location a');
  source.focus();
  d.querySelector('.event-card .live-market-wrap').scrollLeft = 180;
  view.update(data);
  assert.equal(d.activeElement.href, source.href);
  assert.equal(d.querySelector('.event-card .live-market-wrap').scrollLeft, 180);
});

function responseSnapshot(payload) {
  return { ok: true, text: async () => 'window.UFC_MENTION_DASHBOARD_DATA = ' + JSON.stringify(payload) + ';' };
}
function responseStatus(status) { return { ok: true, json: async () => ({ ok: true, live_status: status }) }; }

test('local refresh checks the actual runtime and prefers its heartbeat to the saved one', async t => {
  const payload = fixture();
  payload.live_status.collector_checked_at = '2026-09-14T21:00:00Z';
  const { d, w, view } = setup(t, payload, 'http://127.0.0.1:8901/');
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
  const calls = [];
  w.fetch = async address => {
    calls.push(address);
    if (address === '/api/refresh') return { ok: true, json: async () => ({ ok: true }) };
    if (address === '/api/status') return responseStatus({ state: 'ready', checked_at: '2026-09-15T20:59:59Z', paper_enabled: true, error: '' });
    return responseSnapshot(payload);
  };
  await view.refresh();
  assert.equal(calls[0], '/api/refresh');
  assert.equal(calls.filter(call => call === '/api/status').length, 1);
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector on/);
  assert.equal(w.UFC_MENTION_DASHBOARD_DATA.live_status.collector_checked_at, '2026-09-15T20:59:59Z');
  assert.equal(d.querySelector('.live-call').textContent, 'Meets entry rule');
});

test('automatic local checks read status and data without requesting a collector run', async t => {
  const { d, w, view } = setup(t, fixture(), 'http://localhost:8901/');
  const calls = [];
  w.fetch = async address => {
    calls.push(address);
    return address === '/api/status' ? responseStatus({ state: 'ready', checked_at: '2026-09-15T20:59:59Z', paper_enabled: false, error: '' }) : responseSnapshot(fixture());
  };
  await view.refresh(false);
  assert.equal(calls.includes('/api/refresh'), false);
  assert.equal(calls.includes('/api/status'), true);
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
});

test('a failed or malformed local status cannot reuse an old collector-on claim', async t => {
  for (const statusResponse of [
    { ok: false, json: async () => ({ ok: false, live_status: { state: 'error', error: 'Collector stopped' } }) },
    { ok: true, json: async () => ({ ok: true, live_status: {} }) },
  ]) {
    const { d, w, view } = setup(t, fixture(), 'http://127.0.0.1:8901/');
    w.fetch = async address => address === '/api/status' ? statusResponse : responseSnapshot(fixture());
    await view.refresh(false);
    assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
    assert.doesNotMatch(d.querySelector('.live-call').textContent, /Meets entry/);
    assert.equal(d.querySelector('.live-status').dataset.state, 'error');
  }
});

test('a failed manual collector refresh is not presented as a successful update', async t => {
  const { d, w, view } = setup(t, fixture(), 'http://localhost:8901/');
  w.fetch = async address => {
    if (address === '/api/refresh') return { ok: true, json: async () => ({ ok: false, error: 'Still starting up' }) };
    if (address === '/api/status') return responseStatus({ state: 'ready', checked_at: '2026-09-15T20:59:59Z', paper_enabled: true, error: '' });
    return responseSnapshot(fixture());
  };
  await view.refresh();
  assert.match(d.querySelector('.live-status').textContent, /Update failed/);
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
});

test('public sites never call local runtime APIs', async t => {
  for (const address of ['https://example.test/', 'http://localhost.example.test/', 'https://localhost/']) {
    const { w, view } = setup(t, fixture(), address);
    const calls = [];
    w.fetch = async url => { calls.push(url); return responseSnapshot(fixture()); };
    await view.refresh();
    assert.equal(calls.length, 1);
    assert.match(calls[0], /^data\.js\?/);
  }
});

test('a file preview reloads only its snapshot script, never a runtime API', async t => {
  const { d, w, view } = setup(t, fixture(), 'file:///test/dashboard/index.html');
  w.fetch = async () => { assert.fail('file previews must not fetch runtime APIs'); };
  const pending = view.refresh();
  const script = d.querySelector('script[src^="data.js?"]');
  assert.ok(script);
  w.UFC_MENTION_DASHBOARD_DATA = fixture();
  script.onload();
  await pending;
  assert.equal(d.querySelector('script[src^="data.js?"]'), null);
  assert.equal(d.querySelector('#live').getAttribute('aria-busy'), 'false');
});

test('a local runtime request times out and leaves the last prices visibly offline', async t => {
  const { d, w, view } = setup(t, fixture(), 'http://localhost:8901/');
  let timeout;
  w.setTimeout = (callback, delay) => { assert.equal(delay, 30000); timeout = callback; return 1; };
  w.clearTimeout = () => {};
  w.fetch = (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  });
  const pending = view.refresh();
  timeout();
  await pending;
  assert.equal(d.querySelector('#live').getAttribute('aria-busy'), 'false');
  assert.match(d.querySelector('.live-status').textContent, /Update failed/);
  assert.match(d.querySelector('.paper-live').textContent, /Paper collector offline/);
  assert.match(d.querySelector('.live-markets tbody tr').textContent, /43¢/);
});
