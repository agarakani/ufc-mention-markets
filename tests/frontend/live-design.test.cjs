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
