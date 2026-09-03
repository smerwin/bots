"""Tests for the console's live report of how long the current tick has run.

Issue #312. `run_bot` dequeues console commands once per outer-loop iteration,
and #321 already narrowed the window that mattered most -- pause and stop are
now also drained inside the per-task loop (`while pending`), and a tick that
holds the loop past `MAX_TICK_SECONDS` (300s) is given back on its own. Both of
those *fix* the underlying stall; neither *reports* it while it is happening,
and #321's own give-back note only ever prints once the bound has already been
crossed.

That still leaves a gap #321 cannot close by construction: a single task whose
own call blocks -- `slicer_run1_2026-08-19.log` tick 482 spent 2,674 seconds on
three substeps, an average of 890s each -- holds the very thread that would
have to notice anything at all. Nothing in `run_bot`'s loop can report during a
call it has not returned from.

**The fix is a clock the HTTP handler thread reads for itself.**
`ConsoleState.note_tick_started` stamps a wall-clock timestamp once per tick,
from the loop, and `snapshot()` computes elapsed time against it fresh on every
poll -- on the handler thread, which is never the thread a single slow task
could have stuck. So `/api/state` answers "how long has this been running" even
while `run_bot`'s own thread has not executed a line of Python in minutes.

Two thresholds, both pure and both asked directly through
`web_console.tick_progress_state` rather than by driving a console and a
wedged bot process to reach them: `notablyLong` is worth a look and sits above
the busiest *normal* band `botlab_host.MAX_TICK_SECONDS`'s own comment already
measured (95% of 11-20-substep ticks finish under 18s); `wedged` is kept equal
to that same `MAX_TICK_SECONDS`, so a value the console still sees climbing
past it is the tell that one task, not the whole tick, is what is stuck.

What cannot be executed from here -- that the loop stamps the clock once a
tick and throttles its own log line to one print per tick rather than one a
substep -- is pinned as source, the same shape `test_the_tick_is_bounded.py`
already uses for the neighbouring bound.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import io
import os
import re
import sys
import tokenize
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
sys.path.insert(0, MACOS_HOST_DIR)

import botlab_host  # noqa: E402
import web_console  # noqa: E402

HOST_SOURCE = os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py")


def collapse(path):
    with open(path) as f:
        return re.sub(r"\s+", " ", f.read())


def code_only(path):
    """The source with its comments removed, whitespace-collapsed.

    `test_the_tick_is_bounded.py`'s own helper, copied rather than shared --
    every file in this suite carries its own small text readers, and a case
    asking "does this region call X" has to read code and not the comment
    that names X while explaining why the region does *not* call it.
    """
    with open(path) as f:
        source = f.read()
    cut_at = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            row, col = token.start
            cut_at[row] = min(cut_at.get(row, col), col)
    kept = [line[:cut_at[n]] if n in cut_at else line
            for n, line in enumerate(source.splitlines(), 1)]
    return re.sub(r"\s+", " ", "\n".join(kept))


class TheThresholdsSitInARealGapTest(unittest.TestCase):
    def test_notably_long_is_well_below_wedged(self):
        self.assertLess(web_console.TICK_NOTABLY_LONG_SECONDS,
                        web_console.TICK_WEDGED_SECONDS)

    def test_notably_long_clears_the_busiest_normal_band(self):
        # botlab_host.MAX_TICK_SECONDS's own comment: the 11-20-substep band's
        # 95th percentile blocks under 18s.
        self.assertGreater(web_console.TICK_NOTABLY_LONG_SECONDS, 18.0)

    def test_the_console_agrees_with_the_hosts_own_bound(self):
        """Pinned equal rather than imported -- botlab_host imports this
        module, so the reverse would cycle. A retune of one that leaves the
        other behind is what this catches."""
        self.assertEqual(web_console.TICK_WEDGED_SECONDS,
                         botlab_host.MAX_TICK_SECONDS)


class TheRuleAnswersTheClockTest(unittest.TestCase):
    def test_a_fresh_tick_is_neither(self):
        state = web_console.tick_progress_state(0.0)
        self.assertFalse(state["notablyLong"])
        self.assertFalse(state["wedged"])

    def test_at_the_notably_long_bound_it_is_not_yet_notable(self):
        # The bound is what is allowed, not the first thing flagged --
        # `tick_bound_note`'s own convention.
        state = web_console.tick_progress_state(web_console.TICK_NOTABLY_LONG_SECONDS)
        self.assertFalse(state["notablyLong"])

    def test_just_past_the_notably_long_bound_it_is(self):
        state = web_console.tick_progress_state(
            web_console.TICK_NOTABLY_LONG_SECONDS + 0.1)
        self.assertTrue(state["notablyLong"])
        self.assertFalse(state["wedged"])

    def test_at_the_wedged_bound_it_is_not_yet_wedged(self):
        state = web_console.tick_progress_state(web_console.TICK_WEDGED_SECONDS)
        self.assertFalse(state["wedged"])

    def test_just_past_the_wedged_bound_both_are_true(self):
        # Wedged implies notably long -- there is no state past the second
        # threshold that reads as merely "a look worth taking".
        state = web_console.tick_progress_state(
            web_console.TICK_WEDGED_SECONDS + 0.1)
        self.assertTrue(state["notablyLong"])
        self.assertTrue(state["wedged"])

    def test_a_single_stuck_task_still_reads_as_wedged(self):
        # slicer_run1_2026-08-19.log tick 482: 2,674s on three substeps.
        state = web_console.tick_progress_state(2674.0)
        self.assertTrue(state["wedged"])

    def test_the_elapsed_seconds_are_carried_raw(self):
        self.assertAlmostEqual(
            web_console.tick_progress_state(12.34)["elapsedSeconds"], 12.3)


class TheConsoleStateComputesItLiveTest(unittest.TestCase):
    """A real `ConsoleState`, told the tick started the way the loop tells it."""

    def setUp(self):
        self.state = web_console.ConsoleState()

    def test_a_console_nobody_has_told_reads_as_freshly_started(self):
        # Construction itself stamps the clock, so a poll before the first
        # tick answers a small number rather than a field the page has to
        # guard against being absent.
        snapshot = self.state.snapshot()
        self.assertLess(snapshot["tickElapsedSeconds"], 5.0)
        self.assertFalse(snapshot["tickNotablyLong"])
        self.assertFalse(snapshot["tickWedged"])

    def test_note_tick_started_resets_the_clock(self):
        # White-box: back-date the stamp the way a long-running tick would
        # leave it, then confirm a fresh call brings it back to now rather
        # than requiring a real sleep to prove the same thing.
        self.state.tick_started_at -= 500.0
        self.assertTrue(self.state.snapshot()["tickWedged"])
        self.state.note_tick_started()
        self.assertFalse(self.state.snapshot()["tickWedged"])
        self.assertLess(self.state.snapshot()["tickElapsedSeconds"], 5.0)

    def test_a_tick_that_has_run_long_reads_wedged_on_the_snapshot(self):
        self.state.tick_started_at -= (web_console.TICK_WEDGED_SECONDS + 1.0)
        snapshot = self.state.snapshot()
        self.assertTrue(snapshot["tickNotablyLong"])
        self.assertTrue(snapshot["tickWedged"])
        self.assertGreater(snapshot["tickElapsedSeconds"],
                           web_console.TICK_WEDGED_SECONDS)

    def test_the_identity_the_console_already_had_is_untouched(self):
        state = web_console.ConsoleState(app_name="eve-online-saxrat")
        state.note_tick_started()
        snapshot = state.snapshot()
        self.assertEqual(snapshot["appName"], "eve-online-saxrat")
        self.assertIn("tickElapsedSeconds", snapshot)


class TheLoopStampsAndThrottlesItTest(unittest.TestCase):
    """Pinned as source: reaching this live needs a bot process and a wedge."""

    def setUp(self):
        self.source = collapse(HOST_SOURCE)
        code = code_only(HOST_SOURCE)
        self.tick_top = code[code.index('cont = response["ContinueSession"]'):]
        self.tick_top = self.tick_top[:self.tick_top.index('pending = list(')]
        self.loop = code[code.index('pending = list(cont["startTasks"])'):]
        self.loop = self.loop[:self.loop.index('if "FinishSession" in response: continue')]

    def test_the_clock_is_stamped_once_at_the_top_of_the_tick(self):
        self.assertIn("console.note_tick_started()", self.tick_top)

    def test_the_clock_is_not_restamped_inside_the_task_loop(self):
        # Restamping on every substep would make elapsed time measure the age
        # of the *last substep* rather than of the tick -- exactly what a
        # wedge has to be measured against.
        self.assertNotIn("note_tick_started", self.loop)

    def test_the_throttle_flag_starts_false_each_tick(self):
        self.assertIn("tick_notably_long_reported = False", self.tick_top)

    def test_the_print_is_guarded_by_the_flag(self):
        self.assertIn("if (not tick_notably_long_reported", self.loop)
        self.assertIn("tick_notably_long_reported = True", self.loop)

    def test_the_log_line_uses_the_consoles_own_threshold(self):
        # Not a second, hand-picked number here -- the same one `/api/state`
        # answers with, so the log and the page cannot disagree about what
        # "notably long" means.
        self.assertIn("web_console.TICK_NOTABLY_LONG_SECONDS", self.loop)

    def test_it_is_also_pushed_to_the_consoles_own_log(self):
        # `self.source` is whitespace-collapsed, so the check is on the
        # tokens rather than on the original line breaks or indentation.
        self.assertIn('f"tick {tick} has been running {elapsed_this_tick:.0f}s, "',
                      self.source)
        self.assertIn('f"longer than usual")', self.source)


if __name__ == "__main__":
    unittest.main()
