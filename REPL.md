# Driving the EVE client by hand (`eve_repl.py`)

An interactive handle on the running client, for the one-offs that don't
justify a script: rescuing a ship, unsticking a window, checking what the bot
can actually see, or trying an interaction before writing it into a bot.

```
cd tools/macos-host
python3 -i eve_repl.py
```

```
EVE session: pid 21325, window 9228, canvas 2880x1864 -> 1710x1069 pt (scale 1.684 x 1.744)
`eve` is ready. Try eve.overview(), eve.find('...'), eve.buttons().
```

The scale on that line is measured, not assumed — see *Coordinates* below.

## Before it will attach

- SIP debugging restrictions off, as for everything else here (see `MACOS.md`).
- **A bot must have run at least once since the client launched.** The REPL
  reuses `botlab_host`'s UI-root cache; without it there is nothing to attach
  to, and it will say so rather than guess. The addresses are per-launch, so a
  client restart means running a bot again.

**Neither applies on Windows** — see *On Windows* below, where the pid and the
root are found directly and no bot need ever have run.

## The model

Read a snapshot, act on it, read again. `eve.read()` refreshes; most helpers
refresh for you unless you pass `refresh=False`. A read is about half a second,
so re-reading freely is fine.

## Looking around

```python
eve.overview()                     # rows: (x, y, cells) — only rendered rows are real
eve.windows()                      # open windows by type and caption
eve.grep("Kruul")                  # every node whose text mentions this
eve.of_type("SelectedItemButton")  # nodes by widget type
eve.docked()                       # in station?
eve.objective()                    # the tracked mission's current objective line
```

`eve.objective()` returning `None` means no mission is **tracked**, which is a
real failure mode and not the same as having no mission — see CLAUDE.md.

## Acting on something in space

Everything here is the same pattern: select the overview row, then press a
named button on the Selected Item panel. That is the one interaction on this
client that has worked every time.

```python
eve.dock("Emperor Family Academy")     # select the station, press Dock
eve.warp_to("Amarr - Star")            # get off this grid
eve.jump("Amarr")                      # stargate: warps and jumps in one action
eve.approach("Acceleration Gate")
eve.keep_at_range("Centii Loyal")
eve.activate_gate()                    # defaults to "Acceleration Gate"
eve.undock()
```

Each is `act_on(needle, button)` underneath, which re-finds the row, confirms
the panel is showing it, then presses. To see what a selection offers:

```python
eve.select("Acceleration Gate")
eve.buttons()
# {'selectedItemActivateGate': (2485, 93), 'selectedItemWarpTo': (2465, 93), ...}
eve.panel("selectedItemActivateGate")
```

A gate whose name reads **"(Locked Down)"** will not open until the pocket is
cleared — and approaching it is what spawns the rats that unlock it, so
`eve.approach(...)` is the right move there, not `activate_gate`.

## Rescuing a ship

The sequence that recovered a pod from a mission pocket:

```python
eve.warp_to("Amarr - Star")            # anything at AU range is off this grid
eve.wait_until(lambda: not eve.docked(), timeout=60)
eve.dock("Emperor Family Academy")
eve.wait_until(eve.docked, timeout=300)
```

## Context menus

Right-click, read the entries, click one by label. `menu()` returns
**mid-entry** y coordinates, because the reported y is an entry's top edge and
clicking there hits the entry above.

```python
row = eve.find("Minmatar Plot")
eve.menu(row[0] + 200, row[1] + 12)
# [('Agent: Almananeg Erafeke', ...), ('Start Conversation', ...), ('Track', ...)]
eve.menu_click("Track")
```

That exact sequence is how a mission gets tracked so it appears in the info
panel — without which the mission runner cannot leave the station.

## Windows

```python
eve.close_window("Agency")             # press the window's own Close control
eve.key("alt", "j")                    # Opportunities
eve.key("alt", "c")                    # Inventory
eve.key("escape")
eve.screenshot()                       # by window id, returns the path
```

`screenshot()` captures the game window rather than the screen: the client is
usually on another macOS Space, where a screen grab catches the wrong desktop.

## On Windows

Same commands, same conventions:

```
cd tools/macos-host
python -i eve_repl.py
```

Four call sites dispatch to `tools/windows-host/repl_platform.py` — attach,
window geometry, tree read, input — and everything above them, which is where
every convention in this document lives, is the same code.

Three differences are worth knowing before using it:

- **No bot need have run.** There is no UI-root cache to be stale; the pid and
  the root are found directly, so the repl attaches to a client nobody has
  pointed a bot at.
- **The key names are the same and the codes are not.** `keydown` reaches
  `SendInput` as a Windows virtual key code, and the two encodings collide
  rather than fail — CGKeyCode 53 is Escape while Windows 53 is the `5` key, so
  a shared table would type digits and report that it pressed Escape. `KEYS`
  and `KEYCODE` are swapped wholesale per platform.
- **`screenshot()` raises the window first.** Windows has no Spaces, but
  `BitBlt` copies whatever is actually on top, and a capture of the wrong
  application reads exactly like a capture of the right one.

**Two rules matter more here than the macOS text implies**, because both were
broken while driving a real ship four jumps home and each cost a wrong action:

- **Match a system on the Name column, never the Type.** A gate's Type reads
  `Stargate (Amarr System)`, so `eve.find("Amarr")` matches every gate in the
  constellation. It selected the gate the ship had just come out of and jumped
  it backwards. `eve.select(row)` with a row you chose yourself is the safe
  form; a bare needle is not.
- **Let the route panel settle after a session change.** Read immediately, it
  still names the *previous* hop — which sent the ship at the gate 13 km behind
  it, too close to warp, where it sat until the timeout. And the panel names
  two systems, the destination and the next hop; with markup stripped they are
  the same shape, so identify the next one by its `alt="Next System in Route"`
  attribute rather than by position.

`Jump` works at any distance — the client warps in and jumps on arrival.
`Warp To` lands at the client's preset warp-to distance, which on this account
is 13 km and outside jump range.

## Clicking something awkward

```python
n = eve.node("InfoPanelSearch")
eve.size_of(n)          # (312, 38)
eve.click_node(n)       # centre of it, descending if it has no size of its own
```

## Double clicking

```python
eve.doubleclick(x, y)   # one protocol command, not two clicks
```

Some things the client only opens on a double click and offers nothing at all
on a right click, so this is the only way in — an inventory stack, an asset in a
hangar, and (per CLAUDE.md) an overview wreck, where the client reads a double
click as "Open Cargo" and flies there first if it has to.

**Do not try to fake it with two `down`/`up` pairs.** Each `_cg_send` is its own
round trip through the backend, so the gap between the presses is whatever that
machinery costs rather than the few milliseconds intended. On Windows the
receiving application decides from that gap against `GetDoubleClickTime`, so a
slow pair arrives as two single clicks; macOS is stricter and cannot be faked
here at all, since the second press must carry `kCGMouseEventClickState = 2`.
Both platforms already carried a `doubleclick` verb — `cg_input`'s own on macOS,
`win_platform.command`'s here — and only the repl was missing the method.

**A row that ignores it is telling you something.** A market Sellers row does
not open on a double click and its right-click menu offers only column options
(`Make primary`, `Hide Jumps`), so a specific sell order cannot be bought that
way; the Buy dialog's **Advanced** form is the route. Verified against a live
client, and it cost an evening to find out.

## Coordinates

The client's internal canvas is not screen points, and the ratio is **not** the
Retina backing scale. It is UIRoot's reported size over the window's point
size, per axis, measured on connect — 1.684 × 1.744 on the machine this was
written on, where 2.0 would have been wrong on both axes. `eve.to_screen(x, y)`
does the conversion; the helpers all use it.

Two things the tree does *not* give you:

- **No `totalDisplayRegion`.** Not one node has one — that field is computed by
  the Elm parser, not by `tree_walker`. Sizes are in `dictEntriesOfInterest` as
  `_displayWidth`/`_displayHeight`, which is what `size_of` reads. Any
  `x + region.width / 2` written against this tree silently yields the node's
  top-left corner.
- **Overview rows have no size**, so a row's position is its left edge — the
  icon column, which does not select. The helpers click `NAME_COLUMN` (200)
  into the row, on the name.

## Running it while a bot is running

Safe, and useful: `botlab_host` treats input it did not post itself as a human
at the keyboard and stands down for a few seconds, so you can close a stray
window mid-fight without stopping anything. The log says
`standing down: someone used the mouse/keyboard 3.7s ago`.

That is courtesy, not isolation. Anything that moves the ship will be fought by
the bot as soon as it resumes, so stop the bot first for anything beyond
tidying windows — the same reason `route_setter.py` and `reload_drones.py` are
documented as never-alongside.

## Gotchas worth knowing

- **The overview re-sorts between a read and a click.** `select()` re-finds the
  row each attempt and confirms by name; do the same if you drive clicks
  yourself. Reading a position and clicking it later selected a star instead of
  a station, live.
- **Check nothing is overlaying.** An open Settings window silently swallowed
  two test clicks and produced a confident, wrong conclusion about a keybind.
  `eve.windows()` before concluding a click "didn't work".
- **Verify after acting.** Objective text changed, overview row count changed,
  window gone. Most wrong conclusions come from acting and assuming.
- **Not everything responds to synthetic clicks.** The EVE *launcher's* PLAY
  NOW ignores them entirely; see `MACOS.md`.
