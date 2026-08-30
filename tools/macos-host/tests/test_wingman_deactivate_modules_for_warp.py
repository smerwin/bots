"""Tests for the wingman switching a module off for a warp (#410).

`deactivateModulesForWarp` clicked every module the `deactivate-module-on-warp`
setting names whose `isActive` read `Just True`. That entry is the client's
`ramp_active`, which is a **duty cycle** rather than an on/off state: #408
established one level up that the propulsion module goes on reading it for the
whole ten seconds it takes to run its cycle out after being told to stop, while
`clickModuleButtonButWaitIfClickedInPreviousStep` waits two steps -- roughly
four seconds. A module button is a toggle, so the second click re-armed what the
first switched off, and the arm could repeat for as long as the reading held.

The fix is #408's, and its shape is the whole of this file's subject:
`ShipUIModuleButton.stateFromDictEntries.isDeactivating` is the entry that
answers *did my click take*, and `Just True` **and** `Nothing` both buy no
click. `ParseUserInterface`'s own doc block is what insists on the second half
-- an entry that did not decode is absent rather than false, absent and `False`
are different facts, and only one of them is safe to act on. Collapsing them
licences exactly the click that re-arms the module, which is why
`test_absent_is_not_a_licence_to_click` is the case this file cares about most.

## The bound, and why this arm needed one where #408's argument alone would not

This is **live code on the retreat path**. `warpAwayFromDanger` takes this arm's
answer *before* commanding the warp, so an arm that answers `Just` forever is a
damaged ship that never leaves -- worse than #408's loop, which merely stopped
four ships following their commander. It has not fired only because
`deactivate-module-on-warp` ships as `[]` and no pilot profile sets it, so the
first operator to set that setting arms the bug, on the retreat.

`isDeactivating` alone does not bound it: a click the client never acknowledges
leaves the module reading active and settled on every reading, and the arm
clicks again. So `deactivateForWarpAskedReadingsBound` bounds the click and the
give-up **declines and hands the caller's own step back** -- the shape this repo
uses for a give-up that bounds effort, against the root-placed shape it uses for
one that ends the session. `TheBoundTest` and `TheGiveUpHandsTheReadingBackTest`
are those two halves.

**And the reset is deliberately tighter than #408's**, which is the one place
this diverges from the change it ports. `middleRowAskedReadings` resets on every
answer that declined to click; here only `NoModuleToDeactivateForWarp` resets.
A module whose deactivation is cancelled mid-cycle reads `Just True` on one
reading and `Just False` on the next with `isActive` never falling, so the arm
clicks, declines, clicks -- and a counter that resets on the decline never
reaches its bound. `test_a_click_decline_alternation_still_reaches_the_bound` is
that case, and it fails against #408's reset rule.

## Confirmed by mutation

Each fails the named case, and each was applied to the shipped `Bot.elm` and the
whole file re-run:

1. `Nothing` treated as licence to click (`/= Just True` at
   `moduleToDeactivateForWarp`) -- the asymmetry this change exists for; fails
   `test_absent_is_not_a_licence_to_click`,
   `test_a_reading_the_client_says_nothing_about_is_not_clicked`,
   `test_the_arm_declines_where_the_client_says_nothing` and
   `test_the_clause_names_the_two_isDeactivating_answers_apart`;
2. the read pointed back at `.isActive` (`moduleButton.isActive == Just True`),
   which is the shipped defect restored -- fails the same set, since on this
   client's readings `isActive` is `Just True` on all three;
3. the comparison inverted (`== Just True` at `moduleToDeactivateForWarp`) --
   fails `test_a_settled_module_is_the_one_clicked` and
   `test_a_module_already_deactivating_is_left_to_finish`;
4. the bound moved by one in either direction -- fails
   `test_the_bound_is_the_last_reading_that_clicks` /
   `test_one_reading_past_the_bound_still_declines`;
5. the bound removed (`deactivateForWarpStep` never answering
   `GaveUpOnDeactivatingForWarp`) -- fails four cases in `TheBoundTest` and
   `test_a_session_that_never_lands_a_click_reaches_the_bound_and_holds`;
6. the reset widened to #408's rule (every non-clicking answer resetting) --
   fails `test_a_click_decline_alternation_still_reaches_the_bound`;
7. `activateAlwaysOnModules` repointed at `moduleToDeactivateForWarp`, which is
   one of the four callers #410 puts out of scope -- fails
   `test_the_new_rule_is_read_only_where_this_change_put_it` and
   `test_the_activation_arms_still_choose_their_own_modules`;
8. `fireOnActiveTarget` repointed the same way -- fails the first of those and
   `test_the_gun_arms_still_choose_their_own_modules`;
9. the give-up made to answer `askForHelpToGetUnstuck` rather than `Nothing` --
   fails `test_the_give_up_hands_the_reading_back`;
10. the status clause dropped from the status line -- fails
    `test_the_clause_is_in_the_status_line`;
11. the memory update handed `botMemoryBefore.shipModules` rather than the
    integrated value -- fails
    `test_the_counter_and_the_arm_are_asked_with_one_tooltip_memory`.

The cases run the real `Bot.elm` through `elm repl`, and the readings come from
the real `EveOnline.ParseUserInterface`. Nothing here reads a live client, the
recorded corpus, or a running bot -- there is none: no recorded wingman run sets
`deactivate-module-on-warp`, so nothing in this file is a measurement.

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
    collapsed, reading_binding)
from test_wingman_activates_the_middle_row import (  # noqa: E402
    OFF, ON, SETTLED, SHUTTING_DOWN, SILENT, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The tooltip text the setting is matched against, and the setting itself.
# `runningModulesNamedForWarp` matches with `stringContainsIgnoringCase`, so the
# setting names a fragment of what the client's tooltip says -- which is how an
# operator writes one.
PROPULSION_TOOLTIP = "500MN Microwarpdrive II"
OTHER_TOOLTIP = "Medium Shield Booster II"
SETTING = "Microwarpdrive"

# Where the middle row's slots sit. Only the x matters to anything here: it is
# what `middleRowLeftToRight` sorts on, and this file does not care about that
# order at all -- every fact it asks about is keyed by the module button's own
# address.
PROPULSION_X = 120
OTHER_X = 180


def with_module_addresses(tree):
    """Stamp every `ModuleButton` in `tree` with a fixed address, in tree order.

    The shared `node` draws from a process-global counter, so the address a
    fixture's module button gets depends on how many nodes every other test
    module built first. That is fine everywhere else and useless here:
    `getModuleButtonTooltipFromModuleButton` keys `ShipModulesMemory` on
    `pythonObjectAddress`, so a case that seeds a tooltip has to know the
    address it is seeding it against.

    Returns the addresses, in the order the buttons appear.
    """
    addresses = []

    def walk(current):
        if current["pythonObjectTypeName"] == "ModuleButton":
            address = "9%05d" % len(addresses)
            current["pythonObjectAddress"] = address
            addresses.append(address)
        for child in current["children"]:
            walk(child)

    walk(tree)
    return addresses


def stamped_ship_ui(middle_slots, maneuver=None):
    """A `ShipUI` the real parser accepts, with known module-button addresses.

    `ship_ui` puts one top-row weapon slot in before the middle row, so the
    addresses come back as `[ weapon, first middle slot, ... ]`. The weapon's
    `ramp_active` is absent, which is what a module that has not cycled this
    session reads -- so it is never a candidate here whatever a tooltip says
    about it, and that is deliberate: it is a second module button in the tree
    that this arm must leave alone.
    """
    tree = ship_ui(middle_slots, maneuver=maneuver)
    return tree, with_module_addresses(tree)


# The addresses are the same for every fixture below, because every fixture
# builds the same shape of ship: one weapon, then the middle-row slots in the
# order given. Taken from one build rather than written down, so a change to
# `ship_ui`'s own shape moves them here rather than making the seeds miss.
_, ADDRESSES = stamped_ship_ui([(PROPULSION_X, ON, SETTLED)])
WEAPON_ADDRESS, PROPULSION_ADDRESS = ADDRESSES[0], ADDRESSES[1]

_, TWO_MODULE_ADDRESSES = stamped_ship_ui(
    [(PROPULSION_X, ON, SETTLED), (OTHER_X, ON, SETTLED)])
SECOND_ADDRESS = TWO_MODULE_ADDRESSES[2]


def named_reading(name, middle_slots, maneuver=None):
    tree, _ = stamped_ship_ui(middle_slots, maneuver=maneuver)
    return reading_binding(name, [tree])


READINGS = [
    # The one shape in which a click is warranted: the module the setting names
    # reads active, and the client says it is not in the act of shutting down.
    named_reading("settled", [(PROPULSION_X, ON, SETTLED)]),

    # #410 itself. `ramp_active` still reads on because the module is running
    # out a ten-second cycle, and the click the debounce releases four seconds
    # in is what switches it back on.
    named_reading("deactivating", [(PROPULSION_X, ON, SHUTTING_DOWN)]),

    # The same again with the entry absent from the tree -- a build that does
    # not carry it. Not the same fact as `SETTLED`, and the parser's own doc
    # block is what insists on that.
    named_reading("silent", [(PROPULSION_X, ON, SILENT)]),

    # The module the setting names is not running, so there is nothing to
    # switch off however the entry reads.
    named_reading("moduleOff", [(PROPULSION_X, OFF, SETTLED)]),

    # Two named modules, the first already deactivating and the second settled.
    named_reading("oneDeactivatingOneSettled",
                  [(PROPULSION_X, ON, SHUTTING_DOWN), (OTHER_X, ON, SETTLED)]),

    # Two running modules where only the first is named by the setting.
    named_reading("namedAndUnnamed",
                  [(PROPULSION_X, ON, SETTLED), (OTHER_X, ON, SETTLED)]),

    # No ship UI at all.
    reading_binding("noShip", []),
]


def elm_strings(values):
    return "[ %s ]" % ", ".join('"%s"' % value for value in values)


def modules_memory(pairs):
    """An Elm `ShipModulesMemory` naming each address with a tooltip text."""
    return "(modulesMemory [ %s ])" % ", ".join(
        '( "%s", tooltipFor "%s" )' % (address, text)
        for address, text in pairs)


# The tooltip memory the ordinary cases run against: the propulsion module named
# by the setting, and nothing else named at all.
NAMES_THE_PROPULSION_MODULE = modules_memory(
    [(PROPULSION_ADDRESS, PROPULSION_TOOLTIP)])

# Both middle-row slots have a tooltip, and only the first matches the setting.
NAMES_ONE_OF_TWO = modules_memory([
    (PROPULSION_ADDRESS, PROPULSION_TOOLTIP),
    (SECOND_ADDRESS, OTHER_TOOLTIP),
])

# Both named, which is what `oneDeactivatingOneSettled` is asked with.
NAMES_BOTH = modules_memory([
    (PROPULSION_ADDRESS, PROPULSION_TOOLTIP),
    (SECOND_ADDRESS, PROPULSION_TOOLTIP),
])

# The weapon carries the setting's own tooltip, and its `ramp_active` is absent
# -- so a rule reading the tooltip without the active filter would pick it.
NAMES_THE_WEAPON = modules_memory([(WEAPON_ADDRESS, PROPULSION_TOOLTIP)])


class WarpDeactivationRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what asking this arm costs.

    Every field of the `BotDecisionContext` is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide an answer except the reading, the
    tooltip memory and the counter a case names.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Dict",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "aRegion = { x = 0, y = 0, width = 0, height = 0 }",
        "tooltipFor = \\text ->"
        " { uiNodeDisplayRegion = aRegion, shortcut = Nothing"
        " , optimalRange = Nothing"
        " , allContainedDisplayTextsWithRegion = [ ( text, aRegion ) ] }",
        "modulesMemory = \\pairs ->"
        " { tooltipFromModuleButton = Dict.fromList pairs"
        " , previousReadingTooltip = Nothing }",
        "settingsWith = \\names ->"
        " { defaultBotSettings | deactivateModuleOnWarp = names }",
        "aScreenshot ="
        " { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }",
        "memoryWith = \\shipModules -> \\asked ->"
        " { initBotMemory | shipModules = shipModules"
        " , deactivateForWarpAskedReadings = asked }",
        "contextFor = \\shipModules -> \\names -> \\asked -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0, botSettings = settingsWith names"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = aScreenshot"
        " , memory = memoryWith shipModules asked"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack ="
        " Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # The rule asked of a reading, which is what the arm, the status line
        # and the memory update all ask -- so a case here is asking the shipped
        # decision rather than a restatement of it.
        "stepFor = \\shipModules -> \\names -> \\asked -> \\parsed ->"
        " parsed |> Maybe.map"
        " (deactivateForWarpStepFromReading shipModules names asked)",
        "moduleFor = \\shipModules -> \\names -> \\parsed ->"
        " parsed |> Maybe.andThen"
        " (moduleToDeactivateForWarp shipModules names)"
        " |> Maybe.map Tuple.first",
        "armFor = \\shipModules -> \\names -> \\asked -> \\parsed ->"
        " parsed |> Maybe.andThen"
        " (contextFor shipModules names asked >> deactivateModulesForWarp)",
        "describeArm = \\shipModules -> \\names -> \\asked -> \\parsed ->"
        " armFor shipModules names asked parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "ARM STOOD DOWN"',
        "clauseFor = \\shipModules -> \\names -> \\asked -> \\parsed ->"
        " parsed"
        " |> Maybe.map"
        " (contextFor shipModules names asked >> describeDeactivateForWarp)"
        ' |> Maybe.withDefault "NO READING"',
        # The real memory update over real readings, so what a case asks about
        # the counter is what a run would have written -- not a restatement of
        # the rule beside it, which is #102's own defect.
        "updateOver = \\names -> \\parsed -> \\memory ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = parsed"
        " , screenshot = aScreenshot, botSettings = settingsWith names }"
        " memory",
        "foldReadings = \\shipModules -> \\names -> \\asked -> \\readings ->"
        " List.foldl (updateOver names)"
        " (memoryWith shipModules asked)"
        " (List.filterMap identity readings)"
        " |> .deactivateForWarpAskedReadings",
        "readingsArrived = \\readings ->"
        " List.length (List.filterMap identity readings)",
    ) + tuple(READINGS)

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-warp-deactivation-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def step(present="True", deactivating="False", silent="False", asked="0"):
    """The shipped rule, over three plain facts and a counter.

    `present` is `moduleToDeactivatePresent` -- a named module that reads active
    and that the client says is *not* deactivating. The other two are what is
    left when there is no such module, and they are separate facts rather than
    one because the parser's doc block says they are.
    """
    return ("deactivateForWarpStep { moduleToDeactivatePresent = %s"
            ", namedModuleIsAlreadyDeactivating = %s"
            ", namedModuleSaysNothingAboutDeactivating = %s"
            ", askedReadings = %s }"
            % (present, deactivating, silent, asked))


class ReplTest(unittest.TestCase):
    """A repl per class, shared through the process's one built app."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WarpDeactivationRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()


class TheRuleTest(ReplTest):
    """The rule on its own, over facts rather than over a reading."""

    def test_a_module_to_switch_off_is_switched_off(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == DeactivateAModuleForWarp" % step(present="True")]),
            [True])

    def test_a_module_already_deactivating_is_left_to_finish(self):
        """The whole of #408's mechanism, as this arm's own rule: a module the
        client says is shutting down is left alone however long `isActive`
        stays true, because clicking it again is what switches it back on."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == NamedModuleIsAlreadyDeactivating"
                % step(present="False", deactivating="True"),
                "%s /= DeactivateAModuleForWarp"
                % step(present="False", deactivating="True"),
            ]),
            [True, True])

    def test_absent_is_not_a_licence_to_click(self):
        """`Nothing` is its own answer, and this is the case #410 exists for.

        A rule that collapsed absent into "not deactivating" would answer
        `DeactivateAModuleForWarp` here, which is the click that re-arms a
        module the last click may already have stopped."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == NamedModuleSaysNothingAboutDeactivating"
                % step(present="False", silent="True"),
                "%s /= DeactivateAModuleForWarp"
                % step(present="False", silent="True"),
            ]),
            [True, True])

    def test_the_two_isDeactivating_answers_are_not_one_answer(self):
        """"The client says it is deactivating" and "the client says nothing"
        are different facts, and only the first is evidence a click landed."""
        self.assertEqual(
            self.repl.evaluate([
                "%s /= %s" % (step(present="False", deactivating="True"),
                              step(present="False", silent="True")),
            ]),
            [True])

    def test_nothing_named_and_running_needs_nothing(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoModuleToDeactivateForWarp" % step(present="False")]),
            [True])

    def test_a_clickable_module_outranks_one_already_deactivating(self):
        """One module running its cycle out never holds up a second the setting
        also names and that the client says is settled."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == DeactivateAModuleForWarp"
                % step(present="True", deactivating="True"),
                "%s == DeactivateAModuleForWarp"
                % step(present="True", silent="True"),
            ]),
            [True, True])


class TheBoundTest(ReplTest):
    """`deactivateForWarpAskedReadingsBound`, at its edges and beyond them."""

    def test_the_bound_is_the_last_reading_that_clicks(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == DeactivateAModuleForWarp"
                % step(present="True",
                       asked="(deactivateForWarpAskedReadingsBound - 1)"),
                "%s == GaveUpOnDeactivatingForWarp"
                % step(present="True",
                       asked="deactivateForWarpAskedReadingsBound"),
            ]),
            [True, True])

    def test_one_reading_past_the_bound_still_declines(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == GaveUpOnDeactivatingForWarp"
                % step(present="True",
                       asked="(deactivateForWarpAskedReadingsBound + 1)"),
                "%s == GaveUpOnDeactivatingForWarp"
                % step(present="True",
                       asked="(deactivateForWarpAskedReadingsBound * 50)"),
            ]),
            [True, True])

    def test_the_bound_is_above_a_handful_of_readings(self):
        """A boundary pair passes for *any* constant, including one that admits
        nothing -- so the constant is asserted against a fixed value too. Four
        readings is roughly two clicks after the debounce, which is the least
        this arm could be allowed and still be an ask rather than a single
        attempt."""
        self.assertEqual(
            self.repl.evaluate([
                "4 < deactivateForWarpAskedReadingsBound",
                "%s == DeactivateAModuleForWarp" % step(present="True",
                                                        asked="4"),
                "%s == DeactivateAModuleForWarp" % step(present="True",
                                                        asked="0"),
            ]),
            [True, True, True])

    def test_it_is_written_as_the_file_s_own_allowance(self):
        """Written as `weaponsAskedReadingsBound` rather than as a number, so
        the argument for the size cannot drift away from the number."""
        self.assertEqual(
            self.repl.evaluate([
                "deactivateForWarpAskedReadingsBound"
                " == weaponsAskedReadingsBound",
            ]),
            [True])
        body = declaration(WINGMAN_BOT_ELM, "deactivateForWarpAskedReadingsBound")
        self.assertIn("weaponsAskedReadingsBound", body)
        self.assertNotRegex(body, r"=\s*\d+")

    def test_only_the_click_can_give_up(self):
        """The answers that decline to click are reported as themselves however
        much budget has been spent, so a give-up in the status line always means
        "this bot clicked and the client never showed the change"."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == NamedModuleIsAlreadyDeactivating"
                % step(present="False", deactivating="True",
                       asked="(deactivateForWarpAskedReadingsBound * 10)"),
                "%s == NamedModuleSaysNothingAboutDeactivating"
                % step(present="False", silent="True",
                       asked="(deactivateForWarpAskedReadingsBound * 10)"),
                "%s == NoModuleToDeactivateForWarp"
                % step(present="False",
                       asked="(deactivateForWarpAskedReadingsBound * 10)"),
            ]),
            [True, True, True])


class TheRuleOverRealReadingsTest(ReplTest):
    """The same rule, asked about trees the real parser produced."""

    def test_the_fixtures_arrived(self):
        """A reading that failed to decode answers `Nothing` for everything,
        which reads exactly like a rule that declined -- so this is asked first
        and every case below rests on it."""
        self.assertEqual(
            self.repl.evaluate([
                "readingsArrived [ settled, deactivating, silent, moduleOff"
                ", oneDeactivatingOneSettled, namedAndUnnamed ] == 6",
                "noShip /= Nothing",
                "(settled |> Maybe.andThen .shipUI"
                " |> Maybe.map (.moduleButtons >> List.length)) == Just 2",
            ]),
            [True, True, True])

    def test_a_settled_module_is_the_one_clicked(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 settled == Just DeactivateAModuleForWarp"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                'moduleFor %s %s settled == Just "%s"'
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]),
                   PROPULSION_TOOLTIP),
            ]),
            [True, True])

    def test_a_reading_the_client_says_is_deactivating_is_not_clicked(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 deactivating"
                " == Just NamedModuleIsAlreadyDeactivating"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "moduleFor %s %s deactivating == Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True, True])

    def test_a_reading_the_client_says_nothing_about_is_not_clicked(self):
        """The same tree with the entry left out, which is what a build that
        does not carry it looks like. `ramp_active` reads on in all three of
        these readings, so a rule on `isActive` cannot tell them apart."""
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 silent"
                " == Just NamedModuleSaysNothingAboutDeactivating"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "moduleFor %s %s silent == Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "(silent |> Maybe.andThen .shipUI"
                " |> Maybe.map (.moduleButtons >> List.filterMap .isActive))"
                " == Just [ True ]",
            ]),
            [True, True, True])

    def test_a_module_that_is_not_running_is_nothing_to_do(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 moduleOff == Just NoModuleToDeactivateForWarp"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True])

    def test_a_module_the_setting_does_not_name_is_left_alone(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 namedAndUnnamed"
                " == Just NoModuleToDeactivateForWarp"
                % (NAMES_ONE_OF_TWO, elm_strings(["Nothing At All"])),
                'moduleFor %s %s namedAndUnnamed == Just "%s"'
                % (NAMES_ONE_OF_TWO, elm_strings([SETTING]),
                   PROPULSION_TOOLTIP),
            ]),
            [True, True])

    def test_a_module_with_no_tooltip_read_is_never_named(self):
        """The setting is matched against the tooltip, so a module whose
        tooltip this session never read cannot be picked however the setting
        reads -- which is the state every recorded wingman run is in."""
        self.assertEqual(
            self.repl.evaluate([
                "stepFor (modulesMemory []) %s 0 settled"
                " == Just NoModuleToDeactivateForWarp" % elm_strings([SETTING]),
            ]),
            [True])

    def test_a_module_that_has_never_cycled_is_not_a_candidate(self):
        """The weapon slot carries no `ramp_active` at all, which is what a
        module that has not run this session reads. Naming it in the tooltip
        memory must not make it a candidate."""
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 settled == Just NoModuleToDeactivateForWarp"
                % (NAMES_THE_WEAPON, elm_strings([SETTING])),
            ]),
            [True])

    def test_one_module_deactivating_does_not_hold_up_another(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 oneDeactivatingOneSettled"
                " == Just DeactivateAModuleForWarp"
                % (NAMES_BOTH, elm_strings([SETTING])),
            ]),
            [True])

    def test_a_reading_with_no_ship_ui_needs_nothing(self):
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s %s 0 noShip == Just NoModuleToDeactivateForWarp"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True])

    def test_an_empty_setting_names_nothing(self):
        """`deactivate-module-on-warp` ships as `[]`, which is why #410 is
        latent rather than active: with nothing named this arm is inert."""
        self.assertEqual(
            self.repl.evaluate([
                "stepFor %s [] 0 settled == Just NoModuleToDeactivateForWarp"
                % NAMES_THE_PROPULSION_MODULE,
                "defaultBotSettings.deactivateModuleOnWarp == []",
            ]),
            [True, True])


class TheArmTest(ReplTest):
    """`deactivateModulesForWarp` itself, over the same readings."""

    def test_the_arm_clicks_the_settled_module(self):
        """Both stages, so the second one pins that the click still goes
        through `clickModuleButtonButWaitIfClickedInPreviousStep` -- the
        debounce whose expiry inside a module's cycle is the whole of #410."""
        self.assertEqual(
            self.repl.strings([
                "describeArm %s %s 0 settled"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            ["Click module to deactivate '%s' to speed up warp."
             " | Click on this module button." % PROPULSION_TOOLTIP])

    def test_the_decision_line_still_opens_with_what_operators_grep(self):
        """The wording is the one this arm has always printed, so an existing
        grep still finds it."""
        line = self.repl.strings([
            "describeArm %s %s 0 settled"
            % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
        ])[0]
        self.assertTrue(line.startswith("Click module to deactivate "), line)

    def test_the_arm_declines_where_the_client_says_it_is_deactivating(self):
        self.assertEqual(
            self.repl.evaluate([
                "armFor %s %s 0 deactivating == Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True])

    def test_the_arm_declines_where_the_client_says_nothing(self):
        self.assertEqual(
            self.repl.evaluate([
                "armFor %s %s 0 silent == Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True])

    def test_the_arm_declines_with_nothing_named(self):
        self.assertEqual(
            self.repl.evaluate([
                "armFor %s [] 0 settled == Nothing"
                % NAMES_THE_PROPULSION_MODULE,
            ]),
            [True])


class TheGiveUpHandsTheReadingBackTest(ReplTest):
    """Past the bound the arm answers `Nothing`, so the caller's own step runs.

    That is what makes this a give-up that bounds *effort* rather than one that
    ends the session: `warpAwayFromDanger` takes this arm's answer before
    commanding the warp, so an arm that parked on `askForHelpToGetUnstuck`
    instead would be a damaged ship that never leaves.
    """

    def test_the_give_up_hands_the_reading_back(self):
        self.assertEqual(
            self.repl.evaluate([
                "armFor %s %s deactivateForWarpAskedReadingsBound settled"
                " == Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "armFor %s %s (deactivateForWarpAskedReadingsBound - 1) settled"
                " /= Nothing"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True, True])

    def test_the_retreat_takes_this_arm_before_it_warps(self):
        """Read out of the source, because it is the placement rather than a
        value that makes the bound necessary at all."""
        body = collapsed(declaration(WINGMAN_BOT_ELM, "warpAwayFromDanger"))
        self.assertIn("deactivateModulesForWarp context", body)
        self.assertIn("List.filterMap identity |> List.head", body)

    def test_the_arm_never_asks_for_help(self):
        body = declaration(WINGMAN_BOT_ELM, "deactivateModulesForWarp")
        self.assertNotIn("askForHelpToGetUnstuck", body)
        self.assertNotIn("waitForProgressInGame", body)


class TheCounterTest(ReplTest):
    """The counter, folded through the real `updateMemoryForNewReadingFromGame`.

    A counter that is right for one reading and wrong across a session is the
    defect this shape prevents, so every case here folds a list rather than
    asking once.
    """

    def readings(self, names):
        return "[ %s ]" % ", ".join(names)

    def test_a_click_advances_the_counter_by_one(self):
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s 0 [ settled ] == 1"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "foldReadings %s %s 0 [ settled, settled, settled ] == 3"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True, True])

    def test_a_session_that_never_lands_a_click_reaches_the_bound_and_holds(self):
        """The runaway this bound exists for: the client never acknowledges the
        click, so the module reads active and settled on every reading."""
        many = self.readings(["settled"] * 25)
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s 0 %s"
                " == deactivateForWarpAskedReadingsBound"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]), many),
            ]),
            [True])

    def test_nothing_to_do_is_what_resets_the_counter(self):
        """The end of an episode: the module is off, so it is no longer a named
        module that reads active, and the next warp gets the whole allowance."""
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s 0 [ settled, settled, moduleOff ] == 0"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "foldReadings %s %s 0"
                " [ settled, settled, moduleOff, settled ] == 1"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True, True])

    def test_a_decline_holds_the_count_rather_than_resetting_it(self):
        """The divergence from #408's reset, and the reason for it is the case
        below: a decline that resets is a bound an alternation walks past."""
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s 0 [ settled, deactivating ] == 1"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
                "foldReadings %s %s 0 [ settled, silent ] == 1"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True, True])

    def test_a_click_decline_alternation_still_reaches_the_bound(self):
        """A module whose deactivation is cancelled mid-cycle reads `Just True`
        on one reading and `Just False` on the next with `isActive` never
        falling. Under #408's reset the counter oscillates 0, 1, 0, 1 and the
        bound is unreachable; here it climbs and the arm eventually hands the
        reading back, which on the retreat path is the ship warping."""
        alternating = self.readings(["settled", "deactivating"] * 25)
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s 0 %s"
                " == deactivateForWarpAskedReadingsBound"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]),
                   alternating),
            ]),
            [True])

    def test_the_give_up_holds_the_count_rather_than_running_away(self):
        """Held rather than advanced, so the status line's "after N readings"
        goes on meaning what it says."""
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s %s"
                " (deactivateForWarpAskedReadingsBound + 5) [ settled ]"
                " == deactivateForWarpAskedReadingsBound + 5"
                % (NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING])),
            ]),
            [True])

    def test_a_session_that_names_nothing_spends_no_budget(self):
        """With `deactivate-module-on-warp` at its shipped `[]` the counter
        never moves, which is why no recorded run could have shown this."""
        many = self.readings(["settled"] * 10)
        self.assertEqual(
            self.repl.evaluate([
                "foldReadings %s [] 0 %s == 0"
                % (NAMES_THE_PROPULSION_MODULE, many),
            ]),
            [True])

    def test_the_counter_and_the_arm_are_asked_with_one_tooltip_memory(self):
        """The framework updates memory and only then decides, so the arm reads
        the *integrated* `shipModules` while the counter beside it would read
        `botMemoryBefore`'s. `shipModulesNow` is hoisted so the two cannot
        disagree; asserted here because on the reading a tooltip first arrives
        they otherwise name different modules."""
        body = collapsed(declaration(
            WINGMAN_BOT_ELM, "updateMemoryForNewReadingFromGame"))
        binding = indented_binding(body, "deactivateForWarpNow")
        self.assertIn("shipModulesNow", binding)
        self.assertNotIn("botMemoryBefore.shipModules", binding)
        self.assertIn("shipModules = shipModulesNow", body)


class TheStatusClauseTest(ReplTest):
    """What an operator reads, since three of the five answers are `Nothing`."""

    def clause(self, shipModules, names, asked, reading):
        return self.repl.strings(
            ["clauseFor %s %s %s %s" % (shipModules, names, asked, reading)])[0]

    def test_the_quiet_reading_says_nothing(self):
        self.assertEqual(
            self.clause(NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]),
                        "0", "moduleOff"),
            "")

    def test_the_clause_names_the_two_isDeactivating_answers_apart(self):
        """A console showing the second for a whole session is a build that does
        not carry the entry, which is worth being able to see."""
        deactivating = self.clause(
            NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]), "0",
            "deactivating")
        silent = self.clause(
            NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]), "0", "silent")
        self.assertNotEqual(deactivating, silent)
        self.assertIn("already deactivating", deactivating)
        self.assertIn("says nothing", silent)
        self.assertIn("absent is not 'not deactivating'", silent)

    def test_the_clause_carries_the_count_and_the_bound(self):
        clause = self.clause(
            NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]), "7", "settled")
        self.assertIn("7 of ", clause)
        bound = self.repl.strings(
            ["String.fromInt deactivateForWarpAskedReadingsBound"])[0]
        self.assertIn("7 of %s readings spent clicking." % bound, clause)

    def test_the_give_up_says_the_warp_goes_ahead(self):
        clause = self.clause(
            NAMES_THE_PROPULSION_MODULE, elm_strings([SETTING]),
            "deactivateForWarpAskedReadingsBound", "settled")
        self.assertIn("GAVE UP after ", clause)
        self.assertIn("deactivate-module-on-warp", clause)
        self.assertIn("still up", clause)

    def test_the_clause_is_in_the_status_line(self):
        body = collapsed(declaration(WINGMAN_BOT_ELM, "statusTextFromState"))
        self.assertIn("describeDeactivateForWarp context", body)


class TheOtherCallersAreDeliberatelyUntouchedTest(unittest.TestCase):
    """#410 names four other callers of the debounce and puts them out of scope.

    The two **activation-direction** arms have the opposite transient --
    `ramp_active` is absent until a module first cycles, and its duration is
    unmeasured -- and the two **gun** arms click top-row modules whose
    `isActive` genuinely is the duty cycle, bounded today by
    `weaponsAskedReadingsBound`. Both are different questions needing their own
    measurement, so this change touches neither; these cases are what makes that
    a decision somebody has to argue against rather than one a later edit drifts
    into.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = without_comments(handle.read())

    def test_the_new_rule_is_read_only_where_this_change_put_it(self):
        """The whole point of the case: repointing one of the four other
        callers at this rule shows up here and nowhere else."""
        for name in ("deactivateForWarpStep", "deactivateForWarpStepFromReading",
                     "deactivateForWarpStepFromContext",
                     "moduleToDeactivateForWarp", "runningModulesNamedForWarp",
                     "deactivateForWarpAnswersThatSpendAReading"):
            with self.subTest(name):
                self.assertLessEqual(
                    set(declarations_naming(self.source, name)),
                    {"deactivateModulesForWarp", "describeDeactivateForWarp",
                     "updateMemoryForNewReadingFromGame",
                     "deactivateForWarpStep", "deactivateForWarpStepFromReading",
                     "deactivateForWarpStepFromContext",
                     "moduleToDeactivateForWarp", "runningModulesNamedForWarp",
                     "deactivateForWarpAnswersThatSpendAReading"},
                    name)

    def test_the_activation_arms_still_choose_their_own_modules(self):
        self.assertIn(
            "knownModulesToActivateAlways",
            declaration(WINGMAN_BOT_ELM, "activateAlwaysOnModules"))
        self.assertIn(
            "middleRowStepFromContext",
            declaration(WINGMAN_BOT_ELM, "manageMiddleRowModules"))

    def test_the_gun_arms_still_choose_their_own_modules(self):
        self.assertIn(
            "inactiveWeaponFromReading",
            declaration(WINGMAN_BOT_ELM, "fireOnActiveTarget"))
        self.assertIn(
            "shipUIModulesToActivateOnTarget",
            declaration(WINGMAN_BOT_ELM, "fightUsingDronesAndModules"))

    def test_the_debounce_still_has_five_callers(self):
        """A sixth caller is a fifth arm that has to be asked which transient it
        is reading, so it wants to be noticed rather than merged quietly."""
        self.assertEqual(
            sorted(declarations_naming(
                self.source, "clickModuleButtonButWaitIfClickedInPreviousStep")),
            ["activateAlwaysOnModules", "deactivateModulesForWarp",
             "fightUsingDronesAndModules", "fireOnActiveTarget",
             "manageMiddleRowModules"])


def without_comments(text):
    """The source with prose removed, so it is not read as code.

    Both kinds, and the second is not optional here. The doc comments name the
    very declarations the cases below count call sites of --
    `moduleToDeactivateForWarp` appears in three of them -- and a case that
    counted those would report the opposite of what it means to. The `--`
    comments matter for a subtler reason: `BotMemory`'s field comments name
    these declarations too, and `type alias` carries no `name :` annotation, so
    `declaration_containing` walks back past it and attributes the whole record
    to whatever function precedes it. Measured: it reported
    `deactivateForWarpAnswersThatSpendAReading` as being read by
    `goodStandingPatterns`, which reads nothing of the sort.

    Whole-line comments only, so a `--` inside a decision line's own string is
    left alone. And a comment line becomes **a space rather than nothing**:
    `declaration` ends a slice at the first blank line pair, and a doc comment
    inside a declaration would otherwise become one and cut it short. That is
    not hypothetical -- it truncated three declarations here on the first run,
    and each of the three cases then passed or failed on text it had never
    read, which is the shape this repo keeps finding in its own suite.
    """
    without_blocks = re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL)
    return "\n".join(
        " " if line.strip().startswith("--") else line
        for line in without_blocks.splitlines())


def declaration(path, name):
    """One top-level declaration's own lines, from its type annotation on."""
    with open(path, encoding="utf-8") as handle:
        source = without_comments(handle.read())
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
                      flags=re.DOTALL | re.MULTILINE)
    if match is None:
        raise AssertionError("no declaration named %r in %s" % (name, path))
    return match.group(0)


def declaration_containing(source, line_index):
    """The name of the top-level declaration a line falls in, or `None`."""
    annotation = re.compile(r"^([a-z][A-Za-z0-9_]*) :")
    for line in reversed(source.splitlines()[:line_index + 1]):
        match = annotation.match(line)
        if match:
            return match.group(1)
    return None


def declarations_naming(source, name):
    """Every top-level declaration whose body mentions `name`, bar its own."""
    lines = source.splitlines()
    found = []
    for index, line in enumerate(lines):
        if name not in line:
            continue
        owner = declaration_containing(source, index)
        if owner is None or owner == name:
            continue
        found.append(owner)
    return sorted(set(found))


def indented_binding(source, name):
    """One `let` binding's own text, sliced by **indentation**.

    Ends at the next line indented no further than the binding's own name --
    the following binding, or the `in`. A reader that stops at the next
    ` <name> = ` stops at a *record literal* instead, and the binding under test
    here builds one; that reader has cost this repo four assertions that passed
    having read nothing.

    Takes already-collapsed text as readily as raw source: where the caller
    collapsed it, the slice is the whole run between the binding's name and the
    next one, which is what the assertions here need.
    """
    if "\n" not in source:
        match = re.search(
            r"\b%s =(.*?)(?=\b[a-z][A-Za-z0-9_]* =|\bin\b)" % re.escape(name),
            source, flags=re.DOTALL)
        if match is None:
            raise AssertionError("no binding named %r" % name)
        return match.group(1)
    lines = source.splitlines()
    opening = re.compile(r"^(\s+)%s =$" % re.escape(name))
    for index, line in enumerate(lines):
        match = opening.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        body = []
        for following in lines[index + 1:]:
            if following.strip() and (
                    len(following) - len(following.lstrip()) <= indent):
                break
            body.append(following)
        return "\n".join(body)
    raise AssertionError("no binding named %r" % name)


if __name__ == "__main__":
    unittest.main()
