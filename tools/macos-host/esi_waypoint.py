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

Secrets. The PKCE flow means no client secret exists at all, so the only
sensitive artifact is the refresh token, and it goes straight into the macOS
Keychain -- never a file in the repo, never an argument, never printed. Nothing
here echoes a token, deliberately: this runs in a terminal whose scrollback ends
up in bug reports.

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
KEYCHAIN_ACCOUNT = os.environ.get("USER", "eve")

# The client id lives beside the refresh token rather than in the repo or a
# shell profile. It is not a secret -- PKCE issues no client secret, and this
# one is useless without the login it authorises -- but it does identify a
# specific developer application on a specific account, which is not something
# to commit to a fork or leave in shell history.
KEYCHAIN_CLIENT_ID_SERVICE = "eve-esi-client-id"

# CCP asks that every caller identify itself so they can get in touch before
# blocking a misbehaving client rather than after.
USER_AGENT = "macos-host-eve-bot (personal, non-commercial)"


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
        sys.exit("no client id -- set ESI_CLIENT_ID, or store one once with "
                 "`esi_waypoint.py client-id <id>`. See the setup notes at the "
                 "top of this file.")
    return value.strip()


def keychain_store_client_id(value):
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_CLIENT_ID_SERVICE, "-w", value],
        check=True,
    )


def keychain_load_client_id():
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
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w", token],
        check=True,
    )


def keychain_load():
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
def post_form(url, fields):
    body = urllib.parse.urlencode(fields).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    request.add_header("Host", urllib.parse.urlparse(url).netloc)
    request.add_header("User-Agent", USER_AGENT)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def esi(method, path, token=None, params=None, body=None):
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
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            detail = json.loads(raw)
        except Exception:
            detail = raw.decode("utf-8", "replace")
        return error.code, detail


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


def access_token():
    """A fresh access token, from the stored refresh token.

    Access tokens last 20 minutes, so there is no point caching one between
    invocations -- refreshing every run is simpler and cheap.
    """
    refresh = keychain_load()
    if not refresh:
        sys.exit("no stored refresh token -- run 'esi_waypoint.py auth' first.")
    try:
        tokens = post_form(f"{LOGIN_HOST}/v2/oauth/token", {
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id(),
        })
    except urllib.error.HTTPError as error:
        sys.exit(f"refresh failed ({error.code}) -- re-run 'auth'. "
                 "A revoked or rotated token cannot be repaired here.")
    # CCP rotates refresh tokens: the old one stops working once used.
    if tokens.get("refresh_token"):
        keychain_store(tokens["refresh_token"])
    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def resolve_name(name):
    status, payload = esi("POST", "/universe/ids/", body=[name])
    if status != 200:
        sys.exit(f"name lookup failed ({status}): {payload}")
    for key in ("stations", "structures", "systems"):
        for entry in (payload or {}).get(key) or []:
            if entry.get("name", "").lower() == name.lower():
                return entry["id"], key
    for key in ("stations", "structures", "systems"):
        entries = (payload or {}).get(key) or []
        if entries:
            return entries[0]["id"], key

    # /universe/ids/ does not index every NPC station: the agent's own
    # "Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal" comes back empty
    # from it while resolving perfectly through the system's station list.
    # NPC station names begin with their system's name, so that first token is
    # enough to find the system and enumerate what is docked in it.
    found = _resolve_via_system(name)
    if found:
        return found

    sys.exit(f"nothing named {name!r} was found. Structures in player-owned "
             "space often need the character to have docked there before ESI "
             "will resolve them.")


def _resolve_via_system(name):
    system_name = name.split()[0] if name.split() else ""
    if not system_name:
        return None
    status, payload = esi("POST", "/universe/ids/", body=[system_name])
    if status != 200:
        return None
    systems = (payload or {}).get("systems") or []
    if not systems:
        return None

    status, system = esi("GET", f"/universe/systems/{systems[0]['id']}/")
    if status != 200:
        return None
    for station_id in system.get("stations") or []:
        status, station = esi("GET", f"/universe/stations/{station_id}/")
        if status == 200 and station.get("name", "").lower() == name.lower():
            return station_id, "stations"
    return None


def set_waypoint(destination_id, clear_other=True, add_to_beginning=False):
    status, payload = esi(
        "POST", "/ui/autopilot/waypoint/",
        token=access_token(),
        params={
            "destination_id": destination_id,
            "clear_other_waypoints": str(clear_other).lower(),
            "add_to_beginning": str(add_to_beginning).lower(),
        },
    )
    if status in (200, 204):
        print(f"destination set to {destination_id}")
        return 0
    if status == 403:
        print(f"refused ({status}): {payload}\n"
              "  A 403 here is usually the scope: the token needs "
              "esi-ui.write_waypoint.v1. Re-run 'auth' if the app's scopes changed.",
              file=sys.stderr)
        return 1
    print(f"failed ({status}): {payload}\n"
          "  This endpoint drives the logged-in client's UI -- it fails if no "
          "client is running for this character.", file=sys.stderr)
    return 1


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

    destination = args.id
    if destination is None:
        destination, kind = resolve_name(args.name)
        print(f"# {args.name!r} -> {destination} ({kind[:-1]})")
    return set_waypoint(destination,
                        clear_other=not args.keep_other_waypoints,
                        add_to_beginning=args.add_to_beginning)


if __name__ == "__main__":
    sys.exit(main())
