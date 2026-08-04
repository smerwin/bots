"""Tests for the mission runner giving back a mission it cannot progress.

Issue #54. The verdict was already right and the response was inert: run 12
raised `askForHelpToGetUnstuck` **817 times** on
`Illegal Activity (1 of 3) -- Retrieve Gallente Light Marines` and was stopped by
hand; run 13 restarted on the same mission and reached the same state in **29
readings**, because a fresh process cannot escape a mission that is still
accepted and still impossible. Recovery took a person: fly Irnin to Amarr, dock,
open the agent conversation, `Quit Mission`, confirm, restart with
`decline-mission=Illegal Activity`.

**What is being pinned, and what is deliberately not.**

The give-up branch itself is untouched, and one case here says so: it still
fires at `nothingToDoTicksBeforeCryingStuck` and still ends in
`askForHelpToGetUnstuck`. #41 and #53 both confirmed that verdict firing on real
stalls, so this change adds a response to it rather than retuning it.

**The threshold is a relation, not a number.** Quitting costs standing and
cannot be undone, so it may only happen well after the alarm has been raised.
`missionStalledReadings` counts a strict subset of the readings
`nothingToDoTicks` counts -- every reading that advances the first advances the
second, and every reading that resets the second resets the first -- so a
threshold at twice `nothingToDoTicksBeforeCryingStuck` cannot be reached without
the alarm having sounded for at least 300 readings. That subset relation is
asserted directly, on the conditions as written.

**A bot that is merely busy must not reach it.** The counter excludes any
reading where the ship reports a manoeuvre -- an approach reads
`ManeuverApproach` for as long as it runs, which the recordings show as
`Already on the way -- let it run.` 68 to 94 times per run -- and any reading
where the previous step put effects on the client, which covers combat, looting,
gate activation and every context-menu cascade.

**Mission names are read out of `~/eve-bot-logs`, not invented.** The stripping
rule that feeds `decline-mission` is executed through the real `Bot.elm` in
`elm repl` against every mission name the twelve recorded runs contain, in both
the tracker's spelling and the agent's own offer.

**And #53 has since confirmed the verdict this responds to was right.** PR #57
found that run 12's wrecks were genuinely all looted and the mission item was in
a `Cargo Container` that left the grid sixteen readings later -- so the bot's
"this mission is not going to progress on its own" was correct, and quitting is
the only response left rather than a workaround for a bug.

**Every case that reads `Bot.elm` as text goes through `collapsed()`**, which
reduces every run of whitespace to one space, and the expected strings are
written the same way. PR #58 is the reason: running `elm-format` across the
sources moved where lines break and broke three tests that had asserted on the
old layout. A formatter is entitled to rewrap anything, so these assert the
structure and not its typography.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH with the app's dependencies fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
LOG_GLOB = os.path.expanduser("~/eve-bot-logs/mission_run*.log")

# The mission at the centre of #54, as the tracker spells it.
STUCK_MISSION = "Illegal Activity (1 of 3)"
# What must go into the session's decline list for the rest of the chain to be
# refused too -- the operator typed exactly this by hand after run 13.
STUCK_MISSION_DECLINED_AS = "Illegal Activity"


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def collapsed(text):
    """Source text with every run of whitespace reduced to one space.

    Every assertion below that reads `Bot.elm` goes through this, and the
    expected strings are written in the same form. PR #58 is why: running
    `elm-format` across the sources moved where lines happened to break and
    broke three tests that had asserted on the old layout. What those tests
    meant -- and what these mean -- is the structure, not its typography, and a
    formatter is entitled to rewrap anything it likes.
    """
    return " ".join(text.split())


def int_constant(source, name):
    """The right-hand side of an `Int` constant, whitespace-normalised."""
    match = re.search(r"^" + name + r" : Int\n" + name + r" =\n(.+?)(?=\n\n)",
                      source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return collapsed(match.group(1))


def function_body(source, signature_start, next_top_level):
    start = source.index(signature_start)
    end = source.index(next_top_level, start)
    return source[start:end]


def update_memory_source(source):
    """`updateMemoryForNewReadingFromGame`'s whole definition.

    Every binding and record field asserted on below is scoped to it, because
    `initBotMemory` sets the same field names a few hundred lines earlier and an
    unscoped search finds the initial values instead -- which say nothing about
    whether a counter can advance.
    """
    return function_body(
        source,
        "updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings",
        "\ngetNamesOfRatsInOverview :")


def let_binding_body(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding.

    The same extraction `test_ammo_silenced_bound.py` uses, so the counter
    property below is asserted the same way there and here.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    if end is None:
        end = re.search(r"\n    in\n", rest)
    return rest[:end.start()] if end else rest


def record_field_body(source, name):
    """The right-hand side of a field in the record a function returns."""
    return let_binding_body(source, name, indent="    , ")


def branch_results(body):
    """The value each branch of an `if`/`else` chain evaluates to."""
    results = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped == "else" or (
                stripped.startswith(("if ", "else if ")) and stripped.endswith(" then")):
            continue
        results.append(stripped)
    return results


def mission_names_from_logs():
    """Every mission name the recorded runs contain, from two sources.

    The tracker's own spelling, off the `Mission: <name> -- <objective>` status
    line, and the agent's, off the bot's `Accept the mission '<name>'` decision.
    Both matter: the first is what gets recorded when a mission is abandoned and
    the second is what a later offer is matched against, and the whole point of
    dropping the `(N of M)` counter is that those two meet on the rest of the
    chain.
    """
    tracker = set()
    offered = set()
    tracker_line = re.compile(r"^# \[[\d.]+\] \([\d.]+s\) Mission: (.*?) -- ")
    offer_line = re.compile(r"Accept the mission '(.*?)'\.")
    for path in sorted(glob.glob(LOG_GLOB)):
        with open(path, encoding="utf-8", errors="replace") as log:
            for line in log:
                if not line.endswith("\n"):
                    # A run still being appended to: skip the partial line.
                    break
                found = tracker_line.match(line)
                if found:
                    tracker.add(found.group(1))
                found = offer_line.search(line)
                if found:
                    offered.add(found.group(1))
    return tracker, offered


PREAMBLE = (
    "import Bot exposing (..)",
    "import Common.EffectOnWindow as EffectOnWindow",
    "import Common.Basics exposing (stringContainsIgnoringCase)",
)


def repl():
    return open_repl(ElmRepl, prefix="test-abandon-mission-", preamble=PREAMBLE)


class TheDeclineNameIsExecutedRatherThanMirrored(unittest.TestCase):
    """`missionNameForDeclining`, run for real against the recorded names."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.tracker_names, cls.offered_names = mission_names_from_logs()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_chain_counter_is_dropped(self):
        # The whole reason this function exists: quitting (1 of 3) is pointless
        # if the agent can hand back (2 of 3) two minutes later.
        answers = self.repl.strings([
            "missionNameForDeclining " + elm_string(STUCK_MISSION),
            'missionNameForDeclining "Illegal Activity (2 of 3)"',
            'missionNameForDeclining "Minmatar Plot (3 of 3)"',
            'missionNameForDeclining "Recon (1 of 3)"',
        ])
        self.assertEqual(answers, [STUCK_MISSION_DECLINED_AS,
                                   STUCK_MISSION_DECLINED_AS,
                                   "Minmatar Plot",
                                   "Recon"])

    def test_a_name_with_no_counter_is_left_alone(self):
        names = ["Gone Berserk", "The Damsel In Distress",
                 "Save a Man's Career", "Unauthorized Military Presence"]
        answers = self.repl.strings(
            ["missionNameForDeclining " + elm_string(name) for name in names])
        self.assertEqual(answers, names)

    def test_it_never_produces_an_empty_decline_entry(self):
        # An empty entry in the decline list is a substring of every mission
        # name there is, so it refuses everything the agent ever offers --
        # `splitSettingIntoNames` drops empties for exactly this reason.
        answers = self.repl.strings([
            'missionNameForDeclining "(1 of 3)"',
            'missionNameForDeclining "   "',
            'missionNameForDeclining ""',
        ])
        self.assertEqual(answers[0], "(1 of 3)")
        self.assertEqual(answers[1], "")
        self.assertEqual(answers[2], "")
        # The two blanks are only reachable from a blank tracker name, which
        # `missionNameFromTracker` refuses to produce at all.
        self.assertIn("nonEmptySettingValue",
                      collapsed(function_body(
                          bot_elm(),
                          "missionNameFromTracker : ReadingFromGameClient",
                          "\ntrackerStillShowsMission :")))

    def test_every_recorded_mission_name_survives_the_round_trip(self):
        """The stripped name must match its own chain and nothing else.

        Run against every mission name in `~/eve-bot-logs` rather than a chosen
        few, because the failure mode is a stripped name that is a substring of
        an unrelated mission -- which would have the bot decline work it can do,
        silently, for the rest of the session.

        Both halves are executed in Elm, and by the two functions that actually
        decide it: `missionNameForDeclining` produces the entry and
        `stringContainsIgnoringCase` is what `shouldDeclineMission` matches it
        with. The whole cross product is one expression rather than one per
        pair, because the repl costs about a tenth of a second an expression and
        the recordings hold enough names to make that minutes.
        """
        names = sorted(self.tracker_names | self.offered_names)
        if not names:
            # CI has no recordings, and neither does a fresh clone. Skipping is
            # right only for *nothing* to read -- a machine that has logs but
            # whose names no longer parse out of them is drift worth failing on,
            # which is why the assertion below is not the skip condition. Same
            # split `test_dock_outranks_the_fight` makes.
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        self.assertGreater(len(names), 20,
                           "recorded runs are present but hold almost no "
                           "mission names -- the status line's wording has "
                           "drifted from what this reads")
        elm_names = "[ " + ", ".join(elm_string(name) for name in names) + " ]"
        # One line, no blank lines: `elm repl` ends a multi-line entry at the
        # first blank one, which silently truncates a pretty-printed expression
        # into a syntax error.
        expression = (
            "(let names = %s in names |> List.concatMap (\\a -> names "
            "|> List.filterMap (\\b -> if stringContainsIgnoringCase "
            "(missionNameForDeclining a) b == (missionNameForDeclining a "
            "== missionNameForDeclining b) then Nothing else Just (a ++ "
            "\" -> \" ++ b))) |> String.join \"; \")" % elm_names)
        violations = self.repl.strings([expression])[0]
        self.assertEqual(
            violations, "",
            "a declined mission name matched an unrelated mission, or failed "
            "to match its own chain")


class TheIdleTestIsExecutedRatherThanMirrored(unittest.TestCase):
    """`previousStepDispatchedEffects`, the "is the bot acting" half."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_step_that_did_nothing_reads_as_idle(self):
        answers = self.repl.booleans([
            "previousStepDispatchedEffects []",
            "previousStepDispatchedEffects [ [] ]",
        ])
        self.assertEqual(answers, [False, False],
                         "no effects at all is the state the verdict counts")

    def test_a_keypress_counts_as_acting_not_only_a_click(self):
        # Typing a station name into the search bar presses no mouse button,
        # and a counter that only watched the mouse would count the route being
        # set as the mission going nowhere.
        answers = self.repl.booleans([
            "previousStepDispatchedEffects "
            "[ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE ] ]",
            "previousStepDispatchedEffects "
            "[ [ EffectOnWindow.ButtonDown EffectOnWindow.MouseButtonLeft ] ]",
            "previousStepDispatchedEffects "
            "[ [ EffectOnWindow.MouseMoveTo { x = 1, y = 2 } ] ]",
        ])
        self.assertEqual(answers, [True, True, True])

    def test_only_the_step_just_dispatched_counts(self):
        # A step that acted two readings ago is not the bot acting now, and
        # letting it count would hold the counter at zero through a stall that
        # began right after a click.
        answers = self.repl.booleans([
            "previousStepDispatchedEffects "
            "[ [], [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE ] ]",
        ])
        self.assertEqual(answers, [False])


class TheThresholdIsARelationNotANumber(unittest.TestCase):
    """Quitting may only happen long after the alarm has been sounding."""

    def setUp(self):
        self.source = bot_elm()

    def test_the_abandon_threshold_is_derived_from_the_alarm_threshold(self):
        # Written as a multiple so the two cannot drift apart silently: a bare
        # 600 beside a retuned alarm would be a threshold whose justification
        # had quietly stopped being true.
        self.assertEqual(
            int_constant(self.source, "missionStalledReadingsBeforeAbandoning"),
            "nothingToDoTicksBeforeCryingStuck * 2")

    def test_the_alarm_itself_is_unchanged(self):
        # #41 and #53 both confirmed this verdict firing on real stalls. This
        # change adds a response to it and must not retune it.
        self.assertEqual(
            int_constant(self.source, "nothingToDoTicksBeforeCryingStuck"), "300")
        pocket = collapsed(function_body(
            self.source,
            "decideActionInMissionPocket context seeUndockingComplete =",
            "\ndockOutranksTheFight :"))
        self.assertIn("this mission is not going to progress on its own", pocket)
        self.assertIn(
            "if nothingToDoTicksBeforeCryingStuck < context.memory.nothingToDoTicks then",
            pocket)
        self.assertIn("askForHelpToGetUnstuck", pocket)

    def test_the_stall_counter_is_a_subset_of_the_alarm_counter(self):
        """Every reading counted here is also counted by `nothingToDoTicks`.

        This is what makes "twice the alarm's threshold" mean "the alarm has
        been raised for at least 300 readings first". It holds because the
        stall counter's condition is a conjunction that includes both of the
        alarm counter's -- in space, and the objective unchanged -- plus more.
        """
        update_memory = update_memory_source(self.source)
        stall = collapsed(let_binding_body(update_memory, "missionIsGoingNowhere"))
        alarm = collapsed(record_field_body(update_memory, "nothingToDoTicks"))

        # The alarm counter's two conditions, as it writes them.
        self.assertIn("context.readingFromGameClient.shipUI /= Nothing", alarm)
        self.assertIn(
            "missionObjectiveText context.readingFromGameClient == botMemoryBefore.lastObjectiveText",
            alarm)

        # The stall counter carries the second one itself, and gets the first
        # from `readingShowsAMissionGoingNowhere`.
        self.assertIn(
            "missionObjectiveText context.readingFromGameClient == botMemoryBefore.lastObjectiveText",
            stall)
        self.assertIn("readingShowsAMissionGoingNowhere", stall)
        going_nowhere = collapsed(function_body(
            self.source,
            "readingShowsAMissionGoingNowhere : ReadingFromGameClient",
            "\ntrackerTravelStepLabel :"))
        self.assertIn("readingFromGameClient.shipUI /= Nothing", going_nowhere)

    def test_a_busy_bot_cannot_reach_the_verdict(self):
        """The two exclusions that are not conditions of the alarm at all."""
        stall = collapsed(let_binding_body(update_memory_source(self.source),
                                           "missionIsGoingNowhere"))
        self.assertIn("not (previousStepDispatchedEffects context.previousStepsEffects)",
                      stall,
                      "a bot clicking, dragging or typing is a bot working")

        going_nowhere = collapsed(function_body(
            self.source,
            "readingShowsAMissionGoingNowhere : ReadingFromGameClient",
            "\ntrackerTravelStepLabel :"))
        self.assertIn("maneuverType", going_nowhere,
                      "an approach, a warp or an orbit must not count -- a "
                      "ship mid-approach is not a mission going nowhere")
        self.assertIn("routeIsSetInReading", going_nowhere,
                      "a route set is travel, including this verdict's own trip")
        self.assertIn("trackerTravelStepLabel", going_nowhere,
                      "a tracker offering a travel step is not stuck")


class TheCounterCanActuallyAdvanceAndReset(unittest.TestCase):
    """A bound that cannot advance is indistinguishable from no bound.

    The same property `test_ammo_silenced_bound.py` asserts, applied to the two
    counters this change adds -- because #34's shape was a counter pinned at a
    constant, which mentions nothing forbidden and passes every test about what
    a definition may refer to.
    """

    def setUp(self):
        self.source = bot_elm()

    def test_the_stall_counter_only_resets_or_increments(self):
        results = branch_results(
            let_binding_body(update_memory_source(self.source),
                             "missionStalledReadings"))
        allowed = {"0", "1", "botMemoryBefore.missionStalledReadings",
                   "botMemoryBefore.missionStalledReadings + 1"}
        for result in results:
            self.assertIn(result, allowed,
                          "missionStalledReadings has a branch evaluating to "
                          + repr(result))
        self.assertIn("botMemoryBefore.missionStalledReadings + 1", results,
                      "the counter never increments, so the threshold can "
                      "never be reached")
        self.assertIn("0", results,
                      "the counter never resets, so it would climb across "
                      "unrelated missions")

    def test_the_attempt_clock_advances_every_reading_it_is_latched(self):
        latch = collapsed(let_binding_body(update_memory_source(self.source),
                                           "missionToAbandon"))
        self.assertIn("readingsSince = latched.readingsSince + 1", latch,
                      "the bound on the quit attempt can never be reached")
        self.assertIn("readingsSince = 0", latch,
                      "a fresh verdict must start its clock at zero")

    def test_the_verdict_is_latched_and_released_by_one_thing_only(self):
        latch = collapsed(let_binding_body(update_memory_source(self.source),
                                           "missionToAbandon"))
        # Released by the mission leaving the tracker, which is what quitting
        # it produces -- and by nothing else, or the bot would go back to
        # flying a mission it had already concluded was impossible.
        self.assertIn(
            "if trackerStillShowsMission context.readingFromGameClient "
            "latched.name then", latch,
            "the release condition must be exactly 'the mission is still in "
            "the tracker' -- anything conjoined to it is a second way to "
            "silently un-conclude the verdict and go back to flying a mission "
            "already judged impossible")
        self.assertEqual(
            latch.count("Nothing ->"), 1,
            "more than one way out of the latch is more than one thing that "
            "can silently un-conclude the verdict")


class TheQuitAttemptIsBounded(unittest.TestCase):
    """Quitting must not become the second forever-loop."""

    def setUp(self):
        self.source = bot_elm()
        self.body = collapsed(function_body(
            self.source,
            "abandonMissionThatCannotProgress : BotDecisionContext",
            "\nstationToReturnToForAbandonment :"))

    def test_the_bound_ends_the_session(self):
        self.assertIn("if abandonMissionGiveUpReadings <= verdict.readingsSince then",
                      self.body)
        deadline = self.body[self.body.index("abandonMissionGiveUpReadings <="):]
        self.assertIn("Common.DecisionPath.endDecisionPath FinishSession",
                      deadline.split("else")[0],
                      "reaching the bound must end the session, not hand the "
                      "problem back to the branch that could not solve it")

    def test_the_bound_is_larger_than_the_trip_it_has_to_cover(self):
        # The same route-set, travel, dock the pod recovery budgets for, plus
        # the station work. Smaller than that budget would be a deadline that
        # fires during a trip that was going to succeed.
        self.assertGreater(
            int(int_constant(self.source, "abandonMissionGiveUpReadings")),
            int(int_constant(self.source, "podRecoveryGiveUpReadings")))

    def test_no_branch_of_the_attempt_can_wait_without_the_clock_running(self):
        # `readingsSince` is advanced in the memory update on every reading the
        # verdict is latched, so every branch below is under the deadline --
        # including the ones that wait. What must not appear is a second,
        # unbounded escape hatch.
        self.assertNotIn("endDecisionPath ContinueSession", self.body)


class TheAbandonmentReusesWhatIsAlreadyThere(unittest.TestCase):
    """No second travel path, no second agent-conversation handler."""

    def setUp(self):
        self.source = bot_elm()
        self.body = function_body(
            self.source,
            "abandonMissionThatCannotProgress : BotDecisionContext",
            "\nstationToReturnToForAbandonment :")

    def test_travel_goes_through_the_one_shared_path(self):
        self.assertIn("travelToStationByName context", self.body)
        for second_path in ["routeToStationByName", "jumpToNextSystem",
                            "dockAtStation", "undockUsingStationWindow"]:
            self.assertNotIn(
                second_path, self.body,
                "the abandonment must not drive travel itself -- "
                "`travelToStationByName` is the one route-set, fly, dock path "
                "in this bot and #16 and #33 already share it")

    def test_the_drone_recall_is_not_duplicated(self):
        # `jumpToNextSystem` already wraps its cascade in `returnDronesToBay`,
        # so travelling here recalls drones through #7's own guard.
        self.assertNotIn("returnDronesToBay", self.body)
        self.assertIn("returnDronesToBay context",
                      collapsed(function_body(
                          self.source,
                          "jumpToNextSystem : BotDecisionContext",
                          "\n{-| Every reason this bot has to stop")))

    def test_the_conversation_is_opened_by_the_existing_helper(self):
        self.assertIn("openAgentConversation context", self.body)

    def test_the_quit_click_waits_a_reading_after_any_click(self):
        # The Accept/Quit Mission button rows overlap by three pixels, which is
        # how a stray second click once opened this very dialog by accident.
        quit_body = collapsed(function_body(
            self.source, "quitMissionInConversation :",
            "\n{-| Whether the confirmation dialog now on screen"))
        self.assertIn("previousStepClickedMouse context", quit_body)
        self.assertIn('"QuitMission_Button"', quit_body)


class TheConfirmationIsTheOnlyAffirmativeAnswer(unittest.TestCase):
    """`closeMessageBox` says No to everything else, and still does."""

    def setUp(self):
        self.source = bot_elm()

    def test_the_declining_path_has_no_affirmative_in_it(self):
        declining = collapsed(function_body(
            self.source,
            "closeMessageBoxByDeclining : EveOnline.ParseUserInterface.MessageBox",
            "\njumpToNextSystem :"))
        self.assertIn('namedButton "no_dialog_button"', declining)
        for affirmative in ["yes_dialog_button", "quitMissionConfirmationButton",
                            "confirmQuitMission"]:
            self.assertNotIn(
                affirmative, declining,
                "the default answer to a confirmation must stay the one that "
                "declines -- the 'Quit Mission?' dialog cost a mission's "
                "standing once already")

    def test_the_exception_needs_all_three_conditions(self):
        expected = collapsed(function_body(
            self.source,
            "quitMissionConfirmationIsExpected : BotDecisionContext",
            "\n\n\n-- Docked"))
        self.assertIn("context.memory.missionToAbandon /= Nothing", expected)
        self.assertIn("context.readingFromGameClient.agentConversationWindows /= []",
                      expected)
        self.assertIn("previousStepClickedMouse context", expected)

    def test_the_dialog_is_recognised_by_shape_not_by_wording(self):
        # `no_dialog_button` is the one button name this file already relies on
        # being stable across client languages. `yes_dialog_button` has never
        # been read out of a live tree here, so it is preferred and not
        # required: the affirmative is "the other button of a two-button
        # dialog that has a No".
        button = collapsed(function_body(
            self.source, "quitMissionConfirmationButton :",
            "\ncloseMessageBoxByDeclining :"))
        self.assertIn('buttonIsNamed "no_dialog_button"', button)
        self.assertIn("( [ _ ], [ theOtherOne ] ) ->", button)
        self.assertNotIn("mainText", button,
                         "matching the button's rendered text would make this "
                         "depend on the client's language")


class TheOperatorCanReadWhatHappened(unittest.TestCase):
    """A mission thrown away must never be thrown away silently."""

    def setUp(self):
        self.source = bot_elm()

    def test_every_decision_line_of_the_abandonment_names_the_mission(self):
        body = collapsed(function_body(
            self.source,
            "abandonMissionThatCannotProgress : BotDecisionContext",
            "\nstationToReturnToForAbandonment :"))
        # Each `describeBranch` in the response either names the mission itself
        # or is nested inside the one that does, which is the outermost.
        first = body.index("describeBranch")
        self.assertIn("verdict.name", body[first:body.index("(if abandon")])
        deadline = body[body.index("abandonMissionGiveUpReadings <="):]
        self.assertIn("verdict.name", deadline.split("else")[0],
                      "the give-up must say which mission is still stuck, or "
                      "the operator has nothing to quit by hand")

    def test_the_repeating_line_carries_no_reading_count(self):
        """The lesson the give-up alarm this responds to already learned.

        The abandonment's own line repeats for as long as the attempt lasts, so
        a counter in it makes every repeat a distinct line -- which defeats
        `stall_watch.py`'s dedupe and any log filter downstream. Run 126 emitted
        151 unique variants of one alarm that way. The counts belong in the
        status line, which nothing dedupes, and in the give-up, which prints on
        exactly one reading before the session ends.
        """
        body = collapsed(function_body(
            self.source,
            "abandonMissionThatCannotProgress : BotDecisionContext",
            "\nstationToReturnToForAbandonment :"))
        repeating = body[body.index("describeBranch"):body.index("(if abandon")]
        self.assertNotIn("String.fromInt", repeating)
        deadline = body[body.index("abandonMissionGiveUpReadings <="):]
        self.assertIn("String.fromInt verdict.readingsSince",
                      deadline.split("else")[0],
                      "the one line printed once may carry its numbers, and "
                      "should -- it is what says how long the attempt ran")

    def test_the_status_line_carries_it_for_the_rest_of_the_session(self):
        status = collapsed(function_body(self.source,
                                         "describeMissionAbandonment :",
                                         "\n{-| The home station"))
        self.assertIn('String.join ", " context.memory.missionNamesAbandoned',
                      status,
                      "the names themselves must be printed -- 'a mission was "
                      "abandoned' tells an operator nothing to act on")
        self.assertIn("ABANDONING", status)
        self.assertIn("describeMissionAbandonment context",
                      collapsed(function_body(
                          self.source, "statusTextFromState :",
                          "\n{-| What the gate branch can see")),
                      "the description exists but is never printed")


class TheSameMissionIsNotTakenStraightBack(unittest.TestCase):
    """What the operator did by hand: quit it, then decline it."""

    def setUp(self):
        self.source = bot_elm()

    def test_the_decline_consults_the_session_s_own_list(self):
        decline = collapsed(function_body(
            self.source, "shouldDeclineMission : BotDecisionContext",
            "\n\n\n-- A mission that cannot be progressed"))
        self.assertIn("context.eventContext.botSettings.missionNamesToDecline",
                      decline)
        self.assertIn("context.memory.missionNamesAbandoned", decline)
        self.assertIn("stringContainsIgnoringCase", decline)

    def test_the_name_is_recorded_stripped_of_its_counter(self):
        record = collapsed(record_field_body(update_memory_source(self.source),
                                             "missionNamesAbandoned"))
        self.assertIn("missionNameForDeclining justDecided.name", record)

    def test_it_is_recorded_once_when_the_verdict_latches(self):
        record = collapsed(record_field_body(update_memory_source(self.source),
                                             "missionNamesAbandoned"))
        self.assertIn("( Nothing, Just justDecided ) ->", record,
                      "recording on any reading the verdict is latched would "
                      "add the same name once per reading")


class TheOrderingIsThePoint(unittest.TestCase):
    """What still outranks an errand."""

    def setUp(self):
        self.source = bot_elm()
        start = self.source.index(
            "missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        self.collapsed = collapsed(self.source[start:end])

    def test_the_ship_loss_and_the_wind_down_outrank_it(self):
        # Both live in the pre-split list, and the abandonment does not: there
        # is no mission worth giving back if the ship is gone, and a session
        # that is ending should not start an errand.
        pre_split = self.collapsed[:self.collapsed.index(
            "branchDependingOnDockedOrInSpace")]
        self.assertIn("recoverPodAfterShipLoss context", pre_split)
        self.assertIn("windDownBeforeSessionEnd context", pre_split)
        self.assertNotIn("abandonMissionThatCannotProgress", pre_split)

    def test_the_retreat_outranks_it(self):
        retreat = self.collapsed.index("runAwayIfLowHealth context shipUI")
        abandon = self.collapsed.index(
            "abandonMissionThatCannotProgress context |> Maybe.withDefault "
            "(decideActionWhenInSpace")
        self.assertLess(retreat, abandon,
                        "a ship being taken apart is more urgent than an "
                        "errand back to the agent")

    def test_it_outranks_every_branch_that_would_fly_the_stuck_mission(self):
        for flown in ["decideActionWhenDocked context",
                      "decideActionWhenInSpace context"]:
            abandon = self.collapsed.index(
                "abandonMissionThatCannotProgress context |> Maybe.withDefault ("
                + flown)
            self.assertGreater(abandon, 0)


if __name__ == "__main__":
    unittest.main()
