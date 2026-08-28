"""Tests for the wingman refusing to shoot the fleet it is flying with.

The incident (#367): in `wingman_run9.log` this bot fired `Small Focused Beam
Laser II` at `Sonya Spodumain[MNRLG](Imperial Navy Slicer)` -- a real player,
named twice by this bot's own "other pilots" line -- across two clusters of
hits, penetrations and grazes about thirty seconds each.

Three separate defects had to line up, and there is a case here for each.

**The trigger asked nothing about who was locked.** `weaponsStep` reads
`targetLocked` and three other facts, none of them a name. The one fleet check
in the file guarded the *lock*, on the broadcast path only, and two other paths
put a target in the bar without passing it: `fightRatsIfShipIsPointed`
ctrl-clicks whoever is pointing this ship, and a hand-locked target was never
asked about at all.

**Nothing ever unlocked a fleet member.** The cascade existed as a sketch
inside `decideActionInAnomaly`, which nothing on the live decision path calls.

**And the membership list could be empty without anything saying so.**
`fleetMemberNames` reads the Fleet window, which answers `[]` when the window
is shut -- and `List.member` over `[]` is `False` for everybody, so a guard
that stopped there would pass every target through while reading in the log
exactly like a guard that had checked. That is the case this file cares about
most: `test_an_empty_membership_list_is_not_a_clean_bill_of_health` and its
neighbours.

The cases run the real `Bot.elm` through `elm repl`. Nothing here reads a live
client, the recorded corpus, or a running bot.

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

from prerequisites import ElmRepl, elm_json_literal, open_repl  # noqa: E402

WINGMAN_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-wingman")
WINGMAN_BOT_ELM = os.path.join(WINGMAN_DIR, "Bot.elm")

# The pilot run 9 shot, and the fleet she was not in. Quoted from that log:
# the combat lines name her `Sonya Spodumain[MNRLG](Imperial Navy Slicer)` and
# the bot's own overview line names her `Sonya Spodumain`.
SONYA = "Sonya Spodumain"
COMMANDER = "Gal Bistot"
# A member row and the header labels, from the fleet window capture WINGMAN.md
# records off Gal Bistot's live client: `FleetHeader (label) 'Fleet (5)' /
# 'Gal Bistot'`, with `Greta Gneiss` a `FleetMember` row -- four rows against
# `Fleet (5)` because the boss is drawn in the header instead. The two structure
# labels are the rest of what `fleetCommanderNameFromFleetWindowHeader`'s own
# comment records, and are what its "the name is the label without a
# parenthesis" rule has to sort past.
MEMBER_ROW = "Greta Gneiss"
HEADER_LABELS = ["Fleet (5)", COMMANDER, "Squad 1 (4)", "Wing 1 (4)"]

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

_address = iter(range(100000, 999999))


def node(type_name, entries=None, children=(), region=None):
    """One UI tree node in the shape `decodeMemoryReadingFromString` wants."""
    dict_entries = dict(entries or {})
    if region is not None:
        x, y, width, height = region
        dict_entries.update({
            "_displayX": x, "_displayY": y,
            "_displayWidth": width, "_displayHeight": height,
        })
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": type_name,
        "dictEntriesOfInterest": dict_entries,
        "children": list(children),
    }


def label(text, region, name="label"):
    return node("EveLabelMedium", {"_name": name, "_setText": text},
                region=region)


def fleet_window(header_labels, member_rows):
    """A `FleetWindow` the real parser will accept.

    `fleetCommanderNameFromFleetWindowHeader` looks for a descendant whose
    type name contains `FleetHeader` and reads the display texts *below* it,
    so the labels are that node's children rather than the node itself.
    `fleetMemberNames` wants `_name = "entryLabel"` anywhere in the window.
    """
    header = node("FleetHeaderContainer", {}, [
        label(text, (10, 10 + index * 16, 200, 16))
        for index, text in enumerate(header_labels)
    ], region=(0, 0, 300, 80))

    rows = [
        node("FleetMember", {}, [
            label(row, (10, 100 + index * 20, 200, 16), name="entryLabel"),
        ], region=(0, 100 + index * 20, 300, 20))
        for index, row in enumerate(member_rows)]

    return node("FleetWindow", {}, [header] + rows, region=(0, 0, 300, 400))


def tree_with(children):
    return node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def reading_binding(name, children):
    """A `let`-free binding of `name` to a real parsed reading.

    Goes through `decodeMemoryReadingFromString` and the real
    `parseUserInterfaceFromUITree`, so what the cases assert on is what the bot
    would have been handed. The literal comes from `elm_json_literal` rather
    than a triple-quoted string: getting that wrong is not a broken fixture but
    a case that passes having asserted against a reading that never arrived.
    """
    return "%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s" \
           " |> Result.toMaybe" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUITreeWithDisplayRegionFromUITree" \
           " |> Maybe.map EveOnline.ParseUserInterface" \
           ".parseUserInterfaceFromUITree" % (
               name, elm_json_literal(tree_with(children)))


FLEET_OPEN = reading_binding(
    "fleetOpen", [fleet_window(HEADER_LABELS, [MEMBER_ROW])])
FLEET_SHUT = reading_binding("fleetShut", [])


def elm_strings(values):
    return "[ %s ]" % ", ".join('"%s"' % value for value in values)


def elm_string_lists(values):
    return "[ %s ]" % ", ".join(elm_strings(value) for value in values)


def friendly_fire_step(locked, fleet, verifiable, others, asked=0):
    """The shipped rule, as one expression over five plain facts."""
    return ("friendlyFireStep { lockedTargetTexts = %s, fleetPilots = %s"
            ", membershipIsVerifiable = %s, otherPilotsOnOverview = %s"
            ", askedReadings = %s }"
            % (elm_string_lists(locked), elm_strings(fleet),
               verifiable, elm_strings(others), asked))


# The target bar decorates a name with distance and hull, which is why the
# matcher contains rather than equals.
SONYA_LOCKED = [[SONYA + " [MNRLG]", "13 km", "Imperial Navy Slicer"]]
RAT_LOCKED = [["Centior Monster", "8 km"]]


class WingmanRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "wingman-friendly-fire-repl-")
        kwargs.setdefault("app_dir", WINGMAN_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


class TheFriendlyFireRuleTest(unittest.TestCase):
    """`friendlyFireStep` executed, rather than restated in Python."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_empty_lock_bar_is_the_only_thing_that_needs_no_opinion(self):
        self.assertEqual(
            self.repl.evaluate([
                "%s == NothingIsLocked"
                % friendly_fire_step([], [COMMANDER], "True", [])]),
            [True])

    def test_a_locked_fleet_pilot_is_unlocked_and_named(self):
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s"'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "True", []),
                   SONYA)]),
            [True])

    def test_the_commander_counts_as_a_fleet_pilot(self):
        """`Fleet (5)` beside four member rows: the boss is in the header, and
        is the one pilot it matters most not to shoot."""
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s"'
                % (friendly_fire_step([[COMMANDER, "4 km"]],
                                      [MEMBER_ROW, COMMANDER], "True", []),
                   COMMANDER)]),
            [True])

    def test_the_name_is_matched_inside_the_target_bar_s_decoration(self):
        """The bar carries hull and distance beside the name, so the match
        contains rather than equals -- and it is `lockedTargetNamed`'s own
        matcher, not a second one that could disagree with it."""
        self.assertEqual(
            self.repl.evaluate([
                'targetTextsCarryName "%s" %s' % (
                    SONYA, elm_strings(SONYA_LOCKED[0])),
                'targetTextsCarryName "%s" %s' % (
                    SONYA, elm_strings(RAT_LOCKED[0]))]),
            [True, False])

    def test_a_stranger_is_shot_once_membership_really_was_checked(self):
        """The other half of the guard: with the Fleet window open, an empty
        member list is a real answer and a non-member is a legitimate target.
        Without this the fix would be "never fire", which is not a fix."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ClearToFire"
                % friendly_fire_step(SONYA_LOCKED, [MEMBER_ROW], "True",
                                     [SONYA])]),
            [True])

    def test_an_empty_membership_list_is_not_a_clean_bill_of_health(self):
        """#367's central point. `fleetMemberNames` answers `[]` for a fleet of
        forty whose window is shut exactly as it does for a pilot flying alone,
        and `List.member` over `[]` is `False` for everybody -- so a guard that
        stopped at the list would pass Sonya through and leave a log
        indistinguishable from one where the check had run.

        Both readings below hand the rule an empty `fleetPilots`. The only
        difference is whether the membership source could be read at all, and
        the answers must differ.
        """
        self.assertEqual(
            self.repl.evaluate([
                '%s == HoldFireOnAnUnverifiedPilot "%s"'
                % (friendly_fire_step(SONYA_LOCKED, [], "False", [SONYA]),
                   SONYA),
                "%s == ClearToFire"
                % friendly_fire_step(SONYA_LOCKED, [], "True", [SONYA])]),
            [True, True])

    def test_an_unverifiable_fleet_still_shoots_rats(self):
        """PvE is untouched by the refusal above. An NPC is never in
        `getNamesOfOtherPilotsInOverview`, which is built from local chat's
        user list, so a rat locked with the Fleet window shut is still shot."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ClearToFire"
                % friendly_fire_step(RAT_LOCKED, [], "False", [SONYA])]),
            [True])

    def test_a_known_fleetmate_outranks_the_unverifiable_case(self):
        """A name that is on the membership list is unlocked rather than merely
        held, whether or not the list is complete -- positive evidence is
        usable even when the source cannot certify itself."""
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s"'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "False", [SONYA]),
                   SONYA)]),
            [True])

    def test_the_unlock_ask_gives_up_at_the_bound(self):
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s"'
                % (friendly_fire_step(
                    SONYA_LOCKED, [SONYA], "True", [],
                    "unlockFleetPilotAskedReadingsBound - 1"), SONYA),
                '%s == GaveUpUnlockingAFleetPilot "%s"'
                % (friendly_fire_step(
                    SONYA_LOCKED, [SONYA], "True", [],
                    "unlockFleetPilotAskedReadingsBound"), SONYA),
                "unlockFleetPilotAskedReadingsBound == 20"]),
            [True, True, True])

    def test_giving_up_on_the_unlock_does_not_release_the_guns(self):
        """Every other give-up in this file hands the reading back. This one
        must not: a context menu that will not open is no reason at all to
        start shooting the pilot it would have unlocked."""
        self.assertEqual(
            self.repl.evaluate([
                "friendlyFireVetoesTheGuns (%s)"
                % friendly_fire_step(
                    SONYA_LOCKED, [SONYA], "True", [],
                    "unlockFleetPilotAskedReadingsBound + 500")]),
            [True])

    def test_exactly_the_three_refusing_answers_hold_the_trigger(self):
        """Read together with the source pins below: this is the predicate
        every firing arm consults, so an answer wrongly on either side of it
        is either a friendly shot or a bot that never fires."""
        self.assertEqual(
            self.repl.evaluate([
                "friendlyFireVetoesTheGuns NothingIsLocked",
                "friendlyFireVetoesTheGuns ClearToFire",
                'friendlyFireVetoesTheGuns (UnlockAFleetPilot "x")',
                'friendlyFireVetoesTheGuns (GaveUpUnlockingAFleetPilot "x")',
                'friendlyFireVetoesTheGuns (HoldFireOnAnUnverifiedPilot "x")']),
            [False, False, True, True, True])


class TheMembershipSourceIsReadTest(unittest.TestCase):
    """The two readings the whole distinction rests on, through the parser."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_fixtures_reach_the_parser(self):
        """A tree the parser makes nothing of answers every question below the
        same way an absent rule would, so the fixtures are checked first."""
        self.assertEqual(
            self.repl.evaluate(
                ["(fleetOpen |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(fleetShut |> Maybe.andThen .fleetWindow) == Nothing"],
                definitions=[FLEET_OPEN, FLEET_SHUT]),
            [True, True])

    def test_a_shut_fleet_window_is_not_an_empty_fleet(self):
        """The two facts side by side: the member list is empty either way,
        and only `fleetMembershipIsVerifiable` tells the readings apart."""
        self.assertEqual(
            self.repl.evaluate(
                ["(fleetShut |> Maybe.map fleetMemberNames"
                 " |> Maybe.withDefault []) == []",
                 "(fleetShut |> Maybe.map fleetMembershipIsVerifiable"
                 " |> Maybe.withDefault True) == False",
                 "(fleetOpen |> Maybe.map fleetMembershipIsVerifiable"
                 " |> Maybe.withDefault False) == True"],
                definitions=[FLEET_OPEN, FLEET_SHUT]),
            [True, True, True])

    def test_the_open_window_names_its_rows_and_its_boss(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(fleetOpen |> Maybe.map fleetMemberNames'
                 ' |> Maybe.withDefault []) == [ "%s" ]' % MEMBER_ROW,
                 '(fleetOpen |> Maybe.andThen'
                 ' fleetCommanderNameFromFleetWindowHeader)'
                 ' == Just "%s"' % COMMANDER],
                definitions=[FLEET_OPEN]),
            [True, True])

    def test_the_header_outranks_the_setting_and_the_setting_is_the_floor(self):
        """#367's unification, and the defect #369 flagged with it: the retreat
        used to run to the setting alone and answered `Nothing` when it was
        unset -- a break-off decided with nowhere to go. An open fleet window
        now answers it whatever the operator configured, and a shut one still
        falls back to the pilot they said they trust."""
        self.assertEqual(
            self.repl.evaluate(
                ['(fleetOpen |> Maybe.andThen'
                 ' (fleetCommanderNameFromReading [ "Someone Else" ]))'
                 ' == Just "%s"' % COMMANDER,
                 '(fleetShut |> Maybe.andThen'
                 ' (fleetCommanderNameFromReading [ "Someone Else" ]))'
                 ' == Just "Someone Else"',
                 "(fleetShut |> Maybe.andThen"
                 " (fleetCommanderNameFromReading [])) == Nothing"],
                definitions=[FLEET_OPEN, FLEET_SHUT]),
            [True, True, True])

    def test_the_pilots_not_to_shoot_carry_the_commander_with_them(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(fleetOpen |> Maybe.map (fleetPilotNamesFromReading [])'
                 ' |> Maybe.withDefault []) == [ "%s", "%s" ]'
                 % (MEMBER_ROW, COMMANDER)],
                definitions=[FLEET_OPEN]),
            [True])

    def test_an_empty_name_cannot_enter_the_no_shoot_list(self):
        """The matcher contains rather than equals, so `""` would answer "that
        is a fleetmate" for every target in the bar -- and then nothing would
        ever fire, which is the failure mode that looks like safety."""
        self.assertEqual(
            self.repl.evaluate(
                ['(fleetShut |> Maybe.map'
                 ' (fleetPilotNamesFromReading [ "", "  " ])'
                 ' |> Maybe.withDefault [ "x" ]) == []'],
                definitions=[FLEET_SHUT]),
            [True])


def wingman_root_body(source):
    """Both halves of the in-space decision root, spliced in source order.

    #378 split it: `wingmanDecisionRootInSpace` keeps only the arms that take
    the ship off the grid -- the session wind-down, the retreat, the recovery
    -- and hands every other arm, the unlock included, to
    `wingmanDecisionRootInSpaceOrdinary`.
    """
    root = source[source.index("wingmanDecisionRootInSpace context shipUI ="):]
    ordinary = root[root.index(
        "wingmanDecisionRootInSpaceOrdinary context shipUI ="):]
    return (root[:root.index("\n\n\n")] + "\n"
            + ordinary[:ordinary.index("\n\n\n")])


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


class TheGuardsAreOnEveryFiringPathTest(unittest.TestCase):
    """Source-pinned, because reachability is a shape and not a value.

    Every slice below is bounded to one declaration. An assertion over the
    whole file would match the same words in a status string and pass against
    a deleted rule, which is the hole this repo has found in its own suite
    before.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def declaration(self, name):
        match = re.search(
            r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), self.source,
            re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match, "no declaration named %r" % name)
        return match.group(0)

    def test_the_trigger_refuses_on_its_own_and_not_via_the_lock(self):
        """#367's first requirement. `fireOnActiveTarget` is the arm that shot
        Sonya, and it reached her through a lock the one existing fleet check
        never saw.

        Re-expressed for #389, which made the veto an answer of `weaponsStep`
        rather than a condition wrapped around it -- the counter is advanced
        from that rule, and a refusal the rule cannot see is a reading charged
        to a budget nobody spent. The property is unchanged and is now checked
        along the path the arm actually takes: the arm asks the rule, and the
        rule asks the guard.
        """
        arm = self.declaration("fireOnActiveTarget")
        self.assertIn("weaponsStepFromContext context", arm)
        self.assertIn("FriendlyFireHoldsTheTrigger ->", arm)
        rule = self.declaration("weaponsStepFromReading")
        self.assertIn("friendlyFireVetoesTheGuns", rule)
        self.assertIn("friendlyFireHoldsTheTrigger", self.declaration(
            "weaponsStep"))

    def test_the_self_defense_trigger_refuses_too(self):
        """The other arm that activates modules, and the one whose lock is made
        by ctrl-clicking a buff button that names nobody."""
        body = self.declaration("fightPointedRatsOrReturnDrones")
        self.assertIn("friendlyFireVetoesTheGuns", body)
        self.assertIn("fightRatsIfShipIsPointed", body)

    def test_the_unlock_arm_takes_the_client_s_own_unlock_entry(self):
        """The primitive existed only inside `decideActionInAnomaly`, which
        nothing on the live decision path calls. This is it, reachable."""
        body = collapsed(self.declaration("unlockFleetPilotInTargetBar"))
        self.assertIn('useMenuEntryWithTextContaining "unlock"', body)
        self.assertIn("barAndImageCont", body)
        self.assertIn("lockedTargetNamed", body)

    def test_the_unlock_arm_sits_above_everything_that_wants_the_reading(self):
        """Each arm below answers `Just` for the whole of a fight -- the
        broadcast banner does not clear (#360), the drone arm answers on every
        idle drone (#326), the guns on every silent weapon. An unlock under any
        of them is reachable only on the readings nothing is happening.

        The three arms allowed above it all end with the ship leaving, which
        settles an engagement more thoroughly than an unlock does: the session
        wind-down, #364's retreat, and #378's recovery flight back.
        """
        arms = re.findall(r"case (\w+) context", wingman_root_body(self.source))
        self.assertEqual(
            arms[:4],
            ["sessionIsEnding", "retreatToTheCommander", "recoverFromRetreat",
             "unlockFleetPilotInTargetBar"])
        for below in ["activateAlwaysOnModules", "actOnFleetBroadcast",
                      "dronesAssistTheCommander", "fireOnActiveTarget",
                      "accelerationGateStep"]:
            self.assertGreater(arms.index(below), 3, below)

    def test_the_unlock_counter_is_advanced_by_the_shipped_rule(self):
        """#102: a counter advanced by one condition and read by another is two
        rules on two schedules. The memory update asks `friendlyFireStep`
        itself rather than restating when an ask goes out."""
        update = self.source[self.source.index(
            "updateMemoryForNewReadingFromGame context botMemoryBefore ="):]
        update = update[:update.index(
            "\n\n\n{-| The values this gauge is allowed to have at all.")]
        self.assertIn("friendlyFireStepFromReading", update)
        self.assertIn("unlockFleetPilotAskedReadings + 1", update)

    def test_the_membership_source_is_named_every_reading(self):
        """The half of #367 that is about the log rather than the trigger:
        run 9 carried no line at all about the fleet, so nothing could
        distinguish "nobody qualified" from "there was nothing to check"."""
        status = self.declaration("statusTextFromState")
        self.assertIn("describeFleetMembership context", status)
        self.assertIn("describeFriendlyFireGuard context", status)

        membership = self.declaration("describeFleetMembership")
        self.assertIn("THE FLEET WINDOW IS NOT OPEN", membership)
        self.assertIn("the Fleet window is open and lists ", membership)
        self.assertIn("fleetCommanderNameFromFleetWindowHeader", membership)
        self.assertIn("fleetmateNamesFromLocalChat", membership)

    def test_the_give_up_and_the_hold_are_both_visible(self):
        """Both leave the decision tree looking like a bot with nothing to do,
        which is how a silent refusal becomes a mystery a run later."""
        guard = self.declaration("describeFriendlyFireGuard")
        self.assertIn("GAVE UP unlocking ", guard)
        self.assertIn("HOLDING FIRE on ", guard)
        self.assertIn("UNLOCKING, guns held", guard)


class TheThreeCommanderResolversAreTwoTest(unittest.TestCase):
    """#368 left a case pinning the divergence and asked for it to be deleted
    here. This is what replaces it.

    `fleetCommanderNameFromPanel` is gone; `fleetCommanderName` reads the
    header and falls back to the setting, and
    `fleetCommanderNameFromFleetWindowHeader` stays as the reading-only half
    that `updateMemoryForNewReadingFromGame` needs.
    """

    @classmethod
    def setUpClass(cls):
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    def test_the_panel_sibling_is_gone(self):
        """Its name survives in one doc comment, which is the point -- a reader
        arriving from #365 or #368 has to be able to find where it went."""
        self.assertNotIn("fleetCommanderNameFromPanel :", self.source)
        self.assertNotIn("fleetCommanderNameFromPanel context", self.source)

    def test_every_arm_that_names_a_commander_asks_the_same_question(self):
        """They ran to different resolvers, so a reading where the window and
        the setting disagreed had the arms about different ships.

        #364's retreat was one of the two arms here until #378 took the
        commander out of it: it now warps away from danger and names nobody,
        and the flight back is `recoverFromRetreat`. The property did not go
        with it -- the two arms that still resolve a commander on the decision
        path have to agree, or a ship rejoins one pilot while its drones assist
        another. The retreat is asserted to have left rather than dropped from
        the case, since re-resolving a commander in there is exactly the
        regression #377 measured.

        `fleetCommanderNameFromFleetWindowHeader` is the reading-only half and
        belongs to `updateMemoryForNewReadingFromGame` and the status line.
        A decision arm reaching it directly is the divergence coming back.
        """
        retreat = self.source[self.source.index(
            "\nretreatToTheCommander context"):]
        retreat = retreat[:retreat.index("\n\n\n")]
        recover = self.source[self.source.index(
            "\nrecoverFromRetreat context"):]
        recover = recover[:recover.index("\n\n\n")]
        drones = self.source[self.source.index(
            "dronesAssistTheCommander context ="):]
        drones = drones[:drones.index("\n\n\n")]
        self.assertIn("fleetCommanderName context", recover)
        self.assertIn("fleetCommanderName context", drones)
        self.assertNotIn("fleetCommanderName", retreat)
        for arm in [recover, drones]:
            self.assertNotIn("fleetCommanderNameFromFleetWindowHeader", arm)


if __name__ == "__main__":
    unittest.main()
