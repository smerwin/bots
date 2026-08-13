"""Read a HOTAS on Windows, and bind its controls to EVE actions by using them.

    python hotas_map.py --watch          # live values, to see what moves what
    python hotas_map.py --map            # bind each action by moving the control
    python hotas_map.py --show           # print the saved map

**This never sends the EVE client anything.** It reads the stick and writes a
JSON map, nothing else. Driving the client is a separate piece with its own
go-ahead, and `HOTAS.md` records why the two must not run beside a bot: the host
stands down for 5 seconds after any human input, so continuous stick input holds
a bot permanently idle. They are alternatives, not companions.

Why `winmm` rather than DirectInput or a package: it needs no COM, no window,
no message loop and no dependency -- ctypes reaches `joyGetPosEx` directly.
Measured against the device here (Thrustmaster, VID_044F): 6 axes, 14 buttons,
one hat, which fits inside the API's limits. Those limits are **six axes, one
hat and 32 buttons**, and a larger HOTAS can exceed the button count -- at which
point this needs Raw Input or DirectInput instead. `--watch` is what says
whether a control is visible at all, so run it before concluding anything is
unbindable.

The binding is **detection-driven and never prompts for a keypress**: it says
what to bind, then watches until that control actually moves. Two reasons. It
is the right feel for a HOTAS -- hands stay on the stick -- and commands here
often run without an interactive stdin, where `input()` reads EOF immediately
and would record whatever happened to be held. `launch_character.py --record`
had the same problem and took the same shape.

An axis binding records which way it was moved, so a driver can tell a pull from
a push without the operator having to know the polarity. A step that sees
nothing within `--step-timeout` is **skipped and said to be skipped**, rather
than left to look bound.
"""
import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

winmm = ctypes.WinDLL("winmm")

MAXPNAMELEN = 32
MAX_JOYSTICKOEMVXDNAME = 260
JOYERR_NOERROR = 0
JOY_RETURNALL = 0x000000FF
JOYCAPS_HASPOV = 0x0001
POV_CENTERED = 0xFFFF

AXES = ("X", "Y", "Z", "R", "U", "V")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MAP = os.path.join(HERE, "hotas_map.json")

# The actions worth binding, from HOTAS.md's own table. `axis` wants a lever or
# a stick travel; `button` wants a press. Nothing here is EVE-specific beyond
# the names -- what each one *does* belongs to the driver, not to the mapper.
DEFAULT_ACTIONS = [
    ("steer-x", "axis", "stick left/right -- steers the ship (double-click in space)"),
    ("steer-y", "axis", "stick forward/back -- steers the ship"),
    ("throttle", "axis", "throttle lever -- fraction of max speed on the SpeedGauge"),
    ("fire-group-1", "button", "weapon group 1 (F1)"),
    ("fire-group-2", "button", "weapon group 2 (F2)"),
    ("fire-group-3", "button", "weapon group 3 (F3)"),
    ("fire-group-4", "button", "weapon group 4 (F4)"),
    ("launch-drones", "button", "launch drones (Shift+F)"),
    ("recall-drones", "button", "recall drones (Shift+R)"),
    ("prop-mod", "button", "propulsion module (Alt+F1) -- a toggle, not a deactivate"),
    ("full-stop", "button", "stop the ship (Ctrl+Space)"),
    ("max-speed", "button", "MaxSpeedButton -- 100% throttle in one click"),
    ("orbit", "button", "orbit the selected object"),
    ("approach", "button", "approach the selected object"),
    ("keep-at-range", "button", "keep at range from the selected object"),
]


class JOYCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("szPname", wintypes.WCHAR * MAXPNAMELEN),
        ("wXmin", wintypes.UINT), ("wXmax", wintypes.UINT),
        ("wYmin", wintypes.UINT), ("wYmax", wintypes.UINT),
        ("wZmin", wintypes.UINT), ("wZmax", wintypes.UINT),
        ("wNumButtons", wintypes.UINT),
        ("wPeriodMin", wintypes.UINT), ("wPeriodMax", wintypes.UINT),
        ("wRmin", wintypes.UINT), ("wRmax", wintypes.UINT),
        ("wUmin", wintypes.UINT), ("wUmax", wintypes.UINT),
        ("wVmin", wintypes.UINT), ("wVmax", wintypes.UINT),
        ("wCaps", wintypes.UINT),
        ("wMaxAxes", wintypes.UINT),
        ("wNumAxes", wintypes.UINT),
        ("wMaxButtons", wintypes.UINT),
        ("szRegKey", wintypes.WCHAR * MAXPNAMELEN),
        ("szOEMVxD", wintypes.WCHAR * MAX_JOYSTICKOEMVXDNAME),
    ]


class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD),
        ("dwZpos", wintypes.DWORD), ("dwRpos", wintypes.DWORD),
        ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
        ("dwButtons", wintypes.DWORD),
        ("dwButtonNumber", wintypes.DWORD),
        ("dwPOV", wintypes.DWORD),
        ("dwReserved1", wintypes.DWORD),
        ("dwReserved2", wintypes.DWORD),
    ]


class Device:
    """One joystick, polled. Axis values are normalised to -1.0 .. +1.0."""

    def __init__(self, index):
        self.index = index
        self.caps = self._caps()
        if self.caps is None:
            raise SystemExit("no joystick at id %d -- try --watch to list" % index)
        self.name = self.caps.szPname
        self.ranges = {
            "X": (self.caps.wXmin, self.caps.wXmax),
            "Y": (self.caps.wYmin, self.caps.wYmax),
            "Z": (self.caps.wZmin, self.caps.wZmax),
            "R": (self.caps.wRmin, self.caps.wRmax),
            "U": (self.caps.wUmin, self.caps.wUmax),
            "V": (self.caps.wVmin, self.caps.wVmax),
        }

    def _caps(self):
        caps = JOYCAPSW()
        if winmm.joyGetDevCapsW(self.index, ctypes.byref(caps),
                                ctypes.sizeof(caps)) != JOYERR_NOERROR:
            return None
        return caps

    def raw(self):
        info = JOYINFOEX()
        info.dwSize = ctypes.sizeof(JOYINFOEX)
        info.dwFlags = JOY_RETURNALL
        if winmm.joyGetPosEx(self.index, ctypes.byref(info)) != JOYERR_NOERROR:
            return None
        return info

    def read(self):
        """{'axes': {name: -1..1}, 'buttons': int, 'hat': int|None} or None."""
        info = self.raw()
        if info is None:
            return None
        values = (info.dwXpos, info.dwYpos, info.dwZpos,
                  info.dwRpos, info.dwUpos, info.dwVpos)
        axes = {}
        for name, value in zip(AXES, values):
            low, high = self.ranges[name]
            span = (high - low) or 1
            axes[name] = (value - low) / float(span) * 2.0 - 1.0
        hat = None
        if self.caps.wCaps & JOYCAPS_HASPOV and info.dwPOV != POV_CENTERED:
            hat = info.dwPOV
        return {"axes": axes, "buttons": info.dwButtons, "hat": hat}


def devices():
    found = []
    for index in range(16):
        info = JOYINFOEX()
        info.dwSize = ctypes.sizeof(JOYINFOEX)
        info.dwFlags = JOY_RETURNALL
        if winmm.joyGetPosEx(index, ctypes.byref(info)) == JOYERR_NOERROR:
            found.append(index)
    return found


def pressed_buttons(mask):
    return [i + 1 for i in range(32) if mask & (1 << i)]


# --------------------------------------------------------------------------
# watch


def watch(device, seconds):
    print("%s -- %d axes, %d buttons, hat %s"
          % (device.name, device.caps.wNumAxes, device.caps.wNumButtons,
             "yes" if device.caps.wCaps & JOYCAPS_HASPOV else "no"))
    print("Move things. Ctrl-C to stop.\n")
    deadline = time.time() + seconds
    axes_shown = AXES[: device.caps.wNumAxes] or AXES
    # Redraw in place only on a terminal. Piped -- which is how this is usually
    # run here -- a carriage return is not a redraw, it is one line per poll,
    # and 6 seconds of it buried the output the first time this ran. Piped, say
    # something only when the reading actually changes.
    interactive = sys.stdout.isatty()
    last = None
    changes = 0
    while time.time() < deadline:
        state = device.read()
        if state is None:
            print("device went away")
            return 1
        axes = "  ".join("%s%+.2f" % (n, state["axes"][n]) for n in axes_shown)
        buttons = pressed_buttons(state["buttons"])
        hat = "-" if state["hat"] is None else "%d" % (state["hat"] // 100)
        line = "%s | hat %-4s | buttons %s" % (
            axes, hat, ",".join(str(b) for b in buttons) if buttons else "-")
        if interactive:
            print("\r" + line.ljust(96), end="", flush=True)
        else:
            coarse = "%s|%s|%s" % (
                " ".join("%+.1f" % state["axes"][n] for n in axes_shown),
                hat, buttons)
            if coarse != last:
                print(line, flush=True)
                last = coarse
                changes += 1
        time.sleep(0.05)
    if interactive:
        print()
    elif changes <= 1:
        print("\nnothing moved in %.0fs -- every axis sat still and no button "
              "was pressed." % seconds)
        print("If you were using the stick, this device id is enumerating but "
              "not carrying its reports.")
    return 0


# --------------------------------------------------------------------------
# binding


def settled(device, samples=6, interval=0.05):
    """A baseline taken once the stick has stopped moving."""
    while True:
        first = device.read()
        if first is None:
            raise SystemExit("device went away")
        steady = True
        for _ in range(samples):
            time.sleep(interval)
            now = device.read()
            if now is None:
                raise SystemExit("device went away")
            if now["buttons"] != first["buttons"] or now["hat"] != first["hat"]:
                steady = False
                break
            for name in AXES:
                if abs(now["axes"][name] - first["axes"][name]) > 0.08:
                    steady = False
                    break
            if not steady:
                break
        if steady:
            return first


def detect(device, base, want, timeout, threshold, confirm=3):
    """Watch until one control moves clearly, and say which.

    `confirm` consecutive agreeing polls, because a lever at rest jitters and a
    single sample would bind the noise rather than the control.
    """
    deadline = time.time() + timeout
    candidate = None
    agreed = 0
    while time.time() < deadline:
        state = device.read()
        if state is None:
            raise SystemExit("device went away")
        found = None
        if want == "axis":
            biggest, moved = 0.0, None
            for name in AXES:
                delta = state["axes"][name] - base["axes"][name]
                if abs(delta) > max(threshold, biggest):
                    biggest, moved = abs(delta), (name, delta)
            if moved:
                found = ("axis", moved[0], "+" if moved[1] > 0 else "-")
        else:
            new = state["buttons"] & ~base["buttons"]
            if new:
                found = ("button", pressed_buttons(new)[0], None)
            elif state["hat"] is not None and base["hat"] is None:
                found = ("hat", state["hat"], None)
        if found is not None and found == candidate:
            agreed += 1
            if agreed >= confirm:
                return found
        else:
            candidate, agreed = found, 1 if found else 0
        time.sleep(0.02)
    return None


def release(device, base, timeout=10.0, threshold=0.25):
    """Wait for the control to come back, so the next step sees a clean slate."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = device.read()
        if state is None:
            return
        quiet = (state["buttons"] & ~base["buttons"]) == 0 and state["hat"] is None
        for name in AXES:
            if abs(state["axes"][name] - base["axes"][name]) > threshold:
                quiet = False
        if quiet:
            return
        time.sleep(0.05)


def describe(binding):
    kind = binding["kind"]
    if kind == "axis":
        return "axis %s (%s)" % (binding["axis"], binding["direction"])
    if kind == "button":
        return "button %d" % binding["button"]
    return "hat %d deg" % (binding["hat"] // 100)


def run_map(device, actions, out_path, timeout, threshold):
    print("%s -- %d axes, %d buttons\n" % (device.name, device.caps.wNumAxes,
                                           device.caps.wNumButtons))
    print("For each action, move the control you want. Nothing is sent to EVE.")
    print("Do nothing for %ds to skip a step.\n" % timeout)

    existing = load_map(out_path)
    bindings = existing.get("bindings", {}) if existing else {}
    bindings = dict(bindings)

    for name, want, blurb in actions:
        base = settled(device)
        print("  %-16s %-52s " % (name, blurb), end="", flush=True)
        found = detect(device, base, want, timeout, threshold)
        if found is None:
            print("skipped")
            continue
        kind, value, direction = found
        if kind == "axis":
            binding = {"kind": "axis", "axis": value, "direction": direction}
        elif kind == "button":
            binding = {"kind": "button", "button": value}
        else:
            binding = {"kind": "hat", "hat": value}
        clash = [k for k, v in bindings.items() if v == binding and k != name]
        bindings[name] = binding
        print(describe(binding) + (
            "   (also bound to %s)" % ", ".join(clash) if clash else ""))
        release(device, base)

    data = {
        "device": {"index": device.index, "name": device.name,
                   "axes": device.caps.wNumAxes,
                   "buttons": device.caps.wNumButtons},
        "bindings": bindings,
    }
    save_map(data, out_path)
    print("\nwrote %d binding(s) to %s" % (len(bindings), out_path))
    for line in problems(bindings):
        print("  ! %s" % line)
    return 0


def load_map(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_map(data, path):
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def problems(bindings):
    """Everything wrong with a map, as sentences.

    A map is read once and then acted on thousands of times, so a control bound
    to two actions is a driver that fires both and an operator who sees one --
    which is this repo's signature failure wearing a different hat. Said here
    rather than left for the driver to discover.
    """
    found = []
    seen = {}
    for name in sorted(bindings):
        key = json.dumps(bindings[name], sort_keys=True)
        seen.setdefault(key, []).append(name)
    for key, names in sorted(seen.items()):
        if len(names) > 1:
            found.append("%s are all bound to %s -- one control, several "
                         "actions, so a driver would fire every one of them"
                         % (", ".join(names), describe(json.loads(key))))
    missing = [n for n, _, _ in DEFAULT_ACTIONS if n not in bindings]
    if missing:
        found.append("not bound: %s" % ", ".join(missing))
    axes = {n: b for n, b in bindings.items() if b.get("kind") == "axis"}
    if "steer-x" in axes and "steer-y" in axes:
        if axes["steer-x"]["axis"] == axes["steer-y"]["axis"]:
            found.append("steer-x and steer-y are the same axis, which cannot "
                         "be right for a two-axis stick")
    return found


def show(path):
    data = load_map(path)
    if data is None:
        print("no map at %s" % path)
        return 1
    device = data.get("device", {})
    print("device %s (id %s)" % (device.get("name", "?"), device.get("index", "?")))
    bindings = data.get("bindings", {})
    for name in sorted(bindings):
        print("  %-16s %s" % (name, describe(bindings[name])))
    found = problems(bindings)
    if found:
        print()
        for line in found:
            print("  ! %s" % line)
        print("\n  Re-run --map --only <names> to fix just those.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Read a HOTAS and bind its controls to EVE actions. "
                    "Sends the EVE client nothing.")
    parser.add_argument("--watch", action="store_true",
                        help="print live axis, button and hat values")
    parser.add_argument("--map", action="store_true",
                        help="bind each action by moving the control")
    parser.add_argument("--show", action="store_true",
                        help="print the saved map")
    parser.add_argument("--device", type=int, default=None,
                        help="joystick id (default: the first that answers)")
    parser.add_argument("--out", default=DEFAULT_MAP, help="map file path")
    parser.add_argument("--only", default="",
                        help="comma-separated action names to bind")
    parser.add_argument("--step-timeout", type=float, default=20.0,
                        help="seconds to wait per action before skipping")
    parser.add_argument("--axis-threshold", type=float, default=0.35,
                        help="axis travel counted as a deliberate move (0-2)")
    parser.add_argument("--seconds", type=float, default=30.0,
                        help="how long --watch runs")
    args = parser.parse_args()

    if args.show:
        return show(args.out)

    available = devices()
    if not available:
        print("no joystick answered joyGetPosEx on ids 0-15.")
        print("winmm only sees devices the legacy joystick driver enumerates;")
        print("a stick that is present but absent here needs Raw Input or")
        print("DirectInput instead.")
        return 1
    index = args.device if args.device is not None else available[0]
    if args.device is None and len(available) > 1:
        print("several joysticks answered (%s); using %d -- pass --device to pick"
              % (", ".join(str(i) for i in available), index))
    device = Device(index)

    if args.watch:
        return watch(device, args.seconds)
    if args.map:
        actions = DEFAULT_ACTIONS
        if args.only:
            wanted = [n.strip() for n in args.only.split(",") if n.strip()]
            actions = [a for a in DEFAULT_ACTIONS if a[0] in wanted]
            unknown = set(wanted) - {a[0] for a in DEFAULT_ACTIONS}
            if unknown:
                parser.error("unknown action(s): %s" % ", ".join(sorted(unknown)))
        return run_map(device, actions, args.out, args.step_timeout,
                       args.axis_threshold)
    parser.error("give --watch, --map or --show")


if __name__ == "__main__":
    sys.exit(main())
