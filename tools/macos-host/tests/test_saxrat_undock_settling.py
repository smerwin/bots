"""One click undocks; the second one, a second later, docks again.

`test_abort_undock_button_parse` pins the *parser* half of this button: the
undock slot carries three labels and `parseStationWindowFromUITreeRoot` blanks
`undockButton` for the two that abort. That work is correct and this file does
not revisit it. saxrat run 20 carried it and still never left the station.

What run 20 shows is the other half. Across 405 readings it dispatched **298**
undock clicks and reached warp **zero** times, and the dispatches come in pairs
inside a single tick -- substeps `.2` and `.5`, three steps apart. The parse is
not wrong on either: the first click starts the undock, and a second or two later
the second lands on the same screen point, which by then reads "Abort Undock".
The client says so itself:

    05:39:27 (None)   Undocking from Amarr VIII (Oris) ... to Amarr solar system.
    05:39:36 (notify) Can't do that while undocking. You should be squeezed out in 2 seconds.
    05:39:41 (notify) Docking operation already in progress. Estimated time left: 10 seconds.

Note what the client does *not* write: there is no line for undock being
*clicked*, only for an undock that *starts*. So the whole of a 405-reading loop
is three lines, and none of them is the press that caused it.

This is `moduleButtonClickSettlingSteps`' failure on a more expensive button --
"a second click, which turned it _off_", except that here it puts the ship back
in the station. `undockClickedStepsAgo` is the same shape: a window over the
button's own region, suppressing the re-click and nothing else.

The cases below execute the rule rather than reading it -- which is why it takes
a list of effects and a region rather than a `BotDecisionContext`, the shape
CLAUDE.md records as checkable only by eye. The corpus half is asserted as
relations over whatever `saxrat_run*.log` this machine has, so a new run cannot
turn a true claim red.
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, ElmRepl, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SAXRAT_DIR, body_of, collapsed, source_of)

# The undock button as the live client rendered it while run 20 was looping:
# canvas region, and the point the host clicked on every one of those 298
# dispatches. Real numbers rather than invented ones, so a case that passes is
# a case about the button this bot actually presses.
REGION = {"x": 1616, "y": 278, "width": 270, "height": 40}
INSIDE = (1751, 298)
OUTSIDE = (100, 100)

# The gap between the two dispatches in run 20's own ticks. The window has to
# clear it, and a bound at or below it is the loop restored.
OBSERVED_INTRA_TICK_GAP = 3

# `lastStepsEffects` is `List.take 10`, so ten is the whole stored history.
# A window of ten is "as long as we can see" rather than a bound -- the very
# margin BotFrameworkSeparatingMemory's own comment records the original
# version lacking.
FRAMEWORK_HISTORY = 10

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.ParseUserInterface",
    # `Bot exposing (..)` does not re-export another module's constructors, and
    # these cases build real effect values rather than describing them.
    "import Common.EffectOnWindow as E",
)


def region_literal(region):
    return "{ x = %(x)d, y = %(y)d, width = %(width)d, height = %(height)d }" % region


def click(point, button="E.MouseButtonLeft"):
    """The effects one real click dispatches, built by the client's own helper."""
    return "E.effectsMouseClickAtLocation %s { x = %d, y = %d }" % (
        button, point[0], point[1])


def history(*steps):
    """Newest step first, which is the order `previousStepsEffects` is in."""
    return "[ %s ]" % ", ".join(steps)


def nothing_at(steps_back, point=INSIDE):
    """A history whose only click sits `steps_back` steps behind this one."""
    return history(*(["[]"] * (steps_back - 1) + [click(point)]))


class UndockSettlingRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-undock-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super(UndockSettlingRepl, self).__init__(**kwargs)


class RuleRepl(object):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(UndockSettlingRepl)
        cls.region = region_literal(REGION)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def rule(self, steps):
        return "undockClickedStepsAgo %s %s" % (steps, self.region)


class TheWindowCoversTheSecondDispatch(RuleRepl, unittest.TestCase):
    """The bound, at its edges and against fixed values either side.

    A case that only asks about `constant - 1` and `constant` passes for *any*
    constant, including one that admits everything -- the hole four of #120's
    cases had. So the fixed values are asserted too.
    """

    def test_the_window_clears_the_observed_gap(self):
        self.assertTrue(
            self.repl.evaluate(
                ["undockClickSettlingSteps > %d" % OBSERVED_INTRA_TICK_GAP])[0],
            "a window at or below run 20's three-step gap does not suppress the "
            "second dispatch, which is the loop restored")

    def test_the_window_is_a_bound_and_not_the_whole_history(self):
        self.assertTrue(
            self.repl.evaluate(
                ["undockClickSettlingSteps < %d" % FRAMEWORK_HISTORY])[0],
            "a window equal to the stored history is 'as long as we can see', "
            "with no margin to distinguish a bound from the storage limit")

    def test_a_click_at_the_last_covered_step_still_suppresses(self):
        answers = self.repl.evaluate([
            "undockClickedStepsAgo %s %s == Just undockClickSettlingSteps"
            % ("(List.repeat (undockClickSettlingSteps - 1) [] ++ [ %s ])"
               % click(INSIDE), self.region),
        ])
        self.assertTrue(answers[0])

    def test_a_click_one_step_past_the_window_does_not(self):
        answers = self.repl.evaluate([
            "undockClickedStepsAgo %s %s == Nothing"
            % ("(List.repeat undockClickSettlingSteps [] ++ [ %s ])"
               % click(INSIDE), self.region),
        ])
        self.assertTrue(answers[0])

    def test_fixed_values_either_side_of_the_boundary(self):
        answers = self.repl.evaluate([
            "%s == Just %d" % (self.rule(nothing_at(4)), 4),
            "%s == Nothing" % self.rule(nothing_at(20)),
        ])
        self.assertEqual([True, True], answers)


class TheRuleAnswersAboutThisButton(RuleRepl, unittest.TestCase):
    def test_no_history_is_no_suppression(self):
        self.assertTrue(self.repl.evaluate(["%s == Nothing" % self.rule("[]")])[0])

    def test_a_click_on_the_previous_step_is_one_step_ago(self):
        self.assertTrue(
            self.repl.evaluate(
                ["%s == Just 1" % self.rule(history(click(INSIDE)))])[0],
            "the count an operator reads is 1-based, so 'Just 0' would print "
            "'I clicked undock 0 step(s) ago'")

    def test_run_20s_own_gap_is_reported_as_three(self):
        self.assertTrue(
            self.repl.evaluate([
                "%s == Just %d"
                % (self.rule(nothing_at(OBSERVED_INTRA_TICK_GAP)),
                   OBSERVED_INTRA_TICK_GAP)])[0])

    def test_clicks_elsewhere_do_not_suppress(self):
        self.assertTrue(
            self.repl.evaluate([
                "%s == Nothing"
                % self.rule(history(click(OUTSIDE), click(OUTSIDE)))])[0],
            "a window keyed on the step rather than on the button would stop "
            "the bot undocking after any click at all")

    def test_a_right_click_is_not_this_click(self):
        self.assertTrue(
            self.repl.evaluate([
                "%s == Nothing"
                % self.rule(history(click(INSIDE, "E.MouseButtonRight")))])[0],
            "the cascade right-clicks all over the client; only the left click "
            "presses this button")

    def test_the_nearest_click_wins_when_there_are_several(self):
        self.assertTrue(
            self.repl.evaluate([
                "%s == Just 1"
                % self.rule(history(click(INSIDE), "[]", click(INSIDE)))])[0])

    def test_the_region_is_grown_so_an_edge_click_counts(self):
        edge = (REGION["x"], REGION["y"])
        self.assertTrue(
            self.repl.evaluate(
                ["%s == Just 1" % self.rule(history(click(edge)))])[0])


class TheDecisionConsultsTheRule(unittest.TestCase):
    """The wiring, read from the source -- the branch itself needs a context."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(body_of(cls.source, "undockUsingStationWindow"))

    def test_the_click_is_gated_on_the_rule(self):
        self.assertIn("undockClickedStepsAgo context.previousStepsEffects", self.branch)

    def test_the_gate_waits_rather_than_clicking(self):
        suppressed = self.branch.split("undockClickedStepsAgo")[1]
        self.assertIn("waitForProgressInGame", suppressed.split("Nothing ->")[0])

    def test_the_suppressed_branch_says_why(self):
        self.assertIn("would abort the undock", self.branch)

    def test_the_abort_button_still_wins_on_its_own(self):
        self.assertIn("I see we are already undocking.", self.branch)

    def test_the_rule_takes_plain_values_so_it_can_be_executed(self):
        signature = collapsed(body_of(self.source, "undockClickedStepsAgo"))
        self.assertNotIn("BotDecisionContext", signature)
        self.assertIn("List (List EffectOnWindow.EffectOnWindowStruct)", signature)


def saxrat_runs():
    """Whatever this machine has, with `recorded_runs`' three-way discipline."""
    found = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
    if not found:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
            "can say about the undock click rate cannot be consulted here")
    return found


def dispatches_per_tick(path):
    """`{tick: dispatches}` for the steps that decided to click undock."""
    ticks = {}
    tick = None
    with open(path, errors="replace") as handle:
        for line in handle:
            step = re.match(r"^# \[(\d+)\.\d+\]", line)
            if step:
                tick = step.group(1)
                ticks.setdefault(tick, [0, False])
            elif tick is None:
                continue
            elif "Click on the button to undock" in line:
                ticks[tick][1] = True
            elif "send-effects" in line:
                ticks[tick][0] += 1
    return {tick: count for tick, (count, clicked) in ticks.items() if clicked}


def carries_the_suppression(path):
    with open(path, errors="replace") as handle:
        return "would abort the undock" in handle.read()


class TheCorpusShowsTheShapeBeingFixed(unittest.TestCase):
    def test_some_run_dispatched_twice_in_one_tick_while_deciding_to_undock(self):
        doubled = {}
        for path in saxrat_runs():
            worst = max(list(dispatches_per_tick(path).values()) or [0])
            if worst > 1:
                doubled[os.path.basename(path)] = worst
        self.assertTrue(
            doubled,
            "no recorded saxrat run dispatches more than once in a tick while "
            "deciding to undock -- the defect this rule exists for is not in "
            "the corpus, so the corpus can no longer justify the rule")

    def test_a_run_that_suppressed_never_doubled(self):
        """The fix, where a run carries it. Silent where none does yet."""
        carried = [path for path in saxrat_runs() if carries_the_suppression(path)]
        if not carried:
            raise unittest.SkipTest(
                "no recorded run carries the suppression wording yet")
        for path in carried:
            worst = max(list(dispatches_per_tick(path).values()) or [0])
            self.assertLessEqual(
                worst, 1,
                "%s carries the settling window and still dispatched %d clicks "
                "in one tick while deciding to undock"
                % (os.path.basename(path), worst))


if __name__ == "__main__":
    unittest.main()
