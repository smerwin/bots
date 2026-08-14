"""Tests for saxrat no longer avoiding an anomaly a fleetmate is already in.

Issue #224. `findReasonToAvoidAnomalyFromMemory` takes the head of
`otherPilotsFoundOnArrival` and avoids the anomaly on whoever is there, with no
notion of the fleet -- so the fleet commander whose broadcast sent the ship to
the site reads exactly like a stranger, and the site is written off for the
rest of the session. This bot is meant to be flown in a fleet
(`accept-fleet-invite-from` and `follow-fleet-broadcast-from` are shipped
settings), so "a fleetmate is already on grid" is the intended configuration
rather than an edge case.

**The fix is a filter on a list `getNamesOfOtherPilotsInOverview` already
builds, not a new field and not `fleetWindow.fleetMembers`.** CLAUDE.md's
"Strings and identities read off a live client" records a live capture: `Pilot
is in your fleet` sits on `FlagIconWithState` nodes inside local chat rows
(`XmppChatUserEntry`), and the parser already lifts it, per pilot, as
`ChatUserEntry.standingIconHint` -- the exact list
`getNamesOfOtherPilotsInOverview` cross-references against the overview to name
"other pilots" in the first place. It is **not** on the overview row itself:
five rows were checked live and none carried a `rightAlignedIconContainer`
hint at all, so there is no overview-side field to read instead.

`fleetWindow.fleetMembers` (`Bot.elm`'s own abandoned, commented-out
`getFleetMembers` stub) was the issue's original suggestion and is
deliberately not used. It is a `List UITreeNodeWithDisplayRegion`, not a list
of names -- extracting a pilot's name from each row is new work and is exactly
the "which label in this row is the name" problem the overview reader and the
chat-userlist reader have each already solved once. The chat-hint route needs
none of that: the names it excludes are already resolved strings in a list
this function already holds.

**Absent evidence must not read as "fleetmate".** A chat row this bot cannot
resolve a hint for -- no `FlagIconWithState` at all -- must still read as a
stranger, exactly as it did before this change, so the anomaly is still
avoided. `chatUserIsKnownFleetmate`'s `Nothing -> False` branch is the whole
of that, and it is the one case this file names explicitly as the failure
the design must refuse: a chat row with no hint reading as a fleetmate would
mean a stranger the client simply has not drawn an icon for yet gets treated
as safe.

**Latched and sticky, so getting this wrong the other way costs a session.**
The verdict this feeds is written once, on arrival, into `BotMemory` and never
revisited -- CLAUDE.md's "the do-not-come-back half" -- so a fleetmate wrongly
read as a stranger avoids the anomaly for the rest of the session, and a
stranger wrongly read as a fleetmate would mean fighting beside somebody
neither invited nor followed. Both directions are covered here: a fleetmate
alone must produce an empty list (nothing to avoid), and a fleetmate beside a
genuine stranger must still name the stranger.

**Reachable but never observed.** #201 fixed the trigger that made the arrival
snapshot run at all, so `FoundOtherPilotOnArrival` has never been constructed
in any recorded run -- this defect is latent, not yet paid for, and nothing
here claims otherwise.

The pure rules are executed through the real `Bot.elm` in `elm repl`, with the
`ChatUserEntry` values `chatUserIsKnownFleetmate` is asked about coming from
the real `EveOnline.ParseUserInterface` rather than being hand-built records --
so what the cases assert on is a value shaped exactly as the parser produces
it, not a guess at its fields.

**Both apps.** `eve-online-combat-anomaly-bot` carries the identical
`getNamesOfOtherPilotsInOverview` (compared byte for byte with saxrat's own
copy in `test_arrival_pilot_window.py`'s neighbourhood already established for
the six declarations around it), so it has the same defect and gets the same
filter -- `chatUserStandingHintFleetmateMarker` and `chatUserIsKnownFleetmate`
are identical declarations in both files, asserted here.

**Not touched, and said so rather than silently skipped.** `hideWhenNeutralInLocal`
(`Bot.elm:3680` in the combat anomaly bot) may have the same blind spot -- its
`goodStandingPatterns` list includes the substring `"is in your"`, which a
fleetmate's own hint `Pilot is in your fleet` would match, so a fleetmate might
already read as neutral-or-worse there and cause the bot to dock up on its own
fleet. That is a different function, a different bot setting, and a different
failure (hiding rather than declining an anomaly); #224 does not claim to have
read that path, and this file does not touch it either.

Confirmed by mutation: an absent hint reading as a fleetmate (the failure this
design refuses), the marker string weakened to a shorter substring that would
catch an unrelated standing hint, the filter dropped from
`getNamesOfOtherPilotsInOverview` entirely, and the two apps' copies of the new
declarations drifting apart.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import re
import unittest

from prerequisites import open_repl
from test_arrival_pilot_window import (
    APPS, CombatAnomalyRepl, body_of_declaration, without_block_comments)
from test_saxrat_ported_guards import (
    SaxratRepl, collapsed, label, node, overview, source_of)

# The client's own words, quoted verbatim in CLAUDE.md's "Strings and
# identities read off a live client" -- captured on a `FlagIconWithState` node
# inside a local-chat `XmppChatUserEntry` row, never on an overview row.
FLEET_HINT = "Pilot is in your fleet"

# A standing hint that is a real thing the client draws and is not this one --
# the near miss `stringContainsIgnoringCase` has to decline. Quoted from
# `goodStandingPatterns` in the combat anomaly bot's own `Bot.elm`, which is
# unrelated code this file does not touch but whose vocabulary is real.
UNRELATED_HINT = "Pilot is in your corporation"

FLEET_COMMANDER = "Fleet Commander"
STRANGER = "A Stranger"
SILENT_STRANGER = "A Quiet Stranger"


def chat_user_entry(name, hint=None):
    """One `XmppChatUserEntry` row in the local-chat userlist.

    `hint=None` omits the `FlagIconWithState` node entirely -- the shape a
    stranger with no drawn standing icon takes, and the shape absent evidence
    must still read as a stranger from.
    """
    children = [label(name, (0, 0, 80, 16))]
    if hint is not None:
        children.append(
            node("FlagIconWithState", {"_hint": hint}, region=(80, 0, 16, 16)))
    return node("XmppChatUserEntry", {}, children, region=(0, 0, 100, 16))


def local_chat_window(users):
    """A `ChatWindowStack` for the local channel, holding `users`.

    `localChatWindowFromUserInterface` picks the chat window whose own `_name`
    ends with `_local`, and `parseChatWindowUserlist` needs a descendant whose
    `_name` contains "userlist" case-insensitively to find the row list at
    all -- both are given exactly the shape those two filters read for.
    """
    userlist = node("Userlist", {"_name": "chatUserlist"}, list(users),
                    region=(0, 20, 100, 200))
    chat_window = node("XmppChatWindow", {"_name": "solarsystem_local"},
                       [userlist], region=(0, 0, 120, 220))
    return node("ChatWindowStack", {}, [chat_window], region=(0, 0, 120, 220))


def elm_string_list(names):
    return "[ %s ]" % ", ".join('"%s"' % name for name in names)


class BothAppsRepl:
    """One repl per app carrying this function, so a failure names which."""

    REPLS = {"saxrat": SaxratRepl, "combat anomaly bot": CombatAnomalyRepl}

    @classmethod
    def setUpClass(cls):
        cls.repls = {app: open_repl(repl_class)
                     for app, repl_class in cls.REPLS.items()}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        for app, repl in self.repls.items():
            yield app, repl.evaluate(expressions, definitions)


class TheFleetHintIsReadFromRealChatUserEntries(BothAppsRepl, unittest.TestCase):
    """`chatUserIsKnownFleetmate`, asked about values the real parser produced.

    Not hand-built records: the reading is a UI tree run through the real
    `EveOnline.ParseUserInterface`, and `visibleUsers` is read back off it, so
    what `chatUserIsKnownFleetmate` sees is exactly what the parser hands the
    rest of the bot.
    """

    def flags_for(self):
        """`chatUserIsKnownFleetmate` over the real chat userlist's own order.

        Written against the reading's own `chatWindowStacks` field rather than
        through `localChatWindowFromUserInterface`, because that function is
        merely imported into `Bot.elm` rather than defined there, and `module
        Bot exposing (..)` -- the patch the harness applies to reach anything
        under test at all -- only exposes names a module defines for itself.
        The filter below (`_local`) is the same one that function applies.
        """
        return ("reading |> Maybe.map .chatWindowStacks"
                " |> Maybe.withDefault []"
                " |> List.filterMap .chatWindow"
                " |> List.filter (.name"
                " >> Maybe.map (String.endsWith \"_local\")"
                " >> Maybe.withDefault False)"
                " |> List.head"
                " |> Maybe.andThen .userlist"
                " |> Maybe.map .visibleUsers"
                " |> Maybe.withDefault []"
                " |> List.map chatUserIsKnownFleetmate")

    def test_the_fleet_hint_marks_a_known_fleetmate(self):
        for app, answers in self.each(
                ["(%s) == [ True ]" % self.flags_for()],
                definitions=[SaxratRepl.reading_binding("reading", [
                    local_chat_window(
                        [chat_user_entry(FLEET_COMMANDER, FLEET_HINT)])])]):
            self.assertEqual(
                answers, [True],
                "%s does not read `Pilot is in your fleet` as a known "
                "fleetmate" % app)

    def test_a_stranger_with_no_hint_at_all_is_not_a_fleetmate(self):
        """The failure this whole design must refuse.

        A chat row this bot cannot resolve a hint for -- no
        `FlagIconWithState` node at all, which is the shape a stranger with no
        drawn standing icon takes -- must still read as a stranger. Reading it
        as a fleetmate would mean the anomaly is not avoided for a pilot the
        client has simply not finished rendering an icon for.
        """
        for app, answers in self.each(
                ["(%s) == [ False ]" % self.flags_for()],
                definitions=[SaxratRepl.reading_binding("reading", [
                    local_chat_window(
                        [chat_user_entry(SILENT_STRANGER, hint=None)])])]):
            self.assertEqual(
                answers, [True],
                "%s reads a chat row with no standing hint at all as a known "
                "fleetmate, which is the failure #224's fix must refuse -- "
                "absent evidence must read as a stranger" % app)

    def test_an_unrelated_standing_hint_is_not_a_fleetmate(self):
        """The near miss a substring match would let through.

        `Pilot is in your corporation` is a real hint the client draws and
        shares a prefix with the fleet one; only the fleet wording may count.
        """
        for app, answers in self.each(
                ["(%s) == [ False ]" % self.flags_for()],
                definitions=[SaxratRepl.reading_binding("reading", [
                    local_chat_window(
                        [chat_user_entry(STRANGER, UNRELATED_HINT)])])]):
            self.assertEqual(
                answers, [True],
                "%s reads an unrelated standing hint as the fleet one" % app)

    def test_order_and_the_mix_of_all_three_shapes(self):
        """One row of each shape, read in the order the client rendered them."""
        for app, answers in self.each(
                ["(%s) == [ True, False, False ]" % self.flags_for()],
                definitions=[SaxratRepl.reading_binding("reading", [
                    local_chat_window([
                        chat_user_entry(FLEET_COMMANDER, FLEET_HINT),
                        chat_user_entry(STRANGER, UNRELATED_HINT),
                        chat_user_entry(SILENT_STRANGER, hint=None),
                    ])])]):
            self.assertEqual(
                answers, [True],
                "%s does not read the fleet hint, an unrelated hint and no "
                "hint at all as [fleetmate, stranger, stranger]" % app)


class TheOverviewCrossReferenceDropsFleetmates(BothAppsRepl, unittest.TestCase):
    """`getNamesOfOtherPilotsInOverview`, on a grid holding fleetmates.

    This is the function `findReasonToAvoidAnomalyFromMemory` (through
    `otherPilotsFoundOnArrivalAfterReading`) reads the head of, so what it
    excludes here is what can never become the reason an anomaly is avoided.
    """

    def names_for(self, users, rows):
        reading_def = SaxratRepl.reading_binding(
            "reading", [local_chat_window(users), overview(rows)])
        return reading_def

    def test_a_fleetmate_only_grid_names_nobody(self):
        """An anomaly whose only other occupant is a fleetmate: nothing to avoid.

        This is #224's headline case: the fleet commander whose broadcast sent
        the ship here must not read as a reason to leave.
        """
        for app, answers in self.each(
                ["(reading |> Maybe.map getNamesOfOtherPilotsInOverview)"
                 " == Just []"],
                definitions=[self.names_for(
                    [chat_user_entry(FLEET_COMMANDER, FLEET_HINT)],
                    [("5,000 m", FLEET_COMMANDER, FLEET_COMMANDER)])]):
            self.assertEqual(
                answers, [True],
                "%s still names a fleetmate as another pilot in the "
                "overview, so an anomaly with only a fleetmate on it would "
                "still be avoided" % app)

    def test_a_stranger_beside_a_fleetmate_is_still_named(self):
        """A stranger on grid still means avoid, whoever else is there too."""
        for app, answers in self.each(
                ["(reading |> Maybe.map getNamesOfOtherPilotsInOverview)"
                 " == Just %s" % elm_string_list([STRANGER])],
                definitions=[self.names_for(
                    [chat_user_entry(FLEET_COMMANDER, FLEET_HINT),
                     chat_user_entry(STRANGER, hint=None)],
                    [("5,000 m", FLEET_COMMANDER, FLEET_COMMANDER),
                     ("6,000 m", STRANGER, STRANGER)])]):
            self.assertEqual(
                answers, [True],
                "%s does not still name a genuine stranger once a "
                "fleetmate is also on grid -- the site should still be "
                "avoided" % app)

    def test_a_stranger_with_no_standing_hint_is_still_named(self):
        """The same failure as above, at the level this function is read at.

        Repeats the absent-evidence case through the whole cross-reference
        rather than only through `chatUserIsKnownFleetmate` in isolation, since
        this is the function the leave branch actually reads.
        """
        for app, answers in self.each(
                ["(reading |> Maybe.map getNamesOfOtherPilotsInOverview)"
                 " == Just %s" % elm_string_list([SILENT_STRANGER])],
                definitions=[self.names_for(
                    [chat_user_entry(SILENT_STRANGER, hint=None)],
                    [("5,000 m", SILENT_STRANGER, SILENT_STRANGER)])]):
            self.assertEqual(
                answers, [True],
                "%s drops a stranger with no standing hint from the "
                "overview cross-reference, which reads as though nobody "
                "were there at all" % app)

    def test_two_fleetmates_and_no_strangers_names_nobody(self):
        for app, answers in self.each(
                ["(reading |> Maybe.map getNamesOfOtherPilotsInOverview)"
                 " == Just []"],
                definitions=[self.names_for(
                    [chat_user_entry(FLEET_COMMANDER, FLEET_HINT),
                     chat_user_entry("Fleet Mate Two", FLEET_HINT)],
                    [("5,000 m", FLEET_COMMANDER, FLEET_COMMANDER),
                     ("6,000 m", "Fleet Mate Two", "Fleet Mate Two")])]):
            self.assertEqual(
                answers, [True],
                "%s still names one of two fleetmates as another pilot" % app)


class TheLeaveBranchStillReadsTheHeadOfTheFilteredList(unittest.TestCase):
    """`findReasonToAvoidAnomalyFromMemory` is untouched, read rather than run.

    It takes a whole `BotDecisionContext`, which this suite does not construct
    anywhere -- CLAUDE.md's own reason: a rule reachable only through the whole
    context "could not be executed ... which is exactly why the shipped
    version was checked by reading it". What is checked here is that it still
    takes the head of `otherPilotsFoundOnArrival` unchanged, so the fix really
    is upstream, in the list that memory is built from, and not a second
    change to this branch that could disagree with the first.
    """

    def test_it_still_takes_the_head_of_the_memory_list(self):
        for app, path in APPS:
            branch = collapsed(without_block_comments(
                body_of_declaration(
                    source_of(path), "findReasonToAvoidAnomalyFromMemory")))
            self.assertIn(
                "otherPilotFoundOnArrival :: _", branch,
                "%s's leave branch no longer takes the head of "
                "`otherPilotsFoundOnArrival`, so #224's fix -- which filters "
                "the list built for that memory -- would not reach it" % app)
            self.assertIn(
                "FoundOtherPilotOnArrival", branch,
                "%s's leave branch no longer answers "
                "`FoundOtherPilotOnArrival`" % app)


class TheTwoAppsCarryIdenticalDeclarations(unittest.TestCase):
    """The fix as two new declarations, compared byte for byte across apps.

    `getNamesOfOtherPilotsInOverview` itself is intentionally not compared
    here: saxrat's copy carries a doc comment explaining #224 and the combat
    anomaly bot's did not carry one before this change either, so the two
    text bodies differ by prose while the code -- the `List.filter
    (chatUserIsKnownFleetmate >> not)` this fix adds -- is identical, which
    the case below checks directly.
    """

    def declaration(self, path, name):
        source = source_of(path)
        match = re.search(
            r"(\{-\|(?:(?!-\})[\s\S])*?-\}\n)?%s :[\s\S]*?(?=\n\n\n)"
            % re.escape(name), source)
        self.assertTrue(match, "no declaration named %r in %s" % (name, path))
        return match.group(0)

    def test_the_marker_and_the_predicate_are_identical_in_both_apps(self):
        for name in ("chatUserStandingHintFleetmateMarker",
                     "chatUserIsKnownFleetmate"):
            copies = {app: self.declaration(path, name) for app, path in APPS}
            first = sorted(copies)[0]
            for app, text in copies.items():
                self.assertEqual(
                    text, copies[first],
                    "%s's %s has drifted from %s's" % (app, name, first))

    def test_the_cross_reference_filters_by_the_predicate_in_both_apps(self):
        for app, path in APPS:
            body = collapsed(without_block_comments(
                body_of_declaration(
                    source_of(path), "getNamesOfOtherPilotsInOverview")))
            self.assertIn(
                "List.filter (chatUserIsKnownFleetmate >> not)", body,
                "%s's getNamesOfOtherPilotsInOverview no longer filters "
                "fleetmates out of the names it cross-references against the "
                "overview" % app)


if __name__ == "__main__":
    unittest.main()
