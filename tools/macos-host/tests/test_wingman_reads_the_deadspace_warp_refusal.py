"""Tests for the wingman reading the client's deadspace warp refusal. #440.

The client refuses a warp out of a deadspace pocket in as many words, and the
string is quoted out of `~/eve-bot-logs` rather than typed from memory:

    <center>You cannot warp there because natural phenomena are disrupting the warp.

**It is a fact about this ship, not about the commander**, and that is what the
design turns on. All three recorded runs that carry it show this bot's own warp
being refused -- saxrat's run 12 pressing `Activate Gate` on a gate 312 km off,
mission run 32 on one 263 km off, and mission run 14's retreat warping to a
celestial at 1% shield -- and both mission runs had acceleration gates on the
overview on the same reading. So the client is saying *this pocket cannot be left
by warping*, and the gate is the only way out.

## The design question #440 asks, and why the answer is a fifth input

#348 refuses a gate while rats are on the overview because taking one mid-fight
abandons a fight the fleet may still be in. `gateMayBeTaken` carried three
bypasses of that guard before this change, and #440's point is that two of them
were merged by union rather than by anyone deciding whether they mean the same
thing. So the first thing asked here was whether the refusal replaces one.

**It does not, and the reason is structural rather than a matter of strength.**
The refusal exists only on a reading where this ship commanded a warp and the
client answered. The readings `commanderLeftTheGrid` (#411) exists for are
readings on which nothing warped at all -- a commander vanishes, no broadcast
names a place, and no arm in `wingmanDecisionRootInSpaceOrdinary` issues a warp.
A licence that requires the bot to have already tried something cannot replace
one that fires where the bot tried nothing. The mirror holds for #429's rejoin:
`retreatRecoveryStep` asks the gate *above* its fleet-window warp, so on the
readings that permission matters no warp has gone out and there is no refusal to
read. `TheTwoOlderLicencesAreNotThisOneTest` executes both halves of that rather
than leaving it as prose.

What the refusal *would* buy `commanderLeftTheGrid` is narrower and is
deliberately not taken: #411's own status line admits the follow "cannot tell
that from him having died, warped off or cloaked", and in a pocket the client has
just called un-warpable, *warped off* is one cause fewer. Narrowing that
inference is a change to `followTheCommanderThroughTheGate` with its own evidence
to gather.

## What bounds the licence

`deadspaceWarpRefusalLicensesAGateForReadings` is
`accelerationGateRefusesThisShipTicks`, written as that constant rather than as a
number: the two bound the same stretch from opposite ends, so a licence outliving
the arm's own budget for asking one gate can license nothing. A live-only rule
(`readingsSince == 0`) was the alternative and would have been inert -- taking a
gate is select, wait, press, so a licence lasting one reading switches the arm on
and off underneath itself.

## The reason is a field on #439's `GateLicence`, and that is not a formality

`gateMayBeTaken` is defined over `gateLicenceFromCase` since #439, so the reason
is a field on one closed record rather than a disjunct. Adding it to the
permission alone does not compile, which is what that record was closed for --
and #440 is the first change to arrive since, so it is the first time the
enforcement has bought anything.

**What it buys is the case in `TheRefusalRefillsTheBudgetTest`**, and it is the
one the two changes had to agree about. `accelerationGateRefusesThisShipTicks`
bounds readings spent asking *one* gate, and the ordinary hunting arm has usually
been asking about a gate for a while before a warp is ever commanded -- so a
refusal arriving on a spent budget would license a gate the arm had already given
up on, which is #439's own live reading (`GIVEN UP after 41 readings of asking`
beside a licence that had just arrived, and the ship sitting still). Being a
reason means the refusal refills the budget once, is accumulated once spent
under, and cannot refill again by arriving a second time. The bound it hands back
is `accelerationGateRefusesThisShipTicks`, which is also what this licence's own
staleness bound is -- so a refusal that refills the budget licenses the gate for
exactly as long as the refilled budget lasts.

## What is unverified, and these cases cannot close it

**No live client and no recorded wingman run.** The wording, its channel and its
frequency are measured; what a wingman does on meeting one is not. Nothing in any
corpus shows this bot being refused a warp beside a gate, because this bot has
never been recorded at all (WINGMAN.md).

**Whether the wingman's own warps produce this sentence is inherited rather than
shown.** The three recorded instances are a mission runner and saxrat. This bot
warps by the Selected Item panel's `selectedItemWarpTo`, by the broadcast
banner's `Warp to Member` and by the fleet window's row, and no recording shows
any of those being refused for deadspace. The client writes the sentence in
answer to a warp command, and all three are warp commands, but that is reasoning
rather than a reading.

**What to watch on a first run**: `Quick msg (now): "<center>You cannot warp
there ..."` in the status line, then `Acceleration gate: on the overview and the
client has refused this ship a warp for deadspace`, then the press's own line.
A run that meets the refusal and never prints the quick-message clause means the
channel is not reaching the memory, which is the direction this fails silently
in; a run that prints the clause and never the gate one means the marker does not
match what this client writes.

## Confirmed by mutation

Sixteen, none surviving. **The cases listed are the ones each mutation actually
broke, read off the run rather than predicted** -- where a mutation kills only
one case that is recorded as it is rather than padded.

The first four are the licence's, and they are the ones this file gained when
#439 landed first: the reason has four places to reach and each of them is a way
it could be present at the arm and absent from the refill.

| the mutation | cases it fails |
|---|---|
| **the reason dropped from `gateIsLicensed`** while the field stays in the record, so every rule below reads correctly and the bot behaves exactly as it did | 5, including `test_the_refusal_overrides_the_rats`, `test_a_refused_warp_takes_the_gate` and `test_the_refusal_is_reached_through_the_whole_root` |
| **the reason dropped from `gateLicenceFromCase`** | **does not compile** -- the record literal is missing a field its annotation names, so all 9 classes error in `setUpClass`. That is #439's closed record doing what it was closed for, and it is a stronger kill than any case: the licence the refill reads cannot be built without the reason in it |
| **the reason dropped from the refill**, so a gate given up on under an earlier reason stays given up on when the client refuses the warp -- #439's own live reading, reached by #440's reason | `test_a_gate_given_up_on_can_be_asked_again_once_the_client_refuses` |
| **the reason never accumulated as spent under**, so one refusal refills the budget on every reading it is live -- the runaway `gateLicenceSpentUnderAfter` exists to bound | `test_the_refusal_refills_at_most_once` |
| **the staleness clause dropped**, so a refusal from a pocket this ship has left licenses a gate forever -- the failure #440 names | 6, including `test_a_stale_refusal_licenses_nothing`, `test_a_stale_refusal_is_reached_and_declines` and `test_the_licence_lapses_across_a_quiet_session` |
| the bound's comparison moved by one (`<` for `<=`) | `test_the_licence_lasts_exactly_its_bound`, `test_the_licence_lapses_across_a_quiet_session` |
| **the bound written as a bare `0`**, which is the inert live-only rule | 3, including `test_the_licence_survives_the_readings_a_press_costs` |
| the bound written as a bare `40` rather than as the arm's own constant | `test_the_bound_is_written_as_the_arms_own` |
| **the marker weakened to `cannot warp`** | `test_the_marker_is_one_literal` -- and *not* the decline case, because none of the six wordings the corpus holds contains that phrase. The pin that catches it is the sentence being quoted once, verbatim; the decline case's own reach is recorded as what it is rather than claimed wider |
| the marker lower-cased on one side of the comparison only | 9, including `test_the_corpus_wording_is_matched_byte_for_byte` and `test_a_refused_warp_takes_the_gate` |
| **the ageing removed** from `quickMessageAfterReading`, so `readingsSince` never advances | 3, including `test_the_age_advances_one_reading_at_a_time` and `test_the_port_is_saxrats_own_declarations` |
| the gate licence reading `botMemoryBefore.quickMessage` rather than this reading's sighting | `test_the_counter_reads_this_readings_sighting`, `test_one_rule_with_four_readers` |
| **the channel never reaching the memory** -- `quickMessage` carried forward unchanged, so the popup is parsed on every reading and discarded exactly as it was before | `test_the_sighting_is_settled_in_the_memory_update` |
| **the gate arm made unreachable** -- `accelerationGateStep` answering `Nothing` | 6, including `test_the_refusal_is_reached_through_the_whole_root` |
| the status clause dropped from `statusTextFromState` | `test_the_status_line_carries_the_wording`, `test_the_clause_is_printed_from_the_status_line` |
| the gate clause in `describeAccelerationGateAsk` neutralised | `test_the_gate_clause_names_the_refusal_while_it_is_live` |

The two a suite of rule-level cases alone would miss are the first and the gate
arm made unreachable: a licence wired to nothing, and an arm nothing reaches.
Both are this repo's signature bug and both are caught here only because the root
is run for real. The third and fourth are the same shape one level down -- a
reason the *arm* honours and the *budget* never sees -- which no case that asks
only `gateMayBeTaken` could tell apart from working code.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, EVE_BOT_LOGS, open_repl  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    header_labels, label, node, reading_binding)
from test_wingman_called_gate import GATE, RAT  # noqa: E402
from test_wingman_follows_the_commander_through_a_gate import (  # noqa: E402
    collapsed, declaration, gate_row, grid, indented_let_binding, rat_row)

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

#: The refusal, exactly as the client writes it into `l_abovemain`. The
#: `<center>` wrapper is the client's own and is on the popup's copy and not on
#: the game log's, which is why the marker itself does not carry it.
REFUSAL = ("<center>You cannot warp there because natural phenomena are "
           "disrupting the warp.")

#: Wordings this client really writes that the marker has to decline. Every one
#: is quoted out of `~/eve-bot-logs` or out of CLAUDE.md's own record of it --
#: the first is the commonest quick message either bot has ever recorded and is
#: a *success* rather than a refusal, which is why there is no general "a quick
#: message means something went wrong" rule to fall back on.
OTHER_WORDINGS = (
    "<center>Cargo is too far away. Ship is on automatic approach to cargo.",
    "<center>You cannot launch Hammerhead I because you are already "
    "controlling 5 drones, as much as you have skill to.",
    "<center>You are already managing 6 targets, as many as you have skill to.",
    "<center>Please wait...",
    "The target <b>Centii Minion</b> is too far away. It must be within "
    "<b>49 km</b>.",
    "You cannot do that while warping",
)


def quick_message(lines, top=400):
    """A `QuickMessage` node with one label per line.

    The node itself carries no text, so `getAllContainedDisplayTexts` yields the
    labels in order and `parseQuickMessage`'s `List.head` takes the first.
    """
    return node("QuickMessage", {}, [
        label(text, (500, top + 20 * index, 400, 16))
        for index, text in enumerate(lines)
    ], region=(500, top, 400, 20 * max(1, len(lines))))


def layer_abovemain(messages):
    """The `l_abovemain` layer, holding one `QuickMessage` per entry.

    Identified by `_name`, which is what `parseLayerAbovemainFromUITreeRoot`
    matches on, and given a display region because that parser navigates by one.
    """
    return node("LayerCore", {"_name": "l_abovemain"}, [
        quick_message(lines, 400 + 100 * index)
        for index, lines in enumerate(messages)
    ], region=(0, 0, 1920, 1080))


def grid_showing(popup=None, rows=None, panel=GATE, **kwargs):
    """A whole reading: `test_wingman_follows...`'s grid, plus the popup layer.

    The grid is that file's rather than a second one, so the two modules cannot
    come to disagree about what a gate on a grid with rats on it looks like --
    which is the fixture #348's guard is decided from.
    """
    children = grid(rows if rows is not None else [rat_row(), gate_row()],
                    panel=panel, **kwargs)
    if popup is not None:
        children.append(layer_abovemain([[popup]]))
    return children


def elm_string(text):
    """An Elm string literal of `text`.

    `json.dumps` rather than `elm_json_literal`: that one encodes twice, because
    what it builds is a literal holding a whole reading's *JSON* for the decoder
    to read back. What is wanted here is the wording itself, and for ASCII the
    two escape vocabularies agree.
    """
    return json.dumps(text)


def sighting(text, readings_since=0, messages_in_layer=1, display_texts=1):
    """A `QuickMessageSighting` written out, for the rules that take one."""
    return ("(Just { text = %s, messagesInLayer = %d"
            ", displayTextsInMessage = %d, readingsSince = %d })"
            % (elm_string(text), messages_in_layer, display_texts,
               readings_since))


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
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "contextWith = \\seen -> \\parsed ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = defaultBotSettings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = parsed"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = { initBotMemory | quickMessage = seen }"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] }",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        # `FELL THROUGH` is a sentence no branch produces, so an arm answering
        # `Nothing` reads as itself. `THE FIXTURE NEVER ARRIVED` is the other
        # half: a reading that never decoded and an arm that decided nothing
        # would otherwise print alike.
        "describeArm = \\answer -> answer"
        ' |> Maybe.map (unpack >> Tuple.first >> String.join " | ")'
        ' |> Maybe.withDefault "FELL THROUGH"',
        "gateArm = \\seen -> \\parsed -> parsed"
        " |> Maybe.map (\\p ->"
        " describeArm (accelerationGateStep (contextWith seen p)))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The whole in-space root below the two arms that take the ship off the
        # grid, run for real -- the only thing that can say whether the arm this
        # change widens is reached at all.
        "rootFor = \\seen -> \\parsed -> parsed"
        " |> Maybe.andThen (\\p -> p.shipUI |> Maybe.map (\\s ->"
        " unpack (wingmanDecisionRootInSpaceOrdinary (contextWith seen p) s)"
        ' |> Tuple.first |> String.join " | "))'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "describeGate = \\seen -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> describeAccelerationGateAsk (contextWith seen p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "statusFor = \\seen -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> statusTextFromState (contextWith seen p))"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        # The parser's own answer about a reading, so the matcher is asked about
        # what the bot would have been handed rather than about a record shaped
        # by hand.
        "seenIn = \\parsed -> parsed |> Maybe.andThen quickMessageOnScreen",
        "textIn = \\parsed -> seenIn parsed"
        ' |> Maybe.map .text |> Maybe.withDefault "NO QUICK MESSAGE"',
        "refusedIn = \\parsed -> deadspaceRefusedTheWarp (seenIn parsed)",
        # The ageing folded over a whole session rather than asked once: a rule
        # right for one reading and wrong across a run is what this shape sees.
        "foldQuickMessage = \\start -> \\onScreens -> List.foldl"
        " (\\onScreen before -> quickMessageAfterReading"
        " { onScreenNow = onScreen, before = before })"
        " start onScreens",
        "ageOf = \\seen -> seen |> Maybe.map .readingsSince |> Maybe.withDefault -1",
        # #393's call, #411's follow and #429's rejoin are held off in every row
        # this module asks, for the reason those files hold this one off in
        # theirs: an exception that is switched on would answer for the one
        # under test.
        "mayTake = \\rats -> \\refused -> gateMayBeTaken"
        " { ratsOnTheGrid = rats"
        ", calledByTheCommander = False"
        ", commanderLeftTheGrid = False"
        ", rejoiningAfterARetreat = False"
        ", deadspaceRefusedTheWarp = refused }",
        "authority = \\refused -> gateTakingAuthority"
        " { calledByTheCommander = False"
        ", rejoiningAfterARetreat = False"
        ", followingTheCommander = False"
        ", deadspaceRefusedTheWarp = refused }",
        # #439's enumeration, which `gateMayBeTaken` is defined over. The two
        # reasons this file needs are the refusal and the clear grid: a gate
        # given up on while the grid was clear is the state the refusal has to
        # be able to buy a fresh budget out of.
        "licenceWith = \\refused -> \\clear -> gateLicenceFromCase"
        " { ratsOnTheGrid = not clear"
        ", calledByTheCommander = False"
        ", commanderLeftTheGrid = False"
        ", rejoiningAfterARetreat = False"
        ", deadspaceRefusedTheWarp = refused }",
        "refill = \\now -> \\spentUnder -> \\spent ->"
        " askedReadingsRefilledByANewLicence"
        " { licenceNow = now, spentUnder = spentUnder, spentBefore = spent }",
        "spentUnderAfter = \\onOverview -> \\asked -> \\now -> \\before ->"
        " gateLicenceSpentUnderAfter"
        " { gateOnTheOverview = onOverview"
        ", askedThisReading = asked"
        ", licenceNow = now"
        ", before = before }",
        "gateStep = \\asked -> accelerationGateActivationStep"
        " { panelShowsTheGate = True"
        ", panelOffersActivateGate = True"
        ", askedReadings = asked }",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-deadspace-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


class TheMatcherTest(unittest.TestCase):
    """The wording, read through the real parser and matched byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("refusalOnScreen",
                            grid_showing(popup=REFUSAL)),
            reading_binding("noPopup", grid_showing()),
        ] + [
            reading_binding("other%d" % index, grid_showing(popup=wording))
            for index, wording in enumerate(OTHER_WORDINGS)
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixture_really_reaches_the_parser(self):
        """The half a case cannot see once it has gone wrong: a reading that
        never decoded and a layer with no message in it answer the same
        `Nothing`, so the wording is asserted back out before anything is asked
        about it."""
        self.assertEqual(
            self.repl.strings(["textIn refusalOnScreen", "textIn noPopup"],
                              definitions=self.definitions),
            [REFUSAL, "NO QUICK MESSAGE"])

    def test_the_corpus_wording_is_matched_byte_for_byte(self):
        """The captured string, through the real parser, licenses the gate.

        Fed in with the client's own `<center>` wrapper, its own capitalisation
        and its own full stop, because the marker matches a substring of exactly
        that and a normalisation applied on either side is one nobody downstream
        can undo.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["refusedIn refusalOnScreen", "refusedIn noPopup"],
                definitions=self.definitions),
            [True, False])

    def test_the_matcher_declines_every_other_wording_the_corpus_holds(self):
        """Six real wordings, none of them this refusal.

        `Cargo is too far away. Ship is on automatic approach to cargo.` is the
        one that matters most: it is the commonest quick message either bot has
        recorded and it is the client *accepting* a command, so a rule keyed on
        "a quick message means something went wrong" would be wrong about it 795
        times in one run.

        **What this case does not reach** is a marker cut down to `cannot warp`:
        none of the six contains that phrase, so the mutation survives here and
        is killed by `test_the_marker_is_one_literal` instead. Recorded as it is
        rather than the reach being claimed wider -- a wording that would catch
        it is not in any recording, and inventing one would be #92's trap.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["refusedIn other%d" % index
                 for index in range(len(OTHER_WORDINGS))],
                definitions=self.definitions),
            [False] * len(OTHER_WORDINGS))

    def test_the_marker_is_the_clients_sentence_without_its_wrapper(self):
        """The popup carries `<center>` and the game log's copy of the same
        sentence does not, so a marker carrying the wrapper would read one
        channel and not the other."""
        self.assertEqual(
            self.repl.evaluate([
                'String.contains deadspaceWarpRefusalMarker %s'
                % elm_string(REFUSAL),
                'String.contains "<center>" deadspaceWarpRefusalMarker',
            ]),
            [True, False])


class TheStalenessBoundTest(unittest.TestCase):
    """How long one refusal keeps licensing a gate, and that it stops."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_live_refusal_licenses_the_gate(self):
        self.assertEqual(
            self.repl.evaluate(["deadspaceRefusedTheWarp %s" % sighting(REFUSAL)]),
            [True])

    def test_a_stale_refusal_licenses_nothing(self):
        """The failure #440 names: a refusal from a pocket this ship has left
        must not license a gate in this one. Asked far past the bound rather
        than one reading past it, so a boundary pair alone cannot carry it."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceRefusedTheWarp %s" % sighting(REFUSAL, 500),
                "deadspaceRefusedTheWarp %s" % sighting(REFUSAL, 5000),
            ]),
            [False, False])

    def test_the_licence_lasts_exactly_its_bound(self):
        """Both sides of the comparison, against the constant rather than
        against a number, so a bound that moves moves this case with it."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceRefusedTheWarp"
                " (Just { text = deadspaceWarpRefusalMarker"
                ", messagesInLayer = 1, displayTextsInMessage = 1"
                ", readingsSince ="
                " deadspaceWarpRefusalLicensesAGateForReadings - 1 })",
                "deadspaceRefusedTheWarp"
                " (Just { text = deadspaceWarpRefusalMarker"
                ", messagesInLayer = 1, displayTextsInMessage = 1"
                ", readingsSince = deadspaceWarpRefusalLicensesAGateForReadings })",
                "deadspaceRefusedTheWarp"
                " (Just { text = deadspaceWarpRefusalMarker"
                ", messagesInLayer = 1, displayTextsInMessage = 1"
                ", readingsSince ="
                " deadspaceWarpRefusalLicensesAGateForReadings + 1 })",
            ]),
            [True, True, False])

    def test_the_licence_survives_the_readings_a_press_costs(self):
        """A fixed value inside the bound, which is what a boundary pair cannot
        say: a live-only rule (`readingsSince == 0`) passes every boundary case
        and is inert, because taking a gate is select, wait for the panel's
        button, press."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceRefusedTheWarp %s" % sighting(REFUSAL, 0),
                "deadspaceRefusedTheWarp %s" % sighting(REFUSAL, 1),
                "deadspaceRefusedTheWarp %s" % sighting(REFUSAL, 5),
            ]),
            [True, True, True])

    def test_the_bound_is_the_arms_own_budget(self):
        """Written as `accelerationGateRefusesThisShipTicks` rather than as a
        number: past that the arm has given up on the gate anyway, so a licence
        outliving it can license nothing, and this bot has no corpus to place a
        second number against (WINGMAN.md)."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceWarpRefusalLicensesAGateForReadings"
                " == accelerationGateRefusesThisShipTicks",
                "3 < deadspaceWarpRefusalLicensesAGateForReadings",
                "deadspaceWarpRefusalLicensesAGateForReadings < 500",
            ]),
            [True, True, True])

    def test_nothing_licenses_a_gate_with_no_sighting_at_all(self):
        self.assertEqual(
            self.repl.evaluate(["deadspaceRefusedTheWarp Nothing"]), [False])


class TheAgeingTest(unittest.TestCase):
    """`quickMessageAfterReading`, folded over sessions rather than asked once.

    The port is saxrat's and its own cases are `test_quick_message_logged`'s.
    What is asked here is the half #440 depends on: that the age really advances,
    since the licence is dated off it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_session_starts_having_seen_nothing(self):
        """Against the shipped initial memory rather than a literal, so a field
        initialised to some other state fails here rather than in a run."""
        self.assertEqual(
            self.repl.evaluate([
                "initBotMemory.quickMessage == Nothing",
                "deadspaceRefusedTheWarp initBotMemory.quickMessage == False",
            ]),
            [True, True])

    def test_the_age_advances_one_reading_at_a_time(self):
        quiet = "[ %s ]" % ", ".join(["Nothing"] * 5)
        self.assertEqual(
            self.repl.evaluate([
                "ageOf (foldQuickMessage %s [ Nothing ]) == 1"
                % sighting(REFUSAL),
                "ageOf (foldQuickMessage %s %s) == 5"
                % (sighting(REFUSAL), quiet),
            ]),
            [True, True])

    def test_a_message_on_screen_starts_the_age_again(self):
        """A fresh popup replaces whatever was remembered, so a second refusal
        renews the licence rather than inheriting the first one's age."""
        self.assertEqual(
            self.repl.evaluate([
                "ageOf (foldQuickMessage %s [ Nothing, Nothing, %s ]) == 0"
                % (sighting(REFUSAL), sighting(REFUSAL)),
                "deadspaceRefusedTheWarp"
                " (foldQuickMessage %s [ Nothing, Nothing, %s ])"
                % (sighting(REFUSAL, 500), sighting(REFUSAL)),
            ]),
            [True, True])

    def test_a_later_message_ends_the_licence_at_once(self):
        """The client saying something else replaces the refusal outright rather
        than ageing it, so a licence cannot outlive the wording it came from."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceRefusedTheWarp"
                " (foldQuickMessage %s [ %s ])"
                % (sighting(REFUSAL), sighting(OTHER_WORDINGS[0])),
            ]),
            [False])

    def test_the_licence_lapses_across_a_quiet_session(self):
        """Folded rather than asserted at a number: a refusal followed by one
        reading more than the bound licenses nothing, and nothing has to notice
        the pocket changed for that to happen."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceRefusedTheWarp"
                " (foldQuickMessage %s (List.repeat"
                " (deadspaceWarpRefusalLicensesAGateForReadings + 1) Nothing))"
                % sighting(REFUSAL),
                "deadspaceRefusedTheWarp"
                " (foldQuickMessage %s (List.repeat"
                " deadspaceWarpRefusalLicensesAGateForReadings Nothing))"
                % sighting(REFUSAL),
            ]),
            [False, True])


class TheGuardTest(unittest.TestCase):
    """`gateMayBeTaken` over the grid of the two inputs this issue owns."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_rule_answers_its_four_combinations(self):
        """The two rows with no rats are the ones that must not have changed;
        the two with rats are what #440 decides between."""
        self.assertEqual(
            self.repl.evaluate([
                "mayTake %s %s" % (rats, refused)
                for rats in ("False", "True")
                for refused in ("False", "True")
            ]),
            [True, True, False, True])

    def test_348s_guard_still_refuses_an_unlicensed_gate(self):
        """The row this whole change must not have moved: rats on the grid, no
        licence of any kind, and the gate is refused. With every exception
        `False` the rule *is* #348's guard, unchanged."""
        self.assertEqual(self.repl.evaluate(["mayTake True False"]), [False])

    def test_the_refusal_overrides_the_rats(self):
        self.assertEqual(self.repl.evaluate(["mayTake True True"]), [True])

    def test_the_press_says_which_authority_it_is_on(self):
        """`The overview is clear of rats` is **false** on a gate taken under
        this licence, and a log claiming a clear grid on a reading that had rats
        on it is worse than no line at all. The sentence is rendered from the
        rule rather than asserted as a substring over the branch."""
        answer, clear = self.repl.strings([
            "describeGateTakingAuthority (authority True)",
            "describeGateTakingAuthority (authority False)",
        ])
        self.assertIn("refused this ship a warp", answer)
        self.assertIn("natural phenomena", answer)
        self.assertNotIn("clear of rats", answer)
        self.assertIn("clear of rats", clear)

    def test_the_authority_rule_names_this_one_last(self):
        """Ordering, executed. The three older exceptions name *who* licensed
        the gate and this one names why leaving by warp was not available, so it
        is the answer when nothing else licensed it. Nothing decides on the
        order -- `gateMayBeTaken` is a disjunction -- but the sentence an
        operator reads does."""
        self.assertEqual(
            self.repl.evaluate([
                "gateTakingAuthority { calledByTheCommander = True"
                ", rejoiningAfterARetreat = False, followingTheCommander = False"
                ", deadspaceRefusedTheWarp = True }"
                " == TheCommanderCalledThisGate",
                "gateTakingAuthority { calledByTheCommander = False"
                ", rejoiningAfterARetreat = True, followingTheCommander = False"
                ", deadspaceRefusedTheWarp = True }"
                " == TheShipIsRejoiningAfterARetreat",
                "gateTakingAuthority { calledByTheCommander = False"
                ", rejoiningAfterARetreat = False, followingTheCommander = True"
                ", deadspaceRefusedTheWarp = True }"
                " == TheCommanderLeftThisGrid",
                "authority True == TheClientRefusedTheWarpForDeadspace",
            ]),
            [True] * 4)


class TheRefusalRefillsTheBudgetTest(unittest.TestCase):
    """#439's refill, reached by #440's reason.

    This is the case the two changes exist to make: a gate the ship has already
    given up on, and then the client refuses it a warp. Before #439 a licence
    arriving on a spent budget bought nothing -- the live reading that change
    was filed on printed `GIVEN UP after 41 readings of asking` beside
    `FOLLOWING HIM THROUGH IT` while the ship sat still -- and #440 would have
    reproduced it exactly, since a refusal is a reason arriving on a gate the
    hunting arm has usually been asking about for a while.

    **Nothing here is new machinery**, and that is the point of #439's closed
    record: adding the field to `gateMayBeTaken` alone does not compile, so the
    reason reaches `askedReadingsRefilledByANewLicence` by construction. What
    these cases establish is that the construction really does carry it, since
    a rule that is right about four reasons and silently drops a fifth is
    exactly what the type was closed to prevent.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_gate_given_up_on_can_be_asked_again_once_the_client_refuses(self):
        """The whole case, end to end through the two shipped rules: a budget
        spent under the clear grid, a refusal arriving, and the arm going from
        `GiveUpOnThisGate` back to acting."""
        self.assertEqual(
            self.repl.evaluate([
                # The budget was spent under the clear grid alone, and is past
                # the arm's own give-up.
                "gateStep (accelerationGateRefusesThisShipTicks + 1)"
                " == GiveUpOnThisGate",
                # The refusal arrives on a grid that now has rats on it, which
                # is the state #348's guard would otherwise refuse.
                "refill (licenceWith True False) (licenceWith False True)"
                " (accelerationGateRefusesThisShipTicks + 1) == 0",
                # So the arm is asking again on that reading.
                "gateStep (refill (licenceWith True False) (licenceWith False True)"
                " (accelerationGateRefusesThisShipTicks + 1)) == PressActivateGate",
            ]),
            [True] * 3)

    def test_the_refusal_refills_at_most_once(self):
        """The bound on the refill, which is what stops a reason that comes and
        goes handing the budget back forever. Once a reading has asked under the
        refusal, `gateLicenceSpentUnderAfter` records it and the same reason
        arriving again buys nothing."""
        spent = ("spentUnderAfter True True (licenceWith True False)"
                 " (licenceWith False True)")
        self.assertEqual(
            self.repl.evaluate([
                "(%s).deadspaceRefusedTheWarp" % spent,
                "(%s).gridIsClearOfRats" % spent,
                "refill (licenceWith True False) (%s) 41 == 41" % spent,
            ]),
            [True] * 3)

    def test_a_refusal_already_spent_under_is_not_a_new_reason(self):
        """The other direction of the same bound: a refusal that was the reason
        the budget was spent in the first place refills nothing when it is still
        the reason."""
        self.assertEqual(
            self.repl.evaluate([
                "refill (licenceWith True False) (licenceWith True False) 41"
                " == 41",
                "refill (licenceWith True True) (licenceWith True True) 41"
                " == 41",
            ]),
            [True, True])

    def test_the_licence_and_the_permission_answer_alike_about_the_refusal(self):
        """`gateMayBeTaken` is defined over `gateLicenceFromCase`, so the arm's
        permission and the budget's refill cannot come to hold two opinions
        about whether a refusal licenses a gate. Asked over the grid of the two
        reasons this file varies."""
        self.assertEqual(
            self.repl.evaluate([
                "gateIsLicensed (licenceWith %s %s) == mayTake %s %s"
                % (refused, clear, "False" if clear == "True" else "True",
                   refused)
                for refused in ("False", "True")
                for clear in ("False", "True")
            ]),
            [True] * 4)

    def test_the_licence_carries_the_refusal_as_its_own_reason(self):
        """Not folded into another field, which a port that ran out of record
        fields might do -- the refill compares reasons one at a time, so a
        refusal spelled as `gridIsClearOfRats` would refill on every rat that
        died."""
        self.assertEqual(
            self.repl.evaluate([
                "(licenceWith True False).deadspaceRefusedTheWarp",
                "not (licenceWith True False).gridIsClearOfRats",
                "not (licenceWith False True).deadspaceRefusedTheWarp",
                "(licenceWith False True).gridIsClearOfRats",
                "not noGateLicence.deadspaceRefusedTheWarp",
            ]),
            [True] * 5)


class TheArmTest(unittest.TestCase):
    """`accelerationGateStep` run for real over a grid with rats and a gate."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding(
                "ratsAndAGate",
                grid_showing(headers=header_labels(2))),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixture_really_carries_rats_and_a_gate(self):
        """Otherwise everything below passes on a grid #348's guard would have
        let through anyway, which is a case that checks nothing."""
        self.assertEqual(
            self.repl.evaluate([
                "(ratsAndAGate |> Maybe.map (getNamesOfRatsInOverview"
                " >> List.length)) == Just 1",
                "(ratsAndAGate |> Maybe.map (accelerationGatesOnOverview"
                " >> List.length)) == Just 1",
            ], definitions=self.definitions),
            [True, True])

    def test_rats_hold_the_gate_with_no_refusal_remembered(self):
        self.assertIn(
            "rats are still on the grid",
            self.repl.strings(["gateArm Nothing ratsAndAGate"],
                              definitions=self.definitions)[0])

    def test_a_refused_warp_takes_the_gate(self):
        """The whole of #440 in one answer: the same grid, the same rats, and a
        remembered refusal is the difference between waiting and pressing."""
        answer = self.repl.strings(
            ["gateArm %s ratsAndAGate" % sighting(REFUSAL)],
            definitions=self.definitions)[0]
        self.assertIn("refused this ship a warp", answer)
        self.assertNotIn("rats are still on the grid", answer)

    def test_a_stale_refusal_holds_the_gate_again(self):
        """The other side of the bound, through the arm rather than the rule, so
        a licence that never lapsed would be visible as a gate taken."""
        self.assertIn(
            "rats are still on the grid",
            self.repl.strings(
                ["gateArm %s ratsAndAGate" % sighting(REFUSAL, 500)],
                definitions=self.definitions)[0])

    def test_an_unrelated_message_holds_the_gate(self):
        """The commonest quick message either bot has recorded, remembered live,
        and the arm behaves exactly as it does with nothing remembered."""
        self.assertIn(
            "rats are still on the grid",
            self.repl.strings(
                ["gateArm %s ratsAndAGate" % sighting(OTHER_WORDINGS[0])],
                definitions=self.definitions)[0])


class TheRootReachesItTest(unittest.TestCase):
    """CLAUDE.md's own standard: state reachability, not just correctness.

    `accelerationGateStep` sits below the drones and below the guns (#348,
    #326), and the state this licence acts on -- rats on the grid -- is the
    state those arms answer in. So whether it is reached at all is a real
    question, and this is where the two mutations a suite of rule-level cases
    alone would miss are caught: a licence wired to nothing, and an arm nothing
    reaches.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        # The roster corroborates (#419) and the guns are cycling, so the arms
        # above hand the reading down and nothing but this licence decides it.
        cls.definitions = [
            reading_binding(
                "gunsCycling",
                grid_showing(headers=header_labels(2), modules=((10, True),),
                             targets=[[RAT, "2,000 m"]])),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_refusal_is_reached_through_the_whole_root(self):
        taken, held = self.repl.strings([
            "rootFor %s gunsCycling" % sighting(REFUSAL),
            "rootFor Nothing gunsCycling",
        ], definitions=self.definitions)
        self.assertIn("refused this ship a warp", taken)
        self.assertIn("rats are still on the grid", held)

    def test_a_stale_refusal_is_reached_and_declines(self):
        """The bound asked through the root as well, so a licence that outlived
        the arm's own budget would show up as a gate taken here."""
        self.assertIn(
            "rats are still on the grid",
            self.repl.strings(
                ["rootFor %s gunsCycling" % sighting(REFUSAL, 500)],
                definitions=self.definitions)[0])


class TheTwoOlderLicencesAreNotThisOneTest(unittest.TestCase):
    """#440's design question, executed rather than argued in prose.

    The refusal was asked to replace `commanderLeftTheGrid` or
    `rejoiningAfterARetreat`, and it cannot, because the three are independent
    inputs: each licenses the gate on its own, so none of them is doing another's
    work and removing any one changes what the bot does on readings the others
    cannot answer.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_each_licence_answers_on_its_own(self):
        """Four rows, rats up on every one: each exception alone takes the gate.
        A rule where one subsumed another would have a row that only answers with
        two of them switched on."""
        base = ("gateMayBeTaken { ratsOnTheGrid = True"
                ", calledByTheCommander = %s"
                ", commanderLeftTheGrid = %s"
                ", rejoiningAfterARetreat = %s"
                ", deadspaceRefusedTheWarp = %s }")
        self.assertEqual(
            self.repl.evaluate([
                base % ("True", "False", "False", "False"),
                base % ("False", "True", "False", "False"),
                base % ("False", "False", "True", "False"),
                base % ("False", "False", "False", "True"),
                base % ("False", "False", "False", "False"),
            ]),
            [True, True, True, True, False])

    def test_the_absence_based_licence_fires_where_no_warp_was_commanded(self):
        """Why the refusal cannot replace #411's follow: the follow's whole
        subject is a reading on which nothing warped, and with nothing warped
        there is no refusal to read. Asked of the follow's own rule, so the two
        populations are shown to be different rather than described as such."""
        self.assertEqual(
            self.repl.evaluate([
                "followTheCommanderThroughTheGate"
                " { presence = CommanderGoneFromTheGrid"
                " commanderGoneReadingsBeforeFollowing"
                ", accelerationGatesOnTheGrid = 1 }",
                "deadspaceRefusedTheWarp Nothing == False",
            ]),
            [True, True])

    def test_the_rejoin_asks_the_gate_before_it_warps(self):
        """Why the refusal cannot replace #429's rejoin either: on a grid with a
        gate the recovery answers `GateThroughToTheCommander` *before* it reaches
        either warp, so no warp goes out and no refusal exists on the readings
        that permission is for."""
        recovering = ("retreatRecoveryStep { recovering = True"
                      ", commanderIsNamed = True, commanderIsOnThisGrid = False"
                      ", bannerNamesTheCommander = False"
                      ", remembersWhereTheCommanderWas = False"
                      ", anAccelerationGateIsOnThisGrid = %s"
                      ", fleetWindowNamesTheCommander = True"
                      ", shipIsWarpingOrJumping = False, askedReadings = 0 }")
        self.assertEqual(
            self.repl.evaluate([
                "%s == GateThroughToTheCommander" % (recovering % "True"),
                "%s == WarpToTheCommanderFromTheFleetWindow"
                % (recovering % "False"),
            ]),
            [True, True])


class TheStatusLineTest(unittest.TestCase):
    """What a run has to be able to see, since the licence lapses on its own."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            reading_binding("ratsAndAGate",
                            grid_showing(headers=header_labels(2))),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_gate_clause_names_the_refusal_while_it_is_live(self):
        named, unnamed = self.repl.strings([
            "describeGate %s ratsAndAGate" % sighting(REFUSAL),
            "describeGate Nothing ratsAndAGate",
        ], definitions=self.definitions)
        self.assertIn("refused this ship a warp for deadspace", named)
        self.assertIn("rats still on the grid -- not taking it", unnamed)

    def test_the_status_line_carries_the_wording(self):
        """The clause an operator reads first, and the three states it has to
        keep apart -- a live refusal, an aged one and a session that has seen
        nothing. Asked through `statusTextFromState` rather than through
        `describeQuickMessage`, because a clause nothing prints is this repo's
        signature bug."""
        live, aged, quiet = self.repl.strings([
            "statusFor %s ratsAndAGate" % sighting(REFUSAL),
            "statusFor %s ratsAndAGate" % sighting(REFUSAL, 7),
            "statusFor Nothing ratsAndAGate",
        ], definitions=self.definitions)
        self.assertIn('Quick msg (now): "%s"' % REFUSAL, live)
        self.assertIn('Quick msg (7 ago): "%s"' % REFUSAL, aged)
        self.assertIn("Quick message: none on this reading", quiet)

    def test_a_message_older_than_the_status_bound_is_not_reprinted(self):
        """The status line's own bound is `quickMessageStaleAfterReadings` and no
        rule reads it -- two numbers because they answer different questions, and
        collapsing them would tie the licence to a number chosen for a log."""
        self.assertEqual(
            self.repl.evaluate([
                "deadspaceWarpRefusalLicensesAGateForReadings"
                " < quickMessageStaleAfterReadings",
                'describeQuickMessage %s == "Quick message: none recent."'
                % sighting(REFUSAL, 5000),
            ]),
            [True, True])


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

    def test_the_sighting_is_settled_in_the_memory_update(self):
        """#102's and #126's placement rule: the memory update is the only thing
        that runs on every reading unconditionally, and a reading's popup is gone
        by the next one -- CLAUDE.md's `loadRefusedByClient` shape."""
        binding = indented_let_binding(self.source, "quickMessageNow")
        self.assertIn("quickMessageAfterReading", binding)
        self.assertIn("onScreenNow = quickMessageOnScreen", collapsed(binding))
        self.assertIn("before = botMemoryBefore.quickMessage",
                      collapsed(binding))
        self.assertIn("quickMessage = quickMessageNow", collapsed(self.update))

    def test_the_counter_reads_this_readings_sighting(self):
        """The decision reads the memory this update writes, so a counter
        advanced under `botMemoryBefore`'s sighting runs a reading behind the arm
        -- and on the reading a refusal arrives that is the difference between
        `accelerationGateRefusesThisShipTicks` being reachable and not. #397's
        arrangement, and `commanderGridPresenceNow`'s own reason.

        Read off `gateLicenceNow` rather than off `askingTheGateToOpen`, which
        is where #439 moved the record: that binding is now the licence the
        refill also reads, so this reading's sighting has to reach it or the
        refusal refills a budget it was never counted against.
        """
        binding = indented_let_binding(self.source, "gateLicenceNow")
        self.assertIn("deadspaceRefusedTheWarp quickMessageNow",
                      collapsed(binding))
        self.assertNotIn("botMemoryBefore.quickMessage", binding)

    def test_the_rule_dates_the_sighting_itself(self):
        """`memory.quickMessage` and `quickMessageOnScreen` are the same type at
        a call site and only one of them carries an age, so a rule that trusted
        its caller would license a gate off a popup shown before the last
        pocket."""
        rule = declaration(self.source, "deadspaceRefusedTheWarp sighting =")
        self.assertIn("readingsSince", rule)
        self.assertIn("deadspaceWarpRefusalLicensesAGateForReadings", rule)
        self.assertIn("deadspaceWarpRefusalMarker", rule)

    def test_one_rule_with_four_readers(self):
        """The arm, the press's own wording, the memory update and the status
        clause ask one declaration. A `deadspaceRefusedTheWarp` written as
        anything else at any of those sites is two rules on two schedules --
        #102's defect.

        Each reader is required to hand the rule a sighting rather than merely
        to name it, which is what a substring over the block would have let
        through: `gateMayBeTaken`'s own record field is spelled the same as the
        rule, so a site passing a literal `False` mentions the name too.
        """
        self.assertEqual(
            self.source.count("\ndeadspaceRefusedTheWarp :"), 1)
        self.assertEqual(
            self.source.count("\ndeadspaceRefusedTheWarp sighting =\n"), 1)
        for reader in ("takeTheAccelerationGate context gateToTake =",
                       "pressTheAccelerationGate context gateToTake =",
                       "updateMemoryForNewReadingFromGame context botMemoryBefore =",
                       "describeAccelerationGateAsk context ="):
            with self.subTest(reader=reader):
                body = collapsed(declaration(self.source, reader))
                self.assertTrue(
                    "deadspaceRefusedTheWarp context.memory.quickMessage"
                    in body
                    or "deadspaceRefusedTheWarp quickMessageNow" in body,
                    "%s has to ask the rule about a sighting rather than "
                    "restate it" % reader)

    def test_the_marker_is_one_literal(self):
        """A second copy of the client's sentence is two matchers drifting
        apart, which is what `gateKeyClosingMarker`'s arrangement exists to
        stop."""
        self.assertEqual(
            self.source.count("\ndeadspaceWarpRefusalMarker :"), 1)
        self.assertEqual(
            self.source.count(
                '"You cannot warp there because natural phenomena'
                ' are disrupting the warp."'), 1,
            "the sentence is quoted more than once, so there is more than one"
            " matcher to keep in step")

    def test_the_bound_is_written_as_the_arms_own(self):
        """A number here would be a second opinion about the same stretch of
        readings, on a bot with no corpus to place one against."""
        rule = declaration(
            self.source, "deadspaceWarpRefusalLicensesAGateForReadings =")
        self.assertIn("accelerationGateRefusesThisShipTicks", rule)
        self.assertIsNone(
            re.search(r"\d", rule),
            "the bound carries a number of its own: %r" % rule)

    def test_the_clause_is_printed_from_the_status_line(self):
        status = declaration(self.source, "statusTextFromState context =")
        self.assertIn("describeQuickMessage context.memory.quickMessage",
                      collapsed(status))

    def test_the_port_is_saxrats_own_declarations(self):
        """The reader, the ageing and the rendering are `eve-online-saxrat`'s,
        compared byte for byte rather than merely both present. Two copies of a
        channel reader is how the bot with a corpus and the bot starting one come
        to disagree about what the client said."""
        saxrat = os.path.join(
            REPO_DIR, "implement", "applications", "eve-online",
            "eve-online-saxrat", "Bot.elm")
        with open(saxrat, encoding="utf-8") as handle:
            other = handle.read()
        for name in ("quickMessageOnScreen readingFromGameClient =",
                     "quickMessageAfterReading state =",
                     "quickMessageTextForStatusLine text =",
                     "describeQuickMessage sighting =",
                     "quickMessageStatusCharacterBudget =",
                     "quickMessageStaleAfterReadings ="):
            with self.subTest(name=name):
                self.assertEqual(declaration(self.source, name),
                                 declaration(other, name))


class TheCorpusTest(unittest.TestCase):
    """The wording, recounted from `~/eve-bot-logs` as relations.

    Numbers rather than relations would turn a true claim red as the corpus
    grows, so what is asserted is that each run #440 names still carries the
    sentence, that the popup's copy carries the `<center>` wrapper the marker
    does not, and that the shipped marker reads every one of them.
    """

    #: The runs #440 names, which are the ones this machine is asked about. A
    #: glob over the whole directory would make "the wording is not here" mean
    #: two different things -- the corpus disagreeing, and a machine that simply
    #: holds different runs -- and only the first is a finding.
    NAMED = ("saxrat_run12.log", "mission_run14.log", "mission_run32.log")

    @classmethod
    def setUpClass(cls):
        present = [name for name in cls.NAMED
                   if os.path.exists(os.path.join(EVE_BOT_LOGS, name))]
        if not present:
            raise unittest.SkipTest("none of the recorded runs are present")
        cls.runs = {}
        for name in present:
            hits = []
            with open(os.path.join(EVE_BOT_LOGS, name),
                      encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "natural phenomena are disrupting" in line:
                        hits.append(line.rstrip("\n"))
            cls.runs[name] = hits

    def test_every_run_the_issue_names_carries_it(self):
        """A relation rather than a count, so a growing corpus cannot turn a
        true claim red -- and a *failure*, not a skip, on a machine that has the
        run and cannot find the wording in it, since that is the evidence for
        this change having disappeared."""
        for name, hits in sorted(self.runs.items()):
            with self.subTest(run=name):
                self.assertTrue(
                    hits, "%s no longer carries the deadspace refusal" % name)

    def test_the_shipped_marker_reads_every_recorded_sighting(self):
        """Read out of the source rather than restated here, so a matcher that
        drifts from what the client writes fails in this file rather than in a
        run."""
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            source = handle.read()
        match = re.search(
            r"\ndeadspaceWarpRefusalMarker =\n    \"([^\"]+)\"", source)
        self.assertIsNotNone(match, "no marker literal in Bot.elm")
        marker = match.group(1)
        for name, hits in sorted(self.runs.items()):
            with self.subTest(run=name):
                self.assertTrue(all(marker in line for line in hits),
                                "the marker misses a line in %s" % name)

    def test_the_popup_carries_the_wrapper_and_the_game_log_does_not(self):
        """Which is why the marker carries neither: one literal reads both
        channels. The status clause's copy is the quick message; the `game log:`
        line is the client's `(notify)` copy of the same sentence."""
        popups = [line for hits in self.runs.values() for line in hits
                  if "Quick message" in line]
        game_log = [line for hits in self.runs.values() for line in hits
                    if "game log:" in line]
        self.assertTrue(popups, "no quick-message sighting in the corpus")
        self.assertTrue(game_log, "no game-log sighting in the corpus")
        self.assertTrue(
            all("<center>You cannot warp there" in line for line in popups))
        self.assertTrue(
            all("<center>" not in line for line in game_log))

    def test_the_popup_copies_are_lines_rather_than_readings(self):
        """The relation the doc comments' two figures rest on, and this repo's
        own standing warning applied to its own evidence: the status line is
        reprinted under every decision and the game log's copy is written once,
        so the live-popup lines outnumber the game-log ones by a wide margin and
        neither number is a count of readings."""
        popups = [line for hits in self.runs.values() for line in hits
                  if "on screen now" in line]
        game_log = [line for hits in self.runs.values() for line in hits
                    if "game log:" in line]
        self.assertTrue(game_log)
        self.assertGreater(len(popups), 10 * len(game_log))


if __name__ == "__main__":
    unittest.main()
