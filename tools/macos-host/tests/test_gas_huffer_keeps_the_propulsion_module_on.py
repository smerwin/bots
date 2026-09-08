"""The gas huffer's propulsion module: on through every warp, and never pressed
at a module that is already running.

Issue #465, under #456, and it is the last of that series. The operator's reason
is that a gas huffer's survival plan is speed rather than tank -- the hull has no
guns and nothing worth calling a tank -- so the propulsion module is what keeps
the ship alive if rats spawn, and it has to be running through the retreat, each
evasion bounce and the deposit trip both ways. That is the opposite of what every
other app in this repository does: they funnel their warps through
`ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`, which switches
the module off as a courtesy on the way out.

**The failure is silent in the worst available direction**, which is why the
issue asks for a property rather than a check. A bot that deactivates the module
before warping warps correctly, logs correctly, and is slow exactly when it is
being shot at; nothing in a reading, a log or a status line says so unless
somebody puts it there. So two things are asserted here and neither of them is a
source read of one branch.

**No warp path reaches a declaration that presses the module's hotkey.** Asserted
over the *call graph* rather than over the warp declarations themselves, because
the shape the issue warns about is a deactivation that is not named "deactivate"
at the call site -- it is reached *through* a warp helper doing it as a courtesy,
which reading the warp branch would not catch. Every warp call site in the app is
found rather than listed (four of them, covering five warps), the transitive
closure of each is taken, and no declaration in any of them may name the chord or
carry a deactivating name. `TheDetectorFindsItInSaxratTest` runs the same
construction over `eve-online-saxrat`, where it *does* find one, so the property
is shown able to detect the thing rather than merely to answer no.

**The activation guard presses only where the module does not already read
running.** A module button is a toggle, so a press aimed at a running module
switches it **off** -- which is this issue's own failure arriving by the front
door. `propulsionStep` is executed at all five of its answers, including the two
that are declines rather than presses: an unreadable module is not pressed at (a
toggle must never be pressed on a guess), and neither is one whose last press has
not had time to show up.

**Which field says "active" was the open question, and the answer is that it is
the same field read from the other end.** `deactivatePropulsionModuleBeforeWarping`
reads `.isActive`, and #465 is right that it is correct to -- but `.isActive`
*is* `ramp_active`, the entry `moduleRunningState` already reads, so the two
rules differ in which of its values they act on rather than in which field they
consult. A deactivation must be sure the module is on and acts on `Just True`; an
activation must be sure it is off and acts on the widget being absent. Both
decline `Just False`, and that is asserted here in both directions.

**And the press is bounded**, because it sits above the retreat. A middle row
whose first module is not a propulsion module reads as not running on every
reading of the session, and an unbounded rule there is a ship that never leaves a
hostile grid -- #257's shape in the worst place to put it.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`, and folded over
whole sessions rather than asked once where the answer depends on a count. Every
ship UI they are asked about is built by running a UI tree through the **real**
`EveOnline.ParseUserInterface`, so a module that reads as running does so because
the parser said it did.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode gives a reading with no ship UI, which this rule
answers `CannotTellWhetherItIsRunning` for -- the same answer a correct decline
gives, for the wrong reason, silently.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl
from test_gas_huffer_scaffold import (
    APPLICATIONS_DIR, GAS_HUFFER_DIR, bot_source, collapsed, source_of,
    top_level_declarations)
from test_gas_huffer_harvests_a_cloud import reading_binding, ship_ui

PREAMBLE = (
    "import Bot exposing (..)",
    "import Common.EffectOnWindow as EffectOnWindow",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The five declarations in this app that open a warp cascade, and the warps
# they carry. #465 says "at least four" and names five warps; the deposit's
# return leg is the hunt warp again, which is why four declarations covered
# five before #485 split one of them in two.
#
# `warpToScanResult` is `warpToTheHuntedSite`'s own `ScannedAnomaly` arm,
# pulled out by #485 so a scan result carrying its own warp button can take
# a one-click path instead of the two-level cascade -- the cascade stays as
# the fallback for a result with no such button, and both live in this one
# declaration rather than the caller.
WARP_CALL_SITES = {
    "warpToTheHuntedSite":
        "the warp to the site (#461), and the deposit's return leg (#464)",
    "warpToScanResult":
        "warpToTheHuntedSite's own ScannedAnomaly arm, split out by #485",
    "warpToTheRetreatDestination": "the retreat, all three rungs (#463)",
    "warpToACelestialAtARandomRange": "each evasion bounce (#463)",
    "actOnTheDepositStep": "the deposit trip out (#464)",
}

# What must not be reachable from any of them. The first two are the helpers
# every other app in this repo warps through; the third is the shape of a step
# that would do the same thing under a name of its own.
DEACTIVATION_NAMES = (
    "ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping",
    "deactivatePropulsionModuleBeforeWarping",
    "SwitchThePropulsionModuleOff",
)

DEACTIVATING_NAME = re.compile(r"deactivat|switchoff|switchitoff|turnoff",
                               re.IGNORECASE)

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

SAXRAT_BOT_ELM = os.path.join(
    APPLICATIONS_DIR, "eve-online-saxrat", "Bot.elm")


def call_graph(declarations):
    """Which top-level declarations each one names, as {name: {names}}.

    Deliberately **over-approximate**: every identifier token in a declaration's
    body that is the name of another top-level declaration counts as an edge,
    including one that only occurs inside a string. That widens every closure
    below, which can only make the property this file asserts stronger -- a
    warp path is required to reach *nothing* that touches the module, so an
    edge that is not really a call cannot hide one that is.

    Doc comments are already gone: `top_level_declarations` strips them, which
    matters here because `warpToTheHuntedSite`'s own comment names the helper it
    refuses to reach.
    """
    names = set(declarations)
    return {
        name: {token for token in IDENTIFIER.findall(collapsed(body))
               if token in names and token != name}
        for name, body in declarations.items()
    }


def reachable_from(graph, start):
    """Everything `start` can reach, including itself."""
    seen = {start}
    pending = [start]
    while pending:
        for name in graph.get(pending.pop(), ()):
            if name not in seen:
                seen.add(name)
                pending.append(name)
    return seen


def declarations_naming(declarations, token):
    """Every declaration whose body names `token`, other than its own.

    The annotation line is part of the body `top_level_declarations` returns, so
    a constant would otherwise report itself.
    """
    return {name for name, body in declarations.items()
            if name != token and token in IDENTIFIER.findall(collapsed(body))}


def situation(reading="Just ModuleIsNotRunning", pressed_recently=False,
              presses=0):
    """A `PropulsionSituation` written out, since it is a record of plain facts.

    Written here rather than derived from a reading, for the reason
    `propulsionStep` takes the record at all: the answers this rule has to get
    right include combinations no single fixture can be in at once -- a module
    that reads off *and* a press already in flight *and* a count against the
    bound. `propulsionSituationFromContext` is what builds one from a client,
    and it is asked about separately, off a real parsed ship UI.
    """
    return ("{ moduleReading = %s"
            ", pressedRecently = %s"
            ", pressesUnanswered = %d }" % (
                reading, "True" if pressed_recently else "False", presses))


class GasHufferRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-propulsion-repl-")
        kwargs.setdefault("app_dir", GAS_HUFFER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    def rendered(self, expressions, definitions=()):
        """Each answer rendered whole, constructor and payload.

        `Debug.toString` rather than a battery of equalities: one answer per
        question, naming *which* constructor the rule gave, so a rule that
        answers two things at once -- or none -- fails rather than passing on
        whichever equality a case happened to ask.
        """
        return self.strings(["Debug.toString (%s)" % expression
                             for expression in expressions],
                            definitions=list(definitions))


def repl():
    return open_repl(GasHufferRepl)


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a module row, that it is there.

    Every case below is of the form "the rule pressed" or "the rule declined",
    and a fixture that never decoded gives a reading with no ship UI -- which
    this rule answers `CannotTellWhetherItIsRunning` for, correctly, which is
    also one of the answers under test.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def reading_says(self, expression, **ship):
        return self.repl.rendered(
            [expression],
            definitions=[reading_binding("reading", [ship_ui(**ship)])])[0]

    def test_a_ship_ui_with_a_middle_row_comes_back_from_the_real_parser(self):
        self.assertEqual(
            self.reading_says(
                "reading |> Maybe.andThen .shipUI"
                " |> Maybe.map (.moduleButtonsRows >> .middle >> List.length)"),
            "Just 1")

    def test_a_fixture_with_no_middle_row_is_a_ship_ui_all_the_same(self):
        """The distinction the decline rests on: the reading arrived and the
        row is genuinely empty, rather than the whole tree having failed."""
        self.assertEqual(
            self.reading_says(
                "reading |> Maybe.andThen .shipUI"
                " |> Maybe.map (.moduleButtonsRows >> .middle >> List.length)",
                middle_ramps=()),
            "Just 0")


class TheModuleReadingIsTheSameFieldReadFromTheOtherEndTest(unittest.TestCase):
    """#465's open question, answered off the entry both rules already read.

    `deactivatePropulsionModuleBeforeWarping` reads `.isActive`, which the
    vendored parser fills from `ramp_active` -- the same entry
    `moduleRunningState` reads. So the two rules do not want different fields;
    they want different *values* of one field, and each takes the value that is
    strong evidence for its own press:

      - a deactivation must be sure the module is on: `Just True` says so.
      - an activation must be sure it is off: the widget being **absent** says
        so, on 20,095 observations in #286 and not one of them a running module.

    Both decline `Just False`, which is the value neither can read safely, and
    both cases are here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step_for(self, **ship):
        """From a real UI tree to the rule's answer, with nothing in between.

        The reading goes through the real parser, `propulsionModuleFromShipUI`
        finds the module the client-setup contract puts first in the middle row,
        `moduleRunningState` reads it, and `propulsionStep` answers -- which is
        the whole path `propulsionSituationFromContext` takes on a live reading.
        """
        return self.repl.rendered([
            "propulsionStep"
            " { moduleReading ="
            " (reading |> Maybe.andThen .shipUI"
            " |> Maybe.andThen propulsionModuleFromShipUI"
            " |> Maybe.map moduleRunningState)"
            " , pressedRecently = False"
            " , pressesUnanswered = 0 }",
        ], definitions=[reading_binding("reading", [ship_ui(**ship)])])[0]

    def test_a_module_with_a_ramp_widget_is_left_alone(self):
        self.assertEqual(self.step_for(middle_ramps=(True,)),
                         "TheModuleIsRunning")

    def test_a_ramp_reading_false_is_left_alone_too(self):
        """The value neither rule acts on. Read as off, an activation presses a
        module that is on, which is a toggle switching it off -- and that is
        this issue's own failure arriving by the front door."""
        self.assertEqual(self.step_for(middle_ramps=(False,)),
                         "TheModuleIsRunning")

    def test_a_module_with_no_ramp_widget_is_the_one_that_gets_pressed(self):
        self.assertEqual(self.step_for(middle_ramps=(None,)), "SwitchItOn")

    def test_an_empty_middle_row_is_not_pressed_at(self):
        """A toggle must not be pressed on a guess: `Alt+F1` at a ship whose
        modules are arranged some other way presses whatever is bound there."""
        self.assertEqual(self.step_for(middle_ramps=()),
                         "CannotTellWhetherItIsRunning")

    def test_the_first_module_in_the_row_is_the_one_read(self):
        """The client-setup contract puts the propulsion module first, and the
        row is sorted by x rather than taken in parser order -- the parser drops
        a slot whose region it cannot read, so an index names a different module
        from one reading to the next."""
        self.assertEqual(self.step_for(middle_ramps=(None, True)),
                         "SwitchItOn")
        self.assertEqual(self.step_for(middle_ramps=(True, None)),
                         "TheModuleIsRunning")
        self.assertIn("moduleButtonsLeftToRight",
                      collapsed(top_level_declarations(
                          bot_source())["propulsionModuleFromShipUI"]))

    def test_nothing_in_the_file_reads_the_fields_286_measured_as_constants(self):
        """`isInActiveState` is `not isDeactivating` and is true on 99.7% of all
        observations; `.isActive` is the duty cycle under another name. A rule
        reading either as "switched on" presses a running module."""
        bodies = " ".join(collapsed(text) for text
                          in top_level_declarations(bot_source()).values())
        for field in (".isActive", "isInActiveState", "isDeactivating"):
            with self.subTest(field):
                self.assertNotIn(field, bodies)


class TheActivationGuardPressesOnlyWhenItReadsOffTest(unittest.TestCase):
    """The five answers, executed. Only one of them presses anything.

    #465 asks for exactly three of these by name -- active means no press,
    inactive means press, unreadable means no press -- and the other two are
    what a rule that has to live above a retreat needs: a press already in
    flight, and a client that has answered none of them.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["propulsionStep %s" % situation(**kwargs)])[0]

    def test_a_running_module_is_never_pressed_at(self):
        self.assertEqual(self.step(reading="Just ModuleIsRunning"),
                         "TheModuleIsRunning")

    def test_a_module_that_reads_off_is_pressed(self):
        self.assertEqual(self.step(reading="Just ModuleIsNotRunning"),
                         "SwitchItOn")

    def test_a_module_this_reading_cannot_read_is_not_pressed_at(self):
        self.assertEqual(self.step(reading="Nothing"),
                         "CannotTellWhetherItIsRunning")

    def test_a_reading_it_cannot_read_declines_whatever_else_is_true(self):
        """The decline is on the reading and on nothing else, so a press in
        flight or a spent budget cannot turn it into one."""
        for pressed in (False, True):
            for presses in (0, 3, 99):
                with self.subTest(pressed=pressed, presses=presses):
                    self.assertEqual(
                        self.step(reading="Nothing", pressed_recently=pressed,
                                  presses=presses),
                        "CannotTellWhetherItIsRunning")

    def test_a_press_already_in_flight_is_waited_out_rather_than_repeated(self):
        """`clickModuleButtonButWaitIfClickedInPreviousStep`'s reason applied to
        the key that stands in for the click: a second press before the client
        has shown the first one's result switches the module back off."""
        self.assertEqual(
            self.step(reading="Just ModuleIsNotRunning", pressed_recently=True),
            "WaitForTheLastPressToShow")

    def test_the_settling_window_outranks_the_bound(self):
        """A press in flight is not a press to be counted against the budget --
        it is one the client has not answered yet."""
        self.assertEqual(
            self.step(reading="Just ModuleIsNotRunning", pressed_recently=True,
                      presses=99),
            "WaitForTheLastPressToShow")

    def test_the_two_declines_are_the_ones_that_do_not_press(self):
        """Asked as the whole grid rather than case by case, so a rule that
        answered `SwitchItOn` for something not listed here fails."""
        presses = {
            ("Just ModuleIsRunning", False, 0): "TheModuleIsRunning",
            ("Just ModuleIsRunning", True, 0): "TheModuleIsRunning",
            ("Just ModuleIsNotRunning", False, 0): "SwitchItOn",
            ("Just ModuleIsNotRunning", True, 0): "WaitForTheLastPressToShow",
            ("Nothing", False, 0): "CannotTellWhetherItIsRunning",
            ("Nothing", True, 0): "CannotTellWhetherItIsRunning",
        }
        for (reading, pressed, spent), expected in presses.items():
            with self.subTest(reading=reading, pressed=pressed):
                self.assertEqual(
                    self.step(reading=reading, pressed_recently=pressed,
                              presses=spent),
                    expected)

    def test_the_one_answer_that_acts_is_the_only_one_that_yields_a_step(self):
        """`keepThePropulsionModuleRunning` takes a whole `BotDecisionContext`,
        so what it answers cannot be executed here. What can be read is its
        shape: one arm of the case produces a `Just`, and it is `SwitchItOn`'s.
        """
        body = collapsed(top_level_declarations(
            bot_source())["keepThePropulsionModuleRunning"])
        self.assertIn("SwitchItOn -> Just", body)
        self.assertIn("_ -> Nothing", body)
        self.assertEqual(body.count("Just ("), 1, body)

    def test_it_never_waits_for_progress(self):
        """Four of the five answers hand the reading straight back. A branch
        that waited here would hold the retreat, which is the one thing this
        rule sits above and must never delay beyond the press itself."""
        self.assertNotIn("waitForProgressInGame", collapsed(
            top_level_declarations(bot_source())[
                "keepThePropulsionModuleRunning"]))


class ThePressesAreBoundedTest(unittest.TestCase):
    """A branch on the hot path that can act forever without progressing.

    This one sits **above the retreat**, so an unbounded version of it is a ship
    that never leaves a hostile grid -- #257's shape in the worst place to put
    it, and reachable by nothing more exotic than a middle row whose first
    module is offline or is not a propulsion module at all.

    The counter is folded over sessions rather than asked once, because a
    counter that is right for one reading and wrong across a session is the
    defect the shape prevents.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def folded(self, answers):
        """`propulsionPressesAfterReading` folded over a session of readings."""
        return self.repl.rendered([
            "List.foldl propulsionPressesAfterReading 0 [ %s ]" % ", ".join(
                "{ pressDispatched = %s, readsRunning = %s }" % (
                    "True" if pressed else "False",
                    "True" if running else "False")
                for pressed, running in answers)
        ])[0]

    def test_a_press_the_client_never_answers_is_counted(self):
        self.assertEqual(self.folded([(True, False)] * 4), "4")

    def test_a_module_that_reads_running_clears_the_count_outright(self):
        """Which is what makes the bound one on a single attempt rather than a
        session budget: a run that docks gets its whole budget back on the
        reading after it undocks."""
        self.assertEqual(
            self.folded([(True, False)] * 5 + [(False, True)]), "0")
        self.assertEqual(
            self.folded([(True, False)] * 5 + [(False, True)] +
                        [(True, False)]), "1")

    def test_a_reading_that_could_not_read_the_module_holds_the_count(self):
        """#145's rule: a reset on a reading that did not ask is what pins a
        counter at one forever. Here the readings that cannot answer are the
        docked ones, which is exactly the stretch a deposit spends."""
        self.assertEqual(
            self.folded([(True, False)] * 3 + [(False, False)] * 20), "3")

    def test_one_press_counts_once_however_long_the_window_is(self):
        self.assertEqual(
            self.folded([(True, False)] + [(False, False)] * 4), "1")

    def test_the_bound_ends_the_asking_and_one_press_fewer_does_not(self):
        bound = int(self.repl.rendered(["propulsionPressesBeforeGivingUp"])[0])
        self.assertEqual(
            self.repl.rendered([
                "propulsionStep %s" % situation(presses=bound - 1),
                "propulsionStep %s" % situation(presses=bound),
                "propulsionStep %s" % situation(presses=bound + 1),
            ]),
            ["SwitchItOn", "GivenUpOnSwitchingItOn", "GivenUpOnSwitchingItOn"])

    def test_the_bound_is_a_real_number_rather_than_one_that_admits_anything(self):
        """A boundary pair alone passes for *any* constant, including one that
        gives up on the first reading and one that never gives up. So a fixed
        value either side rides along, which is the hole four of #120's own
        cases had.
        """
        bound = int(self.repl.rendered(["propulsionPressesBeforeGivingUp"])[0])
        self.assertGreaterEqual(bound, 3)
        self.assertLessEqual(bound, 20)
        self.assertEqual(
            self.repl.rendered([
                "propulsionStep %s" % situation(presses=2),
                "propulsionStep %s" % situation(presses=40),
            ]),
            ["SwitchItOn", "GivenUpOnSwitchingItOn"])

    def test_a_session_of_unanswered_presses_gives_up_and_stays_given_up(self):
        """The fold and the rule together, which is the failure mode itself:
        press, count, press, count, and then stop."""
        bound = int(self.repl.rendered(["propulsionPressesBeforeGivingUp"])[0])
        spent = self.folded([(True, False)] * (bound + 5))
        self.assertEqual(
            self.repl.rendered(
                ["propulsionStep %s" % situation(presses=int(spent))])[0],
            "GivenUpOnSwitchingItOn")

    def test_the_counter_is_written_where_every_reading_reaches_it(self):
        """In the memory update, which is the one thing that runs on every
        reading whatever the decision tree did with it -- and the press is read
        out of the effects the bot dispatched rather than out of anything the
        client said.

        **The argument is sliced rather than searched for**, which is the half
        this case did not have on its first pass: `previousStepsEffects |>
        List.head` occurs in that declaration twice, once here and once for the
        deposit's drag, so a mutation that pointed *this* one at the whole
        settling window went on satisfying a substring check on the strength of
        the other one. Asserting the form is the lesson #109's status clause,
        #122's trust rule and #145's named button each paid for once already.
        """
        update = collapsed(top_level_declarations(
            bot_source())["updateMemoryForNewReadingFromGame"])
        self.assertIn("propulsionPressesAfterReading", update)
        argument = update.split("propulsionPressesAfterReading", 1)[1].split(
            "botMemoryBefore.propulsionPressesUnanswered", 1)[0]
        self.assertIn("stepPressedExactly propulsionModuleHotkey", argument)
        self.assertIn("previousStepsEffects |> List.head", argument)
        for whole_window in ("List.any", "List.take", "moduleButtonClickSettlingSteps"):
            with self.subTest(whole_window):
                self.assertNotIn(whole_window, argument)


class NoWarpPathReachesADeactivationTest(unittest.TestCase):
    """The property, over the call graph rather than over one branch.

    #465 is explicit that a source read is not enough on its own, and about why:
    the deactivation is not named "deactivate" at every call site -- it is
    reached *through* a warp helper that does it as a courtesy. So every warp
    call site in the app is found rather than listed, the transitive closure of
    each is taken, and nothing in any of them may name the module's chord or
    carry a deactivating name.

    A future pull request that routes one of these warps through a helper which
    switches the module off fails here whatever it calls that helper.
    """

    @classmethod
    def setUpClass(cls):
        cls.declarations = top_level_declarations(bot_source())
        cls.graph = call_graph(cls.declarations)

    def test_every_warp_call_site_is_found_rather_than_listed(self):
        """The property is worthless if it holds by finding no warps. What
        opens a warp cascade in this app is `warpCascadeWithin`, one
        declaration with several readers, so the readers are the call sites.
        """
        found = declarations_naming(self.declarations, "warpCascadeWithin")
        self.assertEqual(found, set(WARP_CALL_SITES), found)
        self.assertGreaterEqual(len(found), 4)

    def test_no_warp_path_reaches_the_modules_chord(self):
        pressers = declarations_naming(self.declarations,
                                       "propulsionModuleHotkey")
        self.assertTrue(pressers, "nothing names the chord at all")
        for site, what in WARP_CALL_SITES.items():
            with self.subTest(site=site, warps=what):
                reached = reachable_from(self.graph, site)
                self.assertEqual(reached & pressers, set(),
                                 "%s reaches %s" % (site, reached & pressers))

    def test_no_warp_path_reaches_a_deactivating_name(self):
        for site in WARP_CALL_SITES:
            with self.subTest(site=site):
                named = {name for name in reachable_from(self.graph, site)
                         if DEACTIVATING_NAME.search(name)}
                self.assertEqual(named, set(), "%s reaches %s" % (site, named))

    def test_the_shared_helpers_every_other_app_warps_through_are_absent(self):
        bodies = " ".join(collapsed(text)
                          for text in self.declarations.values())
        for forbidden in DEACTIVATION_NAMES:
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, bodies)

    def test_the_only_declaration_that_presses_it_switches_it_on(self):
        """Everything that names the chord, and what each does with it: one
        presses, one reads the settling window, one counts the press against a
        bound. None of the three is reachable from a warp."""
        pressers = declarations_naming(self.declarations,
                                       "propulsionModuleHotkey")
        self.assertEqual(
            pressers,
            {"keepThePropulsionModuleRunning", "propulsionSituationFromContext",
             "updateMemoryForNewReadingFromGame"},
            pressers)
        pressing = collapsed(
            self.declarations["keepThePropulsionModuleRunning"])
        self.assertIn("hotkeyEffects propulsionModuleHotkey", pressing)
        self.assertIn("SwitchItOn ->", pressing)

    def test_the_harvest_loop_no_longer_has_a_second_copy_of_it(self):
        """Two branches pressing one toggle is the flicker
        `manageMiddleRowModules` was split up to end, and here the second copy
        would press *inside* the first's settling window."""
        bodies = " ".join(collapsed(text)
                          for text in self.declarations.values())
        self.assertNotIn("SwitchThePropulsionModuleOn", bodies)
        for name in ("harvestStep", "harvestSituationFromContext",
                     "actOnTheHarvestStep", "describeHarvestSituation"):
            with self.subTest(name):
                self.assertNotIn("propulsion",
                                 collapsed(self.declarations[name]).lower())


class TheDetectorFindsItInSaxratTest(unittest.TestCase):
    """The same construction over an app that *does* deactivate, as the control.

    Without this, `NoWarpPathReachesADeactivationTest` is a case that answers
    "nothing found" and cannot say whether it would have found anything. saxrat
    is the app this one is forked from and it funnels its anomaly warp through
    `ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`, so the
    closure from its warp reaches a deactivation by a chain of calls -- which is
    exactly the shape #465 says a source read of one branch would miss.
    """

    @classmethod
    def setUpClass(cls):
        cls.declarations = top_level_declarations(source_of(SAXRAT_BOT_ELM))
        cls.graph = call_graph(cls.declarations)

    def test_saxrats_warp_reaches_a_deactivation_it_does_not_name_itself(self):
        reached = reachable_from(self.graph, "enterAnomaly")
        self.assertIn("deactivatePropulsionModuleBeforeWarping", reached)
        # And it is reached *through* something else, which is the whole point:
        # the warp branch itself names neither the deactivation nor the module.
        body = collapsed(self.declarations["enterAnomaly"])
        self.assertNotIn("deactivatePropulsionModuleBeforeWarping", body)

    def test_the_deactivation_it_finds_is_a_press_at_the_same_module(self):
        """So the thing being detected is a press and not a name: saxrat's
        helper reads the first module in the middle row exactly as this app's
        activation does, and presses its hotkey to switch it off."""
        body = collapsed(
            self.declarations["deactivatePropulsionModuleBeforeWarping"])
        self.assertIn(".moduleButtonsRows", body)
        self.assertIn("middle", body)


class TheGuardIsAskedAboveTheLeavingTest(unittest.TestCase):
    """Where the press sits, which is #465's substance rather than its wording.

    The reading the module matters most on is the one the ship is *leaving* on,
    not one it is harvesting on -- so the guard is asked above the retreat, the
    evasion, the deposit and the harvest alike, and the cost is one reading at
    the head of a retreat that begins with the module off.

    It sits below the Directional Scan refresh, because the scan is the
    instrument the leaving is decided on and a scan skipped is a grid the bot
    cannot see.
    """

    @classmethod
    def setUpClass(cls):
        cls.declarations = top_level_declarations(bot_source())

    def test_the_scan_is_asked_first_and_the_module_second(self):
        body = collapsed(self.declarations["watchLeaveDepositOrHarvest"])
        self.assertLess(body.index("refreshTheDirectionalScanner"),
                        body.index("keepThePropulsionModuleRunning"))
        self.assertLess(body.index("keepThePropulsionModuleRunning"),
                        body.index("leaveDepositOrHarvest"))

    def test_everything_else_is_reached_through_its_declining_arm(self):
        """So a reading the module needs pressing on is a reading that presses
        and nothing else, and every other reading falls straight through."""
        body = collapsed(self.declarations["watchLeaveDepositOrHarvest"])
        self.assertIn("case keepThePropulsionModuleRunning context of", body)
        self.assertIn("Nothing -> leaveDepositOrHarvest context", body)

    def test_the_leaving_the_deposit_and_the_harvest_keep_their_order(self):
        """#463's and #464's ordering is untouched by the hoist: the retreat
        still outranks the deposit, and both still sit above the
        docked-or-in-space split."""
        body = collapsed(self.declarations["leaveDepositOrHarvest"])
        self.assertLess(body.index("actOnTheEvasionStep"),
                        body.index("actOnTheDepositStep"))
        self.assertLess(body.index("actOnTheDepositStep"),
                        body.index("branchDependingOnDockedOrInSpace"))

    def test_it_is_asked_on_readings_with_no_ship_ui_too(self):
        """Not gated on the ship UI at the call site, because the rule's own
        `Nothing` answer covers a docked reading -- and a second place deciding
        whether the module can be read would be a second place to be wrong."""
        body = collapsed(self.declarations["watchLeaveDepositOrHarvest"])
        self.assertNotIn("shipUI", body)
        self.assertIn("context.readingFromGameClient.shipUI", collapsed(
            self.declarations["propulsionSituationFromContext"]))


class TheStatusLineSaysItOnEveryReadingTest(unittest.TestCase):
    """#465 in its own words: *say whether the module reads active on every
    in-space reading*.

    A gas huffer whose propulsion module is off is in a worse position than one
    that never armed it, and the operator should be able to see that at a glance
    rather than infer it from the ship's speed. Until #465 the only place it
    appeared was the harvest clause, which a reading with no cloud on the grid
    does not carry -- so every reading of a retreat, an evasion and a deposit
    said nothing about it at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, **kwargs):
        return self.repl.strings(
            ["describePropulsionModule %s" % situation(**kwargs)])[0]

    def test_the_ordinary_reading_says_running(self):
        self.assertIn("running", self.clause(reading="Just ModuleIsRunning"))

    def test_a_module_that_is_off_says_so_with_the_budget_beside_it(self):
        """The number an operator watches climb. A press being made and a press
        being made for the sixth time read identically without it."""
        clause = self.clause(reading="Just ModuleIsNotRunning", presses=2)
        self.assertIn("NOT RUNNING", clause)
        self.assertIn("2/", clause)

    def test_the_give_up_names_itself_and_what_to_go_and_look_at(self):
        clause = self.clause(reading="Just ModuleIsNotRunning", presses=99)
        self.assertIn("GIVEN UP ON", clause)
        self.assertIn("base speed", clause)
        self.assertIn("middle row", clause)

    def test_an_unreadable_module_says_cannot_tell_rather_than_off(self):
        """Absent evidence is reported as absent. `off` here would be a bot
        telling an operator its propulsion module is off on every docked
        reading of every session."""
        clause = self.clause(reading="Nothing")
        self.assertIn("CANNOT TELL", clause)
        self.assertNotIn("NOT RUNNING", clause)

    def test_every_answer_carries_the_standing_fact(self):
        """The one thing an operator cannot check from a log: nothing in this
        file ever switches the module off."""
        for reading in ("Just ModuleIsRunning", "Just ModuleIsNotRunning",
                        "Nothing"):
            with self.subTest(reading):
                self.assertIn("ever switches it off", self.clause(
                    reading=reading))

    def test_the_clause_is_printed_outside_the_case_that_needs_a_cloud(self):
        """In the outer list, so it is on every reading rather than only on the
        ones with a grid and a cloud on it."""
        body = collapsed(top_level_declarations(
            bot_source())["statusTextFromState"])
        outer = body.split("in [ ", 1)
        self.assertEqual(len(outer), 2, "the outer list moved")
        self.assertIn("describePropulsionModule", outer[1])
        self.assertNotIn("describePropulsionModule", outer[0])

    def test_the_harvest_clause_no_longer_carries_it(self):
        """One reader, said once. Two clauses about one module would be two
        places for an operator to read a different answer."""
        self.assertNotIn("propulsion", collapsed(top_level_declarations(
            bot_source())["describeHarvestSituation"]).lower())


class TheMarkerMovedRatherThanBeingDeletedTest(unittest.TestCase):
    """#456's last issue, so the header's "what this bot cannot do" line has
    nothing left to name from that series.

    It is not deleted, because a bot reporting only what it *can* do is the
    failure this repository is named after. What replaces it is weaker and
    honest: none of this has ever been run against a live client, so every bound
    in it is a relation rather than a measurement.
    """

    def setUp(self):
        self.source = bot_source()
        self.header = self.source.split("\n-}", 1)[0]

    def test_the_header_no_longer_says_the_module_is_missing(self):
        """Absent from the header and from every declaration body. It survives
        in one doc comment, deliberately -- `statusTextFromState`'s own comment
        lists the markers this one has replaced, and a change that dropped that
        list would lose the record of what each issue closed.
        """
        self.assertNotIn("LEAVES WITHOUT ITS PROPULSION MODULE", self.header)
        bodies = " ".join(collapsed(text) for text
                          in top_level_declarations(self.source).values())
        self.assertNotIn("LEAVES WITHOUT ITS PROPULSION MODULE", bodies)

    def test_the_header_says_what_465_did(self):
        self.assertIn("#465", self.header)
        self.assertIn("survives every warp", self.header)

    def test_the_marker_is_still_the_first_thing_and_still_a_limitation(self):
        self.assertIn("NEVER FLOWN", self.header)
        self.assertLess(self.header.index("NEVER FLOWN"),
                        self.header.index("## Configuration Settings"))
        self.assertIn("NEVER FLOWN", collapsed(top_level_declarations(
            self.source)["statusTextFromState"]))


class TheMutationsThisFileCatches(unittest.TestCase):
    """Confirmed by mutation. Each of these was applied to `Bot.elm` and the
    named case failed; the list is here so a later reader can re-run them.

    The three #465 names by hand are 1, 2 and 3.

    1.  **a deactivation step reintroduced on a warp path**, once per warp call
        site: a `deactivateBeforeWarping` helper added and the warp routed
        through it. All four fail
        `NoWarpPathReachesADeactivationTest.test_no_warp_path_reaches_the_
        modules_chord` and `..._reaches_a_deactivating_name`, and the site
        naming it directly also fails `test_the_only_declaration_that_presses_
        it_switches_it_on`.
    1b. the same thing reached **two calls deep** and under a name with nothing
        deactivating in it -- `warpToTheRetreatDestination` calling a
        `prepareToWarp` that calls `settleTheModules`, which presses the chord.
        That one is invisible to a source read of the warp branch and is why
        the case walks the call graph; it fails the same two.
    2.  **the activation guard pressing unconditionally** -- `propulsionStep`
        answering `SwitchItOn` for every reading -- `TheActivationGuardPresses
        OnlyWhenItReadsOffTest.test_a_running_module_is_never_pressed_at`,
        `test_a_module_this_reading_cannot_read_is_not_pressed_at` and
        `test_the_two_declines_are_the_ones_that_do_not_press`.
    3.  **the "already active" read inverted** -- `moduleRunningState` answering
        `ModuleIsRunning` for an absent ramp widget and `ModuleIsNotRunning` for
        a present one -- `TheModuleReadingIsTheSameFieldReadFromTheOtherEndTest`,
        every case in it, off really parsed module rows.
    3b. the milder half of the same: `moduleRunningState` reading the ramp's
        *value* (`Just True` only) rather than its existence, so a module
        between cycles reads as off and gets pressed --
        `test_a_ramp_reading_false_is_left_alone_too`.
    4.  the unreadable case pressed: `propulsionStep`'s `Nothing` arm answering
        `SwitchItOn` -- `test_a_module_this_reading_cannot_read_is_not_pressed_
        at` and `test_a_reading_it_cannot_read_declines_whatever_else_is_true`.
    5.  the settling window dropped from the situation, so a press goes out on
        every reading of the window and the client is asked to toggle a module
        it is in the middle of switching on -- `test_a_press_already_in_flight_
        is_waited_out_rather_than_repeated`, and the bound's own case, since the
        count then climbs on readings no press was answered on.
    6.  the settling clause moved *below* the bound, so a press in flight spends
        the budget -- `test_the_settling_window_outranks_the_bound`.
    7.  the bound removed entirely, and separately raised past anything a
        session reaches -- `test_the_bound_ends_the_asking_and_one_press_fewer_
        does_not` and `test_the_bound_is_a_real_number_rather_than_one_that_
        admits_anything`.
    8.  the bound's comparison moved by one in either direction -- the first of
        those two.
    9.  `propulsionPressesAfterReading` never resetting on a module that reads
        running, so the budget is a session budget and a deposit exhausts it --
        `test_a_module_that_reads_running_clears_the_count_outright`.
    10. the same rule *resetting* on a reading that could not read the module,
        which pins the count at one forever and makes the bound unreachable --
        `test_a_reading_that_could_not_read_the_module_holds_the_count`.
    11. the counter reading the whole of `previousStepsEffects` rather than its
        head, so one press counts once per step of its settling window --
        `test_the_counter_is_written_where_every_reading_reaches_it`. **This one
        survived the first sweep and the hole was real**: that declaration reads
        the head of the effects twice, once for this press and once for the
        deposit's drag, so a substring check went on being satisfied by the
        other one while this extraction was pointed at the whole window. The
        argument handed to the rule is sliced now rather than searched for.
    12. **the guard placed below the leaving**, so the retreat warps before the
        module is switched on -- `TheGuardIsAskedAboveTheLeavingTest.test_the_
        scan_is_asked_first_and_the_module_second`.
    13. the guard placed *above* the scan, which costs the grid verdict a
        reading on the readings it matters -- the same case.
    14. the guard answering `Just waitForProgressInGame` on `WaitForTheLast
        PressToShow`, which holds the whole tree -- and the retreat with it --
        for a settling window -- `test_it_never_waits_for_progress`.
    15. the propulsion stage restored to `harvestStep`, which is the second
        controller for one toggle -- `test_the_harvest_loop_no_longer_has_a_
        second_copy_of_it`.
    16. the status clause dropped from `statusTextFromState`, and separately
        moved inside the case that needs a cloud -- `TheStatusLineSaysItOnEvery
        ReadingTest.test_the_clause_is_printed_outside_the_case_that_needs_a_
        cloud`.
    17. the unreadable state rendered as `not running` -- `test_an_unreadable_
        module_says_cannot_tell_rather_than_off`.
    18. the give-up rendered without its count or without what to go and look
        at -- `test_the_give_up_names_itself_and_what_to_go_and_look_at`.
    19. `propulsionModuleFromShipUI` taking the middle row in parser order
        rather than sorted by x -- `test_the_first_module_in_the_row_is_the_one_
        read`.
    20. a rule started reading `.isActive` or `isInActiveState`, which #286
        measured to be close to a constant -- `test_nothing_in_the_file_reads_
        the_fields_286_measured_as_constants`.
    21. on this file's own premises: the call graph narrowed to direct calls
        only, so a two-deep chain is missed -- `TheDetectorFindsItInSaxratTest`,
        which is what makes the walk demonstrably able to find one.
    """

    def test_the_list_is_here_to_be_read(self):
        self.assertIn("call graph", TheMutationsThisFileCatches.__doc__)


if __name__ == "__main__":
    unittest.main()
