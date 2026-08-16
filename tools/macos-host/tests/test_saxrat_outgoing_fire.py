"""saxrat reads what its own guns achieved, and decides nothing on it.

Issue: *"if we see lots of missed shots from us, we swap ammo and/or manoeuvre
class"*. PR #271 made a miss reach the bot for the first time -- `misses` sits
beside `hits` on `OutgoingDamageToTarget` in all six vendored parser copies --
so the signal is available with no host or parser work.

**What ships is the instrument and not the trigger, and the corpus is the
reason.** The rule the issue asks for has no threshold: measured against the
client's own statement that a rat died, a fight that misses almost every shot is
indistinguishable from one that is being won, and the fights that miss most are
the ones that are *winning*. Those measurements are recomputed here as
relations, per session, so a corpus that grows cannot turn a true claim red --
and if they ever stop holding, this file is what goes red and the threshold
becomes writable.

Three groups of case:

  - the rule, executed through the real `Bot.elm` in `elm repl` against readings
    built by the real `EveOnline.ParseUserInterface`, so the synthetic node the
    host emits is parsed rather than restated;
  - the measurement, recomputed from `~/Documents/EVE/logs/Gamelogs` through the
    host's own two matchers rather than a third regex here;
  - the boundary: no decision reads the field, and neither manoeuvre verb nor
    the ammo swap gained a caller.

Nothing here reads a live game client or drives a bot. The corpus cases skip
with a stated reason on a machine that has no client logs, and they glob the
sessions rather than naming them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
import datetime
import glob
import os
import re
import sys
import unittest

from prerequisites import MACOS_HOST_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

sys.path.insert(0, MACOS_HOST_DIR)
from botlab_host import botlab_host  # noqa: E402

GAMELOGS_GLOB = os.path.join(
    os.path.expanduser("~"), "Documents", "EVE", "logs", "Gamelogs", "*.txt")

# The wording the rest of the suite uses for this prerequisite, so
# `check_expected_skips.py` covers it under the entry it already has rather than
# needing a new one. A skip nobody has classified is one CI refuses.
NO_GAMELOGS = "no recorded game logs in ~/Documents/EVE/logs/Gamelogs"

# The bounty channel is the only thing in this corpus that states a rat died.
# The bot is deliberately not given these lines (CLAUDE.md, Architecture), which
# is exactly why they can serve as an independent kill signal here.
KILL_MARKER = "added to next bounty payout"

# A stretch has to carry real shooting before its miss share means anything: two
# shots that both missed are 100% and say nothing. The fixed-window cut below
# uses a lower floor of its own, deliberately, since its buckets are shorter.
SHOT_FLOOR = 20


def outgoing_damage_node(targets):
    """The host's third synthetic node, exactly as `botlab_host.py` emits it.

    Built through the host's own emitter rather than written out here, so a
    fixture cannot drift from what the bot is really handed -- and so the
    `misses` key it reads strictly is the one under test.
    """
    return botlab_host.synthetic_outgoing_damage_node(targets)


def target(name, hits=0, damage=0, misses=0):
    return {"name": name, "hits": hits, "damage": damage, "misses": misses}


def source():
    return source_of(SAXRAT_BOT_ELM)


def without_comments(text):
    """The same source with its doc comments and `--` lines dropped.

    Every case asserting a name is read *nowhere* needs this: this change
    discusses misses at length in prose, so a count over the raw text cannot
    tell a mention from a use.
    """
    text = re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL)
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("--"))


# --------------------------------------------------------------------------
# the corpus, read once for the process


_SHOTS = []


def recorded_shots():
    """Every shot of ours and every kill, `(session, kind, second)`.

    Read through the host's own two matchers rather than a third regex here, so
    what these cases measure is the shipped pattern and not a restatement of it.
    Cached for the process: the corpus is 189 files and several cases fold it
    more than one way.
    """
    if _SHOTS:
        return _SHOTS
    paths = sorted(glob.glob(GAMELOGS_GLOB))
    if not paths:
        raise unittest.SkipTest(NO_GAMELOGS)
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = " ".join(botlab_host._GAME_LOG_MARKUP.sub("", raw).split())
                entry = botlab_host.parse_game_log_line(line)
                if entry is None:
                    continue
                when = datetime.datetime.strptime(
                    entry["timestamp"], "%Y.%m.%d %H:%M:%S").timestamp()
                if entry["channel"] == "bounty" and KILL_MARKER in entry["text"]:
                    _SHOTS.append((path, "kill", int(when)))
                    continue
                if botlab_host.parse_outgoing_damage(entry) is not None:
                    _SHOTS.append((path, "hit", int(when)))
                elif botlab_host.parse_outgoing_miss(entry) is not None:
                    _SHOTS.append((path, "miss", int(when)))
    if not _SHOTS:
        raise unittest.SkipTest(NO_GAMELOGS)
    return _SHOTS


def per_session():
    """`{session: (hits, misses, kills)}`, each a `Counter` keyed by second."""
    sessions = collections.defaultdict(
        lambda: (collections.Counter(), collections.Counter(), collections.Counter()))
    for path, kind, second in recorded_shots():
        hits, misses, kills = sessions[path]
        {"hit": hits, "miss": misses, "kill": kills}[kind][second] += 1
    return {path: value for path, value in sessions.items()
            if value[0] or value[1]}


def kill_free_intervals():
    """Every stretch of fighting between two kills, scored by its miss share.

    Cut at each `(bounty)` line rather than into fixed windows, because a fixed
    window puts a kill in one bucket and the fire that earned it in the one
    before -- which is what made an earlier pass of this measurement report a
    gap that moved with the window length.

    `ends_in_kill` is the discriminator the issue asks for: an interval that
    ends in a kill is a fight that was slow and then got somewhere, and one that
    ends because the session ran out is a fight that never did.
    """
    intervals = []
    for path, (hits, misses, kills) in per_session().items():
        firing = sorted(set(hits) | set(misses))
        if not firing:
            continue
        cuts = sorted(s for s in kills if firing[0] <= s <= firing[-1])
        edges = [firing[0]] + cuts + [firing[-1] + 1]
        for start, end in zip(edges, edges[1:]):
            fired = [s for s in firing if start <= s < end]
            if not fired:
                continue
            landed = sum(hits[s] for s in fired)
            missed = sum(misses[s] for s in fired)
            if landed + missed < SHOT_FLOOR:
                continue
            intervals.append({
                "share": 100.0 * missed / (landed + missed),
                "shots": landed + missed,
                "seconds": len(fired),
                "ends_in_kill": end in kills,
                "path": path,
            })
    return intervals


def windows(length):
    """Fixed windows of `length` seconds, each `(miss share, a rat died)`.

    The cruder cut, kept because it is the one that reads most naturally as "a
    miss rate", and because the direction it reports is the finding: the windows
    that killed something miss *more*.
    """
    scored = []
    for path, (hits, misses, kills) in per_session().items():
        firing = sorted(set(hits) | set(misses))
        if not firing:
            continue
        at = firing[0]
        while at <= firing[-1]:
            landed = sum(hits[s] for s in range(at, at + length))
            missed = sum(misses[s] for s in range(at, at + length))
            killed = sum(kills[s] for s in range(at, at + length))
            if landed + missed >= 10:
                scored.append((100.0 * missed / (landed + missed), bool(killed)))
            at += length
    return scored


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else float("nan")


# --------------------------------------------------------------------------


class TheRuleTest(unittest.TestCase):
    """`outgoingFireAfterReading`, executed against really parsed readings.

    The node the fixtures carry is built by the host's own emitter and decoded
    by the real `EveOnline.ParseUserInterface`, so what is asserted here is what
    the bot would have been handed rather than a record shaped by hand.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def definitions_for(self, readings):
        """A `folded` binding: `readings` run through the real rule in order.

        Each reading is `None` for a host that carries no channel, or a list of
        `(name, hits, damage, misses)`. Folded rather than asked once, because a
        run counter that is right for one reading and wrong across a session is
        the defect this shape exists to prevent.
        """
        definitions = ["start = { hostCarriesTheChannel = False, hits = 0,"
                       " misses = 0, readingsEveryShotMissed = 0,"
                       " longestRunEveryShotMissed = 0, sessionHits = 0,"
                       " sessionMisses = 0 }"]
        names = []
        for index, reading in enumerate(readings):
            name = "reading%d" % index
            children = [] if reading is None else [outgoing_damage_node(
                [target(*row) for row in reading])]
            definitions.append(SaxratRepl.reading_binding(name, children))
            names.append(name)
        summaries = " , ".join(
            "%s |> Maybe.andThen .outgoingDamageSinceLastReading" % name
            for name in names)
        definitions.append(
            "folded = List.foldl (\\s m -> Bot.outgoingFireAfterReading"
            " { before = m, summaries = s }) start [ %s ]" % summaries)
        return definitions

    def fold(self, readings, field):
        """An `Int` field of the memory after the fold."""
        return int(self.repl.values(
            ["folded.%s" % field], r"(-?\d+) : Int",
            definitions=self.definitions_for(readings))[0])

    def fold_bool(self, readings, field):
        return self.repl.evaluate(
            ["folded.%s" % field], definitions=self.definitions_for(readings))[0]

    def test_a_landed_shot_and_a_miss_are_counted_apart(self):
        """The one mistake the parser's doc comment names: never summed."""
        self.assertEqual(self.fold([[("Centii Plague", 3, 90, 2)]], "hits"), 3)
        self.assertEqual(self.fold([[("Centii Plague", 3, 90, 2)]], "misses"), 2)

    def test_a_reading_where_every_shot_missed_advances_the_run(self):
        self.assertEqual(
            self.fold([[("Centii Plague", 0, 0, 4)]] * 3,
                      "readingsEveryShotMissed"), 3)

    def test_a_landed_shot_clears_the_run_even_at_zero_damage(self):
        """A shot that lands and achieves nothing is #90's failure, not this one.

        The run is about the guns being unable to *hit*. A landed zero says they
        cannot hurt the object, which is a different fact with its own rule, so
        it ends this run rather than extending it.
        """
        self.assertEqual(
            self.fold([[("Infested Asteroid", 0, 0, 4)]] * 5
                      + [[("Infested Asteroid", 1, 0, 0)]],
                      "readingsEveryShotMissed"), 0)

    def test_a_reading_with_no_shot_in_it_holds_the_run(self):
        """`gateWithinReachTicks`' hold, for its reason.

        A reload, a target dying or a menu cascade all produce readings a firing
        ship put no shot into, and resetting on one is the shape that pinned
        `gunsSilencedTicks` at 1 forever.
        """
        self.assertEqual(
            self.fold([[("Centii Plague", 0, 0, 4)]] * 3 + [[]]
                      + [[("Centii Plague", 0, 0, 4)]],
                      "readingsEveryShotMissed"), 4)

    def test_a_host_with_no_channel_holds_the_run_and_says_so(self):
        """Absent is not quiet, which is this repo's standing rule.

        `Nothing` from the parser is "this host has no game log" and `Just []`
        is "the client reported no shot". Both leave the counts at zero and only
        the first may ever be read as not knowing.
        """
        readings = [[("Centii Plague", 0, 0, 4)]] * 3 + [None]
        self.assertEqual(self.fold(readings, "readingsEveryShotMissed"), 3)
        self.assertFalse(self.fold_bool(readings, "hostCarriesTheChannel"))
        self.assertTrue(self.fold_bool([[]], "hostCarriesTheChannel"))

    def test_the_worst_run_is_kept_once_the_run_itself_has_gone(self):
        self.assertEqual(
            self.fold([[("Centii Plague", 0, 0, 1)]] * 6
                      + [[("Centii Plague", 2, 40, 0)]]
                      + [[("Centii Plague", 0, 0, 1)]],
                      "longestRunEveryShotMissed"), 6)
        self.assertEqual(
            self.fold([[("Centii Plague", 0, 0, 1)]] * 6
                      + [[("Centii Plague", 2, 40, 0)]]
                      + [[("Centii Plague", 0, 0, 1)]],
                      "readingsEveryShotMissed"), 1)

    def test_the_session_totals_accumulate_across_targets(self):
        self.assertEqual(
            self.fold([[("Centii Plague", 2, 40, 1), ("Centii Minion", 1, 10, 3)],
                       [("Centii Plague", 0, 0, 2)]], "sessionHits"), 3)
        self.assertEqual(
            self.fold([[("Centii Plague", 2, 40, 1), ("Centii Minion", 1, 10, 3)],
                       [("Centii Plague", 0, 0, 2)]], "sessionMisses"), 6)

    def test_a_reading_that_missed_one_target_and_hit_another_is_not_a_miss_run(self):
        """The signal is the ship's fire, not one row's.

        A reading in which the guns hit a rat while a drone missed a second is a
        reading the guns landed a shot on, and treating it as an all-miss
        reading is how a ship-wide counter would run up during an ordinary
        fight.
        """
        self.assertEqual(
            self.fold([[("Centii Plague", 3, 60, 0), ("Hunter Alvi", 0, 0, 5)]] * 4,
                      "readingsEveryShotMissed"), 0)


class TheHazardTest(unittest.TestCase):
    """A fight that is merely slow is never interrupted.

    The 702-consecutive-miss hazard the parser's doc comment records, at a scale
    no threshold could survive -- and the assertion is not that some threshold
    was cleared but that **nothing acts**, because nothing reads the field.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_thousand_readings_of_pure_misses_change_no_verdict(self):
        """The instrument counts to a thousand and the fight is untouched.

        `combatStalemateVerdict` is the only thing on this path that can decide
        to break off, and it is a function of its own reading count. Folding a
        thousand all-miss readings through the fire rule leaves that count where
        it was, because the two do not share an input -- which is what "nothing
        decides on this" means operationally rather than as a claim about
        occurrences.
        """
        definitions = [
            "start = { hostCarriesTheChannel = False, hits = 0, misses = 0,"
            " readingsEveryShotMissed = 0, longestRunEveryShotMissed = 0,"
            " sessionHits = 0, sessionMisses = 0 }",
            SaxratRepl.reading_binding("missed", [outgoing_damage_node(
                [target("Hunter Alvi", hits=0, damage=0, misses=1)])]),
            "summary = missed |> Maybe.andThen .outgoingDamageSinceLastReading",
            "folded = List.foldl (\\_ m -> Bot.outgoingFireAfterReading"
            " { before = m, summaries = summary }) start (List.range 1 1000)",
        ]
        counted = self.repl.values(
            ["folded.readingsEveryShotMissed"], r"(-?\d+) : Int",
            definitions=definitions)
        self.assertEqual(counted[0], "1000")
        # A thousand readings of nothing but misses, and the fight is still the
        # fight: the stalemate rule answers on its own count and never sees this.
        verdicts = self.repl.evaluate(
            ["Bot.combatStalemateVerdict 0 == Bot.FightIsStillGettingSomewhere",
             "Bot.combatStalemateVerdict 199 == Bot.FightIsStillGettingSomewhere",
             "Bot.combatStalemateVerdict 200 == Bot.CloseTheRangeOnTheTarget"],
            definitions=definitions)
        self.assertEqual(verdicts, [True, True, True])

    def test_the_status_clause_says_nothing_decides_on_it(self):
        rendered = self.repl.strings([
            "Bot.describeOutgoingFire { hostCarriesTheChannel = True, hits = 0,"
            " misses = 3, readingsEveryShotMissed = 702,"
            " longestRunEveryShotMissed = 702, sessionHits = 15,"
            " sessionMisses = 702 }",
            "Bot.describeOutgoingFire { hostCarriesTheChannel = False, hits = 0,"
            " misses = 0, readingsEveryShotMissed = 0,"
            " longestRunEveryShotMissed = 0, sessionHits = 0, sessionMisses = 0 }",
        ])
        self.assertIn("702", rendered[0])
        self.assertIn("Nothing decides on this", rendered[0])
        # An absent channel says so in words rather than printing zeros that
        # read exactly like a ship whose every shot landed.
        self.assertIn("NO COMBAT LOG", rendered[1])
        self.assertNotIn("missed this reading", rendered[1])


class NothingDecidesOnItTest(unittest.TestCase):
    """The boundary, read out of the source.

    This is the case that goes red the day somebody wires a rule to the signal
    -- which is the point at which the measurement below has to be argued
    against rather than drifted past.
    """

    def test_the_field_is_read_by_the_memory_update_and_the_status_line_only(self):
        code = without_comments(source())
        readers = [line.strip() for line in code.splitlines()
                   if "outgoingFire" in line]
        # The field, its init, the memory update that writes it, and the status
        # line that prints it. Anything else is a decision starting to read it.
        self.assertTrue(readers, "the field is not in the source at all")
        allowed = (
            ", outgoingFire :",                      # the field
            ", outgoingFire =",                      # its init, and the update
            "{ before = botMemoryBefore.outgoingFire",   # what the update folds
            "outgoingFireAfterReading",              # the rule itself
            "describeOutgoingFire",                  # the clause
        )
        for line in readers:
            self.assertTrue(
                any(fragment in line for fragment in allowed),
                "an unexpected reader of the fire memory: %r" % line)
        # And exactly one place renders it, which is the status line.
        self.assertEqual(
            len([line for line in readers
                 if "describeOutgoingFire context.memory.outgoingFire" in line]),
            1, "the clause is printed somewhere other than the status line")

    def test_the_rule_reaches_for_nothing_but_its_own_two_inputs(self):
        """It takes a record and a summary and cannot see the fight.

        A rule that reached into `BotDecisionContext` could come to depend on
        the target, the range or the gauge, and would stop being executable
        through `elm repl` -- which is #106's recorded cost and the reason every
        rule this file asserts on is a function of records.
        """
        body = collapsed(body_of(source(), "outgoingFireAfterReading"))
        for forbidden in ("context", "botSettings", "memory.", "shipUI",
                          "readingFromGameClient", "combatStalemate"):
            self.assertNotIn(
                forbidden, body,
                "the rule reaches for %r, so it is no longer a pure fold"
                % forbidden)

    def test_neither_manoeuvre_verb_gained_a_caller(self):
        """The two key-wrapped clicks are not fired more often than before.

        `ensureShipIsKeepingRange` holds `vkey_E` and `ensureShipIsOrbiting`
        holds `vkey_W` over a click. PR #243 removed the third such chord
        (`vkey_Q` on approach) because a posted key inherits the session's
        modifiers, and with the Fn bit set the bot pressed macOS Quick Note at
        itself 241 times in one run. Anything that changes manoeuvre class more
        often makes those fire more often, so this change may not widen their
        use -- and does not.
        """
        code = without_comments(source())
        for verb in ("ensureShipIsOrbiting", "ensureShipIsKeepingRange"):
            # The token itself, never the `…Decision` binding that wraps it,
            # and never its own annotation or definition head.
            uses = re.findall(r"\b%s\b(?!Decision)" % verb, code)
            self.assertEqual(
                len(uses), 3,
                "%s appears %d times rather than the annotation, the "
                "definition and one call -- this change widened a key-wrapped "
                "click" % (verb, len(uses)))
        # And the chords themselves are still pressed in exactly those two
        # places: `vkey_E` once, `vkey_W` once beyond the loot window's Ctrl+W.
        self.assertEqual(len(re.findall(r"\bvkey_E\b", code)), 2, "vkey_E moved")

    def test_the_ammo_swap_still_decides_on_the_target_distance_alone(self):
        """The wanted charge gained no second source.

        `rangeVerdict` is a pure function of the active target's distance and
        the configured crossover. A miss-driven swap would have to give it a
        second input, and the swap is not an actuator to feed while it abandons
        the attempts it already starts -- see this file's own docstring and the
        pull request.
        """
        update = collapsed(body_of(source(), "updateAmmoSwapMemoryWithConfig"))
        verdict = update[update.index("rangeVerdict ="):]
        verdict = verdict[:verdict.index("rangeVerdictTicks")]
        self.assertIn("activeTargetDistanceInMeters", verdict)
        for forbidden in ("misses", "outgoingFire", "outgoingDamage"):
            self.assertNotIn(
                forbidden, verdict,
                "the wanted charge now reads %r, which the corpus does not "
                "support a threshold for" % forbidden)


class TheCorpusHasNoThresholdTest(unittest.TestCase):
    """The measurement the change rests on, recomputed as relations.

    Every claim here is a *relation* rather than one of the numbers in the pull
    request, so a corpus that goes on growing cannot turn a true claim red. If
    one of these ever fails, the finding has changed and the trigger the issue
    asks for has become writable -- which is the outcome this file exists to
    make visible.
    """

    def test_the_corpus_carries_both_kinds_of_shot_and_a_kill_signal(self):
        """The control: a measurement over an empty corpus proves nothing."""
        kinds = collections.Counter(kind for _, kind, _ in recorded_shots())
        self.assertGreater(kinds["miss"], 1000, kinds)
        self.assertGreater(kinds["hit"], 1000, kinds)
        self.assertGreater(kinds["kill"], 1000, kinds)

    def test_a_fight_that_recovered_missed_as_hard_as_one_that_never_did(self):
        """The finding: there is no share at which missing predicts a dead end.

        Scored against the client's own kill signal, the worst miss share on an
        interval that then produced a kill is at least as high as the worst on
        an interval that never produced one. The two populations do not
        separate, so no threshold on a miss rate can tell them apart.

        **The `never` population is thin and this case says so rather than
        leaning on it.** Every interval but the last of a session is closed by a
        kill, so what is left is one stretch per session and its composition is
        an artefact of where the log stops. The argument does not rest here:
        `test_a_long_hard_miss_run_recovered_on_its_own` carries it on the
        recovered side alone, where the sample is thousands. This case is the
        cheap tripwire for a corpus that grows a real stall population.
        """
        intervals = kill_free_intervals()
        recovered = [i["share"] for i in intervals if i["ends_in_kill"]]
        never = [i["share"] for i in intervals if not i["ends_in_kill"]]
        self.assertGreater(len(recovered), 100, "too few intervals to measure")
        self.assertTrue(never, "no interval in the corpus failed to produce a kill")
        self.assertGreaterEqual(
            max(recovered), max(never),
            "a fight that never got anywhere now misses harder than any that "
            "recovered -- the populations have separated and a threshold may "
            "be writable")

    def test_a_long_hard_miss_run_recovered_on_its_own(self):
        """The 702-hazard, from the side that makes it a hazard.

        **This is the case the whole change rests on, and it needs one
        population rather than two.** The corpus holds an interval that missed
        nearly every shot for hundreds of consecutive shots and then killed its
        rat. Any threshold on a miss rate below that share fires on it and
        breaks off a fight that was being won -- which is true whatever the
        stretches that killed nothing look like, and is why nothing here has to
        argue from the thin side of the split.
        """
        recovered = [i for i in kill_free_intervals() if i["ends_in_kill"]]
        punishing = [i for i in recovered
                     if i["share"] > 90.0 and i["shots"] >= 100]
        self.assertTrue(
            punishing,
            "no interval in the corpus both missed above 90%% and recovered; "
            "the hazard this change refuses to act on may have gone")

    def test_the_windows_that_killed_something_miss_more_not_less(self):
        """The finding read the other way round, and the direction is the point.

        Over fixed windows the median miss share is *higher* where a rat died
        than where none did. A rule keyed on missing would fire hardest on the
        grids that were paying.
        """
        scored = windows(30)
        killed = [share for share, did in scored if did]
        quiet = [share for share, did in scored if not did]
        self.assertGreater(len(killed), 100)
        self.assertGreater(len(quiet), 100)
        self.assertGreaterEqual(
            median(killed), median(quiet),
            "the fights that kill things no longer miss at least as much as "
            "the ones that do not -- the premise this change declines has "
            "started to hold")

    def test_the_stalls_this_bot_suffers_are_not_miss_stalls(self):
        """PR #272's finding restated from this side.

        A miss signal could not have caught run 48 however it was tuned: the
        stretches of fighting that killed nothing are mostly stretches in which
        the guns were *landing*. Asserted as the relation -- most kill-free
        intervals sit below a high miss share -- rather than as a count.

        Same thin population as above, and the same posture: this is corroboration
        for PR #272's own reading of run 48 rather than the load-bearing half.
        """
        never = [i["share"] for i in kill_free_intervals()
                 if not i["ends_in_kill"]]
        self.assertTrue(never)
        low = [share for share in never if share < 50.0]
        self.assertGreaterEqual(
            len(low) * 2, len(never),
            "kill-free fighting is now mostly high-miss, so misses may have "
            "become the explanation for a stall")

    def test_the_separation_moves_with_the_window_so_it_is_not_a_gap(self):
        """A gap that depends on how you cut the corpus is not a gap.

        At some window lengths the two populations look separated and at others
        they do not. That instability is itself the evidence against a
        threshold, so it is asserted rather than left as a remark.
        """
        verdicts = set()
        for length in (10, 30, 60):
            scored = windows(length)
            killed = [share for share, did in scored if did]
            quiet = [share for share, did in scored if not did]
            if len(killed) < 50 or len(quiet) < 20:
                continue
            verdicts.add(max(quiet) > max(killed))
        self.assertGreater(len(verdicts), 1,
                           "the two populations now order the same way at every "
                           "window length, so the instability this rests on has "
                           "gone")
