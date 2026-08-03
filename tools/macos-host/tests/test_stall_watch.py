"""Tests for stall_watch's progress signals and the unit it counts in.

Every case here stands for a real observation on a recorded run: the false alarm
a long approach raised, the flood of alarms an eight-second threshold raised on
healthy combat, and the pathologies that must still be caught after fixing both.
The point is not coverage -- it is that a flying ship stays quiet and a wedged
one still alarms.

Decisions are fed in **readings**, because that is the unit the counter now
works in: `observe` folds a decision into the reading being assembled and
reports nothing, and `end_reading` judges it. A real reading carries about a
dozen decisions, all of them the framework re-deriving one decision path over
one look at the game.

None of this reads EVE's game log. `_newest_gamelog_size` is replaced with a
constant, which pins the game-log signal silent -- the condition every one of
these is interesting under, since a growing game log resets the count on its own
and would prove nothing about the decision-based tests.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import stall_watch


LEAF = "Wait for progress in game"
CARGO = "Look inside Cargo Container for the The Damsel, {} m away."
COMBAT_CYCLE = ["I see a locked target.", "Cycle combat mod",
                "Already pressed this weapon hotkey in a previous step.", LEAF]
DEEP_READING = ["I see a locked target.", "All guns cycling", "No idling drones.",
                "Everything worth locking is locked.", LEAF]


def check(shooting_only=False):
    c = stall_watch.StallCheck("/nonexistent", threshold=stall_watch.CIRCLING_THRESHOLD,
                               shooting_only=shooting_only)
    c._newest_gamelog_size = lambda: 4242
    return c


def alarms(readings, shooting_only=False):
    """`readings` is a list of readings, each a list of decision lines."""
    c = check(shooting_only)
    out = []
    for reading in readings:
        for decision in reading:
            c.observe(decision)
        r = c.end_reading()
        if r:
            out.append(r)
    return out


def repeat(decisions, n):
    """The same reading n times over -- a bot deciding the same thing again."""
    return [list(decisions) for _ in range(n)]


def approach(start, stop, step, plateau, leaf=True):
    """A ship closing on a container. The distance is quantised, so one reading
    repeats for a whole plateau before the number moves."""
    out = []
    for d in range(start, stop, -step):
        body = [CARGO.format(d)] + ([LEAF] if leaf else [])
        out += repeat(body, plateau)
    return out


class TheUnitIsTheReading(unittest.TestCase):
    """The counter used to count decision lines. The bot re-derives its whole
    path on every framework event -- about a dozen lines per reading -- so the
    threshold was really about eight seconds of wall clock, and healthy combat
    pauses for longer than that."""

    def test_a_reading_counts_once_however_many_decisions_it_carries(self):
        just_under = stall_watch.CIRCLING_THRESHOLD - 1
        self.assertEqual(alarms(repeat(DEEP_READING, just_under)), [])

    def test_the_threshold_is_reached_in_readings_not_decisions(self):
        self.assertTrue(alarms(repeat(DEEP_READING, stall_watch.CIRCLING_THRESHOLD + 1)))

    def test_a_reading_with_nothing_to_judge_is_passed_over(self):
        """Not evidence either way. Counting it as progress would reset the
        counter on every reading a wedged bot spends saying nothing."""
        stream = []
        for _ in range(stall_watch.CIRCLING_THRESHOLD + 2):
            stream.append(["Cycle combat mod"])
            stream.append([])
        self.assertTrue(alarms(stream))


class ApproachIsNotAStall(unittest.TestCase):
    """A travel leg holds both original stall conditions while working perfectly:
    the quantised distance repeats, and EVE's game log notes the approach only
    every 20-100 seconds."""

    def test_reported_plateaus_stay_quiet(self):
        self.assertEqual(alarms(approach(84000, 2000, 1000, 15)), [])

    def test_slow_ship_stays_quiet(self):
        """Plateaus far longer than anything measured. On the recorded run the
        longest gap between two strict decreases inside one approach was 22
        decisions -- about two readings -- so 25 and 30 are an order of
        magnitude of headroom."""
        self.assertEqual(alarms(approach(84000, 2000, 1000, 25)), [])
        self.assertEqual(alarms(approach(84000, 60000, 1000, 30)), [])

    def test_a_ship_that_stops_mid_approach_is_still_caught(self):
        """The headroom is bounded on purpose. Past APPROACH_PATIENCE plus the
        threshold -- about a hundred seconds on one quantised distance, when the
        measured worst case is two readings -- a ship that has not gained a
        kilometre is not approaching, it is stuck."""
        plateau = stall_watch.APPROACH_PATIENCE + stall_watch.CIRCLING_THRESHOLD
        self.assertTrue(alarms(approach(84000, 60000, 1000, plateau)))

    def test_quiet_without_the_universal_leaf(self):
        self.assertEqual(alarms(approach(84000, 2000, 1000, 15, leaf=False)), [])

    def test_first_plateau_is_given_the_benefit_of_the_doubt(self):
        """At the first sighting there is nothing to compare against, and the
        number will not move until the plateau ends. Counting it raised one
        alarm per approach before the distance had ever had a chance to change.

        The grace is bounded: a ship that never moves is the wedge case below."""
        opening = repeat([CARGO.format(84000), LEAF], stall_watch.APPROACH_PATIENCE)
        self.assertEqual(alarms(opening + [[CARGO.format(83000)]]), [])


class StallsStillAlarm(unittest.TestCase):

    def test_wedged_ship_alarms(self):
        """The distance never falls: the ship has stopped. Caught
        APPROACH_PATIENCE readings later than a bare repeat, not lost."""
        n = stall_watch.APPROACH_PATIENCE + stall_watch.CIRCLING_THRESHOLD + 5
        self.assertTrue(alarms(repeat([CARGO.format(5000), LEAF], n)))

    def test_oscillating_distance_alarms(self):
        """The documented 'target drifting while the ship does nothing' case.
        Judging against the smallest distance seen, rather than the previous
        one, is what keeps this alarming: the lower value is a new minimum once
        and never again."""
        n = stall_watch.APPROACH_PATIENCE + stall_watch.CIRCLING_THRESHOLD + 5
        stream = [[CARGO.format(5000 if i % 2 else 5100), LEAF] for i in range(n)]
        self.assertTrue(alarms(stream))

    def test_circling_decision_cycle_alarms(self):
        """The four-line combat cycle the circling test was written for, here
        spread one line per reading -- the shape that defeated the original
        consecutive-identical counter."""
        n = stall_watch.CIRCLING_THRESHOLD + 5
        self.assertTrue(alarms([[d] for _ in range(n) for d in COMBAT_CYCLE]))

    def test_silent_guns_still_alarm(self):
        n = stall_watch.CIRCLING_THRESHOLD + 5
        self.assertTrue(alarms(repeat(["All guns cycling"], n), shooting_only=True))

    def test_benign_idling_does_not_alarm(self):
        n = stall_watch.CIRCLING_THRESHOLD + 5
        self.assertEqual(alarms(repeat(["I am in warp", LEAF], n)), [])


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
        gap = repeat(["I see a locked target.", "All guns cycling"], 30)
        second = approach(40000, 4000, 1000, 25)
        self.assertEqual(alarms(first + gap + second), [])


class ReportingTheSameStallOnce(unittest.TestCase):
    """Every screenshot is a full-resolution Retina grab, so a stall reported on
    a metronome costs gigabytes. Distinctness masks the parts that drift."""

    def setUp(self):
        self._capture = stall_watch.capture
        stall_watch.capture = lambda *a, **kw: "/dev/null"
        self.addCleanup(setattr, stall_watch, "capture", self._capture)
        self.reporter = stall_watch.Reporter(window_id=0, out_dir="/nonexistent",
                                             max_shots=99)

    def test_numbers_do_not_make_a_new_stall(self):
        self.reporter.report("circling", "going in circles: 20 readings -- 5000 m away")
        self.reporter.report("circling", "going in circles: 20 readings -- 4000 m away")
        self.assertEqual(self.reporter.shots, 1)

    def test_object_names_do_not_make_a_new_stall(self):
        """A benign pattern already dismissed for one rat should not be
        re-photographed for the next rat of a different name."""
        self.reporter.report("circling", "circles -- Lock target from entry 'EoM Demon'")
        self.reporter.report("circling", "circles -- Lock target from entry 'EoM Succubus'")
        self.assertEqual(self.reporter.shots, 1)

    def test_a_genuinely_different_stall_is_photographed(self):
        self.reporter.report("circling", "going in circles -- All guns cycling")
        self.reporter.report("circling", "going in circles -- I see a message box to close")
        self.assertEqual(self.reporter.shots, 2)


if __name__ == "__main__":
    unittest.main()
