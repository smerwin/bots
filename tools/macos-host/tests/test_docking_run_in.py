"""Tests for the mission runner not re-commanding a dock it is already flying.

Docking is not a command that completes when it is issued. The client answers a
Dock by flying the ship to the station's docking perimeter, and from 17 km that
run-in takes about eight minutes -- during which nothing else in a reading says
it is happening. `ShipManeuverType` has no docking member, the ship keeps its
ordinary UI, and the station's overview row looks like any other row.

Run 27 is what that cost. Between the two course-settings the client accepted at
readings 346 and 467 there are **486 seconds** -- the run-in's own length, so the
ship had precisely enough time to arrive -- and the bot commanded Dock on **120
of the 121 readings in between**. It never docked, and the session ended in
space. Every one of those commands restarted the run-in, and the alarm never
fired because the bot was printing `A route is set -- travel towards the
mission's system.` and believed it was making progress.

**What these cases pin is the two halves of the fix, and the second is the one
that matters.** Swapping the context-menu cascade for a Selected Item panel
click does not fix this by itself: a panel click repeated every reading restarts
the perimeter run just as effectively. So the rule under test is
`dockingRunInAfterReading` -- what arms the latch, what holds it, and what ends
it -- and it is *executed* through the real `Bot.elm` rather than restated in
Python, for the reason CLAUDE.md's "How a change is verified here" gives: a
Python restatement of a rule tests the restatement.

The three properties worth naming:

- **What stops the re-command** is the client's own sentence, `Setting course to
  docking perimeter`, which it writes for a dock and never for a gate jump. That
  is also why the jump leg is untouched without any test for which leg the bot
  is on -- the latch cannot be armed by a jump.
- **What ends the wait is not a clock.** Eight minutes is roughly sixty
  readings, an order of magnitude past any settling window in `Bot.elm`, and a
  station 200 km off is a longer run-in and just as legitimate. The wait is
  bounded by the range to the station *falling*; only a run-in that has stopped
  closing spends `dockingRunInPatienceReadings`.
- **The marker is asserted against what the client actually wrote**, in
  `~/Documents/EVE/logs/Gamelogs` and in run 27's own bot log, because a matcher
  that drifts from the client's wording fails in the direction that looks like
  success -- nothing matches, the latch never arms, and the bot goes back to
  re-commanding with nothing complaining.

Nothing here reads a live game client or drives a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
import glob
import os
import re
import unittest

from prerequisites import MISSION_RUNNER_DIR, open_repl, recorded_runs

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

GAME_LOGS_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "EVE", "logs", "Gamelogs")

# Quoted verbatim from ~/Documents/EVE/logs/Gamelogs. The channel matters: every
# other consumer of this log in the bot reads `notify` or `info`, and #42 is
# what a matcher on the wrong one costs.
COURSE_SET_LINE = (
    "[ 2026.08.04 01:51:41 ] (notify) Setting course to docking perimeter")

# The client refusing a re-command outright, five times in run 27's window. Not
# matched by anything here -- it is quoted so that a matcher loose enough to
# take it fails.
SESSION_CHANGE_LINE = (
    "[ 2026.08.04 01:50:20 ] (notify) Session change already in progress.")

# Other things the client said on `notify` in the recorded sessions. None of
# them is about a dock.
OTHER_NOTIFY_LINES = [
    "The ship you are piloting does not have targeting systems installed.",
    "You cannot load or unload Focused Modulated Medium Energy Beam I while "
    "it is active.",
    "You cannot do that while warping",
    "Cargo Container has just left Irnin as of 2 seconds ago",
]


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """`text` with every run of whitespace flattened to one space.

    Source assertions go through this so the next `elm-format` pass cannot
    break them the way #58's broke three others.
    """
    return " ".join(text.split())


def declaration(source, name):
    """One top-level declaration's text, from its type annotation to the next.

    Declarations are separated by two blank lines throughout this file, which
    `elm-format` guarantees.
    """
    start = source.index("\n%s :" % name) + 1
    end = source.index("\n\n\n", start)
    return source[start:end]


def string_constant(source, name):
    match = re.search(
        r'^' + name + r' : String\n' + name + r' =\n\s+"([^"]*)"',
        source, re.MULTILINE)
    if match is None:
        raise AssertionError("no String constant named " + name)
    return match.group(1)


def int_constant(source, name):
    match = re.search(
        r'^' + name + r' : Int\n' + name + r' =\n\s+(\d+)',
        source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


class Episode(collections.namedtuple(
        "Episode", "start end commands accepted")):
    """One stretch of run 27's log between two accepted course-settings.

    `commands` and `accepted` are readings, not decision lines, for
    `readings_with`'s reason. `span` counts both bounds, since the run-in was
    under way on each of them.
    """

    @property
    def span(self):
        return self.end - self.start + 1


def run_in(range_meters, since_closer, course_settings):
    """An Elm literal for a `DockingRunIn`, for the repl to fold over."""
    return ("Just { rangeToStationMeters = %s, readingsSinceCloser = %d, "
            "courseSettings = %d }"
            % (("Just %d" % range_meters) if range_meters is not None
               else "Nothing", since_closer, course_settings))


def step(before, course_set=False, range_now=None, docked=False):
    return ("dockingRunInAfterReading { before = %s, courseSetThisReading = %s, "
            "rangeNow = %s, docked = %s }"
            % (before, "True" if course_set else "False",
               ("Just %d" % range_now) if range_now is not None else "Nothing",
               "True" if docked else "False"))


def fold_ranges(start, ranges):
    """`dockingRunInAfterReading` folded over a series of ranges, in Elm.

    One expression rather than a Python loop calling the repl, because the repl
    recompiles the module per line -- and because folding in Elm is the rule
    running, where folding in Python would be the restatement this file exists
    to avoid.
    """
    return ("List.foldl (\\metersNow acc -> dockingRunInAfterReading "
            "{ before = acc, courseSetThisReading = False, "
            "rangeNow = Just metersNow, docked = False }) (%s) [ %s ]"
            % (start, ", ".join(str(value) for value in ranges)))


class ElmRuleUnderTest(unittest.TestCase):
    """The base every executing case here shares: one repl for the file."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(prefix="elm-docking-run-in-")
        cls.source = bot_elm()
        cls.patience = int_constant(cls.source, "dockingRunInPatienceReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()


class WhatArmsTheLatch(ElmRuleUnderTest):
    """The client's own sentence, and nothing else."""

    def test_no_course_setting_leaves_no_run_in(self):
        """A reading the client said nothing on does not arm it.

        The direction that keeps an absent game log from making the bot wait on
        a dock that is not happening: no line means "no run-in reported", never
        "the dock is under way".
        """
        self.assertEqual(
            [True],
            self.repl.evaluate(
                ["(%s) == Nothing" % step("Nothing", range_now=17000)]))

    def test_a_course_setting_arms_it_and_records_the_range(self):
        armed, at_range, counted = self.repl.evaluate([
            "(%s) /= Nothing" % step("Nothing", course_set=True,
                                     range_now=17000),
            "((%s) |> Maybe.andThen .rangeToStationMeters) == Just 17000"
            % step("Nothing", course_set=True, range_now=17000),
            "((%s) |> Maybe.map .courseSettings) == Just 1"
            % step("Nothing", course_set=True, range_now=17000),
        ])
        self.assertTrue(armed, "the client's sentence must arm the latch")
        self.assertTrue(at_range, "the range to beat is this reading's")
        self.assertTrue(counted, "the first course-setting counts as one")

    def test_a_second_course_setting_restarts_it_and_counts(self):
        """The number run 27 is about.

        The client writes the line each time it accepts a Dock, so a second one
        is a second run-in from wherever the ship now is -- the range to beat
        must be the new one, and the count must climb so that a run says
        outright it restarted its own dock.
        """
        restarted, recounted, rearmed = self.repl.evaluate([
            "((%s) |> Maybe.andThen .rangeToStationMeters) == Just 9000"
            % step(run_in(17000, 5, 1), course_set=True, range_now=9000),
            "((%s) |> Maybe.map .courseSettings) == Just 2"
            % step(run_in(17000, 5, 1), course_set=True, range_now=9000),
            "((%s) |> Maybe.map .readingsSinceCloser) == Just 0"
            % step(run_in(17000, 5, 1), course_set=True, range_now=9000),
        ])
        self.assertTrue(restarted, "a restart measures from the new range")
        self.assertTrue(recounted, "each accepted Dock counts")
        self.assertTrue(rearmed, "a restart starts the patience over")

    def test_docking_clears_it(self):
        """So the latch cannot suppress the first Dock of the next trip.

        Asserted even against a reading that also carries a course-setting,
        because docked is the stronger fact: the run-in finished, whatever it
        was doing.
        """
        cleared, cleared_over_a_course_setting = self.repl.evaluate([
            "(%s) == Nothing" % step(run_in(2000, 0, 1), range_now=2000,
                                     docked=True),
            "(%s) == Nothing" % step(run_in(2000, 0, 1), course_set=True,
                                     range_now=2000, docked=True),
        ])
        self.assertTrue(cleared, "a docked reading ends the run-in")
        self.assertTrue(cleared_over_a_course_setting,
                        "docked outranks a course-setting on the same reading")


class WhatEndsTheWait(ElmRuleUnderTest):
    """A falling range, not a clock. This is the half that is easy to get wrong."""

    def test_a_run_in_that_keeps_closing_outlasts_every_settling_window(self):
        """The eight-minute case, and the whole reason the bound is not a number.

        Two hundred readings is roughly twenty-seven minutes at the eight
        seconds a reading the recorded runs average -- far past the ~60 the
        control's own dock took, and far past any settling window in `Bot.elm`.
        A ship that is closing is allowed all of it.

        This is the case a clock-based bound fails: `approachIndicationTrusted-
        ForTicks` is 10, and ten readings into run 27's dock the bot would have
        commanded another one.
        """
        [survived] = self.repl.evaluate([
            "(%s) /= Nothing"
            % fold_ranges(run_in(17000, 0, 1),
                          [17000 - step_index * 80
                           for step_index in range(1, 201)])])
        self.assertTrue(
            survived,
            "a run-in whose range keeps falling must never be re-commanded; "
            "the client is flying it and the distance says so")

    def test_a_run_in_that_stops_closing_expires_at_the_patience(self):
        """And not before it, which is where an off-by-one would hide.

        Exactly `dockingRunInPatienceReadings` readings without a gain end it;
        one fewer does not. Asserted at both sides of the boundary so that
        moving the comparison in either direction fails here.
        """
        held, expired = self.repl.evaluate([
            "(%s) /= Nothing"
            % fold_ranges(run_in(17000, 0, 1), [17000] * (self.patience - 1)),
            "(%s) == Nothing"
            % fold_ranges(run_in(17000, 0, 1), [17000] * self.patience),
        ])
        self.assertTrue(
            held,
            "%d readings without a gain is inside the patience"
            % (self.patience - 1))
        self.assertTrue(
            expired,
            "%d readings without a gain must hand the command back"
            % self.patience)

    def test_a_range_that_grows_is_not_a_gain(self):
        """A ship being pushed away is not a ship arriving.

        The smallest range seen is what is compared against, not the previous
        reading's -- `stall_watch.py`'s rule, and what keeps an oscillating
        distance from setting a new minimum forever.
        """
        no_gain, still_the_minimum = self.repl.evaluate([
            "((%s) |> Maybe.map .readingsSinceCloser) == Just 1"
            % step(run_in(9000, 0, 1), range_now=12000),
            "((%s) |> Maybe.andThen .rangeToStationMeters) == Just 9000"
            % step(run_in(9000, 0, 1), range_now=12000),
        ])
        self.assertTrue(no_gain, "a larger range does not reset the patience")
        self.assertTrue(still_the_minimum,
                        "the smallest range seen is what is held")

    def test_an_unreadable_range_counts_as_no_gain(self):
        """The conservative direction, stated so it is not read as an accident.

        `Nothing` covers no station on the overview, a station whose row is not
        rendered, and a distance the client wrote in AU. None of them is
        evidence the ship is closing, so a run-in nobody can measure spends its
        patience and the Dock is commanded again -- one per patience window
        instead of run 27's one per reading.
        """
        counted, expires = self.repl.evaluate([
            "((%s) |> Maybe.map .readingsSinceCloser) == Just 1"
            % step(run_in(9000, 0, 1)),
            "(%s) == Nothing"
            % ("List.foldl (\\_ acc -> dockingRunInAfterReading { before = acc, "
               "courseSetThisReading = False, rangeNow = Nothing, "
               "docked = False }) (%s) (List.range 1 %d)"
               % (run_in(9000, 0, 1), self.patience)),
        ])
        self.assertTrue(counted, "an unreadable range is not a gain")
        self.assertTrue(expires,
                        "a run-in that can never be measured still ends")

    def test_a_first_readable_range_starts_the_measurement(self):
        """`( Just _, Nothing )` is a gain, not a miss.

        The reading now has something to measure against, so the patience
        should start from it rather than from a count already part-spent.
        """
        [started] = self.repl.evaluate([
            "((%s) |> Maybe.map .readingsSinceCloser) == Just 0"
            % step(run_in(None, 4, 1), range_now=17000)])
        self.assertTrue(started, "the first readable range restarts the count")


class TheDeclineSaysSoEveryReading(ElmRuleUnderTest):
    """A branch that declines has to say so each time it declines."""

    def test_the_line_quotes_the_client_and_carries_the_range(self):
        """Both halves, and the range is not decoration.

        `stall_watch.py` keys its circling test on the decision text changing,
        so a line that read the same at every range would raise an alarm on a
        ship flying its run-in perfectly -- run 107's lesson, one branch over.
        """
        marker = string_constant(self.source, "courseSetToDockingPerimeterMarker")
        [near, far] = self.repl.strings([
            "describeDockingRunIn { rangeToStationMeters = Just 17000, "
            "readingsSinceCloser = 0, courseSettings = 1 }",
            "describeDockingRunIn { rangeToStationMeters = Just 9000, "
            "readingsSinceCloser = 3, courseSettings = 1 }",
        ])
        self.assertIn(marker, near,
                      "the decline must quote the client's own sentence")
        self.assertIn("17000", near, "the decline must carry the range")
        self.assertNotEqual(
            near, far,
            "the decision text has to change as the ship closes, or a "
            "perfectly good run-in reads as a stall to the watcher")

    def test_the_line_says_when_the_range_is_unreadable(self):
        """Rather than printing a number it does not have."""
        [unreadable] = self.repl.strings([
            "describeDockingRunIn { rangeToStationMeters = Nothing, "
            "readingsSinceCloser = 2, courseSettings = 1 }"])
        self.assertNotIn(
            "Nothing", unreadable,
            "an unreadable range must be said in words, not leaked as a Maybe")


class TheMarkerIsWhatTheClientWrote(unittest.TestCase):
    """Read out of `Bot.elm` and checked against real lines, never memory."""

    def setUp(self):
        self.marker = string_constant(
            bot_elm(), "courseSetToDockingPerimeterMarker")

    def test_it_matches_the_recorded_sentence(self):
        self.assertIn(self.marker.lower(), COURSE_SET_LINE.lower())

    def test_it_does_not_match_the_clients_refusal_or_other_notify_lines(self):
        """The five `Session change already in progress.` lines in run 27's own
        window are the client refusing a re-command, not reporting a run-in. A
        matcher loose enough to take one of these would arm the latch on a Dock
        the client threw away.
        """
        for line in [SESSION_CHANGE_LINE] + OTHER_NOTIFY_LINES:
            self.assertNotIn(
                self.marker.lower(), line.lower(),
                "the marker must not match: " + line)

    def test_every_occurrence_in_the_clients_own_logs_is_on_notify(self):
        """The channel, checked against every line the client ever wrote here.

        #42 is what a matcher on the wrong channel costs: a guard that can
        never fire, and which looks exactly like a client that never says
        anything. `gateLockedForWantOfAnItemFromGameLog` had to read `info`
        where three other consumers read `notify`, so which one carries a given
        sentence is checked rather than assumed.

        An absent or silent corpus is a skip, worded to the shape
        `check_expected_skips.py` already names: a machine that has never
        docked cannot report on what the client writes for a dock, and the
        marker is separately pinned against a quoted line above either way.
        """
        lines = []
        for path in glob.glob(os.path.join(GAME_LOGS_DIR, "*.txt")):
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines.extend(line for line in handle
                             if self.marker.lower() in line.lower())
        if not lines:
            raise unittest.SkipTest(
                "no recorded game logs carrying a docking-perimeter line, so "
                "the client's own wording for one cannot be consulted here")
        for line in lines:
            self.assertIn(
                "(notify)", line,
                "the matcher filters on the notify channel, and this line is "
                "not on it: " + line.strip())

    def test_it_reached_the_bot_in_run_27(self):
        """The channel works end to end, on the run the issue is about.

        Three of these lines are carried in run 27's own log by the game-log
        channel (#28), which is what makes the latch reachable at all rather
        than a guard resting on a sentence the bot never sees.
        """
        for name, path in recorded_runs("27"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                carried = [line for line in handle
                           if "game log:" in line
                           and self.marker.lower() in line.lower()]
            self.assertGreater(
                len(carried), 0,
                "run %s carries no docking-perimeter line on the game-log "
                "channel, so nothing could arm the latch" % name)


class RunTwentySevenIsTheEvidence(unittest.TestCase):
    """The measurement the fix is sized against, re-derived from the log.

    **Scoped to the incident rather than to the run, and #103 is why.** These
    cases were written while run 27 was still being appended to, when what the
    log held was the incident: two course-settings the client accepted 121
    readings apart, with a Dock commanded on nearly every reading between them.
    The run then went on for another 5,800 readings and eleven further
    course-settings -- ordinary docking, arriving the first time it was asked --
    and the same question put to the finished log answers 124 commands over
    3,104 readings, 4%. That is a true statement about a whole session and no
    statement at all about the incident, so the assertion went red on `main`
    with nothing wrong with the bot.

    The property belongs to the *episode*, so the episode is what is selected --
    by its own shape, a course-setting followed by a dense run of commands,
    rather than by where it sits in the log -- and what is asserted is that such
    an episode exists and is overwhelmingly dense. That is
    `test_travel_outranks_the_fight.py`'s lesson applied here: assert the
    relation the change rests on, not the numbers one run happened to produce,
    so a corpus that grows cannot make a true claim red. Later docking adds
    episodes; it cannot take this one away.

    What it still cannot pass without is the incident itself. An episode of a
    hundred-odd readings that is 80% Dock commands is not something an ordinary
    dock produces: of run 27's twelve other episodes the most commanded carries
    five, and the whole rest of the run holds ten. So a corpus without #89's
    evidence in it fails here, which is the whole point of these two cases --
    checked by removing the episode's commands from a copy of the log, which
    fails both.
    """

    def readings_with(self, path, needle):
        """The set of reading numbers whose decisions include `needle`.

        The unit is the reading, not the decision line -- the single easiest
        thing to get wrong here, and what `stall_watch.py` got wrong twice. The
        bot re-derives its whole decision path on every framework event, so
        `# [343.3]` and `# [343.7]` are one look at the game.
        """
        readings = set()
        current = None
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                tick = re.match(r"# \[(\d+)\.\d+\]", line)
                if tick:
                    current = int(tick.group(1))
                elif needle in line and current is not None:
                    readings.add(current)
        return readings

    def course_setting_episodes(self, path):
        """Every stretch from one accepted course-setting to the next.

        The bounds are the client's own sentence rather than anything the bot
        said, so an episode is "a dock the client took on, up to the next dock
        it took on" -- which is the unit the re-command hypothesis is about.
        Both bounds are inside it: the first is the reading the run-in started
        on and the second is the reading it was restarted on.
        """
        marker = string_constant(bot_elm(), "courseSetToDockingPerimeterMarker")
        docking = self.readings_with(path, "Click on menu entry 'Dock'")
        course_set = sorted(self.readings_with(path, marker))
        return [
            Episode(start, end,
                    len([r for r in docking if start <= r <= end]),
                    len([r for r in course_set if start <= r <= end]))
            for start, end in zip(course_set, course_set[1:])]

    def the_re_command_episode(self, name, path):
        """The episode the bot spent re-commanding, taken by that property.

        The most Dock commands of any of them, which is a way of asking the log
        where the re-commanding happened rather than telling it. Run 27's own
        answer is emphatic -- 114 against the runner-up's 5 -- and the
        assertions the callers make are what pin that this is #89's episode
        rather than merely the busiest one.
        """
        episodes = self.course_setting_episodes(path)
        self.assertTrue(
            episodes,
            "run %s carries fewer than two accepted course-settings, so it "
            "holds no dock the client both started and restarted" % name)
        return max(episodes, key=lambda episode: episode.commands)

    def test_the_bot_commanded_the_dock_on_almost_every_reading(self):
        for name, path in recorded_runs("27"):
            episode = self.the_re_command_episode(name, path)
            self.assertGreater(
                episode.commands, 100,
                "run %s should show the dock commanded over a long stretch of "
                "readings; that stretch is the bug" % name)
            self.assertGreater(
                episode.commands / float(episode.span), 0.8,
                "run %s commanded the dock on %d of the %d readings between "
                "the course-settings at %d and %d -- the density is what makes "
                "this a re-command rather than a retry"
                % (name, episode.commands, episode.span, episode.start,
                   episode.end))

    def test_the_client_accepted_far_fewer_course_settings_than_commands(self):
        """And that gap is the client throwing re-commands away.

        Stated as the inequality rather than as the counts, because the counts
        are a property of one run and the relation is the finding: the bot asks
        far more often than the client acts, and the asking is what keeps the
        run-in from finishing.

        Asked of the episode, where the run cannot answer it. The client
        accepts a course-setting for every dock it takes on, so a session that
        docks a dozen times ordinarily has a dozen of them and the ratio over
        the whole log measures how much of the session was spent docking --
        which is what #103 found it measuring. Inside the episode the accepted
        ones are the two bounding it, counted from the log rather than assumed
        from the construction, against every reading the bot asked again.
        """
        for name, path in recorded_runs("27"):
            episode = self.the_re_command_episode(name, path)
            self.assertGreater(
                episode.commands, 10 * episode.accepted,
                "run %s should show the dock commanded an order of magnitude "
                "more often between the course-settings at %d and %d than the "
                "client set a course for one"
                % (name, episode.start, episode.end))


class TheWiringIsInPlace(unittest.TestCase):
    """Structure, read whitespace-tolerantly out of the source.

    Everything here is reachability rather than behaviour: the rule above can
    be perfect and change nothing if no branch consults it, which is #12's
    failure and #15's.
    """

    def setUp(self):
        self.source = bot_elm()
        self.flat = collapsed(self.source)

    def test_the_verdict_is_written_in_the_memory_update(self):
        """It has to be. A reading's game-log entries are gone by the next
        reading, and `updateMemoryForNewReadingFromGame` is the only place that
        can write memory.
        """
        update = declaration(self.source, "updateMemoryForNewReadingFromGame")
        self.assertIn("dockingRunInAfterReading", collapsed(update))
        self.assertIn("courseSetToDockingPerimeterFromGameLog",
                      collapsed(update))
        self.assertIn(", dockingRunIn = dockingRunIn", collapsed(update))

    def test_the_travel_branch_declines_while_a_run_in_stands(self):
        jump = declaration(self.source, "jumpToNextSystem")
        flat = collapsed(jump)
        self.assertIn("context.memory.dockingRunIn", flat,
                      "the dock leg must consult the latch")
        self.assertIn("describeDockingRunIn", flat,
                      "and say so on every reading it declines")
        self.assertIn("waitForProgressInGame", flat)

    def test_the_matcher_reads_the_notify_channel(self):
        matcher = collapsed(declaration(
            self.source, "courseSetToDockingPerimeterFromGameLog"))
        self.assertIn("gameLogEntryIsFromNotifyChannel", matcher)
        self.assertIn("courseSetToDockingPerimeterMarker", matcher,
                      "the literal belongs in one named constant, so the "
                      "status line and the matcher cannot drift apart")

    def test_the_dock_leg_presses_the_panels_own_button(self):
        dock = collapsed(declaration(self.source, "dockAtDestinationStation"))
        self.assertIn('selectedItemButtonNamed context "selectedItemDock"', dock)
        self.assertIn("selectedItemIsOverviewEntry", dock,
                      "the panel acts on whatever is selected, so the station "
                      "has to be confirmed as the selected item first")

    def test_the_dock_leg_falls_back_rather_than_waiting_when_out_of_range(self):
        """The Dock button is absent out of range, and that is the gate.

        `selectThenPanelAction` answers a missing button by waiting and
        eventually asking for help, which here would strand a ship that simply
        has to fly further first -- so this branch hands back to the cascade
        instead, and must not be quietly rewired to the shared helper.
        """
        dock = collapsed(declaration(self.source, "dockAtDestinationStation"))
        self.assertIn("ifThePanelCannotDoIt", dock)
        self.assertNotIn("selectThenPanelAction", dock)
        self.assertNotIn("askForHelpToGetUnstuck", dock)

    def test_the_dock_leg_only_fires_when_the_destination_is_in_this_system(self):
        """Or it would dock at a station that happens to be on a gate's grid.

        Issue #171: the route panel's marker count is jumps remaining, not
        waypoints, so counting `AutopilotDestinationIcon`s answered this one
        system early. `destinationIsInThisSystemFromRouteMarkers` reads the
        marker's own `numJumps` instead -- see `test_route_marker_num_jumps.py`
        for the rule itself, executed at each of its cases.
        """
        dock = collapsed(declaration(self.source, "dockAtDestinationStation"))
        self.assertIn("destinationIsInThisSystemFromRouteMarkers", dock)
        self.assertNotIn("routeElementMarker >> List.length", dock)

    def test_the_jump_leg_still_goes_through_the_cascade(self):
        """A jump is instantaneous once commanded and has never failed this way.

        The cascade keeps both entries: `jump` because that leg is unchanged,
        and `dock` because an out-of-range dock is exactly what the panel
        cannot serve and the menu's own Dock is what closes the distance.
        """
        cascade = collapsed(declaration(self.source, "routeMarkerCascade"))
        self.assertIn('[ "dock" , "jump" ]', cascade)
        self.assertIn("useContextMenuCascadeWithCustomConfig", cascade)

    def test_the_station_rule_has_one_definition(self):
        """Two copies of "is this a station" would drift in both directions."""
        self.assertEqual(
            1, self.flat.count("overviewEntryIsAStation entry ="),
            "overviewEntryIsAStation should be defined exactly once")
        self.assertGreaterEqual(
            self.flat.count("overviewEntryIsAStation"), 3,
            "and read by the retreat's escape target as well as the dock leg")

    def test_the_range_excludes_an_au_distance(self):
        """An unparsed distance becomes a 999999 placeholder, and a placeholder
        read as a real range would look like a gain the ship never made.
        """
        ranged = collapsed(declaration(
            self.source, "rangeToNearestStationInMeters"))
        self.assertIn("overviewEntryDistanceIsOnGrid", ranged)
        self.assertNotIn("overviewEntryDistanceOrFarInMeters", ranged)

    def test_the_station_row_has_to_be_rendered(self):
        """A virtualised row keeps a region belonging to whatever was recycled
        into its place, so it is worse than absent both to click and to measure.
        """
        nearest = collapsed(declaration(self.source, "nearestStationOnOverview"))
        self.assertIn("overviewEntryIsDisplayed", nearest)

    def test_the_patience_is_stated_as_a_count_of_readings(self):
        patience = int_constant(self.source, "dockingRunInPatienceReadings")
        self.assertEqual(
            20, patience,
            "the patience is stall_watch.py's APPROACH_PATIENCE, in the same "
            "unit and for the same question; changing it needs its own evidence")

    def test_the_status_line_carries_the_number_this_issue_is_about(self):
        """How many times a run restarted its own dock, in words an operator
        can act on. The number alone is not enough -- a count printed under
        some other name is a measurement nobody will recognise as this one.
        """
        status = collapsed(declaration(self.source, "statusTextFromState"))
        self.assertIn("runIn.courseSettings", status)
        self.assertIn("course-setting", status,
                      "the count has to be labelled as what it is")


class NothingElseDependsOnTheLatch(unittest.TestCase):
    """The latch is one branch's, and stays that way.

    Asserted because the failure it would cause is silent: a second consumer
    reading `dockingRunIn` as "the ship is busy" would suppress a retreat or a
    fight on a reading the ship was under attack, and the log would look
    exactly like a bot that had nothing to do.
    """

    def test_only_the_travel_branch_and_the_status_line_read_it(self):
        source = bot_elm()
        readers = [line.strip() for line in source.split("\n")
                   if "context.memory.dockingRunIn" in line]
        self.assertEqual(
            2, len(readers),
            "expected exactly two decisions to read the latch -- the dock leg "
            "and the status line -- but found: %r" % (readers,))

    def test_the_memory_update_carries_it_forward_exactly_once(self):
        """`botMemoryBefore.dockingRunIn` is not a third consumer.

        It is the rule's own previous value, handed to
        `dockingRunInAfterReading` as `before`, and it belongs in exactly one
        place: two writers of one latch is how a counter ends up pinned.
        """
        source = bot_elm()
        carried = [line.strip() for line in source.split("\n")
                   if "botMemoryBefore.dockingRunIn" in line]
        self.assertEqual(1, len(carried), repr(carried))
        self.assertIn("before =", carried[0])


if __name__ == "__main__":
    unittest.main()
