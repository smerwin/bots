"""Tests for the wingman following its commander through an acceleration gate.

Issue #411, and the issue body argues *against* the shape that shipped. The
operator decided in favour of it on 2026-08-29 and the design is recorded in the
issue's own comment, so a later reader finds the argument beside the code rather
than having to reconstruct why the weakest candidate on a ranked list was the
one taken.

**Only the trigger is new.** The manoeuvre is #401's entirely:
`accelerationGateToAct` already answers `{ gate, calledByTheCommander }`,
`gateMayBeTaken` is already the one declaration three readers ask, the drones
already come home first on a called gate, and the press is already bounded by
`accelerationGateRefusesThisShipTicks`. What this adds is a third field in that
record -- `commanderLeftTheGrid` -- and the memory that can answer it.

**The inference is not sound and nothing here claims it is.** A pilot leaving
the overview has at least five causes and only one is *took the gate*: he died,
he warped off, he cloaked, he drifted out of the overview's range filter, or
this pilot's preset never drew his row. The four guards narrow *when* the
inference is drawn, never what it infers. A wingman that follows a dead
commander through a gate ends up alone in a pocket, and that is the accepted
cost -- the alternative is sitting on the grid following nobody, which is what
#415 had to write a give-up for.

## The four guards, and the case each answers

1. **A prior sighting.** `CommanderGoneFromTheGrid` is reachable only from
   `CommanderOnTheGrid`, so the rule cannot fire on a grid that never named him.
   This is the guard that matters most and it is not hypothetical: a short
   overview window fails `_display` while the entry is still in the tree, and
   #366 was fixed on exactly that correction.
2. **The sighting is scoped to the grid**, cleared whenever the grid changes.
   `gridChangedThisReading` is one notion of that over two positive facts: the
   shared `warpJustEnded` that #397's landing window and the drone bookkeeping
   already read, and this bot having pressed an acceleration gate, read out of
   the previous step's own effects. The second is what stops one wrong follow
   chaining through pocket after pocket -- see
   `TheGatePressAlsoChangesTheGridTest`.
3. **The absence persists** for `commanderGoneReadingsBeforeFollowing` readings,
   because a row can fail `_display` for one reading without the pilot going
   anywhere.
4. **Exactly one acceleration gate**, which is the whole difference from #401:
   nobody named this gate, so with two there is no basis to choose and picking
   the nearest is a guess whose failure is a wrong pocket. Refusing on ambiguity
   is `dockAtDestinationStation`'s discipline.

Guards 1 to 3 live in `commanderPresenceAfterReading`, folded in the memory
update; guard 4 is the second clause of `followTheCommanderThroughTheGate`.

## What is unverified, and these cases cannot close it

**No live client, no recorded wingman run, and nothing in any corpus shows a
commander leaving a grid with a gate on it.** So every number and every premise
below is reasoned from this repo's own precedents rather than measured, and
`commanderGoneReadingsBeforeFollowing` is sized by argument alone.

**Whether taking an acceleration gate reads as a warp is still not established,
and nothing here depends on the answer.** It used to: guard 2 reset only on
`warpJustEnded`, so a gate that is not a warp let a follow carry its count into
the next pocket and take that pocket's gate blind. `gridChangedThisReading` now
also resets on this bot's own gate press, which is a fact the bot owns rather
than an inference about the client. What a live reading would still settle is
whether the warp half was ever doing that work on its own; with a gate that *is*
a warp both sources fire on the same reading and the reset is identical.

**What to watch on a first run** is the status clause on every in-space reading:
`Commander on this grid: NEVER SEEN ...` on a pilot whose overview never draws
him -- in which case nothing here will ever fire, correctly -- against
`SEEN AND GONE for N of 3 readings`, and then `FOLLOWING HIM THROUGH IT` beside
the press. A run that follows a gate having printed `NEVER SEEN` on the readings
before it would mean the prior-sighting guard is not reaching the rule, which is
the direction this fails silently in.

## Confirmed by mutation

Fifteen, each failing at least one named case. **The cases listed are the ones
each mutation actually broke, read off the run rather than predicted** -- the
counts are the whole file's, and where a mutation kills only one case that is
recorded as it is rather than padded.

| the mutation | cases it fails |
|---|---|
| **the prior-sighting guard dropped** -- `commanderPresenceAfterReading` answering `CommanderGoneFromTheGrid 1` from `CommanderNotSeenOnThisGrid`, so a commander this grid never drew is followed from the third reading. The failure this whole design refuses | 3, including `test_a_grid_that_never_named_him_says_nothing` and `test_a_commander_never_rendered_is_never_followed` |
| **the sighting surviving a warp** -- the `gridChanged` clause dropped | 3, including `test_a_warp_clears_the_sighting` and `test_a_sighting_in_the_last_pocket_licenses_nothing_in_this_one` |
| **the gate-press reset removed** -- `gridChangedThisReading` narrowed back to `state.warpJustEnded`, so a follow through a gate carries its count into the next pocket and takes that pocket's gate blind. The defect the review closed | `test_a_click_inside_the_remembered_button_is_a_grid_change`, `test_a_gate_this_bot_took_starts_the_next_pocket_from_nothing` |
| **the button's region read live rather than remembered** -- the memory update asking about the panel as it is *now* instead of as it was when the press was decided, which fails silently on any client that drops the button once the gate is taken | `test_the_memory_update_reads_the_press_it_remembered` |
| the persistence bound removed (`0 <= readings`) | 5, including `test_the_absence_has_to_persist` and `test_a_row_that_flickers_re_arms_the_guard` |
| the persistence bound moved by one (`<` for `<=`) | 12, including both boundary cases and the status line's own count |
| **the exactly-one-gate guard relaxed to "at least one"**, which is the "pick the nearest" guess | `test_exactly_one_gate_or_nothing`, `test_two_gates_on_the_grid_refuse_the_follow`, `test_the_status_line_says_why_a_follow_did_not_happen` |
| **the follow made to wait** -- a branch added to `takeTheAccelerationGate` answering `waitForProgressInGame` on a licensed follow with rats up | 6, including `test_the_follow_acts_rather_than_holding_the_reading` |
| **the rule split into a second copy** -- `describeAccelerationGateAsk` passing `commanderLeftTheGrid = False` of its own | `test_one_rule_with_five_readers`, `test_the_status_line_and_the_arm_agree_about_the_follow` |
| **the status clause collapsing the two absences** -- `CommanderNotSeenOnThisGrid` rendered as `SEEN AND GONE for 0 readings` | `test_the_status_line_keeps_the_two_absences_apart` |
| a reading that cannot say counted as him being gone | `test_a_reading_that_cannot_say_holds_rather_than_counting` |
| the counter in the memory update reading `botMemoryBefore`'s presence rather than this reading's | `test_the_counter_reads_this_readings_presence` |
| the press claiming a clear grid on a followed gate | 7, including `test_the_press_says_which_authority_it_is_on` |
| **the trigger doing nothing** -- `commanderLeftTheGrid` dropped from `gateMayBeTaken`'s body while the field stays in its record, so every rule below reads correctly and the bot behaves exactly as it did | 7, including `test_either_exception_overrides_the_rats` |
| **the gate arm made unreachable** -- `accelerationGateStep` answering `Nothing` | 8, including `test_the_follow_is_reached_once_the_guns_are_cycling` |

The last two are the ones a suite of rule-level cases alone would miss: a
trigger wired to nothing, and an arm nothing reaches. Both are this repo's
signature bug, and both are caught here only because the root is run for real.

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
    COMMANDER, HEADER_LABELS, MEMBER_ROW, fleet_window, header_labels,
    reading_binding, target_bar)
from test_wingman_called_gate import (  # noqa: E402
    GATE, overview, selected_item_panel, ship_ui)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

RAT = "Centii Minion"
SECOND_GATE = "Ancient Acceleration Gate"


def commander_row(displayed=True):
    """The commander's own overview row, as an ordinary pilot.

    Not a rat, so `getNamesOfRatsInOverview` does not count him and #348's guard
    is decided by the rat row alone.
    """
    return (COMMANDER, "Battlecruiser", displayed, False)


def rat_row(name=RAT):
    return (name, "Frigate", True, True)


def gate_row(name=GATE):
    return (name, "Acceleration Gate", True, False)


def grid(rows, panel=None, with_fleet_window=True, headers=None,
         modules=((10, True),), targets=None):
    """A whole reading: the fleet window, the overview, a ship and the panel.

    The fleet window is what names the commander -- `commanderOnGridFromReading`
    reads `fleetCommanderNameFromFleetWindowHeader` first and answers "cannot
    say" without it, so a fixture that leaves it out is asking about a reading
    that cannot answer rather than one that answers no.

    `modules` and `targets` exist only for the reachability class at the foot of
    this file, which needs the guns to have something or nothing to do; every
    other case here asks one arm directly and the defaults are what
    `test_wingman_called_gate` uses.
    """
    children = []
    if with_fleet_window:
        children.append(
            fleet_window(headers or HEADER_LABELS, [MEMBER_ROW]))
    children.append(overview(rows))
    children.append(ship_ui(modules))
    if targets is not None:
        children.append(target_bar(targets))
    if panel is not None:
        children.append(selected_item_panel(panel))
    return children


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, plus what running one arm costs.

    Every field of the context is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in a fixture can decide an answer except the reading and the one
    memory field a case names -- `test_wingman_called_gate`'s arrangement.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import Common.EffectOnWindow as EffectOnWindow",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "contextWith = \\presence -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = { initBotMemory | commanderGridPresence = presence }"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # `FELL THROUGH` is a sentence no branch produces, so an arm answering
        # `Nothing` reads as itself rather than as a decision this file failed
        # to anticipate. `THE FIXTURE NEVER ARRIVED` is the other half of that:
        # a reading that never decoded and an arm that decided nothing would
        # otherwise print alike.
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        "gateArm = \\presence -> \\parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeArm (accelerationGateStep (contextWith presence p)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The whole in-space root below the two arms that take the ship off the
        # grid, run for real -- which is the only thing that can say whether the
        # arm this change widens is reached at all.
        "rootFor = \\presence -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " unpack (wingmanDecisionRootInSpaceOrdinary (contextWith presence p) s)"
        ' |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "gunsFor = \\parsed -> parsed"
        " |> Maybe.map (\\p -> weaponsStepFromContext (contextWith"
        " CommanderNotSeenOnThisGrid p))"
        " |> Maybe.withDefault NoShipUIToFireFrom",
        "describeGate = \\presence -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeAccelerationGateAsk (contextWith presence p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "describePresence = \\presence -> \\parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeCommanderFollowThroughGate (contextWith presence p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "statusFor = \\presence -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> statusTextFromState (contextWith presence p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "onGridFor = \\parsed -> parsed"
        " |> Maybe.map commanderOnGridFromReading"
        " |> Maybe.withDefault (Just True)",
        "gatesOn = \\parsed -> parsed"
        " |> Maybe.map (accelerationGatesOnOverview >> List.length)"
        " |> Maybe.withDefault -1",
        # The presence folded over a whole session rather than asked once: a
        # rule that is right for one reading and wrong across a run is the
        # defect this shape prevents.
        "foldPresence = \\start -> \\steps -> List.foldl"
        " (\\stepPair before -> commanderPresenceAfterReading"
        " { before = before"
        " , gridChanged = Tuple.first stepPair"
        " , commanderOnGrid = Tuple.second stepPair })"
        " start steps",
        "presenceAfter = \\before -> \\changed -> \\onGrid ->"
        " commanderPresenceAfterReading"
        " { before = before, gridChanged = changed, commanderOnGrid = onGrid }",
        "follow = \\presence -> \\gates -> followTheCommanderThroughTheGate"
        " { presence = presence, accelerationGatesOnTheGrid = gates }",
        "mayTake = \\rats -> \\called -> \\left -> gateMayBeTaken"
        " { ratsOnTheGrid = rats"
        ", calledByTheCommander = called"
        ", commanderLeftTheGrid = left }",
        "authority = \\called -> \\following -> gateTakingAuthority"
        " { calledByTheCommander = called, followingTheCommander = following }",
        # The grid-change half, from the effects the bot would really have
        # dispatched rather than from a pre-computed `gridChanged` -- so the
        # chaining scenario below is executed end to end instead of described.
        "gateRegion = { x = 100, y = 200, width = 40, height = 20 }",
        "clickAt = \\x -> \\y ->"
        " [ EffectOnWindow.MouseMoveTo { x = x, y = y }"
        " , EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft"
        " , EffectOnWindow.ButtonUp EffectOnWindow.MouseButtonLeft ]",
        "gridChanged = \\warpEnded -> \\region -> \\effects ->"
        " gridChangedThisReading"
        " { warpJustEnded = warpEnded"
        " , activateGateButtonInTheLastReading = region"
        " , previousStepEffects = effects }",
        # A session of readings, folded through *both* rules the memory update
        # composes -- so a case can put a gate press in the middle of a run and
        # ask what the far side believes. A record rather than a tuple because
        # Elm takes no four-tuple, and because a named field cannot be misread
        # for its neighbour in a fixture this long.
        "foldSession = \\start -> \\readings -> List.foldl"
        " (\\r before -> commanderPresenceAfterReading"
        " { before = before"
        " , gridChanged = gridChanged r.warpEnded r.region r.effects"
        " , commanderOnGrid = r.onGrid })"
        " start readings",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-follow-gate-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def elm_bool(value):
    return "True" if value else "False"


def elm_maybe_bool(value):
    return "Nothing" if value is None else "Just %s" % elm_bool(value)


def steps(pairs):
    """`[(gridChanged, commanderOnGrid), ...]` as an Elm list of tuples."""
    return "[ %s ]" % ", ".join(
        "( %s, %s )" % (elm_bool(changed), elm_maybe_bool(on_grid))
        for changed, on_grid in pairs)


def collapsed(text):
    return re.sub(r"\s+", " ", text)


def declaration(source, name):
    """One top-level declaration, from its definition to the blank line pair.

    Doc comments are stripped, so a case cannot pass on prose -- which is what a
    plain substring over a block whose comment quotes the name it forbids would
    do.
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


class ThePresenceMemoryTest(unittest.TestCase):
    """Guards 1 to 3, executed and folded over sessions.

    The fold is the shape that matters: a rule right for one reading and wrong
    across a run is exactly what a single-reading case cannot see.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_session_starts_having_seen_nothing(self):
        """Executed against the shipped initial memory rather than a literal, so
        a field initialised to some other state fails here rather than in a run.
        """
        self.assertEqual(
            self.repl.evaluate([
                "initBotMemory.commanderGridPresence"
                " == CommanderNotSeenOnThisGrid",
                "commanderHasLeftTheGrid"
                " initBotMemory.commanderGridPresence == False",
            ]),
            [True, True])

    def test_a_grid_that_never_named_him_says_nothing(self):
        """Guard 1. Thirty readings of a grid answering "he is not on it", from
        a session that never saw him: the state does not move and the rule stays
        false. This is the pilot whose overview window is too short to draw his
        row -- #366's own correction -- and the case the whole design exists to
        refuse."""
        self.assertEqual(
            self.repl.evaluate([
                "foldPresence CommanderNotSeenOnThisGrid %s"
                " == CommanderNotSeenOnThisGrid"
                % steps([(False, False)] * 30),
                "commanderHasLeftTheGrid"
                " (foldPresence CommanderNotSeenOnThisGrid %s) == False"
                % steps([(False, False)] * 30),
            ]),
            [True, True])

    def test_a_sighting_is_what_arms_it(self):
        """One reading naming him is the whole of the positive evidence, and it
        wins over every other clause -- including a grid change on the same
        reading, since he is here and that is a reading rather than an
        inference."""
        self.assertEqual(
            self.repl.evaluate([
                "presenceAfter CommanderNotSeenOnThisGrid False (Just True)"
                " == CommanderOnTheGrid",
                "presenceAfter CommanderNotSeenOnThisGrid True (Just True)"
                " == CommanderOnTheGrid",
                "presenceAfter (CommanderGoneFromTheGrid 9) False (Just True)"
                " == CommanderOnTheGrid",
            ]),
            [True] * 3)

    def test_the_absence_has_to_persist(self):
        """Guard 3, at both sides of its bound *and* at fixed values either
        side. A boundary pair alone passes for any constant, which is the hole
        #120's own cases had."""
        self.assertEqual(
            self.repl.evaluate([
                "commanderHasLeftTheGrid (CommanderGoneFromTheGrid 1) == False",
                "commanderHasLeftTheGrid (CommanderGoneFromTheGrid 2) == False",
                "commanderHasLeftTheGrid (CommanderGoneFromTheGrid 3) == True",
                "commanderHasLeftTheGrid (CommanderGoneFromTheGrid 30) == True",
                "commanderHasLeftTheGrid"
                " (CommanderGoneFromTheGrid"
                " (commanderGoneReadingsBeforeFollowing - 1)) == False",
                "commanderHasLeftTheGrid"
                " (CommanderGoneFromTheGrid"
                " commanderGoneReadingsBeforeFollowing) == True",
            ]),
            [True] * 6)

    def test_the_count_advances_one_reading_at_a_time(self):
        """Folded, so a rule that pinned the count at one or jumped straight to
        the bound is visible."""
        self.assertEqual(
            self.repl.evaluate([
                "foldPresence CommanderOnTheGrid %s"
                " == CommanderGoneFromTheGrid 1" % steps([(False, False)]),
                "foldPresence CommanderOnTheGrid %s"
                " == CommanderGoneFromTheGrid 2" % steps([(False, False)] * 2),
                "foldPresence CommanderOnTheGrid %s"
                " == CommanderGoneFromTheGrid 5" % steps([(False, False)] * 5),
            ]),
            [True] * 3)

    def test_a_row_that_flickers_re_arms_the_guard(self):
        """The count resets on the reading his row comes back, so a preset that
        drops him for two readings out of three never accumulates -- which is
        what makes being early cheap."""
        self.assertEqual(
            self.repl.evaluate([
                "foldPresence CommanderOnTheGrid %s == CommanderOnTheGrid"
                % steps([(False, False), (False, False), (False, True)]),
                "commanderHasLeftTheGrid (foldPresence CommanderOnTheGrid %s)"
                " == False"
                % steps([(False, False), (False, False), (False, True),
                         (False, False), (False, False)]),
            ]),
            [True, True])

    def test_a_warp_clears_the_sighting(self):
        """Guard 2. The reading a warp ends puts the memory back to "this grid
        has never named him", whatever it believed about the last one."""
        self.assertEqual(
            self.repl.evaluate([
                "presenceAfter CommanderOnTheGrid True (Just False)"
                " == CommanderNotSeenOnThisGrid",
                "presenceAfter (CommanderGoneFromTheGrid 9) True (Just False)"
                " == CommanderNotSeenOnThisGrid",
                "presenceAfter (CommanderGoneFromTheGrid 9) True Nothing"
                " == CommanderNotSeenOnThisGrid",
            ]),
            [True] * 3)

    def test_a_sighting_in_the_last_pocket_licenses_nothing_in_this_one(self):
        """The whole of guard 2 said as a session: he is seen, he goes, the ship
        warps, and the readings after the warp start the count from nothing --
        so a follow cannot be licensed by a pocket the ship has left."""
        self.assertEqual(
            self.repl.evaluate([
                "commanderHasLeftTheGrid (foldPresence CommanderNotSeenOnThisGrid %s)"
                " == False"
                % steps([(False, True), (False, False), (False, False),
                         (True, False), (False, False), (False, False)]),
                "commanderHasLeftTheGrid (foldPresence CommanderNotSeenOnThisGrid %s)"
                " == True"
                % steps([(False, True), (False, False), (False, False),
                         (False, False)]),
            ]),
            [True, True])

    def test_a_reading_that_cannot_say_holds_rather_than_counting(self):
        """`Nothing` is *cannot say* and is never read as *he is not here*.
        Advancing on one would count a shut fleet window or a docked reading as
        the commander leaving -- `Maybe.withDefault False` in the expensive
        direction, which is the mistake CLAUDE.md keeps a rule about."""
        self.assertEqual(
            self.repl.evaluate([
                "presenceAfter CommanderOnTheGrid False Nothing"
                " == CommanderOnTheGrid",
                "presenceAfter (CommanderGoneFromTheGrid 2) False Nothing"
                " == CommanderGoneFromTheGrid 2",
                "commanderHasLeftTheGrid (foldPresence CommanderOnTheGrid %s)"
                " == False" % steps([(False, None)] * 30),
            ]),
            [True] * 3)

    def test_the_bound_is_small_and_its_own(self):
        """Three, and deliberately *not* written as `calledTargetGoneReadings`:
        the two questions are the same and the two give-ups are not, so a retune
        of #395's bound must not silently move this one.

        The value is asserted beside a relation, because a case that only
        compared it against another constant would pass on any number the two
        happened to share.
        """
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        body = declaration(source, "commanderGoneReadingsBeforeFollowing =")
        self.assertNotIn("calledTargetGoneReadings", body)
        self.assertEqual(
            self.repl.evaluate([
                "commanderGoneReadingsBeforeFollowing == 3",
                "commanderGoneReadingsBeforeFollowing"
                " < weaponsAskedReadingsBound",
                "commanderGoneReadingsBeforeFollowing"
                " < accelerationGateRefusesThisShipTicks",
                "0 < commanderGoneReadingsBeforeFollowing",
            ]),
            [True] * 4)


class TheGatePressAlsoChangesTheGridTest(unittest.TestCase):
    """The second half of guard 2: a gate this bot took clears the sighting.

    **This is the chaining scenario, executed rather than described.** #411 as
    first written reset only on `warpJustEnded`, and an acceleration gate is
    very likely not a warp -- so after following the commander through a gate on
    grid A carrying `CommanderGoneFromTheGrid 3`, the bot arrived in pocket B
    with that count intact and would take B's single gate on the arrival
    reading, without ever having looked for him there. It chains until it
    reaches a pocket with no gate or with two.

    **And it bites only where the follow was already wrong.** A follow that was
    right puts the commander on grid B, where a sighting clears the state on its
    own. So the unbounded case is exactly the one where compounding it is worst,
    which is why this is closed rather than documented.

    The rule reads the *press* and not the client, so none of this depends on
    whether taking a gate reads as a warp -- which is still unestablished, and
    is now a question about nothing load-bearing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_click_inside_the_remembered_button_is_a_grid_change(self):
        """The press, matched against the button's region as it was on the
        reading the press was decided from. A click elsewhere on the screen is
        not this gesture, and a reading whose panel drew no such button cannot
        match one however the mouse moved."""
        self.assertEqual(
            self.repl.evaluate([
                # The centre of the remembered button.
                "gridChanged False (Just gateRegion) (clickAt 120 210) == True",
                # Its very corner, which the one-pixel grow admits.
                "gridChanged False (Just gateRegion) (clickAt 100 200) == True",
                # A click somewhere else entirely -- an overview row, a module.
                "gridChanged False (Just gateRegion) (clickAt 900 700) == False",
                # No button on the last reading: nothing to have pressed.
                "gridChanged False Nothing (clickAt 120 210) == False",
                # A step that dispatched nothing at all.
                "gridChanged False (Just gateRegion) [] == False",
            ]),
            [True] * 5)

    def test_a_keystroke_over_the_button_is_not_a_press(self):
        """Only a left click counts. The bot presses hotkeys constantly and a
        rule keyed on "the previous step did something" would clear the sighting
        on every one of them."""
        self.assertEqual(
            self.repl.evaluate([
                "gridChanged False (Just gateRegion)"
                " [ EffectOnWindow.MouseMoveTo { x = 120, y = 210 } ]"
                " == False",
                "gridChanged False (Just gateRegion)"
                " [ EffectOnWindow.KeyDown EffectOnWindow.vkey_F"
                " , EffectOnWindow.KeyUp EffectOnWindow.vkey_F ]"
                " == False",
            ]),
            [True, True])

    def test_the_warp_half_still_answers_on_its_own(self):
        """An additional reset, not a replacement. A warp ending is a grid
        change whatever the previous step dispatched, so nothing #411 already
        did stops working."""
        self.assertEqual(
            self.repl.evaluate([
                "gridChanged True Nothing [] == True",
                "gridChanged True (Just gateRegion) (clickAt 900 700) == True",
            ]),
            [True, True])

    def test_a_gate_this_bot_took_starts_the_next_pocket_from_nothing(self):
        """The chaining scenario, folded as a session.

        Grid A: he is seen, he goes, three readings pass and the follow is
        licensed. The bot presses Activate Gate. Grid B: the commander is not
        drawn there either -- which is the bad case, since a follow that was
        right would have shown him.

        On the far side the presence has to read `CommanderNotSeenOnThisGrid`,
        so B's own gate is not taken on the strength of A's absence. The control
        beside it is the same session with the press missing, which is what the
        bot did before this and which reaches the far side still licensed.
        """
        onGrid = "(Just True)"
        offGrid = "(Just False)"
        press = "(clickAt 120 210)"
        nothing = "[]"
        region = "(Just gateRegion)"

        def reading(warp, effects, seen):
            return ("{ warpEnded = %s, region = %s, effects = %s, onGrid = %s }"
                    % (warp, region, effects, seen))

        grid_a = [
            reading("False", nothing, onGrid),
            reading("False", nothing, offGrid),
            reading("False", nothing, offGrid),
            reading("False", nothing, offGrid),
        ]
        # The reading after the press -- the arrival in pocket B, with the
        # commander not drawn there.
        pocket_b = [
            reading("False", press, offGrid),
            reading("False", nothing, offGrid),
        ]
        # The same arrival with no press dispatched, which is #411 as it
        # shipped: the count carries over and B's gate is taken blind.
        pocket_b_without_the_press = [
            reading("False", nothing, offGrid),
            reading("False", nothing, offGrid),
        ]

        def session(readings):
            return "[ %s ]" % ", ".join(readings)

        self.assertEqual(
            self.repl.evaluate([
                # Grid A licenses the follow, which is the premise.
                "commanderHasLeftTheGrid"
                " (foldSession CommanderNotSeenOnThisGrid %s) == True"
                % session(grid_a),
                # The press clears it, and guard 1 then holds the far side at
                # "this grid has never named him" -- so the readings after the
                # gate do not merely restart the count, they cannot start one
                # until pocket B has drawn him at least once.
                "foldSession CommanderNotSeenOnThisGrid %s"
                " == CommanderNotSeenOnThisGrid"
                % session(grid_a + pocket_b),
                "commanderHasLeftTheGrid"
                " (foldSession CommanderNotSeenOnThisGrid %s) == False"
                % session(grid_a + pocket_b),
                # The control: with no press the count carries into pocket B and
                # the follow is licensed there having never looked for him.
                "commanderHasLeftTheGrid"
                " (foldSession CommanderNotSeenOnThisGrid %s) == True"
                % session(grid_a + pocket_b_without_the_press),
            ]),
            [True] * 4)

    def test_the_far_side_re_arms_from_a_sighting_rather_than_staying_blind(self):
        """Clearing is not latching. Once through the gate the ordinary rule
        applies again: he is seen in pocket B, he goes, and three readings later
        the follow is licensed on B's own evidence."""
        def reading(effects, seen):
            return ("{ warpEnded = False, region = Just gateRegion"
                    ", effects = %s, onGrid = %s }" % (effects, seen))

        rows = [
            reading("(clickAt 120 210)", "(Just False)"),
            reading("[]", "(Just True)"),
            reading("[]", "(Just False)"),
            reading("[]", "(Just False)"),
            reading("[]", "(Just False)"),
        ]
        self.assertEqual(
            self.repl.evaluate([
                "commanderHasLeftTheGrid"
                " (foldSession (CommanderGoneFromTheGrid 9) [ %s ]) == True"
                % ", ".join(rows),
            ]),
            [True])

    def test_the_memory_update_reads_the_press_it_remembered(self):
        """The wiring, read out of the source: the memory update hands the rule
        the button region *from the memory it is updating* and the head of
        `previousStepsEffects`, and writes this reading's region back for the
        next one.

        Two ways this could be wired and be wrong, both of which compile.
        Reading the region live off this reading would ask about a panel that
        may no longer offer the button, which fails silently in exactly the case
        the rule exists for. And folding the whole effect history rather than
        its head would re-clear the sighting for as many readings as the press
        stays in the list.
        """
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        binding = collapsed(indented_let_binding(source, "commanderGridPresenceNow"))
        self.assertIn("gridChanged = gridChangedThisReading", binding)
        self.assertIn("warpJustEnded = weJustFinishedWarping", binding)
        self.assertIn(
            "activateGateButtonInTheLastReading ="
            " botMemoryBefore.activateGateButtonRegion",
            binding)
        self.assertIn(
            "previousStepEffects = context.previousStepsEffects"
            " |> List.head |> Maybe.withDefault []",
            binding)
        # And the region really is written back, from this reading.
        self.assertIn(
            "activateGateButtonRegion ="
            " activateGateButtonRegionFromReading context.readingFromGameClient",
            collapsed(source))

    def test_the_framework_carries_the_effects_to_the_memory_update(self):
        """`UpdateMemoryContext` did not carry `previousStepsEffects` in this
        app's vendored copy, though `eve-online-saxrat` and
        `eve-online-mission-runner` have both carried it since #11. Without it
        the memory update cannot know what the bot itself did, which is the one
        thing that makes this reset a positive fact rather than an inference.
        """
        framework = os.path.join(
            WINGMAN_DIR, "EveOnline", "BotFrameworkSeparatingMemory.elm")
        with open(framework, encoding="utf-8") as handle:
            source = handle.read()
        update_context = source.split("type alias UpdateMemoryContext")[1]
        update_context = update_context.split("type alias StepDecisionContext")[0]
        self.assertIn("previousStepsEffects", update_context)
        self.assertIn(
            "previousStepsEffects = stateBefore.lastStepsEffects",
            collapsed(source))


class TheFourGuardsTest(unittest.TestCase):
    """`followTheCommanderThroughTheGate`, over both of its clauses."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_exactly_one_gate_or_nothing(self):
        """Guard 4. Nobody named this gate, so two is not a choice and zero is
        not a gate -- and "the nearest of several" is the guess whose failure is
        a wrong pocket."""
        self.assertEqual(
            self.repl.evaluate([
                "follow (CommanderGoneFromTheGrid 5) 0 == False",
                "follow (CommanderGoneFromTheGrid 5) 1 == True",
                "follow (CommanderGoneFromTheGrid 5) 2 == False",
                "follow (CommanderGoneFromTheGrid 5) 3 == False",
            ]),
            [True] * 4)

    def test_both_clauses_are_needed(self):
        """One gate and no sighting, and a sighting with no gate, both answer
        no -- so neither clause alone is what the rule is resting on."""
        self.assertEqual(
            self.repl.evaluate([
                "follow CommanderNotSeenOnThisGrid 1 == False",
                "follow CommanderOnTheGrid 1 == False",
                "follow (CommanderGoneFromTheGrid 2) 1 == False",
                "follow (CommanderGoneFromTheGrid 3) 1 == True",
            ]),
            [True] * 4)

    def test_the_guard_holds_no_reading(self):
        """It is a `Bool` handed to `gateMayBeTaken`, so it cannot wait: read
        out of the source because "this expression contains no wait" is a
        property of the text rather than of any one answer."""
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        for name in ("followTheCommanderThroughTheGate state =",
                     "commanderHasLeftTheGrid presence =",
                     "commanderPresenceAfterReading state ="):
            with self.subTest(name=name):
                body = declaration(source, name)
                for forbidden in ("waitForProgressInGame", "describeBranch",
                                  "askForHelpToGetUnstuck"):
                    self.assertNotIn(forbidden, body)


class TheGateGuardTest(unittest.TestCase):
    """#348's guard and its two exceptions, over the whole grid of inputs."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_shipped_guard_is_unchanged_with_both_exceptions_off(self):
        """With nothing overriding it, `gateMayBeTaken` *is* #348's guard --
        which is what keeps every existing behaviour on a grid this rule says
        nothing about."""
        self.assertEqual(
            self.repl.evaluate([
                "mayTake True False False == False",
                "mayTake False False False == True",
            ]),
            [True, True])

    def test_either_exception_overrides_the_rats(self):
        """The two are the same thing said twice: the fleet is going through
        this gate. #401's is the commander saying so; #411's is his having gone
        without saying so."""
        self.assertEqual(
            self.repl.evaluate([
                "mayTake True True False == True",
                "mayTake True False True == True",
                "mayTake True True True == True",
                "mayTake False True True == True",
            ]),
            [True] * 4)

    def test_the_press_says_which_authority_it_is_on(self):
        """`The overview is clear of rats` is **false** on a gate taken under
        either exception, and a log claiming a clear grid on readings that had
        rats on them is worse than no line at all -- #401's own argument, with
        a second way to reach it.

        Rendered from the rule's answer rather than asserted by substring over
        the branch, which is the arrangement #109 records a status clause
        passing a case while printing nothing at all.
        """
        self.assertEqual(
            self.repl.evaluate([
                "authority True False == TheCommanderCalledThisGate",
                "authority False True == TheCommanderLeftThisGrid",
                "authority False False == TheGridIsClearOfRats",
                "authority True True == TheCommanderCalledThisGate",
            ]),
            [True] * 4)
        called, left, clear = self.repl.strings([
            "describeGateTakingAuthority TheCommanderCalledThisGate",
            "describeGateTakingAuthority TheCommanderLeftThisGrid",
            "describeGateTakingAuthority TheGridIsClearOfRats",
        ])
        self.assertIn("called this acceleration gate", called)
        self.assertIn("no longer on this grid", left)
        self.assertIn("only acceleration gate", left)
        self.assertIn("died, warped off or cloaked", left)
        self.assertNotIn("clear of rats", left)
        self.assertNotIn("clear of rats", called)
        self.assertIn("clear of rats", clear)


class TheGridAnswersOrDeclinesToTest(unittest.TestCase):
    """`commanderOnGridFromReading`, over readings the real parser produced.

    Three readings cannot answer and each of them reads as an absence to a rule
    that only asks `fleetCommanderOverviewEntry`. An absence is exactly what
    this memory counts, so each is checked rather than reasoned about.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding(
                "commanderHere",
                grid([commander_row(), rat_row(), gate_row()])),
            reading_binding(
                "commanderGone", grid([rat_row(), gate_row()])),
            reading_binding(
                "noFleetWindow",
                grid([rat_row(), gate_row()], with_fleet_window=False)),
            reading_binding(
                "noOverview",
                [fleet_window(HEADER_LABELS, [MEMBER_ROW]), ship_ui()]),
            reading_binding(
                "noShipUI",
                [fleet_window(HEADER_LABELS, [MEMBER_ROW]),
                 overview([rat_row(), gate_row()])]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a rule that answered nothing read
        alike, so what the parser made of each fixture is checked first."""
        self.assertEqual(
            self.repl.evaluate([
                "commanderHere /= Nothing",
                "(commanderHere |> Maybe.andThen .shipUI) /= Nothing",
                "(commanderHere |> Maybe.andThen"
                ' fleetCommanderNameFromFleetWindowHeader) == Just "%s"'
                % COMMANDER,
                "(commanderHere |> Maybe.map (.overviewWindows"
                " >> List.concatMap .entries >> List.length)) == Just 3",
                "(commanderGone |> Maybe.map (.overviewWindows"
                " >> List.concatMap .entries >> List.length)) == Just 2",
                "(noFleetWindow |> Maybe.andThen"
                " fleetCommanderNameFromFleetWindowHeader) == Nothing",
                "(noOverview |> Maybe.map (.overviewWindows >> List.length))"
                " == Just 0",
            ], definitions=self.definitions),
            [True] * 7)

    def test_a_row_naming_him_is_the_grid_answering_yes(self):
        self.assertEqual(
            self.repl.evaluate(["onGridFor commanderHere == Just True"],
                               definitions=self.definitions),
            [True])

    def test_a_grid_with_no_row_naming_him_answers_no(self):
        """The one reading that advances the count, and it needs all three of a
        named commander, a ship UI and an overview."""
        self.assertEqual(
            self.repl.evaluate(["onGridFor commanderGone == Just False"],
                               definitions=self.definitions),
            [True])

    def test_a_shut_fleet_window_cannot_say(self):
        """The header comes and goes -- `fleetPlaceBroadcast`'s own comment
        records that -- so a reading that does not name a commander is not a
        reading that says he left."""
        self.assertEqual(
            self.repl.evaluate(["onGridFor noFleetWindow == Nothing"],
                               definitions=self.definitions),
            [True])

    def test_a_reading_with_no_overview_cannot_say(self):
        self.assertEqual(
            self.repl.evaluate(["onGridFor noOverview == Nothing"],
                               definitions=self.definitions),
            [True])

    def test_a_reading_with_no_ship_ui_cannot_say(self):
        """Docked, or a client that did not render. The overview windows of the
        last grid can still be in the tree, so this is not covered by the check
        above -- and counting a docked reading as the commander leaving is how a
        session in station would arrive in the next pocket already licensed."""
        self.assertEqual(
            self.repl.evaluate([
                "(noShipUI |> Maybe.andThen .shipUI) == Nothing",
                "(noShipUI |> Maybe.map (.overviewWindows >> List.length))"
                " == Just 1",
                "onGridFor noShipUI == Nothing",
            ], definitions=self.definitions),
            [True] * 3)


class TheGateArmFollowsHimTest(unittest.TestCase):
    """The whole point, through the real arm over really parsed readings.

    Every case here is decided on a grid with rats up, because that is the only
    state the trigger changes anything on: with a clear grid #348's guard is
    already satisfied and the gate is already taken.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding(
                "oneGateHeIsGone",
                grid([rat_row(), gate_row()], panel=GATE)),
            reading_binding(
                "twoGatesHeIsGone",
                grid([rat_row(), gate_row(), gate_row(SECOND_GATE)],
                     panel=GATE)),
            reading_binding(
                "oneGateNoPanel", grid([rat_row(), gate_row()])),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate([
                "gatesOn oneGateHeIsGone == 1",
                "gatesOn twoGatesHeIsGone == 2",
                "(oneGateHeIsGone |> Maybe.map"
                " (getNamesOfRatsInOverview >> List.length)) == Just 1",
                "(oneGateHeIsGone |> Maybe.andThen"
                " nearestAccelerationGateOnOverview) /= Nothing",
            ], definitions=self.definitions),
            [True] * 4)

    def test_the_rats_still_hold_the_gate_while_he_is_on_the_grid(self):
        """The control this file turns on. The same reading, the same gate, the
        same rats -- and with the commander still on the grid the arm declines
        exactly as #348 says it must."""
        answer = self.repl.strings(
            ["gateArm CommanderOnTheGrid oneGateHeIsGone"],
            definitions=self.definitions)[0]
        self.assertIn("rats are still on the grid", answer)

    def test_the_follow_takes_the_gate_with_rats_up(self):
        """The change. The same reading with the commander gone for long enough
        presses the gate instead."""
        answer = self.repl.strings(
            ["gateArm (CommanderGoneFromTheGrid 3) oneGateHeIsGone"],
            definitions=self.definitions)[0]
        self.assertNotIn("rats are still on the grid", answer)
        self.assertIn("follow him through", answer)

    def test_the_follow_acts_rather_than_holding_the_reading(self):
        """#411's second constraint. Every arm that answered `Just` on a
        condition it could not clear has owned the whole bot (#360, #389, #395,
        #397, #381), so the licensed reading has to be spent doing something.

        With the panel not yet showing the gate that something is the selection
        click, which is the shipped path and is bounded by
        `accelerationGateRefusesThisShipTicks` -- this adds no wait of its own.
        """
        pressed, selected = self.repl.strings([
            "gateArm (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
            "gateArm (CommanderGoneFromTheGrid 3) oneGateNoPanel",
        ], definitions=self.definitions)
        self.assertIn("activate it and follow him through", pressed)
        self.assertIn("select it", selected)
        for answer in (pressed, selected):
            with self.subTest(answer=answer):
                self.assertNotIn("I wait", answer)
                self.assertNotIn("rats are still on the grid", answer)

    def test_a_commander_never_rendered_is_never_followed(self):
        """Guard 1 through the arm. A session on this grid that never drew his
        row leaves the memory at `CommanderNotSeenOnThisGrid` however many
        readings pass, and the arm declines -- which is the pilot #366 was
        fixed for."""
        presence, answer = (
            self.repl.evaluate([
                "foldPresence initBotMemory.commanderGridPresence %s"
                " == CommanderNotSeenOnThisGrid"
                % steps([(True, False)] + [(False, False)] * 40)],
                definitions=self.definitions)[0],
            self.repl.strings(
                ["gateArm CommanderNotSeenOnThisGrid oneGateHeIsGone"],
                definitions=self.definitions)[0])
        self.assertTrue(presence)
        self.assertIn("rats are still on the grid", answer)

    def test_two_gates_on_the_grid_refuse_the_follow(self):
        """Guard 4 through the arm, on the same commander memory that licenses
        the follow next door -- so what separates the two answers is the grid
        and not the fixture."""
        one, two = self.repl.strings([
            "gateArm (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
            "gateArm (CommanderGoneFromTheGrid 3) twoGatesHeIsGone",
        ], definitions=self.definitions)
        self.assertIn("follow him through", one)
        self.assertIn("rats are still on the grid", two)

    def test_the_absence_still_has_to_persist_at_the_arm(self):
        """Guard 3 through the arm, at both sides of the bound."""
        short, long_enough = self.repl.strings([
            "gateArm (CommanderGoneFromTheGrid 2) oneGateHeIsGone",
            "gateArm (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
        ], definitions=self.definitions)
        self.assertIn("rats are still on the grid", short)
        self.assertIn("follow him through", long_enough)


class TheStatusLineTest(unittest.TestCase):
    """What an operator reads, executed rather than asserted by substring over
    the branch."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding(
                "oneGateHeIsGone",
                grid([rat_row(), gate_row()], panel=GATE)),
            reading_binding(
                "twoGatesHeIsGone",
                grid([rat_row(), gate_row(), gate_row(SECOND_GATE)],
                     panel=GATE)),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_status_line_keeps_the_two_absences_apart(self):
        """The one thing an operator needs first from this change. A run on a
        pilot whose overview never draws the commander and a run that watched
        him leave must not print the same sentence -- that is the difference
        between "nothing here will ever conclude anything, correctly" and
        "this bot is about to follow him"."""
        never, gone, here = self.repl.strings([
            "describePresence CommanderNotSeenOnThisGrid oneGateHeIsGone",
            "describePresence (CommanderGoneFromTheGrid 2) oneGateHeIsGone",
            "describePresence CommanderOnTheGrid oneGateHeIsGone",
        ], definitions=self.definitions)
        self.assertIn("NEVER SEEN", never)
        self.assertNotIn("SEEN AND GONE", never)
        self.assertIn("SEEN AND GONE", gone)
        self.assertNotIn("NEVER SEEN", gone)
        self.assertIn("on the overview now", here)
        self.assertNotIn("NEVER SEEN", here)
        self.assertNotIn("SEEN AND GONE", here)
        self.assertNotEqual(never, gone)

    def test_the_status_line_counts_towards_the_bound(self):
        """A count printed beside its bound, for the reason every other budget
        in this file prints one: a give-up whose arithmetic nobody can see is a
        give-up nobody can size."""
        below, at = self.repl.strings([
            "describePresence (CommanderGoneFromTheGrid 2) oneGateHeIsGone",
            "describePresence (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
        ], definitions=self.definitions)
        self.assertIn("2 of 3 readings", below)
        self.assertNotIn("FOLLOWING", below)
        self.assertIn("3 readings", at)
        self.assertIn("FOLLOWING HIM THROUGH IT", at)

    def test_the_status_line_says_why_a_follow_did_not_happen(self):
        """Guard 4 is not visible from the decision log -- the arm just goes on
        declining for the rats -- so the gate count rides in the clause. A grid
        with two gates and one with none are otherwise the same silence."""
        two = self.repl.strings(
            ["describePresence (CommanderGoneFromTheGrid 5) twoGatesHeIsGone"],
            definitions=self.definitions)[0]
        self.assertIn("Acceleration gates on this grid: 2", two)
        self.assertIn("no basis to choose", two)
        self.assertNotIn("FOLLOWING", two)

    def test_the_status_line_and_the_arm_agree_about_the_follow(self):
        """One rule, five readers. A status line that said the follow was on
        while the arm declined -- or the reverse -- is the shape #389 records
        three restatements of one condition costing, and the reason
        `gateMayBeTaken` is one declaration."""
        clause, gate_clause, decision = self.repl.strings([
            "describePresence (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
            "describeGate (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
            "gateArm (CommanderGoneFromTheGrid 3) oneGateHeIsGone",
        ], definitions=self.definitions)
        self.assertIn("FOLLOWING HIM THROUGH IT", clause)
        self.assertNotIn("rats still on the grid -- not taking it",
                         gate_clause)
        self.assertIn("follow him through", decision)

        clause, gate_clause, decision = self.repl.strings([
            "describePresence CommanderOnTheGrid oneGateHeIsGone",
            "describeGate CommanderOnTheGrid oneGateHeIsGone",
            "gateArm CommanderOnTheGrid oneGateHeIsGone",
        ], definitions=self.definitions)
        self.assertNotIn("FOLLOWING", clause)
        self.assertIn("rats still on the grid -- not taking it", gate_clause)
        self.assertIn("rats are still on the grid", decision)

    def test_the_clause_is_in_the_status_line(self):
        """A clause nothing prints is a clause an operator never reads, which is
        how #164's run left a 125 MB log that could not name the window it was
        stuck on."""
        status = self.repl.strings(
            ["statusFor (CommanderGoneFromTheGrid 3) oneGateHeIsGone"],
            definitions=self.definitions)[0]
        self.assertIn("Commander on this grid:", status)
        self.assertIn("SEEN AND GONE", status)


class TheArmHasToBeReachedForAnyOfThisToMatterTest(unittest.TestCase):
    """Reachability, measured through the real root rather than reasoned about.

    CLAUDE.md's own standard: *state reachability, not just correctness* --
    "I traced the path forward from this state" does not establish that the
    state can be entered. #397 is where that was fatal in this very file:
    `approachTheFleetCommander` sat at the foot of this root, each arm above it
    answers `Just` for the whole of a fight, and so on any grid worth landing on
    the arm was unreachable while every case about it passed.

    **`accelerationGateStep` is below the drones and the guns and this change
    does not move it** (#348, #326: a gate this bot can see is never taken while
    drones are still owed a command on a live grid). And the whole state the
    follow acts on -- rats on the grid -- is the state those arms answer in. So
    whether the follow is ever reached is a real question and these two cases
    are the answer: **it is reached on the readings the guns are cycling**,
    which is most of them, and it is outranked on the reading a weapon needs
    clicking.

    That is the honest shape rather than a fix: the guns get a reading here and
    there and the follow gets the rest, so the gate is taken a reading or two
    later than the trigger licenses it. Whether that is fast enough is a
    question only a live run can answer, and hoisting the arm would be #397's
    change again -- a placement with its own evidence, which this does not have.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        # The roster corroborates (#419), so the friendly-fire guard is clear to
        # fire and the guns are held by nothing but their own cycle -- otherwise
        # the control below would pass for a reason that has nothing to do with
        # this change.
        cls.definitions = [
            reading_binding(
                "gunsCycling",
                grid([rat_row(), gate_row()], panel=GATE,
                     headers=header_labels(2), modules=((10, True),),
                     targets=[[RAT, "2,000 m"]])),
            reading_binding(
                "aWeaponIsIdle",
                grid([rat_row(), gate_row()], panel=GATE,
                     headers=header_labels(2), modules=((10, False),),
                     targets=[[RAT, "2,000 m"]])),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_differ_only_in_what_the_guns_have_to_do(self):
        """Both grids carry the rat, the gate, the panel and the lock; what
        separates them is one module's `ramp_active`."""
        self.assertEqual(
            self.repl.evaluate([
                "gunsFor gunsCycling == AllWeaponsCycling",
                "gunsFor aWeaponIsIdle == ActivateAWeapon",
                "gatesOn gunsCycling == 1",
                "gatesOn aWeaponIsIdle == 1",
                "(gunsCycling |> Maybe.map (.targets >> List.length))"
                " == Just 1",
                "(aWeaponIsIdle |> Maybe.map (.targets >> List.length))"
                " == Just 1",
            ], definitions=self.definitions),
            [True] * 6)

    def test_the_follow_is_reached_once_the_guns_are_cycling(self):
        """The reading that matters, through the whole root: with the guns busy
        the arms above hand the reading down and the follow takes the gate --
        which is the ordinary case, since a module click is one reading and the
        cycle that follows it is many."""
        followed, held = self.repl.strings([
            "rootFor (CommanderGoneFromTheGrid 3) gunsCycling",
            "rootFor CommanderOnTheGrid gunsCycling",
        ], definitions=self.definitions)
        self.assertIn("follow him through", followed)
        self.assertIn("rats are still on the grid", held)

    def test_the_guns_still_outrank_the_follow_on_the_reading_they_act(self):
        """Stated rather than hidden. #326's ordering is untouched, so a reading
        the guns can spend is a reading the follow does not get -- the gate is
        taken a reading or two later than the trigger licenses it, bounded by
        `weaponsAskedReadingsBound` as the guns already were."""
        answer = self.repl.strings(
            ["rootFor (CommanderGoneFromTheGrid 3) aWeaponIsIdle"],
            definitions=self.definitions)[0]
        self.assertIn("Activate it", answer)
        self.assertNotIn("follow him through", answer)


class TheWiringTest(unittest.TestCase):
    """Source-pinned, because a rule nothing reaches is this repo's signature
    bug and no executed case can see it."""

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()
        cls.update = declaration(
            cls.source,
            "updateMemoryForNewReadingFromGame context botMemoryBefore =")

    def test_the_presence_is_settled_in_the_memory_update(self):
        """#102's and #126's placement rule: the memory update is the only thing
        that runs on every reading unconditionally, and the grid changing is a
        transition between two readings only it can see."""
        binding = indented_let_binding(
            self.source, "commanderGridPresenceNow")
        self.assertIn("commanderPresenceAfterReading", binding)
        self.assertIn(
            "before = botMemoryBefore.commanderGridPresence",
            collapsed(binding))
        self.assertIn("commanderOnGrid = commanderOnGridFromReading",
                      collapsed(binding))
        self.assertIn(
            "commanderGridPresence = commanderGridPresenceNow",
            collapsed(self.update))

    def test_the_grid_boundary_is_the_shared_warp_end(self):
        """`weJustFinishedWarping` is `warpJustEnded`, the corrected trigger of
        #194 / #205 -- previous reading `Just True`, a ship UI present now, this
        reading not `Just True`. A second notion of "we changed grid" written
        here would be two definitions drifting apart, and the condition #205
        replaced could not answer `True` at the end of a warp at all.

        The warp is now one of *two* sources feeding one notion of a grid change
        -- see `TheGatePressAlsoChangesTheGridTest` -- so what this asserts is
        that the shared trigger is still what the warp half is, and that the
        second source did not become a second opinion sitting beside it.
        """
        binding = indented_let_binding(
            self.source, "commanderGridPresenceNow")
        self.assertIn("gridChanged = gridChangedThisReading",
                      collapsed(binding))
        rule = declaration(self.source, "gridChangedThisReading state =")
        self.assertIn("state.warpJustEnded", collapsed(rule))
        self.assertIn("warpJustEnded = weJustFinishedWarping",
                      collapsed(binding))
        rule = declaration(
            self.source, "warpJustEnded { warpingLastReading, readingNow } =")
        self.assertIn("readingNow.shipUI /= Nothing", collapsed(rule))
        self.assertIn(
            "shipWarpingFromReading readingNow /= Just True", collapsed(rule))

    def test_the_counter_reads_this_readings_presence(self):
        """The decision reads the memory this update writes, so a counter
        advanced under `botMemoryBefore`'s presence runs a reading behind the
        arm -- and on the reading a follow begins that is the difference between
        `accelerationGateRefusesThisShipTicks` being reachable and not. #397's
        arrangement and #34's shape without it."""
        binding = indented_let_binding(self.source, "askingTheGateToOpen")
        self.assertIn(
            "commanderLeftTheGrid = followingTheCommanderThroughAGate"
            " commanderGridPresenceNow", collapsed(binding))
        self.assertNotIn("botMemoryBefore.commanderGridPresence", binding)

    def test_one_rule_with_five_readers(self):
        """`followingTheCommanderThroughAGate` is asked by the arm, the press's
        own wording, the memory update and both status clauses, and by nobody
        with a second opinion. A `commanderLeftTheGrid` written as anything else
        at any of those sites is two rules on two schedules -- #102's defect and
        #389's."""
        # Comments are stripped first. The memory update's own site carries the
        # reason it reads this reading's presence, and a reader that took the
        # next line verbatim would be asserting against prose -- which is the
        # trap `declaration` strips comments for one screen up.
        without_comments = re.sub(r"--[^\n]*", "", self.source)
        sites = re.findall(r"commanderLeftTheGrid =\s*(\S+)", without_comments)
        self.assertEqual(len(sites), 3, sites)
        for site in sites:
            with self.subTest(site=site):
                self.assertEqual(site, "followingTheCommanderThroughAGate")
        self.assertEqual(
            self.source.count("followTheCommanderThroughTheGate\n        {"), 1)

    def test_the_gate_count_and_the_gate_choice_come_off_one_filter(self):
        """A count taken over a different filter than the choice is two
        questions about one grid: counting undisplayed rows would refuse the
        follow because of a row nothing would have clicked."""
        chooser = declaration(
            self.source,
            "nearestAccelerationGateOnOverview readingFromGameClient =")
        self.assertIn("accelerationGatesOnOverview", chooser)
        follow = declaration(
            self.source,
            "followingTheCommanderThroughAGate presence readingFromGameClient =")
        self.assertIn("accelerationGatesOnOverview", follow)
        gates = declaration(
            self.source,
            "accelerationGatesOnOverview readingFromGameClient =")
        self.assertIn("overviewEntryIsDisplayed", gates)
        self.assertIn("overviewEntryIsAnAccelerationGate", gates)

    def test_the_press_is_rendered_from_the_authority_rule(self):
        """Not an `if` chain written at the press. Three answers over two facts,
        so a case executes the sentence an operator reads."""
        body = declaration(
            self.source, "pressTheAccelerationGate context gateToTake =")
        self.assertIn("describeGateTakingAuthority", body)
        self.assertIn("gateTakingAuthority", body)
        self.assertNotIn("The overview is clear of rats", body)

    def test_the_clause_is_printed_from_the_status_line(self):
        status = declaration(self.source, "statusTextFromState context =")
        self.assertIn("describeCommanderFollowThroughGate context", status)


if __name__ == "__main__":
    unittest.main()
