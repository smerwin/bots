"""The retreat's rule for when a hitpoint gauge reading may be acted on.

Issue #56. `plausibleHitpointsPercent` rejects a gauge value outside [0, 100] and
has since #32. What it cannot do anything about is a garbage read that lands
*inside* that range, and #32 said so at the time -- "the same accident that
produced 21328.22 could as easily produce 0.42". Run 11 is that prediction
landing, on the one value that clears every threshold at once:

    ++ Armor reached 0% (now 0%), get out get out get out        x40

The armour was really at 82-96%. `0` is a legal armour percentage, so no filter
on the value can tell that reading from a hull that is gone.

**The rule chosen is that one reading is not evidence.** The retreat acts on the
healthier of the last two believable readings, so a drop has to survive a second
look. Nothing is excluded by value -- a hull genuinely at zero armour is exactly
the case the guard exists for -- and nothing is gated on the damage window,
which is checked below as a property, because "no game log on this host" must
never read as "ignore the gauge".

Three things this file establishes, all against recorded data rather than
invented numbers:

**It removes run 11's retreats.** The run's own armour series, 739 readings
parsed out of its status lines, carries four values below the 70% threshold and
all four are contradicted by the readings either side of them. Replayed through
the bot's own compiled rule, none survives.

**It keeps run 10's.** That run's armour genuinely declined through
`75, 75, 70, 65, 68, 60, 63, 60` under 2000 hitpoints a window, and the rule
still crosses the threshold there -- exactly one reading later than the raw
gauge did.

**The delay is one reading and cannot be more.** For any non-increasing sequence
the believed value equals the previous reading's, which is asserted over a
catastrophic 100 -> 0 drop as well as a gentle one. The rule can postpone a
retreat by a reading; it can never suppress one.

The rules are **executed** rather than mirrored, through `elm repl` against the
bot's own compiled code -- the recipe `test_travel_outranks_the_fight.py`
established. Those cases need `elm` on PATH and the app's dependencies already
fetched, which is what `compile_bot.sh` leaves behind; without it they **fail**
rather than skipping, for the reason `prerequisites.py` gives. The log-derived
cases do skip if `~/eve-bot-logs` is empty -- absent evidence and absent
machinery are different answers -- and
read a run still being appended to safely, a line at a time with the trailing
partial line dropped.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

LOG_GLOB = os.path.expanduser("~/eve-bot-logs/mission_run*.log")

# The armour threshold run 11 flew with, and the one `run_mission.sh` ships.
ARMOR_THRESHOLD = 70

# Run 11's own count of the decision line this issue was filed on.
RUN_11_ARMOR_RETREAT_LINES = 40

# The four armour readings in run 11 that would trip a threshold of 70. Each is
# one reading wide, and the values around them are what the hull really was.
RUN_11_ARMOR_READINGS_BELOW_THRESHOLD = 4

# Run 10's genuine armour decline, read out of its status lines. This is the
# case the rule must not break: a hull actually losing armour, under 2000
# hitpoints a window, with single-reading corruption interleaved through it.
RUN_10_GENUINE_DECLINE = [75, 75, 70, 65, 68, 60, 63, 60]

TICK = re.compile(r"^# \[(\d+)\.(\d+)\]")
STATUS = re.compile(r"^Shield: (-?\d+)%.*?Armor: (-?\d+)%")


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def definition_body(source, name):
    """A top-level definition's body, from its `=` to the next top-level form."""
    start = re.search(r"^" + re.escape(name) + r" .*=$|^" + re.escape(name)
                      + r" [^\n]*=\n", source, re.M)
    if start is None:
        start = re.search(r"^" + re.escape(name) + r"\b[^\n]*=", source, re.M)
    assert start is not None, "no definition of %s in Bot.elm" % name
    rest = source[start.end():]
    end = re.search(r"\n\n\n", rest)
    return rest[:end.start()] if end else rest


def plausible(value):
    """`plausibleHitpointsPercent`, for reading recorded logs only.

    The rule under test is never restated here -- it is executed through the
    repl. This is the log parser's own filter, so a recorded 2132822% is
    dropped before a series is handed to Elm, exactly as the parser drops it.
    """
    return value if 0 <= value <= 100 else None


def readings_from_log(path):
    """One (shield, armor) pair per reading, in order.

    The status line goes out about three times per reading -- the bot re-derives
    its decision on every framework event -- so consecutive identical lines are
    one reading. The damage window in the same line moves on nearly every
    reading, which is what keeps that collapse from merging two distinct ones.
    """
    rows, current = [], None
    with open(path, encoding="utf-8", errors="replace") as log:
        for line in log:
            if not line.endswith("\n"):
                # The last line of a run still being appended to.
                continue
            tick = TICK.match(line)
            if tick:
                current = tick.group(0)
            status = STATUS.match(line)
            if status is None or current is None:
                continue
            row = (line.rstrip("\n"), int(status.group(1)), int(status.group(2)))
            if rows and rows[-1][0] == row[0]:
                continue
            rows.append(row)
    return [(shield, armor) for _, shield, armor in rows]


def elm_maybe_ints(values):
    return "[ " + ", ".join(
        "Nothing" if value is None else "Just %d" % value
        for value in values) + " ]"


class ReplayingRepl(ElmRepl):
    """The shared harness, plus the folds every case here replays a run through.

    The bindings drive the real `updateHitpointsGaugeMemory` over a series of
    readings and hand back the believed value after each one. They are a
    preamble rather than a definition per case so that a case's assertions line
    up with what it asked.
    """

    BINDINGS = [
        "believedAfterEach th values = List.foldl (\\v acc ->"
        " updateHitpointsGaugeMemory th v (Tuple.first acc) |> (\\m ->"
        " ( m, Tuple.second acc ++ [ m.believed ] ))) ( initHitpointsGaugeMemory, [] )"
        " values |> Tuple.second",
        "memoryAfter th values = List.foldl (updateHitpointsGaugeMemory th)"
        " initHitpointsGaugeMemory values",
        "withheldAfterEach th values = List.foldl (\\v acc ->"
        " updateHitpointsGaugeMemory th v (Tuple.first acc) |> (\\m ->"
        " ( m, Tuple.second acc ++ [ m.readingsWithheld ] ))) ( initHitpointsGaugeMemory, [] )"
        " values |> Tuple.second",
        "belowThreshold th values = List.length (List.filter (\\v ->"
        " Maybe.withDefault 100 v < th) values)",
        "firstBelow th values = List.head (List.filterMap identity"
        " (List.indexedMap (\\i v -> if Maybe.withDefault 100 v < th then Just i else Nothing)"
        " values))",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preamble = self.preamble + self.BINDINGS


def recorded_runs():
    return sorted(glob.glob(LOG_GLOB))


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ReplayingRepl,
                             prefix="test-hitpoint-confirmation-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def armor_series(self, run):
        path = os.path.expanduser("~/eve-bot-logs/mission_%s.log" % run)
        if not os.path.exists(path):
            self.skipTest("no recorded %s in ~/eve-bot-logs" % run)
        series = [plausible(armor) for _, armor in readings_from_log(path)]
        if len(series) < 100:
            self.skipTest("%s carries too few readings to replay" % run)
        return series

    def test_run_11_s_corrupt_armour_readings_are_all_withheld(self):
        # The headline. Run 11's whole armour series through the bot's own rule:
        # the raw gauge dips below the threshold four times and the rule acts on
        # none of them, because each is contradicted by the reading before it.
        series = self.armor_series("run11")
        answers = self.repl.evaluate(
            [
                "belowThreshold %d armor11 == %d"
                % (ARMOR_THRESHOLD, RUN_11_ARMOR_READINGS_BELOW_THRESHOLD),
                "belowThreshold %d (believedAfterEach %d armor11) == 0"
                % (ARMOR_THRESHOLD, ARMOR_THRESHOLD),
            ],
            definitions=["armor11 = " + elm_maybe_ints(series)])
        self.assertEqual(
            answers[0], True,
            "run 11 no longer carries the four sub-threshold armour readings "
            "this test replays; the recording or the parser has changed")
        self.assertEqual(
            answers[1], True,
            "the rule now acts on one of run 11's corrupt armour readings -- "
            "which is issue #56 back again")

    def test_a_ship_that_is_actually_dying_still_retreats(self):
        # Run 10's real decline, and the whole point of not simply excluding a
        # value: the rule has to keep this one. It fires one reading later than
        # the raw gauge, which is the entire cost.
        answers = self.repl.evaluate(
            [
                "firstBelow %d decline == Just 3" % ARMOR_THRESHOLD,
                "firstBelow %d (believedAfterEach %d decline) == Just 4"
                % (ARMOR_THRESHOLD, ARMOR_THRESHOLD),
            ],
            definitions=["decline = " + elm_maybe_ints(RUN_10_GENUINE_DECLINE)])
        self.assertEqual(
            answers[0], True,
            "run 10's recorded decline no longer crosses the threshold where "
            "this test says it does")
        self.assertEqual(
            answers[1], True,
            "the rule no longer retreats on a hull that is genuinely losing "
            "armour, or no longer does it one reading behind the gauge")

    def test_run_10_s_whole_series_still_reaches_a_retreat(self):
        # The same claim against the run's entire recorded armour series rather
        # than the excerpt, so an interleaved corrupt reading cannot be what
        # makes the excerpt work.
        series = self.armor_series("run10")
        answers = self.repl.evaluate(
            ["belowThreshold %d (believedAfterEach %d armor10) > 0"
             % (ARMOR_THRESHOLD, ARMOR_THRESHOLD)],
            definitions=["armor10 = " + elm_maybe_ints(series)])
        self.assertTrue(
            answers[0],
            "run 10's genuine armour decline no longer reaches the threshold "
            "under this rule, so the rule is suppressing rather than delaying")

    def test_a_hull_at_zero_armour_is_believed_when_a_reading_agrees(self):
        # `0` is not excluded and must not be: it is the case the guard exists
        # for. A hull that reaches it and stays there is acted on.
        answers = self.repl.evaluate([
            "plausibleHitpointsPercent 0 == Just 0",
            "believedAfterEach 70 [ Just 30, Just 10, Just 0, Just 0 ]"
            " == [ Nothing, Just 30, Just 10, Just 0 ]",
            "(memoryAfter 70 [ Just 4, Just 0, Just 0 ]).believed == Just 0",
        ])
        self.assertEqual(
            answers, [True, True, True],
            "a hull genuinely at zero armour is being filtered away, which is "
            "the one thing issue #56 says must not happen")

    def test_the_delay_is_one_reading_and_never_more(self):
        # The safety property, and the reason a jump bound was not chosen: on
        # any non-increasing series the believed value is exactly the previous
        # reading's, however violent the step. A catastrophic drop is delayed,
        # never rejected.
        answers = self.repl.evaluate([
            "believedAfterEach 70 [ Just 100, Just 0, Just 0 ]"
            " == [ Nothing, Just 100, Just 0 ]",
            "believedAfterEach 70 [ Just 100, Just 20, Just 5, Just 2 ]"
            " == [ Nothing, Just 100, Just 20, Just 5 ]",
            "believedAfterEach 70 [ Just 99, Just 98, Just 97, Just 96 ]"
            " == [ Nothing, Just 99, Just 98, Just 97 ]",
        ])
        self.assertEqual(
            answers, [True, True, True],
            "the believed value is no longer the previous reading's on a "
            "falling gauge, so the delay is no longer bounded at one reading")

    def test_a_single_reading_is_never_evidence_however_extreme(self):
        # The shape every recorded corruption has: one reading, contradicted by
        # both its neighbours. Run 11's armour, and the same thing on the shield
        # gauge where it is far more common.
        answers = self.repl.evaluate([
            "belowThreshold 70 (believedAfterEach 70"
            " [ Just 96, Just 0, Just 99, Just 99 ]) == 0",
            "belowThreshold 70 (believedAfterEach 70"
            " [ Just 90, Just 9, Just 91, Just 89 ]) == 0",
            "belowThreshold 25 (believedAfterEach 25"
            " [ Just 100, Just 12, Just 99 ]) == 0",
        ])
        self.assertEqual(
            answers, [True, True, True],
            "a one-reading excursion is reaching the retreat again")

    def test_a_reading_with_nothing_to_confirm_it_is_not_acted_on(self):
        # Two cases with the same answer. A session's first reading has nothing
        # behind it, and a reading whose predecessor was unbelievable has
        # nothing believable behind it -- so neither is straddled to make a pair.
        answers = self.repl.evaluate([
            "(memoryAfter 70 [ Just 0 ]).believed == Nothing",
            "believedAfterEach 70 [ Just 96, Nothing, Just 0, Just 99 ]"
            " == [ Nothing, Nothing, Nothing, Just 99 ]",
        ])
        self.assertEqual(
            answers, [True, True],
            "a value with no second reading behind it is being acted on")

    def test_an_implausible_value_is_still_rejected(self):
        # #32's filter is untouched and still ahead of this one.
        answers = self.repl.evaluate([
            "plausibleHitpointsPercent 2132822 == Nothing",
            "plausibleHitpointsPercent -1021821 == Nothing",
            "plausibleHitpointsPercent 100 == Just 100",
        ])
        self.assertEqual(answers, [True, True, True])

    def test_the_withheld_count_counts_what_the_retreat_did_not_act_on(self):
        # What makes a gauge that starts lying constantly visible. It counts
        # readings that would have tripped this gauge's own threshold and did
        # not, so an ordinary decline contributes nothing.
        answers = self.repl.evaluate([
            "(memoryAfter 70 [ Just 96, Just 0, Just 99, Just 95, Just 0,"
            " Just 99 ]).readingsWithheld == 2",
            "(memoryAfter 70 [ Just 96, Just 0, Just 99, Just 95, Just 0,"
            " Just 99 ]).lastWithheld == Just 0",
            "(memoryAfter 70 [ Just 100, Just 99, Just 98, Just 97 ])"
            ".readingsWithheld == 0",
            "(memoryAfter 70 [ Just 30, Just 10, Just 0, Just 0 ])"
            ".readingsWithheld == 1",
        ])
        self.assertEqual(
            answers, [True, True, True, True],
            "the withheld counter no longer reports what the retreat declined "
            "to act on")

    def test_a_disabled_threshold_withholds_nothing(self):
        # `-1` disables a gauge's retreat, and then nothing is reading it, so
        # nothing can be withheld from it. Run 11 flew with the shield disabled
        # exactly this way.
        answers = self.repl.evaluate([
            "(memoryAfter -1 [ Just 96, Just 0, Just 99 ]).readingsWithheld == 0",
            "hitpointsReadingWithheld -1 (Just 0) (Just 96) == False",
            "hitpointsReadingWithheld 70 (Just 0) (Just 96) == True",
            "hitpointsReadingWithheld 70 (Just 0) (Just 0) == False",
            "hitpointsReadingWithheld 70 (Just 0) Nothing == True",
        ])
        self.assertEqual(
            answers, [True, True, True, True, True],
            "the withheld rule no longer follows the gauge's own threshold")

    def test_the_counter_only_holds_or_steps_by_one(self):
        # #34's lesson, applied to the one counter this change adds: assert what
        # it *evaluates to* rather than what it mentions. A counter pinned at a
        # constant, or one that resets, fails here.
        series = [96, 0, 99, 95, 0, 99, 100, 100, 0, 100]
        answers = self.repl.evaluate(
            [
                "List.all identity (List.map2 (\\a b -> b == a || b == a + 1)"
                " (0 :: steps) steps)",
                "(List.reverse steps |> List.head) == Just 3",
            ],
            definitions=["steps = withheldAfterEach %d %s"
                         % (ARMOR_THRESHOLD, elm_maybe_ints(series))])
        self.assertTrue(
            answers[0],
            "the withheld counter takes a step that is neither 'unchanged' nor "
            "'one more' -- it can be pinned or reset")
        self.assertTrue(
            answers[1],
            "the withheld counter no longer counts every reading it declined")


class WhereTheRuleSitsAndWhatItReads(unittest.TestCase):
    """Read out of the source, because these are couplings rather than values.

    Whitespace-tolerant throughout: `elm-format` owns the layout and an
    assertion on exact spacing is a test that fails on a reformat.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_retreat_reads_the_confirmed_value_and_not_the_live_gauge(self):
        body = definition_body(self.source, "runAwayIfLowHealth")
        for gauge in ("shield", "armor"):
            self.assertRegex(
                body,
                r"context\.memory\.hitpoints\." + gauge + r"\.believed",
                "runAwayIfLowHealth no longer reads the confirmed %s value" % gauge)
        self.assertNotRegex(
            body, r"plausibleHitpointsPercent\s+shipUI\.hitpointsPercent",
            "runAwayIfLowHealth is reading this reading's own gauge again, "
            "which is what let one corrupt reading fire forty retreats")

    def test_the_low_water_mark_is_fed_the_confirmed_value(self):
        body = definition_body(self.source, "updateMemoryForNewReadingFromGame")
        for gauge in ("shield", "armor"):
            self.assertRegex(
                body,
                r"lowWaterMark\s+context\.readingFromGameClient\s+"
                r"hitpointsNow\." + gauge + r"\.believed",
                "the %s low-water mark is not fed the confirmed value -- `min` "
                "is what made one corrupt reading last ten readings" % gauge)
        self.assertRegex(
            definition_body(self.source, "lowWaterMark"),
            r"case\s+believed\s+of",
            "lowWaterMark no longer takes the confirmed value")

    def test_the_frozen_reading_guard_reads_the_confirmed_value(self):
        body = definition_body(self.source, "updateIncomingDamageMemory")
        self.assertRegex(
            body,
            r"Maybe\.map2\s+Tuple\.pair\s+hitpoints\.shield\.believed"
            r"\s+hitpoints\.armor\.believed",
            "the frozen-reading guard samples the live gauge again, so a "
            "corrupt reading can pass for an instrument that is still moving")

    def test_the_confirmation_is_written_in_the_memory_update(self):
        # A reading's own values are gone by the next reading, so the pair this
        # rule needs can only be held by the one function that writes memory.
        body = definition_body(self.source, "updateMemoryForNewReadingFromGame")
        self.assertRegex(
            body, r"hitpointsNow\s*=\s*\n?\s*updateHitpointsMemory\s+context",
            "the confirmation is no longer computed in the memory update")
        self.assertRegex(
            body, r"hitpoints\s*=\s*hitpointsNow",
            "the confirmed reading is not being stored for the next reading")

    def test_the_rule_consults_no_damage_signal(self):
        # Deliberate, and the reason is the `Nothing`-versus-`Just 0`
        # distinction #37 preserved. A host with no game log reports no damage,
        # and gating the hitpoint retreat on the damage window would disarm it
        # entirely on such a host. The measurement is the other half: all three
        # of run 11's armour zeros arrived with 874, 1288 and 2006 hitpoints in
        # the window, so a "no damage" cross-check would have caught none of
        # them anyway.
        for name in ("updateHitpointsMemory", "updateHitpointsGaugeMemory",
                     "hitpointsReadingWithheld"):
            body = definition_body(self.source, name)
            for forbidden in ("incomingDamage", "hostCarriesTheChannel",
                              "samples"):
                self.assertNotIn(
                    forbidden, body,
                    "%s consults the damage channel, which disarms the "
                    "hitpoint retreat on a host with no game log" % name)

    def test_the_damage_window_itself_is_left_alone(self):
        # Two rules read this window for opposite purposes: this one must not be
        # tripped by a corrupt gauge reading, and `swapMayDisarmTheGuns` (#50,
        # being retuned under #63) must not be blocked by a trivial damage
        # reading. #56 changes one field of a sample -- the HUD value it carries
        # -- and nothing about the damage. If that stops being true, the two
        # rules have started moving each other's input.
        body = definition_body(self.source, "updateIncomingDamageMemory")
        self.assertRegex(
            body, r"damage\s*=\s*reading\.damage",
            "the sample's damage is no longer the client's own number")
        self.assertRegex(
            body,
            r"hostCarriesTheChannel\s*=\s*\n?\s*context\.readingFromGameClient"
            r"\.incomingDamageSinceLastReading\s*/=\s*Nothing",
            "the Nothing-versus-Just distinction #37 preserved has moved")
        # Anchored at both ends: a transform appended to the pipeline is exactly
        # how this number would change meaning without anyone noticing.
        self.assertRegex(
            definition_body(self.source, "incomingDamageInWindow").strip(),
            r"^memory\.samples\s*\|>\s*List\.map\s+\.damage\s*\|>\s*List\.sum$",
            "the window's total is no longer a plain sum of the damage")
        # That the other rule still reads the same accessor, and deliberately
        # nothing about how it compares the result: #63 is retuning exactly that
        # comparison, and pinning it from here would be this file legislating
        # about a rule it does not own.
        self.assertIn(
            "incomingDamageInWindow",
            definition_body(self.source, "swapMayDisarmTheGuns"),
            "the ammo swap no longer reads the window through the same "
            "accessor, so the two rules' inputs can now diverge")

    def test_only_the_frozen_reading_guard_reads_a_sample_s_hitpoints(self):
        self.assertIn(
            "List.filterMap .hitpoints",
            definition_body(self.source, "hitpointsReadingMovedInWindow"),
            "the frozen-reading guard no longer reads the sample's hitpoints")
        self.assertEqual(
            len(re.findall(r"filterMap\s+\.hitpoints", self.source)), 1,
            "a second consumer of the sample's HUD value has appeared; #56 "
            "changed what that field means, so a new reader needs its own "
            "argument about the confirmed value")

    def test_one_definition_answers_whether_a_reading_was_withheld(self):
        # Two copies of "was this reading withheld" would drift, and the copy
        # that drifted would be the one the operator reads.
        self.assertEqual(
            len(re.findall(r"^hitpointsReadingWithheld\s", self.source, re.M)),
            2,  # the type annotation and the definition
            "hitpointsReadingWithheld is no longer a single definition")
        self.assertIn(
            "hitpointsReadingWithheld",
            definition_body(self.source, "updateHitpointsGaugeMemory"),
            "the memory update no longer counts through the shared definition")
        self.assertIn(
            "hitpointsReadingWithheld",
            definition_body(self.source, "statusTextFromState"),
            "the status line no longer announces through the shared definition")

    def test_the_status_line_names_what_the_retreat_is_going_by_instead(self):
        body = definition_body(self.source, "statusTextFromState")
        self.assertRegex(
            body, r"one reading is not evidence",
            "the status line no longer says a reading was withheld, so a gauge "
            "that starts lying is invisible again")
        self.assertRegex(
            body, r"Readings withheld from the retreat this session",
            "the status line no longer carries the running count")
        self.assertRegex(
            body, r"not a believable reading -- ignored by the retreat guard",
            "#32's annotation for an impossible value has been lost")

    def test_zero_is_not_excluded_anywhere(self):
        # The issue's explicit instruction. Nothing may reject a gauge value for
        # being zero; the whole rule is about persistence, not about the value.
        for name in ("plausibleHitpointsPercent", "updateHitpointsGaugeMemory",
                     "hitpointsReadingWithheld"):
            body = definition_body(self.source, name)
            self.assertNotRegex(
                body, r"==\s*0\b",
                "%s tests a gauge value against zero, and a hull genuinely at "
                "zero armour is the case the guard exists for" % name)


class TheRecordingsThisRuleWasBuiltFrom(unittest.TestCase):
    """The premises, checked against the logs rather than remembered."""

    def setUp(self):
        if not recorded_runs():
            self.skipTest("no recorded runs in ~/eve-bot-logs")

    def test_run_11_printed_forty_retreats_on_a_healthy_hull(self):
        path = os.path.expanduser("~/eve-bot-logs/mission_run11.log")
        if not os.path.exists(path):
            self.skipTest("no recorded run11 in ~/eve-bot-logs")
        lines = []
        with open(path, encoding="utf-8", errors="replace") as log:
            for line in log:
                if not line.endswith("\n"):
                    continue
                if "Armor reached 0%" in line:
                    lines.append(line.strip())
        self.assertEqual(
            len(lines), RUN_11_ARMOR_RETREAT_LINES,
            "run 11 no longer carries the forty decision lines issue #56 was "
            "filed on")
        live = sorted({int(value) for value in re.findall(
            r"\(now (-?\d+)%\)", "\n".join(lines))})
        self.assertIn(
            0, live, "run 11's own retreats no longer include the corrupt zero")
        healthy = [value for value in live if 70 <= value <= 100]
        self.assertTrue(
            healthy,
            "run 11's retreats no longer show the live gauge reading healthy "
            "while the latched low-water mark said zero, which is the "
            "mechanism this change fixes")

    def test_the_recordings_still_carry_the_excursions_this_rule_is_for(self):
        # A premise check: if single-reading excursions inside [0, 100] ever
        # stop happening, this rule is costing a reading of delay for nothing.
        # Counted as values contradicted by the readings either side, which is
        # what a read landing on a reallocated object looks like.
        excursions = {"shield": 0, "armor": 0}
        for path in recorded_runs():
            series = readings_from_log(path)
            if len(series) < 5:
                continue
            for index, gauge in ((0, "shield"), (1, "armor")):
                values = [plausible(row[index]) for row in series]
                for i in range(1, len(values) - 1):
                    before, here, after = values[i - 1], values[i], values[i + 1]
                    if None in (before, here, after):
                        continue
                    if (abs(here - before) >= 20 and abs(here - after) >= 20
                            and abs(before - after) < 20):
                        excursions[gauge] += 1
        self.assertGreaterEqual(
            excursions["armor"], 20,
            "the recorded runs no longer carry the one-reading armour "
            "excursions this rule exists for")
        self.assertGreaterEqual(
            excursions["shield"], 100,
            "the recorded runs no longer carry the one-reading shield "
            "excursions, which are far more common than the armour ones")


if __name__ == "__main__":
    unittest.main()
