"""Tests for #303: a locked wreck was held, never unlocked.

Run 50 (`~/eve-bot-logs/saxrat_run50.log`) held a wreck locked and active for
39 unbroken ticks (154s) with rats on the same grid, because the two guards on
this path read different sources and only one of them fired:

- `activeTargetOverviewEntryIsStray` reads the **overview row** for whatever
  target is currently active. It fired on every one of the 77 ticks a wreck
  was active that run, and what it drives is "hold fire" -- it never frees
  the lock slot.
- `targetsToUnlockFromReadingFromGameClient` reads the **target bar's own
  text**. It fired on none of those readings, so the unlock branch it feeds
  was never reached. Nothing else frees the slot; a wreck cannot die, so
  nothing ends the episode but the wreck despawning.

The fix, `targetsToUnlockIncludingActiveIfStray`, is a union rather than a
replacement: the bar-text match stays the primary source (it can name a
non-active locked target the overview check never looks at), and the active
target is added as a candidate whenever the overview says it is stray. One
definition is read at both the decision site that clicks the unlock and the
memory update that drives the settling-window guard in front of that click --
see that function's own doc comment for why a second copy of this list would
have made the fix compile and never actually fire.

The cases run the real `Bot.elm` through `elm repl`, over readings built by
running a real UI tree through the real `EveOnline.ParseUserInterface` --
`Sunder Alvi` / `Gallente Small Wreck` is the same Name/Type split
`test_saxrat_wrecker_is_not_a_wreck.py`'s own `A_WRECK` fixture uses, since a
wreck's Name is its dead owner's and the Type column is what carries the word.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import unittest

from prerequisites import open_repl
from test_saxrat_ported_guards import SaxratRepl, body_of, label, node, source_of
from test_target_hitpoints import target

SAXRAT_BOT_ELM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..",
    "implement", "applications", "eve-online", "eve-online-saxrat", "Bot.elm")
SAXRAT_BOT_ELM = os.path.normpath(SAXRAT_BOT_ELM)

# Name/Type as the wrecker test's own A_WRECK fixture uses them: a wreck's
# Name is its dead owner's, and the Type column is what carries the word.
WRECK_DISTANCE = "1,500 m"
WRECK_PILOT_NAME = "Sunder Alvi"
WRECK_TYPE = "Gallente Small Wreck"

A_PLAIN_RAT = ("8,000 m", "Centii Ravener", "Centii Ravener")


def overview_with_active(rows):
    """Like `test_saxrat_ported_guards.overview`, but a row can also carry
    `myActiveTargetIndicator` under a `SpaceObjectIcon` child -- which is
    what `overviewEntryIsActiveTarget` (and so `activeTargetOverviewEntryIsStray`)
    actually reads, per `ParseUserInterface.elm`'s own
    `namesUnderSpaceObjectIcon`. `rows` is `(distance, name, type, is_active)`.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (distance, name, object_type, is_active) in enumerate(rows):
        y = 20 + index * 20
        icon_children = (
            [node("Sprite", {"_name": "myActiveTargetIndicator"},
                  region=(0, y, 16, 16))]
            if is_active else [])
        space_object_icon = node(
            "SpaceObjectIcon", {}, icon_children, region=(0, y, 16, 16))
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            space_object_icon,
            label(distance, (10, y, 50, 16)),
            label(name, (110, y, 150, 16)),
            label(object_type, (310, y, 150, 16)),
        ], region=(0, y, 500, 16)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


class StrayUnlockRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, with the functions under test reachable."""

    HELPERS = [
        "unlockNamesOf = \\parsed -> parsed"
        " |> Maybe.map (\\r -> targetsToUnlockFromReadingFromGameClient r"
        "   |> List.concatMap .textsTopToBottom |> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
        "combinedUnlockNamesOf = \\parsed -> parsed"
        " |> Maybe.map (\\r -> targetsToUnlockIncludingActiveIfStray r"
        "   |> List.concatMap .textsTopToBottom |> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
        "strayOf = \\parsed -> parsed"
        " |> Maybe.map activeTargetOverviewEntryIsStray"
        " |> Maybe.withDefault False",
        "targetNamesOf = \\parsed -> parsed"
        " |> Maybe.map (.targets"
        "   >> List.concatMap .textsTopToBottom >> String.join \",\")"
        " |> Maybe.withDefault \"NO READING\"",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class TheHeldWreckIsNowUnlockedTest(unittest.TestCase):
    """Run 50's own shape: bar-text finds nothing, the overview says stray."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(StrayUnlockRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def _reading_for(self, overview_rows, target_names):
        children = [overview_with_active(overview_rows)] + [
            target(name, [], active=True) for name in target_names]
        return self.repl.reading_binding("reading", children)

    def test_the_fixture_reaches_the_parser(self):
        """A case over a reading that never arrived proves nothing (#174)."""
        binding = self._reading_for(
            [(WRECK_DISTANCE, WRECK_PILOT_NAME, WRECK_TYPE, True)],
            [WRECK_PILOT_NAME])
        seen = self.repl.strings(
            ["targetNamesOf reading"], definitions=self.repl.with_helpers([binding]))
        self.assertIn(WRECK_PILOT_NAME, seen[0])

    def test_the_overview_reports_this_active_target_as_stray(self):
        """Sanity check the fixture actually represents the failure mode."""
        binding = self._reading_for(
            [(WRECK_DISTANCE, WRECK_PILOT_NAME, WRECK_TYPE, True)],
            [WRECK_PILOT_NAME])
        stray = self.repl.evaluate(
            ["strayOf reading"], definitions=self.repl.with_helpers([binding]))
        self.assertEqual(stray, [True])

    def test_bar_text_alone_finds_nothing_for_the_pilot_name(self):
        """The precondition for the bug: the bar's own text (the dead
        pilot's name) contains neither "container" nor "wreck"."""
        binding = self._reading_for(
            [(WRECK_DISTANCE, WRECK_PILOT_NAME, WRECK_TYPE, True)],
            [WRECK_PILOT_NAME])
        unlocked = self.repl.strings(
            ["unlockNamesOf reading"], definitions=self.repl.with_helpers([binding]))
        self.assertEqual(unlocked, [""])

    def test_the_combined_function_unlocks_it_via_the_overview_side(self):
        """The fix: run 50's own shape now finds a candidate to unlock."""
        binding = self._reading_for(
            [(WRECK_DISTANCE, WRECK_PILOT_NAME, WRECK_TYPE, True)],
            [WRECK_PILOT_NAME])
        combined = self.repl.strings(
            ["combinedUnlockNamesOf reading"],
            definitions=self.repl.with_helpers([binding]))
        self.assertIn(WRECK_PILOT_NAME, combined[0])

    def test_a_plain_rat_is_not_spuriously_unlocked(self):
        """Control: nothing stray in the overview, nothing wreck-worded in
        the bar -- the union must not manufacture an unlock candidate."""
        rat_distance, rat_name, rat_type = A_PLAIN_RAT
        binding = self._reading_for(
            [(rat_distance, rat_name, rat_type, True)], [rat_name])
        combined = self.repl.strings(
            ["combinedUnlockNamesOf reading"],
            definitions=self.repl.with_helpers([binding]))
        self.assertEqual(combined, [""])

    def test_a_container_the_bar_already_caught_still_works(self):
        """Regression control: the original bar-text path is unchanged when
        it already finds something, with no stray overview row at all."""
        binding = self._reading_for([], ["Cargo Container"])
        combined = self.repl.strings(
            ["combinedUnlockNamesOf reading"],
            definitions=self.repl.with_helpers([binding]))
        self.assertIn("Cargo Container", combined[0])


class TheSharedDefinitionIsReadEverywhereTest(unittest.TestCase):
    """Source-pinned: the settling-window guard, the click site and the
    "is there still something to do here" guard all have to read the same
    list, or the fix compiles and never actually fires -- see
    `targetsToUnlockIncludingActiveIfStray`'s own doc comment for the
    mechanism (a target found only through the overview-stray half has no
    bar-text region for the settling counter to track, so a narrower read at
    that one site pins it at `Nothing` forever)."""

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)

    @staticmethod
    def _code_only(body):
        """Strips `--` line comments, so a prose mention of the function's
        name (in a comment explaining *why*) cannot satisfy a check for
        actual code calling it. Mutating the real call back to the narrower
        function while leaving an explanatory comment untouched is exactly
        the failure this is for -- it was caught writing these cases."""
        return "\n".join(
            line.split("--", 1)[0] for line in body.splitlines())

    def test_the_decision_site_reads_the_combined_list(self):
        body = self._code_only(body_of(self.source, "decideActionInAnomaly"))
        self.assertIn("targetsToUnlockIncludingActiveIfStray", body)

    def test_the_settling_counter_reads_the_combined_list(self):
        body = self._code_only(
            body_of(self.source, "updateMemoryForNewReadingFromGame"))
        self.assertIn(
            "targetsToUnlockIncludingActiveIfStray", body,
            "currentTargetToUnlockRegion must not read the narrower "
            "targetsToUnlockFromReadingFromGameClient on its own, or the "
            "settling guard in front of the unlock click never advances "
            "for a target the overview-stray half found")

    def test_the_still_something_to_do_guard_reads_the_combined_list(self):
        body = self._code_only(
            body_of(self.source, "gridStillHasSomethingToDo"))
        self.assertIn("targetsToUnlockIncludingActiveIfStray", body)

    def test_the_combined_function_still_prefers_bar_text_first(self):
        """The bar-text match stays the primary source -- it is what can
        name a non-active locked target the overview check never looks at."""
        body = body_of(self.source, "targetsToUnlockIncludingActiveIfStray")
        self.assertLess(
            body.index("targetsToUnlockFromReadingFromGameClient"),
            body.index("activeTargetOverviewEntryIsStray"),
            "the bar-text match should be listed before the overview "
            "fallback in the union")


if __name__ == "__main__":
    unittest.main()
