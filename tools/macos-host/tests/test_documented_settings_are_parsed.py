"""Every setting an app's own header offers has to be one its parser accepts.

Issue #161. `eve-online-wingus` documented `avoid-rat` in the `## Configuration
Settings` block that `bot_help.py` generates `--help` from, and showed it again
in the example settings string directly below -- and its `parseBotSettings` had
**no entry for the key**, its `BotSettings` no field. `Common.AppSettings`
answers an unrecognised key with `Unknown setting name 'avoid-rat'`, and
`BotFramework` answers a settings parse error with `InternalFinishSession`, so
an operator who pasted the bot's own example got a session that ended before it
started.

**This is #125 read the other way round, and the two fail in opposite
directions.** There an app parsed a setting nothing read: harmless, silent, and
discovered only because somebody counted references by hand. Here an app
documents a setting nothing parses: loud, immediate, and blamed on the operator
who followed the documentation. `AvoidRatIsParsedAndNeverRead` pinned the first
shape for one key in one app; `test_avoid_rat_removed` generalised it to
"an app that parses `avoid-rat` must read `avoidRats`". This file is the
converse rule, and it is not about `avoid-rat` at all: **every key any app's
header offers must appear in that app's `parseBotSettings`, in every app.**

**The documentation was deleted rather than the setting implemented**, and the
reasoning is checked rather than assumed. wingus has no launcher script, no
recorded run in `~/eve-bot-logs`, and exactly one commit in this repo's history
touching its `Bot.elm` (a vendored-parser sweep); the other two that touch the
app at all touch only its copy of `ParseUserInterface.elm`. It *is*
anomaly-shaped, so a port from `eve-online-saxrat` or
`eve-online-combat-anomaly-bot` -- both of which implement `avoid-rat` at
anomaly granularity, per #125's own correction -- would be a real port rather
than the wrong shape it would have been in the mission runner. Nobody has asked
for it, so the honest change is the one that stops the header promising it.

**The client's own suggestion is what settles that wingus meant something
else.** Asked for `avoid-rat`, its parser answers `Unknown setting name
'avoid-rat'. Did you mean 'hated-rat'?` -- `hated-rat` being the key wingus
actually accepts, filling `priorityRats`. So the avoid machinery was replaced
by a priority list when this bot was adapted, and the header was not updated.
That is a fact about the key rather than a promise about the feature, which is
why nothing here documents `hated-rat`: it is reported under `--help`'s "Also
accepted, but not described in the bot's own header", and a case below pins that
the new note did not accidentally take it out of that list.

## Two readers, because the header promises in two places

`--help` prints the bullets and stops before the example, so a rule built on
bullets alone would have caught #161's `:32` and missed its `:43` -- and the
example is the half an operator *pastes*. Both are read:

- **the bullets**, out of `bot_help.py`'s own rendered output rather than out of
  `Bot.elm`, because that output is what an operator reads. Run as a subprocess
  for `test_avoid_rat_removed`'s reason: the module sets `SIGPIPE` back to the
  default on import.
- **the example settings string**, out of the header's fenced block, as the
  `key = value` lines it is made of.

**A bullet can name more than one key**, which is the hazard that would make
this rule quietly weak rather than wrong. The mission runner writes
`` + `short-range-ammo` / `long-range-ammo` : ... `` and saxrat writes three
keys on one bullet, and the mission runner splits one bullet's head across two
physical lines. A per-line, one-key-per-bullet reader answers 17 and 14 where
the truth is 19 and 16, so five real keys would go unchecked with nothing to
show it. The reader joins a bullet's lines until the head's terminating colon
and takes every backticked key before it; `TheReadersCannotPassBySeeingNothing`
asserts the multi-key bullets are recovered by name.

**Keys are read out of the *head* only**, never the body, because bodies name
other settings in prose -- the mission runner's armour bullet points at
`run-away-incoming-damage-threshold` and at `plausibleHitpointsPercent`. A
body-reading version would demand that prose mentions be parseable keys and go
red on a true header.

**The parsed side is `test_avoid_rat_removed.setting_keys`, imported rather than
copied**, and that is deliberate. CLAUDE.md names the exact hazard: a reader
narrowed to `AppSettings.valueType` -- which is `bot_help.py`'s own pattern --
sees `eve-online-combat-anomaly-bot`'s thirteen `PromptParser` keys as none, so
the app most in need of checking is the one silently exempted, and the rule
passes by seeing nothing. That reader is already written, already carries that
argument, and already has a guard case; a second copy here would drift, and the
direction it would drift in is the one that makes both files pass for free.

## What it found

**Nothing else.** Run over all six EVE apps, in both directions of documentation,
wingus' `avoid-rat` is the only documented key no parser accepts -- before the
fix it was the only one, and after it there are none. The reverse mismatch
(parsed but not in the header) is common and is *not* a defect: `bot_help.py`
reports those under "Also accepted", which is the whole reason that section
exists, and four wingus keys, six saxrat keys and three mission-runner keys sit
there legitimately.

**Verified by execution where it can be.** The cross-app rule is a source read,
because there is nothing to run: a key an app never registered cannot be asked
of anything. wingus' own half is *executed* through the real `Bot.elm` in
`elm repl` -- its parser is asked what it does with the header's complete
example settings string (accepts it, where before this change it did not), with
the key the header used to offer (rejects it, naming the key), and with each key
the header still offers.

Confirmed by mutation, twelve of them, each failing a named case:

- **the `avoid-rat` bullet restored to the wingus header**, which is #161 put
  back and is what the cross-app rule exists to catch;
- **the `avoid-rat` line restored to the wingus example**, which the bullet rule
  does *not* see, since `--help` never prints the example -- the two halves were
  checked separately for exactly this, and each mutation fails only its own;
- the bullet reader narrowed to one key per bullet, so five real keys across two
  apps stop being checked;
- the bullet reader taking keys from a bullet's body as well as its head;
- the bullet reader's line-joining dropped, which loses the mission runner's
  two-line bullet head;
- the example reader made to read fenced blocks anywhere rather than only in the
  header;
- the example reader made to accept lines that are not assignments;
- the parsed-key reader narrowed to `AppSettings.valueType`, which is the
  pass-by-seeing-nothing shape CLAUDE.md names;
- the rule scoped to one app rather than iterated over `eve_apps()`;
- the note gutted so `--help` no longer tells an operator to delete the line;
- the note written so that it suppresses `hated-rat` from "Also accepted";
- and **the wingus parser given an `avoid-rat` entry** -- the other way #161
  could have been closed. That one fails three cases, and failing is the wanted
  answer rather than a hole: implementing a setting is a behaviour change that
  must not arrive under cover of a documentation fix, and whoever makes it has
  to restore the documentation too -- which is then what the cross-app rule
  above checks.

**Two of the twelve survived the first pass and both were real holes.** The
cross-app rule is "no app violates this", which is satisfied by *any* subset of
the apps once the corpus is clean -- so scoping its loop to one app changed
nothing it asserted, and the apps inspected are now asserted beside the rule
rather than left to the loop. And both example-reader loosenings were harmless
against today's six apps, since no app has a fenced block outside its header and
every line inside one is an assignment; the rule caught them only by luck, so
`TheReadersReadOffersAndNotProse` asks the readers directly instead.

Nothing here reads a live game client, a bot, or the recorded runs. The
`elm repl` cases need `elm` on PATH; without it they **fail** rather than
skipping, for the reason `prerequisites.py` gives.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import re
import subprocess
import unittest

from prerequisites import ElmRepl, open_repl
# One definition of "which keys does this parser accept", for the reason in the
# doc comment above: a second copy would drift towards passing by seeing
# nothing, which is the one failure this whole file is about.
from test_avoid_rat_removed import (APPLICATIONS_DIR, bot_elm, eve_apps,
                                    setting_keys, top_level_blocks)

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
BOT_HELP = os.path.join(MACOS_HOST_DIR, "bot_help.py")

WINGUS = "eve-online-wingus"
SETTING = "avoid-rat"
# What wingus accepts instead, and what the client's own parse error suggests.
# Named so that a change which starts *documenting* it has to come past this
# file, since documenting a setting no decision reads is #125's shape.
WINGUS_OWN_RAT_SETTING = "hated-rat"

# Bullets whose head names more than one key, and the app each is in. Named
# rather than discovered: they are what makes the difference between a reader
# that checks every documented key and one that checks the first of each bullet
# and reports nothing about the rest.
MULTI_KEY_BULLETS = {
    "eve-online-mission-runner": ("short-range-ammo", "long-range-ammo"),
    "eve-online-saxrat": ("short-range-ammo", "long-range-ammo",
                          "ammo-swap-range"),
}

# A bullet's head ends at the first colon; every backticked key before it is
# offered. `[a-z][a-z0-9-]*` is the shape `AppSettings` keys have and the shape
# `bot_help.setting_keys` looks for on the other side.
KEY_IN_BACKTICKS = re.compile(r"`([a-z][a-z0-9-]*)`")
BULLET_LINE = re.compile(r"^\s*\+\s+(.*)$")
ASSIGNMENT_LINE = re.compile(r"^([a-z][a-z0-9-]*)\s*=")

# Where `bot_help.py`'s settings text stops. Cutting here keeps the host's own
# argparse output and the "Also accepted" list -- which is about keys the header
# does *not* offer -- from being read as offers.
HELP_SECTION_ENDS_AT = ("Also accepted, but not described",
                        "Host flags --")


def help_text(app):
    """What `--help` prints for `app`, from `bot_help.py` itself.

    A subprocess rather than an import, which is what `test_avoid_rat_removed`
    and `test_settings_name_lists` both do and for the reason those record: the
    module sets `SIGPIPE` back to the default on import, so importing it changes
    how this process dies on a closed pipe. It is also the stronger assertion,
    since what an operator reads is this output rather than the header it is
    derived from.
    """
    return subprocess.run(
        ["python3", BOT_HELP, os.path.join(APPLICATIONS_DIR, app)],
        capture_output=True, text=True, check=True).stdout


def offered_settings_text(text):
    """The part of `--help` that *offers* settings, and nothing after it."""
    for ending in HELP_SECTION_ENDS_AT:
        text = text.split(ending, 1)[0]
    return text


def keys_in_bullet_head(item):
    return KEY_IN_BACKTICKS.findall(item.split(":", 1)[0])


def documented_keys(text):
    """Every key the bullets in `text` offer, in order, without repeats.

    A bullet is joined across physical lines until its head's colon, because a
    head can span two lines (`run-away-shield-hitpoints-threshold-percent` /
    `run-away-armor-hitpoints-threshold-percent` is written that way) and
    because one bullet can offer several keys. Only the head is read: a bullet's
    body names other settings in prose, and demanding those be parseable keys
    would go red on a header that is telling the truth.
    """
    keys = []
    item = None
    for line in text.split("\n"):
        bullet = BULLET_LINE.match(line)
        if bullet is not None:
            if item is not None:
                keys.extend(keys_in_bullet_head(item))
            item = bullet.group(1)
        elif item is not None:
            if not line.strip() or ":" in item:
                keys.extend(keys_in_bullet_head(item))
                item = None
            else:
                item = item + " " + line.strip()
    if item is not None:
        keys.extend(keys_in_bullet_head(item))
    return list(dict.fromkeys(keys))


def header_of(source):
    """`Bot.elm`'s leading `{- ... -}` block, which is the documentation.

    Bounded at the header's own closing delimiter rather than run to the end of
    the file, so that a fenced block in some later doc comment cannot be read as
    the example an operator pastes. That bound matters for
    `eve-online-warp-to-0-autopilot`, whose header carries neither a following
    `##` heading nor the "When using more than one setting" sentence
    `bot_help.settings_section` stops at -- so that function's own section runs
    to the end of the source.
    """
    lines = []
    for line in source.split("\n"):
        if line.rstrip() == "-}":
            break
        lines.append(line)
    return "\n".join(lines)


def example_settings_keys(source):
    """The keys the header's own example settings string assigns.

    Read as assignments inside the header's fenced blocks, which is exactly the
    text an operator copies. An app with no example answers `[]`; the rule below
    is then vacuous for that app, which is why
    `TheReadersCannotPassBySeeingNothing` asserts how many apps carry one.
    """
    keys = []
    inside = False
    for line in header_of(source).split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            inside = not inside
            continue
        if inside:
            match = ASSIGNMENT_LINE.match(stripped)
            if match is not None:
                keys.append(match.group(1))
    return list(dict.fromkeys(keys))


def elm_string(value):
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') \
        .replace("\n", "\\n") + '"'


PREAMBLE = ("import Bot exposing (..)", "import Result.Extra")


class WingusRepl(ElmRepl):
    """The shared harness, asking wingus' own parser the two questions here."""

    def parses(self, settings_strings):
        return self.booleans([
            "parseBotSettings %s |> Result.map (always True) "
            "|> Result.withDefault False" % elm_string(settings)
            for settings in settings_strings])

    def rejection_reasons(self, settings_strings):
        return self.strings([
            'parseBotSettings %s |> Result.map (always "<accepted>") '
            "|> Result.Extra.merge" % elm_string(settings)
            for settings in settings_strings])


class TheReadersCannotPassBySeeingNothing(unittest.TestCase):
    """The rule below is a subset test, so a reader that reads nothing passes.

    Three ways that could happen, one case each: no documented keys found, no
    parsed keys found, and a bullet naming several keys read as naming one.
    """

    def test_every_app_documents_at_least_one_setting(self):
        for app in eve_apps():
            with self.subTest(app):
                self.assertTrue(documented_keys(
                    offered_settings_text(help_text(app))))

    def test_every_app_registers_at_least_one_setting(self):
        # The mirror of `test_avoid_rat_removed`'s own guard, restated here
        # because this file's rule rests on the same reader: narrowed to
        # `AppSettings.valueType`, the combat anomaly bot's thirteen
        # `PromptParser` keys read as none.
        for app in eve_apps():
            with self.subTest(app):
                self.assertTrue(setting_keys(bot_elm(app)))

    def test_a_bullet_naming_several_keys_yields_all_of_them(self):
        # Without this, a one-key-per-bullet reader quietly stops checking five
        # real keys across two apps and every case here still passes.
        for app, keys in MULTI_KEY_BULLETS.items():
            with self.subTest(app):
                offered = documented_keys(
                    offered_settings_text(help_text(app)))
                for key in keys:
                    self.assertIn(key, offered)

    def test_a_bullet_head_split_across_two_lines_is_read_whole(self):
        # The mission runner writes its two hitpoint thresholds as one bullet
        # over two physical lines, so a reader that judges a line at a time
        # loses the second key.
        offered = documented_keys(
            offered_settings_text(help_text("eve-online-mission-runner")))
        self.assertIn("run-away-shield-hitpoints-threshold-percent", offered)
        self.assertIn("run-away-armor-hitpoints-threshold-percent", offered)

    def test_the_example_reader_finds_the_examples_that_exist(self):
        # Most apps carry an example settings string; the rule over them is
        # vacuous for any that does not, so the count is asserted rather than
        # left to chance.
        with_examples = [app for app in eve_apps()
                         if example_settings_keys(bot_elm(app))]
        self.assertGreaterEqual(len(with_examples), 4)
        self.assertIn(WINGUS, with_examples)

    def test_the_example_reader_stops_at_the_end_of_the_header(self):
        # `eve-online-warp-to-0-autopilot` has no example and no terminator that
        # `bot_help.settings_section` recognises, so its settings section runs
        # to the end of the source. Reading fenced blocks anywhere would take
        # whatever a later doc comment happens to hold.
        self.assertEqual(
            example_settings_keys(bot_elm("eve-online-warp-to-0-autopilot")),
            [])
        # The header is the documentation and stops before the code: it carries
        # the settings section and not the module the section describes.
        # (Asserted against the module declaration rather than against a
        # function name, since the prose is free to *name* one.)
        header = header_of(bot_elm(WINGUS))
        self.assertIn("## Configuration Settings", header)
        self.assertNotIn("module Bot exposing", header)


class TheReadersReadOffersAndNotProse(unittest.TestCase):
    """What counts as the header *offering* a setting, asked of the readers.

    The apps happen to make both loosenings below harmless today -- every
    backticked token in a bullet body is a real key somewhere, and no app has a
    fenced block outside its header. So the rule catches them only by luck, and
    these cases ask the readers directly instead.
    """

    def test_a_key_named_in_a_bullets_body_is_not_an_offer(self):
        # Bodies point at other settings in prose: the mission runner's armour
        # bullet names `run-away-incoming-damage-threshold` while explaining
        # what that one cannot do. Reading a body as an offer would demand that
        # every such mention be a parseable key.
        section = (
            "   + `real-setting` : does a thing.\n"
            "     See `some-other-thing` and `not-a-setting` for why.\n")
        self.assertEqual(documented_keys(section), ["real-setting"])

    def test_a_fenced_block_outside_the_header_is_not_the_example(self):
        # The example an operator pastes is the one in the documentation. A
        # fenced block in some later doc comment is about the code.
        source = (
            "{- A bot\n"
            "\n"
            "   ```\n"
            "   real-setting = yes\n"
            "   ```\n"
            "-}\n"
            "module Bot exposing (..)\n"
            "\n"
            "{-| A note about a decision.\n"
            "\n"
            "    ```\n"
            "    not-a-setting = 3\n"
            "    ```\n"
            "-}\n"
            "someRule = 1\n")
        self.assertEqual(example_settings_keys(source), ["real-setting"])

    def test_a_line_in_the_example_that_assigns_nothing_is_not_a_key(self):
        source = (
            "{- A bot\n"
            "\n"
            "   ```\n"
            "   real-setting = yes\n"
            "   and this line is prose the operator would not paste\n"
            "   ```\n"
            "-}\n")
        self.assertEqual(example_settings_keys(source), ["real-setting"])


class TheHeaderMayNotOfferWhatTheParserRefuses(unittest.TestCase):
    """The rule, over every EVE app and both halves of the documentation.

    A key the header offers and the parser does not register is not a setting
    that does nothing -- it is a settings string that ends the session at
    startup, and the operator followed the bot's own documentation to write it.
    """

    def test_every_documented_key_is_registered_in_the_parser(self):
        # The apps inspected are asserted alongside the rule rather than left
        # to the loop. A rule of the form "no app violates this" passes for any
        # subset of the apps once the corpus is clean, so scoping it to one app
        # is invisible to the assertion it carries -- which is exactly the
        # mutation that has to fail.
        inspected = []
        for app in eve_apps():
            registered = setting_keys(bot_elm(app))
            inspected.append(app)
            with self.subTest(app):
                for key in documented_keys(
                        offered_settings_text(help_text(app))):
                    self.assertIn(
                        key, registered,
                        "%s offers '%s' in --help and its parseBotSettings "
                        "does not accept it, so following that help ends the "
                        "session at startup -- that is #161's shape in another "
                        "app" % (app, key))
        self.assertEqual(inspected, eve_apps())
        self.assertGreaterEqual(len(inspected), 6)

    def test_every_example_settings_key_is_registered_in_the_parser(self):
        # The half `--help` never prints, and the half an operator pastes.
        inspected = []
        for app in eve_apps():
            registered = setting_keys(bot_elm(app))
            inspected.append(app)
            with self.subTest(app):
                for key in example_settings_keys(bot_elm(app)):
                    self.assertIn(
                        key, registered,
                        "%s's own example settings string assigns '%s' and its "
                        "parseBotSettings does not accept it, so pasting that "
                        "example ends the session at startup" % (app, key))
        self.assertEqual(inspected, eve_apps())
        self.assertGreaterEqual(len(inspected), 6)


class WingusIsTheAppTheRuleWasWrittenFor(unittest.TestCase):
    """#161 itself, read out of the source.

    Both halves of the promise are asserted gone, and the parser is asserted
    *unchanged* -- implementing the setting is the other way this issue could
    have been closed, and these cases must go red for a header that still
    offers it rather than for a parser that grew an entry.
    """

    def setUp(self):
        self.source = bot_elm(WINGUS)
        self.help = help_text(WINGUS)

    def test_the_header_no_longer_offers_it(self):
        self.assertNotIn(
            SETTING, documented_keys(offered_settings_text(self.help)))

    def test_the_example_settings_string_no_longer_assigns_it(self):
        self.assertNotIn(SETTING, example_settings_keys(self.source))

    def test_the_settings_beside_it_are_still_offered(self):
        offered = documented_keys(offered_settings_text(self.help))
        for key in ("anomaly-name", "hide-when-neutral-in-local",
                    "activate-module-always", "anomaly-wait-time"):
            with self.subTest(key):
                self.assertIn(key, offered)

    def test_the_help_still_tells_an_operator_what_happened_to_it(self):
        # An unknown key ends the session at startup, so somebody whose settings
        # file still carries the line has to be able to read why. Prose rather
        # than a bullet, which is why the two cases above still hold.
        self.assertIn(SETTING, self.help)
        self.assertIn("Unknown setting name", self.help)
        self.assertIn("Delete the line", self.help)

    def test_the_setting_this_bot_does_accept_is_still_reported(self):
        # `hated-rat` is what wingus parses instead, and `--help` lists it under
        # "Also accepted, but not described in the bot's own header". Naming it
        # in the header's prose would take it out of that list -- `bot_help.py`
        # filters on the section's whole text -- so the note deliberately does
        # not, and this case is what notices if that changes.
        self.assertIn(WINGUS_OWN_RAT_SETTING, setting_keys(self.source))
        also_accepted = "".join(self.help.split(
            "Also accepted, but not described in the bot's own header:")[1:])
        self.assertIn(WINGUS_OWN_RAT_SETTING, also_accepted)

    def test_the_field_the_setting_would_have_filled_is_still_absent(self):
        # The half no repl case can see: wingus never had `avoidRats` at all,
        # so "documented but not parsed" was the whole defect and re-adding the
        # field without the parser entry would be a different one.
        mentions = [name for name, text in top_level_blocks(self.source).items()
                    if "avoidRats" in text]
        self.assertEqual(mentions, [])


class WingusParserAnswersForItself(unittest.TestCase):
    """The header's own example, run through the real parser.

    Every case here would have failed before this change: the example carried an
    `avoid-rat` line, so wingus rejected the settings string its own
    documentation told an operator to paste.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(WingusRepl, prefix="test-wingus-settings-",
                             preamble=PREAMBLE,
                             app_dir=os.path.join(APPLICATIONS_DIR, WINGUS))
        cls.source = bot_elm(WINGUS)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def example_settings_string(self):
        """The header's example, reassembled as an operator would paste it."""
        lines = []
        inside = False
        for line in header_of(self.source).split("\n"):
            stripped = line.strip()
            if stripped.startswith("```"):
                inside = not inside
                continue
            if inside and ASSIGNMENT_LINE.match(stripped):
                lines.append(stripped)
        return "\n".join(lines)

    def test_the_headers_own_example_is_accepted(self):
        settings = self.example_settings_string()
        self.assertTrue(settings, "the header has no example to paste")
        self.assertEqual(self.repl.parses([settings]), [True])

    def test_the_key_the_header_used_to_offer_is_still_refused(self):
        # Unchanged by this issue, and the reason the documentation had to go
        # rather than stay: the parser answers `Err`, which ends the session.
        self.assertEqual(
            self.repl.parses(["%s=Infested Carrier" % SETTING]), [False])

    def test_the_refusal_names_the_key_so_an_operator_can_delete_the_line(self):
        reason = self.repl.rejection_reasons(
            ["%s=Infested Carrier" % SETTING])[0]
        self.assertIn(SETTING, reason)
        self.assertIn("Unknown setting name", reason)

    def test_one_such_line_would_reject_the_whole_example(self):
        # What #161 cost, restated as the parser's own answer: a single unknown
        # key rejects everything beside it, so the example was unusable whole.
        self.assertEqual(
            self.repl.parses([
                self.example_settings_string()
                + "\n%s=Infested Carrier" % SETTING]),
            [False])

    def test_every_key_the_header_still_offers_is_accepted_on_its_own(self):
        # The rule above is a source read; this is the same claim executed, for
        # the one app the issue is about.
        offered = documented_keys(offered_settings_text(help_text(WINGUS)))
        values = {"anomaly-name": "Drone Patrol",
                  "hide-when-neutral-in-local": "yes",
                  "activate-module-always": "shield hardener",
                  "anomaly-wait-time": "30"}
        self.assertEqual(sorted(offered), sorted(values))
        self.assertEqual(
            self.repl.parses(["%s = %s" % (key, values[key])
                              for key in sorted(offered)]),
            [True] * len(offered))

    def test_the_setting_this_bot_accepts_instead_still_parses(self):
        self.assertEqual(
            self.repl.parses(["%s = Infested Carrier"
                              % WINGUS_OWN_RAT_SETTING]),
            [True])
