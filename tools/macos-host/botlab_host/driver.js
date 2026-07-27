// Bridges the compiled bot's Elm ports (eventIn/responseOut, see Main.elm)
// to plain newline-delimited JSON over stdin/stdout, so a Python host
// process can drive the bot as a subprocess without needing a browser or
// any JS-side logic beyond this thin relay.
//
// Usage: node driver.js <path-to-compiled-bot.js>
const fs = require("fs");
const readline = require("readline");

const compiledPath = process.argv[2];
if (!compiledPath) {
  console.error("usage: node driver.js <path-to-compiled-bot.js>");
  process.exit(1);
}

const { Elm } = require(compiledPath);
const app = Elm.Main.init();

app.ports.responseOut.subscribe((json) => {
  process.stdout.write(json + "\n");
});

const rl = readline.createInterface({ input: process.stdin, terminal: false });
rl.on("line", (line) => {
  if (line.trim().length === 0) return;
  app.ports.eventIn.send(line);
});
rl.on("close", () => process.exit(0));
