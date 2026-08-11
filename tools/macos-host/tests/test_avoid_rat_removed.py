"""Tests for a setting the mission runner documented, parsed and never read.

Issue #125. `avoid-rat` was listed in `eve-online-mission-runner`'s own header,
reported by `--help` because `bot_help.py` generates that from the header, and
parsed into `BotSettings.avoidRats` -- and **no decision anywhere in that bot
ever read the field**. Three occurrences and no fourth: the default, the parser
handler, and the field in the record type. Elm has no dynamic field access, so
three occurrences is a proof that nothing consumed it rather than a search that
found nothing. An operator who set it got a bot that behaved exactly as if they
had not, with `--help` telling them otherwise.

**The argument is about this app, not about the repo.** The issue as first
written said the repo had declined to have a negative name list beside
`attack-object`'s positive one, and that is false: `eve-online-saxrat`
(`Bot.elm:772`) and `eve-online-combat-anomaly-bot` (`:442`) both implement
`avoid-rat`, wired from the overview through `getRatsToAvoidSeenInAnomaly` and
`FoundRatToAvoid` to decisions that skip a scan result or leave the anomaly.
saxrat's was proved to *execute* -- `avoid-rat = Infested Carrier` and
`shouldAvoidRatAccordingToSettings` answers `True` for `Infested Carrier`, `True`
for `infested carrier`, `False` for `Sunder Alvi`. So the true argument is the
narrower one: the mission runner documented and parsed a setting two sibling apps
implement properly, which made its copy a promise it could not keep. It is
removed rather than implemented, and can be brought back if it is ever wanted.

**A future implementation here would not be a port.** saxrat's rule is
*anomaly*-granularity: it abandons the whole anomaly a named rat is in. The
mission runner has no anomalies, and what run 27's operator wanted was to decline
one target, so the shape does not carry across.

**Removal is a settings-string change, which is the one risk it carries.**
`Common.AppSettings` answers an unrecognised key with `Unknown setting name`, so
a settings file still carrying an `avoid-rat=` line now ends the session at
startup instead of ignoring it. Nothing sets it: not `run_mission.sh`, not
`run_saxrat.sh`, not `bot_help.py`, and none of the 49 recorded runs in
`~/eve-bot-logs`. The launcher's own string is asserted below to still parse,
because that is the only settings string anyone runs unedited.

`AvoidRatIsParsedAndNeverRead` in `test_decline_mission_entries.py` was the case
that pinned the finding, by asserting the field had exactly three uses. It goes
vacuous the moment the setting is gone -- zero uses is not three -- so it is
retired and its job moves here, where the assertion is that the removal happened
and that a reintroduction cannot be silent.

**The cross-app rule is the general form of the bug**, and it is asserted over
every EVE app rather than over this one: an app whose `parseBotSettings` accepts
`avoid-rat` must also read `avoidRats` somewhere outside the default, the handler
and the record type. That is what would have gone red if #125 had been acted on
as written and saxrat's read deleted, and it is what will go red if some other
app gains the parser half without the decision half. The **converse** shape --
documented but never parsed, which ends a session at startup rather than doing
nothing -- was `eve-online-wingus`' and is issue #161's. It is still deliberately
not asserted here: `test_documented_settings_are_parsed.py` is that rule, over
every app and over both halves of a header's promise, and it imports this file's
`setting_keys` rather than copying it, so the two rules cannot come to disagree
about which keys a parser accepts.

The source is read by an **indentation-sliced** block reader rather than by one
that stops at a blank line or at a record literal. PRs #147, #156 and #159 each
paid for the latter: `parseBotSettings`' body is one long list of tuples, and a
reader that ended at its opening bracket would let every assertion about which
keys it accepts pass without reading a single one.

Confirmed by mutation, seven of them, each failing a named case: the setting put
back whole -- field, default and parser entry, with no read -- which is the silent
reintroduction and fails eight cases here including the cross-app rule; the field
and its default put back *without* the parser entry, which no repl case can see
and which `test_no_block_mentions_the_field` catches; the `+ avoid-rat` bullet
restored to the header; the paragraph that tells an operator to delete the line
gutted; saxrat's `shouldAvoidRatAccordingToSettings` read deleted; the combat
anomaly bot's deleted; and the key reader narrowed to `AppSettings.valueType`,
which is `bot_help.py`'s pattern -- the combat anomaly bot is on `PromptParser`,
so its thirteen keys read as none and the cross-app rule would pass by seeing
nothing.

Nothing here reads a live game client, a bot, or the recorded runs. The `elm
repl` cases need `elm` on PATH and the app's dependencies already fetched, which
is what `compile_bot.sh` leaves behind; without it they **fail** rather than
skipping, for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import unittest

from prerequisites import ElmRepl, REPO_DIR, open_repl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)

APPLICATIONS_DIR = os.path.join(REPO_DIR, "implement", "applications",
                                "eve-online")
MISSION_RUNNER_DIR = os.path.join(APPLICATIONS_DIR,
                                  "eve-online-mission-runner")
BOT_HELP = os.path.join(MACOS_HOST_DIR, "bot_help.py")
RUN_MISSION = os.path.join(MACOS_HOST_DIR, "run_mission.sh")

# The apps that implement `avoid-rat` and keep it. Named rather than discovered,
# so deleting one of them is a change this file notices.
APPS_THAT_IMPLEMENT_IT = ("eve-online-saxrat", "eve-online-combat-anomaly-bot")

SETTING = "avoid-rat"
FIELD = "avoidRats"

# Where the field is allowed to appear in an app that only *parses* it. Anywhere
# else is a read, which is the half the mission runner never had.
WRITE_ONLY_BLOCKS = ("defaultBotSettings", "parseBotSettings", "BotSettings")

# The settings that still name one thing each and reject an empty value. This
# used to be four; `avoid-rat` was the fourth, and its guard is what
# `test_decline_mission_entries.py` covers for the three that remain.
NAME_SETTINGS_THAT_REMAIN = ("agent-name", "decline-mission", "drone-type")


def bot_elm(app):
    path = os.path.join(APPLICATIONS_DIR, app, "Bot.elm")
    with open(path, encoding="utf-8") as source:
        return source.read()


def eve_apps():
    """Every EVE app that has a `Bot.elm` with settings to parse."""
    return sorted(
        name for name in os.listdir(APPLICATIONS_DIR)
        if os.path.isfile(os.path.join(APPLICATIONS_DIR, name, "Bot.elm")))


def top_level_blocks(source):
    """`{name: text}` for every top-level block, sliced by **indentation**.

    A block starts at a line in column 0 and runs to the next one, so a body
    that is a single long record or list literal is carried whole. The readers
    this repo reached for first stop at a blank line or at a record's opening
    brace -- PRs #147, #156 and #159 each shipped an assertion that passed
    having read nothing, and `parseBotSettings` is exactly that shape.

    A block is named by the declaration it starts with: `type alias BotSettings`
    is `BotSettings`, `defaultBotSettings :` is `defaultBotSettings`. Blocks
    that are only a comment are kept under the text they start with, because
    what this file asks is which *named* block an occurrence fell in, and an
    occurrence in a comment must not be counted as a read.
    """
    blocks = {}
    name = None
    lines = []
    for line in source.split("\n"):
        if line[:1].strip():
            if name is not None:
                blocks[name] = "\n".join(lines)
            words = line.replace("(", " ").split()
            if words[:2] == ["type", "alias"] or words[:1] == ["type"]:
                name = words[2] if words[:2] == ["type", "alias"] else words[1]
            else:
                name = words[0]
            lines = [line]
        else:
            lines.append(line)
    if name is not None:
        blocks[name] = "\n".join(lines)
    return blocks


def setting_keys(source):
    """Every key `parseBotSettings` accepts, read out of its own block.

    Matched as the first element of a tuple -- `( "avoid-rat" ,` -- rather than
    by what parses the value, because the apps do not agree on that and a rule
    asserted over all of them has to see all of them. The mission runner hands
    four keys to its own `valueTypeNonEmptyString`, which is why
    `bot_help.setting_keys`' `AppSettings.valueType` pattern would have reported
    that it never accepted `avoid-rat` at all -- the opposite of the finding.
    `eve-online-combat-anomaly-bot` and `eve-online-warp-to-0-autopilot` are on
    `PromptParser` and give each key a record, so that pattern sees none of
    theirs either. The `alternativeNames` lists are not tuple heads and so are
    not keys here; no app in the corpus has one for `avoid-rat`.
    """
    body = top_level_blocks(source).get("parseBotSettings", "")
    return re.findall(r'\(\s*"([a-z][a-z0-9-]*)"\s*,', body)


def help_text():
    """What `run_mission.sh --help` prints, from `bot_help.py` itself.

    Run as a subprocess rather than imported, which is what
    `test_settings_name_lists.py` does and for a reason worth keeping: the
    module sets `SIGPIPE` back to the default on import, so importing it into a
    test process changes how that process dies on a closed pipe. Running it is
    also the stronger assertion, since the settings text an operator reads is
    this output rather than the header the output is derived from.
    """
    return subprocess.run(
        ["python3", BOT_HELP, MISSION_RUNNER_DIR],
        capture_output=True, text=True, check=True).stdout


def advertised_keys(text):
    """The settings `--help` *offers*, which is its bullet list.

    Prose that names a setting is not an offer -- the header explains that
    `avoid-rat` was removed and that a file still carrying the line is now
    rejected, and an operator has to be able to read that. Only a bullet says
    "you may set this".
    """
    return re.findall(r"^\s*\+\s*`([a-z][a-z0-9-]*)`", text, re.MULTILINE)


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


PREAMBLE = ("import Bot exposing (..)", "import Result.Extra")


class AvoidRatRepl(ElmRepl):
    """The shared harness, plus the two questions this file asks of it."""

    def parses(self, settings_strings):
        """Whether each settings string is accepted at all."""
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def rejection_reasons(self, settings_strings):
        """The error each settings string is rejected with, or `<accepted>`."""
        return self.strings([
            'parseBotSettings %s |> Result.map (always "<accepted>") '
            "|> Result.Extra.merge" % elm_string(settings)
            for settings in settings_strings])


def repl():
    return open_repl(AvoidRatRepl, prefix="test-avoid-rat-removed-",
                     preamble=PREAMBLE)


class TheMissionRunnerNoLongerAcceptsIt(unittest.TestCase):
    """The removal, executed through the real parser rather than read.

    Every case here would have passed with the opposite assertion before #125,
    which is the point: the parser took the key and filled a field nothing read.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_key_it_used_to_accept_is_refused(self):
        # The case a silent reintroduction fails: putting the handler back makes
        # this string parse again, whatever the header says about it.
        self.assertEqual(
            self.repl.parses(["%s=Infested Carrier" % SETTING]), [False])

    def test_the_refusal_names_the_key_so_an_operator_can_delete_the_line(self):
        # This is the whole cost of the removal, and it lands on a settings file
        # rather than mid-run. It has to say which line.
        reason = self.repl.rejection_reasons(
            ["%s=Infested Carrier" % SETTING])[0]
        self.assertIn(SETTING, reason)
        self.assertIn("Unknown setting name", reason)

    def test_one_such_line_rejects_the_whole_settings_string(self):
        # `Result.Extra.combine` in `parseBotSettings`, restated as its
        # consequence: there is no partial acceptance to be surprised by later.
        self.assertEqual(
            self.repl.parses([
                "decline-mission=Survey Rendezvous\n%s=Infested Carrier"
                % SETTING]),
            [False])

    def test_the_launcher_string_anyone_runs_unedited_still_parses(self):
        # What makes the removal safe rather than merely justified.
        self.assertEqual(self.repl.parses([launcher_default_settings()]), [True])

    def test_the_settings_beside_it_were_not_taken_with_it(self):
        # The deletion touched three sites in one file; its failure mode is
        # taking a neighbour. Both halves of each remaining named setting are
        # asked for: the value it accepts, and the empty value it refuses.
        for key in NAME_SETTINGS_THAT_REMAIN:
            with self.subTest(key):
                self.assertEqual(
                    self.repl.parses(["%s=Something" % key, "%s=" % key]),
                    [True, False])


class TheFieldIsGoneFromTheMissionRunner(unittest.TestCase):
    """No occurrence at all, which is what makes the removal complete.

    The finding it replaces was "three occurrences and no read". Asserting zero
    is the same argument in the same terms, and it fails on a reintroduction that
    adds the field back without the parser key -- which the repl cases above
    would not see.
    """

    @classmethod
    def setUpClass(cls):
        cls.help = help_text()

    def setUp(self):
        self.source = bot_elm("eve-online-mission-runner")

    def test_no_block_mentions_the_field(self):
        mentions = [name for name, text in top_level_blocks(self.source).items()
                    if FIELD in text]
        self.assertEqual(mentions, [])

    def test_the_parser_does_not_accept_the_key(self):
        keys = setting_keys(self.source)
        self.assertNotIn(SETTING, keys)
        # The reader is looking at the right block: these are still there.
        for key in NAME_SETTINGS_THAT_REMAIN:
            with self.subTest(key):
                self.assertIn(key, keys)

    def test_the_help_text_no_longer_advertises_it(self):
        # `--help` is generated from this header by `bot_help.py`, so the
        # advertisement goes with the setting rather than being a second thing
        # to remember. Nor may it come back under "Also accepted, but not
        # described in the bot's own header", which is where a key the parser
        # takes and the header does not mention would be listed.
        offered = advertised_keys(self.help)
        self.assertNotIn(SETTING, offered)
        self.assertIn("agent-name", offered)
        self.assertNotIn(
            SETTING,
            "".join(self.help.split("Also accepted, but not described in the "
                                    "bot's own header:")[1:]))

    def test_the_help_text_still_tells_an_operator_what_happened_to_it(self):
        # Prose rather than a bullet: an unknown key ends the session at
        # startup, so an operator whose settings file still has the line has to
        # be able to read why it is now refused.
        self.assertIn(SETTING, self.help)
        self.assertIn("Unknown setting name", self.help)

    def test_the_guard_the_setting_shared_is_still_used(self):
        # `valueTypeNonEmptyString` was written for four settings and three
        # remain. Removing its last caller would be a different change.
        blocks = top_level_blocks(self.source)
        self.assertIn("valueTypeNonEmptyString", blocks)
        self.assertEqual(
            blocks["parseBotSettings"].count("valueTypeNonEmptyString"),
            len(NAME_SETTINGS_THAT_REMAIN))


class AnAppThatParsesItMustRead(unittest.TestCase):
    """The general form of #125, over every EVE app.

    A settings key an app accepts and never consults is a promise it cannot
    keep, and the mission runner's was found only because somebody counted
    references by hand. This is that count, automated and stated as a rule.
    """

    def read_sites(self, app):
        """Blocks mentioning the field that are not the write-only three."""
        return sorted(
            name for name, text in top_level_blocks(bot_elm(app)).items()
            if FIELD in text and name not in WRITE_ONLY_BLOCKS)

    def test_the_reader_finds_settings_in_every_app(self):
        """Without this the rule below passes for free on a shape it cannot read.

        The apps do not share a settings framework, and the first version of
        `setting_keys` here saw thirteen of `eve-online-combat-anomaly-bot`'s
        keys as none at all -- the app that most needed checking would have been
        the one silently exempted.
        """
        for app in eve_apps():
            with self.subTest(app):
                self.assertTrue(setting_keys(bot_elm(app)))

    def test_every_app_that_parses_it_also_reads_it(self):
        for app in eve_apps():
            if SETTING not in setting_keys(bot_elm(app)):
                continue
            with self.subTest(app):
                self.assertTrue(
                    self.read_sites(app),
                    "%s parses %s and no decision reads %s -- that is #125's "
                    "shape in another app" % (app, SETTING, FIELD))

    def test_the_two_apps_that_implement_it_still_do(self):
        # Named rather than discovered, so deleting saxrat's read fails here
        # instead of quietly satisfying the rule above by parsing nothing. This
        # is the mistake #125 as written would have caused.
        for app in APPS_THAT_IMPLEMENT_IT:
            with self.subTest(app):
                self.assertIn(SETTING, setting_keys(bot_elm(app)))
                self.assertIn("shouldAvoidRatAccordingToSettings",
                              self.read_sites(app))

    def test_the_mission_runner_is_the_one_that_has_neither_half(self):
        source = bot_elm("eve-online-mission-runner")
        self.assertNotIn(SETTING, setting_keys(source))
        self.assertEqual(self.read_sites("eve-online-mission-runner"), [])
