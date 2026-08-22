#!/usr/bin/env python3
"""macOS-native drop-in replacement for BotLab.exe.

Fetches an Elm bot's source (a GitHub URL or a local file/directory path),
compiles it with a thin `Main.elm` port wrapper (see Main.elm in this
directory) so it runs as an ordinary `elm make`-compiled program instead of
needing BotLab.exe's own Pine-based toolchain, and drives it against a live
EVE Online client, emulating the rest of BotLab.exe's host interface
(`BotLab.BotInterface_To_Host_2024_10_19`) and the memory-reading "volatile
process" sub-protocol (`EveOnline.VolatileProcessInterface`) using this
project's own macOS memory-reading tools (`re_helper.py`, `live_reader`,
`window_probe`) instead of the Windows-only C# volatile process.

See CLAUDE.md for the full protocol writeup this implements against.
"""
import argparse
import collections
import json
import os
import random
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time

# Both of these are needed only by paths that do not run on Windows -- PIL by
# the screenshot capture, re_helper by the dump-and-repr-scan root search -- and
# both are macOS-side dependencies. Failing to import them must not stop a
# Windows host that never reaches either. Left as a hard import on macOS, where
# an absent PIL or re_helper is a broken install and should say so at startup
# rather than thousands of readings later.
if sys.platform == "win32":
    try:
        from PIL import Image
    except ImportError:
        Image = None
else:
    from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "re_helper"))
if sys.platform == "win32":
    try:
        import re_helper as rh  # noqa: E402
    except Exception:
        rh = None
else:
    import re_helper as rh  # noqa: E402

sys.path.insert(0, MACOS_HOST_DIR)
import web_console  # noqa: E402
# Imported, not shelled out to: a subprocess would report failure as an exit
# code with the reason on a stdout somebody has to parse, and the one thing
# SetAutopilotDestinationRequest has to get right is telling success from
# failure. In-process, a failure is an EsiError with a message.
import esi_waypoint  # noqa: E402

# How long a key is held between its KeyDown and KeyUp. Long enough that the
# client registers the press, and well under macOS's minimum "delay until
# repeat" (~250ms) so the key never starts auto-repeating.
KEY_HOLD_SECONDS = 0.03

# The most a bot may push its own session end back, however much it asks for.
#
# The deadline stays the host's to enforce -- see the loop's own comment -- and
# the point of this cap is that handing a bound to the thing being bounded is
# only safe if the handing-over is itself bounded. 600s is above every allowance
# the mission runner can currently ask for (the largest is a home-station trip
# plus its restock grace, 480s) and far below anything that would let a looping
# bot run on unnoticed.
MAX_BOT_REQUESTED_OVERRUN_SECONDS = 600.0

# What the bot writes in its status text to ask for the extension. Chosen so it
# cannot occur by accident in a field that otherwise carries free prose and
# mission names -- see Bot.elm's `hostDirectivePrefix`, which must match.
BOT_DIRECTIVE_EXTEND_SESSION = re.compile(r"@host extend-session (\d+)")


def bot_requested_overrun_seconds(status_text):
    """How far past the planned end this bot says it still needs, in seconds.

    Read fresh from every tick's status text, so it is a lease the bot renews
    rather than a setting it latches: a bot that stops asking is stopped on the
    next tick, and one that has crashed or hung asks for nothing at all.

    Capped here rather than trusted, and clamped at zero so a negative or absurd
    number cannot extend anything.
    """
    if not status_text:
        return 0.0
    match = BOT_DIRECTIVE_EXTEND_SESSION.search(status_text)
    if match is None:
        return 0.0
    try:
        requested = float(match.group(1))
    except ValueError:
        return 0.0
    return max(0.0, min(requested, MAX_BOT_REQUESTED_OVERRUN_SECONDS))


# What the bot writes in its status text to ask for a route. Same channel and
# same prefix as the extension above -- see Bot.elm's `hostDirectiveSetDestination`,
# which must match. The argument runs to the end of the line because a station
# name contains spaces, parentheses and hyphens: `Amarr VIII (Oris) - Emperor
# Family Academy`. That is exactly the name the bot cannot type, which is what
# this directive exists for.
BOT_DIRECTIVE_SET_DESTINATION = re.compile(r"@host set-destination (.+)")


def bot_requested_destination(status_text):
    """The station the bot is asking to have set as its autopilot destination.

    `None` when it is not asking, which is every ordinary reading. Read fresh
    from every tick's status text like the extension above, so it is what the
    bot wants *now* rather than something latched -- a bot that stops asking is
    a bot the host stops acting for.

    Only a name comes back out of here. The refresh token that authorises the
    call lives in the Keychain and never enters this string; nothing read from
    a status text is ever treated as a credential, and nothing token-shaped is
    ever written into one -- the whole field is echoed to the log on every
    reading by `log_decision`.
    """
    if not status_text:
        return None
    match = BOT_DIRECTIVE_SET_DESTINATION.search(status_text)
    if match is None:
        return None
    name = match.group(1).strip()
    return name or None


MAIN_ELM_TEMPLATE = os.path.join(HERE, "Main.elm")
# A bot's own source fixes which host interface it imports, and the wrappers are
# not interchangeable -- see Main_2023_02_06.elm's header.
MAIN_ELM_TEMPLATE_BY_INTERFACE = {
    "BotLab.BotInterface_To_Host_2024_10_19": MAIN_ELM_TEMPLATE,
    "BotLab.BotInterface_To_Host_2023_02_06": os.path.join(HERE, "Main_2023_02_06.elm"),
}
DRIVER_JS = os.path.join(HERE, "driver.js")
MEMORY_SAMPLE_BIN = os.path.join(MACOS_HOST_DIR, "memory_sample", "memory_sample")
WINDOW_PROBE_BIN = os.path.join(MACOS_HOST_DIR, "window_probe", "window_probe")
CG_INPUT_BIN = os.path.join(MACOS_HOST_DIR, "cg_input", "cg_input")
TREE_WALKER_BIN = os.path.join(MACOS_HOST_DIR, "tree_walker", "tree_walker")

# Windows as a secondary target (issue #176). macOS stays primary: every
# platform-bound function below keeps its existing body untouched and gains one
# guarded early return in front of it, so on macOS this file is the code it was
# with one boolean test added. Nothing is refactored into a shared layer -- see
# the issue, which asks for the boundary to be drawn cleanly and for the merge
# not to be attempted now.
IS_WINDOWS = sys.platform == "win32"
win_platform = None
if IS_WINDOWS:
    _WINDOWS_HOST_DIR = os.path.join(os.path.dirname(MACOS_HOST_DIR), "windows-host")
    if _WINDOWS_HOST_DIR not in sys.path:
        sys.path.insert(0, _WINDOWS_HOST_DIR)
    import win_platform  # noqa: E402

    # The other half of the same problem as the driver pipe below. This host
    # prints the bot's own status text -- mission names, chat, context-menu
    # entries -- to stderr on every reading, and a Windows console defaults to
    # cp1252, which raises on any character it has no place for. Left as
    # `errors="replace"` rather than strict: a log line is diagnostic, and losing
    # a run three hours in because a rat's name had an accent in it would be a
    # far worse trade than one mangled character in a log.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

# Live-verified via the new per-decision logging (2026-07-28 saxrat run): a
# context-menu entry click dispatched immediately after the mouse glide that
# arrived on it can fail to register with the game at all -- the menu just
# sits open, unclicked, and the bot re-decides the identical click on the
# next tick. Two such real clicks landed 3+ seconds apart before the bot
# gave up and fell back to discard-and-reopen, which is the actual source
# of the "takes several tries to click a menu entry" delay this was added
# to diagnose -- not the decision logic, which was confirmed (via the
# clicked entry's own literal text now being logged) to target the right
# entry every time. Matches the same class of finding already established
# for drag gestures and hover-triggered flyouts elsewhere in this file:
# Photon UI seems to need a real settle interval after the cursor arrives
# somewhere new before it'll honor an action there. Applied only when the
# preceding step was an actual glide to a new position (see call site) --
# clicking again at a position the cursor was already resting on shouldn't
# need it. Starting value, not yet independently A/B-tested the way the
# glide steps/step_delay were -- tune from a live run if clicks still miss.
CLICK_SETTLE_DELAY_SECONDS = 0.15

# What a glide's own pacing spends sleeping, so a caller can back that out of
# a measured duration and be left with what the posting itself cost. Matches
# `_glide_to`'s shape exactly -- see there -- and is not read from `_glide_to`
# at runtime, because the whole point is a figure that does not move if the
# pacing is retuned without this comment being read.
GLIDE_STEPS = 10
GLIDE_STEP_DELAY_SECONDS = 0.025


def glide_per_event_cost_ms(duration_seconds, steps=GLIDE_STEPS,
                             step_delay=GLIDE_STEP_DELAY_SECONDS):
    """What one posted event cost, backed out of a whole glide's duration.

    Issue #163: a glide is `steps` posted `move` commands with a sleep of
    `step_delay` between every pair but the last -- `(steps - 1)` sleeps in
    all -- so its own logged duration is a measurement of what one posted
    event cost, not just of how long the gesture took. Subtracting the known,
    deliberate sleep time and dividing by the event count is the whole of the
    derivation; there is nothing to calibrate and nothing OS- or app-specific
    in it. Runs 17 and 19 lost `Emperor Family Bureau`/`Academy` to a search
    bar while every other recorded run typed the same shape of query cleanly,
    and reading their glides this way is what told the two apart: 53-100ms a
    posted event against under 18ms everywhere else, on the same shipped
    pacing.

    A single homogeneous quantity, deliberately not generalised to a whole
    `WindowsInputRequest`: a request mixes moves, clicks, keys and waits of
    different intrinsic costs, and blending them would need a weight for each
    that nothing here has measured. A glide is the one shape in this host
    that posts the same kind of event a fixed number of times with a fixed,
    known amount of sleep between them, which is what makes the arithmetic
    honest.
    """
    known_sleep_seconds = max(steps - 1, 0) * step_delay
    posted_events = max(steps, 1)
    return (duration_seconds - known_sleep_seconds) / posted_events * 1000.0


# Where the corpus draws the line between a healthy posting path and a
# saturated one. Recomputed from every glide in ~/eve-bot-logs (79 recorded
# runs at the time of writing, not just the two #75 was filed on): every
# healthy-looking run's *worst* glide backs out to under 18ms a posted event,
# and every run showing the saturated pattern -- which by now is a large
# share of the corpus, not only runs 17 and 19 -- has its *best* glide at
# 72ms or more. Nothing recorded falls between those two figures. 30ms sits
# in that gap: comfortably above the noisiest healthy reading and comfortably
# below the calmest saturated one, so a machine drifting slower over time
# would have room to be noticed before this fires on ordinary jitter.
INPUT_COST_SATURATED_MS = 30.0


def describe_input_cost(cost_ms, threshold_ms=INPUT_COST_SATURATED_MS):
    """What this step's posted events cost, in one line for the log.

    Reports only -- see #163's own framing, the same posture as #123's quick
    message and #139's retreat latency: name the number, decide nothing on
    it. `cost_ms` is `None` whenever the step posted no glide to measure,
    which must not print as fast -- a step that moved the mouse in one jump,
    or posted no move at all, says nothing about whether the window server is
    keeping up, and reporting it as healthy would be worse than saying
    nothing.
    """
    if cost_ms is None:
        return ("input cost: no glide posted this step, so there is nothing "
                "to measure -- not read as fast.")
    if cost_ms >= threshold_ms:
        return (f"INPUT COST HIGH: {cost_ms:.1f}ms for the last posted "
                f"event (glide), at or above the {threshold_ms:.0f}ms mark "
                f"the recorded runs separate on -- the window server may be "
                f"saturated and a posted event may be getting dropped "
                f"(#163). Report only; nothing here changes what the bot "
                f"does.")
    return (f"input cost: {cost_ms:.1f}ms for the last posted event "
            f"(glide), under the {threshold_ms:.0f}ms mark.")


class TreeWalkerClient:
    """Client for tree_walker, the native (C) in-process UI-tree walker
    that replaces re_helper.py's build_tree for the hot ReadFromWindow
    path -- see CLAUDE.md for why: profiling showed the Python
    implementation had become genuinely CPU-bound on CPython interpreter
    overhead (millions of small operations for one tree read) once
    round-trip count and data volume were no longer the bottleneck.
    tree_walker does the entire memory-read + struct-decode + tree
    assembly in one attached C process with zero pipe protocol for
    individual fields -- ~5x faster in practice (measured: ~2.0s Python
    vs ~0.4s C for the same ~2800-node live tree).

    Its page cache is what keeps that true as trees grew: uncached, a walk
    is syscall-bound and costs ~0.5ms per node, which put a real in-mission
    read at ~1.8s. Measured in-host after the cache: ~0.44s."""

    def __init__(self, pid):
        self.proc = subprocess.Popen(
            [TREE_WALKER_BIN, str(pid)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ready = self.proc.stderr.readline()
        if b"ready" not in ready:
            err = ready + self.proc.stderr.read()
            raise RuntimeError(f"tree_walker failed to start: {err!r}")

    def tree(self, root_addr, metatype_addr, str_type_addr, max_depth=16, max_nodes=5000):
        req = struct.pack("<QQQII", root_addr, metatype_addr, str_type_addr, max_depth, max_nodes)
        self.proc.stdin.write(req)
        self.proc.stdin.flush()
        len_b = self.proc.stdout.read(8)
        if len(len_b) < 8:
            raise RuntimeError("tree_walker: short read on response length (process died?)")
        (length,) = struct.unpack("<Q", len_b)
        data = bytearray()
        while len(data) < length:
            chunk = self.proc.stdout.read(length - len(data))
            if not chunk:
                raise RuntimeError("tree_walker: short read on response body")
            data.extend(chunk)
        return json.loads(data)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# Windows virtual-key code -> macOS CGKeyCode (see
# Common/EffectOnWindow.elm's vkey_* definitions for the Windows side,
# https://docs.microsoft.com/en-us/windows/desktop/inputdev/virtual-key-codes;
# macOS side is the standard US-layout kVK_* constants from
# HIToolbox/Events.h). Neither side is contiguous/matching the other for
# letters or digits, so this has to be an explicit table, not arithmetic.
# ---------------------------------------------------------------------------

# How recently a person must have used the mouse or keyboard for the bot to keep
# its hands off. Long enough to cover the pause between a human's own clicks,
# short enough that the bot resumes on its own without being told to.
HUMAN_INPUT_STAND_DOWN_SECONDS = 5.0


_VK_TO_CGKEYCODE = {
    0x08: 0x33,  # BACK -> Delete (backspace)
    0x09: 0x30,  # TAB
    0x0D: 0x24,  # RETURN
    0x10: 0x38,  # SHIFT
    0x11: 0x3B,  # CONTROL
    0x12: 0x3A,  # ALT/MENU -> Option
    0x5B: 0x37,  # LWIN -> Command. The editing shortcuts a macOS text field
                 # answers to are Command-based; Control+A is "move to start of
                 # line" here, not "select all".
    0x1B: 0x35,  # ESCAPE
    0x20: 0x31,  # SPACE
    0x21: 0x74,  # PRIOR -> PageUp
    0x22: 0x79,  # NEXT -> PageDown
    0x23: 0x77,  # END
    0x24: 0x73,  # HOME
    0x25: 0x7B,  # LEFT
    0x26: 0x7E,  # UP
    0x27: 0x7C,  # RIGHT
    0x28: 0x7D,  # DOWN
    0x2E: 0x75,  # DELETE -> ForwardDelete
    0x30: 0x1D, 0x31: 0x12, 0x32: 0x13, 0x33: 0x14, 0x34: 0x15,  # '0'-'4'
    0x35: 0x17, 0x36: 0x16, 0x37: 0x1A, 0x38: 0x1C, 0x39: 0x19,  # '5'-'9'
    0x41: 0x00, 0x42: 0x0B, 0x43: 0x08, 0x44: 0x02, 0x45: 0x0E,  # A-E
    0x46: 0x03, 0x47: 0x05, 0x48: 0x04, 0x49: 0x22, 0x4A: 0x26,  # F-J
    0x4B: 0x28, 0x4C: 0x25, 0x4D: 0x2E, 0x4E: 0x2D, 0x4F: 0x1F,  # K-O
    0x50: 0x23, 0x51: 0x0C, 0x52: 0x0F, 0x53: 0x01, 0x54: 0x11,  # P-T
    0x55: 0x20, 0x56: 0x09, 0x57: 0x0D, 0x58: 0x07, 0x59: 0x10,  # U-Y
    0x5A: 0x06,  # Z
    0x70: 0x7A, 0x71: 0x78, 0x72: 0x63, 0x73: 0x76, 0x74: 0x60,  # F1-F5
    0x75: 0x61, 0x76: 0x62, 0x77: 0x64, 0x78: 0x65, 0x79: 0x6D,  # F6-F10
    0x7A: 0x67, 0x7B: 0x6F,  # F11-F12
    0xBA: 0x29,  # OEM_1 ';'
    0xBB: 0x18,  # OEM_PLUS '='
    0xBC: 0x2B,  # OEM_COMMA ','
    0xBD: 0x1B,  # OEM_MINUS '-'
    0xBE: 0x2F,  # OEM_PERIOD '.'
    0xBF: 0x2C,  # OEM_2 '/'
    0xC0: 0x32,  # OEM_3 '`'
    0xDB: 0x21,  # OEM_4 '['
    0xDC: 0x2A,  # OEM_5 '\'
    0xDD: 0x1E,  # OEM_6 ']'
    0xDE: 0x27,  # OEM_7 '''
}


def vk_to_cgkeycode(vk):
    # On Windows the bot's own vkey_* values are already the target's key codes,
    # so there is no table and nothing to be missing from one.
    if IS_WINDOWS:
        return win_platform.vk_to_keycode(vk)
    return _VK_TO_CGKEYCODE.get(vk)


def keys_left_held(items):
    """The macOS key codes a WindowsInputSequenceItem list leaves pressed.

    An unbalanced sequence is not hypothetical. `Common.EffectOnWindow`'s
    `effectsToEnterString` folds the string it is given while tracking whether
    Shift is down, and emits a `KeyUp vkey_SHIFT` only when the *next* character
    does not want Shift -- so a string ending in a capital reaches the end of
    the fold with Shift down and nothing after it, and the host is handed a
    press with no release. `getKeyboardKeyToEnterChar` could reach the same
    state with `[`, which it mapped to `vkey_LWIN` and which this host maps on
    to Command.

    What a key left down costs is at the far end and is already recorded:
    `Bot.elm` notes that Command "does not select, and it leaves the field
    swallowing every keystroke that follows", which run 116 paid for by typing
    128 times and changing the box by not one character. A modifier held
    underneath ordinary typing loses characters without any layer reporting a
    failure -- every KeyDown is posted, every KeyUp is posted, and the client
    reads a shortcut rather than text.

    Pure, and separate from `_keys_down`, because the two answer different
    questions: this one says the *bot's sequence* was unbalanced, where
    `_keys_down` says what this host actually posted and therefore also covers
    a sequence cut short by an abort or by a `cg_input` that died mid-run.
    """
    held = []
    for item in items:
        (tag, payload), = item.items()
        if tag not in ("KeyDown", "KeyUp"):
            continue
        mac_code = vk_to_cgkeycode(payload[0])
        if mac_code is None:
            continue
        if tag == "KeyDown":
            if mac_code not in held:
                held.append(mac_code)
        elif mac_code in held:
            held.remove(mac_code)
    return held


def vk_to_mouse_button(vk):
    """VK_LBUTTON=0x01, VK_RBUTTON=0x02, VK_MBUTTON=0x04 -> cg_input's
    0=left/1=right/2=other."""
    if vk == 0x02:
        return 1
    if vk == 0x04:
        return 2
    return 0


MOUSE_BUTTON_VK_CODES = (0x01, 0x02, 0x04)


def _effect_sequence_of_request(request_str):
    """The EffectSequenceOnWindow body of a volatile-process request, or None.

    Only bots on the 2023_02_06 host interface send these; on 2024_10_19 the
    same input arrives as a WindowsInputRequest task instead.
    """
    try:
        req = json.loads(request_str)
    except (ValueError, TypeError):
        return None
    if isinstance(req, dict):
        return req.get("EffectSequenceOnWindow")
    return None


def _effect_sequence_as_input_items(sequence):
    """EffectSequenceOnWindow -> the item list _windows_input executes.

    Translating rather than executing directly is what keeps the two host
    interfaces on one input path: everything _windows_input has learned about
    this client -- eased movement, the double-click collapse, not pausing
    mid-drag, standing down for a human at the keyboard -- applies unchanged.

    The 2023 vocabulary is narrower: mouse buttons are KeyDown/KeyUp carrying a
    mouse virtual-key code rather than their own ButtonDown/ButtonUp, and there
    is no scroll, no relative move and no raw character input.
    """
    items = []
    window_id = sequence.get("windowId")
    if sequence.get("bringWindowToForeground") and window_id is not None:
        items.append({"BringWindowToForeground": str(window_id)})

    for element in sequence.get("task") or []:
        if "delayMilliseconds" in element:
            items.append({"WaitMilliseconds": element["delayMilliseconds"]})
            continue
        effect = element.get("effect")
        if not effect:
            continue
        (tag, payload), = effect.items()
        if tag == "MouseMoveTo":
            location = payload["location"]
            items.append({"MouseMoveAbsolute": [location["x"], location["y"]]})
        elif tag in ("KeyDown", "KeyUp"):
            code = payload["virtualKeyCode"]
            if code in MOUSE_BUTTON_VK_CODES:
                items.append({"ButtonDown" if tag == "KeyDown" else "ButtonUp": code})
            else:
                items.append({tag: [code, False]})
    return items


# ---------------------------------------------------------------------------
# Bot source acquisition
# ---------------------------------------------------------------------------

def parse_github_url(url):
    """Handles plain repo URLs and github.com/.../tree/<branch>/<subpath>
    URLs (an app can live in a subdirectory of a larger repo, like this
    one: implement/applications/eve-online/...)."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+?)(\.git)?/?$", url)
    if m:
        return f"https://github.com/{m.group(1)}/{m.group(2)}.git", None, None
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.+)$", url)
    if m:
        owner, repo, branch, subpath = m.groups()
        return f"https://github.com/{owner}/{repo}.git", subpath, branch
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$", url)
    if m:
        owner, repo, branch, subpath = m.groups()
        subpath = os.path.dirname(subpath)
        return f"https://github.com/{owner}/{repo}.git", subpath or None, branch
    raise ValueError(f"could not parse as a GitHub URL: {url}")


def find_bot_elm_dir(base):
    if os.path.isfile(os.path.join(base, "Bot.elm")):
        return base
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in (".git", "elm-stuff")]
        if "Bot.elm" in files:
            return root
    return None


def fetch_bot_source(url_or_path, workdir):
    """Returns the local directory containing Bot.elm (and its sibling
    framework files + elm.json)."""
    if url_or_path.startswith("https://github.com/") or url_or_path.startswith("git@"):
        repo_url, subpath, branch = parse_github_url(url_or_path)
        clone_dir = os.path.join(workdir, "clone")
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd += ["--branch", branch]
        cmd += [repo_url, clone_dir]
        print(f"# {' '.join(cmd)}", file=sys.stderr)
        subprocess.run(cmd, check=True)
        base = os.path.join(clone_dir, subpath) if subpath else clone_dir
    else:
        p = url_or_path
        if p.startswith("file://"):
            p = p[len("file://"):]
        base = os.path.abspath(p)

    bot_dir = find_bot_elm_dir(base)
    if bot_dir is None:
        raise RuntimeError(f"could not find Bot.elm under {base}")
    return bot_dir


# ---------------------------------------------------------------------------
# What the bot was built from
# ---------------------------------------------------------------------------

# A version stamp runs once, at launch, in front of everything else. A git that
# hangs -- an index lock held by another process, a filesystem that has gone
# away -- would hold the launch with it, so every call is bounded.
BOT_VERSION_GIT_TIMEOUT_SECONDS = 5.0

# git could not answer at all: not installed, could not be started, or it ran
# past its timeout. Distinct from `None`, which is git running and saying no --
# the difference between "there is no answer to be had here" and "the answer is
# that this is not a checkout", and only the second is a fact about the source.
GIT_UNAVAILABLE = object()


def _git(cwd, *args):
    """Run git in `cwd` and return its stdout, or `None`/`GIT_UNAVAILABLE`.

    Never raises. Nothing about identifying the source is worth failing a
    launch for, and a stamp that cannot be computed is a stamp that says
    "unknown" -- see `bot_source_version`.
    """
    try:
        done = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                              timeout=BOT_VERSION_GIT_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return GIT_UNAVAILABLE
    if done.returncode != 0:
        return None
    return done.stdout


def bot_source_version(bot_dir):
    """What this bot was built from, as far as this machine can actually prove.

    A bare `git rev-parse HEAD` is the wrong answer here, and it is the wrong
    answer in the direction that looks authoritative, so the stamp carries two
    qualifications beside the commit:

      - **The tree, not the commit, is what gets compiled.** `prepare_build_dir`
        copies `bot_dir` as it stands and `elm make` builds that copy, so a
        short SHA printed beside modified sources describes something that was
        never run. Judged over `bot_dir` itself rather than the whole repository
        -- that directory is what is copied, so an edit to the host or to a test
        elsewhere in the same checkout changes nothing about what this bot
        compiled -- and untracked files count, because the copy takes them too.

      - **The commit may exist nowhere but here.** Run 29 flew `776a202`, a
        local revert that was never pushed, and a reader handed that SHA cannot
        resolve it against anything. Reachability is asked of the remote-tracking
        refs this machine holds (`git branch --remotes --contains`), which is a
        local question with no network in it; a fetch that has not happened can
        make a pushed commit read as LOCAL-ONLY, which is the direction that
        understates rather than overstates what a reader can go and look at.

    Anything that cannot be established says so. A source that is not a git
    checkout at all is a supported case -- `fetch_bot_source` takes a plain
    directory -- and it degrades to a stated "unknown" rather than to a blank, a
    crash, or a commit-shaped string nobody can resolve.
    """
    try:
        return _bot_source_version(bot_dir)
    except Exception as exc:  # noqa: BLE001 -- a version must not fail a launch
        return f"unknown (version could not be computed: {exc})"


def _bot_source_version(bot_dir):
    head = _git(bot_dir, "rev-parse", "--short", "HEAD")
    if head is GIT_UNAVAILABLE:
        return "unknown (git could not be run)"
    if head is None or not head.strip():
        return "unknown (not a git checkout)"
    commit = head.strip()

    # `.` rather than the absolute path: git resolves its work tree through
    # symlinks (`/var` is `/private/var` on macOS) and an absolute pathspec that
    # does not match the resolved form is rejected as outside the repository,
    # which would read as "dirtiness unknown" for every run.
    status = _git(bot_dir, "status", "--porcelain", "--", ".")
    if status is GIT_UNAVAILABLE or status is None:
        tree = "dirtiness unknown"
    elif status.strip():
        tree = "DIRTY"
    else:
        tree = "clean"

    on_remote = _git(bot_dir, "branch", "--remotes", "--contains", commit)
    if on_remote is GIT_UNAVAILABLE or on_remote is None:
        where = "remote reachability unknown"
    elif on_remote.strip():
        where = "on a remote-tracking branch"
    else:
        where = "LOCAL-ONLY"

    return f"{commit} ({tree}, {where})"


# ---------------------------------------------------------------------------
# Build: patch elm.json, add Main.elm, compile
# ---------------------------------------------------------------------------

def installed_elm_version():
    out = subprocess.run(["elm", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def host_interface_of_bot(bot_dir):
    """Which BotLab.BotInterface_To_Host_* module the bot's own Bot.elm imports.

    Read from Bot.elm rather than from which interface modules the app happens
    to vendor: the mining bot ships both 2023_01_17 and 2023_02_06, and only the
    import says which one its botMain is actually typed against.
    """
    bot_elm = os.path.join(bot_dir, "Bot.elm")
    # Encoding stated rather than defaulted. Python's default is the locale's,
    # which on Windows is cp1252, and a `Bot.elm` carrying any byte outside it
    # raises `UnicodeDecodeError` before the bot can start at all -- which is
    # how `eve-online-warp-to-0-autopilot` refused to launch on this machine
    # while running fine on macOS, where the default is already UTF-8. `errors`
    # is deliberate too: this only ever reads the import line, so a byte it
    # cannot decode must not stop the launch.
    with open(bot_elm, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = re.match(r"\s*import\s+(BotLab\.BotInterface_To_Host_\w+)", line)
            if m:
                return m.group(1)
    return None


def prepare_build_dir(bot_dir, workdir):
    build_dir = os.path.join(workdir, "build")
    shutil.copytree(bot_dir, build_dir)

    elm_json_path = os.path.join(build_dir, "elm.json")
    # UTF-8 stated for the same reason as `host_interface_of_bot` above:
    # the default is the locale's, cp1252 on Windows, and this file is both
    # read and rewritten -- so a defaulted encoding can corrupt on the way
    # out as well as raise on the way in.
    with open(elm_json_path, encoding="utf-8") as f:
        elm_json = json.load(f)
    real_version = installed_elm_version()
    if elm_json.get("elm-version") != real_version:
        print(f"# patching elm.json elm-version {elm_json.get('elm-version')!r} -> {real_version!r}", file=sys.stderr)
        elm_json["elm-version"] = real_version
        with open(elm_json_path, "w", encoding="utf-8") as f:
            json.dump(elm_json, f, indent=4)

    interface = host_interface_of_bot(build_dir)
    template = MAIN_ELM_TEMPLATE_BY_INTERFACE.get(interface)
    if template is None:
        raise RuntimeError(
            f"no Main.elm wrapper for host interface {interface!r} "
            f"(have: {', '.join(sorted(MAIN_ELM_TEMPLATE_BY_INTERFACE))})"
        )
    print(f"# host interface {interface} -> {os.path.basename(template)}", file=sys.stderr)
    shutil.copy(template, os.path.join(build_dir, "Main.elm"))
    return build_dir


def compile_bot(build_dir):
    out_js = os.path.join(build_dir, "bot.js")
    cmd = ["elm", "make", "Main.elm", f"--output={out_js}"]
    print(f"# {' '.join(cmd)} (cwd={build_dir})", file=sys.stderr)
    result = subprocess.run(cmd, cwd=build_dir, capture_output=True, text=True)
    print(result.stdout, file=sys.stderr)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError("elm make failed")
    return out_js


# ---------------------------------------------------------------------------
# macOS process/window discovery (ListGameClientProcessesRequest)
# ---------------------------------------------------------------------------

WINDOW_LINE_RE = re.compile(
    r'window=(\d+) owner_pid=(\d+) layer=(-?\d+) owner="[^"]*" name="([^"]*)" '
    r'bounds=\{x=([\d.-]+) y=([\d.-]+) w=([\d.-]+) h=([\d.-]+)\}\(points\) '
    r'display=\d+ backing_scale=([\d.]+)'
)


def _windows_for(pid):
    """--all so this works regardless of which macOS Space the window is
    on (a fullscreen game window is invisible to on-screen-only queries
    unless that Space happens to be the active one -- see CLAUDE.md)."""
    r = subprocess.run([WINDOW_PROBE_BIN, str(pid), "--all"], capture_output=True, text=True)
    rows = []
    for line in r.stdout.splitlines():
        m = WINDOW_LINE_RE.match(line)
        if m:
            rows.append({
                "window": int(m.group(1)), "layer": int(m.group(3)), "name": m.group(4),
                "x": float(m.group(5)), "y": float(m.group(6)), "w": float(m.group(7)), "h": float(m.group(8)),
                "backing_scale": float(m.group(9)),
            })
    return rows


def find_eve_processes():
    """Returns [{"processId": int, "mainWindowId": str, "mainWindowTitle":
    str, "mainWindowZIndex": int}, ...] -- matches
    VolatileProcessInterface.GameClientProcessSummaryStruct. The
    memory-reading target (com.ccpgames.eveonline / exefile) and the
    on-screen window can be a different pid (launcher, windowed mode) or
    the same pid (fullscreen, see CLAUDE.md); this returns the memory pid
    with whichever window we can find for it, checking both possible
    owners. Picks the largest layer>=0 window by area (a fullscreen game
    window can have smaller overlay windows -- e.g. the reveal-on-hover
    menu bar strip -- that would otherwise be picked by accident)."""
    if IS_WINDOWS:
        return win_platform.find_eve_processes()
    out = subprocess.run(["lsappinfo", "list"], capture_output=True, text=True, check=True)
    text = out.stdout
    game_pid = None
    launcher_pid = None
    for m in re.finditer(r'bundleID="([^"]+)"[^\x00]*?pid = (\d+)', text):
        bundle, pid = m.group(1), int(m.group(2))
        if bundle == "com.ccpgames.eveonline":
            game_pid = pid
        elif bundle == "com.ccpgames.eve-online-launcher":
            launcher_pid = pid
    if game_pid is None:
        return []

    windows = [w for w in _windows_for(game_pid) if w["layer"] >= 0]
    if not windows and launcher_pid:
        windows = [w for w in _windows_for(launcher_pid) if w["layer"] >= 0]
    if not windows:
        return []
    best = max(windows, key=lambda w: w["w"] * w["h"])
    return [{
        "processId": game_pid,
        "mainWindowId": str(best["window"]),
        "mainWindowTitle": best["name"] or "EVE",
        "mainWindowZIndex": 0,
    }]


def get_window_rect(window_number):
    """{"left","top","right","bottom","backing_scale"}, rect in points,
    for a window number already known (from find_eve_processes'
    mainWindowId), regardless of active Space."""
    if IS_WINDOWS:
        return win_platform.get_window_rect(window_number)
    r = subprocess.run([WINDOW_PROBE_BIN, "--all"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        m = WINDOW_LINE_RE.match(line)
        if m and int(m.group(1)) == window_number:
            x, y, w, h = float(m.group(5)), float(m.group(6)), float(m.group(7)), float(m.group(8))
            return {
                "left": int(x), "top": int(y), "right": int(x + w), "bottom": int(y + h),
                "backing_scale": float(m.group(9)),
            }
    return None


def pack_rgb_int(im):
    """Pack a Pillow RGB image into a flat, row-major list of 0x00RRGGBB
    ints -- the exact format ImageCrop.pixelsString decodes (see
    colorFromInt_R8G8B8 in BotFramework.elm: red<<16 | green<<8 | blue).
    Uses numpy if available (bit-parallel, ~instant even for a few
    million pixels); falls back to a pure-Python loop otherwise."""
    try:
        import numpy as np
        arr = np.asarray(im, dtype=np.uint32)
        packed = (arr[:, :, 0] << 16) | (arr[:, :, 1] << 8) | arr[:, :, 2]
        return packed.flatten().tolist()
    except ImportError:
        px = im.load()
        w, h = im.size
        return [((px[x, y][0] << 16) | (px[x, y][1] << 8) | px[x, y][2])
                for y in range(h) for x in range(w)]


def make_image_crop(im, offset_x, offset_y):
    """One ImageCrop-shaped dict: {"offset", "widthPixels", "pixelsString"}
    matching BotLab.BotInterface_To_Host_2024_10_19.ImageCrop -- height is
    implied by len(pixels)/widthPixels, there is no separate height field
    in the real interface."""
    w, _h = im.size
    pixels = pack_rgb_int(im.convert("RGB"))
    return {
        "offset": {"x": int(offset_x), "y": int(offset_y)},
        "widthPixels": w,
        "pixelsString": json.dumps(pixels),
    }


# The game's canvas does not always fill its window. Mirroring this Mac to an
# external display left the EVE window 1710x1068 points (3420x2136 device
# pixels) while UIRoot went on reporting a 3420x2079 canvas -- 57 pixels
# shorter, with the shortfall at the *top*. That position is measured, not
# assumed: a known info-panel icon the tree placed at canvas y=75 rendered at
# y=134 in a capture of the same window.
#
# Dividing the canvas size by the full window size, which is what this did
# unconditionally, absorbs that shortfall into scale_y -- 2079/1068 = 1.947
# where the truth is a clean 2.0. The resulting error is proportional to y, so
# it is nothing at the top of the window and ~28 points at the bottom, which is
# enough to land a click on the Neocom icon *next to* the intended one. Run 22
# opened Inventory, Wallet, Directional Scanner and Opportunities that way, and
# then could not switch the location info panel back on because the bot's own
# repair click missed the toggle by the same offset -- 116 times, silently,
# since a click that lands on nothing reports exactly like one that lands.
#
# So the canvas is modelled as "uniformly scaled, possibly inset within its
# window", with the old per-axis divide kept as the fallback. The inset model
# is only used when the OS backing scale explains one axis *exactly* -- that
# exact axis is what tells a genuinely uniform scale apart from two ratios that
# merely came out close -- and leaves the other short by no more than
# CANVAS_INSET_MAX_PIXELS. The game has its own UI-scale setting independent of
# the OS backing factor (ratios of 1.684 / 1.743 have been seen on this
# machine), and that case must keep the old behaviour: it is a genuinely
# non-square scale, not an inset.
CANVAS_INSET_MAX_PIXELS = 200


def calibrate_window_canvas(root_size, point_w, point_h, backing_scale):
    """Work out how the game's canvas sits inside its window.

    Returns (scale_x, scale_y, inset_x, inset_y, canvas_w, canvas_h). The
    scales and the insets are in "game pixel" units -- the units the bot's own
    coordinate arithmetic works in, see the note at the ReadFromWindowMethod
    call site. A non-zero inset means the canvas does not start at the window's
    top-left, and every screen coordinate handed to or taken from the bot has
    to carry it.
    """
    if not root_size:
        # First call, before any ReadFromWindow has populated root_display_size.
        # Without the canvas size there is nothing to compare, so assume it
        # fills the window -- which is what this has always done.
        s = backing_scale or 1.0
        return s, s, 0, 0, int(point_w * s), int(point_h * s)

    canvas_w, canvas_h = int(root_size[0]), int(root_size[1])
    s = backing_scale or 0.0
    if s > 0:
        short_x = point_w * s - canvas_w
        short_y = point_h * s - canvas_h
        one_axis_is_exact = abs(short_x) < 1.0 or abs(short_y) < 1.0
        both_shortfalls_are_small = (
            -1.0 < short_x <= CANVAS_INSET_MAX_PIXELS
            and -1.0 < short_y <= CANVAS_INSET_MAX_PIXELS
        )
        if one_axis_is_exact and both_shortfalls_are_small:
            return (s, s,
                    max(0, int(round(short_x))), max(0, int(round(short_y))),
                    canvas_w, canvas_h)

    return canvas_w / point_w, canvas_h / point_h, 0, 0, canvas_w, canvas_h


def window_canvas_geometry(rect, root_size):
    """The canvas rect in game pixels, with the scales and inset behind it.

    Returns (scaled_rect, scale_x, scale_y, (inset_x, inset_y)).

    This exists as one function rather than inline at the call site so the
    coordinate path can be tested as the *composition* it is. The bug it was
    written for lived in how the scale and the origin combine, not in either of
    them, and a test that restates this arithmetic instead of running it would
    have passed throughout.

    Note `right`/`bottom` are the canvas's own extent from its origin, which is
    identical to scaling the window's far corner whenever the canvas fills the
    window -- and correct rather than merely equal when it does not.
    """
    point_w = max(1, rect["right"] - rect["left"])
    point_h = max(1, rect["bottom"] - rect["top"])
    scale_x, scale_y, inset_x, inset_y, canvas_w, canvas_h = calibrate_window_canvas(
        root_size, point_w, point_h, rect["backing_scale"])
    # The canvas origin, not the window origin: the bot adds this to a UI
    # position that is measured from the canvas, so the inset belongs in that
    # sum rather than in a correction applied afterwards.
    left = int(rect["left"] * scale_x) + inset_x
    top = int(rect["top"] * scale_y) + inset_y
    scaled_rect = {
        "left": left, "top": top,
        "right": left + canvas_w, "bottom": top + canvas_h,
    }
    return scaled_rect, scale_x, scale_y, (inset_x, inset_y)


def capture_image_data(window_number, scaled_rect, scale_x, scale_y, canvas_inset=(0, 0)):
    """Real screenshotCrops_binned_2x2/_binned_4x4, captured via
    screencapture and resampled into the game's own coordinate space (see
    the scale_x/scale_y note above build_tree call site -- the game's
    internal UI coordinates are NOT the same as the OS's backing-pixel
    resolution, so the crop pixel array needs to be in "game pixel" units
    too, matching offset/clientRectLeftUpperToScreen, not raw device
    pixels). One crop per resolution, covering the whole window; both use
    PIL's BOX filter, which is a true area-average -- the correct
    operation for "pixel binning", not just a resize.

    screenshotCrops_original is deliberately left empty (valid per the
    type -- List ImageCrop): its pixel array at full window resolution
    packs to tens of MB of JSON per read cycle, and `EveOnline.BotFramework`
    never actually reads `pixels_1x1` (confirmed by grep -- the `screenshot`
    record it builds only has `pixels_1x1`/`pixels_2x2` fields, and no
    call site in this bot's source reads `pixels_1x1` at all). Paying
    that cost every cycle for data nothing consumes would reintroduce
    exactly the kind of per-cycle latency the earlier click-timing fix
    just removed. If a bot that genuinely needs full-resolution pixels
    shows up, this is the place to add it back."""
    if IS_WINDOWS:
        # Issue #176 step 5: the screenshot path is deliberately not ported --
        # it is diagnostic on macOS and it is the cost this whole port exists to
        # escape. The empty crop lists are what the framework is satisfied with.
        return win_platform.capture_image_data()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        subprocess.run(["screencapture", "-x", "-o", "-l", str(window_number), path],
                        capture_output=True, timeout=5)
        im = Image.open(path)
        im.load()
    except Exception as exc:
        print(f"# screenshot capture failed: {exc}", file=sys.stderr)
        return {"screenshotCrops_original": [], "screenshotCrops_binned_2x2": [], "screenshotCrops_binned_4x4": []}
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    game_w = max(1, scaled_rect["right"] - scaled_rect["left"])
    game_h = max(1, scaled_rect["bottom"] - scaled_rect["top"])

    inset_x, inset_y = canvas_inset
    if inset_x or inset_y:
        # The canvas is inset within the window (see calibrate_window_canvas),
        # and the capture covers the whole window. Cut the canvas out of it
        # first, or every crop handed to the bot is shifted by the inset while
        # its declared offset says otherwise. Under the inset model the scale
        # is the OS backing factor, so one game pixel is one captured pixel.
        im = im.crop((inset_x, inset_y, inset_x + game_w, inset_y + game_h))

    im_2x2 = im.resize((max(1, game_w // 2), max(1, game_h // 2)), Image.BOX)
    crop_2x2 = make_image_crop(im_2x2, scaled_rect["left"] // 2, scaled_rect["top"] // 2)
    im_4x4 = im.resize((max(1, game_w // 4), max(1, game_h // 4)), Image.BOX)
    crop_4x4 = make_image_crop(im_4x4, scaled_rect["left"] // 4, scaled_rect["top"] // 4)

    return {
        "screenshotCrops_original": [],
        "screenshotCrops_binned_2x2": [crop_2x2],
        "screenshotCrops_binned_4x4": [crop_4x4],
    }


def _window_is_onscreen(window_number):
    """On-screen-only query (not --all): true only if this window is
    actually visible on the *currently active* macOS Space right now --
    the thing --all deliberately ignores. Used to verify a foreground
    switch actually worked, and to gate every input action so nothing
    gets sent to whatever app happens to be active if focus drifted."""
    if IS_WINDOWS:
        return win_platform.window_is_onscreen(window_number)
    r = subprocess.run([WINDOW_PROBE_BIN], capture_output=True, text=True)
    return re.search(rf"^window={window_number}\b", r.stdout, re.MULTILINE) is not None


def bring_window_to_foreground(pid, window_number, retries=4, delay=0.35):
    """Reliably bring pid's window to the foreground *and* switch to its
    macOS Space if it's on a different one (a fullscreen app lives on its
    own dedicated Space), verifying the result instead of trusting a
    single osascript call blindly.

    Found by testing: 'set frontmost' via System Events is reliable when
    called every cycle as part of the bot's normal loop, but a Space
    switch doesn't always happen from a single call after focus has
    genuinely drifted elsewhere (e.g. the user alt-tabbed to check
    something else) -- see CLAUDE.md. Retries with a second activation
    path (`open -b <bundle id>`, a different code path than System
    Events) as a fallback, and only reports success once the window is
    actually confirmed on-screen.

    Fast path: the bot calls BringWindowToForeground at the start of
    *every* input sequence (BotFramework.elm always prepends it), so the
    overwhelmingly common case is "already in the foreground, nothing to
    do." Checking that first avoids an unconditional osascript call +
    delay-second sleep on every single click -- that was adding
    hundreds of ms of pure latency per action for no benefit, found by
    the user noticing real-world sluggishness between opening a menu and
    clicking it."""
    if IS_WINDOWS:
        return win_platform.bring_window_to_foreground(pid, window_number, retries, delay)
    if _window_is_onscreen(window_number):
        return True
    for _ in range(retries):
        subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to set frontmost of (first process whose unix id is {pid}) to true'],
            capture_output=True,
        )
        time.sleep(delay)
        if _window_is_onscreen(window_number):
            return True
        subprocess.run(["open", "-b", "com.ccpgames.eveonline"], capture_output=True)
        time.sleep(delay)
        if _window_is_onscreen(window_number):
            return True
    return False


# ---------------------------------------------------------------------------
# Volatile-process emulation: ListGameClientProcessesRequest /
# SearchUIRootAddress / ReadFromWindow, matching
# EveOnline.VolatileProcessInterface's JSON shapes exactly.
# ---------------------------------------------------------------------------

# The one node in a reading that was never read out of the client. The type
# name says so in full, because everything around it in this structure mirrors
# a real Python object in the game's memory and a later reader has no other way
# to tell -- see CLAUDE.md's architecture section.
SYNTHETIC_GAME_LOG_TYPE_NAME = "MacOsHostSyntheticGameLog"
SYNTHETIC_GAME_LOG_ENTRY_TYPE_NAME = "MacOsHostSyntheticGameLogEntry"
SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME = "MacOsHostSyntheticIncomingDamage"
SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME = "MacOsHostSyntheticOutgoingDamage"
SYNTHETIC_OUTGOING_DAMAGE_TARGET_TYPE_NAME = "MacOsHostSyntheticOutgoingDamageTarget"
SYNTHETIC_KILLS_TYPE_NAME = "MacOsHostSyntheticKills"


def synthetic_game_log_node(entries):
    """A UI-tree node carrying what the client said since the last reading.

    Three properties this shape has to hold, each of them load-bearing:

    **It has no display region.** No `_displayX`/`_displayY`/`_displayWidth`/
    `_displayHeight`, so `asUITreeNodeWithInheritedOffset` files it as a
    `ChildWithoutRegion` and every existing parser -- all of which navigate by
    display region -- cannot reach it. That is what makes attaching it to a real
    reading safe rather than merely untested.

    **The text is under `text`, never `_setText` or `_text`.** Those two are
    what `getDisplayText` reads, and `getAllContainedDisplayTexts` runs over the
    raw tree without any region filtering -- the mission runner asks it whether
    the whole reading contains "No room for more". A game log line landing in
    that answer would be a refusal dialog the client never showed.

    **The node exists even with nothing to report.** Its absence is the only way
    a bot can tell "this host does not provide the channel" (BotLab.exe, or
    `--no-game-log`) from "the client said nothing this reading", and inferring
    the second from the first is how a bot concludes a command was accepted
    because no refusal arrived.
    """
    return {
        "pythonObjectAddress": "macos-host-synthetic-game-log",
        "pythonObjectTypeName": SYNTHETIC_GAME_LOG_TYPE_NAME,
        "dictEntriesOfInterest": {},
        "children": [
            {
                "pythonObjectAddress": f"macos-host-synthetic-game-log-{index}",
                "pythonObjectTypeName": SYNTHETIC_GAME_LOG_ENTRY_TYPE_NAME,
                "dictEntriesOfInterest": {
                    "timestamp": entry["timestamp"],
                    "channel": entry["channel"],
                    "text": entry["text"],
                },
                "children": [],
            }
            for index, entry in enumerate(entries)
        ],
    }


def synthetic_incoming_damage_node(summary):
    """A UI-tree node carrying how hard the client says we are being hit.

    The same fiction as `synthetic_game_log_node`, with the same three
    properties -- no display region, nothing under `_setText`/`_text`, and a
    type name that says in full that the client never wrote this -- and it
    exists for one reason the game-log node cannot cover.

    `(combat)` is withheld from `gameLogEntriesSinceLastReading` and stays
    withheld: 134,641 of the recorded lines are combat, the peak measured is 54
    of them inside a single three-second reading, and none of them is a sentence
    a decision wants to read. What a decision wants is the *total*, and the
    total is one number. Summing it here rather than in Elm also puts the
    incoming/outgoing split in one place, next to the markup stripping that
    produced the line and covered by tests that run against the real recorded
    lines -- `N from X` is damage taken, `N to X` is damage dealt, and confusing
    the two would arm a retreat on the bot's own guns.

    **Present-with-zero and absent are different answers**, exactly as they are
    for the game log. The node is emitted on every reading a game log exists
    for, so `damage = 0` is "the client reported no incoming fire" and the
    node's absence is "this host does not carry the channel". A bot that read
    the second as the first would conclude it was safe because nothing was
    listening, which is this repo's signature failure.
    """
    entries = {
        "damage": summary["damage"],
        "hits": summary["hits"],
    }
    # Only when there was one: an attacker key on a reading with no incoming
    # fire would be a name the client did not say this reading.
    if summary["topAttacker"] is not None:
        entries["topAttacker"] = summary["topAttacker"]
    return {
        "pythonObjectAddress": "macos-host-synthetic-incoming-damage",
        "pythonObjectTypeName": SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME,
        "dictEntriesOfInterest": entries,
        "children": [],
    }


def synthetic_outgoing_damage_node(targets):
    """A UI-tree node carrying what this ship's shots have achieved, per target.

    The mirror of `synthetic_incoming_damage_node`, with the same four safety
    properties -- a type name that says in full that the client never wrote
    this, no display region, nothing under `_setText`/`_text`, and an absent
    node meaning something different from an empty one.

    Issue #90 is the consumer. Run 27 locked an `Infested Asteroid`, shot it
    with every gun for roughly 290 consecutive readings, and every one of those
    shots *landed* for exactly 0 damage while nine real rats sat on the same
    overview untouched. Nothing in a reading could say so: the incoming half was
    summed here for #32 and the outgoing half was matched nowhere, so no
    decision could ask how much damage this ship was dealing.

    The client distinguishes the three cases in the line itself, which is why
    this needs no health bar and no inference. A miss carries no damage number
    at all (`Your Hobgoblin II misses Vigilant Sentry Tower completely`), a
    landed shot reads `104 to Mammon Apis - Hits`, and a landed shot that
    achieved nothing reads `0 to Infested Asteroid - Hits`.

    **All three are carried, and the third is not the first.** Until issue #267
    a miss reached no field of any reading, so the bot could not tell an object
    it cannot hurt from one it cannot hit. Both now travel, in separate counts,
    because the corpus says they mean opposite things -- see
    `parse_outgoing_miss`.

    **Per target rather than one total**, unlike the incoming node, because the
    question is about one object. Guns and drones routinely engage different
    things in the same reading -- run 27's own log has the drones landing real
    damage on a `Mercenary Commander` in the very readings the guns were
    achieving nothing on the asteroid -- so a single sum would have read as
    "our damage is fine" throughout the incident this exists to catch. One child
    per target name, each carrying `name`, `hits`, `damage` and `misses`.

    **A target with `hits > 0` and `damage = 0` is the whole signal**, and it is
    still not a verdict: the bot requires several of them before concluding
    anything. See `zeroDamageHitsBeforeGivingUp` in the mission runner.

    **A target with `hits = 0` and `misses > 0` is not that signal**, and issue
    #267 is why it is carried anyway: the bot could not previously see a miss at
    all, so it could not tell an object it cannot hurt from one it cannot hit.
    The rule reading these is built so a miss can never open a case on its own.

    **Present-with-nothing and absent are different answers**, as everywhere
    else on this channel. The node is emitted on every reading a game log exists
    for, so no children means "the client reported no shots landing" while the
    node's absence means "this host does not carry the channel". Only the second
    may be read as "we do not know" -- and here the fail-safe direction is the
    opposite of the retreat's: a host that cannot answer must never read as
    "everything is immune", so absent has to keep the guns firing.
    """
    return {
        "pythonObjectAddress": "macos-host-synthetic-outgoing-damage",
        "pythonObjectTypeName": SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME,
        "dictEntriesOfInterest": {},
        "children": [
            {
                "pythonObjectAddress": f"macos-host-synthetic-outgoing-damage-{index}",
                "pythonObjectTypeName": SYNTHETIC_OUTGOING_DAMAGE_TARGET_TYPE_NAME,
                "dictEntriesOfInterest": {
                    "name": target["name"],
                    "hits": target["hits"],
                    "damage": target["damage"],
                    # Read strictly rather than with a default, because a caller
                    # that forgot this key would emit a node saying "no shots
                    # missed" -- a fabricated fact, and one the rule downstream
                    # would act on. The parser's own default belongs at the
                    # other end, where it means "this host is older than #267".
                    "misses": target["misses"],
                },
                "children": [],
            }
            for index, target in enumerate(targets)
        ],
    }


STATUS_LINES_UNCHANGED_LINE = "#   (%d status line(s) unchanged)"

# Matching the status text, less its first line, against what was printed last.
# Both sides are the bot's own bytes, so this is a comparison and not a parse.
STATUS_TEXT_LOG_BUDGET = 4000


def decision_log_lines(status_text, marker, last_lines):
    """What one decision puts in the log, and the lines to compare next against.

    **The status text's first line every time; each line below it only when it
    changed.**

    The repetition this ends is the *host's* rather than the bot's, which is why
    the fix is here and not in an Elm status function. A bot emits one status
    text per decision; this loop printed all of it every time, several times per
    reading, for as long as the run lasted. Measured over saxrat run 52 -- 27.7
    MB, 5,102 readings, 16,742 decisions -- **79.8% of the whole log was status
    text**, of which the diagnostic lines under the header were 77.2% and the
    header itself 2.6%.

    The first line is the bot's header -- for saxrat, `describeStatusHeader`,
    the one line an operator reads -- and it is printed on every decision so
    that "where is the ship, what is it shooting, is it in trouble" is
    answerable at any point in the log. Everything below it is a diagnostic
    whose value is the moment it changes.

    **Per line rather than per body, and the difference is a factor of two.**
    Suppressing the body only where the *whole* of it repeats removes 26.8% of
    that log: some counter or other moves on two decisions in three and drags
    all eleven other lines through with it. Suppressing each line against the
    last line printed in its place removes **61.5%** -- the diagnostics that
    genuinely are steady stop being reprinted by the ones that are not.

    **Judged against what was last printed, never against a reading count**,
    which is what makes suppression safe rather than merely cheap. A line that
    differs from the last line printed at its position is printed, whatever
    produced the difference and however many decisions a reading happens to
    take, so the "changed but not shown" case does not exist. Nothing is
    dropped; it is only not repeated.

    A *position* is not a clause -- a docked reading's status text is shorter
    than an in-space one's, so one index can hold different clauses at different
    moments. That costs nothing, because the invariant is about the position
    rather than the clause: whatever stands at index N is printed unless it is
    byte-identical to the last thing printed at index N. A clause returning to a
    position something else has since used differs from what was printed there,
    so it prints.

    **It says how many it suppressed**, because a log that silently prints a
    clause less often is a log whose counts have quietly changed meaning.
    Anything counting a status clause's occurrences in a recorded run is now
    counting the decisions that clause *moved* on rather than every decision,
    and this marker is what lets a reader tell that from a clause that stopped
    being printed at all. Counting readings is unaffected either way: that has
    always been done on `RequestToVolatileProcess`, not on status lines.

    The whole text is truncated before it is split, so the budget an over-long
    status text is held to is the one it was always held to rather than one per
    line.
    """
    status = (status_text or "")[:STATUS_TEXT_LOG_BUDGET]
    header, _, body = status.partition("\n")
    lines = [marker + header]
    if not body:
        return lines, last_lines
    remembered = list(last_lines or [])
    unchanged = 0
    for index, line in enumerate(body.split("\n")):
        if index < len(remembered) and remembered[index] == line:
            unchanged += 1
            continue
        while len(remembered) <= index:
            remembered.append(None)
        remembered[index] = line
        lines.append(line)
    if unchanged:
        lines.append(STATUS_LINES_UNCHANGED_LINE % unchanged)
    return lines, remembered


def synthetic_kills_node(kills):
    """A UI-tree node carrying how many rats the client paid a bounty for.

    The fourth synthetic node, with the same four safety properties as the other
    three: a type name that says in full that the client never wrote this, no
    display region, nothing under `_setText`/`_text`, and an absent node meaning
    something different from a zero.

    **This is `(combat)`'s argument applied to `(bounty)`, and the deny-list
    comment on `GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT` is what it has to
    answer.** That comment gives two reasons for withholding a channel and only
    one of them is about the lines: combat is withheld because it is per-shot
    noise, and bounty because "a second reader of those lines would be a second
    source of truth for the same statistic". The *lines* stay withheld here, as
    combat's do -- nothing about `entries_for_reading` changes. What travels is
    the count, and it travels through the console's own
    `BOUNTY_TEXT_RE`, so the bot's number and the console's number come off one
    pattern by construction rather than off two that could drift.

    **What it counts is what the client paid, which is not the same as what this
    ship killed**, and the difference is stated here rather than left for a
    later reader to assume:

    - A rat killed by a fleetmate that this ship contributed damage to still
      pays a bounty, so it is counted.
    - A rat this ship killed whose bounty went entirely elsewhere writes no
      line here, so it is not counted.
    - Structures, wrecks and anything with no bounty write no line at all,
      however thoroughly they are destroyed.

    So the honest reading of the number is "rats the client paid this character
    a bounty for since this run started", and no rule may read it as "kills by
    this ship".

    **It names nothing, and that is the point rather than a limitation.** The
    client writes no target name on this channel -- 17,388 lines across the
    recorded sessions and not one carries one -- so this count can never be
    split per rat, per name or per anomaly. PR #274 established what a
    name-keyed fold costs on this grid: a "702 consecutive misses on a target
    the guns went on to hurt" reading that turned out to be the same *name* on a
    different rat, because an anomaly is a pocket of identically named rats. A
    session total off a channel that names nothing cannot mis-attribute, because
    it never attributes.

    **Per reading rather than a running total**, like both damage nodes, so the
    session total is the bot's own memory and a later rule can still ask "did
    anything die on this reading". A reading during which nothing died carries
    `kills = 0`, which is an answer; the node's absence is "this host does not
    carry the channel", which is the only thing that may be read as "we do not
    know". A bot that collapsed those two would report a session that killed
    nothing as one whose kills nobody counted.
    """
    return {
        "pythonObjectAddress": "macos-host-synthetic-kills",
        "pythonObjectTypeName": SYNTHETIC_KILLS_TYPE_NAME,
        "dictEntriesOfInterest": {"kills": kills},
        "children": [],
    }


class VolatileHost:
    def __init__(self, game_log=None):
        self.roots = {}          # processId -> ui root address (int)
        self.root_search = {}    # processId -> {"begin": ms, "thread": Thread, "result": addr|None|"pending"}
        self.metatype = {}       # processId -> metatype addr
        self.str_type = {}       # processId -> str type addr
        self.live = {}           # processId -> LiveSample (kept for root-finding bootstrap only now)
        self.tree_walkers = {}   # processId -> TreeWalkerClient (the fast, native ReadFromWindow path)
        self.root_display_size = {}  # processId -> (width, height) in "game pixel" units, from UIRoot's own _displayWidth/_displayHeight
        self.game_pid = None
        # The client's own window title, which names the character it is flying.
        # Kept so `_set_autopilot_destination` routes *that* character rather
        # than whichever one a single stored token happened to belong to -- see
        # `esi_waypoint.set_destination`.
        self.game_window_title = None
        self.game_log = game_log  # GameLogTail, or None when there is no channel to give
        # `connection_lost_quit_point` over the last tree walked, waiting to be
        # taken by the loop. Kept here rather than recomputed from the task
        # result because the result carries the tree as *serialised JSON*, and
        # re-parsing several thousand nodes once a reading to ask one question
        # about them is a cost the read path does not need.
        self._connection_lost = None

    def _get_live(self, process_id):
        live = self.live.get(process_id)
        if live is None:
            live = rh.LiveSample(process_id)
            self.live[process_id] = live
        return live

    def _get_tree_walker(self, process_id):
        client = self.tree_walkers.get(process_id)
        if client is None:
            client = (win_platform.TreeWalkerClient(process_id) if IS_WINDOWS
                      else TreeWalkerClient(process_id))
            self.tree_walkers[process_id] = client
        return client

    def handle_request(self, request_json_str):
        req = json.loads(request_json_str)
        if "ListGameClientProcessesRequest" in req:
            procs = find_eve_processes()
            if procs:
                self.game_pid = procs[0]["processId"]
                self.game_window_title = procs[0].get("mainWindowTitle")
            return json.dumps({"ListGameClientProcessesResponse": procs})

        if "SearchUIRootAddress" in req:
            process_id = req["SearchUIRootAddress"]["processId"]
            return json.dumps({"SearchUIRootAddressResponse": self._search_ui_root(process_id)})

        if "ReadFromWindow" in req:
            body = req["ReadFromWindow"]
            return json.dumps({"ReadFromWindowResult": self._read_from_window(body)})

        if "SetAutopilotDestinationRequest" in req:
            body = req["SetAutopilotDestinationRequest"]
            return json.dumps({"SetAutopilotDestinationResult":
                               self._set_autopilot_destination(body)})

        # Nothing else is implemented. This used to answer everything with
        # CompletedEffectSequenceOnWindow, which reported success for requests
        # that never ran -- including, before the 2023_02_06 interface was
        # wired up, every input effect a bot on it sent. Input is now
        # intercepted before it reaches this method (see run_task), so anything
        # arriving here is genuinely unhandled and says so.
        print(f"# unhandled volatile-process request: {sorted(req)}", file=sys.stderr)
        return json.dumps({"CompletedEffectSequenceOnWindow": True})

    def _search_ui_root(self, process_id):
        now_ms = int(time.time() * 1000)
        if process_id in self.roots:
            return {
                "processId": process_id,
                "stage": {"SearchUIRootAddressCompleted": {"uiRootAddress": hex(self.roots[process_id])}},
            }

        state = self.root_search.get(process_id)
        if state is None:
            state = {"begin": now_ms, "result": "pending"}
            self.root_search[process_id] = state
            t = threading.Thread(target=self._search_ui_root_worker, args=(process_id, state), daemon=True)
            t.start()

        if state["result"] == "pending":
            return {
                "processId": process_id,
                "stage": {"SearchUIRootAddressInProgress": {
                    "searchBeginTimeMilliseconds": state["begin"],
                    "currentTimeMilliseconds": now_ms,
                }},
            }

        addr = state["result"]
        if addr is not None:
            self.roots[process_id] = addr
        return {
            "processId": process_id,
            "stage": {"SearchUIRootAddressCompleted": {"uiRootAddress": hex(addr) if addr else None}},
        }

    UI_ROOT_CACHE_PATH = os.path.join(tempfile.gettempdir(), "botlab-host-ui-root-cache.json")

    def _cached_ui_root(self, process_id):
        """A previously found root for this same client process, if it still
        reads back sensibly.

        Finding the root needs a full process dump (~20-40s), which is the
        whole cost of starting the bot -- and it is pure waste across a
        restart, since these addresses are per-process-launch and the client
        has usually not restarted. Cached on disk keyed by pid, then validated
        by actually reading the root: a stale entry (pid reused by an unrelated
        process, or the client relaunched into the same pid) gives a node with
        no _displayWidth, and we fall through to the slow path."""
        try:
            with open(self.UI_ROOT_CACHE_PATH, encoding="utf-8") as cache_file:
                entry = json.load(cache_file)
        except (OSError, ValueError):
            return None
        if entry.get("pid") != process_id:
            return None
        try:
            walker = self._get_tree_walker(process_id)
            probe = walker.tree(entry["root"], entry["metatype"], entry["str_type"],
                                max_depth=1, max_nodes=1)
        except Exception:
            return None
        if not (probe.get("dictEntriesOfInterest") or {}).get("_displayWidth"):
            return None
        print(f"# reusing cached UI root {entry['root']:#x} for process {process_id}", file=sys.stderr)
        return entry

    def _store_ui_root_cache(self, process_id, root, metatype, str_type):
        try:
            with open(self.UI_ROOT_CACHE_PATH, "w", encoding="utf-8") as cache_file:
                json.dump({"pid": process_id, "root": root,
                           "metatype": metatype, "str_type": str_type}, cache_file)
        except OSError:
            pass

    def _search_ui_root_worker(self, process_id, state):
        """One-time cost: take a real dump (the only way to repr-scan for
        the root object's address), find it, then all later ReadFromWindow
        calls use the fast LiveSample path -- no more dumps needed."""
        cached = self._cached_ui_root(process_id)
        if cached is not None:
            self.metatype[process_id] = cached["metatype"]
            self.str_type[process_id] = cached["str_type"]
            state["result"] = cached["root"]
            return
        if IS_WINDOWS:
            # No dump and no repr scan: the text macOS seeds from is not in this
            # client's memory at all (FINDINGS.md section 3), and the type
            # objects are reachable directly through python27.dll's exports.
            try:
                root, metatype, str_type = win_platform.search_ui_root(process_id)
                if metatype is not None:
                    self.metatype[process_id] = metatype
                    self.str_type[process_id] = str_type
                if root is not None:
                    self._store_ui_root_cache(process_id, root, metatype, str_type)
                state["result"] = root
            except Exception as exc:
                print(f"# SearchUIRootAddress failed: {exc}", file=sys.stderr)
                state["result"] = None
            return
        try:
            with tempfile.TemporaryDirectory() as d:
                subprocess.run([MEMORY_SAMPLE_BIN, str(process_id), d], check=True,
                                capture_output=True)
                sample = rh.Sample(d)
                metatype = rh.find_metatype(sample, self._any_seed_addr(sample))
                if metatype is None:
                    state["result"] = None
                    return
                str_type = self._bootstrap_str_type(sample, metatype)
                self.metatype[process_id] = metatype
                self.str_type[process_id] = str_type
                root = rh.find_ui_root(sample, metatype, str_type)
                if root is not None:
                    self._store_ui_root_cache(process_id, root, metatype, str_type)
                state["result"] = root
        except Exception as exc:
            print(f"# SearchUIRootAddress failed: {exc}", file=sys.stderr)
            state["result"] = None

    @staticmethod
    def _any_seed_addr(sample):
        # limit=1 (the previous version) took whatever the very first
        # repr-scan hit happened to be, with no validation -- the repr
        # text sitting in EVE's debug-log ring buffer can outlive the
        # object it described (e.g. a ModuleButton destroyed/recreated
        # since the line was logged), so find_metatype on that address
        # can dereference freed/reused memory and return garbage or None.
        # Observed live: this failed SearchUIRootAddress outright even
        # though the same dump had plenty of other, valid candidates.
        # Same fix as _bootstrap_str_type below -- scan more hits and
        # validate each with the 'type(type) is type' invariant instead
        # of trusting the first one blindly.
        hits = rh.repr_scan(sample, limit=200)
        for addrs in hits.values():
            for addr in addrs:
                metatype = rh.find_metatype(sample, addr)
                if metatype is not None and sample.read_u64(metatype + 8) == metatype:
                    return addr
        raise RuntimeError("no repr-scan hit in this dump resolved to a valid metatype")

    @staticmethod
    def _bootstrap_str_type(sample, metatype):
        # limit=5 was too small: repr_scan's limit counts every match, not
        # distinct (class, address) pairs, and the debug-log ring buffer
        # can genuinely contain the same "<Class object at 0x...>" line
        # repeated several times in a row (e.g. from repeated tooltip
        # reads) -- observed live, all 5 hits were the identical address,
        # which happened to have no usable dict, so bootstrapping failed
        # even though the rest of the dump had plenty of good candidates.
        # Raised the limit and dedupe by address so a run of repeats can't
        # exhaust the scan before reaching a distinct object.
        hits = rh.repr_scan(sample, limit=200)
        seen_addrs = set()
        for addrs in hits.values():
            for addr in addrs:
                if addr in seen_addrs:
                    continue
                seen_addrs.add(addr)
                d = rh.get_dict(sample, addr, metatype)
                if d is None:
                    continue
                st = rh.bootstrap_str_type(sample, d, metatype)
                if st:
                    return st
        raise RuntimeError("could not bootstrap str type")

    def _read_from_window(self, body):
        process_id = None
        for pid, root in self.roots.items():
            process_id = pid
            break
        if process_id is None:
            return {"ProcessNotFound": True}

        root_addr = int(body["uiRootAddress"], 16)
        metatype = self.metatype.get(process_id)
        str_type = self.str_type.get(process_id)
        if metatype is None or str_type is None:
            return {"ProcessNotFound": True}

        tree_walker = self._get_tree_walker(process_id)
        # max_depth=12/max_nodes=4000 was too shallow: some real UI content
        # (e.g. the probe scanner's scan-result row labels) sits 15+ levels
        # deep, well past the old depth cap, and once max_depth was raised
        # enough to reach it, the walk needed more than 4000 nodes to avoid
        # the DFS node budget running out on unrelated branches first before
        # reaching the deeper one. Measured against a real live tree
        # (~4800-4900 nodes at full depth): depth=16/nodes=5000 reliably
        # reaches this content at a real but bounded extra cost (~1.6s ->
        # ~2.3s per read on the reference machine) -- see CLAUDE.md.
        # Still too shallow for the Opportunities panel's "Warp to Site"
        # button, confirmed live via a raw memory RE dump to sit at depth 19
        # (UIRoot -> ... -> InfoPanelJobBoard -> ... -> TravelStateButtonTaskWidget
        # -> EveLabelMedium) -- silently truncated before Bot.elm's
        # `findUiElementWithText "Warp to Site"` ever sees it, so the bot fell
        # back to the scan-results/tether path instead. Raised to 24; the
        # same live tree had only 3309 nodes total with just 24 of them past
        # depth 16, so the extra depth costs effectively nothing here.
        #
        # The node budget was left at 5000 when the depth was raised, and that
        # became the binding limit instead: a mission grid busy with wrecks and
        # jetcans measured 5554 nodes, so every read silently dropped ~550 of
        # them. Which ones depends on DFS order, so the loss is arbitrary --
        # live, this intermittently truncated ListSurroundingsBtn out of the
        # location info panel, and since the panel's parser returns Nothing
        # without that button, the bot decided the panel did not exist and sat
        # clicking "enable the info panel" 181 times. A silent wrong answer
        # again, not an error. Raised to 20000: measured on that same grid, the
        # untruncated read costs 0.80s against 0.72s truncated, and anything
        # past 10000 costs nothing at all since the tree is smaller than that.
        tree = tree_walker.tree(root_addr, metatype, str_type, max_depth=24, max_nodes=20000)
        # Asked before the synthetic nodes below are appended, so what is
        # judged is what the client is actually drawing (#299). They carry no
        # display region and no `MessageBox`, so the answer would not change --
        # but a reading that says the client is showing a modal must be about
        # the client and nothing this host added to it.
        self._connection_lost = connection_lost_quit_point(tree)
        entries = tree.get("dictEntriesOfInterest", {})
        w, h = entries.get("_displayWidth"), entries.get("_displayHeight")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
            self.root_display_size[process_id] = (w, h)
        if self.game_log is not None:
            # Scoped to this reading by construction: the queue is drained here
            # and nowhere else, so what the node carries is what the client said
            # between the previous read and this one. A buffer that grew instead
            # would have the bot answering a refusal from four minutes ago.
            tree.setdefault("children", []).append(
                synthetic_game_log_node(self.game_log.entries_for_reading())
            )
            # A sibling rather than a child of the node above, because the two
            # answer different questions and must be able to be absent
            # independently later. Both are drained here and nowhere else, and
            # the queues are independent, so the order of these two calls does
            # not matter -- which is asserted rather than assumed.
            tree["children"].append(
                synthetic_incoming_damage_node(self.game_log.incoming_damage_for_reading())
            )
            # A third sibling, for the same reason the second is one: how hard
            # this ship is being hit and whether its own shots are achieving
            # anything are different questions, and a consumer of either must be
            # able to find the other absent. The queues are independent, so the
            # order of these three calls does not matter -- asserted rather than
            # assumed, in `TailFanOutTest`.
            tree["children"].append(
                synthetic_outgoing_damage_node(self.game_log.outgoing_damage_for_reading())
            )
            # A fourth sibling, on the same argument as the second and third:
            # how many rats died is a different question from how hard this ship
            # is being hit or whether its shots are landing, and a consumer of
            # any of them must be able to find the others absent. Its queue is
            # independent of the other five, so the order of these four calls
            # does not matter -- asserted in `TailFanOutTest` rather than
            # assumed.
            tree["children"].append(
                synthetic_kills_node(self.game_log.kills_for_reading())
            )
        return {
            "Completed": {
                "processId": process_id,
                "readingId": f"reading-{int(time.time()*1000)}",
                "memoryReadingSerialRepresentationJson": json.dumps(tree),
            }
        }

    def take_connection_lost(self):
        """The last read's Connection Lost verdict, once.

        Cleared on the way out so the watch is fed exactly one reading per read
        that completed. A tick that dispatches a screenshot or an input task
        must not advance a counter measured in readings.
        """
        verdict, self._connection_lost = self._connection_lost, None
        return verdict

    def _set_autopilot_destination(self, body):
        """Set the client's autopilot destination through ESI.

        Answers `{"Completed": {"destinationId": N}}` or `{"Failed": "why"}`,
        and never anything in between. A destination that was not set, followed
        by travel logic finding no route, is this repo's signature failure --
        so the two outcomes are different shapes rather than one shape with a
        flag, and a caller that reads neither gets nothing it can mistake for
        success.

        Everything is caught here. `run_task`'s own `except` answers
        `ProcessNotFound`, which BotFramework reads as "the volatile process is
        gone" and responds to by tearing it down and re-running root discovery
        -- an expensive, entirely wrong reaction to CCP being slow.

        Bounded, because this runs inside the host's single request/response
        loop: an ESI that never answers would hold up the tick that asked, and
        every tick behind it. The budget covers the whole resolve-and-set, not
        one request, since resolving a station `/universe/ids/` does not index
        costs a round trip per station in its system.

        Nothing token-shaped is logged or returned. The refresh token stays in
        the Keychain, `esi_waypoint` hands it straight to the token endpoint,
        and `EsiError` messages are built from status codes and names -- the
        same reason this file never prints the client's own command line.
        """
        name = body.get("name")
        destination_id = body.get("destinationId")
        budget = body.get("budgetSeconds")
        if budget is None:
            budget = esi_waypoint.DEFAULT_BUDGET_SECONDS
        target = name if name is not None else destination_id
        try:
            was_set = esi_waypoint.set_destination(
                name=name,
                destination_id=destination_id,
                clear_other=body.get("clearOtherWaypoints", True),
                add_to_beginning=body.get("addToBeginning", False),
                budget_seconds=budget,
                # Whose autopilot this endpoint drives is decided by the token,
                # not by the client the bot is attached to, so a token for the
                # wrong character reports success and routes somebody else. The
                # window title is what this host knows the character by, and
                # `esi_waypoint` now holds a token per character and uses this
                # name to pick one. `None` means the title could not be read:
                # that still proceeds where one character is authorised, and
                # refuses where several are, since any pick would be a guess.
                expected_character=esi_waypoint.character_from_window_title(
                    self.game_window_title),
            )
        except esi_waypoint.EsiError as failure:
            print(f"# ESI: destination {target!r} not set: {failure}", file=sys.stderr)
            return {"Failed": str(failure)}
        except Exception as failure:  # noqa: BLE001 -- see the docstring
            print(f"# ESI: destination {target!r} not set: {failure!r}", file=sys.stderr)
            return {"Failed": f"unexpected failure setting the destination: {failure!r}"}
        print(f"# ESI: destination {target!r} set ({was_set})", file=sys.stderr)
        return {"Completed": {"destinationId": was_set}}


# ---------------------------------------------------------------------------
# Task dispatch (top-level BotLab.BotInterface_To_Host_2024_10_19.Task)
# ---------------------------------------------------------------------------

READS_NOT_COMPLETING_THRESHOLD = 3
READS_NOT_COMPLETING_REPEAT_EVERY = 60


def read_failure_reason(task_tag, result):
    """Why this task's result is a read that did not complete, or `None`.

    Issue #166. In `saxrat_run11.log` the client stopped answering read requests
    and the bot did not notice: 18,158 issued against 17,263 completed, 895 that
    never came back. `ReadingFromGameClientCompleted` never fired again, so
    `updateMemoryForNewReadingFromGame` never ran, so every counter written there
    froze at the same instant -- and the host reprints the current decision on
    every line it writes, so the rest of the run reads exactly like thousands of
    healthy readings.

    **Nothing in `Bot.elm` can fix that.** PR #165 established that the rules
    which looked frozen were correct as written; nothing can advance a counter on
    a reading that never arrived. The defect is that the log says nothing, and
    the host is the only thing positioned to say it.

    Only the volatile-process read is judged. A screenshot or an input task
    failing is a different fact with its own consequences, and calling those a
    stalled read would put the wrong word in the log at the moment somebody is
    reading it carefully.
    """
    if task_tag != "RequestToVolatileProcess":
        return None
    response = (result or {}).get("RequestToVolatileProcessResponse")
    if not isinstance(response, dict):
        return None
    err = response.get("Err")
    if err is None:
        return None
    if isinstance(err, dict) and err.get("ProcessNotFound"):
        return "the client did not answer (ProcessNotFound)"
    return "the read failed: %s" % (err,)


class ReadCompletionWatch:
    """Counts consecutive reads that did not complete, and says so.

    Loud on the way in and on the way out: a run that recovers silently would
    leave an operator reading the same ambiguity in the other direction.

    The repeat exists because the failure mode is a session that goes on for
    hours -- one line at the top of an eight-hour stall is a line nobody scrolls
    back to.
    """

    def __init__(self, threshold=READS_NOT_COMPLETING_THRESHOLD,
                 repeat_every=READS_NOT_COMPLETING_REPEAT_EVERY):
        self.threshold = threshold
        self.repeat_every = repeat_every
        self.consecutive = 0
        self.announced = False

    def note(self, reason):
        """`reason` from `read_failure_reason`; `None` means the read completed.

        Answers the line to print, or `None`.
        """
        if reason is None:
            if self.announced:
                recovered = self.consecutive
                self.consecutive = 0
                self.announced = False
                return ("# READS COMPLETING AGAIN after %d that did not -- the"
                        " decisions above this line were made from a reading"
                        " that could not change" % recovered)
            self.consecutive = 0
            return None

        self.consecutive += 1
        if self.consecutive == self.threshold:
            self.announced = True
            return ("# READS ARE NOT COMPLETING: %d in a row -- %s. Every"
                    " counter is frozen and the decisions below are made from"
                    " the last reading that arrived, not from the client"
                    % (self.consecutive, reason))
        if self.announced and self.consecutive % self.repeat_every == 0:
            return ("# READS STILL NOT COMPLETING: %d in a row -- %s"
                    % (self.consecutive, reason))
        return None


# The two halves of the Connection Lost modal's own wording, lowercased. Both
# rather than either, and kept identical to `messageBoxSaysTheConnectionIsLost`
# in both `Bot.elm` copies, which #185 derived from the same recorded instances.
#
# Both halves matter because the corpus carries a *second* box titled
# `Connection Lost`: `saxrat_run15.log`'s reads
# `OK / Connection Lost / The connection to the server was closed.`, over a
# single **OK**. That one is deliberately not matched here -- its wording was
# never walked, its button is not the Quit this acts on, and quitting a client
# on a title alone is the indiscriminate match #101 is about.
CONNECTION_LOST_WORDING = ("connection lost", "connection to server was lost")

# The label on the one control the box offers, lowercased and trimmed. This is
# matched rather than the button's `_name`, because the name is **not known**:
# `messageBoxIdentityForOperator` truncates before the `with buttons [...]`
# section, so none of the four recorded instances says what it was. `Quit` is
# known -- it is the first entry of the identity every one of them printed,
# which is `getAllContainedDisplayTexts` over the box.
CONNECTION_LOST_QUIT_LABEL = "quit"

# How many consecutive readings must carry the box before the click is posted.
# Small on purpose: in all four recorded instances (`saxrat_run22`, `33`, `38`
# and `40`) the box was still on screen at the last reading of the log, so it
# has never once cleared on its own and waiting longer buys nothing. What the
# count is for is a half-built tree, not a transient dialog.
CONNECTION_LOST_READINGS_BEFORE_QUIT = 5

# How many readings to let a posted click take effect before posting another.
# The click can legitimately not land: `_windows_input` stands down for
# `HUMAN_INPUT_STAND_DOWN_SECONDS` after a person touches the mouse, and it
# aborts a sequence whose window is not frontmost.
CONNECTION_LOST_READINGS_BETWEEN_CLICKS = 10

# How many clicks are posted before this stops trying and says so. It does not
# escalate to killing the client: a kill is what #299 exists to stop -- EVE
# writes its window layout on a clean exit, and the killed client came back with
# the probe scanner closed and the info panels in the state that then met #297.
CONNECTION_LOST_MAX_CLICKS = 3


def _fixed_number(value):
    """An int out of a dict entry, by `getDisplayRegionFromDictEntries`' rule.

    The Elm side accepts an int, a string holding one, or an object with an
    `int_low32` field -- EVE's own numbers arrive as all three.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        return _fixed_number(value.get("int_low32"))
    return None


def node_display_text(node):
    """The node's own display text, by `getDisplayText`'s rule, or `None`.

    Under `_setText` or `_text`, longest wins, and either may hold a nested node
    rather than a string -- EVE's info panel puts the text one level down inside
    a `Link` object, which the Elm side already had to handle.
    """
    entries = node.get("dictEntriesOfInterest") or {}
    texts = []
    for key in ("_setText", "_text"):
        entry = entries.get(key)
        if isinstance(entry, str):
            texts.append(entry)
        elif isinstance(entry, dict):
            nested = node_display_text(entry)
            if nested is not None:
                texts.append(nested)
    if not texts:
        return None
    # `max` keeps the first of equal-length candidates, which is the order
    # `List.sortBy (String.length >> negate) |> List.head` settles ties in.
    return max(texts, key=len)


def display_texts_in(node):
    """Every display text in `node` and its descendants.

    The raw subtree, with no regard for display regions -- `parseMessageBox`
    reads the box's wording with `getAllContainedDisplayTexts`, which walks the
    unparsed node.
    """
    found = []
    stack = [node]
    while stack:
        current = stack.pop()
        text = node_display_text(current)
        if text is not None:
            found.append(text)
        stack.extend(current.get("children") or [])
    return found


def _display_region_of(node):
    """`(x, y, width, height)` relative to the parent, or `None`.

    All four keys or nothing, which is what the Elm side requires before it will
    treat a node as having a position at all.
    """
    entries = node.get("dictEntriesOfInterest") or {}
    region = []
    for key in ("_displayX", "_displayY", "_displayWidth", "_displayHeight"):
        value = _fixed_number(entries.get(key))
        if value is None:
            return None
        region.append(value)
    return tuple(region)


def walk_with_regions(node, x, y, width, height):
    """`(node, absolute x, absolute y, width, height)`, for the region-bearing subtree.

    `x`/`y` are where `node` itself sits, absolutely. Children add their own
    `_displayX`/`_displayY` to that, which is `asUITreeNodeWithInheritedOffset`'s
    arithmetic -- the stored numbers are relative to the parent and only the sum
    is a position on the screen.

    **A child with no display region ends the walk there**, descendants and all.
    That is not a shortcut: `listDescendantsWithDisplayRegion` cannot see past
    such a node either, so a subtree this skips is one the bot's own parser
    never had a position for, and clicking into it would be acting on a
    coordinate nothing computed.
    """
    stack = [(node, x, y, width, height)]
    while stack:
        current, current_x, current_y, current_w, current_h = stack.pop()
        yield current, current_x, current_y, current_w, current_h
        for child in current.get("children") or []:
            region = _display_region_of(child)
            if region is None:
                continue
            stack.append((child, current_x + region[0], current_y + region[1],
                          region[2], region[3]))


def find_connection_lost_box(tree):
    """The Connection Lost modal in `tree` as `(node, x, y, w, h)`, or `None`.

    A `MessageBox` node saying both halves of the wording. The type name is
    asked for as well as the words because that is what the box *is* -- four
    recorded runs printed `Message box: N/120 ... 'Quit / Connection Lost /
    Connection to server was lost.'`, and that clause is only ever built from a
    node `parseMessageBoxesFromUITreeRoot` already accepted, which matches
    `pythonObjectTypeName == "MessageBox"` and nothing else.
    """
    root = _display_region_of(tree) or (0, 0, 0, 0)
    for node, x, y, width, height in walk_with_regions(tree, *root):
        if node.get("pythonObjectTypeName") != "MessageBox":
            continue
        texts = [text.lower() for text in display_texts_in(node)]
        if all(any(half in text for text in texts)
               for half in CONNECTION_LOST_WORDING):
            return node, x, y, width, height
    return None


# What `connection_lost_quit_point` answers when there is no such box, and when
# there is one but nothing in it this host can aim at.
CONNECTION_LOST_ABSENT = "absent"
CONNECTION_LOST_NO_CONTROL = "no control"
CONNECTION_LOST_QUIT_AT = "quit at"


def connection_lost_quit_point(tree):
    """`(verdict, point)` -- where to click to quit a disconnected client.

    `point` is in the same units and origin as `totalDisplayRegion`, so it needs
    the window's screen origin added before it is a place on the screen, exactly
    as the bot's own clicks do.

    **It fails to `CONNECTION_LOST_NO_CONTROL` rather than to a guess.** The
    box's node shape has never been walked: what is known is that it parses as a
    `MessageBox` and that `Quit` is among its display texts, both off the
    recorded runs. What is *not* known is which node carries that text or what
    the button's `_name` is. So the only thing clicked is a node whose text is
    `Quit` and which has a display region of its own -- and if the tree turns
    out not to hold one, nothing is clicked and the host says so. The centre of
    the box, or its only button by shape, are both the sort of guess that clicks
    an unread control on a live client.
    """
    found = find_connection_lost_box(tree)
    if found is None:
        return CONNECTION_LOST_ABSENT, None
    box, box_x, box_y, box_w, box_h = found
    for node, x, y, width, height in walk_with_regions(
            box, box_x, box_y, box_w, box_h):
        text = node_display_text(node)
        if text is None or text.strip().lower() != CONNECTION_LOST_QUIT_LABEL:
            continue
        if width <= 0 or height <= 0:
            continue
        return CONNECTION_LOST_QUIT_AT, (x + width // 2, y + height // 2)
    return CONNECTION_LOST_NO_CONTROL, None


class ConnectionLostWatch:
    """Decides when to click Quit on a client that has lost its connection.

    Issue #299. A client sitting on this modal holds the install open so the
    launcher cannot patch, and nothing dismissed it: since #185 the bot answers
    `LeaveTheMessageBoxAlone` at it, deliberately, because every control on it
    quits the client and #54's rule is that the automatic reply declines. So it
    sat -- one launched 15:38 on 16 Aug was still there the next morning, having
    slept through downtime -- until a person ran `Stop-Process`, which is
    **worse than clicking Quit**: EVE writes its window layout on a clean exit,
    and the killed client came back with the probe scanner closed and the info
    panels in the state that then met #297. Both were investigated as fresh
    bugs before the cause was understood.

    **The trigger is the box, not the read-completion count.** #299 offered
    `ReadCompletionWatch`'s threshold as the hook, on the reasoning that the
    client stops answering when this happens. The corpus says otherwise, three
    times over. In `saxrat_run40.log` the box was up for **1199 consecutive
    readings**, every one of them a read that completed and carried the box's
    own wording -- the client goes on rendering and its memory goes on being
    readable, because a read here is `tree_walker` walking the client's address
    space, not a request the client has to answer. `READS ARE NOT COMPLETING`
    appears in **no** recorded run, this dialog's four included. And run 11, the
    stall #164 was filed about, was 608 reads issued and never answered rather
    than reads that came back with an `Err`, which is the only shape
    `read_failure_reason` counts. So that counter is neither necessary nor
    sufficient here, and the dialog is the positive evidence #299 asked for.

    **The host is the actor, so #54's rule is not touched at all.** No affirmative
    goes near `closeMessageBoxByDeclining`; the bot goes on leaving the box
    alone and the host quits the client out from under it.

    **It does not relaunch.** Quitting alone unblocks the launcher's patching,
    which is #299's stated goal, and relaunching has its own failure mode --
    CLAUDE.md records a press-and-hold that needed two attempts because the
    first only activated the launcher window.
    """

    def __init__(self, before_quit=CONNECTION_LOST_READINGS_BEFORE_QUIT,
                 between_clicks=CONNECTION_LOST_READINGS_BETWEEN_CLICKS,
                 max_clicks=CONNECTION_LOST_MAX_CLICKS):
        self.before_quit = before_quit
        self.between_clicks = between_clicks
        self.max_clicks = max_clicks
        self.readings = 0
        self.clicks = 0
        self.next_click_at = before_quit
        self.announced = None

    def note(self, verdict, point):
        """One reading. Answers `(point to click or None, line to print or None)`."""
        if verdict == CONNECTION_LOST_ABSENT:
            line = None
            if self.announced is not None:
                line = ("# THE CONNECTION LOST BOX IS GONE after %d readings and"
                        " %d click(s) at its Quit" % (self.readings, self.clicks))
            self.readings = 0
            self.clicks = 0
            self.next_click_at = self.before_quit
            self.announced = None
            return None, line

        self.readings += 1

        if verdict == CONNECTION_LOST_NO_CONTROL:
            if self.readings < self.before_quit or self.announced == "no control":
                return None, None
            self.announced = "no control"
            return None, (
                "# CONNECTION LOST, AND NOTHING TO CLICK: the box has been up"
                " for %d readings but carries no node reading 'Quit' with a"
                " display region, so this host will not click at it. The client"
                " is holding the install open and the launcher cannot patch"
                " until somebody quits it" % self.readings)

        if self.readings < self.next_click_at:
            return None, None

        if self.clicks >= self.max_clicks:
            if self.announced == "given up":
                return None, None
            self.announced = "given up"
            return None, (
                "# CONNECTION LOST AND THE CLIENT WILL NOT TAKE THE CLICK: %d"
                " clicks posted at its Quit over %d readings and the box is"
                " still up. Not killing it -- a kill loses the window layout"
                " (#299), so this is now an operator's call"
                % (self.clicks, self.readings))

        self.clicks += 1
        self.next_click_at = self.readings + self.between_clicks
        self.announced = "clicking"
        return point, (
            "# CONNECTION LOST: the client has been showing 'Connection Lost /"
            " Connection to server was lost.' for %d readings. Clicking its"
            " Quit at %s (attempt %d of %d) so the launcher can patch -- a"
            " clean exit, which is what preserves the window layout"
            % (self.readings, point, self.clicks, self.max_clicks))


class TaskDispatcher:
    def __init__(self, execute_input=False, capture_screenshots=False, game_log=None):
        self.volatile = VolatileHost(game_log=game_log)
        self._process_ids = {}
        self.execute_input = execute_input
        self.capture_screenshots = capture_screenshots
        self._scale_x = 1.0
        self._scale_y = 1.0
        # How far the game's canvas sits inside its window, in game pixels.
        self._canvas_inset = (0, 0)
        # Last calibration reported, so a stable geometry says its piece once
        # rather than on every read -- but a geometry that *changes* mid-run
        # says so again, which is the case that stranded run 22.
        self._canvas_note = None
        # `clientRectLeftUpperToScreen` as last reported to the bot, which is
        # what turns a `totalDisplayRegion` into a place on the screen. Kept so
        # this host can aim a click of its own by the same arithmetic the bot
        # uses (#299); `None` until a window read has calibrated it, and a
        # click with no calibration is declined rather than guessed.
        self._client_left_upper = None
        self._cg_input = None
        # Mouse buttons currently held, so cursor motion between a ButtonDown
        # and its ButtonUp is emitted as a drag rather than a plain move.
        self._buttons_down = set()
        # Keys this host has posted a KeyDown for and not yet a KeyUp, in press
        # order, so `_windows_input` can take back whatever a sequence leaves
        # held. A list rather than a set because the undo is the presses in
        # reverse: a modifier pressed first is released last.
        self._keys_down = []
        self._last_mouse_pos = None
        # Monotonic time of our own last posted event, so a stand-down check can
        # tell a person's input apart from the bot's own.
        self._last_input_post_at = None
        # `glide_per_event_cost_ms` readings from every glide `_glide_to` has
        # posted during the `WindowsInputRequest` currently being executed --
        # see there and `_report_input_cost`. Reset per step, not carried
        # across one, so a quiet step cannot be "reported" against a glide
        # from several steps ago.
        self._glide_costs_this_step = []

    def run_task(self, task):
        """task: {"TagName": <payload>}. Returns a TaskResultStructure dict
        (already matching the {"TagName": ...} envelope Main.elm's decoder
        expects) -- see decodeTaskResult in Main.elm."""
        (tag, payload), = task.items()

        if tag == "CreateVolatileProcess":
            process_id = f"vproc-{random.randint(0, 1_000_000_000)}"
            return {"CreateVolatileProcessResponse": {"Ok": {"processId": process_id}}}

        if tag == "RandomBytesRequest":
            n = payload
            return {"RandomBytesResponse": list(os.urandom(n))}

        if tag == "ReleaseVolatileProcess":
            return {"CompleteWithoutResult": True}

        if tag == "RequestToVolatileProcess":
            request_struct = self._unwrap_request_considering_focus(payload)
            request_str = request_struct["request"]
            try:
                # Bots on the 2023_02_06 host interface have no
                # WindowsInputRequest task -- their input arrives here instead,
                # inside the volatile-process request. Intercept it rather than
                # letting it reach VolatileProcess.handle_request, which has no
                # way to reach the input executor.
                effect_sequence = _effect_sequence_of_request(request_str)
                if effect_sequence is not None:
                    self._windows_input(_effect_sequence_as_input_items(effect_sequence))
                    response_json = json.dumps({"CompletedEffectSequenceOnWindow": True})
                else:
                    response_json = self.volatile.handle_request(request_str)
                return {
                    "RequestToVolatileProcessResponse": {
                        "Ok": {
                            "exceptionToString": None,
                            "returnValueToString": response_json,
                            "durationInMilliseconds": 1,
                            "acquireInputFocusDurationMilliseconds": 0,
                        }
                    }
                }
            except Exception as exc:
                return {"RequestToVolatileProcessResponse": {"Err": {"ProcessNotFound": True}}}

        if tag == "InvokeMethodOnWindowRequest":
            window_id, method = payload
            return self._invoke_method_on_window(window_id, method)

        if tag == "WindowsInputRequest":
            return self._windows_input(payload)

        if tag == "OpenWindowRequest":
            return {"OpenWindowResponse": {"Err": "OpenWindowRequest not supported by this macOS host"}}

        return {"CompleteWithoutResult": True}

    def click_connection_lost_quit(self, point):
        """Post one left click at `point`, a `totalDisplayRegion` coordinate.

        Answers the lines to print. The sequence is the bot's own shape and
        goes down the bot's own path, so everything `_windows_input` has learned
        applies unchanged -- the window is brought to the front first (CLAUDE.md:
        a window that is not frontmost will not accept a click), the move is
        eased and forced because a click needs a real movement gesture, and a
        person who has touched the mouse in the last few seconds stands this
        down. A stood-down click is not a failure: the box is still there on the
        next reading and the watch posts another.
        """
        if not self.execute_input:
            return ["# CONNECTION LOST: would click Quit at %s, but"
                    " --execute-input is not set, so nothing is posted" % (point,)]
        if self._client_left_upper is None:
            return ["# CONNECTION LOST: cannot click Quit -- no window read has"
                    " calibrated the screen origin yet, so %s is not a place on"
                    " the screen" % (point,)]
        processes = find_eve_processes()
        if not processes:
            return ["# CONNECTION LOST: cannot click Quit -- no client window"
                    " to click in"]
        left, top = self._client_left_upper
        x, y = left + point[0], top + point[1]
        response = self._windows_input([
            {"BringWindowToForeground": processes[0]["mainWindowId"]},
            {"MouseMoveAbsolute": [x, y]},
            {"WaitMilliseconds": 210},
            {"ButtonDown": 0x01},
            {"WaitMilliseconds": 210},
            {"ButtonUp": 0x01},
        ])["WindowsInputResponse"]
        errors = response.get("errorMessages") or []
        if errors:
            return ["# CONNECTION LOST: the click at Quit did not go through:"
                    " %s" % "; ".join(errors)]
        return ["# CONNECTION LOST: clicked Quit at screen point (%d, %d)" % (x, y)]

    @staticmethod
    def _unwrap_request_considering_focus(payload):
        (tag, inner), = payload.items()
        if tag == "RequestNotRequiringInputFocus":
            return inner
        return inner["request"]

    def _report_canvas_calibration(self, root_size, point_w, point_h,
                                   backing_scale, scale_x, scale_y,
                                   inset_x, inset_y):
        """Say how the canvas was reconciled with its window, when that changes.

        Silent for the ordinary case of a canvas that fills its window, loud
        for both of the others: an inset, and a canvas this cannot explain at
        all. The second is the one worth a line -- the per-axis divide it falls
        back to is a fudge, and a wrong coordinate is invisible in a log
        otherwise, since a click that lands on nothing looks exactly like a
        click that lands.
        """
        if not root_size:
            return
        canvas_w, canvas_h = int(root_size[0]), int(root_size[1])
        if inset_x or inset_y:
            note = ("inset", canvas_w, canvas_h, point_w, point_h, inset_x, inset_y)
            message = (f"# window canvas {canvas_w}x{canvas_h} is inset by "
                       f"({inset_x}, {inset_y}) in a {point_w}x{point_h} pt window "
                       f"at scale {backing_scale:g} -- coordinates carry the inset")
        elif abs(scale_x - scale_y) > 1e-9:
            note = ("per-axis", canvas_w, canvas_h, point_w, point_h)
            message = (f"# window canvas {canvas_w}x{canvas_h} does not fit a "
                       f"{point_w}x{point_h} pt window at any single scale "
                       f"(backing {backing_scale:g}); falling back to per-axis "
                       f"{scale_x:.4f}/{scale_y:.4f}. If clicks land off target, "
                       f"this is why")
        else:
            note = ("filled", canvas_w, canvas_h, point_w, point_h)
            message = None
        if note == self._canvas_note:
            return
        self._canvas_note = note
        if message:
            print(message, file=sys.stderr)

    def _invoke_method_on_window(self, window_id, method):
        (mtag, mpayload), = method.items()
        if mtag == "ReadFromWindowMethod":
            # window_id is "winapi-<mainWindowId>" (see
            # buildTaskFromInvokeMethodOnWindowRequest in BotFramework.elm).
            # Real rect via window_probe --all (works regardless of active
            # macOS Space); this is what the bot uses to translate
            # memory-read UI-relative positions into absolute screen
            # coordinates for input, so getting it right matters even
            # before real input execution exists.
            # Coordinate units: the game's own internal UI coordinates
            # (_displayX/_displayY etc, read via memory) are NOT simply
            # backing_scale * points -- confirmed by comparing UIRoot's own
            # _displayWidth/_displayHeight against the real window's point
            # size empirically: the ratios came out *different* per axis
            # (1.684x / 1.743x on the machine this was tested on), not a
            # clean 2.0. The game evidently has its own internal UI-scale
            # setting independent of the OS's Retina factor. So we
            # self-calibrate per axis from live data every read, rather
            # than trusting backing_scale: scale_x/scale_y = UIRoot's own
            # reported size / the real window's point size (from
            # window_probe). The bot's own coordinate math
            # (effectOnWindowAsWindowsInputSequenceItem in BotFramework.elm)
            # does a plain, unscaled `uiRelativePosition +
            # clientRectLeftUpperToScreen` addition with no DPI correction
            # anywhere -- so both sides of that sum need to already be in
            # the same ("game pixel") units. We report the rect scaled up
            # here so the sum comes out correct, then scale back down to
            # real points in _windows_input just before actually calling
            # cg_input (CGEventPost wants real points -- confirmed via a
            # CGEventGetLocation round-trip test).
            window_number = int(window_id.split("-", 1)[1])
            rect = get_window_rect(window_number)
            if rect is None:
                rect = {"left": 0, "top": 0, "right": 0, "bottom": 0, "backing_scale": 1.0}
            point_w = max(1, rect["right"] - rect["left"])
            point_h = max(1, rect["bottom"] - rect["top"])
            root_size = self.volatile.root_display_size.get(self.volatile.game_pid)
            scaled_rect, scale_x, scale_y, (inset_x, inset_y) = \
                window_canvas_geometry(rect, root_size)
            self._scale_x, self._scale_y = scale_x, scale_y
            self._canvas_inset = (inset_x, inset_y)
            self._client_left_upper = (scaled_rect["left"], scaled_rect["top"])
            self._report_canvas_calibration(root_size, point_w, point_h,
                                            rect["backing_scale"], scale_x, scale_y,
                                            inset_x, inset_y)
            result = {
                "readingId": f"screenshot-{int(time.time()*1000)}",
                "windowText": "",
                "windowRect": scaled_rect,
                "clientRect": scaled_rect,
                "clientRectLeftUpperToScreen": {"x": scaled_rect["left"], "y": scaled_rect["top"]},
                "windowDpi": int(96 * rect["backing_scale"]),
                # Screenshot capture is opt-in (--capture-screenshots), off
                # by default: a real capture costs ~1.6s (dominated by the
                # `screencapture` CLI call itself, not our encoding), which
                # blows through a sub-1s-per-tick target for any bot that
                # doesn't actually need pixel data. eve-online-warp-to-0-autopilot
                # doesn't -- EveOnline.ParseUserInterface never reads
                # pixels_1x1/pixels_2x2 in this bot's own decision logic,
                # only EveOnline.ParseGuiFromScreenshot's two narrow,
                # unvisited code paths do. Empty crop lists are valid per
                # the type (List ImageCrop), so this is a correct, cheap
                # response, not a stub.
                "imageData": (capture_image_data(window_number, scaled_rect, scale_x, scale_y,
                                                 canvas_inset=(inset_x, inset_y))
                              if self.capture_screenshots else
                              {"screenshotCrops_original": [], "screenshotCrops_binned_2x2": [], "screenshotCrops_binned_4x4": []}),
            }
            return {"InvokeMethodOnWindowResponse": [window_id, {"Ok": {"ReadFromWindowMethodResult": result}}]}
        if mtag == "CloseWindowMethod":
            return {"InvokeMethodOnWindowResponse": [window_id, {"Ok": {"InvokeMethodOnWindowResultWithoutValue": True}}]}
        return {"InvokeMethodOnWindowResponse": [window_id, {"Err": {"MethodNotAvailableError": True}}]}

    def _get_cg_input(self):
        if IS_WINDOWS:
            # In-process rather than a persistent helper. cg_input has to be one
            # because it keeps the click position as process-local state; on
            # Windows a button event is delivered wherever the cursor actually
            # is, which the OS owns, so there is no state and no process.
            if self._cg_input is None:
                self._cg_input = win_platform.CgInput(execute=self.execute_input)
            return self._cg_input
        if self._cg_input is None or self._cg_input.poll() is not None:
            self._cg_input = subprocess.Popen(
                [CG_INPUT_BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
            )
        return self._cg_input

    def _cg(self, cmd):
        if IS_WINDOWS:
            reply = self._get_cg_input().command(cmd)
            if not cmd.startswith("idle"):
                self._last_input_post_at = time.monotonic()
            return reply
        proc = self._get_cg_input()
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()
        reply = proc.stdout.readline().strip()
        # "idle" only asks a question; everything else posts an event, and
        # _seconds_since_human_input needs to know when we last did.
        if not cmd.startswith("idle"):
            self._last_input_post_at = time.monotonic()
        return reply

    def _cg_move(self, x, y):
        """Move the cursor, as a drag when a mouse button is currently held.

        macOS delivers cursor motion as either kCGEventMouseMoved or
        kCGEventLeft/RightMouseDragged, and cg_input exposes those as its
        separate "move" and "drag" commands. Everything here used to emit
        "move" unconditionally, including between a ButtonDown and its
        ButtonUp -- which means the bot could not drag anything at all: EVE
        reads a button-down followed by plain moved events as a click that
        happens to be followed by the pointer wandering off, not as a drag.
        reload_drones.py hit the same wall from the other direction and has
        used "drag" for the intermediate points since (see its drag(), and
        its note that a click-then-move sequence reads as a plain click).
        """
        if self._buttons_down:
            button = sorted(self._buttons_down)[0]
            return self._cg(f"drag {x:.1f} {y:.1f} {button}")
        return self._cg(f"move {x:.1f} {y:.1f}")

    def _glide_to(self, start_x, start_y, target_x, target_y, steps, step_delay):
        glide_start = time.monotonic()
        for i in range(1, steps):
            t = i / steps
            self._cg_move(start_x + (target_x - start_x) * t, start_y + (target_y - start_y) * t)
            time.sleep(step_delay)
        self._cg_move(target_x, target_y)
        self._last_mouse_pos = (target_x, target_y)
        # #163: this call, on its own, is exactly the homogeneous shape
        # `glide_per_event_cost_ms` assumes -- `steps` posted moves and
        # `(steps - 1)` known sleeps -- whichever of `_move_mouse_eased`'s two
        # call sites reached it, so recording here rather than at each call
        # site covers both without duplicating the arithmetic.
        self._glide_costs_this_step.append(
            glide_per_event_cost_ms(time.monotonic() - glide_start, steps, step_delay))

    def _move_mouse_eased(self, target_x, target_y, steps=10, step_delay=0.025, force_movement=False):
        """Move the cursor to (target_x, target_y) via a few intermediate
        points instead of one instant CGEventPost teleport.

        Feedback from live runs: a hover-triggered flyout submenu (the
        Photon-UI "Warp to Within..." distance list off "Warp to Within",
        and the wreck loot-menu cascade) kept getting dismissed before it
        had a chance to open, or took several discard-and-reopen retries
        to eventually land. EveOnline.BotFrameworkSeparatingMemory.elm's
        cascade-follow logic already has a separate, larger fix for the
        "gave up too early" half of that (see its widened lookback) -- but
        the other likely contributor is that a single-point teleport may
        not always register as a genuine hover-enter the way a real mouse
        glide does, matching the *already established*, analogous finding
        for drag recognition (reload_drones.py's drag(): "EVE only
        recognizes this as a drag ... if the pointer moves promptly ...
        a synthetic click-then-move sequence with any pause reads as a
        plain click" -- Photon UI evidently cares about real movement
        trajectories, not just final position, for more than one kind of
        gesture). Skips easing (jumps straight there) on the very first
        move of a session, when there's no known prior position to
        interpolate from.

        steps/step_delay tuned from a live A/B: the original 6 steps /
        12ms (~70ms total glide) still let the anomaly-warp cascade get
        stuck hovering "Warp to Within" with the flyout never opening,
        confirmed live (screenshotted the same unopened menu, unmoved,
        after 5+ minutes and 300+ read/act cycles). A manually-driven
        glide over the same real target -- same coordinates, same
        mechanism, just slower (~250ms total) and from a more deliberate
        approach point -- opened the flyout on the first try. The
        earlier, successful anomaly-warp cascades in that same run
        (before the stuck one) suggest this isn't a hard failure, just a
        marginal one -- widening it live-verified.

        Widening steps/step_delay alone wasn't enough, though -- a second
        live run with this wider glide still "flapped" (menu opening,
        never expanding) the same way. The actual difference between
        that and the one hand-driven glide that *did* work: the manual
        one moved once and was then left alone; the bot's own decision
        logic recomputes "move mouse to this entry" fresh every tick
        while the menu list still looks unchanged (which it does, right
        up until the flyout would open) and re-issues the same move
        every ~3-4s cycle. If the flyout needs sustained, uninterrupted
        dwell to expand, re-glide-ing to the *same* spot every tick would
        reset that dwell timer before it ever accumulates enough -- an
        endless retrigger, not a failure to arrive. Skip re-issuing any
        move at all once we're already at (approximately) the target, so
        a hover that's already in place gets to sit undisturbed instead
        of being restarted every tick.

        force_movement changes that skip behavior for click sequences
        specifically (see the caller in _windows_input, which sets it
        whenever the next item is a ButtonDown). Live-verified pattern:
        a right-click or menu-entry click that fails to register on its
        first, genuinely-glided attempt gets retried on every following
        tick at the *same* target -- which this function's own dwell-
        preservation skip then turns into a click fired from a static
        cursor with no accompanying movement at all, every single retry.
        Given the drag and flyout-hover findings above already establish
        that Photon UI cares about real cursor movement, not just final
        position, a click retried with no movement is plausibly doomed
        to keep failing the same way the first one did -- self-
        reinforcing exactly the "stuck for several ticks, then suddenly
        works" pattern observed live. force_movement nudges a few pixels
        off target and glides back, so a click always gets a real (if
        small) movement gesture right before it fires, even when the
        cursor was already resting on the target. Not applied to plain
        hover moves (submenu expansion), which still want the dwell-
        preservation skip -- restarting *those* on every tick is the
        opposite, already-fixed problem.
        """
        # Logged unconditionally (cheap, one line per move) since this is
        # exactly the diagnostic needed to tell apart the two possible
        # causes of a slow-to-open hover flyout: the target coordinate
        # jittering tick to tick (so this never hits the skip branch and
        # dwell keeps getting reset) versus the coordinate being stable
        # but the flyout still not opening (so this hits skip immediately
        # and the delay is downstream, e.g. in the Elm-side cascade
        # discard/reopen logic instead).
        # Returns True if the cursor actually moved (glided, nudged, or
        # this was the first move of the session), False if the move was
        # skipped because the cursor was already at the target -- callers
        # use this to decide whether a settle delay is needed before a
        # click that immediately follows (see CLICK_SETTLE_DELAY_SECONDS).
        if self._last_mouse_pos is not None:
            start_x, start_y = self._last_mouse_pos
            distance = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
            already_there = abs(target_x - start_x) < 3 and abs(target_y - start_y) < 3
            if already_there and not force_movement:
                print(f"#     move: already at ({target_x:.1f}, {target_y:.1f}), "
                      f"skipping to preserve hover dwell (distance {distance:.1f}px)", file=sys.stderr)
                return False
            if already_there and force_movement:
                move_start = time.monotonic()
                nudge_x, nudge_y = target_x - 12, target_y - 8
                self._cg_move(nudge_x, nudge_y)
                time.sleep(step_delay)
                self._glide_to(nudge_x, nudge_y, target_x, target_y, steps, step_delay)
                print(f"#     move: already at ({target_x:.1f}, {target_y:.1f}) but this is a click -- "
                      f"nudged off and glided back for a real movement gesture, in "
                      f"{time.monotonic() - move_start:.3f}s", file=sys.stderr)
                return True
            move_start = time.monotonic()
            self._glide_to(start_x, start_y, target_x, target_y, steps, step_delay)
            print(f"#     move: glided ({start_x:.1f}, {start_y:.1f}) -> ({target_x:.1f}, {target_y:.1f}) "
                  f"distance={distance:.1f}px in {time.monotonic() - move_start:.3f}s", file=sys.stderr)
            return True
        self._cg_move(target_x, target_y)
        self._last_mouse_pos = (target_x, target_y)
        print(f"#     move: first move of session, jumped straight to ({target_x:.1f}, {target_y:.1f})",
              file=sys.stderr)
        return True


    @staticmethod
    def _consume_double_click(items, idx, button):
        """How many items make up a double click starting at `idx`, or 0.

        The shape is ButtonDown/ButtonUp/ButtonDown/ButtonUp on one button,
        ignoring the WaitMilliseconds the framework interleaves between every
        pair of effects. Returns the number of items to skip past (not counting
        the one at `idx` itself), so the caller can jump the whole run.
        """
        wanted = ["ButtonUp", "ButtonDown", "ButtonUp"]
        matched = 0
        for offset in range(idx + 1, len(items)):
            (tag, payload), = items[offset].items()
            if tag == "WaitMilliseconds":
                continue
            if tag != wanted[matched]:
                return 0
            if vk_to_mouse_button(payload) != button:
                return 0
            matched += 1
            if matched == len(wanted):
                return offset - idx
        return 0

    def _seconds_since_human_input(self):
        """How long since a *person* last touched the mouse or keyboard.

        `None` when it cannot be told apart from our own activity.

        The obvious approach does not work. CGEventSourceSecondsSinceLastEventType
        against kCGEventSourceStateHIDSystemState is documented as hardware-only,
        and the intent was that our own CGEventPost calls would not disturb it --
        but measured live while the bot was clicking, it resets to ~0 on our own
        events just as it does on a real one. So the reading alone cannot say who
        moved the mouse.

        What distinguishes them is that we know when *we* last posted. If the last
        input event is no more recent than our own last post, it was us. If it is
        appreciably more recent, somebody else is at the machine.
        """
        reply = self._cg("idle")
        if not reply.startswith("idle "):
            return None
        try:
            idle = float(reply.split()[1])
        except (IndexError, ValueError):
            return None
        if self._last_input_post_at is None:
            return idle
        since_our_post = time.monotonic() - self._last_input_post_at
        # A margin so ordinary jitter between posting an event and reading the
        # clock does not read as a person.
        if since_our_post - idle < 0.5:
            return None
        return idle

    def _windows_input(self, items):
        start = time.time()
        if not self.execute_input:
            print(f"# WindowsInputRequest (not executing, --execute-input not set): {items}", file=sys.stderr)
            return {
                "WindowsInputResponse": {
                    "completedStepsCount": 0,
                    "abortedStepsCount": len(items),
                    "totalTimeMilliseconds": 0,
                    "errorMessages": ["input execution disabled (run with --execute-input to enable)"],
                }
            }

        human_idle = self._seconds_since_human_input()
        if human_idle is not None and human_idle < HUMAN_INPUT_STAND_DOWN_SECONDS:
            # Stand down rather than fight for the cursor. Nothing needs
            # unwinding: the bot re-derives its decision from a fresh reading
            # every step, so a skipped sequence costs one tick and is simply
            # decided again once the machine is quiet.
            print(f"#   standing down: someone used the mouse/keyboard "
                  f"{human_idle:.1f}s ago", file=sys.stderr)
            return {
                "WindowsInputResponse": {
                    "completedStepsCount": 0,
                    "abortedStepsCount": len(items),
                    "totalTimeMilliseconds": 0,
                    "errorMessages": [f"standing down: human input {human_idle:.1f}s ago"],
                }
            }

        scale_x = self._scale_x or 1.0
        scale_y = self._scale_y or 1.0
        completed = 0
        errors = []
        # Reset per step rather than carried over: #163's report has to say
        # "no glide posted this step" on a step that genuinely posted none,
        # and a stale reading from several steps back would answer instead.
        self._glide_costs_this_step = []
        # Tracks whichever window the sequence most recently named via
        # BringWindowToForeground/AbortIfWindowNotInForeground. Verified
        # right at those checkpoints (the bot's own protocol already
        # calls BringWindowToForeground at the start of every input
        # sequence -- BotFramework.elm always prepends it), not before
        # every individual mouse/keyboard action: that finer-grained
        # check was tried first but re-verifies a condition that can't
        # actually change between two CGEventPost calls a few
        # milliseconds apart, while costing a window_probe subprocess
        # spawn per action -- pure latency for no real safety gain. The
        # coarser per-sequence checkpoint still catches the actual risk
        # (focus having drifted to something else since the *last*
        # cycle), just without penalizing every action inside one
        # already-verified sequence.
        current_target_window = None
        # Index up to which items have already been consumed by an earlier
        # step -- set when a double-click pattern is collapsed into one
        # command, so its remaining press/release items are not replayed.
        skip_until_index = -1
        for idx, item in enumerate(items):
            if idx <= skip_until_index:
                continue
            (tag, payload), = item.items()
            try:
                if tag == "WaitMilliseconds":
                    # Do not pause in the middle of a drag. The framework
                    # interleaves a WaitMilliseconds between every pair of
                    # effects, which for a drag lands one between the
                    # ButtonDown and the moves meant to follow it -- and EVE
                    # only reads a drag when the pointer moves promptly after
                    # the press. With the pause in, the client receives a click
                    # and then the cursor wandering off, which is exactly what
                    # the overview scrollbar drag looked like on screen: mouse
                    # onto the bar, mouse away, handle unmoved.
                    #
                    # The pause before the release is kept. reload_drones.py,
                    # whose drag has worked for a long time, presses, moves
                    # immediately, and then waits at the destination before
                    # letting go -- the drop needs that settle even though the
                    # drag itself needs the motion to be prompt.
                    next_real_tag_after_wait = None
                    for later_item in items[idx + 1:]:
                        later_tag = list(later_item.keys())[0]
                        if later_tag == "WaitMilliseconds":
                            continue
                        next_real_tag_after_wait = later_tag
                        break
                    #
                    # A held *key* is worse than a held button: macOS starts
                    # auto-repeating it. The framework's 210ms between KeyDown
                    # and KeyUp is longer than the system repeat delay, so every
                    # typed character came out as a run of itself. Run 115 typed
                    # "Reports" into the inventory quick filter and left
                    # "reportreprrrrrr...rrreporteporteporte...".
                    #
                    # But a keypress with *no* hold at all is not the answer
                    # either: the client can miss it, which reads as characters
                    # dropping at random. So the pause before a KeyUp becomes a
                    # short, fixed hold -- long enough to register, far below the
                    # system's repeat delay -- rather than either extreme.
                    #
                    # Scoped to the release specifically, not to "any key is
                    # down". effectsToEnterString holds Shift across a whole run
                    # of capitals, so keying off the held set would collapse the
                    # gaps between those characters too, firing them back to back
                    # with no spacing -- the same shape that loses keystrokes.
                    if next_real_tag_after_wait in ("KeyUp", "CharacterUp"):
                        time.sleep(KEY_HOLD_SECONDS)
                    elif (not self._buttons_down) or next_real_tag_after_wait == "ButtonUp":
                        time.sleep(payload / 1000.0)
                elif tag == "BringWindowToForeground":
                    window_number = int(payload.split("/")[-1])
                    current_target_window = window_number
                    if not self.volatile.game_pid:
                        errors.append("BringWindowToForeground: game pid not known yet")
                        continue
                    if not bring_window_to_foreground(self.volatile.game_pid, window_number):
                        errors.append(f"BringWindowToForeground: could not verify window {window_number} "
                                       f"came to the foreground after retries -- aborting rest of sequence")
                        break
                elif tag == "AbortIfWindowNotInForeground":
                    window_number = int(payload.split("/")[-1])
                    current_target_window = window_number
                    if not _window_is_onscreen(window_number):
                        errors.append(f"AbortIfWindowNotInForeground: window {window_number} not in "
                                       f"foreground -- aborting rest of sequence")
                        break
                elif tag in ("MouseMoveAbsolute", "MouseMoveRelative", "ButtonDown", "ButtonUp",
                             "ButtonScroll", "KeyDown", "KeyUp", "CharacterDown", "CharacterUp"):
                    if tag == "MouseMoveAbsolute":
                        x, y = payload
                        # force_movement whenever this move leads straight
                        # into a click: see _move_mouse_eased's docstring --
                        # a click needs a real movement gesture even when
                        # the cursor is already resting on the target,
                        # unlike a plain hover move (which should keep
                        # skipping to preserve dwell).
                        # Skip past WaitMilliseconds items to find the next
                        # *real* action -- EveOnline.BotFramework.elm's
                        # buildTaskFromEffectSequence interspersed a
                        # WaitMilliseconds 210 between every pair of effects
                        # (discovered while chasing this same fix), so the
                        # item immediately after a move is never literally
                        # "ButtonDown" -- checking only items[idx + 1]
                        # silently never matched, meaning force_movement
                        # and the settle-delay sleep below never actually
                        # fired despite looking like they should have.
                        next_real_tag = None
                        for later_item in items[idx + 1:]:
                            later_tag = list(later_item.keys())[0]
                            if later_tag == "WaitMilliseconds":
                                continue
                            next_real_tag = later_tag
                            break
                        moved = self._move_mouse_eased(
                            x / scale_x, y / scale_y, force_movement=(next_real_tag == "ButtonDown")
                        )
                        if moved and next_real_tag == "ButtonDown":
                            time.sleep(CLICK_SETTLE_DELAY_SECONDS)
                    elif tag == "MouseMoveRelative":
                        errors.append("MouseMoveRelative not supported (Windows-relative semantics not implemented)")
                        continue
                    elif tag == "ButtonDown":
                        button = vk_to_mouse_button(payload)
                        # A double click cannot be expressed as two ordinary
                        # clicks: what makes the second one count is the
                        # kCGMouseEventClickState field, which only cg_input's
                        # own "doubleclick" command sets. The bot asks for one
                        # by emitting two press/release pairs on the same
                        # button with nothing in between (see
                        # Common.EffectOnWindow.effectsMouseDoubleClickAtLocation),
                        # so that shape is recognised here and collapsed into
                        # the single command that actually works. Collapsing
                        # also drops the framework's ~210ms inter-effect waits,
                        # which would otherwise sit between the two clicks.
                        consumed = self._consume_double_click(items, idx, button)
                        if consumed:
                            self._cg(f"doubleclick {button}")
                            skip_until_index = idx + consumed
                            completed += 1
                            continue
                        self._cg(f"down {button}")
                        self._buttons_down.add(button)
                    elif tag == "ButtonUp":
                        button = vk_to_mouse_button(payload)
                        self._cg(f"up {button}")
                        self._buttons_down.discard(button)
                    elif tag == "ButtonScroll":
                        button, direction, offset = payload
                        self._cg(f"scroll 0 {direction * offset}")
                    elif tag == "KeyDown":
                        code, extended = payload
                        mac_code = vk_to_cgkeycode(code)
                        if mac_code is None:
                            errors.append(f"no macOS key mapping for VK code {code}")
                            continue
                        self._cg(f"keydown {mac_code}")
                        if mac_code not in self._keys_down:
                            self._keys_down.append(mac_code)
                    elif tag == "KeyUp":
                        code, extended = payload
                        mac_code = vk_to_cgkeycode(code)
                        if mac_code is None:
                            errors.append(f"no macOS key mapping for VK code {code}")
                            continue
                        self._cg(f"keyup {mac_code}")
                        if mac_code in self._keys_down:
                            self._keys_down.remove(mac_code)
                    elif tag in ("CharacterDown", "CharacterUp"):
                        errors.append(f"{tag} (raw unicode character input) not implemented")
                        continue
                else:
                    errors.append(f"unhandled WindowsInputSequenceItem: {tag}")
                    continue
                completed += 1
            except Exception as exc:
                errors.append(f"{tag}: {exc}")

        # Take back anything still held. Nothing else in this host ever did:
        # `_keys_down` was written on every KeyDown and read nowhere, so a key
        # this sequence pressed and did not release stayed down for the rest of
        # the session, underneath every keystroke and click after it. Driven by
        # what was actually *posted* rather than by `keys_left_held(items)`, so
        # that it also covers a sequence cut short -- the `break` above, or a
        # `cg_input` that died between a press and its release.
        #
        # Said out loud rather than fixed silently, because the release is a
        # repair and the sequence that needed one is a bug somewhere above:
        # `keys_left_held` names the half the *bot* asked for, which an operator
        # can take to the bot, and the count released names what this host had
        # to undo.
        #
        # Wrapped, because the most likely reason a key was left held is a
        # `cg_input` that has just died -- so the repair runs in exactly the
        # state where posting can fail again, and an exception escaping here
        # would take the whole task with it. `_keys_down` is cleared either way:
        # a release that could not be posted is not one this host can retry, and
        # carrying the code forward would make every later sequence report it.
        asked_unbalanced = keys_left_held(items)
        if self._keys_down:
            for mac_code in reversed(self._keys_down):
                try:
                    self._cg(f"keyup {mac_code}")
                except Exception as exc:
                    errors.append(f"could not release held key {mac_code}: {exc}")
            print(f"#   KEYS LEFT HELD: released {self._keys_down} at the end of "
                  f"this sequence -- a key held past a sequence stays down under "
                  f"everything after it. The sequence itself asked for "
                  f"{asked_unbalanced} without a release.", file=sys.stderr)
            self._keys_down = []

        self._report_input_cost()

        return {
            "WindowsInputResponse": {
                "completedStepsCount": completed,
                "abortedStepsCount": len(items) - completed,
                "totalTimeMilliseconds": int((time.time() - start) * 1000),
                "errorMessages": errors,
            }
        }

    def _report_input_cost(self):
        """Print what a posted event on this step cost -- #163.

        Uses the worst (most expensive) glide this step posted, if any: a
        step can carry several, and the point of this report is to notice a
        saturated posting path, which the cheapest glide in a mixed step
        could hide. Resets the reading it consumed, so the next report is
        never this step's answer repeated.
        """
        worst = max(self._glide_costs_this_step) if self._glide_costs_this_step else None
        self._glide_costs_this_step = []
        print(f"#   {describe_input_cost(worst)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

# The longest a single tick may hold the outer loop before it is given back.
#
# **Everything that protects a run lives outside the task loop**: `tick += 1`,
# the `max_ticks` check, the console command drain and the session deadline are
# all reached only once `while pending` returns. The deadline's own comment
# calls itself "a lease renewed every tick, so a bot that stops asking -- or
# that hangs, or crashes -- is stopped on the next one", and a tick that does
# not end is a run where there is no next one and none of the three are ever
# evaluated. Issue #321; #312 found the console half of the same hole.
#
# **Seconds rather than substeps, because substeps miss the worst cases.**
# Measured over every `*.log` under `~/eve-bot-logs` -- 120 files, 237,431
# ticks with a measurable duration -- a substep cap of 50 still misses two of
# the 39 blocks longer than ten minutes, and the worst thing every cap misses
# is the same tick: `martha_run1_2026-08-20.log` tick 640, 3,140 seconds spent
# on 45 substeps. `slicer_run1_2026-08-19.log` tick 482 blocked 2,674 seconds
# on three. A handful of tasks that each take forever hold the loop exactly as
# hard as thousands of fast ones, and only the clock sees both.
#
# **300 sits in a real gap.** Ticks are normally tiny: the mode is 3 substeps,
# 99% run 20 or fewer, and the 11-20 band's 95th percentile blocks for under 18
# seconds. Of the 331 ticks that blocked longer than a minute, 304 never
# changed their own status header from first substep to last -- no kill, no
# target, no system, no damage -- which is the wedge shape. Among the 27 whose
# header moved at all, the longest that is not already known to be pathological
# is **180.9 s**, and the next is **414.1 s**. Anything between those two cuts
# only ticks that were getting nowhere.
#
# The bound is deliberately clear of setup, which normally completes in
# seconds: `getNextSetupTask` is a closed state machine waiting on specific
# results, so a guard firing there could stall a launch rather than rescue one.
# At 300 s a setup that tripped this was already broken.
MAX_TICK_SECONDS = 300.0


def tick_bound_note(tick, elapsed_seconds, decisions, abandoned_tasks):
    """What to say when a tick has held the loop too long, or `None`.

    A declaration of its own so a case can ask the rule rather than drive the
    whole event loop to reach it -- the same reason `countReadingsWithoutShipUI`
    is not a `let` inside the step it serves.

    **It says what happened and not that anything is fixed.** Handing the tick
    back does not un-wedge the bot: the outer loop sends a `TimeArrivedEvent`,
    the bot re-derives, and if the cause is still there it asks for the same
    tasks and blocks again. What the bound buys is that the wedge becomes
    visible in the tick counter, interruptible from the console, and subject to
    the session deadline.
    """
    if elapsed_seconds <= MAX_TICK_SECONDS:
        return None
    return (f"# tick {tick} has held the loop for {elapsed_seconds:.0f}s over "
            f"{decisions} decision(s), past the {MAX_TICK_SECONDS:.0f}s bound -- "
            f"giving it back with {abandoned_tasks} task(s) undispatched, which "
            f"the bot re-asks for on the next reading. The tick counter, the "
            f"console's pause/stop and the session deadline are all downstream "
            f"of this loop and have not run while it held.")


def run_bot(bot_js_path, settings, max_ticks=None, execute_input=False, capture_screenshots=False,
            session_duration_minutes=None, game_log_dir=None, console=None):
    proc = subprocess.Popen(
        ["node", DRIVER_JS, bot_js_path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
        text=True, bufsize=1,
        # The driver writes JSON, and JSON is UTF-8. `text=True` alone takes the
        # *locale* encoding, which on macOS is already UTF-8 and on Windows is
        # cp1252 -- so this line is a no-op there and load-bearing here. Without
        # it the loop dies with `'charmap' codec can't decode byte 0x90` the
        # moment a reading carries a character cp1252 has no place for, which is
        # any real EVE UI string.
        encoding="utf-8",
    )
    game_log = GameLogTail(game_log_dir) if game_log_dir else None
    dispatcher = TaskDispatcher(execute_input=execute_input, capture_screenshots=capture_screenshots,
                                game_log=game_log)

    def send_event(event_at_time):
        event = {"timeInMilliseconds": int(time.time() * 1000), "eventAtTime": event_at_time}
        proc.stdin.write(json.dumps(event) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("bot process exited")
        return json.loads(line)

    response = send_event({"BotSettingsChangedEvent": settings or ""})

    # A bot that refuses its settings answers `FinishSession` here, naming the
    # key it could not read. Read that answer before sending anything else.
    #
    # **Sending a second event on top of it destroys the diagnostic.** The bot
    # is now finished and still holds `botSettings = Nothing`, so the next event
    # routes through `processEventAfterIntegrateEvent`, finds no settings, and
    # answers `"Unexpected order of events: I did not receive any bot-settings
    # changed event."` -- which overwrites `response` and is what the operator
    # sees. The true message, `"Failed to parse these bot-settings: <key>"`, is
    # gone, and the one that replaces it points at event ordering: a launch that
    # failed because saxrat was handed the mission runner's drone settings cost
    # a session's debugging under an error describing a different fault
    # entirely.
    #
    # Only reachable when `--session-duration-minutes` is set, which both
    # launchers always pass -- so in practice a settings typo *always* reported
    # the wrong cause.
    if "FinishSession" in response:
        print(f"# FinishSession: {response['FinishSession']['statusText']}", file=sys.stderr)
        if console is not None:
            console.note_finished(response["FinishSession"]["statusText"])
        proc.stdin.close()
        proc.wait(timeout=5)
        return

    session_end_at_milliseconds = None
    if session_duration_minutes is not None:
        # BotFramework.elm's own continueIfShouldHide already docks (and
        # stays docked, via Bot.elm's ifDocked branch) once
        # secondsToSessionEnd drops under 200 -- that logic just needed
        # something to actually populate sessionTimeLimitInMilliseconds via
        # a SessionDurationPlannedEvent, which nothing was sending before
        # this. Computed from time.time() (matching send_event's own
        # timeInMilliseconds basis below) so the bot's internal comparison
        # lines up with real wall-clock time.
        session_end_at_milliseconds = int(time.time() * 1000) + int(session_duration_minutes * 60 * 1000)
        print(f"# Session duration planned: {session_duration_minutes:.1f} minutes "
              f"-- bot will dock once ~200s remain", file=sys.stderr)
        response = send_event(
            {"SessionDurationPlannedEvent": {"timeInMilliseconds": session_end_at_milliseconds}}
        )

    read_watch = ReadCompletionWatch()
    connection_lost_watch = ConnectionLostWatch()
    tick = 0
    tick_start = time.monotonic()
    # Only so the granted-overrun notice is printed when the figure changes
    # rather than on every tick past the end.
    last_granted_overrun = None
    # The destination the bot last asked for and this host acted on, so a
    # standing ask is not a route set on every tick. `None` while it is not
    # asking, which is what lets the same station be asked for again later.
    last_requested_destination = None
    # The destination asked for by *any* decision of the tick now running, not
    # only by the one it happens to end on.
    #
    # #306. A tick drains a queue of tasks and every completion hands back a
    # fresh ContinueSession, so `cont` at the foot of the loop is whatever the
    # bot decided *after* the last effect was dispatched. A bot that wants a
    # route while it is also driving a context-menu cascade writes the directive
    # on the decisions that work the menu and something else on the decision the
    # tick ends on, and the ask was then never read at all: the parser was never
    # shown the text, so nothing printed and nothing was suppressed either.
    # Across the 37 recorded runs that ask for a route, every one of the 229
    # routes this host set came from a tick whose *final* decision carried the
    # directive, and all 454 asks that landed on an earlier decision of a tick
    # were ignored -- which is a run parked with hours left whenever the cadence
    # does not happen to line up.
    #
    # Collected here and acted on at the foot of the loop, rather than acted on
    # where it is seen: the ESI call blocks, and blocking between a completed
    # task and the next one would cut a dispatched input sequence in half.
    tick_requested_destination = None
    # The status text's lines below its first, as they were last *printed*, one
    # entry per position. Compared against rather than counted per reading, so a
    # line that changed can never be suppressed however the bot happens to be
    # stepping -- see `decision_log_lines`.
    last_status_lines = [None]

    def log_decision(cont, decision_seq):
        # Every ContinueSession response carries its own freshly computed
        # statusText -- a genuinely new decision, not a duplicate of the
        # last one printed. Confirmed live: completing a WindowsInputRequest
        # task can hand back a *new* ContinueSession (a fresh read + a new
        # decision) without an intervening TimeArrivedEvent at all, so
        # several real decide-and-click rounds can happen inside what used
        # to be logged as a single outer-loop "tick" -- printing only once
        # per outer iteration (the old behavior) silently dropped all but
        # the last of those rounds, hiding exactly the kind of stray click
        # this diagnostic exists to catch. Sub-numbered ("N.0", "N.1", ...)
        # under the same outer tick N so the burst is still visually
        # grouped.
        elapsed = time.monotonic() - tick_start
        lines, last_status_lines[0] = decision_log_lines(
            cont["statusText"], f"# [{tick}.{decision_seq}] ({elapsed:.3f}s) ",
            last_status_lines[0])
        for line in lines:
            print(line, file=sys.stderr)
        if console is not None:
            console.note_decision(tick, cont["statusText"])
        if game_log is not None:
            for line in game_log.lines_for_echo():
                print(f"#   game log: {line}", file=sys.stderr)
                if console is not None:
                    console.note_game_log(line)

    stop_requested = False

    while True:
        if "FinishSession" in response:
            print(f"# FinishSession: {response['FinishSession']['statusText']}", file=sys.stderr)
            if console is not None:
                console.note_finished(response["FinishSession"]["statusText"])
            break

        if console is not None:
            # Apply what the console asked for on this thread and no other: it
            # is the one that owns the pipe to the bot process, and that pipe is
            # a strict request/response conversation. A handler thread writing
            # to it would interleave with a task response and desynchronise the
            # runtime.
            #
            # Pause and stop are *also* drained inside the task loop below, and
            # this is still where both are answered -- the pause wait and the
            # stop break live here. The settings change is what has to stay
            # here to be applied at all, because re-sending
            # `BotSettingsChangedEvent` is itself a write to the pipe and this
            # is the point where the conversation is between exchanges rather
            # than inside one.
            while True:
                command = console.take_command()
                if command is None:
                    break
                if command == "pause":
                    console.set_paused(True)
                elif command == "resume":
                    console.set_paused(False)
                elif command == "stop":
                    stop_requested = True

            new_settings = console.take_settings()
            if new_settings is not None:
                # The bot re-reads its whole settings string from this event --
                # the same one the session opens with -- so a live change needs
                # no restart and no special path in the bot.
                print("# applying settings change from the console", file=sys.stderr)
                response = send_event({"BotSettingsChangedEvent": new_settings})
                console.note_host("settings applied")
                continue

            if stop_requested:
                print("# stop requested from the console", file=sys.stderr)
                console.note_finished("stopped from the console")
                break

            while console.is_paused():
                # Paused means paused: no reads, no input, nothing sent to the
                # bot. Held here rather than by skipping work further down, so
                # a paused session cannot be halfway through a click sequence.
                time.sleep(0.25)
                command = console.take_command()
                if command == "resume":
                    console.set_paused(False)
                elif command == "stop":
                    stop_requested = True
                    break
            if stop_requested:
                print("# stop requested from the console", file=sys.stderr)
                console.note_finished("stopped from the console")
                break

        cont = response["ContinueSession"]
        decision_seq = 0
        log_decision(cont, decision_seq)
        # Every decision of this tick is a reading the bot took and a status
        # text it wrote, so every one of them can carry the route directive --
        # see `tick_requested_destination`. Started fresh here rather than
        # carried over, so a bot that has stopped asking clears the lease.
        tick_requested_destination = bot_requested_destination(cont.get("statusText"))
        tick_start = time.monotonic()

        # Drain tasks as a queue, not a fixed batch: (1) a response can
        # offer several tasks at once (e.g. the real per-cycle read sends
        # both a memory-read RequestToVolatileProcess *and* a screenshot
        # InvokeMethodOnWindowRequest together) and both need dispatching,
        # not just the first; (2) completing one task can also unlock a
        # brand new task in the *next* response (e.g. CreateVolatileProcess
        # completing leads straight to a RequestToVolatileProcess, before
        # another TimeArrivedEvent). Track by taskId so both the original
        # batch and anything newly offered get processed exactly once.
        pending = list(cont["startTasks"])
        seen_ids = {t["taskId"] for t in pending}
        while pending:
            start_task = pending.pop(0)
            task_id = start_task["taskId"]
            task_tag = list(start_task["task"].keys())[0]
            # Per-task timing kept as a permanent, low-cost diagnostic --
            # this is what actually let the sub-1s speed work identify
            # which task type dominated a tick's cost (RequestToVolatileProcess,
            # not screenshot/input), rather than guessing from the total.
            dispatch_start = time.monotonic()
            result = dispatcher.run_task(start_task["task"])
            dispatch_elapsed = time.monotonic() - dispatch_start
            # #166: a read that does not complete leaves every counter frozen
            # while the host goes on reprinting the last decision, so the log
            # reads like thousands of healthy readings. Say it instead.
            read_note = read_watch.note(read_failure_reason(task_tag, result))
            if read_note is not None:
                print(read_note, file=sys.stderr)
            # #299: a client that has lost its connection sits on a modal
            # forever, holding the install open so the launcher cannot patch.
            # The bot deliberately leaves that box alone (#185), so the host is
            # what quits it -- and it can, because a read here walks the
            # client's memory rather than asking the client anything.
            connection_lost = dispatcher.volatile.take_connection_lost()
            if connection_lost is not None:
                click_at, note = connection_lost_watch.note(*connection_lost)
                if note is not None:
                    print(note, file=sys.stderr)
                if click_at is not None:
                    for line in dispatcher.click_connection_lost_quit(click_at):
                        print(line, file=sys.stderr)
            # #310: the console names the bot, and both Windows hosts fly the
            # same one -- so two consoles are the same page twice unless they
            # also name the pilot. The title this reads is the same field the
            # ESI destination guard already refuses to route against, asked here
            # rather than at construction because it does not exist until the
            # bot's first client-list request has been answered above.
            if console is not None:
                console.note_character(esi_waypoint.character_from_window_title(
                    dispatcher.volatile.game_window_title))
            send_start = time.monotonic()
            response = send_event({"TaskCompletedEvent": {"taskId": task_id, "taskResult": result}})
            send_elapsed = time.monotonic() - send_start
            print(f"#   task {task_id}: {task_tag}  dispatch={dispatch_elapsed:.3f}s send={send_elapsed:.3f}s", file=sys.stderr)
            if "FinishSession" in response:
                break
            cont = response["ContinueSession"]
            decision_seq += 1
            log_decision(cont, decision_seq)
            # The latest ask of the tick wins, and a decision that asks for
            # nothing does not erase one that did: a cascade's later steps are
            # silent about the route while the ask still stands. Clearing is the
            # whole tick's business, above, not one decision's.
            mid_tick_destination = bot_requested_destination(cont.get("statusText"))
            if mid_tick_destination is not None:
                tick_requested_destination = mid_tick_destination
            for t in cont["startTasks"]:
                if t["taskId"] not in seen_ids:
                    pending.append(t)
                    seen_ids.add(t["taskId"])

            # #312: pause and stop are drained here as well as between ticks.
            # A tick can hold this loop for over an hour, and the outer loop's
            # drain does not run for any of it -- so the two controls an
            # operator reaches for during exactly that state were inert.
            # Neither needs the pipe, which is what makes this safe here: pause
            # sets a flag and stop sets a break, while a settings change
            # re-sends `BotSettingsChangedEvent` and so stays at the tick
            # boundary where the request/response conversation is between
            # exchanges rather than inside one.
            if console is not None:
                give_tick_back = False
                while True:
                    command = console.take_command()
                    if command is None:
                        break
                    if command == "pause":
                        console.set_paused(True)
                        give_tick_back = True
                    elif command == "resume":
                        console.set_paused(False)
                    elif command == "stop":
                        stop_requested = True
                        give_tick_back = True
                if give_tick_back:
                    # Both are answered by the outer loop -- the pause wait and
                    # the stop break both live there -- so reaching them is the
                    # whole point of not finishing the queue first.
                    break

            note = tick_bound_note(tick, time.monotonic() - tick_start,
                                   decision_seq + 1, len(pending))
            if note is not None:
                print(note, file=sys.stderr)
                if console is not None:
                    console.note_host(
                        f"tick {tick} held the loop {time.monotonic() - tick_start:.0f}s "
                        f"and was given back")
                break

        if "FinishSession" in response:
            continue

        tick += 1
        if max_ticks is not None and tick > max_ticks:
            print("# max_ticks reached, stopping", file=sys.stderr)
            break

        # The deadline is the host's to enforce, not the bot's. The bot is told
        # when the session ends and is expected to wind down and answer
        # FinishSession, but that is a decision it can fail to reach -- stuck in
        # space, unable to dock, or looping on something -- and then nothing
        # stops the run at all. Left to itself the remaining time just goes
        # negative and the session carries on indefinitely.
        #
        # Checked between ticks rather than mid-tick so a dispatched input
        # sequence finishes rather than being cut in half.
        # A bot winding down may need time the planned end does not contain --
        # a trip to its home station is a route, a warp, a jump and a dock, and
        # the mission runner budgets 420s for it. Every one of those allowances
        # was measured past the planned end and so could never be spent, because
        # this check fired first: run 17 was killed mid-trip with its own clock
        # reading 420s of headroom. So the bot may now ask, in its status text,
        # and the host grants what it asks up to a cap.
        #
        # Three properties keep this from being a bot that runs forever. It is a
        # lease renewed every tick, so a bot that stops asking -- or that hangs,
        # or crashes -- is stopped on the next one. It is capped here rather
        # than trusted. And the grant is announced, because a session quietly
        # running past its end is exactly what an operator would not think to
        # look for.
        if session_end_at_milliseconds is not None:
            overrun_seconds = (time.time() * 1000 - session_end_at_milliseconds) / 1000.0
            granted_seconds = bot_requested_overrun_seconds(cont.get("statusText"))
            if overrun_seconds > granted_seconds:
                if granted_seconds > 0:
                    print(f"# session duration elapsed {overrun_seconds:.0f}s ago, past the "
                          f"{granted_seconds:.0f}s the bot asked for -- stopping", file=sys.stderr)
                else:
                    print(f"# session duration elapsed {overrun_seconds:.0f}s ago and the bot has not "
                          f"finished the session -- stopping", file=sys.stderr)
                break
            if overrun_seconds > 0 and granted_seconds > 0 and granted_seconds != last_granted_overrun:
                print(f"# session end passed {overrun_seconds:.0f}s ago; the bot asked for "
                      f"{granted_seconds:.0f}s to finish winding down -- continuing",
                      file=sys.stderr)
                last_granted_overrun = granted_seconds

        # The route, on the same channel and for the same reason: the bot has no
        # way to spell a station name in `buildTaskFromEffectSequence`, and the
        # search bar cannot type one either -- a parenthesis has no key at all.
        #
        # Acted on only when the name *changes*, because the bot re-derives its
        # decision every reading and so asks on every reading it wants the
        # route. Setting the same destination twenty times is twenty
        # authenticated calls to CCP for one outcome. A directive that goes away
        # clears this, so the same station asked for again later is acted on
        # again rather than suppressed forever -- the lease shape #68 uses, not
        # a high-water mark.
        #
        # Between ticks, like the deadline check above, and synchronously: the
        # ESI call blocks this loop for up to its budget, so the reading the bot
        # takes next is one where the call has already finished or given up.
        # That is what makes the bot's own confirmation -- the route panel --
        # meaningful one reading later.
        #
        # Deliberately the same code as the volatile-process request answers, so
        # the two ways in cannot report a failure differently. It prints its own
        # outcome, token-free, on both paths.
        #
        # Read from the whole tick rather than from `cont`, which is only its
        # last decision -- #306, and the reason two runs on 18 Aug parked with
        # hours left while asking 21 times each.
        requested_destination = tick_requested_destination
        if requested_destination != last_requested_destination:
            last_requested_destination = requested_destination
            if requested_destination is not None:
                print(f"# the bot asked for the route to {requested_destination!r}"
                      " -- setting it through ESI", file=sys.stderr)
                dispatcher.volatile._set_autopilot_destination(
                    {"name": requested_destination})

        notify = cont.get("notifyWhenArrivedAtTime")
        if notify:
            delay = max(0, notify["timeInMilliseconds"] - int(time.time() * 1000)) / 1000
            delay = min(delay, 2.0)
            if delay > 0.01:
                print(f"#   notify-delay sleep: {delay:.3f}s", file=sys.stderr)
            time.sleep(delay)
        tick_send_start = time.monotonic()
        response = send_event({"TimeArrivedEvent": None})
        tick_send_elapsed = time.monotonic() - tick_send_start
        print(f"#   TimeArrivedEvent send: {tick_send_elapsed:.3f}s", file=sys.stderr)

    proc.stdin.close()
    proc.wait(timeout=5)


_GAME_LOG_MARKUP = re.compile(r"<[^>]*>")

# "[ 2026.08.02 23:56:34 ] (notify) You cannot launch Acolyte I because ..."
_GAME_LOG_LINE = re.compile(r"^\[ (?P<timestamp>[^\]]+?) \] \((?P<channel>[^)]*)\) (?P<text>.*)$")

# Channels the bot is deliberately *not* given. `(combat)` is per-shot and
# 4,484 of the 4,852 lines across five recorded runs -- carrying it would put
# the cost of this channel entirely in noise the decision path has no use for.
# `(bounty)` is the host's own source for kills and ISK (see the web console),
# and a second reader of the same lines in the bot would be a second source of
# truth for the same statistic. Everything else is carried, including channels
# never seen here: a channel silently dropped for being unfamiliar is this
# repo's signature failure, so the list is a deny-list rather than an allow-list.
#
# **Both withheld channels have since had their totals carried anyway, and the
# distinction is the lines against the summary.** `(combat)` was first: the
# lines are noise no decision uses and the totals are what #32 and #90 needed,
# so they ride `synthetic_incoming_damage_node` and
# `synthetic_outgoing_damage_node`. `(bounty)` is the same shape -- the count
# rides `synthetic_kills_node`, off the console's own `BOUNTY_TEXT_RE`, so the
# second-source-of-truth objection above is answered by there being one pattern
# rather than by the bot going without a kill count. Nothing about *this* list
# changes: neither channel's lines reach `entries_for_reading`.
GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT = frozenset({"combat", "bounty"})

# Incoming damage, after the markup above has been stripped:
#   "49 from Centior Monster - Penetrates"
#   "74 from Centum Fiend - Mjolnir Heavy Missile - Hits"
# Outgoing damage is the same shape with "to", and it must never be counted --
# a retreat armed by the bot's own guns would fire hardest when the fight is
# going well. Anchored on the leading number for the same reason: the only
# other `(combat)` lines carrying "from" are warp-disruption notices
# ("Warp scramble attempt from Chief Republic Isak to you!"), which name no
# damage. Across 134,641 recorded combat lines there are exactly four of those
# and none begins with a digit.
_INCOMING_DAMAGE_LINE = re.compile(r"^(?P<amount>\d+) from (?P<attacker>.+)$")

# Damage dealt, the same shape with "to":
#   "104 to Mammon Apis - Hits"
#   "0 to Infested Asteroid - Focused Modulated Medium Energy Beam I - Hits"
#   "32 to Mercenary Commander - Acolyte I - Smashes"   (a drone's hit)
# Anchored on the leading number and on " to " immediately after it, which is
# what keeps two other shapes out. `100 GJ energy neutralized Sleepless Outguard
# - Sleepless Outguard` begins with a digit and is not damage (19 of them across
# the corpus), and every `Warp disruption attempt from X - to Y` line -- which
# is the only other place " to " appears on this channel -- begins with a word.
# A miss carries no number at all and so cannot match. It is matched separately,
# by the pattern below, because a miss and a landed shot for zero are different
# facts about a target and the bot has to be able to tell them apart.
_OUTGOING_DAMAGE_LINE = re.compile(r"^(?P<amount>\d+) to (?P<target>.+)$")

# A shot of ours that missed, in the client's own two wordings:
#   "Your Hobgoblin II misses Vigilant Sentry Tower completely - Hobgoblin II"
#   "Your group of Small Focused Beam Laser II misses Hunter Alvi completely -
#    Small Focused Beam Laser II"
#
# **Three things about this pattern were measured before it was written**, over
# the 410,023 `(combat)` lines in `~/Documents/EVE/logs/Gamelogs`.
#
# It is anchored on `^Your `, which is what keeps the 139,578 *incoming* misses
# out: the client writes those as "Centior Monster misses you completely", with
# the attacker's name first and no "Your". Reading one as a shot of ours would
# build a case for immunity out of a rat that cannot hit us.
#
# The weapon is required to appear **twice** -- once before "misses" and once
# after "completely - ", matched by backreference -- rather than taking the
# target as whatever sits between the two words. The client repeats it, so the
# repetition is free evidence that the line was cut in the right place, and a
# weapon or target name that happened to contain " misses " cannot slide the
# split. All 19,894 outgoing misses in that corpus match this pattern and
# nothing else does, which is what makes the backreference a measurement rather
# than caution: 211 distinct target names, including ones carrying apostrophes
# ("Sansha's Spy") and quotes ("'Integrated' Acolyte" as the weapon).
#
# `group of` is optional because the client writes it for a grouped weapon and
# omits it for a drone; both shapes occur in the thousands.
_OUTGOING_MISS_LINE = re.compile(
    r"^Your (?:group of )?(?P<weapon>.+) misses (?P<target>.+) completely - (?P=weapon)$")

# A backstop on each queue, not a policy. Both are drained once per reading, so
# reaching either means nothing drained for a long time (a paused session, or a
# run still searching for the UI root) rather than a busy client.
GAME_LOG_QUEUE_LIMIT = 500

# What joins a wrapped entry back together. The client writes a long message
# across several physical lines and puts the "[ ts ] (channel) " prefix on the
# first alone:
#
#   [ 2026.08.04 21:43:33 ] (question) Aggression against this peaceful entity
#   may have consequences such as a standings penalty ... It is recommended
#   that you reconsider.
#   Do you wish to proceed?
#
# So a line the prefix does not match, arriving while an entry is open, is the
# rest of that entry rather than something to drop -- and dropping it is issue
# #124: run 35 carries 113 of these, and the bot got the caveat and lost the
# question on every one.
#
# **Two things about the rule were measured before it was built**, over the
# 214,630 non-blank lines in the 145 files of `~/Documents/EVE/logs/Gamelogs`.
# Not one line lacking the prefix begins with `[`, so nothing the client wraps
# can be mistaken for a new entry by the only test used to tell them apart --
# which is the half the issue flagged as unverified. And the wrapping runs
# deeper than two: 138 entries of two lines, 7 of three and 3 of four, so
# nothing here counts to a fixed number of continuations.
#
# The one shape that is *not* a continuation is the header block every file
# opens with (`----`, `Gamelog`, `Listener: X`, `Session Started: <when>`),
# four or five prefix-less lines. All 143 of them in that corpus sit above
# their file's first entry, so a rule phrased as "continues the entry above it"
# declines them by having nothing to continue. That is why it is phrased that
# way round rather than as a test on the line itself -- there is no wording
# these share that a continuation could not also have.
GAME_LOG_CONTINUATION_JOIN = " "


def parse_game_log_line(line):
    """Split one already-de-markup'd game log line into its three parts.

    Returns `None` for anything not in the client's own line shape. That covers
    two different things and the caller decides between them: the header block
    a file opens with, which is dropped, and the second and later lines of a
    wrapped entry, which belong to the entry above -- see
    `continue_game_log_entry`. A caller wanting the raw text has it already.
    """
    match = _GAME_LOG_LINE.match(line)
    if match is None:
        return None
    return {
        "timestamp": match.group("timestamp"),
        "channel": match.group("channel"),
        "text": match.group("text"),
    }


def continue_game_log_entry(entry, line):
    """Fold a wrapped line back into the entry it belongs to.

    **Appended to the entry's own text rather than carried as a field of its
    own**, and what reads it is the reason. `ParseUserInterface.elm` lifts
    exactly `timestamp`, `channel` and `text` out of the synthetic node, in six
    vendored copies that the policy says must stay identical -- so a fourth key
    is six Elm edits before any decision can see the second half of a sentence,
    where appending needs none. And every consumer of this channel is a
    substring test over `text`: `loadRefusalFromGameLog`'s two, the locked-gate
    verdict, the capsule refusal, the docking-perimeter marker. Appending can
    only make more of an entry matchable and can never stop a match that used
    to happen, which is what makes this safe for entries nobody wrapped --
    they get nothing appended, because nothing was wrapped.

    Joined with a space rather than a newline because `_poll` has already
    collapsed the whitespace inside each line, and what the client wrapped is
    one paragraph rather than two sentences -- so a space puts the entry back
    into the single-line shape every other entry already has, and keeps it out
    of the one thing a newline would cost, which is a `text` no existing
    matcher was written against.
    """
    entry["text"] = GAME_LOG_CONTINUATION_JOIN.join(
        part for part in (entry["text"], line) if part)
    return entry


def game_log_entries_from_lines(lines):
    """Every entry `lines` carries, each one read whole.

    The pure form of what `GameLogTail._poll` does as the file grows, for a
    caller that already holds the lines -- a recorded run's echo, or a whole
    file. A line the client's prefix does not match continues the entry above
    it; one with no entry above it is dropped, exactly as it always was.
    """
    entries = []
    for line in lines:
        entry = parse_game_log_line(line)
        if entry is None:
            if entries:
                continue_game_log_entry(entries[-1], line)
            continue
        entries.append(entry)
    return entries


def parse_incoming_damage(entry):
    """`(amount, attacker)` for a combat line that is damage *taken*, else None.

    The attacker is the name up to the first " - ", because the rest of the line
    is the weapon and the quality of the hit ("- Mjolnir Heavy Missile - Hits")
    and both differ per shot. A miss ("Centior Monster misses you completely")
    is deliberately not damage: it costs nothing and counting it as a hit of
    zero would only inflate the hit count.
    """
    if entry is None or entry["channel"] != "combat":
        return None
    match = _INCOMING_DAMAGE_LINE.match(entry["text"])
    if match is None:
        return None
    attacker = match.group("attacker").split(" - ")[0].strip()
    return int(match.group("amount")), (attacker or None)


def parse_outgoing_damage(entry):
    """`(amount, target)` for a combat line that is damage *dealt*, else None.

    The target is the name up to the first " - ", exactly as the attacker is on
    the incoming side, because the rest of the line is the weapon and the
    quality of the hit and both differ per shot.

    **Zero is a value here, not an absence**, which is the one way this differs
    from its incoming twin. `0 to Infested Asteroid - Hits` is a shot that
    landed and achieved nothing, and it is the single most informative line on
    this channel -- discarding it as "no damage" would throw away the whole
    signal issue #90 is about. A miss still returns `None`, because it carries
    no number and never reaches this pattern; `parse_outgoing_miss` is what
    reads one, and the two must not come to read each other's lines.
    """
    if entry is None or entry["channel"] != "combat":
        return None
    match = _OUTGOING_DAMAGE_LINE.match(entry["text"])
    if match is None:
        return None
    target = match.group("target").split(" - ")[0].strip()
    if not target:
        return None
    return int(match.group("amount")), target


def parse_outgoing_miss(entry):
    """The target of a shot of ours that missed, else None.

    Issue #267. Until it, a miss was matched nowhere: `parse_outgoing_damage`
    declines one by construction, so the bot could not tell "I am hitting this
    and achieving nothing" from "I cannot hit this at all". Those are different
    facts and only the first is evidence of immunity -- see
    `zeroDamageMemoryAfterReading` in the mission runner, which is the only
    consumer and which counts a miss **only against a target that has already
    landed a shot for zero damage**.

    **Kept as its own count rather than folded into `hits`.** Adding a miss to
    the landed-hit count would make the two indistinguishable downstream, and
    the corpus says they must not be: across 5,631 episodes in the client's own
    logs, no target that ever landed a shot for zero was later hurt, while a
    target the guns went on to hurt absorbed **702 consecutive misses** first.
    A miss predicts nothing; a landed zero predicts immunity.

    The target is taken whole rather than cut at the first " - " as the damage
    lines are, because this line's tail is the weapon the pattern has already
    matched by backreference -- there is no weapon suffix left on the name.
    """
    if entry is None or entry["channel"] != "combat":
        return None
    match = _OUTGOING_MISS_LINE.match(entry["text"])
    if match is None:
        return None
    target = match.group("target").strip()
    return target or None


def entry_is_a_bounty_payout(entry):
    """Whether this entry is the client saying a rat it paid for has died.

    One line per rat, on `(bounty)`, and the channel is checked as well as the
    wording: the same words could in principle be said on another channel, and
    a kill count built on a phrase rather than on the client's own channel
    marker is a count anything could inflate.

    **The pattern is the web console's**, imported rather than restated, because
    that console has counted kills off these lines since before the bot could
    see them and two patterns for one statistic is precisely what CLAUDE.md
    gives as the reason for withholding this channel. See `BOUNTY_TEXT_RE`.

    **A line is a kill, and that was measured rather than assumed.** Over the
    17,388 bounty lines in `~/Documents/EVE/logs/Gamelogs`, only 44 pairs are
    byte-identical to another line in the same file -- 0.25%, which is two rats
    of one type dying inside one second rather than the client writing a line
    twice. Nothing repeats more than twice. A channel that duplicated its own
    lines would show that at a very different rate.
    """
    if entry is None or entry["channel"] != "bounty":
        return False
    return web_console.BOUNTY_TEXT_RE.match(entry["text"]) is not None


class GameLogTail:
    """Follow EVE's own game log, the only timestamped record in this system.

    The bot's combat feed reads the floating combat text out of the UI tree, and
    that text lingers on screen after a fight ends -- so the status keeps
    reprinting the last exchange long after it stopped meaning anything, which
    reads as alarming when nothing is happening. It is a stale display being
    reported faithfully, not stale data.

    The client writes a real log with wall-clock timestamps
    ("[ 2026.07.31 03:56:19 ] (None) Jumping from Hedion to Amarr"), which also
    fills the gap left by this host's own log carrying no timestamps at all.

    A new file is opened per client session, so the newest one wins and is
    re-checked as we go rather than pinned at startup. On first sight of a file
    we start at its end: the point is what happened since the last decision, not
    a replay of the session so far.

    **Five readers, one file offset.** This used to serve the stderr echo
    alone, and that echo consuming the lines is precisely what kept them from
    the bot (issue #28). `_poll` is now the only thing that moves the offset,
    and it fans each line out to six independent queues -- so
    `lines_for_echo`, `entries_for_reading`, `incoming_damage_for_reading`,
    `outgoing_damage_for_reading` and `kills_for_reading` each see every line
    exactly once and none can eat another's. Adding a second caller of a
    single-cursor tail would have given whichever ran first that cycle's lines
    and the others nothing, intermittently and without a word.

    Six queues and five readers: `outgoing_damage_for_reading` drains two of
    them, the landed shots and the misses issue #267 added, because both are
    facts about the same reading's shooting and a consumer that got one without
    the other would be reading half a summary.

    Both damage queues are fed from the `(combat)` lines that the reading queue
    deliberately drops (issues #32 and #90): withholding the channel from the
    bot was right about the *lines* and wrong about the *summary*, which is a
    fact no other instrument in this system reports. They are separate queues
    rather than one because they answer opposite questions -- how hard this ship
    is being hit, and whether its own shots are achieving anything -- and a
    consumer of either must be able to find the other absent.

    The kill queue is fed the same way from the `(bounty)` lines that queue also
    drops, and for the same reason: withholding that channel was right about the
    lines and says nothing about the count. It is a third question again -- how
    many rats died -- and must be findable absent independently of the other
    two.
    """

    def __init__(self, directory):
        self.directory = os.path.expanduser(directory)
        self.path = None
        self.offset = 0
        # The entry a continuation would belong to: the last one parsed out of
        # this file, still sitting in the queue below and not yet handed to
        # anybody. Held across polls rather than only within one, because the
        # two halves of a wrapped entry are two writes and a read can land
        # between them -- an entry that arrives whole only when the poll
        # happens to catch both lines is the bug fixed here, arriving less
        # often. It is dropped the moment appending to it would be a lie:
        # `entries_for_reading` has given it away, or the file it came from is
        # no longer the one being read.
        self._entry_open = None
        self._echo_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)
        self._reading_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)
        self._damage_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)
        self._outgoing_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)
        # Misses ride in a queue of their own rather than in `_outgoing_queue`
        # with a sentinel amount, because a miss has no amount and inventing one
        # is how the two stop being distinguishable. Both are drained by
        # `outgoing_damage_for_reading`, which is the one reader of either, so
        # this is a fifth queue on the same offset rather than a fifth reader.
        self._outgoing_miss_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)
        # A sixth queue on the same offset, for the `(bounty)` lines the reading
        # queue drops. It holds nothing but a count -- the client names no
        # target on this channel -- so this is a deque of `True` rather than of
        # anything a consumer could be tempted to attribute.
        self._kill_queue = collections.deque(maxlen=GAME_LOG_QUEUE_LIMIT)

    def _newest_file(self):
        try:
            names = os.listdir(self.directory)
        except OSError:
            return None
        paths = [os.path.join(self.directory, n) for n in names if n.endswith(".txt")]
        paths = [p for p in paths if os.path.isfile(p)]
        return max(paths, key=os.path.getmtime) if paths else None

    def _poll(self):
        path = self._newest_file()
        if path is None:
            return
        if path != self.path:
            self.path = path
            self._entry_open = None
            try:
                self.offset = os.path.getsize(path)
            except OSError:
                self.offset = 0
            return
        try:
            size = os.path.getsize(path)
            # Truncated or replaced under us -- read from the top rather than
            # seeking past the end and reporting nothing forever.
            if size < self.offset:
                self.offset = 0
                # And the next lines are a file's header block rather than the
                # rest of whatever was open, which is the one case where
                # "continues the entry above it" would reach across a boundary
                # it should not.
                self._entry_open = None
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(self.offset)
                data = handle.read()
                self.offset = handle.tell()
        except OSError:
            return
        # Combat lines arrive wrapped in colour and font markup
        # ("<color=0xffcc0000><b>133</b> ... <b>Tower Sentry Gallente I</b> ...
        # - Smashes"), which is unreadable at a glance and drowns the numbers.
        for line in data.splitlines():
            line = " ".join(_GAME_LOG_MARKUP.sub("", line).split())
            if not line:
                continue
            self._echo_queue.append(line)
            entry = parse_game_log_line(line)
            if entry is None:
                # A wrapped entry's second or later line, or -- with nothing
                # open -- a header line, which is dropped as it always was.
                if self._entry_open is not None:
                    continue_game_log_entry(self._entry_open, line)
                continue
            self._entry_open = entry
            if entry["channel"] not in GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT:
                self._reading_queue.append(entry)
            # Both damage reads take the entry as its first line stands, which
            # costs nothing: no `(combat)` line wraps -- 0 of the 191,689 in
            # `~/Documents/EVE/logs/Gamelogs` -- and both patterns anchor on
            # the leading number and stop at the first " - " regardless.
            damage = parse_incoming_damage(entry)
            if damage is not None:
                self._damage_queue.append(damage)
            dealt = parse_outgoing_damage(entry)
            if dealt is not None:
                self._outgoing_queue.append(dealt)
            missed = parse_outgoing_miss(entry)
            if missed is not None:
                self._outgoing_miss_queue.append(missed)
            if entry_is_a_bounty_payout(entry):
                self._kill_queue.append(True)

    def lines_for_echo(self, limit=25):
        """The stderr/web-console echo: whole lines, capped for readability."""
        self._poll()
        lines = list(self._echo_queue)
        self._echo_queue.clear()
        if len(lines) > limit:
            lines = [f"({len(lines) - limit} earlier lines not shown)"] + lines[-limit:]
        return lines

    def entries_for_reading(self):
        """What the client said since the last reading, for the bot.

        Split into `timestamp`/`channel`/`text` here rather than in Elm, since
        the regex belongs beside the markup stripping that produced the line.
        No cap and no placeholder line: a "(N earlier lines not shown)" marker
        is fine in a log a human reads and would be a fabricated game log entry
        in a channel a decision branches on.

        **An entry is handed over as it stands and never held back for a
        continuation that may be coming.** The alternative -- keep the last
        entry until the line after it proves it complete -- would delay every
        refusal by however long the client stays quiet, and a refusal read a
        reading late is the failure this channel exists to end. The price is
        stated rather than hidden: a wrapped entry whose halves fall either
        side of a drain is delivered as its first half, and its second half is
        dropped rather than becoming an entry of its own.
        """
        self._poll()
        entries = list(self._reading_queue)
        self._reading_queue.clear()
        self._entry_open = None
        return entries

    def incoming_damage_for_reading(self):
        """How hard the client says we were hit since the last reading.

        `{"damage": total, "hits": count, "topAttacker": name or None}` --
        the attacker being whichever name did the most damage in this reading,
        so a decision log can name what is shooting without carrying a list.

        Zero is an answer, not an absence: a reading with no incoming fire
        returns `{"damage": 0, "hits": 0, "topAttacker": None}`, and the caller
        turns *that* into a node. The distinction the bot needs -- "the client
        reported nothing" against "nothing is reporting" -- lives in whether
        the node exists at all, which is the same rule the game log follows.
        """
        self._poll()
        events = list(self._damage_queue)
        self._damage_queue.clear()
        by_attacker = collections.Counter()
        for amount, attacker in events:
            if attacker is not None:
                by_attacker[attacker] += amount
        return {
            "damage": sum(amount for amount, _ in events),
            "hits": len(events),
            "topAttacker": by_attacker.most_common(1)[0][0] if by_attacker else None,
        }

    def outgoing_damage_for_reading(self):
        """What this ship's shots achieved since the last reading, per target.

        A list of `{"name": …, "hits": N, "damage": N, "misses": N}`, one entry
        per target the client named, ordered by shots and then by name so two
        identical readings produce two identical nodes.

        **`hits` counts shots that landed, and a landed shot for zero damage is
        counted.** That is the distinction the whole of issue #90 rests on: so
        `hits > 0` with `damage = 0` means the guns are hitting an object they
        cannot hurt, which is what run 27 did for roughly 290 readings while the
        mission objective was already finished.

        **`misses` counts shots that did not land, and is a separate number for
        a measured reason** (issue #267). Summing the two would make the bot
        unable to tell an object it cannot hurt from one it cannot hit, and the
        corpus says those are opposite signals: no target in it that landed a
        shot for zero was ever hurt afterwards, while targets the guns went on
        to kill absorbed runs of up to 702 consecutive misses first. A miss is
        therefore carried so a decision *can* read it, and the only rule that
        does counts one only against a target already landing zeros.

        A target may appear with `hits = 0` and `misses > 0`: a reading in which
        every shot at it missed. That is an answer and not an absence, and the
        rule that reads it declines to build any case on it.

        An empty list is an answer -- the client reported nothing landing and
        nothing missing this reading -- and the caller turns it into a node all
        the same. "Nothing is reporting" lives in whether the node exists at
        all, the same rule the rest of this channel follows, and here reading
        the second as the first would have a bot conclude every target is immune
        on a host that simply has no game log.
        """
        self._poll()
        events = list(self._outgoing_queue)
        self._outgoing_queue.clear()
        missed = list(self._outgoing_miss_queue)
        self._outgoing_miss_queue.clear()
        hits = collections.Counter()
        damage = collections.Counter()
        misses = collections.Counter()
        for amount, target in events:
            hits[target] += 1
            damage[target] += amount
        for target in missed:
            misses[target] += 1
        names = set(hits) | set(misses)
        return [
            {"name": name, "hits": hits[name], "damage": damage[name],
             "misses": misses[name]}
            for name in sorted(names, key=lambda name: (-(hits[name] + misses[name]), name))
        ]

    def kills_for_reading(self):
        """How many rats the client paid a bounty for since the last reading.

        One number and nothing else, because the channel says nothing else --
        see `synthetic_kills_node` for what the number may and may not be read
        as. Zero is an answer, not an absence, and the caller turns it into a
        node all the same; "nothing is reporting" lives in whether the node
        exists at all, which is the rule every other reader of this file
        follows.

        The ISK is deliberately not carried. The console already reports it off
        the same lines and a bot that carried it would have a second field
        nothing decides on, on a channel this repo withheld precisely to avoid a
        second source of truth for one statistic.
        """
        self._poll()
        kills = len(self._kill_queue)
        self._kill_queue.clear()
        return kills


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bot_source", help="GitHub URL (repo or .../tree/<branch>/<subpath>) or a local file/directory path")
    ap.add_argument("--settings", default="",
                     help="the bot's own settings string, one 'key=value' per line. Which keys a "
                          "bot accepts is up to that bot (its parseBotSettings); see the "
                          "'Configuration Settings' section of its Bot.elm header.")
    ap.add_argument("--max-ticks", type=int, default=None,
                     help="stop after this many decision cycles instead of running until "
                          "interrupted. Useful for a short dry run.")
    ap.add_argument("--keep-build-dir", action="store_true",
                     help="keep the temporary directory holding the fetched bot source and the "
                          "compiled bot, instead of deleting it on exit")
    ap.add_argument("--execute-input", action="store_true",
                     help="actually send mouse/keyboard input via CGEventPost (off by default: logs what would be sent instead)")
    ap.add_argument("--capture-screenshots", action="store_true",
                     help="capture real screenshot pixel data for ReadFromWindowMethod (off by default: ~1.6s/cycle cost most bots don't need; see CLAUDE.md)")
    ap.add_argument("--game-log-dir",
                    default=(win_platform.game_log_directory() if IS_WINDOWS
                             else "~/Documents/EVE/logs/Gamelogs"),
                    help="EVE's own game log directory; its newest file is followed, echoed "
                         "under each decision (it is the only timestamped record here) and "
                         "carried into each reading for the bot to parse")
    ap.add_argument("--no-game-log", action="store_true",
                    help="do not follow EVE's game log -- no echo, and no game log in the "
                         "reading, which a bot reads as the channel being absent rather than "
                         "as the client having said nothing")
    ap.add_argument("--web-console", nargs="?", const=8787, type=int, default=None,
                    metavar="PORT",
                    help="serve a status/log/settings console on the tailnet (default port "
                         "8787). Bound to this machine's Tailscale address and nowhere else; "
                         "if there is no tailnet address the run refuses to start rather than "
                         "falling back to a wider interface.")
    ap.add_argument("--session-duration-minutes", type=float, default=None,
                     help="tell the bot how long this session should run; BotFramework's own "
                          "continueIfShouldHide docks (and stays docked) once ~200s remain "
                          "(see secondsToSessionEnd in EveOnline/BotFramework.elm). Unset by "
                          "default: no session end, the bot runs indefinitely.")
    args = ap.parse_args()

    workdir = tempfile.mkdtemp(prefix="botlab-host-")
    try:
        bot_dir = fetch_bot_source(args.bot_source, workdir)
        bot_app_name = os.path.basename(os.path.normpath(bot_dir))
        bot_version = bot_source_version(bot_dir)
        print(f"# bot source: {bot_dir}", file=sys.stderr)
        # Beside the path rather than only in the console: the path never
        # changes and the log is where "which code did this run fly" gets asked
        # afterwards, long after any console has been closed.
        print(f"# bot version: {bot_version}", file=sys.stderr)
        build_dir = prepare_build_dir(bot_dir, workdir)
        bot_js = compile_bot(build_dir)
        print(f"# compiled: {bot_js}", file=sys.stderr)
        console = None
        if args.web_console is not None:
            session_end_at_ms = None
            if args.session_duration_minutes is not None:
                session_end_at_ms = int(time.time() * 1000) + int(args.session_duration_minutes * 60 * 1000)
            console = web_console.ConsoleState(settings_text=args.settings,
                                               session_end_at_ms=session_end_at_ms,
                                               app_name=bot_app_name,
                                               bot_source=bot_dir,
                                               version=bot_version)
            try:
                _httpd, url = web_console.start(console, port=args.web_console)
                print(f"# web console: {url}", file=sys.stderr)
            except web_console.NoTailnet as exc:
                # The console is a convenience; the run is the point. Since
                # run_mission.sh passes --web-console by default, a tailnet that
                # happens to be down would otherwise abort every run here --
                # after compiling, before a single decision. Refusing to bind
                # anywhere else is the safety property and it still holds: we
                # simply do without the console.
                #
                # Loudly, though. A console silently absent is worse than no
                # console, because the operator goes looking for one.
                print(f"# WEB CONSOLE NOT STARTED: {exc}", file=sys.stderr)
                print("# the run continues without it -- no settings box, no "
                      "remote pause/stop", file=sys.stderr)
                console = None
        run_bot(bot_js, args.settings, max_ticks=args.max_ticks, execute_input=args.execute_input,
                capture_screenshots=args.capture_screenshots,
                session_duration_minutes=args.session_duration_minutes,
            game_log_dir=None if args.no_game_log else args.game_log_dir,
            console=console)
    finally:
        if args.keep_build_dir:
            print(f"# left build dir at {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
