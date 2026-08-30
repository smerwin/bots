"""Tests for the approach arm standing aside from a window it cannot close.

Issue #433. Three of four wingmen in one fleet, all on the same build and all
launched within minutes of each other, ended `GAVE UP after 40 readings` with
the commander 32 to 37 km away and an `InfoWindow` still over the client. The
one that had no stray window approached normally.

**The charge, not the refusal, is the defect.** `approachFleetCommanderStep`
answers `CloseAWindowLeftOverTheClient` on every reading a stray window is
open, and that answer is a member of
`approachFleetCommanderAnswersThatSpendAReading`, so each one costs a reading
of the forty. What the arm actually dispatched on those readings is nothing:
`mouseClickOnUIElement` answers `Err ()` for an element whose visible part is
too small to click -- which is what one window over another produces -- and
`clickUiElementForNavigation` folds that into `Result.withDefault []`. So the
decision line printed a close and the effect list went out empty, forty times,
while the arm made **zero** approach attempts and was then permanently given up
on.

`clickUiElementOrSayItCannotBeClicked`'s own doc comment already names an empty
effect list under a decision line as this repo's signature failure and refuses
it for the manoeuvre arm. What #433 adds is that the budget was spent on it.

**The issue names a different gate, and that one is unreachable.** #433 reads
the empty dispatch as `parseWindowControlsFromWindow` finding no close button.
`windowOpenedOverTheClient` has filtered on a *parseable* close button since
#368, so `strayWindowIsOpen` is true only for windows that have one -- which is
also why the status line was able to name the `InfoWindow` at all, since that
clause reads the same matcher. The window had a close button and this bot could
not click it. `test_the_fixtures_are_what_they_claim` is where that distinction
is executed: all three fixtures below are windows the parser finds a close
button on, and exactly one of them is a button this bot can press.

**The fix halts rather than drains**, which is #427's resolution of #426 rather
than a new shape: a window this bot cannot close will not become closable by
being looked at forty times, so `AWindowThisBotCannotCloseIsOpen` is a distinct
answer, is absent from the spend list, and hands the reading back.

**A distinct answer rather than a condition inside the closing one**, because
`approachFleetCommanderAnswersThatSpendAReading` is the single rule the arm,
the counter and the status clause all ask -- an answer that sometimes spends
and sometimes does not makes that list stop being one rule, which is #102's
defect wearing the shape the list exists to prevent.

**The refusal to click at a guessed point is untouched and is asserted here.**
#321's stray-menu rescue right-clicked a computed location 16,791 times in one
run and created the menu it was clearing. Nothing in the halting branch clicks
anything, and `windowOpenedOverTheClient` still identifies a stray window by
its carrying a close button at all -- the halt is about the button being
unreachable, not about there being no window.

**And the give-up stopped claiming what it had not tried.** It read `GAVE UP
after 40 readings, the double click and the panel's Approach button both` on
every give-up, including the runs where the budget had gone to a window and
neither mechanism had had a turn. `approachFleetCommanderCloseWindowReadings`
is the measurement that sentence now rests on; it is read by the status clause
and by no decision.

The fixtures are built by the **real** `EveOnline.ParseUserInterface` from UI
trees, so what makes a close button unclickable here is what makes one
unclickable live rather than a `Bool` written by hand: one window is occluded
by a `ContextMenu` drawn over it (`pythonObjectTypesKnownToOccludeFollowingElements`,
which is #321's own object type), and one draws a close button too small for
`uiNodeVisibleRegionLargeEnoughForClicking`. The closable control rides beside
both as the case that must still behave exactly as it did.

Confirmed by mutation, eleven of them, run against this file and the three
neighbouring wingman files that pin the same arm. None survived, and the counts
are the cases each killed:

 1. `AWindowThisBotCannotCloseIsOpen` added to
    `approachFleetCommanderAnswersThatSpendAReading`, which is #433 restored --
    **7** cases, among them `test_the_halt_spends_nothing`,
    `test_an_unclosable_window_leaves_the_budget_for_the_approach`,
    `test_the_ask_resumes_when_the_window_goes`, and three in the neighbouring
    files that ask the spend list exhaustively;
 2. the halting clause dropped from the ladder, so an unclosable window answers
    `CloseAWindowLeftOverTheClient` again -- **5**, among them
    `test_a_window_this_bot_cannot_press_halts_the_arm` and
    `test_the_step_ladder_is_as_the_two_changes_left_it`;
 3. `closeButtonThisBotCanPress` reduced to the parse, dropping the
    clickability question -- **5**, among them
    `test_the_fixtures_are_what_they_claim` and
    `test_the_clickability_question_is_the_frameworks_own`;
 4. the halting clause ordered *after* the closing one, which makes it
    unreachable -- **5**, the same set as (2) bar the ladder's own wording;
 5. the halting clause's `0 < askedReadings` guard dropped, so an operator's
    own window halts an arm that has not asked for anything -- **2**, led by
    `test_a_window_open_before_the_ask_is_still_not_this_bots_business`;
 6. the halting branch given a click at the window's own region -- **1**,
    `test_nothing_is_dispatched_at_a_window_this_bot_cannot_close`, which is
    the case that keeps #321's refusal;
 7. `CloseAWindowLeftOverTheClient` dropped from the spend list, which is the
    over-correction -- **8**, the widest of the eleven, led by
    `test_a_closable_window_is_still_closed_and_still_charged`;
 8. the close counter advanced on any spending answer rather than on the close
    -- **2**, `test_the_give_up_counts_only_the_window_readings` and
    `test_the_close_record_is_refilled_by_the_landing`;
 9. the close counter never refilled by the landing, so a window on one grid is
    reported against the next -- **2**, including
    `test_the_refill_is_one_rule_with_two_readers` next door;
10. the give-up's claim made unconditional again -- **1**,
    `test_the_give_up_does_not_claim_mechanisms_it_did_not_reach`;
11. the give-up's claim dropped in *both* directions, so a run where the budget
    really did go to the ask no longer says so -- the same case's other half.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from prerequisites import open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    node, reading_binding)
from test_wingman_landing_refills_the_budget import (  # noqa: E402
    APPROACH_SESSION_READINGS, WINGMAN_BOT_ELM, WingmanRepl, approach_grid,
    collapsed, declaration)

# The type name the three pilots' status lines carried. It is a fixture rather
# than a matcher: `windowOpenedOverTheClient` is structural and names no window
# type, which `test_the_stray_window_reader_names_no_unread_literal` pins in
# the neighbouring file. What it is here is the string the clause has to print.
STRAY_WINDOW_TYPE = "InfoWindow"

# The macOS client's own close icon, which is the path this fork's parser was
# taught after the upstream `eveicon/window/close` matched nothing here.
CLOSE_TEXTURE = "res:/UI/Texture/system_icons/close_16px.png"


def stray_window(close_button_size):
    """A window over the client whose close button the parser can find.

    `parseWindowControlsFromWindow` takes the first descendant whose type name
    contains `WindowControls` and then looks inside it for a sprite whose
    texture path names the close icon, so both halves are the parser's own
    lookup rather than a record shaped by hand.

    Regions are relative to the parent, as the client writes them and as
    `asUITreeNodeWithInheritedOffset` reads them, so the button ends up at
    (878, 194) on a window occupying (600, 190) to (900, 390).

    The button's *size* is the argument because it is one of the two things
    that separate a button this bot can press from one it cannot:
    `uiNodeVisibleRegionLargeEnoughForClicking` wants more than three pixels
    each way of whatever is left after occlusion.
    """
    width, height = close_button_size
    return node(STRAY_WINDOW_TYPE, {}, [
        node("WindowControls", {}, [
            node("Sprite", {"texturePath": CLOSE_TEXTURE},
                 [], region=(18, 0, width, height)),
        ], region=(260, 4, 36, 16)),
    ], region=(600, 190, 300, 200))


def context_menu_over_the_window():
    """A menu drawn over the stray window's whole control strip.

    `ContextMenu` is in `pythonObjectTypesKnownToOccludeFollowingElements`, so
    the parser subtracts its region from every *following* sibling's visible
    region -- which is how a real client hides a close button without moving
    it, and is #321's own object type sitting on top of #433's window.

    Wrapped in a container because the parser collects occluders from each
    sibling's **descendants**, so a bare `ContextMenu` at the top level
    occludes nothing and would leave this fixture quietly identical to the
    pressable one.
    """
    return node("Container", {}, [
        node("ContextMenu", {}, [], region=(0, 0, 300, 60)),
    ], region=(600, 190, 300, 200))


def grid_with(extra):
    """`approach_grid`'s shape with something more on the client.

    The commander stays on the overview at range with no selected-item panel,
    which is what makes the ladder spend its whole budget rather than stopping
    at the double click -- the state #428's four pilots were in.
    """
    return approach_grid(None) + extra


CLOSABLE = grid_with([stray_window((16, 16))])

# Occluded: the same window, with the menu ahead of it in sibling order so the
# parser applies the subtraction, and covering the whole of the control strip.
OCCLUDED = grid_with([
    context_menu_over_the_window(),
    stray_window((16, 16)),
])

# Too small to click: nothing over it, but the button the client drew is two
# pixels each way. Kept beside the occluded one because they reach the same
# refusal by different routes, and a rule that only handled occlusion would
# pass a suite that only tested occlusion.
TINY = grid_with([stray_window((2, 2))])


def budget_of(session):
    return ("(memoryOver defaultBotSettings %s"
            " |> .approachFleetCommanderAskedReadings)" % session)


def close_readings_of(session):
    return ("(memoryOver defaultBotSettings %s"
            " |> .approachFleetCommanderCloseWindowReadings)" % session)


def step(stray_window_is_open, can_be_closed, asked):
    """The shipped rule, asked about one reading."""
    return ("approachFleetCommanderStep { settingIsYes = True"
            ", commanderOnGrid = True"
            ", shipIsWarpingOrJumping = False"
            ", shipIsApproaching = False"
            ", strayWindowIsOpen = %s"
            ", strayWindowCanBeClosed = %s"
            ", panelShowsTheCommander = False"
            ", panelOffersApproach = False"
            ", askedReadings = %s }"
            % (stray_window_is_open, can_be_closed, asked))


class TheFixturesAreRealTest(unittest.TestCase):
    """What the parser makes of each tree, before anything is concluded.

    A fixture that never arrived and a rule that answered nothing are the same
    answer from outside (#174), and here the whole change turns on one of three
    windows being pressable -- so each is asked directly. Without this class a
    suite in which every fixture failed to parse would report the fix working.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("closable", CLOSABLE),
            reading_binding("occluded", OCCLUDED),
            reading_binding("tiny", TINY),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_all_three_are_a_window_over_the_client(self):
        """The matcher answers the same for all three, which is what makes the
        three cases about the button rather than about the window."""
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.andThen windowOpenedOverTheClient) /= Nothing"
                % name
                for name in ("closable", "occluded", "tiny")
            ], definitions=self.definitions),
            [True] * 3)

    def test_the_fixtures_are_what_they_claim(self):
        """The one asymmetry the whole change rests on: the parser finds a
        close button on all three, and this bot can press exactly one of
        them."""
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.andThen windowOpenedOverTheClient"
                " |> Maybe.andThen"
                " EveOnline.ParseUserInterface.parseWindowControlsFromWindow"
                " |> Maybe.andThen .closeButton) /= Nothing" % name
                for name in ("closable", "occluded", "tiny")
            ] + [
                "(%s |> Maybe.andThen windowOpenedOverTheClient"
                " |> Maybe.andThen closeButtonThisBotCanPress) %s Nothing"
                % (name, comparison)
                for name, comparison in (("closable", "/="),
                                         ("occluded", "=="),
                                         ("tiny", "=="))
            ], definitions=self.definitions),
            [True] * 6)

    def test_the_commander_is_on_grid_in_all_three(self):
        """Otherwise the arm answers `NoCommanderOnGrid` and the sessions below
        would separate for a reason that has nothing to do with a window."""
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.andThen fleetCommanderOverviewEntry) /= Nothing"
                % name
                for name in ("closable", "occluded", "tiny")
            ], definitions=self.definitions),
            [True] * 3)


class TheRuleTest(unittest.TestCase):
    """`approachFleetCommanderStep`, asked directly.

    Every case asks the whole answer as an equality rather than asking whether
    some constructor was avoided, so a rule that answered two things at once --
    or a constructor that was renamed out from under a case -- fails rather
    than passing on whichever half the case happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_window_this_bot_cannot_press_halts_the_arm(self):
        """#433's answer, at the first reading it can be reached and deep into
        the budget."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == AWindowThisBotCannotCloseIsOpen"
                % step("True", "False", "1"),
                "%s == AWindowThisBotCannotCloseIsOpen"
                % step("True", "False", "20"),
            ]),
            [True, True])

    def test_a_closable_window_is_still_closed(self):
        """Unchanged, which is half of what makes the change a narrowing rather
        than a removal."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == CloseAWindowLeftOverTheClient"
                % step("True", "True", "1"),
                "%s == CloseAWindowLeftOverTheClient"
                % step("True", "True", "20"),
            ]),
            [True, True])

    def test_a_window_open_before_the_ask_is_still_not_this_bots_business(self):
        """`0 < askedReadings` guards the halt exactly as it guards the close.
        An operator's own window on a healthy session must not stop an arm that
        has not asked for anything -- it would be a permanent, silent decline
        on a bot that was working."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ApproachByDoubleClick" % step("True", "False", "0"),
                "%s == ApproachByDoubleClick" % step("True", "True", "0"),
            ]),
            [True, True])

    def test_the_give_up_is_still_asked_first(self):
        """Past the budget nothing goes on poking at the window and nothing
        stands aside from it either: the ask is over either way."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == GaveUpOnTheApproach"
                % step("True", "False", "approachFleetCommanderAskedReadingsBound"),
                "%s == GaveUpOnTheApproach"
                % step("True", "True", "approachFleetCommanderAskedReadingsBound"),
            ]),
            [True, True])

    def test_the_halt_spends_nothing(self):
        """The whole of #433 in one assertion, beside the answer it was split
        out of so the case cannot pass by both being absent."""
        self.assertEqual(
            self.repl.evaluate([
                "List.member AWindowThisBotCannotCloseIsOpen"
                " approachFleetCommanderAnswersThatSpendAReading",
                "List.member CloseAWindowLeftOverTheClient"
                " approachFleetCommanderAnswersThatSpendAReading",
                "List.length approachFleetCommanderAnswersThatSpendAReading == 5",
            ]),
            [False, True, True])


class TheBudgetSurvivesTheWindowTest(unittest.TestCase):
    """Folded through the real `updateMemoryForNewReadingFromGame`.

    The rule answering correctly is not the claim #433 makes; the claim is
    about what the counter does over a session, and those are two different
    pieces of code on two different schedules until something makes them one.
    `test_a_closable_window_is_still_closed_and_still_charged` is the control
    every other case here turns on -- without it, a bot that had stopped
    counting anything at all would pass the rest.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("closable", CLOSABLE),
            reading_binding("occluded", OCCLUDED),
            reading_binding("tiny", TINY),
            reading_binding("clear", approach_grid(None)),
            reading_binding("warping", approach_grid("Warp Drive Active")),
        ]
        cls.long = APPROACH_SESSION_READINGS
        # One reading of asking with nothing in the way -- which is what puts
        # `0 < askedReadings` -- and then the window for the rest.
        cls.with_occluded = "[ ( 1, clear ), ( %d, occluded ) ]" % cls.long
        cls.with_tiny = "[ ( 1, clear ), ( %d, tiny ) ]" % cls.long
        cls.with_closable = "[ ( 1, clear ), ( %d, closable ) ]" % cls.long
        # The window goes away after a long stretch of it, and the arm has to
        # still be able to ask.
        cls.window_then_clear = (
            "[ ( 1, clear ), ( %d, occluded ), ( 5, clear ) ]" % cls.long)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_sessions_are_as_long_as_they_claim(self):
        """Every reading has to have parsed, since `sessionOf` drops the ones
        that did not and a short session reaches no bound."""
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == %d" % (self.with_occluded, self.long + 1),
                "sessionLength %s == %d" % (self.with_tiny, self.long + 1),
                "sessionLength %s == %d" % (self.with_closable, self.long + 1),
                "sessionLength %s == %d"
                % (self.window_then_clear, self.long + 6),
            ], definitions=self.definitions),
            [True] * 4)

    def test_a_closable_window_is_still_closed_and_still_charged(self):
        """The control, and the behaviour deliberately left alone: the close
        counts against the same budget so a rescue that does not land cannot
        outlive the ask it is rescuing."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == approachFleetCommanderAskedReadingsBound"
                % budget_of(self.with_closable),
                "approachFleetCommanderHasBeenGivenUpOn %s"
                % budget_of(self.with_closable),
            ], definitions=self.definitions),
            [True, True])

    def test_an_unclosable_window_leaves_the_budget_for_the_approach(self):
        """#433. Forty-five readings of a window this bot cannot press, and the
        budget still holds the one reading the ask spent before it appeared --
        by both routes to unpressable, because a fix that handled occlusion and
        not a button drawn too small would pass a suite that tested one."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == 1" % budget_of(self.with_occluded),
                "%s == 1" % budget_of(self.with_tiny),
                "not (approachFleetCommanderHasBeenGivenUpOn %s)"
                % budget_of(self.with_occluded),
                "not (approachFleetCommanderHasBeenGivenUpOn %s)"
                % budget_of(self.with_tiny),
            ], definitions=self.definitions),
            [True] * 4)

    def test_the_ask_resumes_when_the_window_goes(self):
        """What the budget was being kept for. The window stands over the
        client for longer than the whole allowance and the arm still asks on
        the readings after it -- which is the difference between the three
        pilots that never moved and the one that did."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == 6" % budget_of(self.window_then_clear),
                "not (approachFleetCommanderHasBeenGivenUpOn %s)"
                % budget_of(self.window_then_clear),
            ], definitions=self.definitions),
            [True, True])

    def test_the_give_up_counts_only_the_window_readings(self):
        """The record the give-up sentence rests on: every reading the close
        was dispatched on and none of the readings the ask spent on itself."""
        self.assertEqual(
            self.repl.evaluate([
                # One clear reading asking, then closing until the shipped
                # bound ends the ask -- so the two counters account for the
                # same forty readings between them, which is what makes the
                # give-up's arithmetic mean anything.
                "%s == approachFleetCommanderAskedReadingsBound - 1"
                % close_readings_of(self.with_closable),
                # A window nothing was dispatched at buys no entry either.
                "%s == 0" % close_readings_of(self.with_occluded),
                "%s == 0" % close_readings_of(self.with_tiny),
            ], definitions=self.definitions),
            [True] * 3)

    def test_the_close_record_is_refilled_by_the_landing(self):
        """It is refilled by the same warp that refills the budget it
        describes, so a window that ate one grid's readings is not still being
        reported against the next grid's ask -- #428's own asymmetry, applied
        to the counter #433 adds."""
        session = ("[ ( 1, clear ), ( 10, closable ), ( 1, warping )"
                   ", ( 1, clear ) ]")
        self.assertEqual(
            self.repl.evaluate([
                "sessionLength %s == 13" % session,
                "%s == 0" % close_readings_of(session),
                "%s == 1" % budget_of(session),
            ], definitions=self.definitions),
            [True] * 3)


class TheStatusLineIsHonestTest(unittest.TestCase):
    """What an operator reads, rendered rather than asserted by substring.

    `describeApproachFleetCommanderAsk` takes a whole `BotDecisionContext`, so
    the give-up's *wording* is executed through `describeApproachGiveUp` -- the
    rendering split out of it -- while the clause that reaches that wording is
    read out of the source beside it. Asserting a sentence over the whole
    branch is how a case written to catch a press aimed at the wrong button
    once passed on the branch's own log text (#145).
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_give_up_does_not_claim_mechanisms_it_did_not_reach(self):
        """Both directions. A give-up whose budget went to the ask still says
        so, because a clause that simply said less would leave the next
        operator with the diagnostic gap that made this take an issue."""
        answers = self.repl.strings([
            "describeApproachGiveUp { askedReadings = 40"
            ", closeWindowReadings = 0 }",
            "describeApproachGiveUp { askedReadings = 40"
            ", closeWindowReadings = 39 }",
        ])
        spent_on_the_ask, spent_on_a_window = answers
        self.assertIn("the double click and the panel's Approach button both",
                      spent_on_the_ask)
        self.assertNotIn(
            "the double click and the panel's Approach button both",
            spent_on_a_window)
        self.assertIn("39", spent_on_a_window)
        self.assertIn("closing a window over the client", spent_on_a_window)
        for answer in answers:
            self.assertIn("GAVE UP after 40 readings", answer)

    def test_the_standing_aside_clause_names_the_window(self):
        """A `Nothing` carries no decision line, so this clause is the only
        thing on a reading that says why the arm is quiet -- run 10 on the
        mission runner is what an unreported decline costs."""
        clause = collapsed(declaration(
            self.source, "describeApproachFleetCommanderAsk context ="))
        opening = clause.index("AWindowThisBotCannotCloseIsOpen ->")
        rest = clause[opening:]
        self.assertIn("strayWindowName", rest[:rest.index("ApproachByDoubleClick")])

    def test_the_give_up_rendering_is_read_by_the_clause(self):
        """One wording with one reader, so the sentence a case executes is the
        sentence an operator gets."""
        clause = declaration(
            self.source, "describeApproachFleetCommanderAsk context =")
        self.assertIn("describeApproachGiveUp", clause)


class NothingIsClickedAtAGuessedPointTest(unittest.TestCase):
    """#321's refusal, which this change must not weaken.

    A stray-menu rescue right-clicked a computed location 16,791 times in one
    run and created the menu it was clearing. The temptation the halt creates
    is to reach for the window's own region instead of its close button, and
    that is the one repair that would be worse than the defect.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_nothing_is_dispatched_at_a_window_this_bot_cannot_close(self):
        arm = declaration(
            self.source, "approachTheFleetCommander context shipUI =")
        start = arm.index("AWindowThisBotCannotCloseIsOpen ->")
        branch = arm[start:arm.index("CloseAWindowLeftOverTheClient ->", start)]
        self.assertNotIn("clickUiElement", branch)
        self.assertNotIn("effectsMouseClickAtLocation", branch)
        self.assertNotIn("useContextMenuCascade", branch)
        self.assertIn("Nothing", branch)

    def test_the_close_is_still_the_windows_own_close_button(self):
        arm = declaration(
            self.source, "approachTheFleetCommander context shipUI =")
        start = arm.index("CloseAWindowLeftOverTheClient ->")
        branch = arm[start:arm.index("ApproachByDoubleClick ->", start)]
        self.assertIn("closeButtonThisBotCanPress", branch)
        self.assertIn("clickUiElementForNavigation closeButton", branch)
        self.assertNotIn("effectsMouseClickAtLocation", branch)

    def test_the_matcher_still_requires_a_close_button_to_identify_a_window(
            self):
        """The halt is about a button that cannot be pressed, not about a node
        with nothing to close it by. Widening `windowOpenedOverTheClient` to
        any `...Window` would make an inert layout node halt the arm
        permanently, which is worse than what #433 reports."""
        matcher = declaration(
            self.source, "windowOpenedOverTheClient readingFromGameClient =")
        self.assertIn("closeButton", matcher)
        self.assertIn('String.endsWith "Window"', matcher)

    def test_the_clickability_question_is_the_frameworks_own(self):
        """Asked through `mouseClickOnUIElement` rather than restating
        `uiNodeVisibleRegionLargeEnoughForClicking` beside the dispatch: two
        spellings of one question is two opinions that can drift, and the click
        site is the thing that has to succeed."""
        helper = declaration(
            self.source, "closeButtonThisBotCanPress strayWindow =")
        self.assertIn("mouseClickOnUIElement", helper)
        self.assertNotIn("uiNodeVisibleRegionLargeEnoughForClicking", helper)


class NoSiblingArmSharesTheDefectTest(unittest.TestCase):
    """The scope claim, checked rather than taken on trust.

    #433 is confined to the approach arm only if no other arm charges a reading
    for a window-closing answer. Asked over every `*AnswersThatSpendAReading`
    list in the file, so an arm that grows one later has to notice.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_approach_arm_is_the_only_one_that_closes_windows(self):
        others = [name for name in (
            "middleRowAnswersThatSpendAReading",
            "deactivateForWarpAnswersThatSpendAReading",
            "backupCallAnswersThatSpendAReading",
            "retreatRecoveryAnswersThatSpendAReading",
            "weaponsAnswersThatSpendAReading",
        )]
        for name in others:
            with self.subTest(list=name):
                body = declaration(self.source, "%s =" % name)
                self.assertNotIn("Window", body)
                self.assertNotIn("Close", body)

    def test_every_spending_list_the_file_has_is_covered(self):
        """A list added since this case was written is one nobody asked the
        question of, so the count is asserted rather than the names."""
        names = set()
        for line in self.source.split("\n"):
            if line.startswith("ansAnswersThatSpendAReading"):
                continue
            if "AnswersThatSpendAReading :" in line and not line.startswith(" "):
                names.add(line.split(" :")[0])
        self.assertEqual(len(names), 6, sorted(names))
        self.assertIn("approachFleetCommanderAnswersThatSpendAReading", names)

    def test_the_only_window_closing_answer_is_the_approachs(self):
        """Executed rather than read: the approach arm's list really does hold
        it, so the source reads above are about absence in the others rather
        than about a string nothing carries."""
        self.assertEqual(
            self.repl.evaluate([
                "List.member CloseAWindowLeftOverTheClient"
                " approachFleetCommanderAnswersThatSpendAReading",
            ]),
            [True])


if __name__ == "__main__":
    unittest.main()
