"""Tests for wingman giving up on a message box its answer does not close.

Issue #402, which is the mission runner's #101 and saxrat's #138 in a third
file. `closeMessageBox` here had no counter, no bound and no give-up: it
accepted only a button whose label lower-cases to `close` or `ok`, clicked it
identically on the first reading and the thirty-thousandth, and sent everything
else to `askForHelpToGetUnstuck` -- a leaf that dispatches nothing.
`generalSetupInUserInterface` is evaluated above the docked-or-in-space split,
so either way **an unrecognised dialog owned every reading for the rest of the
session**. Observed live on 2026-08-28: a 400-line scrollback holding nothing
but those three sentences.

## Three pieces, not the two the issue describes

**Naming the box** is #164's lesson, and it is the cheap half: nothing in this
bot ever printed a dialog's own words, so the window that cost that session
cannot be identified from its log. `messageBoxIdentity` and
`messageBoxIdentityForOperator` are ported, and every line that mentions a box
now names it -- the give-up, the status clause on every counted reading, and the
ask-for-help the answer set still falls through to.

**The ladder** is #109's shape: the ordinary declining answer for
`messageBoxAnswersBeforeEscape` readings, then Escape at the same box for
another, then `Nothing` so the rest of the tree runs with the box still on the
screen.

**`closeSystemSettingsMenu` is the third**, and it is a prerequisite rather than
a tidy-up. Wingman had no such branch at all -- the only occurrence of that
identifier in the whole file was a doc-comment reference in
`clearStrayContextMenu`, which presses Escape and says that branch "exists
because that happened live". Both siblings have it as the **first** entry of
their setup list ahead of `closeMessageBox`, and #109's own argument is that
Escape is safe *because of that placement*: a naked Escape can open the client's
own pause menu, and that branch is what closes it. Porting the Escape rung
without it would have traded a bounded message-box standoff for an unbounded
pause menu -- a different session-owning state, arrived at by the fix.

## The answer set, and what is deliberately not in it

The operator's own note on #402 names three buttons: `Close` for informational
popups, `No` for dangerous actions, `Ok` for "cannot warp to a fleet member who
is not in system". Two were already matched; `No` is the addition, and it is
**consistent** with #54's standing rule rather than a departure from it -- the
declining answer is the one a bot that has not read the dialog may give. No
affirmative is anywhere in the automatic path, which two cases pin: one by
executing the branch against a box offering only `Yes`, one by reading the
source.

**The window's own close ('X') control is not a rung**, though both siblings
have it as their last one. saxrat run 22 lost its client to exactly that on the
Connection Lost modal, and the operator's note says the box seen here was a
"client disconnected" one -- so that shape is what this bot is known to meet.
`messageBoxSaysTheConnectionIsLost` is ported with it, because Escape at a modal
whose only action is Quit is the same keypress by another route.

## What is unverified, and these cases cannot close it

**Any of it running.** No wingman run has been recorded on the machine these
cases run on, so there is no corpus of this bot's own message boxes at all --
the bound's size rests on the mission runner's, which is asserted here as a
relation where that corpus is present and skipped where it is not.

**What Greta's dialog was.** It is still unknown, which is defect 1 and the
reason the identity is now printed on every counted reading rather than only at
the give-up.

**Whether Escape closes a window the answer does not.** Its whole live outing
across both siblings is one press (#164), so this rung is as unproven here as it
is there. What the give-up needs is readings spent, which the rung supplies
whether or not the key works.

**The fleet-invite branch is still unbounded**, deliberately left alone by
#402 and recorded by a case below rather than left to be discovered.

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

from prerequisites import ElmRepl, open_repl, recorded_runs  # noqa: E402
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    label, node, reading_binding, tree_with)

APPS_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online")
WINGMAN_DIR = os.path.join(APPS_DIR, "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")
WINGMAN_PARSER = os.path.join(
    WINGMAN_DIR, "EveOnline", "ParseUserInterface.elm")
SAXRAT_BOT_ELM = os.path.join(APPS_DIR, "eve-online-saxrat", "Bot.elm")
MISSION_RUNNER_BOT_ELM = os.path.join(
    APPS_DIR, "eve-online-mission-runner", "Bot.elm")

# The mission runner's runs whose message boxes all closed, and the one whose
# did not. Quoted because wingman's own corpus does not exist.
RUNS_THAT_CLOSED_THEIR_BOXES = ("10", "22", "25", "26", "27")
THE_INCIDENT = "30"

# The decision line every one of the three bots prints on a reading it answers a
# box, and the only thing run 30's log has 32,585 of.
DECLINE_LINE = "+ I see a message box to close"

# The client's own Connection Lost modal, as saxrat run 22 recorded it. `Quit`
# first because it is a button label and the identity joins display texts in
# order.
CONNECTION_LOST = [
    "Quit",
    "Connection Lost",
    "Connection to server was lost.<br>",
]


def bot_source(path=WINGMAN_BOT_ELM):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break a case.

    #58's reformatting broke three assertions written against exact
    indentation; every source-reading case here goes through this.
    """
    return " ".join(text.split())


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code it sits above, and the comments here
    name the very branches those cases assert are not taken -- the give-up's
    whole body is a `Nothing` and several lines of argument for it.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(name, path=WINGMAN_BOT_ELM):
    """One top-level declaration, from its type annotation to the next gap."""
    source = bot_source(path)
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return collapsed(without_comments(rest[:rest.index("\n\n\n")]))


def declaration_with_comments(name, path=WINGMAN_BOT_ELM):
    source = bot_source(path)
    start = source.index("\n%s :" % name)
    rest = source[start + 1:]
    return collapsed(rest[:rest.index("\n\n\n")])


def int_constant(name, path=WINGMAN_BOT_ELM):
    """A constant read out of `Bot.elm`, so a case tests the shipped number."""
    body = declaration(name, path)
    return int(re.search(r"%s = (\d+)" % name, body).group(1))


def indented_let_binding(source, name):
    """One `let` binding, sliced by indentation rather than by the next name.

    A reader that ends at the next ` <name> = ` stops at a record literal, and
    the bindings read here build records and `case` expressions -- PRs #147,
    #156, #159 and #162 each paid for that once with an assertion that passed
    having read nothing.
    """
    match = re.search(r"\n(\s+)%s =\n" % re.escape(name), source)
    assert match is not None, "no let binding named %r" % name
    indent = len(match.group(1))
    kept = []
    for line in source[match.end():].split("\n"):
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        kept.append(line)
    return collapsed(re.sub(r"--[^\n]*", "", "\n".join(kept)))


def readers_of(name, path=WINGMAN_BOT_ELM):
    """Every top-level declaration whose body names `name`, bar its own."""
    source = bot_source(path)
    declared = re.findall(r"^([a-z]\w*) :", source, re.MULTILINE)
    found = []
    for other in declared:
        if other == name:
            continue
        start = source.index("\n%s :" % other)
        rest = source[start + 1:]
        # The last declaration in the file has no trailing gap to stop at.
        end = rest.find("\n\n\n")
        body = without_comments(rest if end < 0 else rest[:end])
        if re.search(r"\b%s\b" % re.escape(name), body):
            found.append(other)
    return found


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
    text_nodes = [
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

    return node("MessageBox", {}, text_nodes + [group],
                region=(left, top, 400, 200))


def box_streaks(log_path):
    """Lengths of every run of consecutive readings holding a message box.

    Counted in *readings* -- the `# [tick.substep]` boundary -- and not in
    decision lines, for the reason `stall_watch.py` has a section on.
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


class WingmanRepl(ElmRepl):
    """The wingman's own `Bot.elm`, answering for itself.

    The bindings are folded into the one entry that asks a question (#172), so
    what they cost is a compile rather than one each.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import Common.DecisionPath",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
    )

    BINDINGS = (
        "describeDecision = \\n -> n"
        " |> Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf"
        ' |> Tuple.first |> String.join " | "',
        # `FELL THROUGH` is a sentence no branch produces, so it reads as the
        # branch answering `Nothing` rather than as some decision this file
        # failed to anticipate. `THE FIXTURE NEVER ARRIVED` separates that from
        # a reading the parser never got -- #174's failure, where those two are
        # otherwise the same answer.
        "boxOf = \\parsed -> parsed"
        " |> Maybe.andThen (.messageBoxes >> List.head)",
        "answerFor = \\parsed -> boxOf parsed"
        " |> Maybe.map (closeMessageBoxByDeclining >> describeDecision)"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "branchFor = \\st -> \\parsed -> parsed"
        " |> Maybe.map (\\p -> closeMessageBox st p"
        '     |> Maybe.map describeDecision |> Maybe.withDefault "FELL THROUGH")'
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "identityOf = \\parsed -> boxOf parsed"
        " |> Maybe.map messageBoxIdentity"
        ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"',
        "verdictForBoxOf = \\st -> \\parsed -> boxOf parsed"
        " |> Maybe.map (messageBoxStandoffVerdictForBox st)",
        "connectionLostOf = \\parsed -> boxOf parsed"
        " |> Maybe.map messageBoxSaysTheConnectionIsLost",
        "after = \\before -> \\identityNow ->"
        " messageBoxStandoffAfterReading"
        " { before = before, identityNow = identityNow }",
        # The shipped `updateMemoryForNewReadingFromGame`, folded over real
        # readings, so "the counter advances on every reading a box is up" is
        # run rather than read. `-1` where any fixture never arrived, so a
        # broken fixture cannot read as a session that counted nothing.
        "memoryOver = \\readings ->"
        " if List.any ((==) Nothing) readings then"
        " { initBotMemory | messageBoxStandoff ="
        '     Just { identity = "THE FIXTURE NEVER ARRIVED", readings = -1 } }'
        " else (readings |> List.filterMap identity |> List.foldl (\\r -> \\m ->"
        " updateMemoryForNewReadingFromGame"
        " { timeInMilliseconds = 0, readingFromGameClient = r"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , botSettings = defaultBotSettings, previousStepsEffects = [] } m) initBotMemory)",
        "standoffOver = \\readings -> (memoryOver readings).messageBoxStandoff"
        ' |> Maybe.map (\\s -> s.identity ++ ":" ++ String.fromInt s.readings)'
        ' |> Maybe.withDefault "-"',
        "lastChangeOver = \\readings ->"
        ' (memoryOver readings).messageBoxLastChange |> Maybe.withDefault "-"',
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-message-box-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


#: Boxes built once, as `let`-free bindings the repl can be handed.
A_PICKER = reading_binding(
    "aPicker", [message_box_tree(["Really jettison this?"],
                                [("no_dialog_button", "No")])])
A_PICKER_MOVED = reading_binding(
    "aPickerMoved", [message_box_tree(["Really jettison this?"],
                                      [("no_dialog_button", "No")],
                                      origin=(317, 204))])
SAYS_SOMETHING_ELSE = reading_binding(
    "saysSomethingElse", [message_box_tree(["Leave the fleet?"],
                                           [("no_dialog_button", "No")])])
NAMED_OK = reading_binding(
    "namedOk", [message_box_tree(["Are you sure?"],
                                 [("no_dialog_button", "OK")])])
UNNAMED_OK = reading_binding(
    "unnamedOk", [message_box_tree(["Are you sure?"], [(None, "OK")])])
NO_TEXT_AT_ALL = reading_binding(
    "noTextAtAll", [message_box_tree([], [("no_dialog_button", "No")])])
INFORMATIONAL = reading_binding(
    "informational", [message_box_tree(
        ["Notification", "Your ship has been repaired."], [(None, "Close")])])
CANNOT_WARP = reading_binding(
    "cannotWarp", [message_box_tree(
        ["Cannot warp to a fleet member who is not in this system."],
        [(None, "Ok")])])
DANGEROUS = reading_binding(
    "dangerous", [message_box_tree(
        ["Warning", "Are you sure you want to undock?"],
        [("no_dialog_button", "No"), ("yes_dialog_button", "Yes")])])
DECLINING_UNNAMED = reading_binding(
    "decliningUnnamed", [message_box_tree(
        ["Really do that?"], [(None, "No"), (None, "Yes")])])
ONLY_AFFIRMATIVE = reading_binding(
    "onlyAffirmative", [message_box_tree(
        ["Some window nobody has read"], [("yes_dialog_button", "Yes")])])
CONNECTION_LOST_BOX = reading_binding(
    "connectionLost", [message_box_tree(CONNECTION_LOST, [(None, "Quit")])])
HALF_THE_CONNECTION_WORDING = reading_binding(
    "halfTheWording", [message_box_tree(
        ["Connection Lost", "Reconnecting..."], [(None, "Close")])])
NO_BOX = reading_binding("noBox", [])

ALL_BOXES = [
    A_PICKER, A_PICKER_MOVED, SAYS_SOMETHING_ELSE, NAMED_OK, UNNAMED_OK,
    NO_TEXT_AT_ALL, INFORMATIONAL, CANNOT_WARP, DANGEROUS, DECLINING_UNNAMED,
    ONLY_AFFIRMATIVE, CONNECTION_LOST_BOX, HALF_THE_CONNECTION_WORDING, NO_BOX,
]


class TheLadderIsAnswerThenEscapeThenStop(unittest.TestCase):
    """`messageBoxStandoffVerdict`, at every boundary it has.

    The declining answer stays the default, Escape is the escalation this
    codebase already uses, and the give-up hands the tree back rather than
    answering forever.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
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
        self.assertEqual(
            self.repl.evaluate([
                "%s == AnswerTheMessageBox"
                % self._verdict(self.answers_before_escape - 1),
                "%s == PressEscapeAtTheMessageBox"
                % self._verdict(self.answers_before_escape),
            ]),
            [True, True])

    def test_the_give_up_starts_exactly_at_its_own_threshold(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == PressEscapeAtTheMessageBox" % self._verdict(self.give_up - 1),
                "%s == LeaveTheMessageBoxAlone" % self._verdict(self.give_up),
            ]),
            [True, True])

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
        # is exactly the drift this is written to prevent.
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


class TheCountIsAboutOneBox(unittest.TestCase):
    """`messageBoxStandoffAfterReading`, over the states a session passes
    through.

    The count has to be per box. A global tally of dismissals accumulates
    across a session that legitimately closes many dialogs and reaches a
    give-up it should never reach.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _after(self, before, identity_now):
        return "after %s %s" % (
            before,
            "Nothing" if identity_now is None
            else "(Just %s)" % elm_string(identity_now))

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
                "%s == Nothing" % self._after(standoff("a picker", 119), None)]),
            [True])

    def test_a_different_box_starts_over(self):
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
        # Folded rather than asked at one number: the whole of the count's
        # behaviour over a standoff is that it rises by one per reading from the
        # first, so the give-up is reached on exactly the reading its own name
        # says.
        give_up = int_constant("messageBoxAnswersBeforeEscape") * 2
        folded = ("List.foldl (\\_ before -> after before (Just %s))"
                  " Nothing (List.range 1 %d)"
                  % (elm_string("a picker"), give_up))
        self.assertEqual(
            self.repl.evaluate([
                "(%s |> Maybe.map .readings) == Just %d" % (folded, give_up),
                "messageBoxStandoffVerdict (%s) == LeaveTheMessageBoxAlone"
                % folded,
                "messageBoxStandoffVerdict (%s) == PressEscapeAtTheMessageBox"
                % folded.replace("(List.range 1 %d)" % give_up,
                                 "(List.range 1 %d)" % (give_up - 1)),
            ]),
            [True, True, True])


class TheRealMemoryUpdateCountsTheBox(unittest.TestCase):
    """The counter, folded through the shipped
    `updateMemoryForNewReadingFromGame` over really-parsed readings.

    `TheCountIsAboutOneBox` above asks the pure rule; this asks the memory
    update that feeds it, which is the half that can be wired to the wrong
    question. **None of these readings carries a ship UI**, so a counter that
    quietly stopped on a reading it could not see the ship on -- which is every
    docked reading, and exactly the readings a box holding the tree would be
    taken on -- reads `-` here rather than a count.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _over(self, names):
        return "standoffOver [ %s ]" % ", ".join(names)

    def test_the_same_box_on_five_readings_counts_five(self):
        said, = self.repl.strings(
            [self._over(["aPicker"] * 5)], ALL_BOXES)
        self.assertNotEqual(said, "THE FIXTURE NEVER ARRIVED:-1")
        self.assertTrue(
            said.endswith(":5"),
            "five readings of one box counted %r" % said)
        self.assertIn("Really jettison this?", said)

    def test_a_reading_with_no_box_ends_it(self):
        said, = self.repl.strings(
            [self._over(["aPicker", "aPicker", "noBox", "aPicker"])], ALL_BOXES)
        self.assertTrue(said.endswith(":1"), said)

    def test_a_different_box_starts_over(self):
        said, = self.repl.strings(
            [self._over(["aPicker", "aPicker", "saysSomethingElse"])],
            ALL_BOXES)
        self.assertTrue(said.endswith(":1"), said)
        self.assertIn("Leave the fleet?", said)

    def test_a_session_that_never_sees_one_counts_nothing(self):
        # The control: a rule that answered a count for everything would pass
        # every case above.
        said, = self.repl.strings([self._over(["noBox", "noBox"])], ALL_BOXES)
        self.assertEqual(said, "-")

    def test_the_give_up_is_said_once_on_the_reading_it_is_reached(self):
        give_up = int_constant("messageBoxAnswersBeforeEscape") * 2
        quiet, crossing, after = self.repl.strings([
            "lastChangeOver (List.repeat %d aPicker)" % (give_up - 1),
            "lastChangeOver (List.repeat %d aPicker)" % give_up,
            "lastChangeOver (List.repeat %d aPicker)" % (give_up + 1),
        ], ALL_BOXES)
        self.assertEqual(quiet, "-")
        self.assertIn("Really jettison this?", crossing)
        self.assertIn("by hand", crossing)
        self.assertEqual(
            after, "-",
            "the give-up is said on the one reading the bound is crossed and "
            "on no other")


class TheBoxIsIdentifiedByWhatItSaysAndOffers(unittest.TestCase):
    """`messageBoxIdentity`, over boxes the **real parser** produced.

    The boxes are built as UI trees and run through wingman's own
    `EveOnline.ParseUserInterface`, which is also the evidence that its copy
    exposes what the identity needs: a button's `_name` dict entry and its
    rendered label. **No parser change was required for this half.**
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.answers = cls.repl.strings(
            ["identityOf %s" % name for name in
             ("aPicker", "aPickerMoved", "saysSomethingElse", "namedOk",
              "unnamedOk", "noTextAtAll")],
            [A_PICKER, A_PICKER_MOVED, SAYS_SOMETHING_ELSE, NAMED_OK,
             UNNAMED_OK, NO_TEXT_AT_ALL])
        (cls.picker, cls.moved, cls.other, cls.named, cls.unnamed,
         cls.no_text) = cls.answers

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_reached_the_parser(self):
        # #174: a fixture that never arrived and a rule that answered nothing
        # are the same answer from outside, so this is asked before anything
        # below rests on one.
        for answer in self.answers:
            self.assertNotEqual(answer, "THE FIXTURE NEVER ARRIVED")

    def test_it_names_the_box_by_what_it_says(self):
        self.assertIn("Really jettison this?", self.picker)

    def test_it_carries_the_button_names_as_well_as_their_labels(self):
        self.assertIn("no_dialog_button", self.picker)
        self.assertIn("No", self.picker)

    def test_two_dialogs_saying_different_things_are_different_boxes(self):
        self.assertNotEqual(self.picker, self.other)

    def test_two_dialogs_offering_different_buttons_are_different_boxes(self):
        # The labels are identical here, so only the `_name` separates them --
        # which is the half a parser that dropped `_name` would fail on, and the
        # reason the identity reads both.
        self.assertNotEqual(self.named, self.unnamed)

    def test_the_same_box_drawn_somewhere_else_is_the_same_box(self):
        # The property the whole count rests on, and the reason the display
        # region is deliberately not in the identity: a widget re-rendered every
        # reading can differ while looking identical, and an exact-equality test
        # over its region would then never accumulate at all.
        self.assertEqual(self.picker, self.moved)

    def test_a_box_with_no_text_of_its_own_still_has_an_identity(self):
        self.assertIn("no_dialog_button", self.no_text)
        self.assertNotEqual(self.no_text.strip(), "")

    def test_the_identity_carries_no_coordinates(self):
        for coordinate in ("317", "204"):
            self.assertNotIn(coordinate, self.moved)


class TheAnswerIsCloseOkOrNoAndNeverYes(unittest.TestCase):
    """`closeMessageBoxByDeclining`, executed against really-parsed boxes.

    The operator's own three buttons, and the affirmative that must never be
    clicked however the dialog is shaped.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        names = ("informational", "cannotWarp", "dangerous", "decliningUnnamed",
                 "onlyAffirmative")
        cls.answers = dict(zip(names, cls.repl.strings(
            ["answerFor %s" % name for name in names],
            [INFORMATIONAL, CANNOT_WARP, DANGEROUS, DECLINING_UNNAMED,
             ONLY_AFFIRMATIVE])))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_reached_the_parser(self):
        for answer in self.answers.values():
            self.assertNotEqual(answer, "THE FIXTURE NEVER ARRIVED")

    def test_an_informational_popup_is_closed(self):
        self.assertIn("Click on button 'Close'", self.answers["informational"])

    def test_the_cannot_warp_popup_is_answered_with_ok(self):
        self.assertIn("Click on button 'Ok'", self.answers["cannotWarp"])

    def test_a_dangerous_action_is_declined_by_the_named_button(self):
        # `no_dialog_button` is what the client names its declining button, and
        # this dialog offers `Yes` beside it.
        self.assertIn("Click on button 'No'", self.answers["dangerous"])
        self.assertNotIn("Yes", self.answers["dangerous"])

    def test_a_declining_button_the_client_did_not_name_is_still_taken(self):
        # The label rung, which is the half #402's operator note asked for: a
        # `No` the client gave no `_name`.
        self.assertIn("Click on button 'No'", self.answers["decliningUnnamed"])
        self.assertNotIn("Yes", self.answers["decliningUnnamed"])

    def test_a_box_offering_only_an_affirmative_is_not_clicked_at_all(self):
        # The whole of #54's rule, executed: the bot would rather ask for help
        # than press an affirmative it has not read.
        said = self.answers["onlyAffirmative"]
        self.assertIn("I see no way to close this message box", said)
        self.assertNotIn("Click on button", said)

    def test_the_ask_for_help_names_the_dialog(self):
        # Defect 1 of #402: that line carried no display texts and no button
        # names, so the dialog could not be identified from a 400-line
        # scrollback.
        said = self.answers["onlyAffirmative"]
        self.assertIn("Some window nobody has read", said)
        self.assertIn("yes_dialog_button", said)

    def test_the_declining_path_contains_no_affirmative(self):
        body = declaration_with_comments("closeMessageBoxByDeclining")
        self.assertNotIn("yes_dialog_button", body)
        self.assertNotIn('"yes"', body)
        self.assertIn('namedButton "no_dialog_button"', body)

    def test_it_does_not_click_the_window_s_own_close_control(self):
        # saxrat run 22 lost its client to exactly that on the Connection Lost
        # modal, and the operator's note says the box seen here was a "client
        # disconnected" one.
        self.assertNotIn(
            "parseWindowControlsFromWindow",
            declaration("closeMessageBoxByDeclining"))


class TheConnectionLostBoxIsNeverAnsweredOrEscaped(unittest.TestCase):
    """`messageBoxStandoffVerdictForBox`, and the one box every control quits.

    Escape at a modal whose only action is Quit is the same keypress by another
    route, so this is skipped at every rung rather than only at the first.
    `botlab_host.py` recognises the same box by the same two substrings and
    clicks the Quit itself.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.give_up = int_constant("messageBoxAnswersBeforeEscape") * 2

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_client_s_own_wording_is_recognised(self):
        answers = self.repl.evaluate(
            ["connectionLostOf connectionLost == Just True",
             "connectionLostOf halfTheWording == Just False",
             "connectionLostOf aPicker == Just False"],
            [CONNECTION_LOST_BOX, HALF_THE_CONNECTION_WORDING, A_PICKER])
        self.assertEqual(answers, [True, True, True])

    def test_it_is_left_alone_at_every_rung(self):
        rungs = ["Nothing",
                 standoff("x", 1),
                 standoff("x", int_constant("messageBoxAnswersBeforeEscape")),
                 standoff("x", self.give_up)]
        answers = self.repl.evaluate(
            ["verdictForBoxOf %s connectionLost == Just LeaveTheMessageBoxAlone"
             % rung for rung in rungs],
            [CONNECTION_LOST_BOX])
        self.assertEqual(answers, [True] * len(rungs))

    def test_an_ordinary_box_still_climbs_the_ladder(self):
        # The control. A rule that answered `LeaveTheMessageBoxAlone` for
        # everything would pass the case above and silence the whole branch.
        answers = self.repl.evaluate(
            ["verdictForBoxOf Nothing aPicker == Just AnswerTheMessageBox",
             "verdictForBoxOf %s aPicker == Just PressEscapeAtTheMessageBox"
             % standoff("x", int_constant("messageBoxAnswersBeforeEscape")),
             "verdictForBoxOf %s aPicker == Just LeaveTheMessageBoxAlone"
             % standoff("x", self.give_up)],
            [A_PICKER])
        self.assertEqual(answers, [True, True, True])

    def test_the_branch_answers_nothing_for_it_on_the_first_reading(self):
        said, = self.repl.strings(
            ["branchFor Nothing connectionLost"], [CONNECTION_LOST_BOX])
        self.assertEqual(said, "FELL THROUGH")


class TheBranchClimbsTheLadderItIsGiven(unittest.TestCase):
    """`closeMessageBox`, executed end to end over a really-parsed box."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        escalate_at = int_constant("messageBoxAnswersBeforeEscape")
        cls.answering, cls.escaping, cls.given_up, cls.quiet = cls.repl.strings(
            ["branchFor Nothing aPicker",
             "branchFor %s aPicker" % standoff("x", escalate_at),
             "branchFor %s aPicker" % standoff("x", escalate_at * 2),
             "branchFor Nothing noBox"],
            [A_PICKER, NO_BOX])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_ordinary_answer_is_the_first_rung(self):
        self.assertIn("I see a message box to close", self.answering)
        self.assertIn("Click on button 'No'", self.answering)

    def test_the_escalation_says_what_it_is_doing_and_for_how_long(self):
        self.assertIn("press Escape at it", self.escaping)
        self.assertIn(str(int_constant("messageBoxAnswersBeforeEscape")),
                      self.escaping)

    def test_the_give_up_hands_the_reading_back(self):
        # The whole of #402: `Nothing` is what lets the rest of the tree run.
        self.assertEqual(self.given_up, "FELL THROUGH")

    def test_a_reading_with_no_box_is_untouched(self):
        self.assertEqual(self.quiet, "FELL THROUGH")


class TheGiveUpNamesTheBoxAndWhatItTried(unittest.TestCase):
    """`describeMessageBoxGivenUpOn`."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.said, = cls.repl.strings([
            "describeMessageBoxGivenUpOn %s"
            % elm_string("message box saying 'Really jettison this?' "
                         "with buttons [no_dialog_button=No]")])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_it_names_the_box(self):
        self.assertIn("Really jettison this?", self.said)
        self.assertIn("no_dialog_button", self.said)

    def test_it_says_what_was_tried_and_how_long_for(self):
        self.assertIn("Escape", self.said)
        self.assertIn(str(int_constant("messageBoxAnswersBeforeEscape")),
                      self.said)

    def test_it_says_the_box_is_still_there_and_needs_a_person(self):
        self.assertIn("still there", self.said)
        self.assertIn("by hand", self.said)

    def test_a_long_dialog_does_not_run_away_with_the_line(self):
        long_identity = "message box saying '" + ("blah " * 200) + "'"
        said, = self.repl.strings(
            ["describeMessageBoxGivenUpOn %s" % elm_string(long_identity)])
        self.assertLess(len(said), len(long_identity))
        self.assertIn("...", said)
        self.assertIn("by hand", said)


class TheStatusClauseNamesTheBox(unittest.TestCase):
    """`describeMessageBoxStandoff`, executed rather than read.

    Once the give-up is reached `closeMessageBox` prints no decision line at
    all, so the status line is the only place a reading says a box is still
    sitting in front of the bot -- and #164's own lesson is that a standoff
    ending any *other* way leaves nothing that says what the window was.
    """

    IDENTITY = ("message box saying 'Really jettison this?' with buttons "
                "[no_dialog_button=No]")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        escalate_at = int_constant("messageBoxAnswersBeforeEscape")
        cls.quiet, cls.answering, cls.escaping, cls.given_up = cls.repl.strings([
            "describeMessageBoxStandoff Nothing",
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY, 1),
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY, escalate_at),
            "describeMessageBoxStandoff %s" % standoff(cls.IDENTITY,
                                                       escalate_at * 2),
        ])

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_reading_with_no_box_says_nothing(self):
        self.assertEqual(self.quiet, "")

    def test_every_rung_names_the_box(self):
        for rung in (self.answering, self.escaping, self.given_up):
            self.assertIn("Really jettison this?", rung)
            self.assertIn("no_dialog_button", rung)

    def test_every_rung_carries_the_count_against_the_bound(self):
        escalate_at = int_constant("messageBoxAnswersBeforeEscape")
        give_up_at = escalate_at * 2
        self.assertIn("1/%d" % give_up_at, self.answering)
        self.assertIn("%d/%d" % (escalate_at, give_up_at), self.escaping)
        self.assertIn("%d/%d" % (give_up_at, give_up_at), self.given_up)

    def test_it_says_which_rung_the_bot_is_on(self):
        self.assertIn("answering it", self.answering)
        self.assertIn("pressing Escape at it", self.escaping)
        self.assertIn("GIVEN UP ON, still open", self.given_up)

    def test_a_long_dialog_does_not_run_away_with_the_status_line(self):
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

    def test_nothing_decides_anything_on_the_clause(self):
        # It is a report. A branch that started reading it would be deciding on
        # a rendered string where the verdict it is derived from is one function
        # away.
        self.assertEqual(
            readers_of("describeMessageBoxStandoff"), ["statusTextFromState"],
            "the status clause is read somewhere other than the status line")


class TheRuleIsWiredIntoTheTree(unittest.TestCase):
    """That the bound above is what wingman consults, and where.

    A rule no branch asks is a rule that cannot prevent anything, which is the
    shape #402 is the cost of.
    """

    def test_the_box_branch_consults_the_verdict(self):
        self.assertIn("messageBoxStandoffVerdictForBox standoff messageBox",
                      declaration("closeMessageBox"))

    def test_the_setup_list_passes_the_standoff_down(self):
        self.assertIn("closeMessageBox context.memory.messageBoxStandoff",
                      declaration("generalSetupInUserInterface"))

    def test_giving_up_hands_the_rest_of_the_tree_back(self):
        # Not a wait and not an alarm. The whole cost of #402 was that nothing
        # below `generalSetupInUserInterface` ran, so the give-up has to answer
        # `Nothing` and let the branches below reach their own bounds.
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
        body = declaration("closeMessageBox")
        answer_at = body.index("AnswerTheMessageBox ->")
        self.assertIn("closeMessageBoxByDeclining messageBox", body[answer_at:])

    def test_the_escalation_is_escape_and_not_a_click(self):
        # Escape is what `clearStrayContextMenu` already presses at a menu that
        # has not advanced, and it needs no focus. A click would be a click into
        # a dialog nobody has read.
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
        clause = indented_let_binding(
            bot_source(), "messageBoxStandoff")
        self.assertIn("messageBoxStandoffAfterReading", clause)
        self.assertIn("Maybe.map messageBoxIdentity", clause)
        self.assertIn("messageBoxStandoff = messageBoxStandoff",
                      declaration("updateMemoryForNewReadingFromGame"))

    def test_the_counter_advances_on_every_reading_that_has_a_box(self):
        # No reference to what the bot managed to do with the reading: this is
        # elapsed readings with a box in front of the bot, which is what the
        # bound is about. A clock that stopped while the tree was held is not a
        # clock.
        clause = indented_let_binding(bot_source(), "messageBoxStandoff")
        for forbidden in ("previousStepsEffects", "shipUI", "memoryBefore."):
            self.assertNotIn(forbidden, clause)

    def test_the_counter_and_the_branch_ask_one_rule_about_the_reading(self):
        # #102's defect is a counter advanced by one condition and read by
        # another. Both halves here ask the same question -- "is a message box
        # the head of this reading's boxes" -- and the identity that answers it
        # is one function.
        clause = indented_let_binding(bot_source(), "messageBoxStandoff")
        self.assertIn(".messageBoxes |> List.head", clause)
        self.assertIn("messageBoxes |> List.head", declaration("closeMessageBox"))
        self.assertEqual(
            sorted(readers_of("messageBoxIdentity")),
            sorted(["closeMessageBoxByDeclining",
                    "updateMemoryForNewReadingFromGame"]),
            "the identity is derived somewhere other than the memory update "
            "and the line that names an unrecognised box")

    def test_the_give_up_is_announced_once_at_the_root(self):
        # A field holding a sentence only on the reading its conclusion changed,
        # folded in at the root, because the branch that would otherwise say so
        # is the branch that has just stopped running.
        self.assertIn("context.memory.messageBoxLastChange",
                      declaration("anomalyBotDecisionRoot"))
        change = indented_let_binding(bot_source(), "messageBoxLastChange")
        self.assertIn("describeMessageBoxGivenUpOn", change)
        self.assertIn("messageBoxStandoffGiveUpReadings <= now.readings", change)
        self.assertIn("before.readings < messageBoxStandoffGiveUpReadings",
                      change)

    def test_the_status_line_asks_the_rule_and_carries_no_second_copy(self):
        body = declaration("statusTextFromState")
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
        # Explicitly *not* the fix. Narrowing this treats one window and leaves
        # the shape: anything on that widget the answer does not close
        # reproduces the incident exactly.
        self.assertIn(
            '.pythonObjectTypeName >> (==) "MessageBox"',
            declaration("parseMessageBoxesFromUITreeRoot", WINGMAN_PARSER),
            "the message-box parser is deliberately unchanged by #402")


class EscapeIsSafeBecauseOfWhatRunsBeforeIt(unittest.TestCase):
    """The pause-menu risk, and the branch #402 had to port to cover it.

    A naked Escape can open the client's own Settings/pause menu. What makes the
    escalation safe is not a property of the key but a placement: the branch
    that closes that menu is the entry *before* this one in
    `generalSetupInUserInterface`, and the list answers with its head.

    **Wingman had no such branch**, which is the second of #402's own Unverified
    items and the answer is "no": the only occurrence of the identifier in the
    whole file was a doc-comment reference. Both siblings have it first.
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

    def test_the_parser_can_answer_the_lookup_that_branch_makes(self):
        # `getElementIdFromDictEntries` was absent from wingman's vendored
        # parser -- present in the mission runner's, saxrat's and the
        # haulerbot's. Without it the branch does not compile, which is the one
        # way this port could not have failed silently.
        self.assertIn(
            'getStringPropertyFromDictEntries "_elementId"',
            declaration("getElementIdFromDictEntries", WINGMAN_PARSER))

    def test_the_other_two_escape_presses_are_covered_by_it_too(self):
        # `clearStrayContextMenu`'s fallback presses Escape and its own comment
        # already named this branch as the reason that is risky. It was naming a
        # declaration that did not exist.
        source = bot_source()
        self.assertGreater(
            source.count("closeSystemSettingsMenu"), 1,
            "the branch is named in prose and nowhere in code, which is the "
            "state #402 found")
        self.assertIn("vkey_ESCAPE", declaration("clearStrayContextMenu"))


class TheFleetInviteBranchIsUntouchedAndStillUnbounded(unittest.TestCase):
    """What #402 deliberately did not change, recorded rather than left to be
    found.

    `acceptFleetInviteFromNamedPilot` answers the client's own "Join Fleet?"
    dialog, which falls through the Close/OK matcher, and it sits in the setup
    list *above* `closeMessageBox` as its own entry. It is the one exception to
    the declining rule this bot makes, and it is an operator's decision --
    gated on the sender being named in `accept-fleet-invite-from`, which
    defaults to nobody.

    **It carries no bound of its own.** An invitation from a named pilot whose
    Yes click never lands would own the tree exactly as the message box did.
    That is narrow -- it needs the setting armed and the click to fail -- and it
    is not what #402 is about, so it is recorded here so a later change has to
    argue against it rather than rediscover it.
    """

    def test_the_invite_branch_is_still_its_own_entry_above_the_message_box(self):
        body = declaration("generalSetupInUserInterface")
        self.assertLess(
            body.index("acceptFleetInviteFromNamedPilot"),
            body.index("closeMessageBox"))

    def test_it_still_reads_only_the_setting_it_always_did(self):
        body = declaration("acceptFleetInviteFromNamedPilot")
        self.assertIn(
            "List.member sender context.eventContext.botSettings"
            ".acceptFleetInviteFrom", body)
        self.assertIn('button.mainText == Just "Yes"', body)

    def test_it_consults_no_standoff_and_so_has_no_bound(self):
        body = declaration("acceptFleetInviteFromNamedPilot")
        self.assertNotIn("messageBoxStandoff", body)
        self.assertNotIn("MessageBoxStandoff", body)

    def test_the_declining_answer_now_refuses_such_an_invite_rather_than_stalling(self):
        # A consequence rather than a change: a "Join Fleet?" dialog from a
        # pilot nobody named used to reach `askForHelpToGetUnstuck` and own the
        # session. It is declined now, which is what the standing rule says an
        # unread dialog gets.
        repl = open_repl(WingmanRepl)
        try:
            invite = reading_binding("invite", [message_box_tree(
                ["Join Fleet?",
                 "Gal Bistot wants you to join their fleet, do you accept?"],
                [("yes_dialog_button", "Yes"), ("no_dialog_button", "No")])])
            said, = repl.strings(["answerFor invite"], [invite])
            self.assertIn("Click on button 'No'", said)
        finally:
            repl.close()


#: The declarations #402 ported rather than wrote. Every one of them is
#: byte for byte saxrat's, which is what "ported whole" has to mean if it is to
#: be checkable at all -- a port that drifts on arrival is a second
#: implementation nobody decided to have.
PORTED_WHOLE = (
    "closeSystemSettingsMenu",
    "messageBoxStandoffAfterReading",
    "messageBoxStandoffVerdict",
    "messageBoxStandoffVerdictForBox",
    "messageBoxSaysTheConnectionIsLost",
    "messageBoxIdentity",
    "messageBoxIdentityForOperator",
    "describeMessageBoxGivenUpOn",
    "messageBoxGiveUpIdentityLength",
)


class TheSharedRulesArePortedWhole(unittest.TestCase):
    """The ported declarations, compared with saxrat's byte for byte.

    Doc comments are excluded -- each argues from its own app's history -- so
    what is compared is the code. A third copy of a rule this repo already has
    two of is worth having only while the three agree; the day one has to
    diverge, this case is where somebody says so.
    """

    def test_every_ported_rule_is_saxrats(self):
        for name in PORTED_WHOLE:
            self.assertEqual(
                declaration(name), declaration(name, SAXRAT_BOT_ELM),
                "%s has drifted from saxrat's copy" % name)

    def test_the_status_clause_is_the_one_deliberate_difference(self):
        # wingman prints it on its own line in the status text, where saxrat
        # appends it inside one -- so saxrat's literal carries a leading space
        # and wingman's does not. That is the whole difference, and a case
        # rather than a comment because a third rendering is how the give-up
        # sentence and the status clause come to disagree about a box.
        mine = declaration("describeMessageBoxStandoff")
        theirs = declaration("describeMessageBoxStandoff", SAXRAT_BOT_ELM)
        self.assertNotEqual(mine, theirs)
        self.assertEqual(mine, theirs.replace('" Message box: "',
                                              '"Message box: "'))


class TheThreeBotsAgreeOnTheNumber(unittest.TestCase):
    """The constants, compared across the three apps.

    60 is not wingman's measurement -- its corpus does not exist -- so it is the
    mission runner's, and a retune of one that leaves the others behind is the
    drift this catches. The same goes for the give-up being a multiple rather
    than a number.
    """

    def test_the_escalation_is_the_same_in_all_three(self):
        for path in (SAXRAT_BOT_ELM, MISSION_RUNNER_BOT_ELM):
            self.assertEqual(
                int_constant("messageBoxAnswersBeforeEscape"),
                int_constant("messageBoxAnswersBeforeEscape", path),
                "wingman's escalation rests on the mission runner's corpus, so "
                "the three have to be the same number")

    def test_the_give_up_is_a_multiple_in_all_three(self):
        for path in (WINGMAN_BOT_ELM, SAXRAT_BOT_ELM, MISSION_RUNNER_BOT_ELM):
            self.assertIn(
                "messageBoxStandoffGiveUpReadings = "
                "messageBoxAnswersBeforeEscape * 2",
                declaration("messageBoxStandoffGiveUpReadings", path))


class TheMissionRunnersCorpusIsWhatSizesThisBound(unittest.TestCase):
    """The bound's size, recounted from the only corpus that can say.

    No wingman run has been recorded on the machine this was written on, so
    there is nothing here to place a threshold in and inventing a
    wingman-specific number would be inventing it. What transfers is a
    measurement about *the client* rather than about that bot: the same widget,
    matched by the same `pythonObjectTypeName` filter in both parsers.

    Asserted as relations rather than as numbers, so a corpus that grows cannot
    turn a true claim red.
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

    def test_the_incident_is_far_past_the_give_up(self):
        give_up = int_constant("messageBoxAnswersBeforeEscape") * 2
        (name, path), = recorded_runs(THE_INCIDENT)
        streaks = box_streaks(path)
        self.assertTrue(streaks, "run %s carries no message box at all" % name)
        self.assertGreater(max(streaks), give_up * 10)


if __name__ == "__main__":
    unittest.main()
