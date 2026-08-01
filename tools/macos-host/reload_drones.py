#!/usr/bin/env python3
"""Refill the active ship's drone bay from the station Item hangar, while docked.

    python3 reload_drones.py [--drone-name "Acolyte I"]

Built on `eve_repl`, which owns attaching to the client, the canvas-to-screen
calibration, one long-lived `cg_input`, and the drag and typing mechanics. The
original did its own repr-scan bootstrap and a fresh full tree read per step,
which made a run take minutes; this reuses the cached UI root and reads in
about half a second.

Every step below earned its place by failing without it:

  * **Keyboard focus.** Mouse clicks are routed by cursor position and keep
    working regardless, but key events go to whatever holds keyboard focus, and
    closing UI windows leaves EVE frontmost with nothing focused. In that state
    neither cg_input nor System Events lands a single key, while every check
    still reports EVE as frontmost. One click on empty viewport fixes it.

  * **Open the drone bay from the ship's own context menu.** Not decoration: an
    Inventory opened this way is anchored to that ship, and that is the context
    where a drop onto Drone Bay is accepted. An Alt+C inventory looks identical
    in the UI tree and silently refuses the drop -- the items stay in the
    hangar while the quantity dialog still appears, as if it had worked.

  * **Find widgets by type, not by nearby text.** The ship is a `ShipItemCard`;
    the filter is an `InvContQuickFilter` (widest match). The original aimed at
    a fixed offset from the "Active" label and missed the card entirely, and
    hunting for the text "Search" finds unrelated tabs in other windows. Three
    separate bugs in one session had this shape.

  * **Clear the filter before typing.** It keeps the previous run's text, and
    appending gives "Acolyte IAcolyte I", which matches nothing and looks
    exactly like the typing having failed.

  * **A drag is only a drag if the pointer moves promptly after the press** --
    press, pause, then move reads as a click.

  * **The quantity dialog's default already fills the bay**, so it is accepted
    rather than typed into.

Preconditions: docked, spare capacity in the drone bay, and the drone in the
root Item hangar of *this* station (sub-folders are not searched).

Never run alongside a bot. Both drive the real mouse.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eve_repl
import eve_read

VIEWPORT = (1900, 400)          # empty space, for restoring keyboard focus


def labelled(eve, label, kind=None):
    """Widest node whose first visible text is exactly `label`."""
    best = None
    for node, x, y in eve.nodes():
        texts = eve_read.texts_of(node)
        if not texts or texts[0].strip() != label:
            continue
        if kind and node.get("pythonObjectTypeName") != kind:
            continue
        size = eve.size_of(node)
        if size and (best is None or size[0] > best[0]):
            best = (size[0], node, x, y)
    return best[1:] if best else None


def open_drone_bay(eve):
    """Right-click the active ship and choose Open Drone Bay."""
    for tab in ("Hangars", "Ships"):
        entry = labelled(eve, tab, kind="EveLabelMedium")
        if entry:
            eve.click(entry[1] + 18, entry[2] + 8, settle=2.2)
            eve.read()

    cards = eve.of_type("ShipItemCard", refresh=False)
    if not cards:
        raise RuntimeError("no ship card in the Hangars/Ships panel")
    node, x, y = cards[0]
    eve.rclick(*eve.centre_of(node, x, y), settle=1.8)

    if not eve.menu_click("Open Drone Bay"):
        raise RuntimeError("the ship's context menu offered no 'Open Drone Bay'")
    time.sleep(1.5)
    eve.read()


def filter_hangar(eve, drone_name):
    hangar = labelled(eve, "Item hangar")
    if hangar is None:
        raise RuntimeError("no 'Item hangar' in the inventory sidebar")
    eve.click(*eve.centre_of(*hangar), settle=2)
    eve.read()

    boxes = eve.of_type("InvContQuickFilter", refresh=False)
    if not boxes:
        raise RuntimeError("no quick-filter box -- is the Inventory window open?")
    box = max(boxes, key=lambda f: (eve.size_of(f[0]) or (0, 0))[0])
    eve.click(*eve.centre_of(*box), settle=1.2)

    # select-all then delete, so a previous run's text is replaced not appended
    eve._cg_send("keydown 55")
    eve._cg_send("keydown 0")
    eve._cg_send("keyup 0")
    eve._cg_send("keyup 55")
    eve._cg_send("keydown 51")
    eve._cg_send("keyup 51")
    time.sleep(0.4)

    eve.type_text(drone_name)
    time.sleep(2.5)
    eve.read()


def reload_drones(eve, drone_name):
    if not eve.docked(refresh=False):
        raise RuntimeError("not docked")
    if [1 for n, _, _ in eve.nodes()
            if "Display Mode" in " ".join(eve_read.texts_of(n)[:8])]:
        raise RuntimeError("the settings window is covering the client; close it "
                           "(and note Escape opens it rather than closing anything)")

    eve.click(*VIEWPORT, settle=1.2)          # keyboard focus, see the header
    open_drone_bay(eve)
    filter_hangar(eve, drone_name)

    needle = drone_name.split()[0].lower()

    def stack():
        for node, x, y in eve.nodes():
            if (node.get("pythonObjectTypeName") == "InvItem"
                    and needle in " ".join(eve_read.texts_of(node)).lower()):
                return node, x, y
        return None

    found = stack()
    if found is None:
        raise RuntimeError(f"no {drone_name!r} in this station's item hangar")
    node, ix, iy = found
    before = eve_read.texts_of(node)[0]

    bay = labelled(eve, "Drone Bay")
    if bay is None:
        raise RuntimeError("no 'Drone Bay' in the inventory sidebar")

    width, _ = eve.size_of(node)
    # from the icon, not the label beneath it -- the InvItem box covers both
    eve.drag((ix + width / 2, iy + 25), eve.centre_of(*bay), steps=30, step_delay=0.06)

    ok = labelled(eve, "OK") or labelled(eve, "Ok")
    if ok:
        eve.click(*eve.centre_of(*ok), settle=2)

    eve.read()
    again = stack()
    return before, (eve_read.texts_of(again[0])[0] if again else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drone-name", default="Acolyte I")
    args = ap.parse_args()

    eve = eve_repl.connect()
    try:
        before, after = reload_drones(eve, args.drone_name)
    except RuntimeError as exc:
        print(f"! {exc}", file=sys.stderr)
        return 1
    if after != before:
        moved = "the whole stack" if after is None else f"{before} -> {after}"
        print(f"loaded {args.drone_name}: hangar stack {moved}")
        return 0
    print(f"! nothing moved -- hangar stack still {before}; is the drone bay full?",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
