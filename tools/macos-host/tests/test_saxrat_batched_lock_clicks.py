"""Tests for saxrat asking the client for several locks in one step.

`lockTargetFromOverviewEntry` issued one Ctrl+click and handed the step back, so
the next lock waited for the next reading. Measured on `saxrat_run16.log`: 490
lock commands were dispatched and the median gap between two of them is 2
readings, with the reading cadence at 1.5 s plus the read. With the learned
ceiling now 6, filling the bar is most of the first twenty seconds of every
engagement.

**Three things had to be true before batching was worth building, and this file
executes all three.**

The framework has to permit several clicks in one dispatch.
`ContinueSession.effectsOnGameClient` is an unbounded `List`, `BotFramework`
maps the whole of it into one `WindowsInputRequest` with a `WaitMilliseconds`
between every pair, and the host walks the list item by item -- so what is
asserted here is the round trip that matters to this change: the effects
`lockChordForOverviewEntry` builds for N rows are read back by
`lockClickLocationsFromStepEffects` as N points, in order.

**The attribution has to survive.** A batched step teaches the lock-range rule
**nothing** rather than guessing, which is `overviewEntryLockHandle`'s posture
applied to the step rather than to the row. That costs nothing, and the reason
is `lockAttemptCanTeachRange`: a lock asked with the bar occupied is discharged
rather than judged, so batching exactly those locks throws away no evidence. The
one lock that can teach a refusal -- the first of an engagement, bar empty -- is
still asked alone, and `lockBatchSize` is where that is decided.

**A dropped click has to be visible.** #163 established that posted input is
dropped silently under load in this environment, at 53-100 ms per event in the
two runs that lost a typed query against under 18 ms everywhere else, and #75's
`Emperor Family Bureau` arriving as `eueu` is the same mechanism. A batch is
exactly that shape and a lost lock click leaves nothing behind but a bar with
fewer targets in it. `updateLockBatchAccounting` writes down what was asked for
and reads the bar back, so "I asked for six and got four" and "I asked for four"
are different readings.

The rules are executed through the real `Bot.elm` in `elm repl`, and the overview
rows they are asked about come from the real `EveOnline.ParseUserInterface`, so a
hand-written record cannot drift from what the parser would have produced. The
wiring and the placement -- which are not expressions -- are read out of the
source through a reader sliced by **indentation**, since the bindings under test
build record literals and the `let_binding` shape stops at the opening brace.

Confirmed by mutation, fifteen of them, each failing a named case: the effects
reader taking only the first click again; a batched reading teaching the range
rule from an outcome it cannot attribute; a pending attempt carried across a
batch rather than discharged; the first lock of an engagement batched; the probe
batched; the click cap raised past everything this bot has ever dispatched in one
step and lowered so nothing batches; the free-slot bound dropped; the
lockable-row bound dropped; the settling window removed so a whole batch is
re-issued; the batch judged against the reading that observes it rather than the
one it was decided from; the shortfall never reported; the totals not
accumulating; the accounting reaching into the range rule; and the batch built
from rows the ship cannot reach.

Nothing here reads a live game client or a running bot. One case reads the
recorded saxrat runs, and only reads them; it skips with a stated reason on a
machine that has none.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, collapsed, source_of)
from test_saxrat_learned_lock_range import (
    LockRangeRepl, ROW_HEIGHT, ROW_PITCH, ROW_TOP, flying, overview_rows,
    row_center)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Measured over all 16 recorded saxrat runs and their 50,043 `send-effects`
# steps: the longest input step this bot has ever dispatched is 4.68 s, the
# median is 1.03 s, and a lock step's own median is 2.56 s. Three clicks is
# about seven seconds, which is deliberately past the longest recorded step --
# so the cap is what keeps "past it" bounded rather than open-ended. A cap of 1
# batches nothing at all; a cap this bot could not spend in a step it can still
# read out of is the other side.
LONGEST_RECORDED_INPUT_STEP_SECONDS = 4.68
MEDIAN_LOCK_STEP_SECONDS = 2.56


def indented_block(source, name, indent):
    """A binding's right-hand side, sliced by indentation.

    `let_binding`'s shape -- read to the next ` <name> = ` -- stops at a record
    literal, and every binding this file asks about builds one. PRs #147, #156,
    #159 and #162 each paid for that once with an assertion that passed having
    read nothing, so this reads to the next line indented no further than the
    binding's own name and no shorter.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    for match in re.finditer(r"\n([ ]*)(\S)", rest):
        if len(match.group(1)) <= len(indent):
            return rest[:match.start()]
    return rest


def top_level_block(source, name):
    """One top-level declaration, from its annotation to the next one."""
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def anomaly_decision_source():
    return top_level_block(source_of(SAXRAT_BOT_ELM), "decideActionInAnomaly")


class BatchRepl(LockRangeRepl):
    """The lock-range harness plus what a batch needs to be expressed.

    Everything here is Elm rather than a Python string template wherever it can
    be: `batchStep` in particular folds the accounting's own answer back into
    its own input, which is what a session does and what a Python
    reconstruction of one would get to define for itself.
    """

    BATCH_HELPERS = [
        # The chord the bot really builds, for N rows, concatenated exactly as
        # `lockTargetsFromOverviewEntries` concatenates it.
        "chordsFor = \\rowsToLock ->"
        " rowsToLock |> List.concatMap lockChordForOverviewEntry",
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
        # The accounting's own answer folded back into its own input.
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
        return list(definitions) + self.HELPERS + self.BATCH_HELPERS


class TheStepCarriesEveryLockClickTest(unittest.TestCase):
    """What the bot dispatches and what the accounting counts are one thing.

    The chord is built once (`lockChordForOverviewEntry`) and read back once
    (`lockClickLocationsFromStepEffects`), so the two cannot come apart -- which
    is what makes "clicks asked for" a number derived from the effects rather
    than from the rows the decision happened to pick.
    """

    ROWS = [("5,000 m", "Centii Savage", "111", False),
            ("6,000 m", "Centii Ravener", "222", False),
            ("7,000 m", "Centii Scavenger", "333", False)]

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        return self.repl.with_helpers([
            LockRangeRepl.entries_binding("rows", self.ROWS)])

    def test_three_chords_read_back_as_three_points_in_order(self):
        """The round trip, over rows the real parser produced.

        A reader answering `Maybe` could not tell one lock from six, so it would
        have gone on attributing the next reading's outcome to whichever click
        it happened to take -- the feature working while the measurement behind
        it quietly stopped.
        """
        centers = [row_center(index) for index in range(len(self.ROWS))]
        answers = self.repl.evaluate(
            ["(chordsFor rows |> lockClickLocationsFromStepEffects) == [ %s ]"
             % ", ".join("{ x = %d, y = %d }" % point for point in centers),
             "(chordsFor rows |> lockClickLocationsFromStepEffects"
             " |> List.length) == 3",
             # One row is still one point, so a single lock is unchanged.
             "(chordsFor (List.take 1 rows)"
             " |> lockClickLocationsFromStepEffects |> List.length) == 1",
             "(chordsFor [] |> lockClickLocationsFromStepEffects) == []"],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "the effects reader no longer returns every lock click of a step, "
            "so a batched step is indistinguishable from a single lock and its "
            "outcome would be attributed to one row of it")

    def test_the_chord_is_the_same_shape_repeated(self):
        """A batch is N copies of the lock this bot has always dispatched.

        Asserted as an equality between the concatenation and the single chord
        repeated, rather than by counting effects: a version that held Ctrl
        across the whole run would still produce the right number of points and
        a different gesture.
        """
        answers = self.repl.evaluate(
            ["chordsFor rows =="
             " (List.concat (rows |> List.map lockChordForOverviewEntry))",
             "(chordsFor rows |> List.length) == 15",
             # Ctrl is taken back between clicks rather than held across them.
             "(chordsFor rows |> List.filter"
             " ((==) (EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL))"
             " |> List.length) == 3"],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "the batch is no longer the single lock chord repeated, so it is a "
            "gesture no recorded run has ever dispatched")

    def test_a_lock_click_still_needs_ctrl_without_shift(self):
        """The batch must not widen what counts as a lock.

        The unlock holds Shift as well and the loot window's Ctrl+W carries no
        mouse effect, so neither may contribute a point to a batch's count.
        """
        unlock = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
                  ", EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.MouseMoveTo { x = 300, y = 40 }"
                  ", EffectOnWindow.MouseMoveTo { x = 300, y = 60 }"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]")
        answers = self.repl.evaluate(
            ["lockClickLocationsFromStepEffects %s == []" % unlock,
             "(lockClicksAt [ { x = 10, y = 20 }, { x = 10, y = 40 } ]"
             " |> lockClickLocationsFromStepEffects) =="
             " [ { x = 10, y = 20 }, { x = 10, y = 40 } ]"],
            definitions=self.repl.with_helpers([]))
        self.assertEqual(
            answers, [True] * 2,
            "a gesture that is not a lock contributed clicks to a batch, or "
            "the batched lock chord stopped being recognised")


class TheBatchSizeIsBoundedTest(unittest.TestCase):
    """How many rows one step asks for, and every way that is bounded."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def sizes(self, cases):
        return self.repl.evaluate(
            ["lockBatchSize (situation %d %d %d %s) == %d"
             % (held, take, rows, "True" if probe else "False", expected)
             for held, take, rows, probe, expected in cases],
            definitions=self.repl.with_helpers([]))

    def test_the_first_lock_of_an_engagement_is_asked_alone(self):
        """The one lock that can teach a refusal, and it is not batched.

        `lockAttemptCanTeachRange` is `targetsCount == 0`, so an attempt begun
        with the bar occupied is discharged rather than judged and could never
        move either bound. Asking the bar-empty lock alone is therefore what
        makes batching cost the lock-range rule nothing at all, rather than a
        hope that the two do not collide.
        """
        answers = self.sizes([
            (0, 6, 6, False, 1),
            (0, 6, 1, False, 1),
            (0, 2, 2, False, 1),
            # One target held is already enough to batch.
            (1, 6, 6, False, 3),
        ])
        self.assertEqual(
            answers, [True] * 4,
            "the first lock of an engagement is now batched, so the only lock "
            "that could ever have taught the refusal bound is issued in a step "
            "the range rule refuses to learn from")

    def test_the_probe_is_asked_alone(self):
        """#150's probe is a measurement, deliberately one row beyond the
        ceiling. An answer arriving alongside several other locks is an answer
        to none of them in particular."""
        answers = self.sizes([
            (1, 7, 6, True, 1),
            (5, 7, 6, True, 1),
            (2, 7, 6, False, 3),
        ])
        self.assertEqual(
            answers, [True] * 3,
            "the lock-slot probe is issued inside a batch, so what the client "
            "answers cannot be attributed to the probe")

    def test_it_never_exceeds_the_free_slots(self):
        """`rowsToTake` is `maxTargetsRowsToTake`'s own answer, so the batch and
        `Enough locked targets.` cannot disagree about whether there is room."""
        answers = self.sizes([
            (4, 6, 6, False, 2),
            (5, 6, 6, False, 1),
            # At or past the ceiling the answer is still a valid one rather
            # than zero: this branch is only reached where something is about
            # to be clicked.
            (6, 6, 6, False, 1),
            (7, 6, 6, False, 1),
        ])
        self.assertEqual(
            answers, [True] * 4,
            "a batch asked for more locks than the ship has free slots, so it "
            "spends clicks on refusals the ceiling already knows about")

    def test_it_never_exceeds_the_rows_the_ship_can_reach(self):
        """A row out of range is answered by approaching it, and an approach
        cannot be batched with anything."""
        answers = self.sizes([
            (1, 6, 1, False, 1),
            (1, 6, 2, False, 2),
            (1, 6, 0, False, 1),
        ])
        self.assertEqual(
            answers, [True] * 3,
            "a batch counted rows the ship cannot lock from where it stands")

    def test_the_click_cap_bounds_it_and_sits_where_the_corpus_puts_it(self):
        """A batch is a step with no reading in it, so its length is time the
        retreat cannot act on -- and #163's dropped input is likelier the longer
        the burst.

        The boundary pair is asked beside fixed values, because a case that only
        asks about `cap` and `cap - 1` passes for any cap at all, including one
        that batches nothing (CLAUDE.md's own note on the four cases #120
        shipped with that hole).
        """
        answers = self.repl.evaluate([
            "lockBatchSize (situation 1 20 20 False) == lockBatchMaximumClicks",
            "1 < lockBatchMaximumClicks",
            "lockBatchMaximumClicks <= 4",
            "lockBatchSize (situation 1 20 20 False) == 3",
            "lockBatchSize (situation 1 20 2 False) == 2",
        ], definitions=self.repl.with_helpers([]))
        self.assertEqual(
            answers, [True] * 5,
            "the per-step click cap is gone, batches nothing, or runs far past "
            "the 4.68 s longest input step this bot has ever dispatched (a "
            "lock step's median is %.2f s)" % MEDIAN_LOCK_STEP_SECONDS)

    def test_the_cap_is_worth_more_than_one_step_of_the_ramp(self):
        """Stated as the relation the change exists for: filling a six-slot bar
        from the first lock takes at least three steps rather than six."""
        answers = self.repl.evaluate([
            # First lock alone, then batches of at most the cap.
            "(1 + ((6 - 1) + lockBatchMaximumClicks - 1)"
            " // lockBatchMaximumClicks) < 6",
        ], definitions=self.repl.with_helpers([]))
        self.assertTrue(
            answers[0],
            "batching no longer takes fewer steps than one lock a reading, "
            "which is the whole of the change")


class ABatchedReadingTeachesTheRangeRuleNothingTest(unittest.TestCase):
    """The attribution discipline, applied to the step rather than to the row.

    This is the part that must not be simplified. If several locks are issued in
    one reading, the next reading's outcome may be an answer to any of them, and
    the bar the refusal test reads is the bar the batch itself filled. So a
    batched reading teaches **nothing** rather than guessing -- which is exactly
    what `overviewEntryLockHandle` already does to a pocket of same-named rats.
    """

    IDENTIFIED = [("60,000 m", "Centior Monster", "111", False)]
    IDENTIFIED_TARGETED = [("60,000 m", "Centior Monster", "111", True)]
    TWO_ROWS = [("60,000 m", "Centior Monster", "111", False),
                ("61,000 m", "Centii Savage", "222", False)]
    TWO_ROWS_TARGETED = [("60,000 m", "Centior Monster", "111", True),
                         ("61,000 m", "Centii Savage", "222", True)]

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        return self.repl.with_helpers([
            SaxratRepl.reading_binding(
                "waiting", [overview_rows(self.IDENTIFIED), flying()]),
            SaxratRepl.reading_binding(
                "locked", [overview_rows(self.IDENTIFIED_TARGETED), flying()]),
            SaxratRepl.reading_binding(
                "pair", [overview_rows(self.TWO_ROWS), flying()]),
            SaxratRepl.reading_binding(
                "pairLocked",
                [overview_rows(self.TWO_ROWS_TARGETED), flying()]),
        ])

    def batched(self, name, targets, rows):
        """A reading whose previous step asked for `rows` locks."""
        points = ", ".join("{ x = %d, y = %d }" % row_center(index)
                           for index in range(rows))
        return "(lockReading %s %d (lockClicksAt [ %s ]))" % (
            name, targets, points)

    def single(self, name, targets, row):
        return "(lockReading %s %d (lockClickAt %d %d))" % (
            (name, targets) + row_center(row))

    def test_a_batched_reading_moves_neither_bound_and_opens_no_attempt(self):
        """The outcome is unattributable, so nothing is concluded from it.

        The single-click control beside it is what makes this a case about
        *batching* rather than about the fixture: the same rows, the same
        distances and the same locked indicator teach the proven bound when one
        click was issued and teach nothing when two were.
        """
        answers = self.repl.evaluate([
            # Two clicks, and the row now reads locked: the single-click path
            # would credit 60000 m.
            "(updateLockRangeLearning %s noEvidence)"
            " == { attempt = Nothing, provenAtMeters = Nothing"
            " , refusedAtMeters = Nothing, change = Nothing }"
            % self.batched("pairLocked", 2, 2),
            # The control: one click at the same row does learn.
            "(updateLockRangeLearning %s noEvidence).provenAtMeters"
            " == Just 60000" % self.single("pairLocked", 1, 0),
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "a batched reading taught the lock-range rule from an outcome it "
            "cannot attribute to any one of the locks it issued, which is a "
            "range learned from a guess and sticky for the session")

    def test_a_pending_attempt_is_discharged_rather_than_judged(self):
        """A batch fills the bar, which is the very thing the refusal test
        reads to decide a slot was free.

        Carrying the attempt across would let its verdict be read against a bar
        the batch itself filled, so it is dropped on the reading the batch is
        seen -- and the control shows the same attempt surviving a reading whose
        step issued one click.
        """
        pending = ("{ fromSetting = 66000, provenAtMeters = Nothing"
                   ", refusedAtMeters = Nothing"
                   ", attempt = Just { handle = \"id:111\""
                   ", distanceInMeters = 60000, targetsCount = 0"
                   ", readingsWaited = 3 } }")
        answers = self.repl.evaluate([
            "(updateLockRangeLearning %s %s).attempt == Nothing"
            % (self.batched("pair", 0, 2), pending),
            "(updateLockRangeLearning %s %s).change == Nothing"
            % (self.batched("pair", 0, 2), pending),
            # The control: a step with one click carries the attempt on.
            "((updateLockRangeLearning %s %s).attempt |> Maybe.map"
            " .readingsWaited) == Just 4"
            % (self.single("pair", 0, 0), pending),
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "a lock attempt survived a batched reading, so its verdict can be "
            "read against a target bar the batch itself filled -- which is the "
            "hole PR #151 closed, re-opened by batching")

    def test_a_batch_that_landed_nothing_teaches_no_refusal(self):
        """The worst available case: several locks issued, nothing locked, the
        bar empty at both ends. Every clause of the refusal test is satisfied
        and the rule must still say nothing, because it cannot say which click
        the client was answering."""
        answers = self.repl.evaluate([
            "(updateLockRangeLearning %s noEvidence).refusedAtMeters"
            " == Nothing" % self.batched("pair", 0, 2),
            # Folded: the same reading eight times over, which is past the
            # verdict count, still teaches nothing.
            "(List.foldl (\\_ state -> step %s state) noEvidence"
            " (List.range 1 8)).refusedAtMeters == Nothing"
            % self.batched("pair", 0, 2),
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "a batched step taught the refusal bound, so the bot has learned a "
            "lock range from a reading that cannot say which lock was refused")

    def test_the_rule_still_learns_from_the_engagement_s_first_lock(self):
        """Batching must not cost the learning it was arranged around.

        A session where the first lock is asked alone still moves both bounds
        exactly as before, which is what makes `lockBatchSize`'s bar-empty
        clause load-bearing rather than decorative.
        """
        answers = self.repl.evaluate([
            "(updateLockRangeLearning %s noEvidence).provenAtMeters"
            " == Just 60000" % self.single("locked", 1, 0),
            "((List.foldl (\\_ state -> step %s state)"
            " (step %s noEvidence) (List.range 1 9)).refusedAtMeters)"
            " == Just 60000"
            % (self.single("waiting", 0, 0), self.single("waiting", 0, 0)),
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "the lock-range rule stopped learning from a single lock, so "
            "batching has cost the measurement rather than leaving it alone")


class ADroppedClickIsCountedTest(unittest.TestCase):
    """"I asked for six and got four" against "I asked for four".

    #163's finding is that posted input is dropped silently here, and a lost
    lock click leaves nothing behind but a bar with fewer targets in it. This is
    the only thing in the bot that can tell the two apart.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions(self):
        return self.repl.with_helpers([])

    def test_a_batch_opens_a_dispatch_and_a_single_lock_does_not(self):
        """Only a step that asked for more than one lock is accounted for.

        A single lock is left exactly as it was -- repeated clicks and all --
        because that is the behaviour every recorded run was flown on.
        """
        answers = self.repl.evaluate([
            "(updateLockBatchAccounting (batchReading 3 1 1) noBatch).dispatch"
            " == openBatch 3 1 0",
            "(updateLockBatchAccounting (batchReading 1 1 1) noBatch).dispatch"
            " == Nothing",
            "(updateLockBatchAccounting (batchReading 0 1 1) noBatch).dispatch"
            " == Nothing",
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "the accounting no longer records what a batch asked for, so a "
            "dropped lock click leaves no trace at all")

    def test_the_bar_is_measured_from_the_reading_the_step_was_decided_from(self):
        """`targetsCountBefore`, not the reading that observes the click.

        Some of a batch may already have landed by the reading the clicks are
        seen in, so measuring from there would understate what the client
        answered and report drops that did not happen.
        """
        answers = self.repl.evaluate([
            # Decided with the bar at 1; by the reading the clicks are seen it
            # already holds 2. The batch is still judged against 1.
            "(updateLockBatchAccounting (batchReading 3 2 1) noBatch).dispatch"
            " == openBatch 3 1 0",
            # Four readings later the bar holds 4: three asked, three answered.
            "(updateLockBatchAccounting (batchReading 0 4 1)"
            " (batchState (openBatch 3 1 4) 0 0))"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 3"
            " , change = Nothing }",
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "the batch is judged against the bar on the reading that observed "
            "its clicks rather than the reading it was decided from, so locks "
            "that landed promptly read as locks that went missing")

    def test_a_short_batch_is_named_once_with_both_numbers(self):
        """Six asked and four answered has to be a sentence an operator can act
        on, and it has to say so once rather than on every reading."""
        landed = ("updateLockBatchAccounting (batchReading 0 4 1)"
                  " (batchState (openBatch 3 1 4) 0 0)")
        short = ("updateLockBatchAccounting (batchReading 0 3 1)"
                 " (batchState (openBatch 3 1 4) 0 0)")
        answers = self.repl.evaluate([
            "(%s).clicksAsked == 3" % landed,
            "(%s).clicksAnswered == 3" % landed,
            "(%s).change == Nothing" % landed,
            # Two of three landed: the shortfall is reported.
            "(%s).change /= Nothing" % short,
            "(%s).clicksAnswered == 2" % short,
            # And the reading after it says nothing, the dispatch being closed.
            "(updateLockBatchAccounting (batchReading 0 3 1)"
            " (batchState Nothing 3 2)).change == Nothing",
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 6,
            "a batch that came up short said nothing, or a batch that landed "
            "in full reported a shortfall, or the sentence repeats every "
            "reading rather than once")
        sentence = self.repl.strings(
            ["(%s).change |> Maybe.withDefault \"\"" % short],
            definitions=self.definitions())[0]
        for expected in ("3", "1", "unaccounted for"):
            self.assertIn(
                expected, sentence,
                "the shortfall sentence does not carry what was asked for, "
                "what the bar held, or that something is missing: %r"
                % sentence)

    def test_the_session_totals_only_rise(self):
        """A run whose answered count trails its asked count all evening is
        input being dropped, which is the distinction a single reading cannot
        make and a session can."""
        answers = self.repl.evaluate([
            "(List.foldl batchStep noBatch"
            " [ batchReading 3 1 1, batchReading 0 2 1, batchReading 0 2 1"
            " , batchReading 0 2 1, batchReading 0 2 1, batchReading 0 2 1 ])"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 1 }",
            # A second batch adds to the same totals.
            "(List.foldl batchStep (batchState Nothing 3 1)"
            " [ batchReading 2 1 1, batchReading 0 3 1 ])"
            " == { dispatch = Nothing, clicksAsked = 5, clicksAnswered = 3 }",
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 2,
            "the session's asked and answered totals do not accumulate, so a "
            "run that loses a click on every batch reads like a healthy one")

    def test_the_wait_is_bounded_and_a_bar_that_catches_up_ends_it_early(self):
        """The dispatch is what holds the lock site still, so it has to close
        whatever the client does."""
        answers = self.repl.evaluate([
            "lockBatchReadingsBeforeVerdict == 4",
            "0 < lockBatchReadingsBeforeVerdict",
            "lockBatchReadingsBeforeVerdict < lockAttemptReadingsBeforeVerdict",
            # Never closes early while short and under the bound.
            "(updateLockBatchAccounting (batchReading 0 1 1)"
            " (batchState (openBatch 3 1 3) 0 0)).dispatch == openBatch 3 1 4",
            # Closes at the bound.
            "(updateLockBatchAccounting (batchReading 0 1 1)"
            " (batchState (openBatch 3 1 4) 0 0)).dispatch == Nothing",
            # Or early, once the bar has caught up.
            "(updateLockBatchAccounting (batchReading 0 4 1)"
            " (batchState (openBatch 3 1 0) 0 0)).dispatch == Nothing",
            # And a client that answered at once costs no settling reading:
            # the bar already holds all three on the reading the clicks are
            # seen, so the batch is judged there rather than waited out.
            "(updateLockBatchAccounting (batchReading 3 4 1) noBatch)"
            " == { dispatch = Nothing, clicksAsked = 3, clicksAnswered = 3"
            " , change = Nothing }",
        ], definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 7,
            "the batch wait is unbounded, closes on the wrong reading, or no "
            "longer ends early when the target bar has caught up")

    def test_the_accounting_reaches_for_nothing_the_range_rule_owns(self):
        """It reports and never decides, which is why the confounds it carries
        (a rat dying inside the window, the ship locking something by itself)
        are stated rather than designed around."""
        body = collapsed(top_level_block(
            source_of(SAXRAT_BOT_ELM), "updateLockBatchAccounting"))
        for forbidden in ("provenAtMeters", "refusedAtMeters", "lockAttempt",
                          "overviewEntryLockHandle", "entries"):
            self.assertNotIn(
                forbidden, body,
                "the batch accounting reads %r, so a number that cannot tell a "
                "dropped click from a dead rat is reaching the rule whose "
                "whole safety is refusing to guess" % forbidden)


class TheSettlingWindowTest(unittest.TestCase):
    """A batch is not re-issued while the target bar is still catching up.

    Without it the next reading finds the same rows unlocked and clicks every
    one of them again -- a whole batch re-issued, which is several seconds of an
    engagement spent asking for locks the client has already granted.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_site_waits_exactly_while_a_dispatch_is_open(self):
        answers = self.repl.evaluate([
            "lockBatchIsSettling Nothing == False",
            "lockBatchIsSettling (openBatch 3 1 0)",
            "lockBatchIsSettling (openBatch 3 1 4)",
        ], definitions=self.repl.with_helpers([]))
        self.assertEqual(
            answers, [True] * 3,
            "the lock site no longer waits out a batch it has already asked "
            "for, so the rows are clicked again before the bar can answer")

    def test_the_branch_consults_it_before_asking_for_another_batch(self):
        """Read as the form of the branch, not as a substring: the branch's own
        log text names the settling window, so a case asserting a name appears
        in it can pass with the guard gone."""
        branch = collapsed(anomaly_decision_source())
        self.assertIn(
            "if lockBatchIsSettling context.memory.lockBatch then", branch,
            "the lock site does not consult the settling window, so a batch is "
            "re-issued before the target bar has answered the first one")
        self.assertLess(
            branch.index("if lockBatchIsSettling context.memory.lockBatch then"),
            branch.index("lockTargetsFromOverviewEntries"),
            "the settling window is asked after the batch is dispatched, which "
            "is no guard at all")

    def test_the_wait_says_what_it_is_waiting_for(self):
        answers = self.repl.strings(
            ["describeLockBatchSettling (openBatch 3 1 2)"],
            definitions=self.repl.with_helpers([]))
        for expected in ("3", "2"):
            self.assertIn(
                expected, answers[0],
                "the settling line does not say how many locks were asked for "
                "or how long ago: %r" % answers[0])


class TheStatusLineAndTheDecisionLogCarryItTest(unittest.TestCase):
    """What an operator reads, executed rather than asserted by substring."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(BatchRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_status_clause_carries_both_totals_and_the_open_batch(self):
        quiet, waiting = self.repl.strings([
            "describeLockBatch noBatch",
            "describeLockBatch (batchState (openBatch 3 1 2) 12 10)",
        ], definitions=self.repl.with_helpers([]))
        self.assertIn("none waiting", quiet)
        for expected in ("12", "10", "3", "2"):
            self.assertIn(
                expected, waiting,
                "the status clause drops the session totals or the batch it is "
                "waiting on: %r" % waiting)

    def test_the_branch_that_batches_keeps_the_line_operators_grep_for(self):
        """`Lock more targets.` is the wording `describeMaxTargetsProbe` keeps
        deliberately, and a reading where three locks were asked for is still a
        reading where more targets were asked for."""
        answers = self.repl.strings([
            "describeLockBatchAsked []",
        ], definitions=self.repl.with_helpers([]))
        self.assertTrue(
            answers[0].startswith("Lock more targets."),
            "the batched lock site stopped saying 'Lock more targets.', so the "
            "line an operator has been grepping for since before any of this "
            "no longer appears on the readings it was about: %r" % answers[0])

    def test_the_shortfall_is_announced_at_the_root(self):
        """It is settled in `updateMemoryForNewReadingFromGame`, which runs
        whatever the bot is doing, so the branch that would otherwise say so is
        not reliably the branch being evaluated."""
        root = collapsed(top_level_block(
            source_of(SAXRAT_BOT_ELM), "anomalyBotDecisionRoot"))
        self.assertIn(
            "context.memory.lockBatchLastChange", root,
            "a batch that came up short is never printed, so the one thing "
            "that can report a dropped lock click says nothing")

    def test_the_status_line_prints_the_clause(self):
        status = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            "describeLockBatch (lockBatchStateFrom context)", status,
            "the status line no longer carries the batch clause, so the "
            "session totals that separate a dropped click from a dead rat are "
            "not visible on any reading")


class TheDecisionSiteIsWiredToTheRuleTest(unittest.TestCase):
    """The lines that could revert this while everything still compiled."""

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_the_batch_is_taken_from_the_rows_the_ship_can_reach(self):
        binding = collapsed(indented_block(
            anomaly_decision_source(), "overviewEntriesToLockInOneStep",
            indent="        "))
        self.assertIn("overviewEntriesToLockInRange |> List.take", binding,
                      "the batch is built from rows the ship may have to fly "
                      "at first, so an approach would be batched with locks")
        self.assertIn("lockBatchSize", binding,
                      "the batch size is no longer the rule's answer")
        self.assertIn("rowsLockableNow = overviewEntriesToLockInRange", binding,
                      "the rule is told about rows the ship cannot reach")

    def test_the_memory_update_folds_the_accounting_in(self):
        binding = collapsed(indented_block(
            self.source, "lockBatchAccounting", indent="        "))
        self.assertIn("updateLockBatchAccounting", binding)
        self.assertIn("botMemoryBefore.targetsCountLastReading", binding,
                      "the accounting is handed this reading's target count "
                      "rather than the previous reading's, so a batch is "
                      "judged against a bar it has already moved")

    def test_the_previous_reading_s_target_count_is_written_every_reading(self):
        """It is memory rather than a re-derivation, because the memory update
        only ever sees the reading after the clicks it is judging."""
        collapsed_source = collapsed(self.source)
        self.assertIn(
            ", targetsCountLastReading = context.readingFromGameClient.targets "
            "|> List.length", collapsed_source,
            "the previous reading's target bar is not recorded, so nothing can "
            "say what a batch was asked against")

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


class TheMissionRunnerTookThisOnWithItsDisciplineTest(unittest.TestCase):
    """Scope, recorded rather than remembered.

    This class used to be `TheMissionRunnerStillLocksOnePerStepTest`, which held
    a marker: the mission runner's `lockTargetFromOverviewEntry` had the same
    one-Ctrl+click-then-hand-the-step-back shape, it was deliberately untouched,
    and the case existed so that a later port had to *notice* it was taking on
    the attribution problem this change solves.

    **The port has happened and the marker is spent**, so what is recorded here
    is the thing the marker was watching for rather than the state it was
    watching. The mission runner now batches, and it carries the two rules that
    make batching safe -- so a port that takes the batch without the discipline
    still fails a case in the file that warned about it.

    Everything else about the mission runner's version is in
    `test_mission_runner_batched_lock_clicks.py`, which sizes its cap and its
    gain on that bot's own corpus rather than on this one's.
    """

    def test_it_batches_now(self):
        source = source_of(MISSION_RUNNER_BOT_ELM)
        single = collapsed(top_level_block(source, "lockTargetFromOverviewEntry"))
        self.assertIn(
            "lockChordForOverviewEntry", single,
            "the mission runner's single lock site no longer shares one chord "
            "with its batch, so the two can come to dispatch different gestures")
        self.assertIn(
            "lockBatchMaximumClicks", source,
            "the mission runner has lost its batch entirely; if that is "
            "deliberate this case is what has to be argued with")

    def test_it_did_not_take_the_batch_without_the_attribution_discipline(self):
        source = source_of(MISSION_RUNNER_BOT_ELM)
        rule = collapsed(top_level_block(source, "updateLockRangeLearning"))
        self.assertIn(
            "if stepWasBatched then", rule,
            "the mission runner batches lock clicks and its lock-range rule no "
            "longer refuses to learn from a batched reading, which is a range "
            "learned from an outcome that belongs to no one click")
        size = collapsed(top_level_block(source, "lockBatchSize"))
        self.assertIn(
            "situation.probeIsDue || (situation.targetsHeld < 1)", size,
            "the mission runner's batch no longer asks the first lock of an "
            "engagement alone, so the only lock that could have taught the "
            "refusal bound is issued in a step the range rule will not read")


class TheRecordedRunsShowTheRampThisChangeIsAboutTest(unittest.TestCase):
    """The premise, recounted from the corpus as a relation.

    Stated as relations rather than as the counts in the doc comment, so a
    corpus that grows cannot turn a true claim red: the bot dispatched many lock
    commands, and consecutive ones are mostly a reading or two apart -- which is
    one lock per decision cycle, not a client that was slow to answer.
    """

    STEP = re.compile(r"^# \[(\d+)\.(\d+)\] ")
    LOCK = re.compile(r"Lock target from overview entry")
    SEND = re.compile(r"^#   task send-effects-\d+: WindowsInputRequest")

    @classmethod
    def setUpClass(cls):
        paths = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
                 for number in range(1, 17)]
        paths = [path for path in paths if os.path.exists(path)]
        if not paths:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "can say about the lock ramp cannot be consulted here")

        cls.gaps = []
        cls.dispatches = 0
        for path in paths:
            reading = None
            pending = False
            previous = None
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
                            cls.gaps.append(reading - previous)
                        previous = reading
                        pending = False

    def test_locks_were_dispatched_one_reading_at_a_time(self):
        self.assertGreater(
            self.dispatches, 100,
            "the recorded runs carry almost no lock commands, so they cannot "
            "say anything about the ramp this change is about")
        close = [gap for gap in self.gaps if 0 < gap <= 2]
        self.assertGreater(
            len(close), len(self.gaps) // 10,
            "consecutive lock commands are never a reading or two apart in the "
            "recorded runs, which is not the one-lock-per-decision-cycle ramp "
            "this change was built for")
        self.assertEqual(
            [gap for gap in self.gaps if gap < 0], [],
            "the reading numbers do not increase, so the gap measurement is "
            "not measuring what it claims to")


if __name__ == "__main__":
    unittest.main()
