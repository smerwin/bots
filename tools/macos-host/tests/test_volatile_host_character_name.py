"""The character-name filter lived on two objects, and only one of them was
ever given it.

`find_eve_processes(character_name=...)` lets the host pick which EVE client
to drive when more than one is running (see that function's own doc comment).
`TaskDispatcher.__init__` stored the setting on itself, but the object that
actually calls `find_eve_processes` for `ListGameClientProcessesRequest` is
`self.volatile`, a separate `VolatileHost` -- which never had the attribute at
all. Every reading of it raised `AttributeError`.

That exception is exactly the one `run_task`'s `RequestToVolatileProcess`
handler catches with a blanket `except Exception` and turns into
`{"Err": {"ProcessNotFound": True}}` -- the response
`EveOnline.BotFramework.integrateTaskResult` reads as "the volatile process
died", answered by resetting `createVolatileProcessResult` to `Nothing` and
recreating it. So the bug never surfaced as a Python traceback or a bot error
message: it surfaced as the setup state machine oscillating between
`CreateVolatileProcess` and `ListGameClientProcessesRequest` forever, which is
indistinguishable from a hung client until somebody reads the host's own
stderr for the swallowed exception.

`character_name` is now a constructor argument of `VolatileHost` itself, set
once at construction from `TaskDispatcher`'s own argument and never mutated
afterward -- so the two cannot drift apart again the way this file's own
`TheAttributeLivesWhereItIsRead` case would catch if they did.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "botlab_host"))

import botlab_host  # noqa: E402


class TheAttributeLivesWhereItIsRead(unittest.TestCase):
    """`handle_request` is a method of `VolatileHost`, not `TaskDispatcher`,
    so the value it reads has to be `VolatileHost`'s own -- storing it only on
    the dispatcher (the bug this file is about) leaves it looking wired while
    every read of it raises."""

    def test_volatile_host_defaults_to_no_filter(self):
        self.assertIsNone(botlab_host.VolatileHost().character_name)

    def test_volatile_host_takes_the_name_directly(self):
        host = botlab_host.VolatileHost(character_name="Suplex Backbreaker")
        self.assertEqual(host.character_name, "Suplex Backbreaker")

    def test_the_dispatcher_hands_its_own_copy_to_the_volatile_host(self):
        dispatcher = botlab_host.TaskDispatcher(character_name="Suplex Backbreaker")
        self.assertEqual(dispatcher.character_name, "Suplex Backbreaker")
        self.assertEqual(dispatcher.volatile.character_name, "Suplex Backbreaker")

    def test_the_two_copies_cannot_disagree(self):
        # A future refactor that reintroduces two independent attributes
        # would still pass the two tests above individually if it happened to
        # pass the same string to both constructors -- so assert the
        # relationship itself, from a single dispatcher construction, rather
        # than two values that merely look equal by coincidence.
        for name in [None, "Gal Bistot"]:
            dispatcher = botlab_host.TaskDispatcher(character_name=name)
            self.assertIs(dispatcher.character_name, dispatcher.volatile.character_name)


class AListGameClientProcessesRequestNeverRaises(unittest.TestCase):
    """The failure mode was never a visible exception -- it was this request
    always raising, silently, inside code whose caller converts any exception
    into a response that looks like a *different*, more familiar failure."""

    def _list_game_client_processes_request(self):
        return json.dumps({"ListGameClientProcessesRequest": {}})

    def test_handle_request_does_not_raise_with_a_character_name_set(self):
        host = botlab_host.VolatileHost(character_name="Suplex Backbreaker")
        with mock.patch.object(botlab_host, "find_eve_processes", return_value=[]) as fake:
            response_json = host.handle_request(self._list_game_client_processes_request())
        fake.assert_called_once_with("Suplex Backbreaker")
        self.assertEqual(json.loads(response_json), {"ListGameClientProcessesResponse": []})

    def test_handle_request_does_not_raise_with_no_character_name(self):
        host = botlab_host.VolatileHost()
        with mock.patch.object(botlab_host, "find_eve_processes", return_value=[]) as fake:
            host.handle_request(self._list_game_client_processes_request())
        fake.assert_called_once_with(None)


class TheFullRoundTripNeverDegradesToProcessNotFound(unittest.TestCase):
    """Exercised through `TaskDispatcher.run_task`, the same path the Elm
    framework's setup state machine drives on every tick while it has no
    volatile process yet. Before the fix this returned
    `{"Err": {"ProcessNotFound": True}}` on every single call -- the response
    that makes the framework tear down and recreate the volatile process,
    which is what turned one raised exception into a loop with no end."""

    def test_a_client_list_request_round_trips_as_ok(self):
        dispatcher = botlab_host.TaskDispatcher(character_name="Suplex Backbreaker")
        task = {
            "RequestToVolatileProcess": {
                "RequestNotRequiringInputFocus": {
                    "request": json.dumps({"ListGameClientProcessesRequest": {}}),
                }
            }
        }
        with mock.patch.object(botlab_host, "find_eve_processes", return_value=[]):
            result = dispatcher.run_task(task)

        self.assertIn("Ok", result["RequestToVolatileProcessResponse"])
        self.assertNotIn("Err", result["RequestToVolatileProcessResponse"])

    def test_reverting_the_fix_reproduces_the_reported_symptom(self):
        # Simulates the exact bug this file guards against -- the attribute
        # present on the dispatcher and absent from the volatile host it
        # delegates to -- to pin what that failure actually looks like from
        # the framework's side, rather than only asserting it is gone.
        dispatcher = botlab_host.TaskDispatcher(character_name="Suplex Backbreaker")
        del dispatcher.volatile.character_name
        task = {
            "RequestToVolatileProcess": {
                "RequestNotRequiringInputFocus": {
                    "request": json.dumps({"ListGameClientProcessesRequest": {}}),
                }
            }
        }

        result = dispatcher.run_task(task)

        self.assertEqual(
            result,
            {"RequestToVolatileProcessResponse": {"Err": {"ProcessNotFound": True}}})


if __name__ == "__main__":
    unittest.main()
