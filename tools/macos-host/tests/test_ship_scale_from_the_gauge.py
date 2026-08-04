"""Tests for the mission runner deriving its own hull's scale and scaling the
damage-rate retreat to it.

Issue #119. `run-away-incoming-damage-threshold` is the one number in the
settings that is about a *hull* rather than about the game: 3500 sits between
the worst 45-second window any surviving session absorbed (3114) and the window
the session that lost the ship peaked at (4101). Nothing in the bot noticed when
it stopped describing the ship, and moving to a battleship changes the tank by a
large multiple in one step.

**Two properties are what make this safe rather than clever, and both have cases
of their own here.**

The per-reading comparison stays gauge-free. The derivation feeds a number
computed at session scope; the live decision still compares a combat-log window
against a constant, so a gauge that starts lying mid-session cannot disarm the
one retreat guard that does not read it -- it can only fail to have scaled it.
`TheLiveComparisonReadsNoGauge` is that property read out of the source.

Failure falls back to today. No usable derivation means the configured
threshold, unchanged, which is what ten of the 22 recorded runs would get.

**The gauge is a liar and the derivation has to survive it**, which is what most
of these cases are about. CLAUDE.md records `-1021821%`, `2132822%` and a `0%`
that held for ten readings while armour was really at 82-96%. A ratio computed
from a garbage denominator produces a garbage hitpoint figure, which then scales
the threshold wrongly for a whole session -- worse than not scaling at all,
because it is silent and persistent.

The corpus cases recompute everything from `~/eve-bot-logs` rather than
restating numbers written down elsewhere, and they assert *relations* -- the
shield agrees with itself and the armour does not, the scaled threshold stays
inside the band the original calibration established -- so a corpus that grows
cannot turn a true claim red. Per-reading damage is recovered from the bot's own
printed rolling window rather than from the echoed combat lines, since
`window_k = window_(k-1) - expired_k + d_k` follows from two printed windows and
the samples that aged out.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched; without it they
**fail** rather than skipping, for the reason `prerequisites.py` gives.

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

# Every recorded run. The ones that predate the incoming-damage channel carry no
# status line this can read and drop out on their own.
ALL_RUNS = [str(n) for n in range(1, 36)]

# The two hitpoint-window numbers the original calibration rests on.
WORST_SESSION_SURVIVED = 3114
THE_SESSION_THE_SHIP_WAS_LOST_IN = 4101

# Two-reading gauge corruptions CLAUDE.md names, which `believed` cannot filter
# because the healthier of two readings is a real value on both readings.
RUN_10_SHIELD_CORRUPTION = [84, 14, 17, 84]
RUN_11_SHIELD_CORRUPTION = [96, 7, 7, 96]


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case."""
    return " ".join(text.split())


def without_comments(text):
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


def declaration(source, name):
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def int_constant(name):
    """A constant read out of `Bot.elm`, so a case tests the shipped number."""
    body = declaration(bot_source(), name)
    return int(re.search(r"\n%s =\s*(-?\d+)" % name, "\n" + body).group(1))


def maybe_int(value):
    return "Nothing" if value is None else "(Just %d)" % value


def observation_expression(damage, shield_before, shield_now,
                           armor_before=100, armor_now=100):
    return ("shipScaleObservationFromReading "
            "{ damageOnTheLastReading = %s, shieldBefore = %s, shieldNow = %s, "
            "armorBefore = %s, armorNow = %s }"
            % (maybe_int(damage), maybe_int(shield_before), maybe_int(shield_now),
               maybe_int(armor_before), maybe_int(armor_now)))


def threshold_expression(configured, shield_hitpoints):
    return ("scaledRunAwayIncomingDamageThreshold "
            "{ configured = %d, shieldHitpoints = %s }"
            % (configured, maybe_int(shield_hitpoints)))


# --------------------------------------------------------------------------
# The corpus, recomputed.
# --------------------------------------------------------------------------

STATUS = re.compile(
    r"^Shield: (?P<shield>-?\d+)%(?: \([^)]*\))?\s+Armor: (?P<armor>-?\d+)%"
    r"(?: \([^)]*\))?\. "
    r"dmg (?P<window>-?\d+)/(?:-?\d+|off) \(\d+s, \d+rd\)")
STATUS_BEFORE_THE_REWRITE = re.compile(
    r"^Shield: (?P<shield>-?\d+)%(?: \([^)]*\))?\s+Armor: (?P<armor>-?\d+)%"
    r"(?: \([^)]*\))?\. "
    r"Incoming damage: (?P<window>-?\d+) hitpoints over the last \d+ s")
TICK = re.compile(r"^# \[(\d+)\.(\d+)\] \(([\d.]+)s\)")


def believed(now, before):
    """`Maybe.map2 max` over the last two believable readings, as in Bot.elm."""
    if now is None or before is None:
        return None
    return max(now, before)


def readings_of(path, window_seconds):
    """One entry per reading: elapsed time, believed gauges, and this reading's
    own damage, recovered from the printed rolling window."""
    rows = []
    tick = None
    seen = None
    elapsed = 0.0
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            moved = TICK.match(line)
            if moved:
                if moved.group(2) == "0":
                    elapsed += float(moved.group(3))
                tick = int(moved.group(1))
                continue
            status = STATUS.match(line) or STATUS_BEFORE_THE_REWRITE.match(line)
            if not status or tick is None or tick == seen:
                continue
            seen = tick

            def plausible(name):
                value = int(status.group(name))
                return value if 0 <= value <= 100 else None

            shield, armor = plausible("shield"), plausible("armor")
            previous = rows[-1] if rows else None
            rows.append(dict(
                t=elapsed,
                shield=shield, armor=armor,
                believed_shield=believed(shield, previous["shield"] if previous else None),
                believed_armor=believed(armor, previous["armor"] if previous else None),
                window=int(status.group("window"))))

    history = []
    previous_window = 0
    for row in rows:
        expired = sum(d for t, d in history if row["t"] - t >= window_seconds)
        history = [(t, d) for t, d in history if row["t"] - t < window_seconds]
        row["damage"] = row["window"] - previous_window + expired
        history.append((row["t"], row["damage"]))
        previous_window = row["window"]
    return rows


def pairs_of(rows, lag=1):
    """Gauge movement at reading k against the damage `lag` readings earlier.

    `believed` is the healthier of the last two readings, so on a falling gauge
    it is the previous reading's value: the movement it shows at reading k is
    the movement reading k-1's damage caused.
    """
    out = []
    for index in range(1, len(rows)):
        source = index - lag
        if source < 0:
            continue

        def moved(field):
            before, now = rows[index - 1][field], rows[index][field]
            return None if before is None or now is None else before - now

        out.append(dict(damage=rows[source]["damage"],
                        shield=moved("believed_shield"),
                        armor=moved("believed_armor")))
    return out


class Corpus:
    """The recorded runs, read once and shared by every corpus case."""

    _rows = None

    @classmethod
    def rows(cls):
        if cls._rows is None:
            window = int_constant("incomingDamageWindowSeconds")
            cls._rows = {name: readings_of(path, window)
                         for name, path in recorded_runs(*ALL_RUNS)}
        return {name: rows for name, rows in cls._rows.items() if len(rows) > 20}

    @staticmethod
    def admissible(pairs, gauge, other):
        floor = int_constant("smallestDamageWorthDividingByAGaugeMove")
        smallest = int_constant("smallestGaugeMoveWorthDividing")
        largest = int_constant("largestCredibleGaugeMove")
        return [pair["damage"] * 100 // pair[gauge] for pair in pairs
                if pair[gauge] is not None and pair[other] == 0
                and pair["damage"] >= floor
                and smallest <= pair[gauge] <= largest]

    @staticmethod
    def lower_quartile(values):
        values = sorted(values)
        return values[len(values) // 4]

    @classmethod
    def per_run_estimate(cls, gauge, other):
        """What each run would have derived on its own, where it derives at all."""
        needed = int_constant("shipScaleObservationsBeforeTrusted")
        answers = {}
        for name, rows in cls.rows().items():
            values = cls.admissible(pairs_of(rows), gauge, other)
            if len(values) >= needed:
                answers[name] = cls.lower_quartile(values)
        return answers


class TheObservationRule(unittest.TestCase):
    """`shipScaleObservationFromReading`, executed rather than restated."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-ship-scale-observation-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_ratio_is_the_whole_pool_and_not_hitpoints_per_point(self):
        # 600 hitpoints moved the gauge 30 points, so the pool is 2000. Getting
        # this the other way round would derive a number 100 times too small and
        # scale the threshold to nothing.
        self.assertEqual(
            self.repl.evaluate(
                ["%s == Just 2000" % observation_expression(600, 50, 20)]),
            [True])

    def test_a_reading_the_gauge_cannot_answer_for_teaches_nothing(self):
        # Both ends of both gauges have to be believable. `Nothing` is a reading
        # with no confirmed value, and there is no movement to measure across
        # one -- not a movement of zero.
        answers = self.repl.evaluate([
            "%s == Nothing" % observation_expression(600, None, 20),
            "%s == Nothing" % observation_expression(600, 50, None),
            "%s == Nothing" % observation_expression(600, 50, 20, None, 100),
            "%s == Nothing" % observation_expression(600, 50, 20, 100, None),
            "%s /= Nothing" % observation_expression(600, 50, 20),
        ])
        self.assertEqual(answers, [True, True, True, True, True])

    def test_damage_spilling_into_the_second_gauge_is_dropped(self):
        # All of the damage would be charged to the gauge being measured, and
        # apportioning it needs the very number this is deriving. A control
        # rides along so a repl answering `Nothing` to everything cannot pass.
        answers = self.repl.evaluate([
            "%s == Nothing" % observation_expression(600, 50, 20, 100, 99),
            "%s == Nothing" % observation_expression(600, 50, 20, 100, 101),
            "%s /= Nothing" % observation_expression(600, 50, 20, 100, 100),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_a_one_point_move_is_mostly_the_rounding(self):
        # An observed move of `k` points was really somewhere in `(k-1, k+1)`,
        # so one point is the truncation error itself. Asserted on a fixed move
        # as well as at the constant's own boundary: a case that only asks about
        # `constant - 1` is satisfied by any constant, including one that admits
        # everything.
        smallest = int_constant("smallestGaugeMoveWorthDividing")
        self.assertGreater(smallest, 1)
        answers = self.repl.evaluate([
            "%s == Nothing" % observation_expression(600, 50, 49),
            "%s == Nothing" % observation_expression(600, 50, 50 - (smallest - 1)),
            "%s /= Nothing" % observation_expression(600, 50, 50 - smallest),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_a_gauge_that_did_not_fall_is_not_an_observation(self):
        # Zero and a rise both. A shield recovering while damage lands is the
        # regeneration this rule cannot correct for, not evidence about size.
        answers = self.repl.evaluate([
            "%s == Nothing" % observation_expression(600, 50, 50),
            "%s == Nothing" % observation_expression(600, 50, 70),
        ])
        self.assertEqual(answers, [True, True])

    def test_damage_below_the_floor_is_dividing_by_the_rounding(self):
        # 20 hitpoints is about one percentage point on a pool near 1900, so a
        # reading carrying that much has nothing to say about the pool's size
        # however the gauge moved. Asserted on that fixed number as well as at
        # the constant's own boundary, since a boundary-only case passes for a
        # floor of zero -- which is the mutation this exists to catch.
        floor = int_constant("smallestDamageWorthDividingByAGaugeMove")
        self.assertGreater(floor, 20)
        answers = self.repl.evaluate([
            "%s == Nothing" % observation_expression(20, 50, 20),
            "%s == Nothing" % observation_expression(floor - 1, 50, 20),
            "%s /= Nothing" % observation_expression(floor, 50, 20),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_a_host_with_no_combat_log_observes_nothing(self):
        # `Nothing` from the parser is "this host does not carry the channel",
        # and it must never be read as a quiet reading -- a zero-damage
        # observation would imply a pool of zero.
        self.assertEqual(
            self.repl.evaluate(["%s == Nothing" % observation_expression(None, 50, 20)]),
            [True])

    def test_run_10_s_two_reading_corruption_is_refused(self):
        # `84, 14, 17, 84`. `believed` gives `84, 84, 17, 84`, so a 67-point
        # move survives into this rule -- the residue `believed` cannot filter,
        # because on both readings the healthier of two values is a real one.
        # This is the case a derivation that accepts an implausible move fails.
        before, now = self._believed_pair(RUN_10_SHIELD_CORRUPTION)
        self.assertEqual(before - now, 67)
        self.assertEqual(
            self.repl.evaluate(
                ["%s == Nothing" % observation_expression(600, before, now)]),
            [True])

    def test_run_11_s_two_reading_corruption_is_refused(self):
        before, now = self._believed_pair(RUN_11_SHIELD_CORRUPTION)
        self.assertEqual(before - now, 89)
        self.assertEqual(
            self.repl.evaluate(
                ["%s == Nothing" % observation_expression(600, before, now)]),
            [True])

    def test_the_largest_credible_move_is_still_accepted(self):
        # The bound has to reject the corruptions above without rejecting a
        # shield genuinely collapsing, which the corpus shows it doing to 52
        # points in one reading against 1054 hitpoints.
        largest = int_constant("largestCredibleGaugeMove")
        answers = self.repl.evaluate([
            "%s /= Nothing" % observation_expression(1054, 100, 100 - 52),
            "%s /= Nothing" % observation_expression(2000, 100, 100 - largest),
            "%s == Nothing" % observation_expression(2000, 100, 100 - largest - 1),
        ])
        self.assertEqual(answers, [True, True, True])

    @staticmethod
    def _believed_pair(series):
        """The two consecutive `believed` values a corruption leaves behind."""
        confirmed = [max(series[i], series[i - 1]) for i in range(1, len(series))]
        return confirmed[0], confirmed[1]


class TheEstimateNeedsCorroboration(unittest.TestCase):
    """`shieldHitpointsFromObservations`: how much evidence, and which statistic."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-ship-scale-estimate-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_thin_evidence_refuses_to_derive(self):
        # One division is not a measurement: the noise on a single observation
        # is larger than the difference between hull classes this exists to
        # detect. Asserted on a fixed handful as well as at the constant's own
        # boundary, since a boundary-only case passes for a bound of one -- the
        # mutation this exists to catch.
        needed = int_constant("shipScaleObservationsBeforeTrusted")
        self.assertGreater(needed, 3)
        answers = self.repl.evaluate([
            "shieldHitpointsFromObservations [] == Nothing",
            "shieldHitpointsFromObservations [ 2000 ] == Nothing",
            "shieldHitpointsFromObservations [ 2000, 2000, 2000 ] == Nothing",
            "shieldHitpointsFromObservations %s == Nothing" % ([2000] * (needed - 1)),
            "shieldHitpointsFromObservations %s == Just 2000" % ([2000] * needed),
        ])
        self.assertEqual(answers, [True, True, True, True, True])

    def test_the_statistic_is_the_lower_quartile_and_not_the_median(self):
        # Every contamination the corpus contains shrinks the gauge's movement
        # without shrinking the damage, so all of it reads as more tank than
        # there is -- the direction that raises the threshold and keeps the ship
        # in the pocket. Eight observations, the top half of them contaminated:
        # the quartile answers 2000 and the median would answer 2900.
        observations = [1900, 1900, 2000, 2100, 2900, 5000, 9000, 30000]
        median = sorted(observations)[len(observations) // 2]
        answers = self.repl.evaluate([
            "shieldHitpointsFromObservations %s == Just 2000" % observations,
            "shieldHitpointsFromObservations %s == Just %d" % (observations, median),
        ])
        self.assertEqual(answers, [True, False])

    def test_one_outlier_cannot_be_the_answer(self):
        # At the smallest set this will act on, the quartile is the second
        # smallest, so a single contaminated observation is never the answer
        # whichever end it lands at.
        needed = int_constant("shipScaleObservationsBeforeTrusted")
        self.assertGreaterEqual(needed // 4, 1)
        high = [2000] * (needed - 1) + [50000]
        low = [1] + [2000] * (needed - 1)
        answers = self.repl.evaluate([
            "shieldHitpointsFromObservations %s == Just 2000" % high,
            "shieldHitpointsFromObservations %s == Just 2000" % low,
        ])
        self.assertEqual(answers, [True, True])

    def test_the_order_the_observations_arrived_in_does_not_matter(self):
        forwards = [1800, 1900, 2000, 2100, 2200, 9000]
        backwards = list(reversed(forwards))
        answers = self.repl.strings([
            "Debug.toString (shieldHitpointsFromObservations %s)" % forwards,
            "Debug.toString (shieldHitpointsFromObservations %s)" % backwards,
        ])
        self.assertEqual(answers[0], answers[1])


class TheThresholdFallsBackToToday(unittest.TestCase):
    """`scaledRunAwayIncomingDamageThreshold`, including the two refusals."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-ship-scale-threshold-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_no_derivation_is_current_behaviour_exactly(self):
        configured = int_constant("defaultRunAwayIncomingDamageThreshold")
        self.assertEqual(
            self.repl.evaluate(
                ["%s == %d" % (threshold_expression(configured, None), configured)]),
            [True])

    def test_a_disabled_guard_stays_disabled(self):
        # `-1` is an operator switching the retreat off. No derivation may
        # switch it back on, and none may make it a large negative number
        # either, which a bare multiplication would.
        answers = self.repl.evaluate([
            "%s == -1" % threshold_expression(-1, None),
            "%s == -1" % threshold_expression(-1, 2000),
            "%s == -1" % threshold_expression(-1, 30000),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_the_hull_it_was_calibrated_on_answers_unchanged(self):
        # The reference is the denominator, so this is 1.0 by construction --
        # and it is what makes the change a no-op on the ship the number came
        # from.
        configured = int_constant("defaultRunAwayIncomingDamageThreshold")
        reference = int_constant("shieldHitpointsWhereTheThresholdWasCalibrated")
        self.assertEqual(
            self.repl.evaluate(
                ["%s == %d" % (threshold_expression(configured, reference), configured)]),
            [True])

    def test_a_bigger_hull_moves_the_number_with_it(self):
        # The whole issue: a battleship changes the tank by a large multiple in
        # one step and the threshold has to follow.
        configured = int_constant("defaultRunAwayIncomingDamageThreshold")
        reference = int_constant("shieldHitpointsWhereTheThresholdWasCalibrated")
        answers = self.repl.evaluate([
            "%s == %d" % (threshold_expression(configured, reference * 3),
                          configured * (reference * 3) // reference),
            "%s < %d" % (threshold_expression(configured, reference // 2), configured),
            "%s > %d" % (threshold_expression(configured, reference * 3), configured),
        ])
        self.assertEqual(answers, [True, True, True])

    def test_the_operators_own_number_is_still_the_base(self):
        # Somebody who raises the setting gets a proportionally raised result,
        # so the setting does not stop being the control.
        reference = int_constant("shieldHitpointsWhereTheThresholdWasCalibrated")
        answers = self.repl.evaluate([
            "%s == 7000" % threshold_expression(7000, reference),
            "%s == 1000" % threshold_expression(1000, reference),
        ])
        self.assertEqual(answers, [True, True])


class TheCorpusSaysTheEstimateConverges(unittest.TestCase):
    """The measurement issue #119 asked for, before any bot code changes.

    Asserted as relations rather than as the numbers themselves, so a growing
    corpus cannot turn a true claim red.
    """

    def test_the_shield_answer_agrees_with_itself_across_runs(self):
        answers = Corpus.per_run_estimate("shield", "armor")
        self.assertGreaterEqual(len(answers), 8, answers)
        low, high = min(answers.values()), max(answers.values())
        # Tighter than the difference between hull classes this exists to
        # detect, which is what "it converges" has to mean to be worth acting on.
        self.assertLess(high / low, 1.3, answers)

    def test_the_armour_answer_does_not(self):
        # The second noise source #119 names, measured rather than argued: this
        # ship repairs its armour, so armour points recovered while damage lands
        # break the ratio outright. It is why the derivation reads the shield.
        #
        # Asserted over the pooled observations rather than over per-run
        # answers, so it needs no minimum number of runs and therefore no skip
        # of its own -- the corpus gate above is the only prerequisite here.
        def spread(gauge, other):
            pooled = sorted(value for rows in Corpus.rows().values()
                            for value in Corpus.admissible(pairs_of(rows), gauge, other))
            self.assertGreaterEqual(len(pooled), 20, gauge)
            return pooled[len(pooled) * 3 // 4] / pooled[len(pooled) // 4]

        self.assertGreater(spread("armor", "shield"), spread("shield", "armor"))

    def test_the_lagged_pairing_is_the_one_that_converges(self):
        # `believed` is the previous reading's value on a falling gauge, so the
        # movement it shows belongs to the previous reading's damage. Pairing it
        # with this reading's damage does not merely lose evidence -- it
        # disagrees with itself.
        lagged = [len(Corpus.admissible(pairs_of(rows, 1), "shield", "armor"))
                  for rows in Corpus.rows().values()]
        naive = [len(Corpus.admissible(pairs_of(rows, 0), "shield", "armor"))
                 for rows in Corpus.rows().values()]
        self.assertGreater(sum(lagged), sum(naive) * 2, (sum(lagged), sum(naive)))

    def test_the_scaled_threshold_stays_inside_the_calibrated_band(self):
        # The strongest thing that can be said about the cost: on the hull the
        # number was calibrated on, every run that derives anything lands
        # between the worst window a session survived and the window the session
        # that lost the ship peaked at. So the derivation cannot introduce a
        # retreat on a session that survived, and cannot miss the one that did
        # not.
        configured = int_constant("defaultRunAwayIncomingDamageThreshold")
        reference = int_constant("shieldHitpointsWhereTheThresholdWasCalibrated")
        answers = Corpus.per_run_estimate("shield", "armor")
        self.assertGreaterEqual(len(answers), 8, answers)
        for name, shield_hitpoints in answers.items():
            scaled = configured * shield_hitpoints // reference
            self.assertGreater(scaled, WORST_SESSION_SURVIVED, (name, scaled))
            self.assertLess(scaled, THE_SESSION_THE_SHIP_WAS_LOST_IN, (name, scaled))

    def test_the_reference_is_the_corpus_own_answer(self):
        # The denominator has to be measured the same way the numerator is, or
        # the ratio is not 1.0 on the hull it came from. Asserted within a few
        # percent rather than exactly, since the corpus can grow.
        reference = int_constant("shieldHitpointsWhereTheThresholdWasCalibrated")
        pooled = [value for rows in Corpus.rows().values()
                  for value in Corpus.admissible(pairs_of(rows), "shield", "armor")]
        self.assertGreaterEqual(len(pooled), 50)
        measured = Corpus.lower_quartile(pooled)
        self.assertLess(abs(measured - reference) / reference, 0.05,
                        (measured, reference))

    def test_a_quiet_run_derives_nothing_and_that_is_most_of_them(self):
        # The fallback is not a corner case: it is what the majority of recorded
        # sessions get, and it has to be current behaviour exactly.
        answers = Corpus.per_run_estimate("shield", "armor")
        self.assertLess(len(answers), len(Corpus.rows()),
                        "every recorded run derives something, which the "
                        "fallback path then never runs")

    def test_the_bounds_turn_away_only_what_the_damage_cannot_explain(self):
        # The upper bound on a gauge move costs almost nothing and rejects
        # exactly the class it exists for: moves too large for the damage beside
        # them imply a fraction of what every other observation does.
        floor = int_constant("smallestDamageWorthDividingByAGaugeMove")
        largest = int_constant("largestCredibleGaugeMove")
        kept, rejected = [], []
        for rows in Corpus.rows().values():
            for pair in pairs_of(rows):
                if pair["shield"] is None or pair["armor"] != 0:
                    continue
                if pair["damage"] < floor or pair["shield"] <= 0:
                    continue
                implied = pair["damage"] * 100 // pair["shield"]
                (rejected if pair["shield"] > largest else kept).append(implied)
        self.assertGreater(len(kept), len(rejected) * 20, (len(kept), len(rejected)))
        if rejected:
            self.assertLess(max(rejected), Corpus.lower_quartile(kept),
                            "a move over the bound implied as much tank as one "
                            "under it, so the bound is not separating anything")


class TheLiveComparisonReadsNoGauge(unittest.TestCase):
    """The property the whole design is built around, read out of the source.

    The retreat has three guards and this is the only one that does not read the
    HUD gauge. Making the live comparison a function of the gauge would let one
    bad read disarm all three at once, in the direction that keeps the ship in
    the pocket.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_threshold_is_a_function_of_memory_and_the_setting_only(self):
        # Its arguments are the configured number and session-scope memory.
        # A `ReadingFromGameClient` or a `ShipUI` in here would be this
        # reading's gauge reaching the live comparison.
        body = collapsed(without_comments(
            declaration(self.source, "incomingDamageThresholdForThisShip")))
        self.assertIn("incomingDamageThresholdForThisShip : Int -> ShipScaleMemory -> Int",
                      body)
        for forbidden in ("readingFromGameClient", "shipUI", "hitpointsPercent"):
            self.assertNotIn(forbidden, body)

    def test_the_latch_compares_the_window_against_that_number(self):
        # `updateIncomingDamageMemory`'s trip condition, unchanged in shape:
        # damage summed by the host against one integer.
        body = collapsed(without_comments(
            declaration(self.source, "updateIncomingDamageMemory")))
        self.assertIn("0 <= threshold && threshold <= damageInWindow", body)
        self.assertIn("threshold = incomingDamageThresholdForThisShip", body)

    def test_the_retreat_branch_reads_the_same_number(self):
        # One expression for the guard's own threshold, so the branch that
        # retreats and the latch that tripped cannot disagree about it.
        body = collapsed(without_comments(
            declaration(self.source, "runAwayIfLowHealth")))
        self.assertIn("incomingDamageThreshold = incomingDamageThresholdForThisShip", body)

    def test_the_derivation_is_written_where_verdicts_are_written(self):
        # A reading's `incomingDamageSinceLastReading` is gone by the next one,
        # and this rule needs the previous reading's -- so it can only live in
        # the memory update.
        update = collapsed(without_comments(
            declaration(self.source, "updateMemoryForNewReadingFromGame")))
        self.assertIn("shipScaleNow = updateShipScaleMemory context "
                      "botMemoryBefore.hitpoints hitpointsNow botMemoryBefore.shipScale",
                      update)
        self.assertIn(", shipScale = shipScaleNow", update)

    def test_the_scale_is_folded_in_before_the_latch_is_tested(self):
        # Otherwise an observation made on this reading counts towards the next
        # reading's comparison, which is #102's shape in miniature.
        update = collapsed(without_comments(
            declaration(self.source, "updateMemoryForNewReadingFromGame")))
        self.assertLess(update.index("shipScaleNow = updateShipScaleMemory"),
                        update.index("incomingDamageNow = updateIncomingDamageMemory"))
        self.assertIn("updateIncomingDamageMemory context hitpointsNow shipScaleNow "
                      "botMemoryBefore.incomingDamage", update)

    def test_the_observation_reads_the_confirmed_gauge_and_not_the_live_one(self):
        # CLAUDE.md's standing rule: every consumer of a gauge reads `believed`.
        # A derivation built on the live value would take a single corrupt
        # reading straight into the ratio.
        # All four ends named exactly, not a substring any one of them
        # satisfies: a rule that reads `believed` at three of them and the live
        # value at the fourth takes a corrupt reading straight into the ratio,
        # and passes a case that only asks whether `believed` appears.
        body = collapsed(without_comments(
            declaration(self.source, "updateShipScaleMemory")))
        for field in ("shieldBefore = hitpointsBefore.shield.believed",
                      "shieldNow = hitpointsNow.shield.believed",
                      "armorBefore = hitpointsBefore.armor.believed",
                      "armorNow = hitpointsNow.armor.believed"):
            self.assertIn(field, body)
        for live in ("hitpointsPercent", "previousReading"):
            self.assertNotIn(live, body)

    def test_the_observation_is_paired_with_the_previous_readings_damage(self):
        # The one-reading skew this rule can acquire silently. `believed` is the
        # previous reading's value on a falling gauge, so the movement it shows
        # belongs to the previous reading's damage -- and the corpus says the
        # naive pairing does not merely lose evidence, it disagrees with itself.
        body = collapsed(without_comments(
            declaration(self.source, "updateShipScaleMemory")))
        self.assertIn("damageOnTheLastReading = memoryBefore.damageOnTheLastReading",
                      body)
        # And the field it reads is written from this reading, so the next one
        # has it.
        self.assertIn("damageOnTheLastReading = "
                      "context.readingFromGameClient.incomingDamageSinceLastReading "
                      "|> Maybe.map .damage", body)

    def test_the_status_line_says_whether_anything_was_derived(self):
        # "No answer yet" and "this hull is the size the setting assumes"
        # produce the same threshold and would otherwise grep identically.
        body = collapsed(declaration(self.source, "describeShipScale"))
        self.assertIn("going by the threshold as configured", body)
        self.assertIn("shipScaleObservationsBeforeTrusted", body)
        self.assertIn("shieldHitpointsWhereTheThresholdWasCalibrated", body)
        self.assertIn("describeShipScale context",
                      collapsed(declaration(self.source, "describeIncomingDamage")))


class TheAmmoSwapBudgetDoesNotInheritTheScaling(unittest.TestCase):
    """The ripple #119 asks to be asserted rather than inherited.

    `ammoSwapDisarmDamageBudget` is an eighth of the retreat threshold -- a
    share rather than a number, deliberately, so the next hull re-derives it.
    Letting it follow the *derived* threshold would move it too: over the runs
    that derive anything it would land between 420 and 480, and 480 is past the
    445 at which the recordings stop saying the fire does not escalate. So it
    stays pinned to the number an operator set, and this is where that decision
    is written down rather than left to be discovered.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_budget_is_still_an_eighth_of_the_setting(self):
        body = collapsed(without_comments(
            declaration(self.source, "ammoSwapDisarmDamageBudget")))
        self.assertIn("disarmCase.runAwayIncomingDamageThreshold "
                      "// ammoSwapDisarmDamageBudgetDivisor", body)
        self.assertNotIn("incomingDamageThresholdForThisShip", body)
        self.assertNotIn("shipScale", body)

    def test_every_site_that_builds_the_case_reads_the_setting(self):
        # Three call sites build an `AmmoSwapDisarmCase`, and one of them
        # quietly taking the scaled number would be the inheritance this
        # refuses.
        built = re.findall(
            r"\{ runAwayIncomingDamageThreshold =\s*\n\s*([^\n]+)", self.source)
        self.assertGreaterEqual(len(built), 3, built)
        for expression in built:
            self.assertIn("botSettings.runAwayIncomingDamageThreshold", expression)

    def test_the_divisor_is_untouched(self):
        self.assertEqual(int_constant("ammoSwapDisarmDamageBudgetDivisor"), 8)


if __name__ == "__main__":
    unittest.main()
