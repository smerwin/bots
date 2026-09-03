"""Tests for a wingman setting that could never match anything (#400).

`activate-module-always` named ship modules by their tooltip text. That is a
real, working setting on several other apps in this repo -- but on the
wingman it could not be, because the step that reads a module's tooltip,
`readShipUIModuleButtonTooltips`, was called from exactly one place:
`decideNextActionWhenInSpaceNotHiding`, this app's inherited, unreachable copy
of `eve-online-combat-anomaly-bot`'s decision root, kept only for reference.
Nothing on the reachable `wingmanDecisionRootInSpace` ->
`wingmanDecisionRootInSpaceOrdinary` chain ever populated a tooltip, so
`knownModulesToActivateAlways` answered empty on every reading whatever the
setting named, and `activateAlwaysOnModules` -- the arm #349 split out of the
dead root so the wingman's own root could reach it -- correctly did nothing
with an empty list. An operator who set `activate-module-always` got exactly
the bot they would have got without it, while the header and `--help` told
them otherwise.

**#398's `manageMiddleRowModules` is what covers the operator need.** It holds
the whole middle row active by position, needing no setting and no tooltip --
see `WINGMAN.md`'s "The middle row is switched on by position, not by
tooltip". So the setting is removed rather than fixed: fixing it would mean
wiring `readShipUIModuleButtonTooltips` into the live root for a feature
`manageMiddleRowModules` already covers by a cheaper mechanism, on the
strength of nothing an operator has ever asked for that position cannot give
them.

**Both the field and the three functions it fed are gone**, not merely
unreachable: `activateModulesAlways` (the `BotSettings` field),
`activateAlwaysOnModules`, `knownModulesToActivateAlways` and
`tooltipLooksLikeModuleToActivateAlways`. `Common.AppSettings` answers an
unrecognised key with `Unknown setting name`, so a settings string still
carrying the line now ends the session at startup instead of silently doing
nothing -- `parseBotSettings`'s own contract, and the same one #125 and #161
rest on for the mission runner's `avoid-rat`.

**This app is not the general case.** `eve-online-combat-anomaly-bot`,
`eve-online-haulerbot`, `eve-online-mining-bot` and
`eve-online-warp-to-0-autopilot` all still accept `activate-module-always`
and all still read the field it fills -- their own decision roots call
`readShipUIModuleButtonTooltips` (or its inherited equivalent) directly, so
the setting reaches the client on those apps. Removing it here is an argument
about *this app's* dead root, not about the setting being a bad idea.

The cases run the real `Bot.elm` through `elm repl` rather than mirroring the
parser in Python -- `parseBotSettings` is executed, not read -- and the
sibling apps are read straight off disk to confirm they were not swept up
with it.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, HERE)

from prerequisites import open_repl  # noqa: E402
from test_avoid_rat_removed import (  # noqa: E402
    advertised_keys, bot_elm, elm_string, setting_keys, top_level_blocks)
from test_wingman_reads_the_fleet_window import (  # noqa: E402
    WINGMAN_BOT_ELM, WINGMAN_DIR, WingmanRepl, wingman_root_body)

APPLICATIONS_DIR = os.path.join(REPO_DIR, "implement", "applications",
                                "eve-online")
BOT_HELP = os.path.join(MACOS_HOST_DIR, "bot_help.py")

SETTING = "activate-module-always"
FIELD = "activateModulesAlways"

# The three functions the setting fed, all of it -- the header default, the
# parser handler and the field on `BotSettings` are the record type's own
# occurrences and are covered by `FIELD` above.
DEAD_DECLARATIONS = (
    "activateAlwaysOnModules",
    "knownModulesToActivateAlways",
    "tooltipLooksLikeModuleToActivateAlways",
)

# Every settings key this bot still accepts, named rather than discovered, so
# a case here fails loudly if one of them is swept up by accident.
SETTINGS_THAT_REMAIN = (
    "accept-fleet-invite-from",
    "follow-fleet-broadcast-from",
    "answer-backup-calls",
    "home-station",
    "assist-fleet-commander",
    "orbit-fc",
    "approach-fc",
    "orbit-fc-range",
    "orbit-in-combat",
    "deactivate-module-on-warp",
    "run-away-shield-hitpoints-threshold-percent",
    "run-away-armor-hitpoints-threshold-percent",
    "run-away-incoming-damage-threshold",
)

# Apps elsewhere in this repo that still implement the setting for real --
# their own decision roots reach `readShipUIModuleButtonTooltips` (or its
# inherited equivalent), so nothing here should touch them.
APPS_THAT_STILL_IMPLEMENT_IT = (
    "eve-online-combat-anomaly-bot",
    "eve-online-haulerbot",
    "eve-online-mining-bot",
    "eve-online-warp-to-0-autopilot",
)

# The header's own example settings string, which this file's source keeps in
# step with `Bot.elm`'s -- if one drifts from the other this constant is
# wrong rather than silently untested.
HEADER_EXAMPLE = (
    "accept-fleet-invite-from=Gal Bistot\n"
    "follow-fleet-broadcast-from=Gal Bistot\n"
    "home-station=Amarr VIII (Oris) - Emperor Family Academy"
)


def run_bot_help(bot_source_dir, script="fly.sh"):
    """`--help`'s stdout for `bot_source_dir`, as a subprocess.

    A subprocess rather than an import -- `test_documented_settings_are_
    parsed.help_text`'s reason: importing `bot_help` resets SIGPIPE for the
    whole test process, and a subprocess is also the stronger assertion,
    since it is what an operator actually reads.
    """
    result = subprocess.run(
        ["python3", BOT_HELP, bot_source_dir, "--script", script],
        capture_output=True, text=True, check=True)
    return result.stdout


class SettingsRepl(WingmanRepl):
    """The shared harness, plus the two questions this file asks of it."""

    def parses(self, settings_strings):
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def rejection_reasons(self, settings_strings):
        return self.strings([
            'parseBotSettings %s |> Result.map (always "<accepted>") '
            "|> Result.Extra.merge" % elm_string(settings)
            for settings in settings_strings])


def repl():
    return open_repl(
        SettingsRepl, prefix="test-wingman-no-activate-module-always-",
        preamble=("import Bot exposing (..)", "import Result.Extra"))


class TheWingmanNoLongerAcceptsIt(unittest.TestCase):
    """Executed through the real parser rather than read.

    Every case here would have passed with the opposite assertion before
    #400 -- the parser took the key and filled a field nothing on this bot's
    reachable root ever consulted.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_key_it_used_to_accept_is_refused(self):
        self.assertEqual(
            self.repl.parses(["%s=shield hardener" % SETTING]), [False])

    def test_the_refusal_names_the_key_so_an_operator_can_delete_the_line(self):
        reason = self.repl.rejection_reasons(
            ["%s=shield hardener" % SETTING])[0]
        self.assertIn(SETTING, reason)
        self.assertIn("Unknown setting name", reason)

    def test_one_such_line_rejects_the_whole_settings_string(self):
        self.assertEqual(
            self.repl.parses([
                "orbit-fc=no\n%s=shield hardener" % SETTING]),
            [False])

    def test_the_header_s_own_example_settings_string_still_parses(self):
        # What makes the removal safe rather than merely justified: the one
        # settings string this file's own doc comment quotes back at an
        # operator still starts a session.
        self.assertEqual(self.repl.parses([HEADER_EXAMPLE]), [True])

    def test_the_settings_beside_it_still_parse(self):
        integer_valued = (
            "run-away-shield-hitpoints-threshold-percent",
            "run-away-armor-hitpoints-threshold-percent",
            "run-away-incoming-damage-threshold",
        )
        for key in SETTINGS_THAT_REMAIN:
            value = "50" if key in integer_valued else "yes"
            with self.subTest(key):
                self.assertEqual(
                    self.repl.parses(["%s=%s" % (key, value)]), [True])


class TheFieldAndItsThreeDeclarationsAreGone(unittest.TestCase):
    """No occurrence at all, on this app, which is what makes it complete.

    The finding was "reachable code, never reached". Asserting zero
    occurrences is the same argument in the same terms, and it fails on a
    reintroduction that puts the field or a handler back without wiring a
    reader -- which the repl cases above cannot see, since they only ask
    what the parser accepts.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = bot_elm("eve-online-wingman")
        cls.help = run_bot_help(WINGMAN_DIR)

    def test_no_declaration_and_no_field_survive(self):
        for name in DEAD_DECLARATIONS + (FIELD,):
            with self.subTest(name):
                self.assertNotIn(name, self.source)

    def test_the_parser_does_not_accept_the_key(self):
        keys = setting_keys(self.source)
        self.assertNotIn(SETTING, keys)
        for key in ("accept-fleet-invite-from", "home-station", "orbit-fc"):
            with self.subTest(key):
                self.assertIn(key, keys)

    def test_the_help_text_no_longer_advertises_it(self):
        offered = advertised_keys(self.help)
        self.assertNotIn(SETTING, offered)
        self.assertIn("home-station", offered)
        self.assertNotIn(
            SETTING,
            "".join(self.help.split(
                "Also accepted, but not described in the "
                "bot's own header:")[1:]))

    def test_the_help_text_still_tells_an_operator_what_happened_to_it(self):
        self.assertIn(SETTING, self.help)
        self.assertIn("Unknown setting name", self.help)
        self.assertIn("manageMiddleRowModules", self.help)


class TheReachableRootNoLongerNamesTheDeadArm(unittest.TestCase):
    """Source-pinned: the wiring is the half a parser case cannot see.

    A rule test alone would pass on a bot that still called the removed
    function from a live branch, so long as nothing named it in a settings
    string during the test -- which is exactly #349's original defect: the
    function was correct and reachable from the wrong root.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_dead_arm_is_absent_from_the_whole_file(self):
        for name in DEAD_DECLARATIONS:
            with self.subTest(name):
                self.assertNotIn(name, self.source)

    def test_manage_middle_row_modules_is_the_whole_module_step(self):
        """Directly under `unlockFleetPilotInTargetBar`, the slot the
        tooltip arm and the position arm used to share (#398's own rebase
        note in `test_wingman_answers_a_backup_call.py`)."""
        root = wingman_root_body(self.source)
        self.assertIn("case unlockFleetPilotInTargetBar context of", root)
        self.assertIn("case manageMiddleRowModules context of", root)
        self.assertLess(
            root.index("case unlockFleetPilotInTargetBar context of"),
            root.index("case manageMiddleRowModules context of"))

    def test_the_inherited_dead_root_still_falls_back_without_the_arm(self):
        """`decideNextActionWhenInSpaceNotHiding` is kept for reference
        (#349's own comment says so) and must still compile without the
        function this change deletes -- it now falls through
        `readShipUIModuleButtonTooltips` straight to
        `fightPointedRatsOrReturnDrones`."""
        start = self.source.index(
            "\ndecideNextActionWhenInSpaceNotHiding ")
        body = self.source[start:self.source.index("\n\n\n", start)]
        self.assertIn("readShipUIModuleButtonTooltips context", body)
        self.assertIn("fightPointedRatsOrReturnDrones context shipUI", body)
        self.assertNotIn("activateAlwaysOnModules", body)


class TheSiblingAppsStillImplementIt(unittest.TestCase):
    """The other half of the scoping argument: this is a fact about the
    wingman's dead root, not about the setting.

    Named rather than discovered, so a future removal on one of these apps
    fails here instead of quietly narrowing what this file protects.
    """

    def test_each_sibling_still_accepts_and_reads_the_setting(self):
        for app in APPS_THAT_STILL_IMPLEMENT_IT:
            with self.subTest(app):
                source = bot_elm(app)
                self.assertIn(SETTING, setting_keys(source))
                blocks = top_level_blocks(source)
                read_sites = [
                    name for name, text in blocks.items()
                    if FIELD in text
                    and name not in ("defaultBotSettings", "parseBotSettings",
                                     "BotSettings")]
                self.assertTrue(
                    read_sites,
                    "%s no longer reads %s -- that is this change's own "
                    "removal, arrived in the wrong app" % (app, FIELD))


if __name__ == "__main__":
    unittest.main()
