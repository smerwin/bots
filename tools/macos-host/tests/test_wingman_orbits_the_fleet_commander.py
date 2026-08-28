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

So the manoeuvre is now **Approach**, and #387 replaced the second mechanism as
well: it is commanded by a **double click on the commander's overview row**,
which presses no key at all.

**Why the key had to go, and why that is not cosmetic.** The shape #384 built
was a `Q` chord -- `KeyDown vkey_Q`, click, `KeyUp vkey_Q`. That is precisely
what `eve-online-saxrat` deliberately removed, and
`test_saxrat_approach_by_double_click.py` is the authority: `cg_input` posts a
key event without stamping flags on it, so a posted `Q` carries whatever
modifier state the session happens to hold; with the Fn bit set that is macOS
Quick Note, and one recorded run took that branch **1,571 times** while Notes
came to the front **241 times** with nobody at the machine.
`approachTheFleetCommander` is reached whenever the commander is on grid, so it
is on a hot path by exactly the same design.

The gesture is a port rather than an invention. `mouseDoubleClickOnUIElement`
and `effectsMouseDoubleClickAtLocation` were absent from this app's vendored
framework and are now present in it byte-identical to saxrat's, so the wingman
converges on the majority of the six apps rather than growing a fourth dialect.

The properties these cases were guarding are unchanged and still asserted --
the placement in the decision tree, the supersession of `orbit-in-combat`, the
counter advanced by the shipped rule, the bound, the give-up reaching the tree,
the stray-window close being itself bounded, and the prohibition on touching
the client's default distance. What changed is the mechanism they are asserted
against, twice now.

**Neither manoeuvre posts a key any more, and `commandManeuverByModifierClick`
is gone.** #387 took the approach off it, leaving the orbit as its only caller;
#414 then took the orbit off it too, because a `W` held over a click on an
overview row is a gesture aimed at a position and the row order changes between
the reading and the click (#413). `ensureShipIsOrbiting` selects the row and
presses the Selected Item panel's own Orbit, so the helper had no callers left.
The cases that asserted the chord are re-expressed as cases that assert its
absence and the select-then-press that replaced it, rather than deleted -- and
what *executes* the panel rule is `test_selected_item_panel_manoeuvres`, since
`ensureShipIsOrbiting` now takes a whole `BotDecisionContext` and cannot be
handed a ship and a row the way the approach still can.

**One thing is deliberately not asserted here: that the double click commands
an approach.** saxrat double clicks a *rat's* row for exactly this and no run
has recorded `ManeuverApproach` coming back, on any row. What is asserted
instead is that success is read from the client's own word -- the ship UI
naming `ManeuverApproach` -- and never from a dispatched click, so a gesture
that does not work spends its budget and falls back rather than leaving a bot
that believes it is keeping station.

Confirmed by mutation, five of them, each failing named cases:

1. the `Q` chord restored, by routing `ensureShipIsApproaching` back through
   `commandManeuverByModifierClick` -- six cases, among them
   `test_the_approach_presses_no_key_at_all`,
   `test_the_approach_dispatches_a_double_click` and
   `test_nothing_in_this_bot_posts_an_approach_chord`;
2. the double click swapped for a single one --
   `test_the_approach_dispatches_a_double_click` and
   `test_the_approach_double_clicks_and_the_orbit_holds_its_key`;
3. the `ManeuverApproach` confirmation dropped, so the branch asks again on a
   ship the client says is already approaching --
   `test_the_clients_own_word_is_the_only_thing_that_stops_the_ask` and both
   source cases;
4. the decline swallowed -- the `Err` folded into a `Result.withDefault []`, so
   a row too small to click prints "Approach." over nothing. That fails
   `test_a_row_too_small_to_click_declines_out_loud` and *not*
   `test_a_row_too_small_to_click_dispatches_nothing`, which is the whole
   point: an empty list and a spoken decline dispatch alike, so only the
   saying-so half can tell them apart;
5. a chord put back into either manoeuvre --
   `test_neither_manoeuvre_posts_a_chord_any_more`. What now makes the approach
   cases a measurement rather than a repl answering `[]` to everything is
   `test_the_approach_dispatches_a_double_click`, which asks for an exact
   five-effect list rather than for a non-empty one.

**The fall-back it falls back to is the proven half.** Past
`approachFleetCommanderDoubleClickAskedReadingsBound` the arm selects the
commander's row and presses the Selected Item panel's `selectedItemApproach`.
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
from test_saxrat_approach_by_double_click import rows_of_height  # noqa: E402
from test_saxrat_learned_lock_range import ROW_HEIGHT, row_center  # noqa: E402
from test_saxrat_ported_guards import (  # noqa: E402
    SAXRAT_DIR, SaxratRepl, label, node, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The commander's row, as the client draws one. Only the geometry matters to
# `ensureShipIsApproaching`, which is handed an overview entry and never asks
# whose it is -- resolving the commander is `fleetCommanderOverviewEntry`'s job
# and has its own cases.
COMMANDER = "Kara Thrace"

# The two bounds, by the names `Bot.elm` gives them. Spelled out here because
# `step(...)` takes the counter as an Elm expression, and these names are long
# enough that writing them inline pushes every call past the margin.
DOUBLE_CLICK_BOUND = "approachFleetCommanderDoubleClickAskedReadingsBound"
TOTAL_BOUND = "approachFleetCommanderAskedReadingsBound"


def reading_binding(name, children):
    """`SaxratRepl.reading_binding`, called rather than copied.

    It names only `EveOnline.MemoryReading` and `EveOnline.ParseUserInterface`,
    which resolve in whichever app's tree the repl was built from -- so it
    builds a real wingman reading as readily as a saxrat one, and the two
    cannot drift.
    """
    return SaxratRepl.reading_binding(name, children)


def ship_ui_indicating(maneuver):
    """A `ShipUI` the real parser accepts, carrying a manoeuvre indication.

    `parseShipUIIndication` reads the manoeuvre out of the display texts under
    a node whose name contains `indicationcontainer`, so this is the client's
    own channel rather than a field set by hand. `None` leaves the indication
    absent, which is what a ship doing nothing in particular looks like.
    """
    ship = ship_ui(100, 100, 4)
    if maneuver is not None:
        ship["children"].append(
            node("Container", {"_name": "indicationContainer"},
                 [label(maneuver, (100, 100, 80, 16))],
                 region=(100, 100, 80, 16)))
    return ship


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


class WingmanManeuverRepl(WingmanRepl):
    """The wingman's `Bot.elm`, plus what running one manoeuvre costs.

    `ensureShipIsApproaching` takes a `ShipUI` and an `OverviewWindowEntry`,
    neither of which can be written out by hand without inventing a record the
    parser would never have produced. So both come out of a **real** reading
    run through the app's own `EveOnline.ParseUserInterface`, and what the
    branch is handed here is what the bot would have been handed.

    The bindings ride in the preamble rather than in each case's `definitions`,
    which `imports_and_bindings` folds into the one `let` that asks the
    question -- so they cost the same single compile the imports do.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import EveOnline.BotFrameworkSeparatingMemory",
        "import Common.DecisionPath",
        "import Common.EffectOnWindow as EffectOnWindow",
    )

    BINDINGS = (
        "unpack ="
        " Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "effectsOfLeaf = \\leaf ->\n"
        "    case leaf of\n"
        "        EveOnline.BotFrameworkSeparatingMemory.ContinueSession"
        " continue ->\n"
        "            continue.effectsOnGameClient\n"
        "        EveOnline.BotFrameworkSeparatingMemory.FinishSession ->\n"
        "            []",
        # The manoeuvre, asked about the ship and the first overview row of a
        # really parsed reading. Only the approach is asked this way now: since
        # #414 `ensureShipIsOrbiting` takes a whole `BotDecisionContext`, which
        # is what `test_selected_item_panel_manoeuvres` executes it through.
        "maneuverFor = \\command parsed -> parsed"
        " |> Maybe.andThen (\\p -> Maybe.map2 command p.shipUI"
        " (p.overviewWindows |> List.concatMap .entries |> List.head))"
        " |> Maybe.andThen identity",
        "approachFor = maneuverFor ensureShipIsApproaching",
        "effectsOfResult = \\result -> result"
        " |> Result.map (unpack >> Tuple.second >> effectsOfLeaf)"
        " |> Result.withDefault []",
        "effectsFor = \\command parsed -> maneuverFor command parsed"
        " |> Maybe.map effectsOfResult |> Maybe.withDefault []",
        "saidBy = \\command parsed ->\n"
        "    case maneuverFor command parsed of\n"
        "        Nothing ->\n"
        "            \"NOTHING TO DO\"\n"
        "        Just (Err error) ->\n"
        "            \"DECLINED: \" ++ error\n"
        "        Just (Ok path) ->\n"
        "            unpack path |> Tuple.first |> String.join \" | \"",
        "isKeyEffect = \\effect ->\n"
        "    case effect of\n"
        "        EffectOnWindow.KeyDown _ ->\n"
        "            True\n"
        "        EffectOnWindow.KeyUp _ ->\n"
        "            True\n"
        "        _ ->\n"
        "            False",
        "keysIn = List.filter isKeyEffect",
        # The gesture the host collapses into `cg_input`'s `doubleclick`: two
        # press/release pairs with nothing between them, carrying the move.
        "doubleClickAt = \\x y ->"
        " [ EffectOnWindow.MouseMoveTo { x = x, y = y }"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft ]",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-maneuver-repl-")
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
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


def block_of(path, needle):
    """One declaration of `path`, from `needle` to the blank line that ends it.

    Used to compare a vendored function against the copy it was ported from.
    Comparing whole files would say nothing -- these six copies diverged years
    ago -- and comparing a collapsed form would let an `elm-format` dialect
    through, which is the fourth dialect the port exists to avoid.
    """
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    assert needle in source, "%s holds no %r" % (path, needle)
    start = source.index(needle)
    return source[start:source.index("\n\n\n", start)]


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

    def test_a_commander_on_grid_and_a_ship_not_approaching_double_clicks(
            self):
        """The whole point: no fight, no broadcast and no rat is required
        first, and the first thing tried is the double click."""
        self.assertEqual(
            self.repl.evaluate(["%s == ApproachByDoubleClick" % step()]),
            [True])

    def test_the_double_click_gives_way_to_the_panel_and_then_to_nothing(self):
        """Both bounds in one place, because what matters is the sequence: the
        double click, then the panel's own Approach button in its two ticks,
        then a reading handed back. The panel half is the proven one -- it is
        `eve-online-mission-runner`'s `selectedItemApproach` -- so a gesture
        that does not command anything costs twenty readings rather than a
        session."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachByDoubleClick"
                 % step(asked=DOUBLE_CLICK_BOUND + " - 1"),
                 "%s == SelectTheCommandersRow"
                 % step(asked=DOUBLE_CLICK_BOUND),
                 "%s == PressTheApproachButton"
                 % step(panel_shows=True, panel_offers=True,
                        asked=DOUBLE_CLICK_BOUND),
                 "%s == WaitForTheApproachButton"
                 % step(panel_shows=True,
                        asked=DOUBLE_CLICK_BOUND),
                 "%s == PressTheApproachButton"
                 % step(panel_shows=True, panel_offers=True,
                        asked=TOTAL_BOUND + " - 1"),
                 "%s == GaveUpOnTheApproach"
                 % step(panel_shows=True, panel_offers=True,
                        asked=TOTAL_BOUND)]),
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
                        asked=DOUBLE_CLICK_BOUND),
                 "%s == SelectTheCommandersRow"
                 % step(panel_shows=False, panel_offers=False,
                        asked=DOUBLE_CLICK_BOUND)]),
            [True, True])

    def test_the_panel_is_never_touched_while_the_double_click_has_budget(self):
        """The fall-back is a fall-back. A panel that happens to be showing the
        commander with its Approach button up must not pre-empt the double
        click, or the double click would never be exercised and the thing this
        run exists to measure would never be measured."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ApproachByDoubleClick"
                 % step(panel_shows=True, panel_offers=True),
                 "%s == ApproachByDoubleClick"
                 % step(panel_shows=True, panel_offers=True,
                        asked=DOUBLE_CLICK_BOUND + " - 1")]),
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
                 % step(asked=TOTAL_BOUND),
                 "%s == GaveUpOnTheApproach"
                 % step(asked=TOTAL_BOUND + " + 50"),
                 "%s == GaveUpOnTheApproach"
                 % step(panel_shows=True, panel_offers=True,
                        asked=TOTAL_BOUND + " + 50")]),
            [True, True, True])

    def test_the_bounds_leave_the_fall_back_a_real_allowance(self):
        """Twenty for the double click, twenty for the panel, the total written
        as the sum so neither end can be squeezed to nothing by moving the
        other -- the arrangement the two bounds this replaced already had. Both
        halves are this file's allowance for an ask that is a key or a click
        rather than a cascade, `weaponsAskedReadingsBound`."""
        self.assertEqual(
            self.repl.evaluate(
                ["approachFleetCommanderDoubleClickAskedReadingsBound"
                 " == weaponsAskedReadingsBound",
                 "approachFleetCommanderDoubleClickAskedReadingsBound == 20",
                 "approachFleetCommanderAskedReadingsBound == 40",
                 "approachFleetCommanderAskedReadingsBound"
                 " - approachFleetCommanderDoubleClickAskedReadingsBound"
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
                ["%s == ApproachByDoubleClick"
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
                        asked=TOTAL_BOUND)]),
            [True])

    def test_the_give_up_is_reported_even_if_the_ship_reads_as_approaching(
            self):
        """The bound is checked before the state, `weaponsStep`'s ordering, so
        a spent budget is never masked by a moment that happens to look fine."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnTheApproach"
                 % step(approaching=True,
                        asked=TOTAL_BOUND)]),
            [True])

    def test_a_session_without_the_commander_never_reads_as_a_give_up(self):
        """The other half of the ordering. The counter resets when the
        commander leaves the overview, so this state should not arise -- and
        the rule answers for it anyway rather than resting on that."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoCommanderOnGrid"
                 % step(commander_on_grid=False,
                        asked=TOTAL_BOUND + " + 1"),
                 "%s == ApproachFleetCommanderIsOff"
                 % step(setting_is_yes=False,
                        asked=TOTAL_BOUND + " + 1")]),
            [True, True])

    def test_the_row_is_double_clicked_exactly_when_all_five_facts_line_up(
            self):
        """Every combination of the five facts at a fresh counter, so a swapped
        or dropped condition is caught rather than only the combinations
        somebody thought to write down. `askedReadings = 1` so the stray-window
        guard is armed."""
        combinations = list(itertools.product([False, True], repeat=5))
        expressions = [
            "%s == ApproachByDoubleClick"
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


class TheApproachIsADoubleClickTest(unittest.TestCase):
    """`ensureShipIsApproaching` executed, over really parsed readings.

    #384 built this as a `Q` chord and #387 replaced it, so the effects the
    branch actually produces are what these cases read -- not the source, which
    can be made to look right while dispatching something else.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanManeuverRepl)
        drawn = rows_of_height([("5,000 m", COMMANDER)], ROW_HEIGHT)
        cls.definitions = [
            reading_binding("idle", [ship_ui_indicating(None), drawn]),
            reading_binding(
                "approaching", [ship_ui_indicating("Approach"), drawn]),
            reading_binding("orbiting", [ship_ui_indicating("Orbit"), drawn]),
            reading_binding(
                "tiny",
                [ship_ui_indicating(None),
                 rows_of_height([("5,000 m", COMMANDER)], 2)]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a branch answering nothing read
        alike, so the fixtures are checked before anything is concluded from
        them: each has a ship UI and exactly one overview row, and the
        indication says what it was built to say."""
        self.assertEqual(
            self.repl.evaluate(
                ["(idle |> Maybe.andThen .shipUI) /= Nothing",
                 "(idle |> Maybe.map (.overviewWindows"
                 " >> List.concatMap .entries >> List.length)) == Just 1",
                 "(idle |> Maybe.andThen .shipUI |> Maybe.andThen .indication"
                 " |> Maybe.andThen .maneuverType) == Nothing",
                 "(approaching |> Maybe.andThen .shipUI"
                 " |> Maybe.andThen .indication |> Maybe.andThen .maneuverType)"
                 " == Just EveOnline.ParseUserInterface.ManeuverApproach",
                 "(orbiting |> Maybe.andThen .shipUI"
                 " |> Maybe.andThen .indication |> Maybe.andThen .maneuverType)"
                 " == Just EveOnline.ParseUserInterface.ManeuverOrbit"],
                definitions=self.definitions),
            [True, True, True, True, True])

    def test_the_approach_presses_no_key_at_all(self):
        """The whole of #387: the approach dispatches no keystroke.

        A `Q` that inherits the session's Fn bit is macOS Quick Note, and the
        recorded saxrat run that took the equivalent branch 1,571 times fronted
        Notes 241 times with nobody at the machine.
        """
        self.assertEqual(
            self.repl.evaluate(["keysIn (effectsFor ensureShipIsApproaching"
                                " idle) == []"],
                               definitions=self.definitions),
            [True])

    def test_the_approach_dispatches_a_double_click(self):
        """Two press/release pairs with nothing between them, and the move.

        That exact shape is what `botlab_host.py` collapses into `cg_input`'s
        dedicated `doubleclick` command, which exists because macOS only reads
        the second press as a double click when it carries
        `kCGMouseEventClickState = 2`. A single click here would be dispatched
        happily and would do nothing.
        """
        x, y = row_center(0)
        self.assertEqual(
            self.repl.evaluate(
                ["effectsFor ensureShipIsApproaching idle"
                 " == doubleClickAt %d %d" % (x, y)],
                definitions=self.definitions),
            [True])

    def test_the_clients_own_word_is_the_only_thing_that_stops_the_ask(self):
        """The confirmation, and it is the client's own manoeuvre indication
        rather than a click having been dispatched. A ship the client says is
        orbiting is not approaching, so the ask goes on."""
        self.assertEqual(
            self.repl.evaluate(
                ["approachFor approaching == Nothing",
                 "approachFor idle /= Nothing",
                 "approachFor orbiting /= Nothing"],
                definitions=self.definitions),
            [True, True, True])

    def test_a_row_too_small_to_click_declines_out_loud(self):
        """The regression the port had to avoid rather than a property it adds.

        `mouseDoubleClickOnUIElement` answers `Err ()` for a row whose visible
        region is under four pixels, and that reaches
        `approachTheFleetCommander` as an `Err` that prints its reason and
        spends the reading. A branch that says "Approach." over an empty effect
        list is this repo's signature failure, and it would be a total one here
        where the chord at least still sent `Q`.
        """
        answer = self.repl.strings(
            ["saidBy ensureShipIsApproaching tiny",
             "saidBy ensureShipIsApproaching idle"],
            definitions=self.definitions)
        self.assertIn("DECLINED", answer[0])
        self.assertIn("too small to click", answer[0])
        self.assertNotIn("too small to click", answer[1])

    def test_a_row_too_small_to_click_dispatches_nothing(self):
        """Saying so and then clicking anyway would be the other failure. This
        one cannot tell a decline from an empty effect list -- which is why the
        case above exists."""
        self.assertEqual(
            self.repl.evaluate(
                ["effectsFor ensureShipIsApproaching tiny == []",
                 "effectsFor ensureShipIsApproaching idle /= []"],
                definitions=self.definitions),
            [True, True])

    def test_the_orbit_now_goes_through_the_panel_instead(self):
        """#414, and the reason the chord case above it is gone.

        `orbit-in-combat` held `W` over a click on the overview row until
        #414 -- a gesture aimed at a position, on a list the client reorders
        between one reading and the next. It selects the row and presses the
        panel's own Orbit now, which is a source read here because
        `ensureShipIsOrbiting` takes a whole `BotDecisionContext`; the rule
        itself is executed in `test_selected_item_panel_manoeuvres`.
        """
        orbit = block_of(WINGMAN_BOT_ELM, "\nensureShipIsOrbiting =")
        self.assertIn("commandManoeuvreFromSelectedItemPanel", orbit)
        self.assertIn("selectedItemOrbitButton", orbit)
        self.assertIsNone(re.search(r"vkey_\w+", orbit))


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
        """`ensureShipIsApproaching` is where the gesture lives. Nothing posts
        a key code directly from the arm."""
        body = self.body_of("approachTheFleetCommander context shipUI =")
        self.assertIn("ensureShipIsApproaching shipUI", body)
        self.assertIsNone(re.search(r"vkey_\w+", body))

    def test_neither_manoeuvre_posts_a_chord_any_more(self):
        """The needle is the qualified name, so it matches an effect and not
        the paragraphs in either doc comment that explain why the chords are
        gone.

        `Q` went in #387 and `W` in #414, and with it
        `commandManeuverByModifierClick`, whose only caller the orbit had
        become. A posted key carries whatever modifier state the session
        happens to hold, which is what both changes removed this bot's last
        dependence on.
        """
        for chord in ("vkey_Q", "vkey_W", "vkey_E"):
            with self.subTest(chord=chord):
                self.assertEqual(
                    re.findall(r"EffectOnWindow\.%s\b" % chord, self.source),
                    [])
        self.assertNotIn("commandManeuverByModifierClick", self.source)

    def test_the_approach_double_clicks_and_the_orbit_presses_the_panel(self):
        """The two manoeuvres came from one helper until #387 and no longer do.

        An approach that presses no key did not fit an argument list whose
        first field is a key, so `ensureShipIsApproaching` became its own
        function; #414 then moved the orbit onto the Selected Item panel, which
        left `commandManeuverByModifierClick` with no callers at all. Both
        halves are asserted, because a bot that dropped one of them would still
        satisfy a case that only looked at the other.
        """
        orbit = self.body_of("ensureShipIsOrbiting =")
        self.assertIn("commandManoeuvreFromSelectedItemPanel", orbit)
        self.assertIn("selectedItemOrbitButton", orbit)
        self.assertIn("EveOnline.ParseUserInterface.ManeuverOrbit", orbit)
        self.assertIsNone(re.search(r"vkey_\w+", orbit))

        approach = self.body_of(
            "ensureShipIsApproaching shipUI overviewEntry =")
        self.assertIn("mouseDoubleClickOnUIElement MouseButtonLeft", approach)
        self.assertIn(
            "EveOnline.ParseUserInterface.ManeuverApproach", approach)
        self.assertIsNone(re.search(r"vkey_\w+", approach))

    def test_the_double_click_is_the_frameworks_and_not_a_local_copy(self):
        """Ported from `eve-online-saxrat`, byte-identical, rather than a
        second hand-written gesture. Three of the six apps had
        `mouseDoubleClickOnUIElement` and this one did not, which is the whole
        reason #384 reinvented an approach instead of reusing one."""
        self.assertIn("mouseDoubleClickOnUIElement", self.source)
        self.assertNotIn("effectsMouseDoubleClickAtLocation", self.source)
        for relative_path, needle in (
                (os.path.join("Common", "EffectOnWindow.elm"),
                 "{-| A double click:"),
                (os.path.join("EveOnline", "BotFramework.elm"),
                 "mouseDoubleClickOnUIElement :")):
            with self.subTest(file=relative_path):
                self.assertEqual(
                    block_of(os.path.join(WINGMAN_DIR, relative_path), needle),
                    block_of(os.path.join(SAXRAT_DIR, relative_path), needle))

    def test_the_row_is_selected_before_the_panel_button_is_pressed(self):
        """The orbit's own shape since #414, and the order is load-bearing.

        The panel acts on whatever is *selected*, so pressing first would orbit
        whatever the panel happened to be showing. This replaces the case that
        pinned the chord's down/click/up ordering, which pinned the same
        property of the mechanism this one replaced.
        """
        body = self.body_of(
            "commandManoeuvreFromSelectedItemPanel command context shipUI"
            " overviewEntry =")
        select = body.index("SelectTheRowFirst ->")
        press = body.index("PressThePanelButton ->")
        self.assertLess(select, press)
        self.assertIn("overviewEntry.uiNode", body[select:press])
        self.assertNotIn("overviewEntry.uiNode",
                         body[press:body.index("WaitForThePanelButton ->")])

    def test_only_the_clients_own_word_counts_as_success(self):
        """A dispatched click is not a manoeuvre. This is the whole reason a
        gesture that turns out not to work is visible rather than silent.

        Read from each function's body rather than from the file, because the
        doc comments above both say this in words and a needle allowed to reach
        them would find the property in a bot that had dropped it.
        """
        approach = self.body_of(
            "ensureShipIsApproaching shipUI overviewEntry =")
        self.assertIn(
            "== Just EveOnline.ParseUserInterface.ManeuverApproach", approach)
        orbit = self.body_of(
            "commandManoeuvreFromSelectedItemPanel command context shipUI"
            " overviewEntry =")
        self.assertIn(".maneuverType) == Just command.maneuver", orbit)
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
             "selectedItemWarpTo", "selectedItemApproach",
             # #414's own live pass, five readings alongside a running saxrat.
             "selectedItemOrbit", "selectedItemUnLockTarget"})
        # The one of the six a guess gets wrong: `selectedItemUnLockTarget`
        # carries a capital `L` its Lock sibling does not, and the lower-case
        # spelling matches nothing while reading exactly like an object that is
        # not locked.
        self.assertNotIn("selectedItemUnlockTarget", names)


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
    version required `ApproachByDoubleClick` and `CloseAWindowLeftOverTheClient`
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

    ADVANCES = ("ApproachByDoubleClick", "SelectTheCommandersRow",
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
        every answer the arm can give between the double click's bound and the
        total bound advances the counter, so the total bound is reachable
        rather than decorative (#34)."""
        reachable = [
            "List.member (%s) approachFleetCommanderAnswersThatSpendAReading"
            % step(panel_shows=shows, panel_offers=offers,
                   asked=DOUBLE_CLICK_BOUND)
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
                          "edit_qty",
                          "ok_dialog_button"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.source)

    def test_the_panels_orbit_button_is_pressed_and_never_right_clicked(self):
        """#414 introduced `selectedItemOrbit`, which this case used to forbid.

        The name alone was the wrong thing to forbid and forbidding it is no
        longer possible: the orbit is commanded by *left*-clicking that button,
        which uses whatever default the client already holds. What opens the
        modal is a **right** click on it, so that is what is refused -- and the
        two are different effects rather than different spellings.

        The left-ness is asserted where it is written rather than in this body,
        because the body names a helper: `clickUiElementOrSayItCannotBeClicked`
        is the one #414 added, and it is left by construction. Asserting the
        helper's name alone would pass for a helper that had been changed to
        right-click, so both halves are read.
        """
        press = block_of(WINGMAN_BOT_ELM,
                         "\ncommandManoeuvreFromSelectedItemPanel command")
        self.assertIn("clickUiElementOrSayItCannotBeClicked", press)
        helper = block_of(WINGMAN_BOT_ELM,
                          "\nclickUiElementOrSayItCannotBeClicked uiElement =")
        self.assertIn("MouseButtonLeft", helper)
        self.assertNotIn("MouseButtonRight", helper)
        for cascade in ("useContextMenuCascade", "MouseButtonRight",
                        "useMenuEntryWithTextContaining"):
            with self.subTest(forbidden=cascade):
                self.assertNotIn(cascade, press)

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
        close = close[:close.index("ApproachByDoubleClick ->")]
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
