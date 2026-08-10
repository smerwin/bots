"""Tests for the mission runner asking the client for several locks in one step.

PR #178 batched saxrat's lock clicks and recorded, in
`TheMissionRunnerStillLocksOnePerStepTest`, that this bot has the identical
one-Ctrl+click-then-hand-the-step-back shape. This is that port, and the case
which held the marker is replaced by the ones below.

**Four things are this bot's own rather than saxrat's, and each has its own
case.**

**The candidate list is not distance-ordered here.**
`everythingWorthAttacking` sorts a warp-disrupting entry to the **front**, ahead
of the distance order, so the rows in range are not a prefix of it and a batch
built by *filtering* would skip a scrambler the ship cannot reach, lock the rats
behind it, and never approach the one row it most wants.
`lockBatchRowsInReach` counts the in-range prefix instead, so a head out of
reach answers 0 and the reading falls back to the single path, whose
out-of-range branch approaches it exactly as before —
`TheBatchNeverReachesPastARowItCannotLock`.

**The cap is sized on this bot's corpus.** It lands on 3, as saxrat's did, for a
different reason: see `lockBatchMaximumClicks`' doc comment, and
`TheClickCapIsSizedOnThisBotsOwnSteps`.

**The gain is smaller and is stated as such.** saxrat locked a median of 2
readings apart; here the median gap between lock commands is 5 readings and
**76% of lock bursts are a single lock**, so batching applies to under half of
this bot's locks — `TheRecordedRunsShowASmallerRampThanSaxrats`.

**The range rule cannot be executed here.** The mission runner's
`updateLockRangeLearning` takes a whole `UpdateMemoryContext` where saxrat's
takes records, which is the divergence #106 records the cost of — so the
batched-reading guard is **read** rather than run, in the shape
`test_max_targets_probe` already uses for this same function in both apps.
Everything that is a function of records is executed.

Carried across from PR #178 and not re-derived: the framework dispatches an
unbounded effect list in one `WindowsInputRequest`; the host's double-click
recogniser cannot mangle a batch, since every chord puts a `KeyUp`, a `KeyDown`
and a `MouseMoveTo` between one press/release pair and the next; a batched
reading must teach the lock-range rule nothing and discharge any pending
attempt; and that costs nothing because `lockAttemptCanTeachRange` already
discharges an attempt begun with the bar occupied, so batching applies precisely
to the locks that could never have taught anything.

The wiring is read out of the source through a reader sliced by **indentation**,
since the bindings under test build record literals and the `let_binding` shape
stops at the opening brace.

Confirmed by mutation, fifteen of them, each failing a named case: the in-range
prefix replaced by a filter, which is the scrambler-skipping failure this port
exists to refuse; the prefix rule made to count past a row out of reach; the
effects reader taking only the first click again; **the batched-reading guard
dropped from the range rule**; the pending attempt carried across a batch rather
than discharged; the first lock of an engagement batched; the probe batched; the
click cap raised past this bot's 99th-percentile step and lowered so nothing
batches; the free-slot bound dropped; the settling window removed; the batch
judged against the reading that observes it rather than the one it was decided
from; the shortfall never reported; the session totals not accumulating; the
accounting reaching into the range rule; and the batch's line no longer opening
with the string operators grep for.

Nothing here reads a live game client or a running bot. One case reads the
recorded mission runs, and only reads them; it skips with a stated reason on a
machine that has none.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, ElmRepl, open_repl
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, collapsed, source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import Common.EffectOnWindow as EffectOnWindow",
)

# Measured over all 39 recorded mission runs and their 40,903 `send-effects`
# steps: the median step is 1.02 s and the 99th percentile 4.53 s, while a lock
# step's own median is 1.30 s -- half saxrat's 2.56 s. Three clicks is about
# 3.9 s, inside what an ordinary step already reaches. This bot's longest step
# ever is 12.9 s (a typed station name), so unlike saxrat the cap is not about
# what the host can carry.
LOCK_STEP_MEDIAN_SECONDS = 1.30
ORDINARY_STEP_P99_SECONDS = 4.53
LONGEST_RECORDED_STEP_SECONDS = 12.90


def indented_block(source, name, indent):
    """A binding's right-hand side, sliced by indentation.

    `let_binding`'s shape -- read to the next ` <name> = ` -- stops at a record
    literal, and the bindings this file asks about build one. PRs #147, #156,
    #159 and #162 each paid for that once with an assertion that passed having
    read nothing.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    for match in re.finditer(r"\n([ ]*)(\S)", rest):
        if len(match.group(1)) <= len(indent):
            return rest[:match.start()]
    return rest


def top_level_block(source, name):
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def combat_decision_source():
    return top_level_block(
        source_of(MISSION_RUNNER_BOT_ELM), "decideActionInCombat")


class BatchRepl(ElmRepl):
    """The mission runner's own `Bot.elm`, plus what a batch needs expressed."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "mission-batch-repl-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        "situation = \\held take reachable probe ->"
        " { targetsHeld = held, rowsToTake = take"
        " , rowsLockableNow = reachable, probeIsDue = probe }",
        "batchState = \\dispatch asked answered ->"
        " { dispatch = dispatch, clicksAsked = asked"
        " , clicksAnswered = answered }",
        "batchReading = \\asked now before ->"
        " { clicksAsked = asked, targetsCount = now"
        " , targetsCountBefore = before }",
        "openBatch = \\asked before waited ->"
        " Just { clicksAsked = asked, targetsCountBefore = before"
        " , readingsWaited = waited }",
        "batchStep = \\reading state ->"
        " let acc = updateLockBatchAccounting reading state in"
        " { dispatch = acc.dispatch, clicksAsked = acc.clicksAsked"
        " , clicksAnswered = acc.clicksAnswered }",
        "noBatch = { dispatch = Nothing, clicksAsked = 0"
        " , clicksAnswered = 0 }",
        # Several lock chords in one step, at the given points.
        "lockClicksAt = \\points -> points |> List.concatMap (\\point ->"
        " [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
        " , EffectOnWindow.MouseMoveTo point"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ])",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class SharedRepl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def ask(self, expressions):
        return self.repl.evaluate(
            expressions, definitions=self.repl.with_helpers([]))


class TheBatchNeverReachesPastARowItCannotLock(SharedRepl):
    """The one rule this bot needed that saxrat did not.

    saxrat's candidate list is sorted by distance alone, so the rows in range
    are a prefix of it and filtering could not reorder anything. Here
    `everythingWorthAttacking` puts a warp-disrupting entry at the front ahead
    of the distance order, so a scrambler out of reach can sit in front of rats
    that are in reach -- and a batch built by filtering would skip the row the
    bot most wants and never approach it.
    """

    def test_a_head_the_ship_cannot_reach_answers_zero(self):
        """Which drops the batch to one row and hands the reading to the single
        path, whose out-of-range branch approaches it exactly as before."""
        answers = self.ask([
            "lockBatchRowsInReach [ False, True, True, True ] == 0",
            "lockBatchRowsInReach [ False ] == 0",
            "lockBatchRowsInReach [] == 0",
            # And a batch of zero is never an answer.
            "lockBatchSize (situation 1 6 0 False) == 1",
        ])
        self.assertEqual(
            answers, [True] * 4,
            "a row the ship cannot reach no longer stops the batch, so a "
            "scrambler out of range would be skipped and the rats behind it "
            "locked instead -- which is the one thing this port had to get "
            "right that saxrat's did not")

    def test_it_stops_at_the_first_row_out_of_reach(self):
        """A prefix, not a count: the rows after a gap are not reachable
        candidates for *this* step however close they are."""
        answers = self.ask([
            "lockBatchRowsInReach [ True, True, False, True, True ] == 2",
            "lockBatchRowsInReach [ True, False, True ] == 1",
            "lockBatchRowsInReach [ True, True, True ] == 3",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the reachability rule counts past a row the ship cannot lock, so "
            "a batch would reorder the candidate list")

    def test_the_call_site_takes_the_prefix_rather_than_filtering(self):
        binding = collapsed(indented_block(
            combat_decision_source(), "overviewEntriesToLockInOneStep",
            indent="        "))
        self.assertIn("lockBatchRowsInReach", binding,
                      "the batch no longer counts the in-range prefix, so the "
                      "priority ordering can be skipped past")
        self.assertIn("overviewEntriesToLock |> List.take", binding,
                      "the batch is taken from something other than the front "
                      "of the candidate list")
        self.assertNotIn("overviewEntriesToLockInRange", binding,
                         "the batch is built by filtering the candidate list, "
                         "which drops a row the ship cannot reach and promotes "
                         "the ones behind it")


class TheFirstLockAndTheProbeAreAskedAloneTest(SharedRepl):
    """What keeps the lock-range rule whole, carried across unchanged.

    `lockAttemptCanTeachRange` is `targetsCount == 0`, so an attempt begun with
    the bar occupied is discharged rather than judged and could never move
    either bound. Asking the bar-empty lock alone is what makes batching cost
    the range rule nothing at all.

    It matters more here than in saxrat: an anomaly is a pocket of identically
    named rats, so `overviewEntryLockHandle` usually declines to attribute
    anything there, while a mission pocket is mixed and the handle resolves.
    """

    def test_the_first_lock_of_an_engagement_is_asked_alone(self):
        answers = self.ask([
            "lockBatchSize (situation 0 6 6 False) == 1",
            "lockBatchSize (situation 0 6 1 False) == 1",
            "lockBatchSize (situation 1 6 6 False) == 3",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the first lock of an engagement is now batched, so the only lock "
            "that could ever have taught the refusal bound is issued in a step "
            "the range rule refuses to learn from")

    def test_the_probe_is_asked_alone(self):
        answers = self.ask([
            "lockBatchSize (situation 1 7 6 True) == 1",
            "lockBatchSize (situation 5 7 6 True) == 1",
            "lockBatchSize (situation 2 7 6 False) == 3",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "#150's probe is issued inside a batch, so what the client answers "
            "cannot be attributed to the probe")

    def test_it_never_exceeds_the_ships_free_slots(self):
        answers = self.ask([
            "lockBatchSize (situation 4 6 6 False) == 2",
            "lockBatchSize (situation 5 6 6 False) == 1",
            "lockBatchSize (situation 6 6 6 False) == 1",
            "lockBatchSize (situation 7 6 6 False) == 1",
        ])
        self.assertEqual(
            answers, [True] * 4,
            "a batch asked for more locks than the ship has free slots")


class TheClickCapIsSizedOnThisBotsOwnSteps(SharedRepl):
    """A batch is a step with no reading in it, so its length is time the
    retreat cannot act on.

    The boundary pair is asked beside fixed values, because a case that only
    asks about `cap` and `cap - 1` passes for any cap at all, including one that
    batches nothing.
    """

    def test_the_cap_bounds_the_batch_and_sits_where_the_corpus_puts_it(self):
        answers = self.ask([
            "lockBatchSize (situation 1 20 20 False) == lockBatchMaximumClicks",
            "1 < lockBatchMaximumClicks",
            "lockBatchMaximumClicks <= 4",
            "lockBatchSize (situation 1 20 20 False) == 3",
            "lockBatchSize (situation 1 20 2 False) == 2",
        ])
        self.assertEqual(
            answers, [True] * 5,
            "the per-step click cap is gone, batches nothing, or runs far past "
            "the %.2f s an ordinary step of this bot already reaches at the "
            "99th percentile (a lock step's median is %.2f s)"
            % (ORDINARY_STEP_P99_SECONDS, LOCK_STEP_MEDIAN_SECONDS))

    def test_the_cap_takes_fewer_steps_than_one_lock_a_reading(self):
        """The relation the change exists for: filling a six-slot bar from the
        first lock takes fewer steps than six."""
        answers = self.ask([
            "(1 + ((6 - 1) + lockBatchMaximumClicks - 1)"
            " // lockBatchMaximumClicks) < 6",
        ])
        self.assertTrue(
            answers[0],
            "batching no longer takes fewer steps than one lock a reading, "
            "which is the whole of the change")

    def test_the_cap_is_the_same_number_saxrat_settled_on(self):
        """Both bots land on three, from different measurements. Compared so a
        retune of one that leaves the other behind is noticed."""
        saxrat = collapsed(top_level_block(
            source_of(SAXRAT_BOT_ELM), "lockBatchMaximumClicks"))
        mission = collapsed(top_level_block(
            source_of(MISSION_RUNNER_BOT_ELM), "lockBatchMaximumClicks"))
        self.assertIn("lockBatchMaximumClicks = 3", saxrat)
        self.assertIn("lockBatchMaximumClicks = 3", mission)


class TheStepCarriesEveryLockClickTest(SharedRepl):
    """What the bot dispatches and what the accounting counts are one thing."""

    def test_every_click_of_a_batch_is_read_back_in_order(self):
        """A reader answering `Maybe` could not tell one lock from three, so it
        would have gone on attributing the next reading's outcome to whichever
        click it happened to take."""
        answers = self.ask([
            "(lockClicksAt [ { x = 10, y = 20 }, { x = 10, y = 40 }"
            " , { x = 10, y = 60 } ] |> lockClickLocationsFromStepEffects) =="
            " [ { x = 10, y = 20 }, { x = 10, y = 40 }, { x = 10, y = 60 } ]",
            "(lockClicksAt [ { x = 1, y = 2 } ]"
            " |> lockClickLocationsFromStepEffects |> List.length) == 1",
            "(lockClicksAt [] |> lockClickLocationsFromStepEffects) == []",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the effects reader no longer returns every lock click of a step, "
            "so a batched step is indistinguishable from a single lock and its "
            "outcome would be attributed to one row of it")

    def test_the_batch_is_the_single_chord_repeated(self):
        """Asserted as an equality against the single chord repeated, rather
        than by counting effects: a version holding Ctrl across the whole run
        would produce the right number of points and a different gesture."""
        answers = self.repl.evaluate(
            ["chordsFor rows =="
             " (List.concat (rows |> List.map lockChordForOverviewEntry))",
             # Ctrl is taken back between clicks rather than held across them.
             "(chordsFor rows |> List.filter"
             " ((==) (EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL))"
             " |> List.length) == (rows |> List.length)"],
            definitions=self.repl.with_helpers([
                "chordsFor = \\rowsToLock ->"
                " rowsToLock |> List.concatMap lockChordForOverviewEntry",
                "rows = []",
            ]))
        self.assertEqual(
            answers, [True] * 2,
            "the batch is no longer the single lock chord repeated, so it is a "
            "gesture no recorded run has ever dispatched")

    def test_a_lock_click_still_needs_ctrl_without_shift(self):
        unlock = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
                  ", EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.MouseMoveTo { x = 300, y = 40 }"
                  ", EffectOnWindow.MouseMoveTo { x = 300, y = 60 }"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]")
        answers = self.ask([
            "lockClickLocationsFromStepEffects %s == []" % unlock,
            "lockClickLocationsFromStepEffects [] == []",
        ])
        self.assertEqual(
            answers, [True] * 2,
            "a gesture that is not a lock contributed clicks to a batch, or "
            "the batched lock chord stopped being recognised")


class ABatchedReadingTeachesTheRangeRuleNothingTest(unittest.TestCase):
    """The attribution discipline, **read** rather than executed.

    The mission runner's `updateLockRangeLearning` takes a whole
    `UpdateMemoryContext` where saxrat's takes records, so it cannot be run in
    `elm repl` -- the divergence #106 records the cost of, and the reason
    `test_max_targets_probe` reads this same function in both apps.
    """

    def setUp(self):
        self.rule = collapsed(top_level_block(
            source_of(MISSION_RUNNER_BOT_ELM), "updateLockRangeLearning"))

    def test_a_batched_step_is_recognised_from_the_effects(self):
        self.assertIn("stepWasBatched = 1 < (lockClickLocations |> List.length)",
                      self.rule,
                      "the rule no longer notices that a step asked for more "
                      "than one lock, so a batched reading's outcome is "
                      "attributed to whichever row happened to come first")

    def test_a_batched_reading_discharges_the_attempt_and_learns_nothing(self):
        self.assertIn("if stepWasBatched then", self.rule,
                      "the batched-reading guard is gone from the lock-range "
                      "rule, which is a range learned from an outcome that "
                      "belongs to no one click -- sticky for the session")
        self.assertIn("{ unchanged | attempt = Nothing }", self.rule,
                      "a batched reading no longer discharges the pending "
                      "attempt, so its verdict can be read against a bar the "
                      "batch itself filled -- the hole PR #151 closed")
        self.assertLess(
            self.rule.index("if stepWasBatched then"),
            self.rule.index("case attemptAfterClick of"),
            "the batch guard is asked after the attempt has been judged, "
            "which is no guard at all")

    def test_the_discharge_pr_151_added_is_still_there(self):
        """Batching must not re-open the hole it depends on."""
        self.assertIn(
            "else if not (lockAttemptCanTeachRange attempt) then", self.rule,
            "the mission runner no longer discharges a lock the client "
            "declined with the bar occupied, which is the rule that makes "
            "batching those locks cost the range rule nothing")
        self.assertIn(
            "(attempt.targetsCount /= 0) || (targetsCount /= 0)", self.rule,
            "the refusal no longer requires an empty target bar at both ends")


class ADroppedClickIsCountedTest(SharedRepl):
    """"I asked for three and got two" against "I asked for two".

    #163's finding is that posted input is dropped silently here, and a lost
    lock click leaves nothing behind but a bar with fewer targets in it.
    """

    def test_a_batch_opens_a_dispatch_and_a_single_lock_does_not(self):
        answers = self.ask([
            "(updateLockBatchAccounting (batchReading 3 1 1) noBatch).dispatch"
            " == openBatch 3 1 0",
            "(updateLockBatchAccounting (batchReading 1 1 1) noBatch).dispatch"
            " == Nothing",
            "(updateLockBatchAccounting (batchReading 0 1 1) noBatch).dispatch"
            " == Nothing",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the accounting no longer records what a batch asked for, so a "
            "dropped lock click leaves no trace at all")

    def test_the_bar_is_measured_from_the_reading_it_was_decided_from(self):
        answers = self.ask([
            # Decided with the bar at 1; by the reading the clicks are seen it
            # already holds 2. The batch is still judged against 1.
            "(updateLockBatchAccounting (batchReading 3 2 1) noBatch).dispatch"
            " == openBatch 3 1 0",
            "(updateLockBatchAccounting (batchReading 0 4 1)"
            " (batchState (openBatch 3 1 4) 0 0))"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 3"
            " , change = Nothing }",
        ])
        self.assertEqual(
            answers, [True] * 2,
            "the batch is judged against the bar on the reading that observed "
            "its clicks rather than the reading it was decided from, so locks "
            "that landed promptly read as locks that went missing")

    def test_a_short_batch_is_named_once_with_both_numbers(self):
        short = ("updateLockBatchAccounting (batchReading 0 3 1)"
                 " (batchState (openBatch 3 1 4) 0 0)")
        answers = self.ask([
            "(%s).change /= Nothing" % short,
            "(%s).clicksAnswered == 2" % short,
            "(%s).clicksAsked == 3" % short,
            # And the reading after it says nothing, the dispatch being closed.
            "(updateLockBatchAccounting (batchReading 0 3 1)"
            " (batchState Nothing 3 2)).change == Nothing",
        ])
        self.assertEqual(
            answers, [True] * 4,
            "a batch that came up short said nothing, or the sentence repeats "
            "every reading rather than once")
        sentence = self.repl.strings(
            ["(%s).change |> Maybe.withDefault \"\"" % short],
            definitions=self.repl.with_helpers([]))[0]
        for expected in ("3", "1", "unaccounted for"):
            self.assertIn(
                expected, sentence,
                "the shortfall sentence does not carry what was asked for, "
                "what the bar held, or that something is missing: %r" % sentence)

    def test_the_session_totals_only_rise(self):
        answers = self.ask([
            "(List.foldl batchStep noBatch"
            " [ batchReading 3 1 1, batchReading 0 2 1, batchReading 0 2 1"
            " , batchReading 0 2 1, batchReading 0 2 1, batchReading 0 2 1 ])"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 1 }",
            "(List.foldl batchStep (batchState Nothing 3 1)"
            " [ batchReading 2 1 1, batchReading 0 3 1 ])"
            " == { dispatch = Nothing, clicksAsked = 5, clicksAnswered = 3 }",
        ])
        self.assertEqual(
            answers, [True] * 2,
            "the session's asked and answered totals do not accumulate, so a "
            "run that loses a click on every batch reads like a healthy one")

    def test_the_wait_is_bounded_and_a_bar_that_catches_up_ends_it(self):
        answers = self.ask([
            "lockBatchReadingsBeforeVerdict == 4",
            "0 < lockBatchReadingsBeforeVerdict",
            "lockBatchReadingsBeforeVerdict < lockAttemptReadingsBeforeVerdict",
            "(updateLockBatchAccounting (batchReading 0 1 1)"
            " (batchState (openBatch 3 1 3) 0 0)).dispatch == openBatch 3 1 4",
            "(updateLockBatchAccounting (batchReading 0 1 1)"
            " (batchState (openBatch 3 1 4) 0 0)).dispatch == Nothing",
            "(updateLockBatchAccounting (batchReading 0 4 1)"
            " (batchState (openBatch 3 1 0) 0 0)).dispatch == Nothing",
            # A client answering at once costs no settling reading at all.
            "(updateLockBatchAccounting (batchReading 3 4 1) noBatch)"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 3"
            " , change = Nothing }",
        ])
        self.assertEqual(
            answers, [True] * 7,
            "the batch wait is unbounded, closes on the wrong reading, or no "
            "longer ends early when the target bar has caught up")

    def test_the_accounting_reaches_for_nothing_the_range_rule_owns(self):
        body = collapsed(top_level_block(
            source_of(MISSION_RUNNER_BOT_ELM), "updateLockBatchAccounting"))
        for forbidden in ("provenAtMeters", "refusedAtMeters", "lockAttempt",
                          "overviewEntryLockHandle", "entries"):
            self.assertNotIn(
                forbidden, body,
                "the batch accounting reads %r, so a number that cannot tell a "
                "dropped click from a dead rat is reaching the rule whose "
                "whole safety is refusing to guess" % forbidden)


class TheSettlingWindowAndWhatAnOperatorReadsTest(SharedRepl):
    """A batch is not re-issued while the target bar is still catching up."""

    def test_the_site_waits_exactly_while_a_dispatch_is_open(self):
        answers = self.ask([
            "lockBatchIsSettling Nothing == False",
            "lockBatchIsSettling (openBatch 3 1 0)",
            "lockBatchIsSettling (openBatch 3 1 4)",
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the lock site no longer waits out a batch it has already asked "
            "for, so the rows are clicked again before the bar can answer")

    def test_the_branch_consults_it_before_asking_for_another_batch(self):
        """Read as the form of the branch, not as a substring: the branch's own
        log text names the settling window."""
        branch = collapsed(combat_decision_source())
        self.assertIn(
            "if lockBatchIsSettling context.memory.lockBatch then", branch,
            "the lock site does not consult the settling window, so a batch is "
            "re-issued before the target bar has answered the first one")
        self.assertLess(
            branch.index("if lockBatchIsSettling context.memory.lockBatch then"),
            branch.index("lockTargetsFromOverviewEntries"),
            "the settling window is asked after the batch is dispatched, which "
            "is no guard at all")

    def test_the_batch_keeps_the_line_operators_grep_for(self):
        """`Lock more targets.` is `describeMaxTargetsProbe`'s deliberate
        wording, and a reading where three locks were asked for is still a
        reading where more targets were asked for."""
        asked, settling = self.repl.strings(
            ["describeLockBatchAsked []",
             "describeLockBatchSettling (openBatch 3 1 2)"],
            definitions=self.repl.with_helpers([]))
        self.assertTrue(
            asked.startswith("Lock more targets."),
            "the batched lock site stopped saying 'Lock more targets.', so the "
            "line an operator has been grepping for no longer appears on the "
            "readings it was about: %r" % asked)
        for expected in ("3", "2"):
            self.assertIn(
                expected, settling,
                "the settling line does not say how many locks were asked for "
                "or how long ago: %r" % settling)

    def test_the_status_clause_carries_both_totals_and_the_open_batch(self):
        quiet, waiting = self.repl.strings(
            ["describeLockBatch noBatch",
             "describeLockBatch (batchState (openBatch 3 1 2) 12 10)"],
            definitions=self.repl.with_helpers([]))
        self.assertIn("none waiting", quiet)
        for expected in ("12", "10", "3", "2"):
            self.assertIn(
                expected, waiting,
                "the status clause drops the session totals or the batch it is "
                "waiting on: %r" % waiting)


class TheWiringIsWhatMakesAnyOfThisReachableTest(unittest.TestCase):
    """The lines that could revert this while everything still compiled."""

    def setUp(self):
        self.source = source_of(MISSION_RUNNER_BOT_ELM)

    def test_the_memory_update_folds_the_accounting_in(self):
        binding = collapsed(indented_block(
            self.source, "lockBatchAccounting", indent="        "))
        self.assertIn("updateLockBatchAccounting", binding)
        self.assertIn("botMemoryBefore.targetsCountLastReading", binding,
                      "the accounting is handed this reading's target count "
                      "rather than the previous reading's, so a batch is "
                      "judged against a bar it has already moved")

    def test_the_previous_readings_target_count_is_written_every_reading(self):
        self.assertIn(
            ", targetsCountLastReading = context.readingFromGameClient.targets "
            "|> List.length", collapsed(self.source),
            "the previous reading's target bar is not recorded, so nothing can "
            "say what a batch was asked against")

    def test_the_shortfall_is_announced_at_the_root(self):
        root = collapsed(top_level_block(self.source, "missionBotDecisionRoot"))
        self.assertIn(
            "context.memory.lockBatchLastChange", root,
            "a batch that came up short is never printed, so the one thing "
            "that can report a dropped lock click says nothing")

    def test_the_two_learned_verdict_adjacencies_are_undisturbed(self):
        """`test_learned_max_targets` and `test_drone_launch_refusal` each pin a
        pair of these lines as adjacent. The batch's line goes at the end of the
        list rather than between them -- this is the case that says so here, so
        a later insertion is caught in the file that made it."""
        root = collapsed(top_level_block(self.source, "missionBotDecisionRoot"))
        self.assertIn(
            "context.memory.lockRangeLastChange , context.memory"
            ".maxTargetsLastChange", root,
            "the batch's verdict line was inserted between the lock range's "
            "and the ceiling's, which breaks test_learned_max_targets")
        self.assertIn(
            "context.memory.maxTargetsLastChange , context.memory"
            ".droneLaunchLastChange", root,
            "the batch's verdict line was inserted between the ceiling's and "
            "the drone cap's, which breaks test_drone_launch_refusal")

    def test_the_status_line_prints_the_clause(self):
        self.assertIn(
            "describeLockBatch (lockBatchStateFrom context)",
            collapsed(self.source),
            "the status line no longer carries the batch clause, so the "
            "session totals that separate a dropped click from a dead rat are "
            "not visible on any reading")

    def test_both_lock_sites_build_the_same_chord(self):
        single = collapsed(top_level_block(
            self.source, "lockTargetFromOverviewEntry"))
        batch = collapsed(top_level_block(
            self.source, "lockTargetsFromOverviewEntries"))
        self.assertIn("lockChordForOverviewEntry overviewEntry", single,
                      "the single lock builds its own chord again, so the two "
                      "sites can come to dispatch different gestures")
        self.assertIn("List.concatMap lockChordForOverviewEntry", batch,
                      "the batch builds its own chord again")


class TheRecordedRunsShowASmallerRampThanSaxrats(unittest.TestCase):
    """The premise, recounted from this bot's own corpus.

    Stated as relations rather than as the counts in the doc comment, so a
    corpus that grows cannot turn a true claim red. The point of the case is
    that the mission runner's ramp is *smaller* than saxrat's -- most of its
    lock commands stand alone -- which is what makes the cap's sizing this bot's
    own question rather than an inherited one.
    """

    STEP = re.compile(r"^# \[(\d+)\.(\d+)\] ")
    LOCK = re.compile(r"Lock target from overview entry")
    SEND = re.compile(r"^#   task send-effects-\d+: WindowsInputRequest")

    @classmethod
    def setUpClass(cls):
        import glob
        paths = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "mission_run*.log")))
        if not paths:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what those runs can "
                "say about the lock ramp cannot be consulted here")

        cls.gaps = []
        cls.dispatches = 0
        cls.bursts = []
        for path in paths:
            reading = None
            pending = False
            previous = None
            current = 0
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    match = cls.STEP.match(line)
                    if match:
                        reading = int(match.group(1))
                        pending = False
                    elif cls.LOCK.search(line):
                        pending = True
                    elif cls.SEND.match(line) and pending and reading is not None:
                        cls.dispatches += 1
                        if previous is not None:
                            gap = reading - previous
                            cls.gaps.append(gap)
                            if 0 < gap <= 4:
                                current += 1
                            else:
                                if current:
                                    cls.bursts.append(current)
                                current = 1
                        else:
                            current = 1
                        previous = reading
                        pending = False
            if current:
                cls.bursts.append(current)

    def test_locks_were_dispatched_one_at_a_time(self):
        self.assertGreater(
            self.dispatches, 100,
            "the recorded runs carry almost no lock commands, so they cannot "
            "say anything about the ramp this change is about")
        self.assertEqual(
            [gap for gap in self.gaps if gap < 0], [],
            "the reading numbers do not increase, so the gap measurement is "
            "not measuring what it claims to")

    def test_most_bursts_are_a_single_lock_unlike_saxrats(self):
        """76% of them when this was written. Batching therefore applies to a
        minority of this bot's locks, which is why the gain is stated small."""
        self.assertGreater(len(self.bursts), 50)
        alone = [burst for burst in self.bursts if burst == 1]
        self.assertGreater(
            len(alone), len(self.bursts) // 2,
            "most lock commands in this bot's corpus are no longer solitary, "
            "which would mean the ramp is bigger than the doc comment claims "
            "and the cap wants re-sizing")

    def test_but_multi_lock_bursts_carry_a_large_share_of_the_locks(self):
        """46% when this was written -- enough that batching is worth doing at
        all, which is the other half of the same measurement."""
        multi = [burst for burst in self.bursts if burst > 1]
        self.assertGreater(
            sum(multi), self.dispatches // 5,
            "runs of consecutive locks carry too small a share of this bot's "
            "lock commands for batching to be worth the blind interval")


if __name__ == "__main__":
    unittest.main()
