"""Three instruments the mission runner has had and saxrat has printed nothing of.

All three are status-line clauses. None of them changes a decision, and the
cases below are mostly about keeping it that way: what makes this a low-risk
change is that every branch in `Bot.elm` behaves exactly as it did, and the only
difference is that a run says on every reading what it previously left to be
reconstructed from a log -- or, in all three of these cases, left unrecoverable.

**The overview indications are the one that matters.** PR #265 established that
saxrat has never printed them at all: across 227,749 recorded readings there is
no `Overview indications:` line and no equivalent, because that clause was
mission-runner-only. In the same corpus saxrat chose an out-of-range overview row
on 13,918 readings and can say nothing about what was on any of them, so the bot
whose lock-batching defect #265 fixed is structurally unable to show whether it
ever met the situation. saxrat already *reads* these hints -- `combatPriorityTier`
consumes two of the five literals the corpus holds, through `commonIndications`,
which the parser derives from exactly the strings printed here -- so this is a
bot acting on evidence it never shows. The webifier's and the target painter's
literals are parsed and read by no rule in either app; printing them is how the
evidence for a rule about them accumulates, which is how #231's two were cut out
of a log rather than guessed at.

**The attrition warning fires on saxrat's own shipped configuration**, which is
the whole reason for porting it: both hitpoint thresholds default to `-1`, so a
run started without settings is exactly the state `attritionIsUnguarded` exists
to name, and nothing named it. `test_the_shipped_defaults_are_the_state_this_
names` executes that through the real `parseBotSettings`, and its control is
`run_saxrat.sh`'s own settings string, which arms the armour threshold and reads
guarded. Only the *warning* is ported: saxrat already prints the low-water marks
in `describeMenuAndSettlingCounters`, and two clauses for one pair of numbers is
two places to disagree about them.

**The top-row module state is what #154's own Unverified note asks for.** That
run could not say whether the client had taken the guns back; `switchOffUndoneByClient`
is a latch derived from `isInActiveState` and nothing in this bot printed the
field it derives from. The parser has carried all twelve entries here since they
were added.

**saxrat's idiom, not the mission runner's.** PR #242 shortened this bot's
status line and PR #244 established that four clauses are deliberately unshared
between the apps, each pinned by a case that fails if the two ever read the same.
`TheClausesAreSaxratsOwnWords` is the same pin for these three, executed on one
fixture through both apps: the information is the same and the words are not.

The rules are executed through the real `Bot.elm` in `elm repl`, and the readings
they are asked about are built by the real `EveOnline.ParseUserInterface` from UI
trees -- so what a case asserts on is what the bot would have been handed. The
source-read cases go through a declaration reader that drops doc comments, since
prose naming a clause is not a read of one.

Nothing here reads a live game client, a running bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import (
    MISSION_RUNNER_DIR, SAXRAT_BOT_ELM, SAXRAT_DIR, SaxratRepl, collapsed,
    label, node, source_of, tree_with)
from test_ewar_priority_targets import overview as overview_with_hints
from test_quick_message_logged import declaration, top_level_declarations

MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
MACOS_HOST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SAXRAT = os.path.join(MACOS_HOST_DIR, "run_saxrat.sh")

# The five literals the corpus holds, exactly as the client writes them. Nothing
# here is retyped from an issue; each was cut out of `~/eve-bot-logs` for #231
# and is repeated from `test_ewar_priority_targets` rather than imported,
# because what this file asks about them is a different question -- there, which
# ones a matcher admits; here, that all of them are shown whether a matcher
# admits them or not.
TRACKING_DISRUPTION = "Pilot is tracking disrupting me"
SENSOR_DAMPENING = "Pilot is sensor dampening me"
WARP_DISRUPTION = "Pilot is warp disrupting me"
TARGET_PAINTING = "Pilot is target painting me"
WEBIFYING = "Pilot is webifying me"

# The two the corpus carries that **no rule in either app reads**. #231 left
# them out deliberately -- a painter makes the ship easier to hit and a webifier
# is #40's open case -- so a clause that showed only what something acts on
# would show neither, and the evidence for ever acting on them would go on not
# accumulating. That is what `test_a_hint_no_rule_reads_is_shown_anyway` is for.
UNREAD_BY_ANY_RULE = (WEBIFYING, TARGET_PAINTING)

# A rat's icon colour, read off the live client: what makes a fixture row a row
# the overview drew rather than one this file invented.
RAT_COLOR = {"aPercent": 100, "rPercent": 100, "gPercent": 10, "bPercent": 10}
RAT_NAME = "Centii Minion"

# saxrat's own defaults, from `defaultBotSettings`. Asserted by execution below
# rather than trusted here; these are what the numbers should be.
SHIPPED_SHIELD_THRESHOLD = -1
SHIPPED_ARMOR_THRESHOLD = -1

# What `run_saxrat.sh` ships instead: the armour guard armed, the shield one off
# because this hull's shield rests at zero. Read back out of the launcher below.
LAUNCHER_ARMOR_THRESHOLD = 80
LAUNCHER_SHIELD_THRESHOLD = -1


def launcher_settings():
    """The settings string `run_saxrat.sh` passes, as the launcher writes it.

    Taken from the launcher rather than restated, because the point of the
    control case is that the *shipped* configuration reads guarded -- a copy of
    the string here would go on saying so after somebody changed the launcher.
    """
    source = source_of(RUN_SAXRAT)
    start = source.index('SETTINGS="') + len('SETTINGS="')
    return source[start:source.index('"', start)]


def displayed_rows(rows):
    """Rows the overview rendered, in the shape `overview_with_hints` wants.

    Each is `(distance, name, hints, is_rat)`; `True` for the last because
    `parseOverviewWindowEntry` reads `_display` off the row and a fixture built
    without it is one the bot would treat as a virtualised row -- see
    `hidden_row` for the one case that wants that.
    """
    return [(distance, RAT_NAME, list(hints), True) for distance, hints in rows]


def overview_with_a_hidden_row(shown_hints, hidden_hints):
    """One rendered row and one the client did not render, each with hints.

    `overviewEntryIsDisplayed` reads `_display`, which the shared builder writes
    on every row, so the hidden row is built here instead -- same shape, same
    geometry, and `_display` set to `False` the way the client leaves a
    virtualised row. A hint on that row belongs to whatever was recycled into
    its place, which is the whole reason the filter is there.
    """
    window = overview_with_hints(displayed_rows([("1,000 m", shown_hints)]))
    scroll = window["children"][0]

    y = 40
    hidden = node("OverviewScrollEntry",
                  {"_name": "overviewEntry", "_display": False}, [
                      label("2,000 m", (10, y, 50, 16)),
                      label("Centii Savage", (110, y, 150, 16)),
                      label("Centii Savage", (310, y, 150, 16)),
                      node("SpaceObjectIcon", {}, [
                          node("Sprite",
                               {"_name": "iconSprite", "_color": RAT_COLOR},
                               region=(2, y, 8, 16)),
                      ], region=(2, y, 12, 16)),
                      node("Container", {"_name": "rightAlignedIconContainer"},
                           [node("Sprite", {"_hint": hint},
                                 region=(400 + n * 10, y, 8, 8))
                            for n, hint in enumerate(hidden_hints)],
                           region=(400, y, 90, 16)),
                  ], region=(0, y, 500, 16))
    scroll["children"].append(hidden)
    return window


def module_button(x, entries):
    """One top-row module slot carrying the client's own dict entries.

    The slot sits above the capacitor's vertical centre, which is what
    `groupShipUIModulesIntoRows` files it under `top` -- a fixture that put it
    level with the capacitor would be asking about the middle row, which is
    `describeModulesToActivateAlways`' subject and not this one.
    """
    return node("ShipSlot", {"_name": "slot%d" % x}, [
        node("ModuleButton", dict(entries, _name="modulebutton"),
             region=(x, 0, 32, 32)),
    ], region=(x, 0, 32, 32))


def ship_ui_with_top_row(modules, shield=95, armor=100, structure=100):
    """A `ShipUI` the real parser accepts, with `modules` in its top row.

    `modules` is a list of `(x, dict entries)`. The three gauges are all present
    because `parseShipUIFromUITreeRoot` answers `Nothing` for hitpoints unless
    every one of them is readable, and a fixture missing one would be asking
    about a reading the bot never gets.
    """
    def gauge(name, percent):
        return node("Gauge", {"_name": name, "_lastValue": percent / 100.0},
                    region=(0, 0, 100, 8))

    return node("ShipUI", {}, [
        node("CapacitorContainer", {}, region=(0, 40, 100, 20)),
        gauge("structureGauge", structure),
        gauge("armorGauge", armor),
        gauge("shieldGauge", shield),
    ] + [module_button(x, entries) for x, entries in modules],
        region=(0, 0, 400, 200))


class InstrumentRepl(SaxratRepl):
    """One app's `Bot.elm`, plus what asking a clause about a reading costs.

    Every clause is asked through `Maybe.map ... |> Maybe.withDefault`, and the
    default is a string no clause can produce. That puts a positive control
    inside each case: #174's failure is a fixture that never decoded, which
    answers `Nothing` and reads exactly like a clause that declined to say
    anything.
    """

    APP_DIR = SAXRAT_DIR

    NO_READING = "THE FIXTURE NEVER ARRIVED"

    def __init__(self, **kwargs):
        kwargs.setdefault("app_dir", self.APP_DIR)
        super().__init__(**kwargs)

    def reading(self, name, children):
        return self.reading_binding(name, children)

    def clause(self, name, reading="reading"):
        return '%s |> Maybe.map %s |> Maybe.withDefault "%s"' % (
            reading, name, self.NO_READING)

    def said(self, clause_name, children):
        """What `clause_name` prints for a reading built from `children`."""
        [answer] = self.strings([self.clause(clause_name)],
                                [self.reading("reading", children)])
        self.assert_arrived(answer)
        return answer

    def assert_arrived(self, answer):
        if answer == self.NO_READING:
            raise AssertionError(
                "the fixture did not decode, so this case would have been "
                "asserting against a reading the parser never built")


class SaxratInstrumentRepl(InstrumentRepl):
    APP_DIR = SAXRAT_DIR


class MissionRunnerInstrumentRepl(InstrumentRepl):
    APP_DIR = MISSION_RUNNER_DIR


class SaxratTest(unittest.TestCase):
    """A base that opens saxrat's repl once for the class."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratInstrumentRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()


class TheHintsTheClientWroteAreShown(SaxratTest):
    """Instrument one, executed over rows the real parser built.

    The corpus counts the mission runner's clause produced are what #231 was
    written on; what this class asserts is that saxrat now produces the same
    evidence, in its own words, from the same rows.
    """

    def test_a_rendered_rows_hints_are_printed_verbatim(self):
        """Case, spacing and punctuation exactly as the client wrote them.

        The next matcher is going to be written against this string -- #231's
        two were -- and a normalisation applied here is one nobody downstream
        can undo. `is sensor dampening me` against `damping` is the whole
        difference between a rule that fires and one that quietly never does.
        """
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(
                displayed_rows([("1,000 m", [TRACKING_DISRUPTION])]))])
        self.assertIn("'%s'" % TRACKING_DISRUPTION, said)
        self.assertTrue(said.startswith("hints 1 "), said)

    def test_a_hint_no_rule_reads_is_shown_anyway(self):
        """The webifier and the painter, which nothing in either app acts on.

        This is the case that makes the clause worth having rather than
        redundant with `combatPriorityTier`: a clause showing only what some
        rule already consumes would show neither of these, and the evidence for
        ever writing that rule would go on not accumulating. #40's webifier is
        still open for exactly this reason.
        """
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(
                displayed_rows([("1,000 m", list(UNREAD_BY_ANY_RULE))]))])
        for hint in UNREAD_BY_ANY_RULE:
            self.assertIn("'%s'" % hint, said, hint)

    def test_a_quiet_grid_says_so_rather_than_saying_nothing(self):
        """A reading with no hints still prints the clause.

        "no row carried a hint" and "this bot does not carry the clause" have to
        be distinguishable in a log, which is `describeClearing`'s rule and is
        precisely what saxrat's corpus could not answer: 227,749 readings with
        no line either way.
        """
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(displayed_rows([("1,000 m", [])]))])
        self.assertEqual(said, "hints 0.")

    def test_a_row_the_client_did_not_render_contributes_nothing(self):
        """`overviewEntryIsDisplayed`, and it is not a tidiness filter.

        A virtualised row keeps whatever position and contents it last held
        while something else is recycled into its place, so a hint read off one
        is a hint attributed to the wrong object -- which is #265's own subject
        from the other end.
        """
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_a_hidden_row([TRACKING_DISRUPTION], [WEBIFYING])])
        self.assertIn("'%s'" % TRACKING_DISRUPTION, said)
        self.assertNotIn(
            WEBIFYING, said,
            "a hint on a row the client did not render reached the status "
            "line, so the clause is reporting whatever was recycled into that "
            "row's place")
        self.assertTrue(said.startswith("hints 1 "), said)

    def test_the_same_hint_on_two_rows_is_one_string(self):
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(displayed_rows([
                ("1,000 m", [TRACKING_DISRUPTION]),
                ("2,000 m", [TRACKING_DISRUPTION]),
            ]))])
        self.assertEqual(said.count(TRACKING_DISRUPTION), 1, said)
        self.assertTrue(said.startswith("hints 1 "), said)

    def test_two_different_hints_are_both_kept(self):
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(displayed_rows([
                ("1,000 m", [TRACKING_DISRUPTION]),
                ("2,000 m", [SENSOR_DAMPENING]),
            ]))])
        self.assertIn("'%s'" % TRACKING_DISRUPTION, said)
        self.assertIn("'%s'" % SENSOR_DAMPENING, said)
        self.assertTrue(said.startswith("hints 2 "), said)

    def test_the_count_is_not_capped_where_the_list_is(self):
        """A reading past the cap says so by the number exceeding the strings.

        The cap is a bound on line length rather than on what is being
        reported, so the two have to be able to disagree -- a count clamped to
        the cap would make "eight hints" and "twenty hints" the same reading.
        """
        many = ["Pilot indication number %d" % index for index in range(12)]
        said = self.repl.said(
            "describeOverviewIndicationHints",
            [overview_with_hints(displayed_rows([("1,000 m", many)]))])
        self.assertTrue(said.startswith("hints 12 "), said)
        shown = re.findall(r"'([^']*)'", said)
        self.assertEqual(len(shown), 8, said)
        self.assertEqual(shown, many[:8], said)


class TheAttritionWarningNamesTheShippedConfiguration(SaxratTest):
    """Instrument two, executed at both sides of each threshold's boundary.

    The hole four of PR #120's own cases had was a boundary pair that any
    constant satisfies, so every boundary here is asked beside a fixed value on
    the far side of it: a rule answering `True` for everything, or `False` for
    everything, fails rather than passing on whichever pair a case named.
    """

    def unguarded(self, pairs):
        return self.repl.evaluate([
            "attritionIsUnguarded { shieldThresholdPercent = %d,"
            " armorThresholdPercent = %d }" % pair for pair in pairs])

    def test_both_thresholds_off_is_the_state_it_names(self):
        self.assertEqual(
            self.unguarded([(-1, -1), (-5, -20)]), [True, True])

    def test_a_threshold_of_zero_is_not_cover(self):
        """`0` is a keystroke from `-1` and is equally unable to fire.

        A percentage never goes below zero, so `lowestPercentSinceHealthy < 0`
        is false on every reading there has ever been. The bound is read off
        that comparison rather than off the `-1` disabling convention, so the
        two cannot drift apart -- and a `0` that looked configured would
        otherwise be reported as cover.
        """
        self.assertEqual(
            self.unguarded([(0, 0), (0, -1), (-1, 0)]), [True, True, True])

    def test_either_threshold_armed_is_cover(self):
        """One armed guard is cover, which is what makes this `&&` and not `||`.

        The boundary is asked in both directions and beside a fixed pair well
        clear of it, so a rule that answered `True` for everything -- the shape
        that would print the warning on a properly configured run and teach an
        operator to ignore it -- fails here.
        """
        self.assertEqual(
            self.unguarded([(1, 0), (0, 1), (25, 70), (-1, 80), (25, -1)]),
            [False, False, False, False, False])

    def test_the_shipped_defaults_are_the_state_this_names(self):
        """The whole point of porting it, executed rather than asserted.

        Asked of `defaultBotSettings` *and* of what `parseBotSettings` makes of
        an empty settings string, because those are two different things a run
        can start from and only the second is what a bot launched with no
        settings actually gets.
        """
        answers = self.repl.evaluate([
            "attritionIsUnguarded"
            " { shieldThresholdPercent ="
            " defaultBotSettings.runAwayShieldHitpointsThresholdPercent"
            ", armorThresholdPercent ="
            " defaultBotSettings.runAwayArmorHitpointsThresholdPercent }",
            'parseBotSettings "" |> Result.map (\\settings ->'
            " attritionIsUnguarded"
            " { shieldThresholdPercent ="
            " settings.runAwayShieldHitpointsThresholdPercent"
            ", armorThresholdPercent ="
            " settings.runAwayArmorHitpointsThresholdPercent })"
            " |> Result.withDefault False",
            # The control for the line above: `Result.withDefault False` reads
            # a settings string that would not parse as "guarded", so a case
            # resting on it has to show the string parsed at all.
            'parseBotSettings "" |> Result.map (always True)'
            " |> Result.withDefault False",
        ])
        self.assertEqual(
            answers, [True, True, True],
            "saxrat's shipped configuration is no longer the state this rule "
            "exists to name, so either the defaults moved or the rule did")

    def test_the_launcher_arms_the_armour_guard_and_reads_guarded(self):
        """The control, and it is `run_saxrat.sh`'s own string.

        Two things at once: that the rule can answer `False` for a real
        configuration, so nothing above is passing on a rule that says `True`
        to everything; and that a run started by the launcher should **not**
        print the warning, which is what makes the warning appearing on such a
        run mean the settings are not reaching the bot.
        """
        settings = launcher_settings()
        self.assertIn("run-away-armor-hitpoints-threshold-percent=%d"
                      % LAUNCHER_ARMOR_THRESHOLD, settings)
        self.assertIn("run-away-shield-hitpoints-threshold-percent=%d"
                      % LAUNCHER_SHIELD_THRESHOLD, settings)
        literal = json.dumps(settings)
        answers = self.repl.evaluate([
            "parseBotSettings %s |> Result.map (\\settings ->"
            " attritionIsUnguarded"
            " { shieldThresholdPercent ="
            " settings.runAwayShieldHitpointsThresholdPercent"
            ", armorThresholdPercent ="
            " settings.runAwayArmorHitpointsThresholdPercent })"
            " |> Result.withDefault True" % literal,
            "parseBotSettings %s |> Result.map (always True)"
            " |> Result.withDefault False" % literal,
        ])
        self.assertEqual(
            answers, [False, True],
            "the launcher's own settings string no longer reads as covered, "
            "or no longer parses")


class TheAttritionClauseSpeaksOnEveryReading(SaxratTest):
    """What the clause prints, in both of its states.

    Rendered rather than asserted by substring over the branch: a case written
    over the branch's text passes for a clause that prints nothing at all, which
    is the trap PR #109's own status case fell into once.
    """

    def said(self, shield, armor):
        [answer] = self.repl.strings([
            "describeRetreatCover { shieldThresholdPercent = %d,"
            " armorThresholdPercent = %d }" % (shield, armor)])
        return answer

    def test_the_warning_names_the_setting_an_operator_can_act_on(self):
        said = self.said(SHIPPED_SHIELD_THRESHOLD, SHIPPED_ARMOR_THRESHOLD)
        self.assertIn("UNGUARDED", said)
        self.assertIn("run-away-armor-hitpoints-threshold-percent", said)

    def test_the_clause_speaks_on_the_guarded_case_too(self):
        """A clause present only under the warning is one that cannot be read.

        "the thresholds are armed" and "this bot has no such clause" would
        otherwise grep the same, which is the state saxrat's whole corpus is in
        and the reason this instrument is being ported at all.
        """
        said = self.said(LAUNCHER_SHIELD_THRESHOLD, LAUNCHER_ARMOR_THRESHOLD)
        self.assertNotEqual(said.strip(), "")
        self.assertNotIn("UNGUARDED", said)
        self.assertIn("attrition", said)

    def test_both_states_carry_both_numbers(self):
        """The thresholds by value, so a clause naming neither satisfies nothing.

        #244's shape: the words are saxrat's own and may be as short as they
        like, but a clause that dropped the numbers would leave an operator
        unable to tell a threshold that is off from one this bot never read.
        """
        for shield, armor in [(SHIPPED_SHIELD_THRESHOLD,
                               SHIPPED_ARMOR_THRESHOLD),
                              (LAUNCHER_SHIELD_THRESHOLD,
                               LAUNCHER_ARMOR_THRESHOLD)]:
            with self.subTest(shield=shield, armor=armor):
                said = self.said(shield, armor)
                self.assertIn(str(shield), said)
                self.assertIn(str(armor), said)

    def test_the_clause_does_not_reprint_the_low_water_marks(self):
        """The half deliberately left behind, and saxrat already prints it.

        `describeMenuAndSettlingCounters` carries `retreat is going by shield
        N%, armor M%` off `hitpointsLowWaterMark`. Porting the mission runner's
        `Retreat marks:` beside it would be two clauses for one pair of numbers
        and two places to disagree about them.
        """
        for shield, armor in [(-1, -1), (-1, 80)]:
            with self.subTest(shield=shield, armor=armor):
                said = self.said(shield, armor)
                self.assertNotIn("since healthy", said)
                self.assertNotIn("Retreat marks", said)

        saxrat = source_of(SAXRAT_BOT_ELM)
        clause = collapsed(declaration(saxrat, "describeRetreatCover"))
        self.assertNotIn("hitpointsLowWaterMark", clause)
        self.assertIn(
            "hitpointsLowWaterMark", collapsed(
                declaration(saxrat, "statusTextFromState")),
            "the low-water marks have left the status line, so trimming them "
            "from this clause now loses them entirely")


class TheTopRowModulesReportTheirOwnState(SaxratTest):
    """Instrument three, executed over module buttons the real parser built.

    Five entries per module, `/`-separated, in the order the legend names them:
    `ramp_active`, `isInActiveState`, `isDeactivating`, `effect_activating`,
    `waitingForActiveTarget`.
    """

    FIRING = {"ramp_active": True, "isInActiveState": True,
              "isDeactivating": False, "effect_activating": 0,
              "waitingForActiveTarget": 0}

    def said(self, modules):
        return self.repl.said("describeTopRowModuleDictState",
                              [ship_ui_with_top_row(modules)])

    def columns(self, said):
        return re.findall(r"[TF\-0-9]+(?:/[TF\-0-9]+){4}", said)

    def test_a_gun_that_is_firing_reads_the_way_the_sample_measured_it(self):
        said = self.said([(0, self.FIRING)])
        self.assertEqual(self.columns(said), ["T/T/F/0/0"], said)

    def test_the_switch_off_leg_is_what_the_column_records(self):
        """`T/F/T`, which is #154's own missing observation.

        The mission runner's run 11 measured the column going `T/T/F` ->
        `T/F/T` on the reading after the swap clicks the module button:
        `isInActiveState` `True` -> `False` and `isDeactivating` `False` ->
        `True` together, with `ramp_active` still `True` because the gun is
        finishing its cycle. saxrat's #154 could not say whether that happened
        because nothing here printed the field.
        """
        switching_off = dict(self.FIRING,
                             isInActiveState=False, isDeactivating=True)
        self.assertEqual(
            self.columns(self.said([(0, switching_off)])), ["T/F/T/0/0"])

    def test_absent_false_and_zero_all_print_differently(self):
        """Three distinct facts, and two of the three transitions were seen.

        `ramp_active` going absent -> present was measured, and so was it
        oscillating once present. Reading a run's log back afterwards is exactly
        when a collapsed pair cannot be told apart again.
        """
        absent = {}
        false_and_zero = {"ramp_active": False, "isInActiveState": False,
                          "isDeactivating": False, "effect_activating": 0,
                          "waitingForActiveTarget": 0}
        said = self.said([(0, absent), (40, false_and_zero)])
        self.assertEqual(self.columns(said), ["-/-/-/-/-", "F/F/F/0/0"], said)

    def test_the_row_is_ordered_by_position_not_by_index(self):
        """The row list is not a stable index space.

        A slot leaves and rejoins whenever its display region cannot be read, so
        two readings taken in list order would put one gun's values in
        another's column -- the kind of defect that only shows up when somebody
        tries to read the table months later.
        """
        left = dict(self.FIRING, effect_activating=1)
        right = dict(self.FIRING, effect_activating=2)
        # Built right-to-left, so a clause taking the parser's own order rather
        # than sorting answers `2` first.
        said = self.said([(80, right), (0, left)])
        self.assertEqual(self.columns(said), ["T/T/F/1/0", "T/T/F/2/0"], said)

    def test_it_reports_the_row_the_guns_are_in(self):
        """The top row, which is where the weapons are on this fit.

        The middle row is `describeModulesToActivateAlways`' subject and is
        already printed; a clause that quietly read that row instead would
        duplicate it and report nothing about the guns.
        """
        clause = collapsed(
            declaration(source_of(SAXRAT_BOT_ELM),
                        "describeTopRowModuleDictState"))
        self.assertIn("moduleButtonsRows.top", clause)
        self.assertNotIn("moduleButtonsRows.middle", clause)

    def test_a_reading_with_no_ship_ui_says_so(self):
        [answer] = self.repl.strings(
            [self.repl.clause("describeTopRowModuleDictState")],
            [self.repl.reading("reading", [])])
        self.repl.assert_arrived(answer)
        self.assertEqual(answer, "topmods no ship UI.")

    def test_a_ship_with_no_top_row_module_says_so(self):
        said = self.said([])
        self.assertEqual(said, "topmods none.")

    def test_the_five_keys_are_named_by_the_client_s_own_spelling(self):
        """The legend, so a column can be read back without this file.

        The keys are the client's own dict-entry names unchanged, which is what
        makes a value in a log line and a value in a UI tree the same word with
        no translation table to be right about.
        """
        said = self.said([(0, self.FIRING)])
        for key in ["ramp_active", "isInActiveState", "isDeactivating",
                    "effect_activating", "waitingForActiveTarget"]:
            self.assertIn(key, said, key)


class NoDecisionReadsAnyOfTheThree(unittest.TestCase):
    """The property that makes this a low-risk change, asserted rather than said.

    All three are instruments. A later branch that starts consulting one has to
    delete a named case to do it, which makes it a deliberate act rather than
    drift -- `TheFieldIsAnInstrumentAndNothingActsOnIt` and #35's own
    `ExposedAndNotActedOnTest` are the same posture, and both exist because #12
    and #34 were decisions built on a field's assumed meaning.

    Doc comments are dropped before counting, because prose about a clause is
    not a read of one and a case that counted those would forbid explaining the
    thing it is pinning. Nothing here needs `elm`.
    """

    # What may name each of the five declarations this change adds, besides the
    # declaration itself. `statusTextFromState` is saxrat's whole status line,
    # `describeRetreatCover` is the only thing that may ask the rule, and
    # `describeOverviewIndicationHints` is the only thing that may read the cap.
    ALLOWED_READERS = {
        "describeOverviewIndicationHints": {"statusTextFromState"},
        "overviewIndicationHintsShown": {"describeOverviewIndicationHints"},
        "attritionIsUnguarded": {"describeRetreatCover"},
        "describeRetreatCover": {"statusTextFromState"},
        "describeTopRowModuleDictState": {"statusTextFromState"},
    }

    def setUp(self):
        self.declarations = top_level_declarations(source_of(SAXRAT_BOT_ELM))

    def readers_of(self, name):
        return {other for other, body in self.declarations.items()
                if other != name and re.search(r"\b%s\b" % name, body)}

    def test_each_instrument_is_read_by_the_status_line_and_by_nothing_else(self):
        for name, allowed in self.ALLOWED_READERS.items():
            with self.subTest(declaration=name):
                self.assertIn(name, self.declarations,
                              "%s is not a top-level declaration" % name)
                self.assertEqual(
                    self.readers_of(name), allowed,
                    "%s is read somewhere other than %s -- if a decision is "
                    "meant to consult it now, that is a change with its own "
                    "evidence and this case is where it gets argued for"
                    % (name, ", ".join(sorted(allowed))))

    def test_the_status_line_is_the_only_caller_and_it_calls_all_three(self):
        """A clause that answers correctly and is never asked is not an instrument.

        The other half of the case above: nothing outside the status line reads
        them, and the status line really does.
        """
        status = collapsed(declaration(source_of(SAXRAT_BOT_ELM),
                                       "statusTextFromState"))
        for name in ["describeOverviewIndicationHints", "describeRetreatCover",
                     "describeTopRowModuleDictState"]:
            with self.subTest(clause=name):
                self.assertIn(name, status)

    def test_the_retreat_itself_is_untouched(self):
        """`runAwayIfLowHealth` decides on the gauges and on nothing added here.

        A run that was covered before is covered identically now. That is the
        claim the whole change rests on, and it is one line to check.
        """
        retreat = collapsed(declaration(source_of(SAXRAT_BOT_ELM),
                                        "runAwayIfLowHealth"))
        self.assertNotIn("attritionIsUnguarded", retreat)
        self.assertNotIn("describeRetreatCover", retreat)
        self.assertIn("context.memory.hitpointsLowWaterMark.shield"
                      " < runAwayShieldThreshold", retreat)
        self.assertIn("context.memory.hitpointsLowWaterMark.armor"
                      " < runAwayArmorThreshold", retreat)


class TheClausesAreSaxratsOwnWords(unittest.TestCase):
    """PR #244's pin, for the three clauses this change adds.

    Four clauses are already deliberately unshared between the apps --
    `describeQuickMessage`, `describeTargetHitpoints`, `describeMaxTargets`,
    `describeDroneLaunchCeiling` -- each held apart by a case that fails if the
    two ever read the same. PR #242 shortened saxrat's status line and the
    mission runner's was left alone, so a port that carried the mission
    runner's sentences across would be undoing that decision without anyone
    making it.

    What is compared is the *rendering*, on one fixture, through both apps: the
    rules are the same question and the words are not. `attritionIsUnguarded`
    is the exception and goes the other way -- it is a rule rather than a
    rendering, so it is asserted identical, which is the same split the quick
    message's three rules and one clause are held to.
    """

    @classmethod
    def setUpClass(cls):
        cls.repls = [("saxrat", open_repl(SaxratInstrumentRepl)),
                     ("mission runner", open_repl(MissionRunnerInstrumentRepl))]

    @classmethod
    def tearDownClass(cls):
        for _, repl in cls.repls:
            repl.close()

    def rendered(self, clause_name, children):
        return {name: repl.said(clause_name, children)
                for name, repl in self.repls}

    def test_the_hint_clauses_say_the_same_thing_in_different_words(self):
        said = self.rendered(
            "describeOverviewIndicationHints",
            [overview_with_hints(
                displayed_rows([("1,000 m", [TRACKING_DISRUPTION])]))])
        self.assertNotEqual(
            said["saxrat"], said["mission runner"],
            "the two apps' hint clauses now read the same, so this is a fifth "
            "clause #244's argument covers and either the divergence is over "
            "or the port took the wrong words")
        for app, answer in said.items():
            self.assertIn(TRACKING_DISRUPTION, answer, app)

    def test_the_module_clauses_say_the_same_thing_in_different_words(self):
        firing = {"ramp_active": True, "isInActiveState": True,
                  "isDeactivating": False, "effect_activating": 0,
                  "waitingForActiveTarget": 0}
        said = self.rendered("describeTopRowModuleDictState",
                             [ship_ui_with_top_row([(0, firing)])])
        self.assertNotEqual(
            said["saxrat"], said["mission runner"],
            "the two apps' top-row clauses now read the same")
        for app, answer in said.items():
            self.assertIn("T/T/F/0/0", answer, app)

    def test_the_retreat_cover_clauses_diverge_and_the_rule_does_not(self):
        """The rendering diverges; the rule it asks is byte for byte the same.

        The mission runner's clause takes a whole `BotDecisionContext` and
        cannot be executed, so this half is read out of both sources. What it
        pins is the shape of the divergence: saxrat's is a function of a record
        -- which is what let every case above execute it -- and prints no
        low-water marks, where the mission runner's prints them and reaches into
        a context for them.
        """
        saxrat = source_of(SAXRAT_BOT_ELM)
        mission = source_of(MISSION_RUNNER_BOT_ELM)

        self.assertEqual(
            collapsed(declaration(saxrat, "attritionIsUnguarded")),
            collapsed(declaration(mission, "attritionIsUnguarded")),
            "the rule has diverged between the apps -- the wording may differ "
            "per app, the question may not")

        self.assertNotEqual(
            collapsed(declaration(saxrat, "describeRetreatCover")),
            collapsed(declaration(mission, "describeRetreatCover")),
            "the two clauses now read the same, so this case is asserting a "
            "divergence that is over")

        self.assertIn("lowestShieldPercentSinceHealthy",
                      collapsed(declaration(mission, "describeRetreatCover")),
                      "the mission runner has dropped the low-water marks, so "
                      "saxrat trimming them is no longer the divergence this "
                      "describes")
        self.assertNotIn(
            "context",
            collapsed(declaration(saxrat, "describeRetreatCover")),
            "saxrat's clause reaches for a decision context, so the cases "
            "above can no longer execute it over a record")


if __name__ == "__main__":
    unittest.main()
