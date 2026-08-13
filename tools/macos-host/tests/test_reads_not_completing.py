"""Tests for the host noticing that reads have stopped completing.

Issue #166. In `saxrat_run11.log` the client stopped answering read requests and
the bot did not notice: **18,158 issued, 17,263 completed, 895 that never came
back**. From the moment they stopped, `ReadingFromGameClientCompleted` never
fired again, so `updateMemoryForNewReadingFromGame` never ran, so every counter
written there froze at the same instant:

    Ammo swap: off until the next warp (given up 2578 readings ago).
    dmg 0/3500 (45s, 33rd)
    Visited anomalies: 65.  Route marker unchanged ticks: 2428.
    Message box: 60/120 (pressing Escape at it).

The whole memory line is byte-identical for the rest of the run.

**There is no rule to fix.** PR #165 established that the message-box ladder --
the thing that looked frozen -- is correct as written, and nothing in `Bot.elm`
can advance a counter on a reading that never arrived. Every other counter was
equally correct and equally stuck.

**The defect is that the log lies.** The host reprints the current decision on
every line it writes, so a stalled pipeline produces thousands of identical lines
that read exactly like thousands of readings. By PR #165's count that has cost a
threshold calibration twice, a retreat measurement in #141, and the entire
diagnosis of #164 -- an issue filed, worked, and closed as not-a-defect.

So the host says it. These cases are about what it says and when, and about the
one distinction that keeps the word from being wrong: only the volatile-process
read is judged, because a screenshot or an input task failing is a different fact.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))

from botlab_host import (  # noqa: E402
    READS_NOT_COMPLETING_THRESHOLD, ReadCompletionWatch, read_failure_reason)

READ = "RequestToVolatileProcess"
OK_RESULT = {"RequestToVolatileProcessResponse": {"Ok": {
    "exceptionToString": None, "returnValueToString": "{}",
    "durationInMilliseconds": 1, "acquireInputFocusDurationMilliseconds": 0}}}
NOT_FOUND = {"RequestToVolatileProcessResponse": {"Err": {"ProcessNotFound": True}}}


class WhatCountsAsAReadThatDidNotCompleteTest(unittest.TestCase):

    def test_the_clients_own_refusal_is_one(self):
        self.assertIn("ProcessNotFound", read_failure_reason(READ, NOT_FOUND))

    def test_a_read_that_answered_is_not_one(self):
        self.assertIsNone(read_failure_reason(READ, OK_RESULT))

    def test_a_screenshot_failing_is_a_different_fact(self):
        """Naming it a stalled read would put the wrong word in the log at the
        moment somebody is reading it carefully."""
        self.assertIsNone(read_failure_reason(
            "InvokeMethodOnWindowRequest",
            {"InvokeMethodOnWindowResult": {"Err": {"WindowNotFound": True}}}))

    def test_an_input_task_failing_is_not_a_read_either(self):
        self.assertIsNone(read_failure_reason(
            "WindowsInputRequest", {"CompletedEffectSequenceOnWindow": False}))

    def test_the_tag_is_what_decides_and_not_the_shape_of_the_result(self):
        """The guard the other two cases do not actually exercise.

        A screenshot or input failure carries its own result shape, so those
        cases would pass with the tag check removed -- the shape alone declines
        them. This is the collision the check exists for: the 2023 host
        interface routes input *through* a volatile-process request, so a
        read-shaped `Err` can arrive from a task that was never a read. Judging
        it by shape would put "the client did not answer" in the log for a
        failed keystroke.
        """
        self.assertIsNone(read_failure_reason("WindowsInputRequest", NOT_FOUND))

    def test_an_error_shape_it_does_not_know_is_still_a_failure(self):
        """An unrecognised `Err` is a read that did not complete, and saying so
        with the payload beats saying nothing because the shape was new."""
        reason = read_failure_reason(
            READ, {"RequestToVolatileProcessResponse": {"Err": {"Whatever": 1}}})
        self.assertIsNotNone(reason)
        self.assertIn("Whatever", reason)

    def test_a_result_that_is_not_a_response_at_all_is_ignored(self):
        for result in [None, {}, {"RequestToVolatileProcessResponse": None}]:
            with self.subTest(result):
                self.assertIsNone(read_failure_reason(READ, result))


class WhenItSaysSoTest(unittest.TestCase):

    def setUp(self):
        self.watch = ReadCompletionWatch(threshold=3, repeat_every=60)

    def fail_reads(self, count):
        return [self.watch.note("the client did not answer") for _ in range(count)]

    def test_one_failure_is_not_announced(self):
        """A single failed read is ordinary and the log is noisy enough."""
        self.assertIsNone(self.watch.note("the client did not answer"))

    def test_the_threshold_is_where_it_speaks(self):
        notes = self.fail_reads(3)
        self.assertEqual([n for n in notes[:2]], [None, None])
        self.assertIn("READS ARE NOT COMPLETING", notes[2])

    def test_the_line_says_the_counters_are_frozen(self):
        """The operator's actual question is why the numbers stopped moving."""
        line = self.fail_reads(3)[2]
        self.assertIn("frozen", line)
        self.assertIn("last reading that arrived", line)

    def test_it_does_not_repeat_on_every_reading_after_that(self):
        notes = self.fail_reads(10)
        self.assertEqual(sum(1 for n in notes if n is not None), 1)

    def test_it_repeats_rarely_so_a_long_stall_stays_visible(self):
        """One line at the top of an eight-hour stall is a line nobody scrolls
        back to."""
        notes = self.fail_reads(121)
        spoken = [n for n in notes if n is not None]
        self.assertEqual(len(spoken), 3)
        self.assertIn("READS ARE NOT COMPLETING", spoken[0])
        for line in spoken[1:]:
            self.assertIn("READS STILL NOT COMPLETING", line)

    def test_recovery_is_announced_and_names_what_was_missed(self):
        self.fail_reads(5)
        line = self.watch.note(None)
        self.assertIsNotNone(
            line, "a run that recovers silently leaves the same ambiguity in"
                  " the other direction")
        self.assertIn("READS COMPLETING AGAIN", line)
        self.assertIn("5", line)
        self.assertIn("could not change", line)

    def test_a_recovery_that_was_never_announced_stays_quiet(self):
        """Two failures then an answer is not worth a line either way."""
        self.fail_reads(2)
        self.assertIsNone(self.watch.note(None))

    def test_the_count_restarts_after_a_recovery(self):
        self.fail_reads(4)
        self.watch.note(None)
        notes = self.fail_reads(3)
        self.assertEqual(notes[:2], [None, None])
        self.assertIn("3 in a row", notes[2])

    def test_a_run_that_never_stalls_says_nothing_at_all(self):
        self.assertEqual([self.watch.note(None) for _ in range(500)],
                         [None] * 500)


class TheShippedThresholdTest(unittest.TestCase):
    """The default is a judgement and is worth pinning as one."""

    def test_it_is_small_enough_to_catch_run_11_early(self):
        """895 consecutive failures is what run 11 carried, so anything in this
        range is caught long before the run is wasted -- but not so small that
        one dropped read speaks."""
        self.assertGreater(READS_NOT_COMPLETING_THRESHOLD, 1)
        self.assertLess(READS_NOT_COMPLETING_THRESHOLD, 10)

    def test_the_default_watch_uses_it(self):
        watch = ReadCompletionWatch()
        notes = [watch.note("x") for _ in range(READS_NOT_COMPLETING_THRESHOLD)]
        self.assertIsNone(notes[0])
        self.assertIn("READS ARE NOT COMPLETING", notes[-1])


if __name__ == "__main__":
    unittest.main()
