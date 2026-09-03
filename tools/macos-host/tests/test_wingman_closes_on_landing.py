"""Tests for the wingman closing on its fleet commander the moment it lands.

Issue #397. `approachTheFleetCommander` was the last arm of
`wingmanDecisionRootInSpaceOrdinary`, and the root's own comment above
`retreatToTheCommander` already says why that is fatal for anything under the
fighting arms: each of them answers `Just` for the whole of a fight and the
first arm to answer ends the reading -- the broadcast banner does not clear
while a target is called (#360), the drone arm answers on every reading a drone
idles (#326), and the guns answer on every reading a weapon is not cycling. So
on any grid worth landing on the approach was unreachable, and the ship landed
at range, opened fire and never closed. A wingman at range on its own is
outside logistics and outside support, and the operator's framing is that
failing to close is what gets the ship killed.

**What ships is a window rather than a hoist**, and the difference is the whole
of the design. A permanent hoist means the ship never fights while the
commander is on grid and unapproached, which inverts the problem. From the
reading the warp ends (`warpJustEnded`, the corrected trigger of #194 / #205)
until the client names the manoeuvre `Approach`, closing outranks the fight;
after that the arm keeps the place it has always had and the existing order
applies unchanged.

**The window is sized by what ends it and not by a number.** That is #194's own
history read as a warning: its arrival window was first sized by guesswork and
the corpus later contradicted it by a wide margin. Here the closing condition is
`shipIsApproachingFromReading` -- the client's own word, the same read that
already stops the ask -- so there is no number to be wrong about. What bounds an
open window that nothing ever closes is the arm's own
`approachFleetCommanderAskedReadingsBound`, which is not a new number either:
only the five answers in `approachFleetCommanderAnswersThatSpendAReading` can
hold a reading in this arm, and those are exactly the answers the counter
advances on, so the fight can be outranked for at most that many readings.

**The landing close does not depend on `orbit-fc`.** That is a behaviour change
for every existing settings string, including one that switched the key off
deliberately, and it is intended rather than incidental: a survival behaviour is
not opt-in. The key goes on governing the steady-state station-keeping it was
written for, on every reading after the client reports the manoeuvre.

Confirmed by mutation, **twenty** of them, run against this file and each
failing at least one named case. The cases named are the ones each mutation
actually broke, taken from the run rather than predicted:

 1. **the hoist made permanent** -- `closeOnTheCommanderAfterLanding` answering
    `approachTheFleetCommander` unconditionally, which is the inversion this
    whole design refuses. Fails
    `test_the_fight_gets_the_reading_once_the_window_is_shut` (the control),
    `test_the_hoisted_arm_declines_outside_the_window` and
    `test_the_window_changes_when_not_what`;
 2. **the window never closing** -- the `shipIsApproaching` clause dropped from
    `landingCloseAfterReading` -- fails
    `test_the_clients_own_word_closes_the_window`,
    `test_the_window_closes_on_the_reading_the_client_names_the_manoeuvre` and
    `test_a_landing_that_already_reads_approaching_opens_nothing`;
 3. **the setting still gating the landing close** --
    `approachFleetCommanderIsAsked` reduced to `ask.settingIsYes` -- fails
    `test_the_landing_close_ignores_the_setting`,
    `test_the_step_rule_asks_with_the_setting_off`,
    `test_the_root_closes_with_the_setting_off` and
    `test_the_give_up_hands_the_reading_back_inside_the_window`;
 4. **the counter advanced from state alone** -- the memory update handed
    `context.botSettings.orbitFleetCommander == PromptParser.Yes` instead of the
    shared rule, so with `orbit-fc=no` the decision asks while the counter
    believes the ask is off and the bound is unreachable during the very window
    it bounds (#34's shape). Fails
    `test_the_counter_is_advanced_through_the_same_asked_rule` and
    `test_the_counter_reads_this_readings_window`;
 5. **the close placed above the retreat** -- fails
    `test_the_close_is_below_the_two_arms_that_take_the_ship_off_the_grid`,
    `test_the_retreat_is_still_the_second_arm_in_the_root` and
    `test_the_close_is_below_the_bounded_safety_arms`;
 6. the counter reading `botMemoryBefore`'s window rather than this reading's
    answer, so it runs a reading behind the decision --
    `test_the_counter_reads_this_readings_window`;
 7. the window opened on any reading rather than on the warp ending -- fails
    `test_only_a_warp_ending_opens_the_window`,
    `test_a_session_that_never_landed_is_never_in_the_window` and
    `test_the_window_closes_on_the_reading_the_client_names_the_manoeuvre`;
 8. the confirmation asked after the opening, so a landing that already reads
    `Approach` opens a window --
    `test_a_landing_that_already_reads_approaching_opens_nothing`;
 9. the window latched on at session start --
    `test_a_session_that_never_landed_is_never_in_the_window`;
10. the hoisted arm given a branch of its own rather than calling
    `approachTheFleetCommander` -- fails `test_the_window_changes_when_not_what`
    and `test_the_client_naming_the_manoeuvre_ends_the_close`, the second being
    the confirmation the arm owns and a private branch would not honour;
11. the close placed above `unlockFleetPilotInTargetBar` --
    `test_the_close_is_below_the_bounded_safety_arms`;
12. the hoisted call site neutralised, so the arm is reachable only where it
    always was -- fails `test_the_close_outranks_the_three_arms_that_hold_a_fight`,
    `test_the_close_takes_the_reading_inside_the_window`,
    `test_the_root_closes_with_the_setting_off` and both placement cases;
13. the fall-through call site removed, so the arm is reachable only inside the
    window -- `test_the_arm_keeps_its_own_place_below_the_fight`;
14. `approachFleetCommanderAnswersThatSpendAReading` losing an entry, which is
    what makes the arm's bound the hoist's bound --
    `test_every_answer_that_can_hold_a_reading_is_counted`;
15. the give-up counted as holding a reading, which would make the hoist
    unbounded -- `test_the_answers_that_hand_the_reading_back_are_not_counted`;
16. the status clause dropped -- `test_the_window_is_visible_on_every_reading`;
17. the arm reading the setting directly instead of the shared rule -- fails
    `test_the_arm_asks_the_shared_rule_rather_than_the_setting` and
    `test_the_root_closes_with_the_setting_off`;
18. the `orbit-fc=no` status wording put back to a bare `off`, which would tell
    an operator the bot never closes --
    `test_the_status_line_says_the_close_is_not_governed_by_the_key`;
19. **`warpJustEnded` reverted to the dead `shipIsWarping == Just False` shape**
    #205 fixed, which would make the window un-openable while every other case
    here went on passing -- `test_the_trigger_is_the_corrected_one`;
20. the bound written as a bare `40` -- `test_the_bound_is_the_arms_own_and_not_a_new_number`.

**Mutation 20 survived the first pass and the hole was real.** That case
asserted `bound == doubleClickBound + weaponsAskedReadingsBound`, which `40`
satisfies exactly as the sum does -- so a bound written as a number passed a
case written to keep it written as a relation. The form is read out of the
source beside the value now.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_engages_the_called_target import (  # noqa: E402
    overview_window, target_bar)
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    COMMANDER, HEADER_LABELS, MEMBER_ROW, fleet_window, label, node,
    reading_binding)
from test_saxrat_ported_guards import ship_ui  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# A rat, so the locked target the fight arm needs is not a fleet pilot and not
# anybody the friendly-fire guard has to hold the trigger for.
RAT = "Centii Devourer"


def ship_ui_indicating(maneuver):
    """A `ShipUI` the real parser accepts, carrying a manoeuvre indication.

    `parseShipUIIndication` reads the manoeuvre out of the display texts under
    a node whose name contains `indicationcontainer`, so this is the client's
    own channel rather than a field set by hand. `None` leaves the indication
    absent, which is what the captured warp-end reading looks like -- see
    `warpJustEnded`'s own doc comment, which is why the trigger cannot ask for
    `Just False`.

    Four module slots, because `fireOnActiveTarget` needs an inactive weapon to
    have anything to do -- it is the control this file's root cases turn on.
    """
    ship = ship_ui(100, 100, 4)
    if maneuver is not None:
        ship["children"].append(
            node("Container", {"_name": "indicationContainer"},
                 [label(maneuver, (100, 100, 80, 16))],
                 region=(100, 100, 80, 16)))
    return ship


def grid(maneuver):
    """The grid this file's root cases are decided on.

    The commander is in the fleet window's header and on the overview, so the
    approach has a row to click; a rat is locked and a weapon is idle, so the
    guns have something to do. Both arms therefore answer on every one of these
    readings, and what separates the two cases below is the window and nothing
    else.
    """
    return [
        fleet_window(HEADER_LABELS, [MEMBER_ROW]),
        overview_window([(COMMANDER, "22 km", False), (RAT, "14 km", True)]),
        target_bar([[RAT, "14 km"]]),
        ship_ui_indicating(maneuver),
    ]


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running the root costs.

    Every field of the context is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide the answer except the reading and the
    one memory field under test -- `test_wingman_engages_the_called_target`'s
    arrangement, for its reason.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.DecisionPath",
        "import Common.PromptParser",
    )

    BINDINGS = (
        "contextWith = \\closing settings parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = { initBotMemory | closingOnTheCommanderSinceLanding = closing }"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "stationKeepingOff ="
        " { defaultBotSettings | orbitFleetCommander = Common.PromptParser.No }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describePath = \\path ->"
        ' unpack path |> Tuple.first |> String.join " | "',
        # The whole in-space root below the two arms that take the ship off the
        # grid, run for real. `Nothing` for the ship UI is reported rather than
        # swallowed, since a fixture that never parsed and a root that decided
        # nothing would otherwise read alike.
        "rootFor = \\closing settings parsed ->"
        " parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map"
        " (\\s -> describePath"
        " (wingmanDecisionRootInSpaceOrdinary (contextWith closing settings p) s)))"
        ' |> Maybe.withDefault "NO SHIP UI"',
        "approachArmFor = \\closing settings parsed ->"
        " parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.andThen"
        " (\\s -> closeOnTheCommanderAfterLanding"
        " (contextWith closing settings p) s))",
        "statusFor = \\closing settings parsed ->"
        " parsed |> Maybe.map"
        " (\\p -> describeApproachFleetCommanderAsk"
        " (contextWith closing settings p))"
        ' |> Maybe.withDefault "NO READING"',
        # The window, folded over a session rather than asked once: a rule that
        # is right for one reading and wrong across a run is the defect this
        # shape prevents.
        "foldWindow = \\start steps -> List.foldl"
        " (\\step owed -> landingCloseAfterReading"
        " { closeWasOwed = owed"
        " , justLanded = Tuple.first step"
        " , shipIsApproaching = Tuple.second step })"
        " start steps",
        "window = \\owed landed approaching -> landingCloseAfterReading"
        " { closeWasOwed = owed"
        " , justLanded = landed"
        " , shipIsApproaching = approaching }",
        "asked = \\setting closing -> approachFleetCommanderIsAsked"
        " { settingIsYes = setting, closingSinceLanding = closing }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-landing-close-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def step(setting_is_yes=True, closing=False, commander_on_grid=True,
         warping=False, approaching=False, stray_window=False,
         stray_window_closable=True, panel_shows=False, panel_offers=False,
         asked=0):
    """The shipped step rule, asked through the shipped "is it asked" rule.

    The two are spelled together here because that is how all three readers
    reach them -- the arm, the memory update and the status clause -- so a case
    that asked `approachFleetCommanderStep` with a bare boolean would be asking
    something no shipped caller asks.

    `stray_window_closable` defaults to `True` so that every case in this file
    goes on asking what it asked before #433: the hoist is about which arm gets
    the reading, and a window this bot cannot press is that arm declining --
    which `test_wingman_unclosable_window` is where it is asked about.
    """
    return ("approachFleetCommanderStep { settingIsYes ="
            " approachFleetCommanderIsAsked { settingIsYes = %s"
            ", closingSinceLanding = %s }"
            ", commanderOnGrid = %s"
            ", shipIsWarpingOrJumping = %s"
            ", shipIsApproaching = %s"
            ", strayWindowIsOpen = %s"
            ", strayWindowCanBeClosed = %s"
            ", panelShowsTheCommander = %s"
            ", panelOffersApproach = %s"
            ", askedReadings = %s }"
            % (setting_is_yes, closing, commander_on_grid, warping,
               approaching, stray_window, stray_window_closable, panel_shows,
               panel_offers, asked))


def elm_bool(value):
    return "True" if value else "False"


def pairs(steps):
    """`[(landed, approaching), ...]` as an Elm list of tuples."""
    return "[ %s ]" % ", ".join(
        "( %s, %s )" % (elm_bool(landed), elm_bool(approaching))
        for landed, approaching in steps)


def collapsed(text):
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, from its definition to the blank line pair.

    Doc comments are stripped, so a case cannot pass on prose -- which is what
    a plain substring over a block whose comment quotes the name it forbids
    would do.
    """
    needle = "\n%s" % name
    assert needle in source, "no declaration named %r" % name
    start = source.index(needle) + 1
    body = source[start:source.index("\n\n\n", start)]
    return re.sub(r"--[^\n]*", "", body)


def indented_let_binding(source, name):
    """One `let` binding, sliced by indentation rather than by the next name.

    A reader that ends at the next ` <name> = ` stops at a record literal, and
    the bindings read here build records -- PRs #147, #156, #159 and #162 each
    paid for that once with an assertion that passed having read nothing.
    """
    match = re.search(r"\n(\s+)%s =\n" % re.escape(name), source)
    assert match is not None, "no let binding named %r" % name
    indent = len(match.group(1))
    lines = source[match.end():].split("\n")
    kept = []
    for line in lines:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        kept.append(line)
    return re.sub(r"--[^\n]*", "", "\n".join(kept))


class TheLandingWindowTest(unittest.TestCase):
    """What opens the window and what closes it, executed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_only_a_warp_ending_opens_the_window(self):
        """`warpJustEnded` and nothing else. A reading that is neither a
        landing nor a confirmation leaves a shut window shut, which is what
        keeps this from being a hoist that fires whenever the ship is near the
        commander."""
        self.assertEqual(
            self.repl.evaluate([
                "window False True False == True",
                "window False False False == False",
            ]),
            [True, True])

    def test_the_clients_own_word_closes_the_window(self):
        """`shipIsApproachingFromReading` is the same `ManeuverApproach` read
        that already stops the ask, so a dispatched click still never counts as
        a manoeuvre -- the property `approachTheFleetCommander` was built on
        and the one this must not weaken."""
        self.assertEqual(
            self.repl.evaluate([
                "window True False True == False",
                "window True False False == True",
            ]),
            [True, True])

    def test_a_landing_that_already_reads_approaching_opens_nothing(self):
        """The confirmation is asked before the opening. A ship that lands
        already approaching has nothing for this window to buy, and opening one
        would outrank the fight on a reading the client had already answered."""
        self.assertEqual(
            self.repl.evaluate(["window False True True == False"]),
            [True])

    def test_the_window_holds_across_a_grid_that_says_nothing(self):
        """Folded over a session rather than asked once. A landing followed by
        readings the client says nothing on -- which is the ordinary case while
        a double click is being retried -- keeps the window open."""
        self.assertEqual(
            self.repl.evaluate([
                "foldWindow False %s == True"
                % pairs([(True, False)] + [(False, False)] * 12),
            ]),
            [True])

    def test_the_window_closes_on_the_reading_the_client_names_the_manoeuvre(
            self):
        """And stays shut for the rest of that grid, so the fight gets every
        reading after it."""
        self.assertEqual(
            self.repl.evaluate([
                "foldWindow False %s == False"
                % pairs([(True, False), (False, False), (False, True)]),
                "foldWindow False %s == False"
                % pairs([(True, False), (False, True)]
                        + [(False, False)] * 20),
            ]),
            [True, True])

    def test_a_second_landing_opens_it_again(self):
        """A window that closed on one grid must open on the next one, since
        the ship lands at range again every time it warps."""
        self.assertEqual(
            self.repl.evaluate([
                "foldWindow False %s == True"
                % pairs([(True, False), (False, True), (False, False),
                         (True, False), (False, False)]),
            ]),
            [True])

    def test_a_session_that_never_landed_is_never_in_the_window(self):
        """`initBotMemory` starts it shut, so a bot that begins already on grid
        has no landing to close from -- `arrivalWindowIsOpen`'s posture, and
        the conservative direction. Executed against the shipped initial memory
        rather than against a literal."""
        self.assertEqual(
            self.repl.evaluate([
                "initBotMemory.closingOnTheCommanderSinceLanding == False",
                "foldWindow initBotMemory.closingOnTheCommanderSinceLanding %s"
                " == False" % pairs([(False, False)] * 30),
            ]),
            [True, True])


class TheLandingCloseIgnoresTheSettingTest(unittest.TestCase):
    """`orbit-fc` governs station-keeping and not the close on landing.

    Stated as a behaviour change rather than as a tidy-up: an operator who
    switched the key off gets a bot that now closes on landing, which is the
    intended outcome and not a side effect.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_landing_close_ignores_the_setting(self):
        """All four combinations, so a rule that answers the setting alone and
        one that answers the window alone both fail."""
        self.assertEqual(
            self.repl.evaluate([
                "asked True True == True",
                "asked True False == True",
                "asked False True == True",
                "asked False False == False",
            ]),
            [True] * 4)

    def test_the_step_rule_asks_with_the_setting_off(self):
        """The rule the arm, the counter and the status line all reach through.
        With the key off and the window open the ask goes out; with the key off
        and the window shut it is off, which is the behaviour every reading
        after the confirmation keeps."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ApproachByDoubleClick"
                % step(setting_is_yes=False, closing=True),
                "%s == ApproachFleetCommanderIsOff"
                % step(setting_is_yes=False, closing=False),
            ]),
            [True, True])

    def test_the_setting_still_governs_station_keeping(self):
        """The half that does not change: with the window shut, `orbit-fc=yes`
        still keeps station and `orbit-fc=no` still does not."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ApproachByDoubleClick"
                % step(setting_is_yes=True, closing=False),
            ]),
            [True])

    def test_the_status_line_says_the_close_is_not_governed_by_the_key(self):
        """An operator reading `off` about a key that no longer decides the
        landing close would conclude the bot never closes. Rendered rather than
        asserted by substring over the branch."""
        answer = self.repl.strings(
            ["statusFor False stationKeepingOff onGrid"],
            definitions=[reading_binding("onGrid", grid(None))])[0]
        self.assertIn("orbit-fc=no", answer)
        self.assertIn("close on landing", answer)
        self.assertIn("NOT governed", answer)


class TheDecisionRootClosesBeforeItFightsTest(unittest.TestCase):
    """The whole point, executed through the real root.

    Two contexts differing in one memory field, over the **same** reading: a
    grid with the commander on the overview and a rat locked, so the approach
    and the guns both have something to do and only the window separates them.

    `test_the_fight_gets_the_reading_once_the_window_is_shut` is the control
    this file turns on -- it is the fall-through shape
    `test_the_arm_answers_nothing_so_the_guns_below_it_are_reachable` uses next
    door, and without it a root that answered the approach on every reading
    would pass every other case here.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("onGrid", grid(None)),
            reading_binding("readsApproaching", grid("Approach")),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a root that decided nothing read
        alike, so what the parser made of each fixture is checked first."""
        self.assertEqual(
            self.repl.evaluate([
                "onGrid /= Nothing",
                "(onGrid |> Maybe.andThen .shipUI) /= Nothing",
                "(onGrid |> Maybe.map (.targets >> List.length)) == Just 1",
                "(onGrid |> Maybe.map (.overviewWindows"
                " >> List.concatMap .entries >> List.length)) == Just 2",
                '(onGrid |> Maybe.andThen'
                ' fleetCommanderNameFromFleetWindowHeader) == Just "%s"'
                % COMMANDER,
                "(onGrid |> Maybe.map shipIsApproachingFromReading)"
                " == Just False",
                "(readsApproaching |> Maybe.map shipIsApproachingFromReading)"
                " == Just True",
            ], definitions=self.definitions),
            [True] * 7)

    def test_the_close_takes_the_reading_inside_the_window(self):
        """The defect, fixed: on a grid where the fight would otherwise answer,
        the reading goes to the approach."""
        answer = self.repl.strings(
            ["rootFor True defaultBotSettings onGrid"],
            definitions=self.definitions)[0]
        self.assertIn("Approach the fleet commander", answer)

    def test_the_fight_gets_the_reading_once_the_window_is_shut(self):
        """The control, and the half a permanent hoist would break. The same
        reading with the window shut reaches an arm below -- so the arms this
        change moves the close above are still reachable, which is the property
        #326 established and this must not spend."""
        answer = self.repl.strings(
            ["rootFor False defaultBotSettings onGrid"],
            definitions=self.definitions)[0]
        self.assertNotIn("Approach the fleet commander", answer)
        self.assertTrue(answer.strip(),
                        "the root decided nothing at all: %r" % answer)

    def test_the_root_closes_with_the_setting_off(self):
        """`orbit-fc=no` and a window open: the close still happens, which is
        the behaviour change stated rather than slipped in."""
        answers = self.repl.strings([
            "rootFor True stationKeepingOff onGrid",
            "rootFor False stationKeepingOff onGrid",
        ], definitions=self.definitions)
        self.assertIn("Approach the fleet commander", answers[0])
        self.assertNotIn("Approach the fleet commander", answers[1])

    def test_the_client_naming_the_manoeuvre_ends_the_close(self):
        """Even with the window flag still set, a reading on which the client
        says the ship is approaching hands the tree back -- the confirmation is
        the arm's, so the window cannot outlive it by one reading."""
        self.assertEqual(
            self.repl.evaluate([
                "approachArmFor True defaultBotSettings readsApproaching"
                " == Nothing",
                "approachArmFor True defaultBotSettings onGrid /= Nothing",
            ], definitions=self.definitions),
            [True, True])

    def test_the_hoisted_arm_declines_outside_the_window(self):
        """The gate itself, so a window that never opens costs the bot exactly
        the behaviour it had before this change."""
        self.assertEqual(
            self.repl.evaluate([
                "approachArmFor False defaultBotSettings onGrid == Nothing",
            ], definitions=self.definitions),
            [True])

    def test_the_window_is_visible_on_every_reading(self):
        """From outside the tree a reading in which the approach outranked the
        fight and one in which it merely came last read identically, and the
        window is the whole change."""
        answers = self.repl.strings([
            "statusFor True defaultBotSettings onGrid",
            "statusFor False defaultBotSettings onGrid",
        ], definitions=self.definitions)
        self.assertIn("CLOSING SINCE LANDING", answers[0])
        self.assertNotIn("CLOSING SINCE LANDING", answers[1])


class TheHoistIsBoundedTest(unittest.TestCase):
    """What stops the close outranking the fight for ever.

    Not a clock: the arm's own `approachFleetCommanderAskedReadingsBound`. Only
    the answers in `approachFleetCommanderAnswersThatSpendAReading` can hold a
    reading here, and those are exactly the answers the counter advances on --
    so a window nothing ever closes costs the fight that many readings and no
    more. A case that only asserted the window's closing condition would say
    nothing about the case the window never closes in, which is the one that
    matters.

    **#433 narrows what the hoist can cost rather than widening it.** A window
    this bot cannot press the close button of answers
    `AWindowThisBotCannotCloseIsOpen`, which hands the reading back, so it
    joins the list below rather than the one above -- the fight gets those
    readings where before it got a decision line over an empty effect list.
    """

    ADVANCES = ("ApproachByDoubleClick", "SelectTheCommandersRow",
                "PressTheApproachButton", "WaitForTheApproachButton",
                "CloseAWindowLeftOverTheClient")
    HANDS_BACK = ("ApproachFleetCommanderIsOff", "NoCommanderOnGrid",
                  "ShipIsWarpingOrJumping", "AlreadyApproaching",
                  "AWindowThisBotCannotCloseIsOpen",
                  "GaveUpOnTheApproach")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_answer_that_can_hold_a_reading_is_counted(self):
        self.assertEqual(
            self.repl.evaluate([
                "List.member %s approachFleetCommanderAnswersThatSpendAReading"
                % answer for answer in self.ADVANCES]),
            [True] * len(self.ADVANCES))

    def test_the_answers_that_hand_the_reading_back_are_not_counted(self):
        """Including the give-up, which is what ends the hoist: past the bound
        the arm answers `Nothing` at both call sites and every arm below runs
        again."""
        self.assertEqual(
            self.repl.evaluate([
                "List.member %s approachFleetCommanderAnswersThatSpendAReading"
                % answer for answer in self.HANDS_BACK]),
            [False] * len(self.HANDS_BACK))

    def test_the_give_up_hands_the_reading_back_inside_the_window(self):
        """Executed at both sides of the bound, with the setting off so that
        only the window is asking: the hoist ends where the arm's budget does.

        One reading short of the bound the answer is the panel fall-back rather
        than the double click, since the first bound is long spent by then --
        which is what makes this a boundary pair over the real ladder rather
        than a pair any constant would satisfy.
        """
        self.assertEqual(
            self.repl.evaluate([
                "%s == GaveUpOnTheApproach"
                % step(setting_is_yes=False, closing=True,
                       asked="approachFleetCommanderAskedReadingsBound"),
                "%s == SelectTheCommandersRow"
                % step(setting_is_yes=False, closing=True,
                       asked="approachFleetCommanderAskedReadingsBound - 1"),
                "%s == ApproachByDoubleClick"
                % step(setting_is_yes=False, closing=True, asked=0),
                "%s == GaveUpOnTheApproach"
                % step(setting_is_yes=False, closing=True, asked=500),
            ]),
            [True] * 4)

    def test_the_bound_is_the_arms_own_and_not_a_new_number(self):
        """Written as the sum the arm already had, so a hoist bound and an ask
        bound cannot drift apart.

        **The value is asserted and so is the form**, and the second half was a
        hole the mutation matrix found: `40` satisfies
        `bound == doubleClickBound + weaponsAskedReadingsBound` exactly as the
        sum does, so a case asking only the value passes on a bound written as
        a bare number -- which is the drift this repo keeps a rule about.
        """
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            body = declaration(
                handle.read(), "approachFleetCommanderAskedReadingsBound =")
        self.assertIn("approachFleetCommanderDoubleClickAskedReadingsBound",
                      body)
        self.assertIn("weaponsAskedReadingsBound", body)
        self.assertNotIn("40", body)
        self.assertEqual(
            self.repl.evaluate([
                "approachFleetCommanderAskedReadingsBound"
                " == approachFleetCommanderDoubleClickAskedReadingsBound"
                " + weaponsAskedReadingsBound",
                "10 < approachFleetCommanderAskedReadingsBound",
            ]),
            [True, True])


class ThePlacementTest(unittest.TestCase):
    """Source-pinned, because the ordering *is* the change.

    A suite that only exercised the rules would pass on a bot whose close
    nothing could reach, which is exactly the defect #397 was filed on.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        for needle in needles:
            self.assertIn(needle, self.source)
        return [self.source.index(needle) for needle in needles]

    def test_the_close_is_below_the_two_arms_that_take_the_ship_off_the_grid(
            self):
        """#364's ordering, and it is not a trade: a ship past its threshold
        breaks off, and it does not close on anyone first."""
        ending, retreat, recover, close = self.order_of(
            "case sessionIsEnding context shipUI of",
            "case retreatToTheCommander context",
            "case recoverFromRetreat context shipUI of",
            "case closeOnTheCommanderAfterLanding context shipUI of")
        self.assertLess(ending, retreat)
        self.assertLess(retreat, recover)
        self.assertLess(recover, close)

    def test_the_retreat_is_still_the_second_arm_in_the_root(self):
        """Not merely above the close. Everything between `sessionIsEnding` and
        the retreat would be an arm that can hold a reading away from it."""
        root = self.source[self.source.index(
            "wingmanDecisionRootInSpace context shipUI ="):]
        arms = re.findall(r"case (\w+) context", root[:root.index("\n\n\n")])
        self.assertEqual(arms[:2],
                         ["sessionIsEnding", "retreatToTheCommander"])

    def test_the_close_is_below_the_bounded_safety_arms(self):
        """`unlockFleetPilotInTargetBar` is #367's, and its veto on the guns is
        independent of its placement anyway; `manageMiddleRowModules` stops
        answering the moment the hardeners are on, which is a tank worth having
        while landing at range."""
        unlock, modules, close = self.order_of(
            "case unlockFleetPilotInTargetBar context of",
            "case manageMiddleRowModules context of",
            "case closeOnTheCommanderAfterLanding context shipUI of")
        self.assertLess(unlock, modules)
        self.assertLess(modules, close)

    def test_the_close_outranks_the_three_arms_that_hold_a_fight(self):
        """The whole change. Each of these answers `Just` for the whole of a
        fight, which is what made the arm unreachable at the foot of the
        list."""
        close, broadcast, drones, guns = self.order_of(
            "case closeOnTheCommanderAfterLanding context shipUI of",
            "case actOnFleetBroadcast context shipUI of",
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of")
        self.assertLess(close, broadcast)
        self.assertLess(broadcast, drones)
        self.assertLess(drones, guns)

    def test_the_arm_keeps_its_own_place_below_the_fight(self):
        """The window changes *when* the step is taken, never what it is -- so
        the fall-through call site stays where #365 put it, below the guns and
        above the gate, and station-keeping outside the window is unchanged."""
        guns, arm, gate = self.order_of(
            "case fireOnActiveTarget context of",
            "case approachTheFleetCommander context shipUI of",
            "case accelerationGateStep context of")
        self.assertLess(guns, arm)
        self.assertLess(arm, gate)

    def test_the_window_changes_when_not_what(self):
        """The hoisted branch calls the arm rather than carrying a second copy
        of it, so every guarantee the ask already made -- the double click
        first, the panel fall-back behind it, the stray window closed before
        asking again, the client's own word as the only confirmation -- holds
        inside the window without being restated."""
        body = declaration(
            self.source, "closeOnTheCommanderAfterLanding context shipUI =")
        self.assertIn("approachTheFleetCommander context shipUI", body)
        self.assertIn("closingOnTheCommanderSinceLanding", body)
        for forbidden in ("useContextMenuCascade", "clickUiElementForNavigation",
                          "ensureShipIsApproaching", "describeBranch"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, body)

    def test_the_arm_asks_the_shared_rule_rather_than_the_setting(self):
        """A second notion of "the ask is on" beside the counter's is #102's
        defect, and here it is the one that makes the bound unreachable."""
        body = declaration(
            self.source, "approachTheFleetCommander context shipUI =")
        self.assertIn("approachFleetCommanderIsAsked", body)
        self.assertIn("closingOnTheCommanderSinceLanding", body)


class TheCounterIsAdvancedFromTheSameRuleTest(unittest.TestCase):
    """#102 and #34, which meet here.

    The counter has to advance on the readings the decision asks on, and inside
    the window with `orbit-fc=no` those readings exist only because of the
    window. A counter advanced from the setting alone would leave
    `approachFleetCommanderAskedReadingsBound` unreachable during the very
    window it bounds.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()
        cls.update = declaration(
            cls.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =")

    def test_the_counter_is_advanced_through_the_same_asked_rule(self):
        """Read across the two bindings #433 split this into: the step is
        predicted once as `approachStepNow`, because that change gave the
        memory update a second thing to derive from it, and the counter's own
        binding asks the shipped list of that one answer. Both halves are named
        so a step predicted for one counter and a membership test taken against
        something else cannot pass."""
        step = indented_let_binding(self.source, "approachStepNow")
        self.assertIn("approachFleetCommanderStep", step)
        self.assertIn("approachFleetCommanderIsAsked", step)
        self.assertIn("closingSinceLanding", step)
        asking = indented_let_binding(
            self.source, "askingTheCommanderForAnApproach")
        self.assertIn(
            "approachFleetCommanderAnswersThatSpendAReading", asking)
        self.assertIn("approachStepNow", asking)

    def test_the_counter_reads_this_readings_window(self):
        """The decision reads the memory this update writes, so a counter
        reading `botMemoryBefore`'s window is a reading behind it -- and on the
        reading a window opens that is the difference between the ask being
        counted and not."""
        binding = indented_let_binding(self.source, "approachStepNow")
        self.assertIn(
            "closingSinceLanding = closingOnTheCommanderSinceLandingNow",
            collapsed(binding))
        self.assertNotIn(
            "botMemoryBefore.closingOnTheCommanderSinceLanding", binding)

    def test_the_window_is_settled_in_the_memory_update(self):
        """`warpJustEnded` is a transition between two readings, and the memory
        update is the only thing that runs on every reading unconditionally --
        #102's and #126's placement rule.

        **Superseded by the wider `weJustFinishedTraveling`.** A gate jump
        re-arms this window exactly as a warp does --
        `wingman_run22.log` recorded `shipIsApproaching` stuck on a stale
        reading for 600+ lines after a chained gate jump, because
        `weJustFinishedWarping` never fires at the end of one. See
        `test_wingman_jump_refills_the_budget.py`."""
        binding = indented_let_binding(
            self.source, "closingOnTheCommanderSinceLandingNow")
        self.assertIn("landingCloseAfterReading", binding)
        self.assertIn("justLanded = weJustFinishedTraveling", collapsed(binding))
        self.assertIn(
            "closeWasOwed = botMemoryBefore.closingOnTheCommanderSinceLanding",
            collapsed(binding))
        self.assertIn(
            "closingOnTheCommanderSinceLanding ="
            " closingOnTheCommanderSinceLandingNow",
            collapsed(self.update))

    def test_the_trigger_is_the_corrected_one(self):
        """#194 / #205: `weJustFinishedWarping` is `warpJustEnded`, which asks
        for the ship UI's presence and for this reading not being `Just True`.
        The condition it replaced -- `shipIsWarping == Just False` -- could not
        answer `True` at the end of a warp at all, which is exactly the shape
        this window would fail silently in."""
        binding = indented_let_binding(self.source, "weJustFinishedWarping")
        self.assertIn("warpJustEnded", binding)
        rule = declaration(
            self.source, "warpJustEnded { warpingLastReading, readingNow } =")
        self.assertIn("readingNow.shipUI /= Nothing", collapsed(rule))
        self.assertIn(
            "shipWarpingFromReading readingNow /= Just True", collapsed(rule))


if __name__ == "__main__":
    unittest.main()
