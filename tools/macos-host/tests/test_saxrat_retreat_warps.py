"""Tests for saxrat's retreat warping out rather than docking through a menu.

Issue #222. `runAway` was a literal alias for `tetherAtStructure` -- not "calls",
not "falls back to" -- so the branch that means *this ship is dying, leave now*
was the same one that means *nothing to do here, sit somewhere safe*, and it
inherited that branch's surroundings-menu cascade and its entry priority, which
prefers **Dock** over Warp.

Docking is the slowest thing on that list. A dock is a run-in the ship has to fly
(#99 measured one at 486 seconds); a warp to a celestial is instant once
commanded.

Run 35 is what that cost. The retreat fired correctly and then spent 90 seconds
and 36 decision blocks driving the cascade towards a station while taking about
57 hitpoints a second. The armour went 100, 99, 79, 35, 23, 11, 0 and the Coercer
died with the menu still open. **Not one of those 36 blocks was in warp** -- 17
were moving the mouse toward a station entry and 8 were waiting for a menu that
had not rendered.

The mission runner already solved this and its own `tetherAtStructure` comment
records the same shape from its side: nineteen decisions clicking menu entries
while armour fell from 58% to 31%. This is that solution ported, so the two bots
retreat alike.

**What is deliberately kept.** The cascade is still the answer to *nothing at AU
range on the overview*, because a grid with no celestial on it has nothing to warp
to and the menu is then the only thing left. It is a last resort rather than the
first move.

The rules are executed through the real `Bot.elm` in `elm repl`, against readings
built by the real `EveOnline.ParseUserInterface`.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, node, overview, source_of)


class RetreatRepl(SaxratRepl):
    pass


def celestial_row(name, distance):
    """`overview()` takes (distance, name, type) in the client's column order."""
    return (distance, name, "Planet")


class WhatCountsAsSomewhereToWarpToTest(unittest.TestCase):
    """`escapeCelestialsOnOverview`, executed against real parsed readings."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RetreatRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def names_offered(self, rows):
        return self.repl.strings(
            ['(reading |> Maybe.map (escapeCelestialsOnOverview'
             ' >> List.filterMap .objectName >> String.join "|")'
             ' |> Maybe.withDefault "PARSE FAILED")'],
            [RetreatRepl.reading_binding("reading", [overview(rows)])])[0]

    def test_an_au_distance_is_somewhere_to_go(self):
        self.assertEqual(
            self.names_offered([celestial_row("Safilbab I", "4.2 AU")]),
            "Safilbab I")

    def test_a_row_on_this_grid_is_not(self):
        """Warping to something 40 km away is not leaving."""
        self.assertEqual(
            self.names_offered([celestial_row("Sentry Tower", "40,000 m")]), "")

    def test_the_unit_is_the_clients_own_rather_than_a_name(self):
        """The mission runner matched a *station* by name and picked up site
        scenery called `... - 1`, then waited 119 readings for a Dock button
        that scenery never offers while its armour drained to nothing."""
        offered = self.names_offered([
            celestial_row("Some Structure - 1", "12,000 m"),
            celestial_row("Safilbab VII", "31.8 AU"),
        ])
        self.assertEqual(offered, "Safilbab VII")

    def test_a_grid_with_nothing_far_away_offers_nothing(self):
        self.assertEqual(
            self.names_offered([celestial_row("Centii Ravener", "8,100 m")]), "")


class TheRetreatCommandsAWarpTest(unittest.TestCase):
    """What the branch does with a celestial, read out of the branch itself.

    The failure this pins is the one #222 is: a retreat that looks correct in the
    log while driving something slow. So what is asserted is which mechanism it
    reaches for, not merely that it says "Get out".
    """

    @classmethod
    def setUpClass(cls):
        cls.branch = collapsed(body_of(source_of(SAXRAT_BOT_ELM), "runAway"))

    def test_it_presses_the_panels_warp_button(self):
        self.assertIn('selectedItemButtonNamed context.readingFromGameClient'
                      ' "selectedItemWarpTo"', self.branch)

    def test_it_selects_the_celestial_before_pressing(self):
        """The panel acts on whatever is selected, so pressing without checking
        is how a retreat warps somewhere nobody chose."""
        self.assertIn("selectedItemIsOverviewEntry context.readingFromGameClient"
                      " celestial", self.branch)
        self.assertLess(
            self.branch.index("selectedItemIsOverviewEntry"),
            self.branch.index('"selectedItemWarpTo"'),
            "the panel is pressed before it is known to be showing the celestial")

    def test_the_drones_come_home_before_the_warp(self):
        """A warp abandons whatever is still in space."""
        self.assertIn("returnDronesToBay context", self.branch)

    def test_the_cascade_is_only_the_answer_to_having_nowhere_to_go(self):
        """Kept, but as a last resort. A grid with no celestial has nothing to
        warp to, and the menu is then all that is left."""
        before_first_cascade = self.branch[:self.branch.index("tetherAtStructure")]
        self.assertIn("escapeCelestialsOnOverview", before_first_cascade)
        self.assertIn("nothing at AU range", self.branch)

    def test_it_is_no_longer_an_alias(self):
        """`runAway = tetherAtStructure` is the defect itself."""
        self.assertNotRegex(
            self.branch, r"runAway\s*=\s*tetherAtStructure\b")

    def test_it_says_where_it_is_going(self):
        """A retreat that cannot be read afterwards is how run 35 took a log
        replay to diagnose."""
        self.assertIn("Get out -- warp to", self.branch)


class TheEscapeChoiceRotatesTest(unittest.TestCase):
    """A retreat that has not worked tries a different corner of the system.

    Rotating every reading would never let a warp start; not rotating at all
    would re-issue a warp to the celestial that did not help. The counter it
    reads is advanced in the memory update, which is the only thing that runs on
    every reading whatever the bot is doing.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.collapsed = collapsed(cls.source)
        cls.branch = collapsed(body_of(cls.source, "runAway"))

    def test_the_choice_is_taken_at_a_rotating_index(self):
        self.assertIn("listElementAtWrappedIndex", self.branch)
        self.assertIn("context.memory.readingsCount //"
                      " runAwayCelestialStickyReadings", self.branch)

    def test_the_stickiness_is_named_rather_than_a_bare_number(self):
        self.assertRegex(
            self.collapsed,
            r"runAwayCelestialStickyReadings : Int"
            r" runAwayCelestialStickyReadings = \d+")

    def test_it_is_long_enough_for_a_warp_to_start(self):
        match = re.search(
            r"runAwayCelestialStickyReadings = (\d+)", self.collapsed)
        self.assertIsNotNone(match)
        readings = int(match.group(1))
        self.assertGreater(
            readings, 3,
            "a choice that changes every few readings never lets a warp start")
        self.assertLess(
            readings, 60,
            "a choice that never changes re-issues the warp that did not help")

    def test_the_counter_advances_on_every_reading(self):
        """In the memory update, not in the branch -- a counter advanced where
        the retreat is decided would stop advancing whenever something above
        held the tree, which is #102's shape."""
        update = collapsed(body_of(self.source,
                                   "updateMemoryForNewReadingFromGame"))
        self.assertIn("botMemoryBefore.readingsCount + 1", update)

    def test_nothing_else_reads_the_counter(self):
        """One reader, so a second opinion about the rotation cannot appear."""
        readers = re.findall(r"memory\.readingsCount", self.collapsed)
        self.assertEqual(
            len(readers), 1,
            "expected the retreat's rotation to be the only reader of"
            " readingsCount")


if __name__ == "__main__":
    unittest.main()
