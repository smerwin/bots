"""Tests for the docked assumption having to be corroborated.

Issue #304. `branchDependingOnDockedOrInSpace` read an absent ship UI as
_docked_, on the strength of one reading and nothing else. The docked arm
reaches `undockUsingStationWindow`, which finds no station window because the
ship is not in a station, and its `Nothing` arm was `askForHelpToGetUnstuck`
outright -- so a single reading whose ship UI the parser could not complete
produced the full "come and look" alarm while the ship was in space and
fighting.

**The misclassification is the defect, not the alarm.** Bounding
`askForHelpToGetUnstuck` would have quietened the symptom and left a bot that
decides it is docked mid-fight and then chooses on that arm. So the
corroboration is at the split, where the conclusion is drawn.

## What corroboration means here, and why it is two things

**Positive first: the station window.** A missing ship UI is the absence of
evidence. A station window is evidence, and it is evidence a client cannot show
to a ship in space. When it is there the split concludes _docked_ on that
reading, as it always did -- so a genuine dock costs nothing, and neither does a
genuine stall that has a station window to show. The largest stall in the
corpus is one of those, and `AStallWithAStationWindowIsStillImmediateTest` is
that stall.

**Persistence second, for when nothing corroborates.** With no ship UI and no
station window there is nothing in the reading to decide on, so the reading is
given back until the state has held for as many readings as the bound
`readingsWithoutShipUIBeforeAssumingDocked` names -- and then the docked arm
runs anyway, which is what keeps the alarm reachable.

## The fixture that makes the argument is one reading used twice

`unreadableReading` is a tree the parser can make nothing of -- no ship UI, no
station window. Fed as the middle of `in space, unreadable, in space` it is a
dropped parse and must raise nothing; fed on its own, over and over, it is a
ship that is really stuck and must raise the alarm. **The reading is identical in
both. Only the readings around it differ.**

## Where the bound comes from, counted in the right unit

Measured here rather than taken from the issue, over every `*.log` under
`~/eve-bot-logs`: 111 files, 1,082,795 host ticks, 107 episodes where the ship UI
was absent while the ship was demonstrably in space.

**Counted in readings, not in log entries.** The host prints roughly three `# [`
entries per completed memory read -- the entry where the read completes, then two
that reprint the same status while the next read is dispatched -- and
`ReadingFromGameClientCompleted` reaches the bot only on the first of them
(`EveOnline.BotFramework`, the `Just readingFromGameClient` arm). An episode that
occupies three log entries is **one** reading. In readings the 107 episodes run
100 of length 1, five of length 2, one of length 3, and one of length **10**:
`mission_run35.log`, ticks 2540.5 to 2550.1, 17.1 seconds. That one is
`TheLongestRecordedSpuriousEpisodeIsCoveredTest`, and it decides the bound.

The issue's proposed N=2 would have left the whole tail. Twelve clears it with
two readings to spare.

**Confirmed by mutation**, each graded on the process exit code with `NO_COLOR=1`
(`unittest -v` colourises its verdicts, so a grader anchored on the printed
words reports every mutation as passing). The list, with what each fails, is in
`MUTATIONS_GRADED` below so that it is beside the cases rather than in a PR
description nobody can rerun.

**Executed rather than restated.** Every reading here is a UI tree run through
the real `EveOnline.ParseUserInterface`; the count is folded with the framework's
own `countReadingsWithoutShipUI`; the arm the alarm sits on is the app's own
`undockUsingStationWindow`, and the alarm is the framework's own
`askForHelpToGetUnstuck`. Both apps that fly are asked, because they share the
framework and the issue only measured one of them -- and the corpus says the
mission runner drops readings at the same rate (9.1 per 100k against saxrat's
9.9) while printing nothing about it, so it was misclassifying silently.

**Not asserted here:** why the ship UI fails to parse. The issue leaves that
open and this change does not need it settled -- a short gap in the ship UI
should not be actionable whichever cause it has.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import unittest

from prerequisites import open_repl
from test_info_panel_icon_click_settling import (
    EXTRA_PREAMBLE, SIX_VENDORED_FRAMEWORKS)
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_DIR, SaxratRepl, body_of, collapsed, node,
    overview, ship_ui, source_of)

# `askForHelpToGetUnstuck`'s sentence, which `stall_watch.py` matches literally.
STUCK = "I am stuck here and need help to continue."

# The three answers the split can give a reading with no ship UI, quoted so a
# case says which arm was taken rather than which arm was not.
DOCKED_BY_STATION_WINDOW = "I do see the station window -- we are docked."
DOCKED_BY_PERSISTENCE = "assume we are docked."
NOT_YET = "not yet enough to conclude we docked"

# The bound, repeated here so a mutation of the Elm constant is graded against a
# number this file states rather than against whatever the Elm now says.
BOUND = 12

# What each mutation of the rule fails, measured rather than predicted. Kept
# beside the cases so the claim can be rerun; `tools` has no runner for it, so
# it is applied to all six copies by hand and the module is run in a fresh
# process, since the harness copies and compiles the app at process start.
MUTATIONS_GRADED = """
  - the split reverted to `describeBranch "I see no ship UI, assume we are
    docked." ifDocked`, which is the code #304 was filed on -- 11 cases, and the
    two that matter are, in TheIssuesThreeReadingsRaiseNothingTest,
    test_no_reading_of_the_episode_raises_the_alarm -- which is the issue's own
    three log lines -- and test_the_dropped_reading_takes_neither_arm;

  - readingsWithoutShipUIBeforeAssumingDocked = 2, the number the issue proposes
    -- 6 cases, and all three behavioural ones are
    TheLongestRecordedSpuriousEpisodeIsCoveredTest. That is the argument for
    twelve over two, made by the corpus rather than by preference;

  - = 4 -- the same six, for the same ten readings;

  - = 20 -- 4 cases, among them, in TheAlarmStillFiresForARealStallTest,
    test_the_alarm_is_reached_on_the_twelfth_reading_and_not_later. The bound is
    a bound, not a direction;

  - the station window never consulted (`case Nothing of` in its place), so the
    positive signal is gone and every dock and every station-side stall pays the
    wait -- 5 cases, among them
    TheDockedArmStillWorksWhenReallyDockedTest's
    test_a_dock_cycle_costs_no_readings_at_all and
    AStallWithAStationWindowIsStillImmediateTest's
    test_the_alarm_is_raised_on_the_very_first_reading. **Every
    false-positive case still passes under it**, which is the shape of that
    mutation: correct about the defect, and charging every dock cycle and every
    real stall for it;

  - the persistence arm waiting forever, never falling through to `ifDocked`
    (`if True then`) -- 5 cases, three of them
    TheAlarmStillFiresForARealStallTest. **Every false-positive case still
    passes under it too**: the noise gone and the signal with it;

  - countReadingsWithoutShipUI not reset by a reading that parses a ship UI --
    4 cases, among them TheCountResetsOnEveryReadingThatParsesTest's
    test_alternating_readings_never_reach_the_bound, because a
    client dropping one reading in two would otherwise accumulate its way to
    "docked" without the ship ever leaving space.
"""


def in_space():
    """Run 50's reading [158.1]: a live ship, rats on the overview.

    `ship 5/100` in the log's header is a shield at 5% with the structure
    intact, which is what these arguments are. The rats are the two the same
    line reports, named from the recorded overviews so the entries are the shape
    the parser really meets.
    """
    return [
        ship_ui(5, 100, 4),
        overview([
            ("12 km", "Centii Savage", "Frigate"),
            ("24 km", "Tower Sentry Sansha I", "Sentry Gun"),
        ]),
    ]


def nothing_readable():
    """Reading [158.2]: no ship UI, and nothing else to go on either.

    The strictest version of the reading the issue records. The log line shows
    `ship ?/?`, and this fixture carries no station window either, so the split
    has nothing within the reading that could decide it -- which is the point.
    The same fixture is the stall below; what tells them apart is the neighbours.
    """
    return []


def station_lobby(children):
    """A station window, as `parseStationWindowFromUITreeRoot` finds one.

    `LobbyWnd` is the type name it looks for. A button is found by its own type
    name containing `Button` and by its display text, so what is inside decides
    whether the window offers an undock button, an abort, or neither.
    """
    return [node("LobbyWnd", {"_name": "lobby"}, children,
                 region=(1500, 300, 400, 700))]


def undock_button():
    return node("UndockButton", {"_setText": "Undock"},
                region=(1600, 900, 120, 32))


class CorroborationRepl(SaxratRepl):
    """The split, folded over a session of really parsed readings.

    The two arms are the app's own: `undockUsingStationWindow` is where the
    alarm lives, and `runAwayIfLowHealth` is the first thing the in-space arm
    consults. What follows the retreat is replaced by a marker, because what
    these cases assert is which arm a reading takes, not what the in-space arm
    then decides.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", EXTRA_PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        SaxratRepl.reading_binding("inSpaceReading", in_space()),
        SaxratRepl.reading_binding("unreadableReading", nothing_readable()),
        SaxratRepl.reading_binding(
            "dockedReading", station_lobby([undock_button()])),
        SaxratRepl.reading_binding(
            "stationWithoutButtonsReading", station_lobby([])),
        # Every field is either the shipped default or the emptiest value its
        # type has, so nothing in the fixture can decide the answer except the
        # reading and the count -- the same rule
        # `test_saxrat_approach_by_double_click.py` states for its context.
        "contextFor counted parsed ="
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUI = counted"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "splitFor counted parsed ="
        " EveOnline.BotFrameworkSeparatingMemory.branchDependingOnDockedOrInSpace"
        " { ifDocked = undockUsingStationWindow (contextFor counted parsed)"
        " , ifSeeShipUI = \\shipUI ->"
        " runAwayIfLowHealth (contextFor counted parsed) shipUI"
        " |> Maybe.withDefault (Common.DecisionPath.describeBranch \"IN SPACE\""
        " EveOnline.BotFrameworkSeparatingMemory.waitForProgressInGame) }"
        " counted parsed",
        "describeOf decision = decision |> Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf |> Tuple.first"
        " |> String.join \" | \"",
        # One session: the framework's own counter folded over the readings, and
        # the split asked with the number the framework would have handed it.
        "foldSession step readings =\n"
        "    readings\n"
        "        |> List.filterMap identity\n"
        "        |> List.foldl\n"
        "            (\\reading ( before, log ) ->\n"
        "                let\n"
        "                    counted =\n"
        "                        EveOnline.BotFrameworkSeparatingMemory"
        ".countReadingsWithoutShipUI reading before\n"
        "                in\n"
        "                ( counted, log ++ [ step counted reading ] )\n"
        "            )\n"
        "            ( 0, [] )\n"
        "        |> Tuple.second",
        "report readings = foldSession (\\counted reading ->"
        " String.fromInt counted ++ \": \" ++ describeOf (splitFor counted reading))"
        " readings |> String.join \" || \"",
        "countsOf readings = foldSession (\\counted _ -> String.fromInt counted)"
        " readings |> String.join \",\"",
        # A stall, written as a length rather than as a list, so a case can ask
        # for one longer than the bound without writing the bound out.
        "stallOf readings = report (List.repeat readings unreadableReading)",
    ]


class MissionRunnerCorroborationRepl(CorroborationRepl):
    """The same bindings, pointed at the mission runner.

    It shares the framework byte for byte and its `undockUsingStationWindow` has
    the same shape, so the split is the same rule reached the same way. The
    issue measured saxrat and left the mission runner unmeasured; the corpus says
    it drops readings just as often and says nothing about it, which is what
    makes asking both worth the second repl.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        super().__init__(**kwargs)


class BothAppsRepl:
    """One repl per app that flies this framework."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {
            "saxrat": open_repl(CorroborationRepl),
            "mission runner": open_repl(MissionRunnerCorroborationRepl),
        }

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.strings(
                expressions,
                definitions=list(definitions) + list(repl.HELPERS))

    def each_bool(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.evaluate(
                expressions,
                definitions=list(definitions) + list(repl.HELPERS))


class TheFixturesAreWhatTheyClaimTest(BothAppsRepl, unittest.TestCase):
    """The readings, before anything is concluded from them.

    An `inSpaceReading` whose ship UI did not parse would take the docked arm and
    pass most of this file for the wrong reason; an `unreadableReading` that
    accidentally carried a station window would never reach the persistence arm;
    and a `dockedReading` whose `LobbyWnd` the parser walked past would be the
    unreadable one under another name.
    """

    def test_the_four_readings_parse_into_the_four_states(self):
        for app, answers in self.each_bool([
                "inSpaceReading /= Nothing",
                "unreadableReading /= Nothing",
                "dockedReading /= Nothing",
                "stationWithoutButtonsReading /= Nothing",
                # In space: the ship UI reads, and the rats are on the overview.
                "inSpaceReading |> Maybe.andThen .shipUI |> (/=) Nothing",
                "inSpaceReading |> Maybe.map (.overviewWindows"
                " >> List.concatMap .entries >> List.length >> (==) 2)"
                " |> Maybe.withDefault False",
                # Unreadable: no ship UI and no station window, so nothing
                # inside the reading can decide the split.
                "unreadableReading |> Maybe.andThen .shipUI |> (==) Nothing",
                "unreadableReading |> Maybe.andThen .stationWindow |> (==) Nothing",
                # Docked: no ship UI either, and a station window with a button.
                "dockedReading |> Maybe.andThen .shipUI |> (==) Nothing",
                "dockedReading |> Maybe.andThen .stationWindow"
                " |> Maybe.andThen .undockButton |> (/=) Nothing",
                # The stall: a station window the parser finds, offering
                # neither an undock button nor an abort.
                "stationWithoutButtonsReading |> Maybe.andThen .stationWindow"
                " |> (/=) Nothing",
                "stationWithoutButtonsReading |> Maybe.andThen .stationWindow"
                " |> Maybe.andThen .undockButton |> (==) Nothing",
                "stationWithoutButtonsReading |> Maybe.andThen .stationWindow"
                " |> Maybe.andThen .abortUndockButton |> (==) Nothing",
        ]):
            self.assertEqual(
                answers, [True] * 13,
                "%s: the fixtures did not parse as intended" % app)


class TheIssuesThreeReadingsRaiseNothingTest(BothAppsRepl, unittest.TestCase):
    """Run 50's `[158.1] [158.2] [158.3]`, replayed through the real split.

    In space and fighting, then one reading the parser could not complete, then
    in space and fighting again. The issue's whole complaint is the alarm in the
    middle of that.
    """

    EPISODE = "[ inSpaceReading, unreadableReading, inSpaceReading ]"

    def test_no_reading_of_the_episode_raises_the_alarm(self):
        for app, (answer,) in self.each(["report %s" % self.EPISODE]):
            self.assertNotIn(
                STUCK, answer,
                "%s: the dropped reading still raises the alarm: %s"
                % (app, answer))

    def test_the_dropped_reading_takes_neither_arm(self):
        """Not the docked arm -- and not the in-space arm either, which has no
        ship UI to be handed. Nothing below the split can run on a reading whose
        ship UI is missing, so giving the reading back starves nothing."""
        for app, (answer,) in self.each(["report %s" % self.EPISODE]):
            middle = answer.split(" || ")[1]
            self.assertIn(NOT_YET, middle, "%s: %s" % (app, middle))
            self.assertNotIn(DOCKED_BY_PERSISTENCE, middle, "%s: %s" % (app, middle))
            self.assertNotIn(DOCKED_BY_STATION_WINDOW, middle,
                             "%s: %s" % (app, middle))
            self.assertNotIn("IN SPACE", middle, "%s: %s" % (app, middle))

    def test_the_readings_either_side_are_in_space(self):
        """The half that says the episode is a dropped parse rather than a dock:
        the bot reads a live ship on the readings before and after."""
        for app, (answer,) in self.each(["report %s" % self.EPISODE]):
            first, _, last = answer.split(" || ")
            for reading in (first, last):
                self.assertNotIn(DOCKED_BY_PERSISTENCE, reading,
                                 "%s: %s" % (app, reading))
                self.assertNotIn(STUCK, reading, "%s: %s" % (app, reading))

    def test_the_count_is_the_shape_the_episode_has(self):
        """One reading wide, and cleared by the reading that follows it."""
        for app, (answer,) in self.each(["countsOf %s" % self.EPISODE]):
            self.assertEqual("0,1,0", answer, app)


class TheLongestRecordedSpuriousEpisodeIsCoveredTest(
        BothAppsRepl, unittest.TestCase):
    """Ten readings in a row, which is the longest the corpus holds.

    `mission_run35.log`, ticks 2540.5 to 2550.1: ten consecutive failed memory
    reads over 17.1 seconds, with `Shield: 100% Armor: 100%` and the same
    mission tracker on the readings either side. It occupies 30 `# [` entries in
    the log and is **ten readings**, because the host reprints a status while the
    next read is in flight and the bot decides only when one completes.

    **This is the case that decides the bound.** The issue's N=2 covers the 100
    one-reading episodes and none of the seven longer ones; the tail runs
    1, 1, ..., 2, 2, 2, 2, 2, 3, 10, and twelve is the first round number clear
    of it.
    """

    EPISODE = ("[ inSpaceReading ]"
               " ++ List.repeat 10 unreadableReading"
               " ++ [ inSpaceReading ]")

    def test_ten_consecutive_dropped_readings_raise_nothing(self):
        for app, (answer,) in self.each(["report (%s)" % self.EPISODE]):
            self.assertNotIn(STUCK, answer, "%s: %s" % (app, answer))

    def test_none_of_the_ten_reaches_the_docked_arm(self):
        for app, (answer,) in self.each(["report (%s)" % self.EPISODE]):
            for reading in answer.split(" || ")[1:11]:
                self.assertIn(NOT_YET, reading, "%s: %s" % (app, reading))

    def test_the_count_reaches_ten_and_is_then_cleared(self):
        for app, (answer,) in self.each(["countsOf (%s)" % self.EPISODE]):
            self.assertEqual(
                "0," + ",".join(str(n) for n in range(1, 11)) + ",0", answer,
                app)


class TheCountResetsOnEveryReadingThatParsesTest(
        BothAppsRepl, unittest.TestCase):
    """A ship UI that comes and goes must never accumulate into "docked".

    Without the reset a client dropping one reading in two would reach the bound
    inside a minute while the ship never left space, which is a slower version of
    the defect rather than a fix for it.
    """

    FLICKER = ("List.concat (List.repeat 8"
               " [ unreadableReading, inSpaceReading ])")

    def test_alternating_readings_never_reach_the_bound(self):
        for app, (answer,) in self.each(["countsOf (%s)" % self.FLICKER]):
            self.assertEqual("1,0" + ",1,0" * 7, answer, app)

    def test_alternating_readings_never_raise_the_alarm(self):
        for app, (answer,) in self.each(["report (%s)" % self.FLICKER]):
            self.assertNotIn(STUCK, answer, "%s: %s" % (app, answer))


class TheAlarmStillFiresForARealStallTest(BothAppsRepl, unittest.TestCase):
    """The signal the change must not cost, on the same reading that must not
    raise it when it stands alone.

    A genuine stall with nothing readable at all is a ship UI that stays absent:
    a ship in a station has none on any reading, and a client that has stopped
    drawing has none either. `unreadableReading` repeated is that, byte for byte
    the fixture `TheIssuesThreeReadingsRaiseNothingTest` proves raises nothing.
    """

    def test_a_stall_longer_than_the_bound_raises_the_alarm(self):
        for app, (answer,) in self.each(["stallOf %d" % (BOUND + 4)]):
            self.assertIn(
                STUCK, answer,
                "%s: a ship that never shows a ship UI no longer asks for "
                "help, which is the alarm made unreachable: %s" % (app, answer))

    def test_the_alarm_is_reached_on_the_twelfth_reading_and_not_later(self):
        """The bound is a bound. A corroboration that only ever waits is not a
        fix, it is the alarm deleted."""
        for app, (answer,) in self.each(["stallOf %d" % (BOUND + 4)]):
            readings = answer.split(" || ")
            raised = [index for index, reading in enumerate(readings, start=1)
                      if STUCK in reading]
            self.assertEqual(
                list(range(BOUND, BOUND + 5)), raised,
                "%s: the alarm is not raised on every reading from the %dth "
                "on: %s" % (app, BOUND, answer))

    def test_nothing_before_the_bound_raises_it(self):
        for app, (answer,) in self.each(["stallOf %d" % (BOUND - 1)]):
            self.assertNotIn(STUCK, answer, "%s: %s" % (app, answer))

    def test_the_alarm_arrives_through_the_missing_station_window(self):
        """Through the app's own `undockUsingStationWindow`, not from anywhere
        this file arranged."""
        for app, (answer,) in self.each(["stallOf %d" % BOUND]):
            last = answer.split(" || ")[-1]
            self.assertIn(DOCKED_BY_PERSISTENCE, last, "%s: %s" % (app, last))
            self.assertIn("I do not see the station window.", last,
                          "%s: %s" % (app, last))


class AStallWithAStationWindowIsStillImmediateTest(
        BothAppsRepl, unittest.TestCase):
    """The largest stall in the corpus, which the corroboration does not delay.

    `saxrat_run6.log` ticks 8041.2 to 11592.2: 31,234 log entries in which the
    bot saw the station panel, clicked undock 20,441 times and never got out,
    and asked for help 10,310 times. Its ladder is `+ I see no ship UI` then
    `++ I do not see the undock button.` -- a station window that is there, so
    the positive half of the corroboration answers on the first reading and the
    alarm is raised exactly as before.

    **This is what the station-window arm buys.** Without it every real stall of
    this shape would be reported twelve readings late for no reason.
    """

    def test_the_alarm_is_raised_on_the_very_first_reading(self):
        for app, (answer,) in self.each([
                "report (List.repeat 3 stationWithoutButtonsReading)"]):
            first = answer.split(" || ")[0]
            self.assertIn(DOCKED_BY_STATION_WINDOW, first, "%s: %s" % (app, first))
            self.assertIn("I do not see the undock button.", first,
                          "%s: %s" % (app, first))
            self.assertIn(STUCK, first, "%s: %s" % (app, first))

    def test_no_reading_of_it_waits(self):
        for app, (answer,) in self.each([
                "report (List.repeat 3 stationWithoutButtonsReading)"]):
            self.assertNotIn(NOT_YET, answer, "%s: %s" % (app, answer))


class TheDockedArmStillWorksWhenReallyDockedTest(
        BothAppsRepl, unittest.TestCase):
    """A ship that really is in a station undocks, and pays nothing to.

    The station window is what a docked client shows and what a ship in space
    cannot, so the common case never reaches the count at all.
    """

    def test_a_docked_ship_undocks_on_the_first_reading(self):
        for app, (answer,) in self.each([
                "report (List.repeat 3 dockedReading)"]):
            first = answer.split(" || ")[0]
            self.assertIn(DOCKED_BY_STATION_WINDOW, first, "%s: %s" % (app, first))
            self.assertIn("Click on the button to undock.", first,
                          "%s: %s" % (app, first))

    def test_a_dock_cycle_costs_no_readings_at_all(self):
        for app, (answer,) in self.each([
                "report (List.repeat 3 dockedReading)"]):
            waited = [reading for reading in answer.split(" || ")
                      if NOT_YET in reading]
            self.assertEqual(
                [], waited,
                "%s: a genuine dock is paying the corroboration's price: %s"
                % (app, answer))

    def test_it_never_asks_for_help(self):
        for app, (answer,) in self.each([
                "report (List.repeat 3 dockedReading)"]):
            self.assertNotIn(STUCK, answer, "%s: %s" % (app, answer))


class AReadingWithAShipUIIsNeverTouchedTest(BothAppsRepl, unittest.TestCase):
    """The in-space arm is not what changed, asserted so that it stays so."""

    def test_a_ship_ui_takes_the_in_space_arm_whatever_the_count_says(self):
        # A count the framework would never produce beside a ship UI, asked
        # anyway: the arm is chosen by the reading, and the count only ever
        # decides between the other two.
        for app, answers in self.each([
                "inSpaceReading |> Maybe.map (splitFor %d >> describeOf)"
                " |> Maybe.withDefault \"NO READING\"" % counted
                for counted in (0, 99)]):
            for answer in answers:
                self.assertNotIn(DOCKED_BY_PERSISTENCE, answer,
                                 "%s: %s" % (app, answer))
                self.assertNotIn(DOCKED_BY_STATION_WINDOW, answer,
                                 "%s: %s" % (app, answer))
                self.assertNotIn(NOT_YET, answer, "%s: %s" % (app, answer))
                self.assertNotIn(STUCK, answer, "%s: %s" % (app, answer))


class EverySourceCopyCarriesTheSameRuleTest(unittest.TestCase):
    """The six vendored frameworks, and the six call sites that wire them.

    A copy left on the old split is a bot still misclassifying. A call site
    still passing only the reading does not compile, which is the intended way
    to find out; it is asserted here anyway so that a copy added later is asked
    too.
    """

    def test_no_copy_still_assumes_docked_from_one_reading(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "branchDependingOnDockedOrInSpace"))
            self.assertNotIn(
                "I see no ship UI, assume we are docked.", block,
                "%s: still concludes docked from a single reading" % app)
            self.assertIn(
                "readingsWithoutShipUIBeforeAssumingDocked", block,
                "%s: the split does not consult the bound" % app)

    def test_every_copy_asks_for_the_station_window_before_the_count(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "branchDependingOnDockedOrInSpace"))
            positive = block.find("case readingFromGameClient.stationWindow of")
            self.assertNotEqual(
                -1, positive,
                "%s: the split does not consult the station window at all, so "
                "every dock pays the bound" % app)
            self.assertLess(
                positive,
                block.index("readingsWithoutShipUIBeforeAssumingDocked"),
                "%s: the count is consulted before the positive signal" % app)

    def test_every_copy_carries_the_same_bound(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path),
                        "readingsWithoutShipUIBeforeAssumingDocked"))
            self.assertIn(
                "readingsWithoutShipUIBeforeAssumingDocked = %d" % BOUND,
                block,
                "%s: the bound is not %d" % (app, BOUND))

    def test_every_copy_counts_the_same_way(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            block = collapsed(
                body_of(source_of(path), "countReadingsWithoutShipUI"))
            # Reset on a reading that parsed, capped on one that did not.
            self.assertIn("Just _ -> 0", block, app)
            self.assertIn(
                "min readingsWithoutShipUIBeforeAssumingDocked (before + 1)",
                block, app)

    def test_every_call_site_wires_the_count(self):
        for app, path in SIX_VENDORED_FRAMEWORKS.items():
            bot = collapsed(source_of(
                os.path.join(os.path.dirname(os.path.dirname(path)),
                             "Bot.elm")))
            self.assertIn(
                "context.readingsWithoutShipUI context.readingFromGameClient",
                bot,
                "%s: the split is called without the count the framework "
                "maintains" % app)

    def test_the_two_flying_copies_are_still_byte_identical(self):
        """`test_saxrat_ported_guards.FrameworkParityTest` pins this too. Said
        again here because this change touches the file in six places, and a
        change that lands in one copy and not the other is its own bug."""
        framework = os.path.join("EveOnline", "BotFrameworkSeparatingMemory.elm")
        self.assertEqual(
            source_of(os.path.join(SAXRAT_DIR, framework)),
            source_of(os.path.join(MISSION_RUNNER_DIR, framework)))


if __name__ == "__main__":
    unittest.main()
