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

## #390: the guard asked one instrument, and the client defeated it

`friendlyFireStep` decided "is this pilot locked" from the target bar's rendered
labels alone, through `targetTextsCarryName` -- and the bar **wraps a name
across labels**. #303 read `['Tower Sentry', 'Sansha I', '20 km']` off a live
client, and #389 measured the same failure on every reading of four sessions. A
two-word character name -- most of them, `Sonya Spodumain` included -- was
therefore not recognised as locked, the membership branch answered `Nothing`,
and with the Fleet window open that fell through to `ClearToFire`. It failed in
the *firing* direction, which is the one direction #367 exists to prevent.

The rule now asks two instruments and refuses if **either** answers: the bar's
labels, and the named pilot's overview row carrying the client's own
`targetedByMe`. They go quiet in opposite directions -- the bar on a wrapped
name, the row when the pilot has no row on this overview -- so the union is the
only combination that cannot make the guard quieter than it already was. Each
answer carries which instrument saw the pilot, and the status line prints it.

Confirmed by mutation, eleven of them, each failing named cases. The bar-only
and row-only cases are named separately throughout because a mutation that
survives one of them is the guard going quiet on exactly one instrument, which
is the whole subject:

1. `lockSignalForPilot` reduced to the bar (`( False, True ) -> Nothing`),
   which is the shipped defect restored exactly -- eight cases, including
   `test_a_name_the_bar_wraps_is_caught_by_the_overview_row`,
   `test_the_two_signals_are_a_union_and_not_an_intersection`,
   `test_the_unverified_pilot_branch_asks_both_instruments_too`,
   `test_the_guard_holds_fire_on_the_reading_that_used_to_fire`, and
   #389's `test_a_wrapped_name_is_invisible_to_the_target_bar_matcher` in
   `test_wingman_engages_the_called_target`, which is the case that measured
   the failure and now executes it being caught;
2. `lockSignalForPilot` reduced to the row (`( True, False ) -> Nothing`) --
   nine cases, including `test_a_locked_fleet_pilot_is_unlocked_and_named`,
   `test_either_instrument_refuses_and_both_are_reported`, the truth table, and
   `test_the_bar_is_still_a_signal_and_not_leftovers`, which is what keeps the
   bar a decision rather than leftovers on a client that never draws the icon;
3. the union made an intersection -- only `( True, True )` answering `Just` --
   fifteen cases, being (1) and (2) together. This is the mutation the whole
   change is about: `&&` makes the guard *quieter* than either instrument
   alone, which is the one direction a safety rule must not move;
4. `NothingIsLocked` gated on the bar alone --
   `test_a_lock_the_bar_never_rendered_is_still_a_lock` and
   `test_a_row_with_no_bar_parsed_is_not_a_clean_lock_bar`;
5. the row check made "is anything row-locked" rather than "is *this* name" --
   `test_the_row_signal_answers_about_a_named_pilot_and_not_a_lock_count`, the
   case against a guard that never lets the bot fire;
6. the unverifiable-membership branch left on the bar alone --
   `test_the_unverified_pilot_branch_asks_both_instruments_too`;
7. `overviewRowSaysThisShipHasItLocked` reading the neighbouring `.targeting`
   -- three cases in `TheGuardReadsBothInstrumentsTest`, starting with
   `test_the_fixtures_arrived`, plus #389's four in the other file, which share
   the helper;
8. the unlock budget charged on every `UnlockAFleetPilot` again --
   `test_the_unlock_counter_is_advanced_by_the_shipped_rule`;
9. `targetBarSawThePilot` answering `True` for `OverviewRowIndicator`, which is
   the same defect one step earlier --
   `test_the_unlock_budget_is_spent_only_where_there_is_an_entry_to_click`;
10. `friendlyFireStepFromReading` no longer asking the overview
    (`pilotsLockedOnTheOverview = []`) --
    `test_the_rule_is_still_a_function_of_plain_values` and the three executed
    readings, which is the one mutation that leaves the rule itself perfect and
    the bot shipping the old behaviour;
11. the signal dropped from the status line --
    `test_every_refusal_names_the_instrument_that_saw_the_pilot`.

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


def header_labels(fleet_size):
    """The captured header with its stated size varied.

    #380 made that number load-bearing -- `fleetRosterVerdict` compares it
    against the pilots the bot resolved -- so a fixture stating 5 beside one
    member row is a client this bot would (correctly) call short. Every fixture
    below that is meant to read as an ordinary working window therefore states
    the size its own rows and header add up to, which is what the live client
    does: `Fleet (5)` was captured beside **four** rows plus the boss.
    """
    return ["Fleet (%d)" % fleet_size] + HEADER_LABELS[1:]

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


ROW_HEIGHT = 16
ROW_PITCH = 20
ROW_TOP = 20


def overview_window(rows):
    """An overview window whose rows carry the client's own lock indicator.

    Each row is `(name, distance, targeted)`. `targeted` puts a
    `targetedByMeIndicator` under the row's `SpaceObjectIcon`, which is where
    `parseOverviewWindowEntry` reads `commonIndications.targetedByMe` from --
    so what the rules are handed is the icon the client draws rather than a
    boolean this file decided.

    It arrived with #389 in `test_wingman_engages_the_called_target`, which is
    where the called-target arm reads that indicator. #390 put the friendly-fire
    guard on the same indicator, so the builder moved here beside `node`,
    `label` and `fleet_window` rather than being copied into a second file --
    two fixtures for one icon is how two files come to disagree about what the
    client draws.
    """
    headers = node("Headers", {}, [
        label("Distance", (0, 0, 100, 16)),
        label("Name", (100, 0, 200, 16)),
        label("Type", (300, 0, 200, 16)),
    ], region=(0, 0, 500, 16))

    entries = []
    for index, (name, distance, targeted) in enumerate(rows):
        y = ROW_TOP + index * ROW_PITCH
        icon_children = []
        if targeted:
            icon_children.append(
                node("Sprite", {"_name": "targetedByMeIndicator"}))
        entries.append(node("OverviewScrollEntry", {"_name": "overviewEntry"}, [
            label(distance, (10, y, 50, ROW_HEIGHT)),
            label(name, (110, y, 150, ROW_HEIGHT)),
            label(name, (310, y, 150, ROW_HEIGHT)),
            node("SpaceObjectIcon", {}, icon_children,
                 region=(2, y, 12, ROW_HEIGHT)),
        ], region=(0, y, 500, ROW_HEIGHT)))

    return node("OverviewWindow", {}, [
        node("Scroll", {}, [headers] + entries, region=(0, 0, 500, 300)),
    ], region=(0, 0, 500, 300))


def target_bar(targets):
    """The locked-target bar, one `TargetInBar` per entry.

    Each entry is the list of labels the client draws for it, top to bottom --
    which is the field `textsTopToBottom` is built from, and the field whose
    wrapping is what #389 and #390 both turned on.
    """
    bars = []
    for index, texts in enumerate(targets):
        x = 600 + index * 90
        bars.append(node("TargetInBar", {}, [
            node("Container", {"_name": "barAndImageCont"}, [
                label(text, (x, 40 + line * 12, 80, 12))
                for line, text in enumerate(texts)
            ], region=(x, 40, 80, 60)),
        ], region=(x, 30, 80, 80)))
    return node("TargetsContainer", {}, bars, region=(600, 30, 400, 80))


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
    "fleetOpen", [fleet_window(header_labels(2), [MEMBER_ROW])])
FLEET_SHUT = reading_binding("fleetShut", [])


def elm_strings(values):
    return "[ %s ]" % ", ".join('"%s"' % value for value in values)


def elm_string_lists(values):
    return "[ %s ]" % ", ".join(elm_strings(value) for value in values)


def friendly_fire_step(locked, fleet, verifiable, others, asked=0,
                       row_locked=()):
    """The shipped rule, as one expression over six plain facts.

    `row_locked` is #390's second signal: the names whose *overview row* carries
    the client's `targetedByMeIndicator`. It is a plain list here for the same
    reason the target bar's labels are -- `friendlyFireStepFromReading` is what
    turns a reading into both, so a case can execute the rule itself without
    constructing one.
    """
    return ("friendlyFireStep { lockedTargetTexts = %s"
            ", pilotsLockedOnTheOverview = %s, fleetPilots = %s"
            ", membershipIsVerifiable = %s, otherPilotsOnOverview = %s"
            ", askedReadings = %s }"
            % (elm_string_lists(locked), elm_strings(row_locked),
               elm_strings(fleet), verifiable, elm_strings(others), asked))


# The target bar decorates a name with distance and hull, which is why the
# matcher contains rather than equals.
SONYA_LOCKED = [[SONYA + " [MNRLG]", "13 km", "Imperial Navy Slicer"]]
RAT_LOCKED = [["Centior Monster", "8 km"]]

# The same lock, drawn the way the client actually draws a two-word name: #303
# read `['Tower Sentry', 'Sansha I', '20 km']` off a live bar, the name split
# at a wrap point. `targetTextsCarryName` asks whether any *one* label carries
# the whole name, so this is the bar holding Sonya and saying nothing about it
# -- which is #390, and which is most character names.
SONYA_WRAPPED = [["Sonya", "Spodumain [MNRLG]", "13 km"]]


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
                '%s == UnlockAFleetPilot "%s" TargetBarLabels'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "True", []),
                   SONYA)]),
            [True])

    def test_the_commander_counts_as_a_fleet_pilot(self):
        """`Fleet (5)` beside four member rows: the boss is in the header, and
        is the one pilot it matters most not to shoot."""
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s" TargetBarLabels'
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

    def test_a_name_the_bar_wraps_is_caught_by_the_overview_row(self):
        """#390's defect, executed. The bar holds Sonya and cannot say so --
        the client wrapped her name at the space and `targetTextsCarryName`
        asks whether any one label carries the whole of it -- so before this
        the membership branch answered `Nothing` and, with the Fleet window
        open, fell through to `ClearToFire`. It failed in the *firing*
        direction, which is the direction #367 exists to prevent.

        The first assertion is the instrument going quiet; the second is the
        rule refusing anyway, on the overview row's own lock indicator.
        """
        self.assertEqual(
            self.repl.evaluate([
                'targetTextsCarryName "%s" %s'
                % (SONYA, elm_strings(SONYA_WRAPPED[0])),
                '%s == UnlockAFleetPilot "%s" OverviewRowIndicator'
                % (friendly_fire_step(SONYA_WRAPPED, [SONYA], "True", [],
                                      row_locked=[SONYA]), SONYA)]),
            [False, True])

    def test_either_instrument_refuses_and_both_are_reported(self):
        """The shape of the fix: two signals OR-ed, never swapped one for the
        other. The bar goes quiet on a wrapped name; the row goes quiet when
        the pilot has no row on this overview at all -- a preset that hides
        fleet members, or a pilot who left the grid still holding a lock. An
        `&&` here would hold fire only where they agreed, which is every case
        except the ones this rule is for.

        The three refusals are one case together because it is their
        *combination* that is the property. Each names the instrument it came
        from, so a log settles which one was working.
        """
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s" TargetBarLabels'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "True", []),
                   SONYA),
                '%s == UnlockAFleetPilot "%s" OverviewRowIndicator'
                % (friendly_fire_step(SONYA_WRAPPED, [SONYA], "True", [],
                                      row_locked=[SONYA]), SONYA),
                '%s == UnlockAFleetPilot "%s" BothSignals'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "True", [],
                                      row_locked=[SONYA]), SONYA)]),
            [True, True, True])

    def test_the_two_signals_are_a_union_and_not_an_intersection(self):
        """The same property one level down, as `lockSignalForPilot`'s whole
        truth table. Four rows, and the two middle ones are the fix."""
        def signal(locked, row_locked):
            return "lockSignalForPilot %s %s \"%s\"" % (
                elm_string_lists(locked), elm_strings(row_locked), SONYA)

        self.assertEqual(
            self.repl.evaluate([
                "%s == Nothing" % signal(SONYA_WRAPPED, []),
                "%s == Just TargetBarLabels" % signal(SONYA_LOCKED, []),
                "%s == Just OverviewRowIndicator"
                % signal(SONYA_WRAPPED, [SONYA]),
                "%s == Just BothSignals" % signal(SONYA_LOCKED, [SONYA])]),
            [True, True, True, True])

    def test_a_lock_the_bar_never_rendered_is_still_a_lock(self):
        """`NothingIsLocked` releases the guns, so it has to mean *neither*
        instrument sees anything. A row carrying the client's indicator with
        nothing parsed in the bar is a lock, and answering "nothing is locked"
        to it would be this guard going quiet in the firing direction by the
        one route the rest of the fix does not cover."""
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s" OverviewRowIndicator'
                % (friendly_fire_step([], [SONYA], "True", [],
                                      row_locked=[SONYA]), SONYA),
                "%s == NothingIsLocked"
                % friendly_fire_step([], [SONYA], "True", [])]),
            [True, True])

    def test_the_unverified_pilot_branch_asks_both_instruments_too(self):
        """The Fleet-window-shut fallback runs the same two signals over
        `getNamesOfOtherPilotsInOverview`. A fix applied to the membership
        branch alone would leave the wrapped name firing here."""
        self.assertEqual(
            self.repl.evaluate([
                '%s == HoldFireOnAnUnverifiedPilot "%s" OverviewRowIndicator'
                % (friendly_fire_step(SONYA_WRAPPED, [], "False", [SONYA],
                                      row_locked=[SONYA]), SONYA)]),
            [True])

    def test_the_row_signal_answers_about_a_named_pilot_and_not_a_lock_count(
            self):
        """It has to stay a question about *this* name. A row signal that only
        asked "is anything row-locked" would refuse on every reading where the
        fleet is engaging something, which is a bot that never fires -- the
        failure mode that looks like safety."""
        self.assertEqual(
            self.repl.evaluate([
                "%s == ClearToFire"
                % friendly_fire_step(RAT_LOCKED, [SONYA], "True", [],
                                     row_locked=[COMMANDER])]),
            [True])

    def test_the_unlock_budget_is_spent_only_where_there_is_an_entry_to_click(
            self):
        """`unlockFleetPilotInTargetBar` right-clicks a `Target`, so a pilot
        held on the row indicator alone gives it nothing to ask for. #389's
        second defect was a budget charged for asks nobody made, reporting a
        give-up on an arm that had never been reached; `targetBarSawThePilot`
        is what keeps this counter off that path."""
        self.assertEqual(
            self.repl.evaluate([
                "targetBarSawThePilot TargetBarLabels",
                "targetBarSawThePilot BothSignals",
                "targetBarSawThePilot OverviewRowIndicator"]),
            [True, True, False])

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
                '%s == HoldFireOnAnUnverifiedPilot "%s" TargetBarLabels'
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
                '%s == UnlockAFleetPilot "%s" TargetBarLabels'
                % (friendly_fire_step(SONYA_LOCKED, [SONYA], "False", [SONYA]),
                   SONYA)]),
            [True])

    def test_the_unlock_ask_gives_up_at_the_bound(self):
        self.assertEqual(
            self.repl.evaluate([
                '%s == UnlockAFleetPilot "%s" TargetBarLabels'
                % (friendly_fire_step(
                    SONYA_LOCKED, [SONYA], "True", [],
                    "unlockFleetPilotAskedReadingsBound - 1"), SONYA),
                '%s == GaveUpUnlockingAFleetPilot "%s" TargetBarLabels'
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
                'friendlyFireVetoesTheGuns'
                ' (UnlockAFleetPilot "x" TargetBarLabels)',
                'friendlyFireVetoesTheGuns'
                ' (GaveUpUnlockingAFleetPilot "x" OverviewRowIndicator)',
                'friendlyFireVetoesTheGuns'
                ' (HoldFireOnAnUnverifiedPilot "x" BothSignals)']),
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
        and only `fleetMembershipIsVerifiable` tells the readings apart.

        Since #380 that rule takes the settings the commander falls back to,
        because the roster it is judging is `fleetPilotNamesFromReading`'s --
        see `test_wingman_fleet_roster_corroborated` for what it now judges.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(fleetShut |> Maybe.map fleetMemberNames"
                 " |> Maybe.withDefault []) == []",
                 "(fleetShut |> Maybe.map (fleetMembershipIsVerifiable [])"
                 " |> Maybe.withDefault True) == False",
                 "(fleetOpen |> Maybe.map (fleetMembershipIsVerifiable [])"
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


def guard_reading(name, row_is_targeted, bar):
    """Run 9's own shape, through the real parser.

    The Fleet window lists Sonya, her overview row is there either carrying the
    client's lock indicator or not, and the target bar holds whatever labels the
    client is said to have drawn -- or is absent entirely, which is a reading
    where nothing parsed a bar and the row is the only thing that knows.

    `bar` is one entry per locked target, each a list of the labels the client
    drew for it, which is `target_bar`'s own shape.
    """
    return reading_binding(name, [
        fleet_window(header_labels(2), [SONYA]),
        overview_window([(SONYA, "13 km", row_is_targeted)]),
    ] + ([target_bar(bar)] if bar else []))


class TheGuardReadsBothInstrumentsTest(unittest.TestCase):
    """#390, executed against readings the real parser produced.

    The rule above is a function of plain lists and these are the readings that
    become them, so what is checked here is the half a plain-list case cannot
    see: that `friendlyFireStepFromReading` finds the client's lock indicator on
    the row it should, beside the bar it always read.

    - `wrappedRowLocked`: the incident's shape. The bar wraps `Sonya
      Spodumain` at the space -- #303's live reading -- and her row carries
      `targetedByMeIndicator`.
    - `barNamesHer`: no indicator, and a bar entry whose one label carries the
      whole name. The case that keeps the bar a decision rather than leftovers.
    - `rowLockedNoBar`: the indicator with no target bar parsed at all.
    - `wrappedRowClear`: neither instrument sees her, which is the hole this
      change does *not* close and is named rather than left to be discovered.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        cls.definitions = [
            guard_reading("wrappedRowLocked", True, SONYA_WRAPPED),
            guard_reading("barNamesHer", False, SONYA_LOCKED),
            guard_reading("rowLockedNoBar", True, None),
            guard_reading("wrappedRowClear", False, SONYA_WRAPPED),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_fixtures_arrived(self):
        """A tree the parser made nothing of answers every question below the
        same way an absent rule would."""
        self.assertEqual(
            self.repl.evaluate(
                ["(wrappedRowLocked |> Maybe.andThen .fleetWindow) /= Nothing",
                 '(wrappedRowLocked |> Maybe.map'
                 ' (fleetPilotNamesFromReading []))'
                 ' == Just [ "%s", "%s" ]' % (SONYA, COMMANDER),
                 "(wrappedRowLocked |> Maybe.map (.targets >> List.length))"
                 " == Just 1",
                 "(rowLockedNoBar |> Maybe.map (.targets >> List.length))"
                 " == Just 0",
                 '(wrappedRowLocked |> Maybe.map'
                 ' (overviewRowSaysThisShipHasItLocked "%s")) == Just True'
                 % SONYA,
                 '(barNamesHer |> Maybe.map'
                 ' (overviewRowSaysThisShipHasItLocked "%s")) == Just False'
                 % SONYA],
                definitions=self.definitions),
            [True] * 6)

    def test_the_bar_still_cannot_see_her_on_the_reading_that_matters(self):
        """The measurement the fix rests on, on this file's own fixture: the
        pilot run 9 shot is in the lock bar and `lockedTargetNamed` -- the
        matcher the guard used to decide with -- answers `Nothing`."""
        self.assertEqual(
            self.repl.evaluate(
                ['(wrappedRowLocked |> Maybe.andThen (lockedTargetNamed "%s"))'
                 " == Nothing" % SONYA,
                 '(barNamesHer |> Maybe.andThen (lockedTargetNamed "%s"))'
                 " /= Nothing" % SONYA],
                definitions=self.definitions),
            [True, True])

    def test_the_guard_holds_fire_on_the_reading_that_used_to_fire(self):
        """The whole of #390 in one line: this reading answered `ClearToFire`
        before, because the only instrument the guard had was the one the
        client's wrapping defeats."""
        self.assertEqual(
            self.repl.evaluate(
                ['(wrappedRowLocked |> Maybe.map (friendlyFireStepFromReading'
                 ' [] 0)) == Just (UnlockAFleetPilot "%s"'
                 " OverviewRowIndicator)" % SONYA,
                 "(wrappedRowLocked |> Maybe.map (friendlyFireStepFromReading"
                 " [] 0 >> friendlyFireVetoesTheGuns)) == Just True"],
                definitions=self.definitions),
            [True, True])

    def test_the_bar_is_still_a_signal_and_not_leftovers(self):
        """Replacing one instrument with the other would pass every case
        above. This is the reading where only the bar can answer -- an overview
        row without the indicator drawn on it, which is what a client that
        never draws it looks like, and nothing in this repo has yet watched one
        come back."""
        self.assertEqual(
            self.repl.evaluate(
                ['(barNamesHer |> Maybe.map (friendlyFireStepFromReading [] 0))'
                 ' == Just (UnlockAFleetPilot "%s" TargetBarLabels)' % SONYA],
                definitions=self.definitions),
            [True])

    def test_a_row_with_no_bar_parsed_is_not_a_clean_lock_bar(self):
        self.assertEqual(
            self.repl.evaluate(
                ['(rowLockedNoBar |> Maybe.map (friendlyFireStepFromReading'
                 ' [] 0)) == Just (UnlockAFleetPilot "%s"'
                 " OverviewRowIndicator)" % SONYA],
                definitions=self.definitions),
            [True])

    def test_what_this_change_still_does_not_close(self):
        """Named rather than left to be found. Both instruments can go quiet on
        the same reading: the bar wraps her name *and* the row carries no
        indicator -- a client that does not draw one, an overview preset that
        hides fleet members so there is no row at all, or a pilot who left the
        grid still holding a lock. The guard then reads exactly as it did
        before this change, which is why the row signal was added to the bar's
        answer and not put in its place.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(wrappedRowClear |> Maybe.map (friendlyFireStepFromReading"
                 " [] 0)) == Just ClearToFire"],
                definitions=self.definitions),
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
        for below in ["manageMiddleRowModules", "actOnFleetBroadcast",
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
        self.assertIn("targetBarSawThePilot signal", update)

    def test_the_rule_is_still_a_function_of_plain_values(self):
        """What makes every case in `TheFriendlyFireRuleTest` possible, and
        the property #390 was most at risk of spending: the second signal lives
        on the overview, and reading it inside the rule would have meant no
        case could execute the guard without constructing a reading.
        `friendlyFireStepFromReading` is the whole of the reading half."""
        rule = self.declaration("friendlyFireStep")
        self.assertIn("pilotsLockedOnTheOverview : List String", rule)
        self.assertNotIn("ReadingFromGameClient", rule)
        self.assertIn("overviewRowSaysThisShipHasItLocked", self.declaration(
            "friendlyFireStepFromReading"))

    def test_the_membership_source_is_named_every_reading(self):
        """The half of #367 that is about the log rather than the trigger:
        run 9 carried no line at all about the fleet, so nothing could
        distinguish "nobody qualified" from "there was nothing to check"."""
        status = self.declaration("statusTextFromState")
        self.assertIn("describeFleetMembership context", status)
        self.assertIn("describeFriendlyFireGuard context", status)

        membership = self.declaration("describeFleetMembership")
        self.assertIn("describeFleetRosterVerdict", membership)
        self.assertIn("fleetRosterVerdict", membership)
        self.assertIn("Member rows: ", membership)
        self.assertIn("fleetCommanderNameFromFleetWindowHeader", membership)
        self.assertIn("fleetmateNamesFromLocalChat", membership)

    def test_the_give_up_and_the_hold_are_both_visible(self):
        """Both leave the decision tree looking like a bot with nothing to do,
        which is how a silent refusal becomes a mystery a run later."""
        guard = self.declaration("describeFriendlyFireGuard")
        self.assertIn("GAVE UP unlocking ", guard)
        self.assertIn("HOLDING FIRE on ", guard)
        self.assertIn("UNLOCKING, guns held", guard)

    def test_every_refusal_names_the_instrument_that_saw_the_pilot(self):
        """#390's own status-line half. Two instruments that fail in opposite
        directions means a line saying only "held" leaves the next incident
        reasoning from silence about which one was working -- which is the
        shape of #367 itself, one level down."""
        guard = self.declaration("describeFriendlyFireGuard")
        self.assertEqual(guard.count("describeLockedPilotSignal signal"), 4)
        signals = self.declaration("describeLockedPilotSignal")
        for phrase in ("the target bar's labels",
                       "the overview row's lock indicator"):
            self.assertIn(phrase, signals)


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
