"""Tests for the wingman switching its middle row on by position (#394).

Live on `fbf4c2e`, no wingman activated any module at all. Nothing in the bot
was defective: the settings block the pilots are actually launched with carries
no `activate-module-always` line, so `knownModulesToActivateAlways` is empty and
`activateAlwaysOnModules` correctly does nothing. The setting was also the wrong
instrument -- it matches tooltip text, needs the tooltips read first, and cannot
say "everything except the propulsion module" or "this one only while moving".

So `manageMiddleRowModules` ports `eve-online-saxrat`'s position-based shape:

    shipUIModulesToActivateAlways = middleRowLeftToRight >> List.drop 1
    propulsionModuleButton        = middleRowLeftToRight >> List.head

and the propulsion module runs only while the client names this ship's
manoeuvre `Approach`.

## What each case is holding down

**The x-sort, which is the load-bearing half of the port.**
`moduleButtonsRows.middle` arrives in UI-tree order and the parser drops any
node whose display region it cannot read, so a slot can leave and rejoin the
list without anything moving on screen -- "first by index" does not reliably
mean the same module twice. saxrat recorded the cost live: with both tank
modules already running it decided three times in a row to switch on the
propulsion module, the propulsion module never came on, and a *tank* module went
off instead, an odd number of toggles landing on a neighbour.
`SCRAMBLED_ROW` is a middle row whose tree order is not its screen order, and it
is what `test_the_row_is_read_left_to_right_and_not_in_tree_order`,
`test_the_propulsion_module_is_the_leftmost_slot_not_the_first_parsed` and
`test_an_unsorted_row_would_toggle_a_neighbour` are asked over. Dropping
`List.sortBy (.uiNode >> .totalDisplayRegion >> .x)` fails all three, and the
last of them is the live failure restated: the arm clicks the propulsion module
believing it to be a tank module.

**`List.drop 1`, which is what keeps the propulsion module out of the always-on
set.** `test_the_propulsion_module_is_not_one_of_the_always_on_modules` and
`test_a_cold_propulsion_module_is_not_switched_on_as_an_always_on_module`, the
second of them over a row already in screen order so that the sort is not part
of what it is measuring. Reducing the drop to `identity` makes an idle
propulsion module read as a tank module that is off, and the arm switches it on
with the ship sitting still -- which is the one thing the split exists to
prevent.

**The propulsion module follows the ship, not the bot's intention, and it
follows `Approach` specifically.** `test_the_propulsion_module_runs_the_moment_
the_ship_is_approaching`, `test_the_propulsion_module_stops_when_the_ship_stops_
approaching`, `test_a_still_ship_never_starts_the_propulsion_module` and
`test_orbiting_is_not_approaching`. The last one is the difference from saxrat,
which runs its module for `ManeuverOrbit` and `ManeuverRange` as well through
`shipIsUnderway`; the operator's rule for this bot is the approach and nothing
else, so widening the test back to saxrat's fails that case.

**The always-on set is ungated, which was a decision rather than an
inheritance.** saxrat gates its own on `anyAttackableInOverview`.
`test_the_row_is_held_on_with_nothing_to_fight` asks the arm over an overview
carrying rows and nothing attackable in them, so adding that gate fails it.

**#426: a click while cloaked is not one reading, it is up to twenty.**
Live on `wingman_run22.log`, an always-on module refused for cloaking on twenty
straight readings after a jump, with the next gate unasked for the whole
stretch. `TheCloakingMatcherTest` is the client's own refusal, read off the
notify channel; `TheCloakingHaltTest` is the arm declining both activation
branches once it is latched; `TheDecisionTreeFallsThroughTest` is the actual
claim -- that the *tree*, not only the arm, reaches past the middle row while
cloaked; and `TheLatchAfterReadingTest` is what clears the latch -- the ship
moving, which is what EVE's own mechanics say ends a post-jump cloak, rather
than a guessed duration this file has no measurement for.

The cases run the real `Bot.elm` through `elm repl`, and the readings come from
the real `EveOnline.ParseUserInterface`. Nothing here reads a live client, the
recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    label, node, reading_binding, wingman_root_body)
from test_wingman_engages_the_called_target import overview_window  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")

# `groupShipUIModulesIntoRows` splits the slots against the capacitor's vertical
# centre with a 20px threshold, so these three numbers are the whole of what
# makes a slot top-row or middle-row here. The capacitor spans y 40..60, centre
# 50; a slot 32 tall at y 0 has centre 16 and lands above, one at y 40 has
# centre 56 and lands in the middle.
SLOT_SIZE = 32
TOP_ROW_Y = 0
MIDDLE_ROW_Y = 40
CAPACITOR_REGION = (0, 40, 100, 20)

# Middle-row slots start right of the capacitor so no fixture node occludes
# another; the parser's occlusion bookkeeping is real and has nothing to do with
# what these cases are about.
FIRST_SLOT_X = 120
SLOT_PITCH = 60


def module_slot(name, x, y, running, deactivating=None):
    """One `ShipSlot` holding one `ModuleButton`, at a chosen screen position.

    `running` is what the client's `ramp_active` entry says, and `None` means
    the entry is absent -- which is not the same as False and is the state a
    module that has never been switched on this session actually reads in. The
    `ShipModuleButtonRamps` widget holding `ramp_active` is created when the
    module starts cycling and destroyed when it stops, so `isActive` is
    `Nothing` for a cold module and `Just False` only for one that ran earlier.
    Both have to count as "off" or the bot activates nothing, which is saxrat's
    own recorded finding.

    `deactivating` is the client's own `isDeactivating` entry, on the same
    footing: `None` leaves it out of the tree, which is what a build that does
    not carry it looks like and is the `Nothing` #408 turns on. It is a
    separate dictionary key read by a separate `Dict.get`, so a fixture sets
    the two independently -- which is the whole point, since the bug is a
    module that reads `ramp_active` on for ten seconds *after* the client has
    said the switch-off landed.

    The `ModuleButton`'s region is (0, 0, ...) because display regions are
    inherited: the button's `totalDisplayRegion.x` is the slot's, which is the
    coordinate `middleRowLeftToRight` sorts on.
    """
    entries = {"_name": "modulebutton"}
    if running is not None:
        entries["ramp_active"] = running
    if deactivating is not None:
        entries["isDeactivating"] = deactivating
    return node("ShipSlot", {"_name": name}, [
        node("ModuleButton", entries, region=(0, 0, SLOT_SIZE, SLOT_SIZE)),
    ], region=(x, y, SLOT_SIZE, SLOT_SIZE))


def ship_ui(middle_slots, maneuver=None):
    """A `ShipUI` the real parser accepts, with a chosen middle row.

    `middle_slots` is a list of `(x, running)` -- or `(x, running,
    deactivating)` -- **in the order they appear in the tree**, which is the
    point of the fixture: the tree order and the screen order are set
    independently so a case can tell the two apart.

    Hitpoints need all three gauges by name, or `parseShipUIFromUITreeRoot`
    answers `Nothing` for the whole ship UI.
    """
    def gauge(name, percent, line):
        return node("Gauge", {"_name": name, "_lastValue": percent / 100.0},
                    region=(400, line * 10, 100, 8))

    indication = []
    if maneuver is not None:
        indication.append(
            node("Container", {"_name": "indicationContainer"}, [
                label(maneuver, (400, 100, 100, 16)),
            ], region=(400, 100, 100, 16)))

    slots = [
        module_slot("middle%d" % index, slot[0], MIDDLE_ROW_Y, slot[1],
                    *slot[2:])
        for index, slot in enumerate(middle_slots)]

    return node("ShipUI", {}, [
        node("CapacitorContainer", {}, region=CAPACITOR_REGION),
        gauge("structureGauge", 100, 0),
        gauge("armorGauge", 100, 1),
        gauge("shieldGauge", 100, 2),
        module_slot("weapon0", FIRST_SLOT_X, TOP_ROW_Y, None),
    ] + indication + slots, region=(0, 0, 600, 200))


ON = True
OFF = None

# What the client's `isDeactivating` entry says about the leftmost slot.
# `SILENT` leaves the entry out of the tree entirely, and #408 is the whole
# reason the three are named apart: absent is not `False`, and only one of the
# three licences another click at a module button that is a toggle.
SETTLED = False
SHUTTING_DOWN = True
SILENT = None

# The middle row as the tree hands it over: **not** in screen order. Sorted by
# x it is the propulsion module at 120 with two tank modules at 180 and 240,
# which is what the setup instructions describe; read by tree index the first
# entry is the rightmost tank module instead.
SCRAMBLED_ROW = [(240, ON), (120, OFF), (180, ON)]
SORTED_XS = [120, 180, 240]

READINGS = [
    # The row above, with the ship sitting still: correctly read, there is
    # nothing to do at all.
    reading_binding("scrambled", [ship_ui(SCRAMBLED_ROW)]),

    # The same row while the client names the manoeuvre.
    reading_binding("scrambledApproaching",
                    [ship_ui(SCRAMBLED_ROW, maneuver="Approach")]),

    # The propulsion module cold and the tank module running, with the row
    # already in screen order so nothing about the sort is in play.
    reading_binding("coldPropulsionModuleInOrder",
                    [ship_ui([(120, OFF), (180, ON)])]),

    # A tank module that is off, on an overview with nothing attackable on it.
    reading_binding("coldTankModule", [
        ship_ui([(120, ON), (180, OFF)]),
        overview_window([("Greta Gneiss", "12 km", False)]),
    ]),

    # The propulsion module running with the ship not approaching anything,
    # and the client saying the module is not in the act of shutting down --
    # so this is the one shape in which a shutdown click is warranted.
    reading_binding("propulsionModuleLeftRunning",
                    [ship_ui([(120, ON, SETTLED), (180, ON)])]),

    # #408 itself: the same reading, except the client says the module is
    # already deactivating. `ramp_active` still reads on because the module is
    # running out a ten-second cycle, and the click that the debounce releases
    # four seconds in is what switches it back on.
    reading_binding("propulsionModuleDeactivating",
                    [ship_ui([(120, ON, SHUTTING_DOWN), (180, ON)])]),

    # The same again with the entry absent from the tree. Not the same fact as
    # `SETTLED`, and the parser's own doc block is what insists on that.
    reading_binding("propulsionModuleSilentAboutShuttingDown",
                    [ship_ui([(120, ON, SILENT), (180, ON)])]),

    # In warp with the module running: "not approaching" is true here too, and
    # `wingmanDecisionRootInSpaceOrdinary` has no warp gate above this arm.
    reading_binding("warpingWithTheModuleRunning",
                    [ship_ui([(120, ON, SETTLED), (180, ON)],
                             maneuver="Warp")]),

    # Lining up to warp. `ShipManeuverType` has no `Align`, so the client
    # naming it leaves `maneuverType` at `Nothing` -- the same reading as a
    # ship sitting still, which is why the arm cannot decline here.
    reading_binding("aligningWithTheModuleRunning",
                    [ship_ui([(120, ON, SETTLED), (180, ON)],
                             maneuver="Align")]),

    # The same, while the ship is approaching -- nothing to do.
    reading_binding("propulsionModuleRunningOnTheApproach",
                    [ship_ui([(120, ON), (180, ON)], maneuver="Approach")]),

    # Approaching with the propulsion module cold.
    reading_binding("approachingWithTheModuleCold",
                    [ship_ui([(120, OFF), (180, ON)], maneuver="Approach")]),

    # Orbiting, which is a manoeuvre and is not an approach.
    reading_binding("orbitingWithTheModuleRunning",
                    [ship_ui([(120, ON, SETTLED), (180, ON)],
                             maneuver="Orbit")]),

    # A ship UI whose middle row holds nothing at all.
    reading_binding("emptyMiddleRow", [ship_ui([])]),
]

STOOD_DOWN = "ARM STOOD DOWN"

# #426. Quoted verbatim from `wingman_run22.log`, where it appeared on twenty
# straight readings beside an always-on-module click that never landed.
CLOAK_INTERFERENCE = (
    "Interference from the cloaking you are doing is preventing your systems "
    "from functioning at this time.")


def game_log(entries):
    """The host's synthetic game-log node, `test_saxrat_ported_guards.py`'s
    own builder ported here -- see there for why the text sits under `text`
    and never `_setText`, and why the node carries no display region."""
    return node("MacOsHostSyntheticGameLog", {}, [
        node("MacOsHostSyntheticGameLogEntry",
             {"timestamp": "2026.08.29 20:15:02",
              "channel": channel, "text": text})
        for channel, text in entries])


CLOAK_READINGS = [
    # An inactive always-on module, with the client's own cloaking refusal on
    # the game log -- `wingman_run22.log`'s own shape.
    reading_binding("cloakedTankModuleOff", [
        ship_ui([(120, OFF), (180, ON)]),
        game_log([("notify", CLOAK_INTERFERENCE)]),
    ]),

    # The other branch cloak has to cover: approaching with the propulsion
    # module cold, which would otherwise fire `RunThePropulsionModule`.
    reading_binding("cloakedApproachingPropulsionCold", [
        ship_ui([(120, OFF), (180, ON)], maneuver="Approach"),
        game_log([("notify", CLOAK_INTERFERENCE)]),
    ]),

    # No refusal on this reading's own game log, ship sitting still -- what a
    # latch set on an earlier reading has to be told apart from movement by,
    # not by a fresh sighting that is not there.
    reading_binding("quietTankModuleOff", [ship_ui([(120, OFF), (180, ON)])]),

    # No refusal, ship approaching -- the movement #426 reads as "the cloak is
    # gone", whatever a latch carried into this reading said.
    reading_binding("quietApproaching", [
        ship_ui([(120, OFF), (180, ON)], maneuver="Approach"),
    ]),

    # No refusal, ship warping -- the other half of "moved".
    reading_binding("quietWarping", [
        ship_ui([(120, OFF), (180, ON)], maneuver="Warp"),
    ]),
]


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running the middle-row arm costs.

    Every field of the `BotDecisionContext` is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide an answer except the reading itself --
    `test_wingman_engages_the_called_target`'s arrangement, for its reason.
    Note in particular that `orbitFleetCommander` is left at its default `Yes`:
    every case below that expects the propulsion module to stay cold is being
    asked with keeping station switched on.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "context = \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # The counter the bound reads, wound to a chosen value. Everything
        # else in the context stays exactly what `context` builds, so a case
        # asking about the give-up differs from its own control in one number.
        "contextAsked = \\spent -> \\p -> (\\base -> { base | memory ="
        " { initBotMemory | middleRowAskedReadings = spent } }) (context p)",
        "armFor = \\parsed -> parsed |> Maybe.andThen (context >> manageMiddleRowModules)",
        "armAsked = \\spent -> \\parsed -> parsed"
        " |> Maybe.andThen (contextAsked spent >> manageMiddleRowModules)",
        "describeFor = \\parsed -> armFor parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "%s"' % STOOD_DOWN,
        "xsOf = List.map (.uiNode >> .totalDisplayRegion >> .x)",
        "rowXs = \\parsed -> parsed |> Maybe.andThen .shipUI"
        " |> Maybe.map (middleRowLeftToRight >> xsOf) |> Maybe.withDefault []",
        "alwaysOnXs = \\parsed -> parsed |> Maybe.andThen .shipUI"
        " |> Maybe.map (shipUIModulesToActivateAlways >> xsOf)"
        " |> Maybe.withDefault []",
        "propulsionX = \\parsed -> parsed |> Maybe.andThen .shipUI"
        " |> Maybe.andThen propulsionModuleButton"
        " |> Maybe.map (.uiNode >> .totalDisplayRegion >> .x)",
        "statusFor = \\parsed -> parsed"
        ' |> Maybe.map (context >> describeMiddleRowModules)'
        ' |> Maybe.withDefault "NO READING"',
        "askFor = \\parsed -> parsed"
        ' |> Maybe.map (context >> describeMiddleRowAsk)'
        ' |> Maybe.withDefault "NO READING"',
        "askAsked = \\spent -> \\parsed -> parsed"
        ' |> Maybe.map (contextAsked spent >> describeMiddleRowAsk)'
        ' |> Maybe.withDefault "NO READING"',
        "rootFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.map (\\s ->"
        " wingmanDecisionRootInSpaceOrdinary (context p) s"
        ' |> unpack |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "NO SHIP UI"',
        "rootAsked = \\spent -> \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.map (\\s ->"
        " wingmanDecisionRootInSpaceOrdinary (contextAsked spent p) s"
        ' |> unpack |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "NO SHIP UI"',
        # The real memory update over the real reading, so what a case asks
        # about the counter is what a run would have written -- not a
        # restatement of the rule beside it, which is #102's own defect.
        "askedAfter = \\spent -> \\parsed -> parsed |> Maybe.map (\\p ->"
        " (updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = p"
        " , screenshot ="
        " { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings }"
        " { initBotMemory | middleRowAskedReadings = spent })"
        ".middleRowAskedReadings) |> Maybe.withDefault (-1)",
        # #426. The context forced into believing cloaking is already
        # latched, `contextAsked`'s own arrangement for a chosen memory field
        # -- so the arm and the whole tree can be asked what they do while it
        # holds, independent of how the flag came to be set.
        "contextCloaked = \\parsed -> (\\base -> { base | memory ="
        " { initBotMemory | cloakingInterferesWithModules = True } })"
        " (context parsed)",
        "armCloaked = \\parsed -> parsed |> Maybe.andThen (contextCloaked >> manageMiddleRowModules)",
        "describeCloaked = \\parsed -> armCloaked parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "%s"' % STOOD_DOWN,
        "rootCloaked = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.map (\\s ->"
        " wingmanDecisionRootInSpaceOrdinary (contextCloaked p) s"
        ' |> unpack |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "NO SHIP UI"',
        # The real memory update again, this time over both of the fields
        # #426 touches at once -- so a case can ask whether a reading spends
        # the click budget while cloaked (it must not) in the same call that
        # asks whether the latch itself moved.
        "memoryAfterCloak = \\askedBefore -> \\cloakedBefore -> \\parsed ->"
        " parsed |> Maybe.map (\\p ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = p"
        " , screenshot ="
        " { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings }"
        " { initBotMemory | middleRowAskedReadings = askedBefore"
        " , cloakingInterferesWithModules = cloakedBefore })",
        "askedReadingsAfterCloak = \\askedBefore -> \\cloakedBefore -> \\parsed ->"
        " memoryAfterCloak askedBefore cloakedBefore parsed"
        " |> Maybe.map .middleRowAskedReadings |> Maybe.withDefault (-1)",
        "cloakedAfter = \\askedBefore -> \\cloakedBefore -> \\parsed ->"
        " memoryAfterCloak askedBefore cloakedBefore parsed"
        " |> Maybe.map .cloakingInterferesWithModules |> Maybe.withDefault False",
    ) + tuple(READINGS) + tuple(CLOAK_READINGS)

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-middle-row-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def step(inactive_always_on="False", propulsion_present="True",
         propulsion_running="False", deactivating="Just False",
         approaching="False", warping="False", cloaking="False", asked="0"):
    """The shipped middle-row rule, over seven plain facts and a counter.

    `deactivating` is written as the Elm value rather than as a flag, because
    the three values it can take are the point: `Just True`, `Just False` and
    `Nothing` are three different facts and a case that could only pass a
    `Bool` could not tell the last two apart.

    `cloaking` defaults to `False` so every existing case keeps asking the
    question it was written to ask -- #426's fact is orthogonal to the six
    already here, and `TheCloakingHaltTest` below is what asks about it on its
    own.
    """
    return ("middleRowStep { inactiveAlwaysOnModulePresent = %s"
            ", propulsionModulePresent = %s, propulsionModuleIsRunning = %s"
            ", propulsionModuleIsDeactivating = %s, shipIsApproaching = %s"
            ", shipIsWarpingOrJumping = %s, cloakingPreventsActivation = %s"
            ", askedReadings = %s }"
            % (inactive_always_on, propulsion_present, propulsion_running,
               deactivating, approaching, warping, cloaking, asked))


class TheMiddleRowRuleTest(unittest.TestCase):
    """The rule on its own, over facts rather than over a reading."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_tank_module_that_is_off_is_switched_on(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAnAlwaysOnModule"
                 % step(inactive_always_on="True")]),
            [True])

    def test_the_row_is_held_on_whether_or_not_the_ship_is_moving(self):
        """The ungated half, restated as the rule: nothing about the fight or
        the manoeuvre is an input to the always-on answer at all."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAnAlwaysOnModule"
                 % step(inactive_always_on="True", approaching="True"),
                 "%s == ActivateAnAlwaysOnModule"
                 % step(inactive_always_on="True", approaching="False",
                        propulsion_running="True")]),
            [True, True])

    def test_the_tank_modules_are_answered_before_the_propulsion_module(self):
        """saxrat's ordering: a tank module that is off is off in a fight, and
        the propulsion module can wait the one reading that costs."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAnAlwaysOnModule"
                 % step(inactive_always_on="True", approaching="True",
                        propulsion_running="False")]),
            [True])

    def test_the_propulsion_module_runs_the_moment_the_ship_is_approaching(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == RunThePropulsionModule" % step(approaching="True")]),
            [True])

    def test_a_running_propulsion_module_is_left_alone_on_the_approach(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == MiddleRowNeedsNothing"
                 % step(approaching="True", propulsion_running="True")]),
            [True])

    def test_the_propulsion_module_stops_when_the_ship_stops_approaching(self):
        """The direction that is a real state rather than a symmetry: the
        module is switched on out on the approach and has to come off again
        when the ship arrives, when the commander warps off, and when this ship
        lines up to follow."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ShutThePropulsionModuleDown"
                 % step(approaching="False", propulsion_running="True")]),
            [True])

    def test_a_still_ship_never_starts_the_propulsion_module(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == MiddleRowNeedsNothing"
                 % step(approaching="False", propulsion_running="False")]),
            [True])

    def test_no_slot_means_no_click_is_asked_for(self):
        """A middle row the parser read nothing from must answer "nothing"
        rather than fall through to a branch that assumes a button."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == MiddleRowNeedsNothing"
                 % step(propulsion_present="False", approaching="True"),
                 "%s == MiddleRowNeedsNothing"
                 % step(propulsion_present="False", propulsion_running="True")]),
            [True, True])


class TheDeactivationTransientTest(unittest.TestCase):
    """#408's mechanism, as the rule.

    The propulsion module has a ten-second cycle and goes on reading
    `ramp_active` on for the whole of it after being told to stop, while
    `clickModuleButtonButWaitIfClickedInPreviousStep` waits two steps --
    roughly four seconds. So the click landed, the debounce expired inside the
    cycle, `isActive` still said on, and the next click switched the module
    back on. Twenty-three of Greta's last twenty-three top-level decisions were
    that one line, with Heather and Kara word for word the same.

    `isActive` cannot answer "did my click take" during a cycle;
    `isDeactivating` is the entry that can, and this bot had never read it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_module_the_client_says_is_deactivating_is_not_clicked_again(self):
        """The click that costs a session. `propulsionModuleIsRunning` is still
        true -- that is the cycle, not the switch -- so a rule reading only
        `isActive` answers `ShutThePropulsionModuleDown` here and re-arms the
        module it just switched off."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == PropulsionModuleIsAlreadyShuttingDown"
                 % step(propulsion_running="True", deactivating="Just True"),
                 "%s /= ShutThePropulsionModuleDown"
                 % step(propulsion_running="True", deactivating="Just True")]),
            [True, True])

    def test_an_absent_entry_is_not_read_as_not_deactivating(self):
        """The `Maybe`, which is the half of this that is easiest to lose.

        `ParseUserInterface`'s own doc block is explicit that an entry which
        did not decode is absent rather than false, that absent and `False` are
        different facts, and that only one of them is safe to act on -- the
        neighbouring `ramp_active` is a duty cycle rather than an on/off state,
        and #34 is what reading it as a state cost. Collapse `Nothing` to
        `False` -- `Maybe.withDefault False` anywhere on this fact -- and this
        case answers `ShutThePropulsionModuleDown` again.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["%s == PropulsionModuleSaysNothingAboutShuttingDown"
                 % step(propulsion_running="True", deactivating="Nothing"),
                 "%s /= ShutThePropulsionModuleDown"
                 % step(propulsion_running="True", deactivating="Nothing")]),
            [True, True])

    def test_a_client_that_says_the_module_is_settled_still_gets_its_click(self):
        """The control the two cases above need: `Just False` is the client
        saying no switch-off is in flight, and that is the one answer which
        licences a click. A guard that refused on all three values would pass
        both cases above and never switch a propulsion module off again."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ShutThePropulsionModuleDown"
                 % step(propulsion_running="True", deactivating="Just False")]),
            [True])

    def test_the_guard_is_on_the_shutdown_and_not_on_the_switch_on(self):
        """Switching a module *on* has no deactivation transient to misread, so
        a cold propulsion module is clicked whatever this entry says. Widening
        the guard to both directions would leave a build that does not carry
        the entry unable to run its propulsion module at all."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == RunThePropulsionModule"
                 % step(approaching="True", deactivating="Nothing"),
                 "%s == RunThePropulsionModule"
                 % step(approaching="True", deactivating="Just True"),
                 "%s == ActivateAnAlwaysOnModule"
                 % step(inactive_always_on="True", deactivating="Nothing")]),
            [True, True, True])

    def test_a_ship_in_warp_is_not_fought(self):
        """"Not approaching" is true in warp too, and
        `wingmanDecisionRootInSpaceOrdinary` has no warp gate above this arm.
        A click there is both wasted -- a module toggled in warp changes
        nothing about a warp already under way -- and the exact click that
        re-arms a module still running its cycle out, so the ship would drop
        out of warp with the propulsion module lit."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == LeaveThePropulsionModuleToTheWarp"
                 % step(propulsion_running="True", warping="True"),
                 "%s == LeaveThePropulsionModuleToTheWarp"
                 % step(propulsion_running="True", warping="True",
                        deactivating="Just False")]),
            [True, True])

    def test_aligning_is_not_a_state_the_arm_can_decline_in(self):
        """Recorded rather than guarded, and asked of the real parser.

        `ShipManeuverType` has `Warp`, `Jump`, `Orbit` and `Approach` and no
        `Align`, so a client showing "Align" leaves `maneuverType` at `Nothing`
        -- the same reading as a ship floating still, which the arm must go on
        shutting the module down in. Aligning is also where shutting it down is
        worth the most, since an active propulsion module is what makes
        aligning slow, so the arm is left asking there and what stops it
        repeating is `isDeactivating` and then the bound.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(aligningWithTheModuleRunning |> Maybe.andThen .shipUI"
                 " |> Maybe.andThen .indication"
                 " |> Maybe.andThen .maneuverType) == Nothing",
                 "Maybe.map shipIsWarpingOrJumpingFromReading"
                 " aligningWithTheModuleRunning == Just False"]),
            [True, True])


class TheMiddleRowBoundTest(unittest.TestCase):
    """#408's urgent half: the arm sits directly under
    `activateAlwaysOnModules` and above the broadcast arm, the drones, the
    guns, the gate and the travel forms, so answering `Just` forever starves
    all of them. That is #321's shape and the third time it has hit this bot
    (#360, #395)."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_click_the_arm_makes_is_bounded(self):
        """All three, not just the shutdown: any of them repeating forever owns
        the bot, and the always-on half has the same shape."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheMiddleRow"
                 % step(propulsion_running="True",
                        asked="middleRowAskedReadingsBound"),
                 "%s == GaveUpOnTheMiddleRow"
                 % step(approaching="True",
                        asked="middleRowAskedReadingsBound"),
                 "%s == GaveUpOnTheMiddleRow"
                 % step(inactive_always_on="True",
                        asked="middleRowAskedReadingsBound")]),
            [True, True, True])

    def test_the_last_reading_of_the_budget_still_clicks(self):
        """The control on the comparison's direction and operands."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ShutThePropulsionModuleDown"
                 % step(propulsion_running="True",
                        asked="(middleRowAskedReadingsBound - 1)"),
                 "0 < middleRowAskedReadingsBound"]),
            [True, True])

    def test_the_bound_does_not_mask_the_answers_that_decline_to_click(self):
        """A give-up in the status line has to mean "this bot clicked a module
        button and the client never showed the change", so only the clicks may
        become one. It is also what keeps `MiddleRowNeedsNothing` reachable
        past the bound, which is what resets the counter."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == PropulsionModuleIsAlreadyShuttingDown"
                 % step(propulsion_running="True", deactivating="Just True",
                        asked="9999"),
                 "%s == LeaveThePropulsionModuleToTheWarp"
                 % step(propulsion_running="True", warping="True",
                        asked="9999"),
                 "%s == MiddleRowNeedsNothing"
                 % step(approaching="True", propulsion_running="True",
                        asked="9999")]),
            [True, True, True])

    def test_the_bound_is_the_allowance_every_other_ask_here_gets(self):
        self.assertEqual(
            self.repl.evaluate(
                ["middleRowAskedReadingsBound == weaponsAskedReadingsBound",
                 "middleRowAskedReadingsBound == 20"]),
            [True, True])


class TheRowIsReadByPositionTest(unittest.TestCase):
    """`middleRowLeftToRight` and the two readers of it, over real readings."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_row_is_read_left_to_right_and_not_in_tree_order(self):
        self.assertEqual(
            self.repl.evaluate(["rowXs scrambled == %s" % SORTED_XS]),
            [True])

    def test_the_propulsion_module_is_the_leftmost_slot_not_the_first_parsed(self):
        """The tree hands the rightmost tank module over first, so an unsorted
        read names it the propulsion module."""
        self.assertEqual(
            self.repl.evaluate(["propulsionX scrambled == Just 120"]),
            [True])

    def test_the_propulsion_module_is_not_one_of_the_always_on_modules(self):
        self.assertEqual(
            self.repl.evaluate(
                ["alwaysOnXs scrambled == [ 180, 240 ]",
                 "List.member 120 (alwaysOnXs scrambled) == False"]),
            [True, True])

    def test_an_empty_middle_row_has_no_propulsion_module(self):
        self.assertEqual(
            self.repl.evaluate(
                ["propulsionX emptyMiddleRow == Nothing",
                 "alwaysOnXs emptyMiddleRow == []"]),
            [True, True])


class TheArmOverARealReadingTest(unittest.TestCase):
    """What the arm answers when handed a reading the parser produced."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def described(self, reading):
        return self.repl.strings(["describeFor %s" % reading])[0]

    def test_an_unsorted_row_would_toggle_a_neighbour(self):
        """saxrat's live failure, as a case.

        In `scrambled` both tank modules are already running and the propulsion
        module is cold, with the ship sitting still -- so the correct answer is
        that there is nothing to do. Read in tree order instead, `List.drop 1`
        removes the *rightmost tank module* and leaves the propulsion module
        looking like a tank module that is off, and the arm clicks it. That is
        the odd number of toggles landing on a neighbour, and it is why the sort
        is ported rather than simplified away.
        """
        self.assertEqual(self.described("scrambled"), STOOD_DOWN)

    def test_a_cold_propulsion_module_is_not_switched_on_as_an_always_on_module(self):
        """The same property as the case above with the sort taken out of it:
        this row is already in screen order, so what is left is `List.drop 1`
        alone. Reduce it to `identity` and the cold propulsion module reads as a
        tank module that is off, and gets switched on with the ship sitting
        still -- which is the one thing splitting the row exists to prevent."""
        self.assertEqual(self.described("coldPropulsionModuleInOrder"),
                         STOOD_DOWN)

    def test_a_propulsion_module_left_running_is_shut_down(self):
        self.assertEqual(
            self.described("propulsionModuleLeftRunning"),
            "This ship is not approaching anything. Shut the propulsion module"
            " down. | Click on this module button.")

    def test_the_row_is_held_on_with_nothing_to_fight(self):
        """The gate decision, over a reading: the overview carries a row and
        nothing attackable in it, and the tank module is still switched on.
        Adding saxrat's `anyAttackableInOverview` gate fails this."""
        self.assertEqual(
            self.described("coldTankModule"),
            "A middle-row module right of the propulsion module is not"
            " running. Switch it on. | Click on this module button.")

    def test_the_propulsion_module_runs_once_the_client_names_the_manoeuvre(self):
        self.assertEqual(
            self.described("approachingWithTheModuleCold"),
            "This ship is approaching the fleet commander. Run the propulsion"
            " module. | Click on this module button.")

    def test_the_tank_modules_come_first_even_on_the_approach(self):
        """`scrambledApproaching` has the propulsion module cold *and* the ship
        approaching, so both halves want a click; the tank modules are already
        on, so what comes back is the propulsion module rather than a
        neighbour."""
        self.assertEqual(
            self.described("scrambledApproaching"),
            "This ship is approaching the fleet commander. Run the propulsion"
            " module. | Click on this module button.")

    def test_a_running_module_on_the_approach_asks_for_nothing(self):
        self.assertEqual(
            self.described("propulsionModuleRunningOnTheApproach"), STOOD_DOWN)

    def test_orbiting_is_not_approaching(self):
        """The one place this deliberately differs from saxrat, whose
        `shipIsUnderway` counts `ManeuverOrbit` and `ManeuverRange` too. The
        operator's rule for this bot is the approach and nothing else, so a
        ship in an orbit has its propulsion module shut down."""
        self.assertEqual(
            self.described("orbitingWithTheModuleRunning"),
            "This ship is not approaching anything. Shut the propulsion module"
            " down. | Click on this module button.")

    def test_a_module_running_its_cycle_out_is_left_alone(self):
        """#408 over a reading the real parser produced. The two readings
        differ in one dictionary entry, and the whole outage is in it."""
        self.assertEqual(self.described("propulsionModuleDeactivating"),
                         STOOD_DOWN)

    def test_a_client_saying_nothing_buys_no_click(self):
        self.assertEqual(
            self.described("propulsionModuleSilentAboutShuttingDown"),
            STOOD_DOWN)

    def test_a_ship_in_warp_keeps_its_readings(self):
        self.assertEqual(self.described("warpingWithTheModuleRunning"),
                         STOOD_DOWN)

    def test_a_ship_lining_up_still_sheds_the_module(self):
        """The align decision, over a reading: the client names the manoeuvre
        and the parser has no value for it, so this is a ship the arm cannot
        tell from one sitting still -- and it is where the module costs the
        most."""
        self.assertEqual(
            self.described("aligningWithTheModuleRunning"),
            "This ship is not approaching anything. Shut the propulsion module"
            " down. | Click on this module button.")


class TheArmIsOnTheLiveDecisionPathTest(unittest.TestCase):
    """#349's finding, which this file must not repeat: `activateAlwaysOnModules`
    was correct, was tested, and was never called by the wingman's own root --
    the tooltip check lived in `decideNextActionWhenInSpaceNotHiding`, which is
    the inherited combat-anomaly-bot root nothing on this bot's path reaches. An
    arm that answers correctly and is not asked is indistinguishable from the
    defect it was written to fix, which is exactly how #394 was reported.

    So these run the wingman's own `wingmanDecisionRootInSpaceOrdinary` rather
    than the arm, and what they hold down is that the reading reaches it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_root_switches_a_middle_row_module_on(self):
        self.assertEqual(
            self.repl.strings(["rootFor coldTankModule"]),
            ["A middle-row module right of the propulsion module is not"
             " running. Switch it on. | Click on this module button."])

    def test_the_root_runs_the_propulsion_module_on_the_approach(self):
        self.assertEqual(
            self.repl.strings(["rootFor approachingWithTheModuleCold"]),
            ["This ship is approaching the fleet commander. Run the propulsion"
             " module. | Click on this module button."])

    def test_a_row_that_needs_nothing_hands_the_reading_on(self):
        """The other half of being on the path: the step must not answer for
        the whole of a session it has nothing to do in, or every arm below it --
        the broadcast, the drones, the guns -- is starved."""
        self.assertEqual(self.repl.strings(["rootFor scrambled"]),
                         ["Nothing to do. Wait. | Wait for progress in game"])

    def test_the_give_up_hands_the_reading_back_to_the_arms_below(self):
        """#408's outage, as one case, and the one that fails if the bound is
        taken out.

        `propulsionModuleLeftRunning` is the live reading: the module reads on,
        the ship is not approaching, and the arm wants to click. With the
        counter wound past the bound the arm must answer `Nothing` and the
        root must reach something below it -- not park on
        `askForHelpToGetUnstuck` or on a wait, which would be #321's "a branch
        at the head of the tree with no bound owns the whole bot" with a
        politer status line. The control beside it is the same reading with a
        fresh counter, which still clicks.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["armAsked middleRowAskedReadingsBound"
                 " propulsionModuleLeftRunning == Nothing",
                 "armAsked 0 propulsionModuleLeftRunning /= Nothing"]),
            [True, True])
        self.assertEqual(
            self.repl.strings(
                ["rootAsked middleRowAskedReadingsBound"
                 " propulsionModuleLeftRunning"]),
            ["Nothing to do. Wait. | Wait for progress in game"])

    def test_the_root_still_shuts_a_module_down_inside_the_budget(self):
        self.assertEqual(
            self.repl.strings(["rootFor propulsionModuleLeftRunning"]),
            ["This ship is not approaching anything. Shut the propulsion"
             " module down. | Click on this module button."])

    def test_the_tooltip_path_is_still_consulted_ahead_of_it(self):
        """#394 adds a position-based path; it does not replace the setting.

        Source-pinned, and the only case here that is, because
        `activateAlwaysOnModules` cannot be told apart from outside without a
        `ShipModulesMemory` carrying a read tooltip: with none it answers
        `Nothing` for every reading, which is also what a deleted call answers.

        The slice is bounded to the two root declarations by
        `wingman_root_body`, and both needles stop at the scrutinee -- the
        retreat's own comment in the first half of that slice names
        `activateAlwaysOnModules` in prose, and a bare-name search would read
        that mention instead of the arm. `TheModuleActivationSplitTest` records
        the same hazard for the same reason.
        """
        with open(os.path.join(WINGMAN_DIR, "Bot.elm"), encoding="utf-8") as f:
            body = wingman_root_body(f.read())
        tooltips = body.index("case activateAlwaysOnModules context of")
        middleRow = body.index("case manageMiddleRowModules context of")
        self.assertLess(tooltips, middleRow)
        self.assertLess(middleRow,
                        body.index("case actOnFleetBroadcast context"))


class TheStatusLineTest(unittest.TestCase):
    """#394's evidence was read off a console, and an empty setting and an
    unfound row look identical from outside unless the row is printed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_row_is_printed_in_screen_order_with_the_prop_mod_named(self):
        self.assertEqual(
            self.repl.strings(["statusFor scrambled"]),
            ["Middle row: prop mod off and this ship is not approaching,"
             " keep-active [on, on]."])

    def test_the_manoeuvre_the_prop_mod_waits_on_is_printed(self):
        self.assertEqual(
            self.repl.strings(["statusFor approachingWithTheModuleCold"]),
            ["Middle row: prop mod off and this ship is approaching,"
             " keep-active [on]."])

    def test_a_row_the_bot_found_nothing_in_says_so(self):
        self.assertEqual(
            self.repl.strings(["statusFor emptyMiddleRow"]),
            ["Middle row: no module slots read, so nothing is kept active by"
             " position."])

    def test_the_give_up_is_visible(self):
        """`manageMiddleRowModules` answers `Nothing` when it gives up, so
        without this a bot that has stopped managing its middle row reads in
        the status line exactly like one whose row is already right -- which is
        the shape that made #408 hard to see from a console."""
        clause = self.repl.strings(
            ["askAsked middleRowAskedReadingsBound"
             " propulsionModuleLeftRunning"])[0]
        self.assertIn("GAVE UP", clause)
        self.assertIn(str(20), clause)

    def test_each_refusal_is_named_as_itself(self):
        """The two `isDeactivating` refusals are named apart on purpose: a
        console showing the second one for a whole session is a build that does
        not carry the entry, and that is worth being able to see."""
        clauses = self.repl.strings(
            ["askFor propulsionModuleDeactivating",
             "askFor propulsionModuleSilentAboutShuttingDown",
             "askFor warpingWithTheModuleRunning",
             "askFor propulsionModuleLeftRunning",
             "askFor scrambled"])
        self.assertIn("already deactivating", clauses[0])
        self.assertIn("says nothing", clauses[1])
        self.assertIn("warping or jumping", clauses[2])
        self.assertIn("Switching the propulsion module off", clauses[3])
        self.assertEqual(clauses[4], "")

    def test_the_two_clauses_share_a_line_without_a_stray_space(self):
        """`describeMiddleRowAsk` is empty on most readings and sits in the
        same status-line group as the row itself, so the group drops empties
        before joining rather than leaving a gap where a clause was not."""
        self.assertEqual(
            self.repl.evaluate(
                ["(scrambled |> Maybe.map (context >> statusTextFromState)"
                 ' |> Maybe.map (String.contains "keep-active [on, on]."))'
                 " == Just True",
                 "(scrambled |> Maybe.map (context >> statusTextFromState)"
                 ' |> Maybe.map (String.contains "keep-active [on, on]. "))'
                 " == Just False"]),
            [True, True])


class TheCounterAdvancesFromTheShippedRuleTest(unittest.TestCase):
    """#102: a counter advanced by one condition and read by another is two
    rules on two schedules, and #389 is what that costs in this file -- three
    pilots reporting `GAVE UP after 46 readings` on an arm that had never once
    been asked.

    So these run the real `updateMemoryForNewReadingFromGame` over the real
    readings rather than pinning its source, and what they hold down is that
    only the readings the arm actually clicked on are charged for.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_reading_the_arm_clicked_on_is_charged(self):
        self.assertEqual(
            self.repl.evaluate(
                ["askedAfter 4 propulsionModuleLeftRunning == 5",
                 "askedAfter 4 coldTankModule == 5",
                 "askedAfter 4 approachingWithTheModuleCold == 5"]),
            [True, True, True])

    def test_the_readings_the_arm_declined_on_are_not_charged(self):
        """Each of these leaves the module exactly as it found it, so charging
        for them would spend the budget on readings nobody clicked and report a
        give-up on an arm that had stopped asking of its own accord."""
        self.assertEqual(
            self.repl.evaluate(
                ["askedAfter 4 propulsionModuleDeactivating == 0",
                 "askedAfter 4 propulsionModuleSilentAboutShuttingDown == 0",
                 "askedAfter 4 warpingWithTheModuleRunning == 0",
                 "askedAfter 4 scrambled == 0"]),
            [True, True, True, True])

    def test_the_counter_holds_rather_than_running_away_past_the_bound(self):
        """`unlockFleetPilotAskedReadings`'s own arrangement: the row is still
        wrong and this bot has stopped clicking at it, and a counter that ran
        away would make the status line's "after N readings" meaningless."""
        self.assertEqual(
            self.repl.evaluate(
                ["askedAfter 9999 propulsionModuleLeftRunning == 9999"]),
            [True])

    def test_a_row_that_needs_nothing_gives_the_allowance_back(self):
        """What ends an episode here. A ship that starts approaching again
        wants the module it already has running, so the row needs nothing and
        the next stretch of not-approaching starts from a full budget -- which
        is what keeps a give-up from being permanent."""
        self.assertEqual(
            self.repl.evaluate(
                ["askedAfter 9999 propulsionModuleRunningOnTheApproach == 0"]),
            [True])


class TheCloakingMatcherTest(unittest.TestCase):
    """`cloakingInterferenceFromGameLog`, against real parsed game-log
    entries -- #426."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    def test_the_live_sentence_matches(self):
        self.assertEqual(
            self.repl.evaluate(
                ["cloakedTankModuleOff |> Maybe.map"
                 " cloakingInterferenceFromGameLog"]),
            [True])

    def test_a_quiet_game_log_does_not_match(self):
        self.assertEqual(
            self.repl.evaluate(
                ["quietTankModuleOff |> Maybe.map"
                 " cloakingInterferenceFromGameLog"]),
            [False])

    def test_the_channel_is_read_not_assumed(self):
        """The identical sentence on a channel other than `notify` is not
        this refusal -- `loadRefusalFromGameLog`'s own filter, ported."""
        answers = self.repl.evaluate(
            ["otherChannel |> Maybe.map cloakingInterferenceFromGameLog"],
            definitions=[reading_binding("otherChannel", [
                ship_ui([(120, OFF), (180, ON)]),
                game_log([("combat", CLOAK_INTERFERENCE)]),
            ])])
        self.assertEqual(answers, [False])

    def test_an_unrelated_notify_line_does_not_match(self):
        answers = self.repl.evaluate(
            ["unrelated |> Maybe.map cloakingInterferenceFromGameLog"],
            definitions=[reading_binding("unrelated", [
                ship_ui([(120, OFF), (180, ON)]),
                game_log([("notify", "Setting course to docking perimeter")]),
            ])])
        self.assertEqual(answers, [False])


class TheCloakingHaltTest(unittest.TestCase):
    """`middleRowStep`/`manageMiddleRowModules`, with cloaking already latched
    -- independent of how the game log got it there, `contextCloaked`'s own
    point."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    def test_cloaking_declines_the_always_on_module_click(self):
        """`coldTankModule` would otherwise switch a tank module on --
        `TheMiddleRowRuleTest`'s own control for this reading."""
        self.assertEqual(
            self.repl.strings(["describeCloaked coldTankModule"]),
            [STOOD_DOWN])

    def test_cloaking_declines_the_propulsion_module_too(self):
        """`approachingWithTheModuleCold` would otherwise switch the
        propulsion module on -- the other activation branch, not only the
        always-on one."""
        self.assertEqual(
            self.repl.strings(
                ["describeCloaked approachingWithTheModuleCold"]),
            [STOOD_DOWN])

    def test_the_rule_answers_its_own_named_case_not_merely_nothing(self):
        """`manageMiddleRowModules` answering `Nothing` is also what a
        genuinely empty row answers -- `middleRowStep` itself has to name the
        cloaked case distinctly, or a status line reading it could not tell
        the two apart."""
        self.assertEqual(
            self.repl.evaluate(
                [step(cloaking="True") + " == CloakingPreventsActivation"]),
            [True])


class TheDecisionTreeFallsThroughTest(unittest.TestCase):
    """`wingmanDecisionRootInSpaceOrdinary`, the whole tree rather than the
    arm alone -- #426's actual claim is that a jump gets asked for on the
    reading cloaking blocks the module, not merely that the arm goes quiet."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    def test_the_uncloaked_control_does_click_the_module(self):
        """The sanity check the next case is measured against: with cloaking
        not latched, this reading's own path does click a module button."""
        answers = self.repl.strings(["rootFor coldTankModule"])
        self.assertIn("Click on this module button.", answers[0])

    def test_cloaked_the_same_reading_never_reaches_the_module_click(self):
        answers = self.repl.strings(["rootCloaked coldTankModule"])
        self.assertNotIn("Click on this module button.", answers[0])
        self.assertNotIn("module button", answers[0])


class TheLatchAfterReadingTest(unittest.TestCase):
    """`cloakingInterferesWithModulesAfterReading`, exercised through the real
    `updateMemoryForNewReadingFromGame` rather than restated -- #102's own
    reason, applied to a fresh latch."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    def test_a_fresh_refusal_latches_it(self):
        answers = self.repl.evaluate(
            ["cloakedAfter 0 False cloakedTankModuleOff == True"])
        self.assertTrue(answers[0])

    def test_a_quiet_still_reading_holds_an_existing_latch(self):
        """No refusal on *this* reading and the ship has not moved: the latch
        set on an earlier reading has to survive, or every quiet reading in
        between the refusal and the next jump would re-arm the click."""
        answers = self.repl.evaluate(
            ["cloakedAfter 0 True quietTankModuleOff == True"])
        self.assertTrue(answers[0])

    def test_approaching_clears_a_latched_flag_with_no_fresh_refusal(self):
        """Cleared by the ship moving, not by a guessed duration --
        `cloakingInterferesWithModulesAfterReading`'s own point."""
        answers = self.repl.evaluate(
            ["cloakedAfter 0 True quietApproaching == False"])
        self.assertTrue(answers[0])

    def test_warping_clears_it_too(self):
        answers = self.repl.evaluate(
            ["cloakedAfter 0 True quietWarping == False"])
        self.assertTrue(answers[0])

    def test_a_quiet_reading_never_latches_it_from_false(self):
        answers = self.repl.evaluate(
            ["cloakedAfter 0 False quietTankModuleOff == False"])
        self.assertTrue(answers[0])

    def test_the_click_budget_is_not_spent_while_cloaked(self):
        """`middleRowAskedReadings` resets to 0 on `CloakingPreventsActivation`
        the same way it does on every other decline -- `askedReadingsAfterCloak`
        is `askedAfter`'s own arrangement, over both fields #426 touches."""
        answers = self.repl.evaluate(
            ["askedReadingsAfterCloak 5 True cloakedTankModuleOff == 0"])
        self.assertTrue(answers[0])


if __name__ == "__main__":
    unittest.main()
