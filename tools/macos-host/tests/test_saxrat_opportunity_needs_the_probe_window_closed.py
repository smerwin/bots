"""saxrat takes the Opportunities tracker's step only with the probe scanner shut.

`siteProgressStep` resolves three outcomes -- `WorkTheAccelerationGate`,
`WarpToTheOpportunitySite`, `HuntWithTheProbeScanner` -- and the middle one now
also requires `readingFromGameClient.probeScannerWindow == Nothing`. **Closed
means closed in the client**, not "open but holding nothing useful"; the two
readings were weighed and the first is the one that shipped, because closing the
scanner is an act nothing in the client does on its own and is therefore the one
thing on a reading that can carry an operator's intent. With it closed the bot
goes and works escalations; with it open it hunts locally.

**It is a hard gate.** With the window open the tracker's step is not taken at
all, whatever the panel offers.

#202 and #204 are the reason this needs saying out loud rather than merely
implementing. Both were about a **closed** scanner window hiding these very
steps: `decideNextActionWhenInSpace` splits on `probeScannerWindow` and both the
gate step and the opportunity warp were bound inside the `Just` arm, so a shut
window made an acceleration gate on grid and a "Warp to Site" on offer equally
invisible -- reachable code that nothing could reach. This is the opposite
polarity, so it is not that defect coming back: closed *enables* the opportunity
rather than hiding it, and the gate is not gated at all. What it does do is put a
coupling back between the scanner window and the opportunity step, which is why
`test_the_acceleration_gate_is_unaffected_by_the_scanner_window` is here -- the
gate must never become invisible again, in either direction.

**Declining is not waiting**, which is the other property worth a case. PR #257
shipped green and blocked the bot for 108 minutes by putting an unbounded wait on
this exact path; a gate that hands the reading to `ifNeither` -- the hunt loop,
or leaving the system -- cannot do that, and `TheDeclineIsNotAWaitTest` pins it.

The rule is executed through the real `Bot.elm` in `elm repl`, at every
combination of its four inputs and again against readings the real
`EveOnline.ParseUserInterface` produced from a UI tree with and without a
`ProbeScannerWindow` node. The wiring, which is not an expression, is read out of
the source through a whitespace-collapsing reader.

**What it costs is measured here rather than asserted**, in
`TheRecordedRunsPriceThisTest`: across every recorded saxrat run the scanner
window is open on the overwhelming majority of in-space readings, and on
essentially every reading that ever took an opportunity step. So on the corpus as
it stands this gate switches the tracker work off almost always -- which is the
point of an operator switch, and is also the cost, and is recounted as relations
so a growing corpus cannot turn a true claim red.

Confirmed by mutation, ten of them, each failing a named case: the scanner
clause dropped from the rule (the change reverted); the clause inverted, so the
step is taken exactly when it must not be; the clause conjoined onto the gate
answer as well, which is #204's defect restored in the direction that hides the
gate; the clause replacing the gate-in-reach clause rather than joining it; the
wiring handing the rule `/= Nothing`, so a shut window reads as open; the wiring
reading the window's scan results instead of the window, which is the rejected
"open but holding nothing" reading; the hunt answer given a
`waitForProgressInGame` of its own, which is #257's shape; the hunt answer
running the gate step's own fallback rather than the caller's; the doc comment
no longer separating this from #202 and #204; and, on the cases' own premise,
the corpus reader counting decision lines rather than readings.

**One hole was found in the first pass and closed rather than left.** The
inverted wiring failed one case and that case was a *substring read* -- the rule
takes a record of `Bool`s and cannot see where they came from, and
`siteProgressStepOrElse` takes a whole `BotDecisionContext` no case here can
assemble, so nothing executed the question the bot actually asks.
`TheWiringExecutedTest` cuts that expression out of the source and runs it
against both fixtures, which is what a wiring answering the opposite question
has to survive now.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_gate_panel_button import reading
from test_saxrat_opportunity_shadow import without_line_comments
from test_saxrat_opportunity_tracker_button import (
    TrackerRepl, expanded_entry, tracker, travel_button)
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, body_of, collapsed, node, source_of)

STEPS = ("WorkTheAccelerationGate", "WarpToTheOpportunitySite",
         "HuntWithTheProbeScanner")

# The client's own type name for the probe scanner. The parser matches on it and
# on nothing else, so one node with a region is a window as far as the bot is
# concerned -- which is exactly the question this gate asks.
PROBE_SCANNER_TYPE = "ProbeScannerWindow"


def probe_scanner_window():
    """The scanner, open and holding nothing.

    Deliberately empty. "Open with no useful scan results" is the reading of
    "closed" that was considered and rejected, so the fixture that must decline
    the opportunity is the one that would pass under it.
    """
    return node(PROBE_SCANNER_TYPE, {"_name": "probeScannerWindow"}, [
        node("Container", {"_name": "ResultsContainer"}, [], region=(0, 20, 300, 200)),
    ], region=(1000, 100, 300, 240))


def tracker_offering_a_step():
    return tracker([expanded_entry([travel_button("Warp to Site")])])


class TheRuleTest(unittest.TestCase):
    """`siteProgressStep`, executed at every combination of its four inputs.

    Asked as three equalities per case rather than one, so a rule answering two
    things at once -- or none -- fails rather than passing on whichever
    constructor a case happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def step(self, gate_step, warp_offered, gate_in_reach, window_closed):
        expression = (
            "siteProgressStep { gateBranchOffersAStep = %s"
            ", warpToSiteIsOffered = %s, gateWithinReach = %s"
            ", probeScannerWindowIsClosed = %s }" % (
                "True" if gate_step else "False",
                "True" if warp_offered else "False",
                "True" if gate_in_reach else "False",
                "True" if window_closed else "False"))
        answers = self.repl.evaluate(
            ["(%s) == %s" % (expression, step) for step in STEPS])
        chosen = [step for step, yes in zip(STEPS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one step for %s, got %s" % (expression, chosen))
        return chosen[0]

    def test_the_opportunity_is_taken_with_the_scanner_window_closed(self):
        """The state the operator asks for by closing the scanner."""
        self.assertEqual(
            self.step(gate_step=False, warp_offered=True,
                      gate_in_reach=False, window_closed=True),
            "WarpToTheOpportunitySite")

    def test_the_opportunity_is_declined_with_the_scanner_window_open(self):
        """The same reading in every other respect, and the whole change.

        Stated as the comparison against the case above rather than as one
        answer, which is what a clause has to satisfy and a dropped branch does
        not.
        """
        self.assertEqual(
            self.step(gate_step=False, warp_offered=True,
                      gate_in_reach=False, window_closed=False),
            "HuntWithTheProbeScanner")

    def test_the_acceleration_gate_is_unaffected_by_the_scanner_window(self):
        """#202 and #204's defect, refused in both directions.

        A gate branch offering a step wins on every one of the eight readings
        the other three inputs can make, open scanner or shut. This is the case
        that goes red if the scanner clause is ever conjoined onto the gate
        answer, which is what made a gate standing on grid invisible before.
        """
        for warp_offered in (True, False):
            for gate_in_reach in (True, False):
                for window_closed in (True, False):
                    self.assertEqual(
                        self.step(True, warp_offered, gate_in_reach,
                                  window_closed),
                        "WorkTheAccelerationGate",
                        "warp_offered=%s gate_in_reach=%s window_closed=%s"
                        % (warp_offered, gate_in_reach, window_closed))

    def test_the_hunt_loop_is_still_reached_with_nothing_offered(self):
        """The existing fallback, in both scanner states.

        Nothing about this gate may change what a reading with no gate step and
        no tracker step does -- it went to the scanner before and it still does.
        """
        for gate_in_reach in (True, False):
            for window_closed in (True, False):
                self.assertEqual(
                    self.step(False, False, gate_in_reach, window_closed),
                    "HuntWithTheProbeScanner",
                    "gate_in_reach=%s window_closed=%s"
                    % (gate_in_reach, window_closed))

    def test_a_gate_in_reach_still_declines_the_opportunity(self):
        """#147's clause, with the scanner shut so nothing else can decline it.

        The gate branch answers `Nothing` once it has given up, and without this
        clause the very next reading falls into run 5's click that achieved
        nothing for 3,458 readings. The new clause joins it rather than
        replacing it.
        """
        self.assertEqual(
            self.step(gate_step=False, warp_offered=True,
                      gate_in_reach=True, window_closed=True),
            "HuntWithTheProbeScanner")

    def test_the_two_clauses_are_both_required(self):
        """Neither one on its own admits the step.

        Written as the three neighbours of the one state that takes it, so a
        rule that had dropped either clause answers `WarpToTheOpportunitySite`
        somewhere here.
        """
        self.assertEqual(self.step(False, True, True, True),
                         "HuntWithTheProbeScanner")
        self.assertEqual(self.step(False, True, False, False),
                         "HuntWithTheProbeScanner")
        self.assertEqual(self.step(False, True, True, False),
                         "HuntWithTheProbeScanner")
        self.assertEqual(self.step(False, True, False, True),
                         "WarpToTheOpportunitySite")


class TheRuleAgainstRealReadingsTest(unittest.TestCase):
    """The same rule, resolved against what the real parser made of a UI tree.

    Every input but the gate branch's own step is read off the reading here, so
    what the cases assert on is the bot's own view of a client with the scanner
    open and of the same client with it shut.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def step_for(self, children):
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> siteProgressStep"
             " { gateBranchOffersAStep = False"
             " , warpToSiteIsOffered ="
             " warpToOpportunitySiteIfAvailable r /= Nothing"
             " , gateWithinReach = accelerationGateIsWithinReach r"
             " , probeScannerWindowIsClosed = r.probeScannerWindow == Nothing"
             " } == %s) |> Maybe.withDefault False" % step
             for step in STEPS],
            definitions=[TrackerRepl.reading_binding("reading", children)])
        chosen = [step for step, yes in zip(STEPS, answers) if yes]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step, got %s" % chosen)
        return chosen[0]

    def test_the_fixtures_differ_only_in_the_scanner_window(self):
        """The control, before anything is concluded from the pair.

        A case built on a tree the parser makes nothing of would pass or fail
        for reasons that have nothing to do with the rule, so the parser is
        asked directly whether it saw a window in one reading and not the other,
        and whether the tracker's step survived in both.
        """
        for children, expected_window, label in (
                (reading(gate_distance="40 km") + [tracker_offering_a_step()],
                 "False", "scanner shut"),
                (reading(gate_distance="40 km")
                 + [tracker_offering_a_step(), probe_scanner_window()],
                 "True", "scanner open")):
            window, offered = self.repl.evaluate([
                "reading |> Maybe.map (\\r -> r.probeScannerWindow /= Nothing)"
                " |> Maybe.withDefault False",
                "reading |> Maybe.map (\\r ->"
                " warpToOpportunitySiteIfAvailable r /= Nothing)"
                " |> Maybe.withDefault False"],
                definitions=[TrackerRepl.reading_binding("reading", children)])
            self.assertEqual(str(window), expected_window, label)
            self.assertTrue(offered, label)

    def test_a_reading_with_no_probe_window_takes_the_step(self):
        self.assertEqual(
            self.step_for(reading(gate_distance="40 km")
                          + [tracker_offering_a_step()]),
            "WarpToTheOpportunitySite")

    def test_the_same_reading_with_the_window_open_does_not(self):
        """And the window is open holding no scan results at all.

        That is the reading of "closed" this change refuses -- a scanner with
        nothing useful in it is still a scanner the operator left open.
        """
        self.assertEqual(
            self.step_for(reading(gate_distance="40 km")
                          + [tracker_offering_a_step(), probe_scanner_window()]),
            "HuntWithTheProbeScanner")

    def test_a_gate_in_reach_wins_with_the_window_shut(self):
        """#147 on a real reading, with the new clause satisfied.

        The gate branch is handed `False` here, so what declines the tracker is
        the reading's own gate distance rather than anything about the scanner.
        """
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker_offering_a_step()]),
            "HuntWithTheProbeScanner")


class TheWiringExecutedTest(unittest.TestCase):
    """The wiring's own expression, run against both readings.

    `TheRuleAgainstRealReadingsTest` builds the record itself, so it cannot see
    a wiring that answers the opposite question -- and `siteProgressStepOrElse`
    takes a whole `BotDecisionContext`, which no case here can assemble. What is
    executable is the expression: it is cut out of the source, pointed at the
    reading rather than at the context, and asked about a client with the
    scanner shut and the same client with it open.

    That is the half a substring read cannot do. The first pass had only the
    read below, and `/= Nothing` in place of `== Nothing` -- a wiring that takes
    the tracker's step exactly when it must not -- failed one case, on a string
    rather than on an answer.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)
        source = source_of(SAXRAT_BOT_ELM)
        binding = collapsed(without_line_comments(
            body_of(source, "siteProgressStepOrElse")))
        match = re.search(r"probeScannerWindowIsClosed = (.*?) \}", binding)
        assert match, "no probeScannerWindowIsClosed in siteProgressStepOrElse"
        cls.expression = match.group(1).replace(
            "context.readingFromGameClient", "r")

    def closed_for(self, children):
        return self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> %s) |> Maybe.withDefault False"
             % self.expression],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_a_reading_with_no_scanner_window_reads_as_closed(self):
        self.assertTrue(self.closed_for(
            reading(gate_distance="40 km") + [tracker_offering_a_step()]))

    def test_an_open_scanner_holding_nothing_does_not_read_as_closed(self):
        """Both halves of the rejected reading, in one case.

        The window is there and it holds no scan results, so a wiring over
        `scanResults` and a wiring that inverted the comparison both answer
        `True` here, and the shipped one answers `False`.
        """
        self.assertFalse(self.closed_for(
            reading(gate_distance="40 km")
            + [tracker_offering_a_step(), probe_scanner_window()]))


class TheWiringTest(unittest.TestCase):
    """What `siteProgressStepOrElse` hands the rule, which is not an expression.

    The rule takes a record of `Bool`s and cannot see where they came from, so
    a wiring that answered the opposite question -- or the rejected one -- would
    satisfy every case above.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.binding = collapsed(without_line_comments(
            body_of(cls.source, "siteProgressStepOrElse")))

    def test_the_rule_is_told_whether_the_window_is_absent_from_the_reading(self):
        self.assertIn(
            "probeScannerWindowIsClosed ="
            " context.readingFromGameClient.probeScannerWindow == Nothing",
            self.binding)

    def test_it_is_the_window_rather_than_its_scan_results(self):
        """The reading of "closed" that was weighed and rejected.

        A wiring over `scanResults` would answer "the scanner is holding nothing
        useful", which is a fact about the system rather than an act by the
        operator -- and it is true on readings nobody has touched the scanner
        on.
        """
        self.assertNotIn("scanResults", self.binding)

    def test_the_gate_answer_is_not_told_about_the_window(self):
        """#204, refused at the wiring as well as in the rule.

        `activateAccelerationGateIfPresent` is asked before the record is built
        and reaches for nothing about the scanner, so no reading of the window
        can make the gate step invisible.
        """
        gate_branch = collapsed(without_line_comments(
            body_of(self.source, "activateAccelerationGateIfPresent")))
        self.assertNotIn("probeScannerWindow", gate_branch)
        self.assertIn(
            "accelerationGateStep = activateAccelerationGateIfPresent context",
            self.binding)


class TheDeclineIsNotAWaitTest(unittest.TestCase):
    """A declined opportunity hands the reading on rather than holding it.

    PR #257 shipped green and stopped the bot dead for 108 minutes -- 0
    anomalies, 0 warps to site -- by adding a step on this path that could
    decline forever. This gate declines a great deal more often than that step
    did, so the property has to be structural rather than argued: every one of
    the rule's three answers runs a branch, and the one this gate produces is
    the caller's own `ifNeither`.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.binding = collapsed(without_line_comments(
            body_of(cls.source, "siteProgressStepOrElse")))

    def test_the_hunt_answer_is_the_callers_own_step(self):
        self.assertRegex(self.binding,
                         r"HuntWithTheProbeScanner\s*->\s*ifNeither")

    def test_nothing_in_the_dispatch_waits(self):
        """No leaf of its own, in any of the three arms."""
        self.assertNotIn("waitForProgressInGame", self.binding)
        self.assertNotIn("askForHelpToGetUnstuck", self.binding)

    def test_both_callers_supply_a_floor_that_acts(self):
        """The scanner arm's own scan results, and leaving the system.

        Neither is a wait, so a reading this gate declines is spent on work
        whichever arm of `decideNextActionWhenInSpace` it came through.
        """
        whole = collapsed(without_line_comments(self.source))
        self.assertIn(
            "siteProgressStepOrElse context pickAnotherAnomalyOrLeaveViaScanResults",
            whole)
        self.assertIn("siteProgressStepOrElse context (jumpToNextSystem context)",
                      whole)


class TheRecordedRunsPriceThisTest(unittest.TestCase):
    """What the gate costs, measured on the corpus rather than guessed at.

    Counted in **readings** and not decision lines: the host reprints the whole
    decision block on every log line, and reading that as a rate is the mistake
    that has cost `stall_watch.py` two threshold calibrations, #141 a retreat
    measurement and #164 a whole diagnosis. One `RequestToVolatileProcess`
    read-from-game task is one reading.

    `decideNextActionWhenInSpace` prints `No probe window` on every reading it
    takes the closed arm, and one of the anomaly/scan-result labels on the open
    one, so a reading in space and not warping says which it was.

    Asserted as relations rather than as counts, so a growing corpus cannot turn
    a true claim red.
    """

    READ = re.compile(r"task read-from-game-\d+: RequestToVolatileProcess")
    CLOSED = "No probe window"
    OPEN_MARKERS = (
        "We are in anomaly ",
        "Looks like we are not in an anomaly.",
        "The anomaly no longer shows on the scanner",
        "Found matching anomaly.",
    )
    OPEN_SCAN_RESULTS = re.compile(r"^I see \d+ scan results")
    OPPORTUNITY = ("The Opportunities tracker offers",
                   "'Warp to Site' opportunity")

    @classmethod
    def setUpClass(cls):
        cls.logs = sorted(
            glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
        if not cls.logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "say about how often the probe scanner window is open cannot "
                "be consulted here")
        cls.census = [cls.count(path) for path in cls.logs]
        # A sample thinner than the floors below cannot say anything about how
        # often a window is open, so it skips rather than passing on nothing.
        # Evidence that is present and disagrees is still a failure.
        if sum(run["open"] + run["closed"] for run in cls.census) < 5000:
            raise unittest.SkipTest(
                "no recorded saxrat runs with enough in-space readings to say "
                "how often the probe scanner window is open")

    @classmethod
    def count(cls, path):
        """Per run: readings with the window open, closed, and taking a step."""
        tally = {"open": 0, "closed": 0, "opportunity": 0,
                 "opportunity_open": 0, "opportunity_closed": 0}
        current = {"open": False, "closed": False, "opportunity": False}
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if cls.READ.search(line):
                    if current["closed"]:
                        tally["closed"] += 1
                    elif current["open"]:
                        tally["open"] += 1
                    if current["opportunity"]:
                        tally["opportunity"] += 1
                        # The closed arm wraps everything it reaches in its own
                        # `No probe window`, so a reading that took a step and
                        # never printed it was taken with the window open.
                        if current["closed"]:
                            tally["opportunity_closed"] += 1
                        else:
                            tally["opportunity_open"] += 1
                    current = {"open": False, "closed": False,
                               "opportunity": False}
                    continue
                if not line.startswith("+ "):
                    continue
                text = line.rstrip("\n")[2:]
                if text == cls.CLOSED:
                    current["closed"] = True
                elif (text.startswith(cls.OPEN_MARKERS)
                      or cls.OPEN_SCAN_RESULTS.match(text)):
                    current["open"] = True
                if any(marker in text for marker in cls.OPPORTUNITY):
                    current["opportunity"] = True
        return tally

    def totals(self, *keys):
        return [sum(run[key] for run in self.census) for key in keys]

    def test_the_corpus_carries_both_states(self):
        """The control: neither claim below rests on a state nobody recorded."""
        opened, closed = self.totals("open", "closed")
        self.assertGreater(opened, 1000)
        self.assertGreater(closed, 100)

    def test_the_window_is_open_on_the_great_majority_of_in_space_readings(self):
        """Which is the cost, stated as the relation.

        The gate declines the tracker's step on every one of these, so a corpus
        this lopsided means the escalation work is switched off unless somebody
        closes the scanner on purpose.
        """
        opened, closed = self.totals("open", "closed")
        self.assertGreater(opened, closed * 20)

    def test_most_runs_never_closed_the_scanner_at_all(self):
        """Per run rather than pooled, so one long run cannot carry the claim."""
        never = [run for run in self.census
                 if run["open"] + run["closed"] > 0 and run["closed"] == 0]
        with_any = [run for run in self.census
                    if run["open"] + run["closed"] > 0]
        self.assertGreater(len(with_any), 20)
        self.assertGreater(len(never), len(with_any) // 2)

    def test_almost_every_recorded_opportunity_step_had_the_window_open(self):
        """The sharpest form of the cost, on the readings that actually acted.

        These are the readings the gate would have declined. If this ever stops
        holding it means somebody has started flying with the scanner shut,
        which is the behaviour the gate is for.
        """
        taken, with_open, with_closed = self.totals(
            "opportunity", "opportunity_open", "opportunity_closed")
        self.assertGreater(taken, 500)
        self.assertGreater(with_open, taken * 0.9)
        self.assertLess(with_closed, taken * 0.05)

    def test_the_unit_is_the_reading_and_not_the_decision_line(self):
        """The premise every count above rests on.

        A run prints its decision block several times per reading, so counting
        lines would report a rate three to four times larger. Asserted as the
        relation between the two on a run that carries both.
        """
        for path, tally in zip(self.logs, self.census):
            if tally["closed"] < 50:
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = sum(1 for line in handle
                            if line.rstrip("\n")[2:] == self.CLOSED
                            and line.startswith("+ "))
            self.assertGreater(lines, tally["closed"],
                               "%s: %d lines against %d readings"
                               % (os.path.basename(path), lines,
                                  tally["closed"]))
            return
        self.skipTest("no recorded saxrat runs closed the scanner often enough "
                      "to compare lines against readings")


class TheGateIsNamedWhereItIsArguedTest(unittest.TestCase):
    """The doc comments carry the decision and its relation to #202 and #204.

    Somebody reading `siteProgressStep` next has to be able to tell this apart
    from the defect those two fixed, and the two functions are where they will
    be looking rather than in a merged pull request.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    def doc_of(self, name):
        """The `{-| ... -}` block immediately above a declaration."""
        match = re.search(
            r"\{-\|((?:(?!-\}).)*)-\}\s*\n(?:type |)%s\b" % re.escape(name),
            self.source, re.S)
        self.assertIsNotNone(match, "no doc comment above %r" % name)
        return collapsed(match.group(1))

    def test_the_rule_says_the_gate_is_not_the_thing_being_gated(self):
        doc = self.doc_of("SiteProgressStep")
        self.assertIn("probe scanner window is closed", doc)
        self.assertIn("#202", doc)
        self.assertIn("#204", doc)

    def test_the_dispatch_names_the_defect_this_is_not(self):
        doc = self.doc_of("siteProgressStepOrElse")
        self.assertIn("#202", doc)
        self.assertIn("#204", doc)
        self.assertIn("#257", doc)
