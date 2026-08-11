"""The ESI refresh token's home on Windows: the Credential Manager.

``esi_waypoint.py`` keeps two things out of the repo and out of shell history --
the OAuth refresh token and the application's client id -- by putting them in the
macOS Keychain through the ``security`` CLI. This is the same store on Windows,
and it is deliberately the *OS credential store* rather than a file next to the
code, because the property that matters is not obscurity but that the secret is
encrypted at rest under the user's own login and is visible to, and revocable
by, the person whose account it is (``control /name Microsoft.CredentialManager``,
or ``cmdkey /list``).

Two things about the refresh token make this worth doing properly rather than
dropping it in a dotfile. It does not expire the way the ten-minute ``ssoToken``
does, and it authorises writes to a live EVE account's autopilot. CLAUDE.md
already keeps a standing rule about never printing the client's command line for
the same class of reason; a token in a file in a repo directory is the same
hazard with a longer half-life.

``CredReadW``/``CredWriteW`` rather than raw DPAPI: DPAPI would encrypt a blob
just as well, but it would leave us choosing a file path, an ACL and a rotation
story, and it would put the secret somewhere no standard tool can enumerate. The
Credential Manager is what the Keychain is on this platform.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

_advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

CRED_TYPE_GENERIC = 1
# LOCAL_MACHINE rather than SESSION: the token has to survive a logoff, or the
# bot needs re-authorising every time the machine is rebooted. Not ENTERPRISE,
# which would roam it to other machines on a domain -- this is one account on
# one machine and it should stay there.
CRED_PERSIST_LOCAL_MACHINE = 2

ERROR_NOT_FOUND = 1168


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_advapi32.CredReadW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
    ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
]
_advapi32.CredReadW.restype = wintypes.BOOL
_advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
_advapi32.CredWriteW.restype = wintypes.BOOL
_advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
_advapi32.CredDeleteW.restype = wintypes.BOOL
_advapi32.CredFree.argtypes = [ctypes.c_void_p]
_advapi32.CredFree.restype = None


class CredentialError(RuntimeError):
    pass


def _target(service: str) -> str:
    """The Credential Manager key for a Keychain service name.

    Namespaced so these cannot collide with a credential some other program
    stored, and so a person reading `cmdkey /list` can tell whose they are.
    The Keychain's separate *account* field has no direct equivalent -- the
    Credential Manager is already per-user -- so it is carried as `UserName`,
    which is informational there rather than part of the key. That matches how
    the macOS side actually behaves, where the account is the logged-in user.
    """
    return f"eve-bot-windows-host:{service}"


def store(service: str, account: str, secret: str) -> None:
    """Write a secret, replacing any previous one for the same service."""
    # UTF-16LE is the convention for CredentialBlob on Windows, and is what the
    # built-in tooling assumes when it shows a blob at all. Written and read
    # here consistently; `load` falls back to UTF-8 so a credential put there by
    # something else is not silently returned as mojibake.
    blob = secret.encode("utf-16-le")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    cred = CREDENTIALW(
        Flags=0,
        Type=CRED_TYPE_GENERIC,
        TargetName=_target(service),
        Comment="EVE bot Windows host (see tools/windows-host/credential_store.py)",
        LastWritten=wintypes.FILETIME(),
        CredentialBlobSize=len(blob),
        CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)),
        Persist=CRED_PERSIST_LOCAL_MACHINE,
        AttributeCount=0,
        Attributes=None,
        TargetAlias=None,
        UserName=account or None,
    )
    if not _advapi32.CredWriteW(ctypes.byref(cred), 0):
        err = ctypes.get_last_error()
        raise CredentialError(
            f"CredWrite for {service!r} failed with Win32 error {err} "
            f"({ctypes.FormatError(err).strip()})"
        )


def load(service: str, account: str = "") -> Optional[str]:
    """The stored secret, or ``None`` if there is not one.

    ``None`` rather than an exception for the absent case, because "no
    credential yet" is the ordinary state before the one-time setup and the
    caller's job is to say so helpfully rather than to crash.
    """
    pointer = ctypes.POINTER(CREDENTIALW)()
    if not _advapi32.CredReadW(_target(service), CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        err = ctypes.get_last_error()
        if err == ERROR_NOT_FOUND:
            return None
        raise CredentialError(
            f"CredRead for {service!r} failed with Win32 error {err} "
            f"({ctypes.FormatError(err).strip()})"
        )
    try:
        cred = pointer.contents
        size = cred.CredentialBlobSize
        if not size:
            return None
        raw = ctypes.string_at(cred.CredentialBlob, size)
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "strict")
    finally:
        _advapi32.CredFree(pointer)


def delete(service: str) -> bool:
    """Remove a stored secret. True if one was there."""
    if _advapi32.CredDeleteW(_target(service), CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND:
        return False
    err = ctypes.get_last_error()
    raise CredentialError(f"CredDelete for {service!r} failed with Win32 error {err}")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="inspect the host's credential store (never prints a secret)"
    )
    parser.add_argument("action", choices=["status", "delete"])
    parser.add_argument("--service", default=None)
    args = parser.parse_args()

    services = [args.service] if args.service else ["eve-esi-refresh", "eve-esi-client-id"]
    for service in services:
        if args.action == "delete":
            print(f"{service}: {'deleted' if delete(service) else 'was not stored'}")
            continue
        try:
            value = load(service)
        except CredentialError as exc:
            print(f"{service}: error -- {exc}")
            continue
        # Deliberately reports presence and length only. Nothing here echoes a
        # token: this runs in a terminal whose scrollback ends up in bug reports.
        print(f"{service}: {'stored (%d chars)' % len(value) if value else 'not stored'}")
    sys.exit(0)
