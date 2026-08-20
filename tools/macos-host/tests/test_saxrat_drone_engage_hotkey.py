"""saxrat's drones engage the locked target directly, with F, not through Gal.

Issue: with idling drones and a locked target, `launchAndEngageDrones` drove a
context-menu cascade -- right-click the drones group, look for an 'Assist'
entry and, if present, a submenu entry named 'Gal Bistot'; otherwise fall back
to 'Engage Target'. That costs several readings of right-click/hover/click
before a drone fires a shot, and Gal is frequently not even on the grid, so
those readings bought nothing while a real target sat locked and unattended.

`F` is the client's own hotkey for "engage the current target with drones" --
already used by the mission runner (see "In-game hotkeys" in CLAUDE.md) and
already the second half of this exact function for launching drones
(`Shift+F`). The caller only reaches this branch from inside "I see a locked
target", past the container/wreck stray check (`Bot.elm`'s
`decideActionInAnomaly`), so a real target is always active by the time F is
pressed here.

This is read out of the source rather than executed through `elm repl`:
`launchAndEngageDrones` takes a whole `BotDecisionContext`, which is expensive
to construct for one branch, and what has to be pinned is a *replacement* --
one mechanism gone, another in its place -- which a whitespace-collapsing
reader over the declaration answers directly, the way `test_saxrat_ported_
guards.py` and `test_saxrat_message_box_standoff.py` read wiring that is not
itself an expression.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import unittest

from test_saxrat_ported_guards import SAXRAT_BOT_ELM, body_of, collapsed, source_of


def without_comments(text):
    """Drop `--` line comments before a case reads what the code itself does.

    This file's own new comment names the mechanism it replaced ('Assist',
    'Gal Bistot') to explain why, and an unrelated pre-existing commented-out
    drone-launch cascade a few lines below still says `useContextMenuCascade`.
    Both are prose about the code, not the code, so the negative assertions
    below read the declaration with comments stripped -- the same convention
    `test_saxrat_message_box_standoff.py` uses for the same reason.
    """
    return "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("--"))


def declaration(name, path=SAXRAT_BOT_ELM):
    return collapsed(body_of(source_of(path), name))


def declaration_code_only(name, path=SAXRAT_BOT_ELM):
    return collapsed(without_comments(body_of(source_of(path), name)))


class DroneEngageIsAHotkeyNotACascade(unittest.TestCase):
    def setUp(self):
        self.body = declaration("launchAndEngageDrones")
        self.code = declaration_code_only("launchAndEngageDrones")

    # -- the mechanism that replaced the cascade -----------------------------

    def test_the_idling_drones_branch_presses_f(self):
        self.assertIn("EffectOnWindow.KeyDown EffectOnWindow.vkey_F", self.body)
        self.assertIn("EffectOnWindow.KeyUp EffectOnWindow.vkey_F", self.body)

    def test_f_is_dispatched_through_decideActionForCurrentStep(self):
        # Not a context-menu cascade: a bare keypress dispatched as this
        # step's effects, the same shape the Shift+F launch branch already
        # uses lower in the same function.
        self.assertIn("decideActionForCurrentStep", self.body)

    def test_the_branch_is_still_named_for_an_operator_grepping_the_log(self):
        self.assertIn("Engage target with drones (F)", self.body)

    # -- the cascade this replaced is gone, not merely unreachable -----------

    def test_no_assist_cascade_remains_in_code(self):
        self.assertNotIn("Assist", self.code)
        self.assertNotIn("Gal Bistot", self.code)

    def test_no_custom_menu_choice_remains_in_code(self):
        self.assertNotIn("MenuEntryWithCustomChoice", self.code)
        # `useContextMenuCascade` still appears once, commented out, in the
        # pre-existing (and untouched) "Launch drones" branch below this
        # one -- so this asserts on live code only, not on its absence from
        # the declaration's text as a whole.
        self.assertNotIn("useContextMenuCascade", self.code)

    # -- the drone-launch half (Shift+F) is untouched -------------------------

    def test_the_launch_branch_still_holds_shift(self):
        # Confirms this change touched only the idling-drones branch: the
        # separate "launch more drones" branch a few lines below still holds
        # Shift down around F, which is a different client action (launch
        # rather than engage) and must not have been folded into this one.
        self.assertIn("EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT", self.body)
        self.assertIn("Launch drones", self.body)

    def test_both_f_presses_are_distinguishable_by_their_shift_wrapping(self):
        # A crude but real check that the file contains exactly the two F
        # presses expected -- one bare (engage), one Shift-wrapped (launch) --
        # rather than, say, three, which would mean a stray copy survived.
        self.assertEqual(self.body.count("EffectOnWindow.vkey_F"), 4)  # 2 KeyDown+KeyUp pairs


if __name__ == "__main__":
    unittest.main()
