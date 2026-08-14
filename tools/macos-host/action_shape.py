"""Record the *shape* of manual actions in the EVE client, not their coordinates.

A click at (1590, 755) means nothing to a bot and nothing to a reader a week
later: the overview virtualises, windows move, and the row under that point
belongs to something else by the next reading. What is durable is what the
click *was* -- "the overview row named 'Centum Ravisher'", "the context-menu
entry containing 'Warp to'", "the third weapon module from the left". That is
the vocabulary `Bot.elm` already thinks in, so it is the vocabulary a recording
has to be in if it is ever to become bot steps.

Three stages, deliberately separate so each can be checked on its own:

    capture   raw input events + the tree epoch they happened under   (events.jsonl)
    resolve   each event -> an ActionShape, by asking the UI tree     (shapes.jsonl)
    emit      collapse sequences -> Elm sketch                        (sketch.elm)

This module is stages 2 and 3 plus a self-test for stage 2. Stage 1 is
deliberately not here yet -- see NOT BUILT below.

WHAT THIS CANNOT DO, stated up front because the gap is the whole risk:

  * It records what was clicked, never *why*. The Elm it emits is a sketch of a
    sequence, not a bot: it has no guards, no bounds, no memory, and this repo's
    whole discipline is that those are the hard part. Treat the output as the
    shape of an intention that a person then has to write properly.
  * A reading costs ~0.4-0.8s through tree_walker and a human clicks faster than
    that, so a shape is resolved against the most recent tree rather than a
    fresh one. Every shape carries `tree_age_ms`; a large one means the answer
    may name a row that had already moved.
  * Where a click lands on something the bot has no way to express, it emits
    kind="unexpressible" rather than inventing a plausible step.
"""

import json
import time

# Node types that end an ascent: the meaningful thing a click was "on".
# Ordered most-specific first; the ascent stops at the first match.
SEMANTIC_KINDS = [
    ("ContextMenuEntry", "context-menu-entry"),
    ("OverviewScrollEntry", "overview-row"),
    ("ScanResultTextEntry", "probe-scanner-row"),
    ("ShipModuleButton", "module-button"),
    ("DroneEntry", "drone-row"),
    ("ChatUserEntry", "chat-user"),
    ("XmppChatUserEntry", "chat-user"),
    ("InfoPanelRouteRouteElementMarker", "route-marker"),
    ("ShipItemCard", "ship-card"),
    ("MessageBox", "message-box"),
]

# Selected-item panel buttons name themselves; this is the one place a raw
# `_name` is the right identity, because Bot.elm looks them up by that name.
PANEL_BUTTON_PREFIX = "selectedItem"


def _d(node):
    return node.get("dictEntriesOfInterest", {}) or {}


def _name(node):
    return _d(node).get("_name") or ""


def _region(node, x, y):
    d = _d(node)
    w, h = d.get("_displayWidth"), d.get("_displayHeight")
    if not isinstance(w, (int, float)) or not isinstance(h, (int, float)):
        return None
    return (x, y, x + w, y + h)


class Resolver:
    """Turns a point in canvas coordinates into what was there."""

    def __init__(self, eve):
        self.eve = eve
        self.epoch = 0
        self.taken_at = 0.0
        self._indexed = []
        self._parent = {}

    def refresh(self):
        self.eve.read()
        self._indexed = []
        self._parent = {}
        for node, x, y in self.eve.nodes():
            r = _region(node, x, y)
            if r:
                self._indexed.append((node, x, y, r, (r[2] - r[0]) * (r[3] - r[1])))
            for child in (node.get("children") or []):
                if isinstance(child, dict):
                    self._parent[id(child)] = node
        self.epoch += 1
        self.taken_at = time.time()
        return len(self._indexed)

    def _ancestors(self, node):
        chain, seen = [node], 0
        while seen < 40:
            node = self._parent.get(id(node))
            if node is None:
                break
            chain.append(node)
            seen += 1
        return chain

    def _window_of(self, chain):
        for n in chain:
            tn = n.get("pythonObjectTypeName", "")
            if tn.endswith("Window") or tn.startswith("InfoPanel"):
                return tn
        return None

    def _texts(self, node, limit=4):
        out = []
        for t in self.eve.texts(node):
            if t and t.strip() and t.strip() not in out:
                out.append(t.strip()[:60])
            if len(out) >= limit:
                break
        return out

    def hit(self, x, y):
        """Smallest node whose region contains the point."""
        best = None
        for node, nx, ny, r, area in self._indexed:
            if r[0] <= x <= r[2] and r[1] <= y <= r[3]:
                if best is None or area < best[4]:
                    best = (node, nx, ny, r, area)
        return best

    def resolve(self, x, y, button="left", held=()):
        """A point -> an ActionShape. Never raises; unknown is a valid answer."""
        shape = {
            "button": button,
            "held": list(held),
            "tree_epoch": self.epoch,
            "tree_age_ms": int((time.time() - self.taken_at) * 1000),
        }
        best = self.hit(x, y)
        if best is None:
            shape.update(kind="miss", note="no node covers this point")
            return shape

        node = best[0]
        chain = self._ancestors(node)
        shape["window"] = self._window_of(chain)

        # A selected-item panel button is identified by its own name.
        for n in chain:
            nm = _name(n)
            if isinstance(nm, str) and nm.startswith(PANEL_BUTTON_PREFIX):
                shape.update(kind="panel-button", target={"button": nm})
                return shape

        for n in chain:
            tn = n.get("pythonObjectTypeName", "")
            for wanted, kind in SEMANTIC_KINDS:
                if tn == wanted:
                    shape.update(kind=kind, target=self._identify(kind, n))
                    return shape

        deepest = node.get("pythonObjectTypeName", "?")
        shape.update(
            kind="unexpressible",
            target={"nodeType": deepest, "name": _name(node), "texts": self._texts(node)},
            note="no bot vocabulary covers this; write the step by hand",
        )
        return shape

    def _identify(self, kind, node):
        """The durable identity of a target, per this repo's own rules."""
        d = _d(node)
        if kind == "overview-row":
            cells = self._texts(node, limit=8)
            # Two identities, and which one a recording wants is the whole point
            # of recording shapes rather than coordinates.
            #
            #   itemID  is the instance -- unique, and what `overviewEntryLockHandle`
            #           uses to attribute a lock outcome to an object within one
            #           session. Useless in a replay: that rat is dead.
            #   typeID  is the *kind* of object. It survives sessions, and it is
            #           what "I clicked a Centior Abomination" actually means.
            #
            # So the shape carries typeID as its identity and itemID only as
            # provenance, for anyone auditing which instance was on screen.
            return {
                "typeID": d.get("typeID"),
                "instanceItemID": d.get("itemID") or d.get("stateItemID"),
                "cells": cells,
                "displayed": d.get("_display", True),
            }
        if kind == "context-menu-entry":
            return {"entryText": (self._texts(node, limit=1) or [""])[0]}
        if kind == "module-button":
            return {"note": "identify by position: sort the row by x, never by index",
                    "name": _name(node)}
        if kind == "probe-scanner-row":
            return {"cells": self._texts(node, limit=6)}
        return {"name": _name(node), "texts": self._texts(node)}


# ---------------------------------------------------------------- collapsing

def collapse(shapes, max_gap_s=6.0):
    """Fold raw shapes into the steps Bot.elm actually has helpers for.

    The one that matters is the cascade: right-click a thing, then click a menu
    entry, is ONE step (`useContextMenuCascadeOnOverviewEntry`) and not two
    clicks. Recording it as two is what makes a replay brittle, because the
    menu's position is never the same twice.
    """
    out, i = [], 0
    while i < len(shapes):
        s = shapes[i]
        nxt = shapes[i + 1] if i + 1 < len(shapes) else None
        is_cascade = (
            s.get("button") == "right"
            and nxt is not None
            and nxt.get("kind") == "context-menu-entry"
            and (nxt.get("t", 0) - s.get("t", 0)) <= max_gap_s
        )
        if is_cascade:
            out.append({
                "kind": "context-menu-cascade",
                "on": s.get("target"),
                "onKind": s.get("kind"),
                "entry": nxt["target"].get("entryText"),
                "t": s.get("t"),
            })
            i += 2
            continue
        out.append(s)
        i += 1
    return out


# ------------------------------------------------------------------ emitting

def to_elm(steps):
    """Render collapsed steps as an Elm *sketch*.

    Deliberately emits `Debug.todo` for anything it cannot express, rather than
    something that compiles and does the wrong thing -- a step that looks right
    and is not is this repo's signature failure.
    """
    lines = [
        "-- SKETCH, generated by action_shape.py. Not a bot.",
        "-- No guards, no bounds, no memory. Every step below needs a human to",
        "-- decide what makes it safe to take and what bounds it if it does not land.",
        "",
    ]
    for n, s in enumerate(steps, 1):
        k = s.get("kind")
        lines.append("-- step %d" % n)
        if k == "context-menu-cascade":
            entry = (s.get("entry") or "").replace('"', "'")
            if s.get("onKind") == "overview-row":
                on = s.get("on") or {}
                # Which cell is the Name depends on the operator's overview
                # preset -- the column order is read from the headers at
                # runtime -- so naming one here would be a guess that reads
                # like a fact. Emit the type id, which is unambiguous, and
                # every cell, and let the reader pick.
                cells = " | ".join(str(c) for c in (on.get("cells") or []))[:70]
                lines += [
                    'useContextMenuCascadeOnOverviewEntry',
                    '    (useMenuEntryWithTextContaining "%s" menuCascadeCompleted)' % entry,
                    '    -- row had typeID %s; cells were: %s'
                    % (on.get("typeID"), cells.replace('"', "'")),
                    '    overviewEntry',
                    '    context',
                ]
            else:
                lines += [
                    'useContextMenuCascadeOnUIElement',
                    '    (useMenuEntryWithTextContaining "%s" menuCascadeCompleted)' % entry,
                    '    uiElement',
                    '    context',
                ]
        elif k == "panel-button":
            lines.append('selectedItemButtonNamed "%s" readingFromGameClient'
                         % s["target"]["button"])
        elif k == "key":
            lines.append("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_%s"
                         % s["target"]["key"])
            lines.append(", EffectOnWindow.KeyUp EffectOnWindow.vkey_%s ]"
                         % s["target"]["key"])
        elif k == "overview-row":
            cells = (s.get("target") or {}).get("cells") or []
            who = (cells[0] if cells else "?").replace('"', "'")
            lines.append('-- plain click on overview row: %s' % who)
            lines.append('overviewEntry.uiNode |> mouseClickOnUIElement MouseButtonLeft')
        elif k == "module-button":
            lines.append('-- module button; identify by sorting the row by x')
            lines.append('clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton')
        else:
            lines.append('Debug.todo "%s -- %s"'
                         % (k, json.dumps(s.get("target"))[:80].replace('"', "'")))
        lines.append("")
    return "\n".join(lines)


# ----------------------------------------------------------------- self-test

def self_test(eve, verbose=True):
    """Round-trip: take real nodes, resolve their own centres, see if we get
    them back. This is the only part that can be checked without driving input,
    and it is the part most likely to be quietly wrong."""
    r = Resolver(eve)
    count = r.refresh()
    if verbose:
        print("indexed %d nodes with regions" % count)

    targets = []
    for node, x, y in eve.nodes():
        tn = node.get("pythonObjectTypeName", "")
        nm = _name(node)
        want = tn in [t for t, _ in SEMANTIC_KINDS] or (
            isinstance(nm, str) and nm.startswith(PANEL_BUTTON_PREFIX))
        if not want:
            continue
        reg = _region(node, x, y)
        if reg:
            targets.append((tn, nm, reg))

    if verbose:
        print("candidate targets: %d\n" % len(targets))
        print("%-26s %-22s %s" % ("clicked (canvas)", "resolved kind", "identity"))
    agree = 0
    for tn, nm, reg in targets[:24]:
        cx, cy = (reg[0] + reg[2]) // 2, (reg[1] + reg[3]) // 2
        s = r.resolve(cx, cy)
        ident = json.dumps(s.get("target", {}))[:66]
        if verbose:
            print("%-26s %-22s %s" % ("%s @(%d,%d)" % (tn[:12], cx, cy), s.get("kind"), ident))
        if s.get("kind") not in ("miss", "unexpressible"):
            agree += 1
    if verbose:
        print("\nresolved to a bot-expressible shape: %d of %d"
              % (agree, len(targets[:24])))
    return agree, len(targets[:24])


# ----------------------------------------------------------------- capturing

STALE_MS = 700          # refresh the tree when idle and it is older than this
CASCADE_GAP_S = 6.0


def from_screen(eve, sx, sy):
    """Screen points -> canvas coordinates. The inverse of eve_repl.to_screen."""
    return ((sx - eve.origin[0]) * eve.scale[0],
            (sy - eve.origin[1]) * eve.scale[1])


def _keycode_names():
    """CGKeyCode -> the vkey_* name Elm uses, borrowed from the host's own
    table so the two cannot drift into disagreeing about what F1 is."""
    try:
        import botlab_host
        table = getattr(botlab_host, "_VK_TO_CGKEYCODE", {})
        names = {}
        for vk, cg in table.items():
            names.setdefault(cg, vk)
        return names
    except Exception:
        return {}


def _a_bot_is_running():
    import subprocess
    try:
        r = subprocess.run(["pgrep", "-f", r"botlab_host\.py"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False


def record(eve, out_path="shapes.jsonl", recorder=None, allow_bot_running=False):
    """Stage 1 + 2: listen, resolve each event, write shapes as they happen.

    Refreshes the tree *while idle* rather than on demand, because the tree a
    click has to be resolved against is the one from before the click -- a read
    taken afterwards already has the context menu open in it, and would resolve
    the right-click to whatever the menu is now covering.
    """
    import os
    import select
    import signal
    import subprocess

    if _a_bot_is_running() and not allow_bot_running:
        raise SystemExit(
            "refusing to record: a bot session is running, so this would record\n"
            "the bot's clicks rather than yours. Stop it first, or pass\n"
            "--allow-bot-running if you really mean to record a bot.")

    if recorder is None:
        here = os.path.dirname(os.path.abspath(__file__))
        recorder = os.path.join(here, "cg_record", "cg_record")
    if not os.path.exists(recorder):
        raise SystemExit(
            "no recorder binary at %s\n"
            "build it:  clang -O2 -framework ApplicationServices "
            "-framework CoreFoundation -o cg_record cg_record.c" % recorder)

    keynames = _keycode_names()
    r = Resolver(eve)
    r.refresh()
    shapes = []
    started = time.time()

    proc = subprocess.Popen([recorder], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1)
    print("recording -- Ctrl-C to stop and write the sketch")
    try:
        while True:
            ready, _, _ = select.select([proc.stdout], [], [], 0.25)
            if not ready:
                age = (time.time() - r.taken_at) * 1000
                if age > STALE_MS:
                    r.refresh()
                if proc.poll() is not None:
                    break
                continue

            line = proc.stdout.readline()
            if not line:
                break
            parts = line.split()
            if len(parts) != 7 or parts[0] != "EVENT":
                continue
            _, _ms, kind, sx, sy, flags, keycode = parts
            t = time.time() - started

            if kind in ("ldown", "rdown", "mdown"):
                cx, cy = from_screen(eve, float(sx), float(sy))
                button = {"ldown": "left", "rdown": "right", "mdown": "middle"}[kind]
                shape = r.resolve(int(cx), int(cy), button=button)
                shape["t"] = round(t, 2)
            elif kind == "key":
                code = int(keycode)
                shape = {"kind": "key", "t": round(t, 2),
                         "target": {"key": keynames.get(code, "UNKNOWN_%d" % code),
                                    "cgKeyCode": code},
                         "tree_epoch": r.epoch}
            else:
                continue

            shapes.append(shape)
            with open(out_path, "a") as f:
                f.write(json.dumps(shape) + "\n")
            print("  %-22s %s" % (shape["kind"],
                                  json.dumps(shape.get("target", {}))[:70]))
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        try:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

    steps = collapse(shapes, max_gap_s=CASCADE_GAP_S)
    print("\n%d raw shapes -> %d steps" % (len(shapes), len(steps)))
    return shapes, steps


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, ".")
    import eve_repl

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", nargs="?", default="self-test",
                    choices=["self-test", "record", "resolve"])
    ap.add_argument("--x", type=int)
    ap.add_argument("--y", type=int)
    ap.add_argument("--out", default="shapes.jsonl")
    ap.add_argument("--elm", default="sketch.elm")
    ap.add_argument("--allow-bot-running", action="store_true")
    args = ap.parse_args()

    eve = eve_repl.connect()

    if args.mode == "self-test":
        self_test(eve)
    elif args.mode == "resolve":
        res = Resolver(eve)
        res.refresh()
        print(json.dumps(res.resolve(args.x, args.y), indent=2))
    else:
        if sys.platform != "darwin":
            raise SystemExit(
                "record is macOS-only for now: it drives cg_record, a "
                "CGEventTap.\nself-test and resolve work anywhere eve_repl does.")
        _, steps = record(eve, out_path=args.out,
                          allow_bot_running=args.allow_bot_running)
        with open(args.elm, "w") as f:
            f.write(to_elm(steps))
        print("wrote %s and %s" % (args.out, args.elm))
