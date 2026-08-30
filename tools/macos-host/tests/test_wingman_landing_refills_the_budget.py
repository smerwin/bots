"""Tests for a completed warp refilling the wingman's give-up budgets.

Issue #428, and it was a live outage: all four wingman pilots parked 37-46 km
from the fleet commander, every one of them printing

    Approach on the commander: CLOSING SINCE LANDING ..., GAVE UP after 40
    readings ... Commander at 46 km.

on the same reading -- committed to closing and out of readings to close with,
at once and permanently, for as long as the commander stayed on grid. Three of
the four also read `Warp to a fleet-mate: GAVE UP after 30 readings asking to
warp to 'Gal Bistot', who is on this grid`, so neither way of reaching the
commander was left.

**The defect is an asymmetry between two rules written for one event.**
`landingCloseAfterReading` (#397) answers `justLanded || closeWasOwed`, so
**every** warp that ends re-arms `closingOnTheCommanderSinceLanding` -- landing
at range is precisely when a wingman has to close. The counter that bounds the
ask had no matching reset: it reached zero only where the commander was off grid
or the ship was already approaching, so the ordinary landing took the middle
clause and held the count. The re-armed window therefore opened onto a budget
already spent, and `approachFleetCommanderStep` answered `GaveUpOnTheApproach`
for ever. `goToFleetMateWarpAskedReadings` had the same shape from the other
side: it cleared only on `fleetMateOnThisGrid == Nothing`, so a mate who stayed
on grid held the give-up for the rest of the session.

**What ships is one rule with two readers.** `askedReadingsRefilledByLanding`
answers the budget a counter carries **into** this reading, refilled by
`weJustFinishedWarping` -- the same signal that re-arms the flag, already
computed in the same memory update, so the two cannot come to disagree about
what a landing is. It is the carried-in value rather than the value written out,
so the reading a landing spends is still charged: a counter refilled *after* the
ask never charges the first reading of a landing, which is #102's defect in the
direction that under-counts.

**Explicitly out of scope, per the issue.**
`CloseAWindowLeftOverTheClient`'s membership of
`approachFleetCommanderAnswersThatSpendAReading`, and the stray-window clause
that returns it, are a separate defect that wants its own fix and its own
evidence -- the corpus says the 40 readings may have gone entirely on closing a
window rather than on any approach attempt, which is #426's shape. Cases here
pin both as unchanged so a later fix has to be somebody's decision rather than
drift.

**The two counters are folded through the real
`updateMemoryForNewReadingFromGame`** over readings the real
`EveOnline.ParseUserInterface` produced, with the control -- the same session
without the warp -- beside each. Without that control a session that ends
un-given-up says nothing, since any counter that only rises reaches any bound;
and the commander (respectively the mate) is on grid on **every** reading of
both sessions, so the reset that already existed cannot be what cleared them.

Confirmed by mutation, ten of them, each failing at least one named case. The
cases listed are the ones each mutation actually broke, taken from the run
rather than predicted:

 1. **the refill dropped from the approach counter** -- both branches reverted
    to `botMemoryBefore.approachFleetCommanderAskedReadings`, which is the
    shipped defect -- fails `test_a_landing_lets_the_approach_ask_again`,
    `test_the_landing_reading_is_still_charged_for_its_own_ask` and
    `test_the_approach_counter_reads_the_refilled_budget`;
 2. **the refill dropped from the fleet-mate counter** -- fails
    `test_a_landing_lets_the_fleet_mate_warp_ask_again`,
    `test_the_fleet_mate_counter_reads_the_refilled_budget` and
    `test_the_fleet_mate_give_up_is_asked_of_the_refilled_budget`;
 3. `askedReadingsRefilledByLanding` answering `spentBefore` whatever the
    landing says, which is the rule made inert -- fails
    `test_a_landing_refills_the_budget_and_nothing_else_does`,
    `test_the_bounds_it_refills_are_the_arms_own`, both
    `test_a_landing_lets_..._ask_again` cases and
    `test_the_landing_reading_is_still_charged_for_its_own_ask`;
 4. the rule answering `0` unconditionally, so nothing is ever bounded -- fails
    both `test_the_budget_is_still_spent_without_a_landing` controls,
    `test_a_landing_refills_the_budget_and_nothing_else_does` and
    `test_the_bounds_it_refills_are_the_arms_own`;
 5. the refill keyed on `shipIsWarping == Just False` rather than on
    `weJustFinishedWarping`, which is #194 / #205's dead condition and could
    never answer at the end of a warp -- fails
    `test_the_refill_is_keyed_on_the_corrected_warp_end_trigger` for both
    bindings and both `test_a_landing_lets_..._ask_again` cases;
 6. `askingTheCommanderForAnApproach` still predicted against the un-refilled
    count, so the counter and the arm disagree about whether the landing bought
    anything and the landing reading's own ask goes uncharged -- fails
    `test_the_step_is_predicted_against_the_refilled_budget` and
    `test_the_landing_reading_is_still_charged_for_its_own_ask`;
 7. the fleet-mate give-up asked of the un-refilled count while the branches
    return the refilled one, which reports `GAVE UP` on the reading the budget
    came back and drops the landing reading's own charge -- fails
    `test_the_fleet_mate_give_up_is_asked_of_the_refilled_budget`,
    `test_the_fleet_mate_counter_reads_the_refilled_budget` and
    `test_a_landing_lets_the_fleet_mate_warp_ask_again`;
 8. a second copy of the reset written inline into one of the two counters
    rather than both reading the shared rule -- fails
    `test_the_refill_is_one_rule_with_two_readers` and
    `test_the_refill_is_keyed_on_the_corrected_warp_end_trigger`;
 9. `CloseAWindowLeftOverTheClient` dropped from the spend list, which is the
    out-of-scope change made by accident -- fails
    `test_the_stray_window_defect_is_left_alone`;
10. the stray-window clause hoisted above the give-up, which is the other half
    of the same out-of-scope change -- fails
    `test_the_step_ladder_is_unchanged`.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    COMMANDER, HEADER_LABELS, MEMBER_ROW, fleet_window, label, node,
    reading_binding)
from test_saxrat_ported_guards import ship_ui  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The mate whose broadcast the fleet-mate half turns on. `MEMBER_ROW` is
# already a member of the captured fleet window, so the fixture is one client
# rather than two disagreeing ones.
MATE = MEMBER_ROW

# The wingman's own bounds, restated here only so a session can be made long
# enough to reach them. Every assertion asks the shipped constant.
APPROACH_SESSION_READINGS = 45
MATE_SESSION_READINGS = 35


def ship_ui_indicating(maneuver):
    """A `ShipUI` the real parser accepts, carrying a manoeuvre indication.

    `parseShipUIIndication` reads the manoeuvre out of the display texts under
    a node whose name contains `indicationcontainer`, so this is the client's
    own channel. `None` leaves the indication absent, which is what the
    captured warp-end reading looks like -- see `warpJustEnded`, which is why
    the trigger cannot ask for `Just False`.
    """
    ship = ship_ui(100, 100, 4)
    if maneuver is not None:
        ship["children"].append(
            node("Container", {"_name": "indicationContainer"},
                 [label(maneuver, (100, 100, 80, 16))],
                 region=(100, 100, 80, 16)))
    return ship


def overview_row(name, distance, y):
    """One overview row the real parser reads a name and a distance off.

    Deliberately not `test_wingman_holds_fire_on_fleetmates.overview_window`'s
    row: nothing here is about the lock indicator, and a row without one is
    what a pilot the bot has not locked looks like.
    """
    return node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
        label(distance, (10, y, 50, 16)),
        label(name, (110, y, 150, 16)),
        label(name, (310, y, 150, 16)),
        node("SpaceObjectIcon", {}, [], region=(2, y, 12, 16)),
    ], region=(0, y, 500, 16))


def overview_with(rows):
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))
    entries = [overview_row(name, distance, 20 + index * 20)
               for index, (name, distance) in enumerate(rows)]
    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def fleet_window_broadcasting(banner_text):
    """The captured fleet window with a broadcast banner in it.

    `fleetBroadcastBannerText` reads a fleet-window descendant named
    `bannerLabel`, and `is at location` is one of the two company verbs
    `fleetMateCallingForCompany` answers -- the grammar
    `parseFleetBroadcast` calls the sender-with-no-colon form.
    """
    window = fleet_window(HEADER_LABELS, [MEMBER_ROW])
    window["children"].append(
        label(banner_text, (10, 300, 300, 16), name="bannerLabel"))
    return window


def approach_grid(maneuver):
    """The commander on grid at range, and nothing else to decide on.

    No selected-item panel, so the panel never comes to show his row -- which
    is what makes the ladder spend its whole budget rather than stopping at the
    double click, and is the shape #428's four pilots were in.
    """
    return [
        fleet_window(HEADER_LABELS, [MEMBER_ROW]),
        overview_with([(COMMANDER, "46 km")]),
        ship_ui_indicating(maneuver),
    ]


def mate_grid(maneuver):
    """A fleet-mate calling for company, on this grid, with no commander row.

    The commander is deliberately absent from the overview so this session
    decides only the fleet-mate counter -- two counters moving in one fixture
    is two cases that cannot say which rule they exercised.
    """
    return [
        fleet_window_broadcasting("%s is at location Amarr" % MATE),
        overview_with([(MATE, "12 km")]),
        ship_ui_indicating(maneuver),
    ]


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what folding a session costs."""

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.PromptParser",
    )

    BINDINGS = (
        # One `UpdateMemoryContext`, exactly as the framework assembles it. The
        # screenshot's two fields are functions and nothing on this path calls
        # them, which is why a reading can be folded without one.
        "updateContext = \\settings reading ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = reading"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = settings }",
        # A session, written as `(repeats, reading)` pairs. The `filterMap` is
        # what a fixture that never parsed falls out of, which is why every
        # case using this asks `sessionLength` beside it -- see #174 for why a
        # fixture that never arrived and a rule that answered nothing look
        # identical from outside.
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "memoryOver = \\settings pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame"
        " (updateContext settings r) memory)"
        " initBotMemory",
        "followingTheMate ="
        ' { defaultBotSettings | followFleetBroadcastFrom = [ "%s" ] }' % MATE,
        "refill = \\landed spent -> askedReadingsRefilledByLanding"
        " { justLanded = landed, spentBefore = spent }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-landing-refill-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def collapsed(text):
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, from its definition to the blank line pair.

    Doc comments are stripped, so a case cannot pass on prose -- which is what
    a plain substring over a block whose comment quotes the name it forbids
    would do.
    """
    needle = "\n%s" % name
    assert needle in source, "no declaration named %r" % name
    start = source.index(needle) + 1
    body = source[start:source.index("\n\n\n", start)]
    return re.sub(r"--[^\n]*", "", body)


def indented_let_binding(source, name):
    """One `let` binding, sliced by indentation rather than by the next name.

    A reader that ends at the next ` <name> = ` stops at a record literal, and
    the bindings read here build records -- PRs #147, #156, #159 and #162 each
    paid for that once with an assertion that passed having read nothing.
    """
    match = re.search(r"\n(\s+)%s =\n" % re.escape(name), source)
    assert match is not None, "no let binding named %r" % name
    indent = len(match.group(1))
    kept = []
    for line in source[match.end():].split("\n"):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        kept.append(line)
    return re.sub(r"--[^\n]*", "", "\n".join(kept))


def record_field(source, declaration_name, field):
    """One field of the record `declaration_name` returns.

    Sliced by indentation from the `, <field> =` that opens it to the next
    line indented no further, so a field whose value is itself an `if` ladder
    is read whole and the field after it is not read at all.
    """
    body = declaration(source, declaration_name)
    match = re.search(r"\n(\s*), %s =\n" % re.escape(field), body)
    assert match is not None, "no record field named %r" % field
    indent = len(match.group(1))
    kept = []
    for line in body[match.end():].split("\n"):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        kept.append(line)
    return "\n".join(kept)


class TheRefillRuleTest(unittest.TestCase):
    """The shared rule on its own, executed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_landing_refills_the_budget_and_nothing_else_does(self):
        """Both sides, and at a spent budget as well as a fresh one: a rule
        that answered `spentBefore` always and one that answered `0` always
        each fail one of these."""
        self.assertEqual(
            self.repl.evaluate([
                "refill True 40 == 0",
                "refill True 0 == 0",
                "refill False 40 == 40",
                "refill False 7 == 7",
            ]),
            [True] * 4)

    def test_the_bounds_it_refills_are_the_arms_own(self):
        """The rule buys back a budget rather than setting one, so both bounds
        stay where their own arms put them."""
        self.assertEqual(
            self.repl.evaluate([
                "approachFleetCommanderHasBeenGivenUpOn"
                " (refill False approachFleetCommanderAskedReadingsBound)",
                "not (approachFleetCommanderHasBeenGivenUpOn"
                " (refill True approachFleetCommanderAskedReadingsBound))",
                "fleetMateWarpHasBeenGivenUpOn"
                " (refill False fleetMateWarpAskedReadingsBound)",
                "not (fleetMateWarpHasBeenGivenUpOn"
                " (refill True fleetMateWarpAskedReadingsBound))",
            ]),
            [True] * 4)


class TheApproachBudgetIsRefilledTest(unittest.TestCase):
    """#428's headline, folded through the real memory update.

    `test_the_budget_is_still_spent_without_a_landing` is the control this
    class turns on: the same grid, the same length of session, no warp -- and
    without it a bot that never counted anything would pass every other case
    here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", approach_grid(None)),
            reading_binding("warping", approach_grid("Warp Drive Active")),
        ]
        # 45 readings of asking, then one reading in warp, then the landing.
        cls.landed = ("[ ( %d, onGrid ), ( 1, warping ), ( 1, onGrid ) ]"
                      % APPROACH_SESSION_READINGS)
        cls.never_left = ("[ ( %d, onGrid ) ]"
                          % (APPROACH_SESSION_READINGS + 2))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a counter that never moved read
        alike, so what the parser made of each fixture is checked first --
        including that the commander is on the overview in **both**, which is
        what stops the reset that already existed from explaining anything."""
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == %d"
                % (self.landed, APPROACH_SESSION_READINGS + 2),
                "sessionLength %s == %d"
                % (self.never_left, APPROACH_SESSION_READINGS + 2),
                "(onGrid |> Maybe.andThen .shipUI) /= Nothing",
                "(warping |> Maybe.andThen .shipUI) /= Nothing",
                '(onGrid |> Maybe.andThen'
                ' fleetCommanderNameFromFleetWindowHeader) == Just "%s"'
                % COMMANDER,
                "(onGrid |> Maybe.andThen fleetCommanderOverviewEntry)"
                " /= Nothing",
                "(warping |> Maybe.andThen fleetCommanderOverviewEntry)"
                " /= Nothing",
                "(warping |> Maybe.map shipWarpingFromReading)"
                " == Just (Just True)",
                "(onGrid |> Maybe.map shipWarpingFromReading) /= Just (Just True)",
                "(onGrid |> Maybe.map shipIsApproachingFromReading)"
                " == Just False",
            ], definitions=self.definitions),
            [True] * 10)

    def test_the_budget_is_still_spent_without_a_landing(self):
        """The control, and the behaviour this change does not touch: a bot
        that asks and asks with the commander on grid still gives up."""
        self.assertEqual(
            self.repl.evaluate([
                "(memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings)"
                " == approachFleetCommanderAskedReadingsBound"
                % self.never_left,
                "approachFleetCommanderHasBeenGivenUpOn"
                " (memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings)"
                % self.never_left,
            ], definitions=self.definitions),
            [True, True])

    def test_a_landing_lets_the_approach_ask_again(self):
        """The defect, fixed. The same session with one warp in it ends with a
        budget the arm can spend, on a reading whose commander is on the same
        overview he was on throughout."""
        self.assertEqual(
            self.repl.evaluate([
                "not (approachFleetCommanderHasBeenGivenUpOn"
                " (memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings))" % self.landed,
            ], definitions=self.definitions),
            [True])

    def test_the_landing_reading_is_still_charged_for_its_own_ask(self):
        """One, not zero. The landing refills the budget the reading carries
        in, so the ask that goes out on the landing reading is counted -- a
        counter refilled after the increment never charges the first reading of
        a landing, which is #102's defect in the direction that under-counts.
        """
        self.assertEqual(
            self.repl.evaluate([
                "(memoryOver defaultBotSettings %s"
                " |> .approachFleetCommanderAskedReadings) == 1" % self.landed,
            ], definitions=self.definitions),
            [True])

    def test_the_window_and_the_budget_are_re_armed_together(self):
        """The asymmetry #428 is about, said as one assertion: on the reading
        the landing re-arms `closingOnTheCommanderSinceLanding`, the counter
        the ask is bounded by is spendable again."""
        self.assertEqual(
            self.repl.evaluate([
                "(memoryOver defaultBotSettings %s"
                " |> .closingOnTheCommanderSinceLanding)" % self.landed,
                "(memoryOver defaultBotSettings %s"
                " |> .closingOnTheCommanderSinceLanding)" % self.never_left,
            ], definitions=self.definitions),
            [True, False])


class TheFleetMateBudgetIsRefilledTest(unittest.TestCase):
    """The sibling arm, folded the same way and with the same control.

    The mate is on the overview on every reading of both sessions, so
    `fleetMateOnThisGrid == Nothing` -- the reset that already existed -- never
    fires and cannot be what clears the count.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("mateOnGrid", mate_grid(None)),
            reading_binding("mateWarping", mate_grid("Warp Drive Active")),
        ]
        cls.landed = ("[ ( %d, mateOnGrid ), ( 1, mateWarping )"
                      ", ( 1, mateOnGrid ) ]" % MATE_SESSION_READINGS)
        cls.never_left = ("[ ( %d, mateOnGrid ) ]"
                          % (MATE_SESSION_READINGS + 2))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == %d"
                % (self.landed, MATE_SESSION_READINGS + 2),
                "(mateOnGrid |> Maybe.andThen .shipUI) /= Nothing",
                "(mateOnGrid |> Maybe.andThen fleetBroadcastBannerText)"
                ' == Just "%s is at location Amarr"' % MATE,
                "(mateOnGrid |> Maybe.andThen (fleetMateToWarpToOnThisGrid"
                ' { followFleetBroadcastFrom = [ "%s" ]'
                ", recoveringFromRetreat = False }))"
                ' == Just "%s"' % (MATE, MATE),
                "(mateWarping |> Maybe.andThen (fleetMateToWarpToOnThisGrid"
                ' { followFleetBroadcastFrom = [ "%s" ]'
                ", recoveringFromRetreat = False }))"
                ' == Just "%s"' % (MATE, MATE),
                "(mateWarping |> Maybe.map shipWarpingFromReading)"
                " == Just (Just True)",
                "(mateOnGrid |> Maybe.andThen fleetCommanderOverviewEntry)"
                " == Nothing",
            ], definitions=self.definitions),
            [True] * 7)

    def test_the_budget_is_still_spent_without_a_landing(self):
        """The control: a mate who stays on grid while nothing warps still
        exhausts the ask, which is the bound #373 put there."""
        self.assertEqual(
            self.repl.evaluate([
                "fleetMateWarpHasBeenGivenUpOn"
                " (memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings)" % self.never_left,
            ], definitions=self.definitions),
            [True])

    def test_a_landing_lets_the_fleet_mate_warp_ask_again(self):
        """The defect, fixed, on a grid the mate never left."""
        self.assertEqual(
            self.repl.evaluate([
                "not (fleetMateWarpHasBeenGivenUpOn"
                " (memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings))" % self.landed,
                "(memoryOver followingTheMate %s"
                " |> .goToFleetMateWarpAskedReadings) == 1" % self.landed,
            ], definitions=self.definitions),
            [True, True])


class TheCountersReadTheSharedRuleTest(unittest.TestCase):
    """Source-pinned, because *where* the refill is applied is the change.

    A suite that only exercised `askedReadingsRefilledByLanding` would pass on
    a bot no counter read it from, and one that only folded sessions could not
    say the counter and the arm agree about what the landing bought.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_refill_is_keyed_on_the_corrected_warp_end_trigger(self):
        """#194 / #205: `weJustFinishedWarping` is `warpJustEnded`, and the
        condition it replaced -- `shipIsWarping == Just False` -- could not
        answer `True` at the end of a warp at all. A refill keyed on that would
        be a fix that never fires while every rule case here went on passing.
        """
        for binding in ("approachAskedReadingsCarriedIn",
                        "fleetMateWarpAskedReadingsCarriedIn"):
            with self.subTest(binding=binding):
                body = collapsed(indented_let_binding(self.source, binding))
                self.assertIn("askedReadingsRefilledByLanding", body)
                self.assertIn("justLanded = weJustFinishedWarping", body)
        trigger = collapsed(
            indented_let_binding(self.source, "weJustFinishedWarping"))
        self.assertIn("warpJustEnded", trigger)
        self.assertNotIn("Just False", trigger)

    def test_the_approach_counter_reads_the_refilled_budget(self):
        """Every branch that carries a count forward, so a version that
        refilled the increment and not the hold -- which is the shipped defect
        wearing the fix's clothes -- fails here."""
        field = record_field(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =",
            "approachFleetCommanderAskedReadings")
        self.assertIn("approachAskedReadingsCarriedIn + 1", collapsed(field))
        self.assertNotIn(
            "botMemoryBefore.approachFleetCommanderAskedReadings", field)

    def test_the_fleet_mate_counter_reads_the_refilled_budget(self):
        field = record_field(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =",
            "goToFleetMateWarpAskedReadings")
        self.assertIn("fleetMateWarpAskedReadingsCarriedIn + 1",
                      collapsed(field))
        self.assertNotIn(
            "botMemoryBefore.goToFleetMateWarpAskedReadings", field)

    def test_the_fleet_mate_give_up_is_asked_of_the_refilled_budget(self):
        """A give-up asked of the un-refilled count holds for one reading past
        the landing, which is the status line saying `GAVE UP` on a reading the
        bot has just been given its budget back."""
        field = collapsed(record_field(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =",
            "goToFleetMateWarpAskedReadings"))
        self.assertIn(
            "fleetMateWarpHasBeenGivenUpOn fleetMateWarpAskedReadingsCarriedIn",
            field)

    def test_the_step_is_predicted_against_the_refilled_budget(self):
        """#102, and the half only a source read can see. The decision reads
        the count this update writes, so a memory update that predicts the step
        against `botMemoryBefore`'s spent count would charge nothing on the
        landing reading while the arm asked on it."""
        binding = collapsed(
            indented_let_binding(self.source, "askingTheCommanderForAnApproach"))
        self.assertIn("askedReadings = approachAskedReadingsCarriedIn", binding)
        self.assertNotIn(
            "botMemoryBefore.approachFleetCommanderAskedReadings", binding)

    def test_the_refill_is_one_rule_with_two_readers(self):
        """Both counters reach the reset through the same declaration, so the
        approach and the fleet-mate warp cannot come to disagree about what a
        landing is -- which is what a second copy of the condition would be."""
        readers = re.findall(r"askedReadingsRefilledByLanding", self.source)
        # The declaration, its type annotation, and one call from each of the
        # two carried-in bindings.
        self.assertEqual(len(readers), 4)
        for binding in ("approachAskedReadingsCarriedIn",
                        "fleetMateWarpAskedReadingsCarriedIn"):
            with self.subTest(binding=binding):
                self.assertIn(
                    "askedReadingsRefilledByLanding",
                    indented_let_binding(self.source, binding))


class TheStrayWindowDefectIsOutOfScopeTest(unittest.TestCase):
    """#428 names this and says to leave it alone, so it is pinned unchanged.

    `CloseAWindowLeftOverTheClient` spends a reading of the approach budget,
    and three of the four pilots also reported `A 'InfoWindow' is still open
    over the client` -- so the 40 readings may have gone entirely on closing a
    window rather than on any approach attempt. That is #426's shape, it wants
    its own fix and its own evidence, and it must stay separately reviewable.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_stray_window_defect_is_left_alone(self):
        self.assertEqual(
            self.repl.evaluate([
                "List.member CloseAWindowLeftOverTheClient"
                " approachFleetCommanderAnswersThatSpendAReading",
            ]),
            [True])

    def test_the_step_ladder_is_unchanged(self):
        """The clause that returns it, and the ordering around it: the give-up
        before the close, the close before "already approaching"."""
        body = collapsed(declaration(
            self.source, "approachFleetCommanderStep approachCase ="))
        self.assertIn(
            "else if approachCase.strayWindowIsOpen"
            " && 0 < approachCase.askedReadings then"
            " CloseAWindowLeftOverTheClient", body)
        self.assertLess(
            body.index("GaveUpOnTheApproach"),
            body.index("CloseAWindowLeftOverTheClient"))
        self.assertLess(
            body.index("CloseAWindowLeftOverTheClient"),
            body.index("AlreadyApproaching"))


if __name__ == "__main__":
    unittest.main()
