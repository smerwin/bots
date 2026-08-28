"""Tests for #414: the manoeuvre and unlock arms driving the Selected Item panel.

Every one of those arms computed a screen position from a reading and then acted
on it -- a double click for saxrat's approach, a `W`-chord for both bots' orbit,
an `E`-chord for saxrat's keep-at-range, a Ctrl+Shift+Click or a right-click
cascade for the unlock. The overview and the target bar are both reordered by the
client between one reading and the next, so with two identically named rats the
gesture lands on the neighbour and commands the manoeuvre on it. That is #413.

**The panel acts on the selected object rather than on a position.** So the
command half of that exposure is gone: the button sits in the panel and is found
by name in the same reading it is pressed in. What remains is the selection
click, and the difference is that the panel then *names* what was selected, so
`selectedItemIsOverviewEntry` catches a click that went astray before the
manoeuvre is commanded, where the gesture it replaces commanded immediately.

Four constraints from #414's own five live readings, and each has cases below:

  - **match by `_elementId` in the current reading, never by index or a
    remembered position.** `selectedItemOrbit` was seen at x=1515 and at x=1551
    as neighbours came and went. `cmdName` is matched as well, as a second
    independent identifier;
  - **absence is normal, not an error.** The button set is contextual -- a
    station offers Dock and Align To, a gate offers Jump and Approach, a rat
    offers Approach -- so a reading whose panel shows the row and offers no
    button hands the reading back to the fight rather than retrying it;
  - **the greyed-out state is not readable.** Every button in all five readings
    carried `isDisabled = None` and full opacity, so success is confirmed from
    `ShipManeuverType` and never from having pressed;
  - **`selectedItemUnLockTarget` has a capital `L` its Lock sibling does not**,
    and a guessed lower-case spelling matches nothing while "no button" is
    indistinguishable from "nothing to unlock".

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the panels they are asked about go through the real
`EveOnline.ParseUserInterface` -- which is also what makes these cases evidence
that both apps' vendored copies of that parser expose the selected-item window
the press needs. The wiring, which is not an expression, is read out of the
source through a whitespace-collapsing reader so an `elm-format` pass cannot
break it.

Confirmed by mutation, each failing a named case:

  - **a button matched by index or by position** rather than by name, which is
    the one thing #414 says nothing may be optimised into;
  - **`selectedItemUnLockTarget` spelled with a lower-case `l`**, which matches
    nothing and reads exactly like an object that is not locked;
  - **absence treated as a failure to retry** -- `WaitForThePanelButton`
    answering `SelectTheRowFirst`, so the arm clicks the row again at a panel
    that is already showing it;
  - **success inferred from the press**, the manoeuvre clause dropped from the
    step rule so a pressed button ends the ask;
  - the `cmdName` half of the match dropped;
  - the selection bound removed, so a panel that never shows the row is clicked
    forever while the guns never fire;
  - the bound's comparison moved either way;
  - the give-up made to wait rather than hand the reading back;
  - the press aimed at the row instead of at the button;
  - a chord or a double click put back into a manoeuvre arm.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, elm_json_literal, open_repl
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, body_of, collapsed,
    label, node, overview, source_of, tree_with)

WINGMAN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")


# The three manoeuvre buttons and the unlock, exactly as #414 read them off the
# live client. Written here rather than imported from the source, so that a
# `Bot.elm` whose constant drifted is a disagreement rather than a shared
# mistake -- the same arrangement `test_typed_text_key_sequence` uses for the
# key table.
LIVE_PANEL_BUTTONS = {
    "selectedItemApproach": "CmdApproachItem",
    "selectedItemOrbit": "CmdOrbitItem",
    "selectedItemKeepAtRange": "CmdKeepItemAtRange",
    "selectedItemUnLockTarget": "CmdUnlockTargetItem",
}

# The spelling a guess produces, and the one the client does not write.
GUESSED_UNLOCK_NAME = "selectedItemUnlockTarget"

RAT_NAME = "Centum Ravisher"


def panel(buttons, showing=RAT_NAME):
    """The Selected Item panel, as either app's real parser will accept it.

    `parseSelectedItemWindowFromUITreeRoot` matches the window on its type name
    -- the macOS client calls it `SelectedItemWnd` -- and everything read off it
    afterwards is a descendant: the name it is showing as display text, and each
    button by its own identifiers.

    `buttons` is a list of `(elementId, cmdName)`, either of which may be
    `None`, so a case can build the button the client draws (both), one the
    client draws with only an id, and a neighbour that carries a `cmdName` this
    bot does not want.
    """
    children = [label(showing, (0, 0, 200, 16))]
    for index, (element_id, cmd_name) in enumerate(buttons):
        entries = {}
        if element_id is not None:
            entries["_name"] = element_id
            entries["_elementId"] = element_id
        if cmd_name is not None:
            entries["cmdName"] = cmd_name
        children.append(
            node("SelectedItemButton", entries,
                 region=(1443 + index * 36, 700, 32, 32)))
    return node("SelectedItemWnd", {}, children, region=(1400, 690, 400, 60))


def named(element_id):
    return (element_id, LIVE_PANEL_BUTTONS[element_id])


class PanelRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, with no extra preamble."""


class WingmanPanelRepl(ElmRepl):
    """The same harness pointed at the wingman."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-panel-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    @staticmethod
    def reading_binding(name, children):
        return SaxratRepl.reading_binding(name, children)


APPS = (("saxrat", PanelRepl, SAXRAT_BOT_ELM),
        ("wingman", WingmanPanelRepl, WINGMAN_BOT_ELM))


class TheStepRuleTest(unittest.TestCase):
    """`panelManoeuvreStep`, executed at each of its five answers, in both apps.

    Asked as five equalities per case rather than one, so a rule that answered
    two things at once -- or none -- fails rather than passing on whichever
    constructor a case happened to name.
    """

    STEPS = ("ManoeuvreIsAlreadyRunning", "SelectTheRowFirst",
             "PressThePanelButton", "WaitForThePanelButton",
             "GaveUpOnSelectingTheRow")

    @classmethod
    def setUpClass(cls):
        cls.repls = {name: open_repl(repl_class)
                     for name, repl_class, _ in APPS}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def step(self, repl, running, shows, offers, unanswered):
        expression = (
            "panelManoeuvreStep { manoeuvreIsRunning = %s"
            ", panelShowsTheRow = %s, panelOffersTheButton = %s"
            ", selectionUnansweredReadings = %d }" % (
                "True" if running else "False",
                "True" if shows else "False",
                "True" if offers else "False", unanswered))
        answers = repl.evaluate(
            ["(%s) == %s" % (expression, step) for step in self.STEPS])
        chosen = [step for step, yes in zip(self.STEPS, answers) if yes]
        self.assertEqual(
            len(chosen), 1,
            "expected exactly one step for %s, got %s" % (expression, chosen))
        return chosen[0]

    def test_the_client_naming_the_manoeuvre_is_what_stops_the_ask(self):
        """Success is the client's own word, never having pressed.

        The greyed-out state is not readable at all, so a press that landed on a
        dimmed button and a press that worked are the same reading -- and this
        is what makes the difference between them cost one reading rather than
        the whole engagement.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                for shows in (True, False):
                    for offers in (True, False):
                        self.assertEqual(
                            self.step(repl, True, shows, offers, 0),
                            "ManoeuvreIsAlreadyRunning")

    def test_a_panel_showing_something_else_is_selected_first(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertEqual(
                    self.step(repl, False, False, False, 0), "SelectTheRowFirst")
                # Even where the button happens to be drawn: the panel is
                # showing another object, so pressing it would act on that one.
                self.assertEqual(
                    self.step(repl, False, False, True, 0), "SelectTheRowFirst")

    def test_the_button_is_pressed_once_the_panel_shows_the_row(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertEqual(
                    self.step(repl, False, True, True, 0), "PressThePanelButton")

    def test_an_absent_button_is_not_retried_as_a_selection(self):
        """Absence is normal: it can simply mean the ship is in warp.

        The mutation this kills is `WaitForThePanelButton` answering
        `SelectTheRowFirst`, which clicks the row again at a panel that is
        already showing it -- a retry of something that did not fail.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertEqual(
                    self.step(repl, False, True, False, 0),
                    "WaitForThePanelButton")
                # And it is not the give-up either, however long the selection
                # has been unanswered: the selection is not what failed here.
                self.assertEqual(
                    self.step(repl, False, True, False, 1000),
                    "WaitForThePanelButton")

    def test_the_selection_is_bounded_at_the_constant_and_not_before(self):
        """Both sides of the bound, and a fixed value either side of it.

        A case that asks only about `constant - 1` and `constant` passes for any
        constant, including one that admits everything -- the hole four of
        #120's own cases had.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                bound = int(repl.values(
                    ["panelSelectGiveUpReadings"], r"(-?\d+) : Int")[0])
                self.assertGreater(bound, 3, "a bound of %d is small enough "
                                   "that an ordinary two-reading selection "
                                   "could reach it" % bound)
                self.assertLess(bound, 200, "a bound of %d spends more of a "
                                "fight on one selection than the fight has" %
                                bound)
                self.assertEqual(
                    self.step(repl, False, False, False, bound - 1),
                    "SelectTheRowFirst")
                self.assertEqual(
                    self.step(repl, False, False, False, bound),
                    "GaveUpOnSelectingTheRow")
                self.assertEqual(
                    self.step(repl, False, False, False, 3),
                    "SelectTheRowFirst")
                self.assertEqual(
                    self.step(repl, False, False, False, 500),
                    "GaveUpOnSelectingTheRow")


class TheCounterTest(unittest.TestCase):
    """`panelSelectReadingsAfterReading`, folded over a session.

    A counter that is right for one reading and wrong across a session is the
    defect this shape prevents, so it is folded rather than asked once.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = {name: open_repl(repl_class)
                     for name, repl_class, _ in APPS}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def fold(self, repl, askings):
        expression = (
            "List.foldl (\\asking before -> panelSelectReadingsAfterReading "
            "{ asking = asking, before = before }) 0 [ %s ]" % ", ".join(
                "True" if asking else "False" for asking in askings))
        return int(repl.values([expression], r"(-?\d+) : Int")[0])

    def test_it_counts_the_readings_that_were_asking(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertEqual(self.fold(repl, []), 0)
                self.assertEqual(self.fold(repl, [True]), 1)
                self.assertEqual(self.fold(repl, [True] * 7), 7)

    def test_a_reading_that_was_not_asking_clears_it(self):
        """The panel coming to show the row is the ask being answered.

        It also clears on a reading with nothing to manoeuvre on at all, which
        is not the ship failing to select something.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertEqual(self.fold(repl, [True] * 9 + [False]), 0)
                self.assertEqual(
                    self.fold(repl, [True] * 9 + [False] + [True] * 2), 2)


class TheButtonIsFoundByNameAndNeverByPositionTest(unittest.TestCase):
    """`selectedItemPanelButton`, over panels the real parser produced.

    `selectedItemOrbit` was read live at x=1515 in one reading and x=1551 in
    another moments later, because two buttons left the row and everything
    shifted. So the same button is asked for in two panels whose *orders*
    differ, and the answer has to be the same button both times.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = {name: open_repl(repl_class)
                     for name, repl_class, _ in APPS}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def found(self, repl, binding, constant):
        """Whether the named panel button is found in the named reading."""
        return repl.evaluate(
            ["(%s |> Maybe.map (\\r -> selectedItemPanelButton r %s /= Nothing))"
             " == Just True" % (binding, constant)],
            definitions=self.definitions)[0]

    def x_of(self, repl, binding, constant):
        return int(repl.values(
            ["%s |> Maybe.andThen (\\r -> selectedItemPanelButton r %s)"
             " |> Maybe.map (.totalDisplayRegion >> .x) "
             "|> Maybe.withDefault (-1)" % (binding, constant)],
            r"(-?\d+) : Int", definitions=self.definitions)[0])

    def setUp(self):
        # Two live-shaped panels. The first is #414's fourth reading, a rat
        # selected on grid; the second is its first, where Approach is absent
        # and Align To and Dock have pushed Orbit two slots along.
        rat_panel = panel([
            named("selectedItemApproach"),
            ("selectedItemWarpTo", None),
            named("selectedItemOrbit"),
            named("selectedItemKeepAtRange"),
            ("selectedItemLockTarget", "CmdLockTargetItem"),
            ("selectedItemLookAt", "CmdToggleLookAtItem"),
        ])
        shifted_panel = panel([
            ("selectedItemAlignTo", "CmdAlignToItem"),
            ("selectedItemWarpTo", None),
            ("selectedItemDock", "CmdDockOrJumpOrActivateGate"),
            named("selectedItemOrbit"),
            named("selectedItemKeepAtRange"),
            ("selectedItemLockTarget", "CmdLockTargetItem"),
        ])
        locked_panel = panel([
            named("selectedItemApproach"),
            named("selectedItemOrbit"),
            named("selectedItemUnLockTarget"),
        ])
        # A button the client draws with a `cmdName` and no id this bot knows,
        # which is the half `cmdName` is matched for.
        renamed_panel = panel([
            ("selectedItemAlignTo", "CmdAlignToItem"),
            ("someRenamedOrbitButton", "CmdOrbitItem"),
        ])
        repl = next(iter(self.repls.values()))
        self.definitions = [
            repl.reading_binding("ratPanel", [overview([]), rat_panel]),
            repl.reading_binding("shiftedPanel", [overview([]), shifted_panel]),
            repl.reading_binding("lockedPanel", [overview([]), locked_panel]),
            repl.reading_binding("renamedPanel", [overview([]), renamed_panel]),
        ]

    def test_the_fixtures_are_panels_the_parser_really_read(self):
        """Asked before anything is concluded from them.

        A case built on a tree the parser silently makes nothing of would pass
        or fail for reasons that have nothing to do with the rule under test.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertTrue(all(repl.evaluate(
                    ["(%s |> Maybe.map (.selectedItemWindow >> (/=) Nothing))"
                     " == Just True" % binding
                     for binding in ("ratPanel", "shiftedPanel", "lockedPanel",
                                     "renamedPanel")],
                    definitions=self.definitions)))

    def test_the_same_button_is_found_wherever_the_client_draws_it(self):
        """The mutation this kills is a lookup by index or by position.

        Orbit is the third button in one panel and the fourth in the other, and
        the x it is drawn at differs by 36 points -- so a rule that took "the
        button at index 2", or remembered where it was last reading, answers a
        different command here.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertTrue(
                    self.found(repl, "ratPanel", "selectedItemOrbitButton"))
                self.assertTrue(
                    self.found(repl, "shiftedPanel", "selectedItemOrbitButton"))
                self.assertNotEqual(
                    self.x_of(repl, "ratPanel", "selectedItemOrbitButton"),
                    self.x_of(repl, "shiftedPanel", "selectedItemOrbitButton"),
                    "the two fixtures draw Orbit at the same x, so this case "
                    "would not notice a lookup by position")

    def test_cmd_name_is_a_second_independent_identifier(self):
        """A rename of the id alone still finds the button.

        Cheap insurance on a widget name, which is the class of thing that has
        cost this repo several sessions.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertTrue(
                    self.found(repl, "renamedPanel", "selectedItemOrbitButton"))

    def test_a_panel_that_does_not_offer_it_answers_nothing(self):
        """Absence is a normal answer, and it has to be answerable as one."""
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertFalse(
                    self.found(repl, "renamedPanel",
                               "selectedItemUnLockTargetButton"))
                self.assertFalse(
                    self.found(repl, "shiftedPanel",
                               "selectedItemUnLockTargetButton"))

    def test_the_unlock_is_spelled_with_the_capital_l_the_client_writes(self):
        """`selectedItemUnLockTarget`, and not the guess.

        The panel drawing the real name is asked for the guessed one, and the
        answer has to be nothing -- which is the whole hazard: "no button" and
        "nothing to unlock" are the same answer here, so the guess would have
        failed silently in a guard whose job is not to.
        """
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                self.assertTrue(
                    self.found(repl, "lockedPanel",
                               "selectedItemUnLockTargetButton"))
                self.assertFalse(repl.evaluate(
                    ["(lockedPanel |> Maybe.map (\\r -> selectedItemPanelButton"
                     " r { elementId = \"%s\", cmdName = \"NotACommand\" }"
                     " /= Nothing)) == Just True" % GUESSED_UNLOCK_NAME],
                    definitions=self.definitions)[0])


class TheNamesAreTheOnesReadOffTheClientTest(unittest.TestCase):
    """The four constants, against the table #414 measured.

    Written out in this file rather than imported from `Bot.elm`, so a constant
    that drifted is a disagreement between two independently written spellings
    rather than a shared mistake.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = {name: open_repl(repl_class)
                     for name, repl_class, _ in APPS}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    CONSTANTS = {
        "saxrat": ("selectedItemApproachButton", "selectedItemOrbitButton",
                   "selectedItemKeepAtRangeButton",
                   "selectedItemUnLockTargetButton"),
        "wingman": ("selectedItemOrbitButton", "selectedItemUnLockTargetButton"),
    }

    def test_each_constant_carries_both_identifiers(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                for constant in self.CONSTANTS[name]:
                    element_id, cmd_name = repl.strings(
                        ["%s.elementId" % constant, "%s.cmdName" % constant])
                    self.assertIn(element_id, LIVE_PANEL_BUTTONS,
                                  "%s names an id the live readings do not" %
                                  constant)
                    self.assertEqual(
                        cmd_name, LIVE_PANEL_BUTTONS[element_id],
                        "%s pairs %r with a cmdName the client does not write"
                        % (constant, element_id))

    def test_the_unlock_is_not_the_lock_with_a_prefix(self):
        """The asymmetry a guessed name gets wrong, pinned in both apps."""
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                element_id = repl.strings(
                    ["selectedItemUnLockTargetButton.elementId"])[0]
                self.assertEqual(element_id, "selectedItemUnLockTarget")
                self.assertNotEqual(element_id, GUESSED_UNLOCK_NAME)


class TheArmsAreWiredToThePanelTest(unittest.TestCase):
    """What the source has to say, which is not an expression.

    Read through a whitespace-collapsing reader so the next `elm-format` pass
    cannot break an assertion the way #58's broke three others.
    """

    def bodies(self, app, names):
        source = source_of(SAXRAT_BOT_ELM if app == "saxrat"
                           else WINGMAN_BOT_ELM)
        return {name: collapsed(body_of(source, name)) for name in names}

    def test_every_manoeuvre_arm_goes_through_the_shared_shape(self):
        for name, arms in (("saxrat", ("ensureShipIsApproaching",
                                       "ensureShipIsOrbiting",
                                       "ensureShipIsKeepingRange")),
                           ("wingman", ("ensureShipIsOrbiting",))):
            with self.subTest(app=name):
                for arm, body in self.bodies(name, arms).items():
                    self.assertIn(
                        "commandManoeuvreFromSelectedItemPanel", body,
                        "%s in %s no longer drives the panel" % (arm, name))

    def test_no_manoeuvre_arm_presses_a_key_or_double_clicks_a_row(self):
        """The chords and the double click are gone, and stay gone.

        `vkey_W` and `vkey_E` were the last two modifier chords on either bot's
        hot path, and a posted key carries whatever modifier state the session
        holds -- which is what #387 and saxrat's #243 removed the approach's `Q`
        for.
        """
        for name, arms in (("saxrat", ("ensureShipIsApproaching",
                                       "ensureShipIsOrbiting",
                                       "ensureShipIsKeepingRange",
                                       "commandManoeuvreFromSelectedItemPanel")),
                           ("wingman", ("ensureShipIsOrbiting",
                                        "commandManoeuvreFromSelectedItemPanel"))):
            with self.subTest(app=name):
                for arm, body in self.bodies(name, arms).items():
                    for forbidden in ("vkey_W", "vkey_E", "vkey_Q",
                                      "doubleClickUiElement",
                                      "mouseDoubleClickOnUIElement"):
                        self.assertNotIn(
                            forbidden, body,
                            "%s in %s is back to %s" % (arm, name, forbidden))

    def test_the_shared_shape_presses_the_button_and_selects_the_row(self):
        """The press is aimed at the panel's node, the selection at the row's.

        The mutation this kills is the press aimed at `overviewEntry.uiNode`,
        which is the position-based click the whole change removes -- and which
        would go on printing the same decision line.
        """
        for name, _, _ in APPS:
            with self.subTest(app=name):
                body = self.bodies(
                    name, ("commandManoeuvreFromSelectedItemPanel",))[
                        "commandManoeuvreFromSelectedItemPanel"]
                press = body.split("PressThePanelButton ->")[1]
                press = press.split("WaitForThePanelButton ->")[0]
                self.assertIn("buttonNode", press)
                self.assertNotIn("overviewEntry.uiNode", press)
                select = body.split("SelectTheRowFirst ->")[1]
                select = select.split("PressThePanelButton ->")[0]
                self.assertIn("overviewEntry.uiNode", select)

    def test_absence_and_the_give_up_both_hand_the_reading_back(self):
        """Neither dispatches and neither waits.

        A wait here holds the fight for a button that may simply not belong to
        this object, which is what "absence is not a failure" has to mean in the
        code rather than in a comment.
        """
        for name, _, _ in APPS:
            with self.subTest(app=name):
                body = self.bodies(
                    name, ("commandManoeuvreFromSelectedItemPanel",))[
                        "commandManoeuvreFromSelectedItemPanel"]
                tail = body.split("WaitForThePanelButton ->")[1]
                self.assertNotIn("describeBranch", tail)
                self.assertNotIn("waitForProgressInGame", tail)
                self.assertEqual(tail.count("Nothing"), 2, tail)

    def test_the_counter_is_advanced_from_the_reading_alone(self):
        """One rule, asked by the memory update and by the arm's own bound.

        A counter advanced by one condition and read by another is #102's
        defect, and it is the reason the predicate is a function of the reading
        rather than of a decision.
        """
        for name, predicate in (
                ("saxrat", "askingThePanelToShowTheActiveTarget"),
                ("wingman", "askingThePanelToShowTheObjectToOrbit")):
            with self.subTest(app=name):
                source = collapsed(source_of(
                    SAXRAT_BOT_ELM if name == "saxrat" else WINGMAN_BOT_ELM))
                self.assertIn("panelSelectReadingsAfterReading { asking = %s"
                              % predicate, source.replace("\n", " "))
                body = self.bodies(name, (predicate,))[predicate]
                self.assertNotIn("BotDecisionContext", body)

    def test_the_status_line_says_what_the_selection_is_doing(self):
        """The only thing on a reading that reports this at all.

        `WaitForThePanelButton` and `GaveUpOnSelectingTheRow` both answer
        `Nothing`, which cannot carry a decision line -- so without the clause a
        panel that never offers the button and a manoeuvre running happily print
        identically.
        """
        for name, _, _ in APPS:
            with self.subTest(app=name):
                source = collapsed(source_of(
                    SAXRAT_BOT_ELM if name == "saxrat" else WINGMAN_BOT_ELM))
                self.assertIn("describePanelManoeuvreSelection", source)


class TheStatusClauseTest(unittest.TestCase):
    """`describePanelManoeuvreSelection`, rendered rather than asserted about.

    Asserting a substring over the status line is how a clause that printed
    nothing at all passed #109's own file once.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = {name: open_repl(repl_class)
                     for name, repl_class, _ in APPS}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def clause(self, repl, asking, unanswered):
        return repl.strings(
            ["describePanelManoeuvreSelection { asking = %s"
             ", unansweredReadings = %d }" % (
                 "True" if asking else "False", unanswered)])[0]

    def test_it_carries_the_count_against_the_bound(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                bound = int(repl.values(
                    ["panelSelectGiveUpReadings"], r"(-?\d+) : Int")[0])
                self.assertIn("3/%d" % bound, self.clause(repl, True, 3))

    def test_it_separates_asking_from_quiet_from_given_up(self):
        for name, repl in self.repls.items():
            with self.subTest(app=name):
                bound = int(repl.values(
                    ["panelSelectGiveUpReadings"], r"(-?\d+) : Int")[0])
                quiet = self.clause(repl, False, 0)
                asking = self.clause(repl, True, 2)
                given_up = self.clause(repl, True, bound)
                self.assertNotEqual(quiet, asking)
                self.assertNotEqual(asking, given_up)
                self.assertIn("GIVEN UP", given_up)
                self.assertNotIn("GIVEN UP", asking)


class TheUnlockPressesThePanelWhereItCanTest(unittest.TestCase):
    """`unlockFromSelectedItemPanel`, in both apps.

    It adds no way to *select*, so it cannot loop and needs no bound of its own:
    it answers `Nothing` unless the panel is already showing the thing to
    unlock, and the caller then does exactly what it did before #414. These
    cases pin that shape, since a version that selected would need a bound and
    would be a different change.
    """

    def bodies(self, app, names):
        source = source_of(SAXRAT_BOT_ELM if app == "saxrat"
                           else WINGMAN_BOT_ELM)
        return {name: collapsed(body_of(source, name)) for name in names}

    def test_it_presses_the_unlock_button_and_never_a_bar_entry(self):
        for name, _, _ in APPS:
            with self.subTest(app=name):
                body = self.bodies(name, ("unlockFromSelectedItemPanel",))[
                    "unlockFromSelectedItemPanel"]
                self.assertIn("selectedItemUnLockTargetButton", body)
                for forbidden in ("barAndImageCont", "useContextMenuCascade",
                                  "ctrlShiftClickUiElement"):
                    self.assertNotIn(forbidden, body)

    def test_it_never_selects_and_so_needs_no_bound(self):
        """The half that makes a second counter unnecessary."""
        for name, _, _ in APPS:
            with self.subTest(app=name):
                body = self.bodies(name, ("unlockFromSelectedItemPanel",))[
                    "unlockFromSelectedItemPanel"]
                self.assertIn("panelIsShowingText", body)
                self.assertNotIn("panelSelectUnansweredReadings", body)

    def test_the_old_mechanism_is_still_the_fall_back(self):
        """Behaviour is unchanged wherever the panel is showing something else.

        saxrat keeps its Ctrl+Shift+Click and the wingman keeps its cascade --
        and the wingman keeps `lockedTargetNamed` with it, which #390 kept alive
        precisely because a cascade needs a bar entry to right-click.
        """
        saxrat = self.bodies("saxrat", ("decideActionInAnomaly",))[
            "decideActionInAnomaly"]
        self.assertIn("ctrlShiftClickUiElement", saxrat)
        self.assertIn("unlockFromSelectedItemPanel", saxrat)
        wingman = self.bodies("wingman", ("unlockFleetPilotInTargetBar",))[
            "unlockFleetPilotInTargetBar"]
        self.assertIn("unlockFromSelectedItemPanel", wingman)
        self.assertIn("lockedTargetNamed", wingman)
        self.assertIn("useContextMenuCascade", wingman)

    def test_an_empty_name_matches_nothing_rather_than_everything(self):
        """`valueTypeNonEmptyString`'s register, applied to a lookup."""
        source_pairs = [(name, source_of(
            SAXRAT_BOT_ELM if name == "saxrat" else WINGMAN_BOT_ELM))
            for name, _, _ in APPS]
        for name, source in source_pairs:
            with self.subTest(app=name):
                body = collapsed(body_of(source, "panelIsShowingText"))
                self.assertIn("String.trim", body)
                self.assertIn('( _, "" ) -> False', body)


class TheTwoAppsShareTheseRulesTest(unittest.TestCase):
    """The declarations that are the same question in both bots.

    #414 puts one mechanism into two apps, so the rules that carry it are
    compared byte for byte rather than merely checked to exist in each. The doc
    comments are deliberately not compared: each argues from its own app's
    history.
    """

    SHARED = ("panelManoeuvreStep", "panelSelectReadingsAfterReading",
              "selectedItemPanelButton", "describePanelManoeuvreSelection",
              "selectedItemOrbitButton", "selectedItemUnLockTargetButton",
              "panelIsShowingText")

    @staticmethod
    def without_doc(body):
        return re.sub(r"\{-\|.*?-\}", "", body, flags=re.DOTALL).strip()

    def test_the_shared_rules_are_identical(self):
        saxrat = source_of(SAXRAT_BOT_ELM)
        wingman = source_of(WINGMAN_BOT_ELM)
        for name in self.SHARED:
            with self.subTest(declaration=name):
                self.assertEqual(
                    self.without_doc(body_of(saxrat, name)),
                    self.without_doc(body_of(wingman, name)),
                    "%s has drifted between the two apps" % name)


if __name__ == "__main__":
    unittest.main()
