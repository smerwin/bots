"""Tests for saxrat opening an in-range acceleration gate from the Selected Item
panel rather than with a context-menu cascade.

saxrat drove an in-range gate with `useContextMenuCascadeOnOverviewEntry`, and
the mission runner stopped doing that: `activateGateOnOverviewEntry`'s doc
comment records the panel's own `selectedItemActivateGate` verified live on a
gate that had refused 124 D-clicks, the objective going from "You need to
activate the Acceleration Gate" to "Warping" on the press. That is the mechanism
ported here.

**What saxrat's own recordings say is narrower than the give-up count, and these
cases pin the narrow version.** Runs 4 and 5 carry 829 `has not taken me
anywhere` lines between them, but the give-up prints on every reading once
`gateRefusesThisShipTicks` is passed, so 829 lines are **two** in-reach episodes
-- one per run, the only two in the whole corpus that ever passed 40. Only run
4's is this mechanism failing. Run 5's counter reached 3,504 while the bot
pressed `warpToOpportunitySiteIfAvailable` more than ten thousand times: that
branch outranks the gate branch, so the gate was merely nearby and was never
asked to open. Counting proximity is what produced those 108 give-ups, and the
counter is corrected here for that reason.

Three things follow, and each has cases below:

  - the in-range branch selects the row and presses the panel button, and the
    out-of-range branch is deliberately unchanged -- the panel carries
    `selectedItemActivateGate` only in range, which is the natural gate between
    the two mechanisms;
  - `gateWithinReachTicks` counts the *ask* -- readings on which the panel was
    showing a gate that is already in reach -- holds on a reading in reach that
    did not ask, and resets only on leaving reach;
  - the give-up no longer asserts that the gate "most likely will not admit this
    ship". Run 4's client said nothing on any channel, so a sentence naming a
    ship restriction sends an operator to look at the hull when the evidence
    points at the click.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the readings they are asked about go through the real
`EveOnline.ParseUserInterface` -- which is also what makes these cases evidence
that saxrat's diverged copy of that parser exposes the selected-item window and
the button names the panel press needs.

The wiring and the placement, which are not expressions, are read out of the
source through a whitespace-collapsing reader so an `elm-format` pass cannot
break them.

Confirmed by mutation, thirteen of them, each failing a named case: the in-range
branch reverted to the context-menu cascade; the press no longer wrapped in
`unlessAlreadyClosingIn`; the panel lookup aimed at a button that is not this
one; the counter advanced on proximity again (run 5's defect); the counter
resetting rather than holding on a reading that did not ask; a reading with the
gate selected and no button no longer counted, which is the unbounded wait
saxrat has nothing else to end; the bound's comparison moved either way; the
select-first step dropped so the panel is pressed while showing something else;
the range split neutralised so a 40 km gate takes the panel path; the give-up's
ship-restriction sentence restored; the give-up dropping its reading count; and
the status clause no longer separating asking from being near.

Two survived the first pass and both were real holes -- the named-button case
satisfied by the branch's own wait message quoting the button, and the
"selected with no button is still an ask" case written over the counter, which
is handed `asking` as an input and cannot notice that rule being narrowed.

Two cases read the recorded saxrat runs in `~/eve-bot-logs`, and only read them;
they skip with a stated reason on a machine that has none.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, label, node, overview,
    source_of)


def saxrat_runs(*numbers):
    """The recorded saxrat runs this machine has, or the shared skip.

    saxrat's logs are named differently from the mission runner's, so
    `prerequisites.recorded_runs` does not reach them; this is the wording every
    other saxrat corpus case already skips with, and `check_expected_skips.py`
    refuses a second spelling of it.
    """
    logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
            for number in numbers]
    logs = [path for path in logs if os.path.exists(path)]
    if not logs:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
            "say about this gate cannot be consulted here")
    return logs


def read_log(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


# The gate saxrat has actually met. Every acceleration gate named in any
# recorded saxrat run is this one string.
GATE_NAME = "Ancient Acceleration Gate"

# The panel button the mission runner verified live.
ACTIVATE_BUTTON = "selectedItemActivateGate"

# The sentence the give-up used to carry. It is an inference, and run 4's client
# gave no evidence for it.
RETIRED_CLAIM = "most likely will not admit this ship"


def selected_item_window(showing, buttons=()):
    """The Selected Item panel, as the real parser will accept it.

    `parseSelectedItemWindowFromUITreeRoot` matches the window on its type name
    -- the macOS client calls it `SelectedItemWnd` -- and everything the bot
    reads off it afterwards is a descendant: the name it is showing as display
    text, and each action button by its own `_name`.
    """
    children = [label(showing, (0, 0, 200, 16))]
    for index, name in enumerate(buttons):
        children.append(
            node("ButtonIcon", {"_name": name},
                 region=(index * 34, 20, 32, 32)))
    return node("SelectedItemWnd", {}, children, region=(0, 600, 200, 80))


def reading(gate_distance="1500 m", panel=None, extra_rows=()):
    """A reading with one acceleration gate on the overview, and maybe a panel."""
    rows = [(gate_distance, GATE_NAME, "Acceleration Gate")] + list(extra_rows)
    children = [overview(rows)]
    if panel is not None:
        children.append(panel)
    return children


class GateRepl(SaxratRepl):
    pass


class TheStepRuleTest(unittest.TestCase):
    """`gateActivationStep`, executed at each of its four answers.

    Asked as four equalities per case rather than one, so that a rule which
    answered two things at once -- or none -- would fail rather than pass on the
    one constructor a case happened to name.
    """

    STEPS = ("SelectTheGate", "PressActivateGate", "WaitForTheActivateButton",
             "GiveUpOnThisGate")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    def step(self, shows, offers, asked):
        expression = (
            "gateActivationStep { panelShowsTheGate = %s"
            ", panelOffersActivateGate = %s, askedReadings = %d }" % (
                "True" if shows else "False",
                "True" if offers else "False", asked))
        answers = self.repl.evaluate(
            ["(%s) == %s" % (expression, step) for step in self.STEPS])
        chosen = [step for step, yes in zip(self.STEPS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one step for %s, got %s" % (expression, chosen))
        return chosen[0]

    def test_a_panel_showing_something_else_is_selected_first(self):
        self.assertEqual(self.step(False, False, 0), "SelectTheGate")
        self.assertEqual(self.step(False, True, 0), "SelectTheGate")

    def test_the_button_is_pressed_once_the_panel_shows_the_gate(self):
        self.assertEqual(self.step(True, True, 0), "PressActivateGate")
        self.assertEqual(self.step(True, True, 39), "PressActivateGate")

    def test_the_gate_selected_with_no_button_waits(self):
        self.assertEqual(self.step(True, False, 0), "WaitForTheActivateButton")

    def test_the_bound_is_the_last_reading_that_still_asks(self):
        """40 asks, then the give-up on the forty-first.

        Both sides of the comparison and a fixed value well past it, because a
        case that only asks about `constant - 1` and `constant` passes for any
        constant at all -- the hole four of #120's own cases had.
        """
        self.assertEqual(self.step(True, True, 40), "PressActivateGate")
        self.assertEqual(self.step(True, True, 41), "GiveUpOnThisGate")
        self.assertEqual(self.step(True, True, 3504), "GiveUpOnThisGate")

    def test_the_give_up_outranks_every_other_answer(self):
        """Past the bound, nothing about the panel brings the asking back."""
        for shows in (True, False):
            for offers in (True, False):
                self.assertEqual(
                    self.step(shows, offers, 200), "GiveUpOnThisGate",
                    "shows=%s offers=%s" % (shows, offers))

    def test_the_bound_is_forty(self):
        self.assertTrue(self.repl.evaluate(
            ["gateRefusesThisShipTicks == 40"])[0])


class TheAskedCounterTest(unittest.TestCase):
    """`gateAskedReadingsAfterReading`, folded over whole sessions.

    Folded rather than asked at single numbers, because what the rule has to get
    right is a sequence: run 5's shape is thousands of readings in reach with
    nothing asking, and a rule that is correct reading by reading can still
    accumulate the wrong total over that.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    FOLD = (
        "fold session = List.foldl (\\( asking, inReach ) before ->"
        " gateAskedReadingsAfterReading"
        " { asking = asking, gateWithinReach = inReach, before = before })"
        " 0 session")

    def fold(self, session):
        elm = "[ %s ]" % ", ".join(
            "( %s, %s )" % ("True" if a else "False", "True" if r else "False")
            for a, r in session)
        return int(self.repl.values(
            ["fold %s" % elm], r"(\d+) : Int", definitions=[self.FOLD])[0])

    def test_readings_that_ask_are_what_accumulate(self):
        self.assertEqual(self.fold([(True, True)] * 30), 30)

    def test_run_5s_shape_never_reaches_the_bound(self):
        """A gate in reach for thousands of readings that nothing ever asks.

        The measured defect: `warpToOpportunitySiteIfAvailable` outranks the gate
        branch, so run 5 stood beside a gate for 3,504 readings having made three
        attempts on it, and a counter on proximity gave that 108 give-ups.
        """
        self.assertEqual(self.fold([(False, True)] * 3504), 0)

    def test_a_reading_that_does_not_ask_holds_rather_than_resets(self):
        """The evidence survives whatever holds the tree between attempts.

        Resetting here is the shape that pinned `gunsSilencedTicks` at 1 forever:
        a message box, a fight or an opportunity warp between two asks would wipe
        the count and the bound would never be reached.
        """
        self.assertEqual(self.fold([(True, True)] * 20 + [(False, True)] * 50), 20)
        self.assertEqual(
            self.fold([(True, True)] * 20 + [(False, True)] * 50
                      + [(True, True)] * 21), 41)

    def test_leaving_reach_is_what_resets(self):
        self.assertEqual(
            self.fold([(True, True)] * 39 + [(False, False)] + [(True, True)] * 3),
            3)

    def test_a_gate_selected_with_no_button_is_still_an_ask(self):
        """The reading is counted, which is what bounds the no-button wait.

        The mission runner counts only the readings its panel made the offer and
        leaves this state to `nothingToDoTicks` from the bottom of its tree.
        saxrat has no such counter and this branch answers `Just`, so a state
        that is neither counted nor acted on is a ship parked at a gate with
        nothing to end it. The rule takes `asking`, which is the panel showing
        the gate, and says nothing about the button.
        """
        self.assertEqual(self.fold([(True, True)] * 41), 41)


class TheGiveUpSaysWhatIsKnownTest(unittest.TestCase):
    """The wording, which used to name a cause the evidence does not support."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)
        cls.sentence = cls.repl.strings(["describeGateGaveUp 282"])[0]

    def test_it_carries_the_reading_count(self):
        self.assertIn("282", self.sentence)

    def test_it_does_not_assert_a_ship_restriction(self):
        """Run 4's client said nothing, so this cannot be concluded from here.

        The mission runner *can* say a gate wants an item, because the client
        writes `This gate is locked! ... in your cargo hold` on the `info`
        channel and it reads that. No such line appears anywhere in saxrat's
        recorded runs beside either give-up episode.
        """
        self.assertNotIn(RETIRED_CLAIM, self.sentence)
        self.assertNotIn("will not admit this ship.", self.sentence)

    def test_it_names_the_silence_that_makes_the_causes_indistinguishable(self):
        self.assertIn("said nothing", self.sentence)

    def test_it_names_what_it_was_doing_rather_than_only_that_it_failed(self):
        self.assertIn("Activate Gate", self.sentence)

    def test_it_still_reads_as_a_give_up(self):
        self.assertIn("Stopping", self.sentence)

    def test_the_count_is_the_one_it_was_given(self):
        """Not a constant that happens to look like a count."""
        other = self.repl.strings(["describeGateGaveUp 41"])[0]
        self.assertIn("41", other)
        self.assertNotIn("282", other)


class TheStatusClauseTest(unittest.TestCase):
    """`describeGateActivationAsk`, which is what an operator watches.

    Before this the status line could say only how many readings had been spent
    near a gate, which is exactly the quantity run 5 shows is not the one worth
    watching.
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

    def test_it_names_the_bound_beside_the_count(self):
        clause = self.clause(True, True, 12)
        self.assertIn("12", clause)
        self.assertIn("40", clause)

    def test_it_separates_asking_from_merely_being_near(self):
        asking = self.clause(True, True, 12)
        near = self.clause(False, True, 12)
        self.assertNotEqual(asking, near)
        self.assertIn("asking now", asking)
        self.assertIn("not being asked", near)

    def test_a_reading_with_no_gate_says_neither(self):
        clause = self.clause(False, False, 0)
        self.assertNotIn("asking now", clause)
        self.assertNotIn("not being asked", clause)


class ThePanelIsReadFromTheRealParserTest(unittest.TestCase):
    """The three reads the press depends on, over readings the parser produced.

    A hand-written record would prove nothing about saxrat's diverged
    `ParseUserInterface`, and the selected-item window is the part of it this bot
    had never used: before this change `Bot.elm` named `selectedItem` zero times.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(GateRepl)

    def ask(self, expressions, children):
        return self.repl.evaluate(
            ["reading |> Maybe.map (%s) |> Maybe.withDefault False" % e
             for e in expressions],
            definitions=[GateRepl.reading_binding("reading", children)])

    def test_the_parser_finds_the_panel_and_its_button(self):
        found, named = self.ask(
            ["\\r -> r.selectedItemWindow /= Nothing",
             "\\r -> selectedItemButtonNamed r \"%s\" /= Nothing" % ACTIVATE_BUTTON],
            reading(panel=selected_item_window(GATE_NAME, [ACTIVATE_BUTTON])))
        self.assertTrue(found, "the real parser did not find SelectedItemWnd")
        self.assertTrue(named, "the panel's button was not reachable by name")

    def test_a_panel_without_the_button_does_not_offer_it(self):
        self.assertFalse(self.ask(
            ["\\r -> selectedItemButtonNamed r \"%s\" /= Nothing" % ACTIVATE_BUTTON],
            reading(panel=selected_item_window(GATE_NAME)))[0])

    def test_the_panel_showing_the_gate_is_the_ask(self):
        self.assertTrue(self.ask(
            ["askingAnAccelerationGateToOpen"],
            reading(panel=selected_item_window(GATE_NAME, [ACTIVATE_BUTTON])))[0])

    def test_a_panel_showing_something_else_is_not_the_ask(self):
        """Run 5's state, and the one the old counter could not tell apart."""
        self.assertFalse(self.ask(
            ["askingAnAccelerationGateToOpen"],
            reading(
                panel=selected_item_window("Centus Black Ops Agent"),
                extra_rows=[("900 m", "Centus Black Ops Agent", "Battleship")]))[0])

    def test_the_gate_selected_with_no_button_is_still_the_ask(self):
        """Which is what bounds the state saxrat has nothing else to end.

        The mission runner asks the same question about the *offer* -- the
        button being on the panel -- and leaves a gate that is selected and
        offers nothing to `nothingToDoTicks` from the bottom of its decision
        tree. saxrat has no such counter and this branch answers `Just`, so a
        reading in that state must be counted or the ship parks at the gate
        forever. This case is over the rule that decides it rather than over the
        counter it feeds: a fold that is handed `asking` cannot notice this
        narrowing, which is exactly how the first version of this file missed
        it.
        """
        self.assertTrue(self.ask(
            ["askingAnAccelerationGateToOpen"],
            reading(panel=selected_item_window(GATE_NAME)))[0])

    def test_no_panel_at_all_is_not_the_ask(self):
        self.assertFalse(
            self.ask(["askingAnAccelerationGateToOpen"], reading())[0])

    def test_a_gate_out_of_reach_is_not_the_ask_however_the_panel_reads(self):
        """The ask is about a gate the ship could already take.

        A gate 40 km away selected on the panel is the out-of-range branch
        working exactly as intended, and counting those readings against the
        give-up would spend the budget during the approach.
        """
        asking, in_reach = self.ask(
            ["askingAnAccelerationGateToOpen", "accelerationGateIsWithinReach"],
            reading(gate_distance="40 km",
                    panel=selected_item_window(GATE_NAME, [ACTIVATE_BUTTON])))
        self.assertFalse(asking)
        self.assertFalse(in_reach)

    def test_the_panel_test_matches_whole_words(self):
        """A longer name that merely contains this one is not this one."""
        self.assertFalse(self.ask(
            ["askingAnAccelerationGateToOpen"],
            reading(panel=selected_item_window(
                GATE_NAME + "way", [ACTIVATE_BUTTON])))[0])


class TheBranchPressesThePanelTest(unittest.TestCase):
    """Wiring, read out of the source: what the two branches do.

    Not expressions, so they cannot be evaluated -- and the thing most worth
    pinning is a *negative*, that the in-range branch no longer opens a context
    menu, which no evaluation of the rule would notice.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.branch = collapsed(
            body_of(cls.source, "activateAccelerationGateIfPresent"))

    def test_the_in_range_branch_presses_the_named_panel_button(self):
        """The *lookup* names it, not merely a sentence that mentions it.

        The first version of this case asserted the name occurred anywhere in
        the branch, and the branch's own wait message quotes the button by name
        -- so pointing the lookup at `selectedItemApproach` passed. That is the
        press acting on the wrong button while the log still names the right
        one, which is the worst shape available here.
        """
        self.assertIn(
            'selectedItemButtonNamed context.readingFromGameClient "%s"'
            % ACTIVATE_BUTTON, self.branch)

    def test_the_in_range_branch_no_longer_opens_a_context_menu(self):
        """The one cascade left in this function is the out-of-range command."""
        self.assertEqual(
            self.branch.count("useContextMenuCascadeOnOverviewEntry"), 0,
            "the in-range branch reaches the cascade through "
            "closeInOnOverviewEntry only, which is the out-of-range command")

    def test_the_out_of_range_branch_is_untouched(self):
        """`closeInOnOverviewEntry` with EVE's own command list, as before.

        The panel carries `selectedItemActivateGate` only in range, so there is
        nothing to press from out there and the command that flies the ship in is
        one the cascade does land.
        """
        self.assertIn("closeInOnOverviewEntry", self.branch)
        self.assertIn(
            "menuEntries = [ \"activate gate\", \"activate\", \"approach\" ]",
            self.branch)

    def test_the_range_is_what_chooses_between_the_two_mechanisms(self):
        """The distance decides, and each arm keeps its own mechanism.

        The panel carries `selectedItemActivateGate` only in range, so a version
        that routed a 40 km gate to the panel press would sit there waiting for
        a button that cannot appear until something closes the distance -- and
        nothing in this branch would then close it. Pinned on the comparison
        rather than on the two mechanisms being present, because both remain
        present in the source when the split itself is broken.
        """
        self.assertRegex(
            self.branch,
            r"if interactionRangeInMeters < distanceInMeters then"
            r".*?closeInOnOverviewEntry")
        self.assertRegex(
            self.branch,
            r"closeInOnOverviewEntry.*?else case gateActivationStep")

    def test_the_press_is_wrapped_in_the_approach_guard(self):
        """EVE flies the ship over and takes the gate on arrival.

        Re-issuing while that is running restarts the manoeuvre, which is the
        same defect the mission runner's `dockAtDestinationStation` measured at
        one command per reading for 486 seconds.
        """
        self.assertRegex(
            self.branch,
            r"unlessAlreadyClosingIn context \"I see an acceleration gate[^\"]*\" "
            r"\(ensureDronesRecalledBeforeWarping context \(clickUiElement button\)")

    def test_the_drones_still_come_home_before_the_gate_fires(self):
        self.assertIn("ensureDronesRecalledBeforeWarping", self.branch)

    def test_the_branch_selects_before_it_presses(self):
        """The panel acts on whatever is selected, not on whatever we mean."""
        self.assertIn("SelectTheGate -> ", self.branch)
        self.assertIn("clickUiElement accelerationGateEntry.uiNode", self.branch)

    def test_the_bound_is_read_through_the_rule_and_not_a_second_time(self):
        """One comparison, so two places cannot disagree about the give-up."""
        self.assertNotIn("gateRefusesThisShipTicks", self.branch)
        self.assertIn(
            "gateRefusesThisShipTicks < gateCase.askedReadings",
            collapsed(body_of(self.source, "gateActivationStep")))

    def test_the_counter_is_written_through_the_rule(self):
        update = collapsed(
            body_of(self.source, "updateMemoryForNewReadingFromGame"))
        self.assertIn("gateWithinReachTicks =", update)
        self.assertIn(
            "gateAskedReadingsAfterReading { asking = "
            "askingAnAccelerationGateToOpen", update)
        self.assertIn(
            "gateWithinReach = accelerationGateIsWithinReach", update)

    def test_the_panel_read_is_shared_with_the_memory_update(self):
        """One definition of "is the panel showing this row", not two.

        The memory update never sees a decision, so a second copy written for it
        is a second answer that can drift from the one the press uses.
        """
        rule = collapsed(body_of(self.source, "askingAnAccelerationGateToOpen"))
        self.assertIn("selectedItemIsOverviewEntry", rule)
        self.assertEqual(
            self.source.count("\nselectedItemIsOverviewEntry :"), 1)


class TheRecordedSaxratRunsTest(unittest.TestCase):
    """What the corpus says, as relations rather than as the counts above.

    A growing corpus must not turn a true claim red, so nothing here asserts
    "829" or "two"; what it asserts is that the give-up lines collapse to very
    few episodes, that the run-5 episode is dominated by a branch that outranks
    the gate, and that the bound sits in a gap rather than through a
    distribution.
    """

    GIVE_UP = re.compile(r"sitting on this acceleration gate for (\d+)|"
                         r"asking this acceleration gate to open for (\d+)")
    IN_REACH = re.compile(
        r"(?:Ticks on an acceleration gate in reach|"
        r"Readings spent asking an acceleration gate to open): (\d+)")

    @staticmethod
    def episodes(counts):
        """Maximal non-decreasing runs of a nonzero counter -- one per gate."""
        found = []
        current = None
        previous = None
        for value in counts:
            if value == 0:
                current = None
            elif current is None or (previous is not None and value < previous):
                current = [value]
                found.append(current)
            else:
                current.append(value)
            previous = value
        return found

    def counters(self, text):
        return [int(m.group(1)) for m in self.IN_REACH.finditer(text)]

    def test_the_give_up_lines_are_a_handful_of_gates(self):
        """The count an operator sees is readings, not gates.

        The give-up prints on every reading past the bound, so a run that met one
        gate it could not open reports hundreds of lines about it. Asserted as
        the relation: far more lines than episodes.
        """
        for path in saxrat_runs(4, 5):
            name = os.path.basename(path)
            text = read_log(path)
            lines = len(self.GIVE_UP.findall(text))
            over = [e for e in self.episodes(self.counters(text)) if e[-1] > 40]
            self.assertTrue(lines > 0, "%s: no give-up lines to count" % name)
            self.assertTrue(
                len(over) * 10 < lines,
                "%s: %d give-up lines over %d episodes -- if these are now "
                "comparable the give-up is no longer per reading and this "
                "case's premise has changed" % (name, lines, len(over)))

    def test_the_bound_sits_in_a_gap_in_the_recorded_episodes(self):
        """Every episode is far below 40 or far above it, and none is near.

        That separation is what makes 40 a threshold rather than a cut through a
        distribution, and it is why the number did not have to move when the
        mechanism did.
        """
        peaks = []
        for path in saxrat_runs(1, 2, 3, 4, 5):
            text = read_log(path)
            peaks.extend(e[-1] for e in self.episodes(self.counters(text)))
        self.assertTrue(peaks, "no in-reach episodes in the corpus at all")
        below = [p for p in peaks if p <= 40]
        above = [p for p in peaks if p > 40]
        self.assertTrue(below, "no episode ever ended below the bound")
        self.assertTrue(above, "no episode ever passed the bound")
        self.assertTrue(
            max(below) * 4 < min(above),
            "the recorded episodes no longer separate: highest below the bound "
            "%d, lowest above it %d" % (max(below), min(above)))

    def test_run_5s_episode_is_a_branch_that_outranks_the_gate(self):
        """Not the mechanism failing, which is why this change is scoped small.

        `warpToOpportunitySiteIfAvailable` is consulted before the gate branch,
        so for the whole of that episode the gate was nearby and unasked. The
        relation asserted is that the opportunity branch dwarfs every gate
        activation decision in the same run.
        """
        for path in saxrat_runs(5):
            name = os.path.basename(path)
            text = read_log(path)
            opportunity = text.count("'Warp to Site' opportunity")
            activations = text.count("activate it to move to the next pocket")
            self.assertTrue(
                activations * 100 < opportunity,
                "%s: %d opportunity warps against %d in-range gate activations "
                "-- the premise that the gate was never asked has changed"
                % (name, opportunity, activations))

    def test_the_give_ups_are_one_contiguous_block_per_run(self):
        """Which is the shape a per-reading give-up about one gate has.

        Hundreds of lines spread across a run would be many gates and a very
        different finding; hundreds in one block is one gate reported on every
        reading. Asserted as the relation rather than as "one block", so a
        corpus that grows can add blocks without turning this red -- what it
        refuses is the give-ups being scattered.
        """
        for path in saxrat_runs(4, 5):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            at = [i for i, line in enumerate(lines)
                  if "has not taken me anywhere" in line
                  or "asking this acceleration gate to open for" in line]
            self.assertTrue(at, "%s: no give-up lines" % name)
            blocks = 1 + sum(1 for a, b in zip(at, at[1:]) if b - a > 500)
            self.assertTrue(
                blocks * 20 < len(at),
                "%s: %d give-up lines in %d blocks -- these no longer cluster, "
                "so they are no longer a few gates reported many times"
                % (name, len(at), blocks))

    def test_the_give_ups_sit_where_the_opportunity_branch_is_silent(self):
        """#147, seen in the recordings, and the reason a low count proves little.

        `warpToOpportunitySiteIfAvailable` is consulted before the gate branch
        and answers `Just` while a "Warp to Site" button is anywhere in the tree,
        so the gate is unreachable for as long as one is drawn. Run 5 has more
        than ten thousand of those lines and **none** inside its give-up block:
        the branch became reachable only when the button went away. Not fixed
        here -- what this case pins is that the reading of the corpus which
        justifies counting the ask still holds.
        """
        for path in saxrat_runs(5):
            name = os.path.basename(path)
            lines = read_log(path).splitlines()
            give = [i for i, line in enumerate(lines)
                    if "has not taken me anywhere" in line
                    or "asking this acceleration gate to open for" in line]
            opportunity = [i for i, line in enumerate(lines)
                           if "'Warp to Site' opportunity" in line]
            self.assertTrue(give and opportunity,
                            "%s: nothing to compare" % name)
            inside = [i for i in opportunity if give[0] <= i <= give[-1]]
            self.assertTrue(
                len(inside) * 50 < len(opportunity),
                "%s: %d of %d opportunity warps fall inside the give-up block "
                "-- the two are no longer exclusive and the shadowing reading "
                "of this run has changed" % (name, len(inside), len(opportunity)))

    def test_no_client_refusal_was_ever_recorded_beside_a_gate(self):
        """Which is the whole reason the give-up cannot name a cause.

        The client does have a sentence for a gate that wants an item, and the
        mission runner reads it. Nothing of the sort appears in any saxrat run.
        """
        for path in saxrat_runs(3, 4, 5):
            name = os.path.basename(path)
            text = read_log(path)
            self.assertNotIn("This gate is locked", text,
                             "%s: the client did explain a gate here, and the "
                             "give-up could say so" % name)


if __name__ == "__main__":
    unittest.main()
