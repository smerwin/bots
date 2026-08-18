"""Tests for saxrat's pod-recovery deadline being asked where it is reached.

Issue #133, which is the mission runner's #126 in saxrat's copy of the same
branch. The comparison was right and unreachable:

    if podRecoveryGiveUpReadings <= shipLoss.readingsSince then

`shipLoss.readingsSince` is advanced by `shipLossVerdictAfter` from
`updateMemoryForNewReadingFromGame`, which runs on **every** reading and
consults nothing about what the bot managed to do with it. The comparison sat
inside `recoverPodAfterShipLoss`, which
`anomalyBotDecisionRootBeforeApplyingSettings` reaches only after
`generalSetupInUserInterface` has declined -- so anything answering up there
starved the bound while the number it is compared against went on climbing.

**The starvation was unguarded here when this landed, and that was the
difference from the mission runner rather than a restatement of it.** #109
answered that bot's run 30 -- an undismissable window that held
`generalSetupInUserInterface` for 32,585 readings, three hours and forty-four
minutes -- with `MessageBoxStandoff`, and none of it had been ported: saxrat's
`closeMessageBox` clicked its dismissal every reading for as long as a box was
showing, counting nothing. #138 ported it, so both ends are covered now, and
**neither makes the other redundant** -- the ladder bounds one known starver
while this hoist covers whatever else holds the list.
`WhatSaxratHasAgainstAMessageBoxStandoffTest` checks that relation out of the
two sources rather than leaving it remembered.

**Two of PR #132's conclusions hold here unchanged and one does not.** The
expired branch is `endDecisionPath FinishSession` and nothing else, so it hoists;
the recovery is an errand and does not. What differs is the *reason* the ship UI
has to be a condition. The mission runner's docked outcome names its station
through `dockedStationNameFromInfoPanel`, a live parse needing
`ensureInfoPanelLocationInfoIsExpanded` to have run, and that is why it cannot be
hoisted. saxrat's reads `context.memory.lastDockedStationNameFromInfoPanel`
instead -- memory, readable on any reading -- so nothing about the reading stops
*it* hoisting either. It stays where it is because it is success rather than a
bound, and the condition is still needed for the other half of #132's argument:
the docked outcome is below the setup list, so a starved-but-docked session
reaches only the hoisted rule and would end the session claiming the pod never
got there. `TheDockedOutcomeNamesItsStationFromMemoryTest` pins the divergence,
because the doc comment's argument goes stale the moment that changes.

Nothing here reads a live game client or drives a bot. Three cases read the
recorded saxrat runs and only read them; they skip with a stated reason on a
machine that has none, which is the answer an absent piece of *evidence* gets
rather than the one an absent toolchain does.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The mission runner's own starvation, in readings. Quoted so the relations
# below can be stated against it rather than against a number written here.
RUN_30_READINGS_HELD = 32585

# A station name with the punctuation an operator would actually have typed --
# and which this bot cannot press a key for, so it can only ever have come out
# of the info panel.
STATION = "Amarr VIII (Oris) - Emperor Family Academy"


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and the comments here name the
    branches deliberately left elsewhere.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def code_only(text):
    """The source with its doc comments and `--` lines dropped.

    Needed by any case counting *uses* of a name across a whole file: both
    files discuss `MessageBoxStandoff` and its two bounds at length in their doc
    comments, so a count over the raw text cannot tell a mention from a use and
    would answer for the prose.
    """
    return without_comments(re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL))


def declaration(name, source=None):
    return collapsed(without_comments(
        body_of(source if source is not None else source_of(SAXRAT_BOT_ELM),
                name)))


def int_constant(name):
    """A constant read out of `Bot.elm`, so a case tests the shipped number."""
    return int(re.search(r"\n%s =\s*(\d+)" % name,
                         "\n" + body_of(source_of(SAXRAT_BOT_ELM), name)).group(1))


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def verdict(readings_since, reason="the ship UI has carried no modules"):
    return "{ reason = %s, readingsSince = %d }" % (
        elm_string(reason), readings_since)


class TheDeadlineIsTheComparisonAndTheShipUITest(unittest.TestCase):
    """`podRecoveryOutOfTime`, executed, at every boundary it has.

    Extracted as a pure rule over a record -- `LockRangeState`'s shape, and for
    its reason -- so it can be run rather than restated, and so there is exactly
    one place asking it. Two would be two things that could disagree about
    whether the pod still has time.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-pod-deadline-")
        cls.bound = int_constant("podRecoveryGiveUpReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _expired(self, expression, in_space=True):
        return ("podRecoveryOutOfTime { shipLoss = %s, shipUIIsShowing = %s }"
                % (expression, "True" if in_space else "False"))

    def test_no_verdict_is_never_out_of_time(self):
        # The overwhelmingly common case: no ship has been lost, and this rule
        # has to be invisible on every reading of every ordinary run. It is at
        # the head of the decision root now, so a rule answering `Just` here
        # would end every session on its first reading.
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
        # At the mission runner's own run 30 count, on a counter that in that
        # incident was not running. A rule that expired only in a band would
        # hand the pod its budget back on the reading after the bound, which is
        # the forever-loop with one extra step in it.
        self.assertEqual(
            self.repl.evaluate([
                "%s /= Nothing"
                % self._expired("(Just %s)" % verdict(RUN_30_READINGS_HELD))]),
            [True])

    def test_nothing_but_the_reading_count_decides_it_in_space(self):
        # A verdict whose reason is empty still expires: anything conjoined onto
        # the comparison is another way for the deadline to be true and not
        # fire, which is the shape of the defect being fixed.
        self.assertEqual(
            self.repl.evaluate([
                "%s /= Nothing"
                % self._expired("(Just %s)" % verdict(self.bound, reason=""))]),
            [True])

    def test_a_docked_pod_is_never_out_of_time(self):
        """The one condition, and it is not decoration.

        A reading with no ship UI is a docked pod, which is what this bound
        exists to produce, and it is the very test `recoverPodAfterShipLoss`
        already uses to mean docked. Ending the session there would print "has
        not got there" about a pod that had -- and the outcome that says the
        true thing is below `generalSetupInUserInterface`, so a starved tree
        never reaches it.
        """
        answers = self.repl.evaluate([
            "%s == Nothing"
            % self._expired("(Just %s)" % verdict(self.bound), in_space=False),
            "%s == Nothing"
            % self._expired("(Just %s)" % verdict(RUN_30_READINGS_HELD),
                            in_space=False),
        ])
        self.assertEqual(answers, [True, True])

    def test_a_control_row_rides_along(self):
        # So a repl answering `True` to everything cannot pass the cases above.
        answers = self.repl.evaluate([
            "%s == Nothing" % self._expired("(Just %s)" % verdict(0)),
            "%s == Nothing" % self._expired("(Just %s)" % verdict(self.bound)),
        ])
        self.assertEqual(answers, [True, False])


class TheGiveUpLineSaysWhatTheOperatorHasToDoTest(unittest.TestCase):
    """`describePodRecoveryOutOfTime`, executed.

    Printed on exactly one reading before the session ends, so unlike a
    repeating line it may carry its numbers -- and it has to, because how long
    the pod was stuck and where it was trying to dock is the whole of what a
    person can act on when they go looking for a capsule.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-pod-giveup-")
        cls.bound = int_constant("podRecoveryGiveUpReadings")
        cls.with_station, cls.without_station = cls.repl.strings([
            "describePodRecoveryOutOfTime { lastDockedStationName = Just %s,"
            " verdict = %s }" % (elm_string(STATION), verdict(cls.bound)),
            "describePodRecoveryOutOfTime { lastDockedStationName = Nothing,"
            " verdict = %s }" % verdict(cls.bound),
        ])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_station_the_dock_was_preferring(self):
        # "where was it heading" is what sends a person to the right place.
        # There is no `home-station` in this bot, so the only name it can give
        # is the one `dockAtRandomStationOrStructure` is preferring.
        self.assertIn(STATION, self.with_station)

    def test_it_says_so_when_there_was_no_station_to_prefer(self):
        # With nothing docked at this session the dock takes whatever the
        # surroundings menu offers, so there is no name and the line must not
        # invent one.
        self.assertNotIn(STATION, self.without_station)
        self.assertIn("whatever this system offers", self.without_station)

    def test_it_carries_the_count(self):
        self.assertIn(str(self.bound), self.with_station)
        self.assertIn(str(self.bound), self.without_station)

    def test_it_says_the_count_is_readings_and_not_attempts(self):
        # #102's lesson on the bound where a starved tree costs the clone. A
        # session ending here having never flown the pod anywhere is saying
        # something about the rest of the bot rather than about the recovery --
        # which, with no message-box standoff here, is the likelier of the two.
        for said in (self.with_station, self.without_station):
            self.assertIn("rather than attempts", said)
            self.assertIn("Pod recovery:", said)

    def test_it_says_the_pod_still_needs_a_person(self):
        for said in (self.with_station, self.without_station):
            self.assertIn("by hand", said)


class TheDeadlineIsAskedWhereNothingCanBeAboveItTest(unittest.TestCase):
    """The placement, which is the whole fix.

    A bound tested where the tree happens to reach is not a bound. saxrat's
    decision root had no always-evaluated head to hoist into -- unlike the
    mission runner's pre-split list, it is a chain of `Maybe.withDefault`
    beginning at `generalSetupInUserInterface` -- so `endSessionOnAnExpiredBound`
    is the head that was added, and it has to stay above everything.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.root = declaration(
            "anomalyBotDecisionRootBeforeApplyingSettings", self.source)
        self.expired = declaration("endSessionOnAnExpiredBound", self.source)

    def test_the_expired_bounds_entry_leads_the_decision_root(self):
        for below in ["generalSetupInUserInterface",
                      "recoverPodAfterShipLoss",
                      "branchDependingOnDockedOrInSpace"]:
            self.assertLess(
                self.root.index("endSessionOnAnExpiredBound context"),
                self.root.index(below),
                "%s can decline to answer, so anything below it can be starved"
                % below)

    def test_the_pod_deadline_is_asked_from_there(self):
        # Not from `recoverPodAfterShipLoss`, which is below the setup list and
        # is where the comparison used to be.
        self.assertIn("podRecoveryOutOfTime", self.expired)

    def test_the_branch_only_ends_the_session(self):
        # It has no work to do and no state to reach, which is what lets it be
        # evaluated on any reading at all. A branch up here that clicked or
        # waited would need the setup list it is placed above.
        self.assertIn("Common.DecisionPath.endDecisionPath FinishSession",
                      self.expired)
        for acting in ["waitForProgressInGame", "askForHelpToGetUnstuck",
                       "useContextMenuCascade", "mouseClickOnUIElement",
                       "dockAtRandomStationOrStructure",
                       "endDecisionPath ContinueSession"]:
            self.assertNotIn(
                acting, self.expired,
                "the expired-deadline branch must do nothing but end the "
                "session -- anything else gives it a reason to be placed lower")

    def test_the_rule_itself_reaches_for_nothing_the_tree_has_to_have_done(self):
        # The whole defence of the placement. Its only inputs are the latched
        # verdict and whether the reading carries a ship UI, both of which every
        # reading answers on its own.
        rule = declaration("podRecoveryOutOfTime", self.source)
        for from_the_tree in ["context", "previousStepsEffects",
                              "infoPanelLocationInfo", "contextMenu"]:
            self.assertNotIn(
                from_the_tree, rule,
                "a deadline asked above the setup list may not depend on "
                "anything the setup list produces")

    def test_the_comparison_exists_in_exactly_one_place(self):
        # Two would be two things that could disagree, and the one inside
        # `recoverPodAfterShipLoss` is the one a starved tree never reaches.
        asked_in = [
            name for name in
            ["podRecoveryOutOfTime", "recoverPodAfterShipLoss",
             "endSessionOnAnExpiredBound", "describePodRecoveryOutOfTime",
             "statusTextFromState"]
            if "podRecoveryGiveUpReadings" in declaration(name, self.source)]
        self.assertEqual(
            asked_in, ["podRecoveryOutOfTime", "statusTextFromState"],
            "the deadline is compared in `podRecoveryOutOfTime` and printed in "
            "the status line, and nowhere else")

    def test_the_recovery_is_only_reached_while_it_has_time(self):
        body = declaration("recoverPodAfterShipLoss", self.source)
        self.assertNotIn(
            "podRecoveryGiveUpReadings", body,
            "the recovery no longer decides when the session ends for want of "
            "time")
        self.assertIn(
            "dockAtRandomStationOrStructure context", body,
            "and everything it did before the give-up is unchanged")


class TheDockedOutcomeNamesItsStationFromMemoryTest(unittest.TestCase):
    """Where saxrat and the mission runner genuinely differ, pinned.

    PR #132's argument for the ship-UI condition was that the docked outcome
    cannot be hoisted, because `dockedStationNameFromInfoPanel` needs
    `ensureInfoPanelLocationInfoIsExpanded` to have run first. **That is not
    true here.** saxrat names the station from
    `context.memory.lastDockedStationNameFromInfoPanel`, which every reading can
    answer, so its docked outcome has no state to reach either.

    It is left where it is anyway, because it is success rather than a bound and
    hoisting it would change when an *ordinary* session ends as well as a
    starved one. These cases exist so that the argument written into
    `podRecoveryOutOfTime`'s doc comment is checked rather than remembered: the
    moment the docked outcome starts parsing the info panel, that comment is
    describing something else.
    """

    def setUp(self):
        self.recovery = declaration("recoverPodAfterShipLoss")

    def test_the_station_comes_out_of_memory_and_not_the_info_panel(self):
        self.assertIn(
            "context.memory.lastDockedStationNameFromInfoPanel", self.recovery)
        self.assertNotIn("dockedStationNameFromInfoPanel context", self.recovery)

    def test_exactly_the_docked_outcome_ends_the_session_from_in_here(self):
        self.assertEqual(
            1, self.recovery.count(
                "Common.DecisionPath.endDecisionPath FinishSession"),
            "the give-up left this branch in #133; the docked outcome stays, "
            "and a second FinishSession in here is the deadline coming back")

    def test_the_mission_runners_docked_outcome_really_does_parse_the_panel(self):
        # The other half of the divergence, so "these two differ" is read out of
        # both sources rather than asserted about one. This file changes nothing
        # in the mission runner.
        self.assertIn(
            "dockedStationNameFromInfoPanel context",
            declaration("recoverPodAfterShipLoss",
                        source_of(MISSION_RUNNER_BOT_ELM)))


class WhatSaxratHasAgainstAMessageBoxStandoffTest(unittest.TestCase):
    """The ladder, which #138 ported after this bound was hoisted.

    When #133 landed, saxrat had none of it: `closeMessageBox` answered a box on
    the first reading exactly as it answered it on the thirty-thousandth, so the
    standoff that starved the mission runner's tree for 32,585 readings had
    nothing here to end it, and that is what made hoisting this deadline urgent.
    Both ends are now covered and **neither makes the other redundant** -- the
    ladder bounds one known way `generalSetupInUserInterface` can repeat
    forever, while the hoist means this deadline is asked whatever holds that
    list. These cases pin that relation, because it is what the doc comment in
    `endSessionOnAnExpiredBound` now argues.
    """

    def setUp(self):
        self.saxrat = source_of(SAXRAT_BOT_ELM)
        self.mission_runner = source_of(MISSION_RUNNER_BOT_ELM)

    def test_both_bots_now_carry_the_standoff(self):
        # Over the code rather than the prose, since both files discuss the
        # machinery at length in their doc comments.
        saxrat, mission_runner = code_only(self.saxrat), code_only(
            self.mission_runner)
        for name in ("MessageBoxStandoff", "messageBoxStandoffGiveUpReadings",
                     "messageBoxAnswersBeforeEscape"):
            for source, bot in ((mission_runner, "the mission runner"),
                                (saxrat, "saxrat")):
                self.assertGreater(
                    source.count(name), 0,
                    "%s no longer carries %s, so the argument in "
                    "`endSessionOnAnExpiredBound` is stale -- rewrite it "
                    "rather than deleting this case" % (bot, name))

    def test_saxrats_dismissal_now_counts_and_eventually_gives_up(self):
        # The consequence, read out of the branch rather than inferred from a
        # name being present: the ordinary answer is still the default rung, and
        # the give-up hands the tree back rather than raising an alarm.
        body = declaration("closeMessageBox", self.saxrat)
        self.assertIn("messageBoxStandoffVerdictForBox standoff messageBox", body)
        self.assertIn("LeaveTheMessageBoxAlone -> Nothing", body)
        self.assertIn("closeMessageBoxByDeclining messageBox", body)

    def test_the_ladder_bounds_one_starver_and_not_the_list(self):
        # What the hoist is still for. `closeMessageBox` is one of three entries
        # in `generalSetupInUserInterface`, and #297 has since given a second
        # one -- `ensureInfoPanelLocationInfoIsExpanded` -- a bound of its own.
        # `closeSystemSettingsMenu` still has none, so the list can still repeat
        # forever in a way this ladder says nothing about, and the hoist is owed
        # for exactly the entries that have not been dealt with one at a time.
        setup = declaration("generalSetupInUserInterface", self.saxrat)
        for entry in ("closeMessageBox", "closeSystemSettingsMenu",
                      "ensureInfoPanelLocationInfoIsExpanded"):
            self.assertIn(entry, setup)
        root = declaration("anomalyBotDecisionRootBeforeApplyingSettings",
                           self.saxrat)
        self.assertLess(root.index("generalSetupInUserInterface"),
                        root.index("recoverPodAfterShipLoss context"))
        self.assertLess(root.index("endSessionOnAnExpiredBound"),
                        root.index("generalSetupInUserInterface"),
                        "the deadline has to be asked above the list, since "
                        "the list is only partly bounded")


class TheCounterStillCountsReadingsAndNotAttemptsTest(unittest.TestCase):
    """The half of the issue that is a choice rather than a defect.

    The other shape available was to advance `readingsSince` only on readings
    the recovery was reached on, so that 150 means 150 *attempts*. It reads
    better and it is wrong for a deadline that ends the session: a bot held
    elsewhere would spend none of the budget, which is precisely the runaway --
    and here the runaway is a capsule sitting in the pocket that killed the ship.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_the_clock_advances_on_every_reading_the_verdict_is_latched(self):
        latched = declaration("shipLossVerdictAfter", self.source)
        self.assertIn(
            "Just latched -> Just { latched | readingsSince = "
            "latched.readingsSince + 1 }", latched,
            "the latched arm carries no condition at all -- conditioning it on "
            "what the bot managed to do turns the bound into a count of "
            "attempts, which is no bound at all")

    def test_nothing_about_the_decision_reaches_the_clock(self):
        update = declaration("updateMemoryForNewReadingFromGame", self.source)
        clause = update[update.index(", shipLoss ="):]
        clause = clause[:clause.index(", shipUIWithoutModuleButtonsReadings =")]
        for from_the_tree in ["previousStepsEffects", "previousStepDispatched"]:
            self.assertNotIn(
                from_the_tree, clause,
                "the pod recovery clock must not consult what the bot was able "
                "to do with a reading")

    def test_the_drone_recall_counts_the_other_way_on_purpose(self):
        """The counter-example, so the two cannot be conflated.

        `droneRecallUnansweredTicks` deliberately advances only where the bot
        actually asked -- it reads the ask out of `previousStepsEffects` -- and
        is right to, because its give-up *declines an action* rather than ending
        the session. A fight that legitimately kept the bot elsewhere must not
        spend a budget whose purpose is to bound a repeated ask.
        """
        update = declaration("updateMemoryForNewReadingFromGame", self.source)
        clause = update[update.index(", droneRecallUnansweredTicks ="):]
        self.assertIn(
            "recentStepAskedForDroneRecall context.previousStepsEffects",
            clause[:clause.index(", dronesInSpaceCountLastReading =")])

    def test_the_status_line_still_carries_the_count_against_the_bound(self):
        status = declaration("statusTextFromState", self.source)
        self.assertIn("String.fromInt shipLoss.readingsSince", status)
        self.assertIn("String.fromInt podRecoveryGiveUpReadings", status)


class WhatTheRecordedSaxratRunsCanAndCannotSayTest(unittest.TestCase):
    """The three recorded saxrat runs, asked what they bear on -- which is
    mostly that they are silent, and that the silence is checked.

    Asserted as *relations* rather than counts, so a corpus that grows cannot
    turn a true claim red.
    """

    @classmethod
    def setUpClass(cls):
        logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
                for number in (1, 2, 3)]
        logs = [path for path in logs if os.path.exists(path)]
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "can say about this bound cannot be consulted here")

        cls.status_lines = cls.ship_lost = cls.boxes = 0
        for path in logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "Approaching ticks:" in line:
                        cls.status_lines += 1
                    if "SHIP LOST:" in line:
                        cls.ship_lost += 1
                    if "Dismiss it using" in line:
                        cls.boxes += 1

    def test_the_memory_update_printed_throughout(self):
        # The positive control the two silences below need: the status line is
        # written from the memory update on every reading, so a corpus with
        # plenty of them is a corpus that would have shown a latched verdict.
        self.assertGreater(
            self.status_lines, int_constant("podRecoveryGiveUpReadings") * 50,
            "the recorded saxrat runs are too short to say anything about a "
            "bound of this size")

    def test_no_recorded_saxrat_run_has_ever_latched_a_ship_loss(self):
        # So this counter has never been observed running here either, and the
        # defect being fixed has never been *seen* in saxrat -- only reasoned
        # from the source. That is the same standing #132 recorded.
        self.assertEqual(
            self.ship_lost, 0,
            "a recorded saxrat run latched a ship-loss verdict after all, so "
            "the corpus can be asked what the counter did and this file should "
            "be asking it")

    def test_no_recorded_saxrat_run_has_ever_met_a_message_box_either(self):
        # The starvation this fix is aimed at is reasoned from saxrat's source
        # and from the mission runner's run 30, not from anything saxrat has
        # been watched doing. Stated as a checked claim so it cannot quietly
        # become false.
        self.assertEqual(
            self.boxes, 0,
            "a recorded saxrat run dismissed a message box, so the corpus can "
            "now say something about how long one holds this tree")


if __name__ == "__main__":
    unittest.main()
