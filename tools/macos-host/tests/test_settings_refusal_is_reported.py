"""Tests that a bot refusing its settings reports *that*, and not something else.

A bot whose `parseBotSettings` rejects a key answers the very first event with
`FinishSession` and names the key. `run_bot` did not read that answer: it
assigned it to `response` and then overwrote `response` with the reply to
`SessionDurationPlannedEvent`.

By then the bot is finished and still holds `botSettings = Nothing`, so that
second event routes through `processEventAfterIntegrateEvent`, finds no
settings, and answers

    Unexpected order of events: I did not receive any bot-settings changed event.

which is what the operator saw. The true message -- `Failed to parse these
bot-settings: <key>` -- was destroyed, and its replacement describes a fault in
event ordering that did not happen. A launch that failed because saxrat was
handed the mission runner's drone settings cost a session's debugging under
that message, with the host, the port wrapper and the event order all
investigated and cleared before the real cause surfaced.

It only misled when `--session-duration-minutes` was set, and both launchers
always pass it, so in practice a settings typo *always* reported the wrong
cause.

These cases drive the real `run_bot` against a fake bot process -- a stdin that
records what was written and a stdout that answers from a script -- because the
defect is entirely in which events `run_bot` sends and when. Nothing here starts
`node`, compiles a bot, or touches a client.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
sys.path.insert(0, MACOS_HOST_DIR)

import botlab_host  # noqa: E402

REFUSAL = "Failed to parse these bot-settings: unknown setting name 'drone-count'"
WRONG_ONE = "Unexpected order of events: I did not receive any bot-settings changed event."


class _Stdin:
    def __init__(self):
        self.written = []
        self.closed = False

    def write(self, text):
        self.written.append(text)

    def flush(self):
        pass

    def close(self):
        self.closed = True


class _Stdout:
    """Answers from a script, and `""` once it runs out -- a closed pipe."""

    def __init__(self, responses):
        self.responses = list(responses)

    def readline(self):
        if not self.responses:
            return ""
        return json.dumps(self.responses.pop(0)) + "\n"


class _Proc:
    def __init__(self, responses):
        self.stdin = _Stdin()
        self.stdout = _Stdout(responses)
        self.waited = False

    def wait(self, timeout=None):
        self.waited = True


class RunBotAgainstAFakeBot(unittest.TestCase):
    """Drives the real `run_bot`, recording every event it sends."""

    def drive(self, responses, **kwargs):
        proc = _Proc(responses)
        real_popen = botlab_host.subprocess.Popen
        botlab_host.subprocess.Popen = lambda *a, **k: proc
        try:
            botlab_host.run_bot("bot.js", "drone-count=5",
                                session_duration_minutes=60, **kwargs)
        finally:
            botlab_host.subprocess.Popen = real_popen
        self.events = [json.loads(line)["eventAtTime"] for line in proc.stdin.written]
        self.proc = proc
        return self.events


class ARefusedSettingIsWhatIsReportedTest(RunBotAgainstAFakeBot):
    def setUp(self):
        self.drive([{"FinishSession": {"statusText": REFUSAL}}])

    def test_only_the_settings_event_is_ever_sent(self):
        # The whole defect: a second event on top of a finished bot is what
        # produced the misleading answer.
        self.assertEqual(len(self.events), 1, self.events)
        self.assertIn("BotSettingsChangedEvent", self.events[0])

    def test_the_session_duration_event_is_not_sent_after_a_refusal(self):
        self.assertNotIn("SessionDurationPlannedEvent",
                         [key for event in self.events for key in event])

    def test_the_bot_process_is_closed_down(self):
        # Same shutdown the main loop does, rather than leaving `node` running.
        self.assertTrue(self.proc.stdin.closed)
        self.assertTrue(self.proc.waited)


class TheRefusalReachesTheOperatorTest(RunBotAgainstAFakeBot):
    def test_the_refusal_is_printed_to_stderr(self):
        from io import StringIO
        real_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            self.drive([{"FinishSession": {"statusText": REFUSAL}}])
            printed = sys.stderr.getvalue()
        finally:
            sys.stderr = real_stderr
        self.assertIn(REFUSAL, printed)
        self.assertNotIn(WRONG_ONE, printed)

    def test_the_console_is_told_the_session_finished(self):
        class Console:
            def __init__(self):
                self.finished = None

            def note_finished(self, reason):
                self.finished = reason

        console = Console()
        self.drive([{"FinishSession": {"statusText": REFUSAL}}], console=console)
        self.assertEqual(console.finished, REFUSAL)


class AnAcceptedSettingStillStartsTheSessionTest(RunBotAgainstAFakeBot):
    """The check must not cost a launch that was fine."""

    def test_the_duration_event_still_follows_a_good_settings_reply(self):
        events = self.drive([
            {"ContinueSession": {"statusText": "Succeeded parsing these bot-settings.",
                                 "startTasks": []}},
            {"FinishSession": {"statusText": "done"}},
        ])
        self.assertEqual(len(events), 2, events)
        self.assertIn("BotSettingsChangedEvent", events[0])
        self.assertIn("SessionDurationPlannedEvent", events[1])


if __name__ == "__main__":
    unittest.main()
