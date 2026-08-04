"""When the ammo swap asks a weapon for its tooltip, and how often it may.

Issue #106. Run 32 turned the ammo swap off **for the whole session at tick 61**,
four minutes into a three-hour run, on this verdict:

    Ammo swap: given up -- no crossover distance: 'ammo-swap-range' is not set
    and the weapon's tooltip never appeared, so there is no distance to swap at
    even though the menu says which charge is loaded.

The evidence behind it was `tooltip unanswered 5`: five readings of one hover.
That is one of only three verdicts in this feature that switch it off for a
session, and unlike the other two -- the ship carrying neither charge, and the
silence deadline -- nothing about it says the tooltip will never appear.

**The tooltip works on this client**, which is why five readings are not enough
to conclude otherwise. Run 17 answered on the reading straight after the hover
with `tooltip unanswered` at 0 on every one of its ammo status lines; run 26
derived a 44000 m crossover from two observed optimal ranges; run 30 answered on
the third reading of its hover.

**And combat is not what starved run 32**, which is the one place this suite
disagrees with the issue that prompted it. The issue reasons that the hover
landed mid-fight, where the mouse is wanted for locking and clicking, so the
dwell a Photon flyout needs never accumulated. The log says otherwise in both
directions, and both are asserted below:

- Across the eleven steps of run 32's failed hover the bot dispatched **exactly
  one** effect -- the glide onto the module -- and nothing else. Twelve seconds
  of uninterrupted dwell, and no flyout.
- Run 30's hover *was* answered mid-fight, with twelve rats on the overview and
  726 hitpoints in the damage window.

So the fix is about the sample rather than about incoming fire, and it has two
halves. The readings bound one **hover** and no longer the feature
(`weaponTooltipUnansweredGiveUpTicks`); the feature is given up only after
`weaponTooltipAttemptsBeforeGivingUp` separate hovers, each asked at a different
moment. And the moments after the first are **warps**, where
`decideActionWhenInSpace` already issues nothing for sixteen-odd readings, so the
mouse is free by construction and holding it still costs nothing.

`weaponTooltipIsWorthAsking` is that rule, and it takes a record so a case can
run it. The give-up it replaces was reachable only through a whole
`BotDecisionContext`, so nothing here could ever have executed it -- which is why
the version that shipped was checked by reading it rather than by running it.

The rules are **executed** through the real `Bot.elm` in `elm repl`, the one
harness in `prerequisites.py`. Those cases need `elm` on PATH and the app's
dependencies fetched; without them they **fail** rather than skipping, because a
rule that was never executed must not read as a rule that held.

    python3 -m unittest discover -s tools/macos-host/tests
"""
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

# The decision line each hover begins with, and the one it prints while waiting.
HOVER_STARTS = "+ Rest the mouse on a weapon"
HOVER_HOLDS = "+ Holding still for the weapon's tooltip"

# The verdict this whole issue is about, and the short flag it becomes.
GAVE_UP = "Ammo swap: given up"
OFF_FOR_SESSION = "off for this session"

# `decideActionWhenInSpace`'s answer while the ship is warping. Every hover after
# the first is asked on a reading printing this.
IN_WARP = "+ I am in warp"

# Two readings apart is the same episode; a gap of this many log lines is a
# different one. A reading is a dozen-odd lines, so this is a few readings and
# nowhere near the tens of readings a warp or a hover runs for.
EPISODE_GAP_LINES = 40


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapse(text):
    """Whitespace-collapsed source, so `elm-format` cannot break an assertion.

    #58's reformat broke three source-reading assertions pinned on exact
    indentation. Everything asserted about the shape of `Bot.elm` goes through
    this, as it does in the other ammo suites.
    """
    return " ".join(text.split())


def int_constant(source, name):
    match = re.search(r"^" + name + r" : Int\n" + name + r" =\n\s+(\d+)",
                      source, re.MULTILINE)
    if match is None:
        raise AssertionError("no Int constant named " + name)
    return int(match.group(1))


def function_body(source, signature_start, next_top_level):
    start = source.index(signature_start)
    end = source.index(next_top_level, start)
    return source[start:end]


def let_binding(source, name, indent="        "):
    """The right-hand side of a `let` binding, up to the next binding or `in`.

    Same shape as `test_ammo_silenced_bound.definition_body` and separate for
    the reason `test_ammo_no_disarm_under_fire` gives for its own copy: these
    suites own different properties of the same function, and a shared reader
    between them is a coupling nobody wants to reason about later.

    Anchored on the `let`'s own indent rather than on the name alone, because
    every field here is also a field of `initAmmoSwapMemory` and of the record
    the update returns -- a bare name search finds the initialiser and asserts
    on `False`.
    """
    start = source.index(indent + name + " =")
    rest = source[start + len(indent) + len(name) + 3:]
    end = re.search(r"\n\n" + indent + r"\S", rest)
    closing = re.search(r"\n    in\n", rest)
    if end is None or (closing is not None and closing.start() < end.start()):
        end = closing
    return rest[:end.start()] if end else rest


def read_log(path):
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read().split("\n")


def episodes(indices):
    """Consecutive log-line numbers grouped into runs of the same activity."""
    grouped = []
    for index in indices:
        if grouped and index - grouped[-1][-1] <= EPISODE_GAP_LINES:
            grouped[-1].append(index)
        else:
            grouped.append([index])
    return grouped


def lines_starting(lines, prefix):
    return [i for i, line in enumerate(lines) if line.startswith(prefix)]


def readings_in(lines, start, end):
    """The distinct `# [tick.substep]` ticks covered by a slice of the log.

    The bot re-derives its decision on every framework event, so a decision line
    printed four times is not four readings -- CLAUDE.md's first warning to a
    newcomer, and the statistic `stall_watch.py` was once calibrated against by
    mistake.
    """
    ticks = set()
    for line in lines[start:end]:
        match = re.match(r"^# \[(\d+)\.", line)
        if match:
            ticks.add(int(match.group(1)))
    return ticks


def elm_bool(value):
    return "True" if value else "False"


def elm_ask_case(unanswered_ticks=0, attempts_spent=0, ship_is_warping=False,
                 attempt_spent_since_warp_began=False,
                 ammo_names_configured=True, swap_given_up=False,
                 crossover_is_configured=False, optimal_range_is_known=False):
    """A `WeaponTooltipAskCase`: everything the ask turns on, and nothing else."""
    return (
        "{ ammoNamesConfigured = %s, swapGivenUp = %s, crossoverIsConfigured = %s"
        ", optimalRangeIsKnown = %s, unansweredTicks = %d, attemptsSpent = %d"
        ", attemptSpentSinceWarpBegan = %s, shipIsWarping = %s }"
        % (elm_bool(ammo_names_configured), elm_bool(swap_given_up),
           elm_bool(crossover_is_configured), elm_bool(optimal_range_is_known),
           unanswered_ticks, attempts_spent,
           elm_bool(attempt_spent_since_warp_began), elm_bool(ship_is_warping)))


def repl():
    return open_repl(ElmRepl, prefix="test-ammo-tooltip-retry-")


class RunThirtyTwoIsTheIncident(unittest.TestCase):
    """What the log says happened, re-derived rather than quoted.

    The numbers are asserted as *relations* -- one hover, one dispatched effect,
    the budget reached -- because run 32 was still being written when this was
    written, and a corpus that grows must not turn a true claim red.
    """

    def test_the_give_up_rested_on_a_single_hover(self):
        # The whole issue in one assertion. Five readings is
        # `weaponTooltipUnansweredGiveUpTicks`, and they were five readings of
        # *one* hover -- one moment, sampled five times.
        for name, path in recorded_runs("32"):
            lines = read_log(path)
            gave_up = lines_starting(lines, GAVE_UP)
            self.assertTrue(
                gave_up, "run %s no longer carries the give-up this suite is "
                "about" % name)
            hovers = episodes(lines_starting(lines, HOVER_STARTS))
            before = [e for e in hovers if e[0] < gave_up[0]]
            self.assertEqual(
                len(before), 1,
                "run %s reached the give-up after %d hovers, not the single "
                "one the issue is about" % (name, len(before)))

    def test_nothing_interrupted_the_dwell_it_gave_up_on(self):
        # The issue's own explanation is that combat took the mouse away. It did
        # not: one effect went out across the whole episode, the glide onto the
        # module, and the bot then held perfectly still. Whatever starved that
        # flyout, it was not the bot moving the cursor -- which is why the fix
        # below carries no incoming-damage clause.
        for name, path in recorded_runs("32"):
            lines = read_log(path)
            start = lines_starting(lines, HOVER_STARTS)[0]
            end = lines_starting(lines, GAVE_UP)[0]
            dispatched = [line for line in lines[start:end]
                          if "task send-effects-" in line]
            self.assertEqual(
                len(dispatched), 1,
                "run %s dispatched %d effect sequences during the hover it gave "
                "up on; the premise that the mouse was taken away depends on "
                "there being exactly one" % (name, len(dispatched)))

    def test_the_hover_was_held_for_more_readings_than_it_was_given(self):
        # `weaponTooltipUnansweredGiveUpTicks` counts readings in which the bot
        # was still waiting, which is fewer than the readings the episode spans.
        # Both are asserted, because the second is what says the client had real
        # time to answer -- eleven steps, about twelve seconds of stillness.
        budget = int_constant(bot_source(), "weaponTooltipUnansweredGiveUpTicks")
        for name, path in recorded_runs("32"):
            lines = read_log(path)
            start = lines_starting(lines, HOVER_STARTS)[0]
            end = lines_starting(lines, GAVE_UP)[0]
            unanswered = [int(m.group(1)) for line in lines[start:end]
                          for m in [re.search(r"tooltip unanswered (\d+)", line)]
                          if m]
            self.assertEqual(
                max(unanswered), budget,
                "run %s's counter reached %d against a budget of %d"
                % (name, max(unanswered), budget))
            self.assertGreater(
                len(readings_in(lines, start, end)), budget,
                "run %s's hover spanned no more readings than the budget, so "
                "the client was never given longer than the counter says"
                % name)

    def test_the_latch_then_held_for_the_rest_of_the_run(self):
        # What the verdict costs, and why retrying is the cheaper side of the
        # trade: every later reading reports the feature off rather than
        # attempting anything.
        for name, path in recorded_runs("32"):
            lines = read_log(path)
            off = [line for line in lines if OFF_FOR_SESSION in line]
            hovers_after = [i for i in lines_starting(lines, HOVER_STARTS)
                            if i > lines_starting(lines, GAVE_UP)[0]]
            self.assertGreater(
                len(off), 100,
                "run %s does not show the latch holding, so it is not the "
                "incident this suite is written about" % name)
            self.assertEqual(
                hovers_after, [],
                "run %s asked again after the latch, which the latch is "
                "supposed to prevent" % name)


class TheTooltipAnswersOnThisClient(unittest.TestCase):
    """The counter-evidence: three runs got an answer, one of them under fire."""

    def test_the_runs_the_issue_cites_read_an_optimal_range(self):
        for name, path in recorded_runs("17", "26", "30"):
            lines = read_log(path)
            answered = [line for line in lines
                        if re.search(r"Optimal range now: \d+ m", line)]
            self.assertTrue(
                answered,
                "run %s no longer shows the tooltip answering, which is the "
                "evidence that five unanswered readings prove nothing" % name)

    def test_run_30_was_answered_while_the_ship_was_being_shot(self):
        # The assertion that keeps a damage clause out of the rule. Run 30's
        # hover was answered on a grid with rats on the overview and real
        # hitpoints in the 45-second window -- the same conditions the issue
        # blames for run 32.
        for name, path in recorded_runs("30"):
            lines = read_log(path)
            answered = next(i for i, line in enumerate(lines)
                            if re.search(r"Optimal range now: \d+ m", line))
            window = lines[max(0, answered - 14):answered + 1]
            damage = [int(m.group(1)) for line in window
                      for m in [re.search(r"dmg (\d+)/\d+", line)] if m]
            rats = [int(m.group(1)) for line in window
                    for m in [re.match(r"^rats (\d+)", line)] if m]
            self.assertTrue(
                damage and max(damage) > 0,
                "run %s's answered hover no longer sits beside incoming "
                "damage, so it no longer refutes the mid-combat explanation"
                % name)
            self.assertTrue(
                rats and max(rats) > 0,
                "run %s's answered hover no longer sits beside rats on the "
                "overview" % name)


class TheBudgetIsSpendableWithinASession(unittest.TestCase):
    """`weaponTooltipAttemptsBeforeGivingUp` is sized against the runs' warps.

    A budget larger than a session's supply of free moments is a give-up that
    never fires, which is its own failure -- the bot would hover once a warp
    forever on a client that genuinely cannot answer.
    """

    def test_a_session_offers_at_least_as_many_warps_as_the_budget(self):
        budget = int_constant(bot_source(), "weaponTooltipAttemptsBeforeGivingUp")
        for name, path in recorded_runs("17", "26", "30"):
            lines = read_log(path)
            warps = episodes(lines_starting(lines, IN_WARP))
            self.assertGreaterEqual(
                len(warps), budget,
                "run %s carries %d warps against a budget of %d, so the "
                "give-up could not be reached in a session like it"
                % (name, len(warps), budget))

    def test_a_warp_is_longer_than_one_hover_is_given(self):
        # Why the ask moves to the warps at all: the median warp holds more
        # readings of guaranteed stillness than a hover is allowed to spend.
        budget = int_constant(bot_source(), "weaponTooltipUnansweredGiveUpTicks")
        for name, path in recorded_runs("17", "26", "30", "32"):
            lines = read_log(path)
            warps = episodes(lines_starting(lines, IN_WARP))
            lengths = sorted(len(readings_in(lines, warp[0], warp[-1] + 1))
                             for warp in warps)
            median = lengths[len(lengths) // 2]
            self.assertGreater(
                median, budget,
                "run %s's median warp is %d readings against a hover budget of "
                "%d, so a warp no longer supplies the dwell this change moves "
                "the ask into" % (name, median, budget))


class TheRuleIsExecutedRatherThanMirrored(unittest.TestCase):
    """`weaponTooltipIsWorthAsking` and the two bounds, run for real."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.source = bot_source()
        cls.attempt_budget = int_constant(
            cls.source, "weaponTooltipUnansweredGiveUpTicks")
        cls.ask_budget = int_constant(
            cls.source, "weaponTooltipAttemptsBeforeGivingUp")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_run_32_s_own_five_readings_no_longer_end_the_ask(self):
        # The incident, executed. One hover reaching the budget spends one
        # hover; the ask survives it, which is the entire change.
        spent, given_up = self.repl.evaluate([
            "weaponTooltipAttemptIsSpent "
            + elm_ask_case(unanswered_ticks=self.attempt_budget + 1),
            "weaponTooltipAskIsGivenUp " + elm_ask_case(attempts_spent=1),
        ])
        self.assertTrue(spent, "a hover past its budget is not spent")
        self.assertFalse(
            given_up,
            "one spent hover still ends the ask, which is run 32's verdict "
            "unchanged")

    def test_the_hover_bound_fires_one_reading_past_its_budget(self):
        answers = self.repl.evaluate([
            "weaponTooltipAttemptIsSpent " + elm_ask_case(unanswered_ticks=ticks)
            for ticks in range(self.attempt_budget + 2)])
        self.assertEqual(
            answers,
            [False] * (self.attempt_budget + 1) + [True],
            "the hover bound no longer fires exactly one reading past "
            "weaponTooltipUnansweredGiveUpTicks")

    def test_the_ask_is_given_up_exactly_at_the_hover_budget(self):
        answers = self.repl.evaluate([
            "weaponTooltipAskIsGivenUp " + elm_ask_case(attempts_spent=spent)
            for spent in range(self.ask_budget + 1)])
        self.assertEqual(
            answers, [False] * self.ask_budget + [True],
            "the ask is no longer given up on the "
            "weaponTooltipAttemptsBeforeGivingUp'th spent hover")

    def test_the_pocket_gets_one_hover_and_the_warps_get_the_rest(self):
        # The placement issue #106 asks for, as one table. Out of warp the ask
        # is available only while nothing has been spent; in warp it is
        # available until this warp has spent one.
        cases = [
            ("first hover, in a pocket", dict(), True),
            ("second hover, in the same pocket",
             dict(attempts_spent=1), False),
            ("fifth hover, in a pocket", dict(attempts_spent=5), False),
            ("second hover, in warp",
             dict(attempts_spent=1, ship_is_warping=True), True),
            ("second hover, in a warp that already spent one",
             dict(attempts_spent=1, ship_is_warping=True,
                  attempt_spent_since_warp_began=True), False),
            ("first hover, in warp", dict(ship_is_warping=True), True),
        ]
        answers = self.repl.evaluate([
            "weaponTooltipIsWorthAsking " + elm_ask_case(**kwargs)
            for _, kwargs, _ in cases])
        self.assertEqual(
            answers, [expected for _, _, expected in cases],
            "the ask is no longer placed the way #106 asks: "
            + repr(list(zip([name for name, _, _ in cases], answers))))

    def test_a_warp_cannot_spend_the_whole_session_s_budget(self):
        # A warp runs long enough to hold several hovers back to back, and six
        # hovers asked inside one warp are one moment sampled six times -- run
        # 32's mistake with more readings in it.
        (asking,) = self.repl.evaluate([
            "weaponTooltipIsWorthAsking "
            + elm_ask_case(ship_is_warping=True, attempts_spent=1,
                           attempt_spent_since_warp_began=True)])
        self.assertFalse(
            asking,
            "a warp that has already spent a hover asks again, so one warp can "
            "spend every hover the session has")

    def test_leaving_the_warp_does_not_hand_the_pocket_another_hover(self):
        # The per-warp flag clears whenever the ship is not warping, so the
        # pocket has to be held back by the hover count instead. If it were not,
        # every arrival would re-open the fight to a hover.
        (asking,) = self.repl.evaluate([
            "weaponTooltipIsWorthAsking "
            + elm_ask_case(attempts_spent=1, ship_is_warping=False,
                           attempt_spent_since_warp_began=False)])
        self.assertFalse(
            asking,
            "the pocket asks again once a hover has been spent, which is the "
            "eagerness #106 is about")

    def test_nothing_is_asked_once_the_ask_is_given_up(self):
        answers = self.repl.evaluate([
            "weaponTooltipIsWorthAsking "
            + elm_ask_case(attempts_spent=self.ask_budget, ship_is_warping=warping)
            for warping in (False, True)])
        self.assertEqual(
            answers, [False, False],
            "a given-up ask still hovers, so the give-up bounds nothing")

    def test_a_configured_crossover_asks_for_nothing(self):
        # PR #105's `ammo-swap-range`. With the crossover configured the hover
        # is not a precondition for anything, so the mouse is left alone.
        answers = self.repl.evaluate([
            "weaponTooltipIsWorthAsking "
            + elm_ask_case(crossover_is_configured=True, ship_is_warping=warping)
            for warping in (False, True)])
        self.assertEqual(
            answers, [False, False],
            "'ammo-swap-range' being set no longer stops the hover")

    def test_the_other_three_ways_there_is_nothing_to_ask(self):
        cases = [
            ("the optimal range is already read",
             dict(optimal_range_is_known=True)),
            ("the swap is off for the session", dict(swap_given_up=True)),
            ("the charge names are not configured",
             dict(ammo_names_configured=False)),
        ]
        answers = self.repl.evaluate([
            "weaponTooltipIsWorthAsking " + elm_ask_case(ship_is_warping=True, **kwargs)
            for _, kwargs in cases])
        self.assertEqual(
            answers, [False] * len(cases),
            "the ask fires where there is nothing to learn: "
            + repr(list(zip([name for name, _ in cases], answers))))


class TheAskIsWiredWhereTheMouseIsFree(unittest.TestCase):
    """Read out of the source, because placement is not observable per input."""

    def setUp(self):
        self.source = bot_source()

    def test_the_warp_branch_hands_on_to_the_hover(self):
        self.assertIn(
            'describeBranch "I am in warp." (returnDronesToBay context '
            "(readWeaponOptimalRangeWhileWarping context))",
            collapse(self.source),
            "the in-warp branch no longer offers the hover, so every hover "
            "after the first has nowhere to happen")

    def test_the_drones_still_come_home_first(self):
        # `returnDronesToBay` wraps the hover rather than the other way round.
        # Run 11 spent 21 readings of `I am in warp` getting five drones back,
        # and a refinement must not be able to delay that.
        body = collapse(function_body(
            self.source,
            "readWeaponOptimalRangeWhileWarping : BotDecisionContext",
            "{-| Whether this host is carrying the client's game log"))
        self.assertNotIn(
            "returnDronesToBay", body,
            "the hover calls the drone recall, so the two have swapped places")

    def test_the_hover_declines_to_waiting_rather_than_to_anything_else(self):
        # In warp the branch it replaces was `waitForProgressInGame`, so a
        # reading with nothing to ask has to end up exactly where it did.
        body = collapse(function_body(
            self.source,
            "readWeaponOptimalRangeWhileWarping : BotDecisionContext",
            "{-| Whether this host is carrying the client's game log"))
        self.assertEqual(
            body.count("waitForProgressInGame"), 2,
            "the in-warp hover no longer falls back to waiting on both of the "
            "readings that have nothing to ask")

    def test_both_callers_ask_the_same_rule(self):
        # The status line and the two decision paths must not be able to
        # disagree about whether a hover is worth asking, which is what one
        # shared rule and one shared case buy.
        collapsed = collapse(self.source)
        self.assertEqual(
            collapsed.count("weaponTooltipIsWorthAsking (weaponTooltipAskCaseFromContext context)"),
            2,
            "the fight path and the warp path no longer ask the same rule")

    def test_the_fight_path_no_longer_reads_the_latch_directly(self):
        # `stillWorthReadingTheOptimalRange` used to conjoin three fields by
        # hand, which is the version no case could execute.
        body = collapse(let_binding(self.source, "stillWorthReadingTheOptimalRange"))
        self.assertNotIn(
            "optimalRangeGivenUp", body,
            "the fight path reads the latch itself again rather than asking "
            "the rule")

    def test_the_warp_predicate_is_the_one_the_warp_branch_uses(self):
        body = collapse(function_body(
            self.source,
            "shipIsWarpingInReading : ReadingFromGameClient",
            "\n\n{-|"))
        self.assertIn(
            "shipUIIndicatesShipIsWarpingOrJumping", body,
            "the hover decides for itself what a warp is, so it can disagree "
            "with the branch it is supposed to run inside")

    def test_the_status_line_reports_the_count_the_give_up_uses(self):
        # Run 32's operator could watch `tooltip unanswered` climb to 5 and had
        # no way to see that it was the hover count, not the readings, that
        # decides. Both are printed now.
        collapsed = collapse(self.source)
        self.assertIn('++ ", hovers spent " ++ String.fromInt ammoSwap.hoverAttemptsSpent',
                      collapsed,
                      "the status line no longer carries the count the give-up "
                      "is decided on")

    def test_the_give_up_says_it_asked_at_more_than_one_moment(self):
        # The sentence an operator reads. "the tooltip never appeared" was true
        # of five readings and read as true of the session.
        collapsed = collapse(self.source)
        self.assertIn("separate hovers asked at different moments", collapsed,
                      "the give-up no longer says how many hovers it rests on")
        self.assertNotIn("the weapon's tooltip never appeared", collapsed,
                         "the give-up still claims the tooltip never appeared "
                         "on the strength of one hover")


class TheHoverCountIsBoundedAndAdvances(unittest.TestCase):
    """The two new memory fields, checked the way the three counters are.

    `hoverAttemptsSpent` is a bound, so `test_ammo_silenced_bound` owns its
    arithmetic; what is asserted here is the pair of things that file cannot
    see -- that the flag really is cleared by leaving a warp, and that the
    give-up reads the count after this reading's increment rather than before.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_per_warp_flag_clears_when_the_ship_is_not_warping(self):
        body = collapse(let_binding(self.source, "hoverAttemptSpentThisWarp"))
        self.assertIn(
            "if not shipIsWarping then False", body,
            "the per-warp flag no longer clears on leaving a warp, so a "
            "session gets one hover in its first warp and none after")

    def test_the_give_up_reads_this_reading_s_count(self):
        body = collapse(let_binding(self.source, "optimalRangeGivenUp"))
        self.assertIn(
            "{ hoverAskCase | attemptsSpent = hoverAttemptsSpent }", body,
            "the give-up reads the count from before this reading, so it fires "
            "one reading late and the last hover is never counted")

    def test_the_hover_that_ran_out_stops_awaiting(self):
        # Otherwise the bot keeps holding the fight still on a hover whose
        # budget is gone, with the counter reset under it -- an unbounded wait
        # wearing a bounded counter, which is #34's shape.
        body = collapse(let_binding(self.source, "hoverAwaitingTooltip"))
        self.assertIn(
            "hoverStillAwaitingTooltip && not hoverAttemptRanOut", body,
            "a spent hover keeps waiting")


if __name__ == "__main__":
    unittest.main()
