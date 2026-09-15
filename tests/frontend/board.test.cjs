const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { JSDOM } = require('jsdom');

function setup() {
  const dom = new JSDOM('<div id="board"></div><div id="timeline"></div>', { runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  const queue = [];
  w.requestAnimationFrame = fn => { queue.push(fn); return queue.length; };
  w.cancelAnimationFrame = () => {};
  for (const file of ['select.js', 'board.js', 'timeline.js']) w.eval(readFileSync(resolve(__dirname, '../../dashboard/src', file), 'utf8'));
  w.MM.motion = { afterPaint: fn => queue.push(fn), reduced: () => true };
  const market = { ticker: 'TEST-WORD', phrase: 'Dana / Dana White / White', fighter_1: 'Abdul-Kareem Al-Selwady', fighter_2: 'Test Opponent', ask: [null, 0.48], model: [null, 0.36], result: null };
  const night = { date: '2026-07-11', frames: 2, stamps: ['2026-07-10T12:00:00Z', '2026-07-11T12:00:00Z'], markets: [market], fights: [{ fighter_1: market.fighter_1, fighter_2: market.fighter_2, event_ticker: 'TEST', markets: [market], trades: 0, said: 0 }] };
  return { w, night, flush: () => { while (queue.length) queue.shift()(); }, close: () => w.close() };
}

test('tile announces the exact phrase, fighters, quote and independent model number', () => {
  const { w, night, flush, close } = setup();
  w.MM.board.mount(w.document.querySelector('#board'), night);
  flush();
  const tile = w.document.querySelector('.tile');
  const label = tile.getAttribute('aria-description');
  assert.equal(tile.getAttribute('aria-label'), tile.textContent.trim().replace(/\s+/g, ' '));
  assert.match(label, /Dana \/ Dana White \/ White/);
  assert.match(label, /Abdul-Kareem Al-Selwady versus Test Opponent/);
  assert.match(label, /Yes price 48 cents/);
  assert.match(label, /Our number 36%/);
  assert.match(label, /Result pending/);
  assert.equal(w.document.querySelector('.fight-names').tagName, 'H2');
  close();
});

test('an unresolved final frame and missing quotes have explicit states', () => {
  const { w, night, flush, close } = setup();
  const board = w.MM.board.mount(w.document.querySelector('#board'), night);
  flush();
  assert.equal(w.document.querySelector('.tile-state').textContent, 'Pending');
  assert.equal(w.document.querySelector('.tile.is-unsaid'), null);
  board.setFrame(0);
  flush();
  assert.match(w.document.querySelector('.tile').getAttribute('aria-description'), /Yes price unavailable/);
  assert.match(w.document.querySelector('.tile').getAttribute('aria-description'), /Our number unavailable/);
  close();
});

test('empty and single-frame recordings do not create an invalid slider', () => {
  const { w, night, close } = setup();
  const host = w.document.querySelector('#timeline');
  w.MM.timeline.mount(host, { ...night, frames: 0, stamps: [], markets: [] });
  assert.equal(host.querySelector('[role="slider"]'), null);
  assert.match(host.textContent, /No recorded prices/);
  w.MM.timeline.mount(host, { ...night, frames: 1, stamps: night.stamps.slice(0, 1) });
  assert.equal(host.querySelector('[role="slider"]'), null);
  assert.match(host.textContent, /One recorded snapshot/);
  assert.doesNotMatch(host.innerHTML, /NaN|Infinity/);
  close();
});

test('arrow keys, Home and End select recorded frames', () => {
  const { w, night, flush, close } = setup();
  const seen = [];
  w.MM.timeline.mount(w.document.querySelector('#timeline'), night, { onFrame: i => seen.push(i) });
  const slider = w.document.querySelector('[role="slider"]');
  for (const [key, value] of [['Home', '0'], ['ArrowRight', '1'], ['ArrowLeft', '0'], ['End', '1']]) {
    slider.dispatchEvent(new w.KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
    flush();
    assert.equal(slider.getAttribute('aria-valuenow'), value);
    assert.ok(slider.getAttribute('aria-valuetext'));
  }
  assert.deepEqual(seen, [0, 1, 0, 1]);
  close();
});

test('model line animates a transform rather than a layout position', () => {
  const css = readFileSync(resolve(__dirname, '../../dashboard/styles.css'), 'utf8');
  const rule = css.match(/\.tile-model\s*\{([^}]+)\}/)[1];
  assert.match(rule, /transform:/);
  assert.doesNotMatch(rule, /transition:\s*bottom/);
});

test('the horizontal record scroller does not offset its header over the first trade', () => {
  const css = readFileSync(resolve(__dirname, '../../dashboard/styles.css'), 'utf8');
  const rule = css.match(/\.ledger th\s*\{([^}]+)\}/)[1];
  assert.match(rule, /top:\s*0[;\s]/);
  assert.doesNotMatch(rule, /top:\s*var\(--topbar\)/);
});

test('web fonts do not block first paint and token CSS loads without an import waterfall', () => {
  const html = readFileSync(resolve(__dirname, '../../dashboard/index.html'), 'utf8');
  const dom = new JSDOM(html);
  const links = [...dom.window.document.querySelectorAll('head > link')];
  const font = links.find(link => link.href.includes('fonts.googleapis.com/css2'));
  assert.equal(font.media, 'print');
  assert.match(font.getAttribute('onload'), /media='all'/);
  assert.ok(links.some(link => link.getAttribute('href') === 'base.css'));
  const css = readFileSync(resolve(__dirname, '../../dashboard/styles.css'), 'utf8');
  assert.doesNotMatch(css, /@import/);
  assert.match(css, /\.section-night:empty\s*\{[^}]*min-height:/);
  dom.window.close();
});
