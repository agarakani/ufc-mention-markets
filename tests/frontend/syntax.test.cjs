const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const test = require("node:test");

const checker = path.join(__dirname, "check-syntax.cjs");

function checkFixture(t, files) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "ufc-js-syntax-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  for (const [name, content] of Object.entries(files)) {
    const file = path.join(directory, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  return spawnSync(process.execPath, [checker, directory], { encoding: "utf8" });
}

test("syntax checking includes JavaScript throughout the dashboard tree", t => {
  const result = checkFixture(t, {
    "data.js": "window.DATA = {};",
    "helpers/quotes.js": "const price = 0.5;",
    "assets/deep/chart.js": "function chart() {}",
    "notes.txt": "This is not JavaScript and should not be checked.",
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Checked 3 JavaScript files/);
});

test("invalid top-level dashboard JavaScript fails the check", t => {
  const result = checkFixture(t, {
    "app.js": "const ready = true;",
    "data.js": "const broken = ;",
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /data\.js/);
  assert.match(result.stderr, /SyntaxError/);
});

test("invalid nested JavaScript outside src fails the check", t => {
  const result = checkFixture(t, {
    "app.js": "const ready = true;",
    "src/valid.js": "const valid = true;",
    "assets/deep/chart.js": "function broken( {",
  });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /chart\.js/);
  assert.match(result.stderr, /SyntaxError/);
});
