#!/usr/bin/env python3
"""Interactive control of the EVE client, for one-offs.

    python3 -i eve_repl.py

    >>> eve.overview()[:3]
    >>> row = eve.find("Court Chamberlain")
    >>> eve.select(row)
    >>> eve.buttons()
    >>> eve.panel("selectedItemDock")

Everything here already existed in pieces -- `eve_read` reads the tree,
`cg_input` posts events, `window_probe` gives geometry. What this adds is the
handful of conventions that have to be right or a click lands somewhere
plausible and wrong, each of which cost a real debugging session:

  * Canvas coordinates are not screen coordinates, and the scale is not the
    Retina backing scale. It is UIRoot's own reported size over the window's
    point size, per axis, and it must be measured per session -- 1.68 x 1.74 on
    the machine this was written on, not 2.0.
  * `cg_input` has to be one long-lived process. Click position is state it
    keeps from the last `move`, so a fresh process per command clicks at (0, 0).
  * An overview row reports no display region, so "the middle of the row" comes
    out as its left edge -- the icon column, which does not select. Click into
    the name column instead; see NAME_COLUMN.
  * A context-menu entry's reported y is its top edge. Clicking exactly there
    lands on the entry above ("Simulate Fit" instead of "Board Ship", live).
    Click mid-entry.
  * The overview re-sorts between a read and a click, so find and click in one
    pass and confirm by name afterwards, never by position alone.
  * Where the Selected Item panel offers a named button, press that. It is the
    one interaction on this client that has been reliable every time -- Dock,
    Warp To, Jump, Activate Gate, Approach, Keep At Range.

Safe to run while a bot is running: the host treats input it did not post
itself as a human at the keyboard and stands down for a few seconds. That is
courtesy, not isolation -- two things driving the same cursor is still a bad
idea, and `route_setter.py`/`reload_drones.py` are documented as never-alongside
for exactly this reason.
"""
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eve_read

CG_INPUT = os.path.join(eve_read.HERE, "cg_input", "cg_input")

# How far into an overview row to click. The row's own region is absent from the
# tree, so its reported x is the left edge: the icon column, which does not
# select the row. The name column is reliably past this.
NAME_COLUMN = 200

# Mouse buttons as cg_input numbers.
LEFT, RIGHT = 0, 1

# macOS key codes for the few keys worth having to hand.
KEYS = {"escape": 53, "return": 36, "d": 2, "j": 38, "c": 8, "w": 13,
        "alt": 58, "ctrl": 59, "shift": 56, "cmd": 55}


class Session:
    """A live handle on the client: tree reads in, clicks out."""

    def __init__(self):
        self.entry = eve_read.ui_root()          # raises if the cache is stale
        self.pid = self.entry["pid"]
        self.window, self.origin, self.points = self._window()
        self.tree = None
        self._cg = None
        self.read()
        self._calibrate()
        print(f"EVE session: pid {self.pid}, window {self.window}, "
              f"canvas {self.canvas[0]}x{self.canvas[1]} -> {self.points[0]:.0f}x{self.points[1]:.0f} pt "
              f"(scale {self.scale[0]:.3f} x {self.scale[1]:.3f})")

    # -- geometry ---------------------------------------------------------

    def _window(self):
        """The client's largest window, with its origin and size in points. The
        largest matters: a fullscreen client also has a same-width menu-bar
        strip, and picking that gives a badly wrong y scale."""
        out = subprocess.run([eve_read.WINDOW_PROBE, "--all"],
                             capture_output=True, text=True).stdout
        best = None
        for line in out.splitlines():
            m = re.search(r"window=(\d+).*owner_pid=(\d+).*"
                          r"bounds=\{x=([\d.-]+) y=([\d.-]+) w=([\d.]+) h=([\d.]+)\}", line)
            if m and int(m.group(2)) == self.pid:
                x, y, w, h = (float(m.group(i)) for i in (3, 4, 5, 6))
                if best is None or w * h > best[1] * best[2]:
                    best = (int(m.group(1)), w, h, x, y)
        if best is None:
            raise eve_read.NotAvailable(f"no window found for pid {self.pid}")
        wid, w, h, x, y = best
        return wid, (x, y), (w, h)

    def _calibrate(self):
        entries = self.tree.get("dictEntriesOfInterest") or {}
        cw, ch = entries.get("_displayWidth"), entries.get("_displayHeight")
        if not cw or not ch:
            raise eve_read.NotAvailable("root does not report a canvas size")
        self.canvas = (cw, ch)
        self.scale = (cw / self.points[0], ch / self.points[1])

    def to_screen(self, cx, cy):
        """Canvas coordinates -> screen points, which is what cg_input wants."""
        return (cx / self.scale[0] + self.origin[0],
                cy / self.scale[1] + self.origin[1])

    # -- reading ----------------------------------------------------------

    def read(self):
        """Refresh the cached tree. Everything below reads from this snapshot,
        so call it again after anything that changes the client."""
        self.tree = eve_read.read_tree(entry=self.entry, _verify=False)
        return self.tree

    def nodes(self):
        return list(eve_read.walk(self.tree))

    def of_type(self, type_name, refresh=True):
        if refresh:
            self.read()
        return [(n, x, y) for n, x, y in self.nodes()
                if n.get("pythonObjectTypeName") == type_name]

    def texts(self, node):
        return eve_read.texts_of(node)

    def grep(self, needle, refresh=True):
        """Every node whose visible text mentions `needle`, nearest the leaves
        last. Useful for 'where on earth is that label'."""
        if refresh:
            self.read()
        needle = needle.lower()
        out = []
        for n, x, y in self.nodes():
            joined = " | ".join(eve_read.texts_of(n))
            if needle in joined.lower():
                out.append((n.get("pythonObjectTypeName"), round(x), round(y), joined[:90]))
        return out

    def windows(self, refresh=True):
        """Open windows, by type and caption."""
        if refresh:
            self.read()
        out = []
        for n, x, y in self.nodes():
            t = n.get("pythonObjectTypeName", "")
            if t.endswith("Wnd") or t.endswith("Window"):
                out.append((t, round(x), round(y), eve_read.texts_of(n)[:4]))
        return out

    def overview(self, refresh=True):
        """Overview rows as (x, y, cells). Only rendered rows can be clicked --
        a row scrolled out of view keeps a stale position pointing at whatever
        row was recycled into its place."""
        if refresh:
            self.read()
        return [(round(x), round(y), eve_read.texts_of(n))
                for n, x, y in self.nodes()
                if n.get("pythonObjectTypeName") == "OverviewScrollEntry"]

    def find(self, needle, refresh=True):
        """The first overview row mentioning `needle`, as (x, y, cells)."""
        needle = needle.lower()
        for row in self.overview(refresh=refresh):
            if needle in " | ".join(row[2]).lower():
                return row
        return None

    # -- input ------------------------------------------------------------

    def _cg_send(self, command):
        if self._cg is None:
            subprocess.run(["osascript", "-e", 'tell application "EVE" to activate'],
                           capture_output=True)
            time.sleep(0.6)
            self._cg = subprocess.Popen([CG_INPUT], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, text=True, bufsize=1)
        self._cg.stdin.write(command + "\n")
        self._cg.stdin.flush()
        return self._cg.stdout.readline().strip()

    def move(self, cx, cy):
        x, y = self.to_screen(cx, cy)
        return self._cg_send(f"move {x:.1f} {y:.1f}")

    def click(self, cx, cy, button=LEFT, settle=1.0):
        """Approach, then click. The approach matters: Photon UI cares about a
        real movement gesture, not just the final position."""
        x, y = self.to_screen(cx, cy)
        self._cg_send(f"move {x - 40:.1f} {y:.1f}")
        time.sleep(0.2)
        self._cg_send(f"move {x:.1f} {y:.1f}")
        time.sleep(0.35)
        self._cg_send(f"down {button}")
        time.sleep(0.12)
        self._cg_send(f"up {button}")
        time.sleep(settle)

    def rclick(self, cx, cy, settle=1.5):
        self.click(cx, cy, button=RIGHT, settle=settle)

    def key(self, *names, settle=1.0):
        """Press keys together, released in reverse -- key('alt', 'j')."""
        codes = [KEYS[n] if isinstance(n, str) else n for n in names]
        for code in codes:
            self._cg_send(f"keydown {code}")
            time.sleep(0.08)
        for code in reversed(codes):
            self._cg_send(f"keyup {code}")
            time.sleep(0.05)
        time.sleep(settle)

    # -- the reliable interactions ---------------------------------------

    def select(self, row_or_needle, attempts=3):
        """Select an overview row and confirm the Selected Item panel agrees.

        Re-finds the row before each attempt: the overview is distance-sorted
        and re-sorts between a read and a click, so a position from one reading
        can belong to a different object by the time the click lands.
        """
        needle = row_or_needle if isinstance(row_or_needle, str) else " | ".join(row_or_needle[2])
        key = needle.lower()[:40]
        for _ in range(attempts):
            row = self.find(needle if isinstance(row_or_needle, str) else key)
            if row is None:
                return None
            self.click(row[0] + NAME_COLUMN, row[1] + 12)
            shown = self.selected()
            if any(key.split(" | ")[0][:20] in s.lower() for s in shown):
                return shown
        return self.selected()

    def selected(self, refresh=True):
        """What the Selected Item panel is showing."""
        if refresh:
            self.read()
        for n, _, _ in self.nodes():
            if n.get("pythonObjectTypeName") == "SelectedItemWnd":
                return [s for s in eve_read.texts_of(n)
                        if s not in ("Minimize", "More", "Selected Item")]
        return []

    def buttons(self, refresh=True):
        """The Selected Item panel's buttons, by their stable `_name`, with the
        centre of each. These are the actions worth using: selectedItemDock,
        selectedItemWarpTo, selectedItemJump, selectedItemActivateGate,
        selectedItemApproach, selectedItemKeepAtRange, selectedItemOrbit."""
        if refresh:
            self.read()
        out = {}
        for n, x, y in self.nodes():
            if n.get("pythonObjectTypeName") == "SelectedItemButton":
                d = n.get("dictEntriesOfInterest") or {}
                r = n.get("totalDisplayRegion") or {}
                out[d.get("_name")] = (x + r.get("width", 0) / 2, y + r.get("height", 0) / 2)
        return out

    def panel(self, button_name, settle=2.0):
        """Press a Selected Item panel button by name."""
        found = self.buttons().get(button_name)
        if found is None:
            raise KeyError(f"panel offers no {button_name!r}; has {sorted(k for k in self.buttons() if k)}")
        self.click(found[0], found[1], settle=settle)
        return self.selected()

    def menu(self, cx=None, cy=None, refresh=True):
        """Right-click and return the context menu as (label, x, y_click).

        y_click is the middle of the entry, not its top edge -- the reported y
        is the top, and clicking there lands on the entry above.
        """
        if cx is not None:
            self.rclick(cx, cy)
        if refresh:
            self.read()
        raw = []
        for n, x, y in self.nodes():
            if "MenuEntry" in n.get("pythonObjectTypeName", ""):
                labels = eve_read.texts_of(n)
                if labels:
                    raw.append((y, x, labels[0].strip()))
        raw.sort()
        out = []
        for i, (y, x, label) in enumerate(raw):
            nxt = raw[i + 1][0] if i + 1 < len(raw) else y + 22
            out.append((label, x, (y + min(nxt, y + 30)) / 2))
        return out

    def menu_click(self, label, cx=None, cy=None):
        """Right-click if asked, then click the entry with this exact label."""
        for text, x, y in self.menu(cx, cy):
            if text == label:
                self.click(x + 60, y)
                return True
        return False

    def close(self):
        if self._cg is not None:
            self._cg.stdin.close()
            self._cg = None


def connect():
    return Session()


if __name__ == "__main__":
    try:
        eve = connect()
    except eve_read.NotAvailable as exc:
        print(f"cannot attach: {exc}", file=sys.stderr)
        sys.exit(1)
    print("`eve` is ready. Try eve.overview(), eve.find('...'), eve.buttons().")
