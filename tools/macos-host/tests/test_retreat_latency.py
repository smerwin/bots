"""Deciding to leave is not leaving, and nothing measured the gap.

Issue #136. Run 36's armour guard fired correctly at 66% believed armour and the
ship went on to 17% while the bot printed `get out get out get out`. PR #135 had
already established that the armour percentage guard *is* the attrition guard, so
what stands between the decision and the ship being out is **latency**, and no
reading recorded any of it -- run 36's had to be counted by hand out of a log.

What ships is the measurement and nothing else. `retreatProgressAfterReading`
counts consecutive readings on which the retreat is decided and the ship is not
in warp; the status line prints it; no decision consults it. **The retreat's
ordering is untouched**, and these cases pin that as hard as they pin the new
rule -- `returnDronesToBay` still sits in front of the warp, and
`droneRecallGiveUpTicks` is still 60.

Six things this file establishes, all against recorded data or executed code
rather than restatement:

**The verdict has one definition.** `retreatReason` is extracted so the memory
update can ask the question the decision asks, rather than carrying a second copy
of the most consequential condition in the file. It is executed through the real
`Bot.elm` at every guard's boundary, at fixed values either side, and in every
precedence pair -- a boundary pair alone passes for any constant, which is the
hole four of #120's own cases had and which #129 found again.

**The retreat did not change.** `runAwayIfLowHealth`'s four conditions now live
in `retreatReason`, in the same order, and nothing else compares them. The drone
recall's placement in front of the warp and its give-up bound are read out of the
source and asserted unchanged.

**The counter is not "readings the retreat was decided".** The hysteresis keeps
the verdict latched long after a successful warp -- run 36 printed it on 325 log
entries and was off the grid for the last two-thirds of them -- so a counter
without the warping clause reports a completed retreat as a two-hundred-reading
failure.

**Nothing decides on it.** `retreatProgress` is reachable from the status line
and from nowhere else.

**The drone recall is a minority of retreat latency across the whole corpus**,
including in run 36, and the longest retreats outside run 36 contain none of it.
That is the measurement that decided not to reorder the recall.

**#120's gauge-free property still holds**, because this change sits on top of
it: the scaled threshold and the latch's `retreating` verdict must name no gauge,
and `retreatReason` itself must read nothing but its own record.

The corpus is asserted as *relations* rather than as the numbers in the doc
comments, so a growing corpus cannot turn a true claim red. Cases that execute
Elm need the toolchain and **fail** without it; cases that read `~/eve-bot-logs`
skip when it is absent, for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
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

# The four retreat verdicts, as the decision log spells them. One per guard.
VERDICT_LINE = re.compile(
    r"^(Armor reached |Shield reached "
    r"|The client's combat log says we are taking |We have absorbed )")

# What the retreat is doing on the reading under the verdict. The drone recall's
# three, and the warp the retreat exists to reach.
DRONE_RECALL_LINES = (
    "Drones are not coming back -- click the drones window",
    "I see there are drones in space. Return those to bay.",
    "Drones have not answered",
)
WARP_LINE = "Get out -- "

TICK = re.compile(r"^# \[(\d+)\.(\d+)\]")
DECISION = re.compile(r"^(\++) (.*)$")
RATS = re.compile(r"^rats (\d+) \|")

# How many printed decision blocks may fall between two verdict blocks and still
# be one retreat. The bot re-derives its whole path several times per reading, so
# a gap this small is a reading or two with no ship UI rather than a second
# retreat. Two full readings' worth.
EPISODE_GAP = 6


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

    Doc comments are stripped first, because several of them refer to the rule on
    purpose -- that is the argument being written down, and a case that counted
    those would forbid explaining the thing it is pinning.
    """
    code = re.sub(r"\{-.*?-\}", "", source, flags=re.S)
    found = []
    for chunk in re.split(r"\n\n\n+", code):
        if name not in chunk:
            continue
        # A type declaration is named by its second word, not its first, and
        # collapsing every one of them onto the literal `type` is how a first
        # pass at this made three declarations indistinguishable.
        declared = re.match(r"\s*(?:type\s+alias\s+|type\s+)?(\w+)", chunk)
        if declared is not None:
            found.append(declared.group(1))
    return sorted(set(found))


def record_argument(collapsed_source, function):
    """The record literal `function` is applied to, by balancing braces.

    A non-greedy `\\{ (.*?) \\}` stops at the first closing brace, which here is
    the *inner* record update the call passes through -- so the match ends before
    the fields the case is asking about and the assertion passes on a truncated
    string. Same trap `prerequisites.answers_in` documents for brackets.
    """
    start = collapsed_source.find(function + " {")
    if start < 0:
        return None
    open_brace = collapsed_source.index("{", start)
    depth = 0
    for index in range(open_brace, len(collapsed_source)):
        if collapsed_source[index] == "{":
            depth += 1
        elif collapsed_source[index] == "}":
            depth -= 1
            if depth == 0:
                return collapsed_source[open_brace + 1:index]
    return None


def constant_in_source(source, name):
    """An `Int` constant's value, read out of `Bot.elm` rather than repeated."""
    found = re.search(
        r"^" + re.escape(name) + r"\s*:\s*Int\n"
        + re.escape(name) + r"\s*=\s*(-?\d+)", source, re.M)
    assert found is not None, "no Int constant %s in Bot.elm" % name
    return int(found.group(1))


def every_recorded_run():
    """Every recorded run, for the claims that are about the corpus as a whole.

    `prerequisites.recorded_runs` is the gate where a case names the runs it
    needs; these cases cannot, because what they assert is a relation over
    whatever is there. **The skip reason is deliberately the wording the
    neighbouring corpus-wide gate already uses** -- the prerequisite is the same
    one, `check_expected_skips.py` matches on these strings, and a second
    spelling of one answer is a second entry it would have to carry. PR #135's
    CI failed on exactly that.
    """
    runs = sorted(glob.glob(LOG_GLOB))
    if not runs:
        raise unittest.SkipTest(
            "no recorded runs in ~/eve-bot-logs, so a claim about the corpus "
            "as a whole cannot be made here")
    return runs


def decision_blocks(path):
    """One printed decision block per `# [tick.substep]`, with its rats count.

    The unit is the block rather than the reading, deliberately and with the
    reason stated: **these logs carry no per-reading identity at all.** `[N.M]`
    is a framework step, and one step can span fifteen readings when the client
    stalls -- run 36's does. That is itself the finding behind #136's third
    point, and it is why the interval had to be counted by hand. Every count in
    this file is therefore in blocks, the same unit the issue's own "107
    occurrences" and "325 times" are in.
    """
    block = None
    for line in open(path, encoding="utf-8", errors="replace"):
        if not line.endswith("\n"):
            # The last line of a run still being appended to.
            continue
        if TICK.match(line):
            if block is not None:
                yield block
            block = {"decisions": [], "rats": None}
            continue
        if block is None:
            continue
        decision = DECISION.match(line.rstrip("\n"))
        if decision is not None:
            block["decisions"].append((len(decision.group(1)), decision.group(2)))
            continue
        rats = RATS.match(line)
        if rats is not None:
            block["rats"] = int(rats.group(1))
    if block is not None:
        yield block


def step_under_the_verdict(decisions):
    """What the retreat was doing on this block, or `None` if it said nothing.

    The decision immediately below the verdict in the printed path -- which is
    `runAway`'s own next step, so it distinguishes "recalling drones" from
    "warping" without guessing.
    """
    for index, (depth, text) in enumerate(decisions):
        if VERDICT_LINE.match(text):
            for below_depth, below_text in decisions[index + 1:]:
                return below_text if below_depth > depth else None
            return None
    return None


def retreat_episodes(path):
    """Each retreat in one run, as the blocks it spent still under the guns.

    An episode runs from the first block carrying a verdict until hostiles leave
    the overview, which is the observable proxy for "still on the grid it decided
    to leave". The bot does not record whether it is warping -- that is what #136
    adds -- so the corpus cannot be asked directly, and the readings *after* the
    ship is clear are the ones a naive count gets wrong: the low-water mark keeps
    the verdict latched all the way home.
    """
    blocks = list(decision_blocks(path))
    verdicts = [index for index, block in enumerate(blocks)
                if any(VERDICT_LINE.match(text) for _, text in block["decisions"])]
    grouped = []
    for index in verdicts:
        if grouped and index - grouped[-1][-1] <= EPISODE_GAP:
            grouped[-1].append(index)
        else:
            grouped.append([index])

    episodes = []
    for group in grouped:
        under_fire = []
        for index in group:
            under_fire.append(index)
            if blocks[index]["rats"] == 0:
                break
        tally = collections.Counter()
        for index in under_fire:
            step = step_under_the_verdict(blocks[index]["decisions"]) or ""
            if any(step.startswith(line) for line in DRONE_RECALL_LINES):
                tally["drones"] += 1
            elif step.startswith(WARP_LINE):
                tally["warp"] += 1
            else:
                tally["other"] += 1
        episodes.append({
            "blocks": len(group),
            "underFire": len(under_fire),
            "drones": tally["drones"],
            "warp": tally["warp"],
        })
    return episodes


class RetreatLatencyRepl(ElmRepl):
    """The shared harness, plus builders for the two new records.

    A preamble rather than a definition per case, so a case's assertions line up
    with what it asked rather than with what it had to set up first.
    """

    BINDINGS = [
        "verdict shield shieldT armor armorT latch window moved ="
        " retreatReason"
        " { lowestShieldPercent = shield, shieldThresholdPercent = shieldT"
        " , lowestArmorPercent = armor, armorThresholdPercent = armorT"
        " , damageLatchIsRetreating = latch, damageInWindow = window"
        " , hitpointsReadingMoved = moved }",
        "quiet shield armor = verdict shield -1 armor 70 False 0 Nothing",
        "step decided warping was worst ="
        " retreatProgressAfterReading"
        " { retreatIsDecided = decided, shipIsWarping = warping"
        " , before = { unexecutedReadings = was, longestUnexecutedReadings = worst } }",
        "fold readings ="
        " List.foldl"
        " (\\( decided, warping ) before ->"
        " retreatProgressAfterReading"
        " { retreatIsDecided = decided, shipIsWarping = warping, before = before })"
        " { unexecutedReadings = 0, longestUnexecutedReadings = 0 } readings",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.preamble = self.preamble + self.BINDINGS


class TheVerdictIsOneRuleAndIsExecuted(unittest.TestCase):
    """`retreatReason`, run through the bot's own compiled code."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RetreatLatencyRepl, prefix="test-retreat-latency-")
        cls.source = bot_source()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_armour_mark_fires_below_the_threshold_and_not_at_it(self):
        # The comparison is `<`, so a mark equal to the threshold does not fire.
        # The two fixed values either side of the boundary pair are what stops a
        # rule admitting everything -- or nothing -- from passing here.
        answers = self.repl.evaluate([
            "quiet 100 69 == Just RetreatOnArmorMark",
            "quiet 100 70 == Nothing",
            "quiet 100 0 == Just RetreatOnArmorMark",
            "quiet 100 100 == Nothing",
        ])
        self.assertEqual(answers, [True, True, True, True],
                         "the armour mark must fire strictly below its threshold")

    def test_the_shield_mark_fires_below_its_own_threshold(self):
        # The same bound on the other gauge, asked with the armour guard
        # deliberately unable to fire so the answer can only come from the shield.
        answers = self.repl.evaluate([
            "verdict 24 25 100 -1 False 0 Nothing == Just RetreatOnShieldMark",
            "verdict 25 25 100 -1 False 0 Nothing == Nothing",
            "verdict 0 25 100 -1 False 0 Nothing == Just RetreatOnShieldMark",
            "verdict 100 25 100 -1 False 0 Nothing == Nothing",
        ])
        self.assertEqual(answers, [True, True, True, True],
                         "the shield mark must fire strictly below its threshold")

    def test_a_disabled_threshold_can_never_fire(self):
        # `-1` is what the settings document and what a run started without
        # `run_mission.sh` gets. A low-water mark never goes below 0, so `0` is
        # equally inert -- `attritionIsUnguarded` rests on that and so does this.
        answers = self.repl.evaluate([
            "verdict 0 -1 0 -1 False 0 Nothing == Nothing",
            "verdict 0 0 0 0 False 0 Nothing == Nothing",
            "verdict 0 1 100 -1 False 0 Nothing == Just RetreatOnShieldMark",
            "verdict 100 -1 0 1 False 0 Nothing == Just RetreatOnArmorMark",
        ])
        self.assertEqual(answers, [True, True, True, True])

    def test_the_damage_latch_is_read_and_not_the_live_window(self):
        # The latch is the only thing that can hold a verdict across readings,
        # and holding it is the point: the window drains the moment the ship
        # warps clear. A window far over any threshold with the latch unset must
        # not fire this guard.
        answers = self.repl.evaluate([
            "verdict 100 -1 100 70 True 0 Nothing == Just RetreatOnDamageWindow",
            "verdict 100 -1 100 70 False 999999 (Just True) == Nothing",
        ])
        self.assertEqual(answers, [True, True],
                         "the damage guard must read the latch, not the window")

    def test_the_frozen_reading_guard_needs_both_halves(self):
        moving = constant_in_source(self.source, "damageThatMustMoveTheHitpointsReading")
        answers = self.repl.evaluate([
            "verdict 100 -1 100 70 False %d (Just False) == Just RetreatOnFrozenReading" % moving,
            "verdict 100 -1 100 70 False %d (Just False) == Nothing" % (moving - 1),
            "verdict 100 -1 100 70 False %d (Just True) == Nothing" % (moving + 500),
            "verdict 100 -1 100 70 False 0 (Just False) == Nothing",
        ])
        self.assertEqual(answers, [True, True, True, True])
        self.assertGreater(
            moving, 100,
            "the frozen-reading guard's damage floor must be a real quantity of "
            "damage; a rule that fires on a handful of hitpoints would fire "
            "whenever the gauge quantised")

    def test_an_unanswerable_reading_is_not_a_frozen_one(self):
        # `Nothing` is "this window cannot say whether the reading moved", and
        # collapsing it with `Just False` is the repo's signature bug. It must
        # not fire the guard on its own.
        answers = self.repl.evaluate([
            "verdict 100 -1 100 70 False 999999 Nothing == Nothing",
            "verdict 100 -1 100 70 False 999999 (Just False) == Just RetreatOnFrozenReading",
        ])
        self.assertEqual(answers, [True, True])

    def test_the_guards_keep_runawayiflowhealth_s_precedence(self):
        # Which reason an operator reads on a reading where several guards agree
        # is decided here, and the order is the one `runAwayIfLowHealth` has
        # always had. Every adjacent pair is asked, plus all four at once.
        answers = self.repl.evaluate([
            "verdict 0 25 0 70 True 999999 (Just False) == Just RetreatOnShieldMark",
            "verdict 100 25 0 70 True 999999 (Just False) == Just RetreatOnArmorMark",
            "verdict 100 -1 100 70 True 999999 (Just False) == Just RetreatOnDamageWindow",
            "verdict 100 -1 100 70 False 999999 (Just False) == Just RetreatOnFrozenReading",
        ])
        self.assertEqual(answers, [True, True, True, True],
                         "shield, then armour, then the damage latch, then the "
                         "frozen reading")

    def test_the_mark_folds_in_this_reading_rather_than_lagging_it(self):
        # `lowWaterMark` files a reading *after* the decision has read it, so the
        # mark alone is one reading behind a gauge that has just dropped. Taking
        # the `min` is what makes the retreat act on the reading it arrives.
        answers = self.repl.evaluate([
            "lowestPercentSinceHealthy (Just 40) 100 == 40",
            "lowestPercentSinceHealthy (Just 90) 40 == 40",
            "lowestPercentSinceHealthy Nothing 40 == 40",
            "lowestPercentSinceHealthy Nothing 100 == 100",
        ])
        self.assertEqual(answers, [True, True, True, True])


class TheLatencyIsCounted(unittest.TestCase):
    """`retreatProgressAfterReading`, folded over sessions in the real code."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(RetreatLatencyRepl, prefix="test-retreat-progress-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_retreat_that_cannot_execute_accumulates(self):
        answers = self.repl.evaluate([
            "(step True False 0 0).unexecutedReadings == 1",
            "(step True False 3 5).unexecutedReadings == 4",
            "(step True False 3 5).longestUnexecutedReadings == 5",
            "(step True False 9 5).longestUnexecutedReadings == 10",
        ])
        self.assertEqual(answers, [True, True, True, True],
                         "the peak must be a maximum, not the latest value")

    def test_the_ship_being_in_warp_ends_the_interval(self):
        # This is the clause that separates a slow retreat from a successful one.
        # Without it the hysteresis makes every retreat look like run 36's: the
        # verdict stays latched until the gauge recovers past the re-arm level,
        # which is most of the way home.
        answers = self.repl.evaluate([
            "(step True True 40 40).unexecutedReadings == 0",
            "(step True True 40 40).longestUnexecutedReadings == 40",
            "(step False False 40 40).unexecutedReadings == 0",
            "(step False False 40 40).longestUnexecutedReadings == 40",
        ])
        self.assertEqual(answers, [True, True, True, True],
                         "warping and not retreating both end the interval, and "
                         "neither may discard the session's worst")

    def test_a_session_that_never_retreats_reports_nothing(self):
        answers = self.repl.evaluate([
            "(fold (List.repeat 500 ( False, False ))).unexecutedReadings == 0",
            "(fold (List.repeat 500 ( False, False ))).longestUnexecutedReadings == 0",
        ])
        self.assertEqual(answers, [True, True])

    def test_run_36_s_shape_folded_through_the_rule(self):
        # Decide, sit on the grid for thirty readings, warp, then carry the
        # latched verdict home for two hundred more. The interval is thirty and
        # the two hundred are not part of it.
        session = ("List.repeat 30 ( True, False ) ++ "
                   "List.repeat 200 ( True, True )")
        answers = self.repl.evaluate([
            "(fold (%s)).longestUnexecutedReadings == 30" % session,
            "(fold (%s)).unexecutedReadings == 0" % session,
        ])
        self.assertEqual(answers, [True, True],
                         "a retreat that reached warp must not go on counting")

    def test_a_second_retreat_after_a_warp_is_measured_on_its_own(self):
        # Warping to a celestial that turns out to be no safer starts a fresh
        # interval, and that one is the one worth reporting. The peak survives.
        session = ("List.repeat 12 ( True, False ) ++ "
                   "List.repeat 8 ( True, True ) ++ "
                   "List.repeat 5 ( True, False )")
        answers = self.repl.evaluate([
            "(fold (%s)).unexecutedReadings == 5" % session,
            "(fold (%s)).longestUnexecutedReadings == 12" % session,
        ])
        self.assertEqual(answers, [True, True])


class TheRetreatItselfDidNotChange(unittest.TestCase):
    """The ordering and the bounds this change deliberately leaves alone."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()
        cls.flat = collapsed(cls.source)

    def test_the_drone_recall_still_sits_in_front_of_the_warp(self):
        # #11 and #59 put it there and the corpus does not justify moving it --
        # see `retreatProgressAfterReading`'s doc comment. A change that
        # reordered the retreat would pass every other case in this file.
        run_away = collapsed(definition_body(self.source, "runAway"))
        self.assertIn("returnDronesToBay context ( selectThenPanelAction context",
                      run_away.replace("(", "( "),
                      "runAway must still recall drones before warping")
        tether = collapsed(definition_body(self.source, "tetherAtStructure"))
        self.assertIn("returnDronesToBay context", tether,
                      "the dock/gate leg of the retreat must still recall drones")

    def test_the_recall_give_up_bound_is_unchanged(self):
        # 60, and no recorded run has ever reached it -- see the corpus case
        # below. Tightening a bound nothing has approached, on the retreat path,
        # on one incident, is the speculative change this refuses.
        self.assertEqual(constant_in_source(self.source, "droneRecallGiveUpTicks"), 60)
        self.assertEqual(
            constant_in_source(self.source, "droneRecallFocusRecoveryTicks"), 20,
            "the focus-recovery click is untouched too")

    def test_the_retreat_has_exactly_one_copy_of_its_conditions(self):
        # The whole reason `retreatReason` was extracted. A second comparison
        # anywhere is two definitions of when the ship leaves.
        code = collapsed(re.sub(r"\{-.*?-\}", "", self.source, flags=re.S))
        for gauge in ("lowestShieldPercent", "lowestArmorPercent"):
            comparisons = re.findall(re.escape(gauge) + r"\s*<\s*", code)
            self.assertEqual(
                len(comparisons), 1,
                "%s must be compared against its threshold in exactly one "
                "place, found %d" % (gauge, len(comparisons)))

        # And the record's field names are not the only way to write the
        # comparison: a second copy could reach for the *setting* instead, which
        # is what a first pass at this case let through. Neither threshold
        # setting may appear as an operand of a comparison anywhere -- the one
        # place they are read is `retreatCaseFromMemory`, which only files them
        # into the record.
        for setting in ("runAwayShieldHitpointsThresholdPercent",
                        "runAwayArmorHitpointsThresholdPercent"):
            for pattern in (r"[\w.]+\s*<=?\s*[\w.]*" + re.escape(setting),
                            re.escape(setting) + r"\s*<=?"):
                self.assertEqual(
                    re.findall(pattern, code), [],
                    "%s is compared somewhere outside retreatReason, which is a "
                    "second definition of when the ship leaves" % setting)

    def test_runawayiflowhealth_decides_through_the_extracted_rule(self):
        body = collapsed(definition_body(self.source, "runAwayIfLowHealth"))
        self.assertIn("case retreatReason", body,
                      "the decision must ask the shared rule")
        for reason in ("RetreatOnShieldMark", "RetreatOnArmorMark",
                       "RetreatOnDamageWindow", "RetreatOnFrozenReading"):
            self.assertIn(reason, body,
                          "the decision must still name %s, so each guard keeps "
                          "its own decision line" % reason)

    def test_the_rule_reads_nothing_but_its_own_record(self):
        # #120's property, applied to the new function. `retreatReason` is a
        # rule over a record, so a case can build one -- and so a mutation that
        # reached into a reading for the live gauge would break the whole shape
        # rather than only the answer.
        body = collapsed(definition_body(self.source, "retreatReason"))
        for forbidden in ("shipUI", "hitpointsPercent", "readingFromGameClient",
                          "context", "believed"):
            self.assertNotIn(
                forbidden, body,
                "retreatReason must be pure over RetreatCase and must not name "
                "%s" % forbidden)

    def test_the_gauge_free_guard_does_not_read_a_gauge(self):
        # Re-asserted here because this change sits next to it, exactly as #129
        # re-asserted it. The scaled threshold and the latch's verdict must name
        # no gauge; the latch's *sample* record legitimately does, since the
        # frozen-reading guard is what reads it.
        threshold = collapsed(
            definition_body(self.source, "incomingDamageThresholdForThisShip"))
        for forbidden in ("hitpointsPercent", "believed", "lowestArmor",
                          "lowestShield"):
            self.assertNotIn(forbidden, threshold,
                             "the gauge-free threshold must not read %s" % forbidden)
        latch = collapsed(definition_body(self.source, "updateIncomingDamageMemory"))
        # The verdict is the record update the function ends on. The latch's
        # *sample* record above it legitimately names a gauge, because the
        # frozen-reading guard is what reads it, so only this expression is
        # asserted rather than the whole definition.
        retreating = re.search(r"\{ updated \| retreating = (.*)$", latch)
        self.assertIsNotNone(retreating,
                             "could not find the latch's retreating expression")
        for forbidden in ("hitpointsPercent", "believed", "hitpoints"):
            self.assertNotIn(forbidden, retreating.group(1),
                             "the latch's verdict must not read %s" % forbidden)


class NothingDecidesOnTheMeasurement(unittest.TestCase):
    """#135's precedent: a pure rule read by the status line and by no decision."""

    @classmethod
    def setUpClass(cls):
        cls.source = bot_source()

    def test_the_counter_is_read_by_the_status_line_and_by_nothing_else(self):
        readers = definitions_mentioning(self.source, "retreatProgress")
        self.assertEqual(
            sorted(readers),
            sorted(["BotMemory", "retreatProgressAfterReading",
                    "describeRetreatLatency", "initBotMemory",
                    "updateMemoryForNewReadingFromGame"]),
            "retreatProgress must be written by the memory update and read by "
            "the status line only; found %r" % (readers,))

    def test_the_status_line_carries_it(self):
        status = collapsed(definition_body(self.source, "statusTextFromState"))
        self.assertIn("describeRetreatLatency context", status,
                      "the status line must print the retreat's latency")
        self.assertIn("describeRetreatCover context", status,
                      "and must still carry #135's marks beside it")

    def test_the_retreat_does_not_consult_the_new_rule(self):
        for name in ("runAwayIfLowHealth", "runAway", "returnDronesToBay",
                     "retreatReason"):
            body = definition_body(self.source, name)
            self.assertNotIn(
                "retreatProgress", body,
                "%s must not decide on the latency measurement" % name)

    def test_the_counter_is_gated_on_the_ship_ui_and_on_warping(self):
        # `runAwayIfLowHealth` is only reached through `ifSeeShipUI`, so a docked
        # reading whose damage latch is still set is not a retreat that failed to
        # execute. And the warping clause is what stops the hysteresis inflating
        # every successful retreat into a slow one.
        update = collapsed(definition_body(
            self.source, "updateMemoryForNewReadingFromGame"))
        call = record_argument(update, "retreatProgressAfterReading")
        self.assertIsNotNone(call, "could not find the counter's own call")
        self.assertIn("shipUI /= Nothing", call,
                      "the counter must require the ship UI, which is the gate "
                      "runAwayIfLowHealth itself sits behind")
        self.assertIn("shipIsWarping", call,
                      "the counter must consult whether the ship is warping")
        self.assertIn("retreatReason", call,
                      "the counter must use the decision's own verdict rule")


class WhatTheCorpusSaysAboutRetreatLatency(unittest.TestCase):
    """The 29 recorded retreats, measured for the first time.

    These are the measurements that decided **not** to reorder the drone recall,
    so they are asserted as relations rather than as the numbers in the doc
    comment: the recall is a minority of retreat latency, the longest retreats
    contain none of it, and the recall's give-up has never fired at all.
    """

    def test_the_corpus_contains_retreats_to_measure(self):
        episodes = []
        for path in every_recorded_run():
            episodes.extend(retreat_episodes(path))
        self.assertGreater(len(episodes), 5,
                           "the corpus must hold enough retreats for the "
                           "relations below to mean anything")
        self.assertTrue(all(episode["underFire"] >= 1 for episode in episodes))

    def test_the_drone_recall_is_a_minority_of_retreat_latency(self):
        drones = warp = under_fire = 0
        for path in every_recorded_run():
            for episode in retreat_episodes(path):
                drones += episode["drones"]
                warp += episode["warp"]
                under_fire += episode["underFire"]
        self.assertGreater(under_fire, 0)
        self.assertLess(
            drones * 2, under_fire,
            "the drone recall accounts for %d of %d blocks spent under fire "
            "after a retreat verdict. If it ever becomes the majority, the "
            "argument in retreatProgressAfterReading's doc comment for leaving "
            "the ordering alone no longer holds" % (drones, under_fire))
        self.assertGreater(
            warp, drones,
            "most of the interval is the warp command already issued and not "
            "yet taken effect, not the recall in front of it")

    def test_a_slow_retreat_needs_no_drone_recall_at_all(self):
        # The relation that does the work. If every slow retreat in the corpus
        # had the recall in it, the recall would at least be a candidate cause;
        # several do not have it at all, so a slow retreat is fully reachable
        # without it and reordering it cannot be the fix.
        #
        # Deliberately *not* "the longest retreat outside run 36 holds none" --
        # a first pass asserted that and it is false. Run 10's 142-block retreat
        # is the longest of them and spends six blocks on the recall, which is
        # what the second assertion below measures instead.
        others = []
        for path in every_recorded_run():
            if path.endswith("mission_run36.log"):
                continue
            others.extend(retreat_episodes(path))
        slow = [episode for episode in others if episode["underFire"] > 20]
        if not slow:
            self.skipTest(
                "no recorded runs in ~/eve-bot-logs holding a slow retreat "
                "outside run 36, so a claim about the corpus as a whole cannot "
                "be made here")
        without_recall = [episode for episode in slow if episode["drones"] == 0]
        self.assertTrue(
            without_recall,
            "every slow retreat outside run 36 spends blocks on the drone "
            "recall, which would make it a candidate cause after all")

        longest = max(slow, key=lambda episode: episode["underFire"])
        self.assertLess(
            longest["drones"] * 5, longest["underFire"],
            "the longest retreat outside run 36 spent %d of %d blocks on the "
            "drone recall; the argument for leaving the ordering alone rests on "
            "that being a small share" % (longest["drones"], longest["underFire"]))

    def test_run_36_is_the_outlier_and_its_recall_is_the_smaller_half(self):
        for _, path in recorded_runs("36"):
            episodes = retreat_episodes(path)
            self.assertEqual(len(episodes), 1,
                             "run 36 holds exactly one retreat")
            episode = episodes[0]
            self.assertGreater(
                episode["warp"], episode["drones"] * 3,
                "run 36 spent %d blocks on the warp against %d on the drone "
                "recall; the issue's premise is that the recall was the "
                "interval" % (episode["warp"], episode["drones"]))
            self.assertLess(
                episode["underFire"], episode["blocks"],
                "run 36's verdict outlived the grid it left, which is why the "
                "counter cannot simply count readings the retreat was decided")

    def test_the_recall_give_up_has_never_fired_in_any_recorded_run(self):
        # The branch names itself on every reading it declines since #11, so
        # zero is evidence rather than silence. It is the reason
        # droneRecallGiveUpTicks is not retuned here: no recorded run has ever
        # reached it.
        fired = 0
        for path in every_recorded_run():
            with open(path, encoding="utf-8", errors="replace") as log:
                for line in log:
                    if "Drones have not answered" in line:
                        fired += 1
        self.assertEqual(
            fired, 0,
            "returnDronesToBay's give-up appears %d times in the corpus. If a "
            "run has now reached it, droneRecallGiveUpTicks has evidence behind "
            "it for the first time and #136's first question can be reopened"
            % fired)

    def test_no_recorded_run_carries_the_new_measurement(self):
        # The point of #136, stated as a fact about the corpus: nothing recorded
        # says how long a retreat took. A run that does is the evidence a change
        # to the ordering would need, and this case is what notices it arriving.
        carrying = []
        for path in every_recorded_run():
            with open(path, encoding="utf-8", errors="replace") as log:
                if any("RETREAT NOT EXECUTING" in line for line in log):
                    carrying.append(os.path.basename(path))
        self.assertEqual(
            carrying, [],
            "%r already carry the retreat-latency clause, so the corpus can now "
            "answer how long a retreat takes from the bot's own reading rather "
            "than from the rats-on-overview proxy this file uses" % (carrying,))


if __name__ == "__main__":
    unittest.main()
