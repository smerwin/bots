"""Tests for `hide-when-neutral-in-local`'s exit, in `eve-online-saxrat`.

Written live, alongside a hotpatch, while a session was flying this bot
through Providence null-sec for the first time. `hide-when-neutral-in-local`'s
in-space response was `dockAtRandomStationOrStructure` -- a search for a
station or player structure that can fail, take a long time, or point at
something that is not friendly, none of which a ship that has just spotted a
neutral in local can afford. It now calls `runAway`, the same celestial-warp
exit the health guards take, and then -- once off that grid -- `jumpToNextSystem`,
the same "leave this system" travel the hunt circuit already uses when there is
nothing left to hunt. Both were already tested and proven; what is new is the
sequencing between them and the memory that makes it survive across however
many hops leaving takes.

**Why a bare `runAway` was not the whole answer.** It rotates among whatever the
overview shows at AU range, `runAwayCelestialStickyReadings` readings at a
time, and nothing in it ever leaves the system -- a ship that only changes
which rock it orbits is still standing in the same local chat the neutral is
in. **Why a bare `jumpToNextSystem` was not either.** Reached with no route yet
set, its first move is to ask the host for one and wait -- exactly the readings
this setting exists to react to fastest, with the ship sitting still and
exposed on whatever grid it was already on.

**The transition is latched rather than re-derived each reading**, because a
decision cannot write memory (`updateMemoryForNewReadingFromGame` is the only
place that can) and "has this hide episode already gotten the ship moving"
has to survive across however many readings and however many jumps leaving
takes. `hidingFromNeutralPastFirstHop` is set the first reading the ship is
seen warping *or jumping* while `neutralOrHostileInLocal` answers `Just True`
-- covering both a celestial warp `runAway` just issued and a gate jump
`jumpToNextSystem` has already put the ship on the far side of, so a second
neutral met after the first jump does not fall back to a pointless celestial
hop before continuing on -- and cleared the moment that answer stops being
`Just True`, so the next hide episode starts fresh.

`neutralOrHostileInLocal` is the same question `continueIfShouldHide` asked
inline before this change, pulled out so the memory update can ask it too
without a second copy to drift from the first. The `>1` threshold in the
client's own local chat (not this file's invention, unchanged) accounts for
the pilot's own entry, which carries no standing hint either -- so a system
with nobody but this ship reads as one person with no good standing, and it
takes a second one to mean a stranger.

These cases execute the real declarations through `elm repl` rather than
restating them in Python, and where a rule takes a `ReadingFromGameClient` the
reading is built by running a UI tree through the real
`EveOnline.ParseUserInterface`, `test_saxrat_ported_guards.py`'s own
convention -- so a hand-written record cannot drift from what the parser would
actually produce. `chat_user_entry`/`local_chat_window` are
`test_fleetmate_anomaly_avoidance.py`'s, reused rather than rebuilt; `flying`
and the two captured indications are `test_arrival_pilot_window.py`'s, off the
same live-captured shape #194 used.

**Unverified: any of it running.** Written and compiled before a live run met
it -- Providence entry is Sansha Nation null-sec and the whole point of arming
this was to see it for the first time there. What to watch on the first
session that meets a neutral in null: the decision log naming which of the
three states it is in ("already warping or jumping", "off the grid ... keep
moving", or `runAway`'s own "Get out -- select ..."), and -- the thing this
file cannot exercise without a live route -- that a second neutral met after
the first jump goes straight to `jumpToNextSystem` rather than detouring
through another celestial first.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import REPO_DIR, open_repl
from test_arrival_pilot_window import LANDED_INDICATION, WARPING_INDICATION, flying
from test_fleetmate_anomaly_avoidance import chat_user_entry, local_chat_window
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, overview, source_of)

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")

# The client's own list, quoted from `Bot.elm` rather than assumed -- a case
# below is what goes red if this drifts from the source.
GOOD_STANDING_HINTS = ["good standing", "excellent standing", "is in your"]

FAR_CELESTIAL = ("60.0 AU", "Some Moon", "Moon")


class HideThenTravelRepl(SaxratRepl):
    """saxrat's own `Bot.elm`, plus what asking these three questions costs.

    `neutralOrHostileInLocal` and `hideFromNeutralInLocal` are functions of a
    `ReadingFromGameClient` / `BotDecisionContext` respectively, not of a plain
    record, so a case cannot ask them anything without a full context --
    `test_saxrat_approach_by_double_click.ApproachRepl`'s own reasoning, same
    shape reused. `askContext`/`stepMemory` are `test_saxrat_route_ask_bound.py`'s
    fold, reused for the same reason: a latch's correctness is a claim about a
    *session*, not a single reading.
    """

    IMPORTS = (
        "import Bot exposing (..)",
        "import EveOnline.MemoryReading",
        "import EveOnline.ParseUserInterface",
        "import Common.AppSettings as AppSettings",
        "import Common.DecisionPath",
    )

    BINDINGS = (
        "hidingOn = { defaultBotSettings | hideWhenNeutralInLocal = AppSettings.Yes }",
        "hidingOff = { defaultBotSettings | hideWhenNeutralInLocal = AppSettings.No }",
        "decisionContext = \\settings -> \\memory -> \\reading ->"
        " reading |> Maybe.map (\\p ->"
        " { eventContext ="
        " { timeInMilliseconds = 0"
        " , botSettings = settings"
        " , sessionTimeLimitInMilliseconds = Nothing }"
        " , readingFromGameClient = p"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , memory = memory"
        " , previousStepsEffects = []"
        " , previousReadingsFromGameClient = []"
        " , readingsWithoutShipUIOrStationWindow = 0"
        " , contextMenuCascadeLevel = 0"
        " , randomIntegers = [] })",
        "unpack = Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf",
        "hideBranchFor = \\settings -> \\memory -> \\reading -> reading"
        " |> decisionContext settings memory"
        " |> Maybe.map (hideFromNeutralInLocal >> unpack >> Tuple.first >> String.join \" | \")"
        " |> Maybe.withDefault \"NO READING\"",
        "neutralDescribed = \\reading -> reading"
        " |> Maybe.andThen neutralOrHostileInLocal"
        " |> Maybe.map"
        " (\\isNeutral -> if isNeutral then \"NEUTRAL\" else \"CLEAR\")"
        " |> Maybe.withDefault \"NO CHAT WINDOW\"",
        "askContext = \\settings -> \\reading -> reading |> Maybe.map (\\r ->"
        " { timeInMilliseconds = 0"
        " , readingFromGameClient = r"
        " , screenshot = { pixels_1x1 = always Nothing, pixels_2x2 = always Nothing }"
        " , previousStepsEffects = []"
        " , botSettings = settings })",
        "stepMemory = \\settings -> \\memory -> \\reading -> reading"
        " |> askContext settings"
        " |> Maybe.map (\\c -> updateMemoryForNewReadingFromGame c memory)"
        " |> Maybe.withDefault memory",
        "boolWord = \\b -> if b then \"T\" else \"F\"",
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-hide-travel-repl-")
        kwargs.setdefault("preamble", self.IMPORTS + self.BINDINGS)
        super().__init__(**kwargs)


def local_chat_reading(name, users):
    return SaxratRepl.reading_binding(
        name, [flying(LANDED_INDICATION), local_chat_window(users)])


class NeutralOrHostileInLocalTest(unittest.TestCase):
    """`neutralOrHostileInLocal`, against readings the real parser produced."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HideThenTravelRepl)

    def test_no_local_chat_window_answers_nothing(self):
        reading = SaxratRepl.reading_binding("noChat", [flying(LANDED_INDICATION)])
        described = self.repl.strings(
            ["neutralDescribed noChat"], definitions=[reading])
        self.assertEqual(described, ["NO CHAT WINDOW"])

    def test_only_the_pilot_reads_as_no_neutral(self):
        reading = local_chat_reading("selfOnly", [chat_user_entry("Gal Bistot")])
        described = self.repl.strings(
            ["neutralDescribed selfOnly"], definitions=[reading])
        self.assertEqual(described, ["CLEAR"])

    def test_a_fleetmate_beside_the_pilot_still_reads_as_no_neutral(self):
        reading = local_chat_reading("selfAndFleet", [
            chat_user_entry("Gal Bistot"),
            chat_user_entry("Fleet Commander", hint="Pilot is in your fleet"),
        ])
        described = self.repl.strings(
            ["neutralDescribed selfAndFleet"], definitions=[reading])
        self.assertEqual(described, ["CLEAR"])

    def test_a_stranger_beside_the_pilot_reads_as_neutral(self):
        reading = local_chat_reading("selfAndStranger", [
            chat_user_entry("Gal Bistot"),
            chat_user_entry("A Stranger"),
        ])
        described = self.repl.strings(
            ["neutralDescribed selfAndStranger"], definitions=[reading])
        self.assertEqual(described, ["NEUTRAL"])

    def test_good_standing_patterns_match_the_source(self):
        # The fixture above used "Pilot is in your fleet", and the source is
        # what says that has to decline: a case that hard-codes the shipped
        # list rather than reading it would still pass with the list retuned.
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM), "goodStandingPatterns"))
        for hint in GOOD_STANDING_HINTS:
            self.assertIn('"%s"' % hint, body)


class HideFromNeutralInLocalDispatchTest(unittest.TestCase):
    """The three-way branch, over readings built for each state in turn."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HideThenTravelRepl)

    def test_warping_waits_rather_than_touching_travel_ui(self):
        reading = SaxratRepl.reading_binding("warping", [flying(WARPING_INDICATION)])
        described = self.repl.strings(
            ["hideBranchFor hidingOn initBotMemory warping"],
            definitions=[reading])[0]
        self.assertIn("already warping or jumping", described)

    def test_landed_with_the_latch_set_goes_to_jump_to_next_system(self):
        # No route, no hunt-system configured: `jumpToNextSystem` falls all the
        # way to `setRouteToNextHuntingGround`'s `NowhereToAskFor`. That deep a
        # chain reached at all, from this call site, is the proof the dispatch
        # went to `jumpToNextSystem` and not to `runAway`.
        reading = SaxratRepl.reading_binding("landedPastHop", [flying(LANDED_INDICATION)])
        definitions = [
            reading,
            "memoryPastHop = { initBotMemory | hidingFromNeutralPastFirstHop = True }",
        ]
        described = self.repl.strings(
            ["hideBranchFor hidingOn memoryPastHop landedPastHop"],
            definitions=definitions)[0]
        self.assertIn("Nothing left to hunt here and no route set", described)
        self.assertIn("Nowhere to ask for", described)

    def test_landed_before_any_hop_flees_to_a_celestial(self):
        reading = SaxratRepl.reading_binding("landedFresh", [
            flying(LANDED_INDICATION),
            overview([FAR_CELESTIAL]),
        ])
        described = self.repl.strings(
            ["hideBranchFor hidingOn initBotMemory landedFresh"],
            definitions=[reading])[0]
        self.assertIn("Get out --", described)
        self.assertNotIn("Nowhere to ask for", described)
        self.assertNotIn("already warping or jumping", described)

    def test_landed_before_any_hop_with_nothing_to_flee_to_falls_to_the_tether(self):
        reading = SaxratRepl.reading_binding("landedBare", [flying(LANDED_INDICATION)])
        described = self.repl.strings(
            ["hideBranchFor hidingOn initBotMemory landedBare"],
            definitions=[reading])[0]
        self.assertIn("nothing at AU range on the overview to warp to", described)


class HidingFromNeutralPastFirstHopLatchTest(unittest.TestCase):
    """The memory latch, folded across a session rather than asked once."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HideThenTravelRepl)

    def test_set_on_warp_held_on_landing_cleared_on_no_neutral(self):
        warping_with_neutral = SaxratRepl.reading_binding(
            "warpingNeutral", [flying(WARPING_INDICATION), local_chat_window([
                chat_user_entry("Gal Bistot"), chat_user_entry("A Stranger")])])
        landed_with_neutral = SaxratRepl.reading_binding(
            "landedNeutral", [flying(LANDED_INDICATION), local_chat_window([
                chat_user_entry("Gal Bistot"), chat_user_entry("A Stranger")])])
        landed_alone = SaxratRepl.reading_binding(
            "landedAlone", [flying(LANDED_INDICATION), local_chat_window([
                chat_user_entry("Gal Bistot")])])

        definitions = [
            warping_with_neutral, landed_with_neutral, landed_alone,
            "afterWarp = stepMemory hidingOn initBotMemory warpingNeutral",
            "afterLanding = stepMemory hidingOn afterWarp landedNeutral",
            "afterClear = stepMemory hidingOn afterLanding landedAlone",
        ]
        word = self.repl.strings(
            ["boolWord afterWarp.hidingFromNeutralPastFirstHop"
             " ++ boolWord afterLanding.hidingFromNeutralPastFirstHop"
             " ++ boolWord afterClear.hidingFromNeutralPastFirstHop"],
            definitions=definitions)[0]
        self.assertEqual(word, "TTF")

    def test_off_entirely_with_the_setting_disabled(self):
        # `hideWhenNeutralInLocal = No`, matching the launcher's own shipped
        # default: a session that never turns this on pays nothing for it and
        # the latch never moves off its initial `False`, however local chat
        # reads.
        warping_with_neutral = SaxratRepl.reading_binding(
            "warpingNeutralOff", [flying(WARPING_INDICATION), local_chat_window([
                chat_user_entry("Gal Bistot"), chat_user_entry("A Stranger")])])
        definitions = [
            warping_with_neutral,
            "afterWarpOff = stepMemory hidingOff initBotMemory warpingNeutralOff",
        ]
        word = self.repl.strings(
            ["boolWord afterWarpOff.hidingFromNeutralPastFirstHop"],
            definitions=definitions)[0]
        self.assertEqual(word, "F")


class WiringTest(unittest.TestCase):
    """What the source says calls what, read rather than executed.

    `hideFromNeutralInLocal`'s three describeBranch strings above already
    prove the *behaviour* of the in-space call site; this pins that the call
    site itself is the one that was edited (not a second copy), and that the
    unrelated pod-recovery call site -- which should keep docking, recovering
    a lost ship's pod being a different problem from fleeing a live one -- was
    not touched by the same edit.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = source_of(SAXRAT_BOT_ELM)
        cls.collapsed = collapsed(cls.source)

    def test_hide_when_neutral_calls_the_new_function(self):
        self.assertIn("{ ifShouldHide = hideFromNeutralInLocal context }", self.collapsed)

    def test_the_old_dock_wiring_is_gone_from_the_hide_call_site(self):
        self.assertNotIn(
            "{ ifShouldHide = returnDronesToBay context "
            "(dockAtRandomStationOrStructure context) }",
            self.collapsed)

    def test_pod_recovery_is_the_only_remaining_dock_call_site(self):
        # `dockAtRandomStationOrStructure`'s own definition header reads
        # "...context =", never "...context)", so this pattern only matches a
        # real call passing `context` as the argument -- and there is exactly
        # one left, in `recoverPodAfterShipLoss`'s pod-recovery branch.
        calls = re.findall(r"dockAtRandomStationOrStructure context\)", self.collapsed)
        self.assertEqual(len(calls), 1,
            "expected exactly one call site (pod recovery); a different count "
            "means either the hide-when-neutral call site is back or pod "
            "recovery lost its own")
        self.assertIn(
            'Pod recovery: docking at whatever this system offers',
            self.collapsed)

    def test_the_latch_field_is_declared(self):
        # `type alias` has no annotation for `body_of` to key on --
        # `test_saxrat_ammo_swap.py`'s own workaround, reused.
        self.assertIn("hidingFromNeutralPastFirstHop : Bool", self.collapsed)

    def test_the_latch_field_is_initialised_and_written(self):
        init = body_of(self.source, "initBotMemory")
        update = body_of(self.source, "updateMemoryForNewReadingFromGame")
        self.assertIn("hidingFromNeutralPastFirstHop = False", collapsed(init))
        self.assertIn(
            "hidingFromNeutralPastFirstHop = hidingFromNeutralPastFirstHopNow",
            collapsed(update))


if __name__ == "__main__":
    unittest.main()
