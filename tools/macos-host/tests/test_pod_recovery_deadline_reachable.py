"""Tests for the pod recovery's deadline being asked where it is always reached.

Issue #126, and it is issue #102 a second time in the same file. The comparison
was right and unreachable:

    if podRecoveryGiveUpReadings <= shipLoss.readingsSince then

`shipLoss.readingsSince` is advanced in `updateMemoryForNewReadingFromGame`,
which runs on **every** reading unconditionally and does not consult anything
about what the bot managed to do with the reading. The comparison sat inside
`recoverPodAfterShipLoss` -- in the pre-split list, but *below*
`generalSetupInUserInterface` -- so anything answering up there starved the bound
while the number it is compared against went on climbing.

**Run 30 starved it, and it cost nothing by luck.** An undismissable window held
`generalSetupInUserInterface` for 32,585 readings, three hours and forty-four
minutes, and nothing below that entry ran on any of them. The ship-loss status
clause printed on 39,843 log lines and every one of them read `ship ok`, so no
verdict was ever latched, the counter was not running, and the bound had nothing
to be late for. A ship lost during the same standoff would have reproduced run
30 with a capsule sitting in the pocket that killed the ship -- which is the
version of that incident where the stakes are the clone rather than a mission's
standing.

**Which kind of give-up this is, is what decides the fix**, and PR #115 wrote the
rule: a give-up that ends the session bounds elapsed time and belongs where
nothing can decline to ask it; a give-up that declines an action bounds effort
and belongs where the action is. This one is a `describeBranch` around
`FinishSession` and nothing else -- no click, no travel, no dock, no menu -- so
it is the first kind and it hoists. What does *not* hoist is the recovery itself:
flying a pod to a station is an errand needing the location info panel expanded,
which is exactly why `recoverPodAfterShipLoss` sits below the setup list and
still does.

**The ship UI is a condition on the hoisted rule**, and the cases below pin it.
The recovery's other session-ending outcome is the pod being *docked*, which is
success rather than a bound and which names its station out of the location info
panel -- so that one genuinely cannot be hoisted, and a deadline asked without
the ship UI would end a docked session claiming the pod never got there.

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

# The run that starved this bound without anyone noticing.
THE_INCIDENT = "30"

# The line the message box printed on every reading it held the tree, and the
# ship-loss status clause the memory update printed on every reading whatever
# the tree was doing. The gap between them is the whole issue.
BOX_LINE = "Dismiss it using No."
SHIP_OK_CLAUSE = "ship ok (no-mod"
SHIP_LOST_CLAUSE = "SHIP LOST:"

# A station name with the punctuation an operator would actually have typed.
HOME_STATION = "Amarr VIII (Oris) - Emperor Family Academy"


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

    Every case that asserts a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and the comments here name the
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


def verdict(readings_since, reason="the ship UI has carried no modules"):
    return "{ reason = %s, readingsSince = %d }" % (
        elm_string(reason), readings_since)


class TheDeadlineIsTheComparisonAndTheShipUI(unittest.TestCase):
    """`podRecoveryOutOfTime`, executed, at every boundary it has.

    Extracted as a pure rule over a record so that it can be run rather than
    restated -- and so that there is exactly one place asking it. Two would be
    two things that could disagree about whether the pod still has time.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-pod-deadline-")
        cls.bound = int_constant("podRecoveryGiveUpReadings")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _expired(self, expression, in_space=True):
        return ("podRecoveryOutOfTime { shipLoss = %s, shipUIIsShowing = %s }"
                % (expression, "True" if in_space else "False"))

    def test_no_verdict_is_never_out_of_time(self):
        # The overwhelmingly common case: no ship has been lost, and this branch
        # has to be invisible on every reading of every ordinary run.
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
        # Run 30's own count, on the counter that was not running. A rule that
        # expired only in a band would hand the pod its budget back on the
        # reading after the bound, which is the forever-loop with one extra step
        # in it.
        self.assertEqual(
            self.repl.evaluate([
                "%s /= Nothing" % self._expired("(Just %s)" % verdict(10811))]),
            [True])

    def test_nothing_but_the_reading_count_decides_it_in_space(self):
        # A verdict whose reason is empty still expires: anything conjoined onto
        # the comparison is another way for the deadline to be true and not fire.
        self.assertEqual(
            self.repl.evaluate([
                "%s /= Nothing"
                % self._expired("(Just %s)" % verdict(self.bound, reason=""))]),
            [True])

    def test_a_docked_pod_is_never_out_of_time(self):
        """The one condition, and it is not decoration.

        A reading with no ship UI is a docked pod, which is what the bound exists
        to produce. Ending the session there would print "has not got there"
        about a pod that had, and the docked outcome inside
        `recoverPodAfterShipLoss` says the true thing instead -- naming the
        station, which it can only do once the location info panel is expanded.
        """
        answers = self.repl.evaluate([
            "%s == Nothing"
            % self._expired("(Just %s)" % verdict(self.bound), in_space=False),
            "%s == Nothing"
            % self._expired("(Just %s)" % verdict(10811), in_space=False),
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
    """`describePodRecoveryOutOfTime`, executed.

    Printed on exactly one reading before the session ends, so unlike the
    repeating line it may carry its numbers -- and it has to, because how long
    the pod was stuck and where it was heading is the whole of what a person can
    act on when they go looking for a capsule.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-pod-giveup-")
        cls.bound = int_constant("podRecoveryGiveUpReadings")
        cls.with_home, cls.without_home = cls.repl.strings([
            "describePodRecoveryOutOfTime { homeStationName = Just %s, verdict = %s }"
            % (elm_string(HOME_STATION), verdict(cls.bound)),
            "describePodRecoveryOutOfTime { homeStationName = Nothing, verdict = %s }"
            % verdict(cls.bound),
        ])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_station_the_pod_was_routed_to(self):
        # "where was it heading" is what sends a person to the right place, and
        # the name carries punctuation the bot cannot even type, so it has to
        # come out of the setting rather than be reconstructed.
        self.assertIn(HOME_STATION, self.with_home)

    def test_it_says_so_when_there_was_no_named_destination(self):
        # Without `home-station` the recovery docks at whatever the surroundings
        # menu offers, so there is no station to name and the line must not
        # invent one.
        self.assertNotIn(HOME_STATION, self.without_home)
        self.assertIn("home-station", self.without_home)

    def test_it_carries_the_count(self):
        self.assertIn(str(self.bound), self.with_home)
        self.assertIn(str(self.bound), self.without_home)

    def test_it_says_the_count_is_readings_and_not_attempts(self):
        # #102's lesson, on the bound where a starved tree costs the clone. A
        # session that ends here having never flown the pod anywhere is saying
        # something about the rest of the bot rather than about the recovery.
        for said in (self.with_home, self.without_home):
            self.assertIn("rather than attempts", said)

    def test_it_says_the_pod_still_needs_a_person(self):
        for said in (self.with_home, self.without_home):
            self.assertIn("by hand", said)


class TheDeadlineIsAskedWhereNothingCanBeAboveIt(unittest.TestCase):
    """The placement, which is the whole fix.

    A bound tested where the tree happens to reach is not a bound.
    `endSessionOnAnExpiredBound` is the first entry in the list at the top of
    `missionBotDecisionRootBeforeApplyingSettings`, which is the last thing
    evaluated on every reading whatever else is going on, and this deadline has
    to be asked from there.
    """

    def setUp(self):
        self.source = bot_source()
        start = self.source.index(
            "missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nendSessionOnAnExpiredBound :", start)
        self.root = collapsed(without_comments(self.source[start:end]))
        self.expired = collapsed(without_comments(
            declaration(self.source, "endSessionOnAnExpiredBound")))

    def test_the_expired_bounds_entry_still_leads_the_pre_split_list(self):
        pre_split = self.root[:self.root.index("branchDependingOnDockedOrInSpace")]
        self.assertIn("endSessionOnAnExpiredBound context", pre_split)
        for below in ["generalSetupInUserInterface", "recoverPodAfterShipLoss",
                      "windDownBeforeSessionEnd"]:
            self.assertLess(
                pre_split.index("endSessionOnAnExpiredBound context"),
                pre_split.index(below),
                "%s can decline to answer, so anything below it can be starved "
                "-- which is what run 30 did for three hours and forty-four "
                "minutes" % below)

    def test_the_pod_deadline_is_asked_from_there(self):
        # Not from `recoverPodAfterShipLoss`, which is below the setup list and
        # is where the comparison used to be.
        self.assertIn("podRecoveryOutOfTime", self.expired)

    def test_it_is_above_the_user_interface_setup_in_particular(self):
        # `generalSetupInUserInterface` is the entry that held run 30, and it is
        # the one directly above `recoverPodAfterShipLoss` in the same list.
        # Ending a session needs no panel expanded and no menu cleared, so there
        # is no reason for the setup to outrank a deadline that has expired.
        self.assertLess(
            self.root.index("endSessionOnAnExpiredBound context"),
            self.root.index("generalSetupInUserInterface"))

    def test_the_pod_is_asked_before_the_abandonment(self):
        # Both end the session and both can be expired on the same reading. A
        # capsule is what the operator has to go and deal with; a mission still
        # accepted can wait for them, and the ordering says so everywhere else
        # in this file.
        self.assertLess(
            self.expired.index("podRecoveryOutOfTime"),
            self.expired.index("abandonmentOutOfTime"),
            "a lost ship outranks a stuck mission")

    def test_the_branch_only_ends_the_session(self):
        # It has no work to do and no state to reach, which is what lets it be
        # evaluated on any reading at all. A branch up here that clicked or
        # waited would need the setup list it is placed above.
        self.assertIn("Common.DecisionPath.endDecisionPath FinishSession",
                      self.expired)
        for acting in ["waitForProgressInGame", "askForHelpToGetUnstuck",
                       "useContextMenuCascade", "mouseClickOnUIElement",
                       "travelToStationByName", "dockAtStation",
                       "endDecisionPath ContinueSession"]:
            self.assertNotIn(
                acting, self.expired,
                "the expired-deadline branch must do nothing but end the "
                "session -- anything else gives it a reason to be placed lower")

    def test_the_rule_itself_reaches_for_nothing_the_tree_has_to_have_done(self):
        # The whole defence of the placement. Its only inputs are the latched
        # verdict and whether the reading carries a ship UI, both of which every
        # reading answers on its own.
        rule = collapsed(without_comments(
            declaration(self.source, "podRecoveryOutOfTime")))
        for from_the_tree in ["context", "dockedStationNameFromInfoPanel",
                              "previousStepsEffects", "infoPanelLocationInfo"]:
            self.assertNotIn(
                from_the_tree, rule,
                "a deadline asked above the setup list may not depend on "
                "anything the setup list produces")

    def test_the_comparison_exists_in_exactly_one_place(self):
        # Two would be two things that could disagree, and the one inside
        # `recoverPodAfterShipLoss` is the one a starved tree never reaches.
        asked_in = [name for name in
                    ["podRecoveryOutOfTime", "recoverPodAfterShipLoss",
                     "describeShipLoss", "endSessionOnAnExpiredBound",
                     "describePodRecoveryOutOfTime"]
                    if "podRecoveryGiveUpReadings"
                    in collapsed(without_comments(
                        declaration(self.source, name)))]
        self.assertEqual(
            asked_in, ["podRecoveryOutOfTime", "describeShipLoss"],
            "the deadline is compared in `podRecoveryOutOfTime` and printed in "
            "the status line, and nowhere else")

    def test_the_recovery_is_only_reached_while_it_has_time(self):
        body = collapsed(without_comments(
            declaration(self.source, "recoverPodAfterShipLoss")))
        self.assertNotIn(
            "podRecoveryGiveUpReadings", body,
            "the recovery no longer decides when the session ends for want of "
            "time")
        self.assertIn(
            "travelToStationByName context stationName", body,
            "and everything it did before the give-up is unchanged")
        self.assertIn(
            "dockAtStation context.memory.lastDockedStationNameFromInfoPanel",
            body)

    def test_the_docked_outcome_stays_in_the_recovery(self):
        """The one session-ending outcome that genuinely cannot be hoisted.

        It names the station out of `dockedStationNameFromInfoPanel`, and that
        read needs `ensureInfoPanelLocationInfoIsExpanded` to have run -- which
        is a state to reach, which is the property the hoisted entry has to lack.
        """
        body = collapsed(without_comments(
            declaration(self.source, "recoverPodAfterShipLoss")))
        self.assertIn("dockedStationNameFromInfoPanel context", body)
        self.assertEqual(
            1, body.count("Common.DecisionPath.endDecisionPath FinishSession"),
            "exactly the docked outcome ends the session from in here")


class TheCounterStillCountsReadingsAndNotAttempts(unittest.TestCase):
    """The half of the issue that is a choice rather than a defect.

    The other shape available was to advance `readingsSince` only on readings
    the recovery was reached on, so that 150 means 150 *attempts*. It reads
    better and it is wrong for a deadline that ends the session: a bot held
    elsewhere would spend none of the budget, which is precisely the runaway --
    and here the runaway is a capsule sitting in the pocket that killed the ship.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_clock_advances_on_every_reading_the_verdict_is_latched(self):
        latched = collapsed(without_comments(
            declaration(self.source, "shipLossVerdictAfter")))
        self.assertIn(
            "Just latched -> Just { latched | readingsSince = "
            "latched.readingsSince + 1 }", latched,
            "the latched arm carries no condition at all -- conditioning it on "
            "what the bot managed to do turns the bound into a count of "
            "attempts, which run 30 shows is no bound")

    def test_nothing_about_the_decision_reaches_the_clock(self):
        update = collapsed(without_comments(declaration(
            self.source, "updateMemoryForNewReadingFromGame")))
        clause = update[update.index(", shipLoss ="):]
        clause = clause[:clause.index(", ammoSwap =")]
        for from_the_tree in ["previousStepDispatchedEffects",
                              "previousStepsEffectsPressedMouse",
                              "previousStepsEffects"]:
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
        update = collapsed(without_comments(declaration(
            self.source, "updateMemoryForNewReadingFromGame")))
        clause = update[update.index(", droneRecallUnansweredTicks ="):]
        clause = clause[:clause.index(", dronesInSpaceLastSeen")]
        self.assertIn("recentStepAskedForDroneRecall context.previousStepsEffects",
                      clause)

    def test_the_status_line_still_carries_the_count_against_the_bound(self):
        status = collapsed(declaration(self.source, "describeShipLoss"))
        self.assertIn("String.fromInt shipLoss.readingsSince", status)
        self.assertIn("String.fromInt podRecoveryGiveUpReadings", status)


class TheOtherBoundsStillFailSafe(unittest.TestCase):
    """The four PR #115 named as sharing the asymmetry, re-read after #109.

    None is changed here -- moving a bound is a behaviour change wanting its own
    evidence -- and this class exists so the claim that they fail safe is
    checked rather than remembered. Each is a counter advanced from the reading
    and a comparison somewhere the tree may not reach, and for each the
    direction of over-counting is benign.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_message_box_give_up_hands_the_tree_back(self):
        # Counted on every reading a box is showing, tested in `closeMessageBox`
        # below `closeSystemSettingsMenu` in the same list. Over-counting makes
        # it give up *sooner*, and giving up here is answering `Nothing` so that
        # everything below runs -- the safe direction, and the one #109 built.
        body = collapsed(without_comments(
            declaration(self.source, "closeMessageBox")))
        self.assertIn("LeaveTheMessageBoxAlone -> Nothing", body)

    def test_the_docking_run_ins_patience_is_spent_in_the_memory_update(self):
        # Stronger than #115 recorded: the comparison is inside
        # `dockingRunInAfterReading`, which the memory update calls, so the
        # counter and the test are the same code on the same reading and the
        # tree cannot starve it at all. What sits under the split only reads the
        # latch, and losing it early costs one re-commanded dock.
        rule = collapsed(without_comments(
            declaration(self.source, "dockingRunInAfterReading")))
        self.assertIn(
            "runIn.readingsSinceCloser + 1 < dockingRunInPatienceReadings", rule)
        update = collapsed(without_comments(declaration(
            self.source, "updateMemoryForNewReadingFromGame")))
        self.assertIn("dockingRunInAfterReading", update)

    def test_the_loot_write_off_is_applied_in_the_memory_update(self):
        # Both loot counters advance from the reading, and the *effect* of their
        # bounds -- adding the container to `unlootableWreckIds` -- is applied in
        # the memory update on the reading the bound is reached, not in the
        # branch under the split. `giveUpOnOpenContainerReason` down there only
        # supplies the log line, so over-counting costs one abandoned wreck.
        update = collapsed(without_comments(declaration(
            self.source, "updateMemoryForNewReadingFromGame")))
        clause = update[update.index(", unlootableWreckIds ="):]
        clause = clause[:clause.index(", gateWithinReachTicks =")]
        self.assertIn("lootAllRefusedTicks >= lootAllRefusedTicksBeforeGivingUp",
                      clause)
        self.assertIn(
            "lootWindowOutOfRangeTicks >= outOfRangeTicksBeforeGivingUp", clause)


class RunThirtyStarvedThisOneToo(unittest.TestCase):
    """The recorded incident, recounted as the relations the fix rests on.

    Relations rather than numbers, which is `test_travel_outranks_the_fight.py`'s
    lesson: a corpus that grows must not turn a true claim red.
    """

    def _counts(self):
        (_, path), = recorded_runs(THE_INCIDENT)
        box = ship_status = lost = 0
        with open(path, encoding="utf-8", errors="ignore") as log:
            for line in log:
                if BOX_LINE in line:
                    box += 1
                if SHIP_OK_CLAUSE in line:
                    ship_status += 1
                if SHIP_LOST_CLAUSE in line:
                    lost += 1
        return box, ship_status, lost

    def test_the_memory_update_ran_on_every_reading_of_it(self):
        # The half that was working. `describeShipLoss` prints from the memory
        # update's own verdict field, and it printed throughout -- which is what
        # says the counter would have been climbing had there been anything to
        # count.
        box, ship_status, _ = self._counts()
        self.assertGreater(box, 10000, "run 30 is supposed to be the standoff")
        self.assertGreater(
            ship_status, box,
            "the ship-loss status clause is printed from the memory update, "
            "which runs on every reading whatever the tree is doing")

    def test_the_entry_holding_this_bound_was_never_reached(self):
        # `generalSetupInUserInterface` answered `Just` on every one of those
        # readings, and `recoverPodAfterShipLoss` is the entry directly below it
        # in a list resolved by `List.head`. So the branch that used to hold this
        # comparison was not consulted once in three hours and forty-four
        # minutes.
        root = collapsed(without_comments(bot_source()[
            bot_source().index(
                "missionBotDecisionRootBeforeApplyingSettings context ="):]))
        pre_split = root[:root.index("branchDependingOnDockedOrInSpace")]
        self.assertLess(pre_split.index("generalSetupInUserInterface"),
                        pre_split.index("recoverPodAfterShipLoss context"))
        self.assertIn("|> List.filterMap identity |> List.head", pre_split)
        box, _, _ = self._counts()
        self.assertGreater(box, int_constant("podRecoveryGiveUpReadings") * 50)

    def test_it_cost_nothing_only_because_no_verdict_was_latched(self):
        """The luck, stated as the thing that must not be relied on again.

        Every ship-loss status line in the run reads `ship ok`, so the verdict
        never latched and `readingsSince` never left zero. Had it latched at any
        point in that standoff, the counter would have run exactly as the
        abandonment's did -- and the bot would have been in a capsule.
        """
        _, ship_status, lost = self._counts()
        self.assertGreater(ship_status, 0)
        self.assertEqual(
            lost, 0,
            "run 30 never lost its ship, which is the whole reason this bound "
            "has never been seen failing")


if __name__ == "__main__":
    unittest.main()
