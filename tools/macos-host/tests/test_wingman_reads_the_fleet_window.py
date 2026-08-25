"""Tests for the wingman's fleet-window reading.

`eve-online-wingman` replaces `eve-online-wingus`, which flew the same job on
the retired `BotInterface_To_Host_2023_02_06` interface.

**Everything asserted here was captured from a live client**, not invented. Gal
Bistot's fleet window, read through `eve_read.py` while a run was in flight:

    FleetBroadcastCont  bannerLabel  'Target Heather Hemorphite (Tristan)'
    FleetWindow         entryLabel   '02:59:30 - Target Heather Hemorphite (Tristan)'
    FleetWindow         entryLabel   '02:31:32 - Gal Bistot: Travel to Riramia'
    FleetMember         entryLabel   'Greta Gneiss'
    FleetHeader         (label)      'Fleet (5)' / 'Gal Bistot'

Three facts fall out of that capture and each has a case below.

**The two broadcast forms are shaped differently.** A travel broadcast names its
sender before a colon; a target broadcast names the *target* and its hull and
says nothing about who sent it. So `follow-fleet-broadcast-from` -- an allowlist
matched against the sender -- cannot filter a target broadcast at all. The trust
for those is in `accept-fleet-invite-from`, which is what decides whether this
ship is in the fleet in the first place.

**`entryLabel` is not the broadcast history's private name.** Inside the fleet
window it serves the member rows too, and outside it the drones window uses it
for drone status -- which is the collision that made saxrat read a drone's row
instead of a broadcast during exactly the readings a call is most likely to be
real. The `HH:MM:SS - ` prefix is what separates history from members.

**The member rows are not the whole fleet.** The header read `Fleet (5)` beside
four `FleetMember` rows, because the boss is drawn in the header instead. A
"do not shoot a fleet member" guard that reads only the rows misses the
commander -- the one pilot it matters most not to shoot.

The cases run the real `Bot.elm` through `elm repl`. Nothing here reads a live
client, the recorded corpus, or a running bot.

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

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# Exactly as the client rendered them.
TARGET_BANNER = "Target Heather Hemorphite (Tristan)"
TRAVEL_HISTORY = "02:31:32 - Gal Bistot: Travel to Riramia"
TARGET_HISTORY = "02:59:30 - Target Heather Hemorphite (Tristan)"
MEMBER_ROW = "Greta Gneiss"


class WingmanRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-fleet-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        super().__init__(**kwargs)


class TheTargetBroadcastIsReadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_pilot_name_is_taken_without_the_hull(self):
        self.assertEqual(
            self.repl.strings(
                ['Maybe.withDefault "<none>"'
                 ' (targetBroadcastPilotName "%s")' % TARGET_BANNER]),
            ["Heather Hemorphite"])

    def test_a_travel_broadcast_is_not_a_target_broadcast(self):
        # It names its sender before a colon and carries no target at all.
        self.assertEqual(
            self.repl.evaluate(
                ['targetBroadcastPilotName "Gal Bistot: Travel to Riramia"'
                 ' == Nothing']),
            [True])

    def test_a_verb_nobody_has_captured_yet_is_not_guessed_at(self):
        """The eight remaining broadcasts have no observed wording.

        The fleet window's buttons name them -- `Broadcast: Need Backup` and so
        on -- but the button's words are not the broadcast's, and only two
        rendered forms have been seen. Matching one on the button's wording
        would be a guess that reads like a fact.
        """
        self.assertEqual(
            self.repl.evaluate(
                ['targetBroadcastPilotName "Gal Bistot: Need Backup" == Nothing',
                 'List.member "Need Backup" broadcastVerbsNotYetRead',
                 'List.length broadcastVerbsNotYetRead == 8']),
            [True, True, True])


class TheHistoryIsToldFromTheMemberRowsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_history_line_gives_up_its_timestamp(self):
        self.assertEqual(
            self.repl.strings(
                ['Maybe.withDefault "<none>"'
                 ' (textAfterBroadcastTimestamp "%s")' % TRAVEL_HISTORY]),
            ["Gal Bistot: Travel to Riramia"])

    def test_a_member_row_is_not_a_history_line(self):
        # Both are `entryLabel` inside the same window; the prefix is the only
        # thing telling them apart.
        self.assertEqual(
            self.repl.evaluate(
                ['textAfterBroadcastTimestamp "%s" == Nothing' % MEMBER_ROW]),
            [True])

    def test_the_target_history_line_reaches_the_same_pilot_name(self):
        """History and banner carry the same broadcast, so they must agree."""
        self.assertEqual(
            self.repl.strings(
                ['Maybe.withDefault "<none>"'
                 ' (Maybe.andThen targetBroadcastPilotName'
                 ' (textAfterBroadcastTimestamp "%s"))' % TARGET_HISTORY]),
            ["Heather Hemorphite"])

    def test_a_line_that_only_looks_timestamped_is_refused(self):
        for text in ('Gal Bistot - Travel to Riramia',
                     '2:31:32 - too short',
                     '02:31:32 -'):
            with self.subTest(text):
                self.assertEqual(
                    self.repl.evaluate(
                        ['textAfterBroadcastTimestamp "%s" == Nothing' % text]),
                    [True])


class TheFleetIsScopedAndComplete(unittest.TestCase):
    """Source-pinned: reaching these live needs a fleet and a client."""

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_fleet_reading_is_scoped_to_the_fleet_window(self):
        # Not tree-wide. The drones window uses `entryLabel` for its own rows,
        # and reading it tree-wide is what #329 had to fix in saxrat.
        self.assertIn("readingFromGameClient.fleetWindow", self.source)

    def test_the_no_shoot_guard_includes_the_commander(self):
        """`Fleet (5)` beside four member rows -- the boss is in the header."""
        self.assertIn("fleetPilotNames", self.source)
        self.assertIn("fleetCommanderName", self.source)

    def test_a_called_target_in_the_fleet_is_not_shot(self):
        self.assertIn("is in this fleet. Not shooting it.", self.source)

    def test_the_trip_home_routes_and_docks_rather_than_announcing_a_gap(self):
        """This pinned the *absence* of the feature until #350 built it.

        It read `assertIn("is not implemented yet.", source)`, which is a
        perfectly good assertion right up until someone implements the thing --
        and then it fails on the change it should have started covering, which
        is how a reader is taught to edit the pin rather than check the rule.
        The rule worth pinning is the one the two live runs established: a
        session that ends must not leave the ship in space.
        """
        self.assertIn("flyRouteHome", self.source)
        self.assertIn("homeStation", self.source)
        self.assertNotIn("is not implemented yet.", self.source)

    def test_it_gives_up_rather_than_renewing_the_lease_forever(self):
        """The mission runner's 420 seconds, and its bound.

        A wind-down that keeps asking for more time is a session that never
        ends -- #321's lesson in a different place.
        """
        self.assertIn("extend-session", self.source)

    def test_the_docked_branch_no_longer_undocks_unconditionally(self):
        """Found by #354's own review, not by the issue.

        The docked arm has always meant "undock". Without gating it on being at
        the home station, the ship would dock at the end of its trip and undock
        again on the very next reading, making the whole trip pointless.
        """
        self.assertIn("defaultHomeStation", self.source)


if __name__ == "__main__":
    unittest.main()


class TheBroadcastVocabularyIsParsedTest(unittest.TestCase):
    """Every wording four live runs actually observed, through the real parser.

    Three grammars, not one -- which is why `parseFleetBroadcast` is a parser
    and not a prefix test:

        Target Heather Hemorphite (Tristan)        no sender at all
        Gal Bistot: Travel to Bhizheba             sender behind a colon
        Gal Bistot is at location Amarr            sender, no colon

    Asserted by equality against the value the parser should produce, so each
    case pins the arm *and* the fields it carried out of the text -- an arm
    reached with the argument mangled is a bot flying to the wrong place.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_observed_wording_parses_to_its_own_value(self):
        for banner, expected in [
                ('Target Heather Hemorphite (Tristan)',
                 'CalledTarget "Heather Hemorphite"'),
                ('Gal Bistot: Travel to Bhizheba',
                 'TravelTo { pilot = "Gal Bistot", destination = "Bhizheba" }'),
                ('Gal Bistot: Jump Stargate Bhizheba',
                 'JumpGate { pilot = "Gal Bistot", gate = "Bhizheba" }'),
                ('Gal Bistot: Align Stargate Bhizheba',
                 'AlignGate { pilot = "Gal Bistot", gate = "Bhizheba" }'),
                ('Gal Bistot is at location Amarr',
                 'AtLocation { pilot = "Gal Bistot", system = "Amarr" }'),
                ('Gal Bistot is in position at Stargate Amarr',
                 'InPositionAt { pilot = "Gal Bistot", gate = "Amarr" }')]:
            with self.subTest(banner):
                self.assertEqual(
                    self.repl.evaluate(
                        ['parseFleetBroadcast "%s" == %s' % (banner, expected)]),
                    [True])

    def test_in_position_is_not_read_as_at_location(self):
        """`is in position at Stargate X` also contains `is at`.

        The one ordering mistake this parser can make, and the one that would
        route the ship to a system named after a stargate.
        """
        self.assertEqual(
            self.repl.evaluate(
                ['parseFleetBroadcast "Gal Bistot is in position at Stargate Amarr"'
                 ' == InPositionAt { pilot = "Gal Bistot", gate = "Amarr" }']),
            [True])

    def test_a_wording_nobody_has_read_is_carried_rather_than_dropped(self):
        # It reaches the arm that opens the broadcast's own menu, which is how
        # the remaining wordings get captured instead of guessed at.
        self.assertEqual(
            self.repl.evaluate(
                ['parseFleetBroadcast "Gal Bistot: Something Nobody Has Seen"'
                 ' == Unrecognized "Gal Bistot: Something Nobody Has Seen"']),
            [True])

    def test_only_the_called_target_has_no_sender(self):
        """Which is why `follow-fleet-broadcast-from` cannot gate it."""
        self.assertEqual(
            self.repl.evaluate([
                'fleetBroadcastSender (parseFleetBroadcast'
                ' "Target Heather Hemorphite (Tristan)") == Nothing',
                'fleetBroadcastSender (parseFleetBroadcast'
                ' "Gal Bistot is at location Amarr") == Just "Gal Bistot"',
                'fleetBroadcastSender (parseFleetBroadcast'
                ' "Gal Bistot: Jump Stargate Bhizheba") == Just "Gal Bistot"']),
            [True, True, True])


class TheDronesAssistTheCommanderTest(unittest.TestCase):
    """Source-pinned: the cascade needs a drones window and a live fleet.

    What is checkable from here is the shape, and the shape is where the two
    measured failures live.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_commander_is_read_from_the_panel_not_hardcoded(self):
        """saxrat's version named `Gal Bistot` in the source.

        A wingman that only ever assists one pilot is a wingman for one fleet.
        """
        self.assertIn("fleetCommanderNameFromPanel", self.source)
        self.assertNotIn('useMenuEntryWithTextContaining "Gal Bistot"', self.source)

    def test_it_falls_back_to_engage_target_in_the_same_reading(self):
        """#314 deleted the unbounded cascade because the named pilot was often
        off grid and the readings it spent bought nothing. The fallback is what
        makes reinstating it safe."""
        self.assertIn("'Assist' if present, else 'Engage Target'", self.source)
        self.assertIn("Engage Target", self.source)

    def test_the_drone_arm_is_reached_before_the_combat_arm(self):
        """#326: a turret that could not activate held the decision on the
        other arm of that `case` for 262 consecutive readings, drones out and
        idle, nothing landing. So the drone arm must not sit behind it."""
        root = self.source[self.source.index("wingmanDecisionRootInSpace context shipUI ="):]
        root = root[:root.index("\n\n\n")]
        self.assertLess(
            root.index("dronesAssistTheCommander"),
            root.index("fightPointedRatsOrReturnDrones"),
            "the drone arm is behind the inherited combat arm again")

    def test_the_assist_can_be_turned_off(self):
        # A logi or a solo fit wants its drones on its own target.
        self.assertIn("assistFleetCommander", self.source)


class TheAccelerationGateStepTest(unittest.TestCase):
    """#348: take a gate, but only clear of rats, and bounded.

    `accelerationGateActivationStep` is executed for real through `elm repl`
    -- ported from saxrat's `gateActivationStep` of the same shape, so the
    boundary cases are the ones that matter: which side of the give-up bound
    answers what, and that a gate not yet selected is selected before the
    panel's button is ever asked about.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_unselected_gate_is_selected_first(self):
        self.assertEqual(
            self.repl.evaluate([
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = False, panelOffersActivateGate = False'
                ', askedReadings = 0 } == SelectTheGate']),
            [True])

    def test_a_selected_gate_with_no_button_yet_waits(self):
        self.assertEqual(
            self.repl.evaluate([
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = True, panelOffersActivateGate = False'
                ', askedReadings = 3 } == WaitForTheActivateButton']),
            [True])

    def test_the_button_is_pressed_once_offered(self):
        self.assertEqual(
            self.repl.evaluate([
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = True, panelOffersActivateGate = True'
                ', askedReadings = 3 } == PressActivateGate']),
            [True])

    def test_the_give_up_boundary_is_exactly_forty(self):
        # 40 is still an ordinary ask; 41 is a give-up. Same numbers saxrat's
        # `gateRefusesThisShipTicks` uses, and the same reason: its own corpus
        # separates a working gate's cost (0-15 readings) from a genuinely
        # stuck one (past 335) with room on both sides.
        self.assertEqual(
            self.repl.evaluate([
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = True, panelOffersActivateGate = True'
                ', askedReadings = 40 } == PressActivateGate',
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = True, panelOffersActivateGate = True'
                ', askedReadings = 41 } == GiveUpOnThisGate',
                'accelerationGateHasBeenGivenUpOn 40 == False',
                'accelerationGateHasBeenGivenUpOn 41 == True']),
            [True, True, True, True])

    def test_a_give_up_wins_even_over_a_gate_the_panel_already_shows(self):
        # The bound must not be shadowed by the panel already being ready --
        # exactly the #147 shadowing this file's own doc comment references.
        self.assertEqual(
            self.repl.evaluate([
                'accelerationGateActivationStep'
                ' { panelShowsTheGate = True, panelOffersActivateGate = True'
                ', askedReadings = 999 } == GiveUpOnThisGate']),
            [True])

    def test_it_sits_after_the_drone_arm_and_before_the_inherited_combat_arm(self):
        root = self.source[self.source.index("wingmanDecisionRootInSpace context shipUI ="):]
        root = root[:root.index("\n\n\n")]
        self.assertLess(
            root.index("dronesAssistTheCommander"),
            root.index("accelerationGateStep"),
            "the gate arm must not preempt drones still assisting on a live grid")
        self.assertLess(
            root.index("accelerationGateStep"),
            root.index("fightPointedRatsOrReturnDrones"))

    def test_the_ask_is_reported_in_the_status_line(self):
        # #343's own review caught a single "waiting" line covering two
        # different situations; this must name which one it is.
        self.assertIn("describeAccelerationGateAsk", self.source)
        self.assertIn("rats still on the grid", self.source)


class TheModuleActivationSplitTest(unittest.TestCase):
    """#349: `activate-module-always` reached the client only through the arm
    inherited from the combat anomaly bot, which did module activation, rat
    combat and anomaly hunting together. That put module activation behind
    the broadcast and the drone arm, and it dragged an idle-grid anomaly hunt
    in with it -- not following a commander, and the reason a six-hour
    unattended run was a bad idea.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def _wingman_root_body(self):
        root = self.source[self.source.index("wingmanDecisionRootInSpace context shipUI ="):]
        return root[:root.index("\n\n\n")]

    def test_module_activation_is_its_own_step_ahead_of_the_broadcast(self):
        root = self._wingman_root_body()
        self.assertIn("activateAlwaysOnModules", root)
        self.assertIn("actOnFleetBroadcast", root)
        self.assertLess(
            root.index("activateAlwaysOnModules"),
            root.index("actOnFleetBroadcast"),
            "module activation is not ahead of the broadcast")

    def test_the_wingman_s_own_root_no_longer_reaches_anomaly_hunting(self):
        """`enterAnomaly` / `decideActionInAnomaly` still exist in this file,
        for the inherited `anomalyBotDecisionRoot` -- but nothing reachable
        from `wingmanDecisionRootInSpace` may call them."""
        root = self._wingman_root_body()
        self.assertNotIn("enterAnomaly", root)
        self.assertNotIn("decideActionInAnomaly", root)
        self.assertNotIn("modulesToActivateAlwaysActivated", root)

    def test_self_defense_against_a_pointing_rat_is_kept(self):
        fallback = self.source[
            self.source.index("fightPointedRatsOrReturnDrones :"):]
        fallback = fallback[:fallback.index("\n\n\n")]
        self.assertIn("fightRatsIfShipIsPointed", fallback)
        self.assertIn("returnDronesToBay", fallback)


from test_saxrat_ported_guards import (  # noqa: E402
    SaxratRepl, node, overview, source_of)
from test_saxrat_route_stargate_panel_jump import (  # noqa: E402
    JUMP_BUTTON, selected_item_window)

# Stargate rows exactly as `overview()` and the real parser expect them --
# Distance/Name/Type, the shape `test_saxrat_route_stargate_panel_jump.py`'s
# own LIVE_STARGATE_ROWS were read off a live client in.
BHIZHEBA_GATE_ROW = ("8,998 m", "Bhizheba", "Stargate (Amarr System)")
OTHER_GATE_ROW = ("12,000 m", "Tar", "Stargate (CONCORD System)")


class WingmanJumpRepl(WingmanRepl):
    """The fleet-window repl, extended with the parser modules `gateOverviewEntry`
    and `routeStargateJumpForNamedGate` need to be handed a real reading."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-jump-repl-")
        kwargs.setdefault("preamble", (
            "import Bot exposing (..)",
            "import EveOnline.MemoryReading",
            "import EveOnline.ParseUserInterface",
        ))
        super().__init__(**kwargs)


class TheGateOverviewEntryTest(unittest.TestCase):
    """`gateOverviewEntry`, over the overview a real reading would carry.

    #347's own safety condition: the gate a `Jump Stargate X` or
    `Align Stargate X` broadcast names may not be on the overview at all, and
    this is what has to answer `Nothing` rather than a different row when that
    happens -- `stargateNameLeadsToSystem` is the same identity match
    `routeStargateJumpFromReading` already trusts for the route panel's own
    next system, reused rather than a fifth copy of it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanJumpRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def found(self, gate_name, rows, hide_rows=()):
        overview_window = overview(rows)
        for index in hide_rows:
            entries = overview_window["children"][0]["children"][1:]
            entries[index]["dictEntriesOfInterest"]["_display"] = False
        definition = SaxratRepl.reading_binding("reading", [overview_window])
        return self.repl.strings(
            ['reading |> Maybe.andThen (gateOverviewEntry "%s")'
             ' |> Maybe.andThen .objectName'
             ' |> Maybe.withDefault "<none>"' % gate_name],
            definitions=[definition])[0]

    def test_the_named_gate_is_found_on_the_overview(self):
        self.assertEqual(
            self.found("Bhizheba", [BHIZHEBA_GATE_ROW, OTHER_GATE_ROW]),
            "Bhizheba")

    def test_a_gate_leading_elsewhere_is_not_believed_to_be_it(self):
        """The wrong-system hazard: nothing here may stand in for a gate that
        is not on the overview."""
        self.assertEqual(self.found("Bhizheba", [OTHER_GATE_ROW]), "<none>")

    def test_a_row_that_is_not_a_stargate_does_not_match(self):
        self.assertEqual(
            self.found("Bhizheba", [("500 m", "Bhizheba", "Wreck")]), "<none>")

    def test_a_row_the_client_is_not_drawing_is_not_believed(self):
        """A row scrolled out of the overview keeps a plausible region pointing
        at whatever was recycled into its place -- CLAUDE.md's "Reading the
        overview"."""
        self.assertEqual(
            self.found("Bhizheba", [BHIZHEBA_GATE_ROW], hide_rows=(0,)),
            "<none>")

    def test_the_name_is_matched_on_word_boundaries_not_as_a_substring(self):
        self.assertEqual(
            self.found("Bhi", [("500 m", "Bhizheba", "Stargate (Bhizheba)")]),
            "<none>",
            "'Bhi' matched 'Bhizheba' as a substring")


class TheRouteStargateJumpForNamedGateTest(unittest.TestCase):
    """`routeStargateJumpForNamedGate`, over a real reading.

    The same `routeStargateJump` rule `navigateTowardFleetCommander` already
    trusts, fed the broadcast's own gate name instead of the route panel's
    next system -- reused unchanged rather than a fourth copy of the jump
    logic, which is what #347 asked for.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanJumpRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdict(self, gate_name, rows, panel_showing, buttons=(JUMP_BUTTON,)):
        children = [overview(rows)]
        if panel_showing is not None:
            children.append(selected_item_window(panel_showing, buttons))
        definition = SaxratRepl.reading_binding("reading", children)
        return self.repl.strings([
            'reading |> Maybe.map (routeStargateJumpForNamedGate "%s"'
            ' >> describeRouteStargateJump)'
            ' |> Maybe.withDefault "no reading at all"' % gate_name
        ], definitions=[definition])[0]

    def test_the_named_gate_is_jumped_when_the_panel_already_shows_it(self):
        answer = self.verdict(
            "Bhizheba", [BHIZHEBA_GATE_ROW],
            "Bhizheba (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("Jump through 'Bhizheba'", answer)

    def test_a_panel_showing_a_different_gate_does_not_jump(self):
        """The failure this whole design refuses: pressing Jump while the panel
        shows another gate would send the ship through the wrong stargate."""
        answer = self.verdict(
            "Bhizheba", [BHIZHEBA_GATE_ROW],
            "Tar (<color=#ff4ecef8>0.8</color>)")
        self.assertIn("not showing the stargate to 'Bhizheba'", answer)
        self.assertNotIn("Jump through", answer)

    def test_no_gate_named_for_the_broadcast_declines(self):
        answer = self.verdict("Bhizheba", [OTHER_GATE_ROW], None)
        self.assertIn(
            "No stargate on the overview is named for 'Bhizheba'", answer)
        self.assertNotIn("Jump through", answer)

    def test_a_panel_without_the_jump_button_declines(self):
        answer = self.verdict(
            "Bhizheba", [BHIZHEBA_GATE_ROW],
            "Bhizheba (<color=#ff4ecef8>0.8</color>)",
            buttons=("selectedItemOrbit",))
        self.assertIn("offers no 'selectedItemJump'", answer)
        self.assertNotIn("Jump through", answer)


class TheCalledGateHandlingIsWiredTest(unittest.TestCase):
    """`jumpToCalledGate` and `alignToCalledGate` need a whole
    `BotDecisionContext` to run, which is why they are read here rather than
    executed -- the same reason `test_route_stargate_panel_jump.py`'s
    `TheFallBackIsTheCascadeTest` reads `jumpThroughRouteStargate` instead of
    constructing a `BotDecisionContext` by hand. The two pure pieces they
    compose, `gateOverviewEntry` and `routeStargateJumpForNamedGate`, are
    executed for real above.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(WINGMAN_BOT_ELM)

    def test_both_refuse_a_gate_not_on_the_overview_rather_than_guessing(self):
        self.assertIn(
            "is not on the overview -- nothing to jump through.", self.source)
        self.assertIn(
            "is not on the overview -- nothing to align to.", self.source)

    def test_jump_reuses_the_two_pure_pieces_rather_than_a_new_rule(self):
        self.assertIn("gateOverviewEntry gateName", self.source)
        self.assertIn(
            "routeStargateJumpForNamedGate gateName", self.source)

    def test_align_opens_the_gate_s_own_menu_and_clicks_nothing(self):
        """The `openTheBroadcastsOwnMenu` pattern: aligning is not a cascade
        this repo has driven before and the client's own wording for it has
        never been read, so the next reading is what records it rather than a
        guess."""
        self.assertIn(
            "reading records what 'Align' offers.", self.source)
        self.assertIn(
            "useContextMenuCascadeOnOverviewEntry menuCascadeCompleted"
            " overviewEntry context", self.source)

    def test_the_broadcast_arms_call_the_new_functions(self):
        self.assertIn("(jumpToCalledGate context gate)", self.source)
        self.assertIn("(alignToCalledGate context gate)", self.source)

    def test_neither_arm_lost_its_permission_gate(self):
        # `JumpGate {` and `AlignGate {` also match the type definition and
        # `fleetBroadcastSender`, both above `actOnBroadcastVerb`'s own
        # definition -- start from the definition itself, not the first call
        # site, or the slice below catches those instead of the case arms.
        root = self.source[
            self.source.index("actOnBroadcastVerb context bannerText ="):]
        jump_arm = root[root.index("JumpGate {"):root.index("AlignGate {")]
        align_arm = root[root.index("AlignGate {"):]
        align_arm = align_arm[:align_arm.index("Unrecognized text ->")]
        for arm in (jump_arm, align_arm):
            self.assertIn("not(permittedpilot)", arm.replace(" ", ""))
            self.assertIn("follow-fleet-broadcast-from", arm)

    def test_no_third_escalation_rung_was_ported(self):
        """#347 is explicit: `jumpCascadeStuckReadings` -- the stuck-cascade
        counter warp-to-0 falls back to a surroundings-button cascade with --
        must not come along, because approximating it without the real
        `newJumpsCompleted`/`lastSolarSystemName` bookkeeping would misfire on
        exactly the case it protects against. `navigateTowardFleetCommander`'s
        own comment already names both terms to explain why *it* has only two
        rungs (#343); this checks the block #347 added rather than repeating
        that, since a comment mentioning a term is not the same as code using
        it.
        """
        block = self.source[
            self.source.index("gateOverviewEntry gateName readingFromGameClient ="):
            self.source.index("nextSystemOnRouteFromReading readingFromGameClient =")]
        self.assertNotIn("jumpCascadeStuckReadings", block)
        self.assertNotIn("newJumpsCompleted", block)
        self.assertNotIn("surroundings", block)
