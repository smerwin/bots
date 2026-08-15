"""Tests for switching the tank on before warping to an escalation.

The modules `manageMiddleRowModules` calls "always active" were not activated
before the ship warped to an opportunity site, and it failed twice over:

- **The gate could never open.** They are activated only while
  `somethingToFight` is true, which is right on an ordinary grid -- hardeners
  are a waste of capacitor with nothing shooting -- and cannot become true on
  the grid the ship is warping *from*. Warping to a site is the one moment the
  bot knows a fight is coming and can still do something about it.
- **The branch was never asked.** `manageMiddleRowModules` is consulted only
  where the ship is already inside a named anomaly. The site step is reached
  with `getCurrentAnomalyIDAsSeenInProbeScanner` answering `Nothing`, so it was
  not consulted at all on the path that warps.

So the ship arrived at escalations with its tank cold. Run 34 is what a Sansha
site does to a destroyer that is not ready for it: 6,025 hitpoints in 107
seconds, from tower sentries and a missile battery that start shooting on
arrival.

The rule is deliberately narrow -- one module per reading, falling through to
the warp as soon as nothing is inactive, and scoped to the opportunity warp
rather than to anomaly entry, which has the same gap and its own cost.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from test_saxrat_ported_guards import SAXRAT_BOT_ELM, body_of


class TheWarpAsksForTheTankFirstTest(unittest.TestCase):
    """Read out of the source: the branch is reachable only through a whole
    `BotDecisionContext` and a `SeeUndockingComplete`, neither of which a repl
    can build from a reading."""

    def setUp(self):
        with open(SAXRAT_BOT_ELM, encoding="utf-8") as handle:
            self.source = handle.read()

    def test_the_warp_arm_goes_through_the_tank_step(self):
        body = body_of(self.source, "siteProgressStepOrElse")
        arm = body.split("WarpToTheOpportunitySite ->")[1]
        arm = arm.split("HuntWithTheProbeScanner")[0]
        self.assertIn("tankBeforeWarpingToTheSite", arm,
                      "the opportunity warp is taken without asking for the "
                      "tank, which is the defect")

    def test_the_tank_step_reads_the_always_active_modules(self):
        body = body_of(self.source, "tankBeforeWarpingToTheSite")
        self.assertIn("inactiveModulesToActivateAlways", body)

    def test_it_activates_one_module_and_then_warps(self):
        """A module per reading, and the warp the moment none is inactive --
        not a wait, and not every module in one step."""
        body = body_of(self.source, "tankBeforeWarpingToTheSite")
        self.assertIn("List.head", body)
        self.assertIn("clickModuleButtonButWaitIfClickedInPreviousStep", body)
        self.assertIn("warpStep", body.split("Nothing ->")[1])

    def test_it_does_not_consult_something_to_fight(self):
        """The gate that could never open here. If this reappears the branch is
        back to being unreachable on the grid it is reached from."""
        body = body_of(self.source, "tankBeforeWarpingToTheSite")
        self.assertNotIn("somethingToFight", body)
        self.assertNotIn("anyAttackableInOverview", body)

    def test_both_callers_hand_over_the_ship(self):
        """`SeeUndockingComplete` is what carries the module buttons, so a
        caller that does not pass it cannot ask for the tank at all."""
        calls = re.findall(r"siteProgressStepOrElse context (\w+)", self.source)
        self.assertTrue(calls, "no call sites found")
        for argument in calls:
            self.assertEqual(argument, "seeUndockingComplete", calls)

    def test_the_signature_takes_the_ship(self):
        signature = re.search(r"^siteProgressStepOrElse :.*$", self.source, re.M)
        self.assertIsNotNone(signature)
        self.assertIn("SeeUndockingComplete", signature.group(0))

    def test_the_ordinary_module_rule_still_gates_on_a_fight(self):
        """Untouched: on an ordinary grid these modules stay off, which is what
        keeps this change from becoming 'run the tank all session'."""
        body = body_of(self.source, "manageMiddleRowModules")
        self.assertIn("somethingToFight", body)
        self.assertIn("inactiveModulesToActivateAlways", body)

    def test_anomaly_entry_is_deliberately_unchanged(self):
        """Stated so the next person reads it as a scope decision rather than
        an oversight -- the same gap exists there and wants its own evidence.

        Asserted against the doc comment rather than the body, which is where
        a scope decision lives and which `body_of` strips.
        """
        comment = self.source.split("tankBeforeWarpingToTheSite :")[0]
        comment = comment[-1600:]
        self.assertIn("Entering an anomaly has the same gap", comment,
                      "the doc comment no longer says the anomaly path was "
                      "left alone on purpose")


if __name__ == "__main__":
    unittest.main()
