"""Tests for what reload_drones believes about a reading before it reports.

The tool cannot be run here at all -- it drives the real mouse, and a bot
usually has it -- so what can be left behind is the half of it that is a
function of a UI tree: what the capacity gauge says, what the quick filter
holds, and whether a drop landed. Those are exactly the three the tool used to
assume rather than read.

Every case stands for something watched on the live client and recorded in
issue #19 or in the tool's own header. The point is not coverage: it is that a
refused drop cannot come back as a success, and that the filter is judged by
the node that changes rather than by the ones that never do.

Nothing here posts input or reads memory. `Session` is built with `__new__` so
`__init__` never looks for the UI-root cache, and `_cg_send` is replaced with a
recorder -- the same pattern as test_eve_repl.py, and for the same reason.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import eve_read
import eve_repl
import reload_drones


def node(type_name="Node", x=None, y=None, w=None, h=None, text=None, name=None,
         display=None, children=()):
    """A UI tree node in the shape tree_walker emits."""
    entries = {}
    for key, value in (("_displayX", x), ("_displayY", y), ("_displayWidth", w),
                       ("_displayHeight", h), ("_setText", text), ("_name", name)):
        if value is not None:
            entries[key] = value
    if display is not None:
        entries["_display"] = display
    return {
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": entries,
        "children": list(children),
    }


def nodes(tree):
    """A reading, in the (node, x, y) form the tool works in."""
    return list(eve_read.walk(tree))


def gauge(text):
    """A capacity gauge inside an inventory window, as the parser scopes it."""
    return node("InventoryPrimary", x=0, y=0, children=[
        node("InvContCapacityGauge", children=[node("Label", text=text)])])


def filter_box(typed=None, placeholder="Search", clear_hint="Clear"):
    """The quick filter, with its placeholder and clear button beside the box.

    The three texts are what made the field look unreadable: only the first of
    them ever changes, and it is the one nested deepest.
    """
    box_children = [node("LabelOverride", text=placeholder),
                    node("ButtonIcon", x=180, y=0, w=16, h=16, text=clear_hint)]
    if typed is not None:
        box_children.insert(0, node("Label", name="textLabel", text=typed))
    return node("InvContQuickFilter", x=100, y=200, w=200, h=20, children=[
        node("Container", name="quickFilterInputBox", children=box_children)])


def session(tree):
    """A Session with a reading in it and no client behind it."""
    s = eve_repl.Session.__new__(eve_repl.Session)
    s.origin, s.points, s.canvas = (0.0, 0.0), (1400.0, 800.0), (2800, 1600)
    s.scale = (2.0, 2.0)
    s.tree = tree
    s._cg = None
    s.sent = []
    s._cg_send = s.sent.append
    return s


class NumberParsing(unittest.TestCase):
    """The gauge's numbers are rendered for a human, and the separator is not
    fixed. This mirrors the Elm parser's rule rather than guessing a locale, so
    the tool and the bot cannot read one gauge two ways."""

    def test_truncates_at_the_decimal_separator(self):
        self.assertEqual(reload_drones.parse_number("50.0"), 50)

    def test_a_thousands_group_is_not_a_fraction(self):
        """Three digits after the separator is a group, fewer is a fraction --
        which is the only way to read "1,234" and "1,2" differently without
        being told which locale the client is in."""
        self.assertEqual(reload_drones.parse_number("1,000"), 1000)
        self.assertEqual(reload_drones.parse_number("1,234.5"), 1234)

    def test_handles_a_space_as_the_separator(self):
        self.assertEqual(reload_drones.parse_number("1 234"), 1234)
        self.assertEqual(reload_drones.parse_number("1 234"), 1234)

    def test_a_bare_integer_survives(self):
        self.assertEqual(reload_drones.parse_number("50"), 50)

    def test_text_that_is_not_a_number_raises(self):
        with self.assertRaises(ValueError):
            reload_drones.parse_number("Drone Bay")


class CapacityParsing(unittest.TestCase):

    def test_used_and_maximum(self):
        self.assertEqual(reload_drones.parse_capacity("50.0/50.0 m³"),
                         reload_drones.Capacity(50, 50))

    def test_a_selection_in_front_is_not_the_used_figure(self):
        """The gauge prefixes what is selected: taking the first number would
        report a bay far emptier than it is."""
        self.assertEqual(reload_drones.parse_capacity("(10.0) 40.0/50.0 m³"),
                         reload_drones.Capacity(40, 50))

    def test_an_unlimited_container_reports_no_maximum(self):
        """The station item hangar. Not a parse failure -- it is the evidence
        that the selected container is not the drone bay."""
        self.assertEqual(reload_drones.parse_capacity("8,433.7 m³"),
                         reload_drones.Capacity(8433, None))


class ReadingTheGauge(unittest.TestCase):

    def test_reads_the_gauge_inside_the_inventory_window(self):
        self.assertEqual(reload_drones.capacity_gauge(nodes(gauge("45.0/50.0 m³"))),
                         reload_drones.Capacity(45, 50))

    def test_ignores_a_gauge_outside_an_inventory_window(self):
        """Scoped the way `parseInventoryWindow` scopes it. A gauge elsewhere in
        the tree parses perfectly and answers about the wrong container."""
        elsewhere = node("Root", children=[
            node("SomeOtherWnd", children=[
                node("InvContCapacityGauge", children=[node("Label", text="900/1000 m³")])])])
        self.assertIsNone(reload_drones.capacity_gauge(nodes(elsewhere)))

    def test_prefers_the_longest_text_under_the_gauge(self):
        """The subtree carries fragments too, and a fragment parses to a
        plausible wrong number rather than failing."""
        crowded = node("InventoryPrimary", children=[
            node("InvContCapacityGauge", children=[
                node("Label", text="50"),
                node("Label", text="45.0/50.0 m³")])])
        self.assertEqual(reload_drones.capacity_gauge(nodes(crowded)),
                         reload_drones.Capacity(45, 50))

    def test_no_gauge_at_all_is_none_rather_than_zero(self):
        """A missing gauge must not read as an empty bay: that is the reading
        on which the tool would drag into a bay it knows nothing about."""
        self.assertIsNone(reload_drones.capacity_gauge(nodes(node("InventoryPrimary"))))


class ReadingTheQuickFilter(unittest.TestCase):
    """Issue #19 reported that the filter cannot be confirmed by reading it,
    having watched the whole `InvContQuickFilter` node's text stay put while the
    item count moved 40 -> 10. The typed text is there -- one node deeper, under
    the name the parser reads it by -- and it is the placeholder and the clear
    button's hint that never change."""

    def test_reads_what_was_typed(self):
        self.assertEqual(
            reload_drones.quick_filter_text(nodes(filter_box(typed="acolyte i"))),
            "acolyte i")

    def test_does_not_read_the_placeholder_or_the_clear_hint(self):
        """The failure mode this whole path exists for: both of these are
        present on an empty box and on a filtered one alike, so a caller that
        reads them learns nothing and concludes the typing failed."""
        held = reload_drones.quick_filter_text(nodes(filter_box(typed="acolyte i")))
        self.assertNotIn("Search", held)
        self.assertNotIn("Clear", held)

    def test_an_empty_box_reads_empty_not_missing(self):
        self.assertEqual(reload_drones.quick_filter_text(nodes(filter_box(typed=""))), "")

    def test_a_build_without_the_label_reads_missing_not_empty(self):
        """None and "" want opposite responses: retype the filter, or accept
        that this build cannot confirm it and fall back to the item count."""
        self.assertIsNone(reload_drones.quick_filter_text(nodes(filter_box())))


class JudgingTheFilter(unittest.TestCase):
    """A prefix, not an equality: this client drops characters while typing --
    "reports" arrived as "report" every time -- and the filter is a substring
    match, so a prefix narrows the hangar just as well."""

    def test_the_whole_string_holds(self):
        self.assertTrue(reload_drones.filter_holds("acolyte i", "Acolyte I"))

    def test_a_dropped_character_still_holds(self):
        self.assertTrue(reload_drones.filter_holds("acolyt", "Acolyte I"))

    def test_an_empty_box_does_not_hold(self):
        self.assertFalse(reload_drones.filter_holds("", "Acolyte I"))
        self.assertFalse(reload_drones.filter_holds(None, "Acolyte I"))

    def test_unrelated_text_does_not_hold(self):
        self.assertFalse(reload_drones.filter_holds("reports", "Acolyte I"))

    def test_the_previous_run_s_text_appended_does_not_hold(self):
        """The trap the clear step exists for: "Acolyte IAcolyte I" matches
        nothing in the hangar and looks exactly like typing having failed."""
        self.assertFalse(reload_drones.filter_holds("acolyte iacolyte i", "Acolyte I"))

    def test_untypeable_characters_are_not_expected_back(self):
        """`type_text` sends only the characters it has a key code for, so a
        name with punctuation can never come back whole."""
        self.assertTrue(reload_drones.filter_holds("veldspar", "Veldspar (Compressed)"))


class SpottingTheRefusal(unittest.TestCase):
    """A drop into a bay with no room raised a `FormWnd` captioned "No room for
    more in destination container", on screen for four seconds. The tool used to
    click its OK, see no change, and report a number."""

    REFUSAL = node("Root", children=[
        node("FormWnd", children=[node("Label", text="No room for more in destination container"),
                                  node("Label", text="OK")])])

    def test_finds_the_refusal_and_quotes_it(self):
        self.assertIn("No room for more", reload_drones.refusal(nodes(self.REFUSAL)))

    def test_an_ordinary_dialog_is_not_a_refusal(self):
        quantity = node("Root", children=[
            node("FormWnd", children=[node("Label", text="Quantity"), node("Label", text="OK")])])
        self.assertIsNone(reload_drones.refusal(nodes(quantity)))

    def test_nothing_on_screen_is_not_a_refusal(self):
        self.assertIsNone(reload_drones.refusal(nodes(node("Root"))))


class ConfirmingTheDrop(unittest.TestCase):
    """The whole of issue #19: the outcome is the gauge having moved, never a
    dialog having been dismissed."""

    def test_a_gain_passes(self):
        reload_drones.confirm_gain(reload_drones.Capacity(0, 50),
                                   reload_drones.Capacity(50, 50))

    def test_an_unchanged_gauge_is_a_failure_even_with_no_dialog_seen(self):
        """The refusal dialog closes itself after a few seconds, so a reading
        that misses it proves nothing. Silence is not consent."""
        with self.assertRaises(RuntimeError) as caught:
            reload_drones.confirm_gain(reload_drones.Capacity(50, 50),
                                       reload_drones.Capacity(50, 50))
        self.assertIn("nothing arrived", str(caught.exception))

    def test_a_refusal_is_quoted_back_in_the_failure(self):
        with self.assertRaises(RuntimeError) as caught:
            reload_drones.confirm_gain(reload_drones.Capacity(50, 50),
                                       reload_drones.Capacity(50, 50),
                                       refused="No room for more in destination container")
        self.assertIn("No room for more", str(caught.exception))

    def test_a_bay_that_lost_volume_is_not_a_success(self):
        with self.assertRaises(RuntimeError):
            reload_drones.confirm_gain(reload_drones.Capacity(50, 50),
                                       reload_drones.Capacity(45, 50))

    def test_a_different_maximum_means_a_different_container(self):
        """Nothing in a reading says which container is selected. The maximum is
        a property of the ship and cannot move within a run, so a maximum that
        changed is the inventory having switched containers -- read as a gain,
        it would report a success for a drop that never happened."""
        with self.assertRaises(RuntimeError) as caught:
            reload_drones.confirm_gain(reload_drones.Capacity(0, 50),
                                       reload_drones.Capacity(8433, None))
        self.assertIn("some other container", str(caught.exception))


class CountingRenderedItems(unittest.TestCase):
    """The corroborating signal, for a build with no readable filter text. The
    list virtualises at roughly 40 rows, so this is a signal and never a
    total."""

    TREE = node("Root", children=[
        node("InvItem", x=10, y=100, children=[node("Label", text="Acolyte I")]),
        node("InvItem", x=10, y=120, display=False, children=[node("Label", text="Reports")]),
        node("SomethingElse", x=10, y=140, children=[node("Label", text="Acolyte I")]),
    ])

    def test_counts_only_rendered_inventory_rows(self):
        self.assertEqual(len(reload_drones.rendered_items(nodes(self.TREE))), 1)

    def test_a_row_scrolled_out_of_view_is_not_a_row_to_drag(self):
        """Same rule as the overview: an unrendered entry keeps a stale position
        that now belongs to whatever was recycled into its place."""
        rows = reload_drones.rendered_items(nodes(self.TREE))
        self.assertEqual([eve_read.texts_of(n)[0] for n, _, _ in rows], ["Acolyte I"])


class FindingTheStack(unittest.TestCase):

    def test_matches_on_the_first_word(self):
        """A cell renders the name with its quantity and can truncate it, so
        "Acolyte" survives a rendering that "Acolyte I" does not."""
        tree = node("Root", children=[
            node("InvItem", x=10, y=100, children=[node("Label", text="Acolyte 10")])])
        found = reload_drones.find_stack(session(tree), "Acolyte I")
        self.assertIsNotNone(found)

    def test_returns_none_when_the_hangar_holds_none(self):
        tree = node("Root", children=[
            node("InvItem", x=10, y=100, children=[node("Label", text="Veldspar")])])
        self.assertIsNone(reload_drones.find_stack(session(tree), "Acolyte I"))


class ClearingTheFilter(unittest.TestCase):
    """Neither select-all works in this field and both fail silently: Control+A
    moves the caret to the start and the bot's filter accumulated
    "reportreprrrr...", while Command+A -- which this tool used to send -- left
    the field swallowing every keystroke that followed, 128 of them in run
    116."""

    CMD_A = ["keydown 55", "keydown 0"]

    def test_clicks_the_boxs_own_clear_button(self):
        s = session(node("Root", children=[filter_box(typed="reports")]))
        box = [(n, x, y) for n, x, y in s.nodes()
               if n.get("pythonObjectTypeName") == "InvContQuickFilter"][0]
        clicked = []
        s.click = lambda x, y, **kw: clicked.append((x, y))

        reload_drones.clear_quick_filter(s, box)

        # The clear button sits at 180,0 inside a box at 100,200 and is 16x16,
        # so its centre is 288,208. This caught the walk-offset trap in the
        # first draft: walking the box's subtree from the box's own absolute
        # position counts that offset twice and clicks 100px past the button,
        # which is empty inventory and does nothing visible.
        self.assertEqual(clicked, [(288.0, 208.0)])

    def test_sends_no_select_all_shortcut(self):
        s = session(node("Root", children=[filter_box(typed="reports")]))
        box = [(n, x, y) for n, x, y in s.nodes()
               if n.get("pythonObjectTypeName") == "InvContQuickFilter"][0]
        s.click = lambda *a, **kw: None

        reload_drones.clear_quick_filter(s, box)

        self.assertEqual(s.sent, [])


class LabelledNodes(unittest.TestCase):
    """Sidebar entries and dialog buttons are all found this way, and the
    exactness is load-bearing in both places."""

    TREE = node("Root", children=[
        node("TreeEntry", x=10, y=100, w=80, h=20, children=[node("Label", text="Drone Bay")]),
        node("TreeEntry", x=10, y=130, w=140, h=20, children=[node("Label", text="Drone Bay")]),
        node("TreeEntry", x=10, y=160, w=90, h=20, children=[node("Label", text="Item hangar")]),
    ])

    def test_picks_the_widest_match(self):
        """The widest is the clickable box around the text rather than a nested
        fragment of it."""
        found = reload_drones.labelled(session(self.TREE), "Drone Bay")
        self.assertEqual(found[2], 130)

    def test_matches_exactly_rather_than_by_prefix(self):
        self.assertIsNone(reload_drones.labelled(session(self.TREE), "Drone"))

    def test_can_require_a_type(self):
        self.assertIsNone(reload_drones.labelled(session(self.TREE), "Drone Bay",
                                                 kind="EveLabelMedium"))


if __name__ == "__main__":
    unittest.main()
