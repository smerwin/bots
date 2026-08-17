"""Screenshot the client when the bot enters an anomaly or starts shooting.

    python engagement_watch.py saxrat_run38.log --out shots/run38

Follows a live run log and captures the client on two events:

  * **arrival** -- the bot names an anomaly it has not been in before
  * **engagement** -- the first lock it asks for inside that anomaly

One of each per anomaly, so a site that takes four hundred readings costs two
pictures rather than four hundred. `stall_watch.py`'s own history is the reason:
before it deduped, one pathology produced ~225 near-identical Retina grabs and
1.7 GB on disk.

**It never posts input.** The host stands down for five seconds after any human
mouse or keyboard event, and `GetLastInputInfo` cannot tell a synthetic key from
a real one -- so the ALT press that `raise_window.py` uses to beat the
foreground lock would idle the bot on every screenshot. This does not raise the
window at all. It reads `GetForegroundWindow` instead and records the answer in
the filename, because a `BitBlt` of a window that was behind another copies
whatever was actually on top, and that picture looks exactly like a good one.

Reading the log is incremental -- these files reach tens of megabytes and
re-parsing per poll would cost more than the screenshots.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, r"C:\botlab\smerwin-bots\tools\windows-host")
from eve_mem import find_client_pid  # noqa: E402
from window_capture import capture_window  # noqa: E402
from window_probe import declare_dpi_awareness, windows_of_process  # noqa: E402

declare_dpi_awareness()

# The bot names the site it is in on every reading; the id is what makes an
# arrival distinguishable from the four hundred readings that follow it.
IN_ANOMALY = re.compile(rb"We are in anomaly '([^']+)'")
LOCKING = re.compile(rb"Lock target from overview entry '([^']+)'|"
                     rb"Lock more targets\. Asking for (\d+) locks")

# `Found matching anomaly.` is the real wording -- a full stop and no id at all,
# so a pattern reaching for one here can never match. It was in this file until
# the log was read, and it would have contributed nothing while looking like a
# second source of arrivals. `We are in anomaly '<id>'` is the line that names
# the site, and it is what arrivals are taken from.
#
# It is, however, exactly the right marker for a *departure*, which is why it is
# matched below without reaching for an id. Leaving is only knowable after the
# fact from the log -- by the time the site id changes the ship is already
# somewhere else and a frame captured then shows the next site, not the last one
# -- so what is captured instead is the reading the bot decides it is done here
# and picks the next site. Measured over run 45: `Found matching anomaly`
# precedes **31 of 31** site transitions, as does `HOOOOONK in warp`; the warp
# line was rejected because the ship is already gone by then and the frame is a
# warp tunnel. The id is taken from `current` -- the site being left -- rather
# than from this line, which carries none.
LEAVING = re.compile(rb"Found matching anomaly")


def client_window(pid):
    wins = [w for w in windows_of_process(pid)
            if w.visible and w.width > 400 and w.height > 300]
    if not wins:
        return None
    return max(wins, key=lambda w: w.width * w.height)


def main():
    parser = argparse.ArgumentParser(
        description="Screenshot the client at each anomaly arrival and first lock.")
    parser.add_argument("log")
    parser.add_argument("--out", default="shots")
    parser.add_argument("--scale", type=int, default=3,
                        help="downscale divisor (default 3)")
    parser.add_argument("--max-shots", type=int, default=120,
                        help="stop capturing past this many, and say so")
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--patterns-proven-by", metavar="LOG",
                        help="a finished run log the patterns must match, so a "
                             "wording change is caught here rather than by "
                             "silence")
    args = parser.parse_args()

    # A watcher whose patterns no longer match the log is indistinguishable
    # from a quiet run, which is this project's signature failure. Prove them
    # against a log known to contain the events before following a live one.
    if args.patterns_proven_by:
        arrivals = engagements = departures = 0
        with open(args.patterns_proven_by, "rb") as fh:
            for line in fh:
                if IN_ANOMALY.search(line):
                    arrivals += 1
                if LOCKING.search(line):
                    engagements += 1
                if LEAVING.search(line):
                    departures += 1
        print("patterns against %s: %d arrival lines, %d lock lines, "
              "%d departure lines"
              % (os.path.basename(args.patterns_proven_by), arrivals,
                 engagements, departures))
        if not arrivals or not engagements or not departures:
            sys.exit("a pattern matched nothing in a log that should contain "
                     "all three -- the bot's wording has changed and this "
                     "watcher would have captured nothing while looking healthy")

    os.makedirs(args.out, exist_ok=True)
    pid = find_client_pid()
    if not pid:
        sys.exit("no EVE client running")
    print("client pid %d -> %s" % (pid, args.out), flush=True)

    seen_arrival, seen_engagement, seen_departure = set(), set(), set()
    current = None
    shots = 0
    capped = False
    offset = os.path.getsize(args.log)  # only what happens from now on

    def shoot(kind, tag):
        nonlocal shots, capped
        if shots >= args.max_shots:
            if not capped:
                print("MAX SHOTS (%d) reached -- capturing nothing further. "
                      "Later engagements are NOT in this directory."
                      % args.max_shots, flush=True)
                capped = True
            return
        win = client_window(pid)
        if win is None:
            print("  client window gone", flush=True)
            return
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", tag)[:40]
        name = "%s_%s_%s.png" % (time.strftime("%H%M%S"), kind, safe)
        path = os.path.join(args.out, name)
        # raise_first stays off: the synthetic ALT a raise needs is
        # indistinguishable from a person at the keyboard, and would stand the
        # bot down for five seconds on every screenshot. See the module docstring.
        frontmost = capture_window(win, path, scale=args.scale)
        if not frontmost:
            base, ext = os.path.splitext(path)
            os.replace(path, base + "_NOTFRONTMOST" + ext)
            path = base + "_NOTFRONTMOST" + ext
        shots += 1
        print("  [%d] %s %s%s" % (shots, kind, os.path.basename(path),
                                  "" if frontmost else "  (window was not frontmost)"),
              flush=True)

    print("watching from byte %d; Ctrl-C to stop" % offset, flush=True)
    while True:
        try:
            size = os.path.getsize(args.log)
        except OSError:
            time.sleep(args.poll)
            continue
        if size < offset:            # rotated or replaced
            offset = 0
        if size > offset:
            with open(args.log, "rb") as fh:
                fh.seek(offset)
                block = fh.read(size - offset)
                offset = size
            for line in block.splitlines():
                m = IN_ANOMALY.search(line)
                if m:
                    anomaly = m.group(1).decode("ascii", "replace")
                    if anomaly != current:
                        current = anomaly
                    if anomaly not in seen_arrival:
                        seen_arrival.add(anomaly)
                        shoot("arrival", anomaly)
                    continue
                if LOCKING.search(line) and current and current not in seen_engagement:
                    seen_engagement.add(current)
                    shoot("engage", current)
                    continue
                # The site being left is `current`, not anything this line
                # names -- it carries no id. One shot per site: the decision is
                # re-derived every reading, so without the set this would fire
                # for as long as the bot took to get away.
                if LEAVING.search(line) and current and current not in seen_departure:
                    seen_departure.add(current)
                    shoot("depart", current)
        time.sleep(args.poll)


if __name__ == "__main__":
    sys.exit(main())
