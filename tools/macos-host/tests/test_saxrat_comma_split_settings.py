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
Name column and against an overview row, both of which the *client* writes.

**Issue #197 is the read of those two columns, and it answers one of them.**

- `avoid-rat` is safe on the evidence there is. The recordings carry **231**
  distinct names the bots read off an overview row and **225** the client wrote
  into its own `(combat)` lines -- 245 distinct between them, across 69 of the 86
  recorded runs -- and not one contains a comma. The client's own game logs say
  it again from a source this repo does not parse: 348 distinct actors across
  360,788 `(combat)` lines in 40 sessions. What makes that a reading rather than
  a search that came up empty is that these are not plain words: they carry
  apostrophes (`Kruul's Henchman`), full stops (`R.S. Officer`), hyphens,
  brackets and a slash (`Gas/Storage Silo`).
- `anomaly-name` is **still unread, and the corpus cannot read it.** Neither bot
  ever logs the scanner's Name cell -- what a run prints is the ID
  (`We are in anomaly 'AIC-176'`) -- so the site words the launcher itself asks
  for occur in the whole corpus zero times. The only probe-scanner names anybody
  has written down are the five read off a live scanner for #188, and one of
  them is `Dread Assault: Blood Raider Temple`. A colon, which is enough to say
  this column is not the letters and spaces the other four suggest.

So the corpus half of #197 is a measurement for one setting and a recorded
inability for the other, and the cases below keep them apart on purpose. What
would settle the second is a live read of the scanner, which nobody has taken.

The parser is executed through the real `Bot.elm` in `elm repl` via the shared
harness; the wiring and the header text `--help` prints are read out of the
source through a whitespace-collapsing reader. The corpus cases read
`~/eve-bot-logs` and the client's own `~/Documents/EVE/logs/Gamelogs`, and skip
where a machine has neither -- CI is such a machine. Nothing here reads a live
game client or drives a bot.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import glob
import re
import unittest

from prerequisites import EVE_BOT_LOGS, ElmRepl, REPO_DIR, open_repl

GAME_LOGS_DIR = os.path.join(
    os.path.expanduser("~"), "Documents", "EVE", "logs", "Gamelogs")

SAXRAT_DIR = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online", "eve-online-saxrat")
SAXRAT_BOT_ELM = os.path.join(SAXRAT_DIR, "Bot.elm")
MISSION_RUNNER_BOT_ELM = os.path.join(
    REPO_DIR, "implement", "applications", "eve-online",
    "eve-online-mission-runner", "Bot.elm")
RUN_SAXRAT = os.path.join(
    REPO_DIR, "tools", "macos-host", "run_saxrat.sh")

# The two entries `defaultBotSettings` used to ship in the field itself. Since
# #198 they are a fallback supplied by `anomalyNamesInEffect` when nothing was
# named, so an answer that names anything carries exactly what was written and
# these do not appear in it. Kept because the fallback is still what an
# unconfigured bot hunts
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
                ["sansha hideaway", "sansha refuge"])]),
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
                          ["sansha hideaway"]),
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
                          ["B", "A"]),
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
                           expected)]),
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
                          ["Foo", "Bar"]),
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
        self.assertIn("both of those the _client_ writes", source)

    def test_the_doc_comment_says_which_half_is_read_and_which_is_not(self):
        """#197's answer, where the next reader of the splitter meets it.

        The sentence this replaces said neither column had been established.
        One of them now has been, and saying so without saying the other has
        not would be the more expensive half of the cost going quiet.
        """
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn("`avoid-rat`: measured, and no name carries a comma",
                      source)
        self.assertIn(
            "`anomaly-name`: still unread, and the corpus cannot read it",
            source)


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
                # Empty since #198: the field starts empty and an empty value
                # adds nothing, so what an unconfigured bot hunts is supplied by
                # `anomalyNamesInEffect` rather than carried here. The case's
                # own point -- an empty value adds no entry -- is unchanged.
                parses_to("anomaly-name=", "anomalyNames", []),
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


# -- issue #197: what the two client-written columns are recorded as holding --


# Every way a bot writes an overview row's own Name into its log. Each is one
# reading of the column `avoid-rat` is matched against, so the union of them is
# the widest answer the recordings can give to "what may that column contain".
OVERVIEW_NAME_PATTERNS = (
    # `Lock target from overview entry 'X'` -- the decision line both bots have
    # printed since before any of this.
    (b"overview entry '",
     re.compile(rb"Lock target from overview entry '(.*?)'\s*$"), "quoted"),
    # `Shooting back at 'X': the client's combat log names it ...` (#40).
    (b"Shooting back at '",
     re.compile(rb"Shooting back at '(.*?)': the client"), "quoted"),
    # `... every shot that has landed on 'X' did zero damage ...` (#90).
    (b"did zero damage",
     re.compile(rb"landed on '(.*?)' did zero damage"), "quoted"),
    # The status line's own naming of the active target, in each app's wording.
    # Cut at ` (Shield`, which is where #112's condition clause starts.
    (b"Current target: ",
     re.compile(rb"Current target: (.*?)(?: \(Shield|\.\s*$|\. )"), "single"),
    (b"| target ",
     re.compile(rb"\| target (.*?)(?: \(Shield| \|)"), "single"),
    # The two clauses that print a *list* of names.
    (b"locks in this one step",
     re.compile(rb"locks in this one step, at (.*?) -- the bar"), "list"),
    (b"named in the window: ",
     re.compile(rb"Attackers named in the window: (.*?) \(any overview"),
     "list"),
)

# The client's own combat lines, echoed into the bot's log by the host and
# written straight into its own game logs. Independent of this repo's parsing.
COMBAT_DAMAGE = re.compile(rb"\(combat\) [\d,]+ (?:to|from) (.*?) - ")
COMBAT_MISS = re.compile(rb"\(combat\) (?:Your )?(.*?) misses (.*?) completely")

# Floors, far below what the corpus this was measured on carries (231 overview
# names on 68 runs, and 348 actors in the client's own logs). They are here so
# that a search which found nothing cannot report an absence as a finding --
# `prerequisites.recorded_runs`' own rule, applied to a thin corpus rather than
# to a missing one. Below either floor the case skips; it never passes on a
# handful of names.
ENOUGH_OVERVIEW_NAMES = 50
ENOUGH_OVERVIEW_RUNS = 10
ENOUGH_CLIENT_NAMES = 50

# The site words `run_saxrat.sh` itself asks for, plus the two shipped defaults
# and the one non-Sansha name a live scanner has been seen holding. None of them
# occurs anywhere in the recordings, which is the evidence that the scanner's
# Name cell is never written down rather than that it holds nothing unusual.
SITE_WORDS = (b"Hideaway", b"Refuge", b"Burrow", b"Rally Point", b"Sanctum",
              b"Haven", b"Forsaken", b"Forlorn", b"Drone Assembly")

# Read off a live probe scanner and kept in `test_saxrat_anomaly_name_wildcard`
# for #188. Repeated rather than imported: this file asks a different question
# of them, and a later edit there that dropped the punctuated one would
# otherwise silently weaken the case below rather than fail it.
NAMES_READ_OFF_A_LIVE_SCANNER = (
    "Sansha Burrow",
    "Sansha Hideaway",
    "Sansha Refuge",
    "Drone Assembly",
    "Dread Assault: Blood Raider Temple",
)


def let_binding(source, name):
    """A `let` binding's own text, sliced by indentation.

    Not "up to the next ` name = `" and not "up to the closing brace": the
    binding read here builds a pipeline through a record, and a reader that
    stops at a brace reads none of it. `settings_handler` above carries the
    same correction and the same list of PRs that paid for it.
    """
    lines = source.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(name + " ="):
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for following in lines[index + 1:]:
            if following.strip() and \
                    len(following) - len(following.lstrip()) <= indent:
                break
            block.append(following)
        return "\n".join(block)
    raise AssertionError("no let binding named %s" % name)


def names_in_a_quoted_list(blob):
    """The names in a `'A', 'B', 'C'` clause, split on the separator.

    Split rather than matched with `'([^']*)'`, and that is not a nicety: a name
    can carry an apostrophe -- `Kruul's Henchman` is in the corpus 501 times --
    and a quote-pair match over such a list yields `Kruul` and `, ` instead of
    two names. The second of those *contains a comma*, so the naive reader
    reports a finding that is entirely its own doing, which is how this was
    caught.
    """
    text = blob.strip()
    if not (text.startswith(b"'") and text.endswith(b"'")):
        return []
    return text[1:-1].split(b"', '")


def decoded(raw):
    return raw.strip().decode("utf-8", "replace").strip()


_recorded_names = None


def names_the_recordings_carry():
    """Every object name in `~/eve-bot-logs`, by where it was read.

    One pass over the whole corpus -- 1.6 GB and about two minutes on the
    machine this was written on -- cached, because two classes ask about it.
    """
    global _recorded_names
    if _recorded_names is not None:
        return _recorded_names

    overview = set()
    combat = set()
    overview_runs = set()
    runs_with_a_name = set()
    site_word_hits = 0
    for path in sorted(glob.glob(os.path.join(EVE_BOT_LOGS, "*.log"))):
        run = os.path.basename(path)
        with open(path, "rb") as handle:
            for line in handle:
                for marker, pattern, shape in OVERVIEW_NAME_PATTERNS:
                    if marker not in line:
                        continue
                    match = pattern.search(line)
                    if not match:
                        continue
                    if shape == "list":
                        found = names_in_a_quoted_list(match.group(1))
                    else:
                        found = [match.group(1)]
                    for raw in found:
                        name = decoded(raw)
                        # `objectName` is a `Maybe` and the decision line
                        # renders `Nothing` as the empty string, which names
                        # nothing and is not a reading of the column.
                        if not name or name == "None":
                            continue
                        overview.add(name)
                        overview_runs.add(run)
                        runs_with_a_name.add(run)
                if b"(combat)" in line:
                    for match in COMBAT_DAMAGE.finditer(line):
                        combat.add(decoded(match.group(1)))
                    for match in COMBAT_MISS.finditer(line):
                        combat.add(decoded(match.group(1)))
                        combat.add(decoded(match.group(2)))
                    runs_with_a_name.add(run)
                for word in SITE_WORDS:
                    if word in line:
                        site_word_hits += 1

    combat.discard("")
    _recorded_names = {
        "overview": overview,
        "combat": combat,
        "overview_runs": overview_runs,
        "runs": runs_with_a_name,
        "site_word_hits": site_word_hits,
    }
    return _recorded_names


def punctuation_in(names):
    """Every character in `names` that is neither alphanumeric nor a space."""
    return {char for name in names for char in name
            if not (char.isalnum() or char == " ")}


class TheOverviewColumnCarriesNoCommaTest(unittest.TestCase):
    """Issue #197's first half, read off the recordings.

    `avoid-rat` is matched whole against an overview row's Name, so the split
    above makes a comma-bearing name unmatchable -- and unmatchable in the
    direction that *engages* a rat which should have been left alone. Whether
    such a name exists was the open question this file's own docstring recorded.

    It does not, on 245 distinct names between the two independent readings the
    corpus carries, and the answer is a measurement rather than a search that
    happened to come up empty: **these names are not plain words.** They carry
    apostrophes (`Kruul's Henchman`), full stops (`R.S. Officer`), hyphens,
    brackets and a slash (`Gas/Storage Silo`), so a column that admitted commas
    had every opportunity to show one.

    Asserted as *relations* rather than as those counts, so a corpus that grows
    -- or a machine holding a different subset of it -- cannot turn a true claim
    red.
    """

    @classmethod
    def setUpClass(cls):
        cls.found = names_the_recordings_carry()
        if len(cls.found["overview"]) < ENOUGH_OVERVIEW_NAMES \
                or len(cls.found["overview_runs"]) < ENOUGH_OVERVIEW_RUNS:
            raise unittest.SkipTest(
                "no recorded runs carrying enough overview names in "
                "~/eve-bot-logs to say anything about what that column may "
                "contain -- an absence found in a handful of names is not a "
                "finding")

    def test_no_name_the_bots_read_off_an_overview_row_carries_a_comma(self):
        carrying = sorted(n for n in self.found["overview"] if "," in n)
        self.assertEqual(carrying, [])

    def test_no_name_the_client_wrote_in_a_combat_line_carries_a_comma(self):
        """The same question asked of a source this repo does not parse."""
        carrying = sorted(n for n in self.found["combat"] if "," in n)
        self.assertEqual(carrying, [])

    def test_each_reading_on_its_own_carries_other_punctuation(self):
        """What makes the absence above a reading rather than a narrow sample.

        Without this the case would pass just as happily on a client whose
        object names were letters and spaces, where "no comma" says nothing
        about whether a comma is possible.

        Asked of **each** source separately rather than of the union, which is
        the hole the first version had: pooling them let one reading go plain
        while the other carried the punctuation for it, so a defect that
        flattened the bots' own parsing would have passed on the strength of
        the client's `(combat)` lines. Found by mutation, which is what that
        convention is for.
        """
        for where in ("overview", "combat"):
            seen = punctuation_in(self.found[where])
            self.assertIn("'", seen, "%s names carry no apostrophe" % where)
            self.assertTrue(
                seen - {"'"},
                "the only punctuation in any %s name is an apostrophe, so this "
                "reading cannot say a comma is unusual" % where)

    def test_both_readings_are_wide_and_agree(self):
        """Two sources rather than one, and neither is a subset of the other.

        The bots' own decision lines and the client's `(combat)` lines are
        different readings of the same objects -- CLAUDE.md records them as the
        same string where both exist -- so a defect in this repo's overview
        parsing cannot hide a comma from both.
        """
        self.assertGreaterEqual(len(self.found["overview"]),
                                ENOUGH_OVERVIEW_NAMES)
        self.assertGreaterEqual(len(self.found["combat"]),
                                ENOUGH_OVERVIEW_NAMES)
        self.assertTrue(self.found["overview"] - self.found["combat"])
        self.assertTrue(self.found["combat"] - self.found["overview"])


class TheClientsOwnLogsSayTheSameTest(unittest.TestCase):
    """The same question, of the client's own game logs rather than a bot's.

    `~/Documents/EVE/logs/Gamelogs` is written by EVE and covers sessions no bot
    flew, so it is the widest set of client-written object names on this machine
    and owes nothing to how this repo parses a UI tree.
    """

    @classmethod
    def setUpClass(cls):
        names = set()
        for path in sorted(glob.glob(os.path.join(GAME_LOGS_DIR, "*.txt"))):
            with open(path, "rb") as handle:
                for line in handle:
                    if b"(combat)" not in line:
                        continue
                    # EVE colours these lines, and a tag would otherwise be read
                    # as part of the name.
                    plain = re.sub(rb"<[^>]*>", b"", line)
                    for match in COMBAT_DAMAGE.finditer(plain):
                        names.add(decoded(match.group(1)))
                    for match in COMBAT_MISS.finditer(plain):
                        names.add(decoded(match.group(1)))
                        names.add(decoded(match.group(2)))
        names.discard("")
        cls.names = names
        if len(names) < ENOUGH_CLIENT_NAMES:
            raise unittest.SkipTest(
                "no recorded game logs in ~/Documents/EVE/logs/Gamelogs "
                "carrying enough named objects to say anything about what the "
                "client may write")

    def test_no_object_the_client_names_carries_a_comma(self):
        self.assertEqual(sorted(n for n in self.names if "," in n), [])

    def test_and_the_client_does_write_punctuation_into_a_name(self):
        seen = punctuation_in(self.names)
        self.assertTrue(
            seen - {"'"},
            "these logs name nothing carrying punctuation beyond an "
            "apostrophe, so they cannot say a comma is unusual")


class TheScannerNameColumnIsNeverWrittenDownTest(unittest.TestCase):
    """Issue #197's second half: the corpus cannot answer it, and why.

    `anomaly-name` is matched against the probe scanner's Name cell, and
    **nothing in either bot ever logs that cell.** The one thing printed about
    an anomaly is the ID the scanner gives it (`We are in anomaly 'AIC-176'`),
    which is what makes this unanswerable from recordings rather than merely
    unanswered: there is no reading to go back to.

    Two halves, and the second is what would announce the day it changes. The
    source says the cell is read into a `Bool` and nowhere else; the corpus says
    no site name the launcher itself asks for occurs in it. A run that started
    printing one would fail the second, which is exactly the run whose log could
    settle the question.
    """

    def test_the_name_cell_is_read_once_and_only_into_a_verdict(self):
        source = source_of(SAXRAT_BOT_ELM)
        self.assertEqual(
            source.count('Dict.get "Name"'), 1,
            "the scanner's Name cell is read somewhere new -- if that place "
            "logs it, the corpus can answer #197 and this file should say so")
        binding = collapsed(let_binding(source, "matchesAnomalyNameFromSettings"))
        self.assertIn('Dict.get "Name"', binding)
        self.assertIn("anomalyNameMatches", binding)
        self.assertIn("Maybe.withDefault False", binding,
                      "the name reaches something other than a Bool")

    def test_the_anomaly_a_run_names_is_the_id_and_not_the_name(self):
        source = collapsed(source_of(SAXRAT_BOT_ELM))
        self.assertIn('"We are in anomaly \'" ++ anomalyID', source)

    def test_no_recorded_run_carries_a_scanner_site_name(self):
        found = names_the_recordings_carry()
        if not found["runs"]:
            raise unittest.SkipTest(
                "no recorded runs in ~/eve-bot-logs, so what they do and do "
                "not name cannot be consulted here")
        self.assertEqual(
            found["site_word_hits"], 0,
            "a recorded run names an anomaly site, so the scanner's Name "
            "column is being written down after all and #197's second half is "
            "answerable from the corpus")


class TheOnlyScannerNamesAnybodyHasWrittenDownTest(unittest.TestCase):
    """Five names, read off a live scanner for #188, and what they do say.

    They are not evidence that no anomaly name carries a comma -- five is not a
    sample. What they *are* evidence of is that this column is not letters and
    spaces: `Dread Assault: Blood Raider Temple` carries a colon, so the
    naming-rules argument that covers a character or a solar system has nothing
    to say here.
    """

    def test_none_of_them_carries_a_comma(self):
        self.assertEqual(
            [n for n in NAMES_READ_OFF_A_LIVE_SCANNER if "," in n], [])

    def test_but_one_of_them_carries_punctuation_the_other_four_do_not(self):
        punctuated = [n for n in NAMES_READ_OFF_A_LIVE_SCANNER
                      if punctuation_in([n])]
        self.assertEqual(punctuated, ["Dread Assault: Blood Raider Temple"])

    def test_the_wildcard_file_still_records_where_they_came_from(self):
        """The provenance, since this file repeats the names rather than importing them."""
        wildcard = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "test_saxrat_anomaly_name_wildcard.py")
        source = collapsed(source_of(wildcard))
        self.assertIn("Read off the live probe scanner, verbatim.", source)
        for name in NAMES_READ_OFF_A_LIVE_SCANNER:
            self.assertIn('"%s"' % name, source)


if __name__ == "__main__":
    unittest.main()
