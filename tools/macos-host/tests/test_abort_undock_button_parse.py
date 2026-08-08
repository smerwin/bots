"""The station window's undock button becomes "Abort Undock" mid-undock.

`buttonFromDisplayText` matches a whole label -- equality, or the label wrapped
in tags -- so "Abort Undock" matched neither `"undock"` nor `"undocking"`, and
both fields came back `Nothing`. Every caller reads that as "I do not see the
undock button", which is where saxrat's run 43 spent 10,310 readings asking for
help while docked, having clicked undock 20,486 times in between.

These cases pin the parse, the consistency of the six vendored copies, and the
one property that makes the fix safe: nothing changes when no abort button is on
screen.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.path.join(REPO, "implement", "applications", "eve-online")

PARSER_COPIES = [
    os.path.join(APPS, app, "EveOnline", "ParseUserInterface.elm")
    for app in (
        "eve-online-combat-anomaly-bot",
        "eve-online-mining-bot",
        "eve-online-mission-runner",
        "eve-online-saxrat",
        "eve-online-warp-to-0-autopilot",
        "eve-online-wingus",
    )
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
    marker = 'buttonFromDisplayText "undocking"'
    end = text.index(marker, start) + len(marker)
    return collapse(text[start:end])


class AbortUndockIsRecognised(unittest.TestCase):
    def test_every_copy_looks_for_an_abort_label(self):
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertIn('String.contains "abort"', block,
                              "the abort label is matched on a substring")

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

    def test_absent_abort_leaves_the_old_behaviour(self):
        """No abort button on screen must parse exactly as before the fix."""
        for path in PARSER_COPIES:
            with self.subTest(path=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                block = station_window_block(path)
                self.assertIn('Nothing -> buttonFromDisplayText "undock"', block)
                self.assertIn('Nothing -> buttonFromDisplayText "undocking"', block)

    def test_wording_agrees_with_the_mission_runner(self):
        """"abort" is the mission runner's own tested wording, not a new guess."""
        runner = open(os.path.join(APPS, "eve-online-mission-runner", "Bot.elm")).read()
        start = runner.index("labelUndoesStepInProgress label =")
        self.assertIn('"abort"', collapse(runner[start:start + 200]),
                      "the mission runner tests the same word for the same label")


if __name__ == "__main__":
    unittest.main()
