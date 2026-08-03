"""Tests for the mission runner recognising that its ship has been destroyed.

Issue #33 listed four signals that were supposed to change together when a ship
dies. Two of them survived being checked against the recordings, and these cases
pin both the ones that did and the reason the others did not -- because the
tempting "fix" for a signal that never fires is to widen it back towards the
ones that do not work.

**What EVE actually says.** Not "your ship was destroyed": there is no such line
anywhere in `~/Documents/EVE/logs/Gamelogs`. Run 7's loss reads as the last
`(combat)` line at 04:26:59 and then, once the bot asks the capsule to lock:

    [ 2026.08.03 04:27:33 ] (notify) The ship you are piloting does not have targeting systems installed.

173 times, to the end of the run. That is the first signal, and it arrives on
`(notify)`, which the host carries -- unlike `(combat)`, where a destruction
line would almost certainly have been and where the bot would never have seen
it.

**The second signal is the ship UI carrying no module buttons at all**, which
needs no game log. Its discrimination is measured, not assumed: the mission
runner prints `Middle-row modules: none.` on all 724 of run 7's in-space status
prints and on **zero** across runs 1, 3, 5 and 8 -- 15,836 in-space prints over
4,419 readings, every one naming a propulsion module. (Prints, not readings: the
bot re-derives its decision several times per reading, which is the unit
CLAUDE.md keeps a section on. The ratio is what matters here.)

**The drones window is not used.** Run 1 printed `No drones` on 8,076 in-space
status prints while flying a perfectly good ship, so an absent drones window
says nothing about the hull.

The wording is the risk, so the wording is what is pinned: these cases read the
two substrings out of `Bot.elm` rather than restating them, for the reason
`test_ammo_load_refusal.py` does -- a matcher that drifts from what the client
writes fails in the direction that looks like success. No loss is ever
recognised, the guard never fires, and the bot goes back to flying a capsule
among the rats that killed it.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")
BOTLAB_HOST_PY = os.path.join(
    MACOS_HOST_DIR, "botlab_host", "botlab_host.py")

# Quoted verbatim from run 7's game log, where it appears 173 times.
CAPSULE_REFUSAL = (
    "The ship you are piloting does not have targeting systems installed.")

# Every other distinct (notify) line the client wrote during the recorded runs
# that mentions a ship, a target or a lock. None of them may read as a loss:
# each one is something a live ship says while flying perfectly well.
OTHER_NOTIFY_LINES = [
    "You cannot load or unload Focused Modulated Medium Energy Beam I "
    "while it is active.",
    "You cannot launch Acolyte I because you are already controlling 5 drones, "
    "as much as you have skill to.",
    "You cannot do that while warping.",
    "You cannot do that while docking.",
    "You cannot activate that module as the target is no longer present.",
    "You are already managing 6 targets, as many as you have skill to.",
    "Target lock unsuccessful.",
    "Targeting attempt failed as the designated object is no longer present.",
    "To give this command to a drone requires that you have an active target. "
    "Target something and try again.",
    "The drones fail to execute your commands as the target Mission Generic "
    "Frigates is not within your 60000.0 m drone command range.",
    "External factors are preventing your Tracking Computer II from responding "
    "to this command",
    "Your docking request has been accepted. Your ship will be towed into "
    "station.",
    "Cargo is too far away. Ship is on automatic approach to cargo.",
    "Setting course to docking perimeter",
]


def ship_loss_substrings():
    """The substrings `shipLossFromGameLog` actually matches on.

    Read out of the Elm rather than restated, so that changing the matcher
    without checking it against real lines fails here.
    """
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
        source = bot_elm.read()
    start = source.index("shipLossFromGameLog : ReadingFromGameClient")
    end = source.index("shipUIHasNoModuleButtons :", start)
    return re.findall(r'stringContainsIgnoringCase "([^"]+)"', source[start:end])


def matches(text, substrings):
    """What `shipLossFromGameLog`'s filter does, on one line of text."""
    return all(sub.lower() in text.lower() for sub in substrings)


def withheld_channels():
    """The channels the host keeps from the bot, read out of the host."""
    with open(BOTLAB_HOST_PY, encoding="utf-8") as host_py:
        source = host_py.read()
    line = re.search(
        r"GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT = frozenset\(\{([^}]*)\}\)",
        source)
    return set(re.findall(r'"([^"]+)"', line.group(1)))


class MatcherIsReadFromTheElm(unittest.TestCase):
    def test_two_substrings_are_found(self):
        # Two, not one. "targeting systems" alone would also match a rewording
        # about a *module*; the pair ties the subject to the symptom.
        self.assertEqual(
            len(ship_loss_substrings()), 2,
            "expected shipLossFromGameLog to match on two substrings")


class MatchesTheRealCapsuleRefusal(unittest.TestCase):
    def setUp(self):
        self.substrings = ship_loss_substrings()

    def test_matches_the_line_from_run_7(self):
        self.assertTrue(matches(CAPSULE_REFUSAL, self.substrings))

    def test_matches_regardless_of_case(self):
        self.assertTrue(matches(CAPSULE_REFUSAL.upper(), self.substrings))

    def test_does_not_match_the_client_s_other_notify_lines(self):
        for line in OTHER_NOTIFY_LINES:
            self.assertFalse(
                matches(line, self.substrings),
                "would have declared the ship lost on: " + line)

    def test_does_not_match_a_module_that_lacks_a_target(self):
        # The nearest miss to guard: a sentence about a module rather than
        # about the hull. Docking the ship over one of these would end a
        # healthy session.
        self.assertFalse(matches(
            "That module does not have targeting systems installed.",
            self.substrings))


class TheChannelIsOneTheBotIsGiven(unittest.TestCase):
    """The signal is worthless if the host filters the channel it arrives on.

    `(combat)` and `(bounty)` are withheld, and a destruction announcement --
    had one existed -- would almost certainly have been on `(combat)`. What the
    client actually writes is on `(notify)`, which is carried.
    """

    def test_notify_is_not_withheld(self):
        self.assertNotIn("notify", withheld_channels())

    def test_combat_and_bounty_are_still_the_withheld_ones(self):
        # Pinned so that widening the deny-list later fails here rather than
        # silently blinding this guard.
        self.assertEqual(withheld_channels(), {"combat", "bounty"})

    def test_the_bot_checks_for_the_notify_channel(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
            source = bot_elm.read()
        start = source.index("shipLossFromGameLog : ReadingFromGameClient")
        end = source.index("shipUIHasNoModuleButtons :", start)
        self.assertIn("gameLogEntryIsFromNotifyChannel", source[start:end])


class TheBotDoesNotWaitForAnAnnouncementThatDoesNotExist(unittest.TestCase):
    """EVE never states the loss outright, and the code must not look for it.

    This is the finding that cost the most to establish and is the easiest to
    undo by accident: issue #33 asserted that "EVE's own game log states it
    outright", and a later reader who believes that will reach for a phrase the
    client never writes. A matcher looking for one would never fire, which is
    the failure mode that looks exactly like nothing having gone wrong.
    """

    PHRASES_THE_CLIENT_NEVER_WRITES = [
        "has been destroyed",
        "your ship was destroyed",
        "you have been podded",
        "ship destroyed",
    ]

    def test_the_matcher_does_not_look_for_a_destruction_announcement(self):
        substrings = ship_loss_substrings()
        for phrase in self.PHRASES_THE_CLIENT_NEVER_WRITES:
            for substring in substrings:
                self.assertNotIn(phrase, substring.lower())

    def test_no_recorded_game_log_contains_one(self):
        pattern = os.path.expanduser(
            "~/Documents/EVE/logs/Gamelogs/*.txt")
        paths = sorted(glob.glob(pattern))
        if not paths:
            self.skipTest("no recorded game logs on this machine")
        found = []
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as game_log:
                for line in game_log:
                    lowered = line.lower()
                    for phrase in self.PHRASES_THE_CLIENT_NEVER_WRITES:
                        # "criminals are not welcome here, leave now or be
                        # destroyed" is a faction-police warning to somebody
                        # else and is not about our hull.
                        if phrase in lowered and "or be destroyed" not in lowered:
                            found.append(line.strip())
        self.assertEqual(found, [], "the client does state a loss after all")


class TheSecondSignalIsNotUsedAloneWhereItCannotDiscriminate(unittest.TestCase):
    """Bounds and choices in the Elm that the recordings decided.

    Read out of `Bot.elm` rather than restated, so that retuning them without
    revisiting the evidence fails here.
    """

    def bot_source(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
            return bot_elm.read()

    def test_the_module_signal_needs_more_than_one_reading(self):
        # The parser drops a slot whose display region it cannot read, so one
        # reading finding no modules is a parse that may have missed. Three in a
        # row is the ship's shape having changed.
        match = re.search(
            r"shipLossReadingsWithoutModulesBeforeVerdict : Int\s*\n"
            r"shipLossReadingsWithoutModulesBeforeVerdict =\s*\n\s*(\d+)",
            self.bot_source())
        self.assertIsNotNone(match)
        self.assertGreater(int(match.group(1)), 1)

    def test_the_drones_window_is_not_a_signal(self):
        # Run 1 flew a live ship for 8,076 in-space readings with no drones
        # window. Anything keying a loss verdict off `dronesWindow` would have
        # docked that run over and over.
        source = self.bot_source()
        start = source.index("shipUIHasNoModuleButtons : ReadingFromGameClient")
        end = source.index("shipUIWithoutModuleButtonsReadingsAfter :", start)
        self.assertNotIn("dronesWindow", source[start:end])

    def test_hitpoints_are_not_a_signal(self):
        # A capsule reads 100% shield and 100% armour. That is the reassuring
        # and meaningless line that hid this failure for a whole run, and it is
        # also the reading #32 found to be untrustworthy in its own right.
        source = self.bot_source()
        start = source.index("shipLossFromGameLog : ReadingFromGameClient")
        end = source.index("shipLossVerdictAfter :", start)
        self.assertNotIn("hitpointsPercent", source[start:end])

    def test_the_pod_recovery_is_bounded(self):
        match = re.search(
            r"podRecoveryGiveUpReadings : Int\s*\n"
            r"podRecoveryGiveUpReadings =\s*\n\s*(\d+)",
            self.bot_source())
        self.assertIsNotNone(match, "the pod recovery must have an end")
        self.assertGreater(int(match.group(1)), 0)


class TheVerdictIsLatchedInMemory(unittest.TestCase):
    """A reading's game log entries are gone by the next reading.

    So the branch that acts on the loss cannot be the branch that sees it. If
    the verdict were not written in `updateMemoryForNewReadingFromGame` -- the
    only place that can write memory -- the bot would notice the loss once and
    then behave exactly as run 7 did.
    """

    def bot_source(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
            return bot_elm.read()

    def test_the_memory_update_writes_the_verdict(self):
        source = self.bot_source()
        start = source.index(
            "updateMemoryForNewReadingFromGame : UpdateMemoryContext")
        self.assertIn("shipLossVerdictAfter", source[start:])

    def test_the_decision_reads_it_from_memory_and_not_from_the_reading(self):
        source = self.bot_source()
        start = source.index("recoverPodAfterShipLoss : BotDecisionContext")
        end = source.index("-- Reading the mission's state", start)
        branch = source[start:end]
        self.assertIn("context.memory.shipLoss", branch)
        self.assertNotIn("shipLossFromGameLog", branch)

    def test_the_verdict_is_never_cleared(self):
        # Latched on purpose: docking early costs the session, and un-latching
        # on a reading that happens to look normal costs the clone.
        source = self.bot_source()
        start = source.index("shipLossVerdictAfter :")
        end = source.index("recoverPodAfterShipLoss :", start)
        body = source[start:end]
        self.assertIn("Just latched ->", body)
        # The already-latched arm must not be able to answer Nothing.
        latched_arm = body[body.index("Just latched ->"):body.index("Nothing ->")]
        self.assertNotIn("Nothing", latched_arm)


class TheResponseReusesTheHomeStationPath(unittest.TestCase):
    """#16 already built route-set, travel and dock. There must not be a second.

    Both callers go through `travelToStationByName`, so a fix to the travel
    sequence cannot land in one and miss the other.
    """

    def bot_source(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
            return bot_elm.read()

    def test_both_the_restock_trip_and_the_pod_recovery_use_it(self):
        source = self.bot_source()
        callers = []
        for name in ("goToHomeStationWhileInSpace", "recoverPodAfterShipLoss"):
            start = source.index(name + " : BotDecisionContext")
            end = source.index("\n\n\n", start)
            if "travelToStationByName" in source[start:end]:
                callers.append(name)
        self.assertEqual(
            sorted(callers),
            ["goToHomeStationWhileInSpace", "recoverPodAfterShipLoss"])

    def test_the_missing_home_station_case_is_handled(self):
        # `home-station` is unset by default, so this is the common case, not
        # the exotic one. It must not be a route to nowhere.
        source = self.bot_source()
        start = source.index("recoverPodAfterShipLoss : BotDecisionContext")
        end = source.index("-- Reading the mission's state", start)
        branch = source[start:end]
        self.assertIn("homeStationName", branch)
        self.assertIn("dockAtStation", branch)

    def test_the_session_ends_rather_than_running_out_the_clock(self):
        source = self.bot_source()
        start = source.index("recoverPodAfterShipLoss : BotDecisionContext")
        end = source.index("-- Reading the mission's state", start)
        self.assertIn("FinishSession", source[start:end])


class AgainstTheRecordedRuns(unittest.TestCase):
    """The same checks against whatever the recorded runs actually hold.

    Skipped when those logs are absent, since they are not in the repository --
    the same shape as the recorded-runs cases in `test_game_log_channel.py`.
    """

    def notify_lines(self):
        lines = []
        pattern = os.path.expanduser("~/eve-bot-logs/mission_run*.log")
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    if "(notify)" in line:
                        lines.append(line.split("(notify)", 1)[1].strip())
        return lines

    def test_the_capsule_refusal_reached_the_bot_s_reading(self):
        # Not merely present in the client's own log: run 7 was recorded after
        # #30 landed, so the host echoed each entry it handed the bot as a
        # `#   game log:` line. That is the evidence this signal is readable.
        pattern = os.path.expanduser("~/eve-bot-logs/mission_run*.log")
        paths = sorted(glob.glob(pattern))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        carried = 0
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    if "game log:" in line and matches(
                            line, ship_loss_substrings()):
                        carried += 1
        self.assertGreater(
            carried, 0,
            "no recorded run shows the capsule refusal reaching the reading")

    def test_matcher_selects_only_the_capsule_refusal(self):
        lines = self.notify_lines()
        if not lines:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        substrings = ship_loss_substrings()
        for line in set(lines):
            expected = "does not have targeting systems" in line
            self.assertEqual(
                matches(line, substrings), expected,
                "matcher disagreed about: " + line)

    def test_the_module_row_discriminates_between_the_capsule_and_real_ships(self):
        # The second signal's whole justification. `Middle-row modules: none.`
        # is the printed consequence of a ship UI with no modules, and it
        # separates run 7 from every run flying a real ship.
        pattern = os.path.expanduser("~/eve-bot-logs/mission_run*.log")
        paths = sorted(glob.glob(pattern))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        empty_rows = {}
        in_space = {}
        for path in paths:
            run = os.path.basename(path)
            with open(path, encoding="utf-8", errors="replace") as log:
                text = log.read()
            empty_rows[run] = text.count("Middle-row modules: none.")
            in_space[run] = (text.count("Middle-row modules: none.")
                             + text.count("Middle-row modules: prop mod"))
        capsule_runs = [run for run, count in empty_rows.items() if count > 0]
        if not capsule_runs:
            self.skipTest("no recorded run flew a capsule")
        for run, count in empty_rows.items():
            if run in capsule_runs:
                continue
            self.assertEqual(
                count, 0,
                "a run flying a real ship reported an empty module row: " + run)
            self.assertGreater(
                in_space[run], 0,
                "expected in-space readings to compare against: " + run)


if __name__ == "__main__":
    unittest.main()
