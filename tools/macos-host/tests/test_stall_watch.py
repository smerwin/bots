"""Tests for stall_watch's progress signals.

Every case here stands for a real observation on a recorded run: the false alarm
a long approach raised, and the three pathologies that must still be caught after
fixing it. The point is not coverage -- it is that a flying ship stays quiet and
a wedged one still alarms.

None of this reads EVE's game log. `_newest_gamelog_size` is replaced with a
constant, which pins the game-log signal silent -- the condition every one of
these is interesting under, since a growing game log would reset the count on its
own and prove nothing about the decision-based tests.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stall_watch


LEAF = "Wait for progress in game"
CARGO = "Look inside Cargo Container for the The Damsel, {} m away."


def check(shooting_only=False):
    c = stall_watch.StallCheck("/nonexistent", threshold=stall_watch.CIRCLING_THRESHOLD,
                               shooting_only=shooting_only)
    c._newest_gamelog_size = lambda: 4242
    return c


def alarms(stream, shooting_only=False):
    c = check(shooting_only)
    return [r for r in (c.observe(d) for d in stream) if r]


def approach(start, stop, step, plateau, leaf=True):
    """A ship closing on a container. The distance is quantised, so one line
    repeats for a whole plateau before the number moves."""
    out = []
    for d in range(start, stop, -step):
        for _ in range(plateau):
            out.append(CARGO.format(d))
            if leaf:
                out.append(LEAF)
    return out


class ApproachIsNotAStall(unittest.TestCase):
    """A travel leg holds both original stall conditions while working perfectly:
    the quantised distance repeats, and EVE's game log notes the approach only
    every 20-100 seconds."""

    def test_reported_plateaus_stay_quiet(self):
        """The run in the issue: plateaus of up to 15 readings, distance falling
        from 84 km to the container."""
        self.assertEqual(alarms(approach(84000, 2000, 1000, 15)), [])

    def test_slow_ship_stays_quiet(self):
        """Longer plateaus are the same event, and are what actually crossed the
        threshold -- a plateau plus its interleaved leaf is two counts a reading."""
        self.assertEqual(alarms(approach(84000, 2000, 1000, 25)), [])
        self.assertEqual(alarms(approach(84000, 60000, 1000, 40)), [])

    def test_quiet_without_the_universal_leaf(self):
        """Not every approach interleaves 'Wait for progress in game'."""
        self.assertEqual(alarms(approach(84000, 2000, 1000, 15, leaf=False)), [])

    def test_first_plateau_is_given_the_benefit_of_the_doubt(self):
        """At the first sighting there is nothing to compare against, and the
        number will not move until the plateau ends -- 50 counts here, past the
        threshold. Counting it raised one alarm per approach, before the distance
        had ever had the chance to change.

        The grace is bounded: a ship that never moves is the wedge case below,
        and is still caught once the patience runs out."""
        opening = [CARGO.format(84000), LEAF] * 25
        self.assertEqual(alarms(opening + [CARGO.format(83000)]), [])


class StallsStillAlarm(unittest.TestCase):

    def test_wedged_ship_alarms(self):
        """The distance never falls: the ship has stopped, which is the case the
        watcher exists for. It is caught APPROACH_PATIENCE later than before,
        not lost."""
        self.assertTrue(alarms([CARGO.format(5000), LEAF] * 200))

    def test_oscillating_distance_alarms(self):
        """The documented 'target drifting while the ship does nothing' case.
        Judging against the smallest distance seen, rather than the previous one,
        is what keeps this alarming: the lower value is a new minimum once and
        never again."""
        stream = []
        for i in range(200):
            stream += [CARGO.format(5000 if i % 2 else 5100), LEAF]
        self.assertTrue(alarms(stream))

    def test_circling_decision_cycle_alarms(self):
        """No distance anywhere -- the four-line combat cycle the circling test
        was written for must be untouched by any of this."""
        cycle = ["I see a locked target.", "Cycle combat mod",
                 "Already pressed this weapon hotkey in a previous step.", LEAF]
        self.assertTrue(alarms(cycle * 200))

    def test_silent_guns_still_alarm(self):
        """The shooting-only view never sees a distance line, so it is unchanged."""
        self.assertTrue(alarms(["All guns cycling"] * 200, shooting_only=True))


class DistanceParsing(unittest.TestCase):

    def test_wording_ignores_the_number(self):
        self.assertEqual(stall_watch.wording_of(CARGO.format(84000)),
                         stall_watch.wording_of(CARGO.format(2439)))

    def test_wording_separates_different_objects(self):
        self.assertNotEqual(stall_watch.wording_of(CARGO.format(5000)),
                            stall_watch.wording_of(
                                "Look inside Cargo Container for the Reports, 5000 m away."))

    def test_a_second_approach_is_measured_on_its_own(self):
        """Same sentence, a new container, starting further out than the first
        one ended. Measured against the first arrival it could never improve, and
        the whole second leg would count as stalled."""
        first = approach(42000, 4000, 1000, 8)
        gap = ["I see a locked target.", "All guns cycling"] * 30
        second = approach(40000, 4000, 1000, 25)
        self.assertEqual(alarms(first + gap + second), [])


if __name__ == "__main__":
    unittest.main()
