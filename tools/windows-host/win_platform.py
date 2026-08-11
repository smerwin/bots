"""Everything ``botlab_host.py`` reaches the operating system through, on Windows.

Issue #176 step 4: "Wire ``botlab_host.py``'s platform-bound call sites behind a
small dispatch, the minimum that lets one file serve both."  This is the Windows
side of that dispatch.  The host imports it only on Windows, and every function
here has a macOS counterpart in ``botlab_host.py`` that is left exactly as it is.

**The seams were chosen to be as few and as narrow as possible**, because the
issue is explicit that macOS stays primary and must not be destabilised, and
nothing here can be tested against macOS.  Every edit on the host side has the
shape ``if IS_WINDOWS: return win_platform.x(...)`` at the top of a function that
is otherwise untouched, so the macOS path is the same code it was, reached the
same way, with one boolean test in front of it.

The narrowest seam of the lot is the input one.  ``CgInput`` below speaks
``cg_input``'s own line protocol -- ``move x y``, ``down 0``, ``doubleclick 1``,
``idle`` -- so ``_windows_input``'s two hundred lines of tuned behaviour (the
drag that must not pause after the press, the double-click collapse, the key
hold, the human stand-down, the glide) are shared between the platforms rather
than reimplemented.  Those behaviours are where the live findings live, and a
second copy of them is a second set of the bugs they fix.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import input as win_input  # noqa: E402
import tree_walker as win_tree  # noqa: E402
from eve_mem import find_client_pid  # noqa: E402
from window_probe import declare_dpi_awareness, game_window, windows_of_process  # noqa: E402

declare_dpi_awareness()


# --------------------------------------------------------------------------
# Processes and windows
# --------------------------------------------------------------------------


def find_eve_processes() -> list[dict]:
    """The shape ``VolatileProcessInterface.GameClientProcessSummaryStruct`` wants.

    ``mainWindowId`` is the ``HWND`` as a decimal string, which is what the rest
    of the host passes back to ``get_window_rect`` and the foreground calls.  On
    macOS it is a ``CGWindowID``; nothing between here and there interprets it,
    so the two can differ freely.

    The pid is resolved from the executable path, never from a command line --
    the launcher starts the client with ``/ssoToken=`` and ``/refreshToken=`` as
    arguments, so anything that reads an argument vector risks printing live
    credentials into a run log.
    """
    pid = find_client_pid()
    if pid is None:
        return []
    window = game_window(pid)
    if window is None:
        return []
    return [{
        "processId": pid,
        "mainWindowId": str(window.hwnd),
        "mainWindowTitle": window.title or "EVE",
        "mainWindowZIndex": 0,
    }]


def get_window_rect(window_id) -> Optional[dict]:
    """The window's **client** rect in physical pixels, plus a backing scale.

    The client area rather than the frame, and that is a Windows-specific
    correctness point rather than a detail.  A macOS fullscreen game window has
    no decoration, so its frame and its content are the same rectangle and the
    host's own calibration never had to tell them apart.  Here the frame is
    2281x1539 and the client is 2277x1492 on the same window, and it is the
    *client* the game renders its canvas into -- the client's own ``UIRoot``
    reports 2276x1491.  Handing back the frame would put a constant offset into
    every click and a slight scale error on top of it.

    ``backing_scale`` is 1.0 because this process has declared DPI awareness, so
    the numbers here are already physical pixels.  The host self-calibrates
    ``scale_x``/``scale_y`` from ``UIRoot``'s reported canvas against this rect
    regardless -- CLAUDE.md's "don't assume 2.0" -- so a client that disagrees
    still gets the right answer rather than this claim being trusted.
    """
    try:
        hwnd = int(window_id)
    except (TypeError, ValueError):
        return None
    for window in windows_of_process(None):
        if window.hwnd == hwnd:
            return {
                "left": window.client_x,
                "top": window.client_y,
                "right": window.client_x + window.client_width,
                "bottom": window.client_y + window.client_height,
                "backing_scale": 1.0,
            }
    return None


def window_is_onscreen(window_id) -> bool:
    try:
        return win_input.window_is_foreground(int(window_id))
    except (TypeError, ValueError):
        return False


def bring_window_to_foreground(pid, window_id, retries: int = 4, delay: float = 0.2) -> bool:
    try:
        return win_input.bring_window_to_foreground(int(window_id), retries=retries, delay=delay)
    except (TypeError, ValueError):
        return False


# --------------------------------------------------------------------------
# Memory reading
# --------------------------------------------------------------------------


TREE_WALKER_EXE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tree_walker", "tree_walker.exe"
)


class NativeTreeWalkerClient:
    """The C walker, spoken to over the same binary protocol as macOS's.

    Measured against the Python walker on the same client and the same root:
    **143 ms against 1252 ms, 8.7x**, for the same 3,495 nodes and 5,417
    identical string values. That is the whole reason it exists -- see
    ``tree_walker/tree_walker.c``'s header for why the cost was interpreter
    overhead rather than memory reads, and why on Windows a shorter walk is a
    correctness property and not only a faster one.

    Falls back to the Python walker if the binary is not built, rather than
    failing: the Python one is the reference implementation, it works, and a
    host that refuses to start because a build step was skipped is worse than a
    host that runs slower.
    """

    def __init__(self, pid: int):
        self.pid = pid
        self._lock = threading.Lock()
        self.proc = subprocess.Popen(
            [TREE_WALKER_EXE, str(pid)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ready = self.proc.stderr.readline()
        if b"ready" not in ready:
            rest = self.proc.stderr.read() if self.proc.stderr else b""
            raise RuntimeError(
                "tree_walker.exe did not report ready: "
                + (ready + rest).decode("utf-8", "replace").strip()
            )

    def tree(self, root_addr, metatype_addr, str_type_addr,
             max_depth: int = 16, max_nodes: int = 5000):
        with self._lock:
            request = struct.pack(
                "<QQQII", int(root_addr), int(metatype_addr or 0),
                int(str_type_addr or 0), int(max_depth), int(max_nodes),
            )
            self.proc.stdin.write(request)
            self.proc.stdin.flush()
            header = self.proc.stdout.read(8)
            if len(header) < 8:
                raise RuntimeError("tree_walker.exe: short read on length (process died?)")
            (length,) = struct.unpack("<Q", header)
            data = bytearray()
            while len(data) < length:
                chunk = self.proc.stdout.read(length - len(data))
                if not chunk:
                    raise RuntimeError("tree_walker.exe: short read on body")
                data.extend(chunk)
            return json.loads(data)

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class PythonTreeWalkerClient:
    """``botlab_host.TreeWalkerClient``'s interface, backed by the Python walker.

    Same two methods and the same ``tree(...)`` signature, so the host's caching,
    its root validation and its ``_read_from_window`` are unchanged.

    ``metatype_addr`` and ``str_type_addr`` are accepted and ignored: macOS has
    to discover both by scanning, and hands them to the C walker so it does not
    repeat the work.  Here they come from ``python27.dll``'s export table, which
    is authoritative and free.  They stay in the signature because the host
    stores them in its on-disk root cache and passes them back.
    """

    def __init__(self, pid: int):
        self.session = win_tree.open_client(pid)
        self.pid = pid
        self._lock = threading.Lock()

    def tree(self, root_addr, metatype_addr=None, str_type_addr=None,
             max_depth: int = 16, max_nodes: int = 5000):
        # The host reads on its own thread and validates the root cache on
        # another; the reader holds a per-request page cache that must not be
        # interleaved.
        with self._lock:
            return self.session.walker.read_tree(
                int(root_addr), max_depth=max_depth, node_budget=max_nodes
            )

    def close(self) -> None:
        try:
            self.session.reader.close()
        except Exception:
            pass


def TreeWalkerClient(pid: int):
    """The native walker where it has been built, the Python one otherwise.

    Chosen at construction and reported on stderr, because "which walker am I
    running" is the first question to ask of a timing number and the second to
    ask of a wrong reading.
    """
    if os.path.exists(TREE_WALKER_EXE):
        try:
            client = NativeTreeWalkerClient(pid)
            print("# tree_walker: native (tree_walker.exe)", file=sys.stderr)
            return client
        except Exception as exc:
            print(f"# tree_walker.exe failed to start ({exc}); using the Python walker",
                  file=sys.stderr)
    else:
        print(f"# tree_walker.exe not built ({TREE_WALKER_EXE}); using the Python walker "
              f"-- run tree_walker/build.bat for an ~8.7x faster read", file=sys.stderr)
    return PythonTreeWalkerClient(pid)


def search_ui_root(pid: int):
    """``(root, metatype, str_type)`` for the host's root-search worker.

    macOS takes a full process dump (~20-40s) and regex-scans it for EVE's own
    debug-log repr text.  That text does not exist in this client -- a scan of
    the whole readable address space finds none of it -- so the root is found by
    locating the ``UIRoot`` type object and then its instances.  See
    ``tree_walker.find_ui_root`` and FINDINGS.md section 3.

    Returns ``(None, None, None)`` rather than raising, because the host's worker
    stores whatever this gives it and a `None` root is how it reports a failed
    search to the bot.
    """
    try:
        session = win_tree.open_client(pid)
    except Exception:
        return (None, None, None)
    try:
        root = win_tree.find_ui_root(session.reader, session.py, verbose=True)
        metatype = session.py.types.by_name.get("type")
        str_type = session.py.types.by_name.get("str")
        return (root, metatype, str_type)
    finally:
        session.reader.close()


# --------------------------------------------------------------------------
# Input
# --------------------------------------------------------------------------


class CgInput:
    """``cg_input``'s line protocol, executed with ``SendInput``.

    The host talks to macOS's input helper by writing one text command per line
    and reading ``ok`` or ``idle <seconds>`` back.  Keeping that protocol is what
    lets ``_windows_input`` stay one implementation: the command vocabulary is
    the whole platform boundary, and everything above it -- which is where every
    live finding about this client's input handling lives -- is shared.

    ``text`` is deliberately not implemented.  ``cg_input``'s own comment records
    it not working against this client on macOS ("a single 'z' sent this way
    arrives as nothing at all"), the host never sends it, and an unimplemented
    command that answers ``ok`` would be this repo's signature failure.
    """

    def __init__(self, execute: bool):
        self.io = win_input.WindowsInput(execute=execute)

    def command(self, line: str) -> str:
        parts = line.split()
        if not parts:
            return "err parse"
        verb, args = parts[0], parts[1:]
        try:
            if verb == "move":
                self.io.move_to(int(round(float(args[0]))), int(round(float(args[1]))))
            elif verb == "down":
                self.io.button_down(int(float(args[0])))
            elif verb == "up":
                self.io.button_up(int(float(args[0])))
            elif verb == "doubleclick":
                self.io.double_click(int(float(args[0])))
            elif verb == "drag":
                # A drag on Windows is an ordinary move while a button happens to
                # be held; there is no separate event type the way macOS has
                # kCGEventLeftMouseDragged, so the button state the OS already
                # tracks is what makes it one.
                self.io.move_to(int(round(float(args[0]))), int(round(float(args[1]))))
            elif verb == "scroll":
                # `scroll <dx> <dy>`; the host only ever sends a vertical amount.
                self.io.scroll(int(float(args[1])) if len(args) > 1 else int(float(args[0])))
            elif verb == "keydown":
                self.io.key_down(int(float(args[0])))
            elif verb == "keyup":
                self.io.key_up(int(float(args[0])))
            elif verb == "idle":
                idle = self.io.seconds_since_human_input()
                return f"idle {idle:.3f}" if idle is not None else "idle 999.000"
            else:
                return "err unknown command"
        except (IndexError, ValueError):
            return f"err bad args for {verb}"
        except win_input.InputError as exc:
            return f"err {exc}"
        return "ok"

    def release_everything(self):
        return self.io.release_everything()

    def close(self) -> None:
        pass


def vk_to_keycode(vk: int) -> int:
    """The identity.

    ``Common/EffectOnWindow.elm``'s ``vkey_*`` values *are* Windows virtual key
    codes, because the framework was written for Windows.  macOS needs an
    explicit table and has been bitten twice by it -- ``vkey_SUBTRACT`` (0x6D)
    missing from it entirely, and a letter bound that turned an untypable
    character into ``vkey_LWIN``, putting Command down underneath the typing.
    There is no table here to be wrong.
    """
    return vk


# --------------------------------------------------------------------------
# Paths and the screenshot
# --------------------------------------------------------------------------


def game_log_directory() -> str:
    """Where EVE writes its own game logs on Windows.

    ``Documents\\EVE\\logs\\Gamelogs``, the same leaf as macOS under a different
    home.  Resolved through the shell's Personal folder rather than assembled
    from ``USERPROFILE``, because Documents is commonly redirected to OneDrive
    and the assembled path then names a directory that exists and is empty --
    which reads to every consumer as a client that never says anything.
    """
    documents = None
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_PERSONAL = 5, SHGFP_TYPE_CURRENT = 0
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            documents = buf.value
    except Exception:
        documents = None
    if not documents:
        documents = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(documents, "EVE", "logs", "Gamelogs")


def capture_image_data(*_args, **_kwargs):
    """Deliberately empty, and that is the point of the whole port.

    Issue #176 step 5: "Do not port the screenshot path. It is diagnostic on
    macOS and it is the cost being escaped here. If the framework requires the
    field, satisfy it the way the macOS host does -- ``screenshotCrops_original``
    deliberately empty."
    """
    return {
        "screenshotCrops_original": [],
        "screenshotCrops_binned_2x2": [],
        "screenshotCrops_binned_4x4": [],
    }
