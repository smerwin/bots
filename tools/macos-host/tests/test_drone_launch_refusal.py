"""Tests for the drone-launch ceiling, which the client states and the bot learns.

Issue #146, and the first decision either app has ever made on a quick message.
#123 shipped the logging on purpose and nothing read it; the corpus it produced
is what this is written against.

**The bug the corpus shows.** `launchAndEngageDrones` took the drones-in-space
group's title maximum as the number of drones it may have out. That is bandwidth
and bay, not the pilot's drone-control skill, and on this character the two
differ. saxrat's run 6 read `In bay: 3, in space: 5` on 17,919 readings, pressed
Shift+F 826 times, and was answered every time with `You cannot launch Hammerhead
I because you are already controlling 5 drones, as much as you have skill to.` --
1,316 of those refusals live on screen when a reading was taken, the single most
common thing the client said to either bot in that run. Mission run 37 shows the
same shape at 101 live, saxrat run 5 at 224. The bot could not tell the launch was
refused, so it pressed again on the next reading, all session.

**Counted live.** `on screen now` only. The clause carries a stale message
forward with an age until another replaces it, and the carried-forward totals are
three orders of magnitude larger and rank the wordings differently. The rule
itself refuses an aged sighting rather than trusting its callers to, and
`OnlyALiveSightingTeachesAnything` is that case.

**Per-message, never "a quick message means failure".** The vocabulary grows --
#92 records a word list the client outgrew twice unnoticed -- and this corpus
contains a message that means *success in progress* (`Cargo is too far away. Ship
is on automatic approach to cargo.`, the commonest message in the mission runner's
run 37 at 795 live) and a dozen that are pure narration (`Drones engaging ...`,
rat departures). `TheMatcherAdmitsOnlyTheLaunchRefusal` runs every one of the 108
distinct wordings the corpus holds through the shipped matcher and asserts which
two it admits.

**The near-miss that is already spoken for.** `You are already managing 6
targets, as many as you have skill to.` is #110's, read off the game log by
`maxTargetsStatedInGameLog`. Two rules reading each other's sentence would be two
wrong ceilings, so the exclusion is over-determined in both directions:
`controlling` is not `managing`, `much` is not `many`, and the count is sliced
after a clause the targeting sentence does not contain at all.

**Absent evidence never moves the limit**, which is the direction the whole rule
is built around: with nothing stated the ceiling is exactly the window's own
number, so a session in which the client never refuses a launch behaves as every
session did before this rule existed.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives, and the readings they are asked about go through the **real**
`EveOnline.ParseUserInterface` from a UI tree, so the sighting the matcher sees is
the one the bot would have been handed. Every rule is asked of **both** apps,
which carry the declarations identically and are compared byte for byte.

Nothing here reads a live game client, a running bot, or the game log directory.
The corpus cases read the recorded runs in `~/eve-bot-logs`, and only read them;
they skip with a stated reason on a machine that has none.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, open_repl
from test_quick_message_logged import (
    MISSION_RUNNER_BOT_ELM, SAXRAT_BOT_ELM, MissionRunnerRepl, SaxratRepl,
    collapsed, declaration, layer_abovemain, reading_binding, sighting,
    source_of, top_level_declarations)

APPS = (("saxrat", SAXRAT_BOT_ELM), ("mission runner", MISSION_RUNNER_BOT_ELM))

# The client's own sentence, byte for byte off the recorded runs, `<center>`
# wrapper and all -- that wrapper is on the quick-message channel and not on the
# game log, and a matcher that anchored on the start of the string would have
# been broken by it.
REFUSAL_ACOLYTE = ("<center>You cannot launch Acolyte I because you are already "
                   "controlling 5 drones, as much as you have skill to.")
REFUSAL_HAMMERHEAD = ("<center>You cannot launch Hammerhead I because you are "
                      "already controlling 5 drones, as much as you have skill "
                      "to.")

# What the client says its skill allows, in every recorded sighting of both
# wordings.
CLIENT_MAXIMUM = 5

# #110's sentence. Same shape to within two words, about something else, and
# already consumed by `maxTargetsStatedInGameLog` off the game log.
TARGETS_SENTENCE = ("<center>You are already managing 6 targets, as many as you "
                    "have skill to.")

# The message this rule most has to decline, and the reason a general "a quick
# message means failure" rule would be wrong: the client is confirming it took
# the command and is flying there. 795 live in mission run 37, the commonest
# message in either bot.
AUTOMATIC_APPROACH = ("<center>Cargo is too far away. Ship is on automatic "
                      "approach to cargo.")

# Four more from the corpus that a looser matcher could plausibly reach: two
# about drones, one narration, one a refusal that names no capacity.
OTHER_DRONE_MESSAGES = [
    "<center>Drone cannot be commanded as it is not actually present.",
    "<center>Acolyte I cannot be dropped because it is not in your drone bay.",
    "<center>Drones engaging Tower Sentry Sansha I",
    "<center>The drones fail to execute your commands as the target Deadspace "
    "Sansha's Nation Frigate is not within your 60000.0 m drone command range.",
]

# The declarations both apps carry identically. A port that keeps one and drops
# another is what `BothAppsCarryTheSameRule` refuses.
SHARED_DECLARATIONS = (
    "droneLaunchRefusedMarker",
    "droneLaunchSkillMarker",
    "droneLaunchRefusalStatedInQuickMessage",
    "droneLaunchCountInStatement",
    "droneLaunchStateFrom",
    "droneLaunchLimitWithoutATitle",
    "dronesInSpaceLimitFromWindow",
    "droneLaunchCeiling",
    "updateDroneLaunchLearning",
    "describeDroneLaunchCeiling",
)

# Where the popup text sits in a status line, either form of the clause. Used
# only by the corpus cases, to recover the wordings the runs recorded.
RECORDED_QUICK_MESSAGE = re.compile(
    r'Quick message \((?:on screen now|NOT on screen now[^)]*)\): "(.*)"\.\s*$')
LIVE_QUICK_MESSAGE = re.compile(r'Quick message \(on screen now\): "(.*)"\.\s*$')


def state(from_window, stated=None):
    """A `DroneLaunchState`, written the way the repl wants it."""
    return ("{ fromWindow = %d, statedByClient = %s }"
            % (from_window,
               "Nothing" if stated is None else "Just %d" % stated))


def learning(on_screen_now, stated_before=None):
    """The record `updateDroneLaunchLearning` takes."""
    return ("{ onScreenNow = %s, statedBefore = %s }"
            % (on_screen_now,
               "Nothing" if stated_before is None else "Just %d"
               % stated_before))


class BothAppsRepl:
    """One repl per app, so every rule below is asked of both."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {"saxrat": open_repl(SaxratRepl),
                     "mission runner": open_repl(MissionRunnerRepl)}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        """`(app, answers)` for every app, so a failure names which one."""
        for app, repl in self.repls.items():
            yield app, repl.evaluate(expressions, definitions)


class TheRealParserHandsTheRuleTheClientsSentence(
        BothAppsRepl, unittest.TestCase):
    """Both diverged parsers, asked first.

    The two apps vendor separate copies of `EveOnline/ParseUserInterface.elm`, so
    whether a `QuickMessage` node reaches `quickMessageOnScreen` with the text
    intact is a question about that app. Every case below would otherwise pass or
    fail for reasons that have nothing to do with the rule.
    """

    def test_a_real_ui_tree_reaches_the_matcher_with_the_count_intact(self):
        for app, answers in self.each(
                ["(refusal |> Maybe.andThen quickMessageOnScreen"
                 " |> Maybe.map .text) == Just " + json.dumps(REFUSAL_ACOLYTE),
                 "(refusal |> Maybe.andThen quickMessageOnScreen"
                 " |> droneLaunchRefusalStatedInQuickMessage) == Just %d"
                 % CLIENT_MAXIMUM],
                definitions=[reading_binding(
                    "refusal", [layer_abovemain([[REFUSAL_ACOLYTE]])])]):
            self.assertEqual(
                answers, [True] * 2,
                "%s's parser does not carry the refusal as far as the rule, so "
                "nothing below would mean anything" % app)

    def test_a_reading_with_no_popup_states_nothing(self):
        """`Nothing` from the layer is a quiet screen and must never read as the
        client having stated a cap."""
        for app, answers in self.each(
                ["(quiet |> Maybe.andThen quickMessageOnScreen"
                 " |> droneLaunchRefusalStatedInQuickMessage) == Nothing"],
                definitions=[reading_binding("quiet", [])]):
            self.assertEqual(
                answers, [True],
                "%s reads a reading with no popup as a stated cap" % app)


class OnlyALiveSightingTeachesAnything(BothAppsRepl, unittest.TestCase):
    """The trap #146 names, refused inside the rule rather than at its callers.

    The sighting is carried forward with an age until another message replaces
    it, so the refusal that ended one fight is still in memory while the ship is
    docked and restocking. Counting carried-forward sightings gives totals three
    orders of magnitude larger than the live ones, in a different order.
    """

    def test_the_reading_it_is_seen_on_teaches_the_count(self):
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Just %d"
                 % (sighting(REFUSAL_ACOLYTE, readings_since=0),
                    CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True],
                "%s does not learn the cap from the reading the client stated "
                "it, which is the only reading that carries it" % app)

    def test_an_aged_sighting_teaches_nothing_at_any_age(self):
        """Ages either side of a boundary would pass for any boundary, so this
        asks about fixed ages including the smallest one that is not live."""
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Nothing"
                 % sighting(REFUSAL_ACOLYTE, readings_since=age)
                 for age in (1, 2, 12, 210, 3000)]):
            self.assertEqual(
                answers, [True] * 5,
                "%s learns a drone cap from a popup that is no longer on the "
                "screen, so a refusal from before the last dock still binds the "
                "launch site" % app)

    def test_the_whole_session_of_a_single_popup_is_one_statement(self):
        """1,316 live sightings against 215 refusals in saxrat run 6's own game
        log: the same popup sits on screen for several readings, and every
        reading after the first states a number already held.
        """
        first = learning("Just " + sighting(REFUSAL_ACOLYTE), None)
        again = learning("Just " + sighting(REFUSAL_ACOLYTE), CLIENT_MAXIMUM)
        for app, answers in self.each(
                ["(updateDroneLaunchLearning %s).change /= Nothing" % first,
                 "(updateDroneLaunchLearning %s).change == Nothing" % again,
                 "(updateDroneLaunchLearning %s).statedByClient == Just %d"
                 % (again, CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s reports a change on every reading a popup lingers" % app)


class TheMatcherAdmitsOnlyTheLaunchRefusal(BothAppsRepl, unittest.TestCase):
    """Which wordings get in, asked of the literals rather than argued about.

    `briefingSaysClearingIsOptional` was checked against all 46 recorded
    briefings and #151's target matcher against the drone sentence three ways;
    this is that discipline applied to the quick-message channel, whose corpus is
    108 distinct wordings.
    """

    def test_both_recorded_launch_refusals_are_admitted(self):
        """The drone's name varies with what is in the bay, and nothing in the
        matcher reads it -- which is what makes `Hammerhead I` work without ever
        having been seen when the markers were chosen."""
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Just %d"
                 % (sighting(text), CLIENT_MAXIMUM)
                 for text in (REFUSAL_ACOLYTE, REFUSAL_HAMMERHEAD)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s does not read one of the two wordings the corpus holds, so "
                "a session flying the other drone learns nothing" % app)

    def test_the_targets_sentence_is_declined(self):
        """#110's, and already consumed off the game log. Reading it here would
        cap this ship's drones at its lock slots, and #151's matcher declines
        the mirror image of the same mistake.
        """
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Nothing"
                 % sighting(TARGETS_SENTENCE),
                 "droneLaunchCountInStatement %s == Nothing"
                 % json.dumps(TARGETS_SENTENCE)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s reads the lock-slot statement as a drone cap, which is "
                "#151's exclusion run backwards" % app)

    def test_the_automatic_approach_message_is_not_a_refusal(self):
        """The commonest message in either bot and *not* a failure: the client
        is confirming it took the command and is flying there. A rule that read
        it as a refusal would be wrong about 795 readings of run 37 alone.
        """
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Nothing"
                 % sighting(AUTOMATIC_APPROACH),
                 "(updateDroneLaunchLearning %s).statedByClient == Nothing"
                 % learning("Just " + sighting(AUTOMATIC_APPROACH))]):
            self.assertEqual(
                answers, [True] * 2,
                "%s treats the client's confirmation that it is already "
                "approaching as a refusal, which is the trap #146 names by name"
                % app)

    def test_the_other_drone_messages_state_no_cap(self):
        for app, answers in self.each(
                ["droneLaunchRefusalStatedInQuickMessage (Just %s) == Nothing"
                 % sighting(text) for text in OTHER_DRONE_MESSAGES]):
            self.assertEqual(
                answers, [True] * len(OTHER_DRONE_MESSAGES),
                "%s reads a drone message that names no capacity as one that "
                "does" % app)

    def test_a_sentence_naming_no_number_teaches_nothing(self):
        """Both markers present and no count in between is the client having
        reworded past the slice, which is not a reason to move anything."""
        reworded = ("<center>You cannot launch Acolyte I because you are "
                    "already controlling as many drones as you have skill to.")
        marked_up = ("<center>You cannot launch Acolyte I because you are "
                     "already controlling <b>5</b> drones, as much as you have "
                     "skill to.")
        for app, answers in self.each(
                ["droneLaunchCountInStatement %s == Nothing"
                 % json.dumps(text) for text in (reworded, marked_up)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s takes a default from a sentence it cannot read a number "
                "out of" % app)

    def test_the_number_belongs_to_the_clause_that_was_matched(self):
        """Sliced after `droneLaunchRefusedMarker` rather than taken as the first
        integer in the sentence, so a client that puts a number earlier -- in a
        drone's own name, which is client text this rule does not control --
        cannot hand this a count of something else.
        """
        prefixed = ("<center>You cannot launch Hobgoblin 2 because you are "
                    "already controlling 5 drones, as much as you have skill "
                    "to.")
        for app, answers in self.each(
                ["droneLaunchCountInStatement %s == Just %d"
                 % (json.dumps(prefixed), CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True],
                "%s takes the first integer in the line rather than the count "
                "the matched clause is about" % app)


class TheCeilingTakesTheLowerOfTwoRealBounds(BothAppsRepl, unittest.TestCase):
    """Both numbers are read off the client, which is why this is `min`.

    Unlike `maxTargetsCeiling`, neither half here is a guess an operator typed:
    the window's maximum is bandwidth and bay, the client's sentence is the
    drone-control skill, and the lower of two real bounds is the one that binds.
    """

    def test_with_nothing_stated_the_window_stands_exactly_as_it_did(self):
        """The direction the whole rule is built around. Fixed values rather
        than a pair either side of a boundary, which is the hole CLAUDE.md
        records four of #120's cases having.
        """
        for app, answers in self.each(
                ["droneLaunchCeiling %s == %d" % (state(window), window)
                 for window in (0, 1, 2, 5, 8, 10, 23)]):
            self.assertEqual(
                answers, [True] * 7,
                "%s no longer leaves the drones window's own number alone where "
                "the client has said nothing, so a session that hears no "
                "refusal has had its launch site changed" % app)

    def test_a_stated_cap_below_the_window_binds(self):
        """The corpus's own correction: a window offering more than five while
        the client refuses every launch above five."""
        for app, answers in self.each(
                ["droneLaunchCeiling %s == %d"
                 % (state(window, stated=CLIENT_MAXIMUM), CLIENT_MAXIMUM)
                 for window in (8, 10, 6)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s keeps launching against a maximum the client has "
                "contradicted, which is the 826 presses of run 6" % app)

    def test_a_stated_cap_above_the_window_raises_nothing(self):
        """A skill allowing eight does not give this ship the bandwidth for
        eight, so a statement above the window is not permission."""
        for app, answers in self.each(
                ["droneLaunchCeiling %s == 3" % state(3, stated=8),
                 "droneLaunchCeiling %s == 5" % state(5, stated=5)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s lets a stated skill cap raise the launch site above what "
                "the drones window itself offers" % app)

    def test_the_latest_statement_wins_rather_than_the_smallest(self):
        """A drone skill completing mid-session moves the cap up, and a rule
        that kept the smallest could never follow it."""
        raised = REFUSAL_ACOLYTE.replace("controlling 5", "controlling 6")
        session = ("(updateDroneLaunchLearning %s).statedByClient"
                   % learning("Just " + sighting(raised), CLIENT_MAXIMUM))
        for app, answers in self.each(
                ["%s == Just 6" % session]):
            self.assertEqual(
                answers, [True],
                "%s cannot follow the client's answer upwards, so a skill that "
                "finishes mid-session leaves the ship a drone short" % app)


class TheChangeIsSaidOnceAndNamesTheNumber(BothAppsRepl, unittest.TestCase):
    """The decision-log line, which is the only record a run keeps of the move."""

    def test_the_sentence_names_the_count_and_where_it_came_from(self):
        for app, repl in self.repls.items():
            [said] = repl.strings(
                ["(updateDroneLaunchLearning %s).change "
                 "|> Maybe.withDefault \"none\""
                 % learning("Just " + sighting(REFUSAL_ACOLYTE))])
            self.assertIn("Learned drone launch ceiling", said, app)
            self.assertIn("already controlling 5 drones", said, app)
            self.assertIn("drones window", said, app)

    def test_a_reading_that_moves_nothing_says_nothing(self):
        for app, answers in self.each(
                ["(updateDroneLaunchLearning %s).change == Nothing"
                 % learning("Nothing"),
                 "(updateDroneLaunchLearning %s).change == Nothing"
                 % learning("Nothing", CLIENT_MAXIMUM),
                 "(updateDroneLaunchLearning %s).change == Nothing"
                 % learning("Just " + sighting(AUTOMATIC_APPROACH),
                            CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 3,
                "%s reports a change on a reading that moved nothing" % app)

    def test_a_quiet_reading_keeps_what_was_learned(self):
        for app, answers in self.each(
                ["(updateDroneLaunchLearning %s).statedByClient == Just %d"
                 % (learning("Nothing", CLIENT_MAXIMUM), CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True],
                "%s forgets the cap on the next quiet reading, so the launch "
                "site is refused again on every fight" % app)


class TheStatusLineSaysWhereTheCeilingCameFrom(
        BothAppsRepl, unittest.TestCase):
    """Both halves named separately, because they fail differently.

    A run whose `client stated` never leaves `-` is one whose popups are not
    reaching the rule; a window number that never drops below the ceiling is a
    ship whose skill was not the binding constraint. A clause carrying only the
    answer would leave those two grepping the same, which is #123's argument.
    """

    def test_the_clause_carries_the_answer_and_both_halves(self):
        for app, repl in self.repls.items():
            said = repl.strings(
                ["describeDroneLaunchCeiling %s" % state(8),
                 "describeDroneLaunchCeiling %s"
                 % state(8, stated=CLIENT_MAXIMUM)])
            self.assertEqual(
                said[0],
                "Drone launch ceiling: 8 (drones window says 8, client stated "
                "-).", app)
            self.assertEqual(
                said[1],
                "Drone launch ceiling: 5 (drones window says 8, client stated "
                "5).", app)


class TheWiringIsWhatMakesAnyOfThisReachable(unittest.TestCase):
    """Read out of the source, since none of it is an expression.

    A rule that answers correctly and is never asked is this repo's signature
    bug, and #34, #42 and #102 are three of it.
    """

    def test_neither_launch_site_reads_the_window_maximum_directly_any_more(self):
        for app, path in APPS:
            body = collapsed(declaration(source_of(path),
                                         "launchAndEngageDrones"))
            self.assertIn(
                "dronesInSpaceQuantityLimit = droneLaunchCeiling "
                "(droneLaunchStateFrom context)", body,
                "%s's launch site does not consult the learned ceiling" % app)
            self.assertNotIn(
                "Maybe.andThen .maximum", body,
                "%s's launch site still reaches for the drones window's "
                "maximum itself, so the learned cap can be bypassed" % app)

    def test_the_window_maximum_is_read_in_one_place_per_app(self):
        """Two places asking the window directly would be two opinions about the
        ceiling, which is how `weaponModuleButtonsLeftToRight` came to exist."""
        for app, path in APPS:
            declarations = top_level_declarations(source_of(path))
            readers = sorted(
                name for name, body in declarations.items()
                if "Maybe.andThen .maximum" in collapsed(body))
            self.assertEqual(
                readers, ["dronesInSpaceLimitFromWindow"],
                "%s reads the drones window's maximum from %r rather than only "
                "from the declaration that owns it" % (app, readers))

    def test_the_memory_update_is_what_writes_the_verdict(self):
        for app, path in APPS:
            body = collapsed(declaration(source_of(path),
                                         "updateMemoryForNewReadingFromGame"))
            self.assertIn("updateDroneLaunchLearning", body, app)
            self.assertIn(
                "onScreenNow = quickMessageOnScreen "
                "context.readingFromGameClient", body,
                "%s feeds the rule something other than the sighting on this "
                "reading" % app)
            self.assertIn(
                "statedBefore = botMemoryBefore.droneLaunchRefusedAbove", body,
                app)
            for field in ("droneLaunchRefusedAbove = droneLaunchLearning"
                          ".statedByClient",
                          "droneLaunchLastChange = droneLaunchLearning.change"):
                self.assertIn(
                    field, body,
                    "%s writes a drone-launch field from something other than "
                    "the rule's own answer" % app)

    def test_the_rule_never_reads_the_carried_forward_message(self):
        """The one wiring mistake that would be silent.

        `memory.quickMessage` is the aged sighting and `quickMessageOnScreen` is
        this reading's. Both type-check where the rule is called, and a run wired
        to the first would learn a cap from a popup shown before the last dock.
        """
        for app, path in APPS:
            source = source_of(path)
            for name in ("updateDroneLaunchLearning",
                         "droneLaunchRefusalStatedInQuickMessage",
                         "droneLaunchStateFrom", "droneLaunchCeiling"):
                self.assertNotIn(
                    ".quickMessage", collapsed(declaration(source, name)),
                    "%s: %s reaches for the carried-forward sighting"
                    % (app, name))

    def test_the_change_is_announced_at_the_root(self):
        """Settled in the memory update, which runs whatever the bot is doing, so
        the branch that learned it is not reliably the branch being evaluated --
        `maxTargetsLastChange`'s placement for its reason."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            self.assertIn(
                "context.memory.maxTargetsLastChange , context.memory"
                ".droneLaunchLastChange", source,
                "%s does not announce the move beside the other verdicts at the "
                "root, where nothing can decline to print it" % app)

    # The clause as a *term* of each app's own status expression, not merely a
    # name appearing somewhere in the file. Asserting the substring is the hole
    # #109 records finding twice: a version that still names the renderer while
    # answering nothing for it prints nothing and passes.
    STATUS_TERMS = {
        "saxrat":
            "++ describeDroneLaunchCeiling (droneLaunchStateFrom context) ++",
        "mission runner":
            ", describeDroneLaunchCeiling (droneLaunchStateFrom context) ]",
    }

    def test_the_status_line_carries_the_clause(self):
        for app, path in APPS:
            self.assertIn(
                self.STATUS_TERMS[app], collapsed(source_of(path)),
                "%s does not report the launch ceiling on every reading, so a "
                "run that never learned one and a run whose clause was "
                "neutralised grep the same" % app)

    def test_the_rules_are_functions_of_records_so_a_case_can_run_them(self):
        """#106 records what the other shape costs: a rule reachable only through
        a whole `BotDecisionContext` can be checked by reading it and in no other
        way."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            for signature in (
                    "droneLaunchCeiling : DroneLaunchState -> Int",
                    "describeDroneLaunchCeiling : DroneLaunchState -> String",
                    "droneLaunchRefusalStatedInQuickMessage : "
                    "Maybe QuickMessageSighting -> Maybe Int",
                    "droneLaunchCountInStatement : String -> Maybe Int"):
                self.assertIn(
                    signature, source,
                    "%s: %s takes a context, so it can no longer be executed by "
                    "a case" % (app, signature.split(" :")[0]))


class BothAppsCarryTheSameRule(unittest.TestCase):
    """Compared byte for byte, the way #123's quick-message rules are.

    The two apps meet the same client and the same sentence, so a fix that lands
    in one copy while the other silently lacks it is its own bug -- and the
    failure would be quiet, since a ceiling that never moves reads exactly like a
    client that never spoke.
    """

    def test_every_shared_declaration_is_identical(self):
        saxrat = source_of(SAXRAT_BOT_ELM)
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        for name in SHARED_DECLARATIONS:
            self.assertEqual(
                declaration(saxrat, name), declaration(mission, name),
                "%s has drifted between the two apps" % name)


class TheLockSlotRuleIsUntouched(unittest.TestCase):
    """#110's rule, which reads the neighbouring sentence and must keep doing so.

    The targeting statement arrives on both channels, and #149 chose the game log
    for it deliberately. This change reads a different sentence on a different
    channel and must not double-read that one or weaken the exclusion that keeps
    the two apart.
    """

    def test_the_targeting_rule_still_reads_only_the_game_log(self):
        for app, path in APPS:
            body = collapsed(declaration(source_of(path),
                                         "maxTargetsStatedInGameLog"))
            self.assertIn("gameLogEntryIsFromNotifyChannel", body, app)
            self.assertNotIn(
                "uickMessage", body,
                "%s now reads the lock-slot statement off the popup as well as "
                "the game log, so one refusal would be counted twice" % app)

    def test_this_rule_reads_no_game_log_at_all(self):
        for app, path in APPS:
            for name in ("droneLaunchRefusalStatedInQuickMessage",
                         "updateDroneLaunchLearning", "droneLaunchCeiling"):
                body = collapsed(declaration(source_of(path), name))
                self.assertNotIn("gameLog", body,
                                 "%s: %s reaches for the game log" % (app, name))

    def test_the_two_markers_still_disagree_in_both_directions(self):
        for app, path in APPS:
            source = source_of(path)
            self.assertIn('"as many as you have skill to"', source,
                          "%s: the targeting marker is gone" % app)
            self.assertIn('"as much as you have skill to"', source,
                          "%s: the drone marker is gone" % app)
            self.assertIn('"already managing"', source,
                          "%s: the targeting clause is gone" % app)
            self.assertIn('"already controlling"', source,
                          "%s: the drone clause is gone" % app)


class WhatTheRecordedRunsSay(unittest.TestCase):
    """The corpus, asked the questions it bears on.

    Asserted as *relations* rather than as counts wherever a growing corpus could
    turn a true claim red.
    """

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(EVE_BOT_LOGS):
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what the client has "
                "said to these bots cannot be consulted here")
        logs = sorted(name for name in os.listdir(EVE_BOT_LOGS)
                      if name.endswith(".log"))
        if not logs:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what the client has "
                "said to these bots cannot be consulted here")

        # Every distinct wording the runs recorded, live or carried forward,
        # because the matcher has to be checked against the whole vocabulary and
        # not only the part of it that happened to be live.
        cls.wordings = set()
        # Live sightings only, per wording -- the count #146 insists on.
        cls.live = {}
        # `Launch drones` decisions, and how many of them were taken on a
        # reading the refusal was already on the screen.
        cls.launch_decisions = 0
        cls.launch_after_a_live_refusal = 0
        for name in logs:
            refusal_live = False
            with open(os.path.join(EVE_BOT_LOGS, name),
                      encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    stripped = line.rstrip("\n")
                    recorded = RECORDED_QUICK_MESSAGE.search(stripped)
                    if recorded is not None:
                        cls.wordings.add(recorded.group(1))
                    seen_live = LIVE_QUICK_MESSAGE.search(stripped)
                    if seen_live is not None:
                        text = seen_live.group(1)
                        cls.live[text] = cls.live.get(text, 0) + 1
                        refusal_live = "already controlling" in text
                    elif "Quick message" in stripped:
                        refusal_live = False
                    if stripped.endswith("Launch drones"):
                        cls.launch_decisions += 1
                        if refusal_live:
                            cls.launch_after_a_live_refusal += 1
        if not cls.wordings:
            raise unittest.SkipTest(
                "no recorded runs carry a quick message, so there is no "
                "vocabulary here to check the matcher against")

    def refusals(self):
        return [text for text in self.wordings
                if "already controlling" in text and "drones" in text]

    def test_the_refusal_really_occurs_and_names_more_than_one_drone(self):
        """The whole argument for the change, recounted rather than remembered --
        and the reason nothing in the matcher reads the drone's name."""
        found = self.refusals()
        self.assertTrue(
            found,
            "no recorded run carries the drone-launch refusal, so this matcher "
            "is keyed on a sentence this client does not write")
        names = {re.search(r"cannot launch (.+?) because", text).group(1)
                 for text in found
                 if re.search(r"cannot launch (.+?) because", text)}
        self.assertGreater(
            len(names), 1,
            "every recorded refusal names the same drone (%r), so a matcher "
            "that keyed on the name would have looked correct" % sorted(names))

    def test_the_shipped_matcher_reads_every_recorded_refusal(self):
        """The literals are read out of `Bot.elm` and run against the client's
        own recorded lines, so a matcher that drifts from what the client writes
        fails here rather than in a run."""
        source = source_of(SAXRAT_BOT_ELM)
        markers = [
            re.search(r'^%s :\s*String\s*\n%s =\s*\n\s*"([^"]*)"'
                      % (name, name), source, re.MULTILINE)
            for name in ("droneLaunchRefusedMarker", "droneLaunchSkillMarker")]
        self.assertTrue(all(markers), "the markers are no longer plain literals")
        clause, skill = (match.group(1) for match in markers)
        for text in self.refusals():
            lowered = text.lower()
            self.assertIn(clause, lowered, text)
            self.assertIn(skill, lowered, text)
            after = lowered.split(clause)[1].split()
            self.assertEqual(
                int(after[0]), CLIENT_MAXIMUM,
                "the shipped slice does not recover the count from %r" % text)

    def test_the_matcher_admits_nothing_else_the_client_has_ever_said(self):
        """Every distinct wording in the corpus, run through the shipped
        markers. This is `briefingSaysClearingIsOptional` against all 46
        briefings, applied to a channel with a much larger vocabulary -- and it
        is what a claim about what the matcher excludes has to rest on.
        """
        source = source_of(SAXRAT_BOT_ELM)
        clause, skill = (
            re.search(r'^%s :\s*String\s*\n%s =\s*\n\s*"([^"]*)"'
                      % (name, name), source, re.MULTILINE).group(1)
            for name in ("droneLaunchRefusedMarker", "droneLaunchSkillMarker"))
        admitted = sorted(
            text for text in self.wordings
            if clause in text.lower() and skill in text.lower())
        self.assertEqual(
            admitted, sorted(self.refusals()),
            "the shipped markers admit a wording that is not a launch refusal, "
            "out of the %d the corpus holds" % len(self.wordings))

    def test_the_message_that_means_success_is_among_the_ones_it_declines(self):
        """`Cargo is too far away. Ship is on automatic approach to cargo.` is
        the client saying it *took* the command. It is in this corpus, it is the
        commonest thing in it, and the matcher has to be measured against it
        rather than merely intended to decline it.
        """
        approaches = [text for text in self.wordings
                      if "automatic approach" in text]
        self.assertTrue(
            approaches,
            "the corpus no longer carries the automatic-approach message, so "
            "the case that this rule declines it guards against nothing")
        source = source_of(SAXRAT_BOT_ELM)
        clause = re.search(
            r'^droneLaunchRefusedMarker :\s*String\s*\n'
            r'droneLaunchRefusedMarker =\s*\n\s*"([^"]*)"',
            source, re.MULTILINE).group(1)
        for text in approaches:
            self.assertNotIn(clause, text.lower(), text)

    def test_the_bot_pressed_launch_again_after_being_refused(self):
        """The half that decides whether reading this saves readings or merely
        explains them: a refusal followed by another launch is a retry the rule
        now prevents.

        Asserted as "it happened at all", since a later run flying this rule
        should drive the number down and must not turn the claim red.
        """
        self.assertGreater(
            self.launch_decisions, 0,
            "no recorded run reaches the launch site, so nothing here says what "
            "the client answered it")
        self.assertGreater(
            self.launch_after_a_live_refusal, 0,
            "no recorded run pressed a launch on a reading whose screen already "
            "carried the refusal, which is the retry loop this change exists to "
            "end")
