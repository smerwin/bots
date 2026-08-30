"""Tests for locking a called target by ctrl-clicking the broadcast banner.

#366. Ctrl-clicking the fleet broadcast's `Target:` display locks the object the
broadcast refers to -- one dispatch, no context menu, no overview lookup. What
it replaces is `useContextMenuCascadeOnOverviewEntry` over a row found by
matching `targetBroadcastPilotName`'s parse of the banner against `objectName`
by **exact equality**: two string derivations that both have to agree about an
object the client itself already knows the identity of, followed by a cascade.

Three costs went with that, and the issue names all three: a target outside the
active overview preset was one this bot simply never shot, a rendering the parse
and the Name cell spell differently was the same, and cascades are where this
bot's readings and its bugs go (#329's `entryLabel` collision,
`contextMenuStuckTicks`, #285's unbounded loot-window branch).

## What is unknown, and these cases cannot close it

**Whether the ctrl-click works when the object is out of lock range, already
locked, or is a structure rather than a ship** -- and what the client does in
each case. #366 asks for a capture pass with `eve_read.py` before the fall-back
is wired; there is no client on the machine these cases run on, no recorded
corpus and no game log, so no case here recomputes anything live and none rests
on one.

That unknown is what shapes the change rather than being noted beside it. The
overview cascade is **kept as the fall-back**, reachable on _any_ failure to
lock rather than on a diagnosis this bot cannot make: `bannerCtrlClickAskedReadings
Bound` readings of clicking with the target still not reading locked hands it
over, and so does a banner this reading offers nothing to click. "Nothing
happened" and "cannot be locked" want different answers and this bot cannot tell
them apart, so it treats both as the first and says which path it is on in the
status line.

## The three things that had to survive, and none of them is in the lock

**The fleet-member guard is ahead of the click by placement.**
`actOnFleetBroadcast` refuses a called target named in `fleetPilotNames` before
`bringCalledTargetUnderFire` is called at all -- and a ctrl-click will lock a
fleet member as happily as a rat, so that ordering is what stops #367's own
incident arriving by this route. `targetBroadcastPilotName` is therefore still
needed for the *decision* even though the lock no longer needs it.

**The gate check is ahead of the click by placement too.** #393:
`bringCalledTargetUnderFire` dispatches on `calledObjectOnOverviewFromReading`
and hands a called acceleration gate to the gate machinery before it builds the
lock. A ctrl-click will lock a gate as happily as a ship, which is the reason
#393 put the check there rather than behind the lock -- in its own words, "a
gate check placed behind the lock would be dead the moment that lands".

**#395's give-up still bounds a call that names nothing on the grid.** The click
is attempted for a target with no overview row, which is the point of the
change: the banner is on screen whatever the overview is showing. A target that
is *gone* is a different state, and that give-up is asked before the lock and
fires at `calledTargetGoneReadings` (3), which is below this bound (5) -- so a
dead call is left alone by that arm rather than falling through to a cascade
that would find no row, say so, and wait.

Every one of those is asserted by running the real arm over a real parsed
reading, not by reading the source for an ordering.

## The counter counts asks

#389's lesson, and this file has already paid for it once:
`weaponsAskedReadings` advanced from state alone and reported
`GAVE UP after 46 readings` on an arm that had never been asked, on three pilots
at 46, 36 and 50 against a bound of 20. `bannerCtrlClickThisReading` is the
shipped rule answering `CtrlClickTheBroadcastBanner`, asked by
`updateMemoryForNewReadingFromGame` rather than restated beside it.

It **holds** rather than clearing on a reading that did not ask, which is the
one thing about this counter that is not `calledTargetGone`'s shape: past the
bound the rule stops asking, so a counter that cleared there would clear on the
very reading the bound was reached and the fall-back would last exactly one
reading before the click was re-issued for ever.

The cases run the real `Bot.elm` through `elm repl`, and the readings they are
asked about go through the real `EveOnline.ParseUserInterface`. The strongest of
them read the **effects the arm would dispatch** off the decision's own leaf
rather than its description, because a branch that prints an action and
dispatches nothing is this repo's signature failure.

## Confirmed by mutation

Seventeen, none surviving, each failing at least one named case:

| the mutation | what it breaks |
|---|---|
| **the fleet-member guard moved behind the click** | `test_a_called_fleetmate_is_never_clicked`, 2 cases |
| **the gate check bypassed, so the lock is built first** | `test_a_called_gate_is_taken_rather_than_clicked`, 2 cases |
| **the bound removed, so the click is re-issued for ever** | `test_the_bound_hands_it_to_the_cascade`, 8 cases |
| **the fall-back unreachable** (the rule answering the click whatever the count) | the same, 7 cases |
| **the counter advanced from state alone** | `test_a_reading_the_click_is_not_asked_on_spends_nothing`, 5 cases |
| the counter cleared instead of held on a reading that did not ask | `test_the_counter_holds_at_the_bound_rather_than_clearing`, 2 cases |
| the chord dropping its `KeyUp` | `test_the_chord_is_ctrl_held_over_a_left_click` |
| the chord holding Shift as well, which is saxrat's *unlock* | the same |
| the click aimed at the head of `fleetWindowDescendants` rather than the banner | `test_the_click_lands_on_the_banner`, 4 cases |
| an unclickable element dispatching `[]` rather than declining | `test_an_unclickable_banner_takes_the_cascade`, 5 cases |
| the inline copy of the chord left in `fightRatsIfShipIsPointed` | `test_there_is_one_copy_of_the_chord` |
| the bound cut below `calledTargetGoneReadings` | `test_the_bound_sits_above_the_gone_give_up` |
| the bound raised to a cascade's allowance | `test_the_bound_is_small_beside_the_bounds_on_a_cascade` |
| a different call inheriting the last call's count | `test_a_different_call_starts_its_own_count`, 2 cases |
| the count answered for a record about another name | `test_a_budget_spent_on_another_call_is_not_this_call_s` |
| the status clause dropped | `test_the_clause_is_in_the_status_line` |
| the clause speaking on a reading the lock is not the question on | `test_the_clause_is_silent_where_no_lock_is_being_issued` |

**One survived the first pass and the hole was in the fixture rather than in the
rule.** Pointing `calledTargetBannerCtrlClick` at
`fleetWindowDescendants |> List.head` instead of at `fleetBroadcastBannerElement`
changed nothing any case could see, because the fleet window's first child *was*
the banner label -- so "the banner" and "the head of the window" were one node
and every chord assertion passed on both. `DECOY_REGION` is what separates them
now: a clickable node with no name, drawn first and at a different point, so the
mutated rule produces a chord at coordinates the case refuses.

**And one was applied to `Bot.elm` for real, by a mutation run this container
killed before its `finally` could restore the file.** It was
`counter-cleared-not-held`, and it was found by the two cases named for it going
red on an otherwise ordinary run of this module -- which is the matrix doing its
job on the code rather than on a copy of it.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    label, node, overview_window, reading_binding)
from test_wingman_called_gate import (  # noqa: E402
    GATE, drones_window, gate_row, overview, rat_row, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: The commander's called target, and a second one so that "a different call" is
#: a call rather than a placeholder.
CALLED = "Centus Black Ops Agent"
OTHER = "Centus Dark Lord"
#: A fleetmate. The guard that refuses a call on one sits above this arm and a
#: ctrl-click would lock them as happily as a rat.
MATE = "Greta Gneiss"

#: Where the banner label is drawn, and therefore where the click has to land:
#: the centre of that region.
BANNER_REGION = (10, 10, 300, 16)
BANNER_CENTRE = (BANNER_REGION[0] + BANNER_REGION[2] // 2,
                 BANNER_REGION[1] + BANNER_REGION[3] // 2)
#: Too small for `uiNodeVisibleRegionLargeEnoughForClicking`, which wants more
#: than three points each way -- the client drawing a banner this bot cannot
#: click, which is one of the two ways the fall-back is reached.
BANNER_UNCLICKABLE = (10, 10, 3, 3)


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting that a name is *absent* from a declaration needs this
    first: the comments here name the very things those cases assert are not
    being reached for.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def bot_source():
    with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
        return handle.read()


def declaration(name, source=None):
    """One top-level declaration, from its type annotation to the next gap."""
    source = bot_source() if source is None else source
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def int_constant(name):
    """A constant read out of `Bot.elm`, so the cases below run against the
    shipped number rather than one restated here."""
    body = declaration(name)
    return int(body.split("\n%s =" % name)[1].split()[0])


#: Where the fleet window's own first descendant is drawn. It exists so that
#: "the banner element" and "the first thing in the fleet window" are not the
#: same node: with the banner first, a rule that clicked whatever
#: `fleetWindowDescendants` heads would land on exactly the same point and every
#: case here would pass on the fixture rather than on the rule. Its height is
#: over `uiNodeVisibleRegionLargeEnoughForClicking`'s three points on purpose,
#: so such a rule produces a *different* chord rather than no chord.
DECOY_REGION = (0, 0, 300, 6)
DECOY_CENTRE = (DECOY_REGION[0] + DECOY_REGION[2] // 2,
                DECOY_REGION[1] + DECOY_REGION[3] // 2)


def fleet_window(banner=None, members=(), banner_region=BANNER_REGION):
    """A `FleetWindow` carrying a broadcast banner and member rows.

    `fleetBroadcastBannerText` reads the display text of a descendant named
    `bannerLabel` and `fleetBroadcastBannerElement` reads the same node as an
    element -- so `banner_region` is what decides whether there is something to
    click, and the member rows are what the fleet-member guard reads through
    `fleetMemberNames`.

    The first child is a clickable decoy carrying no name, for `DECOY_REGION`'s
    reason.
    """
    children = [node("Container", {}, region=DECOY_REGION)]
    if banner is not None:
        children.append(
            label("Target %s" % banner, banner_region, name="bannerLabel"))
    children.extend(
        node("FleetMember", {}, [
            label(member, (10, 100 + index * 20, 200, 16), name="entryLabel"),
        ], region=(0, 100 + index * 20, 300, 20))
        for index, member in enumerate(members))
    return node("FleetWindow", {}, children, region=(0, 0, 300, 400))


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    Every field of the context is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide an answer except the reading and the
    memory a case names -- `test_wingman_called_target_gone`'s arrangement,
    memory as an argument included, since most of the cases here are about what
    a spent budget does.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import Common.EffectOnWindow",
        "import EveOnline.BotFrameworkSeparatingMemory",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "contextWith = \\memory -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # `FELL THROUGH` is a sentence no branch produces, so it reads as the
        # arm answering `Nothing` rather than as a decision this file failed to
        # anticipate.
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        "broadcastArm = \\memory -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " describeArm (actOnFleetBroadcast (contextWith memory p) s)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The chord, rendered. A description is what a branch *prints*; this is
        # what it would *dispatch*, which is the difference between an action
        # and a line about one.
        # Written across lines because Elm has no one-line `case`.
        # `ElmRepl.entry` supports that by indenting every physical line of a
        # binding rather than only its first -- but a *blank* line inside one
        # closes the entry, since that is what it appends to close the last
        # one. So the branches are packed rather than separated.
        "describeEffect =\n"
        "    \\effect ->\n"
        "        case effect of\n"
        "            Common.EffectOnWindow.MouseMoveTo p ->\n"
        '                "move " ++ String.fromInt p.x'
        ' ++ "," ++ String.fromInt p.y\n'
        "            Common.EffectOnWindow.KeyDown key ->\n"
        "                (if key == Common.EffectOnWindow.vkey_CONTROL"
        ' then "CTRL-DOWN" else "OTHER-KEY-DOWN")\n'
        "            Common.EffectOnWindow.KeyUp key ->\n"
        "                (if key == Common.EffectOnWindow.vkey_CONTROL"
        ' then "CTRL-UP" else "OTHER-KEY-UP")\n'
        "            Common.EffectOnWindow.ButtonDown button ->\n"
        "                (if button == Common.EffectOnWindow.MouseButtonLeft"
        ' then "LEFT-DOWN" else "RIGHT-DOWN")\n'
        "            Common.EffectOnWindow.ButtonUp button ->\n"
        "                (if button == Common.EffectOnWindow.MouseButtonLeft"
        ' then "LEFT-UP" else "RIGHT-UP")',
        "describeEffects = \\effects -> effects"
        ' |> List.map describeEffect |> String.join " "',
        # The chord the banner offers on one reading, rendered, or `NONE`.
        "bannerClick = \\parsed -> parsed |> Maybe.andThen calledTargetBannerCtrlClick",
        "chord = \\parsed -> bannerClick parsed"
        ' |> Maybe.map describeEffects |> Maybe.withDefault "NONE"',
        "describeLeaf =\n"
        "    \\leaf ->\n"
        "        case leaf of\n"
        "            EveOnline.BotFrameworkSeparatingMemory.ContinueSession"
        " session ->\n"
        "                (if session.effectsOnGameClient == []"
        ' then "DISPATCHES NOTHING"'
        " else describeEffects session.effectsOnGameClient)\n"
        "            EveOnline.BotFrameworkSeparatingMemory.FinishSession ->\n"
        '                "FINISH"',
        # What the arm would actually put on the client this reading.
        "armEffects = \\memory -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " actOnFleetBroadcast (contextWith memory p) s"
        " |> Maybe.map (unpack >> Tuple.second >> describeLeaf)"
        ' |> Maybe.withDefault "FELL THROUGH"))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The pure rule, as the three answers it has.
        "stepWith = \\banner -> \\row -> \\asked ->"
        " lockCalledTargetStep { bannerOffersACtrlClick = banner"
        " , overviewRowIsInTheReading = row, askedReadings = asked }",
        # What the shipped rule makes of one reading, as `name:asked` or `-`.
        "askOn = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> bannerCtrlClickThisReading"
        " { followFleetBroadcastFrom = defaultBotSettings.followFleetBroadcastFrom"
        " , calledTargetGone = memory.calledTargetGone"
        " , bannerCtrlClick = memory.bannerCtrlClick } p)"
        " |> Maybe.map (\\ask -> (ask.calledTarget"
        ' |> Maybe.withDefault "-")'
        ' ++ ":" ++ (if ask.asked then "asked" else "no"))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # `updateMemoryForNewReadingFromGame` folded over real readings, giving
        # back the memory itself so an arm can then be asked about it. A
        # fixture that never arrived is named rather than read as a session that
        # counted nothing, which is #174's own failure.
        "memoryOver = \\readings ->"
        " if List.any ((==) Nothing) readings then"
        " { initBotMemory | bannerCtrlClick ="
        '     Just { calledTarget = "THE FIXTURE NEVER ARRIVED", readings = -1 } }'
        " else (readings |> List.filterMap identity |> List.foldl (\\r -> \\m ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = r"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings, previousStepsEffects = [] } m) initBotMemory)",
        "clickAfter = \\readings -> (memoryOver readings).bannerCtrlClick"
        " |> Maybe.map (\\ask -> ask.calledTarget"
        '     ++ ":" ++ String.fromInt ask.readings)'
        ' |> Maybe.withDefault "-"',
        # A record built by hand, for the cases about the boundary itself rather
        # than about how a session reaches it.
        "clickRecord = \\name -> \\readings ->"
        " Just { calledTarget = name, readings = readings }",
        "memoryClicked = \\name -> \\readings ->"
        " { initBotMemory | bannerCtrlClick = clickRecord name readings }",
        "describeCalled = \\memory -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeCalledObject (contextWith memory p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "lockWorkingOn = \\memory -> \\parsed -> parsed"
        " |> Maybe.andThen (calledTargetTheLockIsWorkingOn"
        "     defaultBotSettings.followFleetBroadcastFrom memory.calledTargetGone)"
        ' |> Maybe.withDefault "-"',
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-banner-ctrl-click-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


#: The ordinary case: the commander called a rat, it is on the overview, and
#: nothing has locked it yet.
CALLED_ON_GRID = reading_binding(
    "calledOnGrid",
    [fleet_window(banner=CALLED, members=[MATE]),
     overview([(CALLED, "Frigate", True, True), rat_row()]),
     drones_window(0),
     ship_ui()])

#: The capability #366 is for: the banner names something no overview row
#: carries, and the banner is on screen regardless.
CALLED_OFF_OVERVIEW = reading_binding(
    "calledOffOverview",
    [fleet_window(banner=CALLED, members=[MATE]),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: The same call, with the client drawing its own lock indicator on the row.
#: #360's stand-down, and the reading on which no lock is issued at all.
CALLED_LOCKED = reading_binding(
    "calledLocked",
    [fleet_window(banner=CALLED, members=[MATE]),
     overview_window([(CALLED, "5 km", True)]),
     drones_window(0),
     ship_ui()])

#: The banner is drawn too small to click. One of the two ways the cascade is
#: reached, and the one that needs no budget spent.
BANNER_TOO_SMALL = reading_binding(
    "bannerTooSmall",
    [fleet_window(banner=CALLED, members=[MATE],
                  banner_region=BANNER_UNCLICKABLE),
     overview([(CALLED, "Frigate", True, True), rat_row()]),
     drones_window(0),
     ship_ui()])

#: The same, with nothing on the overview either -- neither mechanism has
#: anything to work with.
BANNER_TOO_SMALL_AND_NO_ROW = reading_binding(
    "bannerTooSmallAndNoRow",
    [fleet_window(banner=CALLED, members=[MATE],
                  banner_region=BANNER_UNCLICKABLE),
     overview([rat_row()]),
     drones_window(0),
     ship_ui()])

#: The banner calls a fleetmate. A ctrl-click would lock them.
CALLED_FLEETMATE = reading_binding(
    "calledFleetmate",
    [fleet_window(banner=MATE, members=[MATE]),
     overview([(MATE, "Capsule", True, False), rat_row()]),
     drones_window(0),
     ship_ui()])

#: The banner calls an acceleration gate. A ctrl-click would lock that too.
CALLED_GATE = reading_binding(
    "calledGate",
    [fleet_window(banner=GATE, members=[MATE]),
     overview([gate_row(), rat_row()]),
     drones_window(0),
     ship_ui()])

#: A second call, on a target that is on the grid.
OTHER_ON_GRID = reading_binding(
    "otherOnGrid",
    [fleet_window(banner=OTHER, members=[MATE]),
     overview([(OTHER, "Frigate", True, True), rat_row()]),
     drones_window(0),
     ship_ui()])

READINGS = [CALLED_ON_GRID, CALLED_OFF_OVERVIEW, CALLED_LOCKED,
            BANNER_TOO_SMALL, BANNER_TOO_SMALL_AND_NO_ROW, CALLED_FLEETMATE,
            CALLED_GATE, OTHER_ON_GRID]

FIXTURE_NAMES = ("calledOnGrid", "calledOffOverview", "calledLocked",
                 "bannerTooSmall", "bannerTooSmallAndNoRow", "calledFleetmate",
                 "calledGate", "otherOnGrid")

#: What the chord looks like when it is dispatched at the banner.
THE_CHORD = "CTRL-DOWN move %d,%d LEFT-DOWN LEFT-UP CTRL-UP" % BANNER_CENTRE


class TheChordTest(unittest.TestCase):
    """The gesture itself, read back as the effects it dispatches.

    A description is what a branch prints; these are what it puts on the client.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """Otherwise every case in this file passes against readings that
        decoded to `Nothing`, which is #174's own failure sitting here."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s /= Nothing" % name for name in FIXTURE_NAMES],
                READINGS),
            [True] * len(FIXTURE_NAMES))

    def test_the_chord_is_ctrl_held_over_a_left_click(self):
        """Ctrl down, the click, Ctrl up -- and nothing else. saxrat's
        `ctrlShiftClickUiElement` holds Shift as well and is the *unlock*, so a
        chord that grew one would be the opposite command."""
        self.assertEqual(
            self.repl.strings(["chord calledOnGrid"], [CALLED_ON_GRID]),
            [THE_CHORD])

    def test_the_click_lands_on_the_banner(self):
        """The centre of the banner's own region, so the chord is aimed at the
        thing the broadcast is drawn on rather than at whatever else the fleet
        window holds.

        The fleet window's first descendant is a clickable decoy at a different
        point (`DECOY_REGION`), so this discriminates the banner from "the head
        of `fleetWindowDescendants`" rather than passing on both.
        """
        chord = self.repl.strings(["chord calledOnGrid"], [CALLED_ON_GRID])[0]
        self.assertIn("move %d,%d" % BANNER_CENTRE, chord)
        self.assertNotIn("move %d,%d" % DECOY_CENTRE, chord)

    def test_an_element_too_small_to_click_declines(self):
        """`mouseClickOnUIElement` answers `Err` for an element whose visible
        region is too small, and dispatching `[]` on that is a branch that
        prints an action and does nothing -- what saxrat's copy of this gesture
        still does."""
        self.assertEqual(
            self.repl.strings(["chord bannerTooSmall"], [BANNER_TOO_SMALL]),
            ["NONE"])

    def test_a_reading_with_no_banner_offers_no_click(self):
        self.assertEqual(
            self.repl.evaluate(
                ["bannerClick calledOnGrid /= Nothing",
                 "bannerClick bannerTooSmall == Nothing"],
                [CALLED_ON_GRID, BANNER_TOO_SMALL]),
            [True, True])

    def test_there_is_one_copy_of_the_chord(self):
        """`fightRatsIfShipIsPointed` wrote this out inline and #366 folded it
        in rather than leaving two. A chord built wrong is one the client reads
        as a plain click, which locks nothing and says nothing, so two copies
        are two chances for one of them to drift."""
        source = without_comments(bot_source())
        builders = [line for line in source.splitlines()
                    if "EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL"
                    in line]
        self.assertEqual(len(builders), 1, builders)
        self.assertIn("ctrlClickEffects firstPointingBuffButton",
                      collapsed(without_comments(
                          declaration("fightRatsIfShipIsPointed"))))


class TheRuleTest(unittest.TestCase):
    """`lockCalledTargetStep`, at every clause and either side of its bound.

    Asked as three equalities per case, so a rule answering two things at once
    -- or none -- fails rather than passing on whichever constructor a case
    happened to name.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("bannerCtrlClickAskedReadingsBound")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, banner, row, asked):
        answers = self.repl.evaluate(
            ["stepWith %s %s %d == %s" % (banner, row, asked, constructor)
             for constructor in ("CtrlClickTheBroadcastBanner",
                                 "LockFromTheOverviewRow",
                                 "NoWayToLockTheCalledTarget")])
        self.assertEqual(answers.count(True), 1, answers)
        return ("CtrlClickTheBroadcastBanner", "LockFromTheOverviewRow",
                "NoWayToLockTheCalledTarget")[answers.index(True)]

    def test_a_banner_and_a_row_takes_the_banner(self):
        self.assertEqual(self.step("True", "True", 0),
                         "CtrlClickTheBroadcastBanner")

    def test_a_banner_and_no_row_still_takes_the_banner(self):
        """The capability: the click needs no overview row at all."""
        self.assertEqual(self.step("True", "False", 0),
                         "CtrlClickTheBroadcastBanner")

    def test_no_banner_takes_the_overview_row(self):
        self.assertEqual(self.step("False", "True", 0),
                         "LockFromTheOverviewRow")

    def test_neither_is_neither(self):
        self.assertEqual(self.step("False", "False", 0),
                         "NoWayToLockTheCalledTarget")

    def test_the_bound_hands_it_to_the_cascade(self):
        """Both sides of the boundary, so a comparison moved by one fails."""
        self.assertEqual(self.step("True", "True", self.BOUND - 1),
                         "CtrlClickTheBroadcastBanner")
        self.assertEqual(self.step("True", "True", self.BOUND),
                         "LockFromTheOverviewRow")

    def test_fixed_values_either_side_of_it(self):
        """A boundary pair alone is satisfied by *any* constant, including one
        that gives up on the first reading -- the hole four of #120's own cases
        had. So: one reading is still clicking, and a hundred is not."""
        self.assertEqual(self.step("True", "True", 1),
                         "CtrlClickTheBroadcastBanner")
        self.assertEqual(self.step("True", "True", 100),
                         "LockFromTheOverviewRow")

    def test_a_spent_budget_with_no_row_has_nothing_left(self):
        """The fall-back is a mechanism rather than an answer: with the click
        given up on and no row to open a menu on, the arm says so."""
        self.assertEqual(self.step("True", "False", self.BOUND),
                         "NoWayToLockTheCalledTarget")

    def test_the_bound_sits_above_the_gone_give_up(self):
        """#395 gives up on a call the banner still names and no overview row
        carries, before the lock. Below that, a dead call would spend this
        budget and fall through to a cascade that finds no row and waits, which
        is the unbounded wait #395 removed."""
        self.assertGreater(self.BOUND, int_constant("calledTargetGoneReadings"))

    def test_the_bound_is_small_beside_the_bounds_on_a_cascade(self):
        """Those budget a cascade the client keeps refusing -- a menu to open on
        every attempt. This budgets one dispatch with nothing to render."""
        for cascade_bound in ("weaponsAskedReadingsBound",
                              "fleetMateWarpAskedReadingsBound",
                              "accelerationGateRefusesThisShipTicks"):
            self.assertLess(self.BOUND, int_constant(cascade_bound),
                            cascade_bound)


class TheArmClicksTheBannerTest(unittest.TestCase):
    """The real `actOnFleetBroadcast` over real parsed readings, read back as
    the effects it would dispatch."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("bannerCtrlClickAskedReadingsBound")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_called_target_is_locked_by_clicking_the_banner(self):
        line, effects = self.repl.strings(
            ["broadcastArm initBotMemory calledOnGrid",
             "armEffects initBotMemory calledOnGrid"],
            [CALLED_ON_GRID])
        self.assertIn("Lock the called target '%s'." % CALLED, line)
        self.assertIn("Ctrl-click the fleet broadcast banner", line)
        self.assertEqual(effects, THE_CHORD)

    def test_a_target_with_no_overview_row_is_still_clicked(self):
        """The capability #366 is for. Before it, this reading was
        `'X' is not on the overview` and a wait: a target outside the active
        overview preset was one this bot never shot."""
        line, effects = self.repl.strings(
            ["broadcastArm initBotMemory calledOffOverview",
             "armEffects initBotMemory calledOffOverview"],
            [CALLED_OFF_OVERVIEW])
        self.assertIn("Ctrl-click the fleet broadcast banner", line)
        self.assertEqual(effects, THE_CHORD)

    def test_a_locked_target_is_not_clicked_again(self):
        """#360's stand-down is untouched: the arm hands the reading to the
        drones and the guns once the client says the thing is locked."""
        self.assertEqual(
            self.repl.strings(["broadcastArm initBotMemory calledLocked"],
                              [CALLED_LOCKED]),
            ["FELL THROUGH"])

    def test_an_unclickable_banner_takes_the_cascade(self):
        """No budget spent and no diagnosis needed: there is nothing to click,
        so the overview row's own menu has it."""
        line, effects = self.repl.strings(
            ["broadcastArm initBotMemory bannerTooSmall",
             "armEffects initBotMemory bannerTooSmall"],
            [BANNER_TOO_SMALL])
        self.assertIn("from its overview row", line)
        self.assertNotIn("Ctrl-click", line)
        self.assertNotIn("CTRL-DOWN", effects)

    def test_neither_mechanism_says_so_rather_than_claiming_one(self):
        line = self.repl.strings(
            ["broadcastArm initBotMemory bannerTooSmallAndNoRow"],
            [BANNER_TOO_SMALL_AND_NO_ROW])[0]
        self.assertIn("there is nothing here to lock it with", line)
        self.assertNotIn("Ctrl-click", line)

    def test_a_spent_budget_hands_the_lock_to_the_cascade(self):
        """The fall-back, reachable on *any* failure to lock rather than on a
        diagnosis this bot cannot make -- and at the bound rather than one
        reading either side of it."""
        clicking, fallen_back = self.repl.strings(
            ['broadcastArm (memoryClicked "%s" %d) calledOnGrid'
             % (CALLED, self.BOUND - 1),
             'broadcastArm (memoryClicked "%s" %d) calledOnGrid'
             % (CALLED, self.BOUND)],
            [CALLED_ON_GRID])
        self.assertIn("Ctrl-click the fleet broadcast banner", clicking)
        self.assertIn("from its overview row", fallen_back)
        self.assertNotIn("Ctrl-click", fallen_back)

    def test_a_budget_spent_on_another_call_is_not_this_call_s(self):
        """A record about the last call must not send this one straight to the
        cascade -- #145's own defect, and `calledTargetHasBeenGivenUpOn`'s
        posture next door."""
        self.assertIn(
            "Ctrl-click the fleet broadcast banner",
            self.repl.strings(
                ['broadcastArm (memoryClicked "%s" 900) calledOnGrid' % OTHER],
                [CALLED_ON_GRID])[0])


class TheGuardsAreAheadOfTheClickTest(unittest.TestCase):
    """Shown by running the arm, not by reading an ordering.

    A ctrl-click will lock a fleet member and it will lock a gate, so both
    checks have to answer before the click is built. Both are placements, which
    is exactly why they can be shown: the arm never reaches the lock.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_called_fleetmate_is_never_clicked(self):
        line, effects = self.repl.strings(
            ["broadcastArm initBotMemory calledFleetmate",
             "armEffects initBotMemory calledFleetmate"],
            [CALLED_FLEETMATE])
        self.assertIn("is in this fleet. Not shooting it.", line)
        self.assertNotIn("Ctrl-click", line)
        self.assertNotIn("CTRL-DOWN", effects)

    def test_a_called_gate_is_taken_rather_than_clicked(self):
        line, effects = self.repl.strings(
            ["broadcastArm initBotMemory calledGate",
             "armEffects initBotMemory calledGate"],
            [CALLED_GATE])
        self.assertIn("ACCELERATION GATE", line.upper())
        self.assertNotIn("Ctrl-click", line)
        self.assertNotIn("CTRL-DOWN", effects)

    def test_the_gate_check_is_what_the_arm_dispatches_on(self):
        """#393's own case, re-asserted here because #366 is the change that
        would have made a gate check placed behind the lock dead. The dispatch
        opens on the classification and the lock is one of its answers."""
        arm = collapsed(
            without_comments(declaration("bringCalledTargetUnderFire")))
        self.assertIn("case calledObjectOnOverviewFromReading calledTarget "
                      "context.readingFromGameClient of "
                      "CalledObjectIsAnAccelerationGate gateEntry ->", arm)
        self.assertNotIn("lockCalledTargetStep", arm,
                         "the lock's own rule belongs below the classification")

    def test_the_fleet_guard_is_ahead_of_the_arm_it_guards(self):
        """The one thing here a run cannot show, since the guard answering is
        what stops the arm being reached at all."""
        act = collapsed(without_comments(declaration("actOnFleetBroadcast")))
        guard = act.index("List.member calledTarget (fleetPilotNames context)")
        self.assertLess(guard, act.index("bringCalledTargetUnderFire context"))

    def test_the_lock_reaches_for_neither_guard(self):
        """Both are placements rather than conditions, so a copy of either
        inside the lock would be a second answer that could disagree."""
        lock = collapsed(without_comments(declaration("lockCalledTarget")))
        self.assertNotIn("fleetPilotNames", lock)
        self.assertNotIn("AccelerationGate", lock)


class TheCounterCountsAsksTest(unittest.TestCase):
    """#389's lesson, and this file has already paid for it once.

    The counter is the shipped rule answering `CtrlClickTheBroadcastBanner`,
    folded through the shipped `updateMemoryForNewReadingFromGame`.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("bannerCtrlClickAskedReadingsBound")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_reading_the_click_is_asked_on_is_what_it_counts(self):
        self.assertEqual(
            self.repl.strings(["askOn initBotMemory calledOnGrid"],
                              [CALLED_ON_GRID]),
            ["%s:asked" % CALLED])

    def test_a_reading_the_click_is_not_asked_on_spends_nothing(self):
        """Every one of the arm's own conditions, each a way the budget could be
        charged for a reading nothing spent: a locked target, a call on a
        fleetmate, and a called gate."""
        self.assertEqual(
            self.repl.strings(
                ["askOn initBotMemory calledLocked",
                 "askOn initBotMemory calledFleetmate",
                 "askOn initBotMemory calledGate"],
                [CALLED_LOCKED, CALLED_FLEETMATE, CALLED_GATE]),
            ["-:no"] * 3)

    def test_a_call_the_cascade_has_is_still_the_lock_s_question(self):
        """The banner offering nothing to click is a reading on which the lock
        is being issued and this click is not -- so the call is named and the
        budget stands still, rather than the record clearing and the click
        starting over on the next reading that offers one."""
        self.assertEqual(
            self.repl.strings(["askOn initBotMemory bannerTooSmall"],
                              [BANNER_TOO_SMALL]),
            ["%s:no" % CALLED])

    def test_a_session_of_clicking_counts_every_one(self):
        session = ", ".join(["calledOnGrid"] * 3)
        self.assertEqual(
            self.repl.strings(["clickAfter [%s]" % session], [CALLED_ON_GRID]),
            ["%s:3" % CALLED])

    def test_the_counter_holds_at_the_bound_rather_than_clearing(self):
        """The one place this differs from `calledTargetGone`'s shape, and the
        reason is the fall-back: past the bound the rule stops asking, so a
        counter that cleared on a reading that did not ask would clear on the
        very reading the bound was reached -- the cascade would have the lock
        for exactly one reading and the click would be re-issued for ever."""
        session = ", ".join(["calledOnGrid"] * (self.BOUND + 4))
        self.assertEqual(
            self.repl.strings(["clickAfter [%s]" % session], [CALLED_ON_GRID]),
            ["%s:%d" % (CALLED, self.BOUND)])

    def test_the_fall_back_sticks_across_a_whole_session(self):
        """The same session, asked of the arm: a click that never locks
        anything ends in the cascade and stays there, rather than alternating
        with it."""
        session = ", ".join(["calledOnGrid"] * (self.BOUND + 4))
        line = self.repl.strings(
            ["broadcastArm (memoryOver [%s]) calledOnGrid" % session],
            [CALLED_ON_GRID])[0]
        self.assertIn("from its overview row", line)
        self.assertNotIn("Ctrl-click", line)

    def test_a_locked_target_clears_it(self):
        """The click worked, so the next call gets a whole allowance."""
        session = ", ".join(["calledOnGrid"] * 2 + ["calledLocked"])
        self.assertEqual(
            self.repl.strings(["clickAfter [%s]" % session],
                              [CALLED_ON_GRID, CALLED_LOCKED]),
            ["-"])

    def test_a_different_call_starts_its_own_count(self):
        session = ", ".join(["calledOnGrid"] * (self.BOUND + 2)
                            + ["otherOnGrid"])
        self.assertEqual(
            self.repl.strings(["clickAfter [%s]" % session],
                              [CALLED_ON_GRID, OTHER_ON_GRID]),
            ["%s:1" % OTHER])

    def test_a_new_call_is_clicked_after_the_last_one_was_given_up_on(self):
        """End to end: a whole session spent clicking at one call, then the
        commander calls something else and the click goes out on that
        reading."""
        session = ", ".join(["calledOnGrid"] * (self.BOUND + 2)
                            + ["otherOnGrid"])
        self.assertIn(
            "Ctrl-click the fleet broadcast banner",
            self.repl.strings(
                ["broadcastArm (memoryOver [%s]) otherOnGrid" % session],
                [CALLED_ON_GRID, OTHER_ON_GRID])[0])

    def test_a_call_395_has_given_up_on_spends_nothing(self):
        """That give-up is asked before the lock, so no click is issued and no
        budget moves on those readings."""
        self.assertEqual(
            self.repl.strings(
                ["askOn { initBotMemory | calledTargetGone ="
                 ' Just { calledTarget = "%s"'
                 " , readings = calledTargetGoneReadings + 1 } }"
                 " calledOffOverview" % CALLED],
                [CALLED_OFF_OVERVIEW]),
            ["-:no"])

    def test_a_call_with_no_row_spends_the_budget_while_395_still_allows_it(self):
        """And before that give-up it is clicked, which is the state #366 makes
        reachable at all."""
        self.assertEqual(
            self.repl.strings(["askOn initBotMemory calledOffOverview"],
                              [CALLED_OFF_OVERVIEW]),
            ["%s:asked" % CALLED])

    def test_the_arm_and_the_counter_read_one_rule(self):
        """`updateMemoryForNewReadingFromGame` never sees a decision, so a
        restatement of when the click is asked would be two rules that can
        disagree -- #145's own defect, and what `calledTargetGone` next door
        already avoids by asking the shipped rule."""
        update = collapsed(
            without_comments(declaration("updateMemoryForNewReadingFromGame")))
        self.assertIn("bannerCtrlClick = bannerCtrlClickAfterReading "
                      "botMemoryBefore.bannerCtrlClick "
                      "(bannerCtrlClickThisReading", update)
        self.assertNotIn("CtrlClickTheBroadcastBanner", update,
                         "the answer belongs to the rule both readers ask")

    def test_the_counter_is_written_where_every_reading_reaches_it(self):
        """#102's placement rule."""
        self.assertIn("bannerCtrlClick =",
                      collapsed(declaration("updateMemoryForNewReadingFromGame")))
        self.assertIn("bannerCtrlClick = Nothing",
                      collapsed(declaration("initBotMemory")))


class TheClauseSaysWhichPathTest(unittest.TestCase):
    """The status line, because #366 ships with the client's answer unknown.

    A run that never leaves the cascade and a run that never reaches it are the
    two things to tell apart on the first run that meets a call, and from a
    decision line alone they read the same.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.BOUND = int_constant("bannerCtrlClickAskedReadingsBound")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_clause_says_which_path_it_is_on(self):
        clicking, given_up, no_banner, neither = self.repl.strings(
            ["describeCalledTargetLock 2 CtrlClickTheBroadcastBanner",
             "describeCalledTargetLock %d LockFromTheOverviewRow" % self.BOUND,
             "describeCalledTargetLock 0 LockFromTheOverviewRow",
             "describeCalledTargetLock 0 NoWayToLockTheCalledTarget"])
        self.assertIn("CTRL-CLICKING THE BROADCAST BANNER", clicking)
        self.assertIn("asked on 2 of %d readings" % self.BOUND, clicking)
        self.assertIn("THE BANNER CLICK DID NOT LOCK IT in %d readings"
                      % self.BOUND, given_up)
        self.assertIn("cascade has it", given_up)
        self.assertIn("no banner in this reading to click", no_banner)
        self.assertIn("NOTHING HERE CAN LOCK IT", neither)

    def test_the_clause_is_in_the_status_line(self):
        """A rule nothing prints is a rule nobody reads."""
        clicking, fallen_back = self.repl.strings(
            ["describeCalled initBotMemory calledOnGrid",
             'describeCalled (memoryClicked "%s" %d) calledOnGrid'
             % (CALLED, self.BOUND)],
            [CALLED_ON_GRID])
        self.assertIn("CTRL-CLICKING THE BROADCAST BANNER", clicking)
        self.assertIn("THE BANNER CLICK DID NOT LOCK IT", fallen_back)

    def test_the_clause_is_silent_where_no_lock_is_being_issued(self):
        """A clause claiming a click on a locked target, a called gate or a
        fleetmate would be a decision this bot did not take."""
        for name, reading in (("calledLocked", CALLED_LOCKED),
                              ("calledGate", CALLED_GATE),
                              ("calledFleetmate", CALLED_FLEETMATE)):
            clause = self.repl.strings(
                ["describeCalled initBotMemory %s" % name], [reading])[0]
            self.assertNotIn("Lock:", clause, name)

    def test_the_status_line_calls_the_clause(self):
        self.assertIn(
            "describeCalledObject context",
            collapsed(declaration("statusTextFromState")))

    def test_the_lock_s_own_question_is_one_rule(self):
        """The clause speaks exactly where the arm issues a lock, so the two
        cannot disagree about whether a click is happening."""
        self.assertEqual(
            self.repl.strings(
                ["lockWorkingOn initBotMemory calledOnGrid",
                 "lockWorkingOn initBotMemory calledLocked",
                 "lockWorkingOn initBotMemory calledGate",
                 "lockWorkingOn initBotMemory calledFleetmate",
                 "lockWorkingOn initBotMemory calledOffOverview"],
                [CALLED_ON_GRID, CALLED_LOCKED, CALLED_GATE, CALLED_FLEETMATE,
                 CALLED_OFF_OVERVIEW]),
            [CALLED, "-", "-", "-", CALLED])


if __name__ == "__main__":
    unittest.main()
