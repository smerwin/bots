"""Tests for the wingman holding a close orbit on its fleet commander.

Issue #365. A fleet follow bot that flies its own kiting pattern against
whatever it is shooting drifts off the commander's grid, which is the one place
it is supposed to be -- and a called target it has drifted out of range of is a
broadcast it cannot act on. So `orbit-fc` defaults to 'yes' and supersedes
`orbit-in-combat` rather than sitting beside it.

Three things need pinning and each has cases here.

**The rule itself**, as `orbitFleetCommanderStep` -- a pure function over five
facts and a counter, executed through the real `Bot.elm` in `elm repl`. The
ordering inside it carries four arguments and each has a case: the commander is
checked before anything counted, the give-up is checked before the stray-window
close (an unbounded rescue is #321's failure), the stray window is checked
before "already orbiting", and the two bounds are what make the fall-back a
fall-back.

**The two bounds**, because this is a repeated ask: open the commander's
overview row's context menu, hover `Orbit`, click the `orbit-fc-range` rung,
every reading, until the client names the manoeuvre `Orbit`. #326 is what an
unbounded one costs: a turret that could not activate held that bot's decision
for 262 consecutive readings with the drones out and idle. Past
`orbitFleetCommanderMenuAskedReadingsBound` the arm stops opening menus and
falls back to the 'W' key, which orbits at the client's own default distance --
a wrong distance beats poking at a menu that will not drive. Past
`orbitFleetCommanderAskedReadingsBound` it answers `Nothing` and
`describeOrbitFleetCommanderAsk` carries the give-up in the status line, the
arrangement `accelerationGateStep` and `fireOnActiveTarget` already use.

**The placement**, which is a shape and not a value, and which a case over the
step function alone would pass on a bot that could never reach it. The arm sits
below `dronesAssistTheCommander` and below `fireOnActiveTarget` so it can
starve neither (#326), and above `accelerationGateStep` because that arm
answers `Just (wait)` on every reading a gate is on the overview while rats are
still on the grid (#348) -- exactly the state this ship most needs to be beside
its commander in. `TheRetreatOutranksTheOrbitTest` covers the one ordering that
is not a trade-off: #364's retreat has to answer before this arm ever can,
because a damaged ship breaks off rather than holds station.

**The mechanism, and what this bot must never do to get a distance.** The
range comes from the context menu, per command. It does **not** come from the
client's default Orbit distance, and nothing here may change that default:
PILOT.md records it as a client setting that survives losing the hull, and #359
hard-linked `core_char_*.dat` across six characters, so a default changed while
flying one follows the others -- including any that later fly saxrat into a
belt at 500 m. `TheClientDefaultIsNeverTouchedTest` refuses the modal route in
source.

**And the mis-click**, which is why this path was thought undrivable. PILOT.md
records gliding to the distance flyout by hand, passing through the parent,
collapsing it, and landing on `Show Info`. The framework does not glide and
click in one motion -- every non-final entry gets `mouseMoveToUIElement` and
nothing else, and only the final entry is clicked, from a node matched in that
reading's own parsed menu. `windowOpenedOverTheClient` is the belt to that
braces: if a window this bot neither opened nor uses appears while the ask is
in flight, the arm closes it by its own close button and the attempt counts
against the budget.

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

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")


class WingmanRepl(ElmRepl):
    """The shared harness, pointed at the wingman.

    `Common.PromptParser` is imported by name because `YesOrNo` is what the
    setting parses to and `Bot` does not re-export it.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-orbit-fc-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", ("import Bot exposing (..)",
                                       "import Common.PromptParser"))
        super().__init__(**kwargs)


def step(setting_is_yes=True, commander_on_grid=True, warping=False,
         orbiting=False, stray_window=False, asked=0):
    """The shipped rule, asked about one reading."""
    return ("orbitFleetCommanderStep { settingIsYes = %s"
            ", commanderOnGrid = %s"
            ", shipIsWarpingOrJumping = %s"
            ", shipIsOrbiting = %s"
            ", strayWindowIsOpen = %s"
            ", askedReadings = %s }"
            % (setting_is_yes, commander_on_grid, warping, orbiting,
               stray_window, asked))


def elm_bool(value):
    return "True" if value else "False"


class TheOrbitDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_setting_turns_it_off(self):
        """`orbit-fc=no` falls back to the saxrat-style movement settings."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == OrbitFleetCommanderIsOff"
                 % step(setting_is_yes=False)]),
            [True])

    def test_only_a_commander_on_the_overview_can_be_orbited(self):
        """A manoeuvre is issued against a row; off grid there is no row."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoCommanderOnGrid" % step(commander_on_grid=False)]),
            [True])

    def test_a_ship_in_warp_is_not_asked_to_orbit(self):
        self.assertEqual(
            self.repl.evaluate(["%s == ShipIsWarpingOrJumping"
                                % step(warping=True)]),
            [True])

    def test_a_commander_on_grid_and_a_ship_not_orbiting_opens_the_menu(self):
        """The whole point: no fight, no broadcast and no rat is required
        first, and the first thing tried is the menu that carries a range."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == OrbitAtRangeViaTheMenu" % step()]),
            [True])

    def test_a_ship_already_orbiting_is_left_alone(self):
        """The confirmation the operator asked for is this and only this: the
        ship UI's own manoeuvre indication, never a dispatched click."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AlreadyOrbiting" % step(orbiting=True)]),
            [True])

    def test_the_menu_gives_way_to_the_key_and_then_to_nothing(self):
        """Both bounds in one place, because what matters is the sequence: the
        cascade, then the 'W' key at the client's default distance, then a
        reading handed back. #326 is what leaving either end unbounded costs."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == OrbitAtRangeViaTheMenu"
                 % step(asked="orbitFleetCommanderMenuAskedReadingsBound - 1"),
                 "%s == OrbitAtTheClientDefaultWithTheKey"
                 % step(asked="orbitFleetCommanderMenuAskedReadingsBound"),
                 "%s == OrbitAtTheClientDefaultWithTheKey"
                 % step(asked="orbitFleetCommanderAskedReadingsBound - 1"),
                 "%s == GaveUpOnTheOrbit"
                 % step(asked="orbitFleetCommanderAskedReadingsBound"),
                 "%s == GaveUpOnTheOrbit"
                 % step(asked="orbitFleetCommanderAskedReadingsBound + 50")]),
            [True, True, True, True, True])

    def test_the_bounds_leave_the_key_a_real_allowance(self):
        """The total is written as the menu bound plus the same 20 the other
        key-over-a-click ask in this file gets, so the fall-back cannot be
        squeezed to nothing by moving one end."""
        self.assertEqual(
            self.repl.evaluate(
                ["orbitFleetCommanderMenuAskedReadingsBound == 30",
                 "orbitFleetCommanderAskedReadingsBound == 50",
                 "orbitFleetCommanderAskedReadingsBound"
                 " - orbitFleetCommanderMenuAskedReadingsBound"
                 " == weaponsAskedReadingsBound"]),
            [True, True, True])

    def test_a_window_the_cascade_opened_is_closed_before_asking_again(self):
        """PILOT.md's recorded mis-click opened a Database Information window.
        Leaving one on top of the client is not acceptable, so this outranks
        both 'already orbiting' and another attempt."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == CloseAWindowTheCascadeOpened"
                 % step(stray_window=True, asked=1),
                 "%s == CloseAWindowTheCascadeOpened"
                 % step(stray_window=True, orbiting=True, asked=1)]),
            [True, True])

    def test_a_window_open_before_the_ask_started_is_not_this_bots_to_close(
            self):
        """`0 < askedReadings` is the whole guard. An operator's own window on
        a healthy session must not be swept away by a bot that never asked for
        anything."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == OrbitAtRangeViaTheMenu"
                 % step(stray_window=True, asked=0)]),
            [True])

    def test_the_window_close_is_itself_bounded(self):
        """A close that does not land is the unbounded rescue #321 names -- one
        run pressed at a stray menu 16,791 times. Past the total budget the
        window is reported and no longer poked at."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheOrbit"
                 % step(stray_window=True,
                        asked="orbitFleetCommanderAskedReadingsBound")]),
            [True])

    def test_the_give_up_is_reported_even_if_the_ship_reads_as_orbiting(self):
        """The bound is checked before the state, `weaponsStep`'s ordering, so
        a spent budget is never masked by a moment that happens to look fine."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheOrbit"
                 % step(orbiting=True,
                        asked="orbitFleetCommanderAskedReadingsBound")]),
            [True])

    def test_a_session_without_the_commander_never_reads_as_a_give_up(self):
        """The other half of the ordering. The counter resets when the
        commander leaves the overview, so this state should not arise -- and
        the rule answers for it anyway rather than resting on that."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoCommanderOnGrid"
                 % step(commander_on_grid=False,
                        asked="orbitFleetCommanderAskedReadingsBound + 1"),
                 "%s == OrbitFleetCommanderIsOff"
                 % step(setting_is_yes=False,
                        asked="orbitFleetCommanderAskedReadingsBound + 1")]),
            [True, True])

    def test_the_menu_is_asked_exactly_when_all_five_facts_line_up(self):
        """Every combination of the five facts at a fresh counter, so a swapped
        or dropped condition is caught rather than only the combinations
        somebody thought to write down. `askedReadings = 1` so the stray-window
        guard is armed."""
        combinations = list(itertools.product([False, True], repeat=5))
        expressions = [
            "%s == OrbitAtRangeViaTheMenu"
            % step(setting_is_yes=elm_bool(setting),
                   commander_on_grid=elm_bool(on_grid),
                   warping=elm_bool(warping),
                   orbiting=elm_bool(orbiting),
                   stray_window=elm_bool(stray),
                   asked=1)
            for setting, on_grid, warping, orbiting, stray in combinations]
        expected = [setting and on_grid and not warping and not orbiting
                    and not stray
                    for setting, on_grid, warping, orbiting, stray
                    in combinations]
        self.assertEqual(self.repl.evaluate(expressions), expected)


class TheSettingTest(unittest.TestCase):
    """The shipped parser, asked what each spelling of the key gives."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parses_to(self, settings_string, expected):
        return ('(parseBotSettings "%s" |> Result.map .orbitFleetCommander)'
                ' == Ok Common.PromptParser.%s'
                % (settings_string, expected))

    def test_an_unconfigured_wingman_orbits_its_commander(self):
        """#365 asks for this on by default, not opt-in."""
        self.assertEqual(
            self.repl.evaluate(
                ["defaultBotSettings.orbitFleetCommander"
                 " == Common.PromptParser.Yes",
                 self.parses_to("", "Yes")]),
            [True, True])

    def test_the_key_can_be_turned_off(self):
        self.assertEqual(
            self.repl.evaluate([self.parses_to("orbit-fc=no", "No")]),
            [True])

    def test_the_range_defaults_to_the_bottom_rung(self):
        """Menu text rather than a number -- `warp-to-anomaly-distance`'s own
        arrangement -- so an operator who reads a different spelling off their
        client can just write it."""
        self.assertEqual(
            self.repl.evaluate(
                ['defaultOrbitFleetCommanderRange == "500 m"',
                 '(parseBotSettings "" |> Result.map .orbitFleetCommanderRange)'
                 ' == Ok "500 m"',
                 '(parseBotSettings "orbit-fc-range=5 km"'
                 ' |> Result.map .orbitFleetCommanderRange) == Ok "5 km"',
                 '(parseBotSettings "orbit-fc-range =  2,500 m "'
                 ' |> Result.map .orbitFleetCommanderRange) == Ok "2,500 m"']),
            [True, True, True, True])

    def test_the_spelling_the_issue_uses_is_accepted(self):
        """Setting names are matched case-sensitively -- `getSettingByNameOrGuide`
        is a `Dict.get` -- so #365's own `orbit-FC` has to be an alternative
        name or an operator who pasted the issue gets a session that ends
        before it starts (#161's failure)."""
        self.assertEqual(
            self.repl.evaluate(
                [self.parses_to("orbit-FC=no", "No"),
                 self.parses_to("orbit-fleet-commander=no", "No")]),
            [True, True])


class ThePlacementAndTheSupersessionTest(unittest.TestCase):
    """Source-pinned, because each of these is a shape rather than a value.

    A suite that only exercised `orbitFleetCommanderStep` would pass on a bot
    whose arm nothing could reach, which is exactly the defect #360 shipped.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        for needle in needles:
            self.assertIn(needle, self.source)
        return [self.source.index(needle) for needle in needles]

    def test_the_orbit_sits_below_the_drones_and_the_guns(self):
        """#326's rule: reaching the drones or the guns must never require a
        manoeuvre to land first."""
        drones, guns, orbit = self.order_of(
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of",
            "case orbitTheFleetCommander context shipUI of")
        self.assertLess(drones, guns)
        self.assertLess(guns, orbit)

    def test_the_orbit_sits_above_the_gate(self):
        """#348's arm answers `Just (wait)` on every reading a gate is on the
        overview with rats still around. Below it, the orbit would be starved
        in the one state it exists for."""
        orbit, gate = self.order_of(
            "case orbitTheFleetCommander context shipUI of",
            "case accelerationGateStep context of")
        self.assertLess(orbit, gate)

    def test_orbit_fc_supersedes_orbit_in_combat(self):
        """#365 is explicit that this is not a third option beside the other
        two: with `orbit-fc=yes` the combat path must not issue its own orbit
        at a rat, which is what walks the ship off the commander's grid."""
        chooser = self.source[self.source.index(
            "    if context.eventContext.botSettings.orbitFleetCommander"):]
        chooser = chooser[:chooser.index("\n\n\n")]
        self.assertLess(
            chooser.index("orbitFleetCommander == PromptParser.Yes"),
            chooser.index("orbitInCombat == PromptParser.Yes"))
        self.assertNotIn("ensureShipIsOrbitingDecision",
                         chooser[:chooser.index(
                             "orbitInCombat == PromptParser.Yes")])

    def test_the_counter_is_advanced_by_the_shipped_rule_itself(self):
        """#102's defect is a counter advanced by one condition and read by
        another. The memory update calls `orbitFleetCommanderStep` rather than
        restating it, so the two cannot drift apart."""
        update = self.source[self.source.index(
            "updateMemoryForNewReadingFromGame context botMemoryBefore ="):]
        update = update[:update.index(
            "\n\n\ngetCurrentAnomalyIDAsSeenInProbeScanner")]
        self.assertIn("orbitFleetCommanderStep", update)
        self.assertIn("orbitFleetCommanderAnswersThatSpendAReading", update)
        self.assertIn("orbitFleetCommanderAskedReadings + 1", update)

    def test_the_commander_is_read_the_one_way_both_sides_can_read_him(self):
        """The arm and the counter resolve the commander through the same
        reading-only function. `fleetCommanderNameFromPanel` falls back to a
        setting, and `updateMemoryForNewReadingFromGame` never sees settings --
        an arm asking in that form would spend a budget nothing advances."""
        entry = self.source[self.source.index(
            "fleetCommanderOverviewEntry readingFromGameClient ="):]
        entry = entry[:entry.index("\n\n\n")]
        self.assertIn("fleetCommanderNameFromFleetWindowHeader", entry)
        self.assertNotIn("fleetCommanderNameFromPanel", entry)

    def test_a_give_up_on_the_orbit_is_visible_in_the_status_line(self):
        """The arm answers `Nothing` when it gives up, so without this a ship
        that stopped trying reads exactly like a ship that is orbiting fine."""
        self.assertIn("describeOrbitFleetCommanderAsk context", self.source)
        self.assertIn("Orbit on the commander: ", self.source)
        self.assertIn("GAVE UP after ", self.source)

    def test_the_header_offers_both_keys(self):
        """`--help` reads the header, and #161's failure is a header that
        promises a key the parser has never heard of. The converse -- a parsed
        key the header hides -- is #125. Both keys are named in both places."""
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("`orbit-fc`", header)
        self.assertIn("`orbit-fc-range`", header)
        self.assertIn('( "orbit-fc"', self.source)
        self.assertIn('( "orbit-fc-range"', self.source)

    def test_the_cascade_takes_orbit_and_then_the_configured_rung(self):
        """The mechanism, in the order the client renders it. A cascade that
        stopped at `Orbit` would orbit at the client's default and read as
        working, which is the failure this whole change exists to avoid."""
        arm = self.source[self.source.index(
            "orbitTheFleetCommander context shipUI ="):]
        arm = arm[:arm.index("\n\n\n")]
        # Bounded at the *next* answer, so the range named in the fall-back
        # branch's own message cannot stand in for the rung the cascade takes.
        cascade = arm[arm.index("useContextMenuCascadeOnOverviewEntry"):
                      arm.index("OrbitAtTheClientDefaultWithTheKey ->")]
        self.assertEqual(cascade.count("useMenuEntryWithTextContaining"), 2)
        self.assertLess(
            cascade.index("useMenuEntryWithTextContaining orbitMenuEntryText"),
            cascade.index("orbitFleetCommanderRange"))
        self.assertIn("menuCascadeCompleted", cascade)

    def test_the_range_default_is_a_round_choice_and_says_so(self):
        """`orbit-fc-range` carries menu text, not a number, because what the
        client offers is a fixed list and this repo has never read it. The
        default is documented as a round operator choice rather than as a
        measurement."""
        block = self.source[self.source.index(
            "defaultOrbitFleetCommanderRange : String"):]
        block = block[:block.index("\n\n\n")]
        self.assertIn('"500 m"', block)
        doc = self.source[:self.source.index(
            "defaultOrbitFleetCommanderRange : String")]
        doc = doc[doc.rindex("{-|"):]
        self.assertIn("round choice", doc)
        self.assertIn("not measured against anything", doc)

    def test_the_orbit_is_below_every_arm_that_fights(self):
        """Restating the whole chain in one place, so a rebase that moved the
        arm to a plausible-looking spot still has to move it past a case."""
        ending, retreat, modules, broadcast, drones, guns, orbit, gate = \
            self.order_of(
                "case sessionIsEnding context shipUI of",
                "case retreatToTheCommander context of",
                "case activateAlwaysOnModules context of",
                "case actOnFleetBroadcast context shipUI of",
                "case dronesAssistTheCommander context of",
                "case fireOnActiveTarget context of",
                "case orbitTheFleetCommander context shipUI of",
                "case accelerationGateStep context of")
        self.assertEqual(
            [ending, retreat, modules, broadcast, drones, guns, orbit, gate],
            sorted([ending, retreat, modules, broadcast, drones, guns, orbit,
                    gate]))

    def test_the_fall_back_reuses_the_established_key_over_a_click(self):
        """`ensureShipIsOrbiting` is saxrat's mechanism, already in this file,
        and it is what the give-up path degrades to. Nothing here invents a
        second way to command a manoeuvre, and nothing posts a key directly."""
        arm = self.source[self.source.index(
            "orbitTheFleetCommander context shipUI ="):]
        arm = arm[:arm.index("\n\n\n")]
        self.assertIn("ensureShipIsOrbiting shipUI", arm)
        self.assertIsNone(re.search(r"vkey_\w+", arm))


class TheClientDefaultIsNeverTouchedTest(unittest.TestCase):
    """The client's default Orbit distance is not this bot's to change.

    It lives in the client rather than the ship, so PILOT.md records it
    surviving the loss of a hull and applying to whatever is boarded next --
    and #359 hard-linked `core_char_*.dat` across six characters, so a default
    changed while flying one of them follows the others, including any that
    later fly `eve-online-saxrat` into a belt at 500 m. A per-command range off
    the context menu mutates nothing, which is the whole reason the operator
    asked for that path.

    The route being refused here is a real one and was this PR's earlier plan:
    right-click the Selected Item panel's Orbit button, take `Set Default
    "Orbit" Distance`, and type into the modal's `edit_qty`. That modal is
    recorded in `saxrat_run15.log`. Nothing in this bot may drive it.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_nothing_drives_the_set_default_modal(self):
        for forbidden in ('Set Default "Orbit"', "Set default \"Orbit\" distance",
                          "edit_qty", "selectedItemOrbit",
                          "ok_dialog_button"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_the_stray_window_reader_names_no_unread_literal(self):
        """No run in `~/eve-bot-logs` carries the Show Info window's type name,
        so a matcher written for it would be a matcher on a channel nothing has
        read -- #42's shape. The reader is structural instead, and prints
        whatever type name it meets so the first run that hits one records the
        literal."""
        block = self.source[self.source.index(
            "windowOpenedOverTheClient readingFromGameClient ="):]
        block = block[:block.index("\n\n\n")]
        for invented in ("ShowInfo", "Database Information", "InfoWindow"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, block)
        self.assertIn('String.endsWith "Window"', block)
        self.assertIn("closeButton", block)
        self.assertIn("pythonObjectTypeName", self.source[
            self.source.index("describeOrbitFleetCommanderAsk context ="):
            self.source.index("{-| The acceleration-gate ask")])

    def test_nothing_is_clicked_at_a_guessed_point(self):
        """#321's stray-menu rescue right-clicked a computed location 16,791
        times in one run and created the menu it was clearing. The window this
        arm closes is closed by its own close button or not at all."""
        arm = self.source[self.source.index(
            "orbitTheFleetCommander context shipUI ="):]
        arm = arm[:arm.index("\n\n\n")]
        close = arm[arm.index("CloseAWindowTheCascadeOpened ->"):]
        close = close[:close.index("OrbitAtRangeViaTheMenu ->")]
        self.assertIn("closeButton", close)
        self.assertIn("clickUiElementForNavigation closeButton", close)
        self.assertNotIn("effectsMouseClickAtLocation", close)

    def test_the_header_says_why_rather_than_only_that(self):
        """A prohibition with no reason attached is one somebody undoes."""
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("#359", header)
        self.assertIn("core_char_", header)


class TheRetreatOutranksTheOrbitTest(unittest.TestCase):
    """#364's retreat must always answer before this arm can.

    The two changes landed on parallel branches and this is where they meet.
    `retreatToTheCommander` sits second in `wingmanDecisionRootInSpace`, under
    `sessionIsEnding` and over everything else, because a ship past its shield
    or armour threshold has to break off. The orbit does the opposite -- it
    holds the ship on the grid it is being shot on -- so an ordering that let
    it answer first would keep a dying ship on station while the guard that
    exists to save it never got the reading.

    Neither branch's own cases could have caught an inversion: #364's pin the
    retreat against the arms that existed when it was written, and the orbit
    arm is not one of them. Nothing but a case naming both refuses a future
    rebase that reorders them, and a rebase is exactly how this one arrived.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_retreat_arm_comes_first(self):
        retreat = self.source.index("case retreatToTheCommander context of")
        orbit = self.source.index(
            "case orbitTheFleetCommander context shipUI of")
        self.assertLess(retreat, orbit)

    def test_the_retreat_is_still_the_second_arm_in_the_root(self):
        """Not merely 'above the orbit'. Everything between `sessionIsEnding`
        and the retreat would be an arm that can hold a reading away from it,
        so the two have to stay adjacent."""
        root = self.source[self.source.index(
            "wingmanDecisionRootInSpace context shipUI ="):]
        root = root[:root.index("\n\n\n")]
        arms = re.findall(r"case (\w+) context", root)
        self.assertEqual(arms[:2],
                         ["sessionIsEnding", "retreatToTheCommander"])
        self.assertIn("orbitTheFleetCommander", arms)
        self.assertGreater(arms.index("orbitTheFleetCommander"), 1)

    def test_the_two_arms_still_read_the_commander_differently(self):
        """Not a rule anybody wants to keep -- a fact this PR is pinning so it
        cannot be lost. #364's retreat runs to `fleetCommanderName`, which is
        the first pilot in `follow-fleet-broadcast-from` and answers `Nothing`
        when that setting is unset; the orbit resolves the commander off the
        fleet window's own header. On a reading where those disagree the two
        arms are about different ships. Unifying them is #367; when that lands
        this case is the one that should go red and be deleted with it."""
        retreat = self.source[self.source.index(
            "retreatToTheCommander context =\n"):]
        retreat = retreat[:retreat.index("\n\n\n")]
        orbit = self.source[self.source.index(
            "orbitTheFleetCommander context shipUI ="):]
        orbit = orbit[:orbit.index("\n\n\n")]
        self.assertIn("fleetCommanderName context", retreat)
        self.assertIn("fleetCommanderOverviewEntry", orbit)
        self.assertNotIn("fleetCommanderName context", orbit)
        self.assertIn("#367", self.source)


if __name__ == "__main__":
    unittest.main()
