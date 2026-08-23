"""Tests for the game log channel: EVE's own refusals, carried into a reading.

The client explains every refusal in its own log -- "You cannot load or unload
<weapon> while it is active", "You are already managing 6 targets" -- and until
issue #28 the bot could not read a word of it, while `stall_watch.py` used the
same file as ground truth. The channel is a synthetic node the host appends to
the UI tree; these cases cover the four things it has to get right.

**Scoped to the reading.** `entries_for_reading` drains, so a refusal appears in
exactly one reading and never again. A buffer that grew instead would have the
bot answering a refusal from four minutes ago.

**Two readers, one file offset.** The stderr echo used to be the only consumer,
and its consuming the lines is what kept them from the bot. Both queues are fed
from one `_poll`, so neither reader can eat the other's lines -- a failure that
would have been intermittent and silent.

**Inert in a real tree.** The node carries no display region, so every existing
parser (all of which navigate by display region) cannot reach it, and its text
sits under `text` rather than `_setText`/`_text`, so `getDisplayText` -- and
through it the mission runner's "does this reading contain 'No room for more'"
question -- cannot see it either.

**Present but empty, versus absent.** A reading with the node and no entries is
the client saying nothing; a reading without the node is a host that has no game
log to give. Collapsing those two is how a bot concludes a command was accepted
because no refusal arrived.

**An entry the client wrapped is one entry.** Only the first physical line of a
long message carries the `[ timestamp ] (channel) ` prefix, so the rest used to
parse as nothing and be dropped -- issue #124, and 113 times in run 35 the bot
was given a standings-penalty warning with `Do you wish to proceed?` cut off the
end of it. The rule is that a prefix-less line continues the entry above it, and
the corpus is what says that rule is safe: nothing the client wraps begins with
`[`, so no continuation can pass for a new entry, and the one prefix-less shape
that is *not* a continuation -- a file's header block -- has no entry above it
to attach to.

The lines here are real, taken from `~/eve-bot-logs/mission_run*.log` where the
host echoed them during recorded runs. Nothing here reads the live game log
directory, a game client, or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")
sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import botlab_host  # noqa: E402

# Recorded from real runs. The refusals are the ones issues #14, #19 and #27
# each had to infer indirectly.
REFUSAL_LOAD_WHILE_ACTIVE = (
    "[ 2026.08.02 23:17:41 ] (notify) You cannot load or unload Focused Modulated "
    "Medium Energy Beam I while it is active."
)
REFUSAL_TARGET_LIMIT = (
    "[ 2026.08.02 22:41:03 ] (notify) You are already managing 6 targets, as many "
    "as you have skill to."
)
REFUSAL_DRONE_LIMIT = (
    "[ 2026.08.02 23:56:34 ] (notify) You cannot launch Acolyte I because you are "
    "already controlling 5 drones, as much as you have skill to."
)
COMBAT_LINE = (
    "[ 2026.08.02 23:56:31 ] (combat) 224 to Rogue Pirate Escort - Focused "
    "Modulated Medium Energy Beam I - Hits"
)
BOUNTY_LINE = "[ 2026.08.02 23:57:02 ] (bounty) 18,750 ISK added to next bounty payout"
JUMP_LINE = "[ 2026.08.02 23:55:23 ] (None) Jumping from Amarr to Irnin"
# As it arrives before the markup is stripped.
COMBAT_LINE_WITH_MARKUP = (
    "[ 2026.08.02 23:56:24 ] (combat) <color=0xffcc0000><b>127</b><color=0x77ffffff> "
    "from <b>Rogue Pirate Escort</b> - Mjolnir Heavy Missile - Hits"
)

# The wrapped entry issue #124 is about, as run 35 carries it 113 times: the
# standings-penalty warning on one line, the question on the next.
QUESTION_WARNING = (
    "[ 2026.08.04 21:43:33 ] (question) Aggression against this peaceful entity "
    "may have consequences such as a standings penalty or returned aggression. "
    "It is recommended that you reconsider."
)
QUESTION_CONTINUATION = "Do you wish to proceed?"

# Four lines, one entry, from ~/Documents/EVE/logs/Gamelogs. The corpus of bot
# runs has only two-line examples; the client's own logs go deeper, which is why
# nothing counts to two.
REDEEM_ENTRY = (
    "[ 2022.12.21 17:20:45 ] (question) 5 items will be moved to Johnny "
    "Fivehonks's hangar at J130832 - Honk's Moving Castle."
)
REDEEM_CONTINUATIONS = [
    "25,000 Skill Points will be redeemed and directly injected to Johnny Fivehonks.",
    "The following items will be redeemed and applied to Johnny Fivehonks Typhoon "
    "Halcyon Dawn SKINInterStellar Kredits (ISK)Winter Nexus Expert System.",
    "Do you wish to proceed?",
]

# The block every game log file opens with, verbatim. Prefix-less, like a
# continuation, and not one -- `Session Started:` even carries a timestamp of
# its own, which is the shape a rule testing the line rather than its position
# would have to tell apart.
FILE_HEADER = [
    "------------------------------------------------------------",
    "Gamelog",
    "Listener: Johnny Fivehonks",
    "Session Started: 2022.12.21 17:19:50",
    "------------------------------------------------------------",
]


class TailingGameLog:
    """A game log directory that can be appended to, with a tail watching it.

    The real directory (`~/Documents/EVE/logs/Gamelogs`) is not reliably
    readable from a test environment, and driving the client to provoke a
    refusal is not something a unit test can do -- so the recorded lines are
    replayed into a temporary file with the client's own naming.
    """

    def __init__(self, test_case):
        self.directory = tempfile.mkdtemp()
        test_case.addCleanup(self._remove)
        self.path = os.path.join(self.directory, "20260802_235000_91000000.txt")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("------------------------------------------------------------\n")
        self.tail = botlab_host.GameLogTail(self.directory)
        # First sight of a file starts at its end, so the header above is not
        # replayed as though it had just happened.
        self.tail.lines_for_echo()
        self.tail.entries_for_reading()

    def append(self, *lines):
        with open(self.path, "a", encoding="utf-8") as handle:
            for line in lines:
                handle.write(line + "\n")

    def _remove(self):
        for name in os.listdir(self.directory):
            os.remove(os.path.join(self.directory, name))
        os.rmdir(self.directory)


class ParseLineTest(unittest.TestCase):
    def test_splits_timestamp_channel_and_text(self):
        self.assertEqual(
            botlab_host.parse_game_log_line(REFUSAL_TARGET_LIMIT),
            {
                "timestamp": "2026.08.02 22:41:03",
                "channel": "notify",
                "text": "You are already managing 6 targets, as many as you have skill to.",
            },
        )

    def test_the_channel_without_a_name_keeps_the_clients_own_word(self):
        # Travel lines arrive as "(None)", which is the client's spelling and
        # not a missing value -- undock and jump lines are the state changes a
        # decision would branch on.
        entry = botlab_host.parse_game_log_line(JUMP_LINE)
        self.assertEqual(entry["channel"], "None")
        self.assertEqual(entry["text"], "Jumping from Amarr to Irnin")

    def test_a_line_not_in_the_clients_shape_is_not_invented(self):
        self.assertIsNone(botlab_host.parse_game_log_line(
            "------------------------------------------------------------"))
        self.assertIsNone(botlab_host.parse_game_log_line(
            "  Gamelog"))
        self.assertIsNone(botlab_host.parse_game_log_line(""))

    def test_a_continuation_on_its_own_is_still_not_an_entry(self):
        # The line-level contract is unchanged, and deliberately: a line with
        # no prefix carries no timestamp and no channel, so inventing an entry
        # for it would be inventing both. Which of the two things a `None`
        # means -- header, or the rest of the entry above -- is the caller's
        # question, and `game_log_entries_from_lines` is where it is answered.
        self.assertIsNone(botlab_host.parse_game_log_line(QUESTION_CONTINUATION))


class MultiLineEntryTest(unittest.TestCase):
    """Issue #124: the client wraps a long message and only the first line of
    it carries the prefix, so the rest was parsed as nothing and dropped."""

    def test_a_wrapped_entry_is_one_entry_carrying_both_halves(self):
        entries = botlab_host.game_log_entries_from_lines(
            [QUESTION_WARNING, QUESTION_CONTINUATION])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["timestamp"], "2026.08.04 21:43:33")
        self.assertEqual(entries[0]["channel"], "question")
        self.assertIn("standings penalty", entries[0]["text"])
        self.assertIn("Do you wish to proceed?", entries[0]["text"])

    def test_the_two_halves_are_joined_by_a_single_space(self):
        # Exactly, rather than "contains both": a newline here would be a
        # `text` no downstream matcher was written against, and a missing
        # separator would run the last word of one line into the first of the
        # next and break a substring that spans the join.
        entries = botlab_host.game_log_entries_from_lines(
            [QUESTION_WARNING, QUESTION_CONTINUATION])
        self.assertEqual(
            entries[0]["text"],
            QUESTION_WARNING.split(") ", 1)[1] + " " + QUESTION_CONTINUATION)

    def test_an_entry_is_not_limited_to_two_lines(self):
        # The recorded bot runs carry only two-line examples; the client's own
        # logs carry seven three-line entries and three four-line ones. A rule
        # that folded one continuation would drop two thirds of this entry.
        entries = botlab_host.game_log_entries_from_lines(
            [REDEEM_ENTRY] + REDEEM_CONTINUATIONS)
        self.assertEqual(len(entries), 1)
        for continuation in REDEEM_CONTINUATIONS:
            self.assertIn(continuation, entries[0]["text"])
        self.assertTrue(entries[0]["text"].endswith(REDEEM_CONTINUATIONS[-1]))

    def test_the_continuations_are_kept_in_the_order_the_client_wrote_them(self):
        entries = botlab_host.game_log_entries_from_lines(
            [REDEEM_ENTRY] + REDEEM_CONTINUATIONS)
        positions = [entries[0]["text"].index(line)
                     for line in REDEEM_CONTINUATIONS]
        self.assertEqual(positions, sorted(positions))

    def test_an_entry_nobody_wrapped_is_untouched(self):
        # The whole safety argument for appending to `text` rests on this:
        # every existing consumer is a substring test over that field, and a
        # single-line entry has to come back byte for byte as it always did.
        singles = [REFUSAL_LOAD_WHILE_ACTIVE, REFUSAL_TARGET_LIMIT,
                   REFUSAL_DRONE_LIMIT, COMBAT_LINE, BOUNTY_LINE, JUMP_LINE]
        self.assertEqual(
            botlab_host.game_log_entries_from_lines(singles),
            [botlab_host.parse_game_log_line(line) for line in singles])

    def test_a_continuation_goes_to_the_entry_above_it_and_no_other(self):
        entries = botlab_host.game_log_entries_from_lines(
            [QUESTION_WARNING, QUESTION_CONTINUATION, REFUSAL_TARGET_LIMIT])
        self.assertEqual(len(entries), 2)
        self.assertIn("Do you wish to proceed?", entries[0]["text"])
        self.assertNotIn("Do you wish to proceed?", entries[1]["text"])
        self.assertEqual(
            entries[1], botlab_host.parse_game_log_line(REFUSAL_TARGET_LIMIT))

    def test_a_file_header_has_nothing_above_it_and_so_continues_nothing(self):
        # The one prefix-less shape that is not a continuation. It is declined
        # by position rather than by wording, because there is no wording these
        # share that a continuation could not also have -- `Session Started:
        # 2022.12.21 17:19:50` is a header line carrying a timestamp.
        self.assertEqual(botlab_host.game_log_entries_from_lines(FILE_HEADER), [])

    def test_a_header_is_not_folded_into_the_entry_that_follows_it(self):
        entries = botlab_host.game_log_entries_from_lines(
            FILE_HEADER + [REFUSAL_TARGET_LIMIT])
        self.assertEqual(
            entries, [botlab_host.parse_game_log_line(REFUSAL_TARGET_LIMIT)])

    def test_a_header_after_an_entry_would_be_folded_and_that_is_the_bound(self):
        # Stated rather than left to be found. Nothing places a header after an
        # entry -- all 143 in the client's logs open their file, and the tail
        # drops its open entry whenever the file it is reading changes or is
        # truncated under it -- so the case below is unreachable through
        # `GameLogTail`. The rule itself cannot tell the two apart, and this
        # says so out loud instead of implying a discrimination it does not
        # have.
        entries = botlab_host.game_log_entries_from_lines(
            [REFUSAL_TARGET_LIMIT] + FILE_HEADER)
        self.assertEqual(len(entries), 1)
        self.assertIn("Gamelog", entries[0]["text"])


class TailTest(unittest.TestCase):
    def test_a_refusal_reaches_the_reading(self):
        log = TailingGameLog(self)
        log.append(REFUSAL_LOAD_WHILE_ACTIVE)
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["channel"], "notify")
        self.assertIn("cannot load or unload", entries[0]["text"])

    def test_it_is_scoped_to_the_reading_and_not_repeated(self):
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT)
        self.assertEqual(len(log.tail.entries_for_reading()), 1)
        # The next reading is a new question. A refusal that answered the
        # previous one must not answer this one too.
        self.assertEqual(log.tail.entries_for_reading(), [])
        log.append(REFUSAL_DRONE_LIMIT)
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertIn("already controlling 5 drones", entries[0]["text"])

    def test_combat_and_bounty_stay_out_of_the_reading(self):
        log = TailingGameLog(self)
        log.append(COMBAT_LINE, BOUNTY_LINE, REFUSAL_DRONE_LIMIT, COMBAT_LINE)
        entries = log.tail.entries_for_reading()
        self.assertEqual([entry["channel"] for entry in entries], ["notify"])

    def test_combat_and_bounty_still_reach_the_echo(self):
        # Withholding them from the bot is about not making this a second
        # source of truth for kills and ISK; the human-facing log is unchanged.
        log = TailingGameLog(self)
        log.append(COMBAT_LINE, BOUNTY_LINE)
        self.assertEqual(log.tail.lines_for_echo(), [COMBAT_LINE, BOUNTY_LINE])

    def test_neither_reader_consumes_the_others_lines(self):
        # The whole point of the change: the echo used to be the only consumer
        # of the file offset, which is what kept these lines from the bot.
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT, JUMP_LINE)
        self.assertEqual(len(log.tail.lines_for_echo()), 2)
        entries = log.tail.entries_for_reading()
        self.assertEqual([entry["text"] for entry in entries],
                         ["You are already managing 6 targets, as many as you have skill to.",
                          "Jumping from Amarr to Irnin"])

    def test_reading_first_then_echo_gives_the_same_answer(self):
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT, JUMP_LINE)
        self.assertEqual(len(log.tail.entries_for_reading()), 2)
        self.assertEqual(len(log.tail.lines_for_echo()), 2)

    def test_markup_is_stripped_before_the_line_is_split(self):
        log = TailingGameLog(self)
        log.append(COMBAT_LINE_WITH_MARKUP)
        line = log.tail.lines_for_echo()[0]
        self.assertNotIn("<", line)
        self.assertEqual(botlab_host.parse_game_log_line(line)["channel"], "combat")

    def test_a_newer_file_is_followed_from_its_end(self):
        # A new file is opened per client session. Replaying it from the top
        # would hand the bot every refusal of the previous session at once.
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT)
        log.tail.entries_for_reading()
        newer = os.path.join(log.directory, "20260803_010000_91000000.txt")
        with open(newer, "w", encoding="utf-8") as handle:
            handle.write(REFUSAL_DRONE_LIMIT + "\n")
        os.utime(newer, (2 ** 31, 2 ** 31))
        self.assertEqual(log.tail.entries_for_reading(), [])
        with open(newer, "a", encoding="utf-8") as handle:
            handle.write(REFUSAL_LOAD_WHILE_ACTIVE + "\n")
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertIn("cannot load or unload", entries[0]["text"])

    def test_a_wrapped_entry_reaches_the_reading_whole(self):
        log = TailingGameLog(self)
        log.append(QUESTION_WARNING, QUESTION_CONTINUATION)
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["channel"], "question")
        self.assertIn("standings penalty", entries[0]["text"])
        self.assertIn("Do you wish to proceed?", entries[0]["text"])

    def test_a_wrapped_entry_split_across_two_polls_is_still_whole(self):
        # The two halves are two writes, so a read can land between them. The
        # open entry is therefore held across polls and not only within one --
        # an entry that arrives whole only when the timing is lucky is the bug
        # this fixes, happening less often.
        log = TailingGameLog(self)
        log.append(QUESTION_WARNING)
        log.tail._poll()
        log.append(QUESTION_CONTINUATION)
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertIn("Do you wish to proceed?", entries[0]["text"])

    def test_a_continuation_arriving_after_the_entry_was_given_away_is_dropped(self):
        # The stated price of never holding an entry back. Once a reading has
        # taken it, appending to it would be writing into something the bot
        # already has -- so the half that arrives late is dropped, and what
        # must not happen is that it becomes an entry with no timestamp and no
        # channel of its own.
        log = TailingGameLog(self)
        log.append(QUESTION_WARNING)
        delivered = log.tail.entries_for_reading()
        self.assertEqual(len(delivered), 1)
        log.append(QUESTION_CONTINUATION)
        self.assertEqual(log.tail.entries_for_reading(), [])
        self.assertNotIn("Do you wish to proceed?", delivered[0]["text"])

    def test_a_wrapped_entry_does_not_swallow_the_line_after_it(self):
        log = TailingGameLog(self)
        log.append(QUESTION_WARNING, QUESTION_CONTINUATION, REFUSAL_TARGET_LIMIT)
        entries = log.tail.entries_for_reading()
        self.assertEqual([entry["channel"] for entry in entries],
                         ["question", "notify"])
        self.assertNotIn("Do you wish to proceed?", entries[1]["text"])

    def test_the_echo_still_carries_the_clients_own_lines(self):
        # The echo is the verbatim record of what the client wrote, and the
        # recorded runs are that record -- joining there would rewrite the one
        # ground truth every corpus-reading case in this suite consults.
        log = TailingGameLog(self)
        log.append(QUESTION_WARNING, QUESTION_CONTINUATION)
        self.assertEqual(log.tail.lines_for_echo(),
                         [QUESTION_WARNING, QUESTION_CONTINUATION])

    def test_a_newer_file_does_not_continue_the_previous_files_entry(self):
        # A new file is joined at its end, and its end can be *inside* an entry
        # the client had already wrapped -- so the first line read from it can
        # be a continuation belonging to a message this tail never saw the
        # start of. Attaching that to whatever the previous file left open
        # would put one session's text into another session's entry.
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT)
        log.tail._poll()
        newer = os.path.join(log.directory, "20260803_010000_91000000.txt")
        with open(newer, "w", encoding="utf-8") as handle:
            handle.write("\n".join(FILE_HEADER + [QUESTION_WARNING]) + "\n")
        os.utime(newer, (2 ** 31, 2 ** 31))
        log.tail._poll()
        with open(newer, "a", encoding="utf-8") as handle:
            handle.write(QUESTION_CONTINUATION + "\n")
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertIn("already managing", entries[0]["text"])
        self.assertNotIn("Do you wish to proceed?", entries[0]["text"])

    def test_a_file_truncated_under_us_does_not_fold_its_header(self):
        # The one path that re-reads a file from the top, and so the one that
        # meets a header block at all. The entry left open before the
        # truncation is what that block would attach to.
        log = TailingGameLog(self)
        log.append(REFUSAL_TARGET_LIMIT)
        log.tail._poll()
        with open(log.path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(FILE_HEADER) + "\n")
        entries = log.tail.entries_for_reading()
        self.assertEqual(len(entries), 1)
        self.assertNotIn("Gamelog", entries[0]["text"])

    def test_a_missing_directory_is_not_an_error(self):
        # `~/Documents/EVE/logs/Gamelogs` is behind a macOS Documents-folder
        # permission prompt, so a host that cannot read it must run without the
        # channel rather than fail the run.
        tail = botlab_host.GameLogTail(os.path.join(tempfile.gettempdir(), "no-such-gamelogs"))
        self.assertEqual(tail.entries_for_reading(), [])
        self.assertEqual(tail.lines_for_echo(), [])

    def test_neither_queue_grows_without_bound(self):
        # Each is drained once per reading, so reaching the cap means nothing
        # drained for a long time -- a paused session, or a run still searching
        # for the UI root.
        log = TailingGameLog(self)
        log.append(*([REFUSAL_TARGET_LIMIT] * (botlab_host.GAME_LOG_QUEUE_LIMIT + 50)))
        log.tail._poll()
        self.assertEqual(len(log.tail._reading_queue), botlab_host.GAME_LOG_QUEUE_LIMIT)
        self.assertEqual(len(log.tail._echo_queue), botlab_host.GAME_LOG_QUEUE_LIMIT)


class SyntheticNodeTest(unittest.TestCase):
    def entries(self, *lines):
        return [botlab_host.parse_game_log_line(line) for line in lines]

    def test_the_type_name_says_it_is_not_from_the_client(self):
        node = botlab_host.synthetic_game_log_node([])
        self.assertEqual(node["pythonObjectTypeName"], "MacOsHostSyntheticGameLog")
        for child in botlab_host.synthetic_game_log_node(
                self.entries(REFUSAL_DRONE_LIMIT))["children"]:
            self.assertEqual(child["pythonObjectTypeName"], "MacOsHostSyntheticGameLogEntry")

    def test_one_child_per_entry_in_order(self):
        node = botlab_host.synthetic_game_log_node(
            self.entries(REFUSAL_TARGET_LIMIT, JUMP_LINE, REFUSAL_DRONE_LIMIT))
        texts = [child["dictEntriesOfInterest"]["text"] for child in node["children"]]
        self.assertEqual(len(texts), 3)
        self.assertIn("already managing 6 targets", texts[0])
        self.assertIn("Jumping from Amarr", texts[1])
        self.assertIn("already controlling 5 drones", texts[2])

    def test_no_node_in_the_tree_carries_a_display_region(self):
        # Without one, `asUITreeNodeWithInheritedOffset` files the node as a
        # `ChildWithoutRegion` and every existing parser -- all of which
        # navigate by display region -- cannot reach it. That is what makes
        # attaching this to a real reading safe.
        node = botlab_host.synthetic_game_log_node(
            self.entries(REFUSAL_TARGET_LIMIT, JUMP_LINE))
        for each in [node] + node["children"]:
            for key in ("_displayX", "_displayY", "_displayWidth", "_displayHeight"):
                self.assertNotIn(key, each["dictEntriesOfInterest"])

    def test_the_text_is_not_where_getDisplayText_looks(self):
        # `getAllContainedDisplayTexts` runs over the raw tree with no region
        # filtering, and the mission runner asks it whether the whole reading
        # contains "No room for more". A game log line landing in that answer
        # would be a refusal dialog the client never showed.
        node = botlab_host.synthetic_game_log_node(
            self.entries("[ 2026.08.02 23:17:41 ] (notify) No room for more."))
        for each in [node] + node["children"]:
            self.assertNotIn("_setText", each["dictEntriesOfInterest"])
            self.assertNotIn("_text", each["dictEntriesOfInterest"])

    def test_it_survives_the_double_encoding_the_reading_travels_in(self):
        # `memoryReadingSerialRepresentationJson` is a JSON string containing
        # JSON, so anything in the node has to be encodable twice over.
        node = botlab_host.synthetic_game_log_node(self.entries(
            "[ 2026.08.02 23:17:41 ] (notify) You cannot warp while \"jammed\" -- 100% <b>"))
        round_tripped = json.loads(json.loads(json.dumps(json.dumps(node))))
        self.assertEqual(round_tripped, node)


class ReadFromWindowTest(unittest.TestCase):
    """The node as it actually reaches the bot, through `_read_from_window`."""

    class StubTreeWalker:
        def __init__(self):
            self.tree_json = {
                "pythonObjectAddress": "0x1234",
                "pythonObjectTypeName": "UIRoot",
                "dictEntriesOfInterest": {"_displayWidth": 3420, "_displayHeight": 2110},
                "children": [{"pythonObjectAddress": "0x2345",
                              "pythonObjectTypeName": "InfoPanelContainer",
                              "dictEntriesOfInterest": {},
                              "children": []}],
            }

        def tree(self, *args, **kwargs):
            return json.loads(json.dumps(self.tree_json))

    def read(self, host):
        host.roots[4242] = 0x1234
        host.metatype[4242] = 0x1
        host.str_type[4242] = 0x2
        host.tree_walkers[4242] = self.StubTreeWalker()
        result = host._read_from_window({"uiRootAddress": "0x1234"})
        return json.loads(result["Completed"]["memoryReadingSerialRepresentationJson"])

    def synthetic_children(self, tree):
        return [child for child in tree["children"]
                if child["pythonObjectTypeName"] == "MacOsHostSyntheticGameLog"]

    def test_the_reading_carries_what_the_client_said(self):
        log = TailingGameLog(self)
        host = botlab_host.VolatileHost(game_log=log.tail)
        log.append(COMBAT_LINE, REFUSAL_LOAD_WHILE_ACTIVE)
        tree = self.read(host)
        node = self.synthetic_children(tree)[0]
        self.assertEqual(len(node["children"]), 1)
        self.assertIn("cannot load or unload",
                      node["children"][0]["dictEntriesOfInterest"]["text"])

    def test_the_real_tree_is_left_alone(self):
        log = TailingGameLog(self)
        host = botlab_host.VolatileHost(game_log=log.tail)
        tree = self.read(host)
        self.assertEqual(tree["pythonObjectTypeName"], "UIRoot")
        self.assertEqual(tree["children"][0]["pythonObjectTypeName"], "InfoPanelContainer")
        self.assertEqual(len(self.synthetic_children(tree)), 1)

    def test_the_node_is_there_with_nothing_to_report(self):
        # Present-and-empty is "the client said nothing this reading". A bot
        # that could not tell that from "this host has no game log" would read
        # a missing channel as a command accepted.
        log = TailingGameLog(self)
        host = botlab_host.VolatileHost(game_log=log.tail)
        node = self.synthetic_children(self.read(host))[0]
        self.assertEqual(node["children"], [])

    def test_no_node_at_all_without_a_game_log(self):
        host = botlab_host.VolatileHost(game_log=None)
        self.assertEqual(self.synthetic_children(self.read(host)), [])

    def test_a_refusal_appears_in_exactly_one_reading(self):
        log = TailingGameLog(self)
        host = botlab_host.VolatileHost(game_log=log.tail)
        log.append(REFUSAL_DRONE_LIMIT)
        self.assertEqual(len(self.synthetic_children(self.read(host))[0]["children"]), 1)
        self.assertEqual(len(self.synthetic_children(self.read(host))[0]["children"]), 0)


class RecordedRunTest(unittest.TestCase):
    """Replay the game log lines a real run echoed, if that run's log is here.

    The recorded runs are the only sample of what this channel actually carries,
    and they are not in the repository -- so this skips rather than failing when
    they are absent.
    """

    LOG_DIR = os.path.expanduser("~/eve-bot-logs")

    def recorded_lines(self):
        lines = []
        for name in sorted(os.listdir(self.LOG_DIR)):
            if not name.endswith(".log"):
                continue
            with open(os.path.join(self.LOG_DIR, name), "r", encoding="utf-8",
                      errors="replace") as handle:
                for line in handle:
                    marker = "#   game log: "
                    if line.startswith(marker):
                        lines.append(line[len(marker):].rstrip("\n"))
        return lines

    def setUp(self):
        if not os.path.isdir(self.LOG_DIR):
            self.skipTest(f"no recorded runs at {self.LOG_DIR}")
        self.lines = [line for line in self.recorded_lines()
                      if not line.startswith("(")]
        if not self.lines:
            self.skipTest(f"no game log lines recorded under {self.LOG_DIR}")
        self.entries = botlab_host.game_log_entries_from_lines(self.lines)

    def test_every_recorded_line_parses(self):
        # Kept under its own name, and what it asserts has widened by exactly
        # what issue #124 was: a recorded line is now read either as an entry
        # or as the rest of the entry above it, and neither is a line the host
        # threw away. Before the fix this failed on 113 lines, every one of
        # them `Do you wish to proceed?`.
        wrapped = [after["text"] for _, after in self.wrapped_entries()]
        unread = []
        seen_an_entry = False
        for line in self.lines:
            if botlab_host.parse_game_log_line(line) is not None:
                seen_an_entry = True
            elif not seen_an_entry or not any(line in text for text in wrapped):
                unread.append(line)
        self.assertEqual(unread, [])

    def test_the_refusals_the_issue_names_are_carried(self):
        carried = [entry["text"] for entry in self.entries
                   if entry["channel"] not in
                   botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT]
        for refusal in ["already managing", "already controlling", "cannot load or unload",
                        "cannot do that while warping"]:
            self.assertTrue(any(refusal in text for text in carried),
                            f"no recorded line contains {refusal!r}")

    def test_the_combat_channel_is_most_of_the_file_and_none_of_the_channel(self):
        channels = [entry["channel"] for entry in self.entries]
        combat = channels.count("combat")
        self.assertGreater(combat, len(channels) / 2)
        carried = [channel for channel in channels
                   if channel not in botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT]
        self.assertNotIn("combat", carried)
        self.assertNotIn("bounty", carried)

    def wrapped_entries(self):
        """The entries that absorbed a continuation, and their first lines."""
        wrapped = []
        opened = (entry for entry in
                  (botlab_host.parse_game_log_line(line) for line in self.lines)
                  if entry is not None)
        for before, after in zip(opened, self.entries):
            if before["text"] != after["text"]:
                wrapped.append((before, after))
        return wrapped

    def test_the_corpus_carries_wrapped_entries_and_they_are_read_whole(self):
        # Asserted as a relation rather than as run 35's 113, so a corpus that
        # grows cannot turn a true claim red. What must hold is that the corpus
        # still contains the thing the fix is for, and that every instance of
        # it ends up inside an entry rather than beside one.
        wrapped = self.wrapped_entries()
        self.assertTrue(wrapped, "no recorded run carries a wrapped entry")
        dropped = [line for line in self.lines
                   if botlab_host.parse_game_log_line(line) is None]
        self.assertTrue(dropped, "no recorded run carries a continuation")
        for line in dropped:
            self.assertTrue(
                any(line in after["text"] for _, after in wrapped),
                "no entry carries %r" % line)

    def test_reading_the_wrapped_entries_changes_nothing_else(self):
        # The claim the whole appending design rests on, checked over 64,000
        # real lines rather than assumed: folding leaves the number of entries
        # alone, leaves every timestamp and channel alone, and touches the text
        # of exactly the entries that absorbed something.
        per_line = [botlab_host.parse_game_log_line(line)
                    for line in self.lines]
        per_line = [entry for entry in per_line if entry is not None]
        self.assertEqual(len(per_line), len(self.entries))
        changed = 0
        for before, after in zip(per_line, self.entries):
            self.assertEqual(before["timestamp"], after["timestamp"])
            self.assertEqual(before["channel"], after["channel"])
            if before["text"] != after["text"]:
                changed += 1
                self.assertTrue(after["text"].startswith(before["text"]))
        self.assertTrue(changed)
        self.assertLess(changed, len(self.entries) / 100)

    def test_the_damage_summaries_read_exactly_what_they_read_before(self):
        # All three are host-side consumers of this entry's text, and #32's
        # retreat and #90's zero-damage verdict are built on their numbers.
        # Nothing wraps on `(combat)`, so the summaries have to be identical
        # before and after -- not merely close. `parse_outgoing_miss` joined
        # them in #267 and is held to the same standard.
        for parse in (botlab_host.parse_incoming_damage,
                      botlab_host.parse_outgoing_damage,
                      botlab_host.parse_outgoing_miss):
            before = [parse(botlab_host.parse_game_log_line(line))
                      for line in self.lines
                      if botlab_host.parse_game_log_line(line) is not None]
            after = [parse(entry) for entry in self.entries]
            self.assertEqual([x for x in before if x is not None],
                             [x for x in after if x is not None])

    def test_no_wrapped_entry_is_on_a_channel_withheld_from_the_bot(self):
        for entry in self.entries:
            if "Do you wish to proceed?" in entry["text"]:
                self.assertNotIn(
                    entry["channel"],
                    botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT)

    def test_the_ammo_load_refusal_matches_the_same_entries_as_before(self):
        # `loadRefusalFromGameLog` is the oldest consumer of this channel and
        # the one #85 made the ammo swap's whole confirmation depend on. Its
        # two substrings are read out of `Bot.elm` rather than restated, for
        # the reason `test_ammo_load_refusal.py` gives, and applied to the
        # corpus both ways: appending to `text` must not add a refusal and must
        # not lose one.
        needles = load_refusal_substrings()
        self.assertEqual(len(needles), 2, needles)

        def refusals(entries):
            return [entry["text"] for entry in entries
                    if entry["channel"].strip().lower() == "notify"
                    and all(needle.lower() in entry["text"].lower()
                            for needle in needles)]

        before = refusals([botlab_host.parse_game_log_line(line)
                           for line in self.lines
                           if botlab_host.parse_game_log_line(line) is not None])
        self.assertTrue(before, "no recorded run carries a refused load")
        self.assertEqual(before, refusals(self.entries))

    def test_the_tail_and_the_pure_rule_agree_over_the_whole_corpus(self):
        # The rule is written twice -- once as a fold over lines a caller
        # already has, once as `GameLogTail._poll` reading a file that grows --
        # and a change landing in one and not the other is this repo's
        # signature failure. Replaying the corpus through a real tail is what
        # makes the two checkable rather than remembered.
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        path = os.path.join(directory, "20260804_000000_91000000.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        tail = botlab_host.GameLogTail(directory)
        tail.entries_for_reading()

        from_tail = []
        for chunk in self.chunks_that_do_not_split_an_entry(200):
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("".join(line + "\n" for line in chunk))
            from_tail.extend(tail.entries_for_reading())

        expected = [entry for entry in self.entries
                    if entry["channel"] not in
                    botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT]
        self.assertEqual(from_tail, expected)

    def chunks_that_do_not_split_an_entry(self, size):
        """The corpus in drained-sized pieces, none ending mid-entry.

        Drained in pieces because `GAME_LOG_QUEUE_LIMIT` caps the queue at 500
        and this corpus is two orders of magnitude larger -- one write and one
        drain would compare the last 500 entries against all of them and call
        the cap a disagreement.

        No piece ends between an entry and its continuation, because that is
        the one place the two forms are *documented* to differ: a drain hands
        the open entry away, so the half arriving after it is dropped. Placing
        a boundary there would be measuring the bound rather than the rule.
        """
        start = 0
        while start < len(self.lines):
            end = min(start + size, len(self.lines))
            while end < len(self.lines) and \
                    botlab_host.parse_game_log_line(self.lines[end]) is None:
                end += 1
            yield self.lines[start:end]
            start = end


def load_refusal_substrings():
    """The two literals `loadRefusalFromGameLog` matches, out of `Bot.elm`."""
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("loadRefusalFromGameLog readingFromGameClient =")
    body = source[start:source.index("|> List.head", start)]
    return re.findall(r'stringContainsIgnoringCase "([^"]+)" entry\.text', body)


class ClientGameLogTest(unittest.TestCase):
    """The client's own logs, which say more about wrapping than the bot runs do.

    `~/eve-bot-logs` holds what the host echoed during recorded runs, and every
    wrapped entry in it is the same `(question)` one. The client's own
    directory is 145 files and 214,630 lines going back years, and it is what
    the two unverified halves of issue #124 had to be settled against: whether
    a continuation can pass for a new entry, and whether an entry stops at two
    lines. Only a machine that has played this game has it.
    """

    GAMELOGS_GLOB = os.path.expanduser("~/Documents/EVE/logs/Gamelogs/*.txt")

    def setUp(self):
        self.paths = sorted(glob.glob(self.GAMELOGS_GLOB))
        if not self.paths:
            self.skipTest("no recorded game logs in ~/Documents/EVE/logs/Gamelogs")

    def files(self):
        """Each file's lines, de-marked up the way `_poll` does it."""
        for path in self.paths:
            with open(path, encoding="utf-8", errors="replace") as handle:
                lines = []
                for raw in handle:
                    line = " ".join(
                        botlab_host._GAME_LOG_MARKUP.sub("", raw.rstrip("\n")).split())
                    if line:
                        lines.append(line)
            yield path, lines

    def prefixless_groups(self):
        """Every run of prefix-less lines, with the entry above it or `None`."""
        for path, lines in self.files():
            above, run = None, []
            for line in lines:
                if botlab_host.parse_game_log_line(line) is None:
                    run.append(line)
                    continue
                if run:
                    yield path, above, run
                    run = []
                above = line
            if run:
                yield path, above, run

    def test_no_continuation_can_pass_for_a_new_entry(self):
        # The half issue #124 called unverified, and the whole safety of the
        # rule. A continuation beginning `[ something ] (something) ` would be
        # read as a new entry and its own entry would be truncated silently.
        # There is no such line: not one prefix-less line in this corpus even
        # begins with `[`, so the client's prefix separates the two shapes
        # completely.
        offenders = [line for _, _, run in self.prefixless_groups()
                     for line in run if line.startswith("[")]
        self.assertEqual(offenders, [])

    def test_an_entry_can_run_past_two_lines(self):
        # The other unverified half. The bot-run corpus has only two-line
        # examples; the client's own logs go to four, so a rule that folded one
        # continuation would silently keep a third of such an entry.
        depths = sorted({len(run) for _, above, run in self.prefixless_groups()
                         if above is not None})
        self.assertTrue(depths, "no wrapped entry in the client's logs")
        self.assertGreater(max(depths), 1)

    def test_every_prefixless_group_with_nothing_above_it_is_a_file_header(self):
        # What makes "continues the entry above it" safe rather than lucky: the
        # only prefix-less lines that are not continuations are the header
        # blocks, and every one of them opens its file.
        for path, above, run in self.prefixless_groups():
            if above is None:
                self.assertIn("Gamelog", run, path)

    def test_the_client_wraps_on_channels_the_bot_is_given(self):
        # Which is what makes this worth fixing at all -- a wrapping confined
        # to `(combat)` or `(bounty)` would never have reached a decision. It
        # is also why the damage summaries are untouched by the change.
        channels = {botlab_host.parse_game_log_line(above)["channel"]
                    for _, above, _ in self.prefixless_groups() if above}
        self.assertTrue(channels)
        self.assertFalse(
            channels & set(botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT))

    def test_reading_a_whole_client_file_keeps_every_line_but_its_header(self):
        # End to end over the real files, header block and all. Two things
        # have to hold at once: one entry per prefixed line, so no continuation
        # has quietly become an entry of its own; and every continuation --
        # every prefix-less line with an entry somewhere above it -- inside one
        # of those entries rather than beside it. Files with no entries at all
        # exist here (a session that opened and wrote nothing), and for those
        # the answer is no entries and a dropped header.
        for path, lines in self.files():
            entries = botlab_host.game_log_entries_from_lines(lines)
            texts = [entry["text"] for entry in entries]
            prefixed = 0
            for line in lines:
                if botlab_host.parse_game_log_line(line) is not None:
                    prefixed += 1
                elif prefixed:
                    self.assertTrue(any(line in text for text in texts),
                                    "%s dropped %r" % (path, line))
            self.assertEqual(len(entries), prefixed, path)


class VendoredParserTest(unittest.TestCase):
    """`ParseUserInterface.elm` is vendored once per app, and a change that
    lands in one copy and silently not the others is its own bug.

    The policy is all six, identically -- there is nothing app-specific in this
    parser, and the one deliberate divergence in this repo
    (`BotFrameworkSeparatingMemory.elm`'s `previousStepsEffects`, mission-runner
    only) is documented as such in CLAUDE.md. This case is what makes the policy
    checkable rather than a note somebody has to remember: it compares the block
    byte for byte across the six, and pins the two strings the host and the
    parser have to agree on across languages.

    **A second deliberate divergence, `eve-online-mining-bot`.** That app's
    whole tree was replaced with Viir's current upstream (a materially newer
    generation -- 2025-11-24 against this fork's prior 2023-04-05 base) rather
    than kept on this fork's own lineage, and vanilla upstream carries none of
    this fork's synthetic-node integration: no game-log channel, no damage
    summaries, no kill count. That is a real capability the mining bot gave up
    by taking the newer base, not an oversight -- porting the integration
    forward is tracked as follow-up work, not done here. `WITHOUT_GAME_LOG`
    names the one app this applies to; every other app is still held to "all
    six, identically" in full.
    """

    APPS_DIR = os.path.join(os.path.dirname(os.path.dirname(MACOS_HOST_DIR)),
                            "implement", "applications", "eve-online")

    WITHOUT_GAME_LOG = {"eve-online-mining-bot"}

    def parser_paths(self):
        paths = []
        for app in sorted(os.listdir(self.APPS_DIR)):
            path = os.path.join(self.APPS_DIR, app, "EveOnline", "ParseUserInterface.elm")
            if os.path.isfile(path):
                paths.append(path)
        return paths

    def app_of(self, path):
        return os.path.basename(os.path.dirname(os.path.dirname(path)))

    def block(self, source):
        start = source.index("{-| One line EVE's own client wrote")
        end = source.index("parseGameLogEntry entryNode =")
        end = source.index("\n\n\n", end)
        return source[start:end]

    def setUp(self):
        self.paths = self.parser_paths()
        if not self.paths:
            self.skipTest(f"no vendored parsers under {self.APPS_DIR}")
        self.sources = {}
        for path in self.paths:
            with open(path, encoding="utf-8") as handle:
                self.sources[path] = handle.read()
        self.sources_with_game_log = {
            path: source for path, source in self.sources.items()
            if self.app_of(path) not in self.WITHOUT_GAME_LOG
        }

    def test_every_copy_has_it(self):
        # Six vendored parsers total -- a sixth quietly appearing or
        # disappearing from the tree is itself worth catching, independent of
        # which ones carry the game-log integration.
        self.assertEqual(len(self.paths), 6, self.paths)
        self.assertEqual(
            {self.app_of(p) for p in self.paths} - self.WITHOUT_GAME_LOG,
            {self.app_of(p) for p in self.sources_with_game_log},
        )
        for path, source in self.sources_with_game_log.items():
            self.assertIn("    , gameLogEntriesSinceLastReading : Maybe (List GameLogEntry)\n",
                          source, path)
            self.assertIn(
                "    , gameLogEntriesSinceLastReading = "
                "parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTree\n",
                source, path)

    def test_every_copy_has_the_same_one(self):
        blocks = {path: self.block(source) for path, source in self.sources_with_game_log.items()}
        reference_path = next(iter(self.sources_with_game_log))
        reference = blocks[reference_path]
        for path, block in blocks.items():
            self.assertEqual(block, reference, path)

    def test_the_parser_looks_for_the_type_name_the_host_emits(self):
        # The one string the two languages have to agree on. Disagreeing costs
        # nothing at compile time and everything at runtime: the parser would
        # answer `Nothing` -- "this host has no game log" -- for every reading.
        for path, source in self.sources_with_game_log.items():
            self.assertIn(f'    "{botlab_host.SYNTHETIC_GAME_LOG_TYPE_NAME}"\n', source, path)

    def test_the_parser_reads_the_keys_the_host_writes(self):
        node = botlab_host.synthetic_game_log_node(
            [botlab_host.parse_game_log_line(REFUSAL_DRONE_LIMIT)])
        written = set(node["children"][0]["dictEntriesOfInterest"])
        self.assertEqual(written, {"timestamp", "channel", "text"})
        for path, source in self.sources_with_game_log.items():
            for key in written:
                self.assertIn(f'getStringPropertyFromDictEntries "{key}" entryNode',
                              source, path)

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_block(self):
        # Guards the exclusion itself: if eve-online-mining-bot ever regains
        # the integration (e.g. it gets ported forward onto the newer base),
        # WITHOUT_GAME_LOG has to shrink to match, or this test would be
        # quietly hiding a real copy that should be back in the byte-for-byte
        # comparison.
        excluded = [p for p in self.paths if self.app_of(p) in self.WITHOUT_GAME_LOG]
        self.assertTrue(excluded)
        for path in excluded:
            with self.assertRaises(ValueError, msg=path):
                self.block(self.sources[path])


if __name__ == "__main__":
    unittest.main()
