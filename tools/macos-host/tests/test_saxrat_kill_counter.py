"""saxrat counts what died, and the status line says the run on one line.

Three changes verified here, and they are one change: the operator asked for a
brief, informative status header, the header needs a kill count, and no kill
count existed anywhere in this repository.

**The kill count is new capability rather than a reformat.** Every occurrence of
"kills" in the Elm source before this was prose in a doc comment. The number has
to come from the client's own `(bounty)` channel, which is one of the two the
bot is deliberately not given -- so the argument the host's deny-list comment
makes ("a second reader of those lines would be a second source of truth") is
answered here by there being **one pattern with two anchorings**, imported from
the web console rather than restated, and by a case that runs both over every
bounty line in the recorded corpus and requires the same number.

**What it counts is what the client paid, and the cases say so by name.** A
bounty is not a kill by this ship: a fleetmate's rat this ship damaged pays, a
rat this ship killed whose bounty went elsewhere does not, and a structure pays
nothing however thoroughly it is destroyed. And the channel names no target, so
the total can never be split -- which is the *reason* to take it, not a
shortfall. PR #274 established what a name-keyed fold costs on this grid: a
"702 consecutive misses on a target the guns went on to hurt" reading that was
the same name on a different rat, because an anomaly is a pocket of identically
named rats. A count that never attributes cannot mis-attribute.

**The verbosity reduction is the host's**, and that placement is the finding.
The status line is reprinted under every decision, which is this loop's doing
and not the bot's -- measured over saxrat run 52, 79.8% of a 27.7 MB log is
status text. `decision_log_lines` prints the header every time and each line
below it only when that line moved, says how many it suppressed, and is executed
here rather than described. Per line rather than per body because the difference
is a factor of two on that run: some counter or other moves on two decisions in
three and would drag every steady line through with it.

The rules are executed through the real `Bot.elm` in `elm repl` and the readings
they are asked about carry the host's own synthetic node, decoded by the real
`EveOnline.ParseUserInterface` -- so the `kills` key the host writes is the one
under test rather than a record shaped by hand.

Nothing here reads a live game client or drives a bot. The corpus cases skip
with a stated reason on a machine that has no client logs, and they glob the
sessions rather than naming them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
import glob
import os
import re
import sys
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

# The host's own directory on the path, then the module by its plain name --
# `tools/macos-host/botlab_host/` carries no `__init__.py`, so it is not a
# package and `from botlab_host import botlab_host` only resolves where an
# implicit namespace package happens to win. That is the idiom every other file
# here uses, and the one that survives being collected from the repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402
import web_console  # noqa: E402

REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
EVE_APPS = os.path.join(REPO_DIR, "implement", "applications", "eve-online")
PARSER_GLOB = os.path.join(EVE_APPS, "*", "EveOnline", "ParseUserInterface.elm")

GAMELOGS_GLOB = os.path.join(
    os.path.expanduser("~"), "Documents", "EVE", "logs", "Gamelogs", "*.txt")
EVE_BOT_LOGS = os.path.join(os.path.expanduser("~"), "eve-bot-logs")

# The wording the rest of the suite uses for these two prerequisites, so
# `check_expected_skips.py` covers them under entries it already has rather than
# needing new ones. A skip nobody has classified is one CI refuses.
NO_GAMELOGS = "no recorded game logs in ~/Documents/EVE/logs/Gamelogs"
NO_RUNS = "no recorded saxrat runs in ~/eve-bot-logs"

# The two wordings the client writes on this channel, taken out of the corpus
# rather than typed from memory -- 17,174 of the first and 214 of the second
# across the 38 sessions that carry any.
PLAIN_PAYOUT = "6,000 ISK added to next bounty payout"
ADJUSTED_PAYOUT = "12,375 ISK added to next bounty payout (payment adjusted)"


def kills_node(count):
    """The host's fourth synthetic node, exactly as `botlab_host.py` emits it.

    Built through the host's own emitter rather than written out here, so a
    fixture cannot drift from what the bot is really handed -- and so the
    `kills` key the parser reads strictly is the one under test.
    """
    return botlab_host.synthetic_kills_node(count)


def entry(channel, text):
    return {"timestamp": "2026.08.16 12:00:00", "channel": channel, "text": text}


def source():
    return source_of(SAXRAT_BOT_ELM)


def without_comments(text):
    """The same source with its doc comments and `--` lines dropped.

    Every case asserting a name is read *nowhere* needs this: this change
    discusses kills at length in prose, so a count over the raw text cannot tell
    a mention from a use.
    """
    text = re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


def game_log_lines():
    """Every markup-stripped line of the client's own logs, cached per process."""
    if not _LINES:
        paths = sorted(glob.glob(GAMELOGS_GLOB))
        if not paths:
            raise unittest.SkipTest(NO_GAMELOGS)
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    _LINES.append(
                        " ".join(botlab_host._GAME_LOG_MARKUP.sub("", raw).split()))
    return _LINES


_LINES = []


# --------------------------------------------------------------------------
# the host


class TheHostCountsBountyPayoutsTest(unittest.TestCase):
    """`entry_is_a_bounty_payout`, against the client's own two wordings."""

    def test_both_wordings_the_client_writes_are_a_kill(self):
        """Read out of the corpus rather than typed from the issue.

        The `(payment adjusted)` form is 214 of the recorded 17,388 and is a rat
        that died exactly as the plain form is, so the pattern stops at the
        payout clause and reads no further.
        """
        self.assertTrue(
            botlab_host.entry_is_a_bounty_payout(entry("bounty", PLAIN_PAYOUT)))
        self.assertTrue(
            botlab_host.entry_is_a_bounty_payout(entry("bounty", ADJUSTED_PAYOUT)))

    def test_the_same_words_on_another_channel_are_not_a_kill(self):
        """The channel is checked as well as the wording.

        A kill count built on a phrase rather than on the client's own channel
        marker is a count anything that quotes the phrase could inflate -- and
        the host echoes every channel into the same log.
        """
        self.assertFalse(
            botlab_host.entry_is_a_bounty_payout(entry("notify", PLAIN_PAYOUT)))
        self.assertFalse(
            botlab_host.entry_is_a_bounty_payout(entry("combat", PLAIN_PAYOUT)))

    def test_another_sentence_on_the_bounty_channel_is_not_a_kill(self):
        """A channel is not a count. Anything the client says here that is not a
        payout is declined rather than counted, so a wording this corpus has not
        seen cannot silently become a kill."""
        self.assertFalse(botlab_host.entry_is_a_bounty_payout(
            entry("bounty", "Bounty payout of 1,000,000 ISK received")))
        self.assertFalse(botlab_host.entry_is_a_bounty_payout(
            entry("bounty", "")))

    def test_the_bounty_lines_still_do_not_reach_the_bot(self):
        """The deny-list is unchanged, which is the whole of the argument.

        Withholding this channel was right about the *lines* and says nothing
        about the count -- exactly as it was for `(combat)`, whose totals ride
        two synthetic nodes while its lines stay withheld. If this ever fails,
        the bot has a second reader of the lines themselves and the objection
        the host's deny-list comment makes has become true.
        """
        self.assertIn(
            "bounty", botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT)
        self.assertIn(
            "combat", botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT)


class TheHostAndTheConsoleCountTheSameKillsTest(unittest.TestCase):
    """One pattern, two anchorings, checked over every recorded bounty line.

    The console has counted kills off these lines since before the bot could see
    them, and CLAUDE.md's stated reason for withholding the channel is that a
    second reader would be a second source of truth for one statistic. So the
    two readers are required to agree on the real corpus rather than to look
    alike in the source.
    """

    def test_the_two_readers_agree_on_every_recorded_line(self):
        lines = game_log_lines()
        console_kills = sum(1 for line in lines if web_console.BOUNTY_RE.search(line))
        host_kills = 0
        for line in lines:
            parsed = botlab_host.parse_game_log_line(line)
            if botlab_host.entry_is_a_bounty_payout(parsed):
                host_kills += 1
        self.assertGreater(host_kills, 1000,
                           "the corpus carries no bounty lines to compare on")
        self.assertEqual(host_kills, console_kills)

    def test_the_two_anchorings_come_from_one_literal(self):
        """Read out of the source, because agreeing today is not the property.

        Two patterns that happen to agree on this corpus are two patterns; what
        keeps them agreeing is that there is one literal underneath them.
        """
        console_source = source_of(os.path.join(MACOS_HOST_DIR, "web_console.py"))
        self.assertIn('BOUNTY_RE = re.compile(r"\\(bounty\\)\\s+" + _BOUNTY_PAYOUT)',
                      console_source)
        self.assertIn('BOUNTY_TEXT_RE = re.compile(r"^" + _BOUNTY_PAYOUT)',
                      console_source)
        self.assertIn("web_console.BOUNTY_TEXT_RE",
                      source_of(os.path.join(
                          MACOS_HOST_DIR, "botlab_host", "botlab_host.py")))

    def test_a_bounty_line_is_a_kill_rather_than_a_repeat(self):
        """Measured rather than assumed, because the whole count rests on it.

        If the client wrote a line twice per rat this number would be double
        everywhere and nothing else in the system could say so. Across the
        corpus only a small fraction of bounty lines are byte-identical to
        another in the same session -- two rats of one type dying inside one
        second -- and none occurs more than twice, which is not what a channel
        duplicating its own output looks like.
        """
        per_session = collections.defaultdict(collections.Counter)
        paths = sorted(glob.glob(GAMELOGS_GLOB))
        if not paths:
            raise unittest.SkipTest(NO_GAMELOGS)
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    line = " ".join(
                        botlab_host._GAME_LOG_MARKUP.sub("", raw).split())
                    parsed = botlab_host.parse_game_log_line(line)
                    if botlab_host.entry_is_a_bounty_payout(parsed):
                        per_session[path][line] += 1
        counts = [n for session in per_session.values() for n in session.values()]
        self.assertGreater(len(counts), 500, "too few bounty lines to measure on")
        self.assertLessEqual(max(counts), 2)
        repeated = sum(n - 1 for n in counts if n > 1)
        self.assertLess(repeated, sum(counts) // 20,
                        "identical bounty lines are common enough to look like "
                        "the client writing one line twice per kill")


class TheKillNodeTest(unittest.TestCase):
    """The node's own shape, and the four properties every synthetic node has."""

    def test_a_reading_with_nothing_dying_still_carries_the_node(self):
        """Zero is an answer; absence is a different one.

        A bot that collapsed the two would report a session nobody counted as
        one that killed nothing, which is this repo's signature failure.
        """
        self.assertEqual(kills_node(0)["dictEntriesOfInterest"], {"kills": 0})
        self.assertEqual(kills_node(7)["dictEntriesOfInterest"], {"kills": 7})

    def test_the_node_says_in_full_that_the_client_never_wrote_it(self):
        self.assertEqual(kills_node(0)["pythonObjectTypeName"],
                         "MacOsHostSyntheticKills")
        self.assertEqual(botlab_host.SYNTHETIC_KILLS_TYPE_NAME,
                         "MacOsHostSyntheticKills")

    def test_the_node_has_no_display_region_and_no_display_text(self):
        """The two properties that keep a fiction out of every existing parser.

        No `_display*` means `asUITreeNodeWithInheritedOffset` files it as a
        `ChildWithoutRegion` and nothing that navigates by region can reach it;
        nothing under `_setText`/`_text` means `getAllContainedDisplayTexts`
        cannot see it either.
        """
        entries = kills_node(3)["dictEntriesOfInterest"]
        for key in entries:
            self.assertFalse(key.startswith("_display"), key)
        for key in ("_setText", "_text"):
            self.assertNotIn(key, entries)


class TheTailFansTheKillQueueOutTest(unittest.TestCase):
    """A sixth queue on one offset, drained by a fifth reader.

    Adding a second caller of a single-cursor tail is what would give whichever
    ran first that cycle's lines and the others nothing, intermittently and
    without a word -- so each reader is required to see every line whatever
    order they are drained in.
    """

    def tail_with(self, lines):
        tail = botlab_host.GameLogTail.__new__(botlab_host.GameLogTail)
        botlab_host.GameLogTail.__init__(tail, "/nonexistent")
        tail._poll = lambda: None
        for line in lines:
            parsed = botlab_host.parse_game_log_line(line)
            if parsed is None:
                continue
            if parsed["channel"] not in \
                    botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT:
                tail._reading_queue.append(parsed)
            dealt = botlab_host.parse_outgoing_damage(parsed)
            if dealt is not None:
                tail._outgoing_queue.append(dealt)
            if botlab_host.entry_is_a_bounty_payout(parsed):
                tail._kill_queue.append(True)
        return tail

    LINES = [
        "[ 2026.08.16 12:00:00 ] (bounty) %s" % PLAIN_PAYOUT,
        "[ 2026.08.16 12:00:01 ] (combat) 104 to Mammon Apis - Hits",
        "[ 2026.08.16 12:00:02 ] (bounty) %s" % ADJUSTED_PAYOUT,
        "[ 2026.08.16 12:00:03 ] (notify) You cannot do that while warping",
    ]

    def test_every_reader_sees_its_own_lines_whichever_drains_first(self):
        tail = self.tail_with(self.LINES)
        self.assertEqual(tail.kills_for_reading(), 2)
        self.assertEqual(len(tail.outgoing_damage_for_reading()), 1)
        self.assertEqual(len(tail.entries_for_reading()), 1)

        tail = self.tail_with(self.LINES)
        self.assertEqual(len(tail.entries_for_reading()), 1)
        self.assertEqual(len(tail.outgoing_damage_for_reading()), 1)
        self.assertEqual(tail.kills_for_reading(), 2)

    def test_the_queue_is_drained_so_a_reading_is_not_a_running_total(self):
        """Scoped to the reading by construction, like every other queue here.

        A queue that grew instead would have the bot reporting the same kill on
        every reading for the rest of the session.
        """
        tail = self.tail_with(self.LINES)
        self.assertEqual(tail.kills_for_reading(), 2)
        self.assertEqual(tail.kills_for_reading(), 0)


# --------------------------------------------------------------------------
# the parser, in every vendored copy that carries the kill channel

#: `eve-online-mining-bot`'s tree was replaced with Viir's current upstream
#: (see CLAUDE.md's Architecture section), which predates the kill-count
#: channel entirely -- its `ParseUserInterface.elm` carries no
#: `killsSinceLastReading` field at all. Excluded from
#: `TheVendoredParserCopiesTest` rather than assigned a shape; porting the
#: synthetic kills node into the newer base is follow-up work, not done here.
WITHOUT_KILLS = {"eve-online-mining-bot"}


def kill_parser_paths():
    return sorted(
        path for path in glob.glob(PARSER_GLOB)
        if os.path.basename(os.path.dirname(os.path.dirname(path)))
        not in WITHOUT_KILLS)


class TheVendoredParserCopiesTest(unittest.TestCase):
    """All copies that carry the channel, identically -- #271's argument
    rather than #252's.

    `ParsedUserInterface` is a shared type five of the six `Bot.elm`s read, and
    the synthetic-node parsers are one of the places those five copies have
    **not** diverged. Adding to one copy would put a divergence into a block
    that has none, which is the opposite of what #252 concluded for an
    app-local panel parser. `eve-online-mining-bot` is excluded (see
    `WITHOUT_KILLS`), not counted as a sixth divergent copy.
    """

    def blocks(self):
        paths = kill_parser_paths()
        self.assertEqual(len(paths), 5, paths)
        out = {}
        for path in paths:
            text = source_of(path)
            start = text.index("parseKillsSinceLastReadingFromUITreeRoot :")
            end = text.index('"MacOsHostSyntheticKills"') + \
                len('"MacOsHostSyntheticKills"')
            out[path] = text[start:end]
        return out

    def test_every_copy_has_the_same_one(self):
        blocks = self.blocks()
        self.assertEqual(len(set(blocks.values())), 1,
                         "the kill parser has diverged between copies")

    def test_every_copy_carries_the_field_and_fills_it(self):
        for path in kill_parser_paths():
            text = source_of(path)
            self.assertIn(", killsSinceLastReading : Maybe Int", text, path)
            self.assertIn(
                ", killsSinceLastReading = parseKillsSinceLastReadingFromUITreeRoot"
                " uiTree", text, path)

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_field(self):
        path = os.path.join(
            EVE_APPS, "eve-online-mining-bot", "EveOnline",
            "ParseUserInterface.elm")
        self.assertNotIn("killsSinceLastReading", source_of(path))

    def test_the_type_name_agrees_with_the_host_across_languages(self):
        """The one string two languages have to agree on, pinned in both.

        A drift here is silent in the direction that looks like a healthy run:
        the host emits a node nothing reads, and the bot reports no kill log
        forever.
        """
        for text in self.blocks().values():
            self.assertIn('"%s"' % botlab_host.SYNTHETIC_KILLS_TYPE_NAME, text)

    def test_the_count_is_read_strictly_rather_than_defaulted(self):
        """A defaulted count reports a quiet grid for a broken channel.

        `Maybe.withDefault 0` here would turn a node whose key this parser does
        not recognise into "nothing died", which is a fabricated fact -- and the
        one distinction this whole channel keeps is that absence is not zero.
        """
        for text in self.blocks().values():
            self.assertIn('Maybe.andThen (getIntPropertyFromDictEntries "kills")',
                          collapsed(text))
            self.assertNotIn("withDefault 0", collapsed(text))


class TheParserReadsWhatTheHostWritesTest(unittest.TestCase):
    """Executed end to end: host emitter -> real parser -> the bot's field."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def kills_of(self, children):
        return self.repl.values(
            ["reading |> Maybe.andThen .killsSinceLastReading"],
            r"(Just \d+|Nothing) : Maybe Int",
            definitions=[SaxratRepl.reading_binding("reading", children)])[0]

    def test_the_number_the_host_wrote_is_the_number_the_bot_reads(self):
        self.assertEqual(self.kills_of([kills_node(7)]), "Just 7")

    def test_a_reading_with_nothing_dying_answers_zero_rather_than_nothing(self):
        self.assertEqual(self.kills_of([kills_node(0)]), "Just 0")

    def test_a_host_that_does_not_carry_the_channel_answers_nothing(self):
        """The distinction the whole design rests on, at the parser."""
        self.assertEqual(self.kills_of([]), "Nothing")

    def test_a_node_without_the_key_answers_nothing_rather_than_zero(self):
        """A host disagreeing with this parser about the node's shape.

        "We do not know" is the safe answer; a fabricated zero would report a
        quiet grid for a channel that is broken rather than silent.
        """
        malformed = dict(kills_node(4))
        malformed["dictEntriesOfInterest"] = {}
        self.assertEqual(self.kills_of([malformed]), "Nothing")


# --------------------------------------------------------------------------
# the rule


class TheKillCountRuleTest(unittest.TestCase):
    """`killCountAfterReading`, folded over sessions rather than asked once.

    A counter that is right for one reading and wrong across a session is the
    defect this shape exists to prevent.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions_for(self, readings):
        definitions = ["start = { hostCarriesTheChannel = False,"
                       " thisReading = 0, session = 0 }"]
        names = []
        for index, reading in enumerate(readings):
            name = "reading%d" % index
            children = [] if reading is None else [kills_node(reading)]
            definitions.append(SaxratRepl.reading_binding(name, children))
            names.append(name)
        counts = " , ".join(
            "%s |> Maybe.andThen .killsSinceLastReading" % name for name in names)
        definitions.append(
            "folded = List.foldl (\\k m -> Bot.killCountAfterReading"
            " { before = m, kills = k }) start [ %s ]" % counts)
        return definitions

    def fold(self, readings, field):
        return int(self.repl.values(
            ["folded.%s" % field], r"(-?\d+) : Int",
            definitions=self.definitions_for(readings))[0])

    def fold_bool(self, readings, field):
        return self.repl.evaluate(
            ["folded.%s" % field], definitions=self.definitions_for(readings))[0]

    def test_the_session_total_is_the_sum_of_the_readings(self):
        self.assertEqual(self.fold([1, 0, 2, 0, 3], "session"), 6)
        self.assertEqual(self.fold([1, 0, 2, 0, 3], "thisReading"), 3)
        self.assertTrue(self.fold_bool([1], "hostCarriesTheChannel"))

    def test_a_reading_with_nothing_dying_is_not_a_missing_channel(self):
        """`Just 0` and `Nothing` are different answers, at the rule too.

        The first leaves the channel armed and the total where it was; the
        second disarms it. A run whose grid was quiet and a run nobody counted
        must not read alike.
        """
        self.assertTrue(self.fold_bool([0], "hostCarriesTheChannel"))
        self.assertFalse(self.fold_bool([None], "hostCarriesTheChannel"))

    def test_a_host_that_stops_answering_keeps_the_total(self):
        """A host that goes quiet has not un-killed anything.

        A total that fell back to zero would report a three-hour run as a fresh
        one, on the reading the channel happened to go away.
        """
        self.assertEqual(self.fold([2, 3, None], "session"), 5)
        self.assertEqual(self.fold([2, 3, None], "thisReading"), 0)
        self.assertFalse(self.fold_bool([2, 3, None], "hostCarriesTheChannel"))

    def test_the_total_recovers_when_the_channel_comes_back(self):
        self.assertEqual(self.fold([2, None, 3], "session"), 5)
        self.assertTrue(self.fold_bool([2, None, 3], "hostCarriesTheChannel"))

    def test_the_total_never_falls(self):
        """Monotone by construction, over a session long enough to show it."""
        readings = [1, 0, None, 2, 0, 0, None, 5, 1]
        totals = []
        for prefix in range(1, len(readings) + 1):
            totals.append(self.fold(readings[:prefix], "session"))
        self.assertEqual(totals, sorted(totals))
        self.assertEqual(totals[-1], 9)


class TheKillClauseTest(unittest.TestCase):
    """What the header prints, executed rather than asserted by substring."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, carries, session):
        return self.repl.strings(
            ["Bot.describeKillCount { hostCarriesTheChannel = %s,"
             " thisReading = 0, session = %d }"
             % ("True" if carries else "False", session)])[0]

    def test_a_counted_session_reads_as_a_number_of_kills(self):
        self.assertEqual(self.clause(True, 273), "273 kills")
        self.assertEqual(self.clause(True, 0), "0 kills")

    def test_an_absent_channel_says_so_rather_than_reporting_zero(self):
        """`describeOutgoingFire`'s `NO COMBAT LOG`, for its reason.

        A header that printed `0 kills` on a host with no game log would be
        reporting a quiet grid for an instrument that is not there, and the run
        that fought hard would look identical to the run that killed nothing.
        """
        self.assertEqual(self.clause(False, 0), "no kill log")
        self.assertEqual(self.clause(False, 40), "no kill log")


# --------------------------------------------------------------------------
# the header


class TheHeaderTest(unittest.TestCase):
    """The one line the log carries on every decision."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_header_is_the_first_line_of_the_status_text(self):
        """Placement is the whole of it, now that the host prints line one every
        decision and the body only on change. A header that was not first would
        be a diagnostic, and the twelve diagnostics would be the header."""
        status = collapsed(body_of(source(), "statusTextFromState"))
        assembly = status.split("in [ ")[-1]
        self.assertIn("[ describeStatusHeader context ]", assembly)
        self.assertLess(assembly.index("describeStatusHeader"),
                        assembly.index("describePerformance"),
                        "the header is not the first row of the status text")

    def test_no_comment_sits_between_the_let_and_the_status_list(self):
        """The trap this change hit, kept as a case because it passes silently.

        `test_quick_message_logged` locates the outer list by splitting the
        collapsed declaration on `in [ `. A comment between the `in` and the
        `[` -- which is where an Elm author naturally puts one explaining the
        list -- removes that occurrence, so the split returns the *whole*
        function. That still contains `describeQuickMessage`, so the case
        passes having read everything rather than the list it meant to read.
        A pin that can pass vacuously is worse than one that fails, and this is
        the second reader that would have to notice.
        """
        status = collapsed(body_of(source(), "statusTextFromState"))
        self.assertEqual(
            status.count("in [ [ describeStatusHeader context ]"), 1,
            "the outer list is no longer reachable by splitting on 'in [ ', so "
            "the quick-message placement pin next door now reads the whole "
            "function and passes on anything")

    def test_the_header_carries_every_field_that_was_asked_for(self):
        """The six the operator named, and the two run 48 argues for.

        Read out of the rendering rather than out of prose: run 48 sat in one
        anomaly for 3,883 seconds and the question was whether the ship was in
        trouble, which took a replay to answer because the shield, the armour
        and the incoming damage were spread across three diagnostic lines.
        """
        header = collapsed(body_of(source(), "describeStatusHeader"))
        for fragment in ("currentSolarSystemNameFromReading",
                         "describeWhereTheShipIs",
                         "activeTargetNameFromReading",
                         "describeTargetHitpoints",
                         '" rats"',
                         "describeKillCount",
                         '" anoms"',
                         '"| ship "',
                         "hitpoints.shield.believed",
                         "hitpoints.armor.believed",
                         "incomingDamageInWindow",
                         "runAwayIncomingDamageThreshold"):
            self.assertIn(fragment, header, fragment)

    def test_the_header_reuses_the_target_hitpoints_clause(self):
        """PR #244 pinned that clause as deliberately unshared between the apps.

        saxrat's is the abbreviated `[10/100/100]` and the mission runner's the
        spelled-out one, and a header that spelled the triple out again here
        would be a third rendering for two apps to drift between. So the header
        *calls* it; it does not carry its own.
        """
        header = collapsed(body_of(source(), "describeStatusHeader"))
        self.assertIn("describeTargetHitpoints", header)
        self.assertNotIn("Shield:", header)
        self.assertNotIn("percent.structure", header)

    def test_the_ship_gauge_is_the_believed_pair_and_not_the_live_one(self):
        """What the guards go by, so the header cannot disagree with them.

        This hull's gauge produced values from -213% to 40,028,800% on one
        recorded run; `plausibleHitpointsPercent` rejects the impossible ones and
        `believed` withholds a fall a second reading has not confirmed. A header
        reading the live value would print numbers no rule here acts on.
        """
        header = collapsed(body_of(source(), "describeStatusHeader"))
        self.assertIn("context.memory.hitpoints.shield.believed", header)
        self.assertIn("context.memory.hitpoints.armor.believed", header)
        self.assertNotIn("shipUI.hitpointsPercent", header)

    def test_a_reading_with_no_ship_ui_answers_docked(self):
        """The one state of the place field a bare reading can be built for.

        Executed rather than read, and it is the state the ordering below
        matters for: a docked reading has no ship UI, so
        `shipWarpingFromReading` answers `Nothing` there and a rule that asked
        about the warp first would print `-` for a docked ship.
        """
        said = self.repl.strings(
            ['reading |> Maybe.map Bot.describeWhereTheShipIs'
             ' |> Maybe.withDefault "THE FIXTURE NEVER ARRIVED"'],
            definitions=[SaxratRepl.reading_binding("reading", [])])[0]
        self.assertEqual(said, "DOCKED")

    def test_the_place_field_answers_the_three_states_it_can_read(self):
        """Docked, warping, in a named anomaly -- and `-` for anything else.

        `DEADSPACE` is deliberately not a fourth case: a pocket reached through
        an acceleration gate has no scan-result row, so the scanner names
        nothing and the honest answer is that the client is not saying.

        Since #197 the anomaly state carries the scanner's Name cell as well as
        its ID, so the reader named here is the identity one. **The header uses
        its own renderer**, and that is the half worth pinning rather than
        merely updating: `describeAnomalyIdentity` renders
        `'ID' 'Name' (Group)` for the lines a run is read back from, and putting
        that in the header would print the group -- one repeated word,
        `Combat Site`, on every line this bot ever writes -- and leave two
        quoted names running together beside the target's own.
        """
        rule = collapsed(body_of(source(), "describeWhereTheShipIs"))
        self.assertIn('"DOCKED"', rule)
        self.assertIn('"IN WARP"', rule)
        self.assertIn("getCurrentAnomalyIdentityAsSeenInProbeScanner", rule)
        self.assertIn("describeAnomalyIdentityForHeader", rule)
        self.assertIn('"-"', rule)
        self.assertNotIn("DEADSPACE", rule)
        # The docked test is asked first, because a docked reading has no ship
        # UI and `shipWarpingFromReading` answers `Nothing` there -- so a rule
        # that asked about the warp first would print `-` for a docked ship.
        self.assertLess(rule.index("DOCKED"), rule.index("IN WARP"))


class NothingDecidesOnTheKillCountTest(unittest.TestCase):
    """An instrument, and it earns the right to drive a rule after a run.

    PR #130's posture for `quickMessage` and #135's for `attritionIsUnguarded`.
    The count has never been printed at all, so nothing may act on it yet -- and
    what it counts (see the doc comment) is not what a combat rule would want it
    to mean.
    """

    def test_the_field_is_read_by_the_memory_update_and_the_header_only(self):
        text = without_comments(source())
        readers = [line.strip().lstrip(", ")
                   for line in text.splitlines() if "memory.kills" in line]
        self.assertEqual(
            readers, ["describeKillCount context.memory.kills"],
            "something other than the header reads the kill count")

    def test_the_memory_is_written_in_the_one_place_that_can_write_memory(self):
        update = collapsed(body_of(source(), "updateMemoryForNewReadingFromGame"))
        self.assertIn("kills = killCountAfterReading { before ="
                      " botMemoryBefore.kills , kills ="
                      " context.readingFromGameClient.killsSinceLastReading }",
                      update)

    def test_the_clause_is_reached_through_one_rendering(self):
        """One `describeKillCount`, so the header and any later reader agree."""
        text = without_comments(source())
        self.assertEqual(text.count("describeKillCount"), 3,
                         "the kill clause has a second rendering")


# --------------------------------------------------------------------------
# the verbosity reduction


class TheStatusLinesArePrintedOnChangeTest(unittest.TestCase):
    """`decision_log_lines`, executed rather than described."""

    def run_decisions(self, texts):
        produced = []
        last = None
        for index, text in enumerate(texts):
            lines, last = botlab_host.decision_log_lines(
                text, "# [%d.0] " % index, last)
            produced.append(lines)
        return produced

    @staticmethod
    def printed(lines):
        """The bot's own lines, without the marker or the header."""
        return [line for line in lines[1:] if not line.startswith("#")]

    HEADER = "Amarr AIC-176 no target 0 rats 12 kills 3 anoms"

    def test_the_header_is_printed_on_every_decision(self):
        """The line an operator reads, every time, whatever the body did."""
        produced = self.run_decisions(
            ["%s %d\nbody" % (self.HEADER, n) for n in range(3)])
        for index, lines in enumerate(produced):
            self.assertEqual(lines[0],
                             "# [%d.0] %s %d" % (index, self.HEADER, index))

    def test_an_unchanged_line_is_not_reprinted(self):
        produced = self.run_decisions(["h\nbody"] * 3)
        self.assertEqual(self.printed(produced[0]), ["body"])
        self.assertEqual(self.printed(produced[1]), [])
        self.assertEqual(self.printed(produced[2]), [])

    def test_only_the_line_that_moved_is_reprinted(self):
        """The whole point of doing this per line rather than per body.

        On a real run some counter moves on two decisions in three and would
        drag every steady line through with it -- 26.8% of run 52's log against
        61.5%.
        """
        produced = self.run_decisions(["h\nsteady\nmoving 1",
                                       "h\nsteady\nmoving 2",
                                       "h\nsteady\nmoving 3"])
        self.assertEqual(self.printed(produced[0]), ["steady", "moving 1"])
        self.assertEqual(self.printed(produced[1]), ["moving 2"])
        self.assertEqual(self.printed(produced[2]), ["moving 3"])

    def test_a_changed_line_is_printed_again(self):
        """The property that makes suppression safe rather than merely cheap.

        The comparison is against what was last *printed* at that position, so
        a line that differs is printed whatever produced the difference and
        however many decisions a reading happens to take. The "changed but not
        shown" case does not exist.
        """
        produced = self.run_decisions(["h\nA", "h\nA", "h\nB", "h\nB", "h\nA"])
        self.assertEqual([self.printed(lines) for lines in produced],
                         [["A"], [], ["B"], [], ["A"]])

    def test_a_position_is_not_a_clause_and_the_invariant_is_the_position(self):
        """A docked reading's status text is shorter, so an index can hold
        different clauses at different moments -- and this is what that costs.

        The invariant is about the position rather than the clause: whatever
        stands at index N is printed unless it is byte-identical to the last
        thing printed at index N. So a clause that *displaced* another one at a
        position prints, and the one it displaced prints again when it returns
        -- while a clause at a position the shorter reading never reached is
        correctly still suppressed, because nothing has been printed over it and
        it has not moved.

        Written this way round deliberately: the first version of this case
        asserted the whole pair reprinting and was wrong about the code rather
        than the other way about.
        """
        produced = self.run_decisions(["h\nrats 3\ntarget X",
                                       "h\ndocked",
                                       "h\nrats 3\ntarget X"])
        self.assertEqual(self.printed(produced[0]), ["rats 3", "target X"])
        # "docked" displaces "rats 3" at index 0 and is printed for it.
        self.assertEqual(self.printed(produced[1]), ["docked"])
        # "rats 3" returns to a position "docked" has since used, so it prints;
        # "target X" is unchanged since it was last shown, so it does not.
        self.assertEqual(self.printed(produced[2]), ["rats 3"])

    def test_the_suppression_says_how_many_it_suppressed(self):
        """A log that prints a clause less often without saying so is a log
        whose counts have quietly changed meaning."""
        produced = self.run_decisions(["h\na\nb\nc", "h\na\nb\nc"])
        marker = produced[1][-1]
        self.assertEqual(marker, botlab_host.STATUS_LINES_UNCHANGED_LINE % 3)
        self.assertTrue(marker.startswith("#"),
                        "the marker would be read as bot output")
        self.assertNotIn("#", "".join(produced[0][1:]),
                         "a decision that suppressed nothing still marked")

    def test_a_status_text_of_one_line_prints_nothing_below_it(self):
        produced = self.run_decisions(["just a header"])
        self.assertEqual(produced[0], ["# [0.0] just a header"])

    def test_the_budget_is_the_one_the_whole_text_always_had(self):
        """Truncated before it is split, so an over-long status text is held to
        the budget it was always held to rather than to one budget per line."""
        body = "x" * 9000
        produced, _ = botlab_host.decision_log_lines("h\n" + body, "# ", None)
        self.assertEqual(sum(len(line) for line in self.printed(produced)),
                         botlab_host.STATUS_TEXT_LOG_BUDGET - len("h\n"))

    def test_nothing_is_dropped_only_not_repeated(self):
        """Every distinct value a position ever held is still in the log, in
        order, so the change is a repetition removed rather than evidence."""
        texts = ["h\nA", "h\nA", "h\nB", "h\nA", "h\nA", "h\nC"]
        printed = [line for lines in self.run_decisions(texts)
                   for line in self.printed(lines)]
        self.assertEqual(printed, ["A", "B", "A", "C"])
        bodies = [text.split("\n", 1)[1] for text in texts]
        self.assertEqual(
            printed,
            [body for index, body in enumerate(bodies)
             if index == 0 or body != bodies[index - 1]])


class TheRepetitionThisEndsIsRealTest(unittest.TestCase):
    """The measurement the change rests on, recomputed from a recorded run.

    Asserted as *relations* rather than as the numbers in the doc comment, so a
    corpus that grows cannot turn a true claim red -- and so a future run that
    stops having this shape is what makes the change worth revisiting.
    """

    def blocks(self):
        paths = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
        if not paths:
            raise unittest.SkipTest(NO_RUNS)
        # The largest recorded run, so the measurement is taken on a session
        # long enough for the repetition to be the log rather than the start-up.
        path = max(paths, key=os.path.getsize)
        blocks = []
        current = None
        status_bytes = 0
        total_bytes = 0
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                total_bytes += len(line)
                if line.startswith("# ["):
                    if current is not None:
                        blocks.append(current)
                    current = [re.sub(r"^# \[[^\]]*\] \([^)]*\) ", "", line).rstrip()]
                    status_bytes += len(line)
                elif current is not None and not (
                        line.startswith("#") or line.startswith("+")):
                    current.append(line.rstrip())
                    status_bytes += len(line)
        if current is not None:
            blocks.append(current)
        if len(blocks) < 500:
            raise unittest.SkipTest(
                "no recorded saxrat runs long enough to measure the status text on")
        return blocks, status_bytes, total_bytes

    def test_the_status_text_is_most_of_a_recorded_log(self):
        _, status_bytes, total_bytes = self.blocks()
        self.assertGreater(status_bytes, total_bytes // 2,
                           "the status text is not the bulk of the log, so the "
                           "argument for suppressing its body has changed")

    def test_the_body_dwarfs_the_header_it_repeats_under(self):
        blocks, _, _ = self.blocks()
        header_bytes = sum(len(block[0]) for block in blocks)
        body_bytes = sum(len(line) for block in blocks for line in block[1:])
        self.assertGreater(body_bytes, header_bytes * 5)

    def test_most_decisions_reprint_a_body_byte_for_byte(self):
        """What the suppression actually removes, on a real run.

        If this ever fails the body has become genuinely per-decision and the
        change below it is buying much less than it was measured to.
        """
        blocks, _, _ = self.blocks()
        bodies = ["\n".join(block[1:]) for block in blocks]
        repeats = sum(1 for index in range(1, len(bodies))
                      if bodies[index] == bodies[index - 1])
        self.assertGreater(repeats, len(bodies) // 4)


if __name__ == "__main__":
    unittest.main()
