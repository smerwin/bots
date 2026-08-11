#!/usr/bin/env python3
"""Set the EVE client's autopilot destination through ESI, the official API.

The bot has never been able to originate a destination. Every route it has set
came from the mission tracker's own travel buttons, so once a mission ends there
is nothing left to click -- which is how a remote hand-in strands it in space
with an agent that will only say "please drop by". `POST /ui/autopilot/waypoint/`
is the missing half: it tells the logged-in client to set a destination by id,
and the bot's existing travel logic flies it from there.

Usage:
    python3 esi_waypoint.py auth                      # one-time, opens a browser
    python3 esi_waypoint.py auth --manual             # same, but log in on another device
    python3 esi_waypoint.py resolve "Jita IV - Moon 4 - Caldari Navy Assembly Plant"
    python3 esi_waypoint.py set --name "Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal"
    python3 esi_waypoint.py set --id 60008494 --keep-other-waypoints

Setup, once:
    * developers.eveonline.com -> Create New Application
    * type "Authentication & API Access", scope `esi-ui.write_waypoint.v1`
    * callback exactly `http://localhost:8635/callback`
    * python3 esi_waypoint.py client-id <the client id>   (kept in the Keychain)
      or export ESI_CLIENT_ID=<the client id> to override it for one run

Also importable. `botlab_host.py` calls `set_destination` in-process for the
`SetAutopilotDestinationRequest` volatile-process request, so every function
below that can fail raises `EsiError` rather than calling `sys.exit`, and the
CLI at the foot is the only thing that turns one into an exit code. A caller
inside the host loop gets a value it can branch on; nothing has to parse this
file's stdout.

Secrets. The PKCE flow means no client secret exists at all, so the only
sensitive artifact is the refresh token, and it goes straight into the macOS
Keychain -- never a file in the repo, never an argument, never printed. Nothing
here echoes a token, deliberately: this runs in a terminal whose scrollback ends
up in bug reports, and the host's own log is tee'd to a file.

The game client must be running and logged in. This endpoint drives that
client's UI; it does not move the ship by itself.
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

LOGIN_HOST = "https://login.eveonline.com"
ESI_HOST = "https://esi.evetech.net/latest"
SCOPES = "esi-ui.write_waypoint.v1"
CALLBACK_PORT = 8635
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"

KEYCHAIN_SERVICE = "eve-esi-refresh"
KEYCHAIN_ACCOUNT = os.environ.get("USER") or os.environ.get("USERNAME") or "eve"

# Windows keeps these in the Credential Manager instead, which is that
# platform's Keychain: encrypted at rest under the user's own login, and
# enumerable and revocable by them (`cmdkey /list`). Same four operations behind
# the same four function names, so nothing below this point knows which store it
# is talking to -- see tools/windows-host/credential_store.py.
IS_WINDOWS = sys.platform == "win32"
_cred_store = None
if IS_WINDOWS:
    _WINDOWS_HOST_DIR = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "windows-host"
    )
    if _WINDOWS_HOST_DIR not in sys.path:
        sys.path.insert(0, _WINDOWS_HOST_DIR)
    import credential_store as _cred_store  # noqa: E402

# The client id lives beside the refresh token rather than in the repo or a
# shell profile. It is not a secret -- PKCE issues no client secret, and this
# one is useless without the login it authorises -- but it does identify a
# specific developer application on a specific account, which is not something
# to commit to a fork or leave in shell history.
KEYCHAIN_CLIENT_ID_SERVICE = "eve-esi-client-id"

# CCP asks that every caller identify itself so they can get in touch before
# blocking a misbehaving client rather than after.
USER_AGENT = "macos-host-eve-bot (personal, non-commercial)"

# The budget for a whole operation, not for one request. A per-request timeout
# bounds nothing useful here: resolving an NPC station that `/universe/ids/`
# misses costs one round trip per station in the system, so a dozen requests
# that each answer just inside their own timeout still add up past any tick the
# host has to spare. Fifteen seconds is about one memory read's worth. Running
# out is a failure the caller branches on, not something to wait through.
DEFAULT_BUDGET_SECONDS = 15.0

# The ceiling on any single request, applied under whatever the budget has left.
PER_REQUEST_TIMEOUT_SECONDS = 30.0


class EsiError(Exception):
    """A failure whose message is safe to log.

    Every message here is built from a status code, a name, or our own wording.
    In particular the token endpoint's error body is never included: that is the
    one response that can quote a request's own parameters back, and a request
    to it carries the refresh token. Callers print these straight into a log
    that is tee'd to a file and pasted into transcripts.
    """


class Deadline:
    """A wall-clock budget shared across the several requests one call makes."""

    def __init__(self, budget_seconds=DEFAULT_BUDGET_SECONDS):
        self.expires_at = time.monotonic() + budget_seconds

    def remaining(self):
        return self.expires_at - time.monotonic()

    def timeout_for(self, what):
        left = self.remaining()
        if left <= 0:
            raise EsiError(f"ESI took too long ({what})")
        return min(left, PER_REQUEST_TIMEOUT_SECONDS)


# Ids never change, so both of these live for the life of the process. Speed is
# not the only point: the enumerate-a-system fallback is the path most likely to
# exhaust the budget, and memoising each station it looks at means an attempt
# that ran out of time gets further next time instead of starting over.
_ID_BY_NAME = {}      # lowercased name -> (id, kind)
_UNIVERSE_GET = {}    # GET path -> decoded payload


def client_id():
    """The application's client id: the environment first, then the Keychain.

    The environment still wins, so a one-off run against a different application
    needs no state change. Falling back to the Keychain is what stops the id
    being something to remember and re-export on every invocation.
    """
    value = os.environ.get("ESI_CLIENT_ID")
    if not value:
        value = keychain_load_client_id()
    if not value:
        raise EsiError("no client id -- set ESI_CLIENT_ID, or store one once "
                       "with `esi_waypoint.py client-id <id>`. See the setup "
                       "notes at the top of this file.")
    return value.strip()


def keychain_store_client_id(value):
    if IS_WINDOWS:
        return _cred_store.store(KEYCHAIN_CLIENT_ID_SERVICE, KEYCHAIN_ACCOUNT, value)
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_CLIENT_ID_SERVICE, "-w", value],
        check=True,
    )


def keychain_load_client_id():
    if IS_WINDOWS:
        return _cred_store.load(KEYCHAIN_CLIENT_ID_SERVICE, KEYCHAIN_ACCOUNT)
    result = subprocess.run(
        ["security", "find-generic-password",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_CLIENT_ID_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


# ---------------------------------------------------------------------------
# Keychain: the refresh token's only home
# ---------------------------------------------------------------------------
def keychain_store(token):
    if IS_WINDOWS:
        return _cred_store.store(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, token)
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w", token],
        check=True,
    )


def keychain_load():
    if IS_WINDOWS:
        return _cred_store.load(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
    result = subprocess.run(
        ["security", "find-generic-password",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def post_form(url, fields, deadline=None):
    """POST a form and return the decoded body.

    Failures raise `EsiError` carrying the status code alone. This is the call
    that carries the refresh token, so its error body -- which quotes the
    request back on at least some CCP errors -- never reaches the message.
    """
    deadline = deadline or Deadline()
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Host", urllib.parse.urlparse(url).netloc)
    request.add_header("User-Agent", USER_AGENT)
    try:
        with urllib.request.urlopen(request, timeout=deadline.timeout_for(url)) as response:
            return json.loads(response.read())
    # `from None` drops the chained original. Not tidiness: the suppressed
    # exception keeps the frame that called urlopen alive, and that frame's
    # locals hold the encoded form body -- the refresh token among them. Nothing
    # here prints locals today, and nothing should have to stay true for this to
    # be safe.
    except urllib.error.HTTPError as error:
        raise EsiError(f"login.eveonline.com refused the token request ({error.code})") from None
    except urllib.error.URLError as error:
        raise EsiError(f"could not reach login.eveonline.com ({error.reason})") from None
    except OSError as error:
        raise EsiError(f"could not reach login.eveonline.com ({error})") from None


def esi(method, path, token=None, params=None, body=None, deadline=None):
    """Call ESI and return `(status, payload)`.

    An HTTP error is a status like any other -- callers here read the code to
    tell a scope problem from a missing client. Only a request that never got an
    answer raises, since there is no status to report and no point retrying
    inside one bounded call.
    """
    deadline = deadline or Deadline()
    url = f"{ESI_HOST}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", USER_AGENT)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=deadline.timeout_for(path)) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw.decode("utf-8", "replace")
        return error.code, detail
    except urllib.error.URLError as error:
        raise EsiError(f"could not reach ESI ({error.reason})")
    except OSError as error:
        raise EsiError(f"could not reach ESI ({error})")


# ---------------------------------------------------------------------------
# OAuth 2.0 with PKCE
# ---------------------------------------------------------------------------
def pkce_pair():
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    captured = {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        _CallbackHandler.captured = dict(urllib.parse.parse_qsl(parsed.query))
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Authorized. You can close this tab and return to the terminal.")

    def log_message(self, *_):
        pass  # the default handler writes the full query string, code included


def authorize_manual():
    """Authorize when the browser is on another device.

    `authorize` opens a browser here and catches the redirect on this machine's
    localhost. Log in on a phone instead and that redirect resolves to the
    *phone's* localhost, where nothing is listening, so the final hop just fails
    to load -- but the URL in the address bar still carries the code. This prints
    the authorize URL, takes that failed URL back, and finishes the exchange
    here.

    The code_verifier never leaves this process, so the half that proves the
    request is ours stays local no matter which device did the logging in. The
    code itself is single-use and short-lived.
    """
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode({
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = f"{LOGIN_HOST}/v2/oauth/authorize/?{query}"

    print("Open this on the other device and log in:\n")
    print(url)
    print("\nThe page it lands on will fail to load -- that is expected, the "
          "redirect points at this machine. Copy its full address and paste it "
          "here.\n")
    pasted = input("callback URL: ").strip()

    captured = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(pasted).query))
    if captured.get("state") != state:
        sys.exit("state mismatch -- refusing the response. Start again.")
    if "code" not in captured:
        sys.exit(f"no authorization code in that URL: {sorted(captured)}")

    tokens = post_form(f"{LOGIN_HOST}/v2/oauth/token", {
        "grant_type": "authorization_code",
        "code": captured["code"],
        "client_id": client_id(),
        "code_verifier": verifier,
    })
    keychain_store(tokens["refresh_token"])
    print(f"authorized; refresh token stored in the Keychain as "
          f"{KEYCHAIN_SERVICE!r} (not printed).")
    return tokens["access_token"]


def authorize():
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(16)
    query = urllib.parse.urlencode({
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id(),
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    url = f"{LOGIN_HOST}/v2/oauth/authorize/?{query}"

    server = http.server.HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"opening the EVE login page; if it does not open, visit:\n  {url}\n")
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()

    captured = _CallbackHandler.captured
    if not captured:
        sys.exit("timed out waiting for the callback -- nothing arrived on port "
                 f"{CALLBACK_PORT}.")
    if captured.get("state") != state:
        sys.exit("state mismatch on the callback -- refusing the response.")
    if "code" not in captured:
        sys.exit(f"no authorization code in the callback: {captured}")

    tokens = post_form(f"{LOGIN_HOST}/v2/oauth/token", {
        "grant_type": "authorization_code",
        "code": captured["code"],
        "client_id": client_id(),
        "code_verifier": verifier,
    })
    keychain_store(tokens["refresh_token"])
    print(f"authorized; refresh token stored in the Keychain as "
          f"{KEYCHAIN_SERVICE!r} (not printed).")
    return tokens["access_token"]


def access_token(deadline=None):
    """A fresh access token, from the stored refresh token.

    Access tokens last 20 minutes, so there is no point caching one between
    invocations -- refreshing every run is simpler and cheap. The refresh token
    is read out of the Keychain here and handed straight to `post_form`; it is
    never returned, stored in an attribute or put in a message.
    """
    refresh = keychain_load()
    if not refresh:
        raise EsiError("no stored refresh token -- run 'esi_waypoint.py auth' first")
    try:
        tokens = post_form(f"{LOGIN_HOST}/v2/oauth/token", {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id(),
        }, deadline=deadline)
    except EsiError as error:
        raise EsiError(f"{error} -- re-run 'auth'. A revoked or rotated token "
                       "cannot be repaired here.")
    # CCP rotates refresh tokens: the old one stops working once used.
    if tokens.get("refresh_token"):
        keychain_store(tokens["refresh_token"])
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def _universe_get(path, deadline):
    """A memoised GET of static universe data. `None` if ESI would not answer."""
    if path in _UNIVERSE_GET:
        return _UNIVERSE_GET[path]
    status, payload = esi("GET", path, deadline=deadline)
    if status != 200:
        return None
    _UNIVERSE_GET[path] = payload
    return payload


def resolve_name(name, deadline=None):
    """The id of a station, structure or system, by name. Raises `EsiError`.

    Returns `(id, kind)` where kind is one of the `/universe/ids/` bucket names.
    """
    deadline = deadline or Deadline()
    cached = _ID_BY_NAME.get(name.lower())
    if cached:
        return cached

    status, payload = esi("POST", "/universe/ids/", body=[name], deadline=deadline)
    if status != 200:
        raise EsiError(f"name lookup failed ({status}): {payload}")
    for key in ("stations", "structures", "systems"):
        for entry in (payload or {}).get(key) or []:
            if entry.get("name", "").lower() == name.lower():
                return _remember(name, entry["id"], key)
    for key in ("stations", "structures", "systems"):
        entries = (payload or {}).get(key) or []
        if entries:
            return _remember(name, entries[0]["id"], key)

    # /universe/ids/ does not index every NPC station: the agent's own
    # "Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal" comes back empty
    # from it while resolving perfectly through the system's station list.
    # NPC station names begin with their system's name, so that first token is
    # enough to find the system and enumerate what is docked in it.
    found = _resolve_via_system(name, deadline)
    if found:
        return _remember(name, found[0], found[1])

    raise EsiError(f"nothing named {name!r} was found. Structures in "
                   "player-owned space often need the character to have docked "
                   "there before ESI will resolve them.")


def _remember(name, found_id, kind):
    _ID_BY_NAME[name.lower()] = (found_id, kind)
    return found_id, kind


def _resolve_via_system(name, deadline):
    system_name = name.split()[0] if name.split() else ""
    if not system_name:
        return None
    status, payload = esi("POST", "/universe/ids/", body=[system_name], deadline=deadline)
    if status != 200:
        return None
    systems = (payload or {}).get("systems") or []
    if not systems:
        return None

    system = _universe_get(f"/universe/systems/{systems[0]['id']}/", deadline)
    if system is None:
        return None
    for station_id in system.get("stations") or []:
        station = _universe_get(f"/universe/stations/{station_id}/", deadline)
        if station and station.get("name", "").lower() == name.lower():
            return station_id, "stations"
    return None


def set_waypoint(destination_id, clear_other=True, add_to_beginning=False, deadline=None):
    """Point the logged-in client's autopilot at `destination_id`.

    Returns `destination_id` on success and raises `EsiError` on every failure,
    including the ones ESI reports as a perfectly ordinary HTTP response. There
    is no return value that means "probably fine": a caller that does not handle
    the failure gets an exception, not a route it never set.
    """
    deadline = deadline or Deadline()
    status, payload = esi(
        "POST", "/ui/autopilot/waypoint/",
        token=access_token(deadline=deadline),
        params={
            "destination_id": destination_id,
            "clear_other_waypoints": str(clear_other).lower(),
            "add_to_beginning": str(add_to_beginning).lower(),
        },
        deadline=deadline,
    )
    if status in (200, 204):
        return destination_id
    if status == 403:
        raise EsiError(f"refused ({status}): {payload} -- a 403 here is usually "
                       "the scope: the token needs esi-ui.write_waypoint.v1. "
                       "Re-run 'auth' if the app's scopes changed.")
    raise EsiError(f"failed ({status}): {payload} -- this endpoint drives the "
                   "logged-in client's UI, so it fails if no client is running "
                   "for this character.")


_token_character = None


def token_character(deadline=None):
    """The character this refresh token authorises, as `(name, id)`.

    Memoised for the life of the process: a token's character cannot change, and
    `authorize` is what replaces the token.

    Nothing token-shaped is returned or logged -- the access token goes straight
    to the verify endpoint and only the character comes back out.
    """
    global _token_character
    if _token_character is None:
        deadline = deadline or Deadline()
        request = urllib.request.Request(f"{LOGIN_HOST}/oauth/verify")
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Authorization",
                           "Bearer " + access_token(deadline=deadline))
        try:
            with urllib.request.urlopen(
                    request, timeout=deadline.timeout_for("verify")) as response:
                payload = json.loads(response.read())
        except (urllib.error.URLError, ValueError) as failure:
            raise EsiError("could not read the token's character: %s" % failure)
        _token_character = (payload.get("CharacterName"), payload.get("CharacterID"))
    return _token_character


def character_from_window_title(title):
    """The character a client window title names, or `None`.

    The client titles its window `EVE - <character>`, so the name is whatever
    follows the first separator. Anything else answers `None`, which callers
    read as "cannot check" rather than as a mismatch -- see `set_destination`.
    """
    if not title:
        return None
    for separator in (" - ", " – "):
        if separator in title:
            candidate = title.split(separator, 1)[1].strip()
            return candidate or None
    return None


def set_destination(name=None, destination_id=None, clear_other=True,
                    add_to_beginning=False, budget_seconds=DEFAULT_BUDGET_SECONDS,
                    expected_character=None):
    """Resolve a name if needed and set the destination, under one budget.

    The single entry point for callers outside this file. Returns the id that
    was set; raises `EsiError` with a loggable reason for every other outcome,
    expiry included.

    **`expected_character` is the guard, and it exists because this endpoint
    fails silently in the worst available direction.** `/ui/autopilot/waypoint/`
    acts on whichever character the *token* belongs to, not on the client the
    bot is flying, so a token authorised for the wrong character reports success
    and sets a route the bot will never see.

    That is not hypothetical. saxrat run 14 was parked for its whole session:
    the host logged `# ESI: destination 'Hamse' set (30003547)` while the token
    belonged to `Gal Bistot` and the bot flew `Joan d'Arkonor`, whose route panel
    read `No Destination` throughout. The bot then spent 3,932 readings latched
    on `ROUTE SETTING GIVEN UP -- this host does not set destinations`, which
    was the one conclusion the evidence beside it ruled out.

    **`None` means "cannot check" and does not block.** A caller that cannot
    name the client's character -- an unreadable window title, a host that does
    not track one -- gets exactly today's behaviour, because a hard refusal on an
    unreadable title would break a working setup to guard against an unproven
    one. A *mismatch*, which is positive evidence, refuses.
    """
    if (name is None) == (destination_id is None):
        raise EsiError("set_destination needs exactly one of name, destination_id")
    deadline = Deadline(budget_seconds)

    if expected_character:
        authorised, _ = token_character(deadline=deadline)
        if authorised and authorised.strip().lower() != expected_character.strip().lower():
            raise EsiError(
                "the stored ESI token authorises %r and the client is flying %r, "
                "so setting a destination here would route the wrong character "
                "and this one would never see it. Re-run 'esi_waypoint.py auth' "
                "and pick %r at the character step."
                % (authorised, expected_character, expected_character))

    if destination_id is None:
        destination_id, _ = resolve_name(name, deadline=deadline)
    return set_waypoint(destination_id, clear_other=clear_other,
                        add_to_beginning=add_to_beginning, deadline=deadline)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    id_cmd = sub.add_parser("client-id", help="store the application's client id in the Keychain")
    id_cmd.add_argument("value", help="the client id from developers.eveonline.com")

    auth_cmd = sub.add_parser("auth", help="one-time browser authorization (PKCE)")
    auth_cmd.add_argument("--manual", action="store_true",
                          help="print the URL and take the pasted redirect back, for logging "
                               "in on another device (the callback points at this machine's "
                               "localhost, which a phone cannot reach)")

    resolve = sub.add_parser("resolve", help="look up a station/system id by name")
    resolve.add_argument("name")

    setter = sub.add_parser("set", help="set the client's autopilot destination")
    target = setter.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", type=int, help="destination id")
    target.add_argument("--name", help="station or system name, resolved first")
    setter.add_argument("--keep-other-waypoints", action="store_true",
                        help="add to the route instead of replacing it")
    setter.add_argument("--add-to-beginning", action="store_true")
    setter.add_argument("--budget", type=float, default=DEFAULT_BUDGET_SECONDS,
                        help="seconds for the whole resolve-and-set, not per request "
                             f"(default {DEFAULT_BUDGET_SECONDS:g})")

    args = parser.parse_args()

    if args.command == "client-id":
        keychain_store_client_id(args.value.strip())
        print(f"client id stored in the Keychain as {KEYCHAIN_CLIENT_ID_SERVICE!r}")
        return 0

    if args.command == "auth":
        if args.manual:
            authorize_manual()
            return 0
        authorize()
        return 0

    if args.command == "resolve":
        found_id, kind = resolve_name(args.name)
        print(f"{found_id}  ({kind[:-1]})")
        return 0

    deadline = Deadline(args.budget)
    destination = args.id
    if destination is None:
        destination, kind = resolve_name(args.name, deadline=deadline)
        print(f"# {args.name!r} -> {destination} ({kind[:-1]})")
    set_waypoint(destination,
                 clear_other=not args.keep_other_waypoints,
                 add_to_beginning=args.add_to_beginning,
                 deadline=deadline)
    print(f"destination set to {destination}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EsiError as failure:
        sys.exit(str(failure))
