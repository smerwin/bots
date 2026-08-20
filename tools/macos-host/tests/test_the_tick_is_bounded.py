"""Tests for the bound on how long one tick may hold the task loop.

Issue #321. `run_bot`'s `while pending` loop refills itself -- every
`TaskCompletedEvent` yields a `ContinueSession`, and any task in it with an
unseen id is appended -- so a bot that asks for a fresh read every cycle hands
back a new id every iteration and the queue never empties. The host is not
malfunctioning there; it is faithfully serving a bot that never stops asking.

**Everything that protects a run is downstream of that loop.** `tick += 1`, the
`max_ticks` check, the console drain and the session deadline are all reached
only once it returns. The deadline calls itself "a lease renewed every tick, so
a bot that stops asking -- or that hangs, or crashes -- is stopped on the next
one", and a tick that does not end is a run where there is no next one.
`saxrat_run1_2026-08-20.log` tick 1796 ran 6,720 substeps over 6,827 seconds --
one hour fifty-four -- and the session killed nothing.

**The unit is seconds, not substeps, and that is the finding.** A substep cap
of 50 still misses two of the 39 blocks longer than ten minutes in the corpus,
and the worst thing every cap misses is `martha_run1_2026-08-20.log` tick 640:
3,140 seconds on 45 substeps. A few tasks that each take forever hold the loop
as hard as thousands of fast ones, and only the clock sees both.

The cases here are executed against `tick_bound_note`, which is a declaration
of its own precisely so they can ask the rule rather than drive a whole event
loop and a `node` subprocess to reach it. What cannot be executed from here --
that the loop consults the rule, and that pause and stop are drained inside it
-- is pinned as source, and said to be pinned as source.

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

HOST_SOURCE = os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py")

# The longest tick in the corpus whose status header moved at all and that is
# not already known to be pathological, and the next one above it. The bound
# has to sit between them.
LONGEST_MOVING_TICK_SECONDS = 180.9
NEXT_TICK_ABOVE_IT_SECONDS = 414.1


def collapse(path):
    with open(path) as f:
        return re.sub(r"\s+", " ", f.read())


def code_only(path):
    """The source with its comments removed, whitespace-collapsed.

    A case asking "does this region call X" has to read code and not prose,
    because the comment explaining why the region *does not* call X names X --
    which is exactly what the change here does about `BotSettingsChangedEvent`.
    #314's own test plan strips comments first for the same reason.
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


class TheBoundIsWhereTheCorpusPutItTest(unittest.TestCase):
    def test_the_bound_clears_every_tick_that_was_getting_somewhere(self):
        self.assertGreater(botlab_host.MAX_TICK_SECONDS,
                           LONGEST_MOVING_TICK_SECONDS)

    def test_the_bound_is_below_the_next_tick_up(self):
        # Otherwise it is not in the gap, and starts cutting ticks the corpus
        # cannot distinguish from work.
        self.assertLess(botlab_host.MAX_TICK_SECONDS,
                        NEXT_TICK_ABOVE_IT_SECONDS)

    def test_a_normal_tick_is_nowhere_near_it(self):
        # 99% of the corpus runs 20 substeps or fewer, and that band's 95th
        # percentile blocks for under 18 seconds.
        self.assertIsNone(botlab_host.tick_bound_note(7, 18.0, 20, 1))


class TheRuleAnswersTheClockTest(unittest.TestCase):
    def test_a_tick_under_the_bound_says_nothing(self):
        self.assertIsNone(botlab_host.tick_bound_note(1, 1.0, 3, 0))

    def test_a_tick_exactly_at_the_bound_says_nothing(self):
        # The bound is what is allowed, not the first thing refused.
        self.assertIsNone(
            botlab_host.tick_bound_note(1, botlab_host.MAX_TICK_SECONDS, 3, 0))

    def test_a_tick_past_the_bound_says_so(self):
        note = botlab_host.tick_bound_note(
            1, botlab_host.MAX_TICK_SECONDS + 0.1, 3, 0)
        self.assertIsNotNone(note)

    def test_it_is_the_clock_and_not_the_substeps_that_decides(self):
        """The whole reason the unit is seconds.

        `martha_run1` tick 640 blocked 3,140 seconds on 45 substeps: every
        substep cap proposed for this would have let it run.
        """
        self.assertIsNotNone(botlab_host.tick_bound_note(640, 3140.8, 45, 0))

    def test_a_tick_with_many_substeps_but_no_time_is_left_alone(self):
        # The mirror of the case above, and the reason a substep cap would have
        # cost something: thousands of fast decisions are not by themselves a
        # wedge.
        self.assertIsNone(botlab_host.tick_bound_note(1, 4.0, 5000, 3))


class TheNoteSaysWhatHappenedTest(unittest.TestCase):
    def setUp(self):
        self.note = botlab_host.tick_bound_note(1796, 6827.0, 6720, 2)

    def test_it_carries_the_tick_the_time_and_the_decisions(self):
        for fragment in ("1796", "6827", "6720"):
            self.assertIn(fragment, self.note)

    def test_it_says_what_was_abandoned(self):
        # An operator reading this needs to know the queue was dropped, not
        # drained.
        self.assertIn("2 task(s) undispatched", self.note)

    def test_it_does_not_claim_the_wedge_is_over(self):
        """Handing the tick back does not un-wedge the bot.

        The outer loop sends a `TimeArrivedEvent`, the bot re-derives, and if
        the cause is still there it asks for the same tasks and blocks again.
        A note that read like a fix would be the console's stuck alarm all over
        again -- a line an operator learns to misread.
        """
        for claim in ("fixed", "recovered", "resolved", "unstuck", "cleared"):
            self.assertNotIn(claim, self.note.lower())

    def test_it_names_what_had_not_been_running(self):
        for downstream in ("tick counter", "pause/stop", "deadline"):
            self.assertIn(downstream, self.note)

    def test_it_is_a_host_comment_line(self):
        # Every other diagnostic on this path is `# `-prefixed, and the log is
        # read with greps that assume it.
        self.assertTrue(self.note.startswith("# "), self.note)


class TheLoopConsultsTheRuleTest(unittest.TestCase):
    """Pinned as source: reaching it live needs a bot process and a wedge."""

    def setUp(self):
        self.source = collapse(HOST_SOURCE)
        code = code_only(HOST_SOURCE)
        self.loop = code[code.index('pending = list(cont["startTasks"])'):]
        self.loop = self.loop[:self.loop.index('if "FinishSession" in response: continue')]

    def test_the_task_loop_asks_the_bound(self):
        self.assertIn("note = tick_bound_note(tick, time.monotonic() - tick_start,",
                      self.source)

    def test_the_bound_is_measured_from_the_tick_start(self):
        # Not from the task, and not from the process: what is being bounded is
        # how long the outer loop has been unreachable.
        self.assertIn("time.monotonic() - tick_start", self.source)

    def test_pause_and_stop_are_drained_inside_the_task_loop(self):
        """#312: both were inert for exactly as long as a tick was wedged."""
        self.assertIn("command = console.take_command()", self.loop)
        self.assertIn("stop_requested = True", self.loop)

    def test_a_settings_change_is_not_drained_there(self):
        """It writes to the pipe, so it stays where the conversation is idle.

        This is the invariant the whole console design rests on, and the one
        thing draining commands early must not break. Asked of the code with
        its comments removed, because the comment that explains the exclusion
        names the thing being excluded.
        """
        self.assertNotIn("take_settings", self.loop)
        self.assertNotIn("BotSettingsChangedEvent", self.loop)


if __name__ == "__main__":
    unittest.main()
