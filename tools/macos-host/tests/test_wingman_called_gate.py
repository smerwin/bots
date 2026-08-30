"""Tests for a `Target` broadcast on an acceleration gate taking the gate.

#393. There is no fleet broadcast that says *take this gate* -- `Align to` names
no object at all -- so `Target` is the only form carrying an object's identity,
and on an acceleration gate it is the commander sending the crew through rather
than a call to shoot it. That reinterpretation is scoped to a gate and to
nothing else.

Three things the owner decided, and each has cases here.

**A called gate is taken even with rats on the grid.** #348's guard refuses a
gate mid-fight because taking one "abandons whatever the fleet is still fighting
and leaves the commander a ship short in the pocket this bot just left". The FC
calling the gate is the explicit instruction that overrides it. **Scoped**: with
no broadcast, `accelerationGateStep` keeps that guard exactly as it was, and the
discriminating case here is one grid asked twice -- once through the called arm
and once through the uncalled one -- so what separates the two answers is the
broadcast and not the fixture.

**The drones still come home first**, through the `returnDronesToBay` every
other departing arm already uses rather than a second copy of one. With rats up
the drones are out essentially by construction, since `dronesAssistTheCommander`
is what puts them there, and CLAUDE.md records run 1 losing ten drones to
exactly this shape.

**And that recall is bounded**, copying saxrat's `droneRecallUnansweredTicks`:
it counts from the first recall the client did not answer, resets whenever the
in-space count falls, holds once it gives up, and names itself on every reading
it declines. Abandoning drones to make a called gate is a real cost and an
acceptable one; abandoning the gate to wait on drones that are not coming is
not.

**The gate check is asked before the lock**, whichever mechanism issues the
lock, because #366 replaces the cascade with a ctrl-click on the broadcast
banner and a ctrl-click will lock a gate as happily as the cascade does. That is
executed here rather than only read, so a refactor that moves the click cannot
quietly move it above the check.

## What is unverified, and these cases cannot close it

**Nobody has captured a `Target` broadcast naming an acceleration gate.** Two
string derivations have to agree for the row to be found at all --
`targetBroadcastPilotName` parses the name out of the banner, and
`overviewRowsForPilot` matches it against `objectName` by exact equality -- and
whether a broadcast on a gate renders the string the overview carries is
**unknown**. There is no client here to ask. So the fixtures below *assume* the
two agree, and what the cases can establish is that the recognition does not
silently do nothing when they do not: `CalledNameNamesNoOverviewRow` is its own
answer, `describeCalledObject` says so in words on every reading, and the arm
falls through to the lock path this bot takes today rather than to a wait.

The locked-target fall-through (`bringCalledTargetUnderFire` answering `Nothing`
once the client says the target is locked) is #389's and lives next door in
`test_wingman_engages_the_called_target.py`; it is not repeated here. What is
here is the fall-through of the two *new* silences -- a called gate whose row is
not drawn, and a called gate whose ask is spent.

The cases run the real `Bot.elm` through `elm repl`, and the readings they are
asked about go through the real `EveOnline.ParseUserInterface`. Nothing here
reads a live client, the recorded corpus, or a running bot.

## Confirmed by mutation

Twenty-one, each failing a named case:

| the mutation | what it breaks |
|---|---|
| `gateMayBeTaken` reverted to `not ratsOnTheGrid` | the override, 8 cases |
| `accelerationGateStep` passing `calledByTheCommander = True` | the override leaking to the uncalled path, 3 cases |
| `gateMayBeTaken` answering `True` | #348's guard gone entirely, 4 cases |
| `returnDronesToBay` dropped from the called path | `test_the_called_gate_path_calls_return_drones_to_bay` |
| the recall's give-up made unreachable | the bound, 4 cases |
| the bound's comparison moved by one | `test_the_recall_gives_up_at_the_bound` |
| the bound retuned to 5 | `test_the_bound_is_saxrats_own_number`, 6 cases |
| the give-up's own wording dropped | `test_the_give_up_names_itself_on_the_reading_it_declines` |
| the recall asked on the uncalled path too | `test_the_uncalled_path_never_recalls` |
| the counter never resetting on a partial recall | `test_a_partial_recall_is_the_client_answering` |
| the counter resetting past the give-up | `test_it_stops_at_the_bound_rather_than_running_away` |
| the counter advancing on every reading | `test_drones_home_and_an_uncalled_gate_spend_nothing` |
| **the gate check placed behind the lock** | the ordering, 7 cases |
| **the press claiming a clear grid on a called reading** | `test_the_press_on_a_called_gate_names_the_broadcast` |
| the `_display` filter dropped from the classification | `test_a_gate_row_that_is_not_drawn_is_neither_of_those` |
| a name no row carries collapsed into "not a gate" | `test_a_name_no_row_carries_is_its_own_answer` |
| the classification reading a head rather than the rows | `test_the_rule_answers_a_list_rather_than_a_head` |
| the Type cell dropped from the gate test | `test_the_type_cell_alone_is_enough_to_recognise_one` |
| the clause dropped from the status line | `test_the_clause_is_in_the_status_line` |
| the no-row clause losing the derivation risk | `test_the_status_line_says_when_a_called_name_matches_no_row` |
| the gate clause never saying it was called | `test_the_gate_clause_says_the_call_and_the_recall` |

The two in bold are the ones this whole design refuses: a check the #366
ctrl-click would make dead, and a log claiming a clear grid on readings that
had rats on them.

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

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: What the client is assumed to render for a called acceleration gate, in both
#: the banner and the overview's Name cell. See the module docstring: that the
#: two agree is the premise nobody has checked, not something these cases show.
GATE = "Acceleration Gate"
RAT = "Centii Minion"

#: The palette `iconSpriteHasColorOfRat` reads: red, and enough of it.
RAT_COLOR = {"aPercent": 100, "rPercent": 100, "gPercent": 10, "bPercent": 10}

ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20


def overview(rows):
    """An overview window whose rows carry a Name and a Type of their own.

    Each row is `(name, type_text, displayed, is_rat)`. Rebuilt here rather than
    imported from `test_wingman_engages_the_called_target` for that file's own
    reason -- its helper puts the same string in both cells and draws no
    `_display` or icon colour, and this file needs all three:

    - the Type column separate from the Name column, because
      `overviewEntryIsAnAccelerationGate` reads **both**, the defensive way
      `isNotableWreck` does, since which cell carries the words for this object
      class is not confirmed live;
    - `_display`, because a gate row that is not drawn is the one case this arm
      refuses to click;
    - the rat palette, because #348's guard is what the call overrides and
      `getNamesOfRatsInOverview` decides what a rat is from the icon.

    A header must span its cell (`parseListViewEntry`'s
    `headerRegionMatchesCellRegion`), which is why the column geometry is
    explicit rather than incidental.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (name, type_text, displayed, is_rat) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        icon_children = []
        if is_rat:
            icon_children.append(
                node("Sprite", {"_name": "iconSprite", "_color": RAT_COLOR},
                     region=(2, y, 8, ROW_HEIGHT)))
        entries.append(node(
            "OverviewScrollEntry",
            {"_name": "overviewEntry", "_display": bool(displayed)}, [
                label("2,000 m", (10, y, 50, ROW_HEIGHT)),
                label(name, (110, y, 150, ROW_HEIGHT)),
                label(type_text, (310, y, 150, ROW_HEIGHT)),
                node("SpaceObjectIcon", {}, icon_children,
                     region=(2, y, 12, ROW_HEIGHT)),
            ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def gate_row(displayed=True, name=GATE, type_text="Acceleration Gate"):
    return (name, type_text, displayed, False)


def rat_row(name=RAT):
    return (name, "Frigate", True, True)


def drones_window(in_space):
    """The drones window, with `in_space` drones out.

    `parseDronesWindowDroneGroupHeader` takes the smallest contained display
    text and `parseQuantityFromDroneGroupTitleText` reads the parenthesised
    numbers, so the title's own wording is what the count comes from.
    """
    return node("DronesWindow", {}, [
        node("DroneGroupHeader", {}, [
            label("Drones in Bay (0)", (0, 0, 200, 16)),
        ], region=(0, 0, 200, 16)),
        node("DroneGroupHeader", {}, [
            label("Drones in Space (%d/5)" % in_space, (0, 20, 200, 16)),
        ], region=(0, 20, 200, 16)),
    ], region=(0, 0, 200, 200))


def selected_item_panel(showing, offers_activate_gate=True):
    """The Selected Item panel, showing `showing` and offering its buttons.

    `selectedItemIsOverviewEntry` matches the row's Name against the panel's
    contained display texts, and `selectedItemButtonNamed` looks up a descendant
    by its own `_name` -- so both halves of the press condition come off this
    one node.
    """
    children = [label(showing, (600, 200, 200, 16), name="nameLabel")]
    if offers_activate_gate:
        children.append(
            node("Button", {"_name": "selectedItemActivateGate"},
                 region=(600, 220, 60, 20)))
    return node("SelectedItemWnd", {}, children, region=(600, 190, 200, 80))


def module_button(x, active):
    return node("ShipSlot", {"_name": "slot%d" % x}, [
        node("ModuleButton", {"_name": "modulebutton", "ramp_active": active},
             region=(x, 0, 32, 32)),
    ], region=(x, 0, 32, 32))


def ship_ui(modules=((10, True),)):
    """A `ShipUI` the real parser accepts, with `modules` in its top row.

    All three gauges are present because `parseShipUIFromUITreeRoot` answers
    `Nothing` for hitpoints unless every one of them is readable, and a fixture
    missing one would be asking about a reading the bot never gets.
    """
    def gauge(name, percent):
        return node("Gauge", {"_name": name, "_lastValue": percent / 100.0},
                    region=(0, 0, 100, 8))

    return node("ShipUI", {}, [
        node("CapacitorContainer", {}, region=(0, 40, 100, 20)),
        gauge("structureGauge", 100),
        gauge("armorGauge", 100),
        gauge("shieldGauge", 95),
    ] + [module_button(x, active) for x, active in modules],
        region=(0, 0, 400, 200))


def fleet_window_calling(target):
    """A fleet window whose banner calls `target`.

    `fleetBroadcastBannerText` reads a descendant named `bannerLabel`, and
    `targetBroadcastPilotName` takes everything after the leading `Target `.
    """
    return node("FleetWindow", {}, [
        label("Target %s" % target, (10, 10, 300, 16), name="bannerLabel"),
    ], region=(0, 0, 300, 400))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    Every field of the context is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide an answer except the reading and the
    memory a case names -- `test_wingman_engages_the_called_target`'s
    arrangement, with the memory made an argument because two of the cases here
    are about what a spent budget does.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "contextWith = \\memory -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # `FELL THROUGH` is a sentence no branch produces, so it reads as the
        # arm answering `Nothing` rather than as some decision this file failed
        # to anticipate.
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        "broadcastArm = \\memory -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " describeArm (actOnFleetBroadcast (contextWith memory p) s)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "gateArm = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeArm (accelerationGateStep (contextWith memory p)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The two status clauses, over a `Maybe` reading for the same
        # reason the arms are: a fixture that never decoded has to read as
        # itself rather than as a clause that said nothing.
        "describeCalled = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeCalledObject (contextWith memory p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "describeGate = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeAccelerationGateAsk (contextWith memory p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The gate answer rendered from a row the real parser produced,
        # since that constructor carries one.
        "describeGateAnswer = \\parsed -> parsed"
        " |> Maybe.andThen (.overviewWindows >> List.concatMap .entries"
        " >> List.filter overviewEntryIsAnAccelerationGate >> List.head)"
        " |> Maybe.map (CalledObjectIsAnAccelerationGate"
        '   >> describeCalledObjectOnOverview "X")'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # Which of the four the classification answers, and the name it carried
        # -- so a rule that answered about a different row than it selected is
        # visible rather than hidden behind a constructor name.
        #
        # Written across lines because Elm will not read a `case` whose arms
        # are on one: the harness indents every physical line of a binding for
        # exactly this.
        "calledObjectTag name parsed =\n"
        "    parsed\n"
        "        |> Maybe.map\n"
        "            (\\p ->\n"
        "                case calledObjectOnOverviewFromReading name p of\n"
        "                    CalledNameNamesNoOverviewRow ->\n"
        '                        "NO ROW"\n'
        "                    CalledObjectIsNotAGate ->\n"
        '                        "NOT A GATE"\n'
        "                    CalledGateIsNotDisplayed ->\n"
        '                        "GATE NOT DRAWN"\n'
        "                    CalledObjectIsAnAccelerationGate entry ->\n"
        '                        "GATE " ++ (entry.objectName |> Maybe.withDefault "?")\n'
        "            )\n"
        '        |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # `updateMemoryForNewReadingFromGame` folded over a list of readings,
        # answering the recall counter it left behind. `-1` where any fixture
        # never arrived, so a broken fixture cannot read as a counter that never
        # advanced.
        "recallCounterOver = \\readings ->"
        " if List.any ((==) Nothing) readings then -1 else"
        " (readings |> List.filterMap identity |> List.foldl (\\r -> \\m ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = r"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings } m) initBotMemory)"
        " |> .calledGateRecallAskedReadings",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-called-gate-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


#: The commander calls a gate while rats are on the grid and drones are out.
#: This one reading is what most of the decisions below are asked about, so the
#: answers differ by the rule rather than by the grid.
CALLED_GATE_MID_FIGHT = reading_binding(
    "calledGateMidFight",
    [fleet_window_calling(GATE),
     overview([gate_row(), rat_row()]),
     drones_window(3),
     ship_ui()])

#: The same grid with no broadcast at all -- the control for the override.
UNCALLED_GATE_MID_FIGHT = reading_binding(
    "uncalledGateMidFight",
    [overview([gate_row(), rat_row()]),
     drones_window(3),
     ship_ui()])

#: The called gate with the drones already home, so the recall has nothing to
#: ask for and the arm goes straight to the gate.
CALLED_GATE_DRONES_HOME = reading_binding(
    "calledGateDronesHome",
    [fleet_window_calling(GATE),
     overview([gate_row(), rat_row()]),
     drones_window(0),
     ship_ui()])

#: The called gate, drones home, and the panel already showing it and offering
#: Activate Gate -- the reading the press happens on.
CALLED_GATE_PANEL_READY = reading_binding(
    "calledGatePanelReady",
    [fleet_window_calling(GATE),
     overview([gate_row(), rat_row()]),
     drones_window(0),
     selected_item_panel(GATE),
     ship_ui()])

#: The uncalled gate with the panel ready and **no** rats, which is the state
#: #348 permits -- the control for the press wording.
UNCALLED_GATE_CLEAR_GRID = reading_binding(
    "uncalledGateClearGrid",
    [overview([gate_row()]),
     drones_window(0),
     selected_item_panel(GATE),
     ship_ui()])

#: A `Target` broadcast on something that is not a gate, on a grid that also
#: holds one -- so "there is a gate here" cannot stand in for "the gate was
#: called".
CALLED_RAT_BESIDE_A_GATE = reading_binding(
    "calledRatBesideAGate",
    [fleet_window_calling(RAT),
     overview([gate_row(), rat_row()]),
     drones_window(0),
     ship_ui()])

#: The called gate's row is in the tree and not drawn. Its region belongs to
#: whatever was recycled into its place, so nothing may click it.
CALLED_GATE_NOT_DRAWN = reading_binding(
    "calledGateNotDrawn",
    [fleet_window_calling(GATE),
     overview([rat_row(), gate_row(displayed=False)]),
     drones_window(0),
     ship_ui()])

#: The broadcast names something no overview row carries -- which is also what
#: the two string derivations disagreeing would look like.
CALLED_NAME_MATCHES_NOTHING = reading_binding(
    "calledNameMatchesNothing",
    [fleet_window_calling("Something Nobody Rendered"),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: The words are in the Type cell alone, which is the half no live reading has
#: confirmed for this object class.
GATE_NAMED_ONLY_IN_ITS_TYPE = reading_binding(
    "gateNamedOnlyInItsType",
    [fleet_window_calling("Vigil"),
     overview([gate_row(name="Vigil")]),
     ship_ui()])

#: A partial recall: the same call, one fewer drone in space.
CALLED_GATE_FEWER_DRONES = reading_binding(
    "calledGateFewerDrones",
    [fleet_window_calling(GATE),
     overview([gate_row(), rat_row()]),
     drones_window(1),
     ship_ui()])

CALLED_OBJECT_ANSWERS = ("NO ROW", "NOT A GATE", "GATE NOT DRAWN",
                         "GATE " + GATE, "THE FIXTURE NEVER ARRIVED")

RECALL_ANSWERS = ("NoDroneRecallBeforeThisGate", "RecallTheDronesFirst",
                  "LeaveTheDronesBehind")


def one_answer(expression, expected, answers, wrap="%s"):
    """`expression` equals `expected` and none of the other `answers`.

    Asked as one equality per answer rather than only the one a case names, so
    a rule that answers two things at once -- or none, which is what a fixture
    that never arrived produces -- fails rather than passing on whichever
    constructor the case happened to check.
    """
    return ([("(%s) == %s" % (expression, wrap % answer))
             for answer in answers],
            [answer == expected for answer in answers])


class TheCalledObjectIsRecognisedAsAGateTest(unittest.TestCase):
    """What the broadcast named, from the client's own overview row."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def answers(self, expression, expected, definitions=()):
        expressions, expect = one_answer(
            expression, expected, CALLED_OBJECT_ANSWERS, wrap='"%s"')
        self.assertEqual(
            self.repl.evaluate(expressions, definitions), expect)

    def test_a_row_whose_words_say_acceleration_gate_is_one(self):
        """The whole of #393: this is licence to activate, not to shoot."""
        self.answers(
            'calledObjectTag "%s" calledGateMidFight' % GATE,
            "GATE " + GATE,
            [CALLED_GATE_MID_FIGHT])

    def test_the_answer_carries_the_row_it_was_made_from(self):
        """A `Bool` beside a second `List.head` is the shape #303 and #389 both
        cost this bot: a state read off one row while the click is aimed at
        another. The tag prints the entry's own name for that reason, and this
        case is what makes the printed name load-bearing."""
        self.assertEqual(
            self.repl.strings(
                ['calledObjectTag "%s" calledGateMidFight' % GATE],
                [CALLED_GATE_MID_FIGHT]),
            ["GATE " + GATE])

    def test_anything_that_is_not_a_gate_still_goes_to_the_lock(self):
        """The reinterpretation is of one verb on one object class. A grid that
        holds a gate does not make a called rat one."""
        self.answers(
            'calledObjectTag "%s" calledRatBesideAGate' % RAT,
            "NOT A GATE",
            [CALLED_RAT_BESIDE_A_GATE])

    def test_a_name_no_row_carries_is_its_own_answer(self):
        """And it is the one the unverified premise fails into: if the banner's
        rendering is not the overview's Name cell, this is what the bot sees.
        Collapsing it into "not a gate" would hide that."""
        self.answers(
            'calledObjectTag "Something Nobody Rendered" calledNameMatchesNothing',
            "NO ROW",
            [CALLED_NAME_MATCHES_NOTHING])

    def test_a_gate_row_that_is_not_drawn_is_neither_of_those(self):
        """Its region belongs to whatever was recycled into its place, so
        selecting it acts on the wrong object -- and this click ends in a gate
        being activated. Distinct from "no row" so the status line can say which
        it is."""
        self.answers(
            'calledObjectTag "%s" calledGateNotDrawn' % GATE,
            "GATE NOT DRAWN",
            [CALLED_GATE_NOT_DRAWN])

    def test_the_row_is_really_hidden_in_that_fixture(self):
        """Otherwise the case above passes whatever the rule does with
        `_display`, which is the shape of a case that checks nothing."""
        self.assertEqual(
            self.repl.evaluate(
                ["calledGateNotDrawn |> Maybe.map (\\r ->"
                 " r.overviewWindows |> List.concatMap .entries"
                 " |> List.filter overviewEntryIsDisplayed"
                 ' |> List.any (.objectName >> (==) (Just "%s"))'
                 " |> not) |> Maybe.withDefault False" % GATE,
                 "calledGateNotDrawn |> Maybe.map (\\r ->"
                 " r.overviewWindows |> List.concatMap .entries"
                 " |> List.length |> (==) 2) |> Maybe.withDefault False"],
                [CALLED_GATE_NOT_DRAWN]),
            [True, True])

    def test_the_type_cell_alone_is_enough_to_recognise_one(self):
        """`overviewEntryIsAnAccelerationGate` reads Name **and** Type, the
        defensive way `isNotableWreck` does, because which cell carries the
        words for this object class is not confirmed live."""
        self.assertEqual(
            self.repl.strings(
                ['calledObjectTag "Vigil" gateNamedOnlyInItsType'],
                [GATE_NAMED_ONLY_IN_ITS_TYPE]),
            ["GATE Vigil"])

    def test_the_rule_answers_a_list_rather_than_a_head(self):
        """A grid whose first row naming the call is not the gate. Asked of the
        rule directly, over rows the real parser produced, because
        `overviewEntryForPilot` takes a head and a head cannot answer this."""
        self.assertEqual(
            self.repl.strings(
                ['calledObjectTag "Shared Name" twoRowsOneName'],
                [reading_binding(
                    "twoRowsOneName",
                    [fleet_window_calling("Shared Name"),
                     overview([("Shared Name", "Frigate", True, True),
                               ("Shared Name", "Acceleration Gate",
                                True, False)]),
                     ship_ui()])]),
            ["GATE Shared Name"])


class TheCallOverridesTheRatsGuardTest(unittest.TestCase):
    """#348's guard, and the one thing that overrules it.

    The override is asked at the rule and then shown on one grid asked both
    ways, because a rule that is right in isolation says nothing about whether
    the arm consults it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_rule_answers_the_four_combinations(self):
        """#429 gave the rule a second exception and this asks it with that one
        switched off, which is what keeps the case about #393's override.

        The whole grid of three inputs is next door, in
        `test_wingman_rejoins_without_a_broadcast`; what belongs here is that
        the call is the only thing that may take a gate with rats up **when
        nothing is rejoining**, and that it always may.
        """
        self.assertEqual(
            self.repl.evaluate([
                "gateMayBeTaken { ratsOnTheGrid = %s"
                ", calledByTheCommander = %s"
                ", rejoiningAfterARetreat = False }" % (rats, called)
                for rats, called in [("False", "False"), ("True", "False"),
                                     ("False", "True"), ("True", "True")]
            ]),
            [True, False, True, True],
            "only the call may take a gate with rats up, and it always may")

    def test_the_fixtures_really_carry_rats_and_a_gate(self):
        """Otherwise everything below passes on a grid #348's guard would have
        let through anyway, which is a case that checks nothing."""
        self.assertEqual(
            self.repl.evaluate(
                ["calledGateMidFight |> Maybe.map (getNamesOfRatsInOverview"
                 " >> List.length >> (==) 1) |> Maybe.withDefault False",
                 "calledGateMidFight |> Maybe.map (nearestAccelerationGateOnOverview"
                 " >> (/=) Nothing) |> Maybe.withDefault False",
                 "uncalledGateMidFight |> Maybe.map (getNamesOfRatsInOverview"
                 " >> List.length >> (==) 1) |> Maybe.withDefault False"],
                [CALLED_GATE_MID_FIGHT, UNCALLED_GATE_MID_FIGHT]),
            [True, True, True])

    def test_one_grid_asked_both_ways_answers_differently(self):
        """The discriminating case. Same rats, same gate, same drones: the
        called arm acts and the uncalled arm stays to fight, so what separates
        the two is the broadcast rather than the fixture.
        """
        called, uncalled = self.repl.strings(
            ["broadcastArm initBotMemory calledGateMidFight",
             "gateArm initBotMemory uncalledGateMidFight"],
            [CALLED_GATE_MID_FIGHT, UNCALLED_GATE_MID_FIGHT])
        self.assertIn("The commander broadcast a Target on the acceleration gate",
                      called)
        self.assertNotIn(
            "staying to fight rather than taking it", called,
            "the call is what overrides #348's hold, and the wrapper line "
            "naming the broadcast is printed whether or not it did")
        self.assertEqual(
            uncalled,
            "An acceleration gate is on the overview, but rats are still on "
            "the grid -- staying to fight rather than taking it."
            " | Wait for progress in game",
            "the uncalled path must keep #348's guard exactly as it was")

    def test_the_uncalled_arm_declines_that_grid_however_it_is_asked(self):
        """The override must not leak through the *nearest gate* arm either: a
        broadcast is what makes a gate called, and this arm never reads one."""
        self.assertEqual(
            self.repl.strings(
                ["gateArm initBotMemory calledGateMidFight"],
                [CALLED_GATE_MID_FIGHT]),
            ["An acceleration gate is on the overview, but rats are still on "
             "the grid -- staying to fight rather than taking it."
             " | Wait for progress in game"],
            "`accelerationGateStep` selects the nearest gate rather than the "
            "called one, so it is #348's guard whatever the banner says")

    def test_the_called_gate_is_recognised_before_any_lock_is_issued(self):
        """#366 replaces the cascade with a ctrl-click on the banner, and a
        ctrl-click will lock a gate as happily as the cascade does -- so a gate
        check placed behind the lock would be dead the moment that lands.

        Executed: the arm must not answer `Lock the called target`.
        """
        called = self.repl.strings(
            ["broadcastArm initBotMemory calledGateMidFight"],
            [CALLED_GATE_MID_FIGHT])[0]
        self.assertNotIn("Lock the called target", called)

    def test_a_called_rat_on_the_same_grid_is_still_locked(self):
        """The control: the gate check declines, and the lock this arm has
        always issued is issued."""
        self.assertTrue(
            self.repl.strings(
                ["broadcastArm initBotMemory calledRatBesideAGate"],
                [CALLED_RAT_BESIDE_A_GATE]
            )[0].startswith("Lock the called target '%s'." % RAT),
            "the lock path is unchanged for everything that is not a gate")

    def test_a_gate_row_that_is_not_drawn_falls_through(self):
        """Neither clicked nor waited on: `describeCalledObject` says so on
        every reading, and the drones and the guns still get their turn. An arm
        above them that answers `Just` on every reading starves them, which is
        #389's own closing note."""
        self.assertEqual(
            self.repl.strings(
                ["broadcastArm initBotMemory calledGateNotDrawn"],
                [CALLED_GATE_NOT_DRAWN]),
            ["FELL THROUGH"])

    def test_the_reading_falls_through_once_the_gate_ask_is_spent(self):
        """#389's closing note applied to the new arm: an arm above the guns
        that answers `Just` on every reading starves them whatever else is
        right.

        Past `accelerationGateRefusesThisShipTicks` the gate ask is spent and
        the whole broadcast arm hands the reading back, with the same grid
        before the budget was spent as the control -- since a rule that answered
        `Nothing` for everything would otherwise pass this.
        """
        spent, fresh = self.repl.strings(
            ["broadcastArm { initBotMemory | gateAskedReadings ="
             " accelerationGateRefusesThisShipTicks + 1 } calledGatePanelReady",
             "broadcastArm initBotMemory calledGatePanelReady"],
            [CALLED_GATE_PANEL_READY])
        self.assertEqual(spent, "FELL THROUGH")
        self.assertIn("activate it and take the fleet through", fresh)


class TheDecisionLineSaysWhichPathItIsOnTest(unittest.TestCase):
    """`The overview is clear of rats` is false on a gate taken mid-fight.

    A log claiming a clear grid on readings that had rats on it is worse than
    no line at all, and a pause nobody can account for is what an unnamed
    recall would be.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def arm(self, expression, definitions):
        return self.repl.strings([expression], definitions)[0]

    def test_the_press_on_a_called_gate_names_the_broadcast(self):
        called = self.arm("broadcastArm initBotMemory calledGatePanelReady",
                          [CALLED_GATE_PANEL_READY])
        self.assertIn(
            "The commander called this acceleration gate -- activate it and "
            "take the fleet through, rats on the grid or not.", called)
        self.assertNotIn(
            "The overview is clear of rats", called,
            "that grid had rats on it, and a log that says otherwise is worse "
            "than no line at all")

    def test_the_uncalled_press_keeps_the_wording_it_had(self):
        """The control, and the operator's existing grep."""
        self.assertIn(
            "The overview is clear of rats -- activate the acceleration gate "
            "to move to the next pocket.",
            self.arm("gateArm initBotMemory uncalledGateClearGrid",
                     [UNCALLED_GATE_CLEAR_GRID]))

    def test_the_recall_says_it_is_holding_the_gate(self):
        held = self.arm("broadcastArm initBotMemory calledGateMidFight",
                        [CALLED_GATE_MID_FIGHT])
        self.assertIn("Holding the called acceleration gate until the drones "
                      "are back", held)
        self.assertIn("0 of 60 readings of recall so far.", held)
        self.assertIn("I see there are drones in space. Return those to bay.",
                      held,
                      "the recall itself is the one every other departing arm "
                      "uses, so its own line is what should follow")

    def test_the_give_up_names_itself_on_the_reading_it_declines(self):
        """The other half of #11: a give-up that answers `Nothing` silently
        reads exactly like a bot that never had drones out. This one is printed
        on **every** reading it declines, not once, because #11's own first
        version fired on an equality test and said nothing on any other
        reading."""
        given_up = self.arm(
            "broadcastArm { initBotMemory | calledGateRecallAskedReadings ="
            " calledGateDroneRecallGiveUpReadings + 1 } calledGateMidFight",
            [CALLED_GATE_MID_FIGHT])
        self.assertIn("The drones have not answered 61 readings of recall and "
                      "are not coming back -- taking the called gate without "
                      "them", given_up)
        self.assertNotIn("Return those to bay", given_up)

    def test_the_status_line_says_a_called_gate_is_not_being_locked(self):
        """Rendered from the rule's own answer, so a case executes what an
        operator reads rather than asserting a substring over the branch --
        `describeWeaponsAsk`'s arrangement, for its reason. The gate answer is
        rendered from a row the real parser produced, since that constructor
        carries one."""
        gate, not_drawn, not_a_gate, no_row = self.repl.strings(
            ["describeGateAnswer calledGateMidFight",
             'describeCalledObjectOnOverview "X" CalledGateIsNotDisplayed',
             'describeCalledObjectOnOverview "X" CalledObjectIsNotAGate',
             'describeCalledObjectOnOverview "X" CalledNameNamesNoOverviewRow'],
            [CALLED_GATE_MID_FIGHT])
        self.assertIn("it is an ACCELERATION GATE, so this is the commander "
                      "sending the fleet through rather than a call to shoot "
                      "it -- taking it, rats on the grid or not.", gate)
        self.assertIn("its overview row is not drawn", not_drawn)
        self.assertIn("a target to shoot", not_a_gate)
        self.assertIn("NO OVERVIEW ROW names it", no_row)

    def test_the_status_line_says_when_a_called_name_matches_no_row(self):
        """The unverified premise's own failure mode, named in words: if the
        banner's rendering is not the overview's Name cell, this is the clause
        an operator reads, and it is the only thing that says so."""
        clause = self.repl.strings(
            ["describeCalled initBotMemory calledNameMatchesNothing"],
            [CALLED_NAME_MATCHES_NOTHING])[0]
        self.assertIn("Called target 'Something Nobody Rendered'", clause)
        self.assertIn(
            "the banner's own wording may not be the overview's Name cell",
            clause)

    def test_the_clause_says_nothing_where_there_is_no_broadcast(self):
        self.assertEqual(
            self.repl.strings(
                ["describeCalled initBotMemory uncalledGateMidFight"],
                [UNCALLED_GATE_MID_FIGHT]),
            ["Called target: none on the banner."])

    def test_the_gate_clause_says_the_call_and_the_recall(self):
        """`describeAccelerationGateAsk` is printed whether or not this arm is
        holding the tree, so a give-up that already handed the turn back is
        still visible."""
        called, uncalled = self.repl.strings(
            ["describeGate initBotMemory calledGateMidFight",
             "describeGate initBotMemory uncalledGateMidFight"],
            [CALLED_GATE_MID_FIGHT, UNCALLED_GATE_MID_FIGHT])
        self.assertIn("CALLED by the commander", called)
        self.assertIn("holding it for the drones (0 of 60 readings of recall)",
                      called)
        self.assertIn("rats still on the grid -- not taking it.", uncalled)
        self.assertNotIn("CALLED", uncalled)

    def test_the_gate_clause_reports_the_drone_give_up(self):
        self.assertIn(
            "DRONES GIVEN UP ON after 61 readings of recall",
            self.repl.strings(
                ["describeGate { initBotMemory | calledGateRecallAskedReadings ="
                 " calledGateDroneRecallGiveUpReadings + 1 } calledGateMidFight"],
                [CALLED_GATE_MID_FIGHT])[0])

    def test_the_clause_is_in_the_status_line(self):
        """Sliced to `statusTextFromState` rather than searched for in the
        file: the substring occurs in the declaration's own head, so a case
        that only searched the source would pass with the clause dropped --
        "assert the form, not the substring", which #109, #122 and #145 each
        paid for once."""
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        status = source[source.index("\nstatusTextFromState context ="):]
        status = status[:status.index("\n\n\n")]
        self.assertIn("describeCalledObject context", status)
        self.assertIn("describeAccelerationGateAsk context", status)


class TheRecallIsBoundedTest(unittest.TestCase):
    """saxrat's `droneRecallUnansweredTicks`, in this bot and on this path.

    The rule is asked at its boundary and at fixed values either side of it --
    a case that only asks about `constant - 1` and `constant` passes for any
    constant, including one that admits everything -- and the counter is folded
    over whole sessions rather than asked once, because a counter that is right
    for one reading and wrong across a session is the defect that shape
    prevents.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def answers(self, expression, expected):
        expressions, expect = one_answer(
            expression, expected, RECALL_ANSWERS)
        self.assertEqual(self.repl.evaluate(expressions), expect)

    def recall(self, asked, called="True", in_space="True"):
        return ("calledGateDroneRecall { calledByTheCommander = %s"
                ", dronesAreInSpace = %s, askedReadings = %s }"
                % (called, in_space, asked))

    def test_a_called_gate_with_drones_out_recalls_them_first(self):
        self.answers(self.recall(0), "RecallTheDronesFirst")

    def test_drones_already_home_ask_for_nothing(self):
        self.answers(self.recall(0, in_space="False"),
                     "NoDroneRecallBeforeThisGate")

    def test_the_uncalled_path_never_recalls(self):
        """Scoped to the called gate. #348's guard means the uncalled arm's
        grid is clear, so adding a recall there is a behaviour change with its
        own evidence to gather -- and it is deliberately not made here."""
        self.answers(self.recall(0, called="False"),
                     "NoDroneRecallBeforeThisGate")
        self.answers(self.recall("calledGateDroneRecallGiveUpReadings + 50",
                                 called="False"),
                     "NoDroneRecallBeforeThisGate")

    def test_the_recall_gives_up_at_the_bound(self):
        self.answers(self.recall("calledGateDroneRecallGiveUpReadings - 1"),
                     "RecallTheDronesFirst")
        self.answers(self.recall("calledGateDroneRecallGiveUpReadings"),
                     "RecallTheDronesFirst")
        self.answers(self.recall("calledGateDroneRecallGiveUpReadings + 1"),
                     "LeaveTheDronesBehind")

    def test_the_bound_holds_at_fixed_values_either_side_of_it(self):
        """The hole #120's four cases had: a boundary pair passes for any
        constant, including one that gives up immediately and one that never
        does."""
        self.answers(self.recall(3), "RecallTheDronesFirst")
        self.answers(self.recall(500), "LeaveTheDronesBehind")

    def test_the_bound_is_saxrats_own_number(self):
        """Copied rather than chosen. It is the only drone-recall number in
        this repository with any evidence behind it, and this bot has no corpus
        of its own -- no wingman run has ever recalled drones before a gate."""
        self.assertEqual(
            self.repl.evaluate(["calledGateDroneRecallGiveUpReadings == 60"]),
            [True])

    def counter(self, expressions, definitions):
        return [int(answer) for answer in self.repl.values(
            expressions, r"(-?\d+) : Int", definitions)]

    def test_the_counter_advances_while_the_recall_is_being_asked(self):
        self.assertEqual(
            self.counter(
                ["recallCounterOver (List.repeat 5 calledGateMidFight)"],
                [CALLED_GATE_MID_FIGHT]),
            [5])

    def test_it_stops_at_the_bound_rather_than_running_away(self):
        """Giving up is what stops the asking, so the count holds past the
        bound rather than resetting -- without that the ship alternates forever
        between abandoning its drones and recalling them."""
        self.assertEqual(
            self.counter(
                ["recallCounterOver (List.repeat 100 calledGateMidFight)",
                 "recallCounterOver (List.repeat 300 calledGateMidFight)"],
                [CALLED_GATE_MID_FIGHT]),
            [61, 61])

    def test_a_partial_recall_is_the_client_answering(self):
        """The in-space count falling resets the patience rather than counting
        against it, which is saxrat's own rule."""
        self.assertEqual(
            self.counter(
                ["recallCounterOver (List.repeat 4 calledGateMidFight"
                 " ++ [ calledGateFewerDrones ])"],
                [CALLED_GATE_MID_FIGHT, CALLED_GATE_FEWER_DRONES]),
            [0])

    def test_drones_home_and_an_uncalled_gate_spend_nothing(self):
        """The counter counts readings the arm asked on, taken from the rule
        the arm itself asks -- #102's defect is a counter advanced by one
        condition and read by another."""
        self.assertEqual(
            self.counter(
                ["recallCounterOver (List.repeat 5 calledGateDronesHome)",
                 "recallCounterOver (List.repeat 5 uncalledGateMidFight)"],
                [CALLED_GATE_DRONES_HOME, UNCALLED_GATE_MID_FIGHT]),
            [0, 0])

    def test_the_fixtures_really_arrived(self):
        """`-1` is the sentinel for a fixture that never decoded, and a case
        asserting `0` cannot tell that from a counter that never advanced."""
        self.assertEqual(
            self.counter(["recallCounterOver [ Nothing ]"], []),
            [-1])


def collapsed(text):
    return re.sub(r"\s+", " ", text).strip()


def declaration(source, head):
    body = source[source.index(head):]
    return body[:body.index("\n\n\n")]


class TheRecallIsTheOneEveryOtherDepartingArmUsesTest(unittest.TestCase):
    """Read out of the source: the wiring the repl cannot expose.

    A second recall mechanism would compile, would look right in the log, and
    would drift from the one the warps and the docks use -- which is why the
    issue says it must not become a second copy of one.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_called_gate_path_calls_return_drones_to_bay(self):
        body = declaration(
            self.source, "takeTheAccelerationGate context gateToTake =")
        self.assertIn("returnDronesToBay context", body)

    def test_there_is_still_one_recall_mechanism(self):
        """The cascade that actually recalls occurs once. A second copy is what
        #374 found the *decline* had already become."""
        self.assertEqual(
            self.source.count('useMenuEntryWithTextContaining "Return to drone bay"'),
            1)
        self.assertEqual(
            self.source.count("returnDronesToBay : BotDecisionContext"), 1)

    def test_the_gate_check_is_what_the_arm_dispatches_on(self):
        """Executed next door; read here so a #366 refactor that moves the
        ctrl-click into this function has to notice the ordering it must keep.

        The assertion is about the *dispatch* rather than about which name
        appears first in the text: the lock lives in a `let` binding, which is
        lazy, so its position says nothing. What has to hold is that the thing
        the function branches on is the classification -- then whatever the lock
        turns out to be, a gate never reaches it.
        """
        body = declaration(
            self.source, "bringCalledTargetUnderFire context calledTarget =")
        dispatch = body[body.index("\n    in\n") + len("\n    in\n"):]
        self.assertTrue(
            dispatch.lstrip().startswith(
                "case calledObjectOnOverviewFromReading calledTarget"),
            "the gate check has to be asked before the lock is decided, "
            "whichever mechanism issues the lock: %r" % dispatch[:120])
        self.assertNotIn(
            "calledTargetIsLocked", dispatch,
            "the lock question belongs to the branches that are not a gate")
        self.assertIn("takeTheCalledAccelerationGate", dispatch)

    def test_the_counter_asks_the_rule_the_arm_asks(self):
        """#102: a counter advanced by one condition and read by another is two
        rules on two schedules."""
        update = declaration(
            self.source,
            "\nupdateMemoryForNewReadingFromGame context botMemoryBefore =")
        self.assertIn("calledGateDroneRecall", update)
        self.assertIn("calledGateRecallAskedReadingsAfter", update)
        self.assertNotIn(
            "calledGateDroneRecallGiveUpReadings", update,
            "the advance must ask the rule rather than re-deriving its bound")

    def test_the_override_has_one_declaration_and_three_readers(self):
        """Three opinions about when #348's guard applies is how the arm, the
        counter and the status line come apart.

        The record grew a third field in #429 and the property did not: what is
        asserted is the two inputs this issue owns and the one declaration, so a
        later exception has to be added to the same rule rather than beside it.
        """
        # Anchored on the annotation line rather than on the bare name, which
        # occurs first in a doc comment several declarations earlier.
        signature = collapsed(declaration(self.source, "\ngateMayBeTaken :"))
        self.assertIn("ratsOnTheGrid : Bool", signature)
        self.assertIn("calledByTheCommander : Bool", signature)
        self.assertEqual(
            len(re.findall(r"^gateMayBeTaken\b", self.source, re.M)), 2,
            "one annotation and one definition")
        for reader in ("takeTheAccelerationGate context gateToTake =",
                       "\nupdateMemoryForNewReadingFromGame context botMemoryBefore =",
                       "describeAccelerationGateAsk context ="):
            self.assertIn("gateMayBeTaken",
                          declaration(self.source, reader),
                          "%s has to ask the rule rather than restate it"
                          % reader)

    def test_nothing_else_re_derives_whether_drones_are_in_space(self):
        """`dronesAreInSpace` and the count are one definition, so the recall,
        its decline and the counter cannot come apart -- which is exactly what
        #374 found had happened to the first two."""
        self.assertIn(
            "dronesAreInSpace readingFromGameClient = 0 < "
            "dronesInSpaceCountFromReading readingFromGameClient",
            collapsed(self.source))
        self.assertEqual(
            self.source.count(
                "dronesInSpaceCountFromReading : ReadingFromGameClient -> Int"),
            1)

    def test_the_row_selection_has_one_definition(self):
        """The lock, the lock recognition and the gate classification read one
        list, so a rule that decides and a click that acts cannot end up on two
        different rows -- #303's lesson, which #389 put both halves of on
        `overviewEntryForPilot`."""
        self.assertIn(
            "overviewEntryForPilot pilotName readingFromGameClient = "
            "overviewRowsForPilot pilotName readingFromGameClient |> List.head",
            collapsed(self.source))
        self.assertIn("overviewRowsForPilot calledTarget readingFromGameClient",
                      collapsed(self.source))
        # `lockCalledTarget` reaches the selection directly. `calledTargetIsLocked`
        # reaches it through `overviewRowSaysThisShipHasItLocked`, which #396
        # lifted out so the called-target arm and the friendly-fire guard read
        # `targetedByMe` through one accessor -- so the chain is asserted rather
        # than the old shape, which named a caller that no longer calls it.
        self.assertIn("overviewEntryForPilot",
                      declaration(self.source, "\nlockCalledTarget context calledTarget ="),
                      "#389's own pin, which this change must not break")
        self.assertIn("overviewRowSaysThisShipHasItLocked",
                      declaration(self.source, "\ncalledTargetIsLocked calledTarget reading ="),
                      "#389's own pin, one level deeper since #396")
        self.assertIn("overviewEntryForPilot",
                      declaration(self.source,
                                  "\noverviewRowSaysThisShipHasItLocked pilotName reading ="),
                      "the accessor #396 lifted out must still read the one row selection")


if __name__ == "__main__":
    unittest.main()
