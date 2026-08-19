"""Tests for saxrat approaching an out-of-range row without pressing a key.

`lockTargetFromOverviewEntry` answered a row beyond lock range by wrapping a
left click in a `Q` chord -- `KeyDown vkey_Q`, click, `KeyUp vkey_Q`. A double
click on the same row asks the client for the same thing and presses no key at
all, which is what this change makes it do.

**Why the keystroke was worth removing rather than merely fixing.** `cg_input`
posts a key event without stamping flags on it, so a posted `Q` carries whatever
modifier state the session happens to hold; with the Fn bit set that is macOS
Quick Note, and one recorded run took this branch 1,571 times while Notes came
to the front 241 times with nobody at the machine. PR #241 stops the
mis-stamping. This is not redundant with it: #241 stops the keystroke being
mis-stamped, and this stops the keystroke existing, which also takes a
modifier-timing dependency off the hottest path in the bot.

The rule is executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives, and the overview rows it is asked about come from the **real**
`EveOnline.ParseUserInterface` -- so what the branch is handed is what the bot
would have been handed. `lockTargetFromOverviewEntry` takes a whole
`BotDecisionContext`, which is why nothing in this suite had executed it before;
the context is built here from `defaultBotSettings` and `initBotMemory`, so the
threshold the branch compares against is the shipped one rather than a number
this file chose.

**The regression this change must not introduce has its own case.**
`doubleClickUiElement` ended in `Result.withDefault []`, so a row whose visible
region is too small to click yielded an empty effect list -- a branch that
prints "Approach." and dispatches nothing, which is this repo's signature
failure. The `Q` chord at least still sent `Q`, so today that failure would be
total where it used to be partial. `test_a_row_too_small_to_click_says_so`
builds exactly that row.

Confirmed by mutation, eight of them, each failing named cases:

1. the `Q` chord restored in the approach branch -- six cases, including
   `test_the_approach_presses_no_key_at_all` and both decline cases, since a
   chord that cannot build its click still sends `Q`;
2. `doubleClickUiElement` reverted to `Result.withDefault []` --
   `test_a_row_too_small_to_click_says_so`, and *not*
   `test_a_row_too_small_to_click_dispatches_nothing`, which is the whole
   point: an empty list and a spoken decline dispatch alike, so only the
   saying-so half can tell them apart;
3. the double click swapped for a single one --
   `test_the_approach_dispatches_a_double_click`;
4. the lock chord's own Ctrl dropped -- the two control cases;
5. the threshold comparison inverted -- seven cases, the first of them
   `test_the_shipped_threshold_is_what_decides`;
6. the drone recall's doc left claiming `vkey_Q` is the approach chord --
   `test_the_drone_recall_no_longer_calls_q_the_approach_chord`;
7. a `Ctrl` put back under the double click --
   `test_nothing_reads_the_approach_back_as_a_lock` with the two effect cases;
8. the keep-at-range chord removed --
   `test_keep_at_range_still_holds_e_over_a_click`, which is what makes that
   marker a measurement rather than a note.

Nothing here reads a live game client, a running bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, collapsed, label, node, source_of)
from test_saxrat_learned_lock_range import (
    ROW_HEIGHT, ROW_PITCH, ROW_TOP, overview_rows, row_center)

# `defaultBotSettings.targetingRangeMeters`. The cases below do not assert this
# number -- they ask the branch about a row either side of it -- but a fixture
# has to be placed relative to something, and the case named just below is what
# keeps these two rows on the sides of it they are meant to be on.
SHIPPED_TARGETING_RANGE_METERS = 66000

# A rat's row, as the client draws one. The name is one the recorded runs carry.
RAT = "Centii Minion"


def rows_of_height(rows, height):
    """Overview rows drawn `height` pixels tall.

    `overview_rows` fixes the row height at `ROW_HEIGHT`, and what this file
    needs that it cannot express is a row too small to click:
    `uiNodeVisibleRegionLargeEnoughForClicking` wants more than three pixels in
    both directions, and a row the overview has all but scrolled out of view is
    how that happens on a live client. Everything else is that helper's shape.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, height)),
            label(name, (110, y, 150, height)),
            label(name, (310, y, 150, height)),
            node("SpaceObjectIcon", {}, [], region=(0, y, 8, height)),
        ], region=(0, y, 500, height)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


class ApproachRepl(SaxratRepl):
    """saxrat's `Bot.elm`, plus what running one decision branch costs.

    `lockTargetFromOverviewEntry` is not a rule over a record -- it takes a
    whole `BotDecisionContext` -- so a case cannot ask it anything without one.
    Every field of that context here is either the shipped default
    (`defaultBotSettings`, `initBotMemory`) or the emptiest value its type has,
    so nothing in the fixture can decide the answer except the reading.

    The bindings ride in the preamble rather than in each case's `definitions`,
    which `imports_and_bindings` folds into the one `let` that asks the
    question -- so they cost the same single compile the imports do.
    """

    BINDINGS = (
        "context = \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = initBotMemory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        # The branch, asked about the first row of a really parsed reading.
        "branchFor = \\parsed -> parsed |> Maybe.andThen (\\p ->"
        " p.overviewWindows |> List.concatMap .entries |> List.head"
        " |> Maybe.map (lockTargetFromOverviewEntry (context p)))",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "describeFor = \\parsed -> branchFor parsed"
        " |> Maybe.map (unpack >> Tuple.first >> String.join \" | \")"
        " |> Maybe.withDefault \"NO ROW\"",
        "effectsOfLeaf = \\leaf ->\n"
        "    case leaf of\n"
        "        EveOnline.BotFrameworkSeparatingMemory.ContinueSession continue ->\n"
        "            continue.effectsOnGameClient\n"
        "        EveOnline.BotFrameworkSeparatingMemory.FinishSession ->\n"
        "            []",
        "effectsFor = \\parsed -> branchFor parsed"
        " |> Maybe.map (unpack >> Tuple.second >> effectsOfLeaf)"
        " |> Maybe.withDefault []",
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

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import EveOnline.BotFrameworkSeparatingMemory",
        "import Common.DecisionPath",
        "import Common.EffectOnWindow as EffectOnWindow",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-approach-repl-")
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


class TheApproachPressesNoKeyTest(unittest.TestCase):
    """The branch itself, run against rows either side of the threshold."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)
        cls.definitions = [
            ApproachRepl.reading_binding(
                "far", [overview_rows([("100 km", RAT, 1, False)])]),
            ApproachRepl.reading_binding(
                "near", [overview_rows([("10 km", RAT, 1, False)])]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A reading that never parsed and a branch answering nothing read alike."""
        self.assertEqual(
            self.repl.evaluate(
                ["far /= Nothing", "near /= Nothing",
                 "(far |> Maybe.map (.overviewWindows"
                 " >> List.concatMap .entries >> List.length)) == Just 1",
                 "(far |> Maybe.map (.overviewWindows >> List.concatMap .entries"
                 " >> List.head >> Maybe.andThen"
                 " (.objectDistanceInMeters >> Result.toMaybe)))"
                 " == Just (Just 100000)"],
                definitions=self.definitions),
            [True, True, True, True])

    def test_the_shipped_threshold_is_what_decides(self):
        """One row is beyond the shipped lock range and the other is not.

        Asked of the branch rather than of the constant, because what a case
        can be wrong about here is which side of the threshold its fixture
        sits on -- and then every assertion below is about the wrong branch.
        """
        answers = self.repl.strings(
            ["describeFor far", "describeFor near"],
            definitions=self.definitions)
        self.assertIn("not in range", answers[0])
        self.assertIn("100000 m away", answers[0])
        self.assertIn("Lock target from overview entry", answers[1])
        self.assertLess(10000, SHIPPED_TARGETING_RANGE_METERS)
        self.assertLess(SHIPPED_TARGETING_RANGE_METERS, 100000)

    def test_the_approach_presses_no_key_at_all(self):
        """The whole of this change: the approach dispatches no keystroke.

        A `Q` that inherits the session's Fn bit is macOS Quick Note, and the
        recorded run that took this branch 1,571 times fronted Notes 241 times
        with nobody at the machine.
        """
        self.assertEqual(
            self.repl.evaluate(["keysIn (effectsFor far) == []"],
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
                ["effectsFor far == doubleClickAt %d %d" % (x, y)],
                definitions=self.definitions),
            [True])

    def test_a_row_in_range_is_still_locked_with_ctrl(self):
        """The control, so this file is about the approach and not the fixture.

        A repl that answered `[]` to everything, or a context whose settings
        did not arrive, would satisfy every assertion above.
        """
        x, y = row_center(0)
        self.assertEqual(
            self.repl.evaluate(
                ["effectsFor near =="
                 " ([ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]"
                 " ++ EffectOnWindow.effectsMouseClickAtLocation"
                 " EffectOnWindow.MouseButtonLeft { x = %d, y = %d }"
                 " ++ [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ])"
                 % (x, y),
                 "keysIn (effectsFor near) /= []"],
                definitions=self.definitions),
            [True, True])

    def test_nothing_reads_the_approach_back_as_a_lock(self):
        """The one rule that recognises a chord out of a step's own effects.

        `lockClickLocationsFromStepEffects` identifies a lock by its `Ctrl`,
        and the lock range and the batch accounting are both built on it. The
        approach's effects must not read as one -- and the chord this replaces
        was never read back by anything either, which is why removing it
        breaks no reader.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["lockClickLocationsFromStepEffects (effectsFor far) == []",
                 "lockClickLocationsFromStepEffects (effectsFor near) /= []",
                 "recentStepAskedForDroneRecall [ effectsFor far ] == False"],
                definitions=self.definitions),
            [True, True, True])


class TheDeclineIsSpokenTest(unittest.TestCase):
    """A row the client cannot be asked about says so rather than nothing.

    This is the regression the change had to avoid rather than a property it
    adds. `doubleClickUiElement` used to end in `Result.withDefault []`, and a
    branch that prints "Approach." over an empty effect list is the failure
    this repo keeps a section on -- worse here than the chord it replaces,
    since the chord at least still sent `Q`.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ApproachRepl)
        cls.definitions = [
            ApproachRepl.reading_binding(
                "tiny", [rows_of_height([("100 km", RAT)], 2)]),
            ApproachRepl.reading_binding(
                "drawn", [rows_of_height([("100 km", RAT)], ROW_HEIGHT)]),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """Both rows parse, and only one of them can be clicked.

        The two differ in one thing -- the row's height -- so a case that
        passed because the small row failed to parse would fail here first.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(tiny |> Maybe.map (.overviewWindows"
                 " >> List.concatMap .entries >> List.length)) == Just 1",
                 "(drawn |> Maybe.map (.overviewWindows"
                 " >> List.concatMap .entries >> List.length)) == Just 1",
                 "(tiny |> Maybe.map (.overviewWindows >> List.concatMap .entries"
                 " >> List.head >> Maybe.andThen"
                 " (.objectDistanceInMeters >> Result.toMaybe)))"
                 " == Just (Just 100000)"],
                definitions=self.definitions),
            [True, True, True])

    def test_a_row_too_small_to_click_says_so(self):
        answer = self.repl.strings(["describeFor tiny"],
                                   definitions=self.definitions)[0]
        self.assertIn("not in range", answer)
        self.assertIn("too small to click", answer)

    def test_a_row_too_small_to_click_dispatches_nothing(self):
        """Saying so and then clicking anyway would be the other failure."""
        self.assertEqual(
            self.repl.evaluate(["effectsFor tiny == []"],
                               definitions=self.definitions),
            [True])

    def test_a_row_that_can_be_clicked_still_is(self):
        """The control: the decline is about the row, not about this fixture."""
        answer = self.repl.strings(["describeFor drawn"],
                                   definitions=self.definitions)[0]
        self.assertNotIn("too small to click", answer)
        self.assertEqual(
            self.repl.evaluate(["effectsFor drawn /= []"],
                               definitions=self.definitions),
            [True])


class TheChordIsGoneTest(unittest.TestCase):
    """What is left of `vkey_Q` in saxrat, read out of the source.

    The branch is executed above; these are the claims that are not
    expressions -- that no *other* site kept the chord, and that the argument
    written beside the drone recall no longer rests on it.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_no_effect_anywhere_in_saxrat_presses_q(self):
        self.assertEqual(
            re.findall(r"EffectOnWindow\.vkey_Q\b", self.source), [])

    def test_the_approach_branch_uses_the_double_click_helper(self):
        """One helper rather than a second copy of the gesture.

        The gesture and its decline live in `doubleClickUiElement`, which the
        wreck path already used, so there is one place where a double click
        this bot cannot build is answered.
        """
        self.assertIn(
            'm away). Approach.") (doubleClickUiElement overviewEntry.uiNode)',
            collapsed(self.source))

    def test_the_drone_recall_no_longer_calls_q_the_approach_chord(self):
        """`recentStepAskedForDroneRecall`'s argument survives, its wording does not.

        It reasons that `vkey_R` is unambiguous because the other movement keys
        are spoken for. That gets stronger with one fewer key in the bot, and
        the sentence naming `vkey_Q` as the approach chord stops being true.
        """
        doc = collapsed(self.source[
            self.source.index("Did the bot ask for a recall recently?"):
            self.source.index("recentStepAskedForDroneRecall :")])
        self.assertNotIn("`vkey_Q` is the approach chord", doc)
        self.assertIn("`vkey_R` is used for nothing else in this bot", doc)


class TheOtherKeyWrappedClicksAreStillHereTest(unittest.TestCase):
    """Recorded rather than fixed, so a later change has to notice them.

    saxrat still wraps a click in a key at two more places -- `vkey_E` for
    keep-at-range and `vkey_W` for orbit, both reached from
    `decideActionInAnomaly` on the same hot path this change cleared. Issue
    #243 is scoped to the approach and does not touch them, and the reason to
    write that down rather than leave it is that "saxrat presses no movement
    key any more" is the claim somebody will make next, and it is false.
    """

    def setUp(self):
        self.source = collapsed(source_of(SAXRAT_BOT_ELM))

    def test_keep_at_range_still_holds_e_over_a_click(self):
        self.assertIn(
            "[ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_E ]"
            " , overviewEntryToKAR.uiNode |> mouseClickOnUIElement"
            " MouseButtonLeft |> Result.withDefault []"
            " , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_E ]", self.source)

    def test_orbit_still_holds_w_over_a_click(self):
        self.assertIn(
            "[ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_W ]"
            " , overviewEntryToOrbit.uiNode |> mouseClickOnUIElement"
            " MouseButtonLeft |> Result.withDefault []"
            " , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_W ]", self.source)


if __name__ == "__main__":
    unittest.main()
