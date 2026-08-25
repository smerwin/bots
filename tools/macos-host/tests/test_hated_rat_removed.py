"""Tests for #195 -- wingus parsed `hated-rat`, had a real reader for it, and
never called that reader.

`#125`'s mission-runner case was three occurrences and no fourth: the default,
the parser handler, the field in the record type -- a setting parsed and never
read at all. This one is #125's shape one step deeper. `eve-online-wingus`
parsed `hated-rat` into `BotSettings.priorityRats`, and a real reader existed,
`getPriorityRatsSeenInAnomaly` -- typed, compiled, and never called anywhere in
the file. So the check #125 taught this repo to run ("is the field read
anywhere?") answered **yes** here, which is exactly why #195 calls this worse:
it passes the shallower check and needs a deeper one, asking whether the reader
itself has a call site rather than whether the field appears in a block that is
not `defaultBotSettings`/`parseBotSettings`/`BotSettings`.

**Removed rather than wired up**, for #125's own reason repeated: which way to
fix it was not proposed by the issue, and wiring the read in means deciding
what a "priority rat" should *do* in a fleet-follow bot that has no anomaly
selection logic of its own -- nobody has established that shape, and guessing
one would be exactly the kind of thing this repo's own culture -- "a bot that
guesses reads exactly like one that knows" -- refuses. `eve-online-saxrat` and
`eve-online-combat-anomaly-bot` implement the *sibling* setting `avoid-rat` at
anomaly granularity; a priority list is not obviously that shape inverted, and
`hated-rat` had no shipped equivalent anywhere to port from.

**Removal is a settings-string change**, same risk `test_avoid_rat_removed.py`
already carries for its own setting: `Common.AppSettings` answers an
unrecognised key with `Unknown setting name`, so a settings file still carrying
`hated-rat=` now ends the session at startup instead of doing nothing. Nothing
in this repo sets it -- there is no `run_wingus.sh` launcher at all, and no
wingus log in `~/eve-bot-logs` -- which is also this issue's own "Unverified"
note about whether wingus is flown at all.

**One more thing #195 asks be closed and this file closes**: the "did you
mean" hint #161 gave `avoid-rat` pointed operators at `hated-rat`, which is
what made following that suggestion land on a setting that parsed and then did
nothing. `Common.AppSettings`' suggestion is computed from whatever keys
`parseBotSettings` actually accepts, so removing the entry removes the
suggestion as a consequence rather than as a second edit -- verified below by
asking the parser what it suggests for `avoid-rat` now.

Scaled down from `test_avoid_rat_removed.py`'s own rigor rather than matching
it case for case: that file is the template for *this repo's* removal
discipline, not a bar every instance of it has to clear on its own -- wingus
is legacy and narrower in scope (one setting, one app, no sibling
implementation to keep in step with), and the cross-app "parses it, must read
it" rule #125 already built stays where it is rather than being duplicated
here; it would not have caught this shape anyway; see the module doc above.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import unittest

from prerequisites import open_repl
from test_avoid_rat_removed import (
    advertised_keys,
    elm_string,
    setting_keys,
    top_level_blocks,
)
from test_wingus_warp_end_trigger import WINGUS_BOT_ELM, WINGUS_DIR, WingusRepl

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
BOT_HELP = os.path.join(MACOS_HOST_DIR, "bot_help.py")

SETTING = "hated-rat"
FIELD = "priorityRats"
DEAD_READER = "getPriorityRatsSeenInAnomaly"
DEAD_READERS_OWN_HELPER = "shouldPrioritizeRatAccordingToSettings"

# The sibling setting #161 taught wingus to suggest `hated-rat` for, before
# this removal. Read live rather than assumed, below.
SIBLING_UNKNOWN_SETTING = "avoid-rat"


def bot_source():
    with open(WINGUS_BOT_ELM, encoding="utf-8") as source:
        return source.read()


def help_text():
    """`--help` for wingus, run as a subprocess for the reason
    `test_avoid_rat_removed.py`'s own `help_text` gives: importing `bot_help`
    changes how the importing process's `SIGPIPE` behaves.
    """
    import subprocess
    return subprocess.run(
        ["python3", BOT_HELP, WINGUS_DIR],
        capture_output=True, text=True, check=True).stdout


PREAMBLE = ("import Bot exposing (..)", "import Result.Extra")


class HatedRatRepl(WingusRepl):
    """`WingusRepl` plus the two questions this file asks of the parser.

    `WingusRepl` inherits `SaxratRepl`'s preamble, which has no
    `Result.Extra` import -- nothing saxrat asks needs one. This file's
    `rejection_reasons` does, the same way `test_avoid_rat_removed.py`'s own
    `AvoidRatRepl` carries its own `PREAMBLE` rather than the shared one, so
    the import is added here explicitly instead of widening a preamble every
    other saxrat/wingus case also gets.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

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


class TheParserNoLongerAcceptsIt(unittest.TestCase):
    """The removal, executed through the real parser rather than read.

    Every case here would have passed with the opposite assertion before
    #195, which is the point: the parser took the key and called a reader
    nothing else ever called.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = open_repl(HatedRatRepl)

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_key_it_used_to_accept_is_refused(self):
        self.assertEqual(
            self.repl.parses(["%s=Infested Carrier" % SETTING]), [False])

    def test_the_refusal_names_the_key(self):
        reason = self.repl.rejection_reasons(
            ["%s=Infested Carrier" % SETTING])[0]
        self.assertIn(SETTING, reason)
        self.assertIn("Unknown setting name", reason)

    def test_the_settings_beside_it_still_parse(self):
        # The deletion touched four sites in one file (the default, the
        # parser entry, the field, and the two dead functions below); its
        # failure mode is taking a neighbour along with it.
        self.assertEqual(
            self.repl.parses([
                "anomaly-name=Drone Patrol",
                "hide-when-neutral-in-local=yes",
                "activate-module-always=shield hardener",
                "anomaly-wait-time=15",
            ]),
            [True, True, True, True])

    def test_the_header_s_own_example_string_still_parses(self):
        # What makes the removal safe rather than merely justified: the one
        # settings string the bot's own header offers an operator to copy.
        example = (
            "anomaly-name = Drone Patrol\n"
            "anomaly-name = Drone Horde\n"
            "hide-when-neutral-in-local = yes\n"
            "activate-module-always = shield hardener"
        )
        self.assertEqual(self.repl.parses([example]), [True])

    def test_the_sibling_setting_no_longer_suggests_it(self):
        # #161's "did you mean" pointed an operator who typed the *other*
        # unimplemented rat setting at this one. The suggestion is computed
        # from whatever `parseBotSettings` currently accepts, so removing the
        # entry removes the suggestion as a consequence -- this is what
        # verifies that rather than assuming it.
        reason = self.repl.rejection_reasons(
            ["%s=Infested Carrier" % SIBLING_UNKNOWN_SETTING])[0]
        self.assertIn("Unknown setting name", reason)
        self.assertNotIn(SETTING, reason)


class TheFieldAndItsReaderAreGone(unittest.TestCase):
    """No occurrence at all outside the doc comment that explains the removal.

    #195's own point is that "is the field read anywhere" was not a strong
    enough question -- `getPriorityRatsSeenInAnomaly` read it and was itself
    never called. So this checks both: the field is gone, *and* the two
    functions that used to read it are gone too, rather than only the
    shallower of the two.
    """

    def setUp(self):
        self.source = bot_source()
        self.blocks = top_level_blocks(self.source)

    def test_no_block_mentions_the_field(self):
        mentions = [name for name, text in self.blocks.items()
                    if FIELD in text]
        self.assertEqual(mentions, [])

    def test_the_dead_reader_and_its_helper_are_both_gone(self):
        self.assertNotIn(DEAD_READER, self.blocks)
        self.assertNotIn(DEAD_READERS_OWN_HELPER, self.blocks)
        # Not merely renamed out of top-level-declaration shape into
        # something this reader would miss: neither name is a live
        # declaration anywhere past the header. `DEAD_READER` does appear
        # once *inside* the header's own doc comment -- the paragraph this
        # file's module docstring quotes -- naming the reader that used to
        # exist is what makes the removal legible to an operator, the same
        # way #125's own removal names `avoidRats` in prose. So the code
        # past the header, rather than the whole file, is what has to be
        # silent.
        code_after_header = self.source.split("-}", 1)[1]
        self.assertNotIn(DEAD_READER, code_after_header)
        self.assertNotIn(DEAD_READERS_OWN_HELPER, code_after_header)
        self.assertNotIn(DEAD_READERS_OWN_HELPER, self.source)

    def test_the_parser_does_not_accept_the_key(self):
        keys = setting_keys(self.source)
        self.assertNotIn(SETTING, keys)
        # The reader is looking at the right block: these are still there.
        for key in ("anomaly-name", "hide-when-neutral-in-local",
                    "activate-module-always", "anomaly-wait-time"):
            with self.subTest(key):
                self.assertIn(key, keys)

    def test_the_help_text_no_longer_advertises_it(self):
        offered = advertised_keys(help_text())
        self.assertNotIn(SETTING, offered)
        self.assertIn("anomaly-name", offered)

    def test_the_help_text_still_tells_an_operator_what_happened_to_it(self):
        # Prose, since an unknown key ends the session at startup and an
        # operator whose settings file still has the line has to be able to
        # read why it is now refused.
        text = help_text()
        self.assertIn(SETTING, text)
        self.assertIn("Unknown setting name", text)
