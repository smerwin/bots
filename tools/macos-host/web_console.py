#!/usr/bin/env python3
"""A small web console for a running bot session: status, live log, settings.

Bound to the tailnet and nowhere else. The console can change what the bot does
and, once paused, drive the mouse, so it is not something to expose. The bind
address is resolved from Tailscale and the server **fails to start** if that
cannot be determined -- there is deliberately no fall back to 0.0.0.0, because
the failure mode of guessing wrong here is a public remote control. Tailscale
itself supplies the authentication: reaching the port at all means being a
device on the tailnet, so the console carries no login of its own.

Two threads, one rule. The HTTP handlers run on their own threads and must never
touch the pipe to the bot process -- that pipe is a strict request/response
conversation with the Elm runtime and interleaving a second writer corrupts it.
So handlers only ever *queue* intent, and `run_bot`'s own loop drains the queue
between ticks and performs the effect. Everything crossing that line lives in
`ConsoleState` behind one lock.
"""
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

# "(bounty) 6,000 ISK added to next bounty payout" -- one line per rat killed,
# carrying what it paid. The (combat) lines are per shot, not per kill, so they
# are no use for a kill count; this is.
#
# **Two anchorings of one literal, because there are now two readers.** This
# console counts kills off whole echoed lines, which still carry the "(bounty)"
# channel marker; `botlab_host.GameLogTail` counts them off a parsed entry,
# whose `text` has already had the "[ ts ] (channel) " prefix cut away. Those
# are the same fact read at two points of the same pipeline, and CLAUDE.md's own
# objection to giving the bot this channel is that a second reader would be a
# second source of truth for one statistic. So there is one pattern and two
# anchorings of it, rather than two patterns -- and
# `test_saxrat_kill_counter.TheHostAndTheConsoleCountTheSameKillsTest` runs both
# over every bounty line in the recorded corpus and requires the same number.
#
# The client writes exactly two wordings, measured over the 17,388 bounty lines
# in the 38 sessions of `~/Documents/EVE/logs/Gamelogs` that carry any: 17,174
# of the plain form and 214 ending "(payment adjusted)". Both are a rat that
# died, so the pattern stops at the payout clause and reads no further.
_BOUNTY_PAYOUT = r"([\d,]+(?:\.\d+)?)\s*ISK added to next bounty payout"
BOUNTY_RE = re.compile(r"\(bounty\)\s+" + _BOUNTY_PAYOUT)
# The same, against a parsed entry's `text` -- what the host's tail hands over.
BOUNTY_TEXT_RE = re.compile(r"^" + _BOUNTY_PAYOUT)

# Tailscale hands out addresses from the 100.64.0.0/10 carrier-grade NAT range.
TAILNET_RE = re.compile(r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}\b")

MAX_LOG_LINES = 4000

# #312: the pause/stop buttons above act on a queue `run_bot`'s own loop
# drains, and that loop can go a while between drains while a single tick
# blocks on a slow task -- the outer drain is between ticks, and #321's inner
# drain and its `MAX_TICK_SECONDS` give-back are both reached only once the
# task in progress *returns*. So a console watching `paused: False` while a
# POST to pause it sits unanswered cannot tell "busy" from "wedged" -- the
# whole complaint #312 was filed on.
#
# Two thresholds rather than one. `TICK_NOTABLY_LONG_SECONDS` is set above the
# busiest *normal* band `botlab_host.MAX_TICK_SECONDS`'s own comment already
# measured from the recorded corpus -- 95% of ticks in the 11-20-substep band
# finish under 18s -- so an ordinary slow tick does not cross it, and this is
# "worth a look", not an alarm. `TICK_WEDGED_SECONDS` is kept equal to
# `botlab_host.MAX_TICK_SECONDS`, the point past which the host's own loop
# gives a tick back on its own: a value the console still sees climbing past
# that point is the tell that one task, not the whole tick, is the thing that
# is stuck, since the loop cannot even reach its own check until that task's
# call returns. Not imported from `botlab_host` -- that module imports this
# one, and a reverse import would cycle -- so the two are pinned equal by
# `test_the_console_reports_a_wedged_tick.TheThresholdsSitInARealGapTest
# .test_the_console_agrees_with_the_hosts_own_bound` instead, the same
# "checked rather than assumed" shape as the saxrat/mission-runner threshold
# pairs elsewhere in this file's sibling constants.
TICK_NOTABLY_LONG_SECONDS = 30.0
TICK_WEDGED_SECONDS = 300.0


def tick_progress_state(elapsed_seconds):
    """How a tick's elapsed time reads to an operator, as a plain dict.

    A declaration of its own, for the same reason `botlab_host.tick_bound_note`
    is one: a case can ask the rule directly rather than driving a whole
    console and a wedged bot process to reach it. `elapsedSeconds` is the raw
    number so a UI can show it even where the two booleans below have not
    changed since the last poll.

    Both booleans are computed from a wall-clock timestamp `ConsoleState`
    stores and `snapshot()` reads live -- **not** from anything the main bot
    loop pushes as it goes -- which is what makes this answer anything at all
    while a single slow task has that loop blocked: the HTTP handler thread
    calling this is never the thread that could be stuck inside one.
    """
    return {
        "elapsedSeconds": round(elapsed_seconds, 1),
        "notablyLong": elapsed_seconds > TICK_NOTABLY_LONG_SECONDS,
        "wedged": elapsed_seconds > TICK_WEDGED_SECONDS,
    }


class NoTailnet(Exception):
    """No tailnet address, so there is nowhere safe to listen."""


def tailnet_address():
    """This machine's tailnet IPv4 address, or raise.

    Asks Tailscale first and falls back to reading the interfaces, because the
    CLI is not always on PATH under a launcher. Never returns a non-tailnet
    address: a caller that cannot bind to the tailnet must not bind at all.
    """
    for candidate in ("tailscale",
                      "/opt/homebrew/bin/tailscale",
                      "/usr/local/bin/tailscale",
                      "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                      # Windows: the installer does not put tailscale on PATH.
                      r"C:\Program Files\Tailscale\tailscale.exe",
                      r"C:\Program Files (x86)\Tailscale\tailscale.exe"):
        try:
            out = subprocess.run([candidate, "ip", "-4"], capture_output=True,
                                 text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        found = TAILNET_RE.search(out or "")
        if found:
            return found.group(0)

    # Interface listing, when the CLI is not reachable. `ifconfig` does not exist
    # on Windows and `ipconfig` does not exist elsewhere, so the command has to
    # follow the platform -- otherwise this leg always fails there and the
    # console refuses to bind on a machine that does have a tailnet, which is
    # exactly what happened the first time it was run on Windows.
    #
    # Both are only ever *searched* for a 100.64.0.0/10 address, so neither can
    # widen what this function is willing to return. The safety property is in
    # TAILNET_RE and in raising rather than defaulting, not in which command
    # produced the text.
    listers = [["ipconfig"]] if sys.platform == "win32" else [["ifconfig"]]
    for lister in listers:
        try:
            out = subprocess.run(lister, capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        found = TAILNET_RE.search(out or "")
        if found:
            return found.group(0)

    raise NoTailnet(
        "no tailnet (100.64.0.0/10) address found -- is Tailscale up? "
        "Refusing to bind anywhere else.")


class ConsoleState:
    """Everything the console shows, and everything it asks for, behind a lock."""

    def __init__(self, settings_text="", session_end_at_ms=None,
                 app_name="", bot_source="", version="", links=None):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.session_end_at_ms = session_end_at_ms

        # Which bot this console is driving, from where, and what it was built
        # from. Fixed for the session -- the host resolves all three before the
        # console exists -- so they are read without the lock and never change
        # under a handler. An empty string is a host that did not say, which the
        # page shows as unknown rather than as blank.
        self.app_name = app_name or ""
        self.bot_source = bot_source or ""
        self.version = version or ""

        # GitHub links for `version`'s own commit, from `bot_source_links` --
        # code/blame/diff URLs, or `{"reason": ...}` when there is nothing to
        # link (LOCAL-ONLY, an unreachable remote, no git checkout at all).
        # Fixed for the session like the three above, for the same reason: it
        # is computed once, before the console exists, from the same read.
        self.links = links or {}

        # Who the console is watching, which is the one identity above that the
        # host cannot resolve before the console exists: the name comes from the
        # client's window title, and the title is not read until the bot asks for
        # the client list, several seconds into the session. So it is written
        # under the lock like any other update, and empty until then.
        self.character = ""
        self.tick = 0
        # Wall clock, not `time.monotonic()`, on purpose -- what leaves this
        # state is JSON on an HTTP response, and `snapshot()` computing
        # elapsed against `time.time()` on the same basis is what lets a
        # caller trust the number rather than having to know which clock the
        # host used. Starts at construction so a poll before the first tick
        # answers a small number rather than a `None` the page has to guard.
        self.tick_started_at = time.time()
        self.status_text = ""
        self.settings_text = settings_text or ""
        self.finished = False
        self.finish_reason = ""

        self._seq = 0
        self._lines = deque(maxlen=MAX_LOG_LINES)

        self.kills = 0
        self.isk = 0.0
        self.decisions = 0

        # Set by handlers, drained by the bot loop.
        self.pending_settings = None
        self.pending_commands = deque()
        self.paused = False

    # -- writes from the bot loop ------------------------------------------

    def _append(self, kind, text):
        self._seq += 1
        self._lines.append({"seq": self._seq, "at": time.time(), "kind": kind, "text": text})

    def note_decision(self, tick, status_text):
        with self._lock:
            self.tick = tick
            self.status_text = status_text
            self.decisions += 1
            for line in (status_text or "").splitlines():
                if line.strip():
                    self._append("decision", line.rstrip())

    def note_game_log(self, line):
        with self._lock:
            self._append("game", line)
            found = BOUNTY_RE.search(line)
            if found:
                self.kills += 1
                try:
                    self.isk += float(found.group(1).replace(",", ""))
                except ValueError:
                    pass

    def note_host(self, line):
        with self._lock:
            self._append("host", line)

    def note_tick_started(self):
        """Stamp the moment the current tick began -- #312.

        Called once per tick from `run_bot`'s own loop, never once per
        substep -- the same "say it once" shape `note_character` already
        uses, and for the same reason: a tick can carry hundreds of substeps,
        and restamping on each of them would make `snapshot()`'s elapsed time
        read the age of the *last substep* rather than of the tick, which is
        what a wedge is measured against.
        """
        with self._lock:
            self.tick_started_at = time.time()

    def note_character(self, character):
        """Who the client is flying, once the host can name one.

        Called on every pass of the bot loop rather than once, because there is
        no single moment the name is known: the title arrives with whichever
        client-list request happens to be first. So this has to be quiet when
        nothing has changed, and a name reaching the log twice would be a line
        per reading for the rest of the session.

        **`None` is the host saying it cannot tell**, not the client changing
        pilot -- a window with no title, or one that carries no name, answers
        `None` through `character_from_window_title`, and a reading that cannot
        tell must not erase a name that an earlier reading could. So an absent
        name is ignored rather than stored, which is the same rule the ESI
        destination guard reads it by: "cannot check" is not "mismatch".
        """
        with self._lock:
            if not character or character == self.character:
                return
            known_before = self.character
            self.character = character
            self._append("host", f"now flying {character}" if known_before
                         else f"flying {character}")

    def note_finished(self, reason):
        with self._lock:
            self.finished = True
            self.finish_reason = reason
            self._append("host", f"session finished: {reason}")

    # -- reads and writes from HTTP handlers -------------------------------

    def snapshot(self, since=0, limit=400):
        with self._lock:
            lines = [line for line in self._lines if line["seq"] > since][-limit:]
            seconds_left = None
            if self.session_end_at_ms is not None:
                seconds_left = max(0, int(self.session_end_at_ms / 1000 - time.time()))
            # Computed here, live, against the wall clock -- not carried from
            # whatever the bot loop last had time to report. That is the
            # whole point (#312): the loop is exactly what can be stuck.
            tick_progress = tick_progress_state(time.time() - self.tick_started_at)
            return {
                "appName": self.app_name,
                "botSource": self.bot_source,
                "version": self.version,
                "links": self.links,
                "character": self.character,
                "uptimeSeconds": int(time.time() - self.started_at),
                "sessionSecondsLeft": seconds_left,
                "tick": self.tick,
                "tickElapsedSeconds": tick_progress["elapsedSeconds"],
                "tickNotablyLong": tick_progress["notablyLong"],
                "tickWedged": tick_progress["wedged"],
                "decisions": self.decisions,
                "kills": self.kills,
                "isk": self.isk,
                "status": self.status_text,
                "settings": self.settings_text,
                "paused": self.paused,
                "finished": self.finished,
                "finishReason": self.finish_reason,
                "lines": lines,
                "latestSeq": self._seq,
            }

    def request_settings(self, text):
        with self._lock:
            self.pending_settings = text
            self._append("host", "settings change requested from the console")

    def request_command(self, name):
        with self._lock:
            self.pending_commands.append(name)
            self._append("host", f"command requested from the console: {name}")

    # -- drained by the bot loop -------------------------------------------

    def take_settings(self):
        with self._lock:
            text, self.pending_settings = self.pending_settings, None
            if text is not None:
                self.settings_text = text
            return text

    def take_command(self):
        with self._lock:
            return self.pending_commands.popleft() if self.pending_commands else None

    def set_paused(self, paused):
        with self._lock:
            self.paused = paused
            self._append("host", "paused" if paused else "resumed")

    def is_paused(self):
        with self._lock:
            return self.paused


class _Handler(BaseHTTPRequestHandler):
    server_version = "bot-host-console"
    state = None

    def log_message(self, *args):
        pass  # the bot's own log is the interesting one

    def _send(self, code, body, content_type="application/json"):
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            try:
                with open(os.path.join(HERE, "web_console.html"), "rb") as page:
                    self._send(200, page.read(), "text/html; charset=utf-8")
            except OSError as exc:
                self._send(500, json.dumps({"error": str(exc)}))
            return
        if self.path.startswith("/api/state"):
            since = 0
            if "?" in self.path:
                for part in self.path.split("?", 1)[1].split("&"):
                    if part.startswith("since="):
                        try:
                            since = int(part[6:])
                        except ValueError:
                            since = 0
            self._send(200, json.dumps(self.state.snapshot(since=since)))
            return
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            self._send(400, json.dumps({"error": "bad request body"}))
            return

        if self.path == "/api/settings":
            text = body.get("settings")
            if not isinstance(text, str):
                self._send(400, json.dumps({"error": "settings must be a string"}))
                return
            self.state.request_settings(text)
            self._send(200, json.dumps({"queued": True}))
            return

        if self.path == "/api/command":
            name = body.get("command")
            if name not in ("pause", "resume", "stop"):
                self._send(400, json.dumps({"error": "unknown command"}))
                return
            self.state.request_command(name)
            self._send(200, json.dumps({"queued": True}))
            return

        self._send(404, json.dumps({"error": "not found"}))


def start(state, port=8787):
    """Serve on the tailnet address only. Raises NoTailnet if there isn't one."""
    address = tailnet_address()
    handler = type("Handler", (_Handler,), {"state": state})
    httpd = ThreadingHTTPServer((address, port), handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True,
                              name="web-console")
    thread.start()
    return httpd, f"http://{address}:{port}/"


def _unused_port_check(address, port):
    with socket.socket() as probe:
        probe.settimeout(0.2)
        return probe.connect_ex((address, port)) != 0
