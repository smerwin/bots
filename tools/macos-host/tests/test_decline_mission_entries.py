"""Tests for the two halves of a decline: the entry that arms it, and the line
that reports it.

Issue #113. `decline-mission` was parsed with `AppSettings.valueTypeString` and
no empty check, and `shouldDeclineMission` matches each entry as a **substring**
of the offered mission name. So a single `decline-mission=` line with nothing
after it put `""` in the list, and the empty string is a substring of every
mission name there is -- the bot would have handed back every mission the agent
ever offered, one standing hit at a time, while the log called each one an
ordinary skip. The codebase already knew: `missionNameFromTracker`'s own comment
says an empty entry "is a filter that declines every mission the agent ever
offers", and `splitSettingIntoNames` drops empties for exactly that reason. The
tracker side was guarded; the settings side was not.

**The empty value is rejected, not dropped**, and `TheParserRefusesANameThatIsNot
One` executes that. The argument is at `valueTypeNonEmptyString` in `Bot.elm`:
an empty value already has two documented meanings here -- `nonEmptySettingValue`
reads it as *unset*, `splitSettingIntoNames` drops it as a trailing comma -- and
neither can apply to an assignment whose whole value is empty, because nothing is
left to read the intent from. Dropping picks one reading without saying so, which
is this repo's signature failure; `AppSettings`' own answer to a value it cannot
use is an `Err` naming the setting.

**Three other handlers had the identical shape** and are fixed with the same
helper: `agent-name` (empty means `stringContainsIgnoringCase ""`, which matches
every agent in the station rather than the documented default of the first
*available* one), `drone-type` (empty makes `droneNameNeedle` empty, so the
restock drags whatever item is first in the hangar view), and `avoid-rat`. The
last is the odd one: `avoidRats` is written by the parser and **read nowhere in
the bot**, so no filter is armed by an empty entry there today. It is guarded
anyway, because "nothing reads this list" is a fact about a setting that does
nothing rather than a property to build a guard's absence on --
`AvoidRatIsParsedAndNeverRead` pins the finding so it is not mistaken for
coverage.

**The second half is legibility.** The decline branch printed
`Skip this mission (<name>) using '<label>'.`, which reads identically whether
the match came from an operator's own `decline-mission` line, from this session's
`missionNamesAbandoned`, or from an entry matching everything. Every one of those
lines costs standing -- run 25 clicked Decline 105 times -- so a wrongly armed
filter has to be visible on the first offer, not after the standing is gone.
`declineMatchFromLists` is that rule, extracted to take its two lists directly so
these cases can execute it rather than restate it.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives. The corpus cases skip where
`~/eve-bot-logs` is absent, for the same file's reason.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, open_repl, recorded_runs

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
PARSE_USER_INTERFACE_ELM = os.path.join(
    MISSION_RUNNER_DIR, "EveOnline", "ParseUserInterface.elm")
RUN_MISSION = os.path.join(MACOS_HOST_DIR, "run_mission.sh")

# Every setting whose value is one name, with the field it fills. All four took
# whatever they were given before #113.
NAME_SETTINGS = {
    "agent-name": "agentName",
    "decline-mission": "missionNamesToDecline",
    "avoid-rat": "avoidRats",
    "drone-type": "droneTypeName",
}

# The settings that deliberately accept an empty value, and must keep doing so:
# `short-range-ammo=` is how the ammo swap is switched off from the web console
# without deleting the line. Guarding these would break that.
SETTINGS_WHERE_EMPTY_MEANS_UNSET = ("home-station", "short-range-ammo",
                                    "long-range-ammo")

# The runs whose decision logs contain the decline branch firing.
RUNS_THAT_SKIPPED = ("20", "25", "26")

SKIP_LINE = re.compile(r"Skip this mission \((.*?)\) using '([^']*)'")
ACCEPT_LINE = re.compile(r"Accept the mission '(.*?)'\.")


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Source text with every run of whitespace reduced to one space.

    PR #58's reason, inherited from `test_abandon_stuck_mission.py`: what these
    assertions mean is the structure, and `elm-format` owns where the lines
    break.
    """
    return " ".join(text.split())


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


def elm_string_list(values):
    return "[ " + ", ".join(elm_string(value) for value in values) + " ]"


def launcher_default_settings():
    """The settings string `run_mission.sh` passes when nobody overrides it."""
    with open(RUN_MISSION, encoding="utf-8") as source:
        match = re.search(r'^SETTINGS="(.*?)"$', source.read(),
                          re.DOTALL | re.MULTILINE)
    assert match, "run_mission.sh no longer defines SETTINGS the way this reads it"
    return match.group(1)


PREAMBLE = (
    "import Bot exposing (..)",
    "import Common.Basics exposing (stringContainsIgnoringCase)",
    "import Result.Extra",
)


class DeclineRepl(ElmRepl):
    """The shared harness, plus the three questions this file asks of it."""

    def parses(self, settings_strings):
        """Whether each settings string is accepted at all."""
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def rejection_reasons(self, settings_strings):
        """The error each settings string is rejected with, or `<accepted>`.

        `Result.Extra.merge` rather than a `case`, because the repl takes one
        line per expression and a multi-line `case` inside a list does not
        survive that.
        """
        return self.strings([
            'parseBotSettings %s |> Result.map (always "<accepted>") '
            "|> Result.Extra.merge" % elm_string(settings)
            for settings in settings_strings])

    def names_of(self, field, settings_strings):
        """The list each settings string parses `field` to, one per string.

        Joined inside Elm and read back as one string, so the repl's pretty
        printer cannot wrap a long answer across lines.
        """
        answers = self.strings([
            'parseBotSettings %s |> Result.map (.%s >> String.join "|") '
            '|> Result.withDefault "<rejected>"'
            % (elm_string(settings), field)
            for settings in settings_strings])
        return [[] if answer == "" else answer.split("|") for answer in answers]

    def matches(self, cases):
        """`declineMatchFromLists` run on `(setting, abandoned, name)` triples.

        Answered as `<source> | <entry>`, or `<none>` where neither list
        refuses the mission, so one string carries both halves of the
        attribution the decision line has to print.
        """
        return self.strings([
            'declineMatchFromLists %s %s %s '
            '|> Maybe.map (\\found -> found.source ++ " | " ++ found.entry) '
            '|> Maybe.withDefault "<none>"'
            % (elm_string_list(to_decline), elm_string_list(abandoned),
               elm_string(name))
            for to_decline, abandoned, name in cases])


def repl():
    return open_repl(DeclineRepl, prefix="test-decline-mission-entries-",
                     preamble=PREAMBLE)


class TheParserRefusesANameThatIsNotOne(unittest.TestCase):
    """The empty value, executed through the real parser.

    Every case here would have passed before #113 with the *opposite* assertion,
    which is the point: the old parser accepted all of these and armed a filter
    with them.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_empty_value_is_rejected_for_every_setting_that_names_one_thing(self):
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertEqual(self.repl.parses(["%s=" % key]), [False])

    def test_a_whitespace_only_value_is_rejected_too(self):
        # End to end, which is what an operator types. Note this alone does not
        # pin the guard: `parseSimpleListOfAssignments` trims every assigned
        # value before any handler sees it, so a guard with no trim of its own
        # passes this. The case below is the one that bites.
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertEqual(
                    self.repl.parses(["%s=   " % key, "%s=\t" % key]),
                    [False, False])

    def test_the_guard_judges_the_trimmed_value_itself(self):
        """The helper asked directly, because the framework hides this.

        Found by mutation: taking `String.trim` out of `valueTypeNonEmptyString`
        left every case above green, since the framework had already trimmed.
        A guard that only works because its caller happens to trim is a guard
        whose next caller does not, and this file has a spare one --
        `Common.AppSettings` is vendored per app and its trimming is not this
        file's to rely on.
        """
        answers = self.repl.strings([
            'valueTypeNonEmptyString (\\_ settings -> settings) %s '
            '|> Result.map (always "<accepted>") |> Result.Extra.merge'
            % elm_string(value)
            for value in ["", "   ", "\t", " Illegal Activity "]])
        self.assertEqual(answers[:3],
                         [answers[0], answers[0], answers[0]])
        self.assertIn("empty", answers[0])
        self.assertEqual(answers[3], "<accepted>")

    def test_the_guard_stores_the_name_with_its_surrounding_space_gone(self):
        # The same trim, in its other direction: an entry stored as
        # ` Illegal Activity ` still matches, so nothing here would notice --
        # except that it is what the decision line then quotes back.
        self.assertEqual(
            self.repl.strings([
                'parseBotSettings %s |> Result.map (.missionNamesToDecline '
                '>> String.join "|") |> Result.withDefault "<rejected>"'
                % elm_string("decline-mission=  Illegal Activity  ")]),
            ["Illegal Activity"])

    def test_the_rejection_says_which_setting_and_why(self):
        # The framework prepends the setting's name; the value carries the
        # reason and the fix. A rejection an operator cannot act on is a run
        # that ends with a shrug.
        reason = self.repl.rejection_reasons(["decline-mission="])[0]
        self.assertIn("decline-mission", reason)
        self.assertIn("empty", reason)
        self.assertIn("substring", reason)
        self.assertIn("Delete the line", reason)

    def test_one_bad_line_rejects_the_whole_settings_string(self):
        # `Result.Extra.combine`, and it matters: a partially applied settings
        # string is a run with settings nobody wrote.
        self.assertEqual(
            self.repl.parses([
                "decline-mission=Survey Rendezvous\ndecline-mission=",
                "decline-mission=\ndecline-mission=Survey Rendezvous",
            ]),
            [False, False])

    def test_a_real_name_still_parses_exactly_as_it_did(self):
        # The compatibility claim. Surrounding space is still trimmed, and a
        # name with spaces inside it is still one name.
        answers = self.repl.strings([
            'parseBotSettings %s |> Result.map (.missionNamesToDecline '
            '>> String.join "|") |> Result.withDefault "<rejected>"'
            % elm_string(settings)
            for settings in [
                "decline-mission=Illegal Activity",
                "decline-mission=   Illegal Activity   ",
                "decline-mission=Illegal Activity\ndecline-mission=Recon",
            ]])
        self.assertEqual(answers, ["Illegal Activity", "Illegal Activity",
                                   "Recon|Illegal Activity"])

    def test_the_settings_that_mean_unset_by_being_empty_still_do(self):
        # The other half of the convention. `short-range-ammo=` switches the
        # ammo swap off from the web console, and guarding it the same way
        # would take that away -- see `nonEmptySettingValue`.
        for key in SETTINGS_WHERE_EMPTY_MEANS_UNSET:
            with self.subTest(key):
                self.assertEqual(self.repl.parses(["%s=" % key]), [True])

    def test_the_list_settings_still_drop_empties_rather_than_rejecting(self):
        # #47's answer, unchanged, and this is where the guard deliberately
        # stops. Inside a comma-separated list the other entries carry what was
        # meant, so a trailing comma is a typo with a recoverable intent; and a
        # wholly empty `attack-object=` yields the empty list, which arms no
        # filter at all and so is the same as omitting the line. Neither is the
        # case `decline-mission=` is.
        for key in ("attack-object", "approach-object", "prefer-wreck"):
            with self.subTest(key):
                self.assertEqual(
                    self.repl.parses(["%s=Drone Silo," % key, "%s=" % key]),
                    [True, True])
        self.assertEqual(
            self.repl.names_of("attackObjectNames", ["attack-object="]), [[]])

    def test_an_empty_entry_would_have_matched_every_mission_name(self):
        """The property that makes the empty value catastrophic, executed.

        Asserted by running the matcher rather than by reading it: if this ever
        stopped being true, the rejection above would look like fussiness.
        """
        matches_anything, matches_nothing = self.repl.booleans([
            'stringContainsIgnoringCase "" "Save a Man\'s Career"',
            'stringContainsIgnoringCase "Save a Man\'s Career" ""',
        ])
        self.assertTrue(matches_anything,
                        "an empty entry is a substring of every mission name")
        self.assertFalse(matches_nothing)


class TheDeclineSaysWhichListRefusedIt(unittest.TestCase):
    """`declineMatchFromLists`, run for real on the two lists it takes."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_setting_is_named_when_the_setting_is_what_matched(self):
        self.assertEqual(
            self.repl.matches([(["Illegal Activity"], [],
                                "Illegal Activity (1 of 3)")]),
            ["the 'decline-mission' setting | Illegal Activity"])

    def test_the_session_list_is_named_when_that_is_what_matched(self):
        # `missionNamesAbandoned` is memory rather than a setting, and an
        # operator's response to it is different: it goes away at the next
        # restart, where a settings line has to be deleted.
        self.assertEqual(
            self.repl.matches([([], ["Illegal Activity"],
                                "Illegal Activity (2 of 3)")]),
            ["a mission this session already gave up on | Illegal Activity"])

    def test_the_setting_wins_where_both_lists_would_match(self):
        # Ties go to the answer an operator can act on.
        self.assertEqual(
            self.repl.matches([(["Illegal"], ["Illegal Activity"],
                                "Illegal Activity (1 of 3)")]),
            ["the 'decline-mission' setting | Illegal"])

    def test_it_names_the_entry_that_matched_not_the_whole_list(self):
        # A list of several entries does not say which one refused the mission,
        # and a substring entry does not read back off the mission's own name.
        self.assertEqual(
            self.repl.matches([(["Worlds Collide", "Recon", "Survey"], [],
                                "Survey Rendezvous")]),
            ["the 'decline-mission' setting | Survey"])

    def test_a_mission_no_entry_refuses_produces_no_match_at_all(self):
        # The headline incident's own mission, against the list the launcher
        # ships. Nothing here explains that decline, and this is what says so.
        self.assertEqual(
            self.repl.matches([(["Survey Rendezvous"], [],
                                "Save a Man's Career")]),
            ["<none>"])

    def test_the_empty_entry_reports_itself_as_the_empty_entry(self):
        """The line the operator would have needed, had one ever been armed.

        The parser now refuses to build this list, so this is the rule being
        asked what it *would* print -- which is the whole reason the entry is
        named rather than only the list. `''` in the decision log is a filter
        matching everything, and it says so on the first mission rather than
        after the standing is gone.
        """
        self.assertEqual(
            self.repl.matches([([""], [], "Save a Man's Career")]),
            ["the 'decline-mission' setting | "])

    def test_matching_is_case_insensitive_and_substring_as_it_always_was(self):
        # Unchanged behaviour, pinned because the extraction moved it: a name
        # recorded without its `(1 of 3)` suffix has to keep covering the chain.
        self.assertEqual(
            self.repl.matches([
                (["illegal activity"], [], "Illegal Activity (3 of 3)"),
                (["Illegal Activity (1 of 3)"], [], "Illegal Activity"),
            ]),
            ["the 'decline-mission' setting | illegal activity", "<none>"])

    def test_the_sentence_the_branch_prints_carries_both_halves(self):
        self.assertEqual(
            self.repl.strings([
                'declineMatchFromLists %s [] %s |> Maybe.map describeDeclineMatch '
                '|> Maybe.withDefault "<none>"'
                % (elm_string_list(["Illegal Activity"]),
                   elm_string("Illegal Activity (1 of 3)"))]),
            ["the 'decline-mission' setting matches it on 'Illegal Activity'"])


class TheWiringIsReadOutOfTheSource(unittest.TestCase):
    """What cannot be executed without a whole `BotDecisionContext`.

    Each of these is a way the two rules above could be correct and unreached,
    which is #15's failure and this repo's most expensive habit.
    """

    def setUp(self):
        self.source = bot_source()
        start = self.source.index("parseBotSettings =")
        self.settings_body = self.source[start:self.source.index("\n\n\n", start)]

    def handler(self, key):
        start = self.settings_body.index('( "%s"' % key)
        following = re.compile(r"\n\s*, \( \"").search(self.settings_body, start)
        end = following.start() if following else len(self.settings_body)
        return collapsed(self.settings_body[start:end])

    def test_every_setting_that_names_one_thing_goes_through_the_guard(self):
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertIn("valueTypeNonEmptyString", self.handler(key))

    def test_none_of_them_takes_a_raw_string_beside_the_guard(self):
        # The shape the bug had. A handler that keeps `AppSettings.valueTypeString`
        # compiles, parses a real name correctly, and differs only on the value
        # nobody types on purpose.
        for key in NAME_SETTINGS:
            with self.subTest(key):
                self.assertNotIn("AppSettings.valueTypeString", self.handler(key))

    def test_the_guard_rejects_rather_than_returning_the_settings_unchanged(self):
        # Dropping the entry is the other candidate answer, and it is a one-word
        # edit away: `Ok (always identity)` in place of the `Err`. That version
        # would pass every case above that asks what the list holds.
        guard = collapsed(self.source[
            self.source.index("valueTypeNonEmptyString integrateSettingValue"):
            self.source.index("emptySettingValueRejected :")])
        self.assertIn('"" -> Err emptySettingValueRejected', guard)
        self.assertIn("trimmed -> Ok (integrateSettingValue trimmed)", guard)

    def test_should_decline_is_defined_by_the_match_rather_than_beside_it(self):
        # Two implementations of one idea is how the tracker side came to be
        # guarded while the settings side was not. The predicate and the
        # attribution must not be able to disagree about what is declined.
        body = collapsed(self.source[
            self.source.index("shouldDeclineMission context missionName ="):
            self.source.index("{-| Which list refused a mission")])
        self.assertIn("declineMissionMatch context missionName /= Nothing", body)
        self.assertNotIn("List.any", body)

    def test_the_decline_branch_derives_the_reason_from_the_same_match(self):
        branch = collapsed(self.source[
            self.source.index("else if shouldDeclineMission context offeredMissionName then"):
            self.source.index('"Accept the mission \'"')])
        self.assertIn("declineMissionMatch context offeredMissionName", branch)
        self.assertIn("Maybe.map describeDeclineMatch", branch)

    def test_the_line_that_actually_clicks_the_button_carries_it(self):
        # Scoped to the `describeBranch` that skips the mission, not to the
        # whole branch: the give-up beside it also mentions `declineReason`, so
        # a wider read passes with this line back the way it was -- which is
        # the one line every recorded decline has printed.
        start = self.source.index('"Skip this mission ("')
        line = collapsed(self.source[
            start:self.source.index("(clickUiElement skipButton)", start)])
        self.assertIn("++ declineReason", line)
        self.assertIn("' -- \"", line)

    def test_the_branch_with_no_skip_button_names_the_reason_too(self):
        # `I want to skip this mission but see no way to.` has never fired, and
        # a branch that fires once in a session is exactly the one whose single
        # line has to carry everything.
        branch = collapsed(self.source[
            self.source.index("else if shouldDeclineMission context offeredMissionName then"):
            self.source.index('"Accept the mission \'"')])
        self.assertIn('"I want to skip this mission (" ++ declineReason', branch)

    def test_the_two_sources_are_named_constants_the_rule_reads(self):
        # So the decision log's wording and the test's expectations cannot
        # drift apart without one of them failing to compile.
        rule = collapsed(self.source[
            self.source.index("declineMatchFromLists namesToDecline"):
            self.source.index("declineMissionMatch : BotDecisionContext")])
        self.assertIn("matchIn declineSourceSetting namesToDecline", rule)
        self.assertIn("matchIn declineSourceAbandoned namesAbandoned", rule)

    def test_the_confirmation_still_asks_the_same_predicate(self):
        # `declineMissionConfirmationIsExpected` is what answers "yes" to the
        # `Decline Mission?` dialog, and it must agree with the branch that
        # asked for it -- #101's territory otherwise.
        confirmation = collapsed(self.source[
            self.source.index("declineMissionConfirmationIsExpected context ="):
            self.source.index("{-| How far back to look for the click")])
        self.assertIn("shouldDeclineMission context conversation.offeredMissionName",
                      confirmation)

    def test_the_message_box_parser_and_the_declining_answer_are_untouched(self):
        # #113's headline incident is unexplained, and the second path it points
        # at is #101's, already merged as PR #109. This change must not have
        # wandered into it, and the two places it would show are the parser's
        # one condition and the declining answer's lack of an affirmative.
        with open(PARSE_USER_INTERFACE_ELM, encoding="utf-8") as parser:
            self.assertIn('pythonObjectTypeName >> (==) "MessageBox"',
                          parser.read())
        start = self.source.index("closeMessageBoxByDeclining messageBox =")
        declining = collapsed(self.source[
            start:self.source.index("\n\n\n", start)])
        self.assertIn("no_dialog_button", declining)
        self.assertNotIn("yes_dialog_button", declining)


class AvoidRatIsParsedAndNeverRead(unittest.TestCase):
    """The finding, recorded so it is not mistaken for a working setting.

    `avoid-rat` has the same shape `decline-mission` had and is guarded the same
    way, but an empty entry there arms nothing -- because *no* entry there arms
    anything. The list is written by the parser and read by no decision, so the
    setting is documented in the bot's own header, reported by `--help`, and
    does nothing at all. That is its own issue, and this case is what keeps the
    guard above from reading as coverage of a live filter.
    """

    def setUp(self):
        self.source = bot_source()

    def test_the_field_is_written_by_the_parser_and_read_nowhere(self):
        uses = [line.strip() for line in self.source.splitlines()
                if "avoidRats" in line]
        # The default, the handler, and the field in the record type. Nothing
        # else: a fourth use would mean some decision has started reading it,
        # at which point the empty entry becomes a live filter and this case
        # should be replaced by one that tests the filter.
        self.assertEqual(len(uses), 3, uses)
        self.assertIn("avoidRats = []", uses[0])
        self.assertIn("avoidRats = ratToAvoid :: settings.avoidRats", uses[1])
        self.assertIn("avoidRats : List String", uses[2])


class TheLauncherWasNeverArmedWithOne(unittest.TestCase):
    """`run_mission.sh` is the only settings string anyone runs unedited.

    This is what makes #113 latent rather than active, and it is worth a case
    rather than a sentence: the shipped string is one stray line away from the
    failure, and it is now also the string the rejection has to keep accepting.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.settings = launcher_default_settings()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_launcher_settings_string_still_parses(self):
        self.assertEqual(self.repl.parses([self.settings]), [True])

    def test_it_ships_exactly_one_non_empty_decline_entry(self):
        names = self.repl.strings([
            'parseBotSettings %s |> Result.map (.missionNamesToDecline '
            '>> String.join "|") |> Result.withDefault "<rejected>"'
            % elm_string(self.settings)])[0]
        self.assertEqual(names, "Survey Rendezvous")

    def test_no_decline_line_in_it_is_empty(self):
        for line in self.settings.splitlines():
            if line.startswith("decline-mission"):
                with self.subTest(line):
                    self.assertTrue(line.split("=", 1)[1].strip())


class TheRecordedRunsShowNoFilterEverArmed(unittest.TestCase):
    """What the corpus says, as relations rather than as counts.

    The issue reports the decline branch firing 486 times on exactly two mission
    names, both configured. Asserting those numbers would turn a true claim red
    the next time a run declines something, so what is asserted is the shape a
    decline-everything filter would break: a run that skips also accepts.
    """

    def setUp(self):
        self.runs = recorded_runs(*RUNS_THAT_SKIPPED)

    def test_every_run_that_declined_also_accepted_a_mission(self):
        """The signature of the failure, stated as its absence.

        An empty entry matches every offer, so a run flying one would show
        skips and no accepts at all -- the agent handing missions over and the
        bot refusing each in turn. Every recorded run that declined anything
        took other work in the same session.
        """
        for name, path in self.runs:
            with self.subTest(name):
                with open(path, encoding="utf-8", errors="replace") as log:
                    text = log.read()
                skipped = SKIP_LINE.findall(text)
                accepted = ACCEPT_LINE.findall(text)
                self.assertTrue(skipped,
                                "run %s was chosen for having declines" % name)
                self.assertTrue(
                    accepted,
                    "run %s declined %d times and accepted nothing, which is "
                    "what an empty decline entry looks like"
                    % (name, len(skipped)))

    def test_the_declines_name_few_missions_where_the_accepts_name_more(self):
        # The same relation counted over distinct names rather than lines: a
        # filter matching everything refuses whatever the agent has, so the
        # names it refuses would outnumber the names anything accepted.
        skipped, accepted = set(), set()
        for _, path in self.runs:
            with open(path, encoding="utf-8", errors="replace") as log:
                text = log.read()
            skipped.update(name for name, _ in SKIP_LINE.findall(text))
            accepted.update(ACCEPT_LINE.findall(text))
        self.assertTrue(skipped)
        self.assertLess(len(skipped), len(accepted))

    def test_no_recorded_decline_was_of_an_unnamed_mission(self):
        # `Maybe.withDefault "unnamed"` in the branch: a decline of a mission
        # the reading could not name would be a refusal with nothing in it for
        # an operator, and none has happened.
        for name, path in self.runs:
            with self.subTest(name):
                with open(path, encoding="utf-8", errors="replace") as log:
                    names = [skipped for skipped, _ in SKIP_LINE.findall(log.read())]
                self.assertNotIn("unnamed", names)


if __name__ == "__main__":
    unittest.main()
