"""The ammo swap's policy about when it may take the ship's guns offline.

Issues #50 and #63. #38 bounded the period the swap leaves the guns off and the
bound worked: run 11's fourth swap reached it and latched the feature off for the
session, exactly as designed. It was not enough. The swap had begun while the
ship was already absorbing 1679 hitpoints a window from twelve hostiles at 26%
shield, and by the time the bound fired the shield was at zero and the armour had
started going. **A bound is a backstop; what was missing was a policy.**

#50's policy was **zero** -- no disarming while the client reports any incoming
damage at all -- and #63 is what that cost. Run 17 held a live verdict wanting
Multifrequency M on 271 readings and loaded it not once, blocked by windows of
128, 190, 301, 309 and 371 hitpoints against a retreat threshold of 3500. In a
mission pocket there is always *some* incoming damage, so a zero rule fires only
between waves.

**So the rule weighs what the swap gains against what the client says it would
cost.** The gain is `ammoSwapRangeErrorPercent`, how wrong the loaded charge's
range is as a share of the crossover; the risk is the same 45-second window,
compared against `ammoSwapDisarmDamageBudget` -- an eighth of the retreat
threshold, and only when the range is badly enough wrong to be worth any risk at
all. The separation is measured against the two runs that produced the two
issues, rather than asserted: run 11's fourth swap is declined, run 17's first
attempt is permitted, and run 17's own shield collapse is declined too.

**A switch-off the client confirmed and then contradicted ends the attempt.** #39
parsed `isInActiveState` onto the module button and deliberately wired it to
nothing, because no sample had ever caught a module switching off. Run 11 is that
sample, and it settles the question #39 left open in a way nobody expected: the
switch-off *lands*, on the reading straight after the click, on all four swaps.
What then happens is that the guns come back on at the third reading -- the
settle hands the fight on and `decisionToKillRats` presses the weapon hotkey --
and the swap spends the remaining seventeen readings issuing loads into a running
gun. `switchOffHasBeenUndone` is what notices, and the replay below runs the
run's own twenty status-line columns through it.

**What is deliberately *not* here.** `gunsSilencedTicks` still consults nothing
the module says about itself; `test_ammo_silenced_bound.py` owns that property
and it is unchanged. The module reading is only ever allowed to make the swap let
go *sooner*, never to hold on longer, which is what keeps #34's lesson intact
while using the signal #34 lacked. That direction is asserted below as a property
of the source, because it is the whole safety argument.

The rules are **executed** rather than mirrored, through `elm repl` against the
bot's own compiled code -- the recipe `test_dock_outranks_the_fight.py`
established. Those cases need `elm` on PATH and the app's dependencies already
fetched, which is what `compile_bot.sh` leaves behind; they skip if the repl
cannot run at all.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The retreat threshold every case below is measured against. It is the value
# `run_mission.sh` ships and `defaultRunAwayIncomingDamageThreshold` carries, and
# it is what both recorded runs were flown with.
RETREAT_THRESHOLD = 3500

# Run 11's four ammo swaps, by the incoming-damage window, the crossover and the
# target distance on the reading each one first told a gun to stop. Read out of
# `~/eve-bot-logs/mission_run11.log`'s own status lines, beside the `GUNS OFF for
# 1 of 20 readings` that marks the switch-off. The fourth is the one #50 was
# filed on and it stays declined; the first is the one #63 changes, at 110
# hitpoints on a window that was *falling* (329, 282, 220, 162, 110) as that
# engagement ended.
RUN_11_SWAPS = [
    ("swap 1, shield 2%, 41 rats", 110, 21000, 54000, True),
    ("swap 2, shield 47%, 36 rats", 0, 21000, 53000, True),
    ("swap 3, shield 100%, 6 rats", 0, 21000, 42000, True),
    ("swap 4, shield 15%, 12 rats -- the one that cost the tank",
     1679, 44000, 8480, False),
]

# Run 17, which never swapped at all. Three verdict attempts; the first is the
# one #63 is about and the third is a shield collapse inside the same run, so the
# rule has to separate them. Window, crossover and distance read out of
# `~/eve-bot-logs/mission_run17.log`'s own status lines, by the verdict's own
# reading count -- nothing may act before `ammoSwapDistanceHoldTicks` (4).
#
# Attempt 3's fourth reading sits one hitpoint under the budget and is permitted.
# That is stated rather than tuned away: the reading after it is 505 and over
# budget, so `fireArrivedWhileHoldingTheGuns` abandons and the guns come back --
# one reading of disarmament on the worst slide in the recorded corpus, against
# run 11's twenty.
RUN_17_READINGS = [
    ("attempt 1, tick 4, shield 82%", 371, 67000, 12000, True),
    ("attempt 1, tick 9, shield 77%", 301, 67000, 29000, True),
    ("attempt 1, tick 14, shield 75%", 190, 67000, 31000, True),
    ("attempt 3, tick 4, shield 42%, the slide beginning", 436, 67000, 30000, True),
    ("attempt 3, tick 5, shield 39%", 505, 67000, 29000, False),
    ("attempt 3, tick 9, shield 29%", 724, 67000, 31000, False),
    ("attempt 3, tick 22, shield 0%, armour going", 1245, 67000, 30000, False),
]

# Every reading of run 17's first attempt, in order, as the status line printed
# it -- ticks 1 to 25, then the give-up. The point is not any one of them but
# that the attempt reaches an acting tick with a permitted window, which is the
# whole of the issue: #50's rule permitted none of these.
RUN_17_FIRST_ATTEMPT = [
    (1, 257, 12000), (2, 371, 12000), (3, 371, 13000), (4, 371, 12000),
    (5, 371, 11000), (6, 371, 11000), (7, 499, 11000), (8, 433, 23000),
    (9, 301, 29000), (10, 301, 28000), (11, 301, 28000), (12, 301, 28000),
    (13, 304, 30000), (14, 190, 31000), (15, 190, 30000), (16, 190, 19000),
    (17, 256, 17000), (18, 256, 15000), (19, 128, 15000), (20, 128, 15000),
    (21, 128, 15000), (22, 128, 16000), (23, 128, 16000), (24, 128, 30000),
    (25, 128, 29000),
]
RUN_17_FIRST_ATTEMPT_CROSSOVER = 67000

# `ammoSwapDistanceHoldTicks`, restated here because these cases are about which
# reading the swap first *could* act on and that is the reading it starts from.
AMMO_SWAP_DISTANCE_HOLD_TICKS = 4

# Run 18's two swaps, at the reading each told a gun to stop. Both began on an
# empty window, so #50's rule permitted them and this one does too -- run 18 is
# the run where **the disarm gate is not what fails**: `not disarming` appears
# zero times in it, and the swap reached `GUNS OFF` twice.
#
# They are here as the no-regression case. What stopped them is one reading
# later and is not this rule's business -- see
# `TheGateIsNotTheOnlyThingBetweenTheSwapAndACharge`.
RUN_18_SWAPS = [
    ("swap 1, shield 61%, 3 rats", 0, 21000, 51000, True),
    ("swap 2, shield 79%, 7 rats", 0, 21000, 64000, True),
]

# Run 11's fatal window, reading by reading, as the status line printed the
# top-row module column: ramp_active/isInActiveState/isDeactivating. Twenty
# readings, `GUNS OFF for 1 of 20` through `20 of 20`.
#
# The shape is the finding. Two readings switched off with the ramp still
# turning, then eighteen switched back on -- while the counter that named itself
# "GUNS OFF" went on climbing, because it consults nothing the module says and
# could not know.
RUN_11_FATAL_WINDOW = (
    ["T/F/T", "T/F/T"] + ["F/T/F"] * 18
)

# The reading the swap should now let go on. Reading 1 is the click landing,
# reading 2 is it still off, reading 3 is the fight having switched it back on.
RUN_11_UNDONE_AT_READING = 3

MODULE_STATE_FIELDS = [
    "ramp_active", "isInActiveState", "isDeactivating", "effect_activating",
    "online", "blinking", "grey", "quantity", "autoreload", "autorepeat",
    "isMaster", "waitingForActiveTarget",
]


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


EVE_BOT_LOGS = os.path.join(os.path.expanduser("~"), "eve-bot-logs")


def recorded_runs(*names):
    """The runs among `names` this machine has, or a skip if it has none.

    Three situations, three different answers, and only the middle one is a
    skip:

    - the corpus is here and says something -> assert on it;
    - **the corpus is absent**, as it is on CI -> skip, with the reason stated.
      A case cannot report on evidence it cannot read, and a suite that goes red
      for "no data" teaches people to ignore red;
    - the corpus is here and does *not* say what a case asserts -> **fail**,
      because that is the evidence for a change having disappeared.

    This is a helper rather than three lines at each call site because the
    natural shape gets it wrong. Skipping missing files *inside* the loop and
    then asserting on whatever accumulated silently turns the third case into
    the second when the loop finds nothing at all: the assertion fires on an
    empty result and reports a finding where there is only an empty directory.
    CI caught exactly that, on a case that passed here.
    """
    found = [(name, os.path.join(EVE_BOT_LOGS, "mission_run%s.log" % name))
             for name in names]
    found = [pair for pair in found if os.path.exists(pair[1])]
    if not found:
        raise unittest.SkipTest(
            "none of mission_run{%s}.log is on this machine, so the recorded "
            "runs cannot be consulted here" % ",".join(names))
    return found


def let_binding(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding or `in`.

    Same shape as `test_ammo_silenced_bound.definition_body`, and separate on
    purpose: that file owns the deadline's properties and this one owns #50's,
    and a shared helper between two suites that check opposite things about the
    same function is a coupling nobody wants to reason about later.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    closing = re.search(r"\n    in\n", rest)
    if end is None or (closing is not None and closing.start() < end.start()):
        end = closing
    return rest[:end.start()] if end else rest


def elm_bool(value):
    return "True" if value else "False"


def elm_incoming_damage(damage, host_carries_the_channel=True):
    """An `IncomingDamageMemory` holding one sample worth `damage` hitpoints."""
    samples = "[]" if damage is None else (
        "[ { atMilliseconds = 0, damage = %d, hitpoints = Nothing, "
        "attacker = Nothing } ]" % damage)
    return ("{ samples = %s, hostCarriesTheChannel = %s, lastAttacker = Nothing,"
            " retreating = False }"
            % (samples, elm_bool(host_carries_the_channel)))


def elm_maybe_int(value):
    return "Nothing" if value is None else "(Just %d)" % value


def elm_disarm_case(damage, range_error_percent,
                    retreat_threshold=RETREAT_THRESHOLD,
                    host_carries_the_channel=True):
    """An `AmmoSwapDisarmCase`: what is gained, and what it would cost."""
    return ("{ runAwayIncomingDamageThreshold = %d, rangeErrorPercent = %s, "
            "incomingDamage = %s }"
            % (retreat_threshold, elm_maybe_int(range_error_percent),
               elm_incoming_damage(damage, host_carries_the_channel)))


def range_error_percent(crossover, distance):
    """`ammoSwapRangeErrorPercent`, restated here only to build the input.

    The rule itself is executed rather than mirrored; this is arithmetic on two
    numbers read off a status line, and the Elm version is checked against it
    directly in `TheGainIsMeasuredFromTheCrossover`.
    """
    return abs(distance - crossover) * 100 // crossover


def collapse(text):
    """Whitespace-collapsed source, so `elm-format` cannot break an assertion.

    #58's reformat broke three source-reading assertions that were pinned on
    exact indentation. Everything asserted about the shape of `Bot.elm` below
    goes through this.
    """
    return " ".join(text.split())


def elm_module_state(column):
    """A `ShipUIModuleButtonState` from a status-line column like "T/F/T".

    The three printed flags are filled in and the other nine left `Nothing`,
    which is also what a build that does not carry those entries produces -- so
    the cases exercise the `Maybe` handling rather than routing around it.
    """
    def flag(text):
        return {"T": "Just True", "F": "Just False"}.get(text, "Nothing")

    ramp, active, deactivating = column.split("/")
    values = dict.fromkeys(MODULE_STATE_FIELDS, "Nothing")
    values["ramp_active"] = flag(ramp)
    values["isInActiveState"] = flag(active)
    values["isDeactivating"] = flag(deactivating)
    return "{ " + ", ".join(
        "%s = %s" % (name, values[name]) for name in MODULE_STATE_FIELDS) + " }"


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    `botlab_host.py`'s recipe: copy the app to scratch, patch `elm-version` to
    whatever this machine's elm reports, build there and never in the checked-in
    source, and open `module Bot exposing (...)` to `(..)` so the repl can reach
    more than `botMain`.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-ammo-under-fire-")
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(MISSION_RUNNER_DIR, self.app)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.app, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched)

        bot = os.path.join(self.app, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened)

    def evaluate(self, expressions):
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def ask(self, expressions):
        """The answers to `expressions`, asked as one `List Bool`.

        Asked as a list rather than one expression per line because the repl
        recompiles the module for every line it is given. Measured against this
        app: twenty expressions cost 36.5s a line at a time and 5.8s as a
        single list, which is the whole reason this suite took twenty-one
        minutes. The answers come back in the order asked either way.

        `evaluate_values` below deliberately still asks line by line -- it
        parses the repl's printed form with a caller's own pattern, and inside
        a list that form is the list's, not each answer's.
        """
        if not expressions:
            return [], "", ""
        plain, stderr = self.run_repl("[ %s ]" % ", ".join(expressions))
        # The repl wraps, so `: List Bool` can land on the line after the list.
        listed = re.search(r"\[([^\]]*)\]\s*:\s*List Bool", plain.replace("\n", " "))
        answers = ([answer == "True"
                    for answer in re.findall(r"True|False", listed.group(1))]
                   if listed else [])
        return answers, plain, stderr

    def run_repl(self, *lines):
        """One repl process, given `lines` verbatim after the import."""
        script = "import Bot exposing (..)\n" + "".join(
            line + "\n" for line in lines)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout), result.stderr

    def evaluate_values(self, expressions, pattern):
        """The repl's own printed answers, for the ones that are not `Bool`.

        Still asked one expression per line, unlike `ask` above: the caller
        matches the repl's printed form with its own pattern, and inside a list
        that form is the list's rather than each answer's. These calls are the
        minority, so the line-at-a-time cost stays where it is understood.
        """
        plain, stderr = self.run_repl(*expressions)
        answers = re.findall(pattern, plain)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def works(self):
        """Whether the repl can evaluate here at all -- not what it answered.

        This decides whether the whole executed-behaviour class is skipped, so
        it must not depend on the rule being right. It used to: it asserted the
        smoke-test expression came back `True`, so a mutation that flipped that
        one answer skipped every case in the class instead of failing one, and
        the suite reported OK for a rule nothing had executed. Found by
        mutating `<=` to `<`, which is exactly the boundary the cases exist to
        pin.

        So the question asked here is only "did Elm compile this and print a
        `Bool`", and the answer it gave belongs to a case.
        """
        answers, plain, stderr = self.ask(
            ["swapMayDisarmTheGuns " + elm_disarm_case(None, None)])
        return len(answers) == 1, plain + "\n" + stderr

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here, so the rules are unchecked "
                "by execution in this environment:\n" + output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _verdicts(self, readings):
        return self.repl.evaluate([
            "swapMayDisarmTheGuns "
            + elm_disarm_case(damage, range_error_percent(crossover, distance))
            for _, damage, crossover, distance, _ in readings])

    def test_run_11_s_expensive_swap_is_still_the_one_it_declines(self):
        # The case #50 was built to prevent and the one #63 must not regress:
        # 1679 hitpoints a window, twelve hostiles, and the swap took the shield
        # from 26% to zero. Measured against the run rather than invented.
        answers = self._verdicts(RUN_11_SWAPS)
        self.assertEqual(
            answers, [allowed for _, _, _, _, allowed in RUN_11_SWAPS],
            "the rule no longer separates run 11's swaps the way the issues "
            "ask: " + repr(list(zip(
                [name for name, _, _, _, _ in RUN_11_SWAPS], answers))))

    def test_run_17_s_plinking_is_permitted_and_its_collapse_is_not(self):
        # Both halves come out of the same run, which is what makes it evidence
        # rather than a threshold chosen to pass one case: the readings that
        # blocked the swap for the whole of run 17 are permitted, and the
        # readings where that run's shield went 49% to 0% are not.
        answers = self._verdicts(RUN_17_READINGS)
        self.assertEqual(
            answers, [allowed for _, _, _, _, allowed in RUN_17_READINGS],
            "the rule no longer separates run 17's light fire from its "
            "collapse: " + repr(list(zip(
                [name for name, _, _, _, _ in RUN_17_READINGS], answers))))

    def test_run_17_s_first_attempt_reaches_a_reading_it_may_act_on(self):
        # The issue itself: 25 readings wanting Multifrequency M, every one of
        # them declined, the verdict given up, and the cycle repeating. What has
        # to change is that at least one reading at or past the hold ticks
        # permits -- otherwise the fix fixes nothing.
        answers = self.repl.evaluate([
            "swapMayDisarmTheGuns " + elm_disarm_case(
                damage,
                range_error_percent(RUN_17_FIRST_ATTEMPT_CROSSOVER, distance))
            for _, damage, distance in RUN_17_FIRST_ATTEMPT])
        acting = [tick for (tick, _, _), permitted
                  in zip(RUN_17_FIRST_ATTEMPT, answers)
                  if permitted and AMMO_SWAP_DISTANCE_HOLD_TICKS <= tick]
        self.assertTrue(
            acting,
            "run 17's first attempt still never reaches a reading it may act "
            "on, which is issue #63 unfixed")
        self.assertEqual(
            acting[0], AMMO_SWAP_DISTANCE_HOLD_TICKS,
            "the attempt should act on the first reading the hold allows; it "
            "acts at tick %d instead" % acting[0])

    def test_run_18_s_two_swaps_are_permitted_exactly_as_before(self):
        # The no-regression case, from the run where this rule is *not* what
        # fails: both swaps began on an empty window, so #50 permitted them and
        # so does this. A change that permitted more where it mattered and less
        # here would have bought run 17 at run 18's expense.
        answers = self._verdicts(RUN_18_SWAPS)
        self.assertEqual(
            answers, [allowed for _, _, _, _, allowed in RUN_18_SWAPS],
            "run 18's swaps no longer pass the gate they already passed: "
            + repr(list(zip([name for name, _, _, _, _ in RUN_18_SWAPS],
                            answers))))

    def test_a_quiet_window_is_permitted_whatever_the_gain(self):
        # The compatibility property, and the reason this cannot be a
        # regression: the budget is never negative, so everything #50 permitted
        # is still permitted and the change only ever adds readings.
        #
        # This is also where the comparison's boundary lives. With no gain the
        # budget is zero and the window is zero, so `<=` rather than `<` is the
        # whole difference between "#50's rule survives" and "the swap never
        # fires on a quiet grid either" -- and no other case here distinguishes
        # them.
        no_gain, marginal_gain, no_threshold, no_channel_entry = \
            self.repl.evaluate([
                "swapMayDisarmTheGuns " + elm_disarm_case(0, None),
                "swapMayDisarmTheGuns " + elm_disarm_case(0, 1),
                "swapMayDisarmTheGuns " + elm_disarm_case(
                    0, 90, retreat_threshold=-1),
                "swapMayDisarmTheGuns " + elm_disarm_case(None, None),
            ])
        self.assertTrue(no_gain)
        self.assertTrue(marginal_gain)
        self.assertTrue(no_threshold)
        self.assertTrue(no_channel_entry)

    def test_a_window_exactly_on_the_budget_is_permitted(self):
        # The other end of the same boundary, where the budget is not zero.
        # `< budget` would decline here and permit one hitpoint less, which is
        # a rule nobody wrote down and a difference no other case would show.
        budget = int(self.repl.evaluate_values(
            ["ammoSwapDisarmDamageBudget " + elm_disarm_case(0, 90)],
            r"(-?\d+) : Int")[0])
        on_it, one_over = self.repl.evaluate([
            "swapMayDisarmTheGuns " + elm_disarm_case(budget, 90),
            "swapMayDisarmTheGuns " + elm_disarm_case(budget + 1, 90),
        ])
        self.assertTrue(on_it)
        self.assertFalse(one_over)

    def test_an_absent_channel_declines_rather_than_reading_as_quiet(self):
        # `Nothing` and `Just 0` are different facts and only one of them may be
        # read as "the grid is quiet". A host that cannot answer gets the answer
        # that keeps the guns firing -- and it declines on a window that would
        # otherwise be well inside the budget, so it is the channel being absent
        # that decides and not the number.
        absent_empty, absent_quiet_sample, absent_inside_budget = \
            self.repl.evaluate([
                "swapMayDisarmTheGuns " + elm_disarm_case(
                    None, 90, host_carries_the_channel=False),
                "swapMayDisarmTheGuns " + elm_disarm_case(
                    0, 90, host_carries_the_channel=False),
                "swapMayDisarmTheGuns " + elm_disarm_case(
                    100, 90, host_carries_the_channel=False),
            ])
        self.assertFalse(absent_empty)
        self.assertFalse(absent_quiet_sample)
        self.assertFalse(absent_inside_budget)

    def test_the_budget_is_a_share_of_the_retreat_threshold(self):
        # The number the whole risk half rests on, and it has to move with the
        # setting rather than being a constant somebody re-measures by hand:
        # 3500 is a fact about this hull.
        budgets = self.repl.evaluate_values(
            ["ammoSwapDisarmDamageBudget " + elm_disarm_case(
                0, 90, retreat_threshold=threshold)
             for threshold in (RETREAT_THRESHOLD, 7000, 1750)],
            r"(-?\d+) : Int")
        self.assertEqual(
            [int(budget) for budget in budgets],
            [RETREAT_THRESHOLD // 8, 7000 // 8, 1750 // 8])

    def test_the_budget_is_below_the_window_that_cost_run_11_its_tank(self):
        # Stated as the relation rather than as two numbers, because the whole
        # argument for the share is that it stays below that window on any hull.
        budget = int(self.repl.evaluate_values(
            ["ammoSwapDisarmDamageBudget " + elm_disarm_case(0, 90)],
            r"(-?\d+) : Int")[0])
        run_11_expensive_swap = RUN_11_SWAPS[3][1]
        self.assertLess(budget, run_11_expensive_swap)

    def test_a_gain_that_cannot_be_measured_buys_nothing(self):
        # And neither does one too small to matter, nor a disabled retreat
        # threshold to take a share of. Each collapses the rule back to #50's,
        # which is the honest answer to not being able to tell.
        budgets = self.repl.evaluate_values(
            ["ammoSwapDisarmDamageBudget " + case for case in [
                elm_disarm_case(0, None),
                elm_disarm_case(0, 0),
                elm_disarm_case(0, 49),
                elm_disarm_case(0, 50),
                elm_disarm_case(0, 90, retreat_threshold=-1),
                elm_disarm_case(0, 90, retreat_threshold=0),
            ]],
            r"(-?\d+) : Int")
        expected = [0, 0, 0, RETREAT_THRESHOLD // 8, 0, 0]
        self.assertEqual([int(budget) for budget in budgets], expected)

    def test_the_budget_is_never_negative(self):
        # The property that makes this a superset of #50 rather than a retune.
        # A negative budget would decline a quiet window, which is the one thing
        # the old rule always allowed.
        #
        # `-1` alone does not test it: Elm's `//` truncates towards zero, so
        # `-1 // 8` is already `0` and a missing `max` survives. The settings
        # parser takes any integer, so the case that bites is a threshold past
        # the divisor.
        budgets = self.repl.evaluate_values(
            ["ammoSwapDisarmDamageBudget " + elm_disarm_case(
                0, gain, retreat_threshold=threshold)
             for threshold in (-RETREAT_THRESHOLD, -8, -1, 0, 1, 7,
                               RETREAT_THRESHOLD)
             for gain in (None, 0, 49, 50, 1000)],
            r"(-?\d+) : Int")
        self.assertTrue(all(0 <= int(budget) for budget in budgets), budgets)

    def test_the_gain_is_measured_from_the_crossover_both_ways(self):
        # A target too close and a target too far are the same magnitude of
        # wrong, and the crossover is the scale -- so the same rule reads on a
        # 21 km fit and a 67 km one.
        answers = self.repl.evaluate_values(
            ["ammoSwapRangeErrorPercent (Just { crossoverInMeters = %d, "
             "deadbandInMeters = 3000, source = \"\" }) %s"
             % (crossover, elm_maybe_int(distance))
             for crossover, distance in [
                 (44000, 8480), (44000, 66000), (44000, 22000),
                 (67000, 29000), (44000, None)]]
            + ["ammoSwapRangeErrorPercent Nothing (Just 29000)"],
            r"(Nothing|Just -?\d+) : Maybe Int")
        self.assertEqual(
            answers,
            ["Just 80", "Just 50", "Just 50", "Just 56", "Nothing", "Nothing"])

    def test_the_module_only_reports_itself_off_when_it_says_so(self):
        # Three answers, not two. An entry that did not decode is not a module
        # reporting anything, and reading it as `False` is how a build without
        # the entry would silently gain a confirmation it never gave.
        off, on, absent = self.repl.evaluate([
            "moduleReadsSwitchedOff " + elm_module_state("T/F/T"),
            "moduleReadsSwitchedOff " + elm_module_state("F/T/F"),
            "moduleReadsSwitchedOff " + elm_module_state("-/-/-"),
        ])
        self.assertTrue(off)
        self.assertFalse(on)
        self.assertFalse(absent)

    def test_the_switch_off_run_11_recorded_is_seen_as_landing(self):
        # #39 asked for exactly this reading and had none. Run 11's first two
        # readings after the click are it.
        answers = self.repl.evaluate(
            ["moduleReadsSwitchedOff " + elm_module_state(column)
             for column in RUN_11_FATAL_WINDOW[:2]])
        self.assertEqual(answers, [True, True])

    def test_run_11_s_window_is_recognised_as_undone_at_the_third_reading(self):
        # The replay: carry `gunsConfirmedOff` forward the way the memory update
        # does, and ask on each reading whether the switch-off has been undone.
        expressions = []
        confirmed = False
        confirmations = []
        for column in RUN_11_FATAL_WINDOW:
            expressions.append("switchOffHasBeenUndone %s [ %s ]"
                               % (elm_bool(confirmed), elm_module_state(column)))
            confirmations.append(confirmed)
            confirmed = confirmed or column.split("/")[1] == "F"

        answers = self.repl.evaluate(expressions)
        undone_at = [reading for reading, undone
                     in enumerate(answers, start=1) if undone]
        self.assertEqual(
            undone_at[:1], [RUN_11_UNDONE_AT_READING],
            "the swap would let go at reading %s of run 11's window, not %d -- "
            "the whole saving is the seventeen readings after that point"
            % (undone_at[:1], RUN_11_UNDONE_AT_READING))

    def test_a_module_that_reports_nothing_changes_nothing(self):
        # The compatibility property. On a build carrying no `isInActiveState`
        # every clause consulting it is false, so the swap settles on the count
        # and lets go on the deadline exactly as it did before this change.
        answers = self.repl.evaluate([
            "switchOffHasBeenUndone True [ %s ]" % elm_module_state("-/-/-"),
            "moduleReadsSwitchedOn " + elm_module_state("-/-/-"),
        ])
        self.assertEqual(answers, [False, False])

    def test_undoing_needs_a_confirmation_first(self):
        # Without one there is nothing to undo, and a gun that simply reads on
        # -- every gun, before the swap touches anything -- would abandon every
        # verdict the moment it formed.
        never_confirmed, confirmed = self.repl.evaluate([
            "switchOffHasBeenUndone False [ %s ]" % elm_module_state("F/T/F"),
            "switchOffHasBeenUndone True [ %s ]" % elm_module_state("F/T/F"),
        ])
        self.assertFalse(never_confirmed)
        self.assertTrue(confirmed)

    def test_a_gun_still_reading_off_is_not_a_switch_off_undone(self):
        # The swap switches one gun off, so a row where any gun still reads off
        # is a row where the thing it commanded is still obeying.
        still_off, one_of_each = self.repl.evaluate([
            "switchOffHasBeenUndone True [ %s ]" % elm_module_state("T/F/T"),
            "switchOffHasBeenUndone True [ %s, %s ]" % (
                elm_module_state("T/F/T"), elm_module_state("F/T/F")),
        ])
        self.assertFalse(still_off)
        self.assertFalse(one_of_each)


class TheModuleReadingCanOnlyShortenTheDisarmedPeriod(unittest.TestCase):
    """The safety argument, as a property of the source.

    Consulting the module's own state is what #34 was burned by, and the reason
    it is safe here is one-directional: every use makes the swap let go of the
    guns sooner, and none can make it hold on longer. That is not visible from
    behaviour on any one input, so it is asserted about the shape.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_undone_verdict_only_ever_abandons(self):
        # `switchOffUndone` is a branch of `verdictAbandoned` evaluating to
        # True. Abandoning resets `gunsSilencedTicks` and hands the fight back,
        # which is what re-arms the guns; any other value here would be a module
        # reading holding them rather than releasing them.
        body = let_binding(self.source, "verdictAbandoned")
        self.assertRegex(
            body, r"else if switchOffUndone then\n(\s*--[^\n]*\n)*\s*True\n")

    def test_fire_arriving_mid_swap_only_ever_abandons(self):
        body = let_binding(self.source, "verdictAbandoned")
        self.assertRegex(
            body,
            r"else if fireArrivedWhileHoldingTheGuns then\n(\s*--[^\n]*\n)*\s*True\n")

    def test_the_settle_is_shortened_and_never_extended(self):
        # `stillSettling` is the count AND-ed with the confirmation being
        # absent, so the confirmation can only end it early. An OR there, or the
        # confirmation being required rather than merely sufficient, would be a
        # wait on a module reading -- #34 exactly.
        body = let_binding(self.source, "stillSettling")
        self.assertIn("ammoSwap.gunsSilencedTicks <= ammoSwapSilenceSettleTicks", body)
        self.assertIn("&& not ammoSwap.gunsConfirmedOff", body)
        self.assertNotIn("||", body)

    def test_the_deadline_still_consults_nothing_the_module_says(self):
        # Restated here as well as in test_ammo_silenced_bound.py, because this
        # change is the first thing since #38 with a reason to reach for it.
        body = let_binding(self.source, "gunsSilencedTicks")
        for reading in ["isInActiveState", "gunsConfirmedOff",
                        "gunsReadSwitchedOff", "stateFromDictEntries"]:
            self.assertNotIn(reading, body)


class TheSwapDoesNotDisarmUnlessItIsWorthIt(unittest.TestCase):
    """Where the rule is applied, as opposed to what it answers."""

    def setUp(self):
        self.source = bot_source()

    def acting_path(self):
        body = self.source[self.source.index(
            "ensureAmmoSuitsTargetRangeWithGuns context fight nextStep ="):]
        return body[:body.index(
            "\n{-| Rest the mouse on a weapon module until the client shows")]

    def test_the_acting_path_asks_before_it_switches_a_gun_off(self):
        """The guard's whole condition, not two substrings of it.

        Two substrings would survive the condition being neutered -- an
        `&& False`, or a `gunsSilencedTicks` bound loosened until it never
        holds -- because both fragments still appear elsewhere in the same
        function. A guard that compiles and never fires is this repo's
        signature failure, so the condition is pinned as written.
        """
        conditions = [collapse(line)
                      for line in self.acting_path().split("\n") if line.strip()]
        self.assertIn(
            "else if (ammoSwap.gunsSilencedTicks < 1) "
            "&& not (swapMayDisarmTheGuns disarmCase) then",
            conditions)

    def test_the_case_the_guard_is_asked_carries_this_reading_s_gain_and_risk(self):
        """The guard is only as good as what it is handed.

        Pinning the condition alone passes happily with `disarmCase` built from
        a constant gain, a stale window, or a hard-coded threshold -- and a
        `rangeErrorPercent` wired to `Just 100` would make the budget
        unconditional, which is the whole of the risk half gone while every
        other case here still passes.
        """
        body = collapse(let_binding(self.acting_path(), "disarmCase"))
        self.assertIn(
            "{ runAwayIncomingDamageThreshold = "
            "context.eventContext.botSettings.runAwayIncomingDamageThreshold",
            body)
        self.assertIn(
            ", rangeErrorPercent = ammoSwapRangeErrorPercent threshold "
            "(Just fight.distance)",
            body)
        self.assertIn(", incomingDamage = context.memory.incomingDamage", body)

    def test_the_mid_swap_case_is_built_from_this_reading_too(self):
        # The memory update's copy. Reading the *previous* reading's distance
        # here would have the swap letting go on a gain it no longer has, or
        # holding on one it does not.
        body = collapse(let_binding(
            self.source[self.source.index(
                "updateAmmoSwapMemoryWithChargeNames context incomingDamage "
                "chargeNames memoryBefore ="):],
            "disarmCase"))
        self.assertIn(
            "{ runAwayIncomingDamageThreshold = "
            "context.botSettings.runAwayIncomingDamageThreshold",
            body)
        self.assertIn(
            ", rangeErrorPercent = ammoSwapRangeErrorPercent threshold "
            "(activeTargetDistanceInMeters context.readingFromGameClient)",
            body)
        self.assertIn(", incomingDamage = incomingDamage", body)

    def test_the_status_line_reports_the_same_verdict_the_branch_took(self):
        # Two callers of one rule, and a status line that answered from a
        # different case would report `not disarming` on readings the branch
        # acted on -- which is the failure #50's own status clause exists to
        # prevent, one level up.
        status = self.source[self.source.index("describeAmmoSwapState context ="):]
        status = status[:status.index("\n\n\n")]
        self.assertIn(
            "swapMayDisarmTheGuns (ammoSwapDisarmCaseForStatus context)",
            collapse(status))
        self.assertIn(
            "describeWhyTheSwapMayNotDisarm (ammoSwapDisarmCaseForStatus context)",
            collapse(status))

        shared = collapse(self.source[self.source.index(
            "ammoSwapDisarmCaseForStatus context ="):][:600])
        self.assertIn(
            "runAwayIncomingDamageThreshold = "
            "context.eventContext.botSettings.runAwayIncomingDamageThreshold",
            shared)
        self.assertIn(
            "rangeErrorPercent = ammoSwapRangeErrorPercent "
            "(ammoSwapThreshold context.eventContext.botSettings "
            "context.memory.ammoSwap) "
            "(activeTargetDistanceInMeters context.readingFromGameClient)",
            shared)

    def test_the_guard_precedes_the_branch_that_opens_a_menu(self):
        # A menu opened under fire is only closed again on the next reading,
        # which is churn with the mouse rather than a swap. The guard has to sit
        # in front of the whole acting path, not beside the click.
        body = self.source[self.source.index(
            "ensureAmmoSuitsTargetRangeWithGuns context fight nextStep ="):]
        guard = body.index("not (swapMayDisarmTheGuns")
        first_menu = body.index("case gunWithMenuOpen of")
        self.assertLess(
            guard, first_menu,
            "the under-fire guard must be reached before any weapon menu is")

    def test_declining_gives_up_nothing(self):
        # Deferring is not failing. The verdict stays live, the guns keep
        # shooting what they have, and `ammoSwapVerdictGiveUpTicks` drops the
        # attempt if the lull never comes.
        body = self.source[self.source.index(
            "ensureAmmoSuitsTargetRangeWithGuns context fight nextStep ="):]
        clause = body[body.index("not (swapMayDisarmTheGuns"):]
        clause = clause[:clause.index("case gunWithMenuOpen of")]
        self.assertNotIn("givenUp", clause)
        self.assertIn("nextStep", clause)

    def test_the_verdict_is_abandoned_when_the_trade_goes_bad_mid_swap(self):
        body = collapse(let_binding(self.source, "fireArrivedWhileHoldingTheGuns"))
        self.assertIn("gunsSilencedTicks > 0", body)
        self.assertIn("not (swapMayDisarmTheGuns disarmCase)", body)

    def test_the_deadline_is_the_invariant_and_nothing_here_touches_it(self):
        # #38's bound over the whole disarmed period, unchanged and still
        # independent of everything above. The mid-swap release is an early exit
        # from it, not a replacement for it -- so the bound must not have grown,
        # and must still consult neither the module nor the new rule.
        constant = self.source[self.source.index(
            "\nammoSwapSilencedGiveUpTicks : Int"):]
        self.assertIn("ammoSwapSilencedGiveUpTicks =\n    20\n", constant)
        body = let_binding(self.source, "gunsSilencedTicks")
        for reading in ["swapMayDisarmTheGuns", "disarmCase",
                        "ammoSwapDisarmDamageBudget", "incomingDamage"]:
            self.assertNotIn(reading, body)

    def test_the_window_the_rule_reads_is_this_reading_s(self):
        # The reading fire first arrives on is exactly the reading a swap must
        # not begin, so a one-reading-stale window would give it away.
        self.assertIn(
            "updateAmmoSwapMemory context incomingDamageNow botMemoryBefore.ammoSwap",
            self.source)
        # Matched loosely across the arguments -- #56 added `hitpointsNow` --
        # and strictly on the two ends that decide whether the window the swap
        # reads is this reading's: the binding, and the memory it folds into.
        self.assertRegex(
            self.source,
            r"incomingDamageNow\s*=\s*updateIncomingDamageMemory\s+context"
            r"[^\n]*botMemoryBefore\.incomingDamage")


class TheLatchedGiveUpIsSaidOnce(unittest.TestCase):
    """Run 11 printed the give-up sentence 763 times, at ~200 characters each.

    It is a permanent state, so it is news exactly once.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_counter_only_resets_starts_holds_or_increments(self):
        body = let_binding(self.source, "givenUpReadingsAgo")
        results = []
        for line in body.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            if stripped == "else" or (
                    stripped.startswith(("if ", "else if "))
                    and stripped.endswith(" then")):
                continue
            results.append(stripped)
        self.assertEqual(
            set(results),
            {"0", "1", "memoryBefore.givenUpReadingsAgo + 1"})

    def test_both_places_that_repeat_the_reason_are_shortened(self):
        # The sentence goes out twice per reading from two different functions:
        # once on the status line, and about a dozen times as a decision line.
        # Asserting only that the condition exists somewhere passes while either
        # site still prints in full, which is most of the volume -- so each site
        # is checked where it is.
        status = self.source[self.source.index("describeAmmoSwapState context ="):]
        status = status[:status.index("\n\n\n")]
        self.assertIn("if ammoSwap.givenUpReadingsAgo <= 1 then", status)
        self.assertIn("Ammo swap: off for this session (given up ", status)

        decision = self.source[self.source.index(
            "ensureAmmoSuitsTargetRange context nextStep ="):]
        decision = decision[:decision.index("\n\n\n")]
        self.assertIn("if ammoSwap.givenUpReadingsAgo <= 1 then", decision)
        self.assertIn(
            "Not swapping ammo any more (see the status line)", decision)


class TheRecordedRunsStillSayWhatTheseCasesAssume(unittest.TestCase):
    """The numbers above are read off two logs, so read them off again.

    A case list transcribed by hand and never re-checked is a case list that
    drifts away from the run it claims to be evidence from -- and every argument
    for the budget's size rests on these being the run's own figures. Skips
    where the logs are not present, since they are not in the repo.
    """

    @staticmethod
    def log_lines(name, prefix):
        path = os.path.join(
            os.path.expanduser("~"), "eve-bot-logs", "mission_run%s.log" % name)
        if not os.path.exists(path):
            raise unittest.SkipTest("no recorded " + os.path.basename(path))
        with open(path, encoding="utf-8", errors="replace") as handle:
            return [line for line in handle if line.startswith(prefix)]

    def status_lines(self, name):
        return self.log_lines(name, "Ammo swap:")

    def test_run_11_s_fourth_swap_began_where_these_cases_say(self):
        # The crossover and the distance, from the reading the swap first told a
        # gun to stop -- which is where the gain half is measured.
        _, damage, crossover, distance, _ = RUN_11_SWAPS[3]
        wanted = ("crossover %d m" % crossover,
                  "target distance: %d m" % distance,
                  "GUNS OFF for 1 of 20 readings")
        matching = [line for line in self.status_lines("11")
                    if all(fragment in line for fragment in wanted)]
        self.assertTrue(
            matching,
            "run 11's fourth swap no longer reads crossover %d m at %d m"
            % (crossover, distance))

        # And the window it began on, off the run's own health line.
        self.assertTrue(
            [line for line in self.log_lines("11", "Shield: ")
             if "Incoming damage: %d hitpoints" % damage in line],
            "run 11 no longer reports the %d hitpoint window" % damage)

    def test_run_17_blocked_the_swap_on_the_readings_these_cases_use(self):
        # The whole triple, on one status line: the window, the crossover the
        # gain is measured against and the distance it is measured from. Any one
        # of them alone would pass on a reading from somewhere else in the run,
        # and the cases are only evidence if they are the same reading.
        lines = self.status_lines("17")
        self.assertTrue(
            [line for line in lines if "not disarming" in line],
            "run 17 no longer carries a `not disarming` clause")
        for name, damage, crossover, distance, _ in RUN_17_READINGS:
            wanted = ("not disarming: the client's combat log reports "
                      "%d hitpoints" % damage,
                      "crossover %d m" % crossover,
                      "target distance: %d m" % distance)
            self.assertTrue(
                [line for line in lines
                 if all(fragment in line for fragment in wanted)],
                "run 17 has no declined reading matching this case: " + name)

    def test_run_17_s_first_attempt_reads_as_these_cases_replay_it(self):
        # The reading-by-reading replay above, checked against the run it was
        # transcribed from -- window and distance on the reading the verdict's
        # own count names.
        lines = self.status_lines("17")
        for tick, damage, distance in RUN_17_FIRST_ATTEMPT:
            wanted = ("wants short-range for %d reading(s)" % tick,
                      "reports %d hitpoints" % damage,
                      "target distance: %d m" % distance,
                      "crossover %d m" % RUN_17_FIRST_ATTEMPT_CROSSOVER)
            self.assertTrue(
                [line for line in lines
                 if all(fragment in line for fragment in wanted)],
                "run 17's first attempt no longer reads %d hitpoints at %d m on "
                "reading %d" % (damage, distance, tick))

    def test_run_17_wanted_short_range_and_kept_being_declined(self):
        # The shape of the issue rather than a count: verdicts that stay live,
        # get declined, and are given up on. The counts themselves are not
        # asserted -- run 17 was still being written when these cases were
        # taken, so a number here would drift with the log.
        lines = self.status_lines("17")
        for clause in ["wants short-range",
                       "not disarming: the client's combat log reports",
                       "gave up on this one, will try again on the next change "
                       "of range"]:
            self.assertTrue(
                [line for line in lines if clause in line],
                "run 17 no longer carries `%s`, so it is not the run these "
                "cases were read from" % clause)


class TheGateIsNotTheOnlyThingBetweenTheSwapAndACharge(unittest.TestCase):
    """What run 18 says, and why it is recorded rather than fixed here.

    Run 17 is gate-bound: 271 readings holding a live verdict, 52 of them
    declined by `swapMayDisarmTheGuns`, and `GUNS OFF` never once. Run 18 is
    **not**: `not disarming` appears zero times in it and the swap reached
    `GUNS OFF` twice. So the gate's cost is real and it is also not the only
    thing in the way, and a change to the gate must be able to say which run it
    is answering.

    What stops run 18 is one reading later. Both swaps read, on the top-row
    module column:

        T/T/F  -> the click        (switched on)
        T/F/T  -> GUNS OFF for 1   (switched off, the client confirmed it)
        F/T/F  -> gave up          (switched on again)

    The gun is back on the reading after the confirmation, with the swap still
    holding the fight and nothing in the bot having pressed the hotkey, so
    `switchOffHasBeenUndone` abandons -- on the very reading the context menu it
    asked for would have arrived. That menu is the swap's only answer to "which
    charge is loaded", which is why run 18 reads `loaded charge reads unknown`
    on all of its ammo status lines while run 11, which predates the
    confirmation, resolved the charge on 358 of its 488.

    That is #50's confirmation logic and a different argument from this one, so
    it is measured here and left alone. These cases exist so that the next
    change to either rule has the run in front of it.
    """

    @staticmethod
    def lines(name, prefix):
        path = os.path.join(
            os.path.expanduser("~"), "eve-bot-logs", "mission_run%s.log" % name)
        if not os.path.exists(path):
            raise unittest.SkipTest("no recorded " + os.path.basename(path))
        with open(path, encoding="utf-8", errors="replace") as handle:
            return [line for line in handle if line.startswith(prefix)]

    def test_run_18_was_never_stopped_by_the_gate(self):
        status = self.lines("18", "Ammo swap:")
        self.assertTrue(status, "run 18 carries no ammo status line at all")
        self.assertEqual(
            [line for line in status if "not disarming" in line], [],
            "run 18 now has the gate declining, so it is no longer the run that "
            "shows the gate is not the only constraint")
        self.assertTrue(
            [line for line in status if "GUNS OFF" in line],
            "run 18 no longer reaches GUNS OFF, so it no longer shows a swap "
            "getting past the gate")

    def test_run_18_s_swaps_died_one_reading_after_the_confirmation(self):
        # The counter never reaches 2 -- which is the whole finding, and is why
        # loosening the gate alone cannot be watched completing a swap.
        status = self.lines("18", "Ammo swap:")
        reached = {int(match.group(1))
                   for match in (re.search(r"GUNS OFF for (\d+) of", line)
                                 for line in status) if match}
        self.assertEqual(
            reached, {1},
            "run 18's swaps now hold the guns for more than one reading, which "
            "is a different run from the one these cases describe")

    def test_neither_run_that_reached_the_menu_could_read_the_charge(self):
        # And the run that predates the confirmation could. Stated as the
        # comparison rather than as three counts, because the counts drift.
        for name in ("17", "18"):
            status = self.lines(name, "Ammo swap:")
            self.assertEqual(
                [line for line in status
                 if "loaded charge reads " in line
                 and "loaded charge reads unknown" not in line],
                [],
                "run %s now resolves the loaded charge, so the symptom these "
                "cases were written from is gone" % name)
        run_11 = self.lines("11", "Ammo swap:")
        self.assertTrue(
            [line for line in run_11
             if "loaded charge reads short-range" in line
             or "loaded charge reads long-range" in line],
            "run 11 no longer resolves the loaded charge, so the menu read "
            "cannot be shown to work at all")


# Run 21's top-row module column for the first weapon, with how many of the
# run's 674 prints carried it. `isInActiveState` is `T` on every one -- the guns
# were switched on for the whole run -- while `ramp_active`, which
# `weaponIsFiring` read until #76, is `True` on barely a tenth of them. That gap
# is the bug: it is the duty cycle, and #35 measured it oscillating fourteen
# times in 240 s under an `isInActiveState` that never moved.
RUN_21_COLUMNS = [
    ("F/T/F", 322),
    ("-/T/F", 283),
    ("T/T/F", 69),
]


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class WhatCountsAsAGunThatNeedsStopping(unittest.TestCase):
    """Issue #76. `weaponIsSwitchedOn` reads the toggle, not the duty cycle.

    The swap presses the switch-off only for a gun this answers `True` for, and
    the entry gate only lets the swap start when it answers `True` for all of
    them. It read `isActive`, which is `ramp_active`, which is `False` for a
    good part of every cycle on a gun that is firing -- so both gates were being
    answered by the wrong question, and run 21 is what that cost.

    **The claim is narrower than "the gun works", deliberately.** #50's rule is
    that `isInActiveState` is used only in the negative, because `Just True` is
    not evidence a weapon is doing anything: runs 11 and 18 both show one firing
    nothing at all while reading `True`. This reads it as "the toggle is on",
    which is what #35 measured and what the client's refusal names -- `while it
    is active`. That is a considered departure from the letter of #50's rule and
    not from its reason.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here, so these rules are unchecked "
                "by execution in this environment:\n" + output)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_run_21_s_own_columns_read_as_switched_on(self):
        """Every column that run took, through the bot's own predicate.

        Including `-/T/F`, which is `ramp_active` **absent** rather than
        `False` -- 283 of the run's 674 prints. That is the entry appearing only
        once a module has first cycled, and it is why the field it replaced
        could not answer this question even in principle on a fresh grid.
        """
        answers = self.repl.evaluate([
            "moduleReadsSwitchedOn " + elm_module_state(column)
            for column, _ in RUN_21_COLUMNS])
        self.assertEqual(
            answers, [True] * len(RUN_21_COLUMNS),
            "a column run 21 actually printed no longer reads as a switched-on "
            "gun, so the swap would still decline to stop it")

    def test_the_duty_cycle_disagrees_on_the_columns_that_matter(self):
        """The measurement, rather than an assertion that the fix was needed.

        If `ramp_active` and `isInActiveState` agreed there would be no bug and
        no reason for this change, so the divergence is executed rather than
        described. Two of run 21's three columns -- 605 of its 674 prints --
        are guns that are switched on and read as idle.
        """
        columns = [column for column, _ in RUN_21_COLUMNS]
        duty = self.repl.evaluate([
            "(%s).ramp_active == Just True" % elm_module_state(column)
            for column in columns])
        switched_on = self.repl.evaluate([
            "moduleReadsSwitchedOn " + elm_module_state(column)
            for column in columns])
        disagreed = [column for column, a, b
                     in zip(columns, duty, switched_on) if a != b]
        self.assertEqual(
            sorted(disagreed), ["-/T/F", "F/T/F"],
            "the two readings no longer diverge on run 21's columns, so the "
            "evidence this change rests on is not what it was")

    def test_an_entry_that_did_not_decode_is_not_a_gun_to_stop(self):
        """`Nothing` answers `False`, exactly as `isActive` did.

        So a build that does not carry the entry behaves as it does today --
        the entry gate never opens and the swap never runs -- rather than
        pressing a module button on a guess. `Just False` likewise: pressing a
        gun that is already off would switch it *on*, since the button is a
        toggle.
        """
        self.assertEqual(
            self.repl.evaluate([
                "moduleReadsSwitchedOn " + elm_module_state("T/-/F"),
                "moduleReadsSwitchedOn " + elm_module_state("T/F/T"),
            ]),
            [False, False])


class TheSwitchOffIsChosenByTheToggleAndNotTheCycle(unittest.TestCase):
    """Issue #76, as the shape of the source and the run that measured it."""

    def setUp(self):
        self.source = bot_source()

    def definition(self, name):
        """A top-level function's own body, up to the blank line after it."""
        start = self.source.index("\n%s : " % name)
        return self.source[start:self.source.index("\n\n\n", start)]

    def test_the_predicate_reads_the_toggle_through_the_named_rule(self):
        body = self.definition("weaponIsSwitchedOn")
        self.assertIn("moduleReadsSwitchedOn moduleButton.stateFromDictEntries",
                      collapse(body))
        for duty_cycle in ["isActive", "ramp_active", "rampRotationMilli"]:
            self.assertNotIn(
                duty_cycle, body,
                duty_cycle + " is back in the predicate that chooses whether "
                "to stop a gun, which is the field #34 and #76 both cost")

    def test_both_gates_ask_it_and_nothing_asks_the_old_one(self):
        collapsed = collapse(self.source)
        self.assertIn("guns |> List.all weaponIsSwitchedOn |> not", collapsed)
        self.assertIn("fight.guns |> List.filter weaponIsSwitchedOn |> List.head",
                      collapsed)
        self.assertNotIn(
            "weaponIsFiring", self.source,
            "the old name is still here, so a call site may still be asking "
            "the duty cycle whether a gun needs stopping")

    def test_the_keep_active_filter_still_reads_isActive(self):
        """#39's line that this change does *not* cross.

        `inactiveModulesToActivateAlways` and `decisionToKillRats` still consult
        `isActive`, and #39 refused to rewire them on one 240 s sample. That is
        still refused here: this changes the ammo swap's question and nothing
        else, so the two can be reverted independently.
        """
        self.assertIn(".isActive", self.source)

    def test_the_branch_taken_is_decided_by_the_duty_cycle_and_nothing_else(self):
        """The falsifiable form, across every run that reached this branch.

        If `ramp_active` were not what chose between stopping a gun and
        declaring none was firing, some reading somewhere would disagree. None
        does: over four runs, **every** `Stop this weapon` decision was taken on
        a reading where it read `T`, and **every** `No weapon reads as firing`
        on one where it read `F` -- while `isInActiveState` read `T` on both
        sides. One counterexample in any recorded run breaks this case, which is
        what makes it evidence rather than a restatement of the diff.

        Run 22 is why this is worth asserting over the whole corpus rather than
        over run 21 alone. Same code and same build as run 21, and it reached
        `GUNS OFF` 29 times where run 21 reached it zero -- because whether a
        run catches the gun mid-cycle at the moment a verdict comes due is luck.
        A bug that presents as a run-to-run coin flip is one a single run can
        neither prove nor disprove.

        Gated on the corpus being *present*, not on the search finding
        anything. Those are different questions and CI is where they come
        apart: with no `~/eve-bot-logs` this found no press, concluded the
        evidence had vanished and failed, when the honest answer is that it
        cannot say. See `recorded_runs`.
        """
        seen = {}
        for _, path in recorded_runs("11", "18", "21", "22"):
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = handle.readlines()
            column = None
            for line in lines:
                match = re.search(r"Top-row modules \([^)]*\): ([^.,]*)", line)
                if match:
                    column = match.group(1)
                elif line.startswith("+ ") and column:
                    if "Stop this weapon before loading" in line:
                        seen.setdefault("press", set()).add(column[0])
                    elif "No weapon reads as firing" in line:
                        seen.setdefault("skip", set()).add(column[0])
        self.assertTrue(seen.get("press"), "no run reaches the switch-off")
        self.assertTrue(seen.get("skip"), "no run reaches the skip")
        self.assertEqual(
            seen["press"], {"T"},
            "a gun was stopped on a reading whose ramp_active was not True, so "
            "the duty cycle is no longer what chose this branch and the "
            "evidence for #76 is not what it was")
        self.assertEqual(
            seen["skip"], {"F"},
            "the swap declared no weapon firing on a reading whose ramp_active "
            "was True, so the two are no longer in lockstep")

    def test_run_21_is_the_measurement(self):
        """The counts, out of the log, so a retune has to argue with them."""
        (_, path), = recorded_runs("21")
        with open(path, encoding="utf-8", errors="replace") as handle:
            log = handle.read()
        columns = re.findall(r"Top-row modules \([^)]*\): ([^.,]*)", log)
        self.assertTrue(columns, "run 21 carries no top-row module clause")
        switched_on = [column for column in columns
                       if column.split("/")[1] == "T"]
        cycling = [column for column in columns
                   if column.split("/")[0] == "T"]
        self.assertEqual(
            len(switched_on), len(columns),
            "run 21 no longer reads switched-on on every reading, so it is no "
            "longer the run that separates the two fields")
        self.assertLess(
            len(cycling) * 4, len(columns),
            "run 21's guns now read mid-cycle on most readings, so the gap "
            "between the duty cycle and the toggle is not what was measured")
        self.assertEqual(
            log.count("GUNS OFF for"), 0,
            "run 21 now reaches GUNS OFF, so it is no longer the run in which "
            "the swap never switched anything off")
        self.assertGreater(
            log.count("No weapon reads as firing"), 0,
            "run 21 no longer carries the decision line this issue is about "
            "-- it is the pre-fix wording and the log is a recording, so it "
            "cannot change unless the file was replaced")


if __name__ == "__main__":
    unittest.main()
