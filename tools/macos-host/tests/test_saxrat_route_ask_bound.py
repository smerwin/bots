"""The bound on saxrat's route ask counts the readings the ask fires on.

Issue #273. `routeAskGiveUpReadings` (20) is the only thing that stops
`setRouteToNextHuntingGround` asking the host for a route, and what it is
compared against is `destinationAskReadings`. That counter advanced only while
`standingInADeadEnd`, which demanded an **empty probe scanner**, while the ask
fires whenever *no anomaly matches the settings* -- the wider state. With a
narrow `anomaly-name` and two signatures on the scanner that do not match it,
every reading took the counter's `else` branch and reset it to zero.

So the counter oscillated 0 -> 1 -> 0 and the comparison
`routeAskGiveUpReadings < destinationAskReadings` could never be true. One run
spent its last 47,000 log lines asking 439 times; across 445 ask decisions the
counter read 0 on 442 of them and 1 on 3.

**The doc comment beside it anticipated the narrowing and mis-priced it.** It
said the counter "can under-count and delay the give-up", which would have been
tolerable. Narrowing to an empty scanner does not delay the give-up, it removes
it: a non-empty scanner is the steady state in the very situation the ask exists
for. Not late, never -- which is #11's own mistake in the shape that comment
cites while walking into it. The comment is corrected in `Bot.elm` rather than
here, and `TheExpiredJustificationIsCorrected` refuses the sentence that carried
it.

## What separates the two constructions

`anomaliesWorthHunting` is one filter, read by the decision that picks an
anomaly and by the memory update that bounds the ask. The condition it replaces
is executed **beside** it over the same really-parsed readings
(`deadEndBeforeThisChange`), because a session that reaches the bound proves
nothing on its own: what makes it evidence is that the old construction, on the
same readings, peaks at 1 and ends at 0.

Two guards are shared rather than restated, which is the drift #273 is about:

- `gridStillHasSomethingToDo` -- the fight that is still going on with the
  site's own signature already off the scanner. This is the one state the ask's
  condition does *not* imply, and it is exactly the "happily fighting" case the
  replaced comment narrowed for. The decision reads it at the site that used to
  spell the same three-way disjunction inline.
- `shipIsWarpingOrJumping` -- `decideNextActionWhenInSpace` answers
  `HOOOOONK in warp` long before the ask, and a warp across a system runs longer
  than 20 readings at this bot's step delay, so counting through one would latch
  the give-up on a bot that was travelling perfectly well.

## The counter is keyed on the ask, not on the dead end

`destinationAskedForNow` is `Just` exactly when the ship is in a dead end **and**
the circuit has somewhere to send it, and the counter is keyed on that. PR #263's
own recount found the other half of this defect from the opposite side: runs 12,
26 and 27 latched the give-up having issued **no ask at all**, two of them with
no `hunt-system` configured, because the counter ran while nothing was being
asked for. `TheCounterCountsAsksAndNotDeadEnds` pins both directions.

That is also what keeps #263's constraint true. The memory update names the
destination the decision will ask for, and the framework hands the decision the
memory this update has already written -- so on the reading the ship arrives in
the system the pointer names, the two are called with indices one apart.
`TheTwoCallersStillNameTheSameDestination` executes that agreement against the
memory the fold produced rather than reading the picker's call site, which
#263's own file already reads.

## What the bot does when the give-up finally fires

It tethers, on that reading and on every reading after: the latch is
`before || ...`, so it cannot come undone, and `setRouteToNextHuntingGround`
tests it first and answers `tetherAtStructure`. Both halves are asserted --
`TheGiveUpHoldsForTheRestOfTheSession` folds a session that goes back to having
anomalies worth hunting and requires the latch to hold on every reading after
it first sets, and `TheGiveUpActsRatherThanWaits` reads the arm. PR #257 shipped
green and blocked the bot for 108 minutes because a step on a hot path could
decline forever; a give-up that is reached on every reading for the rest of a
session is exactly that hot path.

The rules are executed through the real `Bot.elm` in `elm repl`, and the
readings they are folded over are built by running UI trees through the **real**
`EveOnline.ParseUserInterface`. The branch itself takes a whole
`BotDecisionContext` and is read out of the source through a
whitespace-collapsing reader.

Confirmed by mutation, sixteen of them, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client or a running bot. The corpus case reads
the recorded runs in `~/eve-bot-logs`, and only reads them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, label, node,
    ship_ui, source_of)
from test_saxrat_combat_stalemate import overview as combat_overview, rat_rows
from test_saxrat_route_to_the_system_we_are_in import (
    CIRCUIT, ELSEWHERE, location_panel)

# The bound this whole file is about, read back out of `Bot.elm` by
# `TheBoundIsTheOneTheSourceCarries` rather than trusted from here.
GIVE_UP_READINGS = 20

# Anomaly names read off a live probe scanner for #188, kept in
# `test_saxrat_anomaly_name_wildcard`. `anomalyNameMatches` is an exact match
# unless the entry ends in `*`, so a bot configured for the first of these
# leaves the other two on the scanner -- which is the ordinary case the issue
# is about, and the reason the old counter never advanced.
HUNTED = "Sansha Hideaway"
NOT_HUNTED = ("Sansha Refuge", "Drone Assembly")

# The probe scanner's own columns, in the order the client draws them. The
# geometry is explicit because `parseProbeScanResult` maps a cell to a header by
# asking which header's region the cell's midpoint falls inside.
SCAN_COLUMNS = (("ID", 0, 60), ("Name", 60, 220), ("Group", 280, 140),
                ("Distance", 420, 120))

# What `findReasonToIgnoreProbeScanResult` needs of a row before it will look at
# the name at all: a combat anomaly, at a distance in AU.
COMBAT_GROUP = "Combat Site"
DISTANT = "3.5 AU"

# The client's own words for a route that exists, quoted from run 31 in
# `test_saxrat_route_panel_shows_a_route`.
ROUTE_LABELS = ["Route <fontsize=12>5 Jumps"]

# The ship UI's indication container while warping, captured off the live
# client during saxrat run 29 and kept in `test_arrival_pilot_window`.
WARPING_INDICATION = ("Warp Drive Active",
                      "Destination: AreraDistance: 416 km",
                      "Mikhir",
                      "Sansha Hideaway")


def scan_result(name, result_id, index):
    """One `ScanResultNew` row the real parser reads four cells out of.

    Deliberately **not** inside the results scroll: `parseProbeScannerWindow
    FromUITreeRoot` takes the scroll node's own contained texts as the column
    headers, so a row nested under it would have its cells read as headers and
    every cell lookup would then miss.
    """
    y = 60 + index * 20
    cells = {"ID": result_id, "Name": name, "Group": COMBAT_GROUP,
             "Distance": DISTANT}
    return node("ScanResultNew", {"_name": "scanResult"}, [
        label(cells[column], (x + 4, y, width - 8, 16))
        for column, x, width in SCAN_COLUMNS
    ], region=(0, y, 540, 16))


def probe_scanner(names):
    """The scanner window, open, holding one row per name."""
    scroll = node("Scroll", {"_name": "resultsScroll"}, [
        label(column, (x, 20, width, 16))
        for column, x, width in SCAN_COLUMNS
    ], region=(0, 20, 540, 16))
    results = [scan_result(name, "AIC-%03d" % index, index)
               for index, name in enumerate(names)]
    return node("ProbeScannerWindow", {"_name": "probeScannerWindow"}, [
        node("Container", {"_name": "ResultsContainer"}, [scroll],
             region=(0, 20, 540, 240)),
    ] + results, region=(1000, 100, 540, 300))


def info_panel(system_name, route_labels=()):
    """The location panel #262's cases build, plus a route panel beside it.

    One `InfoPanelContainer` rather than two, because the parser takes a single
    container out of the tree and a second one would decide which of the two
    halves the bot could see.
    """
    panel = location_panel(system_name)
    if route_labels:
        panel["children"].append(node("InfoPanelRoute", {}, [
            label(text, (0, 60 + index * 16, 200, 16))
            for index, text in enumerate(route_labels)
        ], region=(0, 60, 200, 64)))
    return panel


def flying(warping=False):
    """A ship UI, warping or not.

    `ship_ui` cannot express an indication, so the container is appended to what
    it builds -- `test_arrival_pilot_window`'s arrangement, and the same
    captured strings.
    """
    ui = ship_ui(100, 100, 4)
    if warping:
        ui["children"].append(
            node("IndicationContainer", {"_name": "indicationContainer"},
                 [label(text, (0, 60 + 18 * index, 200, 16))
                  for index, text in enumerate(WARPING_INDICATION)],
                 region=(0, 60, 200, 100)))
    return ui


def in_space(scanner=(), system=ELSEWHERE, route=(), rats=0, warping=False,
             ship=True):
    """The children of one in-space reading.

    `scanner=None` leaves the window out of the tree altogether, which is a
    different reading from one holding no rows and is the arm
    `decideNextActionWhenInSpace` answers `No probe window` on.
    """
    children = [info_panel(system, route)]
    if ship:
        children.append(flying(warping))
    if scanner is not None:
        children.append(probe_scanner(scanner))
    if rats:
        children.append(combat_overview(rat_rows(rats)))
    return children


class RouteAskRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus what folding a session of readings costs.

    The bindings ride in the preamble, which `imports_and_bindings` folds into
    the one `let` that asks the question -- so they cost the same single compile
    the imports do (#172).
    """

    BINDINGS = (
        # One `UpdateMemoryContext`, exactly as the framework assembles it. The
        # screenshot's two fields are functions and nothing in this path calls
        # them, which is why a reading can be folded without one.
        "askContext = \\settings reading ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = reading"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , previousStepsEffects = []"
        " , botSettings = settings }",
        # A session, written as `(repeats, reading)` pairs. The `filterMap` is
        # what a fixture that never parsed falls out of, which is why every case
        # using this asks `sessionLength` beside it -- see #174 for why a
        # fixture that never arrived and a rule that answered nothing look
        # identical from outside.
        "sessionOf = \\pairs -> pairs"
        " |> List.concatMap (\\( n, r ) -> List.repeat n r)"
        " |> List.filterMap identity",
        "sessionLength = \\pairs -> sessionOf pairs |> List.length",
        "memoryOver = \\settings pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r memory -> updateMemoryForNewReadingFromGame (askContext settings r) memory)"
        " initBotMemory",
        # The high-water mark over a session rather than its final value: a case
        # about a bot that must never latch has to say the counter never reached
        # the bound, not merely that it did not end there.
        "peakAsk = \\settings pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r ( memory, peak ) ->"
        " let now = updateMemoryForNewReadingFromGame (askContext settings r) memory"
        " in ( now, max peak now.destinationAskReadings ))"
        " ( initBotMemory, 0 )"
        " |> Tuple.second",
        # ( the latch was ever set, it held on every reading after it was ).
        "giveUpHeld = \\settings pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r ( memory, ( seen, holds ) ) ->"
        " let now = updateMemoryForNewReadingFromGame (askContext settings r) memory"
        " in ( now, ( seen || now.routeSettingGivenUp"
        " , holds && (not seen || now.routeSettingGivenUp) ) ))"
        " ( initBotMemory, ( False, True ) )"
        " |> Tuple.second",
        # The condition #273 replaced, executed over the same readings as the
        # control. Without it a session that reaches the bound says nothing
        # about the change -- any counter that only ever rises reaches it.
        "deadEndBeforeThisChange = \\r ->"
        " (r.shipUI /= Nothing)"
        " && not (routePanelShowsARoute r)"
        " && (r.probeScannerWindow"
        " |> Maybe.map (.scanResults >> List.isEmpty)"
        " |> Maybe.withDefault True)",
        "askBeforeThisChange = \\pairs -> sessionOf pairs"
        " |> List.foldl"
        " (\\r ( n, peak ) ->"
        " let now = if deadEndBeforeThisChange r then n + 1 else 0"
        " in ( now, max peak now ))"
        " ( 0, 0 )",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-route-ask-")
        # `Dict` is not re-exported by `Bot exposing (..)`, and the anomaly
        # filter takes one.
        kwargs.setdefault("preamble",
                          PREAMBLE + ("import Dict",) + self.BINDINGS)
        super().__init__(**kwargs)

    @staticmethod
    def settings(hunt=CIRCUIT, anomaly=(HUNTED,)):
        return (
            "{ defaultBotSettings"
            " | huntSystemNames = [ %s ]"
            " , anomalyNames = [ %s ] }"
            % (", ".join('"%s"' % name for name in hunt),
               ", ".join('"%s"' % name for name in anomaly)))

    def integers(self, expressions, definitions=()):
        """`Int` answers, as the integers they are.

        Asked as strings rather than as `<` comparisons: a case that only ever
        asks whether the counter passed a constant read out of the same file
        passes for *any* constant, including one that admits everything. That
        hole cost four of #120's cases once.
        """
        return [int(answer) for answer in self.strings(
            ["String.fromInt (%s)" % expression for expression in expressions],
            definitions)]


def readings():
    """Every reading these cases fold, as `definitions` for one repl entry."""
    return [
        # The issue's own pair. `dry` is the ordinary reading of a system whose
        # scanner holds signatures the settings do not name; `empty` is the only
        # reading the counter used to advance on.
        RouteAskRepl.reading_binding("dry", in_space(scanner=NOT_HUNTED)),
        RouteAskRepl.reading_binding("empty", in_space(scanner=())),
        # An anomaly this bot would go and hunt, so there is no dead end.
        RouteAskRepl.reading_binding("hunting", in_space(scanner=[HUNTED])),
        # The site's signature has gone off the scanner and the fight has not:
        # the one state the ask's own condition does not exclude.
        RouteAskRepl.reading_binding("fighting",
                                     in_space(scanner=NOT_HUNTED, rats=3)),
        RouteAskRepl.reading_binding("warping",
                                     in_space(scanner=NOT_HUNTED, warping=True)),
        RouteAskRepl.reading_binding("routed",
                                     in_space(scanner=NOT_HUNTED,
                                              route=ROUTE_LABELS)),
        RouteAskRepl.reading_binding("docked",
                                     in_space(scanner=NOT_HUNTED, ship=False)),
        # No scanner window at all, which is the arm that answers
        # `No probe window` and falls through to leaving the system.
        RouteAskRepl.reading_binding("noScanner", in_space(scanner=None)),
        # Standing in the first system on the circuit, which is the reading
        # `huntSystemIndex` advances on and the one #263's constraint is about.
        RouteAskRepl.reading_binding("arriving",
                                     in_space(scanner=NOT_HUNTED,
                                              system=CIRCUIT[0])),
    ]


def session(pairs):
    """`(repeats, reading)` pairs as the Elm list the bindings fold."""
    return "[ %s ]" % ", ".join(
        "( %d, %s )" % (repeats, name) for repeats, name in pairs)


class TheFixturesAreWhatTheCasesAssume(unittest.TestCase):
    """What the parser makes of these trees, before anything concludes from it.

    #174's lesson: a reading that never arrived and a rule that answered nothing
    are the same `Nothing` from outside, so the trees are asked what they say
    before any case below asks what the rules say about them.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_scanner_rows_reach_the_parser_with_their_cells(self):
        answers = self.repl.strings(
            ["dry |> Maybe.andThen .probeScannerWindow"
             " |> Maybe.map (.scanResults >> List.length >> String.fromInt)"
             " |> Maybe.withDefault \"no window\"",
             "dry |> Maybe.andThen .probeScannerWindow"
             " |> Maybe.map (.scanResults >> List.filterMap"
             " (.cellsTexts >> Dict.get \"Name\") >> String.join \"|\")"
             " |> Maybe.withDefault \"no window\"",
             "dry |> Maybe.andThen .probeScannerWindow"
             " |> Maybe.map (.scanResults >> List.filterMap"
             " (.cellsTexts >> Dict.get \"Group\") >> String.join \"|\")"
             " |> Maybe.withDefault \"no window\"",
             "noScanner |> Maybe.map (\\r -> if r.probeScannerWindow == Nothing"
             " then \"absent\" else \"present\")"
             " |> Maybe.withDefault \"reading did not parse\"",
             "empty |> Maybe.andThen .probeScannerWindow"
             " |> Maybe.map (.scanResults >> List.length >> String.fromInt)"
             " |> Maybe.withDefault \"no window\""],
            readings())
        self.assertEqual(
            answers,
            ["2", "|".join(NOT_HUNTED), "|".join([COMBAT_GROUP] * 2),
             "absent", "0"],
            "the probe scanner these cases build is not read as holding the "
            "rows they build it with, so every answer below is about a "
            "scanner the bot never saw")

    def test_the_two_scanner_readings_are_told_apart_by_the_shipped_filter(self):
        """The whole of #273 in two answers: the ask's own state, and the
        counter's old one, disagreeing on the same reading."""
        answers = self.repl.evaluate(
            ["(dry |> Maybe.map (anomaliesWorthHunting"
             " { botSettings = %s, visitedAnomalies = Dict.empty }"
             " >> List.isEmpty)) == Just True" % RouteAskRepl.settings(),
             "(hunting |> Maybe.map (anomaliesWorthHunting"
             " { botSettings = %s, visitedAnomalies = Dict.empty }"
             " >> List.isEmpty)) == Just False" % RouteAskRepl.settings(),
             "(dry |> Maybe.map deadEndBeforeThisChange) == Just False",
             "(empty |> Maybe.map deadEndBeforeThisChange) == Just True"],
            readings())
        self.assertEqual(
            answers, [True] * 4,
            "the reading with two non-matching signatures is not the reading "
            "the ask fires on and the old counter declined, so the pair these "
            "cases are built on is not the pair the issue is about")

    def test_the_other_readings_say_what_they_are_built_to_say(self):
        answers = self.repl.evaluate(
            ["(routed |> Maybe.map routePanelShowsARoute) == Just True",
             "(dry |> Maybe.map routePanelShowsARoute) == Just False",
             "(warping |> Maybe.map shipIsWarpingOrJumping) == Just True",
             "(dry |> Maybe.map shipIsWarpingOrJumping) == Just False",
             "(docked |> Maybe.map (.shipUI >> (==) Nothing)) == Just True",
             "(fighting |> Maybe.map (gridStillHasSomethingToDo"
             " initBotMemory.incomingDamage)) == Just True",
             "(dry |> Maybe.map (gridStillHasSomethingToDo"
             " initBotMemory.incomingDamage)) == Just False",
             "(arriving |> Maybe.andThen currentSolarSystemNameFromReading)"
             " == Just \"%s\"" % CIRCUIT[0],
             "(dry |> Maybe.andThen currentSolarSystemNameFromReading)"
             " == Just \"%s\"" % ELSEWHERE],
            readings())
        self.assertEqual(
            answers, [True] * 9,
            "one of the readings these cases separate on does not say what it "
            "was built to say")


class TheCounterReachesTheBoundRatherThanOscillating(unittest.TestCase):
    """Issue #273's own verification method, executed.

    Fold `updateMemoryForNewReadingFromGame` over a session alternating one
    empty-scanner reading with one non-matching-results reading, and assert the
    counter reaches the bound rather than oscillating 0 -> 1 -> 0.
    """

    ALTERNATING = [(1, name) for _ in range(GIVE_UP_READINGS + 2)
                   for name in ("empty", "dry")]

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_session_is_the_length_it_was_written_to_be(self):
        """Every fixture arrived. A `filterMap` over readings that failed to
        parse would otherwise fold a shorter session and answer a smaller
        number for a reason that has nothing to do with the rule."""
        [length] = self.repl.integers(
            ["sessionLength %s" % session(self.ALTERNATING)], readings())
        self.assertEqual(length, 2 * (GIVE_UP_READINGS + 2))

    def test_the_counter_advances_on_every_reading_of_the_session(self):
        settings = RouteAskRepl.settings()
        peak, final = self.repl.integers(
            ["peakAsk %s %s" % (settings, session(self.ALTERNATING)),
             "(memoryOver %s %s).destinationAskReadings"
             % (settings, session(self.ALTERNATING))],
            readings())
        self.assertEqual(
            peak, 2 * (GIVE_UP_READINGS + 2),
            "the counter does not advance on every reading the ask fires on, "
            "which is the whole of #273")
        self.assertEqual(final, peak)

    def test_the_construction_this_replaces_peaks_at_one_and_ends_at_zero(self):
        """The control, on the same readings.

        Without it a session that reaches the bound proves nothing: any counter
        that only ever rises reaches any bound. What makes this evidence is that
        the condition #273 removed, executed over the very same parsed readings,
        produces the corpus's own shape -- a counter that touches 1 and is reset
        by the next reading.
        """
        final, peak = self.repl.integers(
            ["askBeforeThisChange %s |> Tuple.first"
             % session(self.ALTERNATING),
             "askBeforeThisChange %s |> Tuple.second"
             % session(self.ALTERNATING)],
            readings())
        self.assertEqual(
            peak, 1,
            "the condition #273 replaced no longer oscillates on this session, "
            "so this pair of readings is not the pair the issue records")
        self.assertEqual(
            final, 0,
            "the old counter does not end this session at zero, which is the "
            "value nearly every recorded ask reading printed beside it")

    def test_the_give_up_is_reachable_now_and_was_not(self):
        settings = RouteAskRepl.settings()
        answers = self.repl.evaluate(
            ["(memoryOver %s %s).routeSettingGivenUp"
             % (settings, session(self.ALTERNATING)),
             "%d < (askBeforeThisChange %s |> Tuple.second)"
             % (GIVE_UP_READINGS, session(self.ALTERNATING))],
            readings())
        self.assertEqual(
            answers, [True, False],
            "either the give-up is still unreachable, or the construction it "
            "replaced would have reached it -- and the second would mean this "
            "session does not separate the two")

    def test_one_reading_short_of_the_bound_does_not_latch(self):
        """The boundary, from both sides, with a fixed value either side of it.

        `routeSettingGivenUp` is `routeAskGiveUpReadings < the count the
        *previous* reading ended on`, so the latch first sets on the reading
        after the count passes the bound.
        """
        settings = RouteAskRepl.settings()
        answers = self.repl.evaluate(
            ["(memoryOver %s [ ( %d, dry ) ]).routeSettingGivenUp"
             % (settings, GIVE_UP_READINGS + 1),
             "(memoryOver %s [ ( %d, dry ) ]).routeSettingGivenUp"
             % (settings, GIVE_UP_READINGS + 2),
             "(memoryOver %s [ ( 3, dry ) ]).routeSettingGivenUp" % settings,
             "(memoryOver %s [ ( 60, dry ) ]).routeSettingGivenUp" % settings],
            readings())
        self.assertEqual(answers, [False, True, False, True])

    def test_the_bound_is_the_one_the_source_carries(self):
        [bound] = self.repl.integers(["routeAskGiveUpReadings"])
        self.assertEqual(
            bound, GIVE_UP_READINGS,
            "the bound moved, so every count in this file is against a number "
            "that is no longer the bot's")


class TheGuardsTheCounterSharesWithTheDecision(unittest.TestCase):
    """The states the ask does *not* fire on, and the counter must decline.

    Each is a way a counter keyed on "no anomaly worth hunting" alone would run
    up while the bot was doing something else, which is the fear behind the
    comment #273 corrects. Each is answered by a declaration the decision reads
    too, rather than by a second condition beside it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def peaks(self, names):
        settings = RouteAskRepl.settings()
        return self.repl.integers(
            ["peakAsk %s [ ( 60, %s ) ]" % (settings, name)
             for name in names], readings())

    def test_none_of_them_lets_the_counter_move_at_all(self):
        names = ["hunting", "fighting", "warping", "routed", "docked"]
        self.assertEqual(
            self.peaks(names), [0] * len(names),
            "a session of one of these readings runs the counter up, so the "
            "give-up can latch on a bot that is not asking for anything: %s"
            % ", ".join(names))

    def test_a_fight_on_a_dry_grid_stops_the_counter_where_it_stood(self):
        """`fighting` differs from `dry` only in the rats on the overview, so
        this separates the shared guard from the fixture."""
        settings = RouteAskRepl.settings()
        peak, final = self.repl.integers(
            ["peakAsk %s [ ( 10, dry ), ( 30, fighting ) ]" % settings,
             "(memoryOver %s [ ( 10, dry ), ( 30, fighting ) ])"
             ".destinationAskReadings" % settings],
            readings())
        self.assertEqual(peak, 10)
        self.assertEqual(
            final, 0,
            "the counter goes on climbing through a fight the site's signature "
            "has already dropped out of, which is the state the replaced "
            "comment narrowed the counter for")

    def test_a_reading_with_no_scanner_window_is_still_a_dead_end(self):
        """That arm reaches the ask through `siteProgressStepOrElse`, so
        declining it here would put the bound back out of reach on the readings
        an operator has closed the scanner for."""
        settings = RouteAskRepl.settings()
        [peak] = self.repl.integers(
            ["peakAsk %s [ ( %d, noScanner ) ]"
             % (settings, GIVE_UP_READINGS + 5)], readings())
        self.assertEqual(peak, GIVE_UP_READINGS + 5)

    def test_the_decision_and_the_counter_read_one_declaration_each(self):
        """The drift #273 is about, refused in the source.

        Both guards are declarations with two readers rather than two spellings
        of one idea. The three-way disjunction in particular was written inline
        at the decision site and would have had to be written again here.
        """
        plain = source_of(SAXRAT_BOT_ELM)
        source = collapsed(plain)
        for name in ("gridStillHasSomethingToDo", "shipIsWarpingOrJumping",
                     "anomaliesWorthHunting"):
            self.assertEqual(
                len(re.findall(r"^%s :" % name, plain, re.M)), 1,
                "%s is declared more than once, so the two sides can drift "
                "again" % name)
        for call in (
                "if shipIsWarpingOrJumping context.readingFromGameClient then",
                "not (shipIsWarpingOrJumping context.readingFromGameClient)",
                "if gridStillHasSomethingToDo context.memory.incomingDamage "
                "context.readingFromGameClient then",
                "not (gridStillHasSomethingToDo incomingDamageNow "
                "context.readingFromGameClient)",
                "anomaliesWorthHunting (anomalyChoiceFromDecisionContext "
                "context) context.readingFromGameClient",
                "anomaliesWorthHunting { botSettings = context.botSettings"):
            self.assertIn(
                call, source,
                "one of the two readers of a shared guard is gone, so that "
                "side is deciding on something of its own: %r" % call)
        self.assertNotIn(
            "anyAttackableInOverview (namesOfRecentAttackers "
            "context.memory.incomingDamage) context.readingFromGameClient "
            "|| anyNotableWreckInOverview", source,
            "the decision spells the on-grid guard out inline again beside the "
            "declaration the counter reads, which is two copies of it")

    def test_the_two_sides_are_handed_the_same_incoming_damage(self):
        """The guard reads a memory field, so the two callers have to be looking
        at the same one. The memory update hands it `incomingDamageNow`, which
        is the value it goes on to store, so the decision -- handed the memory
        this update wrote -- reads that same value."""
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            "gridStillHasSomethingToDo incomingDamageNow "
            "context.readingFromGameClient", source)
        self.assertIn(", incomingDamage = incomingDamageNow", source)
        self.assertIn(
            "gridStillHasSomethingToDo context.memory.incomingDamage "
            "context.readingFromGameClient", source)


class TheCounterCountsAsksAndNotDeadEnds(unittest.TestCase):
    """A dead end the circuit has nowhere to answer with is not an ask.

    PR #263's recount of the corpus found this from the other side: runs 12, 26
    and 27 latched the give-up having issued no ask at all -- run 12 with a
    circuit configured and the branch never reached, runs 26 and 27 with no
    `hunt-system` at all, so there was nothing the bot could have asked for.
    `setRouteToNextHuntingGround` tethers on that reading rather than asking, so
    a counter that advanced through it was bounding something that was not
    happening.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_no_hunt_system_configured_never_reaches_the_give_up(self):
        settings = RouteAskRepl.settings(hunt=())
        peak = self.repl.integers(
            ["peakAsk %s [ ( 60, dry ) ]" % settings], readings())
        latched = self.repl.evaluate(
            ["(memoryOver %s [ ( 60, dry ) ]).routeSettingGivenUp" % settings],
            readings())
        self.assertEqual(peak, [0])
        self.assertEqual(
            latched, [False],
            "a bot with no 'hunt-system' still latches the give-up, which is "
            "what runs 26 and 27 did -- a bound firing on asks nobody made")

    def test_a_circuit_that_names_only_this_system_never_reaches_it_either(self):
        """#262's `Nothing`: every candidate is the system the ship is in, so
        the picker answers nowhere and the branch tethers."""
        settings = RouteAskRepl.settings(hunt=(CIRCUIT[0],))
        peak = self.repl.integers(
            ["peakAsk %s [ ( 60, arriving ) ]" % settings], readings())
        self.assertEqual(peak, [0])

    def test_the_counter_and_the_named_destination_move_together(self):
        """One condition, not two: the counter is keyed on the value the ask is
        keyed on, so they cannot disagree about whether an ask is happening."""
        settings = RouteAskRepl.settings()
        answers = self.repl.evaluate(
            ["(memoryOver %s [ ( 5, dry ) ]).destinationAskedFor /= Nothing"
             % settings,
             "(memoryOver %s [ ( 5, dry ) ]).destinationAskReadings == 5"
             % settings,
             "(memoryOver %s [ ( 5, dry ), ( 1, hunting ) ])"
             ".destinationAskedFor == Nothing" % settings,
             "(memoryOver %s [ ( 5, dry ), ( 1, hunting ) ])"
             ".destinationAskReadings == 0" % settings,
             "(memoryOver %s [ ( 5, dry ) ]).destinationAskedFor == Nothing"
             % RouteAskRepl.settings(hunt=()),
             "(memoryOver %s [ ( 5, dry ) ]).destinationAskReadings == 0"
             % RouteAskRepl.settings(hunt=())],
            readings())
        self.assertEqual(answers, [True] * 6)

    def test_the_counter_reads_the_named_destination_rather_than_the_dead_end(self):
        """Sliced out of the memory update rather than out of the file.

        `initBotMemory` names both fields first, so a slice taken over the whole
        source reads `, destinationAskReadings = 0` and concludes nothing --
        which is the vacuous-pass shape this repo has paid for four times.
        """
        counter = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                    "updateMemoryForNewReadingFromGame"))
        counter = counter[counter.index(", destinationAskReadings ="):]
        counter = counter[:counter.index(", routeSettingGivenUp =")]
        self.assertIn("destinationAskedForNow == Nothing", counter)
        self.assertIn("botMemoryBefore.destinationAskReadings + 1", counter,
                      "the counter never advances, so its bound is "
                      "unreachable")
        self.assertNotIn(
            "if standingInADeadEnd then", counter,
            "the counter is keyed on the dead end again rather than on the "
            "destination the branch would ask for, so a bot with nowhere to go "
            "spends the budget it never asked against")


class TheTwoCallersStillNameTheSameDestination(unittest.TestCase):
    """#263's constraint, executed against the memory this change writes.

    The framework hands the decision the memory `updateMemoryForNewReadingFrom
    Game` has already written, so on the reading the ship arrives in the system
    the pointer names, the counter's picker and the decision's are called with
    indices one apart. #263 closed that by skipping a hunting ground the ship is
    standing in; this change moves what the counter is keyed on, so the property
    is re-asserted rather than assumed -- and asserted over the folded memory
    rather than over the picker's call site, which #263's own file reads.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def agreement(self, reading_name, pairs, settings=None):
        settings = settings or RouteAskRepl.settings()
        return self.repl.strings(
            ["(memoryOver %s %s).destinationAskedFor"
             " |> Maybe.withDefault \"nowhere\"" % (settings, session(pairs)),
             "(%s |> Maybe.andThen (nextHuntingGroundFrom %s"
             " (memoryOver %s %s).huntSystemIndex))"
             " |> Maybe.withDefault \"nowhere\""
             % (reading_name, settings, settings, session(pairs))],
            readings())

    def test_the_memory_names_what_the_decision_would_ask_for(self):
        """Somewhere off the circuit, where the pointer does not move."""
        stored, decided = self.agreement("dry", [(4, "dry")])
        self.assertEqual(stored, decided)
        self.assertEqual(stored, CIRCUIT[0])

    def test_they_agree_on_the_reading_the_pointer_moves(self):
        """The arrival, which is the reading the two are handed indices one
        apart on and the one a dead-ended ship is most likely to be having."""
        stored, decided = self.agreement("arriving", [(4, "arriving")])
        self.assertEqual(
            stored, decided,
            "the memory counts readings against a system the decision is not "
            "asking for, which is the drift #263 closed")
        self.assertEqual(stored, CIRCUIT[1])

    def test_the_picker_is_still_called_the_way_the_decision_calls_it(self):
        """Read out of the source, because neither call site is an expression
        this suite can evaluate. #263's own file reads the same two strings;
        they are read here because this change moved the binding they sit in."""
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            "nextHuntingGround context = nextHuntingGroundFrom "
            "context.eventContext.botSettings context.memory.huntSystemIndex "
            "context.readingFromGameClient", source)
        self.assertIn(
            "nextHuntingGroundFrom context.botSettings "
            "botMemoryBefore.huntSystemIndex context.readingFromGameClient",
            source,
            "the memory update names the destination some other way than the "
            "decision does, so the counter and the ask can disagree again")

    def test_both_callers_hand_the_anomaly_filter_the_same_two_things(self):
        """The new shared rule, given the same treatment.

        `visitedAnomalies` is the value this update has just computed rather
        than `botMemoryBefore`'s, because that is the one the framework hands
        the decision on this same reading.
        """
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn(
            "anomalyChoiceFromDecisionContext context = "
            "{ botSettings = context.eventContext.botSettings"
            " , visitedAnomalies = context.memory.visitedAnomalies }", source)
        self.assertIn(
            "anomaliesWorthHunting { botSettings = context.botSettings"
            " , visitedAnomalies = visitedAnomalies }", source,
            "the memory update asks the anomaly filter about a different set "
            "of visited anomalies than the decision will")
        self.assertNotIn(
            " , visitedAnomalies = botMemoryBefore.visitedAnomalies }", source,
            "the counter reads the previous reading's visited anomalies while "
            "the decision reads this one's")


class TheGiveUpHoldsForTheRestOfTheSession(unittest.TestCase):
    """What the bot does once the bound fires, on that reading and after.

    The latch is `botMemoryBefore.routeSettingGivenUp || ...`, so it cannot come
    undone -- and that is what makes the branch below a hot path rather than a
    one-off, which is why the branch is read as well as the latch executed.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RouteAskRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_holds_on_every_reading_after_it_first_sets(self):
        settings = RouteAskRepl.settings()
        pairs = [(GIVE_UP_READINGS + 5, "dry"), (30, "hunting"),
                 (10, "routed"), (10, "docked"), (10, "dry")]
        answers = self.repl.evaluate(
            ["giveUpHeld %s %s == ( True, True )"
             % (settings, session(pairs)),
             "(memoryOver %s %s).routeSettingGivenUp"
             % (settings, session(pairs))],
            readings())
        self.assertEqual(
            answers, [True, True],
            "the give-up comes undone on a later reading, so the bot goes back "
            "to asking a host that has already been shown not to answer")

    def test_the_counter_going_back_to_zero_does_not_unlatch_it(self):
        """The readings that follow are ones the counter resets on, which is
        what makes this a test of the latch rather than of the counter."""
        settings = RouteAskRepl.settings()
        count, = self.repl.integers(
            ["(memoryOver %s %s).destinationAskReadings"
             % (settings, session([(GIVE_UP_READINGS + 5, "dry"),
                                   (5, "hunting")]))],
            readings())
        self.assertEqual(count, 0)

    def test_the_latch_is_written_as_one_that_cannot_come_undone(self):
        update = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                   "updateMemoryForNewReadingFromGame"))
        latch = update[update.index(", routeSettingGivenUp ="):]
        latch = latch[:latch.index(", lockBatch =")]
        self.assertIn("botMemoryBefore.routeSettingGivenUp ||", latch,
                      "the give-up no longer latches")
        self.assertIn(
            "routeAskGiveUpReadings < botMemoryBefore.destinationAskReadings",
            latch)


class TheGiveUpActsRatherThanWaits(unittest.TestCase):
    """PR #257's hazard, on a branch that is now reached on every reading.

    Once the latch is set `setRouteToNextHuntingGround` takes its first arm for
    the rest of the session, so whatever that arm answers is what the bot does
    every reading from then on. #257 shipped green and blocked the bot for 108
    minutes because a step on such a path could decline forever.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def branch(self):
        body = self.source[self.source.index(
            "setRouteToNextHuntingGround : BotDecisionContext"):]
        return body[:body.index("jumpToNextSystem :")]

    def given_up_arm(self):
        arm = self.branch()
        arm = arm[arm.index("if context.memory.routeSettingGivenUp then"):]
        return arm[:arm.index("else")]

    def test_the_given_up_arm_tethers(self):
        self.assertIn("tetherAtStructure context", self.given_up_arm())

    def test_the_given_up_arm_does_not_hand_the_reading_back(self):
        self.assertNotIn(
            "waitForProgressInGame", self.given_up_arm(),
            "the give-up defers instead of acting, on a branch it now reaches "
            "on every reading for the rest of the session -- which is #257")

    def test_the_latch_is_tested_before_anything_else_in_the_branch(self):
        """So it applies on every reading after, including ones the picker
        would have answered `Nothing` on and ones it would have named a system
        on."""
        branch = self.branch()
        self.assertLess(
            branch.index("context.memory.routeSettingGivenUp"),
            branch.index("nextHuntingGround context"),
            "the branch consults the picker before the give-up, so what the "
            "bot does after the bound fires depends on the circuit again")

    def test_the_operator_is_told_the_asking_has_stopped(self):
        arm = self.given_up_arm()
        self.assertIn("no route ever appeared", arm)
        self.assertIn("routeAskGiveUpReadings", arm,
                      "the give-up names neither how long it waited nor the "
                      "bound it waited against")


class TheExpiredJustificationIsCorrected(unittest.TestCase):
    """The sentence that let this survive review, refused in `Bot.elm`.

    #273's own diagnosis: the comment reasoned that the narrowing "can
    under-count and delay the give-up", which prices a systematically absent
    condition as a late one. Nothing failed when that premise expired -- the
    comment went on reading correctly beside a counter that could never reach
    its bound -- so it is refused as text rather than left to be re-derived.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def test_the_under_count_sentence_is_gone(self):
        self.assertNotIn(
            "can under-count and delay the give-up", self.source,
            "the comment still prices the narrowing as a delay, which is the "
            "reading #273 shows is false")

    def test_the_narrowing_is_not_described_as_the_safe_direction(self):
        self.assertNotIn("Narrower is the safe direction", self.source)

    def test_the_replacement_says_what_the_narrowing_actually_cost(self):
        self.assertIn("#273", self.source,
                      "nothing in the file names the issue, so the next reader "
                      "of this counter cannot find the argument")
        self.assertIn("the bound was unreachable", self.source)


class TheCorpusIsQuotedRatherThanRemembered(unittest.TestCase):
    """What the recorded runs actually say, which is not all of what #273 says.

    Counted in **readings** rather than in lines. The status line is reprinted
    under every decision and one look at the game emits about a dozen, so a
    tally of ask lines is several times a tally of ask readings -- the unit that
    has already distorted `stall_watch.py`'s threshold twice, #141's retreat
    measurement and #164's whole diagnosis.

    Stated as relations rather than as counts, so a corpus that grows cannot
    turn a true claim red -- and aggregated over every run that ever asked
    rather than over one, because the run #273 quotes is **not on this machine**
    (`TheRunTheIssueQuotesIsNotHere`).
    """

    READ = re.compile(r"^#   task read-from-game-\d+: RequestToVolatileProcess")
    ASK = re.compile(
        r"Asking the host to set the destination to '([^']+)' "
        r"\((\d+)/(\d+) readings\)")
    GIVEN_UP = "this host does not set destinations"

    @classmethod
    def saxrat_logs(cls):
        """Every recorded saxrat run this machine has, or the shared skip.

        Globbed rather than numbered, so a new run is read without an edit, and
        the wording is the one `check_expected_skips.py` matches.
        """
        logs = []
        if os.path.isdir(EVE_BOT_LOGS):
            logs = sorted(os.path.join(EVE_BOT_LOGS, name)
                          for name in os.listdir(EVE_BOT_LOGS)
                          if re.match(r"saxrat_run\d+\.log$", name))
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "say about the route ask cannot be consulted here")
        return logs

    @classmethod
    def asking(cls, path):
        """`(counts by reading, ask lines, the give-up was printed)`.

        One count per reading rather than per line: the first ask line inside a
        reading is taken and the rest of that reading's are passed over.
        """
        counts = []
        lines = 0
        given_up = False
        seen_this_reading = False
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if cls.READ.match(line):
                    seen_this_reading = False
                    continue
                if cls.GIVEN_UP in line:
                    given_up = True
                found = cls.ASK.search(line)
                if found:
                    lines += 1
                    if not seen_this_reading:
                        counts.append(int(found.group(2)))
                        seen_this_reading = True
        return counts, lines, given_up

    _asked = None

    @classmethod
    def runs_that_asked(cls):
        """`(path, counts by reading, ask lines, gave up)` per run that asked.

        Cached, because the recorded runs come to well over a gigabyte and four
        cases read them.
        """
        if cls._asked is None:
            cls._asked = [row for row in
                          ((path,) + cls.asking(path)
                           for path in cls.saxrat_logs())
                          if row[1]]
        asking = cls._asked
        if not asking:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs ever asked the host "
                "for a route, so the shape #273 is about cannot be consulted "
                "here")
        return asking

    def test_the_counter_is_pinned_low_on_every_reading_the_bot_asks_on(self):
        """The whole of #273, as the corpus has it.

        Not one recorded ask, in any run, was taken with the counter anywhere
        near the bound -- and nearly all of them were taken at 0 or 1, which is
        the oscillation the issue describes seen across runs rather than within
        one.
        """
        counts = [count for row in self.runs_that_asked() for count in row[1]]
        self.assertGreater(len(counts), 100,
                           "too few recorded ask readings to say anything")
        self.assertLess(
            max(counts), GIVE_UP_READINGS,
            "some recorded run asked with the counter at or past the bound, so "
            "the pinning this change is built on has changed shape -- recount "
            "before trusting this file's premise")
        low = sum(1 for count in counts if count <= 1)
        self.assertGreater(
            low * 10, len(counts) * 9,
            "the counter no longer spends nearly every ask reading at 0 or 1")

    def test_the_run_that_latched_was_not_asking_while_it_spent_the_budget(self):
        """The other half, and the direct evidence for what the counter is now
        keyed on.

        A run that reached the give-up *and* asked for a route is a run whose
        budget was spent on readings it was not asking on -- the counter never
        got past a small number on any reading it printed an ask beside. That is
        `destinationAskedForNow`'s whole argument, in a recording rather than in
        an inference.
        """
        latched = [row for row in self.runs_that_asked() if row[3]]
        if not latched:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs both asked for a "
                "route and reached the give-up, so this half cannot be "
                "consulted here")
        for path, counts, _, _ in latched:
            self.assertLess(
                max(counts), GIVE_UP_READINGS,
                "%s reached the bound on a reading it was asking on, so its "
                "give-up was not spent on readings that asked for nothing"
                % os.path.basename(path))

    def test_the_unit_is_the_reading_and_not_the_decision_line(self):
        """This file's own premise, since #273's own count is in decisions."""
        asking = self.runs_that_asked()
        readings_total = sum(len(row[1]) for row in asking)
        lines_total = sum(row[2] for row in asking)
        self.assertGreater(
            lines_total, readings_total,
            "the corpus carries no more ask lines than ask readings, so either "
            "the status line stopped being reprinted under every decision or "
            "this reader is counting lines after all")

    def test_the_run_the_issue_quotes_is_not_here(self):
        """Said as a case rather than as prose, because #273 reads as though a
        recording on this machine shows it.

        The issue describes a run that asked 439 times across its last 47,000
        log lines. The busiest recorded run on this machine asks on a couple of
        dozen readings. **This going red is good news**: it means the corpus has
        gained that run, and every count in this file should be re-derived from
        it rather than aggregated across runs.
        """
        busiest = max(len(row[1]) for row in self.runs_that_asked())
        self.assertLess(
            busiest, 100,
            "a recorded run now asks on 100 or more readings, which is the "
            "shape #273 quotes and this corpus did not have -- re-derive this "
            "file's relations from it and say so in the issue rather than "
            "leaving this case red")


class TheMutationsThisFileCatches(unittest.TestCase):
    """The list, so that a later reader can re-run them rather than trust it.

    Each of these fails at least one named case above. They are recorded rather
    than executed -- this suite has no mutation runner -- and the count is what
    the PR body quotes.

    1. `standingInADeadEnd` reverted to the empty-scanner test (the defect).
    2. `anomaliesWorthHunting` answering `Nothing` for an absent scanner window,
       so the no-scanner arm stops counting.
    3. the `gridStillHasSomethingToDo` clause dropped from the counter, so it
       climbs through a fight.
    4. the same clause spelled out inline at the decision site as well.
    5. the `shipIsWarpingOrJumping` clause dropped, so a warp spends the budget.
    6. the counter keyed on `standingInADeadEnd` again, so a bot with no
       `hunt-system` latches the give-up.
    7. the counter's `+ 1` pinned at a constant.
    8. the counter's reset removed, so it never comes back to zero.
    9. the latch's comparison moved by one, either way.
    10. the latch's `botMemoryBefore.routeSettingGivenUp ||` dropped.
    11. the memory update handed `botMemoryBefore.visitedAnomalies`.
    12. the memory update handed `botMemoryBefore.incomingDamage`.
    13. the given-up arm answering `waitForProgressInGame`.
    14. the given-up arm tested after the picker.
    15. the "under-count and delay" sentence restored.
    16. on this file's own premise, the corpus reader counting decision lines
        rather than readings.
    """

    def test_the_list_is_a_list(self):
        """`\\s*` rather than `\\s+`: Python 3.13 dedents a docstring at compile
        time, so the numbered lines reach here at column zero on a new
        interpreter and indented on an old one."""
        mutations = re.findall(r"^\s*\d+\. ", self.__doc__, re.M)
        self.assertEqual(
            len(mutations), 16,
            "the mutation list is not the length the PR body quotes")


if __name__ == "__main__":
    unittest.main()
