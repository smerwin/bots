"""Tests for the status clause that reprinted the client's combat widget.

Issue #190. `describeVisibleCombatMessages` rendered up to six lines of
`eve-online-saxrat`'s `CombatMessage` widget into the status text on every
reading, and it was the largest single thing in the log while being almost none
of its information: a third of run 20's and run 21's lines, and 1,376 of run
20's 1,377 feed blocks byte-identical to the block before them. It is removed,
and `visibleCombatMessages` -- the scraper under it -- is kept unused, which is
exactly what `eve-online-mission-runner` did when it dropped the same clause.

**The removal changes no behaviour**, which is what makes it a removal rather
than a retuning: the clause was read by the status line at one site and by no
decision, so the cases below assert the scraper still answers and that nothing
prints it.

**Nothing replaces it, and that is the judgement this file pins.** The incoming
half of the same channel is already in the status line on every reading, summed
host-side and scoped to the reading, as `describeIncomingDamage` -- the window,
the threshold, whether the host carries the channel at all, and the attackers
named. A second clause derived from the same channel would say what that one
already says, on a reading the whole issue is about the log being too big.
`TheChannelIsStillReportedTest` is what would go red if that clause were ever
dropped, since dropping it is what would turn this removal into a loss.

**The widget outlives the fight, which is the half a summary line could not have
fixed either.** Messages age off the *screen*, not off the grid, so run 20
printed 1,344 of its 1,377 feed blocks on readings whose own decision line says
the ship is docked. Run 21 shows almost none of that, so it depends on the
run's shape rather than being universal -- and nothing in the feed distinguished
the two, which is why it is recounted below as a relation rather than as a rate.

The corpus cases read `~/eve-bot-logs` and skip where it is absent, with the
wording every other saxrat corpus case skips with. Nothing here reads a live
game client or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, MISSION_RUNNER_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, collapsed, label, node, source_of)
from test_quick_message_logged import top_level_declarations

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

# The scraper that is kept, and the marker declaration that says why. Named
# rather than discovered, so deleting either is a change these cases notice.
SCRAPER = "visibleCombatMessages"
MARKER = "combatFeedIsReportedByTheHostGameLog"

# The clause that was removed, and the string it put in the log. Both are
# checked for absence, because a reintroduction under the same name and a
# reintroduction that only prints the same text are the same regression.
REMOVED = "describeVisibleCombatMessages"
FEED_HEADING = "Combat feed"

# The clause that carries this channel now.
INCOMING = "describeIncomingDamage"


def saxrat_runs(*numbers):
    """The recorded saxrat runs this machine has, or the shared skip.

    saxrat's logs are named differently from the mission runner's, so
    `prerequisites.recorded_runs` does not reach them; this is the wording every
    other saxrat corpus case already skips with, and `check_expected_skips.py`
    refuses a second spelling of it.
    """
    logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
            for number in numbers]
    logs = [path for path in logs if os.path.exists(path)]
    if not logs:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
            "say about the combat feed cannot be consulted here")
    return logs


def feed_blocks(path):
    """Every combat-feed block in a recorded log, as its own list of lines.

    A block is the heading plus the indented lines under it, which is exactly
    what the removed clause emitted. `Combat feed: quiet.` is a block of one and
    is dropped: it carried no message, so counting it among the repeats would
    flatter the repetition this file is measuring.
    """
    blocks = []
    current = None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            text = line.rstrip("\n")
            if text.startswith(FEED_HEADING):
                if current is not None:
                    blocks.append(current)
                current = None if text.endswith("quiet.") else [text]
            elif current is not None:
                if text.startswith("  ") and text.strip():
                    current.append(text)
                else:
                    blocks.append(current)
                    current = None
    if current is not None:
        blocks.append(current)
    return blocks


def blocks_and_readings(path):
    """`(blocks, docked)` -- the feed blocks, and how many said "docked".

    Docked is read off the reading's own decision text rather than off the feed,
    because the point being measured is that the feed said nothing about it.
    """
    blocks = feed_blocks(path)
    docked = 0
    lines = None
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().split("\n")
    for index, text in enumerate(lines):
        if not text.startswith(FEED_HEADING) or text.endswith("quiet."):
            continue
        for follower in lines[index + 1:index + 30]:
            if follower.startswith(FEED_HEADING):
                break
            if "Looks like we are docked" in follower:
                docked += 1
                break
    return blocks, docked


def combat_message_widget(messages, top=200):
    """A `CombatMessage` node with one child per message.

    Each child carries several labels, because that is how the client splits a
    message -- the number, the preposition, the name and the effect are separate
    labels, which is why the scraper joins a child's texts rather than reading
    any one of them. The colour tagging is EVE's own and is what
    `stripHtmlTags` is there for.
    """
    return node("CombatMessage", {}, [
        node("CombatMessageEntry", {}, [
            label(text, (600, top + 20 * index + 4 * part, 300, 16))
            for part, text in enumerate(parts)
        ], region=(600, top + 20 * index, 300, 18))
        for index, parts in enumerate(messages)
    ], region=(600, top, 300, 20 * max(1, len(messages))))


class CombatFeedCases(unittest.TestCase):
    """The scraper executed, and the clause asserted gone.

    The readings go through the real `EveOnline.ParseUserInterface`, so what the
    scraper is asked about is what the bot would have been handed rather than a
    tree shaped to suit it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)
        cls.source = source_of(SAXRAT_BOT_ELM)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixture_parses_into_the_reading_the_cases_assume(self):
        """The tree first, before anything is concluded from the scraper.

        A scraper answering nothing about a reading that never arrived and one
        answering nothing about a widget it cannot read are the same answer from
        outside, which is what this control separates.
        """
        binding = SaxratRepl.reading_binding("reading", [
            combat_message_widget([["14", " from ", "Sentry Gun", " - Hits"]]),
        ])
        self.assertEqual([True], self.repl.evaluate(
            ["reading /= Nothing"], definitions=[binding]))

    def test_the_scraper_still_reads_the_widget(self):
        """`visibleCombatMessages` is kept and works, which is the whole point
        of keeping it -- a declaration retained but broken teaches nobody which
        nodes carry combat text."""
        binding = SaxratRepl.reading_binding("reading", [
            combat_message_widget([
                ["<color=0xffcc0000>14</color>", " from ", "Sentry Gun",
                 " - Hits"],
                ["22", " from ", "Centus Black Ops Veteran", " - Penetrates"],
            ]),
        ])
        self.assertEqual(
            ["14 from Sentry Gun - Hits"
             " || 22 from Centus Black Ops Veteran - Penetrates"],
            self.repl.strings(
                ['reading'
                 ' |> Maybe.map %s'
                 ' |> Maybe.withDefault []'
                 ' |> String.join " || "' % SCRAPER],
                definitions=[binding]))

    def test_a_reading_with_no_widget_scrapes_nothing(self):
        binding = SaxratRepl.reading_binding("reading", [])
        self.assertEqual([True], self.repl.evaluate(
            ['(reading |> Maybe.map %s |> Maybe.withDefault [ "x" ]) == []'
             % SCRAPER],
            definitions=[binding]))

    def test_the_clause_is_gone(self):
        """No declaration named `describeVisibleCombatMessages`, and none that
        names it.

        Asserted over the declarations rather than over the status line, because
        a clause restored and left uncalled is the half a wiring case cannot see
        and is one edit from being printed again. Doc comments are stripped, so
        the marker below may go on naming what it replaced.
        """
        declarations = top_level_declarations(self.source)
        self.assertNotIn(REMOVED, declarations)
        self.assertEqual(
            [], [name for name, body in declarations.items() if REMOVED in body])

    def test_nothing_prints_a_combat_feed(self):
        """The log string is gone too, so a clause rebuilt under another name
        is caught by what an operator would grep for."""
        self.assertNotIn(FEED_HEADING, self.source)

    def test_no_declaration_reads_the_scraper(self):
        """The scraper is unused, which is what "kept deliberately" means.

        Doc comments are stripped before counting, so the marker's own
        explanation of why it is kept does not read as a use of it.
        """
        readers = [name for name, body in top_level_declarations(
            self.source).items()
            if name != SCRAPER and SCRAPER in body]
        self.assertEqual([], readers)

    def test_the_marker_says_why_the_scraper_is_kept(self):
        """The declaration that carries the argument, and the three things it
        has to say: which issue, that the scraper is deliberate, and what
        reports this channel instead."""
        self.assertIn("%s : ()" % MARKER, self.source)
        doc = self.source[:self.source.index("%s : ()" % MARKER)]
        doc = collapsed(doc[doc.rindex("{-|"):])
        self.assertIn("#190", doc)
        self.assertIn(SCRAPER, doc)
        self.assertIn("kept deliberately", doc)
        self.assertIn(INCOMING, doc)

    def test_the_channel_is_still_reported(self):
        """`describeIncomingDamage` is still in the status line.

        This is the case that makes the removal a removal rather than a loss:
        the marker's doc says the incoming half is still printed every reading,
        and this is what holds that claim true.
        """
        self.assertIn(
            "++ %s context" % INCOMING,
            collapsed(top_level_declarations(self.source)["statusTextFromState"]))

    def test_the_mission_runner_is_the_precedent(self):
        """The sibling app dropped the same clause and kept the same scraper
        under the same marker name, so the two bots read alike here."""
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        self.assertIn("%s : ()" % MARKER, mission)
        self.assertIn(SCRAPER, mission)
        self.assertNotIn(REMOVED, mission)
        self.assertNotIn(FEED_HEADING, mission)


class TheRecordedRunsAreWhatTheIssueMeasuredTest(unittest.TestCase):
    """The corpus, recounted as relations rather than as the issue's numbers.

    A growing corpus must not turn a true claim red, and run 23 was still being
    written while this was measured -- so what is asserted is that the feed was
    a large share of the log, that nearly every block repeated the one before
    it, and that some run printed most of its blocks while docked. The issue's
    own rates are what those relations were derived from.
    """

    def test_the_feed_was_a_large_share_of_the_log(self):
        for path in saxrat_runs(20, 21, 22, 23):
            with self.subTest(log=os.path.basename(path)):
                with open(path, encoding="utf-8", errors="replace") as handle:
                    total = sum(1 for _ in handle)
                feed = sum(1 + len(block) - 1 for block in feed_blocks(path))
                if not feed:
                    continue
                self.assertGreater(feed, total // 10)

    def test_the_quiet_blocks_are_not_what_is_being_counted(self):
        """A quiet reading printed one line and carried no message, and a run of
        them repeats trivially.

        The repetition below is about blocks that said something, so this is
        what keeps that measurement from being satisfied by a run of `Combat
        feed: quiet.` -- and the corpus really does hold those, which is what
        makes the exclusion load-bearing rather than tidy.
        """
        quiet = 0
        for path in saxrat_runs(20, 21, 22, 23):
            with open(path, encoding="utf-8", errors="replace") as handle:
                quiet += sum(1 for line in handle
                             if line.startswith("%s: quiet." % FEED_HEADING))
            for block in feed_blocks(path):
                self.assertGreater(len(block), 1)
        self.assertGreater(quiet, 0)

    def test_nearly_every_block_repeated_the_one_before_it(self):
        looked = False
        for path in saxrat_runs(20, 21, 22, 23):
            blocks = feed_blocks(path)
            if len(blocks) < 100:
                continue
            looked = True
            repeats = sum(1 for index in range(1, len(blocks))
                          if blocks[index] == blocks[index - 1])
            with self.subTest(log=os.path.basename(path)):
                self.assertGreater(repeats * 10, (len(blocks) - 1) * 9)
        self.assertTrue(
            looked, "no recorded run holds enough feed blocks to compare")

    def test_some_run_printed_the_feed_while_docked(self):
        """The staleness the issue is about: the widget retains messages, so the
        feed outlives the fight and says nothing about having done so."""
        worst = 0
        for path in saxrat_runs(20, 21, 22, 23):
            blocks, docked = blocks_and_readings(path)
            if blocks:
                worst = max(worst, docked * 100 // len(blocks))
        self.assertGreater(worst, 50)

    def test_the_client_s_own_lines_are_in_the_same_log(self):
        """The duplication the issue names: the host echoes the `(combat)`
        channel, so a combat event was in the log twice over."""
        echoed = False
        for path in saxrat_runs(20, 21, 22, 23):
            with open(path, encoding="utf-8", errors="replace") as handle:
                if re.search(r"game log:.*\(combat\)", handle.read()):
                    echoed = True
        self.assertTrue(
            echoed, "no recorded run echoes the client's (combat) lines")


if __name__ == "__main__":
    unittest.main()
