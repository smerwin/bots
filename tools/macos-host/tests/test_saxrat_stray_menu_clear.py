"""Tests for saxrat clearing a stray context menu without creating one.

**The rescue reproduced what it was rescuing from, twice.** Run 47 did it 16,791
times; run 18 did it 10,845 times across an eight-hour session -- three quarters
of every decision -- and killed nothing.

The branch right-clicked a computed point and then left-clicked *the same point*
to dismiss whatever the right-click opened. That can never work, and the reason
is structural rather than a matter of tuning: **the client opens a context menu
at the cursor**, so the right-click always draws the new menu over the very
point the left click is aimed at, and the left click lands on a menu entry
instead of on empty canvas. Read off the live client mid-loop:

    info panel   x 40..430,  y 63..418
    click point  (430 + 80, 63 + 177)  =  (510, 240)
    menu drawn   x 510..801, y 233..543      <- the point is its top-left corner

The menu it had standing open was the solar-system menu, which carries
`Clear All Waypoints` -- the entry `beginCascade`'s own fallback comment records
having once triggered on a real route.

Three things change, and each has its own cases below:

- **A left click, and only a left click.** Measured live against the real stuck
  menu: one left click on empty canvas dismissed it and opened nothing. The
  right-click is deleted rather than moved.
- **The point steps clear of any open menu.** `emptyPointBesideTheInfoPanel`'s
  own doc says the point "was covered by zero nodes" -- verified once, against a
  tree with no menu open, which is the one state it is never used in.
- **The branch is bounded.** It had no counter and no give-up while sitting at
  the head of `decideNextActionWhenInSpace`, so a rescue that did not work owned
  the whole bot. Past the bound it answers `Nothing` and the rest of the tree
  runs with the menu still up -- `MessageBoxStandoff`'s posture, for its reason.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, REPO_DIR, elm_json_literal, open_repl

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The live layout, from the client mid-loop.
PANEL = (40, 63, 390, 355)
MENU_OVER_THE_POINT = (510, 233, 291, 310)

_address = iter(range(700000, 999999))


def node(type_name, entries=None, children=(), region=None):
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def context_menu(region):
    """A menu with one entry, at the region the client drew it."""
    x, y, width, height = region
    return node("ContextMenu", {}, [
        node("Container", {"_name": "entries"}, [
            node("ContextMenuEntry", {"_setText": "Clear All Waypoints"},
                 region=(0, 0, width, 30)),
        ], region=(0, 0, width, height)),
    ], region=region)


def reading_tree(menus=()):
    """Menus hang under a root child named `l_menu`, which is where
    `parseContextMenusFromUITreeRoot` looks -- a menu anywhere else in the tree
    is not a menu as far as the bot is concerned."""
    return node("UIRoot", {}, [
        node("InfoPanelContainer", {}, [], region=PANEL),
        node("Container", {"_name": "l_menu"},
             [context_menu(m) for m in menus],
             region=(0, 0, 3840, 2125)),
    ], region=(0, 0, 3840, 2125))


def reading_binding(name, menus=()):
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree"
            % (name, elm_json_literal(reading_tree(menus))))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    return re.sub(r"\s+", " ", text)


class SaxratRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-straymenu-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class ThePointStepsClearOfTheMenuTest(unittest.TestCase):
    """The bug: the dismissal click landing inside the menu it must dismiss."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)
        cls.definitions = [
            reading_binding("noMenu"),
            reading_binding("menuOverPoint", [MENU_OVER_THE_POINT]),
            "pointOf r = r |> Maybe.andThen emptyPointBesideTheInfoPanel"
            " |> Maybe.map (\\p -> String.fromInt p.x ++ \",\" ++ String.fromInt p.y)"
            " |> Maybe.withDefault \"NONE\"",
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate(["noMenu /= Nothing", "menuOverPoint /= Nothing"],
                               definitions=self.definitions),
            [True, True])

    def test_the_menu_fixture_really_covers_the_old_point(self):
        """Otherwise the case below proves nothing about the real failure."""
        panel_x, panel_y, panel_w, panel_h = PANEL
        old_point = (panel_x + panel_w + 80, panel_y + panel_h // 2)
        mx, my, mw, mh = MENU_OVER_THE_POINT
        self.assertTrue(mx <= old_point[0] <= mx + mw
                        and my <= old_point[1] <= my + mh,
                        "fixture does not reproduce the live overlap")

    def test_with_no_menu_it_is_beside_the_panel_as_before(self):
        panel_x, panel_y, panel_w, panel_h = PANEL
        self.assertEqual(
            self.repl.strings(["pointOf noMenu"], definitions=self.definitions),
            ["%d,%d" % (panel_x + panel_w + 80, panel_y + panel_h // 2)])

    def test_a_menu_over_the_point_pushes_the_click_clear_of_it(self):
        answer = self.repl.strings(["pointOf menuOverPoint"],
                                   definitions=self.definitions)[0]
        self.assertNotEqual(answer, "NONE", "it must still find somewhere")
        x, y = (int(part) for part in answer.split(","))
        mx, my, mw, mh = MENU_OVER_THE_POINT
        covered = mx <= x <= mx + mw and my <= y <= my + mh
        self.assertFalse(covered,
                         "the dismissal click is inside the menu again: %s" % answer)


class TheDismissalIsALeftClickOnlyTest(unittest.TestCase):
    """The right-click is what created the menu, so it is gone."""

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.branch = self._declaration("clearStrayContextMenu")

    def _declaration(self, name):
        match = re.search(r"^%s :.*?(?=\n\n\n)" % re.escape(name),
                          self.source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise AssertionError("no declaration named " + name)
        return collapsed(match.group(0))

    def test_the_branch_no_longer_right_clicks(self):
        self.assertNotIn("MouseButtonRight", self.branch)

    def test_the_branch_still_left_clicks(self):
        self.assertIn("MouseButtonLeft", self.branch)

    def test_the_escape_fallback_is_kept_for_a_reading_with_no_anchor(self):
        self.assertIn("vkey_ESCAPE", self.branch)


class TheRescueIsBoundedTest(unittest.TestCase):
    """It sits at the head of the in-space tree, so it may not run forever."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _stray(self, ticks):
        """`ticks` may be a number or an Elm expression yielding one.

        The boundary cases below name the shipped declarations rather than the
        numbers they currently hold: this threshold has been retuned once
        already -- 3 to 12, to clear `enterAnomaly`'s own 8-reading lookback --
        and a case that hard-codes the old value fails on a change that is
        right, which teaches the reader to edit the number rather than to check
        the rule.
        """
        return ('strayContextMenuIsStray { stuckTicks = %s,'
                ' ammoSwapOwnsTheMenu = False }' % ticks)

    def test_it_arms_at_the_threshold_and_not_before(self):
        self.assertEqual(
            self.repl.evaluate([
                self._stray("strayContextMenuStuckTicksThreshold - 1"),
                self._stray("strayContextMenuStuckTicksThreshold"),
                self._stray("strayContextMenuStuckTicksThreshold + 1")]),
            [False, True, True])

    def test_it_clears_the_cascade_lookback_it_was_raised_for(self):
        """Why the threshold moved, asserted rather than left in a comment.

        Below `enterAnomaly`'s 8-reading lookback the clearer was discarding a
        cascade still inside its own patience and clicking beside the info
        panel -- the rescue reproducing what it rescues from, a third time.
        """
        self.assertEqual(
            self.repl.evaluate(["strayContextMenuStuckTicksThreshold > 8"]),
            [True])

    def test_it_stands_aside_past_the_give_up(self):
        self.assertEqual(
            self.repl.evaluate([
                "strayContextMenuGiveUpTicks"
                " == strayContextMenuStuckTicksThreshold * 20",
                self._stray("strayContextMenuGiveUpTicks - 1"),
                self._stray("strayContextMenuGiveUpTicks"),
                self._stray("strayContextMenuGiveUpTicks * 10")]),
            [True, True, False, False])

    def test_run_18_would_have_stood_aside(self):
        """10,845 attempts is what having no bound cost."""
        self.assertEqual(
            self.repl.evaluate([self._stray(10845)]), [False])

    def test_the_ammo_swap_still_owns_its_own_menu(self):
        self.assertEqual(
            self.repl.evaluate([
                'strayContextMenuIsStray { stuckTicks = 5,'
                ' ammoSwapOwnsTheMenu = True }']),
            [False])

    def test_the_bound_is_written_as_a_multiple_of_the_threshold(self):
        source = source_of(SAXRAT_BOT_ELM)
        match = re.search(
            r"strayContextMenuGiveUpTicks =\s*\n\s*(.+)", source)
        self.assertIsNotNone(match)
        self.assertIn("strayContextMenuStuckTicksThreshold", match.group(1),
                      "a bare number lets the two drift apart")


if __name__ == "__main__":
    unittest.main()
