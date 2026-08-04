"""Tests for the mission runner saying when it leaves drones behind.

Issue #59. Warping or docking with drones still in space abandons them, and the
bot never goes back -- but until now it also never said so. This change is the
observation the issue asked for first, and nothing else: a memory of what was in
space and where, a decision-log line on the reading the ship leaves without it,
and a clause in the status line for the rest of the session. No decision reads
any of it.

**The first job was establishing whether it still happens, and the recorded runs
say it does not.** Run 1 is the only one that predates PR #11, and it is the only
one whose drone total falls while the ship leaves: it warped with five drones in
space across 24 readings and jumped a stargate with them out across 12 more.
Every run after it carries #11's own status-line wording, and across all of them:

  - `returnDronesToBay`'s give-up -- which since #11 names itself on every
    reading it declines, rather than only on the reading a counter was exactly
    60 -- appears **zero** times;
  - the only other reading where the ship is in warp with drones in space is run
    11's, where the ship was lining up and all five drones were in the bay by
    the reading the warp finished;
  - recalls land: runs 9, 10, 11, 12 and 14 completed 41 between them, each
    ending with the in-space count at zero and the bay holding what came back.

The drones that were lost after #11 were lost two other ways, neither of which
this issue is about: destroyed in space by rats while the ship was still on grid
(run 5 went 10 -> 8, run 14 went 5 -> 2), and left out when an operator stopped a
run mid-pocket (run 8 ended 3 in bay / 5 in space, and run 9 picked the same five
up 40 readings later, which is also the only direct evidence in the corpus that
abandoned drones persist and can be recalled).

**So the trigger is read at the far end of a departure, not at its start**, and
run 11 is why. A ship lining up to warp still has time to get its drones home,
and treating "the ship is entering warp with drones out" as the event would have
reported an abandonment that did not happen -- a lying instrument, which is
worse here than no instrument.

**What is asserted against the logs is the finished runs by name.** They are
fixed history; a run still being appended to is not, and pinning "no run has ever
done this" would turn a real future occurrence into a failing test rather than
into the signal it should be. That is exactly what this change exists to record.
Run 17 was live while this was written and says the same thing so far -- its last
drone died mid-fight at tick 293, with the ship on grid still shooting the rat
that killed it -- and is left unpinned for that reason.

The `elm repl` cases run the real rule out of the bot's own compiled code rather
than restating it in Python, the recipe #45 and #49 established. They need `elm`
on PATH with the app's dependencies fetched -- what `compile_bot.sh` leaves
behind -- and skip if the repl cannot run at all.

Every case that reads `Bot.elm` as text goes through `collapsed()`, so a future
`elm-format` pass cannot break them the way #58's broke three others.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
BOT_LOGS_DIR = os.path.expanduser("~/eve-bot-logs")

# The runs this change's finding was established from -- every one that had
# finished. A run still being appended to is deliberately not asserted on: it can
# develop a real abandonment at any moment, and that is a finding rather than a
# broken test.
RUNS_RECORDED = list(range(1, 17))

# The only run that predates PR #11, by its own status-line wording.
RUN_BEFORE_THE_RECALL_FIX = 1

# Runs whose drones window never appeared in a single reading, because none of
# them ever got to space with a bay to look at. Run 16 is the interesting one:
# it sat docked for all 362 of its ticks, which is what PR #62 fixed, so it is
# evidence about the travel step and about nothing else here.
RUNS_WITHOUT_A_DRONES_WINDOW = [2, 7, 15, 16]

# What #11 and the later status-line rewrite each print beside the drone counts.
# Both are unconditional, so either one identifies a run as post-#11; the
# `recall-unanswered` clause beside the second is dropped when zero and cannot
# be used for this.
POST_RECALL_FIX_MARKERS = ["unanswered recall for", "sp out "]

# Run 1's own wording, which carries neither.
DRONE_STATUS_MARKERS = ["In bay:", "sp out "]

# The two runs with a reading where the ship is in warp and the client still
# reports drones in space. Run 1 lost them; run 11's five were in the bay by the
# reading the warp finished, which is the case the trigger must not fire on.
RUNS_IN_WARP_WITH_DRONES_OUT = [1, 11]

IN_WARP_DECISION = "I am in warp."

# A place string of the shape `placeFromReading` builds, quoted from run 11.
PLACE_OF_THE_POCKET = "Irnin, on 'Illegal Activity (3 of 3)'"
PLACE_OF_THE_STATION = "Amarr VIII (Oris)"


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Source text with every run of whitespace reduced to one space.

    Every assertion that reads `Bot.elm` goes through this, and the expected
    strings are written in the same form -- PR #58 moved where lines break and
    broke three tests that had asserted on the old layout.
    """
    return " ".join(text.split())


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def elm_maybe_sighting(sighting):
    if sighting is None:
        return "Nothing"
    count, place = sighting
    return "(Just { count = %d, place = %s })" % (count, elm_string(place))


def elm_maybe_int(value):
    return "Nothing" if value is None else "(Just %d)" % value


def abandonment_call(sighting_before=None, left_behind_before=None,
                     events_before=0, total_before=0, drones_in_space_now=None,
                     place_now=PLACE_OF_THE_POCKET, ship_left=False):
    """`droneAbandonmentAfterReading` applied to one reading's worth of facts."""
    return (
        "(droneAbandonmentAfterReading { sightingBefore = %s"
        ", leftBehindBefore = %s"
        ", eventsBefore = %d"
        ", totalBefore = %d"
        ", dronesInSpaceNow = %s"
        ", placeNow = %s"
        ", shipLeftThisReading = %s })"
        % (elm_maybe_sighting(sighting_before),
           elm_maybe_sighting(left_behind_before),
           events_before,
           total_before,
           elm_maybe_int(drones_in_space_now),
           elm_string(place_now),
           "True" if ship_left else "False"))


def function_body(source, signature_start, next_top_level):
    start = source.index(signature_start)
    end = source.index(next_top_level, start)
    return source[start:end]


def update_memory_source(source):
    """`updateMemoryForNewReadingFromGame`'s whole definition.

    Scoped, because `initBotMemory` sets the same field names a few hundred
    lines earlier and an unscoped search finds the initial values instead --
    which say nothing about whether anything can advance.
    """
    return function_body(
        source,
        "updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings",
        "\ngetNamesOfRatsInOverview :")


def let_binding_body(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding."""
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    if end is None:
        end = re.search(r"\n    in\n", rest)
    return rest[:end.start()] if end else rest


def record_field_body(source, name):
    return let_binding_body(source, name, indent="    , ")


def top_level_definitions(source):
    """Each top-level definition's name and its text, in file order."""
    starts = [(match.start(), match.group(1))
              for match in re.finditer(r"^([a-z]\w*) :", source, re.MULTILINE)]
    definitions = []
    for index, (start, name) in enumerate(starts):
        end = starts[index + 1][0] if index + 1 < len(starts) else len(source)
        definitions.append((name, source[start:end]))
    return definitions


def definitions_mentioning(source, needle):
    return sorted({name for name, text in top_level_definitions(source)
                   if needle in text})


def log_path(run):
    return os.path.join(BOT_LOGS_DIR, "mission_run%d.log" % run)


def recorded_runs():
    return [run for run in RUNS_RECORDED if os.path.exists(log_path(run))]


def readings_of_log(run):
    """The recorded run as blocks, one per `# [tick.substep]` unit.

    Reading a log a run is still appending to is safe: lines are taken one at a
    time and a trailing partial line simply ends the last block early.
    """
    block = None
    with open(log_path(run), errors="replace") as handle:
        for line in handle:
            if line.startswith("# ["):
                if block is not None:
                    yield block
                block = []
                continue
            if block is not None:
                block.append(line.rstrip("\n"))
    if block is not None:
        yield block


DRONE_COUNTS = [
    re.compile(r"In bay: (\d+), in space: (\d+)"),
    re.compile(r"drones (\d+)bay/(\d+)sp"),
]


def drones_in_space_of_reading(lines):
    """What the reading's status line says is in space, if it says anything."""
    for line in lines:
        for pattern in DRONE_COUNTS:
            match = pattern.search(line)
            if match:
                return int(match.group(2))
    return None


def elm_is_available():
    return shutil.which("elm") is not None


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, and build there -- never in the
    checked-in source. The one extra step is opening `module Bot exposing (...)`
    to `(..)`, since the repl can only call what the module exports.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-drones-left-in-space-")
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(MISSION_RUNNER_DIR, self.app)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.app, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched)

        bot = os.path.join(self.app, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened)

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def ask(self, expressions):
        # Asked as one `List Bool` rather than one expression per line,
        # because the repl recompiles the module for every line it is given.
        # Measured against this app: twenty expressions cost 36.5s a line at a
        # time and 5.8s as a single list. The answers come back in the order
        # asked either way, which is all any caller here relies on.
        if not expressions:
            return [], "", ""
        script = "import Bot exposing (..)\n[ %s ]\n" % ", ".join(expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        # The repl wraps, so `: List Bool` can land on the line after the list.
        listed = re.search(r"\[([^\]]*)\]\s*:\s*List Bool",
                           plain.replace("\n", " "))
        answers = ([answer == "True"
                    for answer in re.findall(r"True|False", listed.group(1))]
                   if listed else [])
        return answers, plain, result.stderr

    def works(self):
        """Whether the repl can evaluate anything at all here.

        Distinguishes an environment where `elm repl` cannot run from the bot
        answering wrongly. Only the first is a reason to skip.
        """
        answers, plain, stderr = self.ask(
            [abandonment_call(drones_in_space_now=0) + ".change == Nothing"])
        return answers == [True], plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """`droneAbandonmentAfterReading`, run for real."""

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here, so the rule is unchecked by "
                "execution in this environment:\n" + output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_ship_that_has_not_left_reports_nothing(self):
        on_grid = abandonment_call(drones_in_space_now=5)
        nothing_said, sighting_taken = self.repl.evaluate([
            on_grid + ".change == Nothing",
            on_grid + ".sighting == " + elm_maybe_sighting(
                (5, PLACE_OF_THE_POCKET)),
        ])
        self.assertTrue(nothing_said, "a ship still on grid reported a loss")
        self.assertTrue(sighting_taken, "the sighting was not recorded")

    def test_a_finished_warp_with_drones_still_out_is_the_event(self):
        arrived = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=5,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        latched, events, total, named = self.repl.evaluate([
            arrived + ".leftBehind == " + elm_maybe_sighting(
                (5, PLACE_OF_THE_POCKET)),
            arrived + ".events == 1",
            arrived + ".total == 5",
            "(" + arrived + ".change |> Maybe.map (String.contains "
            + elm_string(PLACE_OF_THE_POCKET) + ") |> Maybe.withDefault False)",
        ])
        self.assertTrue(latched, "the verdict did not latch")
        self.assertTrue(events, "the event was not counted")
        self.assertTrue(total, "the drones were not added to the total")
        self.assertTrue(named, "the log line does not name where they are")

    def test_the_place_is_where_they_are_not_where_the_ship_arrived(self):
        # The whole reason the sighting carries a place of its own. By the time
        # the ship has arrived it is somewhere else, and that somewhere else is
        # the one place the drones are certainly not.
        arrived = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=5,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        names_the_pocket, names_the_station = self.repl.evaluate([
            "(" + arrived + ".change |> Maybe.map (String.contains "
            + elm_string(PLACE_OF_THE_POCKET) + ") |> Maybe.withDefault False)",
            "(" + arrived + ".change |> Maybe.map (String.contains "
            + elm_string(PLACE_OF_THE_STATION) + ") |> Maybe.withDefault False)",
        ])
        self.assertTrue(names_the_pocket)
        self.assertFalse(names_the_station,
                         "the line named where the ship arrived")

    def test_run_11_s_recall_landing_during_the_align_is_not_an_event(self):
        # Run 11 spent 21 readings of `I am in warp` with five drones out and
        # had all five in the bay by the reading the warp finished. Reading the
        # start of a departure as the event would have reported a loss that did
        # not happen.
        arrived_empty = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=0,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        silent, no_verdict, no_event = self.repl.evaluate([
            arrived_empty + ".change == Nothing",
            arrived_empty + ".leftBehind == Nothing",
            arrived_empty + ".events == 0",
        ])
        self.assertTrue(silent, "a landed recall was reported as a loss")
        self.assertTrue(no_verdict)
        self.assertTrue(no_event)

    def test_docking_reports_from_the_last_reading_that_could_see_the_window(self):
        # The drones window is absent for the whole of a dock, so "how many"
        # has to have been written down before the ship arrived.
        docked = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=None,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        latched, total = self.repl.evaluate([
            docked + ".leftBehind == " + elm_maybe_sighting(
                (5, PLACE_OF_THE_POCKET)),
            docked + ".total == 5",
        ])
        self.assertTrue(latched, "the docked case reported nothing")
        self.assertTrue(total)

    def test_docking_after_a_clean_recall_reports_nothing(self):
        docked = abandonment_call(
            sighting_before=None,
            drones_in_space_now=None,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        silent, no_event = self.repl.evaluate([
            docked + ".change == Nothing",
            docked + ".events == 0",
        ])
        self.assertTrue(silent, "an ordinary dock reported a loss")
        self.assertTrue(no_event)

    def test_an_unreadable_window_does_not_clear_a_sighting(self):
        # `Nothing` from the window is "this reading cannot say", never "the
        # sky is empty" -- the distinction #15 shipped without.
        blind = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=None)
        kept, = self.repl.evaluate([
            blind + ".sighting == " + elm_maybe_sighting(
                (5, PLACE_OF_THE_POCKET)),
        ])
        self.assertTrue(kept, "one blind reading forgot the drones")

    def test_a_warp_home_and_the_dock_after_it_are_one_event(self):
        # The verdict drops the sighting, so the dock that follows the warp has
        # nothing left to report a second time.
        after_the_warp = abandonment_call(
            sighting_before=(5, PLACE_OF_THE_POCKET),
            drones_in_space_now=5,
            ship_left=True)
        sighting_dropped, = self.repl.evaluate([
            after_the_warp + ".sighting == Nothing"])
        self.assertTrue(sighting_dropped)

        then_docked = abandonment_call(
            sighting_before=None,
            left_behind_before=(5, PLACE_OF_THE_POCKET),
            events_before=1,
            total_before=5,
            drones_in_space_now=None,
            place_now=PLACE_OF_THE_STATION,
            ship_left=True)
        silent, events, total = self.repl.evaluate([
            then_docked + ".change == Nothing",
            then_docked + ".events == 1",
            then_docked + ".total == 5",
        ])
        self.assertTrue(silent, "the dock reported the same drones again")
        self.assertTrue(events, "one departure was counted twice")
        self.assertTrue(total)

    def test_a_second_abandonment_is_counted_separately(self):
        again = abandonment_call(
            sighting_before=(2, PLACE_OF_THE_STATION),
            left_behind_before=(5, PLACE_OF_THE_POCKET),
            events_before=1,
            total_before=5,
            drones_in_space_now=2,
            ship_left=True)
        events, total, newest = self.repl.evaluate([
            again + ".events == 2",
            again + ".total == 7",
            again + ".leftBehind == " + elm_maybe_sighting(
                (2, PLACE_OF_THE_STATION)),
        ])
        self.assertTrue(events)
        self.assertTrue(total, "the totals do not accumulate")
        self.assertTrue(newest, "the verdict does not name the latest event")

    def test_an_empty_sky_on_arrival_with_nothing_remembered_says_nothing(self):
        arrived = abandonment_call(drones_in_space_now=0, ship_left=True)
        silent, no_event = self.repl.evaluate([
            arrived + ".change == Nothing",
            arrived + ".events == 0",
        ])
        self.assertTrue(silent)
        self.assertTrue(no_event)


class TheDepartureIsReadAtItsEnd(unittest.TestCase):
    """Where the trigger sits, read out of the memory update."""

    @classmethod
    def setUpClass(cls):
        cls.update = update_memory_source(bot_source())
        cls.trigger = collapsed(
            let_binding_body(cls.update, "droneAbandonment"))

    def test_the_warp_half_is_the_end_of_the_warp(self):
        self.assertIn("shipLeftThisReading = weJustFinishedWarping",
                      self.trigger)

    def test_the_warp_half_is_not_the_start_of_one(self):
        # Mutating this to `shipIsEnteringWarp` or to the raw warping flag
        # reinstates run 11 as a false positive.
        self.assertNotIn("shipIsEnteringWarp", self.trigger)
        self.assertNotIn("shipIsWarping", self.trigger)

    def test_the_dock_half_needs_the_previous_reading_to_have_been_in_space(self):
        # Otherwise every reading of a dock is a fresh departure, and the whole
        # of a docked stretch reports the same drones over and over.
        self.assertIn("dockedNow && not botMemoryBefore.dockedInLastReading",
                      self.trigger)

    def test_the_window_is_asked_the_question_that_can_answer_i_do_not_know(self):
        self.assertIn("dronesInSpaceNow = dronesInSpaceCountReadable",
                      self.trigger)

    def test_docked_is_the_info_panel_naming_a_station(self):
        # Not the ship UI being absent. Run 11's tick 232 has three consecutive
        # readings of `I see no ship UI, assume we are docked` taken by a ship
        # that was demonstrably in space -- the readings either side report
        # `In bay: 3, in space: 5` and the client's combat log inside the same
        # window records this ship's guns hitting a rat. That signal would have
        # reported a departure from a ship that had not gone anywhere.
        self.assertEqual(
            collapsed(let_binding_body(self.update, "dockedNow")),
            "currentStationNameFromInfoPanel /= Nothing")
        self.assertIn("dockedInLastReading = dockedNow",
                      collapsed(self.update))


class AnUnreadableWindowIsNotAnEmptySky(unittest.TestCase):
    """The `Maybe` the bookkeeping needs, and the default nothing else loses."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def test_the_readable_count_never_defaults(self):
        body = collapsed(function_body(
            self.source,
            "dronesInSpaceCountReadable : ReadingFromGameClient -> Maybe Int",
            "\ndronesInSpaceCount :"))
        self.assertNotIn("withDefault", body)

    def test_the_old_count_is_the_readable_one_defaulted(self):
        # So every existing caller behaves exactly as it did, and there is one
        # reading of the window rather than two that can drift.
        body = collapsed(function_body(
            self.source,
            "dronesInSpaceCount : ReadingFromGameClient -> Int",
            "\ndronesAreInSpace :"))
        self.assertIn(
            "dronesInSpaceCount readingFromGameClient = "
            "dronesInSpaceCountReadable readingFromGameClient "
            "|> Maybe.withDefault 0",
            body)


class NothingActsOnTheObservation(unittest.TestCase):
    """It is a record, not a controller."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def test_the_verdict_is_read_only_where_it_is_written_and_printed(self):
        readers = definitions_mentioning(self.source, "memory.dronesLeftBehind")
        self.assertEqual(readers, ["describeDronesLeftBehindSoFar",
                                   "missionBotDecisionRoot"])

    def test_the_sighting_is_read_only_where_it_is_written(self):
        readers = definitions_mentioning(
            self.source, "botMemoryBefore.dronesInSpaceLastSeen")
        self.assertEqual(readers, ["updateMemoryForNewReadingFromGame"])

    def test_the_rule_returns_a_record_and_touches_no_reading(self):
        # It takes plain values on purpose: that is what lets it be executed
        # above rather than restated, and it is what stops it growing a
        # dependency on the client.
        body = collapsed(function_body(
            self.source,
            "droneAbandonmentAfterReading : DroneAbandonmentInput",
            "\ntype alias DroneAbandonmentInput"))
        self.assertNotIn("readingFromGameClient", body)
        self.assertNotIn("context", body)


class TheLineAndTheCounters(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def test_the_log_line_carries_no_reading_count(self):
        # One number, the drone count. A counter in a repeated line makes every
        # repeat distinct and defeats `stall_watch.py`'s dedupe -- run 126's
        # 151 variants of one alarm.
        body = function_body(
            self.source,
            "describeDronesLeftBehind : DronesInSpaceSighting -> String",
            "\ndescribeDronesLeftBehindSoFar :")
        self.assertEqual(body.count("String.fromInt"), 1)

    def test_the_counters_only_ever_rise(self):
        body = collapsed(function_body(
            self.source,
            "droneAbandonmentAfterReading : DroneAbandonmentInput",
            "\ntype alias DroneAbandonmentInput"))
        self.assertIn("events = input.eventsBefore + 1", body)
        self.assertIn("total = input.totalBefore + left.count", body)
        self.assertNotIn("- 1", body)

    def test_the_status_line_says_nothing_until_it_has_happened(self):
        body = collapsed(function_body(
            self.source,
            "describeDronesLeftBehindSoFar : BotDecisionContext -> String",
            "\nstatusTextFromState :"))
        self.assertIn('Nothing -> ""', body)

    def test_the_status_clause_survives_the_drones_window_being_gone(self):
        # The clause is appended outside the case on the window, because a
        # docked reading has no window and docked is where an operator looks.
        body = collapsed(function_body(
            self.source, "statusTextFromState : BotDecisionContext -> String",
            "\ndescribeAccelerationGate :"))
        self.assertIn(
            "describeDrones = describeDronesWindow "
            "++ describeDronesLeftBehindSoFar context",
            body)


@unittest.skipUnless(os.path.isdir(BOT_LOGS_DIR), "no recorded runs to read")
class WhatTheRecordedRunsSay(unittest.TestCase):
    """The evidence the observation was landed on instead of a recovery path.

    Asserted over the fourteen runs by name. A fifteenth is deliberately not
    covered: pinning "no run has ever done this" would turn the next real
    occurrence into a failing test rather than into the record this change
    exists to make.
    """

    @classmethod
    def setUpClass(cls):
        cls.runs = recorded_runs()
        if not cls.runs:
            raise unittest.SkipTest("none of the recorded runs are present")

    def test_the_recall_give_up_never_fired_in_any_of_them(self):
        # Since #11 this branch names itself on every reading it declines,
        # rather than only on the reading a counter was exactly 60. Zero
        # occurrences is therefore evidence rather than the silence it was
        # before -- and it is why nothing after run 1 left drones anywhere
        # through the one path that already said so.
        give_up = "will not come back"
        self.assertIn(
            give_up,
            bot_source(),
            "the give-up's wording has changed; this count means nothing")
        for run in self.runs:
            with open(log_path(run), errors="replace") as handle:
                occurrences = sum(1 for line in handle if give_up in line)
            self.assertEqual(
                occurrences, 0,
                "run %d gave up on its drones, which no recorded run had "
                "done" % run)

    def test_every_run_after_the_first_carries_the_recall_fix(self):
        # The finding rests on these runs having run the fixed code, so that is
        # checked rather than inferred from when the pull request merged.
        for run in self.runs:
            with open(log_path(run), errors="replace") as handle:
                text = handle.read()
            has_status = any(marker in text for marker in DRONE_STATUS_MARKERS)
            post_fix = any(marker in text for marker in POST_RECALL_FIX_MARKERS)
            if run in RUNS_WITHOUT_A_DRONES_WINDOW:
                self.assertFalse(
                    has_status,
                    "run %d was expected to have no drone readings" % run)
            elif run == RUN_BEFORE_THE_RECALL_FIX:
                self.assertTrue(has_status)
                self.assertFalse(
                    post_fix, "run 1 is supposed to be the pre-#11 run")
            else:
                self.assertTrue(has_status, "run %d lost its drone status" % run)
                self.assertTrue(
                    post_fix, "run %d does not carry #11's status wording, so "
                    "it cannot be counted as post-fix evidence" % run)

    def test_only_two_runs_were_ever_in_warp_with_drones_in_space(self):
        # Run 1 is the abandonment. Run 11 is the align, where all five drones
        # were in the bay by the reading the warp finished -- which is the case
        # `test_run_11_s_recall_landing_during_the_align_is_not_an_event`
        # checks the rule declines.
        found = []
        for run in self.runs:
            for lines in readings_of_log(run):
                in_space = drones_in_space_of_reading(lines)
                if not in_space:
                    continue
                if any(line.startswith("+") and IN_WARP_DECISION in line
                       for line in lines):
                    found.append(run)
                    break
        self.assertEqual(
            found, [run for run in RUNS_IN_WARP_WITH_DRONES_OUT
                    if run in self.runs])


if __name__ == "__main__":
    unittest.main()
