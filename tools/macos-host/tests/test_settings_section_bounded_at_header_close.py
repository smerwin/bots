"""Issue #196: `bot_help.settings_section` could run past the header entirely.

`bot_help.py` slices a bot's `## Configuration Settings` block out of its
`Bot.elm` header by scanning forward from that heading to a terminator -- the
next `##` heading, or the sentence "When using more than one setting".
`eve-online-warp-to-0-autopilot` has neither: its header's only `##` heading
*is* "## Configuration Settings" itself, and the sentence does not occur in the
file at all. So the section ran to end of file, and `--help` for a launcher
built on that app would print the app's whole ~500-line source -- Elm imports,
decision logic and all -- under "Bot settings".

#161's fix for a related defect had already worked out the safe bound and used
it in this same test directory (`test_documented_settings_are_parsed.header_of`):
every `Bot.elm` header closes with its own `-}` by construction, so stopping
there can never run past the header, on any app, including one written after
this file. This is that bound applied to `settings_section` itself rather than
reimplemented a second time beside it.

## Why the '-}' bound and not a terminator for this one app

The issue names two ways to close it and picks the first: give the reader a
third, general terminator (this change), rather than a terminator specific to
`eve-online-warp-to-0-autopilot` (a `## Configuration Settings`-only header
matching "When using more than one setting", say). The second fixes one app and
leaves the reader able to over-run on the next one that ships without the two
existing terminators; the first fixes the class of defect.

## What is asserted

- The three termination paths individually, against synthetic headers, so a
  regression in any one is caught by name rather than only by the aggregate
  real-app check below.
- The bound is the header's own `-}` at column 0 (matching `header_of`'s
  convention) and not any indented text that merely reads `-}` -- a settings
  bullet is prose and must not be truncated by something that looks like a
  delimiter but is not one at the header's own nesting level.
- Every one of the six EVE apps' rendered `--help` output, via `bot_help.py`
  as a subprocess (matching this directory's convention of not importing
  `bot_help` directly, since importing it resets `SIGPIPE` for the whole test
  process): none of them ever prints real Elm source -- `module Bot exposing`
  or an `import` line -- under "Bot settings". That is the property most at
  risk from this change, since the five apps that already had a working
  terminator must keep behaving exactly as before.
- `eve-online-warp-to-0-autopilot` specifically: its settings section is now
  small and ends with the header's own closing prose, rather than running to
  the end of the file.

## Confirmed by mutation

Three mutations of `bot_help.settings_section`, each checked to fail a named
case here (and to leave `test_documented_settings_are_parsed.py`'s cases
passing, since that file's own `header_of` is untouched by this change and is
what proves the bound is correct in the first place):

- **the `-}` check removed entirely** -- restores #196 exactly, and
  `test_the_section_stops_before_the_module_declaration` and
  `test_every_app_never_leaks_real_source_into_its_help` both fail, the second
  by name for `eve-online-warp-to-0-autopilot`;
- **the `-}` check loosened to `stripped == "-}"`** (matching any indentation,
  not only column 0) -- fails
  `test_an_indented_closing_brace_look_alike_does_not_terminate_early`, which
  is exactly the over-eager version this file's own bound has to not be;
- **the `-}` check placed before the two existing ones** instead of after --
  passes every case here (the three terminators agree on which line ends the
  section whichever order they are tried, since the loop always breaks on the
  first line that matches any of them), which is recorded as a mutation that
  does *not* need to fail rather than skipped over: order among the three
  conditions is not part of the contract this file pins.

Nothing here reads a live game client, a bot, or the recorded runs, and none of
it needs the `elm` toolchain -- `settings_section` is a pure text reader.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import subprocess
import tempfile
import unittest

from test_avoid_rat_removed import APPLICATIONS_DIR, bot_elm, eve_apps

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
BOT_HELP = os.path.join(MACOS_HOST_DIR, "bot_help.py")

# The app the issue is filed on, and the one whose header has neither of the
# two pre-existing terminators.
BROKEN_APP = "eve-online-warp-to-0-autopilot"

# Text that can only appear in the --help output if the settings reader ran
# past the header and into the module's real source. None of these are
# something a bot's own header prose would ever contain.
REAL_SOURCE_MARKERS = ("module Bot exposing", "import BotLab", "botMain")


def run_bot_help(bot_source_dir, script="the launcher"):
    """`--help`'s stdout for `bot_source_dir`, as a subprocess.

    A subprocess rather than an import, for the reason
    `test_documented_settings_are_parsed.help_text` gives: importing
    `bot_help` resets SIGPIPE for the whole test process, and a subprocess is
    also the stronger assertion, since it is what an operator actually reads.
    """
    result = subprocess.run(
        ["python3", BOT_HELP, bot_source_dir, "--script", script],
        capture_output=True, text=True, check=True)
    return result.stdout


def settings_block(help_output):
    """The text between the "Bot settings" banner and the next section."""
    after_banner = help_output.split(
        'Bot settings -- pass with --settings "...", one key=value per line:',
        1)[1]
    for ending in ("Also accepted, but not described", "Host flags --"):
        after_banner = after_banner.split(ending, 1)[0]
    return after_banner


def write_bot_elm(directory, text):
    with open(os.path.join(directory, "Bot.elm"), "w", encoding="utf-8") as f:
        f.write(text)


class TheThreeTerminatorsEachStopTheSectionOnTheirOwn(unittest.TestCase):
    """Each terminator, exercised in isolation, keeps the section bounded.

    Every fixture below places its terminator well before a trailing '-}' so
    that a mutation removing the '-}' check cannot make these particular
    cases pass by accident -- the existing terminator still has to do the
    work by itself.
    """

    def render(self, header_lines):
        source = "\n".join(header_lines) + "\nmodule Bot exposing (State, botMain)\n"
        with tempfile.TemporaryDirectory() as tmp:
            write_bot_elm(tmp, source)
            return settings_block(run_bot_help(tmp))

    def test_a_following_heading_still_stops_the_section(self):
        block = self.render([
            "{- A bot",
            "",
            "   ## Configuration Settings",
            "",
            "   + `real-setting` : does a thing.",
            "",
            "   ## Something Else",
            "",
            "   this prose must not appear in --help",
            "-}",
        ])
        self.assertIn("real-setting", block)
        self.assertNotIn("must not appear", block)

    def test_the_more_than_one_setting_sentence_still_stops_the_section(self):
        block = self.render([
            "{- A bot",
            "",
            "   ## Configuration Settings",
            "",
            "   + `real-setting` : does a thing.",
            "",
            "   When using more than one setting, separate them with a newline.",
            "",
            "   this prose must not appear in --help",
            "-}",
        ])
        self.assertIn("real-setting", block)
        self.assertNotIn("must not appear", block)

    def test_the_headers_own_close_stops_the_section_when_neither_exists(self):
        # This is #196 itself: no following '##' heading (the settings
        # heading is the header's only one) and no "more than one setting"
        # sentence.
        block = self.render([
            "{- A bot",
            "",
            "   ## Configuration Settings",
            "",
            "   + `real-setting` : does a thing.",
            "-}",
            "{- a second, later doc comment -}",
            "must-not-appear-in-help = 1",
        ])
        self.assertIn("real-setting", block)
        self.assertNotIn("must-not-appear", block)


class TheClosingDelimiterIsMatchedAtTheHeadersOwnNesting(unittest.TestCase):
    """The bound is a line that is exactly '-}', not text that contains it.

    A settings bullet could in principle *talk about* Elm syntax and mention
    '-}' as part of a longer line, or an example block could be indented; the
    bound must not fire on either, only on the header's own closing line at
    column 0 -- the same convention
    `test_documented_settings_are_parsed.header_of` already uses.
    """

    def render(self, header_lines):
        source = "\n".join(header_lines) + "\nmodule Bot exposing (State, botMain)\n"
        with tempfile.TemporaryDirectory() as tmp:
            write_bot_elm(tmp, source)
            return settings_block(run_bot_help(tmp))

    def test_an_indented_closing_brace_look_alike_does_not_terminate_early(self):
        block = self.render([
            "{- A bot",
            "",
            "   ## Configuration Settings",
            "",
            "   + `real-setting` : an example reads `foo -}` inline.",
            "     -}",
            "   + `second-setting` : also documented.",
            "-}",
        ])
        self.assertIn("real-setting", block)
        self.assertIn("second-setting", block)

    def test_a_line_that_merely_contains_the_delimiter_is_not_the_bound(self):
        block = self.render([
            "{- A bot",
            "",
            "   ## Configuration Settings",
            "",
            "   + `real-setting` : this line ends with -} as prose.",
            "",
            "   + `second-setting` : also documented.",
            "-}",
        ])
        self.assertIn("real-setting", block)
        self.assertIn("second-setting", block)


class EveryEveAppsHelpNeverLeaksRealSource(unittest.TestCase):
    """The property most at risk: five apps already worked, and must still.

    Iterated over every app `bot_help.py` can see, not only the one the issue
    is filed on -- CLAUDE.md's own review convention for this repo.
    """

    def test_every_app_never_leaks_real_source_into_its_help(self):
        inspected = []
        for app in eve_apps():
            inspected.append(app)
            with self.subTest(app):
                block = settings_block(
                    run_bot_help(os.path.join(APPLICATIONS_DIR, app),
                                script="run_%s.sh" % app))
                for marker in REAL_SOURCE_MARKERS:
                    self.assertNotIn(
                        marker, block,
                        "%s's --help settings section contains '%s', which "
                        "is real Elm source -- the reader ran past the "
                        "header" % (app, marker))
        self.assertEqual(inspected, eve_apps())
        self.assertGreaterEqual(len(inspected), 6)

    def test_the_five_apps_with_a_pre_existing_terminator_are_unaffected(self):
        # All five (every app but the broken one) stop their settings section
        # at the "When using more than one setting" sentence rather than at a
        # following '##' heading -- checked here rather than assumed, since
        # #196's own doc comment reports that both terminators exist in the
        # codebase without saying which apps use which. So the '-}' bound
        # this change adds is never the terminator that fires for any of
        # them: the sentence itself has to appear in each one's header, ahead
        # of the header's own close, for that to hold.
        terminator = "When using more than one setting"
        for app in eve_apps():
            if app == BROKEN_APP:
                continue
            with self.subTest(app):
                source = bot_elm(app)
                after_heading = source.split(
                    "## Configuration Settings", 1)[1]
                header_only = after_heading.split("\n-}", 1)[0]
                self.assertIn(
                    terminator, header_only,
                    "%s's header no longer carries the sentence this app "
                    "was assumed to terminate on; this case needs "
                    "re-pointing at whatever terminator it now relies on, "
                    "or removing if it no longer has one before its own "
                    "'-}'" % app)
                block = settings_block(
                    run_bot_help(os.path.join(APPLICATIONS_DIR, app),
                                script="run_%s.sh" % app))
                self.assertTrue(block.strip())


class TheBrokenAppSpecifically(unittest.TestCase):
    """#196's own app, before and after the fix, read directly off disk."""

    def setUp(self):
        self.source = bot_elm(BROKEN_APP)
        self.block = settings_block(
            run_bot_help(os.path.join(APPLICATIONS_DIR, BROKEN_APP),
                        script="run_autopilot.sh"))

    def test_the_header_really_has_neither_pre_existing_terminator(self):
        # If this ever stops being true the regression this file exists for
        # can no longer occur for this app, and the case above should be the
        # one carrying the coverage instead.
        after_settings_heading = self.source.split(
            "## Configuration Settings", 1)[1]
        header_only = after_settings_heading.split("\n-}", 1)[0]
        self.assertNotIn("##", header_only)
        self.assertNotIn("When using more than one setting", header_only)

    def test_the_settings_section_is_small(self):
        # Before the fix this ran to end of file -- hundreds of lines of Elm
        # source. The header's own settings prose is a handful of lines.
        self.assertLess(len(self.block.strip().split("\n")), 20)

    def test_the_settings_section_contains_the_one_documented_setting(self):
        self.assertIn("activate-module-always", self.block)

    def test_the_settings_section_does_not_contain_the_bots_own_code(self):
        for marker in REAL_SOURCE_MARKERS:
            self.assertNotIn(marker, self.block)
        self.assertNotIn("catalog-tags", self.block)


if __name__ == "__main__":
    unittest.main()
