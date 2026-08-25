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

    def test_the_trip_home_says_it_is_unfinished_rather_than_doing_nothing(self):
        """Answering `Nothing` would read as "nothing to do" and fly past the
        session's end in silence."""
        self.assertIn("is not implemented yet.", self.source)


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
