"""Tests for a wingman rejoining a commander who is not broadcasting.

#429. Four wingmen retreated to repair in an escalation in Bika under a
**human** fleet commander -- Gal Bistot flown by hand, with its own bot not
running -- and not one of them got back. Kara Kernite states the cause in as
many words:

    Retreat recovery: the commander is off this grid and nothing names a place
    to fly to, so the reading is handed back. Nowhere remembered: no broadcast
    has named a place since this ship was last with its commander.

and all four report the other half:

    Warp to a fleet-mate: nobody this ship is flying to has a row on this
    overview.
    Approach on the commander: 'Gal Bistot' has NO OVERVIEW ROW.

Every route back was gated on something a human commander does not produce.
#415's recovery routes to `fleetPlaceBroadcast`, which is written only from the
broadcast banner; the warp-to-a-fleet-mate arm needs an overview row, which the
operator's preset does not draw for fleet members; and #348's guard refuses an
acceleration gate while rats are on the grid unless the commander *called* it,
which is another broadcast, and an escalation is one or two gates deep.

## What the change is

**A row that is always there.** The fleet window is open for the roster on
every reading whatever anybody broadcasts, and it already names the commander --
`fleetCommanderNameFromFleetWindowHeader` reads that header. What it could not
do was *click* it, so `fleetWindowRowForPilot` answers the same question as
nodes rather than as strings, and `warpToFleetMateFromTheirFleetWindowRow`
drives the client's own `Fleet Member` -> `Warp to Member` off it -- the same
cascade node `warpToFleetMateFromTheBroadcastBanner` drives, shared rather than
copied.

**A gate, asked before that warp.** `Warp to Member` lands this ship at the
mouth of the pocket rather than beside its commander, so a rule offering the
warp first would warp, land, find the commander still off grid and warp again
until the budget was gone. The gate clause is what terminates the rejoin, and it
reuses `accelerationGateStep` rather than adding a second gate mechanism.

**One uncalled gate, and the permission is scoped to the reading.**
`gateMayBeTaken` gains a third input, and `rejoinIsTakingThisGate` is the one
declaration that answers it -- asked of the shipped `RetreatRecoveryStep`, so
the permission exists only where `recoverFromRetreat` is itself dispatching this
gate. A recovery past its bound, a recovery routing to a remembered place, and a
bot that is not recovering at all each leave #348's guard exactly what it was.

**The bound is #415's, unchanged.** Both new answers are in
`retreatRecoveryAnswersThatSpendAReading`, because both dispatch, so they are
advanced and read by the same rule -- #102's defect is a counter advanced by one
condition and read by another. Past `retreatRecoveryAskedReadingsBound` the arm
hands the reading back rather than parking, which is #415's posture and is what
the two-root comparison below is about.

**And a place that *has* been broadcast still wins.** The two broadcast-fed
answers keep their places ahead of these two, so a reading #415 could act on is
a reading #429 does not touch. The stated cost is in `recoverFromRetreat`'s own
doc comment: a place remembered from before the retreat outranks a gate standing
right here.

## What these cases cannot establish

**Nobody has captured the menu the client offers on a fleet-window row.** The
`Fleet Member` -> `Warp to Member` rungs are recorded live off the broadcast
banner and off nothing else, and `fleetMemberNames`' own comment records the
boss being drawn in the window's *header* rather than in a `FleetMember` row --
so on this account the element this rejoin right-clicks is usually a header
label, and whether the client offers that menu there is **unknown**. There is no
client here to ask. What the cases can establish is that the element is found,
that the cascade driven off it is the one the banner path already drives, and
that the attempt is bounded and hands the reading back rather than parking when
it resolves nothing -- which is the shape a wrong premise fails in.

The cases run the real `Bot.elm` through `elm repl`, and the readings they ask
about come from the real `EveOnline.ParseUserInterface`. Nothing here reads a
live client, the recorded corpus, or a running bot -- there is no wingman corpus
to read (WINGMAN.md).

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
    label, node, reading_binding)
from test_wingman_called_gate import (  # noqa: E402
    GATE, gate_row, overview, rat_row, selected_item_panel, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: The commander the four live wingmen follow, and two pilots who are not him.
#: Two-word names, because that is what the client writes and because a
#: one-word name could not show that the row is matched exactly.
COMMANDER = "Gal Bistot"
OTHER_MATE = "Olivia Olivine"

#: The place a broadcast named in #381, kept here so the case that shows the
#: remembered-place path unchanged asks about a real one.
PLACE = "Madirmilire"


def fleet_window(header_names=(), member_rows=(), banner=None, history=()):
    """A `FleetWindow` the real parser accepts, in the four shapes needed here.

    `header_names` fills the header *below* its `Fleet (N)` label, which is
    where `fleetCommanderNameFromFleetWindowHeader` reads a commander -- the
    size label carries a parenthesis and that function's rule is the label
    without one. Left empty, nothing in the window names a commander and the
    fallback (`List.head follow-fleet-broadcast-from`) names one instead, which
    is the state the live #429 readings were in.

    `member_rows` and `history` both render as `entryLabel`, which is the
    client's own arrangement and the reason `textAfterBroadcastTimestamp`
    exists: only the `HH:MM:SS -` prefix tells a broadcast line from a pilot.
    """
    header = node("FleetHeaderContainer", {}, [
        label(text, (10, 10 + index * 16, 200, 16))
        for index, text in enumerate(["Fleet (5)"] + list(header_names))
    ], region=(0, 0, 300, 80))

    rows = [
        node("FleetMember", {}, [
            label(pilot, (10, 100 + index * 20, 200, 16), name="entryLabel"),
        ], region=(0, 100 + index * 20, 300, 20))
        for index, pilot in enumerate(member_rows)]

    lines = [
        node("FleetBroadcastEntry", {}, [
            label("02:59:%02d - %s" % (index, text),
                  (10, 200 + index * 20, 300, 16), name="entryLabel"),
        ], region=(0, 200 + index * 20, 300, 20))
        for index, text in enumerate(history)]

    children = [header] + rows + lines

    if banner is not None:
        children.append(
            node("FleetBroadcastCont", {}, [
                node("EveLabelMedium",
                     {"_name": "bannerLabel", "_setText": banner},
                     region=(10, 300, 280, 16)),
            ], region=(0, 294, 300, 24)))

    return node("FleetWindow", {}, children, region=(0, 0, 300, 400))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, doc comment stripped.

    Sliced on the signature line and ended at the next top-level declaration,
    so a claim about a rule's body cannot be satisfied by prose above it.
    """
    anchor = "\n%s :" % name
    assert anchor in source, name
    start = source.index(anchor) + 1
    rest = source[start:]
    end = rest.index("\n\n\n") if "\n\n\n" in rest else len(rest)
    return rest[:end]


def indented_block(source, header):
    """From `header` to the next line indented no further than `header` is.

    The readers that stop at a blank line or at a record's opening brace have
    already cost several PRs an assertion that passed having read nothing, and
    every binding asserted on below builds a record literal.
    """
    assert header in source, header
    start = source.index(header)
    first = header.split("\n")[-1]
    indent = len(first) - len(first.lstrip())
    lines = source[start:].split("\n")
    while lines and not lines[0].strip():
        lines = lines[1:]
    out = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        out.append(line)
    return "\n".join(out)


def step(recovering="True", named="True", on_grid="False", banner="False",
         remembers="False", gate="False", fleet_row="False", warping="False",
         asked=0):
    """The shipped rule, as one expression over seven facts and a count.

    The same helper `test_wingman_recovers_from_a_retreat` uses, restated here
    rather than imported so that this file's cases and that file's cases cannot
    come to disagree about the record's shape without one of them failing.
    """
    return ("retreatRecoveryStep { recovering = %s, commanderIsNamed = %s"
            ", commanderIsOnThisGrid = %s, bannerNamesTheCommander = %s"
            ", remembersWhereTheCommanderWas = %s"
            ", anAccelerationGateIsOnThisGrid = %s"
            ", fleetWindowNamesTheCommander = %s"
            ", shipIsWarpingOrJumping = %s"
            ", askedReadings = %s }"
            % (recovering, named, on_grid, banner, remembers, gate, fleet_row,
               warping, asked))


def may_be_taken(rats, called, rejoining):
    """`gateMayBeTaken`, over the two `Bool`s this issue owns.

    The record grew a fourth field when #411 landed -- `commanderLeftTheGrid`,
    the commander having gone through a gate without saying so. It is held off
    in every row here, for the reason this file already holds `calledByTheCommander`
    off where it is asking about the rejoin: an exception that is switched on
    would answer for the one under test. #411's own combinations are
    `test_wingman_follows_the_commander_through_a_gate`'s.
    """
    return ("gateMayBeTaken { ratsOnTheGrid = %s, calledByTheCommander = %s"
            ", rejoiningAfterARetreat = %s, commanderLeftTheGrid = False }"
            % (rats, called, rejoining))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    `recoverFromRetreat` takes a whole `BotDecisionContext` and a `ShipUI`, so a
    case cannot ask it anything without both. Every field of the context is
    either the shipped default (`defaultBotSettings`, `initBotMemory`) or the
    emptiest value its type has, so nothing in the fixture can decide the answer
    except the reading and the three memory fields a case sets --
    `test_wingman_recovers_from_a_retreat`'s arrangement, for its reason. The
    `ShipUI` comes out of the same really parsed reading, so the arm is handed
    what the bot would have been handed.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.PromptParser",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "settings = { defaultBotSettings | followFleetBroadcastFrom ="
        ' [ "%s" ] }' % COMMANDER,
        "memoryWith = \\recovering placeMemory asked ->"
        " { initBotMemory | recoveringFromRetreat = recovering"
        " , fleetPlaceBroadcast = placeMemory"
        " , retreatRecoveryAskedReadings = asked }",
        "contextWith = \\recovering remembered asked parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memoryWith recovering remembered asked"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "saidBy = \\pilot place -> Just { pilot = pilot, place = place }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeArm = \\recovering place asked parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.andThen"
        " (recoverFromRetreat (contextWith recovering place asked p)))"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "ARM STOOD DOWN"',
        "describeGate = \\recovering place asked parsed -> parsed"
        " |> Maybe.andThen (\\p ->"
        " accelerationGateStep (contextWith recovering place asked p))"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "GATE ARM STOOD DOWN"',
        "rootWith = \\recovering place asked parsed -> parsed |> Maybe.andThen"
        " (\\p -> p.shipUI |> Maybe.map"
        " (wingmanDecisionRootInSpace (contextWith recovering place asked p)))"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "NO READING"',
        "clauseWith = \\recovering place asked parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeRetreatRecovery (contextWith recovering place asked p))"
        ' |> Maybe.withDefault "NO READING"',
        "gateClauseWith = \\recovering place asked parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeAccelerationGateAsk (contextWith recovering place asked p))"
        ' |> Maybe.withDefault "NO READING"',
        "rowFor = \\pilot parsed -> parsed"
        " |> Maybe.andThen (fleetWindowRowForPilot pilot)"
        " |> Maybe.map (.totalDisplayRegion >> .y >> String.fromInt)"
        ' |> Maybe.withDefault "NO ROW"',
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-rejoin-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


class ReplCase(unittest.TestCase):
    """One repl for the whole class, opened once.

    `definitions` is a class attribute rather than a preamble entry, so a
    subclass that needs readings supplies them per question -- `ElmRepl.script`
    folds bindings into the one `let ... in` entry that asks it, which is what
    #172 measured as the cost of a question.
    """

    definitions = ()

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def bound(self):
        """`retreatRecoveryAskedReadingsBound`, read out of the running bot."""
        return int(self.repl.values(["retreatRecoveryAskedReadingsBound"],
                                    r"(\d+) : Int")[0])

    def answers(self, expressions):
        """Each step expression rendered as its constructor's name.

        One rendering per case rather than a `Bool` per constructor, so a rule
        that answered two things at once -- or none -- fails rather than
        passing on whichever one a case happened to name.
        """
        return self.repl.strings(
            ["(case %s of\n"
             "    NotRecoveringFromARetreat ->\n"
             '        "NotRecoveringFromARetreat"\n'
             "    NothingNamesTheCommander ->\n"
             '        "NothingNamesTheCommander"\n'
             "    GaveUpOnRejoiningTheCommander ->\n"
             '        "GaveUpOnRejoiningTheCommander"\n'
             "    AlreadyOnTheWayBackToTheCommander ->\n"
             '        "AlreadyOnTheWayBackToTheCommander"\n'
             "    RejoinTheCommanderOnThisGrid ->\n"
             '        "RejoinTheCommanderOnThisGrid"\n'
             "    WarpToTheCommanderFromTheBroadcast ->\n"
             '        "WarpToTheCommanderFromTheBroadcast"\n'
             "    RouteToWhereTheCommanderLastSaidHeWas ->\n"
             '        "RouteToWhereTheCommanderLastSaidHeWas"\n'
             "    GateThroughToTheCommander ->\n"
             '        "GateThroughToTheCommander"\n'
             "    WarpToTheCommanderFromTheFleetWindow ->\n"
             '        "WarpToTheCommanderFromTheFleetWindow"\n'
             "    NowhereToRejoinTheCommander ->\n"
             '        "NowhereToRejoinTheCommander")' % expression
             for expression in expressions],
            definitions=self.definitions)


class TheRuleReachesTheRejoinTest(ReplCase):
    """`retreatRecoveryStep` at #429's two answers, and their ordering.

    Every case here sets exactly one fact differently from the live reading the
    issue quotes -- recovering, commander named, off grid, no banner, nothing
    remembered -- so what the assertion is about is the fact rather than the
    record.
    """

    def test_the_live_reading_with_a_fleet_row_now_warps(self):
        """#429's own state, plus the row that was there all along.

        This is the whole change at the rule: the reading four wingmen printed
        `NowhereToRejoinTheCommander` on answers something now.
        """
        self.assertEqual(self.answers([step(fleet_row="True")]),
                         ["WarpToTheCommanderFromTheFleetWindow"])

    def test_a_gate_here_is_taken_before_the_warp_is_offered(self):
        """The clause that terminates the rejoin.

        `Warp to Member` lands this ship at the mouth of the pocket rather than
        beside its commander, so warping first would warp, land, find the
        commander still off grid and warp again until the budget was gone.
        """
        self.assertEqual(self.answers([step(gate="True", fleet_row="True")]),
                         ["GateThroughToTheCommander"])

    def test_a_gate_with_no_row_to_warp_to_is_still_taken(self):
        """The two are independent answers rather than two halves of one, so a
        grid carrying a gate is acted on whatever the fleet window shows."""
        self.assertEqual(self.answers([step(gate="True")]),
                         ["GateThroughToTheCommander"])

    def test_a_remembered_place_still_outranks_both(self):
        """#415's path is preserved, which the issue asks for in as many words:
        it works, it is cheaper, and it is the cross-system one."""
        self.assertEqual(
            self.answers([step(remembers="True", gate="True",
                               fleet_row="True")]),
            ["RouteToWhereTheCommanderLastSaidHeWas"])

    def test_the_banner_still_outranks_everything_below_it(self):
        self.assertEqual(
            self.answers([step(banner="True", remembers="True", gate="True",
                               fleet_row="True")]),
            ["WarpToTheCommanderFromTheBroadcast"])

    def test_the_commander_on_this_grid_still_outranks_both(self):
        """A rejoin that has arrived is a reunion, not a rejoin."""
        self.assertEqual(
            self.answers([step(on_grid="True", gate="True",
                               fleet_row="True")]),
            ["RejoinTheCommanderOnThisGrid"])

    def test_a_ship_in_warp_is_told_to_do_nothing(self):
        """The manoeuvre is the rejoin executing -- a ship gating across a
        pocket is warping, and charging it would bill this arm for the very
        flight it asked for."""
        self.assertEqual(
            self.answers([step(gate="True", fleet_row="True",
                               warping="True")]),
            ["AlreadyOnTheWayBackToTheCommander"])

    def test_the_give_up_outranks_both(self):
        """A spent budget must never be masked by a moment that happens to look
        actionable -- `approachFleetCommanderStep`'s ordering, and what keeps
        the gate permission below from outliving the attempt it belongs to."""
        self.assertEqual(
            self.answers([step(gate="True", fleet_row="True", asked=99)]),
            ["GaveUpOnRejoiningTheCommander"])

    def test_the_bound_is_asked_at_its_boundary_on_the_new_answers(self):
        """Both sides of the comparison and fixed values either side of it. A
        case asking only `constant - 1` and `constant` passes for any constant,
        including one that admits everything -- the hole four of #120's own
        cases had."""
        bound = self.bound()
        self.assertGreater(bound, 5)
        self.assertEqual(
            self.answers([step(gate="True", asked=asked)
                          for asked in (0, 5, bound - 1, bound,
                                        bound + 1, 999)]),
            ["GateThroughToTheCommander"] * 3
            + ["GaveUpOnRejoiningTheCommander"] * 3)

    def test_neither_a_gate_nor_a_row_is_still_nowhere(self):
        """The answer #429 was filed on, kept: with nothing at all this arm
        still hands the reading back rather than parking."""
        self.assertEqual(self.answers([step()]),
                         ["NowhereToRejoinTheCommander"])

    def test_a_commander_nothing_names_outranks_both(self):
        """Permission before the give-up and before every action, which is what
        stops an unset `follow-fleet-broadcast-from` reading as a spent
        budget."""
        self.assertEqual(
            self.answers([step(named="False", gate="True", fleet_row="True")]),
            ["NothingNamesTheCommander"])

    def test_a_ship_that_is_not_recovering_is_left_alone(self):
        """The gate clause must not reach a bot that is merely hunting -- that
        arm's own placement in the decision root is below this one."""
        self.assertEqual(
            self.answers([step(recovering="False", gate="True",
                               fleet_row="True")]),
            ["NotRecoveringFromARetreat"])


class TheCounterCountsWhatTheRejoinSpendsTest(ReplCase):
    """Which answers may advance the budget, executed rather than read.

    #429's two dispatch -- one drives `accelerationGateStep` and one a context
    menu cascade -- so both are advanced and read by the same rule the arm
    asks. A counter advanced by one condition and read by another is #102's
    defect, and #389 is what the wrong half costs.
    """

    def spends(self, names):
        return self.repl.evaluate(
            ["List.member %s retreatRecoveryAnswersThatSpendAReading" % name
             for name in names])

    def test_both_new_answers_spend_a_reading(self):
        self.assertEqual(
            self.spends(["GateThroughToTheCommander",
                         "WarpToTheCommanderFromTheFleetWindow"]),
            [True, True])

    def test_the_answers_that_came_first_are_unchanged(self):
        self.assertEqual(
            self.spends(["RejoinTheCommanderOnThisGrid",
                         "WarpToTheCommanderFromTheBroadcast",
                         "RouteToWhereTheCommanderLastSaidHeWas",
                         "NowhereToRejoinTheCommander",
                         "NotRecoveringFromARetreat",
                         "GaveUpOnRejoiningTheCommander",
                         "AlreadyOnTheWayBackToTheCommander"]),
            [True, True, True, False, False, False, False])


class TheFleetWindowRowIsFoundTest(ReplCase):
    """`fleetWindowRowForPilot` over really parsed fleet windows.

    Rendered as the node's own `totalDisplayRegion.y`, so a case can say *which*
    node was answered rather than only that some node was -- the member rows and
    the header labels carry the same text and are told apart by nothing else.
    """

    definitions = (
        reading_binding("readingHeaderOnly", [
            fleet_window(header_names=[COMMANDER, "Squad 1 (4)"],
                         member_rows=[OTHER_MATE]),
        ]),
        reading_binding("readingRowOnly", [
            fleet_window(member_rows=[OTHER_MATE, COMMANDER]),
        ]),
        reading_binding("readingBoth", [
            fleet_window(header_names=[COMMANDER],
                         member_rows=[OTHER_MATE, COMMANDER]),
        ]),
        reading_binding("readingHistoryOnly", [
            fleet_window(member_rows=[OTHER_MATE],
                         history=["%s is at location Amarr" % COMMANDER]),
        ]),
        reading_binding("readingLongerName", [
            fleet_window(member_rows=["Gal Bistoteles"]),
        ]),
        reading_binding("readingNoWindow", []),
    )

    def rows(self, expressions):
        return self.repl.strings(expressions, definitions=self.definitions)

    def test_the_fixtures_are_real(self):
        """The readings themselves, before anything is concluded from them: a
        case built on a tree the parser makes nothing of would pass or fail for
        reasons that have nothing to do with the rule."""
        self.assertEqual(
            self.repl.evaluate([
                "readingHeaderOnly /= Nothing",
                "readingNoWindow /= Nothing",
                "(readingHeaderOnly |> Maybe.andThen .fleetWindow) /= Nothing",
                "(readingNoWindow |> Maybe.andThen .fleetWindow) == Nothing",
                '(readingRowOnly |> Maybe.map fleetMemberNames'
                ' |> Maybe.withDefault []) == [ "%s", "%s" ]'
                % (OTHER_MATE, COMMANDER),
            ], definitions=self.definitions),
            [True, True, True, True, True])

    def test_the_header_label_is_a_row_this_bot_can_click(self):
        """The case #429 is actually about. `fleetMemberNames`' own comment
        records the boss being drawn in the header rather than in a
        `FleetMember` row, and the commander is the one pilot this is asked
        about -- so a lookup over the member rows alone would answer nothing for
        the pilot it exists for."""
        self.assertNotEqual(self.rows(['rowFor "%s" readingHeaderOnly'
                                       % COMMANDER])[0], "NO ROW")

    def test_a_member_row_is_found_too(self):
        self.assertNotEqual(self.rows(['rowFor "%s" readingRowOnly'
                                       % COMMANDER])[0], "NO ROW")

    def test_the_member_row_wins_where_the_window_draws_both(self):
        """A fleet whose window draws the commander as an ordinary member is a
        fleet where the member row is the more specific answer. The header sits
        at the top of this fixture and the rows below it, so the two are told
        apart by the node's own region rather than by its text."""
        header, both = self.rows(['rowFor "%s" readingHeaderOnly' % COMMANDER,
                                  'rowFor "%s" readingBoth' % COMMANDER])
        self.assertNotEqual(both, "NO ROW")
        self.assertNotEqual(both, header)

    def test_the_pilot_is_matched_exactly(self):
        """A substring match would warp this ship to whichever pilot's name
        merely contains the commander's -- `fleetInviteSenderFromMessageBox`'s
        reason, and it decides where this ship flies.

        The **broadcast history** is the case that makes this load-bearing
        rather than defensive, and it is why there is no timestamp filter in the
        rule. The history and the member rows share `entryLabel`, so
        `02:59:00 - Gal Bistot is at location Amarr` is a node this lookup sees
        -- and only a containing match could take it for his row. A separate
        filter for it was written first and no mutation could kill it, because
        the comparison already had.
        """
        self.assertEqual(
            self.rows(['rowFor "%s" readingHistoryOnly' % COMMANDER,
                       'rowFor "%s" readingLongerName' % COMMANDER,
                       'rowFor "Gal" readingRowOnly',
                       'rowFor "%s" readingRowOnly' % OTHER_MATE.upper()]),
            ["NO ROW", "NO ROW", "NO ROW", "NO ROW"])

    def test_the_history_fixture_really_carries_that_line(self):
        """Otherwise the case above asserts nothing about the history at all --
        a fixture that never arrived reads exactly like a rule that declined
        it."""
        self.assertEqual(
            self.repl.evaluate([
                "(readingHistoryOnly |> Maybe.map"
                " (fleetBroadcastHistoryEntries >> List.length))"
                " == Just 1",
                '(readingHistoryOnly |> Maybe.map fleetMemberNames'
                ' |> Maybe.withDefault []) == [ "%s" ]' % OTHER_MATE,
            ], definitions=self.definitions),
            [True, True])

    def test_a_shut_fleet_window_offers_nothing(self):
        self.assertEqual(self.rows(['rowFor "%s" readingNoWindow'
                                    % COMMANDER])[0], "NO ROW")


class TheArmWarpsToTheRowTest(ReplCase):
    """`recoverFromRetreat` run for real on #429's own reading shape.

    Recovering, the commander nowhere on the overview, nothing remembered and
    the banner showing somebody else's call -- which is exactly the caller
    `fleetMateBroadcastBannerElement` exists to keep the banner cascade away
    from, and therefore exactly the caller that had nothing left to click.
    """

    definitions = (
        # #429's reading, with the commander in the window's header. No gate on
        # the overview, so the warp is the answer rather than the gate.
        reading_binding("readingWithARow", [
            fleet_window(header_names=[COMMANDER],
                         banner="%s is at location Amarr" % OTHER_MATE),
            overview([("Sunder Alvi", "Frigate", True, True)]),
            ship_ui(),
        ]),
        # The same reading with nothing in the window naming the commander, so
        # `follow-fleet-broadcast-from` names one and no row exists for him.
        reading_binding("readingWithNoRow", [
            fleet_window(member_rows=[OTHER_MATE],
                         banner="%s is at location Amarr" % OTHER_MATE),
            overview([("Sunder Alvi", "Frigate", True, True)]),
            ship_ui(),
        ]),
    )

    def arm(self, reading="readingWithARow", recovering="True",
            place="Nothing", asked=0):
        return self.repl.strings(
            ["describeArm %s %s %s %s" % (recovering, place, asked, reading)],
            definitions=self.definitions)[0]

    def test_the_fixtures_are_real(self):
        self.assertEqual(
            self.repl.evaluate([
                "readingWithARow /= Nothing",
                "(readingWithARow |> Maybe.andThen .shipUI) /= Nothing",
                '(readingWithARow |> Maybe.map (pilotIsOnOverview "%s")'
                " |> Maybe.withDefault True) == False" % COMMANDER,
                '(readingWithARow |> Maybe.andThen'
                ' (fleetCommanderNameFromFleetWindowHeader)) == Just "%s"'
                % COMMANDER,
                '(readingWithNoRow |> Maybe.andThen'
                " (fleetCommanderNameFromFleetWindowHeader)) == Nothing",
                "(readingWithARow |> Maybe.map"
                " (nearestAccelerationGateOnOverview >> (/=) Nothing)"
                " |> Maybe.withDefault True) == False",
            ], definitions=self.definitions),
            [True, True, True, True, True, True])

    def test_the_reading_that_parked_four_wingmen_now_acts(self):
        line = self.arm()
        self.assertIn("Recovering from a retreat", line)
        self.assertIn("fleet-window row", line)
        self.assertIn(COMMANDER, line)

    def test_the_same_reading_with_no_row_still_hands_the_reading_back(self):
        """The discriminating control, and it differs in one thing: the fleet
        window naming the commander. Without it the arm answers exactly what it
        answered before #429."""
        self.assertEqual(self.arm(reading="readingWithNoRow"),
                         "ARM STOOD DOWN")

    def test_a_stale_banner_is_still_not_warped_to(self):
        """`fleetMateBroadcastBannerElement`'s refusal is untouched -- the
        banner on this reading is another pilot's, and it is the fleet window
        rather than the banner that this arm acts on."""
        self.assertNotIn("broadcast banner", self.arm())

    def test_a_remembered_place_is_still_what_is_flown_to(self):
        """#415's path preserved on the very reading #429 changes: with the
        commander's own place remembered, the arm routes there and says so
        rather than warping from the window."""
        line = self.arm(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE))
        self.assertIn(PLACE, line)
        self.assertNotIn("fleet-window row", line)

    def test_a_ship_not_recovering_is_left_alone(self):
        self.assertEqual(self.arm(recovering="False"), "ARM STOOD DOWN")

    def test_the_give_up_hands_the_reading_back(self):
        """#415's posture, on #429's path: bounded, and giving up rather than
        parking."""
        self.assertEqual(self.arm(asked=self.bound()), "ARM STOOD DOWN")


class TheRejoinTakesAnUncalledGateTest(ReplCase):
    """One grid asked twice, so what separates the answers is the rejoin.

    #348 refuses a gate while rats are on the grid because taking one mid-fight
    "abandons whatever the fleet is still fighting and leaves the commander a
    ship short in the pocket this bot just left". On the way back the commander
    is off this grid by construction, so there is no fleet fight here to abandon
    -- and landing in a room with rats is the normal case, which is why the
    rejoin could not have used the gate at all without this.
    """

    definitions = (
        # Rats and a gate on one grid, the commander nowhere on it and named by
        # the fleet window's header. Asked once as a rejoin and once as
        # ordinary hunting.
        reading_binding("readingGateAndRats", [
            fleet_window(header_names=[COMMANDER]),
            overview([gate_row(), rat_row()]),
            ship_ui(),
        ]),
        reading_binding("readingGateAndRatsSelected", [
            fleet_window(header_names=[COMMANDER]),
            overview([gate_row(), rat_row()]),
            selected_item_panel(GATE),
            ship_ui(),
        ]),
    )

    def gate(self, reading="readingGateAndRats", recovering="True",
             place="Nothing", asked=0):
        return self.repl.strings(
            ["describeGate %s %s %s %s" % (recovering, place, asked, reading)],
            definitions=self.definitions)[0]

    def test_the_fixture_really_carries_rats_and_a_gate(self):
        """Without this the pair below could agree for reasons that have
        nothing to do with either guard."""
        self.assertEqual(
            self.repl.evaluate([
                "(readingGateAndRats |> Maybe.map"
                " (getNamesOfRatsInOverview >> List.isEmpty)"
                " |> Maybe.withDefault True) == False",
                "(readingGateAndRats |> Maybe.map"
                " (nearestAccelerationGateOnOverview >> (/=) Nothing)"
                " |> Maybe.withDefault False) == True",
                '(readingGateAndRats |> Maybe.map (pilotIsOnOverview "%s")'
                " |> Maybe.withDefault True) == False" % COMMANDER,
            ], definitions=self.definitions),
            [True, True, True])

    def test_ordinary_hunting_still_refuses_that_grid(self):
        """#348's guard, unchanged, and the half the issue asks not to
        loosen."""
        self.assertIn("rats are still on the grid",
                      self.gate(recovering="False"))

    def test_the_rejoin_takes_the_same_gate(self):
        """One grid, asked twice: the answers differ, and what differs between
        the two questions is whether the retreat recovery is the arm acting."""
        line = self.gate()
        self.assertNotIn("rats are still on the grid", line)
        self.assertIn("acceleration gate", line)

    def test_the_rejoin_says_so_when_it_presses(self):
        """The press names the rejoin rather than reporting a clear overview,
        which on this grid would be a status line disagreeing with the decision
        it is on."""
        line = self.gate(reading="readingGateAndRatsSelected")
        self.assertIn("Gating back toward the commander", line)
        self.assertNotIn("The overview is clear of rats", line)

    def test_a_spent_budget_puts_the_guard_back(self):
        """The permission is the rejoin's reading rather than the retreat's
        latch: past the bound the recovery answers `GaveUpOnRejoiningTheCommander`
        and this grid is refused exactly as it is for a hunting bot."""
        self.assertIn("rats are still on the grid",
                      self.gate(asked=self.bound()))

    def test_a_recovery_routing_to_a_remembered_place_puts_it_back_too(self):
        """A recovery acting on #415's path is not the rejoin taking this gate,
        so the guard holds -- which is what makes `rejoinIsTakingThisGate` the
        rule rather than `recoveringFromRetreat`."""
        self.assertIn(
            "rats are still on the grid",
            self.gate(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE)))

    def test_the_rule_answers_its_eight_combinations(self):
        """`gateMayBeTaken` executed over the whole grid of its three inputs.

        The four rows with no rats are the ones that must not have changed, and
        the two exceptions are each asked on their own so that neither can be
        passing on the strength of the other.
        """
        self.assertEqual(
            self.repl.evaluate([
                may_be_taken(rats, called, rejoining)
                for rats in ("False", "True")
                for called in ("False", "True")
                for rejoining in ("False", "True")
            ]),
            [True, True, True, True, False, True, True, True])


class TheArmsBelowGetTheirReadingsBackTest(ReplCase):
    """The give-up's whole point, run rather than asserted.

    The arm answering `Nothing` is only worth anything if something below it
    then acts, so the real `wingmanDecisionRootInSpace` is run on one reading
    and its decision compared against the same root with nothing recovering.
    **Two-root equality alone is not evidence** -- a give-up that parks
    satisfies it by breaking both roots -- which is what the positive control
    beside it is for.
    """

    definitions = (
        reading_binding("readingWithSomethingToDo", [
            fleet_window(header_names=[COMMANDER],
                         banner="Target Sunder Alvi (Tristan)"),
            overview([("Sunder Alvi", "Frigate", True, True)]),
            ship_ui(),
        ]),
    )

    def root(self, recovering="True", place="Nothing", asked=0):
        return self.repl.strings(
            ["rootWith %s %s %s readingWithSomethingToDo"
             % (recovering, place, asked)],
            definitions=self.definitions)[0]

    def test_the_control_arm_acts_when_the_recovery_stands_down(self):
        """The positive control: with nothing recovering at all, the root
        reaches something below and acts on it. This is the case that kills a
        give-up which parks."""
        line = self.root(recovering="False")
        self.assertNotIn("Recovering from a retreat", line)
        self.assertNotEqual(line, "NO READING")

    def test_the_arms_below_are_reachable_once_the_rejoin_gives_up(self):
        """A rejoin that has spent its budget hands the reading back, and the
        root reaches the same decision it reaches with no recovery at all."""
        self.assertEqual(self.root(asked=self.bound()),
                         self.root(recovering="False"))

    def test_a_rejoin_that_can_act_still_owns_the_reading(self):
        """The negative control, and what stops the case above passing on a
        root that never reaches this arm at all."""
        self.assertIn("Recovering from a retreat", self.root())


class TheStatusLineNamesTheRejoinTest(ReplCase):
    """`describeRetreatRecovery` and `describeAccelerationGateAsk`, rendered.

    The arm answers `Nothing` for five of its ten cases, so from outside the
    decision tree the clause is the only thing that says which case a reading is
    in -- #381's lesson, and #429's own diagnosis came off exactly this line.
    """

    definitions = (
        reading_binding("readingForWarp", [
            fleet_window(header_names=[COMMANDER]),
            overview([("Sunder Alvi", "Frigate", True, True)]),
            ship_ui(),
        ]),
        reading_binding("readingForGate", [
            fleet_window(header_names=[COMMANDER]),
            overview([gate_row(), rat_row()]),
            ship_ui(),
        ]),
        reading_binding("readingForNowhere", [
            fleet_window(member_rows=[OTHER_MATE]),
            overview([("Sunder Alvi", "Frigate", True, True)]),
            ship_ui(),
        ]),
    )

    def clause(self, reading, recovering="True", place="Nothing", asked=0):
        return self.repl.strings(
            ["clauseWith %s %s %s %s" % (recovering, place, asked, reading)],
            definitions=self.definitions)[0]

    def gate_clause(self, reading, recovering="True", place="Nothing",
                    asked=0):
        return self.repl.strings(
            ["gateClauseWith %s %s %s %s"
             % (recovering, place, asked, reading)],
            definitions=self.definitions)[0]

    def test_the_warp_case_says_nothing_has_broadcast(self):
        line = self.clause("readingForWarp")
        self.assertIn("nothing has broadcast", line)
        self.assertIn("fleet-window row", line)
        self.assertIn("Readings spent: 0 of %d" % self.bound(), line)

    def test_the_gate_case_says_which_lever_it_is_on(self):
        line = self.clause("readingForGate")
        self.assertIn("acceleration gate", line)
        self.assertIn("Readings spent: 0 of %d" % self.bound(), line)

    def test_the_nowhere_case_now_names_all_four_levers(self):
        """The line #429 was diagnosed from, widened so that an operator
        reading it can tell which of the four is missing."""
        line = self.clause("readingForNowhere")
        self.assertIn("nothing names a place to fly to", line)
        self.assertIn("no acceleration gate is here", line)
        self.assertIn("fleet window shows no row", line)

    def test_the_gate_clause_says_the_rejoin_is_why_it_may_be_taken(self):
        """A gate taken with rats on the grid is the one reading where an
        operator most needs to know on whose authority."""
        self.assertIn("gating back to its commander after a retreat",
                      self.gate_clause("readingForGate"))

    def test_the_gate_clause_is_unchanged_for_ordinary_hunting(self):
        line = self.gate_clause("readingForGate", recovering="False")
        self.assertNotIn("gating back to its commander", line)
        self.assertIn("rats still on the grid", line)


class TheWiringIsWhereItSaysItIsTest(unittest.TestCase):
    """The placements a repl cannot reach, read out of the source.

    Sliced by **indentation** rather than to a blank line or a brace, since the
    bindings asserted on build record literals and the brace-stopping reader
    passes vacuously on those.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(WINGMAN_BOT_ELM)

    def test_the_guard_has_one_declaration(self):
        """One rule with four readers, so the arm, the press, the memory update
        and the status clause cannot hold four opinions about when #348's guard
        applies.

        **Two of those readers ask the licence rather than the `Bool` since
        #439**, and that is the same enumeration rather than a second one:
        `gateMayBeTaken` is now defined as `gateIsLicensed` over
        `gateLicenceFromCase`, and the memory update asks the licence because it
        has to know *which* reason licensed a reading to refill the gate budget
        when a new one arrives. What has to stay true is what this case asks:
        one declaration of the guard, and no reader with a disjunction of its
        own.
        """
        self.assertEqual(self.source.count("\ngateMayBeTaken :"), 1)
        self.assertEqual(self.source.count("\ngateMayBeTaken gateCase =\n"), 1)
        self.assertEqual(self.source.count("\ngateLicenceFromCase :"), 1)
        self.assertGreaterEqual(self.source.count("gateMayBeTaken\n"), 2)
        self.assertIn(
            "gateIsLicensed (gateLicenceFromCase gateCase)",
            declaration(self.source, "gateMayBeTaken"))
        self.assertIn(
            "gateLicenceFromCase",
            declaration(self.source, "updateMemoryForNewReadingFromGame"))

    def test_the_rejoin_permission_has_one_declaration_and_four_readers(self):
        """A constructor comparison restated beside each reader is #102's
        defect. This is the one place the comparison is made."""
        self.assertEqual(self.source.count("\nrejoinIsTakingThisGate :"), 1)
        self.assertEqual(
            self.source.count("== GateThroughToTheCommander"), 1)
        self.assertGreaterEqual(
            self.source.count("rejoinIsTakingThisGate "), 5)

    def test_the_memory_update_asks_the_rule_the_arm_asks(self):
        """`recoveringStepNow` is the answer that decides whether the reading
        spends the recovery's budget, so taking the gate permission from it is
        what stops the counter and the permission disagreeing about which
        reading it is."""
        # Read off `gateLicenceNow` since #439, which is where the four inputs
        # moved when the memory update grew a second thing to derive from them
        # -- the licence a spent budget is refilled by has to be the same
        # answer the ask is spent under. Which binding holds it does not
        # matter; what does is that the rejoin's half comes from
        # `recoveringStepNow`.
        #
        # The **binding** line rather than the type annotation above it: the
        # two are indented identically, so a reader anchored on the annotation
        # stops on the very next line and asserts nothing.
        binding = indented_block(self.source, "        gateLicenceNow =")
        self.assertIn("rejoinIsTakingThisGate recoveringStepNow", binding)
        self.assertIn(
            "gateIsLicensed gateLicenceNow",
            indented_block(self.source, "        askingTheGateToOpen ="))

    def test_the_rejoin_reuses_the_one_gate_mechanism(self):
        """`accelerationGateStep` rather than a second select-then-press, so the
        bound, the drone recall and the wording are the ones the hunting arm
        already uses."""
        arm = declaration(self.source, "recoverFromRetreat")
        self.assertIn("accelerationGateStep context", arm)
        self.assertEqual(
            self.source.count("accelerationGateStep context =\n"), 1)
        self.assertEqual(
            self.source.count("accelerationGateStep context")
            - self.source.count("accelerationGateStep context =\n"), 2)

    def test_the_rejoin_reuses_the_one_warp_to_member_cascade(self):
        """The menu node is shared with the banner path rather than copied --
        the question it answers is about what the client offers, not about which
        node was right-clicked."""
        cascade = declaration(
            self.source, "warpToFleetMateFromTheirFleetWindowRow")
        self.assertIn("warpToMemberFromTheBroadcastBanner", cascade)
        self.assertEqual(
            self.source.count("warpToMemberFromTheBroadcastBanner =\n"), 1)

    def test_the_row_lookup_has_one_definition(self):
        """Two ways of deciding which node is a pilot's own line would be two
        opinions about where this ship warps."""
        self.assertEqual(self.source.count("\nfleetWindowRowForPilot :"), 1)

    def test_the_rule_reads_the_gate_off_the_shipped_accessor(self):
        """`nearestAccelerationGateOnOverview` rather than a second overview
        walk, so the fact the rule answers on and the gate the arm then takes
        are the same row."""
        rule = declaration(self.source, "retreatRecoveryStepFromReading")
        self.assertIn("nearestAccelerationGateOnOverview", rule)
        self.assertIn("fleetWindowRowForPilot", rule)

    def test_the_arm_still_sits_below_the_retreat(self):
        """The one arm that outranks it, unchanged by #429: a ship whose health
        says leave must leave, and a rejoin that outranked the retreat would fly
        a damaged ship back toward the fight it just broke off from."""
        root = collapsed(declaration(self.source, "wingmanDecisionRootInSpace"))
        self.assertLess(root.index("retreatToTheCommander"),
                        root.index("recoverFromRetreat"))
