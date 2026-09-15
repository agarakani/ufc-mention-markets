const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const dashboard = path.resolve(__dirname, "../../dashboard");
const html = fs.readFileSync(path.join(dashboard, "index.html"), "utf8");

test("current markets come first and recorded cards are a separate disclosure", () => {
  const { document } = new JSDOM(html).window;
  const live = document.querySelector("#live");
  assert.ok(live);
  assert.equal(document.querySelector("main").firstElementChild, live);
  assert.equal(live.getAttribute("aria-labelledby"), "liveTitle");
  const archive = document.querySelector("details#archive");
  assert.ok(archive);
  assert.equal(archive.hasAttribute("open"), false);
  assert.ok(archive.querySelector("#nightSwitch"));
  assert.ok(archive.querySelector("#night"));
  assert.equal(document.querySelector(".skip-link").getAttribute("href"), "#live");
});

test("primary navigation links to current markets, the record and the model", () => {
  const { document } = new JSDOM(html).window;
  const links = [...document.querySelectorAll(".primary-nav a")];
  assert.deepEqual(links.map(link => link.getAttribute("href")), ["#/live", "#/record", "#/model"]);
  assert.deepEqual(links.map(link => link.textContent.trim()), ["Current", "Record", "Model"]);
  assert.ok(html.indexOf('"src/live.js"') < html.indexOf('"app.js"'));
  assert.ok(html.includes('"src/live.js"'));
});

test("live quote tables retain a contained horizontal scroll area on small screens", () => {
  const css = fs.readFileSync(path.join(dashboard, "styles.css"), "utf8");
  assert.match(css, /\.live-market-wrap\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.live-markets\s*\{[^}]*min-width:/s);
  assert.match(css, /\.live-refresh[^}]*min-height:\s*44px/s);
});

test("poster cards expand to the full grid width without widening their quote tables", () => {
  const css = fs.readFileSync(path.join(dashboard, "styles.css"), "utf8");
  assert.match(css, /\.live-cards\s*\{[^}]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s);
  assert.match(css, /\.event-card\[data-featured="true"\],\s*\.event-card\[open\]\s*\{[^}]*grid-column:\s*1\s*\/\s*-1/s);
  assert.match(css, /@media\s*\(max-width:\s*720px\)[\s\S]*\.live-cards\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/);
  assert.match(css, /\.event-card\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.live-market-wrap\s*\{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto/s);
});

test("poster palettes stay separate from theme controls and financial signals", () => {
  const css = fs.readFileSync(path.join(dashboard, "styles.css"), "utf8");
  for (const tone of ["ice", "copper", "crimson", "ink"]) {
    assert.match(css, new RegExp(`\\.event-card\\[data-tone="${tone}"\\]\\s*\\{[^}]*--poster-accent:`));
  }
  assert.doesNotMatch(css, /\.event-card\[data-theme=/);
  const posterRules = css.slice(css.indexOf(".event-card {"), css.indexOf(".event-location {"));
  assert.doesNotMatch(posterRules, /var\(--(?:up|down|series-model|series-market)\)/);
  assert.match(css, /\.live-edge\.up[^}]*color:\s*var\(--up\)/s);
});

test("poster photos do not block card controls and motion respects system preference", () => {
  const css = fs.readFileSync(path.join(dashboard, "styles.css"), "utf8");
  const base = fs.readFileSync(path.join(dashboard, "base.css"), "utf8");
  assert.match(css, /\.event-poster-art\s*\{[^}]*position:\s*absolute[^}]*z-index:\s*-3/s);
  assert.match(css, /\.event-card > summary:focus-visible\s*\{[^}]*outline:/s);
  assert.match(css, /\.event-poster-art \.event-portrait\s*\{[^}]*object-fit:\s*cover[^}]*object-position:\s*center top/s);
  assert.match(base, /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*transition-duration:\s*1ms\s*!important/);
});

test("the poster arrow styling does not shrink its text label", () => {
  const css = fs.readFileSync(path.join(dashboard, "styles.css"), "utf8");
  assert.match(css, /\.event-card-cta > span\[aria-hidden\]\s*\{[^}]*border-radius:\s*50%/s);
  assert.doesNotMatch(css, /\.event-card-cta > span\s*\{/);
});
