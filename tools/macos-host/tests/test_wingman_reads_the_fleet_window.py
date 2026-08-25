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
