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
    exactly like the typing having failed. Clear it with the box's own clear
    button, never a select-all: see `clear_quick_filter`.

  * **A drag is only a drag if the pointer moves promptly after the press** --
    press, pause, then move reads as a click.

  * **The quantity dialog's default already fills the bay**, so it is accepted
    rather than typed into.

**Accepting that dialog is not evidence the drop landed**, which is what the
rest of this file is about. A drop into a bay with no room is answered by a
`FormWnd` captioned "No room for more in destination container" -- watched live,
on screen for four seconds -- and it carries an OK too. The tool used to click
whatever said OK, compare hangar stack counts, see no change and report a
number, so "the bay was already full" and "the client refused the drop" came
back identically. Two things fix that, and both come from the same reading:

  * **The capacity gauge is the outcome.** With the bay as the selected
    container, `InvContCapacityGauge` reads `50.0/50.0 m³` straight off the
    tree. So the bay is measured before and after, the drag is skipped entirely
    when it is already full (which is when the refusal appears), and success is
    the gauge having moved -- never a dialog having been dismissed. An
    unlimited container such as the station item hangar reports no maximum at
    all, which is also how the tool tells it has the right container selected.

  * **The quick filter can be read back after all**, and the tool now checks
    it. Reading the whole `InvContQuickFilter` node shows its placeholder and
    its clear button's hint whatever has been typed, and an earlier session
    concluded from that the typing had failed when it had not. The typed
    contents are one specific descendant -- `textLabel` under the node named
    `quickFilterInputBox` -- which is where `ParseUserInterface` reads them and
    where the bot watched its own filter accumulate "reportreprrrr..." live.

Preconditions: docked, and the drone in the root Item hangar of *this* station
(sub-folders are not searched). Spare capacity in the drone bay is no longer a
precondition -- a full bay is reported as nothing to do rather than attempted.

Never run alongside a bot. Both drive the real mouse.
"""
import argparse
import collections
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eve_repl
import eve_read

VIEWPORT = (1900, 400)          # empty space, for restoring keyboard focus

# The window types the parser treats as an inventory, so the capacity gauge is
# looked for inside one rather than anywhere in the tree.
INVENTORY_WINDOWS = ("InventoryPrimary", "ActiveShipCargo")

# The quick filter's typed contents live in this descendant, not in the box's
# own texts -- see the header and `quick_filter_text`.
FILTER_BOX_NAME = "quickFilterInputBox"
FILTER_TEXT_NAME = "textLabel"

# What the client says when a drop does not fit. Matched on its text rather
# than on the window type: the refusal is a `FormWnd`, but nothing recorded
# says the quantity dialog is not one too, and both carry an OK button.
DROP_REFUSED = "no room for more"

# Every separator EVE has been seen to put in a number, from the parser's own
# list -- see `parse_number`.
NUMBER_SEPARATORS = (",", ".", "’", "'", " ", " ", " ")

Capacity = collections.namedtuple("Capacity", "used maximum")


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


# -- reading the tree, without touching the client ------------------------
#
# Everything in this section is a function of a reading, so it can be tested
# against nodes built by hand. That matters more here than usual: the tool
# cannot be exercised at all while a bot has the mouse.


def name_of(node):
    return (node.get("dictEntriesOfInterest") or {}).get("_name")


def descendant_named(node, name):
    for child, _, _ in eve_read.walk(node):
        if name_of(child) == name:
            return child
    return None


def parse_number(text):
    """A number as the client renders it, truncated at the decimal separator.

    The same rule `ParseUserInterface.parseNumberTruncatingAfterOptionalDecimal
    Separator` uses, deliberately: split on every separator EVE is known to
    emit and drop a trailing group of fewer than three digits as the fraction,
    so "50.0", "1,234.5" and "1 234" all come out as the integer the bot would
    see. Copying the rule is the point -- the host and the bot disagreeing
    about what the gauge says would be worse than either of them being wrong.
    """
    groups = [text.strip()]
    for separator in NUMBER_SEPARATORS:
        groups = [part for group in groups for part in group.split(separator)]
    if len(groups) > 1 and len(groups[-1]) < 3:
        groups = groups[:-1]
    digits = "".join(groups)
    if not digits.isdigit():
        raise ValueError(f"not a number: {text!r}")
    return int(digits)


def parse_capacity(text):
    """A capacity gauge's text as `Capacity`. `50.0/50.0 m³` -> (50, 50).

    Two shapes beyond the obvious, both from the parser. A selection is shown
    in front of the used figure -- `(10.0) 40.0/50.0 m³` -- and an *unlimited*
    container reports what it holds and no maximum at all, which is what the
    station item hangar does. The missing maximum is not a parse failure; it is
    the signal that the selected container is not the drone bay.
    """
    parts = text.replace("m³", "").replace("m3", "").split("/")
    if len(parts) > 2:
        raise ValueError(f"not a capacity gauge: {text!r}")
    used, maximum = parts[0], (parse_number(parts[1]) if len(parts) == 2 else None)
    return Capacity(parse_number(used.split(")")[-1]), maximum)


def capacity_gauge(nodes):
    """The selected container's capacity, or None if no gauge is on screen.

    Scoped to an inventory window, and taking the longest text under the gauge
    that parses -- both from `parseInventoryWindow`. The gauge's subtree also
    carries shorter fragments, and a fragment parses to a plausible wrong
    number rather than failing, which is the worst of the available outcomes.
    """
    for window, _, _ in nodes:
        if window.get("pythonObjectTypeName") not in INVENTORY_WINDOWS:
            continue
        for node, _, _ in eve_read.walk(window):
            if "CapacityGauge" not in (node.get("pythonObjectTypeName") or ""):
                continue
            for text in sorted(eve_read.texts_of(node), key=len, reverse=True):
                try:
                    return parse_capacity(text)
                except ValueError:
                    continue
    return None


def quick_filter_text(nodes):
    """What the quick-filter box holds, or None if no readable box is on screen.

    Not the box's own texts: those carry the placeholder and the clear button's
    hint whatever has been typed, so reading them says the same thing about a
    filter that worked and one that never landed. An empty string here means an
    empty box, which is a different answer from None and is treated as one.
    """
    for node, _, _ in nodes:
        if name_of(node) != FILTER_BOX_NAME:
            continue
        label = descendant_named(node, FILTER_TEXT_NAME)
        if label is None:
            continue
        texts = eve_read.texts_of(label)
        return texts[0] if texts else ""
    return None


def typeable(text):
    """The text as it will arrive: `type_text` lowercases and sends only the
    characters it has a key code for."""
    return "".join(ch for ch in text.lower() if ch in eve_repl.KEYCODE)


def filter_holds(current, wanted):
    """Whether the box holds the filter that was asked for.

    A prefix, not an equality. This client drops characters while typing --
    "reports" landed as "report" every time the bot tried it -- and the filter
    is a substring match, so a prefix narrows the hangar just as well. Demanding
    the whole string back means the filter never looks set and the caller
    retypes forever. An empty box or unrelated text is still a failure.
    """
    if not current:
        return False
    current = current.strip().lower()
    return bool(current) and typeable(wanted).startswith(current)


def rendered_items(nodes):
    """The `InvItem` rows the client is actually drawing.

    The list virtualises at roughly 40 rows, so this is a signal and never a
    total: it moved 40 -> 10 when a filter was applied and 10 -> 40 when it was
    cleared, which is what makes it usable as corroboration.
    """
    return [(node, x, y) for node, x, y in nodes
            if node.get("pythonObjectTypeName") == "InvItem"
            and (node.get("dictEntriesOfInterest") or {}).get("_display") is not False]


def refusal(nodes):
    """The client's "that drop did not fit" dialog, in its own words, or None.

    Worth finding only so a failure can quote it. Whether the drop landed is
    decided by the capacity gauge either way -- this dialog closes itself after
    a few seconds, so a reading that misses it proves nothing.
    """
    for node, _, _ in nodes:
        if "FormWnd" not in (node.get("pythonObjectTypeName") or ""):
            continue
        text = " ".join(" ".join(eve_read.texts_of(node)).split())
        if DROP_REFUSED in text.lower():
            return text
    return None


def confirm_gain(before, after, refused=None):
    """Raise unless the bay's own gauge shows it gained what was dropped in.

    The gauge is only evidence about the drone bay while the drone bay is the
    selected container, and nothing in a reading says which container that is.
    A maximum that has changed between the two readings is therefore taken as
    "this is a different container", not as a bay that grew: the maximum is a
    property of the ship and cannot move within one run.
    """
    if after.maximum != before.maximum:
        raise RuntimeError(
            f"the capacity gauge now reports a maximum of {after.maximum} m³ where the "
            f"drone bay reported {before.maximum} m³ -- the inventory has some other "
            "container selected, so this reading says nothing about the drop")
    if after.used <= before.used:
        raise RuntimeError(
            (f"the client refused the drop: {refused}" if refused else
             "nothing arrived in the drone bay")
            + f" -- it still reads {after.used}/{after.maximum} m³")


# -- driving the client ---------------------------------------------------


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

    # Exactly this label, and `menu_click` matching exactly is load-bearing:
    # the ship's menu carries "Open Cargohold" directly above "Open Drone Bay",
    # so anything looser -- a startswith, a substring, the first entry
    # containing "Open" -- opens the cargohold, which looks the same in the
    # tree and is silently the wrong container to drop drones into.
    if not eve.menu_click("Open Drone Bay"):
        raise RuntimeError("the ship's context menu offered no 'Open Drone Bay'")
    time.sleep(1.5)
    eve.read()


def select_sidebar(eve, label, settle=2.0):
    """Click a container in the inventory sidebar and read the result."""
    entry = labelled(eve, label)
    if entry is None:
        raise RuntimeError(f"no {label!r} in the inventory sidebar")
    eve.click(*eve.centre_of(*entry), settle=settle)
    eve.read()
    return entry


def bay_capacity(eve):
    """The drone bay's used/maximum, with the bay as the selected container."""
    gauge = capacity_gauge(eve.nodes())
    if gauge is None:
        raise RuntimeError("the inventory window shows no capacity gauge -- without one "
                           "there is no way to tell a drop that landed from one that "
                           "was refused, so this stops rather than guessing")
    if gauge.maximum is None:
        raise RuntimeError(f"the selected container reports no capacity limit "
                           f"({gauge.used} m³ used), so it is an unlimited container such "
                           "as the station item hangar rather than the ship's drone bay")
    return gauge


def clear_quick_filter(eve, box):
    """Empty the focused quick-filter box.

    Not with a select-all: neither shortcut works in this field and both fail
    silently. Control+A is macOS's "move to start of line", so it inserts in
    front of what is already there -- run 115 of the bot accumulated
    "reportreprrrr...". Command+A, which this tool used to send, does not select
    either and leaves the field swallowing every keystroke that follows: run 116
    typed 128 times and changed the box by not one character. The box's own
    clear button is what works, and deleting from both sides of the caret is the
    fallback for a box that is not showing one.
    """
    # `walk` re-applies the box's own offset, so it starts from the box's
    # parent's origin -- walking a subtree from its own absolute position counts
    # that offset twice and clicks a box-width past the button.
    entries = box[0].get("dictEntriesOfInterest") or {}
    ox = box[1] - (entries.get("_displayX") or 0)
    oy = box[2] - (entries.get("_displayY") or 0)
    for child, cx, cy in eve_read.walk(box[0], ox, oy):
        if child.get("pythonObjectTypeName") == "ButtonIcon":
            eve.click(*eve.centre_of(child, cx, cy), settle=0.8)
            return
    eve.clear_text()


def filter_hangar(eve, drone_name, attempts=3):
    """Select the item hangar and narrow it to `drone_name`.

    Returns what the box was confirmed to hold and the rendered item count
    either side of the filter, so the caller can say what it saw rather than
    assert what it wanted. Retypes rather than trusting the first attempt,
    because the only failure mode seen here -- a field that has stopped
    accepting keystrokes -- looks exactly like a slow client.
    """
    select_sidebar(eve, "Item hangar")
    before = len(rendered_items(eve.nodes()))

    held = None
    for _ in range(attempts):
        boxes = eve.of_type("InvContQuickFilter", refresh=False)
        if not boxes:
            raise RuntimeError("no quick-filter box -- is the Inventory window open?")
        box = max(boxes, key=lambda f: (eve.size_of(f[0]) or (0, 0))[0])
        eve.click(*eve.centre_of(*box), settle=1.2)

        clear_quick_filter(eve, box)
        eve.type_text(drone_name)
        time.sleep(2.5)
        eve.read()

        held = quick_filter_text(eve.nodes())
        after = len(rendered_items(eve.nodes()))
        if held is None:
            # No readable box in this build. The rendered count is then the only
            # confirmation there is, and it is a weak one -- a hangar holding
            # nothing but drones filters to the same count it started at.
            return None, before, after
        if filter_holds(held, drone_name):
            return held, before, after

    raise RuntimeError(f"the quick filter still reads {held!r} after {attempts} attempts at "
                       f"typing {typeable(drone_name)!r}, so the hangar was never narrowed")


def find_stack(eve, drone_name):
    """The rendered hangar row for this drone, or None.

    The first word, not the whole name: a cell renders the name with its
    quantity and can truncate it, so "Acolyte" survives a rendering that
    "Acolyte I" does not, and the filter has already narrowed the hangar.
    """
    needle = drone_name.split()[0].lower()
    for node, x, y in rendered_items(eve.nodes()):
        if needle in " ".join(eve_read.texts_of(node)).lower():
            return node, x, y
    return None


def reload_drones(eve, drone_name):
    if not eve.docked(refresh=False):
        raise RuntimeError("not docked")
    if [1 for n, _, _ in eve.nodes()
            if "Display Mode" in " ".join(eve_read.texts_of(n)[:8])]:
        raise RuntimeError("the settings window is covering the client; close it "
                           "(and note Escape opens it rather than closing anything)")

    eve.click(*VIEWPORT, settle=1.2)          # keyboard focus, see the header
    open_drone_bay(eve)

    before = bay_capacity(eve)
    if before.used >= before.maximum:
        # Skipping the drag is not just tidiness: a drop into a full bay is
        # exactly what raises the "No room for more in destination container"
        # dialog, and that dialog is indistinguishable from the quantity prompt
        # by anything this tool can click.
        return before, before

    held, shown_before, shown_after = filter_hangar(eve, drone_name)

    found = find_stack(eve, drone_name)
    if found is None:
        if held is not None:
            detail = f"the quick filter holds {held!r}"
        elif shown_after != shown_before:
            detail = (f"this build shows no readable quick-filter text; the rendered item "
                      f"count went {shown_before} -> {shown_after}, so the filter did narrow "
                      "the list and this station simply has none")
        else:
            detail = (f"this build shows no readable quick-filter text and the rendered item "
                      f"count stayed at {shown_before}, so the filter cannot be confirmed to "
                      "have applied -- the stack may be there and simply past the ~40 rows "
                      "the list renders")
        raise RuntimeError(f"no {drone_name!r} in this station's item hangar ({detail})")
    node, ix, iy = found

    bay = labelled(eve, "Drone Bay")
    if bay is None:
        raise RuntimeError("no 'Drone Bay' in the inventory sidebar")

    width, _ = eve.size_of(node)
    # from the icon, not the label beneath it -- the InvItem box covers both
    eve.drag((ix + width / 2, iy + 25), eve.centre_of(*bay), steps=30, step_delay=0.06)

    eve.read()
    refused = refusal(eve.nodes())
    # Both dialogs have to be dismissed and both say OK. Which one it was is
    # decided below by the gauge, never by this click having landed.
    ok = labelled(eve, "OK") or labelled(eve, "Ok")
    if ok:
        eve.click(*eve.centre_of(*ok), settle=2)

    eve.read()
    select_sidebar(eve, "Drone Bay")
    after = bay_capacity(eve)
    confirm_gain(before, after, refused)
    return before, after


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
    if after.used == before.used:
        print(f"nothing to do: the drone bay is already full at "
              f"{before.used}/{before.maximum} m³")
        return 0
    print(f"loaded {args.drone_name}: drone bay {before.used} -> "
          f"{after.used} of {after.maximum} m³")
    return 0


if __name__ == "__main__":
    sys.exit(main())
