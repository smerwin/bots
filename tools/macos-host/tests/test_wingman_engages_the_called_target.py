"""Tests for the wingman actually shooting what the fleet commander calls.

The bug these pin: a `Target` broadcast's banner **does not clear when the
target is locked**. It stays up for the rest of the call. The target arm of
`actOnFleetBroadcast` answered `Just (lock it)` on every reading while the
banner was up, and because that arm sits above `dronesAssistTheCommander` and
above the combat arm in `wingmanDecisionRootInSpace` -- where the first arm to
answer `Just` ends the reading -- the bot could never reach its drones or its
guns while a target was called.

So it locked what it was told to, correctly, on every reading, and never shot
it. Locking read as working and engaging read as broken, which is exactly how
it was reported from the field.

Three things had to change and each has cases here:

**The broadcast arm has to stand down once the lock exists**, otherwise
nothing below it is reachable. `bringCalledTargetUnderFire` answers `Nothing`
the moment the called target is in the target bar.

**Something has to fire.** Before `fireOnActiveTarget`, the only thing in this
bot that ever activated a weapon was `fightUsingDronesAndModules`, reachable
only through `fightRatsIfShipIsPointed` -- which answers `Nothing` unless a rat
has pointed this ship. A target the commander called is not pointing anybody.

**The fallback must not undo the drones.** `fightPointedRatsOrReturnDrones`
recalled drones whenever the ship was not pointed, which with a called target
locked would have fought `dronesAssistTheCommander` on every reading.

The cases run the real `Bot.elm` through `elm repl`. Nothing here reads a live
client, the recorded corpus, or a running bot.

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


class WingmanRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-engage-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        super().__init__(**kwargs)


def step(target_locked, inactive_weapon, asked):
    return ("weaponsStep { targetLocked = %s, inactiveWeaponPresent = %s"
            ", askedReadings = %s }" % (target_locked, inactive_weapon, asked))


class TheWeaponDecisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_nothing_locked_means_nothing_to_fire_on(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == NoTargetToFireOn" % step("False", "True", 0)]),
            [True])

    def test_a_locked_target_and_a_silent_weapon_activates_it(self):
        """The whole point: no rat has to be pointing this ship first."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAWeapon" % step("True", "True", 0)]),
            [True])

    def test_weapons_already_cycling_are_left_alone(self):
        self.assertEqual(
            self.repl.evaluate(
                ["%s == AllWeaponsCycling" % step("True", "False", 0)]),
            [True])

    def test_the_ask_gives_up_at_the_bound(self):
        """#326: a turret that could not activate held that bot's decision for
        262 consecutive readings with the drones out and idle."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == ActivateAWeapon"
                 % step("True", "True", "weaponsAskedReadingsBound - 1"),
                 "%s == GaveUpOnWeapons"
                 % step("True", "True", "weaponsAskedReadingsBound"),
                 "%s == GaveUpOnWeapons"
                 % step("True", "True", "weaponsAskedReadingsBound + 50")]),
            [True, True, True])

    def test_the_bound_is_reported_even_while_the_guns_happen_to_be_fine(self):
        """The bound is checked before the state, so a give-up is reported as
        one rather than masked by a moment when every weapon is cycling."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == GaveUpOnWeapons"
                 % step("True", "False", "weaponsAskedReadingsBound")]),
            [True])

    def test_the_bound_is_far_from_a_session_and_far_from_a_hiccup(self):
        self.assertEqual(
            self.repl.evaluate(
                ["weaponsAskedReadingsBound == 20"]),
            [True])


class TheDecisionRootReachesTheGunsTest(unittest.TestCase):
    """Source-pinned: the ordering *is* the bug, and it is a shape not a value.

    A test that only exercised `weaponsStep` would have passed on the broken
    bot too -- the rule was never wrong, it was unreachable.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def order_of(self, *needles):
        return [self.source.index(needle) for needle in needles]

    def test_the_guns_sit_below_the_drones_and_above_the_gate(self):
        """#326's rule, restated: reaching the drones must never require the
        weapons to read active first. Keeping the guns strictly below the
        drone arm is what makes that true whatever the guns do."""
        drones, guns, gate = self.order_of(
            "case dronesAssistTheCommander context of",
            "case fireOnActiveTarget context of",
            "case accelerationGateStep context of")
        self.assertLess(drones, guns)
        self.assertLess(guns, gate)

    def test_the_broadcast_arm_stands_down_once_the_target_is_locked(self):
        """Answering `Just` here on every reading is what starved everything
        below it, because the banner never clears on its own."""
        body = self.source[self.source.index("bringCalledTargetUnderFire context calledTarget ="):]
        body = body[:body.index("\n\n\n")]
        self.assertIn("Just _ ->", body)
        self.assertIn("Nothing", body)

    def test_the_fallback_leaves_the_drones_out_while_something_is_locked(self):
        self.assertIn(
            "A target is locked -- leaving the drones out.", self.source)

    def test_a_give_up_on_the_guns_is_visible_in_the_status_line(self):
        """`fireOnActiveTarget` answers `Nothing` when it gives up, so without
        its own status line a locked target with silent guns would read
        exactly like nothing to shoot."""
        self.assertIn("describeWeaponsAsk context", self.source)
        self.assertIn("Weapons: GAVE UP after ", self.source)


if __name__ == "__main__":
    unittest.main()
