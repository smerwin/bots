"""Tests for saxrat asking the host for time past the planned session end.

Issue #230: the host has read `@host extend-session <seconds>` out of the
status text since PR #68, and `eve-online-mission-runner` has written one ever
since -- `hostDirectiveExtendSession` there is silent unless the session is
inside its wind-down window, and then asks for `sessionOverrunSecondsNeeded`
only if that is positive. saxrat's own `hostDirectivePrefix` was wired for
`set-destination` (#69) and nothing else, so this bot could reach the host's
`--session-duration-minutes` cap and never ask for a second past it.

**What "needed" means here is a design decision the repo owner made, not one
this file re-derives**: the max of (a) time to finish the anomaly currently
being fought, bounded by rats left on the overview, and (b) time to finish an
escalation trip already in progress, since abandoning one mid-trip can leave
the ship several jumps from home. Nothing else -- no docked/restocking case,
which saxrat has no equivalent of and does not gain one here.

**Two properties carry over from the mission runner's version unchanged, and
both are cases here rather than only a claim**: it is a lease re-derived every
reading, not a setting (a bot that stops needing the extension stops asking
for it, and nothing latches), and the bot never enforces its own 600s cap --
it only asks for what `sessionOverrunSecondsNeeded` says, and the host's own
`MAX_BOT_REQUESTED_OVERRUN_SECONDS` clamps it.

**Neither of the two constants behind the ask is corpus-derived, and this file
does not pretend otherwise.** `anomalyFightSecondsPerRatRemaining` (45s a rat,
capped at `anomalyFightOverrunCapSeconds`, 300s) and
`escalationTripOverrunAllowanceSeconds` (420s, flat, at the mission runner's
own `homeStationTripSecondsPastSessionEnd`'s order of magnitude) are both
placeholders pending a real read of `~/eve-bot-logs` -- see the doc comments
in `Bot.elm` beside each. What is checked here is that the plumbing computes
what it claims to, not that the numbers are right.

These cases execute `anomalyFightOverrunSecondsNeeded`,
`escalationOverrunSecondsNeeded`, `sessionOverrunSecondsNeeded` and
`hostDirectiveExtendSession` through the real `Bot.elm` in `elm repl`, and the
readings they are asked about are built by running UI trees through the real
`EveOnline.ParseUserInterface` -- a Python restatement of what these functions
compute would only test the restatement, which is exactly the trap
`test_bot_extends_session.py` (the mission runner's own file for the same
directive) does not fall into either. The overview and escalation fixtures are
reused rather than rebuilt: `overview`/`rat_rows`/`RAT_COLOR` are
`test_saxrat_combat_stalemate.py`'s, and `tracker_offering`/
`probe_scanner_window` are `test_saxrat_escalation_outranks_the_hunt_circuit.py`'s
-- both already proven against the real parser for the two signals this
change reads.

**The two conditions are close to mutually exclusive on this bot** (the
escalation half is scoped to a shut probe scanner, and this bot fights rats
with it open on 99% of in-space readings per that file's own count), so a
fixture combining both is a property of the pure function rather than a
situation expected to occur in play -- `TheCombinedHalfTest` says so and tests
it anyway, since nothing in the code enforces the exclusivity and the function
has to behave sensibly regardless.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import unittest

from prerequisites import open_repl
from test_saxrat_combat_stalemate import overview, rat_rows
from test_saxrat_escalation_outranks_the_hunt_circuit import (
    probe_scanner_window, tracker_offering)
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, PREAMBLE, SaxratRepl, body_of, collapsed, source_of)

# The constants as shipped, restated here so a case can assert the *relation*
# (scaling, capping, max-not-sum) against known numbers rather than reading
# them back out of the source and comparing them with themselves.
SECONDS_BEFORE_WIND_DOWN = 200
SECONDS_PER_RAT = 45
FIGHT_CAP = 300
ESCALATION_ALLOWANCE = 420

DEFAULT_MEMORY = "initBotMemory"


class ExtendSessionRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus a real `BotDecisionContext` to ask
    `sessionOverrunSecondsNeeded` and `hostDirectiveExtendSession` through --
    both take the whole context rather than a plain record, the same reason
    `test_saxrat_hide_neutral_then_travel.HideThenTravelRepl` builds one.

    The bindings ride in the preamble so `ElmRepl.script` folds them into the
    one `let` each question costs (#172) rather than paying a compile for them
    on every call.
    """

    BINDINGS = (
        "decisionContext = \\memory -> \\sessionTimeLimitMs -> \\reading ->"
        " reading |> Maybe.map (\\p ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = sessionTimeLimitMs }"
        " , readingFromGameClient = p"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] })",
        "neededFor = \\memory -> \\sessionTimeLimitMs -> \\reading -> reading"
        " |> decisionContext memory sessionTimeLimitMs"
        " |> Maybe.map sessionOverrunSecondsNeeded",
        "directiveFor = \\memory -> \\sessionTimeLimitMs -> \\reading -> reading"
        " |> decisionContext memory sessionTimeLimitMs"
        " |> Maybe.map hostDirectiveExtendSession"
        " |> Maybe.withDefault \"<no reading>\"",
        "statusFor = \\memory -> \\sessionTimeLimitMs -> \\reading -> reading"
        " |> decisionContext memory sessionTimeLimitMs"
        " |> Maybe.map statusTextFromState"
        " |> Maybe.withDefault \"<no reading>\"",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-extend-session-repl-")
        kwargs.setdefault("preamble", PREAMBLE + self.BINDINGS)
        super().__init__(**kwargs)


def no_rats_no_escalation_reading(name):
    """A tree with neither signal: no overview window, no tracker, no probe
    scanner -- the baseline every other fixture is a variation on."""
    return ExtendSessionRepl.reading_binding(name, [])


def rats_reading(name, count):
    """`count` rats on the overview, using run 48's own colour and distance so
    `getNamesOfRatsInOverview` counts them -- no tracker, no scanner node."""
    return ExtendSessionRepl.reading_binding(name, [overview(rat_rows(count))])


def escalation_reading(name, scanner_open=False):
    """A tracker offering a travel step, with the scanner shut (the ordinary
    escalation-mode reading) or open (`escalationIsBeingWorked`'s own scope
    guard, which must decline it)."""
    children = [tracker_offering("Set Destination")]
    if scanner_open:
        children.append(probe_scanner_window())
    return ExtendSessionRepl.reading_binding(name, children)


def both_reading(name, rat_count):
    """An escalation and a fight on the same reading -- unreachable in play per
    the probe-scanner scoping, but a value the pure function has to answer
    about all the same."""
    return ExtendSessionRepl.reading_binding(
        name,
        [tracker_offering("Set Destination"), overview(rat_rows(rat_count))])


class TheAnomalyFightHalfTest(unittest.TestCase):
    """`anomalyFightOverrunSecondsNeeded`, against overview rows the real
    parser produced."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ExtendSessionRepl)

    def test_it_scales_with_rats_left_and_then_caps(self):
        """Zero rats needs nothing; each further rat adds
        `anomalyFightSecondsPerRatRemaining` up to the cap.

        A per-rat allowance rather than a flat one, per the design decision:
        "an allowance sized for one rat asks for too little the moment a
        second one arrives" (`Bot.elm`'s own doc comment on this function).
        """
        cases = [
            ("zero", 0, 0),
            ("one", 1, SECONDS_PER_RAT),
            ("four", 4, 4 * SECONDS_PER_RAT),
            ("a_full_room", 20, FIGHT_CAP),
        ]
        definitions = [rats_reading(name, count) for name, count, _ in cases]
        answers = self.repl.evaluate(
            ["(%s |> Maybe.map anomalyFightOverrunSecondsNeeded) == Just %d"
             % (name, expected) for name, _, expected in cases],
            definitions=definitions)
        for (name, count, expected), answer in zip(cases, answers):
            self.assertTrue(
                answer, "%d rats: expected %d" % (count, expected))

    def test_the_cap_really_bites_rather_than_the_count_coincidentally_matching(self):
        """The control for the cap above: a room bigger still asks the same
        capped number, so the cap is a ceiling and not a number that happened
        to equal `20 * 45`."""
        answers = self.repl.evaluate(
            ["(bigger |> Maybe.map anomalyFightOverrunSecondsNeeded) == Just %d"
             % FIGHT_CAP],
            definitions=[rats_reading("bigger", 40)])
        self.assertTrue(answers[0])


class TheEscalationHalfTest(unittest.TestCase):
    """`escalationOverrunSecondsNeeded`, which is `escalationIsBeingWorked`
    (already proven against the real parser next door) turned into a flat
    number of seconds."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ExtendSessionRepl)

    def test_it_asks_the_flat_allowance_only_while_the_tracker_is_working_one(self):
        cases = [
            ("none", no_rats_no_escalation_reading("none"), 0),
            ("shut", escalation_reading("shut"), ESCALATION_ALLOWANCE),
            ("open", escalation_reading("open", scanner_open=True), 0),
        ]
        answers = self.repl.evaluate(
            ["(%s |> Maybe.map escalationOverrunSecondsNeeded) == Just %d"
             % (label, expected) for label, _, expected in cases],
            definitions=[definition for _, definition, _ in cases])
        for (label, _, expected), answer in zip(cases, answers):
            self.assertTrue(answer, "%s: expected %d" % (label, expected))


class TheCombinedHalfTest(unittest.TestCase):
    """`sessionOverrunSecondsNeeded`, the max of the two halves."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ExtendSessionRepl)

    def test_neither_condition_needs_nothing(self):
        answers = self.repl.evaluate(
            ["(neededFor %s Nothing none) == Just 0" % DEFAULT_MEMORY],
            definitions=[no_rats_no_escalation_reading("none")])
        self.assertTrue(answers[0])

    def test_only_the_fight_is_the_fights_own_number(self):
        answers = self.repl.evaluate(
            ["(neededFor %s Nothing fourRats) == Just %d"
             % (DEFAULT_MEMORY, 4 * SECONDS_PER_RAT)],
            definitions=[rats_reading("fourRats", 4)])
        self.assertTrue(answers[0])

    def test_only_the_escalation_is_the_escalations_own_number(self):
        answers = self.repl.evaluate(
            ["(neededFor %s Nothing escalating) == Just %d"
             % (DEFAULT_MEMORY, ESCALATION_ALLOWANCE)],
            definitions=[escalation_reading("escalating")])
        self.assertTrue(answers[0])

    def test_both_present_take_the_larger_not_the_sum(self):
        """4 rats need `4 * 45 = 180`; the escalation needs 420. `max` answers
        420; a version that summed the two would answer 600, which the second
        assertion refuses on its own terms rather than by inference from the
        first."""
        rat_only = 4 * SECONDS_PER_RAT
        answers = self.repl.evaluate(
            ["(neededFor %s Nothing both) == Just %d"
             % (DEFAULT_MEMORY, max(rat_only, ESCALATION_ALLOWANCE)),
             "(neededFor %s Nothing both) /= Just %d"
             % (DEFAULT_MEMORY, rat_only + ESCALATION_ALLOWANCE)],
            definitions=[both_reading("both", 4)])
        self.assertTrue(answers[0], "expected the max of the two halves")
        self.assertTrue(answers[1], "the two halves were summed rather than "
                                    "maxed")

    def test_the_fight_half_reads_the_live_overview_not_remembered_memory(self):
        """`BotMemory.combatStalemate.ratsInOverview` is last reading's count,
        kept for the stalemate detector's own reason -- reusing it here would
        carry a one-reading lag into a request whose whole point is silence
        the moment nothing is left to finish. A memory claiming 99 rats beside
        a live reading of 4 has to answer as 4, not 99."""
        stale_memory = "{ initBotMemory | combatStalemate =" \
                        " { readings = 0, ratsInOverview = 99 } }"
        answers = self.repl.evaluate(
            ["(neededFor (%s) Nothing fourRats) == Just %d"
             % (stale_memory, 4 * SECONDS_PER_RAT)],
            definitions=[rats_reading("fourRats", 4)])
        self.assertTrue(
            answers[0],
            "the live overview count was not what decided the ask")


class TheDirectiveTest(unittest.TestCase):
    """`hostDirectiveExtendSession`: silent outside the window or with nothing
    needed, otherwise `hostDirectivePrefix ++ "extend-session " ++ N`."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ExtendSessionRepl)

    def milliseconds_remaining(self, seconds):
        return "Just %d" % (seconds * 1000)

    def test_it_is_silent_outside_the_window_even_with_something_needed(self):
        """201s remaining is one second past `secondsBeforeSessionEndToWindDown`
        (200), with 4 rats on the overview -- the ask exists and is simply not
        asked yet."""
        answers = self.repl.strings(
            ["directiveFor %s (%s) fourRats"
             % (DEFAULT_MEMORY,
                self.milliseconds_remaining(SECONDS_BEFORE_WIND_DOWN + 1))],
            definitions=[rats_reading("fourRats", 4)])
        self.assertEqual(answers[0], "")

    def test_it_is_silent_without_a_planned_session_end(self):
        """No `--session-duration-minutes` at all: `secondsToSessionEnd`
        answers `Nothing`, so the question of winding down never arises."""
        answers = self.repl.strings(
            ["directiveFor %s Nothing fourRats" % DEFAULT_MEMORY],
            definitions=[rats_reading("fourRats", 4)])
        self.assertEqual(answers[0], "")

    def test_it_is_silent_inside_the_window_with_nothing_needed(self):
        answers = self.repl.strings(
            ["directiveFor %s (%s) none"
             % (DEFAULT_MEMORY, self.milliseconds_remaining(100))],
            definitions=[no_rats_no_escalation_reading("none")])
        self.assertEqual(answers[0], "")

    def test_the_window_boundary_admits_the_ask_at_exactly_the_bound(self):
        """`secondsBeforeSessionEndToWindDown < secondsRemaining` is a strict
        `<`, so exactly 200s remaining is inside the window and 201 is not --
        the second half is `test_it_is_silent_outside_the_window...` above."""
        answers = self.repl.strings(
            ["directiveFor %s (%s) fourRats"
             % (DEFAULT_MEMORY,
                self.milliseconds_remaining(SECONDS_BEFORE_WIND_DOWN))],
            definitions=[rats_reading("fourRats", 4)])
        self.assertNotEqual(
            answers[0], "",
            "exactly at the window's own bound the ask should already be "
            "asking, not waiting one more reading")

    def test_rats_inside_the_window_produce_a_directive_matching_the_prefix(self):
        answers = self.repl.strings(
            ["directiveFor %s (%s) fourRats"
             % (DEFAULT_MEMORY, self.milliseconds_remaining(100))],
            definitions=[rats_reading("fourRats", 4)])
        self.assertEqual(
            answers[0], "@host extend-session %d" % (4 * SECONDS_PER_RAT))

    def test_an_escalation_inside_the_window_produces_a_directive(self):
        answers = self.repl.strings(
            ["directiveFor %s (%s) escalating"
             % (DEFAULT_MEMORY, self.milliseconds_remaining(100))],
            definitions=[escalation_reading("escalating")])
        self.assertEqual(
            answers[0], "@host extend-session %d" % ESCALATION_ALLOWANCE)


class TheWiringTest(unittest.TestCase):
    """What `statusTextFromState` does with the directive, which is not an
    expression -- read out of the source through a whitespace-collapsing
    reader, the same convention `test_bot_extends_session.py` and
    `test_saxrat_kill_counter.py` both use for their own placement pins."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    def test_the_directive_is_the_last_entry_of_the_status_text_list(self):
        block = collapsed(body_of(self.source, "statusTextFromState"))
        directive_marker = "[ hostDirectiveExtendSession context ]"
        # `, describeCurrentReading` rather than the bare name, which also
        # matches the `let`-bound definition much earlier in the function --
        # the comma is only on the outer list's own usage of it.
        usage_marker = ", describeCurrentReading"
        self.assertIn(directive_marker, block)
        self.assertIn(usage_marker, block)
        self.assertLess(
            block.index(usage_marker), block.index(directive_marker),
            "the directive is not the last thing statusTextFromState builds")
        # And nothing may follow it inside the list literal.
        remainder = block[
            block.index(directive_marker) + len(directive_marker):].strip()
        self.assertTrue(
            remainder.startswith("]"),
            "something follows the directive inside the outer list: %r"
            % remainder[:40])

    def test_the_pipeline_filters_empty_entries_rather_than_printing_them(self):
        """Outside the wind-down window `hostDirectiveExtendSession` answers
        `""`, and the pipeline has to drop that rather than join it in as a
        blank line -- the mission runner's own `List.filter (String.isEmpty
        >> not)` next to its own directive."""
        block = collapsed(body_of(self.source, "statusTextFromState"))
        # One substring rather than two separate `index` lookups: several
        # other clauses in this function join strings of their own (the
        # overview's pilot names, for one), so a bare `"String.join"` search
        # can find one of those instead of the final pipeline.
        self.assertIn(
            "List.concat |> List.filter (String.isEmpty >> not)"
            ' |> String.join "\\n"', block,
            "the filter is not where it has to be: immediately between "
            "List.concat and the final String.join")


class TheEndToEndStatusTextTest(unittest.TestCase):
    """`statusTextFromState` itself, so the wiring pin above is checked
    against what the function actually produces rather than only against its
    own source."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ExtendSessionRepl)

    def test_a_winding_down_reading_ends_with_the_directive_on_its_own_line(self):
        status = self.repl.strings(
            ["statusFor %s (Just %d) fourRats"
             % (DEFAULT_MEMORY, 100 * 1000)],
            definitions=[rats_reading("fourRats", 4)])[0]
        lines = status.split("\\n")
        self.assertEqual(
            lines[-1], "@host extend-session %d" % (4 * SECONDS_PER_RAT),
            "the directive is not the final line of the full status text")

    def test_an_ordinary_reading_carries_no_directive_line_at_all(self):
        """No session limit configured -- an everyday run with no
        `--session-duration-minutes` -- so the status text must not gain a
        trailing blank line where the directive would otherwise sit."""
        status = self.repl.strings(
            ["statusFor %s Nothing fourRats" % DEFAULT_MEMORY],
            definitions=[rats_reading("fourRats", 4)])[0]
        self.assertNotIn("@host extend-session", status)
        self.assertFalse(
            status.endswith("\\n"),
            "a trailing blank line means the empty directive was joined in "
            "rather than filtered out")


if __name__ == "__main__":
    unittest.main()
