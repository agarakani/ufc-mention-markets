const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const dashboard = path.resolve(__dirname, "../../dashboard");

// Deliberately small, synthetic examples. Counts must use trades, not m.trade.
function fixture() {
  const first = {
    ticker: "TEST-JUL11-DANA", event_ticker: "TEST-JUL11-FIGHT",
    fighter_1: "Abdul-Kareem Al-Selwady", fighter_2: "Test Opponent",
    phrase: "Dana / Dana White / White", result: "yes",
    ask: [0.4, 0.6], bid: [0.3, 0.5], model: [0.5, 0.5],
  };
  const second = { ...first, ticker: "TEST-JUL11-CHOKE", phrase: "Choke", result: null };
  const later = { ...first, ticker: "TEST-JUL25-DANA", event_ticker: "TEST-JUL25-FIGHT", result: "no" };
  const trades = [
    { ...first, event_date: "2026-07-11", entered_at: "2026-07-11T10:00:00Z", side: "yes", price: 0.4, model_probability: 0.5, edge: 0.1, won: true, pnl: 0.6 },
    { ...first, event_date: "2026-07-11", entered_at: "2026-07-11T11:00:00Z", side: "no", price: 0.5, model_probability: 0.5, edge: 0, won: false, pnl: -0.5 },
  ];
  first.trade = trades[1];
  return {
    tapes: [
      { card: "JUL25", event_date: "2026-07-25", markets: [later], stamps: ["2026-07-25T10:00:00Z", "2026-07-25T11:00:00Z"], frames: 2 },
      { card: "JUL11", event_date: "2026-07-11", markets: [first, second], stamps: ["2026-07-11T10:00:00Z", "2026-07-11T11:00:00Z"], frames: 2 },
    ],
    trades,
    performance: { equity: [{ date: "2026-07-11", card_pnl: 0.1 }, { date: "2026-07-25", card_pnl: 0 }] },
    fighters: {}, model_health: {},
  };
}

function browser(t, { hash = "", data = fixture(), app = true, immediatePaint = true, flushTasks = true } = {}) {
  const html = fs.readFileSync(path.join(dashboard, "index.html"), "utf8").replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "");
  const dom = new JSDOM(html, { url: `https://example.test/${hash}`, runScripts: "outside-only", pretendToBeVisual: true });
  t.after(() => dom.window.close());
  const w = dom.window;
  Object.defineProperty(w.document, "readyState", { value: "complete" });
  w.HTMLElement.prototype.scrollIntoView = function () {};
  w.UFC_MENTION_DASHBOARD_DATA = data;
  const paint = [];
  const tasks = [];
  w.setTimeout = fn => tasks.push(fn);
  w.MM = {
    motion: { reduced: () => true, afterPaint: fn => immediatePaint ? fn() : paint.push(fn), reveal() {} },
    charts: { line: () => ({ destroy() {} }) },
    board: {
      splitPhrase: phrase => { const [word, ...alts] = phrase.split(" / "); return { word, alts }; },
      mount(container, night, options) {
        container.innerHTML = night.markets.map(m => `<button class="tile" data-ticker="${m.ticker}">${m.phrase}</button>`).join("");
        container.querySelectorAll("button").forEach(button => button.addEventListener("click", () => options.onOpen(button.dataset.ticker)));
        return { setFrame() {}, destroy() {}, focusTile(ticker) { container.querySelector(`[data-ticker="${ticker}"]`)?.focus(); } };
      },
    },
    timeline: { mount: () => ({ destroy() {} }) },
    book: { mount() {} }, model: { mount() {} },
  };
  ["src/select.js", "src/ledger.js", "src/pane.js", "src/palette.js", ...(app ? ["app.js"] : [])].forEach(file => w.eval(fs.readFileSync(path.join(dashboard, file), "utf8")));
  const flush = () => { while (tasks.length) tasks.shift()(); };
  if (flushTasks) flush();
  return { w, d: w.document, flushPaint: () => { while (paint.length) paint.shift()(); }, flushTasks: flush };
}

function key(w, element, value, options = {}) {
  const event = new w.KeyboardEvent("keydown", { key: value, bubbles: true, cancelable: true, ...options });
  element.dispatchEvent(event);
  return event;
}

test("night totals agree with the ledger even when a market has several trades", t => {
  const { w, d } = browser(t);
  const night = w.MM.select.night("JUL11");
  assert.equal(night.trades, 2);
  assert.equal(night.fights[0].trades, 2);
  assert.equal(night.wins, 1);
  assert.equal(night.staked, 0.9);
  assert.equal(night.pnl, 0.1);
  d.querySelector('[data-filter="night"][data-value="2026-07-11"]').click();
  assert.equal(d.querySelectorAll(".ledger-row").length, night.trades);
  assert.match(d.querySelector("#ledgerCount").textContent, /2 contracts.*1 won.*\+\$0.10/);
  assert.equal(w.MM.select.night("JUL25").trades, 0);
});

test("nights are chronological and each market looks up its own fight and night", t => {
  const { w } = browser(t, { app: false });
  assert.deepEqual(Array.from(w.MM.select.nights(), n => n.card), ["JUL11", "JUL25"]);
  assert.equal(w.MM.select.latestNight().card, "JUL25");
  for (const hit of w.MM.select.allMarkets()) {
    const found = w.MM.select.market(hit.market.ticker);
    assert.equal(found.night, hit.night);
    assert.equal(found.fight, hit.fight);
    assert.equal(found.market, hit.market);
  }
  assert.equal(w.MM.select.market("DOES-NOT-EXIST"), null);
});

test("an unknown ticker falls back to the latest night with a valid night URL", t => {
  const { w, d } = browser(t, { hash: "#/w/DOES-NOT-EXIST" });
  assert.equal(w.MM.pane.isOpen(), false);
  assert.equal(d.querySelector(".night-btn.is-active").dataset.card, "JUL25");
  assert.equal(w.location.hash, "#/n/JUL25");
  const malformed = browser(t, { hash: "#/w/%E0%A4%A" });
  assert.equal(malformed.w.MM.pane.isOpen(), false);
  assert.equal(malformed.d.querySelector(".night-btn.is-active").dataset.card, "JUL25");
});

test("word links, previous and next, and Escape preserve a usable focus target", t => {
  const { w, d } = browser(t, { hash: "#/w/TEST-JUL11-DANA" });
  assert.equal(w.MM.pane.current().market.ticker, "TEST-JUL11-DANA");
  assert.equal(d.activeElement.id, "paneClose");
  assert.equal(d.querySelector("#panePrev").disabled, true);
  d.querySelector("#paneNext").click();
  assert.equal(w.MM.pane.current().market.ticker, "TEST-JUL11-CHOKE");
  assert.equal(d.querySelector("#paneNext").disabled, true);
  d.querySelector("#panePrev").click();
  key(w, d.activeElement, "Escape");
  assert.equal(w.MM.pane.isOpen(), false);
  assert.equal(d.activeElement.dataset.ticker, "TEST-JUL11-DANA");
});

test("palette Escape closes only search and restores focus to the pane", t => {
  const { w, d } = browser(t, { hash: "#/w/TEST-JUL11-DANA" });
  key(w, d.activeElement, "k", { metaKey: true });
  assert.equal(w.MM.palette.isOpen(), true);
  assert.equal(d.activeElement.id, "paletteInput");
  key(w, d.activeElement, "Tab");
  assert.equal(d.activeElement.id, "paletteInput");
  key(w, d.activeElement, "Tab", { shiftKey: true });
  assert.equal(d.activeElement.id, "paletteInput");
  key(w, d.activeElement, "Escape");
  assert.equal(w.MM.palette.isOpen(), false);
  assert.equal(w.MM.pane.isOpen(), true);
  assert.equal(d.activeElement.id, "paneClose");
});

test("the word pane wraps Tab and Shift-Tab within its controls", t => {
  const { w, d } = browser(t, { hash: "#/w/TEST-JUL11-DANA" });
  key(w, d.activeElement, "Tab", { shiftKey: true });
  assert.equal(d.activeElement.id, "paneNext");
  key(w, d.activeElement, "Tab");
  assert.equal(d.activeElement.id, "paneClose");
});

test("search exposes the active keyboard option and clears it when nothing matches", t => {
  const { w, d } = browser(t);
  d.querySelector("#searchBtn").click();
  const input = d.querySelector("#paletteInput");
  assert.equal(input.getAttribute("aria-label"), "Search words, fights, and nights");
  const initial = input.getAttribute("aria-activedescendant");
  assert.ok(initial);
  assert.equal(d.getElementById(initial).getAttribute("aria-selected"), "true");
  key(w, input, "ArrowDown");
  assert.notEqual(input.getAttribute("aria-activedescendant"), initial);
  input.value = "zzzzzzzzzzzzzzzzzzzzzzzzzz";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.match(d.querySelector("#paletteList").textContent, /Nothing matches/);
  assert.equal(input.hasAttribute("aria-activedescendant"), false);
  key(w, input, "Enter");
  assert.equal(w.MM.palette.isOpen(), true);
});

test("choosing a night in search closes the word pane before navigating", t => {
  const { w, d } = browser(t, { hash: "#/w/TEST-JUL11-DANA" });
  key(w, d.activeElement, "k", { ctrlKey: true });
  key(w, d.activeElement, "Enter");
  assert.equal(w.location.hash, "#/n/JUL25");
  assert.equal(w.MM.palette.isOpen(), false);
  assert.equal(w.MM.pane.isOpen(), false);
  assert.equal(d.activeElement.id, "nightTitle");
});

test("closing search before its opening paint does not focus the hidden input", t => {
  const { w, d, flushPaint } = browser(t, { immediatePaint: false });
  d.querySelector("#searchBtn").focus();
  w.MM.palette.open();
  w.MM.palette.close();
  flushPaint();
  assert.equal(d.activeElement.id, "searchBtn");
  assert.equal(d.querySelector("#palette").hidden, true);
  assert.equal(d.querySelector("#palette").classList.contains("is-open"), false);
});

test("the empty snapshot still supports search and theme without claiming a live recorder", t => {
  for (const data of [{}, { tapes: null }, { tapes: [] }, { tapes: {} }]) {
    const { w, d } = browser(t, { data, hash: "#/w/DOES-NOT-EXIST" });
    assert.match(d.querySelector("#night").textContent, /Nothing recorded yet/);
    assert.equal(w.location.hash, "#/");
    d.querySelector("#themeBtn").click();
    assert.equal(d.documentElement.getAttribute("data-theme"), "light");
    d.querySelector("#searchBtn").click();
    assert.equal(w.MM.palette.isOpen(), true);
    assert.doesNotMatch(d.querySelector("#footer").textContent, /Recording\.|every 30 minutes|will pick up/);
  }
});

test("a pending paper trade is never described as lost", t => {
  const data = fixture();
  data.tapes[1].markets[1].trade = { entered_at: "2026-07-11T11:00:00Z", side: "yes", price: 0.4, edge: 0.1, result: null, won: null, pnl: null };
  const { d } = browser(t, { data, hash: "#/w/TEST-JUL11-CHOKE" });
  assert.match(d.querySelector(".pane-trade-result").textContent, /Pending/);
  assert.doesNotMatch(d.querySelector(".pane-trade").textContent, /Lost/);
  assert.equal(d.querySelector(".pane-trade").classList.contains("is-lost"), false);
});

test("word details describe the saved record without guessing why no trade exists", t => {
  const { d } = browser(t, { hash: "#/w/TEST-JUL11-CHOKE" });
  assert.equal(d.querySelector(".pane-notrade").textContent, "No paper trade is recorded for this market.");
  const count = Array.from(d.querySelectorAll(".pane-facts dt")).find(el => el.textContent === "Snapshots");
  assert.ok(count);
  assert.equal(count.nextElementSibling.textContent, "2");
});

test("ledger rows open their exact word using Enter and Space", t => {
  const { w, d } = browser(t);
  const row = d.querySelector(".ledger-row");
  row.focus();
  key(w, row, "Enter");
  assert.equal(w.MM.pane.current().market.ticker, row.dataset.ticker);
  key(w, d.activeElement, "Escape");
  assert.equal(d.activeElement, row);
  key(w, row, " ");
  assert.equal(w.MM.pane.current().market.ticker, row.dataset.ticker);
});

test("the night title is the page heading, including an empty snapshot", t => {
  for (const data of [fixture(), {}]) {
    const { d } = browser(t, { data });
    assert.equal(d.querySelectorAll("h1").length, 1);
    assert.equal(d.querySelector("h1").id, "nightTitle");
  }
});

test("night links keep keyboard focus after the navigation is redrawn", t => {
  const { d } = browser(t);
  const link = d.querySelector('.night-btn[data-card="JUL11"]');
  link.focus();
  link.click();
  assert.equal(d.activeElement.dataset.card, "JUL11");
});

test("book, model and record wait until the board has painted", t => {
  const { d, flushPaint, flushTasks } = browser(t, { immediatePaint: false, flushTasks: false });
  assert.ok(d.querySelector("#nightBoard .tile"));
  assert.equal(d.querySelector("#ledgerBody"), null);
  assert.ok(d.querySelector("#recordTitle"));
  flushPaint();
  assert.equal(d.querySelector("#ledgerBody"), null);
  flushTasks();
  assert.ok(d.querySelector("#ledgerBody"));
});

test("a direct record link mounts the ledger before deferred work runs", t => {
  const { d } = browser(t, { hash: "#/record", immediatePaint: false, flushTasks: false });
  assert.ok(d.querySelector("#ledgerBody"));
});

test("the search theme action describes the current theme", t => {
  const { w, d } = browser(t);
  d.querySelector("#themeBtn").click();
  d.querySelector("#searchBtn").click();
  const input = d.querySelector("#paletteInput");
  input.value = "Switch";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  assert.match(d.querySelector(".palette-item.is-active").textContent, /Switch to dark/);
});

test("a refused clipboard write is reported as a failure, never as copied", async t => {
  const { w, d, flushTasks } = browser(t);
  w.navigator.clipboard = { writeText: () => ({ then(resolve, reject) { reject(new Error("Clipboard unavailable")); } }) };
  d.querySelector("#searchBtn").click();
  const input = d.querySelector("#paletteInput");
  input.value = "Copy link";
  input.dispatchEvent(new w.Event("input", { bubbles: true }));
  key(w, input, "Enter");
  await new Promise(resolve => setImmediate(resolve));
  flushTasks();
  assert.match(d.querySelector("#announce").textContent, /could not be copied/);
});
