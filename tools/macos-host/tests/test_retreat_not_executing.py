"""The bot commanded a warp and never noticed that none of them had worked.

Issue #141. PR #139 shipped `retreatProgressAfterReading` -- consecutive readings
on which the retreat is decided and the ship is not in warp -- and **nothing read
it**. This wires a bound to it: on the reading the interval reaches
`retreatNotExecutingAlarmReadings` the bot says so once, at the root, in a line
carrying the sentence `stall_watch.py` answers by screenshotting the client. It
does not touch the retreat, and it does not claim to know why the warp did not
take.

Six things this file establishes, all against recorded data or executed code.

**The corpus, recounted in readings.** #139 measured in decision blocks because
"the logs carry no per-reading identity at all". There is one: the framework
issues exactly one `RequestToVolatileProcess` memory read per reading, and run 36
carries a second and independent per-reading counter of its own. A case asserts
the two agree, which is what makes every number below a reading rather than a
block.

**Run 36 is not an outlier and its warp did take.** Its episode is the same length
as run 10's, in a run nobody had looked at; its overview emptied and its escape
target closed while the armour recovered; and the 1% armour the issue reports is
one reading with **both** gauges at 1%, taken off the grid, bracketed by 37%.
Those are asserted as relations against the log.

**The bound is placed where the measurement puts it and written as a relation.**
`runAwayCelestialStickyReadings * 3` -- three rotations of the escape choice --
lands above every recorded episode but the two longest, which is the only gap the
upper tail has. A case pins that placement, so a corpus that grows into the gap
turns it red.

**The alarm fires once per interval.** Executed through the real `Bot.elm` at both
sides of the crossing, at fixed values either side of the boundary pair, and
folded over whole sessions including a second episode.

**The sentence the watchdog matches is one string in three places** -- `Bot.elm`,
the vendored framework and `stall_watch.py` -- and a drift is silent in the
direction that looks like a healthy run. A case reads all three.

**Nothing decides on it and the retreat did not change.** The drone recall still
sits in front of the warp, `droneRecallGiveUpTicks` is still 60, and #120's
gauge-free property is re-asserted because this change sits on top of it.

Cases that execute Elm need the toolchain and **fail** without it; cases that read
`~/eve-bot-logs` skip, with the wording the neighbouring file already uses.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs
from test_retreat_latency import (
    DECISION,
    RATS,
    VERDICT_LINE,
    WARP_LINE,
    bot_source,
    collapsed,
    constant_in_source,
    definition_body,
    definitions_mentioning,
    every_recorded_run,
)

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
FRAMEWORK_ELM = os.path.join(
    MISSION_RUNNER_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm")
STALL_WATCH = os.path.join(MACOS_HOST_DIR, "stall_watch.py")

# The framework issues exactly one memory read per reading from the game, and
# every decision the bot prints between two of them belongs to the reading the
# first one produced. That is the per-reading identity #139 says the logs do not
# have -- it is not in a decision line, which is where it was looked for.
# `TheUnitIsTheReading` checks it against run 36's own independent counter.
MEMORY_READ = re.compile(r"^#\s+task read-from-game-\d+: RequestToVolatileProcess")

# Run 36's own per-reading counter, and the only one any recorded run carries:
# the ammo swap prints how many readings ago it gave up, and that number advances
# once per reading in the memory update.
READINGS_AGO = re.compile(r"given up (\d+) readings ago")

HITPOINTS = re.compile(r"^Shield: (-?\d+)%\s+Armor: (-?\d+)%\.")

# The two halves of `selectThenPanelAction`, as the decision log spells them: the
# panel is not showing the row yet, against the panel button being pressed.
SELECTING = "(selecting it first)"


def readings_in(path):
    """One record per reading from the game, with what the bot decided on it."""
    out = []
    current = None
    with open(path, encoding="utf-8", errors="replace") as log:
        lines = log.readlines()
    for line in lines:
        if MEMORY_READ.match(line):
            if current is not None:
                out.append(current)
            current = {"verdict": False, "rats": None, "armor": None,
                       "warpCommands": 0, "selecting": 0, "readingsAgo": None}
            continue
        if current is None:
            continue
        decision = DECISION.match(line.rstrip("\n"))
        if decision is not None:
            text = decision.group(2)
            if VERDICT_LINE.match(text):
                current["verdict"] = True
            if text.startswith(WARP_LINE):
                current["warpCommands"] += 1
                if text.endswith(SELECTING):
                    current["selecting"] += 1
            continue
        rats = RATS.match(line)
        if rats is not None:
            current["rats"] = int(rats.group(1))
            continue
        hitpoints = HITPOINTS.match(line)
        if hitpoints is not None:
            current["armor"] = int(hitpoints.group(2))
            continue
        counter = READINGS_AGO.search(line)
        if counter is not None:
            current["readingsAgo"] = int(counter.group(1))
    if current is not None:
        out.append(current)
    return out


def retreat_episodes_in_readings(path):
    """Each retreat, as the readings it spent on the grid after a verdict.

    The same episode definition #139's block measurement uses -- from the first
    verdict until hostiles leave the overview -- in the unit the bot's own counter
    is in. The end is a proxy because the log cannot say the ship is warping: the
    retreat short-circuits the branch that prints `I am in warp`, so during a
    decided retreat that line never appears.
    """
    readings = readings_in(path)
    episodes = []
    index = 0
    while index < len(readings):
        if not readings[index]["verdict"]:
            index += 1
            continue
        spent = 0
        cursor = index
        while cursor < len(readings) and readings[cursor]["verdict"]:
            spent += 1
            if readings[cursor]["rats"] == 0:
                break
            cursor += 1
        episodes.append(spent)
        while cursor < len(readings) and readings[cursor]["verdict"]:
            cursor += 1
        index = cursor
    return episodes


def every_recorded_episode():
    return sorted(episode
                  for path in every_recorded_run()
                  for episode in retreat_episodes_in_readings(path))


class RetreatAlarmRepl(ElmRepl):
    """The shared harness, plus builders for the alarm and for whole sessions."""

    BINDINGS = [
        "alarm before now ="
        " retreatNotExecutingAlarm"
        " { unexecutedReadingsBefore = before, unexecutedReadings = now }",
        "fired before now = alarm before now /= Nothing",
        "start = { unexecutedReadings = 0, longestUnexecutedReadings = 0 }",
        "onReading ( decided, warping ) ( progress, said ) ="
        " (\\after -> ( after, said + (alarm progress.unexecutedReadings"
        " after.unexecutedReadings |> Maybe.map (always 1)"
        " |> Maybe.withDefault 0) ))"
        " (retreatProgressAfterReading"
        " { retreatIsDecided = decided, shipIsWarping = warping, before = progress })",
        "alarms readings = List.foldl onReading ( start, 0 ) readings |> Tuple.second",
        "clause now worst ="
        " describeRetreatLatencyFromProgress"
        " { unexecutedReadings = now, longestUnexecutedReadings = worst }",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preamble = self.preamble + self.BINDINGS


class TheAlarmFiresOncePerInterval(unittest.TestCase):
    """`retreatNotExecutingAlarm`, run through the bot's own compiled code."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RetreatAlarmRepl, prefix="test-retreat-alarm-")
        cls.source = bot_source()
        cls.bound = constant_in_source(cls.source, "runAwayCelestialStickyReadings") * 3

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_alarm_fires_on_the_reading_the_bound_is_crossed(self):
        # The boundary pair, plus fixed values either side of it -- a boundary
        # pair alone passes for any constant, which is the hole #129 found in
        # four of #120's cases and #139 wrote down again.
        answers = self.repl.evaluate([
            "fired %d %d" % (self.bound - 1, self.bound),
            "not (fired %d %d)" % (self.bound - 2, self.bound - 1),
            "not (fired 0 1)",
            "not (fired 0 0)",
            "fired 0 %d" % (self.bound + 40),
        ])
        self.assertEqual(answers, [True, True, True, True, True],
                         "the alarm must fire exactly where the interval "
                         "reaches the bound, and nowhere below it")

    def test_the_alarm_does_not_repeat_once_the_interval_is_past_the_bound(self):
        # A line per reading for the rest of the episode is what run 30's message
        # box gave an operator 32,585 times, and it is what defeats the
        # watchdog's own dedupe. The status line carries the count instead.
        answers = self.repl.evaluate([
            "not (fired %d %d)" % (self.bound, self.bound + 1),
            "not (fired %d %d)" % (self.bound + 50, self.bound + 51),
            "not (fired %d %d)" % (self.bound + 1, self.bound + 2),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_a_retreat_that_executes_promptly_says_nothing(self):
        # Nineteen of the corpus's twenty-nine episodes are four readings or
        # fewer. None of them may produce a line.
        session = "List.repeat 4 ( True, False ) ++ List.repeat 100 ( True, True )"
        answers = self.repl.evaluate([
            "alarms (%s) == 0" % session,
            "alarms (List.repeat 400 ( False, False )) == 0",
        ])
        self.assertEqual(answers, [True, True])

    def test_a_retreat_at_the_worst_recorded_length_that_recovers_says_nothing(self):
        # Run 31's 28-reading retreat is the longest recorded episode *below* the
        # bound, and it recovered. The bound is above it deliberately, so a
        # session of that shape must stay silent.
        episodes = every_recorded_episode()
        below = [episode for episode in episodes if episode < self.bound]
        longest_below = max(below)
        session = ("List.repeat %d ( True, False ) ++ List.repeat 50 ( True, True )"
                   % longest_below)
        answers = self.repl.evaluate(["alarms (%s) == 0" % session])
        self.assertEqual(
            answers, [True],
            "the longest recorded retreat below the bound is %d readings and it "
            "must not raise the alarm" % longest_below)

    def test_run_36_s_own_shape_raises_it_once(self):
        # Forty readings on the grid, then the warp that did take, then the
        # hysteresis carrying the latched verdict home. One line, not two, and
        # none of it from the readings spent in warp.
        session = ("List.repeat 40 ( True, False ) ++ "
                   "List.repeat 43 ( True, True )")
        answers = self.repl.evaluate(["alarms (%s) == 1" % session])
        self.assertEqual(answers, [True])

    def test_a_second_interval_that_reaches_the_bound_says_so_again(self):
        # Warping to a celestial that turns out to be no safer starts a fresh
        # interval, and the second one is a second thing worth telling a person.
        session = ("List.repeat %d ( True, False ) ++ "
                   "List.repeat 10 ( True, True ) ++ "
                   "List.repeat %d ( True, False )" % (self.bound, self.bound))
        answers = self.repl.evaluate(["alarms (%s) == 2" % session])
        self.assertEqual(answers, [True])

    def test_an_interval_broken_before_the_bound_never_reaches_it(self):
        # `retreatProgressAfterReading` resets on any reading that is not a
        # retreat, including one with no ship UI. Stated rather than hidden: a
        # single unparsed reading inside a long retreat delays the alarm by the
        # whole interval, and #139 chose that reset.
        session = ("List.repeat %d ( True, False ) ++ "
                   "[ ( False, False ) ] ++ "
                   "List.repeat %d ( True, False )"
                   % (self.bound - 1, self.bound - 1))
        answers = self.repl.evaluate(["alarms (%s) == 0" % session])
        self.assertEqual(answers, [True])

    def test_the_line_says_what_it_counted_and_asks_for_a_person(self):
        [line] = self.repl.strings(["describeRetreatNotExecuting 42"])
        self.assertIn("42", line, "the line must carry the count")
        self.assertIn("readings, not decisions", line,
                      "the line must say which of this file's two units the "
                      "count is in")
        self.assertIn("do not know why", line,
                      "the line must not claim to know why the warp did not take")
        self.assertIn("still commanding it", line,
                      "the line must say the retreat has not stopped, or a "
                      "reader assumes the bot gave up")
        self.assertNotIn("\n", line, "the decision log is line-structured")

    def test_the_status_line_shows_the_count_against_the_bound(self):
        # #101's lesson: run 30's operator watched a counter climb with no way
        # to see what it was climbing towards. Executed rather than read out of
        # the source, because a mutation that dropped the bound from the count
        # while leaving it in the sentence below survived the source read.
        quiet, climbing, past, over = self.repl.strings([
            "clause 0 0",
            "clause %d %d" % (self.bound - 1, self.bound - 1),
            "clause %d %d" % (self.bound, self.bound),
            "clause 0 %d" % self.bound,
        ])
        self.assertEqual(quiet, "",
                         "a session that never retreated says nothing")
        self.assertIn("%d of %d" % (self.bound - 1, self.bound), climbing,
                      "the live count must be printed against the bound")
        self.assertNotIn("person has been asked for", climbing,
                         "and must not claim an alarm that has not fired")
        self.assertIn("%d of %d" % (self.bound, self.bound), past)
        self.assertIn("person has been asked for", past,
                      "past the bound the clause must say the alarm went out")
        self.assertIn("worst this session", over,
                      "a retreat that ended still reports the session's worst")


class TheWatchdogSentenceIsOneString(unittest.TestCase):
    """One literal in three places, across two languages, pinned by a case."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RetreatAlarmRepl, prefix="test-retreat-alarm-text-")
        cls.source = bot_source()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    @staticmethod
    def _framework_sentence():
        with open(FRAMEWORK_ELM, encoding="utf-8") as handle:
            body = collapsed(definition_body(handle.read(), "askForHelpToGetUnstuck"))
        found = re.search(r'describeBranch "([^"]*)"', body)
        assert found is not None, "no sentence in askForHelpToGetUnstuck"
        return found.group(1)

    @staticmethod
    def _watchdog_sentence():
        with open(STALL_WATCH, encoding="utf-8") as handle:
            found = re.search(r'^STUCK_TEXT = "([^"]*)"', handle.read(), re.M)
        assert found is not None, "no STUCK_TEXT in stall_watch.py"
        return found.group(1)

    def test_the_three_copies_are_the_same_sentence(self):
        [ours] = self.repl.strings(["askForHelpToGetUnstuckText"])
        self.assertEqual(
            ours, self._framework_sentence(),
            "Bot.elm's copy has drifted from the framework's, so the bot would "
            "print a sentence the watchdog does not recognise")
        self.assertEqual(
            ours, self._watchdog_sentence(),
            "stall_watch.py matches STUCK_TEXT as a substring of a log line; a "
            "drift here means the alarm prints and nothing escalates")

    def test_the_alarm_line_carries_it(self):
        [line] = self.repl.strings(["describeRetreatNotExecuting 99"])
        self.assertIn(
            self._watchdog_sentence(), line,
            "the whole escalation is that a person is fetched, and the watchdog "
            "is what fetches them")

    def test_the_alarm_does_not_branch_to_the_leaf_that_stops_acting(self):
        # `askForHelpToGetUnstuck` dispatches no effects. Taking it would stop
        # the retreat commanding the warp, which is the one thing that must not
        # happen while the ship is still in the pocket.
        for name in ("describeRetreatNotExecuting", "retreatNotExecutingAlarm",
                     "missionBotDecisionRoot"):
            body = definition_body(self.source, name)
            self.assertNotIn(
                "askForHelpToGetUnstuck ", body,
                "%s must carry the sentence, not branch to the leaf" % name)


class TheBoundIsPlacedInTheMeasurement(unittest.TestCase):
    """Where the number comes from, and what it is written as."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()
        cls.flat = collapsed(cls.source)

    def test_the_bound_is_a_relation_to_the_rotation_rather_than_a_bare_number(self):
        # `missionStalledReadingsBeforeAbandoning`'s form: a multiple of the
        # thing it is about, so the argument cannot drift away from the number.
        # Three rotations of the escape choice is the point at which the only
        # self-correction the retreat owns has been spent on three destinations.
        body = collapsed(definition_body(self.source, "retreatNotExecutingAlarmReadings"))
        self.assertIn(
            "runAwayCelestialStickyReadings * 3", body,
            "the bound must be written as three rotations of the escape choice, "
            "not as a bare number; found %r" % (body,))
        self.assertEqual(constant_in_source(self.source,
                                            "runAwayCelestialStickyReadings"), 12)

    def test_the_bound_sits_above_every_recorded_retreat_but_the_longest(self):
        # #109's method: placed in a gap rather than cut through a distribution.
        # The gap here is the only one the upper tail has, and it is narrow --
        # which is the finding, not a defect in the placement. A corpus that
        # grows into it turns this red, and that is what it is for.
        episodes = every_recorded_episode()
        bound = constant_in_source(self.source, "runAwayCelestialStickyReadings") * 3
        self.assertGreater(len(episodes), 5,
                           "the corpus must hold enough retreats for a "
                           "placement to mean anything")
        below = [episode for episode in episodes if episode < bound]
        at_or_above = [episode for episode in episodes if episode >= bound]
        self.assertTrue(
            at_or_above,
            "no recorded retreat reaches the bound of %d, so the alarm has "
            "never had anything to fire on and is untethered from the corpus; "
            "episodes were %r" % (bound, episodes))
        self.assertLessEqual(
            len(at_or_above), 3,
            "the bound of %d catches %d of %d recorded retreats. It is meant to "
            "catch the incident's shape and not the ordinary case; episodes "
            "were %r" % (bound, len(at_or_above), len(episodes), episodes))
        self.assertGreater(
            bound, max(below),
            "the bound must be above the longest recorded retreat that stayed "
            "below it, or it cuts the distribution instead of sitting in its "
            "gap; episodes were %r" % (episodes,))

    def test_a_retreat_that_works_is_far_shorter_than_the_bound(self):
        # The relation the whole placement rests on: the manoeuvre takes a
        # handful of readings when it works, and everything long is a retry.
        episodes = every_recorded_episode()
        bound = constant_in_source(self.source, "runAwayCelestialStickyReadings") * 3
        median = episodes[len(episodes) // 2]
        self.assertLess(
            median * 5, bound,
            "the median recorded retreat is %d readings against a bound of %d; "
            "if those come close together the bound is no longer distinguishing "
            "a retry from an ordinary retreat" % (median, bound))


class TheUnitIsTheReading(unittest.TestCase):
    """Why every number above is a reading, when #139's were blocks.

    #139 measured in decision blocks and said why: "the logs carry no per-reading
    identity at all". It is not in a decision line, which is where it was looked
    for -- it is in the framework's own task log, one memory read per reading.
    These cases are what makes that claim checkable rather than asserted.
    """

    def test_the_memory_read_agrees_with_run_36_s_own_reading_counter(self):
        # Run 36 carries an independent per-reading counter -- the ammo swap's
        # `given up N readings ago`, advanced in the memory update -- so the two
        # can be compared over the same stretch. They must agree closely; a
        # segmentation that drifts would put every episode length above in the
        # wrong unit.
        for _, path in recorded_runs("36"):
            readings = readings_in(path)
            counted = [reading["readingsAgo"] for reading in readings
                       if reading["readingsAgo"] is not None]
            self.assertGreater(len(counted), 100,
                               "run 36 must carry its own counter to compare "
                               "against")
            spanned = max(counted) - min(counted) + 1
            segmented = len(counted)
            self.assertLess(
                abs(segmented - spanned) * 20, spanned,
                "the memory read segments run 36 into %d readings where the "
                "run's own counter spans %d, so one of the two is not a reading"
                % (segmented, spanned))

    def test_the_bots_own_counter_would_have_been_the_unit_if_a_run_carried_it(self):
        # And the point of #139: none does. The first run that retreats replaces
        # every proxy in this file with the bot's own number, and this is what
        # notices it arriving.
        carrying = []
        for path in every_recorded_run():
            with open(path, encoding="utf-8", errors="replace") as log:
                if any("RETREAT NOT EXECUTING" in line for line in log):
                    carrying.append(os.path.basename(path))
        self.assertEqual(
            carrying, [],
            "%r already carry the retreat-latency clause, so the episode "
            "lengths here can be read off the bot rather than reconstructed"
            % (carrying,))


class WhatRun36ActuallyDid(unittest.TestCase):
    """The corrections the reading-based recount makes to the issue's premise.

    Asserted as relations against run 36's own log rather than as the numbers in
    the doc comment, so a re-reading cannot turn a true claim red.
    """

    def test_run_36_is_not_the_only_retreat_of_its_length(self):
        # The issue calls it an outlier by twenty times, off a block count. In
        # readings run 10's is the same length, in a run nobody had looked at --
        # which is why the bound cannot be placed to catch one and not the other.
        longest = {}
        for path in every_recorded_run():
            episodes = retreat_episodes_in_readings(path)
            if episodes:
                longest[os.path.basename(path)] = max(episodes)
        if "mission_run36.log" not in longest:
            self.skipTest("no recorded mission_run36.log")
        worst = max(longest.values())
        near = [name for name, value in longest.items() if value * 5 >= worst * 4]
        self.assertGreater(
            len(near), 1,
            "run 36's retreat is the only one within a fifth of the worst "
            "recorded length, so it really is an outlier and the bound could "
            "have been placed to catch it alone; lengths were %r" % (longest,))

    def test_most_of_run_36_s_warp_commands_were_issued_after_the_grid_emptied(self):
        # The issue's 296 are two different things. The hysteresis keeps the
        # verdict latched after the ship is clear and `runAwayIfLowHealth`
        # short-circuits the branch that would otherwise print `I am in warp`,
        # so the retreat goes on commanding a warp at a ship already in one.
        for _, path in recorded_runs("36"):
            on_grid = off_grid = 0
            for reading in readings_in(path):
                if not reading["warpCommands"]:
                    continue
                if reading["rats"]:
                    on_grid += reading["warpCommands"]
                else:
                    off_grid += reading["warpCommands"]
            self.assertGreater(on_grid, 0, "run 36 must hold the failure itself")
            self.assertGreater(
                off_grid, on_grid,
                "run 36 issued %d warp commands with something on the overview "
                "and %d after it had emptied; the issue's 296 is the sum of the "
                "two and only the first is the failure" % (on_grid, off_grid))

    def test_the_selection_half_of_the_manoeuvre_stalls_as_well(self):
        # This is what decides that a context-menu cascade is not an escalation:
        # it begins with a click on the same overview row, which is the half the
        # log says stalls at least as often as the panel button.
        for _, path in recorded_runs("36"):
            commands = selecting = 0
            for reading in readings_in(path):
                commands += reading["warpCommands"]
                selecting += reading["selecting"]
            self.assertGreater(commands, 100)
            self.assertGreater(
                selecting * 3, commands,
                "only %d of run 36's %d warp blocks are the selection half. If "
                "the panel press were the whole failure, a different mechanism "
                "for pressing it would be worth trying" % (selecting, commands))

    def test_the_one_percent_armour_is_one_reading_taken_off_the_grid(self):
        # The issue reports the ship reaching 1%. Both gauges read 1% on that
        # reading, it is taken with nothing on the overview, and the readings
        # either side are far higher -- the single-reading corruption #120
        # exists because of, which the retreat's own `believed` value rejects
        # and the status line prints raw.
        for _, path in recorded_runs("36"):
            readings = readings_in(path)
            armour = [reading["armor"] for reading in readings]
            lows = [index for index, value in enumerate(armour)
                    if value is not None and value <= 5]
            self.assertTrue(lows, "run 36 must carry the reading the issue quotes")
            for index in lows:
                self.assertEqual(
                    readings[index]["rats"], 0,
                    "the 1%% armour reading at %d was taken with something still "
                    "on the overview, which would make it a real value" % index)
                neighbours = [armour[other]
                              for other in (index - 1, index + 1)
                              if 0 <= other < len(armour)
                              and armour[other] is not None]
                self.assertTrue(
                    any(value > 20 for value in neighbours),
                    "the 1%% armour reading at %d is not bracketed by healthy "
                    "ones, so it may be a real decline after all" % index)


class NothingDecidesOnIt(unittest.TestCase):
    """#135's precedent, kept: a rule read by a report and by no decision."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()
        cls.flat = collapsed(cls.source)

    def test_the_alarm_is_said_at_the_root_where_nothing_can_decline_to_ask_it(self):
        # #102's placement rule, and the reason it applies here: a message-box
        # standoff above the docked-or-in-space split can hold the tree off
        # `runAwayIfLowHealth` entirely, and a held tree is one of the ways a
        # retreat comes to be this long in the first place.
        root = collapsed(definition_body(self.source, "missionBotDecisionRoot"))
        self.assertIn("context.memory.retreatNotExecutingLastChange", root,
                      "the alarm must be folded in at the root")
        self.assertIn("List.foldr describeBranch", root,
                      "and by the same mechanism as every other verdict the "
                      "memory update settles")

    def test_the_verdict_is_settled_in_the_memory_update(self):
        update = collapsed(definition_body(
            self.source, "updateMemoryForNewReadingFromGame"))
        self.assertIn("retreatNotExecutingAlarm", update,
                      "the bound must be compared where the counter is written")
        self.assertIn("unexecutedReadingsBefore = "
                      "botMemoryBefore.retreatProgress.unexecutedReadings", update,
                      "the crossing must be judged against the previous "
                      "reading's interval, or it fires on every reading past "
                      "the bound")
        self.assertIn("unexecutedReadings = retreatProgressNow.unexecutedReadings",
                      update,
                      "and against this reading's, which is #139's counter")

    def test_the_alarm_is_written_and_read_in_four_places_and_no_decision(self):
        readers = definitions_mentioning(self.source, "retreatNotExecutingLastChange")
        self.assertEqual(
            sorted(readers),
            sorted(["BotMemory", "initBotMemory", "missionBotDecisionRoot",
                    "updateMemoryForNewReadingFromGame"]),
            "the alarm must be written by the memory update and printed at the "
            "root only; found %r" % (readers,))

    def test_the_retreat_does_not_consult_the_bound(self):
        for name in ("runAwayIfLowHealth", "runAway", "returnDronesToBay",
                     "retreatReason", "tetherAtStructure"):
            body = definition_body(self.source, name)
            for forbidden in ("retreatNotExecuting", "retreatProgress"):
                self.assertNotIn(
                    forbidden, body,
                    "%s must not decide on the measurement or its bound" % name)

    def test_the_alarm_does_not_end_the_session(self):
        # The bot is the only thing still commanding a warp, and a session that
        # ends leaves a ship under fire with nobody at the controls -- run 7's
        # own failure. `endSessionOnAnExpiredBound` carries the two bounds whose
        # subject is an errand and must not gain this one.
        expired = collapsed(definition_body(self.source, "endSessionOnAnExpiredBound"))
        self.assertNotIn("retreatNotExecuting", expired,
                         "the retreat alarm must not end the session")
        for name in ("retreatNotExecutingAlarm", "describeRetreatNotExecuting"):
            self.assertNotIn("FinishSession", definition_body(self.source, name),
                             "%s must report and nothing else" % name)

    def test_the_rule_reads_nothing_but_its_own_record(self):
        # #120's property, applied to the new rule: a rule over a record is one
        # a case can build, and a mutation that reached into a reading for a
        # gauge would break the shape rather than only the answer.
        body = collapsed(definition_body(self.source, "retreatNotExecutingAlarm"))
        for forbidden in ("shipUI", "hitpointsPercent", "readingFromGameClient",
                          "context", "believed", "memory"):
            self.assertNotIn(
                forbidden, body,
                "retreatNotExecutingAlarm must be pure over its own record and "
                "must not name %s" % forbidden)

    def test_the_status_line_still_carries_the_latency(self):
        status = collapsed(definition_body(self.source, "statusTextFromState"))
        self.assertIn("describeRetreatLatency context", status,
                      "the status line must still carry the retreat's latency")


class TheRetreatItselfDidNotChange(unittest.TestCase):
    """What this change deliberately leaves exactly as #139 left it."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def test_the_drone_recall_still_sits_in_front_of_the_warp(self):
        run_away = collapsed(definition_body(self.source, "runAway"))
        self.assertIn("returnDronesToBay context ( selectThenPanelAction context",
                      run_away.replace("(", "( "),
                      "runAway must still recall drones before warping")

    def test_the_bounds_around_the_retreat_are_unchanged(self):
        self.assertEqual(constant_in_source(self.source, "droneRecallGiveUpTicks"), 60)
        self.assertEqual(
            constant_in_source(self.source, "droneRecallFocusRecoveryTicks"), 20)

    def test_the_warp_is_still_the_selected_item_panel_and_not_a_cascade(self):
        # The escalation this change considered and refused. A cascade begins
        # with a click on the same overview row, adds a flyout that has to
        # render, and would run on the retreat path under fire.
        run_away = collapsed(definition_body(self.source, "runAway"))
        self.assertIn('selectThenPanelAction context "selectedItemWarpTo"', run_away)
        self.assertNotIn("useContextMenuCascade", run_away,
                         "the retreat must not have gained a cascade")

    def test_the_gauge_free_guard_does_not_read_a_gauge(self):
        # Re-asserted because this change sits on top of #120 and #129, exactly
        # as #139 re-asserted it.
        threshold = collapsed(
            definition_body(self.source, "incomingDamageThresholdForThisShip"))
        for forbidden in ("hitpointsPercent", "believed", "lowestArmor",
                          "lowestShield"):
            self.assertNotIn(forbidden, threshold,
                             "the gauge-free threshold must not read %s" % forbidden)
        latch = collapsed(definition_body(self.source, "updateIncomingDamageMemory"))
        retreating = re.search(r"\{ updated \| retreating = (.*)$", latch)
        self.assertIsNotNone(retreating)
        for forbidden in ("hitpointsPercent", "believed", "hitpoints"):
            self.assertNotIn(forbidden, retreating.group(1),
                             "the latch's verdict must not read %s" % forbidden)


if __name__ == "__main__":
    unittest.main()
