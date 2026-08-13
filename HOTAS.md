# Flying EVE with a HOTAS, through `eve_repl`

A sketch, not an implementation. Pinned here so the groundwork found while
building the bot is not rediscovered later.

The idea: bind a flight stick and throttle to the client, using the same
machinery the bot uses to click. This is a *human* control scheme rather than
automation — every input originates from a hand on a stick — but it travels the
same synthetic-input path, so the same caveats apply as everything else in this
repo.

## Why it is mostly already built

`eve_repl` owns the two halves that are actually hard:

- **Canvas-to-screen calibration.** `Session._calibrate()` derives
  `scale_x`/`scale_y` from UIRoot's own reported size against the real window,
  every session, and `to_screen()` applies it along with the window origin. That
  is what turns "40% along the speed bar" into a screen point that lands.
- **A persistent `cg_input`.** One long-lived process for the whole session,
  which matters because it tracks click position as process-local state — a
  fresh process per command clicks at (0, 0).

What is missing is only the input side: read the HID device (IOKit / Game
Controller framework, or `hidapi` from Python) and map it. No new client
knowledge is required.

**On Windows that half is now built, and it needed less than this sketch
assumed** — see "The Windows side" below.

## The mapping

EVE is not a flight sim, and that shapes everything. There is no pitch/yaw
axis, no analog turn rate. Ship control is command-based — approach, orbit,
keep-at-range, align, warp. Most of a HOTAS has nothing to bind to.

Three things do map, and between them they cover the axes:

| control | maps to | how |
|---|---|---|
| stick X/Y | manual flight | direction vector → a screen point offset from centre → `doubleclick`. This is how manual piloting genuinely works in EVE: double-click in space and the ship steers there. `cg_input` has a dedicated `doubleclick` because macOS needs `kCGMouseEventClickState = 2` — two plain clicks are not a double click |
| throttle | fraction of max speed | click along the `SpeedGauge` widget. Measured live: canvas (1379, 1799), 124×36, reading `295 m/s` as text. So `x = 1379 + fraction × 124`, through `to_screen()`. `MaxSpeedButton` sits beside it at (1480, 1791), 12×12 — one click for 100%, no arithmetic |
| buttons / hats | everything else | `F1`–`F4` weapon groups, `Shift+F` launch drones, `Shift+R` recall, `Alt+F1` prop mod (a *toggle*, not a "deactivate"), `Ctrl+Space` stop, and `eve_repl`'s semantic verbs — `orbit()`, `keep_at_range()`, `approach()`, `dock()`, `activate_gate()` |

Coordinates are per-layout: re-derive them from a capture rather than trusting
the numbers above.

## Constraints that would bite

**Never read the UI tree on the input path.** A `tree_walker` read is ~0.4s on a
small tree and seconds on a docked one. That is fine for the bot's multi-second
tick and unusable for a trigger pull. Keypresses and the steering double-click
need no read at all, so they are instant. Only the name-based verbs
(`dock("Emperor Family Academy")`) need a tree, and those belong on a button
pressed once — never polled.

**Rate-limit the throttle axis.** A physical lever moves continuously and would
otherwise emit a click per poll. This client dislikes repeated identical input:
see the hover flap in CLAUDE.md, where re-issuing the same move every tick reset
the dwell timer and produced an endless open/close cycle, and the module-toggle
bug where a second click before the first registered turned the module back off.
Quantise to a few percent of travel and click only on meaningful change.

**The gauge is readable, so the loop can be closed.** `SpeedGauge` carries its
value as text (`295 m/s`). A driver can compare actual against commanded and
notice a click that did not take, rather than running open-loop. Worth doing —
"the input was accepted" is exactly the assumption that fails silently
everywhere else in this project.

**It cannot share the client with the bot.** The host skips any input sequence
if a human used the mouse or keyboard within `HUMAN_INPUT_STAND_DOWN_SECONDS`
(5.0). A HOTAS driving continuously would hold the bot in permanent stand-down.
That is the right outcome — the two are alternatives, not companions — but it
should be a deliberate choice rather than a surprise.

## The Windows side

**The stick is read, and `eve_repl` turns out not to be the prerequisite.** The
two halves this document calls hard both exist on the Windows host already, and
neither is in `eve_repl`:

| this sketch wants | Windows equivalent |
|---|---|
| `Session._calibrate()`'s scale | `window_probe.py` plus UIRoot's own reported canvas size |
| a persistent `cg_input` | `input.py`'s `WindowsInput`, which is in-process — there is no per-command launch, so the `(0, 0)` trap that forces persistence on macOS does not exist |
| `doubleclick` with `kCGMouseEventClickState = 2` | not needed. That is a macOS requirement; two `SendInput` clicks inside the double-click interval *are* a double click |

So `eve_repl`'s port (#192) is wanted only for the name-based verbs —
`dock("Emperor Family Academy")` and friends — which this document already says
belong on a button pressed once and never polled.

`tools/windows-host/hotas_map.py` is the input half: `--watch` for live values,
`--map` to bind an action by moving the control that should drive it, `--show`
to read the map back. **It sends the client nothing.**

`winmm`'s `joyGetPosEx` is what it reads, over DirectInput or a package,
because it needs no COM, no window, no message loop and no dependency. Its
ceilings are **six axes, one hat and 32 buttons**, which a larger HOTAS can
exceed — at which point this needs Raw Input instead, and `--watch` is what says
so. Measured on the Thrustmaster here (VID_044F): one combined device at id 0,
**6 axes, 14 buttons, one hat**, comfortably inside those limits.

Two things it does that are about this repo rather than about joysticks.
Binding is **detection-driven and never waits on a keypress** — it names an
action and watches until that control moves — because a HOTAS operator's hands
are on the stick, and because commands here often run with no interactive
stdin, where `input()` reads EOF and would bind whatever was held. And `--show`
**reports what is wrong with a map**: a control bound to two actions, an axis
bound to both steering axes, anything unbound. A driver reading such a map fires
two actions where the operator saw one, which is this repo's signature failure
in a new place.

## Status

**The input half is implemented on Windows** (above) and nothing drives the
client yet. The mapping table and the client-side facts below it remain a
sketch.

The client-side facts were measured live on 2026-08-02 during run 5 and are the
parts most likely to be wrong later: widget positions move with layout, and
`SpeedGauge`/`MaxSpeedButton` type names are the stable handles rather than the
coordinates.

The first real map made here says something worth knowing before the driver is
written: the buttons bound cleanly and **the axes did not**. `steer-x` captured
axis `U` and `steer-y` captured axis `X`, which is not the pairing a two-axis
stick should give, and the throttle bound to nothing at all. The mapper picks
the axis with the largest deflection, so a stick that rocks a second axis while
being pushed can be captured wrong. Re-run `--map --only steer-x,steer-y,throttle`
and move one axis at a time; the driver should not be built on an axis map
nobody has checked.
