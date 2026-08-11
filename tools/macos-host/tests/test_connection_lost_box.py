"""The one dialog whose declining answer is the destructive one.

`closeMessageBoxByDeclining` promises that the automatic reply always declines,
because these dialogs guard destructive actions. EVE's Connection Lost modal
inverts that. It carries a single `Quit`, no `Close`/`OK` and no
`no_dialog_button`, so both recognising options miss and the answer falls
through to the third -- the window's own close control, meant for "a dialog
whose buttons we do not recognise at all".

saxrat run 22 lost its client to it six minutes into an eight-hour tour:

    12:28:31 (info) Network communication between your computer and the EVE
                    Online server has been interrupted.

    + I see a message box to close.
    ++ Dismiss it using the window's close button.

and then the log stops, with no client process and no EVE window left. Run 21
met the same box and sat at it for five hours instead, because the screen was
locked and no input could land -- the same defect with the input path removed.

`messageBoxStandoffVerdictForBox` answers `LeaveTheMessageBoxAlone` for this box
at every rung, so neither the click nor #138's Escape is dispatched. The cases
below execute both rules through the real `Bot.elm`, and the boxes they are
asked about are built by the **real** `EveOnline.ParseUserInterface` from a UI
tree, so what is asserted on is what the bot would have been handed.
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, ElmRepl, open_repl
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
from test_saxrat_message_box_standoff import (
    MISSION_RUNNER_BOT_ELM, message_box_tree)

# The box that took the client down, as run 22's own status clause recorded it.
# `Quit` first because it is a button label and the identity joins every display
# text in order.
CONNECTION_LOST = [
    "Quit",
    "Connection Lost",
    "Connection to server was lost.<br>",
]

# Boxes that must keep the answer they have always had. The first two are the
# shapes `closeMessageBoxByDeclining`'s own comment names; the third is #54's
# Quit Mission confirmation, which the mission runner deliberately *does*
# answer affirmatively and which must not be silenced by a rule about quitting.
ORDINARY_BOXES = [
    (["Warning", "Are you sure you want to undock?"], [("no_dialog_button", "No"),
                                                       (None, "Yes")]),
    (["Notification", "Your ship has been repaired."], [(None, "OK")]),
    (["Quit Mission?", "Are you sure you want to quit this mission?"],
     [("no_dialog_button", "No"), (None, "Yes")]),
]

# Each says only one half of the pair, so neither is this box.
HALF_MATCHES = [
    ["Connection Lost"],
    ["Connection to server was lost."],
    ["Quit", "Lost", "connection"],
]

STANDOFF_STATES = [
    ("Nothing", "no box seen yet"),
    ("(Just { identity = \"x\", readings = 1 })", "first reading"),
    ("(Just { identity = \"x\", readings = messageBoxAnswersBeforeEscape })",
     "the Escape rung"),
    ("(Just { identity = \"x\", readings = messageBoxStandoffGiveUpReadings })",
     "the give-up rung"),
]


class MissionRunnerRepl(ElmRepl):
    """The same harness pointed at the mission runner, which shares the fix."""

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "mr-connection-lost-")
        kwargs.setdefault("app_dir", MISSION_RUNNER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super(MissionRunnerRepl, self).__init__(**kwargs)


class BothAppsRepl(object):
    @classmethod
    def setUpClass(cls):
        cls.repls = {
            "saxrat": open_repl(SaxratRepl, prefix="saxrat-connection-lost-"),
            "mission runner": open_repl(MissionRunnerRepl),
        }

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def box_binding(self, repl, name, texts, buttons):
        return SaxratRepl.reading_binding(
            name, [message_box_tree(texts, buttons)])

    def box_expression(self, name, rule):
        """`rule` applied to the parsed box, or False if nothing parsed."""
        return ("(%s |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
                " |> Maybe.map (%s) |> Maybe.withDefault False)" % (name, rule))

    def ask(self, boxes, rule):
        """`(app, [answer per box])`, with a parse guard on every one."""
        for app, repl in self.repls.items():
            definitions, expressions, parsed = [], [], []
            for index, (texts, buttons) in enumerate(boxes):
                name = "box%d" % index
                definitions.append(self.box_binding(repl, name, texts, buttons))
                expressions.append(self.box_expression(name, rule))
                parsed.append(
                    "(%s |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
                    " |> (/=) Nothing)" % name)
            answers = repl.evaluate(expressions + parsed, definitions)
            half = len(boxes)
            for index, was_parsed in enumerate(answers[half:]):
                self.assertTrue(
                    was_parsed,
                    "%s: the real parser made no message box out of fixture "
                    "%d, so nothing below is about the rule" % (app, index))
            yield app, answers[:half]


class TheBoxIsRecognisedByTheClientsOwnWords(BothAppsRepl, unittest.TestCase):
    RULE = "messageBoxSaysTheConnectionIsLost"

    def test_the_box_that_took_the_client_down_is_recognised(self):
        for app, answers in self.ask(
                [(CONNECTION_LOST, [(None, "Quit")])], self.RULE):
            self.assertEqual([True], answers, app)

    def test_ordinary_boxes_are_not(self):
        for app, answers in self.ask(ORDINARY_BOXES, self.RULE):
            self.assertEqual(
                [False] * len(ORDINARY_BOXES), answers,
                "%s: an ordinary dialog read as the connection being lost "
                "would stop the bot answering something it should" % app)

    def test_half_a_match_is_not_a_match(self):
        boxes = [(texts, [(None, "Quit")]) for texts in HALF_MATCHES]
        for app, answers in self.ask(boxes, self.RULE):
            self.assertEqual(
                [False] * len(HALF_MATCHES), answers,
                "%s: one substring is not the pair -- a single common word "
                "reaches dialogs this must not silence" % app)

    def test_the_wording_is_matched_whatever_its_case(self):
        shouted = [text.upper() for text in CONNECTION_LOST]
        for app, answers in self.ask(
                [(shouted, [(None, "QUIT")])], self.RULE):
            self.assertEqual([True], answers, app)


class NeitherRungIsDispatchedAtThisBox(BothAppsRepl, unittest.TestCase):
    """Both the click and #138's Escape are what this skips."""

    def verdicts(self, texts, buttons):
        for app, repl in self.repls.items():
            binding = self.box_binding(repl, "box", texts, buttons)
            expressions = [
                "(box |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
                " |> Maybe.map (messageBoxStandoffVerdictForBox %s)"
                " |> (==) (Just LeaveTheMessageBoxAlone))" % state
                for state, _ in STANDOFF_STATES]
            yield app, repl.evaluate(expressions, [binding])

    def test_the_connection_lost_box_is_left_alone_at_every_rung(self):
        for app, answers in self.verdicts(CONNECTION_LOST, [(None, "Quit")]):
            for (state, description), left_alone in zip(STANDOFF_STATES, answers):
                self.assertTrue(
                    left_alone,
                    "%s: at %s the bot would still press something at a box "
                    "whose every control quits the client" % (app, description))

    def test_an_ordinary_box_keeps_the_ladder_it_always_had(self):
        texts, buttons = ORDINARY_BOXES[0]
        for app, answers in self.verdicts(texts, buttons):
            self.assertEqual(
                [False, False, False, True], answers,
                "%s: an ordinary box must be answered, then Escaped, and only "
                "left alone at the give-up -- the ladder #138 built" % app)

    def test_the_verdict_otherwise_agrees_with_the_standoff(self):
        texts, buttons = ORDINARY_BOXES[1]
        for app, repl in self.repls.items():
            binding = self.box_binding(repl, "box", texts, buttons)
            expressions = [
                "(box |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
                " |> Maybe.map (messageBoxStandoffVerdictForBox %s)"
                " |> (==) (Just (messageBoxStandoffVerdict %s)))" % (state, state)
                for state, _ in STANDOFF_STATES]
            self.assertEqual(
                [True] * len(STANDOFF_STATES),
                repl.evaluate(expressions, [binding]),
                "%s: for any other box this must be the standoff's own "
                "verdict, unchanged" % app)


class TheDispatchAsksTheNewRule(unittest.TestCase):
    APPS = {"saxrat": SAXRAT_BOT_ELM, "mission runner": MISSION_RUNNER_BOT_ELM}

    def test_close_message_box_consults_the_per_box_verdict(self):
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path), "closeMessageBox"))
            self.assertIn("messageBoxStandoffVerdictForBox standoff messageBox",
                          branch, app)

    def test_the_dispatch_no_longer_asks_the_box_blind_verdict(self):
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path), "closeMessageBox"))
            self.assertNotIn(
                "case messageBoxStandoffVerdict standoff of", branch,
                "%s: the dispatch still reaches the verdict that cannot see "
                "which box it is answering" % app)

    def test_the_declining_answer_still_contains_no_affirmative(self):
        """#54's standing rule, which this change must not have loosened."""
        for app, path in self.APPS.items():
            branch = collapsed(body_of(source_of(path),
                                       "closeMessageBoxByDeclining"))
            for affirmative in ('"yes"', "yes_dialog_button"):
                self.assertNotIn(affirmative, branch.lower(), app)

    def test_both_apps_carry_the_same_two_declarations(self):
        bodies = {}
        for app, path in self.APPS.items():
            source = source_of(path)
            bodies[app] = tuple(
                collapsed(body_of(source, name))
                for name in ("messageBoxStandoffVerdictForBox",
                             "messageBoxSaysTheConnectionIsLost"))
        self.assertEqual(
            bodies["saxrat"], bodies["mission runner"],
            "the two apps' copies have drifted, which is how one bot keeps a "
            "fix the other silently loses")


def saxrat_runs():
    found = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
    if not found:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
            "can say about the Connection Lost incident cannot be consulted "
            "here")
    return found


class TheCorpusCarriesTheIncident(unittest.TestCase):
    def test_a_run_met_this_box(self):
        met = [os.path.basename(path) for path in saxrat_runs()
               if self._says(path, "Connection to server was lost")]
        self.assertTrue(
            met,
            "no recorded run carries the Connection Lost box, so the corpus "
            "no longer evidences the dialog this rule is about")

    def test_a_run_answered_it_with_the_window_close_button(self):
        """The click that is believed to have quit the client."""
        answered = [os.path.basename(path) for path in saxrat_runs()
                    if self._says(path, "Connection to server was lost")
                    and self._says(path, "Dismiss it using the window's close button")]
        self.assertTrue(
            answered,
            "no recorded run answers this box with the window's close button, "
            "which is the fall-through this change exists to stop")

    @staticmethod
    def _says(path, needle):
        with open(path, errors="replace") as handle:
            return needle in handle.read()


if __name__ == "__main__":
    unittest.main()
