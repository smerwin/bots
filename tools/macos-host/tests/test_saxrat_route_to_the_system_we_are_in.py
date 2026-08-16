"""Tests for the hunt circuit never asking for the system the ship is in.

Issue #262. A destination in the current solar system is `Route 0 Jumps` with
no marker, which `routePanelSaysNoDestination` reads -- correctly -- as no
route. So the ask can never be satisfied: the client accepts it, the panel
never answers, and `routeAskGiveUpReadings` turns that into
`routeSettingGivenUp`, which is latched for the whole session and takes the
bot's ability to change system with it.

**The guard is in the picker rather than at the ask**, because the picker has
two callers and they have to name the same destination. `nextHuntingGround`
runs on the memory `updateMemoryForNewReadingFromGame` has already written for
this reading, and that update names `destinationAskedFor` from the index it had
*before* writing it -- so on the reading where the ship arrives in the system
the pointer names, the two are handed indices one apart. Skipping "the system
we are in" is what makes that step invisible: the answer from `index` and the
answer from `index + 1` are the same as soon as the entry at `index` is the
system the ship is standing in, which is the only condition under which the
pointer moves.

That disagreement is recorded rather than theoretical, in the shape the status
line prints it:

    Sys Hamse -> Lashkai asked 'Hamse' 1/20

-- the counter naming the system the ship is standing in while the decision
asks for the next one. 21 such readings across runs 41, 44, 46 and 47 -- every
disagreement those runs carry -- against 87 where the two agree, and the older
wording carries the same shape (`next Zhilshinou. Asked for 'Lashkai' 1/20`)
141 times across 13 runs before them.

**What the corpus does not show is the ask itself going to the current
system.** Across the 116,062 status lines in runs 38-47 that print both the
current system and the next hunting ground, the two are never equal, and none
of those runs latched the give-up. The four runs that did latch it -- 2, 12, 26
and 27 -- each did so for a different reason than this issue describes, and
`TheCorpusIsQuotedRatherThanRememberedTest` below records what they actually
say. The hazard this file pins is therefore proved from the code rather than
from a recording: `nextHuntingGroundFrom`'s home-system fallback answers the
same name at every index once a lap is complete, so a ship standing in its home
system asks for the system it is in on every reading until the latch fires.

**The skip must not become a stall.** A circuit whose every entry is the system
the ship is in answers `Nothing`, which is the answer
`setRouteToNextHuntingGround` already has a home for: it tethers and goes on
hunting whatever spawns, exactly as a bot with no `hunt-system` does. Nothing
here can decline forever -- #257 shipped green and blocked the bot for 108
minutes doing that, so `TheSkipEndsSomewhereSafeTest` reads the branch.

The rules are executed through the real `Bot.elm` in `elm repl`, against
readings built by the real `EveOnline.ParseUserInterface`.

Confirmed by mutation, nine of them, each failing a named case: the skip
dropped entirely (six cases, led by
`test_the_next_entry_is_skipped_when_it_is_this_system`); only the entry under
the pointer skipped rather than the search running past it
(`test_a_run_of_this_system_is_searched_past`); an unreadable location panel
skipping everything (`test_an_unreadable_location_panel_skips_nothing`); the
names compared untrimmed
(`test_the_client_s_own_padding_does_not_defeat_the_comparison`); the unguarded
answer taken when every candidate is skipped
(`test_the_home_system_is_not_asked_for_while_standing_in_it` and two more);
the memory update calling `huntingGroundAtIndex` and so bypassing the guard
(`test_both_callers_hand_it_the_same_three_things`); the status line reading
the location panel itself again
(`test_the_current_system_is_read_in_one_place`); the nowhere clause naming
only the missing setting
(`test_the_operator_is_told_which_kind_of_nowhere_it_is`); and the nowhere case
waiting instead of tethering
(`test_naming_nowhere_tethers_rather_than_waits`).

**One of those survived the first pass and the hole was real.** Skipping only
the candidate under the pointer passes
`test_a_circuit_that_is_all_this_system_names_nowhere`, because every candidate
in that circuit is skipped either way -- so the case that was written to pin
"the search terminates" said nothing about "the search continues".
`test_a_run_of_this_system_is_searched_past` is what separates them.

Nothing here reads a live game client or a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_saxrat_ported_guards import (
    SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, node, source_of)

# The circuit this bot is actually flown with, in the order CLAUDE.md and every
# recorded run carry it. Hamse is first, and is also the staging system, which
# is what makes the lap-completed case the live one rather than a contrived one.
CIRCUIT = ["Hamse", "Lashkai", "Zhilshinou"]

# A system that is not on the circuit above, for the readings where the ship is
# somewhere the guard has no opinion about.
ELSEWHERE = "Amarr"


def location_panel(systemName):
    """The info panel as the client draws it, naming the system we are in.

    `parseInfoPanelLocationInfoFromInfoPanelContainer` needs all three of these:
    the `InfoPanelLocationInfo` node itself, a `ListSurroundingsBtn` under it --
    without which the whole panel parses to `Nothing` -- and the label the
    client has named `headerLabelSystemName` since 2024-05-26, whose text is
    where the system's name is read from.
    """
    return node("InfoPanelContainer", {"_name": "infoPanelContainer"}, [
        node("InfoPanelLocationInfo", {"_name": "infoPanelLocationInfo"}, [
            node("EveLabelMedium",
                 {"_name": "headerLabelSystemName", "_setText": systemName},
                 region=(4, 4, 120, 12)),
            node("ListSurroundingsBtn", {"_name": "listSurroundingsBtn"},
                 region=(4, 20, 20, 20)),
        ], region=(0, 0, 200, 44)),
    ], region=(0, 0, 200, 44))


def pick(settings, index, reading):
    """`nextHuntingGroundFrom` over a reading the binding holds as a `Maybe`.

    The reading is the picker's last argument, so the partial application is
    what `Maybe.andThen` wants and nothing has to unwrap a
    `ParsedUserInterface` this suite deliberately never builds by hand.
    """
    return "(%s |> Maybe.andThen (nextHuntingGroundFrom %s %d))" % (
        reading, settings, index)


def saxrat_runs(*numbers):
    """The recorded saxrat runs this machine has, or the shared skip.

    Same wording as every other saxrat corpus case, because
    `check_expected_skips.py` matches on it and refuses a second spelling.
    """
    logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
            for number in numbers]
    logs = [path for path in logs if os.path.exists(path)]
    if not logs:
        raise unittest.SkipTest(
            "no recorded saxrat runs in ~/eve-bot-logs, so what those runs say "
            "about the hunt circuit cannot be consulted here")
    return logs


class HuntCircuitRepl(SaxratRepl):
    """The picker, over readings that name the system the ship is in."""

    @staticmethod
    def settings(hunt=(), home=None):
        return "{ defaultBotSettings | huntSystemNames = [ %s ], homeSystemName = %s }" % (
            ", ".join('"%s"' % name for name in hunt),
            'Just "%s"' % home if home else "Nothing")

    def picked(self, expressions, definitions):
        """`Maybe String` answers, printed as a string so `nowhere` is legible."""
        return self.strings(
            ["(%s) |> Maybe.withDefault \"nowhere\"" % expression
             for expression in expressions], definitions)


class TheFixtureNamesTheSystemTest(unittest.TestCase):
    """What the parser makes of these trees, before anything concludes from it.

    Issue #174's lesson: a reading that never arrived and a rule that answered
    nothing are the same `Nothing` from outside, so the fixture is asked what it
    says before any case below asks what the rule says about it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HuntCircuitRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_panel_reads_back_as_the_system_it_was_built_with(self):
        answers = self.repl.picked(
            ["here |> Maybe.andThen currentSolarSystemNameFromReading",
             "nowhere |> Maybe.andThen currentSolarSystemNameFromReading"],
            [self.repl.reading_binding("here", [location_panel("Hamse")]),
             self.repl.reading_binding("nowhere", [])])
        self.assertEqual(
            answers, ["Hamse", "nowhere"],
            "the location panel this file builds is not read as naming a solar "
            "system, so every case below would be asserting against a reading "
            "that says nothing")


class AHuntingGroundEqualToThisSystemIsSkippedTest(unittest.TestCase):
    """The guard itself, executed."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HuntCircuitRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def readings(self):
        return [
            self.repl.reading_binding("inHamse", [location_panel("Hamse")]),
            self.repl.reading_binding("elsewhere", [location_panel(ELSEWHERE)]),
        ]

    def test_the_next_entry_is_skipped_when_it_is_this_system(self):
        """The whole issue in one answer: index 0 names Hamse, the ship is in
        Hamse, and what comes back is the entry after it."""
        settings = self.repl.settings(hunt=CIRCUIT)
        [asked] = self.repl.picked(
            [pick(settings, 0, "inHamse")], self.readings())
        self.assertEqual(
            asked, "Lashkai",
            "the circuit asked for a route to the system the ship is already "
            "in, which the client answers with `Route 0 Jumps` and no marker")

    def test_nothing_is_skipped_when_the_ship_is_somewhere_else(self):
        """The rotation is untouched where the guard has nothing to say."""
        settings = self.repl.settings(hunt=CIRCUIT)
        answers = self.repl.picked(
            [pick(settings, index, "elsewhere")
             for index in range(len(CIRCUIT))], self.readings())
        self.assertEqual(
            answers, CIRCUIT,
            "the circuit no longer visits its systems in the order they were "
            "configured")

    def test_the_home_system_is_not_asked_for_while_standing_in_it(self):
        """The one path that can hold this state open indefinitely.

        Once a lap is complete the picker answers `home-system` at *every*
        index, and the pointer goes on advancing while the ship stands in a
        system the circuit names -- so with the home system reached, every
        reading asks for the system the ship is in, for as long as the bot is
        there. This is the shape the issue is about and it needs no misreading
        anywhere to arrive.
        """
        settings = self.repl.settings(hunt=CIRCUIT, home="Hamse")
        answers = self.repl.picked(
            [pick(settings, index, "inHamse")
             for index in [len(CIRCUIT), len(CIRCUIT) + 1, len(CIRCUIT) * 3]],
            self.readings())
        self.assertEqual(
            answers, ["nowhere"] * 3,
            "a completed lap asks for the staging system while the ship is "
            "standing in it, which is a route the client cannot give")

    def test_the_home_system_is_still_reached_from_anywhere_else(self):
        settings = self.repl.settings(hunt=CIRCUIT, home="Hamse")
        [asked] = self.repl.picked(
            [pick(settings, len(CIRCUIT), "elsewhere")],
            self.readings())
        self.assertEqual(
            asked, "Hamse",
            "the guard swallowed the staging system for a ship that is not in "
            "it, so a completed lap no longer goes home")

    def test_a_circuit_of_one_that_is_this_system_names_nowhere(self):
        """The degenerate configuration, which must park rather than ask.

        `Nothing` here is the answer `setRouteToNextHuntingGround` already
        handles, and it is the honest one: there is nowhere on this circuit to
        go that the ship is not already.
        """
        [asked] = self.repl.picked(
            [pick(self.repl.settings(hunt=["Hamse"]), 0, "inHamse")],
            self.readings())
        self.assertEqual(asked, "nowhere")

    def test_a_run_of_this_system_is_searched_past(self):
        """The case a one-entry lookahead passes and should not.

        A guard that skipped the entry under the pointer and then took whatever
        came next answers `nowhere` here -- and there *is* somewhere to go, two
        entries along. Written after a mutation of exactly that shape survived
        the all-one-system case below, which cannot separate the two because
        every candidate in it is skipped either way.
        """
        settings = self.repl.settings(hunt=["Hamse", "Hamse", "Lashkai"])
        [asked] = self.repl.picked(
            [pick(settings, 0, "inHamse")], self.readings())
        self.assertEqual(
            asked, "Lashkai",
            "the search stops at the first candidate it skips, so a circuit "
            "that names this system twice reads as having nowhere to go")

    def test_a_circuit_that_is_all_this_system_names_nowhere(self):
        """Searching past the first candidate must terminate.

        A guard that only looked at the entry under the pointer would answer
        the *next* copy of the same name here, which is the same unsatisfiable
        ask one index along.
        """
        settings = self.repl.settings(hunt=["Hamse", "Hamse", "Hamse"])
        answers = self.repl.picked(
            [pick(settings, index, "inHamse")
             for index in range(4)], self.readings())
        self.assertEqual(answers, ["nowhere"] * 4)

    def test_an_unreadable_location_panel_skips_nothing(self):
        """Absent evidence must not decide anything here.

        A reading with no location panel says nothing about where the ship is,
        and the safe direction is to ask as before: the ask is bounded, and a
        guard that skipped on silence would answer `nowhere` for every reading
        the panel failed to parse and strand a bot that had somewhere to go.
        """
        settings = self.repl.settings(hunt=CIRCUIT)
        answers = self.repl.picked(
            [pick(settings, index, "blind")
             for index in range(len(CIRCUIT))],
            [self.repl.reading_binding("blind", [])])
        self.assertEqual(answers, CIRCUIT)

    def test_the_client_s_own_padding_does_not_defeat_the_comparison(self):
        """The 2024-05-26 branch of the parser does not trim what it reads.

        Only the older `alt='Current Solar System'` variant does, so a name that
        arrives with the client's own whitespace around it has to be compared
        trimmed or the guard silently stops guarding.
        """
        [asked] = self.repl.picked(
            [pick(self.repl.settings(hunt=CIRCUIT), 0, "padded")],
            [self.repl.reading_binding("padded", [location_panel("  Hamse ")])])
        self.assertEqual(asked, "Lashkai")

    def test_no_circuit_configured_still_names_nowhere(self):
        """With no `hunt-system` the bot parks exactly as it did before the
        circuit existed, guard or no guard."""
        answers = self.repl.picked(
            [pick(self.repl.settings(), 0, "inHamse"),
             pick(self.repl.settings(), 0, "elsewhere"),
             # A staging system alone is not a circuit: with nothing to
             # exhaust, there is no lap to complete.
             pick(self.repl.settings(home="Hamse"), 0, "elsewhere")],
            self.readings())
        self.assertEqual(answers, ["nowhere"] * 3)


class TheTwoCallersNameTheSameDestinationTest(unittest.TestCase):
    """The constraint `nextHuntingGroundFrom`'s doc comment is written for.

    `updateMemoryForNewReadingFromGame` has to name the destination the decision
    will ask for, and it has the settings and the index but no
    `BotDecisionContext`. One picker is not enough on its own, because the
    framework hands the decision the memory this update has already written:
    the two are called with indices one apart on exactly the reading where the
    pointer moves, and that is the reading a dead-ended ship is most likely to
    be having.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HuntCircuitRepl)
        cls.source = collapsed(source_of(SAXRAT_BOT_ELM))

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_two_callers_answer_the_same_thing_on_the_reading_the_pointer_moves(self):
        """`index` and `index + 1`, over the arrival the pointer advances on.

        The memory update is handed the index from before the advance and the
        decision the index after it, so agreement is the property to assert
        rather than a single answer. Without the skip the two answer `Hamse` and
        `Lashkai`, which is `Sys Hamse -> Lashkai asked 'Hamse' 1/20` -- 21
        readings of it in the corpus.
        """
        plain = self.repl.settings(hunt=CIRCUIT)
        staging = self.repl.settings(hunt=CIRCUIT, home="Hamse")
        answers = self.repl.evaluate(
            ["%s == %s" % (pick(plain, 0, "inHamse"),
                           pick(plain, 1, "inHamse")),
             "%s == %s" % (pick(staging, len(CIRCUIT), "inHamse"),
                           pick(staging, len(CIRCUIT) + 1, "inHamse")),
             # The last entry of a lap, where the step also crosses into the
             # home-system fallback.
             "%s == %s" % (pick(staging, len(CIRCUIT) - 1, "inLast"),
                           pick(staging, len(CIRCUIT), "inLast"))],
            [self.repl.reading_binding("inHamse", [location_panel("Hamse")]),
             self.repl.reading_binding(
                 "inLast", [location_panel(CIRCUIT[-1])])])
        self.assertEqual(
            answers, [True] * 3,
            "the memory counts readings against a system the decision is not "
            "asking for, which is the drift the picker was split out to "
            "prevent")

    def test_both_callers_hand_it_the_same_three_things(self):
        """Read out of the source, because neither call site is an expression
        this suite can evaluate."""
        self.assertIn(
            "nextHuntingGround context = nextHuntingGroundFrom "
            "context.eventContext.botSettings context.memory.huntSystemIndex "
            "context.readingFromGameClient", self.source)
        self.assertIn(
            "nextHuntingGroundFrom context.botSettings "
            "botMemoryBefore.huntSystemIndex context.readingFromGameClient",
            self.source,
            "the memory update names the destination some other way than the "
            "decision does, so the counter and the ask can disagree again")

    def test_the_current_system_is_read_in_one_place(self):
        """Three readers of the same three `Maybe.andThen`s would drift, and a
        guard that read the panel differently from the pointer's own advance
        would skip systems the rotation never moves past."""
        self.assertEqual(
            1, self.source.count("|> Maybe.andThen .infoPanelLocationInfo |> "
                                 "Maybe.andThen .currentSolarSystemName"),
            "the current solar system is read from the panel in more than one "
            "place")
        self.assertIn(
            "currentSolarSystemName = currentSolarSystemNameFromReading "
            "context.readingFromGameClient", self.source,
            "the memory update reads the panel itself rather than through the "
            "reader the picker uses")


class TheSkipEndsSomewhereSafeTest(unittest.TestCase):
    """What the bot does when the guard has skipped everything.

    #257 shipped green and blocked the bot completely for 108 minutes, because
    a step on a decision path could decline forever and nothing in the suite
    said so. The answer here has to be an act, not a deferral.
    """

    @classmethod
    def setUpClass(cls):
        cls.branch = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                       "setRouteToNextHuntingGround"))

    def test_naming_nowhere_tethers_rather_than_waits(self):
        nowhere = self.branch[self.branch.index("Nothing ->"):]
        nowhere = nowhere[:nowhere.index("Just systemName ->")]
        self.assertIn("tetherAtStructure context", nowhere)
        self.assertNotIn(
            "waitForProgressInGame", nowhere,
            "a circuit with nowhere to go hands the reading back instead of "
            "acting, which is a bot that does nothing for the rest of the "
            "session")

    def test_the_operator_is_told_which_kind_of_nowhere_it_is(self):
        """`Nothing` used to mean only "no `hunt-system` configured". It now
        also means "everything on the circuit is this system", and a clause
        that names only the first would send an operator to look at a setting
        that is not the problem."""
        self.assertIn("no 'hunt-system'", self.branch)
        self.assertIn("already in", self.branch)

    def test_every_way_out_still_ends_somewhere_safe(self):
        self.assertEqual(
            2, self.branch.count("tetherAtStructure context"),
            "the give-up and the nowhere-to-go case must both fall back to the "
            "behaviour this bot had before the circuit existed")
        self.assertIn("hostDirectiveSetDestination systemName", self.branch)


class TheCorpusIsQuotedRatherThanRememberedTest(unittest.TestCase):
    """What the recorded runs actually say, which is not all of what #262 says.

    Two different claims live here and only the first is evidence for this
    change:

    - the two callers disagreeing, with the counter naming the system the ship
      is standing in. Recorded, in both wordings the status line has had;
    - the give-up latching. Also recorded -- and in none of the four runs that
      latched it did the bot ask for a route to the system it was in. Those
      cases are here because the latch's own premise is a separate defect that
      this change does not touch, and a recount is the only thing that keeps
      that distinction from being lost.
    """

    ASKED_CLAUSE = re.compile(
        r"Sys ([A-Za-z]+) -> ([A-Za-z]+) asked '([A-Za-z]+)' \d+/20")
    OLDER_ASKED_CLAUSE = re.compile(
        r"next ([A-Za-z]+)\. Asked for '([A-Za-z]+)' \d+/20")
    ASK = "Asking the host to set the destination to"
    GIVEN_UP = "this host does not set destinations"

    def lines_of(self, path):
        """One recorded run, a line at a time -- these files reach 76 MB."""
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                yield line

    def test_the_counter_names_the_system_the_ship_is_standing_in(self):
        """The disagreement, in the wording that prints both systems.

        `Sys Hamse -> Lashkai asked 'Hamse' 1/20`: the memory named the system
        under the ship while the decision asked for the next one.
        """
        standing = 0
        for path in saxrat_runs(41, 44, 46, 47):
            for line in self.lines_of(path):
                found = self.ASKED_CLAUSE.search(line)
                if found and found.group(1) == found.group(3):
                    standing += 1
        self.assertTrue(
            standing,
            "the runs that print the current system beside the ask no longer "
            "show the counter naming the system the ship is in, so the "
            "evidence this change rests on has changed shape")

    def test_the_older_wording_carries_the_same_disagreement(self):
        disagreements = 0
        for path in saxrat_runs(2, 3, 11, 16, 23, 29, 31, 32):
            for line in self.lines_of(path):
                found = self.OLDER_ASKED_CLAUSE.search(line)
                if found and found.group(1) != found.group(2):
                    disagreements += 1
        self.assertTrue(
            disagreements,
            "the recorded runs no longer show `next X. Asked for 'Y'`, which "
            "is the same drift in the wording that predates #242")

    def test_no_recorded_run_asks_for_the_system_the_ship_is_in(self):
        """Stated because #262 reads as though one does.

        The decision's own line names what it asked for. Across every recorded
        run, none of them names the system the status line says the ship is in
        -- the shape this change prevents is proved from the code, not from a
        recording, and saying otherwise would put weight on evidence that is
        not there.
        """
        asked_here = []
        for path in saxrat_runs(*range(38, 48)):
            current = None
            for line in self.lines_of(path):
                found = self.ASKED_CLAUSE.search(line)
                if found:
                    current = found.group(1)
                if current and self.ASK + " '%s'" % current in line:
                    asked_here.append((os.path.basename(path), current))
        self.assertEqual(
            [], asked_here,
            "a recorded run does ask for the system the ship is in, which is "
            "stronger evidence than this change was written on -- say so in "
            "the issue rather than leaving this case red")

    def test_the_latch_fired_in_runs_where_the_bot_never_asked(self):
        """The latch's premise, which this change does not repair.

        `destinationAskReadings` counts readings spent in a dead end, not asks
        issued, so it can reach `routeAskGiveUpReadings` on a bot that has
        never written a directive at all. Run 12 latched it having issued zero
        asks; runs 26 and 27 latched it with no `hunt-system` configured, where
        there was nothing the bot could have asked for. Recorded here so the
        separate issue this needs is not lost.
        """
        never_asked = []
        for path in saxrat_runs(12, 26, 27):
            gave_up = asked = False
            for line in self.lines_of(path):
                gave_up = gave_up or self.GIVEN_UP in line
                asked = asked or self.ASK in line
            if gave_up and not asked:
                never_asked.append(os.path.basename(path))
        self.assertTrue(
            never_asked,
            "the recorded runs no longer show the give-up latching without a "
            "single ask, so the counter may have been fixed -- check whether "
            "the follow-up issue is still open")


if __name__ == "__main__":
    unittest.main()
