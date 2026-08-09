"""A rank-bearing rat's wreck is recognised whatever word EVE used for the rank.

`isNotableWreck` matched "commander" and "overseer" only, so
`Sansha Black Ops Squad Leader` -- whose wreck is worth what the
`Centus Black Ops Commander` beside it is worth -- was filtered out before
looting and the bot went to the acceleration gate instead. Reported live, and
the recorded runs bear it out: those two are the only rank-bearing rats in the
whole corpus and only the first was ever looted, while the loot path itself ran
4,616 times in the same runs.

These cases pin the words against the corpus rather than against this file, so a
rat the runs actually contain cannot be dropped from the list unnoticed.
"""
import glob
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
APPS = os.path.join(REPO, "implement", "applications", "eve-online")
LOGS = os.path.expanduser("~/eve-bot-logs")

BOTS = [
    os.path.join(APPS, app, "Bot.elm")
    for app in ("eve-online-saxrat", "eve-online-mission-runner")
]

# Rank-bearing rats the recorded runs contain. Both are Black Ops rats of
# equivalent standing; EVE simply named their ranks differently.
RANK_RATS = ["Centus Black Ops Commander", "Sansha Black Ops Squad Leader"]


def rank_words(path):
    text = open(path).read()
    start = text.index("notableRatRankWords =")
    block = text[start:start + 200]
    return re.findall(r'"([a-z ]+)"', block)


def recorded_lines():
    """Every saxrat log line, or None when the corpus is not on this machine."""
    paths = sorted(glob.glob(os.path.join(LOGS, "saxrat_run*.log")))
    if not paths:
        return None
    lines = []
    for path in paths:
        with open(path, errors="ignore") as handle:
            lines.extend(handle)
    return lines


class NotableWreckRanks(unittest.TestCase):
    def test_every_recorded_rank_rat_is_matched(self):
        """The words must cover the rats the runs actually contain."""
        for path in BOTS:
            words = rank_words(path)
            for rat in RANK_RATS:
                with self.subTest(bot=os.path.basename(os.path.dirname(path)), rat=rat):
                    self.assertTrue(
                        any(word in rat.lower() for word in words),
                        "%r matches none of %r, so its wreck is skipped" % (rat, words))

    def test_leader_is_present(self):
        """The word this fix adds, named so removing it fails here."""
        for path in BOTS:
            with self.subTest(bot=os.path.basename(os.path.dirname(path))):
                self.assertIn("leader", rank_words(path))

    def test_both_bots_agree(self):
        self.assertEqual(len({tuple(rank_words(p)) for p in BOTS}), 1,
                         "both bots judge a notable wreck by the same words")

    def test_the_rank_rats_are_in_the_corpus(self):
        """Guards the premise: these are real names, not invented for the test."""
        lines = recorded_lines()
        if lines is None:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        joined = "".join(lines)
        for rat in RANK_RATS:
            with self.subTest(rat=rat):
                self.assertIn(rat, joined, "the corpus should contain this rat")

    def test_leader_has_no_other_referent(self):
        """"leader" is safe as a substring only while nothing else uses it.

        A wider word would risk the trap `containsWords` exists for -- a rogue
        drone called a "Wrecker" contains "wreck". If a future run introduces
        some other object whose name carries "leader", this fails and the word
        needs narrowing to the phrase.
        """
        lines = recorded_lines()
        if lines is None:
            self.skipTest("no recorded runs in ~/eve-bot-logs")
        others = set()
        for line in lines:
            for match in re.finditer(r"[A-Za-z'][A-Za-z' ]{0,30}[Ll]eader", line):
                text = match.group(0).strip()
                if "Squad Leader" not in text:
                    others.add(text[-40:])
        self.assertEqual(others, set(),
                         "something other than the Squad Leader carries 'leader'")


if __name__ == "__main__":
    unittest.main()
