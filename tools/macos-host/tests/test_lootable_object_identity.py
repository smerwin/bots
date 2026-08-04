"""Tests for `nearestLootableEntry` answering about something lootable.

Issue #53. Run 12 opened wrecks correctly for 109 loot decisions and then found
no candidates at all, on a grid the operator read as covered in wrecks. Reading
the live client while it was still stuck settled what the log could not: all
twelve wrecks on that grid carried the texture `wreckLootedNPC.png`, so
`overviewEntryLooksLooted` retired them **statelessly and correctly** -- the
client itself said they were empty -- and the mission's own `Cargo Container`
had left the grid twenty seconds after the fight cleared, which the client's
game log states outright:

    [ 2026.08.03 15:20:42 ] (notify) Cargo Container has just left Irnin as of 2 seconds ago

**Run 13 settles it, and settles it against a fresh process.** The operator
restarted onto the same accepted mission. A new process starts with an empty
`BotMemory` -- no `lootedWreckIds`, no `unlootableWreckIds` -- so anything the
old run had accumulated was gone. It reached the same state on its **third
reading** and stayed there for all 495: across 6,069 log lines it decided
`Nothing to fight and no travel step offered` 483 times and never once decided
to look inside anything, never opened a loot window (`loot-open` appears zero
times), and never scrolled the overview looking for a row it wanted
(`A row I want is off screen` appears zero times).

That disproves every accumulating explanation at once, and it also says which
term in `notAlreadyEmptied` is doing the rejecting. Two of its three terms read
memory that was empty; the third, `overviewEntryLooksLooted`, is stateless and
reads the client's own icon -- and that is exactly the texture found on all
twelve wrecks. **The bot is right about them.** Recovering an objective that
can no longer be completed is a different problem, filed as #54.

So the candidate list was empty because the grid was empty, not because a
remembered id retired anything. What the same read turned up instead is a
defect one layer down, in the function that decides *which* wreck the bot is
talking about:

    nearestLootableEntry readingFromGameClient =
        readingFromGameClient.overviewWindows
            |> List.concatMap .entries
            |> List.filter (\\entry -> entry.objectItemID /= Nothing)   -- every row
            |> List.sortBy overviewEntryDistanceOrFarInMeters
            |> List.head

`missionObjectiveText`'s own comment, fifteen lines below it in the same file,
says why that is not a filter: *"Every row has one -- stargates, stations, the
sun."* It is the identical mistake, in the identical field, and this copy
survived it. So "the nearest lootable object" was answered with the nearest
object of any kind.

**Run 12's final grid is what makes that concrete.** Sixty-three overview rows,
of which twelve are wrecks and **fifty-one are not lootable by any reading** --
forty-one Sharded Rocks, three stargates, a sun, an Azbel, a trade post, a
Ruined Neon Sign, a storage silo, a mining post and a beacon. The nearest wreck
was 2,699 m away, outside `interactionRangeInMeters`. Every one of those
fifty-one rows was a candidate for "the container we have open".

Two callers read it, and both are wrong in a way nothing reports:

  * `shipIsWithinLootRange` asks whether the open container is within reach and
    was answered about whatever was physically nearest. Its false branch --
    `Still on the way to the container` -- appears **zero times across all
    thirteen recorded runs**, while run 12 alone decided `Click 'Loot All'` 109
    times. A guard that has never once been false is not a guard; it is #34's
    shape again.
  * `openWreckLootWindowAndId` uses the id it returns to record which wreck was
    emptied (`lootedWreckIds`) or written off (`unlootableWreckIds`). On this
    grid those sets could be stamped with an asteroid's id while the wreck that
    was actually emptied went unmarked.

The rule is now one shared definition, `textNamesALootableObject`, asked by the
picker, the scroller and this function, and it is executed here against the
strings the client really wrote rather than restated in Python.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
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

# Run 12's overview at the moment it was stuck, read out of the live client
# with `eve_read.py` while the run was still wedged: every distinct (Type,
# Name) pair with how many rows carried it. Sixty-three rows in total, and the
# Type/Name split is the client's own -- a wreck's Type is the hull class and
# its Name is the dead ship, so both name it and either alone would do.
RUN_12_OVERVIEW_ROWS = [
    # (Type, Name, count, is a thing that can hold loot)
    ("Gallente Small Wreck", "Federation Navy Delta II Support Frigate Wreck", 2, True),
    ("Gallente Small Wreck", "Federation Navy Soldier Wreck", 2, True),
    ("Gallente Small Wreck", "Gallente Miner Wreck", 4, True),
    ("Gallente Small Wreck", "Federation Navy Atron Wreck", 3, True),
    ("Gallente Small Wreck", "Federation Navy Officer Wreck", 1, True),
    ("Sharded Rock", "Sharded Rock", 41, False),
    ("Stargate (Amarr System)", "Amarr", 1, False),
    ("Stargate (Amarr System)", "Martha", 1, False),
    ("Stargate (Amarr System)", "Toshabia", 1, False),
    ("Azbel", "Irnin - Big Yellow Fab", 1, False),
    ("Sun K7 (Orange)", "Irnin - Star", 1, False),
    ("Amarr Trade Post", "Irnin VIII - Moon 8 - Court Chamberlain Bureau", 1, False),
    ("Ruined Neon Sign", "Ruined Neon Sign", 1, False),
    ("Gas/Storage Silo", "Storage Silo", 1, False),
    ("Asteroid Deadspace Mining Post", "Asteroid Mining Post", 1, False),
    ("Beacon", "Beacon", 1, False),
]

# The container this mission wanted, as its own row read before it left the
# grid. The bot's own decision line names it: `Look inside Cargo Container for
# the Gallente Light Marines, 43000 m away.`
MISSION_CARGO_CONTAINER_TYPE = "Cargo Container"

# Strings that must not be read as lootable, each from a bug this repo already
# paid for. The rogue drone is why `containsWords` exists at all; the station
# is why "warehouse" was narrowed to the scroller and kept out of the picker.
NOT_LOOTABLE_TRAPS = [
    "Wrecker",
    "Bhizheba VIII - Moon 5 - Expert Distribution Warehouse",
    "Cargo Warehouse",
    "Habitation Module",
    "",
]


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def without_comments(text):
    """Elm comments stripped, so an assertion cannot be satisfied by prose.

    Both block comments (`{-| ... -}`, which is where every explanation in this
    file lives) and line comments. A test that matched a name inside the very
    comment explaining why that name is gone would pass for the wrong reason.
    """
    text = re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.split("\n")
                     if not line.strip().startswith("--"))


def function_slice(source, signature_start):
    """A top-level definition, from its type signature to the next doc comment."""
    start = source.index(signature_start)
    end = source.find("\n\n\n{-|", start)
    return source[start:end] if end != -1 else source[start:]


def record_field_body(source, name):
    """The right-hand side of a `, name =` field in a record update.

    Terminated by the next field at the same indent, which may be preceded by
    the comment introducing it -- so the terminator is the `    , ` itself.
    """
    start = source.index("\n    , " + name + " =\n")
    rest = source[start + len("\n    , " + name + " =\n"):]
    end = re.search(r"\n    [,}]", rest)
    return rest[:end.start()] if end else rest


def branch_results(body):
    """What each branch of a counter body evaluates to.

    Every line that is not a comment, a blank, or part of a `case`/`if`
    scaffold is a result. Anything written some other way shows up as an
    unrecognised result and fails loudly rather than passing quietly.
    """
    results = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped == "else" or stripped.endswith(" of") or stripped.endswith("->"):
            continue
        if stripped.startswith(("if ", "else if ")) and stripped.endswith(" then"):
            continue
        results.append(stripped)
    return results


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    Same recipe as `test_dock_outranks_the_fight.py`: copy the app to scratch,
    open `module Bot exposing (..)` so the repl can reach more than `botMain`,
    patch `elm-version` to whatever this machine's elm reports, and drive it.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-lootable-identity-")
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

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def works(self):
        answers, plain, stderr = self.ask(
            ['textNamesALootableObject "Gallente Small Wreck"'])
        return answers == [True], plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRuleIsExecutedAgainstRunTwelvesOwnGrid(unittest.TestCase):
    """Every row the stuck client was holding, classified by the real rule."""

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

    def lootable_by_either_column(self, rows):
        """A row is lootable if its Type or its Name says so, as the bot asks."""
        expressions = []
        for objectType, objectName, _, _ in rows:
            expressions.append("textNamesALootableObject " + elm_string(objectType))
            expressions.append("textNamesALootableObject " + elm_string(objectName))
        answers = self.repl.evaluate(expressions)
        return [answers[index * 2] or answers[index * 2 + 1]
                for index in range(len(rows))]

    def test_every_recorded_row_is_classified_as_it_should_be(self):
        answers = self.lootable_by_either_column(RUN_12_OVERVIEW_ROWS)
        for (objectType, objectName, _, expected), got in zip(
                RUN_12_OVERVIEW_ROWS, answers):
            self.assertEqual(
                got, expected,
                "%r / %r was classified lootable=%s" % (objectType, objectName, got))

    def test_the_grid_the_bot_was_stuck_on_holds_twelve_lootable_rows_of_sixty_three(self):
        # The number is the point rather than decoration: the old filter --
        # "has an objectItemID" -- admitted all 63, so 51 rows that cannot hold
        # anything were competing to be "the container we have open".
        answers = self.lootable_by_either_column(RUN_12_OVERVIEW_ROWS)
        lootable = sum(row[2] for row, yes in zip(RUN_12_OVERVIEW_ROWS, answers) if yes)
        total = sum(row[2] for row in RUN_12_OVERVIEW_ROWS)
        self.assertEqual((lootable, total), (12, 63))

    def test_a_named_cargo_container_is_lootable(self):
        # The mission's own container, and the one the bot was flying to when
        # it left the grid. Losing this would make the whole retrieval path
        # blind to the containers a mission places deliberately.
        self.assertEqual(
            self.repl.evaluate([
                "textNamesALootableObject " + elm_string(MISSION_CARGO_CONTAINER_TYPE)]),
            [True])

    def test_the_traps_this_repo_has_already_paid_for_are_declined(self):
        answers = self.repl.evaluate(
            ["textNamesALootableObject " + elm_string(text)
             for text in NOT_LOOTABLE_TRAPS])
        self.assertEqual(answers, [False] * len(NOT_LOOTABLE_TRAPS))

    def test_the_scroller_still_reaches_a_warehouse_the_picker_will_not_open(self):
        # The two sets differ by one word on purpose. `isLootableFor` gates the
        # scroll and wants a Cargo Warehouse brought into view; the picker does
        # not open one. Asserted so that folding them together -- the obvious
        # tidy-up -- fails here rather than silently widening what the ship
        # flies to.
        source = bot_source()
        self.assertIn('containsWords "warehouse"', source)
        self.assertNotIn('"wreck", "cargo container", "warehouse"', source)


class TheNearestLootableEntryFiltersOnBeingLootable(unittest.TestCase):
    """Read out of the source, because the shape is what shipped wrong."""

    def setUp(self):
        source = bot_source()
        start = source.index("\nnearestLootableEntry : ")
        self.body = source[start:source.index("\n\n\n{-|", start)]

    def test_it_asks_the_shared_lootable_rule(self):
        self.assertIn("List.filter overviewEntryNamesALootableObject", self.body)

    def test_it_skips_rows_that_are_not_rendered(self):
        # "Reading the overview": a virtualised row keeps whatever distance was
        # last rendered into its place, and this function sorts by distance.
        self.assertIn("List.filter overviewEntryIsDisplayed", self.body)

    def test_having_an_item_id_is_not_by_itself_what_makes_a_row_lootable(self):
        # The defect exactly: `objectItemID /= Nothing` is still here, because
        # the id is what the caller stores -- but it may not be the only test.
        self.assertIn("entry.objectItemID /= Nothing", self.body)
        self.assertGreaterEqual(
            self.body.count("List.filter"), 3,
            "nearestLootableEntry is back to filtering on the item id alone, "
            "which every overview row has")

    def test_one_definition_answers_for_all_three_callers(self):
        # A signature, a definition, and exactly three call sites: the picker,
        # the scroller, and `nearestLootableEntry`. Counted with comments
        # stripped so the prose explaining the change cannot satisfy it.
        code = without_comments(bot_source())
        self.assertEqual(
            code.count("overviewEntryNamesALootableObject"), 5,
            "the picker, the scroller and nearestLootableEntry must all ask "
            "the one shared rule")
        self.assertEqual(
            code.count('[ "wreck", "cargo container" ]'), 1,
            "the word list is duplicated, so the two copies can drift apart")


class TheWaitsThisMakesReachableAreBounded(unittest.TestCase):
    """Making a guard answerable makes the branch behind it reachable.

    `shipIsWithinLootRange` can now be `False`, so
    `Still on the way to the container -- wait ...` is reachable for the first
    time in thirteen recorded runs. Its bound is `lootWindowOutOfRangeTicks`,
    and that counter used to reset whenever `openWreckLootWindowAndId` could
    not resolve a row -- which is precisely the new case, a loot window open
    with no lootable row on the overview to measure against. A bound that
    resets in the state it exists to escape is no bound at all.
    """

    COUNTERS = ["lootAllRefusedTicks", "lootWindowOutOfRangeTicks"]

    def body_for(self, name):
        return without_comments(record_field_body(bot_source(), name))

    def test_both_counters_key_off_the_open_window_not_the_resolved_row(self):
        for name in self.COUNTERS:
            body = self.body_for(name)
            self.assertIn("wreckLootWindowsFromReadingFromGameClient", body, name)
            self.assertNotIn(
                "openWreckLootWindowAndId", body,
                name + " resets whenever the wreck's overview row cannot be "
                "resolved, which is the state its bound has to age out of")

    def test_every_branch_resets_holds_starts_or_increments(self):
        for name in self.COUNTERS:
            previous = "botMemoryBefore." + name
            allowed = {"0", "1", previous, previous + " + 1"}
            for result in branch_results(self.body_for(name)):
                self.assertIn(
                    result, allowed,
                    name + " has a branch evaluating to " + repr(result))

    def test_every_counter_increments_and_resets(self):
        for name in self.COUNTERS:
            results = branch_results(self.body_for(name))
            self.assertIn("botMemoryBefore." + name + " + 1", results,
                          name + " never increments")
            self.assertIn("0", results, name + " never resets")

    def test_the_id_memories_still_need_a_resolved_row(self):
        # The other half of the split. `lootedWreckIds` and
        # `unlootableWreckIds` record an id, so they genuinely cannot act
        # without one -- and now that id is a container's rather than
        # whatever was nearest.
        for name in ["lootedWreckIds", "unlootableWreckIds"]:
            self.assertIn("openWreckLootWindowAndId", self.body_for(name), name)


class TheRejectionIsStatelessAndTheClientMakesIt(unittest.TestCase):
    """Run 13, the restart, is what rules out every accumulating explanation.

    A fresh process cannot be carrying a stale candidate set or a per-type
    "already opened" record, because it has neither. If it reaches the same
    dead end in three readings, the rejection is derived from a single reading
    -- which leaves `overviewEntryLooksLooted`, the client's own
    `wreckLootedNPC.png`, as the only term that can be doing it.

    Kept as a test rather than as prose so that a rewrite which reintroduces
    remembered state as the *primary* filter has to argue with this file.
    """

    RESTART_LOG = os.path.join(BOT_LOGS_DIR, "mission_run13.log")

    def setUp(self):
        if not os.path.exists(self.RESTART_LOG):
            self.skipTest("run 13's log is not on this machine")
        with open(self.RESTART_LOG, encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
        if lines and not lines[-1].endswith("\n"):
            lines = lines[:-1]
        self.lines = lines

    def counted(self, needle):
        return sum(1 for line in self.lines if needle in line)

    def test_the_restart_reached_the_dead_end_on_the_same_objective(self):
        self.assertGreater(
            self.counted("Retrieve <a href=\"showinfo:22802\">Gallente Light "
                         "Marines</a> from the cargo Container"), 0)
        self.assertGreater(
            self.counted("+ Nothing to fight and no travel step offered"), 0)

    def test_the_restart_never_found_a_single_candidate(self):
        # Not "fewer than before" -- none at all, on a run whose memory began
        # empty. Any accumulating filter would have had to admit the first
        # wreck at least once.
        self.assertEqual(self.counted("+ Look inside "), 0)
        self.assertEqual(self.counted("+ Open the container"), 0)

    def test_the_restart_never_opened_a_loot_window(self):
        # So nothing could have been written into either id memory either.
        self.assertEqual(self.counted("| loot-open "), 0)

    def test_virtualisation_is_not_what_hid_them(self):
        # With 63 rows and a window showing a dozen, the obvious suspect is a
        # wanted row scrolled out of view. `scrollOverviewToReveal` fires on
        # exactly that and never fired, so no row was both wanted and hidden.
        self.assertEqual(self.counted("A row I want is off screen"), 0)

    def test_the_stateless_test_is_still_first_in_the_filter(self):
        # `overviewEntryLooksLooted` is the term that answers on a cold start,
        # and it reads the client rather than anything the bot remembers.
        body = without_comments(
            function_slice(bot_source(), "\nnotAlreadyEmptied : "))
        self.assertIn("not (overviewEntryLooksLooted entry)", body)
        self.assertIn("looted", without_comments(
            function_slice(bot_source(), "\noverviewEntryLooksLooted : ")))


class TheStateTheGuardRunsInIsReachable(unittest.TestCase):
    """Asserted against the recorded runs, not against expectation.

    A guard is only worth having if the bot reaches the state it judges. The
    logs say it does, often: a loot window open is printed as `loot-open N` in
    the status line, and the decision above it is `Click 'Loot All'`.
    """

    @classmethod
    def setUpClass(cls):
        cls.logs = sorted(glob.glob(os.path.join(BOT_LOGS_DIR, "mission_run*.log")))

    def counted_across_logs(self, needle):
        total = 0
        for path in self.logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            # A run still being written leaves a partial final line; drop it.
            if lines and not lines[-1].endswith("\n"):
                lines = lines[:-1]
            total += sum(1 for line in lines if needle in line)
        return total

    def test_the_recorded_runs_reach_an_open_loot_window(self):
        if not self.logs:
            self.skipTest("no recorded runs in " + BOT_LOGS_DIR)
        self.assertGreater(
            self.counted_across_logs("| loot-open "), 0,
            "no recorded run ever had a loot window open, so nothing here "
            "judges a state the bot can be in")

    def test_the_recorded_runs_reach_the_click_this_guard_gates(self):
        if not self.logs:
            self.skipTest("no recorded runs in " + BOT_LOGS_DIR)
        self.assertGreater(self.counted_across_logs("+ Click 'Loot All'."), 0)

    def test_the_wait_branch_still_says_which_range_it_is_waiting_for(self):
        # The literal an operator greps for when this finally fires. It had
        # never appeared in a log before this change, which is the whole point.
        self.assertIn(
            '"Still on the way to the container -- wait until inside "',
            bot_source())
