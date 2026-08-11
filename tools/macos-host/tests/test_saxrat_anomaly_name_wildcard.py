"""Tests for `anomaly-name` matching a trailing `*` as a prefix.

`anomaly-name` is compared **whole**, so an operator who wants every Sansha site
had to enumerate them -- and getting that list wrong is silent. Run 19 sat in a
system holding `Sansha Burrow`, `Sansha Hideaway`, `Sansha Refuge` and
`Drone Assembly` while the shipped default asked for `sansha rally point` and
`angel rally point`, and simply reported `no matching anomaly` for as long as it
was left there.

`anomaly-name=Sansha*` is the answer, and the cases below are mostly about the
ways a wildcard could widen more than was asked for:

- **Exact stays the default.** Only an entry ending in `*` is a prefix; every
  other entry is compared whole, so no existing settings string changes meaning.
  `attack-object` records what an accidental substring costs -- a wreck's Type
  is its owner's name with " Wreck" appended, so the bot fired on the corpse of
  what it had just killed.
- **Only a trailing `*`.** Site names read `Sansha <adjective> <noun>`, so a
  prefix is the shape the client's own naming produces. A `*` anywhere else is
  not special and stays part of the literal, which a case pins.
- **An empty list still means everything**, unchanged, and is a different thing
  from a list whose entries match nothing -- the distinction that made run 19
  look broken rather than misconfigured.

The rule is executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, against the names the live scanner actually showed.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")

PREAMBLE = ("import Bot exposing (..)",)

# Read off the live probe scanner, verbatim.
ON_THE_SCANNER = [
    "Sansha Burrow",
    "Sansha Hideaway",
    "Sansha Refuge",
    "Drone Assembly",
    "Dread Assault: Blood Raider Temple",
]


class SaxratRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-anomalyname-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class TheWildcardMatchesAPrefixTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def match(self, name, entry):
        return 'anomalyNameMatches "%s" "%s"' % (name, entry)

    def test_sansha_star_takes_every_sansha_site_on_the_scanner(self):
        sansha = [n for n in ON_THE_SCANNER if n.startswith("Sansha")]
        self.assertEqual(
            self.repl.evaluate([self.match(n, "Sansha*") for n in sansha]),
            [True] * len(sansha))

    def test_sansha_star_takes_nothing_else_on_the_scanner(self):
        others = [n for n in ON_THE_SCANNER if not n.startswith("Sansha")]
        self.assertEqual(
            self.repl.evaluate([self.match(n, "Sansha*") for n in others]),
            [False] * len(others))

    def test_case_and_surrounding_space_do_not_matter(self):
        self.assertEqual(
            self.repl.evaluate([
                self.match("Sansha Burrow", "  sansha*  "),
                self.match("Sansha Burrow", "SANSHA*"),
                self.match("Sansha Burrow", "Sansha *"),
            ]),
            [True, True, True])

    def test_an_entry_without_a_star_is_still_matched_whole(self):
        """The default, and the behaviour every existing settings string has."""
        self.assertEqual(
            self.repl.evaluate([
                self.match("Sansha Burrow", "Sansha Burrow"),
                self.match("Sansha Burrow", "Sansha"),
                self.match("Sansha Burrow", "Burrow"),
                self.match("Sansha Burrow", "Sansha Bur"),
            ]),
            [True, False, False, False])

    def test_a_star_that_is_not_at_the_end_is_a_literal(self):
        self.assertEqual(
            self.repl.evaluate([
                self.match("Sansha Burrow", "San*ha Burrow"),
                self.match("San*ha Burrow", "San*ha Burrow"),
            ]),
            [False, True])

    def test_a_prefix_cannot_match_a_shorter_name(self):
        self.assertEqual(
            self.repl.evaluate([
                self.match("Sansha", "Sansha Burrow*"),
                self.match("Sansha Burrow", "Sansha Burrow*"),
            ]),
            [False, True])

    def test_the_wildcard_does_not_care_where_in_the_list_it_sits(self):
        """`List.any`, so one wildcard among exact entries still matches."""
        self.assertEqual(
            self.repl.evaluate([
                self.match("Sansha Refuge", "Drone Assembly"),
                self.match("Sansha Refuge", "Sansha*"),
            ]),
            [False, True])


class TheHeaderSaysWhatTheWildcardCostsTest(unittest.TestCase):
    """`--help` is generated from this section, so it is where an operator reads
    that a wildcard cannot tell an easy site from a lethal one."""

    def setUp(self):
        with open(SAXRAT_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()
        self.bullet = self._bullet("anomaly-name")

    def _bullet(self, key):
        match = re.search(r"\+ `%s`[^\n]*(?:\n(?!\s*\+ `)[^\n]*)*"
                          % re.escape(key), self.source)
        if match is None:
            raise AssertionError("no header bullet for " + key)
        return re.sub(r"\s+", " ", match.group(0))

    def test_the_bullet_documents_the_wildcard(self):
        self.assertIn("*", self.bullet)
        self.assertIn("Sansha*", self.bullet)

    def test_the_bullet_says_matching_is_whole_by_default(self):
        self.assertIn("whole", self.bullet)

    def test_the_bullet_states_the_danger_rather_than_only_the_feature(self):
        lowered = self.bullet.lower()
        self.assertTrue("kill" in lowered or "haven" in lowered,
                        "an operator reading --help should learn what a "
                        "wildcard can drag the ship into: %s" % self.bullet)


if __name__ == "__main__":
    unittest.main()
