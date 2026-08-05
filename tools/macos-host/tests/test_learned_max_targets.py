"""Tests for the lock-slot ceiling, which the client states and the bot learns.

`maxTargetCount = 4` was hardcoded in both apps -- a field in `BotSettings` with
no setting able to reach it -- and the real number on this character is **6**.
saxrat paid for that on 2,149 readings across its runs 2 to 5, printing
`Enough locked targets.` with two lock slots sitting unused; the mission runner
paid silently, since its `List.take` says nothing.

**The client answers the question itself, and it had been answering all along.**
`You are already managing 6 targets, as many as you have skill to.` arrives on
`(notify)` -- the channel `loadRefusalFromGameLog` already reads -- 228 distinct
entries across the recorded runs of both apps and 491 across the client's own
game logs, where it reads **5** for about ninety minutes on 31 July 2026 and 6
before and since. So the number is not a constant even for one character, which
is the argument against a constant.

Two halves, and they fail differently, so the cases pin them separately:

- **The floor** is the target bar holding N, which needs no attribution at all
  and cannot be a misread of somebody else's overview row. It only ever rises.
- **The stated maximum** is the client's own sentence. It can move either way,
  and `TheClientsSentenceIsNotTheDroneOne` is the case that matters most for it:
  the client writes a refusal of exactly this shape about *drones* -- `You cannot
  launch Acolyte I because you are already controlling 5 drones, as much as you
  have skill to.`, 188 live sightings in saxrat's run 5 against 40 of the
  targeting one -- and reading that as a lock ceiling would cap this ship at five
  targets on a reading that said nothing about targeting.

**Absent evidence must never raise the ceiling**, which is the direction the
whole rule is built around and the one
`TheSettingStandsExactlyWhereNothingIsKnown` exists for. A ceiling raised on a
guess makes the bot spend readings asking for locks the client will never grant,
and nothing would teach it back down: the bot learns only from what the client
grants, and a slot that does not exist grants nothing. That is
`loadRefusalFromGameLog`'s register applied to a ceiling.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python, for the reason CLAUDE.md's "How a change is verified here"
gives, and the game-log entries they are asked about come from the **real**
`EveOnline.ParseUserInterface` -- which is also what makes these cases evidence
that saxrat's diverged copy of that parser carries the channel this reads.

Every rule is asked of **both** apps, because the two carry the same declarations
under the same names and a case compares them byte for byte. The wiring and the
placement -- which are not expressions and cannot be evaluated -- are read out of
the source through a whitespace-collapsing reader, so an `elm-format` pass cannot
break them.

Confirmed by mutation, **sixteen** of them, each failing a named case: the
ceiling raised on absent evidence (the mutation this whole design refuses), the
stated maximum clamped so it can never rise above the setting, the proven floor
allowed to fall with the bar, an empty bar recorded as a floor of zero, the
number taken as the first integer anywhere in the line, the whole matcher
replaced by the naive one (keyed on `skill to`, first integer in the line), the
channel filter dropped, a sentence the slice cannot read taking a default, the
stated maximum taking the largest rather than the latest, `max-targets` moved off
`AppSettings.valueTypeInteger` so an empty value silently leaves 4, each app's
decision site reading the raw setting again, the move no longer announced at the
root, the status clause neutralised, and -- against the neighbouring rule this
must not weaken -- `overviewEntryLockHandle`'s same-name exclusion loosened,
which fails both a case here and `test_saxrat_learned_lock_range.RowIdentityTest`.

**Two mutations survived the first pass and one was a real hole.** Neutralising
the status clause with `|> always ""` left the renderer's name in the source, so
a substring assertion passed while the clause printed nothing -- the hole #109
records finding twice, on the other bot. The case now pins the clause as a *term*
of each app's own status expression. The other survivor was the mutation's fault
rather than the case's: it renamed the setting rather than changing its value
type, so the empty value was still refused.

**And the drone refusal turned out to be excluded three times over**, which is
worth writing down because it was expected to be excluded once. `controlling`
is not `managing`, `much` is not `many`, and the slice after
`maxTargetsStatedMarker` lands on a word rather than a digit -- so no single
loosening admits it, and the mutation that does is the naive matcher with all
three gone.

Nothing here reads a live game client or a running bot. The corpus cases read
the recorded runs in `~/eve-bot-logs`, and only read them; they skip with a
stated reason on a machine that has none, which is the answer an absent piece of
*evidence* gets rather than the one an absent toolchain does.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import EVE_BOT_LOGS, REPO_DIR, ElmRepl, open_repl
from test_saxrat_ported_guards import (
    PREAMBLE, SAXRAT_BOT_ELM, SaxratRepl, body_of, collapsed, game_log,
    source_of)

MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")

# The client's own sentence, byte for byte off the recorded runs. Both numbers
# occur: 6 throughout the bot corpus, and 5 for about ninety minutes on
# 31 July 2026 in the client's own logs, which is a targeting skill completing.
STATED_SIX = "You are already managing 6 targets, as many as you have skill to."
STATED_FIVE = "You are already managing 5 targets, as many as you have skill to."

# The near-miss. Same shape, same closing clause to within one word, and about
# something else entirely -- the case `maxTargetsSkillMarker` documents.
DRONE_REFUSAL = ("You cannot launch Acolyte I because you are already "
                 "controlling 5 drones, as much as you have skill to.")

# Two more real targeting failures from the recorded runs, neither of which
# states a capacity. A matcher that admitted either would be learning a ceiling
# from a rat that died.
OTHER_TARGETING_FAILURES = [
    "Targeting attempt failed as the designated object is no longer present.",
    "Interference from Centii Scavenger's warp prevents your sensors from "
    "locking the target.",
]

# The shipped ceiling, and the number the client actually states.
SHIPPED_DEFAULT = 4
CLIENT_MAXIMUM = 6

APPS = (("saxrat", SAXRAT_BOT_ELM), ("mission runner", MISSION_RUNNER_BOT_ELM))

# The declarations both apps carry identically. A port that keeps one and drops
# another is what `BothAppsCarryTheSameRule` refuses.
SHARED_DECLARATIONS = (
    "maxTargetsCeiling",
    "maxTargetsStatedInGameLog",
    "maxTargetsInStatement",
    "updateMaxTargetsLearning",
    "describeMaxTargets",
    "maxTargetsStatedMarker",
    "maxTargetsSkillMarker",
)


class MaxTargetsRepl(ElmRepl):
    """The mission runner's own `Bot.elm`, plus the bindings these cases need.

    It takes saxrat's preamble rather than the default one because the readings
    here go through the **real** `EveOnline.ParseUserInterface`, which the
    default preamble does not import -- and a case built on a tree the parser
    silently makes nothing of would pass or fail for reasons that have nothing
    to do with the rule.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    HELPERS = [
        # One reading, as the rule takes it, with no game log at all.
        "quietReading = \\targets ->"
        " { targetsCount = targets, gameLogEntries = [] }",
        # The rule's own answer folded back into its own input, so a case can
        # run a session rather than one reading.
        "step = \\reading state ->"
        " let learned = updateMaxTargetsLearning reading state in"
        " { fromSetting = state.fromSetting"
        " , statedByClient = learned.statedByClient"
        " , heldAtOnce = learned.heldAtOnce }",
        "changeOf = \\reading state ->"
        " (updateMaxTargetsLearning reading state).change",
        "nothingKnown = \\setting ->"
        " { fromSetting = setting, statedByClient = Nothing"
        " , heldAtOnce = Nothing }",
        # The entries of a really parsed reading, which is what the rule is
        # asked about wherever the parser's own shape is part of the claim.
        "entriesOf = \\parsed -> parsed"
        " |> Maybe.andThen .gameLogEntriesSinceLastReading"
        " |> Maybe.withDefault []",
    ]

    def with_helpers(self, definitions):
        return list(definitions) + self.HELPERS


class SaxratMaxTargetsRepl(SaxratRepl, MaxTargetsRepl):
    """The same bindings, pointed at saxrat."""


def state(setting, stated=None, held=None):
    """A `MaxTargetsState`, written the way the repl wants it."""
    return ("{ fromSetting = %d, statedByClient = %s, heldAtOnce = %s }"
            % (setting,
               "Nothing" if stated is None else "Just %d" % stated,
               "Nothing" if held is None else "Just %d" % held))


def reading(targets, entries=()):
    """A `MaxTargetsReading` with a hand-written game log.

    The entries are a flat record the parser also produces, so writing them
    here costs nothing a real tree would have added -- and
    `TheParserCarriesTheChannelThisReads` asks the *real* parser the same
    question, so that claim is not resting on this shortcut.
    """
    return ("{ targetsCount = %d, gameLogEntries = [ %s ] }"
            % (targets,
               ", ".join(
                   '{ timestamp = Nothing, channel = Just "%s", text = "%s" }'
                   % (channel, text.replace('"', '\\"'))
                   for channel, text in entries)))


class BothAppsRepl:
    """One repl per app, so every rule below is asked of both."""

    @classmethod
    def setUpClass(cls):
        cls.repls = {"saxrat": open_repl(SaxratMaxTargetsRepl),
                     "mission runner": open_repl(MaxTargetsRepl)}

    @classmethod
    def tearDownClass(cls):
        for repl in cls.repls.values():
            repl.close()

    def each(self, expressions, definitions=()):
        """`(app, answers)` for every app, so a failure names which one."""
        for app, repl in self.repls.items():
            yield app, repl.evaluate(
                expressions, repl.with_helpers(definitions))


class TheParserCarriesTheChannelThisReads(BothAppsRepl, unittest.TestCase):
    """Both diverged parsers, asked directly for what the rule keys on.

    The two apps vendor separate copies of `EveOnline/ParseUserInterface.elm`,
    so whether each carries `gameLogEntriesSinceLastReading` with the channel
    and the text intact is a question about that app rather than about shared
    code. It is asked first, because every case below would otherwise pass or
    fail for reasons that have nothing to do with the rule.
    """

    def test_a_real_reading_gives_the_rule_the_clients_sentence(self):
        for app, answers in self.each(
                ["(entriesOf stated |> List.length) == 1",
                 "(entriesOf stated |> List.map .channel) == [ Just \"notify\" ]",
                 "(entriesOf stated |> List.map .text) == [ \"%s\" ]" % STATED_SIX,
                 "maxTargetsStatedInGameLog (entriesOf stated) == Just %d"
                 % CLIENT_MAXIMUM],
                definitions=[SaxratRepl.reading_binding(
                    "stated", [game_log([("notify", STATED_SIX)])])]):
            self.assertEqual(
                answers, [True] * 4,
                "%s's parser does not carry the client's statement as far as "
                "the rule, so nothing below would mean anything" % app)

    def test_an_absent_game_log_states_no_maximum(self):
        """`Nothing` from the parser is a host with no game log, and it must
        never read as the client having stated something."""
        for app, answers in self.each(
                ["maxTargetsStatedInGameLog (entriesOf quiet) == Nothing"],
                definitions=[SaxratRepl.reading_binding("quiet", [])]):
            self.assertEqual(
                answers, [True],
                "%s reads a reading with no game log as a stated maximum" % app)


class TheSettingStandsExactlyWhereNothingIsKnown(
        BothAppsRepl, unittest.TestCase):
    """The direction the whole rule is built around.

    A ceiling raised on absent evidence makes the bot spend readings asking for
    locks the client will never grant, and nothing would ever teach it back
    down. So `Nothing` in both halves is "nobody has said", never a default.

    The settings asked about are fixed values rather than a pair either side of
    a boundary, which is the hole CLAUDE.md records four of #120's own cases
    having: a case that only asks about `constant - 1` and `constant` passes for
    any constant, including one that admits everything.
    """

    def test_with_no_evidence_the_ceiling_is_exactly_the_setting(self):
        for app, answers in self.each(
                ["maxTargetsCeiling %s == %d" % (state(setting), setting)
                 for setting in (0, 1, 2, SHIPPED_DEFAULT, CLIENT_MAXIMUM, 17)]):
            self.assertEqual(
                answers, [True] * 6,
                "%s no longer leaves the setting alone where the client has "
                "said nothing -- a ceiling that grows on a guess is the one "
                "failure this rule exists to refuse" % app)

    def test_a_sentence_that_names_no_number_teaches_nothing(self):
        """Both markers present and no count in between is the client having
        reworded past the slice, which is not a reason to move anything."""
        reworded = ("You are already managing as many targets as you have "
                    "skill to.")
        for app, answers in self.each(
                ["maxTargetsInStatement \"%s\" == Nothing" % reworded,
                 "maxTargetsCeiling (step %s %s) == %d"
                 % (reading(0, [("notify", reworded)]),
                    state(SHIPPED_DEFAULT), SHIPPED_DEFAULT)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s took a default from a sentence that named no number" % app)


class TheClientsStatementMovesTheCeiling(BothAppsRepl, unittest.TestCase):
    """The half the corpus is loudest about."""

    def test_it_raises_the_shipped_default_to_what_the_client_says(self):
        """The corpus's own correction: a hardcoded 4 against a client that
        says 6, on 228 distinct entries and never once saying 4."""
        for app, answers in self.each(
                ["maxTargetsCeiling %s == %d"
                 % (state(SHIPPED_DEFAULT, stated=CLIENT_MAXIMUM),
                    CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True],
                "%s no longer raises the ceiling to the maximum the client "
                "states, which is the whole of this change" % app)

    def test_it_lowers_a_setting_the_client_contradicts(self):
        """`as many as you have skill to` is an upper bound as well as a floor,
        so a setting above it is a setting asking for locks that cannot be
        granted."""
        for app, answers in self.each(
                ["maxTargetsCeiling %s == 5" % state(8, stated=5),
                 "maxTargetsCeiling %s == 5" % state(6, stated=5)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s keeps a setting the client has contradicted" % app)

    def test_the_latest_statement_wins_rather_than_the_largest(self):
        """The client read 5 for about ninety minutes on 31 July 2026 and 6
        before and since, which is a skill completing -- so a session takes the
        client's answer *now*, in both directions.
        """
        session = ("step %s (step %s %s)"
                   % (reading(0, [("notify", STATED_FIVE)]),
                      reading(0, [("notify", STATED_SIX)]),
                      state(SHIPPED_DEFAULT)))
        for app, answers in self.each(
                ["(%s).statedByClient == Just 5" % session,
                 "maxTargetsCeiling (%s) == 5" % session]):
            self.assertEqual(
                answers, [True] * 2,
                "%s no longer takes the client's latest answer, so a ceiling "
                "cannot follow a skill in both directions" % app)

    def test_a_repeated_statement_moves_nothing_and_says_nothing(self):
        """228 distinct entries across the corpus, and one line per change:
        once-per-change needs no `already reported` flag because a repeat moves
        nothing."""
        after = ("step %s %s" % (reading(0, [("notify", STATED_SIX)]),
                                 state(SHIPPED_DEFAULT)))
        for app, answers in self.each(
                ["(changeOf %s %s) /= Nothing"
                 % (reading(0, [("notify", STATED_SIX)]),
                    state(SHIPPED_DEFAULT)),
                 "(changeOf %s (%s)) == Nothing"
                 % (reading(0, [("notify", STATED_SIX)]), after)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s says it learned something on a reading that moved nothing"
                % app)


class TheClientsSentenceIsNotTheDroneOne(BothAppsRepl, unittest.TestCase):
    """The near-miss the corpus contains, and the case that matters most here.

    `You cannot launch Acolyte I because you are already controlling 5 drones,
    as much as you have skill to.` is the same shape to within two words, and it
    is *more* common than the targeting one -- 188 live quick-message sightings
    in saxrat's run 5 against 40. Admitting it would cap this ship at five
    targets on a reading that said nothing about targeting at all.
    """

    def test_the_drone_refusal_states_no_target_maximum(self):
        for app, answers in self.each(
                ["maxTargetsStatedInGameLog [ %s ] == Nothing"
                 % ('{ timestamp = Nothing, channel = Just "notify"'
                    ', text = "%s" }' % DRONE_REFUSAL),
                 "maxTargetsCeiling (step %s %s) == %d"
                 % (reading(0, [("notify", DRONE_REFUSAL)]),
                    state(SHIPPED_DEFAULT), SHIPPED_DEFAULT)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s reads the drone-control refusal as a lock ceiling, which "
                "would cap this ship at the number of drones it can fly" % app)

    def test_other_targeting_failures_state_no_maximum_either(self):
        for app, answers in self.each(
                ["maxTargetsStatedInGameLog [ %s ] == Nothing"
                 % ('{ timestamp = Nothing, channel = Just "notify"'
                    ', text = "%s" }' % text.replace('"', '\\"'))
                 for text in OTHER_TARGETING_FAILURES]):
            self.assertEqual(
                answers, [True] * len(OTHER_TARGETING_FAILURES),
                "%s reads a targeting failure that names no capacity as one "
                "that does" % app)

    def test_the_sentence_on_another_channel_is_not_read(self):
        """#41's lesson in the other direction: the channel is part of the
        match, and a sentence carried on `info` is not the one this reads."""
        for app, answers in self.each(
                ["maxTargetsStatedInGameLog [ %s ] == Nothing"
                 % ('{ timestamp = Nothing, channel = Just "info"'
                    ', text = "%s" }' % STATED_SIX)]):
            self.assertEqual(
                answers, [True],
                "%s reads the statement off a channel it does not arrive on"
                % app)

    def test_the_number_belongs_to_the_clause_that_was_matched(self):
        """Sliced out after `maxTargetsStatedMarker` rather than taken as the
        first integer in the sentence, so a client that puts a number earlier in
        a reworded line cannot hand this a count of something else."""
        prefixed = ("2 of your modules are offline. You are already managing 6 "
                    "targets, as many as you have skill to.")
        for app, answers in self.each(
                ["maxTargetsInStatement \"%s\" == Just 6" % prefixed]):
            self.assertEqual(
                answers, [True],
                "%s takes the first integer in the line rather than the count "
                "the matched clause is about" % app)


class TheTargetBarProvesAFloor(BothAppsRepl, unittest.TestCase):
    """The half that needs no attribution and cannot be wrong.

    A reading whose bar holds N is this ship holding N -- the bar is the ship's
    own state, not an overview row that could have been somebody else's. This is
    also what covers the ship auto-locking past whatever the bot asked for, which
    is how six targets came to be held while the shipped ceiling was four.
    """

    def test_a_bar_holding_more_than_the_setting_raises_the_ceiling(self):
        for app, answers in self.each(
                ["maxTargetsCeiling %s == %d"
                 % (state(SHIPPED_DEFAULT, held=CLIENT_MAXIMUM), CLIENT_MAXIMUM),
                 "maxTargetsCeiling (step %s %s) == %d"
                 % (reading(CLIENT_MAXIMUM), state(SHIPPED_DEFAULT),
                    CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s does not believe a bar it can see holding more than the "
                "setting allows" % app)

    def test_a_bar_below_the_setting_lowers_nothing(self):
        """Holding three does not prove four is impossible: the floor only
        rises."""
        for app, answers in self.each(
                ["maxTargetsCeiling %s == %d"
                 % (state(SHIPPED_DEFAULT, held=1), SHIPPED_DEFAULT),
                 "maxTargetsCeiling %s == 6" % state(4, stated=6, held=2)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s lets a partly filled bar lower a ceiling it says nothing "
                "about" % app)

    def test_the_floor_never_falls_back(self):
        """An empty bar is a ship between engagements, not a ship that has lost
        slots -- so a session that filled six holds six."""
        session = ("step %s (step %s %s)"
                   % (reading(0), reading(CLIENT_MAXIMUM),
                      state(SHIPPED_DEFAULT)))
        for app, answers in self.each(
                ["(%s).heldAtOnce == Just %d" % (session, CLIENT_MAXIMUM),
                 "maxTargetsCeiling (%s) == %d" % (session, CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True] * 2,
                "%s lets the proven floor fall on an empty target bar" % app)

    def test_an_empty_bar_is_not_a_floor_of_zero(self):
        """Absent against false, in a field an operator reads: `-` in the status
        line means the bar has never been seen carrying anything, and `0` would
        mean it was seen carrying nothing.
        """
        for app, answers in self.each(
                ["(step %s %s).heldAtOnce == Nothing"
                 % (reading(0), state(SHIPPED_DEFAULT))]):
            self.assertEqual(
                answers, [True],
                "%s records an empty bar as a floor of zero, which collapses "
                "'never seen' into 'seen holding nothing'" % app)

    def test_the_floor_outranks_a_lower_stated_maximum(self):
        """A bar demonstrably holding six is not contradicted by a sentence the
        client wrote before a skill finished."""
        for app, answers in self.each(
                ["maxTargetsCeiling %s == %d"
                 % (state(SHIPPED_DEFAULT, stated=5, held=CLIENT_MAXIMUM),
                    CLIENT_MAXIMUM)]):
            self.assertEqual(
                answers, [True],
                "%s lets a stale statement override a bar it can see" % app)


class TheChangeIsSaidOnceAndSaysWhichHalfMoved(
        BothAppsRepl, unittest.TestCase):
    """The decision-log line, which is the only record a run keeps of the move."""

    def test_the_statement_and_the_bar_name_themselves(self):
        for app, repl in self.repls.items():
            said = repl.strings(
                ["changeOf %s %s |> Maybe.withDefault \"none\""
                 % (reading(0, [("notify", STATED_SIX)]),
                    state(SHIPPED_DEFAULT)),
                 "changeOf %s %s |> Maybe.withDefault \"none\""
                 % (reading(CLIENT_MAXIMUM), state(SHIPPED_DEFAULT))],
                repl.with_helpers([]))
            self.assertIn("already managing 6", said[0], app)
            self.assertIn("target bar is holding 6", said[1], app)
            for sentence in said:
                self.assertIn("from 4 to 6", sentence, app)

    def test_a_session_that_learns_nothing_says_nothing(self):
        for app, answers in self.each(
                ["(changeOf %s %s) == Nothing"
                 % (reading(0), state(SHIPPED_DEFAULT)),
                 "(changeOf %s %s) == Nothing"
                 % (reading(2), state(SHIPPED_DEFAULT))]):
            self.assertEqual(
                answers, [True] * 2,
                "%s reports a change on a reading that moved nothing" % app)


class TheStatusLineSaysWhereTheCeilingCameFrom(
        BothAppsRepl, unittest.TestCase):
    """Both halves named separately, because they fail differently.

    A run whose `client stated` never leaves `-` is one whose game log is not
    reaching the bot; a `most held at once` stuck below the ceiling is a ship
    that has not filled its slots. A clause carrying only the answer would leave
    those two grepping the same, which is #123's argument.
    """

    def test_the_clause_carries_the_answer_and_both_halves(self):
        for app, repl in self.repls.items():
            said = repl.strings(
                ["describeMaxTargets %s" % state(SHIPPED_DEFAULT),
                 "describeMaxTargets %s"
                 % state(SHIPPED_DEFAULT, stated=CLIENT_MAXIMUM, held=5)],
                repl.with_helpers([]))
            # `probing for 5` is #150's clause and is present exactly while
            # `client stated` is `-`: the statement is the only thing that ends
            # the probing, so a run whose two clauses disagree has a rule
            # reading something other than its own state.
            self.assertEqual(
                said[0],
                "Max targets: 4 (setting 4, client stated -, most held at "
                "once -, probing for 5).", app)
            self.assertEqual(
                said[1],
                "Max targets: 6 (setting 4, client stated 6, most held at "
                "once 5).", app)


class TheSettingIsReachableAndRefusesAnEmptyValue(
        BothAppsRepl, unittest.TestCase):
    """`max-targets`, and PR #116's rule reached by picking the value type.

    `AppSettings.valueTypeInteger` answers `Err` for a value `String.toInt`
    cannot read, and `BotFramework` turns that into `InternalFinishSession`. So
    `max-targets=` with nothing after it ends the session naming the value
    rather than silently leaving the ceiling at 4, which would read exactly like
    a ceiling an operator set.
    """

    def test_a_number_reaches_the_setting(self):
        for app, answers in self.each(
                ["(parseBotSettings \"max-targets=6\" |> Result.map "
                 ".maxTargetCount) == Ok 6",
                 "(parseBotSettings \"max-targets=1\" |> Result.map "
                 ".maxTargetCount) == Ok 1"]):
            self.assertEqual(
                answers, [True] * 2,
                "%s does not let an operator set the ceiling at all" % app)

    def test_an_empty_value_is_refused_rather_than_dropped(self):
        for app, answers in self.each(
                ["(parseBotSettings \"max-targets=\" |> Result.toMaybe) "
                 "== Nothing"]):
            self.assertEqual(
                answers, [True],
                "%s accepts an empty max-targets, so a ceiling nobody set "
                "reads exactly like one somebody did" % app)

    def test_the_default_is_unchanged_so_an_existing_settings_string_is_not(self):
        for app, answers in self.each(
                ["defaultBotSettings.maxTargetCount == %d" % SHIPPED_DEFAULT]):
            self.assertEqual(
                answers, [True],
                "%s changed the shipped default, which is a behaviour change "
                "for every settings string that does not name it" % app)


class TheWiringIsWhatMakesAnyOfThisReachable(unittest.TestCase):
    """Read out of the source, since none of it is an expression.

    A rule that answers correctly and is never asked is this repo's signature
    bug, and #34, #42 and #102 are three of it.
    """

    def test_neither_app_locks_against_the_raw_setting_any_more(self):
        for app, path in APPS:
            source = collapsed(source_of(path))
            self.assertNotIn(
                "botSettings.maxTargetCount <=", source,
                "%s still compares the raw setting where the learned ceiling "
                "belongs" % app)
            self.assertNotIn(
                "List.take context.eventContext.botSettings.maxTargetCount",
                source,
                "%s still takes the raw setting as its lock candidates" % app)
            # The decision reaches the ceiling *through*
            # `maxTargetsRowsToTake` since #150, which adds the one row the
            # probe needs and is the only caller of `maxTargetsCeiling` at a
            # lock site. Asserting the ceiling's own name here would now pass
            # for a decision that consulted it and took the raw setting anyway.
            self.assertIn(
                "maxTargetsRowsToTake (maxTargetsStateFrom context)", source,
                "%s never consults the learned ceiling from a decision" % app)

    def test_the_setting_is_read_only_where_the_state_is_assembled(self):
        """One reader per app on the decision side and one on the memory side.

        Two places asking the setting directly would be two opinions about the
        ceiling, which is how `weaponModuleButtonsLeftToRight` came to exist.
        """
        for app, path in APPS:
            source = source_of(path)
            reads = re.findall(r"botSettings\.maxTargetCount", source)
            self.assertEqual(
                len(reads), 2,
                "%s reads max-targets from %d places rather than the two that "
                "assemble the state" % (app, len(reads)))

    def test_the_memory_update_is_what_writes_the_verdict(self):
        for app, path in APPS:
            body = collapsed(body_of(source_of(path),
                                     "updateMemoryForNewReadingFromGame"))
            self.assertIn("updateMaxTargetsLearning", body, app)
            for field in ("maxTargetsStatedByClient = maxTargetsLearning"
                          ".statedByClient",
                          "maxTargetsHeldAtOnce = maxTargetsLearning.heldAtOnce",
                          "maxTargetsLastChange = maxTargetsLearning.change"):
                self.assertIn(
                    field, body,
                    "%s writes a max-targets field from something other than "
                    "the rule's own answer" % app)

    def test_the_change_is_announced_at_the_root(self):
        """Settled in the memory update, which runs whatever the bot is doing,
        so the branch that learned it is not reliably the branch being
        evaluated -- `lockRangeLastChange`'s placement for its reason."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            self.assertIn(
                "context.memory.maxTargetsLastChange", source,
                "%s never prints the sentence the memory update settled" % app)
            self.assertIn(
                "context.memory.lockRangeLastChange , context.memory"
                ".maxTargetsLastChange", source,
                "%s does not announce the move beside the other verdicts at "
                "the root, where nothing can decline to print it" % app)

    # The clause as a *term* of each app's own status expression, not merely a
    # name appearing somewhere in the file. Asserting the substring is the hole
    # #109 records finding twice: a version that still names the renderer while
    # answering nothing for it prints nothing and passes.
    STATUS_TERMS = {
        "saxrat":
            "++ describeMaxTargets (maxTargetsStateFrom context) ++",
        "mission runner":
            ", describeMaxTargets (maxTargetsStateFrom context) ]",
    }

    def test_the_status_line_carries_the_clause(self):
        for app, path in APPS:
            self.assertIn(
                self.STATUS_TERMS[app], collapsed(source_of(path)),
                "%s does not report the ceiling on every reading, so a run "
                "that never learned one and a run whose clause was "
                "neutralised grep the same" % app)

    def test_the_rules_are_functions_of_records_so_a_case_can_run_them(self):
        """#106 records what the other shape costs: a rule reachable only
        through a whole `BotDecisionContext` can be checked by reading it and in
        no other way, which is exactly why the version it replaced was."""
        for app, path in APPS:
            source = collapsed(source_of(path))
            for signature in (
                    "maxTargetsCeiling : MaxTargetsState -> Int",
                    "describeMaxTargets : MaxTargetsState -> String",
                    "updateMaxTargetsLearning : MaxTargetsReading -> "
                    "MaxTargetsState -> MaxTargetsLearning"):
                self.assertIn(
                    signature, source,
                    "%s: %s takes a context again, so it can no longer be "
                    "executed by a case" % (app, signature.split(" :")[0]))

    def test_the_setting_is_parsed_by_the_type_that_refuses_an_empty_value(self):
        for app, path in APPS:
            source = collapsed(source_of(path))
            match = re.search(
                r'\( "max-targets" , (AppSettings\.\w+)', source)
            self.assertIsNotNone(match, "%s has no max-targets setting" % app)
            self.assertEqual(
                match.group(1), "AppSettings.valueTypeInteger",
                "%s parses max-targets with something other than the value "
                "type that answers Err for an empty value" % app)


class BothAppsCarryTheSameRule(unittest.TestCase):
    """Compared byte for byte, the way #123's quick-message rules are.

    The two apps meet the same client and the same sentence, so a fix that lands
    in one copy while the other silently lacks it is its own bug -- and the
    failure would be quiet, since a ceiling that never moves reads exactly like
    a client that never spoke.
    """

    def test_every_shared_declaration_is_identical(self):
        saxrat = source_of(SAXRAT_BOT_ELM)
        mission = source_of(MISSION_RUNNER_BOT_ELM)
        for name in SHARED_DECLARATIONS:
            self.assertEqual(
                body_of(saxrat, name), body_of(mission, name),
                "%s has drifted between the two apps" % name)


class TheRowIdentityDisciplineIsUntouched(unittest.TestCase):
    """The neighbouring rule this must not weaken, asserted rather than assumed.

    `overviewEntryLockHandle` keys on EVE's `itemID` and falls back to a row's
    name only where no other row shares it, so a pocket of same-named rats
    teaches nothing. This change does not consult it -- the target bar is the
    ship's own state and needs no attribution at all -- and that is the finding
    rather than an omission: there is no row here to attribute anything to. The
    case exists so that a later version reaching for an overview row has to
    notice it is taking on a problem this one does not have.
    """

    def test_the_ceiling_is_learned_without_attributing_anything_to_a_row(self):
        saxrat = source_of(SAXRAT_BOT_ELM)
        for name in ("maxTargetsStatedInGameLog", "updateMaxTargetsLearning",
                     "maxTargetsCeiling"):
            body = body_of(saxrat, name)
            for reached in ("overviewEntryLockHandle", "objectItemID",
                            "overviewWindows"):
                self.assertNotIn(
                    reached, body,
                    "%s reaches for an overview row, so the ceiling is now "
                    "only as good as the row-identity rule -- which in an "
                    "anomaly of identically named rats yields no evidence at "
                    "all" % name)

    def test_the_same_name_exclusion_is_still_the_shipped_one(self):
        body = collapsed(body_of(source_of(SAXRAT_BOT_ELM),
                                 "overviewEntryLockHandle"))
        self.assertIn(
            "|> List.length) == 1", body,
            "the same-name exclusion has been loosened from 'no other row "
            "shares it', which is the one change the lock-range rule must not "
            "take")


class WhatTheRecordedRunsSayAboutTheCeiling(unittest.TestCase):
    """The corpus, asked the questions it bears on.

    Asserted as *relations* rather than as counts, so a corpus that grows cannot
    turn a true claim red.
    """

    STATED = re.compile(
        r"\(notify\) (You are already managing (\d+) targets, "
        r"as many as you have skill to\.)")

    @classmethod
    def setUpClass(cls):
        if not os.path.isdir(EVE_BOT_LOGS):
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what the client has "
                "stated about this ship's lock slots cannot be consulted here")
        logs = sorted(name for name in os.listdir(EVE_BOT_LOGS)
                      if name.endswith(".log"))
        if not logs:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what the client has "
                "stated about this ship's lock slots cannot be consulted here")

        cls.statements = set()
        cls.drone_refusals = 0
        # Runs that flew the rule, and what it did there. A run appears here
        # only if its status line carries the clause, which is what separates a
        # run from before #149 from one after it -- the log's own
        # `# bot version:` names a commit and says nothing about which rules
        # were in it.
        cls.runs_reporting_a_ceiling = {}
        for name in logs:
            reported = {"clauses": 0, "moved": 0, "stated": 0}
            with open(os.path.join(EVE_BOT_LOGS, name),
                      encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "game log:" in line:
                        for whole, count in cls.STATED.findall(line):
                            cls.statements.add((whole, int(count)))
                    if "already controlling" in line and "drones" in line:
                        cls.drone_refusals += 1
                    if "Max targets:" in line:
                        reported["clauses"] += 1
                        if "client stated -" not in line:
                            reported["stated"] += 1
                    if "Learned max targets" in line:
                        reported["moved"] += 1
            if reported["clauses"]:
                cls.runs_reporting_a_ceiling[name] = reported

    def test_the_client_states_a_maximum_and_it_is_above_the_shipped_default(self):
        """The whole argument for the change, recounted rather than remembered.

        Every statement the corpus holds names a number, and every one of them is
        larger than the 4 both apps shipped -- so the ceiling was leaving lock
        slots unused on every engagement that filled it.
        """
        self.assertTrue(
            self.statements,
            "no recorded run carries the client's statement of its target "
            "maximum, so the matcher is keyed on a sentence this client does "
            "not write")
        for whole, count in self.statements:
            self.assertGreater(
                count, SHIPPED_DEFAULT,
                "the client stated a maximum of %d, which the shipped default "
                "of %d did not waste: %r"
                % (count, SHIPPED_DEFAULT, whole))

    def test_the_shipped_matcher_reads_every_one_of_them(self):
        """The literals are read out of `Bot.elm` and run against the client's
        own recorded lines, so a matcher that drifts from what the client writes
        fails here rather than in a run."""
        source = source_of(SAXRAT_BOT_ELM)
        markers = [
            re.search(r'^%s :\s*String\s*\n%s =\s*\n\s*"([^"]*)"'
                      % (name, name), source, re.MULTILINE)
            for name in ("maxTargetsStatedMarker", "maxTargetsSkillMarker")]
        self.assertTrue(all(markers), "the markers are no longer plain literals")
        stated, skill = (match.group(1) for match in markers)
        for whole, count in self.statements:
            lowered = whole.lower()
            self.assertIn(stated, lowered, whole)
            self.assertIn(skill, lowered, whole)
            after = lowered.split(stated)[1].split()
            self.assertEqual(
                int(after[0]), count,
                "the shipped slice does not recover the count from %r" % whole)

    def test_the_drone_refusal_really_occurs_and_is_declined(self):
        """The near-miss is not hypothetical: the client writes it, and more
        often than the targeting one."""
        self.assertGreater(
            self.drone_refusals, 0,
            "no recorded run carries the drone-control refusal, so the case "
            "that this matcher declines it is guarding against nothing")
        source = source_of(SAXRAT_BOT_ELM)
        self.assertIn(
            '"as many as you have skill to"', source,
            "the closing marker no longer distinguishes the targeting refusal "
            "from the drone one, which says 'as much'")

    def test_a_run_has_now_flown_the_rule_and_learned_nothing_from_it(self):
        """The other half, which only a run could answer -- and one has flown.

        This case used to assert that the corpus carried no `Max targets:`
        clause at all, and that premise expired the moment saxrat's run 6
        launched from the merge commit of #149. What the run says is what #150
        argues: the clause is on every reading, `client stated` never leaves
        `-`, the client wrote its sentence **not once**, and no ceiling ever
        moved. Neither half of the rule can move while the lock site stops at
        the ceiling it already believes in.

        Asserted as an *existence* claim over the corpus rather than as a
        property of every run, because a run flown after #150 should be
        expected to learn something -- and that later run makes this one no
        less true.
        """
        self.assertTrue(
            self.runs_reporting_a_ceiling,
            "no recorded run carries a max-targets clause, so nothing here "
            "says what the rule does in flight -- which was true when #149 "
            "merged and stopped being true with the next launch")
        inert = [name for name, run in self.runs_reporting_a_ceiling.items()
                 if not run["moved"] and not run["stated"]]
        self.assertTrue(
            inert,
            "every recorded run that flew the rule learned something from it, "
            "which contradicts #150's premise that neither half of it can move "
            "on its own -- go and read what moved it: %r"
            % (self.runs_reporting_a_ceiling,))


class WhatTheCeilingCostSaxrat(unittest.TestCase):
    """The measurement that says the shipped number was expensive here.

    saxrat is the worse affected of the two: anomalies are fuller than mission
    pockets, and its `Enough locked targets.` branch prints on every reading it
    declines to lock another rat. The mission runner's `List.take` says nothing,
    which is why there is no matching case for it.
    """

    @classmethod
    def setUpClass(cls):
        logs = [os.path.join(EVE_BOT_LOGS, "saxrat_run%d.log" % number)
                for number in range(1, 10)]
        logs = [path for path in logs if os.path.exists(path)]
        if not logs:
            raise unittest.SkipTest(
                "no recorded saxrat runs in ~/eve-bot-logs, so what the "
                "shipped ceiling cost cannot be counted here")
        cls.declined = 0
        cls.wanted_more = 0
        for path in logs:
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "Enough locked targets." in line:
                        cls.declined += 1
                    if "Lock more targets." in line:
                        cls.wanted_more += 1

    def test_the_ceiling_stopped_the_bot_on_readings_it_wanted_more(self):
        """Both branches are reached in the same runs, so the cap was binding
        rather than merely present."""
        self.assertGreater(
            self.declined, 0,
            "no recorded saxrat run ever stopped at the ceiling, so nothing "
            "here says the shipped number cost anything")
        self.assertGreater(
            self.wanted_more, 0,
            "no recorded saxrat run ever wanted another target, so the two "
            "branches cannot be compared")


if __name__ == "__main__":
    unittest.main()
