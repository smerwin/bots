"""Tests for noticing that this ship's shots are achieving nothing.

Issue #90. Run 27 locked an `Infested Asteroid` and shot it with every gun for
roughly 290 consecutive readings. Every shot **landed** and every one did zero
damage, while nine real rats sat on the same overview untouched and the mission
tracker had already read `no instruction (next step: Set Destination)` -- the
objective was finished and the bot was holding the grid to shoot a rock. It
ended with the shield at 0% and three named attackers hitting the ship while its
own guns were still pointed at the asteroid.

**The bot could not see any of it.** The host matched only
`^(\\d+) from (?P<attacker>.+)$`, the incoming half, which #32 summed for the
retreat. Outgoing `N to <target>` lines were matched nowhere, so no field in any
reading said how much damage this ship was dealing and no decision could ask.

Three things here can fail in the direction that looks like success, and they
are what these cases exist for.

**The fail-safe direction is the opposite of #37's.** There an absent channel
must not read as "the grid is quiet"; here it must not read as "everything is
immune". A host that does not carry the game log has to keep the guns firing,
so `Nothing` from the parser may never add a name to the verdict.

**One zero is not evidence.** A threshold that fired on the first one would
refuse to shoot anything the moment a resist, a glancing hit or a target dying
mid-volley produced a zero -- and refusing is latched for the session, so a
false positive costs the run. `ThresholdCalibrationTest` reads the number out of
`Bot.elm` and checks it against what the client actually wrote.

**What the threshold has to clear is a run, not a target.** #90's own
calibration rested on there being no target that ever read both zero and
nonzero, and issue #158 is that claim expiring on a `Centii Servant` while the
rule was untouched. The rule never asked that question: it tallies *consecutive*
readings whose whole summary for a target was zero and clears the tally on any
reading that target took damage. So the separation is recounted here as the run
length -- one, against the ten the shortest episode worth catching runs -- and
eight is a number in that gap rather than one in empty space.

**A verdict that is not written down is not a verdict.** A reading's entries are
gone by the next one, so a branch that saw the zero and recorded nothing would
see it once and go back to shooting the same object -- the failure
`loadRefusedByClient` documents.

The corpus is real. Every line quoted here was written by the client during a
recorded session under `~/Documents/EVE/logs/Gamelogs`, and the aggregate counts
come from the outgoing damage lines across those files -- 77,316 of them when
#90 was written and 165,420 today. Nothing here reads a live game client or a
bot; the counts are asserted as relations rather than as numbers, so a corpus
that goes on growing cannot turn a true claim red.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
import glob
import json
import os
import re
import sys
import tempfile
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

GAMELOGS_GLOB = os.path.expanduser("~/Documents/EVE/logs/Gamelogs/*.txt")
NO_GAMELOGS = "no recorded game logs in ~/Documents/EVE/logs/Gamelogs"

# Damage this ship dealt, verbatim from the recorded sessions with the client's
# colour and font markup already stripped the way `GameLogTail._poll` strips it.
# The last one is the whole issue: a shot that landed and achieved nothing.
OUTGOING = [
    ("[ 2026.08.03 12:11:04 ] (combat) 104 to Mammon Apis - Hits", 104, "Mammon Apis"),
    ("[ 2026.08.03 12:11:07 ] (combat) 32 to Mercenary Commander - Acolyte I - Smashes",
     32, "Mercenary Commander"),
    ("[ 2026.08.03 12:11:09 ] (combat) 15 to Mercenary Commander - Acolyte I - Glances Off",
     15, "Mercenary Commander"),
    ("[ 2026.08.03 12:16:31 ] (combat) 0 to Infested Asteroid - "
     "Focused Modulated Medium Energy Beam I - Hits", 0, "Infested Asteroid"),
]

# Damage this ship took. The same shape with "from", and there are 31,524 of
# them against 77,316 of the above -- so confusing the two is not a corner case.
INCOMING = [
    "[ 2026.08.03 04:26:58 ] (combat) 49 from Centior Monster - Penetrates",
    "[ 2026.08.03 04:26:59 ] (combat) 74 from Centum Fiend - Mjolnir Heavy Missile - Hits",
]

# Free, in both directions, and deliberately not damage. A miss costs nothing
# and counting it as a landed hit of zero would build a case for immunity out of
# a range problem -- which is the one way this guard could fire on a target the
# guns simply cannot reach.
MISSES = [
    "[ 2026.07.31 18:20:09 ] (combat) Your Hobgoblin II misses Vigilant Sentry Tower "
    "completely - Hobgoblin II",
    "[ 2026.08.03 04:26:55 ] (combat) Centior Misshape misses you completely",
]

# The two `(combat)` shapes that would match a looser outgoing pattern. The
# first begins with a digit and is not damage (19 across the corpus); the second
# is the only other place " to " appears on this channel, and it begins with a
# word -- which is why the matcher is anchored on `^<number> to `.
NOT_OUTGOING_DAMAGE = [
    "[ 2026.07.29 20:14:02 ] (combat) 100 GJ energy neutralized Sleepless Outguard - "
    "Sleepless Outguard",
    "[ 2026.07.30 18:22:36 ] (combat) Warp scramble attempt from Chief Republic Isak to you!",
    "[ 2026.07.30 18:22:40 ] (combat) Warp disruption attempt from Legion [HULL] [.338] "
    "[Tonz Ritc] - to Joint Harvesting Bestower",
]

NON_COMBAT = [
    "[ 2026.08.03 04:27:33 ] (notify) The ship you are piloting does not have "
    "targeting systems installed.",
    "[ 2026.07.31 03:56:19 ] (None) Jumping from Hedion to Amarr",
]


def bot_constant(name):
    """A number read out of `Bot.elm` rather than restated beside it.

    The same coupling `test_incoming_damage` puts on the retreat's thresholds.
    A threshold quietly edited to a value the evidence does not support is the
    kind of change that never fails until a run refuses to shoot something it
    could have killed.
    """
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
        source = handle.read()
    match = re.search(rf"^{name} =\n    (-?\d+)$", source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"{name} not found in Bot.elm")
    return int(match.group(1))


_RECORDED_OUTGOING = []


def recorded_outgoing_damage():
    """Every `N to <target>` line the client wrote, timestamp included.

    Read through the host's own stripping and parsing rather than a second
    regex here, so a matcher that drifts from what the client writes is what
    these cases measure rather than something they reimplement.

    Cached for the process: the corpus is 185 files and several cases fold it
    more than one way, so re-reading it per case was most of this file's time.
    """
    if _RECORDED_OUTGOING:
        return _RECORDED_OUTGOING
    paths = sorted(glob.glob(GAMELOGS_GLOB))
    if not paths:
        raise unittest.SkipTest(NO_GAMELOGS)
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = " ".join(botlab_host._GAME_LOG_MARKUP.sub("", raw).split())
                entry = botlab_host.parse_game_log_line(line)
                dealt = botlab_host.parse_outgoing_damage(entry)
                if dealt is not None:
                    _RECORDED_OUTGOING.append(
                        (path, dealt[0], dealt[1], entry["timestamp"]))
    if not _RECORDED_OUTGOING:
        raise unittest.SkipTest(NO_GAMELOGS)
    return _RECORDED_OUTGOING


def outgoing_damage_in_recorded_logs():
    """The same lines as `(path, amount, target)`, which is what most cases want."""
    return [(path, amount, target)
            for path, amount, target, _ in recorded_outgoing_damage()]


def targets_that_ever_took_damage():
    return {target for _, amount, target in outgoing_damage_in_recorded_logs()
            if amount != 0}


def summaries_the_host_would_have_built():
    """What each reading's `MacOsHostSyntheticOutgoingDamage` node would have said.

    The host does not carry lines, it carries `{name, hits, damage}` summed per
    target per reading -- so a reading in which one gun reads 0 and a drone
    reads 55 on the same target is handed to the bot as `damage = 55`, and the
    rule reads that as the target taking damage rather than as a zero. Any case
    counting *lines* is therefore measuring something the bot never sees.

    Readings are the client's own second, which is the finest its timestamps
    can distinguish and shorter than any real reading (one to eight seconds).
    That is the fold most favourable to a zero standing alone in a reading of
    its own, so a claim that holds here holds at every real reading length.

    Returns `{(path, target): [summary, ...]}` in order, one entry per reading
    that named the target, in `outgoing_damage_for_reading`'s own shape plus the
    timestamp the fold was cut on -- which the host's node does not carry and
    nothing handed to the rule reads.
    """
    readings = collections.OrderedDict()
    for path, amount, target, timestamp in recorded_outgoing_damage():
        key = (path, target)
        entries = readings.setdefault(key, [])
        if entries and entries[-1]["timestamp"] == timestamp:
            entries[-1]["hits"] += 1
            entries[-1]["damage"] += amount
        else:
            entries.append({"name": target, "hits": 1, "damage": amount,
                            "timestamp": timestamp})
    return readings


class OutgoingDamageMatchingTest(unittest.TestCase):
    def entry(self, line):
        return botlab_host.parse_game_log_line(line)

    def test_damage_dealt_is_recognised_with_its_target(self):
        for line, amount, target in OUTGOING:
            self.assertEqual(
                botlab_host.parse_outgoing_damage(self.entry(line)),
                (amount, target), line)

    def test_a_landed_shot_for_zero_is_damage_dealt_of_zero(self):
        # The distinction the whole issue rests on, and the one place this
        # differs from its incoming twin: zero is a value here, not an absence.
        # Discarding it as "no damage" would throw the signal away.
        line, _, target = OUTGOING[-1]
        self.assertEqual(botlab_host.parse_outgoing_damage(self.entry(line)),
                         (0, target))

    def test_damage_taken_is_not_damage_dealt(self):
        for line in INCOMING:
            self.assertIsNone(botlab_host.parse_outgoing_damage(self.entry(line)), line)

    def test_damage_dealt_is_not_damage_taken(self):
        # The other direction, so neither matcher can quietly widen into the
        # other's lines. A retreat armed by this ship's own guns would fire
        # hardest when the fight was going well.
        for line, _, _ in OUTGOING:
            self.assertIsNone(botlab_host.parse_incoming_damage(self.entry(line)), line)

    def test_a_miss_is_not_a_landed_hit(self):
        for line in MISSES:
            self.assertIsNone(botlab_host.parse_outgoing_damage(self.entry(line)), line)

    def test_the_other_combat_shapes_are_not_damage_dealt(self):
        for line in NOT_OUTGOING_DAMAGE:
            self.assertIsNone(botlab_host.parse_outgoing_damage(self.entry(line)), line)

    def test_other_channels_are_never_damage_dealt(self):
        for line in NON_COMBAT:
            self.assertIsNone(botlab_host.parse_outgoing_damage(self.entry(line)), line)

    def test_a_line_that_does_not_parse_is_not_damage_dealt(self):
        self.assertIsNone(botlab_host.parse_outgoing_damage(None))


class TailFanOutTest(unittest.TestCase):
    """The outgoing queue is the tail's fourth reader of one file offset.

    #30's bug was one cursor with two readers, where whichever drained first
    took that cycle's lines and the other got nothing -- intermittently and
    without a word. A fourth reader is the same hazard again, so the same
    property is asserted: each queue sees every line exactly once, whatever the
    drain order.
    """

    def make_tail(self, tmpdir, lines):
        path = os.path.join(tmpdir, "20260803_000000_1.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("header\n")
        tail = botlab_host.GameLogTail(tmpdir)
        tail._poll()  # first sight of a file starts at its end
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in lines))
        return tail

    def drain(self, tail, order):
        readers = {
            "outgoing": tail.outgoing_damage_for_reading,
            "incoming": tail.incoming_damage_for_reading,
            "entries": tail.entries_for_reading,
            "echo": tail.lines_for_echo,
        }
        return {name: readers[name]() for name in order}

    def test_no_queue_eats_another(self):
        lines = [OUTGOING[0][0], INCOMING[0], NON_COMBAT[0], OUTGOING[3][0]]
        orders = [
            ("outgoing", "incoming", "entries", "echo"),
            ("echo", "entries", "incoming", "outgoing"),
            ("incoming", "outgoing", "echo", "entries"),
        ]
        for order in orders:
            with self.subTest(order=order):
                with tempfile.TemporaryDirectory() as tmpdir:
                    drained = self.drain(self.make_tail(tmpdir, lines), order)
                    self.assertEqual(
                        sorted((t["name"], t["hits"], t["damage"])
                               for t in drained["outgoing"]),
                        [("Infested Asteroid", 1, 0), ("Mammon Apis", 1, 104)])
                    self.assertEqual(drained["incoming"]["damage"], 49)
                    self.assertEqual(len(drained["entries"]), 1)
                    self.assertEqual(len(drained["echo"]), 4)

    def test_outgoing_damage_is_scoped_to_the_reading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tail = self.make_tail(tmpdir, [OUTGOING[0][0]])
            self.assertEqual(len(tail.outgoing_damage_for_reading()), 1)
            # Gone by the next reading, like every other part of this channel.
            self.assertEqual(tail.outgoing_damage_for_reading(), [])


class SummaryTest(unittest.TestCase):
    def summarise(self, lines):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "20260803_000000_1.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("header\n")
            tail = botlab_host.GameLogTail(tmpdir)
            tail._poll()
            with open(path, "a", encoding="utf-8") as handle:
                handle.write("".join(line + "\n" for line in lines))
            return tail.outgoing_damage_for_reading()

    def test_hits_and_damage_are_summed_per_target(self):
        summary = self.summarise([line for line, _, _ in OUTGOING])
        self.assertEqual(
            {t["name"]: (t["hits"], t["damage"]) for t in summary},
            {"Mammon Apis": (1, 104),
             "Mercenary Commander": (2, 47),
             "Infested Asteroid": (1, 0)})

    def test_run_27s_own_reading_shape(self):
        """Guns on the rock, drones on a rat, in the same reading.

        This is why the summary is per target and not one total. Run 27's
        drones were landing real damage on a `Mercenary Commander` in the very
        readings its guns were achieving nothing on the asteroid, so a single
        sum would have read as a healthy 47 hitpoints throughout the incident
        this whole change exists to catch.
        """
        summary = self.summarise([
            OUTGOING[3][0], OUTGOING[3][0], OUTGOING[3][0],
            OUTGOING[1][0], OUTGOING[2][0],
        ])
        by_name = {t["name"]: t for t in summary}
        self.assertEqual((by_name["Infested Asteroid"]["hits"],
                          by_name["Infested Asteroid"]["damage"]), (3, 0))
        self.assertEqual((by_name["Mercenary Commander"]["hits"],
                          by_name["Mercenary Commander"]["damage"]), (2, 47))

    def test_misses_reach_no_target(self):
        self.assertEqual(self.summarise(MISSES + NON_COMBAT), [])

    def test_the_order_is_stable(self):
        # Two identical readings must produce two identical nodes, or a
        # consumer comparing readings sees changes that are only ordering.
        lines = [OUTGOING[1][0], OUTGOING[2][0], OUTGOING[0][0], OUTGOING[3][0]]
        self.assertEqual(self.summarise(lines), self.summarise(lines))
        self.assertEqual([t["name"] for t in self.summarise(lines)],
                         ["Mercenary Commander", "Infested Asteroid", "Mammon Apis"])


class SyntheticNodeTest(unittest.TestCase):
    """#30's four safety properties, applied to the third synthetic node."""

    def node(self, targets):
        return botlab_host.synthetic_outgoing_damage_node(targets)

    def test_the_node_carries_no_display_region(self):
        # With no region, `asUITreeNodeWithInheritedOffset` files it as a
        # `ChildWithoutRegion` and every parser that navigates by region walks
        # straight past it.
        node = self.node([{"name": "Infested Asteroid", "hits": 12, "damage": 0}])
        for entries in [node["dictEntriesOfInterest"]] + [
                child["dictEntriesOfInterest"] for child in node["children"]]:
            for key in ("_displayX", "_displayY", "_displayWidth", "_displayHeight"):
                self.assertNotIn(key, entries)

    def test_a_target_name_cannot_reach_getdisplaytext(self):
        # `getAllContainedDisplayTexts` runs over the raw tree with no region
        # filtering, and the mission runner asks it whether the whole reading
        # contains "No room for more". A target's name arriving in that answer
        # would be a dialog the client never showed.
        node = self.node([{"name": "No room for more", "hits": 1, "damage": 0}])
        for child in node["children"]:
            for key in ("_setText", "_text"):
                self.assertNotIn(key, child["dictEntriesOfInterest"])

    def test_a_reading_with_nothing_landing_still_produces_a_node(self):
        # An empty list is an answer -- the client reported no shot landing.
        # The node's *absence* is the other answer, and here collapsing the two
        # would have a bot conclude every target is immune on a host that
        # simply has no game log.
        node = self.node([])
        self.assertEqual(node["children"], [])
        self.assertEqual(node["pythonObjectTypeName"],
                         botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME)

    def test_the_type_names_say_they_are_fictions(self):
        for name in (botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME,
                     botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TARGET_TYPE_NAME):
            self.assertIn("MacOsHost", name)
        self.assertEqual(
            len({botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME,
                 botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TARGET_TYPE_NAME,
                 botlab_host.SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME,
                 botlab_host.SYNTHETIC_GAME_LOG_TYPE_NAME,
                 botlab_host.SYNTHETIC_GAME_LOG_ENTRY_TYPE_NAME}), 5)

    def test_the_node_is_attached_beside_the_other_two(self):
        with open(os.path.join(MACOS_HOST_DIR, "botlab_host", "botlab_host.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        body = source[source.index("def _read_from_window"):]
        for call in ("synthetic_game_log_node(",
                     "synthetic_incoming_damage_node(",
                     "synthetic_outgoing_damage_node("):
            self.assertIn(call, body)


class VendoredParserTest(unittest.TestCase):
    """`ParseUserInterface.elm` is vendored six times; the policy is all six.

    #30's check applied to the new block. A type name that disagreed across the
    two languages would have the parser answer `Nothing` -- "this host has no
    outgoing damage channel" -- on every reading, which is a guard that never
    fires and is indistinguishable from a bot with nothing to give up on.
    """

    APPS_DIR = os.path.join(REPO_DIR, "implement", "applications", "eve-online")

    def setUp(self):
        self.sources = {}
        for app in sorted(os.listdir(self.APPS_DIR)):
            path = os.path.join(self.APPS_DIR, app, "EveOnline", "ParseUserInterface.elm")
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as handle:
                    self.sources[path] = handle.read()
        if not self.sources:
            self.skipTest(f"no vendored parsers under {self.APPS_DIR}")

    def block(self, source):
        start = source.index("{-| What this ship's own shots achieved")
        end = source.index("syntheticOutgoingDamageNodeTypeName =", start)
        return source[start:source.index("\n\n\n", end)]

    def test_every_copy_has_it(self):
        self.assertEqual(len(self.sources), 6, sorted(self.sources))
        for path, source in self.sources.items():
            self.assertIn(
                "    , outgoingDamageSinceLastReading : "
                "Maybe (List OutgoingDamageToTarget)\n", source, path)
            self.assertIn(
                "    , outgoingDamageSinceLastReading = "
                "parseOutgoingDamageSinceLastReadingFromUITreeRoot uiTree\n",
                source, path)

    def test_every_copy_has_the_same_one(self):
        blocks = {path: self.block(source) for path, source in self.sources.items()}
        reference = blocks[sorted(blocks)[0]]
        for path, block in blocks.items():
            self.assertEqual(block, reference, path)

    def test_the_parser_looks_for_the_type_name_the_host_emits(self):
        for path, source in self.sources.items():
            self.assertIn(
                f'    "{botlab_host.SYNTHETIC_OUTGOING_DAMAGE_TYPE_NAME}"\n',
                source, path)

    def test_the_parser_reads_the_keys_the_host_writes(self):
        node = botlab_host.synthetic_outgoing_damage_node(
            [{"name": "Infested Asteroid", "hits": 12, "damage": 0}])
        self.assertEqual(set(node["children"][0]["dictEntriesOfInterest"]),
                         {"name", "hits", "damage"})
        for path, source in self.sources.items():
            block = self.block(source)
            for key in ("hits", "damage"):
                self.assertIn(f'getIntPropertyFromDictEntries "{key}"', block, path)
            self.assertIn('getStringPropertyFromDictEntries "name"', block, path)


class ThresholdCalibrationTest(unittest.TestCase):
    """The number, checked against what the client actually wrote.

    Read out of `Bot.elm` rather than restated, the same coupling
    `test_incoming_damage` puts on the retreat's thresholds. A threshold quietly
    edited to a value the evidence does not support is the kind of change that
    never fails until a run refuses to shoot something it could have killed.
    """

    def constant(self, name):
        return bot_constant(name)

    def episodes(self):
        """Runs of consecutive zero-damage hits on one target within a session.

        Broken by that target taking any damage at all, which is the same reset
        the bot's own memory applies.
        """
        running = collections.defaultdict(list)
        finished = []
        for path, amount, target in outgoing_damage_in_recorded_logs():
            key = (path, target)
            if amount == 0:
                running[key].append(amount)
            elif running.get(key):
                finished.append((target, len(running.pop(key))))
        finished.extend((target, len(hits)) for (_, target), hits in running.items())
        return finished

    def test_a_zero_on_a_target_the_guns_are_hurting_is_isolated(self):
        """The premise the threshold rests on, which is about runs and not targets.

        #90 rested it on a disjointness instead -- across 77,316 outgoing lines
        naming 294 distinct targets, eight ever produced a zero and none of the
        eight ever produced a nonzero -- and called eight margin rather than a
        separator because there was no observed overlap for it to sit in. Issue
        #158 is that claim expiring: `Centii Servant` now both took damage and
        read zero, and no edit to the rule caused it.

        **The rule never asked that question.** `zeroDamageMemoryAfterReading`
        tallies *consecutive* readings in which a target's whole summary was
        zero and clears the tally outright on any reading it took damage, so
        what has to stay small is the run and not the count of targets. So the
        separation is recounted here as the run length, which is what eight has
        to clear.

        Two things ride beside the relation, because a comparison against a
        constant is satisfied by any constant large enough. The threshold has to
        keep **several times** the observed worst case rather than one hit of
        headroom -- a false positive is latched for the session, so a number one
        above the longest run the corpus has ever shown is not a calibration --
        which is what rules out a threshold of two or three sitting in the same
        gap and claiming the same evidence. And the run itself has a fixed
        ceiling, which is what stops a threshold raised to cover a real overlap
        from making this pass: the corpus's own answer is one, and a target
        being hit that reads zero three times running is a different animal from
        an isolated resist and wants looking at whatever the threshold says.
        """
        hurt = targets_that_ever_took_damage()
        overlap = {target for _, amount, target in outgoing_damage_in_recorded_logs()
                   if amount == 0 and target in hurt}
        self.assertTrue(
            overlap,
            "no target in this corpus both read zero and took damage, so this "
            "case is measuring nothing -- see issue #158")
        runs = sorted(((target, length) for target, length in self.episodes()
                       if target in hurt), key=lambda pair: -pair[1])
        longest = runs[0][1]
        threshold = self.constant("defaultZeroDamageHitsBeforeGivingUp")
        self.assertLess(longest, threshold, repr(runs))
        self.assertLessEqual(longest * 4, threshold, repr(runs))
        self.assertLessEqual(longest, 3, repr(runs))

    def test_the_threshold_catches_every_episode_worth_catching(self):
        """Eight is the largest value that still catches the long ones.

        The zero-only episodes ran 3, 3, 5, 10, 28, 74, 86, 101 and 108 landed
        hits. The short ones ended on their own inside a few seconds and are
        nothing to fix; the smallest that did not is ten, so a threshold above
        that would have watched run 27 shoot its rock for the full 414 seconds
        and said nothing.

        With the case above this is the whole calibration: the longest run on a
        target the guns were hurting is one, the shortest episode worth catching
        is ten, and eight is a number in that gap. #90 could only say the gap was
        empty, which is what issue #158 retired.
        """
        threshold = self.constant("defaultZeroDamageHitsBeforeGivingUp")
        lengths = sorted(length for _, length in self.episodes())
        long_ones = [length for length in lengths if length >= 10]
        self.assertTrue(long_ones, "the corpus holds no episode worth catching")
        self.assertLessEqual(threshold, min(long_ones))
        self.assertGreater(threshold, 1,
                           "one zero is not evidence -- see the issue")

    def test_run_27s_own_episode_would_have_been_cut_short(self):
        # The incident this exists for, named rather than left to the aggregate.
        episodes = dict(self.episodes())
        self.assertIn("Infested Asteroid", episodes,
                      "run 27's asteroid is not in this machine's game logs")
        self.assertGreater(episodes["Infested Asteroid"],
                           self.constant("defaultZeroDamageHitsBeforeGivingUp"))

    def test_the_tally_list_is_bounded(self):
        self.assertGreater(self.constant("zeroDamageTalliesTracked"), 0)


class ZeroDamageRuleTest(unittest.TestCase):
    """The accumulation rule, executed rather than restated.

    `zeroDamageMemoryAfterReading` is arithmetic over a list where an off-by-one
    is invisible in review, and CLAUDE.md's rule is that a Python restatement of
    an Elm rule tests the restatement. So the real `Bot.elm` answers these.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(ElmRepl, prefix="test-zero-damage-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    DEFINITIONS = (
        "empty = { landedHitsAtZero = [], namesGivenUpOn = [], "
        "hostCarriesTheChannel = False }",
        "step t o m = zeroDamageMemoryAfterReading t o m",
        "run t os = List.foldl (\\o m -> step t (Just o) m) empty os",
        'rock n = { name = "Infested Asteroid", hits = n, damage = 0 }',
    )

    def given_up(self, expressions):
        return self.repl.values(
            expressions, r"\[([^\]]*)\]\s*: List String",
            definitions=self.DEFINITIONS)

    def test_the_threshold_is_where_the_verdict_lands(self):
        threshold, under, over = self.given_up([
            "(run 8 (List.repeat 8 [ rock 1 ])).namesGivenUpOn",
            "(run 8 (List.repeat 7 [ rock 1 ])).namesGivenUpOn",
            "(run 8 (List.repeat 40 [ rock 1 ])).namesGivenUpOn",
        ])
        self.assertEqual(threshold, '"Infested Asteroid"')
        self.assertEqual(under, "")
        # And it is recorded once however long the object is shot at, so the
        # list cannot grow with every reading after the verdict.
        self.assertEqual(over, '"Infested Asteroid"')

    def test_the_corpus_overlap_folded_through_the_rule_tallies_nothing(self):
        """Issue #158's own overlap, as readings, through the real rule.

        `ThresholdCalibrationTest` recounts the separation as *lines*, which is
        the pessimistic fold. The host does not carry lines: it carries
        `{name, hits, damage}` summed per target per reading, so a reading in
        which a drone reads 0 and the same drone reads 55 on the same target is
        handed over as `damage = 55` -- which this rule reads as the target
        taking damage and clears the tally on.

        That is what every one of the corpus's zeros on a target that was being
        hurt turns out to be. All three were written in the same second as a
        real hit on that same target:

            0 to Centii Servant - Acolyte I - Hits
            55 to Centii Servant - Acolyte I - Smashes

        So the sessions carrying the overlap are folded here at the client's own
        second -- shorter than any real reading, and so the fold most favourable
        to a zero standing alone -- and run through `Bot.elm` itself. Nothing is
        given up on, and the tally never leaves zero: the overlap that retired
        #90's claim never reached the bot at all.

        The peak is asserted against a fixed ceiling as well as against the
        threshold, so a threshold raised to cover a real overlap cannot make
        this pass.

        **The same session with its damage taken out is the control**, and it
        rides along because an assertion that something did not happen passes
        just as well on a fold that produced nothing, a literal the repl could
        not compile, or a session that turned out to be empty. Same target, same
        readings, same hit counts, `damage = 0` throughout: the rule gives up on
        it. So what saves the bot here is the damage in those readings and not
        an answer that never arrived.
        """
        hurt = targets_that_ever_took_damage()
        # The sessions that wrote a zero-damage *line* against such a target.
        # No other session can tally anything for it, so folding those adds
        # thousands of readings and can only ever answer nothing.
        wrote_a_zero = {(path, target)
                        for path, amount, target in outgoing_damage_in_recorded_logs()
                        if amount == 0 and target in hurt}
        sessions = [(key, summaries)
                    for key, summaries in summaries_the_host_would_have_built().items()
                    if key in wrote_a_zero]
        self.assertTrue(
            sessions,
            "no session in this corpus holds a zero on a target that was being "
            "hurt, so this case is measuring nothing -- see issue #158")
        threshold = bot_constant("defaultZeroDamageHitsBeforeGivingUp")
        peak_definition = (
            "peak t os = List.foldl (\\o ( m, best ) -> let next = step t"
            " (Just o) m in ( next, max best (List.sum (List.map .hits"
            " next.landedHitsAtZero)) )) ( empty, 0 ) os |> Tuple.second",)
        for (path, target), summaries in sessions:
            def fold(damage_of):
                return ", ".join(
                    "[ { name = %s, hits = %d, damage = %d } ]"
                    % (json.dumps(target), summary["hits"], damage_of(summary))
                    for summary in summaries)

            readings = fold(lambda summary: summary["damage"])
            without_damage = fold(lambda _: 0)
            where = "%s / %s" % (os.path.basename(path), target)
            given_up, control = self.given_up([
                "(run %d [ %s ]).namesGivenUpOn" % (threshold, readings),
                "(run %d [ %s ]).namesGivenUpOn" % (threshold, without_damage),
            ])
            self.assertEqual(given_up, "", where)
            self.assertEqual(control, json.dumps(target), where)
            peak, = self.repl.values(
                ["peak %d [ %s ]" % (threshold, readings)],
                r"(\d+) : Int", definitions=self.DEFINITIONS + peak_definition)
            self.assertLess(int(peak), threshold, where)
            self.assertLessEqual(int(peak), 3, where)

    def test_a_target_taking_any_damage_never_trips_it(self):
        """A merely well-tanked target is not an immune one.

        One hitpoint a shot, forty readings, and nothing is given up on -- which
        is the difference between "these shots achieve nothing" and "these
        shots are slow".
        """
        tanked, = self.given_up([
            '(run 8 (List.repeat 40 '
            '[ { name = "Tough Rat", hits = 1, damage = 1 } ])).namesGivenUpOn',
        ])
        self.assertEqual(tanked, "")

    def test_damage_partway_through_clears_the_evidence(self):
        cleared, = self.repl.values(
            ["(run 8 (List.repeat 4 [ rock 1 ] "
             '++ [ [ { name = "Infested Asteroid", hits = 1, damage = 5 } ] ] '
             "++ List.repeat 3 [ rock 1 ])).landedHitsAtZero"],
            r"hits = (\d+)", definitions=self.DEFINITIONS)
        self.assertEqual(cleared, "3")

    def test_a_miss_builds_no_case(self):
        """Missing is a range problem, and giving up is not the answer to it.

        The host never counts a miss, because the client writes no damage number
        for one -- so a reading of nothing but misses reaches this with `hits =
        0` and must add nothing. Without that, a gun firing out of range would
        give up on everything it could not reach.
        """
        missing, = self.given_up([
            '(run 8 (List.repeat 40 '
            '[ { name = "Out Of Range", hits = 0, damage = 0 } ])).namesGivenUpOn',
        ])
        self.assertEqual(missing, "")

    def test_the_run_27_reading_shape_still_reaches_the_verdict(self):
        """Guns on the rock, drones landing real damage on a rat beside it.

        The reading shape the whole incident had. The rat's damage must not
        clear the rock's tally, or the guard would have been silent for exactly
        the 290 readings it exists for.
        """
        both, = self.given_up([
            "(run 8 (List.repeat 20 [ rock 1, "
            '{ name = "Mammon Apis", hits = 3, damage = 104 } ])).namesGivenUpOn',
        ])
        self.assertEqual(both, '"Infested Asteroid"')

    def test_an_absent_channel_gives_up_on_nothing(self):
        """The fail-safe direction, and it is the opposite of the retreat's.

        A host that does not carry the game log reports no shot landing, which
        reads exactly like a ship whose guns are all missing. Absent means
        unknown, and unknown must keep shooting -- so a `Nothing` may neither
        add to the evidence nor produce a verdict.
        """
        never_seen, = self.given_up([
            "(List.foldl (\\_ m -> step 8 Nothing m) empty "
            "(List.range 1 40)).namesGivenUpOn",
        ])
        self.assertEqual(never_seen, "")

    def test_a_verdict_survives_a_reading_the_host_cannot_answer(self):
        # And the evidence short of a verdict survives it too: a host that
        # dropped the channel mid-session must not reset the count either.
        latched, = self.given_up([
            "(step 8 Nothing (run 8 (List.repeat 8 [ rock 1 ]))).namesGivenUpOn",
        ])
        self.assertEqual(latched, '"Infested Asteroid"')
        kept, = self.repl.values(
            ["(step 8 Nothing (run 8 (List.repeat 7 [ rock 1 ]))).landedHitsAtZero"],
            r"hits = (\d+)", definitions=self.DEFINITIONS)
        self.assertEqual(kept, "7")

    def test_the_verdict_is_latched_for_the_session(self):
        """Real damage afterwards does not un-latch it, deliberately.

        After giving up the bot stops shooting the object, so no later evidence
        can arrive and a rule waiting for some would wait forever. An operator
        who disagrees restarts the session, exactly as with
        `missionNamesAbandoned`.
        """
        still, = self.given_up([
            "(List.foldl (\\o m -> step 8 (Just o) m) "
            "(run 8 (List.repeat 8 [ rock 1 ])) (List.repeat 5 "
            '[ { name = "Infested Asteroid", hits = 4, damage = 400 } ]'
            ")).namesGivenUpOn",
        ])
        self.assertEqual(still, '"Infested Asteroid"')

    def test_the_setting_can_disable_it(self):
        disabled, = self.given_up([
            "(run -1 (List.repeat 40 [ rock 1 ])).namesGivenUpOn",
        ])
        self.assertEqual(disabled, "")

    def test_the_tally_list_cannot_grow_without_bound(self):
        # The names come from the client, so nothing about a pocket bounds how
        # many can appear.
        length, = self.repl.values(
            ["(run 8 (List.map (\\i -> "
             '[ { name = "Rat " ++ String.fromInt i, hits = 1, damage = 0 } ]) '
             "(List.range 1 200))).landedHitsAtZero |> List.length"],
            r"(\d+) : Int", definitions=self.DEFINITIONS)
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
            cap = int(re.search(r"^zeroDamageTalliesTracked =\n    (\d+)$",
                                handle.read(), re.MULTILINE).group(1))
        self.assertEqual(int(length), cap)

    def test_the_name_is_matched_exactly(self):
        """Exact, trimmed, case-insensitive -- never as a substring.

        A substring rule on "Infested Asteroid" would also refuse to shoot an
        "Infested Asteroid Cluster" nobody has any evidence about, and a wreck's
        Type is its owner's name with " Wreck" appended -- so a target given up
        on would take its own corpse out of the loot path with it.
        """
        exact, cluster, spaced, wreck, nothing_named = self.repl.evaluate([
            'namesMatchLabels [ "Infested Asteroid" ] [ "Infested Asteroid" ]',
            'namesMatchLabels [ "Infested Asteroid" ] [ "Infested Asteroid Cluster" ]',
            'namesMatchLabels [ "Infested Asteroid" ] [ "infested asteroid " ]',
            'namesMatchLabels [ "Infested Asteroid" ] [ "Infested Asteroid Wreck" ]',
            'namesMatchLabels [] [ "Infested Asteroid" ]',
        ])
        self.assertTrue(exact)
        self.assertFalse(cluster)
        self.assertTrue(spaced)
        self.assertFalse(wreck)
        self.assertFalse(nothing_named)


class MissionRunnerWiringTest(unittest.TestCase):
    """Where the verdict is written and who reads it.

    Structure rather than behaviour, so these read the source through a
    whitespace-collapsing reader -- #58's `elm-format` pass broke three
    assertions written against exact spacing.
    """

    def setUp(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()
        self.collapsed = " ".join(self.source.split())

    def test_the_verdict_is_written_where_memory_is_written(self):
        """A reading's summary is gone by the next one.

        `updateMemoryForNewReadingFromGame` is the only place that can write
        memory and the one place that never sees a decision, so a branch that
        read the zero and recorded nothing would see it once and go straight
        back to shooting the same object.
        """
        update = self.source.index("updateMemoryForNewReadingFromGame context botMemoryBefore =")
        body = " ".join(self.source[update:].split())
        self.assertIn(
            ", zeroDamage = updateZeroDamageMemory context botMemoryBefore.zeroDamage",
            body)

    def test_the_two_halves_of_the_channel_do_not_collide(self):
        # #32 reads `incomingDamageSinceLastReading` and this reads
        # `outgoingDamageSinceLastReading` -- different fields of the same pure
        # record, each writing its own `BotMemory` field in the one place that
        # can. The host-side hazard, one file offset and four queues, is
        # `TailFanOutTest`'s.
        update = self.source.index("updateMemoryForNewReadingFromGame context botMemoryBefore =")
        body = " ".join(self.source[update:].split())
        self.assertIn(", incomingDamage = incomingDamageNow", body)
        self.assertIn(", zeroDamage = updateZeroDamageMemory", body)

    def test_a_given_up_object_stops_being_a_target(self):
        """The subtraction sits in `shouldAttackOverviewEntry` and nowhere else.

        Three call sites ask that predicate -- the lock candidates, the
        scroll-to-reveal and `anyAttackableInOverview` -- and a rule applied to
        only the first would have the bot scrolling the overview looking for the
        object it had just given up on.
        """
        start = self.source.index("shouldAttackOverviewEntry namesToAttack overviewEntry =")
        body = " ".join(self.source[start:start + 1500].split())
        self.assertIn(
            "&& not (overviewEntryWasGivenUpAsImmune namesToAttack.givenUpAsImmune "
            "overviewEntry)", body)

    def test_the_active_target_is_unlocked_rather_than_merely_not_shot_at(self):
        """Holding fire leaves it locked, active and soaking every gun.

        Nothing here chooses which locked target EVE calls the active one, so
        declining to shoot would leave the object in the slot and reach exactly
        this branch again next reading -- which is run 27 with a different
        decision line. The unlock path is the locked-target-bar icon that
        already exists.
        """
        self.assertIn("if activeTargetGivenUpAsImmune /= Nothing then", self.collapsed)
        branch = self.source[self.source.index("if activeTargetGivenUpAsImmune"):]
        branch = " ".join(branch[:2500].split())
        self.assertIn("ctrlShiftClickUiElement", branch)
        self.assertIn("these shots are achieving nothing", branch)

    def test_the_unlock_reads_the_whole_overview(self):
        # Giving up removes the row from `overviewEntriesToAttack`, so looking
        # for the active target there would find nothing and the guns would go
        # on firing at it.
        start = self.collapsed.index("activeTargetGivenUpAsImmune =")
        body = self.collapsed[start:start + 400]
        self.assertIn("context.readingFromGameClient.overviewWindows", body)
        self.assertNotIn("overviewEntriesToAttack", body)

    def test_the_status_line_says_when_the_guard_is_unarmed(self):
        # "nothing has been given up on" reads identically whether the guns are
        # landing or nothing is listening.
        start = self.source.index("describeZeroDamage context =")
        body = self.source[start:start + 1200]
        self.assertIn("NO COMBAT LOG", body)
        # And it is actually in the status line, not merely defined: a clause
        # nothing calls is the silence it exists to replace.
        self.assertIn("[ describeZeroDamage context ]", self.collapsed)

    def test_the_setting_exists_and_is_documented(self):
        self.assertIn('( "give-up-after-zero-damage-hits"', self.collapsed)
        self.assertIn("zeroDamageHitsBeforeGivingUp = hits", self.collapsed)
        # The header section `bot_help.py` reports from.
        self.assertIn("+ `give-up-after-zero-damage-hits`", self.source)


if __name__ == "__main__":
    unittest.main()
