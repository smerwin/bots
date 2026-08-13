"""Tests for saxrat ignoring an acceleration gate that is too far away to be one.

Issue #168 ported into `eve-online-saxrat`. The argument is not re-derived -- see
`test_distant_gate_ignored.py` for the incident (mission run 51, four hours spent
closing on a gate at 1,395,000 m for about 122,500 ISK an hour), for why
`gateWithinReachTicks` cannot be the bound (it only advances inside
`interactionRangeInMeters`, which such a gate never enters), and for where
150,000 m comes from. What follows is only what saxrat changes about it.

**The rule is shared byte for byte**, the way the quick-message clause is:
`distantAccelerationGateMeters`, `DistantGateVerdict`, `distantGateVerdict` and
`describeDistantGate` are the same declarations under the same names in both
apps, and a case compares them. A threshold retuned in one bot and left in the
other is two bots with different ideas of how far a gate can be.

**What differs is where the decline lands.** The mission runner's `Nothing` goes
to the caller's own fallbacks; saxrat's goes to `siteProgressStep`, which asks
the gate branch first and then declines a "Warp to Site" offered while a gate is
in reach -- so an ignored gate reaches the probe-scan hunt loop rather than
falling into the dead opportunity click #147 measured at 3,458 readings. And the
status clause is appended beside `describeGateActivationAsk` rather than folded
into it: a gate this bot declines to fly at and a gate it has been asking to open
all along are different sentences.

**`nearestAccelerationGateOnOverview` is new here and is what keeps them
honest.** saxrat's branch built its candidate list inline, so a status clause
that rebuilt it would be a second opinion about which gate was ignored. One
definition, read by both.

The rule and both sentences are executed through saxrat's own `Bot.elm` in
`elm repl`; the wiring, which is not an expression, is read out of the source
through a whitespace-collapsing reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_distant_gate_ignored import (
    AU_PLACEHOLDER, FURTHEST_REAL_GATE, RUN_51_GATE, SAXRAT_RUN_49_GATE,
    THRESHOLD, VERDICTS)
from test_distant_gate_ignored import bot_elm as mission_runner_source
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

# The value declarations that must not drift between the two apps.
# `DistantGateVerdict` is the fourth and is compared separately, since a `type`
# has no annotation for `body_of` to start at.
SHARED = ("distantAccelerationGateMeters", "distantGateVerdict",
          "describeDistantGate")


class DistantGateRepl(SaxratRepl):
    pass


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Any case asserting something is *absent* needs this: the new arms are mostly
    comment, and one of those comments names `askForHelpToGetUnstuck` to say why
    the branch does not answer it.
    """
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


def code_only(text):
    """`text` with both kinds of Elm comment removed.

    `without_comments` drops `--` lines and leaves `{-| … -}` blocks, which is
    enough for the assertions that read one declaration. A case counting *call
    sites* needs both gone: this file's own doc comments and branch comments
    name `describeDistantGate` several times to say where the decline is
    reported, so a status line that had stopped calling it would still leave the
    name in the file.
    """
    return re.sub(
        r"^\s*--.*$", "", re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL),
        flags=re.MULTILINE)


def case_arm(source, declaration_name, constructor):
    """One arm of a `case`, sliced by indentation rather than by a blank line.

    Ends at the next non-blank line indented no further than the arm's own
    pattern. A reader that stops at the next blank line stops inside these arms,
    which carry blank comment lines; one that stops at the next ` -> ` stops at
    the nested `case` below. PRs #147, #156, #159 and #162 each paid once for a
    reader that silently returned too little.
    """
    lines = body_of(source, declaration_name).splitlines()
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


class TheRuleTest(unittest.TestCase):
    """`distantGateVerdict`, executed through saxrat's own `Bot.elm`.

    Run here as well as in the mission runner's file rather than trusted to the
    byte-for-byte case: that case says the two texts agree, and this one says
    the text saxrat compiles answers what it is meant to.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(DistantGateRepl)

    def verdict(self, distance_expression, payload=0):
        """Which of the three, asked as all three equalities, payload included."""
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
        self.assertEqual(self.range_verdict(THRESHOLD),
                         "GateIsCloseEnoughToFlyTo")

    def test_a_gate_one_metre_past_the_threshold_is_ignored(self):
        self.assertEqual(self.range_verdict(THRESHOLD + 1),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_the_furthest_gate_the_corpus_holds_is_still_flown_to(self):
        """A fixed value well inside the bound: the two boundary cases above are
        satisfied by any constant, and this one is not."""
        self.assertEqual(self.range_verdict(FURTHEST_REAL_GATE),
                         "GateIsCloseEnoughToFlyTo")

    def test_saxrat_run_49_s_own_gate_is_ignored(self):
        """314,000 m -- this bot's own worst recorded gate distance, and the
        case a 300 km bound catches only a tenth of."""
        self.assertEqual(self.range_verdict(SAXRAT_RUN_49_GATE),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_the_mission_runner_s_incident_is_ignored_here_too(self):
        self.assertEqual(self.range_verdict(RUN_51_GATE),
                         "GateIsTooFarToBeSomewhereToFlyTo")

    def test_a_gate_the_ship_is_sitting_on_is_never_ignored(self):
        for distance in (0, 2000, 32):
            self.assertEqual(self.range_verdict(distance),
                             "GateIsCloseEnoughToFlyTo",
                             "at %d m" % distance)

    def test_an_unreadable_distance_is_declined_on_its_own_terms(self):
        self.assertEqual(self.verdict('Err "failed to parse distance"'),
                         "GateDistanceDoesNotReadAsARange")

    def test_the_au_placeholder_is_not_what_the_rule_reads(self):
        """saxrat spells the fallback inline as `Result.withDefault 999999`, so
        a rule reading it would ignore a row that reported no distance at all
        under the sentence for a gate that is far away."""
        self.assertEqual(self.range_verdict(AU_PLACEHOLDER),
                         "GateIsTooFarToBeSomewhereToFlyTo")
        self.assertEqual(self.verdict('Err "999999 is not a range"'),
                         "GateDistanceDoesNotReadAsARange")

    def test_the_threshold_is_one_hundred_and_fifty_kilometres(self):
        self.assertTrue(self.repl.evaluate(
            ["distantAccelerationGateMeters == %d" % THRESHOLD])[0])


class TheWordingTest(unittest.TestCase):
    """What an operator watching saxrat reads, rendered rather than asserted."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(DistantGateRepl)
        cls.close, cls.far, cls.unreadable = cls.repl.strings([
            "describeDistantGate (GateIsCloseEnoughToFlyTo %d)"
            % FURTHEST_REAL_GATE,
            "describeDistantGate (GateIsTooFarToBeSomewhereToFlyTo %d)"
            % SAXRAT_RUN_49_GATE,
            "describeDistantGate GateDistanceDoesNotReadAsARange"])

    def test_the_ordinary_reading_says_nothing(self):
        self.assertEqual(self.close, "")

    def test_the_ignored_gate_names_its_range_and_the_number(self):
        self.assertIn("IGNORING", self.far)
        self.assertIn(str(SAXRAT_RUN_49_GATE), self.far)
        self.assertIn(str(THRESHOLD), self.far)

    def test_the_unreadable_range_quotes_no_number(self):
        self.assertIn("IGNORING", self.unreadable)
        self.assertNotIn(str(THRESHOLD), self.unreadable)
        self.assertNotIn(str(AU_PLACEHOLDER), self.unreadable)

    def test_neither_asks_for_help(self):
        """The alarm this deliberately is not. saxrat's gate give-up answered
        `askForHelpToGetUnstuck` until #147 and that cost run 4 the rest of its
        session; a distance bound must not reintroduce it."""
        for sentence in (self.far, self.unreadable):
            self.assertNotIn("stuck", sentence)
            self.assertNotIn("need help", sentence)


class TheSharedRuleTest(unittest.TestCase):
    """The two apps' copies, compared byte for byte.

    A number about how these sites are laid out that is retuned in one bot and
    left in the other is two bots with different ideas of how far a gate can be,
    and nothing else in either file would notice.
    """

    @classmethod
    def setUpClass(cls):
        cls.saxrat = source_of(SAXRAT_BOT_ELM)
        cls.mission_runner = mission_runner_source()

    def test_each_shared_declaration_is_identical(self):
        for name in SHARED:
            self.assertEqual(
                body_of(self.saxrat, name),
                body_of(self.mission_runner, name),
                "%s has drifted between the two apps" % name)

    def test_the_verdict_type_is_identical(self):
        def verdict_type(source):
            match = re.search(
                r"^type DistantGateVerdict$.*?(?=\n\n\n|\Z)", source,
                re.MULTILINE | re.DOTALL)
            assert match, "no DistantGateVerdict declaration"
            return match.group(0)

        self.assertEqual(verdict_type(self.saxrat),
                         verdict_type(self.mission_runner))


class TheWiringTest(unittest.TestCase):
    """What saxrat's `activateAccelerationGateIfPresent` does with the answer."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(without_comments(
            body_of(cls.source, "activateAccelerationGateIfPresent")))

    def test_the_branch_asks_the_rule_on_the_row_s_own_reading(self):
        self.assertIn(
            "case distantGateVerdict accelerationGateEntry.objectDistanceInMeters of",
            self.branch)

    def test_both_ignoring_answers_hand_the_reading_back(self):
        """`Nothing`, the same answer `GiveUpOnThisGate` gives, so
        `siteProgressStep` sends the reading to the hunt loop."""
        for constructor in ("GateIsTooFarToBeSomewhereToFlyTo",
                            "GateDistanceDoesNotReadAsARange"):
            arm = case_arm(self.source, "activateAccelerationGateIfPresent",
                           constructor)
            self.assertRegex(arm, r"-> Nothing$", constructor)

    def test_the_ignoring_answers_do_not_ask_for_help(self):
        for constructor in ("GateIsTooFarToBeSomewhereToFlyTo",
                            "GateDistanceDoesNotReadAsARange"):
            arm = case_arm(self.source, "activateAccelerationGateIfPresent",
                           constructor)
            self.assertNotIn("askForHelpToGetUnstuck", arm)

    def test_the_distance_is_asked_before_the_close_in_command(self):
        """Ordering, not preference: the out-of-range branch is the one that
        would issue `Activate Gate` from 1,395 km and let the client fly there.
        """
        self.assertLess(
            self.branch.index("distantGateVerdict"),
            self.branch.index("interactionRangeInMeters < distanceInMeters"),
            "the distance must be asked before the close-in command")

    def test_the_flyable_answer_is_what_carries_the_old_branch(self):
        arm = case_arm(self.source, "activateAccelerationGateIfPresent",
                       "GateIsCloseEnoughToFlyTo")
        for named in ("interactionRangeInMeters", "gateActivationStep",
                      "selectedItemActivateGate"):
            self.assertIn(named, arm)

    def test_the_distance_used_downstream_is_the_readable_one(self):
        """`distanceInMeters` comes out of the `Ok`, so the close-in command's
        own message cannot carry the AU placeholder."""
        self.assertIn("GateIsCloseEnoughToFlyTo distanceInMeters ->",
                      self.branch)
        self.assertNotIn(
            "distanceInMeters = accelerationGateEntry.objectDistanceInMeters"
            " |> Result.withDefault 999999", self.branch)

    def test_the_threshold_is_compared_in_one_place(self):
        comparisons = re.findall(
            r"distantAccelerationGateMeters\s*<[^-]", self.source)
        self.assertEqual(
            len(comparisons), 1,
            "the threshold is compared %d times; it is meant to be compared "
            "once, inside distantGateVerdict" % len(comparisons))


class TheNearestGateIsOneDefinitionTest(unittest.TestCase):
    """The branch and the status clause speak about the same gate.

    saxrat built its candidate list inline inside the branch, so a status clause
    that rebuilt it would be a second opinion about which gate was ignored --
    and the two would drift the first time either filter changed.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    def test_the_branch_asks_the_shared_definition(self):
        self.assertIn(
            "case nearestAccelerationGateOnOverview context.readingFromGameClient of",
            collapsed(body_of(self.source,
                              "activateAccelerationGateIfPresent")))

    def test_the_status_line_asks_the_same_one(self):
        self.assertIn(
            "|> nearestAccelerationGateOnOverview |> Maybe.map"
            " (.objectDistanceInMeters >> distantGateVerdict"
            " >> describeDistantGate)",
            collapsed(self.source))

    def test_the_shared_definition_still_drops_virtualised_rows(self):
        """A row that is not `_display`ed reports a region belonging to whatever
        was recycled into its place, so it can neither be clicked nor believed
        about its range."""
        body = collapsed(body_of(self.source,
                                 "nearestAccelerationGateOnOverview"))
        self.assertIn("List.filter isAccelerationGate", body)
        self.assertIn("List.filter overviewEntryIsDisplayed", body)
        self.assertIn("List.head", body)

    def test_the_candidate_list_is_not_built_twice(self):
        """One `List.filter isAccelerationGate` pipeline over the overview
        windows, not two."""
        self.assertEqual(
            collapsed(self.source).count(
                "List.concatMap .entries |> List.filter isAccelerationGate"
                " |> List.filter overviewEntryIsDisplayed"),
            1)


class TheGateWithinReachBudgetIsUntouchedTest(unittest.TestCase):
    """The issue is explicit that this must not fold into `gateWithinReachTicks`.

    That counter is saxrat's bound on readings spent *asking* a gate in reach to
    open -- #145 corrected it off proximity for exactly that reason -- and a
    gate 1,395 km away never reaches it. A distant gate must not spend it.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    def test_the_counter_still_advances_on_the_ask(self):
        body = collapsed(body_of(self.source, "gateAskedReadingsAfterReading"))
        self.assertIn("if readingCase.asking then readingCase.before + 1", body)

    def test_the_counter_knows_nothing_about_the_distance_rule(self):
        for name in ("gateAskedReadingsAfterReading",
                     "askingAnAccelerationGateToOpen",
                     "accelerationGatesWithinReach"):
            body = without_comments(body_of(self.source, name))
            for named in ("distantGateVerdict", "distantAccelerationGateMeters"):
                self.assertNotIn(named, body, "%s reads %s" % (name, named))

    def test_the_reach_test_is_still_the_interaction_range(self):
        body = collapsed(body_of(self.source, "accelerationGatesWithinReach"))
        self.assertIn("<= interactionRangeInMeters", body)


class TheStatusLineSaysSoTest(unittest.TestCase):
    """A silent decline is this repo's signature failure, and this branch has
    already paid for one: the mission runner's gate give-up answered `Nothing`
    about a gate 32 m away and the log said only that nothing was happening,
    1,325 readings running.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def test_the_status_line_renders_the_verdict(self):
        """Called from somewhere, not merely declared.

        Asserting the name occurs in the file would be satisfied by its own
        declaration, so a status line that had stopped calling it would pass --
        which is exactly the silent decline this case exists for.
        """
        code = code_only(source_of(SAXRAT_BOT_ELM))
        rendering = code_only(
            body_of(source_of(SAXRAT_BOT_ELM), "describeDistantGate"))
        callers = code.count("describeDistantGate") - \
            rendering.count("describeDistantGate")
        self.assertGreaterEqual(
            callers, 1,
            "describeDistantGate is declared and never called, so an ignored "
            "gate is declined silently")

    def test_the_clause_is_beside_the_ask_rather_than_inside_it(self):
        """Two different sentences: a gate this bot declines to fly at, and a
        gate it has been asking to open all along. `describeGateActivationAsk`
        keeps its three-field record, which its own cases build."""
        self.assertIn(
            "describeGateActivationAsk { asked = askingAnAccelerationGateToOpen"
            " readingFromGameClient", self.source)
        ask = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                "describeGateActivationAsk"))
        self.assertNotIn("describeDistantGate", ask)

    def test_the_clause_is_derived_rather_than_written_twice(self):
        """The sentence lives in `describeDistantGate` and nowhere else.

        Both occurrences are its own two arms, so a second copy written into the
        status line -- which is how the two would come to disagree about what an
        ignored gate is called -- shows up here as a third.
        """
        rendering = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                      "describeDistantGate"))
        self.assertEqual(rendering.count("IGNORING the nearest one"), 2)
        self.assertEqual(self.source.count("IGNORING the nearest one"), 2)


if __name__ == "__main__":
    unittest.main()
