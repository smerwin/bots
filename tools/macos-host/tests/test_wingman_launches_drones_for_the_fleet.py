"""Tests for the wingman actually launching drones to assist its commander.

Issue #374. `dronesAssistTheCommander` is the one drone arm wired into the
live decision tree (`implement/applications/eve-online/eve-online-wingman/
Bot.elm`, sitting right after the broadcast arm and above the guns), and it
only ever *redirects drones already in space*: it derives `idlingDrones` from
`droneGroupInSpace`, and with nothing out there that count is always zero. A
six-hour recorded run (`wingman_run12.log`) confirms it end to end -- `In
bay: 15, in space: 0.` on every reading of the whole session, including
readings that logged `A target is locked -- leaving the drones out.`

The function that actually launches from the bay, `dronesForTheFleet`
(a one-line wrapper around `launchAndEngageDrones { redirectToTargets =
Nothing }`), has existed since the very first wingman skeleton commit
(`be47b3f`, before `dronesAssistTheCommander` was even written across
#345/#360/#365) and had exactly one occurrence in the whole file: its own
declaration. Dead code from day one.

**The fix reuses rather than reimplements.** `dronesAssistTheCommander` now
falls through to `dronesForTheFleet context` in both branches that used to
answer bare `Nothing` -- no `droneGroupInSpace` at all, and a
`droneGroupInSpace` with nothing idling in it -- so the same arm that
redirects idling drones is what puts drones out in the first place.
`launchAndEngageDrones`' own bandwidth, quantity and space-limit gating
(`considerLaunch`) is untouched and unduplicated.

Two things need pinning here, and neither needs a full UI-tree fixture for a
`DronesWindow` (which `dronesAssistTheCommander` reaches through a whole
`BotDecisionContext` it takes no pure step function out of, unlike
`weaponsStep` or `orbitFleetCommanderStep` next door -- building one well
enough to be worth trusting is its own change).

**The wiring**, read out of `dronesAssistTheCommander`'s own body through a
reader sliced to just that declaration, so a match inside some other
function's `Nothing` cannot pass this by accident. Both of its old bare
`Nothing` fallbacks must now read `dronesForTheFleet context`, and the
gating this reuses (`assistFleetCommander`, the drones window, the commander
name) must be untouched -- a case that only checked "does the string
`dronesForTheFleet` appear somewhere in the file" would pass on a version
that called it from the wrong branch, or twice from the right one and never
the wrong one.

**That the module still compiles and both functions keep their type**,
executed through the real `Bot.elm` in `elm repl` rather than assumed from
reading the diff -- a full recompile is what would have caught a stray
brace or a typo'd call.

Nothing here reads a live client, the recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
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
        kwargs.setdefault("prefix", "wingman-drones-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault(
            "preamble",
            ("import Bot exposing (..)",
             "import EveOnline.BotFrameworkSeparatingMemory"))
        super().__init__(**kwargs)


def top_level_declaration(source, name):
    """The body of one top-level declaration, sliced by indentation.

    Starts at the line beginning `<name> ` or `<name>=` (the pattern's own
    call site, not its type signature) and runs until the next line that
    starts at column 0 -- the next top-level declaration. The `let`-binding
    extractors elsewhere in this suite read a binding this same way, for the
    same reason: stopping at the next blank line or `in` reads only part of
    a multi-branch body.
    """
    match = re.search(r"^%s\b[^\n]*=\n" % re.escape(name), source, re.MULTILINE)
    if match is None:
        raise AssertionError("no top-level declaration named %r" % name)
    start = match.end()
    rest = source[start:]
    boundary = re.search(r"^\S", rest, re.MULTILINE)
    end = start + boundary.start() if boundary else len(source)
    return source[start:end]


class TheDroneArmLaunchesRatherThanOnlyRedirecting(unittest.TestCase):
    """Source-pinned: what the fix actually changed, read out of `Bot.elm`."""

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()
        cls.assist_body = top_level_declaration(cls.source, "dronesAssistTheCommander")
        cls.launch_body = top_level_declaration(cls.source, "dronesForTheFleet")

    def test_dronesForTheFleet_still_exists_and_wraps_launchAndEngageDrones(self):
        self.assertIn(
            "launchAndEngageDrones { redirectToTargets = Nothing } context",
            self.launch_body)

    def test_dronesAssistTheCommander_falls_through_to_it_with_no_space_group(self):
        # The `droneGroupInSpace` pattern's `Nothing` arm.
        self.assertIn("dronesForTheFleet context", self.assist_body)
        self.assertNotIn(
            "Nothing ->\n                        Nothing",
            self.assist_body)

    def test_dronesAssistTheCommander_falls_through_to_it_when_nothing_is_idling(self):
        self.assertIn("if idlingDrones < 1 then\n                            dronesForTheFleet context",
                       self.assist_body)

    def test_the_fallback_appears_exactly_twice(self):
        # Once per branch that used to answer bare `Nothing`. A third call
        # would be a change nobody argued for here; a first or second
        # missing is the bug this file exists to catch.
        self.assertEqual(self.assist_body.count("dronesForTheFleet context"), 2)

    def test_the_existing_gates_are_untouched(self):
        # assistFleetCommander, the drones window, and the commander name are
        # still what this arm is conditioned on -- the fix reuses the arm's
        # own gating rather than adding a second, differently-gated call site.
        self.assertIn("context.eventContext.botSettings.assistFleetCommander /= PromptParser.Yes",
                       self.assist_body)
        self.assertIn(
            "( context.readingFromGameClient.dronesWindow, fleetCommanderName context )",
            self.assist_body)

    def test_the_idling_branch_still_redirects_rather_than_relaunches(self):
        # The `else` arm -- idling drones present -- must still be the
        # Assist/Engage-Target cascade, untouched by this change.
        self.assertIn("'Assist' if present, else 'Engage Target'", self.assist_body)

    def test_dronesForTheFleet_names_its_only_caller_in_its_own_doc_comment(self):
        # The stale "Assist first, `F` second" doc this function carried
        # since the original skeleton described a cascade choice it never
        # implemented -- that choice lives in `dronesAssistTheCommander`'s
        # own `MenuEntryWithCustomChoice` now. A reader editing this function
        # without reading `dronesAssistTheCommander` first should be told
        # where it's called from.
        declaration_and_doc = self.source[
            :self.source.index("dronesForTheFleet :")]
        doc_start = declaration_and_doc.rindex("{-|")
        doc_comment = declaration_and_doc[doc_start:]
        self.assertIn("dronesAssistTheCommander", doc_comment)


class TheModuleStillCompilesTest(unittest.TestCase):
    """Executed, not assumed: a full recompile of the real `Bot.elm`."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_functions_keep_their_type(self):
        for name in ("dronesForTheFleet", "dronesAssistTheCommander"):
            with self.subTest(name):
                definitions = [
                    "check : BotDecisionContext -> Maybe "
                    "EveOnline.BotFrameworkSeparatingMemory.DecisionPathNode",
                    "check = %s" % name,
                ]
                self.assertEqual(
                    self.repl.evaluate(["True"], definitions=definitions),
                    [True])


if __name__ == "__main__":
    unittest.main()
