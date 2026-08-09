"""Tests for the three settings that hold a list of overview names.

Issue #47. `attack-object` took a comma-separated list; `approach-object` and
`prefer-wreck` took the whole value as one name, so the only way to give several
was one line each -- nine of them in `run_mission.sh`'s own defaults against
`attack-object`'s one. All three are now parsed by the same
`splitSettingIntoNames`, which is what keeps a second convention from growing
beside the first.

**The empty entry is the failure this guards.** All three lists are matched
against an overview row as a substring -- `matchesOverviewName` for the objects
to attack and approach, `stringContainsIgnoringCase` for the wrecks -- and the
empty string is a substring of every row. So one empty name is not a name that
matches nothing, it is a filter that matches everything: the bot would fly at the
first row on the grid, or call every hulk a preferred wreck. A trailing comma is
the ordinary way to write one by accident, which is why the splitter drops
empties rather than merely trimming them. Both halves are checked here -- that
the empty string really does match anything, and that the parser never produces
one.

The rules are **run** rather than restated in Python, through `elm repl` against
the real `Bot.elm`, for PR #45's reason: a mirrored parser only ever asserts what
its author thought the code did. That matters more than usual here, because the
compatibility claim is about a value the parser sees rather than about a shape it
returns -- `approach-object=Abandoned Mining Station` has to keep meaning exactly
what it meant, spaces and all.

The two orderings are checked too, because they differ and both are live. Names
on one line stay in the order they are written, while a repeated key prepends --
so across lines the last line is tried first, and inside a line the first name
is. That is `attack-object`'s existing behaviour, inherited rather than chosen,
and it is what makes collapsing the launcher's nine `approach-object=` lines into
one a reordering unless the line is written in the reverse of the old file order.
`TheLauncherDefaultsStillMeanWhatTheyMeant` pins that against the exact lists the
nine lines produced.

Nothing here reads a live game client or drives a bot. The `elm repl` cases need
`elm` on PATH and the app's dependencies already fetched, which is what
`compile_bot.sh` leaves behind; without it they **fail** rather than skipping,
for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import unittest

from prerequisites import ElmRepl, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(os.path.dirname(MACOS_HOST_DIR))
MISSION_RUNNER_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner")
MISSION_RUNNER_BOT_ELM = os.path.join(MISSION_RUNNER_DIR, "Bot.elm")
RUN_MISSION = os.path.join(MACOS_HOST_DIR, "run_mission.sh")

# The settings that hold a list of overview names, and the field each fills.
NAME_LIST_SETTINGS = {
    "attack-object": "attackObjectNames",
    "approach-object": "approachObjectNames",
    "prefer-wreck": "preferWreckNames",
}

# What the launcher's nine `approach-object=` lines and two `prefer-wreck=` lines
# meant before they were collapsed, in the order the bot ends up trying them.
# Repeated keys prepend, so this is the reverse of the order they were written
# in -- and the whole point of writing it out here is that the collapsed lines
# have to reproduce it exactly.
LAUNCHER_APPROACH_OBJECTS = [
    "Survey Ship",
    "Amarr-Caldari Mediation Center",
    "Amarr Chapel",
    "Caldari Deadspace Tactical Outpost",
    "Circular Construction",
    "Amarr Station",
    "Abandoned Mining Station",
]
LAUNCHER_PREFER_WRECKS = [
    "Cargo Container",
    "Personnel Transport",
]


def bot_source():
    with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def launcher_default_settings():
    """The settings string `run_mission.sh` passes when nobody overrides it."""
    with open(RUN_MISSION, encoding="utf-8") as source:
        match = re.search(r'^SETTINGS="(.*?)"$', source.read(),
                          re.DOTALL | re.MULTILINE)
    assert match, "run_mission.sh no longer defines SETTINGS the way this reads it"
    return match.group(1)


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


PREAMBLE = (
    "import Bot exposing (..)",
    "import Common.Basics exposing (stringContainsIgnoringCase)",
)


class SettingsRepl(ElmRepl):
    """The shared harness, plus the two questions this file asks of it."""

    def names(self, field, settings_strings):
        """The list each settings string parses to, one per string.

        The list is joined inside Elm and read back as a single string, so a
        long answer cannot be wrapped across lines by the repl's pretty printer.
        A settings string the parser rejects answers `<rejected>`, which is a
        distinct result from the empty list rather than an exception here.
        """
        answers = self.strings([
            'parseBotSettings %s |> Result.map (.%s >> String.join "|") '
            '|> Result.withDefault "<rejected>"'
            % (elm_string(settings), field)
            for settings in settings_strings])
        return [[] if answer == "" else answer.split("|") for answer in answers]

    def parses(self, settings_strings):
        """Whether each settings string is accepted at all."""
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])


def repl():
    return open_repl(SettingsRepl, prefix="test-settings-name-lists-",
                     preamble=PREAMBLE)


class TheParserIsExecutedRatherThanMirrored(unittest.TestCase):
    """All three settings, run for real."""

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def parsed(self, key, values):
        return self.repl.names(NAME_LIST_SETTINGS[key],
                               ["%s=%s" % (key, value) for value in values])

    def test_one_value_still_means_exactly_that_value(self):
        # The compatibility claim: every settings string written before this
        # change keeps working, including a name with spaces in it. Nothing here
        # may split on a space, and nothing may drop the spaces inside a name.
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertEqual(
                    self.parsed(key, ["Abandoned Mining Station"]),
                    [["Abandoned Mining Station"]])

    def test_several_values_arrive_as_several_names(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertEqual(
                    self.parsed(key, ["Amarr Chapel,Survey Ship"]),
                    [["Amarr Chapel", "Survey Ship"]])

    def test_space_around_a_comma_does_not_change_the_meaning(self):
        # `a, b` is how a person writes a list, and it has to mean `a,b`.
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                spaced, tight, padded = self.parsed(key, [
                    "Amarr Chapel, Survey Ship",
                    "Amarr Chapel,Survey Ship",
                    "   Amarr Chapel ,  Survey Ship   ",
                ])
                self.assertEqual(spaced, ["Amarr Chapel", "Survey Ship"])
                self.assertEqual(tight, spaced)
                self.assertEqual(padded, spaced)

    def test_a_trailing_comma_yields_no_empty_name(self):
        # The whole reason empties are dropped rather than trimmed: an empty
        # name is a substring of every overview row -- see the test below.
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                trailing, doubled, spaced_empty = self.parsed(key, [
                    "Amarr Chapel,",
                    "Amarr Chapel,,Survey Ship",
                    "Amarr Chapel, , Survey Ship",
                ])
                self.assertEqual(trailing, ["Amarr Chapel"])
                self.assertEqual(doubled, ["Amarr Chapel", "Survey Ship"])
                self.assertEqual(spaced_empty, ["Amarr Chapel", "Survey Ship"])

    def test_a_key_with_no_value_at_all_yields_nothing(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertEqual(self.parsed(key, ["", "   ", ","]),
                                 [[], [], []])

    def test_an_empty_name_would_match_every_overview_row(self):
        """Which is what the dropping is for, stated as the client's own rule.

        Both list matchers end in a substring test, so this is the property that
        makes an empty entry dangerous rather than merely useless. Asserted by
        running the matcher rather than by reading it, because if this ever
        stopped being true the dropping above would look like fussiness.
        """
        matches_anything, matches_nothing = self.repl.booleans([
            'stringContainsIgnoringCase "" "Amarr Chapel"',
            'stringContainsIgnoringCase "Amarr Chapel" ""',
        ])
        self.assertTrue(matches_anything,
                        "an empty name is a substring of every row")
        self.assertFalse(matches_nothing)

    def test_repeating_the_key_still_accumulates(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                field = NAME_LIST_SETTINGS[key]
                self.assertEqual(
                    self.repl.names(field, ["%s=Amarr Chapel\n%s=Survey Ship"
                                            % (key, key)]),
                    [["Survey Ship", "Amarr Chapel"]])

    def test_the_two_orderings_differ_and_both_are_intended(self):
        # A repeated key prepends, so the last line is tried first; a list on one
        # line keeps the order it is written in. Mixing the two forms therefore
        # does not commute, which is exactly what makes collapsing repeated lines
        # into one a reordering unless the list is written in reverse.
        field = NAME_LIST_SETTINGS["approach-object"]
        in_lines, in_one_line = self.repl.names(field, [
            "approach-object=A\napproach-object=B\napproach-object=C",
            "approach-object=C, B, A",
        ])
        self.assertEqual(in_lines, ["C", "B", "A"])
        self.assertEqual(in_one_line, in_lines)

    def test_other_settings_are_untouched_by_this(self):
        # `decline-mission` is deliberately still single-value: a mission name is
        # prose from the agent's own text rather than an overview label, and it
        # was not asked for here. This pins that it was left alone rather than
        # half-converted. `avoid-rat` was checked beside it until #125, which
        # removed that setting from this bot -- it was parsed into a field no
        # decision ever read; see `test_avoid_rat_removed.py`.
        self.assertEqual(
            self.repl.names("missionNamesToDecline",
                            ["decline-mission=Worlds Collide, Recon"]),
            [["Worlds Collide, Recon"]])


class TheLauncherDefaultsStillMeanWhatTheyMeant(unittest.TestCase):
    """`run_mission.sh` is the only settings string anyone runs unedited.

    Collapsing its nine `approach-object=` lines into one is the change's own
    payoff and its own risk: repeated keys prepend and a list does not, so the
    collapsed line is a silent re-prioritisation unless it is written in the
    reverse of the old file order. `approachConfiguredObjectIfPresent` takes the
    first match on the grid, so the order is what the bot flies at.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.settings = launcher_default_settings()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_launcher_settings_string_parses_at_all(self):
        # A settings string the bot rejects starts a run with none of them,
        # which is the whole file silently doing nothing.
        self.assertEqual(self.repl.parses([self.settings]), [True])

    def test_the_approach_objects_are_the_same_names_in_the_same_order(self):
        self.assertEqual(
            self.repl.names("approachObjectNames", [self.settings]),
            [LAUNCHER_APPROACH_OBJECTS])

    def test_the_preferred_wrecks_are_the_same_names_in_the_same_order(self):
        self.assertEqual(
            self.repl.names("preferWreckNames", [self.settings]),
            [LAUNCHER_PREFER_WRECKS])

    def test_no_default_name_is_empty(self):
        for field in ("attackObjectNames", "approachObjectNames",
                      "preferWreckNames"):
            with self.subTest(field):
                names = self.repl.names(field, [self.settings])[0]
                self.assertTrue(names)
                self.assertNotIn("", [name.strip() for name in names])


class OneSplitterForAllThree(unittest.TestCase):
    """Read out of the source, because a second copy would drift silently.

    This repo has been bitten by two implementations of one idea before. A
    settings handler that trims its own value still compiles, still parses a
    single name correctly, and differs only on the input nobody tests.
    """

    def setUp(self):
        self.source = bot_source()
        start = self.source.index("parseBotSettings =")
        self.body = self.source[start:self.source.index("\n\n\n", start)]

    def handler(self, key):
        start = self.body.index('( "%s"' % key)
        return self.body[start:self.body.index("         , (", start)]

    def test_every_name_list_setting_goes_through_the_shared_splitter(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertIn("splitSettingIntoNames", self.handler(key))

    def test_none_of_them_trims_its_own_value_instead(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertNotIn("String.trim", self.handler(key))

    def test_the_splitter_still_drops_empties(self):
        start = self.source.index("splitSettingIntoNames =")
        body = self.source[start:self.source.index("\n\n", start)]
        self.assertIn("String.split", body)
        self.assertIn("String.trim", body)
        self.assertIn("String.isEmpty", body)


class TheHelpTextSaysSo(unittest.TestCase):
    """`--help` is generated from the bot's own header, so the header is the docs.

    `bot_help.py` reads the `## Configuration Settings` section and every key
    `parseBotSettings` accepts, which is why a setting changing shape needs no
    launcher edit -- but it also means a header still describing the old shape is
    the only documentation anyone sees.
    """

    def setUp(self):
        self.source = bot_source()

    def section(self, key):
        start = self.source.index("+ `%s` :" % key)
        # The next entry, found by shape rather than by a fixed indent. These
        # bullets live inside the module's doc comment, and elm-format owns the
        # indentation of that block -- it currently sets them six spaces deep
        # where this used to assume three. Anchoring on the exact indent made
        # the whole settings documentation unreadable to this test the first
        # time the formatter ran over the file.
        #
        # Bounded by the end of the doc comment when there is no next bullet,
        # never by the end of the file: a section running to EOF would find
        # "comma-separated list" somewhere further down and report a setting as
        # documented when its own entry says nothing.
        following = re.compile(r"\n\s*\+ `").search(self.source, start + 1)
        end = following.start() if following else self.source.index("\n-}", start)
        return self.source[start:end]

    def test_each_name_list_setting_documents_the_comma_separated_form(self):
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertIn("comma-separated list", self.section(key))

    def test_bot_help_reports_them_as_documented_settings(self):
        # If the header stopped describing one, `bot_help.py` would fall back to
        # listing it under "Also accepted, but not described", which is the tell
        # that the two halves have drifted.
        help_text = subprocess.run(
            ["python3", os.path.join(MACOS_HOST_DIR, "bot_help.py"),
             MISSION_RUNNER_DIR],
            capture_output=True, text=True, check=True).stdout
        undocumented = help_text.split(
            "Also accepted, but not described in the bot's own header:")
        for key in NAME_LIST_SETTINGS:
            with self.subTest(key):
                self.assertIn("`%s`" % key, undocumented[0])
                self.assertIn("comma-separated list", undocumented[0])


if __name__ == "__main__":
    unittest.main()
