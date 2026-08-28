"""Tests for an open Fleet window no longer meaning the roster was verified.

The incident (#380): four wingmen read the same fleet at the same moment and
reported **different** member lists -- 0, 2, 4 and 4 rows -- while every one of
them read the commander correctly out of the window's header. Greta Gneiss read
**zero rows and zero local-chat fleetmate icons, with the window open**, in a
four-pilot fleet, with a target locked, and the bot printed:

    Fleet membership: the Fleet window is open and lists 0 member rows: none.
    Friendly fire guard: 1 locked, none of them a fleet pilot -- clear to fire.

`fleetMembershipIsVerifiable` asked whether the Fleet **window was present**,
deliberately not whether it listed anybody, because a fleet of one is a real
reading and requiring a row would put the rule back to reasoning from an empty
list. That argument is right about a fleet of one and wrong about Greta, and
the two readings are otherwise identical -- so the fix has to separate them
with something that is not the row count.

## Why neither of the issue's own two shapes is what shipped

#380 offers corroborating the rows against local chat's standing icons and
treating disagreement as unverified, or dropping the boolean and refusing on
any recognised pilot where the two sources disagree. **Both are keyed on
disagreement, and Greta's two sources agree** -- at zero -- so both verify the
one reading the issue was filed on. `test_the_two_sources_agreeing_at_zero_is_
not_corroboration` is that argument executed rather than asserted here.

The union is also already there: since #396 `fleetPilotNamesFromReading` is the
member rows, the header commander **and** `fleetmateNamesFromLocalChat`, so
Kara's window listing 2 while her icons marked 4 already gives her 4. What no
source on the reading gave was any way to know 4 was not all of them.

## What shipped: the window states its own size

The captured header reads `Fleet (5)` beside **four** member rows, the boss
being drawn in the header instead. `fleetRosterVerdict` compares that number
against the count of **distinct** pilots the bot resolved, and answers four
things: the window is shut, the header states no size, the roster is short, or
the roster is complete. Only the last lets an empty membership list mean
"nobody".

It needs no theory of **why** the rows differ, which is the half #380 says
nobody has established and this cannot establish either. Every candidate the
issue names -- a collapsed or scrolled window, a fleet in wings and squads with
only some branches expanded, a parse that depends on window size -- makes the
rows a *subset* of the fleet, and a count catches a subset however it arose.

And it keeps the fleet of one: header `Fleet (1)`, the boss named, one pilot
resolved, complete. Greta's reading is `Fleet (5)` against the same one
resolved pilot, and short. Those two fixtures below differ in **one character**.

## The direction it fails in

Refusing to fire is cheap here and firing on a fleetmate is not. Both kinds of
not-knowing -- a shut window and a header that states no size -- refuse, which
is `loadRefusalFromGameLog`'s register applied to a roster. The cost falls
entirely on shooting *players*: `getNamesOfOtherPilotsInOverview` is built from
local chat's userlist and never holds an NPC, so a PvE fight is untouched.
`test_the_guard_still_fires_on_a_rat_beside_it` is that shown with a control on
the same reading rather than claimed.

Confirmed by mutation, each failing named cases:

 1. `fleetMembershipIsVerifiable` reverted to `fleetWindow /= Nothing` -- the
    shipped defect exactly, and the one this whole file is about;
 2. `RosterIsShort` made to corroborate, which is the same thing one rule down;
 3. the fleet of one read as unverified (`resolvedPilots <= statedSize`
    inverted, or a non-empty row count required instead of the count rule);
 4. `FleetSizeNotStated` corroborating, so absent evidence reads as a finding;
 5. `FleetWindowIsShut` corroborating, which is #367 undone;
 6. the distinct-name fold dropped, so Kara's duplicated names read as a
    complete roster;
 7. the comparison as `<=` rather than `<`, so a roster one pilot short reads
    as complete;
 8. the guard no longer consulting the verdict;
 9. `fleetPilotNamesFromReading` narrowed by the verdict, which is the lock
    guard being made quieter;
10. the status line still claiming an open window is a verified roster;
11. the two clauses given separate wordings, so they can disagree about one
    reading;
12. the size read as the first integer anywhere in the header, so `Squad 1 (4)`
    answers.

The cases run the real `Bot.elm` through `elm repl` and the readings through
the real `EveOnline.ParseUserInterface`. Nothing here reads a live client, the
recorded corpus, or a running bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from prerequisites import open_repl  # noqa: E402
from test_fleetmate_anomaly_avoidance import (  # noqa: E402
    FLEET_HINT, chat_user_entry, local_chat_window)
from test_wingman_holds_fire_on_fleetmates import (  # noqa: E402
    COMMANDER, HEADER_LABELS, MEMBER_ROW, SONYA, WINGMAN_BOT_ELM, WingmanRepl,
    fleet_window, header_labels, overview_window, reading_binding, target_bar)

# #380's own four pilots. Greta read 0 rows and 0 icons; Kara read 2 rows
# against 4 icons; Heather and Olivia read 4 and 4. All five names below are
# the issue's, and the fleet is five pilots including the boss.
GRETA = MEMBER_ROW
HEATHER = "Heather Hemorphite"
OLIVIA = "Olivia Ochre"
KARA = "Kara Kernite"
FLEET_SIZE = 5

# A rat, which is never in local chat's userlist and therefore never in
# `getNamesOfOtherPilotsInOverview`. The control for "this refuses players and
# not PvE".
RAT = "Centior Monster"


def collapsed(text):
    """Whitespace flattened, so `elm-format` cannot break a structural check."""
    return re.sub(r"\s+", " ", text)


def wingman_source():
    with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
        return handle.read()


def declaration(source, name):
    """One declaration, annotation to body, with its doc comment left behind.

    Bounded to the one declaration: an assertion over the whole file would
    match the same words in a status string and pass against a deleted rule,
    which is the hole this repo has found in its own suite before.
    """
    match = re.search(
        r"^%s :.*?(?=\n\n\n|\Z)" % re.escape(name), source,
        re.MULTILINE | re.DOTALL)
    assert match is not None, "no declaration named %r" % name
    return match.group(0)


def with_fleet_size(name, stated_size, member_rows=(), chat=(), overview=(),
                    bar=None):
    """A reading whose Fleet window states `stated_size`.

    `chat` is `(pilot, is_fleetmate)` pairs, `overview` is
    `(name, distance, targeted)` triples -- `overview_window`'s own shape.
    """
    children = [fleet_window(header_labels(stated_size), list(member_rows))]
    if chat:
        children.append(local_chat_window([
            chat_user_entry(pilot, FLEET_HINT if is_mate else None)
            for pilot, is_mate in chat]))
    if overview:
        children.append(overview_window(list(overview)))
    if bar:
        children.append(target_bar(bar))
    return reading_binding(name, children)


# Greta's reading and a genuine fleet of one, which the shipped rule has to
# answer differently. They are the same tree bar the number in the header
# label: the window is open, no member row parses, no chat icon marks anybody,
# and the header names the boss. What separates them is the client's own
# statement of how many pilots there are.
GRETA_ROSTER = with_fleet_size("gretaRoster", FLEET_SIZE)
FLEET_OF_ONE = with_fleet_size("fleetOfOne", 1)

# Kara's: two rows, four icons. The union rescues her to four distinct names
# and the header says there are five, so the roster is still short -- by
# herself, which is a name no source on her own reading carries.
KARA_ROSTER = with_fleet_size(
    "karaRoster", FLEET_SIZE, member_rows=[GRETA, HEATHER],
    chat=[(COMMANDER, True), (GRETA, True), (HEATHER, True), (OLIVIA, True)])

# Heather's: four rows plus the boss in the header is five, which is what the
# header states. The working client, and the case that keeps this rule from
# being "always unverified".
HEATHER_ROSTER = with_fleet_size(
    "heatherRoster", FLEET_SIZE,
    member_rows=[GRETA, KARA, HEATHER, OLIVIA])

# The same names twice, once as rows and once as chat icons. The list the
# verdict counts is a concatenation, so a count that did not fold duplicates
# would read seven names against a stated five and call the roster complete.
DUPLICATED_ROSTER = with_fleet_size(
    "duplicatedRoster", FLEET_SIZE, member_rows=[GRETA, HEATHER, OLIVIA],
    chat=[(GRETA, True), (HEATHER, True), (OLIVIA, True)])

# The window open with a header carrying no `Fleet (N)` label at all. Absent
# evidence, which must not read as a finding.
NO_SIZE_STATED = reading_binding("noSizeStated", [
    fleet_window([COMMANDER, "Squad 1 (4)", "Wing 1 (4)"], [MEMBER_ROW])])

# More resolved names than the header counts, which the comparison has to
# accept: the stated size and the resolved count come from different sources.
OVER_FULL_ROSTER = with_fleet_size(
    "overFullRoster", 2, member_rows=[GRETA, HEATHER, OLIVIA])

# The commander named one way by the header and another by a chat icon. One
# pilot, and a count that did not fold case would read two.
MIXED_CASE_ROSTER = with_fleet_size(
    "mixedCaseRoster", 2, chat=[(COMMANDER.upper(), True)])

FLEET_SHUT = reading_binding("rosterFleetShut", [])

# Greta's reading with a target locked, which is what makes it an incident
# rather than a curiosity. Sonya is a pilot -- in local chat with no fleetmate
# icon -- her overview row carries the client's own lock indicator, and the
# target bar names her.
GRETA_PILOT_LOCKED = with_fleet_size(
    "gretaPilotLocked", FLEET_SIZE, chat=[(SONYA, False)],
    overview=[(SONYA, "13 km", True)], bar=[[SONYA, "13 km"]])

# The same reading with a **rat** locked instead, and Sonya still on the
# overview and still unlocked. The control: the verdict is identical, so what
# separates the answers is which object is in the lock bar.
GRETA_RAT_LOCKED = with_fleet_size(
    "gretaRatLocked", FLEET_SIZE, chat=[(SONYA, False)],
    overview=[(SONYA, "13 km", False), (RAT, "8 km", True)],
    bar=[[RAT, "8 km"]])

# A corroborated roster with the same stranger locked, which is the other
# control: a bot that could no longer fire on anybody would pass every case
# above.
COMPLETE_PILOT_LOCKED = with_fleet_size(
    "completePilotLocked", 1, chat=[(SONYA, False)],
    overview=[(SONYA, "13 km", True)], bar=[[SONYA, "13 km"]])

# And a fleetmate locked on an uncorroborated roster: positive evidence is
# usable even where the source cannot certify itself, so this is unlocked
# rather than merely held.
GRETA_FLEETMATE_LOCKED = with_fleet_size(
    "gretaFleetmateLocked", FLEET_SIZE, chat=[(OLIVIA, True)],
    overview=[(OLIVIA, "13 km", True)], bar=[[OLIVIA, "13 km"]])

ALL_ROSTERS = [
    GRETA_ROSTER, FLEET_OF_ONE, KARA_ROSTER, HEATHER_ROSTER,
    DUPLICATED_ROSTER, OVER_FULL_ROSTER, MIXED_CASE_ROSTER, NO_SIZE_STATED,
    FLEET_SHUT]

LOCK_READINGS = [
    GRETA_PILOT_LOCKED, GRETA_RAT_LOCKED, COMPLETE_PILOT_LOCKED,
    GRETA_FLEETMATE_LOCKED]


def verdict_of(binding_name):
    return "(%s |> Maybe.map (fleetRosterVerdict []))" % binding_name


def short(stated, resolved):
    return ("Just (RosterIsShort { statedSize = %d, resolvedPilots = %d })"
            % (stated, resolved))


def complete(stated, resolved):
    return ("Just (RosterIsComplete { statedSize = %d, resolvedPilots = %d })"
            % (stated, resolved))


class TheFixturesArrivedTest(unittest.TestCase):
    """A tree the parser made nothing of answers every question below the same
    way an absent rule would, so the fixtures are checked first.

    #174's own lesson, one level up: a reading that never arrived and a rule
    that declined are the same answer from outside.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_fleet_window_reached_the_parser(self):
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaRoster |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(fleetOfOne |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(karaRoster |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(heatherRoster |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(noSizeStated |> Maybe.andThen .fleetWindow) /= Nothing",
                 "(rosterFleetShut |> Maybe.andThen .fleetWindow) == Nothing"],
                definitions=ALL_ROSTERS),
            [True] * 6)

    def test_the_rows_and_the_icons_are_what_the_issue_reports(self):
        """Greta's 0 and 0, Kara's 2 and 4, Heather's 4 -- the issue's own
        table, read back off the real parser rather than assumed of the
        fixtures. Every claim below rests on these being what they say."""
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaRoster |> Maybe.map fleetMemberNames"
                 " |> Maybe.withDefault [ \"x\" ]) == []",
                 "(gretaRoster |> Maybe.map fleetmateNamesFromLocalChat"
                 " |> Maybe.withDefault [ \"x\" ]) == []",
                 "(karaRoster |> Maybe.map"
                 " (fleetMemberNames >> List.length)) == Just 2",
                 "(karaRoster |> Maybe.map"
                 " (fleetmateNamesFromLocalChat >> List.length)) == Just 4",
                 "(heatherRoster |> Maybe.map"
                 " (fleetMemberNames >> List.length)) == Just 4"],
                definitions=ALL_ROSTERS),
            [True] * 5)

    def test_the_two_headline_readings_differ_only_in_the_stated_size(self):
        """Greta's reading and a fleet of one carry the same rows, the same
        (absent) icons and the same commander. If they differed in anything
        else, the pair below would not be about the stated size."""
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaRoster |> Maybe.map fleetMemberNames)"
                 " == (fleetOfOne |> Maybe.map fleetMemberNames)",
                 "(gretaRoster |> Maybe.map fleetmateNamesFromLocalChat)"
                 " == (fleetOfOne |> Maybe.map fleetmateNamesFromLocalChat)",
                 "(gretaRoster |> Maybe.map (fleetPilotNamesFromReading []))"
                 " == (fleetOfOne |> Maybe.map (fleetPilotNamesFromReading []))",
                 "(gretaRoster |> Maybe.andThen"
                 " fleetSizeStatedByFleetWindowHeader) == Just 5",
                 "(fleetOfOne |> Maybe.andThen"
                 " fleetSizeStatedByFleetWindowHeader) == Just 1"],
                definitions=ALL_ROSTERS),
            [True] * 5)


class TheRosterVerdictTest(unittest.TestCase):
    """`fleetRosterVerdict` executed, rather than restated in Python."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_gretas_reading_is_short_and_a_fleet_of_one_is_complete(self):
        """The headline pair, and the whole of #380 in two lines. The window is
        open in both; the row count is 0 in both; the chat icons name nobody in
        both. The client's own stated size is what separates them, and the
        answers have to differ or the rule is either Greta's defect or a rule
        that has broken the fleet of one."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == %s" % (verdict_of("gretaRoster"), short(5, 1)),
                 "%s == %s" % (verdict_of("fleetOfOne"), complete(1, 1)),
                 "(gretaRoster |> Maybe.map (fleetMembershipIsVerifiable []))"
                 " == Just False",
                 "(fleetOfOne |> Maybe.map (fleetMembershipIsVerifiable []))"
                 " == Just True"],
                definitions=ALL_ROSTERS),
            [True] * 4)

    def test_the_two_sources_agreeing_at_zero_is_not_corroboration(self):
        """The argument against both of #380's own shapes, executed.

        Corroborating rows against chat icons -- either as a boolean or as a
        refusal on disagreement -- verifies Greta's reading, because her two
        sources agree: both are empty. So a rule keyed on disagreement cannot
        catch the reading the issue was filed on, whichever way it is spelled.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaRoster |> Maybe.map (\\r ->"
                 " fleetMemberNames r == fleetmateNamesFromLocalChat r))"
                 " == Just True",
                 "%s == %s" % (verdict_of("gretaRoster"), short(5, 1))],
                definitions=ALL_ROSTERS),
            [True, True])

    def test_karas_window_is_short_even_though_the_union_rescues_two(self):
        """#380's sharper case, and the half the union already answered: her
        window lists 2 and her icons mark 4, so `fleetPilotNamesFromReading`
        resolves four distinct names. The header says five, so the roster is
        still short -- by the one name no source on her own reading carries,
        which is Kara herself."""
        self.assertEqual(
            self.repl.evaluate(
                ["(karaRoster |> Maybe.map (fleetPilotNamesFromReading []"
                 " >> List.length)) == Just 7",
                 "%s == %s" % (verdict_of("karaRoster"), short(5, 4)),
                 "(karaRoster |> Maybe.map (fleetMembershipIsVerifiable []))"
                 " == Just False"],
                definitions=ALL_ROSTERS),
            [True] * 3)

    def test_a_window_that_lists_the_whole_fleet_is_corroborated(self):
        """The control against a rule that simply never verifies. Four rows
        plus the boss in the header is five, which is what the header states --
        the working client, and the reading the other three wingmen took."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == %s" % (verdict_of("heatherRoster"), complete(5, 5)),
                 "(heatherRoster |> Maybe.map"
                 " (fleetMembershipIsVerifiable [])) == Just True"],
                definitions=ALL_ROSTERS),
            [True, True])

    def test_a_header_that_states_no_size_cannot_corroborate(self):
        """Absent evidence never reads as a finding. A window whose header
        carries no `Fleet (N)` label at all says nothing about how many pilots
        there are, so it cannot say the member list is all of them -- even
        though this fixture does list a row."""
        self.assertEqual(
            self.repl.evaluate(
                ["(noSizeStated |> Maybe.andThen"
                 " fleetSizeStatedByFleetWindowHeader) == Nothing",
                 "%s == Just FleetSizeNotStated" % verdict_of("noSizeStated"),
                 "(noSizeStated |> Maybe.map"
                 " (fleetMemberNames >> List.length)) == Just 1",
                 "(noSizeStated |> Maybe.map"
                 " (fleetMembershipIsVerifiable [])) == Just False"],
                definitions=ALL_ROSTERS),
            [True] * 4)

    def test_a_shut_window_is_still_its_own_answer(self):
        """#367's original case, unchanged and still distinct from the two new
        ones -- an operator reading `FleetWindowIsShut` has a different remedy
        from one reading `RosterIsShort`."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == Just FleetWindowIsShut" % verdict_of("rosterFleetShut"),
                 "(rosterFleetShut |> Maybe.map"
                 " (fleetMembershipIsVerifiable [])) == Just False"],
                definitions=ALL_ROSTERS),
            [True, True])

    def test_only_a_complete_roster_is_corroborated(self):
        """All four constructors through the one rule the guard reads, so a
        constructor added later has to be given an answer rather than
        inheriting one."""
        self.assertEqual(
            self.repl.evaluate(
                ["fleetRosterIsCorroborated FleetWindowIsShut == False",
                 "fleetRosterIsCorroborated FleetSizeNotStated == False",
                 "fleetRosterIsCorroborated (RosterIsShort"
                 " { statedSize = 5, resolvedPilots = 4 }) == False",
                 "fleetRosterIsCorroborated (RosterIsComplete"
                 " { statedSize = 5, resolvedPilots = 5 }) == True"]),
            [True] * 4)

    def test_the_comparison_is_at_its_boundary_and_either_side(self):
        """A case that asks only about `constant - 1` and `constant` passes for
        any constant, which is the hole four of #120's own cases had. So the
        boundary pair rides with fixed values well clear of it in both
        directions."""
        self.assertEqual(
            self.repl.evaluate(
                ["%s == %s" % (verdict_of("heatherRoster"), complete(5, 5)),
                 "%s == %s" % (verdict_of("karaRoster"), short(5, 4)),
                 "%s == %s" % (verdict_of("gretaRoster"), short(5, 1)),
                 "%s == %s" % (verdict_of("fleetOfOne"), complete(1, 1))],
                definitions=ALL_ROSTERS),
            [True] * 4)

    def test_a_roster_longer_than_the_stated_size_is_complete(self):
        """`>=` rather than `==`, because the stated size and the resolved
        count come from different sources and a chat icon marking somebody the
        header has not counted yet must not read as a short roster. The
        direction is the safe one either way: more names on the no-shoot list
        than the client counted refuses more, never less."""
        self.assertEqual(
            self.repl.evaluate(
                ["fleetRosterIsCorroborated (RosterIsComplete"
                 " { statedSize = 2, resolvedPilots = 9 }) == True",
                 "%s == %s" % (verdict_of("overFullRoster"), complete(2, 4))],
                definitions=ALL_ROSTERS),
            [True, True])

    def test_the_names_are_counted_distinctly(self):
        """`fleetPilotNamesFromReading` concatenates three sources, so a pilot
        in the rows and in the chat icons appears twice. Counting the list
        rather than the distinct names would read this roster as six against a
        stated five and call it complete, which is a roster short by two
        pilots reading as verified."""
        self.assertEqual(
            self.repl.evaluate(
                ["(duplicatedRoster |> Maybe.map"
                 " (fleetPilotNamesFromReading [] >> List.length)) == Just 7",
                 "%s == %s" % (verdict_of("duplicatedRoster"), short(5, 4))],
                definitions=ALL_ROSTERS),
            [True, True])

    def test_the_count_is_case_insensitive(self):
        """Two spellings of one pilot are one pilot. Over-merging lowers the
        count, which reads as short and refuses -- the safe direction -- where
        under-merging inflates it and verifies a roster that is not there."""
        self.assertEqual(
            self.repl.evaluate(
                ["(mixedCaseRoster |> Maybe.map"
                 " (fleetPilotNamesFromReading [] >> List.length)) == Just 2",
                 "%s == %s" % (verdict_of("mixedCaseRoster"), short(2, 1))],
                definitions=ALL_ROSTERS),
            [True, True])


class TheStatedSizeIsReadOffTheHeaderTest(unittest.TestCase):
    """The parse the verdict rests on, against the client's own label."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_captured_header_is_read_as_five(self):
        """`Fleet (5)` is the live capture WINGMAN.md records off Gal Bistot's
        client, beside four member rows -- so the size and the row count really
        do differ by the boss on a working window, which is what makes the
        comparison a comparison."""
        self.assertEqual(HEADER_LABELS[0], "Fleet (5)")
        self.assertEqual(
            self.repl.evaluate(
                ["fleetSizeFromHeaderLabel \"Fleet (5)\" == Just 5"]),
            [True])

    def test_the_structure_labels_are_not_read_as_a_fleet_size(self):
        """The other three labels the capture carries. `Squad 1 (4)` and
        `Wing 1 (4)` also end in a parenthesised integer, so a rule taking the
        first integer anywhere in the header would answer 1 for the squad's own
        number and a rule taking any `(N)` would answer 4."""
        self.assertEqual(
            self.repl.evaluate(
                ["fleetSizeFromHeaderLabel \"%s\" == Nothing" % COMMANDER,
                 "fleetSizeFromHeaderLabel \"Squad 1 (4)\" == Nothing",
                 "fleetSizeFromHeaderLabel \"Wing 1 (4)\" == Nothing",
                 "fleetSizeFromHeaderLabel \"(no commander)\" == Nothing"]),
            [True] * 4)

    def test_a_label_that_is_not_a_number_answers_nothing(self):
        """Never a guessed zero: a header this bot cannot read a size out of is
        `FleetSizeNotStated`, which refuses, where `Just 0` would make every
        roster complete."""
        self.assertEqual(
            self.repl.evaluate(
                ["fleetSizeFromHeaderLabel \"Fleet (many)\" == Nothing",
                 "fleetSizeFromHeaderLabel \"Fleet (\" == Nothing",
                 "fleetSizeFromHeaderLabel \"Fleet 5\" == Nothing",
                 "fleetSizeFromHeaderLabel \"\" == Nothing",
                 "fleetSizeFromHeaderLabel \"Fleet (0)\" == Just 0"]),
            [True] * 5)

    def test_the_marker_is_one_constant_for_the_match_and_the_slice(self):
        """`gateKeyClosingMarker`'s arrangement: an extraction can never
        succeed on a label the match would have rejected, because there is one
        literal rather than two that could drift apart."""
        body = collapsed(
            declaration(wingman_source(), "fleetSizeFromHeaderLabel"))
        self.assertEqual(body.count("fleetSizeStatedMarker"), 2)
        self.assertNotIn('"Fleet ("', body)


class TheGuardActsOnTheVerdictTest(unittest.TestCase):
    """#380's incident and its controls, through `friendlyFireStepFromReading`.

    The rule is a function of plain lists and these are the readings that
    become them, so what is checked here is the half a plain-list case cannot
    see: that the reading really reaches the verdict, and that the verdict
    really reaches the guard.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_lock_fixtures_arrived(self):
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaPilotLocked |> Maybe.map (.targets >> List.length))"
                 " == Just 1",
                 "(gretaRatLocked |> Maybe.map (.targets >> List.length))"
                 " == Just 1",
                 "(gretaPilotLocked |> Maybe.map"
                 " getNamesOfOtherPilotsInOverview) == Just [ \"%s\" ]" % SONYA,
                 "(gretaRatLocked |> Maybe.map"
                 " getNamesOfOtherPilotsInOverview) == Just [ \"%s\" ]" % SONYA,
                 "(gretaPilotLocked |> Maybe.map (fleetRosterVerdict []))"
                 " == %s" % short(5, 1),
                 "(gretaRatLocked |> Maybe.map (fleetRosterVerdict []))"
                 " == %s" % short(5, 1)],
                definitions=LOCK_READINGS),
            [True] * 6)

    def test_greta_would_have_fired_and_now_holds(self):
        """The incident. A pilot is locked, the Fleet window is open, and the
        member list is empty -- which the shipped rule read as `ClearToFire`
        while printing that membership had been verified."""
        self.assertEqual(
            self.repl.evaluate(
                ['(gretaPilotLocked |> Maybe.map'
                 ' (friendlyFireStepFromReading [] 0))'
                 ' == Just (HoldFireOnAnUnverifiedPilot "%s" BothSignals)'
                 % SONYA,
                 "(gretaPilotLocked |> Maybe.map (friendlyFireStepFromReading"
                 " [] 0 >> friendlyFireVetoesTheGuns)) == Just True"],
                definitions=LOCK_READINGS),
            [True, True])

    def test_the_guard_still_fires_on_a_rat_beside_it(self):
        """The control, and the one that keeps this from being "never fire".

        The same uncorroborated roster, the same pilot on the same overview --
        merely not locked -- and a rat in the lock bar instead. An NPC is never
        in `getNamesOfOtherPilotsInOverview`, which is built from local chat's
        userlist, so PvE is untouched by the refusal above. What separates the
        two answers is which object is locked and nothing else.
        """
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaRatLocked |> Maybe.map"
                 " (friendlyFireStepFromReading [] 0)) == Just ClearToFire",
                 "(gretaRatLocked |> Maybe.map (friendlyFireStepFromReading"
                 " [] 0 >> friendlyFireVetoesTheGuns)) == Just False"],
                definitions=LOCK_READINGS),
            [True, True])

    def test_a_corroborated_roster_still_fires_on_a_stranger(self):
        """The second control: with the roster corroborated, a pilot who is not
        on it is a legitimate target and the guns are released. Without this a
        rule that refused everything would pass every case above."""
        self.assertEqual(
            self.repl.evaluate(
                ["(completePilotLocked |> Maybe.map (fleetRosterVerdict []))"
                 " == %s" % complete(1, 1),
                 "(completePilotLocked |> Maybe.map"
                 " (friendlyFireStepFromReading [] 0)) == Just ClearToFire"],
                definitions=LOCK_READINGS),
            [True, True])

    def test_a_named_fleetmate_outranks_the_uncorroborated_case(self):
        """Positive evidence is usable even where the source cannot certify
        itself: a pilot the chat icons mark is unlocked rather than merely
        held, on the same short roster. #396's ordering, unchanged."""
        self.assertEqual(
            self.repl.evaluate(
                ["(gretaFleetmateLocked |> Maybe.map (fleetRosterVerdict []))"
                 " == %s" % short(5, 2),
                 '(gretaFleetmateLocked |> Maybe.map'
                 ' (friendlyFireStepFromReading [] 0))'
                 ' == Just (UnlockAFleetPilot "%s" BothSignals)' % OLIVIA],
                definitions=LOCK_READINGS),
            [True, True])


class TheLockGuardsConsumerIsNotQuieterTest(unittest.TestCase):
    """#380 names the second consumer: `fleetPilotNames` also feeds "do not
    lock a called target who is in the fleet", so an under-reported roster
    weakens the lock guard too.

    **That list is deliberately untouched**, and this class is what says so.
    Narrowing it by the verdict is the one change that would make the lock
    guard *quieter* -- it would stop refusing names it refuses today, on
    exactly the readings where the roster is least trustworthy. So the roster
    rule adds a refusal to the trigger and takes none away from the lock, and
    the shortfall the lock guard still has is now named on every reading by the
    membership clause, which is the evidence a follow-up would need.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_no_shoot_list_still_names_everyone_it_resolved(self):
        """On the short roster the list is exactly what the three sources gave,
        in the order they gave it -- no shorter for the verdict being
        uncorroborated."""
        self.assertEqual(
            self.repl.evaluate(
                ['(karaRoster |> Maybe.map (fleetPilotNamesFromReading []))'
                 ' == Just [ "%s", "%s", "%s", "%s", "%s", "%s", "%s" ]'
                 % (GRETA, HEATHER, COMMANDER, COMMANDER, GRETA, HEATHER,
                    OLIVIA)],
                definitions=ALL_ROSTERS),
            [True])

    def test_the_roster_rule_never_narrows_that_list(self):
        """`fleetPilotNamesFromReading` is an input to the verdict and never
        the other way round, so there is no path by which a verdict can remove
        a name from the no-shoot list."""
        names = self.declaration("fleetPilotNamesFromReading")
        for forbidden in ("fleetRosterVerdict", "fleetRosterIsCorroborated",
                          "fleetMembershipIsVerifiable",
                          "fleetSizeStatedByFleetWindowHeader"):
            self.assertNotIn(forbidden, names)

    def test_the_called_target_guard_still_asks_the_unnarrowed_list(self):
        """The lock guard's own site: the `CalledTarget` arm asks
        `fleetPilotNames` and nothing else, which is what it asked before."""
        arm = self.declaration("actOnFleetBroadcast")
        self.assertIn("List.member calledTarget (fleetPilotNames context)",
                      collapsed(arm))
        self.assertNotIn("fleetRosterVerdict", arm)
        self.assertNotIn("fleetMembershipIsVerifiable", arm)

    def test_the_verdict_is_read_by_the_guard_and_by_the_status_line_only(self):
        """The blast radius, counted. `fleetRosterVerdict` is reached from the
        rule that answers the guard and from the two clauses that report it,
        and by no decision branch -- so a later reader has to be added
        deliberately."""
        callers = [name for name in self.declaration_names()
                   if "fleetRosterVerdict" in self.declaration(name)
                   and name != "fleetRosterVerdict"]
        self.assertEqual(
            sorted(callers),
            ["describeFleetMembership", "describeFriendlyFireGuard",
             "fleetMembershipIsVerifiable"])

    def declaration(self, name):
        return declaration(self.source, name)

    def declaration_names(self):
        return re.findall(r"^(\w+) :", self.source, re.MULTILINE)


class TheStatusLineSaysWhichAnswerItGaveTest(unittest.TestCase):
    """The half #367 is about the log rather than the trigger.

    Greta's line read `the Fleet window is open and lists 0 member rows: none`,
    which is a true sentence that reads as verification. What an operator needs
    on that reading is that the roster was **not** corroborated and why.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_every_verdict_renders_and_names_its_own_numbers(self):
        """Rendered rather than asserted by substring over the branch, which is
        how a case written to catch a press aimed at the wrong button once
        passed on the branch's own log text (#145)."""
        rendered = self.repl.strings([
            "describeFleetRosterVerdict FleetWindowIsShut",
            "describeFleetRosterVerdict FleetSizeNotStated",
            "describeFleetRosterVerdict (RosterIsShort"
            " { statedSize = 5, resolvedPilots = 1 })",
            "describeFleetRosterVerdict (RosterIsComplete"
            " { statedSize = 5, resolvedPilots = 5 })"])
        shut, no_size, is_short, is_complete = rendered

        for refusing in (shut, no_size, is_short):
            self.assertIn("NOT CORROBORATED", refusing)
        self.assertNotIn("NOT CORROBORATED", is_complete)
        self.assertIn("corroborated", is_complete)

        self.assertIn("the Fleet window is not open", shut)
        self.assertIn("states no fleet size", no_size)
        self.assertIn("states 5 pilots and only 1 could be resolved", is_short)
        self.assertIn("states 5 pilots and 5 are resolved", is_complete)

    def test_the_open_window_is_no_longer_called_verified(self):
        """The sentence Greta got, refused by name. `describeFleetMembership`
        may still print the row count -- an operator wants it -- but not as the
        clause that says whether the list may be believed."""
        membership = collapsed(self.declaration("describeFleetMembership"))
        self.assertNotIn("the Fleet window is open and lists ", membership)
        self.assertIn("describeFleetRosterVerdict", membership)

    def test_the_two_clauses_cannot_disagree_about_one_reading(self):
        """The membership clause and the guard's `HOLDING FIRE` sentence are
        printed side by side, so a reader is entitled to assume they describe
        the same reading. One wording, contained in the other, rather than two
        that could drift."""
        self.assertIn(
            "describeFleetRosterVerdictBriefly",
            collapsed(self.declaration("describeFleetRosterVerdict")))
        self.assertIn(
            "describeFleetRosterVerdictBriefly",
            collapsed(self.declaration("describeFriendlyFireGuard")))
        rendered = self.repl.strings([
            "describeFleetRosterVerdictBriefly (RosterIsShort"
            " { statedSize = 5, resolvedPilots = 1 })",
            "describeFleetRosterVerdict (RosterIsShort"
            " { statedSize = 5, resolvedPilots = 1 })"])
        self.assertIn(rendered[0], rendered[1])

    def test_the_hold_no_longer_blames_a_shut_window(self):
        """`HoldFireOnAnUnverifiedPilot` used to say "with the Fleet window
        shut", which is now one of three reasons and is the wrong one on
        Greta's reading -- her window was open."""
        guard = collapsed(self.declaration("describeFriendlyFireGuard"))
        self.assertIn("HOLDING FIRE on ", guard)
        self.assertNotIn("with the Fleet window shut", guard)

    def declaration(self, name):
        return declaration(self.source, name)


class TheRowCountIsDeliberatelyNotTheRuleTest(unittest.TestCase):
    """The shape #380 warns against, refused rather than left to be tried.

    Requiring a non-empty member row count is the obvious fix and is the one
    `fleetMembershipIsVerifiable`'s own doc comment already declined: it
    reintroduces reasoning from an empty list, and it breaks a genuine fleet of
    one, whose window legitimately lists no rows because the only pilot is the
    boss in the header.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingmanRepl)
        with open(WINGMAN_BOT_ELM, encoding="utf-8") as handle:
            cls.source = handle.read()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_verdict_asks_no_row_count(self):
        body = collapsed(declaration(self.source, "fleetRosterVerdict"))
        self.assertNotIn("fleetMemberNames", body)
        self.assertIn("fleetSizeStatedByFleetWindowHeader", body)
        self.assertIn("fleetPilotNamesFromReading", body)

    def test_a_fleet_of_one_lists_no_rows_and_is_still_corroborated(self):
        """The reading a row-count rule would refuse, executed."""
        self.assertEqual(
            self.repl.evaluate(
                ["(fleetOfOne |> Maybe.map fleetMemberNames)"
                 " == Just []",
                 "(fleetOfOne |> Maybe.map (fleetMembershipIsVerifiable []))"
                 " == Just True"],
                definitions=ALL_ROSTERS),
            [True, True])


if __name__ == "__main__":
    unittest.main()
