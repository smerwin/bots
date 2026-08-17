"""An arrival the Opportunities tracker offers is taken before the gate (#261).

`siteProgressStep` had one opportunity tier and it sat **below** the
acceleration gate, which is #147's ordering: a gate on the grid is progress
inside the site the ship is already in, and the tracker's button is how the ship
reaches the next one, so the gate wins and the tracker's step is additionally
declined while a gate is in reach.

**That argument is about a label the ship has not travelled to yet.** #256 split
the tracker's vocabulary in two: `opportunityArrivalCommandLabels` --
`warp to site`, `warp to location`, `dock` -- is the client saying the
escalation is reachable from where the ship is standing, and `jump` and
`set destination` are it offering to leave for one somewhere else. Run 38 is
what conflating them cost: three `Sansha's Command Relay Outpost` entries, the
reachable one second, `Jump` pressed 1,989 times and not one warp to a site.

So an arrival is asked **above** the gate now, and the travelling case is
untouched -- it still loses to a gate that offers a step and still carries
`not gateWithinReach`. What this file has to hold is the scope of that reversal
as much as the reversal itself, which is why the rule is executed over **every**
one of the 32 states its five booleans can make, against a table written out
rather than recomputed.

The new tier carries the scanner clause the existing one grew in #260, so the
operator's switch stays one switch: an arrival offered with the probe scanner
window open is declined exactly as a travelling step is.

**`arrivalIsOffered` is derived from the parsed tracker and not from a search.**
The rule is a function of booleans and cannot see where they came from, so
`TheWiringExecutedTest` cuts the expression out of `siteProgressStepOrElse` and
runs it against readings the real `EveOnline.ParseUserInterface` produced -- a
wiring answering "any command label" rather than "an arrival label" satisfies
every case over the rule, and is exactly the mistake the misleadingly named
`warpToSiteIsOffered` invites.

**What the bot does when this tier declines is asserted rather than argued.**
PR #257 shipped green and blocked the bot for 108 minutes by putting a step on
this exact path that could decline forever. Two properties cover it here:
a declined arrival falls through to the gate and then to the caller's own
`ifNeither`, which is a branch that acts; and the arrival answer itself cannot
decline, because `arrivalIsOffered` is read off the very step the warp arm
presses -- `TheArrivalAnswerAlwaysHasAStepToPressTest` executes that pairing
over every fixture rather than reading it out of the source.

Confirmed by mutation, twelve of them, each watched failing a named case: the
new tier deleted (the behaviour reverted); the new tier moved below the gate;
its scanner clause dropped; its scanner clause inverted; the tier reading
`warpToSiteIsOffered` rather than `arrivalIsOffered`, so a `Jump` outranks a
gate; `not gateWithinReach` dropped from the travelling tier; the travelling
tier's scanner clause dropped; the gate tier given a scanner clause (#204's
defect, restored); the wiring asking `travelLabelIsACommand` instead of
`opportunityLabelArrivesAtTheSite`; the wiring reading the panel's first entry
rather than the step the click is aimed at, so a panel whose first entry travels
and whose second arrives fires the tier while the click presses a different
button; the arrival answer wired to `ifNeither`; and the doc comment no longer
recording the reversal.

**One of those twelve is caught by a source read alone and says so here.**
Wiring `WarpToTheOpportunitySite -> ifNeither` is #257's shape -- a tier that
fires and hands the reading on for ever -- and only
`test_the_warp_answer_is_still_the_warp_branch` fails on it, because
`siteProgressStepOrElse` takes a whole `BotDecisionContext` no case in this
suite can assemble. `test_saxrat_opportunity_needs_the_probe_window_closed.py`
reads the same dispatch the same way and for the same reason; what is executed
instead is the pairing that makes the arm reachable at all.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_gate_panel_button import reading
from test_saxrat_opportunity_needs_the_probe_window_closed import (
    probe_scanner_window)
from test_saxrat_opportunity_shadow import let_binding_of, without_line_comments
from test_saxrat_opportunity_tracker_button import (
    TrackerRepl, expanded_entry, progress_bar, tracker, travel_button)
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, body_of, collapsed, source_of)

GATE = "WorkTheAccelerationGate"
WARP = "WarpToTheOpportunitySite"
HUNT = "HuntWithTheProbeScanner"
STEPS = (GATE, WARP, HUNT)

# The three arrival labels and the two travelling ones, as #256 sorted them.
ARRIVAL_LABELS = ["Warp to Site", "Warp to Location", "Dock"]
TRAVELLING_LABELS = ["Jump", "Set Destination"]

# Every state the five booleans can make, and what the ordering the owner chose
# answers for it. Written out rather than recomputed: a Python restatement of
# the rule would test the restatement, and this table is the specification.
#
# The key is `gate step / arrival / warp offered / gate in reach / scanner shut`.
#
# Two of the columns are not independent in a real reading -- an arrival on
# offer means a step is on offer -- so the rows with `arrival` set and `warp`
# clear are unreachable through `siteProgressStepOrElse` and are here because
# the rule is a total function over its own inputs.
EXPECTED = {
    "00000": HUNT, "00001": HUNT, "00010": HUNT, "00011": HUNT,
    "00100": HUNT, "00101": WARP, "00110": HUNT, "00111": HUNT,
    "01000": HUNT, "01001": WARP, "01010": HUNT, "01011": WARP,
    "01100": HUNT, "01101": WARP, "01110": HUNT, "01111": WARP,
    "10000": GATE, "10001": GATE, "10010": GATE, "10011": GATE,
    "10100": GATE, "10101": GATE, "10110": GATE, "10111": GATE,
    "11000": GATE, "11001": WARP, "11010": GATE, "11011": WARP,
    "11100": GATE, "11101": WARP, "11110": GATE, "11111": WARP,
}


def record(bits):
    """The rule's argument, spelled out from a five-character state."""
    gate, arrival, warp, reach, closed = (bit == "1" for bit in bits)
    return (
        "{ gateBranchOffersAStep = %s, arrivalIsOffered = %s"
        ", warpToSiteIsOffered = %s, gateWithinReach = %s"
        ", probeScannerWindowIsClosed = %s }"
        % tuple("True" if value else "False"
                for value in (gate, arrival, warp, reach, closed)))


def tracker_offering(labels):
    """The Opportunities panel with one expanded escalation per label.

    Each entry gets its own `_name`, the way the client numbers them, so a
    several-escalation panel is several entries rather than one repeated.
    """
    entries = []
    for index, text in enumerate(labels):
        # The progress bar rides along because the client always draws one
        # beside the button, and since the 0.5 gate it is where the trip's
        # destination is read from -- an entry without one has no readable
        # security and is refused, which would make every case here about the
        # gate rather than about the ordering it is testing.
        entry = expanded_entry([progress_bar(), travel_button(text)])
        entry["dictEntriesOfInterest"]["_name"] = (
            "escalation_sites:%d" % (50791 + index))
        entries.append(entry)
    return tracker(entries)


class TheRuleTest(unittest.TestCase):
    """`siteProgressStep`, executed at every one of its 32 states.

    Asked as three equalities per state rather than one, so a rule answering two
    things at once -- or none -- fails rather than passing on whichever
    constructor the table happened to name.
    """

    # Eight states an entry, which is 24 expressions -- the repl recompiles the
    # module per entry, so one entry per state would cost 32 compiles, and all
    # 32 in one entry is a single line of some twenty kilobytes.
    STATES_PER_ENTRY = 8

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)
        states = sorted(EXPECTED)
        cls.answered = {}
        for start in range(0, len(states), cls.STATES_PER_ENTRY):
            batch = states[start:start + cls.STATES_PER_ENTRY]
            expressions = []
            for bits in batch:
                expressions.extend(
                    "(siteProgressStep %s) == %s" % (record(bits), step)
                    for step in STEPS)
            answers = cls.repl.evaluate(expressions)
            for index, bits in enumerate(batch):
                cls.answered[bits] = [
                    step for step, yes
                    in zip(STEPS, answers[index * 3:index * 3 + 3]) if yes]

    def step(self, gate_step, arrival, warp_offered, gate_in_reach,
             window_closed):
        bits = "".join(
            "1" if value else "0"
            for value in (gate_step, arrival, warp_offered, gate_in_reach,
                          window_closed))
        chosen = self.answered[bits]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step for %s, got %s"
                         % (record(bits), chosen))
        return chosen[0]

    def test_the_whole_table(self):
        """All 32 states, so nothing the change touches is unexamined."""
        for bits in sorted(EXPECTED):
            with self.subTest(state=bits):
                self.assertEqual(self.answered[bits], [EXPECTED[bits]],
                                 record(bits))

    def test_an_arrival_beats_a_gate_that_offers_a_step(self):
        """The reversal, in the one state that is only about the reversal.

        Everything else here is what #147 asks for -- the gate has work to do,
        it is in reach, and under the old ordering it won. An arrival is the
        ship being told it can reach the escalation from where it stands, and
        that is now asked first.
        """
        self.assertEqual(
            self.step(gate_step=True, arrival=True, warp_offered=True,
                      gate_in_reach=True, window_closed=True),
            WARP)

    def test_the_same_arrival_declines_with_the_scanner_open(self):
        """#260's switch, and the whole of what the new tier costs.

        Stated as the comparison against the case above, which is what a clause
        satisfies and a tier without one does not: the reading is identical in
        every other respect and the gate takes it back.
        """
        self.assertEqual(
            self.step(gate_step=True, arrival=True, warp_offered=True,
                      gate_in_reach=True, window_closed=False),
            GATE)

    def test_a_travelling_label_still_loses_to_the_gate(self):
        """#147's ordering, unreversed, which is the scope of the change.

        Same reading as the reversal case with the arrival flag cleared -- a
        `Jump`, which is the ship offering to leave a site it is standing in the
        middle of.
        """
        self.assertEqual(
            self.step(gate_step=True, arrival=False, warp_offered=True,
                      gate_in_reach=True, window_closed=True),
            GATE)

    def test_the_travelling_tier_still_declines_beside_a_gate_in_reach(self):
        """#147's second half, which the ordering does not subsume.

        `activateAccelerationGateIfPresent` answers `Nothing` once it has given
        up on a gate, so with no clause here the very next reading falls into
        run 5's click that achieved nothing for 3,458 readings. The gate branch
        offers no step in this state, exactly as it does after a give-up.
        """
        self.assertEqual(
            self.step(gate_step=False, arrival=False, warp_offered=True,
                      gate_in_reach=True, window_closed=True),
            HUNT)
        self.assertEqual(
            self.step(gate_step=False, arrival=False, warp_offered=True,
                      gate_in_reach=False, window_closed=True),
            WARP)

    def test_an_arrival_is_not_declined_by_a_gate_in_reach(self):
        """Which is the same reversal read off the other clause.

        A gate in reach is what the travelling tier declines for, and it is the
        ordinary state for an arrival: gates exist only inside sites, so the
        ship is standing in one and the tracker is naming another it can reach.
        """
        self.assertEqual(
            self.step(gate_step=False, arrival=True, warp_offered=True,
                      gate_in_reach=True, window_closed=True),
            WARP)

    def test_the_gate_is_never_told_about_the_scanner(self):
        """#202 and #204, refused in the direction that hides the gate.

        With no arrival on offer the gate answer must not move for any reading
        of the window -- that coupling is what made a gate standing on grid
        invisible, and the new tier is a second place it could come back.
        """
        for warp_offered in (True, False):
            for gate_in_reach in (True, False):
                for window_closed in (True, False):
                    self.assertEqual(
                        self.step(True, False, warp_offered, gate_in_reach,
                                  window_closed),
                        GATE,
                        "warp=%s reach=%s closed=%s"
                        % (warp_offered, gate_in_reach, window_closed))

    def test_a_reading_offering_nothing_still_hunts(self):
        for gate_in_reach in (True, False):
            for window_closed in (True, False):
                self.assertEqual(
                    self.step(False, False, False, gate_in_reach,
                              window_closed),
                    HUNT)


class TheRuleAgainstRealReadingsTest(unittest.TestCase):
    """The same ordering, resolved against what the real parser made of a tree.

    Every input but the gate branch's own step is read off the reading, so what
    these assert on is the bot's own view of a client whose tracker offers an
    arrival and of the same client offering a `Jump`.
    `activateAccelerationGateIfPresent` takes a whole `BotDecisionContext` no
    case here can assemble, so that one is supplied and named.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def step_for(self, children, gate_offers_a_step):
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> siteProgressStep"
             " { gateBranchOffersAStep = %s"
             " , arrivalIsOffered ="
             " (opportunityTravelStep r |> Maybe.map (.label >>"
             " opportunityLabelArrivesAtTheSite) |> Maybe.withDefault False)"
             " , warpToSiteIsOffered ="
             " warpToOpportunitySiteIfAvailable r /= Nothing"
             " , gateWithinReach = accelerationGateIsWithinReach r"
             " , probeScannerWindowIsClosed = r.probeScannerWindow == Nothing"
             " } == %s) |> Maybe.withDefault False"
             % ("True" if gate_offers_a_step else "False", step)
             for step in STEPS],
            definitions=[TrackerRepl.reading_binding("reading", children)])
        chosen = [step for step, yes in zip(STEPS, answers) if yes]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step, got %s" % chosen)
        return chosen[0]

    def test_the_fixtures_differ_the_way_the_cases_say(self):
        """The control, before anything is concluded from the pair.

        A case built on a tree the parser makes nothing of would pass or fail
        for reasons that have nothing to do with the ordering, so the parser is
        asked directly what it made of each: a tracker step in both, an arrival
        in one, a gate in reach in both, and a scanner window in neither.
        """
        for text, arrives in (("Warp to Site", True), ("Jump", False)):
            children = (reading(gate_distance="1500 m")
                        + [tracker_offering([text])])
            offered, arrival, in_reach, window = self.repl.evaluate([
                "reading |> Maybe.map (\\r ->"
                " warpToOpportunitySiteIfAvailable r /= Nothing)"
                " |> Maybe.withDefault False",
                "reading |> Maybe.map (\\r -> opportunityTravelStep r"
                " |> Maybe.map (.label >> opportunityLabelArrivesAtTheSite)"
                " |> Maybe.withDefault False) |> Maybe.withDefault False",
                "reading |> Maybe.map accelerationGateIsWithinReach"
                " |> Maybe.withDefault False",
                "reading |> Maybe.map (\\r -> r.probeScannerWindow /= Nothing)"
                " |> Maybe.withDefault False"],
                definitions=[TrackerRepl.reading_binding("reading", children)])
            self.assertTrue(offered, text)
            self.assertEqual(arrival, arrives, text)
            self.assertTrue(in_reach, text)
            self.assertFalse(window, text)

    def test_an_arrival_beats_a_gate_offering_a_step(self):
        """The reversal, on a reading rather than on a record."""
        for text in ARRIVAL_LABELS:
            with self.subTest(label=text):
                self.assertEqual(
                    self.step_for(reading(gate_distance="1500 m")
                                  + [tracker_offering([text])],
                                  gate_offers_a_step=True),
                    WARP)

    def test_a_travelling_label_leaves_the_gate_its_step(self):
        for text in TRAVELLING_LABELS:
            with self.subTest(label=text):
                self.assertEqual(
                    self.step_for(reading(gate_distance="1500 m")
                                  + [tracker_offering([text])],
                                  gate_offers_a_step=True),
                    GATE)

    def test_an_arrival_with_the_scanner_open_leaves_the_gate_its_step(self):
        """The same client, with the window the operator did not close."""
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker_offering(["Warp to Site"]),
                             probe_scanner_window()],
                          gate_offers_a_step=True),
            GATE)

    def test_an_arrival_with_the_scanner_open_and_no_gate_step_hunts(self):
        """Which is what the bot does when this tier declines.

        The gate is in reach and has nothing to do -- the state after a give-up
        -- so the reading reaches the last resort, which is the caller's own
        branch and not a wait. `TheDeclineIsNotAWaitTest` is the other half.
        """
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker_offering(["Warp to Site"]),
                             probe_scanner_window()],
                          gate_offers_a_step=False),
            HUNT)

    def test_a_state_label_is_not_an_arrival(self):
        """`Warping` is the client saying the trip is already under way.

        It is not a command at all, so it reaches neither tier -- and the tier
        added here must not be the thing that starts re-commanding a manoeuvre
        (#99).
        """
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker_offering(["Warping"])],
                          gate_offers_a_step=True),
            GATE)

    def test_the_arriving_entry_beside_a_travelling_one_fires_the_tier(self):
        """Run 38's panel: the reachable escalation is not the first listed.

        #256 made the *click* prefer the arriving entry; this is the tier
        agreeing with it. A wiring that read the panel's first entry instead
        would answer `False` here and the gate would take the reading while the
        click, when it eventually came, pressed the arrival.
        """
        self.assertEqual(
            self.step_for(reading(gate_distance="1500 m")
                          + [tracker_offering(["Jump", "Warp to Site", "Jump"])],
                          gate_offers_a_step=True),
            WARP)


class TheWiringExecutedTest(unittest.TestCase):
    """`arrivalIsOffered`'s own expression, cut out and run against readings.

    The rule takes booleans and cannot see where they came from, and
    `siteProgressStepOrElse` takes a whole `BotDecisionContext` no case here can
    assemble -- so a wiring that answered "any step the tracker offers" would
    satisfy every case above while making a `Jump` outrank a gate. What is
    executable is the expression, pointed at the reading rather than at the
    context.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)
        binding = let_binding_of(
            without_line_comments(
                body_of(source_of(SAXRAT_BOT_ELM), "siteProgressStepOrElse")),
            "arrivalIsOffered")
        # Two substitutions now: the reading, and the settings the destination
        # gate is asked against. `defaultBotSettings` rather than a literal so
        # the cases run at the shipped 0.5 rather than at a number written here.
        cls.expression = (
            binding
            .replace("context.eventContext.botSettings", "defaultBotSettings")
            .replace("context.readingFromGameClient", "r"))

    def offered_for(self, children):
        return self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> %s) |> Maybe.withDefault False"
             % self.expression],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_every_arrival_label_reads_as_an_arrival(self):
        for text in ARRIVAL_LABELS:
            with self.subTest(label=text):
                self.assertTrue(self.offered_for([tracker_offering([text])]))

    def test_no_travelling_label_does(self):
        """The distinction the whole tier rests on."""
        for text in TRAVELLING_LABELS:
            with self.subTest(label=text):
                self.assertFalse(self.offered_for([tracker_offering([text])]))

    def test_a_state_label_does_not(self):
        for text in ["Warping", "Docking", "Destination Set"]:
            with self.subTest(label=text):
                self.assertFalse(self.offered_for([tracker_offering([text])]))

    def test_a_panel_with_no_tracker_at_all_does_not(self):
        self.assertFalse(self.offered_for(reading(gate_distance="1500 m")))

    def test_an_arrival_behind_a_travelling_entry_still_reads_as_one(self):
        """Run 38's panel again, at the expression rather than at the rule."""
        self.assertTrue(
            self.offered_for([tracker_offering(["Jump", "Dock", "Jump"])]))

    def test_a_hidden_arrival_is_not_offered(self):
        """The client hides the tasks that are not available.

        So a `Warp to Site` the panel is not showing must not outrank a gate.
        """
        self.assertFalse(self.offered_for([tracker([expanded_entry(
            [travel_button("Warp to Site", displayed=False)])])]))


class TheWiringTest(unittest.TestCase):
    """What `siteProgressStepOrElse` hands the rule, which is not an expression.

    The executed cases above cover what the expression answers; these cover
    where it came from, because two rules that agree on every fixture can still
    be the wrong one -- `travelLabelIsACommand` and
    `opportunityLabelArrivesAtTheSite` differ only on two words.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.binding = collapsed(without_line_comments(
            body_of(cls.source, "siteProgressStepOrElse")))

    def test_the_rule_is_told_whether_an_arrival_is_offered(self):
        self.assertIn("arrivalIsOffered = arrivalIsOffered", self.binding)

    def test_it_is_read_off_the_step_the_click_is_aimed_at(self):
        """`opportunityTravelStep`, which is what `warpToOpportunitySiteIfAvailable`
        presses, so the tier and the click cannot disagree about which entry the
        panel is offering."""
        binding = let_binding_of(
            without_line_comments(body_of(self.source, "siteProgressStepOrElse")),
            "arrivalIsOffered")
        # Narrowed since the 0.5 gate, and it has to be the *same* narrowing
        # the click gets or the tier and the press disagree about which entry
        # the panel is offering -- which is the whole point of this case.
        self.assertIn(
            "opportunityTravelStep (escalationEntriesPermitted"
            " context.eventContext.botSettings context.readingFromGameClient)",
            binding)
        self.assertIn("opportunityLabelArrivesAtTheSite", binding)

    def test_it_is_the_arrival_rule_rather_than_the_command_rule(self):
        """The one that admits `Jump`, which is the ordering being reversed."""
        binding = let_binding_of(
            without_line_comments(body_of(self.source, "siteProgressStepOrElse")),
            "arrivalIsOffered")
        self.assertNotIn("travelLabelIsACommand", binding)

    def test_it_is_not_a_search_over_the_tree(self):
        """#252 removed that from this branch, and it answered `Just` after the
        ship arrived -- which is the premise the whole ordering rests on.

        Asked of the binding rather than of the file: `findUiElementWithText`
        is a general helper other branches still use, and asserting its absence
        everywhere would be a claim about them.
        """
        binding = let_binding_of(
            without_line_comments(body_of(self.source, "siteProgressStepOrElse")),
            "arrivalIsOffered")
        self.assertNotIn("findUiElementWithText", binding)
        self.assertNotIn('findUiElementWithText "Warp to Site"',
                         collapsed(self.source))

    def test_the_gate_answer_is_still_the_gate_branch(self):
        self.assertRegex(
            self.binding,
            r"WorkTheAccelerationGate -> accelerationGateStep \|> Maybe\.withDefault")

    def test_the_warp_answer_is_still_the_warp_branch(self):
        """Both tiers answer `WarpToTheOpportunitySite`, so both press this."""
        self.assertRegex(
            self.binding,
            r"WarpToTheOpportunitySite -> opportunityWarpStep \|> Maybe\.withDefault")

    def test_the_existing_tier_is_unchanged(self):
        """Read off the rule rather than off the wiring.

        The travelling clause is the one #147 and #260 wrote, and the change is
        a tier above it rather than an edit to it.
        """
        rule = collapsed(without_line_comments(
            body_of(self.source, "siteProgressStep")))
        self.assertIn(
            "progressCase.warpToSiteIsOffered"
            " && progressCase.probeScannerWindowIsClosed"
            " && not progressCase.gateWithinReach", rule)

    def test_the_new_tier_is_asked_before_the_gate(self):
        """The ordering as it stands in the source, since the table cannot say
        *where* the tier is -- only what it answers."""
        rule = collapsed(without_line_comments(
            body_of(self.source, "siteProgressStep")))
        arrival = rule.index("progressCase.arrivalIsOffered")
        gate = rule.index("progressCase.gateBranchOffersAStep then")
        self.assertLess(arrival, gate)

    def test_the_new_tier_carries_the_scanner_clause(self):
        rule = collapsed(without_line_comments(
            body_of(self.source, "siteProgressStep")))
        self.assertIn(
            "if progressCase.arrivalIsOffered"
            " && progressCase.probeScannerWindowIsClosed then", rule)


class TheArrivalAnswerAlwaysHasAStepToPressTest(unittest.TestCase):
    """The property that makes the new tier unable to decline forever.

    PR #257 blocked the bot for 108 minutes with a step on this path that could
    decline on every reading. This tier cannot: `arrivalIsOffered` is read off
    the same `opportunityTravelStep` that `warpToOpportunitySiteIfAvailable`
    wraps, so wherever the tier fires the warp arm has a click to dispatch and
    the `Maybe.withDefault ifNeither` beside it is unreachable.

    Executed as the implication over every fixture rather than read out of the
    source, because it is a claim about two functions agreeing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def pair_for(self, children):
        return self.repl.evaluate([
            "reading |> Maybe.map (\\r -> opportunityTravelStep r"
            " |> Maybe.map (.label >> opportunityLabelArrivesAtTheSite)"
            " |> Maybe.withDefault False) |> Maybe.withDefault False",
            "reading |> Maybe.map (\\r ->"
            " warpToOpportunitySiteIfAvailable r /= Nothing)"
            " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding("reading", children)])

    def test_an_arrival_on_offer_always_has_a_click(self):
        panels = [[text] for text in ARRIVAL_LABELS + TRAVELLING_LABELS]
        panels += [["Jump", "Dock"], ["Warping", "Warp to Site"],
                   ["Warping"], []]
        fired = 0
        for labels in panels:
            with self.subTest(panel=labels):
                arrival, offered = self.pair_for([tracker_offering(labels)])
                if arrival:
                    fired += 1
                    self.assertTrue(
                        offered,
                        "the tier fires on %s and the warp arm has nothing to "
                        "press, so the reading would fall to `ifNeither`"
                        % labels)
        self.assertGreater(fired, 2, "no fixture ever fired the tier, so the "
                                     "implication above held vacuously")


class TheDeclineIsNotAWaitTest(unittest.TestCase):
    """Where a declined arrival goes, and that every answer runs a branch.

    The tier declines on the overwhelming majority of readings -- the scanner
    window is open on 98.7% of the corpus -- so this is the ordinary path rather
    than an edge case.
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
        self.assertNotIn("waitForProgressInGame", self.binding)
        self.assertNotIn("askForHelpToGetUnstuck", self.binding)

    def test_both_callers_supply_a_floor_that_acts(self):
        whole = collapsed(self.source)
        self.assertIn(
            "siteProgressStepOrElse context"
            " pickAnotherAnomalyOrLeaveViaScanResults", whole)
        self.assertIn("siteProgressStepOrElse context (jumpToNextSystem context)",
                      whole)


class TheReversalIsRecordedWhereItIsArguedTest(unittest.TestCase):
    """The doc comments say #147 was reversed and how far.

    Somebody reading `siteProgressStep` next finds the gate-first argument in
    full and has to be able to tell that it was overturned for one tier on
    purpose rather than forgotten -- and that the travelling case still carries
    it. That is a claim about the file rather than about a merged pull request.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    def doc_of(self, name):
        match = re.search(
            r"\{-\|((?:(?!-\}).)*)-\}\s*\n(?:type |)%s\b" % re.escape(name),
            self.source, re.S)
        self.assertIsNotNone(match, "no doc comment above %r" % name)
        return collapsed(match.group(1))

    def test_the_type_records_the_reversal_and_names_the_issue(self):
        doc = self.doc_of("SiteProgressStep")
        self.assertIn("#147", doc)
        self.assertIn("reversed", doc)
        self.assertIn("arrival", doc)

    def test_the_type_records_the_scope(self):
        """The half a later reader most needs: what did *not* change."""
        doc = self.doc_of("SiteProgressStep")
        self.assertIn("opportunityArrivalCommandLabels", doc)
        self.assertIn("not gateWithinReach", doc)

    def test_the_type_still_carries_the_argument_being_overturned(self):
        """The gate-first reasoning stays, so the reversal can be weighed."""
        doc = self.doc_of("SiteProgressStep")
        self.assertIn("gates exist only inside sites", doc)

    def test_the_dispatch_says_where_the_answer_comes_from(self):
        doc = self.doc_of("siteProgressStepOrElse")
        self.assertIn("arrivalIsOffered", doc)
        self.assertIn("opportunityTravelStep", doc)

    def test_the_dispatch_still_separates_this_from_202_and_204(self):
        """#260's clause is now on two tiers, so the polarity note has to hold
        for both."""
        doc = self.doc_of("siteProgressStepOrElse")
        self.assertIn("#202", doc)
        self.assertIn("#204", doc)
        self.assertIn("#257", doc)

    def test_the_travel_step_no_longer_claims_the_ordering_is_untouched(self):
        """`opportunityTravelStep` carried "#147's ordering is untouched", which
        is the sentence this change makes false for three of its five labels."""
        doc = self.doc_of("opportunityTravelStep")
        self.assertNotIn("#147's ordering is untouched.", doc)
        self.assertIn("#147", doc)
        self.assertIn("arrival", doc)


if __name__ == "__main__":
    unittest.main()
