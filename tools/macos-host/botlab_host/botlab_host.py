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

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "re_helper"))
import re_helper as rh  # noqa: E402

MAIN_ELM_TEMPLATE = os.path.join(HERE, "Main.elm")
DRIVER_JS = os.path.join(HERE, "driver.js")
MEMORY_SAMPLE_BIN = os.path.join(MACOS_HOST_DIR, "memory_sample", "memory_sample")
WINDOW_PROBE_BIN = os.path.join(MACOS_HOST_DIR, "window_probe", "window_probe")
CG_INPUT_BIN = os.path.join(MACOS_HOST_DIR, "cg_input", "cg_input")
TREE_WALKER_BIN = os.path.join(MACOS_HOST_DIR, "tree_walker", "tree_walker")

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
    vs ~0.4s C for the same ~2800-node live tree)."""

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

_VK_TO_CGKEYCODE = {
    0x08: 0x33,  # BACK -> Delete (backspace)
    0x09: 0x30,  # TAB
    0x0D: 0x24,  # RETURN
    0x10: 0x38,  # SHIFT
    0x11: 0x3B,  # CONTROL
    0x12: 0x3A,  # ALT/MENU -> Option
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
    return _VK_TO_CGKEYCODE.get(vk)


def vk_to_mouse_button(vk):
    """VK_LBUTTON=0x01, VK_RBUTTON=0x02, VK_MBUTTON=0x04 -> cg_input's
    0=left/1=right/2=other."""
    if vk == 0x02:
        return 1
    if vk == 0x04:
        return 2
    return 0


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
# Build: patch elm.json, add Main.elm, compile
# ---------------------------------------------------------------------------

def installed_elm_version():
    out = subprocess.run(["elm", "--version"], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def prepare_build_dir(bot_dir, workdir):
    build_dir = os.path.join(workdir, "build")
    shutil.copytree(bot_dir, build_dir)

    elm_json_path = os.path.join(build_dir, "elm.json")
    with open(elm_json_path) as f:
        elm_json = json.load(f)
    real_version = installed_elm_version()
    if elm_json.get("elm-version") != real_version:
        print(f"# patching elm.json elm-version {elm_json.get('elm-version')!r} -> {real_version!r}", file=sys.stderr)
        elm_json["elm-version"] = real_version
        with open(elm_json_path, "w") as f:
            json.dump(elm_json, f, indent=4)

    shutil.copy(MAIN_ELM_TEMPLATE, os.path.join(build_dir, "Main.elm"))
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


def capture_image_data(window_number, scaled_rect, scale_x, scale_y):
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

class VolatileHost:
    def __init__(self):
        self.roots = {}          # processId -> ui root address (int)
        self.root_search = {}    # processId -> {"begin": ms, "thread": Thread, "result": addr|None|"pending"}
        self.metatype = {}       # processId -> metatype addr
        self.str_type = {}       # processId -> str type addr
        self.live = {}           # processId -> LiveSample (kept for root-finding bootstrap only now)
        self.tree_walkers = {}   # processId -> TreeWalkerClient (the fast, native ReadFromWindow path)
        self.root_display_size = {}  # processId -> (width, height) in "game pixel" units, from UIRoot's own _displayWidth/_displayHeight
        self.game_pid = None

    def _get_live(self, process_id):
        live = self.live.get(process_id)
        if live is None:
            live = rh.LiveSample(process_id)
            self.live[process_id] = live
        return live

    def _get_tree_walker(self, process_id):
        client = self.tree_walkers.get(process_id)
        if client is None:
            client = TreeWalkerClient(process_id)
            self.tree_walkers[process_id] = client
        return client

    def handle_request(self, request_json_str):
        req = json.loads(request_json_str)
        if "ListGameClientProcessesRequest" in req:
            procs = find_eve_processes()
            if procs:
                self.game_pid = procs[0]["processId"]
            return json.dumps({"ListGameClientProcessesResponse": procs})

        if "SearchUIRootAddress" in req:
            process_id = req["SearchUIRootAddress"]["processId"]
            return json.dumps({"SearchUIRootAddressResponse": self._search_ui_root(process_id)})

        if "ReadFromWindow" in req:
            body = req["ReadFromWindow"]
            return json.dumps({"ReadFromWindowResult": self._read_from_window(body)})

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
            with open(self.UI_ROOT_CACHE_PATH) as cache_file:
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
            with open(self.UI_ROOT_CACHE_PATH, "w") as cache_file:
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
        entries = tree.get("dictEntriesOfInterest", {})
        w, h = entries.get("_displayWidth"), entries.get("_displayHeight")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w > 0 and h > 0:
            self.root_display_size[process_id] = (w, h)
        return {
            "Completed": {
                "processId": process_id,
                "readingId": f"reading-{int(time.time()*1000)}",
                "memoryReadingSerialRepresentationJson": json.dumps(tree),
            }
        }


# ---------------------------------------------------------------------------
# Task dispatch (top-level BotLab.BotInterface_To_Host_2024_10_19.Task)
# ---------------------------------------------------------------------------

class TaskDispatcher:
    def __init__(self, execute_input=False, capture_screenshots=False):
        self.volatile = VolatileHost()
        self._process_ids = {}
        self.execute_input = execute_input
        self.capture_screenshots = capture_screenshots
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._cg_input = None
        # Mouse buttons currently held, so cursor motion between a ButtonDown
        # and its ButtonUp is emitted as a drag rather than a plain move.
        self._buttons_down = set()
        self._last_mouse_pos = None

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

    @staticmethod
    def _unwrap_request_considering_focus(payload):
        (tag, inner), = payload.items()
        if tag == "RequestNotRequiringInputFocus":
            return inner
        return inner["request"]

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
            if root_size:
                scale_x = root_size[0] / point_w
                scale_y = root_size[1] / point_h
            else:
                # first call, before any ReadFromWindow has populated
                # root_display_size yet: fall back to the OS backing scale
                scale_x = scale_y = rect["backing_scale"]
            self._scale_x, self._scale_y = scale_x, scale_y
            scaled_rect = {
                "left": int(rect["left"] * scale_x), "top": int(rect["top"] * scale_y),
                "right": int(rect["right"] * scale_x), "bottom": int(rect["bottom"] * scale_y),
            }
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
                "imageData": (capture_image_data(window_number, scaled_rect, scale_x, scale_y)
                              if self.capture_screenshots else
                              {"screenshotCrops_original": [], "screenshotCrops_binned_2x2": [], "screenshotCrops_binned_4x4": []}),
            }
            return {"InvokeMethodOnWindowResponse": [window_id, {"Ok": {"ReadFromWindowMethodResult": result}}]}
        if mtag == "CloseWindowMethod":
            return {"InvokeMethodOnWindowResponse": [window_id, {"Ok": {"InvokeMethodOnWindowResultWithoutValue": True}}]}
        return {"InvokeMethodOnWindowResponse": [window_id, {"Err": {"MethodNotAvailableError": True}}]}

    def _get_cg_input(self):
        if self._cg_input is None or self._cg_input.poll() is not None:
            self._cg_input = subprocess.Popen(
                [CG_INPUT_BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
            )
        return self._cg_input

    def _cg(self, cmd):
        proc = self._get_cg_input()
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()
        return proc.stdout.readline().strip()

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
        for i in range(1, steps):
            t = i / steps
            self._cg_move(start_x + (target_x - start_x) * t, start_y + (target_y - start_y) * t)
            time.sleep(step_delay)
        self._cg_move(target_x, target_y)
        self._last_mouse_pos = (target_x, target_y)

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

        scale_x = self._scale_x or 1.0
        scale_y = self._scale_y or 1.0
        completed = 0
        errors = []
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
                    if (not self._buttons_down) or next_real_tag_after_wait == "ButtonUp":
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
                    elif tag == "KeyUp":
                        code, extended = payload
                        mac_code = vk_to_cgkeycode(code)
                        if mac_code is None:
                            errors.append(f"no macOS key mapping for VK code {code}")
                            continue
                        self._cg(f"keyup {mac_code}")
                    elif tag in ("CharacterDown", "CharacterUp"):
                        errors.append(f"{tag} (raw unicode character input) not implemented")
                        continue
                else:
                    errors.append(f"unhandled WindowsInputSequenceItem: {tag}")
                    continue
                completed += 1
            except Exception as exc:
                errors.append(f"{tag}: {exc}")

        return {
            "WindowsInputResponse": {
                "completedStepsCount": completed,
                "abortedStepsCount": len(items) - completed,
                "totalTimeMilliseconds": int((time.time() - start) * 1000),
                "errorMessages": errors,
            }
        }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_bot(bot_js_path, settings, max_ticks=None, execute_input=False, capture_screenshots=False,
            session_duration_minutes=None):
    proc = subprocess.Popen(
        ["node", DRIVER_JS, bot_js_path],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr,
        text=True, bufsize=1,
    )
    dispatcher = TaskDispatcher(execute_input=execute_input, capture_screenshots=capture_screenshots)

    def send_event(event_at_time):
        event = {"timeInMilliseconds": int(time.time() * 1000), "eventAtTime": event_at_time}
        proc.stdin.write(json.dumps(event) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("bot process exited")
        return json.loads(line)

    response = send_event({"BotSettingsChangedEvent": settings or ""})

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

    tick = 0
    tick_start = time.monotonic()

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
        print(f"# [{tick}.{decision_seq}] ({elapsed:.3f}s) {cont['statusText'][:4000]}", file=sys.stderr)

    while True:
        if "FinishSession" in response:
            print(f"# FinishSession: {response['FinishSession']['statusText']}", file=sys.stderr)
            break

        cont = response["ContinueSession"]
        decision_seq = 0
        log_decision(cont, decision_seq)
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
            send_start = time.monotonic()
            response = send_event({"TaskCompletedEvent": {"taskId": task_id, "taskResult": result}})
            send_elapsed = time.monotonic() - send_start
            print(f"#   task {task_id}: {task_tag}  dispatch={dispatch_elapsed:.3f}s send={send_elapsed:.3f}s", file=sys.stderr)
            if "FinishSession" in response:
                break
            cont = response["ContinueSession"]
            decision_seq += 1
            log_decision(cont, decision_seq)
            for t in cont["startTasks"]:
                if t["taskId"] not in seen_ids:
                    pending.append(t)
                    seen_ids.add(t["taskId"])

        if "FinishSession" in response:
            continue

        tick += 1
        if max_ticks is not None and tick > max_ticks:
            print("# max_ticks reached, stopping", file=sys.stderr)
            break

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
    ap.add_argument("--session-duration-minutes", type=float, default=None,
                     help="tell the bot how long this session should run; BotFramework's own "
                          "continueIfShouldHide docks (and stays docked) once ~200s remain "
                          "(see secondsToSessionEnd in EveOnline/BotFramework.elm). Unset by "
                          "default: no session end, the bot runs indefinitely.")
    args = ap.parse_args()

    workdir = tempfile.mkdtemp(prefix="botlab-host-")
    try:
        bot_dir = fetch_bot_source(args.bot_source, workdir)
        print(f"# bot source: {bot_dir}", file=sys.stderr)
        build_dir = prepare_build_dir(bot_dir, workdir)
        bot_js = compile_bot(build_dir)
        print(f"# compiled: {bot_js}", file=sys.stderr)
        run_bot(bot_js, args.settings, max_ticks=args.max_ticks, execute_input=args.execute_input,
                capture_screenshots=args.capture_screenshots,
                session_duration_minutes=args.session_duration_minutes)
    finally:
        if args.keep_build_dir:
            print(f"# left build dir at {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
