"""Raise a process's window to the front, hard, and say whether it worked.

    python raise_window.py <pid>

The logic lives in ``input.bring_window_to_foreground``; this is the hand-driven
front end for it, and it passes ``allow_synthetic_alt=True`` because a person at
a prompt is not a bot -- see that function's docstring for why the bot's own
path must never pass it.

**Never run this alongside a bot.**  The ALT press is indistinguishable from a
person at the keyboard, so the host stands down for five seconds; and stealing
the foreground from a client the bot is clicking is worse than that.

Verified by reading ``GetForegroundWindow`` back, never by assuming, because a
screenshot of the wrong window looks exactly like a screenshot of the right one.
That is not hypothetical: this session captured the EVE launcher while it was
buried, read the terminal that was covering it, and drew a conclusion about the
launcher from it.
"""
import argparse
import sys

sys.path.insert(0, r"C:\botlab\smerwin-bots\tools\windows-host")
from input import bring_window_to_foreground, foreground_window_title  # noqa: E402
from window_probe import declare_dpi_awareness, windows_of_process  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description="raise a process's largest visible window to the foreground")
    parser.add_argument("pid", type=int)
    args = parser.parse_args()

    declare_dpi_awareness()
    wins = [w for w in windows_of_process(args.pid)
            if w.visible and w.width > 200 and w.height > 200]
    if not wins:
        return "no visible window for pid %d" % args.pid
    win = max(wins, key=lambda w: w.width * w.height)
    print("target %dx%d at (%d,%d) %r"
          % (win.width, win.height, win.x, win.y, win.title))

    if bring_window_to_foreground(win.hwnd, allow_synthetic_alt=True):
        print("foreground: yes")
        return 0
    return "NOT foreground -- front window is %r" % foreground_window_title()


if __name__ == "__main__":
    sys.exit(main())
