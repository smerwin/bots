"""Tests for the wingman keeping station on its fleet commander.

Issue #365 asked for this, and the mechanism has since been replaced. A fleet
follow bot that flies its own kiting pattern against whatever it is shooting
drifts off the commander's grid, which is the one place it is supposed to be --
and a called target it has drifted out of range of is a broadcast it cannot act
on. So `orbit-fc` defaults to 'yes' and supersedes `orbit-in-combat` rather
than sitting beside it.

**What changed, and why these cases were re-expressed rather than deleted.**
The first shape right-clicked the commander's overview row, hovered `Orbit`,
and clicked the `orbit-fc-range` rung, so that the range came from the menu
rather than from the client's persistent default -- and every case in this file
was written against that. PILOT.md already recorded that flyout mis-clicking
when driven by hand; all four wingman pilots then reproduced it live on the
same day, with Kara opening an `InfoWindow` and Heather a `LoggerWindow` while
the cascade ran, and every pilot spending the whole 30-reading menu budget and
falling back to the key. Per-command range through that flyout is not
achievable from here.

So the manoeuvre is now **Approach**, commanded the way the client commands it:
hold `Q`, click the commander's overview row, release. That is
`ensureShipIsOrbiting`'s shape with the key and the manoeuvre swapped, which is
why both now come from `commandManeuverByModifierClick` rather than from two
hand-written copies.

The properties these cases were guarding are unchanged and still asserted --
the placement in the decision tree, the supersession of `orbit-in-combat`, the
counter advanced by the shipped rule, the bound, the give-up reaching the tree,
the stray-window close being itself bounded, and the prohibition on touching
the client's default distance. What changed is the mechanism they are asserted
against. The two cases that could not survive the change are the ones that
asserted the cascade itself -- that it took `Orbit` and then the configured
rung, and that the fall-back reused the key -- and they are replaced by cases
on the two mechanisms that took their place.

**One thing is deliberately not asserted here: that `Q` works.** Nothing in
this repo has watched a `Q` modifier-click command an approach; the proven
usage of that shape is `W` for an orbit. What is asserted instead is that
success is read from the client's own word -- the ship UI naming
`ManeuverApproach` -- and never from a dispatched click, so a `Q` that does not
work spends its budget and falls back rather than leaving a bot that believes
it is keeping station.

**The fall-back it falls back to is the proven half.** Past
`approachFleetCommanderKeyAskedReadingsBound` the arm selects the commander's
row and presses the Selected Item panel's `selectedItemApproach` --
`eve-online-mission-runner` reaches that button by that name, its note records
it taking a ship from 0.0 to 585 m/s after a cascade had achieved nothing
across 180 decisions, and the recorded corpus carries the name in that bot's
own status line. It is a port, not a guess, which is what separates it from
the `Warp to Within` flyout text that is still refused elsewhere in this
branch.

The cases run the real `Bot.elm` through `elm repl` and read its source.
Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import itertools
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")


class WingmanRepl(ElmRepl):
    """The shared harness, pointed at the wingman.

    `Common.PromptParser` is imported by name because `YesOrNo` is what the
    setting parses to and `Bot` does not re-export it.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-orbit-fc-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", ("import Bot exposing (..)",
                                       "import Common.PromptParser"))
        super().__init__(**kwargs)


def step(setting_is_yes=True, commander_on_grid=True, warping=False,
         approaching=False, stray_window=False, panel_shows=False,
         panel_offers=False, asked=0):
    """The shipped rule, asked about one reading."""
    return ("approachFleetCommanderStep { settingIsYes = %s"
            ", commanderOnGrid = %s"
            ", shipIsWarpingOrJumping = %s"
            ", shipIsApproaching = %s"
            ", strayWindowIsOpen = %s"
            ", panelShowsTheCommander = %s"
            ", panelOffersApproach = %s"
            ", askedReadings = %s }"
            % (setting_is_yes, commander_on_grid, warping, approaching,
               stray_window, panel_shows, panel_offers, asked))


def wingman_root_body(source):
    """Both halves of the in-space decision root, spliced in source order.

    #378 split it: `wingmanDecisionRootInSpace` keeps only the arms that take
    the ship off the grid, and `wingmanDecisionRootInSpaceOrdinary` holds the
    rest. The station-keeping arm is in the second half and the retreat in the
    first, and the ordering between them is the whole point of this file's last
    case.
    """
    root = source[source.index("wingmanDecisionRootInSpace context shipUI ="):]
    ordinary = root[root.index(
        "wingmanDecisionRootInSpaceOrdinary context shipUI ="):]
    return (root[:root.index("\n\n\n")] + "\n"
            + ordinary[:ordinary.index("\n\n\n")])


def elm_bool(value):
    return "True" if value else "False"


class TheStationKeepingDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_setting_turns_it_off(self):
        """`orbit-fc=no` falls back to the saxrat-style movement settings."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachFleetCommanderIsOff"
                 % step(setting_is_yes=False)]),
            [True])

    def test_only_a_commander_on_the_overview_can_be_approached(self):
        """A manoeuvre is issued against a row; with no row -- off grid, or an
        overview preset that hides fleet members -- there is nothing to
        click."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoCommanderOnGrid" % step(commander_on_grid=False)]),
            [True])

    def test_a_ship_in_warp_is_not_asked_to_approach(self):
        self.assertEqual(
            self.repl.evaluate(["%s == ShipIsWarpingOrJumping"
                                % step(warping=True)]),
            [True])

    def test_a_commander_on_grid_and_a_ship_not_approaching_presses_the_key(
            self):
        """The whole point: no fight, no broadcast and no rat is required
        first, and the first thing tried is the keypress."""
        self.assertEqual(
            self.repl.evaluate(["%s == ApproachWithTheKey" % step()]),
            [True])

    def test_the_key_gives_way_to_the_panel_and_then_to_nothing(self):
        """Both bounds in one place, because what matters is the sequence: the
        modifier click, then the panel's own Approach button in its two ticks,
        then a reading handed back. The panel half is the proven one -- it is
        `eve-online-mission-runner`'s `selectedItemApproach` -- so a `Q` that
        does not command anything costs twenty readings rather than a
        session."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachWithTheKey"
                 % step(asked="approachFleetCommanderKeyAskedReadingsBound - 1"),
                 "%s == SelectTheCommandersRow"
                 % step(asked="approachFleetCommanderKeyAskedReadingsBound"),
                 "%s == PressTheApproachButton"
                 % step(panel_shows=True, panel_offers=True,
                        asked="approachFleetCommanderKeyAskedReadingsBound"),
                 "%s == WaitForTheApproachButton"
                 % step(panel_shows=True,
                        asked="approachFleetCommanderKeyAskedReadingsBound"),
                 "%s == PressTheApproachButton"
                 % step(panel_shows=True, panel_offers=True,
                        asked="approachFleetCommanderAskedReadingsBound - 1"),
                 "%s == GaveUpOnTheApproach"
                 % step(panel_shows=True, panel_offers=True,
                        asked="approachFleetCommanderAskedReadingsBound")]),
            [True, True, True, True, True, True])

    def test_the_row_is_selected_before_the_button_is_pressed(self):
        """The panel acts on whatever is *currently* selected, which is the
        hazard `selectThenPanelAction` was written around. A panel showing some
        other object while offering an Approach button is the state where
        pressing first would send this ship at the wrong thing -- so the row is
        selected first even when the button is right there."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == SelectTheCommandersRow"
                 % step(panel_shows=False, panel_offers=True,
                        asked="approachFleetCommanderKeyAskedReadingsBound"),
                 "%s == SelectTheCommandersRow"
                 % step(panel_shows=False, panel_offers=False,
                        asked="approachFleetCommanderKeyAskedReadingsBound")]),
            [True, True])

    def test_the_panel_is_never_touched_while_the_key_still_has_budget(self):
        """The fall-back is a fall-back. A panel that happens to be showing the
        commander with its Approach button up must not pre-empt the key, or the
        key would never be exercised and the thing this run exists to measure
        would never be measured."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachWithTheKey"
                 % step(panel_shows=True, panel_offers=True),
                 "%s == ApproachWithTheKey"
                 % step(panel_shows=True, panel_offers=True,
                        asked="approachFleetCommanderKeyAskedReadingsBound"
                              " - 1")]),
            [True, True])

    def test_a_ship_already_approaching_is_left_alone(self):
        """The confirmation the operator asked for is this and only this: the
        ship UI's own manoeuvre indication, never a dispatched click."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AlreadyApproaching" % step(approaching=True)]),
            [True])

    def test_past_the_total_budget_the_reading_is_handed_back(self):
        """The arm answers `Nothing` and
        `describeApproachFleetCommanderAsk` carries the give-up -- #326 is what
        leaving it unbounded costs: a turret that could not activate held that
        bot's decision for 262 consecutive readings."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheApproach"
                 % step(asked="approachFleetCommanderAskedReadingsBound"),
                 "%s == GaveUpOnTheApproach"
                 % step(asked="approachFleetCommanderAskedReadingsBound + 50"),
                 "%s == GaveUpOnTheApproach"
                 % step(panel_shows=True, panel_offers=True,
                        asked="approachFleetCommanderAskedReadingsBound + 50")]),
            [True, True, True])

    def test_the_bounds_leave_the_fall_back_a_real_allowance(self):
        """Twenty for the key, twenty for the panel, the total written as the
        sum so neither end can be squeezed to nothing by moving the other --
        the arrangement the two bounds this replaced already had. Both halves
        are this file's key-over-a-click allowance, `weaponsAskedReadingsBound`,
        because both are a key or a click rather than a cascade."""
        self.assertEqual(
            self.repl.evaluate(
                ["approachFleetCommanderKeyAskedReadingsBound"
                 " == weaponsAskedReadingsBound",
                 "approachFleetCommanderKeyAskedReadingsBound == 20",
                 "approachFleetCommanderAskedReadingsBound == 40",
                 "approachFleetCommanderAskedReadingsBound"
                 " - approachFleetCommanderKeyAskedReadingsBound"
                 " == weaponsAskedReadingsBound"]),
            [True, True, True, True])

    def test_a_window_over_the_client_is_closed_before_asking_again(self):
        """PILOT.md's recorded mis-click opened a Database Information window,
        and the live run that removed the cascade opened an `InfoWindow` and a
        `LoggerWindow`. Leaving one on top of the client is not acceptable, so
        this outranks both 'already approaching' and another attempt."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == CloseAWindowLeftOverTheClient"
                 % step(stray_window=True, asked=1),
                 "%s == CloseAWindowLeftOverTheClient"
                 % step(stray_window=True, approaching=True, asked=1)]),
            [True, True])

    def test_a_window_open_before_the_ask_started_is_not_this_bots_to_close(
            self):
        """`0 < askedReadings` is the whole guard. An operator's own window on
        a healthy session must not be swept away by a bot that never asked for
        anything."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachWithTheKey"
                 % step(stray_window=True, asked=0)]),
            [True])

    def test_the_window_close_is_itself_bounded(self):
        """A close that does not land is the unbounded rescue #321 names -- one
        run pressed at a stray menu 16,791 times. Past the budget the window is
        reported and no longer poked at."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheApproach"
                 % step(stray_window=True,
                        asked="approachFleetCommanderAskedReadingsBound")]),
            [True])

    def test_the_give_up_is_reported_even_if_the_ship_reads_as_approaching(
            self):
        """The bound is checked before the state, `weaponsStep`'s ordering, so
        a spent budget is never masked by a moment that happens to look fine."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheApproach"
                 % step(approaching=True,
                        asked="approachFleetCommanderAskedReadingsBound")]),
            [True])

    def test_a_session_without_the_commander_never_reads_as_a_give_up(self):
        """The other half of the ordering. The counter resets when the
        commander leaves the overview, so this state should not arise -- and
        the rule answers for it anyway rather than resting on that."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoCommanderOnGrid"
                 % step(commander_on_grid=False,
                        asked="approachFleetCommanderAskedReadingsBound + 1"),
                 "%s == ApproachFleetCommanderIsOff"
                 % step(setting_is_yes=False,
                        asked="approachFleetCommanderAskedReadingsBound + 1")]),
            [True, True])

    def test_the_key_is_pressed_exactly_when_all_five_facts_line_up(self):
        """Every combination of the five facts at a fresh counter, so a swapped
        or dropped condition is caught rather than only the combinations
        somebody thought to write down. `askedReadings = 1` so the stray-window
        guard is armed."""
        combinations = list(itertools.product([False, True], repeat=5))
        expressions = [
            "%s == ApproachWithTheKey"
            % step(setting_is_yes=elm_bool(setting),
                   commander_on_grid=elm_bool(on_grid),
                   warping=elm_bool(warping),
                   approaching=elm_bool(approaching),
                   stray_window=elm_bool(stray),
                   panel_shows="True",
                   panel_offers="True",
                   asked=1)
            for setting, on_grid, warping, approaching, stray in combinations]
        expected = [setting and on_grid and not warping and not approaching
                    and not stray
                    for setting, on_grid, warping, approaching, stray
                    in combinations]
        self.assertEqual(self.repl.evaluate(expressions), expected)


class TheSettingTest(unittest.TestCase):
    """The shipped parser, asked what each spelling of the key gives."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parses_to(self, settings_string, expected):
        return ('(parseBotSettings "%s" |> Result.map .orbitFleetCommander)'
                ' == Ok Common.PromptParser.%s'
                % (settings_string, expected))

    def test_an_unconfigured_wingman_keeps_station_on_its_commander(self):
        """#365 asks for this on by default, not opt-in."""
        self.assertEqual(
            self.repl.evaluate(
                ["defaultBotSettings.orbitFleetCommander"
                 " == Common.PromptParser.Yes",
                 self.parses_to("", "Yes")]),
            [True, True])

    def test_the_key_can_be_turned_off(self):
        self.assertEqual(
            self.repl.evaluate([self.parses_to("orbit-fc=no", "No")]),
            [True])

    def test_the_spelling_the_issue_uses_is_accepted(self):
        """Setting names are matched case-sensitively -- `getSettingByNameOrGuide`
        is a `Dict.get` -- so #365's own `orbit-FC` has to be an alternative
        name or an operator who pasted the issue gets a session that ends
        before it starts (#161's failure)."""
        self.assertEqual(
            self.repl.evaluate(
                [self.parses_to("orbit-FC=no", "No"),
                 self.parses_to("orbit-fleet-commander=no", "No")]),
            [True, True])

    def test_the_manoeuvre_it_actually_commands_can_also_be_spelled(self):
        """The key is still called `orbit-fc` so a settings string written for
        an earlier version starts a session, but what it commands is an
        approach -- so the honest spelling has to work too."""
        self.assertEqual(
            self.repl.evaluate(
                [self.parses_to("approach-fc=no", "No"),
                 self.parses_to("approach-FC=no", "No")]),
            [True, True])

    def test_the_range_key_still_parses_and_no_longer_decides_anything(self):
        """`orbit-fc-range` named a rung of the Orbit flyout this bot no longer
        drives. Deleting it would end a session that has it set, which is
        #161's failure, so it still parses -- and nothing reads it to decide
        anything, which is what `TheRangeKeyIsAcceptedAndIgnoredTest` pins in
        source."""
        self.assertEqual(
            self.repl.evaluate(
                ['defaultOrbitFleetCommanderRange == "500 m"',
                 '(parseBotSettings "" |> Result.map .orbitFleetCommanderRange)'
                 ' == Ok "500 m"',
                 '(parseBotSettings "orbit-fc-range=5 km"'
                 ' |> Result.map .orbitFleetCommanderRange) == Ok "5 km"',
                 '(parseBotSettings "orbit-FC-range =  2,500 m "'
                 ' |> Result.map .orbitFleetCommanderRange) == Ok "2,500 m"']),
            [True, True, True, True])


class TheMechanismTest(unittest.TestCase):
    """How the manoeuvre is commanded, source-pinned.

    Needles are taken from slices that start at a definition line or a `case`
    arm rather than from the whole file: the doc comment on
    `approachTheFleetCommander` narrates the cascade it replaced, so a needle
    allowed to match a comment would find the old mechanism in exactly the
    function that must no longer contain it.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def body_of(self, definition_line):
        anchor = "\n" + definition_line
        self.assertIn(anchor, self.source)
        start = self.source.index(anchor) + 1
        return self.source[start:self.source.index("\n\n\n", start)]

    def test_the_arm_opens_no_context_menu_at_all(self):
        """The cascade is what mis-clicked. Nothing in this arm reopens one."""
        body = self.body_of("approachTheFleetCommander context shipUI =")
        for cascade in ("useContextMenuCascadeOnOverviewEntry",
                        "useContextMenuCascade",
                        "useMenuEntryWithTextContaining",
                        "menuCascadeCompleted"):
            with self.subTest(cascade=cascade):
                self.assertNotIn(cascade, body)

    def test_the_arm_commands_the_approach_through_the_shared_helper(self):
        """`ensureShipIsApproaching`, which is `ensureShipIsOrbiting`'s shape
        with the key and the manoeuvre swapped. Nothing posts a key code
        directly from the arm."""
        body = self.body_of("approachTheFleetCommander context shipUI =")
        self.assertIn("ensureShipIsApproaching shipUI", body)
        self.assertIsNone(re.search(r"vkey_\w+", body))

    def test_the_two_manoeuvres_come_from_one_helper(self):
        """The key and the manoeuvre it commands are one pairing. Two
        hand-written copies is how a `Q` that stopped meaning approach would
        take the orbit with it."""
        for definition, key, maneuver in (
                ("ensureShipIsOrbiting =", "vkey_W", "ManeuverOrbit"),
                ("ensureShipIsApproaching =", "vkey_Q", "ManeuverApproach")):
            with self.subTest(definition=definition):
                body = self.body_of(definition)
                self.assertIn("commandManeuverByModifierClick", body)
                self.assertIn("EffectOnWindow." + key, body)
                self.assertIn(
                    "EveOnline.ParseUserInterface." + maneuver, body)

    def test_the_key_is_held_down_around_the_click_and_released(self):
        """The client's own modifier shape: down, click, up. A click with no
        key is a plain selection and commands nothing."""
        body = self.body_of(
            "commandManeuverByModifierClick command shipUI overviewEntry =")
        # From the effect list itself, not from the `Ok effectToClick ->`
        # pattern that binds it -- the binding is above the list and would
        # make any ordering look right.
        effects = body[body.index("decideActionForCurrentStep"):]
        self.assertLess(effects.index("EffectOnWindow.KeyDown command.key"),
                        effects.index("effectToClick"))
        self.assertLess(effects.index("effectToClick"),
                        effects.index("EffectOnWindow.KeyUp command.key"))

    def test_only_the_clients_own_word_counts_as_success(self):
        """A dispatched click is not a manoeuvre. This is the whole reason a
        `Q` that turns out not to work is visible rather than silent."""
        body = self.body_of(
            "commandManeuverByModifierClick command shipUI overviewEntry =")
        self.assertIn(".maneuverType) == Just command.maneuver", body)
        reader = self.body_of(
            "shipIsApproachingFromReading readingFromGameClient =")
        self.assertIn(
            "== Just EveOnline.ParseUserInterface.ManeuverApproach", reader)

    def test_the_fall_back_presses_the_panels_own_approach_button(self):
        """Two ticks, and the order matters: the panel acts on whatever is
        selected, so the row is selected first and the button pressed after."""
        body = self.body_of("approachTheFleetCommander context shipUI =")
        select = body[body.index("SelectTheCommandersRow ->"):
                      body.index("WaitForTheApproachButton ->")]
        self.assertIn("clickUiElementForNavigation entry.uiNode", select)
        press = body[body.index("PressTheApproachButton ->"):]
        self.assertIn("clickUiElementForNavigation button", press)
        self.assertIn("selectedItemApproachButtonName", body)

    def test_the_button_name_is_a_port_and_not_a_guess(self):
        """`eve-online-mission-runner` reaches this button by this name, and
        its own note records the live result. Every other `selectedItem` name
        in this file was read the same way -- none of them is invented, which
        is what #42 asks of a matcher."""
        block = self.body_of("selectedItemApproachButtonName =")
        self.assertIn('"selectedItemApproach"', block)
        with open(os.path.join(
                REPO_DIR, "implement", "applications", "eve-online",
                "eve-online-mission-runner", "Bot.elm"),
                encoding="utf-8") as handle:
            mission_runner = handle.read()
        self.assertIn('"selectedItemApproach"', mission_runner)
        names = set(re.findall(r'"(selectedItem\w+)"', self.source))
        self.assertEqual(
            names,
            {"selectedItemActivateGate", "selectedItemJump",
             "selectedItemWarpTo", "selectedItemApproach"})


class TheRangeKeyIsAcceptedAndIgnoredTest(unittest.TestCase):
    """A setting that silently does nothing is the thing that must not exist.

    `orbit-fc-range` named a rung of a flyout this bot no longer drives, so it
    cannot decide anything any more. Deleting it would end a session that has
    it set (#161); leaving it to be quietly ignored is worse. So it parses, no
    decision reads it, and the status line names it whenever an operator has
    set it to something other than the default.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_no_decision_reads_the_range(self):
        """The only readers left are the describer's clause and the default it
        compares against."""
        readers = [self.source.count(needle) for needle in
                   ("orbitFleetCommanderRange",)]
        self.assertTrue(readers[0] >= 1)
        arm_start = self.source.index(
            "\napproachTheFleetCommander context shipUI =")
        arm = self.source[arm_start:self.source.index("\n\n\n", arm_start)]
        self.assertNotIn("orbitFleetCommanderRange", arm)
        step_start = self.source.index(
            "\napproachFleetCommanderStep approachCase =")
        step_body = self.source[
            step_start:self.source.index("\n\n\n", step_start)]
        self.assertNotIn("orbitFleetCommanderRange", step_body)

    def test_the_status_line_names_it_as_ignored(self):
        start = self.source.index(
            "\ndescribeApproachFleetCommanderAsk context =")
        body = self.source[start:self.source.index("\n\n\n", start)]
        self.assertIn("IGNORED", body)
        self.assertIn("defaultOrbitFleetCommanderRange", body)

    def test_the_header_says_it_is_ignored_too(self):
        """`--help` reads the header, and an operator who set the key has to
        find out there rather than by watching the ship."""
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("`orbit-fc-range`", header)
        self.assertIn("Accepted and ignored", header)
        self.assertIn("ACCEPTED AND IGNORED", self.source)

    def test_the_orbit_menu_matcher_is_gone(self):
        """Nothing matches an `Orbit` menu entry any more, because nothing
        opens that menu."""
        self.assertNotIn("orbitMenuEntryText", self.source)


class ThePlacementAndTheSupersessionTest(unittest.TestCase):
    """Source-pinned, because each of these is a shape rather than a value.

    A suite that only exercised `approachFleetCommanderStep` would pass on a
    bot whose arm nothing could reach, which is exactly the defect #360
    shipped.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        for needle in needles:
            self.assertIn(needle, self.source)
        return [self.source.index(needle) for needle in needles]

    def test_it_sits_below_the_drones_and_the_guns(self):
        """#326's rule: reaching the drones or the guns must never require a
        manoeuvre to land first."""
        drones, guns, approach = self.order_of(
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of",
            "case approachTheFleetCommander context shipUI of")
        self.assertLess(drones, guns)
        self.assertLess(guns, approach)

    def test_it_sits_above_the_gate(self):
        """#348's arm answers `Just (wait)` on every reading a gate is on the
        overview with rats still around. Below it, station-keeping would be
        starved in the one state it exists for."""
        approach, gate = self.order_of(
            "case approachTheFleetCommander context shipUI of",
            "case accelerationGateStep context of")
        self.assertLess(approach, gate)

    def test_orbit_fc_supersedes_orbit_in_combat(self):
        """#365 is explicit that this is not a third option beside the other
        two: with `orbit-fc=yes` the combat path must not issue its own orbit
        at a rat, which is what walks the ship off the commander's grid."""
        chooser = self.source[self.source.index(
            "    if context.eventContext.botSettings.orbitFleetCommander"):]
        chooser = chooser[:chooser.index("\n\n\n")]
        self.assertLess(
            chooser.index("orbitFleetCommander == PromptParser.Yes"),
            chooser.index("orbitInCombat == PromptParser.Yes"))
        self.assertNotIn("ensureShipIsOrbitingDecision",
                         chooser[:chooser.index(
                             "orbitInCombat == PromptParser.Yes")])

    def test_the_counter_is_advanced_by_the_shipped_rule_itself(self):
        """#102's defect is a counter advanced by one condition and read by
        another. The memory update calls `approachFleetCommanderStep` rather
        than restating it, so the two cannot drift apart."""
        update = self.source[self.source.index(
            "updateMemoryForNewReadingFromGame context botMemoryBefore ="):]
        update = update[:update.index(
            "\n\n\ngetCurrentAnomalyIDAsSeenInProbeScanner")]
        self.assertIn("approachFleetCommanderStep", update)
        self.assertIn("approachFleetCommanderAnswersThatSpendAReading", update)
        self.assertIn("approachFleetCommanderAskedReadings + 1", update)

    def test_the_counter_is_advanced_by_the_shipped_rule_and_the_memory_field(
            self):
        """The other half of #102: the memory update writes the field the
        decision reads, and by name."""
        update = self.source[self.source.index(
            "updateMemoryForNewReadingFromGame context botMemoryBefore ="):]
        update = update[:update.index(
            "\n\n\ngetCurrentAnomalyIDAsSeenInProbeScanner")]
        self.assertIn("approachFleetCommanderAskedReadings + 1", update)

    def test_the_commander_is_read_the_one_way_both_sides_can_read_him(self):
        """The arm and the counter resolve the commander through the same
        reading-only function. The manoeuvre is issued against the commander's
        overview row, so a name the client itself did not write is a name there
        may be no row for -- `fleetCommanderName`'s fall-back to
        `follow-fleet-broadcast-from` belongs to the arms that run *to* him
        (#367), not to the one that clicks his row."""
        entry = self.source[self.source.index(
            "fleetCommanderOverviewEntry readingFromGameClient ="):]
        entry = entry[:entry.index("\n\n\n")]
        self.assertIn("fleetCommanderNameFromFleetWindowHeader", entry)
        self.assertNotIn("fleetCommanderName context", entry)

    def test_a_give_up_is_visible_in_the_status_line(self):
        """The arm answers `Nothing` when it gives up, so without this a ship
        that stopped trying reads exactly like a ship keeping station fine."""
        self.assertIn("describeApproachFleetCommanderAsk context", self.source)
        self.assertIn("Approach on the commander: ", self.source)
        self.assertIn("GAVE UP after ", self.source)

    def test_a_missing_overview_row_names_the_preset_as_a_cause(self):
        """The bot clicks the commander's overview row, so an overview preset
        that hides fleet members leaves it with nothing to click -- and that is
        indistinguishable from a commander who is off the grid. Reporting only
        'not on this grid' would send an operator looking in the wrong place."""
        start = self.source.index(
            "\ndescribeApproachFleetCommanderAsk context =")
        body = self.source[start:self.source.index("\n\n\n", start)]
        self.assertIn("NO OVERVIEW ROW", body)
        self.assertIn("preset", body)
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("Show fleet members on the active overview preset",
                      header)

    def test_the_header_offers_both_keys(self):
        """`--help` reads the header, and #161's failure is a header that
        promises a key the parser has never heard of. The converse -- a parsed
        key the header hides -- is #125. Both keys are named in both places."""
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("`orbit-fc`", header)
        self.assertIn("`orbit-fc-range`", header)
        self.assertIn('( "orbit-fc"', self.source)
        self.assertIn('( "orbit-fc-range"', self.source)

    def test_the_arm_is_below_every_arm_that_fights(self):
        """Restating the whole chain in one place, so a rebase that moved the
        arm to a plausible-looking spot still has to move it past a case."""
        ending, retreat, modules, broadcast, drones, guns, approach, gate = \
            self.order_of(
                "case sessionIsEnding context shipUI of",
                "case retreatToTheCommander context",
                "case activateAlwaysOnModules context of",
                "case actOnFleetBroadcast context shipUI of",
                "case dronesAssistTheCommander context of",
                "case fireOnActiveTarget context of",
                "case approachTheFleetCommander context shipUI of",
                "case accelerationGateStep context of")
        self.assertEqual(
            [ending, retreat, modules, broadcast, drones, guns, approach,
             gate],
            sorted([ending, retreat, modules, broadcast, drones, guns,
                    approach, gate]))


class TheAnswersThatSpendAReadingTest(unittest.TestCase):
    """Which answers the counter advances on -- executed, not read.

    **This class exists because a source pin here had a hole.** The first
    version required `ApproachWithTheKey` and `CloseAWindowLeftOverTheClient`
    to be in the list and forbade the five silent answers, and said nothing
    about the three the panel fall-back uses. Deleting all three from
    `approachFleetCommanderAnswersThatSpendAReading` broke nothing: the counter
    would then never advance while the fall-back ran, so
    `approachFleetCommanderAskedReadingsBound` could never be reached from that
    state and the fall-back would poke at the panel forever. That is #34's
    shape -- a bound whose counter cannot reach it -- sitting inside the very
    change that exists to bound this arm.

    So the question is asked exhaustively and of every constructor, which is
    the only form that cannot go quiet when a constructor is added.
    """

    ADVANCES = ("ApproachWithTheKey", "SelectTheCommandersRow",
                "PressTheApproachButton", "WaitForTheApproachButton",
                "CloseAWindowLeftOverTheClient")
    SILENT = ("ApproachFleetCommanderIsOff", "NoCommanderOnGrid",
              "ShipIsWarpingOrJumping", "AlreadyApproaching",
              "GaveUpOnTheApproach")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_answer_that_spends_a_reading_is_counted(self):
        """Each of the five dispatches an effect or holds the reading in this
        arm. `WaitForTheApproachButton` counts for the reason
        `askingTheGateToOpen` counts its own wait: a panel that showed the row
        and never produced the button would otherwise buy unlimited readings by
        doing nothing."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s approachFleetCommanderAnswersThatSpendAReading"
                 % answer for answer in self.ADVANCES]),
            [True] * len(self.ADVANCES))

    def test_no_answer_that_does_nothing_is_counted(self):
        """A session that never has the commander on grid must not read as a
        give-up, and a give-up must not go on advancing the number it reports."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.member %s approachFleetCommanderAnswersThatSpendAReading"
                 % answer for answer in self.SILENT]),
            [False] * len(self.SILENT))

    def test_the_list_holds_those_five_and_nothing_else(self):
        """Length as well as membership, so a constructor added to the list
        without being thought about is caught rather than absorbed."""
        self.assertEqual(
            self.repl.evaluate(
                ["List.length approachFleetCommanderAnswersThatSpendAReading"
                 " == 5"]),
            [True])

    def test_the_bound_is_reachable_from_the_fall_back(self):
        """The property all of the above exists to protect, stated directly:
        every answer the arm can give between the key bound and the total bound
        advances the counter, so the total bound is reachable rather than
        decorative (#34)."""
        reachable = [
            "List.member (%s) approachFleetCommanderAnswersThatSpendAReading"
            % step(panel_shows=shows, panel_offers=offers,
                   asked="approachFleetCommanderKeyAskedReadingsBound")
            for shows, offers in
            (("False", "False"), ("True", "False"), ("True", "True"))]
        self.assertEqual(self.repl.evaluate(reachable), [True, True, True])


class TheClientDefaultIsNeverTouchedTest(unittest.TestCase):
    """The client's default Orbit distance is not this bot's to change.

    It lives in the client rather than the ship, so PILOT.md records it
    surviving the loss of a hull and applying to whatever is boarded next --
    and #359 hard-linked `core_char_*.dat` across six characters, so a default
    changed while flying one of them follows the others, including any that
    later fly `eve-online-saxrat` into a belt at 500 m.

    The route being refused here is a real one and was an earlier plan:
    right-click the Selected Item panel's Orbit button, take `Set Default
    "Orbit" Distance`, and type into the modal's `edit_qty`. That modal is
    recorded in `saxrat_run15.log`. Nothing in this bot may drive it. The same
    prohibition now covers the Approach distance, which is the client's own
    setting for exactly the same reasons.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_nothing_drives_the_set_default_modal(self):
        for forbidden in ('Set Default "Orbit"', "Set default \"Orbit\" distance",
                          'Set Default "Approach"',
                          "edit_qty", "selectedItemOrbit",
                          "ok_dialog_button"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_the_stray_window_reader_names_no_unread_literal(self):
        """The reader is structural, and it is what *recorded* the two window
        type names the corpus lacked -- naming them in the matcher now would
        make it go quiet the next time the client invents a third."""
        block = self.source[self.source.index(
            "windowOpenedOverTheClient readingFromGameClient ="):]
        block = block[:block.index("\n\n\n")]
        for invented in ("ShowInfo", "Database Information", "InfoWindow",
                         "LoggerWindow"):
            with self.subTest(invented=invented):
                self.assertNotIn(invented, block)
        self.assertIn('String.endsWith "Window"', block)
        self.assertIn("closeButton", block)
        start = self.source.index(
            "\ndescribeApproachFleetCommanderAsk context =")
        self.assertIn("pythonObjectTypeName",
                      self.source[start:self.source.index("\n\n\n", start)])

    def test_nothing_is_clicked_at_a_guessed_point(self):
        """#321's stray-menu rescue right-clicked a computed location 16,791
        times in one run and created the menu it was clearing. The window this
        arm closes is closed by its own close button or not at all."""
        arm = self.source[self.source.index(
            "\napproachTheFleetCommander context shipUI ="):]
        arm = arm[:arm.index("\n\n\n")]
        close = arm[arm.index("CloseAWindowLeftOverTheClient ->"):]
        close = close[:close.index("ApproachWithTheKey ->")]
        self.assertIn("closeButton", close)
        self.assertIn("clickUiElementForNavigation closeButton", close)
        self.assertNotIn("effectsMouseClickAtLocation", close)

    def test_the_header_says_why_rather_than_only_that(self):
        """A prohibition with no reason attached is one somebody undoes."""
        header = self.source[:self.source.index("\nmodule Bot exposing")]
        self.assertIn("#359", header)
        self.assertIn("core_char_", header)


class TheRetreatOutranksStationKeepingTest(unittest.TestCase):
    """#364's retreat must always answer before this arm can.

    The two changes landed on parallel branches and this is where they meet.
    `retreatToTheCommander` sits second in `wingmanDecisionRootInSpace`, under
    `sessionIsEnding` and over everything else, because a ship past its shield
    or armour threshold has to break off. Station-keeping does the opposite --
    it holds the ship on the grid it is being shot on -- so an ordering that
    let it answer first would keep a dying ship on station while the guard that
    exists to save it never got the reading.

    Neither branch's own cases could have caught an inversion: #364's pin the
    retreat against the arms that existed when it was written, and this arm is
    not one of them. Nothing but a case naming both refuses a future rebase
    that reorders them, and a rebase is exactly how this one arrived.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_retreat_arm_comes_first(self):
        retreat = self.source.index("case retreatToTheCommander context")
        approach = self.source.index(
            "case approachTheFleetCommander context shipUI of")
        self.assertLess(retreat, approach)

    def test_the_retreat_is_still_the_second_arm_in_the_root(self):
        """Not merely 'above the approach'. Everything between `sessionIsEnding`
        and the retreat would be an arm that can hold a reading away from it,
        so the two have to stay adjacent."""
        arms = re.findall(r"case (\w+) context", wingman_root_body(self.source))
        self.assertEqual(arms[:2],
                         ["sessionIsEnding", "retreatToTheCommander"])
        self.assertIn("approachTheFleetCommander", arms)
        self.assertGreater(arms.index("approachTheFleetCommander"), 1)


if __name__ == "__main__":
    unittest.main()
