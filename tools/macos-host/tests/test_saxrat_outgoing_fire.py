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

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)

# The host's own directory on the path, then the module by its plain name --
# `tools/macos-host/botlab_host/` carries no `__init__.py`, so it is not a
# package and `from botlab_host import botlab_host` only resolves where an
# implicit namespace package happens to win. That is the idiom every other file
# here uses, and the one that survives being collected from the repo root.
HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402

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
# saxrat's own runs, which are the only corpus that carries the loaded charge
# and the target distance *and* echoes the client's `(combat)` and `(bounty)`
# lines. That combination is what the conditional hypothesis needs and the
# client logs alone cannot supply.


NO_SAXRAT_RUNS = ("no recorded saxrat runs in ~/eve-bot-logs, so what the "
                  "loaded charge was at each range cannot be counted here")

# `# [N.M]` is reading N, **step** M. Folding on the whole marker counts steps,
# which is the confusion that has already cost `stall_watch.py` two threshold
# calibrations, #141 a retreat measurement and #164 an issue's whole diagnosis.
# Consecutive blocks sharing N are one reading.
STEP_MARKER = re.compile(r"^# \[(\d+)\.\d+\]")
GAME_LOG_ECHO = re.compile(r"^#\s+game log: (.*)$")
AMMO_CLAUSE = re.compile(
    r"Ammo swap: loaded charge reads (\S+?)(?: \(assumed[^)]*\))?, "
    r"crossover (\d+) m \(\+/-(\d+)[^)]*\), target distance (\d+) m")

_RUNS = {}


def saxrat_runs():
    """Every recorded saxrat run, folded to readings. Cached for the process."""
    if _RUNS:
        return _RUNS
    paths = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
    if not paths:
        raise unittest.SkipTest(NO_SAXRAT_RUNS)
    for path in paths:
        rows = readings_in_run(path)
        if any(row["ammo"] for row in rows):
            _RUNS[path] = rows
    if not _RUNS:
        raise unittest.SkipTest(NO_SAXRAT_RUNS)
    return _RUNS


def readings_in_run(path):
    """One entry per reading: its ammo clause and what the guns did.

    The combat and bounty lines are read through the host's own matchers rather
    than a regex here, exactly as the client-log reader above does, so both
    corpora are measured with the shipped patterns.
    """
    out = []
    current = None
    index = None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            marker = STEP_MARKER.match(line)
            if marker:
                number = int(marker.group(1))
                if number != index:
                    if current is not None:
                        out.append(current)
                    current = {"hits": 0, "misses": 0, "kills": 0, "ammo": None}
                    index = number
                continue
            if current is None:
                continue
            clause = AMMO_CLAUSE.search(line)
            if clause and current["ammo"] is None:
                current["ammo"] = (clause.group(1), int(clause.group(2)),
                                   int(clause.group(3)), int(clause.group(4)))
                continue
            echoed = GAME_LOG_ECHO.match(line)
            if not echoed:
                continue
            text = " ".join(botlab_host._GAME_LOG_MARKUP.sub(
                "", echoed.group(1)).split())
            entry = botlab_host.parse_game_log_line(text)
            if entry is None:
                continue
            if entry["channel"] == "bounty" and KILL_MARKER in entry["text"]:
                current["kills"] += 1
            elif botlab_host.parse_outgoing_damage(entry) is not None:
                current["hits"] += 1
            elif botlab_host.parse_outgoing_miss(entry) is not None:
                current["misses"] += 1
    if current is not None:
        out.append(current)
    return out


def charge_matches_the_range(ammo):
    """`appropriate`, `mismatched`, or None where the corpus cannot say.

    **The dead band is excluded rather than assigned.** Inside it the swap
    itself declines to decide, so calling the charge right or wrong there would
    be this measurement inventing a verdict the bot never formed -- and run 48's
    deadlock is precisely a target parked in that band.

    The charge is the bot's *believed* one, which its own clause marks `assumed
    from the load, not read back`. That is deliberate rather than a compromise:
    a trigger could only ever act on the belief, so measuring on the belief
    measures exactly the input the proposed rule would have had.
    """
    if ammo is None:
        return None
    loaded, crossover, deadband, distance = ammo
    if loaded not in ("long-range", "short-range"):
        return None
    if distance > crossover + deadband:
        wanted = "long-range"
    elif distance < crossover - deadband:
        wanted = "short-range"
    else:
        return None
    return "appropriate" if loaded == wanted else "mismatched"


def charge_stretches(rows, lookahead):
    """Maximal runs of consecutive readings sharing one class.

    `lookahead` readings past the end also count toward "a rat died", which is
    what stops a class boundary faking a stall: the one stretch that made this
    partition look separated is run 36's, and three rats die in the readings
    immediately after it.
    """
    kills = [row["kills"] for row in rows]
    out = []
    start = None
    for index in range(len(rows) + 1):
        kind = (charge_matches_the_range(rows[index]["ammo"])
                if index < len(rows) else None)
        previous = (charge_matches_the_range(rows[start]["ammo"])
                    if start is not None else None)
        if start is not None and kind != previous:
            span = rows[start:index]
            hits = sum(row["hits"] for row in span)
            misses = sum(row["misses"] for row in span)
            died = (sum(row["kills"] for row in span)
                    + sum(kills[index:index + lookahead]))
            if hits + misses:
                out.append({"kind": previous, "readings": len(span),
                            "shots": hits + misses, "misses": misses,
                            "kills": died})
            start = None
        if kind is not None and start is None:
            start = index
    return out


def all_charge_stretches(lookahead, floor):
    out = []
    for rows in saxrat_runs().values():
        out += [s for s in charge_stretches(rows, lookahead)
                if s["shots"] >= floor]
    return out


def miss_share(stretch):
    return 100.0 * stretch["misses"] / stretch["shots"]


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
        # places: `vkey_E` once and `vkey_W` once. Since #285 the loot window's
        # escape is `Alt+C` rather than `Ctrl+W`, so `vkey_W` no longer has a
        # second site here.
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


class TheRangeConditionedHypothesisTest(unittest.TestCase):
    """The refined proposal: misses only mean "wrong ammo" if the range agrees.

    The unconditional rule has no threshold, and the answer offered to that was
    that a miss is only evidence when the loaded charge is on the wrong side of
    the `ammo-swap-range` crossover for the current target distance. So the fire
    is partitioned on exactly that and the kill question asked inside each half.

    This needs saxrat's own runs rather than the client's logs, because only
    they carry the loaded charge and the target distance beside the shots.
    Counted in **readings**, folded at real reading boundaries.

    It does not separate, and the mechanism it assumes is not there either.
    """

    def test_the_dead_band_is_excluded_rather_than_assigned(self):
        """The premise the partition is built on, held rather than stated.

        Inside the crossover's dead band the swap itself declines to decide, so
        calling the charge right or wrong there would be this measurement
        inventing a verdict the bot never formed -- and run 48's deadlock is
        exactly a target parked in that band, so the readings this would
        misclassify are the ones the question is about. A mutation that
        classified the band instead of skipping it survived every other case
        here, which is why this one exists.
        """
        crossover, deadband = 20000, 3000
        for distance in (crossover - deadband, crossover, crossover + deadband):
            for loaded in ("short-range", "long-range"):
                self.assertIsNone(
                    charge_matches_the_range(
                        (loaded, crossover, deadband, distance)),
                    "a reading %d m from a %d m crossover is inside the dead "
                    "band and must be classified as neither" % (distance, crossover))
        # And just outside it, both directions resolve the way the swap would.
        self.assertEqual(charge_matches_the_range(
            ("long-range", crossover, deadband, crossover + deadband + 1)),
            "appropriate")
        self.assertEqual(charge_matches_the_range(
            ("short-range", crossover, deadband, crossover + deadband + 1)),
            "mismatched")
        self.assertEqual(charge_matches_the_range(
            ("short-range", crossover, deadband, crossover - deadband - 1)),
            "appropriate")
        self.assertEqual(charge_matches_the_range(
            ("long-range", crossover, deadband, crossover - deadband - 1)),
            "mismatched")
        # An unread charge is not a verdict either.
        self.assertIsNone(charge_matches_the_range(
            ("unknown", crossover, deadband, 50000)))

    def test_the_corpus_holds_both_halves_of_the_partition(self):
        """The control: a partition with nothing on one side proves nothing."""
        pooled = collections.Counter()
        for rows in saxrat_runs().values():
            for row in rows:
                kind = charge_matches_the_range(row["ammo"])
                if kind:
                    pooled[kind] += row["hits"] + row["misses"]
        self.assertGreater(pooled["appropriate"], 2000, pooled)
        self.assertGreater(pooled["mismatched"], 2000, pooled)

    def test_a_charge_on_the_wrong_side_of_the_crossover_does_not_miss_more(self):
        """The mechanism the hypothesis rests on is not in the corpus.

        Pooled over every classifiable reading, the charge the swap would call
        wrong for the range misses **no more** than the one it would call right.
        That is what a crossover is: it is about damage at range, not about
        tracking, and what makes a shot miss is the target's angular velocity.
        So the proposed condition is not selecting fights where the guns cannot
        hit -- there is no such population to select.

        Asserted as the relation rather than as the two percentages, with a
        margin, so ordinary drift cannot turn a true claim red.
        """
        pooled = collections.defaultdict(lambda: [0, 0])
        for rows in saxrat_runs().values():
            for row in rows:
                kind = charge_matches_the_range(row["ammo"])
                if kind:
                    pooled[kind][0] += row["hits"] + row["misses"]
                    pooled[kind][1] += row["misses"]
        shares = {kind: 100.0 * missed / shots
                  for kind, (shots, missed) in pooled.items()}
        self.assertLessEqual(
            shares["mismatched"], shares["appropriate"] * 1.5,
            "a mismatched charge now misses half again as much as an "
            "appropriate one (%r), so the mechanism the range-conditioned "
            "trigger assumes may have appeared" % shares)

    def test_the_mismatched_partition_does_not_separate_either(self):
        """The finding: conditioning on the range does not rescue the signal.

        Inside the mismatched half, the stretches that produced a kill reach a
        **100%** miss share -- so any threshold fires on a fight that was being
        won, exactly as it does in the pooled data. Conditioning removes the
        barren population rather than sharpening it.

        A lookahead is used because without one a class boundary fakes a stall;
        see the case below, which is the whole reason this reads differently
        from the first pass.
        """
        for floor in (10, 20, 40):
            stretches = [s for s in all_charge_stretches(lookahead=10, floor=floor)
                         if s["kind"] == "mismatched"]
            killed = [miss_share(s) for s in stretches if s["kills"]]
            barren = [miss_share(s) for s in stretches if not s["kills"]]
            self.assertGreater(len(killed), 20,
                               "too few mismatched stretches at floor %d" % floor)
            self.assertGreaterEqual(
                max(killed), max(barren) if barren else 0.0,
                "at shot floor %d a mismatched stretch that never produced a "
                "kill now misses harder than any that did -- the range-"
                "conditioned trigger may have become writable" % floor)

    def test_the_apparent_gap_is_one_stretch_and_a_class_boundary(self):
        """Why the first pass looked like it separated, and why it does not.

        Scored with no lookahead the mismatched half shows a gap -- and it rests
        on exactly **one** stretch at every shot floor. That stretch is run 36's:
        a short-range charge held while the target drifts from 19 km out to 34 km
        against a 15 km crossover, missing every shot -- 58 shots over 133
        readings, no kill. It is scored barren only because the charge class
        changed before the kill landed. **Three rats die in the very next ten
        readings**, on three landed shots and no misses at all.

        So the case asserts both halves -- that the unguarded gap is one stretch
        wide, and that a lookahead of ten readings dissolves it. The count is
        allowed a little slack rather than pinned at one, so a corpus that grows
        another such stretch reports the finding rather than a red suite; two is
        still "one anomaly", and three would be worth arguing about.
        """
        for floor in (10, 20, 40):
            unguarded = [s for s in all_charge_stretches(lookahead=0, floor=floor)
                         if s["kind"] == "mismatched"]
            killed = [miss_share(s) for s in unguarded if s["kills"]]
            above = [miss_share(s) for s in unguarded
                     if not s["kills"] and miss_share(s) > max(killed)]
            self.assertLessEqual(
                len(above), 2,
                "the unguarded gap at floor %d now rests on %d stretches rather "
                "than one or two, which is enough to be worth arguing about"
                % (floor, len(above)))

        guarded = [s for s in all_charge_stretches(lookahead=10, floor=20)
                   if s["kind"] == "mismatched"]
        killed = [miss_share(s) for s in guarded if s["kills"]]
        barren = [miss_share(s) for s in guarded if not s["kills"]]
        self.assertTrue(
            not barren or max(barren) <= max(killed),
            "ten readings of lookahead no longer dissolve the gap")

    def test_the_separation_does_not_survive_a_change_of_lookahead(self):
        """The same instability that exposed the pooled signal as noise.

        A finding that holds only at one lookahead is a finding about the
        boundary. Here the verdict flips between no lookahead and any lookahead
        at all, which is the evidence against the threshold rather than a
        caveat on it.
        """
        verdicts = set()
        for lookahead in (0, 10, 20, 40):
            stretches = [s for s in all_charge_stretches(lookahead, floor=20)
                         if s["kind"] == "mismatched"]
            killed = [miss_share(s) for s in stretches if s["kills"]]
            barren = [miss_share(s) for s in stretches if not s["kills"]]
            if not killed:
                continue
            verdicts.add(bool(barren) and max(barren) > max(killed))
        self.assertGreater(
            len(verdicts), 1,
            "the mismatched partition now orders the same way at every "
            "lookahead, so the instability this rests on has gone")
