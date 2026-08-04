"""Tests for the mission runner knowing whether it has read a briefing at all.

Issue #108. `briefingSaysClearingIsOptional` is right and names the exact mission
run 32 lost a session to; it never ran, because the evidence never arrived. A
briefing is readable only while the agent conversation is open, and run 32 never
opened one: `Recon (1 of 3)` was accepted in run **31**, run 32 was cycled onto
it mid-flight, and across its 784 readings it clicked `Accept the mission` zero
times while spending all 2,861 of its decision blocks trying to kill eleven
cruisers on the one mission whose briefing says in writing that it need not be
done. The operator stopped it and flew the ship out by hand.

The defect was in the *remembered* answer rather than in the matcher.
`clearingNotRequired : Bool` initialised to `False`, so "the briefing said clear
them" and "I have never seen a briefing" were the same value -- and it was one
answer for the whole session, so a "clearing is optional" read from one mission
also stood over the next one until that one's briefing happened to be read.

Both of those cost something and they are not the same cost, which is what these
cases are mostly about:

- a session that has never read a briefing now *clears the field*, deliberately,
  because leaving rats alive on a pocket that has to be cleared strands the ship
  at a gate that will not open -- worse than a session spent shooting;
- a briefing read for another mission no longer answers for this one, because
  that failure points the other way.

So the direction is unchanged and the conflation is gone, and the third thing
these cases pin is that the bot *says* which case it is in, on every reading:
`describeClearing` is in the status line unconditionally while a mission is
tracked, because run 32's log contains no line at all recording that an
assumption was being made.

Nothing here reads a live game client or drives a bot, and nothing depends on a
run being finished -- a log still being appended to is read line by line and its
final partial line skipped. The `elm repl` cases need `elm` on PATH and the app's
dependencies already fetched, which is what `compile_bot.sh` leaves behind;
without it they **fail** rather than skipping, for the reason `prerequisites.py`
gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The mission run 32 lost its session to, as the tracker and the agent's own
# briefing both write it.
RECON = "Recon (1 of 3)"

# The next mission in the same chain. Whole-string comparison is what keeps
# these apart -- the names differ only in the counter, so a substring test would
# carry one mission's verdict onto the other, which is exactly the leak the
# per-mission entries exist to close.
RECON_NEXT = "Recon (2 of 3)"

# The clause `briefingSaysClearingIsOptional` matches, quoted from the Recon
# briefing the recordings hold. The corpus check below asserts it is still there.
RECON_CLAUSE = "Destroying any pirates found in the area is not a requirement"

# A mission whose briefing mentions pirates and asks for them dead. Quoted from
# the recordings for the same reason: "pirate" alone must not switch the fight
# off, and this is the client's own counterexample.
FIGHTING_MISSION = "Avenge a Fallen Comrade"
FIGHTING_CLAUSE = ("Destroy the habitat of the pirate leaders then report back "
                   "to your agent.")


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this, and the
    expected strings are written the same way.
    """
    return " ".join(text.split())


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def elm_maybe_string(value):
    return "Nothing" if value is None else "(Just %s)" % elm_string(value)


def verdict(mission_name, clearing_is_optional):
    return "{ missionName = %s, clearingIsOptional = %s }" % (
        elm_string(mission_name), "True" if clearing_is_optional else "False")


def elm_verdict_list(verdicts):
    return "[ %s ]" % ", ".join(verdicts) if verdicts else "[]"


def clearing_case(briefings_read, mission_name_now):
    return "clearingCase { briefingsRead = %s, missionNameNow = %s }" % (
        elm_verdict_list(briefings_read), elm_maybe_string(mission_name_now))


def briefing(mission_name, terms_are_on_screen, fine_print):
    return ("clearingVerdictFromBriefing { missionName = %s, "
            "termsAreOnScreen = %s, finePrint = %s }"
            % (elm_maybe_string(mission_name),
               "True" if terms_are_on_screen else "False",
               elm_string(fine_print)))


def recorded_briefings(test_case):
    """Every mission briefing the recordings hold, by the name the bot quoted.

    The bot prints the agent's whole fine print on the reading it accepts a
    mission (and on the two skip paths that carry it), so the recordings are a
    corpus of real briefings paired with the mission names the client wrote.
    That is what the matcher is asked about below, rather than about strings
    invented here.
    """
    paths = sorted(glob.glob(os.path.expanduser(
        "~/eve-bot-logs/mission_run*.log")))
    if not paths:
        test_case.skipTest("no recorded runs in ~/eve-bot-logs")
    pattern = re.compile(
        r"^\++ (?:Accept the mission|'?)(?P<lead>.*?)'(?P<name>[^']*)'"
        r"(?:\.| does not admit this ship -- skip it with '[^']*'\.) "
        r"(?P<fine_print>.+)\n$")
    briefings = {}
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as log:
            for line in log:
                if not line.endswith("\n"):
                    # The last line of a run still in progress.
                    continue
                match = pattern.match(line)
                if match and match.group("lead").strip() in ("", "'"):
                    briefings.setdefault(match.group("name"),
                                         match.group("fine_print").strip())
    test_case.assertTrue(
        briefings,
        "the recorded runs are here and carry no mission briefings at all, "
        "which is the third answer rather than the second: evidence present "
        "and not saying what these cases read out of it")
    return briefings


def readings_and_briefings(path):
    """(readings, briefings seen, mission names tracked) for one recorded run.

    The unit is the **reading**, not the decision line, for `stall_watch.py`'s
    reason: the bot re-derives its whole decision path several times per look at
    the game, so counting decision blocks counts one state a dozen times.
    """
    readings = set()
    briefings = 0
    missions = set()
    head = re.compile(r"^# \[(?P<tick>\d+)\.\d+\] ")
    tracked = re.compile(r" Mission: (?P<name>.*?) -- ")
    saw_briefing = ("Accept the mission", "Skip this mission",
                    "does not admit this ship")
    with open(path, encoding="utf-8", errors="replace") as log:
        for line in log:
            if not line.endswith("\n"):
                continue
            match = head.match(line)
            if match:
                readings.add(match.group("tick"))
                named = tracked.search(line)
                if named:
                    missions.add(named.group("name"))
            if any(phrase in line for phrase in saw_briefing):
                briefings += 1
    return len(readings), briefings, missions


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """`clearingCase` and `clearingIsOptional`, run for real."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-clearing-case-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_run_32_s_own_state_clears_the_field(self):
        """The chosen direction, and the one that costs a session.

        No briefing read this session and a Recon pocket on the grid. The bot
        fights, exactly as it did -- what changed is that this is now an answer
        rather than an initialiser.
        """
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)" % clearing_case([], RECON)]),
            [False])

    def test_the_briefing_read_for_this_mission_switches_the_fight_off(self):
        # The whole point of the matcher, and the case that has to keep working:
        # a briefing read for the mission being flown is the client saying in
        # writing that the fight is not the job.
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)"
                % clearing_case([verdict(RECON, True)], RECON)]),
            [True])

    def test_another_mission_s_briefing_does_not_answer_for_this_one(self):
        """The other direction of the same conflation, and the worse one.

        One session-wide `Bool` kept the last briefing's answer until another
        overwrote it, so an optional-clearing verdict stood over whatever came
        next. Leaving a pocket alive that has to be cleared strands the ship at
        a gate the client opens only once the vicinity is clear.
        """
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)"
                % clearing_case([verdict(FIGHTING_MISSION, True)], RECON)]),
            [False])

    def test_the_name_is_matched_whole_and_not_as_a_substring(self):
        # `missionNameForDeclining` wants the opposite behaviour and says why:
        # a chain's missions differ only by `(N of 3)`. Here a substring test
        # would hand one mission's briefing to the next room of a chain that
        # does need clearing.
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)"
                % clearing_case([verdict(RECON, True)], RECON_NEXT),
                "clearingIsOptional (%s)"
                % clearing_case([verdict(RECON, True)], RECON),
            ]),
            [False, True])

    def test_a_briefing_that_says_nothing_about_clearing_clears_the_field(self):
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)"
                % clearing_case([verdict(FIGHTING_MISSION, False)],
                                FIGHTING_MISSION)]),
            [False])

    def test_a_read_briefing_and_an_unread_one_are_different_values(self):
        """The bug, asserted directly.

        Both clear the field, and that is deliberate -- but they must not be the
        same value, because the status line has to be able to tell an operator
        which of them the bot is in, and because a later rule that wants to act
        on "we are guessing" needs something to act on.
        """
        answers = self.repl.evaluate([
            "(%s) == (%s)" % (
                clearing_case([verdict(FIGHTING_MISSION, False)],
                              FIGHTING_MISSION),
                clearing_case([], FIGHTING_MISSION)),
            "(%s) == (%s)" % (
                clearing_case([verdict(FIGHTING_MISSION, False)],
                              FIGHTING_MISSION),
                clearing_case([verdict(FIGHTING_MISSION, False)],
                              FIGHTING_MISSION)),
        ])
        self.assertEqual(answers, [False, True],
                         "an unread briefing and one that said nothing must be "
                         "distinguishable, and a case must equal itself")

    def test_a_tracker_that_names_no_mission_clears_the_field(self):
        # Nothing to match a verdict against, so nothing may switch the fight
        # off -- including a briefing read moments earlier for a mission the
        # panel is no longer showing.
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)" % clearing_case([], None),
                "clearingIsOptional (%s)"
                % clearing_case([verdict(RECON, True)], None),
            ]),
            [False, False])

    def test_the_answer_is_the_mission_s_own_among_several(self):
        # A session reads a briefing per mission and keeps them all, so the
        # lookup has to pick this mission's out of the pile rather than the
        # newest.
        several = [verdict(RECON, True),
                   verdict(FIGHTING_MISSION, False),
                   verdict(RECON_NEXT, False)]
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (%s)" % clearing_case(several, RECON),
                "clearingIsOptional (%s)" % clearing_case(several, RECON_NEXT),
                "clearingIsOptional (%s)"
                % clearing_case(several, FIGHTING_MISSION),
            ]),
            [True, False, False])


class TheBriefingHasToNameItsOwnMission(unittest.TestCase):
    """`clearingVerdictFromBriefing` -- the attribution, not the matching."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-clearing-briefing-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_named_briefing_on_screen_answers_for_that_mission(self):
        answers = self.repl.evaluate([
            "(%s |> Maybe.map .missionName) == Just %s" % (
                briefing(RECON, True, RECON_CLAUSE), elm_string(RECON)),
            "(%s |> Maybe.map .clearingIsOptional) == Just True"
            % briefing(RECON, True, RECON_CLAUSE),
        ])
        self.assertEqual(answers, [True, True])

    def test_terms_that_are_not_on_screen_are_not_a_briefing(self):
        """`objectiveHtml` is where the terms live and it goes with the window.

        This is the half that was already right, and it has to stay right: a
        conversation carrying no terms must leave the remembered answer alone
        rather than overwrite it with a verdict read from nothing.
        """
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % briefing(RECON, False, RECON_CLAUSE)]),
            [True])

    def test_a_briefing_that_names_no_mission_is_dropped(self):
        """The attribution that would put #108 back, pointing the other way.

        The conversation on screen is as often an offer the bot is about to skip
        as it is the mission being flown, so a nameless briefing pinned on the
        tracked mission could switch the fight off on a pocket that has to be
        cleared. Dropping it leaves the mission unanswered, and an unanswered
        mission is one the bot clears.
        """
        answers = self.repl.evaluate([
            "%s == Nothing" % briefing(None, True, RECON_CLAUSE),
            "%s == Nothing" % briefing("", True, RECON_CLAUSE),
            "%s == Nothing" % briefing("   ", True, RECON_CLAUSE),
            # The control, so a repl answering `Nothing` to everything cannot
            # pass this by refusing all four.
            "%s == Nothing" % briefing(RECON, True, RECON_CLAUSE),
        ])
        self.assertEqual(answers, [True, True, True, False])

    def test_the_name_arrives_trimmed(self):
        # It is compared against `missionNameFromTracker`, which trims, so a
        # briefing whose subheader carries padding has to trim too or the
        # lookup never matches and every such mission reads as unread.
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.map .missionName) == Just %s" % (
                    briefing("  " + RECON + "  ", True, RECON_CLAUSE),
                    elm_string(RECON))]),
            [True])

    def test_pirates_alone_do_not_make_clearing_optional(self):
        # The client's own counterexample, and why the matcher wants two
        # clauses rather than one.
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.map .clearingIsOptional) == Just False"
                % briefing(FIGHTING_MISSION, True, FIGHTING_CLAUSE)]),
            [True])


class TheVerdictSurvivesTheConversationClosing(unittest.TestCase):
    """`rememberClearingVerdict`, folded the way the memory update folds it."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-clearing-memory-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _remembered(self, verdicts):
        return ("(List.foldl rememberClearingVerdict [] %s)"
                % elm_verdict_list(verdicts))

    def test_the_answer_outlives_the_briefing(self):
        """The property the old field had and this must not lose.

        The briefing closes long before the rooms it describes are fought, so a
        verdict that only existed while the window was open would never reach
        the pocket -- `loadRefusedByClient`'s failure.
        """
        remembered = self._remembered([verdict(RECON, True)])
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (clearingCase { briefingsRead = %s, "
                "missionNameNow = %s })" % (remembered, elm_maybe_string(RECON))
            ]),
            [True])

    def test_a_second_mission_does_not_displace_the_first(self):
        # The old field's whole failure mode: one answer, overwritten. Both
        # missions have to keep their own, because a session flies several and
        # a chain can come back to one.
        remembered = self._remembered(
            [verdict(RECON, True), verdict(FIGHTING_MISSION, False)])
        self.assertEqual(
            self.repl.evaluate([
                "clearingIsOptional (clearingCase { briefingsRead = %s, "
                "missionNameNow = %s })" % (remembered, elm_maybe_string(RECON)),
                "clearingIsOptional (clearingCase { briefingsRead = %s, "
                "missionNameNow = %s })"
                % (remembered, elm_maybe_string(FIGHTING_MISSION)),
            ]),
            [True, False])

    def test_re_reading_a_briefing_replaces_rather_than_accumulates(self):
        """The conversation stays open for several readings.

        Appending would hold one mission's answer once per reading the window
        was up, and the newest read has to win -- the client speaking now
        outranks the client having spoken earlier.
        """
        rewritten = self._remembered(
            [verdict(RECON, True), verdict(RECON, False)])
        answers = self.repl.evaluate([
            "List.length %s == 1" % rewritten,
            "clearingIsOptional (clearingCase { briefingsRead = %s, "
            "missionNameNow = %s })" % (rewritten, elm_maybe_string(RECON)),
        ])
        self.assertEqual(answers, [True, False])

    def test_forty_readings_of_one_open_conversation_leave_one_entry(self):
        # The shape the memory update actually produces: the same verdict
        # arriving on every reading the window is up.
        held = self._remembered([verdict(RECON, True)] * 40)
        self.assertEqual(self.repl.evaluate(["List.length %s == 1" % held]),
                         [True])


class TheClientsOwnBriefingsAreWhatItIsMatchedAgainst(unittest.TestCase):
    """Every briefing the recordings hold, through the real rule."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-clearing-corpus-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_exactly_the_recon_briefing_makes_clearing_optional(self):
        """The claim the matcher's own doc comment makes, re-run.

        Every mission briefing in the recordings goes through
        `clearingVerdictFromBriefing`, and the ones that come back optional are
        compared against the mission this issue is about. A second mission
        appearing here is not necessarily wrong -- the wordings are the client's
        -- but it is a change nobody decided, which is what this is for.
        """
        briefings = recorded_briefings(self)
        names = sorted(briefings)
        answers = self.repl.evaluate([
            "(%s |> Maybe.map .clearingIsOptional) == Just True"
            % briefing(name, True, briefings[name]) for name in names])
        optional = [name for name, yes in zip(names, answers) if yes]
        self.assertEqual(
            optional, [RECON],
            "the recorded briefings that read as optional are not the one "
            "mission this rule was measured against")

    def test_every_recorded_briefing_is_attributed_to_its_own_mission(self):
        # The name the verdict carries is the name the log quoted, for every
        # briefing the client ever wrote here -- so the lookup against the
        # tracker is comparing like with like.
        briefings = recorded_briefings(self)
        names = sorted(briefings)
        answers = self.repl.evaluate([
            "(%s |> Maybe.map .missionName) == Just %s"
            % (briefing(name, True, briefings[name]), elm_string(name))
            for name in names])
        wrong = [name for name, yes in zip(names, answers) if not yes]
        self.assertEqual(wrong, [])

    def test_the_recon_clause_is_still_in_the_recordings(self):
        # The anchor every case above rests on. If the client stops writing it,
        # the matcher is resting on nothing and somebody should know.
        briefings = recorded_briefings(self)
        self.assertIn(RECON, briefings,
                      "the recordings no longer contain the Recon briefing")
        self.assertIn(RECON_CLAUSE.lower(), briefings[RECON].lower())

    def test_a_briefing_naming_pirates_and_wanting_them_dead_is_there_too(self):
        # The negative half of the same anchor. Without a real briefing that
        # says "pirate" and means it, "pirate" plus "not required" would be two
        # clauses where one would have done.
        briefings = recorded_briefings(self)
        self.assertIn(FIGHTING_MISSION, briefings)
        self.assertIn("pirate", briefings[FIGHTING_MISSION].lower())


class TheRecordedRunsSayThisIsNotAnEdgeCase(unittest.TestCase):
    """A run flying a mission whose briefing it never read is the common case."""

    def test_run_32_never_had_a_briefing_on_screen(self):
        # The incident, re-derived rather than quoted. A run with no briefing on
        # any reading is a run for which the old `False` was an initialiser and
        # not an answer.
        for name, path in recorded_runs("32"):
            readings, briefings, missions = readings_and_briefings(path)
            self.assertEqual(
                briefings, 0,
                "run %s is the incident because it never saw a briefing" % name)
            self.assertGreater(readings, 500)
            self.assertEqual(
                missions, {RECON},
                "run %s flew one mission from its first reading to its last"
                % name)

    def test_run_33_reached_the_same_pocket_on_the_same_evidence(self):
        # Killed a few readings in, on the same mission, with the same absence
        # of any briefing -- so the state is reproducible rather than a one-off.
        for name, path in recorded_runs("33"):
            _, briefings, missions = readings_and_briefings(path)
            self.assertEqual(briefings, 0)
            self.assertEqual(missions, {RECON})

    def test_a_large_share_of_recorded_runs_never_saw_a_briefing(self):
        """The reason `Nothing` needed a chosen answer rather than a default.

        Asserted as a share rather than as the count it was measured at (13 of
        34), so a corpus that grows cannot make a true claim red.
        """
        paths = sorted(glob.glob(os.path.expanduser(
            "~/eve-bot-logs/mission_run*.log")))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        blind = [path for path in paths
                 if readings_and_briefings(path)[1] == 0]
        self.assertGreaterEqual(
            len(blind), len(paths) // 4,
            "flying a mission whose briefing this session never read is meant "
            "to be the ordinary case, and this corpus no longer says so")

    def test_the_briefing_and_the_tracker_write_the_same_name(self):
        """What makes the per-mission lookup work at all.

        The verdict is filed under the briefing's own name and looked up under
        the tracker's, so the two have to be the same string. Asserted as a
        majority rather than as 331 of 361: the accepts that never appear are
        missions the tracker never showed, which is the untracked-mission state
        `agentConversationWithoutTrackerTicks` already exists for.
        """
        paths = sorted(glob.glob(os.path.expanduser(
            "~/eve-bot-logs/mission_run*.log")))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        accepted = re.compile(r"^\++ Accept the mission '(?P<name>.*?)'\. ")
        tracked = re.compile(r"^# \[\d+\.\d+\] .* Mission: (?P<name>.*?) -- ")
        agree = 0
        total = 0
        for path in paths:
            names_after = []
            accepts = []
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    if not line.endswith("\n"):
                        continue
                    match = accepted.match(line)
                    if match:
                        accepts.append((match.group("name"), len(names_after)))
                        continue
                    match = tracked.match(line)
                    if match:
                        names_after.append(match.group("name"))
            for name, seen_before in accepts:
                total += 1
                if name in names_after[seen_before:]:
                    agree += 1
        self.assertTrue(
            total,
            "the recorded runs are here and none of them ever accepted a "
            "mission, so there is nothing to compare the two names across")
        self.assertGreater(
            agree * 10, total * 8,
            "the agent's own mission name and the tracker's have come apart, "
            "which would leave every mission reading as one with no briefing")


class TheSourceSaysWhichDirectionItFailsIn(unittest.TestCase):
    """The choice is in the source, where a reader will meet it."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def _declaration(self, name):
        start = self.source.index("\n%s :" % name)
        return collapsed(self.source[start:self.source.index("\n\n\n", start)])

    def test_only_a_briefing_read_for_this_mission_answers_true(self):
        # Read out of the source as well as executed above, because the thing
        # that matters is that every other case is written down and answered
        # rather than swept up by a wildcard nobody chose.
        body = self._declaration("clearingIsOptional")
        self.assertEqual(body.count("True"), 1, body)
        self.assertEqual(body.count("False"), 3, body)
        for constructor in ("ThisBriefingSaysClearingIsOptional",
                            "ThisBriefingSaysNothingAboutClearing",
                            "NoBriefingReadForThisMission",
                            "NoMissionTracked"):
            self.assertIn(
                "%s _ ->" % constructor, body,
                "every case is named and answered here, so a fifth cannot "
                "inherit an answer nobody decided on through a wildcard")

    def test_the_memory_holds_one_entry_per_mission_and_starts_empty(self):
        self.assertIn(", briefingsRead : List ClearingVerdict", self.source)
        self.assertIn(", briefingsRead = []", self.source)
        self.assertNotIn("clearingNotRequired", self.source,
                         "the session-wide Bool is what #108 is about")

    def test_the_memory_update_never_defaults_the_answer(self):
        start = self.source.index("\n    , briefingsRead =\n")
        clause = collapsed(self.source[start:self.source.index(
            "\n    , siteAdmitsThisShip =", start)])
        self.assertIn("List.foldl rememberClearingVerdict", clause)
        self.assertNotIn("Maybe.withDefault", clause,
                         "defaulting is how absent evidence became a positive "
                         "finding in the first place")

    def test_the_status_line_says_which_case_every_reading(self):
        self.assertIn("[ describeClearing context ]", self.source)
        naming = self._declaration("describeClearing")
        self.assertIn("NO BRIEFING READ this session", naming)
        self.assertIn("an assumption rather than a reading", naming)

    def test_the_fight_asks_the_rule_rather_than_the_memory(self):
        # One choke point. A branch reading `briefingsRead` directly would be
        # deciding the lookup for itself, which is where the two copies of
        # "was this just emptied" went wrong in #45.
        readers = [line for line in self.source.splitlines()
                   if "memory.briefingsRead" in line]
        self.assertEqual(
            [collapsed(line) for line in readers],
            ["{ briefingsRead = context.memory.briefingsRead"],
            "clearingCaseForContext is meant to be the only reader")


if __name__ == "__main__":
    unittest.main()
