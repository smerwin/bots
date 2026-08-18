"""Grab a window's screen region to a PNG, and say whether it was frontmost.

One implementation, because there were two and they disagreed about the thing
that matters.  ``engagement_watch.py`` had a ``StretchBlt`` downscale, a
24-bit ``GetDIBits`` and a row-sliced PNG encoder; ``shot.py`` in the
scratchpad had a full-size ``BitBlt``, 32 bits, and a per-pixel Python loop
that costs width*height iterations -- 3.8 million of them on this client, for
a picture identical to the one the row slices produce.  Neither is wrong; two
of them is.

**The capture is of the screen region the window occupies, not of the
window.**  ``BitBlt`` from the desktop DC copies whatever is actually on top,
so a window that is behind another yields a perfect screenshot of the wrong
application -- and that picture looks exactly like a good one.  This session
paid for that twice: a launcher capture came back showing the terminal that
was covering it, and the conclusion drawn from it was about the launcher.

So ``frontmost`` is returned rather than assumed, and callers are expected to
do something with it.  ``engagement_watch.py`` renames the file
``_NOTFRONTMOST`` and never raises anything, deliberately -- raising costs a
synthetic ALT, which ``GetLastInputInfo`` cannot tell from a person at the
keyboard, so it would idle the bot for five seconds on every screenshot.  A
tool that is not running beside a bot can instead pass ``raise_first=True``.
"""
import ctypes
import struct
import sys
import zlib
from ctypes import wintypes

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
HALFTONE = 4


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def _png(width, height, rgb_rows):
    def chunk(kind, data):
        body = struct.pack(">I", len(data)) + kind + data
        return body + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rgb_rows), 6))
            + chunk(b"IEND", b""))


def capture_window(win, path, scale=1, raise_first=False):
    """Write the region ``win`` occupies to ``path`` as a PNG.

    ``scale`` is an integer downscale divisor applied by ``StretchBlt`` with
    ``HALFTONE``, so 3 gives a ninth of the pixels -- the bot's own runs use
    that, since a full-resolution grab of this client is ~12 MB and one run
    takes dozens of them.

    ``raise_first`` presses a synthetic ALT.  Never pass it from anything
    running alongside a bot; see the module docstring.
    """
    if raise_first:
        import input as win_input
        win_input.bring_window_to_foreground(win.hwnd, allow_synthetic_alt=True)

    frontmost = _user32.GetForegroundWindow() == win.hwnd
    src_w, src_h = win.width, win.height
    dst_w, dst_h = max(1, src_w // scale), max(1, src_h // scale)

    srcdc = _user32.GetDC(None)
    memdc = _gdi32.CreateCompatibleDC(srcdc)
    bitmap = _gdi32.CreateCompatibleBitmap(srcdc, dst_w, dst_h)
    _gdi32.SelectObject(memdc, bitmap)
    _gdi32.SetStretchBltMode(memdc, HALFTONE)
    _gdi32.StretchBlt(memdc, 0, 0, dst_w, dst_h,
                      srcdc, win.x, win.y, src_w, src_h, SRCCOPY)

    header = _BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    header.biWidth, header.biHeight = dst_w, -dst_h  # negative: top-down
    header.biPlanes, header.biBitCount, header.biCompression = 1, 24, 0
    stride = ((dst_w * 3 + 3) // 4) * 4
    buffer = ctypes.create_string_buffer(stride * dst_h)
    _gdi32.GetDIBits(memdc, bitmap, 0, dst_h, buffer, ctypes.byref(header), 0)

    # BGR -> RGB by slice assignment, one row at a time, with the PNG filter
    # byte in front of each.  A per-pixel loop here is the same picture and
    # about two orders of magnitude slower.
    raw = bytearray()
    for row in range(dst_h):
        raw += b"\x00"
        line = bytearray(buffer[row * stride:row * stride + dst_w * 3])
        line[0::3], line[2::3] = line[2::3], line[0::3]
        raw += line

    with open(path, "wb") as handle:
        handle.write(_png(dst_w, dst_h, raw))

    _gdi32.DeleteObject(bitmap)
    _gdi32.DeleteDC(memdc)
    _user32.ReleaseDC(None, srcdc)
    return frontmost


def main():
    import argparse

    from window_probe import declare_dpi_awareness, windows_of_process

    parser = argparse.ArgumentParser(
        description="screenshot a process's largest visible window to a PNG")
    parser.add_argument("pid", type=int)
    parser.add_argument("out")
    parser.add_argument("--scale", type=int, default=1,
                        help="integer downscale divisor (default 1)")
    parser.add_argument("--raise-first", action="store_true",
                        help="raise the window before grabbing. Presses a "
                             "synthetic ALT -- never use this alongside a "
                             "running bot, which reads it as a human and "
                             "stands down for five seconds.")
    args = parser.parse_args()

    declare_dpi_awareness()
    wins = [w for w in windows_of_process(args.pid)
            if w.visible and w.width > 200 and w.height > 200]
    if not wins:
        return "no visible window for pid %d" % args.pid
    win = max(wins, key=lambda w: w.width * w.height)
    print("window %dx%d at (%d,%d) %r"
          % (win.width, win.height, win.x, win.y, win.title))

    frontmost = capture_window(win, args.out, scale=args.scale,
                               raise_first=args.raise_first)
    print("wrote %s%s" % (args.out,
                          "" if frontmost else
                          "  -- WINDOW WAS NOT FRONTMOST, this is a picture "
                          "of whatever was on top of it"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
