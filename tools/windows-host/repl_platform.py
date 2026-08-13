"""Everything ``eve_repl.py`` reaches the operating system through, on Windows.

Issue #192. Same posture as ``win_platform.py`` is for the host: ``eve_repl``
keeps its macOS code exactly as it is and gains ``if IS_WINDOWS:`` in front of
four call sites -- attach, window geometry, tree read, and input -- while
everything above those seams stays one implementation.

That matters more for the repl than for the host. What lives above the seams is
the list of conventions in ``eve_repl``'s module docstring, and every one of
them is a debugging session somebody already paid for: the name column, because
a row's own region resolves to the icon column and does not select; the
mid-entry click, because a menu entry's reported y is its top edge and clicking
it lands on the entry above; find-and-click in one pass, because the overview
re-sorts between a read and a click. A second copy of those is a second set of
the bugs they fix.

This is a separate module from ``win_platform`` deliberately -- that file's own
first line scopes it to what the *host* reaches the OS through, and the repl is
a different consumer with a different lifetime.

Three things differ from macOS and none of them is a preference:

**There is no UI-root cache to read.** ``eve_read.ui_root()`` reads what a bot
run leaves behind, and says in as many words that the repl cannot be used before
one exists. ``find_client_pid`` plus ``find_ui_root`` answers the same question
directly, so the Windows repl attaches to a client no bot has ever been pointed
at -- which is the situation it is most wanted in.

**The walker session is held open.** Attaching costs a handle and
``find_ui_root`` costs a scan, and a cold scan is about four minutes after a
reboot (FINDINGS section 8). It is reopened only when a read fails, which is
what a relaunched client looks like -- root addresses are per launch and never
reused.

**Geometry is the client rect, not the window rect.** The tree's canvas covers
the drawable area, so including the title bar and border in the scale drifts
every click down the screen by their height.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
import time
import zlib
from ctypes import wintypes
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import input as win_input  # noqa: E402
import tree_walker as win_tree  # noqa: E402
import win_platform  # noqa: E402
from eve_mem import find_client_pid  # noqa: E402
from window_probe import declare_dpi_awareness, game_window, windows_of_process  # noqa: E402

declare_dpi_awareness()

SRCCOPY = 0x00CC0020


class ReplBackend:
    """The platform half of an ``eve_repl`` session."""

    def __init__(self, execute: bool = True):
        # `win_platform.CgInput` rather than a second input path: it speaks
        # `cg_input`'s own line protocol, so the tuned behaviour behind it --
        # the glide, the click settle, the human stand-down -- is the same code
        # the bot uses rather than a reimplementation of it.
        self._cg = win_platform.CgInput(execute=execute)
        self._session = None
        self._root = None
        self._pid = None
        self._foregrounded = False

    # -- attach ------------------------------------------------------------

    def attach(self) -> dict:
        """``{"pid": ...}``, the shape ``eve_read.ui_root()`` returns."""
        pid = find_client_pid()
        if not pid:
            raise RuntimeError("no running EVE client found")
        self._pid = pid
        return {"pid": pid}

    def window(self, pid: int):
        """``(hwnd, (x, y), (width, height))`` of the **client area**."""
        found = game_window(pid)
        if found is None:
            candidates = [w for w in windows_of_process(pid)
                          if w.visible and w.width > 200 and w.height > 200]
            if not candidates:
                raise RuntimeError("no window found for pid %d" % pid)
            found = max(candidates, key=lambda w: w.width * w.height)
        return (found.hwnd,
                (float(found.client_x), float(found.client_y)),
                (float(found.client_width), float(found.client_height)))

    # -- reading -----------------------------------------------------------

    def _open(self, pid: int):
        session = win_tree.open_client(pid)
        root = win_tree.find_ui_root(session.reader, session.py)
        if not root:
            session.reader.close()
            raise RuntimeError("no UIRoot found in pid %d" % pid)
        self._session, self._root = session, root

    def read_tree(self, pid: int) -> dict:
        if self._session is None or self._pid != pid:
            self.close_reader()
            self._open(pid)
            self._pid = pid
        try:
            return self._session.walker.read_tree(self._root)
        except Exception:
            # Usually the client having gone or relaunched, which invalidates
            # the root address. One retry against a fresh attach, then raise --
            # a silent empty tree would read as "the client shows nothing".
            self.close_reader()
            self._open(pid)
            return self._session.walker.read_tree(self._root)

    # -- input -------------------------------------------------------------

    def command(self, line: str, hwnd: Optional[int] = None) -> str:
        """One ``cg_input`` protocol line, executed with ``SendInput``.

        The client is raised once per session rather than per command. It is a
        request Windows can refuse, and paying it on every ``move`` of a glide
        is exactly the felt sluggishness ``BringWindowToForeground`` is recorded
        as causing on macOS.
        """
        if hwnd is not None and not self._foregrounded:
            win_input.bring_window_to_foreground(hwnd)
            time.sleep(0.3)
            self._foregrounded = True
        return self._cg.command(line)

    # -- pictures ----------------------------------------------------------

    def screenshot(self, hwnd: int, path: str) -> str:
        """The window to a PNG, by handle.

        macOS captures by window id because the client is usually on another
        Space. Windows has no Spaces, but a window can still sit behind another
        and ``BitBlt`` copies whatever is really on top -- so the window is
        raised first, and that is the trap ``launch_character.py`` documents
        after a capture of the wrong application was read as the launcher.
        """
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        win_input.bring_window_to_foreground(hwnd)
        time.sleep(0.25)

        rect = wintypes.RECT()
        user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top

        srcdc = user32.GetDC(None)
        memdc = gdi32.CreateCompatibleDC(srcdc)
        bitmap = gdi32.CreateCompatibleBitmap(srcdc, width, height)
        gdi32.SelectObject(memdc, bitmap)
        gdi32.BitBlt(memdc, 0, 0, width, height, srcdc,
                     rect.left, rect.top, SRCCOPY)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD),
                        ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD),
                        ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long),
                        ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth, header.biHeight = width, -height
        header.biPlanes, header.biBitCount, header.biCompression = 1, 24, 0
        stride = ((width * 3 + 3) // 4) * 4
        buffer = ctypes.create_string_buffer(stride * height)
        gdi32.GetDIBits(memdc, bitmap, 0, height, buffer, ctypes.byref(header), 0)

        raw = bytearray()
        for row in range(height):
            raw += b"\x00"
            line = bytearray(buffer[row * stride:row * stride + width * 3])
            line[0::3], line[2::3] = line[2::3], line[0::3]  # BGR -> RGB
            raw += line

        def chunk(kind, data):
            body = struct.pack(">I", len(data)) + kind + data
            return body + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
               + chunk(b"IEND", b""))
        with open(path, "wb") as handle:
            handle.write(png)

        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(None, srcdc)
        return path

    # -- teardown ----------------------------------------------------------

    def close_reader(self):
        if self._session is not None:
            try:
                self._session.reader.close()
            except Exception:  # noqa: BLE001 - closing a dead handle
                pass
            self._session, self._root = None, None

    def close(self):
        self.close_reader()


# --------------------------------------------------------------------------
# Keys
# --------------------------------------------------------------------------

# `keydown <n>` reaches `SendInput` as a **Windows virtual key code** --
# `win_platform.vk_to_keycode` is the identity, deliberately, because the
# framework's own `vkey_*` values already are Windows codes.
#
# eve_repl's tables are macOS CGKeyCodes, and the two overlap in the worst
# possible way rather than failing: CGKeyCode 53 is Escape and Windows 53 is the
# `5` key, so the macOS table used here would type digits where the repl said it
# was pressing Escape, and report `ok` for every one of them. That is this
# repo's signature failure, so the tables are per platform rather than shared.
KEYS = {
    "escape": 0x1B, "return": 0x0D, "d": 0x44, "j": 0x4A, "c": 0x43,
    "w": 0x57, "alt": 0x12, "ctrl": 0x11, "shift": 0x10,
    # No Command key. `cmd` is bound to LWIN so a macOS-shaped call does not
    # raise, but note CLAUDE.md's warning: on this client a stray Windows/
    # Command key leaves the field swallowing every keystroke that follows.
    "cmd": 0x5B,
}

KEY_BACKSPACE = 0x08
KEY_FORWARD_DELETE = 0x2E
KEY_END = 0x23

KEYCODE = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
KEYCODE.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
KEYCODE.update({str(d): ord(str(d)) for d in range(10)})
KEYCODE[" "] = 0x20
