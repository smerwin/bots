"""Tests for saxrat's three remaining list settings splitting on commas.

Issue #182. saxrat has five settings that build a list of names, and two of them
split a comma-separated value while three did not:

    accept-fleet-invite-from     repeatable, splits
    follow-fleet-broadcast-from  repeatable, splits
    hunt-system                  repeatable, did not split
    anomaly-name                 repeatable, did not split
    avoid-rat                    repeatable, did not split

`splitSettingIntoNames` arrived with the fleet settings and the three older ones
were left on `String.trim`, so a comma-separated value parsed with **no
complaint** into one entry that is not a system, an anomaly or a rat. That is
this repo's signature failure in the settings parser: `hunt-system=A, B, C` then
had the bot ask the host to set the autopilot destination to the whole string,
which `resolve_name` cannot resolve and which parks the run; `anomaly-name`
matched no anomaly and looked merely unlucky; and `avoid-rat` matched no rat,
which engages one that should have been left alone.

**The claim that made the fleet split safe turned out to be false, and these
cases are where that was found.** `splitSettingIntoNames`' own doc comment said
a name the splitter would cut "can still be given a line of its own", because
every setting using it is also repeatable. It cannot: the split is applied to
the value of *every* line, so `avoid-rat=Foo, Bar` is two entries wherever it is
written, and a name that really contains a comma is not expressible in either
form. `TheCommaIsUnconditionalTest` executes that rather than reasoning about it,
and the comment now says what repeatability actually buys -- that nothing forces
the comma form, so one name per line parses to exactly what it always did.

What that costs is stated rather than hidden. A character name and a solar system
name cannot contain a comma, so `hunt-system` and the two fleet settings lose
nothing. `anomaly-name` and `avoid-rat` are matched against the probe scanner's
Name column and against an overview row, and nothing here has established what
those columns may contain.

The parser is executed through the real `Bot.elm` in `elm repl` via the shared
harness; the wiring and the header text `--help` prints are read out of the
source through a whitespace-collapsing reader.

**No case here reads the recorded corpus, deliberately.** Nothing in this change
is a client string or a calibrated threshold -- the parser answers for itself,
and a log could only show that an operator once typed a comma, which the issue
already records. Nothing here reads a live game client, a bot, or the game log
directory either.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")
RUN_SAXRAT = os.path.join(
    REPO_DIR, "tools", "macos-host", "run_saxrat.sh")

# The two entries `defaultBotSettings` ships, which `anomaly-name` prepends to
# rather than replacing. That is pre-existing behaviour and #182 does not touch
# it; it is written down here because every `anomaly-name` answer below carries
# it, and a case that did not expect it would read as a split gone wrong.
DEFAULT_ANOMALY_NAMES = ["sansha rally point", "angel rally point"]

# The five settings that build a list of names, and the field each fills.
LIST_SETTINGS = {
    "hunt-system": "huntSystemNames",
    "anomaly-name": "anomalyNames",
    "avoid-rat": "avoidRats",
    "accept-fleet-invite-from": "acceptFleetInviteFrom",
    "follow-fleet-broadcast-from": "followFleetBroadcastFrom",
}

# The three #182 changed.
SPLIT_ADDED_TO = ("hunt-system", "anomaly-name", "avoid-rat")


class SaxratRepl(ElmRepl):
    """The shared harness, pointed at saxrat."""

    def __init__(self, **kwargs):
        super().__init__(prefix="saxrat-comma-split-", app_dir=SAXRAT_DIR,
                         **kwargs)


def source_of(path):
    with open(path, encoding="utf-8") as source:
        return source.read()


def collapsed(text):
    """Source text with every run of whitespace reduced to one space.

    PR #58's reason: what these assertions mean is the structure, and
    `elm-format` owns where the lines break.
    """
    return " ".join(text.split())


def settings_handler(source, key):
    """The `parseBotSettings` entry for `key`, sliced by indentation.

    Not by "up to the next ` name = `" and not by "up to the closing brace":
    every handler here builds a record literal, and a reader that stops at its
    opening brace reads none of the assignment inside it. PRs #147, #156, #159
    and #162 each paid for that once, and the assertion that passes having read
    nothing is exactly what this file exists to prevent.
    """
    lines = source.splitlines()
    opening = '( "%s"' % key
    for index, line in enumerate(lines):
        if line.strip().startswith(", " + opening) or line.strip() == opening:
            indent = len(line) - len(line.lstrip())
            body = [line]
            for following in lines[index + 1:]:
                if following.strip() and (
                        len(following) - len(following.lstrip())) <= indent:
                    break
                body.append(following)
            return "\n".join(body)
    raise AssertionError("no parseBotSettings entry for %r" % key)


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


def elm_string_list(values):
    return "[ " + ", ".join(elm_string(value) for value in values) + " ]"


def parses_to(setting_string, field, expected):
    """An expression asking the shipped parser what one settings string gives."""
    return ('(parseBotSettings %s |> Result.map .%s) == Ok %s'
            % (elm_string(setting_string), field, elm_string_list(expected)))


def launcher_default_settings():
    """The settings string `run_saxrat.sh` passes when nobody overrides it."""
    match = re.search(r'^SETTINGS="(.*?)"$', source_of(RUN_SAXRAT),
                      re.DOTALL | re.MULTILINE)
    assert match, "run_saxrat.sh no longer defines SETTINGS the way this reads it"
    return match.group(1)


class TheThreeSettingsSplitOnCommasTest(unittest.TestCase):
    """The whole of #182, asked of the shipped parser."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_hunt_system_splits_one_line_into_systems(self):
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "hunt-system=Hamse, Lashkai, Zhilshinou",
                "huntSystemNames", ["Hamse", "Lashkai", "Zhilshinou"])]),
            [True])

    def test_anomaly_name_splits_one_line_into_names(self):
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "anomaly-name=sansha hideaway, sansha refuge", "anomalyNames",
                ["sansha hideaway", "sansha refuge"] + DEFAULT_ANOMALY_NAMES)]),
            [True])

    def test_avoid_rat_splits_one_line_into_names(self):
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "avoid-rat=Infested Carrier, Sunder Alvi", "avoidRats",
                ["Infested Carrier", "Sunder Alvi"])]),
            [True])

    def test_whitespace_around_each_entry_is_trimmed(self):
        """Not only around the value, which `AppSettings` already trimmed."""
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "hunt-system=  Hamse ,   Lashkai  ", "huntSystemNames",
                ["Hamse", "Lashkai"])]),
            [True])

    def test_a_trailing_comma_is_dropped_rather_than_kept(self):
        """The splitter's own rule: the other names still carry what was meant."""
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "avoid-rat=Infested Carrier,", "avoidRats",
                ["Infested Carrier"])]),
            [True])

    def test_a_value_with_no_comma_is_one_entry_exactly_as_before(self):
        """The control: every settings string in this repo is of this shape."""
        self.assertEqual(
            self.repl.evaluate([
                parses_to("hunt-system=Irnin", "huntSystemNames", ["Irnin"]),
                parses_to("avoid-rat=Infested Carrier", "avoidRats",
                          ["Infested Carrier"]),
                parses_to("anomaly-name=sansha hideaway", "anomalyNames",
                          ["sansha hideaway"] + DEFAULT_ANOMALY_NAMES),
            ]),
            [True, True, True])


class TheSettingsAreStillRepeatableTest(unittest.TestCase):
    """Split *as well as* repeatable, which is what makes the change free.

    The issue is explicit that keeping both is the point: an existing settings
    string writes one name per line and must parse to exactly what it did.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_each_of_the_three_still_takes_a_line_per_name(self):
        self.assertEqual(
            self.repl.evaluate([
                parses_to("hunt-system=A\nhunt-system=B", "huntSystemNames",
                          ["A", "B"]),
                parses_to("avoid-rat=A\navoid-rat=B", "avoidRats", ["B", "A"]),
                parses_to("anomaly-name=A\nanomaly-name=B", "anomalyNames",
                          ["B", "A"] + DEFAULT_ANOMALY_NAMES),
            ]),
            [True, True, True])

    def test_repeated_lines_and_a_comma_list_combine(self):
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "hunt-system=A, B\nhunt-system=C", "huntSystemNames",
                ["A", "B", "C"])]),
            [True])

    def test_the_hunt_circuit_keeps_the_order_it_was_written_in(self):
        """`nextHuntSystem` indexes this list, so the order is the circuit.

        Both forms and their combination, because appending the split entries in
        the wrong place would reverse a circuit while every other case here
        still passed.
        """
        self.assertEqual(
            self.repl.evaluate([parses_to(
                "hunt-system=A, B\nhunt-system=C, D", "huntSystemNames",
                ["A", "B", "C", "D"])]),
            [True])

    def test_the_launcher_s_own_settings_string_still_parses(self):
        """`run_saxrat.sh` writes one `anomaly-name` per line and no commas."""
        settings = launcher_default_settings()
        self.assertIn("anomaly-name=", settings)
        self.assertNotIn(",", settings)
        expected = [line.split("=", 1)[1].strip()
                    for line in reversed(settings.splitlines())
                    if line.startswith("anomaly-name=")]
        self.assertEqual(
            self.repl.evaluate(
                [parses_to(settings, "anomalyNames",
                           expected + DEFAULT_ANOMALY_NAMES)]),
            [True])


class TheCommaIsUnconditionalTest(unittest.TestCase):
    """The claim the doc comment used to make, executed and found false.

    It said a name the splitter would cut "can still be given a line of its
    own". The split is applied to the value of every line, so it cannot be --
    and the cost of that falls on `anomaly-name` and `avoid-rat`, whose names
    come from the client's own columns rather than from EVE's character-naming
    rules.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_a_name_with_a_comma_is_split_even_on_a_line_of_its_own(self):
        self.assertEqual(
            self.repl.evaluate([
                parses_to("avoid-rat=Foo, Bar", "avoidRats", ["Foo", "Bar"]),
                parses_to("anomaly-name=Foo, Bar", "anomalyNames",
                          ["Foo", "Bar"] + DEFAULT_ANOMALY_NAMES),
            ]),
            [True, True])

    def test_so_no_settings_string_yields_that_name_whole(self):
        """Stated as the negative it is: there is no form that expresses it."""
        self.assertEqual(
            self.repl.evaluate([
                '(parseBotSettings "avoid-rat=Foo, Bar"'
                ' |> Result.map .avoidRats) /= Ok ["Foo, Bar"]',
                '(parseBotSettings "avoid-rat=Foo,Bar"'
                ' |> Result.map .avoidRats) /= Ok ["Foo,Bar"]',
            ]),
            [True, True])

    def test_the_doc_comment_no_longer_makes_the_false_claim(self):
        handler = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertNotIn(
            "so a name this splitter would cut can still be given a line of "
            "its own", handler)

    def test_the_doc_comment_states_the_cost_on_the_two_client_named_lists(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn("nothing here has established what those columns may "
                      "contain", source)


class AnEmptyValueAddsNoEntryTest(unittest.TestCase):
    """A behaviour change #182 carries, recorded rather than left to be found.

    `hunt-system=` used to append `""` to the circuit, which is a destination
    the host cannot resolve; `avoid-rat=` and `anomaly-name=` used to add an
    entry matching only a nameless rat or anomaly. Going through
    `splitSettingIntoNames` drops it, which is that helper's documented rule for
    an empty *entry*.

    That is deliberately **not** what the two fleet settings do -- those are on
    `valueTypeNonEmptyString` and answer `Err`, PR #116's rule for a wholly
    empty value. Whether these three should join them is a second behaviour
    change with its own cost (an `Err` ends the session) and is not #182; the
    cases below pin which answer each setting gives so that nobody has to guess.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_empty_value_adds_nothing_to_the_three(self):
        self.assertEqual(
            self.repl.evaluate([
                parses_to("hunt-system=", "huntSystemNames", []),
                parses_to("avoid-rat=", "avoidRats", []),
                parses_to("anomaly-name=", "anomalyNames",
                          DEFAULT_ANOMALY_NAMES),
            ]),
            [True, True, True])

    def test_the_fleet_settings_still_refuse_an_empty_value(self):
        self.assertEqual(
            self.repl.evaluate([
                '(parseBotSettings "accept-fleet-invite-from="'
                ' |> Result.toMaybe) == Nothing',
                '(parseBotSettings "follow-fleet-broadcast-from="'
                ' |> Result.toMaybe) == Nothing',
            ]),
            [True, True])

    def test_an_empty_circuit_is_still_the_default_with_no_setting(self):
        self.assertEqual(
            self.repl.evaluate([parses_to("", "huntSystemNames", [])]),
            [True])


class TheFleetSettingsAreUnchangedTest(unittest.TestCase):
    """The two that already split are asserted beside the three that now do."""

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(SaxratRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_still_split_and_are_still_repeatable(self):
        self.assertEqual(
            self.repl.evaluate([
                parses_to("accept-fleet-invite-from=A, B",
                          "acceptFleetInviteFrom", ["A", "B"]),
                parses_to("follow-fleet-broadcast-from=A\n"
                          "follow-fleet-broadcast-from=B",
                          "followFleetBroadcastFrom", ["A", "B"]),
            ]),
            [True, True])


class EveryListSettingGoesThroughTheOneHelperTest(unittest.TestCase):
    """The wiring, read out of the source.

    Asserted per handler rather than by counting call sites, so that adding a
    sixth list setting is not silently fine -- it has to be added here, which is
    where somebody notices it needs the helper.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def test_each_of_the_five_handlers_calls_the_splitter(self):
        for key, field in sorted(LIST_SETTINGS.items()):
            handler = collapsed(settings_handler(self.source, key))
            self.assertIn("splitSettingIntoNames", handler,
                          "%s does not split its value" % key)
            self.assertIn(field, handler)

    def test_no_list_handler_still_builds_an_entry_with_string_trim(self):
        """The shape #182 replaced, in either of the two forms it took."""
        for key in sorted(LIST_SETTINGS):
            handler = collapsed(settings_handler(self.source, key))
            self.assertNotIn("String.trim", handler,
                             "%s still trims a single entry itself" % key)

    def test_the_three_append_the_split_entries_rather_than_one_string(self):
        for key in SPLIT_ADDED_TO:
            handler = collapsed(settings_handler(self.source, key))
            self.assertIn("++", handler)
            self.assertNotIn("::", handler,
                             "%s still conses one entry" % key)

    def test_home_system_is_not_a_list_and_does_not_split(self):
        """One name, so a comma in it is the operator's business, not ours."""
        handler = collapsed(settings_handler(self.source, "home-system"))
        self.assertIn("homeSystemName = Just", handler)
        self.assertNotIn("splitSettingIntoNames", handler)

    def test_the_splitter_itself_is_unchanged(self):
        self.assertIn(
            collapsed('splitSettingIntoNames : String -> List String'
                      ' splitSettingIntoNames = String.split ","'
                      ' >> List.map String.trim'
                      ' >> List.filter (String.isEmpty >> not)'),
            collapsed(self.source))


class TheHeaderSaysSoTest(unittest.TestCase):
    """`bot_help.py` prints this section, so it is what an operator reads.

    An operator who cannot tell whether commas work is the whole of #182's
    cost -- the value parsed either way and only the behaviour differed.
    """

    def setUp(self):
        self.source = source_of(SAXRAT_BOT_ELM)

    def _bullet(self, key):
        match = re.search(r"^\s*\+ `%s`.*$" % re.escape(key), self.source,
                          re.MULTILINE)
        self.assertIsNotNone(match, "no header bullet for %s" % key)
        return collapsed(match.group(0))

    def test_each_of_the_three_bullets_mentions_the_comma(self):
        for key in SPLIT_ADDED_TO:
            self.assertIn("comma", self._bullet(key),
                          "%s's bullet does not say commas separate" % key)

    def test_each_of_the_three_bullets_still_says_it_is_repeatable(self):
        for key in SPLIT_ADDED_TO:
            bullet = self._bullet(key)
            self.assertTrue(
                "multiple times" in bullet or "several times" in bullet,
                "%s's bullet no longer says it repeats" % key)

    def test_the_two_name_bullets_say_the_comma_always_separates(self):
        """The false-claim correction reaches the text `--help` prints too."""
        for key in ("anomaly-name", "avoid-rat"):
            self.assertIn("cannot be written here in either form",
                          self._bullet(key))


class TheMissionRunnerIsNotAuditedHereTest(unittest.TestCase):
    """#182 is scoped to saxrat, and this records what that leaves.

    The precedent is `TheMissionRunnerStillLocksOnePerStepTest`: a sibling app
    sharing a shape is written down rather than left as a claim, so a later
    audit has the fact instead of a search.

    The mission runner's three *name* lists already split. Its one list that
    does not is `decline-mission`, and it differs in kind rather than by
    oversight: it is matched as a **substring** of the offered mission name,
    where every setting in this file is matched whole. Splitting a substring
    filter is a different question with a different cost, and nothing here
    answers it.
    """

    def setUp(self):
        self.source = source_of(MISSION_RUNNER_BOT_ELM)

    def test_the_mission_runner_s_name_lists_split(self):
        for key in ("attack-object", "approach-object", "prefer-wreck"):
            self.assertIn("splitSettingIntoNames",
                          collapsed(settings_handler(self.source, key)))

    def test_decline_mission_still_does_not_split(self):
        handler = collapsed(settings_handler(self.source, "decline-mission"))
        self.assertIn("missionNamesToDecline", handler)
        self.assertNotIn("splitSettingIntoNames", handler)


if __name__ == "__main__":
    unittest.main()
