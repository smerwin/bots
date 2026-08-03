"""The ammo swap's policy about when it may take the ship's guns offline.

Issue #50. #38 bounded the period the swap leaves the guns off and the bound
worked: run 11's fourth swap reached it and latched the feature off for the
session, exactly as designed. It was not enough. The swap had begun while the
ship was already absorbing 1679 hitpoints a window from twelve hostiles at 26%
shield, and by the time the bound fired the shield was at zero and the armour had
started going. **A bound is a backstop; what was missing was a policy.**

Two rules are checked here, and they come from two signals that did not exist
when the swap was written.

**The guns do not go off while the client says the ship is being shot.** #37
exposed `incomingDamageSinceLastReading` and the mission runner already sums it
over a rolling 45-second window, so "am I being shot right now" is a number the
bot holds on every reading. `swapMayDisarmTheGuns` is that rule. The separation
it produces is measured against run 11's own four swaps rather than asserted: the
two that began under fire are declined and the two that began in a lull are
allowed.

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

# Run 11's four ammo swaps, by the incoming-damage window on the reading each
# one first told a gun to stop. Read out of `~/eve-bot-logs/mission_run11.log`'s
# own status lines, beside the `GUNS OFF for 1 of 20 readings` that marks the
# switch-off. The fourth is the one the issue was filed on.
RUN_11_SWAPS = [
    ("swap 1, shield 2%, 41 rats", 110, False),
    ("swap 2, shield 47%, 36 rats", 0, True),
    ("swap 3, shield 100%, 6 rats", 0, True),
    ("swap 4, shield 15%, 12 rats -- the one that cost the tank", 1679, False),
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
        script = "import Bot exposing (..)\n" + "".join(
            expression + "\n" for expression in expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = [answer == "True"
                   for answer in re.findall(r"(True|False) : Bool", plain)]
        return answers, plain, result.stderr

    def works(self):
        answers, plain, stderr = self.ask(
            ["swapMayDisarmTheGuns " + elm_incoming_damage(None)])
        return answers == [True], plain + "\n" + stderr

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

    def test_run_11_s_two_swaps_under_fire_are_the_two_it_declines(self):
        # The separation the whole change rests on, measured against the run
        # that produced the issue rather than against invented numbers.
        answers = self.repl.evaluate(
            ["swapMayDisarmTheGuns " + elm_incoming_damage(damage)
             for _, damage, _ in RUN_11_SWAPS])
        self.assertEqual(
            answers, [allowed for _, _, allowed in RUN_11_SWAPS],
            "the rule no longer separates run 11's swaps the way the issue "
            "asks: " + repr(list(zip(
                [name for name, _, _ in RUN_11_SWAPS], answers))))

    def test_any_damage_at_all_declines(self):
        # Zero, not a threshold. `runAwayIncomingDamageThreshold` answers a
        # different question -- how much punishment a hull absorbs before
        # running -- and a threshold here would license disarming under light
        # fire, which is what heavy fire starts as.
        one_hitpoint, quiet = self.repl.evaluate([
            "swapMayDisarmTheGuns " + elm_incoming_damage(1),
            "swapMayDisarmTheGuns " + elm_incoming_damage(0),
        ])
        self.assertFalse(one_hitpoint)
        self.assertTrue(quiet)

    def test_an_absent_channel_declines_rather_than_reading_as_quiet(self):
        # `Nothing` and `Just 0` are different facts and only one of them may be
        # read as "the grid is quiet". A host that cannot answer gets the answer
        # that keeps the guns firing.
        absent_empty, absent_quiet_sample = self.repl.evaluate([
            "swapMayDisarmTheGuns " + elm_incoming_damage(
                None, host_carries_the_channel=False),
            "swapMayDisarmTheGuns " + elm_incoming_damage(
                0, host_carries_the_channel=False),
        ])
        self.assertFalse(absent_empty)
        self.assertFalse(absent_quiet_sample)

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


class TheSwapDoesNotDisarmUnderFire(unittest.TestCase):
    """Where the rule is applied, as opposed to what it answers."""

    def setUp(self):
        self.source = bot_source()

    def test_the_acting_path_asks_before_it_switches_a_gun_off(self):
        """The guard's whole condition, not two substrings of it.

        Two substrings would survive the condition being neutered -- an
        `&& False`, or a `gunsSilencedTicks` bound loosened until it never
        holds -- because both fragments still appear elsewhere in the same
        function. A guard that compiles and never fires is this repo's
        signature failure, so the condition is pinned as written.
        """
        body = self.source[self.source.index(
            "ensureAmmoSuitsTargetRangeWithGuns context fight nextStep ="):]
        body = body[:body.index(
            "\n{-| Rest the mouse on a weapon module until the client shows")]
        conditions = [" ".join(line.split())
                      for line in body.split("\n") if line.strip()]
        self.assertIn(
            "else if (ammoSwap.gunsSilencedTicks < 1) "
            "&& not (swapMayDisarmTheGuns context.memory.incomingDamage) then",
            conditions)

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

    def test_the_verdict_is_abandoned_when_fire_arrives_mid_swap(self):
        body = let_binding(self.source, "fireArrivedWhileHoldingTheGuns")
        self.assertIn("gunsSilencedTicks > 0", body)
        self.assertIn("not (swapMayDisarmTheGuns incomingDamage)", body)

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


if __name__ == "__main__":
    unittest.main()
