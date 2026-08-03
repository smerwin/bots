"""Tests for cycle_run.sh's wait for a run's first decision.

Every case here is a shape a real start() has to tell apart: a healthy run that
has not decided yet, one that died in `elm make`, one whose launcher never ran,
and the window right after `screen -X stuff` where nothing is running because
nothing has started. The point is that a failing run says so in seconds and a
slow one is still given its five minutes.

Nothing here starts a bot, a screen session or a game client. The tests source
cycle_run.sh -- the dispatch at its foot is guarded on ZSH_EVAL_CONTEXT for
exactly this -- replace bot_pids() with a stub, and call
wait_for_first_decision() against a file on disk. Polls are shortened to 50ms
via BOT_WAIT_POLL_SECONDS so the whole file runs in about a second.

The elm-failure fixture is not invented: it is what botlab_host.compile_bot
leaves in the log, captured by running it against a deliberately broken
elm.json. Note the exception line carries ANSI colour even through `tee`, which
is why the detection anchors on the plain traceback header instead.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import os
import subprocess
import tempfile
import textwrap
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CYCLE_RUN = os.path.join(os.path.dirname(HERE), "cycle_run.sh")

# The tail of a run that died in `elm make`, reproduced from botlab_host.py.
# The escapes are Python's own traceback colouring, present in the log because
# it colours regardless of stderr being a pipe into `tee`.
ELM_FAILURE = (
    "# elm make Main.elm --output=/tmp/build/bot.js (cwd=/tmp/build)\n"
    "\n"
    "Dependencies ready!\n"
    "\n"
    "-- TYPE MISMATCH ---------------------------------------------------- Bot.elm\n"
    "\n"
    "The 1st argument to `decideNextAction` is not what I expect:\n"
    "\n"
    "Traceback (most recent call last):\n"
    '  File "/tmp/botlab_host.py", line 1795, in <module>\n'
    "    main()\n"
    "  File \"/tmp/botlab_host.py\", line 371, in compile_bot\n"
    '    raise RuntimeError("elm make failed")\n'
    "\x1b[1;35mRuntimeError\x1b[0m: \x1b[35melm make failed\x1b[0m\n"
)

# A healthy startup that has not reached its first decision: the launcher is
# talking, nothing has gone wrong, and no decision line exists yet.
COMPILING = (
    "# bot source: /Users/x/bots/implement/applications/eve-online/eve-online-mission-runner\n"
    "# patching elm.json elm-version '0.19.1' -> '0.19.2'\n"
    "Dependencies ready!\n"
    "Compiling (14)\n"
)

# The first decision, as start() recognises it.
DECISION = COMPILING + "+ Read game client process list.\n"


def wait(log_path, pids="", polls=6, poll_seconds="0.05", extra_env=None):
    """Run wait_for_first_decision against `log_path` with bot_pids() stubbed.

    `pids` is what the stub prints -- empty for "nothing matching BOT_PATTERNS
    is alive". Returns (exit status, combined output).
    """
    driver = textwrap.dedent(f"""
        source {CYCLE_RUN}
        bot_pids() {{ print -n "{pids}" }}
        wait_for_first_decision "{log_path}"
    """)
    env = dict(os.environ)
    env.update({
        "BOT_WAIT_POLL_SECONDS": poll_seconds,
        "BOT_WAIT_POLL_COUNT": str(polls),
        # Sourcing the script mkdir -p's this, so keep it off the real one.
        "BOT_LOG_DIR": tempfile.mkdtemp(prefix="cycle-run-test-"),
    })
    env.update(extra_env or {})
    proc = subprocess.run(["zsh", "-c", driver], capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


class WaitForFirstDecision(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="cycle-run-log-")

    def log(self, contents, name="mission_run7.log"):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(contents)
        return path

    def test_first_decision_is_success(self):
        status, out = wait(self.log(DECISION), pids="4242")
        self.assertEqual(status, 0, out)
        self.assertIn("live: 4242", out)
        self.assertIn("Read game client process list.", out)

    def test_elm_failure_fails_immediately(self):
        # The whole point of the issue: this used to cost five minutes.
        started = time.monotonic()
        status, out = wait(self.log(ELM_FAILURE), pids="4242", polls=100, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertLess(time.monotonic() - started, 2.0, "did not fail on the first poll")
        self.assertIn("failed before its first decision", out)
        # A live process does not excuse it -- elm make can still be running.
        self.assertIn("TYPE MISMATCH", out)
        self.assertIn("elm make failed", out)

    def test_launcher_that_never_ran_fails_immediately(self):
        # A stale absolute path in BOT_LAUNCHER, which cost a whole cycle once.
        log = self.log("zsh: no such file or directory: ./run_mission.sh\n")
        status, out = wait(log, pids="", polls=100, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertIn("failed before its first decision", out)
        self.assertIn("no such file or directory", out)

    def test_dead_run_without_fatal_output(self):
        # Nothing diagnostic in the log -- killed, OOM, client gone. The verdict
        # comes from the process check plus a log that stopped growing.
        status, out = wait(self.log(COMPILING), pids="", polls=100, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertIn("the run is gone", out)
        self.assertIn("Compiling (14)", out)

    def test_slow_run_with_a_live_process_is_not_declared_dead(self):
        # A static log is not death while something is still running: elm can
        # sit between lines, and this is the signal the original comment
        # deliberately did not trust.
        status, out = wait(self.log(COMPILING), pids="4242", polls=6, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertNotIn("the run is gone", out)
        self.assertIn("no decisions after", out)

    def test_not_started_yet_is_not_declared_dead(self):
        # The race the original comment guards: `screen -X stuff` has returned,
        # the session's shell has not read the line, so nothing is running and
        # `tee` has created an empty log. Two polls of that must not be death.
        status, out = wait(self.log(""), pids="", polls=6, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertNotIn("the run is gone", out)
        self.assertIn("no decisions after", out)
        self.assertIn("is empty", out)

    def test_missing_log_is_not_declared_dead(self):
        # Same race, one step earlier: `tee` has not created the file at all.
        status, out = wait(os.path.join(self.dir, "never_created.log"), pids="",
                           polls=6, poll_seconds="0.05")
        self.assertEqual(status, 1, out)
        self.assertNotIn("the run is gone", out)
        self.assertIn("no decisions after", out)

    def test_growing_log_with_no_process_is_not_yet_death(self):
        # A log still being written is a run still alive, whatever pgrep says --
        # the process check races the write. Only a log that has stopped counts.
        log = self.log(COMPILING)
        driver = textwrap.dedent(f"""
            source {CYCLE_RUN}
            bot_pids() {{ print -n "" }}
            ( for i in 1 2 3 4 5 6 7 8; do print "Compiling ($i)" >> {log}; sleep 0.05; done ) &
            wait_for_first_decision "{log}"
        """)
        env = dict(os.environ)
        env.update({"BOT_WAIT_POLL_SECONDS": "0.05", "BOT_WAIT_POLL_COUNT": "6",
                    "BOT_LOG_DIR": tempfile.mkdtemp(prefix="cycle-run-test-")})
        proc = subprocess.run(["zsh", "-c", driver], capture_output=True, text=True, env=env)
        out = proc.stdout + proc.stderr
        self.assertNotIn("the run is gone", out)


class DispatchGuard(unittest.TestCase):
    """Sourcing must not cycle the bot.

    The guard the tests above rely on is itself the kind of thing that fails
    silently, so check both directions: sourcing runs nothing, and executing
    still dispatches.
    """

    def test_sourcing_does_not_dispatch(self):
        driver = f"source {CYCLE_RUN}\nprint SOURCED-CLEANLY\n"
        env = dict(os.environ)
        env["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="cycle-run-test-")
        proc = subprocess.run(["zsh", "-c", driver], capture_output=True, text=True, env=env)
        out = proc.stdout + proc.stderr
        self.assertIn("SOURCED-CLEANLY", out)
        self.assertNotIn("stopping", out)
        self.assertNotIn("starting", out)

    def test_executing_still_dispatches(self):
        # --status is the only path safe to run here: it reads pgrep and the log
        # directory and touches neither the screen session nor any process.
        env = dict(os.environ)
        env["BOT_LOG_DIR"] = tempfile.mkdtemp(prefix="cycle-run-test-")
        proc = subprocess.run([CYCLE_RUN, "--status"], capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertRegex(proc.stdout, r"not running|running: ")


if __name__ == "__main__":
    unittest.main()
