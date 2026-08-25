"""Tests for `preflight.py`'s undock-button occlusion check.

Issue #318. The check answered "ok" for the full ~65 minutes a run was stuck
clicking Undock, because it looked for one specific occluder shape -- a window
whose close-icon node is named `CloseButtonIcon` and sits in a narrow
top-right band (`x>1500, y<70`) -- rather than for occlusion. The Local chat
window (`ChatWindowStack`) sat over the station lobby's `UndockButton` at
almost exactly its own rectangle, down to their own `Minimize` buttons sharing
one pixel, with no `CloseButtonIcon` anywhere in that band. The bot clicked the
button's own coordinates 1088 times in a row and never undocked.

`windows_over_undock_button` replaces the band-of-pixels heuristic with a real
rectangle-overlap test: resolve the undock button's own region and check every
window-like node's region against it, needing no z-order -- the same posture
`FINDINGS.md`'s locked-target-bar section takes ("subtracting every
overlapping window's rectangle, whether or not it is on top, only ever
over-excludes"). Over-reporting here is the safe direction: `preflight.py`
only reports, it does not act.

These are plain Python unit tests over a pure function -- no live client, no
Elm, nothing recorded. The fixtures are `(node, x, y)` tuples in exactly the
shape `eve_read.walk` produces, built directly from the geometry #318 itself
records having read off a live client.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
WINDOWS_HOST_DIR = os.path.join(REPO_DIR, "tools", "windows-host")
sys.path.insert(0, WINDOWS_HOST_DIR)
sys.path.insert(0, MACOS_HOST_DIR)

import preflight  # noqa: E402


def node(type_name, x=0, y=0, width=None, height=None, name=None):
    """One `(node, x, y)` tuple in the shape `eve_read.walk` yields -- `x, y`
    already the accumulated absolute position, size (if any) carried in the
    node's own `dictEntriesOfInterest` as `_displayWidth`/`_displayHeight`,
    exactly as `tree_walker` emits it and `_node_region` reads it.
    """
    entries = {}
    if width is not None:
        entries["_displayWidth"] = width
    if height is not None:
        entries["_displayHeight"] = height
    if name is not None:
        entries["_name"] = name
    return ({"pythonObjectTypeName": type_name,
             "dictEntriesOfInterest": entries}, x, y)


class TheLiveCapturedOverlapTest(unittest.TestCase):
    """#318's own geometry, read off a live client while the run was stuck:

        LobbyWnd        at 1467,0  size 243x817  display True
        ChatWindowStack at 1479,0  size 231x699  display True   [Local 242+]
        UndockButton    at 1476,237 size 225x36  (child of LobbyWnd)

    The chat window's bounding box covers the button entirely, and it carries
    no `CloseButtonIcon` in the old check's `x>1500, y<70` band -- which is
    exactly why that check read clean for the whole stall.
    """

    def nodes(self):
        return [
            node("LobbyWnd", 1467, 0, 243, 817),
            node("UndockButton", 1476, 237, 225, 36),
            node("ChatWindowStack", 1479, 0, 231, 699),
        ]

    def test_the_chat_window_is_reported_as_covering_the_button(self):
        covering = preflight.windows_over_undock_button(self.nodes())
        self.assertEqual([t for t, _ in covering], ["ChatWindowStack"])

    def test_the_old_check_would_have_missed_it(self):
        """The regression this whole change exists to fix: no node named
        `CloseButtonIcon` sits in the old check's own top-right band, so it
        would have reported nothing covering the button."""
        covering_old_shape = [
            n for n, x, y in self.nodes()
            if n.get("dictEntriesOfInterest", {}).get("_name") == "CloseButtonIcon"
            and x > 1500 and y < 70]
        self.assertEqual(covering_old_shape, [])

    def test_the_lobby_and_the_button_do_not_count_as_covering_themselves(self):
        """`LobbyWnd` ends in `Wnd` and contains the button -- it must not
        report as its own occluder."""
        nodes = [node("LobbyWnd", 1467, 0, 243, 817),
                 node("UndockButton", 1476, 237, 225, 36)]
        self.assertEqual(preflight.windows_over_undock_button(nodes), [])


class TheOverlapRuleTest(unittest.TestCase):
    """The rectangle test itself, away from the live capture's own numbers."""

    def test_a_window_that_does_not_reach_the_button_is_not_reported(self):
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            # Entirely above the button -- shares no pixel with it.
            node("ChatWindowStack", 0, 0, 300, 100),
        ]
        self.assertEqual(preflight.windows_over_undock_button(nodes), [])

    def test_touching_edges_do_not_count_as_overlap(self):
        """A window whose edge lands exactly on the button's own edge shares
        no pixel with it -- `<` rather than `<=` is deliberate."""
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("ChatWindowStack", 210, 700, 100, 30),  # starts at x=210, button ends at x=210
        ]
        self.assertEqual(preflight.windows_over_undock_button(nodes), [])

    def test_a_one_pixel_overlap_is_still_reported(self):
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("ChatWindowStack", 209, 700, 100, 30),  # overlaps by 1px
        ]
        covering = preflight.windows_over_undock_button(nodes)
        self.assertEqual([t for t, _ in covering], ["ChatWindowStack"])

    def test_a_node_with_no_size_is_never_reported(self):
        """Plenty of nodes carry no `totalDisplayRegion` at all (see
        `eve_repl.py`'s `clickable`) -- one cannot occlude anything if this
        reading cannot say where its edges are."""
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("ChatWindowStack", 0, 0),  # no width/height
        ]
        self.assertEqual(preflight.windows_over_undock_button(nodes), [])

    def test_a_node_type_that_is_not_window_like_is_not_reported(self):
        """A label or an icon sitting over the button by coincidence is not a
        window -- only `KNOWN_OCCLUDING_TYPES` and `*Wnd`/`*Window` nodes
        count, or every tooltip in the tree would fail this check."""
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("EveLabelMedium", 10, 700, 200, 30),
        ]
        self.assertEqual(preflight.windows_over_undock_button(nodes), [])

    def test_several_covering_windows_are_all_reported(self):
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("ChatWindowStack", 0, 690, 300, 60),
            node("DronesWindow", 0, 690, 300, 60),
        ]
        covering = preflight.windows_over_undock_button(nodes)
        self.assertEqual(
            sorted(t for t, _ in covering), ["ChatWindowStack", "DronesWindow"])

    def test_a_context_menu_over_the_button_is_reported_too(self):
        """`ContextMenu` is in the known-occluding set as well as this check's
        own generic suffix test -- a stray menu blocking the button is exactly
        as real a reason it never lands as a chat window is."""
        nodes = [
            node("LobbyWnd", 0, 0, 300, 800),
            node("UndockButton", 10, 700, 200, 30),
            node("ContextMenu", 5, 695, 100, 40),
        ]
        covering = preflight.windows_over_undock_button(nodes)
        self.assertEqual([t for t, _ in covering], ["ContextMenu"])


class TheMissingButtonTest(unittest.TestCase):
    """`None` -- "cannot check" -- rather than a false "clear", per
    `loadRefusalFromGameLog`'s register: absent evidence is not a finding."""

    def test_no_button_and_no_lobby_answers_none(self):
        nodes = [node("ChatWindowStack", 0, 0, 300, 60)]
        self.assertIsNone(preflight.windows_over_undock_button(nodes))

    def test_the_lobby_s_own_region_is_the_fallback(self):
        """The issue names this explicitly: fall back to `LobbyWnd`'s region
        when the button node itself carries none."""
        nodes = [
            node("LobbyWnd", 100, 0, 300, 800),
            node("UndockButton", 110, 700),  # no size of its own
            node("ChatWindowStack", 100, 0, 300, 800),
        ]
        covering = preflight.windows_over_undock_button(nodes)
        self.assertEqual([t for t, _ in covering], ["ChatWindowStack"])

    def test_neither_button_nor_lobby_carrying_a_size_answers_none(self):
        nodes = [
            node("LobbyWnd", 100, 0),
            node("UndockButton", 110, 700),
        ]
        self.assertIsNone(preflight.windows_over_undock_button(nodes))

    def test_an_empty_reading_answers_none(self):
        self.assertIsNone(preflight.windows_over_undock_button([]))


if __name__ == "__main__":
    unittest.main()
