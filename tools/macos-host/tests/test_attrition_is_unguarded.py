"""The retreat's three guards are not symmetric, and one shape has no cover.

Issue #129. `run-away-incoming-damage-threshold` bounds a **burst**. Run 36 was
ground down from 95% to 17% believed armour over about 53 seconds while that
window peaked at 1854 against 3500 -- its highest reading of the whole run --
and read 602 at the moment the armour gauge showed 1%. The ship survived because
the armour *percentage* guard fired. Nothing else was ever going to.

PR #120 established that the gauge-free guard must stay gauge-free, so that a
corrupt HUD costs two guards and leaves the third armed. What #129 adds is the
other direction, which had never been written down: against attrition the
gauge-based guard is the *only* cover and the gauge-free one is inert. So the
independence is real and asymmetric.

**No new guard is added and the retreat is untouched.** The honest reading of the
corpus is that the armour percentage guard already is the attrition guard, and
that no gauge-free instrument could be one -- the combat log reports *gross*
incoming damage while survival is governed by *net*, and this hull's armour
repairer is of the same order as the fire it was under. What ships instead is
`attritionIsUnguarded`, a pure rule read by the status line and by no decision,
which says on every reading when the configuration leaves that shape uncovered.

Five things this file establishes, all against recorded data rather than
invented numbers:

**The rule is executed, not restated.** `attritionIsUnguarded` runs through the
real `Bot.elm` in `elm repl`, at both sides of each threshold's boundary and
against fixed values either side of it, so a rule admitting everything cannot
pass -- that is the hole four of PR #120's own cases had.

**The retreat did not change.** `runAwayIfLowHealth`'s three conditions and the
gauge-free comparison behind the damage guard are read out of the source, so a
mutation that makes the gauge-free guard read a gauge fails here.

**Nothing decides on it.** `attritionIsUnguarded` is reachable from the status
line and from nowhere else.

**The damage guard has never fired.** Across every recorded mission run the
retreat has fired on the armour percentage and on the shield percentage, and not
once on the damage window or on the frozen reading.

**The shield is a fuse on this hull**, which is what makes the settings advice
this change corrects load-bearing: in every recorded run whose shield fell at
all it collapsed while the armour still read near 100%, and stayed collapsed.

The corpus is asserted as *relations* rather than as the numbers above, so a
growing corpus cannot turn a true claim red. Cases that execute Elm need the
toolchain and **fail** without it; cases that read `~/eve-bot-logs` skip when it
is absent, for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

LOG_GLOB = os.path.expanduser("~/eve-bot-logs/mission_run*.log")

# The pair `run_mission.sh` ships: the armour guard armed, the shield one off
# because this hull's shield rests at zero. Asserted against the launcher below
# rather than assumed here.
LAUNCHER_ARMOR_THRESHOLD = 70
LAUNCHER_SHIELD_THRESHOLD = -1

# `runAwayRearmPercent`, so the replayed low-water mark is the bot's own.
REARM_PERCENT = 90

# How many consecutive readings a decline must hold before it is a decline
# rather than a corrupt gauge. The `believed` rule filters a one-reading
# excursion by construction; what it cannot filter is a two-reading one, and
# CLAUDE.md records the longest anywhere -- run 10's shield `84, 14, 17, 84`,
# run 11's `96, 7, 7, 96`, run 14's armour holding 0 for three. Four is one
# past that, and is not a threshold anything acts on: it separates the corpus
# for the purpose of measuring it here.
SUSTAINED_READINGS = 4

# The retreat's decision lines, one per guard. The two damage-based ones have
# never appeared in any recorded run; the two percentage ones have.
GUARD_LINES = {
    "armor": re.compile(r"^\++ Armor reached "),
    "shield": re.compile(r"^\++ Shield reached "),
    "damage": re.compile(r"^\++ The client's combat log says we are taking "),
    "frozen": re.compile(r"^\++ We have absorbed "),
}

TICK = re.compile(r"^# \[(\d+)\.(\d+)\]")
STATUS = re.compile(
    r"^Shield: (-?\d+)%\s+Armor: (-?\d+)%.*?\bdmg (\d+)/(-?\d+) \((\d+)s, (\d+)rd\)")


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(source):
    """The source with runs of whitespace collapsed, for reading structure.

    `elm-format` moves line breaks around inside an expression, and #58 broke
    three cases that had matched the old layout. Nothing here matches a newline.
    """
    return re.sub(r"\s+", " ", source)


def definition_body(source, name):
    """A top-level definition's body, from its `=` to the next top-level form."""
    start = re.search(r"^" + re.escape(name) + r"\b[^\n]*=\n", source, re.M)
    assert start is not None, "no definition of %s in Bot.elm" % name
    rest = source[start.end():]
    end = re.search(r"\n\n\n", rest)
    return rest[:end.start()] if end else rest


def definitions_mentioning(source, name):
    """Every top-level definition whose *code* names `name`.

    Doc comments are stripped first, because several of them refer to the rule
    on purpose -- that is the argument being written down, and a case that
    counted those would forbid explaining the thing it is pinning.
    `elm-format` puts two blank lines between top-level forms, which is what
    splits them.
    """
    code = re.sub(r"\{-.*?-\}", "", source, flags=re.S)
    found = []
    for chunk in re.split(r"\n\n\n+", code):
        if name not in chunk:
            continue
        first = re.match(r"\s*(\w+)", chunk)
        if first is not None:
            found.append(first.group(1))
    return sorted(set(found))


def readings_from_log(path):
    """One (shield, armour, window, threshold) per *reading*, in order.

    `# [1298.3]` is reading 1298, sub-step 3, and the status line goes out once
    per sub-step -- so the integer part is what identifies a reading. Collapsing
    on the whole line instead merges a corrupt gauge excursion into one entry
    and makes a three-sub-step corruption look like three readings, which is how
    a first pass at this measurement found ten runs at 0% armour that are not
    there.
    """
    rows, reading = [], None
    with open(path, encoding="utf-8", errors="replace") as log:
        for line in log:
            if not line.endswith("\n"):
                # The last line of a run still being appended to.
                continue
            tick = TICK.match(line)
            if tick:
                reading = int(tick.group(1))
                continue
            status = STATUS.match(line)
            if status is None or reading is None:
                continue
            if rows and rows[-1][0] == reading:
                continue
            rows.append((reading, int(status.group(1)), int(status.group(2)),
                         int(status.group(3)), int(status.group(4))))
    return rows


def believed(values):
    """`HitpointsMemory`'s rule, for reading recorded logs only.

    The healthier of this reading and the one before, with a value outside
    [0, 100] rejected the way `plausibleHitpointsPercent` rejects it. The rules
    under test are executed through the repl; this reconstructs what the bot
    believed at each recorded reading so a claim can be made about a run.
    """
    out, previous = [], None
    for value in values:
        plausible = value if 0 <= value <= 100 else None
        if plausible is None:
            out.append(None)
            continue
        out.append(plausible if previous is None else max(plausible, previous))
        previous = plausible
    return out


def low_water(believed_values):
    """`lowWaterMark` folded over a run: the mark after each reading."""
    out, mark = [], 100
    for value in believed_values:
        if value is not None:
            mark = 100 if REARM_PERCENT <= value else min(mark, value)
        out.append(mark)
    return out


def guard_firings(path):
    counts = dict.fromkeys(GUARD_LINES, 0)
    with open(path, encoding="utf-8", errors="replace") as log:
        for line in log:
            for guard, pattern in GUARD_LINES.items():
                if pattern.match(line):
                    counts[guard] += 1
    return counts


def every_recorded_run():
    runs = sorted(glob.glob(LOG_GLOB))
    if not runs:
        raise unittest.SkipTest(
            "no mission_run*.log in ~/eve-bot-logs, so the recorded runs "
            "cannot be consulted here")
    return runs


class CoverCaseRepl(ElmRepl):
    """The shared harness, plus one builder for the rule's own record.

    A preamble rather than a definition per case, so a case's assertions line up
    with what it asked rather than with what it had to set up first.
    """

    BINDINGS = [
        "unguarded shield armor = attritionIsUnguarded"
        " { shieldThresholdPercent = shield, armorThresholdPercent = armor }",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preamble = self.preamble + self.BINDINGS


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """`attritionIsUnguarded`, run through the bot's own compiled code."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(CoverCaseRepl, prefix="test-attrition-cover-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_thresholds_disabled_leaves_attrition_uncovered(self):
        # The default settings, and the headline: with both percentage guards
        # off, the damage window and the frozen-reading check are all that is
        # armed and neither can see a grind.
        answers = self.repl.evaluate([
            "unguarded -1 -1",
            "unguarded -1 %d" % LAUNCHER_ARMOR_THRESHOLD,
            "unguarded %d -1" % 25,
            "unguarded 25 %d" % LAUNCHER_ARMOR_THRESHOLD,
        ])
        self.assertEqual(answers[0], True,
                         "both thresholds disabled must report attrition uncovered")
        self.assertEqual(answers[1], False,
                         "the launcher's armour threshold is cover against attrition")
        self.assertEqual(answers[2], False,
                         "a shield threshold is cover too, on a hull it suits")
        self.assertEqual(answers[3], False,
                         "both armed is covered")

    def test_the_armour_threshold_is_cover_from_one_and_not_from_zero(self):
        # The bound is read off `runAwayIfLowHealth`'s own `lowestArmor <
        # threshold`: a low-water mark never goes below 0, so 0 is as inert as
        # -1 while looking configured. The fixed values either side of the pair
        # are what stops a rule admitting everything -- or nothing -- from
        # passing on the boundary alone.
        answers = self.repl.evaluate([
            "unguarded -1 0",
            "unguarded -1 1",
            "unguarded -1 -5",
            "unguarded -1 100",
        ])
        self.assertEqual(answers[0], True,
                         "an armour threshold of 0 can never fire, so it is not cover")
        self.assertEqual(answers[1], False,
                         "an armour threshold of 1 can fire, so it is cover")
        self.assertEqual(answers[2], True, "a negative threshold is disabled")
        self.assertEqual(answers[3], False, "100 is armed and is cover")

    def test_the_shield_threshold_is_cover_from_one_and_not_from_zero(self):
        # The same bound on the other gauge, because there is nothing about the
        # shield the armour does not also do -- which gauge suits a hull is a
        # separate question this rule deliberately does not answer.
        answers = self.repl.evaluate([
            "unguarded 0 -1",
            "unguarded 1 -1",
            "unguarded -5 -1",
            "unguarded 100 -1",
        ])
        self.assertEqual(answers[0], True,
                         "a shield threshold of 0 can never fire, so it is not cover")
        self.assertEqual(answers[1], False,
                         "a shield threshold of 1 can fire, so it is cover")
        self.assertEqual(answers[2], True, "a negative threshold is disabled")
        self.assertEqual(answers[3], False, "100 is armed and is cover")

    def test_either_threshold_alone_is_enough(self):
        # Stated as its own case because the two obvious mutations -- `||` for
        # `&&`, and either clause dropped -- are each caught by exactly one of
        # these four and by none of the boundary pairs above.
        answers = self.repl.evaluate([
            "unguarded -1 70",
            "unguarded 70 -1",
            "unguarded -1 -1",
            "unguarded 70 70",
        ])
        self.assertEqual(answers, [False, False, True, False])

    def test_the_damage_threshold_is_not_an_input(self):
        # The record has exactly the two percentage thresholds in it. Counting
        # `run-away-incoming-damage-threshold` as cover against attrition is the
        # mistake #129 was filed on, and a rule that consulted it could not
        # answer this record at all.
        answers = self.repl.evaluate([
            "unguarded -1 -1",
            "attritionIsUnguarded { shieldThresholdPercent = -1"
            ", armorThresholdPercent = -1 } == True",
        ])
        self.assertEqual(answers, [True, True])


class TheRetreatItselfIsUnchanged(unittest.TestCase):
    """PR #120's two properties, re-asserted because this change is next to them.

    Read out of the source through a whitespace-collapsing reader, so the next
    `elm-format` pass cannot break them the way #58's broke three others.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()
        cls.flat = collapsed(cls.source)

    def test_the_retreat_still_has_exactly_its_three_guards(self):
        body = collapsed(definition_body(self.source, "runAwayIfLowHealth"))
        self.assertIn("if lowestShield < runAwayShieldThreshold then", body)
        self.assertIn("else if lowestArmor < runAwayArmorThreshold then", body)
        self.assertIn("else if context.memory.incomingDamage.retreating then", body)
        self.assertIn(
            "damageThatMustMoveTheHitpointsReading <= damageInWindow", body)

    def test_the_gauge_free_guard_does_not_read_a_gauge(self):
        """The property #120 calls non-negotiable, in the two places it lives.

        The live comparison is a latch set from the combat-log window, and the
        threshold it was set against is a function of the setting and the
        session's ship-scale memory only. A mutation that lets either one reach
        `shipUI.hitpointsPercent` or a `believed` value fails here.
        """
        threshold = collapsed(
            definition_body(self.source, "incomingDamageThresholdForThisShip"))
        self.assertIn("scaledRunAwayIncomingDamageThreshold", threshold)
        for gauge in ("hitpointsPercent", "believed", "lowestArmorPercentSinceHealthy",
                      "lowestShieldPercentSinceHealthy", "attritionIsUnguarded"):
            self.assertNotIn(
                gauge, threshold,
                "the gauge-free threshold must not read %s" % gauge)

        # The latch does read the gauges, to file each sample's `hitpoints` for
        # the frozen-reading guard -- that is the third guard's whole input. What
        # must stay gauge-free is the verdict, so the assertion is on the
        # `retreating` expression itself rather than on the function around it.
        latch = collapsed(definition_body(self.source, "updateIncomingDamageMemory"))
        verdict = latch[latch.index("{ updated | retreating ="):]
        self.assertIn("damageInWindow", verdict)
        self.assertIn("threshold", verdict)
        for gauge in ("hitpointsPercent", "believed", "hitpointsNow",
                      "lowestArmorPercentSinceHealthy",
                      "lowestShieldPercentSinceHealthy"):
            self.assertNotIn(
                gauge, verdict,
                "the damage latch's verdict must not be a function of %s" % gauge)

    def test_the_retreat_does_not_consult_the_new_rule(self):
        """Nothing on the retreat path may decide on `attritionIsUnguarded`.

        It is a report. A retreat that read it would be a fourth guard
        calibrated on one incident, which is what this change deliberately does
        not ship.
        """
        body = collapsed(definition_body(self.source, "runAwayIfLowHealth"))
        self.assertNotIn("attritionIsUnguarded", body)

    def test_the_new_rule_is_read_by_the_status_line_and_by_nothing_else(self):
        # The definition itself is one of them; every other reader must be the
        # status-line clause.
        self.assertEqual(
            definitions_mentioning(self.source, "attritionIsUnguarded"),
            ["attritionIsUnguarded", "describeRetreatCover"],
            "attritionIsUnguarded gained a reader outside the status line")
        self.assertIn("++ describeRetreatCover context", self.flat,
                      "the status line no longer carries the clause")

    def test_the_rule_reads_no_gauge_of_its_own(self):
        """It answers from the settings, not from this reading.

        A report that waits until the armour is already down arrives too late to
        act on -- what an operator does about it is set a threshold. It is also
        what keeps a corrupt gauge from suppressing the warning.
        """
        body = collapsed(definition_body(self.source, "attritionIsUnguarded"))
        for gauge in ("hitpointsPercent", "believed", "incomingDamage",
                      "lowestArmorPercentSinceHealthy",
                      "lowestShieldPercentSinceHealthy"):
            self.assertNotIn(gauge, body,
                             "attritionIsUnguarded must not consult %s" % gauge)

    def test_the_status_clause_names_the_setting_to_change(self):
        body = collapsed(definition_body(self.source, "describeRetreatCover"))
        self.assertIn("ATTRITION UNGUARDED", body)
        self.assertIn("run-away-armor-hitpoints-threshold-percent", body)
        self.assertIn("lowestArmorPercentSinceHealthy", body)
        self.assertIn("lowestShieldPercentSinceHealthy", body)

    def test_the_launcher_still_ships_cover_against_attrition(self):
        """The armour threshold is what saved run 36, so it may not quietly go.

        Asserted through the rule rather than against a number, so the launcher
        may change which gauge it arms without this case having an opinion.
        """
        with open(os.path.join(MACOS_HOST_DIR, "run_mission.sh"),
                  encoding="utf-8") as handle:
            launcher = handle.read()

        def threshold(name):
            match = re.search(rf'^run-away-{name}=(-?\d+)"?$', launcher, re.MULTILINE)
            self.assertIsNotNone(match, f"{name} missing from the launcher defaults")
            return int(match.group(1))

        shield = threshold("shield-hitpoints-threshold-percent")
        armor = threshold("armor-hitpoints-threshold-percent")
        self.assertTrue(
            shield > 0 or armor > 0,
            "the launcher ships no percentage threshold, so nothing it starts "
            "can see the ship being ground down: shield=%d armor=%d"
            % (shield, armor))
        self.assertEqual(armor, LAUNCHER_ARMOR_THRESHOLD)
        self.assertEqual(shield, LAUNCHER_SHIELD_THRESHOLD)


class WhatTheRecordedRunsSay(unittest.TestCase):
    """The corpus, as relations rather than as the numbers in the doc comment."""

    def test_no_recorded_run_has_ever_retreated_on_the_damage_window(self):
        """The asymmetry in one measurement.

        Every retreat this bot has ever made came from a HUD gauge. That is not
        a claim the gauge-free guard is useless -- it is calibrated to a burst
        nothing recorded has produced, and the session that did produce one
        predates this channel. It is the reason attrition needs a percentage
        threshold and cannot be left to the damage window.
        """
        totals = dict.fromkeys(GUARD_LINES, 0)
        for path in every_recorded_run():
            for guard, count in guard_firings(path).items():
                totals[guard] += count

        self.assertGreater(
            totals["armor"], 0,
            "no recorded run retreats on the armour gauge at all; the corpus "
            "or the decision wording has changed")
        self.assertEqual(
            totals["damage"], 0,
            "a recorded run now retreats on the damage window (%d times) -- the "
            "burst guard has fired for the first time, and #129's premise that "
            "it never has is what needs re-reading" % totals["damage"])
        self.assertEqual(
            totals["frozen"], 0,
            "a recorded run now retreats on a frozen reading (%d times)"
            % totals["frozen"])

    def test_run_36_is_the_deepest_sustained_decline_in_the_corpus(self):
        """How rare the shape is, which #129 lists as unmeasured.

        **The raw minimum is the wrong statistic and gets this badly wrong.**
        Taken that way the corpus shows nine runs reaching 0-11% armour and run
        36 looks ordinary. Every one of those is a gauge corruption two to four
        readings wide, bracketed by 91-100% either side -- the case
        `HitpointsMemory` says the two-reading rule cannot filter, and the case
        CLAUDE.md records as run 10's `84, 14, 17, 84`.

        What separates them is duration, so the statistic is the deepest level
        the believed armour was held at or below for `SUSTAINED_READINGS`
        consecutive readings. That is one reading past the longest corruption
        anywhere in the corpus, and it collapses the nine to nothing while
        leaving run 36 where it is.
        """
        held = {}
        worst_reading = {}
        for path in every_recorded_run():
            rows = readings_from_log(path)
            armour = [(row, value)
                      for row, value in zip(rows, believed([r[2] for r in rows]))
                      if value is not None]
            if len(armour) < SUSTAINED_READINGS + 20:
                continue
            windows = [armour[i:i + SUSTAINED_READINGS]
                       for i in range(len(armour) - SUSTAINED_READINGS + 1)]
            deepest = min(windows, key=lambda window: max(v for _, v in window))
            name = os.path.basename(path)
            held[name] = max(value for _, value in deepest)
            worst_reading[name] = min(deepest, key=lambda pair: pair[1])[0]
        if not held:
            self.skipTest("no recorded run carries the damage-window status line")
        if "mission_run36.log" not in held:
            self.skipTest("mission_run36.log is not on this machine")

        others = {name: value for name, value in held.items()
                  if name != "mission_run36.log"}
        self.assertTrue(
            all(held["mission_run36.log"] < value for value in others.values()),
            "run 36 is no longer the deepest sustained armour decline recorded: "
            "%s" % sorted(held.items(), key=lambda pair: pair[1])[:4])

        # And it was ground down while the guard that is supposed to notice a
        # ship being taken apart sat at a fraction of its threshold.
        _, _, _, window, threshold = worst_reading["mission_run36.log"]
        self.assertGreater(threshold, 0, "run 36 flew with the damage guard armed")
        self.assertLess(
            window * 2, threshold,
            "at run 36's worst sustained armour reading the damage window was "
            "%d of %d -- not the fraction of the threshold #129 was filed on"
            % (window, threshold))

    def test_the_zeroes_in_the_corpus_are_corruptions_and_not_incidents(self):
        """Named separately because it is the trap in reading this corpus.

        Any run whose believed armour touches 0 recovers to over 90% within
        `SUSTAINED_READINGS` readings, so nothing was ever at 0% armour. A run
        that genuinely reached it would fail this case, which is the right
        answer: that would be a second incident and the argument above rests on
        there being one.
        """
        touched = 0
        for path in every_recorded_run():
            rows = readings_from_log(path)
            armour = [value for value in believed([row[2] for row in rows])
                      if value is not None]
            for index, value in enumerate(armour):
                if value > 0:
                    continue
                touched += 1
                following = armour[index:index + SUSTAINED_READINGS + 1]
                self.assertGreater(
                    max(following), 90,
                    "%s holds believed armour at 0%% for %d readings, which is "
                    "longer than any recorded corruption"
                    % (os.path.basename(path), SUSTAINED_READINGS))
        if touched == 0:
            self.skipTest("no recorded run's believed armour reaches 0%")

    def test_run_36_s_window_peaked_while_the_ship_was_still_healthy(self):
        """Gross incoming damage does not order the danger, and that is the crux.

        The combat log reports gross; survival is governed by net; and this
        hull's armour repairer is of the same order as the fire it was under. So
        the guard read its highest value of the whole run at a moment the ship
        was fine, and read lower while the ship was being taken apart. No
        threshold on this instrument separates those two.
        """
        (_, path), = recorded_runs("36")
        rows = readings_from_log(path)
        if len(rows) < 100:
            self.skipTest("mission_run36.log carries too few readings to replay")

        armour = believed([row[2] for row in rows])
        peak = max(range(len(rows)), key=lambda i: rows[i][3])
        live = [i for i, value in enumerate(armour) if value is not None]
        worst = min(live, key=lambda i: armour[i])

        self.assertGreater(
            armour[peak], armour[worst],
            "the window's peak no longer sits above the run's worst armour")
        self.assertGreater(
            armour[peak], 70,
            "the window peaked at %d with armour at %d%%, which is not the "
            "'healthy while the guard reads highest' relation #129 rests on"
            % (rows[peak][3], armour[peak]))
        self.assertGreater(
            rows[peak][3], rows[worst][3],
            "the window read %d at the peak and %d at the ship's worst"
            % (rows[peak][3], rows[worst][3]))

    def test_run_36_s_armour_recovered_under_fire_the_guard_still_reported(self):
        """The repairer, measured on the run the issue was filed on.

        After the low-water mark bottoms out the armour climbs back while the
        combat log still reports hundreds of hitpoints a window. That is the
        repairer out-pacing the incoming fire, and it is why cumulative damage
        over a longer window is not bounded by the tank -- so a longer clock on
        the same gauge-free instrument would not have caught this either.
        """
        (_, path), = recorded_runs("36")
        rows = readings_from_log(path)
        if len(rows) < 100:
            self.skipTest("mission_run36.log carries too few readings to replay")

        armour = believed([row[2] for row in rows])
        marks = low_water(armour)
        bottom = min(range(len(rows)), key=lambda i: marks[i])
        after = [(armour[i], rows[i][3]) for i in range(bottom, len(rows))
                 if armour[i] is not None]
        recovered = [value for value, _ in after]
        self.assertTrue(recovered, "nothing follows run 36's low-water mark")
        self.assertGreater(
            max(recovered) - marks[bottom], 10,
            "run 36's armour no longer recovers meaningfully after its low-water "
            "mark of %d%%" % marks[bottom])

        # It recovered while the client was still reporting real incoming fire,
        # which is the half that makes the point.
        under_fire = [window for value, window in after
                      if value > marks[bottom] and window > 0]
        self.assertTrue(
            under_fire and max(under_fire) > 300,
            "run 36's armour recovery no longer overlaps a live damage window")

    def test_the_shield_is_a_fuse_on_this_hull_and_the_armour_is_the_tank(self):
        """What makes the corrected settings advice load-bearing.

        `Bot.elm` used to tell an operator to set the shield threshold, on the
        reasoning that armour cannot move until the shield is spent. That is
        true of this hull and is exactly why the shield is useless as a guard
        here: it is spent in the first minute of every fight and reads 0-5% for
        the rest of the run, so a shield threshold trips on the ship's ordinary
        condition. Run 10 raised the retreat 142 times that way.
        """
        collapses = 0
        armour_still_high = 0
        for path in every_recorded_run():
            rows = readings_from_log(path)
            if len(rows) < 50:
                continue
            shield = believed([row[1] for row in rows])
            armour = believed([row[2] for row in rows])
            start = None
            for i, row in enumerate(rows):
                if row[3] > 0 and shield[i] is not None and shield[i] >= 95:
                    start = i
                if start is not None and shield[i] is not None and shield[i] <= 5:
                    collapses += 1
                    if armour[i] is not None and armour[i] >= 90:
                        armour_still_high += 1
                    break
        if collapses == 0:
            self.skipTest("no recorded run's shield falls under fire")

        self.assertEqual(
            armour_still_high, collapses,
            "the shield no longer collapses ahead of the armour in every "
            "recorded run that fought: %d of %d" % (armour_still_high, collapses))

    def test_most_readings_under_fire_are_taken_with_the_shield_already_gone(self):
        """The other half of the same fact, counted rather than sampled."""
        under_fire = 0
        shield_gone = 0
        for path in every_recorded_run():
            rows = readings_from_log(path)
            shield = believed([row[1] for row in rows])
            for i, row in enumerate(rows):
                if row[3] > 0 and shield[i] is not None:
                    under_fire += 1
                    if shield[i] <= 5:
                        shield_gone += 1
        if under_fire < 100:
            self.skipTest("the corpus carries too few readings under fire")

        self.assertGreater(
            shield_gone * 2, under_fire,
            "the shield is no longer at or below 5%% on most readings taken "
            "under fire: %d of %d" % (shield_gone, under_fire))


if __name__ == "__main__":
    unittest.main()
