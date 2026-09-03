"""Tests for `WINDOW_LINE_RE` and what a missing Screen Recording grant does to it.

Issue #363: `window_probe.c`'s `print_string_field` writes the bare, unquoted
literal `name=(null)` for a window title it cannot read -- which is what every
window owned by another process prints when the terminal app running this host
lacks the Screen Recording grant. `WINDOW_LINE_RE` only ever matched
`name="([^"]*)"`, so every such line failed to match, `_windows_for` returned
`[]`, and `find_eve_processes` returned `[]` even though `lsappinfo` had found
the right pid -- surfacing as the Elm side's "I did not find an EVE Online
client process", which points an operator at the wrong half of the problem: the
process *was* found, its window's title just could not be read.

Nothing here needs a running client, `window_probe`, or `lsappinfo`; every case
either exercises the regex directly or replaces `subprocess.run` with a
recorder, the same pattern `test_eve_repl.py` uses for its own window lookup.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))
import botlab_host  # noqa: E402


def probe_line(window=549, owner_pid=1234, layer=0, owner="EVE", name='""',
                x=0.0, y=38.0, w=1710.0, h=1069.0, display=1, backing_scale=2.00):
    """One `window_probe --all` output line, `name` given pre-quoted (or as
    the literal `(null)`) so a caller can pass either form directly."""
    return (f'window={window} owner_pid={owner_pid} layer={layer} owner="{owner}" '
            f'name={name} bounds={{x={x} y={y} w={w} h={h}}}(points) '
            f'display={display} backing_scale={backing_scale:.2f}')


LSAPPINFO_WITH_GAME = (
    'ASN="com.ccpgames.eveonline"    bundleID="com.ccpgames.eveonline"    pid = 4242    '
)
LSAPPINFO_WITHOUT_GAME = (
    'ASN="com.apple.finder"    bundleID="com.apple.finder"    pid = 99    '
)


class WindowLineRegexTests(unittest.TestCase):
    """The regex itself, with no subprocess involved."""

    def test_a_quoted_title_still_matches_and_is_captured(self):
        """The existing case: `window_probe` could read the title."""
        m = botlab_host.WINDOW_LINE_RE.match(
            probe_line(name='"EVE - Gal Bistot"'))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(4), "EVE - Gal Bistot")

    def test_an_empty_quoted_title_still_matches_and_is_captured(self):
        """An ordinary untitled window, `name=""`, is not the `(null)` case."""
        m = botlab_host.WINDOW_LINE_RE.match(probe_line(name='""'))
        self.assertIsNotNone(m)
        self.assertEqual(m.group(4), "")

    def test_an_unreadable_title_now_matches_with_no_captured_name(self):
        """The new case: no Screen Recording grant, `window_probe` writes the
        bare, unquoted `(null)` rather than a quoted string."""
        m = botlab_host.WINDOW_LINE_RE.match(probe_line(name="(null)"))
        self.assertIsNotNone(m)
        self.assertIsNone(m.group(4))

    def test_the_other_fields_are_unaffected_by_which_name_form_is_used(self):
        m = botlab_host.WINDOW_LINE_RE.match(
            probe_line(name="(null)", window=550, owner_pid=1234, layer=25,
                       x=0.0, y=38.0, w=1710.0, h=1069.0))
        self.assertEqual(m.group(1), "550")
        self.assertEqual(m.group(2), "1234")
        self.assertEqual(m.group(3), "25")
        self.assertEqual((m.group(5), m.group(6), m.group(7), m.group(8)),
                          ("0.0", "38.0", "1710.0", "1069.0"))


class WindowsForTests(unittest.TestCase):
    """`_windows_for` parses `window_probe`'s stdout into row dicts."""

    def _rows_for(self, stdout, pid=1234):
        with mock.patch.object(botlab_host.subprocess, "run",
                                return_value=mock.Mock(stdout=stdout)):
            return botlab_host._windows_for(pid)

    def test_a_readable_title_comes_through_as_given(self):
        rows = self._rows_for(probe_line(name='"EVE - Gal Bistot"') + "\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "EVE - Gal Bistot")

    def test_an_unreadable_title_comes_through_as_an_empty_string_not_dropped(self):
        """This is the failure #363 reports: the line used to fail to match
        `WINDOW_LINE_RE` entirely and the window vanished from the result."""
        rows = self._rows_for(probe_line(name="(null)") + "\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "")

    def test_a_mix_of_readable_and_unreadable_titles_keeps_both_windows(self):
        stdout = (
            probe_line(window=549, name="(null)", w=1710.0, h=38.0) + "\n" +
            probe_line(window=550, name='"EVE - Gal Bistot"', w=1710.0, h=1069.0) + "\n"
        )
        rows = self._rows_for(stdout)
        self.assertEqual({r["window"] for r in rows}, {549, 550})
        by_window = {r["window"]: r["name"] for r in rows}
        self.assertEqual(by_window[549], "")
        self.assertEqual(by_window[550], "EVE - Gal Bistot")


class FindEveProcessesTests(unittest.TestCase):
    """`find_eve_processes` end to end, `lsappinfo` and `window_probe` both
    replaced with recorders keyed on which command was asked for."""

    def _run(self, lsappinfo_stdout, window_probe_stdout):
        def fake_run(cmd, **kwargs):
            if cmd[0] == "lsappinfo":
                return mock.Mock(stdout=lsappinfo_stdout)
            return mock.Mock(stdout=window_probe_stdout)
        with mock.patch.object(botlab_host.subprocess, "run", side_effect=fake_run):
            return botlab_host.find_eve_processes()

    def test_a_process_with_only_unreadable_windows_is_still_found(self):
        """The fix: a missing Screen Recording grant degrades to a window with
        no title, which the framework already handles via the "EVE" fallback,
        rather than to no process being found at all."""
        procs = self._run(
            LSAPPINFO_WITH_GAME,
            probe_line(owner_pid=4242, layer=0, name="(null)") + "\n",
        )
        self.assertEqual(len(procs), 1)
        self.assertEqual(procs[0]["processId"], 4242)
        self.assertEqual(procs[0]["mainWindowTitle"], "EVE")

    def test_a_readable_window_title_is_carried_through_unchanged(self):
        procs = self._run(
            LSAPPINFO_WITH_GAME,
            probe_line(owner_pid=4242, layer=0, name='"EVE - Gal Bistot"') + "\n",
        )
        self.assertEqual(procs[0]["mainWindowTitle"], "EVE - Gal Bistot")

    def test_pid_found_but_genuinely_no_window_names_the_pid_on_stderr(self):
        """A pid found by lsappinfo but with no window at all (not even an
        unreadable one) is the case the caller's own "I did not find an EVE
        Online client process" wording misdescribes -- the log should say a
        process *was* found."""
        with mock.patch.object(sys, "stderr") as fake_stderr:
            procs = self._run(LSAPPINFO_WITH_GAME, "")
        self.assertEqual(procs, [])
        printed = "".join(c.args[0] for c in fake_stderr.write.mock_calls if c.args)
        self.assertIn("4242", printed)
        self.assertIn("found the EVE process", printed)
        self.assertIn("Screen Recording", printed)

    def test_no_process_found_at_all_says_nothing_new_on_stderr(self):
        """The genuinely-absent-process case is unaffected: no pid to name, so
        no distinguishing message -- this stays the Elm side's wording."""
        with mock.patch.object(sys, "stderr") as fake_stderr:
            procs = self._run(LSAPPINFO_WITHOUT_GAME, "")
        self.assertEqual(procs, [])
        fake_stderr.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
