"""Input execution for the Windows host: the port of ``cg_input.c``.

Issue #176's table asks for ``cg_input`` (CoreGraphics) to become ``SendInput``.
The API swap is the easy half and is about forty lines of it; what carries the
weight is the behaviour the macOS host tuned against this client over many runs,
which is documented in ``botlab_host.py`` and CLAUDE.md rather than in
``cg_input.c``. Each of those is reproduced here with the reason kept, because
every one of them is a live failure somebody already paid for.

**This is not a separate process.**  ``cg_input`` has to be one, and CLAUDE.md
says why -- it "tracks click position as process-local state set by the last
`move`, so a fresh process per command always clicks at (0, 0)".  Windows has no
such problem: a button event is delivered at the cursor's real position, which
the OS owns, so there is no state to keep and nothing to keep it in.  The
persistent-helper design was a workaround for a macOS constraint and is not
ported.

**Two things get simpler and one gets harder.**

*Simpler:* the key mapping disappears.  ``Common/EffectOnWindow.elm``'s
``vkey_*`` values are literal Windows virtual key codes -- ``vkey_RETURN`` is
``0x0D``, ``vkey_CONTROL`` is ``0x11``, ``vkey_A`` is ``0x41`` -- because the
framework was written for Windows.  macOS needs ``_VK_TO_CGKEYCODE``, "an
explicit lookup table ... neither side is contiguous for letters or digits, so
no arithmetic mapping works", and that table has cost this repo two real bugs:
``vkey_SUBTRACT`` missing from it entirely, and a letter bound of ``<= 26``
turning an untypable character into ``vkey_LWIN``, which put Command down
underneath the typing.  Here there is no table to be wrong.

*Simpler:* the double click needs no special event field.  macOS requires
``kCGMouseEventClickState`` to say 2 or the application sees two independent
clicks; Windows does that detection itself, in the receiving application, from
timing and distance.

*Harder:* DPI.  See ``window_probe.declare_dpi_awareness`` -- a process that has
not declared awareness is handed virtualised coordinates and ``SendInput``
consumes virtualised coordinates, so every click lands somewhere else and
nothing reports an error.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from typing import Optional

from window_probe import declare_dpi_awareness, game_window

declare_dpi_awareness()

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# --------------------------------------------------------------------------
# Timings, carried over from the macOS host with their reasons
# --------------------------------------------------------------------------

# How long a key is held between KeyDown and KeyUp.  The framework interleaves
# WaitMilliseconds 210 between every pair of effects, which is longer than the
# system's key-repeat delay -- run 115 typed "Reports" into a filter and left
# "reportreprrrrrr...rrreporteporte". A press with no hold at all is not the
# answer either; the client misses those, which reads as characters dropping at
# random. Windows' repeat delay is 250ms at its shortest setting, so 30ms is
# under it there too.
KEY_HOLD_SECONDS = 0.03

# A click fired immediately after the cursor arrives can miss; the settle is
# applied only where a move leads straight into a ButtonDown.
CLICK_SETTLE_DELAY_SECONDS = 0.15

# The bot yields to a person at the keyboard rather than fighting for the cursor.
HUMAN_INPUT_STAND_DOWN_SECONDS = 5.0

# The glide. Photon UI cares about real trajectories, not just final position --
# established twice over on macOS, once for drag recognition and once for
# hover-triggered flyouts. 10 steps at 25ms is the value a live A/B settled on
# after 6 steps at 12ms left an anomaly-warp cascade stuck with the flyout never
# opening.
GLIDE_STEPS = 10
GLIDE_STEP_SECONDS = 0.025

# Under this many pixels counts as already there.
AT_TARGET_PIXELS = 3

# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
WHEEL_DELTA = 120

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC = 0

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

# VK codes whose scan code must carry the extended-key flag, or the receiving
# application reads the numpad twin instead: an arrow key sent without it can
# arrive as a digit when NumLock is on.
EXTENDED_VKS = frozenset({
    0x21, 0x22, 0x23, 0x24,          # PRIOR NEXT END HOME
    0x25, 0x26, 0x27, 0x28,          # LEFT UP RIGHT DOWN
    0x2C, 0x2D, 0x2E,                # PRINT INSERT DELETE
    0x5B, 0x5C, 0x5D,                # LWIN RWIN APPS
    0x6F,                            # DIVIDE
    0x90,                            # NUMLOCK
    0xA3, 0xA5,                      # RCONTROL RMENU
})


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = wintypes.UINT
_user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
_user32.MapVirtualKeyW.restype = wintypes.UINT
_user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
_user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]


class InputError(RuntimeError):
    pass


def _send(*inputs: INPUT) -> None:
    array = (INPUT * len(inputs))(*inputs)
    sent = _user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT))
    if sent != len(inputs):
        err = ctypes.get_last_error()
        # UIPI: a process at a lower integrity level than the target cannot
        # inject into it, and SendInput reports that by sending nothing rather
        # than by failing loudly.  Worth naming, because "the bot clicks and
        # nothing happens" is otherwise indistinguishable from a missed click.
        raise InputError(
            f"SendInput sent {sent} of {len(inputs)} events (Win32 error {err})"
            + (" -- the target may be running elevated while this host is not"
               if err == 5 else "")
        )


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> INPUT:
    event = INPUT()
    event.type = INPUT_MOUSE
    event.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, None)
    return event


def _key(vk: int, up: bool) -> INPUT:
    """One key event carrying both the virtual key and its scan code.

    Games commonly read the keyboard below the virtual-key layer -- DirectInput
    and Raw Input both deliver scan codes -- so a VK-only event can be ignored by
    the very application it is aimed at while working everywhere else.  macOS hit
    the mirror image of this and its note is the warning: driving the search
    field a character at a time, "'a' (keycode 0) never arrived at all across
    five retries" while other letters were perfect.  Sending both costs nothing
    and leaves the receiver to take whichever it reads.
    """
    scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_KEYUP if up else 0
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    event = INPUT()
    event.type = INPUT_KEYBOARD
    event.ki = KEYBDINPUT(vk, scan, flags, 0, None)
    return event


def virtual_screen() -> tuple[int, int, int, int]:
    return (
        _user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        _user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        _user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        _user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


# --------------------------------------------------------------------------


class WindowsInput:
    """Executes one bot input sequence's worth of effects.

    Holds only what the macOS host holds: which buttons and keys it has pressed
    and not released, when it last posted anything, and where it last aimed.
    """

    def __init__(self, execute: bool = False):
        self.execute = execute
        self.buttons_down: set[int] = set()
        self.keys_down: list[int] = []
        self.last_post_at: Optional[float] = None
        self.last_target: Optional[tuple[int, int]] = None
        self.posted = 0

    # -- the guard ---------------------------------------------------------

    def seconds_since_human_input(self) -> Optional[float]:
        """How long since a *person* last touched the mouse or keyboard.

        Windows has macOS's problem here exactly: ``GetLastInputInfo`` counts
        injected input too, so the reading alone cannot say who moved the mouse.
        The macOS host's answer is the one that works and it ports unchanged --
        we know when *we* last posted, so an input event no more recent than our
        own last post was ours, and one appreciably more recent was not.
        """
        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not _user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        idle = (_k32_tick() - info.dwTime) / 1000.0
        if self.last_post_at is None:
            return idle
        since_our_post = time.monotonic() - self.last_post_at
        # A margin for ordinary jitter between posting an event and reading the
        # clock back.
        if idle >= since_our_post - 0.25:
            return None
        return idle

    def standing_down(self) -> Optional[float]:
        """The idle time if the bot should skip this sequence, else ``None``.

        Nothing needs unwinding when this fires: the bot re-derives its decision
        from a fresh reading every step, so a skipped sequence costs one tick and
        is simply decided again once the machine is quiet.
        """
        idle = self.seconds_since_human_input()
        if idle is not None and idle < HUMAN_INPUT_STAND_DOWN_SECONDS:
            return idle
        return None

    # -- mouse -------------------------------------------------------------

    def _post(self, *events: INPUT) -> None:
        if not self.execute:
            return
        _send(*events)
        self.posted += len(events)
        self.last_post_at = time.monotonic()

    def move_to(self, x: int, y: int) -> None:
        """Teleport the cursor to a screen pixel.  Prefer ``glide_to``."""
        left, top, width, height = virtual_screen()
        # SendInput's absolute space is 0..65535 across the virtual desktop, and
        # the conversion is off by one at the far edge if the -1 is dropped.
        nx = int(round((x - left) * 65535 / max(1, width - 1)))
        ny = int(round((y - top) * 65535 / max(1, height - 1)))
        self._post(
            _mouse(
                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK,
                max(0, min(65535, nx)),
                max(0, min(65535, ny)),
            )
        )
        self.last_target = (x, y)

    def glide_to(self, x: int, y: int, force_movement: bool = False) -> bool:
        """Move through intermediate points, and report whether it moved at all.

        Three behaviours, all of them macOS findings and none of them obvious:

        - **Glide rather than teleport.** Photon UI reads real trajectories, for
          drag recognition and for hover-triggered flyouts both.
        - **Do not re-issue an identical move.** A flyout needs sustained,
          uninterrupted dwell, and re-gliding to the same spot every tick resets
          that timer before it accumulates -- an endless open/close flap that
          looks like hard failure rather than a slow success.
        - **Except before a click**, where the opposite is true: a click retried
          at a target the cursor is already resting on fires with no movement
          gesture at all, and plausibly keeps failing the same way the first one
          did.  ``force_movement`` nudges off target and glides back.
        """
        start = cursor_position() if self.execute else (self.last_target or (x, y))
        already_there = (
            abs(x - start[0]) < AT_TARGET_PIXELS and abs(y - start[1]) < AT_TARGET_PIXELS
        )
        if already_there and not force_movement:
            self.last_target = (x, y)
            return False
        if already_there and force_movement:
            # A small real gesture: step off, then come back.
            self.move_to(x - 12, y - 12)
            time.sleep(GLIDE_STEP_SECONDS)
            start = (x - 12, y - 12)
        for step in range(1, GLIDE_STEPS + 1):
            fraction = step / GLIDE_STEPS
            # Ease in and out, so the trajectory has acceleration rather than
            # being a uniform slide.
            eased = fraction * fraction * (3 - 2 * fraction)
            self.move_to(
                int(round(start[0] + (x - start[0]) * eased)),
                int(round(start[1] + (y - start[1]) * eased)),
            )
            if step < GLIDE_STEPS:
                time.sleep(GLIDE_STEP_SECONDS)
        return True

    _DOWN = {0: MOUSEEVENTF_LEFTDOWN, 1: MOUSEEVENTF_RIGHTDOWN, 2: MOUSEEVENTF_MIDDLEDOWN}
    _UP = {0: MOUSEEVENTF_LEFTUP, 1: MOUSEEVENTF_RIGHTUP, 2: MOUSEEVENTF_MIDDLEUP}

    def button_down(self, button: int) -> None:
        self._post(_mouse(self._DOWN.get(button, MOUSEEVENTF_LEFTDOWN)))
        self.buttons_down.add(button)

    def button_up(self, button: int) -> None:
        self._post(_mouse(self._UP.get(button, MOUSEEVENTF_LEFTUP)))
        self.buttons_down.discard(button)

    def double_click(self, button: int) -> None:
        """Two press/release pairs with nothing between them.

        Unlike macOS this needs no special event field -- Windows does the
        detection in the receiving application, from the gap between the two
        presses and the distance between them.  What it does need is for the
        gap to be under ``GetDoubleClickTime`` (500ms by default), which is why
        the caller collapses the bot's four separate effects into this one call
        rather than letting the framework's 210ms inter-effect waits sit between
        them: two of those is 420ms, close enough to the limit that a user who
        has ever moved that slider would get two single clicks instead.
        """
        down = self._DOWN.get(button, MOUSEEVENTF_LEFTDOWN)
        up = self._UP.get(button, MOUSEEVENTF_LEFTUP)
        self._post(_mouse(down), _mouse(up), _mouse(down), _mouse(up))

    def scroll(self, notches: int) -> None:
        """Wheel at the cursor's current position, which is where it goes."""
        self._post(_mouse(MOUSEEVENTF_WHEEL, data=notches * WHEEL_DELTA))

    # -- keyboard ----------------------------------------------------------

    def key_down(self, vk: int) -> None:
        self._post(_key(vk, up=False))
        if vk not in self.keys_down:
            self.keys_down.append(vk)

    def key_up(self, vk: int) -> None:
        self._post(_key(vk, up=True))
        if vk in self.keys_down:
            self.keys_down.remove(vk)

    def release_everything(self) -> list[int]:
        """Take back anything this host pressed and did not release.

        Issue #175's fix, ported: on macOS ``_keys_down`` was written on every
        KeyDown and read nowhere, so a sequence that ended with a modifier held
        left it down underneath every keystroke and click that followed, for the
        rest of the run.  ``effectsToEnterString`` builds exactly that sequence,
        emitting ``KeyUp SHIFT`` only when the *next* character does not want it.

        In reverse order, because the undo of two modifiers is the presses
        backwards.  Wrapped, because the likeliest reason a key is stuck is that
        something already went wrong.
        """
        released = []
        for vk in reversed(list(self.keys_down)):
            try:
                self.key_up(vk)
                released.append(vk)
            except InputError:
                pass
        for button in list(self.buttons_down):
            try:
                self.button_up(button)
            except InputError:
                pass
        return released


def _k32_tick() -> int:
    return ctypes.WinDLL("kernel32").GetTickCount()


# --------------------------------------------------------------------------
# Foreground
# --------------------------------------------------------------------------


def window_is_foreground(hwnd: int) -> bool:
    return int(_user32.GetForegroundWindow()) == int(hwnd)


def bring_window_to_foreground(hwnd: int, retries: int = 4, delay: float = 0.2) -> bool:
    """Focus a window, working around Windows' foreground lock.

    ``SetForegroundWindow`` is not a command, it is a request, and Windows
    refuses it from a process that does not already own the foreground -- which
    is exactly this one's situation.  The documented way through is to attach
    this thread's input queue to the current foreground window's, which makes the
    two count as one input context for the duration.

    Verified afterwards rather than trusted, and the fast path is checked first:
    ``BotFramework.elm`` prepends ``BringWindowToForeground`` to *every* input
    sequence, so the overwhelmingly common case is that it is already there.
    Paying an unconditional attach-and-sleep per click was the real source of
    felt sluggishness on macOS.
    """
    if window_is_foreground(hwnd):
        return True

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    our_thread = kernel32.GetCurrentThreadId()
    for _ in range(retries):
        foreground = _user32.GetForegroundWindow()
        their_thread = _user32.GetWindowThreadProcessId(foreground, None) if foreground else 0
        attached = False
        if their_thread and their_thread != our_thread:
            attached = bool(_user32.AttachThreadInput(their_thread, our_thread, True))
        try:
            _user32.ShowWindow(wintypes.HWND(hwnd), 9)  # SW_RESTORE, in case minimised
            _user32.SetForegroundWindow(wintypes.HWND(hwnd))
            _user32.SetActiveWindow(wintypes.HWND(hwnd))
        finally:
            if attached:
                _user32.AttachThreadInput(their_thread, our_thread, False)
        time.sleep(delay)
        if window_is_foreground(hwnd):
            return True
    return False


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="input executor self-test -- reports what it would do"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually send input. Without this nothing is sent to any window.",
    )
    parser.add_argument("--pid", type=int, default=None)
    args = parser.parse_args()

    from eve_mem import find_client_pid

    print(f"DPI awareness: {declare_dpi_awareness()}")
    left, top, width, height = virtual_screen()
    print(f"virtual desktop: {width}x{height} at ({left},{top})")
    print(f"cursor now: {cursor_position()}")

    pid = args.pid or find_client_pid()
    if pid:
        window = game_window(pid)
        if window:
            print(f"client window: hwnd=0x{window.hwnd:X} "
                  f"client {window.client_width}x{window.client_height} "
                  f"at ({window.client_x},{window.client_y})")
            print(f"foreground: {window_is_foreground(window.hwnd)}")

    controller = WindowsInput(execute=args.execute)
    idle = controller.seconds_since_human_input()
    print(f"seconds since human input: {idle}")
    print(f"would stand down: {controller.standing_down() is not None}")

    # Key mapping is the identity here, which is the claim worth checking.
    for name, vk in (("RETURN", 0x0D), ("CONTROL", 0x11), ("A", 0x41), ("F1", 0x70),
                     ("LEFT", 0x25), ("SUBTRACT", 0x6D)):
        scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        extended = " extended" if vk in EXTENDED_VKS else ""
        print(f"  vkey_{name:<9} 0x{vk:02X} -> scan 0x{scan:02X}{extended}")

    if not args.execute:
        print()
        print("Nothing was sent. Pass --execute to drive the real mouse and keyboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
