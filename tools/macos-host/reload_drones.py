#!/usr/bin/env python3
"""Refill the active ship's drone bay from the station Item hangar, while docked.

    python3 reload_drones.py [--drone-name "Acolyte I"] [--count N]

Rewritten on top of `eve_repl`, which now owns the parts every one-off needs:
attaching to the client, the canvas-to-screen calibration, one long-lived
`cg_input`, and the drag and typing mechanics. What is kept from the original,
because it was established live and each piece has a reason:

  * Keyboard focus has to be given back to the game window before typing.
    Mouse clicks are routed by cursor position and keep working regardless,
    but key events go to whatever holds keyboard focus -- and closing UI
    windows can leave the client frontmost with no window focused, at which
    point every keystroke vanishes. Neither cg_input nor System Events gets
    through in that state. One click on empty viewport fixes it, and this
    cost an hour to find.
  * The Item hangar's quick-filter is found by **widget type**
    (`InvContQuickFilter`, widest match), not by its placeholder text. Several
    unrelated nodes read "Search", including other windows' tabs, and clicking
    one of those focuses nothing while looking exactly like success.
  * A drag is only a drag if the pointer moves promptly after the press. Press,
    pause, then move reads as a click and the item stays put.
  * The quantity dialog's default is already the amount that fits, so it is
    accepted rather than typed into.

What is dropped: the original walked the station Hangars panel, switched it to
the Ships tab and right-clicked the active ship to reach "Open Drone Bay". That
step is unnecessary -- the Inventory window's own sidebar lists Drone Bay
directly -- and it was also the step that broke, because it aimed at a fixed
offset from the "Active" marker and missed the ship card.

Preconditions: docked, the named drone in the root Item hangar (not a
sub-folder), and spare capacity in the drone bay.

Never run this while a bot is running. It drives the real mouse, and the two
will fight for the cursor.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eve_repl
import eve_read


def sidebar_entry(eve, label):
    """A row in the Inventory window's tree sidebar, by exact label.

    Matched on size rather than widget type: "Item hangar" is a
    TreeViewEntryWithTag but "Drone Bay" is a plain Container, because it hangs
    under the ship rather than the station. Both render as the same 160-wide
    row, so take the widest node carrying exactly that label.
    """
    best = None
    for node, x, y in eve.nodes():
        texts = eve_read.texts_of(node)
        if not texts or texts[0].strip() != label:
            continue
        size = eve.size_of(node)
        if not size:
            continue
        if best is None or size[0] > best[0]:
            best = (size[0], node, x, y)
    return best[1:] if best else None


def quick_filter(eve):
    """The Item hangar's own filter box: by type, widest match."""
    found = eve.of_type("InvContQuickFilter", refresh=False)
    if not found:
        return None
    return max(found, key=lambda f: (eve.size_of(f[0]) or (0, 0))[0])


def item_matching(eve, name):
    """A rendered item icon in the hangar list whose text matches."""
    needle = name.lower()
    best = None
    for node, x, y in eve.nodes():
        if node.get("pythonObjectTypeName") not in ("InvItem", "Item", "ContainerAutoSize"):
            continue
        joined = " ".join(eve_read.texts_of(node)).lower()
        if needle in joined and eve.size_of(node):
            # the smallest matching node is the icon itself rather than a
            # container several levels up that happens to contain the text
            size = eve.size_of(node)
            area = size[0] * size[1]
            if best is None or area < best[0]:
                best = (area, node, x, y)
    return best[1:] if best else None


def reload_drones(eve, drone_name, expect_overlay_free=True):
    if expect_overlay_free:
        overlay = [1 for n, _, _ in eve.nodes()
                   if "Display Mode" in " ".join(eve_read.texts_of(n)[:8])]
        if overlay:
            raise RuntimeError("the settings window is covering the client -- close it first; "
                               "note Escape opens it rather than closing anything")

    if not eve.docked(refresh=False):
        raise RuntimeError("not docked")

    # Give the game window keyboard focus before any typing -- see the header.
    eve.click(1900, 400, settle=1.2)

    if not eve.of_type("InventoryPrimary", refresh=False):
        eve.key("alt", "c", settle=3)
        eve.read()

    hangar = sidebar_entry(eve, "Item hangar")
    if hangar is None:
        raise RuntimeError("no 'Item hangar' in the inventory sidebar")
    eve.click(*eve.centre_of(*hangar), settle=2)
    eve.read()

    box = quick_filter(eve)
    if box is None:
        raise RuntimeError("no InvContQuickFilter -- is the Inventory window open?")
    eve.click(*eve.centre_of(*box), settle=1.2)
    # Clear first. The box keeps whatever a previous run typed, and typing
    # again appends -- "Acolyte IAcolyte I" matches nothing, which looks
    # exactly like the typing having failed.
    eve._cg_send("keydown 55"); eve._cg_send("keydown 0")
    eve._cg_send("keyup 0");    eve._cg_send("keyup 55")
    time.sleep(0.2)
    eve._cg_send("keydown 51"); eve._cg_send("keyup 51")
    time.sleep(0.4)
    eve.type_text(drone_name)
    time.sleep(2.5)
    eve.read()

    item = item_matching(eve, drone_name.split()[0])
    if item is None:
        raise RuntimeError(f"the filter did not surface {drone_name!r} -- "
                           f"check the text actually landed in the box")

    bay = sidebar_entry(eve, "Drone Bay")
    if bay is None:
        raise RuntimeError("no 'Drone Bay' in the inventory sidebar")

    eve.drag(eve.centre_of(*item), eve.centre_of(*bay))

    # A "Set Quantity" dialog appears when the stack is larger than the bay's
    # remaining capacity. Its default already fills the bay exactly, so accept.
    eve.read()
    for node, x, y in eve.nodes():
        texts = eve_read.texts_of(node)
        if texts and texts[0].strip() in ("OK", "Ok") and eve.size_of(node):
            eve.click(*eve.centre_of(node, x, y), settle=1.5)
            break
    else:
        eve.key("return", settle=1.5)

    eve.read()
    return eve.grep(drone_name.split()[0], refresh=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drone-name", default="Acolyte I")
    args = ap.parse_args()

    eve = eve_repl.connect()
    try:
        loaded = reload_drones(eve, args.drone_name)
    except RuntimeError as exc:
        print(f"! {exc}", file=sys.stderr)
        return 1
    print(f"drone bay now mentions {args.drone_name.split()[0]} in {len(loaded)} nodes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
