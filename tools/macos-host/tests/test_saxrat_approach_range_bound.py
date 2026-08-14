"""Approaching has a maximum range, and past it the bot warps or leaves it alone.

`lockTargetFromOverviewEntry` had two branches -- lock it, or approach it -- and
no upper bound on the second. Run 41 double-clicked a row **2,266 km** away
13,541 times across three hours. `Already on the way` fired **zero** times and
the ship never moved: 3 anomalies and 39 kills, against 31 anomalies on the same
settings a week earlier.

A double click at that range is a gesture the client discards, and nothing in the
loop could tell the difference -- the row stayed where it was and stayed the
nearest thing worth attacking, so the same decision came out on every reading.

150 km is EVE's own boundary rather than a number picked here: the client will
not warp to anything closer, and an approach is how the last of that distance is
closed. So the two branches either side of it are the two gestures the client
actually offers.

This is #168's shape one branch over -- that issue is an acceleration gate
chased at 1,395 km for four hours -- and a bound written only for gates would
not have covered run 41.
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

# Run 41's own distance, and the boundary either side.
RUN41_METRES = 2266000
LIMIT = 150000


class TheBoundIsTheClientsOwnWarpMinimum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-approach-bound-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_limit_is_150_km(self):
        self.assertTrue(
            self.repl.evaluate(["approachRangeLimitMeters == %d" % LIMIT])[0],
            "150 km is EVE's own warp minimum; a different number would put the "
            "two branches somewhere the client does not agree with")

    def test_it_is_far_below_the_distance_run_41_chased(self):
        """A bound above run 41's distance would leave that session unchanged,
        which is the one thing this must not do."""
        self.assertTrue(
            self.repl.evaluate(
                ["approachRangeLimitMeters < %d" % RUN41_METRES])[0])

    def test_it_is_far_above_any_lock_range_in_use(self):
        """Below the largest targeting range a hull might have, the bound would
        take over from the lock branch rather than from the approach."""
        self.assertTrue(
            self.repl.evaluate(["70000 < approachRangeLimitMeters"])[0])


class TheDistantRowIsWarpedAtOrLeftAlone(unittest.TestCase):
    """`warpToDistantOverviewEntry`, read from the source -- it needs a whole
    context, so the branch cannot be called from the repl."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(body_of(cls.source, "warpToDistantOverviewEntry"))
        cls.lock = collapsed(body_of(cls.source, "lockTargetFromOverviewEntry"))

    def test_the_approach_is_gated_on_the_limit(self):
        self.assertIn("distanceInMeters <= approachRangeLimitMeters", self.lock)

    def test_past_the_limit_it_no_longer_double_clicks(self):
        gated = self.lock.split("distanceInMeters <= approachRangeLimitMeters")[1]
        past = gated.split("else")[-1]
        self.assertNotIn("doubleClickUiElement", past,
                         "the whole failure is a double click at a range the "
                         "client discards it at")
        self.assertIn("warpToDistantOverviewEntry", past)

    def test_it_selects_the_row_before_pressing(self):
        self.assertIn("selectedItemIsOverviewEntry context.readingFromGameClient overviewEntry",
                      self.branch)
        self.assertIn("clickUiElement overviewEntry.uiNode", self.branch)

    def test_it_presses_the_panel_warp_button(self):
        self.assertIn('selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo"',
                      self.branch)

    def test_no_warp_button_ends_the_attempt_rather_than_approaching(self):
        """The 'do nothing' half. Falling back to the approach here would be
        run 41 again with one extra reading of ceremony."""
        self.assertNotIn("doubleClickUiElement", self.branch)
        self.assertIn("waitForProgressInGame", self.branch)

    def test_the_drones_come_home_before_the_warp(self):
        self.assertIn("ensureDronesRecalledBeforeWarping", self.branch)

    def test_the_distance_is_reported_in_km(self):
        """2266000 reads as noise; 2266 km reads as a mistake."""
        self.assertIn("distanceInMeters // 1000", self.branch)

    def test_the_lock_branch_is_otherwise_untouched(self):
        for kept in ("Lock target from overview entry",
                     "Locking target is in progress",
                     "Failed to read the distance"):
            self.assertIn(kept, self.lock)


def run41():
    path = os.path.join(EVE_BOT_LOGS, "saxrat_run41.log")
    if not os.path.exists(path):
        raise unittest.SkipTest("no recorded saxrat_run41.log")
    return path


class Run41IsWhyTheBoundExists(unittest.TestCase):
    def test_it_approached_something_past_the_limit_many_times(self):
        far = 0
        with open(run41(), errors="replace") as handle:
            for line in handle:
                m = re.search(r"Object is not in range \((\d+) m away\)", line)
                if m and int(m.group(1)) > LIMIT:
                    far += 1
        self.assertGreater(
            far, 1000,
            "run 41's defining failure is a great many approaches past the "
            "bound; a corpus that no longer shows them is not this run")

    def test_the_ship_never_actually_moved(self):
        with open(run41(), errors="replace") as handle:
            text = handle.read()
        self.assertEqual(
            0, text.count("Already on the way"),
            "the approaches were dispatched and achieved nothing -- if the ship "
            "did move, the bound is solving a different problem than this")


if __name__ == "__main__":
    unittest.main()
