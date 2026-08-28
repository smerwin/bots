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


def module_slot(name, x, y, running):
    """One `ShipSlot` holding one `ModuleButton`, at a chosen screen position.

    `running` is what the client's `ramp_active` entry says, and `None` means
    the entry is absent -- which is not the same as False and is the state a
    module that has never been switched on this session actually reads in. The
    `ShipModuleButtonRamps` widget holding `ramp_active` is created when the
    module starts cycling and destroyed when it stops, so `isActive` is
    `Nothing` for a cold module and `Just False` only for one that ran earlier.
    Both have to count as "off" or the bot activates nothing, which is saxrat's
    own recorded finding.

    The `ModuleButton`'s region is (0, 0, ...) because display regions are
    inherited: the button's `totalDisplayRegion.x` is the slot's, which is the
    coordinate `middleRowLeftToRight` sorts on.
    """
    entries = {"_name": "modulebutton"}
    if running is not None:
        entries["ramp_active"] = running
    return node("ShipSlot", {"_name": name}, [
        node("ModuleButton", entries, region=(0, 0, SLOT_SIZE, SLOT_SIZE)),
    ], region=(x, y, SLOT_SIZE, SLOT_SIZE))


def ship_ui(middle_slots, maneuver=None):
    """A `ShipUI` the real parser accepts, with a chosen middle row.

    `middle_slots` is a list of `(x, running)` **in the order they appear in the
    tree**, which is the point of the fixture: the tree order and the screen
    order are set independently so a case can tell the two apart.

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
        module_slot("middle%d" % index, x, MIDDLE_ROW_Y, running)
        for index, (x, running) in enumerate(middle_slots)]

    return node("ShipUI", {}, [
        node("CapacitorContainer", {}, region=CAPACITOR_REGION),
        gauge("structureGauge", 100, 0),
        gauge("armorGauge", 100, 1),
        gauge("shieldGauge", 100, 2),
        module_slot("weapon0", FIRST_SLOT_X, TOP_ROW_Y, None),
    ] + indication + slots, region=(0, 0, 600, 200))


ON = True
OFF = None

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

    # The propulsion module running with the ship not approaching anything.
    reading_binding("propulsionModuleLeftRunning",
                    [ship_ui([(120, ON), (180, ON)])]),

    # The same, while the ship is approaching -- nothing to do.
    reading_binding("propulsionModuleRunningOnTheApproach",
                    [ship_ui([(120, ON), (180, ON)], maneuver="Approach")]),

    # Approaching with the propulsion module cold.
    reading_binding("approachingWithTheModuleCold",
                    [ship_ui([(120, OFF), (180, ON)], maneuver="Approach")]),

    # Orbiting, which is a manoeuvre and is not an approach.
    reading_binding("orbitingWithTheModuleRunning",
                    [ship_ui([(120, ON), (180, ON)], maneuver="Orbit")]),

    # A ship UI whose middle row holds nothing at all.
    reading_binding("emptyMiddleRow", [ship_ui([])]),
]

STOOD_DOWN = "ARM STOOD DOWN"


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
        "armFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.andThen (manageMiddleRowModules (context p)))",
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
        "rootFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.shipUI |> Maybe.map (\\s ->"
        " wingmanDecisionRootInSpaceOrdinary (context p) s"
        ' |> unpack |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "NO SHIP UI"',
    ) + tuple(READINGS)

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-middle-row-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def step(inactive_always_on="False", propulsion_present="True",
         propulsion_running="False", approaching="False"):
    """The shipped middle-row rule, as one expression over four plain facts."""
    return ("middleRowStep { inactiveAlwaysOnModulePresent = %s"
            ", propulsionModulePresent = %s, propulsionModuleIsRunning = %s"
            ", shipIsApproaching = %s }"
            % (inactive_always_on, propulsion_present, propulsion_running,
               approaching))


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
        middleRow = body.index("case manageMiddleRowModules context shipUI of")
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


if __name__ == "__main__":
    unittest.main()
