"""Tests for a new licence refilling the wingman's acceleration-gate budget.

Issue #439, and it is #428's defect in the gate arm. A wingman printed all three
of these on one reading and did not move:

    Acceleration gate: on the overview, GIVEN UP after 41 readings of asking.
    Commander on this grid: SEEN AND GONE for 138 readings -- taken as him
    having left. Acceleration gates on this grid: 1. FOLLOWING HIM THROUGH IT,
    rats on the grid or not.

`FOLLOWING HIM THROUGH IT` is #411's permission granted; `GIVEN UP after 41
readings` is the budget for asking that gate already spent. `gateAskedReadings`
advanced only while `askingTheGateToOpen` -- which is `gateMayBeTaken` -- and
reached zero only where no gate was on the overview at all, so a budget spent
under the ordinary `not ratsOnTheGrid` permission was still spent when a
different, stronger licence arrived on the same gate and the same overview row.
`commanderLeftTheGrid` and `rejoiningAfterARetreat` both arrive mid-grid, so
nothing about the gate or the overview changes and no reset ever fires.

**What ships is #430's arrangement over a licence rather than a landing.**
`askedReadingsRefilledByANewLicence` answers the budget the counter carries
**into** this reading, refilled by a reason nothing has yet been spent against.
It is the carried-in value rather than the value written out, so the reading
that asks under the new licence is still charged -- a counter refilled after the
ask never charges the first reading of a new licence, which is #102's defect in
the direction that under-counts. Both branches of the counter read that one
value and the decision reads the count they write, so the arm and the memory
update cannot come to disagree about whether the new licence bought anything.

**"The licence changed" is a reason present now that has not already been spent
under, and not the looser "the licence is not the one it was".** The looser rule
cannot be used, and `gridIsClearOfRats` is why: rats arrive and die on a grid
constantly, so that reason comes and goes on its own and every difference would
hand the budget back when the last rat died --
`accelerationGateRefusesThisShipTicks` would then bound nothing at all.
`gateLicenceSpentUnderAfter` therefore *accumulates* the reasons already spent
against, so a reason returning is not a new one and one gate can spend at most
four budgets. `test_rats_coming_and_going_do_not_refill_the_budget` is that
claim executed, and it is the case the looser definition fails.

**The sessions are folded through the real
`updateMemoryForNewReadingFromGame`** over readings the real
`EveOnline.ParseUserInterface` produced, with the control -- the same grid, the
same length of session, no second licence -- beside each. Without that control a
session that ends un-given-up says nothing, since any counter that only rises
reaches any bound.

Confirmed by mutation, eleven of them, each failing at least one named case.
**The cases listed are the ones each mutation actually broke, read off the run
rather than predicted**, and where a mutation kills only two that is recorded as
it is rather than padded:

| the mutation | cases it fails |
|---|---|
| **the refill dropped from the counter** -- both branches reverted to `botMemoryBefore.gateAskedReadings`, which is the shipped defect | 5, including `test_a_licence_arriving_lets_the_gate_be_asked_again` and `test_the_arm_can_press_again_once_the_licence_changes` |
| **the refill applied to the increment and not to the hold**, which is the shipped defect wearing the fix's clothes | `test_a_licence_arriving_on_a_reading_that_does_not_ask_still_refills`, `test_the_counter_reads_the_refilled_budget` |
| `askedReadingsRefilledByANewLicence` answering `spentBefore` whatever the licence says -- the rule made inert | 6, including `test_a_reason_nothing_has_been_spent_under_refills_the_budget` and `test_the_bound_it_refills_is_the_arms_own` |
| the rule answering `0` unconditionally, so nothing is bounded | 6, including `test_the_budget_is_spent_under_one_unchanging_licence` and `test_a_licence_already_spent_under_refills_nothing` |
| **the looser definition** -- the rule answering `0` whenever `licenceNow /= spentUnder` | 5, including `test_a_reason_leaving_is_not_a_new_licence` and `test_rats_coming_and_going_do_not_refill_the_budget` |
| **`gateLicenceSpentUnderAfter` replacing rather than accumulating**, which is the same runaway reached from the memory rather than from the rule | `test_a_reason_already_spent_under_is_not_recorded_twice`, `test_the_licence_a_budget_was_spent_under_is_recorded` |
| the spent-under memory not clearing when the gate leaves the overview | `test_the_gate_leaving_the_overview_clears_it`, `test_the_gate_leaving_the_overview_still_resets` |
| the spent-under memory recording a licence on a reading that did not ask | `test_a_reading_that_did_not_ask_records_nothing`, `test_a_licence_arriving_on_a_reading_that_does_not_ask_still_refills` |
| **`gridIsClearOfRats` written as `gateCase.ratsOnTheGrid`** rather than its negation, so the licence disagrees with the permission about #348's guard | 10, including `test_the_licence_answers_what_the_permission_answers` and `test_the_grid_being_clear_is_the_reason_rather_than_the_rats` |
| **a reason dropped from `gateLicenceFromCase`**, which is a licence the refill can never see while the arm goes on behaving exactly as it does today | 9, including `test_the_licence_answers_what_the_permission_answers` and the three follow sessions |
| **`gateMayBeTaken` given back its own disjunction** rather than going through the licence, so a fifth reason could be added to the permission and left out of the refill silently | `test_the_permission_is_defined_over_the_licence` |

The last two are the ones a suite of session cases alone would miss: a reason
the refill cannot see, and a permission that has stopped being the licence's own.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""

import itertools
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
    COMMANDER, HEADER_LABELS, MEMBER_ROW, fleet_window, reading_binding)
from test_wingman_called_gate import (  # noqa: E402
    GATE, gate_row, overview, rat_row, selected_item_panel, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: Long enough to pass `accelerationGateRefusesThisShipTicks` (40) by one, so a
#: session that spends every reading of it ends given up on. Every assertion
#: asks the shipped constant rather than this number.
READINGS_TO_SPEND_THE_BUDGET = 41


def commander_row():
    """The commander's own overview row, as an ordinary pilot.

    Not a rat, so `getNamesOfRatsInOverview` does not count him and #348's
    guard is decided by the rat row alone. His row being here is also what
    keeps `commanderLeftTheGrid` off: `commanderPresenceAfterReading` answers
    `CommanderOnTheGrid` for as long as it is drawn.
    """
    return (COMMANDER, "Battlecruiser", True, False)


def grid(rows, panel=GATE):
    """A whole reading: the fleet window, the overview, a ship and the panel.

    The fleet window is what names the commander --
    `commanderOnGridFromReading` reads
    `fleetCommanderNameFromFleetWindowHeader` first and answers "cannot say"
    without it, so a fixture that leaves it out asks about a reading that
    cannot answer rather than one that answers no.

    The panel showing the gate is what makes `askingTheGateToOpen` true at all;
    without it every reading here would take the counter's hold branch and the
    budget would never be spent.
    """
    children = [
        fleet_window(HEADER_LABELS, [MEMBER_ROW]),
        overview(rows),
        ship_ui(),
    ]
    if panel is not None:
        children.append(selected_item_panel(panel))
    return children


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what folding a session costs."""

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        # One `UpdateMemoryContext`, exactly as the framework assembles it --
        # `test_wingman_landing_refills_the_budget`'s arrangement. Nothing
        # folded here dispatches anything, so an empty effect history is what
        # the framework would hand it, and `gridChangedThisReading` therefore
        # answers `False` on every reading: no warp ends and no gate is pressed,
        # so a commander who leaves the overview stays remembered.
        "updateContext = \\reading ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = reading"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , previousStepsEffects = []"
        " , botSettings = defaultBotSettings }",
        # A session, written as `(repeats, reading)` pairs. The `filterMap` is
        # what a fixture that never parsed falls out of, which is why every case
        # using this asks `sessionLength` beside it -- see #174 for why a
        # fixture that never arrived and a rule that answered nothing look
        # identical from outside.
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "memoryOver = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame"
        " (updateContext r) memory)"
        " initBotMemory",
        "askedOver = \\pairs -> memoryOver pairs |> .gateAskedReadings",
        "spentUnderOver = \\pairs -> memoryOver pairs |> .gateLicenceAskedUnder",
        # The step the arm takes with the panel already showing the gate and
        # already offering its button, which is the state every session below
        # ends in -- so what a case asks is whether the budget leaves the ship
        # able to press, rather than whether a fixture happens to select.
        "stepWith = \\asked -> accelerationGateActivationStep"
        " { panelShowsTheGate = True"
        ", panelOffersActivateGate = True"
        ", askedReadings = asked }",
        # And the same arm on a reading the panel is showing something else,
        # which is the state a licence can arrive in without the ship asking on
        # that reading -- the counter's *hold* branch rather than its
        # increment.
        "stepWithoutThePanel = \\asked -> accelerationGateActivationStep"
        " { panelShowsTheGate = False"
        ", panelOffersActivateGate = False"
        ", askedReadings = asked }",
        # The four inputs, in the order the arm hands them over.
        "gateCase = \\called -> \\left -> \\rejoining -> \\rats ->"
        " { ratsOnTheGrid = rats"
        ", calledByTheCommander = called"
        ", commanderLeftTheGrid = left"
        ", rejoiningAfterARetreat = rejoining }",
        "licence = \\called -> \\left -> \\rejoining -> \\rats ->"
        " gateLicenceFromCase (gateCase called left rejoining rats)",
        # The four licences the cases name. `clearOnly` is the one the live
        # reading's budget was spent under; `followOnly` is the one that arrived
        # and bought nothing.
        "clearOnly = licence False False False False",
        "followOnly = licence False True False True",
        "calledOnly = licence True False False True",
        "rejoinOnly = licence False False True True",
        "clearAndFollow = licence False True False False",
        "refill = \\now -> \\spentUnder -> \\spent ->"
        " askedReadingsRefilledByANewLicence"
        " { licenceNow = now, spentUnder = spentUnder, spentBefore = spent }",
        "spentUnderAfter = \\onOverview -> \\asked -> \\now -> \\before ->"
        " gateLicenceSpentUnderAfter"
        " { gateOnTheOverview = onOverview"
        ", askedThisReading = asked"
        ", licenceNow = now"
        ", before = before }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-gate-licence-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def elm_bool(value):
    return "True" if value else "False"


def collapsed(text):
    return re.sub(r"\s+", " ", text)


def without_comments(source):
    """The source with its doc comments and its line comments removed.

    A case that counts a name in the whole file counts the prose that names it
    too, and would then fail for a comment being edited rather than for a
    second copy of a rule appearing.
    """
    return re.sub(r"--[^\n]*", "", re.sub(r"\{-.*?-\}", "", source, flags=re.S))


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

    Sliced by indentation from the `, <field> =` that opens it to the next line
    indented no further, so a field whose value is itself an `if` ladder is read
    whole and the field after it is not read at all.
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


class TheLicenceIsThePermissionsOwnReasonsTest(unittest.TestCase):
    """The licence and the permission read one enumeration of the reasons.

    A licence that named three of the four, or that read `ratsOnTheGrid` where
    the permission reads its negation, would be a refill that never sees the
    reason it exists for -- and the arm would go on behaving exactly as it does
    today, which is this repo's signature failure.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_licence_answers_what_the_permission_answers(self):
        """All sixteen combinations of the four inputs, asked of both -- and of
        an expectation written here rather than of each other.

        `gateMayBeTaken` is now defined over the licence, so asking only
        whether the two agree is a case that cannot fail. What it is asked
        against instead is #348's guard and its three exceptions spelled out in
        Python, so a reason the licence drops or reads backwards is a
        disagreement rather than a shared mistake.
        """
        expressions = []
        expected = []
        for called, left, rejoining, rats in itertools.product(
                [False, True], repeat=4):
            inputs = (elm_bool(called), elm_bool(left), elm_bool(rejoining),
                      elm_bool(rats))
            permitted = called or left or rejoining or not rats
            expressions.append("gateIsLicensed (licence %s %s %s %s)" % inputs)
            expressions.append("gateMayBeTaken (gateCase %s %s %s %s)" % inputs)
            expected.extend([permitted, permitted])
        self.assertEqual(self.repl.evaluate(expressions), expected)

    def test_each_reason_licenses_the_gate_on_its_own(self):
        """Sixteen equalities pass for a rule that answers `True` always, so
        each reason is asked alone against a grid with rats on it -- which is
        the only state #348's guard refuses."""
        self.assertEqual(
            self.repl.evaluate([
                "gateIsLicensed calledOnly",
                "gateIsLicensed followOnly",
                "gateIsLicensed rejoinOnly",
                "gateIsLicensed clearOnly",
                "not (gateIsLicensed (licence False False False True))",
                "not (gateIsLicensed noGateLicence)",
            ]),
            [True] * 6)

    def test_the_grid_being_clear_is_the_reason_rather_than_the_rats(self):
        """The one field that is not the case's own, and the one a copy would
        get backwards: a licence has to be spelled positively."""
        self.assertEqual(
            self.repl.evaluate([
                "(licence False False False False).gridIsClearOfRats",
                "not (licence False False False True).gridIsClearOfRats",
                "(licence True False False True).calledByTheCommander",
                "(licence False True False True).commanderLeftTheGrid",
                "(licence False False True True).rejoiningAfterARetreat",
            ]),
            [True] * 5)

    def test_nothing_licenses_a_reading_with_no_gate(self):
        self.assertEqual(
            self.repl.evaluate([
                "not noGateLicence.calledByTheCommander",
                "not noGateLicence.commanderLeftTheGrid",
                "not noGateLicence.rejoiningAfterARetreat",
                "not noGateLicence.gridIsClearOfRats",
            ]),
            [True] * 4)


class TheRefillRuleTest(unittest.TestCase):
    """The shared rule on its own, executed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_reason_nothing_has_been_spent_under_refills_the_budget(self):
        """Both halves of what #439 asks for: from no licence to any licence,
        and from one licence to another the budget has not been spent under."""
        self.assertEqual(
            self.repl.evaluate([
                # Unlicensed to licensed, which is the plain case.
                "refill clearOnly noGateLicence 41 == 0",
                "refill followOnly noGateLicence 41 == 0",
                # The live reading: spent under the ordinary permission, and
                # #411's follow arrives on the same gate and the same row.
                "refill followOnly clearOnly 41 == 0",
                "refill calledOnly clearOnly 41 == 0",
                "refill rejoinOnly clearOnly 41 == 0",
                # The new reason arriving *beside* the spent one rather than
                # instead of it -- the commander leaves a grid that is still
                # clear.
                "refill clearAndFollow clearOnly 41 == 0",
                # A budget with nothing spent out of it is refilled to the same
                # zero, so the rule cannot be read as a way to gain readings.
                "refill followOnly clearOnly 0 == 0",
            ]),
            [True] * 7)

    def test_a_licence_already_spent_under_refills_nothing(self):
        """The control, and the behaviour this change does not touch: a gate
        asked under one unchanging reason still runs out of readings."""
        self.assertEqual(
            self.repl.evaluate([
                "refill clearOnly clearOnly 41 == 41",
                "refill clearOnly clearOnly 7 == 7",
                "refill followOnly followOnly 41 == 41",
                "refill clearAndFollow clearAndFollow 41 == 41",
                # Every reason present has been spent under, even though the
                # licence carries fewer of them than the memory does.
                "refill clearOnly clearAndFollow 41 == 41",
                "refill followOnly clearAndFollow 41 == 41",
            ]),
            [True] * 6)

    def test_a_reason_leaving_is_not_a_new_licence(self):
        """The looser definition -- refill whenever the licence differs from
        the one spent under -- fails here, and this is the case that says why
        it cannot be used: a reason going away buys the ship nothing, and
        `gridIsClearOfRats` goes away every time a rat warps in."""
        self.assertEqual(
            self.repl.evaluate([
                "refill clearOnly clearAndFollow 41 == 41",
                "refill followOnly clearAndFollow 41 == 41",
                # The licence gone entirely -- rats up on a grid whose
                # commander is back -- refills nothing either.
                "refill noGateLicence clearOnly 41 == 41",
                "refill noGateLicence clearAndFollow 41 == 41",
            ]),
            [True] * 4)

    def test_the_bound_it_refills_is_the_arms_own(self):
        """The rule buys back a budget rather than setting one, so the bound
        stays where `accelerationGateRefusesThisShipTicks` puts it."""
        self.assertEqual(
            self.repl.evaluate([
                "accelerationGateHasBeenGivenUpOn"
                " (refill clearOnly clearOnly"
                " (accelerationGateRefusesThisShipTicks + 1))",
                "not (accelerationGateHasBeenGivenUpOn"
                " (refill followOnly clearOnly"
                " (accelerationGateRefusesThisShipTicks + 1)))",
                "stepWith (refill clearOnly clearOnly"
                " (accelerationGateRefusesThisShipTicks + 1))"
                " == GiveUpOnThisGate",
                "stepWith (refill followOnly clearOnly"
                " (accelerationGateRefusesThisShipTicks + 1))"
                " == PressActivateGate",
            ]),
            [True] * 4)


class TheReasonsSpentUnderAreRememberedTest(unittest.TestCase):
    """What makes the refills bounded rather than a second runaway."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_reading_that_asked_records_its_reasons(self):
        self.assertEqual(
            self.repl.evaluate([
                "spentUnderAfter True True clearOnly noGateLicence == clearOnly",
                "spentUnderAfter True True followOnly noGateLicence == followOnly",
            ]),
            [True] * 2)

    def test_a_reading_that_did_not_ask_records_nothing(self):
        """A reading the arm did not spend is not a reading spent under
        anything -- and a memory that recorded one would let a licence the ship
        never asked under stop a later refill."""
        self.assertEqual(
            self.repl.evaluate([
                "spentUnderAfter True False followOnly clearOnly == clearOnly",
                "spentUnderAfter True False clearOnly noGateLicence"
                " == noGateLicence",
            ]),
            [True] * 2)

    def test_a_reason_already_spent_under_is_not_recorded_twice(self):
        """It accumulates rather than replacing, which is the whole of the
        bound: a memory that held only the last reason asked under would let
        two reasons that alternate refill the budget on every swap."""
        self.assertEqual(
            self.repl.evaluate([
                "spentUnderAfter True True followOnly clearOnly"
                " == clearAndFollow",
                "spentUnderAfter True True clearOnly followOnly"
                " == clearAndFollow",
                # And having accumulated both, neither can refill again.
                "refill clearOnly (spentUnderAfter True True followOnly"
                " clearOnly) 41 == 41",
                "refill followOnly (spentUnderAfter True True clearOnly"
                " followOnly) 41 == 41",
            ]),
            [True] * 4)

    def test_the_gate_leaving_the_overview_clears_it(self):
        """The same condition `gateAskedReadings` itself resets on: the count
        and the licence it was spent under are one episode."""
        self.assertEqual(
            self.repl.evaluate([
                "spentUnderAfter False True clearOnly clearAndFollow"
                " == noGateLicence",
                "spentUnderAfter False False clearOnly clearAndFollow"
                " == noGateLicence",
            ]),
            [True] * 2)


class TheBudgetIsRefilledInTheMemoryUpdateTest(unittest.TestCase):
    """#439's headline, folded through the real memory update.

    `test_the_budget_is_spent_under_one_unchanging_licence` is the control this
    class turns on: the same grid, the same length of session, no second
    licence -- and without it a bot that never counted anything would pass
    every other case here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            # The grid the live budget was spent on: no rats, so the ordinary
            # `not ratsOnTheGrid` permission licenses the gate, and the
            # commander's own row is drawn, so #411's follow cannot be what is
            # licensing anything.
            reading_binding("clearGrid",
                            grid([commander_row(), gate_row()])),
            # Rats up with the commander still on the grid: no reason at all,
            # so the counter holds.
            reading_binding("ratsUp",
                            grid([commander_row(), gate_row(), rat_row()])),
            # Rats up and the commander's row gone: #411's licence, once the
            # absence has persisted for `commanderGoneReadingsBeforeFollowing`
            # readings. This is the live reading, and the gate is the same row
            # on the same overview throughout.
            reading_binding("commanderGone",
                            grid([gate_row(), rat_row()])),
            # The same licence arriving on a reading the panel is showing
            # something else, so the ask does not go out and the counter takes
            # its hold branch -- which is where a refill applied to the
            # increment alone would leave the ship still given up on.
            reading_binding("commanderGoneUnselected",
                            grid([gate_row(), rat_row()], panel=None)),
            # No gate at all, which is the one reset the arm already had.
            reading_binding("noGate",
                            grid([commander_row()], panel=None)),
        ]
        spend = READINGS_TO_SPEND_THE_BUDGET
        cls.spent = "[ ( %d, clearGrid ) ]" % spend
        cls.spent_then_follow = (
            "[ ( %d, clearGrid ), ( 3, commanderGone ) ]" % spend)
        cls.spent_then_rats = (
            "[ ( %d, clearGrid ), ( 3, ratsUp ) ]" % spend)
        cls.spent_then_follow_unselected = (
            "[ ( %d, clearGrid ), ( 3, commanderGoneUnselected ) ]" % spend)
        cls.flickering = (
            "[ ( 20, clearGrid ), ( 2, ratsUp ), ( %d, clearGrid ) ]"
            % (spend - 20))
        cls.gate_leaves = (
            "[ ( %d, clearGrid ), ( 1, noGate ) ]" % spend)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a counter that never moved read
        alike, so what the parser made of each fixture is checked first --
        including that the gate is the same one row on every one of them, which
        is what stops the reset that already existed from explaining
        anything."""
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == %d"
                % (self.spent, READINGS_TO_SPEND_THE_BUDGET),
                "sessionLength %s == %d"
                % (self.spent_then_follow, READINGS_TO_SPEND_THE_BUDGET + 3),
                "sessionLength %s == %d"
                % (self.flickering, READINGS_TO_SPEND_THE_BUDGET + 2),
                # One gate, drawn, on all three grids that have one -- which is
                # also #411's fourth guard.
                "(clearGrid |> Maybe.map (accelerationGatesOnOverview"
                " >> List.length)) == Just 1",
                "(ratsUp |> Maybe.map (accelerationGatesOnOverview"
                " >> List.length)) == Just 1",
                "(commanderGone |> Maybe.map (accelerationGatesOnOverview"
                " >> List.length)) == Just 1",
                "(noGate |> Maybe.map (accelerationGatesOnOverview"
                " >> List.length)) == Just 0",
                # The panel is showing that gate, which is what lets a reading
                # spend the budget at all.
                "(clearGrid |> Maybe.andThen (\\r -> accelerationGateToAct r"
                " |> Maybe.map (\\g -> selectedItemIsOverviewEntry r g.gate)))"
                " == Just True",
                # The rat rows are counted as rats and the commander's is not.
                "(clearGrid |> Maybe.map getNamesOfRatsInOverview) == Just []",
                "(ratsUp |> Maybe.map (getNamesOfRatsInOverview"
                " >> List.length)) == Just 1",
                # And the commander is on the grid on the first two and gone on
                # the third, which is what the follow licence is derived from.
                "(clearGrid |> Maybe.map commanderOnGridFromReading)"
                " == Just (Just True)",
                "(ratsUp |> Maybe.map commanderOnGridFromReading)"
                " == Just (Just True)",
                "(commanderGone |> Maybe.map commanderOnGridFromReading)"
                " == Just (Just False)",
            ], definitions=self.definitions),
            [True] * 13)

    def test_the_budget_is_spent_under_one_unchanging_licence(self):
        """The control, and the bound doing its job: a gate asked under the
        ordinary permission and nothing else still runs out of readings."""
        self.assertEqual(
            self.repl.evaluate([
                "askedOver %s == %d"
                % (self.spent, READINGS_TO_SPEND_THE_BUDGET),
                "accelerationGateHasBeenGivenUpOn (askedOver %s)" % self.spent,
                "stepWith (askedOver %s) == GiveUpOnThisGate" % self.spent,
                # Rats arriving afterwards buy nothing either: no reason is
                # present at all on those readings, so the count holds.
                "accelerationGateHasBeenGivenUpOn (askedOver %s)"
                % self.spent_then_rats,
                "askedOver %s == %d"
                % (self.spent_then_rats, READINGS_TO_SPEND_THE_BUDGET),
            ], definitions=self.definitions),
            [True] * 5)

    def test_a_licence_arriving_lets_the_gate_be_asked_again(self):
        """The defect, fixed. The same gate on the same overview row, with
        #411's follow arriving on a grid that still has rats on it."""
        self.assertEqual(
            self.repl.evaluate([
                "not (accelerationGateHasBeenGivenUpOn (askedOver %s))"
                % self.spent_then_follow,
            ], definitions=self.definitions),
            [True])

    def test_the_reading_that_asks_under_the_new_licence_is_charged(self):
        """One, not zero. The refill is the budget the reading carries in, so
        the ask that goes out under the new licence is counted -- a counter
        refilled after the increment never charges the first reading of a new
        licence, which is #102's defect in the direction that under-counts."""
        self.assertEqual(
            self.repl.evaluate([
                "askedOver %s == 1" % self.spent_then_follow,
            ], definitions=self.definitions),
            [True])

    def test_the_arm_can_press_again_once_the_licence_changes(self):
        """What the operator watching the live reading wanted: the ship decides
        to follow and has readings to follow with."""
        self.assertEqual(
            self.repl.evaluate([
                "stepWith (askedOver %s) == PressActivateGate"
                % self.spent_then_follow,
            ], definitions=self.definitions),
            [True])

    def test_a_licence_arriving_on_a_reading_that_does_not_ask_still_refills(
            self):
        """The counter's hold branch, which is where a refill applied to the
        increment alone leaves the ship still given up on. The licence arrives
        while the panel is showing something else, so nothing is asked on that
        reading -- and the budget it carries in has to be the refilled one, or
        the very next reading that selects the gate finds it spent."""
        self.assertEqual(
            self.repl.evaluate([
                "askedOver %s == 0" % self.spent_then_follow_unselected,
                "not (accelerationGateHasBeenGivenUpOn (askedOver %s))"
                % self.spent_then_follow_unselected,
                "stepWithoutThePanel (askedOver %s) == SelectTheGate"
                % self.spent_then_follow_unselected,
                # And nothing was recorded as spent under it, so the reading
                # that does ask is still the one that charges.
                "spentUnderOver %s == clearOnly"
                % self.spent_then_follow_unselected,
            ], definitions=self.definitions),
            [True] * 4)

    def test_rats_coming_and_going_do_not_refill_the_budget(self):
        """The bound must still bound, and this is the session the looser
        definition of "the licence changed" fails: `gridIsClearOfRats` goes
        away when a rat warps in and comes back when it dies, and a refill on
        every difference would hand the budget back every time."""
        self.assertEqual(
            self.repl.evaluate([
                "askedOver %s == %d"
                % (self.flickering, READINGS_TO_SPEND_THE_BUDGET),
                "accelerationGateHasBeenGivenUpOn (askedOver %s)"
                % self.flickering,
                "stepWith (askedOver %s) == GiveUpOnThisGate" % self.flickering,
            ], definitions=self.definitions),
            [True] * 3)

    def test_the_gate_leaving_the_overview_still_resets(self):
        """The reset the arm already had, unchanged -- and the licence spent
        under goes with it, because the count and the reasons it was spent
        under are one episode."""
        self.assertEqual(
            self.repl.evaluate([
                "askedOver %s == 0" % self.gate_leaves,
                "spentUnderOver %s == noGateLicence" % self.gate_leaves,
            ], definitions=self.definitions),
            [True] * 2)

    def test_the_licence_a_budget_was_spent_under_is_recorded(self):
        """The memory the refill is asked against, folded rather than asked
        once: a run that spends its readings under the ordinary permission and
        then follows has both reasons recorded, so neither can buy a third
        budget."""
        self.assertEqual(
            self.repl.evaluate([
                "spentUnderOver %s == clearOnly" % self.spent,
                "spentUnderOver %s == clearAndFollow" % self.spent_then_follow,
                # Nothing was asked on the readings with rats up and the
                # commander present, so no reason was recorded for them.
                "spentUnderOver %s == clearOnly" % self.spent_then_rats,
            ], definitions=self.definitions),
            [True] * 3)


class TheCounterReadsTheSharedRuleTest(unittest.TestCase):
    """Source-pinned, because *where* the refill is applied is the change.

    A suite that only exercised `askedReadingsRefilledByANewLicence` would pass
    on a bot no counter read it from.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_counter_reads_the_refilled_budget(self):
        """Every branch that carries a count forward, so a version that
        refilled the increment and not the hold -- which is the shipped defect
        wearing the fix's clothes -- fails here."""
        field = collapsed(record_field(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =",
            "gateAskedReadings"))
        self.assertIn("gateAskedReadingsCarriedIn + 1", field)
        self.assertIn(
            "else if gateOnOverview /= Nothing then gateAskedReadingsCarriedIn",
            field)
        self.assertNotIn("botMemoryBefore.gateAskedReadings", field)

    def test_the_carried_in_budget_is_the_shared_rule(self):
        """And is handed this reading's licence against the reasons already
        spent under, rather than either of them restated."""
        binding = collapsed(
            indented_let_binding(self.source, "gateAskedReadingsCarriedIn"))
        self.assertIn("askedReadingsRefilledByANewLicence", binding)
        self.assertIn("licenceNow = gateLicenceNow", binding)
        self.assertIn("spentUnder = botMemoryBefore.gateLicenceAskedUnder",
                      binding)
        self.assertIn("spentBefore = botMemoryBefore.gateAskedReadings",
                      binding)

    def test_the_arm_and_the_refill_read_one_licence(self):
        """#102, and the half only a source read can see. The permission the
        ask is spent under and the licence the budget is refilled by are one
        binding, so they cannot come to disagree about which reason licensed a
        reading."""
        asking = collapsed(
            indented_let_binding(self.source, "askingTheGateToOpen"))
        self.assertIn("gateIsLicensed gateLicenceNow", asking)
        self.assertNotIn("gateMayBeTaken", asking)
        recorded = collapsed(record_field(
            self.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =",
            "gateLicenceAskedUnder"))
        self.assertIn("gateLicenceSpentUnderAfter", recorded)
        self.assertIn("licenceNow = gateLicenceNow", recorded)
        self.assertIn("askedThisReading = askingTheGateToOpen", recorded)

    def test_the_permission_is_defined_over_the_licence(self):
        """So a fifth reason cannot be added to `gateMayBeTaken` and left out
        of the refill: both read one closed record type, and an input the
        licence does not name is a type error at the arm rather than a budget
        the refill silently never sees."""
        body = collapsed(declaration(self.source, "gateMayBeTaken gateCase ="))
        self.assertIn("gateIsLicensed (gateLicenceFromCase gateCase)", body)
        for reason in ("calledByTheCommander", "commanderLeftTheGrid",
                       "rejoiningAfterARetreat", "ratsOnTheGrid"):
            with self.subTest(reason=reason):
                self.assertIn(
                    reason,
                    collapsed(declaration(
                        self.source, "gateLicenceFromCase gateCase =")))

    def test_the_refill_is_one_rule_with_one_reader(self):
        """One declaration, its annotation, and the single carried-in binding
        that calls it -- a second copy of "the licence changed" is what this
        refuses."""
        self.assertEqual(
            len(re.findall(r"askedReadingsRefilledByANewLicence",
                           without_comments(self.source))),
            3)

    def test_the_decision_reads_the_count_this_update_writes(self):
        """The other end of the same property: the arm and the status line ask
        the memory rather than recomputing a budget of their own, so a refilled
        count reaches both without either being changed."""
        press = collapsed(declaration(
            self.source, "pressTheAccelerationGate context gateToTake ="))
        self.assertIn("askedReadings = context.memory.gateAskedReadings", press)
        status = collapsed(declaration(
            self.source, "describeAccelerationGateAsk context ="))
        self.assertIn("context.memory.gateAskedReadings", status)


if __name__ == "__main__":
    unittest.main()
