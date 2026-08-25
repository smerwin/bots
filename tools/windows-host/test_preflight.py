"""Tests for `preflight.py`'s undock-button occlusion check (#318).

No live client needed -- `region_of`, `regions_overlap`, `_is_window_type` and
`overlapping_windows` are pure functions over the `(node, x, y)` shape
`eve_read.walk` produces, so a synthetic tree exercises the real code exactly
as a live reading would.

The synthetic tree below is built from #318's own live capture:

    LobbyWnd        at 1467,0  size 243x817  display True
    ChatWindowStack at 1479,0  size 231x699  display True   [Local 242+]
    UndockButton    at 1476,237 size 225x36  (child of LobbyWnd)

    python test_preflight.py
"""
import unittest

from preflight import overlapping_windows, region_of, regions_overlap


def node(type_name, width=None, height=None, display=True, name=None):
    entries = {"_display": display}
    if width is not None:
        entries["_displayWidth"] = width
    if height is not None:
        entries["_displayHeight"] = height
    if name is not None:
        entries["_name"] = name
    return {"pythonObjectTypeName": type_name, "dictEntriesOfInterest": entries}


class RegionOfTest(unittest.TestCase):
    def test_a_sized_node_answers_its_box(self):
        self.assertEqual(
            region_of(node("LobbyWnd", 243, 817), 1467, 0),
            (1467, 0, 1710, 817))

    def test_a_node_with_no_size_answers_none(self):
        self.assertIsNone(region_of(node("Sprite"), 0, 0))


class RegionsOverlapTest(unittest.TestCase):
    def test_the_318_capture_overlaps(self):
        lobby = (1467, 0, 1467 + 243, 0 + 817)
        chat = (1479, 0, 1479 + 231, 0 + 699)
        self.assertTrue(regions_overlap(lobby, chat))

    def test_touching_edges_do_not_overlap(self):
        # Half-open on purpose: a window that starts exactly where another
        # ends is adjacent, not covering it.
        a = (0, 0, 10, 10)
        b = (10, 0, 20, 10)
        self.assertFalse(regions_overlap(a, b))

    def test_disjoint_regions_do_not_overlap(self):
        self.assertFalse(regions_overlap((0, 0, 10, 10), (100, 100, 110, 110)))


class OverlappingWindowsTest(unittest.TestCase):
    """Reproduces #318's own live capture: a `ChatWindowStack` anchored to
    the same corner as the station lobby, entirely covering the undock
    button, with no `CloseButtonIcon` anywhere near it -- the shape the old
    band/`CloseButtonIcon` heuristic could not see at all."""

    def setUp(self):
        self.lobby = node("LobbyWnd", 243, 817)
        self.button = node("UndockButton", 225, 36)
        self.chat = node("ChatWindowStack", 231, 699)
        self.nodes = [
            (self.lobby, 1467, 0),
            (self.button, 1476, 237),
            (self.chat, 1479, 0),
        ]

    def test_the_chat_window_is_caught_covering_the_button(self):
        target_region = region_of(self.button, 1476, 237)
        exclude_ids = {id(self.button), id(self.lobby)}
        covering = overlapping_windows(self.nodes, exclude_ids, target_region)
        self.assertEqual(covering, ["ChatWindowStack"])

    def test_the_old_check_would_have_missed_it(self):
        # The regression this fix closes: no `CloseButtonIcon` anywhere in
        # this scene, in the top-right band or otherwise, so the check #318
        # replaces would have reported clean.
        self.assertFalse(any(
            (n.get("dictEntriesOfInterest") or {}).get("_name") == "CloseButtonIcon"
            for n, _, _ in self.nodes))

    def test_the_buttons_own_containing_window_is_not_a_false_occluder(self):
        # LobbyWnd necessarily contains its own child button's whole region --
        # that must never be reported as something covering the button.
        target_region = region_of(self.button, 1476, 237)
        exclude_ids = {id(self.button), id(self.lobby)}
        covering = overlapping_windows(self.nodes, exclude_ids, target_region)
        self.assertNotIn("LobbyWnd", covering)

    def test_a_hidden_window_is_not_reported(self):
        hidden_chat = node("ChatWindowStack", 231, 699, display=False)
        nodes = [(self.lobby, 1467, 0), (self.button, 1476, 237), (hidden_chat, 1479, 0)]
        target_region = region_of(self.button, 1476, 237)
        exclude_ids = {id(self.button), id(self.lobby)}
        self.assertEqual(overlapping_windows(nodes, exclude_ids, target_region), [])

    def test_a_non_window_node_over_the_button_is_not_reported(self):
        # A tooltip, sprite or icon sitting over the button is not a stray
        # window occluding it -- only window-shaped nodes are considered.
        tooltip = node("Sprite", 50, 20)
        nodes = [(self.lobby, 1467, 0), (self.button, 1476, 237), (tooltip, 1476, 237)]
        target_region = region_of(self.button, 1476, 237)
        exclude_ids = {id(self.button), id(self.lobby)}
        self.assertEqual(overlapping_windows(nodes, exclude_ids, target_region), [])

    def test_without_a_button_the_whole_lobby_is_the_fallback_target(self):
        # No UndockButton this time -- only the lobby and the occluding chat
        # window, which is the shape `main()` falls back to.
        nodes = [(self.lobby, 1467, 0), (self.chat, 1479, 0)]
        target_region = region_of(self.lobby, 1467, 0)
        exclude_ids = {id(self.lobby)}
        covering = overlapping_windows(nodes, exclude_ids, target_region)
        self.assertEqual(covering, ["ChatWindowStack"])


if __name__ == "__main__":
    unittest.main()
