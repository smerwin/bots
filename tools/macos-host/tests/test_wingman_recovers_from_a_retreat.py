"""Tests for the wingman getting back to its commander after a retreat.

#381. `recoverFromRetreat` handed `goToFleetMate` the **empty string** as the
place to route to, and that function's off-grid half needs a place name -- so it
took the branch that says so and waited:

    + Recovering from a retreat -- rejoin the fleet commander before resuming.
    ++ 'Gal Bistot' is this fleet's commander and this ship is recovering,
       rejoining and is not on this grid, and nothing names a place to route to,
       so there is nothing to fly toward.
    +++ Wait for progress in game

That branch is not an edge case. **The retreat is what puts the commander off
grid** -- `warpAwayFromDanger` warps to a celestial at AU range or docks -- so
the arm reached after every successful retreat was the one arm that could never
do anything. And because it sits above the broadcast and combat arms and
answered `Just` for as long as `recoveringFromRetreat` was latched, a ship that
could not rejoin did not fight either: Greta at tick 706, Heather at 464 and
Kara at 749, all healthy at 86-100% shield, all parked. Those are the issue's
own live observations; nothing here recomputes them.

## What the change is

**A remembered place.** `fleetPlaceBroadcast` carries the last place any
broadcast named, with the pilot who named it, across the retreat. The three
forms that carry one are `Travel to`, `is at location` and `is in position at`,
and `TravelTo` is in that list because the Olivia reading in #381 is the proof
the place was there: on the reading three wingmen had nothing to fly to, a
fourth was routing to `'Madirmilire'` off `Gal Bistot: Travel to Madirmilire`.
It is replaced by a newer place broadcast and dropped by the reunion, so no
place this arm routes to was broadcast before the last time this ship was with
its commander.

**A second lever.** Where the banner is the commander's own call for company,
`Fleet Member` -> `Warp to Member` off it -- saxrat's proven in-system path, the
same cascade `answerTheBackupCall` drives off the banner for a caller with no
overview row. It is asked before the remembered place, because after
`warpAwayFromDanger` this ship is usually in the same system as its commander,
where the banner's warp is right and a route to a system the ship is already in
is empty.

**A bound.** `retreatRecoveryAskedReadingsBound` (`fleetMateWarpAskedReadingsBound`,
30). It counts only the answers this arm dispatches on, resets on a reading the
ship is warping or jumping, holds once spent, and resets when the recovery ends.
The give-up **hands the reading back** rather than parking, so everything below
becomes reachable -- and it does **not** clear `recoveringFromRetreat`, which is
the only thing that says this ship is still away from its fleet.

Confirmed by mutation, each failing a named case:

 1. the bound removed, so the arm answers forever --
    `test_the_bound_is_asked_at_its_boundary` and
    `test_the_give_up_outranks_every_actionable_moment`;
 2. the counter advanced from state alone (`recovering` rather than the rule's
    answer), so a reading with nowhere to rejoin is charged -- #389's own shape
    -- `test_nowhere_to_rejoin_spends_nothing` and
    `test_only_the_answers_that_dispatch_are_counted`;
 3. the give-up made to answer `Just (... waitForProgressInGame)` --
    `test_the_give_up_hands_the_reading_back` and
    `test_the_arms_below_are_reachable_once_the_recovery_gives_up`;
 4. the reunion clause dropped from `fleetPlaceBroadcastAfterReading`, so a
    place is never invalidated -- `test_the_reunion_drops_the_remembered_place`;
 5. `recoverFromRetreat` hoisted above `retreatToTheCommander` --
    `test_the_arm_sits_below_the_retreat`;
 6. the empty place handed to `goToFleetMate` again --
    `test_a_remembered_place_is_flown_to` and
    `test_the_arm_no_longer_routes_to_the_empty_place`;
 7. `TravelTo` dropped from `fleetPlaceBroadcastAnyPilot`, which is the Olivia
    reading -- `test_the_travel_form_carries_a_place`;
 8. the commander filter dropped, so any pilot's place is flown to --
    `test_another_pilots_place_is_not_flown_to`;
 9. the commander filter weakened to a substring --
    `test_the_commander_is_matched_exactly`;
10. the warping reset moved above the give-up, so a warp un-gives-up --
    `test_a_warp_cannot_undo_a_spent_budget`;
11. the counter reset rather than held past the bound --
    `test_the_counter_is_held_once_the_budget_is_spent`;
12. the give-up made to clear `recoveringFromRetreat` --
    `test_the_give_up_leaves_the_latch_alone`;
13. permission asked after the give-up --
    `test_a_commander_nothing_names_is_not_a_spent_budget`;
14. the banner clause dropped, so an in-system commander is routed to instead --
    `test_the_banner_is_asked_before_the_remembered_place`;
15. `describeRetreatRecovery` dropped from the status line --
    `test_the_arm_is_visible_in_the_status_line`;
16. the counter's rule restated in the memory update rather than asked --
    `test_the_counter_asks_the_shipped_rule`.

The cases run the real `Bot.elm` through `elm repl`, and the readings they ask
about come from the real `EveOnline.ParseUserInterface`. Nothing here reads a
live client, the recorded corpus, or a running bot -- there is no wingman corpus
to read (WINGMAN.md).

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
from test_saxrat_ported_guards import (  # noqa: E402
    SaxratRepl, label, node, overview)
from test_wingman_orbits_the_fleet_commander import (  # noqa: E402
    ship_ui_indicating)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The commander the four live wingmen follow, and a fleet-mate who is not him.
# Two-word names, because that is what the client writes and because a
# one-word name could not show that the commander is matched exactly.
COMMANDER = "Gal Bistot"
OTHER_MATE = "Olivia Olivine"

# The place #381's own reading carried, on a travel broadcast, while three
# wingmen a grid away had nothing to fly to.
PLACE = "Madirmilire"


def reading_binding(name, children):
    """`SaxratRepl.reading_binding`, called rather than copied.

    It names only `EveOnline.MemoryReading` and `EveOnline.ParseUserInterface`,
    which resolve in whichever app's tree the repl was built from, so it builds
    a real wingman reading as readily as a saxrat one -- and it goes through
    `elm_json_literal`, which is what stops a fixture carrying a double quote
    from decoding to `Nothing` and a case passing having asserted nothing.
    """
    return SaxratRepl.reading_binding(name, children)


def fleet_window(banner=None, header_commander=None):
    """A `FleetWindow` the real parser accepts, with an optional banner.

    `fleetBroadcastBannerText` filters the window's descendants for
    `_name = "bannerLabel"`, so the banner is told from the header by the
    client's own names rather than by anything this file decides.
    `header_commander` fills the header's second label, which is where
    `fleetCommanderNameFromFleetWindowHeader` reads a commander -- left out by
    default so that the fallback (`List.head follow-fleet-broadcast-from`) is
    what names one, which is the state `fleetMateToWarpToOnThisGrid` records as
    making the recovery's on-grid branch reachable at all.
    """
    header_children = [label("Fleet (5)", (10, 10, 200, 16))]
    if header_commander is not None:
        header_children.append(label(header_commander, (10, 26, 200, 16)))

    children = [node("FleetHeaderContainer", {}, header_children,
                     region=(0, 0, 300, 46))]

    if banner is not None:
        children.append(
            node("FleetBroadcastCont", {}, [
                node("EveLabelMedium",
                     {"_name": "bannerLabel", "_setText": banner},
                     region=(10, 60, 280, 16)),
            ], region=(0, 54, 300, 24)))

    return node("FleetWindow", {}, children, region=(0, 0, 300, 400))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, doc comment stripped.

    Sliced on the signature line and ended at the next top-level declaration,
    so a claim about a rule's body cannot be satisfied by prose above it.
    """
    anchor = "\n%s :" % name
    assert anchor in source, name
    start = source.index(anchor) + 1
    rest = source[start:]
    end = rest.index("\n\n\n") if "\n\n\n" in rest else len(rest)
    return rest[:end]


def let_binding(source, name, indent=8):
    """One `let` binding's body, sliced by indentation from its `=` line.

    The **binding** line rather than the type annotation above it: the two are
    indented identically, so a reader anchored on the annotation stops on the
    very next line and asserts nothing. The readers that stop at a blank line
    or at a record's opening brace have already cost several PRs an assertion
    that passed having read nothing, so this slices by indentation -- the
    bindings asserted on below build record literals.
    """
    return indented_block(source, "%s%s =" % (" " * indent, name))


def record_field(source, name):
    """One multi-line field of the memory update's record, sliced the same way.

    Located by `= \n` -- a newline immediately after the equals -- because
    `initBotMemory` sets the same field on one line and the plain name would
    find that one first and read nothing about the update. The **header** it is
    then sliced by is the field line itself, since a header ending in a newline
    reads as indent zero and swallows the whole record.
    """
    header = "    , %s =" % name
    assert header + "\n" in source, name
    return indented_block(source[source.index(header + "\n"):], header)


def indented_block(source, header):
    """From `header` to the next line indented no further than `header` is.

    The readers that stop at a blank line or at a record's opening brace have
    already cost several PRs an assertion that passed having read nothing, so
    this slices by indentation -- the bindings asserted on below build record
    literals and their `case` arms are separated by blank lines.
    """
    assert header in source, header
    start = source.index(header)
    first = header.split("\n")[-1]
    indent = len(first) - len(first.lstrip())
    lines = source[start:].split("\n")
    while lines and not lines[0].strip():
        lines = lines[1:]
    out = [lines[0]]
    for line in lines[1:]:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
            break
        out.append(line)
    return "\n".join(out)


def step(recovering="True", named="True", on_grid="False", banner="False",
         remembers="False", warping="False", asked=0):
    """The shipped rule, as one expression over five facts and a count."""
    return ("retreatRecoveryStep { recovering = %s, commanderIsNamed = %s"
            ", commanderIsOnThisGrid = %s, bannerNamesTheCommander = %s"
            ", remembersWhereTheCommanderWas = %s, shipIsWarpingOrJumping = %s"
            ", askedReadings = %s }"
            % (recovering, named, on_grid, banner, remembers, warping, asked))


def place_after(seen=None, on_grid="False", before=None):
    """`fleetPlaceBroadcastAfterReading`, as one expression."""
    def literal(value):
        if value is None:
            return "Nothing"
        pilot, place = value
        return 'Just { pilot = "%s", place = "%s" }' % (pilot, place)

    return ("fleetPlaceBroadcastAfterReading { seenThisReading = %s"
            ", commanderIsOnGrid = %s, before = %s }"
            % (literal(seen), on_grid, literal(before)))


def show_place(expression):
    """A `Maybe { pilot, place }` rendered as a comparable string."""
    return ('(case %s of\n'
            '    Nothing ->\n'
            '        "NOTHING"\n'
            '    Just seen ->\n'
            '        seen.pilot ++ " @ " ++ seen.place)'
            % expression)


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one decision arm costs.

    `recoverFromRetreat` takes a whole `BotDecisionContext` and a `ShipUI`, so a
    case cannot ask it anything without both. Every field of the context is
    either the shipped default (`defaultBotSettings`, `initBotMemory`) or the
    emptiest value its type has, so nothing in the fixture can decide the answer
    except the reading and the three memory fields a case sets --
    `test_wingman_answers_a_backup_call`'s arrangement, for its reason. The
    `ShipUI` comes out of the same really parsed reading, so the arm is handed
    what the bot would have been handed.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.PromptParser",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "settings = { defaultBotSettings | followFleetBroadcastFrom ="
        ' [ "%s" ] }' % COMMANDER,
        "memoryWith = \\recovering placeMemory asked ->"
        " { initBotMemory | recoveringFromRetreat = recovering"
        " , fleetPlaceBroadcast = placeMemory"
        " , retreatRecoveryAskedReadings = asked }",
        "contextWith = \\recovering remembered asked parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memoryWith recovering remembered asked"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "saidBy = \\pilot place -> Just { pilot = pilot, place = place }",
        "armWith = \\recovering place asked parsed -> parsed |> Maybe.andThen"
        " (\\p -> p.shipUI |> Maybe.andThen"
        " (recoverFromRetreat (contextWith recovering place asked p)))",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeArm = \\recovering place asked parsed ->"
        " armWith recovering place asked parsed"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "ARM STOOD DOWN"',
        "rootWith = \\recovering place asked parsed -> parsed |> Maybe.andThen"
        " (\\p -> p.shipUI |> Maybe.map"
        " (wingmanDecisionRootInSpace (contextWith recovering place asked p)))"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "NO READING"',
        "clauseWith = \\recovering place asked parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeRetreatRecovery (contextWith recovering place asked p))"
        ' |> Maybe.withDefault "NO READING"',
        "stepWith = \\recovering place asked parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " retreatRecoveryStepNow (contextWith recovering place asked p))",
        "placeOf = \\parsed -> parsed"
        " |> Maybe.andThen fleetPlaceBroadcastAnyPilot",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-retreat-recovery-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


class ReplCase(unittest.TestCase):
    """One repl for the whole class, opened once.

    `definitions` is a class attribute rather than a preamble entry, so a
    subclass that needs readings supplies them per question -- `ElmRepl.script`
    folds bindings into the one `let ... in` entry that asks it, which is what
    #172 measured as the cost of a question.
    """

    definitions = ()

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def bound(self):
        """`retreatRecoveryAskedReadingsBound`, read out of the running bot."""
        return int(self.repl.values(["retreatRecoveryAskedReadingsBound"],
                                    r"(\d+) : Int")[0])

    def answers(self, expressions):
        """Each step expression rendered as its constructor's name."""
        return self.repl.strings(
            ["(case %s of\n"
             "    NotRecoveringFromARetreat ->\n"
             '        "NotRecoveringFromARetreat"\n'
             "    NothingNamesTheCommander ->\n"
             '        "NothingNamesTheCommander"\n'
             "    GaveUpOnRejoiningTheCommander ->\n"
             '        "GaveUpOnRejoiningTheCommander"\n'
             "    AlreadyOnTheWayBackToTheCommander ->\n"
             '        "AlreadyOnTheWayBackToTheCommander"\n'
             "    RejoinTheCommanderOnThisGrid ->\n"
             '        "RejoinTheCommanderOnThisGrid"\n'
             "    WarpToTheCommanderFromTheBroadcast ->\n"
             '        "WarpToTheCommanderFromTheBroadcast"\n'
             "    RouteToWhereTheCommanderLastSaidHeWas ->\n"
             '        "RouteToWhereTheCommanderLastSaidHeWas"\n'
             "    NowhereToRejoinTheCommander ->\n"
             '        "NowhereToRejoinTheCommander")' % expression
             for expression in expressions],
            definitions=self.definitions)


class TheRuleAnswersOneThingPerReadingTest(ReplCase):
    """`retreatRecoveryStep` itself, executed at each of its eight answers.

    Asked as one rendering per case rather than as a `Bool` per constructor, so
    a rule that answered two things at once -- or none -- fails rather than
    passing on whichever one a case happened to name.
    """

    def test_a_ship_that_is_not_recovering_is_left_alone(self):
        self.assertEqual(self.answers([step(recovering="False")]),
                         ["NotRecoveringFromARetreat"])

    def test_a_commander_nothing_names_is_not_a_spent_budget(self):
        """Permission before the give-up -- `backupCallStep`'s own ordering.

        Reporting an unset `follow-fleet-broadcast-from` as a spent budget would
        send an operator to look at the bound when what is wrong is the setting.
        Asked with the budget spent so the two orderings are distinguishable.
        """
        self.assertEqual(
            self.answers([step(named="False", asked=99)]),
            ["NothingNamesTheCommander"])

    def test_the_bound_is_asked_at_its_boundary(self):
        """Both sides of the comparison, and fixed values either side of it.

        A case that asks only `constant - 1` and `constant` passes for any
        constant, including one that admits everything -- the hole four of
        #120's own cases had.
        """
        bound = self.bound()
        self.assertGreater(bound, 5)
        self.assertEqual(
            self.answers([step(remembers="True", asked=asked)
                          for asked in (0, 5, bound - 1, bound,
                                        bound + 1, 999)]),
            ["RouteToWhereTheCommanderLastSaidHeWas"] * 3
            + ["GaveUpOnRejoiningTheCommander"] * 3)

    def test_the_give_up_outranks_every_actionable_moment(self):
        """A spent budget must never be masked by a moment that looks
        actionable -- `approachFleetCommanderStep`'s ordering, and the whole
        point of a bound on an arm this high in the tree."""
        self.assertEqual(
            self.answers([step(on_grid="True", banner="True",
                               remembers="True", warping="True", asked=99)]),
            ["GaveUpOnRejoiningTheCommander"])

    def test_a_ship_in_warp_is_told_to_do_nothing(self):
        """The manoeuvre is the recovery executing, so it outranks every way of
        starting another one."""
        self.assertEqual(
            self.answers([step(on_grid="True", banner="True",
                               remembers="True", warping="True")]),
            ["AlreadyOnTheWayBackToTheCommander"])

    def test_the_commander_on_this_grid_is_the_on_grid_half(self):
        self.assertEqual(
            self.answers([step(on_grid="True", banner="True",
                               remembers="True")]),
            ["RejoinTheCommanderOnThisGrid"])

    def test_the_banner_is_asked_before_the_remembered_place(self):
        """After `warpAwayFromDanger` this ship is usually in the commander's
        own system and on another grid, where the banner's `Warp to Member` is
        right and a route to a system the ship is already in is empty."""
        self.assertEqual(
            self.answers([step(banner="True", remembers="True")]),
            ["WarpToTheCommanderFromTheBroadcast"])

    def test_a_remembered_place_is_the_fallback(self):
        self.assertEqual(self.answers([step(remembers="True")]),
                         ["RouteToWhereTheCommanderLastSaidHeWas"])

    def test_nothing_at_all_is_named_rather_than_waited_on(self):
        """#381's own state: recovering, commander off grid, nothing to fly
        to."""
        self.assertEqual(self.answers([step()]),
                         ["NowhereToRejoinTheCommander"])


class TheCounterCountsWhatTheArmSpendsTest(ReplCase):
    """Which answers may advance the budget, executed rather than read.

    #389 is the shape this refuses: a counter advanced from state alone reported
    a give-up at 46 readings against a bound of 20 without the arm having been
    asked once.
    """

    def spends(self, names):
        return self.repl.evaluate(
            ["List.member %s retreatRecoveryAnswersThatSpendAReading" % name
             for name in names])

    def test_only_the_answers_that_dispatch_are_counted(self):
        self.assertEqual(
            self.spends(["RejoinTheCommanderOnThisGrid",
                         "WarpToTheCommanderFromTheBroadcast",
                         "RouteToWhereTheCommanderLastSaidHeWas"]),
            [True, True, True])

    def test_nowhere_to_rejoin_spends_nothing(self):
        """The reading this arm has nothing to do with. Charging it would be
        #389 exactly, and it needs no budget: it already hands the reading
        back, so the arms below run whether or not anything is remembered."""
        self.assertEqual(self.spends(["NowhereToRejoinTheCommander"]), [False])

    def test_the_refusals_and_the_warp_spend_nothing(self):
        self.assertEqual(
            self.spends(["NotRecoveringFromARetreat",
                         "NothingNamesTheCommander",
                         "GaveUpOnRejoiningTheCommander",
                         "AlreadyOnTheWayBackToTheCommander"]),
            [False, False, False, False])


class TheRememberedPlaceIsInvalidatedTest(ReplCase):
    """`fleetPlaceBroadcastAfterReading`, folded over the readings a session
    passes through rather than asked once."""

    def test_a_place_named_this_reading_is_remembered(self):
        self.assertEqual(
            self.repl.strings(
                [show_place(place_after(seen=(COMMANDER, PLACE)))]),
            ["%s @ %s" % (COMMANDER, PLACE)])

    def test_a_reading_that_names_no_place_holds_the_old_one(self):
        """The banner persists between broadcasts, so a reading naming no place
        is not a reading saying the fleet moved."""
        self.assertEqual(
            self.repl.strings(
                [show_place(place_after(before=(COMMANDER, PLACE)))]),
            ["%s @ %s" % (COMMANDER, PLACE)])

    def test_the_reunion_drops_the_remembered_place(self):
        """The invalidation, and the one this arm needs: on the reading the
        commander gets an overview row -- the same reading
        `recoveringFromRetreat` clears -- wherever he last said he was is
        superseded by his being right there. So no place this arm routes to was
        broadcast before the last time this ship was with its commander."""
        self.assertEqual(
            self.repl.strings(
                [show_place(place_after(on_grid="True",
                                        before=(COMMANDER, PLACE)))]),
            ["NOTHING"])

    def test_a_place_named_this_reading_beats_the_reunion(self):
        """A commander who broadcasts `Travel to X` on the very reading this
        ship rejoins him has said where the fleet is going next, which is the
        most useful thing this memory ever holds."""
        self.assertEqual(
            self.repl.strings(
                [show_place(place_after(seen=(COMMANDER, "Riramia"),
                                        on_grid="True",
                                        before=(COMMANDER, PLACE)))]),
            ["%s @ Riramia" % COMMANDER])

    def test_another_pilots_place_displaces_the_commanders(self):
        """The stated cost of one slot. The recovery then has nothing and gives
        up rather than routing somewhere arbitrary, which is the refusal
        `goToFleetMate`'s own doc comment already makes."""
        self.assertEqual(
            self.repl.strings(
                [show_place(place_after(seen=(OTHER_MATE, "Sarum Prime"),
                                        before=(COMMANDER, PLACE)))]),
            ["%s @ Sarum Prime" % OTHER_MATE])

    def test_a_session_that_never_hears_a_place_remembers_nothing(self):
        self.assertEqual(self.repl.strings([show_place(place_after())]),
                         ["NOTHING"])


class TheBroadcastFormsThatCarryAPlaceTest(ReplCase):
    """Which broadcasts name a place, asked of the real parser.

    The readings come from `EveOnline.ParseUserInterface`, so what these assert
    on is what the bot would have been handed.
    """

    def place_in(self, banner):
        return self.repl.strings(
            [show_place("placeOf readingWithBanner")],
            definitions=[reading_binding(
                "readingWithBanner", [fleet_window(banner=banner)])])[0]

    def company_place_in(self, banner):
        """`fleetMatePlaceAnyPilot`, the accessor this one is not."""
        return self.repl.strings(
            ['(readingWithBanner |> Maybe.andThen fleetMatePlaceAnyPilot'
             ' |> Maybe.withDefault "NOTHING")'],
            definitions=[reading_binding(
                "readingWithBanner", [fleet_window(banner=banner)])])[0]

    def test_the_travel_form_carries_a_place(self):
        """#381's own evidence that a place was available: the reading three
        wingmen had nothing to fly to carried this banner, and a fourth pilot
        was routing to it."""
        self.assertEqual(
            self.place_in("%s: Travel to %s" % (COMMANDER, PLACE)),
            "%s @ %s" % (COMMANDER, PLACE))

    def test_the_at_location_form_carries_a_place(self):
        self.assertEqual(
            self.place_in("%s is at location Amarr" % COMMANDER),
            "%s @ Amarr" % COMMANDER)

    def test_the_in_position_form_carries_a_place(self):
        self.assertEqual(
            self.place_in("%s is in position at Stargate Riramia" % COMMANDER),
            "%s @ Riramia" % COMMANDER)

    def test_a_broadcast_that_names_no_place_carries_none(self):
        self.assertEqual(self.place_in("%s needs backup" % COMMANDER),
                         "NOTHING")
        self.assertEqual(self.place_in("Target Heather Hemorphite (Tristan)"),
                         "NOTHING")

    def test_the_two_shared_forms_agree_with_the_company_accessor(self):
        """`fleetMatePlaceAnyPilot` answers the two _company_ verbs only, and
        this one adds `TravelTo`. Where both answer they must answer the same
        place, or two rules would disagree about what the client said."""
        for banner, place in [
                ("%s is at location Amarr" % COMMANDER, "Amarr"),
                ("%s is in position at Stargate Riramia" % COMMANDER,
                 "Riramia")]:
            self.assertEqual(self.company_place_in(banner), place)
            self.assertEqual(self.place_in(banner),
                             "%s @ %s" % (COMMANDER, place))

    def test_the_company_accessor_does_not_read_the_travel_form(self):
        """The deliberate difference, pinned so a later change that folds one
        into the other has to notice it is changing what the company verbs ask
        the host to route to."""
        self.assertEqual(
            self.company_place_in("%s: Travel to %s" % (COMMANDER, PLACE)),
            "NOTHING")


class ThePlaceIsTheCommandersOrItIsNotFlownToTest(ReplCase):
    """`rememberedCommanderPlaceFromReading`, the filter the memory update does
    not make."""

    definitions = (reading_binding("readingPlain", [fleet_window()]),)

    def flown_to(self, pilot):
        return self.repl.strings(
            ['(readingPlain |> Maybe.andThen (\\p ->'
             ' rememberedCommanderPlaceFromReading [ "%s" ]'
             ' (saidBy "%s" "%s") p)'
             ' |> Maybe.withDefault "NOTHING")'
             % (COMMANDER, pilot, PLACE)],
            definitions=self.definitions)[0]

    def test_the_commanders_own_place_is_flown_to(self):
        self.assertEqual(self.flown_to(COMMANDER), PLACE)

    def test_another_pilots_place_is_not_flown_to(self):
        """Routing to wherever anybody last broadcast is the "somewhere
        arbitrary" `goToFleetMate`'s own doc comment declines to fly to."""
        self.assertEqual(self.flown_to(OTHER_MATE), "NOTHING")

    def test_the_commander_is_matched_exactly(self):
        """A substring match would fly this ship to a place named by a pilot
        whose name merely contains the commander's --
        `fleetInviteSenderFromMessageBox`'s reason."""
        self.assertEqual(self.flown_to("Gal Bistoteles"), "NOTHING")
        self.assertEqual(self.flown_to("Gal"), "NOTHING")


class TheArmActsOnWhatTheRuleSaysTest(ReplCase):
    """`recoverFromRetreat` run for real, on really parsed readings.

    Each case sets exactly one thing differently from #381's own state, so what
    the assertions are about is the change rather than the fixture.
    """

    # #381's reading: recovering, the commander nowhere on the overview,
    # somebody else's banner still up -- which is exactly the caller
    # `fleetMateBroadcastBannerElement` exists to keep the banner cascade away
    # from. The other two differ from it in one thing each.
    definitions = (
        reading_binding("readingOffGrid", [
            fleet_window(banner="%s is at location Amarr" % OTHER_MATE),
            overview([("2,700 m", "Sunder Alvi", "Frigate")]),
            ship_ui_indicating(None),
        ]),
        reading_binding("readingCommanderBanner", [
            fleet_window(banner="%s is at location Amarr" % COMMANDER),
            overview([("2,700 m", "Sunder Alvi", "Frigate")]),
            ship_ui_indicating(None),
        ]),
        reading_binding("readingOnGrid", [
            fleet_window(banner="%s is at location Amarr" % OTHER_MATE),
            overview([("2,700 m", COMMANDER, "Frigate")]),
            ship_ui_indicating(None),
        ]),
    )

    def arm(self, reading="readingOffGrid", recovering="True",
            place="Nothing", asked=0):
        return self.repl.strings(
            ["describeArm %s %s %s %s" % (recovering, place, asked, reading)],
            definitions=self.definitions)[0]

    def test_the_fixtures_are_real(self):
        """The readings themselves, before anything is concluded from them: a
        case built on a tree the parser makes nothing of would pass or fail for
        reasons that have nothing to do with the rule."""
        self.assertEqual(
            self.repl.evaluate([
                "readingOffGrid /= Nothing",
                "(readingOffGrid |> Maybe.andThen .shipUI) /= Nothing",
                '(readingOffGrid |> Maybe.map (pilotIsOnOverview "%s")'
                " |> Maybe.withDefault True) == False" % COMMANDER,
                '(readingOnGrid |> Maybe.map (pilotIsOnOverview "%s")'
                " |> Maybe.withDefault False) == True" % COMMANDER,
            ], definitions=self.definitions),
            [True, True, True, True])

    def test_the_arm_no_longer_routes_to_the_empty_place(self):
        """#381's own decision line, gone. It said the ship was "not on this
        grid, and nothing names a place to route to" and then waited."""
        self.assertNotIn("nothing names a place to route to", self.arm())

    def test_nothing_to_rejoin_hands_the_reading_back(self):
        self.assertEqual(self.arm(), "ARM STOOD DOWN")

    def test_a_remembered_place_is_flown_to(self):
        """The primary fix: the same reading, with the commander's own place
        remembered, now flies somewhere."""
        line = self.arm(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE))
        self.assertIn("Recovering from a retreat", line)
        self.assertIn(PLACE, line)

    def test_a_place_another_pilot_named_is_not_flown_to(self):
        self.assertEqual(
            self.arm(place='(saidBy "%s" "%s")' % (OTHER_MATE, PLACE)),
            "ARM STOOD DOWN")

    def test_the_commanders_own_banner_is_warped_to(self):
        line = self.arm(reading="readingCommanderBanner")
        self.assertIn("Recovering from a retreat", line)
        self.assertIn("broadcast banner", line)

    def test_a_stale_banner_is_not_warped_to(self):
        """`recoverFromRetreat` is exactly the caller that arrives with somebody
        else's banner still up, and driving the cascade off one would warp this
        ship to whoever last broadcast."""
        self.assertEqual(self.arm(), "ARM STOOD DOWN")

    def test_the_on_grid_half_is_unchanged(self):
        self.assertIn("Recovering from a retreat",
                      self.arm(reading="readingOnGrid"))

    def test_a_ship_not_recovering_is_left_alone(self):
        self.assertEqual(
            self.arm(recovering="False",
                     place='(saidBy "%s" "%s")' % (COMMANDER, PLACE)),
            "ARM STOOD DOWN")

    def test_the_give_up_hands_the_reading_back(self):
        """Past the bound, with a place remembered that the arm would otherwise
        fly to."""
        bound = self.bound()
        self.assertEqual(
            self.arm(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE),
                     asked=bound),
            "ARM STOOD DOWN")


class TheArmsBelowGetTheirReadingsBackTest(ReplCase):
    """The control the whole of #381 turns on, run rather than asserted.

    The arm answering `Nothing` is only worth anything if something below it
    then acts, so the real `wingmanDecisionRootInSpace` is run on the same
    reading and its decision is compared against the recovery's own line.
    """

    # A called target with a row on this grid, which
    # `bringCalledTargetUnderFire` answers -- an arm placed below
    # `recoverFromRetreat` in the root.
    definitions = (
        reading_binding("readingWithSomethingToDo", [
            fleet_window(banner="Target Sunder Alvi (Tristan)"),
            overview([("2,700 m", "Sunder Alvi", "Frigate")]),
            ship_ui_indicating(None),
        ]),
    )

    def root(self, recovering="True", place="Nothing", asked=0):
        return self.repl.strings(
            ["rootWith %s %s %s readingWithSomethingToDo"
             % (recovering, place, asked)],
            definitions=self.definitions)[0]

    def test_the_control_arm_acts_when_the_recovery_stands_down(self):
        """The positive control: with nothing recovering at all, the root
        reaches something below and acts on it."""
        line = self.root(recovering="False")
        self.assertNotIn("Recovering from a retreat", line)
        self.assertNotEqual(line, "NO READING")

    def test_the_arms_below_are_reachable_once_the_recovery_gives_up(self):
        """The whole of #381: recovering, nothing to rejoin, and the root
        reaches the same decision it reaches with no recovery at all. Compared
        against the control rather than asserted as a shape, so a root that had
        stopped working entirely could not pass."""
        self.assertEqual(self.root(), self.root(recovering="False"))

    def test_the_arms_below_are_reachable_once_the_budget_is_spent(self):
        bound = self.bound()
        self.assertEqual(
            self.root(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE),
                      asked=bound),
            self.root(recovering="False"))

    def test_a_recovery_that_can_act_still_owns_the_reading(self):
        """The negative control, and what stops the two above passing on a root
        that never reaches this arm at all."""
        self.assertIn(
            "Recovering from a retreat",
            self.root(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE)))


class TheStatusLineNamesTheCaseTest(ReplCase):
    """`describeRetreatRecovery`, rendered rather than asserted by substring
    over the arm.

    The arm answers `Nothing` for five of its eight cases, and from outside the
    decision tree a ship that is not recovering, one with no commander named,
    one whose budget is spent, one already in warp and one with nowhere at all
    to fly are the same silence.
    """

    definitions = (
        reading_binding("readingForClause", [
            fleet_window(banner="%s is at location Amarr" % OTHER_MATE),
            overview([("2,700 m", "Sunder Alvi", "Frigate")]),
            ship_ui_indicating(None),
        ]),
    )

    def clause(self, recovering="True", place="Nothing", asked=0):
        return self.repl.strings(
            ["clauseWith %s %s %s readingForClause"
             % (recovering, place, asked)],
            definitions=self.definitions)[0]

    def test_the_nowhere_case_says_so(self):
        line = self.clause()
        self.assertIn("nothing names a place to fly to", line)
        self.assertIn("handed back", line)

    def test_the_give_up_names_itself_and_its_count(self):
        bound = self.bound()
        line = self.clause(asked=bound)
        self.assertIn("GAVE UP", line)
        self.assertIn(str(bound), line)

    def test_the_remembered_place_and_its_sender_are_named(self):
        """An operator who cannot see whose place is remembered cannot tell a
        commander who has said nothing from a place refused for being somebody
        else's."""
        line = self.clause(place='(saidBy "%s" "%s")' % (OTHER_MATE, PLACE))
        self.assertIn(PLACE, line)
        self.assertIn(OTHER_MATE, line)
        self.assertIn("not this fleet's commander", line)

    def test_the_commanders_own_place_is_not_reported_as_refused(self):
        line = self.clause(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE))
        self.assertIn(PLACE, line)
        self.assertNotIn("not this fleet's commander", line)

    def test_a_ship_not_recovering_says_so_rather_than_nothing(self):
        self.assertIn("not flying back from a retreat",
                      self.clause(recovering="False"))

    def test_the_budget_is_on_every_reading_the_arm_is_working(self):
        bound = self.bound()
        line = self.clause(place='(saidBy "%s" "%s")' % (COMMANDER, PLACE),
                           asked=7)
        self.assertIn("7 of %d" % bound, line)


class TheWiringIsWhereItSaysItIsTest(unittest.TestCase):
    """The parts a repl cannot reach: placement, the counter's rule, and the
    status line. Read through a whitespace-collapsing reader, so the next
    `elm-format` pass cannot break an assertion.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(WINGMAN_BOT_ELM)

    def test_the_arm_sits_below_the_retreat(self):
        """The one arm that outranks it. A recovery placed above the retreat
        would fly a damaged ship back toward the fight it just broke off from,
        which is the ordering saxrat's own retreat records having needed."""
        root = declaration(self.source, "wingmanDecisionRootInSpace")
        self.assertIn("retreatToTheCommander", root)
        self.assertIn("recoverFromRetreat", root)
        self.assertLess(root.index("retreatToTheCommander"),
                        root.index("recoverFromRetreat"))

    def test_the_arm_sits_above_the_ordinary_arms(self):
        """A ship flying back from a break-off is not pulled into the next
        fight or the next broadcast before it gets there."""
        root = declaration(self.source, "wingmanDecisionRootInSpace")
        self.assertLess(root.index("recoverFromRetreat"),
                        root.index("wingmanDecisionRootInSpaceOrdinary"))

    def test_the_counter_asks_the_shipped_rule(self):
        """Not a second copy of the conditions beside it -- #102's defect."""
        counter = record_field(self.source, "retreatRecoveryAskedReadings")
        self.assertIn("recoveringStepNow", counter)
        self.assertIn("retreatRecoveryAnswersThatSpendAReading", counter)
        # The rule is asked, never restated: none of the facts it reads may
        # appear as a condition here.
        for fact in ["pilotIsOnOverview", "fleetMateBroadcastBannerElement",
                     "recoveringFromRetreatNow ", "fleetPlaceBroadcastNow "]:
            self.assertNotIn(fact, counter)

    def test_the_memory_side_step_is_the_same_function_the_arm_asks(self):
        assembled = let_binding(self.source, "recoveringStepNow")
        self.assertIn("retreatRecoveryStepFromReading", assembled)
        self.assertIn("botMemoryBefore.retreatRecoveryAskedReadings", assembled)

    def test_a_warp_cannot_undo_a_spent_budget(self):
        """The reset for a ship in warp is reached through the rule, which asks
        the give-up first -- so a warp cannot turn a spent budget back into an
        unspent one."""
        body = collapsed(indented_block(
            self.source, "retreatRecoveryStep recoveryCase ="))
        self.assertLess(body.index("retreatRecoveryHasBeenGivenUpOn"),
                        body.index("shipIsWarpingOrJumping"))

    def test_the_counter_is_held_once_the_budget_is_spent(self):
        """Held rather than reset, or the give-up would un-give-up on the very
        next reading and the status line's "after N readings" would be
        meaningless -- #389's own lesson."""
        counter = collapsed(record_field(
            self.source, "retreatRecoveryAskedReadings"))
        self.assertTrue(
            counter.rstrip().endswith(
                "botMemoryBefore.retreatRecoveryAskedReadings"),
            counter)

    def test_the_give_up_leaves_the_latch_alone(self):
        """`recoveringFromRetreat` is cleared by the one thing that means the
        recovery worked -- the commander getting an overview row -- and by
        nothing else. Clearing it on the give-up would report this ship as
        rejoined when it is not, and would silently change what
        `fleetMateToWarpToOnThisGrid` answers."""
        latch = collapsed(let_binding(self.source, "recoveringFromRetreatNow"))
        self.assertIn("retreatIsDecided", latch)
        self.assertIn("commanderIsOnGrid", latch)
        for forbidden in ["retreatRecoveryAskedReadings",
                          "retreatRecoveryHasBeenGivenUpOn",
                          "GaveUpOnRejoiningTheCommander"]:
            self.assertNotIn(forbidden, latch)

    def test_the_place_and_the_latch_clear_on_one_condition(self):
        """One event -- this ship is back with its commander -- so two
        conditions for it would be two definitions drifting apart."""
        place = collapsed(let_binding(self.source, "fleetPlaceBroadcastNow"))
        self.assertIn("commanderIsOnGrid = commanderIsOnGrid", place)
        self.assertIn("botMemoryBefore.fleetPlaceBroadcast", place)

    def test_the_arm_is_visible_in_the_status_line(self):
        self.assertIn("describeRetreatRecovery context",
                      collapsed(self.source))

    def test_the_arm_hands_back_rather_than_waiting(self):
        """Every answer that is not an action is a `Nothing`, so nothing under
        this arm is starved -- #360's lesson, and #385's arrangement."""
        arm = declaration(self.source, "recoverFromRetreat")
        self.assertNotIn("waitForProgressInGame", arm)

    def test_the_bound_is_the_one_the_two_mechanisms_were_sized_at(self):
        """Written as `fleetMateWarpAskedReadingsBound` rather than as a number,
        `backupCallAskedReadingsBound`'s arrangement: this arm drives the same
        banner cascade and the same route-marker cascade, and a second number
        would be two opinions about one pair of mechanisms on a bot with no
        corpus of its own."""
        bound = collapsed(
            declaration(self.source, "retreatRecoveryAskedReadingsBound"))
        self.assertIn("fleetMateWarpAskedReadingsBound", bound)
        self.assertFalse(re.search(r"=\s*\d", bound), bound)


if __name__ == "__main__":
    unittest.main()
