"""Tests for eve_repl's geometry, targeting and input encoding.

Every case here stands for a failure that cost real debugging time against the
live client, recorded in CLAUDE.md or in eve_repl's own comments. The point is
not coverage: it is that the specific wrong answers stay wrong.

None of this needs a running client, and nothing here posts input. `Session` is
built with `__new__` so `__init__` never looks for the UI-root cache, and
`_cg_send` is replaced with a recorder -- which matters, because these tests are
expected to run while a bot has the mouse.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eve_read
import eve_repl


def node(type_name="Node", x=None, y=None, w=None, h=None, text=None, children=()):
    """A UI tree node in the shape tree_walker emits."""
    entries = {}
    if x is not None:
        entries["_displayX"] = x
    if y is not None:
        entries["_displayY"] = y
    if w is not None:
        entries["_displayWidth"] = w
    if h is not None:
        entries["_displayHeight"] = h
    if text is not None:
        entries["_setText"] = text
    return {
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": entries,
        "children": list(children),
    }


def session(origin=(0.0, 0.0), points=(1400.0, 800.0), canvas=(2800, 1600), tree=None):
    """A Session with geometry set by hand and no client behind it."""
    s = eve_repl.Session.__new__(eve_repl.Session)
    s.pid = 1234
    s.window = 116
    s.origin = origin
    s.points = points
    s.canvas = canvas
    s.scale = (canvas[0] / points[0], canvas[1] / points[1])
    s.tree = tree
    s._cg = None
    s.sent = []
    s._cg_send = s.sent.append
    return s


class WindowSelection(unittest.TestCase):
    """A fullscreen client also has a same-width menu-bar strip. Picking the
    first window over some width threshold lands on the strip, whose height is
    ~44pt against the real 1069 -- a y scale wrong by 24x, so every click lands
    near the top of the screen."""

    PROBE_OUTPUT = (
        'window=549 owner_pid=1234 layer=0 owner="EVE" name="" '
        'bounds={x=0.0 y=0.0 w=1710.0 h=38.0}(points) display=1 backing_scale=2.00\n'
        'window=552 owner_pid=1234 layer=25 owner="EVE" name="" '
        'bounds={x=0.0 y=38.0 w=1710.0 h=44.0}(points) display=1 backing_scale=2.00\n'
        'window=550 owner_pid=1234 layer=25 owner="EVE" name="EVE - Gal Bistot" '
        'bounds={x=0.0 y=38.0 w=1710.0 h=1069.0}(points) display=1 backing_scale=2.00\n'
        'window=116 owner_pid=640 layer=0 owner="eve-online" name="EVE Launcher" '
        'bounds={x=0.0 y=39.0 w=1400.0 h=800.0}(points) display=1 backing_scale=2.00\n'
    )

    def _window_for(self, output, pid=1234):
        s = eve_repl.Session.__new__(eve_repl.Session)
        s.pid = pid
        with mock.patch.object(eve_repl.subprocess, "run",
                               return_value=mock.Mock(stdout=output)):
            return s._window()

    def test_picks_largest_by_area_not_first_match(self):
        wid, origin, points = self._window_for(self.PROBE_OUTPUT)
        self.assertEqual(wid, 550)
        self.assertEqual(points, (1710.0, 1069.0))

    def test_ignores_windows_belonging_to_other_pids(self):
        """The launcher is a separate app with its own pid, and is the largest
        window on screen in some layouts."""
        wid, origin, _ = self._window_for(self.PROBE_OUTPUT)
        self.assertNotEqual(wid, 116)
        self.assertEqual(origin, (0.0, 38.0))

    def test_keeps_a_non_zero_origin(self):
        """The window sits below the menu bar, so its origin y is not 0. Losing
        it puts every click 38pt too high."""
        _, origin, _ = self._window_for(self.PROBE_OUTPUT)
        self.assertEqual(origin[1], 38.0)

    def test_no_window_for_pid_raises(self):
        with self.assertRaises(eve_read.NotAvailable):
            self._window_for(self.PROBE_OUTPUT, pid=9999)


class Calibration(unittest.TestCase):
    """The canvas is laid out against UIRoot's own reported size, not a fixed
    Retina backing scale -- so the scale is derived per session, never assumed
    to be 2.0."""

    def _calibrate(self, entries, points=(1400.0, 800.0)):
        s = eve_repl.Session.__new__(eve_repl.Session)
        s.points = points
        s.tree = {"dictEntriesOfInterest": entries}
        s._calibrate()
        return s

    def test_scale_comes_from_the_reported_canvas(self):
        s = self._calibrate({"_displayWidth": 2800, "_displayHeight": 1600})
        self.assertEqual(s.scale, (2.0, 2.0))

    def test_scale_is_not_assumed_to_be_two(self):
        """A UI-scale setting other than 100% gives a non-integer scale, and
        hardcoding 2.0 is what makes clicks land near-but-not-on a target."""
        s = self._calibrate({"_displayWidth": 2100, "_displayHeight": 1200})
        self.assertAlmostEqual(s.scale[0], 1.5)
        self.assertAlmostEqual(s.scale[1], 1.5)

    def test_axes_scale_independently(self):
        s = self._calibrate({"_displayWidth": 2800, "_displayHeight": 800})
        self.assertAlmostEqual(s.scale[0], 2.0)
        self.assertAlmostEqual(s.scale[1], 1.0)

    def test_missing_canvas_raises_rather_than_defaulting(self):
        with self.assertRaises(eve_read.NotAvailable):
            self._calibrate({})


class ToScreen(unittest.TestCase):
    def test_divides_by_scale_and_adds_the_window_origin(self):
        s = session(origin=(0.0, 38.0))
        self.assertEqual(s.to_screen(200, 400), (100.0, 238.0))

    def test_origin_is_added_after_scaling_not_before(self):
        """Scaling an origin-relative coordinate would misplace every click by
        the origin times the scale."""
        s = session(origin=(100.0, 100.0))
        self.assertEqual(s.to_screen(0, 0), (100.0, 100.0))


class NodeGeometry(unittest.TestCase):
    def test_size_prefers_display_keys(self):
        s = session()
        self.assertEqual(s.size_of(node(w=40, h=10)), (40, 10))

    def test_size_falls_back_to_width_and_height(self):
        s = session()
        n = {"dictEntriesOfInterest": {"_width": 25, "_height": 8}}
        self.assertEqual(s.size_of(n), (25, 8))

    def test_size_is_none_when_absent(self):
        s = session()
        self.assertIsNone(s.size_of(node()))

    def test_size_is_none_when_only_one_dimension_is_known(self):
        s = session()
        self.assertIsNone(s.size_of(node(w=40)))

    def test_centre_is_the_middle_of_the_region(self):
        s = session()
        self.assertEqual(s.centre_of(node(w=40, h=10), 100, 50), (120.0, 55.0))

    def test_centre_without_a_size_is_the_position_itself(self):
        s = session()
        self.assertEqual(s.centre_of(node(), 100, 50), (100, 50))


class Clickable(unittest.TestCase):
    """Region-less nodes are the norm, not the exception -- every info panel and
    every overview row is one, which is why searchInputField could never find
    InfoPanelSearch and run 108 stalled. clickable() descends to the first thing
    with a real region.

    The trap is that walk() re-applies the starting node's own offset, so
    walking a subtree from its own absolute position counts that offset twice.
    """

    def test_uses_its_own_centre_when_it_has_a_region(self):
        s = session()
        n = node(x=100, y=50, w=40, h=10)
        self.assertEqual(s.clickable(n, base=(100, 50)), (120.0, 55.0))

    def test_descends_without_double_counting_its_own_offset(self):
        child = node("Label", x=10, y=20, w=40, h=10)
        parent = node("InfoPanel", x=100, y=50, children=[child])

        s = session()
        point = s.clickable(parent, base=(100, 50))

        # Child sits at 110, 70 absolute; its centre is 130, 75. Double-counting
        # the parent's offset would give 230, 125 -- off screen for a panel near
        # the top left, and a click into empty space.
        self.assertEqual(point, (130.0, 75.0))

    def test_skips_region_less_descendants_until_one_has_a_region(self):
        deep = node("Label", x=5, y=5, w=20, h=10)
        middle = node("Container", x=10, y=10, children=[deep])
        parent = node("InfoPanel", x=100, y=50, children=[middle])

        s = session()
        # parent 100,50 -> middle 110,60 -> deep 115,65, centred 125,70.
        self.assertEqual(s.clickable(parent, base=(100, 50)), (125.0, 70.0))

    def test_falls_back_to_the_base_when_nothing_has_a_region(self):
        parent = node("InfoPanel", x=100, y=50, children=[node("Empty", x=1, y=1)])
        s = session()
        self.assertEqual(s.clickable(parent, base=(100, 50)), (100, 50))

    def test_returns_none_when_the_node_is_not_in_the_tree(self):
        s = session(tree=node("Root"))
        self.assertIsNone(s.clickable(node("Orphan", x=1, y=1)))


class OverviewReading(unittest.TestCase):
    def _session_with_rows(self):
        rows = [
            node("OverviewScrollEntry", x=10, y=100, children=[node(text="Kruul's Henchman")]),
            node("OverviewScrollEntry", x=10, y=120, children=[node(text="Cargo Container")]),
            node("SomethingElse", x=10, y=140, children=[node(text="Kruul's Henchman")]),
        ]
        return session(tree=node("Root", x=0, y=0, children=rows))

    def test_reads_only_overview_rows(self):
        s = self._session_with_rows()
        rows = s.overview(refresh=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][2], ["Kruul's Henchman"])

    def test_find_matches_case_insensitively(self):
        s = self._session_with_rows()
        self.assertIsNotNone(s.find("kruul's henchman", refresh=False))

    def test_find_ignores_matching_text_outside_the_overview(self):
        """A tooltip renders the same string outside the row, and clicking that
        hits empty space."""
        s = self._session_with_rows()
        row = s.find("Kruul", refresh=False)
        self.assertEqual(row[1], 100)

    def test_find_returns_none_when_absent(self):
        s = self._session_with_rows()
        self.assertIsNone(s.find("Damsel", refresh=False))


class InputEncoding(unittest.TestCase):
    def test_type_text_skips_characters_it_has_no_key_for(self):
        """getKeyboardKeyToEnterChar covers letters, digits and space. A station
        name with parentheses cannot be typed, and silently dropping them is the
        documented behaviour -- so a caller must search on a substring that has
        none rather than trust the whole string went in."""
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.type_text("a(b)")
        codes = [c for c in s.sent if c.startswith("keydown")]
        self.assertEqual(codes, ["keydown 0", "keydown 11"])

    def test_type_text_holds_each_key_down_then_up(self):
        """Down and up back to back is a press this client misses, which reads
        as characters dropping at random."""
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.type_text("ab")
        self.assertEqual(s.sent, ["keydown 0", "keyup 0", "keydown 11", "keyup 11"])

    def test_type_text_lowercases_before_lookup(self):
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.type_text("A")
        self.assertEqual(s.sent, ["keydown 0", "keyup 0"])

    def test_key_releases_in_reverse_order(self):
        """A modifier must outlive the key it modifies, or alt+j arrives as a
        bare j."""
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.key("alt", "j")
        self.assertEqual(s.sent, ["keydown 58", "keydown 38", "keyup 38", "keyup 58"])

    def test_click_approaches_before_pressing(self):
        """Photon UI cares about a real movement gesture, not just the final
        position: a teleport-then-click is ignored by some elements."""
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.click(200, 400)
        self.assertEqual(s.sent,
                         ["move 60.0 200.0", "move 100.0 200.0", "down 0", "up 0"])

    def test_click_sends_the_requested_button(self):
        s = session()
        with mock.patch.object(eve_repl.time, "sleep"):
            s.rclick(200, 400)
        self.assertIn("down 1", s.sent)
        self.assertIn("up 1", s.sent)


class MenuClicking(unittest.TestCase):
    def test_clicks_past_the_left_edge_of_the_entry(self):
        """A menu entry's reported x is its left edge; clicking exactly there
        can miss the entry."""
        s = session()
        clicked = []
        s.click = lambda x, y, **kw: clicked.append((x, y))
        s.menu = lambda cx=None, cy=None, refresh=True: [("Dock", 300, 400)]

        self.assertTrue(s.menu_click("Dock"))
        self.assertEqual(clicked, [(360, 400)])

    def test_returns_false_when_the_label_is_absent(self):
        """The caller needs to know the entry was not there, rather than having
        a click land on whatever occupies that spot."""
        s = session()
        s.click = lambda *a, **kw: self.fail("must not click when absent")
        s.menu = lambda cx=None, cy=None, refresh=True: [("Warp to Within", 300, 400)]

        self.assertFalse(s.menu_click("Dock"))

    def test_matches_the_label_exactly(self):
        """'Dock' must not select 'Dock at ...' -- the cascade's own step
        depends on which entry opened."""
        s = session()
        s.click = lambda *a, **kw: self.fail("must not click a partial match")
        s.menu = lambda cx=None, cy=None, refresh=True: [("Dock at Station", 300, 400)]

        self.assertFalse(s.menu_click("Dock"))


if __name__ == "__main__":
    unittest.main()
