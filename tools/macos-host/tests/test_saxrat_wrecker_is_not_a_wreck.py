"""Tests for a live rat that contains the word "wreck" (run 44).

`Wrecker Alvum` is a rogue drone. Both of saxrat's "is this loot rather than
something to shoot" sites matched it with `stringContainsIgnoringCase "wreck"`,
so the bot classified a live rat as a container.

The expensive half is not the unlock. `activeTargetOverviewEntryIsStray` is
consulted by the *fighting* branch, which answers

    "The active target looks like a container/wreck, not a rat -- hold fire."

so the guns were held against a rat the ship was pointed at. Run 44 spent 36
minutes in one anomaly and 18 in another with the target reading 99% shield,
and issued 387 unlock decisions that could never finish.

The fix is the mission runner's, which has carried it since #53:
`textNamesALootableObject` matches whole words *because* "a rogue drone called a
'Wrecker' contains 'wreck'". saxrat already had `containsWords` -- its doc
comment names this exact rat -- and simply never used it at either site.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, overview, source_of)
from test_target_hitpoints import target

MISSION_RUNNER_BOT_ELM = os.path.join(
    os.path.dirname(SAXRAT_BOT_ELM), "..", "eve-online-mission-runner",
    "Bot.elm")

# Rows as `(distance, name, type)`, which is the overview's own column order.
# The rat is the one run 44 stalled on; the wreck's Name is its dead owner's,
# which is why the Type column is what carries the word.
THE_RAT = ("12,000 m", "Wrecker Alvum", "Wrecker Alvum")
A_PLAIN_RAT = ("8,000 m", "Centii Ravener", "Centii Ravener")
A_CONTAINER = ("2,000 m", "Cargo Container", "Cargo Container")
A_WRECK = ("1,500 m", "Sunder Alvi", "Gallente Small Wreck")


class StrayLockRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, with the two rules under test reachable."""

    HELPERS = [
        # Every parsed row, labelled by what the rule makes of it, so one
        # answer per row arrives as one string rather than a list of Bools.
        "verdictsOf = \\parsed -> parsed"
        " |> Maybe.map (.overviewWindows >> List.concatMap .entries"
        "   >> List.map (\\e ->"
        "        if overviewEntryIsStrayLockTarget e then \"loot\" else \"shoot\")"
        "   >> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
        # The count of rows the fixture actually produced, so a case cannot
        # pass on a reading that never arrived (#174).
        "rowsOf = \\parsed -> parsed"
        " |> Maybe.map (.overviewWindows >> List.concatMap .entries"
        "   >> List.length >> String.fromInt)"
        " |> Maybe.withDefault \"NO READING\"",
        "unlockNamesOf = \\parsed -> parsed"
        " |> Maybe.map (\\r -> targetsToUnlockFromReadingFromGameClient r"
        "   |> List.concatMap .textsTopToBottom |> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
        "targetNamesOf = \\parsed -> parsed"
        " |> Maybe.map (.targets"
        "   >> List.concatMap .textsTopToBottom >> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class TheOverviewSiteReadsWholeWordsTest(unittest.TestCase):
    """`overviewEntryIsStrayLockTarget`, executed on really parsed rows.

    This is the site that holds fire, so it is the one whose answer decides
    whether the guns fire at all.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StrayLockRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def verdicts(self, rows):
        binding = self.repl.reading_binding("reading", [overview(rows)])
        rows_seen, verdicts = self.repl.strings(
            ["rowsOf reading", "verdictsOf reading"],
            definitions=self.repl.with_helpers([binding]))
        self.assertEqual(
            rows_seen, str(len(rows)),
            "the fixture did not reach the parser as %d rows (got %r) -- a "
            "case over a reading that never arrived proves nothing"
            % (len(rows), rows_seen))
        return verdicts.split(",")

    def test_the_rat_run_44_stalled_on_is_something_to_shoot(self):
        """The whole point: `Wrecker Alvum` is a rat, not loot."""
        self.assertEqual(self.verdicts([THE_RAT]), ["shoot"])

    def test_a_container_is_still_loot(self):
        self.assertEqual(self.verdicts([A_CONTAINER]), ["loot"])

    def test_a_wreck_is_still_loot_by_its_type_column(self):
        """A wreck's Name is its dead owner's, so the Type carries the word --
        which is why the rule reads both columns and must go on doing so."""
        self.assertEqual(self.verdicts([A_WRECK]), ["loot"])

    def test_an_ordinary_rat_was_never_affected(self):
        """The control: a name with no "wreck" in it answered the same before
        and after, so a case passing here says nothing on its own."""
        self.assertEqual(self.verdicts([A_PLAIN_RAT]), ["shoot"])

    def test_the_four_together_separate_on_one_grid(self):
        """All four on one overview, which is what a real anomaly looks like
        once the rats are dead and the wrecks are not."""
        self.assertEqual(
            self.verdicts([A_WRECK, A_CONTAINER, A_PLAIN_RAT, THE_RAT]),
            ["loot", "loot", "shoot", "shoot"])


class TheTargetBarSiteReadsWholeWordsTest(unittest.TestCase):
    """`targetsToUnlockFromReadingFromGameClient`, on a real target bar.

    This is the site that issues the unlock. It reads the bar's own text rather
    than cross-referencing the overview, and that is deliberate -- see its doc
    comment -- so the fixture puts the name where the client puts it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StrayLockRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def unlocked(self, names):
        binding = self.repl.reading_binding(
            "reading", [target(name, []) for name in names])
        seen, unlocked = self.repl.strings(
            ["targetNamesOf reading", "unlockNamesOf reading"],
            definitions=self.repl.with_helpers([binding]))
        for name in names:
            self.assertIn(
                name, seen,
                "the fixture did not reach the parser carrying %r (bar reads "
                "%r) -- a case over a target bar that never arrived proves "
                "nothing" % (name, seen))
        return unlocked

    def test_the_rat_is_not_asked_to_be_unlocked(self):
        self.assertNotIn("Wrecker Alvum", self.unlocked(["Wrecker Alvum"]))

    def test_a_container_is_still_asked_to_be_unlocked(self):
        self.assertIn("Cargo Container", self.unlocked(["Cargo Container"]))

    def test_a_wreck_is_still_asked_to_be_unlocked(self):
        self.assertIn("Gallente Small Wreck",
                      self.unlocked(["Gallente Small Wreck"]))

    def test_the_rat_is_left_alone_with_a_container_beside_it(self):
        """Both locked at once: the container is unlocked and the rat is not,
        which a rule answering the whole bar one way could not do."""
        unlocked = self.unlocked(["Wrecker Alvum", "Cargo Container"])
        self.assertIn("Cargo Container", unlocked)
        self.assertNotIn("Wrecker Alvum", unlocked)


class NeitherSiteSubstringMatchesTest(unittest.TestCase):
    """Read out of the source, since a substring test is what the bug was.

    Both rules are asked for their own body rather than for the file, so a
    third site adopting `stringContainsIgnoringCase` elsewhere is not what
    these go red on.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_the_overview_site_matches_on_word_boundaries(self):
        body = body_of(self.source, "overviewEntryIsStrayLockTarget")
        self.assertIn("containsWords", body)
        self.assertNotIn("stringContainsIgnoringCase", body)

    def test_the_target_bar_site_matches_on_word_boundaries(self):
        body = body_of(self.source,
                       "targetsToUnlockFromReadingFromGameClient")
        self.assertIn("containsWords", body)
        self.assertNotIn("stringContainsIgnoringCase", body)

    def test_both_sites_still_look_for_the_same_two_words(self):
        """The patterns are untouched -- this change is the matcher and not
        the vocabulary, so a container is still found by "container"."""
        for name in ("overviewEntryIsStrayLockTarget",
                     "targetsToUnlockFromReadingFromGameClient"):
            body = body_of(self.source, name)
            self.assertIn('"container"', body, name)
            self.assertIn('"wreck"', body, name)

    def test_the_mission_runner_reads_the_same_way(self):
        """The precedent this follows, so the two bots cannot drift apart on
        the question again."""
        body = body_of(source_of(MISSION_RUNNER_BOT_ELM),
                       "textNamesALootableObject")
        self.assertIn("containsWords", body)
        self.assertNotIn("stringContainsIgnoringCase", body)


class TheHoldFireBranchIsWhatThisCostTest(unittest.TestCase):
    """Why the overview site is the expensive one, read out of the source.

    The unlock can fail and cost readings; holding fire needs no cascade to
    land and nothing bounds it, so a rat misread here is a rat that never dies.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_the_fighting_branch_consults_the_overview_rule(self):
        body = body_of(self.source, "activeTargetOverviewEntryIsStray")
        self.assertIn("overviewEntryIsStrayLockTarget", body)

    def test_holding_fire_is_what_that_answer_does(self):
        """Two call sites, both answering the same way, both reachable while a
        target is locked."""
        flat = re.sub(r"\s+", " ", self.source)
        held = flat.count(
            "The active target looks like a container/wreck, not a rat "
            "-- hold fire.")
        self.assertGreaterEqual(
            held, 2,
            "the hold-fire answer is what a wrong verdict here costs; if this "
            "branch is gone the argument in both doc comments is stale")


if __name__ == "__main__":
    unittest.main()
