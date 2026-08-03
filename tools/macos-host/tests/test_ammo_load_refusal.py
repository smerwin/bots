"""Tests for the mission runner's reading of EVE's "cannot load or unload" refusal.

The ammo swap is the first consumer of the game log channel #28 added. When the
client throws a load away it says so in its own log and nowhere else, so the
branch that acts on that has to recognise one sentence among the several
refusals the client makes -- and recognise it across fittings, since the
weapon's own name sits in the middle of it:

    You cannot load or unload Focused Modulated Medium Energy Beam I while it is active.

**The wording is the risk, so the wording is what is pinned.** These cases read
the two substrings out of `Bot.elm` itself rather than restating them, for the
reason `VendoredParserTest` pins the synthetic node's type name across the two
languages: a matcher that drifts from what the client actually writes fails in
the direction that looks like success -- no refusal is ever seen, the branch
never fires, and the swap goes back to waiting out its bound with nothing to
show for it.

The corpus is real. Every line here was written by the client during a recorded
run and echoed into `~/eve-bot-logs/mission_run*.log`; the counts across those
five runs were 17 drone-control refusals, 4 "while warping", 3 loads refused, 2
"while docking" and 1 module-activation. Selectivity matters as much as
matching: four of those five must *not* trigger an ammo branch.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Quoted verbatim from the recorded runs. The first is the one the ammo swap
# has to act on; the rest are the other refusals the same client made, and are
# here to keep the matcher from widening into them.
LOAD_REFUSAL = (
    "You cannot load or unload Focused Modulated Medium Energy Beam I "
    "while it is active.")

OTHER_REFUSALS = [
    "You cannot launch Acolyte I because you are already controlling 5 drones, "
    "as much as you have skill to.",
    "You cannot do that while warping.",
    "You cannot do that while docking.",
    "You cannot activate that module as the target is no longer present.",
]

# The same sentence from a different fitting. The bot must not have to be told
# about each weapon it might ever fly.
LOAD_REFUSAL_OTHER_FITTING = (
    "You cannot load or unload 425mm AutoCannon II while it is active.")


def load_refusal_substrings():
    """The substrings `loadRefusalFromGameLog` actually matches on.

    Read out of the Elm rather than restated, so that changing the matcher
    without checking it against real lines fails here.
    """
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as bot_elm:
        source = bot_elm.read()
    start = source.index("loadRefusalFromGameLog : ReadingFromGameClient")
    end = source.index("gameLogEntryIsFromNotifyChannel :", start)
    return re.findall(r'stringContainsIgnoringCase "([^"]+)"', source[start:end])


def matches(text, substrings):
    """What `loadRefusalFromGameLog`'s filter does, on one line of text."""
    return all(sub.lower() in text.lower() for sub in substrings)


class MatcherIsReadFromTheElm(unittest.TestCase):
    def test_two_substrings_are_found(self):
        # Two, not one: `cannot` alone catches every refusal the client makes,
        # and the whole line is per-fitting.
        self.assertEqual(len(load_refusal_substrings()), 2,
                         "expected loadRefusalFromGameLog to match on two substrings")

    def test_neither_substring_contains_a_weapon_name(self):
        # The weapon's name sits between the two halves of the sentence. A
        # substring carrying part of it would work on exactly one fitting.
        for substring in load_refusal_substrings():
            self.assertNotIn("beam", substring.lower())
            self.assertNotIn("modulated", substring.lower())


class MatchesTheRealRefusal(unittest.TestCase):
    def setUp(self):
        self.substrings = load_refusal_substrings()

    def test_matches_the_line_from_the_recorded_runs(self):
        self.assertTrue(matches(LOAD_REFUSAL, self.substrings))

    def test_matches_the_same_refusal_on_another_fitting(self):
        self.assertTrue(matches(LOAD_REFUSAL_OTHER_FITTING, self.substrings))

    def test_matches_regardless_of_case(self):
        self.assertTrue(matches(LOAD_REFUSAL.upper(), self.substrings))

    def test_does_not_match_the_client_s_other_refusals(self):
        for line in OTHER_REFUSALS:
            self.assertFalse(matches(line, self.substrings),
                             "would have fired the ammo branch on: " + line)

    def test_does_not_match_an_unload_that_succeeded(self):
        # "load or unload" appears in the refusal only. A line merely
        # mentioning loading must not read as a refusal.
        self.assertFalse(matches("Loading Multifrequency M.", self.substrings))


class AgainstTheRecordedRuns(unittest.TestCase):
    """The same check against whatever the recorded runs actually hold.

    Skipped when those logs are absent, since they are not in the repository --
    the same shape as the recorded-runs case in `test_game_log_channel.py`.
    """

    def refusal_lines(self):
        lines = []
        pattern = os.path.expanduser("~/eve-bot-logs/mission_run*.log")
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    for found in re.findall(r"You cannot [^<\n]*", line):
                        lines.append(found.strip())
        return lines

    def test_matcher_selects_only_the_load_refusals(self):
        lines = self.refusal_lines()
        if not lines:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        substrings = load_refusal_substrings()
        for line in set(lines):
            expected = "load or unload" in line and "while it is active" in line
            self.assertEqual(matches(line, substrings), expected,
                             "matcher disagreed about: " + line)

    def test_at_least_one_load_refusal_is_present(self):
        # Guards the case above from passing vacuously on a corpus that happens
        # to contain no load refusal at all.
        lines = self.refusal_lines()
        if not lines:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        substrings = load_refusal_substrings()
        self.assertTrue(any(matches(line, substrings) for line in lines))


if __name__ == "__main__":
    unittest.main()
