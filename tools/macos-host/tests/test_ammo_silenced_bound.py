"""Structural guards on the ammo swap's silenced period, and what it costs.

The swap switches the ship's guns off to load a charge, and issue #34 is what
happens when that period is not bounded: run 8 sat in a hostile pocket with the
guns off, repeating one decision 298 times, and would not have recovered on its
own. The promise the code makes is

    failing to a firing gun with the wrong ammo beats failing to a silent gun

and the first three classes here check the two structural properties that promise
now rests on, rather than one branch at a time remembering to honour it.

**The counter cannot be stalled by anything the module reports.** That is the
actual defect, and it had two halves. The wait that ran for 298 readings had no
counter at all; and the counter in front of it reset whenever no gun *read* as
firing, so a weapon flickering between cycles held it at 1 forever -- run 8's log
shows "Silencing for 1 of 8" on all eight readings it appears. Issue #35 then
measured `ramp_active` returning False on a module that was switched on, so those
readings are not merely flaky, they may be meaningless. A counter that consults
them can be stopped by them.

**Nothing in the acting path waits.** Every state either acts or hands the fight
back, so there is no state that can sit still while the guns are off.

**Every counter can actually advance.** The two properties above are about what
the source *mentions*, and that turned out not to be enough: replacing the
increment with the literal `1` pins the counter at 1 forever -- run 8's exact
symptom -- while mentioning nothing forbidden. So the arithmetic is asserted
too, for all three counters in the ammo memory rather than only the one that
failed. A bound that cannot advance is indistinguishable from no bound, and that
is the whole lesson of #34.

**The last three classes are issue #157**, which is about what reaching the
deadline *costs* rather than about the deadline. Run 11 switched the whole
feature off on the sentence "the guns were switched off to load and were still
not back 21 readings later", while its own module column had read
`isInActiveState` `T` -- the gun switched on -- since reading 3 of that attempt;
run 27 did the same with the bot saying so in words, its status clause reading
`the client switched a gun back on by itself 3 of 20 readings in`.
`TheDisarmLatchAsksWhetherTheGunsCameBack` covers the narrowed verdict,
`TheDisarmGiveUpIsRetriedAfterAWarp` the unlatch and the third latch that is
deliberately *not* retried, and `TheRecordedMissionRunsTest` is the corpus those
rest on.

The pure rules there are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python, for the reason CLAUDE.md's "How a change is
verified here" gives. Everything else -- what a definition is allowed to mention,
what it evaluates to, where it is called from -- is read as text on purpose,
through a whitespace-collapsing reader so an `elm-format` pass cannot break it.

The corpus cases read the recorded mission runs and only read them; they skip
with a stated reason on a machine that has none, and they glob the runs rather
than numbering them, so a new one is read without an edit.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Everything the client says about a module's own state. The parser reads the
# first two; #35 found the rest sitting unread in the button's dict entries,
# and found the first one lying. None of them may gate the deadline.
#
# #35 has since parsed them onto the button and put four of them in the status
# line, which is the only reason this list grew rather than shrank: a field the
# log now shows every reading is a field somebody will be tempted to consult
# here, and what any of them means during a firing cycle is still unmeasured.
# `stateFromDictEntries` is the accessor all twelve arrive through, so naming it
# covers the eight not spelled out.
MODULE_STATE_READINGS = [
    "weaponIsFiring",
    "rampRotationMilli",
    "isActive",
    "isDeactivating",
    "isInActiveState",
    "effect_activating",
    "isHiliteVisible",
    "isBusy",
    "stateFromDictEntries",
    "ramp_active",
    "waitingForActiveTarget",
]

# The charge names the two sentence-rendering rules are asked about. Both are
# what `run_mission.sh` ships, so the strings a case reads back are the ones an
# operator would see.
CHARGE_NAMES = ('{ shortRangeAmmoName = "Multifrequency M"'
                ', longRangeAmmoName = "Radio M" }')

# The three ammo status clauses issue #157 turns on. The bot prints one of the
# first two on every reading an attempt is live -- `GUNS OFF` only while
# `switchOffUndoneByClient` is unset, which is what makes its count meaningful --
# and the third is the give-up that read neither.
GUNS_OFF_CLAUSE = "GUNS OFF for "
GUNS_BACK_ON_CLAUSE = "the client switched a gun back on by itself "
DISARM_GIVE_UP = "the guns were switched off to load"

# `decideActionWhenInSpace`'s answer while the ship is warping, and the log-line
# gap that separates one warp from the next. Both are `test_ammo_tooltip_retry`'s
# and are repeated rather than imported for the reason that file gives for its
# own copy of a reader: these suites own different properties of the same
# feature, and a shared helper between them is a coupling nobody wants to reason
# about later.
IN_WARP = "+ I am in warp"
EPISODE_GAP_LINES = 40

# `Top-row modules (ramp_active/isInActiveState/isDeactivating/...)`, whose
# second field is the entry #35 measured as meaning "switched on". This is the
# only instrument run 11 has: it predates the status clause that says the client
# took the guns back, so what says the guns were firing there is the client's own
# module reading beside the `GUNS OFF` print.
MODULE_COLUMN = re.compile(r"Top-row modules \([^)]*\): (\S+)\.")


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and the comments here name the halves
    deliberately left elsewhere.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def code_only(text):
    """The source with its doc comments and `--` lines dropped.

    Needed by any case counting *uses* of a name across the file: the doc
    comments here name `describeAmmoSwapGiveUp` while arguing for it, so a count
    over the raw text cannot tell a mention from a call.
    """
    return without_comments(re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL))


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def definition_body(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding.

    Bindings are separated by a blank line and the next thing at the same
    indent -- which is often the *comment* introducing the following binding,
    so the terminator is any non-space, not an identifier.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    if end is None:
        end = re.search(r"\n    in\n", rest)
    return rest[:end.start()] if end else rest


def indented_let_binding(declaration_name, name):
    """One `let` binding, sliced by indentation rather than by a blank line.

    `definition_body` above ends at the next blank line followed by something at
    the same indent, which is right for every binding that has one. This ends at
    the next non-blank line indented no further, which is right for a binding
    whose body builds a record: PRs #147 and #156 both paid for a reader that
    stopped at a record literal, and #156's assertion that the give-up hands
    `ammoSwapDisarmEndsTheSession` the client's own answer was reading text that
    ended at the record's opening brace and passed vacuously.
    """
    lines = declaration(declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^(\s*)%s =(\s|$)" % re.escape(name), line)]
    assert opens, "no let binding named %r" % name
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    return collapsed(without_comments("\n".join(lines[start:end])))


def declaration(name, source=None):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source if source is not None else bot_elm(),
                      re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def function_body(source, signature_start, next_top_level):
    start = source.index(signature_start)
    end = source.index(next_top_level, start)
    return source[start:end]


def int_constant(source, name):
    match = re.search(r"^" + name + r" : Int\n" + name + r" =\n\s+(\d+)",
                      source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


def read_log(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().split("\n")


def warp_episodes(lines):
    """Consecutive `I am in warp` lines grouped into one warp each.

    The bot re-derives its decision on every framework event, so the line is
    printed about a dozen times per reading and a warp runs for tens of readings
    -- CLAUDE.md's first warning to a newcomer, and the statistic
    `stall_watch.py` was once calibrated against by mistake.
    """
    grouped = []
    for index, line in enumerate(lines):
        if not line.startswith(IN_WARP):
            continue
        if grouped and index - grouped[-1][-1] <= EPISODE_GAP_LINES:
            grouped[-1].append(index)
        else:
            grouped.append([index])
    return grouped


class TheDeadlineCannotBeStalled(unittest.TestCase):
    """`gunsSilencedTicks` must not consult the module's own state."""

    def test_counter_mentions_no_module_state_reading(self):
        body = definition_body(bot_elm(), "gunsSilencedTicks")
        for reading in MODULE_STATE_READINGS:
            self.assertNotIn(
                reading, body,
                "gunsSilencedTicks consults " + reading + " -- a reading that "
                "#35 shows can be wrong, and #34 shows can stall the deadline")

    def test_counter_advances_from_what_the_bot_asked_for(self):
        # The one input it is allowed: whether the bot commanded a switch-off,
        # which is read from the step's own effects rather than from the client.
        body = definition_body(bot_elm(), "gunsSilencedTicks")
        self.assertIn("swapJustCommandedAGunOff", body)

    def test_the_command_is_read_from_the_step_s_effects(self):
        body = definition_body(bot_elm(), "swapJustCommandedAGunOff")
        self.assertIn("previousStepsEffects", body)
        self.assertIn("doEffectsClickModuleButton", body)

    def test_the_verdict_changing_does_not_reset_it(self):
        # A distance drifting across the deadband flips the verdict with the
        # guns still off. Resetting there would let a flickering target hold the
        # ship disarmed indefinitely.
        body = definition_body(bot_elm(), "gunsSilencedTicks")
        self.assertNotIn("verdictIsTheSameOneAsBefore", body)


class EveryCounterCanActuallyAdvance(unittest.TestCase):
    """A bound that cannot advance is indistinguishable from no bound.

    The other cases here assert what a counter is *allowed to mention*, and
    that is not enough on its own: pinning `gunsSilencedTicks` at the literal
    `1` -- exactly run 8's observed symptom, `Silencing for 1 of 8` eight times
    over -- mentions nothing forbidden and passes all of them. So these assert
    the arithmetic instead.

    Applied to all three counters in the ammo memory rather than the one that
    failed, because the shape is what shipped twice, not the instance.
    """

    # `givenUpReadingsAgo` joins them from #50. It bounds nothing -- it exists
    # so the latched give-up is printed once rather than 763 times -- but the
    # property is about the shape a counter in this record has, and a counter
    # exempted from it because it looked harmless is how the next one drifts.
    #
    # `hoverAttemptsSpent` joins them from #106, and it is a bound: it is what
    # ends the tooltip ask, where `hoverUnansweredTicks` now ends only one
    # hover. Its reset branch is an answered tooltip, which voids the evidence
    # the count is accumulating.
    COUNTERS = ["rangeVerdictTicks", "gunsSilencedTicks", "hoverUnansweredTicks",
                "hoverAttemptsSpent", "givenUpReadingsAgo"]

    def results_for(self, name):
        return branch_results(definition_body(bot_elm(), name))

    def test_every_branch_resets_holds_starts_or_increments(self):
        for name in self.COUNTERS:
            previous = "memoryBefore." + name
            allowed = {"0", "1", previous, previous + " + 1"}
            for result in self.results_for(name):
                self.assertIn(
                    result, allowed,
                    name + " has a branch evaluating to " + repr(result) +
                    " -- a counter may only reset, start, hold or increment, and "
                    "anything else is a bound whose behaviour is not obvious")

    def test_every_counter_has_a_branch_that_increments(self):
        # The assertion the suite was missing. Replacing the increment with a
        # constant leaves a counter that never reaches its threshold, which is
        # the general shape of #34 rather than the particular mechanism.
        for name in self.COUNTERS:
            self.assertIn(
                "memoryBefore." + name + " + 1", self.results_for(name),
                name + " never increments, so whatever bound reads it can "
                "never be reached")

    def test_every_counter_has_a_branch_that_resets(self):
        # Without one it would climb across unrelated verdicts and fire its
        # bound on a state that had already recovered.
        for name in self.COUNTERS:
            self.assertIn("0", self.results_for(name), name + " never resets")


def branch_results(body):
    """The value each branch of an `if`/`else if` chain evaluates to.

    Comments and blank lines are dropped, then every line that is not part of a
    condition is a result. All three counters here are single-line conditions
    with single-line results, which is what makes this reliable rather than
    clever; a counter written some other way would show up as an unrecognised
    result and fail loudly rather than pass quietly.
    """
    results = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped == "else" or (
                stripped.startswith(("if ", "else if ")) and stripped.endswith(" then")):
            continue
        results.append(stripped)
    return results


class NothingInTheActingPathWaits(unittest.TestCase):
    def test_no_wait_for_progress_while_the_guns_may_be_off(self):
        body = function_body(
            bot_elm(),
            "ensureAmmoSuitsTargetRangeWithGuns :\n    BotDecisionContext",
            "{-| Rest the mouse on a weapon module until the client shows its tooltip.")
        self.assertNotIn(
            "waitForProgressInGame", body,
            "a state in the acting path declines to hand the fight on; that is "
            "the shape issue #34 was filed for")

    def test_the_ramp_is_no_longer_a_precondition_for_loading(self):
        # weaponWillAcceptACharge waited for the ramp to go quiet, and that wait
        # is what ran for 298 readings. It is gone, and must stay gone: the load
        # is attempted and the client's refusal (#31) arbitrates.
        self.assertNotIn("weaponWillAcceptACharge", bot_elm())


class TheDangerousStateTimesOutFirst(unittest.TestCase):
    def setUp(self):
        self.source = bot_elm()

    def test_silenced_bound_is_tighter_than_the_whole_verdict_bound(self):
        silenced = int_constant(self.source, "ammoSwapSilencedGiveUpTicks")
        verdict = int_constant(self.source, "ammoSwapVerdictGiveUpTicks")
        self.assertLess(
            silenced, verdict,
            "the guns-off deadline must fire before the general one, or the "
            "ship spends the difference disarmed")

    def test_the_settle_fits_inside_the_deadline(self):
        settle = int_constant(self.source, "ammoSwapSilenceSettleTicks")
        silenced = int_constant(self.source, "ammoSwapSilencedGiveUpTicks")
        self.assertLess(settle, silenced)

    def test_reaching_the_deadline_can_still_switch_the_swap_off(self):
        # Every other failure abandons one attempt. This one can do more -- but
        # since #157 only through `ammoSwapDisarmEndsTheSession`, so what is
        # asserted here is that the session consequence is still reachable from
        # this deadline at all. Which ships it is that rule's own class below.
        self.assertIn(
            "ammoSwapSilencedGiveUpTicks",
            declaration("ammoSwapDisarmEndsTheSession"),
            "the session verdict no longer reads the deadline, so reaching it "
            "costs nothing beyond the attempt")


class TheDisarmLatchAsksWhetherTheGunsCameBack(unittest.TestCase):
    """`ammoSwapDisarmEndsTheSession`, which is issue #157.

    Run 11 switched the whole feature off with

        Ammo swap: given up -- the guns were switched off to load and were still
        not back 21 readings later.

    and on that reading its own status line carried
    `Top-row modules (...): F/T/F.` -- `isInActiveState` `True`, the gun switched
    **on** -- as it had since reading 3 of that attempt. Run 27 is the same shape
    said in words rather than read off the module column: its clause read
    `the client switched a gun back on by itself 3 of 20 readings in` and climbed
    to 18 before the give-up.

    `gunsSilencedTicks` is right to consult nothing the module says (#34), and
    that is exactly why it cannot be read as a statement about the guns. So the
    *session* consequence asks the client's own latched answer instead, while
    the attempt bound is untouched -- PR #151's shape on `lockAttempt`,
    discharging an outcome on the rule's own terms rather than retuning a bound.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(prefix="mission-disarm-latch-")
        cls.bound = int_constant(bot_elm(), "ammoSwapSilencedGiveUpTicks")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _ends(self, ticks, undone):
        return ("ammoSwapDisarmEndsTheSession { gunsSilencedTicks = %d"
                ", switchOffUndoneByClient = %s }" % (ticks, undone))

    def test_the_budget_still_ends_the_session_on_a_ship_left_disarmed(self):
        self.assertEqual(
            self.repl.evaluate([
                self._ends(self.bound + 1, "False"),
                self._ends(self.bound + 40, "False"),
                # A fixed value far past any plausible bound, so a constant that
                # simply admits everything above it is not what is being tested.
                self._ends(200, "False"),
            ]),
            [True] * 3,
            "the guns went off, the client never reported one back on, and the "
            "budget expired. That is what this latch is for")

    def test_a_ship_whose_guns_the_client_gave_back_does_not_latch(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._ends(self.bound + 1, "True"),
                "not (%s)" % self._ends(self.bound + 40, "True"),
                "not (%s)" % self._ends(200, "True"),
            ]),
            [True] * 3,
            "runs 11 and 27's shape: the budget expired on a firing ship, so "
            "the attempt is abandoned and the feature is not")

    def test_it_answers_at_both_sides_of_the_bound(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._ends(self.bound - 1, "False"),
                "not (%s)" % self._ends(self.bound, "False"),
                self._ends(self.bound + 1, "False"),
                # Fixed values either side, so a bound moved to something that
                # admits or refuses everything still fails here.
                "not (%s)" % self._ends(3, "False"),
                self._ends(60, "False"),
            ]),
            [True] * 5)
        self.assertGreater(
            self.bound, 3,
            "the fixed low value above has to sit under the shipped bound")
        self.assertLess(
            self.bound, 60,
            "and the fixed high value above has to sit over it")

    def test_the_attempt_is_still_abandoned_at_exactly_the_same_reading(self):
        # Nothing is loosened. The budget ends the attempt where it always did;
        # only what that costs afterwards is narrowed. A version that also
        # deferred the abandonment would hold the fight longer on no evidence.
        abandoned = indented_let_binding(
            "updateAmmoSwapMemoryWithChargeNames", "verdictAbandoned")
        self.assertIn(
            "ammoSwapSilencedGiveUpTicks < gunsSilencedTicks", abandoned)
        self.assertNotIn("switchOffUndoneByClient", abandoned)
        self.assertNotIn("ammoSwapDisarmEndsTheSession", abandoned)

    def test_the_session_verdict_asks_the_rule_and_compares_nothing_itself(self):
        reached = indented_let_binding(
            "updateAmmoSwapMemoryWithChargeNames", "giveUpReachedThisReading")
        self.assertIn("ammoSwapDisarmEndsTheSession", reached)
        self.assertNotIn(
            "ammoSwapSilencedGiveUpTicks <", reached,
            "one comparison, so the latch and the rule cannot disagree about "
            "when the budget expired")
        self.assertIn(
            "switchOffUndoneByClient = switchOffUndoneByClient", reached,
            "the rule has to be handed the client's own report that the guns "
            "came back -- `gunsConfirmedOff` is the same type and the opposite "
            "question, and would type-check here")

    def test_the_rule_reads_a_latch_rather_than_the_module(self):
        # #34's property has to survive this. `switchOffUndoneByClient` is
        # monotone within an attempt and cleared exactly where the counter is,
        # so unlike a live module read it cannot flicker -- and it is only ever
        # consulted to make the outcome milder.
        undone = indented_let_binding(
            "updateAmmoSwapMemoryWithChargeNames", "switchOffUndoneByClient")
        self.assertIn("memoryBefore.switchOffUndoneByClient then True", undone)
        for clearing in ("rangeVerdict == Nothing", "verdictSatisfied",
                         "memoryBefore.verdictAbandoned"):
            self.assertIn(
                clearing, undone,
                "cleared exactly where gunsSilencedTicks is, so it belongs to "
                "one attempt and cannot be inherited")
        rule = collapsed(without_comments(
            declaration("ammoSwapDisarmEndsTheSession")))
        for reading in MODULE_STATE_READINGS + [
                "readingFromGameClient", "gunsConfirmedOff"]:
            self.assertNotIn(
                reading, rule,
                "%s would make the rule a function of this reading's module "
                "state, which is the thing #34 refused" % reading)

    def test_the_sentence_no_longer_claims_readings_the_ship_was_not_disarmed(self):
        [charge, guns, crossover] = self.repl.strings([
            'describeAmmoSwapGiveUp %s ShipCarriesNeitherCharge' % CHARGE_NAMES,
            'describeAmmoSwapGiveUp %s (GunsDidNotComeBack 21)' % CHARGE_NAMES,
            'describeAmmoSwapGiveUp %s NoCrossoverDistance' % CHARGE_NAMES,
        ])
        self.assertIn("Multifrequency M", charge)
        self.assertIn("Radio M", charge)
        self.assertIn("ammo-swap-range", crossover)
        self.assertIn("21", guns)
        self.assertIn("that attempt", guns)
        self.assertNotIn(
            "still not back", guns,
            "run 11's wording said the guns were still off after a count that "
            "measures the attempt, not the silence")


class TheDisarmGiveUpIsRetriedAfterAWarp(unittest.TestCase):
    """`ammoSwapGiveUpAfterReading`: one failure no longer ends a session.

    Run 11 spent 763 decision lines reporting the swap given up after a single
    21-reading attempt. A warp means a new grid and a fresh fight, and it is a
    signal this bot already reads for the drone bookkeeping.

    **The three verdicts do not end the same way, and that is the whole of this
    class.** `ShipCarriesNeitherCharge` is a fact about the ship's hold that a
    warp cannot change. `NoCrossoverDistance` is the mission runner's third
    latch, which saxrat does not have, and it is deliberately *not* retried
    either: #106 already spends the tooltip ask one hover per warp, so the warp
    boundary is consumed at the evidence rather than at the verdict, and
    clearing it would re-latch on the very reading it was cleared on --
    `weaponTooltipAskIsGivenUp` is still true, no new hover is asked, and
    `threshold` is still `Nothing`. What that would buy is the long sentence
    reprinted once a warp.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(prefix="mission-giveup-warp-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    @staticmethod
    def _after(before, reached="Nothing", warping="False"):
        return ("ammoSwapGiveUpAfterReading { before = %s"
                ", reachedThisReading = %s, justFinishedWarping = %s }"
                % (before, reached, warping))

    def test_only_the_disarm_verdict_is_retryable(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapGiveUpSurvivesAWarp ShipCarriesNeitherCharge",
                "ammoSwapGiveUpSurvivesAWarp NoCrossoverDistance",
                "not (ammoSwapGiveUpSurvivesAWarp (GunsDidNotComeBack 21))",
                "not (ammoSwapGiveUpSurvivesAWarp (GunsDidNotComeBack 200))",
            ]),
            [True] * 4,
            "a hold carrying neither charge is not something a warp changes, "
            "and neither is an ask #106 already spread across six warps")

    def test_the_disarm_verdict_is_cleared_by_a_warp_and_by_nothing_else(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % self._after(
                    "Just (GunsDidNotComeBack 21)", warping="True"),
                "%s == Just (GunsDidNotComeBack 21)" % self._after(
                    "Just (GunsDidNotComeBack 21)", warping="False"),
            ]),
            [True, True],
            "the latch stands on every reading that is not the end of a warp, "
            "so it is not simply absent")

    def test_the_two_permanent_verdicts_survive_a_warp(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just ShipCarriesNeitherCharge" % self._after(
                    "Just ShipCarriesNeitherCharge", warping="True"),
                "%s == Just NoCrossoverDistance" % self._after(
                    "Just NoCrossoverDistance", warping="True"),
            ]),
            [True, True])

    def test_a_verdict_reached_on_a_warp_reading_is_not_cleared_by_it(self):
        # The reading a swap is given up on can itself be the reading a warp
        # ends. Clearing there would drop a verdict formed after the warp, and
        # the attempt would have been spent for nothing.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just (GunsDidNotComeBack 21)" % self._after(
                    "Nothing", reached="Just (GunsDidNotComeBack 21)",
                    warping="True"),
                "%s == Nothing" % self._after("Nothing", warping="True"),
            ]),
            [True, True])

    def test_folded_over_a_session_the_latch_returns_once_per_warp(self):
        # A run's shape rather than one reading: give up, hold it across a
        # site's worth of readings, come back on the warp, and do it again.
        readings = (["False"] * 8 + ["True"] + ["False"] * 8
                    + ["True"] + ["False"])
        fold = (
            "List.foldl (\\warping before -> ammoSwapGiveUpAfterReading "
            "{ before = before, reachedThisReading = "
            "(if before == Nothing then Just (GunsDidNotComeBack 21) "
            "else Nothing), justFinishedWarping = warping }) "
            "(Just (GunsDidNotComeBack 21)) [ %s ]" % ", ".join(readings))
        self.assertEqual(
            self.repl.evaluate(["%s == Just (GunsDidNotComeBack 21)" % fold]),
            [True],
            "each warp clears it and the very next reading latches it again, "
            "so the session ends holding one -- retried, not abandoned")

    def test_the_status_line_says_which_of_the_three_it_is(self):
        # Run 11's operator read one wording for 763 decision lines, about a
        # verdict a warp would now have cleared, with no way to know which.
        clause = collapsed(without_comments(declaration("describeAmmoSwapState")))
        self.assertIn("ammoSwapGiveUpSurvivesAWarp giveUp", clause)
        self.assertIn('"off for this session"', clause)
        self.assertIn('"off until the next warp"', clause)

    def test_the_decision_line_and_the_status_line_share_one_sentence(self):
        for reader in ("describeAmmoSwapState", "ensureAmmoSuitsTargetRange"):
            self.assertIn(
                "describeAmmoSwapGiveUp",
                collapsed(without_comments(declaration(reader))),
                "%s has to render the case rather than carry its own wording, "
                "or the two can describe one verdict differently" % reader)
        self.assertEqual(
            code_only(bot_elm()).count("describeAmmoSwapGiveUp"), 4,
            "the two readers above and the definition's own two lines, and "
            "nothing else")

    def test_nothing_stores_the_sentence_beside_the_case(self):
        # A `Maybe String` was the old shape and it is what let the give-up go
        # on claiming something the memory beside it already contradicted. The
        # sentence is derived, every time. `type alias` has no annotation for
        # `declaration` to key on.
        self.assertIn("givenUp : Maybe AmmoSwapGiveUp", collapsed(bot_elm()))
        reached = indented_let_binding(
            "updateAmmoSwapMemoryWithChargeNames", "giveUpReachedThisReading")
        self.assertNotIn(
            '"', reached,
            "a string literal here is a sentence stored in memory, which is "
            "the shape this change exists to leave")


class TheWarpTheSwapIsRetriedAcross(unittest.TestCase):
    """Where the unlatch is wired in, read out of the source."""

    def setUp(self):
        self.source = bot_elm()

    def test_the_memory_update_runs_on_every_reading(self):
        # In `updateMemoryForNewReadingFromGame`, which is the only place that
        # can write memory and the one place that never sees the decision -- so
        # a warp cannot be missed because the tree was held somewhere else.
        update = collapsed(without_comments(
            declaration("updateMemoryForNewReadingFromGame", self.source)))
        self.assertIn(
            "ammoSwap = updateAmmoSwapMemory context incomingDamageNow "
            "{ justFinishedWarping = weJustFinishedWarping } "
            "botMemoryBefore.ammoSwap", update)

    def test_the_warp_is_the_one_already_defined(self):
        """One definition of "a site ended", and it is the shared rule now.

        The property this protects is #154's and is unchanged: the retry uses
        the warp notion that already exists rather than defining a second,
        subtly different one, so it and the drone abandonment cannot come to
        disagree about when a site ended. What changed is *which* notion that
        is. This quoted #194's condition, because when #154 was written that
        was the only shape available -- and #205 then established it could
        never answer `True` at the end of a warp, so the retry was reading a
        value that never moved.

        Re-pointed rather than relaxed. A substring that would pass against
        either shape would stop catching the thing the case is named for, and
        the property is worth more now than it was: `warpJustEnded` is shared
        across four apps, so a second definition introduced here would be a
        divergence from all of them rather than from one binding. Same text
        `test_saxrat_ammo_swap` asserts of saxrat's copy, which #201 re-pointed
        for the same reason.
        """
        update = collapsed(without_comments(
            declaration("updateMemoryForNewReadingFromGame", self.source)))
        self.assertIn(
            "weJustFinishedWarping = warpJustEnded "
            "{ warpingLastReading = botMemoryBefore.shipWarpingInLastReading "
            ", readingNow = context.readingFromGameClient }", update)
        self.assertEqual(
            code_only(self.source).count("weJustFinishedWarping ="), 1,
            "one definition, read by both the drone bookkeeping and the swap")


class TheRecordedMissionRunsTest(unittest.TestCase):
    """The recorded mission runs, asked what they actually did.

    Asserted as *relations* and as existence claims rather than as counts, so a
    corpus that grows -- or a later run that behaves differently -- cannot turn
    a true claim red. Runs are globbed rather than numbered, so a run 38 is read
    without an edit.
    """

    @classmethod
    def setUpClass(cls):
        logs = sorted(glob.glob(
            os.path.join(EVE_BOT_LOGS, "mission_run*.log")))
        if not logs:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what those runs did "
                "cannot be consulted here")

        cls.runs = []
        for path in logs:
            lines = read_log(path)
            run = {"ammo_clauses": 0, "guns_off": 0, "guns_back_on": 0,
                   "disarm_give_ups": 0, "worst_guns_off": 0,
                   "guns_off_with_the_module_reading_on": 0,
                   "warp_episodes": len(warp_episodes(lines))}
            module_column = None
            for line in lines:
                seen = MODULE_COLUMN.search(line)
                if seen:
                    module_column = seen.group(1)
                if DISARM_GIVE_UP in line:
                    run["disarm_give_ups"] += 1
                if GUNS_BACK_ON_CLAUSE in line:
                    run["guns_back_on"] += 1
                if "Ammo swap:" in line:
                    run["ammo_clauses"] += 1
                count = re.search(re.escape(GUNS_OFF_CLAUSE) + r"(\d+) of", line)
                if not count:
                    continue
                run["guns_off"] += 1
                run["worst_guns_off"] = max(
                    run["worst_guns_off"], int(count.group(1)))
                # The second field is `isInActiveState`, which #35 measured as
                # meaning "switched on". Run 11 predates the clause that says
                # the client took the guns back, so this is the only instrument
                # that speaks for it.
                fields = (module_column or "").split("/")
                if len(fields) > 1 and fields[1] == "T":
                    run["guns_off_with_the_module_reading_on"] += 1
            cls.runs.append((os.path.basename(path), run))

        cls.swapping = [(name, run) for name, run in cls.runs
                        if run["ammo_clauses"]]
        cls.gave_up = [(name, run) for name, run in cls.swapping
                       if run["disarm_give_ups"]]

    def test_the_swap_flies_on_this_bot_and_reaches_its_disarm(self):
        """A lower bound, so more runs can only make it truer.

        A run carrying an ammo clause is a run with the swap configured; one
        carrying `GUNS OFF` is a run whose swap got past the disarm gate and
        actually switched a gun off.
        """
        self.assertTrue(
            self.swapping,
            "no recorded run carries an ammo clause at all, so this bot's own "
            "corpus cannot say anything about the swap")
        self.assertTrue(
            [name for name, run in self.swapping if run["guns_off"]],
            "a swap that never reaches GUNS OFF is one the disarm gate stops, "
            "and none of the claims below would be about anything")

    def test_a_run_gave_up_while_its_own_instruments_said_the_guns_were_firing(self):
        """Issue #157's finding, and the one the narrowed latch rests on.

        Either the swap's own status clause had gone over to reporting the guns
        back on, or -- for a run predating that clause -- the client's module
        column read `isInActiveState` `T` on the readings the give-up was
        counting. Run 27 is the first, run 11 the second.
        """
        misread = [name for name, run in self.gave_up
                   if run["guns_back_on"]
                   or run["guns_off_with_the_module_reading_on"]]
        self.assertTrue(
            misread,
            "no recorded run reached the disarm give-up while the bot's own "
            "readings said the guns were firing, which is the observation "
            "#157 is filed on -- runs 11 and 27 are the ones that did")

    def test_the_shape_the_latch_is_kept_for_is_reachable_here(self):
        """Why this narrows the latch rather than removing it.

        `GUNS OFF for N` is printed only while `switchOffUndoneByClient` is
        unset, so a high N is an attempt the narrowed rule would still latch on.
        Runs have carried it to the budget itself -- one reading short of the
        give-up -- so removing the latch would leave a ship that really is being
        held disarmed with nothing to stop the next attempt.
        """
        bound = int_constant(bot_elm(), "ammoSwapSilencedGiveUpTicks")
        deep = [name for name, run in self.swapping
                if bound // 2 <= run["worst_guns_off"]]
        self.assertTrue(
            deep,
            "no recorded run held the counter to half the budget with the "
            "client never reporting a gun back on, so the case this latch is "
            "kept for would be unreachable and removing it would be free")

    def test_a_warp_offers_far_more_retries_than_a_session_does(self):
        """The cost of unlatching on a warp, measured rather than asserted.

        A swap failing for a persistent reason retries once per warp instead of
        once per session. Stated as the relation that makes it bounded and
        plural: every run that gave up warped many times more often than it gave
        up, so the retry is tens of attempts over a long session and not one,
        and not thousands either.
        """
        self.assertTrue(self.gave_up, "no give-up recorded to size this against")
        for name, run in self.gave_up:
            self.assertGreater(
                run["warp_episodes"], 2,
                "%s gave up on the swap and warped almost never, so a per-warp "
                "retry would not be a retry at all" % name)


if __name__ == "__main__":
    unittest.main()
