"""Tests for the incoming-damage channel behind the mission runner's retreat.

Issue #32 asked for a retreat that does not depend on the ship's HUD, because
the HUD gauge is a float scraped out of live memory and is demonstrably not
reliable. The signal that replaces it is EVE's own combat log, which the host
already tails and which #30 deliberately withheld from the bot for being 96% of
all recorded lines. Withholding the *lines* was right; withholding the *total*
was not, and the host now sums it.

**Two things here can fail in the direction that looks like success**, and both
are what these cases exist for.

The first is the incoming/outgoing split. `N to X` is damage this ship dealt and
`N from X` is damage it took, they are the same shape, and a retreat armed by
the bot's own guns would fire hardest when the fight is going well. Across the
recorded logs there are 63,688 of the first and 27,063 of the second, so getting
this wrong is not a corner case.

The second is the `Nothing`-versus-zero distinction the whole channel rests on.
A host that does not carry the log reports nothing, which reads exactly like a
peaceful grid; the node's presence is what separates them, and a summary of zero
still has to produce a node.

The corpus is real: every line quoted here was written by the client during a
recorded session under `~/Documents/EVE/logs/Gamelogs`, and the aggregate counts
in the docstrings come from the 134,641 `(combat)` lines across those files.
Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Verbatim from 20260802_234531_2120724228.txt, the session the ship was lost
# in, with the client's colour and font markup already stripped the way
# `GameLogTail._poll` strips it. The two shapes differ: some weapons name
# themselves between the attacker and the quality of the hit, some do not.
INCOMING = [
    ("[ 2026.08.03 04:26:58 ] (combat) 49 from Centior Monster - Penetrates", 49, "Centior Monster"),
    ("[ 2026.08.03 04:26:59 ] (combat) 74 from Centum Fiend - Mjolnir Heavy Missile - Hits", 74, "Centum Fiend"),
    ("[ 2026.08.03 04:26:53 ] (combat) 25 from Centii Loyal Enslaver - Hits", 25, "Centii Loyal Enslaver"),
    ("[ 2026.08.03 04:26:56 ] (combat) 65 from Centum Fiend - Smashes", 65, "Centum Fiend"),
]

# Damage this ship dealt. Same shape, opposite meaning, and 63,688 of the
# recorded lines -- more than twice as many as the incoming ones.
OUTGOING = [
    "[ 2026.08.03 05:19:21 ] (combat) 51 to Blood Raider Personnel Transport - Scourge Heavy Missile - Hits",
    "[ 2026.07.31 18:20:13 ] (combat) 261 to Vigilant Sentry Tower - Scourge Heavy Missile - Hits",
]

# Incoming, and free. Counting a miss as a hit of zero would only inflate the
# hit count with nothing to show for it.
MISSES = [
    "[ 2026.08.03 04:26:55 ] (combat) Centior Misshape misses you completely",
    "[ 2026.08.03 04:26:53 ] (combat) Centior Monster misses you completely",
]

# The only `(combat)` lines carrying "from" that are not damage. There are
# exactly four of them in 134,641 recorded combat lines, and none begins with a
# digit -- which is why the matcher is anchored on the number rather than on the
# word.
WARP_DISRUPTION = [
    "[ 2026.07.30 18:22:36 ] (combat) Warp scramble attempt from Chief Republic Isak to you!",
    "[ 2026.07.30 18:22:40 ] (combat) Warp disruption attempt from Legion [HULL] [.338] [Tonz Ritc] - to Joint Harvesting Bestower",
]

# Not combat at all. These reach the bot through the game-log channel proper and
# must not be counted as damage on the way past.
NON_COMBAT = [
    "[ 2026.08.03 04:27:33 ] (notify) The ship you are piloting does not have targeting systems installed.",
    "[ 2026.08.02 23:55:23 ] (None) Jumping from Amarr to Irnin",
    "[ 2026.08.02 23:56:34 ] (bounty) 18,750 ISK added to next bounty payout",
]


def entry(line):
    return botlab_host.parse_game_log_line(line)


class IncomingDamageMatchingTest(unittest.TestCase):
    def test_damage_taken_is_recognised_with_its_attacker(self):
        for line, amount, attacker in INCOMING:
            with self.subTest(line=line):
                self.assertEqual(
                    botlab_host.parse_incoming_damage(entry(line)), (amount, attacker))

    def test_damage_dealt_is_not_damage_taken(self):
        for line in OUTGOING:
            with self.subTest(line=line):
                self.assertIsNone(botlab_host.parse_incoming_damage(entry(line)))

    def test_a_miss_is_not_a_hit(self):
        for line in MISSES:
            with self.subTest(line=line):
                self.assertIsNone(botlab_host.parse_incoming_damage(entry(line)))

    def test_warp_disruption_notices_carry_no_damage(self):
        for line in WARP_DISRUPTION:
            with self.subTest(line=line):
                self.assertIsNone(botlab_host.parse_incoming_damage(entry(line)))

    def test_other_channels_are_never_damage(self):
        for line in NON_COMBAT:
            with self.subTest(line=line):
                self.assertIsNone(botlab_host.parse_incoming_damage(entry(line)))

    def test_a_line_that_does_not_parse_is_not_damage(self):
        self.assertIsNone(botlab_host.parse_incoming_damage(None))


class TailFanOutTest(unittest.TestCase):
    """The damage queue is the tail's third reader of one file offset.

    #30's bug was one cursor with two readers, where whichever drained first
    took that cycle's lines and the other got nothing -- intermittently and
    without a word. A third reader is the same hazard again, so the same
    property is asserted: each queue sees every line exactly once, in either
    drain order.
    """

    def make_tail(self, tmpdir, lines):
        path = os.path.join(tmpdir, "20260803_000000_1.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("header\n")
        tail = botlab_host.GameLogTail(tmpdir)
        tail._poll()  # first sight of a file starts at its end
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return tail

    def test_damage_and_entries_do_not_eat_each_other(self):
        lines = [INCOMING[0][0], NON_COMBAT[0], INCOMING[1][0]]
        for drain_damage_first in (True, False):
            with self.subTest(drain_damage_first=drain_damage_first):
                with tempfile.TemporaryDirectory() as tmpdir:
                    tail = self.make_tail(tmpdir, lines)
                    if drain_damage_first:
                        damage = tail.incoming_damage_for_reading()
                        entries = tail.entries_for_reading()
                    else:
                        entries = tail.entries_for_reading()
                        damage = tail.incoming_damage_for_reading()
                    self.assertEqual(damage["damage"], INCOMING[0][1] + INCOMING[1][1])
                    self.assertEqual(damage["hits"], 2)
                    # The `(notify)` line is the only one the bot's game-log
                    # channel carries; the two combat lines stay withheld from
                    # it, exactly as before this change.
                    self.assertEqual([e["text"] for e in entries],
                                     ["The ship you are piloting does not have "
                                      "targeting systems installed."])

    def test_the_echo_still_sees_every_line(self):
        lines = [INCOMING[0][0], OUTGOING[0], NON_COMBAT[1]]
        with tempfile.TemporaryDirectory() as tmpdir:
            tail = self.make_tail(tmpdir, lines)
            tail.incoming_damage_for_reading()
            self.assertEqual(len(tail.lines_for_echo()), 3)

    def test_damage_is_scoped_to_the_reading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tail = self.make_tail(tmpdir, [INCOMING[0][0]])
            self.assertEqual(tail.incoming_damage_for_reading()["damage"], INCOMING[0][1])
            # Gone by the next reading, like every other part of this channel.
            self.assertEqual(tail.incoming_damage_for_reading()["damage"], 0)


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
            return tail.incoming_damage_for_reading()

    def test_the_top_attacker_is_the_one_that_did_the_most(self):
        # Centum Fiend lands 74 + 65; Centior Monster lands 49, twice. The
        # heaviest hitter is not the most frequent one, and the decision log
        # wants the heaviest.
        summary = self.summarise([INCOMING[1][0], INCOMING[3][0],
                                  INCOMING[0][0], INCOMING[0][0]])
        self.assertEqual(summary["topAttacker"], "Centum Fiend")
        self.assertEqual(summary["damage"], 74 + 65 + 49 + 49)
        self.assertEqual(summary["hits"], 4)

    def test_a_quiet_reading_summarises_to_zero_rather_than_to_nothing(self):
        summary = self.summarise(MISSES + NON_COMBAT)
        self.assertEqual(summary, {"damage": 0, "hits": 0, "topAttacker": None})


class SyntheticNodeTest(unittest.TestCase):
    def test_the_node_carries_no_display_region(self):
        # The property that keeps a fiction safe in a structure that otherwise
        # mirrors real memory: with no region, every parser in
        # ParseUserInterface.elm navigates straight past it.
        node = botlab_host.synthetic_incoming_damage_node(
            {"damage": 120, "hits": 3, "topAttacker": "Centum Fiend"})
        for key in ("_displayX", "_displayY", "_displayWidth", "_displayHeight"):
            self.assertNotIn(key, node["dictEntriesOfInterest"])

    def test_the_attacker_name_cannot_reach_getdisplaytext(self):
        # `getAllContainedDisplayTexts` runs over the raw tree with no region
        # filtering, and the mission runner asks it whether the whole reading
        # contains "No room for more". A rat's name arriving in that answer
        # would be a dialog the client never showed.
        node = botlab_host.synthetic_incoming_damage_node(
            {"damage": 1, "hits": 1, "topAttacker": "No room for more"})
        for key in ("_setText", "_text"):
            self.assertNotIn(key, node["dictEntriesOfInterest"])

    def test_a_quiet_reading_still_produces_a_node(self):
        # Zero is an answer. The node's *absence* is the other answer -- this
        # host does not carry the channel -- and collapsing the two is how a
        # bot concludes it is safe because nothing is listening.
        node = botlab_host.synthetic_incoming_damage_node(
            {"damage": 0, "hits": 0, "topAttacker": None})
        self.assertEqual(node["dictEntriesOfInterest"], {"damage": 0, "hits": 0})
        self.assertEqual(node["pythonObjectTypeName"],
                         botlab_host.SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME)

    def test_the_type_name_says_it_is_a_fiction(self):
        self.assertIn("MacOsHost", botlab_host.SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME)
        self.assertNotEqual(botlab_host.SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME,
                            botlab_host.SYNTHETIC_GAME_LOG_TYPE_NAME)


class VendoredParserTest(unittest.TestCase):
    """`ParseUserInterface.elm` is vendored six times; the policy is all six.

    Same check #30 put on the game-log block, for the same reason: a change that
    lands in one copy and silently not the others is its own bug, and the strings
    the host and the parser have to agree on across two languages cost nothing at
    compile time and everything at runtime. A type name that disagreed would have
    the parser answer `Nothing` -- "this host has no damage channel" -- on every
    reading, which is precisely the failure that reads like a quiet grid.
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
        start = source.index("{-| How much damage the client's own combat log")
        end = source.index("getIntPropertyFromDictEntries dictEntryKey node =")
        return source[start:source.index("\n\n\n", end)]

    def test_every_copy_has_it(self):
        self.assertEqual(len(self.sources), 6, sorted(self.sources))
        for path, source in self.sources.items():
            self.assertIn("    , incomingDamageSinceLastReading : Maybe IncomingDamage\n",
                          source, path)
            self.assertIn(
                "    , incomingDamageSinceLastReading = "
                "parseIncomingDamageSinceLastReadingFromUITreeRoot uiTree\n",
                source, path)

    def test_every_copy_has_the_same_one(self):
        blocks = {path: self.block(source) for path, source in self.sources.items()}
        reference = blocks[sorted(blocks)[0]]
        for path, block in blocks.items():
            self.assertEqual(block, reference, path)

    def test_the_parser_looks_for_the_type_name_the_host_emits(self):
        for path, source in self.sources.items():
            self.assertIn(f'    "{botlab_host.SYNTHETIC_INCOMING_DAMAGE_TYPE_NAME}"\n',
                          source, path)

    def test_the_parser_reads_the_keys_the_host_writes(self):
        node = botlab_host.synthetic_incoming_damage_node(
            {"damage": 7, "hits": 1, "topAttacker": "Centum Fiend"})
        self.assertEqual(set(node["dictEntriesOfInterest"]),
                         {"damage", "hits", "topAttacker"})
        for path, source in self.sources.items():
            for key in ("damage", "hits"):
                self.assertIn(f'getIntPropertyFromDictEntries "{key}"', source, path)
            self.assertIn('getStringPropertyFromDictEntries "topAttacker"', source, path)


class MissionRunnerGuardTest(unittest.TestCase):
    """The Elm side's constants, pinned to what the recorded data supports.

    These read the numbers out of `Bot.elm` rather than restating them, the same
    coupling `test_ammo_load_refusal` uses on the refusal's wording. A threshold
    quietly edited to a value the evidence does not support is the kind of change
    that never fails until a ship is lost.
    """

    def setUp(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()

    def constant(self, name):
        match = re.search(rf"^{name} =\n    (-?\d+)$", self.source, re.MULTILINE)
        self.assertIsNotNone(match, f"{name} not found in Bot.elm")
        return int(match.group(1))

    def test_the_damage_threshold_separates_the_loss_from_every_survival(self):
        # Peak incoming damage in any 45-second window, measured from the
        # client's own timestamps across sixteen recorded sessions: the worst a
        # session the ship survived reached was 3114, and the session it was
        # lost in peaked at 4101.
        threshold = self.constant("defaultRunAwayIncomingDamageThreshold")
        self.assertGreater(threshold, 3114)
        self.assertLess(threshold, 4101)

    def test_the_frozen_reading_threshold_clears_the_benign_cases(self):
        # The most damage absorbed while the `(shield, armor)` pair stayed
        # frozen, in the three recorded runs whose gauge was live, was 595
        # hitpoints over 21 seconds. A guard that fired at or below that would
        # fire on a healthy ship taking light fire.
        self.assertGreater(self.constant("damageThatMustMoveTheHitpointsReading"), 595)

    def test_the_frozen_reading_guard_is_the_more_sensitive_of_the_two(self):
        # A ship that cannot see what is happening to it gets less rope than one
        # that can.
        self.assertLess(self.constant("damageThatMustMoveTheHitpointsReading"),
                        self.constant("defaultRunAwayIncomingDamageThreshold"))

    def test_the_window_is_the_one_the_thresholds_were_measured_over(self):
        self.assertEqual(self.constant("incomingDamageWindowSeconds"), 45)

    def test_a_lost_ship_outranks_the_retreat(self):
        """#33's pod recovery must win over #32's retreat, by placement.

        A retreat manoeuvre is something a ship does. Once the ship is gone the
        right response is to fly the pod home and end the session, not to warp a
        capsule between celestials forever -- and a capsule being shot is exactly
        the state that arms the damage guard, so the two really can both want to
        act on the same reading.

        Nothing in `runAwayIfLowHealth` enforces this; the decision tree's shape
        does. `recoverPodAfterShipLoss` sits in the pre-split list and answers
        `Just` on every reading the verdict exists, so the docked-or-in-space
        split -- which is the only caller of `runAwayIfLowHealth` -- is
        unreachable after the verdict latches. That is exactly the kind of
        invariant a later edit can invert while everything still compiles, which
        is issue #12's failure, so it is pinned here rather than remembered.
        """
        root = self.source.index("missionBotDecisionRootBeforeApplyingSettings context =")
        end = self.source.index("\nsecondsBeforeSessionEndToWindDown", root)
        body = self.source[root:end]

        pod = body.index(", recoverPodAfterShipLoss context")
        split = body.index("branchDependingOnDockedOrInSpace")
        retreat = body.index("runAwayIfLowHealth context shipUI")
        self.assertLess(pod, split, "pod recovery must be decided before the split")
        self.assertLess(split, retreat, "the retreat must live under the split")

        # And the short-circuit is unconditional: a `Maybe.map` over the latched
        # verdict, so there is no reading where the verdict exists and the
        # branch declines to take it.
        recovery = self.source.index("recoverPodAfterShipLoss context =\n")
        head = self.source[recovery:recovery + 200]
        self.assertIn("context.memory.shipLoss\n        |> Maybe.map", head)

    def test_the_two_game_log_readers_do_not_collide(self):
        """Both changes read the channel, and neither consumes it.

        #33 reads `gameLogEntriesSinceLastReading` and #32 reads
        `incomingDamageSinceLastReading` -- different fields of the same pure
        record, so reading one cannot hide the other. The hazard this guards
        against is the host-side one, where the two really do share a file
        offset; that is covered by `TailFanOutTest`. Here it is enough to assert
        both verdicts are still written, in the one place that can write memory.

        The window is computed into `incomingDamageNow` rather than inline since
        #50, because the ammo swap reads it too and has to read *this* reading's
        value: the reading fire first arrives on is exactly the reading a swap
        must not begin on. One binding, two readers, still one writer.
        """
        update = self.source.index("updateMemoryForNewReadingFromGame context botMemoryBefore =")
        body = self.source[update:]
        self.assertIn(
            "        incomingDamageNow =\n"
            "            updateIncomingDamageMemory context botMemoryBefore.incomingDamage",
            body)
        self.assertIn("    , incomingDamage = incomingDamageNow", body)
        self.assertIn("    , shipLoss =", body)

    def test_the_launcher_always_ships_at_least_one_armed_guard(self):
        """At least one retreat guard must be armed, whichever suits the hull.

        This used to assert the *shield* guard specifically was above zero, on
        the reasoning in #32 that the hull is shield-tanked and armour therefore
        cannot move until the tank is gone. That had the hull backwards: it is
        armour-tanked, its shield rests at 0 by design, and a shield threshold
        fires on the ship's normal condition -- run 10 raised the retreat 142
        times in one session before it was corrected live.

        So which guard is armed depends on the fit and cannot be asserted. What
        can be asserted is the thing #32 was really about: the launcher must not
        ship a set where every guard is disabled, which is what left run 7 with
        nothing watching. The damage guard needs no gauge at all, so it is the
        one that holds regardless of tank.
        """
        with open(os.path.join(MACOS_HOST_DIR, "run_mission.sh"),
                  encoding="utf-8") as handle:
            launcher = handle.read()

        def threshold(name):
            # The trailing "? matters: these live inside the quoted SETTINGS
            # block, so whichever key happens to be last carries the closing
            # quote and an end-anchored pattern silently misses it.
            match = re.search(rf'^run-away-{name}=(-?\d+)"?$', launcher, re.MULTILINE)
            self.assertIsNotNone(match, f"{name} missing from the launcher defaults")
            return int(match.group(1))

        guards = {
            "shield": threshold("shield-hitpoints-threshold-percent"),
            "armor": threshold("armor-hitpoints-threshold-percent"),
            "damage": threshold("incoming-damage-threshold"),
        }
        armed = {name: value for name, value in guards.items() if value > 0}
        self.assertTrue(armed, f"every retreat guard is disabled: {guards}")

        # The damage guard is the gauge-free one, and the only failure run 7
        # could not have been saved from is the one where nothing watches at all.
        self.assertGreater(guards["damage"], 0,
                           "the damage guard should stay armed whatever the tank is")


if __name__ == "__main__":
    unittest.main()
