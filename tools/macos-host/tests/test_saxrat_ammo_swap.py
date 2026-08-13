"""Tests for saxrat's ammo swap, ported from the mission runner around the
tooltip rather than through it.

Issue #122. `ammoSwap` appears 165 times in the mission runner and appeared zero
times here, along with `Charge`, `chargeName` and `optimalRange`: the capability
was absent rather than unconfigured, and none of `short-range-ammo`,
`long-range-ammo` or `ammo-swap-range` existed in the settings. Nothing
structural blocked the port -- neither app's `ParseUserInterface` exposes charges,
and the mission runner's swap is built entirely on tooltip and menu interaction.

**The tooltip half is deliberately not here, and `TheTooltipHalfIsAbsentTest`
pins that rather than leaving it to be noticed.** The mission runner derives a
crossover distance from a weapon's optimal range, read by resting the mouse on a
module until a flyout appears; that hover is the fragile half (two issues against
it, one still open) and it is only ever asked when `ammo-swap-range` is unset. So
requiring the setting here makes the whole hover unreachable, and porting it
would have been porting dead code. What that costs is that saxrat never refines
its crossover and uses the number it is given -- the mission runner's #128, and
the trade the mission runner already makes on every run where the setting is set.

**The swap's own safety came across whole**, and most of these cases are about
that half:

  - `ammoSwapLoadIsTrusted` records the charge a dispatched load asked for as the
    charge in the gun, which is sound *only* because `loadRefusalFromGameLog`
    reads the client saying otherwise. The mission runner's run 22 recorded 134
    of those refusals when every load was going into a running gun; its run 26
    recorded none against 819 satisfied readings. `TheRefusalMatcherTest` and
    `TheTrustRuleReadsTheRefusalTest` are the pair: one checks the wording
    against real recorded lines, the other checks that the wiring between them
    exists, because a port that keeps the trust rule and drops the matcher would
    compile and would start reporting charges the guns do not have.
  - `ammoSwapDisarmDamageBudget` reads its configured setting rather than any
    scaled threshold, at every call site.
  - `ammoSwapRangeErrorPercent`'s documented weakness carries over unchanged.

**One rule here has no counterpart in the mission runner**, and it is the only
part of the port that is new rather than moved. saxrat's `clearStrayContextMenu`
presses Escape at a context menu that has sat at the same cascade depth for three
readings, from above every other decision -- and the swap holds a weapon's menu
open across a settle of exactly that length. `TheStrayMenuGuardTest` covers both
directions: the guard still clears a genuinely stray menu, and it no longer
closes the one the load is about to be clicked out of. Run 10 is the observation
that rule was written for, and it says the rule is right: the guard suppressed
itself through every swap in that run.

**Two classes here are issue #154**, which the same run found. Run 10 latched the
whole feature off 21 readings in, on a sentence saying the guns were still off,
with its own status clause reading `a gun has been switched back on ... the guns
are firing` on the same reading and the seventeen before it.
`TheDisarmLatchAsksWhetherTheGunsCameBackTest` covers the narrowed verdict and
`TheGiveUpIsRetriedAfterAWarpTest` the unlatch. `TheRecordedSaxratRunsTest` is
what those rest on, and it no longer says the corpus is silent about ammo --
that was true when the port shipped and expired the moment it flew.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives: a Python restatement of a rule tests the restatement. The wiring, the
placement and the counters' arithmetic -- which are not expressions and cannot be
evaluated -- are read out of the source through a whitespace-collapsing reader,
so an `elm-format` pass cannot break them.

Nothing here reads a live game client or drives a bot. The corpus cases read the
recorded saxrat runs and only read them; they skip with a stated reason on a
machine that has none, and they glob the runs rather than numbering them, so a
new one is read without an edit.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, game_log, source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# Quoted verbatim from the mission runner's recorded runs. The first is the one
# the swap has to act on; the rest are the other refusals the same client made,
# and are here to keep the matcher from widening into them.
LOAD_REFUSAL = (
    "You cannot load or unload Focused Modulated Medium Energy Beam I "
    "while it is active.")

LOAD_REFUSAL_OTHER_FITTING = (
    "You cannot load or unload 425mm AutoCannon II while it is active.")

OTHER_REFUSALS = [
    "You cannot launch Acolyte I because you are already controlling 5 drones, "
    "as much as you have skill to.",
    "You cannot do that while warping.",
    "You cannot do that while docking.",
    "You cannot activate that module as the target is no longer present.",
]

# The mission runner's decision line for the branch that issues nothing while
# the ship is in warp, and saxrat's. Counted rather than described in
# `TheRecordedSaxratRunsTest`, because the issue's premise about this bot's warp
# behaviour is the one thing in it the corpus can answer.
SAXRAT_IN_WARP = "HOOOOONK in warp"

# The two ammo status clauses that separate a ship that is disarmed from one
# that is not. The bot prints one or the other on every reading an attempt is
# live, and issue #154 is that the give-up beside them read neither.
GUNS_OFF_CLAUSE = "GUNS OFF for "
GUNS_BACK_ON_CLAUSE = "a gun has been switched back on "
DISARM_GIVE_UP = "the guns were switched off to load"

# An `AmmoSwapConfig` for the two rules that render a sentence from one.
_CONFIG = ('{ shortRangeAmmoName = "Multifrequency M"'
           ', longRangeAmmoName = "Radio M"'
           ', threshold = { crossoverInMeters = 29000, deadbandInMeters = 3000 } }')


def without_comments(text):
    """The same source with its `--` line comments dropped.

    Every case asserting a branch is *absent* needs this: `collapsed` puts a
    comment on the same line as the code, and the comments here name the halves
    deliberately left elsewhere.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def code_only(text):
    """The source with its doc comments and `--` lines dropped.

    Needed by any case counting *uses* of a name across a whole file: this file
    discusses the tooltip half at length in its doc comments, so a count over
    the raw text cannot tell a mention from a use.
    """
    return without_comments(re.sub(r"\{-.*?-\}", "", text, flags=re.DOTALL))


def declaration(name, path=SAXRAT_BOT_ELM):
    return collapsed(without_comments(body_of(source_of(path), name)))


def doc_of(marker, path=SAXRAT_BOT_ELM):
    """The `{-| ... -}` comment immediately above a declaration.

    `body_of` starts at the type annotation, so a case about what an argument
    *says* cannot use it -- and a `type alias` has no annotation to key on at
    all. The comment is taken as the last one before `marker`, which is what
    "the doc comment for this declaration" means in Elm.
    """
    source = source_of(path)
    before = source[:source.index(marker)]
    return before[before.rindex("{-|"):]


def let_binding(body, name):
    """One `let` binding out of an already-collapsed declaration body.

    From `<name> =` to the next binding, skipping the record fields that share
    the name -- `, loadRefusedByClient = loadRefusedByClient` is the trust rule
    being handed the binding, not the binding itself.
    """
    starts = [match.end() for match in
              re.finditer(r"([,{]?) %s = " % re.escape(name), body)
              if match.group(1) == ""]
    assert starts, "no let binding named %r" % name
    rest = body[starts[0]:]
    end = re.search(r" [a-z][A-Za-z]* = ", rest)
    return rest if end is None else rest[:end.start()]


def indented_let_binding(declaration_name, name, path=SAXRAT_BOT_ELM):
    """One `let` binding, sliced by indentation rather than by the next `=`.

    `let_binding` above ends at the next ` <name> = `, which a *record literal*
    inside the binding satisfies -- so a binding whose body builds a record is
    truncated at its first field, and an assertion about anything past that
    field passes vacuously. That is what bit here: the give-up hands
    `ammoSwapDisarmEndsTheSession` a two-field record, and a case asserting
    which value reaches the second field read text that stopped at the brace.

    So this reads the raw source, takes the line the binding opens on, and ends
    at the next non-blank line indented no further -- the same correction #147
    made for a `let` binding it was reading with a regex.
    """
    lines = body_of(source_of(path), declaration_name).splitlines()
    opens = [index for index, line in enumerate(lines)
             if re.match(r"^(\s*)%s =(\s|$)" % re.escape(name), line)]
    assert opens, "no let binding named %r" % name
    start = opens[0]
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            end = index
            break
    return collapsed(without_comments("\n".join(lines[start:end])))


def int_constant(name, path=SAXRAT_BOT_ELM):
    """A constant read out of `Bot.elm`, so a case tests the shipped number."""
    return int(re.search(r"\n%s =\s*(\d+)" % name,
                         "\n" + body_of(source_of(path), name)).group(1))


def load_refusal_substrings(path=SAXRAT_BOT_ELM):
    """The substrings `loadRefusalFromGameLog` actually matches on.

    Read out of the Elm rather than restated, so that changing the matcher
    without checking it against real lines fails here.
    """
    return re.findall(r'stringContainsIgnoringCase "([^"]+)"',
                      body_of(source_of(path), "loadRefusalFromGameLog"))


def matches(text, substrings):
    """What `loadRefusalFromGameLog`'s filter does, on one line of text."""
    return all(sub.lower() in text.lower() for sub in substrings)


def settings(short="Just \"Multifrequency M\"", long="Just \"Radio M\"",
             crossover="Just 29000"):
    return ("{ shortRangeAmmoName = %s, longRangeAmmoName = %s"
            ", ammoSwapRangeMeters = %s }" % (short, long, crossover))


def disarm_case(threshold=3500, range_error="Nothing", damage=0,
                carried="True"):
    """An `AmmoSwapDisarmCase` with a window of `damage` in one sample."""
    return ("{ runAwayIncomingDamageThreshold = %d"
            ", rangeErrorPercent = %s"
            ", incomingDamage = { samples = [ { atMilliseconds = 0"
            ", damage = %d, hitpoints = Nothing, attacker = Nothing } ]"
            ", hostCarriesTheChannel = %s, lastAttacker = Nothing"
            ", retreating = False } }" % (threshold, range_error, damage,
                                          carried))


def trust_case(same_verdict="True", every_gun="True", dispatched="True",
               refused="Nothing", contradicted="False"):
    return ("{ verdictIsTheSameOneAsBefore = %s, everyGunVisited = %s"
            ", loadWasDispatched = %s, loadRefusedByClient = %s"
            ", menuContradictsTheLoad = %s }" % (
                same_verdict, every_gun, dispatched, refused, contradicted))


class AmmoSwapNeedsAllThreeSettingsTest(unittest.TestCase):
    """`ammoSwapConfigFromSettings`, executed over every combination.

    This is the whole of "required rather than optional", and it is one function
    rather than two so that the gate and the status line cannot disagree about
    which settings are wanted. The `Err` naming the absent ones is the half that
    matters to an operator: a swap reporting itself off says nothing about
    whether that was a decision or a typo.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-config-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_all_three_present_is_the_only_configured_case(self):
        present = ["Just \"a\"", "Just \"b\"", "Just 29000"]
        absent = ["Nothing", "Nothing", "Nothing"]
        expressions = []
        for mask in range(8):
            chosen = [present[index] if mask & (1 << index) else absent[index]
                      for index in range(3)]
            expected = "True" if mask == 7 else "False"
            expressions.append(
                "(ammoSwapConfigFromSettings %s |> Result.toMaybe |> (/=) Nothing)"
                " == %s" % (settings(*chosen), expected))
        self.assertEqual(self.repl.evaluate(expressions), [True] * 8)

    def test_the_error_names_exactly_the_settings_that_are_missing(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapConfigFromSettings %s == Err [ \"ammo-swap-range\" ]"
                % settings(crossover="Nothing"),
                "ammoSwapConfigFromSettings %s == Err [ \"short-range-ammo\" ]"
                % settings(short="Nothing"),
                "ammoSwapConfigFromSettings %s == Err [ \"long-range-ammo\" ]"
                % settings(long="Nothing"),
                "ammoSwapConfigFromSettings %s == Err "
                "[ \"short-range-ammo\", \"long-range-ammo\", \"ammo-swap-range\" ]"
                % settings("Nothing", "Nothing", "Nothing"),
            ]),
            [True] * 4,
            "an operator who set two of the three has to be told which one is "
            "missing, and this is the only place that can say")

    def test_the_crossover_is_the_setting_and_the_deadband_the_constant(self):
        deadband = int_constant("ammoSwapDeadbandMeters")
        self.assertEqual(
            self.repl.evaluate([
                "(ammoSwapConfigFromSettings %s |> Result.map .threshold)"
                " == Ok { crossoverInMeters = 29000, deadbandInMeters = %d }"
                % (settings(), deadband)]),
            [True])

    def test_an_empty_ammo_name_switches_the_swap_off(self):
        # `short-range-ammo=` with nothing after it is how an operator turns the
        # swap off from the web console without deleting the line, and an empty
        # string would otherwise match every context-menu entry.
        self.assertEqual(
            self.repl.evaluate([
                "(parseBotSettings \"short-range-ammo=\\nlong-range-ammo=Radio M"
                "\\nammo-swap-range=29000\""
                " |> Result.map (ammoSwapConfigFromSettings >> Result.toMaybe))"
                " == Ok Nothing",
                "(parseBotSettings \"short-range-ammo=Multifrequency M"
                "\\nlong-range-ammo=Radio M\\nammo-swap-range=29000\""
                " |> Result.map (ammoSwapConfigFromSettings >> Result.toMaybe"
                " >> (/=) Nothing))"
                " == Ok True",
            ]),
            [True, True])

    def test_the_default_settings_leave_the_swap_off(self):
        self.assertEqual(
            self.repl.evaluate([
                "(ammoSwapConfigFromSettings defaultBotSettings"
                " |> Result.toMaybe) == Nothing"]),
            [True],
            "the shipped configuration must not swap ammo: an operator who "
            "never asked for it has no charges named for it to alternate")


class TheTrustRuleTest(unittest.TestCase):
    """`ammoSwapLoadIsTrusted`, executed, with each of its five inputs falsified.

    The swap dispatches a load and records the charge it asked for as the charge
    in the gun. Each of these five is a way that can be wrong, which is why they
    are named rather than inlined -- and why each gets its own case.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-trust-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_all_five_satisfied_is_trusted(self):
        self.assertEqual(
            self.repl.evaluate(["ammoSwapLoadIsTrusted %s" % trust_case()]),
            [True])

    def test_each_input_alone_withholds_the_trust(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (ammoSwapLoadIsTrusted %s)" % trust_case(same_verdict="False"),
                "not (ammoSwapLoadIsTrusted %s)" % trust_case(every_gun="False"),
                "not (ammoSwapLoadIsTrusted %s)" % trust_case(dispatched="False"),
                "not (ammoSwapLoadIsTrusted %s)"
                % trust_case(refused="Just \"%s\"" % LOAD_REFUSAL),
                "not (ammoSwapLoadIsTrusted %s)" % trust_case(contradicted="True"),
            ]),
            [True] * 5,
            "a conjunction that lost a term would still answer True for the "
            "all-true case, so each term is falsified on its own")

    def test_the_dispatch_is_read_from_the_previous_reading(self):
        # `loadCascadeReachedTheMenu` is true on the reading the cascade clicks
        # the charge entry. Read on that same reading, the verdict would be
        # satisfied before the click went out and the swap would be trusting a
        # load it never issued.
        body = declaration("updateAmmoSwapMemoryWithConfig")
        self.assertIn("loadWasDispatched = memoryBefore.loadCascadeReachedTheMenu",
                      body)
        self.assertNotIn("loadWasDispatched = loadCascadeReachedTheMenu", body)


class TheRefusalMatcherTest(unittest.TestCase):
    """The client's own sentence, matched on the two parts that do not vary.

    The weapon's name sits between them, so a whole-line match would be
    per-fitting; matching `cannot` alone would catch every other refusal the
    client makes. Both substrings are read out of `Bot.elm` rather than restated
    here, so a matcher that drifts from what the client writes fails here rather
    than in a run -- where it fails in the direction that looks like success.
    """

    @classmethod
    def setUpClass(cls):
        cls.substrings = load_refusal_substrings()
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-refusal-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_two_substrings_neither_naming_a_weapon(self):
        self.assertEqual(len(self.substrings), 2)
        for substring in self.substrings:
            self.assertNotIn("beam", substring.lower())
            self.assertNotIn("autocannon", substring.lower())

    def test_it_is_the_same_matcher_the_mission_runner_ships(self):
        # The sentence is the client's, not this bot's, so the two copies must
        # not be allowed to drift apart independently.
        self.assertEqual(
            self.substrings, load_refusal_substrings(MISSION_RUNNER_BOT_ELM))

    def test_it_matches_the_real_refusal_across_fittings_and_case(self):
        self.assertTrue(matches(LOAD_REFUSAL, self.substrings))
        self.assertTrue(matches(LOAD_REFUSAL_OTHER_FITTING, self.substrings))
        self.assertTrue(matches(LOAD_REFUSAL.upper(), self.substrings))

    def test_it_matches_none_of_the_client_s_other_refusals(self):
        for refusal in OTHER_REFUSALS:
            self.assertFalse(
                matches(refusal, self.substrings),
                "%r must not reach the ammo branch" % refusal)

    def test_executed_against_a_real_parsed_reading(self):
        # Through the real parser rather than against a hand-built record, so a
        # channel filter that stopped working would show up here.
        self.assertEqual(
            self.repl.evaluate(
                ["(refused |> Maybe.andThen loadRefusalFromGameLog) == Just %s"
                 % ('"%s"' % LOAD_REFUSAL),
                 "(drones |> Maybe.andThen loadRefusalFromGameLog) == Nothing",
                 "(quiet |> Maybe.andThen loadRefusalFromGameLog) == Nothing"],
                definitions=[
                    self.repl.reading_binding(
                        "refused", [game_log([("notify", LOAD_REFUSAL)])]),
                    self.repl.reading_binding(
                        "drones", [game_log([("notify", OTHER_REFUSALS[0])])]),
                    self.repl.reading_binding("quiet", []),
                ]),
            [True] * 3)

    def test_an_absent_game_log_is_not_a_load_that_worked(self):
        # `Nothing` and `Just []` are collapsed, which is safe only because of
        # the direction of the inference: no refusal is never read as the load
        # having been accepted. The trust rule needs four other things.
        self.assertEqual(
            self.repl.evaluate([
                "not (ammoSwapLoadIsTrusted %s)"
                % trust_case(dispatched="False", refused="Nothing")]),
            [True])


class TheTrustRuleReadsTheRefusalTest(unittest.TestCase):
    """The wiring between the two, which is what a port can silently drop.

    Porting `ammoSwapLoadIsTrusted` without `loadRefusalFromGameLog` compiles
    and type-checks: the trust rule takes a `Maybe String` and `Nothing` is a
    perfectly good value for it. What it produces is a swap that reports charges
    the guns do not have, which is the exact failure the removed menu read
    existed to prevent -- so the connection is asserted rather than assumed.
    """

    def setUp(self):
        self.update = declaration("updateAmmoSwapMemoryWithConfig")
        # The trust rule's own argument, sliced out rather than searched for in
        # the whole declaration. The record this function *returns* carries a
        # `loadRefusedByClient = loadRefusedByClient` field too, and an
        # assertion over the whole body is satisfied by that one while the trust
        # rule is being handed `Nothing` -- which is this port's worst available
        # failure and was passing until a mutation caught it.
        start = self.update.index("loadIsTrusted = ammoSwapLoadIsTrusted")
        self.trust_call = self.update[start:self.update.index("}", start) + 1]

    def test_the_refusal_reaches_the_trust_rule(self):
        self.assertIn("loadRefusedByClient = loadRefusedByClient",
                      self.trust_call)

    def test_the_trust_rule_is_given_all_five_of_its_inputs(self):
        # Each is a way the trust can be wrong. One handed a constant is a term
        # that has stopped participating, which type-checks.
        for field in ("verdictIsTheSameOneAsBefore", "everyGunVisited",
                      "loadWasDispatched", "loadRefusedByClient",
                      "menuContradictsTheLoad"):
            self.assertRegex(
                self.trust_call,
                r"%s = (?!True\b|False\b|Nothing\b)" % field,
                "%s is being handed a constant rather than this reading's "
                "answer" % field)

    def test_the_refusal_is_read_from_the_game_log(self):
        self.assertIn(
            "loadRefusalFromGameLog context.readingFromGameClient", self.update)

    def test_the_matcher_is_the_only_source_of_the_refusal(self):
        # A binding assembled from anything else would be a second opinion about
        # whether the client refused, and only one of them would be the client.
        binding = let_binding(self.update, "loadRefusedByClient")
        self.assertIn("loadRefusalFromGameLog", binding)
        self.assertIn("memoryBefore.loadRefusedByClient", binding)
        for other in ("verdictAbandoned", "gunsSilencedTicks", "menuWasRead"):
            self.assertNotIn(
                other, binding,
                "the client's own sentence is the whole evidence here, and %s "
                "is the bot's opinion about something else" % other)

    def test_the_refusal_is_asked_before_the_trust(self):
        # A refusal arriving one reading after the click has to un-satisfy a
        # verdict the trust already closed, so it is tested above `loadIsTrusted`
        # in `verdictSatisfied`.
        satisfied = self.update[self.update.index("verdictSatisfied ="):]
        satisfied = satisfied[:satisfied.index("chargeLoadedOrAssumed =")]
        self.assertLess(satisfied.index("loadRefusedByClient /= Nothing"),
                        satisfied.index("loadIsTrusted"))

    def test_the_refusal_also_abandons_the_attempt(self):
        abandoned = self.update[self.update.index("verdictAbandoned ="):]
        abandoned = abandoned[:abandoned.index("givenUpReadingsAgo =")]
        self.assertIn("loadRefusedByClient /= Nothing", abandoned)

    def test_the_matcher_doc_comment_still_says_what_rests_on_it(self):
        # Somebody editing the matcher is not reading a test file. The argument
        # has to be where the code is.
        doc = doc_of("loadRefusalFromGameLog : ReadingFromGameClient")
        self.assertIn("ammoSwapLoadIsTrusted", doc)
        self.assertIn("charge the gun does not have", doc)


class TheDisarmBudgetReadsTheConfiguredSettingTest(unittest.TestCase):
    """`ammoSwapDisarmDamageBudget`, and where its scale comes from.

    An eighth of `run-away-incoming-damage-threshold`, read from the setting an
    operator wrote. The mission runner kept all three of its call sites on
    `botSettings` deliberately: its retreat scales its own threshold per session
    from the ship's derived shield pool, and letting this budget follow that
    scaling would move it past the window the recordings show damage starting to
    escalate at. Nothing in saxrat scales anything yet, so the constraint is
    presently free -- which is exactly why it is asserted, since the port that
    adds the scaling is the one that would sweep this up.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-budget-")
        cls.divisor = int_constant("ammoSwapDisarmDamageBudgetDivisor")
        cls.worthwhile = int_constant("ammoSwapWorthwhileRangeErrorPercent")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_budget_is_the_share_of_the_setting(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapDisarmDamageBudget %s == %d"
                % (disarm_case(threshold=3500,
                               range_error="Just %d" % self.worthwhile),
                   3500 // self.divisor)]),
            [True])

    def test_a_gain_below_the_worthwhile_percent_buys_nothing(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapDisarmDamageBudget %s == 0"
                % disarm_case(range_error="Just %d" % (self.worthwhile - 1)),
                "ammoSwapDisarmDamageBudget %s == %d"
                % (disarm_case(range_error="Just %d" % self.worthwhile),
                   3500 // self.divisor),
            ]),
            [True, True],
            "both sides of the boundary, because a comparison moved by one is "
            "the mutation this case exists to catch")

    def test_an_unmeasurable_gain_buys_nothing(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapDisarmDamageBudget %s == 0"
                % disarm_case(range_error="Nothing")]),
            [True])

    def test_a_disabled_retreat_is_not_a_budget(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapDisarmDamageBudget %s == 0"
                % disarm_case(threshold=-1,
                              range_error="Just %d" % self.worthwhile)]),
            [True],
            "a share of a disabled number is not a budget, and it must never "
            "be negative -- which would license disarming through any fire")

    def test_every_call_site_takes_the_setting(self):
        source = code_only(source_of(SAXRAT_BOT_ELM))
        assignments = re.findall(
            r"runAwayIncomingDamageThreshold =\s*([A-Za-z.]+)", source)
        self.assertTrue(assignments, "no disarm case is being built at all")
        for assignment in assignments:
            self.assertTrue(
                assignment.endswith("botSettings.runAwayIncomingDamageThreshold")
                or assignment == "defaultRunAwayIncomingDamageThreshold"
                or assignment == "threshold",
                "%r is not the operator's setting" % assignment)

    def test_nothing_derives_a_scaled_threshold_to_take_a_share_of(self):
        source = code_only(source_of(SAXRAT_BOT_ELM))
        for scaled in ("shieldPoolThreshold", "scaledRunAwayThreshold",
                       "derivedIncomingDamageThreshold"):
            self.assertNotIn(scaled, source)


class TheDisarmGateTest(unittest.TestCase):
    """`swapMayDisarmTheGuns`: what the swap gains against what it would cost.

    A swap is an optimisation; the tank is not. The mission runner's run 11
    began one on a ship already absorbing 1679 hitpoints a window at 26% shield
    and reached zero shield before its bound fired.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-disarm-")
        cls.worthwhile = int_constant("ammoSwapWorthwhileRangeErrorPercent")
        cls.budget = 3500 // int_constant("ammoSwapDisarmDamageBudgetDivisor")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _may(self, **kwargs):
        return "swapMayDisarmTheGuns %s" % disarm_case(**kwargs)

    def test_a_quiet_window_passes_whatever_the_gain(self):
        self.assertEqual(
            self.repl.evaluate([
                self._may(damage=0, range_error="Nothing"),
                self._may(damage=0, range_error="Just 0"),
            ]),
            [True, True],
            "the budget is never negative, so nothing the previous rule "
            "permitted is refused")

    def test_it_declines_at_one_hitpoint_over_the_budget(self):
        gain = "Just %d" % self.worthwhile
        self.assertEqual(
            self.repl.evaluate([
                self._may(damage=self.budget, range_error=gain),
                "not (%s)" % self._may(damage=self.budget + 1, range_error=gain),
            ]),
            [True, True])

    def test_an_absent_channel_declines_whatever_the_numbers(self):
        # A host that cannot answer gets the answer that keeps the guns firing.
        # `Nothing` and `Just 0` are different facts and only one of them may be
        # read as "the grid is quiet".
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._may(damage=0, carried="False",
                                       range_error="Just 100")]),
            [True])

    def test_the_sentence_and_the_rule_take_the_same_case(self):
        # Two values would be two things that could disagree about why the swap
        # is standing still.
        rule = declaration("swapMayDisarmTheGuns")
        sentence = declaration("describeWhyTheSwapMayNotDisarm")
        self.assertIn("AmmoSwapDisarmCase -> Bool", rule)
        self.assertIn("AmmoSwapDisarmCase -> String", sentence)


class TheRangeErrorWeaknessTest(unittest.TestCase):
    """`ammoSwapRangeErrorPercent`, and the weakness that carries over unchanged.

    It is the swap's only measurement of what it stands to gain and it is a poor
    one: what decides whether the other charge is better is whether the guns are
    landing, which turns on tracking and angular velocity as much as distance.
    The mission runner says so in the function's own doc comment and this port
    does not fix it, so this port has to say so too.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-ammo-range-error-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _percent(self, crossover, distance):
        return ("ammoSwapRangeErrorPercent (Just { crossoverInMeters = %s"
                ", deadbandInMeters = 3000 }) %s" % (crossover, distance))

    def test_it_is_the_distance_from_the_crossover_as_a_share_of_it(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just 0" % self._percent(29000, "(Just 29000)"),
                "%s == Just 50" % self._percent(29000, "(Just 43500)"),
                "%s == Just 100" % self._percent(29000, "(Just 58000)"),
                "%s == Just 50" % self._percent(29000, "(Just 14500)"),
            ]),
            [True] * 4,
            "symmetric about the crossover: being too close is as wrong as "
            "being too far, and the other charge is better either way")

    def test_no_distance_and_no_crossover_answer_nothing(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % self._percent(29000, "Nothing"),
                "ammoSwapRangeErrorPercent Nothing (Just 29000) == Nothing",
                "%s == Nothing" % self._percent(0, "(Just 29000)"),
            ]),
            [True] * 3,
            "a crossover of zero is a division, not a swap -- and `Nothing` is "
            "a real answer here rather than a zero")

    def test_the_doc_comment_still_states_the_weakness(self):
        doc = doc_of("ammoSwapRangeErrorPercent : Maybe AmmoSwapThreshold")
        self.assertIn("landing", doc)
        self.assertIn("tracking", doc)


class TheTooltipHalfIsAbsentTest(unittest.TestCase):
    """The half of the mission runner's swap that was deliberately not ported.

    Asserted as a relation between the two files rather than as a count in this
    one: the mission runner has this machinery and saxrat does not, which is the
    claim. A count of zero on its own would also pass on a file where the swap
    itself had been deleted.
    """

    @classmethod
    def setUpClass(cls):
        cls.saxrat = code_only(source_of(SAXRAT_BOT_ELM))
        cls.mission = code_only(source_of(MISSION_RUNNER_BOT_ELM))

    def test_the_mission_runner_has_the_hover_and_saxrat_does_not(self):
        for name in ("weaponOptimalRangeFromHover", "hoverWeaponForOptimalRange",
                     "weaponTooltipIsWorthAsking", "hoverAwaitingTooltip",
                     "readWeaponOptimalRangeWhileWarping",
                     "optimalRangeGivenUp", "ammoSwapBootstrapThreshold"):
            self.assertIn(name, self.mission,
                          "%s is what this port declined to bring across, so "
                          "the mission runner having it is the premise" % name)
            self.assertNotIn(name, self.saxrat)

    def test_saxrat_reads_no_module_tooltip_at_all(self):
        self.assertNotIn("moduleButtonTooltip", self.saxrat)
        self.assertNotIn("mouseMoveToUIElement", self.saxrat)

    def test_saxrat_still_has_the_swap_it_is_missing_the_hover_from(self):
        for name in ("ammoSwapLoadIsTrusted", "loadRefusalFromGameLog",
                     "swapMayDisarmTheGuns", "ensureAmmoSuitsTargetRange"):
            self.assertIn(name, self.saxrat)

    def test_the_crossover_has_exactly_one_source(self):
        # With `ammo-swap-range` required there is nothing to bootstrap from and
        # nothing to bootstrap to, so an `AmmoSwapThreshold` can only be built
        # where the setting is read.
        built = re.findall(r"crossoverInMeters = ([A-Za-z.]+)", self.saxrat)
        self.assertEqual(set(built), {"crossoverInMeters"},
                         "a second way to build a crossover would be a second "
                         "answer to where the swap changes its mind")

    def test_the_cost_of_declining_it_is_written_down(self):
        # An operator finding out later that the crossover never moves is the
        # failure this port is most likely to be blamed for, so the trade is in
        # the doc comment rather than only in a pull request.
        doc = doc_of("type alias AmmoSwapThreshold")
        self.assertIn("never refines its", doc)
        self.assertIn("crossover", doc)
        self.assertIn("#128", doc)


class TheStrayMenuGuardTest(unittest.TestCase):
    """`strayContextMenuIsStray`: the one rule this port had to add rather than
    move.

    saxrat presses Escape at a context menu that has sat at the same cascade
    depth for `strayContextMenuStuckTicksThreshold` readings, from above every
    other decision -- and the swap holds a weapon's menu open across a settle of
    exactly that length while it waits for the guns to go quiet. Without this
    the two take turns: Escape closes the menu, the swap re-opens it, and the
    attempt runs out its bound having loaded nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-stray-menu-")
        cls.threshold = int_constant("strayContextMenuStuckTicksThreshold")
        cls.settle = int_constant("ammoSwapSilenceSettleTicks")
        cls.verdict_bound = int_constant("ammoSwapVerdictGiveUpTicks")
        cls.silence_bound = int_constant("ammoSwapSilencedGiveUpTicks")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _stray(self, ticks, owns):
        return ("strayContextMenuIsStray { stuckTicks = %d"
                ", ammoSwapOwnsTheMenu = %s }" % (ticks, owns))

    def test_it_still_clears_a_menu_nobody_is_driving(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._stray(self.threshold - 1, "False"),
                self._stray(self.threshold, "False"),
                self._stray(self.threshold + 1, "False"),
            ]),
            [True] * 3,
            "the guard this bot already had, unchanged in the case it was "
            "written for -- both sides of its boundary")

    def test_it_leaves_the_swap_s_own_menu_alone(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._stray(self.threshold, "True"),
                "not (%s)" % self._stray(self.silence_bound, "True"),
            ]),
            [True, True])

    def test_the_settle_is_long_enough_to_have_tripped_the_guard(self):
        # This is why the clause exists rather than being defensive: the swap
        # holds a menu for at least as many readings as the guard waits.
        self.assertLessEqual(
            self.threshold, self.settle,
            "if the settle were shorter than the guard's patience the swap "
            "could never have tripped it, and this clause would be unmotivated")

    def test_the_suppression_is_bounded_by_the_swap_s_own_deadlines(self):
        # The guard's promise is that a menu cannot sit forever. That survives
        # because `ammoSwapIsActingOnAVerdict` is false once the verdict is
        # satisfied or abandoned, and both deadlines abandon it.
        self.assertGreater(self.verdict_bound, self.threshold)
        self.assertGreater(self.verdict_bound, self.silence_bound,
                           "the dangerous state has to time out first")
        acting = declaration("ammoSwapIsActingOnAVerdict")
        self.assertIn("not ammoSwap.verdictSatisfied", acting)
        self.assertIn("not ammoSwap.verdictAbandoned", acting)

    def test_the_branch_asks_the_rule_and_nothing_else_compares_the_threshold(self):
        branch = declaration("clearStrayContextMenu")
        self.assertIn("strayContextMenuIsStray", branch)
        self.assertNotIn("strayContextMenuStuckTicksThreshold", branch)
        source = code_only(source_of(SAXRAT_BOT_ELM))
        self.assertEqual(
            source.count("strayContextMenuStuckTicksThreshold <="), 1,
            "one comparison, so two places cannot disagree about whether a "
            "menu is stray")


class TheSilenceDeadlineIsUnstallableTest(unittest.TestCase):
    """`gunsSilencedTicks`, which bounds the whole period the ship is disarmed.

    The mission runner's issue #34: the shape this replaces reset whenever no
    gun *read* as firing, so a weapon flickering between cycles held it at 1
    forever, and the phase behind it had no counter and ran for 298 readings.
    Asserting what the counter *mentions* is not enough -- a counter pinned at a
    constant mentions everything it should -- so every branch is checked to
    evaluate to one of four values.
    """

    def setUp(self):
        self.update = declaration("updateAmmoSwapMemoryWithConfig")
        start = self.update.index("gunsSilencedTicks =")
        self.body = self.update[start:self.update.index("gunStates =", start)]

    def test_every_branch_is_zero_one_or_the_previous_value_plus_one(self):
        answers = re.findall(
            r"(?:then|else)\s+(memoryBefore\.gunsSilencedTicks \+ 1|[01])\b",
            self.body)
        self.assertGreaterEqual(len(answers), 5)
        self.assertEqual(
            set(answers), {"0", "1", "memoryBefore.gunsSilencedTicks + 1"},
            "a branch answering anything else is a counter that can be stalled "
            "or pinned, which is what #34 was")

    def test_it_consults_nothing_the_module_says_about_itself(self):
        for reading in ("isActive", "rampRotationMilli", "moduleReadsSwitchedOff",
                        "gunsReadSwitchedOff", "weaponIsSwitchedOn"):
            self.assertNotIn(
                reading, self.body,
                "%s is a reading of the module, and a counter that consults "
                "the thing it is waiting out can be stopped by it" % reading)

    def test_it_advances_from_the_bot_s_own_dispatched_click(self):
        self.assertIn("swapJustCommandedAGunOff", self.body)
        self.assertIn("doEffectsClickModuleButton", self.update)

    def test_a_changed_verdict_does_not_reset_it(self):
        # A target drifting back across the deadband flips the verdict with the
        # guns still off, and a counter that restarted there would let a
        # flickering distance hold the ship disarmed indefinitely.
        self.assertNotIn("verdictIsTheSameOneAsBefore", self.body)

    def test_nothing_in_the_acting_path_waits(self):
        # Every state either acts or hands the fight back, so no state can sit
        # still while the guns are off. Run 8 is what a wait here costs.
        acting = declaration("ensureAmmoSuitsTargetRangeWithGuns")
        self.assertNotIn("waitForProgressInGame", acting)
        self.assertNotIn("askForHelpToGetUnstuck", acting)


class TheDisarmLatchAsksWhetherTheGunsCameBackTest(unittest.TestCase):
    """`ammoSwapDisarmEndsTheSession`, which is issue #154.

    saxrat's run 10 latched the whole feature off 21 readings into a three-hour
    run with:

        Ammo swap: given up -- the guns were switched off to load and were still
        not back 21 readings later.

    and on that same reading its own status line read `a gun has been switched
    back on 20 of 20 readings in -- the guns are firing`, as it had for the
    previous seventeen consecutive readings. `GUNS OFF` printed for readings 1
    to 3 of that attempt and never again: the ship was disarmed for three
    readings and the sentence claimed twenty-one.

    `gunsSilencedTicks` is right to consult nothing the module says (#34), and
    that is exactly why it cannot be read as a statement about the guns. So the
    *session* consequence asks the client's own latched answer instead, while
    the attempt bound is untouched -- PR #151's shape on `lockAttempt`,
    discharging an outcome on the rule's own terms rather than retuning a bound.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-disarm-latch-")
        cls.bound = int_constant("ammoSwapSilencedGiveUpTicks")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _ends(self, ticks, undone):
        return ("ammoSwapDisarmEndsTheSession { gunsSilencedTicks = %d"
                ", switchOffUndoneByClient = %s }" % (ticks, undone))

    def test_the_budget_still_ends_the_session_on_a_ship_left_disarmed(self):
        self.assertEqual(
            self.repl.evaluate([
                self._ends(self.bound + 1, "False"),
                self._ends(self.bound + 40, "False"),
                # A fixed value far past any plausible bound, so a constant that
                # simply admits everything above it is not what is being tested.
                self._ends(200, "False"),
            ]),
            [True] * 3,
            "run 6's shape: the guns went off, the client never reported one "
            "back on, and the budget expired. That is what this latch is for")

    def test_a_ship_whose_guns_the_client_gave_back_does_not_latch(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._ends(self.bound + 1, "True"),
                "not (%s)" % self._ends(self.bound + 40, "True"),
                "not (%s)" % self._ends(200, "True"),
            ]),
            [True] * 3,
            "run 10's shape: the budget expired on a firing ship, so the "
            "attempt is abandoned and the feature is not")

    def test_it_answers_at_both_sides_of_the_bound(self):
        self.assertEqual(
            self.repl.evaluate([
                "not (%s)" % self._ends(self.bound - 1, "False"),
                "not (%s)" % self._ends(self.bound, "False"),
                self._ends(self.bound + 1, "False"),
                # Fixed values either side, so a bound moved to something that
                # admits or refuses everything still fails here.
                "not (%s)" % self._ends(3, "False"),
                self._ends(60, "False"),
            ]),
            [True] * 5)
        self.assertGreater(
            self.bound, 3,
            "the fixed low value above has to sit under the shipped bound")
        self.assertLess(
            self.bound, 60,
            "and the fixed high value above has to sit over it")

    def test_the_attempt_is_still_abandoned_at_exactly_the_same_reading(self):
        # Nothing is loosened. The budget ends the attempt where it always did;
        # only what that costs afterwards is narrowed. A version that also
        # deferred the abandonment would hold the fight longer on no evidence.
        abandoned = indented_let_binding(
            "updateAmmoSwapMemoryWithConfig", "verdictAbandoned")
        self.assertIn(
            "ammoSwapSilencedGiveUpTicks < gunsSilencedTicks", abandoned)
        self.assertNotIn("switchOffUndoneByClient", abandoned)
        self.assertNotIn("ammoSwapDisarmEndsTheSession", abandoned)

    def test_the_session_verdict_asks_the_rule_and_compares_nothing_itself(self):
        reached = indented_let_binding(
            "updateAmmoSwapMemoryWithConfig", "giveUpReachedThisReading")
        self.assertIn("ammoSwapDisarmEndsTheSession", reached)
        self.assertNotIn(
            "ammoSwapSilencedGiveUpTicks <", reached,
            "one comparison, so the latch and the rule cannot disagree about "
            "when the budget expired")
        self.assertIn(
            "switchOffUndoneByClient = switchOffUndoneByClient", reached,
            "the rule has to be handed the client's own report that the guns "
            "came back -- `gunsConfirmedOff` is the same type and the opposite "
            "question, and would type-check here")

    def test_the_rule_reads_a_latch_rather_than_the_module(self):
        # #34's property has to survive this. `switchOffUndoneByClient` is
        # monotone within an attempt and cleared exactly where the counter is,
        # so unlike a live module read it cannot flicker -- and it is only ever
        # consulted to make the outcome milder.
        undone = indented_let_binding(
            "updateAmmoSwapMemoryWithConfig", "switchOffUndoneByClient")
        self.assertIn("memoryBefore.switchOffUndoneByClient then True", undone)
        for clearing in ("rangeVerdict == Nothing", "verdictSatisfied",
                         "memoryBefore.verdictAbandoned"):
            self.assertIn(
                clearing, undone,
                "cleared exactly where gunsSilencedTicks is, so it belongs to "
                "one attempt and cannot be inherited")
        rule = declaration("ammoSwapDisarmEndsTheSession")
        for reading in ("isActive", "moduleReadsSwitchedOff", "stateFromDictEntries",
                        "readingFromGameClient", "gunsConfirmedOff"):
            self.assertNotIn(
                reading, rule,
                "%s would make the rule a function of this reading's module "
                "state, which is the thing #34 refused" % reading)

    def test_the_sentence_no_longer_claims_readings_the_ship_was_not_disarmed(self):
        [charge, guns] = self.repl.strings([
            'describeAmmoSwapGiveUp %s ShipCarriesNeitherCharge' % _CONFIG,
            'describeAmmoSwapGiveUp %s (GunsDidNotComeBack 21)' % _CONFIG,
        ])
        self.assertIn("Multifrequency M", charge)
        self.assertIn("Radio M", charge)
        self.assertIn("21", guns)
        self.assertIn("that attempt", guns)
        self.assertNotIn(
            "still not back", guns,
            "run 10's wording said the guns were still off after a count that "
            "measures the attempt, not the silence")


class TheGiveUpIsRetriedAfterAWarpTest(unittest.TestCase):
    """`ammoSwapGiveUpAfterReading`: a single failure no longer ends a
    three-hour session.

    Run 10 spent 3,832 status lines reporting the swap `off for this session`
    after a single 21-reading attempt in its first minutes. A warp means a new
    pocket and a fresh fight, and it is a signal both bots already read.

    The two verdicts end differently on purpose, and that is the whole of this
    class: `ShipCarriesNeitherCharge` is a fact about the ship's hold that a
    warp cannot change, so retrying it buys a menu cascade per pocket and the
    same answer each time.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl, prefix="saxrat-giveup-warp-")

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    @staticmethod
    def _after(before, reached="Nothing", warping="False"):
        return ("ammoSwapGiveUpAfterReading { before = %s"
                ", reachedThisReading = %s, justFinishedWarping = %s }"
                % (before, reached, warping))

    def test_only_the_disarm_verdict_is_retryable(self):
        self.assertEqual(
            self.repl.evaluate([
                "ammoSwapGiveUpSurvivesAWarp ShipCarriesNeitherCharge",
                "not (ammoSwapGiveUpSurvivesAWarp (GunsDidNotComeBack 21))",
                "not (ammoSwapGiveUpSurvivesAWarp (GunsDidNotComeBack 200))",
            ]),
            [True] * 3,
            "a hold carrying neither charge is not something a warp changes")

    def test_the_disarm_verdict_is_cleared_by_a_warp_and_by_nothing_else(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % self._after(
                    "Just (GunsDidNotComeBack 21)", warping="True"),
                "%s == Just (GunsDidNotComeBack 21)" % self._after(
                    "Just (GunsDidNotComeBack 21)", warping="False"),
            ]),
            [True, True],
            "the latch stands on every reading that is not the end of a warp, "
            "so it is not simply absent")

    def test_the_charge_verdict_survives_a_warp(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just ShipCarriesNeitherCharge" % self._after(
                    "Just ShipCarriesNeitherCharge", warping="True"),
            ]),
            [True])

    def test_a_verdict_reached_on_a_warp_reading_is_not_cleared_by_it(self):
        # The reading a swap is given up on can itself be the reading a warp
        # ends. Clearing there would drop a verdict formed after the warp, and
        # the attempt would have been spent for nothing.
        self.assertEqual(
            self.repl.evaluate([
                "%s == Just (GunsDidNotComeBack 21)" % self._after(
                    "Nothing", reached="Just (GunsDidNotComeBack 21)",
                    warping="True"),
                "%s == Nothing" % self._after("Nothing", warping="True"),
            ]),
            [True, True])

    def test_folded_over_a_session_the_latch_returns_once_per_warp(self):
        # A run's shape rather than one reading: give up, hold it across a
        # pocket's worth of readings, come back on the warp, and do it again.
        readings = (["False"] * 8 + ["True"] + ["False"] * 8
                    + ["True"] + ["False"])
        fold = (
            "List.foldl (\\warping before -> ammoSwapGiveUpAfterReading "
            "{ before = before, reachedThisReading = "
            "(if before == Nothing then Just (GunsDidNotComeBack 21) "
            "else Nothing), justFinishedWarping = warping }) "
            "(Just (GunsDidNotComeBack 21)) [ %s ]" % ", ".join(readings))
        self.assertEqual(
            self.repl.evaluate(["%s == Just (GunsDidNotComeBack 21)" % fold]),
            [True],
            "each warp clears it and the very next reading latches it again, "
            "so the session ends holding one -- retried, not abandoned")

    def test_the_status_line_says_which_of_the_two_it_is(self):
        # Run 10's operator read `off for this session` 3,832 times about a
        # verdict a warp would have cleared, with no way to know which it was.
        clause = declaration("describeAmmoSwapState")
        self.assertIn("ammoSwapGiveUpSurvivesAWarp giveUp", clause)
        self.assertIn('"off for this session"', clause)
        self.assertIn('"off until the next warp"', clause)

    def test_the_decision_line_and_the_status_line_share_one_sentence(self):
        for reader in ("describeAmmoSwapState", "ensureAmmoSuitsTargetRange"):
            self.assertIn(
                "describeAmmoSwapGiveUp config giveUp", declaration(reader),
                "%s has to render the case rather than carry its own wording, "
                "or the two can describe one verdict differently" % reader)
        source = code_only(source_of(SAXRAT_BOT_ELM))
        self.assertEqual(
            source.count("describeAmmoSwapGiveUp config giveUp"), 3,
            "the two readers above and the one definition, and nothing else")

    def test_nothing_stores_the_sentence_beside_the_case(self):
        # A `Maybe String` was the old shape and it is what let the give-up go
        # on claiming for 3,832 status lines something the memory beside it
        # already contradicted. The sentence is derived, every time.
        # `type alias` has no annotation for `body_of` to key on.
        self.assertIn("givenUp : Maybe AmmoSwapGiveUp",
                      collapsed(source_of(SAXRAT_BOT_ELM)))
        reached = indented_let_binding(
            "updateAmmoSwapMemoryWithConfig", "giveUpReachedThisReading")
        self.assertNotIn(
            '"', reached,
            "a string literal here is a sentence stored in memory, which is "
            "the shape this change exists to leave")


class ThePlacementTest(unittest.TestCase):
    """Where the swap is wired in, read out of the source.

    None of this is an expression, and all of it is the kind of thing that
    compiles while doing nothing: a memory update never called, a decision never
    reached, a status clause never printed.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.collapsed = collapsed(without_comments(cls.source))

    def test_the_swap_sits_in_front_of_the_fight(self):
        self.assertIn(
            "decisionToFight = ensureAmmoSuitsTargetRange context decisionToKillRats",
            self.collapsed)

    def test_every_arm_of_the_movement_dispatch_reaches_it(self):
        anomaly = collapsed(without_comments(
            body_of(self.source, "decideActionInAnomaly")))
        self.assertEqual(
            anomaly.count("Maybe.withDefault decisionToFight"), 3,
            "orbit, keep-at-range and align each fall through to the fight, so "
            "an arm still naming decisionToKillRats would never swap")
        self.assertNotIn("Maybe.withDefault decisionToKillRats", anomaly)

    def test_the_memory_update_runs_on_every_reading(self):
        update = collapsed(without_comments(
            body_of(self.source, "updateMemoryForNewReadingFromGame")))
        self.assertIn(
            "ammoSwap = updateAmmoSwapMemory context incomingDamageNow "
            "{ justFinishedWarping = weJustFinishedWarping } "
            "botMemoryBefore.ammoSwap", update)

    def test_the_warp_the_swap_is_retried_across_is_the_one_already_defined(self):
        # One definition of "a pocket ended", shared with the anomaly
        # bookkeeping, so the two cannot come to disagree about it -- and so a
        # second, subtly different warp test cannot be introduced here without
        # somebody noticing.
        update = collapsed(without_comments(
            body_of(self.source, "updateMemoryForNewReadingFromGame")))
        self.assertIn(
            "weJustFinishedWarping = warpJustEnded "
            "{ warpingLastReading = botMemoryBefore.shipWarpingInLastReading "
            ", readingNow = context.readingFromGameClient }", update)
        self.assertEqual(
            code_only(self.source).count("weJustFinishedWarping ="), 1,
            "one definition, read by both the anomaly bookkeeping and the swap")

    def test_the_disarm_reads_this_reading_s_damage_window(self):
        # Not `botMemoryBefore.incomingDamage`: the trade is re-asked on every
        # reading the swap holds the guns, and a window one reading stale would
        # let it sit through the first reading of a fight arriving.
        update = collapsed(without_comments(
            body_of(self.source, "updateMemoryForNewReadingFromGame")))
        self.assertIn(
            "incomingDamageNow = updateIncomingDamageMemory context hitpoints "
            "botMemoryBefore.incomingDamage", update)
        self.assertIn("incomingDamage = incomingDamageNow", update)

    def test_the_status_line_carries_the_swap(self):
        status = collapsed(without_comments(
            body_of(self.source, "statusTextFromState")))
        self.assertIn("describeAmmoSwapState context", status)

    def test_the_swap_reads_the_toggle_and_not_the_duty_cycle(self):
        # The fight decides whether to press a hotkey from `.isActive`, which is
        # `ramp_active` -- the duty cycle. The mission runner's run 21 spent 605
        # of 674 module clauses being told no gun was firing on a ship that was.
        self.assertIn(
            "weaponIsSwitchedOn moduleButton = moduleReadsSwitchedOn "
            "moduleButton.stateFromDictEntries", self.collapsed)
        entry = declaration("moduleReadsSwitchedOn")
        self.assertIn("isInActiveState == Just True", entry)

    def test_the_weapon_row_has_one_ordering(self):
        # The swap silences a gun the fight re-arms by its list position, so two
        # sorts of the weapon row would be two opinions about which physical
        # weapon that is. Other rows sort themselves and are not this rule's
        # business, so what is asserted is that neither weapon-row reader sorts
        # for itself.
        self.assertIn(
            "shipUIModulesToActivateOnTarget = .shipUI >> .moduleButtonsRows "
            ">> .top >> weaponModuleButtonsLeftToRight", self.collapsed)
        self.assertIn("|> weaponModuleButtonsLeftToRight",
                      declaration("weaponModuleButtonsFromReading"))
        for reader in ("shipUIModulesToActivateOnTarget",
                       "weaponModuleButtonsFromReading"):
            self.assertNotIn("List.sortBy", declaration(reader))
        self.assertIn("List.sortBy (.uiNode >> .totalDisplayRegion >> .x)",
                      declaration("weaponModuleButtonsLeftToRight"))

    def test_the_settings_are_documented_in_the_bot_s_own_header(self):
        # `bot_help.py` reads the header section, so a setting missing from it
        # is a setting the launcher's --help will not mention.
        header = self.source[:self.source.index("module Bot exposing")]
        for setting in ("short-range-ammo", "long-range-ammo", "ammo-swap-range"):
            self.assertIn(setting, header)


class TheRecordedSaxratRunsTest(unittest.TestCase):
    """The recorded saxrat runs, asked what they actually did.

    This class used to assert that no recorded run had ever swapped ammo, which
    was true when the port shipped and expired the moment it flew. Its premise
    is gone; what replaces it is the evidence issue #154 rests on, keyed as
    *relations* between runs so that a corpus which grows -- or a later run that
    behaves differently -- cannot turn a true claim red.

    Runs are globbed rather than numbered, so run 11 is read without an edit.
    """

    @classmethod
    def setUpClass(cls):
        logs = sorted(glob.glob(
            os.path.join(EVE_BOT_LOGS, "saxrat_run*.log")))
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what those runs "
                "can say about warping and ammo cannot be consulted here")

        cls.readings = 0
        cls.warp_readings = 0
        cls.warp_episodes = 0
        cls.ammo_clauses = 0
        # Per run, so the claims below are relations between runs and not one
        # pooled number that a single odd run could carry on its own.
        cls.runs = []
        for path in logs:
            run = {"ammo_clauses": 0, "guns_off": 0, "guns_back_on": 0,
                   "disarm_give_ups": 0, "warp_episodes": 0,
                   "worst_guns_off": 0}
            in_warp = False
            was_in_warp = False
            started = False
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith("--------"):
                        if started:
                            cls.readings += 1
                            if in_warp:
                                cls.warp_readings += 1
                                if not was_in_warp:
                                    cls.warp_episodes += 1
                                    run["warp_episodes"] += 1
                            was_in_warp = in_warp
                        started = True
                        in_warp = False
                        continue
                    if SAXRAT_IN_WARP in line:
                        in_warp = True
                    if "Ammo swap:" not in line:
                        continue
                    cls.ammo_clauses += 1
                    run["ammo_clauses"] += 1
                    if GUNS_OFF_CLAUSE in line:
                        run["guns_off"] += 1
                        count = re.search(
                            re.escape(GUNS_OFF_CLAUSE) + r"(\d+) of", line)
                        if count:
                            run["worst_guns_off"] = max(
                                run["worst_guns_off"], int(count.group(1)))
                    if GUNS_BACK_ON_CLAUSE in line:
                        run["guns_back_on"] += 1
                    if DISARM_GIVE_UP in line:
                        run["disarm_give_ups"] += 1
            cls.runs.append((os.path.basename(path), run))

        cls.swapping = [(name, run) for name, run in cls.runs
                        if run["ammo_clauses"]]

    def test_the_port_is_flying_and_the_swap_reaches_its_disarm(self):
        """The claim the expired case denied, stated as the corpus now has it.

        A run carrying an ammo clause is a run flown since the port; one
        carrying `GUNS OFF` is a run whose swap got past the disarm gate and
        actually switched a gun off. Both are lower bounds, so more runs can
        only make them truer.
        """
        self.assertTrue(
            self.swapping,
            "no recorded run carries an ammo clause at all, so this bot's own "
            "corpus cannot say anything about the swap")
        self.assertTrue(
            [name for name, run in self.swapping if run["guns_off"]],
            "a swap that never reaches GUNS OFF is one the disarm gate stops, "
            "and none of the claims below would be about anything")

    def test_a_run_gave_up_on_a_ship_whose_guns_the_client_had_given_back(self):
        """Issue #154's finding, and the one the fix rests on.

        In such a run the swap's own status clause had gone over to reporting
        the guns back on, and the deepest `GUNS OFF` count it ever printed is
        far below the budget the give-up then claimed. That is a bound counting
        readings that belong to a different outcome.
        """
        bound = int_constant("ammoSwapSilencedGiveUpTicks")
        misread = [name for name, run in self.swapping
                   if run["disarm_give_ups"] and run["guns_back_on"]
                   and run["worst_guns_off"] * 2 < bound]
        self.assertTrue(
            misread,
            "no recorded run reached the disarm give-up having recorded the "
            "client re-arming the guns, which is the observation #154 is "
            "filed on -- runs 9 and 10 are the ones that did")

    def test_and_a_run_gave_up_with_the_guns_genuinely_off_throughout(self):
        """The counterexample that keeps the latch worth having.

        Not every give-up is a misreading. A run whose swap never once recorded
        a gun coming back, and whose `GUNS OFF` count ran all the way to the
        budget, is a ship that really was left disarmed -- so the fix narrows
        the latch rather than removing it.
        """
        bound = int_constant("ammoSwapSilencedGiveUpTicks")
        genuine = [name for name, run in self.swapping
                   if run["disarm_give_ups"] and not run["guns_back_on"]
                   and run["worst_guns_off"] >= bound]
        self.assertTrue(
            genuine,
            "no recorded run reached the give-up with the guns demonstrably "
            "still off, which is the case this latch exists for -- run 6 is "
            "the one that did")

    def test_a_warp_offers_far_more_retries_than_a_session_does(self):
        """The cost of unlatching on a warp, measured rather than asserted.

        A swap failing for a persistent reason retries once per warp instead of
        once per session. Stated as the relation that makes it bounded and
        plural: every run that gave up warped many times more often than it gave
        up, so the retry is tens of attempts over a long session and not one,
        and not thousands either.
        """
        gave_up = [(name, run) for name, run in self.swapping
                   if run["disarm_give_ups"]]
        self.assertTrue(gave_up, "no give-up recorded to size this against")
        for name, run in gave_up:
            self.assertGreater(
                run["warp_episodes"], 2,
                "%s gave up on the swap and warped almost never, so a per-warp "
                "retry would not be a retry at all" % name)

    def test_this_bot_does_commute_between_sites(self):
        """The issue's premise, and the corpus disagrees with it.

        Issue #122 argues the in-warp hover window "may barely exist here",
        from a source-reference count of 7 warp-related names against 103
        anomaly ones. That is a count of identifiers, not of behaviour: saxrat
        warps between anomalies constantly, and spends a substantial share of
        every long run in warp with nothing else wanting the mouse.

        It does not change the decision -- the hover is unreachable with
        `ammo-swap-range` required, whatever the warps look like -- but it is the
        premise a later change would rest on, so it is measured rather than
        repeated.
        """
        self.assertGreater(self.readings, 1000,
                           "too little recorded to say anything about warps")
        self.assertGreater(
            self.warp_episodes, 20,
            "the recorded runs warp many times over, so a hover asked once per "
            "warp would have many separate moments to be asked at")
        self.assertGreater(
            self.warp_readings * 20, self.readings,
            "more than a twentieth of every recorded reading is spent in warp, "
            "where this bot issues nothing at all")
