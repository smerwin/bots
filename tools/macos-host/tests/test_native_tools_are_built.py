"""The native tools are rebuilt when their source moves, and nothing else does it.

The six C tools are gitignored build output. Nothing about pulling a change to
one of them updates what runs, and before `build_tools.sh` nothing noticed: the
launchers recompile the Elm bot on every run -- `botlab_host.py` copies the bot
directory and runs `elm make` every time -- while the C half of the same
executable surface was last built whenever somebody last remembered to.

What that cost, on 2026-08-16: `cg_input` on the machine that flies these bots
was compiled Aug 2 against an Aug 14 source, so PR #241 -- "cg_input posts the
key's own flags and its own modifiers, not the session's" -- had never run. Every
posted key carried the session's stray `SecondaryFn`, asserted by the bot's own
F1-F4 weapon hotkeys, so the client received Globe chords rather than text and
every typed string arrived empty. Clicks were unaffected, a stray Fn on a click
being harmless, so the symptom read as a focus bug and was not one. `tree_walker`
was stale too, by 17 minutes, and the first run of the build script found it.

These cases are about the *script and its wiring*, deliberately not about the
binaries on this machine: CI has none, and a case that went red for "nothing has
been built here" would be red on every runner forever. The one case that does
look at binaries skips when they are absent, which is the convention the
corpus-reading cases already use -- absent evidence is a skip, and a missing
prerequisite that the code still exists for is not.
"""

import os
import re
import stat
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(MACOS_HOST))
BUILD_TOOLS = os.path.join(MACOS_HOST, "build_tools.sh")
MACOS_MD = os.path.join(REPO, "MACOS.md")
def source_of(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def launchers():
    """Every bot launcher in `tools/macos-host`.

    Computed from the filesystem for the same reason `tool_directories` below
    is: a fourth launcher must not be able to appear without the cases in
    `TheLaunchersCallIt` noticing. A hardcoded list would have let one ship
    that never rebuilds the native tools, which is exactly the state those
    cases replaced.
    """
    return tuple(sorted(
        name for name in os.listdir(MACOS_HOST)
        if name.startswith("run_") and name.endswith(".sh")))


LAUNCHERS = launchers()


def tool_directories():
    """Every directory under `tools/macos-host` holding a C tool.

    Computed from the filesystem rather than listed here, so a seventh tool
    cannot be added without the coverage case below noticing.
    """
    found = []
    for name in sorted(os.listdir(MACOS_HOST)):
        directory = os.path.join(MACOS_HOST, name)
        if os.path.isdir(directory) and \
                os.path.isfile(os.path.join(directory, name + ".c")):
            found.append(name)
    return found


class TheScriptCoversEveryTool(unittest.TestCase):
    """A tool the script does not name is a tool that never gets rebuilt."""

    def setUp(self):
        self.script = source_of(BUILD_TOOLS)
        self.tools = tool_directories()

    def test_there_are_tools_to_cover(self):
        """The floor, so the coverage case cannot pass by finding nothing."""
        self.assertGreaterEqual(
            len(self.tools), 6,
            "found %r, which is fewer C tools than this repo has -- the "
            "coverage case below would pass having checked almost nothing"
            % (self.tools,))

    def test_every_tool_is_named_in_the_script(self):
        for name in self.tools:
            self.assertRegex(
                self.script, r'"%s:' % re.escape(name),
                "%s has a %s.c and is not in build_tools.sh's table, so it is "
                "never rebuilt and can go stale silently" % (name, name))

    def test_the_script_is_executable(self):
        mode = os.stat(BUILD_TOOLS).st_mode
        self.assertTrue(mode & stat.S_IXUSR,
                        "build_tools.sh is not executable, so the launchers' "
                        "call to it fails and every run refuses to start")


class TheRecipesAgreeWithTheDocumentedOnes(unittest.TestCase):
    """MACOS.md is where a person building by hand reads the recipe.

    Two copies of a build command drift, and the direction that matters is the
    script's: a tool built without its entitlements cannot `task_for_pid`, and
    one built without `-framework ApplicationServices` does not link at all.
    """

    def setUp(self):
        self.script = source_of(BUILD_TOOLS)
        self.macos_md = source_of(MACOS_MD)

    def test_the_entitled_tools_are_the_ones_macos_md_signs_with_entitlements(self):
        documented = set(re.findall(
            r"codesign -s - --entitlements (\w+)/entitlements\.plist",
            self.macos_md))
        in_script = set(re.findall(r'"(\w+):[^"]*:yes"', self.script))
        self.assertTrue(documented,
                        "read no entitled tools out of MACOS.md, so this case "
                        "is comparing against nothing")
        self.assertEqual(
            in_script, documented,
            "build_tools.sh and MACOS.md disagree about which tools need "
            "entitlements; a tool built without them cannot read memory")

    def test_the_framework_tools_are_the_ones_macos_md_links(self):
        documented = set(re.findall(
            r"clang [^\n]*-framework ApplicationServices -o (\w+)/",
            self.macos_md))
        in_script = set(re.findall(
            r'"(\w+):[^"]*-framework ApplicationServices[^"]*:', self.script))
        self.assertTrue(documented)
        self.assertEqual(in_script, documented)


class TheLaunchersCallIt(unittest.TestCase):
    """A build step nothing invokes is the state this replaced."""

    def test_each_launcher_runs_the_script(self):
        for launcher in LAUNCHERS:
            body = source_of(os.path.join(MACOS_HOST, launcher))
            self.assertIn(
                "build_tools.sh", body,
                "%s does not rebuild the native tools, so a pulled fix to one "
                "of them never reaches a run" % launcher)

    def test_each_launcher_refuses_to_start_when_the_build_fails(self):
        """Carrying on would leave the old binary running, which is the bug.

        Checked as "the call is followed by an exit", rather than by running a
        launcher -- a launcher kills the running bot and starts a new one.
        """
        for launcher in LAUNCHERS:
            body = source_of(os.path.join(MACOS_HOST, launcher))
            # Anchored on the invocation rather than on the first mention: the
            # comment above it names the script too, and slicing from there
            # reads the comment instead of the branch.
            after = body.split('"${SCRIPT_DIR}/build_tools.sh"', 1)[1][:500]
            self.assertIn(
                "exit 1", after,
                "%s calls build_tools.sh and does not stop when it fails"
                % launcher)

    def test_the_build_runs_before_the_one_bot_guard(self):
        """A failed build must not have already killed the running session.

        Anchored on the invocation, not on the first mention. The comment above
        the call names the script and sits above the guard, so a version that
        moved the call below the guard and left the comment where it was would
        satisfy a first-mention comparison -- which is the ordering this case
        exists to pin.
        """
        for launcher in LAUNCHERS:
            body = source_of(os.path.join(MACOS_HOST, launcher))
            self.assertLess(
                body.index('"${SCRIPT_DIR}/build_tools.sh"'),
                body.index("Guard: one bot at a time"),
                "%s kills the running bot before finding out whether the new "
                "one can be built" % launcher)


class TheStalenessRuleIsTheRightWayRound(unittest.TestCase):
    """Judged over every source beside the tool, and on a real filesystem.

    `cg_input.c` includes `input_flags.h`, so a fix landing only in the header
    has to count -- that is not hypothetical, it is where #241's flag
    composition constants live.
    """

    def test_a_header_counts_as_a_source(self):
        self.assertRegex(
            source_of(BUILD_TOOLS), r"\*\.h",
            "staleness ignores headers, so a fix that lands in input_flags.h "
            "would never be built")

    def test_running_it_twice_rebuilds_nothing_the_second_time(self):
        """It has to be idempotent, or every launch pays a full rebuild.

        Executed rather than read: this is a claim about `-nt` and about the
        timestamps a build leaves behind, which a source read cannot settle.
        Skipped where the tools cannot be built at all.
        """
        if sys.platform != "darwin":
            self.skipTest("not macOS: the native tools are Darwin-only")
        first = subprocess.run([BUILD_TOOLS], capture_output=True, text=True)
        self.assertEqual(
            first.returncode, 0,
            "the native tools do not build on this macOS machine, which is a "
            "breakage rather than an absent prerequisite: %s"
            % first.stderr.strip()[:400])
        second = subprocess.run([BUILD_TOOLS], capture_output=True, text=True)
        self.assertEqual(second.returncode, 0)
        self.assertNotIn(
            "rebuilding", second.stdout,
            "the second run rebuilt something, so every launch recompiles and "
            "the timestamp comparison is the wrong way round")


class WhatThisMachineHasBuilt(unittest.TestCase):
    """The invariant itself, where there is anything to check it against."""

    def test_no_binary_is_older_than_its_sources(self):
        stale = []
        checked = 0
        for name in tool_directories():
            binary = os.path.join(MACOS_HOST, name, name)
            if not os.path.exists(binary):
                continue
            checked += 1
            built = os.path.getmtime(binary)
            for entry in os.listdir(os.path.join(MACOS_HOST, name)):
                if entry.endswith((".c", ".h")):
                    source = os.path.join(MACOS_HOST, name, entry)
                    if os.path.getmtime(source) > built:
                        stale.append("%s (%s is newer)" % (name, entry))
        if not checked:
            self.skipTest("no native tool has been built here")
        self.assertEqual(
            stale, [],
            "built binaries are older than their source: %s -- this is the "
            "shape that cost every typed character on 2026-08-16" % stale)


if __name__ == "__main__":
    unittest.main()
