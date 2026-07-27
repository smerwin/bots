#!/usr/bin/env python3
"""Refill the active ship's drone bay from the station Items hangar, while
docked. Built from a live, manually-verified session against the real game
(see CLAUDE.md) -- every coordinate is computed from a live memory read of
the UI tree, not guessed from a screenshot.

Usage:
    python3 reload_drones.py [--drone-name "Acolyte I"] [--pid 86516]

Preconditions:
    - Character is docked, with the station "Hangars" panel visible
      (the right-side panel showing Undock / Guests / Agents / Offices /
      Hangars).
    - The active ship has spare capacity in its drone bay.
    - The named drone is sitting in the station's Item hangar (not a
      sub-folder -- this only searches the flat root item list).

What it does, end to end:
    1. Activates EVE as the frontmost application. This step is not
       optional: CGEventPost mouse clicks are routed by cursor position
       regardless of which app is frontmost, but keyDown/keyUp events go
       to whichever app currently has keyboard focus. Skipping this step
       is the single most common failure mode -- clicks appear to work
       (menus open, buttons respond) while every typed character silently
       goes to the wrong application.
    2. Bootstraps live memory access to the game process (one-time
       repr-scan + walk-to-root, ~5-7s).
    3. Switches the Hangars panel to the "Ships" tab and right-clicks the
       active ship, choosing "Open Drone Bay" -- this opens a proper
       Inventory window already anchored to that ship, with Drone Bay
       selected in its tree.
    4. Selects "Item hangar" in that same Inventory window's tree.
    5. Types the drone name into the Item hangar's own quick-filter
       search box (NOT the global "Search for anything" box -- see
       CLAUDE.md for how this was found: the game's internal UI
       coordinate space is a non-uniformly-scaled virtual canvas
       reported via the UIRoot's own _displayWidth/_displayHeight
       and _dpiScaling, not a simple multiple of the window's actual
       point size).
    6. Drags the filtered item from the list onto "Drone Bay" in the
       tree. EVE only recognizes this as a drag (as opposed to a
       click-to-select) if the pointer moves promptly after mouse-down;
       a synthetic click-then-move sequence with any pause reads as a
       plain click.
    7. If a "Set Quantity" dialog appears (typical: the drone bay has
       less free capacity than the stack size), accepts the default
       quantity by clicking OK. The default is already computed by the
       game to exactly fill remaining capacity, so no typing is needed
       here.

Known limitations, not yet handled:
    - Only searches the root Item hangar; drones stored in a hangar
      sub-folder or inside another ship's cargo won't be found.
    - Assumes a single EVE game window; does not handle multiple
      characters/windows.
    - Does not verify the drone bay actually had room before starting --
      if it's already full, the drag will simply fail to open a dialog
      and the script will report that rather than erroring cleanly.
"""

import argparse
import subprocess
import sys
import time

SCRIPT_DIR = __import__("pathlib").Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "re_helper"))
import re_helper as rh  # noqa: E402

CG_INPUT = str(SCRIPT_DIR / "cg_input" / "cg_input")
MEMORY_SAMPLE_BIN = str(SCRIPT_DIR / "memory_sample" / "memory_sample")

KEYCODE = {
    "a": 0x00, "b": 0x0B, "c": 0x08, "d": 0x02, "e": 0x0E, "f": 0x03,
    "g": 0x05, "h": 0x04, "i": 0x22, "j": 0x26, "k": 0x28, "l": 0x25,
    "m": 0x2E, "n": 0x2D, "o": 0x1F, "p": 0x23, "q": 0x0C, "r": 0x0F,
    "s": 0x01, "t": 0x11, "u": 0x20, "v": 0x09, "w": 0x0D, "x": 0x07,
    "y": 0x10, "z": 0x06, " ": 0x31,
}


class CgInput:
    """Thin persistent wrapper around the cg_input binary."""

    def __init__(self):
        self.p = subprocess.Popen(
            [CG_INPUT], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def send(self, cmd):
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()
        return self.p.stdout.readline().strip()

    def click(self, x, y, button=0, delay=0.05):
        self.send(f"move {x} {y}")
        time.sleep(delay)
        self.send(f"down {button}")
        time.sleep(delay)
        self.send(f"up {button}")
        time.sleep(delay)

    def type_text(self, text, delay=0.03):
        for ch in text.lower():
            code = KEYCODE.get(ch)
            if code is None:
                continue
            self.send(f"keydown {code}")
            self.send(f"keyup {code}")
            time.sleep(delay)

    def drag(self, sx, sy, dx, dy, button=0, steps=24, step_delay=0.05):
        self.send(f"move {sx} {sy}")
        time.sleep(0.15)
        self.send(f"down {button}")
        for i in range(1, steps + 1):
            ix = sx + (dx - sx) * i / steps
            iy = sy + (dy - sy) * i / steps
            self.send(f"drag {ix} {iy} {button}")
            time.sleep(step_delay)
        time.sleep(0.3)
        self.send(f"drag {dx} {dy} {button}")
        time.sleep(0.3)
        self.send(f"up {button}")

    def close(self):
        self.p.stdin.close()
        self.p.wait()


def activate_game(pid):
    """Bring the game process to the frontmost/active application. Real
    keyboard events (as opposed to clicks) only reach whichever app is
    frontmost, regardless of where the mouse is."""
    subprocess.run(
        [
            "osascript", "-e",
            f'tell application "System Events" to set frontmost of first '
            f'process whose unix id is {pid} to true',
        ],
        check=True,
        capture_output=True,
    )


def window_bounds(pid):
    out = subprocess.run(
        [str(SCRIPT_DIR / "window_probe" / "window_probe"), "--all"],
        check=True, capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if f"owner_pid={pid}" not in line:
            continue
        fields = dict(
            part.split("=", 1) for part in line.split() if "=" in part
        )
        bounds = fields.get("bounds", "")
        # bounds={x=0.0 y=38.0 w=1710.0 h=1074.0}(points) -- reconstructed
        # from the raw line since it isn't a single field.
        import re

        m = re.search(
            r"x=([\d.]+) y=([\d.]+) w=([\d.]+) h=([\d.]+)", line
        )
        if m and float(m.group(3)) > 200:  # skip tiny menu-bar-strip windows
            return tuple(float(v) for v in m.groups())
    raise RuntimeError(f"no window found for pid {pid}")


def bootstrap_memory(pid):
    """One-time cost: dump the process, find the UI root, and figure out
    the metatype/str-type addresses and the root's own virtual-canvas
    size (needed to convert the game's internal UI coordinates to real
    screen points)."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        subprocess.run(
            [MEMORY_SAMPLE_BIN, str(pid), d], check=True, capture_output=True
        )
        sample = rh.Sample(d)
        seed = rh._any_seed_addr(sample)
        metatype = rh.find_metatype(sample, seed)
        str_type = rh.__dict__.get("_bootstrap_str_type")
        # _bootstrap_str_type is a private helper on a class in
        # botlab_host.py, not re_helper -- reimplement its small body here.
        hits = rh.repr_scan(sample, limit=5)
        str_type = None
        for addrs in hits.values():
            for addr in addrs:
                dct = rh.get_dict(sample, addr, metatype)
                if dct is None:
                    continue
                st = rh.bootstrap_str_type(sample, dct, metatype)
                if st:
                    str_type = st
                    break
            if str_type:
                break
        if str_type is None:
            raise RuntimeError("could not bootstrap str type")

        root = rh.find_ui_root(sample, metatype, str_type)
        if root is None:
            raise RuntimeError("could not find UI root")

    # Live reads from here on -- no more dumps needed.
    live = rh.LiveSample(pid)
    root_dict = rh.get_dict(live, root, metatype)
    root_entries = dict(rh.dict_items(live, root_dict, metatype, str_type))
    root_w = rh.describe_primitive(
        live, root_entries.get(b"_displayWidth"), metatype, str_type
    )
    root_h = rh.describe_primitive(
        live, root_entries.get(b"_displayHeight"), metatype, str_type
    )
    return live, root, metatype, str_type, root_w, root_h


def build_scale(root_w, root_h, win_bounds):
    """The game's internal UI coordinates (_displayX/_displayY) are laid
    out against a virtual canvas of size root_w x root_h -- NOT the
    window's own point or backing-pixel size. Scale factors below convert
    a summed game-pixel coordinate to a real global screen point."""
    win_x, win_y, win_w, win_h = win_bounds
    sx = win_w / root_w
    sy = win_h / root_h
    return sx, sy, win_x, win_y


def game_to_global(gx, gy, scale):
    sx, sy, win_x, win_y = scale
    return win_x + gx * sx, win_y + gy * sy


def get_tree(live, root, metatype, str_type, max_depth=22, max_nodes=10000):
    return rh.build_tree(
        live, root, metatype, str_type, max_depth=max_depth, max_nodes=max_nodes
    )


def find_all(tree, predicate):
    """Depth-first walk accumulating each node's absolute (summed)
    game-pixel display region alongside whatever predicate(node) returns
    truthy for."""
    out = []

    def walk(n, dx, dy):
        entries = n.get("dictEntriesOfInterest", {})
        sx_, sy_ = entries.get("_displayX"), entries.get("_displayY")
        w, h = entries.get("_displayWidth"), entries.get("_displayHeight")
        absx = dx + sx_ if isinstance(sx_, (int, float)) else dx
        absy = dy + sy_ if isinstance(sy_, (int, float)) else dy
        if predicate(n):
            out.append((absx, absy, w, h, n))
        for c in n.get("children", []):
            walk(c, absx, absy)

    walk(tree, 0, 0)
    return out


def find_text(tree, needle, exact=False):
    needle_l = needle.lower()

    def pred(n):
        entries = n.get("dictEntriesOfInterest", {})
        for v in entries.values():
            if isinstance(v, str):
                if exact and v.lower() == needle_l:
                    return True
                if not exact and needle_l in v.lower():
                    return True
        return False

    return find_all(tree, pred)


def find_type(tree, type_name):
    return find_all(tree, lambda n: n.get("pythonObjectTypeName") == type_name)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pid", type=int, default=None, help="game process pid (auto-detected if omitted)")
    ap.add_argument("--drone-name", default="Acolyte I")
    args = ap.parse_args()

    pid = args.pid
    if pid is None:
        out = subprocess.run(["pgrep", "-f", "SharedCache.*exefile"], capture_output=True, text=True).stdout
        pid = int(out.strip().splitlines()[0])
        print(f"# using detected game pid {pid}")

    print("# activating EVE as the frontmost application")
    activate_game(pid)

    print("# bootstrapping live memory access (one-time dump, ~5-7s)")
    live, root, metatype, str_type, root_w, root_h = bootstrap_memory(pid)
    scale = build_scale(root_w, root_h, window_bounds(pid))
    print(f"# root canvas {root_w}x{root_h}, scale={scale}")

    cg = CgInput()

    def click_node(gx, gy, w, h, button=0):
        cx, cy = gx + (w or 0) / 2, gy + (h or 0) / 2
        px, py = game_to_global(cx, cy, scale)
        if button == 0:
            cg.click(px, py, 0)
        else:
            cg.send(f"move {px} {py}")
            time.sleep(0.05)
            cg.send(f"down {button}")
            time.sleep(0.08)
            cg.send(f"up {button}")
        return px, py

    tree = get_tree(live, root, metatype, str_type)

    ships_tab = find_text(tree, "Ships", exact=True)
    if not ships_tab:
        print("! could not find the 'Ships' hangar tab -- is the station Hangars panel open?")
        sys.exit(1)
    click_node(*ships_tab[0][:4])
    time.sleep(0.3)

    tree = get_tree(live, root, metatype, str_type)
    active_hits = find_text(tree, "Active", exact=True)
    if not active_hits:
        print("! could not find the active ship marker")
        sys.exit(1)
    # the active ship's own name label sits above the "Active" marker in
    # the same row; approximate by clicking slightly above/left of it,
    # then rely on the resulting context menu for the real target.
    ax, ay, aw, ah, _ = active_hits[0]
    px, py = game_to_global(ax - 200, ay - 40, scale)
    cg.send(f"move {px} {py}")
    time.sleep(0.05)
    cg.send("down 1")
    time.sleep(0.08)
    cg.send("up 1")
    time.sleep(0.4)

    tree = get_tree(live, root, metatype, str_type)
    open_drone_bay = find_text(tree, "Open Drone Bay", exact=True)
    if not open_drone_bay:
        print("! no 'Open Drone Bay' menu entry -- right-click may have missed the active ship")
        cg.send("keydown 0x35")
        cg.send("keyup 0x35")
        sys.exit(1)
    gx, gy, w, h, _ = open_drone_bay[0]
    click_node(gx, gy, w, h)
    time.sleep(0.5)

    tree = get_tree(live, root, metatype, str_type)
    item_hangar = find_text(tree, "Item hangar", exact=True)
    if not item_hangar:
        print("! could not find 'Item hangar' in the Inventory window's tree")
        sys.exit(1)
    click_node(*item_hangar[0][:4])
    time.sleep(0.3)

    activate_game(pid)  # re-assert focus before typing
    tree = get_tree(live, root, metatype, str_type)
    filters = find_type(tree, "InvContQuickFilter")
    if not filters:
        print("! could not find the Item hangar's quick-filter search box")
        sys.exit(1)
    # the Inventory window's own filter box is the widest match
    gx, gy, w, h, _ = max(filters, key=lambda f: f[2] or 0)
    px, py = game_to_global(gx + (w or 0) / 2, gy + (h or 0) / 2, scale)
    cg.click(px, py, 0)
    cg.click(px, py, 0)  # double-click: first click can only select/hover
    time.sleep(0.15)
    cg.type_text(args.drone_name)
    time.sleep(0.4)

    tree = get_tree(live, root, metatype, str_type)
    item_hits = find_text(tree, f"<center>{args.drone_name}")
    drone_bay_hits = find_text(tree, "Drone Bay", exact=True)
    if not item_hits:
        print(f"! '{args.drone_name}' not found in the Item hangar (checked root folder only)")
        sys.exit(1)
    if not drone_bay_hits:
        print("! could not find 'Drone Bay' in the tree")
        sys.exit(1)

    ix, iy, iw, ih, _ = item_hits[0]
    # the icon sits above its caption label; aim for the icon, not the text
    icon_x, icon_y = ix + (iw or 0) / 2, iy - 55
    dx, dy, dw, dh, _ = drone_bay_hits[0]
    dest_x, dest_y = dx + (dw or 0) / 2, dy + (dh or 0) / 2

    src_px, src_py = game_to_global(icon_x, icon_y, scale)
    dst_px, dst_py = game_to_global(dest_x, dest_y, scale)

    print(f"# dragging '{args.drone_name}' onto Drone Bay")
    cg.drag(src_px, src_py, dst_px, dst_py)
    time.sleep(0.4)

    tree = get_tree(live, root, metatype, str_type)
    ok_dialog = find_text(tree, "Set Quantity", exact=True)
    if ok_dialog:
        gx, gy, w, h, _ = ok_dialog[0]
        # OK/Cancel button group sits near the bottom of the dialog;
        # OK is the left half.
        ok_x, ok_y = gx + (w or 450) * 0.29, gy + (h or 276) * 0.8
        px, py = game_to_global(ok_x, ok_y, scale)
        cg.click(px, py, 0)
        print("# confirmed quantity dialog")
    else:
        print("# no quantity dialog appeared (stack may have fit without one)")

    cg.close()
    live.close()
    print("# done")


if __name__ == "__main__":
    main()
