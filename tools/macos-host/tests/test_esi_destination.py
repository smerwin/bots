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
the credential-store stub and have CCP quote it back in an error body -- the one
response that realistically could -- then assert the sentinel appears in
neither the message, the response, nor stderr. The host's log is tee'd to a file
and pasted into transcripts, which is the same reason this project never prints
the client's command line. Every path added by the per-character store gets the
same treatment, because a listing command and a refusal that names characters
are both new places a token could be printed by accident.

And since one token became one per character, it must **route the character the
client is flying** and refuse rather than guess where it cannot tell. Those
cases run whole `set`s against a fake CCP that hands out a different access
token per character, and assert on *which* token reached
`/ui/autopilot/waypoint/` -- not merely that something was set, since setting
the wrong character's route is exactly the failure that looks like success.

Nothing here reaches the network, the Keychain or a game client: `urlopen`,
the three credential-store functions and `set_destination` are replaced per
test.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import contextlib
import io
import json
import os
import sys
import unittest
import urllib.error
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS_HOST_DIR = os.path.dirname(HERE)
sys.path.insert(0, MACOS_HOST_DIR)
sys.path.insert(0, os.path.join(MACOS_HOST_DIR, "botlab_host"))
import esi_waypoint  # noqa: E402
import botlab_host  # noqa: E402

# What a leak would look like. Nothing in a real message is shaped like this, so
# a substring search for it cannot pass by accident.
SENTINEL = "REFRESH-TOKEN-THAT-MUST-NOT-BE-LOGGED"

# Kept from before `fake_store` replaces it, for the one case that wants the
# real lookup rather than the stub.
REAL_CLIENT_ID = esi_waypoint.client_id


def dispatch(body, window_title=None):
    """One SetAutopilotDestinationRequest through the real dispatcher."""
    request = json.dumps({"SetAutopilotDestinationRequest": body})
    captured = io.StringIO()
    volatile = botlab_host.VolatileHost()
    volatile.game_window_title = window_title
    with contextlib.redirect_stderr(captured):
        response = volatile.handle_request(request)
    return json.loads(response)["SetAutopilotDestinationResult"], captured.getvalue()


@contextlib.contextmanager
def patched(module, name, value):
    original = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, original)


@contextlib.contextmanager
def fake_store(entries=None):
    """The credential store as a dict, and every per-process cache reset.

    This is the seam the real thing sits behind on both platforms -- `security`
    on macOS and `CredReadW`/`CredWriteW` on Windows -- so a case that goes
    through it exercises the same keying decisions the live store would.
    """
    data = dict(entries or {})

    def write(service, value):
        data[service] = value

    def delete(service):
        return data.pop(service, None) is not None

    with patched(esi_waypoint, "credential_store_write", write), \
            patched(esi_waypoint, "credential_store_read", data.get), \
            patched(esi_waypoint, "credential_store_delete", delete), \
            patched(esi_waypoint, "_token_character", {}), \
            patched(esi_waypoint, "_legacy_migration_checked", False), \
            patched(esi_waypoint, "client_id", lambda: "client"), \
            patched(esi_waypoint, "_ID_BY_NAME", {}):
        yield data


def seed_character(data, name, token, character_id):
    """Put one character's token and index row into a fake store."""
    data[esi_waypoint.character_service(name)] = token
    index = json.loads(data.get(esi_waypoint.KEYCHAIN_CHARACTER_INDEX_SERVICE) or "[]")
    index = [row for row in index
             if esi_waypoint.character_key(row["name"]) != esi_waypoint.character_key(name)]
    index.append({"name": name, "id": character_id})
    data[esi_waypoint.KEYCHAIN_CHARACTER_INDEX_SERVICE] = json.dumps(index)


class FakeCcp:
    """Enough of login.eveonline.com and ESI to run a whole `set`.

    Rotation is modelled the way CCP does it -- the refresh token handed in
    stops working the moment it is exchanged -- because the migration's whole
    ordering argument is about surviving an interruption around that.
    """

    def __init__(self, characters):
        self.characters = dict(characters)   # refresh token -> (name, id)
        self.access = {}                     # access token -> (name, id)
        self.exchanges = 0
        self.verifies = 0
        self.waypoints = []                  # [((name, id), destination_id)]

    def _identity_for(self, request):
        return self.access[request.headers["Authorization"].split(" ", 1)[1]]

    def urlopen(self, request, timeout=None):
        url = request.full_url
        if "oauth/token" in url:
            fields = urllib.parse.parse_qs(request.data.decode())
            refresh = fields["refresh_token"][0]
            if refresh not in self.characters:
                raise urllib.error.HTTPError(
                    url, 400, "Bad Request", {},
                    io.BytesIO(json.dumps({
                        "error": "invalid_grant",
                        "error_description": f"bad token {refresh}"}).encode()))
            identity = self.characters.pop(refresh)
            self.exchanges += 1
            rotated = f"{refresh}/rotated-{self.exchanges}"
            access = f"access-{self.exchanges}"
            self.characters[rotated] = identity
            self.access[access] = identity
            return _Body(json.dumps({"access_token": access,
                                     "refresh_token": rotated}).encode())
        if "oauth/verify" in url:
            self.verifies += 1
            name, character_id = self._identity_for(request)
            return _Body(json.dumps({"CharacterName": name,
                                     "CharacterID": character_id}).encode())
        if "/ui/autopilot/waypoint/" in url:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            self.waypoints.append(
                (self._identity_for(request), int(query["destination_id"][0])))
            return _Body(b"", status=204)
        raise AssertionError(f"the fake was asked for an unexpected URL: {url}")

    @property
    def routed(self):
        """The names, in order, whose autopilot was actually pointed at something."""
        return [identity[0] for identity, _ in self.waypoints]


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
                                "budget_seconds": 3, "expected_character": None})

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
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            with patched(esi_waypoint.urllib.request, "urlopen", self.quoting_urlopen):
                result, log = dispatch({"destinationId": 60008950})
        self.assertNotIn("Completed", result)
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL, log)

    def test_a_successful_set_leaks_the_token_into_neither_response_nor_log(self):
        def succeed(request, timeout=None):
            if "oauth/token" in request.full_url:
                return _Body(json.dumps({"access_token": "access"}).encode())
            return _Body(b"", status=204)

        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            with patched(esi_waypoint.urllib.request, "urlopen", succeed):
                result, log = dispatch({"destinationId": 60008950})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertNotIn(SENTINEL, json.dumps(result))
        self.assertNotIn(SENTINEL, log)

    def test_the_refusal_that_names_the_characters_names_no_token(self):
        """The ambiguity message lists who is authorised, so it is a new place a
        token could be printed by accident."""
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            seed_character(data, "Joan d'Arkonor", SENTINEL + "-two", 2119999999)
            with self.assertRaises(esi_waypoint.EsiError) as raised:
                esi_waypoint.character_to_route(None)
        self.assertNotIn(SENTINEL, str(raised.exception))
        self.assertIn("Gal Bistot", str(raised.exception))
        self.assertIn("Joan d'Arkonor", str(raised.exception))

    def test_the_refusal_for_an_unauthorised_character_names_no_token(self):
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            with self.assertRaises(esi_waypoint.EsiError) as raised:
                esi_waypoint.character_to_route("Joan d'Arkonor")
        self.assertNotIn(SENTINEL, str(raised.exception))
        self.assertIn("Joan d'Arkonor", str(raised.exception))

    def test_the_listing_prints_names_and_ids_and_no_token(self):
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            seed_character(data, "Joan d'Arkonor", SENTINEL + "-two", 2119999999)
            printed = run_cli("characters")
        self.assertNotIn(SENTINEL, printed)
        self.assertIn("Gal Bistot", printed)
        self.assertIn("2112625428", printed)
        self.assertIn("2119999999", printed)

    def test_the_stored_character_description_never_carries_a_token(self):
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            described = esi_waypoint.describe_stored_characters()
        self.assertNotIn(SENTINEL, described)
        self.assertIn("Gal Bistot", described)

    def test_the_migration_announcement_never_carries_a_token(self):
        ccp = FakeCcp({SENTINEL: ("Gal Bistot", 2112625428)})
        with fake_store({esi_waypoint.KEYCHAIN_SERVICE: SENTINEL}), \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                esi_waypoint.ensure_legacy_token_migrated()
        self.assertIn("Gal Bistot", captured.getvalue())
        self.assertNotIn(SENTINEL, captured.getvalue())

    def test_a_forget_never_echoes_what_it_dropped(self):
        with fake_store() as data:
            seed_character(data, "Gal Bistot", SENTINEL, 2112625428)
            printed = run_cli("forget", "Gal Bistot")
        self.assertNotIn(SENTINEL, printed)
        self.assertIn("Gal Bistot", printed)


def run_cli(*argv):
    """`main()` with these arguments, returning everything it printed."""
    captured = io.StringIO()
    with patched(sys, "argv", ["esi_waypoint.py", *argv]), \
            contextlib.redirect_stdout(captured), \
            contextlib.redirect_stderr(captured):
        esi_waypoint.main()
    return captured.getvalue()


class CharacterSelectionTest(unittest.TestCase):
    """The four cases in `esi_waypoint`'s own header, each asked of a whole set.

    What is asserted is *whose* autopilot was pointed somewhere, because a route
    set on the wrong character is a success everywhere except in the game.
    """

    def run_set(self, data, window_title, characters):
        ccp = FakeCcp(characters)
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            result, log = dispatch({"destinationId": 60008950}, window_title=window_title)
        return ccp, result, log

    def test_the_character_the_client_is_flying_is_the_one_routed(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp, result, _ = self.run_set(
            data, "EVE - Joan d'Arkonor",
            {"token-gal": ("Gal Bistot", 2112625428),
             "token-joan": ("Joan d'Arkonor", 2119999999)})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertEqual(ccp.routed, ["Joan d'Arkonor"])

    def test_the_other_character_is_routed_when_the_client_names_it(self):
        """The control for the case above: same store, same fake, other title."""
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp, _, _ = self.run_set(
            data, "EVE - Gal Bistot",
            {"token-gal": ("Gal Bistot", 2112625428),
             "token-joan": ("Joan d'Arkonor", 2119999999)})
        self.assertEqual(ccp.routed, ["Gal Bistot"])

    def test_a_character_with_no_token_refuses_and_says_which(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp, result, log = self.run_set(
            data, "EVE - Joan d'Arkonor", {"token-gal": ("Gal Bistot", 2112625428)})
        self.assertNotIn("Completed", result)
        self.assertIn("Joan d'Arkonor", result["Failed"])
        self.assertIn("auth", result["Failed"])
        self.assertEqual(ccp.routed, [], "nothing may be routed on a refusal")
        self.assertIn("not set", log)

    def test_an_unreadable_title_with_one_token_still_works(self):
        """Every single-character install predates this change and must not break."""
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp, result, _ = self.run_set(
            data, None, {"token-gal": ("Gal Bistot", 2112625428)})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertEqual(ccp.routed, ["Gal Bistot"])

    def test_an_unreadable_title_with_two_tokens_refuses_rather_than_guessing(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp, result, _ = self.run_set(
            data, None,
            {"token-gal": ("Gal Bistot", 2112625428),
             "token-joan": ("Joan d'Arkonor", 2119999999)})
        self.assertNotIn("Completed", result)
        self.assertIn("Gal Bistot", result["Failed"])
        self.assertIn("Joan d'Arkonor", result["Failed"])
        self.assertEqual(ccp.routed, [],
                         "guessing here is run 14 again -- nothing may be routed")

    def test_an_unreadable_title_with_no_token_says_to_authorise(self):
        ccp, result, _ = self.run_set({}, None, {})
        self.assertNotIn("Completed", result)
        self.assertIn("auth", result["Failed"])
        self.assertEqual(ccp.routed, [])

    def test_the_character_override_wins_over_the_stored_set(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428),
                       "token-joan": ("Joan d'Arkonor", 2119999999)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            esi_waypoint.set_destination(destination_id=60008950,
                                         character="Joan d'Arkonor")
        self.assertEqual(ccp.routed, ["Joan d'Arkonor"])

    def test_the_name_is_matched_trimmed_and_case_insensitively(self):
        """The same normalisation the mismatch guard always compared with, so a
        title that used to match cannot now fail to find its own token."""
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp, result, _ = self.run_set(
            data, "EVE -   gal bISTOT  ", {"token-gal": ("Gal Bistot", 2112625428)})
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertEqual(ccp.routed, ["Gal Bistot"])

    def test_picking_a_token_by_name_costs_no_verify(self):
        """A token filed under a character is one CCP has already named. The old
        guard spent a round trip on every process; this spends none."""
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp, _, _ = self.run_set(
            data, "EVE - Gal Bistot", {"token-gal": ("Gal Bistot", 2112625428)})
        self.assertEqual(ccp.verifies, 0)
        self.assertEqual(ccp.exchanges, 1, "one refresh, which is what it always was")


class RotationTest(unittest.TestCase):
    """CCP rotates refresh tokens, so where the replacement lands matters."""

    def test_a_rotation_is_written_back_under_the_same_character(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428),
                       "token-joan": ("Joan d'Arkonor", 2119999999)})
        with fake_store(data) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            esi_waypoint.set_destination(destination_id=1, character="Gal Bistot")
            gal = store[esi_waypoint.character_service("Gal Bistot")]
            joan = store[esi_waypoint.character_service("Joan d'Arkonor")]
        self.assertNotEqual(gal, "token-gal", "the rotation has to be stored")
        self.assertEqual(joan, "token-joan",
                         "the other character's token must not be touched")
        self.assertEqual(ccp.characters.get(gal), ("Gal Bistot", 2112625428))

    def test_the_rotated_token_is_the_one_used_next_time(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            esi_waypoint.set_destination(destination_id=1, character="Gal Bistot")
            esi_waypoint.set_destination(destination_id=2, character="Gal Bistot")
        self.assertEqual(ccp.routed, ["Gal Bistot", "Gal Bistot"])


class TokenCharacterCacheTest(unittest.TestCase):
    """The memo is keyed, because one pair for several characters is the
    wrong-character answer arriving through the function whose job is to say
    who a token belongs to."""

    def test_two_characters_get_two_answers(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428),
                       "token-joan": ("Joan d'Arkonor", 2119999999)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            first = esi_waypoint.token_character("Gal Bistot")
            second = esi_waypoint.token_character("Joan d'Arkonor")
        self.assertEqual(first, ("Gal Bistot", 2112625428))
        self.assertEqual(second, ("Joan d'Arkonor", 2119999999))

    def test_the_same_character_is_asked_once(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            esi_waypoint.token_character("Gal Bistot")
            esi_waypoint.token_character("gal bistot")
        self.assertEqual(ccp.verifies, 1)


class MigrationTest(unittest.TestCase):
    """An install that predates this store keeps working with no operator action."""

    def test_a_legacy_token_is_filed_under_its_character_and_then_used(self):
        ccp = FakeCcp({"legacy-token": ("Gal Bistot", 2112625428)})
        with fake_store({esi_waypoint.KEYCHAIN_SERVICE: "legacy-token"}) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            result, log = dispatch({"destinationId": 60008950},
                                   window_title="EVE - Gal Bistot")
            self.assertNotIn(esi_waypoint.KEYCHAIN_SERVICE, store,
                             "the legacy entry goes only once it is re-stored")
            filed = store[esi_waypoint.character_service("Gal Bistot")]
            index = json.loads(store[esi_waypoint.KEYCHAIN_CHARACTER_INDEX_SERVICE])
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertEqual(ccp.routed, ["Gal Bistot"])
        self.assertEqual(ccp.characters.get(filed), ("Gal Bistot", 2112625428))
        self.assertEqual(index, [{"name": "Gal Bistot", "id": 2112625428}])
        self.assertIn("Gal Bistot", log)

    def test_an_interruption_between_the_copy_and_the_delete_completes_next_run(self):
        """Killed after the character's entry is written and before the legacy
        one is dropped, the next run finds a live token in the legacy slot,
        rotates it, and overwrites the character's entry with the newer value."""
        ccp = FakeCcp({"legacy-token": ("Gal Bistot", 2112625428)})
        half_done = {esi_waypoint.KEYCHAIN_SERVICE: "legacy-token"}
        seed_character(half_done, "Gal Bistot", "legacy-token", 2112625428)
        with fake_store(half_done) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen), \
                contextlib.redirect_stderr(io.StringIO()):
            esi_waypoint.ensure_legacy_token_migrated()
            filed = store[esi_waypoint.character_service("Gal Bistot")]
            self.assertNotIn(esi_waypoint.KEYCHAIN_SERVICE, store)
        self.assertNotEqual(filed, "legacy-token")
        self.assertEqual(ccp.characters.get(filed), ("Gal Bistot", 2112625428),
                         "the entry has to hold the token that still works")

    def killed_at(self, service):
        """A store that dies the moment one particular entry is written.

        Which is what makes the migration's *ordering* checkable rather than
        merely readable: the exchange has already killed the old token value by
        the time any of these writes happen, so a step done in the wrong order
        is a token that exists nowhere.
        """
        real_write = esi_waypoint.credential_store_write

        def write(where, value):
            if where == service:
                raise RuntimeError("the process died here")
            real_write(where, value)

        return patched(esi_waypoint, "credential_store_write", write)

    def assert_a_live_token_survived(self, store, ccp):
        self.assertTrue(
            [value for value in store.values() if value in ccp.characters],
            "an interrupted migration must leave a token that still works "
            "somewhere -- nothing may be dropped before it is re-stored")

    def test_a_kill_while_writing_the_character_entry_loses_no_token(self):
        ccp = FakeCcp({"legacy-token": ("Gal Bistot", 2112625428)})
        with fake_store({esi_waypoint.KEYCHAIN_SERVICE: "legacy-token"}) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen), \
                self.killed_at(esi_waypoint.character_service("Gal Bistot")):
            with self.assertRaises(RuntimeError):
                esi_waypoint.ensure_legacy_token_migrated()
            self.assert_a_live_token_survived(store, ccp)

    def test_a_kill_while_writing_the_index_loses_no_token(self):
        ccp = FakeCcp({"legacy-token": ("Gal Bistot", 2112625428)})
        with fake_store({esi_waypoint.KEYCHAIN_SERVICE: "legacy-token"}) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen), \
                self.killed_at(esi_waypoint.KEYCHAIN_CHARACTER_INDEX_SERVICE):
            with self.assertRaises(RuntimeError):
                esi_waypoint.ensure_legacy_token_migrated()
            self.assert_a_live_token_survived(store, ccp)

    def test_a_migration_that_fails_deletes_nothing(self):
        ccp = FakeCcp({})   # the legacy token has been revoked
        with fake_store({esi_waypoint.KEYCHAIN_SERVICE: "revoked"}) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                self.assertIsNone(esi_waypoint.ensure_legacy_token_migrated())
            self.assertEqual(store[esi_waypoint.KEYCHAIN_SERVICE], "revoked")
        self.assertIn("nothing was deleted", captured.getvalue())

    def test_a_failed_migration_does_not_stop_a_working_character(self):
        data = {esi_waypoint.KEYCHAIN_SERVICE: "revoked"}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            result, _ = dispatch({"destinationId": 60008950},
                                 window_title="EVE - Gal Bistot")
        self.assertEqual(result, {"Completed": {"destinationId": 60008950}})
        self.assertEqual(ccp.routed, ["Gal Bistot"])

    def test_an_absent_legacy_entry_costs_one_read_and_no_network(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428)})
        with fake_store(data), patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            self.assertIsNone(esi_waypoint.ensure_legacy_token_migrated())
        self.assertEqual(ccp.exchanges, 0)
        self.assertEqual(ccp.verifies, 0)


class CharacterIndexTest(unittest.TestCase):
    def test_an_index_row_whose_token_is_gone_is_not_a_stored_character(self):
        """Otherwise a stale row makes the ambiguity rule believe in a choice
        that is not there, and refuse a machine that has exactly one token."""
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        del data[esi_waypoint.character_service("Joan d'Arkonor")]
        with fake_store(data):
            known = esi_waypoint.stored_characters()
            chosen = esi_waypoint.character_to_route(None)
        self.assertEqual([entry["name"] for entry in known], ["Gal Bistot"])
        self.assertEqual(chosen, "Gal Bistot")

    def test_a_token_whose_index_row_is_gone_is_still_usable_by_name(self):
        """The index decides what can be listed, never what can be used."""
        with fake_store({esi_waypoint.character_service("Gal Bistot"): "token-gal"}):
            self.assertEqual(esi_waypoint.character_to_route("Gal Bistot"), "Gal Bistot")

    def test_a_corrupt_index_is_read_as_empty_rather_than_raising(self):
        with fake_store({esi_waypoint.KEYCHAIN_CHARACTER_INDEX_SERVICE: "{not json"}):
            self.assertEqual(esi_waypoint.stored_characters(), [])

    def test_authorising_a_second_character_leaves_the_first_alone(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({})
        ccp.access["fresh-access"] = ("Joan d'Arkonor", 2119999999)
        with fake_store(data) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            with contextlib.redirect_stdout(io.StringIO()):
                esi_waypoint.finish_authorization(
                    {"access_token": "fresh-access", "refresh_token": "token-joan"})
            self.assertEqual(store[esi_waypoint.character_service("Gal Bistot")],
                             "token-gal")
            self.assertEqual(store[esi_waypoint.character_service("Joan d'Arkonor")],
                             "token-joan")
            self.assertEqual([entry["name"] for entry in esi_waypoint.stored_characters()],
                             ["Gal Bistot", "Joan d'Arkonor"])

    def test_authorising_the_same_character_again_replaces_its_token(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        ccp = FakeCcp({})
        ccp.access["fresh-access"] = ("Gal Bistot", 2112625428)
        with fake_store(data) as store, \
                patched(esi_waypoint.urllib.request, "urlopen", ccp.urlopen):
            with contextlib.redirect_stdout(io.StringIO()):
                esi_waypoint.finish_authorization(
                    {"access_token": "fresh-access", "refresh_token": "token-gal-2"})
            self.assertEqual(store[esi_waypoint.character_service("Gal Bistot")],
                             "token-gal-2")
            self.assertEqual(len(esi_waypoint.stored_characters()), 1)

    def test_forget_drops_the_token_and_the_row(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        with fake_store(data) as store:
            self.assertTrue(esi_waypoint.forget_character("Gal Bistot"))
            self.assertNotIn(esi_waypoint.character_service("Gal Bistot"), store)
            self.assertEqual([entry["name"] for entry in esi_waypoint.stored_characters()],
                             ["Joan d'Arkonor"])
            self.assertFalse(esi_waypoint.forget_character("Gal Bistot"))

    def test_forgetting_the_second_of_two_ends_the_ambiguity(self):
        data = {}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        with fake_store(data):
            with self.assertRaises(esi_waypoint.EsiError):
                esi_waypoint.character_to_route(None)
            esi_waypoint.forget_character("Joan d'Arkonor")
            self.assertEqual(esi_waypoint.character_to_route(None), "Gal Bistot")


class ClientIdIsNotPerCharacterTest(unittest.TestCase):
    """One application registration for every character, and PKCE means it is
    not a secret -- so keying it per character would be wrong as well as
    useless, and would make `auth` need a second setup step per character."""

    def test_the_client_id_entry_is_not_keyed_by_character(self):
        self.assertNotIn(esi_waypoint.KEYCHAIN_CHARACTER_SERVICE_PREFIX,
                         esi_waypoint.KEYCHAIN_CLIENT_ID_SERVICE)

    def test_both_characters_read_the_one_stored_client_id(self):
        data = {esi_waypoint.KEYCHAIN_CLIENT_ID_SERVICE: "the-one-application"}
        seed_character(data, "Gal Bistot", "token-gal", 2112625428)
        seed_character(data, "Joan d'Arkonor", "token-joan", 2119999999)
        ccp = FakeCcp({"token-gal": ("Gal Bistot", 2112625428),
                       "token-joan": ("Joan d'Arkonor", 2119999999)})
        asked = []

        def watching_urlopen(request, timeout=None):
            if "oauth/token" in request.full_url:
                asked.append(urllib.parse.parse_qs(request.data.decode())["client_id"][0])
            return ccp.urlopen(request, timeout)

        with fake_store(data), \
                patched(esi_waypoint, "client_id", REAL_CLIENT_ID), \
                patched(esi_waypoint.os, "environ", {}), \
                patched(esi_waypoint.urllib.request, "urlopen", watching_urlopen):
            esi_waypoint.set_destination(destination_id=1, character="Gal Bistot")
            esi_waypoint.set_destination(destination_id=2, character="Joan d'Arkonor")
        self.assertEqual(asked, ["the-one-application", "the-one-application"])


class ServiceKeyingTest(unittest.TestCase):
    """The character goes in the *service*, not the account: the Windows
    Credential Manager keys on the target alone, so two characters sharing a
    service would share one entry there while looking fine on macOS."""

    def test_two_characters_are_two_entries(self):
        self.assertNotEqual(esi_waypoint.character_service("Gal Bistot"),
                            esi_waypoint.character_service("Joan d'Arkonor"))

    def test_a_character_entry_is_not_the_legacy_entry(self):
        self.assertNotEqual(esi_waypoint.character_service("Gal Bistot"),
                            esi_waypoint.KEYCHAIN_SERVICE)

    def test_the_key_is_the_name_normalised_the_way_the_guard_compared(self):
        self.assertEqual(esi_waypoint.character_service("  GAL bistot "),
                         esi_waypoint.character_service("Gal Bistot"))

    def test_an_empty_name_names_no_character(self):
        """`character_from_window_title` answers `None` rather than an empty
        string, but a caller that passes one must not match every entry."""
        self.assertIsNone(esi_waypoint.refresh_token_for("   "))


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
