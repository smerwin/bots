"""The retreat leaves by the fastest exit, not the one that docks.

`runAway` was an alias -- not a caller -- for `tetherAtStructure`, so the branch
meaning *this ship is dying, leave now* was the same one meaning *nothing to do
here, sit somewhere safe*, and it inherited that branch's surroundings-menu
cascade with `Dock` at the top of its entry priority.

Run 35 died inside it. The armour guard fired 90 seconds before the loss, into a
grid that was quiet:

    first 10 s of the retreat      0 hp
    first 20 s                     0 hp
    first 30 s                    23 hp
    the last 30 s              2,124 hp   (73% of the whole episode)

and the bot spent that free window opening context menus -- `Move mouse to entry
'Safilbab I (Barren)'` seventeen times, not one of its 36 blocks in warp. Nothing
scrambled or disrupted the ship at any point in the three minutes before it died,
so the warp was available throughout: a warp commanded when the guard fired leaves
having taken 23 hitpoints.

These cases execute the two pure rules through the real `Bot.elm`, build the
overview rows with the **real** `EveOnline.ParseUserInterface`, and read the
wiring out of the source. The corpus half re-derives run 35's own numbers, as
relations rather than as the figures above.
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)
from test_saxrat_learned_lock_range import overview_rows

# An AU distance is what identifies something worth warping to: the parser reads
# only `m` and `km`, so `objectDistanceInMeters` is an `Err` for these and the
# placeholder that makes them read as merely far is exactly the tell.
CELESTIALS = [("8.0 AU", "Amarr - Star", "101", False),
              ("9.8 AU", "Amarr VI (Zorast)", "102", False)]
ON_GRID = [("12,000 m", "Centii Manslayer", "201", False),
           ("2,366 m", "Jaswelu", "202", False)]


class TheRuleAnswersTheTwoStepInOrder(unittest.TestCase):
    """`retreatWarpStep`. The panel acts on whatever is selected, so the order
    is load-bearing: pressing before selecting warps to the previous object."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-retreat-warp-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, shows, offers):
        return ("retreatWarpStep { panelShowsTheCelestial = %s, panelOffersWarpTo = %s }"
                % ("True" if shows else "False", "True" if offers else "False"))

    def test_nothing_selected_selects_first(self):
        answers = self.repl.evaluate([
            "%s == SelectTheCelestial" % self.step(False, False),
            "%s == SelectTheCelestial" % self.step(False, True),
        ])
        self.assertEqual([True, True], answers,
                         "with the panel showing something else, pressing Warp To "
                         "would warp to whatever that something else is")

    def test_selected_but_no_button_waits(self):
        self.assertTrue(
            self.repl.evaluate(["%s == WaitForTheWarpButton" % self.step(True, False)])[0])

    def test_selected_and_offered_presses(self):
        self.assertTrue(
            self.repl.evaluate(["%s == PressWarpTo" % self.step(True, True)])[0])

    def test_every_combination_answers_exactly_one_step(self):
        """A rule answering two things at once, or none, would pass a case
        written against whichever constructor that case happened to name."""
        expressions = []
        for shows in (False, True):
            for offers in (False, True):
                expressions.append(
                    "(List.length (List.filter identity [ %s == SelectTheCelestial"
                    ", %s == WaitForTheWarpButton, %s == PressWarpTo ]) == 1)"
                    % (self.step(shows, offers), self.step(shows, offers),
                       self.step(shows, offers)))
        self.assertEqual([True] * 4, self.repl.evaluate(expressions))


class TheCelestialsAreTheAuRowsThatAreDrawn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-retreat-celestials-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def names(self, rows, hidden=(), stacked=False):
        binding = SaxratRepl.reading_binding(
            "reading", [overview_rows(rows, hidden=hidden, stacked=stacked)])
        expression = (
            "(reading |> Maybe.map (\\r -> r.overviewWindows"
            " |> List.concatMap .entries |> List.filter overviewEntryIsDisplayed"
            " |> List.filter (.objectDistance >> Maybe.map (String.toUpper >>"
            " String.contains \"AU\") >> Maybe.withDefault False)"
            " |> List.filterMap .objectName |> String.join \",\")"
            " |> Maybe.withDefault \"NO READING\")")
        return self.repl.strings([expression], [binding])[0]

    def test_au_rows_are_escape_candidates(self):
        self.assertEqual("Amarr - Star,Amarr VI (Zorast)", self.names(CELESTIALS))

    def test_rows_on_grid_are_not(self):
        self.assertEqual("", self.names(ON_GRID),
                         "warping to something 12 km away is not leaving the grid")

    def test_a_hidden_row_is_never_a_candidate(self):
        """The overview virtualises: a row that is not drawn reports a region
        belonging to whatever was recycled into its place, so selecting one
        acts on the wrong object."""
        self.assertEqual("Amarr VI (Zorast)",
                         self.names(CELESTIALS, hidden=(0,), stacked=True))

    def test_a_mixed_overview_keeps_only_the_au_rows(self):
        self.assertEqual("Amarr - Star", self.names([CELESTIALS[0]] + ON_GRID))


class TheExitIsThePanelAndNotTheDockCascade(unittest.TestCase):
    """The wiring, read from the source -- `runAway` needs a whole context."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(body_of(cls.source, "runAway"))

    def test_run_away_is_no_longer_an_alias_for_tethering(self):
        self.assertNotIn("runAway = tetherAtStructure", collapsed(self.source),
                         "the alias is what made the emergency retreat and "
                         "'park somewhere safe' the same code path")

    def test_it_presses_the_panel_warp_button(self):
        self.assertIn('selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo"',
                      self.branch)

    def test_it_selects_the_row_before_pressing(self):
        self.assertIn("selectedItemIsOverviewEntry context.readingFromGameClient celestial",
                      self.branch)
        self.assertIn("clickUiElement celestial.uiNode", self.branch)

    def test_it_never_prefers_docking(self):
        self.assertNotIn('"Dock"', self.branch)
        self.assertNotIn("selectedItemDock", self.branch)

    def test_tethering_is_only_the_no_celestial_fallback(self):
        """Reached when the overview offers nothing at AU range -- the case
        where there is no celestial to warp to -- and nowhere else."""
        self.assertEqual(1, self.branch.count("tetherAtStructure context"))
        before = self.branch.split("tetherAtStructure context")[0]
        self.assertIn("nothing at AU range", before)

    def test_the_drones_still_come_home_first(self):
        self.assertIn("ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping",
                      self.branch)

    def test_tether_at_structure_itself_is_untouched(self):
        """It is still right for the wind-down and the no-route dead end."""
        tether = collapsed(body_of(self.source, "tetherAtStructure"))
        self.assertIn("useContextMenuCascadeOnListSurroundingsButton", tether)
        self.assertIn('withTextContainingIgnoringCase "Dock"', tether)

    def test_the_choice_rotates_rather_than_re_commanding_one_celestial(self):
        self.assertIn("listElementAtWrappedIndex", self.branch)
        self.assertIn("runAwayCelestialStickyReadings", self.branch)

    def test_the_counter_it_rotates_on_advances_every_reading(self):
        update = collapsed(body_of(self.source, "updateMemoryForNewReadingFromGame"))
        self.assertIn("readingsCount = botMemoryBefore.readingsCount + 1", update)


def run35():
    path = os.path.join(EVE_BOT_LOGS, "saxrat_run35.log")
    if not os.path.exists(path):
        raise unittest.SkipTest(
            "no saxrat_run35.log in %s -- the run this change is derived from "
            "is not on this machine" % EVE_BOT_LOGS)
    return path


class Run35IsWhyTheExitChanged(unittest.TestCase):
    def test_the_fatal_retreat_spent_itself_on_the_menu_and_never_warped(self):
        with open(run35(), errors="replace") as handle:
            text = handle.read()
        blocks = re.split(r"^# \[", text, flags=re.M)
        retreat = [b for b in blocks if "get out" in b]
        self.assertTrue(retreat, "run 35 has no retreat at all")
        menu = sum(1 for b in retreat
                   if "matched dock, else warp" in b or "surroundings button" in b)
        warping = sum(1 for b in retreat if "in warp" in b)
        self.assertGreater(
            menu, 0,
            "run 35's retreat should show the surroundings cascade this change removes")
        self.assertEqual(
            0, warping,
            "run 35's retreat never reached warp -- that is the whole finding, and "
            "a corpus that now shows one means this assertion is reading the wrong run")

    def test_the_ship_was_lost_and_the_pod_was_recovered(self):
        with open(run35(), errors="replace") as handle:
            text = handle.read()
        self.assertIn("SHIP LOST", text)
        self.assertIn("Pod recovery", text)


if __name__ == "__main__":
    unittest.main()
