#!/usr/bin/env python3
"""Set the in-game autopilot route from a chat channel's MOTD (e.g. the
corp channel), by clicking the system-name links embedded in the MOTD
text exactly the way a player would: right-click each system link in
order, choosing "Set Destination" for the first one and "Add Waypoint"
for the rest.

Usage:
    python3 route_setter.py [--pid PID] [--channel corp] [--dry-run]

--dry-run right-clicks each system link, verifies it (see below), and
closes the menu with Escape instead of clicking "Set Destination"/"Add
Waypoint" -- use it to sanity-check parsing and click-targeting without
touching the character's actual route.

Where this came from / status:
    Built during a live session (see CLAUDE.md) that worked out, in
    order: (1) that EVE's own UI display-region math
    (ParseUserInterface.elm's totalDisplayRegion) is just a cumulative
    sum of each node's own _displayX/_displayY down the ancestor chain
    -- confirmed by reading the Elm source, not guessed; (2) that a
    corp/channel MOTD is posted as an ordinary rich-text chat message
    (a "EVE System > Channel MOTD: ..." line), not a separate popup --
    its system-name links are <a href="showinfo:5//<solarSystemID>">
    links baked into one Label's _setText, not separate child UI nodes,
    so there's no exact per-link display region to read the way there
    is for a button; and (3) that cg_input MUST be kept as a single
    persistent process across a move+down+up sequence -- it tracks the
    click position as process-local state set by the last "move", so a
    fresh process per command always clicks at (0, 0), which looked
    like the OS cursor teleporting to the top-left corner.

    Because a link's exact position inside the packed MOTD text can't
    be read directly, this locates each one by calibrated trial: right-
    click a y offset inside the MOTD label, read back the resulting
    context menu's entries (which name the system explicitly, e.g.
    "Avoid Hamse (Solar System)"), and adjust up/down by the measured
    per-line height until the right system is confirmed -- self-
    correcting rather than relying on getting the line math right by
    construction. This calibration loop is implemented but has only
    been smoke-tested for the coordinate math and menu-reading pieces
    individually this session, not run start-to-finish against a real
    multi-system route -- treat a first real run as a trial, watch it,
    and keep --dry-run handy.

    The screen-coordinate conversion follows reload_drones.py's
    approach (scale by window-points / UIRoot's own _displayWidth,
    _displayHeight -- NOT a fixed Retina backing-scale factor), which
    is the validated-correct one; an earlier draft of this tool used a
    hardcoded backing_scale=2.0 guess that was measurably wrong (UIRoot
    reported a 2880x1863 canvas against a 1710x1069-point window, i.e.
    sx=0.594 -- not 0.5) and only produced an on-target click once, by
    luck within the click-verify loop's tolerance, not because the math
    was right.
"""

import argparse
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "re_helper"))
import re_helper as rh  # noqa: E402

MEMORY_SAMPLE_BIN = os.path.join(MACOS_HOST_DIR, "memory_sample", "memory_sample")
WINDOW_PROBE_BIN = os.path.join(MACOS_HOST_DIR, "window_probe", "window_probe")
CG_INPUT_BIN = os.path.join(MACOS_HOST_DIR, "cg_input", "cg_input")
TREE_WALKER_BIN = os.path.join(MACOS_HOST_DIR, "tree_walker", "tree_walker")

VK_ESCAPE = 0x35  # macOS CGKeyCode


# ---------------------------------------------------------------------------
# Persistent input
# ---------------------------------------------------------------------------

class CgInput:
    """Persistent cg_input process. Must stay persistent across a whole
    move/down/up sequence -- cg_input tracks the click position as static
    state inside the process, only updated by "move"; spawning a fresh
    process per command always clicks at (0, 0) (see module docstring)."""

    BUTTON_LEFT = 0
    BUTTON_RIGHT = 1

    def __init__(self):
        self.proc = subprocess.Popen(
            [CG_INPUT_BIN], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _cmd(self, line):
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        resp = self.proc.stdout.readline()
        if not resp.startswith("ok"):
            raise RuntimeError(f"cg_input error for {line!r}: {resp!r}")
        return resp

    def move(self, x, y):
        return self._cmd(f"move {x} {y}")

    def down(self, button):
        return self._cmd(f"down {button}")

    def up(self, button):
        return self._cmd(f"up {button}")

    def key(self, code):
        self._cmd(f"keydown {code}")
        self._cmd(f"keyup {code}")

    def click(self, x, y, button=BUTTON_LEFT, settle=0.15):
        self.move(x, y)
        time.sleep(settle)
        self.down(button)
        time.sleep(0.08)
        self.up(button)

    def close(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=2)


def activate_game(pid):
    """Bring the game process frontmost. Clicks are routed by cursor
    position regardless of frontmost app, but keyboard events (Escape to
    close a menu) go to whichever app has focus."""
    subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to set frontmost of first '
         f'process whose unix id is {pid} to true'],
        check=True, capture_output=True,
    )


def window_bounds(pid):
    """Real on-screen bounds (points) of the game's largest window, e.g.
    for a fullscreen client. Picks the LARGEST by area among the pid's
    windows, not just the first one over a width threshold -- a
    fullscreen game window can have a smaller overlay window at the same
    width (the reveal-on-hover menu-bar strip, ~1710x44) that would
    otherwise be picked by accident since it also clears a naive width
    check. Found live: an earlier width-only version of this function
    picked that 44-point-tall strip, producing a badly wrong y-scale
    factor and a bogus click target -- see find_eve_processes in
    botlab_host.py, which already has this exact fix, for the same
    reasoning applied to the real bot's own window resolution."""
    out = subprocess.run([WINDOW_PROBE_BIN, "--all"], check=True,
                          capture_output=True, text=True).stdout
    best = None
    for line in out.splitlines():
        if f"owner_pid={pid}" not in line:
            continue
        m = re.search(r"bounds=\{x=([\-0-9.]+) y=([\-0-9.]+) w=([\-0-9.]+) h=([\-0-9.]+)\}", line)
        if not m:
            continue
        x, y, w, h = (float(v) for v in m.groups())
        if best is None or w * h > best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        raise RuntimeError(f"no window found for pid {pid}")
    return best


# ---------------------------------------------------------------------------
# Memory bootstrap (root/metatype/str_type) + fast live tree reads
# ---------------------------------------------------------------------------

def find_valid_seed_addr(sample):
    """Pick a repr-scanned address that actually resolves to a valid
    CPython type/metatype, instead of trusting the first hit blindly.

    The repr text this scans (EVE's own "<ClassName object at 0X...>"
    debug-log lines) can outlive the object it describes -- UI widgets
    get destroyed/recreated constantly, so the address in an old log
    line can point at freed/reused memory by the time a dump is taken.
    Observed live: this broke SearchUIRootAddress in botlab_host.py
    outright (see its _any_seed_addr, fixed the same way) even though
    the same dump had plenty of other valid candidates -- of 165 hits
    in one real dump, 146 were valid and only 19 (including the unlucky
    first one) were stale."""
    hits = rh.repr_scan(sample, limit=200)
    for addrs in hits.values():
        for addr in addrs:
            metatype = rh.find_metatype(sample, addr)
            if metatype is not None and sample.read_u64(metatype + 8) == metatype:
                return addr
    raise RuntimeError("no repr-scan hit in this dump resolved to a valid metatype")


def bootstrap_str_type(sample, metatype):
    hits = rh.repr_scan(sample, limit=200)
    seen = set()
    for addrs in hits.values():
        for addr in addrs:
            if addr in seen:
                continue
            seen.add(addr)
            d = rh.get_dict(sample, addr, metatype)
            if d is None:
                continue
            st = rh.bootstrap_str_type(sample, d, metatype)
            if st:
                return st
    raise RuntimeError("could not bootstrap str type")


class TreeWalker:
    """Persistent tree_walker process -- the fast (C, in-process) live UI
    tree reader; see CLAUDE.md for why this exists (~5x faster than the
    pure-Python re_helper.build_tree path for repeated reads, which this
    tool needs one of per system while calibrating link positions)."""

    def __init__(self, pid):
        self.proc = subprocess.Popen(
            [TREE_WALKER_BIN, str(pid)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        ready = self.proc.stderr.readline()
        if b"ready" not in ready:
            raise RuntimeError(f"tree_walker failed to start: {ready!r}")

    def tree(self, root_addr, metatype_addr, str_type_addr, max_depth=16, max_nodes=6000):
        req = struct.pack("<QQQII", root_addr, metatype_addr, str_type_addr, max_depth, max_nodes)
        self.proc.stdin.write(req)
        self.proc.stdin.flush()
        len_b = self.proc.stdout.read(8)
        if len(len_b) < 8:
            raise RuntimeError("tree_walker: short read (died?)")
        (length,) = struct.unpack("<Q", len_b)
        data = bytearray()
        while len(data) < length:
            chunk = self.proc.stdout.read(length - len(data))
            if not chunk:
                raise RuntimeError("tree_walker: short read on body")
            data.extend(chunk)
        tree = json.loads(data)
        annotate_regions(tree)
        return tree

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            # Seen live: a tree_walker request can occasionally take far
            # longer than normal (observed once, ~90s for an otherwise
            # ordinary-sized tree, cause unconfirmed) -- if it's still
            # mid-request when we want to stop, closing stdin alone won't
            # interrupt it. Escalate rather than leave a runaway process
            # burning CPU in the background.
            self.proc.kill()
            self.proc.wait(timeout=5)


def bootstrap(pid):
    """One-time cost: dump the process, find UI root + metatype + str
    type, and the root's own virtual-canvas size (needed for the
    game-pixel -> real-screen-point scale, see build_scale). Returns
    (tree_walker, root, metatype, str_type, root_w, root_h)."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([MEMORY_SAMPLE_BIN, str(pid), d], check=True, capture_output=True)
        sample = rh.Sample(d)
        seed = find_valid_seed_addr(sample)
        metatype = rh.find_metatype(sample, seed)
        str_type = bootstrap_str_type(sample, metatype)
        root = rh.find_ui_root(sample, metatype, str_type)
        if root is None:
            raise RuntimeError("could not find UI root")

    tw = TreeWalker(pid)
    root_tree = tw.tree(root, metatype, str_type, max_depth=1, max_nodes=1)
    de = root_tree.get("dictEntriesOfInterest", {})
    root_w, root_h = de.get("_displayWidth"), de.get("_displayHeight")
    return tw, root, metatype, str_type, root_w, root_h


def build_scale(root_w, root_h, win_bounds):
    """EVE's internal UI coordinates (_displayX/_displayY) are laid out
    against UIRoot's own virtual-canvas size (root_w x root_h) -- NOT the
    window's point size or its Retina backing-pixel size. This is the
    validated-correct scale (see reload_drones.py, and the module
    docstring above for why an earlier backing_scale=2.0 guess was
    wrong)."""
    win_x, win_y, win_w, win_h = win_bounds
    return win_w / root_w, win_h / root_h, win_x, win_y


def game_to_global(gx, gy, scale):
    sx, sy, win_x, win_y = scale
    return win_x + gx * sx, win_y + gy * sy


# ---------------------------------------------------------------------------
# UI tree helpers
# ---------------------------------------------------------------------------

def annotate_regions(node, offset=(0, 0)):
    """Attach 'region': {x,y,w,h} (cumulative _displayX/_displayY, i.e.
    ParseUserInterface.elm's totalDisplayRegion) to every node in place."""
    de = node.get("dictEntriesOfInterest", {})
    dx, dy = de.get("_displayX"), de.get("_displayY")
    dw, dh = de.get("_displayWidth"), de.get("_displayHeight")
    if all(isinstance(v, (int, float)) for v in (dx, dy, dw, dh)):
        total = (offset[0] + dx, offset[1] + dy)
        node["region"] = {"x": total[0], "y": total[1], "w": dw, "h": dh}
        child_offset = total
    else:
        node["region"] = None
        child_offset = offset
    for c in node.get("children", []) or []:
        annotate_regions(c, child_offset)
    return node


def find_all(node, pred):
    if pred(node):
        yield node
    for c in node.get("children", []) or []:
        yield from find_all(c, pred)


def find_by_type(node, type_name):
    return list(find_all(node, lambda n: n.get("pythonObjectTypeName") == type_name))


def get_display_text(node):
    de = node.get("dictEntriesOfInterest", {}) or {}
    for key in ("_setText", "_text"):
        v = de.get(key)
        if isinstance(v, str):
            return v
    return None


def find_chat_window(tree, channel_category):
    """XmppChatWindow whose channelCategory matches (e.g. "corp", "local")."""
    for n in find_all(tree, lambda n: n.get("pythonObjectTypeName") == "XmppChatWindow"):
        de = n.get("dictEntriesOfInterest", {})
        if de.get("channelCategory") == channel_category:
            return n
    return None


def find_motd_label(chat_window):
    """The MOTD is posted as an ordinary rich-text chat message ("EVE
    System > Channel MOTD: ..."); among possibly-several Label instances
    with that text (scrollback can hold stale/duplicate copies), keep
    only the one whose region actually falls within the chat window's own
    bounds -- others are off-screen/scrolled-away duplicates."""
    win_region = chat_window.get("region")
    candidates = []
    for n in find_all(chat_window, lambda n: n.get("pythonObjectTypeName") == "Label"):
        text = get_display_text(n)
        if text and "Channel MOTD:" in text:
            candidates.append(n)
    if not candidates:
        return None
    if win_region is None:
        return candidates[0]
    win_top, win_bottom = win_region["y"], win_region["y"] + win_region["h"]

    def within(n):
        r = n.get("region")
        return r is not None and win_top <= r["y"] <= win_bottom
    on_screen = [n for n in candidates if within(n)]
    return (on_screen or candidates)[0]


def parse_motd_route(motd_html):
    """Extract the ordered [(name, solarSystemID), ...] list from a MOTD's
    raw rich-text HTML. Strips tags before taking each link's visible text
    (rather than assuming clean markup) since real MOTDs can have stray
    unmatched tags -- observed live: one entry was
    '<a href="...">Sizamo</loc>d</a>', a stray </loc> splitting the name;
    tag-stripping recovers "Sizamod" correctly rather than truncating at
    the first close tag."""
    route = []
    for m in re.finditer(r'<a href="showinfo:5//(\d+)">(.*?)</a>', motd_html, re.DOTALL):
        system_id = int(m.group(1))
        name = re.sub(r"<[^>]+>", "", m.group(2))
        route.append((name, system_id))
    return route


# ---------------------------------------------------------------------------
# Context menu reading (mirrors ParseUserInterface.elm's parseContextMenu)
# ---------------------------------------------------------------------------

def read_open_context_menu(tree):
    """Returns [{"text": str, "region": {...}}, ...] for the currently
    open context menu's entries (empty list if none is open), matching
    ParseUserInterface.elm's parseContextMenu: entries are descendants of
    the menu whose type name contains "menuentry"."""
    l_menu = next(
        (n for n in find_all(tree, lambda n: (n.get("dictEntriesOfInterest", {}) or {}).get("_name", "").lower() == "l_menu")),
        None,
    )
    if l_menu is None:
        return []
    entries = []
    for menu_container in l_menu.get("children", []) or []:
        for n in find_all(menu_container, lambda n: "menuentry" in (n.get("pythonObjectTypeName") or "").lower()):
            text = None
            for cand in find_all(n, lambda n: get_display_text(n) is not None):
                t = get_display_text(cand)
                if text is None or len(t) > len(text):
                    text = t
            entries.append({"text": text or "", "region": n.get("region")})
    entries.sort(key=lambda e: (e["region"] or {}).get("y", 0))
    return entries


# ---------------------------------------------------------------------------
# Route setting
# ---------------------------------------------------------------------------

class RouteSetter:
    def __init__(self, pid, dry_run=False):
        self.pid = pid
        self.dry_run = dry_run
        self.cg = CgInput()
        activate_game(pid)
        print("# bootstrapping live memory access (one-time dump, ~5-10s)")
        self.tw, self.root, self.metatype, self.str_type, self.root_w, self.root_h = bootstrap(pid)
        self.scale = build_scale(self.root_w, self.root_h, window_bounds(pid))
        print(f"# root canvas {self.root_w}x{self.root_h}, scale={self.scale}")

    def read_tree(self, max_depth=16, max_nodes=6000):
        return self.tw.tree(self.root, self.metatype, self.str_type, max_depth=max_depth, max_nodes=max_nodes)

    def click_region_center(self, region, button=CgInput.BUTTON_LEFT):
        cx = region["x"] + region["w"] / 2
        cy = region["y"] + region["h"] / 2
        px, py = game_to_global(cx, cy, self.scale)
        self.cg.click(px, py, button)
        return px, py

    def right_click_game_point(self, gx, gy):
        px, py = game_to_global(gx, gy, self.scale)
        self.cg.move(px, py)
        time.sleep(0.2)
        self.cg.down(CgInput.BUTTON_RIGHT)
        time.sleep(0.1)
        self.cg.up(CgInput.BUTTON_RIGHT)

    def close_menu(self):
        """Press Escape and confirm the menu actually closed before
        returning, retrying if not. Found live: a single Escape + 0.15s
        wasn't reliably enough -- the next right-click (at a corrected
        position) could land while the old menu was still open/closing,
        re-reading the *same* stale menu instead of a fresh one at the
        new spot. Symptom: the steering math was computing a real
        correction each attempt, but the tool kept reporting the exact
        same y/hit result over and over, because it was never actually
        looking at a new state."""
        for _ in range(4):
            self.cg.key(VK_ESCAPE)
            time.sleep(0.3)
            entries = read_open_context_menu(self.read_tree(max_depth=6, max_nodes=400))
            if not entries:
                return
        print("# warning: close_menu gave up waiting for the menu to actually close")

    def find_and_click_route_link(self, motd_label_region, target_name, y_guess, line_height_guess, action_text,
                                   route_names=None, target_index=None, x_candidates=(30, 45, 60, 90, 120, 150, 180)):
        """Right-click near y_guess inside the MOTD label until the
        resulting context menu names target_name, then click action_text
        ("Set Destination" / "Add Waypoint") in that menu. Adjusts y using
        the ordinal mismatch between the system actually hit and the one
        intended (see module docstring) rather than a blind scan.
        Returns the y offset (local to the label) that worked, so the
        caller can refine line_height_guess for the next system.

        route_names/target_index (the full route's names, and this call's
        index into it) let a miss steer proportionally in the *correct*
        direction using how many lines apart the two entries really are --
        without them, a fixed one-line downward nudge is the only option,
        which can only search downward and gets stuck forever once it
        overshoots the target (found live: overshot 'Ana', kept hitting
        later and later entries with no way back up, until the attempt
        cap raised an exception).

        x_candidates starts at 30 (short names like 'Nalu' don't extend as
        far right as x=60) and includes 45 (double-digit line numbers,
        '10.' onward, have a wider prefix than single digits, shifting
        where the actual name text starts -- x=30 on a double-digit line
        landed on the '10.' prefix itself, a plain-text 'Copy'-only menu,
        not the link). Both found live: skipping the entry's real x
        position landed on blank space (or plain text) for every x tried,
        triggering the oscillation bug above."""
        y = y_guess
        # Direction of the most recent deliberate move, used by the
        # "landed on blank space between lines" fallback below. Found
        # live: that fallback always nudged *down*, so a correct upward
        # steer (e.g. stepping back up after overshooting) could be
        # immediately undone by the very next attempt landing in a gap
        # and nudging back down again -- symptom was the tool reporting
        # the exact same y and the exact same wrong hit twice in a row,
        # because two down-nudges after one up-steer summed back to the
        # starting position.
        last_direction = 1
        for attempt in range(8):
            hit_name = None
            hit_x = None
            other_name = None
            for x in x_candidates:
                self.right_click_game_point(motd_label_region["x"] + x, motd_label_region["y"] + y)
                time.sleep(0.25)
                tree = self.read_tree(max_depth=6, max_nodes=400)
                entries = read_open_context_menu(tree)
                if not entries:
                    continue
                menu_text = " | ".join(e["text"] for e in entries)
                if target_name.lower() in menu_text.lower():
                    hit_name = target_name
                    hit_x = x
                    break
                # Extract whichever system the menu actually names, e.g.
                # "Avoid Sizamod (Solar System)" / "Remove Waypoint" (no
                # name) -- used only to steer the next y guess. A menu
                # with neither the target nor an "Avoid" entry (e.g. a
                # bare "Copy | Copy All" from right-clicking plain text
                # like a line's "10." prefix, not a link) isn't useful
                # information -- close it and keep trying the remaining
                # x candidates at this y instead of giving up on the row
                # entirely (found live: this was silently treating "hit
                # plain text" the same as "hit a real, wrong link",
                # aborting the x-scan on the very first x tried).
                m = re.search(r"Avoid (.+) \(Solar System\)", menu_text)
                other_name = m.group(1) if m else None
                self.close_menu()
                if other_name:
                    print(f"#   y={y} x={x}: hit '{other_name}', not '{target_name}'")
                    break

            if hit_name:
                entry = next((e for e in read_open_context_menu(self.read_tree(max_depth=6, max_nodes=400))
                              if action_text.lower() in e["text"].lower()), None)
                if entry is None or entry["region"] is None:
                    self.close_menu()
                    raise RuntimeError(f"menu for {target_name!r} has no {action_text!r} entry")
                if self.dry_run:
                    print(f"# [dry-run] would click {action_text!r} for {target_name!r}")
                    self.close_menu()
                else:
                    self.click_region_center(entry["region"])
                    time.sleep(0.3)
                print(f"# {target_name}: confirmed at y={y} x={hit_x}")
                return y

            if other_name is None:
                # Nothing under the cursor at any x -- probably between
                # lines. Nudge half a line in whatever direction we were
                # last actually correcting toward, not unconditionally
                # down -- an unconditional-down nudge here can silently
                # cancel out a correct upward steer from the previous
                # attempt.
                y += last_direction * max(line_height_guess / 2, 8)
                continue

            # Steer toward the target using the known MOTD ordering: if
            # we can find both names' positions in route_names, jump
            # directly by the line-count difference (works whether the
            # target is above or below where we just looked). Falls back
            # to a nudge in the last known direction only if either name
            # can't be located (e.g. other_name was the RIP/header line,
            # not a route entry).
            steered = False
            if route_names is not None and target_index is not None and other_name in route_names:
                other_index = route_names.index(other_name)
                delta = (target_index - other_index) * line_height_guess
                if delta != 0:
                    last_direction = 1 if delta > 0 else -1
                y += delta
                steered = True
            if not steered:
                y += last_direction * line_height_guess

        raise RuntimeError(f"could not locate '{target_name}' in the MOTD after {attempt + 1} attempts")

    def get_current_route_system_ids(self):
        """Distinct destinationIDs currently in the live autopilot route,
        in encounter order (includes intermediate jump-path systems
        between waypoints, not just the waypoints themselves -- see
        AutopilotDestinationIcon in ParseUserInterface.elm)."""
        tree = self.read_tree()
        ids = []
        for n in find_all(tree, lambda n: n.get("pythonObjectTypeName") == "AutopilotDestinationIcon"):
            sid = (n.get("dictEntriesOfInterest", {}) or {}).get("destinationID")
            if sid is not None and sid not in ids:
                ids.append(sid)
        return ids

    def set_route_from_motd(self, channel_category="corp"):
        tree = self.read_tree()
        chat_window = find_chat_window(tree, channel_category)
        if chat_window is None:
            raise RuntimeError(f"no open chat window for channel category {channel_category!r}")
        label = find_motd_label(chat_window)
        if label is None:
            raise RuntimeError(f"no MOTD text found in the {channel_category!r} channel window")
        de = label.get("dictEntriesOfInterest", {})
        motd_html = de.get("_setText", "")
        route = parse_motd_route(motd_html)
        if not route:
            raise RuntimeError("MOTD contains no showinfo:5// (solar system) links")
        print(f"# parsed {len(route)} systems from the {channel_category} MOTD:")
        for name, system_id in route:
            print(f"#   {name} ({system_id})")

        # Resume support: if some prefix of the route is already in the
        # live route (e.g. a previous run got partway through before
        # crashing on the search bug), skip straight to the first
        # not-yet-set system and use "Add Waypoint" for it -- re-clicking
        # "Set Destination" on an already-set system would wipe whatever
        # progress is already there instead of extending it.
        live_ids = set(self.get_current_route_system_ids())
        start_index = 0
        while start_index < len(route) and route[start_index][1] in live_ids:
            start_index += 1
        if start_index > 0:
            print(f"# resuming: {start_index} system(s) already in the live route "
                  f"({', '.join(n for n, _ in route[:start_index])}), starting from {route[start_index][0]!r}")
        if start_index >= len(route):
            print("# entire route already set, nothing to do")
            return

        # Initial guess: label's own numLines / height gives an average
        # line height; assume 2 header lines (the sender/MOTD-label line
        # commonly wraps) + 1 blank + 1 "ROUTE" line before the first
        # numbered entry -- unverified structural assumption, corrected
        # live by find_and_click_route_link's calibration loop regardless.
        num_lines = de.get("_numLines") or 20
        pad_top = de.get("_padTop") or 4
        line_height = label["region"]["h"] / num_lines
        y = pad_top + 4 * line_height + line_height / 2 + start_index * line_height

        route_names = [name for name, _ in route]
        for i in range(start_index, len(route)):
            name, system_id = route[i]
            action = "Set Destination" if i == 0 else "Add Waypoint"
            y = self.find_and_click_route_link(label["region"], name, y, line_height, action,
                                                route_names=route_names, target_index=i)
            y += line_height  # next system starts ~one line further down

    def close(self):
        self.cg.close()
        self.tw.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pid", type=int, default=None, help="game process pid (auto-detected if omitted)")
    ap.add_argument("--channel", default="corp", help="chat channel category to read the MOTD from (default: corp)")
    ap.add_argument("--dry-run", action="store_true", help="verify/click into each link's menu but don't actually set destination/waypoints")
    args = ap.parse_args()

    pid = args.pid
    if pid is None:
        out = subprocess.run(["pgrep", "-f", "SharedCache.*exefile"], capture_output=True, text=True).stdout
        pid = int(out.strip().splitlines()[0])
        print(f"# using detected game pid {pid}")

    setter = RouteSetter(pid, dry_run=args.dry_run)
    try:
        setter.set_route_from_motd(args.channel)
        print("# done")
    finally:
        setter.close()


if __name__ == "__main__":
    main()
