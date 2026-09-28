"""A slow UI-root search and a hung one looked identical, and one got reported
as a broken launcher.

On 2026-09-12 the Spotlight autopilot app was reported busted. It was not: the
root search took **81 seconds** on that client and then the bot flew its route
perfectly. What the operator had on screen for those 81 seconds was the bot's
own status line, reprinted unchanged every tick:

    EVE Online framework status:
    Search the address of the UI root in process 87630

That line is the *bot's*, re-derived each tick from a setup state that has
genuinely not moved, so it says nothing about whether the host is working. And
this repository has actually shipped a hang that presents the same way -- #455,
where `character_name` living on the wrong object turned every
`ListGameClientProcessesRequest` into `ProcessNotFound` and the framework tore
the volatile process down and rebuilt it forever. A setup line repeating for
minutes is therefore a thing an operator has already been burned by, and
"working, just slow" is not distinguishable from it without help.

So the host now says which phase it is in, and marks time inside a phase. The
cases below are about that reporting being *there* and being *bounded* -- a
progress report that floods the window is its own failure, since the whole point
is that the operator can see one line change.

Nothing here reads a live client, a bot, or the recorded runs.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import io
import os
import sys
import time
import unittest
from contextlib import redirect_stderr

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))

import botlab_host  # noqa: E402


PID = 4242


def host_with_pending_search():
    """A host mid-search, without having started the real worker thread.

    `_search_ui_root` starts a background thread that dumps process memory, so
    the state it would have created is built here instead -- these cases are
    about what gets *said*, and saying it must not require a client.
    """
    host = botlab_host.VolatileHost()
    # `begin` is wall-clock milliseconds and the heartbeat falls back to it
    # before the worker has recorded a monotonic start, so a fixed literal here
    # would print an elapsed time of years and make a real reading unreadable.
    host.root_search[PID] = {"begin": int(time.time() * 1000), "result": "pending"}
    return host


class ThePhasesAnnounceThemselves(unittest.TestCase):
    def test_a_phase_names_the_pid_and_the_elapsed_time(self):
        host = host_with_pending_search()
        err = io.StringIO()
        with redirect_stderr(err):
            host._note_root_search_phase(PID, "dumping process memory", began=0.0)
        line = err.getvalue()
        self.assertIn(str(PID), line)
        self.assertIn("dumping process memory", line)
        self.assertIn("UI root search", line)
        # The host's own log convention: every line it writes starts with '#'.
        self.assertTrue(line.lstrip().startswith("#"), line)

    def test_the_phase_is_recorded_so_the_heartbeat_can_repeat_it(self):
        host = host_with_pending_search()
        with redirect_stderr(io.StringIO()):
            host._note_root_search_phase(PID, "indexing the dump", began=0.0)
        self.assertEqual(host.root_search[PID]["phase"], "indexing the dump")

    def test_reporting_progress_can_never_break_the_search(self):
        """The one thing here with no business raising.

        A search that dies because it could not *describe itself* would be this
        change causing the failure it exists to explain.
        """
        host = host_with_pending_search()
        host.root_search = None  # any breakage inside the reporter at all
        with redirect_stderr(io.StringIO()):
            host._note_root_search_phase(PID, "walking up to the UI root", began=0.0)

    def test_an_unknown_process_does_not_raise(self):
        host = botlab_host.VolatileHost()
        with redirect_stderr(io.StringIO()):
            host._note_root_search_phase(99999, "checking the cached root", began=0.0)


class TheHeartbeatMarksTimeWithoutFloodingTheWindow(unittest.TestCase):
    """The phase lines alone leave a silence as long as the dump. The heartbeat
    is what makes the clock visibly move inside one -- but it is asked once per
    tick, so it has to decline most of the times it is asked."""

    def _pending_response(self, host):
        err = io.StringIO()
        with redirect_stderr(err):
            response = host._search_ui_root(PID)
        return response, err.getvalue()

    def test_the_first_ask_speaks(self):
        host = host_with_pending_search()
        _, err = self._pending_response(host)
        self.assertIn("UI root search", err)
        self.assertIn("not a hang", err)

    def test_the_next_ask_a_moment_later_stays_quiet(self):
        host = host_with_pending_search()
        self._pending_response(host)
        _, err = self._pending_response(host)
        self.assertEqual("", err)

    def test_it_speaks_again_once_the_interval_has_passed(self):
        host = host_with_pending_search()
        self._pending_response(host)
        host.root_search[PID]["heartbeat_at"] -= (
            host.ROOT_SEARCH_HEARTBEAT_SECONDS + 1)
        _, err = self._pending_response(host)
        self.assertIn("UI root search", err)

    def test_the_interval_is_long_enough_to_be_a_clock_and_not_a_flood(self):
        """A bot tick is about two seconds, so anything under a few seconds
        would print several times a tick and bury the thing it is marking."""
        self.assertGreaterEqual(botlab_host.VolatileHost.ROOT_SEARCH_HEARTBEAT_SECONDS, 5)
        self.assertLessEqual(botlab_host.VolatileHost.ROOT_SEARCH_HEARTBEAT_SECONDS, 60)

    def test_the_pending_answer_is_unchanged_by_any_of_this(self):
        """The report rides alongside the protocol answer and must not alter
        it: `SearchUIRootAddressInProgress` is what keeps the framework waiting
        rather than tearing the volatile process down."""
        host = host_with_pending_search()
        response, _ = self._pending_response(host)
        self.assertEqual(response["processId"], PID)
        self.assertIn("SearchUIRootAddressInProgress", response["stage"])

    def test_a_finished_search_answers_completed_and_says_nothing_extra(self):
        host = botlab_host.VolatileHost()
        host.roots[PID] = 0xDEADBEEF
        err = io.StringIO()
        with redirect_stderr(err):
            response = host._search_ui_root(PID)
        self.assertIn("SearchUIRootAddressCompleted", response["stage"])
        self.assertEqual("", err.getvalue())


class TheReportCoversTheWholeSearchAndNotJustItsStart(unittest.TestCase):
    """Read out of the source rather than executed: reaching the real phases
    needs a live client and a process dump, which is exactly what these cases
    are written to avoid. What is asserted is that each phase of the macOS path
    has a line, so a future phase added without one is visible here."""

    def setUp(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "botlab_host", "botlab_host.py")
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        start = source.index("def _find_ui_root")
        self.body = source[start:source.index("def _search_ui_root_worker", start)]

    def test_the_dump_is_announced_before_it_starts(self):
        """The longest single phase, and the one whose silence started this."""
        self.assertIn("dumping process memory", self.body)

    def test_every_phase_of_the_search_reports(self):
        for name in ["checking the cached root", "indexing the dump",
                     "scanning for a seed object", "bootstrapping the str type",
                     "walking up to the UI root"]:
            self.assertIn(name, self.body, name)

    def test_both_outcomes_are_announced(self):
        self.assertIn("found the UI root", self.body)
        self.assertIn("GAVE UP", self.body)

    def test_the_cached_path_says_it_was_cached(self):
        """Otherwise the fast path is silent and an operator cannot tell a
        cache hit from a search that has not begun."""
        self.assertIn("reused the cached root", self.body)


if __name__ == "__main__":
    unittest.main()
