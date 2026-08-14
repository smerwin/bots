"""Tests for `anomaly-name` replacing the shipped defaults rather than joining them.

Issue #198. `BotSettings.anomalyNames` started as
`[ "sansha rally point", "angel rally point" ]` and the `anomaly-name` handler
prepended to it, so an operator naming six hideaways got those six **and** those
two. A rally point is a considerably harder site than a hideaway, so the widening
runs the wrong way: the operator who narrows the filter is the one it costs.

The header read like replacement -- "Choose the name of anomalies to take" -- and
`--help` is generated from that header, so what the bot did and what it said were
two different things. Nothing anywhere expressed "only this one".

**The defaults are kept, as a fallback rather than a floor.** An unconfigured bot
still hunts the two rally points; naming anything replaces them. That is the
second of the two readings the issue set out, and it is the one `--help` was
already promising.

**"Take anything" did not exist before and does now.** The read site carried a
`List.isEmpty` shortcut meaning "no names, take any combat anomaly", which could
never fire: the handler only ever prepends, so the list was never empty while it
started with two entries. That shortcut is gone and `anomaly-name=*` is the
operator's way to say it, through #188's prefix rule.

The rules are executed through the real `Bot.elm` in `elm repl` rather than
restated here. The settings string is put through the real parser, so what is
asserted is what an operator's file would actually produce.

Nothing here reads a live game client, a bot, or the game log directory.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
BOT_HELP = os.path.join(REPO_DIR, "tools", "macos-host", "bot_help.py")

PREAMBLE = ("import Bot exposing (..)",)

SHIPPED = ["sansha rally point", "angel rally point"]


class SaxratRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "saxrat-anomalydefaults-repl-")
        kwargs.setdefault("app_dir", SAXRAT_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)


def settings_binding(name, settings_string):
    """`name` bound to what the real parser makes of `settings_string`."""
    return ("%s = Bot.parseBotSettings %s |> Result.toMaybe"
            % (name, elm_string(settings_string)))


def elm_string(value):
    return '"%s"' % value.replace("\\", "\\\\").replace('"', '\\"').replace(
        "\n", "\\n")


class TheDefaultsAreAFallbackTest(unittest.TestCase):
    """What the list is before anyone has named anything."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_unconfigured_bot_still_hunts_the_two_rally_points(self):
        """The defaults survive, which is the half that must not regress."""
        self.assertTrue(self.repl.evaluate(
            ["anomalyNamesInEffect Bot.defaultBotSettings == %s"
             % elm_list(SHIPPED)])[0])

    def test_the_field_itself_starts_empty(self):
        """Empty is how "nobody named one" is now represented.

        Asserted separately from the answer above, because a default that still
        carried the two entries would give the same answer while leaving the
        handler prepending to them -- which is the defect.
        """
        self.assertTrue(self.repl.evaluate(
            ["Bot.defaultBotSettings.anomalyNames == []"])[0])


class NamingOneReplacesThemTest(unittest.TestCase):
    """The defect itself, through the real parser."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def effect_of(self, settings_string):
        return self.repl.strings(
            ['(parsed |> Maybe.map (anomalyNamesInEffect >> String.join "|")'
             ' |> Maybe.withDefault "PARSE FAILED")'],
            [settings_binding("parsed", settings_string)])[0]

    def test_one_name_is_the_whole_list(self):
        self.assertEqual(self.effect_of("anomaly-name=Drone Horde"),
                         "Drone Horde")

    def test_neither_shipped_default_survives_a_naming(self):
        """The failure as an operator would meet it, named rather than counted."""
        effect = self.effect_of("anomaly-name=sansha hideaway")
        self.assertNotIn("rally point", effect)
        self.assertEqual(effect, "sansha hideaway")

    def test_several_names_are_all_of_them_and_only_them(self):
        """The shape of the launcher's own settings string."""
        effect = self.effect_of(
            "anomaly-name=sansha hideaway\n"
            "anomaly-name=sansha refuge\n"
            "anomaly-name=sansha burrow")
        self.assertEqual(sorted(effect.split("|")),
                         ["sansha burrow", "sansha hideaway", "sansha refuge"])

    def test_a_narrowing_wildcard_is_not_widened_underneath(self):
        """#198's own note: `Sansha*` was silently joined by the Angel default."""
        self.assertEqual(self.effect_of("anomaly-name=Sansha*"), "Sansha*")

    def test_take_anything_is_expressible_and_was_not(self):
        """The `List.isEmpty` shortcut meant this and could never fire."""
        self.assertTrue(self.repl.evaluate(
            ['anomalyNameMatches "Dread Assault: Blood Raider Temple" "*"',
             'anomalyNameMatches "Sansha Burrow" "*"'])[0])


class TheHelpTextSaysWhichItIsTest(unittest.TestCase):
    """`--help` is generated from the header, so the promise is testable.

    The header already read like replacement while the code appended, which is
    how this survived: an operator checking the documentation was told the truth
    about the behaviour they wanted and not about the one they had.
    """

    @classmethod
    def setUpClass(cls):
        cls.help_text = subprocess.run(
            ["python3", BOT_HELP, SAXRAT_DIR],
            capture_output=True, text=True, check=True).stdout

    def test_the_help_names_the_replacement(self):
        self.assertRegex(self.help_text,
                         r"[Nn]aming any replaces the shipped defaults")

    def test_the_help_still_names_what_the_defaults_are(self):
        """An operator has to be able to see what they are replacing."""
        for name in SHIPPED:
            self.assertIn(name, self.help_text)

    def test_the_help_says_how_to_take_everything(self):
        self.assertIn("anomaly-name=*", self.help_text)


class TheReadSiteHasNoSecondOpinionTest(unittest.TestCase):
    """One place decides what the list is.

    The filter used to consult `botSettings.anomalyNames` directly and carry its
    own empty-list shortcut beside it. Two answers to "what are we hunting" is
    what this replaces, and a second reader appearing is the regression.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = open(SAXRAT_BOT_ELM).read()

    def test_the_filter_asks_the_rule_rather_than_the_field(self):
        self.assertIn("anomalyNamesInEffect context.eventContext.botSettings",
                      re.sub(r"\s+", " ", self.source))

    def test_nothing_else_reads_the_field(self):
        """Eight uses, each accounted for, and no ninth.

        The default; the handler's four, which grew by two when #182 added the
        comma split (its lambda parameter, the record update, the
        `splitSettingIntoNames` call on the parameter, and the
        `settings.anomalyNames` it prepends to); the record field; and
        `anomalyNamesInEffect`'s two -- the emptiness test and the answer it
        gives when the list is not empty. A ninth is a second opinion about what
        is hunted, which is the shape #198 was.
        """
        uses = len(re.findall(r"\banomalyNames\b",
                              re.sub(r"\{-.*?-\}", "", self.source,
                                     flags=re.DOTALL)))
        self.assertEqual(
            uses, 8,
            "expected the default, the handler's four, the record field and the"
            " rule's two; a further use is a second opinion about what is"
            " hunted")


def elm_list(values):
    return "[ %s ]" % ", ".join('"%s"' % v for v in values)


if __name__ == "__main__":
    unittest.main()
