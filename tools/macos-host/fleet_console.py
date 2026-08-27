"""One page showing every bot's web console at once.

    python3 tools/macos-host/fleet_console.py
    python3 tools/macos-host/fleet_console.py --consoles 100.1.2.3 100.4.5.6
    python3 tools/macos-host/fleet_console.py --port 8080

**Why this proxies instead of being a static page.** The consoles send no
`Access-Control-Allow-Origin`, so a page loaded from anywhere else cannot read
their `/api/state` -- the browser blocks it before the request is answered.
They send no `X-Frame-Options` either, so five `<iframe>`s would work, but five
consoles' worth of dense UI on one screen is not a thing anyone can read at a
glance, which is the whole point. So this fetches server-side, where the
same-origin policy does not apply, and renders what an operator actually scans
for. Each card links to its own console for the controls.

**It binds to the tailnet and nowhere else**, reusing `web_console`'s own
`tailnet_address` for exactly the reason written there: the consoles it fronts
can pause and stop a running bot, and this makes them reachable from one page.
A dashboard that is easier to reach than the things it fronts is a way to make
them public by accident.

**Unreachable is not the same as idle, and both are drawn differently.** A
console that does not answer says so, with how long it has been failing. The
silent-failure shape this repo keeps meeting -- a thing that reports nothing
and reads exactly like a thing with nothing to report -- is the one thing a
monitoring page must not do.
"""
import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from web_console import NoTailnet, tailnet_address  # noqa: E402

DEFAULT_CONSOLES = [
    "100.117.101.93",
    "100.94.230.99",
    "100.112.230.53",
    "100.86.234.101",
    "100.105.176.45",
]

# A tick is allowed to be long: the host's own bound is 300 s (#321), so
# anything under that is a slow reading rather than a wedge. Past it the tick
# counter genuinely should have moved, and the card says so instead of leaving
# the operator to compare numbers between refreshes.
TICK_STALL_SECONDS = 300.0

POLL_TIMEOUT = 4.0


class Fleet:
    """The last good reading from each console, and how old it is.

    Kept server-side rather than in the page so that a reload does not reset
    what is known -- "this tick has not moved in 11 minutes" is a fact about
    the bot, not about how long a browser tab has been open.
    """

    def __init__(self, hosts, port):
        self.hosts = list(hosts)
        self.port = port
        self.lock = threading.Lock()
        self.by_host = {h: {"host": h, "state": None, "error": "not polled yet",
                            "last_ok": None, "tick": None, "tick_changed_at": None}
                        for h in hosts}

    def url(self, host, path):
        return "http://%s:%d%s" % (host, self.port, path)

    def poll_one(self, host):
        now = time.time()
        try:
            with urllib.request.urlopen(self.url(host, "/api/state"),
                                        timeout=POLL_TIMEOUT) as response:
                state = json.loads(response.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as exc:
            with self.lock:
                self.by_host[host]["error"] = str(exc) or exc.__class__.__name__
            return

        # `lines` is the console's whole scrollback and is far and away the
        # biggest field; nothing here shows it, so it never crosses the wire.
        state.pop("lines", None)

        with self.lock:
            entry = self.by_host[host]
            tick = state.get("tick")
            if tick != entry.get("tick"):
                entry["tick"] = tick
                entry["tick_changed_at"] = now
            entry["state"] = state
            entry["error"] = None
            entry["last_ok"] = now

    def poll_all(self):
        threads = [threading.Thread(target=self.poll_one, args=(h,), daemon=True)
                   for h in self.hosts]
        for thread in threads:
            thread.start()
        # Bounded by the per-request timeout, plus a little: one unreachable
        # console must not hold up the four that answered.
        for thread in threads:
            thread.join(timeout=POLL_TIMEOUT + 1.0)

    def snapshot(self):
        now = time.time()
        out = []
        with self.lock:
            for host in self.hosts:
                entry = self.by_host[host]
                state = entry["state"]
                item = {
                    "host": host,
                    "url": self.url(host, "/"),
                    "error": entry["error"],
                    "secondsSinceGoodRead":
                        None if entry["last_ok"] is None else now - entry["last_ok"],
                    "secondsSinceTickMoved":
                        None if entry["tick_changed_at"] is None
                        else now - entry["tick_changed_at"],
                    "tickStallSeconds": TICK_STALL_SECONDS,
                }
                if state is not None:
                    item["state"] = state
                out.append(item)
        return {"consoles": out, "at": now}


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bots</title>
<style>
 :root { color-scheme: dark light; --bg:#12141a; --card:#1b1f27; --line:#2a3038;
         --text:#e6e9ef; --dim:#8b94a3; --ok:#5ad48b; --warn:#e8c05a; --bad:#f2685f; }
 body { margin:0; padding:14px; background:var(--bg); color:var(--text);
        font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; }
 h1 { font-size:14px; margin:0 0 12px; font-weight:600; }
 h1 span { color:var(--dim); font-weight:400; }
 .grid { display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(430px,1fr)); }
 .card { background:var(--card); border:1px solid var(--line); border-radius:8px;
         padding:10px 12px; border-left:3px solid var(--line); }
 .card.ok   { border-left-color:var(--ok); }
 .card.warn { border-left-color:var(--warn); }
 .card.bad  { border-left-color:var(--bad); }
 .top { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
 .who { font-weight:600; }
 .who a { color:inherit; text-decoration:none; border-bottom:1px dotted var(--dim); }
 .app { color:var(--dim); font-weight:400; }
 .status { margin:7px 0; white-space:pre-wrap; word-break:break-word; }
 .facts { display:flex; flex-wrap:wrap; gap:4px 14px; color:var(--dim); }
 .facts b { color:var(--text); font-weight:600; }
 .flag { color:var(--warn); }
 .err  { color:var(--bad); }
 .muted { color:var(--dim); }
</style></head><body>
<h1>bots <span id="when"></span></h1>
<div class="grid" id="grid"></div>
<script>
const dur = s => {
  if (s === null || s === undefined) return "-";
  s = Math.floor(s);
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s/60) + "m" + String(s%60).padStart(2,"0") + "s";
  return Math.floor(s/3600) + "h" + String(Math.floor(s%3600/60)).padStart(2,"0") + "m";
};
const esc = t => String(t === undefined || t === null ? "" : t)
  .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function card(c) {
  const s = c.state;
  // No state at all means this console has never answered. Say that, rather
  // than drawing an empty card that reads like a quiet bot.
  if (!s) {
    return `<div class="card bad"><div class="top"><span class="who">
      <a href="${esc(c.url)}" target="_blank">${esc(c.host)}</a></span></div>
      <div class="status err">no answer &mdash; ${esc(c.error || "unreachable")}</div>
      <div class="facts">${c.secondsSinceGoodRead === null ? "never reached since this page started"
        : "last good read " + dur(c.secondsSinceGoodRead) + " ago"}</div></div>`;
  }
  const flags = [];
  let cls = "ok";
  if (c.error) { cls = "warn"; flags.push(`<span class="flag">stale: ${esc(c.error)}</span>`); }
  if (s.finished) { cls = "warn"; flags.push(`<span class="flag">finished${s.finishReason ? ": " + esc(s.finishReason) : ""}</span>`); }
  if (s.paused) { cls = "warn"; flags.push(`<span class="flag">paused</span>`); }
  if (c.secondsSinceTickMoved !== null && c.secondsSinceTickMoved > c.tickStallSeconds) {
    cls = "bad";
    flags.push(`<span class="err">tick has not moved in ${dur(c.secondsSinceTickMoved)}</span>`);
  }
  return `<div class="card ${cls}">
    <div class="top">
      <span class="who"><a href="${esc(c.url)}" target="_blank">${esc(s.character || "(no character)")}</a>
        <span class="app">${esc(s.appName || "")}</span></span>
      <span class="muted">${esc(c.host)}</span>
    </div>
    <div class="status">${esc(s.status || "(no status line yet)")}</div>
    <div class="facts">
      <span>tick <b>${esc(s.tick)}</b></span>
      <span>decisions <b>${esc(s.decisions)}</b></span>
      <span>kills <b>${esc(s.kills)}</b></span>
      <span>up <b>${dur(s.uptimeSeconds)}</b></span>
      <span>session left <b>${dur(s.sessionSecondsLeft)}</b></span>
      <span class="muted">${esc(s.version)}</span>
    </div>
    ${flags.length ? `<div class="facts">${flags.join("")}</div>` : ""}
  </div>`;
}

async function tick() {
  try {
    const r = await fetch("/api/fleet", {cache:"no-store"});
    const d = await r.json();
    document.getElementById("grid").innerHTML = d.consoles.map(card).join("");
    document.getElementById("when").textContent =
      "updated " + new Date(d.at * 1000).toLocaleTimeString();
  } catch (e) {
    document.getElementById("when").textContent = "aggregator unreachable: " + e;
  }
}
tick(); setInterval(tick, 3000);
</script></body></html>
"""


def make_handler(fleet):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body, content_type):
            payload = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path.startswith("/api/fleet"):
                fleet.poll_all()
                self._send(json.dumps(fleet.snapshot()), "application/json")
                return
            if self.path == "/" or self.path.startswith("/?"):
                self._send(PAGE, "text/html; charset=utf-8")
                return
            self.send_error(404)

        def log_message(self, *args):
            pass

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--consoles", nargs="+", default=DEFAULT_CONSOLES,
                        help="console hosts to front (default: the five known bots)")
    parser.add_argument("--console-port", type=int, default=8787,
                        help="port the consoles listen on (default: 8787)")
    parser.add_argument("--port", type=int, default=8080,
                        help="port to serve this page on (default: 8080)")
    args = parser.parse_args(argv)

    try:
        address = tailnet_address()
    except NoTailnet as exc:
        print("fleet_console: %s" % exc, file=sys.stderr)
        return 1

    fleet = Fleet(args.consoles, args.console_port)
    httpd = ThreadingHTTPServer((address, args.port), make_handler(fleet))
    print("fleet console on http://%s:%d  fronting %d consoles"
          % (address, args.port, len(args.consoles)))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
