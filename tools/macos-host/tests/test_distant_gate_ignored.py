"""Tests for ignoring an acceleration gate that is too far away to be one.

Issue #168. Mission run 51 (`mission_run38.log`) spent four hours closing on an
acceleration gate at **1,395,000 m** and returned about 122,500 ISK an hour
against the 1.36M saxrat was measured at. Nothing bounded the approach, because
nothing thought a distance could be absurd -- and `gateWithinReachTicks` could
not be that bound: it counts readings spent asking a gate _in reach_ to open, and
only advances inside `interactionRangeInMeters`, which a gate 1,395 km away never
enters.

A gate that far out is not a gate to fly to. It is evidence that something else
went wrong -- the grid was not cleared, the wrong object was picked, or the bot
is looking at a gate on someone else's grid -- and flying at it converts one
mistake into a whole session.

**The threshold is 150,000 m**, and the measurement behind it is issue #168's own
count over `~/eve-bot-logs`, which this checkout cannot recompute:

    source                  readings   furthest gate
    ---------------------   --------   -------------
    24 mission runs            1,385        77,000 m
    saxrat run 49              3,503       314,000 m
    mission run 51            11,200     1,395,000 m

Twenty-four mission runs never saw a gate past 77,000 m, so 150,000 sits at
roughly twice anything observed working. 300,000 -- the number the issue was
filed at -- catches only 196 of saxrat run 49's 1,629 readings above 150 km, and
run 49 is not a healthy control either (770k ISK/hr against run 48's 1,357k on
identical code, with 28 `askForHelpToGetUnstuck` alarms). The issue files 300 km
as "the safe choice; it is not necessarily the effective one" and puts the real
gap at 100-150 km; 150,000 is the conservative end of that.

Three things follow, and each has cases below:

  - the rule ignores the gate and **does not give up on the grid** -- the same
    `Nothing` shape the existing give-up answers, so the caller's own fallbacks
    run. An `askForHelpToGetUnstuck` here would swap a four-hour chase for a
    four-hour alarm;
  - the AU placeholder is declined **on its own terms**. Every other consumer
    turns an unparsed distance into `999999`, which is past any threshold this
    could carry, so a rule reading that number would decline the row for the
    right reason under a sentence sending an operator to look for a gate that is
    far away rather than for one whose range did not parse;
  - it is **never silent**. `describeAccelerationGate` names the ignored gate,
    its range and the number on every reading, because a bot that has silently
    stopped acting on a gate plainly on screen is this repo's signature failure.

The rule and both sentences are executed through the real `Bot.elm` in
`elm repl` rather than restated in Python; the wiring, which is not an
expression, is read out of the source through a whitespace-collapsing reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import MISSION_RUNNER_DIR, open_repl, recorded_runs

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The three answers the rule can give. Asked as three equalities per case, so a
# rule answering two things at once -- or none -- fails rather than passing on
# whichever constructor a case happened to name.
VERDICTS = ("GateIsCloseEnoughToFlyTo", "GateIsTooFarToBeSomewhereToFlyTo",
            "GateDistanceDoesNotReadAsARange")

# The number under test, written here rather than read out of the source: a case
# that only ever asks about `constant - 1` and `constant` passes for *any*
# constant, including one that ignores every gate or none. #120 paid for that
# hole four times over.
THRESHOLD = 150000

# What the corpus says a real gate has ever measured, and what run 51 chased.
FURTHEST_REAL_GATE = 77000
RUN_51_GATE = 1395000
SAXRAT_RUN_49_GATE = 314000

# The placeholder every other consumer falls back to for a distance the client
# wrote in AU. Past the threshold, which is exactly why the rule reads the
# `Result` rather than this.
AU_PLACEHOLDER = 999999

# The decision line the approach branch prints, which is where a recorded run
# says how far away the gate it was flying at was.
GATE_DISTANCE_LINE = re.compile(r"acceleration gate is (\d+) m away")


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """`text` with every run of whitespace flattened to one space.

    Source assertions go through this so the next `elm-format` pass cannot
    break them the way #58's broke three others.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Any case asserting something is *absent* needs this: a comment naming the
    branch this deliberately does not take would otherwise satisfy the
    assertion, and the new arms are mostly comment.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


def declaration(name, source=None):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source if source is not None else bot_elm(),
                      re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def case_arm(declaration_name, constructor):
    """One arm of a `case`, sliced by indentation rather than by a blank line.

    Ends at the next non-blank line indented no further than the arm's own
    pattern. A reader that stops at the next blank line stops inside the arm --
    these arms carry blank comment lines -- and one that stops at the next
    ` -> ` stops at a nested `case`. PRs #147, #156, #159 and #162 each paid for
    a reader that silently returned too little.
    """
    lines = declaration(declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^\s*%s\b.*->$" % re.escape(constructor), line)]
    assert opens, "no %r arm in %r" % (constructor, declaration_name)
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    return collapsed(without_comments("\n".join(lines[start:end])))


def gate_distances(path):
    """Every gate range a run's approach branch printed, in metres."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return [int(match.group(1))
                for match in GATE_DISTANCE_LINE.finditer(handle.read())]


class TheRuleTest(unittest.TestCase):
    """`distantGateVerdict`, executed through the real `Bot.elm`.

    Every case asks all three equalities, so an answer is a single named
    constructor rather than "the one this case looked for was true".
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()

    def verdict(self, distance_expression, payload=0):
        """Which of the three the rule answers, asked as all three equalities.

        **The payload is part of the question**, since the status clause prints
        it: a rule answering the right constructor carrying the wrong number
        would put a range in the log that no row reported. For an `Err` input
        the two carrying a payload are compared against 0, which is a real
        distance and so a real disagreement rather than a hole.
        """
        expression = "distantGateVerdict (%s)" % distance_expression
        answers = self.repl.evaluate([
            "(%s) == GateIsCloseEnoughToFlyTo %d" % (expression, payload),
            "(%s) == GateIsTooFarToBeSomewhereToFlyTo %d"
            % (expression, payload),
            "(%s) == GateDistanceDoesNotReadAsARange" % expression])
        chosen = [verdict for verdict, yes in zip(VERDICTS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one verdict for %s, got %s"
            % (expression, chosen))
        return chosen[0]

    def range_verdict(self, distance):
        return self.verdict("Ok %d" % distance, distance)

    def test_a_gate_at_the_threshold_is_still_somewhere_to_fly_to(self):
        """The boundary itself, so the comparison cannot move without saying so."""
        self.assertEqual(self.range_verdict(THRESHOLD),
                         "GateIsCloseEnoughToFlyTo")

    def test_a_gate_one_metre_past_the_threshold_is_ignored(self):
        self.assertEqual(self.range_verdict(THRESHOLD + 1),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_the_furthest_gate_the_corpus_holds_is_still_flown_to(self):
        """77,000 m, and it is what keeps this from cutting good behaviour.

        A fixed value well inside the bound rather than a second boundary pair:
        the two above are satisfied by any constant, and this one is not.
        """
        self.assertEqual(self.range_verdict(FURTHEST_REAL_GATE),
                         "GateIsCloseEnoughToFlyTo")

    def test_run_51_s_own_gate_is_ignored(self):
        """The incident, at the distance its log printed 11,182 times."""
        self.assertEqual(self.range_verdict(RUN_51_GATE),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_saxrat_run_49_s_gate_is_ignored_too(self):
        """314,000 m -- the case a 300 km bound catches only a tenth of."""
        self.assertEqual(self.range_verdict(SAXRAT_RUN_49_GATE),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_a_gate_the_ship_is_sitting_on_is_never_ignored(self):
        for distance in (0, 2000, 32):
            self.assertEqual(self.range_verdict(distance),
                             "GateIsCloseEnoughToFlyTo",
                             "at %d m" % distance)

    def test_an_unreadable_distance_is_declined_on_its_own_terms(self):
        """`Err` is its own answer, not "very far away".

        The two want different sentences, and an operator handed the far-away
        one would go looking for a gate that is far away rather than for a row
        whose range did not parse.
        """
        self.assertEqual(self.verdict('Err "failed to parse distance"'),
                         "GateDistanceDoesNotReadAsARange")

    def test_the_au_placeholder_is_not_what_the_rule_reads(self):
        """The whole reason the rule takes the `Result`.

        `overviewEntryDistanceOrFarInMeters` answers 999999 for an AU distance,
        which is past this threshold -- so a rule reading that number would
        answer `GateIsTooFarToBeSomewhereToFlyTo` for a row that reported no
        distance at all. Asked as the disagreement rather than as one answer.
        """
        self.assertEqual(self.range_verdict(AU_PLACEHOLDER),
                         "GateIsTooFarToBeSomewhereToFlyTo")
        self.assertEqual(self.verdict('Err "999999 is not a range"'),
                         "GateDistanceDoesNotReadAsARange")

    def test_the_threshold_is_one_hundred_and_fifty_kilometres(self):
        self.assertTrue(self.repl.evaluate(
            ["distantAccelerationGateMeters == %d" % THRESHOLD])[0])

    def test_the_threshold_sits_between_the_corpus_and_the_incident(self):
        """Stated as the relation the measurement supports.

        A number below the furthest gate a run ever flew to would cut through
        observed good behaviour; one above run 51's would never fire.
        """
        self.assertGreater(THRESHOLD, FURTHEST_REAL_GATE)
        self.assertLess(THRESHOLD, RUN_51_GATE)
        self.assertLess(THRESHOLD, SAXRAT_RUN_49_GATE)


class TheWordingTest(unittest.TestCase):
    """What an operator reads, rendered rather than asserted by substring.

    `describeAccelerationGate` is not an expression a repl can be handed, and a
    case asserting a phrase occurs *somewhere in the branch* has already passed
    on a branch's own log text once (#145's named-button case). So the sentence
    itself is executed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()
        cls.close, cls.far, cls.unreadable = cls.repl.strings([
            "describeDistantGate (GateIsCloseEnoughToFlyTo %d)"
            % FURTHEST_REAL_GATE,
            "describeDistantGate (GateIsTooFarToBeSomewhereToFlyTo %d)"
            % RUN_51_GATE,
            "describeDistantGate GateDistanceDoesNotReadAsARange"])

    def test_the_ordinary_reading_says_nothing(self):
        """A clause on every reading a gate is on the overview would be noise;
        the rest of `describeAccelerationGate` already names it and its range.
        """
        self.assertEqual(self.close, "")

    def test_the_ignored_gate_says_it_is_being_ignored(self):
        self.assertIn("IGNORING", self.far)
        self.assertIn("IGNORING", self.unreadable)

    def test_the_ignored_gate_names_its_range_and_the_number(self):
        """Both, because one without the other cannot be acted on.

        The range says which gate, and the threshold says what it was measured
        against -- which is the evidence a retune of a number about how these
        sites are laid out would rest on.
        """
        self.assertIn(str(RUN_51_GATE), self.far)
        self.assertIn(str(THRESHOLD), self.far)

    def test_the_unreadable_range_quotes_no_number(self):
        """There is no distance to quote, and inventing one is the failure the
        `Result` split exists to refuse."""
        self.assertNotIn(str(THRESHOLD), self.unreadable)
        self.assertNotIn(str(AU_PLACEHOLDER), self.unreadable)
        self.assertRegex(self.unreadable, r"does not read as a range")

    def test_both_say_the_reading_goes_back_to_the_rest_of_the_tree(self):
        """Ignoring the gate rather than giving up on the grid, in words.

        An operator reading "IGNORING" with nothing after it cannot tell this
        from a bot that has stopped.
        """
        for sentence in (self.far, self.unreadable):
            self.assertIn("rest of the decision tree", sentence)

    def test_neither_asks_for_help(self):
        """The alarm this deliberately is not -- see the branch's own comment."""
        for sentence in (self.far, self.unreadable):
            self.assertNotIn("stuck", sentence)
            self.assertNotIn("need help", sentence)


class TheWiringTest(unittest.TestCase):
    """What `activateAccelerationGateIfPresent` does with the rule's answer."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_elm()
        cls.branch = collapsed(without_comments(
            declaration("activateAccelerationGateIfPresent", cls.source)))

    def test_the_branch_asks_the_rule_on_the_row_s_own_reading(self):
        """The `Result` the parser produced, not the 999999 fallback."""
        self.assertIn(
            "case distantGateVerdict accelerationGateEntry.objectDistanceInMeters of",
            self.branch)

    def test_both_ignoring_answers_hand_the_reading_back(self):
        """`Nothing`, so the caller's own fallbacks run -- the shape the
        existing give-up already uses, for the same reason."""
        for constructor in ("GateIsTooFarToBeSomewhereToFlyTo",
                            "GateDistanceDoesNotReadAsARange"):
            arm = case_arm("activateAccelerationGateIfPresent", constructor)
            self.assertRegex(arm, r"-> Nothing$", constructor)

    def test_the_ignoring_answers_do_not_ask_for_help(self):
        """A four-hour alarm in place of a four-hour chase is not a fix, and it
        is what saxrat's gate give-up did wrong until #147 -- 721 repeats in its
        run 43."""
        for constructor in ("GateIsTooFarToBeSomewhereToFlyTo",
                            "GateDistanceDoesNotReadAsARange"):
            arm = case_arm("activateAccelerationGateIfPresent", constructor)
            self.assertNotIn("askForHelpToGetUnstuck", arm)

    def test_the_flyable_answer_is_what_carries_the_old_branch(self):
        """So a revert has to be visible here rather than hiding in a name."""
        arm = case_arm("activateAccelerationGateIfPresent",
                       "GateIsCloseEnoughToFlyTo")
        for named in ("gateLockedForWantOfAnItem", "gateCanBeActivatedNow",
                      "gateRefusesThisShipTicks"):
            self.assertIn(named, arm)

    def test_the_distance_is_asked_before_anything_flies_at_the_gate(self):
        """Ordering, not preference: the approach branch is what would fly at
        it, and the locked verdict raises an alarm about a gate that is only
        worth an alarm if the ship could ever reach it."""
        self.assertLess(
            self.branch.index("distantGateVerdict"),
            self.branch.index("gateLockedForWantOfAnItem"),
            "the distance must be asked before the locked verdict")
        self.assertLess(
            self.branch.index("distantGateVerdict"),
            self.branch.index("gateCanBeActivatedNow"),
            "the distance must be asked before the approach branch")

    def test_the_distance_used_downstream_is_the_readable_one(self):
        """`distanceInMeters` comes out of the `Ok` now, so the messages the
        approach branch prints cannot carry the AU placeholder."""
        self.assertIn("GateIsCloseEnoughToFlyTo distanceInMeters ->",
                      self.branch)
        self.assertNotIn(
            "distanceInMeters = overviewEntryDistanceOrFarInMeters"
            " accelerationGateEntry", self.branch)

    def test_the_threshold_is_compared_in_one_place(self):
        """One comparison with three readers -- the rule, the branch and the
        status clause -- because a verdict decided in one place and reported in
        another is two places that can disagree about which gates are ignored.
        """
        comparisons = re.findall(
            r"distantAccelerationGateMeters\s*<[^-]", self.source)
        self.assertEqual(
            len(comparisons), 1,
            "the threshold is compared %d times; it is meant to be compared "
            "once, inside distantGateVerdict" % len(comparisons))
        self.assertIn(
            "distantAccelerationGateMeters < distanceInMeters",
            collapsed(declaration("distantGateVerdict", self.source)))


class TheGateWithinReachBudgetIsUntouchedTest(unittest.TestCase):
    """The issue is explicit that this must not fold into `gateWithinReachTicks`.

    That counter is for a gate _in reach_ that will not open, and it only
    advances inside `interactionRangeInMeters` -- which is precisely why nothing
    caught run 51. A distant gate must not spend it, and an in-reach gate that
    refuses must still spend it.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = bot_elm()

    def test_the_counter_still_advances_on_the_client_s_own_offer(self):
        field = re.search(
            r"\n    , gateWithinReachTicks =\n(.*?)\n    , ",
            self.source, re.DOTALL)
        self.assertIsNotNone(field, "no gateWithinReachTicks field")
        body = collapsed(without_comments(field.group(1)))
        self.assertIn("selectedItemOffersActivateGate", body)

    def test_the_counter_knows_nothing_about_the_distance_rule(self):
        field = re.search(
            r"\n    , gateWithinReachTicks =\n(.*?)\n    , ",
            self.source, re.DOTALL)
        body = without_comments(field.group(1))
        for named in ("distantGateVerdict", "distantAccelerationGateMeters"):
            self.assertNotIn(named, body)

    def test_the_reach_test_is_still_the_interaction_range(self):
        """A distant gate is ignored; a near one is still in reach by the same
        number it always was, so the propulsion rule and the counter are
        unmoved."""
        body = collapsed(declaration("accelerationGateIsWithinReach",
                                     self.source))
        self.assertIn("<= interactionRangeInMeters", body)
        self.assertNotIn("distantAccelerationGateMeters", body)


class TheStatusLineSaysSoTest(unittest.TestCase):
    """A silent decline is this repo's signature failure.

    Run 10 is what it costs on this very branch: the give-up answered `Nothing`
    about a gate 32 m away and the log said only that nothing was happening,
    1,325 readings running.
    """

    @classmethod
    def setUpClass(cls):
        cls.clause = collapsed(without_comments(
            declaration("describeAccelerationGate")))

    def test_the_clause_renders_the_verdict(self):
        self.assertIn("describeDistantGate", self.clause)

    def test_the_clause_speaks_about_the_gate_the_branch_acts_on(self):
        """Both take the head of `accelerationGatesOnOverview`, so the line and
        the decision cannot disagree about which gate was ignored."""
        self.assertIn("List.head", self.clause)
        self.assertIn(".objectDistanceInMeters >> distantGateVerdict"
                      " >> describeDistantGate", self.clause)

    def test_the_clause_is_derived_rather_than_written_twice(self):
        """The sentence is `describeDistantGate`'s and no second copy of it
        lives here, so the two cannot drift."""
        self.assertNotIn("IGNORING", self.clause)


class TheCorpusTest(unittest.TestCase):
    """What the recorded mission runs say, as relations rather than as numbers.

    The counts in issue #168 were taken over a corpus this checkout does not
    have, so they are cited in the doc comment rather than claimed here. What
    these cases assert is the shape a growing corpus cannot turn red: a healthy
    run's gates all sit below the threshold, and the incident's sit far above
    it.
    """

    def test_a_healthy_run_holds_no_gate_this_rule_would_ignore(self):
        """Otherwise the threshold cuts through observed good behaviour."""
        found = recorded_runs("35", "37", "36", "34")
        seen = False
        for name, path in found:
            distances = gate_distances(path)
            if not distances:
                continue
            seen = True
            self.assertLessEqual(
                max(distances), THRESHOLD,
                "run %s flew at a gate at %d m, which this rule would now "
                "ignore" % (name, max(distances)))
        if not seen:
            raise unittest.SkipTest(
                "no recorded runs carry an acceleration-gate distance line")

    def test_the_incident_s_gate_is_far_past_the_threshold(self):
        """`mission_run38.log` is run 51, the four hours this was filed on."""
        found = recorded_runs("38")
        for name, path in found:
            distances = gate_distances(path)
            self.assertTrue(
                distances, "run %s carries no gate distance line" % name)
            self.assertGreater(
                max(distances), THRESHOLD * 2,
                "run %s's furthest gate is %d m" % (name, max(distances)))


if __name__ == "__main__":
    unittest.main()
