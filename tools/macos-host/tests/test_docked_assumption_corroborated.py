"""The docked assumption, corroborated across readings before it is acted on.

Issue #304. `branchDependingOnDockedOrInSpace` read an **absent** ship UI as
*docked*, so a single reading whose ship UI the parser could not complete put
the bot on the docked arm while the ship was in space and fighting, and the
docked arm's first stop -- `undockUsingStationWindow` -- found no station window
either and answered `askForHelpToGetUnstuck` outright. One bad reading, the full
"come and look" alarm, and the reading after it back to shooting rats.

**What the corpus says, counted rather than remembered.** Over the 111 recorded
runs in `~/eve-bot-logs`, **110 episodes** across 40 of them reach that alarm
through `I do not see the station window.`, and not one of them is a stall --
every one ends by itself. They come in two shapes:

  - **79** where the reading before and the reading after both show a ship in
    space with real hitpoints and rats on the overview. This is #304's shape.
    76 of the 79 are one reading wide and the widest is two;
  - **31** where the ship is at a station: 29 across an undock, where the
    station window has gone and the ship UI has not arrived yet, and 2 where the
    ship stayed docked and the station window itself dropped out of one reading.
    These are the wide ones -- up to seven readings -- and a rule that only
    counted readings without a *ship UI* would not have touched a single one of
    them, because the ship UI had been absent for the whole time the ship was in
    the station.

Two absences, one rule. **The docked conclusion is drawn from the station
window** -- a positive fact, the same object the docked arm goes on to act on --
and never from the absence of the ship UI. A reading with neither says nothing
about where the ship is, and on such a reading the bot concludes nothing and
dispatches nothing; it gives the reading back. Only when that has held for
`readingsWithoutShipUIOrStationWindowBeforeConcluding` readings in a row does it
conclude, and what it concludes then is the docked arm -- which is where the
alarm lives, so a real stall still raises it.

**Executed, not restated.** Every reading here is a UI tree run through the real
`EveOnline.ParseUserInterface`; the counter folded over a sequence is the
framework's own `readingsWithoutShipUIOrStationWindowAfter`, the one
`processEventInBaseFramework` calls; and the docked arm is saxrat's real
`undockUsingStationWindow` given a real `BotDecisionContext`, so the alarm these
cases see is the alarm the bot raises.

**Confirmed by mutation**, each applied to saxrat's copy of the framework and
graded on the process exit code with `NO_COLOR=1`. Every mutation also fails
`test_the_two_pinned_copies_are_still_byte_identical`, because only one copy is
mutated; that one is a property of the method and is not counted below.

  - restoring the old split (`Nothing -> describeBranch "I see no ship UI,
    assume we are docked." ifDocked`) fails **ten**, including
    `test_the_unparsed_reading_raises_no_alarm`,
    `test_the_unparsed_reading_concludes_nothing_about_where_the_ship_is`,
    `test_the_reading_below_the_bound_still_only_waits` and
    `test_four_readings_into_an_undock_raises_no_alarm`;
  - dropping the station-window arm, so the count is the only corroboration,
    fails **three**: `test_a_docked_reading_reaches_the_undock_button_at_once`,
    `test_a_long_stay_in_the_station_still_undocks` and
    `test_every_copy_draws_docked_from_the_station_window`. Nothing else moves,
    which is the point -- what that arm buys is a genuine dock costing no
    readings, and it buys nothing else;
  - counting readings without a *ship UI* rather than readings without either
    object -- the narrower fix -- fails **four**:
    `test_four_readings_into_an_undock_raises_no_alarm`,
    `test_the_widest_recorded_undock_raises_no_alarm`,
    `test_the_count_is_cleared_by_the_station_window` and
    `test_every_copy_counts_readings_without_either_object`. It leaves the whole
    of `TheIssuesThreeReadingShapeTest` passing, which is exactly its shape: it
    fixes the 79 episodes the issue is filed on and none of the 31 it is not;
  - moving the bound to 9 fails `test_fixed_values_either_side_of_the_boundary`
    alone; moving it to 7 fails that plus
    `test_the_widest_recorded_undock_raises_no_alarm`,
    `test_the_bound_is_a_bound_and_not_a_ceiling_nothing_reaches` and
    `test_the_bound_is_wider_than_the_widest_episode_recorded_here`;
  - pinning the bound at 4 -- a number the corpus reaches -- fails **five**,
    among them `test_the_bound_is_wider_than_the_widest_episode_recorded_here`,
    which re-takes the widest episode from whatever runs this machine has rather
    than trusting the number written above.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_info_panel_icon_click_settling import SIX_VENDORED_FRAMEWORKS
from test_saxrat_ported_guards import (
    SAXRAT_DIR, SaxratRepl, collapsed, label, node, overview, ship_ui,
    source_of)

# The reading either side of the alarm in saxrat run 50, tick 1103: a ship at
# 69% shield with rats on the overview. Real values, so a case that passes is a
# case about the reading this bot actually took.
SHIELD = 69
ARMOR = 100
MODULE_SLOTS = 4
RATS = [("28,000 m", "Centum Ravager", "Centum Ravager"),
        ("30,000 m", "Centii Minion", "Centii Minion")]

EXTRA_PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import EveOnline.BotFrameworkSeparatingMemory",
    "import Common.DecisionPath",
    "import Common.EffectOnWindow as EffectOnWindow",
)


def station_window():
    """A `LobbyWnd` with the undock button in it -- a genuinely docked reading.

    `parseStationWindowFromUITreeRoot` looks for the `LobbyWnd` type name, and
    finds the undock button among descendants whose type name *contains*
    "Button" and whose display texts match the whole word "undock". A node that
    misses either of those parses into a station window with no undock button,
    which is a different branch of `undockUsingStationWindow` and would make
    these cases pass for the wrong reason -- `TheFixturesAreWhatTheyClaimTest`
    is what stops that.
    """
    return node("LobbyWnd", {"_name": "lobby"}, [
        node("UndockButton", {"_name": "undock"}, [
            label("Undock", (1650, 290, 200, 20)),
        ], region=(1616, 278, 270, 40)),
    ], region=(1600, 270, 300, 800))


def fighting_tree():
    """In space and shooting: a ship UI, an overview with rats, no station."""
    return [ship_ui(SHIELD, ARMOR, MODULE_SLOTS), overview(RATS)]


def unparsed_tree():
    """The same reading with the ship UI gone, and nothing put in its place.

    Built by removing one node from `fighting_tree` rather than by writing a
    second fixture, so the two cannot drift apart in the overview they share.
    The rats stay: what the client dropped is the HUD, and a reading with an
    overview full of rats and no ship UI is the harder case for a rule that is
    supposed to decline to conclude.
    """
    return [overview(RATS)]


class DockedSplitRepl(SaxratRepl):
    """saxrat's own compiled code, and what one reading sequence costs to ask.

    The `BotDecisionContext` is built the way
    `test_saxrat_approach_by_double_click` builds one: every field is either the
    shipped default or the emptiest value its type has, except the reading and
    the count, so nothing in the fixture can decide an answer but those two.
    """

    HELPERS = [
        SaxratRepl.reading_binding("fighting", fighting_tree()),
        SaxratRepl.reading_binding("unparsed", unparsed_tree()),
        SaxratRepl.reading_binding("docked", [station_window()]),
        "ctx parsed count ="
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = count"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        # The framework's own counter, folded over the sequence exactly as
        # `processEventInBaseFramework` folds it reading by reading.
        "countOver readings ="
        " List.foldl (\\reading count -> EveOnline.BotFrameworkSeparatingMemory"
        ".readingsWithoutShipUIOrStationWindowAfter count reading) 0 readings",
        # A sequence is only a sequence if every fixture in it parsed. Where one
        # did not, the answer says so rather than quietly being a shorter run --
        # a fixture that never arrived otherwise reads exactly like a rule that
        # concluded nothing.
        "seqOf maybes = List.filterMap identity maybes",
        "complete maybes ="
        " List.length (seqOf maybes) == List.length maybes",
        "splitOver maybes =\n"
        "    case ( complete maybes, List.reverse (seqOf maybes) ) of\n"
        "        ( True, last :: _ ) ->\n"
        "            Just (EveOnline.BotFrameworkSeparatingMemory"
        ".branchDependingOnDockedOrInSpace\n"
        "                { ifDocked = undockUsingStationWindow"
        " (ctx last (countOver (seqOf maybes)))\n"
        "                , ifSeeShipUI = \\_ -> Common.DecisionPath"
        ".describeBranch \"IN SPACE\" EveOnline"
        ".BotFrameworkSeparatingMemory.waitForProgressInGame\n"
        "                }\n"
        "                (ctx last (countOver (seqOf maybes))))\n"
        "        _ ->\n"
        "            Nothing",
        "unpack = Common.DecisionPath"
        ".unpackToDecisionStagesDescriptionsAndLeaf",
        "textOver maybes = splitOver maybes"
        " |> Maybe.map (unpack >> Tuple.first >> String.join \" | \")"
        " |> Maybe.withDefault \"FIXTURE MISSING\"",
        "effectsOfLeaf leaf =\n"
        "    case leaf of\n"
        "        EveOnline.BotFrameworkSeparatingMemory.ContinueSession"
        " continue ->\n"
        "            continue.effectsOnGameClient\n"
        "        EveOnline.BotFrameworkSeparatingMemory.FinishSession ->\n"
        "            []",
        "effectsOver maybes = splitOver maybes"
        " |> Maybe.map (unpack >> Tuple.second >> effectsOfLeaf)"
        " |> Maybe.withDefault []",
        "repeated count reading = List.repeat count reading",
        "bound = EveOnline.BotFrameworkSeparatingMemory"
        ".readingsWithoutShipUIOrStationWindowBeforeConcluding",
    ]

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", EXTRA_PREAMBLE)
        super().__init__(**kwargs)


ALARM = "I am stuck here and need help to continue."
NO_STATION_WINDOW = "I do not see the station window."
DOES_NOT_SAY = "does not say where the ship is"
DOCKED = "I do see the station window, so we are docked"
LONG_ENOUGH = "that is long enough to be the client and not a dropped reading"
IN_SPACE = "IN SPACE"


class SplitCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(DockedSplitRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def texts(self, *sequences):
        return self.repl.strings(
            ["textOver [ %s ]" % ", ".join(sequence) for sequence in sequences],
            definitions=DockedSplitRepl.HELPERS)

    def booleans(self, expressions):
        return self.repl.evaluate(
            expressions, definitions=DockedSplitRepl.HELPERS)


class TheFixturesAreWhatTheyClaimTest(SplitCase):
    """The three readings, before anything is concluded from them.

    A `docked` fixture the parser made no station window of, or an `unparsed`
    one that quietly kept its ship UI, would make every case below pass for a
    reason that has nothing to do with the rule.
    """

    def test_the_trees_parse_into_the_three_readings_the_cases_assume(self):
        self.assertEqual(
            [True] * 8,
            self.booleans([
                "(fighting |> Maybe.map (.shipUI >> (/=) Nothing)) == Just True",
                "(fighting |> Maybe.andThen .shipUI"
                " |> Maybe.map (.hitpointsPercent >> .shield)) == Just %d" % SHIELD,
                "(fighting |> Maybe.map (.stationWindow >> (==) Nothing))"
                " == Just True",
                "(unparsed |> Maybe.map (.shipUI >> (==) Nothing)) == Just True",
                "(unparsed |> Maybe.map (.stationWindow >> (==) Nothing))"
                " == Just True",
                # The rats are still there on the unparsed reading, so it is a
                # dropped HUD rather than an empty tree.
                "(unparsed |> Maybe.map (.overviewWindows"
                " >> List.concatMap .entries >> List.length)) == Just %d"
                % len(RATS),
                "(docked |> Maybe.map (.shipUI >> (==) Nothing)) == Just True",
                "(docked |> Maybe.andThen .stationWindow"
                " |> Maybe.map (.undockButton >> (/=) Nothing)) == Just True",
            ]))


class TheIssuesThreeReadingShapeTest(SplitCase):
    """fighting -> one unparsed reading -> fighting, which is #304's own log."""

    def test_the_readings_either_side_take_the_in_space_arm(self):
        before, after = self.texts(
            ["fighting"], ["fighting", "unparsed", "fighting"])
        self.assertIn(IN_SPACE, before)
        self.assertIn(IN_SPACE, after)

    def test_the_unparsed_reading_raises_no_alarm(self):
        text = self.texts(["fighting", "unparsed"])[0]
        self.assertNotIn(ALARM, text)
        self.assertNotIn(NO_STATION_WINDOW, text)

    def test_the_unparsed_reading_concludes_nothing_about_where_the_ship_is(self):
        """Not the docked arm either -- the point is that it does not conclude.

        A rule that answered `ifDocked` and merely kept quiet would still put
        the bot on the docked arm, where it would stay docked, decline to hunt,
        or try to undock. That is the misclassification rather than the alarm,
        and it is what this asserts is gone.
        """
        text = self.texts(["fighting", "unparsed"])[0]
        self.assertIn(DOES_NOT_SAY, text)
        self.assertNotIn(DOCKED, text)
        self.assertNotIn(IN_SPACE, text)

    def test_the_unparsed_reading_dispatches_nothing(self):
        """It must not act on the reading, and it must not act *instead* of it.

        The bot gave this reading up before the change too --
        `askForHelpToGetUnstuck` dispatches no effects and neither does
        `waitForProgressInGame` -- so what the change costs in-game is nothing,
        and what it buys is the signal.
        """
        self.assertEqual(
            [True],
            self.booleans(["effectsOver [ fighting, unparsed ] == []"]))

    def test_the_count_is_cleared_by_the_reading_that_parses(self):
        self.assertEqual(
            [True] * 3,
            self.booleans([
                "countOver (seqOf [ fighting ]) == 0",
                "countOver (seqOf [ fighting, unparsed ]) == 1",
                "countOver (seqOf [ fighting, unparsed, fighting ]) == 0",
            ]))


class AGenuineDockIsBelievedWithoutWaitingTest(SplitCase):
    """The corroboration is a positive signal, so a real dock costs no readings.

    This is the half a counter alone cannot buy. If the docked conclusion had to
    wait for the ship UI to be absent N times, every dock in every run would pay
    N readings before the bot could undock. It pays none, because the station
    window is in the reading and the station window is what being docked looks
    like.
    """

    def test_a_docked_reading_reaches_the_undock_button_at_once(self):
        text = self.texts(["fighting", "docked"])[0]
        self.assertIn(DOCKED, text)
        self.assertIn("Click on the button to undock.", text)
        self.assertNotIn(ALARM, text)

    def test_the_count_is_cleared_by_the_station_window(self):
        self.assertEqual(
            [True] * 2,
            self.booleans([
                "countOver (seqOf [ docked ]) == 0",
                "countOver (seqOf (repeated 20 docked)) == 0",
            ]))

    def test_a_long_stay_in_the_station_still_undocks(self):
        text = self.repl.strings(
            ["textOver (repeated 40 docked)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertIn("Click on the button to undock.", text)


class TheUndockTransitionIsNotAStallTest(SplitCase):
    """The 31 episodes a ship-UI-only counter cannot reach.

    Docked, then the undock starts: the station window leaves the tree and the
    ship UI has not arrived. The ship UI has been absent throughout -- it was
    absent for the whole stay in the station -- so a counter over readings
    without a ship UI is already far past any bound and concludes at once. The
    counter here is over readings without *either*, and it starts at zero on the
    reading the station window was last seen.
    """

    def test_the_ship_ui_has_been_absent_all_along(self):
        self.assertEqual(
            [True],
            self.booleans([
                "List.all (\\reading -> reading.shipUI == Nothing)"
                " (seqOf (repeated 20 docked ++ repeated 4 unparsed))"]))

    def test_four_readings_into_an_undock_raises_no_alarm(self):
        text = self.repl.strings(
            ["textOver (repeated 20 docked ++ repeated 4 unparsed)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertNotIn(ALARM, text)
        self.assertIn(DOES_NOT_SAY, text)

    def test_the_widest_recorded_undock_raises_no_alarm(self):
        """Seven readings: saxrat run 6, tick 9, undocking at session start."""
        text = self.repl.strings(
            ["textOver (repeated 20 docked ++ repeated 7 unparsed)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertNotIn(ALARM, text)

    def test_the_ship_appearing_ends_it(self):
        text = self.repl.strings(
            ["textOver (repeated 20 docked ++ repeated 7 unparsed"
             " ++ [ fighting ])"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertIn(IN_SPACE, text)


class TheAlarmArrivesAtTheBoundAndNotBeforeTest(SplitCase):
    """A genuine stall, and the edges of the bound that lets it through.

    What a genuine one looks like: the client showing neither a ship UI nor a
    station window on reading after reading -- a session change, a client stuck
    on a loading screen, a character-select screen. Nothing below the split can
    run on such a reading (the retreat and the guns need the ship UI, the undock
    needs the station window), and unlike every recorded episode it does not
    end. That is the case a person has to come and look at, and it still raises
    the alarm -- `readingsWithoutShipUIOrStationWindowBeforeConcluding` readings
    later than it used to, which on this host is about fifteen seconds.

    Both edges *and* fixed values either side, because a case that only asks
    about `bound - 1` and `bound` passes for any bound, including one no run
    could reach.
    """

    def test_the_reading_below_the_bound_still_only_waits(self):
        text = self.repl.strings(
            ["textOver (repeated (bound - 1) unparsed)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertNotIn(ALARM, text)
        self.assertIn(DOES_NOT_SAY, text)

    def test_the_reading_at_the_bound_raises_the_alarm(self):
        text = self.repl.strings(
            ["textOver (repeated bound unparsed)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertIn(LONG_ENOUGH, text)
        self.assertIn(NO_STATION_WINDOW, text)
        self.assertIn(ALARM, text)

    def test_it_keeps_raising_it_rather_than_falling_quiet(self):
        text = self.repl.strings(
            ["textOver (repeated (bound * 5) unparsed)"],
            definitions=DockedSplitRepl.HELPERS)[0]
        self.assertIn(ALARM, text)

    def test_fixed_values_either_side_of_the_boundary(self):
        seven, eight = self.repl.strings(
            ["textOver (repeated 7 unparsed)",
             "textOver (repeated 8 unparsed)"],
            definitions=DockedSplitRepl.HELPERS)
        self.assertNotIn(ALARM, seven)
        self.assertIn(ALARM, eight)

    def test_the_bound_is_a_bound_and_not_a_ceiling_nothing_reaches(self):
        self.assertEqual(
            [True, True],
            self.booleans(["bound > 7", "bound < 60"]))


class TheSplitReadsTheStationWindowAndNotTheAbsenceTest(unittest.TestCase):
    """What the docked conclusion is drawn from, read out of the source.

    The wiring is not an expression and cannot be evaluated, so it is read --
    through the whitespace-collapsing reader, so an `elm-format` pass cannot
    break it.
    """

    def setUp(self):
        self.frameworks = {
            name: collapsed(source_of(path))
            for name, path in SIX_VENDORED_FRAMEWORKS.items()}

    def test_no_copy_still_assumes_docked_from_a_missing_ship_ui(self):
        for name, framework in self.frameworks.items():
            self.assertNotIn(
                "I see no ship UI, assume we are docked.", framework,
                "%s still concludes docked from an absence" % name)

    def test_every_copy_draws_docked_from_the_station_window(self):
        for name, framework in self.frameworks.items():
            self.assertIn(
                "I see no ship UI and I do see the station window, so we are "
                "docked.", framework, name)

    def test_every_copy_counts_readings_without_either_object(self):
        for name, framework in self.frameworks.items():
            self.assertIn(
                "readingsWithoutShipUIOrStationWindowAfter readingsBefore "
                "readingFromGameClient = case ( readingFromGameClient.shipUI, "
                "readingFromGameClient.stationWindow ) of ( Nothing, Nothing ) "
                "->", framework, name)

    def test_the_two_pinned_copies_are_still_byte_identical(self):
        self.assertEqual(
            source_of(SIX_VENDORED_FRAMEWORKS["saxrat"]),
            source_of(SIX_VENDORED_FRAMEWORKS["mission runner"]),
            "a change that lands in one and not the other is its own bug")


class TheBoundClearsEveryRecordedEpisodeTest(unittest.TestCase):
    """The number, re-taken from whatever runs this machine has.

    The bound is a claim about the corpus -- "wider than any episode that ever
    ended by itself" -- and a claim like that stops holding without saying so.
    So it is measured here rather than remembered, from every `*.log` in
    `~/eve-bot-logs` rather than from a `saxrat_run*.log` glob that misses the
    runs named after what they were testing.

    Readings are counted the way the host counts them, on
    `read-from-game-N: RequestToVolatileProcess`, and the ticks an episode spans
    are counted beside them -- the two bracket the truth, and the bound has to
    clear the wider.
    """

    HEADER = re.compile(r"^# \[(\d+)\.(\d+)\]")
    READ = re.compile(r"read-from-game-\d+: RequestToVolatileProcess")

    @classmethod
    def setUpClass(cls):
        cls.logs = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "*.log")))
        if not cls.logs:
            raise unittest.SkipTest(
                "no recorded runs in %s, so the widest episode cannot be "
                "measured here" % EVE_BOT_LOGS)

    @classmethod
    def episodes(cls, path):
        """(reads, ticks) for every run of readings that reached the alarm."""
        reads = 0
        block = None
        open_episode = None
        found = []

        def close(tick, lines):
            nonlocal open_episode
            text = "\n".join(lines)
            if ("I see no ship UI, assume we are docked." in text
                    and NO_STATION_WINDOW in text):
                if open_episode is None:
                    open_episode = [reads, tick, tick]
                else:
                    open_episode[2] = tick
            elif open_episode is not None:
                found.append((reads - open_episode[0],
                              open_episode[2] - open_episode[1] + 1))
                open_episode = None

        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if block is None and cls.READ.search(line):
                    reads += 1
                    continue
                match = cls.HEADER.match(line)
                if match:
                    if block is not None:
                        close(block[0], block[1])
                    block = (int(match.group(1)), [line])
                    continue
                if block is None:
                    continue
                if line.startswith("--------"):
                    close(block[0], block[1])
                    block = None
                    continue
                block[1].append(line)
        if block is not None:
            close(block[0], block[1])
        if open_episode is not None:
            found.append((reads - open_episode[0],
                          open_episode[2] - open_episode[1] + 1))
        return found

    def test_the_bound_is_wider_than_the_widest_episode_recorded_here(self):
        widest = 0
        where = None
        total = 0
        for path in self.logs:
            for reads, ticks in self.episodes(path):
                total += 1
                if max(reads, ticks) > widest:
                    widest, where = max(reads, ticks), os.path.basename(path)
        if not total:
            # Worded to match `check_expected_skips.EXPECTED`'s corpus entry:
            # a reason that matches none of them fails CI, and this one names
            # the same absent evidence as the gate in `setUpClass`.
            self.skipTest(
                "no recorded runs here reached the alarm through the missing "
                "station window, so there is no episode to measure")
        bound = self.bound_from_source()
        self.assertLess(
            widest, bound,
            "%d episodes on this machine, the widest %d readings (%s); a bound "
            "of %d does not clear it and would let that episode alarm"
            % (total, widest, where, bound))

    def test_every_recorded_episode_ended_by_itself(self):
        """None of them is a stall, which is why none of them should alarm.

        An episode that ran to the end of its log would be one the bot never
        came out of -- the case the alarm is for. `episodes` only records an
        episode when a reading after it did not reach the alarm, so an unclosed
        one at the end of a file is simply not counted; this asserts that there
        is no such thing to count.
        """
        unfinished = []
        for path in self.logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                tail = handle.read()[-4000:]
            if NO_STATION_WINDOW in tail and ALARM in tail:
                unfinished.append(os.path.basename(path))
        self.assertEqual(
            [], unfinished,
            "a run ends inside the alarm, which would be a real stall and "
            "would change what the bound has to clear")

    @staticmethod
    def bound_from_source():
        source = source_of(os.path.join(
            SAXRAT_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm"))
        match = re.search(
            r"readingsWithoutShipUIOrStationWindowBeforeConcluding\s*=\s*"
            r"(\d+)", source)
        assert match, "the bound is not a literal any more"
        return int(match.group(1))


if __name__ == "__main__":
    unittest.main()
