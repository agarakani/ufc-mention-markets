const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const dashboard = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(__dirname, "../../dashboard");
function javascriptIn(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? javascriptIn(file) : entry.name.endsWith(".js") ? [file] : [];
  });
}
const sources = javascriptIn(dashboard);
for (const source of sources) execFileSync(process.execPath, ["--check", source], { stdio: "inherit" });
console.log(`Checked ${sources.length} JavaScript files.`);
