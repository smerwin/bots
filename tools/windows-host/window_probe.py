"""Window enumeration for the Windows host.

The port of ``tools/macos-host/window_probe/window_probe.c``, which uses
``CGWindowList``; here it is ``EnumWindows`` + ``GetWindowRect``, which is what
issue #176's table asks for.

The macOS version's hard-won rule is carried over rather than rediscovered:
**pick the largest window by area for a pid, not the first one over a width
threshold.**  CLAUDE.md records a fullscreen game window having a smaller
same-width overlay (the reveal-on-hover menu-bar strip, ~1710x44) that a naive
check picks by accident, giving a badly wrong y-scale and bogus click targets.
Windows has its own version of the same hazard -- a client with any tool window,
tooltip or IME candidate window open exposes several windows on the same pid --
so the rule is the rule here too.

What does *not* carry over is the macOS ``--all`` flag and its Spaces problem.
``CGWindowListCopyWindowInfo``'s on-screen-only query sees nothing when the game
is on another Space; Windows has no Spaces, and ``EnumWindows`` enumerates
top-level windows on the desktop regardless of z-order or occlusion, so there is
nothing for the flag to switch on.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from dataclasses import asdict, dataclass
from typing import Optional

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

_user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
_user32.EnumWindows.restype = wintypes.BOOL
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_user32.GetForegroundWindow.restype = wintypes.HWND

# DWM's extended frame bounds, rather than GetWindowRect's.  Since Vista the
# latter includes the invisible resize border, which is 7-8px per side at
# 100% scaling and more when scaled -- an offset that lands every click that
# far off if it is taken as the visible edge.
DWMWA_EXTENDED_FRAME_BOUNDS = 9


@dataclass
class Window:
    hwnd: int
    pid: int
    title: str
    visible: bool
    foreground: bool
    # The visible frame, in screen pixels.
    x: int
    y: int
    width: int
    height: int
    # The client area, which is what the game renders into.
    client_x: int
    client_y: int
    client_width: int
    client_height: int

    @property
    def area(self) -> int:
        return self.width * self.height


def _frame_bounds(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    got = _dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if got != 0:
        _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def windows_of_process(pid: Optional[int] = None) -> list[Window]:
    found: list[Window] = []
    foreground = _user32.GetForegroundWindow()

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if pid is not None and owner.value != pid:
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        x, y, width, height = _frame_bounds(hwnd)
        client = wintypes.RECT()
        _user32.GetClientRect(hwnd, ctypes.byref(client))
        origin = wintypes.POINT(0, 0)
        _user32.ClientToScreen(hwnd, ctypes.byref(origin))
        found.append(
            Window(
                hwnd=int(hwnd),
                pid=owner.value,
                title=buffer.value,
                visible=bool(_user32.IsWindowVisible(hwnd)),
                foreground=int(hwnd) == int(foreground),
                x=x,
                y=y,
                width=width,
                height=height,
                client_x=origin.x,
                client_y=origin.y,
                client_width=client.right,
                client_height=client.bottom,
            )
        )
        return True

    _user32.EnumWindows(WNDENUMPROC(callback), 0)
    return found


def game_window(pid: int) -> Optional[Window]:
    """The client's real window: the largest visible one belonging to the pid.

    Largest *by area*, for the reason CLAUDE.md records costing a debugging
    session on macOS -- a same-width overlay picked by a width threshold gives a
    badly wrong y-scale and every click lands somewhere else.
    """
    candidates = [w for w in windows_of_process(pid) if w.visible and w.area > 0]
    if not candidates:
        return None
    return max(candidates, key=lambda w: w.area)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--all", action="store_true", help="every window, not just the game's")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    pid = args.pid
    if pid is None:
        sys.path.insert(0, __file__.rsplit("\\", 1)[0])
        from eve_mem import find_client_pid

        pid = find_client_pid()
        if pid is None:
            print("no EVE client found", file=sys.stderr)
            return 1

    if args.all:
        result = [asdict(w) for w in windows_of_process(None if args.all else pid)]
    else:
        window = game_window(pid)
        if window is None:
            print(f"no visible window for pid {pid}", file=sys.stderr)
            return 1
        result = [asdict(window)]

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for w in result:
            print(
                f"hwnd=0x{w['hwnd']:X} pid={w['pid']} "
                f"frame=({w['x']},{w['y']} {w['width']}x{w['height']}) "
                f"client=({w['client_x']},{w['client_y']} "
                f"{w['client_width']}x{w['client_height']}) "
                f"{'FG ' if w['foreground'] else ''}{w['title']!r}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
