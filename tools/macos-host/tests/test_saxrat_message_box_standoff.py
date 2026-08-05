"""Tests for saxrat giving up on a message box its dismissal does not close.

Issue #138, which is the mission runner's #101 in saxrat's copy of the same
branch. `closeMessageBox` here had no counter, no bound and no give-up: it
clicked its dismissal on the first reading and would have clicked it identically
on the thirty-thousandth, while `generalSetupInUserInterface` -- the list it is
reached from -- is evaluated above the docked-or-in-space split, above the pod
recovery and above everything the bot does in space.

**The starvation is the mission runner's run 30 and it is unobserved here.** That
bot spent 32,585 readings, three hours and forty-four minutes, dismissing one
window that did not care, with nothing else running for any of them. saxrat has
the same parse breadth (`parseMessageBoxesFromUITreeRoot` matches
`pythonObjectTypeName == "MessageBox"` and nothing else, in both copies) and had
none of the counter -- and it rats unattended, so nobody is at the console.

**The bound's size rests on the mission runner's corpus, and that is checked
rather than asserted.** `TheRecordedSaxratRunsCannotSizeThisBoundTest` reads the
three recorded saxrat runs and finds no message box on any of their ~49,000
readings, so there is nothing here to place a threshold against;
`TheMissionRunnersCorpusIsWhatSizesThisBoundTest` recounts the runs that do have
one and asserts the separation 60 sits in. The two bots' constants are compared
so a retune in one is visible in the other.

**What must not change** is the default. The declining answer stays the first
rung (#54's standing lesson in the mission runner, and these dialogs guard
destructive actions here too), the give-up hands the tree back with `Nothing`
rather than raising `askForHelpToGetUnstuck` -- that is the entire point, since
the starved branches are what the change exists to make reachable -- and
`parseMessageBoxesFromUITreeRoot` is not narrowed, because narrowing treats the
instance and leaves the shape.

**Escape is safe here for the mission runner's reason**, and the reason is a
placement rather than a property of the key: a naked Escape can open the
client's own pause menu, and `closeSystemSettingsMenu` is the entry *before*
this one in `generalSetupInUserInterface`, which answers with its head. That
ordering is read out of saxrat's own source rather than assumed from the other
bot's.

Nothing here reads a live game client or drives a bot. One case reads the
recorded saxrat runs and only reads them; it skips with a stated reason on a
machine that has none, which is the answer an absent piece of *evidence* gets
rather than the one an absent toolchain does.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl, recorded_runs
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, label, node, source_of,
    tree_with)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")
SAXRAT_PARSER = os.path.join(
    os.path.dirname(SAXRAT_BOT_ELM), "EveOnline", "ParseUserInterface.elm")

# The decision line the mission runner's `closeMessageBoxByDeclining` prints on
# every reading it answers a box, and the only thing run 30's log has 32,585 of.
# saxrat's copy prints the same sentence, which is what lets one reader count
# stretches in either bot's log.
DECLINE_LINE = "+ I see a message box to close"

# The mission runner's runs whose message boxes all closed, and the one whose
# did not. Quoted here because saxrat's own corpus has none at all.
RUNS_THAT_CLOSED_THEIR_BOXES = ("10", "22", "25", "26", "27")
THE_INCIDENT = "30"

# The mission runner's own starvation, in readings.
RUN_30_READINGS_HELD = 32585


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and the comments here name the
    branches deliberately not taken -- the give-up's whole body is a `Nothing`
    and several lines of argument for it.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(name, path=SAXRAT_BOT_ELM):
    return collapsed(without_comments(body_of(source_of(path), name)))


def declaration_with_comments(name, path=SAXRAT_BOT_ELM):
    return collapsed(body_of(source_of(path), name))


def doc_comment(name, path=SAXRAT_BOT_ELM):
    """The `{-| ... -}` block immediately above a declaration.

    `body_of` starts at the type annotation, so a case about what a doc comment
    argues -- which is where this repo keeps the argument for a placement --
    cannot use it. The block has to be adjacent, or it belongs to something
    else and reading it here would attribute the wrong prose.
    """
    source = source_of(path)
    at = re.search(r"^%s :" % re.escape(name), source, re.MULTILINE).start()
    before = source[:at]
    closed = before.rindex("-}")
    assert before[closed + 2:].strip() == "", (
        "no doc comment sits immediately above %s" % name)
    return collapsed(before[before.rindex("{-|", 0, closed):closed + 2])


def int_constant(name, path=SAXRAT_BOT_ELM):
    """A constant read out of `Bot.elm`, so a case tests the shipped number."""
    return int(re.search(r"\n%s =\s*(\d+)" % name,
                         "\n" + body_of(source_of(path), name)).group(1))


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def standoff(identity, readings):
    return "(Just { identity = %s, readings = %d })" % (
        elm_string(identity), readings)


def message_box_tree(texts, buttons, origin=(300, 200)):
    """A UI tree the real parser turns into one `MessageBox`.

    `buttons` are `(name, label)` pairs -- `name` is the button's `_name` dict
    entry or `None` for a button the client does not name, and `label` is what
    it renders. `origin` moves the whole widget without changing a word of it,
    which is what the region case needs.
    """
    left, top = origin
    texts_nodes = [
        label(text, (left + 10, top + 10 + index * 20, 200, 16))
        for index, text in enumerate(texts)]

    button_nodes = []
    for index, (name, text) in enumerate(buttons):
        entries = {} if name is None else {"_name": name}
        region = (left + 10 + index * 90, top + 120, 80, 24)
        button_nodes.append(node(
            "Button", entries,
            [label(text, (region[0] + 4, region[1] + 4, 70, 16))],
            region=region))

    group = node("ButtonGroup", {}, button_nodes,
                 region=(left + 10, top + 120, 300, 24))

    return node("MessageBox", {}, texts_nodes + [group],
                region=(left, top, 400, 200))


class TheCountIsAboutOneBoxTest(unittest.TestCase):
    """`messageBoxStandoffAfterReading`, over the states a session passes through.

    The count has to be per box. A global tally of dismissals accumulates across
    a session that legitimately closes many dialogs and reaches a give-up it
    should never reach -- the mission runner's recovered runs answer 175
    separate stretches of message box between them.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-msgbox-count-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _after(self, before, identity_now):
        return ("messageBoxStandoffAfterReading "
                "{ before = %s, identityNow = %s }"
                % (before,
                   "Nothing" if identity_now is None
                   else "(Just %s)" % elm_string(identity_now)))

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
        # The reset that keeps the count about *this* box. Without it a session
        # answering dialog after dialog accumulates towards a give-up between
        # them.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing"
                % self._after(standoff("a picker", 119), None)]),
            [True])

    def test_a_different_box_starts_over(self):
        # A session that answers two dialogs with no quiet reading between them
        # still starts each from 1. This is the case a bare "some box is open"
        # counter gets wrong.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just { identity = %s, readings = 1 }"
                % (self._after(standoff("a picker", 119), "something else"),
                   elm_string("something else"))]),
            [True])

    def test_the_count_only_rises_by_one_and_only_on_the_same_box(self):
        # A control row rides along, so a repl answering `True` to everything
        # cannot pass this.
        answers = self.repl.evaluate([
            "(%s |> Maybe.map .readings) == Just 2"
            % self._after(standoff("x", 1), "x"),
            "(%s |> Maybe.map .readings) == Just 1"
            % self._after(standoff("x", 1), "y"),
            "(%s |> Maybe.map .readings) == Just 1"
            % self._after("Nothing", "x"),
            "(%s |> Maybe.map .readings) == Just 3"
            % self._after(standoff("x", 1), "x"),
        ])
        self.assertEqual(answers, [True, True, True, False])

    def test_a_box_that_stays_reaches_the_give_up_and_no_further_state(self):
        # Folded, rather than asked at one number: the whole of the count's
        # behaviour over a standoff is that it rises by one per reading from
        # the first, so the give-up is reached on exactly the reading its own
        # name says.
        give_up = int_constant("messageBoxAnswersBeforeEscape") * 2
        folded = ("List.foldl (\\_ before -> messageBoxStandoffAfterReading"
                  " { before = before, identityNow = Just %s })"
                  " Nothing (List.range 1 %d)" % (elm_string("a picker"), give_up))
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.map .readings) == Just %d" % (folded, give_up),
                "messageBoxStandoffVerdict (%s) == LeaveTheMessageBoxAlone"
                % folded,
            ]),
            [True, True])


class TheLadderIsAnswerThenEscapeThenStopTest(unittest.TestCase):
    """`messageBoxStandoffVerdict`, at every boundary it has.

    The declining answer stays the default, Escape is the escalation this
    codebase already uses, and the give-up hands the tree back rather than
    answering forever.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-msgbox-ladder-")
        cls.answers_before_escape = int_constant("messageBoxAnswersBeforeEscape")
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
        # 44 readings is the mission runner's run 26 worst, and the whole point
        # of the number is that a dialog like that one is still answered
        # normally. Asserted at a fixed value as well as at the boundary,
        # because a boundary pair alone passes for any constant.
        self.assertGreater(self.answers_before_escape, 44)
        self.assertEqual(
            self.repl.evaluate([
                "%s == AnswerTheMessageBox" % self._verdict(44)]),
            [True])

    def test_escape_starts_exactly_at_the_threshold(self):
        answers = self.repl.evaluate([
            "%s == AnswerTheMessageBox"
            % self._verdict(self.answers_before_escape - 1),
            "%s == PressEscapeAtTheMessageBox"
            % self._verdict(self.answers_before_escape),
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
                "%s == LeaveTheMessageBoxAlone"
                % self._verdict(RUN_30_READINGS_HELD)]),
            [True])

    def test_escape_gets_as_long_as_the_answer_it_replaced(self):
        # Stated as a relation rather than as a second number, so retuning one
        # cannot silently leave the other where it was. Both halves are needed:
        # the value, and the *form* -- a bare `120` evaluates the same today and
        # is exactly the drift `routeAskGiveUpReadings` is written to prevent.
        self.assertEqual(
            self.repl.evaluate([
                "messageBoxStandoffGiveUpReadings"
                " == messageBoxAnswersBeforeEscape * 2"]),
            [True])
        self.assertIn(
            "messageBoxStandoffGiveUpReadings = messageBoxAnswersBeforeEscape * 2",
            declaration("messageBoxStandoffGiveUpReadings"),
            "the give-up has to be written as a multiple of the escalation, "
            "not as the number it currently comes to")


class TheBoxIsIdentifiedByWhatItSaysAndOffersTest(unittest.TestCase):
    """`messageBoxIdentity`, over boxes the **real parser** produced.

    The boxes here are built as UI trees and run through saxrat's own
    `EveOnline.ParseUserInterface`, which is also the evidence that its diverged
    copy exposes what the identity needs: a button's `_name` dict entry and its
    rendered label. It does -- `MessageBox.buttons` carries `uiNode` and
    `mainText`, and `getNameFromDictEntries` and `getAllContainedDisplayTexts`
    are both here. **No parser change was required.**
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-msgbox-identity-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _identity(self, name, texts, buttons, origin=(300, 200)):
        binding = SaxratRepl.reading_binding(
            name, [message_box_tree(texts, buttons, origin=origin)])
        return binding, (
            "(%s |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
            " |> Maybe.map messageBoxIdentity"
            " |> Maybe.withDefault %s)"
            % (name, elm_string("PARSED NO MESSAGE BOX")))

    def _identities(self, boxes):
        """One identity string per `(texts, buttons, origin)` triple."""
        definitions, expressions = [], []
        for index, box in enumerate(boxes):
            texts, buttons = box[0], box[1]
            origin = box[2] if len(box) > 2 else (300, 200)
            binding, expression = self._identity(
                "box%d" % index, texts, buttons, origin)
            definitions.append(binding)
            expressions.append(expression)
        answers = self.repl.strings(expressions, definitions)
        for answer in answers:
            self.assertNotEqual(
                answer, "PARSED NO MESSAGE BOX",
                "the real parser made no message box out of this tree, so "
                "nothing below is about the identity rule")
        return answers

    def test_it_names_the_box_by_what_it_says(self):
        identity, = self._identities([
            (["Really jettison this?"], [("no_dialog_button", "No")])])
        self.assertIn("Really jettison this?", identity)

    def test_it_carries_the_button_names_as_well_as_their_labels(self):
        # `no_dialog_button` is the one name this file relies on across client
        # languages, and a dialog offering it is a different dialog from one
        # offering an unnamed OK even where both render the same word.
        identity, = self._identities([
            (["Really jettison this?"], [("no_dialog_button", "No")])])
        self.assertIn("no_dialog_button", identity)
        self.assertIn("No", identity)

    def test_two_dialogs_saying_different_things_are_different_boxes(self):
        first, second = self._identities([
            (["Really jettison this?"], [("no_dialog_button", "No")]),
            (["Leave the fleet?"], [("no_dialog_button", "No")]),
        ])
        self.assertNotEqual(first, second)

    def test_two_dialogs_offering_different_buttons_are_different_boxes(self):
        # The labels are identical here, so only the `_name` separates them --
        # which is the half a parser that dropped `_name` would fail on, and
        # the reason the identity reads both.
        named, unnamed = self._identities([
            (["Are you sure?"], [("no_dialog_button", "OK")]),
            (["Are you sure?"], [(None, "OK")]),
        ])
        self.assertNotEqual(named, unnamed)

    def test_the_same_box_drawn_somewhere_else_is_the_same_box(self):
        # The property the whole count rests on, and the reason the display
        # region is deliberately not in the identity: a widget re-rendered
        # every reading can differ while looking identical, and an
        # exact-equality test over its region would then never accumulate at
        # all -- which is precisely the failure this bound exists to prevent.
        here, moved = self._identities([
            (["Really jettison this?"], [("no_dialog_button", "No")], (300, 200)),
            (["Really jettison this?"], [("no_dialog_button", "No")], (317, 204)),
        ])
        self.assertEqual(here, moved)

    def test_a_box_with_no_text_of_its_own_still_has_an_identity(self):
        # Run 30's box, as far as anyone can reconstruct it: a widget with a
        # `no_dialog_button` and, apparently, nothing to read. An identity that
        # came back empty for it would collapse every such box into one.
        identity, = self._identities([([], [("no_dialog_button", "No")])])
        self.assertIn("no_dialog_button", identity)
        self.assertNotEqual(identity.strip(), "")

    def test_the_identity_carries_no_coordinates(self):
        # Stated directly as well as by the moved-box case above, since a
        # region reaching the string by some other route would defeat the count
        # in exactly the same way.
        identity, = self._identities([
            (["Really jettison this?"], [("no_dialog_button", "No")],
             (317, 204))])
        for coordinate in ("317", "204"):
            self.assertNotIn(coordinate, identity)


class TheGiveUpNamesTheBoxAndWhatItTriedTest(unittest.TestCase):
    """`describeMessageBoxGivenUpOn`.

    32,585 identical `Dismiss it using No.` lines is what the mission runner's
    operator got, and `stall_watch.py` deduped them into a single alarm, so
    nothing escalated. saxrat rats unattended, so the one line it prints has to
    carry everything.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-msgbox-giveup-")
        cls.said = cls.repl.strings([
            "describeMessageBoxGivenUpOn %s"
            % elm_string("message box saying 'Really jettison this?' "
                         "with buttons [no_dialog_button=No]")])[0]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_box(self):
        self.assertIn("Really jettison this?", self.said)
        self.assertIn("no_dialog_button", self.said)

    def test_it_says_what_was_tried_and_how_long_for(self):
        # Both rungs, with their counts, so the line answers "what did you do
        # about it" rather than only "I gave up".
        self.assertIn("Escape", self.said)
        self.assertIn(str(int_constant("messageBoxAnswersBeforeEscape")),
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


class TheRuleIsWiredIntoTheTreeTest(unittest.TestCase):
    """That the bound above is what saxrat consults, and where.

    A rule no branch asks is a rule that cannot prevent anything, which is the
    shape #133 found in the pod recovery and the shape #138 is the cost of.
    """

    def test_the_box_branch_consults_the_verdict(self):
        self.assertIn("messageBoxStandoffVerdict standoff",
                      declaration("closeMessageBox"))

    def test_the_setup_list_passes_the_standoff_down(self):
        self.assertIn("closeMessageBox messageBoxStandoff",
                      declaration("generalSetupInUserInterface"))

    def test_the_root_reads_it_out_of_memory(self):
        self.assertIn(
            "generalSetupInUserInterface context.memory.messageBoxStandoff",
            declaration("anomalyBotDecisionRootBeforeApplyingSettings"))

    def test_giving_up_hands_the_rest_of_the_tree_back(self):
        # Not a wait and not an alarm. The whole cost of #101 was that nothing
        # below `generalSetupInUserInterface` ran, so the give-up has to answer
        # `Nothing` and let the branches with their own bounds -- the pod
        # recovery's above all -- reach them.
        body = declaration("closeMessageBox")
        self.assertIn("LeaveTheMessageBoxAlone -> Nothing", body)
        self.assertIn(
            "Maybe.andThen", body,
            "the branch must be able to answer Nothing for a reading that has "
            "a box in it")
        give_up_at = body.index("LeaveTheMessageBoxAlone ->")
        escape_at = body.index("PressEscapeAtTheMessageBox ->")
        self.assertNotIn(
            "askForHelpToGetUnstuck", body[give_up_at:escape_at],
            "the give-up must hand the tree back rather than raise an alarm -- "
            "an alarm leaves every starved branch exactly as starved")

    def test_the_declining_answer_is_still_the_default(self):
        # Every reading below the escalation goes to the same place it always
        # went, which is what keeps the automatic reply the declining one.
        body = declaration("closeMessageBox")
        answer_at = body.index("AnswerTheMessageBox ->")
        self.assertIn("closeMessageBoxByDeclining messageBox", body[answer_at:])

    def test_the_declining_path_still_contains_no_affirmative(self):
        body = declaration_with_comments("closeMessageBoxByDeclining")
        self.assertNotIn("yes_dialog_button", body)
        self.assertIn('namedButton "no_dialog_button"', body)

    def test_the_escalation_is_escape_and_not_a_click(self):
        # Escape is what `clearStrayContextMenu` already presses at a menu that
        # has not advanced, and it needs no focus. A click would be a click into
        # a dialog nobody has read, which is the one thing the declining path
        # refuses to do.
        body = declaration("closeMessageBox")
        escape_at = body.index("PressEscapeAtTheMessageBox ->")
        answer_at = body.index("AnswerTheMessageBox ->")
        rung = body[escape_at:answer_at]
        self.assertIn("EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE", rung)
        self.assertNotIn("mouseClickOnUIElement", rung)

    def test_the_standoff_is_written_where_memory_is_written(self):
        # The decision tree cannot write memory, and the branch that would keep
        # the count is precisely the branch that stops running when the count
        # reaches its bound.
        body = declaration("updateMemoryForNewReadingFromGame")
        self.assertIn("messageBoxStandoff = messageBoxStandoffAfterReading", body)
        self.assertIn("Maybe.map messageBoxIdentity", body)

    def test_the_counter_advances_on_every_reading_that_has_a_box(self):
        # No reference to what the bot managed to do with the reading: this is
        # elapsed readings with a box in front of the bot, which is what the
        # bound is about. A clock that stopped while the tree was held is not a
        # clock.
        body = declaration("updateMemoryForNewReadingFromGame")
        clause = body[body.index("messageBoxStandoff = "):]
        clause = clause[:clause.index("messageBoxLastChange =")]
        self.assertNotIn("previousStepsEffects", clause)

    def test_the_give_up_is_announced_once_at_the_root(self):
        # `lockRangeLastChange`'s mechanism: a field holding a sentence only on
        # the reading its conclusion changed, folded in at the root, because
        # the branch that would otherwise say so is the branch that has just
        # stopped running.
        self.assertIn("context.memory.messageBoxLastChange",
                      declaration("anomalyBotDecisionRoot"))
        self.assertIn("describeMessageBoxGivenUpOn",
                      declaration("updateMemoryForNewReadingFromGame"))

    def test_the_status_line_keeps_saying_it_after_the_branch_goes_quiet(self):
        # Once the give-up is reached `closeMessageBox` prints no decision line
        # at all, so the status line is the only place a reading says a box is
        # still sitting in front of the bot.
        #
        # The *form* is read, not just the names. A clause that still mentions
        # the memory field while answering `Nothing` for every standoff prints
        # nothing and satisfies any substring test -- that mutation survived the
        # first run of this file, and it is the same one PR #109 found on the
        # mission runner's equivalent.
        body = declaration("statusTextFromState")
        self.assertIn("case context.memory.messageBoxStandoff of", body)
        self.assertIn("messageBoxStandoffVerdict (Just standoff)", body)
        self.assertIn("String.fromInt standoff.readings", body)
        self.assertIn("String.fromInt messageBoxStandoffGiveUpReadings", body)
        self.assertIn("GIVEN UP ON", body)

    def test_the_parser_still_matches_every_message_box(self):
        # Explicitly *not* the fix. Narrowing this treats one window and leaves
        # the shape: anything on that widget the declining answer does not close
        # reproduces run 30 exactly.
        self.assertIn(
            '.pythonObjectTypeName >> (==) "MessageBox"',
            declaration("parseMessageBoxesFromUITreeRoot", SAXRAT_PARSER),
            "the message-box parser is deliberately unchanged by #138")


class EscapeIsSafeInSaxratsOwnOrderingTest(unittest.TestCase):
    """The pause-menu risk, answered out of saxrat's source rather than the
    mission runner's.

    A naked Escape can open the client's own Settings/pause menu --
    `closeSystemSettingsMenu` records that happening live, in this very file,
    from exactly this key. What makes the escalation safe is not a property of
    the key but a placement: that branch is the entry *before* this one in
    `generalSetupInUserInterface`, and the list answers with its head, so a
    pause menu opened on one reading is closed on the next by the branch that
    exists for it. Both halves are checked, because either alone is not the
    argument.
    """

    def setUp(self):
        self.body = declaration("generalSetupInUserInterface")

    def test_the_pause_menu_branch_is_asked_before_the_message_box(self):
        self.assertLess(
            self.body.index("closeSystemSettingsMenu"),
            self.body.index("closeMessageBox"),
            "Escape's pause-menu risk is covered by the entry before this one; "
            "reordering the list uncovers it")

    def test_the_list_answers_with_its_head(self):
        # `List.head` after a `filterMap` is what makes "before" mean anything:
        # under any other resolution the earlier entry is not preferred and the
        # ordering above is decoration.
        self.assertIn("List.filterMap", self.body)
        self.assertIn("List.head", self.body)

    def test_the_pause_menu_branch_is_the_one_that_recovers_from_escape(self):
        # It has to be the branch that actually closes that menu, not merely
        # something sitting in front. Read out of its own body.
        recovery = declaration_with_comments("closeSystemSettingsMenu")
        self.assertIn('"l_systemmenu"', recovery)
        self.assertIn('"closeMenuClick"', recovery)


class TheTwoBotsAgreeOnTheNumberTest(unittest.TestCase):
    """The constants, compared across the two apps.

    60 is not saxrat's measurement -- see below, its corpus has no message box
    at all -- so it is the mission runner's, and a retune of one that leaves the
    other behind is the drift this catches. The same goes for the give-up being
    a multiple rather than a number.
    """

    def test_the_escalation_is_the_same_in_both(self):
        self.assertEqual(
            int_constant("messageBoxAnswersBeforeEscape"),
            int_constant("messageBoxAnswersBeforeEscape",
                         MISSION_RUNNER_BOT_ELM),
            "saxrat's escalation rests on the mission runner's corpus, so the "
            "two have to be the same number")

    def test_the_give_up_is_a_multiple_in_both(self):
        for path in (SAXRAT_BOT_ELM, MISSION_RUNNER_BOT_ELM):
            self.assertIn(
                "messageBoxStandoffGiveUpReadings = "
                "messageBoxAnswersBeforeEscape * 2",
                declaration("messageBoxStandoffGiveUpReadings", path))

    def test_saxrats_doc_comment_no_longer_says_the_bound_is_absent(self):
        # PR #137 left a paragraph in `endSessionOnAnExpiredBound` recording
        # that none of this existed here. It is the argument for the hoist it
        # sits under, so leaving it stale would leave the wrong reason attached
        # to a bound somebody may later move.
        argument = doc_comment("endSessionOnAnExpiredBound")
        self.assertNotIn("None of it was ported", argument)
        self.assertNotIn("counts nothing at all", argument)
        self.assertIn("messageBoxStandoffGiveUpReadings", argument)


class TheRecordedSaxratRunsCannotSizeThisBoundTest(unittest.TestCase):
    """The three recorded saxrat runs, asked to size the threshold -- which they
    cannot, and the silence is what is checked.

    Asserted as *relations* rather than counts, so a corpus that grows cannot
    turn a true claim red.
    """

    @classmethod
    def setUpClass(cls):
        logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
                for number in (1, 2, 3)]
        logs = [path for path in logs if os.path.exists(path)]
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "can say about this bound cannot be consulted here")

        cls.status_lines = cls.boxes = 0
        for path in logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "Approaching ticks:" in line:
                        cls.status_lines += 1
                    if line.startswith(DECLINE_LINE) or "Dismiss it using" in line:
                        cls.boxes += 1

    def test_the_memory_update_printed_throughout(self):
        # The positive control the silence below needs: the status line is
        # written from the memory update on every reading, so a corpus with
        # plenty of them is a corpus in which a message box would have shown.
        self.assertGreater(
            self.status_lines,
            int_constant("messageBoxAnswersBeforeEscape") * 100,
            "the recorded saxrat runs are too short to say anything about a "
            "bound of this size")

    def test_no_recorded_saxrat_run_has_ever_met_a_message_box(self):
        # So the escalation cannot be placed against anything saxrat has been
        # watched doing, and 60 rests on the mission runner's corpus instead.
        # Stated as a checked claim so it cannot quietly become false: the day
        # a saxrat run dismisses one, this file should be measuring it.
        self.assertEqual(
            self.boxes, 0,
            "a recorded saxrat run dismissed a message box, so the corpus can "
            "now say something about how long one holds this tree and the "
            "threshold should be placed against it rather than imported")


class TheMissionRunnersCorpusIsWhatSizesThisBoundTest(unittest.TestCase):
    """The corpus the threshold actually rests on, recounted.

    Numbers rather than relations would go red as the corpus grows. What is
    asserted is the separation: every stretch of message box in a mission-runner
    run that recovered is below the escalation, and run 30's is far above the
    give-up. The two bots meet the same client through the same parser, which is
    what makes that measurement transfer.
    """

    def test_every_box_that_ever_closed_closed_before_the_escalation(self):
        escalate_at = int_constant("messageBoxAnswersBeforeEscape")
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
            worst, 0, "no recorded message box at all, so this proves nothing")

    def test_run_thirty_is_far_past_the_give_up(self):
        give_up = int_constant("messageBoxAnswersBeforeEscape") * 2
        (name, path), = recorded_runs(THE_INCIDENT)
        streaks = box_streaks(path)
        self.assertTrue(streaks, "run %s carries no message box at all" % name)
        self.assertGreater(max(streaks), give_up * 10)

    def test_the_two_parsers_match_the_same_widget(self):
        # What makes the mission runner's measurement a measurement about *this*
        # client rather than about that bot: the same filter, in both vendored
        # copies, so a window that is a message box there is one here.
        mission_runner_parser = os.path.join(
            os.path.dirname(MISSION_RUNNER_BOT_ELM), "EveOnline",
            "ParseUserInterface.elm")
        self.assertEqual(
            declaration("parseMessageBoxesFromUITreeRoot", SAXRAT_PARSER),
            declaration("parseMessageBoxesFromUITreeRoot",
                        mission_runner_parser),
            "the two apps' message-box parsers have diverged, so the mission "
            "runner's corpus no longer sizes saxrat's bound")


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


if __name__ == "__main__":
    unittest.main()
