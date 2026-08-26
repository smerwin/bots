"""The wingman's health retreat, and where it sits in the decision tree.

Issue #364. Before it this bot had **no health-based retreat of any kind**. The
only place it read a hitpoint gauge at all was one raw live percentage printed
in the status line, which no decision looked at; the function called `runAway`
in `Bot.elm` is the neutral-in-local hiding logic reached through
`continueIfShouldHide` and has nothing to do with hitpoints. So the ship flew
hour-long and six-hour fleet tours with nothing watching its health.

What the cases here pin, and each is a different way the change could be wrong:

**The rules themselves.** `retreatStep` over `RetreatCase` and
`incomingDamageLatchAfterReading`, `lowWaterMarkAfterReading`,
`updateHitpointsGaugeMemory` and `plausibleHitpointsPercent` under it, executed
through the real `Bot.elm` in `elm repl` rather than restated in Python.

**That the guards ship disarmed.** All three thresholds default to `-1`,
because they are facts about a hull and no run of this bot has recorded what
this hull does under fire. A `-1` or `0` threshold must not fire at 0%
hitpoints, and the status line must say the retreat is disarmed rather than
looking like a healthy ship.

**That a single corrupt reading cannot fire it.** `0` is a legal armour
percentage and the mission runner's run 11 printed `Armor reached 0%` forty
times with the armour really at 82-96%. Nothing acts on a value a second
reading has not confirmed.

**That the arm is reachable while the guns are firing.** This is the half a
rule test cannot see and the half #360 got wrong on this same file: every arm
below the retreat answers `Just` for the whole of a fight, and the first arm to
answer ends the reading, so a retreat placed under any of them would be
reachable only on the readings the fleet is doing nothing.

Nothing here reads a live client, a recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import ElmRepl, open_repl  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# What `defaultBotSettings` ships. Not a tuning choice: a threshold is a fact
# about a hull, and no wingman run has been recorded anywhere.
DISABLED = -1


class WingmanRepl(ElmRepl):
    """The shared harness, plus the fold the gauge cases replay a run through.

    `believedAfterEach` drives the real `updateHitpointsGaugeMemory` over a
    series of readings and hands back the believed value after each one, so a
    case asserts about a series rather than about one call.
    """

    BINDINGS = [
        "believedAfterEach values = List.foldl (\\v acc ->"
        " updateHitpointsGaugeMemory v (Tuple.first acc) |> (\\m ->"
        " ( m, Tuple.second acc ++ [ m.believed ] ))) ( initHitpointsGaugeMemory, [] )"
        " values |> Tuple.second",
    ]

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-retreat-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        super().__init__(**kwargs)
        self.preamble = self.preamble + self.BINDINGS


def retreat_case(shield=100, shield_threshold=DISABLED, armor=100,
                 armor_threshold=DISABLED, latched="False", asked=0):
    return ("{ lowestShieldPercent = %s, shieldThresholdPercent = %s"
            ", lowestArmorPercent = %s, armorThresholdPercent = %s"
            ", damageLatchIsRetreating = %s, askedReadings = %s }"
            % (shield, shield_threshold, armor, armor_threshold,
               latched, asked))


def step(**kwargs):
    return "retreatStep %s" % retreat_case(**kwargs)


def reason(**kwargs):
    return "retreatReason %s" % retreat_case(**kwargs)


def latch(damage, threshold, before):
    return ("incomingDamageLatchAfterReading { damageInWindow = %s"
            ", threshold = %s, latchedBefore = %s }"
            % (damage, threshold, before))


def mark(showing, believed, previous):
    return ("lowWaterMarkAfterReading { shipUIIsShowing = %s"
            ", believed = %s, previous = %s }" % (showing, believed, previous))


def elm_maybe_ints(values):
    return "[ " + ", ".join(
        "Nothing" if value is None else "Just %d" % value
        for value in values) + " ]"


class TheRetreatDecisionTest(unittest.TestCase):
    """The rule, executed. Every case is one way a ship dies or does not."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_shipped_settings_never_fire(self):
        """All three default to -1, so a hull at nothing still stays.

        This is the whole of #364's "do not invent a calibrated number": the
        mechanism ships built and off, and an operator arms it from their own
        run's recorded gauge values.
        """
        self.assertEqual(
            self.repl.evaluate([
                "%s == NoRetreat" % step(shield=0, armor=0),
                "%s == Nothing" % reason(shield=0, armor=0),
                "defaultBotSettings.runAwayShieldHitpointsThresholdPercent == -1",
                "defaultBotSettings.runAwayArmorHitpointsThresholdPercent == -1",
                "defaultBotSettings.runAwayIncomingDamageThreshold == -1",
            ]),
            [True] * 5)

    def test_a_threshold_of_zero_cannot_fire_either(self):
        """A percentage never goes below zero, so `0` is as disarmed as `-1` --
        and it is one keystroke away from a number an operator meant."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == NoRetreat" % step(armor=0, armor_threshold=0),
                "%s == NoRetreat" % step(shield=0, shield_threshold=0),
                "retreatIsDisarmed { shieldThresholdPercent = 0"
                ", armorThresholdPercent = 0, damageThreshold = -1 }",
                "not (retreatIsDisarmed { shieldThresholdPercent = -1"
                ", armorThresholdPercent = 40, damageThreshold = -1 })",
                "not (retreatIsDisarmed { shieldThresholdPercent = -1"
                ", armorThresholdPercent = -1, damageThreshold = 0 })",
            ]),
            [True] * 5)

    def test_an_armed_armor_threshold_fires_and_says_which_guard(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == RejoinTheCommander RetreatOnArmorMark"
                % step(armor=55, armor_threshold=70),
                "%s == NoRetreat" % step(armor=70, armor_threshold=70),
                "%s == RejoinTheCommander RetreatOnArmorMark"
                % step(armor=69, armor_threshold=70),
            ]),
            [True] * 3)

    def test_an_armed_shield_threshold_fires_and_outranks_the_armor_one(self):
        """The order decides which reason an operator reads when both trip, and
        it is saxrat's own: shield, then armour, then the damage window."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == RejoinTheCommander RetreatOnShieldMark"
                % step(shield=10, shield_threshold=25),
                "%s == RejoinTheCommander RetreatOnShieldMark"
                % step(shield=10, shield_threshold=25, armor=5,
                       armor_threshold=70),
            ]),
            [True, True])

    def test_the_damage_window_fires_with_both_gauges_reading_full(self):
        """The instrument that needs no gauge, which is the point of it: a HUD
        that has started lying cannot disarm this one."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == RejoinTheCommander RetreatOnDamageWindow"
                % step(shield=100, armor=100, latched="True"),
            ]),
            [True])

    def test_the_ask_gives_up_at_the_bound_but_only_while_one_is_wanted(self):
        """Past the bound this arm hands the reading back so the drones and the
        guns still run -- `goToFleetMate` can end in a wait that dispatches
        nothing, and an arm this high in the tree parked there owns the bot.

        The bound is asked *after* "is a retreat wanted", the opposite order
        from `weaponsStep`, because this counter only advances while a retreat
        is decided: asking it first would report a give-up on a healthy ship.
        """
        self.assertEqual(
            self.repl.evaluate([
                "%s == RejoinTheCommander RetreatOnArmorMark"
                % step(armor=55, armor_threshold=70,
                       asked="retreatAskedReadingsBound - 1"),
                "%s == GaveUpOnRejoining RetreatOnArmorMark"
                % step(armor=55, armor_threshold=70,
                       asked="retreatAskedReadingsBound"),
                "%s == GaveUpOnRejoining RetreatOnArmorMark"
                % step(armor=55, armor_threshold=70,
                       asked="retreatAskedReadingsBound + 500"),
                "%s == NoRetreat"
                % step(asked="retreatAskedReadingsBound + 500"),
            ]),
            [True] * 4)

    def test_the_damage_latch_holds_until_the_window_is_empty(self):
        """A live comparison would cancel its own retreat: the moment the ship
        warps clear the window starts draining."""
        self.assertEqual(
            self.repl.evaluate([
                # Reaches the threshold: set.
                latch(3600, 3500, "False"),
                # Draining but not empty, and it was set: still set.
                "%s == True" % latch(120, 3500, "True"),
                # Empty: released.
                "%s == False" % latch(0, 3500, "True"),
                # Under the threshold and never set: stays clear.
                "%s == False" % latch(120, 3500, "False"),
                # The shipped setting. No amount of damage arms a `-1`.
                "%s == False" % latch(99999, -1, "False"),
            ]),
            [True] * 5)

    def test_a_single_corrupt_reading_is_not_evidence(self):
        """Run 11's `Armor reached 0%` forty times, with the armour at 82-96%.

        `believed` is the healthier of the last two believable readings, so the
        corrupt `0` never becomes the value a guard reads.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["believedAfterEach %s == %s"
                 % (elm_maybe_ints([95, 95, 0, 95, 95]),
                    elm_maybe_ints([95, 95, 95, 95, 95]))]),
            [True])

    def test_a_genuine_decline_still_retreats_one_reading_later(self):
        """It delays; it cannot suppress. On any non-increasing series the
        believed value is the previous reading's, so a hull really at 0% still
        gets there -- which is the case the guard exists for."""
        self.assertEqual(
            self.repl.evaluate([
                "believedAfterEach %s == %s"
                % (elm_maybe_ints([100, 0]), elm_maybe_ints([100, 100])),
                "believedAfterEach %s == %s"
                % (elm_maybe_ints([100, 0, 0]),
                   elm_maybe_ints([100, 100, 0])),
                "believedAfterEach %s == %s"
                % (elm_maybe_ints([75, 70, 65, 60]),
                   elm_maybe_ints([75, 75, 70, 65])),
            ]),
            [True] * 3)

    def test_readings_either_side_of_a_gap_do_not_vouch_for_each_other(self):
        """An unreadable gauge leaves nothing behind to confirm against, so the
        reading after a gap stands on its own rather than being withheld for
        ever -- a gauge readable every other reading would otherwise never be
        believed at all."""
        self.assertEqual(
            self.repl.evaluate([
                "believedAfterEach %s == %s"
                % (elm_maybe_ints([95, None, 20]),
                   elm_maybe_ints([95, None, 20])),
                "believedAfterEach %s == %s"
                % (elm_maybe_ints([20]), elm_maybe_ints([20])),
            ]),
            [True, True])

    def test_the_impossible_readings_are_rejected_by_value(self):
        """The mission runner's recorded corpus produced -1021821%, 2132822%
        and 8362%, always for one reading and always surrounded by sane ones."""
        self.assertEqual(
            self.repl.evaluate([
                "plausibleHitpointsPercent 2132822 == Nothing",
                "plausibleHitpointsPercent -1021821 == Nothing",
                "plausibleHitpointsPercent 101 == Nothing",
                "plausibleHitpointsPercent 0 == Just 0",
                "plausibleHitpointsPercent 100 == Just 100",
            ]),
            [True] * 5)

    def test_the_low_water_mark_holds_a_retreat_committed(self):
        """Without hysteresis a live threshold flips back the moment a repairer
        catches up, and the ship oscillates between fleeing and returning."""
        self.assertEqual(
            self.repl.evaluate([
                # Docked: there is no gauge and the next undock is a fresh hull.
                "%s == 100" % mark("False", "Just 20", 30),
                # Keeps the lowest seen.
                "%s == 30" % mark("True", "Just 40", 30),
                "%s == 20" % mark("True", "Just 20", 30),
                # An unreadable gauge changes nothing.
                "%s == 30" % mark("True", "Nothing", 30),
                # Released only well above every sane trip level.
                "%s == 30" % mark("True", "Just (runAwayRearmPercent - 1)", 30),
                "%s == 100" % mark("True", "Just runAwayRearmPercent", 30),
                "runAwayRearmPercent == 90",
            ]),
            [True] * 7)

    def test_the_mark_acts_on_the_reading_the_drop_arrives_on(self):
        """`lowWaterMarkAfterReading` folds a reading in after the decision has
        read it, so the retreat takes the `min` of the mark and this reading's
        believed value or it would act one reading late."""
        self.assertEqual(
            self.repl.evaluate([
                "lowestPercentSinceHealthy (Just 20) 100 == 20",
                "lowestPercentSinceHealthy (Just 80) 20 == 20",
                "lowestPercentSinceHealthy Nothing 20 == 20",
            ]),
            [True] * 3)


class TheRetreatIsReachableTest(unittest.TestCase):
    """Source-pinned: the placement is the half a rule test cannot see.

    #360 is the precedent on this exact file -- the target broadcast arm's rule
    was never wrong, it was starving every arm below it. A retreat under any
    arm that answers `Just` throughout a fight is a retreat that only fires
    when nothing is happening.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        return [self.source.index(needle) for needle in needles]

    def test_the_retreat_outranks_every_arm_that_fights(self):
        retreat, modules, broadcast, drones, guns, gate = self.order_of(
            "case retreatToTheCommander context",
            "case activateAlwaysOnModules context of",
            "case actOnFleetBroadcast context shipUI of",
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of",
            "case accelerationGateStep context of")
        self.assertLess(retreat, modules)
        self.assertLess(retreat, broadcast)
        self.assertLess(retreat, drones)
        self.assertLess(retreat, guns)
        self.assertLess(retreat, gate)

    def test_the_retreat_sits_below_the_one_arm_with_a_deadline(self):
        """`sessionIsEnding` is bounded by `tripHomeSecondsPastSessionEnd` and
        ends the session at the far end. A latched retreat above it could warp
        a damaged ship back to its commander for the rest of a session that was
        supposed to be over -- #350 again, one system later."""
        ending, retreat = self.order_of(
            "case sessionIsEnding context shipUI of",
            "case retreatToTheCommander context")
        self.assertLess(ending, retreat)

    def test_the_retreat_runs_to_the_fleet_and_not_to_the_hide_logic(self):
        """`runAway` in this file is the neutral-in-local hiding logic. The
        retreat must not reach it -- it docks or warps to a configured hide
        location, which is not the fleet and is not what a wingman needs."""
        body = self.source[
            self.source.index("\nretreatToTheCommander context"):]
        body = body[:body.index("\n\n\n")]
        self.assertIn("goToFleetMate context", body)
        self.assertIn("commander", body)
        self.assertIn("fleetCommanderName context", body)
        self.assertNotIn("runAway ", body)
        self.assertNotIn("dockAtRandomStationOrStructure", body)

    def test_the_hide_logic_still_owns_its_own_name(self):
        """The collision #364 warns about, asserted rather than assumed: the
        neutral-in-local branch still reaches `runAway`, and the retreat is a
        differently named function."""
        self.assertIn("(runAway context shipUI)", self.source)
        self.assertIn("Hide at configured location.", self.source)
        self.assertIn("retreatToTheCommander : BotDecisionContext", self.source)

    def test_the_guards_are_disarmed_and_visible_in_the_status_line(self):
        """This bot ships with all three thresholds off, so "nothing is
        watching" is the normal case rather than the exceptional one. A run
        whose thresholds were never set must not read like a healthy ship."""
        self.assertIn("describeRetreat context", self.source)
        self.assertIn("Retreat: DISARMED", self.source)
        self.assertIn("Retreat: GAVE UP after ", self.source)
        self.assertIn("NO COMBAT LOG", self.source)

    def test_no_decision_reads_a_live_hitpoint_gauge(self):
        """CLAUDE.md's "Retreating: the HUD hitpoint gauge is the weakest
        instrument here". The one reader of `hitpointsPercent` that feeds a
        decision goes through `plausibleHitpointsPercent` and `believed`; the
        only other one is the status line printing the raw value beside the
        believed pair, which is a report and not a decision."""
        self.assertIn(
            "|> Maybe.map (.hitpointsPercent >> whichGauge)\n"
            "                |> Maybe.andThen plausibleHitpointsPercent",
            self.source)
        code = "\n".join(
            line for line in self.source.splitlines()
            if "hitpointsPercent" in line)
        self.assertEqual(len(code.splitlines()), 3, code)
        self.assertIn("shipUI.hitpointsPercent.shield |> String.fromInt", code)


if __name__ == "__main__":
    unittest.main()
