"""Tests for tracking disruption and sensor dampening being priority targets.

Issue #231. `overviewEntryIsWarpDisruptingMe` shoots a warp scrambler first, on
the argument that everything the bot does when a fight goes wrong assumes it can
leave. The client names two other EWAR types on the same overview row and the
bot read **neither** -- and it acted on the rarest of the three while ignoring
the most common by a factor of nineteen.

Recounted from `~/eve-bot-logs` rather than quoted from the issue. Counted per
*reading* (`RequestToVolatileProcess`, one per reading) as well as per line,
because `Overview indications:` is a status clause and the status line is
reprinted under every decision -- this file's own "a decision in the log is not
an action" applied to counting, and the unit that has already cost
`stall_watch.py` two threshold calibrations, #141 a retreat measurement and #164
an issue's whole diagnosis:

| literal, as the client writes it | lines | readings | runs |
|---|---:|---:|---:|
| `Pilot is tracking disrupting me` | 5,320 | **1,640** | 13 |
| `Pilot is webifying me`           |   992 |      306 |  5 |
| `Pilot is target painting me`     |   732 |      228 |  4 |
| `Pilot is warp disrupting me`     |   290 |       86 |  3 |
| `Pilot is sensor dampening me`    |   265 |       89 |  1 |
| `Pilot is jamming me`             |     0 |        0 |  0 |

Every count above is asserted here as a **relation** rather than as a number, so
a growing corpus cannot turn a true claim red.

Four things had to be got right and each has its own class.

- **The literals are the client's own**, checked against the corpus rather than
  written from memory. **"dampening", not "damping"** -- and the discriminating
  case is the one that feeds the parser the corpus string byte for byte, since a
  matcher spelled `is sensor damping me` finds no substring of
  `Pilot is sensor dampening me` and answers `False` --
  `TheClientsOwnSpellingIsWhatIsMatched`.
- **The ordering is three tiers and warp disruption stays first.** `#231` argues
  survival ahead of effectiveness: a scrambler takes the option to leave away,
  where these two only make the ship worse at using it --
  `TheTierOrderingIsSurvivalThenEffectiveness`.
- **It adds no rows.** This is a *reordering*, which is stronger than the
  "widening keeps every guard" property #40 needed: every row a tier can move is
  a row `shouldAttackOverviewEntry` already admitted, so
  `overviewEntryDistanceIsOnGrid` still holds by construction and
  `overviewEntryIsDisplayed` still runs at the lock site --
  `TheReorderingAddsNoRows`.
- **saxrat read none of this at all**, which is arguably the bigger half of the
  issue: `isWarpDisruptingMe` had exactly one read site in the whole repository,
  in the mission runner, so the bot that flies unattended in the hull that was
  lost twice had no scrambler priority whatever --
  `SaxratHadNoScramblerPriorityAtAll`.

The rules are executed through the real `Bot.elm` in `elm repl` in **both** apps,
and the overview rows they are asked about are built by running UI trees through
the **real** `EveOnline.ParseUserInterface` -- so what the cases assert on is
what the bot would have been handed, and the parser half is executed rather than
read. A Python restatement of "what does this parser make of this hint" would
test the restatement.

**One case is honestly weaker than the rest and is reported as such.**
`test_the_sort_puts_them_in_that_order` applies the real `combatPriorityTier`
with a real `List.sortBy` over really parsed rows, which is the expression the
decision applies -- but the `List.sortBy` in that case is written here rather
than reached through `decideActionInCombat`, which takes a whole
`BotDecisionContext`. What pins the decision to that expression is a source read
beside it (`test_each_app_sorts_its_attack_list_by_the_tier`), and #40's own
`test_a_scrambler_still_outranks_something_merely_shooting_us` reads it too.

Nothing here reads a live game client, a running bot, or the game log directory.
The corpus cases read the recorded runs in `~/eve-bot-logs`, and only read them.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import hashlib
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl, vendored_parser_count
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, collapsed,
    label, node, source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
APPS = (("saxrat", SAXRAT_BOT_ELM), ("mission runner", MISSION_RUNNER_BOT_ELM))

EVE_ONLINE_APPS = os.path.join(
    os.path.dirname(os.path.dirname(SAXRAT_DIR)), "eve-online")

# The five literals the corpus holds, exactly as the client writes them, and the
# one the parser has matched since upstream and this client has never written.
# Nothing here is retyped from the issue: each was cut out of `~/eve-bot-logs`.
TRACKING_DISRUPTION = "Pilot is tracking disrupting me"
SENSOR_DAMPENING = "Pilot is sensor dampening me"
WARP_DISRUPTION = "Pilot is warp disrupting me"
TARGET_PAINTING = "Pilot is target painting me"
WEBIFYING = "Pilot is webifying me"
JAMMING = "Pilot is jamming me"

# What the parser matches, which is the client's sentence with the subject cut
# off -- `rightAlignedIconsHintsContainsTextIgnoringCase` is a substring test.
# Read back out of the vendored source by `TheVendoredParserPolicy`, so a
# matcher that drifts from the client fails there as well as here.
TRACKING_DISRUPTION_MATCHER = "is tracking disrupting me"
SENSOR_DAMPENING_MATCHER = "is sensor dampening me"

# The spelling a matcher written from memory gets wrong. It is not the client's
# and appears nowhere in the corpus; a parser carrying it answers `False` for
# every real reading, which is a guard that quietly never fires.
THE_MISSPELLING = "Pilot is sensor damping me"

# A rat's icon colour, read off the live client: every rat on the overview
# during that read carried exactly this, against white and yellow for the
# stargates and the sun. What makes a fixture row attackable at all.
RAT_COLOR = {"aPercent": 100, "rPercent": 100, "gPercent": 10, "bPercent": 10}

# Names quoted from the recorded runs, so a fixture row is one the client really
# drew rather than one this file invented.
RAT_NAME = "Centii Minion"

ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20


def overview(rows):
    """An overview window whose rows carry icon colours and EWAR hints.

    Each row is `(distance, name, hints, is_rat)`. `hints` are put under a
    container named `rightAlignedIconContainer`, each on its own `_hint`, which
    is where `parseOverviewWindowEntry` reads `rightAlignedIconsHints` from; the
    hint nodes carry display regions because that parse goes through
    `listDescendantsWithDisplayRegion` and a node without one is filed as a
    child without a region and never reached.

    A header must span its cell (`parseListViewEntry`'s
    `headerRegionMatchesCellRegion`), which is why the column geometry is
    explicit rather than incidental.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name, hints, is_rat) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH

        icon_children = []
        if is_rat:
            icon_children.append(
                node("Sprite", {"_name": "iconSprite", "_color": RAT_COLOR},
                     region=(2, y, 8, ROW_HEIGHT)))

        hint_nodes = [
            node("Sprite", {"_hint": hint}, region=(400 + n * 10, y, 8, 8))
            for n, hint in enumerate(hints)]

        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, ROW_HEIGHT)),
            label(name, (110, y, 150, ROW_HEIGHT)),
            label(name, (310, y, 150, ROW_HEIGHT)),
            node("SpaceObjectIcon", {}, icon_children,
                 region=(2, y, 12, ROW_HEIGHT)),
            node("Container", {"_name": "rightAlignedIconContainer"},
                 hint_nodes, region=(400, y, 90, ROW_HEIGHT)),
        ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def rat(distance, name=RAT_NAME, hints=()):
    return (distance, name, list(hints), True)


class EwarRepl(SaxratRepl):
    """One app's `Bot.elm`, plus what asking about an overview row costs.

    The bindings ride in the preamble, which `imports_and_bindings` folds into
    the one `let` that asks the question -- so they cost the same single compile
    the imports do (#172).
    """

    APP_DIR = SAXRAT_DIR

    BINDINGS = (
        "rowsOf = \\parsed -> parsed"
        " |> Maybe.map (.overviewWindows >> List.concatMap .entries)"
        " |> Maybe.withDefault []",
        "rowAt = \\n parsed -> rowsOf parsed |> List.drop n |> List.head",
        # `False` for a row that is not there is deliberate: it is the same
        # answer a row carrying no hint gives, so a case that means to ask about
        # a hint has to be built on a fixture that really arrived. That is what
        # `TheFixturesReallyArrive` is for.
        "indicationAt = \\field n parsed ->"
        " rowAt n parsed |> Maybe.map (.commonIndications >> field)"
        " |> Maybe.withDefault False",
        "tierAt = \\n parsed ->"
        " rowAt n parsed |> Maybe.map combatPriorityTier"
        " |> Maybe.withDefault -1",
        "nameAt = \\n parsed ->"
        " rowAt n parsed |> Maybe.andThen .objectName"
        " |> Maybe.withDefault \"NO ROW\"",
        "hintsAt = \\n parsed ->"
        " rowAt n parsed |> Maybe.map .rightAlignedIconsHints"
        " |> Maybe.withDefault [] |> String.join \"|\"",
        # The expression the decision applies, over really parsed rows.
        "namesByTier = \\parsed -> rowsOf parsed"
        " |> List.sortBy combatPriorityTier"
        " |> List.map (.objectName >> Maybe.withDefault \"?\")"
        " |> String.join \",\"",
        # The rows a predicate keeps, named. Answering with the *names* rather
        # than with a `Bool` per row is what puts a positive control inside
        # every case that uses it: a fixture that never arrived, or a rule that
        # answers nothing, comes back empty rather than coming back `False` --
        # which is the same answer a rule correctly declining would give.
        "namesKept = \\rule parsed -> rowsOf parsed"
        " |> List.filter rule"
        " |> List.map (.objectName >> Maybe.withDefault \"?\")"
        " |> String.join \",\"",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("app_dir", self.APP_DIR)
        super().__init__(**kwargs)
        self.preamble = list(self.preamble) + list(self.BINDINGS)

    def reading(self, name, rows):
        """A binding of `name` to a really parsed reading over `rows`."""
        return self.reading_binding(name, [overview(rows)])


class SaxratEwarRepl(EwarRepl):
    APP_DIR = SAXRAT_DIR


class MissionRunnerEwarRepl(EwarRepl):
    APP_DIR = MISSION_RUNNER_DIR


REPLS = (("saxrat", SaxratEwarRepl), ("mission runner", MissionRunnerEwarRepl))


class BothAppsTest(unittest.TestCase):
    """A base that opens one repl per app and asks each the same question."""

    @classmethod
    def setUpClass(cls):
        cls.repls = [(name, open_repl(repl_class))
                     for name, repl_class in REPLS]

    @classmethod
    def tearDownClass(cls):
        for _, repl in cls.repls:
            repl.close()


class TheFixturesReallyArrive(BothAppsTest):
    """Before anything is concluded from a row, that the row got here.

    #174's discipline: a reading that never decoded and a rule that declined it
    are the same answer from outside, so a case built on a fixture the parser
    made nothing of passes having asserted nothing.
    """

    def test_the_hints_reach_the_parser_intact(self):
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION, SENSOR_DAMPENING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                answer = repl.strings(
                    ["hintsAt 0 reading"], [repl.reading("reading", rows)])
                self.assertEqual(
                    answer,
                    ["%s|%s" % (TRACKING_DISRUPTION, SENSOR_DAMPENING)])

    def test_the_rows_reach_the_parser_named_and_ordered(self):
        rows = [rat("1,000 m", name="Centii Minion"),
                rat("2,000 m", name="Centii Savage")]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    repl.strings(["nameAt 0 reading", "nameAt 1 reading"],
                                 [repl.reading("reading", rows)]),
                    ["Centii Minion", "Centii Savage"])


class TheClientsOwnSpellingIsWhatIsMatched(BothAppsTest):
    """The two new fields, executed through the real parser.

    The discriminating case here is the plainest one:
    `test_the_sensor_dampening_hint_is_read` feeds the parser the corpus literal
    byte for byte, so a matcher spelled `is sensor damping me` -- the spelling
    somebody writing from memory reaches for, and the one this whole class
    exists to refuse -- finds no substring of it and answers `False`.
    """

    def ask(self, repl, rows, expressions):
        return repl.evaluate(expressions, [repl.reading("reading", rows)])

    def test_the_tracking_disruption_hint_is_read(self):
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows,
                             ["indicationAt .isTrackingDisruptingMe 0 reading"]),
                    [True])

    def test_the_sensor_dampening_hint_is_read(self):
        rows = [rat("1,000 m", hints=[SENSOR_DAMPENING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows,
                             ["indicationAt .isSensorDampeningMe 0 reading"]),
                    [True])

    def test_damping_is_not_the_clients_spelling(self):
        # The other direction of the same claim. A matcher loosened to catch
        # both spellings -- `sensor damp`, say -- would pass the case above and
        # fail this one, and it is a guard resting on a string no evidence
        # supports, which is #40's own discipline.
        rows = [rat("1,000 m", hints=[THE_MISSPELLING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows,
                             ["indicationAt .isSensorDampeningMe 0 reading"]),
                    [False])

    def test_the_two_new_fields_do_not_read_each_others_hint(self):
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION]),
                rat("2,000 m", hints=[SENSOR_DAMPENING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 0 reading",
                        "indicationAt .isTrackingDisruptingMe 1 reading",
                        "indicationAt .isSensorDampeningMe 1 reading",
                    ]),
                    [True, False, False, True])

    def test_neither_new_field_reads_the_scramblers_hint(self):
        # The three are separate facts about one row, and the corpus has all
        # three occurring. A field that fired on the scrambler would make the
        # tiers below meaningless.
        rows = [rat("1,000 m", hints=[WARP_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isWarpDisruptingMe 0 reading",
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 0 reading",
                    ]),
                    [True, False, False])

    def test_the_match_ignores_case_like_the_other_two(self):
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION.upper()]),
                rat("2,000 m", hints=[SENSOR_DAMPENING.upper()])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 1 reading",
                    ]),
                    [True, True])

    def test_a_near_miss_is_not_a_match(self):
        # The corpus carries five literals and only two of them are these, so a
        # matcher that reads on one word would take rows the issue deliberately
        # leaves out of scope.
        rows = [rat("1,000 m", hints=[TARGET_PAINTING]),
                rat("2,000 m", hints=[WEBIFYING]),
                rat("3,000 m", hints=["Pilot is tracking me"])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 0 reading",
                        "indicationAt .isTrackingDisruptingMe 1 reading",
                        "indicationAt .isSensorDampeningMe 1 reading",
                        "indicationAt .isTrackingDisruptingMe 2 reading",
                    ]),
                    [False, False, False, False, False])

    def test_a_row_with_no_hint_at_all_reads_false_everywhere(self):
        rows = [rat("1,000 m")]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 0 reading",
                        "indicationAt .isWarpDisruptingMe 0 reading",
                    ]),
                    [False, False, False])

    def test_one_row_can_carry_several_of_them(self):
        # The client draws these on the same right-aligned strip, so a row under
        # two kinds of EWAR at once is the ordinary case rather than a corner.
        rows = [rat("1,000 m",
                    hints=[TRACKING_DISRUPTION, SENSOR_DAMPENING,
                           WARP_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    self.ask(repl, rows, [
                        "indicationAt .isTrackingDisruptingMe 0 reading",
                        "indicationAt .isSensorDampeningMe 0 reading",
                        "indicationAt .isWarpDisruptingMe 0 reading",
                    ]),
                    [True, True, True])


class TheTierOrderingIsSurvivalThenEffectiveness(BothAppsTest):
    """`combatPriorityTier`, executed on really parsed rows in both apps.

    Three tiers rather than two. A scrambler takes the option to leave away and
    the other two only make the ship worse at using it, so warp disruption stays
    ahead of both -- which is the ordering question #231 raises and the one a
    later change is most likely to flatten.
    """

    def tiers(self, repl, rows):
        return [int(answer) for answer in repl.strings(
            ["String.fromInt (tierAt %d reading)" % index
             for index in range(len(rows))],
            [repl.reading("reading", rows)])]

    def test_a_scrambler_is_the_first_tier(self):
        rows = [rat("1,000 m", hints=[WARP_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(self.tiers(repl, rows), [0])

    def test_both_new_kinds_are_the_second_tier(self):
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION]),
                rat("2,000 m", hints=[SENSOR_DAMPENING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(self.tiers(repl, rows), [1, 1])

    def test_everything_else_is_the_third_tier(self):
        rows = [rat("1,000 m"), rat("2,000 m", hints=[TARGET_PAINTING])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(self.tiers(repl, rows), [2, 2])

    def test_warp_disruption_stays_ahead_on_a_row_that_is_both(self):
        # A row under two kinds at once takes the *higher* priority, not the
        # one whose test happens to come first.
        #
        # This case was written claiming to be what separates "warp disruption
        # first" from "any EWAR first", and the mutation run showed that was
        # false: swapping the two branches wholesale leaves a row that is both
        # answering 0 either way, and what catches that swap is
        # `test_a_scrambler_is_the_first_tier` beside it. What this really pins
        # is narrower and is still worth having -- that the scrambler clause is
        # not skipped when some other indication is also on the row, which is
        # the shape `if stopping then 1 else if disrupting then 0 else 2` has.
        # That mutation answers 1 here and passes every other case in the class.
        rows = [rat("1,000 m", hints=[TRACKING_DISRUPTION, WARP_DISRUPTION]),
                rat("2,000 m", hints=[SENSOR_DAMPENING, WARP_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(self.tiers(repl, rows), [0, 0])

    def test_the_sort_puts_them_in_that_order(self):
        # The rows arrive in distance order, which is what
        # `overviewEntriesToAttackFromReadingFromGameClient` answers with, and
        # the tier is what moves them. The nearest rat is last and the furthest
        # scrambler first, which is the whole behaviour change.
        #
        # `List.sortBy` is written here rather than reached through the decision
        # -- see this file's own docstring for why, and for what pins the
        # decision to this expression.
        rows = [rat("1,000 m", name="near rat"),
                rat("2,000 m", name="near damper", hints=[SENSOR_DAMPENING]),
                rat("3,000 m", name="far rat"),
                rat("4,000 m", name="far disruptor",
                    hints=[TRACKING_DISRUPTION]),
                rat("5,000 m", name="far scrambler", hints=[WARP_DISRUPTION])]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    repl.strings(["namesByTier reading"],
                                 [repl.reading("reading", rows)]),
                    ["far scrambler,near damper,far disruptor,"
                     "near rat,far rat"])

    def test_the_sort_is_stable_within_a_tier(self):
        # Every consumer downstream takes a prefix of this list -- the lock
        # candidates, #178's in-range prefix, `clickTargetBeforeShooting`'s head
        # -- so a tier that reordered within itself would quietly change which
        # rat is locked first on every reading of every fight.
        rows = [rat("1,000 m", name="a"), rat("2,000 m", name="b"),
                rat("3,000 m", name="c"), rat("4,000 m", name="d")]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    repl.strings(["namesByTier reading"],
                                 [repl.reading("reading", rows)]),
                    ["a,b,c,d"])

    def test_each_app_sorts_its_attack_list_by_the_tier(self):
        # The half that is not an expression: that this rule is the one applied,
        # and applied *after* the helper that carries every guard.
        for name, path in APPS:
            with self.subTest(app=name):
                source = collapsed(source_of(path))
                self.assertIn(
                    "overviewEntriesToAttackFromReadingFromGameClient", source)
                self.assertIn("|> List.sortBy combatPriorityTier", source)
                self.assertEqual(
                    source.count("|> List.sortBy combatPriorityTier"), 1,
                    "one sort, so two places cannot come to disagree about the "
                    "order the fight sees")


class TheReorderingAddsNoRows(BothAppsTest):
    """#231's premise says the change "adds rows at their own distance rank".

    It does not: it adds none. Every row a tier can move is a row
    `shouldAttackOverviewEntry` already admitted, which is a stronger property
    than the one #40 needed and is what makes every existing guard hold by
    placement. Both halves are asserted -- the executable one here, and the
    placement below.
    """

    ATTACK_RULES = {
        "saxrat": "shouldAttackOverviewEntry []",
        "mission runner":
            "shouldAttackOverviewEntry"
            " { fromObjective = [], fromSettings = []"
            " , fromIncomingDamage = [], givenUpAsImmune = [] }",
    }

    def test_an_ewar_row_nothing_else_would_attack_is_still_not_attacked(self):
        # Not a rat by icon colour, named by no objective, no setting and no
        # combat-log line. The hint is the only thing about it, and the hint is
        # not a reason to shoot anything. The plain rat beside it is the
        # positive control: the rule really did run and really did keep a row.
        rows = [("1,000 m", "under EWAR and not a rat",
                 [TRACKING_DISRUPTION, SENSOR_DAMPENING], False),
                rat("2,000 m", name="an ordinary rat")]
        for name, repl in self.repls:
            with self.subTest(app=name):
                self.assertEqual(
                    repl.strings(
                        ["namesKept (%s) reading" % self.ATTACK_RULES[name]],
                        [repl.reading("reading", rows)]),
                    ["an ordinary rat"])

    def test_an_au_distance_is_still_excluded_whatever_the_hint(self):
        # Distances parse only as m and km, so an AU distance is an `Err` that
        # `overviewEntryDistanceIsOnGrid` refuses -- and the tier cannot put a
        # row back that the rule never let in. Same rat, same hint, one on grid
        # and one not, so the distance is the only thing separating them.
        rows = [("1.2 AU", RAT_NAME, [WARP_DISRUPTION], True),
                ("1,000 m", RAT_NAME, [WARP_DISRUPTION], True)]
        for name, repl in self.repls:
            with self.subTest(app=name):
                kept = repl.strings(
                    ["namesKept (%s) reading" % self.ATTACK_RULES[name]],
                    [repl.reading("reading", rows)])
                self.assertEqual(kept, [RAT_NAME])

    def test_a_virtualised_row_is_still_never_clicked(self):
        # The lock site filters on `_display` before taking anything, and the
        # tier sits above it -- so a priority row scrolled out of view is
        # dropped there exactly as any other row would be.
        for name, path in APPS:
            with self.subTest(app=name):
                source = source_of(path)
                lock = source[source.index("overviewEntriesToLock ="):]
                lock = collapsed(lock[:lock.index("\n\n")])
                self.assertIn("List.filter overviewEntryIsDisplayed", lock)

    def test_the_tier_reads_nothing_but_the_row(self):
        # No memory, no settings, no reading. That is what makes it executable
        # here at all, and it is also what stops a later version deciding a
        # priority from something a case cannot reach.
        #
        # Read without its doc comment, which talks about all four of these.
        for name, path in APPS:
            with self.subTest(app=name):
                body = collapsed(_body(source_of(path), "combatPriorityTier"))
                for forbidden in ("context", "memory", "botSettings",
                                  "readingFromGameClient"):
                    self.assertNotIn(forbidden, body)


class SaxratHadNoScramblerPriorityAtAll(BothAppsTest):
    """The bigger half of #231, and it is about an absence.

    `isWarpDisruptingMe` was parsed on every reading of every recorded run and
    the only read site in the whole repository was the mission runner's. saxrat
    -- the bot that flies unattended, in the hull that was lost twice -- had no
    scrambler priority whatever.
    """

    def test_saxrat_now_reads_the_scrambler(self):
        rows = [rat("1,000 m", name="a scrambler", hints=[WARP_DISRUPTION]),
                rat("2,000 m", name="an ordinary rat")]
        repl = dict(self.repls)["saxrat"]
        self.assertEqual(
            repl.strings(
                ["namesKept overviewEntryIsWarpDisruptingMe reading"],
                [repl.reading("reading", rows)]),
            ["a scrambler"])

    def test_both_apps_read_it_now(self):
        # The absence was the whole finding, so what is asserted is that it is
        # gone from both rather than that it exists in one.
        for name, path in APPS:
            with self.subTest(app=name):
                source = collapsed(source_of(path))
                self.assertIn(
                    "overviewEntry.commonIndications.isWarpDisruptingMe",
                    source)
                self.assertIn(
                    "if overviewEntryIsWarpDisruptingMe entry then", source)

    def test_the_two_new_rules_are_the_same_declarations_in_both_apps(self):
        # A port that keeps one and drops another is what this refuses, and the
        # failure would be quiet: a bot that never prioritises reads exactly
        # like a grid with no EWAR on it.
        for declaration in ("combatPriorityTier",
                            "overviewEntryIsStoppingUsFighting"):
            with self.subTest(declaration=declaration):
                bodies = {name: _declaration(source_of(path), declaration)
                          for name, path in APPS}
                self.assertEqual(bodies["saxrat"], bodies["mission runner"])

    def test_saxrats_own_read_of_the_scrambler_stands_on_its_own(self):
        # `overviewEntryIsWarpDisruptingMe` is deliberately *not* compared byte
        # for byte: the mission runner's doc comment argues from run 102 and the
        # Coercer it lost, and saxrat's argues from never having read the field
        # at all. Both are true of their own app and neither is true of both.
        bodies = {name: _declaration(source_of(path),
                                     "overviewEntryIsWarpDisruptingMe")
                  for name, path in APPS}
        self.assertNotEqual(bodies["saxrat"], bodies["mission runner"])
        for name, body in bodies.items():
            with self.subTest(app=name):
                self.assertIn(
                    "overviewEntry.commonIndications.isWarpDisruptingMe", body)


def _body(source, name):
    """One top-level declaration, from its type annotation to the next one."""
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match, "no declaration named %r" % name
    return match.group(0)


def _declaration(source, name):
    """The same, with the doc comment above it.

    Byte-for-byte comparisons across the two apps take this rather than `_body`,
    because a doc comment that drifts is how two copies of one rule come to be
    arguing different things while still computing the same answer.
    """
    body = _body(source, name)
    start = source.index(body)
    prefix = source[:start]
    if prefix.rstrip().endswith("-}"):
        doc_start = prefix.rindex("{-|")
        return source[doc_start:start + len(body)]
    return body


class TheVendoredParserPolicy(unittest.TestCase):
    """Where this lands among the six vendored copies, and why.

    `CLAUDE.md` states the policy over the whole file ("vendored six times, and
    the policy is all six, identically"). What the repo **enforces** is
    `test_game_log_channel.VendoredParserTest`, which compares the *game-log
    block* byte for byte across the six and pins a type-name string -- and
    outside that block the copies have already diverged. PR #252 concluded from
    that divergence that an app-local panel parser lands in one copy only.

    **This one is different and lands in all six**, and the difference is
    checked rather than argued. `OverviewWindowEntryCommonIndications` is a
    field on a *shared* overview type that five of the six `Bot.elm`s read, one
    of the places the six copies have **not** diverged: the type alias and the
    matcher block were byte-identical across all six before this change. Adding
    to one would introduce a divergence into a block that has none, in a type
    whose readers are spread across the apps -- so the app-local argument does
    not reach it.
    """

    # `eve-online-mining-bot`'s tree was replaced with Viir's current upstream
    # (see CLAUDE.md's Architecture section), which predates #231 entirely --
    # its `OverviewWindowEntryCommonIndications` carries only `targeting`,
    # `targetedByMe`, `isJammingMe` and `isWarpDisruptingMe`, neither of the
    # two fields this file is about. Excluded from every case below rather
    # than assigned a shape; porting #231 into the newer base is follow-up
    # work, not done here.
    WITHOUT_EWAR_WIDENING = {"eve-online-mining-bot"}

    def parsers(self):
        paths = sorted(
            path for path in glob.glob(os.path.join(
                EVE_ONLINE_APPS, "*", "EveOnline", "ParseUserInterface.elm"))
            if os.path.basename(os.path.dirname(os.path.dirname(path)))
            not in self.WITHOUT_EWAR_WIDENING)
        self.assertEqual(
            len(paths),
            vendored_parser_count(paths) - len(self.WITHOUT_EWAR_WIDENING),
            paths)
        return {path: source_of(path) for path in paths}

    def test_the_mining_bot_is_excluded_because_it_genuinely_lacks_the_fields(self):
        path = os.path.join(
            EVE_ONLINE_APPS, "eve-online-mining-bot", "EveOnline",
            "ParseUserInterface.elm")
        source = source_of(path)
        self.assertNotIn("isTrackingDisruptingMe", source)
        self.assertNotIn("isSensorDampeningMe", source)

    @staticmethod
    def alias_block(source):
        start = source.index(
            "type alias OverviewWindowEntryCommonIndications")
        return source[start:source.index("\n\n\n", start)]

    @staticmethod
    def matcher_block(source):
        start = source.index("        commonIndications =")
        return source[start:source.index("\n\n", start)]

    def test_every_copy_carries_both_new_fields(self):
        for path, source in self.parsers().items():
            with self.subTest(path=os.path.basename(os.path.dirname(
                    os.path.dirname(path)))):
                self.assertIn("    , isTrackingDisruptingMe : Bool\n", source)
                self.assertIn("    , isSensorDampeningMe : Bool\n", source)

    def test_every_copy_matches_the_clients_own_literals(self):
        for path, source in self.parsers().items():
            with self.subTest(path=os.path.basename(os.path.dirname(
                    os.path.dirname(path)))):
                self.assertIn(
                    'isTrackingDisruptingMe = '
                    'rightAlignedIconsHintsContainsTextIgnoringCase "%s"'
                    % TRACKING_DISRUPTION_MATCHER, source)
                self.assertIn(
                    'isSensorDampeningMe = '
                    'rightAlignedIconsHintsContainsTextIgnoringCase "%s"'
                    % SENSOR_DAMPENING_MATCHER, source)

    def test_no_copy_carries_the_misspelling(self):
        for path, source in self.parsers().items():
            with self.subTest(path=os.path.basename(os.path.dirname(
                    os.path.dirname(path)))):
                self.assertNotIn("sensor damping", source)

    def test_the_block_is_still_identical_across_all_six(self):
        sources = self.parsers()
        aliases = {p: self.alias_block(s) for p, s in sources.items()}
        matchers = {p: self.matcher_block(s) for p, s in sources.items()}
        reference = sorted(aliases)[0]
        for path in sources:
            with self.subTest(path=os.path.basename(os.path.dirname(
                    os.path.dirname(path)))):
                self.assertEqual(aliases[path], aliases[reference])
                self.assertEqual(matchers[path], matchers[reference])

    def test_the_copies_had_already_diverged_as_whole_files(self):
        # PR #252's own finding, re-taken here rather than inherited: the six
        # files are not one file. That is what makes "identical *here*" a
        # deliberate property of this block rather than an accident of the
        # copies being the same.
        digests = {hashlib.md5(source.encode()).hexdigest()
                   for source in self.parsers().values()}
        self.assertGreater(
            len(digests), 1,
            "the six copies are byte-identical as whole files, which would "
            "make this block's identity say nothing")

    def test_the_shared_type_is_read_by_more_than_one_app(self):
        # The premise the all-six conclusion rests on. #252's panel parser was
        # read by one `Bot.elm`; this is a field on a type several read.
        readers = [
            os.path.basename(os.path.dirname(path))
            for path in sorted(glob.glob(
                os.path.join(EVE_ONLINE_APPS, "*", "Bot.elm")))
            if "commonIndications" in source_of(path)]
        self.assertGreater(len(readers), 1, readers)


class TheCorpusIsWhereTheLiteralsCameFrom(unittest.TestCase):
    """The strings were checked against the recorded runs, not guessed.

    That is what made #40's attacker rule safe and it is the same discipline
    here. Everything below is a **relation** -- the counts in this file's
    docstring are what they were on the day it was written, and a corpus that
    grows must not turn a true claim red.

    Counted per *reading* as well as per line, because the status line is
    reprinted under every decision.
    """

    @classmethod
    def setUpClass(cls):
        paths = sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "*.log")))
        if not paths:
            raise unittest.SkipTest(
                "no recorded runs under %s, so the corpus cannot be consulted "
                "here" % EVE_BOT_LOGS)
        cls.lines = {}
        cls.readings = {}
        cls.runs = {}
        literals = (TRACKING_DISRUPTION, SENSOR_DAMPENING, WARP_DISRUPTION,
                    TARGET_PAINTING, WEBIFYING, JAMMING, THE_MISSPELLING)
        for literal in literals:
            cls.lines[literal] = 0
            cls.readings[literal] = 0
            cls.runs[literal] = 0
        cls.total_readings = 0
        for path in paths:
            with open(path, errors="replace") as handle:
                text = handle.read()
            chunks = text.split("RequestToVolatileProcess")
            cls.total_readings += len(chunks) - 1
            for literal in literals:
                count = text.count(literal)
                cls.lines[literal] += count
                if count:
                    cls.runs[literal] += 1
                cls.readings[literal] += sum(
                    1 for chunk in chunks if literal in chunk)

    def test_the_corpus_is_big_enough_to_say_anything(self):
        self.assertGreater(self.total_readings, 100000, self.total_readings)

    def test_both_new_literals_are_in_the_recorded_runs(self):
        for literal in (TRACKING_DISRUPTION, SENSOR_DAMPENING):
            with self.subTest(literal=literal):
                self.assertGreater(self.readings[literal], 0)
                self.assertGreater(self.runs[literal], 0)

    def test_the_matchers_are_substrings_of_what_the_client_wrote(self):
        # The parser's literals read back out of a vendored copy and checked
        # against the client's own sentence, so a matcher that drifts from what
        # the client writes fails here rather than in a run.
        source = source_of(os.path.join(
            SAXRAT_DIR, "EveOnline", "ParseUserInterface.elm"))
        for matcher, sentence in (
                (TRACKING_DISRUPTION_MATCHER, TRACKING_DISRUPTION),
                (SENSOR_DAMPENING_MATCHER, SENSOR_DAMPENING)):
            with self.subTest(matcher=matcher):
                self.assertIn('"%s"' % matcher, source)
                self.assertIn(matcher.lower(), sentence.lower())

    def test_tracking_disruption_dwarfs_the_one_the_bot_already_acted_on(self):
        # #231's headline. The bot acted on the rarest of the three and ignored
        # the most common; asserted as "several times more", not as nineteen.
        self.assertGreater(self.readings[TRACKING_DISRUPTION],
                           5 * self.readings[WARP_DISRUPTION])
        self.assertGreater(self.lines[TRACKING_DISRUPTION],
                           5 * self.lines[WARP_DISRUPTION])

    def test_sensor_dampening_is_also_more_common_than_warp_disruption(self):
        self.assertGreater(self.readings[SENSOR_DAMPENING],
                           self.readings[WARP_DISRUPTION])

    def test_the_misspelling_is_written_by_nobody(self):
        # The whole reason this class exists. If the client ever wrote
        # "damping", this would be the place it turned up.
        self.assertEqual(self.lines[THE_MISSPELLING], 0)

    def test_the_reading_count_is_smaller_than_the_line_count(self):
        # The unit this file counts in, asserted rather than remembered: the
        # status line is reprinted under every decision, so lines over-state
        # every one of these by several times.
        for literal in (TRACKING_DISRUPTION, SENSOR_DAMPENING,
                        WARP_DISRUPTION):
            with self.subTest(literal=literal):
                self.assertGreater(self.lines[literal],
                                   self.readings[literal])

    def test_the_literal_the_parser_has_always_matched_never_occurs(self):
        # `is jamming me` is the other way round from these two -- matched since
        # upstream, written by this client not once. Recorded as a scope note
        # rather than a fix: either the literal is wrong for this client or
        # jamming genuinely never happens here, and the corpus cannot tell those
        # apart. A run that finally writes it turns this case red, which is when
        # somebody should look.
        self.assertEqual(self.lines[JAMMING], 0)

    def test_the_two_kinds_left_out_of_scope_really_are_in_the_corpus(self):
        # Target painting and webifying are deliberately not acted on, and both
        # occur -- painting at several times warp disruption's rate. So leaving
        # them out is a decision rather than an absence of evidence, which is
        # what the PR says and what this pins.
        for literal in (TARGET_PAINTING, WEBIFYING):
            with self.subTest(literal=literal):
                self.assertGreater(self.readings[literal], 0)


if __name__ == "__main__":
    unittest.main()
