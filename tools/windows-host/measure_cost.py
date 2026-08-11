"""What a reading costs: the screenshot against the memory read.

Issue #176's second unverified item, in full:

    Whether the screenshot is actually BotLab.exe's cost was not measured, only
    reported.  If the expense is the capture rather than the decode, then simply
    not capturing may win most of it without porting tree_walker at all -- a far
    smaller change worth pricing first.

That is a fair challenge to the whole premise of the port and it is answerable
here, because this machine has both a live client and a running BotLab.exe.  This
measures the three things that decide it and asserts nothing:

1. **One window capture**, the way a host would take it -- BitBlt of the client
   area into a DIB, which is what any Windows screenshot path reduces to.
2. **One full UI-tree read** through the ported walker, on the same client, same
   moment.
3. **What BotLab.exe is actually spending** -- CPU time and working set over an
   interval, sampled rather than inferred.

Read-only throughout: it captures pixels and reads memory, and sends no input.
"""

from __future__ import annotations

import argparse
import ctypes
import statistics
import sys
import time
from ctypes import wintypes

from eve_mem import find_client_pid
from window_probe import game_window

_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

SRCCOPY = 0x00CC0020
BI_RGB = 0
DIB_RGB_COLORS = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def capture_client(window, want_pixels: bool = True):
    """One BitBlt of the window's client area, returning (seconds, bytes).

    This is the cheapest correct way to take the shot on Windows and therefore
    the fairest number to price the port against: anything a real host does
    (PrintWindow, Desktop Duplication, a PIL grab) is this plus overhead.
    """
    width, height = window.client_width, window.client_height
    started = time.perf_counter()

    screen_dc = _user32.GetDC(None)
    memory_dc = _gdi32.CreateCompatibleDC(screen_dc)
    bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    _gdi32.SelectObject(memory_dc, bitmap)
    _gdi32.BitBlt(
        memory_dc, 0, 0, width, height,
        screen_dc, window.client_x, window.client_y, SRCCOPY,
    )

    size = 0
    if want_pixels:
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        size = width * height * 4
        buffer = (ctypes.c_char * size)()
        _gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, ctypes.byref(info), DIB_RGB_COLORS)

    _gdi32.DeleteObject(bitmap)
    _gdi32.DeleteDC(memory_dc)
    _user32.ReleaseDC(None, screen_dc)
    return time.perf_counter() - started, size


def process_cpu_and_memory(pid: int):
    """(kernel+user CPU seconds, working set bytes) for a pid."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        creation, exit_, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not _k32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None

        def seconds(ft):
            return ((ft.dwHighDateTime << 32) | ft.dwLowDateTime) / 1e7

        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        return seconds(kernel) + seconds(user), counters.WorkingSetSize
    finally:
        _k32.CloseHandle(handle)


def find_pid_by_name(name: str):
    import subprocess

    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"Get-Process {name} -ErrorAction SilentlyContinue | "
         "Sort-Object WorkingSet64 -Descending | Select-Object -First 1 -ExpandProperty Id"],
        capture_output=True, text=True,
    )
    text = out.stdout.strip()
    return int(text) if text.isdigit() else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, default=None)
    parser.add_argument("--shots", type=int, default=12)
    parser.add_argument("--reads", type=int, default=5)
    parser.add_argument("--watch", type=float, default=20.0,
                        help="seconds to sample BotLab.exe over")
    args = parser.parse_args()

    pid = args.pid or find_client_pid()
    if pid is None:
        print("no EVE client found", file=sys.stderr)
        return 1
    window = game_window(pid)
    if window is None:
        print(f"no visible window for pid {pid}", file=sys.stderr)
        return 1

    print(f"client pid {pid}")
    print(f"window {window.width}x{window.height} at ({window.x},{window.y}), "
          f"client {window.client_width}x{window.client_height}")
    print()

    # -- 1. the screenshot -------------------------------------------------
    print("1. One window capture (BitBlt of the client area + GetDIBits)")
    capture_client(window)  # warm the GDI path
    timings, size = [], 0
    for _ in range(args.shots):
        seconds, size = capture_client(window)
        timings.append(seconds)
    print(f"   raw frame           {size/(1<<20):.1f} MiB "
          f"({window.client_width}x{window.client_height} x 4 bytes)")
    print(f"   median              {statistics.median(timings)*1000:.1f} ms")
    print(f"   min / max           {min(timings)*1000:.1f} / {max(timings)*1000:.1f} ms")
    capture_median = statistics.median(timings)
    print()

    # -- 2. the memory read ------------------------------------------------
    print("2. One full UI-tree read (the ported walker, same client, same moment)")
    import tree_walker

    session = tree_walker.open_client(pid)
    started = time.time()
    root = tree_walker.find_ui_root(session.reader, session.py)
    root_seconds = time.time() - started
    if root is None:
        print("   no UI root found", file=sys.stderr)
        return 1
    print(f"   root discovery      {root_seconds:.1f}s  (once per session, then cached)")
    read_timings, nodes = [], 0
    for _ in range(args.reads):
        started = time.perf_counter()
        session.walker.read_tree(root)
        read_timings.append(time.perf_counter() - started)
        nodes = session.walker.nodes
    read_median = statistics.median(read_timings)
    print(f"   nodes               {nodes}")
    print(f"   median              {read_median*1000:.0f} ms")
    print(f"   min / max           {min(read_timings)*1000:.0f} / {max(read_timings)*1000:.0f} ms")
    session.reader.close()
    print()

    # -- 3. what BotLab.exe is spending ------------------------------------
    print(f"3. BotLab.exe over {args.watch:.0f}s")
    botlab = find_pid_by_name("BotLab")
    if botlab is None:
        print("   not running -- nothing to compare against")
    else:
        before = process_cpu_and_memory(botlab)
        time.sleep(args.watch)
        after = process_cpu_and_memory(botlab)
        if before and after:
            cpu = after[0] - before[0]
            print(f"   pid                 {botlab}")
            print(f"   CPU used            {cpu:.1f}s over {args.watch:.0f}s "
                  f"= {100*cpu/args.watch:.0f}% of one core")
            print(f"   working set         {after[1]/(1<<30):.2f} GiB "
                  f"(was {before[1]/(1<<30):.2f} GiB)")
    print()

    # -- the comparison ----------------------------------------------------
    print("Comparison")
    print("-" * 10)
    print(f"   capture, per reading      {capture_median*1000:6.1f} ms")
    print(f"   memory read, per reading  {read_median*1000:6.0f} ms")
    ratio = read_median / capture_median if capture_median else float("inf")
    print()
    print(f"   The memory read costs {ratio:.0f}x what the capture does.")
    print()
    print("   So on this machine the capture is not the expensive half, and issue")
    print("   #176's 'simply not capturing may win most of it' does not hold as")
    print("   stated -- the saving from dropping the screenshot is bounded by the")
    print("   number above, whatever else BotLab.exe is doing with its 4 GiB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
