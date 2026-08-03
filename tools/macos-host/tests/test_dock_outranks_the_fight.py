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
counted across the twelve recorded runs in `~/eve-bot-logs`. Ten of them are
text, and exactly one of those is the one this change acts on:

    9634  Warp to Location      1136  Set Destination        638  Abort Undock
    2882  Destination Set        932  Undock                  53  Read Details
    3070  Warping                908  Preparing
    1929  Dock                   842  Start Conversation

The recordings also say the second half of the condition is load-bearing rather
than belt-and-braces: 326 of those "Dock" readings carry a live courier
instruction ("Bring <a ...>The Damsel</a> to ..."), so the label alone would
have disengaged on a mission whose objective was still asking for something.

**And an eleventh label exists that is not text at all.** Run 11 rendered a
travel step three times as

    U+0002 U+0000 U+AD1D8 U+0001 U+0001 U+0000 U+0001

-- six C0 control characters around one **unassigned** codepoint (category `Cn`,
plane 10). Not the private-use area, which matters: a test that classified
non-text by PUA membership would call this text and fail. It appeared on
`Recon (3 of 3) -- You need to warp to the mission location`, and the bot pressed
the button carrying it, which is the pre-existing travel behaviour and not
something this change alters.

The rule fails closed on it, checked by execution rather than by inspection:
`missionTravelStepIsDock` answers `False` for that string, and so does
`missionHasNoOutstandingInstruction` for the objective it appeared beside, so
*both* halves of the condition independently decline. That is why the first
class below asserts over the *printable* labels and the non-text one is its own
case: an eleventh **text** label is drift worth failing on, while a glyph with no
text is now a covered case rather than a broken test.

Nothing here reads a live game client or drives a bot, and nothing here depends
on a run being finished -- a log still being appended to is read line by line and
its final partial line skipped. The `elm repl` cases need `elm` on PATH and the
app's dependencies already fetched, which is what `compile_bot.sh` leaves behind;
they skip if the repl cannot be run at all.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# Every *text* travel label the recorded runs contain, quoted from their
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
    # The next four appear only from run 17 onward, and only because #62 taught
    # the parser to read the *objective-chain* mission panel -- a layout whose
    # travel steps are per-task widgets rather than one relabelled button. The
    # vocabulary was always being written; nothing could see it. That is what
    # this assertion is for, and it fired the first time the client wrote
    # something new, exactly as intended.
    #
    # Two of them are the argument for the exact match in one line: "Docking"
    # and "Undocking" both contain "dock", and a substring rule would read
    # either as the end of the mission -- one of them while the ship is still
    # leaving the station.
    "Docking",
    "Jump",
    # Trailing space is the client's, not a typo here.
    "Jumping ",
    "Undocking",
]

# The eleventh, from run 11: a travel step the client rendered as a glyph with
# no text. Held as codepoints rather than as a literal so this file stays
# readable and so an editor cannot silently normalise it away.
NON_TEXT_TRAVEL_LABEL_CODEPOINTS = [0x02, 0x00, 0xAD1D8, 0x01, 0x01, 0x00, 0x01]

# The objective the tracker was carrying on the readings it appeared -- quoted
# because it is the second half of the condition, and it declines too.
OBJECTIVE_BESIDE_THE_NON_TEXT_LABEL = "You need to warp to the mission location"

# Categories no rendered label is made of: control, format, surrogate,
# private-use and unassigned. Deliberately wider than "is it in the PUA" --
# U+AD1D8 above is unassigned, not private-use, so a PUA test would call it text.
NON_TEXT_CATEGORIES = frozenset(["Cc", "Cf", "Cs", "Co", "Cn"])


def looks_like_text(label):
    """Whether a label is something the client meant a person to read."""
    return bool(label) and all(
        unicodedata.category(character) not in NON_TEXT_CATEGORIES
        for character in label)

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


def elm_string_from_codepoints(codepoints):
    """A string literal cannot carry a NUL or a lone unassigned codepoint.

    `Char.fromCode` can, so the label is rebuilt inside Elm from the numbers the
    log actually holds -- no escaping, and nothing lost in transit.
    """
    return "String.fromList (List.map Char.fromCode [ %s ])" % ", ".join(
        str(codepoint) for codepoint in codepoints)


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
        answers, plain, stderr = self.ask(expressions)
        if len(answers) != len(expressions):
            raise AssertionError(
                "elm repl answered %d of %d expressions.\nstdout:\n%s\nstderr:\n%s"
                % (len(answers), len(expressions), plain, stderr))
        return answers

    def ask(self, expressions):
        script = "import Bot exposing (..)\n" + "".join(
            expression + "\n" for expression in expressions)
        result = subprocess.run(["elm", "repl"], cwd=self.app, input=script,
                                capture_output=True, text=True)
        plain = re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)
        answers = [answer == "True"
                   for answer in re.findall(r"(True|False) : Bool", plain)]
        return answers, plain, result.stderr

    def works(self):
        """Whether the repl can evaluate anything at all here.

        Distinguishes an environment where `elm repl` cannot run -- no cached
        dependencies, no writable ELM_HOME -- from the bot answering wrongly.
        Only the first is a reason to skip: a suite that skipped on any failure
        would be a check that never fires, which is this repo's own failure mode.
        """
        answers, plain, stderr = self.ask(['missionTravelStepIsDock "Dock"'])
        return answers == [True], plain + "\n" + stderr

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
        usable, output = cls.repl.works()
        if not usable:
            cls.repl.close()
            raise unittest.SkipTest(
                "elm repl cannot evaluate here, so the rules are unchecked "
                "by execution in this environment:\n" + output)

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

    def test_a_travel_label_that_is_not_text_fails_closed(self):
        """Run 11's eleventh label: a glyph where a word should be.

        Both halves of the condition are asked, because both have to decline on
        their own -- the label is not "Dock", and the objective it appeared
        beside was still asking for something. Neither leans on the other.
        """
        label = elm_string_from_codepoints(NON_TEXT_TRAVEL_LABEL_CODEPOINTS)
        matches_dock, objective_is_finished, control = self.repl.evaluate([
            "missionTravelStepIsDock (%s)" % label,
            "missionHasNoOutstandingInstruction "
            + elm_list_of_strings([OBJECTIVE_BESIDE_THE_NON_TEXT_LABEL]),
            'missionTravelStepIsDock "Dock"',
        ])
        self.assertFalse(matches_dock,
                         "a label with no text must never end a mission")
        self.assertFalse(objective_is_finished)
        self.assertTrue(control, "the control case still matches, so the repl "
                                 "is answering rather than failing everything")

    def test_control_characters_alone_do_not_match(self):
        # The recorded label is mostly C0 controls, and `String.trim` removes
        # some of them -- so a rule that trimmed its way to an empty string and
        # then compared loosely could still go wrong. It does not.
        answers = self.repl.evaluate([
            "missionTravelStepIsDock (%s)" % elm_string_from_codepoints([0x02]),
            "missionTravelStepIsDock (%s)" % elm_string_from_codepoints([0x00]),
            "missionTravelStepIsDock (%s)"
            % elm_string_from_codepoints([0x01, 0x01, 0x00]),
        ])
        self.assertEqual(answers, [False, False, False])

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

    If the client starts writing a different travel label these tests are
    asserting against a vocabulary that no longer exists, and the failure that
    would produce -- a bot that never disengages, or one that disengages on the
    wrong step -- is silent. So the list is checked against the recordings
    whenever they are on the machine.

    **What is asserted is the set of *text* labels.** A label with no text is
    not drift, it is a case with its own test above, and failing here on one
    would make this suite depend on which runs happen to be on disk. Run 11
    produced one and it appeared only in the part of the log written after the
    change was first measured -- so this failed on someone else's machine, once,
    for a client behaviour that was real and harmless.

    Reading a log that is still being written is fine: lines are read one at a
    time and a trailing partial line has no newline, so it is skipped rather
    than half-matched.
    """

    STATUS_LINE = re.compile(
        r"^# \[\d+\.\d+\] \([\d.]+s\) Mission: (?P<name>.*) -- "
        r"(?P<instruction>.*) \(next step: (?P<label>[^)]*)\)\n$")

    def recorded_labels(self):
        paths = sorted(glob.glob(os.path.expanduser(
            "~/eve-bot-logs/mission_run*.log")))
        if not paths:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        labels = set()
        dock_with_instruction = 0
        dock_without_instruction = 0
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    if not line.endswith("\n"):
                        # The last line of a run still in progress.
                        continue
                    match = self.STATUS_LINE.match(line)
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

    def test_no_text_travel_label_has_appeared_that_these_tests_do_not_know(self):
        labels, _, _ = self.recorded_labels()
        self.assertTrue(labels, "the recordings carry no travel labels at all")
        text_labels = sorted(label for label in labels if looks_like_text(label))
        self.assertTrue(text_labels, "the recordings carry no readable labels")
        self.assertEqual(
            sorted(set(text_labels) - set(TRAVEL_LABELS_SEEN)), [],
            "the client is writing a travel label these tests do not know")

    def test_a_label_that_is_not_text_is_a_known_case_and_not_a_failure(self):
        # Whatever the client renders as a glyph, the rule declines it -- see
        # the executed test above. All this asserts is that such a label is
        # classified as non-text, so it never reaches the drift check.
        labels, _, _ = self.recorded_labels()
        for label in labels:
            if looks_like_text(label):
                continue
            self.assertNotIn(TRAVEL_LABEL_ENDS_THE_MISSION, label)
            self.assertNotEqual(label.strip().lower(), "dock")

    def test_dock_really_does_appear_with_the_objective_finished(self):
        # The state this change acts on has to be one the bot actually reaches,
        # or the branch is the kind of guard that compiles and never fires.
        _, without, _ = self.recorded_labels()
        self.assertGreater(without, 0)

    def test_and_also_appears_with_an_objective_outstanding(self):
        # Which is why the label alone is not the condition: a courier delivery
        # docks too, and its objective is still asking for something.
        _, _, with_instruction = self.recorded_labels()
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
        # Located by tokens, not by line: elm-format wraps this application as
        # `(decideActionInCombat context` / `seeUndockingComplete`, so a literal
        # one-line match finds nothing. The ordering is what this pins, and the
        # ordering is unaffected by where the formatter breaks the line.
        combat = re.search(
            r"decideActionInCombat\s+context\s+seeUndockingComplete", body
        ).start()
        self.assertLess(override, combat,
                        "the fight must be the fallback, not the wrapper")

    def test_the_retreat_still_outranks_it(self):
        # #32's damage-rate retreat is the "leave now, this is going badly"
        # controller and runs before `decideActionWhenInSpace` is called at all,
        # so this change cannot get in front of it. Inverting that leaves
        # everything compiling, which is issue #12's failure.
        #
        # Asserted on the collapsed text rather than on exact indentation:
        # #54's mission abandonment now sits between the two, as a second
        # fallback of the same retreat, and the property being pinned here is
        # the ordering rather than what happens to be nested in between.
        start = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        collapsed = " ".join(self.source[start:end].split())
        self.assertIn("runAwayIfLowHealth context shipUI |> Maybe.withDefault",
                      collapsed)
        self.assertLess(collapsed.index("runAwayIfLowHealth context shipUI"),
                        collapsed.index("decideActionWhenInSpace context"),
                        "the retreat must be consulted before the in-space "
                        "decision, not the other way round")

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
