"""The route directive must be read from every decision of a tick, not the last.

Issue #306. Two runs on 18 Aug parked with hours left -- one at 107 minutes of a
3 hour run, one after its first system of a 6 hour run, having already made 53
kills and 373,438 ISK. In both, the bot wrote `@host set-destination Lashkai`
into its status text 21 times, the host printed nothing at all, and the circuit
then latched off for the session at `routeAskGiveUpReadings`.

**Three things were ruled out before this was written.** ESI works: with the bot
mid-ask and the directive on screen, `esi_waypoint.py set --name "Lashkai"`
succeeded on the same name in the same minute on the same token. The travel path
works: after that manual call the bot picked the route up and resumed hunting
with no restart. And the directive was neither missing nor malformed -- 21 well
formed lines, at the end of the line, in `statusText` by construction, since the
`+++` lines in the log are what `log_decision` prints out of `cont["statusText"]`.

That left two candidates the log could not separate, because the block prints
only once the parsed name *changes* and so says nothing at all on the ordinary
reading: either `bot_requested_destination` returned `None` on all 21 readings,
or the block never saw those readings.

**It never saw them, and the corpus says so with no ambiguity.** A tick drains a
queue of tasks, and every `TaskCompletedEvent` hands back a fresh
`ContinueSession` with a freshly computed status text -- `log_decision`'s own
`[N.0]`, `[N.1]`, ... sub-numbering exists because of it. `cont` at the foot of
the loop is therefore whatever the bot decided *after* the last effect was
dispatched, and the route ask was only ever read off that one decision. Over the
37 recorded runs in `~/eve-bot-logs` that ask for a route at all:

    asks on a tick's final decision : 273
    asks on an earlier decision     : 454
    routes the host actually set    : 229
      ...on a tick whose final decision carried the directive : 229
      ...on a tick that carried it only earlier               :   0

Every route ever set came from an ask that happened to land on the decision the
tick ended on. Not one of the 454 that landed earlier was acted on. The Lashkai
runs are that, sustained: the ask comes on readings that are also driving a
context-menu cascade (`Open context menu on route element icon` runs throughout
them), so every tick ends on a menu step and the ask is never the last word.
The Hamse ask that *was* honoured, in the same run, came from a reading whose
step had nothing to dispatch -- a tick with one decision, which is trivially
also its last.

So the cases below drive `run_bot` itself rather than reading its source. The
tick loop is Python and its collaborators are two objects, so a scripted bot on
one side and a recording dispatcher on the other is enough to put a real
`ContinueSession` through it. **The discriminating pair is
`test_a_tick_with_no_effects_still_sets_the_route` against
`test_a_tick_that_dispatched_effects_sets_the_route_too`**: the first passes on
the code that shipped the bug, the second does not.

The suppression this must not break is the other half. The bot re-derives its
decision every reading and so asks on every reading it wants the route; the host
owes CCP one authenticated call per distinct name, not one per reading. That is
a lease and not a high-water mark -- an ask that goes away clears it, so the same
station asked for again later is acted on again.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import contextlib
import io
import os
import json
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)

sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import botlab_host  # noqa: E402

# The name both parked runs asked for, 21 times each, and the one that was set
# by hand from the same token in the same minute.
ASKED_FOR = "Lashkai"

# What the bot's status text really looks like on the reading that asks. The
# directive is the tail of the last line -- see `hostDirectiveSetDestination`.
def asking(name=ASKED_FOR, reading=1):
    return "\n".join([
        "Visited anomalies: 3.",
        "+ Hunt in this system.",
        "++ Nothing left to hunt here and no route set. Asking the host to set "
        "the destination to '%s' (%d/20 readings). @host set-destination %s"
        % (name, reading, name),
    ])


# The same tick, a decision later: the cascade that opens the route element's
# context menu says nothing about a route, because it is a different branch.
def working_the_menu(step="Open context menu on route element icon"):
    return "\n".join([
        "Visited anomalies: 3.",
        "+ Hunt in this system.",
        "++ " + step,
    ])


def continue_session(status_text, task_ids=()):
    """One decision, in the shape `run_bot` unpacks.

    `startTasks` is what makes a tick busy: each entry is dispatched and its
    completion brings back another decision, so a response carrying effects is a
    response whose status text is not the last one of its tick.
    """
    return {"ContinueSession": {
        "statusText": status_text,
        "startTasks": [{"taskId": task_id,
                        # Any tag but `RequestToVolatileProcess`, which
                        # `read_failure_reason` judges and these cases are not
                        # about.
                        "task": {"WindowsInputRequest": {"sequence": []}}}
                       for task_id in task_ids],
        "notifyWhenArrivedAtTime": None,
    }}


class ScriptedBot:
    """A bot process that answers each event with the next scripted response.

    Stands in for the node driver: `run_bot` talks to it through exactly two
    calls -- write a JSON line, read a JSON line -- so nothing about the real
    subprocess is needed to exercise the loop. Records the events it was sent so
    a case can say which ones a tick really produced.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.events = []
        self.stdin = self
        self.stdout = self
        self._pending = None

    # -- the stdin side
    def write(self, line):
        event = json.loads(line)
        self.events.append(list(event["eventAtTime"].keys())[0])
        if self.responses:
            self._pending = self.responses.pop(0)
        else:
            # A script that runs out ends the session cleanly rather than
            # hanging the loop or raising something a case would have to read
            # past.
            self._pending = {"FinishSession": {"statusText": "script exhausted"}}

    def flush(self):
        pass

    def close(self):
        pass

    # -- the stdout side
    def readline(self):
        return json.dumps(self._pending) + "\n"

    def wait(self, timeout=None):
        return 0


class RecordingVolatile:
    def __init__(self):
        self.destinations = []

    def take_connection_lost(self):
        return None

    def _set_autopilot_destination(self, request):
        self.destinations.append(request["name"])
        return {"Completed": {"bodyString": "destination set"}}


class RecordingDispatcher:
    def __init__(self, *args, **kwargs):
        self.volatile = RecordingVolatile()
        self.tasks = []

    def run_task(self, task):
        self.tasks.append(list(task.keys())[0])
        return {"WindowsInputResponse": "ok"}


@contextlib.contextmanager
def patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


def drive(responses, max_ticks):
    """Run the real tick loop over a scripted conversation.

    Returns the names the host carried to ESI, in order, and the bot it drove.
    The first response answers the opening `BotSettingsChangedEvent`, and each
    one after that answers whatever the loop sent next.
    """
    bot = ScriptedBot(responses)
    dispatcher = RecordingDispatcher()
    # The module reference rather than `subprocess.Popen` itself: patching the
    # real one would be in force for anything else sharing this process, and CI
    # gives a pytest-xdist worker several files in a row.
    launcher = types.SimpleNamespace(PIPE=None, Popen=lambda *a, **k: bot)
    with patched(botlab_host, "subprocess", launcher), \
            patched(botlab_host, "TaskDispatcher", lambda *a, **k: dispatcher), \
            contextlib.redirect_stderr(io.StringIO()) as log:
        botlab_host.run_bot("unused.js", "", max_ticks=max_ticks)
    return dispatcher.volatile.destinations, bot, log.getvalue()


class AnAskIsReadFromEveryDecisionOfTheTick(unittest.TestCase):
    """The pair that separates the two hypotheses #306 could not."""

    def test_a_tick_with_no_effects_still_sets_the_route(self):
        """The Hamse case: one decision, nothing to dispatch, so the ask is
        trivially the tick's last word. This passed before #306 too -- it is
        here so the pair below reads as a pair."""
        destinations, _, log = drive([continue_session(asking())], max_ticks=1)
        self.assertEqual([ASKED_FOR], destinations)
        self.assertIn("the bot asked for the route to", log)

    def test_a_tick_that_dispatched_effects_sets_the_route_too(self):
        """The Lashkai case, and the regression guard. The ask is on the
        decision that opens the context menu; completing that effect brings back
        a decision about the menu, which is where the tick ends. Reading only
        `cont` at the foot of the loop sees the menu step and nothing else."""
        destinations, bot, log = drive([
            continue_session(asking(), task_ids=["t1"]),
            continue_session(working_the_menu()),
        ], max_ticks=1)
        self.assertEqual(["TaskCompletedEvent"], bot.events[1:2],
                         "the tick must really have dispatched an effect")
        self.assertEqual([ASKED_FOR], destinations)
        self.assertIn("the bot asked for the route to", log)

    def test_an_ask_that_only_appears_after_a_task_completed_is_read(self):
        """The commonest shape of all, and the one a head-of-tick-only read
        would still miss. A tick opens on the decision that asks for the memory
        read; the bot cannot know the system is dry until that read comes back,
        so the ask is written on the decision *after* the first task completes,
        never on the one the tick opened with."""
        destinations, _, _ = drive([
            continue_session(working_the_menu("Read the game client's memory"),
                             task_ids=["read"]),
            continue_session(asking(), task_ids=["t1"]),
            continue_session(working_the_menu()),
        ], max_ticks=1)
        self.assertEqual([ASKED_FOR], destinations)

    def test_an_ask_buried_under_a_whole_cascade_is_still_read(self):
        """What the parked runs actually looked like: the ask opens the menu and
        four more decisions work it, so the ask is five decisions from the end."""
        destinations, _, _ = drive([
            continue_session(asking(), task_ids=["t1"]),
            continue_session(working_the_menu("Open context menu on route "
                                              "element icon"), task_ids=["t2"]),
            continue_session(working_the_menu("Click on menu entry 'Set "
                                              "Destination'"), task_ids=["t3"]),
            continue_session(working_the_menu("Wait for the menu to close"),
                             task_ids=["t4"]),
            continue_session(working_the_menu("Wait for progress in game.")),
        ], max_ticks=1)
        self.assertEqual([ASKED_FOR], destinations)

    def test_the_last_ask_of_a_tick_is_the_one_acted_on(self):
        """Two names inside one tick is a bot that changed its mind mid-tick,
        and what it wants is the later one. Seen live: `saxrat_run52.log` tick
        898 asks for 'Ana' on `[898.0]` and `[898.1]` and for 'Jaswelu' on
        `[898.2]`, which is where that tick ends."""
        destinations, _, _ = drive([
            continue_session(asking("Ana"), task_ids=["t1"]),
            continue_session(asking("Jaswelu")),
        ], max_ticks=1)
        self.assertEqual(["Jaswelu"], destinations)


class OneAuthenticatedCallPerDistinctName(unittest.TestCase):
    """The suppression #68 put in, which the fix above must not spend.

    The bot asks on every reading it wants the route -- 21 readings for one
    outcome in the runs #306 was filed about. Twenty-one calls to CCP for one
    route is what this stops, and it is a lease rather than a high-water mark so
    the second trip to the same station in a session still happens.
    """

    def test_a_standing_ask_is_one_call_however_many_readings_it_spans(self):
        destinations, _, _ = drive([
            continue_session(asking(reading=n), task_ids=["t%d" % n])
            for n in range(1, 6)
        ] + [continue_session(working_the_menu())], max_ticks=5)
        self.assertEqual([ASKED_FOR], destinations)

    def test_a_standing_ask_across_busy_ticks_is_still_one_call(self):
        """The same, with the ask buried mid-tick every time -- which is the
        arrangement the fix newly makes visible, and so the one where a lease
        that had stopped working would show up as 21 calls instead of 0."""
        responses = []
        for n in range(1, 6):
            responses.append(continue_session(asking(reading=n), task_ids=["t%d" % n]))
            responses.append(continue_session(working_the_menu()))
        destinations, _, _ = drive(responses, max_ticks=5)
        self.assertEqual([ASKED_FOR], destinations)

    def test_an_ask_that_goes_away_is_forgotten(self):
        """A tick with no directive on any of its decisions clears the lease, so
        the same station asked for again later is set again. A high-water mark
        would strand the second trip home of a session."""
        destinations, _, _ = drive([
            continue_session(asking()),
            continue_session(working_the_menu()),
            continue_session(asking()),
        ], max_ticks=3)
        self.assertEqual([ASKED_FOR, ASKED_FOR], destinations)

    def test_a_cascade_inside_a_tick_does_not_clear_the_lease(self):
        """The clearing is the tick's business, not one decision's. A decision
        that says nothing about the route while the ask still stands must not
        look like an ask that went away -- that would put the route back to CCP
        on every tick of a cascade."""
        responses = []
        for n in range(1, 4):
            responses.append(continue_session(asking(reading=n), task_ids=["a%d" % n]))
            responses.append(continue_session(working_the_menu(), task_ids=["b%d" % n]))
            responses.append(continue_session(working_the_menu()))
        destinations, _, _ = drive(responses, max_ticks=3)
        self.assertEqual([ASKED_FOR], destinations)

    def test_a_new_name_is_a_new_call(self):
        destinations, _, _ = drive([
            continue_session(asking("Lashkai"), task_ids=["t1"]),
            continue_session(working_the_menu()),
            continue_session(asking("Zhilshinou"), task_ids=["t2"]),
            continue_session(working_the_menu()),
        ], max_ticks=2)
        self.assertEqual(["Lashkai", "Zhilshinou"], destinations)

    def test_a_tick_that_never_asks_calls_nothing(self):
        destinations, _, log = drive([
            continue_session(working_the_menu(), task_ids=["t1"]),
            continue_session(working_the_menu()),
        ], max_ticks=1)
        self.assertEqual([], destinations)
        self.assertNotIn("the bot asked for the route to", log)


if __name__ == "__main__":
    unittest.main()
