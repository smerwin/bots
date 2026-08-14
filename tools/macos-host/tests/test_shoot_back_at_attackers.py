"""Tests for shooting back at whatever the client says is shooting us (#40).

The mission runner decided what to shoot from the overview's icon colour plus a
list of names an operator had to write down in advance, and anything matching
neither was invisible to it -- including things actively firing at the ship,
since "nothing to fight" is what it prints either way. The client, meanwhile,
names the attacker on every damage line it writes.

Measured over the recordings: 299 of 1198 readings taken under fire found no rat
by icon colour, 26 of them sitting at an acceleration gate under 320-370
hitpoints a window from something named "R.S. Officer". Whether that attacker
had an overview row the colour rule missed is not answerable from a recording --
the bot prints the count, never the rows. (Run 10's long "Nothing to fight"
stretch, which #40 attributes to this, took no damage at all and is #41's locked
gate.)

Two things have to hold for the fix to be worth anything, and each is a place it
could fail while looking correct.

**The two names have to be the same name.** The attacker string comes out of
EVE's combat log; the overview row carries its own Name and Type cells. Nothing
guarantees they agree, and if they do not, the widening matches nothing and the
bot reports "nothing to fight" exactly as before -- silently, since a matcher
that never matches looks identical to a grid with no attackers on it. So the
round-trip is asserted against lines the client really wrote and names the bot
really printed, quoted verbatim below.

**The match must not be loose.** Substring matching would engage the wrong
object, and here it fails in a specific and unrecoverable way: a wreck's Type is
its owner's name with " Wreck" appended, so a substring rule would have the bot
keep firing at the corpse of the thing that stopped shooting it, and a wreck
never dies. `attack-object` already learned this the expensive way in both
directions -- see `isObjectToAttackFromSettings`.

The corpus is real. Every game-log line quoted here was written by the client
during a recorded session, and every overview name quoted here was printed by
the bot itself from `objectName` in the same recorded runs. Nothing here reads a
live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import collections
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))

import botlab_host  # noqa: E402

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The evidence for "these are the same string", one pair per row: a `(combat)`
# line the client wrote, and a line the bot printed from the overview entry's
# own `objectName` on the same or another recorded run. Both sides are verbatim,
# including the apostrophe in "Kruul's Henchman" and the full stops in
# "R.S. Officer" -- the two shapes most likely to be re-spelled between two
# subsystems of the same client.
#
# Measured across all ten runs: the combat log names 37 distinct attackers and
# 33 of them appear byte for byte as an overview name. The four that do not are
# three rats the bot never locked, so no overview-side string was ever printed
# for them, and "Toxic Cloud Environment", which is the pocket's damage cloud
# and has no overview row at all.
NAME_ROUND_TRIP = [
    ("[ 2026.08.03 12:28:45 ] (combat) 51 from Federation Navy Delta II Support Frigate - Penetrates",
     "Lock target from overview entry 'Federation Navy Delta II Support Frigate'"),
    ("[ 2026.08.03 00:02:33 ] (combat) 8 from Kruul's Henchman - Grazes",
     "Current target: Kruul's Henchman."),
    ("[ 2026.08.03 12:55:03 ] (combat) 61 from R.S. Officer - Penetrates",
     "Lock target from overview entry 'R.S. Officer'"),
    ("[ 2026.08.03 00:41:26 ] (combat) 8 from Centii Savage - Grazes",
     "Lock target from overview entry 'Centii Savage'"),
    ("[ 2026.08.03 01:09:22 ] (combat) 18 from Tower Sentry Sansha I - Grazes",
     "Lock target from overview entry 'Tower Sentry Sansha I'"),
    ("[ 2026.08.03 12:49:36 ] (combat) 11 from Federation Navy Atron - Penetrates",
     "Lock target from overview entry 'Federation Navy Atron'"),
    ("[ 2026.08.03 06:00:33 ] (combat) 2 from Splinter Alvi - Grazes",
     "Lock target from overview entry 'Splinter Alvi'"),
]

# Run 10's own pocket, two consecutive readings from the Illegal Activity
# mission the issue was filed on. `topAttacker` is one name per reading, and
# here it changes between two of them -- which is why accumulating it across the
# window recovers the second attacker without the host having to carry a list.
TWO_ATTACKERS_ACROSS_TWO_READINGS = [
    ["[ 2026.08.03 12:28:52 ] (combat) 43 from Federation Navy Delta II Support Frigate - Hits",
     "[ 2026.08.03 12:28:53 ] (combat) 46 from Federation Navy Delta II Support Frigate - Penetrates"],
    ["[ 2026.08.03 12:28:54 ] (combat) 25 from Federation Navy Soldier - Hits"],
]

# Names that must never be engaged by a rule reading the combat log. The first
# two are what a substring rule would select while "Kruul" was shooting; the
# third is the wreck case, which cannot end because a wreck cannot die.
NOT_THE_ATTACKER = [
    "Kruul's Pleasure Hub",
    "Kruul's Henchman",
    "Kruul Wreck",
]


def bot_elm():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as handle:
        return handle.read()


def function_body(source, name):
    """The lines of a top-level definition, up to the next one."""
    start = source.index("\n" + name + " ")
    if source.index("=", start) > source.index("\n", start + 1):
        start = source.index("\n" + name + " ", start + 1)
    end = source.index("\n\n\n", start)
    return source[start:end]


def without_comments(source):
    """Elm source with `{- -}` blocks and `--` line comments removed.

    Needed by the webifier case below, which is about what the code *matches*
    rather than what it talks about -- and the prose there quotes the very
    string it is asserting is not matched.
    """
    out = []
    depth = 0
    index = 0
    while index < len(source):
        if source.startswith("{-", index):
            depth += 1
            index += 2
        elif depth and source.startswith("-}", index):
            depth -= 1
            index += 2
        elif depth:
            index += 1
        elif source.startswith("--", index):
            index = source.find("\n", index)
            if index < 0:
                break
        else:
            out.append(source[index])
            index += 1
    return "".join(out)


def top_attacker(lines):
    """The host's own per-reading aggregation, applied to a list of lines."""
    by_attacker = collections.Counter()
    for line in lines:
        parsed = botlab_host.parse_incoming_damage(botlab_host.parse_game_log_line(line))
        if parsed is not None and parsed[1] is not None:
            by_attacker[parsed[1]] += parsed[0]
    return by_attacker.most_common(1)[0][0] if by_attacker else None


class TheTwoNamesAreTheSameNameTest(unittest.TestCase):
    def test_the_attacker_the_host_reads_is_the_name_the_overview_shows(self):
        for combat_line, overview_line in NAME_ROUND_TRIP:
            with self.subTest(combat_line=combat_line):
                amount, attacker = botlab_host.parse_incoming_damage(
                    botlab_host.parse_game_log_line(combat_line))
                self.assertGreater(amount, 0)
                overview_name = re.search(
                    r"overview entry '(.*)'$|^Current target: (.*)\.$",
                    overview_line)
                overview_name = overview_name.group(1) or overview_name.group(2)
                # Byte for byte. Not "close enough": the matcher this feeds is
                # an exact one, so any difference here is the whole feature
                # failing quietly.
                self.assertEqual(attacker, overview_name)

    def test_the_weapon_and_the_quality_of_the_hit_are_not_part_of_the_name(self):
        # "51 from X - Penetrates" and "74 from X - Mjolnir Heavy Missile -
        # Hits" name the same X. Keeping either suffix would produce a string no
        # overview row has ever carried.
        _, attacker = botlab_host.parse_incoming_damage(
            botlab_host.parse_game_log_line(
                "[ 2026.08.03 04:26:59 ] (combat) 74 from Centum Fiend - "
                "Mjolnir Heavy Missile - Hits"))
        self.assertEqual(attacker, "Centum Fiend")


class OneNameSeveralAttackersTest(unittest.TestCase):
    """`topAttacker` is singular; run 10 had two frigates and a soldier.

    The answer is to accumulate the per-reading name across the window rather
    than to widen the host's aggregation into a list. This asserts the premise
    that makes that work: the top slot really does change between readings, so
    the window collects more names than any single reading reports.
    """

    def test_the_top_attacker_changes_between_readings(self):
        names = [top_attacker(reading)
                 for reading in TWO_ATTACKERS_ACROSS_TWO_READINGS]
        self.assertEqual(names, ["Federation Navy Delta II Support Frigate",
                                 "Federation Navy Soldier"])
        self.assertEqual(len(set(names)), 2,
                         "the window would collect only one name, so the second "
                         "attacker would stay invisible")

    def test_a_single_reading_names_only_its_hardest_hitter(self):
        # The cost being accepted, stated as a test rather than in prose: within
        # one reading the second attacker is genuinely dropped.
        both = TWO_ATTACKERS_ACROSS_TWO_READINGS[0] + TWO_ATTACKERS_ACROSS_TWO_READINGS[1]
        self.assertEqual(top_attacker(both),
                         "Federation Navy Delta II Support Frigate")

    def test_the_window_is_what_bounds_and_clears_the_names(self):
        """No new counter, no new clearing rule -- the samples carry the names.

        `test_ammo_silenced_bound` pins every counter in `BotMemory` to
        resetting, holding, starting or incrementing. This adds none: the names
        ride on `IncomingDamageSample`, so they are trimmed by the same clock
        and capped by the same `incomingDamageSampleLimit` as the damage, and
        they are gone `incomingDamageWindowSeconds` after the last hit -- which
        is the same condition whether the rat died, the ship warped out or the
        pocket ended.
        """
        source = bot_elm()
        body = function_body(source, "namesOfRecentAttackers")
        self.assertIn("memory.samples", body)
        self.assertIn("List.filterMap .attacker", body)
        # It may not reach for anything that outlives the window.
        for forbidden in ("lastAttacker", "botMemoryBefore", "readingFromGameClient"):
            self.assertNotIn(forbidden, body,
                             "namesOfRecentAttackers reads " + forbidden +
                             ", which the window does not bound")

        sample = source[source.index("type alias IncomingDamageSample ="):]
        sample = sample[:sample.index("\n\n\n")]
        self.assertIn(", attacker : Maybe String", sample)

        update = function_body(source, "updateIncomingDamageMemory")
        self.assertIn("attacker = reading.topAttacker", update)
        # Matched as tokens rather than as a line, because elm-format decides
        # where this expression wraps -- it currently splits the operands of
        # `<` across three lines, which a literal "a * 1000" never survives.
        # What the assertion is about is the window bounding the samples, not
        # the layout the formatter chose for it.
        self.assertRegex(update, r"incomingDamageWindowSeconds\s*\*\s*1000")
        self.assertIn("List.take incomingDamageSampleLimit", update)


class TheMatchIsExactTest(unittest.TestCase):
    """The comparison itself, wherever `isObjectShootingAtUs` keeps it.

    Since #90 it keeps it in `namesMatchLabels`, shared with the rule that takes
    a row *out* of the target set for having absorbed every shot fired at it.
    The two are the same question asked in opposite directions and a difference
    between them would be a row that can be engaged for shooting us and never
    dropped for being unhurtable -- so one definition, and these assertions
    follow it rather than pinning the caller's shape.
    """

    def setUp(self):
        source = bot_elm()
        self.body = (function_body(source, "isObjectShootingAtUs")
                     + function_body(source, "anyNameMatchesOverviewLabel")
                     + function_body(source, "namesMatchLabels"))

    def test_it_compares_whole_labels_rather_than_substrings(self):
        # `List.member` over the row's labels, not `String.contains`. See
        # NOT_THE_ATTACKER for what the loose version selects.
        self.assertIn("List.member", self.body)
        for loose in ("String.contains", "stringContainsIgnoringCase", "containsWords"):
            self.assertNotIn(loose, self.body,
                             "isObjectShootingAtUs matches loosely via " + loose)

    def test_it_normalises_case_and_surrounding_space(self):
        self.assertIn("String.trim >> String.toLower", self.body)

    def test_it_still_reads_both_of_the_rows_own_labels(self):
        # Name and Type, which exactness is what makes safe: a wreck's Type is
        # its owner's name with " Wreck" appended. Asserted here because the
        # extraction moved these two lines out of the caller.
        self.assertIn("overviewEntry.objectName", self.body)
        self.assertIn("overviewEntry.objectType", self.body)

    def test_the_names_a_loose_rule_would_have_engaged(self):
        # Asserted as data rather than by running Elm: with the attacker
        # "Kruul", every one of these contains it and none of them equals it.
        for name in NOT_THE_ATTACKER:
            with self.subTest(name=name):
                self.assertIn("Kruul", name)
                self.assertNotEqual(name.strip().lower(), "kruul")


class TheWideningKeepsEveryExistingGuardTest(unittest.TestCase):
    """#40 asked for a wider target set, not a second targeting controller."""

    def setUp(self):
        self.source = bot_elm()

    def test_an_au_distance_is_still_excluded(self):
        # Distances parse only as m and km; an AU distance is an `Err` that
        # every consumer turns into a 999999 placeholder reading as merely far
        # rather than unreachable. The new disjunct sits inside the parenthesised
        # group that `overviewEntryDistanceIsOnGrid` is ANDed with, so it is
        # gated by placement -- which is exactly the kind of thing an edit can
        # undo while everything still compiles.
        body = function_body(self.source, "shouldAttackOverviewEntry")
        self.assertIn("|| isObjectShootingAtUs namesToAttack.fromIncomingDamage overviewEntry\n    )",
                      body)
        self.assertIn("&& overviewEntryDistanceIsOnGrid overviewEntry", body)

    def test_a_virtualised_row_is_still_never_clicked(self):
        # Only rendered rows have a usable region; a hidden one reports the
        # position of whatever was recycled into its place. The lock site
        # filters on `_display` before taking anything, and the new source of
        # candidates arrives through that same list.
        combat = function_body(self.source, "decideActionInCombat")
        lock = combat[combat.index("overviewEntriesToLock ="):]
        lock = lock[:lock.index("\n\n")]
        self.assertIn("List.filter overviewEntryIsDisplayed", lock)

    def test_a_scrambler_still_outranks_something_merely_shooting_us(self):
        # Being unable to leave outranks being shot, so #40's own entries take
        # their distance rank like everything else.
        #
        # The comparison used to be an inline lambda here and #231 moved it into
        # `combatPriorityTier`, which is a rule over a row and can therefore be
        # *executed* -- see `test_ewar_priority_targets`, which asks it what a
        # scrambler and a plain rat sort to. What is left here is the half that
        # is not an expression: that this sort is the one being applied, and
        # that #40's attacker set did not grow a second priority order beside
        # it.
        combat = function_body(self.source, "decideActionInCombat")
        everything = combat[combat.index("everythingWorthAttacking ="):]
        self.assertIn("List.sortBy combatPriorityTier", everything)
        tier = function_body(self.source, "combatPriorityTier")
        self.assertIn("if overviewEntryIsWarpDisruptingMe entry then", tier)
        selection = combat[:combat.index("targetsToUnlock =")]
        self.assertNotIn("fromIncomingDamage entry then", selection,
                         "the attacker set must not introduce a second priority "
                         "order alongside the scrambler-first one")

    def test_an_optional_clearing_briefing_still_wins(self):
        # A briefing that says the pirates need not be cleared is the client
        # saying in writing that the fight is not the job -- run 102 spent 400
        # combat decisions ignoring that, and run 106 repeated it. So attackers
        # are deliberately absent from `isObjectToAttackByName`, which is what
        # survives that filter.
        body = function_body(self.source, "isObjectToAttackByName")
        self.assertIn("isObjectToAttackFromObjective", body)
        self.assertIn("isObjectToAttackFromSettings", body)
        self.assertNotIn("isObjectShootingAtUs", body)
        self.assertNotIn("fromIncomingDamage", body)

    def test_the_existing_two_rules_still_stand(self):
        body = function_body(self.source, "shouldAttackOverviewEntry")
        self.assertIn("iconSpriteHasColorOfRat overviewEntry", body)
        self.assertIn("isObjectToAttackFromObjective namesToAttack.fromObjective", body)
        self.assertIn("isObjectToAttackFromSettings namesToAttack.fromSettings", body)


class TheOperatorCanSeeItTest(unittest.TestCase):
    """A bot that engages something for a reason nobody can read is worse than
    one that does not engage it -- see the `describeBranch` convention."""

    def setUp(self):
        self.source = bot_elm()

    def test_the_decision_log_says_why_it_engaged(self):
        combat = function_body(self.source, "decideActionInCombat")
        self.assertIn("Shooting back at ", combat)
        self.assertIn("the client's combat log names it as having hit this ship",
                      combat)
        # Named only when nothing else would have selected it, so the line means
        # "this is new" rather than appearing on every rat in the pocket.
        branch = combat[combat.index("entriesEngagedOnlyBecauseTheyShotUs ="):]
        branch = branch[:branch.index("targetsToUnlock =")]
        self.assertIn("not (iconSpriteHasColorOfRat entry)", branch)
        self.assertIn("not (isObjectToAttackByName", branch)

    def test_the_branch_is_reachable_from_every_way_the_fight_can_start(self):
        # orbit, keep-at-range and plain: all three end in the fight, and a line
        # that only appears under one of them would be missing on most runs.
        combat = function_body(self.source, "decideActionInCombat")
        for call in [
            "describeShootingBack (ensureShipIsOrbitingDecision",
            "describeShootingBack (ensureShipIsKeepingRangeDecision",
            "describeShootingBack decisionToFight",
        ]:
            self.assertIn(call, combat)

    def test_the_status_line_reports_the_set_every_reading(self):
        # Including when it is empty. The diagnosis this has to support is "the
        # client named an attacker and no overview row carried that name", and a
        # clause printed only on a match cannot say that.
        body = function_body(self.source, "describeIncomingDamage")
        self.assertIn("Attackers named in the window: none.", body)
        self.assertIn("namesOfRecentAttackers memory", body)


class WebbingIsNotDamageTest(unittest.TestCase):
    """A webifier can apply no damage at all, and then it writes no combat line.

    Not covered by this change, and the point of these cases is that the source
    does not pretend otherwise. Issue #40 reports run 10's frigates rendering
    "Pilot is webifying me" on the overview row, but that string appears nowhere
    in the ten recorded runs -- nothing has ever printed these hints -- so
    matching it would be a guard resting on a premise no evidence supports.
    The hints are printed instead, which is what makes the next run evidence.
    """

    def setUp(self):
        self.source = bot_elm()

    def test_no_webifier_literal_is_matched_anywhere(self):
        # Mentioning it in a comment is the point; matching on it is the thing
        # with no evidence behind it. So this looks at string literals only.
        for literal in re.findall(r'"([^"\n]*)"', without_comments(self.source)):
            self.assertNotIn(
                "webif", literal.lower(),
                "Bot.elm matches the literal " + repr(literal) + ", but no "
                "recorded run contains a webifier hint to have derived it from")

    def test_the_hints_are_reported_so_the_next_run_can_settle_it(self):
        body = function_body(self.source, "describeOverviewIndicationHints")
        self.assertIn(".rightAlignedIconsHints", body)
        # Rendered rows only: an undisplayed row's contents belong to whatever
        # was recycled into its place, so reporting them would be reporting a
        # different object's state.
        self.assertIn("List.filter overviewEntryIsDisplayed", body)
        self.assertIn("Common.Basics.listUnique", body)
        self.assertIn("List.take", body)

    def test_the_parser_still_reads_only_the_two_literals_it_can_support(self):
        parser = os.path.join(
            REPO_DIR, "implement", "applications", "eve-online",
            "eve-online-mission-runner", "EveOnline", "ParseUserInterface.elm")
        with open(parser, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn('rightAlignedIconsHintsContainsTextIgnoringCase "is jamming me"', source)
        self.assertIn('rightAlignedIconsHintsContainsTextIgnoringCase "is warp disrupting me"', source)


if __name__ == "__main__":
    unittest.main()
