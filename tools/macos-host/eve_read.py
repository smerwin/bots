#!/usr/bin/env python3
"""Read the live EVE client's UI state, quickly, from outside the bot.

Finding the UI root costs a full process dump and 20-40 seconds. Never pay that
twice: `botlab_host.py` writes what it found to a small cache, and this reuses
it, which is the difference between a two-second answer and a minute of waiting.

    {"pid": 22510, "root": 5201217576, "metatype": ..., "str_type": ...}

Those addresses are per-process-launch, so the cache is only meaningful while
that exact client is still running. Two checks before trusting it, both cheap:

  * the pid is alive and is the EVE client -- not merely alive, since pids get
    reused and reading a random process's memory at those offsets yields
    plausible-looking nonsense rather than an error.
  * the root still answers, by reading one node and looking for the
    _displayWidth that only UIRoot carries.

Skipping the second is the tempting mistake. Every ad-hoc probe in the session
this came from trusted the cache blindly; that happened to be safe because the
client never restarted, and would have silently produced garbage if it had.

Usage as a CLI:

    python3 eve_read.py overview     # rows, which are rendered, name/type/distance
    python3 eve_read.py targets      # target bar, and which entry is active
    python3 eve_read.py modules      # ship module slots and ramp_active
    python3 eve_read.py combat       # the floating combat feed
    python3 eve_read.py window       # the game window id, for screencapture -l
    python3 eve_read.py pid          # the client's pid, without printing its
                                     # command line -- see client_pid()

or as a library:

    import eve_read
    tree = eve_read.read_tree()
    for node, x, y in eve_read.walk(tree): ...
"""
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TREE_WALKER = os.path.join(HERE, "tree_walker", "tree_walker")
WINDOW_PROBE = os.path.join(HERE, "window_probe", "window_probe")
CACHE = os.path.join(tempfile.gettempdir(), "botlab-host-ui-root-cache.json")

# EVE's own colour and font markup, which is in most user-visible strings.
MARKUP = re.compile(r"<[^>]*>")


class NotAvailable(Exception):
    """The cache cannot be trusted, with a reason worth printing."""


def _pid_is_eve(pid):
    return pid == client_pid()


def ui_root():
    """The cached root addresses, once verified against the running client."""
    try:
        entry = json.load(open(CACHE))
    except (OSError, ValueError) as exc:
        raise NotAvailable(f"no usable UI-root cache at {CACHE} ({exc}). "
                           "Run a bot once to populate it.") from exc

    if not _pid_is_eve(entry["pid"]):
        raise NotAvailable(
            f"cache names pid {entry['pid']}, which is not a running EVE client. "
            "The addresses are per-launch, so they are stale -- run a bot to refresh them.")

    probe = read_tree(max_depth=1, max_nodes=1, entry=entry, _verify=False)
    if not (probe.get("dictEntriesOfInterest") or {}).get("_displayWidth"):
        raise NotAvailable(
            f"pid {entry['pid']} is an EVE client but the cached root does not read "
            "as UIRoot -- the client has relaunched into the same pid. Run a bot to refresh.")
    return entry


def read_tree(max_depth=20, max_nodes=20000, entry=None, _verify=True):
    """One UI-tree read. ~2s for a full ~4,000-node tree, ~35ms to attach."""
    entry = entry or (ui_root() if _verify else json.load(open(CACHE)))
    proc = subprocess.Popen([TREE_WALKER, str(entry["pid"])],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    try:
        if b"ready" not in proc.stderr.readline():
            raise NotAvailable("tree_walker did not start -- is SIP debugging still disabled?")
        proc.stdin.write(struct.pack("<QQQII", entry["root"], entry["metatype"],
                                     entry["str_type"], max_depth, max_nodes))
        proc.stdin.flush()
        (length,) = struct.unpack("<Q", proc.stdout.read(8))
        buf = bytearray()
        while len(buf) < length:
            chunk = proc.stdout.read(length - len(buf))
            if not chunk:
                raise NotAvailable("tree_walker stopped mid-response")
            buf += chunk
        return json.loads(buf.decode("utf-8", "replace"))
    finally:
        proc.kill()


def walk(node, x=0, y=0):
    """Every node with its absolute position. Positions in the tree are relative
    to the parent, so they only mean anything accumulated."""
    entries = node.get("dictEntriesOfInterest") or {}
    ax = x + (entries.get("_displayX") or 0)
    ay = y + (entries.get("_displayY") or 0)
    yield node, ax, ay
    for child in node.get("children") or []:
        yield from walk(child, ax, ay)


def texts_of(node):
    """Every visible string under a node, markup stripped. Several keys carry
    text depending on the widget, and a single label is often only part of a
    sentence -- see the combat feed, where a message is split across four."""
    out = []
    for child, _, _ in walk(node):
        entries = child.get("dictEntriesOfInterest") or {}
        for key in ("_setText", "_text", "_hint"):
            value = entries.get(key)
            if isinstance(value, str) and value.strip():
                out.append(MARKUP.sub("", value).strip())
    return out


def of_type(tree, type_name):
    return [(n, x, y) for n, x, y in walk(tree)
            if n.get("pythonObjectTypeName") == type_name]


def game_window_id(pid=None):
    """The client's largest window. A fullscreen game also has a small same-width
    menu-bar strip that a naive pick lands on, giving a wrong scale and bogus
    click targets."""
    pid = pid or ui_root()["pid"]
    out = subprocess.run([WINDOW_PROBE, "--all"], capture_output=True, text=True).stdout
    best = None
    for line in out.splitlines():
        m = re.search(r"window=(\d+).*owner_pid=(\d+).*w=([\d.]+) h=([\d.]+)", line)
        if m and int(m.group(2)) == pid:
            area = float(m.group(3)) * float(m.group(4))
            if best is None or area > best[1]:
                best = (int(m.group(1)), area)
    return best[0] if best else None


def client_pid():
    """The running client's pid, or None.

    Ask for this rather than reaching for `ps`. The launcher starts the client
    with the account's `/ssoToken=` and `/refreshToken=` on its command line, so
    anything that prints a command line -- `ps aux | grep EVE`, `pgrep -fl`,
    `ps -o command=` -- puts live credentials wherever that output goes: a
    terminal, a run log, a transcript pasted into a chat. `lsappinfo` answers
    from the bundle id and never reports an argument vector; this is the same
    lookup `botlab_host.find_eve_processes` uses.
    """
    out = subprocess.run(["lsappinfo", "list"], capture_output=True, text=True).stdout
    for m in re.finditer(r'bundleID="([^"]+)"[^\x00]*?pid = (\d+)', out):
        if m.group(1) == "com.ccpgames.eveonline":
            return int(m.group(2))
    return None


def _cli(what):
    if what == "pid":
        pid = client_pid()
        print(pid if pid is not None else "no EVE client running")
        return 0 if pid is not None else 1

    if what == "window":
        print(game_window_id())
        return 0

    tree = read_tree()
    if what == "overview":
        rows = of_type(tree, "OverviewScrollEntry")
        shown = [r for r in rows
                 if (r[0].get("dictEntriesOfInterest") or {}).get("_display") is not False]
        print(f"{len(rows)} rows, {len(shown)} rendered")
        for node, _, _ in rows:
            disp = (node.get("dictEntriesOfInterest") or {}).get("_display")
            print(f"  rendered={str(disp is not False):<5} {texts_of(node)}")
    elif what == "targets":
        entries = of_type(tree, "TargetInBar")
        print(f"{len(entries)} locked")
        for node, _, _ in entries:
            active = any(c.get("pythonObjectTypeName") in
                         ("ActiveTargetIndicator", "ActiveTargetOnBracket")
                         for c, _, _ in walk(node))
            print(f"  active={str(active):<5} {texts_of(node)}")
    elif what == "modules":
        for node, _, ay in of_type(tree, "ShipSlot"):
            buttons = [c for c, _, _ in walk(node)
                       if c.get("pythonObjectTypeName") == "ModuleButton"]
            if not buttons:
                continue
            d = buttons[0].get("dictEntriesOfInterest") or {}
            name = (node.get("dictEntriesOfInterest") or {}).get("_name")
            # ramp_active is absent entirely until a module has run: the widget
            # holding it is created when cycling starts. Absent means off.
            print(f"  {str(name):<22} y={ay:<6} ramp_active={d.get('ramp_active')} "
                  f"online={d.get('online')}")
    elif what == "combat":
        feeds = of_type(tree, "CombatMessage")
        if not feeds:
            print("no combat messages on screen")
        for node, _, _ in feeds:
            for child in node.get("children") or []:
                line = " ".join(texts_of(child))
                if line.strip():
                    print(" ", " ".join(line.split()))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(_cli(sys.argv[1] if len(sys.argv) > 1 else "help"))
    except NotAvailable as exc:
        print(f"eve_read: {exc}", file=sys.stderr)
        sys.exit(1)
