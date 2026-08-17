"""saxrat's loot-window escape: a key that works, and a bound on pressing it.

Issue #285, and it is the **second** recorded instance of one defect.
`decisionIfNoEnemyToAttack`'s escape fired at `lootWindowOpenTicks > 2` and
pressed **Ctrl+W** at a window it had never focused, with no upper bound at all
-- so once the trigger was crossed it was the only thing the bot did for as long
as the window stayed in the reading. Measured live on 2026-08-16, an escalation
room in Uchat with the site cleared: 919 `force it shut (Ctrl+W)` decision lines
and zero windows closed. `Alt+C` pressed by hand at the same client shut it --
`['InventoryPrimary']` before, `[]` after -- the Ctrl+W count froze, and the bot
went on to take an acceleration gate. `CLAUDE.md` already recorded 650 of the
same presses closing nothing a year earlier, as prose that nothing executed.
This file is what executes it.

Recounted here from the run's own log, because the issue's "roughly 190
readings" is an estimate off the line count: 919 lines fall on **303** readings
at three lines a reading, and the bot's own `lootWindowOpenTicks` -- printed in
the same status line -- peaks at **301**. `TheCorpusTest` re-takes both.

## Both halves, because the keystroke alone is not the fix

Ctrl+W is the client's *close the active window* and needs the window focused;
Alt+C is the inventory **toggle** and does not. But swapping the key would leave
the branch unbounded, and a working keystroke that fails for some other reason
takes every reading forever exactly as the broken one did -- PR #257's family
(108 minutes blocked by a hot-path step that could act without progressing) and
PR #272's (8,770 readings at a branch that asked "bounce?" and never bounced).

So `lootWindowCloseRung` is a ladder with a bound, and what the bound falls
through to is asserted rather than described: past
`lootWindowForceCloseGiveUpReadings` the branch hands the reading to
`lootAnotherWreckOrLeaveTheGrid`, which is the *same expression* the
no-loot-window case takes -- open the next notable wreck, scroll one into view,
or leave the grid. It acts, on the reading the bound expires and on every
reading after, and `TheGiveUpActsRatherThanWaits` is what goes red if it stops.

## What is executed and what is read

The rung, the chord, the counter and the status clause are executed through the
real `Bot.elm` in `elm repl`. The counter is **folded over whole sessions**
through the real `updateMemoryForNewReadingFromGame`, over readings the real
`EveOnline.ParseUserInterface` produced -- so "the count resets on a close" is
run rather than read, and a fixture that never parsed is caught by
`TheFixturesAreRealTest` rather than passing as a rule that answered nothing
(#174). The branch itself takes a whole `BotDecisionContext` and is read out of
the source through a whitespace-collapsing reader sliced by indentation.

Confirmed by mutation, listed in `TheMutationsThisFileCatchesTest`.

Nothing here reads a live game client or a running bot. The corpus case reads
the recorded runs in `~/eve-bot-logs`, and only reads them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SaxratRepl, collapsed, label, node, ship_ui,
    source_of)

# The three constants this whole file is about, read back out of `Bot.elm` by
# `TheConstantsAreTheOnesTheSourceCarriesTest` rather than trusted from here.
OWN_CONTROLS_READINGS = 2
CLOSE_CONTROL_READINGS = 6
GIVE_UP_READINGS = 16

# The old chord, kept so the cases can assert the app no longer builds it and so
# `doEffectsPressInventoryToggle` can be asked to decline it.
CTRL_W = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
          ", EffectOnWindow.KeyDown EffectOnWindow.vkey_W"
          ", EffectOnWindow.KeyUp EffectOnWindow.vkey_W"
          ", EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]")

# The propulsion module's own Alt chord, which shares this one's modifier and
# must not satisfy the recogniser -- `doEffectsDeactivatePropulsionModule`'s
# same-modifier problem from the other side.
ALT_F1 = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU"
          ", EffectOnWindow.KeyDown EffectOnWindow.vkey_F1"
          ", EffectOnWindow.KeyUp EffectOnWindow.vkey_F1"
          ", EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU ]")

# A bare `C`, which is what a chord built without pressing the modifier as its
# own effect would come out as -- and what PR #241 established a posted key
# cannot be trusted to carry on its own.
BARE_C = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_C"
          ", EffectOnWindow.KeyUp EffectOnWindow.vkey_C ]")

ALT_C_IN_ORDER = ("[ EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU"
                  ", EffectOnWindow.KeyDown EffectOnWindow.vkey_C"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_C"
                  ", EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU ]")


def window_controls():
    """The title-bar controls, as `parseWindowControls` finds them.

    It takes the first descendant whose type name contains `WindowControls` and
    then looks for a texture path -- the macOS client's is
    `system_icons/close_16px`, which this fork's parser had to learn because the
    upstream `eveicon/window/close` matches nothing here.
    """
    return node("WindowControls", {"_name": "windowControls"}, [
        node("Sprite", {"_name": "closeButton",
                        "texturePath": "res:/UI/Texture/system_icons/close_16px.png"},
             region=(860, 300, 16, 16)),
    ], region=(840, 300, 60, 16))


def loot_window(close_control=True):
    """The window the branch is about, as the real parser reads one.

    `parseInventoryWindowsFromUITreeRoot` takes `InventoryPrimary` and
    `ActiveShipCargo` nodes, and `wreckLootWindowsFromReadingFromGameClient`
    then keeps the ones carrying "Loot All". `InventoryPrimary` deliberately,
    because that is the node the stuck client held: the tree carried no
    `LootWindow` at all, so what the branch was matching in the incident was the
    primary inventory.

    `close_control=False` is the window whose controls the parser cannot find,
    which is the reading the Close rung has to fall through rather than wait on.
    """
    children = [label("Loot All", (600, 400, 80, 16))]
    if close_control:
        children.append(window_controls())
    return node("InventoryPrimary", {"_name": "inventoryPrimary"}, children,
                region=(500, 300, 400, 300))


def plain_inventory():
    """An inventory window with nothing to loot in it.

    The control for every counter case: an inventory the bot opened for some
    other reason is not a wreck's loot window, and must leave the count at zero.
    """
    return node("InventoryPrimary", {"_name": "inventoryPrimary"}, [
        label("Item Hangar", (600, 400, 80, 16)),
    ], region=(500, 300, 400, 300))


def in_space(window=None):
    children = [ship_ui(100, 100, 4)]
    if window is not None:
        children.append(window)
    return children


def declaration(source, name):
    """One top-level declaration, from its annotation to the next one."""
    match = re.search(r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
                      re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def let_binding(source, declaration_name, name):
    """One `let` binding, sliced by **indentation**.

    A reader that ends at the next ` <name> = ` stops at a record literal, which
    is what PRs #147, #156, #159 and #162 each paid for once -- and the binding
    under test here hands `lootWindowCloseRung` a record. This ends at the next
    non-blank line indented no further than the binding's own name.
    """
    lines = declaration(source, declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^(\s*)%s =(\s|$)" % re.escape(name), line)]
    assert opens, "no let binding named %r" % name
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    return collapsed(without_comments("\n".join(lines[start:end])))


def without_comments(text):
    """Comments dropped a **line** at a time, never by matching `--` anywhere.

    Elm's comment marker is also two hyphens, and this branch's own decision
    lines are full of them -- `"... -- force it shut (Alt+C, ...)"`. A stripper
    that cuts at the first `--` truncates every one of those strings, which
    silently hides exactly the text several of these cases assert on.
    """
    text = re.sub(r"\{-.*?-\}", " ", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("--"))


class LootWindowRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus what folding a session of readings costs.

    The bindings ride in the preamble, which `imports_and_bindings` folds into
    the one `let` that asks the question, so they cost the single compile the
    imports do (#172). `askContext` and the session helpers are
    `test_saxrat_route_ask_bound`'s, restated here rather than imported because
    that file's preamble carries anomaly fixtures this one has no use for.
    """

    BINDINGS = (
        # One `UpdateMemoryContext`, exactly as the framework assembles it. The
        # screenshot's two fields are functions and nothing on this path calls
        # them, which is why a reading can be folded without one.
        "lootContext = \\effects reading ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = reading"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , previousStepsEffects = effects"
        " , botSettings = defaultBotSettings }",
        # A session, written as `(repeats, reading)` pairs. The `filterMap` is
        # what a fixture that never parsed falls out of, which is why every case
        # using this asks `sessionLength` beside it -- see #174 for why a
        # fixture that never arrived and a rule that answered nothing look
        # identical from outside.
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "ticksOver = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame (lootContext [] r) memory)"
        " initBotMemory"
        " |> .lootWindowOpenTicks",
        # The high-water mark over a session rather than its final value: a case
        # about a counter that must come back down has to say where it got to.
        "peakTicks = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r ( memory, peak ) ->"
        " let now = updateMemoryForNewReadingFromGame (lootContext [] r) memory"
        " in ( now, max peak now.lootWindowOpenTicks ))"
        " ( initBotMemory, 0 )"
        " |> Tuple.second",
        # The rung a whole session ends on, folded through the same update, so
        # the ladder is asked about a count the bot really produced rather than
        # about a number written in a case.
        "rungAfter = \\settled pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame (lootContext [] r) memory)"
        " initBotMemory"
        " |> (\\m -> lootWindowCloseRung"
        " { readingsOpen = m.lootWindowOpenTicks"
        " , closeControlIsInTheReading = True"
        " , togglePressedRecently = settled })",
        "lootWindowsIn = \\r -> wreckLootWindowsFromReadingFromGameClient r"
        " |> List.length",
        # What the call site hands the rung: the parser's own answer about this
        # window's controls, not a flag written in a case.
        "closeControlIn = \\r -> wreckLootWindowsFromReadingFromGameClient r"
        " |> List.head"
        " |> Maybe.andThen (.uiNode >> EveOnline.ParseUserInterface.parseWindowControlsFromWindow)"
        " |> Maybe.andThen .closeButton"
        " |> (/=) Nothing",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-loot-window-")
        kwargs.setdefault("preamble", PREAMBLE + self.BINDINGS)
        super().__init__(**kwargs)

    def definitions(self):
        return [
            self.reading_binding("looting", in_space(loot_window())),
            self.reading_binding("lootingNoControls",
                                 in_space(loot_window(close_control=False))),
            self.reading_binding("clear", in_space()),
            self.reading_binding("plainInventory",
                                 in_space(plain_inventory())),
        ]


class TheFixturesAreRealTest(unittest.TestCase):
    """Before anything is concluded from a reading, that it arrived.

    A fixture that never decoded and a rule that answered nothing are the same
    answer from outside -- #174, which found a shared harness turning the first
    into the second. So the parser is asked what it made of each tree first.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LootWindowRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_each_reading_parsed(self):
        answers = self.repl.evaluate(
            ["looting /= Nothing", "lootingNoControls /= Nothing",
             "clear /= Nothing", "plainInventory /= Nothing"],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 4,
                         "a fixture did not reach the parser, so every case "
                         "folding it would assert against nothing")

    def test_the_parser_finds_the_close_control_where_the_client_draws_one(self):
        """The input the Close rung is decided on, answered by the real parser.

        Both directions, because a fixture the parser cannot find controls in
        would make `closeControlIsInTheReading` constantly `False` and the rung
        would look correct while never being exercised.
        """
        answers = self.repl.evaluate(
            ["(looting |> Maybe.map closeControlIn) == Just True",
             "(lootingNoControls |> Maybe.map closeControlIn) == Just False"],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 2)

    def test_only_the_window_carrying_loot_all_is_a_wreck_loot_window(self):
        """The branch's own subject, answered by the real parser.

        An inventory the bot opened for some other reason must not start the
        count -- and must not be shut with Alt+C, which is exactly the toggle
        hazard: pressed at no inventory the key *opens* one.
        """
        answers = self.repl.evaluate(
            ["(looting |> Maybe.map lootWindowsIn) == Just 1",
             "(clear |> Maybe.map lootWindowsIn) == Just 0",
             "(plainInventory |> Maybe.map lootWindowsIn) == Just 0"],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 3)


RUNGS = ("UseTheWindowsOwnControls", "ClickTheWindowsCloseControl",
         "PressTheInventoryToggle", "LeaveTheLootWindowAlone")


class TheLadderTest(unittest.TestCase):
    """`lootWindowCloseRung` at every rung and either side of every boundary.

    Asked as four equalities per input, one per constructor, so a rule that
    answers two things at once -- or none -- fails rather than passing on
    whichever constructor a case happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LootWindowRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def rung(self, readings, close_control=True, settled=False):
        expressions = [
            "lootWindowCloseRung { readingsOpen = %d,"
            " closeControlIsInTheReading = %s, togglePressedRecently = %s }"
            " == %s" % (readings, "True" if close_control else "False",
                        "True" if settled else "False", constructor)
            for constructor in RUNGS]
        answers = self.repl.evaluate(expressions)
        self.assertEqual(
            answers.count(True), 1,
            "the rung answered %d of the four constructors for %d readings"
            % (answers.count(True), readings))
        return RUNGS[answers.index(True)]

    def test_loot_all_comes_first(self):
        # Zero and a fixed value inside the rung as well as its boundary, so a
        # constant that admits everything cannot satisfy the pair.
        for readings in (0, 1, OWN_CONTROLS_READINGS):
            self.assertEqual(self.rung(readings), "UseTheWindowsOwnControls",
                             "the escalation started at %d readings" % readings)

    def test_the_close_control_is_next_and_this_bot_could_never_reach_it(self):
        """The rung the incident never got to.

        `wreckLootWindowsFromReadingFromGameClient` selects a window *by* its
        carrying "Loot All", and the close-button lookup used to sit under a
        `Nothing` branch of a second lookup for that same text on the same node
        -- so the click, and the `askForHelpToGetUnstuck` beneath it, could not
        be reached at all. The mission runner reached the equivalent click and
        recorded it closing a hours-stuck window with no focus step.
        """
        for readings in (OWN_CONTROLS_READINGS + 1, OWN_CONTROLS_READINGS + 2,
                         CLOSE_CONTROL_READINGS):
            self.assertEqual(self.rung(readings), "ClickTheWindowsCloseControl",
                             "the Close control is skipped at %d readings"
                             % readings)

    def test_the_keystroke_comes_after_the_close_control(self):
        self.assertEqual(self.rung(CLOSE_CONTROL_READINGS + 1),
                         "PressTheInventoryToggle")

    def test_a_reading_with_no_close_control_goes_straight_to_the_keystroke(self):
        """The fall-through is the key rather than a wait, so a window whose
        controls the parser cannot find is not a reading spent on nothing."""
        for readings in (OWN_CONTROLS_READINGS + 1, CLOSE_CONTROL_READINGS):
            self.assertEqual(self.rung(readings, close_control=False),
                             "PressTheInventoryToggle",
                             "a window with no Close control waited at %d "
                             "readings" % readings)

    def test_the_escalation_runs_to_the_bound_and_not_past_it(self):
        self.assertEqual(self.rung(GIVE_UP_READINGS),
                         "PressTheInventoryToggle",
                         "the give-up fired a reading early")
        self.assertEqual(self.rung(GIVE_UP_READINGS + 1),
                         "LeaveTheLootWindowAlone",
                         "the branch is still pressing past its own bound")

    def test_the_give_up_holds_however_long_the_window_stays(self):
        """The half that matters: 919 decision lines is what no bound looks
        like. A rule that gave up at the boundary and resumed above it would be
        the ladder wrapping back round, which #109 lists as its own mutation."""
        for readings in (GIVE_UP_READINGS + 2, 301, 10000):
            self.assertEqual(self.rung(readings), "LeaveTheLootWindowAlone",
                             "the branch pressed again at %d readings"
                             % readings)

    def test_the_settling_window_falls_through_to_a_rung_that_acts(self):
        """Alt+C is a toggle, so a press before the client has shown the result
        re-opens what the last press closed -- `moduleButtonClickSettlingSteps`'
        problem at a window. The settle must not become a wait: it answers a
        rung that clicks something."""
        self.assertEqual(self.rung(CLOSE_CONTROL_READINGS + 1, settled=True),
                         "UseTheWindowsOwnControls")
        self.assertEqual(self.rung(GIVE_UP_READINGS, settled=True),
                         "UseTheWindowsOwnControls")
        self.assertEqual(
            self.rung(OWN_CONTROLS_READINGS + 1, close_control=False,
                      settled=True),
            "UseTheWindowsOwnControls")

    def test_the_settle_cannot_revive_the_branch_past_the_bound(self):
        self.assertEqual(self.rung(GIVE_UP_READINGS + 1, settled=True),
                         "LeaveTheLootWindowAlone")
        self.assertEqual(self.rung(1, settled=True), "UseTheWindowsOwnControls")

    def test_the_settle_does_not_displace_the_close_control(self):
        """It is the *keystroke* that is being settled for, so a Close control
        the client is drawing is still clicked on a settling reading."""
        self.assertEqual(self.rung(OWN_CONTROLS_READINGS + 1, settled=True),
                         "ClickTheWindowsCloseControl")


class TheConstantsAreTheOnesTheSourceCarriesTest(unittest.TestCase):
    """Both numbers, read back out of `Bot.elm`, and the give-up's form."""

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def constant(self, name):
        match = re.search(r"^%s : Int\n%s =\n\s+(.+)$" % (name, name),
                          self.source, re.MULTILINE)
        assert match, "no Int constant named %r" % name
        return match.group(1).strip()

    def test_the_own_controls_rung_is_the_trigger_the_branch_always_had(self):
        self.assertEqual(self.constant("lootWindowOwnControlsReadings"),
                         str(OWN_CONTROLS_READINGS))

    def test_both_later_rungs_are_multiples_rather_than_bare_numbers(self):
        """`missionStalledReadingsBeforeAbandoning`'s form, for its reason: the
        argument cannot drift away from the number."""
        self.assertEqual(self.constant("lootWindowCloseControlReadings"),
                         "lootWindowOwnControlsReadings * 3")
        self.assertEqual(self.constant("lootWindowForceCloseGiveUpReadings"),
                         "lootWindowOwnControlsReadings * 8")

    def test_the_rungs_are_in_order_and_none_is_empty(self):
        self.assertLess(OWN_CONTROLS_READINGS, self.value(
            "lootWindowCloseControlReadings"))
        self.assertLess(self.value("lootWindowCloseControlReadings"),
                        self.give_up_value())

    def test_the_bound_leaves_room_for_several_presses(self):
        """A bound of `ownControls + 1` would permit one press and would satisfy
        every boundary pair above, which is the hole four of PR #120's cases
        had. So a fixed value beside the boundary."""
        self.assertGreaterEqual(
            self.give_up_value(), OWN_CONTROLS_READINGS + 5,
            "the escalation gets too few readings to press more than once at "
            "the settling window")

    def give_up_value(self):
        return self.value("lootWindowForceCloseGiveUpReadings")

    def value(self, name):
        """What the source arrives at, whatever the constant is written as."""
        written = self.constant(name).replace(
            "lootWindowOwnControlsReadings",
            self.constant("lootWindowOwnControlsReadings"))
        assert re.fullmatch(r"[\d\s+*]+", written), \
            "%s is no longer arithmetic over the first rung: %r" % (name,
                                                                    written)
        return eval(written)  # noqa: S307 -- checked to be arithmetic just above


class TheChordTest(unittest.TestCase):
    """What is pressed, how it is built, and what no longer is."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LootWindowRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_chord_is_alt_c_in_order(self):
        """Round-tripped rather than described. The modifier is pressed and
        released as its own effect because `cg_input` stamps each posted event
        with the modifiers *this process is holding* -- PR #241's fix -- so a
        chord that assumed the modifier would arrive with the key would arrive
        without it."""
        answers = self.repl.evaluate([
            "pressInventoryToggleEffects == %s" % ALT_C_IN_ORDER,
            "List.head pressInventoryToggleEffects"
            " == Just (EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU)",
            "List.reverse pressInventoryToggleEffects |> List.head"
            " |> (==) (Just (EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU))",
        ])
        self.assertEqual(answers, [True] * 3,
                         "the chord is not Alt held across C and released")

    def test_the_recogniser_takes_alt_c_and_nothing_else(self):
        """Both KeyDowns, so neither the propulsion module's Alt+F1 nor a bare
        C can satisfy it -- `doEffectsDeactivatePropulsionModule`'s arrangement,
        which exists because a plain F1 is a weapon hotkey."""
        answers = self.repl.evaluate([
            "doEffectsPressInventoryToggle pressInventoryToggleEffects",
            "doEffectsPressInventoryToggle %s == False" % ALT_F1,
            "doEffectsPressInventoryToggle %s == False" % BARE_C,
            "doEffectsPressInventoryToggle %s == False" % CTRL_W,
            "doEffectsPressInventoryToggle [] == False",
        ])
        self.assertEqual(answers, [True] * 5)

    def test_the_branch_no_longer_builds_a_ctrl_w(self):
        """The key that needs focus, gone from this app rather than merely
        unreachable.

        Asserted over the code with the comments taken out, because the doc
        comments deliberately go on naming Ctrl+W: what it did and why it could
        not work is the finding, and burying it is how the first measurement
        came to be made twice. `vkey_W` itself stays too -- it is the orbit
        chord.
        """
        code = collapsed(without_comments(self.source))
        self.assertNotIn(
            "EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL , "
            "EffectOnWindow.KeyDown EffectOnWindow.vkey_W", code,
            "the Ctrl+W chord is still built somewhere in this bot")
        self.assertNotIn(
            "Ctrl+W", code,
            "a decision line or a rendered string still promises Ctrl+W")

    def test_the_decision_line_says_which_key_and_why(self):
        branch = let_binding(self.source, "decideActionInAnomaly",
                             "decisionIfNoEnemyToAttack")
        self.assertIn("Alt+C", branch,
                      "the decision line no longer names the key it presses")
        self.assertIn("needs no focus", branch,
                      "the decision line no longer records the mechanism, "
                      "which is the half that went unacted on for a year")


class TheCounterIsDerivedFromTheWindowTest(unittest.TestCase):
    """Folded over whole sessions through the real memory update.

    This is what answers the issue's own question about whether the count should
    be reset on a successful close: it already is, because it is derived from
    the window being in the reading rather than accumulated across windows.
    Asserting that by reading the update would assert the arithmetic; folding it
    asserts the behaviour.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LootWindowRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_session_the_cases_fold_is_the_length_they_think(self):
        answers = self.repl.evaluate(
            ["sessionLength [ ( 4, looting ), ( 1, clear ), ( 2, looting ) ]"
             " == 7"],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True],
                         "a fixture fell out of the fold, so every count below "
                         "is over fewer readings than the case names")

    def test_it_climbs_while_the_window_is_in_the_reading(self):
        answers = self.repl.evaluate(
            ["ticksOver [ ( 1, looting ) ] == 1",
             "ticksOver [ ( 4, looting ) ] == 4",
             "ticksOver [ ( %d, looting ) ] == %d"
             % (GIVE_UP_READINGS + 1, GIVE_UP_READINGS + 1)],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 3)

    def test_a_close_resets_it_and_the_next_wreck_starts_from_the_first_rung(self):
        answers = self.repl.evaluate(
            ["ticksOver [ ( 4, looting ), ( 1, clear ) ] == 0",
             "ticksOver [ ( 4, looting ), ( 1, clear ), ( 2, looting ) ] == 2",
             "peakTicks [ ( 4, looting ), ( 1, clear ), ( 2, looting ) ] == 4"],
            definitions=self.repl.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "the count survives a close, so a run that legitimately loots "
            "several wrecks would escalate at one it had already shut")

    def test_an_inventory_that_is_not_a_wreck_s_loot_window_never_starts_it(self):
        answers = self.repl.evaluate(
            ["ticksOver [ ( 5, plainInventory ) ] == 0",
             "peakTicks [ ( 5, plainInventory ) ] == 0"],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 2)

    def test_the_ladder_reads_the_count_the_bot_really_produced(self):
        """The rung asked about a folded session rather than a written number,
        so the two halves cannot agree on a count neither produces."""
        answers = self.repl.evaluate(
            ["rungAfter False [ ( %d, looting ) ] == UseTheWindowsOwnControls"
             % OWN_CONTROLS_READINGS,
             "rungAfter False [ ( %d, looting ) ] == ClickTheWindowsCloseControl"
             % (OWN_CONTROLS_READINGS + 1),
             "rungAfter False [ ( %d, looting ) ] == PressTheInventoryToggle"
             % (CLOSE_CONTROL_READINGS + 1),
             "rungAfter False [ ( %d, looting ) ] == LeaveTheLootWindowAlone"
             % (GIVE_UP_READINGS + 1),
             # And a close inside the session puts it back on the first rung,
             # which is the whole of "nothing has to be reset on success".
             "rungAfter False [ ( %d, looting ), ( 1, clear ), ( 1, looting ) ]"
             " == UseTheWindowsOwnControls" % (GIVE_UP_READINGS + 1)],
            definitions=self.repl.definitions())
        self.assertEqual(answers, [True] * 5)


class TheGiveUpActsRatherThanWaitsTest(unittest.TestCase):
    """What the bot does on the reading the bound expires, and after it.

    PR #257 shipped green and blocked the bot for 108 minutes because a step on
    a hot path could act forever without progressing; a give-up reached on every
    reading for the rest of a stuck window is exactly that hot path, so what it
    hands back has to act.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.branch = let_binding(self.source, "decideActionInAnomaly",
                                  "decisionIfNoEnemyToAttack")
        self.fallthrough = let_binding(self.source, "decideActionInAnomaly",
                                       "lootAnotherWreckOrLeaveTheGrid")

    def test_the_give_up_hands_the_reading_to_the_wreck_path(self):
        arm = self.branch[self.branch.index("LeaveTheLootWindowAlone ->"):]
        arm = arm[:arm.index("PressTheInventoryToggle ->")]
        self.assertIn(
            "lootAnotherWreckOrLeaveTheGrid", arm,
            "the expired bound does something other than hand the reading on")
        for forbidden in ("waitForProgressInGame", "askForHelpToGetUnstuck",
                          "decideActionForCurrentStep"):
            self.assertNotIn(
                forbidden, arm,
                "the expired bound %r rather than handing the reading on"
                % forbidden)

    def test_it_is_the_same_expression_the_no_window_case_takes(self):
        """One expression rather than two that could disagree about what the
        bot does with a reading it is not spending on the loot window."""
        self.assertEqual(
            self.branch.count("lootAnotherWreckOrLeaveTheGrid"), 2,
            "the give-up and the no-loot-window case no longer share a path")

    def test_what_it_falls_through_to_acts_on_every_reading(self):
        for acting in ("openCargoOnOverviewEntry", "scrollOverviewToReveal",
                       "decisionAfterLootingNotableWrecks"):
            self.assertIn(acting, self.fallthrough,
                          "the wreck path no longer %r" % acting)
        for forbidden in ("waitForProgressInGame", "askForHelpToGetUnstuck"):
            self.assertNotIn(
                forbidden, self.fallthrough,
                "the branch the bound falls through to can now %r, so a stuck "
                "loot window becomes a stuck bot by another route" % forbidden)

    def test_no_rung_of_the_ladder_asks_for_help(self):
        """The `askForHelpToGetUnstuck` that used to sit under the unreachable
        close-button lookup is gone. A bounded ladder that ends in an alarm
        leaves every branch below it exactly as starved -- #109's whole
        argument, and the leaf dispatches nothing besides."""
        self.assertNotIn(
            "askForHelpToGetUnstuck", self.branch,
            "a rung of the loot-window ladder asks for help again")

    def test_the_close_control_is_looked_up_once(self):
        """One lookup, read by the rule and by the arm that clicks it, so the
        two cannot disagree about whether the client is drawing one."""
        self.assertEqual(
            self.branch.count("parseWindowControlsFromWindow"), 1,
            "the close control is looked up more than once in this branch")
        self.assertIn("closeControlIsInTheReading = closeControl /= Nothing",
                      self.branch)

    def test_the_give_up_line_names_the_count_and_the_bound(self):
        arm = self.branch[self.branch.index("LeaveTheLootWindowAlone ->"):]
        arm = arm[:arm.index("PressTheInventoryToggle ->")]
        self.assertIn("lootWindowOpenTicks", arm,
                      "the give-up line no longer says how long it waited")
        self.assertIn("lootWindowForceCloseGiveUpReadings", arm,
                      "the give-up line no longer names the bound it crossed")

    def test_the_settle_reads_the_previous_steps_effects(self):
        """And reads them for the Alt+C chord, so it is the press being settled
        for rather than any keystroke at all."""
        self.assertIn("previousStepsEffects", self.branch)
        self.assertIn("doEffectsPressInventoryToggle", self.branch)
        self.assertIn("moduleButtonClickSettlingSteps", self.branch)


class TheStatusLineSaysSoTest(unittest.TestCase):
    """The decision line goes away on the reading the branch stands aside --
    that is what standing aside means -- so the status line is the only thing
    on a later reading that says a window is still open and is being left
    alone. `describeMessageBoxStandoff`'s mechanism, for its reason.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LootWindowRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def rendered(self, readings, open_window=True):
        return self.repl.strings([
            "describeLootWindowStandoff { readingsOpen = %d,"
            " lootWindowOpen = %s }"
            % (readings, "True" if open_window else "False")])[0]

    def test_a_reading_with_no_loot_window_says_nothing_new(self):
        self.assertEqual(self.rendered(0, open_window=False), "loot 0")

    def test_an_open_window_carries_the_count_against_the_bound(self):
        self.assertEqual(self.rendered(1), "loot 1/%d" % GIVE_UP_READINGS)

    def test_the_close_control_rung_says_so_and_names_its_fall_back(self):
        """The clause is a function of the count and nothing else, so on the
        readings where the rung turns on whether the parser found a control it
        has to name both rather than pick one."""
        self.assertEqual(
            self.rendered(OWN_CONTROLS_READINGS + 1),
            "loot %d/%d (clicking its Close control, or Alt+C if it has none)"
            % (OWN_CONTROLS_READINGS + 1, GIVE_UP_READINGS))

    def test_the_escalation_says_which_key_it_is_pressing(self):
        self.assertEqual(self.rendered(CLOSE_CONTROL_READINGS + 1),
                         "loot %d/%d (pressing Alt+C at it)"
                         % (CLOSE_CONTROL_READINGS + 1, GIVE_UP_READINGS))

    def test_the_give_up_keeps_saying_the_window_is_still_there(self):
        self.assertEqual(self.rendered(GIVE_UP_READINGS + 1),
                         "loot %d/%d (GIVEN UP ON, still open)"
                         % (GIVE_UP_READINGS + 1, GIVE_UP_READINGS))

    def test_the_status_line_reaches_the_clause(self):
        status = declaration(self.source, "statusTextFromState")
        self.assertIn("describeLootWindowStandoff", status,
                      "the clause is written and never printed")

    def test_nothing_decides_on_the_clause(self):
        """It is an instrument. A branch reading a rendered sentence is two
        readers of one verdict that can disagree in words."""
        readers = [name for name in re.findall(
            r"^([a-zA-Z][a-zA-Z0-9_]*) :", self.source, re.MULTILINE)
            if "describeLootWindowStandoff" in declaration(self.source, name)]
        self.assertEqual(sorted(readers),
                         ["describeLootWindowStandoff", "statusTextFromState"],
                         "something other than the status line reads the "
                         "rendered clause")


class TheCorpusTest(unittest.TestCase):
    """What this Mac's recorded runs say, recounted as relations.

    Relations rather than the numbers in the pull request, so a corpus that goes
    on growing cannot turn a true claim red.

    **The glob is `saxrat_*.log` and not `saxrat_run*.log`**, which is not a
    detail: the run the issue was filed on is
    `saxrat_uchat_escalation_2026-08-16.log`, and a reader that only takes the
    numbered runs misses the incident entirely while reporting a clean corpus.
    That happened once while this file was being written.
    """

    STATUS_LOOT = re.compile(r"\| loot (\d+)")
    READ = "RequestToVolatileProcess"
    FORCE = "force it shut"

    @classmethod
    def setUpClass(cls):
        cls.runs = sorted(glob.glob(
            os.path.join(EVE_BOT_LOGS, "saxrat_*.log")))
        if not cls.runs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in %s, so what the local corpus "
                "says about this branch cannot be consulted here"
                % EVE_BOT_LOGS)
        cls.measured = [cls.measure(path) for path in cls.runs]

    @classmethod
    def measure(cls, path):
        """Per run: the force-close stretches, in **readings**, and the peaks
        the `loot N` status clause reached.

        Counted per reading rather than per decision line, which is this repo's
        most expensive recurring mistake -- the status line is reprinted under
        every decision, and the issue's own headline 919 is decision lines
        against roughly 190 readings.
        """
        stretches, current, saw_force = [], 0, False
        peaks, peak, seen = [], 0, None
        force_lines = 0
        with open(path, errors="replace") as handle:
            for line in handle:
                if cls.FORCE in line:
                    saw_force = True
                    force_lines += 1
                match = cls.STATUS_LOOT.search(line)
                if match:
                    value = int(match.group(1))
                    seen = value if seen is None else max(seen, value)
                if cls.READ in line:
                    if saw_force:
                        current += 1
                    else:
                        if current:
                            stretches.append(current)
                        current = 0
                    saw_force = False
                    if seen is not None:
                        if seen == 0:
                            if peak:
                                peaks.append(peak)
                            peak = 0
                        else:
                            peak = max(peak, seen)
                        seen = None
        if current:
            stretches.append(current)
        if peak:
            peaks.append(peak)
        return {"name": os.path.basename(path), "stretches": stretches,
                "peaks": peaks, "force_lines": force_lines}

    def test_a_decision_line_is_not_a_reading(self):
        """The unit, asserted rather than remembered. A run whose force-close
        lines equal the readings it spent there would mean the log had stopped
        reprinting the decision, and every count here would mean something
        else."""
        with_force = [run for run in self.measured if run["stretches"]]
        if not with_force:
            self.skipTest("no recorded run reached the force-close")
        for run in with_force:
            self.assertGreater(
                run["force_lines"], sum(run["stretches"]),
                "%s prints one force-close line per reading, which is not how "
                "this log is written" % run["name"])

    def test_the_bots_own_counter_agrees_with_the_readings_and_not_the_lines(self):
        """Which is what settles the size of the incident.

        The issue counts 919 decision lines and reads them as roughly 190
        readings. The bot's own `lootWindowOpenTicks` is a per-reading counter
        and it is printed in the same log, so the run says how long the window
        was really open without anybody estimating: the counter and the readings
        the branch was decided on agree closely, and both are far below the
        line count.
        """
        worst = max(self.measured,
                    key=lambda run: max(run["stretches"] or [0]))
        if not worst["stretches"]:
            self.skipTest("no recorded run reached the force-close")
        readings = max(worst["stretches"])
        peak = max(worst["peaks"] or [0])
        self.assertGreater(
            worst["force_lines"], readings * 2,
            "%s no longer prints several decision lines per reading, so the "
            "two units cannot be told apart in it" % worst["name"])
        self.assertLessEqual(
            abs(peak - readings), max(2, readings // 20),
            "the bot's own per-reading counter (%d) and the readings the branch "
            "was decided on (%d) disagree in %s, so one of the two is not "
            "measuring what this file thinks"
            % (peak, readings, worst["name"]))

    def test_the_bound_is_placed_in_a_gap_rather_than_cut_through_a_distribution(self):
        """`messageBoxAnswersBeforeEscape`'s standard, on this counter.

        Every recorded stretch is either at or below the rung that closes a
        window, or an order of magnitude past the bound. Nothing lies between,
        so the bound cannot be cutting short a window that was about to shut.
        """
        peaks = [peak for run in self.measured for peak in run["peaks"]]
        if not peaks:
            self.skipTest("no recorded run carries the loot-window clause")
        self.assertTrue(
            any(peak <= OWN_CONTROLS_READINGS for peak in peaks)
            and any(peak > GIVE_UP_READINGS for peak in peaks),
            "the corpus no longer holds both a window that closed and one that "
            "did not, so it cannot place a bound between them")
        between = [peak for peak in peaks
                   if OWN_CONTROLS_READINGS < peak <= GIVE_UP_READINGS]
        self.assertEqual(
            between, [],
            "a recorded loot window sat between the first rung and the bound, "
            "so the bound is now cutting through a distribution rather than "
            "sitting in a gap: %s" % between)

    def test_the_escalation_ran_far_longer_than_the_bound_now_allows(self):
        """The runaway half, and the issue's own episode is in here."""
        stretches = [length for run in self.measured for length in
                     run["stretches"]]
        if not stretches:
            self.skipTest("no recorded run reached the force-close")
        self.assertGreater(
            max(stretches), GIVE_UP_READINGS * 2,
            "no recorded escalation runs long enough to have needed a bound, "
            "which would make this bound's sizing rest on nothing")

    def test_the_bound_sits_under_the_shortest_recorded_runaway(self):
        long_ones = [length for run in self.measured
                     for length in run["stretches"]
                     if length > OWN_CONTROLS_READINGS * 2]
        if not long_ones:
            self.skipTest("no recorded run escalated long enough to bound")
        self.assertLess(
            GIVE_UP_READINGS, min(long_ones),
            "the bound is above the shortest escalation the corpus records, so "
            "it would not have cut one of them short")


class TheMutationsThisFileCatchesTest(unittest.TestCase):
    """Each of these fails a named case. Graded on the process exit code with
    `NO_COLOR=1`, because `unittest -v` colourises verdicts and a grader
    anchored on `^OK`/`^FAIL:` reports every mutation as passing.

    1.  the give-up rung removed, so the branch presses forever again --
        `test_the_give_up_holds_however_long_the_window_stays`;
    2.  the give-up's comparison moved by one in either direction --
        `test_the_escalation_runs_to_the_bound_and_not_past_it`;
    3.  the first rung's comparison moved by one -- `test_loot_all_comes_first`;
    4.  either later rung written as a bare number --
        `test_both_later_rungs_are_multiples_rather_than_bare_numbers`;
    5.  the bound cut so it leaves room for one press --
        `test_the_bound_leaves_room_for_several_presses`;
    6.  the bound raised past the recorded runaways --
        `test_the_bound_sits_under_the_shortest_recorded_runaway`;
    7.  the Close-control rung removed, which is the click this bot could never
        reach put back out of reach --
        `test_the_close_control_is_next_and_this_bot_could_never_reach_it`;
    8.  the Close-control rung's comparison moved by one --
        `test_the_close_control_is_next_and_this_bot_could_never_reach_it` /
        `test_the_keystroke_comes_after_the_close_control`;
    9.  `closeControlIsInTheReading` pinned `True` at the call site, so a window
        with no control reaches an arm that has nothing to click --
        `test_the_close_control_is_looked_up_once`;
    10. the Close rung made to wait when the parser finds no control --
        `test_a_reading_with_no_close_control_goes_straight_to_the_keystroke`;
    11. the keystroke reverted to Ctrl+W -- `test_the_chord_is_alt_c_in_order`,
        `test_the_branch_no_longer_builds_a_ctrl_w`;
    12. the modifier dropped, so a bare `C` is posted and arrives with whatever
        the session was holding -- `test_the_chord_is_alt_c_in_order`,
        `test_the_recogniser_takes_alt_c_and_nothing_else`;
    13. the recogniser weakened to either KeyDown alone, so Alt+F1 or a bare C
        satisfies the settle --
        `test_the_recogniser_takes_alt_c_and_nothing_else`;
    14. the settling window dropped, so a toggle is pressed every reading --
        `test_the_settle_reads_the_previous_steps_effects`;
    15. the settle made to answer the give-up rather than a rung that acts --
        `test_the_settling_window_falls_through_to_a_rung_that_acts`;
    16. the settle allowed to override the give-up --
        `test_the_settle_cannot_revive_the_branch_past_the_bound`;
    17. the settle allowed to displace the Close control --
        `test_the_settle_does_not_displace_the_close_control`;
    18. the expired bound made to raise `askForHelpToGetUnstuck`, which
        dispatches nothing --
        `test_the_give_up_hands_the_reading_to_the_wreck_path`,
        `test_no_rung_of_the_ladder_asks_for_help`;
    19. the expired bound given its own copy of the wreck path --
        `test_it_is_the_same_expression_the_no_window_case_takes`;
    20. the counter accumulated across windows rather than derived from the
        window being in the reading --
        `test_a_close_resets_it_and_the_next_wreck_starts_from_the_first_rung`;
    21. `wreckLootWindowsFromReadingFromGameClient` widened to every inventory
        window, which is Alt+C pressed at a window the branch is not about --
        `test_only_the_window_carrying_loot_all_is_a_wreck_loot_window`;
    22. the status clause dropped from the status line, so a stood-aside window
        is invisible -- `test_the_status_line_reaches_the_clause`;
    23. the status clause dropping the bound or the give-up wording --
        `test_an_open_window_carries_the_count_against_the_bound` /
        `test_the_give_up_keeps_saying_the_window_is_still_there`;
    24. a decision branch made to read the rendered clause --
        `test_nothing_decides_on_the_clause`;
    25. the decision line no longer naming Alt+C or its lack of focus --
        `test_the_decision_line_says_which_key_and_why`;
    26. on this file's own premises, the corpus counted in decision lines
        rather than readings -- `test_a_decision_line_is_not_a_reading` and
        `test_the_bots_own_counter_agrees_with_the_readings_and_not_the_lines`;
    27. and, also on this file's premises, the comment stripper reverted to
        cutting at the first `--`, which truncates every decision line in the
        branch -- `test_the_decision_line_says_which_key_and_why`.
    """

    def test_the_list_is_the_documentation(self):
        self.assertTrue(TheMutationsThisFileCatchesTest.__doc__)


if __name__ == "__main__":
    unittest.main()
