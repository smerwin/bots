"""Tests for saxrat accepting a fleet invitation from a named pilot.

The one dialog this bot ever answers yes to, and the second exception in this
repo to `closeMessageBoxByDeclining`'s standing rule that a dialog is always
declined.

**The fixture is a real invitation, not a guess at one.** Nothing here had ever
read a fleet invitation: `FleetWindow`/`FleetMember` are the *roster*, and the
invitation's node type, its buttons and its wording were unobserved. So one was
captured off the live client on 2026-08-10 before any of this was written --

    MessageBox  _name='modal'  [1658,900 525x325]
      TextHeadline  _setText='Join Fleet?'
      TextBody      _setText='<a href="showinfo:1385//2120724228">Gal Bistot</a>
                              wants you to join their fleet, do you accept?<br><br>NOTE: ...'
      Button _name='yes_dialog_button'  label 'Yes'
      Button _name='no_dialog_button'   label 'No'

-- and the strings below are that capture rather than a plausible reconstruction
of one. Two things it settles beyond this rule:

- **A fleet invitation is a `MessageBox`.** So before this change the bot did not
  merely fail to accept invitations, it *rejected* them: `no_dialog_button` is
  the second of `closeMessageBoxByDeclining`'s dismissal options and the dialog
  offers no Close/OK, so `Dismiss it using No.` was the answer. Observed nine
  times in saxrat run 13, with the operator confirming the rejection at the other
  end.
- **`yes_dialog_button` exists under that name in a live tree.** CLAUDE.md
  records the mission runner's abandonment identifying the affirmative by the
  dialog's *shape* precisely because "`yes_dialog_button` has never been read out
  of a live UI tree here". It has now.

**What the cases are mostly about is the ways this could accept the wrong
thing**, since that is what it costs: a fleet commander can warp a fleet member's
ship. So absent evidence accepts nothing, the name is matched exactly rather than
as a substring, an empty setting value is refused rather than dropped, and the
declining answer is asserted to be unchanged for everything else.

The rules are executed through the real `Bot.elm` in `elm repl` via the shared
harness, and the message boxes are built by running UI trees through the **real**
`EveOnline.ParseUserInterface`, so what the cases assert on is what the bot would
have been handed.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import (ElmRepl, REPO_DIR, elm_json_literal, open_repl)

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import Common.DecisionPath",
)

# Verbatim from the capture, markup and all. The inviter's name sits inside a
# showinfo link, which is the whole reason `textWithoutMarkupTags` exists.
REAL_INVITE_BODY = (
    '<a href="showinfo:1385//2120724228">Gal Bistot</a> wants you to join their'
    ' fleet, do you accept?<br><br>NOTE: Attacking members of your fleet is not'
    ' a CONCORD sanctioned activity and may result in security status loss and'
    ' police response.'
)
REAL_INVITE_HEADLINE = "Join Fleet?"
INVITER = "Gal Bistot"

_address = iter(range(100000, 999999))


def node(type_name, entries=None, children=(), region=None):
    """One UI tree node in the shape `decodeMemoryReadingFromString` wants."""
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def dialog_button(name, label, x):
    """A button as the client draws one: a named `Button` over a label node."""
    return node("ButtonWrapper", {}, [
        node("Button", {"_name": name}, [
            node("EveLabelMedium", {"_name": "label", "_setText": label},
                 region=(x + 112, 9, 21, 22)),
        ], region=(0, 0, 245, 40)),
    ], region=(x, 0, 245, 40))


def message_box(headline, body, buttons):
    """A `MessageBox` shaped like the captured one."""
    return node("MessageBox", {"_name": "modal"}, [
        node("Container", {"_name": "content"}, [
            node("Container", {"_name": "main"}, [
                node("Container", {"_name": "bottom"}, [
                    node("ButtonGroup", {}, [
                        node("ContainerAutoSize", {"_name": "btns"}, buttons,
                             region=(0, 0, 500, 40)),
                    ], region=(0, 0, 500, 40)),
                ], region=(0, 270, 500, 40)),
                node("ContainerAutoSize", {"_name": "topParent"}, [
                    node("TextHeadline", {"_setText": headline},
                         region=(80, 13, 420, 35)),
                ], region=(0, 20, 500, 60)),
                node("ScrollContainer", {}, [
                    node("Container", {"_name": "clipCont"}, [
                        node("ContainerAutoSize", {"_name": "mainCont"}, [
                            node("TextBody", {"_setText": body},
                                 region=(0, 0, 500, 95)),
                        ], region=(0, 0, 500, 95)),
                    ], region=(0, 0, 500, 165)),
                ], region=(0, 100, 500, 165)),
            ], region=(10, 0, 500, 310)),
        ], region=(3, 3, 520, 320)),
    ], region=(1658, 900, 525, 325))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


YES_AND_NO = [dialog_button("yes_dialog_button", "Yes", 0),
              dialog_button("no_dialog_button", "No", 255)]

FLEET_INVITE = message_box(REAL_INVITE_HEADLINE, REAL_INVITE_BODY, YES_AND_NO)

# The shape #54 warns about: a two-button confirmation that is not an invitation.
QUIT_MISSION = message_box(
    "Quit Mission?",
    "Are you sure you want to quit this mission? Your standing will suffer.",
    YES_AND_NO)


def reading_binding(name, box):
    """Bind `name` to a whole parsed reading holding `box`."""
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree"
            % (name, elm_json_literal(tree_with([box]))))


def box_binding(name, box):
    """Bind `name` to the first parsed `MessageBox` of a tree holding `box`."""
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree"
            " |> Maybe.map .messageBoxes |> Maybe.andThen List.head"
            % (name, elm_json_literal(tree_with([box]))))


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    return re.sub(r"\s+", " ", text)


class SaxratRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-fleetinvite-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class TheCapturedInvitationIsReadTest(unittest.TestCase):
    """The rules, against the dialog the client actually drew."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)
        cls.definitions = [
            box_binding("invite", FLEET_INVITE),
            box_binding("quitMission", QUIT_MISSION),
            box_binding(
                "noYesButton",
                message_box(REAL_INVITE_HEADLINE, REAL_INVITE_BODY,
                            [dialog_button("no_dialog_button", "No", 255)])),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixture_arrived(self):
        """A box that never parsed and a rule answering nothing read alike."""
        self.assertEqual(
            self.repl.evaluate(["invite /= Nothing", "quitMission /= Nothing",
                                "noYesButton /= Nothing"],
                               definitions=self.definitions),
            [True, True, True])

    def test_the_inviter_is_read_through_the_markup(self):
        self.assertEqual(
            self.repl.strings(
                ['invite |> Maybe.andThen fleetInvitationInviter'
                 ' |> Maybe.withDefault "NONE"'],
                definitions=self.definitions),
            [INVITER])

    def test_markup_is_stripped_rather_than_matched(self):
        stripped = self.repl.strings(
            ["textWithoutMarkupTags %s" % elm_json_literal(REAL_INVITE_BODY)],
            definitions=self.definitions)[0]
        self.assertIn(INVITER, stripped)
        self.assertNotIn("<a href", stripped)
        self.assertNotIn("showinfo", stripped)

    def test_a_named_pilot_is_accepted(self):
        self.assertEqual(
            self.repl.strings(
                ['invite |> Maybe.andThen (fleetInvitationToAccept ["%s"])'
                 ' |> Maybe.withDefault "NONE"' % INVITER],
                definitions=self.definitions),
            [INVITER])

    def test_the_name_is_matched_ignoring_case(self):
        self.assertEqual(
            self.repl.strings(
                ['invite |> Maybe.andThen'
                 ' (fleetInvitationToAccept ["  gal BISTOT "])'
                 ' |> Maybe.withDefault "NONE"'],
                definitions=self.definitions),
            [INVITER])

    def test_a_substring_of_the_name_is_refused(self):
        """`attack-object`'s lesson, where the cost is the ship's position."""
        entries = ("Gal", "Bistot", "al Bisto")
        self.assertEqual(
            self.repl.evaluate(
                ['(invite |> Maybe.andThen'
                 ' (fleetInvitationToAccept ["%s"])) == Nothing' % entry
                 for entry in entries],
                definitions=self.definitions),
            [True] * len(entries))

    def test_absent_evidence_accepts_nothing(self):
        """The whole default: no setting, no acceptance."""
        self.assertEqual(
            self.repl.evaluate(
                ["(invite |> Maybe.andThen (fleetInvitationToAccept []))"
                 " == Nothing"],
                definitions=self.definitions),
            [True])

    def test_another_pilot_is_refused(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(invite |> Maybe.andThen'
                 ' (fleetInvitationToAccept ["Someone Else"])) == Nothing'],
                definitions=self.definitions),
            [True])

    def test_a_confirmation_that_is_not_an_invitation_is_not_read_as_one(self):
        """The Quit Mission shape: same two buttons, different sentence."""
        self.assertEqual(
            self.repl.evaluate(
                ["(quitMission |> Maybe.andThen fleetInvitationInviter)"
                 " == Nothing",
                 '(quitMission |> Maybe.andThen'
                 ' (fleetInvitationToAccept ["%s"])) == Nothing' % INVITER],
                definitions=self.definitions),
            [True, True])

    def test_the_affirmative_button_is_found_by_its_live_name(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(invite |> Maybe.andThen'
                 ' (messageBoxButtonNamed "yes_dialog_button")) /= Nothing',
                 '(invite |> Maybe.andThen'
                 ' (messageBoxButtonNamed "not_a_button")) == Nothing'],
                definitions=self.definitions),
            [True, True])

    def test_an_invitation_with_no_yes_button_is_not_accepted(self):
        """All three conditions hold together or the branch declines."""
        self.assertEqual(
            self.repl.evaluate(
                ['(noYesButton |> Maybe.andThen'
                 ' (acceptFleetInvitationFrom "%s")) == Nothing' % INVITER],
                definitions=self.definitions),
            [True])


class TheSettingRefusesAnEmptyValueTest(unittest.TestCase):
    """An empty entry would match every invitation there is."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_named_pilot_parses(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(parseBotSettings "accept-fleet-invite-from=%s"'
                 ' |> Result.map .acceptFleetInviteFrom) == Ok ["%s"]'
                 % (INVITER, INVITER)]),
            [True])

    def test_an_empty_value_is_rejected_rather_than_dropped(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(parseBotSettings "accept-fleet-invite-from=" '
                 '|> Result.toMaybe) == Nothing']),
            [True])

    def test_the_default_is_nobody(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(parseBotSettings "" |> Result.map .acceptFleetInviteFrom)'
                 ' == Ok []']),
            [True])

    def test_several_pilots_may_be_named(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(parseBotSettings "accept-fleet-invite-from=A\\n'
                 'accept-fleet-invite-from=B"'
                 ' |> Result.map .acceptFleetInviteFrom) == Ok ["A","B"]']),
            [True])


class TheDecliningAnswerIsUnchangedTest(unittest.TestCase):
    """#54's standing rule, read out of the source.

    The accept is a separate branch *above* `closeMessageBoxByDeclining`, so that
    function keeps its property: it contains no affirmative at all, and every box
    that is not a permitted invitation still reaches it.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)
        self.declining = self._declaration("closeMessageBoxByDeclining")

    def _declaration(self, name):
        match = re.search(
            r"^%s :.*?(?=\n\n\n)" % re.escape(name),
            self.source, re.MULTILINE | re.DOTALL)
        if match is None:
            raise AssertionError("no declaration named " + name)
        return collapsed(match.group(0))

    def test_the_declining_path_still_contains_no_affirmative(self):
        for affirmative in ("yes_dialog_button", '"yes"', '"accept"'):
            self.assertNotIn(affirmative, self.declining.lower(), affirmative)

    def test_the_declining_path_still_offers_its_three_dismissals(self):
        for option in ("no_dialog_button", "closeButton", '"close", "ok"'):
            self.assertIn(option, self.declining, option)

    def test_the_accept_is_asked_before_the_decline_and_falls_through(self):
        branch = self._declaration("closeMessageBox")
        self.assertIn("fleetInvitationToAccept", branch)
        self.assertIn("closeMessageBoxByDeclining", branch)
        self.assertLess(branch.index("fleetInvitationToAccept"),
                        branch.index("closeMessageBoxByDeclining"),
                        "the accept has to be asked first")

    def test_reading_the_order_is_not_enough_and_this_says_so(self):
        """A note, not a rule: the case above passed a mutation that disabled
        the accept entirely, because text order survives a branch wired to
        `Nothing`. `TheWholeBranchIsExecutedTest` is what actually holds it.
        """
        self.assertTrue(hasattr(TheWholeBranchIsExecutedTest,
                                "test_a_permitted_invitation_is_accepted"))

    def test_the_accept_reaches_the_operator_s_setting(self):
        """A branch wired to a literal would accept from anyone."""
        branch = self._declaration("closeMessageBox")
        self.assertIn("fleetInvitationToAccept acceptFleetInviteFrom", branch)

    def test_the_marker_is_one_constant_shared_by_test_and_slice(self):
        rule = self._declaration("fleetInvitationInviter")
        self.assertIn("fleetInvitationMarker", rule)
        self.assertNotIn("wants you to join", rule,
                         "the wording belongs in the marker constant")


class TheWholeBranchIsExecutedTest(unittest.TestCase):
    """`closeMessageBox` itself, end to end, rather than its source text.

    **This class exists because a mutation survived without it.** Replacing the
    accept lookup with one that can only answer `Nothing` -- so every invitation
    is declined again, which is the whole defect this change fixes -- left
    `test_the_accept_is_asked_before_the_decline_and_falls_through` passing,
    because the names still appear in that order in the source. A case that
    passes while the feature is switched off is this repo's signature failure
    sitting in its own test file.

    So the branch is run, and what is asserted is the decision it produces.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)
        cls.definitions = [
            reading_binding("inviteReading", FLEET_INVITE),
            reading_binding("quitReading", QUIT_MISSION),
            "describe = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf"
            " >> Tuple.first >> String.join \" | \"",
            "answer = \\permitted -> \\reading -> reading"
            " |> Maybe.andThen (closeMessageBox (Just { identity = \"x\","
            " readings = 1 }) permitted)"
            " |> Maybe.map describe |> Maybe.withDefault \"NO DECISION\"",
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_permitted_invitation_is_accepted(self):
        answer = self.repl.strings(
            ['answer ["%s"] inviteReading' % INVITER],
            definitions=self.definitions)[0]
        self.assertIn("fleet invitation from '%s'" % INVITER, answer)
        self.assertNotIn("Dismiss it using", answer)

    def test_an_unnamed_pilot_s_invitation_is_still_declined(self):
        answer = self.repl.strings(
            ['answer ["Someone Else"] inviteReading'],
            definitions=self.definitions)[0]
        self.assertIn("Dismiss it using", answer)
        self.assertNotIn("fleet invitation from", answer)

    def test_with_no_setting_the_invitation_is_still_declined(self):
        answer = self.repl.strings(
            ["answer [] inviteReading"], definitions=self.definitions)[0]
        self.assertIn("Dismiss it using", answer)
        self.assertNotIn("fleet invitation from", answer)

    def test_every_other_dialog_still_gets_the_declining_answer(self):
        answer = self.repl.strings(
            ['answer ["%s"] quitReading' % INVITER],
            definitions=self.definitions)[0]
        self.assertIn("Dismiss it using", answer)
        self.assertNotIn("fleet invitation from", answer)


if __name__ == "__main__":
    unittest.main()
