"""Everything that has silently killed a run, checked before one is launched.

    python preflight.py            # report, exit 0 if ready and 1 if not
    python preflight.py --quiet    # exit code only, for scripting a launcher

**Read-only.**  It posts no input and is safe beside a live bot -- the host
stands down for *input*, and this is one memory read.  It reports; fixing is a
separate decision, and each check prints the remedy rather than applying it.

Why this exists.  Every item below cost a whole session on 17-18 Aug, and each
one presents as a *different* bug from the outside, which is what makes a list
worth more than the individual fixes:

  * **The probe scanner shut.**  A run configured to hunt anomalies spent its
    whole session unable to see one.  The trap is that the scanner is a *space*
    window: `Alt+P` does nothing while docked and the node count reads 0 whether
    it is closed or merely unavailable, so **checking it from station proves
    nothing**.  This refuses to answer while docked rather than answering
    wrongly.
  * **The location info panel switched off.**  The two branches of
    `ensureInfoPanelLocationInfoIsExpanded` then deadlock over it (#297), and
    because that runs inside `generalSetupInUserInterface` -- above the
    docked-or-in-space split -- the retreat is unreachable while they do.  One
    run spent 364 of its 567 readings there and killed nothing.
  * **A window left over the station lobby's Undock button.**  The bot clicks
    into it forever while reporting `I clicked undock N step(s) ago and the
    client is still showing the undock button`.  It never reports being blocked,
    because from the UI tree the button is right there -- it is simply occluded.
  * **A stray context menu**, which sits over the UI swallowing later clicks.
  * **Hostiles already on grid**, because a run that starts mid-fight has no
    chance to arm anything first.

A client that has been killed rather than quit cleanly is how several of these
arise at once: EVE writes its window layout on a clean exit, so a `Stop-Process`
restart comes back with the scanner closed and the panels wrong.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Resolved from this file rather than hardcoded: a sibling here carries an
# absolute path to a checkout that does not exist on this machine.
sys.path.insert(0, os.path.join(HERE, os.pardir, "macos-host"))
sys.path.insert(0, HERE)

import eve_read  # noqa: E402
import eve_repl  # noqa: E402


class Report:
    def __init__(self, quiet=False):
        self.ok = True
        self.quiet = quiet

    def check(self, label, good, detail="", remedy=""):
        if not good:
            self.ok = False
        if self.quiet:
            return
        print("  [%s] %-32s %s" % ("ok" if good else "!!", label, detail))
        if not good and remedy:
            print("       -> %s" % remedy)

    def skip(self, label, why):
        self.ok = False
        if not self.quiet:
            print("  [--] %-32s %s" % (label, why))


def _node_region(node, x, y):
    """A node's absolute screen rectangle as `(x0, y0, x1, y1)`, or `None` if
    it carries no size of its own.

    `tree_walker` emits no `totalDisplayRegion` -- see `eve_repl.py`'s own
    header -- so size lives in `dictEntriesOfInterest` as
    `_displayWidth`/`_displayHeight`, while `x, y` (from `eve_read.walk`) are
    already the accumulated absolute position.
    """
    entries = (node.get("dictEntriesOfInterest") or {}) if node else {}
    width = entries.get("_displayWidth")
    height = entries.get("_displayHeight")
    if not width or not height:
        return None
    return (x, y, x + width, y + height)


def _regions_overlap(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


# `EveOnline.ParseUserInterface.pythonObjectTypesKnownToOccludeFollowingElements`
# already ships in every bot -- built from real observed occlusions, and it is
# where `ChatWindowStack`, #318's actual occluder, comes from. Unioned with any
# node whose own type name says it is a window, rather than used alone: the
# curated set is what caught this bug's occluder, and the suffix test is what
# stops this being one more detector built against a single specific shape,
# which is #318's own diagnosis of the check it replaces. Over-including here
# costs nothing -- this only reports, never acts.
KNOWN_OCCLUDING_TYPES = frozenset({
    "SortHeaders", "ContextMenu", "OverviewWindow", "DronesWindow",
    "SelectedItemWnd", "InventoryPrimary", "ChatWindowStack",
})


def _is_window_like(type_name):
    return (type_name in KNOWN_OCCLUDING_TYPES
            or type_name.endswith("Wnd") or type_name.endswith("Window"))


def windows_over_undock_button(nodes):
    """Every displayed, window-like node whose rectangle overlaps the undock
    button's own -- a real rectangle-overlap test rather than one specific
    occluder shape (#318).

    Confirmed live: the Local chat window (`ChatWindowStack`) sat over the
    station lobby's `UndockButton` at almost exactly its own rectangle, down to
    their `Minimize` controls sharing one pixel, while carrying no
    `CloseButtonIcon` in the narrow top-right band the check this replaces
    looked at -- so it read clean for the full ~65 minutes the bot clicked into
    the chat window instead of the button underneath it.

    Needs no z-order, for the reason `FINDINGS.md`'s locked-target-bar section
    gives: flagging every overlapping window's rectangle whether or not it is
    on top only ever over-reports, and over-reporting here costs nothing since
    this check only prints a remedy -- it posts no input and fixes nothing
    itself.

    Returns `None` if the undock button's own region cannot be resolved at all
    -- no `UndockButton` node and no `LobbyWnd` to fall back to, or neither
    carries a size -- which is distinct from an empty list, meaning the check
    ran and found nothing covering it.
    """
    button = next((t for t in nodes
                   if t[0] and t[0].get("pythonObjectTypeName") == "UndockButton"), None)
    lobby = next((t for t in nodes
                  if t[0] and t[0].get("pythonObjectTypeName") == "LobbyWnd"), None)

    button_region = _node_region(*button) if button else None
    if button_region is None and lobby is not None:
        button_region = _node_region(*lobby)
    if button_region is None:
        return None

    exclude_ids = {id(t[0]) for t in (button, lobby) if t is not None}
    covering = []
    for node, x, y in nodes:
        if not node or id(node) in exclude_ids:
            continue
        type_name = node.get("pythonObjectTypeName", "")
        if not _is_window_like(type_name):
            continue
        region = _node_region(node, x, y)
        if region and _regions_overlap(region, button_region):
            covering.append((type_name, region))
    return covering


def panels_of(eve, nodes):
    container = next((n for n, x, y in nodes
                      if n and n.get("pythonObjectTypeName") == "InfoPanelContainer"), None)
    out = {}
    if container is not None:
        for node, _, _ in eve_read.walk(container):
            name = node.get("pythonObjectTypeName", "")
            if name.startswith("InfoPanel") and name != "InfoPanelContainer":
                out[name] = (node.get("dictEntriesOfInterest", {}) or {}).get("_display", True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quiet", action="store_true",
                        help="print nothing; the exit code is the answer")
    args = parser.parse_args()

    report = Report(args.quiet)
    eve = eve_repl.connect()
    eve.read()
    nodes = eve.nodes()
    docked = eve.docked()

    location = next((n for n, x, y in nodes
                     if n and n.get("pythonObjectTypeName") == "InfoPanelLocationInfo"), None)
    texts = [t.strip() for t in eve.texts(location) if t and t.strip()] if location else []
    if not args.quiet:
        print("=== pre-flight ===")
        print("  docked: %s   system: %s" % (docked, texts[1] if len(texts) > 1 else "?"))

    panels = panels_of(eve, nodes)
    report.check("location panel displayed",
                 panels.get("InfoPanelLocationInfo") is True,
                 str(panels),
                 "click the toggle whose icon texture is LocationInfo.png "
                 "(the toggles are told apart by texturePath, not position)")
    report.check("route panel displayed", panels.get("InfoPanelRoute") is True,
                 "", "click the toggle whose icon texture is Route.png")

    probes = sum(1 for n, x, y in nodes
                 if n and "ProbeScanner" in n.get("pythonObjectTypeName", ""))
    if docked:
        report.skip("probe scanner", "CANNOT BE CHECKED WHILE DOCKED -- undock first")
    else:
        report.check("probe scanner open", probes > 0, "%d nodes" % probes,
                     "Alt+P, then re-run this; it is a space window")

    if docked:
        covering = windows_over_undock_button(nodes)
        if covering is None:
            report.skip("nothing over the undock button",
                        "no UndockButton or LobbyWnd node with a size in this "
                        "reading -- cannot check occlusion")
        else:
            report.check(
                "nothing over the undock button", not covering,
                ", ".join(sorted({type_name for type_name, _ in covering})),
                "close the window(s) named above; the bot cannot tell an "
                "occluded button from a slow undock")

    menus = sum(1 for n, x, y in nodes
                if n and "ContextMenu" in n.get("pythonObjectTypeName", ""))
    report.check("no stray context menu", menus == 0, "%d open" % menus,
                 "press Escape")

    if not docked:
        ship = next((n for n, x, y in nodes
                     if n and n.get("pythonObjectTypeName") == "ShipUI"), None)
        gauges = [t.strip() for t in eve.texts(ship) if t and t.strip() and "%" in t][:3] if ship else []
        report.check("ship UI present", ship is not None, str(gauges))

    rows = [n for n, x, y in nodes
            if n and n.get("pythonObjectTypeName") == "OverviewScrollEntry"]
    hostile = [r for r in rows
               if any(word in " ".join(eve.texts(r))
                      for word in ("Centi", "Sansha", "Sentry", "Pithi",
                                   "Guristas", "Serpentis", "Blood"))]
    report.check("grid clear of hostiles", not hostile,
                 "%d rows, %d hostile" % (len(rows), len(hostile)),
                 "let the bot finish, or warp clear, before starting a run")

    if not args.quiet:
        print()
        print("PREFLIGHT: %s" % ("PASS" if report.ok else "NOT READY"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
