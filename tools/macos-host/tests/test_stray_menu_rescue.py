"""A stray context menu is cleared with a click, not with Escape.

Escape does not clear these. Measured live on saxrat's run 45 against a stray
drone menu: the bot pressed Escape at it 48 times, a hand-sent Escape into a
frontmost client did nothing at all, and the menu survived -- while a left click
elsewhere dismissed it immediately. The cascade meanwhile discarded 3,877 times
and dispatched no input for ~185,000 log lines, because the only action that
could clear the menu was one it refused to take.

Escape is also actively unsafe as a default: a naked Escape can open the client's
own settings menu, which is why `closeSystemSettingsMenu` exists.

These cases pin the click, the anchor it is derived from, the fallback, and the
one property that keeps it away from `beginCascade`'s "empty space" failure --
the point is computed from the panel's live region rather than remembered.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.path.join(REPO, "implement", "applications", "eve-online")

BOTS = [
    os.path.join(APPS, app, "Bot.elm")
    for app in ("eve-online-saxrat", "eve-online-combat-anomaly-bot",
                "eve-online-mission-runner")
]


def collapse(text):
    return re.sub(r"\s+", " ", text)


def rescue_branch(path):
    """The rescue action only, not the condition that triggers it.

    The trigger legitimately differs between bots -- saxrat's asks whether the
    ammo swap owns the menu, the other two compare a tick threshold directly --
    and that divergence predates this change. What every bot must agree on is
    what it does once it has decided a menu is stray.
    """
    text = open(path).read()
    start = text.index("case emptyPointBesideTheInfoPanel")
    end = text.index("strayMenuClearGapFromInfoPanel :", start)
    return collapse(text[start:end])


def empty_point_helper(path):
    """The helper's body, ending at the definition boundary.

    A fixed-width window would run past it into whatever function each bot
    happens to declare next, which differs between them.
    """
    text = open(path).read()
    start = text.index("emptyPointBesideTheInfoPanel readingFromGameClient =")
    end = text.index("\n\n\n", start)
    return collapse(text[start:end])


class StrayMenuIsClearedWithAClick(unittest.TestCase):
    def test_the_rescue_is_a_right_click(self):
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                branch = rescue_branch(path)
                self.assertIn("effectsMouseClickAtLocation EffectOnWindow.MouseButtonRight",
                              branch, "the stray menu is cleared with a click")

    def test_escape_is_only_the_fallback(self):
        """Escape survives for the case with no panel to measure against.

        It must not be the first answer: it was measured doing nothing to the
        menu it is meant to clear, and it can open the settings menu instead.
        """
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                branch = rescue_branch(path)
                click_at = branch.index("MouseButtonRight")
                escape_at = branch.index("vkey_ESCAPE")
                self.assertLess(click_at, escape_at,
                                "the click is reached before Escape")
                self.assertIn("Nothing ->", branch[:escape_at],
                              "Escape sits on the no-info-panel arm")

    def test_the_point_is_derived_not_remembered(self):
        """The whole reason this is safe where `beginCascade`'s was not.

        A remembered coordinate once opened 'Clear All Waypoints' on a real
        route. This one is computed from the info panel's live region every
        reading, so it moves with the layout.
        """
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                helper = empty_point_helper(path)
                self.assertIn("infoPanelContainer", helper)
                self.assertIn("totalDisplayRegion", helper)
                self.assertIn("region.x + region.width", helper,
                              "the point is offset from the panel's own edge")

    def test_no_panel_means_no_point(self):
        """`Nothing` rather than a guessed location when there is no anchor."""
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                helper = empty_point_helper(path)
                self.assertIn("Maybe.map", helper,
                              "an absent info panel yields Nothing, not a default point")

    def test_the_three_bots_agree(self):
        self.assertEqual(len({rescue_branch(p) for p in BOTS}), 1,
                         "every bot carrying this branch clears the menu the same way")
        self.assertEqual(len({empty_point_helper(p) for p in BOTS}), 1,
                         "and derives the point the same way")

    def test_the_gap_is_named_rather_than_inline(self):
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                helper = empty_point_helper(path)
                self.assertIn("strayMenuClearGapFromInfoPanel", helper,
                              "the offset is a named constant, not a bare number")


if __name__ == "__main__":
    unittest.main()
