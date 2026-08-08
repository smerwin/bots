"""The cascade waits for a first menu longer than it takes to render.

A freshly opened context menu's widget exists and is visibly on screen before
its display-region entries populate, and the parser drops nodes without a
region -- so a real, open menu reads back as zero menus for the length of that
gap. `useContextMenuCascadeWithCustomConfig`'s own comment records that gap
lasting "as long as 10+ real ticks in one observed case", and the wait was
capped at 2.

A cap set below the phenomenon it caps is the loop, not the guard: saxrat's run
46 right-clicked a scan result 385 times, spent 1,340 readings on the wait
branch, and read the menu back zero times -- because a second right-click on an
already-open menu dismisses it.

These cases pin the size against the observation, the bound that keeps it from
becoming an unbounded search, and the property that makes waiting free: the
cascade proceeds the moment any menu is in the reading.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.path.join(REPO, "implement", "applications", "eve-online")

COPIES = [
    os.path.join(APPS, app, "EveOnline", "BotFrameworkSeparatingMemory.elm")
    for app in ("eve-online-saxrat", "eve-online-mission-runner",
                "eve-online-combat-anomaly-bot", "eve-online-warp-to-0-autopilot")
]


def collapse(text):
    return re.sub(r"\s+", " ", text)


def source(path):
    return open(path).read()


def wait_value(path):
    text = source(path)
    start = text.index("readingsToWaitForAFirstContextMenu :")
    return int(re.search(r"readingsToWaitForAFirstContextMenu =\s*(\d+)",
                         text[start:start + 300]).group(1))


def history_depth(path):
    """How many steps of effects history the framework keeps."""
    text = source(path)
    start = text.index(":: stateBefore.lastStepsEffects")
    return int(re.search(r"List\.take (\d+)", text[start:start + 120]).group(1))


class FirstMenuWait(unittest.TestCase):
    def test_the_wait_covers_the_observed_render_gap(self):
        """10+ readings was measured live; a shorter wait re-clicks into it."""
        for path in COPIES:
            with self.subTest(bot=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                self.assertGreaterEqual(
                    wait_value(path), 10,
                    "the wait must cover the 10+ reading gap its own comment records")

    def test_the_wait_is_bounded_by_the_history(self):
        """It cannot become the unbounded search the original cap guarded against."""
        for path in COPIES:
            with self.subTest(bot=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                self.assertLessEqual(
                    wait_value(path), history_depth(path),
                    "looking back further than the history keeps would be meaningless")

    def test_the_wait_is_a_named_constant(self):
        for path in COPIES:
            with self.subTest(bot=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                text = source(path)
                self.assertIn("List.take readingsToWaitForAFirstContextMenu", text,
                              "the wait reads a named constant, not a bare number")
                self.assertNotIn("|> List.take 2\n", text,
                                 "the old two-reading cap is gone")

    def test_every_copy_agrees(self):
        self.assertEqual(len({wait_value(p) for p in COPIES}), 1,
                         "all four vendored copies wait the same number of readings")

    def test_it_quits_early_on_a_win(self):
        """Waiting longer costs a healthy cascade nothing.

        The wait branch is only reachable on the empty-list arm, so any menu at
        all in the reading takes the other branch immediately -- the wait can
        only ever delay the case that would otherwise destroy its own menu.
        """
        for path in COPIES:
            with self.subTest(bot=os.path.basename(os.path.dirname(os.path.dirname(path)))):
                text = source(path)
                start = text.index("case List.reverse context.readingFromGameClient.contextMenus of")
                arm = collapse(text[start:start + 200])
                self.assertRegex(arm, r"contextMenus of \[\] ->",
                                 "the wait sits on the no-menus arm only")
                after = text.index("readingsToWaitForAFirstContextMenu", start)
                following = text.index("cascadeFirstElement :: cascadeFollowingElements", start)
                self.assertLess(after, following,
                                "and the populated arm follows it, reached without waiting")


if __name__ == "__main__":
    unittest.main()
