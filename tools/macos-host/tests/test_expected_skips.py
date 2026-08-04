"""Tests for the thing that reads the suite's own skip count.

Issue #71. `check_expected_skips.py` is the assertion CI makes about this suite,
so it is exactly the kind of code that must not report success while doing
nothing: a checker that accepted everything would look identical to a run with
nothing wrong in it, on every build, forever.

So both directions are covered here. It accepts the corpus skips CI genuinely
has -- 43 of them at the time of writing, against a runner with no
`~/eve-bot-logs` -- and it refuses the two that mean the environment is broken
rather than bare: a missing `elm` toolchain, and missing vendored parsers that
are checked into this repository.

**The toolchain reason is a cross-language coupling of the same kind #30 pins**,
across two files rather than two languages: `prerequisites.py` writes the skip
message and this checker matches it. A drift between them is silent and reads
exactly like a clean build, so it is asserted directly rather than remembered.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, MACOS_HOST_DIR)
import check_expected_skips  # noqa: E402

from prerequisites import NO_TOOLCHAIN_SKIP_REASON  # noqa: E402


def report_of(cases):
    """A JUnit report holding `cases`, each `(name, skip reason or None)`."""
    body = []
    for name, reason in cases:
        if reason is None:
            body.append('<testcase classname="c" name="%s"/>' % name)
        else:
            body.append(
                '<testcase classname="c" name="%s">'
                '<skipped message="%s">detail</skipped></testcase>'
                % (name, reason.replace("&", "&amp;").replace('"', "&quot;")
                   .replace("<", "&lt;")))
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-8")
    handle.write("<testsuites><testsuite>%s</testsuite></testsuites>"
                 % "".join(body))
    handle.close()
    return handle.name


def accepts(cases):
    """Whether the checker passes this run, with what it printed."""
    path = report_of(cases)
    try:
        out = io.StringIO()
        return check_expected_skips.report([path], out), out.getvalue()
    finally:
        os.unlink(path)


# The reasons a run with no `~/eve-bot-logs` and no client game logs produces,
# read off a real CI-shaped run rather than invented. Every one of them is a
# case that cannot report on evidence it does not have.
CORPUS_SKIPS = [
    "no recorded runs in ~/eve-bot-logs",
    "no recorded runs at /home/runner/eve-bot-logs",
    "no recorded runs to read",
    "none of the recorded runs are present",
    "no recorded mission_run11.log",
    "no recorded run10 in ~/eve-bot-logs",
    "run 13's log is not on this machine",
    "no recorded game logs in ~/Documents/EVE/logs/Gamelogs",
    "no recorded game logs on this machine",
    "no recorded run flew a capsule",
    "no game log lines recorded under /home/runner/eve-bot-logs",
    "none of mission_run{11,18,21,22}.log is on this machine, so the recorded "
    "runs cannot be consulted here",
]


class TheCorpusSkipsCiActuallyHasArePermitted(unittest.TestCase):
    """Zero skips is the wrong assertion, and this is why."""

    def test_every_reason_a_bare_runner_produces_is_expected(self):
        for reason in CORPUS_SKIPS:
            with self.subTest(reason=reason):
                self.assertIsNone(check_expected_skips.unexpected(reason))

    def test_a_run_that_is_all_corpus_skips_and_real_work_passes(self):
        ok, printed = accepts(
            [("executed_%d" % index, None) for index in range(20)]
            + [("skipped_%d" % index, reason)
               for index, reason in enumerate(CORPUS_SKIPS)])
        self.assertTrue(ok, printed)
        self.assertIn("%d executed" % 20, printed)
        self.assertIn("%d skipped" % len(CORPUS_SKIPS), printed)


class ABrokenEnvironmentIsRefused(unittest.TestCase):

    def test_the_toolchain_skip_this_suite_writes_is_the_one_refused(self):
        """The coupling, in the direction that would otherwise be silent.

        `prerequisites.py` writes this reason and the checker matches it. If
        either is reworded on its own the build stays green while the skip it
        exists to catch walks straight through, so the real string is asserted
        rather than a copy of it.
        """
        complaint = check_expected_skips.unexpected(
            NO_TOOLCHAIN_SKIP_REASON.split("\n")[0])
        self.assertIsNotNone(
            complaint,
            "the toolchain skip reason is no longer refused by the checker")
        self.assertIn("elm", complaint)

    def test_a_run_carrying_the_toolchain_skip_fails(self):
        ok, printed = accepts(
            [("executed", None),
             ("skipped_for_elm", NO_TOOLCHAIN_SKIP_REASON.split("\n")[0])])
        self.assertFalse(ok, printed)
        self.assertIn("unexpected skip", printed)

    def test_missing_vendored_parsers_are_not_an_absent_prerequisite(self):
        # They are checked into this repository, so a runner without them has a
        # broken checkout rather than nothing to check.
        ok, printed = accepts(
            [("executed", None),
             ("skipped", "no vendored parsers under /x/implement/applications")])
        self.assertFalse(ok, printed)
        self.assertIn("checked in", printed)

    def test_a_reason_nobody_named_fails_rather_than_passing_quietly(self):
        ok, printed = accepts(
            [("executed", None), ("skipped", "some new prerequisite is absent")])
        self.assertFalse(ok, printed)
        self.assertIn("EXPECTED", printed)

    def test_a_skip_with_no_reason_at_all_fails(self):
        ok, printed = accepts([("executed", None), ("skipped", "")])
        self.assertFalse(ok, printed)


class ARunThatExecutedNothingIsNotAPass(unittest.TestCase):
    """The failure #71 is about, in its purest form: everything skipped, `OK`."""

    def test_a_run_of_nothing_but_expected_skips_still_fails(self):
        ok, printed = accepts(
            [("skipped_%d" % index, "no recorded runs in ~/eve-bot-logs")
             for index in range(5)])
        self.assertFalse(ok, printed)
        self.assertIn("executed nothing", printed)

    def test_an_empty_report_fails(self):
        ok, printed = accepts([])
        self.assertFalse(ok, printed)
        self.assertIn("did not run", printed)


if __name__ == "__main__":
    unittest.main()
