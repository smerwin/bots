"""A fight that is not killing anything is bounded, and the bot acts on it.

Issue: saxrat's run 48 sat in anomaly `OTC-000` printing `All locked up; bounce?`
on 1,563 consecutive readings and answering "wait" to every one of them -- the
anomaly's own age clause reached **4,759 seconds**, and the run was still being
written when the incident was reported at 3,883. Three rats the whole time, none
of them dying, a `Centii Loyal Enslaver` out-regenerating the guns from a hull the
bot had already taken down to 12%, no drones left to launch, and the ship in no
danger at all. The branch asked whether to bounce and then never did.

**The obvious progress signal does not survive the log, and that is the first
finding here.** Run 48's target had a *rising* shield, so "the hitpoints stopped
moving in the damaging direction" reads like the discriminator. Measured over the
longest recorded stall -- 821 consecutive readings at this branch with a readable
ring -- the triple **rises on 154 readings, holds on 642, and falls on 24**: the
guns were landing and the repairs were faster. What that costs a rule keyed on it
is not the share but the run length: **the longest stretch inside that stall with
no fall in it is 113 readings**, against a bound of 200 -- so a counter reset by
the triple never fires and the incident repeats. That margin is 1.8x where the
rat count's is sevenfold, which is the whole reason the ring is measured here and
read nowhere in `Bot.elm`. `TheHitpointRingMovesThroughoutTheStall`
is that recomputed from the corpus, and `TheHitpointTripleIsNotTheSignal` runs the
same shape through the shipped rule.

What stayed true for all 1,563 readings is that the overview still showed three
rats. So the rule is a count of rows and a count of readings:

    no progress on a reading = the fight is still underway (a locked target, and
    a rat still on the overview) and the overview's rat count did not fall.

**The bounds are derived, not picked.** Replayed over the twenty-two recorded
saxrat logs whose status line carries a reading index -- runs 31 to 50, counting
*readings* rather than decision lines, since the status text is reprinted under
every decision -- the two populations separate by a factor of seven:

| | readings |
|---|---|
| longest a fight went between kills **and still produced one** | **130** (run 36's `QRH-534`) |
| the next four | 55, 43, 34, 27 |
| the other 440 of 445 | 19 or below |
| ordinary stretches that produced no kill (a fight the bot broke off) | 73 at the top |
| **the three recorded stalls** | **932, 1443, 1582** |

The gap between 130 and 932 is empty. `combatStalemateApproachReadings` is 200
and `combatStalemateLeaveReadings` is 300, both inside it. Every count above is
asserted here as a **relation** recomputed from `~/eve-bot-logs`, so a growing
corpus cannot turn a true claim red.

**What the bot does when the bound fires, and on every reading after it.** Three
rungs, and none of them is a wait that can decline forever:

- below 200 -- `waitForProgressInGame`, exactly as today;
- 200 to 299 -- **close the range**, by double-clicking the active target's
  overview row, which is how this bot has approached since PR #249 and presses no
  key. Run 48's target sat at 20,000 m, exactly on the ammo swap's crossover and
  inside its dead band, so the swap could not decide which charge the fight
  wanted and the guns held a long-range one at knife range;
- 300 and up -- **leave the grid**, through the same `returnDronesToBay` /
  `continueIfCombatComplete` construction the anomaly's own wait deadline uses.

The count only rises while the fight stands still, so the branch does not fall
back to waiting on the reading after it acts -- `TheBoundIsCrossedOnceAndStaysCrossed`.
And a row the ship cannot reach is not a range it can close:
`approachRangeLimitMeters` (PR #251, run 41's 13,541 double clicks at 2,266 km)
is applied *inside* the row selection, and a reading with no reachable row
escalates straight to leaving rather than asking anyway.

**Nothing is keyed on a rat's name.** An anomaly is a pocket of identically named
rats, so a verdict latched by name would blacklist every `Centii Loyal Enslaver`
for the session -- which is why the mission runner's zero-damage rule was
deliberately not ported here. `NothingLatchesAgainstARatsName` asserts it three
ways: the same session with the rats renamed answers identically, a fresh fight
against the same name starts at zero, and the memory the rule keeps is two
integers.

The rules are executed through the real `Bot.elm` in `elm repl`, and the readings
they are asked about are built by running UI trees through the **real**
`EveOnline.ParseUserInterface` -- a Python restatement of "what does the parser
make of these rows" would test the restatement. The decision site itself takes a
whole `BotDecisionContext` and so is read out of the source, through a
whitespace-collapsing reader and, where the binding builds a record literal, a
reader sliced by indentation.

**Two things here are weaker than the rest and say so.** `stalemateStep` is
written in `StalemateRepl` rather than reached through
`updateMemoryForNewReadingFromGame`, which takes a whole `UpdateMemoryContext` --
so no executable case here can see what the memory update *feeds* the rule, and a
mutation handing it the target's shield percentage instead of the rat count
survived every one of them until `test_the_memory_update_feeds_the_rule_a_count_of_rows`
was tightened to pin that expression by its form. `test_saxrat_ammo_swap`'s trust
rule records the same hole in the same place. And
`test_no_rung_of_the_ladder_can_decline_forever` reads the branch's own text, so
the bounded wait inside `unlessAlreadyClosingIn` is not what it refuses -- what
bounds that one is the count, which rises whatever the guard answers.

Nothing here reads a live game client or a running bot. The corpus cases read the
recorded runs in `~/eve-bot-logs`, and only read them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, collapsed, label, node, source_of)

# The two bounds, written here so a case can assert the constant rather than
# read whatever the source happens to say and compare it with itself.
APPROACH_READINGS = 200
LEAVE_READINGS = 300

# PR #251's bound, past which the client discards a double click.
APPROACH_RANGE_LIMIT_METERS = 150000

# A rat's icon colour, read off the live client (CLAUDE.md, "Strings and
# identities read off a live client"). What makes a fixture row a rat at all --
# `getNamesOfRatsInOverview` filters on this and on the distance.
RAT_COLOR = {"aPercent": 100, "rPercent": 100, "gPercent": 10, "bPercent": 10}

# Run 48's own rat, and its own distance: 20,000 m, which is exactly the
# crossover `crossover 20000 m (+/-3000 ...), target distance 20000 m` names.
RUN48_RAT = "Centii Loyal Enslaver"
RUN48_DISTANCE = "20,000 m"

# A second name, used only to show that renaming every rat changes nothing.
OTHER_RAT = "Centii Ravener"

# Beyond `approachRangeLimitMeters`, so the row is one the bot must decline to
# close on. Still inside the 300 km `getNamesOfRatsInOverview` counts within, so
# it is a rat the stalemate is accumulating against rather than a row already
# dropped.
OUT_OF_APPROACH_RANGE = "200,000 m"

ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20

# Run 48's target as the ring read it, and the two neighbours the log carries
# either side of it: the shield climbing (which is what the stall looks like) and
# the shield and armour falling (which is what the guns landing looks like, on
# readings inside the same stall). Fractions, because the client stores the
# fraction itself on the named container -- see `parseTargetHitpointsPercent`.
RUN48_HITPOINTS = (0.84, 1.0, 0.20)
RUN48_REGENERATED = (0.85, 1.0, 0.20)
RUN48_DAMAGED = (0.74, 0.92, 0.20)


def health_bar(layer, fraction):
    return node("Container", {"_name": layer, "_elementId": layer,
                              "lastState": fraction},
                region=(0, 0, 141, 141))


def target_in_bar(name, hitpoints):
    """A `TargetInBar` the real parser reads, so `.targets` is not empty."""
    icon_par = node("Container", {"_name": "iconPar"}, [
        node("TargetHealthBars", {}, [
            health_bar("shieldBar", hitpoints[0]),
            health_bar("armorBar", hitpoints[1]),
            health_bar("hullBar", hitpoints[2]),
        ], region=(12, 0, 141, 141)),
    ], region=(12, 0, 141, 141))
    return node("TargetInBar", {"_name": "target", "label": name}, [
        node("Container",
             {"_name": "barAndImageCont", "_elementId": "barAndImageCont"},
             [icon_par], region=(0, 0, 165, 150)),
        node("EveLabelSmall", {"_name": "label", "_setText": name},
             region=(0, 155, 165, 16)),
        node("ActiveTargetIndicator", {}, region=(0, 0, 165, 150)),
    ], region=(1000, 69, 165, 270))


def overview(rows):
    """An overview window with Distance/Name/Type columns the parser can read.

    Each row is `(distance, name, is_rat, is_active_target)`. A header must span
    its cell (`parseListViewEntry`'s `headerRegionMatchesCellRegion`), which is
    why the column geometry is explicit rather than incidental, and the active
    target's marker is a **named child of the row's `SpaceObjectIcon`**, which is
    where `namesUnderSpaceObjectIcon` reads it from.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name, is_rat, is_active) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        icon_children = []
        if is_rat:
            icon_children.append(
                node("Sprite", {"_name": "iconSprite", "_color": RAT_COLOR},
                     region=(2, y, 8, ROW_HEIGHT)))
        if is_active:
            icon_children.append(
                node("Sprite", {"_name": "myActiveTargetIndicator"},
                     region=(2, y, 8, ROW_HEIGHT)))
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, ROW_HEIGHT)),
            label(name, (110, y, 150, ROW_HEIGHT)),
            label(name, (310, y, 150, ROW_HEIGHT)),
            node("SpaceObjectIcon", {}, icon_children,
                 region=(2, y, 12, ROW_HEIGHT)),
        ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def rat_rows(count, name=RUN48_RAT, distance=RUN48_DISTANCE):
    """`count` rat rows, the first of them the active target."""
    return [(distance, name, True, index == 0) for index in range(count)]


class StalemateRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus what folding a session costs.

    The bindings ride in the preamble, which `imports_and_bindings` folds into
    the one `let` that asks the question -- so they cost the same single compile
    the imports do (#172).
    """

    BINDINGS = (
        # One reading's worth of the memory update, exactly as
        # `updateMemoryForNewReadingFromGame` assembles it.
        "stalemateStep = \\before reading ->"
        " combatStalemateAfterReading"
        " { before = before"
        " , fightIsUnderway = combatFightIsUnderway reading"
        " , ratsInOverview = getNamesOfRatsInOverview reading |> List.length }",
        # A session, written as `(repeats, reading)` pairs. The `filterMap` is
        # what a fixture that never parsed falls out of, which is why every case
        # using this asks `sessionLength` beside it -- see #174 for why a fixture
        # that never arrived and a rule that answered nothing look identical.
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "stalemateOver = \\pairs ->"
        " List.foldl (\\r before -> stalemateStep before r)"
        " { readings = 0, ratsInOverview = 0 } (sessionOf pairs)",
        "readingsAfter = \\pairs -> (stalemateOver pairs).readings",
        "verdictAfter = \\pairs ->"
        " combatStalemateVerdict (stalemateOver pairs).readings",
        # The high-water mark over a session rather than its final value: a case
        # about a fight that must never be interrupted has to say the counter
        # never reached the bound, not merely that it did not end there.
        "peakOver = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r ( before, peak ) ->"
        " let now = stalemateStep before r"
        " in ( now, max peak now.readings ))"
        " ( { readings = 0, ratsInOverview = 0 }, 0 )"
        " |> Tuple.second",
        "ratsIn = \\r -> getNamesOfRatsInOverview r |> List.length",
        "targetsIn = \\r -> r.targets |> List.length",
        "activeRowDistance = \\r -> r.overviewWindows"
        " |> List.concatMap .entries"
        " |> List.filter overviewEntryIsActiveTarget"
        " |> List.head"
        " |> Maybe.map (.objectDistanceInMeters >> Result.withDefault -1)"
        " |> Maybe.withDefault -2",
        "activeRowIsReachable = \\r -> r.overviewWindows"
        " |> List.concatMap .entries"
        " |> List.filter overviewEntryIsActiveTarget"
        " |> List.filter overviewEntryIsDisplayed"
        " |> List.filter (\\e -> e.objectDistanceInMeters"
        " |> Result.map (\\m -> m <= approachRangeLimitMeters)"
        " |> Result.withDefault False)"
        " |> List.isEmpty |> not",
        "hitpointsIn = \\r -> activeTargetHitpointsPercent r"
        " |> Maybe.map (\\h ->"
        " String.join \"/\""
        " [ String.fromInt h.shield"
        " , String.fromInt h.armor"
        " , String.fromInt h.structure ])"
        " |> Maybe.withDefault \"unreadable\"",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-combat-stalemate-")
        super().__init__(**kwargs)
        self.preamble = list(self.preamble) + list(self.BINDINGS)


def reading(name, rows, target=RUN48_HITPOINTS, target_name=RUN48_RAT):
    """A binding of `name` to a really parsed reading.

    `target` of `None` builds a reading with an empty target bar, which is a
    grid the guns are not pointed at anything on.
    """
    children = [overview(rows)]
    if target is not None:
        children.append(node("TargetsContainer", {"_name": "targets"}, [
            target_in_bar(target_name, target)], region=(1000, 60, 400, 300)))
    return StalemateRepl.reading_binding(name, children)


DEFINITIONS = [
    # Run 48's own shape: three rats, one of them the active target at the ammo
    # swap's crossover, a readable ring, and no drones window at all.
    reading("stall", rat_rows(3)),
    # The same grid one reading later, with the shield a point higher. This is
    # what the log shows the target doing: 74% climbing to 85% while the bot
    # waits.
    reading("stallRegenerating", rat_rows(3), RUN48_REGENERATED),
    # And the same grid on a reading the guns *did* land on -- shield and armour
    # both lower than the reading before. Hundreds of run 48's stalled readings
    # look like this, which is why the hitpoint triple cannot be the signal.
    reading("stallDamaged", rat_rows(3), RUN48_DAMAGED),
    # A rat died: the count falls, which is the whole progress signal.
    reading("twoRats", rat_rows(2)),
    reading("oneRat", rat_rows(1)),
    # The same stall with every rat renamed. Nothing about the rule may notice.
    reading("stallRenamed", rat_rows(3, name=OTHER_RAT),
            target_name=OTHER_RAT),
    # The active target too far to approach, so there is no range to close.
    reading("stallOutOfReach",
            [(OUT_OF_APPROACH_RANGE, RUN48_RAT, True, True)]
            + rat_rows(2)[1:] + [(RUN48_DISTANCE, RUN48_RAT, True, False)]),
    # The two ways a fight is not underway: no locked target, and no rat left.
    reading("noTarget", rat_rows(3), target=None),
    reading("noRats", [("20,000 m", "Sansha Command Relay Outpost", False,
                        True)]),
]

# The sessions the cases fold. Written as `(repeats, reading)` so a case reads
# as the run it is replaying rather than as a list comprehension.
RUN48_STALL = "[ ( %d, stall ) ]" % LEAVE_READINGS
RUN48_STALL_TO_APPROACH = "[ ( %d, stall ) ]" % APPROACH_READINGS
RUN48_STALL_ONE_SHORT = "[ ( %d, stall ) ]" % (APPROACH_READINGS - 1)

# Run 36's `QRH-534` is the longest fight in the whole corpus that went without a
# kill and still produced one: 130 readings. Replayed three times over, once per
# rat, which is a harder session than anything recorded.
WINNABLE_FIGHT = ("[ ( 130, stall ), ( 130, twoRats ), ( 130, oneRat )"
                  ", ( 1, noRats ) ]")


class TheFixturesAreWhatTheCasesAssume(unittest.TestCase):
    """The trees first, before anything is concluded from them.

    A case built on a tree the parser makes nothing of would pass or fail for
    reasons that have nothing to do with the rule under test -- and, since #174,
    a fixture that never arrived and a rule that answered nothing are the same
    answer from outside.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_stall_reading_is_run_48s_grid(self):
        answers = self.repl.evaluate(
            ["(stall |> Maybe.map ratsIn) == Just 3",
             "(stall |> Maybe.map targetsIn) == Just 1",
             "(stall |> Maybe.map activeRowDistance) == Just 20000",
             "(stall |> Maybe.map activeRowIsReachable) == Just True"],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 4,
            "the parser does not make of this tree the three-rat grid at the "
            "ammo swap's crossover that every case below assumes")

    def test_the_ring_reads_and_the_three_layers_stay_apart(self):
        """The hitpoint triple is readable here, which is what makes the case
        that it is *not* the signal a measurement rather than an absence."""
        answers = self.repl.strings(
            ["(stall |> Maybe.map hitpointsIn |> Maybe.withDefault \"no\")",
             "(stallRegenerating |> Maybe.map hitpointsIn"
             " |> Maybe.withDefault \"no\")",
             "(stallDamaged |> Maybe.map hitpointsIn"
             " |> Maybe.withDefault \"no\")"],
            definitions=DEFINITIONS)
        self.assertEqual(answers, ["84/100/20", "85/100/20", "74/92/20"])

    def test_the_other_fixtures_are_the_grids_they_are_named_for(self):
        answers = self.repl.evaluate(
            ["(twoRats |> Maybe.map ratsIn) == Just 2",
             "(oneRat |> Maybe.map ratsIn) == Just 1",
             "(noRats |> Maybe.map ratsIn) == Just 0",
             "(noRats |> Maybe.map targetsIn) == Just 1",
             "(noTarget |> Maybe.map ratsIn) == Just 3",
             "(noTarget |> Maybe.map targetsIn) == Just 0",
             "(stallRenamed |> Maybe.map ratsIn) == Just 3",
             "(stallOutOfReach |> Maybe.map ratsIn) == Just 3",
             "(stallOutOfReach |> Maybe.map activeRowDistance) == Just 200000",
             "(stallOutOfReach |> Maybe.map activeRowIsReachable) == Just False"],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 10)

    def test_every_session_folded_below_is_the_length_it_claims(self):
        """`sessionOf` drops a reading that did not parse, so a session whose
        length is not asserted is one a case could pass having folded nothing."""
        answers = self.repl.evaluate(
            ["sessionLength %s == %d" % (RUN48_STALL, LEAVE_READINGS),
             "sessionLength %s == %d" % (RUN48_STALL_TO_APPROACH,
                                         APPROACH_READINGS),
             "sessionLength %s == %d" % (RUN48_STALL_ONE_SHORT,
                                         APPROACH_READINGS - 1),
             "sessionLength %s == 391" % WINNABLE_FIGHT],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 4)


class TheBoundsAreTheOnesTheCorpusSupports(unittest.TestCase):
    """The two constants, and where they sit relative to what was measured."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_two_bounds_are_200_and_300(self):
        self.assertEqual(
            self.repl.evaluate(
                ["combatStalemateApproachReadings == %d" % APPROACH_READINGS,
                 "combatStalemateLeaveReadings == %d" % LEAVE_READINGS]),
            [True, True])

    def test_the_approach_bound_clears_the_longest_fight_ever_won(self):
        """130 readings is run 36's `QRH-534`, the worst case in eighteen
        sessions. A bound at or below it interrupts a fight the guns won."""
        self.assertEqual(
            self.repl.evaluate(
                ["130 < combatStalemateApproachReadings",
                 # And with margin rather than by one reading: a bound of 131
                 # would satisfy the line above and be a coincidence.
                 "combatStalemateApproachReadings > 130 * 3 // 2"]),
            [True, True])

    def test_the_leave_bound_is_far_below_the_shortest_recorded_stall(self):
        """932 is the shortest of the three. The whole ladder has to finish well
        inside it, or the escalation is slower than the thing it escalates."""
        self.assertEqual(
            self.repl.evaluate(
                ["combatStalemateLeaveReadings < 932",
                 "combatStalemateLeaveReadings * 3 <= 932"]),
            [True, True])

    def test_the_ladder_is_ordered_and_the_approach_gets_a_window(self):
        """A leave bound at or below the approach bound is a ladder with one
        rung, and the approach would never be taken at all."""
        self.assertEqual(
            self.repl.evaluate(
                ["combatStalemateApproachReadings"
                 " < combatStalemateLeaveReadings",
                 # 20 readings is what the corpus says closing 20,000 m costs at
                 # the 1,000 m a reading the runs record while approaching, so
                 # the window has to be several times that to mean anything.
                 "combatStalemateLeaveReadings"
                 " - combatStalemateApproachReadings >= 20 * 4"]),
            [True, True])

    def test_the_verdict_changes_at_both_bounds_and_nowhere_else(self):
        answers = self.repl.evaluate(
            ["combatStalemateVerdict 0 == FightIsStillGettingSomewhere",
             "combatStalemateVerdict 130 == FightIsStillGettingSomewhere",
             "combatStalemateVerdict %d == FightIsStillGettingSomewhere"
             % (APPROACH_READINGS - 1),
             "combatStalemateVerdict %d == CloseTheRangeOnTheTarget"
             % APPROACH_READINGS,
             "combatStalemateVerdict %d == CloseTheRangeOnTheTarget"
             % (LEAVE_READINGS - 1),
             "combatStalemateVerdict %d == LeaveThisGrid" % LEAVE_READINGS,
             "combatStalemateVerdict 1582 == LeaveThisGrid"])
        self.assertEqual(answers, [True] * 7)


class Run48sOwnShapeReachesBothRungs(unittest.TestCase):
    """The incident, replayed through the rule as the readings it really was.

    Three rats, a target regenerating faster than the guns hurt it, no drones and
    nothing to lock. The bot has to stop waiting.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_stall_reaches_the_approach_bound(self):
        answers = self.repl.evaluate(
            ["readingsAfter %s == %d"
             % (RUN48_STALL_TO_APPROACH, APPROACH_READINGS),
             "verdictAfter %s == CloseTheRangeOnTheTarget"
             % RUN48_STALL_TO_APPROACH],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True, True],
            "run 48's own grid does not reach the bound that makes the bot "
            "close the range, so the incident would repeat")

    def test_one_reading_short_of_the_bound_it_still_waits(self):
        """The boundary from the other side, so a rule that acted on every
        reading would fail here rather than passing the case above."""
        self.assertEqual(
            self.repl.evaluate(
                ["verdictAfter %s == FightIsStillGettingSomewhere"
                 % RUN48_STALL_ONE_SHORT],
                definitions=DEFINITIONS),
            [True])

    def test_the_stall_goes_on_to_the_leave_bound(self):
        """Closing the range is a rung rather than an answer: a stall that
        outlasts it has to leave, or the approach is the new forever-wait."""
        answers = self.repl.evaluate(
            ["readingsAfter %s == %d" % (RUN48_STALL, LEAVE_READINGS),
             "verdictAfter %s == LeaveThisGrid" % RUN48_STALL],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True, True])

    def test_the_target_regenerating_does_not_reset_the_count(self):
        """The shape the log actually carries: the ring moving up and down while
        nothing dies. Neither direction is progress."""
        session = ("[ ( 100, stall ), ( 100, stallRegenerating )"
                   ", ( 100, stallDamaged ) ]")
        answers = self.repl.evaluate(
            ["sessionLength %s == %d" % (session, LEAVE_READINGS),
             "readingsAfter %s == %d" % (session, LEAVE_READINGS),
             "verdictAfter %s == LeaveThisGrid" % session],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 3)

    def test_the_bound_is_crossed_once_and_stays_crossed(self):
        """What the bot does on the reading the bound fires and on every reading
        after it. The count only rises while the fight stands still, so the
        branch cannot fall back to waiting -- which is the bug in a new hat."""
        longer = "[ ( %d, stall ) ]" % (LEAVE_READINGS * 5)
        answers = self.repl.evaluate(
            ["verdictAfter %s == LeaveThisGrid" % longer,
             "readingsAfter %s == %d" % (longer, LEAVE_READINGS * 5),
             # And from the other end: once past the approach bound, no number
             # of further stalled readings answers "keep waiting".
             "List.all (\\n -> combatStalemateVerdict n"
             " /= FightIsStillGettingSomewhere)"
             " (List.range combatStalemateApproachReadings 5000)"],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 3)


class AWinnableFightIsNeverInterrupted(unittest.TestCase):
    """The other direction, and the one a bound placed too low costs.

    Damage landing, rats dying, the bound never reached -- replayed at the
    corpus's own worst case rather than at a comfortable one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_three_kills_at_the_corpus_worst_case_never_reach_the_bound(self):
        """130 readings a kill is run 36's `QRH-534`, the longest gap between
        kills anywhere in the corpus that still produced one. Three of them back
        to back is harder than anything recorded."""
        answers = self.repl.evaluate(
            ["sessionLength %s == 391" % WINNABLE_FIGHT,
             "peakOver %s == 130" % WINNABLE_FIGHT,
             "peakOver %s < combatStalemateApproachReadings" % WINNABLE_FIGHT,
             "verdictAfter %s == FightIsStillGettingSomewhere"
             % WINNABLE_FIGHT],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 4,
            "a fight the guns are winning reaches a rung it must not reach")

    def test_a_kill_clears_the_count_on_the_reading_it_lands(self):
        """The reset is the kill and not the reading after it, so a fight that
        kills something every 200 readings never accumulates."""
        session = "[ ( 199, stall ), ( 1, twoRats ), ( 199, twoRats ) ]"
        answers = self.repl.evaluate(
            ["sessionLength %s == 399" % session,
             "peakOver %s == 199" % session,
             "peakOver %s < combatStalemateApproachReadings" % session],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 3)

    def test_a_grid_that_is_not_a_fight_accumulates_nothing(self):
        """Travelling, warping, docked, a cleared grid: the count is cleared
        rather than carried into the next anomaly, which is what would let a
        bound fire on arrival somewhere it had never been."""
        answers = self.repl.evaluate(
            ["peakOver [ ( %d, noTarget ) ] == 0" % LEAVE_READINGS,
             "peakOver [ ( %d, noRats ) ] == 0" % LEAVE_READINGS,
             # And a stall interrupted by leaving the grid starts again at zero
             # rather than resuming where it left off.
             "readingsAfter [ ( 199, stall ), ( 1, noTarget )"
             ", ( 10, stall ) ] == 10"],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 3)


class TheHitpointTripleIsNotTheSignal(unittest.TestCase):
    """Why the obvious rule was not built, executed rather than argued.

    "The hitpoints stopped moving in the damaging direction" is the reading run
    48 invites, and the log refutes it: inside that stall the triple falls on 24
    readings out of 820 and the longest stretch without a fall is 113, so a
    counter reset by it never reaches the bound. Here that is run through the
    shipped rule rather than counted -- and through the source, since nothing
    executable can see what the memory update feeds the rule.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_ring_falling_every_other_reading_still_reaches_both_rungs(self):
        """The discriminating shape, and it has to be built rather than repeated:
        a session of one reading over and over has no *transitions* in it, so a
        rule watching the triple would pass it by accident.

        Here the ring really moves -- 84/100/20 down to 74/92/20 and back, a fall
        on every other reading -- and nothing dies. A rule reset by a fall never
        gets past 1; this one reaches both rungs.
        """
        session = ("(List.repeat %d [ ( 1, stall ), ( 1, stallDamaged ) ]"
                   " |> List.concat)" % (LEAVE_READINGS // 2))
        answers = self.repl.evaluate(
            ["sessionLength %s == %d" % (session, LEAVE_READINGS),
             "readingsAfter %s == %d" % (session, LEAVE_READINGS),
             "verdictAfter %s == LeaveThisGrid" % session],
            definitions=DEFINITIONS)
        self.assertEqual(
            answers, [True] * 3,
            "a fight whose target's ring falls on every other reading and that "
            "kills nothing does not reach the bound, so the rule is watching "
            "the ring after all")

    def test_no_declaration_in_the_rule_reads_the_hitpoint_ring(self):
        """The stronger form: the rule cannot be watching the triple, because
        none of its declarations reaches for one."""
        source = source_of(SAXRAT_BOT_ELM)
        for name in ("combatStalemateAfterReading", "combatFightIsUnderway",
                     "combatStalemateVerdict"):
            with self.subTest(declaration=name):
                body = collapsed(declaration(source, name))
                for forbidden in ("activeTargetHitpointsPercent", "hitpoints",
                                  "shield", "armor", "structure"):
                    self.assertNotIn(
                        forbidden, body,
                        "%s reads %s -- the corpus says the triple moves in the "
                        "damaging direction throughout the stall, so a rule "
                        "consulting it resets on the readings it must not"
                        % (name, forbidden))


class NothingLatchesAgainstARatsName(unittest.TestCase):
    """The constraint the whole design was chosen for.

    An anomaly is a pocket of identically named rats, so a verdict latched by
    name blacklists every one of them for the session -- which is why the
    mission runner's zero-damage rule was not ported here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StalemateRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_renaming_every_rat_changes_nothing(self):
        answers = self.repl.evaluate(
            ["readingsAfter %s == readingsAfter [ ( %d, stallRenamed ) ]"
             % (RUN48_STALL, LEAVE_READINGS),
             "verdictAfter [ ( %d, stallRenamed ) ] == LeaveThisGrid"
             % LEAVE_READINGS,
             # And a session that switches from one name to the other mid-stall
             # is one stall rather than two.
             "readingsAfter [ ( 150, stall ), ( 150, stallRenamed ) ] == %d"
             % LEAVE_READINGS],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 3)

    def test_a_fresh_fight_against_the_same_name_starts_at_zero(self):
        """The failure a name latch produces: the bot leaves a
        `Centii Loyal Enslaver` and then refuses to fight the next one."""
        answers = self.repl.evaluate(
            ["readingsAfter [ ( %d, stall ), ( 1, noTarget ), ( 5, stall ) ]"
             " == 5" % LEAVE_READINGS,
             "verdictAfter [ ( %d, stall ), ( 1, noTarget ), ( 5, stall ) ]"
             " == FightIsStillGettingSomewhere" % LEAVE_READINGS],
            definitions=DEFINITIONS)
        self.assertEqual(answers, [True] * 2)

    def test_the_memory_the_rule_keeps_is_two_integers(self):
        """Nothing to latch a name in. A `Set`, a `Dict` or a `List String`
        appearing here is the shape this refuses."""
        source = source_of(SAXRAT_BOT_ELM)
        record = collapsed(declaration(source, "CombatStalemate"))
        self.assertRegex(
            record,
            r"type alias CombatStalemate = \{ readings : Int"
            r" , ratsInOverview : Int \}",
            "the stalemate memory is no longer two integers")
        for forbidden in ("Set", "Dict", "String", "objectName", "label"):
            self.assertNotIn(forbidden, record)

    def test_the_memory_update_feeds_the_rule_a_count_of_rows(self):
        """The wiring, pinned by its **form** rather than by a word list.

        This case is load-bearing beyond the name question, and a mutation is
        what showed it: the executable cases above fold `stalemateStep`, which
        is written in the harness because `updateMemoryForNewReadingFromGame`
        takes a whole `UpdateMemoryContext` and cannot be called from the repl.
        So **nothing executable can see what the memory update feeds the rule**,
        and a version handing it the target's shield percentage instead of the
        rat count passed every one of them. `test_saxrat_ammo_swap`'s trust rule
        is the same hole in the same place.

        So the three fields are asserted as the exact expressions they are, and
        the word list stays underneath as a second line rather than as the
        argument.
        """
        binding = collapsed(indented_let_field(
            declaration(source_of(SAXRAT_BOT_ELM),
                        "updateMemoryForNewReadingFromGame"),
            "combatStalemate"))
        self.assertRegex(
            binding,
            r", combatStalemate = combatStalemateAfterReading"
            r" \{ before = botMemoryBefore\.combatStalemate"
            r" , fightIsUnderway = combatFightIsUnderway context\.readingFromGameClient"
            r" , ratsInOverview = namesOfRatsInOverview \|> List\.length"
            r" \}",
            "the stalemate count is not being fed this reading's rat count -- a "
            "different expression here is invisible to every executable case in "
            "this file, which is why the form is pinned rather than a word list")
        for forbidden in ("objectName", "Set.", "Dict.", "String",
                          "activeTargetHitpointsPercent", "hitpoints",
                          "shield", "armor", "structure"):
            self.assertNotIn(
                forbidden, binding,
                "the stalemate count is being keyed on something other than a "
                "count of rows")


class WhatTheBotDoesWhenTheBoundFires(unittest.TestCase):
    """The decision site, read out of the source.

    `decideActionInAnomaly` takes a whole `BotDecisionContext`, so these are
    reads rather than evaluations -- the division of labour
    `test_saxrat_lock_batch_prefix` established. Mutating the site fails these
    and none of the executable cases above, which is how that split is checked
    rather than assumed.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.decision = declaration(self.source, "decideActionInAnomaly")
        self.branch = indented_let_field(self.decision,
                                         "breakTheCombatStalemate")

    def test_the_branch_that_asked_the_question_now_answers_it(self):
        """`All locked up; bounce?` no longer hands the reading to
        `waitForProgressInGame`."""
        flat = collapsed(self.decision)
        self.assertRegex(
            flat,
            r'describeMaxTargetsNothingToLock maxTargetsProbeNow'
            r' "All locked up; bounce\?" \) breakTheCombatStalemate',
            "the stalemate branch is not wired to the site run 48 stalled at")

    def test_the_branch_consults_the_count_and_nothing_else(self):
        self.assertIn(
            "combatStalemateVerdict context.memory.combatStalemate.readings",
            collapsed(self.branch),
            "the branch is not deciding on the stalemate count")

    def test_below_the_bound_it_waits_exactly_as_it_did(self):
        flat = collapsed(self.branch)
        self.assertRegex(
            flat, r"FightIsStillGettingSomewhere -> waitForProgressInGame",
            "the unchanged rung is no longer the unchanged rung")

    def test_at_the_approach_bound_it_double_clicks_and_presses_no_key(self):
        """PR #249's mechanism. The `Q` chord it replaced carried the session's
        modifiers and pressed Globe shortcuts at the machine."""
        flat = collapsed(self.branch)
        self.assertIn("doubleClickUiElement entry.uiNode", flat)
        for forbidden in ("vkey_", "KeyDown", "KeyUp"):
            self.assertNotIn(
                forbidden, flat,
                "the approach is wrapped in a keystroke again, which is what "
                "PR #249 removed")

    def test_the_approach_goes_through_the_already_closing_in_guard(self):
        """Re-issuing an approach restarts the manoeuvre, so the guard that
        stops that has to be in front of it -- and it is itself bounded by
        `approachIndicationTrustedForTicks`."""
        self.assertRegex(
            collapsed(self.branch),
            r"CloseTheRangeOnTheTarget -> case rowToCloseTheRangeOn of"
            r" Just entry -> unlessAlreadyClosingIn context")

    def test_the_row_it_closes_on_respects_the_approach_range_bound(self):
        """Run 41 double-clicked a row 2,266 km away 13,541 times with the ship
        never moving. The bound is applied inside the row selection, so a row
        past it is never asked for at all."""
        rows = indented_let_field(self.decision, "rowToCloseTheRangeOn")
        flat = collapsed(rows)
        self.assertIn("overviewEntryIsActiveTarget", flat)
        self.assertIn("overviewEntryIsDisplayed", flat)
        self.assertRegex(
            flat, r"distanceInMeters <= approachRangeLimitMeters")
        self.assertIn(
            "Result.withDefault False", flat,
            "a distance the row does not state is being read as reachable")

    def test_a_row_it_cannot_reach_escalates_rather_than_waiting(self):
        """The one place an approach-only fix would have reintroduced the bug:
        no reachable row, and nothing else to do."""
        flat = collapsed(self.branch)
        self.assertRegex(
            flat,
            r"Nothing -> describeBranch \(describeCombatStalemate"
            r"[^)]*\) leaveThisGrid",
            "a stalemate with no row to close on does not escalate")

    def test_at_the_leave_bound_it_leaves(self):
        self.assertRegex(
            collapsed(self.branch),
            r"LeaveThisGrid -> describeBranch \(describeCombatStalemate"
            r"[^)]*\) leaveThisGrid")

    def test_no_rung_of_the_ladder_can_decline_forever(self):
        """PR #257 blocked the bot for 108 minutes by putting a step that could
        decline forever on a hot path. Every rung above the first either acts or
        hands the reading to something that does."""
        flat = collapsed(self.branch)
        after_the_bound = flat[flat.index("CloseTheRangeOnTheTarget ->"):]
        self.assertNotIn(
            "waitForProgressInGame", after_the_bound,
            "a rung past the bound waits, which is the bug this change exists "
            "to end wearing a different hat")

    def test_leaving_is_the_construction_the_wait_deadline_already_uses(self):
        """`returnDronesToBay` first, so the ship does not warp off without its
        drones -- and then the caller's own answer to a finished grid."""
        leaving = indented_let_field(self.decision, "leaveThisGrid")
        flat = collapsed(leaving)
        self.assertRegex(
            flat,
            r"leaveThisGrid = returnDronesToBay context"
            r' \(describeBranch "No drones to return\." continueIfCombatComplete\)')

    def test_the_anomalys_own_wait_deadline_leaves_the_same_way(self):
        """One construction rather than two that could come to disagree about
        what leaving means."""
        after_looting = indented_let_field(
            self.decision, "decisionAfterLootingNotableWrecks")
        self.assertIn("leaveThisGrid", collapsed(after_looting))

    def test_every_caller_hands_this_branch_something_that_acts(self):
        """`continueIfCombatComplete` is the caller's argument, so a caller that
        passed a wait would make leaving the grid another forever-loop.

        All three call sites are read: the argument each hands over, and -- for
        the two that name a `let` binding -- that the binding cannot decline.
        `enterAnomaly`'s own `askForHelpToGetUnstuck` branch is unreachable from
        here, since this site is only reached where
        `getCurrentAnomalyIDAsSeenInProbeScanner` has already answered `Just`,
        which is what makes the probe scanner window present.
        """
        flat = collapsed(self.source)
        self.assertEqual(
            flat.count("decideActionInAnomaly {"), 3,
            "decideActionInAnomaly no longer has the three call sites this "
            "case reads")
        for continuation in (
                "siteProgressStepOrElse context (jumpToNextSystem context)",
                "pickAnotherAnomalyOrLeave",
                "returnDronesAndEnterAnomalyOrWait"):
            with self.subTest(continuation=continuation):
                self.assertGreaterEqual(
                    flat.count(continuation), 1,
                    "%s is no longer what a caller hands this branch"
                    % continuation)
        for name in ("pickAnotherAnomalyOrLeave",
                     "returnDronesAndEnterAnomalyOrWait"):
            with self.subTest(continuation=name):
                body = collapsed(indented_let_field(self.source, name))
                self.assertNotIn(
                    "waitForProgressInGame", body,
                    "%s can decline, so leaving the grid would not leave it"
                    % name)


class TheCountIsAdvancedWhereNothingCanStarveIt(unittest.TestCase):
    """#102's and #126's placement rule, applied to this counter.

    A count advanced inside the branch it bounds is a count the branch can stop
    by not being reached -- which is exactly the state this bound exists to end.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_the_count_is_written_only_in_the_memory_update(self):
        writers = {name for name, body in
                   top_level_declarations(self.source).items()
                   if "combatStalemateAfterReading" in body
                   and name != "combatStalemateAfterReading"}
        self.assertEqual(
            writers, {"updateMemoryForNewReadingFromGame"},
            "the stalemate count is advanced somewhere other than the one "
            "thing that runs on every reading unconditionally")

    def test_the_fight_gate_is_a_read_of_the_reading_and_nothing_else(self):
        """A gate that needed anything the decision tree produces would freeze
        with the tree."""
        body = collapsed(declaration(self.source, "combatFightIsUnderway"))
        self.assertRegex(
            body,
            r"combatFightIsUnderway readingFromGameClient = not "
            r"\(List\.isEmpty readingFromGameClient\.targets\) && not "
            r"\(List\.isEmpty \(getNamesOfRatsInOverview readingFromGameClient\)\)")
        self.assertNotIn("context", body)
        self.assertNotIn("memory", body)

    def test_the_status_line_carries_the_count(self):
        """Run 48's operator had no clause on any reading saying how long the
        fight had been going nowhere."""
        status = collapsed(declaration(self.source, "statusTextFromState"))
        self.assertIn(
            "describeCombatStalemate context.memory.combatStalemate", status)

    def test_the_clause_names_both_bounds(self):
        body = collapsed(declaration(self.source, "describeCombatStalemate"))
        self.assertIn("combatStalemateApproachReadings", body)
        self.assertIn("combatStalemateLeaveReadings", body)
        self.assertIn("stalemate ", body)


# ---------------------------------------------------------------------------
# The corpus. Every number in the doc comment above is recomputed here as a
# relation, from whatever `saxrat_run*.log` this machine holds, so a growing
# corpus cannot turn a true claim red.
# ---------------------------------------------------------------------------

# A reading's own index, printed on every in-space reading since the arrival
# window landed: `readingsSinceWarpEnded`, advanced once per reading in the
# memory update. This is what makes the counts below readings rather than
# decision lines -- the status text is reprinted under every decision, and that
# confusion has already cost `stall_watch.py` two threshold calibrations, #141 a
# retreat measurement and #164 an issue's whole diagnosis.
READING_INDEX = re.compile(
    r"Arrival window: (?:OPEN|closed), (\d+) of \d+ readings since the last "
    r"warp ended")
ANOMALY = re.compile(r"^Current anomaly: (\S+?)\.")
RATS = re.compile(r"^rats (\d+)\. (.*)$")
RATS_OLD = re.compile(r"^Rats in overview: (\d+)\. (.*)$")
TARGET_HITPOINTS = re.compile(r"^target .+? \[(\d+|\?)/(\d+|\?)/(\d+|\?)\]\.$")
DECISION = re.compile(r"^\++ (.*)$")

LOCKED_TARGET = "I see a locked target."
STALL_BRANCH = "All locked up; bounce?"

_corpus_cache = {}


def saxrat_runs():
    """Every recorded saxrat run on this machine, or a skip naming what is
    absent. CI has no corpus and must not go red for having none."""
    paths = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
    if not paths:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs say "
            "about how long a fight goes between kills cannot be counted here")
    return paths


def readings_of(path):
    """One entry per completed reading: its index, anomaly, rat count, whether
    the target bar was occupied, the hitpoint triple, and its decision lines.

    Consecutive status blocks carrying the same reading index are one reading.
    """
    out = []
    block = []
    last_index = None

    def flush(lines):
        nonlocal last_index
        index = anomaly = rats = triple = None
        locked = stalled = False
        for line in lines:
            found = READING_INDEX.search(line)
            if found is not None:
                index = int(found.group(1))
                named = ANOMALY.match(line)
                if named is not None:
                    anomaly = named.group(1)
                continue
            found = RATS.match(line) or RATS_OLD.match(line)
            if found is not None:
                rats = int(found.group(1))
                hitpoints = TARGET_HITPOINTS.match(found.group(2))
                if hitpoints is not None and "?" not in hitpoints.groups():
                    triple = tuple(int(v) for v in hitpoints.groups())
                continue
            found = DECISION.match(line)
            if found is not None:
                if found.group(1) == LOCKED_TARGET:
                    locked = True
                elif found.group(1) == STALL_BRANCH:
                    stalled = True
        if index is None or index == last_index:
            return
        last_index = index
        out.append({"index": index, "anomaly": anomaly, "rats": rats,
                    "locked": locked, "triple": triple, "stalled": stalled})

    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line == "--------":
                if block:
                    flush(block)
                block = []
            else:
                block.append(line)
    if block:
        flush(block)
    return out


def corpus():
    """The whole corpus, parsed once for the process.

    Cached for the reason PR #246 records: one class was re-reading every log
    per case, which cost more than the cases did.
    """
    if "runs" not in _corpus_cache:
        _corpus_cache["runs"] = {os.path.basename(path): readings_of(path)
                                 for path in saxrat_runs()}
    return _corpus_cache["runs"]


def fight_stretches(readings):
    """Runs of consecutive fight readings with no kill in them.

    Yields `(length, ended_in_a_kill, stalled_readings)`. A fight is underway
    where the target bar is occupied and the overview still shows a rat, which
    is `combatFightIsUnderway`'s own condition; a kill is the rat count falling.
    A small gap in the reading index is the log losing a status block rather
    than the bot's counter resetting, so it does not break a stretch.
    """
    previous = None
    run = []
    out = []

    def underway(entry):
        return entry["rats"] is not None and entry["rats"] > 0 and entry["locked"]

    for entry in readings:
        continuous = (previous is not None
                      and underway(previous) and underway(entry)
                      and entry["anomaly"] == previous["anomaly"]
                      and previous["index"] < entry["index"]
                      <= previous["index"] + 3)
        if not continuous:
            if run:
                out.append((len(run), False, sum(r["stalled"] for r in run)))
            run = []
            previous = entry
            continue
        if entry["rats"] < previous["rats"]:
            if run:
                out.append((len(run), True, sum(r["stalled"] for r in run)))
            run = []
        else:
            run.append(entry)
        previous = entry
    if run:
        out.append((len(run), False, sum(r["stalled"] for r in run)))
    return out


class TheCorpusIsWhereTheBoundsCameFrom(unittest.TestCase):
    """The measurement, recomputed rather than quoted.

    Counted in **readings** rather than decision lines, from the reading index
    the status line itself carries.
    """

    @classmethod
    def setUpClass(cls):
        cls.won = []
        cls.no_kill = []
        for readings in corpus().values():
            for length, killed, stalled in fight_stretches(readings):
                (cls.won if killed else cls.no_kill).append((length, stalled))
        if not cls.won:
            raise unittest.SkipTest(
                "no recorded saxrat runs on this machine carry a fight that "
                "produced a kill, so there is nothing to measure a bound "
                "against")
        cls.longest_won = max(length for length, _ in cls.won)
        # A stall is a stretch that never produced a kill and that the bot spent
        # at the branch run 48 stalled at, rather than one it broke off by
        # leaving. The branch is what makes it this bug and not an interrupted
        # fight.
        cls.stalls = sorted(length for length, stalled in cls.no_kill
                            if stalled > cls.longest_won)

    def test_the_longest_fight_that_produced_a_kill_is_below_the_bound(self):
        self.assertLess(
            self.longest_won, APPROACH_READINGS,
            "a fight in the corpus went %d readings between kills and still "
            "produced one, which is at or past the bound that would have "
            "interrupted it" % self.longest_won)

    def test_the_recorded_stalls_are_far_past_the_leave_bound(self):
        """The other population. Without these the bound would be one-sided."""
        self.assertTrue(
            self.stalls,
            "no recorded run holds a stall at all, so this corpus cannot say "
            "the bound catches one")
        self.assertGreater(
            min(self.stalls), LEAVE_READINGS,
            "the shortest recorded stall (%d readings) is not past the bound "
            "that ends it" % min(self.stalls))

    def test_the_two_populations_do_not_overlap(self):
        """What makes this a separator rather than a threshold with margin: the
        gap between the longest won fight and the shortest stall is empty, and
        both bounds sit inside it."""
        self.assertLess(self.longest_won, min(self.stalls))
        for bound in (APPROACH_READINGS, LEAVE_READINGS):
            with self.subTest(bound=bound):
                self.assertLess(self.longest_won, bound)
                self.assertLess(bound, min(self.stalls))

    def test_the_gap_is_wide_rather_than_a_coincidence(self):
        """A gap of one reading would satisfy the case above. This one is a
        multiple, which is what makes a bound placed in it a measurement."""
        self.assertGreater(
            min(self.stalls), self.longest_won * 4,
            "the shortest stall is not several times the longest won fight, so "
            "the separation these bounds rest on has narrowed")

    def test_the_stalls_are_the_branch_this_change_acts_on(self):
        """A control: the long no-kill stretches really are readings spent at
        `All locked up; bounce?`, not some other way of achieving nothing."""
        stalled_shares = [stalled / float(length)
                          for length, stalled in self.no_kill
                          if length > APPROACH_READINGS]
        self.assertTrue(
            stalled_shares,
            "no no-kill stretch in the corpus is long enough to reach the "
            "bound, so nothing here says the bound would ever fire")
        self.assertGreater(
            max(stalled_shares), 0.9,
            "the long no-kill stretches are not readings spent at the branch "
            "this change alters")


class TheHitpointRingMovesThroughoutTheStall(unittest.TestCase):
    """Why the obvious signal was measured and then not used.

    "The target's hitpoints stopped moving in the damaging direction" is what
    run 48 invites, and the corpus refuses it. Inside the longest recorded stall
    the ring rises far more often than it falls -- but it does fall, regularly
    enough that a counter reset by a fall never gets near the bound, which is the
    quantity that decides a rule rather than the share.
    """

    @classmethod
    def setUpClass(cls):
        longest = []
        for readings in corpus().values():
            run = []
            for entry in readings:
                if entry["stalled"] and entry["triple"] is not None:
                    run.append(entry)
                else:
                    if len(run) > len(longest):
                        longest = run
                    run = []
            if len(run) > len(longest):
                longest = run
        if len(longest) < APPROACH_READINGS:
            raise unittest.SkipTest(
                "no recorded saxrat runs on this machine hold a stall long "
                "enough to say anything about what the target's ring did "
                "inside one")
        cls.longest = longest
        cls.falls = cls.rises = cls.held = 0
        # How long a counter reset by a fall would ever have got, inside the one
        # stretch of readings this whole change exists to end.
        cls.longest_run_without_a_fall = 0
        since_a_fall = 0
        for before, now in zip(longest, longest[1:]):
            # `(structure, armor, shield)` -- the order the damage has to get
            # through, and the reading of "moved in the damaging direction" most
            # favourable to the rule being refuted here.
            a = (before["triple"][2], before["triple"][1], before["triple"][0])
            b = (now["triple"][2], now["triple"][1], now["triple"][0])
            if b < a:
                cls.falls += 1
                cls.longest_run_without_a_fall = max(
                    cls.longest_run_without_a_fall, since_a_fall)
                since_a_fall = 0
            else:
                cls.rises += b > a
                cls.held += b == a
                since_a_fall += 1
        cls.longest_run_without_a_fall = max(
            cls.longest_run_without_a_fall, since_a_fall)

    def test_the_ring_falls_inside_the_stall(self):
        """The damage was landing. Without this the incident would be a target
        the guns could not touch, which is a different bug."""
        self.assertGreater(
            self.falls, 0,
            "the target's ring never falls inside the longest recorded stall, "
            "which would make the hitpoint triple a usable signal after all")

    def test_it_rises_far_more_often_than_it_falls(self):
        """The repairs were faster than the guns, which is what the incident
        report leads with -- and on its own it is not an argument, since a rule
        could still key on the falls."""
        self.assertGreater(self.rises, self.falls)

    def test_a_counter_reset_by_a_fall_never_reaches_the_bound(self):
        """The measurement that decides it. However long the stall runs, the
        longest stretch inside it with no fall is the most such a counter would
        ever reach -- 113 readings against a bound of 200, so the branch goes on
        waiting and run 48 repeats.

        **This is the narrowest margin anywhere in the change and is stated as
        such.** It is 1.8x rather than the sevenfold separation the rat count
        gives, which is the whole reason the ring is measured here and read
        nowhere in `Bot.elm`.
        """
        self.assertLess(
            self.longest_run_without_a_fall, APPROACH_READINGS,
            "a counter reset whenever the target's ring falls reaches %d "
            "readings inside the longest recorded stall, which is past the "
            "bound -- so reading the ring would have worked here after all"
            % self.longest_run_without_a_fall)

    def test_the_ring_loses_most_of_the_stall_and_the_rat_count_does_not(self):
        """The comparison that makes the choice rather than the bound above: the
        stall is several times longer than anything the ring can see of it,
        while the rat count sees all of it."""
        self.assertGreater(
            len(self.longest), self.longest_run_without_a_fall * 4,
            "the longest stretch the ring can see of this stall is most of the "
            "stall, so the two signals no longer differ by much")

    def test_the_rat_count_is_what_stays_still(self):
        """The signal that does separate: nothing left the overview for the
        whole of it, which is what makes a counter reset by a kill run the
        length of the stall."""
        counts = {entry["rats"] for entry in self.longest}
        self.assertEqual(
            len(counts), 1,
            "the rat count moved inside the longest recorded stall, so the "
            "signal this rule is built on is not constant there after all")
        self.assertGreater(
            len(self.longest), LEAVE_READINGS,
            "the longest recorded stall is shorter than the ladder it has to "
            "outlast, so nothing here says the bound would ever fire")


# ---------------------------------------------------------------------------
# Source readers.
# ---------------------------------------------------------------------------


def top_level_declarations(source):
    """Every top-level declaration, as {name: body}, without its doc comment.

    `elm-format` puts exactly two blank lines between top-level declarations, so
    the split is structural rather than a guess.
    """
    found = {}
    for block in source.split("\n\n\n"):
        body = re.sub(r"^\{-.*?-\}\n", "", block, flags=re.DOTALL)
        match = re.match(r"^(?:type alias )?([a-zA-Z][a-zA-Z0-9_]*)\s*(?::|=)",
                         body)
        if match is not None:
            found[match.group(1)] = body
    return found


def declaration(source, name):
    declarations = top_level_declarations(source)
    if name not in declarations:
        raise AssertionError("no top-level declaration named " + name)
    return declarations[name]


def indented_let_field(source, name):
    """One `let` binding or record field, sliced by **indentation**.

    Not by the next ` <name> = `: the bindings read here build record literals
    and `case` expressions, and a reader that stops at the next assignment stops
    inside one -- so an assertion about a binding's later clauses passes having
    read nothing. PRs #147, #156, #159 and #162 each paid for that once.

    The leading run is `[ ]*` rather than `\\s*` for the same class of reason: a
    `\\s` run swallows the blank lines above the match, which puts the slice's
    own start in the wrong place and makes the indent it measures meaningless.
    A record field (`, name =`) is accepted as well as a `let` binding, since
    `updateMemoryForNewReadingFromGame` writes this count as one.
    """
    match = re.search(r"^([ ]*)(?:, )?%s =(?:[ ]*$|[ ])"
                      % re.escape(name), source, re.MULTILINE)
    if match is None:
        raise AssertionError("no let binding named " + name)
    indent = len(match.group(1))
    lines = source[match.start():].split("\n")
    kept = [lines[0]]
    for line in lines[1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        kept.append(line)
    return "\n".join(kept)


if __name__ == "__main__":
    unittest.main()
