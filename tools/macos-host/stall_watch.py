#!/usr/bin/env python3
"""Watch a running bot's log for a stall and screenshot the client when one happens.

Two things count as a stall:

  * "I am stuck here and need help to continue." -- the bot saying so itself
    (askForHelpToGetUnstuck), which is never normal.
  * the same decision repeating REPEAT_THRESHOLD times in a row. Calibrated
    against 55 past runs: runs of >=80 identical decisions are 0.74% of all
    decision runs, so the threshold sits below the real pathologies (one run
    reached 8,983 repeats of "I see a message box to close") and above ordinary
    waiting.

Screenshots the game window by id rather than the screen, since the client is
often on another macOS Space where a plain screen grab catches the wrong thing.
"""
import argparse, os, re, subprocess, sys, time

REPEAT_THRESHOLD = 60
STUCK_TEXT = "I am stuck here and need help to continue."
DECISION = re.compile(r'^\++ (.*)$')


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--pid", type=int, required=True, help="game client pid")
    ap.add_argument("--out", required=True, help="directory for screenshots")
    ap.add_argument("--threshold", type=int, default=REPEAT_THRESHOLD)
    args = ap.parse_args()

    win = game_window_id(args.pid)
    if win is None:
        print(f"no window found for pid {args.pid}", file=sys.stderr)
        return 1
    print(f"watching {os.path.basename(args.log)}; game window {win}; "
          f"threshold {args.threshold} repeats", flush=True)

    # Start at the end: only stalls from now on are interesting.
    with open(args.log, errors="replace") as fh:
        fh.seek(0, os.SEEK_END)
        prev, run = None, 0
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
                shot = capture(win, args.out, "askedforhelp")
                print(f"STALL: bot asked for help\nSCREENSHOT: {shot}", flush=True)
                return 0

            m = DECISION.match(line.rstrip())
            if not m:
                continue
            text = m.group(1)
            run = run + 1 if text == prev else 1
            prev = text
            if run == args.threshold:
                shot = capture(win, args.out, "repeat")
                print(f"STALL: {run} identical decisions\n  {text[:110]}\n"
                      f"SCREENSHOT: {shot}", flush=True)
                return 0


if __name__ == "__main__":
    sys.exit(main())
