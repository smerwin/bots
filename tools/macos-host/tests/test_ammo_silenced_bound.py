"""Structural guards on the ammo swap's silenced period.

The swap switches the ship's guns off to load a charge, and issue #34 is what
happens when that period is not bounded: run 8 sat in a hostile pocket with the
guns off, repeating one decision 298 times, and would not have recovered on its
own. The promise the code makes is

    failing to a firing gun with the wrong ammo beats failing to a silent gun

and these cases check the two structural properties that promise now rests on,
rather than one branch at a time remembering to honour it.

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

These read `Bot.elm` as text on purpose. The properties are about the shape of
the code -- what a definition is allowed to mention, what it is allowed to
evaluate to, what a function is allowed to call -- and that is not observable
from its behaviour on any one input.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

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


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


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

    def test_reaching_the_deadline_switches_the_swap_off_for_the_session(self):
        # Every other failure abandons one attempt. This one is different: the
        # ship was disarmed and did not recover on schedule, so it is not
        # retried.
        body = definition_body(self.source, "givenUp")
        self.assertIn("ammoSwapSilencedGiveUpTicks", body)


if __name__ == "__main__":
    unittest.main()
