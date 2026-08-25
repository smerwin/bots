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


def region_of(node, x, y):
    """`(x1, y1, x2, y2)` for a node already resolved to absolute `(x, y)` by
    `eve_read.walk`, or `None` if it carries no readable size. Only position
    accumulates through a node's ancestors; size is the node's own."""
    entries = node.get("dictEntriesOfInterest") or {}
    width, height = entries.get("_displayWidth"), entries.get("_displayHeight")
    if not width or not height:
        return None
    return (x, y, x + width, y + height)


def regions_overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _is_window_type(type_name):
    # The two occluders #318 was filed on -- `LobbyWnd` and `ChatWindowStack`
    # -- and every other top-level window in this codebase follows one of
    # these two naming conventions.
    return bool(type_name) and ("Wnd" in type_name or "Window" in type_name)


def overlapping_windows(nodes, exclude_ids, target_region):
    """`pythonObjectTypeName`s of every other displayed *window* whose region
    overlaps `target_region`.

    Scoped to window-shaped nodes (`_is_window_type`) rather than every node
    in the tree: the target's own child icons and labels sit trivially
    inside its own region, and so does its containing window (which is why
    the caller excludes it by id too) -- neither is an occluder.

    **No z-order test.** Subtracting every overlapping window, whether or not
    it is actually on top, only ever over-excludes -- the worst case is a
    false alarm on a window that happens to be *behind* the target, never a
    missed real occluder. That is the safe direction for a tool that only
    reports; see #318 and windows-host/FINDINGS.md's note on the same
    trade-off in the locked-target-bar icon cascade.
    """
    names = []
    for n, x, y in nodes:
        if n is None or id(n) in exclude_ids:
            continue
        type_name = n.get("pythonObjectTypeName")
        if not _is_window_type(type_name):
            continue
        if not (n.get("dictEntriesOfInterest") or {}).get("_display", True):
            continue
        region = region_of(n, x, y)
        if region and regions_overlap(target_region, region):
            names.append(type_name)
    return names


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
        # #318: the previous check matched one specific occluder shape (a
        # window with a `CloseButtonIcon` in a fixed top-right pixel band)
        # rather than occlusion itself, and a large chat window anchored to
        # the same corner as the station lobby -- with no `CloseButtonIcon`
        # in that exact slice -- passed clean while covering the undock
        # button entirely. This is a real rectangle-overlap test instead.
        lobby = next(((n, x, y) for n, x, y in nodes
                     if n and n.get("pythonObjectTypeName") == "LobbyWnd"), None)
        button = next(((n, x, y) for n, x, y in nodes
                      if n and n.get("pythonObjectTypeName") == "UndockButton"), None)
        # The button's own region is the precise target; falling back to the
        # whole lobby panel when it is not found is broader but still
        # correct -- this only reports, so over-excluding is the safe
        # direction.
        target = button or lobby

        if target is None:
            report.skip("nothing over the undock button",
                        "no LobbyWnd or UndockButton in the tree while docked")
        else:
            target_node, tx, ty = target
            target_region = region_of(target_node, tx, ty)
            if target_region is None:
                report.skip("nothing over the undock button",
                            "%s has no readable size" % target_node.get("pythonObjectTypeName"))
            else:
                exclude_ids = {id(target_node)}
                if lobby is not None:
                    exclude_ids.add(id(lobby[0]))
                covering = overlapping_windows(nodes, exclude_ids, target_region)
                report.check(
                    "nothing over the undock button", not covering,
                    ("%d overlapping window(s): %s"
                     % (len(covering), ", ".join(covering))) if covering else "",
                    "close whatever is listed; the bot cannot tell an occluded "
                    "button from a slow undock")

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
