"""Tests for the mission runner leaving once the objective is done and the
tracker offers a travel step.

Issues #46 and #92. #46's fix stopped the fight when the tracker's travel button
read exactly "Dock" and the objective carried no instruction. #92 is that fix
measured: "Dock" is the *rarest* label there is. Counted over every recorded run
on the readings that cost something -- in space, objective complete, rats on the
overview:

    Set Destination    1,443   avg 7.0 rats      Dock          35   avg 1.8
    Destination Set      812   avg 3.0           Preparing     15   avg 2.0
    Start Conversation    71   avg 1.7           Warping        3   avg 2.0

So the label the first fix handled is 35 readings and the ones it did not are
2,344, on grids carrying up to four times the rats. The rule is now the
objective and the *existence* of a travel step rather than which word the button
carries, and three things are checked here.

(Those counts are what the corpus said while this was written, and it grows: a
run was still being appended to. The cases below assert the *relations* the
change rests on -- these labels dwarf `Dock`, the grids are busy ones -- rather
than the numbers, so a growing corpus cannot make them wrong.)

**The failure direction, which is the part that changed.** An equality test
against "Dock" declined a label with no text by accident; "any travel step"
would match one. Two such labels are in the corpus:

    U+0002 U+0000 U+AD1D8 U+0001 U+0001 U+0000 U+0001     run 11
    U+0000 U+0000 . 5 0 <space> A U U+0000                run 22

The first is six C0 controls around an **unassigned** codepoint (category `Cn`,
plane 10 -- not private-use, which is the trap: a rule recognising "not text" by
PUA membership would call it text). It arrived beside an objective that was
still asking for something, so the objective half declined it too. **The second
did not.** Run 22 rendered it on `Avenge a Fallen Comrade -- no instruction`, so
on that reading the objective half says "finished" and the label is the only
thing standing between the bot and disengaging on a button the client failed to
draw. `travelLabelIsReadableText` is what declines it, and this file executes
that rule against both.

**Which labels the widened rule covers**, which is a fact about the corpus
rather than about a list in the source: `Warp to Location` -- the label that
means the mission is still running, and the one whose admission would disengage
inside an uncleared pocket -- appears 10,032 times beside a live objective,
three times beside a finished one (a flicker between two `Dock` readings as a
mission ended), and **never once** on a grid with a rat on it. So the objective
half excludes it where it matters, on the evidence. That is asserted here,
because it is the property that makes "any step" safe rather than merely
convenient.

**That nothing new is done to leave.** The step handed back is the same value
the fight itself falls through to, so the drone recall, the click's settling
window and the acceleration gate's precedence over a route all still apply.

Nothing here reads a live game client or drives a bot, and nothing here depends
on a run being finished -- a log still being appended to is read line by line and
its final partial line skipped. The `elm repl` cases need `elm` on PATH and the
app's dependencies already fetched, which is what `compile_bot.sh` leaves behind;
without it they **fail** rather than skipping, for the reason `prerequisites.py`
gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unicodedata
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# Every *text* travel label the recorded runs contain, quoted from their
# `(next step: ...)` status lines.
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
    # something new, exactly as intended -- and it is half the argument against
    # a list of permitted words: the list would have needed four more entries
    # and nobody would have known.
    "Docking",
    "Jump",
    # Trailing space is the client's, not a typo here.
    "Jumping ",
    "Undocking",
]

# The label that always means the mission is still running, and the one the
# widened rule must never act on. It is excluded by the *objective* half, on
# evidence -- see `TheRecordedRunsSayWhichLabelsThisCovers`.
TRAVEL_LABEL_THAT_NEVER_ENDS_A_MISSION = "Warp to Location"

# The two labels the first fix missed, which are the whole of issue #92.
TRAVEL_LABELS_THE_DOCK_RULE_MISSED = ["Set Destination", "Destination Set"]

# The labels that are not text at all, held as codepoints rather than as
# literals so this file stays readable and so an editor cannot silently
# normalise them away.
#
# The first is run 11's, beside an objective still asking for something. The
# second is run 22's, beside a *finished* one -- which is why the label rule has
# to decline it on its own.
NON_TEXT_TRAVEL_LABELS = {
    "run 11's glyph": [0x02, 0x00, 0xAD1D8, 0x01, 0x01, 0x00, 0x01],
    "run 22's NUL-wrapped distance": [
        0x00, 0x00, 0x2E, 0x35, 0x30, 0x20, 0x41, 0x55, 0x00],
}

# The objectives the tracker was carrying beside each of them.
OBJECTIVE_BESIDE_RUN_11_GLYPH = "You need to warp to the mission location"
OBJECTIVE_BESIDE_RUN_22_LABEL = ""

# Categories no rendered label is made of: control, format, surrogate,
# private-use and unassigned. Deliberately wider than "is it in the PUA" --
# U+AD1D8 above is unassigned, not private-use, so a PUA test would call it
# text. This is the *test's* classifier; the bot's own rule is narrower still
# (printable ASCII with a letter in it), and the point of running them against
# the same corpus is that they have to agree about every label the client wrote.
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


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this, and the
    expected strings are written the same way.
    """
    return " ".join(text.split())


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


def recorded_status_lines(test_case):
    """Every `(next step: ...)` status line the recordings hold, parsed.

    Reading a log that is still being written is fine: lines are read one at a
    time and a trailing partial line has no newline, so it is skipped rather
    than half-matched.
    """
    paths = sorted(glob.glob(os.path.expanduser(
        "~/eve-bot-logs/mission_run*.log")))
    if not paths:
        test_case.skipTest("no recorded runs in ~/eve-bot-logs")
    pattern = re.compile(
        r"^# \[\d+\.\d+\] \([\d.]+s\) Mission: (?P<name>.*) -- "
        r"(?P<instruction>.*) \(next step: (?P<label>[^)]*)\)\n$")
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as log:
            for line in log:
                if not line.endswith("\n"):
                    # The last line of a run still in progress.
                    continue
                match = pattern.match(line)
                if match:
                    yield match


def recorded_travel_labels(test_case):
    return {match.group("label") for match in recorded_status_lines(test_case)}


def costly_readings(test_case):
    """Per label: readings and total rats, for the state this change is about.

    In space, objective complete, rats on the overview. The unit is the
    **reading**, for `stall_watch.py`'s reason -- the bot re-derives its whole
    decision path several times per look at the game, so counting decision
    lines counts one state a dozen times.
    """
    paths = sorted(glob.glob(os.path.expanduser(
        "~/eve-bot-logs/mission_run*.log")))
    if not paths:
        test_case.skipTest("no recorded runs in ~/eve-bot-logs")
    head = re.compile(
        r"^# \[\d+\.\d+\] \([\d.]+s\) Mission: .* -- "
        r"(?P<instruction>.*) \(next step: (?P<label>[^)]*)\)$")
    rats_line = re.compile(r"^rats (\d+)")
    readings = {}
    rats_total = {}
    in_warp = {}
    for path in paths:
        reading = None
        with open(path, encoding="utf-8", errors="replace") as log:
            for raw in log:
                if not raw.endswith("\n"):
                    continue
                line = raw.rstrip("\n")
                if line.startswith("# ["):
                    if reading and reading["rats"] and not reading["docked"]:
                        label = reading["label"]
                        readings[label] = readings.get(label, 0) + 1
                        rats_total[label] = (rats_total.get(label, 0)
                                             + reading["rats"])
                        in_warp[label] = (in_warp.get(label, 0)
                                          + reading["warping"])
                    match = head.match(line)
                    reading = None
                    if match and match.group("instruction") == "no instruction":
                        reading = {"label": match.group("label"), "rats": 0,
                                   "docked": False, "warping": 0}
                    continue
                if reading is None:
                    continue
                counted = rats_line.match(line)
                if counted:
                    reading["rats"] = int(counted.group(1))
                if "I see no ship UI, assume we are docked" in line:
                    reading["docked"] = True
                if line.startswith("+ I am in warp"):
                    reading["warping"] = 1
    return readings, rats_total, in_warp


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """The rules are run for real against the strings the client wrote."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-travel-outranks-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_recorded_text_label_reads_as_a_step(self):
        # The widened rule acts on the *existence* of a step, so every label
        # the client has ever written as words has to pass. One that did not
        # would be a mission the bot keeps fighting after it is over, which is
        # the whole of #92.
        answers = self.repl.evaluate(
            ["travelLabelIsReadableText " + elm_string(label)
             for label in TRAVEL_LABELS_SEEN])
        refused = [label for label, yes in zip(TRAVEL_LABELS_SEEN, answers)
                   if not yes]
        self.assertEqual(refused, [])

    def test_a_travel_label_that_is_not_text_fails_closed(self):
        """The deliberate half of #92: an unreadable label is not a step.

        Both recorded ones are asked, because they fail for different reasons
        and only one of them is also declined by the objective. `Dock` rides
        along as a control, so a repl that has stopped answering cannot pass
        this by refusing everything.
        """
        names = sorted(NON_TEXT_TRAVEL_LABELS)
        answers = self.repl.evaluate(
            ["travelLabelIsReadableText (%s)"
             % elm_string_from_codepoints(NON_TEXT_TRAVEL_LABELS[name])
             for name in names]
            + ['travelLabelIsReadableText "Dock"'])
        for name, answer in zip(names, answers):
            self.assertFalse(
                answer, "%s must never be read as a travel step" % name)
        self.assertTrue(answers[-1], "the control case still matches, so the "
                                     "repl is answering rather than failing "
                                     "everything")

    def test_the_objective_does_not_decline_run_22_s_label(self):
        # Which is why the label rule carries this on its own. Run 11's glyph
        # arrived beside an objective still asking for something, so *both*
        # halves declined it and the fail-closed behaviour was free. Run 22's
        # arrived on a finished objective, and there the label is all there is.
        beside_run_11, beside_run_22 = self.repl.evaluate([
            "missionHasNoOutstandingInstruction "
            + elm_list_of_strings([OBJECTIVE_BESIDE_RUN_11_GLYPH]),
            "missionHasNoOutstandingInstruction "
            + elm_list_of_strings([OBJECTIVE_BESIDE_RUN_22_LABEL]),
        ])
        self.assertFalse(beside_run_11)
        self.assertTrue(beside_run_22,
                        "run 22's non-text label sits on a finished objective")

    def test_the_client_s_spacing_and_case_do_not_decide_it(self):
        answers = self.repl.evaluate([
            'travelLabelIsReadableText " Dock "',
            'travelLabelIsReadableText "dock"',
            'travelLabelIsReadableText "DOCK"',
            'travelLabelIsReadableText "Jumping "',
            'travelLabelIsReadableText ""',
            'travelLabelIsReadableText "   "',
        ])
        self.assertEqual(answers, [True, True, True, True, False, False])

    def test_control_characters_and_punctuation_alone_are_not_a_label(self):
        # The recorded labels are mostly C0 controls, and `String.trim` removes
        # some of them -- so a rule that trimmed its way to something short and
        # then accepted whatever was left could still go wrong. And a label of
        # digits and punctuation with no letter in it is a readout the client
        # leaked into the button, not a step: that is run 22's, with its NULs
        # stripped.
        answers = self.repl.evaluate([
            "travelLabelIsReadableText (%s)"
            % elm_string_from_codepoints([0x02]),
            "travelLabelIsReadableText (%s)"
            % elm_string_from_codepoints([0x00]),
            "travelLabelIsReadableText (%s)"
            % elm_string_from_codepoints([0x01, 0x01, 0x00]),
            'travelLabelIsReadableText ".50"',
            'travelLabelIsReadableText "---"',
        ])
        self.assertEqual(answers, [False] * 5)

    def test_a_non_ascii_label_is_declined_rather_than_guessed_at(self):
        # The stated cost of the rule: a client writing this button in another
        # script switches the branch off rather than disengaging on a word
        # nothing here has ever read. Failing towards "keep fighting" is the
        # behaviour the bot had before the change.
        answers = self.repl.evaluate([
            'travelLabelIsReadableText "Andocken"',
            "travelLabelIsReadableText (%s)"
            % elm_string_from_codepoints([0x421, 0x442, 0x44B, 0x43A]),
        ])
        self.assertEqual(answers, [True, False])

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

    def test_the_two_classifiers_agree_about_every_recorded_label(self):
        """The bot's rule against this file's own, over the client's writing.

        They are deliberately different -- the bot asks for printable ASCII
        with a letter in it, this file asks for Unicode categories that are not
        control, format, surrogate, private-use or unassigned -- and the
        recordings are where they have to give the same answer. A disagreement
        means the client has started writing labels one of them is wrong about.
        """
        labels = sorted(recorded_travel_labels(self))
        answers = self.repl.evaluate(
            ["travelLabelIsReadableText " + elm_string(label)
             for label in labels])
        disagreed = [label for label, answer in zip(labels, answers)
                     if answer != looks_like_text(label)]
        self.assertEqual(
            [repr(label) for label in disagreed], [],
            "the bot's label rule and this file's classifier disagree")


class TheRecordedRunsStillSayWhatTheseTestsAssume(unittest.TestCase):
    """The labels above are the client's, not this repo's.

    **What is asserted is the set of *text* labels.** A label with no text is
    not drift, it is a case with its own test above, and failing here on one
    would make this suite depend on which runs happen to be on disk. Two exist
    and both were found this way.

    Note what this check is *not* for any more. Under the old rule a new label
    could have been the one that ends a mission and nobody would have known;
    under this one a new readable label is acted on as soon as the objective is
    finished, which is the intended behaviour. It stays because the vocabulary
    is the evidence every number in this file is counted from.
    """

    def test_no_text_travel_label_has_appeared_that_these_tests_do_not_know(self):
        labels = recorded_travel_labels(self)
        self.assertTrue(labels, "the recordings carry no travel labels at all")
        text_labels = sorted(label for label in labels if looks_like_text(label))
        self.assertTrue(text_labels, "the recordings carry no readable labels")
        self.assertEqual(
            sorted(set(text_labels) - set(TRAVEL_LABELS_SEEN)), [],
            "the client is writing a travel label these tests do not know")

    def test_both_recorded_non_text_labels_are_still_there(self):
        # The corpus is the only reason this repo knows the client does this at
        # all. If they stop appearing the fail-closed rule is resting on
        # nothing, and somebody should know that before relaxing it.
        labels = recorded_travel_labels(self)
        not_text = {label for label in labels if not looks_like_text(label)}
        expected = {"".join(chr(code) for code in codepoints)
                    for codepoints in NON_TEXT_TRAVEL_LABELS.values()}
        self.assertEqual(
            sorted(repr(label) for label in expected - not_text), [],
            "a non-text travel label these tests are built on is no longer in "
            "the recordings")

    def test_a_non_text_label_appears_beside_a_finished_objective(self):
        # The reason the label rule cannot lean on the objective rule. If this
        # ever stops being true the fail-closed choice is still right, but the
        # argument for it is weaker than this file claims.
        beside_finished = [
            match.group("label") for match in recorded_status_lines(self)
            if match.group("instruction") == "no instruction"
            and not looks_like_text(match.group("label"))]
        self.assertTrue(
            beside_finished,
            "no recorded reading pairs an unreadable label with a finished "
            "objective, which is the case this rule exists for")


class TheRecordedRunsSayWhichLabelsThisCovers(unittest.TestCase):
    """#92's measurement, recounted rather than quoted."""

    def test_the_two_labels_the_dock_rule_missed_are_most_of_the_cost(self):
        readings, _, _ = costly_readings(self)
        missed = sum(readings.get(label, 0)
                     for label in TRAVEL_LABELS_THE_DOCK_RULE_MISSED)
        dock = readings.get("Dock", 0)
        self.assertGreater(dock, 0, "the label the first fix handled has to "
                                    "occur, or that fix was unreachable")
        self.assertGreater(
            missed, dock * 10,
            "the labels #92 is about should still dwarf 'Dock'; if they no "
            "longer do, this change is being argued from numbers that moved")

    def test_the_route_already_set_case_is_worth_its_own_branch(self):
        # `Destination Set` is not a click -- `missionTravelStep` filters it --
        # so covering it meant letting the disengage hand back to the branch
        # that travels the route rather than one that presses a button. This is
        # what that is worth.
        readings, _, _ = costly_readings(self)
        self.assertGreater(readings.get("Destination Set", 0), 100)

    def test_the_grids_it_leaves_are_the_busy_ones(self):
        # The rats on grid are why these readings cost more than their count
        # suggests: the bot was not finishing off a straggler, it was working a
        # field it had been told to leave.
        readings, rats, _ = costly_readings(self)
        for label in TRAVEL_LABELS_THE_DOCK_RULE_MISSED:
            self.assertGreater(readings.get(label, 0), 0)
            self.assertGreaterEqual(rats[label] / readings[label], 2.0)

    def test_warp_to_location_never_costs_anything(self):
        """The exclusion that makes "any step" safe, and it is evidence.

        A rule keyed on the existence of a step would disengage inside a pocket
        that is not cleared if this label appeared beside a finished objective
        with a fight still on the grid. In 9,945 readings it has appeared with
        a finished objective **three times**, all three in one flicker between
        `Dock` readings as a mission ended, and **never once** with a rat on the
        overview -- so it has never appeared in a reading where this branch
        changes what the bot does.

        The three are why this asserts the costly count rather than the raw
        one: the issue was filed on "9,934 and never", the corpus has moved,
        and the property that actually matters survived the move.
        """
        with_objective = 0
        without = 0
        for match in recorded_status_lines(self):
            if match.group("label") != TRAVEL_LABEL_THAT_NEVER_ENDS_A_MISSION:
                continue
            if match.group("instruction") == "no instruction":
                without += 1
            else:
                with_objective += 1
        self.assertGreater(with_objective, 1000,
                           "this label has to be common, or its rarity beside "
                           "a finished objective says nothing")
        self.assertLess(without * 100, with_objective,
                        "this label is meant to be the one that means the "
                        "mission is still running")
        readings, _, _ = costly_readings(self)
        self.assertEqual(
            readings.get(TRAVEL_LABEL_THAT_NEVER_ENDS_A_MISSION, 0), 0,
            "'%s' now appears with a finished objective *and rats on grid*, "
            "which is a reading where this change disengages inside a pocket "
            "-- the rule needs re-arguing"
            % TRAVEL_LABEL_THAT_NEVER_ENDS_A_MISSION)

    def test_the_transient_labels_are_only_reached_in_warp(self):
        """Why `Preparing` and `Warping` are included rather than excluded.

        They read like states rather than commands, and the argument for
        covering them anyway is that the distinction is unobservable from this
        branch: on every costly reading carrying one, the ship was already in
        warp, where `decideActionWhenInSpace` answers "I am in warp" long
        before this branch is consulted. Including them therefore changes no
        recorded reading, and excluding them would be a list to maintain for
        nothing.
        """
        readings, _, in_warp = costly_readings(self)
        transient = {label: count for label, count in readings.items()
                     if label in ("Preparing", "Warping")}
        self.assertTrue(transient, "no recorded reading carries one of these "
                                   "labels with a finished objective and rats "
                                   "on grid")
        for label, count in sorted(transient.items()):
            self.assertEqual(
                in_warp.get(label, 0), count,
                "'%s' now coincides with a finished objective and rats on grid "
                "while the ship is *not* in warp, which is the case the "
                "argument for including it says does not happen" % label)


class TheOrderingIsThePoint(unittest.TestCase):
    """Travel has to win over "something is still alive", and nothing else moves."""

    def setUp(self):
        self.source = bot_source()

    def test_the_travel_step_is_decided_before_the_fight(self):
        start = self.source.index("decideActionInMissionPocket context seeUndockingComplete =")
        end = self.source.index("\ntravelOutranksTheFight :", start)
        body = self.source[start:end]
        override = body.index("travelOutranksTheFight context")
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
        start = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        body = collapsed(self.source[start:end])
        self.assertIn("runAwayIfLowHealth context shipUI |> Maybe.withDefault",
                      body)
        self.assertLess(body.index("runAwayIfLowHealth context shipUI"),
                        body.index("decideActionWhenInSpace context"),
                        "the retreat must be consulted before the in-space "
                        "decision, not the other way round")

    def test_the_ship_loss_verdict_still_outranks_everything(self):
        # PR #37 pinned this and it is not this change's to move: the pre-split
        # list is untouched, and nothing about travel appears in it.
        start = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", start)
        body = self.source[start:end]
        pod = body.index(", recoverPodAfterShipLoss context")
        split = body.index("branchDependingOnDockedOrInSpace")
        self.assertLess(pod, split)
        self.assertNotIn("travelOutranksTheFight", body)

    def test_the_override_is_reached_from_the_mission_pocket_and_nowhere_else(self):
        callers = [line for line in self.source.split("\n")
                   if "travelOutranksTheFight" in line
                   and not line.startswith("travelOutranksTheFight")]
        # Its own type annotation, the doc references in
        # `decideActionInMissionPocket`, and the single call.
        self.assertEqual(
            [line.strip() for line in callers if line.startswith("    travel")],
            ["travelOutranksTheFight context"])


class WhatStillKeepsTheGunsFiring(unittest.TestCase):
    """The exceptions are the reviewable part of a change that stops a fight."""

    def setUp(self):
        self.source = bot_source()
        start = self.source.index(
            "travelOutranksTheFight context ifTheJobHereIsDone ifTheFightIsStillOurs =")
        self.branch = self.source[start:self.source.index(
            "\ntravelStepThatEndsTheFight :", start)]
        rule = self.source.index("travelStepThatEndsTheFight context =")
        self.rule = self.source[rule:self.source.index(
            "\ntravelLabelIsReadableText :", rule)]

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
        # the tracker asked for a trip, rather than appearing to lose interest.
        # The wording is #49's, unchanged, so a grep or a log filter an operator
        # already has keeps working -- and it carries the label, which is now
        # the part that varies.
        self.assertIn("The objective is complete and the mission tracker says",
                      self.branch)
        self.assertIn("++ label", self.branch)

    def test_the_objective_half_is_still_required(self):
        # The clause, not the mention. `test_ammo_silenced_bound`'s lesson: an
        # assertion that a rule *names* a condition passes for a rule that has
        # been conjoined into never firing, which is the defect it exists to
        # prevent -- and a mutation adding `False &&` here proved it does.
        self.assertIn(
            "if not (missionHasNoOutstandingInstruction "
            "mission.instructionTexts) then Nothing else",
            collapsed(self.rule))

    def test_an_unreadable_label_is_not_a_step(self):
        # The fail-closed decision, read out of the rule rather than restated:
        # dropping this clause still compiles, still passes everything else,
        # and disengages on a button the client failed to draw. Pinned as the
        # whole clause for the reason above.
        self.assertIn(
            "if not (travelLabelIsReadableText label) then Nothing else",
            collapsed(self.rule))

    def test_the_step_has_to_be_one_the_bot_can_take(self):
        # Either a button `missionTravelStep` would click, or the tracker
        # reporting a route the panel says exists. Without the second condition
        # the branch can disengage into the bottom of the travel tree, where
        # the stall counter and #54's abandonment are waiting.
        body = collapsed(self.rule)
        self.assertIn("case missionTravelStep context of", body)
        self.assertIn("labelReportsRouteAlreadySet label && routeIsSet context",
                      body)

    def test_the_label_rule_classifies_rather_than_matching_a_word(self):
        # #49's `== "dock"` is gone, and what replaces it must not be another
        # word list -- nor a private-use-area test, which is the trap: run 11's
        # codepoint is unassigned, and a PUA rule would call it text.
        start = self.source.index("travelLabelIsReadableText label =")
        body = collapsed(self.source[start:self.source.index("\n\n\n", start)])
        self.assertNotIn('== "dock"', body)
        self.assertNotIn("String.contains", body)
        self.assertNotIn("stringContainsIgnoringCase", body)
        self.assertIn("String.all", body)
        self.assertIn("String.any Char.isAlpha", body)


class TheLeavingIsTheExistingLeaving(unittest.TestCase):
    """No second travel path, no second drone recall, and no second clock."""

    def setUp(self):
        self.source = bot_source()
        start = self.source.index("decideActionInMissionPocket context seeUndockingComplete =")
        # To the next doc comment rather than to the next declaration: the doc
        # comment names the binding too, and counting its mentions as uses
        # would make the assertion below say nothing.
        self.pocket = self.source[start:self.source.index("\n{-|", start)]
        branch = self.source.index(
            "travelOutranksTheFight context ifTheJobHereIsDone ifTheFightIsStillOurs =")
        self.branch = self.source[branch:self.source.index(
            "\ntravelStepThatEndsTheFight :", branch)]

    def test_the_disengage_takes_the_step_the_fight_was_hiding(self):
        """One binding, handed to both -- which is the whole safety argument.

        The value passed to `travelOutranksTheFight` as "the job here is done"
        is the same one `decideActionInCombat` falls through to, so disengaging
        cannot invent a move, drop a settling window, or reorder the gate and
        the route. A second copy of the travel branch would pass every other
        case here and drift from it silently.
        """
        body = collapsed(self.pocket)
        self.assertIn("travelOutranksTheFight context "
                      "travelTheStepTheTrackerOffers", body)
        self.assertEqual(body.count("travelTheStepTheTrackerOffers ="), 1)
        self.assertEqual(body.count("travelTheStepTheTrackerOffers"), 3)

    def test_the_drones_come_home_through_the_gate_every_warp_uses(self):
        # Issue #7 lost ten drones by warping with them out, and the recall that
        # followed routes every warp, dock, retreat and gate activation. The
        # step this branch hands back must go through it rather than beside it.
        self.assertIn(
            "ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context",
            self.pocket)

    def test_the_click_goes_through_the_shared_travel_button_step(self):
        # Which is what keeps the "I clicked on the previous step" settling
        # window: the tracker's button changes what it says once pressed.
        self.assertIn("clickMissionTravelButton context label buttonNode",
                      self.pocket)

    def test_the_gate_still_outranks_flying_a_route(self):
        # An acceleration gate on the grid is how a multi-pocket mission moves
        # on, and the route is how it leaves the system. Handing back the whole
        # travel branch is what keeps that order; a branch that jumped straight
        # to the route would strand the bot short of a gate.
        body = collapsed(self.pocket)
        self.assertLess(body.index("activateAccelerationGateIfPresent context"),
                        body.index("if routeIsSet context then"))

    def test_the_branch_itself_neither_clicks_nor_counts(self):
        # Every condition is re-derived from the live reading, so the branch
        # clears itself the moment the tracker stops offering a step. A counter
        # here would be a second "leave now" controller beside #32's retreat,
        # and a click of its own would be a second travel path.
        self.assertNotIn("context.memory", self.branch)
        self.assertNotIn("Ticks", self.branch)
        self.assertNotIn("droneRecall", self.branch)
        self.assertNotIn("clickUiElement", self.branch)
        self.assertNotIn("clickMissionTravelButton", self.branch)


if __name__ == "__main__":
    unittest.main()
