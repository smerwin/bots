"""Tests for saxrat working an acceleration gate before warping to a site, and
for the gate branch handing the reading back rather than parking the session.

`pickAnotherAnomalyOrLeave` asked `warpToOpportunitySiteIfAvailable` first and
`activateAccelerationGateIfPresent` only where that answered `Nothing` -- and the
first is a whole-tree text search for a "Warp to Site" button, which the
Opportunities panel goes on drawing after the ship has arrived. So the gate
branch was unreachable inside exactly the multi-pocket sites it exists to follow,
and the site was warped to again instead of being worked through.

**The crux is whether the reading can tell "an opportunity exists" from "the ship
still needs to go there", and it can -- off the grid rather than off the panel.**
The button is identical in both states and the client answers a stale click with
nothing at all, so no reading of the panel separates them. An acceleration gate
does: gates exist only inside sites, so one on the overview means the ship has
already arrived somewhere. Every recorded episode agrees, and the cases below
recount it from `~/eve-bot-logs`:

  - three opportunity stretches began with a gate already in reach and **none
    ever produced a warp** -- run 5's ran 3,458 readings, clicking one screen
    position 3,460 times, and ended only when a person warped the ship by hand;
  - the two that began with no gate in reach were in warp within three readings;
  - **the client said nothing on any of those 3,460 clicks**, which is what rules
    out asking it instead of the grid.

Three things follow, and each has cases below:

  - `siteProgressStep` is the ordering, as a pure rule over a record: the gate
    branch first, then a "Warp to Site" **only where no gate is in reach**, then
    the probe-scan hunt loop;
  - the in-range gate branch answers `Nothing` on its give-up instead of
    `askForHelpToGetUnstuck`, so the caller's fallbacks run -- with the give-up
    moved into the status line, since a `Nothing` cannot carry a decision line;
  - `gateRefusesThisShipTicks` stays at 40, on the mission runner's corpus rather
    than on the saxrat peaks #148 cited. Those were counted on proximity under
    the shadowing this change removes, so they say nothing about readings spent
    asking. Where the branch is genuinely reachable, a gate that opens is taken
    within 0 to 15 readings of coming into reach and a gate that does not runs to
    a count more than four times the bound.

**#200 replaced the search with a parse and the ordering is unchanged.**
`warpToOpportunitySiteIfAvailable` now reads the tracker's own travel widget and
its label, so the branch declines a `Warping` of its own accord -- but a gate on
the grid still outranks it, because that ordering is a claim about which work
comes first rather than about what a search can tell. The one case here that
asserted the search's *inability* moved with the code and says the bare panel
text is no longer read at all; everything else stands as it was, including all
of the corpus.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the readings the search is asked about go through the
real `EveOnline.ParseUserInterface`. The ordering itself is not an expression, so
it is read out of the source through a whitespace-collapsing reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl, recorded_runs
from test_saxrat_gate_panel_button import (
    ACTIVATE_BUTTON, GATE_NAME, GateRepl, read_log, reading, saxrat_runs,
    selected_item_window)
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, body_of, collapsed, label, node, source_of)

# The client's own text on the Opportunities panel, which is all the whole-tree
# search has to go on.
WARP_TO_SITE = "Warp to Site"

# The decision line the shadowed branch printed, and the one that means the ship
# is on its way somewhere.
OPPORTUNITY_LINE = "opportunity -- warp there"
IN_WARP_LINE = "HOOOOONK in warp"


def warp_to_site_button(text=WARP_TO_SITE):
    """The panel's button, as the whole-tree text search will find it.

    `findUiElementWithText` reads `getAllContainedDisplayTextsWithRegion`, so
    what it needs is a node carrying the text and a display region -- which is
    exactly what it gets on a live client, and exactly why it cannot tell a
    button that is still offered from one that has been taken.
    """
    return node("OpportunitiesPanel", {}, [label(text, (0, 0, 120, 16))],
                region=(40, 300, 200, 120))


def without_line_comments(text):
    """A declaration with its whole-line comments dropped.

    What the give-up branch does and what its comment *says it used to do* are
    different claims, and the comment names `askForHelpToGetUnstuck` to explain
    why it no longer answers it -- so a case asking what the code does has to
    read past the prose. Only whole-line comments go: `--` also occurs inside
    this file's decision strings, and those are code.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("--"))


def let_binding_of(source, name):
    """One `let` binding: its own lines, and none of its neighbours'.

    `body_of` reads top-level declarations and `pickAnotherAnomalyOrLeave` is
    not one; it is a binding of a `let` inside `decideNextActionWhenInSpace`.

    **It ends at the next line indented no further than the binding's own name**
    -- the following binding, or the `in` -- rather than at the first `in` in
    the file. Reading to the `in` was the first version and a mutation walked
    straight through it: moving the real ordering into a second binding and
    leaving the old nesting under this name passed every case here, because the
    text asserted on still held both. Asserted to have matched rather than
    silently returning nothing, since a reader that finds nothing makes every
    case over it pass.
    """
    lines = source.splitlines()
    opening = re.compile(r"^(\s+)%s =$" % re.escape(name))
    for index, line in enumerate(lines):
        match = opening.match(line)
        if not match:
            continue
        indent = len(match.group(1))
        body = []
        for following in lines[index + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        return collapsed("\n".join(body))
    raise AssertionError("no let binding named %r" % name)


class TheOrderingRuleTest(unittest.TestCase):
    """`siteProgressStep`, executed at every combination of its three inputs.

    Asked as three equalities per case rather than one, so a rule that answered
    two things at once -- or none -- would fail rather than pass on the one
    constructor a case happened to name.
    """

    STEPS = ("WorkTheAccelerationGate", "WarpToTheOpportunitySite",
             "HuntWithTheProbeScanner")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    def step(self, gate_step, warp_offered, gate_in_reach):
        expression = (
            "siteProgressStep { gateBranchOffersAStep = %s"
            ", warpToSiteIsOffered = %s, gateWithinReach = %s }" % (
                "True" if gate_step else "False",
                "True" if warp_offered else "False",
                "True" if gate_in_reach else "False"))
        answers = self.repl.evaluate(
            ["(%s) == %s" % (expression, step) for step in self.STEPS])
        chosen = [step for step, yes in zip(self.STEPS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one step for %s, got %s" % (expression, chosen))
        return chosen[0]

    def test_the_gate_is_worked_whenever_it_has_a_step(self):
        """Whatever the panel is offering, and wherever the gate is.

        This is the ordering #147 asks for: a gate on the grid is the work in
        front of the ship, and the site the button names will still be offered
        afterwards -- the panel is persistent, so taking the gate costs a delay
        rather than an opportunity.
        """
        for warp_offered in (True, False):
            for gate_in_reach in (True, False):
                self.assertEqual(
                    self.step(True, warp_offered, gate_in_reach),
                    "WorkTheAccelerationGate",
                    "warp_offered=%s gate_in_reach=%s"
                    % (warp_offered, gate_in_reach))

    def test_a_site_is_warped_to_where_no_gate_is_in_reach(self):
        """The state both recorded warps that worked were taken from."""
        self.assertEqual(self.step(False, True, False),
                         "WarpToTheOpportunitySite")

    def test_a_button_offered_beside_a_gate_in_reach_is_not_a_warp(self):
        """Run 5's state, and the whole of the measurement.

        The gate branch answers `Nothing` once it has given up, so without this
        clause the very next reading falls into the click that achieved nothing
        for 3,458 readings. Reaching the scanner instead is the recovery run 4
        eventually made on its own.
        """
        self.assertEqual(self.step(False, True, True),
                         "HuntWithTheProbeScanner")

    def test_nothing_offered_is_the_hunt_loop(self):
        for gate_in_reach in (True, False):
            self.assertEqual(self.step(False, False, gate_in_reach),
                             "HuntWithTheProbeScanner",
                             "gate_in_reach=%s" % gate_in_reach)

    def test_the_gate_outranks_the_warp_where_both_are_available(self):
        """Stated as the comparison rather than as one answer.

        A rule that had merely dropped the warp branch would pass every case
        above; what this asks is that the same inputs answer differently with
        and without a gate step, which only an ordering can do.
        """
        self.assertEqual(self.step(True, True, False),
                         "WorkTheAccelerationGate")
        self.assertEqual(self.step(False, True, False),
                         "WarpToTheOpportunitySite")


class TheWiringTest(unittest.TestCase):
    """What `siteProgressStepOrElse` does with the rule's answer.

    Not an expression, and the failure most worth pinning is a swap: two arms
    that each run a branch, wired to the wrong one, would satisfy every case
    over the rule itself.

    This read used to be `let_binding_of(source, "pickAnotherAnomalyOrLeave")`,
    which is where the dispatch lived when it was bound inside the probe-scanner
    arm. #204 moved it out to a declaration both arms call, because a shut
    scanner window made the gate and the warp unreachable; the assertions below
    are the same ones, following the code they pin.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.binding = collapsed(without_line_comments(
            body_of(cls.source, "siteProgressStepOrElse")))

    def test_the_choice_is_made_through_the_rule(self):
        self.assertIn("case siteProgressStep {", self.binding)

    def test_the_gate_branch_is_what_the_gate_answer_runs(self):
        self.assertRegex(
            self.binding,
            r"WorkTheAccelerationGate -> accelerationGateStep \|> Maybe\.withDefault")

    def test_the_warp_branch_is_what_the_warp_answer_runs(self):
        self.assertRegex(
            self.binding,
            r"WarpToTheOpportunitySite -> opportunityWarpStep \|> Maybe\.withDefault")

    def test_the_two_steps_are_the_branches_they_are_named_for(self):
        """So a swap has to be visible here rather than hiding in a name."""
        let_block = collapsed(self.source)
        self.assertIn(
            "accelerationGateStep = activateAccelerationGateIfPresent context",
            let_block)
        self.assertIn(
            "opportunityWarpStep = warpToOpportunitySiteIfAvailable"
            " context.readingFromGameClient", let_block)

    def test_the_reach_input_is_the_shared_rule(self):
        """One definition of "a gate is close enough to use", not a second one.

        `accelerationGateIsWithinReach` is what the counter and the propulsion
        rule already read; a copy written for this record could drift from them
        silently, and the whole ordering rests on that answer.
        """
        self.assertIn(
            "gateWithinReach = accelerationGateIsWithinReach"
            " context.readingFromGameClient", self.binding)

    def test_the_old_nesting_is_gone(self):
        """The shadowing itself, which is what a revert would restore."""
        self.assertNotIn(
            "warpToOpportunitySiteIfAvailable context.readingFromGameClient"
            " |> Maybe.withDefault ( activateAccelerationGateIfPresent",
            self.binding)

    def test_the_hunt_loop_is_still_the_last_resort(self):
        """The floor is the caller's, and the scanner arm still supplies its own.

        Split in two because the answer moved: the rule's last resort is now
        whatever the caller passed, and it is the probe-scanner call site that
        makes that the scan results. Asserting only the first half would pass
        while the scanner arm quietly fell back to something else.
        """
        self.assertIn("HuntWithTheProbeScanner -> ifNeither", self.binding)
        self.assertIn(
            "siteProgressStepOrElse context pickAnotherAnomalyOrLeaveViaScanResults",
            collapsed(self.source))

    def test_both_arms_of_the_probe_window_split_reach_the_rule(self):
        """#204: the defect was that only one of them could.

        `decideNextActionWhenInSpace` splits on `probeScannerWindow`, and the
        dispatch used to be bound inside the `Just` arm -- so a shut window made
        a gate on grid and a "Warp to Site" on offer both unreachable. Two call
        sites is the fix; one is the bug restored.
        """
        whole = collapsed(self.source)
        self.assertIn(
            "siteProgressStepOrElse context pickAnotherAnomalyOrLeaveViaScanResults",
            whole, "the arm with a scanner must go through the rule")
        self.assertIn(
            "siteProgressStepOrElse context (jumpToNextSystem context)", whole,
            "the arm without a scanner must go through it too, and fall back to"
            " leaving the system")

    def test_the_arm_without_a_scanner_says_its_clock_rather_than_a_number(self):
        """The literal `600` matched `anomalyWaitTimeSeconds`' default by luck.

        There is no anomaly memory to age on that arm -- it is filed under the ID
        the scanner gives -- so what the branch means is "the wait is already
        over", and it now says that in terms of the setting rather than in a
        number that stops meaning it the moment an operator changes one.
        """
        whole = collapsed(self.source)
        self.assertIn(
            "{ arrivalInAnomalyAgeSeconds ="
            " context.eventContext.botSettings.anomalyWaitTimeSeconds }", whole)
        self.assertNotIn("{ arrivalInAnomalyAgeSeconds = 600 }", whole)


class TheGiveUpHandsTheReadingBackTest(unittest.TestCase):
    """The half without which the new ordering swaps one shadow for another.

    `activateAccelerationGateIfPresent` used to answer `Just askForHelpToGetUnstuck`
    on its give-up, which dispatches nothing and waits -- run 4 spent 238 readings
    and the rest of its session that way. Asked first, that would shadow the warp
    branch permanently rather than being shadowed by it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(without_line_comments(
            body_of(cls.source, "activateAccelerationGateIfPresent")))

    def test_the_give_up_answers_nothing(self):
        self.assertIn("GiveUpOnThisGate -> Nothing", self.branch)

    def test_the_branch_no_longer_asks_for_help(self):
        """The whole point: an alarm leaves every other branch as starved."""
        self.assertNotIn("askForHelpToGetUnstuck", self.branch)

    def test_the_other_three_answers_still_act(self):
        """Handing the reading back is the give-up's answer and no other's."""
        for step in ("SelectTheGate", "WaitForTheActivateButton",
                     "PressActivateGate"):
            self.assertRegex(self.branch, r"%s -> Just" % step)

    def test_the_bound_is_one_comparison(self):
        """Three readers -- the step rule, the branch, the status clause.

        A give-up decided in one place and reported in another is two places
        that can disagree about whether the gate was given up on.
        """
        comparisons = re.findall(r"gateRefusesThisShipTicks\s*<", self.source)
        self.assertEqual(
            len(comparisons), 1,
            "the bound is compared %d times; it is meant to be compared once, "
            "inside gateHasBeenGivenUpOn" % len(comparisons))
        self.assertIn(
            "gateRefusesThisShipTicks < askedReadings",
            collapsed(body_of(self.source, "gateHasBeenGivenUpOn")))
        self.assertIn("gateHasBeenGivenUpOn gateCase.askedReadings",
                      collapsed(body_of(self.source, "gateActivationStep")))

    def test_the_verdict_is_the_last_reading_that_still_asks(self):
        """Both sides of the comparison, and a fixed value well past it."""
        at_bound, past_bound, far_past = self.repl.evaluate([
            "gateHasBeenGivenUpOn 40", "gateHasBeenGivenUpOn 41",
            "gateHasBeenGivenUpOn 3504"])
        self.assertFalse(at_bound)
        self.assertTrue(past_bound)
        self.assertTrue(far_past)

    def test_the_bound_is_forty(self):
        self.assertTrue(self.repl.evaluate(["gateRefusesThisShipTicks == 40"])[0])


class TheStatusClauseCarriesTheGiveUpTest(unittest.TestCase):
    """Because a `Nothing` cannot carry a decision line.

    The mission runner records what that costs unreported: its gate branch gave
    up on a gate 32 m away and the log said only that nothing was happening,
    1,325 times.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    def clause(self, asked, in_reach, readings):
        return self.repl.strings([
            "describeGateActivationAsk { asked = %s, gateWithinReach = %s"
            ", askedReadings = %d }" % (
                "True" if asked else "False",
                "True" if in_reach else "False", readings)])[0]

    def test_past_the_bound_it_says_the_gate_was_given_up_on(self):
        clause = self.clause(True, True, 41)
        self.assertIn("has not taken me anywhere", clause)
        self.assertIn("41", clause)

    def test_at_the_bound_it_is_still_asking(self):
        clause = self.clause(True, True, 40)
        self.assertNotIn("has not taken me anywhere", clause)
        self.assertIn("asking now", clause)

    def test_a_given_up_gate_does_not_read_as_being_asked(self):
        """The two clauses mean opposite things and must not appear together."""
        clause = self.clause(True, True, 200)
        self.assertNotIn("asking now", clause)

    def test_the_count_is_the_one_it_was_given(self):
        other = self.clause(True, True, 300)
        self.assertIn("300", other)
        self.assertNotIn("200", other)


class TheSearchCannotTellArrivalTest(unittest.TestCase):
    """The premise of the whole change, over readings the real parser produced.

    What is asserted is an *inability*: the whole-tree search answers the same
    thing whether or not the ship has arrived, so the ordering cannot be built
    on it. The grid answers differently, which is what it is built on instead.

    **#200 removed that search and the branch no longer has the inability**, so
    the case that asserted it moved with the code rather than being deleted: the
    text on the panel is now read past by the branch entirely, and what still
    holds -- and is what the ordering rests on -- is that the *grid* separates
    the two states. The label doing so as well is
    `test_saxrat_opportunity_tracker_button
    .TheBranchActsOnWhatTheTrackerOffers.test_a_state_label_is_not_taken`.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    def ask(self, expressions, children):
        return self.repl.evaluate(
            ["reading |> Maybe.map (%s) |> Maybe.withDefault False" % e
             for e in expressions],
            definitions=[GateRepl.reading_binding("reading", children)])

    def test_the_panels_bare_text_is_no_longer_what_is_read(self):
        """The search this replaced answered `Just` for both of these.

        A `Warp to Site` drawn anywhere in the tree, with and without a gate on
        the grid: identical to the old search and nothing to the new branch,
        which wants the tracker's own widget under a `DungeonInfoPanelEntry`.
        That is also the collision the issue rules out -- the same text search
        widened to `Jump` would have found the Selected Item panel's button.
        """
        before = self.ask(
            ["\\r -> warpToOpportunitySiteIfAvailable r /= Nothing"],
            [warp_to_site_button()])[0]
        after = self.ask(
            ["\\r -> warpToOpportunitySiteIfAvailable r /= Nothing"],
            reading(gate_distance="1500 m") + [warp_to_site_button()])[0]
        self.assertFalse(
            before,
            "a bare panel label is being acted on again, which is the "
            "whole-tree search #200 removed")
        self.assertFalse(after, "the same, with a gate on the grid")

    def test_the_grid_is_what_answers_differently(self):
        away, arrived = (
            self.ask(["accelerationGateIsWithinReach"],
                     [warp_to_site_button()])[0],
            self.ask(["accelerationGateIsWithinReach"],
                     reading(gate_distance="1500 m")
                     + [warp_to_site_button()])[0])
        self.assertFalse(away)
        self.assertTrue(arrived)

    def test_a_gate_out_of_reach_does_not_decline_the_warp(self):
        """The clause is about a gate the ship is standing on, not any gate.

        A gate 40 km away is the out-of-range branch's business and it takes the
        reading through the ordering, not through this clause -- which matters
        because the clause is what still applies after the gate is given up on.
        """
        self.assertFalse(self.ask(
            ["accelerationGateIsWithinReach"],
            reading(gate_distance="40 km") + [warp_to_site_button()])[0])

    def test_the_two_readings_take_different_steps(self):
        """The rule executed on what the parser said about each reading."""
        answers = self.repl.evaluate([
            "siteProgressStep { gateBranchOffersAStep = False"
            ", warpToSiteIsOffered = True, gateWithinReach = %s }"
            " == WarpToTheOpportunitySite" % state
            for state in ("False", "True")])
        self.assertEqual(answers, [True, False])

    def test_a_panel_saying_something_else_is_not_an_opportunity(self):
        self.assertFalse(self.ask(
            ["\\r -> warpToOpportunitySiteIfAvailable r /= Nothing"],
            [warp_to_site_button("Dock in Station")])[0])


class TheRecordedSaxratRunsTest(unittest.TestCase):
    """What the corpus says, as relations rather than as the counts above.

    A growing corpus must not turn a true claim red, so nothing here asserts
    "3,458" or "3,460"; what it asserts is that a stretch of opportunity warps
    exists beside a gate in reach in which the ship never went into warp and the
    client never said a word, and that the stretches which *did* end in a warp
    had no gate in reach.
    """

    IN_REACH = re.compile(
        r"(?:Ticks on an acceleration gate in reach|"
        r"Readings spent asking an acceleration gate to open): (\d+)")

    @staticmethod
    def stretches(lines):
        """Maximal runs of consecutive opportunity-warp decision lines.

        Consecutive in decision lines rather than in log lines: the bot prints
        its whole path several times per reading, so what separates two
        stretches is another decision appearing between them.
        """
        found = []
        current = None
        for index, line in enumerate(lines):
            if not line.startswith("+"):
                continue
            if OPPORTUNITY_LINE in line:
                if current is None:
                    current = {"first": index, "last": index, "lines": 0}
                    found.append(current)
                current["last"] = index
                current["lines"] += 1
            elif IN_WARP_LINE not in line:
                # An in-warp line inside a stretch is the arrival the click was
                # issued during, not the stretch ending -- the ship is still
                # coming out of the warp that brought it to the site.
                current = None
        return found

    def counters_between(self, lines, first, last):
        values = []
        for line in lines[first:last + 1]:
            match = self.IN_REACH.search(line)
            if match:
                values.append(int(match.group(1)))
        return values

    def test_a_stretch_beside_a_gate_in_reach_never_produced_a_warp(self):
        """The shadow, measured: thousands of clicks and no ship movement.

        Asserted as a ratio so the two arrival readings at the very start of run
        5's stretch -- the ship still finishing the warp that brought it there --
        do not make this a claim about zero.
        """
        found = False
        for path in saxrat_runs(3, 4, 5):
            lines = read_log(path).splitlines()
            for stretch in self.stretches(lines):
                if stretch["lines"] < 500:
                    continue
                counters = self.counters_between(
                    lines, stretch["first"], stretch["last"])
                self.assertTrue(counters, "no in-reach counter in the stretch")
                self.assertTrue(
                    min(counters) > 0,
                    "%s: a long opportunity stretch with no gate in reach -- "
                    "the shadowing reading of this corpus has changed"
                    % os.path.basename(path))
                warps = sum(
                    1 for line in lines[stretch["first"]:stretch["last"] + 1]
                    if IN_WARP_LINE in line)
                self.assertTrue(
                    warps * 100 < stretch["lines"],
                    "%s: %d in-warp lines inside %d opportunity warps -- the "
                    "click is landing after all"
                    % (os.path.basename(path), warps, stretch["lines"]))
                found = True
        self.assertTrue(
            found,
            "no long opportunity stretch in the corpus at all, so the shadow "
            "this change removes is no longer recorded anywhere")

    def test_the_client_never_answered_the_stale_click(self):
        """Which is what rules out asking the client instead of the grid.

        The run as a whole carries plenty of quick messages, so this is the
        client being silent about these clicks rather than the channel being
        unread.
        """
        for path in saxrat_runs(5):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            on_screen = [index for index, line in enumerate(lines)
                         if "Quick message (on screen now)" in line]
            self.assertTrue(
                on_screen, "%s: no quick message was ever on screen" % name)
            for stretch in self.stretches(lines):
                if stretch["lines"] < 500:
                    continue
                inside = [index for index in on_screen
                          if stretch["first"] <= index <= stretch["last"]]
                self.assertTrue(
                    len(inside) * 50 < len(on_screen),
                    "%s: %d of %d on-screen quick messages fall inside the "
                    "shadowed stretch -- the client does answer these clicks "
                    "and could be read instead"
                    % (name, len(inside), len(on_screen)))

    def test_every_warp_that_worked_was_taken_with_no_gate_in_reach(self):
        """The other half of the discriminator.

        A stretch followed by `HOOOOONK in warp` is a click the client acted on.
        Every one of those in the corpus was issued with the in-reach counter at
        zero. A future run that warps to a site with a gate in reach would fail
        this, and would be real evidence against the rule rather than a stale
        case -- which is why it is asserted rather than assumed.
        """
        asked = False
        for path in saxrat_runs(3, 4, 5):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            for stretch in self.stretches(lines):
                after = lines[stretch["last"] + 1:stretch["last"] + 200]
                if not any(IN_WARP_LINE in line for line in after):
                    continue
                counters = self.counters_between(
                    lines, stretch["first"], stretch["last"])
                self.assertTrue(counters, "%s: no counter in the stretch" % name)
                self.assertEqual(
                    max(counters), 0,
                    "%s: a warp followed a stretch taken with a gate in reach "
                    "(counter reached %d) -- the grid no longer separates the "
                    "click that works from the one that does not"
                    % (name, max(counters)))
                asked = True
        self.assertTrue(
            asked,
            "no opportunity stretch in the corpus was ever followed by a warp, "
            "so nothing here says the click works at all")


class TheMissionCorpusIsWhatSizesTheBoundTest(unittest.TestCase):
    """40 readings, on the one bot whose gate branch is genuinely asked.

    saxrat's own peaks cannot size this: every one of them was counted on
    proximity while `warpToOpportunitySiteIfAvailable` held the tree, which is
    the quantity #148's own change argued was the wrong one. The mission runner's
    branch is reached, presses the same panel button and takes gates, so its
    corpus is where a budget for readings-spent-asking comes from.
    """

    STEP = re.compile(r"^# \[\d+\.\d+\] \(")
    GATES = re.compile(r"Acceleration gates on the overview: ([^.]*)\.")
    DISTANCE = re.compile(r" at (\d+) m")
    COUNTER = re.compile(r"Offered and not opened for (\d+) of (\d+)")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)
        cls.bound = int(cls.repl.values(
            ["gateRefusesThisShipTicks"], r"(\d+) : Int")[0])
        # saxrat's own reach, read rather than restated: it is the condition its
        # counter runs inside, and the mission runner's clause reports a distance
        # so its readings can be filtered to the same one. A copy of the number
        # here would keep answering after the real one moved.
        cls.reach_metres = int(cls.repl.values(
            ["interactionRangeInMeters"], r"(\d+) : Int")[0])

    def episodes(self, path):
        """(readings in reach before the ship warped, largest counter) per run.

        A reading is a `# [tick.substep]` block; the counter holds within one, so
        a block whose value repeats the previous one is not counted twice.
        """
        before, peak, current, block = [], 0, None, []

        def end_block(block):
            nonlocal current, peak
            text = "\n".join(block)
            gates = self.GATES.search(text)
            nearest = None
            if gates:
                distances = [int(d) for d in self.DISTANCE.findall(gates.group(1))]
                if distances:
                    nearest = min(distances)
            counter_match = self.COUNTER.search(text)
            counter = int(counter_match.group(1)) if counter_match else None
            if counter is not None:
                peak = max(peak, counter)
            if nearest is not None and nearest <= self.reach_metres:
                if current is None:
                    current = {"before": [], "warped": False}
                if not current["warped"]:
                    if "I am in warp" in text:
                        current["warped"] = True
                    elif counter is not None and (
                            not current["before"]
                            or current["before"][-1] != counter):
                        current["before"].append(counter)
            elif current is not None:
                if current["warped"]:
                    before.append(len(current["before"]))
                current = None

        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if self.STEP.match(line) and block:
                    end_block(block)
                    block = []
                block.append(line)
        if block:
            end_block(block)
        if current is not None and current["warped"]:
            before.append(len(current["before"]))
        return before, peak

    def test_a_gate_that_opens_is_taken_far_inside_the_bound(self):
        """So the bound cannot be cutting through the successes.

        Doubled rather than compared directly, because a bound that merely
        exceeds the longest success by one reading is not a bound.
        """
        longest, episodes = 0, 0
        for _, path in recorded_runs("24", "34", "35", "36", "37"):
            spent, _ = self.episodes(path)
            episodes += len(spent)
            longest = max([longest] + spent)
        self.assertTrue(
            episodes >= 5,
            "only %d gates were reached and taken in the runs read, which is "
            "too few to say anything about the bound" % episodes)
        self.assertTrue(
            longest * 2 < self.bound,
            "the longest gate that still opened spent %d readings in reach "
            "against a bound of %d -- the bound is no longer clear of the "
            "successes" % (longest, self.bound))

    def test_a_gate_that_never_opens_runs_far_past_the_bound(self):
        """The other edge, without which the number above is unbounded below."""
        peak = 0
        for _, path in recorded_runs("24", "34", "35", "36", "37"):
            _, run_peak = self.episodes(path)
            peak = max(peak, run_peak)
        self.assertTrue(
            self.bound * 4 < peak,
            "the largest offered-and-not-opened count in the runs read is %d "
            "against a bound of %d -- the gap the bound sits in has closed"
            % (peak, self.bound))


if __name__ == "__main__":
    unittest.main()
