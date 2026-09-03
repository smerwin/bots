"""Tests for #442: prioritise getting back to the FC over every reading she is
off-grid.

Two gaps, and both were the same shape -- a mechanism that already existed and
already worked, wired to only one of its two possible callers.

## Gap 1: the off-grid warp fell straight to the slow route/ESI ask

`warpToFleetMateFromTheirFleetWindowRow` (#429) right-clicks a fleet-mate's own
fleet-window row and drives the proven `Warp to Member` cascade off it -- no
banner needed, which is the whole point: it exists for a commander who is not
broadcasting. But the only caller that ever reached it was
`recoverFromRetreat`'s `WarpToTheCommanderFromTheFleetWindow` case, reachable
only while the health retreat has latched `recoveringFromRetreat` -- and that
retreat ships switched off by default (WINGMAN.md, "The health retreat, and why
it ships switched off"). So on the common run -- retreat off, an FC who simply
flies faster than the ESI round trip -- the two ordinary broadcast forms
(`AtLocation`, `InPositionAt`) fell straight from "she is off this grid" to
`goToFleetMate`'s place-based `@host set-destination` ask on every single
reading she stayed off it, never trying the mechanism sitting right there.

`goToFleetMateOffGridPreferringTheFleetWindow` is the fix: `goToFleetMate`,
with the fleet-window warp tried first when the pilot has a row there and no
overview row. `actOnBroadcastVerb`'s two ordinary call sites are rewired to it;
`recoverFromRetreat`'s own two call sites are deliberately untouched, for the
reason in that function's own doc comment -- its `retreatRecoveryStep` already
orders the fleet-window case against its own `RouteToWhereTheCommanderLast
SaidHeWas`, and a `goToFleetMate` that silently preferred the fleet window here
would let the warp fire on a reading whose own status-line-driving
`retreatRecoveryStepNow` still claims to be routing to a remembered place --
#102's failure, a status line disagreeing with the decision.

## Gap 2: two acceleration gates refused the follow rather than guessing

`followTheCommanderThroughTheGate`'s guard 4 was "exactly one gate on the
grid" -- with two or more, nobody names which one the commander took, so the
bot refused to guess and sat on the grid instead, citing
`dockAtDestinationStation`'s "don't guess" discipline (a 2026-08-29 decision).
Live evidence since then is that refusing to guess here means stalling or
drifting from the commander on every grid that happens to carry more than one
gate -- and `nearestAccelerationGateOnOverview` already picks the nearest gate
regardless of count, for every *other* caller of it. The guard is relaxed to
"at least one gate", accepting the wrong-pocket risk explicitly rather than
refuse and stall. This gap's own dedicated file,
`test_wingman_follows_the_commander_through_a_gate.py`, carries the full
fifteen-mutation battery; what is here is the lighter check the issue's own
checklist asks this file to carry too, plus the end-to-end proof that both
gaps are reachable from the real decision root together.

## What this file adds beyond the dedicated files

Both mechanisms already had their own tests -- #429's for the fleet-window
warp cascade itself, #411's fifteen-mutation battery for the gate guard. What
neither had is a test of the *wiring*: that the ordinary broadcast path
actually tries the fleet-window warp before falling to the slow ask, that the
budget which bounds it is a real bound and not a second opinion nobody
compares against `fleetMateWarpAskedReadingsBound`, that `recoverFromRetreat`'s
own two call sites are untouched, and that both gaps are reachable together
from `wingmanDecisionRootInSpaceOrdinary` -- the real root, not an arm asked in
isolation, which is #411's own standard for what makes a fix real rather than
merely correct in a vacuum.

## Confirmed by mutation

Two, checked by hand against this file rather than carried as a battery
(the two mechanisms' own files already carry the exhaustive ones):

- **Gap 1 reverted** -- `goToFleetMateOffGridPreferringTheFleetWindow`'s body
  replaced with a bare call to `goToFleetMate` (what the wrapper degenerates to
  with the fleet-window branch removed) -- fails
  `TheOffGridDecisionTest.test_off_grid_with_a_row_warps_from_it` and
  `TheEndToEndReachabilityTest.test_the_root_reaches_the_fleet_window_warp`,
  both for the right reason: the decision falls straight to "asking the host
  for the route" instead of naming the fleet-window row.
- **Gap 2 reverted** -- `followTheCommanderThroughTheGate`'s guard put back at
  `== 1` -- fails `TheGateAmbiguityTest.test_two_or_more_gates_now_follow_too`.

## Unverified

Everything here runs through `elm repl` against the real `Bot.elm`; nothing
has been flown. What to watch on the first live run that meets an off-grid FC
with a fleet-window row is the decision log naming "warping to them from their
own row's menu" rather than "asking the host for the route", and the status
line's `Off-grid fleet-window warp:` clause showing readings climbing rather
than staying at the give-up sentence on every reading. What to watch for the
gate half is in the dedicated file.

    python3 -m unittest discover -s tools/macos-host/tests
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
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    COMMANDER, HEADER_LABELS, MEMBER_ROW, fleet_window, label,
    reading_binding)
from test_wingman_called_gate import overview, ship_ui  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

PLACE = "Amarr"
CALLED_IT = "is at location"
CALL_TEXT = "%s %s %s" % (COMMANDER, CALLED_IT, PLACE)

# A member row who is not the commander, for a fleet window that carries a
# roster but no row naming him -- what a badly-drawn or truncated fleet
# window looks like, and the shape the control case (part (c) of #442's own
# checklist) needs.
OTHER_MEMBER = MEMBER_ROW


def commander_row():
    """The commander's own overview row, undisplayed by nothing else here."""
    return (COMMANDER, "Battlecruiser", True, False)


def fleet_window_with_commander(banner_text=None):
    """The captured fleet window, the commander named in its header.

    `fleetWindowRowForPilot` searches the header labels as well as the member
    rows and finds him there -- `HEADER_LABELS`' own second entry is his name,
    which is WINGMAN.md's own capture off a live client.
    """
    window = fleet_window(HEADER_LABELS, [MEMBER_ROW])
    if banner_text is not None:
        window["children"].append(
            label(banner_text, (10, 300, 300, 16), name="bannerLabel"))
    return window


def fleet_window_without_commander(banner_text=None):
    """A fleet window with a roster and, optionally, a banner -- but no row
    (header or member) naming the commander at all.

    This is the control fixture: `fleetWindowRowForPilot` answers `Nothing`
    for him here exactly as it would for a window truncated mid-render, so
    `goToFleetMateOffGridPreferringTheFleetWindow` has nothing to try and must
    fall through to `goToFleetMate` unmodified.
    """
    window = fleet_window(["Fleet (2)", "Squad 1 (2)"], [OTHER_MEMBER])
    if banner_text is not None:
        window["children"].append(
            label(banner_text, (10, 300, 300, 16), name="bannerLabel"))
    return window


def grid(fleet_window_node, overview_rows, modules=((10, True),)):
    """A whole reading: the fleet window, the overview and a ship UI.

    The same quiet shape `test_wingman_called_gate` and the gate-follow file's
    own `grid` use -- one inactive-looking module row, no targets, no panel --
    which is what lets `wingmanDecisionRootInSpaceOrdinary` fall all the way
    through the module and backup-call arms to the broadcast arm on a fixture
    nobody built with the root in mind.
    """
    return [
        fleet_window_node,
        overview(overview_rows),
        ship_ui(modules),
    ]


# The three shapes the decision-level tests need. No banner: the decision-level
# arm is handed the pilot directly by its caller, so it never reads one -- only
# `fleetMateCallingForCompany`'s own callers (the memory update, the status
# line, the real decision root) need the banner to name the pilot themselves.
OFF_GRID_WITH_ROW = reading_binding(
    "offGridWithRow", grid(fleet_window_with_commander(), []))
OFF_GRID_NO_ROW = reading_binding(
    "offGridNoRow", grid(fleet_window_without_commander(), []))
ON_OVERVIEW = reading_binding(
    "onOverview", grid(fleet_window_with_commander(), [commander_row()]))

# The three the root/memory/status tests need, carrying the broadcast banner
# so `fleetMateCallingForCompany` can name the pilot from the reading alone.
BANNER_OFF_GRID_WITH_ROW = reading_binding(
    "bannerOffGridWithRow",
    grid(fleet_window_with_commander(CALL_TEXT), []))
BANNER_OFF_GRID_NO_ROW = reading_binding(
    "bannerOffGridNoRow",
    grid(fleet_window_without_commander(CALL_TEXT), []))
BANNER_ON_OVERVIEW = reading_binding(
    "bannerOnOverview",
    grid(fleet_window_with_commander(CALL_TEXT), [commander_row()]))

ALL_READINGS = (
    OFF_GRID_WITH_ROW, OFF_GRID_NO_ROW, ON_OVERVIEW,
    BANNER_OFF_GRID_WITH_ROW, BANNER_OFF_GRID_NO_ROW, BANNER_ON_OVERVIEW,
)


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what #442's two mechanisms cost."""

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "followingCommander ="
        ' { defaultBotSettings | followFleetBroadcastFrom = [ "%s" ] }'
        % COMMANDER,
        "contextWith = \\settings -> \\askedReadings -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory ="
        " { initBotMemory | goToFleetMateFleetWindowWarpAskedReadings = askedReadings }"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        # The decision-level arm, asked directly with the pilot/place/verb an
        # `actOnBroadcastVerb` call site would already have parsed off the
        # banner -- so this needs no banner in the fixture at all, only the
        # fleet window and overview rows for that named pilot.
        "offGridArm = \\askedReadings -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " describeArm (goToFleetMateOffGridPreferringTheFleetWindow"
        " (contextWith followingCommander askedReadings p) s"
        ' "%s" "%s" "%s")))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"'
        % (COMMANDER, PLACE, CALLED_IT),
        # The whole in-space root, run for real -- the only thing that can say
        # whether the wiring in `actOnBroadcastVerb` actually reaches this
        # mechanism rather than the arm merely answering correctly in
        # isolation. #411's own standard.
        "rootFor = \\askedReadings -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " unpack (wingmanDecisionRootInSpaceOrdinary"
        " (contextWith followingCommander askedReadings p) s)"
        ' |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "statusFor = \\askedReadings -> \\parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeFleetMateOffGridFleetWindowWarp"
        " (contextWith followingCommander askedReadings p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "stepFor = \\askedReadings -> fleetWindowWarpStep { askedReadings = askedReadings }",
        # The memory update, folded over a session of readings -- so a case
        # can put "he lands" or "his row vanishes" in the middle of a run and
        # ask what the far side of it believes, rather than asking one
        # reading at a time and trusting the arithmetic in its own head.
        "updateContext = \\reading ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = reading"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , previousStepsEffects = []"
        " , botSettings = followingCommander }",
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "memoryOver = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame (updateContext r) memory)"
        " initBotMemory",
        "counterAfter = \\pairs ->"
        " (memoryOver pairs).goToFleetMateFleetWindowWarpAskedReadings",
        # Gap 2's own light check, the pure rule with no fixture at all --
        # `test_wingman_follows_the_commander_through_a_gate.py` carries the
        # exhaustive battery this borrows the shape of.
        "follow = \\gates -> followTheCommanderThroughTheGate"
        " { presence = CommanderGoneFromTheGrid 5"
        " , accelerationGatesOnTheGrid = gates }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-offgrid-fc-pursuit-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def declaration(source, name):
    """One top-level declaration, from its definition to the blank line pair.

    Doc comments are stripped, so a case cannot pass on prose -- the same
    reader `test_wingman_landing_refills_the_budget.py` carries, copied rather
    than imported since that file's own name is not this gap's.
    """
    needle = "\n%s" % name
    assert needle in source, "no declaration named %r" % name
    start = source.index(needle) + 1
    body = source[start:source.index("\n\n\n", start)]
    return re.sub(r"--[^\n]*", "", body)


class TheFixturesArrivedTest(unittest.TestCase):
    """A fixture that never arrived and a rule that answered nothing read
    identically from outside -- #174's own trap. Every case below asks a
    string that could only come from a reading that really parsed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_reading_parsed(self):
        names = [reading.split(" =", 1)[0] for reading in ALL_READINGS]
        answers = self.repl.evaluate(
            ["%s /= Nothing" % name for name in names],
            definitions=ALL_READINGS)
        self.assertEqual(answers, [True] * len(ALL_READINGS))


class TheFleetWindowWarpStepRuleTest(unittest.TestCase):
    """The pure rule on its own -- two answers over one counter, and the
    bound it shares with the on-grid warp rather than a second one invented
    for the same shape of wait."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_bound_is_the_on_grid_warps_own(self):
        (same,) = self.repl.evaluate([
            "fleetWindowWarpAskedReadingsBound == fleetMateWarpAskedReadingsBound"
        ])
        self.assertTrue(same)

    def test_below_the_bound_warps_from_the_row(self):
        below_warps, below_gives_up, at_warps, at_gives_up = self.repl.evaluate([
            "stepFor (fleetWindowWarpAskedReadingsBound - 1) == WarpFromTheFleetWindowRow",
            "stepFor (fleetWindowWarpAskedReadingsBound - 1) == FleetWindowWarpGivenUp",
            "stepFor fleetWindowWarpAskedReadingsBound == WarpFromTheFleetWindowRow",
            "stepFor fleetWindowWarpAskedReadingsBound == FleetWindowWarpGivenUp",
        ])
        self.assertTrue(below_warps)
        self.assertFalse(below_gives_up)
        self.assertFalse(at_warps)
        self.assertTrue(at_gives_up)

    def test_one_reading_short_of_the_bound_still_warps(self):
        (still_warping,) = self.repl.evaluate([
            "stepFor (fleetWindowWarpAskedReadingsBound - 1)"
            " == WarpFromTheFleetWindowRow"
        ])
        self.assertTrue(still_warping)


class TheOffGridDecisionTest(unittest.TestCase):
    """`goToFleetMateOffGridPreferringTheFleetWindow`, asked directly.

    Three shapes: a fleet-window row to try first, no row so it falls
    straight through to `goToFleetMate` unmodified (the control case, part
    (c) of the issue's own checklist), and the on-overview case where the
    wrapper must not disturb `goToFleetMate`'s own on-grid branch at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_off_grid_with_a_row_warps_from_it(self):
        """Gap 1, part (a). A fleet-window row and no overview row is exactly
        the state #429's mechanism was proven live on and #442 found nothing
        reaching it in."""
        answer = self.repl.strings(
            ["offGridArm 0 offGridWithRow"], definitions=[OFF_GRID_WITH_ROW]
        )[0]
        self.assertIn("in the fleet window", answer)
        self.assertIn("warping to them from their own row's menu", answer)
        self.assertNotIn("asking the host for the route", answer)

    def test_off_grid_with_no_row_falls_through_unmodified(self):
        """Part (c), the control. Nothing for the fleet-window branch to try,
        so this must read exactly as `goToFleetMate` always has -- the
        route/ESI ask -- and not silently do nothing instead."""
        answer = self.repl.strings(
            ["offGridArm 0 offGridNoRow"], definitions=[OFF_GRID_NO_ROW]
        )[0]
        self.assertIn("asking the host for the route", answer)
        self.assertNotIn("fleet window", answer)

    def test_on_overview_reaches_the_on_grid_branch_unmodified(self):
        """The wrapper only changes the off-grid half. On the overview, this
        must read exactly as `warpToFleetMateOnThisGrid` always has -- never
        the fleet-window mechanism, which is for a pilot with no overview row
        at all."""
        answer = self.repl.strings(
            ["offGridArm 0 onOverview"], definitions=[ON_OVERVIEW]
        )[0]
        self.assertIn("is on this grid", answer)
        self.assertNotIn("fleet window", answer)
        self.assertNotIn("asking the host for the route", answer)

    def test_the_give_up_falls_through_to_the_ordinary_ask(self):
        """Past the bound, the fleet-window mechanism hands the reading to
        `goToFleetMate` rather than parking on a wait -- `Nothing` is the
        give-up and nothing else, this function's own doc comment says, and
        that give-up is `warpToFleetMateOnThisGrid`'s pattern reused."""
        answer = self.repl.strings(
            ["offGridArm fleetWindowWarpAskedReadingsBound offGridWithRow"],
            definitions=[OFF_GRID_WITH_ROW])[0]
        self.assertIn("asking the host for the route", answer)
        self.assertNotIn("fleet window", answer)


class TheMemoryCounterTest(unittest.TestCase):
    """`goToFleetMateFleetWindowWarpAskedReadings`, folded over a session.

    A rule that is right for one reading and wrong across a run is the defect
    this shape prevents -- `foldPresence`'s own reason in the gate-follow
    file, applied here to the counter #442 adds.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_starts_at_zero(self):
        (zero,) = self.repl.evaluate(
            ["initBotMemory.goToFleetMateFleetWindowWarpAskedReadings == 0"])
        self.assertTrue(zero)

    def test_it_advances_while_off_grid_with_a_row(self):
        answer = self.repl.values(
            ["counterAfter [ (1, bannerOffGridWithRow)"
             ", (1, bannerOffGridWithRow), (1, bannerOffGridWithRow) ]"],
            r"(-?\d+) : Int",
            definitions=[BANNER_OFF_GRID_WITH_ROW])
        self.assertEqual(answer, ["3"])

    def test_it_resets_the_moment_he_lands_on_the_overview(self):
        """Landing puts the pilot back on this ship's own overview -- the
        same reading the warp would have taken effect on -- so the counter
        must not go on climbing as though he were still off-grid."""
        answer = self.repl.values(
            ["counterAfter [ (5, bannerOffGridWithRow), (1, bannerOnOverview) ]"],
            r"(-?\d+) : Int",
            definitions=[BANNER_OFF_GRID_WITH_ROW, BANNER_ON_OVERVIEW])
        self.assertEqual(answer, ["0"])

    def test_it_resets_the_moment_the_row_disappears_too(self):
        """Off-grid with no row at all is not evidence the fleet-window
        mechanism is being tried -- the counter must not credit a reading
        `goToFleetMateOffGridPreferringTheFleetWindow` never spent on it."""
        answer = self.repl.values(
            ["counterAfter [ (5, bannerOffGridWithRow), (1, bannerOffGridNoRow) ]"],
            r"(-?\d+) : Int",
            definitions=[BANNER_OFF_GRID_WITH_ROW, BANNER_OFF_GRID_NO_ROW])
        self.assertEqual(answer, ["0"])

    def test_it_holds_once_the_bound_is_reached(self):
        pairs = "[ (fleetWindowWarpAskedReadingsBound + 5, bannerOffGridWithRow) ]"
        held_at, bound = self.repl.values(
            ["counterAfter %s" % pairs, "fleetWindowWarpAskedReadingsBound"],
            r"(-?\d+) : Int",
            definitions=[BANNER_OFF_GRID_WITH_ROW])
        self.assertEqual(held_at, bound)


class TheStatusLineTest(unittest.TestCase):
    """One rule, two readers -- the decision and the status line must never
    disagree about whether the fleet-window warp is under way, #102's own
    failure applied to #442's own addition."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_status_line_names_the_pilot_and_the_budget(self):
        answer = self.repl.strings(
            ["statusFor 2 bannerOffGridWithRow"],
            definitions=[BANNER_OFF_GRID_WITH_ROW])[0]
        self.assertIn(COMMANDER, answer)
        self.assertIn("fleet-window row", answer)
        self.assertIn("Readings spent: 2 of", answer)

    def test_the_status_line_says_nobody_is_off_grid_with_a_row(self):
        for name, reading in (
                ("no row at all", BANNER_OFF_GRID_NO_ROW),
                ("on the overview", BANNER_ON_OVERVIEW)):
            with self.subTest(name):
                answer = self.repl.strings(
                    ["statusFor 0 %s" % reading.split(" =", 1)[0]],
                    definitions=[reading])[0]
                self.assertIn("nobody this ship is flying to is off this grid", answer)

    def test_the_status_line_names_the_give_up(self):
        answer = self.repl.strings(
            ["statusFor fleetWindowWarpAskedReadingsBound bannerOffGridWithRow"],
            definitions=[BANNER_OFF_GRID_WITH_ROW])[0]
        self.assertIn("GAVE UP", answer)
        self.assertIn(COMMANDER, answer)
        self.assertIn("falling back to the route", answer)


class TheEndToEndReachabilityTest(unittest.TestCase):
    """#442's own standard, and the gate-follow file's: a rule that answers
    correctly in isolation says nothing about whether anything ever asks it.
    `wingmanDecisionRootInSpaceOrdinary` is the real root -- these run it end
    to end rather than the isolated arm."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_root_reaches_the_fleet_window_warp(self):
        """The wiring gap #442 fixes, closed: the real decision root, run
        against an off-grid commander with a fleet-window row and nothing
        else in the tree to decide on, reaches the fleet-window warp rather
        than falling through six arms to the route/ESI ask."""
        answer = self.repl.strings(
            ["rootFor 0 bannerOffGridWithRow"],
            definitions=[BANNER_OFF_GRID_WITH_ROW])[0]
        self.assertIn("warping to them from their own row's menu", answer)

    def test_the_root_still_asks_for_the_route_with_no_row_at_all(self):
        """The control, run through the root rather than the isolated arm --
        an FC neither on this overview nor in a readable fleet window still
        gets the ordinary ask, exactly as before #442."""
        answer = self.repl.strings(
            ["rootFor 0 bannerOffGridNoRow"],
            definitions=[BANNER_OFF_GRID_NO_ROW])[0]
        self.assertIn("asking the host for the route", answer)

    def test_the_root_does_not_warp_from_the_fleet_window_while_hes_on_grid(self):
        """On the overview, the root must reach the ordinary on-grid warp
        machinery -- never the fleet-window mechanism, which #429 built for a
        pilot with no overview row to select at all."""
        answer = self.repl.strings(
            ["rootFor 0 bannerOnOverview"],
            definitions=[BANNER_ON_OVERVIEW])[0]
        self.assertNotIn("fleet window", answer)


class TheGateAmbiguityTest(unittest.TestCase):
    """Gap 2's own light check -- the full battery lives in
    `test_wingman_follows_the_commander_through_a_gate.py`; this is the
    version the issue's own checklist asks this file to carry too, part (b)
    and its control."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_two_or_more_gates_now_follow_too(self):
        """Part (b): a confirmed-gone commander and two ambiguous gates, and
        the bot takes one rather than refusing to guess."""
        answers = self.repl.evaluate(
            ["follow 1", "follow 2", "follow 3"])
        self.assertEqual(answers, [True, True, True])

    def test_no_gate_at_all_still_refuses(self):
        """The control: guard 4's relaxation is 'at least one', never 'any
        number including none' -- a grid with no acceleration gate has
        nothing this arm can press."""
        (refuses,) = self.repl.evaluate(["follow 0"])
        self.assertFalse(refuses)


class TheRecoverFromRetreatIsUntouchedTest(unittest.TestCase):
    """Source-level: the two ordinary broadcast forms are rewired and
    `recoverFromRetreat`'s own fleet-window case is not touched at all --
    `goToFleetMateOffGridPreferringTheFleetWindow`'s own doc comment names
    this as deliberate, and this is what pins it rather than leaving it to be
    taken on the doc comment's word."""

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM) as handle:
            cls.source = handle.read()

    def test_at_location_and_in_position_at_call_the_wrapper(self):
        body = declaration(self.source, "actOnBroadcastVerb")
        self.assertEqual(
            body.count("goToFleetMateOffGridPreferringTheFleetWindow"), 2)
        # And not the bare `goToFleetMate` any more, for either ordinary form.
        self.assertNotIn(
            "                goToFleetMate context shipUI pilot", body)

    def test_recover_from_retreat_still_calls_the_named_mechanisms_directly(self):
        """`recoverFromRetreat` itself -- not `retreatRecoveryStep`, which only
        names which case to take -- is where the two mechanisms are actually
        called, and it must go on calling the bare `goToFleetMate` and
        `warpToFleetMateFromTheirFleetWindowRow` directly rather than the
        wrapper, exactly as its own case (`RouteToWhereTheCommanderLastSaid
        HeWas` before `WarpToTheCommanderFromTheFleetWindow`) already orders
        them."""
        body = declaration(self.source, "recoverFromRetreat")
        self.assertIn("WarpToTheCommanderFromTheFleetWindow", body)
        self.assertIn("RouteToWhereTheCommanderLastSaidHeWas", body)
        self.assertIn("goToFleetMate context shipUI commander", body)
        self.assertIn("warpToFleetMateFromTheirFleetWindowRow context row", body)
        self.assertNotIn("goToFleetMateOffGridPreferringTheFleetWindow", body)

    def test_the_wrapper_itself_still_falls_through_to_go_to_fleet_mate(self):
        body = declaration(self.source, "goToFleetMateOffGridPreferringTheFleetWindow")
        self.assertIn("goToFleetMate context shipUI pilot place calledIt", body)

    def test_one_rule_with_two_readers(self):
        """`fleetMateOffGridWithFleetWindowRow` is asked by the memory update
        and the status line -- a condition restated beside the rule in either
        one is exactly #102's failure."""
        memory_update = declaration(self.source, "updateMemoryForNewReadingFromGame")
        status = declaration(self.source, "describeFleetMateOffGridFleetWindowWarp")
        self.assertIn("fleetMateOffGridWithFleetWindowRow", memory_update)
        self.assertIn("fleetMateOffGridWithFleetWindowRow", status)


if __name__ == "__main__":
    unittest.main()
