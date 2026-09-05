"""Issue #163: the host has no idea a posted event is costing a multiple of
what it should, and it is the same layer #75's mangled query turned out to
live in -- below `effectsToEnterString`, below the key table, below
`cg_input`, in whatever `CGEventPost` is landing in. #160 established how to
see it after the fact, from a glide's own duration: ten posted `move`
commands and nine known, fixed sleeps, so subtracting the sleeps and dividing
by the count gives what one posted event cost. Runs 17 and 19 read
53-100ms a posted event there against under 18ms everywhere else in the
eight runs #160 checked, on the same shipped pacing -- and that gap is what
told the two runs apart from every healthy one, not the query itself.

This is that same derivation wired into the host so it says so on every step
that posts a glide, rather than needing an investigation to reconstruct it
from a log afterwards. It **reports and decides nothing** -- the same posture
as #123's quick message and #139's retreat latency: name the number, and let
whatever comes next supply the vocabulary for a rule, if one is ever built.
No retreat, no give-up, no behaviour change; `TheReportDecidesNothingTest`
below is what pins that.

**The corpus has grown since #160 and the two-run framing does not hold
any more.** Recomputed here from every `move: glided ... in Xs` line under
`~/eve-bot-logs` (79 recorded runs at the time of writing, not the ~19 #160
had), the *gap* the derivation draws is still completely clean -- no run's
worst glide falls between roughly 18ms and roughly 70ms a posted event -- but
the population on the slow side of it is no longer two runs. It is a large
and growing share of the corpus, concentrated in two long, otherwise
unremarkable stretches of wall-clock time that include the days immediately
before this was written. `TheCorpusStillDrawsACleanGapTest` asserts the gap;
it deliberately does not assert a count of how many runs sit on which side,
because that count is exactly the kind of thing a growing corpus must not be
allowed to turn red.
"""
import glob
import inspect
import io
import os
import re
import sys
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
sys.path.insert(0, MACOS_HOST_DIR)

import botlab_host  # noqa: E402
import web_console  # noqa: E402
from prerequisites import recorded_runs  # noqa: E402

EVE_BOT_LOGS = os.path.join(os.path.expanduser("~"), "eve-bot-logs")

GLIDE_LINE = re.compile(r"^#\s+move: .*\bin (\d+\.\d+)s\s*$", re.M)


def glide_durations(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return [float(value) for value in GLIDE_LINE.findall(handle.read())]


def worst_per_event_cost(path):
    """This run's own worst (most expensive) posted event, in ms, or None."""
    durations = glide_durations(path)
    if not durations:
        return None
    return max(botlab_host.glide_per_event_cost_ms(d) for d in durations)


def new_dispatcher():
    """A `TaskDispatcher` with only the state `_glide_to` and
    `_report_input_cost` touch -- see `test_typed_text_key_sequence.dispatch`
    for the fuller harness this borrows the shape of.
    """
    dispatcher = botlab_host.TaskDispatcher.__new__(botlab_host.TaskDispatcher)
    dispatcher._glide_costs_this_step = []
    dispatcher._last_mouse_pos = None
    return dispatcher


def captured_stderr(action):
    noise = io.StringIO()
    saved, sys.stderr = sys.stderr, noise
    try:
        action()
    finally:
        sys.stderr = saved
    return noise.getvalue()


class GlidePerEventCostMsTest(unittest.TestCase):
    """The pure arithmetic #160's investigation used, now a function."""

    def test_backs_out_the_known_sleep_and_divides_by_the_count(self):
        # 10 posted events, 9 sleeps of 25ms = 0.225s known. A measured
        # duration of 0.725s therefore has 0.5s left over the posting itself,
        # 50ms an event.
        self.assertAlmostEqual(
            botlab_host.glide_per_event_cost_ms(0.725, steps=10, step_delay=0.025),
            50.0, places=6)

    def test_the_measured_duration_by_itself_is_not_the_answer(self):
        """The whole point of subtracting the sleep -- without it every glide
        reads as costing well over 100ms, which is not what any recorded run
        shows."""
        without_subtraction = 0.725 / 10 * 1000.0
        self.assertNotAlmostEqual(
            botlab_host.glide_per_event_cost_ms(0.725, steps=10, step_delay=0.025),
            without_subtraction, places=3)

    def test_exactly_the_known_sleep_is_zero_cost(self):
        self.assertAlmostEqual(
            botlab_host.glide_per_event_cost_ms(0.225, steps=10, step_delay=0.025),
            0.0, places=6)

    def test_shipped_defaults_match_the_glide_they_describe(self):
        """`_move_mouse_eased`'s own `steps`/`step_delay` defaults are the
        shape this derivation assumes. Read from the live signature rather
        than restated, so retuning the glide without updating this constant
        is a case that fails here rather than a report that quietly starts
        answering a number for a different gesture.
        """
        import inspect
        sig = inspect.signature(botlab_host.TaskDispatcher._move_mouse_eased)
        self.assertEqual(sig.parameters["steps"].default, botlab_host.GLIDE_STEPS)
        self.assertEqual(sig.parameters["step_delay"].default,
                          botlab_host.GLIDE_STEP_DELAY_SECONDS)


class DescribeInputCostTest(unittest.TestCase):
    """What the report says, for each of the three answers it can give."""

    def test_absent_does_not_read_as_healthy(self):
        text = botlab_host.describe_input_cost(None)
        self.assertIn("no glide posted this step", text)
        self.assertNotIn("ms", text, "an absent reading must carry no number")

    def test_under_the_threshold_is_the_ordinary_reading(self):
        text = botlab_host.describe_input_cost(5.0, threshold_ms=30.0)
        self.assertIn("5.0ms", text)
        self.assertNotIn("HIGH", text)

    def test_at_the_threshold_is_saturated(self):
        """`>=`, not `>` -- the threshold is the first value the report
        treats as saturated, not the last one it lets through."""
        text = botlab_host.describe_input_cost(30.0, threshold_ms=30.0)
        self.assertIn("INPUT COST HIGH", text)

    def test_just_under_the_threshold_is_not_saturated(self):
        text = botlab_host.describe_input_cost(29.9, threshold_ms=30.0)
        self.assertNotIn("HIGH", text)

    def test_the_report_names_the_issue_and_takes_no_action(self):
        text = botlab_host.describe_input_cost(100.0, threshold_ms=30.0)
        self.assertIn("#163", text)
        self.assertIn("Report only", text)


class GlideToRecordsWhatItPostedTest(unittest.TestCase):
    """`_glide_to` is the one call site #163's arithmetic can trust: every
    invocation posts exactly `steps` events with exactly `(steps - 1)`
    sleeps of `step_delay` between them, whichever of `_move_mouse_eased`'s
    two branches reached it."""

    def test_records_the_derived_cost_for_this_glide(self):
        dispatcher = new_dispatcher()
        dispatcher._cg_move = lambda x, y: None
        clock = iter([100.0, 100.325])  # 0.325s elapsed
        real_monotonic, real_sleep = time.monotonic, time.sleep
        time.monotonic = lambda: next(clock)
        time.sleep = lambda seconds: None
        try:
            dispatcher._glide_to(0.0, 0.0, 50.0, 50.0, steps=10, step_delay=0.025)
        finally:
            time.monotonic, time.sleep = real_monotonic, real_sleep
        # 0.325s - 0.225s known sleep = 0.1s over 10 events = 10ms each.
        self.assertEqual(len(dispatcher._glide_costs_this_step), 1)
        self.assertAlmostEqual(dispatcher._glide_costs_this_step[0], 10.0, places=3)

    def test_a_second_glide_in_the_same_step_appends_rather_than_replaces(self):
        dispatcher = new_dispatcher()
        dispatcher._cg_move = lambda x, y: None
        clock = iter([0.0, 0.325, 10.0, 10.725])
        real_monotonic, real_sleep = time.monotonic, time.sleep
        time.monotonic = lambda: next(clock)
        time.sleep = lambda seconds: None
        try:
            dispatcher._glide_to(0.0, 0.0, 50.0, 50.0, steps=10, step_delay=0.025)
            dispatcher._glide_to(50.0, 50.0, 0.0, 0.0, steps=10, step_delay=0.025)
        finally:
            time.monotonic, time.sleep = real_monotonic, real_sleep
        self.assertEqual(len(dispatcher._glide_costs_this_step), 2)


class ReportInputCostTest(unittest.TestCase):
    """The per-step report: worst reading wins, and it resets what it read."""

    def test_reports_the_worst_of_several_glides(self):
        dispatcher = new_dispatcher()
        dispatcher._glide_costs_this_step = [5.0, 40.0, 12.0]
        output = captured_stderr(dispatcher._report_input_cost)
        self.assertIn("40.0ms", output)
        self.assertIn("INPUT COST HIGH", output)

    def test_a_cheaper_glide_does_not_hide_behind_a_healthy_one(self):
        """If the cheapest glide in a mixed step won instead, a step that
        posted one saturated glide and one lucky one would report healthy."""
        dispatcher = new_dispatcher()
        dispatcher._glide_costs_this_step = [2.0, 90.0]
        output = captured_stderr(dispatcher._report_input_cost)
        self.assertIn("90.0ms", output)
        self.assertNotIn("2.0ms", output)

    def test_a_quiet_step_says_nothing_was_posted(self):
        dispatcher = new_dispatcher()
        dispatcher._glide_costs_this_step = []
        output = captured_stderr(dispatcher._report_input_cost)
        self.assertIn("no glide posted this step", output)

    def test_the_reading_is_reset_after_it_is_reported(self):
        dispatcher = new_dispatcher()
        dispatcher._glide_costs_this_step = [5.0]
        captured_stderr(dispatcher._report_input_cost)
        self.assertEqual(dispatcher._glide_costs_this_step, [])


class TheReportDecidesNothingTest(unittest.TestCase):
    """#163's own posture, checked rather than trusted: the same one #123's
    quick message and #139's retreat latency were built on. `_windows_input`
    is where this report is produced, and it must not be one of the things
    `_windows_input`'s own control flow (aborts, `completedStepsCount`,
    `errorMessages`) reads back."""

    def test_report_input_cost_is_called_for_its_print_and_nothing_else(self):
        import inspect
        body = inspect.getsource(botlab_host.TaskDispatcher._windows_input)
        self.assertIn("self._report_input_cost()", body)
        # The call sits after every branch that can add to `errors` or change
        # `completed`, and the value it computes is not assigned to a name --
        # if it were, that name would be free to leak into the response this
        # method returns.
        after_call = body.split("self._report_input_cost()", 1)[1]
        self.assertNotIn("worst", after_call)


class WiredThroughWindowsInputTest(unittest.TestCase):
    """`_windows_input` itself, exercised for real -- reused from
    `test_typed_text_key_sequence`'s harness rather than a second one, since
    what is being checked here is genuinely the same dispatcher."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, HERE)
        import test_typed_text_key_sequence as glide_harness
        cls.harness = glide_harness

    def test_a_step_that_moves_the_mouse_reports_something(self):
        items = [{"MouseMoveAbsolute": [128, 89]}]
        _, _, _, log = self.harness.dispatch(items)
        # The harness's own `time.sleep` stub means the arithmetic answers a
        # meaningless (very negative) number here -- the wiring, not the
        # value, is what this checks; the value is
        # `GlideToRecordsWhatItPostedTest`'s job.
        self.assertIn("input cost:", log)

    def test_a_step_with_no_move_at_all_reports_absence(self):
        items = [{"KeyDown": [0x41, False]}, {"KeyUp": [0x41, False]}]
        _, _, _, log = self.harness.dispatch(items)
        self.assertIn("no glide posted this step", log)

    def test_a_stale_reading_left_over_from_before_this_call_is_not_reported(self):
        """`_windows_input` resets its own reading at the top rather than
        trusting that the previous call's report already cleared it -- a
        dispatcher handed a step that posts nothing must not report whatever
        glide cost happens to still be sitting in `_glide_costs_this_step`
        from earlier, however that got there.
        """
        dispatcher = botlab_host.TaskDispatcher.__new__(botlab_host.TaskDispatcher)
        dispatcher.execute_input = True
        dispatcher._buttons_down = set()
        dispatcher._keys_down = []
        dispatcher._scale_x = 1.0
        dispatcher._scale_y = 1.0
        dispatcher._last_mouse_pos = (0.0, 0.0)
        dispatcher._last_input_post_at = 0.0
        # A stale reading, as if some earlier step had left one behind.
        dispatcher._glide_costs_this_step = [999.0]
        dispatcher.volatile = types.SimpleNamespace(game_pid=1234)
        dispatcher._cg = lambda command: "ok"
        dispatcher._cg_move = lambda x, y: None
        dispatcher._seconds_since_human_input = lambda: 100.0

        saved = (botlab_host.bring_window_to_foreground,
                 botlab_host._window_is_onscreen)
        botlab_host.bring_window_to_foreground = lambda pid, window: True
        botlab_host._window_is_onscreen = lambda window: True
        log = captured_stderr(
            lambda: dispatcher._windows_input(
                [{"KeyDown": [0x41, False]}, {"KeyUp": [0x41, False]}]))
        (botlab_host.bring_window_to_foreground,
         botlab_host._window_is_onscreen) = saved

        self.assertIn("no glide posted this step", log)
        self.assertNotIn("999.0ms", log)


class TheCorpusStillDrawsACleanGapTest(unittest.TestCase):
    """Recomputed from `~/eve-bot-logs` rather than trusted from #160's own
    write-up, which was against a smaller corpus. See this file's module
    docstring for what changed and what did not.
    """

    def setUp(self):
        if not os.path.isdir(EVE_BOT_LOGS):
            # Matches check_expected_skips.py's EXPECTED entry for
            # "the recorded runs in ~/eve-bot-logs" -- reworded to that
            # entry rather than adding a near-duplicate one.
            self.skipTest("no recorded runs in ~/eve-bot-logs, so a claim "
                           "about the corpus as a whole cannot be made here")

    def per_run_worst_costs(self):
        worst = {}
        for path in glob.glob(os.path.join(EVE_BOT_LOGS, "*.log")):
            cost = worst_per_event_cost(path)
            if cost is not None:
                worst[os.path.basename(path)] = cost
        return worst

    def test_named_healthy_and_saturated_runs_bracket_the_threshold(self):
        """The two runs #75 was filed on, and the eight #160 checked against
        them -- kept as the fixed control, so a threshold placed wrong fails
        here independently of anything the corpus has grown into since.

        Uses `prerequisites.recorded_runs`, the shared corpus gate, rather
        than a hand-rolled one -- its skip reason is already the one
        `check_expected_skips.py` recognises.
        """
        saturated_pairs = recorded_runs("17", "19")
        healthy_pairs = recorded_runs("27", "29", "30", "31", "34", "35",
                                       "36", "37")
        saturated = [worst_per_event_cost(path) for _, path in saturated_pairs]
        healthy = [worst_per_event_cost(path) for _, path in healthy_pairs]
        saturated = [c for c in saturated if c is not None]
        healthy = [c for c in healthy if c is not None]
        if not saturated or not healthy:
            self.skipTest("no recorded runs in ~/eve-bot-logs, so a claim "
                           "about the corpus as a whole cannot be made here")
        for cost in healthy:
            self.assertLess(cost, botlab_host.INPUT_COST_SATURATED_MS,
                             "a run #160 called healthy must read under the mark")
        for cost in saturated:
            self.assertGreaterEqual(cost, botlab_host.INPUT_COST_SATURATED_MS,
                                     "a run #75 was filed on must read at or "
                                     "above the mark")

    def test_the_whole_corpus_separates_with_a_wide_margin(self):
        """Every run this machine has, not only the named ones -- the claim
        this file's docstring makes: the gap is still clean, even though the
        population on the slow side is no longer two runs.
        """
        worst = self.per_run_worst_costs()
        if len(worst) < 10:
            self.skipTest("no recorded runs in ~/eve-bot-logs, so a claim "
                           "about the corpus as a whole cannot be made here")
        threshold = botlab_host.INPUT_COST_SATURATED_MS
        below = [c for c in worst.values() if c < threshold]
        at_or_above = [c for c in worst.values() if c >= threshold]
        self.assertTrue(below, "no run reads healthy -- the corpus changed shape")
        self.assertTrue(at_or_above,
                         "no run reads saturated any more -- the corpus changed "
                         "shape, and #163's premise should be revisited rather "
                         "than assumed")
        # A wide margin, not merely opposite sides of the constant: the point
        # is that 30ms sits in a real gap the data draws, not that it is the
        # number used to draw the boundary in the first place.
        self.assertGreater(min(at_or_above) - max(below), 40.0,
                            "the two clusters have closed in on the threshold; "
                            "the corpus may no longer support this mark")

    def test_the_saturated_side_is_no_longer_only_the_two_named_runs(self):
        """The honest finding this PR is built on: recomputed today, the
        slow cluster is a large share of the corpus, concentrated in two
        stretches of wall-clock time that include the days immediately
        before this was written -- not an anomaly confined to runs 17 and 19.
        """
        worst = self.per_run_worst_costs()
        threshold = botlab_host.INPUT_COST_SATURATED_MS
        saturated_other_than_the_named_two = [
            name for name, cost in worst.items()
            if cost >= threshold and name not in
            ("mission_run17.log", "mission_run19.log")
        ]
        self.assertTrue(
            saturated_other_than_the_named_two,
            "if this ever goes empty, the finding that motivated placing the "
            "threshold where it is has reverted and the doc comment above "
            "INPUT_COST_SATURATED_MS needs rewriting, not silencing")


def host_lines(state):
    """The console's own lines, which is where a slow event is announced --
    reused from `test_console_names_the_character.host_lines`'s shape rather
    than a second helper."""
    return [line["text"] for line in state.snapshot()["lines"]
            if line["kind"] == "host"]


class ConsoleNoteInputCostTest(unittest.TestCase):
    """`web_console.ConsoleState.note_input_cost` -- a real `ConsoleState`,
    told a cost the way the dispatcher tells it."""

    def setUp(self):
        self.state = web_console.ConsoleState()

    def test_a_console_nobody_has_told_reports_nothing_measured(self):
        snapshot = self.state.snapshot()
        self.assertIsNone(snapshot["lastInputCostMs"])
        self.assertEqual(snapshot["slowInputEvents"], 0)

    def test_an_absent_cost_does_not_move_the_last_reading(self):
        # A step that posted no glide answers `None`, and that must not be
        # read as healthy -- see `describe_input_cost`'s own reasoning.
        self.state.note_input_cost(5.0, threshold_ms=30.0)
        self.state.note_input_cost(None, threshold_ms=30.0)
        self.assertEqual(self.state.snapshot()["lastInputCostMs"], 5.0)
        self.assertEqual(self.state.snapshot()["slowInputEvents"], 0)

    def test_a_healthy_cost_updates_the_reading_and_counts_nothing(self):
        self.state.note_input_cost(12.0, threshold_ms=30.0)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["lastInputCostMs"], 12.0)
        self.assertEqual(snapshot["slowInputEvents"], 0)
        self.assertEqual(host_lines(self.state), [])

    def test_a_saturated_cost_counts_and_says_so(self):
        self.state.note_input_cost(85.0, threshold_ms=30.0)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["lastInputCostMs"], 85.0)
        self.assertEqual(snapshot["slowInputEvents"], 1)
        self.assertEqual(len(host_lines(self.state)), 1)
        self.assertIn("INPUT COST HIGH", host_lines(self.state)[0])
        self.assertIn("#163", host_lines(self.state)[0])

    def test_at_the_threshold_counts_as_saturated(self):
        """`>=`, matching `describe_input_cost`'s own boundary."""
        self.state.note_input_cost(30.0, threshold_ms=30.0)
        self.assertEqual(self.state.snapshot()["slowInputEvents"], 1)

    def test_every_saturated_event_is_counted_not_only_the_first(self):
        for _ in range(3):
            self.state.note_input_cost(85.0, threshold_ms=30.0)
        self.assertEqual(self.state.snapshot()["slowInputEvents"], 3)

    def test_it_decides_nothing(self):
        """Same posture as #123's quick message: `note_input_cost` sets a
        field and, past the threshold, appends a log line -- nothing here
        compares `slow_input_events` against anything, and nothing pauses,
        stops or retreats on its strength."""
        body = inspect.getsource(web_console.ConsoleState.note_input_cost)
        self.assertNotIn("slow_input_events >", body)
        self.assertNotIn("pending_commands", body)
        self.assertNotIn("paused", body)


class ReportInputCostTellsTheConsoleTest(unittest.TestCase):
    """The wiring from `_report_input_cost` to a real `ConsoleState` --
    exercised end to end rather than with a stub, so what is checked is the
    same object `/api/state` would serve."""

    def dispatcher_with_console(self):
        dispatcher = botlab_host.TaskDispatcher.__new__(botlab_host.TaskDispatcher)
        dispatcher._glide_costs_this_step = []
        dispatcher._console = web_console.ConsoleState()
        return dispatcher

    def test_a_saturated_reading_reaches_the_console(self):
        dispatcher = self.dispatcher_with_console()
        dispatcher._glide_costs_this_step = [85.0]
        captured_stderr(dispatcher._report_input_cost)
        snapshot = dispatcher._console.snapshot()
        self.assertEqual(snapshot["lastInputCostMs"], 85.0)
        self.assertEqual(snapshot["slowInputEvents"], 1)

    def test_a_healthy_reading_reaches_the_console_without_counting(self):
        dispatcher = self.dispatcher_with_console()
        dispatcher._glide_costs_this_step = [5.0]
        captured_stderr(dispatcher._report_input_cost)
        snapshot = dispatcher._console.snapshot()
        self.assertEqual(snapshot["lastInputCostMs"], 5.0)
        self.assertEqual(snapshot["slowInputEvents"], 0)

    def test_a_quiet_step_does_not_disturb_the_console(self):
        dispatcher = self.dispatcher_with_console()
        dispatcher._console.note_input_cost(12.0, threshold_ms=30.0)
        dispatcher._glide_costs_this_step = []
        captured_stderr(dispatcher._report_input_cost)
        # A step that posted nothing must not overwrite the last real
        # reading with silence.
        self.assertEqual(dispatcher._console.snapshot()["lastInputCostMs"], 12.0)

    def test_a_dispatcher_with_no_console_still_reports_to_stderr(self):
        """The overwhelming majority of existing dispatchers -- every raw
        `TaskDispatcher.__new__` in this suite included -- never set
        `_console` at all, since `__init__` is what would. The report must
        stay reachable without it."""
        dispatcher = new_dispatcher()
        dispatcher._glide_costs_this_step = [5.0]
        output = captured_stderr(dispatcher._report_input_cost)
        self.assertIn("input cost:", output)


class RunBotHandsTheDispatcherItsConsoleTest(unittest.TestCase):
    """The wiring that cannot be executed from here without a running bot
    process -- read out of `run_bot`'s own source instead."""

    def test_run_bot_passes_its_console_to_the_dispatcher(self):
        body = inspect.getsource(botlab_host.run_bot)
        constructor = body[body.index("TaskDispatcher("):]
        constructor = constructor[:constructor.index(")") + 1]
        self.assertIn("console=console", constructor)


if __name__ == "__main__":
    unittest.main()
