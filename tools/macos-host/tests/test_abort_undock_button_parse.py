"""One button, three labels, and only the first is one to press.

The station window's undock slot reads "Undock" while docked, then "Abort
Undock", then "Undocking...". Pressing either of the last two cancels the undock
already under way.

`buttonFromDisplayText` matches a *whole* label -- equality, or the label wrapped
in tags -- so "Abort Undock" matched neither `"undock"` nor `"undocking"`, and
"Undocking..." misses the `"undocking"` matcher written for it because the
ellipsis is part of the label. Both states left `undockButton` and
`abortUndockButton` empty, which every caller reads as "I do not see the undock
button".

saxrat's run 43 spent 10,310 readings there, asking for help while docked and
clicking undock 20,486 times in between. Matching "abort" alone cut that to 3
readings in three minutes and still did not free the ship -- 256 clicks met 132
waits -- because the third label was still invisible.

These cases pin both matches, the consistency of the six vendored copies, the
suppression that stops the loop, and the property that makes it safe: nothing
changes when no in-progress label is on screen.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.path.join(REPO, "implement", "applications", "eve-online")

ALL_APPS = (
    "eve-online-combat-anomaly-bot",
    "eve-online-mining-bot",
    "eve-online-mission-runner",
    "eve-online-saxrat",
    "eve-online-warp-to-0-autopilot",
    "eve-online-wingus",
)

# `eve-online-mining-bot`'s tree was replaced with Viir's current upstream
# (see CLAUDE.md's Architecture section), which predates this fix entirely:
# its parse still calls `buttonFromDisplayText "undock"` /
# `buttonFromDisplayText "undocking"` directly (whole-label matching), with
# no `buttonUndoingTheUndock` helper and no abort-suppression case at all.
# Excluded from every case below rather than assigned a shape; porting this
# fix into the newer base is follow-up work, not done here.
WITHOUT_ABORT_UNDOCK_MATCHING = {"eve-online-mining-bot"}

PARSER_COPIES = [
    os.path.join(APPS, app, "EveOnline", "ParseUserInterface.elm")
    for app in ALL_APPS
    if app not in WITHOUT_ABORT_UNDOCK_MATCHING
]


def collapse(text):
    return re.sub(r"\s+", " ", text)


def station_window_block(path):
    """The parse of the station window's two undock fields, whitespace-collapsed.

    Ends at the last literal of the `abortUndockButton` field rather than at the
    record's closing brace: the record itself is not identical across copies --
    the mission runner carries `agentsTab` and `agentEntries` after these two --
    and those differences are not what this file is pinning.
    """
    text = open(path).read()
    start = text.index("buttonUndoingTheUndock =")
    marker = ", abortUndockButton = buttonUndoingTheUndock"
    end = text.index(marker, start) + len(marker)
    return collapse(text[start:end])


class AbortUndockIsRecognised(unittest.TestCase):
    def test_every_copy_looks_for_an_abort_label(self):
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertIn('String.contains "abort"', block,
                              "the abort label is matched on a substring")

    def test_every_copy_also_looks_for_the_undocking_label(self):
        """The slot carries three labels, not two.

        "Undock" -> "Abort Undock" -> "Undocking...". The third was reported
        live after the abort match shipped: matching "abort" alone cut "I do not
        see the undock button" from 852 readings to 3, but the ship still did not
        get out, because 256 clicks were still meeting 132 waits. The ellipsis is
        part of the label, so the `"undocking"` matcher already written for this
        state could never match it on equality.
        """
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertIn('String.contains "undocking"', block,
                              "the in-progress label is matched on a substring too")

    def test_the_six_copies_agree(self):
        blocks = {station_window_block(p) for p in PARSER_COPIES}
        self.assertEqual(len(blocks), 1,
                         "all six vendored copies must carry the identical parse")

    def test_an_abort_button_suppresses_the_undock_button(self):
        """The field the caller clicks must be empty while an undock is under way.

        This is the half that stops the loop: `undockUsingStationWindow` clicks
        whatever `undockButton` holds, so leaving it populated during the abort
        window is what let a click cancel the undock it had just commanded.
        """
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertRegex(
                    block,
                    r"undockButton = case buttonUndoingTheUndock of Just _ -> Nothing",
                    "an abort label must leave undockButton empty")

    def test_absent_in_progress_label_leaves_the_old_behaviour(self):
        """Nothing on screen undoing an undock must parse exactly as before."""
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertIn('Nothing -> buttonFromDisplayText "undock"', block)

    def test_wording_agrees_with_the_mission_runner(self):
        """"abort" is the mission runner's own tested wording, not a new guess."""
        runner = open(os.path.join(APPS, "eve-online-mission-runner", "Bot.elm")).read()
        start = runner.index("labelUndoesStepInProgress label =")
        self.assertIn('"abort"', collapse(runner[start:start + 200]),
                      "the mission runner tests the same word for the same label")

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_fix(self):
        path = os.path.join(
            APPS, "eve-online-mining-bot", "EveOnline", "ParseUserInterface.elm")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("buttonUndoingTheUndock", source)
        self.assertIn(
            'undockButton = buttonFromDisplayText "undock"', collapse(source))


if __name__ == "__main__":
    unittest.main()
