"""What `isInActiveState` means, read off the corpus rather than assumed.

Issue #286. Three rules read this entry as *switched on* -- #50's
`moduleReadsSwitchedOff`/`moduleReadsSwitchedOn`, #76's `weaponIsSwitchedOn` and
#154's `switchOffUndoneByClient` -- and a live read of an Omen Navy Issue
contradicted them: four `ModuleButton` nodes all reading `isInActiveState=True`
while only one module was running, with the disproof a state change rather than a
snapshot (pressing two of the modules' hotkeys moved them from
`ramp_active=None` to `ramp_active=True`, and a module button is a toggle).

**Nothing about the three rules changes here, and that is deliberate.** They sit
on the path that disarms the ship, and #34 is the standing record of what acting
on a field's assumed meaning costs. What this file does is execute what each rule
answers today and pin the corpus relations underneath the reading, so that a fix
is somebody's decision rather than a drift -- and so that the day a run
contradicts the finding, a case says so.

**Two prerequisites, two different answers**, per `prerequisites.py`: the rules
are *executed* through the real `Bot.elm` in `elm repl` (absent toolchain is an
error, never a skip), and the corpus classes read `~/eve-bot-logs` (absent
corpus is a skip with its reason stated, since CI has no runs).

The unit is the **reading**, not the decision line. The host reprints the whole
status text under every decision, so the clause appears several times per
reading; `readings_of` cuts at the framework's own one-memory-read-per-reading
boundary, and `test_the_clause_repeats_under_every_decision` asserts the two
counts really do differ so that nothing below can be quietly counting the wrong
one. That confusion has already cost `stall_watch.py` two threshold
calibrations, #141 a retreat measurement and #164 an issue's whole diagnosis.

**Every run in the corpus repeats, at 2.6 to 3.4 clause lines a reading and no
run outside that band.** #284 has since stopped the host repeating an unchanged
status line, so a later run will read differently -- but the newest run here
(`d2fd6e0`, 2026-08-16 19:54) predates that merge by half an hour, so nothing
below is reading a suppressed log and a later reader must not assume this ratio
either way. What the cases assert is the relation rather than the ratio.

The corpus claims are *relations* -- the two flags never agree, a module whose
ramp widget does not exist never reads switched off, the swap's own "switched
back on" windows carry no fire -- rather than the counts in CLAUDE.md, so a
corpus that grows cannot turn a true claim red. Where a claim is asserted
absolutely it is because its whole purpose is to go red: a single observation of
`isInActiveState` disagreeing with `isDeactivating`, or one gun line inside a
window the bot reports as re-armed, means the finding has changed and somebody
should be looking at it rather than at a widened tolerance.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import SAXRAT_DIR, SaxratRepl

MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")

# Both spellings of the clause `describeTopRowModuleDictState` renders: the
# mission runner's `Top-row modules (...):` and saxrat's shorter `topmods (...)`.
# Reading both is what makes this one corpus rather than two.
CLAUSE = re.compile(
    r"(?:topmods|Top-row modules) \(ramp_active/isInActiveState/isDeactivating/"
    r"effect_activating/waitingForActiveTarget\):? ([^.|]*)\.")

# One memory read per reading, which is the framework's own boundary and the
# only per-reading identity these logs carry -- `# [N.M]` is a framework step.
READ_TASK = re.compile(r"^#   task read-from-game-\d+: RequestToVolatileProcess")

GAME_LOG = re.compile(r"^#   game log: \[ [^\]]*\] \((\w+)\) (.*)$")
OUTGOING_HIT = re.compile(r"^\d+ to (.+)$")
OUTGOING_MISS = re.compile(r"^Your (.+?) (?:misses|barely)")

# The client names the thing that fired on every outgoing line, so a gun shot
# and a drone shot are separable without attributing anything. The list is drone
# type names; anything else that fires is a module on this ship.
DRONE_NAMES = ("Acolyte", "Hobgoblin", "Hammerhead", "Warrior", "Vespa",
               "Valkyrie", "Berserker", "Ogre", "Wasp", "Praetor",
               "Infiltrator", "Curator", "Garde", "Bouncer", "Warden")


def shooter_named_by(text):
    """Who fired, off `N to <target> - <weapon> - <quality>`.

    Split on the separator rather than matched with a character class, because a
    target name carries hyphens of its own -- `The Holo-Star`, `Rent-A-Dream` --
    and `[^-]+` for the target silently drops every line naming one. That bites
    in the direction that matters here: those lines then read as *unattributed*,
    and a case asserting the guns fired nothing would be counting fewer shots
    than the client wrote.

    `None` where the client named nobody, which the caller counts as a gun for
    the same reason -- an unattributed shot must not make a quiet window quieter.
    """
    parts = [part.strip() for part in text.split(" - ")]
    return parts[-2] if len(parts) >= 3 else None

# `switchOffUndoneByClient` in the status line, in both bots' words -- saxrat's
# and the mission runner's, which says outright that the guns are firing. Both
# are read, because on one bot alone this measurement would rest on one run.
GUNS_BACK_ON = ("a gun has been switched back on ",
                "the client switched a gun back on by itself ")

# The swap waiting for `moduleReadsSwitchedOff`, in the decision line.
STILL_WAITING = "none has yet read switched off"

_CORPUS = None


class Reading(object):
    """One reading: the module states it printed, and what the client said."""

    __slots__ = ("modules", "clause_lines", "gun_lines", "drone_lines",
                 "back_on", "waiting", "index")

    def __init__(self, index):
        self.index = index
        self.modules = None
        self.clause_lines = 0
        self.gun_lines = 0
        self.drone_lines = 0
        self.back_on = False
        self.waiting = False


def readings_of(path):
    """The readings in one log, in order.

    A reading's module states are taken from the *last* clause it printed, since
    the status text is reprinted under every decision and the last one is the
    one the reading ended holding.
    """
    readings = []
    current = Reading(0)
    with open(path, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.rstrip("\n")
            if line.startswith("#   task read-from-game-") and READ_TASK.match(line):
                readings.append(current)
                current = Reading(len(readings))
                continue
            if line.startswith("#   game log: "):
                entry = GAME_LOG.match(line)
                if entry and entry.group(1) == "combat":
                    text = entry.group(2)
                    landed = OUTGOING_HIT.match(text)
                    missed = OUTGOING_MISS.match(text)
                    if landed or missed:
                        name = (shooter_named_by(landed.group(1)) if landed
                                else missed.group(1).strip())
                        if name and any(drone in name for drone in DRONE_NAMES):
                            current.drone_lines += 1
                        else:
                            current.gun_lines += 1
                continue
            if "isInActiveState" in line:
                found = CLAUSE.search(line)
                if found:
                    current.clause_lines += 1
                    # The mission runner joins several modules with ", ", so
                    # the separator is stripped rather than read as a value.
                    current.modules = [
                        entry.strip(",").split("/")
                        for entry in found.group(1).strip().split(" ")
                        if entry.count("/") == 4]
                    continue
            if any(clause in line for clause in GUNS_BACK_ON):
                current.back_on = True
            if STILL_WAITING in line:
                current.waiting = True
    readings.append(current)
    # The first element holds whatever the host printed before its first memory
    # read -- the compile, the settings -- and is not a reading.
    return readings[1:]


def corpus():
    """Every recorded run on this machine that carries the clause, parsed once.

    Cached at module scope because reading `~/eve-bot-logs` end to end is most
    of what this file costs locally, and nothing in it changes between cases.
    """
    global _CORPUS
    if _CORPUS is None:
        parsed = []
        for path in sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "*.log"))):
            readings = readings_of(path)
            if any(reading.modules for reading in readings):
                parsed.append((os.path.basename(path), readings))
        _CORPUS = parsed
    return _CORPUS


def corpus_or_skip():
    parsed = corpus()
    if not parsed:
        raise unittest.SkipTest(
            "no recorded run in ~/eve-bot-logs carries the module dict-state "
            "clause, so what the client wrote about its own modules cannot be "
            "consulted here")
    return parsed


def observations(parsed):
    for _, readings in parsed:
        for reading in readings:
            for module in reading.modules or []:
                yield module


def module_state(ramp, active, deactivating,
                 activating="Nothing", online="Just True"):
    """A `ShipUIModuleButtonState` written the way a log line reads.

    The five printed entries are given as the clause's own `T`/`F`/`-`, so a case
    quotes a real column rather than translating one. The remaining seven are the
    constants #39's sample measured and no rule reads.
    """
    flag = {"T": "Just True", "F": "Just False", "-": "Nothing"}
    return ("{ ramp_active = " + flag[ramp]
            + ", isInActiveState = " + flag[active]
            + ", isDeactivating = " + flag[deactivating]
            + ", effect_activating = " + activating
            + ", online = " + online
            + ", blinking = Just False"
            + ", grey = Just False"
            + ", quantity = Nothing"
            + ", autoreload = Just 1"
            + ", autorepeat = Just 1000"
            + ", isMaster = Just True"
            + ", waitingForActiveTarget = Just 0 }")


# Every combination of (ramp_active, isInActiveState, isDeactivating) the whole
# corpus contains, cut out of it rather than invented. The last two are the only
# ones in which anything reads switched off, and both carry `isDeactivating`.
STATES_THE_CLIENT_WRITES = [
    ("-", "T", "F"),
    ("F", "T", "F"),
    ("T", "T", "F"),
    ("T", "F", "T"),
    ("F", "F", "T"),
]


def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TheCorpusSaysWhatTheEntryIsTest(unittest.TestCase):
    """The client's own words about its own modules, over every recorded run."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = corpus_or_skip()
        cls.modules = list(observations(cls.parsed))
        cls.readings = [reading for _, readings in cls.parsed
                        for reading in readings if reading.modules]

    def test_the_corpus_is_large_enough_to_say_anything(self):
        # A floor rather than the count, so a machine holding some of the runs
        # still checks them and a machine holding more does not go red. The
        # floor is well under what any single run contributes, so it is a guard
        # against an empty read rather than a restatement of the total.
        self.assertGreaterEqual(len(self.parsed), 3)
        self.assertGreaterEqual(len(self.readings), 1000)
        self.assertGreaterEqual(len(self.modules), 1000)

    def test_the_client_writes_only_the_states_the_repl_cases_are_asked_about(self):
        # `STATES_THE_CLIENT_WRITES` is what the executed cases below feed to the
        # three rules, and its claim is that it is the whole vocabulary. Asserted
        # rather than left as a comment: a sixth combination would mean the repl
        # cases have stopped covering what the client actually writes, which is
        # the way a case like that goes quietly out of date.
        seen = {(module[0], module[1], module[2]) for module in self.modules}
        self.assertEqual(
            sorted(seen - set(STATES_THE_CLIENT_WRITES)), [],
            "the client writes a module state no executed case is asked about")

    def test_the_clause_repeats_under_every_decision(self):
        # The unit warning, executed. The host reprints the status text under
        # every decision, so counting clause *lines* over-counts readings -- and
        # every number below is per reading. If these two are ever equal the
        # log format has changed and the counts stop meaning what they say.
        lines = sum(reading.clause_lines for reading in self.readings)
        self.assertGreater(lines, len(self.readings))

    def test_the_two_flags_never_disagree_about_disagreeing(self):
        """`isInActiveState` is `not isDeactivating`, everywhere, always.

        Asserted absolutely and on purpose. They are separate dictionary keys
        read by separate `Dict.get`s in the parser, so one counterexample would
        mean the client distinguishes them after all and the whole reading in
        CLAUDE.md is wrong. That is a case worth going red.
        """
        both = [module for module in self.modules
                if (module[1] == "F") == (module[2] == "F")]
        self.assertEqual(
            both, [],
            "isInActiveState and isDeactivating are no longer complements, so "
            "#286's reading of the entry has to be re-derived")

    def test_switched_off_is_a_minority_and_switched_on_is_not(self):
        # The relation that makes `weaponIsSwitchedOn` close to a constant: the
        # entry reads `True` on the overwhelming majority of everything the
        # client has ever written about a module here.
        off = sum(1 for module in self.modules if module[1] == "F")
        self.assertGreater(len(self.modules), off * 50)

    def test_a_module_whose_ramp_widget_does_not_exist_still_reads_switched_on(self):
        """The reading that cannot be explained by "the toggle was on".

        `ramp_active` absent means the `ShipModuleButtonRamps` widget is not in
        the tree, which is a module that is not running. There are tens of
        thousands of those observations and not one of them reads switched off.
        """
        absent = [module for module in self.modules if module[0] == "-"]
        self.assertGreater(len(absent), 100)
        self.assertEqual(
            [module for module in absent if module[1] != "T"], [],
            "a module with no ramp widget read something other than switched "
            "on, which is the first evidence that the entry is a toggle after "
            "all")

    def test_a_session_that_fired_nothing_reads_switched_on_throughout(self):
        """Whole runs of it, with the client's combat log as the witness.

        Two conditions, and both are needed. The ramp widget never existing all
        session is the module never having run; the client's combat log carrying
        no gun line all session is the corroboration. **Neither alone would
        do** -- run 36 fired no gun line in 1,668 readings because every
        outgoing line in it belongs to a drone, and its guns were switched on
        and off inside that.
        """
        quiet = [(name, readings) for name, readings in self.parsed
                 if not any(reading.gun_lines for reading in readings)
                 and all(module[0] == "-"
                         for reading in readings
                         for module in reading.modules or [])
                 and sum(1 for reading in readings if reading.modules) >= 10]
        if not quiet:
            raise unittest.SkipTest(
                "no recorded run on this machine both carries the clause and "
                "fired nothing, so this reading cannot be taken here")
        for name, readings in quiet:
            states = {module[1] for reading in readings
                      for module in reading.modules or []}
            self.assertEqual(
                states, {"T"},
                "%s fired no shot all session and did not read switched on "
                "throughout" % name)

    def test_the_guns_neither_cycle_nor_fire_while_the_swap_reports_them_back_on(self):
        """#72's re-arm, against the client's own combat log.

        `switchOffUndoneByClient` says the client took the guns back. Over every
        window in which it has ever been set, the guns fire nothing and
        `ramp_active` never reads `True` -- while the readings on either side of
        the swap carry both. Asserted absolutely for the reason the class
        docstring gives: one gun line in such a window would mean a gun really
        did come back, and that is the day to look.
        """
        windows = 0
        during_readings = 0
        during_fire = 0
        during_cycling = 0
        outside_fire = 0
        outside_readings = 0
        outside_cycling = 0
        for name, readings in self.parsed:
            index = 0
            while index < len(readings):
                if readings[index].back_on and not (
                        index and readings[index - 1].back_on):
                    end = index
                    while end + 1 < len(readings) and readings[end + 1].back_on:
                        end += 1
                    window = readings[index:end + 1]
                    outside = (readings[max(0, index - 20):max(0, index - 10)]
                               + readings[end + 1:end + 11])
                    windows += 1
                    during_readings += len(window)
                    during_fire += sum(r.gun_lines for r in window)
                    during_cycling += sum(
                        1 for r in window
                        if any(m[0] == "T" for m in r.modules or []))
                    outside_readings += len(outside)
                    outside_fire += sum(r.gun_lines for r in outside)
                    outside_cycling += sum(
                        1 for r in outside
                        if any(m[0] == "T" for m in r.modules or []))
                    index = end + 1
                else:
                    index += 1
        if not windows:
            raise unittest.SkipTest(
                "no recorded run on this machine ever set "
                "switchOffUndoneByClient, so what the guns were doing while it "
                "was set cannot be read here")
        self.assertEqual(
            during_fire, 0,
            "the guns fired while the swap reported them switched back on, so "
            "#286's reading of switchOffUndoneByClient has to be re-derived")
        self.assertEqual(during_cycling, 0, "ramp_active read True in a window "
                         "the swap reported as re-armed")
        # The control: the same guns, either side of the same swaps, doing both.
        self.assertGreater(outside_fire, 0)
        self.assertGreater(outside_cycling, 0)

    def test_half_the_waits_for_silence_are_on_guns_that_had_gone_quiet(self):
        """How much of "the guns never go quiet" this entry accounts for.

        `none has yet read switched off` is printed while the swap waits for
        `moduleReadsSwitchedOff`. Some of those waits are guns that really are
        still running, which is #76's territory; the rest are guns the client's
        own combat log shows to be silent, which is this entry's transient being
        missed. Both populations exist, which is the claim -- the split itself is
        a number about one corpus and is left to CLAUDE.md.
        """
        quiet = noisy = 0
        for _, readings in self.parsed:
            index = 0
            while index < len(readings):
                if readings[index].waiting and not (
                        index and readings[index - 1].waiting):
                    end = index
                    while end + 1 < len(readings) and readings[end + 1].waiting:
                        end += 1
                    if sum(r.gun_lines for r in readings[index:end + 1]):
                        noisy += 1
                    else:
                        quiet += 1
                    index = end + 1
                else:
                    index += 1
        if not quiet + noisy:
            raise unittest.SkipTest(
                "no recorded run on this machine waited for the guns to read "
                "switched off, so the two populations cannot be separated here")
        self.assertGreater(
            quiet, 0,
            "no wait for silence was ever taken on guns that had already gone "
            "quiet, which would make this entry no part of that failure")
        self.assertGreater(
            noisy, 0,
            "every wait for silence was taken on quiet guns, which would make "
            "this entry the whole of that failure and #76 none of it")


class WhatTheRulesAnswerTodayBase(object):
    """The three rules, executed over the module states the client writes.

    Nothing here asserts what the rules *should* answer. Each case executes what
    they answer now, so the reading in CLAUDE.md is run rather than described and
    a later repointing fails a named case instead of passing silently.
    """

    repl_class = None
    app_dir = None
    bot_elm = None

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(cls.repl_class)
        cls.source = source_of(cls.bot_elm)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_switched_off_is_answered_exactly_where_the_client_is_deactivating(self):
        expressions = [
            "moduleReadsSwitchedOff " + module_state(*state)
            for state in STATES_THE_CLIENT_WRITES]
        answers = self.repl.evaluate(expressions)
        self.assertEqual(
            answers,
            [state[2] == "T" for state in STATES_THE_CLIENT_WRITES],
            "moduleReadsSwitchedOff no longer answers exactly isDeactivating "
            "over the states the client writes")

    def test_switched_on_is_answered_everywhere_else(self):
        expressions = [
            "moduleReadsSwitchedOn " + module_state(*state)
            for state in STATES_THE_CLIENT_WRITES]
        answers = self.repl.evaluate(expressions)
        self.assertEqual(
            answers, [state[2] == "F" for state in STATES_THE_CLIENT_WRITES])

    def test_a_module_that_has_never_run_reads_switched_on(self):
        # The discriminating case, and the one the corpus supplies 20,095 times:
        # no ramp widget at all -- so the module is not running -- and the rules
        # answer switched on.
        never_ran = module_state("-", "T", "F", activating="Nothing")
        self.assertEqual(
            self.repl.evaluate(["moduleReadsSwitchedOn " + never_ran,
                                "moduleReadsSwitchedOff " + never_ran]),
            [True, False])

    def test_an_entry_that_did_not_decode_answers_neither(self):
        # Unchanged and asserted so it stays that way: both predicates are
        # `Just`-only, so a build without the entry behaves as though the signal
        # did not exist rather than as though the module were off.
        undecoded = module_state("F", "T", "F").replace(
            "isInActiveState = Just True", "isInActiveState = Nothing")
        self.assertEqual(
            self.repl.evaluate(["moduleReadsSwitchedOn " + undecoded,
                                "moduleReadsSwitchedOff " + undecoded]),
            [False, False])

    def test_the_undone_report_fires_when_the_deactivation_ends(self):
        """The transition #286 measures, folded through the real rule.

        `T/F/T` is the deactivation; the reading after it is `F/T/F`, which is
        the same gun still switched off. The rule answers `True` there, which is
        what it reports as the client having taken the guns back.
        """
        deactivating = "[ " + module_state("T", "F", "T") + " ]"
        settled = "[ " + module_state("F", "T", "F") + " ]"
        self.assertEqual(
            self.repl.evaluate([
                # No confirmation yet: there is no undoing to detect.
                "switchOffHasBeenUndone False " + settled,
                # The confirmation reading itself.
                "switchOffHasBeenUndone True " + deactivating,
                # The reading after it, with nothing having pressed anything.
                "switchOffHasBeenUndone True " + settled,
            ]),
            [False, False, True])

    def test_the_three_rules_are_unchanged(self):
        # #286 changes no behaviour. These are the expressions the corpus was
        # read against, so a repointing that is not accompanied by new evidence
        # fails here rather than quietly making the measurement above describe
        # something the bot no longer does.
        code = re.sub(r"\{-.*?-\}", "", self.source, flags=re.DOTALL)
        collapsed = " ".join(code.split())
        for expression in (
                "moduleReadsSwitchedOff state = state.isInActiveState == Just False",
                "moduleReadsSwitchedOn state = state.isInActiveState == Just True",
                "weaponIsSwitchedOn moduleButton = moduleReadsSwitchedOn "
                "moduleButton.stateFromDictEntries",
                "switchOffHasBeenUndone confirmedOffBefore moduleStates = "
                "confirmedOffBefore && not (moduleStates |> List.any "
                "moduleReadsSwitchedOff) && (moduleStates |> List.any "
                "moduleReadsSwitchedOn)"):
            self.assertIn(expression, collapsed)

    def test_the_correction_is_written_where_an_editor_would_read_it(self):
        """CLAUDE.md is not what somebody repointing these rules is reading.

        The doc comment above each rule is, which is the same argument
        `loadRefusalFromGameLog` carries for #31. So the measurement has to be
        there, and the sentence it replaces has to be gone -- a doc comment that
        still asserts the entry means switched on is how this gets re-derived
        from scratch in six months.
        """
        docs = "\n".join(re.findall(r"\{-\|.*?-\}", self.source, flags=re.DOTALL))
        self.assertIn("#286", docs)
        self.assertIn("not the toggle", docs)
        for expired in (
                "`isInActiveState` is the entry that means switched on",
                "which is what the entry measurably means",
                "So the client re-arms the gun by itself, on every swap"):
            self.assertNotIn(
                expired, docs,
                "a doc comment still carries a claim #286 measured to be false")


class WhatSaxratsRulesAnswerTodayTest(WhatTheRulesAnswerTodayBase,
                                      unittest.TestCase):
    repl_class = SaxratRepl
    app_dir = SAXRAT_DIR
    bot_elm = os.path.join(SAXRAT_DIR, "Bot.elm")


class WhatTheMissionRunnersRulesAnswerTodayTest(WhatTheRulesAnswerTodayBase,
                                                unittest.TestCase):
    repl_class = None
    app_dir = MISSION_RUNNER_DIR
    bot_elm = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl()
        cls.source = source_of(cls.bot_elm)


if __name__ == "__main__":
    unittest.main()
