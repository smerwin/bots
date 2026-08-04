"""Tests for reading whether the mission tracker entry is actually open.

`expandMissionTrackerIfCollapsed` has existed, correctly written and correctly
placed, since the mission runner was written: it runs *before* the readiness
test in `decideActionWhenDockedWithoutConversation`, precisely because a
collapsed tracker hides the objectives as well as the travel button. It was
defeated by the one line that told it whether to act.

`isExpanded` read the client's `_expanded` key with
`Maybe.withDefault True`, and the key **is present on the entry and reads
`True` while the entry is collapsed** — measured on the live client against a
`content_container` of `384x0` in the same reading. So the guard answered
`Nothing`, the branch behind it was unreachable, and the bot printed

    A mission is running but the tracker offers no travel step from here.

**512 times** in run 30 while four manual clicks on the header opened the entry
(`384x0` -> `384x135`) and the run resumed within twenty seconds. Run 28 lost a
session to the same thing, and the collapsed state was misdiagnosed twice —
first as an untracked mission, then as a panel toggle — because the entry *is*
tracked and the panel *is* open. Only the entry's content is missing.

The failure class is the one CLAUDE.md keeps a section on: **absent is not
false, and a `Maybe.withDefault` gets the unsafe inference for free.** Here the
default was chosen in the safe-looking direction — do not click things
unnecessarily — and it is the direction that made the guard unable to fire.

The measurements these cases pin, all from the live client:

| state | `content_container` | `_expanded` |
|---|---|---|
| collapsed, bot stuck | `384x0` | `True` |
| expanded | `384x135`, `384x144`, `384x186` | `True` |

Nothing here reads a live client. The Elm rule is executed rather than
restated; the wiring is read out of the source.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402

MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")

PARSER = os.path.join(MISSION_RUNNER_DIR, "EveOnline", "ParseUserInterface.elm")
BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")


def source(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace-collapsed, so the next `elm-format` pass cannot break these."""
    return re.sub(r"\s+", " ", text)


def without_comments(text):
    """Code only.

    The doc comment on this field quotes the line it replaced, so an assertion
    that the old expression is gone has to read the code rather than the prose
    explaining why it went. Asserting against the comment is how a test passes
    for the wrong reason — or, as here, fails for one.
    """
    text = re.sub(r"\{-.*?-\}", " ", text, flags=re.S)
    return re.sub(r"--[^\n]*", " ", text)


def function_body(text, start, end):
    first = text.index(start)
    return text[first:text.index(end, first)]


class TheRuleIsExecuted(unittest.TestCase):
    """The heights are the ones the live client produced, in both states."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(
            ElmRepl, prefix="test-tracker-collapsed-",
            preamble=("import Bot exposing (..)",
                      "import EveOnline.ParseUserInterface as Parse"))

    def test_the_collapsed_entry_reads_collapsed(self):
        """`384x0` — run 30's stuck reading, and the whole point."""
        answers = self.repl.evaluate(
            ["Parse.missionEntryIsExpandedFromContentHeight (Just 0)"])
        self.assertEqual([False], answers)

    def test_every_expanded_height_seen_reads_expanded(self):
        answers = self.repl.evaluate([
            "Parse.missionEntryIsExpandedFromContentHeight (Just 135)",
            "Parse.missionEntryIsExpandedFromContentHeight (Just 144)",
            "Parse.missionEntryIsExpandedFromContentHeight (Just 186)",
        ])
        self.assertEqual([True, True, True], answers,
                         "135, 144 and 186 were all read off the live client "
                         "while the entry was open and the objective grew")

    def test_no_container_reads_expanded(self):
        """The direction of the unknown case, chosen rather than defaulted.

        A client naming that node something else leaves the tracker shut and
        the bot waiting — which is what run 30 already did. The other answer
        would have the bot clicking a header it can never open for a whole
        session, which is worse than the bug being fixed.
        """
        answers = self.repl.evaluate(
            ["Parse.missionEntryIsExpandedFromContentHeight Nothing"])
        self.assertEqual([True], answers)

    def test_a_negative_height_is_not_expanded(self):
        # The panel does emit negative widths on empty labels (`-6x0` was in
        # the same subtree), so the comparison has to be `> 0` rather than
        # `/= 0`.
        answers = self.repl.evaluate(
            ["Parse.missionEntryIsExpandedFromContentHeight (Just -6)"])
        self.assertEqual([False], answers)


class TheKeyThatLiedIsNoLongerConsulted(unittest.TestCase):
    """`_expanded` read `True` while collapsed, so it decides nothing now."""

    def setUp(self):
        self.parser = source(PARSER)
        self.field = collapsed(without_comments(function_body(
            self.parser, "    , isExpanded =", "\n    }")))

    def test_the_expanded_key_is_not_read(self):
        self.assertNotIn(
            'Dict.get "_expanded"', self.field,
            "the client's `_expanded` was measured reading True on a collapsed "
            "entry, so consulting it is what this change removes")

    def test_there_is_no_default_standing_in_for_the_state(self):
        self.assertNotIn(
            "Maybe.withDefault True", self.field,
            "a `withDefault` here is how the guard became unable to fire")

    def test_it_measures_the_content_container(self):
        self.assertIn('Just "content_container"', self.field)
        self.assertIn("totalDisplayRegion", self.field)

    def test_the_rule_is_reachable_on_its_own(self):
        # Extracted for the reason `stationNameIsTheOneUndockedFrom` was: a
        # rule reachable only by parsing a whole live UI tree is a rule no
        # case can execute, and this one shipped wrong for exactly that long.
        self.assertIn("missionEntryIsExpandedFromContentHeight", self.field)
        self.assertIn(
            "missionEntryIsExpandedFromContentHeight : Maybe Int -> Bool",
            self.parser)


class TheGuardIsStillWiredAndOrdered(unittest.TestCase):
    """The branch was never the problem; it must stay where it is."""

    def setUp(self):
        self.bot = source(BOT_ELM)

    def test_the_expand_branch_reads_the_parsed_state(self):
        body = collapsed(function_body(
            self.bot,
            "expandMissionTrackerIfCollapsed : BotDecisionContext",
            "\n{-|"))
        self.assertIn("mission.isExpanded", body)

    def test_it_runs_before_the_readiness_test(self):
        """A collapsed tracker hides the objectives too, so this ordering is
        what stops `missionIsReadyToComplete` reading False for the wrong
        reason."""
        docked = collapsed(function_body(
            self.bot,
            "decideActionWhenDockedWithoutConversation : BotDecisionContext",
            "decideActionWhenDockedWithMissionTracker :"))
        expand = docked.index("expandMissionTrackerIfCollapsed context")
        self.assertLess(
            expand, docked.index("courierLoadHasHadLongEnough"),
            "the tracker is expanded before anything else in the docked path")

    def test_the_branch_waits_a_reading_after_clicking(self):
        body = collapsed(function_body(
            self.bot,
            "expandMissionTrackerIfCollapsed : BotDecisionContext",
            "\n{-|"))
        self.assertIn("previousStepClickedMouse context", body)


if __name__ == "__main__":
    unittest.main()
