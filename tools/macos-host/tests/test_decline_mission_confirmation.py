"""Tests for confirming the "Decline Mission?" dialog the bot itself asked for.

`closeMessageBox`'s standing rule is that the bot's automatic answer to a
confirmation is the one that declines. #60 carved out one exception, the "Quit
Mission?" dialog. Declining a mission has the identical shape and nobody added
it, so `decline-mission` — a feature that has shipped since run 13 — was one
timing coincidence away from being unusable.

**Run 25 is that coincidence.** The agent offered `Illegal Activity (1 of 3)`,
which the settings name; the bot clicked `Decline`; EVE raised

    Decline Mission?
    If you decline a mission before 2026.08.04 04:07 you will lose standings
    with this agent, as well as his corp and faction. ... Are you sure you would
    like to decline this mission?
    [Yes] [No]

and `closeMessageBoxByDeclining` answered **No**, which *cancels the decline*.
The offer came back and the bot declined it again: **105** `Decline` clicks
against **226** `Dismiss it using No`, until it was stopped by hand.

**Why twenty-five runs never saw it.** EVE only raises that confirmation inside
the standing-penalty window. Run 20 clicked `Decline` six times and got **zero**
dialogs, so the feature looked like it worked. That contrast is asserted below
from the two logs, because it is the whole reason this shipped unreachable and
the reason a green suite said nothing.

The standing cost is not a new decision this makes. `skipOfferedMissionButton`
already says in so many words that declining "costs standing with the agent,
which is the price of actually moving on; delaying costs the whole session" —
so confirming is what that comment already committed to. Answering No was never
the cheaper option; it bought nothing at all.

Nothing here reads a live game client or a bot. The two run logs it reads are
under `~/eve-bot-logs` and are not in the repo, so those cases skip when absent.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))

BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

LOG_DIR = os.path.expanduser("~/eve-bot-logs")


def bot_elm():
    with open(BOT_ELM, encoding="utf-8") as handle:
        return handle.read()


def collapsed(text):
    """Whitespace-collapsed, so `elm-format` cannot break these assertions.

    #58 broke three tests by reflowing code they matched literally; every
    structural assertion here goes through this.
    """
    return re.sub(r"\s+", " ", text)


def function_body(source, start, end):
    first = source.index(start)
    return source[first:source.index(end, first)]


def log_lines(path):
    """One line at a time, tolerating a log a run is still appending to."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if line.endswith("\n"):
                yield line


class TheGateIsTheSameShapeAsTheQuitMissionOne(unittest.TestCase):
    """Three conditions, and each has to be there for the same reason."""

    def setUp(self):
        self.source = bot_elm()
        # Ends at the lookback constant that follows it, not at the section
        # break: that constant's own doc comment names the dialog, and a looser
        # slice would make `test_it_does_not_read_the_dialog_text` fail on prose
        # rather than on the rule it is about.
        self.expected = collapsed(function_body(
            self.source,
            "declineMissionConfirmationIsExpected : BotDecisionContext",
            "\n{-| How far back to look for the click"))

    def test_it_needs_the_agent_to_be_offering_a_mission_we_decline(self):
        # The verdict is the bot's own settings naming this mission, which is
        # what makes the Yes *intended* rather than inferred from the dialog.
        self.assertIn("shouldDeclineMission context conversation.offeredMissionName",
                      self.expected)

    def test_it_needs_an_agent_conversation_open(self):
        # No travel or station step produces one, so this is what stops a
        # confirmation raised anywhere else being answered in the affirmative.
        self.assertIn("context.readingFromGameClient.agentConversationWindows",
                      self.expected)
        self.assertIn("Nothing -> False", self.expected)

    def test_it_looks_for_the_click_over_a_window_not_on_the_previous_step(self):
        """The bug the first version of this shipped with.

        Copied straight from #60, which asks whether the *previous* step
        clicked. Run 26 ran that live and the branch never fired once: the
        steps between the click and the dialog dispatch nothing, so the strict
        predicate is already false by the time there is a dialog to answer.
        """
        self.assertIn("recentStepsEffectsPressedMouse", self.expected)
        self.assertIn("declineConfirmationClickLookbackSteps", self.expected)
        self.assertNotIn(
            "previousStepClickedMouse context", self.expected,
            "the strict previous-step predicate cannot see this dialog -- "
            "measured six steps after the click, every time")

    def test_the_strict_predicate_still_exists_for_its_other_callers(self):
        # Widening this one caller must not widen #60's gate or the cascade's.
        strict = collapsed(function_body(
            self.source,
            "previousStepsEffectsPressedMouse :",
            "\n{-| The same question over a window"))
        self.assertIn("recentStepsEffectsPressedMouse 1", strict)

    def test_it_does_not_read_the_dialog_text(self):
        # The wording is the client's language. Matching it would make the
        # branch fail on a client that renders the same dialog differently,
        # which is the failure direction that looks like success.
        for wording in ["Decline Mission?", "lose standings", "Are you sure",
                        "mainText"]:
            self.assertNotIn(
                wording, self.expected,
                "the gate must be a fact about the bot's intent, not about "
                "how the client happens to word its dialog")


class TheLookbackIsMeasured(unittest.TestCase):
    """Eight steps, because six is what the client does and ten is the cap."""

    def setUp(self):
        self.source = bot_elm()
        self.lookback = int(re.search(
            r"declineConfirmationClickLookbackSteps : Int\s+"
            r"declineConfirmationClickLookbackSteps =\s+(\d+)",
            self.source).group(1))

    def test_the_constant_is_the_measured_gap_with_headroom(self):
        self.assertEqual(8, self.lookback)

    def test_it_fits_inside_the_history_the_framework_keeps(self):
        """A lookback past the cap silently becomes the cap."""
        framework = os.path.join(
            REPO_DIR, "implement", "applications", "eve-online",
            "eve-online-mission-runner", "EveOnline",
            "BotFrameworkSeparatingMemory.elm")
        with open(framework, encoding="utf-8") as handle:
            kept = int(re.search(
                r"effectsOnGameClientWindow\s*::\s*stateBefore\.lastStepsEffects"
                r"\s*\|>\s*List\.take (\d+)",
                collapsed(handle.read())).group(1))
        self.assertLessEqual(
            self.lookback, kept,
            "asking for more steps than the framework keeps would make the "
            "window silently the cap rather than the measured number")

    def test_the_recorded_gap_is_what_the_constant_is_set_from(self):
        """Re-measured from the logs, so a client that changes says so here.

        The gap is the number of framework steps from the dispatch that clicks
        Decline to the reading carrying the confirmation.
        """
        gaps = []
        for run in (25, 26):
            path = os.path.join(LOG_DIR, "mission_run%d.log" % run)
            if not os.path.exists(path):
                continue
            steps = 0
            last_dispatch = None
            declined = False
            counted = True
            for line in log_lines(path):
                if line.startswith("# ["):
                    steps += 1
                elif "using 'Decline'" in line:
                    declined, counted = True, False
                elif "send-effects" in line and declined:
                    last_dispatch = steps
                elif ("I see a message box to close" in line
                      and last_dispatch is not None and not counted):
                    gaps.append(steps - last_dispatch)
                    counted, declined = True, False
        if not gaps:
            self.skipTest("neither run 25 nor run 26 is on this machine")
        self.assertGreater(len(gaps), 100, "the measurement rests on 158 cases")
        self.assertEqual(
            {6}, set(gaps),
            "the recorded gap was six steps with no other value; a different "
            "number here means the client changed and the lookback is stale")
        self.assertGreaterEqual(self.lookback, max(gaps))


class TheAffirmativeIsStillNarrow(unittest.TestCase):
    """Two exceptions now, and everything else is still answered No."""

    def setUp(self):
        self.source = bot_elm()
        self.close = collapsed(function_body(
            self.source,
            "closeMessageBox :",
            "\n{-| The affirmative button on a yes/no confirmation"))

    def test_both_affirmatives_go_through_the_shape_based_button_finder(self):
        # `quitMissionConfirmationButton` declines anything that is not a
        # two-button yes/no pair, so a notification with a single OK, or a
        # three-button dialog, is untouched by either exception.
        self.assertEqual(
            2, self.close.count("quitMissionConfirmationButton messageBox"),
            "both confirmations must identify the button by the dialog's "
            "shape rather than by its wording")

    def test_anything_else_still_declines(self):
        self.assertIn("Nothing -> closeMessageBoxByDeclining messageBox",
                      self.close)

    def test_the_two_confirmations_are_separately_gated(self):
        self.assertIn("if confirmQuitMission then", self.close)
        self.assertIn("else if confirmDeclineMission then", self.close)

    def test_the_decline_confirmation_names_itself_in_the_log(self):
        # An operator reading the log has to be able to tell which of the two
        # dialogs was confirmed, because only one of them ends a mission.
        self.assertIn("'Decline Mission?' confirmation", self.close)
        self.assertIn("'Quit Mission' confirmation", self.close)

    def test_the_log_line_says_what_saying_no_would_have_done(self):
        # The whole bug is that No is not a safe default here, and the next
        # reader of this branch should not have to rediscover that.
        self.assertIn("cancels the decline", self.close)

    def test_the_gate_reaches_close_message_box_from_the_decision_root(self):
        # A gate computed and never passed down is #15's shape: it compiles,
        # it runs, and the branch behind it can never be true.
        root = collapsed(function_body(
            self.source,
            "[ generalSetupInUserInterface",
            "context.readingFromGameClient"))
        self.assertIn(
            "confirmDeclineMission = declineMissionConfirmationIsExpected context",
            root)
        setup = collapsed(function_body(
            self.source,
            "generalSetupInUserInterface :",
            "\n        |> List.filterMap"))
        self.assertIn("confirmDeclineMission = confirmDeclineMission", setup)


class TheLoopThisAnswers(unittest.TestCase):
    """The recorded evidence, and the contrast that explains the blind spot."""

    def _counts(self, run):
        path = os.path.join(LOG_DIR, "mission_run%d.log" % run)
        if not os.path.exists(path):
            self.skipTest("%s is not on this machine" % path)
        declines = dismissals = 0
        for line in log_lines(path):
            if "using 'Decline'" in line:
                declines += 1
            if "Dismiss it using No" in line:
                dismissals += 1
        return declines, dismissals

    def test_run_25_declined_over_and_over_and_dismissed_the_confirmation(self):
        declines, dismissals = self._counts(25)
        self.assertGreater(declines, 20,
                           "run 25 is the log this change exists for")
        self.assertGreater(dismissals, declines,
                           "every decline raised a confirmation that was then "
                           "answered No, which cancelled it")

    def test_run_20_declined_without_ever_seeing_the_confirmation(self):
        """Why this shipped unreachable, and why a green suite said nothing.

        EVE only asks inside the standing-penalty window. Outside it the
        decline goes straight through, which is what every run before 25 saw.
        """
        declines, dismissals = self._counts(20)
        self.assertGreater(declines, 0)
        self.assertEqual(
            0, dismissals,
            "run 20's declines raised no confirmation at all -- the same "
            "setting, the same code, and no dialog")


if __name__ == "__main__":
    unittest.main()
