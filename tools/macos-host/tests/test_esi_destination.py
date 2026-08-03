"""Tests for SetAutopilotDestinationRequest and esi_waypoint's importable half.

Three things this request has to get right, and each has a case here.

It must **tell success from failure**, in shapes a decision can branch on. A
destination that silently was not set, followed by travel logic finding no
route, is this repo's signature failure -- so `Completed` and `Failed` are
different shapes, and the unexpected-exception case is included because
`run_task`'s own `except` answers `ProcessNotFound`, which BotFramework reads
as "the volatile process is gone" and reacts to by tearing it down.

It must be **bounded**, because `handle_request` runs inside the host's single
request/response loop. The budget covers the whole resolve-and-set rather than
one request, so the expiry cases run the deadline down and check that what comes
back is a failure rather than a wait.

It must **never leak the refresh token**. Those cases plant a sentinel token in
the Keychain stub and have CCP quote it back in an error body -- the one
response that realistically could -- then assert the sentinel appears in
neither the message, the response, nor stderr. The host's log is tee'd to a file
and pasted into transcripts, which is the same reason this project never prints
the client's command line.

Nothing here reaches the network, the Keychain or a game client: `urlopen`,
`keychain_load` and `set_destination` are replaced per test.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import contextlib
import io
import json
import os
import sys
import unittest
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import esi_waypoint  # noqa: E402
import botlab_host  # noqa: E402

# What a leak would look like. Nothing in a real message is shaped like this, so
# a substring search for it cannot pass by accident.
SENTINEL = "REFRESH-TOKEN-THAT-MUST-NOT-BE-LOGGED"


def dispatch(body):
    """One SetAutopilotDestinationRequest through the real dispatcher."""
    request = json.dumps({"SetAutopilotDestinationRequest": body})
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        response = botlab_host.VolatileHost().handle_request(request)
    return json.loads(response)["SetAutopilotDestinationResult"], captured.getvalue()


@contextlib.contextmanager
def patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


class DispatchTest(unittest.TestCase):
    def test_success_reports_the_id_that_was_set(self):
        with patched(esi_waypoint, "set_destination", lambda **kwargs: 60008950):
            result, _ = dispatch({"name": "Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal"})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})

    def test_the_request_carries_its_arguments_through(self):
        seen = {}

        def record(**kwargs):
            seen.update(kwargs)
            return 60008494

        with patched(esi_waypoint, "set_destination", record):
            dispatch({"destinationId": 60008494, "clearOtherWaypoints": False,
                      "addToBeginning": True, "budgetSeconds": 3})
        self.assertEqual(seen, {"name": None, "destination_id": 60008494,
                                "clear_other": False, "add_to_beginning": True,
                                "budget_seconds": 3})

    def test_clearing_the_route_is_the_default(self):
        seen = {}

        def record(**kwargs):
            seen.update(kwargs)
            return 1

        with patched(esi_waypoint, "set_destination", record):
            dispatch({"name": "Jita"})
        self.assertTrue(seen["clear_other"])
        self.assertFalse(seen["add_to_beginning"])
        self.assertEqual(seen["budget_seconds"], esi_waypoint.DEFAULT_BUDGET_SECONDS)

    def test_failure_is_a_different_shape_carrying_the_reason(self):
        def refuse(**_):
            raise esi_waypoint.EsiError("refused (403): scope missing")

        with patched(esi_waypoint, "set_destination", refuse):
            result, log = dispatch({"name": "Jita"})
        self.assertNotIn("Completed", result)
        self.assertIn("403", result["Failed"])
        self.assertIn("not set", log)

    def test_an_unexpected_exception_is_a_failure_not_a_lost_process(self):
        """Anything escaping here becomes ProcessNotFound, which recycles the
        volatile process and re-runs root discovery -- see the docstring."""
        def explode(**_):
            raise ValueError("something nobody anticipated")

        with patched(esi_waypoint, "set_destination", explode):
            result, _ = dispatch({"name": "Jita"})
        self.assertNotIn("Completed", result)
        self.assertIn("something nobody anticipated", result["Failed"])

    def test_a_request_naming_nothing_fails_rather_than_setting_something(self):
        result, _ = dispatch({})
        self.assertNotIn("Completed", result)


class BudgetTest(unittest.TestCase):
    def test_an_exhausted_budget_raises_instead_of_issuing_a_request(self):
        deadline = esi_waypoint.Deadline(0)
        with self.assertRaises(esi_waypoint.EsiError):
            deadline.timeout_for("/universe/ids/")

    def test_a_request_never_gets_longer_than_the_budget_has_left(self):
        deadline = esi_waypoint.Deadline(0.5)
        self.assertLessEqual(deadline.timeout_for("/universe/ids/"), 0.5)

    def test_a_long_budget_is_still_capped_per_request(self):
        deadline = esi_waypoint.Deadline(600)
        self.assertEqual(deadline.timeout_for("/universe/ids/"),
                         esi_waypoint.PER_REQUEST_TIMEOUT_SECONDS)

    def test_expiry_reaches_the_bot_as_a_failure(self):
        with patched(esi_waypoint, "_ID_BY_NAME", {}):
            result, _ = dispatch({"name": "Jita", "budgetSeconds": -1})
        self.assertNotIn("Completed", result)
        self.assertIn("too long", result["Failed"])


class ResolutionCacheTest(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def counting_esi(self, method, path, **kwargs):
        self.calls.append(path)
        return 200, {"systems": [{"id": 30000142, "name": "Jita"}]}

    def test_a_name_is_resolved_once_per_session(self):
        with patched(esi_waypoint, "_ID_BY_NAME", {}), \
                patched(esi_waypoint, "esi", self.counting_esi):
            first = esi_waypoint.resolve_name("Jita")
            second = esi_waypoint.resolve_name("Jita")
        self.assertEqual(first, (30000142, "systems"))
        self.assertEqual(second, first)
        self.assertEqual(len(self.calls), 1)

    def test_the_cache_is_case_insensitive_like_the_lookup(self):
        with patched(esi_waypoint, "_ID_BY_NAME", {}), \
                patched(esi_waypoint, "esi", self.counting_esi):
            esi_waypoint.resolve_name("Jita")
            esi_waypoint.resolve_name("JITA")
        self.assertEqual(len(self.calls), 1)

    def test_a_name_that_resolves_to_nothing_is_not_cached_as_an_answer(self):
        def empty(method, path, **kwargs):
            self.calls.append(path)
            return 200, {}

        with patched(esi_waypoint, "_ID_BY_NAME", {}), \
                patched(esi_waypoint, "esi", empty):
            with self.assertRaises(esi_waypoint.EsiError):
                esi_waypoint.resolve_name("Nowhere At All")
            with self.assertRaises(esi_waypoint.EsiError):
                esi_waypoint.resolve_name("Nowhere At All")
        self.assertGreater(len(self.calls), 2)


class TokenSecrecyTest(unittest.TestCase):
    """CCP quoting the request back is the realistic leak; these pin it shut."""

    def quoting_urlopen(self, request, timeout=None):
        body = json.dumps({"error": "invalid_grant",
                           "error_description": f"bad token {SENTINEL}"}).encode()
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    def test_a_token_endpoint_error_body_never_reaches_the_message(self):
        with patched(esi_waypoint, "keychain_load", lambda: SENTINEL), \
                patched(esi_waypoint, "client_id", lambda: "client"), \
                patched(esi_waypoint.urllib.request, "urlopen", self.quoting_urlopen):
            with self.assertRaises(esi_waypoint.EsiError) as raised:
                esi_waypoint.access_token()
        self.assertNotIn(SENTINEL, str(raised.exception))
        self.assertIn("400", str(raised.exception))

    def test_a_failed_set_leaks_the_token_into_neither_response_nor_log(self):
        with patched(esi_waypoint, "_ID_BY_NAME", {}), \
                patched(esi_waypoint, "keychain_load", lambda: SENTINEL), \
                patched(esi_waypoint, "client_id", lambda: "client"), \
                patched(esi_waypoint.urllib.request, "urlopen", self.quoting_urlopen):
            result, log = dispatch({"destinationId": 60008950})
        self.assertNotIn("Completed", result)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL, log)

    def test_a_successful_set_leaks_the_token_into_neither_response_nor_log(self):
        def succeed(request, timeout=None):
            if "oauth/token" in request.full_url:
                return _Body(json.dumps({"access_token": "access"}).encode())
            return _Body(b"", status=204)

        with patched(esi_waypoint, "keychain_load", lambda: SENTINEL), \
                patched(esi_waypoint, "client_id", lambda: "client"), \
                patched(esi_waypoint.urllib.request, "urlopen", succeed):
            result, log = dispatch({"destinationId": 60008950})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL, log)


class _Body:
    """The little of urlopen's context-manager result that esi() touches."""

    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


if __name__ == "__main__":
    unittest.main()
