#!/usr/bin/env python3
"""Make sure the EVE client is running as a named character, launching it if not.

    python3 launch_client.py --character "Gal Bistot"
    python3 launch_client.py --character "Gal Bistot" --check   # report only

Exit status is the answer: `0` the client is up as that character, non-zero it
is not and why is on stderr. Nothing here is best-effort -- every step either
verifies its own result or fails loudly, because the failures this replaces all
looked like success.

## What makes launching awkward, and what each step is for

**A process is not a logged-in character.** `exefile` exists from the moment the
client starts, minutes before the character is in space, and it exists at the
character-select screen too. The window *title* is the only thing that says who
is flying: it becomes `EVE - <character>` and nothing else does. So that is the
success condition here, and waiting for the process is not.

**PLAY NOW ignores synthetic clicks.** The way in is a press-and-hold on the
character's avatar for several seconds (see MACOS.md). A normal click does
nothing at all.

**The launcher must be frontmost first.** The first press-and-hold ever tried
here did nothing but activate the window; the gesture was consumed making the
app active. This activates and then *confirms* the window is on screen before
touching the mouse.

**The avatar's position is per-layout and must not be hard-coded.** CLAUDE.md
says to re-derive it from a capture rather than trusting a remembered point, and
the launcher is an Electron app: its account list is not in the game client's
memory, so `eve_read` cannot see it, and it exposes nothing over the
accessibility API -- `AXUIElement` on its window answers `missing value` for
every child. Reading the pixels is what is left, so `ocr_probe` (Vision) finds
the character's own row and this converts that to a screen point.

**Two rows can carry the same name.** The account list shows `Gal Bistot` and
the right-hand panel shows `Gal Bistot 5.00` for the selected character. Only
the first is clickable, so the match is on the *whole* label rather than a
substring, and ties break leftmost -- the list is left of the panel.

**A synthetic glide is not a hover unless it is paced.** `cg_input` posts every
move with `CGEventPost` and sleeps for nothing, so a script piped in at once is
a burst rather than a trajectory. Measured here: 24 unpaced moves left the
cursor at an arbitrary intermediate point, in one run at y = -38.8, off the top
of the screen -- while `cg_input` answered `ok` to all 24 and nothing reported
an error. The launcher then quite correctly lit nothing, and the missing hover
looked like the launcher ignoring us. Everything that moves the mouse here
therefore drives one persistent process and spaces the steps out itself.

**The launcher must acknowledge the cursor before anything is pressed.** It
lights the avatar with a thin cyan glow the moment a real hover lands on the
row, so this captures the avatar before and after gliding onto it and refuses
to press unless it lit -- a mis-located point then costs a few seconds instead
of a stray press-and-hold somewhere unknown.

Two things about that test are what make it work rather than merely exist.
It judges on the **strongest** pixel, not the average: the glow is a thin ring,
so over a box big enough to hold the avatar it averages to 5.05 while its peak
is 31, and every mean-based threshold clear of the animated backdrop reads a
plain hover as nothing. And the watched region is the **avatar's**, fixed,
rather than a box around wherever the cursor was probed -- the row also lights
when the cursor sits between the avatar and the name, so a moving box measures
a different thing at each step and can report a reaction for a point that is
not the character's avatar. Measured separation at that box: two captures with
the cursor off the row differ by at most 1, and a hover reads 36-37.

The `Click and hold to launch <character>` tooltip is stronger when it appears,
because it names the character, and it is reported when seen. It is *not*
required: it is a delayed tooltip that hides itself again, and it was observed
not drawing at all across eight seconds of a hover the avatar was visibly
responding to. A check that flaky must not be the thing standing between the
script and its job.

## What it will not do

It will not touch a client that is already running as somebody else. Quitting a
live client can strand a ship in space, and this has no way to know whether that
one is mid-mission, so it reports and stops.

It never prints the client's command line. The launcher starts the game with
`/ssoToken=` and `/refreshToken=` in its arguments, so `pgrep -f` is used
without `-l` and `ps` is not used at all -- see CLAUDE.md.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
WINDOW_PROBE = os.path.join(HERE, "window_probe", "window_probe")
CG_INPUT = os.path.join(HERE, "cg_input", "cg_input")
OCR_PROBE = os.path.join(HERE, "ocr_probe", "ocr_probe")

CLIENT_PROCESS_PATTERN = "SharedCache/tq/EVE.app"
LAUNCHER_PROCESS_PATTERN = "eve-online"
LAUNCHER_BUNDLE_ID = "com.ccpgames.eve-online-launcher"

# How long the avatar has to be held. MACOS.md says ~5s; 6.5 leaves margin
# without being long enough to look like a stuck button.
HOLD_SECONDS = 6.5
# The client takes a while between the hold and a character being in the world.
DEFAULT_LOGIN_TIMEOUT = 240
# Where the avatar sits relative to the name label, in image pixels: it is the
# square immediately left of the name, vertically centred on it. Expressed
# against the label OCR found *by name*, so the point pressed belongs to the
# character asked for -- which is the whole job -- and so it survives a
# different window position or backing scale. Measured live on this layout: the
# label reads at x=1066 and the avatar spans x=920..1040, y centred on the text.
AVATAR_LEFT_OF_LABEL = 150
AVATAR_RIGHT_OF_LABEL = 26
AVATAR_HALF_HEIGHT = 60
# Probed in this order, as offsets from the avatar's own centre in image pixels.
# Every one stays *inside* the avatar: the row also lights when the cursor is
# between the avatar and the name, so a probe that walked toward the label could
# report a reaction and then press somewhere that is not the character's avatar.
AVATAR_PROBE_OFFSETS = ((0, 0), (-30, 0), (30, 0), (0, -30), (0, 30))
# A glide is only a hover if it arrives over time. `cg_input` posts each move
# with `CGEventPost` and no pacing of its own, and a burst of them is not
# delivered as a trajectory -- measured, 25 unpaced moves left the cursor at an
# arbitrary intermediate point, once off-screen entirely -- so the caller has to
# space them out. This is a whole gesture, not a per-step delay.
GLIDE_SECONDS = 0.4
GLIDE_STEPS = 24


class LaunchError(Exception):
    """Something verifiable did not verify."""


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, **kwargs)


def pgrep(pattern):
    """Pids matching a command line, without ever printing that command line.

    `-f` matches the full argument vector and prints only pids; `-fl` would
    print the arguments, and the client's carry live credentials.
    """
    result = run(["pgrep", "-f", pattern])
    return [int(p) for p in result.stdout.split()]


def windows_for(pid):
    """Every window the probe can see for a pid, on any Space."""
    result = run([WINDOW_PROBE, "--all"])
    rows = []
    for line in result.stdout.splitlines():
        if "owner_pid=%d" % pid not in line:
            continue
        bounds = re.search(
            r"bounds=\{x=([-\d.]+) y=([-\d.]+) w=([-\d.]+) h=([-\d.]+)\}", line)
        number = re.search(r"^window=(\d+)", line)
        scale = re.search(r"backing_scale=([\d.]+)", line)
        name = re.search(r'name="([^"]*)"', line)
        if not (bounds and number):
            continue
        x, y, w, h = (float(g) for g in bounds.groups())
        rows.append({
            "id": int(number.group(1)), "x": x, "y": y, "w": w, "h": h,
            "area": w * h, "name": name.group(1) if name else "",
            "scale": float(scale.group(1)) if scale else 1.0,
        })
    return rows


def main_window(pid):
    """The largest window by area.

    Not the first one over a width threshold: a fullscreen EVE window has a
    same-width menu-bar strip overlay beside it, and picking that gives a badly
    wrong scale and useless coordinates (CLAUDE.md).
    """
    rows = windows_for(pid)
    return max(rows, key=lambda r: r["area"]) if rows else None


def client_character():
    """The character the running client is flying, or None.

    `EVE - <name>` is the title once a character is in the world; the bare `EVE`
    that precedes it is the client still loading or at character select.
    """
    for pid in pgrep(CLIENT_PROCESS_PATTERN):
        for window in windows_for(pid):
            match = re.match(r"^EVE - (.+)$", window["name"].strip())
            if match:
                return match.group(1).strip()
    return None


def client_is_running():
    return bool(pgrep(CLIENT_PROCESS_PATTERN))


def ocr(image_path):
    """Text observations as (confidence, x, y, w, h, text), image pixels."""
    if not os.access(OCR_PROBE, os.X_OK):
        raise LaunchError(
            "%s is missing or not executable -- build it with:\n"
            "  swiftc -O -o %s %s.swift" % (OCR_PROBE, OCR_PROBE, OCR_PROBE))
    result = run([OCR_PROBE, image_path])
    if result.returncode != 0:
        raise LaunchError("ocr_probe failed: %s" % result.stderr.strip())
    observations = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        confidence, x, y, w, h, text = parts
        observations.append((float(confidence), float(x), float(y),
                             float(w), float(h), text))
    return observations


def capture(window_id):
    handle, path = tempfile.mkstemp(suffix=".png", prefix="launch-client-")
    os.close(handle)
    result = run(["screencapture", "-x", "-o", "-l", str(window_id), path])
    if result.returncode != 0 or not os.path.getsize(path):
        os.unlink(path)
        raise LaunchError("could not capture window %s -- Screen Recording "
                          "permission is granted per-app, to whichever "
                          "terminal this runs from" % window_id)
    return path


def image_point_to_screen(window, image_x, image_y):
    """Image pixels to screen points, through the window's own backing scale."""
    return (window["x"] + image_x / window["scale"],
            window["y"] + image_y / window["scale"])


def find_character_row(observations, character):
    """The account-list row for this character, leftmost first.

    Whole-label equality rather than a substring: the right-hand panel renders
    `<name> <security status>` for the selected character and is not clickable.
    A substring rule matches both and the panel usually sorts first.
    """
    wanted = character.strip().lower()
    exact = [o for o in observations if o[5].strip().lower() == wanted]
    if not exact:
        raise LaunchError(
            "the launcher does not show a row named %r. Rows it does show: %s"
            % (character, ", ".join(sorted({o[5] for o in observations
                                            if o[5].strip()}))[:400]))
    return sorted(exact, key=lambda o: o[1])


def tooltip_names(observations, character):
    """Whether `Click and hold to launch <character>` is on screen.

    The strongest confirmation when it appears, and it does not reliably: it is
    a delayed tooltip that hides itself again, so a capture can straddle it.
    Preferred, never required -- `region_reacted` is what must hold.
    """
    wanted = character.strip().lower()
    for _, _, _, _, _, text in observations:
        lowered = text.strip().lower()
        if "click and hold to launch" in lowered and wanted in lowered:
            return True
    return False


def region_change(before_path, after_path, box):
    """The largest single-channel change anywhere in `box`, 0-255.

    The *strongest* pixel rather than the average, which is the whole
    difference between this working and not. The launcher acknowledges a hover
    by drawing a thin cyan glow around the avatar's edge, so averaging it over
    a box big enough to contain the avatar dilutes it to nearly nothing:
    measured on the same pair of captures, mean 5.05 against a max of 31, so a
    mean-based test with any threshold clear of the animated background could
    not see a hover that was plainly there.

    Measured separation on this launcher, at the avatar box below: two captures
    with the cursor away from the row differ by at most **1**, and a hover
    reads **36-37**. The backdrop animates and the news panel changes, but not
    inside this box, which is why a small fixed region beats a whole-window
    comparison.
    """
    from PIL import Image, ImageChops, ImageStat
    with Image.open(before_path) as before, Image.open(after_path) as after:
        left, top, right, bottom = box
        left = max(0, int(left)); top = max(0, int(top))
        right = min(before.width, int(right)); bottom = min(before.height, int(bottom))
        if right <= left or bottom <= top:
            return 0
        a = before.convert("RGB").crop((left, top, right, bottom))
        b = after.convert("RGB").crop((left, top, right, bottom))
        extrema = ImageStat.Stat(ImageChops.difference(a, b)).extrema
        return max(high for _, high in extrema)


# An order of magnitude above the measured noise of 1 and well under the
# measured hover of 36 -- there is no distribution to cut through here, only a
# gap to sit in.
AVATAR_REACTION_THRESHOLD = 12


def cg_input_session():
    """One `cg_input` process, to be fed a line at a time.

    Everything here drives it this way rather than through `run`, for two
    separate reasons that both produce input landing somewhere other than where
    it was aimed. `cg_input` tracks the click position as process-local state
    set by the last `move`, so a fresh process per command presses at (0, 0)
    (CLAUDE.md). And a whole script piped in at once is executed with no pacing,
    which is what broke the glide below.
    """
    return subprocess.Popen([CG_INPUT], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)


def send(session, line):
    session.stdin.write(line + "\n")
    session.stdin.flush()


def finish(session):
    session.stdin.close()
    session.wait(timeout=10)


def glide_mouse(x, y, start=None):
    """Glide through intermediate points, over time, rather than teleport.

    Two things matter and only the first was obvious. A single jump is not a
    trajectory and the launcher does not read it as a hover -- the same finding
    CLAUDE.md records for the game's own Photon UI, and it holds for the
    Electron launcher too.

    The second is that the moves have to be *paced*. `cg_input` posts each one
    with `CGEventPost` and sleeps for nothing, so a burst piped in together is
    not a slow trajectory, it is a burst: measured here, 24 unpaced moves left
    the cursor at an arbitrary intermediate point rather than the destination,
    in one run at y = -38.8, off the top of the screen. Nothing reported an
    error -- `cg_input` answered `ok` to every line -- so the hover simply never
    happened and the launcher was blamed for not lighting up.
    """
    sx, sy = start if start else (x + 260.0, y - 240.0)
    session = cg_input_session()
    try:
        for i in range(GLIDE_STEPS + 1):
            t = i / float(GLIDE_STEPS)
            ease = t * t * (3 - 2 * t)
            send(session, "move %.1f %.1f" % (sx + (x - sx) * ease,
                                              sy + (y - sy) * ease))
            time.sleep(GLIDE_SECONDS / GLIDE_STEPS)
    finally:
        finish(session)


def press_and_hold(x, y, seconds):
    """Press, hold and release at one point, from one process.

    The move, the press and the release must share a process: `up` acts at the
    position that process last moved to, so releasing from a second process
    releases at (0, 0) -- the press lands on the avatar and the release lands in
    the corner, which is not a press-and-hold at all.
    """
    session = cg_input_session()
    try:
        send(session, "move %.1f %.1f" % (x, y))
        time.sleep(0.2)
        send(session, "down 0")
        time.sleep(seconds)
        send(session, "up 0")
        time.sleep(0.2)
    finally:
        finish(session)


def bring_launcher_to_front(launcher_pid, attempts=4):
    for _ in range(attempts):
        run(["osascript", "-e",
             'tell application id "%s" to activate' % LAUNCHER_BUNDLE_ID])
        time.sleep(1.2)
        onscreen = run([WINDOW_PROBE]).stdout
        window = main_window(launcher_pid)
        if window and re.search(r"^window=%d\b" % window["id"], onscreen,
                                re.MULTILINE):
            return window
    raise LaunchError(
        "the launcher would not come to the front. A click on a launcher that "
        "is not frontmost is consumed activating it, so this refuses to press.")


def start_launcher():
    if pgrep(LAUNCHER_PROCESS_PATTERN):
        return
    run(["open", "-b", LAUNCHER_BUNDLE_ID])
    for _ in range(40):
        if pgrep(LAUNCHER_PROCESS_PATTERN):
            return
        time.sleep(1)
    raise LaunchError("the launcher (%s) did not start" % LAUNCHER_BUNDLE_ID)


def wait_for_character(character, timeout):
    """Poll the window title, which is the only thing that names the pilot."""
    deadline = time.time() + timeout
    saw_process = False
    while time.time() < deadline:
        current = client_character()
        if current and current.lower() == character.strip().lower():
            return current
        if current:
            raise LaunchError(
                "the client came up as %r, not %r" % (current, character))
        saw_process = saw_process or client_is_running()
        time.sleep(4)
    raise LaunchError(
        "no window titled 'EVE - %s' within %ds (client process %s). A process "
        "without that title is the client still loading or sitting at "
        "character select." %
        (character, timeout, "did start" if saw_process else "never started"))


def launch(character, timeout):
    start_launcher()
    launcher_pids = pgrep(LAUNCHER_PROCESS_PATTERN)
    if not launcher_pids:
        raise LaunchError("no launcher process to drive")

    # The launcher is Electron, so most of these pids are helper processes with
    # no window at all. Take the one owning the largest window rather than the
    # first: driving a helper fails as "the launcher would not come to the
    # front", which sends the reader looking at activation rather than at pid
    # choice.
    windowed = [(main_window(pid), pid) for pid in launcher_pids]
    windowed = [(w, pid) for w, pid in windowed if w]
    if not windowed:
        raise LaunchError(
            "no launcher process owns a window (%d processes matched %r). If "
            "window titles are missing entirely, Screen Recording permission "
            "is granted per-app and this one does not have it."
            % (len(launcher_pids), LAUNCHER_PROCESS_PATTERN))
    launcher_pid = max(windowed, key=lambda pair: pair[0]["area"])[1]

    window = bring_launcher_to_front(launcher_pid)
    print("launcher window %d at (%g,%g) %gx%g" %
          (window["id"], window["x"], window["y"], window["w"], window["h"]),
          file=sys.stderr)

    shot = capture(window["id"])
    try:
        rows = find_character_row(ocr(shot), character)
    finally:
        os.unlink(shot)

    label = rows[0]
    _, lx, ly, lw, lh, _ = label
    print("found %r at image (%.0f,%.0f)" % (character, lx, ly), file=sys.stderr)

    # The avatar belonging to *this* name, and the region watched for the glow
    # that says the cursor is on it. Both are fixed here rather than moving with
    # the probe point: the question asked of every capture is "is this
    # character's avatar lit", which is the same question wherever the cursor
    # went.
    avatar = (lx - AVATAR_LEFT_OF_LABEL, ly + lh / 2.0 - AVATAR_HALF_HEIGHT,
              lx - AVATAR_RIGHT_OF_LABEL, ly + lh / 2.0 + AVATAR_HALF_HEIGHT)
    centre_x = (avatar[0] + avatar[2]) / 2.0
    centre_y = (avatar[1] + avatar[3]) / 2.0

    # The baseline has to be taken with the cursor demonstrably off the row.
    # Capturing it where the cursor happens to be already is how this fails
    # silently: a previous attempt leaves the cursor parked on the avatar, so
    # the baseline is the *lit* state, the probe matches it, and the script
    # refuses to press on an avatar that was responding the whole time.
    park_x, park_y = image_point_to_screen(window, avatar[0] - 300, centre_y)
    glide_mouse(park_x, park_y)
    time.sleep(1.0)
    baseline = capture(window["id"])

    best = None
    try:
        for offset_x, offset_y in AVATAR_PROBE_OFFSETS:
            image_x, image_y = centre_x + offset_x, centre_y + offset_y
            screen_x, screen_y = image_point_to_screen(window, image_x, image_y)
            glide_mouse(screen_x, screen_y)
            time.sleep(1.5)
            probe = capture(window["id"])
            try:
                change = region_change(baseline, probe, avatar)
                if change >= AVATAR_REACTION_THRESHOLD:
                    named = tooltip_names(ocr(probe), character)
                    print("%r's avatar lit (change %d) at image (%.0f,%.0f)%s"
                          % (character, change, image_x, image_y,
                             "; tooltip names the character" if named
                             else "; no tooltip (it is not always drawn)"),
                          file=sys.stderr)
                    best = (screen_x, screen_y)
                    break
                print("  no reaction (change %d) at image (%.0f,%.0f)"
                      % (change, image_x, image_y), file=sys.stderr)
            finally:
                os.unlink(probe)
    finally:
        os.unlink(baseline)

    if best is None:
        raise LaunchError(
            "%r's avatar never lit while the cursor was on it. Refusing to "
            "press and hold on a point the launcher does not acknowledge -- a "
            "press somewhere unknown is worse than not launching." % character)

    screen_x, screen_y = best
    print("holding %.1fs at screen (%.1f,%.1f)"
          % (HOLD_SECONDS, screen_x, screen_y), file=sys.stderr)
    press_and_hold(screen_x, screen_y, HOLD_SECONDS)
    return wait_for_character(character, timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--character", required=True,
                        help="character name as the launcher renders it")
    parser.add_argument("--check", action="store_true",
                        help="report the state and change nothing")
    parser.add_argument("--timeout", type=int, default=DEFAULT_LOGIN_TIMEOUT,
                        help="seconds to wait for the character to be in the "
                             "world (default %(default)s)")
    args = parser.parse_args()

    current = client_character()
    if current and current.lower() == args.character.strip().lower():
        print("already running as %r" % current)
        return 0
    if current:
        print("the client is running as %r, not %r. Not touching it -- "
              "quitting a live client can strand a ship in space."
              % (current, args.character), file=sys.stderr)
        return 3
    if client_is_running():
        print("a client process exists with no 'EVE - <character>' window yet; "
              "it is loading or at character select. Waiting rather than "
              "launching a second one.", file=sys.stderr)
        if args.check:
            return 2
        try:
            print("now running as %r" % wait_for_character(args.character,
                                                           args.timeout))
            return 0
        except LaunchError as error:
            print(str(error), file=sys.stderr)
            return 1

    if args.check:
        print("the client is not running", file=sys.stderr)
        return 2

    try:
        print("now running as %r" % launch(args.character, args.timeout))
        return 0
    except LaunchError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
