"""Launch a named EVE character from the EVE launcher, and prove it worked.

    python launch_character.py "Joan d'Arkonor"
    python launch_character.py --list
    python launch_character.py --record "Some Other Pilot"

Why this exists at all: starting the client by hand is the one step of a run
that had no script, so every restart was a human pressing PLAY NOW and every
agent restart was a hardcoded pixel offset for one character.

Why it works by *press-and-hold on the character's avatar* rather than by
pressing PLAY NOW: PLAY NOW launches whichever character the launcher happens
to have selected, which is a different thing from the character you asked for
(`autoSelectCharacter` is on, so it is usually the last one played). Holding a
specific avatar launches *that* character. `CLAUDE.md` records the hold as a
macOS quirk -- "PLAY NOW ignores synthetic clicks" -- but it is not a quirk and
not macOS: the launcher has a setting, `actionToActivateMethod`, and this reads
it rather than assuming either way.

Three things here are deliberately paranoid, each because the cheap version has
already produced a confident wrong answer on this machine:

- **The raise is verified.** ``bring_window_to_foreground`` does the documented
  ``AttachThreadInput`` dance and still returns False against the launcher,
  because Windows keeps a *foreground lock* the attach alone does not clear. A
  synthetic ALT press clears it. Skipping the check means clicking at
  coordinates that belong to whatever window is actually in front -- which is
  how a screenshot of Discord got mistaken for a screenshot of the launcher.
- **The character is verified after launch, from the window title.** The client
  titles itself ``EVE - <character>`` once in, so a launch that selected the
  wrong pilot is detectable rather than silent. Routing the wrong character
  while reporting success has already cost a whole session here (the ESI token
  belonged to a different pilot), and this is the same failure shape.
- **"In game" is not "the process exists".** A client sits on the character
  screen for a long time with a readable UI tree; a readiness check that accepts
  it reports success roughly a minute early. ``--wait-in-game`` waits for an
  actual overview or station window.

Positions are stored as *fractions* of the launcher window in
``launcher_characters.json``, not pixels, so they survive the window being moved
or resized. Record a new pilot with ``--record``; nothing here is specific to
one account.

This never types a credential. The launcher is expected to be already signed in
-- entering an EVE password is the operator's job, never this script's.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import input as win_input  # noqa: E402
from window_probe import declare_dpi_awareness, windows_of_process  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "launcher_characters.json")

user32 = ctypes.WinDLL("user32", use_last_error=True)

# The launcher's own settings file, which knows whether a character is activated
# by a click or by a press-and-hold.
LAUNCHER_DATA = os.path.join(
    os.environ.get("APPDATA", ""), "EVE Online", "launcher-data.json")
LAUNCHER_EXE = os.path.join(
    os.environ.get("LOCALAPPDATA", ""), "eve-online", "eve-online.exe")


# --------------------------------------------------------------------------
# the launcher window


def launcher_window(timeout=0.0):
    """The launcher's main window, or None. Waits up to `timeout` seconds."""
    deadline = time.time() + timeout
    while True:
        for proc in _launcher_pids():
            wins = [w for w in windows_of_process(proc)
                    if w.visible and w.width > 400 and w.height > 300
                    and "launcher" in (w.title or "").lower()]
            if wins:
                return max(wins, key=lambda w: w.width * w.height)
        if time.time() >= deadline:
            return None
        time.sleep(2)


def _launcher_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process eve-online -ErrorAction SilentlyContinue | "
         "ForEach-Object { $_.Id }"],
        capture_output=True, text=True)
    return [int(line) for line in out.stdout.split() if line.strip().isdigit()]


def start_launcher():
    if not os.path.exists(LAUNCHER_EXE):
        sys.exit("launcher not found at %s" % LAUNCHER_EXE)
    print("starting the launcher ...")
    subprocess.Popen([LAUNCHER_EXE], close_fds=True)
    win = launcher_window(timeout=120)
    if win is None:
        sys.exit("the launcher did not open a window within 120s")
    return win


def raise_window(win, attempts=5):
    """Bring `win` to the front and *confirm* it, or die.

    ``SetForegroundWindow`` is a request, not a command. Windows refuses it from
    a process that does not own the foreground, and the documented thread-attach
    workaround is not sufficient on its own -- a synthetic ALT keypress is what
    releases the foreground lock.
    """
    KEYEVENTF_KEYUP, VK_MENU = 0x0002, 0x12
    SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x0002, 0x0001, 0x0040
    for _ in range(attempts):
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.ShowWindow(wintypes.HWND(win.hwnd), 9)  # SW_RESTORE
        user32.SetWindowPos(wintypes.HWND(win.hwnd), wintypes.HWND(0), 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetForegroundWindow(wintypes.HWND(win.hwnd))
        user32.BringWindowToTop(wintypes.HWND(win.hwnd))
        time.sleep(0.4)
        if user32.GetForegroundWindow() == win.hwnd:
            return True
    sys.exit("could not bring the launcher to the front -- refusing to click, "
             "because the click would land on whatever window is actually there")


# --------------------------------------------------------------------------
# how the launcher wants a character activated


def activation_method(override=None):
    """('hold'|'click', seconds) -- read from the launcher's own settings."""
    if override:
        return override, 3.0
    method, speed = "hold", "normal"
    try:
        with open(LAUNCHER_DATA, encoding="utf-8") as handle:
            data = json.load(handle)
        state = data.get("state", {})
        settings = state.get("settings", {})
        method = settings.get("actionToActivateMethod", method)
        launcher = state.get("v2/settings", {}).get("eve-launcher", {})
        method = launcher.get("actionToActivateMethod", method)
        speed = launcher.get("actionToActivateSpeed", speed)
    except (OSError, ValueError) as exc:
        print("  (could not read launcher settings, assuming %r: %s)"
              % (method, exc))
    seconds = {"fast": 1.5, "normal": 3.0, "slow": 5.0}.get(speed, 3.0)
    return method, seconds


# --------------------------------------------------------------------------
# the character registry


def load_registry():
    if not os.path.exists(REGISTRY):
        return {}
    with open(REGISTRY, encoding="utf-8") as handle:
        return json.load(handle)


def save_registry(reg):
    text = json.dumps(reg, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    with open(REGISTRY, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def lookup(reg, name):
    """Case-insensitive, so the shell does not have to match capitalisation."""
    for key, value in reg.items():
        if key.lower() == name.lower():
            return key, value
    return None, None


def record(name, seconds=12):
    """Store where a character's avatar sits, as a fraction of the window.

    A countdown rather than a prompt: this is often run from a button or a
    non-interactive shell, where ``input()`` reads EOF immediately and the
    recorded point would be wherever the pointer happened to be.
    """
    win = launcher_window(timeout=5)
    if win is None:
        sys.exit("the launcher is not running -- open it, then record")
    print("launcher window %dx%d at (%d,%d)"
          % (win.width, win.height, win.x, win.y))
    print()
    print("Put the mouse pointer on %s's avatar in the launcher." % name)
    for left in range(seconds, 0, -1):
        print("  recording in %2ds ..." % left, end="\r", flush=True)
        time.sleep(1)
    print(" " * 40, end="\r")
    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    fx = (point.x - win.x) / float(win.width)
    fy = (point.y - win.y) / float(win.height)
    if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
        sys.exit("that point (%d,%d) is outside the launcher window"
                 % (point.x, point.y))
    reg = load_registry()
    key, _ = lookup(reg, name)
    reg[key or name] = {"avatar": [round(fx, 4), round(fy, 4)]}
    save_registry(reg)
    print("recorded %s at fraction (%.4f, %.4f) -> %s"
          % (name, fx, fy, os.path.basename(REGISTRY)))


# --------------------------------------------------------------------------
# clients


def client_pids():
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process exefile -ErrorAction SilentlyContinue | "
         "ForEach-Object { $_.Id }"],
        capture_output=True, text=True)
    return {int(line) for line in out.stdout.split() if line.strip().isdigit()}


def client_titles(pids):
    """Window titles of the given clients.

    Titles only -- never the command line, which carries the account's live SSO
    and refresh tokens.
    """
    titles = {}
    for pid in pids:
        for win in windows_of_process(pid):
            if win.visible and win.title:
                titles[pid] = win.title
    return titles


def wait_for_character(name, before, timeout=300):
    """Wait for a client that titles itself for `name`. Returns its pid."""
    wanted = ("EVE - %s" % name).lower()
    deadline = time.time() + timeout
    seen_new = set()
    while time.time() < deadline:
        new = client_pids() - before
        seen_new |= new
        titles = client_titles(seen_new)
        for pid, title in titles.items():
            if title.strip().lower() == wanted:
                return pid
        wrong = [t for t in titles.values()
                 if t.strip().lower().startswith("eve - ")
                 and t.strip().lower() != wanted]
        if wrong:
            sys.exit("WRONG CHARACTER: the launcher started %r, not %r.\n"
                     "The client is still running; close it yourself if that is "
                     "not what you wanted." % (wrong[0], name))
        time.sleep(3)
    if seen_new:
        sys.exit("a client started but never titled itself %r within %ds "
                 "(titles seen: %s)"
                 % ("EVE - " + name, timeout,
                    sorted(set(client_titles(seen_new).values())) or "none"))
    sys.exit("no client process appeared within %ds -- the activation did not "
             "take" % timeout)


def wait_in_game(pid, timeout=300):
    """Wait for a tree that is actually the game, not the character screen.

    The character screen has a perfectly readable UI tree with a ShipUI node in
    it, so counting nodes -- or trusting ShipUI -- declares victory about a
    minute early. An overview or a station window is the honest signal.
    """
    try:
        import tree_walker
    except ImportError as exc:
        print("  (skipping the in-game wait: %s)" % exc)
        return False
    deadline = time.time() + timeout
    while time.time() < deadline:
        session = None
        try:
            session = tree_walker.open_client(pid)
            root = tree_walker.find_ui_root(session.reader, session.py)
            if root:
                tree = session.walker.read_tree(root)
                names = []

                def walk(node):
                    names.append(node["pythonObjectTypeName"])
                    for child in node["children"]:
                        walk(child)

                walk(tree)
                overview = names.count("OverviewWindow")
                station = names.count("StationWindow") + names.count("LobbyWnd")
                print("  nodes=%-6d overview=%d station=%d"
                      % (len(names), overview, station))
                if overview or station:
                    print("IN GAME (%s)" % ("in space" if overview else "docked"))
                    return True
        except Exception as exc:  # noqa: BLE001 - the client is still loading
            print("  not readable yet: %s" % exc)
        finally:
            if session is not None:
                try:
                    session.reader.close()
                except Exception:  # noqa: BLE001
                    pass
        time.sleep(8)
    print("still not in game after %ds -- the client is up, but something is "
          "holding it on the character screen" % timeout)
    return False


# --------------------------------------------------------------------------


def launch(name, args):
    reg = load_registry()
    key, entry = lookup(reg, name)
    if entry is None:
        sys.exit("no recorded position for %r.\nKnown: %s\nRecord it with:  "
                 "python launch_character.py --record %r"
                 % (name, ", ".join(sorted(reg)) or "(none)", name))
    name = key  # the registry's spelling is the one the title will carry

    win = launcher_window(timeout=5) or start_launcher()
    print("launcher window %dx%d at (%d,%d)"
          % (win.width, win.height, win.x, win.y))

    fx, fy = entry["avatar"]
    sx = win.x + int(round(fx * win.width))
    sy = win.y + int(round(fy * win.height))
    method, seconds = activation_method(args.method)
    seconds = args.hold_seconds if args.hold_seconds else seconds

    print("%s -> fraction (%.4f, %.4f) -> screen (%d,%d), by %s%s"
          % (name, fx, fy, sx, sy, method,
             " for %.1fs" % seconds if method == "hold" else ""))
    if args.dry_run:
        print("dry run -- not clicking")
        return 0

    before = client_pids()
    print("clients before: %d" % len(before))

    raise_window(win)

    # `raise_window` sends SW_RESTORE, so a launcher that was maximized is a
    # different rect by the time it is frontmost -- and the point above was
    # computed against the rect as it was *before* the raise.  On this machine
    # that is 1712x1083 at (-1,-8) maximized against 1402x801 at (154,137)
    # restored, which put two launch attempts about 150 px off the avatar and
    # reported only "the activation did not take".  The launcher's own content
    # does not scale with the window either: it draws at a fixed size, centred,
    # so the same fraction genuinely means two different points.
    #
    # Re-resolve after the raise and recompute against the rect that will be on
    # screen when the click lands.  Said out loud rather than silently, because
    # a click that misses looks exactly like a launcher that ignored it.
    raised = launcher_window(timeout=5) or win
    if (raised.x, raised.y, raised.width, raised.height) != \
            (win.x, win.y, win.width, win.height):
        sx = raised.x + int(round(fx * raised.width))
        sy = raised.y + int(round(fy * raised.height))
        print("the raise changed the launcher rect to %dx%d at (%d,%d)"
              % (raised.width, raised.height, raised.x, raised.y))
        print("recomputed target -> screen (%d,%d)" % (sx, sy))

    io = win_input.WindowsInput(execute=True)
    io.glide_to(sx, sy, force_movement=True)
    time.sleep(0.3)
    io.button_down(0)
    time.sleep(seconds if method == "hold" else 0.06)
    io.button_up(0)

    print("waiting for a client titled %r ..." % ("EVE - " + name))
    pid = wait_for_character(name, before, timeout=args.timeout)
    print("CLIENT STARTED as %s (pid %d)" % (name, pid))

    if args.wait_in_game:
        wait_in_game(pid, timeout=args.timeout)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Launch a named EVE character from the EVE launcher.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="The launcher must already be signed in; this never types a "
               "credential.")
    parser.add_argument("character", nargs="?", help="character name to launch")
    parser.add_argument("--list", action="store_true",
                        help="list the characters that have a recorded position")
    parser.add_argument("--record", metavar="NAME",
                        help="record where a character's avatar sits")
    parser.add_argument("--record-seconds", type=int, default=12,
                        help="countdown before --record samples the pointer")
    parser.add_argument("--method", choices=("hold", "click"),
                        help="override the launcher's own activation setting")
    parser.add_argument("--hold-seconds", type=float, default=0.0,
                        help="override the hold duration")
    parser.add_argument("--wait-in-game", action="store_true",
                        help="also wait for an overview or station window")
    parser.add_argument("--timeout", type=int, default=300,
                        help="seconds to wait for the client (default 300)")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve and print the target, but do not click")
    args = parser.parse_args()

    declare_dpi_awareness()

    if args.list:
        reg = load_registry()
        if not reg:
            print("no characters recorded yet (%s)" % REGISTRY)
            return 0
        method, seconds = activation_method(args.method)
        print("activation: %s%s"
              % (method, " for %.1fs" % seconds if method == "hold" else ""))
        for key in sorted(reg):
            fx, fy = reg[key]["avatar"]
            print("  %-24s avatar at (%.4f, %.4f)" % (key, fx, fy))
        return 0

    if args.record:
        record(args.record, args.record_seconds)
        return 0

    if not args.character:
        parser.error("give a character name, --list, or --record NAME")
    return launch(args.character, args)


if __name__ == "__main__":
    sys.exit(main())
