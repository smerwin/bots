"""Tests for the mission runner leaving when the tracker's travel step is Dock.

Issue #46. Once the mission tracker's travel button reads "Dock" and the
objective carries no instruction, the mission is over and the only thing being
asked for is the trip home -- but `decideActionInMissionPocket` wrapped the whole
travel branch in `decideActionInCombat`, so travel was the fallback reached only
once combat had nothing left to offer, and combat has something to offer for as
long as anything on the grid is alive.

Measured from run 11's log. The tracker read

    Mission: Illegal Activity (3 of 3) -- no instruction (next step: Dock)

on 77 consecutive in-space readings; 386 of the 453 decision blocks inside them
went to locking and shooting; and the first in-space click on that Dock button
came 603 seconds -- just over ten minutes -- after the label appeared, on the
first reading where the overview finally held zero rats. Over the same 77
readings the client's combat log reported any incoming damage at all on 4 of
them, at most 7 hitpoints in a 45-second window against a threshold of 3500, so
this was not a fight the ship was in danger of losing. It was a field being
farmed after the bot had been told to go home.

**Two things are checked here, and the first is the one that matters.**

The label match is exact rather than a substring because *"Undock" contains
"dock"* -- the label the tracker shows at the start of every mission. A substring
rule would read the ship's own departure as "the objective is complete" and try
to disengage on the station ramp. That is checked by running the real
`Bot.elm` through `elm repl` rather than by restating the rule in Python, for the
reason PR #45 was verified that way: a mirrored rule only ever asserts what its
author thought the code did.

The travel labels it is checked against are the ones the client actually writes,
counted across the eleven recorded runs in `~/eve-bot-logs`. Ten distinct labels,
exactly one of which is the one this change acts on:

    9527  Warp to Location      1092  Set Destination        560  Abort Undock
    2737  Destination Set        777  Preparing               32  Read Details
    2679  Warping                752  Start Conversation
    1738  Dock                   710  Undock

The recordings also say the second half of the condition is load-bearing rather
than belt-and-braces: 326 of those 1738 "Dock" readings carry a live courier
instruction ("Bring <a ...>The Damsel</a> to ..."), so the label alone would
have disengaged on a mission whose objective was still asking for something.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; they skip if it is not there.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# Every travel label the eleven recorded runs contain, quoted from their
# `(next step: ...)` status lines. Exactly one of them ends a mission.
TRAVEL_LABEL_ENDS_THE_MISSION = "Dock"
TRAVEL_LABELS_SEEN = [
    "Abort Undock",
    "Destination Set",
    "Dock",
    "Preparing",
    "Read Details",
    "Set Destination",
    "Start Conversation",
    "Undock",
    "Warp to Location",
    "Warping",
]

# Objective wording taken verbatim from the same status lines. The first is what
# a finished mission prints; the rest are trackers still asking for something.
NO_INSTRUCTION = []
INSTRUCTIONS_SEEN = [
    ('Bring <a href="showinfo:11742">The Damsel</a> to '
     '<a href="showinfo:1373//3008916">Almananeg Erabone</a>'),
    "You need to activate the Acceleration Gate",
    ('You need to travel to <a href="showinfo:5//30005038">Kor-Azor Prime</a> '
     '<color=#ff3a9aeb>0.9</color>'),
]


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def elm_list_of_strings(values):
    return "[ " + ", ".join(elm_string(value) for value in values) + " ]" \
        if values else "[]"


class ElmRepl:
    """The bot's own compiled code, answering for itself.

    The recipe is `botlab_host.py`'s: copy the app to scratch, patch
    `elm-version` to whatever this machine's elm reports, and build there --
    never in the checked-in source. The one extra step is opening
    `module Bot exposing (...)` to `(..)`, since the repl can only call what the
    module exports and the bot exports `botMain` alone.
    """

    def __init__(self):
        self.scratch = tempfile.mkdtemp(prefix="test-dock-outranks-")
        self.app = os.path.join(self.scratch, "app")
        shutil.copytree(MISSION_RUNNER_DIR, self.app)

        version = subprocess.run(
            ["elm", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
        elm_json = os.path.join(self.app, "elm.json")
        with open(elm_json, encoding="utf-8") as source:
            patched = source.read().replace(
                '"elm-version": "0.19.1"', '"elm-version": "%s"' % version)
        with open(elm_json, "w", encoding="utf-8") as target:
            target.write(patched)

        bot = os.path.join(self.app, "Bot.elm")
        with open(bot, encoding="utf-8") as handle:
            source = handle.read()
        opened = re.sub(r"module Bot exposing\s*\([^)]*\)",
                        "module Bot exposing (..)", source, count=1)
        assert opened != source, "could not open Bot.elm's exports"
        with open(bot, "w", encoding="utf-8") as handle:
            handle.write(opened)

    def evaluate(self, expressions):
        """Answers, one per expression, in order."""
        script = "import Bot exposing (..)\n" + "".join(
            expression + "\n" for expression in expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = re.findall(r"(True|False) : Bool", plain)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, result.stderr))
        return [answer == "True" for answer in answers]

    def close(self):
        shutil.rmtree(self.scratch, ignore_errors=True)


def elm_is_available():
    return shutil.which("elm") is not None


@unittest.skipUnless(elm_is_available(), "elm is not on PATH")
class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """Both halves of the condition, run for real against the recorded strings."""

    @classmethod
    def setUpClass(cls):
        cls.repl = ElmRepl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_exactly_one_recorded_travel_label_ends_the_mission(self):
        answers = self.repl.evaluate(
            ["missionTravelStepIsDock " + elm_string(label)
             for label in TRAVEL_LABELS_SEEN])
        matched = [label for label, yes in zip(TRAVEL_LABELS_SEEN, answers) if yes]
        self.assertEqual(matched, [TRAVEL_LABEL_ENDS_THE_MISSION])

    def test_undock_is_not_dock(self):
        # The whole reason the match is exact. "Undock" is what the tracker
        # shows at the start of every mission, and a substring rule would read
        # it as "the objective is finished" while the ship is still in station.
        undock, abort, dock = self.repl.evaluate([
            'missionTravelStepIsDock "Undock"',
            'missionTravelStepIsDock "Abort Undock"',
            'missionTravelStepIsDock "Dock"',
        ])
        self.assertFalse(undock)
        self.assertFalse(abort)
        self.assertTrue(dock)

    def test_the_client_s_spacing_and_case_do_not_decide_it(self):
        answers = self.repl.evaluate([
            'missionTravelStepIsDock " Dock "',
            'missionTravelStepIsDock "dock"',
            'missionTravelStepIsDock "DOCK"',
            'missionTravelStepIsDock ""',
        ])
        self.assertEqual(answers, [True, True, True, False])

    def test_an_objective_that_still_says_something_is_not_finished(self):
        expressions = ["missionHasNoOutstandingInstruction "
                       + elm_list_of_strings(NO_INSTRUCTION)]
        expressions += ['missionHasNoOutstandingInstruction '
                        + elm_list_of_strings([instruction])
                        for instruction in INSTRUCTIONS_SEEN]
        answers = self.repl.evaluate(expressions)
        self.assertTrue(answers[0], "an empty objective list is finished")
        self.assertEqual(answers[1:], [False] * len(INSTRUCTIONS_SEEN))

    def test_a_blank_label_is_not_an_instruction(self):
        # The client renders empty labels; "no instruction" is what the status
        # line prints for them, and treating one as work outstanding would keep
        # the bot fighting for a mission that had finished.
        answers = self.repl.evaluate([
            'missionHasNoOutstandingInstruction [ "" ]',
            'missionHasNoOutstandingInstruction [ "   " ]',
            'missionHasNoOutstandingInstruction [ "", "You need to '
            'activate the Acceleration Gate" ]',
        ])
        self.assertEqual(answers, [True, True, False])


class TheRecordedRunsStillSayWhatTheseTestsAssume(unittest.TestCase):
    """The labels above are the client's, not this repo's.

    If the client starts writing a different travel label -- or an eleventh one
    -- these tests are asserting against a vocabulary that no longer exists, and
    the failure that would produce (a bot that never disengages, or one that
    disengages on the wrong step) is silent. So the list is checked against the
    recordings whenever they are on the machine.
    """

    def status_lines(self):
        paths = sorted(glob.glob(os.path.expanduser(
            "~/eve-bot-logs/mission_run*.log")))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        labels = set()
        dock_with_instruction = 0
        dock_without_instruction = 0
        pattern = re.compile(
            r"^# \[\d+\.\d+\] \([\d.]+s\) Mission: (?P<name>.*) -- "
            r"(?P<instruction>.*) \(next step: (?P<label>[^)]*)\)\s*$")
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    match = pattern.match(line)
                    if not match:
                        continue
                    labels.add(match.group("label"))
                    if match.group("label") != TRAVEL_LABEL_ENDS_THE_MISSION:
                        continue
                    if match.group("instruction") == "no instruction":
                        dock_without_instruction += 1
                    else:
                        dock_with_instruction += 1
        return labels, dock_without_instruction, dock_with_instruction

    def test_no_travel_label_has_appeared_that_these_tests_do_not_know(self):
        labels, _, _ = self.status_lines()
        self.assertTrue(labels, "the recordings carry no travel labels at all")
        self.assertEqual(sorted(labels & set(TRAVEL_LABELS_SEEN)), sorted(labels))

    def test_dock_really_does_appear_with_the_objective_finished(self):
        # The state this change acts on has to be one the bot actually reaches,
        # or the branch is the kind of guard that compiles and never fires.
        _, without, _ = self.status_lines()
        self.assertGreater(without, 0)

    def test_and_also_appears_with_an_objective_outstanding(self):
        # Which is why the label alone is not the condition: a courier delivery
        # docks too, and its objective is still asking for something.
        _, _, with_instruction = self.status_lines()
        self.assertGreater(with_instruction, 0)


class TheOrderingIsThePoint(unittest.TestCase):
    """Dock has to win over "something is still alive", and nothing else may move."""

    def setUp(self):
        self.source = bot_source()

    def branch(self, name, following):
        start = self.source.index(name + " context")
        return self.source[start:self.source.index(following, start)]

    def test_the_dock_step_is_decided_before_the_fight(self):
        start = self.source.index("decideActionInMissionPocket context seeUndockingComplete =")
        end = self.source.index("\ndockOutranksTheFight :", start)
        body = self.source[start:end]
        override = body.index("dockOutranksTheFight context")
        combat = body.index("decideActionInCombat context seeUndockingComplete")
        self.assertLess(override, combat,
                        "the fight must be the fallback, not the wrapper")

    def test_the_retreat_still_outranks_it(self):
        # #32's damage-rate retreat is the "leave now, this is going badly"
        # controller and runs before `decideActionWhenInSpace` is called at all,
        # so this change cannot get in front of it. Inverting that leaves
        # everything compiling, which is issue #12's failure.
        start = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        body = self.source[start:end]
        self.assertIn("runAwayIfLowHealth context shipUI\n"
                      "                            |> Maybe.withDefault "
                      "(decideActionWhenInSpace context", body)

    def test_the_ship_loss_verdict_still_outranks_everything(self):
        # PR #37 pinned this and it is not this change's to move: the pre-split
        # list is untouched, and nothing about docking appears in it.
        start = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        body = self.source[start:end]
        pod = body.index(", recoverPodAfterShipLoss context")
        split = body.index("branchDependingOnDockedOrInSpace")
        self.assertLess(pod, split)
        self.assertNotIn("dockOutranksTheFight", body)

    def test_the_override_is_reached_from_the_mission_pocket_and_nowhere_else(self):
        callers = [line for line in self.source.split("\n")
                   if "dockOutranksTheFight" in line
                   and not line.startswith("dockOutranksTheFight")]
        # Its own type annotation, the doc reference in
        # `decideActionInMissionPocket`, and the single call.
        self.assertEqual(
            [line.strip() for line in callers if line.startswith("    dock")],
            ["dockOutranksTheFight context"])


class WhatStillKeepsTheGunsFiring(unittest.TestCase):
    """The exceptions are the reviewable part of a change that stops a fight."""

    def setUp(self):
        self.source = bot_source()
        start = self.source.index("dockOutranksTheFight context ifTheFightIsStillOurs =")
        self.branch = self.source[start:self.source.index(
            "\ntravelStepThatEndsTheFight :", start)]

    def test_a_scrambler_hands_the_fight_back(self):
        # Docking is a warp. Something warp disrupting the ship makes leaving
        # impossible, so the only thing that restores the option is killing it.
        self.assertIn("scramblerHoldingTheShipHere context", self.branch)
        held = self.branch.index("Just holdingUs ->")
        free = self.branch.index("Nothing ->", held)
        self.assertIn("ifTheFightIsStillOurs", self.branch[held:free])

    def test_the_decline_names_itself_in_the_decision_log(self):
        # A branch that hands the fight back has to be visible doing it, or the
        # log reads as though this change never fired -- `returnDronesToBay`'s
        # lesson, where a silent decline disabled drone recall for a session.
        held = self.branch.index("Just holdingUs ->")
        free = self.branch.index("Nothing ->", held)
        self.assertIn("describeBranch", self.branch[held:free])
        self.assertIn("warp disrupting", self.branch[held:free])

    def test_leaving_says_so_in_the_decision_log(self):
        # An operator must be able to see that the bot stopped fighting because
        # the tracker said Dock, rather than appearing to lose interest.
        self.assertIn("The objective is complete and the mission tracker says",
                      self.branch)

    def test_both_halves_of_the_condition_are_required(self):
        start = self.source.index("travelStepThatEndsTheFight context =")
        body = self.source[start:self.source.index(
            "\nmissionTravelStepIsDock :", start)]
        self.assertIn("missionHasNoOutstandingInstruction", body)
        self.assertIn("missionTravelStepIsDock", body)

    def test_the_label_is_compared_whole(self):
        # Read out of the source rather than restated: a matcher that drifts
        # into `String.contains` still compiles, still passes every other test,
        # and disengages on "Undock".
        start = self.source.index("missionTravelStepIsDock label =")
        body = self.source[start:self.source.index("\n\n", start)]
        self.assertIn('== "dock"', body)
        self.assertNotIn("stringContainsIgnoringCase", body)
        self.assertNotIn("String.contains", body)


class TheLeavingIsTheExistingLeaving(unittest.TestCase):
    """No second drone recall, and no second clock."""

    def setUp(self):
        self.source = bot_source()
        start = self.source.index("dockOutranksTheFight context ifTheFightIsStillOurs =")
        self.branch = self.source[start:self.source.index(
            "\ntravelStepThatEndsTheFight :", start)]

    def test_the_drones_come_home_through_the_gate_every_warp_uses(self):
        # Issue #7 lost ten drones by warping with them out, and the recall that
        # followed routes every warp, dock, retreat and gate activation. This
        # branch must go through it rather than beside it.
        self.assertIn(
            "ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context",
            self.branch)

    def test_there_is_no_second_drone_give_up(self):
        self.assertNotIn("droneRecall", self.branch)
        self.assertNotIn("dronesInSpace", self.branch)

    def test_the_branch_owns_no_counter_and_no_memory(self):
        # Every condition is re-derived from the live reading, so the branch
        # clears itself the moment the tracker stops saying Dock. A counter here
        # would be a second "leave now" controller beside #32's retreat, and
        # would need the give-up rules that go with one.
        self.assertNotIn("context.memory", self.branch)
        self.assertNotIn("Ticks", self.branch)

    def test_the_click_goes_through_the_shared_travel_button_step(self):
        # Which is what keeps the "I clicked on the previous step" settling
        # window: the tracker's button changes what it says once pressed.
        self.assertIn("clickMissionTravelButton context label buttonNode",
                      self.branch)


if __name__ == "__main__":
    unittest.main()
