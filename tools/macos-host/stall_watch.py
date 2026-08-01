#!/usr/bin/env python3
"""Watch a running bot's log for a stall and screenshot the client when one happens.

Three things count as a stall:

  * "I am stuck here and need help to continue." -- the bot saying so itself
    (askForHelpToGetUnstuck), which is never normal.
  * the decision tree going in circles: the last DECISION_WINDOW decisions
    containing no line the window did not already contain, for CIRCLING_THRESHOLD
    readings running.
  * the bot deciding to shoot while the game log stays silent -- the same test
    narrowed to decisions that claim to be firing, which names the problem
    precisely and reaches the threshold sooner.

The circling test replaced one that counted a decision repeating N times in a
row, which sounds equivalent and is not. A stalled bot repeats a *cycle*, not a
line:

    +    I see a locked target.
    ++   Cycle combat mod
    +++  Already pressed this weapon hotkey in a previous step.
    ++++ Wait for progress in game

Every line differs from the one before it, so a consecutive-identical counter
resets on each and never climbs. Measured against a real fifteen-minute stall:
the longest run of identical decisions in the entire log was **3**, against a
threshold of 60, while the four-line cycle repeated 62 times. The old test could
not have fired, and its threshold had been carefully calibrated -- against the
wrong statistic.

Screenshots the game window by id rather than the screen, since the client is
often on another macOS Space where a plain screen grab catches the wrong thing.
"""
import argparse, os, re, subprocess, sys, time
from collections import deque

# How many recent decisions make up the window whose contents must stop changing.
# Wide enough to hold a few full cycles of the longest repeating pattern seen
# live (period 6), so a legitimate but long decision sequence is not mistaken for
# one.
DECISION_WINDOW = 24

# How many decisions may arrive with nothing new in the window and nothing new in
# EVE's game log before it counts as a stall. Chosen by replaying three real
# runs: at 40, the fifteen-minute stall raises 99 alarms while a run that
# completed 12 missions raises none. 30 starts catching a healthy run, and
# raising it past 40 only delays the alarm without buying accuracy.
CIRCLING_THRESHOLD = 40

STUCK_TEXT = "I am stuck here and need help to continue."
DECISION = re.compile(r'^\++ (.*)$')

# Deciding to fire is the bot's claim that it is shooting something; a new
# (combat) line in EVE's own game log is the client agreeing. The two coming
# apart is exactly the fifteen-minute stall, and neither the bot's log nor the
# game log shows it alone.
SHOOTING = re.compile(r'Cycle combat mod|Shoot!|All guns cycling')


# States where doing nothing is the correct behaviour and the game log is
# legitimately silent: parked in station, waiting out a warp, winding down at
# session end. A bot sitting in these is not stuck.
BENIGN_IDLE = re.compile(
    r'assume we are docked|Already docked|I am in warp|wind down|session ends'
)
# Deliberately absent: "Wait for progress in game". It reads like idling but is
# the universal leaf of the decision tree -- it terminates a healthy branch and a
# stuck one alike. Treating it as benign reset the counter on every fourth line
# of the very cycle this exists to catch, and detection dropped to nothing.
#
# It cannot simply be counted against a window either. Every benign state reaches
# the tree's leaf, so "I am in warp" is always followed by this line and a window
# holding both can never be all-benign -- which is how run 114 raised an alarm,
# and a 9.7 MB screenshot, for a bot correctly sitting out a warp. So the leaf is
# passed over when judging a window, and a window of nothing but leaves is not
# benign, since that carries no evidence of *why* the bot is waiting.
BENIGN_LEAF = re.compile(r'^Wait for progress in game$')


class StallCheck:
    """Notices the decision tree going in circles while nothing happens in game.

    Neither half is sufficient alone, which the first version of this got wrong
    in both directions. Circling by itself is normal -- "All guns cycling / no
    idling drones / everything worth locking is locked" is a healthy bot waiting
    for a rat to die, and firing on that produced 11 false alarms on a run that
    completed 12 missions. A silent game log by itself is normal too: docked,
    travelling, or between fights, nothing is written for minutes at a time.

    Together they are precise. The bot claiming to act, the same handful of
    decisions recurring, and EVE writing nothing at all, is the fifteen-minute
    stall exactly: `Cycle combat mod` every reading with the weapon never firing.

    `shooting_only` narrows it further to decisions that claim to be shooting,
    which is the same evidence arriving sooner because the claim is specific.
    """

    def __init__(self, gamelog_dir, threshold, shooting_only=False):
        self.dir = gamelog_dir
        self.threshold = threshold
        self.shooting_only = shooting_only
        self.recent = deque(maxlen=DECISION_WINDOW)
        self.stuck_for = 0
        self.last_size = None

    def _newest_gamelog_size(self):
        """Size of EVE's current game log. Size rather than contents: it grows on
        any new line, which is all that needs knowing, and the file reaches tens
        of megabytes."""
        try:
            logs = [os.path.join(self.dir, f) for f in os.listdir(self.dir) if f.endswith(".txt")]
            return os.path.getsize(max(logs, key=os.path.getmtime)) if logs else None
        except OSError:
            return None

    def observe(self, decision):
        """Returns a reason string when stuck, else None."""
        if BENIGN_IDLE.search(decision):
            self.recent.append(decision)
            # Reset only while the bot is doing nothing *but* idling. A benign
            # line interleaved with a recurring action is a loop wearing an idle
            # line as camouflage, and zeroing on it hides exactly that: run 101
            # alternated "assume we are docked" with "I see a message box to
            # close" for 415 decisions, and because every other line was benign
            # the counter never climbed past one. The watcher sat there, alive
            # and silent, through the whole thing.
            judged = [d for d in self.recent if not BENIGN_LEAF.match(d)]
            if judged and all(BENIGN_IDLE.search(d) for d in judged):
                self.stuck_for = 0
            return None
        if self.shooting_only and not SHOOTING.search(decision):
            return None

        size = self._newest_gamelog_size()
        game_moved = size is not None and size != self.last_size
        self.last_size = size

        nothing_new = decision in self.recent
        self.recent.append(decision)

        if game_moved or not nothing_new:
            self.stuck_for = 0
            return None

        self.stuck_for += 1
        if self.stuck_for >= self.threshold:
            self.stuck_for = 0                       # report once, keep watching
            loop = " | ".join(dict.fromkeys(self.recent))
            what = "shooting with nothing landing" if self.shooting_only else "going in circles"
            return (f"{what}: {self.threshold} decisions with no new line in EVE's "
                    f"game log -- {loop[:200]}")
        return None


def game_window_id(pid):
    """The client's largest window -- a fullscreen game also has a small
    menu-bar strip of the same width, which a naive pick lands on."""
    probe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window_probe", "window_probe")
    out = subprocess.run([probe, "--all"], capture_output=True, text=True).stdout
    best = None
    for line in out.splitlines():
        m = re.search(r'window=(\d+).*owner_pid=(\d+).*w=([\d.]+) h=([\d.]+)', line)
        if m and int(m.group(2)) == pid:
            area = float(m.group(3)) * float(m.group(4))
            if best is None or area > best[1]:
                best = (int(m.group(1)), area)
    return best[0] if best else None


def capture(window_id, out_dir, label):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"stall_{time.strftime('%H%M%S')}_{label}.png")
    subprocess.run(["screencapture", "-x", "-o", "-l", str(window_id), path],
                   capture_output=True, timeout=10)
    return path if os.path.exists(path) and os.path.getsize(path) > 0 else None


class Reporter:
    """Prints stalls, and screenshots each distinct one exactly once.

    Every shot is a full-resolution Retina grab of the game window -- 7.5 MB on
    average here, 9.7 MB for the last one. With `--keep-going` and no dedupe, a
    genuinely wedged run reports on a metronome: the worst pathology on record
    repeated one decision 8,983 times, which at one shot per 40 is ~225 shots and
    ~1.7 GB of near-identical pictures of the same frozen screen. The alarm is
    worth having; the 225th photograph of it is not.

    Distinctness is judged on the reason with its numbers masked, because the
    same stall reports slightly different text each time -- distances and tick
    counts appear in the loop it quotes. A repeat still prints, so the log shows
    the stall persisting; it just does not photograph it again.
    """

    def __init__(self, window_id, out_dir, max_shots):
        self.window_id = window_id
        self.out_dir = out_dir
        self.max_shots = max_shots
        self.shots = 0
        self.counts = {}

    def report(self, label, reason):
        key = label + "|" + re.sub(r"\d+", "#", reason)
        self.counts[key] = self.counts.get(key, 0) + 1
        seen = self.counts[key]

        if seen > 1:
            print(f"STALL (repeat {seen}, no new screenshot): {reason}", flush=True)
            return
        if self.shots >= self.max_shots:
            print(f"STALL: {reason}\nSCREENSHOT: skipped, already at the "
                  f"{self.max_shots}-screenshot cap for this run", flush=True)
            return

        shot = capture(self.window_id, self.out_dir, label)
        self.shots += 1
        print(f"STALL: {reason}\nSCREENSHOT: {shot}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--pid", type=int, required=True, help="game client pid")
    ap.add_argument("--out", required=True, help="directory for screenshots")
    ap.add_argument("--threshold", type=int, default=CIRCLING_THRESHOLD,
                    help="decisions without progress before a stall is called")
    ap.add_argument("--gamelogs", default=os.path.expanduser("~/Documents/EVE/logs/Gamelogs"),
                    help="EVE's own game-log directory, for the silent-guns check")
    ap.add_argument("--keep-going", action="store_true",
                    help="report every stall and keep watching, instead of exiting on the first. "
                         "Without it one invocation gives one alarm and then stops, which looks "
                         "identical to having crashed.")
    ap.add_argument("--max-shots", type=int, default=20,
                    help="hard ceiling on screenshots per invocation (default 20). Distinct "
                         "stalls are already screenshotted only once each; this bounds the "
                         "disk cost even when a run finds many genuinely different ones.")
    args = ap.parse_args()

    win = game_window_id(args.pid)
    if win is None:
        print(f"no window found for pid {args.pid}", file=sys.stderr)
        return 1
    # Two views of the same evidence. The shooting-only one is narrower and so
    # fires sooner, and names the problem precisely when it does.
    reporter = Reporter(win, args.out, args.max_shots)
    circling = StallCheck(args.gamelogs, threshold=args.threshold)
    silent_guns = StallCheck(args.gamelogs, threshold=args.threshold, shooting_only=True)
    print(f"watching {os.path.basename(args.log)}; game window {win}; "
          f"threshold {args.threshold} decisions without progress", flush=True)

    # Start at the end: only stalls from now on are interesting.
    with open(args.log, errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        while True:
            line = fh.readline()
            if not line:
                if not subprocess.run(["pgrep", "-f", "botlab_host.py"],
                                      capture_output=True).stdout.strip():
                    print("RUN ENDED, no stall seen", flush=True)
                    return 0
                time.sleep(1)
                continue

            if STUCK_TEXT in line:
                reporter.report("askedforhelp", "bot asked for help")
                if not args.keep_going:
                    return 0

            m = DECISION.match(line.rstrip())
            if not m:
                continue
            text = m.group(1)

            for label, reason in (("circling", circling.observe(text)),
                                  ("silentguns", silent_guns.observe(text))):
                if reason:
                    reporter.report(label, reason)
                    if not args.keep_going:
                        return 0


if __name__ == "__main__":
    sys.exit(main())
