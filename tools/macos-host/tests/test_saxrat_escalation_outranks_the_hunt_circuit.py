"""The hunt circuit stands down for an escalation the tracker is working.

Issue #279. `setRouteToNextHuntingGround` is the one branch that lets saxrat
originate a route, and it had two answers: ask the host for the next hunting
ground, or -- where the circuit names nowhere -- `tetherAtStructure`, which
docks. Beside an escalation the Opportunities tracker is working, both are
wrong, and the second is wrong in the direction that costs a session.

**The two decisions #279 names are one clause, and the first has no content on
its own.** *Whether the floor may ask at all when the circuit is empty* changes
nothing by itself: with no `hunt-system` configured `nextHuntingGround` is
already `Nothing`, so the floor never asks -- it answers `NowhereToAskFor` and
tethers. What parks the ship is what the ask falls through to. So the
load-bearing decision is the second, *whether an escalation in progress
suppresses the circuit outright*, and the first is satisfied by it: an existing
route is still travelled by `jumpToNextSystem`, which this branch is only
reached from when there is none.
`TheEmptyCircuitFallsBackRatherThanAskingTest` executes that claim rather than
leaving it as an argument, because it is the reason the change is shaped the way
it is.

**That class also covers the owner's follow-up**, which lands on the same
decision point: with the circuit empty the bot travels to `home-system` and then
to the station it last undocked from, rather than tethering. `home-system` was
**unreachable** in exactly that state -- `huntingGroundAtIndex` consults it only
once a lap is complete and computed the lap count by dividing by the circuit's
length, so an empty circuit pinned it at zero and its own fallback was code
nothing could run. The station rung needed no new state:
`lastDockedStationNameFromInfoPanel` is already in `BotMemory`. Its one hazard
is #262's -- a station name is not a system name, so the picker's existing "not
here" equality cannot see that the ship is standing at it, and asking for a
route to a station in this system latches the give-up for the session.

**The contention half is recorded in this machine's own corpus.** Counted in
readings rather than decision lines, `saxrat_run46` cycles: the circuit asks the
host for `Shumam`, the tracker's own `Set Destination` puts the escalation back,
the ship jumps for eighteen readings, and the circuit asks for `Shumam` again --
four complete cycles, 25 ask readings interleaved into 123 opportunity readings,
every one of them naming `Sansha's Command Relay Outpost`. Runs 43 and 44 carry
the same shape. Two controllers, two destinations, each overwriting the other's.

**Scoped to a shut probe scanner, which is #260's switch rather than a second
one.** The scanner window is the operator's mode switch: open, the bot flies its
hunting circuit and collects escalations; shut, it goes and flies the ones it
collected. With it open `siteProgressStep` declines the tracker's step outright,
so holding the ship in the system would hold it away from the hunt it is
actually doing. Recounted here rather than inherited: over the 53 saxrat runs on
this machine that reached space, the scanner is open on 160,171 in-space
readings against 1,862 shut -- **1.15%** -- and 36 of the 53 never shut it once.

**The hold is bounded, and the bound is placed in a gap the corpus draws.**
Over the four runs that ever took a step from the tracker there are 307 gaps
between two consecutive readings on which the panel offered a pressable command:
median 1, p95 20, largest **30**, and nothing at all between 31 and the end of a
run. #279's own run held the floor for **414** consecutive readings. So 40 sits
at 1.33x the largest legitimate gap and a tenth of the recorded park, and it is
written as `routeAskGiveUpReadings * 2` so the argument cannot drift from the
number. Those gaps are measured on the travel-to-location row only, because #280
is the *other* row's `Warp to Site` being invisible to the parser -- so once
that lands the panel offers a command on more readings and the gaps can only
shrink, which is the safe direction for a bound placed above them.

**A floor that stops asking must not become a floor that does nothing**, which
is PR #257's shape (green, and 108 minutes of a blocked bot) and #272's (8,770
readings at a branch that asked "bounce?" and never bounced). Three properties
answer it and each has its own case: the hold names itself with its count on
every reading it fires, so it is never a silent decline; nothing above it is
suppressed, and the tracker's own step outranks it by two tiers; and the counter
behind the bound advances on the hold's condition *without* the bound, so the
bound is a give-up rather than a duty cycle of forty held readings and one ask
forever.

The rules are executed through the real `Bot.elm` in `elm repl`, and the
readings they are asked about are built by the real
`EveOnline.ParseUserInterface`. What is not an expression -- the wiring, the
counter's arithmetic, the placement -- is read out of the source through a
whitespace-collapsing reader and an indentation-sliced one.

Confirmed by mutation, **twenty** of them, each failing a named case:

  - the stand-down clause dropped from the rule, which is the change reverted
    (six cases, including `test_the_contention_half_no_longer_overwrites_the_
    destination`);
  - the clause asked *after* the give-up, so a latched host tethers beside an
    escalation anyway (`test_the_hold_outranks_the_give_up`);
  - the scanner clause dropped, so the hold fires in hunting mode
    (`test_hunting_mode_is_untouched_in_both_halves`), and separately inverted;
  - the readable-text clause dropped, so a label the client failed to draw
    suppresses the circuit (`test_a_label_the_client_failed_to_draw_is_not_
    evidence`);
  - the entry test narrowed to `travelLabelIsACommand`, which is the state
    labels the whole signal exists to see through
    (`test_the_signal_does_not_move_with_the_click_allow_list`);
  - the bound written as a bare number; cut below the corpus's largest
    legitimate gap; raised past the park it separates from; its comparison
    weakened to `<=`; and its comparison moved one reading early;
  - the counter advanced on `standingDownForATrackedEscalation` rather than on
    its unbounded condition, which is the duty cycle, and separately never
    reset (`test_the_counter_advances_without_the_bound`);
  - the ask counter left running through a stand-down, which is #273's own
    defect restored (`test_the_ask_counter_does_not_run_through_a_hold`);
  - the hold's decision text dropping its count and its bound; and the hold
    docking after all, which is the parking half restored
    (`test_the_hold_does_not_dock`);
  - and, on the two rungs the owner's follow-up added: an empty circuit pinned
    at zero laps again so `home-system` is unreachable; the station rung dropped;
    its same-system guard dropped, so a station in this system is asked for and
    the give-up latches for the session; and the station preferred over the home
    system.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ammo_swap import indented_let_binding
from test_saxrat_gate_panel_button import read_log, saxrat_runs
from test_saxrat_opportunity_shadow import without_line_comments
from test_saxrat_opportunity_tracker_button import (
    TrackerRepl, collapsed_entry, expanded_entry, tracker, travel_button)
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, body_of, collapsed, node, source_of)

STEPS = ("StandDownForATrackedEscalation", "StopAskingForARoute",
         "AskForTheHuntingGround \"Hamse\"", "NowhereToAskFor")

# The client's own type name for the probe scanner. The parser matches on it and
# on nothing else, so one node with a region is an open scanner as far as the
# bot is concerned -- which is the question the scope clause asks.
PROBE_SCANNER_TYPE = "ProbeScannerWindow"

# The bound, as the corpus places it. Both numbers are fixed here rather than
# read out of `Bot.elm`, because a case that only asks about `constant - 1` and
# `constant` passes for any constant at all -- including one that admits
# everything. See `test_ship_scale_from_the_gauge`, where four cases had that
# hole.
LARGEST_LEGITIMATE_GAP = 30
THE_RECORDED_PARK = 414


def probe_scanner_window():
    """The scanner, open and holding nothing.

    Deliberately empty, for #260's own reason: "open with no useful scan
    results" is the reading of "closed" that was considered and rejected, so the
    fixture that must decline is the one that would pass under it.
    """
    return node(PROBE_SCANNER_TYPE, {"_name": "probeScannerWindow"}, [
        node("Container", {"_name": "ResultsContainer"}, [], region=(0, 20, 300, 200)),
    ], region=(1000, 100, 300, 240))


def tracker_offering(label, **kwargs):
    return tracker([expanded_entry([travel_button(label, **kwargs)])])


def location_info_panel(system_name):
    """The info panel naming the system the ship is in, as the client marks it.

    Two things have to be right or the panel parses to `Nothing` and the guard
    under test declines for the wrong reason.
    `parseCurrentSolarSystemFromUINodeText` finds the system by the client's own
    `alt='Current Solar System'` attribute rather than by position, so a label
    carrying the bare name is not enough. And the whole panel is built through
    `maybeListSurroundingsButton |> Maybe.map`, so one without a
    `ListSurroundingsBtn` is no panel at all whatever else it holds --
    `test_the_fixture_really_named_the_current_system` is the control that says
    this fixture cleared both.
    """
    return node("InfoPanelContainer", {"_name": "infoPanelContainer"}, [
        node("InfoPanelLocationInfo", {"_name": "locationInfo"}, [
            node("EveLabelMedium",
                 {"_setText":
                  "<color=0xFF00FF00><b>0.9</b></color>"
                  " <a href=showinfo:5//30000001"
                  " alt='Current Solar System'>%s</a>" % system_name},
                 region=(20, 60, 160, 16)),
            node("ListSurroundingsBtn", {"_name": "listSurroundings"}, [],
                 region=(180, 60, 16, 16)),
        ], region=(20, 50, 200, 40)),
    ], region=(10, 40, 240, 60))


class TheRuleTest(unittest.TestCase):
    """`huntCircuitStep`, executed at every combination of its four inputs.

    Asked as four equalities per case rather than one, so a rule answering two
    things at once -- or none -- fails rather than passing on whichever
    constructor a case happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def step(self, escalation, stand_down, given_up, hunting_ground):
        expression = (
            "huntCircuitStep { escalationIsBeingWorked = %s"
            ", standDownReadings = %d"
            ", routeSettingGivenUp = %s"
            ", nextHuntingGround = %s }" % (
                "True" if escalation else "False", stand_down,
                "True" if given_up else "False",
                "Just \"Hamse\"" if hunting_ground else "Nothing"))
        answers = self.repl.evaluate(
            ["(%s) == %s" % (expression, step) for step in STEPS])
        chosen = [step for step, yes in zip(STEPS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one step for %s, got %s" % (expression, chosen))
        return chosen[0]

    def test_the_circuit_is_unchanged_where_no_escalation_is_being_worked(self):
        """Everything this change must not touch, in one grid.

        Eight readings: the give-up, the ask and the nowhere-to-ask answer, at
        every stand-down count. A rule that started answering the hold without
        an escalation would fail here rather than in a case about escalations.
        """
        for stand_down in (0, 1, 39, 40, 200):
            self.assertEqual(self.step(False, stand_down, True, True),
                             "StopAskingForARoute", "count=%d" % stand_down)
            self.assertEqual(self.step(False, stand_down, True, False),
                             "StopAskingForARoute", "count=%d" % stand_down)
            self.assertEqual(self.step(False, stand_down, False, True),
                             "AskForTheHuntingGround \"Hamse\"",
                             "count=%d" % stand_down)
            self.assertEqual(self.step(False, stand_down, False, False),
                             "NowhereToAskFor", "count=%d" % stand_down)

    def test_an_escalation_being_worked_takes_the_reading(self):
        """#279's whole clause, stated over the four readings it displaces.

        Both halves of the issue are in this grid. `nextHuntingGround = Nothing`
        with the circuit empty is the parking half -- the answer that used to be
        `NowhereToAskFor` and therefore a dock. `Just "Hamse"` is the contention
        half, and `Hamse` is the system run 46's own circuit kept asking for
        while the tracker was travelling to `Sansha's Command Relay Outpost`.
        """
        for given_up in (True, False):
            for hunting_ground in (True, False):
                self.assertEqual(
                    self.step(True, 0, given_up, hunting_ground),
                    "StandDownForATrackedEscalation",
                    "given_up=%s hunting_ground=%s"
                    % (given_up, hunting_ground))

    def test_the_hold_outranks_the_give_up(self):
        """Which is the one ordering decision in the rule.

        The give-up's own answer is `tetherAtStructure`, and docking is what
        must not happen beside a live escalation -- so a latched host must not
        be able to dock the ship out of an escalation prowl. This is also the
        residue of #281 that survives on current main: `hunt-system` populated
        plus a host that never answers arms the latch legitimately, and this
        clause is what stops that becoming the dock cycle for the session.
        """
        self.assertEqual(self.step(True, 0, True, True),
                         "StandDownForATrackedEscalation")
        self.assertEqual(self.step(False, 0, True, True), "StopAskingForARoute")

    def test_the_hold_ends_at_the_bound_and_the_circuit_answers_again(self):
        """The give-up, at both sides of its boundary and at fixed values
        either side, so a constant that admits everything cannot pass.

        Past the bound the rule answers exactly what it answers with no
        escalation at all, which is what makes the change cost at most the bound
        against the behaviour it replaces.
        """
        self.assertEqual(self.step(True, 39, False, True),
                         "StandDownForATrackedEscalation")
        self.assertEqual(self.step(True, 40, False, True),
                         "AskForTheHuntingGround \"Hamse\"")
        self.assertEqual(self.step(True, LARGEST_LEGITIMATE_GAP, False, True),
                         "StandDownForATrackedEscalation",
                         "the hold expires inside the range of gaps a real "
                         "tracker-led leg goes between commands")
        self.assertEqual(self.step(True, THE_RECORDED_PARK, False, False),
                         "NowhereToAskFor")

    def test_the_bound_is_the_only_thing_that_ends_the_hold(self):
        """Neither of the circuit's own two states shortens it.

        Written as the three neighbours of the state that holds, so a rule that
        had conjoined the give-up or the picker onto the clause answers
        something other than the hold somewhere here.
        """
        self.assertEqual(self.step(True, 39, True, True),
                         "StandDownForATrackedEscalation")
        self.assertEqual(self.step(True, 39, True, False),
                         "StandDownForATrackedEscalation")
        self.assertEqual(self.step(True, 39, False, False),
                         "StandDownForATrackedEscalation")


class TheHoldIsAGiveUpAndNotADutyCycleTest(unittest.TestCase):
    """The counter and the bound, folded over a whole session of readings.

    **This is the mistake the first draft of this change made.** Advancing the
    counter on `standingDownForATrackedEscalation` -- the bounded predicate --
    resets it on the very reading the hold expires, so the next reading holds
    again: forty held readings, one ask, forever. That is not a bound, it is a
    duty cycle, and it is `gunsSilencedTicks` pinned at 1 by a reset the thing
    it was waiting on could trigger (#34). The counter therefore advances on the
    hold's condition *without* its bound, and this folds both shapes to show the
    difference rather than asserting it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    BINDINGS = [
        "holds worked n = standingDownForATrackedEscalation"
        " { escalationIsBeingWorked = worked, standDownReadings = n }",
        # The shipped arithmetic: advance on the unbounded condition.
        "shipped ( n, out ) worked ="
        " ( if worked then n + 1 else 0, out ++ [ holds worked n ] )",
        # The shape the first draft had: advance on the bounded predicate.
        "dutyCycle ( n, out ) worked ="
        " ( if holds worked n then n + 1 else 0, out ++ [ holds worked n ] )",
        "session step ws = List.foldl (\\w acc -> step acc w) ( 0, [] ) ws"
        " |> Tuple.second",
    ]

    def held(self, step, readings):
        """How many of `readings` the bot holds the grid on, and in what run."""
        answers = self.repl.strings(
            ["session %s (List.repeat %d True)"
             " |> List.map (\\h -> if h then \"H\" else \".\")"
             " |> String.join \"\"" % (step, readings)],
            definitions=self.BINDINGS)
        return answers[0]

    def test_the_hold_runs_once_and_then_stops(self):
        """Forty held readings, then the circuit on every reading after."""
        run = self.held("shipped", 45)
        self.assertEqual(run, "H" * 40 + "." * 5,
                         "the hold is not one uninterrupted run of the bound")

    def test_it_does_not_come_back_while_the_escalation_stays(self):
        """The property a bound has and a duty cycle does not.

        Two hundred readings of an escalation the tracker never offers a command
        for: the bot holds for the bound and then behaves exactly as it does
        today, rather than returning to the hold every forty-first reading.
        """
        run = self.held("shipped", 200)
        self.assertNotIn("H", run[40:],
                         "the hold comes back after the bound, so the bound is "
                         "a duty cycle rather than a give-up")

    def test_the_duty_cycle_shape_is_what_this_avoids(self):
        """The rejected arithmetic, executed rather than described.

        A case that only asserts the shipped shape cannot show that the other
        one is wrong, and this is the difference the reader has to see: the same
        rule, the same bound, one line different in the counter, and a bot that
        never stops holding.
        """
        run = self.held("dutyCycle", 200)
        self.assertIn("H", run[41:],
                      "the rejected shape has to reproduce the defect, or this "
                      "case is not showing what it claims to")
        self.assertGreater(run.count("H"), 150)

    def test_a_reading_the_hold_does_not_apply_to_resets_it(self):
        """A route appearing, the escalation leaving, the ship docking.

        The counter measures one uninterrupted hold rather than a session's
        worth of them, so an escalation worked in two legs gets the bound twice.
        """
        answers = self.repl.strings(
            ["session shipped ("
             " List.repeat 39 True ++ [ False ] ++ List.repeat 39 True )"
             " |> List.map (\\h -> if h then \"H\" else \".\")"
             " |> String.join \"\""],
            definitions=self.BINDINGS)
        self.assertEqual(answers[0], "H" * 39 + "." + "H" * 39)


class TheEscalationSignalTest(unittest.TestCase):
    """`escalationIsBeingWorked`, against what the real parser made of a tree.

    The rule above takes a `Bool` and cannot see where it came from, so a wiring
    that answered a different question would satisfy every case in it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def worked(self, children):
        return self.repl.evaluate(
            ["reading |> Maybe.map escalationIsBeingWorked"
             " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding("reading", children)])[0]

    def test_the_fixtures_are_what_the_cases_assume(self):
        """The control, before anything is concluded from the pair.

        A tree the parser makes nothing of would answer `False` for reasons that
        have nothing to do with the rule, so the parser is asked directly
        whether it saw a scanner in one reading and not the other, and whether
        the tracker's entry survived in both.
        """
        for children, expected, label in (
                ([tracker_offering("Set Destination")], "False", "scanner shut"),
                ([tracker_offering("Set Destination"), probe_scanner_window()],
                 "True", "scanner open")):
            window, entries = self.repl.evaluate([
                "reading |> Maybe.map (\\r -> r.probeScannerWindow /= Nothing)"
                " |> Maybe.withDefault False",
                "(reading |> Maybe.map (\\r ->"
                " List.length r.opportunityInfoPanelEntries)) == Just 1"],
                definitions=[TrackerRepl.reading_binding("reading", children)])
            self.assertEqual(str(window), expected, label)
            self.assertTrue(entries, label)

    def test_a_command_on_offer_with_the_scanner_shut_is_an_escalation(self):
        """Run 46's own label, which is what the circuit was overwriting."""
        self.assertTrue(self.worked([tracker_offering("Set Destination")]))

    def test_the_same_reading_with_the_scanner_open_is_not(self):
        """Hunting mode. The bot is not working the escalation there -- #260's
        gate declines the step outright -- so holding the ship in the system
        would hold it away from the hunt it is actually doing."""
        self.assertFalse(self.worked(
            [tracker_offering("Set Destination"), probe_scanner_window()]))

    def test_a_state_label_is_still_an_escalation_in_progress(self):
        """The case the whole signal exists for.

        `Warping`, `Jumping` and `Docking` are the client saying the trip is
        already happening, and `travelLabelIsACommand` is right to refuse them
        -- clicking one re-commands a manoeuvre already under way, which is
        #99's docking run-in with a different button. But a reading the step
        refuses is still a reading with a trip under way, and it is exactly the
        reading the floor owns. A signal keyed on the step rather than on the
        button would answer `False` here and the circuit would ask, which is
        the defect.
        """
        for label in ("Warping", "Jumping", "Docking"):
            self.assertTrue(self.worked([tracker_offering(label)]), label)

    def test_the_signal_does_not_move_with_the_click_allow_list(self):
        """Which is a property to keep rather than an accident of drafting.

        `travelLabelIsACommand` answers whether a label may be *clicked*; this
        answers whether anything has said where to go. The two have already
        moved apart once -- the allow-list carried `Dock`, which nobody had read
        off this widget, while lacking `Undock`, which the client really writes
        when the escalation is in the system the ship is docked in -- so a
        signal that inherited its verdicts would move for reasons that have
        nothing to do with the circuit.

        Asserted over both sides of the list at once: every label here is an
        escalation in progress, whichever way the allow-list classifies it.
        """
        for label in ("Set Destination", "Jump", "Warp to Site", "Dock",
                      "Undock", "Warping", "View Details"):
            self.assertTrue(self.worked([tracker_offering(label)]), label)

    def test_a_label_the_client_failed_to_draw_is_not_evidence(self):
        """Fail closed, which is #92's direction.

        Run 22 on the mission runner drew a travel step as a distance wrapped in
        NULs, and run 11 as six C0 control characters around one unassigned
        codepoint. A button whose label the client did not draw says nothing
        about a trip, and declining leaves the bot behaving exactly as it did
        before this change.

        The label travels inside the fixture's JSON rather than as an Elm string
        literal, which a NUL cannot appear in -- `elm_json_literal` encodes
        twice, so the escape the inner call writes reaches the decoder intact.
        """
        self.assertFalse(self.worked(
            [tracker_offering("\x00\x00.50 AU\x00")]),
            "a label the client failed to draw suppresses the hunt circuit")
        self.assertFalse(self.worked([tracker_offering("\x02\x01\x01")]))

    def test_the_fixture_really_carried_the_undrawn_label(self):
        """The control for the case above, which would otherwise pass on a
        fixture the parser threw away for some other reason."""
        label = self.repl.strings(
            ["reading |> Maybe.map (.opportunityInfoPanelEntries"
             " >> List.filterMap .travelButton"
             " >> List.filterMap .label >> List.head"
             " >> Maybe.withDefault \"<none>\")"
             " |> Maybe.withDefault \"<no reading>\""],
            definitions=[TrackerRepl.reading_binding(
                "reading", [tracker_offering("\x00\x00.50 AU\x00")])])[0]
        self.assertIn(".50 AU", label,
                      "the fixture's label never reached the parser, so the "
                      "case above is about an absent button rather than an "
                      "undrawn label")

    def test_a_button_the_client_is_hiding_is_not_on_offer(self):
        """The parser's own `_display` filter, which the chain uses to hide a
        task that is not available rather than removing it."""
        self.assertFalse(self.worked(
            [tracker_offering("Set Destination", displayed=False)]))

    def test_a_tracker_with_no_travel_button_is_not_an_escalation(self):
        """A collapsed escalation offers its name and `View Details` and no
        travel widget at all, so there is no trip on offer to stand down for."""
        self.assertFalse(self.worked([tracker([collapsed_entry()])]))

    def test_an_empty_tracker_is_not_an_escalation(self):
        self.assertFalse(self.worked([tracker([])]))

    def test_one_expanded_entry_among_collapsed_ones_is_enough(self):
        """The live panel's own shape: several escalations, one expanded."""
        self.assertTrue(self.worked([tracker(
            [collapsed_entry(), expanded_entry([travel_button("Jump")]),
             collapsed_entry()])]))


class TheIssuesOwnShapeTest(unittest.TestCase):
    """#279's reading end to end: empty circuit, tracked escalation, no dock.

    The rule and the signal are joined here so that what is asserted is the
    answer the bot would reach, not two halves that happen to agree.

    **What "travelling rather than parking" can honestly mean on this reading is
    worth stating.** Where the tracker offers a pressable command the bot
    travels, and it does so two tiers *above* this branch -- `siteProgressStep`
    answers `WarpToTheOpportunitySite` and the floor is never consulted, which
    the second case here shows. Where it offers none there is no control on the
    reading that moves the ship, and the most this change can do is stop the
    reading being spent docking away from the site. So the pair is asserted
    together: the reading with a command is a warp, and the reading without one
    is a hold rather than a tether.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def circuit_step(self, children, hunting_ground="Nothing"):
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> huntCircuitStep"
             " { escalationIsBeingWorked = escalationIsBeingWorked r"
             " , standDownReadings = 0"
             " , routeSettingGivenUp = False"
             " , nextHuntingGround = %s"
             " } == %s) |> Maybe.withDefault False" % (hunting_ground, step)
             for step in STEPS],
            definitions=[TrackerRepl.reading_binding("reading", children)])
        chosen = [step for step, yes in zip(STEPS, answers) if yes]
        self.assertEqual(len(chosen), 1,
                         "expected exactly one step, got %s" % chosen)
        return chosen[0]

    def test_an_empty_circuit_beside_an_escalation_does_not_tether(self):
        """The issue's own shape, and the answer it asks for.

        `hunt-system` empty, a tracked escalation offering a trip, the scanner
        shut. Today's answer is `NowhereToAskFor`, whose branch is
        `tetherAtStructure` -- a dock, which the docked branch undocks from on
        the next reading because the tracker is still offering something, and
        the pair repeats. #279's run spent 414 readings and three hours in it.

        The label is `Warping`, which stays a state whatever else is being
        revised about this widget's vocabulary, so the case goes on being about
        a reading the floor owns rather than about one classification of one
        word.
        """
        self.assertEqual(
            self.circuit_step([tracker_offering("Warping")]),
            "StandDownForATrackedEscalation")

    def test_the_reading_the_tracker_offers_a_command_is_a_warp(self):
        """And it is decided two tiers above this branch, so the hold cannot
        stand in its way.

        This is what makes the hold a hold rather than a stall: the very reading
        the panel offers something pressable is a reading `siteProgressStep`
        takes and this branch is not reached on.
        """
        answers = self.repl.evaluate(
            ["reading |> Maybe.map (\\r -> siteProgressStep"
             " { gateBranchOffersAStep = False"
             " , arrivalIsOffered ="
             " (opportunityTravelStep r |> Maybe.map (.label >>"
             " opportunityLabelArrivesAtTheSite) |> Maybe.withDefault False)"
             " , warpToSiteIsOffered ="
             " warpToOpportunitySiteIfAvailable r /= Nothing"
             " , gateWithinReach = accelerationGateIsWithinReach r"
             " , probeScannerWindowIsClosed = r.probeScannerWindow == Nothing"
             " } == WarpToTheOpportunitySite) |> Maybe.withDefault False",
             "reading |> Maybe.map (\\r ->"
             " warpToOpportunitySiteIfAvailable r /= Nothing)"
             " |> Maybe.withDefault False"],
            definitions=[TrackerRepl.reading_binding(
                "reading", [tracker_offering("Warp to Site")])])
        self.assertTrue(answers[1], "the tracker's step is not on offer at all")
        self.assertTrue(answers[0],
                        "a pressable command is not taken above the floor, so "
                        "the hold is standing in the way of the trip")

    def test_the_same_reading_with_no_escalation_tethers_exactly_as_today(self):
        """The control. Nothing about an empty circuit changes on its own --
        which is #279's first decision executed rather than argued."""
        self.assertEqual(
            self.circuit_step([tracker([collapsed_entry()])]),
            "NowhereToAskFor")

    def test_the_contention_half_no_longer_overwrites_the_destination(self):
        """`hunt-system` populated and an escalation live, which is run 46.

        `Hamse` is the system that run's circuit kept asking the host for while
        the tracker was travelling to `Sansha's Command Relay Outpost`. The two
        no longer name a destination on the same trip: the circuit stands down
        and the escalation's route is the only one anything sets.
        """
        self.assertEqual(
            self.circuit_step([tracker_offering("Set Destination")],
                              hunting_ground="Just \"Hamse\""),
            "StandDownForATrackedEscalation")

    def test_the_contention_control_still_asks_where_nothing_has_answered(self):
        """The same populated circuit with no escalation on the panel asks for
        `Hamse` exactly as it does today, so this is a suppression by the
        escalation rather than a circuit that stopped working."""
        self.assertEqual(
            self.circuit_step([tracker([collapsed_entry()])],
                              hunting_ground="Just \"Hamse\""),
            "AskForTheHuntingGround \"Hamse\"")

    def test_hunting_mode_is_untouched_in_both_halves(self):
        """The same two readings with the scanner open answer what they answer
        today, which is the whole of the scope decision."""
        self.assertEqual(
            self.circuit_step(
                [tracker_offering("Set Destination"), probe_scanner_window()]),
            "NowhereToAskFor")
        self.assertEqual(
            self.circuit_step(
                [tracker_offering("Set Destination"), probe_scanner_window()],
                hunting_ground="Just \"Hamse\""),
            "AskForTheHuntingGround \"Hamse\"")


class TheEmptyCircuitFallsBackRatherThanAskingTest(unittest.TestCase):
    """What an empty `hunt-system` names, which is #279's first decision and the
    owner's follow-up in one place.

    **#279 asks whether the floor may ask at all when the circuit is empty, and
    the answer was that it already did not.** `nextHuntingGroundFrom` over an
    empty `hunt-system` answered `Nothing` at every index, so the branch reached
    `NowhereToAskFor` and tethered and no `@host set-destination` ever went out.
    Removing the ask removed nothing; what parked the ship was the tether behind
    it. That is why the escalation clause is one clause rather than two, and
    `test_with_nothing_else_configured_it_still_names_nowhere` is what keeps the
    claim executed rather than argued.

    It is also what makes #281's headline scenario unreachable on current main:
    with nothing to ask for, `destinationAskedForNow` is `Nothing`,
    `destinationAskReadings` never advances and `routeSettingGivenUp` cannot
    latch. The log #281 cites was flown on `32369b2`, five commits back, whose
    counter advanced on `standingInADeadEnd` alone -- and that run issued zero
    asks and latched anyway, which is the defect #273 fixed in #275.

    **And it is why `home-system` was dead code in the state it is most wanted
    in.** `huntingGroundAtIndex` reaches the home fallback only once a lap is
    complete, and it computed the lap count by dividing by the circuit's length
    -- so an empty circuit pinned it at zero and the fallback could not be
    reached at all. The operator's own preference for that state is home system,
    then the station the ship last undocked from, then somewhere safe.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(TrackerRepl)

    def named(self, settings, station="Nothing", system=None):
        """What the picker answers over forty laps, as one string or `-`.

        Forty rather than one, because the home fallback is reached through the
        lap count -- a case asking at index 0 alone would miss the one way an
        empty circuit can name somewhere. Asserted as the *set* of answers, so a
        picker that named the right thing at one index and something else at the
        next fails rather than passing on whichever index a case chose.
        """
        panel = ([] if system is None
                 else [location_info_panel(system)])
        # Mapped over the `Maybe` rather than unwrapped with a `Debug.todo`
        # default: Elm evaluates an argument whether or not it is used, so a
        # `Maybe.withDefault (Debug.todo ...)` crashes on every fixture,
        # including the ones that parsed perfectly.
        return self.repl.strings(
            ["maybeReading |> Maybe.map (\\r -> List.range 0 40"
             " |> List.map (\\index -> nextHuntingGroundFrom (%s) index r (%s)"
             " |> Maybe.withDefault \"-\")"
             " |> List.foldl (\\name acc ->"
             " if List.member name acc then acc else acc ++ [ name ]) []"
             " |> String.join \"|\")"
             " |> Maybe.withDefault \"<the fixture did not parse>\""
             % (settings, station)],
            definitions=[
                TrackerRepl.reading_binding("maybeReading",
                                            [tracker([])] + panel)])[0]

    def test_with_nothing_else_configured_it_still_names_nowhere(self):
        """#279's first decision, unchanged: no circuit, no home, nowhere
        docked, and the floor never asks. `NowhereToAskFor` and its tether are
        still what a bot configured this way does."""
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = [] }"), "-")

    def test_an_empty_circuit_names_the_home_system(self):
        """The fallback that was unreachable, at every index.

        This case is the pin on `lapsCompleted`: written as 0 for an empty list,
        the division below is the only thing that could ever raise it, so the
        `home-system` arm was code nothing could reach.
        """
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = []"
                       ", homeSystemName = Just \"Amarr\" }"),
            "Amarr")

    def test_the_home_system_outranks_the_station_undocked_from(self):
        """The operator's own preference order, asked where both are known."""
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = []"
                       ", homeSystemName = Just \"Amarr\" }",
                       station="Just \"Hamse VII - Sisters of EVE Bureau\""),
            "Amarr")

    def test_the_station_undocked_from_is_the_last_rung(self):
        """Reached with no `home-system` configured, which is the shipped
        default -- so this is what an operator flying an escalation prowl on a
        bare settings string actually gets."""
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = [] }",
                       station="Just \"Hamse VII - Sisters of EVE Bureau\""),
            "Hamse VII - Sisters of EVE Bureau")

    def test_a_station_in_this_system_is_declined_rather_than_asked_for(self):
        """#262's guard, which the equality above cannot do for a station.

        A station name is not a system name, so `Just stationName /=
        currentSolarSystemName` is true of the station the ship is standing at
        -- and asking for that is `Route 0 Jumps` with no marker, an ask that
        can never be satisfied, and `routeSettingGivenUp` latched for the
        session. Declining falls through to the tether, which is what this bot
        did before the fallback existed.
        """
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = [] }",
                       station="Just \"Hamse VII - Sisters of EVE Bureau\"",
                       system="Hamse"),
            "-")

    def test_a_station_somewhere_else_is_still_named(self):
        """The control for the guard above, so it is a guard rather than a
        clause that declines everything."""
        self.assertEqual(
            self.named("{ defaultBotSettings | huntSystemNames = [] }",
                       station="Just \"Hamse VII - Sisters of EVE Bureau\"",
                       system="Ahrosseas"),
            "Hamse VII - Sisters of EVE Bureau")

    def test_a_configured_circuit_still_comes_first(self):
        """Nothing about the two new rungs may reorder the circuit itself, which
        is what #262 and #263 measured."""
        self.assertEqual(
            self.named("{ defaultBotSettings"
                       " | huntSystemNames = [ \"Hamse\", \"Lashkai\" ]"
                       ", homeSystemName = Just \"Amarr\" }",
                       station="Just \"Ahrosseas V - Ammatar Consulate\""),
            "Hamse|Lashkai|Amarr")

    def test_the_fixture_really_named_the_current_system(self):
        """The control for the two cases that depend on it: a panel the parser
        made nothing of would decline for the wrong reason."""
        named = self.repl.strings(
            ["maybeReading |> Maybe.andThen currentSolarSystemNameFromReading"
             " |> Maybe.withDefault \"-\""],
            definitions=[TrackerRepl.reading_binding(
                "maybeReading",
                [tracker([]), location_info_panel("Hamse")])])[0]
        self.assertEqual(named, "Hamse")


class TheBoundIsPlacedInTheGapTheCorpusDrawsTest(unittest.TestCase):
    """The number, and the measurement that puts it where it is.

    Both edges are fixed values rather than `constant +/- 1`, because a case
    that only asks about the boundary passes for any constant at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def test_it_is_written_as_a_multiple_rather_than_a_bare_number(self):
        """`missionStalledReadingsBeforeAbandoning`'s form, for its reason: the
        argument cannot drift away from the number. What the hold displaces is
        the circuit's own ask, which gets `routeAskGiveUpReadings`."""
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "escalationStandDownGiveUpReadings"))
        self.assertIn("routeAskGiveUpReadings * 2", body)
        self.assertNotRegex(
            body, r"escalationStandDownGiveUpReadings =\s*\d",
            "the bound is a bare number, so the argument for it is no longer "
            "attached to it")

    def test_it_sits_above_every_legitimate_gap_the_corpus_records(self):
        self.assertGreater(self.bound(), LARGEST_LEGITIMATE_GAP,
                           "the bound cuts through the gaps a real "
                           "tracker-led leg goes between pressable commands")

    def test_it_sits_far_below_the_park_it_has_to_separate_from(self):
        self.assertLess(self.bound(), THE_RECORDED_PARK // 2)

    def bound(self):
        """The constant, resolved out of the source rather than recomputed.

        Read through `routeAskGiveUpReadings` because that is how it is written,
        so a case cannot go on passing against a multiple somebody replaced with
        a bare number -- which is what the case above this one refuses.
        """
        match = re.search(r"routeAskGiveUpReadings\s*=\s*(\d+)", self.source)
        self.assertIsNotNone(match, "no routeAskGiveUpReadings")
        return int(match.group(1)) * 2


class TheRecordedRunsPlaceThisBoundTest(unittest.TestCase):
    """What the corpus says, recounted here rather than quoted.

    Counted in **readings** and not decision lines: the host reprints the whole
    decision block on every log line, and reading that as a rate is the mistake
    that has cost `stall_watch.py` two threshold calibrations, #141 a retreat
    measurement and #164 a whole diagnosis. One `RequestToVolatileProcess`
    read-from-game task is one reading.

    Asserted as relations rather than as counts, so a growing corpus cannot turn
    a true claim red.
    """

    READ = re.compile(r"task read-from-game-\d+: RequestToVolatileProcess")
    OPPORTUNITY = "The Opportunities tracker offers"
    ASK = "Asking the host to set the destination to"
    CLOSED = "No probe window"

    # The four runs that ever took a step from the tracker. Named rather than
    # globbed because the claim is about those runs' own trips.
    TRIP_RUNS = (43, 44, 46, 52)

    # Below this many gaps the corpus cannot say how long a leg goes without a
    # command, and a case asserting on what accumulated would report an absence
    # as a finding. Absent evidence skips; evidence that disagrees fails.
    GAPS_NEEDED = 100

    @classmethod
    def setUpClass(cls):
        cls.logs = saxrat_runs(*cls.TRIP_RUNS)
        cls.census = {os.path.basename(path): cls.count(path)
                      for path in cls.logs}
        pooled = sum(len(run["offered"]) - 1 for run in cls.census.values()
                     if run["offered"])
        if pooled < cls.GAPS_NEEDED:
            raise unittest.SkipTest(
                "no recorded saxrat runs with enough tracker-led trips to say "
                "how long a leg goes between pressable commands")

    @classmethod
    def count(cls, path):
        """Per run: which readings offered a step, asked, and had the scanner
        shut."""
        readings = 0
        offered, asked, shut = [], [], set()
        current = {"offered": False, "asked": None, "shut": False}
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if cls.READ.search(line):
                    readings += 1
                    if current["offered"]:
                        offered.append(readings)
                    if current["asked"]:
                        asked.append((readings, current["asked"]))
                    if current["shut"]:
                        shut.add(readings)
                    current = {"offered": False, "asked": None, "shut": False}
                    continue
                if cls.OPPORTUNITY in line:
                    current["offered"] = True
                if cls.ASK in line:
                    match = re.search(r"destination to '([^']*)'", line)
                    current["asked"] = match.group(1) if match else "?"
                if line.startswith("+ ") and line.rstrip("\n")[2:] == cls.CLOSED:
                    current["shut"] = True
        return {"readings": readings, "offered": offered, "asked": asked,
                "shut": shut}

    def gaps(self):
        pooled = []
        for run in self.census.values():
            pooled += [later - earlier for earlier, later
                       in zip(run["offered"], run["offered"][1:])]
        return sorted(pooled)

    def test_the_corpus_carries_enough_trips_to_say_anything(self):
        """The control: the floor `setUpClass` skips below, asserted here so
        that a class which reached this point really is reporting on a sample
        rather than on whatever a thin one happened to hold."""
        self.assertGreaterEqual(len(self.gaps()), self.GAPS_NEEDED)

    def test_no_leg_ever_went_longer_than_the_bound_without_a_command(self):
        """The measurement the bound rests on, as the relation.

        If this ever stops holding it means a real trip has gone longer than the
        hold, and the hold would be expiring on a leg that was working.
        """
        pooled = self.gaps()
        self.assertLessEqual(
            pooled[-1], LARGEST_LEGITIMATE_GAP,
            "a tracker-led leg went longer between commands than the bound "
            "was placed above")

    def test_the_gap_between_a_working_leg_and_a_park_is_empty(self):
        """Which is what makes 40 a separator rather than a compromise.

        Nothing recorded sits between the largest legitimate gap and the park
        the hold has to be told apart from -- so the bound is placed in an empty
        band rather than cut through a distribution.
        """
        pooled = self.gaps()
        self.assertEqual(
            [gap for gap in pooled
             if LARGEST_LEGITIMATE_GAP < gap < THE_RECORDED_PARK], [],
            "a gap now sits in the band the bound was placed in")

    def test_the_contention_is_in_the_corpus_and_names_another_system(self):
        """Run 46's cycle, which is #279's second half recorded here.

        The circuit asks the host for a system while the tracker is travelling
        to an escalation, and the two overwrite each other's destination. What
        makes it contention rather than coincidence is that the asks fall
        *inside* the trip and name somewhere the tracker is not going.
        """
        for name, run in self.census.items():
            if not run["offered"] or not run["asked"]:
                continue
            first, last = run["offered"][0], run["offered"][-1]
            inside = [ask for ask in run["asked"] if first <= ask[0] <= last]
            if inside:
                self.assertGreater(
                    len(inside), 1,
                    "%s: the circuit asked inside a trip only once, which is "
                    "not a cycle" % name)
                return
        self.skipTest("no recorded saxrat runs asked the circuit for a "
                      "destination inside a tracker-led trip")

    def test_the_gate_is_what_decides_whether_a_step_is_taken_at_all(self):
        """#260's switch, on the one run in this set that carries it.

        Run 52 flew `32369b2`, which contains #260; runs 43, 44 and 46 predate
        it. So a run with the gate takes the tracker's step only on readings
        where the scanner was shut, and one without it takes it with the scanner
        open -- which is the provenance of the contention above, and the reason
        that shape is reachable today only in escalation mode.
        """
        with_gate = self.census.get("saxrat_run52.log")
        if with_gate is None or not with_gate["offered"]:
            # The one run in this set flown on a tree carrying #260's gate.
            self.skipTest("no recorded saxrat_run52.log")
        self.assertTrue(
            set(with_gate["offered"]) <= with_gate["shut"],
            "a run flown with #260's gate took the tracker's step on a reading "
            "whose scanner was open")

    def test_the_scanner_is_shut_on_a_small_share_of_readings(self):
        """What the scope decision costs, stated as the relation.

        The clause fires only in escalation mode, and escalation mode is entered
        on purpose. A corpus this lopsided is what makes the change narrow.
        """
        shut = sum(len(run["shut"]) for run in self.census.values())
        readings = sum(run["readings"] for run in self.census.values())
        self.assertGreater(readings, 5000)
        self.assertLess(shut * 20, readings,
                        "the scanner is shut on a large share of readings, so "
                        "the scope clause is no longer narrow")


class ThePreviousDiagnosisIsRecordedTest(unittest.TestCase):
    """#281's log, read here so the correction is not only in a pull request.

    #281 reports that the route-ask give-up starves the tracker step, measured
    on two runs differing in the scanner window. Its failing log is on this
    machine and says something else:

    - it was flown on `32369b2`, five commits back, whose `destinationAskReadings`
      advances on `standingInADeadEnd` alone. The run issued **zero** asks and
      latched the give-up anyway, which is the defect #273 named and #275 fixed
      -- so the headline scenario does not reproduce on current main;
    - the shadow is #260's gate rather than the give-up's depth. Two of its 61
      readings had the scanner shut, and those two are the two that fired the
      tracker step.

    This is a case rather than a paragraph because the log is the evidence and
    it will outlive the issue.
    """

    LOG = os.path.join(EVE_BOT_LOGS, "saxrat_escalation_probe_2026-08-16.log")
    READ = re.compile(r"task read-from-game-\d+: RequestToVolatileProcess")

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.LOG):
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what #281's own "
                "run says cannot be consulted here")
        cls.text = read_log(cls.LOG)
        readings = 0
        current = {"offered": False, "shut": False, "gave_up": False}
        cls.offered, cls.shut, cls.gave_up = [], set(), []
        for line in cls.text.splitlines():
            if cls.READ.search(line):
                readings += 1
                if current["offered"]:
                    cls.offered.append(readings)
                if current["shut"]:
                    cls.shut.add(readings)
                if current["gave_up"]:
                    cls.gave_up.append(readings)
                current = {"offered": False, "shut": False, "gave_up": False}
                continue
            if "The Opportunities tracker offers" in line:
                current["offered"] = True
            if line.startswith("+ ") and line.rstrip("\n")[2:] == "No probe window":
                current["shut"] = True
            if "stop asking and wait where it is safe" in line:
                current["gave_up"] = True
        cls.readings = readings

    def test_it_was_flown_on_a_tree_that_predates_the_counter_fix(self):
        self.assertIn("# bot version: 32369b2", self.text)

    def test_the_latch_armed_having_asked_for_nothing(self):
        """Which is #273's defect and not the ordering #281 describes.

        A give-up that says "asked for a destination for more than 20 readings"
        on a run that issued no ask at all is a counter measuring something
        other than the thing it bounds.
        """
        self.assertNotIn("Asking the host to set the destination to", self.text)
        self.assertIn("no 'hunt-system' is configured", self.text)
        self.assertGreater(len(self.gave_up), 10)

    def test_the_tracker_step_fired_only_where_the_scanner_was_shut(self):
        """So what silenced it is #260's gate, not the give-up's depth."""
        self.assertTrue(self.offered, "the run never took the tracker's step")
        self.assertTrue(set(self.offered) <= self.shut)
        self.assertTrue(set(self.gave_up) - self.shut,
                        "the give-up never fired on an open-scanner reading, "
                        "so the two cannot be told apart in this run")


class TheWiringTest(unittest.TestCase):
    """What the branch and the memory update hand the rules, which is not an
    expression.

    The rules take records and cannot see where the values came from, so a
    wiring answering a different question would satisfy every case above.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(without_line_comments(
            body_of(cls.source, "setRouteToNextHuntingGround")))
        cls.signal = collapsed(without_line_comments(
            body_of(cls.source, "escalationIsBeingWorked")))

    def test_the_rule_is_told_about_the_reading_and_the_count(self):
        # Narrowed since the 0.5 gate: the reading handed to the stand-down
        # reader is the one with lowsec escalations already removed, so this
        # and the travel step cannot disagree about whether an escalation is
        # worth holding the grid for.
        self.assertIn(
            "escalationIsBeingWorked = escalationIsBeingWorked"
            " (escalationEntriesPermitted context.eventContext.botSettings"
            " context.readingFromGameClient)", self.branch)
        self.assertIn(
            "standDownReadings = context.memory.escalationStandDownReadings",
            self.branch)

    def test_the_signal_reads_the_button_rather_than_the_step(self):
        """`opportunityTravelStep` refuses a state label, which is the reading
        the floor owns -- so a signal built on it would answer `False` exactly
        where the circuit must not ask."""
        self.assertNotIn("opportunityTravelStep", self.signal)
        self.assertNotIn("travelLabelIsACommand", self.signal)
        self.assertIn("travelLabelIsReadableText", self.signal)
        self.assertIn(".travelButton", self.signal)

    def test_the_signal_reads_the_window_rather_than_its_scan_results(self):
        """#260's own reading of "closed", which is an act by the operator
        rather than a fact about the system."""
        self.assertIn(
            "readingFromGameClient.probeScannerWindow == Nothing", self.signal)
        self.assertNotIn("scanResults", self.signal)

    def test_the_counter_advances_without_the_bound(self):
        """The duty-cycle trap, refused at the wiring as well as in the fold.

        The counter's own condition must be the hold's *unbounded* one, or the
        bound resets itself on the reading it expires.
        """
        binding = collapsed(without_line_comments(indented_let_binding(
            "updateMemoryForNewReadingFromGame",
            "anEscalationIsBeingWorkedInADeadEnd")))
        self.assertIn("standingInADeadEnd && escalationIsBeingWorked", binding)
        self.assertNotIn("standingDownForATrackedEscalation", binding)

        update = collapsed(without_line_comments(
            body_of(self.source, "updateMemoryForNewReadingFromGame")))
        field = update[update.index(", escalationStandDownReadings ="):]
        field = field[:field.index(", lockBatch =")]
        self.assertIn("if anEscalationIsBeingWorkedInADeadEnd then", field)
        self.assertIn("botMemoryBefore.escalationStandDownReadings + 1", field)
        self.assertIn("else 0", field,
                      "the counter never resets, so it measures a session "
                      "rather than one hold")

    def test_the_counter_is_narrowed_to_the_readings_the_branch_is_reached_on(self):
        """`standingInADeadEnd` is the condition under which the circuit is
        consulted at all. Counting anything wider spends the bound on readings
        the branch never ran on, which is #145's `gateWithinReachTicks` and
        #11's `dronesInSpaceTicks`."""
        binding = collapsed(without_line_comments(indented_let_binding(
            "updateMemoryForNewReadingFromGame",
            "anEscalationIsBeingWorkedInADeadEnd")))
        self.assertIn("standingInADeadEnd", binding)

    def test_the_ask_counter_does_not_run_through_a_hold(self):
        """#273's defect, refused in the new state that could reproduce it.

        No ask goes out on a held reading, so a counter that ran through one
        would latch `routeSettingGivenUp` for the session against asks nobody
        made -- which is exactly what #281's own run recorded, on a tree where
        the counter ran on `standingInADeadEnd` alone.
        """
        binding = collapsed(without_line_comments(indented_let_binding(
            "updateMemoryForNewReadingFromGame", "destinationAskedForNow")))
        self.assertIn(
            "if standingInADeadEnd && not standingDownForAnEscalationNow then",
            binding)

    def test_the_hold_is_the_only_new_thing_and_the_others_are_untouched(self):
        """Every other arm answers exactly what it answered before, so a reading
        with no escalation on the panel is decided as it is today."""
        self.assertIn("tetherAtStructure context", self.branch)
        self.assertEqual(2, self.branch.count("tetherAtStructure context"))
        self.assertIn("hostDirectiveSetDestination systemName", self.branch)


class TheDeclineIsNotASilentWaitTest(unittest.TestCase):
    """A hold that names itself, which is what #257 and #272 both lacked.

    PR #257 shipped green and blocked the bot for 108 minutes because something
    on a hot decision path could decline forever with nothing else able to act;
    #272 waited 8,770 readings at a branch that asked "bounce?" and never
    bounced. Neither said so on a reading.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(without_line_comments(
            body_of(cls.source, "setRouteToNextHuntingGround")))

    def hold_arm(self):
        arm = self.branch[self.branch.index("StandDownForATrackedEscalation ->"):]
        return arm[:arm.index("StopAskingForARoute ->")]

    def test_every_arm_of_the_branch_answers_something(self):
        """Four constructors, four `describeBranch`es. A `Nothing` here would be
        a decline the log cannot see."""
        self.assertEqual(4, self.branch.count("describeBranch"))

    def test_the_hold_carries_its_count_and_its_bound(self):
        arm = self.hold_arm()
        self.assertIn("context.memory.escalationStandDownReadings", arm)
        self.assertIn("escalationStandDownGiveUpReadings", arm)

    def test_the_hold_says_what_it_is_not_doing_and_why(self):
        """An operator reading one line has to be able to tell this from a bot
        that has nothing to do."""
        arm = self.hold_arm()
        self.assertIn("Opportunities tracker", arm)
        self.assertIn("not docking", arm)

    def test_the_hold_does_not_dock(self):
        """Which is the whole of the parking half: `tetherAtStructure` is a
        dock, and the docked branch undocks from it again on the next reading
        because the tracker is still offering something."""
        self.assertNotIn("tetherAtStructure", self.hold_arm())

    def test_nothing_above_the_hold_is_suppressed(self):
        """It is reached from the floor of `siteProgressStepOrElse`, which is
        below the tracker's own step, the acceleration gate, the fight, the
        loot, the retreats and the pod recovery. So the hold can only replace
        the circuit."""
        whole = collapsed(without_line_comments(self.source))
        self.assertIn(
            "siteProgressStepOrElse context (jumpToNextSystem context)", whole)
        self.assertIn("HuntWithTheProbeScanner -> ifNeither", whole)
