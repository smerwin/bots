"""Tests for a completed gate jump opening the landing-close window and
refilling the give-up budgets #428 already refills on a warp.

`wingman_run22.log` is the live evidence. Chained gate jumps behind the fleet
commander left `shipIsApproaching` reading `True` for over 600 consecutive
lines while the commander's own distance grew monotonically from 3,014 m to
18 km -- the ship still nominally "approaching" a target the jump had already
left behind. The cause is `warpJustEnded` (#194 / #205): it answers about the
manoeuvre `Warp` only, via `shipWarpingFromReading`, and a gate jump never
reads as that manoeuvre at any point -- the client names it `Jump` throughout,
so `shipWarpingFromReading` is `Just False` from the first reading of the jump
to the last, and the `Just True -> not Just True` transition `warpJustEnded`
looks for never happens. `landingCloseAfterReading` (#397) therefore never
re-armed on a jump, and `approachFleetCommanderStep` kept reading whatever
manoeuvre state survived from before the jump.

**This is #397's own gap, and #428 is a second one layered on top of it.**
`shipWarpingFromReading` and `warpJustEnded` are deliberately not widened in
place -- that shape backs `otherPilotArrivalWindowReadings` (#194), which is
about landing in an anomaly after a warp specifically, and a gate jump does not
put a ship in one. Instead `shipTravelingFromReading` (`Warp` or `Jump`
together) and `travelJustEnded` are their own functions, and
`weJustFinishedTraveling` is what opens `closingOnTheCommanderSinceLanding` and
feeds both of #428's `askedReadingsRefilledByLanding` call sites --
`approachAskedReadingsCarriedIn` and `fleetMateWarpAskedReadingsCarriedIn`.
Landing from #428's own corpus (a warp) is untouched, since
`weJustFinishedTraveling` answers `True` there too; what changes is that a
landing from a jump now answers the same way, where `weJustFinishedWarping`
never did.

**Without the refill half, the reopened window would only trade one stale
give-up for another.** #428 already found this shape for warps -- a window
re-armed onto a budget that never reset is a give-up that can never be taken
back -- and it applies identically to jumps: a wingman who exhausts the
approach ask at long range and then jumps to within a few hundred metres of the
commander gets nothing from the landing unless the budget it inherits is
fresh.

**Deliberately out of scope, matching #428's own boundary.** The stray-window
clause (`CloseAWindowLeftOverTheClient`) is untouched here -- that is #426's
shape. So is `#194`'s own arrival window (`readingsSinceWarpEnded`,
`arrivalWindowIsOpen`), which is measured against warps specifically and stays
that way; `TheScopeBoundaryIsUnchangedTest` pins both a jump landing not
resetting it and the source not reading the wider trigger.

**The jump indication text is not a captured client string, unlike
`WARPING_INDICATION`'s `"Warp Drive Active"` (saxrat run 29, used in
`test_arrival_pilot_window.py`).** No live capture of a gate-jump indication
exists in this repo yet. `parseShipUIIndication` matches by
`String.contains "Jump"` against every display text under the indication
container (`EveOnline/ParseUserInterface.elm`), so any text containing the
word is read identically by the real parser; `"Jump Drive Active"` is used
here only because it mirrors the captured warp string's shape. That the
*matcher* is substring-based is read straight out of the parser source rather
than assumed, in `test_the_parser_matches_jump_by_substring`.

**Confirmed by mutation.** Reverting either `approachAskedReadingsCarriedIn`
or `fleetMateWarpAskedReadingsCarriedIn` back to
`justLanded = weJustFinishedWarping` -- #428's own shipped shape, before this
change -- fails `test_a_jump_landing_lets_the_approach_ask_again`
(respectively `..._the_fleet_mate_warp_ask_again`) and
`test_the_refill_is_keyed_on_the_wider_travel_trigger`. Reverting
`closingOnTheCommanderSinceLandingNow`'s `justLanded` the same way fails
`test_a_jump_opens_the_window_a_warp_already_opens` and the window half of
`test_the_refill_is_keyed_on_the_wider_travel_trigger`. Pointing
`shipTravelingFromReading` at `Warp` alone (dropping the `Jump` disjunct)
fails `test_traveling_is_true_for_a_jump_exactly_as_for_a_warp` and every
folded session below that lands via a jump. Widening `shipWarpingFromReading`
itself to accept `Jump` -- the tempting one-line fix -- would pass every case
above but fails `test_the_arrival_window_does_not_open_on_a_jump_landing`,
which is #194's own boundary.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import reading_binding  # noqa: E402
from test_wingman_landing_refills_the_budget import (  # noqa: E402
    APPROACH_SESSION_READINGS, MATE_SESSION_READINGS, WINGMAN_BOT_ELM,
    WingmanRepl, approach_grid, collapsed, declaration, indented_let_binding,
    mate_grid, record_field)

# Not a captured client string -- see the module docstring. Any text
# containing "Jump" reads identically through the real parser's substring
# match, so the shape (not the exact wording) is what matters here.
JUMPING_INDICATION = "Jump Drive Active"

# `approach_grid` always appends a ship UI; a reading with none at all is a
# different fixture, built by dropping it rather than by a fourth argument
# `approach_grid` was never asked to grow.
NO_SHIP_UI = ("noShipUI", approach_grid(None)[:-1])


class TheTravelingRuleTest(unittest.TestCase):
    """`shipTravelingFromReading` and `travelJustEnded` on their own,
    executed -- and `warpJustEnded` asked of the same transition, so the
    defect this change fixes is run rather than described."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", approach_grid(None)),
            reading_binding("warping", approach_grid("Warp Drive Active")),
            reading_binding("jumping", approach_grid(JUMPING_INDICATION)),
            reading_binding("orbiting", approach_grid("Orbiting")),
            reading_binding("approaching", approach_grid("Approaching")),
            reading_binding(NO_SHIP_UI[0], NO_SHIP_UI[1]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate([
                "(onGrid |> Maybe.andThen .shipUI) /= Nothing",
                "(jumping |> Maybe.andThen .shipUI) /= Nothing",
                "(noShipUI |> Maybe.andThen .shipUI) == Nothing",
            ], definitions=self.definitions),
            [True] * 3)

    def test_the_parser_matches_jump_by_substring(self):
        """Read out of `EveOnline/ParseUserInterface.elm` rather than
        assumed, since the jump indication text used everywhere below is not
        a captured client string -- see the module docstring."""
        with open(
            os.path.join(
                os.path.dirname(WINGMAN_BOT_ELM), "EveOnline",
                "ParseUserInterface.elm"),
            encoding="utf-8",
        ) as handle:
            source = handle.read()
        body = collapsed(
            declaration(source, "parseShipUIIndication indicationUINode ="))
        self.assertIn('( "Jump", ManeuverJump )', body)
        self.assertIn("String.contains pattern", body)

    def test_traveling_is_true_for_a_jump_exactly_as_for_a_warp(self):
        self.assertEqual(
            self.repl.evaluate([
                "(warping |> Maybe.map shipTravelingFromReading)"
                " == Just (Just True)",
                "(jumping |> Maybe.map shipTravelingFromReading)"
                " == Just (Just True)",
                "(orbiting |> Maybe.map shipTravelingFromReading)"
                " == Just (Just False)",
                "(approaching |> Maybe.map shipTravelingFromReading)"
                " == Just (Just False)",
                "(onGrid |> Maybe.map shipTravelingFromReading)"
                " == Just Nothing",
                "(noShipUI |> Maybe.map shipTravelingFromReading)"
                " == Just Nothing",
            ], definitions=self.definitions),
            [True] * 6)

    def test_a_jump_landing_is_seen_where_a_warp_landing_already_was(self):
        """The transition both functions are asked about: the previous
        reading named the manoeuvre, this one names none (a landing), and a
        ship UI is present now to say so."""
        travel_end_seen = (
            "travelEndSeen = \\before after -> Maybe.map2"
            " (\\b a -> travelJustEnded"
            " { travelingLastReading = shipTravelingFromReading b"
            ", readingNow = a })"
            " before after")
        self.assertEqual(
            self.repl.evaluate([
                "travelEndSeen warping onGrid == Just True",
                "travelEndSeen jumping onGrid == Just True",
                "travelEndSeen jumping jumping == Just False",
                "travelEndSeen jumping noShipUI == Just False",
            ], definitions=self.definitions + [travel_end_seen]),
            [True] * 4)

    def test_the_pre_existing_trigger_misses_exactly_the_jump_case(self):
        """`wingman_run22.log`'s own shape, run rather than quoted:
        `warpJustEnded` answers `True` at the end of a warp and `False` at the
        end of a jump, because a jump is never
        `shipWarpingFromReading == Just True` at any point for it to
        transition away from. This is the gap `travelJustEnded` closes -- the
        case above asks the same two transitions of the wider function and
        gets `True` both times."""
        warp_end_seen = (
            "warpEndSeen = \\before after -> Maybe.map2"
            " (\\b a -> warpJustEnded"
            " { warpingLastReading = shipWarpingFromReading b"
            ", readingNow = a })"
            " before after")
        self.assertEqual(
            self.repl.evaluate([
                "warpEndSeen warping onGrid == Just True",
                "warpEndSeen jumping onGrid == Just False",
            ], definitions=self.definitions + [warp_end_seen]),
            [True, True])


class TheApproachBudgetIsRefilledOnAJumpTest(unittest.TestCase):
    """#428's headline test, replayed with a jump in place of the warp.

    Same fixtures, same session shape, same control as
    `test_wingman_landing_refills_the_budget.TheApproachBudgetIsRefilledTest`
    -- only the manoeuvre naming the landing changes.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", approach_grid(None)),
            reading_binding("jumping", approach_grid(JUMPING_INDICATION)),
        ]
        cls.landed = ("[ ( %d, onGrid ), ( 1, jumping ), ( 1, onGrid ) ]"
                      % APPROACH_SESSION_READINGS)
        cls.never_left = ("[ ( %d, onGrid ) ]"
                          % (APPROACH_SESSION_READINGS + 2))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == %d"
                % (self.landed, APPROACH_SESSION_READINGS + 2),
                "(jumping |> Maybe.map shipTravelingFromReading)"
                " == Just (Just True)",
                "(jumping |> Maybe.map shipWarpingFromReading)"
                " == Just (Just False)",
                "(onGrid |> Maybe.andThen fleetCommanderOverviewEntry)"
                " /= Nothing",
                "(jumping |> Maybe.andThen fleetCommanderOverviewEntry)"
                " /= Nothing",
            ], definitions=self.definitions),
            [True] * 5)

    def test_the_budget_is_still_spent_without_a_landing(self):
        """The control this class turns on: without it a bot that never
        counted anything would pass the case below for the wrong reason."""
        self.assertEqual(
            self.repl.evaluate([
                "approachFleetCommanderHasBeenGivenUpOn"
                " (memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings)"
                % self.never_left,
            ], definitions=self.definitions),
            [True])

    def test_a_jump_landing_lets_the_approach_ask_again(self):
        """#428's own fix answered this for a warp; a wingman who catches up
        by jumping rather than warping gets the same working budget."""
        self.assertEqual(
            self.repl.evaluate([
                "not (approachFleetCommanderHasBeenGivenUpOn"
                " (memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings))" % self.landed,
                "(memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings) == 1" % self.landed,
            ], definitions=self.definitions),
            [True, True])

    def test_a_jump_opens_the_window_a_warp_already_opens(self):
        """#428's own assertion, replayed: the reading the jump lands on is
        the reading `closingOnTheCommanderSinceLanding` re-arms on."""
        self.assertEqual(
            self.repl.evaluate([
                "(memoryOver defaultBotSettings %s"
                " |> .closingOnTheCommanderSinceLanding)" % self.landed,
                "(memoryOver defaultBotSettings %s"
                " |> .closingOnTheCommanderSinceLanding)" % self.never_left,
            ], definitions=self.definitions),
            [True, False])


class TheFleetMateBudgetIsRefilledOnAJumpTest(unittest.TestCase):
    """The sibling arm, on a jump rather than a warp -- three of #428's own
    four pilots read this give-up beside the approach's."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("mateOnGrid", mate_grid(None)),
            reading_binding("mateJumping", mate_grid(JUMPING_INDICATION)),
        ]
        cls.landed = ("[ ( %d, mateOnGrid ), ( 1, mateJumping )"
                      ", ( 1, mateOnGrid ) ]" % MATE_SESSION_READINGS)
        cls.never_left = ("[ ( %d, mateOnGrid ) ]"
                          % (MATE_SESSION_READINGS + 2))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_budget_is_still_spent_without_a_landing(self):
        self.assertEqual(
            self.repl.evaluate([
                "fleetMateWarpHasBeenGivenUpOn"
                " (memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings)" % self.never_left,
            ], definitions=self.definitions),
            [True])

    def test_a_jump_landing_lets_the_fleet_mate_warp_ask_again(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (fleetMateWarpHasBeenGivenUpOn"
                " (memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings))" % self.landed,
                "(memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings) == 1" % self.landed,
            ], definitions=self.definitions),
            [True, True])


class TheScopeBoundaryIsUnchangedTest(unittest.TestCase):
    """What this deliberately does not touch, pinned the way #428 pins its
    own out-of-scope clause -- so a later change has to be somebody's
    decision rather than drift."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", approach_grid(None)),
            reading_binding("warping", approach_grid("Warp Drive Active")),
            reading_binding("jumping", approach_grid(JUMPING_INDICATION)),
        ]
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_arrival_window_does_not_open_on_a_jump_landing(self):
        """#194's `otherPilotArrivalWindowReadings` is about landing in an
        anomaly after a **warp**; a jump landing must leave it exactly as a
        session with no warp at all does."""
        self.assertEqual(
            self.repl.evaluate([
                "(memoryOver defaultBotSettings"
                " [ ( 1, warping ), ( 1, onGrid ) ]"
                " |> .readingsSinceWarpEnded) == Just 0",
                "(memoryOver defaultBotSettings"
                " [ ( 1, jumping ), ( 1, onGrid ) ]"
                " |> .readingsSinceWarpEnded) == Nothing",
            ], definitions=self.definitions),
            [True, True])

    def test_the_refill_is_keyed_on_the_wider_travel_trigger(self):
        for binding in ("approachAskedReadingsCarriedIn",
                        "fleetMateWarpAskedReadingsCarriedIn"):
            with self.subTest(binding=binding):
                body = collapsed(indented_let_binding(self.source, binding))
                self.assertIn("justLanded = weJustFinishedTraveling", body)
        window = collapsed(indented_let_binding(
            self.source, "closingOnTheCommanderSinceLandingNow"))
        self.assertIn("justLanded = weJustFinishedTraveling", window)
        arrival = collapsed(
            indented_let_binding(self.source, "readingsSinceWarpEnded"))
        self.assertIn("weJustFinishedWarping", arrival)
        self.assertNotIn("weJustFinishedTraveling", arrival)

    def test_shipTravelingFromReading_admits_both_maneuvers(self):
        """Sliced from the declaration rather than asked through the repl, so
        a version that reintroduced `shipWarpingFromReading`'s
        single-manoeuvre shape under this name -- which the folded-session
        cases above cannot distinguish from the real thing, since they only
        ever land via a jump or a warp and never assert the two disagree --
        still fails here."""
        body = collapsed(declaration(
            self.source, "shipTravelingFromReading readingFromGameClient ="))
        self.assertIn("ManeuverWarp", body)
        self.assertIn("ManeuverJump", body)

    def test_the_new_memory_field_is_wired_separately_from_warping(self):
        """`shipTravelingInLastReading` is its own field, not a rename of
        `shipWarpingInLastReading` -- #194's warp-only reading and this one
        have to be able to disagree, which a single field could not do."""
        body = collapsed(declaration(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore ="))
        self.assertIn(", shipTravelingInLastReading = shipIsTraveling", body)
        self.assertIn(", shipWarpingInLastReading = shipIsWarping", body)
        self.assertIn("shipWarpingInLastReading : Maybe Bool", self.source)
        self.assertIn("shipTravelingInLastReading : Maybe Bool", self.source)


if __name__ == "__main__":
    unittest.main()
