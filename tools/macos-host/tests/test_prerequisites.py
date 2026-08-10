"""Tests for the two prerequisite gates themselves.

Issue #71. The harness that decides whether a case runs is the last place a
silent skip can be allowed to hide, so its own rules are asserted rather than
read: a missing toolchain raises, an absent corpus skips, and the probe that
decides "can this machine execute Elm at all" cannot be changed by anything
under test.

The structural case is the one that keeps this fixed. Eleven test files each
carried their own copy of the harness and their own smoke probe; within a day of
#71 being filed those copies had split into two dialects (#84 batched five of
them and left six alone). One copy is only one copy for as long as nothing adds
a twelfth, which is what `NoFileCarriesItsOwnHarness` is for.

Nothing here needs `elm`: the toolchain cases substitute what `open_repl` looks
for rather than removing it.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import glob
import os
import re
import shutil
import tempfile
import unittest

import prerequisites

HERE = os.path.dirname(os.path.abspath(__file__))
MISSION_RUNNER_BOT_ELM = os.path.join(prerequisites.MISSION_RUNNER_DIR,
                                      "Bot.elm")


def suite_sources():
    """Every test module in this directory, bar this one.

    This file is excluded because it is the scanner: the patterns it looks for
    are written out here, so it would report itself.
    """
    return sorted(path for path in glob.glob(os.path.join(HERE, "test_*.py"))
                  if os.path.basename(path) != os.path.basename(__file__))


class AMissingToolchainIsNotASkip(unittest.TestCase):
    """The whole of #71 in one property.

    A skip means "there was nothing to report on". A toolchain that is not
    there means "the report was never made", and a run must not print those two
    the same way.
    """

    def setUp(self):
        self.which = prerequisites.shutil.which
        prerequisites.shutil.which = lambda name: None
        self.addCleanup(setattr, prerequisites.shutil, "which", self.which)
        os.environ.pop(prerequisites.MAY_SKIP_ENV, None)

    def test_it_raises_rather_than_skipping(self):
        with self.assertRaises(prerequisites.ElmToolchainMissing) as raised:
            prerequisites.open_repl()
        self.assertNotIsInstance(raised.exception, unittest.SkipTest)

    def test_the_error_says_how_to_fix_it(self):
        with self.assertRaises(prerequisites.ElmToolchainMissing) as raised:
            prerequisites.open_repl()
        self.assertIn("brew install elm", str(raised.exception))

    def test_the_escape_hatch_downgrades_it_to_a_named_skip(self):
        # Named, because CI matches on the reason -- see
        # `check_expected_skips.py`, which refuses this one.
        os.environ[prerequisites.MAY_SKIP_ENV] = "1"
        self.addCleanup(os.environ.pop, prerequisites.MAY_SKIP_ENV, None)
        with self.assertRaises(unittest.SkipTest) as raised:
            prerequisites.open_repl()
        self.assertEqual(str(raised.exception),
                         prerequisites.NO_TOOLCHAIN_SKIP_REASON)

    def test_the_hatch_is_off_unless_it_is_set_to_something(self):
        for value, expected in [("", False), ("0", False), ("1", True),
                                ("yes", True)]:
            with self.subTest(value=value):
                os.environ[prerequisites.MAY_SKIP_ENV] = value
                self.addCleanup(os.environ.pop, prerequisites.MAY_SKIP_ENV, None)
                self.assertEqual(prerequisites.may_skip_without_elm(), expected)


class TheProbeCannotDriftWithTheCodeUnderTest(unittest.TestCase):
    """Each of the eleven copies probed a real function's current behaviour.

    `missionNameForDeclining "x"` answering `"x" : String` was one of them, so
    changing that function disabled a whole file without a word. The probe now
    asks for a declaration the harness itself appends to the scratch copy.
    """

    def test_the_probe_name_appears_nowhere_in_the_checked_in_source(self):
        with open(MISSION_RUNNER_BOT_ELM, encoding="utf-8") as source:
            self.assertNotIn(prerequisites.PROBE_NAME, source.read())

    def test_the_declaration_the_harness_appends_answers_the_probe(self):
        # The two halves are written apart -- a declaration and the string the
        # probe looks for -- so they are checked against each other.
        self.assertIn('"%s"' % prerequisites.PROBE_ANSWER,
                      prerequisites.PROBE_DECLARATION)
        self.assertIn("%s =" % prerequisites.PROBE_NAME,
                      prerequisites.PROBE_DECLARATION)

    def test_it_still_goes_through_bot_so_a_broken_app_cannot_pass_it(self):
        """The one thing the probe must remain coupled to.

        A probe on `1 + 1` cannot drift either, and would answer just as
        happily for an app that does not compile. This one is declared *in*
        `Bot.elm`, so it cannot be reached unless the app builds.
        """
        self.assertIn("elmReplHarnessProbe : String",
                      prerequisites.PROBE_DECLARATION)


class TheCorpusGateIsAThreeWayAnswer(unittest.TestCase):
    """Absent evidence skips; present evidence that disagrees must fail.

    Only the middle case is a skip, and the reason is stated so CI can tell it
    from a prerequisite the runner should have had.
    """

    def setUp(self):
        self.logs = tempfile.mkdtemp(prefix="test-recorded-runs-")
        self.addCleanup(shutil.rmtree, self.logs, True)
        real = prerequisites.EVE_BOT_LOGS
        prerequisites.EVE_BOT_LOGS = self.logs
        self.addCleanup(setattr, prerequisites, "EVE_BOT_LOGS", real)

    def record(self, name):
        path = os.path.join(self.logs, "mission_run%s.log" % name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# [1.0] (0s)\n")
        return path

    def test_no_recorded_run_skips_with_the_reason_stated(self):
        with self.assertRaises(unittest.SkipTest) as raised:
            prerequisites.recorded_runs("11", "17")
        self.assertIn("mission_run{11,17}.log", str(raised.exception))

    def test_the_runs_that_are_here_are_returned_and_the_rest_ignored(self):
        expected = self.record("11")
        self.assertEqual(prerequisites.recorded_runs("11", "17"),
                         [("11", expected)])

    def test_one_recorded_run_is_enough_to_stop_it_skipping(self):
        # The failure #78 found from the other side: a gate that answers on
        # what the *search* returned rather than on what evidence exists turns
        # "the corpus disagrees" into "there was no corpus", which reports a
        # finding where there is only an empty directory.
        self.record("21")
        self.assertEqual(len(prerequisites.recorded_runs("21")), 1)


class NoFileCarriesItsOwnHarness(unittest.TestCase):
    """One harness, and the assertion that it stays one.

    Eleven copies is how eleven probes drifted, and nothing structural stopped a
    twelfth. These read the test sources themselves.
    """

    def test_no_test_module_defines_its_own_repl_class(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r"^class ElmRepl\b", source.read(), re.M):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these define their own harness rather than importing the shared "
            "one from prerequisites.py")

    def test_no_test_module_runs_elm_for_itself(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r'subprocess\.run\(\s*\[\s*"elm"', source.read()):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these drive `elm` directly, so their cases are gated by whatever "
            "they decided for themselves rather than by open_repl")

    def test_no_test_module_decides_for_itself_whether_elm_is_available(self):
        # `@unittest.skipUnless(elm_is_available(), ...)` is the decorator that
        # turned an absent toolchain into a quiet skip in all eleven files.
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                text = source.read()
            if "elm_is_available" in text or re.search(
                    r'shutil\.which\(\s*"elm"', text):
                offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these answer the toolchain question themselves; open_repl owns it")

    def test_no_test_module_wraps_json_in_an_elm_literal_of_its_own(self):
        # Issue #174. Three files each dropped `json.dumps` output straight into
        # an Elm `"""..."""` string, and Elm eats the backslash escapes inside
        # one -- so every fixture holding a double quote decoded to `Nothing`
        # and the cases over it reported the parser answering nothing.
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                if re.search(r'"""\s*%s\s*"""', source.read()):
                    offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these build an Elm string literal by hand rather than through "
            "elm_json_literal, which is how a fixture comes to decode to "
            "nothing while its case still passes")

    def test_every_module_that_builds_a_reading_uses_the_shared_literal(self):
        offenders = []
        for path in suite_sources():
            with open(path, encoding="utf-8") as source:
                text = source.read()
            if ("decodeMemoryReadingFromString" in text
                    and "elm_json_literal" not in text):
                offenders.append(os.path.basename(path))
        self.assertEqual(
            offenders, [],
            "these hand the decoder a literal they escaped themselves")


if __name__ == "__main__":
    unittest.main()
