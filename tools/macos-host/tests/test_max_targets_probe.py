"""Tests for the probe that lets the learned lock-slot ceiling bootstrap.

PR #149 taught both bots to learn their ceiling and **neither half of it could
move on its own**, which is issue #150. `maxTargetsCeiling` is
`max heldAtOnce (statedByClient or setting)` and that number fed the lock site's
`List.take`, so the bot locked four, saw four held and learned four; and
`statedByClient` comes from a refusal the client writes only when a lock is
attempted **beyond** the cap, which stopping at the ceiling never provokes. The
constraint being learned is the one that prevents the attempt. All 228 recorded
statements exist because a person locked the extra targets by hand.

So the lock site now takes **one row more than it believes in** until the client
states its maximum. A probe that lands raises `heldAtOnce`, which raises the
ceiling, so the next probe is one higher and it ratchets; a probe the client
declines produces the sentence, which sets `statedByClient` and ends the probing
for the session. The refused attempt is not waste, it *is* the measurement, and
there is one of them per session rather than one per reading.

Five things had to be got right and each has its own case here.

- **The probe must not displace a real target.** It is `List.take (n + 1)`
  rather than a different `n`, so the rows the ceiling covers keep their order
  and their places and the extra one is reachable only once every one of them is
  locked -- `TheProbeIsAnExtraRowAndNotAReRanking`.
- **A refused probe must not read as a stuck lock.** `lockAttemptCanTeachRange`
  discharges any attempt begun with the target bar occupied, which every probe
  is by definition, so none of `lockAttemptReadingsBeforeVerdict` is spent on
  one and the give-up can never see it -- `ARefusedProbeIsNotAStuckLock`.
- **Nothing to spare means no probe.** A probe due with no lockable row in range
  beyond the ones held answers `MaxTargetsProbeNothingToSpare` and the reading
  says so instead of counting an attempt -- `NothingToSpareMeansNoProbe`.
- **The probing stops on the statement and on no count.**
  `MaxTargetsProbeSettled` is the only answer that ends it, so a client that
  never names a number is asked again rather than given up on after some bound
  nobody has evidence for -- `TheStatementIsWhatEndsTheProbing`.
- **The row-identity discipline is untouched**, which is PR #149's own finding
  and the property this must not spend. The rule is a function of two counts and
  a state and reaches for no overview row --
  `TheRowIdentityDisciplineIsStillUntouched`.

**The first live run of #149 says the rule is inert, which is #150's premise
observed rather than argued.** saxrat's run 6 launched from that change's own
merge commit while this was being written: 2,193 readings, the `Max targets:`
clause on every one, `client stated -` on every one, not one statement from the
client and not one ceiling moved. `test_learned_max_targets` next door is what
asserts it, since that file's own case predicting an empty corpus expired the
moment run 6 launched.

**What a refused lock costs is measured rather than assumed**, and the corpus
had more to say than the issue does. `mission_run37.log` -- in flight,
unattended, no `standing down` anywhere in the window -- shows the **bot's own**
`Lock more targets.` click answered by
`(notify) You are already managing 6 targets, as many as you have skill to.` on
the very next reading, eight distinct times. So the statement is provoked by a
click the bot makes today whenever the bar is full of rows other than its
candidates, it arrives within one reading, and the mechanism is not purely
hand-fed after all. What it cost is the pending attempt: it climbed to the
verdict count and latched there, and `for 8 readings` appears on more than three
thousand status lines across 22 recorded runs while `stop waiting for it` has
fired **zero**
times in the whole corpus -- the give-up is only asked of a row that reads
`targeting`, and a lock the client declines never does.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, and the lock-range half is folded over whole sessions
through saxrat's own `updateLockRangeLearning`, which is pure. Every rule is
asked of **both** apps and a case compares the shared declarations byte for
byte.

Confirmed by mutation, **fourteen** of them, each failing a named case: the take
count back at the ceiling so nothing can bootstrap (the mutation this whole
change refuses), the probe taking a different row rather than one more, the
probe due while the bar is below the ceiling so it displaces a real target,
`rowsToSpare` ignored so a probe is counted with nothing to attempt, the probe
row taken from the unfiltered list so the ship flies at a rat to measure
something, the statement no longer ending the probing, a count invented that
ends it early, `lockAttemptCanTeachRange` inverted or dropped so a refused probe
spends the lock-attempt budget, the discharge branch removed from either app,
saxrat's `Enough locked targets.` gate left on the raw ceiling, saxrat's lock
window left at its hardcoded 4, the status line no longer saying it is probing,
and `overviewEntryLockHandle`'s same-name exclusion loosened.

Nothing here reads a live game client or a running bot. The corpus cases read
the recorded runs in `~/eve-bot-logs`, and only read them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, source_of)
from test_learned_max_targets import (
    APPS, CLIENT_MAXIMUM, MISSION_RUNNER_BOT_ELM, MaxTargetsRepl,
    SHIPPED_DEFAULT, STATED_SIX, SaxratMaxTargetsRepl, reading, state)
from test_saxrat_learned_lock_range import (
    LockRangeRepl, flying, overview_rows, row_center)

# What each app's status line says the ceiling is: nothing learned, the target
# bar having held six, and the client having stated six. #242 shortened
# saxrat's status line and left the mission runner's alone, so the two render
# the same four facts in different words -- and what the case below asserts is
# that all four survive whichever spelling the app uses.
MAX_TARGETS_CLAUSES = {
    "saxrat": ("maxtgt 4 (setting 4 client - held - probing 5).",
               "maxtgt 6 (setting 4 client - held 6 probing 7).",
               "maxtgt 6 (setting 4 client 6 held 5)."),
    "mission runner": (
        "Max targets: 4 (setting 4, client stated -, most held at once -, "
        "probing for 5).",
        "Max targets: 6 (setting 4, client stated -, most held at once 6, "
        "probing for 7).",
        "Max targets: 6 (setting 4, client stated 6, most held at once 5)."),
}

# The declarations #150 adds, which both apps carry identically. A port that
# keeps one and drops another is what `BothAppsCarryTheSameRule` refuses, and
# the failure would be quiet -- a bot that never probes reads exactly like a
# client that granted nothing.
SHARED_DECLARATIONS = (
    "maxTargetsRowsToTake",
    "maxTargetsProbe",
    "describeMaxTargetsProbe",
    "describeMaxTargetsNothingToLock",
    "maxTargetsStateBefore",
    "lockAttemptCanTeachRange",
)

# The type declarations the same argument applies to, which `body_of` cannot
# read because they carry no type annotation of their own.
SHARED_TYPES = ("MaxTargetsProbeSituation", "MaxTargetsProbe")

# The line the bot prints on a reading it asks for a lock it already expects to
# be granted, unchanged from before #150 so an operator's existing grep still
# answers.
ORDINARY_LOCK_LINE = "Lock more targets."


def type_declaration(source, name):
    """One `type` or `type alias` declaration, to the next blank-line pair."""
    match = re.search(r"^type (?:alias )?%s\b.*?(?=\n\n\n|\Z)" % re.escape(name),
                      source, re.MULTILINE | re.DOTALL)
    assert match, "no type declaration named %r" % name
    return match.group(0)


def probe(fromSetting, targetsHeld, rowsToSpare, stated=None, held=None):
    """A `MaxTargetsProbeSituation`, written the way the repl wants it."""
    return ("{ state = %s, targetsHeld = %d, rowsToSpare = %d }"
            % (state(fromSetting, stated=stated, held=held),
               targetsHeld, rowsToSpare))


class ProbeRepl(MaxTargetsRepl):
    """The mission runner's `Bot.elm` and the bindings these cases need."""

    HELPERS = MaxTargetsRepl.HELPERS + [
        # A list of rows standing in for the overview's, so the take can be run
        # over something with an order rather than described.
        "rows = List.range 1 12",
        # The take the lock site makes, and the take it would make with the
        # probe switched off, so a case can compare them rather than assert
        # each against a number it wrote down itself.
        "taken = \\st -> rows |> List.take (maxTargetsRowsToTake st)",
        "takenWithoutProbing = \\st -> rows |> List.take (maxTargetsCeiling st)",
        # A whole session of readings the bar never rises through and the client
        # never speaks on, which is the client that states nothing.
        "silentSession = \\count setting ->"
        " List.foldl step (nothingKnown setting)"
        " (List.repeat count (quietReading setting))",
    ]


class SaxratProbeRepl(SaxratRepl, ProbeRepl):
    """The same bindings, pointed at saxrat."""


class BothAppsRepl:
    """One repl per app, so every rule below is asked of both."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {"saxrat": open_repl(SaxratProbeRepl),
                     "mission runner": open_repl(ProbeRepl)}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        """`(app, answers)` for every app, so a failure names which one."""
        for app, repl in self.repls.items():
            yield app, repl.evaluate(
                expressions, repl.with_helpers(definitions))


class TheCeilingCanNowBootstrap(BothAppsRepl, unittest.TestCase):
    """The whole of #150: the bot asks for one more than it believes in.

    Without this both halves of PR #149 are inert. The floor cannot rise past
    the ceiling because the ceiling is what the lock site takes, and the stated
    maximum cannot arrive because the client writes it only for a lock beyond
    the cap.
    """

    def test_the_lock_site_takes_one_more_than_the_ceiling_while_unstated(self):
        """Asked at fixed settings rather than only either side of a boundary,
        which is the hole CLAUDE.md records four of #120's cases having: a pair
        astride a constant passes for any constant, including one that admits
        everything."""
        for app, answers in self.each(
                ["maxTargetsRowsToTake %s == %d" % (state(setting), setting + 1)
                 for setting in (0, 1, 2, SHIPPED_DEFAULT, CLIENT_MAXIMUM, 17)]):
            self.assertEqual(
                answers, [True] * 6,
                "%s stops at the ceiling it already believes in, so nothing it "
                "does can ever provoke the client's statement and the ceiling "
                "cannot move -- which is #150 exactly" % app)

    def test_a_probe_that_lands_ratchets_the_next_one_higher(self):
        """The bar holding five raises the floor, which raises the ceiling,
        which is what makes the next probe ask for six. That is the whole
        mechanism by which a session climbs from the shipped 4 to the client's
        own maximum without a person locking anything."""
        after_five = "step %s %s" % (reading(5), state(SHIPPED_DEFAULT))
        after_six = "step %s (%s)" % (reading(CLIENT_MAXIMUM), after_five)
        for app, answers in self.each(
                ["maxTargetsRowsToTake %s == 5" % state(SHIPPED_DEFAULT),
                 "maxTargetsRowsToTake (%s) == 6" % after_five,
                 "maxTargetsRowsToTake (%s) == 7" % after_six]):
            self.assertEqual(
                answers, [True] * 3,
                "%s does not ask for one more than the bar has just shown it "
                "can hold, so the ceiling cannot ratchet" % app)

    def test_a_stated_maximum_returns_the_take_to_the_ceiling(self):
        """The probing is over the moment the client answers, in both
        directions: a stated maximum above the setting and one below it."""
        for app, answers in self.each(
                ["maxTargetsRowsToTake %s == %d"
                 % (state(SHIPPED_DEFAULT, stated=CLIENT_MAXIMUM),
                    CLIENT_MAXIMUM),
                 "maxTargetsRowsToTake %s == 5" % state(8, stated=5),
                 "maxTargetsRowsToTake %s == %d"
                 % (state(SHIPPED_DEFAULT, stated=CLIENT_MAXIMUM,
                          held=CLIENT_MAXIMUM), CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s goes on asking for one more after the client has said how "
                "many there are, which is a lock it knows will be refused on "
                "every reading for the rest of the session" % app)


class TheProbeIsAnExtraRowAndNotAReRanking(BothAppsRepl, unittest.TestCase):
    """The first thing that can go wrong, and it would go wrong quietly.

    A probe that *replaced* a candidate would leave a real target unlocked to
    ask a question, on every engagement, and the log would read exactly the
    same. Taking one row more is what makes that impossible by construction:
    `List.take (n + 1)` extends `List.take n` rather than choosing differently,
    so the rows the ceiling covers keep their order and their places.
    """

    def test_the_rows_the_ceiling_covers_are_untouched_by_probing(self):
        """Compared against the take the same rule would make with probing off,
        rather than against a list written down here."""
        for app, answers in self.each(
                ["(taken %s |> List.take (maxTargetsCeiling %s))"
                 " == takenWithoutProbing %s" % (three, three, three)
                 for three in [state(setting) for setting in (0, 1, 2, 4, 6, 9)]]):
            self.assertEqual(
                answers, [True] * 6,
                "%s no longer takes the rows the ceiling covers first, so the "
                "probe can displace a target the bot would have locked" % app)

    def test_the_probe_is_the_one_row_past_them(self):
        for app, answers in self.each(
                ["(taken %s |> List.drop (maxTargetsCeiling %s)) == [ %d ]"
                 % (state(setting), state(setting), setting + 1)
                 for setting in (0, 1, 4, 6)]):
            self.assertEqual(
                answers, [True] * 4,
                "%s takes something other than exactly one extra row" % app)

    def test_no_probe_is_due_while_the_bar_is_below_the_ceiling(self):
        """The extra row is only ever *reached* once every row the ceiling
        covers is locked, and that is what the rule says as well as what the
        list does -- so the branch that clicks cannot pick the probe while a
        real candidate is waiting."""
        for app, answers in self.each(
                ["maxTargetsProbe %s == MaxTargetsProbeFillingSlots"
                 % probe(SHIPPED_DEFAULT, held_now, 5)
                 for held_now in (0, 1, 2, 3)]):
            self.assertEqual(
                answers, [True] * 4,
                "%s calls a lock a probe while the bar is still below the "
                "ceiling, so an ordinary target is being reported as a "
                "measurement" % app)

    def test_the_probe_is_due_exactly_at_the_ceiling_and_above(self):
        for app, answers in self.each(
                ["maxTargetsProbe %s == MaxTargetsProbeOneMore 5"
                 % probe(SHIPPED_DEFAULT, held_now, 1)
                 for held_now in (4, 5, 9)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s does not ask for one more once the bar is full, so a "
                "session that filled its believed ceiling learns nothing" % app)

    def test_the_lock_site_takes_the_rule_rather_than_the_ceiling(self):
        """Read out of the source, since a decision site is not an expression.

        A rule that answers correctly and is never asked is this repo's
        signature bug, and #34, #42 and #102 are three of it.
        """
        for app, path in APPS:
            source = collapsed(source_of(path))
            self.assertIn(
                "|> List.filter overviewEntryIsDisplayed"
                " |> List.take (maxTargetsRowsToTake (maxTargetsStateFrom context))"
                " |> List.filter (overviewEntryIsTargetedOrTargeting >> not)",
                source,
                "%s's lock site does not take the probing row count off the "
                "front of its own candidates, so either the rule is answered "
                "and never asked or something has been dropped ahead of the "
                "take and the probe is displacing a target" % app)
            self.assertNotIn(
                "List.take (maxTargetsCeiling (maxTargetsStateFrom context))",
                source,
                "%s still takes exactly the ceiling somewhere, which is the "
                "shape that cannot bootstrap" % app)

    def test_saxrats_lock_window_is_no_longer_a_second_hardcoded_ceiling(self):
        """saxrat took `4` rows of candidates, which is the shipped ceiling
        written out a second time -- so a client stating six left two slots
        unreachable however far the gate was raised."""
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "decideActionInAnomaly"))
        self.assertNotIn(
            "|> List.take 4 |> List.filter (overviewEntryIsTargetedOrTargeting",
            body,
            "saxrat still takes a hardcoded four rows of lock candidates, so "
            "the learned ceiling cannot reach past it")
        self.assertIn(
            "|> List.take (maxTargetsRowsToTake (maxTargetsStateFrom context))",
            body,
            "saxrat's candidate window is not the learned one")


class NothingToSpareMeansNoProbe(BothAppsRepl, unittest.TestCase):
    """A probe with nothing to attempt is not an attempt.

    The reading says so rather than counting one, which matters because the
    only thing that ends the probing is the client's statement: a reading that
    reported a probe it never made would be a reading claiming to have asked a
    question nobody answered.
    """

    def test_a_probe_with_no_row_to_spare_says_so(self):
        for app, answers in self.each(
                ["maxTargetsProbe %s == MaxTargetsProbeNothingToSpare 5"
                 % probe(SHIPPED_DEFAULT, 4, 0),
                 "maxTargetsProbe %s == MaxTargetsProbeOneMore 5"
                 % probe(SHIPPED_DEFAULT, 4, 1),
                 "maxTargetsProbe %s == MaxTargetsProbeOneMore 5"
                 % probe(SHIPPED_DEFAULT, 4, 7)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s counts a probe on a reading with no lockable row to spare, "
                "or declines one on a reading that has several" % app)

    def test_the_reading_says_it_rather_than_reporting_everything_locked(self):
        for app, repl in self.repls.items():
            said = repl.strings(
                ["describeMaxTargetsNothingToLock"
                 " (MaxTargetsProbeNothingToSpare 5) \"%s\"" % ORDINARY_LOCK_LINE,
                 "describeMaxTargetsNothingToLock"
                 " MaxTargetsProbeFillingSlots \"%s\"" % ORDINARY_LOCK_LINE],
                repl.with_helpers([]))
            self.assertIn("Nothing to spare for a probe", said[0], app)
            self.assertIn("5", said[0], app)
            self.assertTrue(said[0].startswith(ORDINARY_LOCK_LINE), app)
            self.assertEqual(
                said[1], ORDINARY_LOCK_LINE,
                "%s changed what it says on an ordinary reading with nothing "
                "left to lock, where nothing about #150 applies" % app)

    def test_the_branch_that_clicks_keeps_the_wording_it_always_had(self):
        """`Lock more targets.` on every reading nothing is being probed, so a
        grep an operator has been running since before any of this still
        answers."""
        for app, repl in self.repls.items():
            said = repl.strings(
                ["describeMaxTargetsProbe MaxTargetsProbeFillingSlots",
                 "describeMaxTargetsProbe (MaxTargetsProbeSettled 6)",
                 "describeMaxTargetsProbe (MaxTargetsProbeOneMore 5)"],
                repl.with_helpers([]))
            self.assertEqual(said[0], ORDINARY_LOCK_LINE, app)
            self.assertEqual(said[1], ORDINARY_LOCK_LINE, app)
            self.assertIn("Probing for lock slot 5", said[2], app)
            self.assertIn("4", said[2], app)

    def test_nothing_to_spare_yields_no_row_at_the_lock_site(self):
        """Read out of the source: the branch answers `Nothing` rather than
        falling back to the nearest candidate, which with the bar full at the
        believed ceiling would be a row out of lock range that the ship would
        fly at to measure something."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            self.assertIn(
                "MaxTargetsProbeOneMore _ -> overviewEntriesToLockInRange "
                "|> List.head MaxTargetsProbeNothingToSpare _ -> Nothing",
                source,
                "%s picks a row to probe with even where the rule says there "
                "is none to spare, or picks it from rows the ship cannot "
                "reach" % app)
            self.assertIn(
                "rowsToSpare = overviewEntriesToLockInRange |> List.length",
                source,
                "%s counts rows to spare from a different list than the one it "
                "would probe with, so the two can disagree" % app)
            self.assertIn(
                "overviewEntriesToLock |> List.filter "
                "(overviewEntryIsWithinLockRange context)", source,
                "%s no longer restricts the probe to rows the ship can lock "
                "from where it is, so a measurement can move the ship" % app)


class TheStatementIsWhatEndsTheProbing(BothAppsRepl, unittest.TestCase):
    """Stop on the evidence, not on a count.

    The client naming the number is the terminating evidence, and all 228
    recorded refusals name it. A count would stop the learning before the
    answer arrived, and what it would save is one lock click on a reading the
    bot was going to spend waiting anyway.
    """

    def test_the_statement_ends_it_whatever_the_bar_is_doing(self):
        for app, answers in self.each(
                ["maxTargetsProbe %s == MaxTargetsProbeSettled %d"
                 % (probe(SHIPPED_DEFAULT, held_now, spare,
                          stated=CLIENT_MAXIMUM), CLIENT_MAXIMUM)
                 for held_now, spare in ((0, 0), (6, 3), (9, 9))]):
            self.assertEqual(
                answers, [True] * 3,
                "%s goes on probing after the client has stated its maximum" % app)

    def test_the_statement_reaches_the_rule_within_one_reading(self):
        """The path the corpus says a session takes: the probe is refused, the
        client writes the sentence on the game log, and the reading that
        carries it is the reading probing stops on."""
        after = "step %s %s" % (reading(4, [("notify", STATED_SIX)]),
                                state(SHIPPED_DEFAULT))
        for app, answers in self.each(
                ["(%s).statedByClient == Just %d" % (after, CLIENT_MAXIMUM),
                 "maxTargetsRowsToTake (%s) == %d" % (after, CLIENT_MAXIMUM),
                 "maxTargetsProbe { state = %s, targetsHeld = 4, rowsToSpare = 3 }"
                 " == MaxTargetsProbeSettled %d" % (after, CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s does not stop probing on the reading that carries the "
                "client's own sentence" % app)

    def test_a_client_that_never_states_it_is_asked_again(self):
        """No count bounds this, deliberately. A session of readings on which
        the bar never rises and the client never speaks is still probing at the
        end of it, because nothing has answered the question.
        """
        for app, answers in self.each(
                ["maxTargetsRowsToTake (silentSession %d %d) == %d"
                 % (count, SHIPPED_DEFAULT, SHIPPED_DEFAULT + 1)
                 for count in (1, 8, 40, 200)]):
            self.assertEqual(
                answers, [True] * 4,
                "%s stops asking after some number of readings, which is a "
                "bound with no evidence behind it that ends the learning "
                "before the answer arrives" % app)

    def test_the_status_line_says_it_is_probing_and_for_what(self):
        """`probing for N` is present exactly while `client stated` is `-`, so
        the two clauses cannot disagree about whether the question is still
        open."""
        for app, repl in self.repls.items():
            said = repl.strings(
                ["describeMaxTargets %s" % state(SHIPPED_DEFAULT),
                 "describeMaxTargets %s"
                 % state(SHIPPED_DEFAULT, held=CLIENT_MAXIMUM),
                 "describeMaxTargets %s"
                 % state(SHIPPED_DEFAULT, stated=CLIENT_MAXIMUM, held=5)],
                repl.with_helpers([]))
            self.assertEqual(said, list(MAX_TARGETS_CLAUSES[app]), app)


class ARefusedProbeIsNotAStuckLock(unittest.TestCase):
    """The lock-range machinery, asked what a declined lock costs it.

    `lockAttempt` bounds a lock the client *accepted* and never finished. A
    lock the client declines is a different outcome and must not spend that
    budget: the refusal test needs the target bar empty at both ends of the
    attempt, so an attempt begun with a target already held can never move
    either bound however long it is carried -- it fails that condition rather
    than the wait.

    Run 37 is what carrying it cost, live: the bot clicked, the client answered
    `You are already managing 6 targets` on the next reading, and the attempt
    climbed to the verdict count and latched there for nineteen readings of an
    operator's status line reporting a lock that had not landed. Every probe is
    by definition asked with the bar at the ceiling, so this is what keeps the
    probe out of that machinery entirely.

    Folded through saxrat's own `updateLockRangeLearning`, which is a function
    of records and so can be run for real; the mission runner's copy takes a
    whole `UpdateMemoryContext`, so the branch is compared against saxrat's as
    source instead.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(LockRangeRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    ROW = [("60,000 m", "Centior Monster", "111", False)]

    def definitions(self, extra=()):
        """Whole readings, each carrying an overview *and* a ship UI.

        The ship UI is not decoration: `shipCannotLock` is one of the rule's
        own judgements, so a fixture without one would send every case below
        through the "the ship could not have locked anything" branch and assert
        nothing about a declined lock at all.
        """
        return self.repl.with_helpers([
            SaxratRepl.reading_binding(
                "waiting", [overview_rows(self.ROW), flying()]),
        ] + list(extra))

    def click(self, targets):
        x, y = row_center(0)
        return "lockReading waiting %d (lockClickAt %d %d)" % (targets, x, y)

    def idle(self, targets):
        return "lockReading waiting %d []" % targets

    def fold(self, readings, start="noEvidence"):
        folded = start
        for one in readings:
            folded = "step (%s) (%s)" % (one, folded)
        return folded

    def test_an_attempt_made_with_the_bar_occupied_can_teach_nothing(self):
        """The rule the discharge rests on, over the record itself."""
        def attempt(targets):
            return ("{ handle = \"111\", distanceInMeters = 60000"
                    ", targetsCount = %d, readingsWaited = 0 }" % targets)

        answers = self.repl.evaluate(
            ["lockAttemptCanTeachRange %s" % attempt(0),
             "not (lockAttemptCanTeachRange %s)" % attempt(1),
             "not (lockAttemptCanTeachRange %s)" % attempt(4),
             "not (lockAttemptCanTeachRange %s)" % attempt(6)],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "a lock asked for with the target bar already occupied is being "
            "treated as one that could still teach a range, which is the wait "
            "run 37 spent 8 readings of status line on")

    def test_a_declined_probe_spends_none_of_the_lock_attempt_budget(self):
        """The bar holds four, the click is the probe, the row never reads
        targeted -- and the attempt is gone on the very next reading rather
        than carried to the verdict count."""
        one_reading = self.fold([self.click(4)])
        many = self.fold([self.click(4)] + [self.idle(4)] * 12)
        answers = self.repl.evaluate(
            ["(%s).attempt == Nothing" % one_reading,
             "(%s).attempt == Nothing" % many,
             "(%s).refusedAtMeters == Nothing" % many,
             "(%s).provenAtMeters == Nothing" % many,
             "changeOf (%s) (%s) == Nothing" % (self.idle(4), many)],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 5,
            "a lock the client declined with the bar full is still being "
            "waited on, so a probe spends the give-up's budget and shows in "
            "the status line as a lock that has not landed")

    def test_the_give_up_can_never_see_a_probe(self):
        """`lockAttemptIsSpent` compares `readingsWaited` against the verdict
        count, and a discharged attempt is not there to be compared. Asserted
        as the count never rising rather than as the branch not firing, since
        the branch takes a whole decision context."""
        answers = self.repl.evaluate(
            ["((%s).attempt |> Maybe.map .readingsWaited"
             " |> Maybe.withDefault 0) == 0"
             % self.fold([self.click(4)] + [self.idle(4)] * count)
             for count in (0, 1, 8, 20)],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 4,
            "a probe's attempt accumulates readings, so it can reach the "
            "verdict count and trip a give-up written for a lock the client "
            "accepted and never finished")

    def test_a_lock_with_an_empty_bar_is_judged_exactly_as_before(self):
        """The neighbouring rule this must not weaken. With the bar empty at
        both ends the attempt is still carried to the verdict count and still
        teaches a refusal there, one reading either side."""
        short = self.fold([self.click(0)] + [self.idle(0)] * 7)
        full = self.fold([self.click(0)] + [self.idle(0)] * 8)
        answers = self.repl.evaluate(
            ["(%s).refusedAtMeters == Nothing" % short,
             "(%s).attempt /= Nothing" % short,
             "(%s).refusedAtMeters == Just 60000" % full],
            definitions=self.definitions())
        self.assertEqual(
            answers, [True] * 3,
            "the lock range no longer learns a refusal from an attempt with "
            "the target bar empty throughout, which is the case #134 built "
            "this for")

    def test_a_lock_that_lands_is_still_credited_with_the_bar_occupied(self):
        """The discharge is about a lock the client did not take. One it *did*
        take is still the proven bound's evidence, whatever the bar held."""
        landed = self.fold([
            "lockReading locked 4 (lockClickAt %d %d)" % row_center(0)])
        answers = self.repl.evaluate(
            ["(%s).provenAtMeters == Just 60000" % landed],
            definitions=self.definitions([SaxratRepl.reading_binding(
                "locked",
                [overview_rows([("60,000 m", "Centior Monster", "111", True)]),
                 flying()])]))
        self.assertEqual(
            answers, [True],
            "a lock the client accepted while the ship held targets is no "
            "longer evidence about range, which throws away the furthest "
            "locks a session makes")

    def test_both_apps_discharge_it_in_the_same_place(self):
        """The mission runner's copy of the rule takes a whole
        `UpdateMemoryContext` and cannot be executed, so it is read: the branch
        has to be there, and it has to come before the wait it replaces."""
        for app, path in APPS:
            body = collapsed(body_of(source_of(path), "updateLockRangeLearning"))
            self.assertIn(
                "else if not (lockAttemptCanTeachRange attempt) then",
                body,
                "%s does not discharge a lock the client declined with the bar "
                "occupied, so a refused probe spends the give-up's budget" % app)
            self.assertLess(
                body.index("lockAttemptCanTeachRange"),
                body.index("attempt.readingsWaited < "
                           "lockAttemptReadingsBeforeVerdict"),
                "%s asks the wait before the discharge, so the attempt is "
                "carried to the verdict count anyway" % app)
            self.assertIn(
                "(attempt.targetsCount /= 0) || (targetsCount /= 0)", body,
                "%s no longer requires an empty target bar at both ends of an "
                "attempt before learning a refusal, which is the condition "
                "that separates 'too far' from 'no free slot'" % app)


class TheRowIdentityDisciplineIsStillUntouched(unittest.TestCase):
    """PR #149's finding, which #150 spends nothing of.

    The lock range needs `overviewEntryLockHandle` because it attributes a lock
    *outcome* to an *object*, and in an anomaly of identically named rats it
    correctly yields no evidence at all. The probe attributes nothing: it is a
    function of two counts and a state, and what it decides is how many rows to
    take rather than which. The case exists so that a later version reaching
    for a row has to notice it is taking on a problem this one does not have.
    """

    def test_the_probe_reaches_for_no_overview_row(self):
        for app, path in APPS:
            source = source_of(path)
            for name in ("maxTargetsRowsToTake", "maxTargetsProbe",
                         "describeMaxTargetsProbe",
                         "describeMaxTargetsNothingToLock"):
                body = body_of(source, name)
                for reached in ("overviewEntryLockHandle", "objectItemID",
                                "overviewWindows", "objectName"):
                    self.assertNotIn(
                        reached, body,
                        "%s: %s reaches for an overview row, so the ceiling is "
                        "now only as good as the row-identity rule -- which in "
                        "an anomaly of identically named rats yields no "
                        "evidence at all" % (app, name))

    def test_the_probe_row_is_taken_in_order_rather_than_chosen(self):
        """No sort and no re-ranking anywhere near the probe: the candidate
        list keeps whatever order the selection gave it, and both the rows the
        ceiling covers and the extra one come off the front of it."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            start = source.find(
                "nextOverviewEntryToLockOrProbe : Maybe OverviewWindowEntry")
            self.assertNotEqual(
                start, -1, "%s has no probe-aware lock-site selection" % app)
            selection = source[start:start + 400]
            self.assertIn("MaxTargetsProbeOneMore", selection, app)
            self.assertNotIn("List.sort", selection, app)
            self.assertNotIn("List.reverse", selection, app)

    def test_the_same_name_exclusion_is_still_the_shipped_one(self):
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "overviewEntryLockHandle"))
        self.assertIn(
            "|> List.length) == 1", body,
            "the same-name exclusion has been loosened from 'no other row "
            "shares it', which is the one change the lock-range rule must not "
            "take")


class BothAppsCarryTheSameRule(unittest.TestCase):
    """Compared byte for byte, the way #123's and #149's rules are.

    The two apps meet the same client and the same sentence, so a fix that
    lands in one copy while the other silently lacks it is its own bug -- and
    the failure is quiet, since a bot that never probes reads exactly like a
    client that granted nothing.
    """

    def test_every_shared_declaration_is_identical(self):
        saxrat = source_of(SAXRAT_BOT_ELM)
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        for name in SHARED_DECLARATIONS:
            self.assertEqual(
                body_of(saxrat, name), body_of(mission, name),
                "%s has drifted between the two apps" % name)
        for name in SHARED_TYPES:
            self.assertEqual(
                type_declaration(saxrat, name),
                type_declaration(mission, name),
                "the type %s has drifted between the two apps" % name)

    def test_saxrats_enough_locked_gate_asks_the_same_rule_as_the_take(self):
        """saxrat is the app that *says* it has enough, and if that gate stayed
        on the raw ceiling it would answer "enough" on the very reading the
        take had made room for a probe -- so the probe would never be clicked
        and the log would say the bot was satisfied."""
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "decideActionInAnomaly"))
        self.assertIn(
            "if maxTargetsRowsToTake (maxTargetsStateFrom context) <= "
            "(context.readingFromGameClient.targets |> List.length) then",
            body,
            "saxrat's 'Enough locked targets.' gate is not the rule the lock "
            "site takes, so the two can disagree about whether there is room")

    def test_the_setting_is_still_read_only_where_the_state_is_assembled(self):
        """One reader per app on the decision side and one on the memory side.
        Two places asking the setting directly would be two opinions about the
        ceiling, which is how `weaponModuleButtonsLeftToRight` came to exist.
        """
        for app, path in APPS:
            source = source_of(path)
            reads = re.findall(r"botSettings\.maxTargetCount", source)
            self.assertEqual(
                len(reads), 2,
                "%s reads max-targets from %d places rather than the two that "
                "assemble the state" % (app, len(reads)))
            self.assertIn(
                "updateMaxTargetsLearning (maxTargetsReadingFrom context) "
                "(maxTargetsStateBefore context botMemoryBefore)",
                collapsed(source),
                "%s's memory update assembles the state before this reading "
                "some other way, so the lock range and the ceiling can "
                "disagree about what the bot believed" % app)


class WhatTheRecordedRunsSayAboutARefusedLock(unittest.TestCase):
    """The corpus, asked what a lock the client declines actually costs.

    Asserted as *relations* rather than as counts, so a corpus that grows
    cannot turn a true claim red.
    """

    STATED = re.compile(
        r"\(notify\) You are already managing (\d+) targets, "
        r"as many as you have skill to\.")
    CLICKED = "Lock target from overview entry"
    STOOD_DOWN = "standing down: someone used the mouse"
    # How far back a click counts as the one the client is answering. The
    # framework prints about a dozen decision lines per reading, so this is a
    # couple of readings rather than a couple of decisions.
    LOOKBACK_LINES = 40

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(EVE_BOT_LOGS):
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what a lock the client "
                "declines costs cannot be measured here")
        logs = sorted(name for name in os.listdir(EVE_BOT_LOGS)
                      if name.endswith(".log"))
        if not logs:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what a lock the client "
                "declines costs cannot be measured here")

        cls.latched_at_the_verdict = 0
        cls.gave_up_waiting = 0
        cls.statements = 0
        cls.statements_the_bot_provoked = 0
        verdict = re.compile(r"attempt \d+ m for (\d+) readings")
        for name in logs:
            with open(os.path.join(EVE_BOT_LOGS, name),
                      encoding="utf-8", errors="replace") as handle:
                recent = []
                for line in handle:
                    for waited in verdict.findall(line):
                        if int(waited) >= cls.verdict_count():
                            cls.latched_at_the_verdict += 1
                    if "stop waiting for it" in line:
                        cls.gave_up_waiting += 1
                    if cls.STATED.search(line):
                        cls.statements += 1
                        window = recent[-cls.LOOKBACK_LINES:]
                        if any(cls.CLICKED in earlier for earlier in window) \
                                and not any(cls.STOOD_DOWN in earlier
                                            for earlier in window):
                            cls.statements_the_bot_provoked += 1
                    recent.append(line)
                    if len(recent) > cls.LOOKBACK_LINES:
                        del recent[0]

    @staticmethod
    def verdict_count():
        """`lockAttemptReadingsBeforeVerdict`, read out of the source rather
        than written down here."""
        match = re.search(
            r"lockAttemptReadingsBeforeVerdict : Int\s*\n"
            r"lockAttemptReadingsBeforeVerdict =\s*\n\s*(\d+)",
            source_of(SAXRAT_BOT_ELM))
        assert match, "the verdict count is no longer a plain literal"
        return int(match.group(1))

    def test_a_declined_lock_latches_at_the_verdict_and_is_never_given_up_on(self):
        """What the wait costs, and why the give-up was never the answer to it.

        `lockAttemptIsSpent` is only asked of a row that reads `targeting`, and
        a lock the client declines never does -- so the attempt runs to the
        verdict count, latches there, and the branch that would stop waiting
        for it is unreachable. That is the budget #150's probe must not spend.
        """
        self.assertGreater(
            self.latched_at_the_verdict, 0,
            "no recorded run ever carried a lock attempt as far as the verdict "
            "count, so there is nothing here about what waiting one out costs")
        self.assertEqual(
            self.gave_up_waiting, 0,
            "a recorded run gave up waiting for a lock after all, so the "
            "give-up is reachable and this file should be asking the corpus "
            "what it did rather than asserting it never fired")

    def test_the_bot_provokes_the_statement_with_its_own_clicks(self):
        """The issue says every recorded refusal was hand-fed, and the newest
        run says otherwise: `mission_run37.log` carries the statement on a
        reading whose preceding decisions are the bot's own lock clicks, with
        no human input note anywhere in the window. So the sentence is one a
        click provokes and it arrives within a reading or two -- which is what
        makes a probe a measurement rather than a hope.
        """
        self.assertGreater(
            self.statements, 0,
            "no recorded run carries the client's statement of its target "
            "maximum, so nothing here says what provokes it")
        self.assertGreater(
            self.statements_the_bot_provoked, 0,
            "every recorded statement follows either a human at the keyboard "
            "or no lock click at all, so the corpus does not show the bot's "
            "own click provoking it and the probe's premise is unsupported")


if __name__ == "__main__":
    unittest.main()
