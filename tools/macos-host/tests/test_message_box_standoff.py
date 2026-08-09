"""Tests for the mission runner giving up on a message box its answer does not
close.

Issue #101. `closeMessageBoxByDeclining` had no counter, no bound and no
give-up, so it answered a dialog the same way on the first reading and on the
thirty-thousandth. Run 30 found the window that does not care: something the
client draws on the `MessageBox` widget carried a `no_dialog_button`, so
`Dismiss it using No.` was the right-looking answer, and the box was still there
afterwards -- **32,585 readings, three hours and forty-four minutes**, with
nothing else in the bot running for any of them, because `closeMessageBox` is
reached from `generalSetupInUserInterface` and that list is evaluated above the
docked-or-in-space split. `abandonMissionThatCannotProgress` held a live verdict
throughout and its own 200-reading bound never fired, because the branch holding
it was unreachable.

**The corpus is what calibrates the bound**, and it separates by three orders of
magnitude. Counting consecutive readings with a message box on the screen:

    runs 10, 22, 25, 26, 27    175 stretches, 1,267 readings
                               lengths 6, 10, 11, 18, 20, 44 and nothing else
    run 30                       1 stretch,  32,585 readings

So `messageBoxAnswersBeforeEscape` (60) is placed in a gap rather than cut
through a distribution. A stretch is an *upper bound* on any single box, since
one stretch can hold several dialogs in succession, which makes the real
separation wider still -- the safe direction for a threshold that must never
fire on a box the ordinary answer was about to close.

**What is deliberately not the fix**, and is asserted here as an absence:
narrowing `parseMessageBoxesFromUITreeRoot` so that an emoji picker is not a
message box. That treats one instance and leaves the shape -- any window on that
widget the declining answer does not close reproduces run 30 exactly.

**What must not change** is the default. #54's standing lesson is that the bot's
automatic reply to a dialog is the one that declines, because these guard
destructive actions, and the escalation must not become a way to answer them
some other way: the ladder is the same declining answer, then Escape at the same
box, then leaving it alone. `closeMessageBoxByDeclining` still contains no
affirmative at all, which a case here pins alongside the ones in
`test_abandon_stuck_mission.py`.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The decision line `closeMessageBoxByDeclining` prints on every reading it
# answers a box, and the only thing run 30's log has 32,585 of.
DECLINE_LINE = "+ I see a message box to close"

# The runs whose message boxes all closed, and the one whose did not.
RUNS_THAT_CLOSED_THEIR_BOXES = ("10", "22", "25", "26", "27")
THE_INCIDENT = "30"

# The repl needs more than `Bot` here: a `MessageBox` has to be built out of raw
# UI-tree nodes before `messageBoxIdentity` can be asked about one.
PREAMBLE = (
    "import Bot exposing (..)",
    "import Dict",
    "import Json.Encode",
    "import EveOnline.MemoryReading",
)

# Built once and shared, because every case that asks about a box needs all of
# them and the repl recompiles the module per line it is given.
BOX_BUILDERS = (
    "zeroRegion = { x = 0, y = 0, width = 0, height = 0 }",

    'rawNode typeName pairs kids ='
    ' { originalJson = Json.Encode.null, pythonObjectAddress = "0",'
    ' pythonObjectTypeName = typeName,'
    ' dictEntriesOfInterest ='
    ' Dict.fromList (List.map (\\( k, v ) -> ( k, Json.Encode.string v )) pairs),'
    ' children = Just (List.map EveOnline.MemoryReading.UITreeNodeChild kids) }',

    "withRegion n ="
    " { uiNode = n, children = Nothing, selfDisplayRegion = zeroRegion,"
    " totalDisplayRegion = zeroRegion, totalDisplayRegionVisible = zeroRegion }",

    'textNode t = rawNode "EveLabelMedium" [ ( "_setText", t ) ] []',

    'boxButton names label ='
    ' { uiNode = withRegion (rawNode "Button"'
    ' (List.map (\\n -> ( "_name", n )) names) []), mainText = label }',

    'box texts buttons ='
    ' { uiNode = withRegion (rawNode "MessageBox" [] (List.map textNode texts)),'
    ' buttonGroup = Nothing, buttons = buttons }',
)


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


def without_comments(text):
    """The same source with its `--` line comments dropped.

    For the one case that asserts what a branch does *not* contain: the
    give-up's whole body is a `Nothing` and several lines of argument for it,
    and `collapsed` puts the argument on the same line as the answer.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(source, name):
    """One top-level declaration, from its type annotation to the next gap."""
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return rest[:rest.index("\n\n\n")]


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def standoff(identity, readings):
    return "(Just { identity = %s, readings = %d })" % (
        elm_string(identity), readings)


def box_streaks(log_path):
    """Lengths of every run of consecutive readings holding a message box.

    Counted in *readings* -- the `# [tick.substep]` boundary -- and not in
    decision lines, for the reason `stall_watch.py` has a section on: the bot
    re-derives its whole path per framework event, so decision lines are the
    wrong statistic and were the wrong statistic twice already.
    """
    streaks, current, saw, started = [], 0, False, False
    with open(log_path, encoding="utf-8", errors="ignore") as log:
        for line in log:
            if line.startswith("# ["):
                if started:
                    if saw:
                        current += 1
                    else:
                        if current:
                            streaks.append(current)
                        current = 0
                started, saw = True, False
            elif line.startswith(DECLINE_LINE):
                saw = True
    if saw:
        current += 1
    if current:
        streaks.append(current)
    return streaks


def threshold_from_source(name):
    """A constant read out of `Bot.elm`, so the corpus cases test the shipped
    number rather than one restated here."""
    body = declaration(bot_source(), name)
    return int(re.search(r"\n%s =\s*(\d+)" % name, "\n" + body).group(1))


class TheCountIsAboutOneBox(unittest.TestCase):
    """`messageBoxStandoffAfterReading`, over the states a run passes through.

    The count has to be per box. A global tally of dismissals accumulates across
    a run that legitimately closes many dialogs -- run 25 closed 143 stretches of
    them -- and reaches a give-up it should never reach.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-msgbox-count-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _after(self, before, identity_now):
        return (
            "messageBoxStandoffAfterReading "
            "{ before = %s, identityNow = %s }"
            % (before,
               "Nothing" if identity_now is None else "(Just %s)"
               % elm_string(identity_now)))

    def test_the_first_reading_with_a_box_starts_at_one(self):
        # One, not zero: memory is updated before the decision runs, so the
        # reading the bot first answers a box is a reading the box survived.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just { identity = %s, readings = 1 }"
                % (self._after("Nothing", "a picker"), elm_string("a picker"))]),
            [True])

    def test_the_same_box_again_advances_it(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just { identity = %s, readings = 8 }"
                % (self._after(standoff("a picker", 7), "a picker"),
                   elm_string("a picker"))]),
            [True])

    def test_no_box_ends_it_outright(self):
        # The reset that keeps the count about *this* box. Without it run 25's
        # 143 dialogs would have accumulated towards a give-up between them.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % self._after(standoff("a picker", 119), None)]),
            [True])

    def test_a_different_box_starts_over(self):
        # A run that answers dialog after dialog with no quiet reading between
        # them still starts each one from 1. This is the case a bare
        # "some box is open" counter gets wrong.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just { identity = %s, readings = 1 }"
                % (self._after(standoff("Quit Mission?", 119), "Decline Mission?"),
                   elm_string("Decline Mission?"))]),
            [True])

    def test_the_count_only_ever_rises_by_one_and_only_on_the_same_box(self):
        # A control row rides along, so a repl answering `True` to everything
        # cannot pass this.
        answers = self.repl.evaluate([
            "(%s |> Maybe.map .readings) == Just 2" % self._after(standoff("x", 1), "x"),
            "(%s |> Maybe.map .readings) == Just 1" % self._after(standoff("x", 1), "y"),
            "(%s |> Maybe.map .readings) == Just 1" % self._after("Nothing", "x"),
            "(%s |> Maybe.map .readings) == Just 3" % self._after(standoff("x", 1), "x"),
        ])
        self.assertEqual(answers, [True, True, True, False])


class TheLadderIsAnswerThenEscapeThenStop(unittest.TestCase):
    """`messageBoxStandoffVerdict`, at every boundary it has.

    The declining answer stays the default (#54), Escape is the escalation this
    codebase already uses, and the give-up hands the tree back rather than
    answering forever.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-msgbox-ladder-")
        cls.answers_before_escape = threshold_from_source(
            "messageBoxAnswersBeforeEscape")
        cls.give_up = cls.answers_before_escape * 2

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _verdict(self, readings):
        return "messageBoxStandoffVerdict %s" % standoff("a picker", readings)

    def test_no_box_at_all_answers_as_it_always_did(self):
        self.assertEqual(
            self.repl.evaluate([
                "messageBoxStandoffVerdict Nothing == AnswerTheMessageBox"]),
            [True])

    def test_the_ordinary_answer_holds_through_the_slowest_recorded_dialog(self):
        # 44 readings is run 26's worst, and the whole point of the number is
        # that a dialog like that one is still answered normally.
        self.assertEqual(
            self.repl.evaluate([
                "%s == AnswerTheMessageBox" % self._verdict(44)]),
            [True])

    def test_escape_starts_exactly_at_the_threshold(self):
        # Both sides of the boundary, because a comparison moved by one is the
        # mutation this case exists to catch.
        answers = self.repl.evaluate([
            "%s == AnswerTheMessageBox" % self._verdict(self.answers_before_escape - 1),
            "%s == PressEscapeAtTheMessageBox" % self._verdict(self.answers_before_escape),
        ])
        self.assertEqual(answers, [True, True])

    def test_the_give_up_starts_exactly_at_its_own_threshold(self):
        answers = self.repl.evaluate([
            "%s == PressEscapeAtTheMessageBox" % self._verdict(self.give_up - 1),
            "%s == LeaveTheMessageBoxAlone" % self._verdict(self.give_up),
        ])
        self.assertEqual(answers, [True, True])

    def test_it_never_goes_back_to_answering_once_it_has_given_up(self):
        # Run 30 ran to 32,585. Nothing above the bound may answer the box
        # again, or the standoff resumes wherever the ladder wrapped.
        self.assertEqual(
            self.repl.evaluate([
                "%s == LeaveTheMessageBoxAlone" % self._verdict(32585)]),
            [True])

    def test_escape_gets_as_long_as_the_answer_it_replaced(self):
        # Stated as a relation rather than as a second number, so retuning one
        # cannot silently leave the other where it was. Both halves are needed:
        # the value, and the *form* -- a bare `120` evaluates the same today and
        # is exactly the drift `missionStalledReadingsBeforeAbandoning` is
        # written as a multiple to prevent.
        self.assertEqual(
            self.repl.evaluate([
                "messageBoxStandoffGiveUpReadings == messageBoxAnswersBeforeEscape * 2"]),
            [True])
        self.assertIn(
            "messageBoxStandoffGiveUpReadings = messageBoxAnswersBeforeEscape * 2",
            collapsed(declaration(bot_source(), "messageBoxStandoffGiveUpReadings")),
            "the give-up has to be written as a multiple of the escalation, "
            "not as the number it currently comes to")


class TheBoxIsIdentifiedByWhatItSaysAndOffers(unittest.TestCase):
    """`messageBoxIdentity`, over the boxes this file has to tell apart.

    Its display texts and its buttons, and not its display region --
    `strayContextMenuStuckTicksThreshold` records what a coordinate-based
    identity costs, which is a count that never accumulates at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-msgbox-identity-",
                             preamble=PREAMBLE)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _identity(self, expression):
        return self.repl.strings(["messageBoxIdentity (%s)" % expression],
                                 BOX_BUILDERS)[0]

    def test_it_names_the_box_by_what_it_says(self):
        identity = self._identity(
            'box [ "Quit Mission?" ] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        self.assertIn("Quit Mission?", identity)

    def test_it_carries_the_button_names_as_well_as_their_labels(self):
        # `no_dialog_button` is the one name this file relies on across client
        # languages, and a dialog offering it is a different dialog from one
        # offering an unnamed OK even where both render the same word.
        identity = self._identity(
            'box [ "Quit Mission?" ] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        self.assertIn("no_dialog_button", identity)
        self.assertIn("No", identity)

    def test_two_dialogs_saying_different_things_are_different_boxes(self):
        quit_mission = self._identity(
            'box [ "Quit Mission?" ] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        decline = self._identity(
            'box [ "Decline Mission?" ] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        self.assertNotEqual(quit_mission, decline)

    def test_two_dialogs_offering_different_buttons_are_different_boxes(self):
        with_no = self._identity(
            'box [ "Are you sure?" ] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        with_ok = self._identity(
            'box [ "Are you sure?" ] [ boxButton [] (Just "OK") ]')
        self.assertNotEqual(with_no, with_ok)

    def test_the_same_box_read_twice_reads_the_same(self):
        # The property the whole count rests on. Run 30's box was re-rendered
        # every reading for three hours and forty-four minutes and the bot's
        # click landed on the same point every time.
        expression = ('box [ "Quit Mission?" ]'
                      ' [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        self.assertEqual(self._identity(expression), self._identity(expression))

    def test_a_box_with_no_text_of_its_own_still_has_an_identity(self):
        # Run 30's box, as far as anyone can reconstruct it: a widget with a
        # `no_dialog_button` and, apparently, nothing to read. An identity that
        # came back empty for it would collapse every such box into one.
        identity = self._identity(
            'box [] [ boxButton [ "no_dialog_button" ] (Just "No") ]')
        self.assertIn("no_dialog_button", identity)
        self.assertNotEqual(identity.strip(), "")


class TheGiveUpNamesTheBoxAndWhatItTried(unittest.TestCase):
    """`describeMessageBoxGivenUpOn`.

    32,585 identical `Dismiss it using No.` lines are what an operator got, and
    `stall_watch.py` deduped them into a single alarm, so nothing escalated.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-msgbox-giveup-")
        cls.said = cls.repl.strings([
            "describeMessageBoxGivenUpOn %s"
            % elm_string("message box saying 'Quit Mission?' "
                         "with buttons [no_dialog_button=No]")])[0]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_box(self):
        self.assertIn("Quit Mission?", self.said)
        self.assertIn("no_dialog_button", self.said)

    def test_it_says_what_was_tried_and_how_long_for(self):
        # Both rungs, with their counts, so the line answers "what did you do
        # about it" rather than only "I gave up".
        self.assertIn("Escape", self.said)
        self.assertIn(str(threshold_from_source("messageBoxAnswersBeforeEscape")),
                      self.said)

    def test_it_says_the_box_is_still_there_and_needs_a_person(self):
        # The bot is not claiming to have closed it. Returning `Nothing` leaves
        # the box on the screen, and an operator who reads this as success will
        # not go and close it.
        self.assertIn("still there", self.said)
        self.assertIn("by hand", self.said)

    def test_a_long_dialog_does_not_run_away_with_the_line(self):
        long_identity = "message box saying '" + ("blah " * 200) + "'"
        said = self.repl.strings(
            ["describeMessageBoxGivenUpOn %s" % elm_string(long_identity)])[0]
        self.assertLess(len(said), len(long_identity))
        self.assertIn("...", said)
        self.assertIn("by hand", said)


class TheStatusClauseNamesTheBox(unittest.TestCase):
    """`describeMessageBoxStandoff`, executed rather than read.

    Issue #164's first Unverified item is *what the box was*. saxrat run 11 --
    this ladder, in the other app -- spent 60 readings on one and its 125 MB log
    cannot say what it was, because the only thing that ever prints a box's
    identity is the give-up sentence and that run never reached the give-up. So
    the clause an operator reads on every counted reading now carries the
    identity, and it is a function of the record so a case can execute it: the
    version it replaces was inline in `statusTextFromState` and could only be
    checked by substring, which is the trap that let a clause printing nothing
    at all pass PR #109's own file once.
    """

    IDENTITY = ("message box saying 'Quit Mission?' with buttons "
                "[no_dialog_button=No]")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-msgbox-clause-")
        escalate_at = threshold_from_source("messageBoxAnswersBeforeEscape")
        give_up_at = escalate_at * 2
        cls.quiet, cls.answering, cls.escaping, cls.given_up = cls.repl.strings([
            "describeMessageBoxStandoff Nothing",
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY, 1),
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY,
                                                       escalate_at),
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY,
                                                       give_up_at),
        ])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_reading_with_no_box_says_nothing(self):
        # The clause sits in a group of settling counters that disappears when
        # nothing is waiting on anything, so it has to be empty on the ordinary
        # reading or it is noise on every line of every run.
        self.assertEqual(self.quiet, "")

    def test_every_rung_names_the_box(self):
        # Including the first, which is the one saxrat run 11 spent 59 of its 60
        # readings on and the one an operator would have been reading while the
        # window was still on the screen to be looked at.
        for rung in (self.answering, self.escaping, self.given_up):
            self.assertIn("Quit Mission?", rung)
            self.assertIn("no_dialog_button", rung)

    def test_every_rung_carries_the_count_against_the_bound(self):
        escalate_at = threshold_from_source("messageBoxAnswersBeforeEscape")
        give_up_at = escalate_at * 2
        self.assertIn("1/%d" % give_up_at, self.answering)
        self.assertIn("%d/%d" % (escalate_at, give_up_at), self.escaping)
        self.assertIn("%d/%d" % (give_up_at, give_up_at), self.given_up)

    def test_it_says_which_rung_the_bot_is_on(self):
        self.assertIn("pressing Escape at it", self.escaping)
        self.assertIn("GIVEN UP ON, still open", self.given_up)
        for wording in ("pressing Escape at it", "GIVEN UP ON"):
            self.assertNotIn(
                wording, self.answering,
                "the ordinary rung claims to be doing something it is not")

    def test_a_long_dialog_does_not_run_away_with_the_status_line(self):
        # The identity carries the box's whole rendered text, and this clause
        # goes out on every reading rather than once, so a dialog with a
        # paragraph in it would push the rest of the status line along.
        long_identity = "message box saying '" + ("blah " * 200) + "'"
        said, = self.repl.strings(
            ["describeMessageBoxStandoff %s" % standoff(long_identity, 1)])
        self.assertLess(len(said), len(long_identity))
        self.assertIn("...", said)

    def test_the_two_lines_cut_a_box_the_same_way(self):
        # One cut for both readers. Two would drift, and an operator comparing
        # the status line against the give-up sentence would be comparing two
        # different prefixes of the same dialog.
        long_identity = "message box saying '" + ("blah " * 200) + "'"
        clause, sentence, cut = self.repl.strings([
            "describeMessageBoxStandoff %s" % standoff(long_identity, 1),
            "describeMessageBoxGivenUpOn %s" % elm_string(long_identity),
            "messageBoxIdentityForOperator %s" % elm_string(long_identity),
        ])
        self.assertIn(cut, clause)
        self.assertIn(cut, sentence)

    def test_the_two_apps_render_the_box_the_same_way(self):
        # The wording differs -- each app's status line has its own shape -- but
        # both have to name the box, and a port that named it in one is a port
        # that leaves the other's next incident as unrecoverable as run 11's.
        saxrat = os.path.join(
            os.path.dirname(os.path.dirname(MISSION_RUNNER_BOT_ELM)),
            "eve-online-saxrat", "Bot.elm")
        with open(saxrat, encoding="utf-8") as source:
            theirs = collapsed(declaration(source.read(),
                                           "describeMessageBoxStandoff"))
        for both in ("messageBoxIdentityForOperator present.identity",
                     "messageBoxStandoffVerdict (Just present)",
                     "String.fromInt messageBoxStandoffGiveUpReadings"):
            self.assertIn(both, theirs)
            self.assertIn(
                both,
                collapsed(declaration(bot_source(),
                                      "describeMessageBoxStandoff")))


class TheRecordedRunsAreWhatCalibratesTheBound(unittest.TestCase):
    """The corpus, recounted, as the relations the threshold rests on.

    Numbers rather than relations would go red as the corpus grows, which is
    `test_travel_outranks_the_fight.py`'s lesson. What is asserted is the
    separation: every stretch of message box in a run that recovered is below
    the escalation, and run 30's is far above the give-up.
    """

    def test_every_box_that_ever_closed_closed_before_the_escalation(self):
        # The direction that matters. A recorded dialog reaching the escalation
        # would mean this bound fires on boxes the ordinary answer closes, and
        # that is a failure rather than a corpus that has grown.
        escalate_at = threshold_from_source("messageBoxAnswersBeforeEscape")
        worst = 0
        for name, path in recorded_runs(*RUNS_THAT_CLOSED_THEIR_BOXES):
            for streak in box_streaks(path):
                worst = max(worst, streak)
                self.assertLess(
                    streak, escalate_at,
                    "run %s spent %d consecutive readings on a message box "
                    "that did close, against an escalation at %d"
                    % (name, streak, escalate_at))
        self.assertGreater(
            worst, 0,
            "no recorded message box at all, so this proves nothing")

    def test_run_thirty_is_far_past_the_give_up(self):
        give_up = threshold_from_source("messageBoxAnswersBeforeEscape") * 2
        (name, path), = recorded_runs(THE_INCIDENT)
        streaks = box_streaks(path)
        self.assertTrue(streaks, "run %s carries no message box at all" % name)
        self.assertGreater(max(streaks), give_up * 10)

    def test_nothing_else_in_run_thirty_ran_while_the_box_was_up(self):
        # The cost, and the reason the give-up hands the tree back rather than
        # asking for help: the abandonment's own bound was unreachable.
        (_, path), = recorded_runs(THE_INCIDENT)
        with open(path, encoding="utf-8", errors="ignore") as log:
            after_onset = False
            others = 0
            boxes = 0
            for line in log:
                if line.startswith(DECLINE_LINE):
                    after_onset = True
                    boxes += 1
                elif after_onset and line.startswith("+ ") and not line.startswith("++"):
                    others += 1
        self.assertGreater(boxes, 10000)
        self.assertLess(
            others, boxes // 1000,
            "run 30 is supposed to be the run in which nothing but the message "
            "box ran")


class TheRuleIsWiredIntoTheTree(unittest.TestCase):
    """That the bound above is what the bot consults, and where.

    A rule no branch asks is a rule that cannot prevent anything, which is the
    shape #98 arrived in and the shape #101 is the cost of.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_box_branch_consults_the_verdict(self):
        self.assertIn("messageBoxStandoffVerdict standoff",
                      collapsed(declaration(self.source, "closeMessageBox")))

    def test_the_setup_list_passes_the_standoff_down(self):
        body = collapsed(declaration(self.source, "generalSetupInUserInterface"))
        self.assertIn("standoff = messageBoxStandoff", body)

    def test_the_root_reads_it_out_of_memory(self):
        body = collapsed(declaration(
            self.source, "missionBotDecisionRootBeforeApplyingSettings"))
        self.assertIn("messageBoxStandoff = context.memory.messageBoxStandoff",
                      body)

    def test_giving_up_hands_the_rest_of_the_tree_back(self):
        # Not a wait and not an alarm. The whole cost of #101 was that nothing
        # below `generalSetupInUserInterface` ran, so the give-up has to answer
        # `Nothing` and let the branches with their own bounds reach them.
        body = collapsed(without_comments(
            declaration(self.source, "closeMessageBox")))
        self.assertIn("LeaveTheMessageBoxAlone -> Nothing", body)
        self.assertIn("Maybe.andThen", body,
                      "the branch must be able to answer Nothing for a reading "
                      "that has a box in it")

    def test_the_declining_answer_is_still_the_default(self):
        # #54's standing lesson, and the reason the ladder starts where it did.
        # Every reading below the escalation goes to the same place it always
        # went.
        body = collapsed(declaration(self.source, "closeMessageBox"))
        answer_at = body.index("AnswerTheMessageBox ->")
        self.assertIn("closeMessageBoxByDeclining messageBox", body[answer_at:])

    def test_the_declining_path_still_contains_no_affirmative(self):
        # Pinned in `test_abandon_stuck_mission.py` too, and pinned again here
        # because this change is the one that reaches into this function.
        body = collapsed(declaration(self.source, "closeMessageBoxByDeclining"))
        self.assertNotIn("yes_dialog_button", body)
        self.assertIn('namedButton "no_dialog_button"', body)

    def test_the_escalation_is_escape_and_not_a_click(self):
        # Escape is what `beginCascade` and `clearStrayContextMenu` already
        # press, and it needs no focus. A click would be a click into a dialog
        # nobody has read.
        body = collapsed(declaration(self.source, "closeMessageBox"))
        escape_at = body.index("PressEscapeAtTheMessageBox ->")
        answer_at = body.index("AnswerTheMessageBox ->")
        rung = body[escape_at:answer_at]
        self.assertIn("EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE", rung)
        self.assertNotIn("mouseClickOnUIElement", rung)

    def test_the_standoff_is_written_where_memory_is_written(self):
        # The decision tree cannot write memory, and the branch that would keep
        # the count is precisely the branch that stops running when the count
        # reaches its bound.
        body = collapsed(declaration(
            self.source, "updateMemoryForNewReadingFromGame"))
        self.assertIn("messageBoxStandoff = messageBoxStandoffAfterReading", body)
        self.assertIn("Maybe.map messageBoxIdentity", body)

    def test_the_give_up_is_announced_once_at_the_root(self):
        # `dronesLeftBehindLastChange`'s mechanism: a field holding a message
        # only on the reading its conclusion changed, folded in at the root.
        self.assertIn("context.memory.messageBoxLastChange",
                      collapsed(declaration(self.source, "missionBotDecisionRoot")))
        self.assertIn("describeMessageBoxGivenUpOn",
                      collapsed(declaration(
                          self.source, "updateMemoryForNewReadingFromGame")))

    def test_the_status_line_keeps_saying_it_after_the_branch_goes_quiet(self):
        # Once the give-up is reached `closeMessageBox` prints no decision line
        # at all, so the status line is the only place a reading says a box is
        # still sitting in front of the bot.
        #
        # The clause is a rule since #164 and is executed by
        # `TheStatusClauseNamesTheBox` below. What is read here is only that the
        # status line asks it and carries no second copy of it: two renderings
        # of one clause is how the give-up sentence and the status line would
        # come to disagree about a box.
        body = collapsed(declaration(self.source, "statusTextFromState"))
        self.assertIn(
            "describeMessageBoxStandoff context.memory.messageBoxStandoff",
            body)
        for reimplemented in ("standoff.readings", "GIVEN UP ON",
                              "messageBoxStandoffVerdict"):
            self.assertNotIn(
                reimplemented, body,
                "the status line renders the clause itself again, so a case "
                "that executes the rule no longer tests what an operator reads")

    def test_the_parser_still_matches_every_message_box(self):
        # Explicitly *not* the fix. Narrowing this treats the emoji picker and
        # leaves the shape: any window on the widget that the declining answer
        # does not close reproduces run 30 exactly.
        parser = os.path.join(
            os.path.dirname(MISSION_RUNNER_BOT_ELM), "EveOnline",
            "ParseUserInterface.elm")
        with open(parser, encoding="utf-8") as source:
            body = collapsed(declaration(source.read(),
                                         "parseMessageBoxesFromUITreeRoot"))
        self.assertIn(
            '.pythonObjectTypeName >> (==) "MessageBox"', body,
            "the message-box parser is deliberately unchanged by #101")


if __name__ == "__main__":
    unittest.main()
