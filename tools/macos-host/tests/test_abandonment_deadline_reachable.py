"""Tests for the abandonment's deadline being asked where it is always reached.

Issue #102. The comparison was right and unreachable:

    if abandonMissionGiveUpReadings <= verdict.readingsSince then

Right direction, right operands, and it sat inside
`abandonMissionThatCannotProgress`, below the docked-or-in-space split.
`readingsSince` is advanced in `updateMemoryForNewReadingFromGame`, which runs on
**every** reading unconditionally -- that is the whole point of writing verdicts
there -- so the counter and the comparison were measuring different things the
moment anything above the split held the tree.

Run 30 held it. An undismissable window kept `generalSetupInUserInterface`
answering (#101) and the two halves came apart completely:

    the counter reached                 10,811   54x a bound of 200
    the status clause printed on        32,813   log lines
    the branch printed on                  211   log lines, 0.7% of them

**And the comparison was never wrong.** On the last reading of the run the box
was gone, `generalSetupInUserInterface` declined for the first time in three
hours and forty-four minutes, the tree reached the branch, and the deadline
fired on that reading at 10,811 and ended the session. A bound that is correct
and fires immediately when it is finally asked, 54 times late, is a bound whose
only defect is where it is asked.

**This is #34's family with the halves swapped.** There a counter could never
reach its bound; here it reaches it easily and the comparison is never asked.
Both present identically from outside -- a bound that is printed, looks armed and
does not fire -- and both survive review because the arithmetic reads correctly
in isolation. CLAUDE.md's own standard is the one that catches it: *state
reachability, not just correctness*, and for a guard the missing sentence is
"...and say what guarantees the branch holding it is evaluated on the reading it
becomes true."

**The fix is placement, and the shape of the counter is deliberately unchanged.**
`abandonmentOutOfTime` is asked from the head of
`missionBotDecisionRootBeforeApplyingSettings`, above
`generalSetupInUserInterface` and above everything else, because ending a session
needs no panel expanded and no menu cleared. The counter still advances on every
reading rather than only on readings the branch was reached, and a case here pins
that: an attempt counter would have stood at 211 through run 30 and gone on
standing there, which is exactly the runaway the bound exists for. A give-up that
ends the session bounds elapsed time; a give-up that declines an action bounds
effort, which is why `droneRecallUnansweredTicks` counts the opposite way and is
pinned here too.

**#109 is not this fix and this is not #109.** That change removed one way the
tree can be held above this branch. The retreats, the pod recovery and the
wind-down all sit above it legitimately, and any future entry in that list is
another one, so the defect is the placement of the test and not the message box.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH with the app's dependencies fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
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

# The run in which the bound was live, correct and never asked.
THE_INCIDENT = "30"

# The decision line the abandonment prints on every reading it is *reached*, and
# the status clause it prints on every reading the verdict is *latched*. The
# whole issue is the gap between the two counts.
BRANCH_LINE = "+ Abandoning the mission "
STATUS_CLAUSE = "ABANDONING "

# The mission run 30 could not give back.
STUCK_MISSION = "Technological Secrets (1 of 3)"


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


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case below that asserts a branch is *absent* needs this: `collapsed`
    puts a comment on the same line as the code, and the comments here name the
    branches deliberately left elsewhere.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(source, name):
    """One top-level declaration, from its type annotation to the next gap."""
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def int_constant(name):
    """A constant read out of `Bot.elm`, so a corpus case tests the shipped
    number rather than one restated here."""
    body = declaration(bot_source(), name)
    return int(re.search(r"\n%s =\s*(\d+)" % name, "\n" + body).group(1))


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def verdict(readings_since, stalled=600, name=STUCK_MISSION):
    return "{ name = %s, stalledReadings = %d, readingsSince = %d }" % (
        elm_string(name), stalled, readings_since)


class TheDeadlineIsTheComparisonAndNothingElse(unittest.TestCase):
    """`abandonmentOutOfTime`, executed, at every boundary it has.

    Extracted as a pure rule over a record so that it can be run rather than
    restated -- and so that there is exactly one place asking it. Two would be
    two things that could disagree about whether an attempt still has time.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-abandon-deadline-")
        cls.bound = int_constant("abandonMissionGiveUpReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _expired(self, expression):
        return "abandonmentOutOfTime { missionToAbandon = %s }" % expression

    def test_no_verdict_is_never_out_of_time(self):
        # The overwhelmingly common case: nothing has been abandoned, and this
        # branch has to be invisible on every reading of every ordinary run.
        self.assertEqual(
            self.repl.evaluate(["%s == Nothing" % self._expired("Nothing")]),
            [True])

    def test_it_expires_exactly_at_the_bound(self):
        # Both sides of the boundary, because a comparison moved by one is the
        # mutation this case exists to catch.
        answers = self.repl.evaluate([
            "%s == Nothing" % self._expired("(Just %s)" % verdict(self.bound - 1)),
            "%s == Just %s" % (self._expired("(Just %s)" % verdict(self.bound)),
                               verdict(self.bound)),
        ])
        self.assertEqual(answers, [True, True])

    def test_a_fresh_verdict_has_its_whole_budget(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % self._expired("(Just %s)" % verdict(0))]),
            [True])

    def test_it_never_wraps_back_to_having_time(self):
        # Run 30's own count. A rule that expired only in a band would hand the
        # attempt back its budget on the reading after the bound, which is the
        # forever-loop with one extra step in it.
        self.assertEqual(
            self.repl.evaluate([
                "%s /= Nothing" % self._expired("(Just %s)" % verdict(10811))]),
            [True])

    def test_nothing_but_the_reading_count_decides_it(self):
        # A verdict that never stalled at all, and one on a mission with no
        # name, both still expire: anything conjoined onto the comparison is
        # another way for the deadline to be true and not fire.
        answers = self.repl.evaluate([
            "%s /= Nothing"
            % self._expired("(Just %s)" % verdict(self.bound, stalled=0)),
            "%s /= Nothing"
            % self._expired("(Just %s)" % verdict(self.bound, name="")),
        ])
        self.assertEqual(answers, [True, True])

    def test_a_control_row_rides_along(self):
        # So a repl answering `True` to everything cannot pass the cases above.
        answers = self.repl.evaluate([
            "%s == Nothing" % self._expired("(Just %s)" % verdict(0)),
            "%s == Nothing" % self._expired("(Just %s)" % verdict(self.bound)),
        ])
        self.assertEqual(answers, [True, False])


class TheGiveUpLineSaysWhatTheOperatorHasToDo(unittest.TestCase):
    """`describeAbandonmentOutOfTime`, executed.

    Printed on exactly one reading before the session ends, so unlike the
    repeating line it may carry its numbers -- and it has to, because how long
    the attempt ran is the whole of what an operator can act on.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-abandon-giveup-")
        cls.said = cls.repl.strings(
            ["describeAbandonmentOutOfTime %s" % verdict(200)])[0]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_mission_that_is_still_accepted(self):
        # "which mission did the bot throw away, and fail to" is the one fact
        # the operator needs to finish the job by hand at the agent.
        self.assertIn(STUCK_MISSION, self.said)

    def test_it_carries_both_counts(self):
        self.assertIn("200", self.said)
        self.assertIn("600", self.said)

    def test_it_says_the_count_is_readings_and_not_attempts(self):
        # New in #102, and the half run 30 could not answer. A session that ends
        # here having never reached the agent is saying something about the rest
        # of the bot rather than about the quit, and the line points at that
        # rather than leaving it to be noticed.
        self.assertIn("rather than attempts", self.said)

    def test_it_says_the_mission_still_needs_a_person(self):
        self.assertIn("by hand", self.said)
        self.assertIn("still accepted", self.said)


class TheDeadlineIsAskedWhereNothingCanBeAboveIt(unittest.TestCase):
    """The placement, which is the whole fix.

    A bound tested where the tree happens to reach is not a bound. The list at
    the top of `missionBotDecisionRootBeforeApplyingSettings` is the last thing
    evaluated on every reading whatever else is going on, and this has to be its
    first entry.
    """

    def setUp(self):
        self.source = bot_source()
        start = self.source.index(
            "missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nendSessionOnAnExpiredBound :", start)
        self.root = collapsed(without_comments(self.source[start:end]))

    def test_it_is_the_first_entry_in_the_pre_split_list(self):
        pre_split = self.root[:self.root.index("branchDependingOnDockedOrInSpace")]
        self.assertIn("endSessionOnAnExpiredBound context", pre_split)
        for below in ["generalSetupInUserInterface", "recoverPodAfterShipLoss",
                      "windDownBeforeSessionEnd"]:
            self.assertLess(
                pre_split.index("endSessionOnAnExpiredBound context"),
                pre_split.index(below),
                "%s can decline to answer, so anything below it can be starved "
                "-- which is what run 30 did to this very comparison" % below)

    def test_it_is_above_the_user_interface_setup_in_particular(self):
        # `generalSetupInUserInterface` is the one that actually held run 30,
        # and #109 bounded that instance. This case is about the shape: ending a
        # session needs no panel expanded and no menu cleared, so there is no
        # reason for the setup list to outrank a deadline that has expired.
        self.assertLess(
            self.root.index("endSessionOnAnExpiredBound context"),
            self.root.index("generalSetupInUserInterface"))

    def test_the_branch_only_ends_the_session(self):
        # It has no work to do and no state to reach, which is what lets it be
        # evaluated on any reading at all. A branch up here that clicked or
        # waited would need the setup list it is placed above.
        body = collapsed(without_comments(
            declaration(self.source, "endSessionOnAnExpiredBound")))
        self.assertIn("Common.DecisionPath.endDecisionPath FinishSession", body)
        for acting in ["waitForProgressInGame", "askForHelpToGetUnstuck",
                       "useContextMenuCascade", "mouseClickOnUIElement",
                       "travelToStationByName", "endDecisionPath ContinueSession"]:
            self.assertNotIn(
                acting, body,
                "the expired-deadline branch must do nothing but end the "
                "session -- anything else gives it a reason to be placed lower")

    def test_the_comparison_exists_in_exactly_one_place(self):
        # Two would be two things that could disagree, and the one inside
        # `abandonMissionThatCannotProgress` is the one run 30 never reached.
        asked_in = [name for name in
                    ["abandonmentOutOfTime", "abandonMissionThatCannotProgress",
                     "describeMissionAbandonment", "endSessionOnAnExpiredBound"]
                    if "abandonMissionGiveUpReadings"
                    in collapsed(without_comments(
                        declaration(self.source, name)))]
        self.assertEqual(
            asked_in, ["abandonmentOutOfTime", "describeMissionAbandonment"],
            "the deadline is compared in `abandonmentOutOfTime` and printed in "
            "the status line, and nowhere else")

    def test_the_attempt_branch_is_only_reached_while_it_has_time(self):
        body = collapsed(without_comments(
            declaration(self.source, "abandonMissionThatCannotProgress")))
        self.assertNotIn("FinishSession", body,
                         "the attempt no longer decides when the session ends")
        self.assertIn("quitMissionInConversation context verdict conversation",
                      body,
                      "and everything it did before the give-up is unchanged")


class TheCounterStillCountsReadingsAndNotAttempts(unittest.TestCase):
    """The half of the issue that is a choice rather than a defect.

    The other shape available was to advance `readingsSince` only on readings
    this branch was reached on, so that 200 means 200 *attempts*. It reads
    better and it is wrong for a deadline that ends the session: a bot held
    elsewhere would spend none of the budget, which is precisely the runaway.
    Run 30 reached the branch on 211 readings in three and three-quarter hours,
    so an attempt counter would have stood at 211 and gone on standing there.
    """

    def setUp(self):
        self.source = bot_source()
        self.update = declaration(self.source,
                                  "updateMemoryForNewReadingFromGame")

    def test_the_clock_advances_on_every_reading_the_verdict_is_latched(self):
        latched = collapsed(self.update)
        self.assertIn(
            "if trackerStillShowsMission context.readingFromGameClient "
            "latched.name then Just { latched | readingsSince = "
            "latched.readingsSince + 1 }", latched,
            "the only condition on the clock is that the mission is still "
            "there -- conditioning it on what the bot managed to do turns the "
            "bound into a count of attempts, which run 30 shows is no bound")

    def test_nothing_about_the_decision_reaches_the_clock(self):
        latched = collapsed(self.update)
        clause = latched[latched.index("case botMemoryBefore.missionToAbandon of"):]
        clause = clause[:clause.index("messageBoxStandoff")]
        for from_the_tree in ["previousStepDispatchedEffects",
                              "previousStepsEffectsPressedMouse",
                              "agentConversationWindows", "shipUI"]:
            self.assertNotIn(
                from_the_tree, clause,
                "the abandonment clock must not consult what the bot was able "
                "to do with a reading")

    def test_the_drone_recall_counts_the_other_way_on_purpose(self):
        """The counter-example, so the two cannot be conflated.

        `droneRecallUnansweredTicks` deliberately advances only where the bot
        actually asked -- it reads the ask out of `previousStepsEffects` -- and
        is right to, because its give-up *declines an action* rather than ending
        the session. A fight that legitimately kept the bot elsewhere must not
        spend a budget whose purpose is to bound a repeated ask.
        """
        recall = collapsed(self.update)
        clause = recall[recall.index(", droneRecallUnansweredTicks ="):]
        clause = clause[:clause.index(", dronesInSpaceLastSeen")]
        self.assertIn("recentStepAskedForDroneRecall context.previousStepsEffects",
                      clause)

    def test_the_status_line_still_carries_the_count_against_the_bound(self):
        status = collapsed(declaration(self.source,
                                       "describeMissionAbandonment"))
        self.assertIn("String.fromInt verdict.readingsSince", status)
        self.assertIn("String.fromInt abandonMissionGiveUpReadings", status)


class RunThirtyIsTheEvidence(unittest.TestCase):
    """The recorded incident, recounted as the relations the fix rests on.

    Relations rather than numbers, which is `test_travel_outranks_the_fight.py`'s
    lesson: a corpus that grows must not turn a true claim red.
    """

    def _run_thirty(self):
        (name, path), = recorded_runs(THE_INCIDENT)
        return name, path

    def _counts(self):
        _, path = self._run_thirty()
        branch = status = highest = 0
        pattern = re.compile(r"quitting it for (\d+) of (\d+)")
        with open(path, encoding="utf-8", errors="ignore") as log:
            for line in log:
                if line.startswith(BRANCH_LINE):
                    branch += 1
                if STATUS_CLAUSE in line:
                    status += 1
                    found = pattern.search(line)
                    if found:
                        highest = max(highest, int(found.group(1)))
        return branch, status, highest

    def test_the_counter_ran_far_past_the_bound(self):
        bound = int_constant("abandonMissionGiveUpReadings")
        _, _, highest = self._counts()
        self.assertGreater(
            highest, bound * 50,
            "run 30 is supposed to be the run in which the printed count ran "
            "away from the bound it was being printed against")

    def test_the_branch_holding_the_bound_was_reached_on_almost_nothing(self):
        # The asymmetry itself, in one comparison. The counter had every
        # reading; the comparison had 0.7% of them.
        branch, status, _ = self._counts()
        self.assertGreater(status, 10000)
        self.assertGreater(branch, 0, "the branch has to have run at all")
        self.assertLess(
            branch * 100, status,
            "run 30 is the run in which the verdict was latched on two orders "
            "of magnitude more readings than the branch testing its bound was "
            "reached on")

    def test_the_give_up_fired_the_instant_the_branch_was_finally_reached(self):
        """The strongest thing run 30 says, and the whole diagnosis in one line.

        The comparison was never wrong and was never disabled. On the last
        reading of the run the box was gone, `generalSetupInUserInterface`
        declined for the first time in three hours and forty-four minutes, the
        tree reached the branch, and the deadline fired **on that reading** at
        10,811 -- the highest count the run ever printed. A bound that is
        correct and fires immediately when asked, 54 times late, is a bound
        whose only defect is where it is asked.
        """
        # Read out of the source, so a reworded give-up keeps this honest.
        marker = "and have not managed it"
        self.assertIn(
            marker,
            collapsed(declaration(bot_source(), "describeAbandonmentOutOfTime")),
            "this case is checking for the give-up sentence the bot ships")
        _, path = self._run_thirty()
        with open(path, encoding="utf-8", errors="ignore") as log:
            fired = [line for line in log if marker in line]
        self.assertEqual(
            len(fired), 1,
            "the give-up prints on exactly one reading, and then the session "
            "ends")
        _, _, highest = self._counts()
        printed = int(re.search(r"for (\d+) readings", fired[0]).group(1))
        self.assertGreaterEqual(
            printed, highest,
            "the deadline fired at the highest count the run reached, which is "
            "what 'correct, and never asked' looks like from outside")
        self.assertGreater(printed, int_constant(
            "abandonMissionGiveUpReadings") * 50)


if __name__ == "__main__":
    unittest.main()
