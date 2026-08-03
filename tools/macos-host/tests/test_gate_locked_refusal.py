"""Tests for the mission runner's reading of EVE's "This gate is locked!" refusal.

Run 10 pressed the Selected Item panel's Activate on an acceleration gate 32 m
away, nine times in two minutes, and the client answered every press on its own
`info` channel:

    This gate is locked! To activate it, you need to have R.S. Officer's
    Passcard in your cargo hold. By all signs it will not be consumed upon use,
    so the only problem is to locate the thing!

Nothing read it. The same refusal also arrives as a message box, which the bot
dismissed as generic noise, so the exchange was press, dismiss, press -- until
`gateWithinReachTicks` ran out, `activateAccelerationGateIfPresent` began
returning `Nothing`, and the log said "nothing to fight and no travel step
offered" for 1,325 readings before the bottom of the tree raised the alarm.

**The selectivity is the point, not the match.** The recorded game logs hold two
different sentences opening "This gate is locked!", and they want opposite
responses:

    ... There are synchronized gate scramblers on all hostile entities in this
    area ... you must simply clear the vicinity of enemy ships. So grab your
    guns.

That gate opens by itself once the pocket is clear, and the bot already answers
it correctly by fighting. A matcher on the exclamation alone would stop a run
that was about to succeed, so `in your cargo hold` is load-bearing and these
cases fail if it goes away.

The substrings are read out of `Bot.elm` rather than restated, for the reason
`test_ammo_load_refusal.py` reads its own: a matcher that drifts from what the
client writes fails in the direction that looks like success -- no refusal is
ever seen and the branch never fires.

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

# Both quoted verbatim from ~/Documents/EVE/logs/Gamelogs. The first is the one
# the gate branch has to act on; the second is the one it must leave alone.
LOCKED_FOR_WANT_OF_AN_ITEM = (
    "This gate is locked! To activate it, you need to have R.S. Officer's "
    "Passcard in your cargo hold. By all signs it will not be consumed upon "
    "use, so the only problem is to locate the thing!")

LOCKED_UNTIL_THE_POCKET_IS_CLEAR = (
    "This gate is locked! There are synchronized gate scramblers on all "
    "hostile entities in this area. Unless you are physically inside one of "
    "them to unscramble the signal, you must simply clear the vicinity of "
    "enemy ships. So grab your guns.")

# Other things the client said on the same channel during the recorded
# sessions. None of them is about a gate at all.
OTHER_INFO_LINES = [
    "The transport has not yet been connected, or authentication was not "
    "successful.",
    "5.00 cargo units would be required to complete this operation. "
    "Destination container only has 1.99 units available.",
    "There are no free slots on the ship. Unfit some modules first.",
    "A recent transit through this wormhole has polarized your secondary "
    "coils, making it unsafe to re-enter right now.",
]


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def matcher_body(source):
    start = source.index("gateLockedForWantOfAnItemFromGameLog : ReadingFromGameClient")
    end = source.index("\n\n\n", start)
    return source[start:end]


def matcher_substrings(source):
    return re.findall(r'stringContainsIgnoringCase "([^"]+)"', matcher_body(source))


def matches(text, substrings):
    """What the matcher's filter does, on one line of text."""
    return all(sub.lower() in text.lower() for sub in substrings)


def record_field_body(source, name):
    """The right-hand side of one field of the `BotMemory` record update.

    Fields are written one per line as `    , name =`, so the next line at that
    indent ends this one -- including the comment introducing it, which is why
    the terminator is any non-space.
    """
    opening = "\n    , " + name + " =\n"
    start = source.index(opening) + len(opening)
    rest = source[start:]
    end = re.search(r"\n    [,}]", rest)
    return rest[:end.start()] if end else rest


def branch_results(body):
    """The value each branch of an `if`/`else if` chain evaluates to."""
    results = []
    for line in body.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped == "else" or (
                stripped.startswith(("if ", "else if ")) and stripped.endswith(" then")):
            continue
        results.append(stripped)
    return results


def branch_conditions(body):
    """The condition each `if`/`else if` branch tests."""
    conditions = []
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("if ", "else if ")) and stripped.endswith(" then"):
            conditions.append(stripped)
    return conditions


class MatcherIsReadFromTheElm(unittest.TestCase):
    def setUp(self):
        self.substrings = matcher_substrings(bot_elm())

    def test_two_substrings_are_found(self):
        self.assertEqual(
            len(self.substrings), 2,
            "expected gateLockedForWantOfAnItemFromGameLog to match on two "
            "substrings -- one of them is what separates the locked gate the "
            "bot cannot open from the one it is already clearing")

    def test_one_substring_is_the_cargo_hold_requirement(self):
        # The whole distinction between the two sentences lives here. Without
        # it the matcher fires on a gate that opens once the rats are dead.
        self.assertIn(
            "in your cargo hold",
            [substring.lower() for substring in self.substrings])

    def test_neither_substring_names_the_mission_s_own_item(self):
        # "R.S. Officer's Passcard" is this mission's item. A matcher carrying
        # it would work on exactly one mission.
        for substring in self.substrings:
            self.assertNotIn("passcard", substring.lower())
            self.assertNotIn("officer", substring.lower())

    def test_the_matcher_reads_the_info_channel(self):
        # The line arrives on `info`, not `notify` -- every other consumer of
        # the game log in this bot reads `notify`, and copying one of those
        # would give a matcher that can never fire.
        self.assertIn("gameLogEntryIsFromInfoChannel", matcher_body(bot_elm()))


class MatchesTheRefusalItMustActOn(unittest.TestCase):
    def setUp(self):
        self.substrings = matcher_substrings(bot_elm())

    def test_matches_the_line_from_run_10(self):
        self.assertTrue(matches(LOCKED_FOR_WANT_OF_AN_ITEM, self.substrings))

    def test_matches_regardless_of_case(self):
        self.assertTrue(matches(LOCKED_FOR_WANT_OF_AN_ITEM.upper(), self.substrings))

    def test_matches_the_same_requirement_for_another_item(self):
        # The item's name sits in the middle of the sentence, so the bot must
        # not have to be told about each mission item it might ever need.
        self.assertTrue(matches(
            "This gate is locked! To activate it, you need to have Zbikoki's "
            "Hacker Card in your cargo hold.",
            self.substrings))


class LeavesTheGateThatOpensItself(unittest.TestCase):
    """The case that decides whether this feature helps or hurts."""

    def setUp(self):
        self.substrings = matcher_substrings(bot_elm())

    def test_does_not_match_the_scrambled_gate(self):
        self.assertFalse(
            matches(LOCKED_UNTIL_THE_POCKET_IS_CLEAR, self.substrings),
            "would have asked for help on a gate that opens as soon as the "
            "bot finishes the fight it is already winning")

    def test_does_not_match_the_exclamation_on_its_own(self):
        self.assertFalse(matches("This gate is locked!", self.substrings))

    def test_does_not_match_the_client_s_other_info_lines(self):
        for line in OTHER_INFO_LINES:
            self.assertFalse(matches(line, self.substrings),
                             "would have fired the gate branch on: " + line)


class TheVerdictIsBothWrittenAndRead(unittest.TestCase):
    """Neither half on its own does anything, and both compile.

    Issue #12 shipped a guard that was written and never read; #15 shipped one
    that was read and could never be true. A memory field needs the pair.
    """

    def setUp(self):
        self.source = bot_elm()

    def test_the_field_is_written_in_the_memory_update(self):
        self.assertIn("\n    , gateLockedForWantOfAnItem =\n", self.source)

    def test_the_field_is_read_by_the_gate_branch(self):
        start = self.source.index(
            "activateAccelerationGateIfPresent : BotDecisionContext")
        end = self.source.index("\n\n\n", start)
        self.assertIn("context.memory.gateLockedForWantOfAnItem",
                      self.source[start:end])

    def test_the_locked_verdict_is_checked_before_the_range_test(self):
        # Ordering, not preference: a gate the client has said is shut is not
        # worth flying at, and the approach branch is what would fly at it.
        start = self.source.index(
            "activateAccelerationGateIfPresent : BotDecisionContext")
        body = self.source[start:self.source.index("\n\n\n", start)]
        self.assertLess(
            body.index("gateLockedForWantOfAnItem"),
            body.index("gateCanBeActivatedNow"),
            "the locked verdict must be tested before the approach branch")

    def test_the_verdict_can_be_forgotten_again(self):
        # It is not latched for the session, unlike `shipLoss`: that verdict
        # ends the run, this one asks for help while the run continues, so a
        # gate opened by hand must not still read as locked afterwards.
        body = record_field_body(self.source, "gateLockedForWantOfAnItem")
        self.assertIn("Nothing", branch_results(body))


class TheGateBudgetIsSpentByTheOffer(unittest.TestCase):
    """`gateWithinReachTicks` counts refusals, not time parked near a gate.

    Counting proximity is the same mistake `dronesInSpaceTicks` made about the
    drone recall: it spends the budget on readings that are not evidence. The
    gate whose own message says "clear the vicinity of enemy ships" is precisely
    a long fight inside `interactionRangeInMeters`, and that fight is far longer
    than the budget.
    """

    def setUp(self):
        self.body = record_field_body(bot_elm(), "gateWithinReachTicks")

    def test_only_the_panel_s_offer_increments_it(self):
        conditions = branch_conditions(self.body)
        self.assertTrue(conditions, "expected an if/else chain")
        self.assertIn("selectedItemOffersActivateGate", conditions[0],
                      "the incrementing branch must be the one where the "
                      "client was offering to open the gate")

    def test_a_gate_in_reach_without_the_offer_holds_the_count(self):
        # A reset there is the shape that held `gunsSilencedTicks` at 1
        # forever: the message box the client raises between every attempt is
        # exactly such a reading.
        self.assertIn("botMemoryBefore.gateWithinReachTicks",
                      branch_results(self.body))

    def test_every_branch_resets_holds_or_increments(self):
        previous = "botMemoryBefore.gateWithinReachTicks"
        allowed = {"0", "1", previous, previous + " + 1"}
        for result in branch_results(self.body):
            self.assertIn(
                result, allowed,
                "gateWithinReachTicks has a branch evaluating to " +
                repr(result) + " -- a counter may only reset, start, hold or "
                "increment")

    def test_it_can_advance(self):
        self.assertIn("botMemoryBefore.gateWithinReachTicks + 1",
                      branch_results(self.body),
                      "gateWithinReachTicks never increments, so the bound "
                      "reading it can never be reached")

    def test_it_can_reset(self):
        self.assertIn("0", branch_results(self.body),
                      "gateWithinReachTicks never resets, so it would carry "
                      "one grid's refusals onto the next")


class AgainstTheRecordedGameLogs(unittest.TestCase):
    """The same check against whatever the client actually wrote.

    Skipped when the game logs are absent, since they are not in the
    repository -- the same shape as the recorded-runs case in
    `test_ammo_load_refusal.py`.
    """

    def locked_gate_lines(self):
        lines = set()
        pattern = os.path.expanduser("~/Documents/EVE/logs/Gamelogs/*.txt")
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    for found in re.findall(r"This gate is locked![^<\n]*", line):
                        lines.add(found.strip())
        return sorted(lines)

    def test_matcher_selects_only_the_gates_wanting_an_item(self):
        lines = self.locked_gate_lines()
        if not lines:
            self.skipTest("no recorded game logs in ~/Documents/EVE/logs/Gamelogs")
        substrings = matcher_substrings(bot_elm())
        for line in lines:
            wants_an_item = "in your cargo hold" in line.lower()
            self.assertEqual(
                matches(line, substrings), wants_an_item,
                "matcher disagrees with the client on: " + line)


if __name__ == "__main__":
    unittest.main()
