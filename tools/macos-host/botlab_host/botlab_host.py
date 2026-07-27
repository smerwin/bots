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

    def _search_ui_root_worker(self, process_id, state):
        """One-time cost: take a real dump (the only way to repr-scan for
        the root object's address), find it, then all later ReadFromWindow
        calls use the fast LiveSample path -- no more dumps needed."""
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
                state["result"] = root
        except Exception as exc:
            print(f"# SearchUIRootAddress failed: {exc}", file=sys.stderr)
            state["result"] = None

    @staticmethod
    def _any_seed_addr(sample):
        hits = rh.repr_scan(sample, limit=1)
        for addrs in hits.values():
            if addrs:
                return addrs[0]
        raise RuntimeError("no repr-scan hits at all in this dump; can't bootstrap metatype")

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
        tree = tree_walker.tree(root_addr, metatype, str_type, max_depth=16, max_nodes=5000)
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
        for item in items:
            (tag, payload), = item.items()
            try:
                if tag == "WaitMilliseconds":
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
                        self._cg(f"move {x/scale_x:.1f} {y/scale_y:.1f}")
                    elif tag == "MouseMoveRelative":
                        errors.append("MouseMoveRelative not supported (Windows-relative semantics not implemented)")
                        continue
                    elif tag == "ButtonDown":
                        self._cg(f"down {vk_to_mouse_button(payload)}")
                    elif tag == "ButtonUp":
                        self._cg(f"up {vk_to_mouse_button(payload)}")
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

def run_bot(bot_js_path, settings, max_ticks=None, execute_input=False, capture_screenshots=False):
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
    tick = 0
    tick_start = time.monotonic()
    while True:
        if "FinishSession" in response:
            print(f"# FinishSession: {response['FinishSession']['statusText']}", file=sys.stderr)
            break

        cont = response["ContinueSession"]
        tick_elapsed = time.monotonic() - tick_start
        print(f"# [{tick}] ({tick_elapsed:.3f}s) {cont['statusText'][:2000]}", file=sys.stderr)
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
    ap.add_argument("--settings", default="")
    ap.add_argument("--max-ticks", type=int, default=None)
    ap.add_argument("--keep-build-dir", action="store_true")
    ap.add_argument("--execute-input", action="store_true",
                     help="actually send mouse/keyboard input via CGEventPost (off by default: logs what would be sent instead)")
    ap.add_argument("--capture-screenshots", action="store_true",
                     help="capture real screenshot pixel data for ReadFromWindowMethod (off by default: ~1.6s/cycle cost most bots don't need; see CLAUDE.md)")
    args = ap.parse_args()

    workdir = tempfile.mkdtemp(prefix="botlab-host-")
    try:
        bot_dir = fetch_bot_source(args.bot_source, workdir)
        print(f"# bot source: {bot_dir}", file=sys.stderr)
        build_dir = prepare_build_dir(bot_dir, workdir)
        bot_js = compile_bot(build_dir)
        print(f"# compiled: {bot_js}", file=sys.stderr)
        run_bot(bot_js, args.settings, max_ticks=args.max_ticks, execute_input=args.execute_input,
                capture_screenshots=args.capture_screenshots)
    finally:
        if args.keep_build_dir:
            print(f"# left build dir at {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
