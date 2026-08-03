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

The lines here are real, taken from `~/eve-bot-logs/mission_run*.log` where the
host echoed them during recorded runs. Nothing here reads the live game log
directory, a game client, or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
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

    def test_every_recorded_line_parses(self):
        unparsed = [line for line in self.lines
                    if botlab_host.parse_game_log_line(line) is None]
        self.assertEqual(unparsed, [])

    def test_the_refusals_the_issue_names_are_carried(self):
        carried = [botlab_host.parse_game_log_line(line) for line in self.lines]
        carried = [entry["text"] for entry in carried
                   if entry["channel"] not in
                   botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT]
        for refusal in ["already managing", "already controlling", "cannot load or unload",
                        "cannot do that while warping"]:
            self.assertTrue(any(refusal in text for text in carried),
                            f"no recorded line contains {refusal!r}")

    def test_the_combat_channel_is_most_of_the_file_and_none_of_the_channel(self):
        channels = [botlab_host.parse_game_log_line(line)["channel"] for line in self.lines]
        combat = channels.count("combat")
        self.assertGreater(combat, len(channels) / 2)
        carried = [channel for channel in channels
                   if channel not in botlab_host.GAME_LOG_CHANNELS_WITHHELD_FROM_THE_BOT]
        self.assertNotIn("combat", carried)
        self.assertNotIn("bounty", carried)


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
    """

    APPS_DIR = os.path.join(os.path.dirname(os.path.dirname(MACOS_HOST_DIR)),
                            "implement", "applications", "eve-online")

    def parser_paths(self):
        paths = []
        for app in sorted(os.listdir(self.APPS_DIR)):
            path = os.path.join(self.APPS_DIR, app, "EveOnline", "ParseUserInterface.elm")
            if os.path.isfile(path):
                paths.append(path)
        return paths

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

    def test_every_copy_has_it(self):
        self.assertEqual(len(self.paths), 6, self.paths)
        for path, source in self.sources.items():
            self.assertIn("    , gameLogEntriesSinceLastReading : Maybe (List GameLogEntry)\n",
                          source, path)
            self.assertIn(
                "    , gameLogEntriesSinceLastReading = "
                "parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTree\n",
                source, path)

    def test_every_copy_has_the_same_one(self):
        blocks = {path: self.block(source) for path, source in self.sources.items()}
        reference = blocks[self.paths[0]]
        for path, block in blocks.items():
            self.assertEqual(block, reference, path)

    def test_the_parser_looks_for_the_type_name_the_host_emits(self):
        # The one string the two languages have to agree on. Disagreeing costs
        # nothing at compile time and everything at runtime: the parser would
        # answer `Nothing` -- "this host has no game log" -- for every reading.
        for path, source in self.sources.items():
            self.assertIn(f'    "{botlab_host.SYNTHETIC_GAME_LOG_TYPE_NAME}"\n', source, path)

    def test_the_parser_reads_the_keys_the_host_writes(self):
        node = botlab_host.synthetic_game_log_node(
            [botlab_host.parse_game_log_line(REFUSAL_DRONE_LIMIT)])
        written = set(node["children"][0]["dictEntriesOfInterest"])
        self.assertEqual(written, {"timestamp", "channel", "text"})
        for path, source in self.sources.items():
            for key in written:
                self.assertIn(f'getStringPropertyFromDictEntries "{key}" entryNode',
                              source, path)


if __name__ == "__main__":
    unittest.main()
