"""Tests for the thing that reads how the suite packs onto the workers.

Issue #199. `--dist loadfile` is kept on a measurement -- no single file comes
near the floor the run could not beat anyway -- and a measurement recorded in a
comment stops being true without anybody hearing. `check_file_packing.py` is
the assertion that replaces the comment, so it has to fail when the shape it
describes changes, rather than agreeing with every run forever.

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
import check_file_packing  # noqa: E402


def report_of(cases):
    """A JUnit report holding `cases`, each `(module, class, seconds)`."""
    body = [
        '<testcase classname="tools.macos-host.tests.%s.%s" name="case_%d" '
        'time="%s"/>' % (module, klass, index, seconds)
        for index, (module, klass, seconds) in enumerate(cases)]
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".xml", delete=False, encoding="utf-8")
    handle.write("<testsuites><testsuite>%s</testsuite></testsuites>"
                 % "".join(body))
    handle.close()
    return handle.name


def accepts(cases, workers):
    """Whether the checker passes this run, with what it printed."""
    path = report_of(cases)
    try:
        out = io.StringIO()
        return check_file_packing.report([path], workers, out), out.getvalue()
    finally:
        os.unlink(path)


def spread(module, total, cases=4, klass="SomeClass"):
    """`total` seconds of one file, split over several cases and classes."""
    return [(module, "%s%d" % (klass, index), total / cases)
            for index in range(cases)]


class TheFileIsWhatIsCountedRatherThanTheClass(unittest.TestCase):
    """`--dist loadfile` deals out files, so files are the unit that matters.

    pytest writes no `file` attribute, only the dotted `classname`, so this is
    the one place a rename could quietly turn every case into its own "file"
    and make the packing look perfect.
    """

    def test_the_module_is_read_out_of_a_dotted_classname(self):
        self.assertEqual(
            check_file_packing.module_of(
                "tools.macos-host.tests.test_docking_run_in.RunTwentySeven"),
            "test_docking_run_in")

    def test_a_case_outside_a_class_still_belongs_to_its_file(self):
        self.assertEqual(
            check_file_packing.module_of("tools.macos-host.tests.test_bot_help"),
            "test_bot_help")

    def test_every_class_in_one_file_adds_up_to_that_file(self):
        totals, total = check_file_packing.file_totals(
            [report_of(spread("test_one", 40) + spread("test_two", 10))])
        self.assertEqual(dict(totals), {"test_one": 40.0, "test_two": 10.0})
        self.assertEqual(total, 50.0)


class AFileUnderTheFloorIsNotWhatBoundsTheRun(unittest.TestCase):

    def test_the_shape_this_suite_has_today_passes(self):
        # This suite's own shape, off the CI run #199 was measured on: 86 files
        # and 3,643s of case time on four workers, the longest of them 256s
        # against a 911s floor. That margin is why the flag is left alone.
        ok, printed = accepts(
            spread("test_longest", 256)
            + [("test_%d" % index, "C", 40.0) for index in range(85)],
            workers=4)
        self.assertTrue(ok, printed)
        self.assertIn("granularity is not what bounds this run", printed)

    def test_a_file_that_grows_past_the_floor_fails(self):
        # The staleness the comment could not announce: one file long enough
        # that three workers finish and wait for it, on a run that otherwise
        # looks exactly like a healthy one.
        ok, printed = accepts(
            spread("test_grown", 600)
            + [("test_%d" % index, "C", 10.0) for index in range(100)],
            workers=4)
        self.assertFalse(ok, printed)
        self.assertIn("test_grown", printed)
        self.assertIn("sets the wall clock", printed)

    def test_more_workers_than_the_suite_can_use_is_the_same_failure(self):
        # The floor is the case time divided by the workers, so a wider runner
        # reaches the same conclusion sooner -- which is the answer wanted, not
        # a false alarm: at that width the file really is the constraint.
        cases = spread("test_longest", 300) + [
            ("test_%d" % index, "C", 30.0) for index in range(100)]
        self.assertTrue(accepts(cases, workers=4)[0])
        self.assertFalse(accepts(cases, workers=16)[0])

    def test_an_empty_report_fails_rather_than_packing_perfectly(self):
        # A run that collected nothing has no longest file, which is a shape
        # that satisfies every comparison here and means nothing at all.
        ok, printed = accepts([], workers=4)
        self.assertFalse(ok, printed)
        self.assertIn("did not run", printed)


if __name__ == "__main__":
    unittest.main()
