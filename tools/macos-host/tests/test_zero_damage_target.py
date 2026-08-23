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

# Shots of ours that did not land, in the client's own two wordings -- with the
# weapon named before "misses" and again after "completely - ", which is what
# the matcher requires to agree.
#
# Deliberately not damage, and since issue #267 deliberately not nothing either.
# A miss is carried as its own count, and the rule that reads it may only add one
# to a case a landed zero has already opened. Counting a miss as a landed hit of
# zero would build the case for immunity out of a range problem, which is the one
# way this guard could fire on a target the guns simply cannot reach.
OUTGOING_MISSES = [
    ("[ 2026.07.31 18:20:09 ] (combat) Your Hobgoblin II misses Vigilant Sentry Tower "
     "completely - Hobgoblin II", "Vigilant Sentry Tower"),
    ("[ 2026.08.03 12:11:11 ] (combat) Your group of Focused Modulated Medium Energy "
     "Beam I misses Centii Plague completely - Focused Modulated Medium Energy Beam I",
     "Centii Plague"),
]

# Misses *at* this ship. The client puts the attacker's name first and never
# writes "Your", which is the whole of what keeps these out: there are 139,578 of
# them against 19,894 of the above, so reading one as a shot of ours would build
# a case for immunity out of a rat that cannot hit us.
INCOMING_MISSES = [
    "[ 2026.08.03 04:26:55 ] (combat) Centior Misshape misses you completely",
    "[ 2026.08.03 04:26:57 ] (combat) Centus Black Ops Veteran misses you completely",
]

MISSES = [line for line, _ in OUTGOING_MISSES] + INCOMING_MISSES

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


_RECORDED_SHOTS = []


def recorded_outgoing_shots():
    """Every shot of ours the client wrote, landed or missed.

    `(path, kind, target, timestamp)` with `kind` in `{"hit", "miss"}` and the
    amount folded away, because what issue #267's measurement needs is the
    order of the two kinds against one target rather than the numbers.

    Read through the host's own two matchers rather than a third regex here, so
    what these cases measure is the shipped pattern and not a restatement of it.
    """
    if _RECORDED_SHOTS:
        return _RECORDED_SHOTS
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
                    _RECORDED_SHOTS.append(
                        (path, "hit" if dealt[0] else "zero", dealt[1],
                         entry["timestamp"]))
                    continue
                missed = botlab_host.parse_outgoing_miss(entry)
                if missed is not None:
                    _RECORDED_SHOTS.append((path, "miss", missed, entry["timestamp"]))
    if not _RECORDED_SHOTS:
        raise unittest.SkipTest(NO_GAMELOGS)
    return _RECORDED_SHOTS


def episodes_the_rule_would_have_seen(misses):
    """Every episode in the corpus, tallied under one of three readings of a miss.

    An *episode* is what `zeroDamageMemoryAfterReading` accumulates: shots at
    one target that achieved nothing, ended by that target taking any damage at
    all. Returned as `(target, shots, ever_hurt_in_this_session)`.

    Folded at the client's own second, which is finer than any real reading (one
    to eight seconds) and is therefore the fold most favourable to a zero
    standing alone -- so a separation that holds here holds at every real
    reading length. The host sums per target per reading, so a second carrying
    both a zero and a real hit on one target is handed over as damage, which
    ends the episode rather than extending it. That is issue #158's own overlap
    and is why this is folded rather than counted per line.

    `misses` is the question issue #267 had to answer, and the three answers are
    what the cases below compare:

      "ignored"   -- the rule as it shipped before #267.
      "pooled"    -- every shot counts equally, the unqualified reading of "a
                     miss should count". The cases show it has no threshold.
      "gated"     -- what shipped: a miss counts only against a target that has
                     already landed a shot for zero in this same episode.
    """
    assert misses in ("ignored", "pooled", "gated"), misses
    folded = collections.OrderedDict()
    for path, kind, target, timestamp in recorded_outgoing_shots():
        key = (path, target, timestamp)
        cell = folded.setdefault(key, {"hits": 0, "damage": 0, "misses": 0})
        if kind == "hit":
            cell["hits"] += 1
            cell["damage"] += 1
        elif kind == "zero":
            cell["hits"] += 1
        else:
            cell["misses"] += 1

    landed = collections.Counter()
    running = collections.Counter()
    hurt = collections.defaultdict(set)
    finished = []
    for (path, target, _), cell in folded.items():
        key = (path, target)
        if cell["damage"]:
            hurt[path].add(target)
            if running[key]:
                finished.append((path, target, running[key]))
            running[key] = landed[key] = 0
            continue
        landed[key] += cell["hits"]
        shots = cell["hits"]
        if misses == "pooled" or (misses == "gated" and landed[key]):
            shots += cell["misses"]
        if shots:
            running[key] += shots
    for (path, target), shots in running.items():
        if shots:
            finished.append((path, target, shots))
    return [(target, shots, target in hurt[path]) for path, target, shots in finished]


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
        # Unchanged by issue #267 and load-bearing because of it: a miss now
        # reaches the bot, and the moment it reaches it as a *hit* the two stop
        # being distinguishable and the rule downstream can be fooled by a
        # target the guns cannot reach.
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


class OutgoingMissMatchingTest(unittest.TestCase):
    """Issue #267: a shot of ours that did not land, matched at last.

    Before this the host matched a miss nowhere, so no field in any reading said
    the guns were missing and the give-up's own documentation said "a miss builds
    no case, because the host never counts one".

    The danger in reading them is the *other* direction of the same channel. The
    client writes 139,578 misses at this ship against 19,894 by it, seven to one,
    and a matcher that took either would have the bot conclude an object is
    immune because a rat keeps missing us.
    """

    def entry(self, line):
        return botlab_host.parse_game_log_line(line)

    def test_a_miss_of_ours_is_recognised_with_its_target(self):
        for line, target in OUTGOING_MISSES:
            self.assertEqual(botlab_host.parse_outgoing_miss(self.entry(line)),
                             target, line)

    def test_a_miss_at_us_is_not_a_miss_of_ours(self):
        # The seven-to-one direction, and the whole reason the pattern is
        # anchored on "Your" rather than on the word "misses".
        for line in INCOMING_MISSES:
            self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(line)), line)

    def test_a_landed_shot_is_not_a_miss(self):
        for line, _, _ in OUTGOING:
            self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(line)), line)

    def test_damage_taken_is_not_a_miss(self):
        for line in INCOMING:
            self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(line)), line)

    def test_the_weapon_must_agree_at_both_ends(self):
        """The backreference, which is what keeps the cut in the right place.

        The client names the weapon twice and the pattern requires the two to
        match, so a name carrying " misses " or " completely " cannot slide the
        split and take part of the weapon into the target. Doctored here rather
        than found, because the corpus holds no such line -- which is the point:
        the property is asserted before something writes one.
        """
        line, target = OUTGOING_MISSES[0]
        self.assertEqual(botlab_host.parse_outgoing_miss(self.entry(line)), target)
        doctored = line.replace("completely - Hobgoblin II",
                                "completely - Warrior II")
        self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(doctored)),
                          doctored)

    def test_the_other_combat_shapes_are_not_misses(self):
        for line in NOT_OUTGOING_DAMAGE:
            self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(line)), line)

    def test_other_channels_are_never_a_miss(self):
        for line in NON_COMBAT:
            self.assertIsNone(botlab_host.parse_outgoing_miss(self.entry(line)), line)

    def test_a_line_that_does_not_parse_is_not_a_miss(self):
        self.assertIsNone(botlab_host.parse_outgoing_miss(None))

    def test_the_matcher_reads_every_miss_the_client_wrote(self):
        """The corpus, as relations rather than as counts.

        Every `(combat)` line naming a miss is one of exactly two things, and
        each has to land in exactly one place: a miss of ours reaches the
        matcher, a miss at us reaches neither matcher. A line that is neither
        would be a third shape nobody has read, and there is none.
        """
        paths = sorted(glob.glob(GAMELOGS_GLOB))
        if not paths:
            self.skipTest(NO_GAMELOGS)
        ours, at_us, unread = 0, 0, []
        targets = set()
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    line = " ".join(botlab_host._GAME_LOG_MARKUP.sub("", raw).split())
                    entry = botlab_host.parse_game_log_line(line)
                    if entry is None or entry["channel"] != "combat":
                        continue
                    if " misses " not in entry["text"]:
                        continue
                    missed = botlab_host.parse_outgoing_miss(entry)
                    if missed is not None:
                        ours += 1
                        targets.add(missed)
                    elif entry["text"].endswith("misses you completely"):
                        at_us += 1
                    else:
                        unread.append(entry["text"])
        self.assertFalse(unread[:5], "a miss shape nothing reads: %r" % unread[:5])
        self.assertGreater(ours, 1000, "too few misses of ours to say anything")
        self.assertGreater(at_us, ours,
                           "misses at this ship should dwarf misses by it")
        self.assertGreater(len(targets), 50, sorted(targets)[:10])

    def test_no_target_name_is_taken_from_an_incoming_miss(self):
        """The attacker names, which must never appear as targets of ours.

        A pattern that dropped the "Your" anchor would read every one of the
        139,578 incoming misses as a shot of ours, and the tell would be the
        attacker's name arriving as a target. Asserted as the relation rather
        than by counting: the two sets are read the same way and compared.
        """
        paths = sorted(glob.glob(GAMELOGS_GLOB))
        if not paths:
            self.skipTest(NO_GAMELOGS)
        attackers = set()
        for path in paths:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for raw in handle:
                    line = " ".join(botlab_host._GAME_LOG_MARKUP.sub("", raw).split())
                    entry = botlab_host.parse_game_log_line(line)
                    if entry is None or entry["channel"] != "combat":
                        continue
                    text = entry["text"]
                    if text.endswith(" misses you completely"):
                        attackers.add(text[: -len(" misses you completely")])
                        self.assertIsNone(botlab_host.parse_outgoing_miss(entry), text)
        self.assertGreater(len(attackers), 20, sorted(attackers)[:10])


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

    def test_a_miss_of_ours_reaches_its_target_and_lands_no_hit(self):
        """Issue #267's whole host-side change, in one summary.

        This case is where the previous `test_misses_reach_no_target` was, and
        it is the pin that had to be confronted rather than deleted: the summary
        used to answer `[]` for a reading of nothing but misses, so the bot could
        not tell "nothing was shot" from "everything missed".
        """
        summary = self.summarise([line for line, _ in OUTGOING_MISSES] + NON_COMBAT)
        self.assertEqual(
            {t["name"]: (t["hits"], t["damage"], t["misses"]) for t in summary},
            {"Vigilant Sentry Tower": (0, 0, 1), "Centii Plague": (0, 0, 1)})

    def test_a_miss_at_this_ship_still_reaches_no_target(self):
        # The half that must not change: an incoming miss is not this ship
        # shooting, so it names no target of ours at all.
        self.assertEqual(self.summarise(INCOMING_MISSES + NON_COMBAT), [])

    def test_landed_shots_and_misses_are_summed_on_one_target(self):
        # Both kinds against one object in one reading, which is the shape the
        # rule reads: the tally opens on the landed zero and the miss joins it.
        summary = self.summarise([OUTGOING[3][0], OUTGOING[3][0],
                                  OUTGOING_MISSES[0][0]])
        by_name = {t["name"]: t for t in summary}
        self.assertEqual((by_name["Infested Asteroid"]["hits"],
                          by_name["Infested Asteroid"]["damage"],
                          by_name["Infested Asteroid"]["misses"]), (2, 0, 0))
        self.assertEqual((by_name["Vigilant Sentry Tower"]["hits"],
                          by_name["Vigilant Sentry Tower"]["misses"]), (0, 1))

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
        node = self.node([{"name": "Infested Asteroid", "hits": 12, "damage": 0, "misses": 0}])
        for entries in [node["dictEntriesOfInterest"]] + [
                child["dictEntriesOfInterest"] for child in node["children"]]:
            for key in ("_displayX", "_displayY", "_displayWidth", "_displayHeight"):
                self.assertNotIn(key, entries)

    def test_a_target_name_cannot_reach_getdisplaytext(self):
        # `getAllContainedDisplayTexts` runs over the raw tree with no region
        # filtering, and the mission runner asks it whether the whole reading
        # contains "No room for more". A target's name arriving in that answer
        # would be a dialog the client never showed.
        node = self.node([{"name": "No room for more", "hits": 1, "damage": 0, "misses": 0}])
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


#: `eve-online-mining-bot`'s tree was replaced with Viir's current upstream
#: (see CLAUDE.md's Architecture section), which predates this channel
#: entirely -- its `ParseUserInterface.elm` carries no
#: `outgoingDamageSinceLastReading` field at all. Excluded from
#: `VendoredParserTest` rather than assigned a shape; porting the synthetic
#: outgoing-damage node into the newer base is follow-up work, not done here.
WITHOUT_OUTGOING_DAMAGE = {"eve-online-mining-bot"}


class VendoredParserTest(unittest.TestCase):
    """`ParseUserInterface.elm` is vendored six times; the policy is all six
    that carry this channel (see `WITHOUT_OUTGOING_DAMAGE`).

    #30's check applied to the new block. A type name that disagreed across the
    two languages would have the parser answer `Nothing` -- "this host has no
    outgoing damage channel" -- on every reading, which is a guard that never
    fires and is indistinguishable from a bot with nothing to give up on.
    """

    APPS_DIR = os.path.join(REPO_DIR, "implement", "applications", "eve-online")

    def setUp(self):
        self.sources = {}
        for app in sorted(os.listdir(self.APPS_DIR)):
            if app in WITHOUT_OUTGOING_DAMAGE:
                continue
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
        self.assertEqual(len(self.sources), 5, sorted(self.sources))
        for path, source in self.sources.items():
            self.assertIn(
                "    , outgoingDamageSinceLastReading : "
                "Maybe (List OutgoingDamageToTarget)\n", source, path)
            self.assertIn(
                "    , outgoingDamageSinceLastReading = "
                "parseOutgoingDamageSinceLastReadingFromUITreeRoot uiTree\n",
                source, path)

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_field(self):
        path = os.path.join(
            self.APPS_DIR, "eve-online-mining-bot", "EveOnline",
            "ParseUserInterface.elm")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("outgoingDamageSinceLastReading", source)

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
            [{"name": "Infested Asteroid", "hits": 12, "damage": 0, "misses": 3}])
        self.assertEqual(set(node["children"][0]["dictEntriesOfInterest"]),
                         {"name", "hits", "damage", "misses"})
        for path, source in self.sources.items():
            block = self.block(source)
            for key in ("hits", "damage", "misses"):
                self.assertIn(f'getIntPropertyFromDictEntries "{key}"', block, path)
            self.assertIn('getStringPropertyFromDictEntries "name"', block, path)

    def test_a_node_cannot_be_built_without_the_miss_count(self):
        """Read strictly, so a forgotten key is an error and not a fabricated zero.

        A `.get("misses", 0)` here would have the host emit "no shots missed" for
        a caller that simply did not supply the number, which the rule downstream
        would then act on. The parser's own default is at the other end, where it
        means something true: this host predates issue #267.
        """
        with self.assertRaises(KeyError):
            botlab_host.synthetic_outgoing_damage_node(
                [{"name": "Infested Asteroid", "hits": 12, "damage": 0}])


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

    def test_counting_every_shot_equally_has_no_threshold_at_all(self):
        """Issue #267's central measurement, and the reason the rule has a gate.

        "A miss should count toward giving up" read without qualification means
        every shot counts, and the corpus says there is no number that works.
        Folded into readings and separated by the only discriminator available --
        did the guns ever hurt this target in this session -- the two
        distributions **overlap by an order of magnitude**: the objects worth
        giving up on top out where targets that were being killed are still
        being missed.

        Asserted as the relation rather than as the numbers, so a growing corpus
        cannot turn it red: the worst run of shots at a target the guns went on
        to hurt is *larger* than the largest episode worth catching, and it is
        not close. If that ever stops being true the pooled rule becomes
        arguable and somebody should be looking.
        """
        pooled = episodes_the_rule_would_have_seen("pooled")
        hurt = [shots for _, shots, was_hurt in pooled if was_hurt]
        cold = [shots for _, shots, was_hurt in pooled if not was_hurt]
        self.assertTrue(hurt and cold, "the corpus separates into nothing")
        self.assertGreater(max(hurt), max(cold),
                           "pooled: %r vs %r" % (sorted(hurt)[-5:], sorted(cold)[-5:]))
        self.assertGreater(max(hurt), 4 * max(cold),
                           "pooled: %r vs %r" % (sorted(hurt)[-5:], sorted(cold)[-5:]))

    def test_the_pooled_rule_would_fire_on_targets_the_guns_were_killing(self):
        """What that overlap costs, priced at the shipped threshold.

        Not "there is no gap" in the abstract: at eight, the pooled rule gives up
        on *dozens* of targets in this corpus that the guns went on to hurt --
        which is a permanent, name-keyed blacklist entry for each of them. The
        shipped rule fires on none, at any threshold, because the gate is not a
        threshold.
        """
        threshold = self.constant("defaultZeroDamageHitsBeforeGivingUp")
        pooled = [target for target, shots, was_hurt
                  in episodes_the_rule_would_have_seen("pooled")
                  if was_hurt and shots >= threshold]
        gated = [target for target, shots, was_hurt
                 in episodes_the_rule_would_have_seen("gated")
                 if was_hurt and shots >= threshold]
        self.assertGreater(len(pooled), 20, sorted(set(pooled))[:10])
        self.assertEqual(gated, [], sorted(set(gated))[:10])

    def test_the_gate_keeps_the_threshold_in_a_measured_gap(self):
        """Eight, re-derived against the rule as shipped rather than inherited.

        With misses counted behind the gate, the episodes worth catching are the
        same ones and two of them are a little longer -- the shortest that does
        not end on its own is still ten, and the longest that does is now seven
        rather than five. Eight is still between them, with one value of slack
        instead of three, and that narrowing is the whole cost of the change.
        """
        threshold = self.constant("defaultZeroDamageHitsBeforeGivingUp")
        gated = sorted(shots for _, shots, was_hurt
                       in episodes_the_rule_would_have_seen("gated") if not was_hurt)
        long_ones = [shots for shots in gated if shots >= 10]
        short_ones = [shots for shots in gated if shots < 10]
        self.assertTrue(long_ones, "the corpus holds no episode worth catching")
        self.assertTrue(short_ones, "the corpus holds no episode that ended on its own")
        self.assertLessEqual(threshold, min(long_ones), repr(gated))
        self.assertGreater(threshold, max(short_ones), repr(gated))

    def test_every_object_it_has_ever_fired_on_is_a_structure(self):
        """The hazard, measured rather than argued.

        The verdict latches by name and never releases, so giving up on a rat
        blacklists every rat of that name for the session -- and an anomaly is a
        pocket of identically named rats. What the corpus says is that the rule
        has never fired on one: every episode it would have caught is an
        asteroid, a gate, a wreck-like structure or a ship that is scenery, and
        those are objects whose *name* really does predict the next one.

        Asserted by the property that makes them scenery rather than by a list of
        names, which a new mission would break: every one of them is a target the
        guns landed shots on and never once hurt, in a session where they were
        hurting other things.
        """
        threshold = self.constant("defaultZeroDamageHitsBeforeGivingUp")
        caught = {target for target, shots, was_hurt
                  in episodes_the_rule_would_have_seen("gated")
                  if not was_hurt and shots >= threshold}
        self.assertTrue(caught, "nothing in this corpus reaches the threshold")
        hurt = targets_that_ever_took_damage()
        self.assertEqual(caught & hurt, set(),
                         "an object it fires on was hurt elsewhere: %r"
                         % sorted(caught & hurt))


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
        'rock n = { name = "Infested Asteroid", hits = n, damage = 0, misses = 0 }',
        # The same object, missed rather than hit. Issue #267's fixtures are
        # named for what they are evidence of rather than for what they are:
        # a rock that is hit for nothing is immune, a rat that is missed is not.
        'rockMissed n = { name = "Infested Asteroid", hits = 0, damage = 0, misses = n }',
        'rat n = { name = "Centii Loyal Enslaver", hits = 0, damage = 0, misses = n }',
        'ratHit = { name = "Centii Loyal Enslaver", hits = 1, damage = 55, misses = 0 }',
        'rockHit = { name = "Infested Asteroid", hits = 1, damage = 5, misses = 0 }',
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
            " (Just o) m in ( next, max best (List.sum (List.map zeroDamageShotsSpent"
            " next.landedHitsAtZero)) )) ( empty, 0 ) os |> Tuple.second",)
        for (path, target), summaries in sessions:
            def fold(damage_of):
                return ", ".join(
                    "[ { name = %s, hits = %d, damage = %d, misses = 0 } ]"
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
            '[ { name = "Tough Rat", hits = 1, damage = 1, misses = 0 } ])).namesGivenUpOn',
        ])
        self.assertEqual(tanked, "")

    def test_damage_partway_through_clears_the_evidence(self):
        cleared, = self.repl.values(
            ["(run 8 (List.repeat 4 [ rock 1 ] "
             '++ [ [ { name = "Infested Asteroid", hits = 1, damage = 5, misses = 0 } ] ] '
             "++ List.repeat 3 [ rock 1 ])).landedHitsAtZero"],
            r"hits = (\d+)", definitions=self.DEFINITIONS)
        self.assertEqual(cleared, "3")

    def test_a_miss_alone_never_opens_a_case(self):
        """Missing is a range problem, and giving up is not the answer to it.

        This is where `test_a_miss_builds_no_case` was, and issue #267 is the
        change it had to be confronted by rather than deleted. The host counts a
        miss now, so the reading reaching this rule carries `misses = 40` where
        it used to carry nothing at all -- and the answer has to be the same.

        A gun firing out of range misses everything, and a rule that read that
        as evidence would give up on every object it could not reach. The corpus
        says so too, at a scale nobody would guess: targets the guns went on to
        hurt absorbed 702 consecutive misses first.
        """
        verdict, = self.given_up(["(run 8 (List.repeat 40 [ rat 3 ])).namesGivenUpOn"])
        self.assertEqual(verdict, "")
        # And no tally is opened either, so 120 misses cost neither a verdict
        # nor a slot in a list `zeroDamageTalliesTracked` bounds.
        opened, = self.repl.values(
            ["List.length (run 8 (List.repeat 40 [ rat 3 ])).landedHitsAtZero"],
            r"(\d+)\s*: Int", definitions=self.DEFINITIONS)
        self.assertEqual(opened, "0")

    def test_a_miss_counts_once_a_shot_has_landed_for_zero(self):
        """The half of issue #267 that is a change rather than a refusal.

        One shot landing for zero is what opens the case; the seven misses that
        follow carry it to the threshold, where before they would have counted
        nothing and the object would have gone on being shot. Both sides of the
        boundary, so a rule that counted misses twice or not at all fails here.
        """
        fires, holds = self.given_up([
            "(run 8 ([ rock 1 ] :: List.repeat 7 [ rockMissed 1 ])).namesGivenUpOn",
            "(run 8 ([ rock 1 ] :: List.repeat 6 [ rockMissed 1 ])).namesGivenUpOn",
        ])
        self.assertEqual(fires, '"Infested Asteroid"')
        self.assertEqual(holds, "")

    def test_the_misses_counted_are_the_ones_after_the_case_opened(self):
        """The arithmetic, so an off-by-one in either component is visible.

        One landed zero and three misses is four shots spent. Three misses with
        nothing landed is zero, because there is no tally for them to join.
        """
        opened, unopened = self.repl.values(
            ["List.sum (List.map zeroDamageShotsSpent "
             "(run 8 [ [ rock 1 ], [ rockMissed 3 ] ]).landedHitsAtZero)",
             "List.sum (List.map zeroDamageShotsSpent "
             "(run 8 [ [ rockMissed 3 ] ]).landedHitsAtZero)"],
            r"(\d+)\s*: Int", definitions=self.DEFINITIONS)
        self.assertEqual(opened, "4")
        self.assertEqual(unopened, "0")

    def test_damage_shuts_the_gate_as_well_as_clearing_the_count(self):
        """One real hit ends the episode whatever it was built out of.

        The gate is "has a shot landed for zero *in this episode*", not "ever",
        so a target that reads zero once and is then hurt starts again with
        nothing -- and the forty misses that follow count for nothing, because
        there is no longer an open case for them to join. Without that clause a
        single early zero would arm an object for the rest of the session and
        every later miss would build against it, which is the slow version of
        the failure this rule refuses outright.

        The control beside it is the same forty misses with the hit removed,
        which *does* reach the verdict: so what saves the target here is the
        damage and not some other reason the fold answered nothing.
        """
        cleared, control = self.given_up([
            "(run 8 ([ rock 1 ] :: [ rockHit ] "
            ":: List.repeat 40 [ rockMissed 1 ])).namesGivenUpOn",
            "(run 8 ([ rock 1 ] "
            ":: List.repeat 40 [ rockMissed 1 ])).namesGivenUpOn",
        ])
        self.assertEqual(cleared, "")
        self.assertEqual(control, '"Infested Asteroid"')

    def test_damage_on_a_neighbour_does_not_shut_this_targets_gate(self):
        """Run 27's shape again, with misses in it.

        The drones landing real damage on a rat must not clear the rock's case,
        or the guard is silent for exactly the readings it exists for. That was
        already true of landed zeros and has to stay true now the case can be
        carried by misses.
        """
        rock, = self.given_up([
            "(run 8 ([ rock 1 ] :: [ ratHit ] "
            ":: List.repeat 7 [ rockMissed 1 ])).namesGivenUpOn",
        ])
        self.assertEqual(rock, '"Infested Asteroid"')

    def test_a_rat_that_is_merely_missed_is_never_blacklisted(self):
        """The hazard, named: the verdict latches by name and never releases.

        `namesGivenUpAsImmune` is matched against every overview row, so giving
        up on a `Centii Loyal Enslaver` refuses every one of them for the rest of
        the session -- and an anomaly is a pocket of identically named rats. A
        rule that let misses open a case would put a rat that is fast, or under a
        tracking disruptor, into that list for good.

        What stops it is the gate rather than the threshold, which is why this is
        asserted at a scale no threshold could survive: 500 readings, three
        misses each, 1,500 shots against a threshold of 8. The corpus agrees that
        this is the real shape -- every object the rule has ever fired on in the
        recordings is an asteroid, a gate or a structure, and never a rat.
        """
        blacklisted, = self.given_up([
            "(run 8 (List.repeat 500 [ rat 3 ])).namesGivenUpOn",
        ])
        self.assertEqual(blacklisted, "")

    def test_the_run_27_reading_shape_still_reaches_the_verdict(self):
        """Guns on the rock, drones landing real damage on a rat beside it.

        The reading shape the whole incident had. The rat's damage must not
        clear the rock's tally, or the guard would have been silent for exactly
        the 290 readings it exists for.
        """
        both, = self.given_up([
            "(run 8 (List.repeat 20 [ rock 1, "
            '{ name = "Mammon Apis", hits = 3, damage = 104, misses = 0 } ])).namesGivenUpOn',
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
            '[ { name = "Infested Asteroid", hits = 4, damage = 400, misses = 0 } ]'
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
             '[ { name = "Rat " ++ String.fromInt i, hits = 1, damage = 0, misses = 0 } ]) '
             "(List.range 1 200))).landedHitsAtZero |> List.length"],
            r"(\d+) : Int", definitions=self.DEFINITIONS)
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
            cap = int(re.search(r"^zeroDamageTalliesTracked =\n    (\d+)$",
                                handle.read(), re.MULTILINE).group(1))
        self.assertEqual(int(length), cap)

    def test_the_cap_drops_the_targets_with_the_least_evidence_against_them(self):
        """Which sixteen survive, when the list has to be cut.

        `zeroDamageTalliesTracked` keeps the strongest cases and drops the
        weakest, and since issue #267 the strength of a case is its shots rather
        than its landed zeros -- so an object with one landed zero and twenty
        misses outranks one with a single zero and nothing else. Ordering by the
        old measure looks right and silently throws away the case closest to
        firing.

        The object under test is put **last** in the reading, so a sort by
        landed zeros -- which are all equal here -- leaves it at the end of a
        stable order and off the end of the cut. Its seven shots are one short
        of the threshold, so what is being measured is which tally survives the
        cut rather than which name reaches the verdict: a target that had
        already fired would have left the list by the other door.
        """
        rats = ", ".join(
            '{ name = "Rat %d", hits = 1, damage = 0, misses = 0 }' % i
            for i in range(1, 20))
        loud = '{ name = "Loud Rock", hits = 1, damage = 0, misses = 6 }'
        kept, verdict = self.repl.values(
            ["(run 8 [ [ %s, %s ] ]).landedHitsAtZero "
             '|> List.map .name |> List.member "Loud Rock"' % (rats, loud),
             "(run 8 [ [ %s, %s ] ]).namesGivenUpOn |> List.isEmpty" % (rats, loud)],
            r"(True|False) : Bool", definitions=self.DEFINITIONS)
        self.assertEqual(kept, "True")
        self.assertEqual(verdict, "True", "the fixture fired instead of being kept")

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
        # The wording moved in #267 -- it can no longer say every shot landed --
        # and what this pins is that the branch still says the shots achieved
        # nothing rather than merely doing the unlock in silence.
        self.assertIn("has achieved nothing", branch)

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

    def test_the_setting_no_longer_says_a_miss_does_not_count(self):
        """The pin the change had to confront, in the text `--help` prints.

        That paragraph said "Misses do not count -- the client writes no damage
        number for one", which was true of the host rather than of the game and
        stopped being true at all with issue #267. An operator reading it would
        conclude the guard could never fire on something being missed, which is
        still the right conclusion and now for a different reason -- so the
        paragraph has to give the reason that actually holds.
        """
        start = self.source.index("+ `give-up-after-zero-damage-hits`")
        paragraph = self.source[start:start + 900]
        self.assertNotIn("Misses do not count", paragraph)
        self.assertIn("miss counts too", paragraph)
        self.assertIn("already landed a shot for zero", paragraph)

    def test_the_status_line_prints_both_halves_of_a_tally(self):
        """A sum alone cannot say which kind of evidence a case rests on.

        `8/8` reads the same whether eight shots landed for zero or one did and
        seven missed, and those are the two facts the rule is built to tell
        apart. An operator watching a run has no other instrument for it, so the
        clause carries both numbers and is executed rather than asserted by
        substring -- a clause that prints nothing satisfies a substring check on
        the branch above it, which is how #109's own status case once passed.
        """
        start = self.source.index("describeZeroDamage context =")
        body = self.source[start:start + 2000]
        self.assertIn("landed for zero", body)
        self.assertIn("missed", body)
        self.assertIn("zeroDamageShotsSpent tally", body)

    def test_the_give_up_line_does_not_claim_every_shot_landed(self):
        """The sentence an operator reads on the one reading this fires.

        It said "Every shot that has landed ... did zero damage, 8 of them",
        which stops being true the moment a miss can be one of the eight. It now
        says what is provable: at least the threshold's worth of shots achieved
        nothing, by landing for zero or missing, and shots have landed.
        """
        self.assertIn("has achieved nothing -- at least", self.collapsed)
        self.assertIn("landing for zero damage or missing outright", self.collapsed)
        # Scoped to the branch: "did zero damage" is ordinary prose elsewhere in
        # this file, and a whole-file assertion would be measuring that instead.
        start = self.collapsed.index("Every shot at '")
        self.assertNotIn("did zero damage,", self.collapsed[start:start + 600])


if __name__ == "__main__":
    unittest.main()
