# Project: macOS-native EVE Online bot host (no BotLab.exe / reactor.botlab.org)

## Goal

A macOS-native replacement for the closed-source `BotLab.exe` "volatile host"
so the existing Elm bot programs in `implement/applications/eve-online/`
(mining bot, saxrat combat-anomaly bot, warp-to-0 autopilot, wingus) run on
Apple Silicon without the Windows client and without reactor.botlab.org
(BotLab's paid licensing backend). Non-commercial, not for distribution.

**Status: done and working.** The host runs unmodified Elm bot source
end-to-end against the live game client — real memory reads, real decisions,
real mouse/keyboard input. Remaining work is refinement (see "Open gaps"),
not architecture.

## Architecture

The Elm bot code never touches memory directly — it talks to a "volatile
host" via a small JSON protocol (`EveOnline/VolatileProcessInterface.elm`,
`EveOnline/MemoryReading.elm`): `ListGameClientProcessesRequest`,
`SearchUIRootAddress`, `ReadFromWindow` → a generic `UITreeNode` tree
(`pythonObjectAddress`, `pythonObjectTypeName`, `dictEntriesOfInterest`,
`children`). This shape comes from the open-source **Sanderling** project,
which `BotLab.exe` wraps on Windows. Since the protocol is OS-agnostic, a
macOS host that emits the same JSON and executes the same mouse/key effects
runs the existing ~8,500 lines of bot logic (`Bot.elm`, `ParseUserInterface.elm`,
`BotFramework.elm`) completely unmodified.

BotLab.exe's own toolchain ("Pine", a custom Elm interpreter) isn't needed
either: a bot's `botMain : InterfaceToHost.BotConfig State` is a plain Elm
value compilable with vanilla `elm make`. `tools/macos-host/botlab_host/Main.elm`
is a small port-wrapper (copied alongside fetched bot source, not part of it)
that turns `botMain` into a `Platform.worker` with hand-written JSON
encoders/decoders for the host-interface types. Only
`EveOnline.VolatileProcessInterface`'s codecs (used *inside* the opaque
`RequestToVolatileProcess.request : String` field) must match the real
protocol exactly, since that's unmodified bot source. On Windows, BotLab.exe
runs the bot's `EveOnline/VolatileProcess.csx` as a real C# child process for
this sub-protocol — we don't run that at all; our host fakes being a
competent volatile process entirely in Python, dispatching the parsed inner
JSON to our own macOS memory-reading tools.

Two protocol details worth remembering: `ReadFromWindowResult.Completed
.memoryReadingSerialRepresentationJson` is `Maybe String` — the UI tree JSON
is **double-encoded** (a JSON string containing JSON), decoded downstream via
`decodeMemoryReadingFromString`. And the main operating loop issues **two
parallel reads per cycle** — the memory-based `ReadFromWindow` *and* an
`InvokeMethodOnWindowRequest ReadFromWindowMethod` (screenshot-based, returns
`windowRect`/`clientRect`/`clientRectLeftUpperToScreen`/`imageData`) — the
latter supplies the rect used to translate memory-read UI positions into
absolute screen coordinates for effects, so both are needed, not just the
memory read.

The native Apple Silicon client (`~/Library/Application Support/EVE
Online/SharedCache/tq/EVE.app/.../bin64/exefile`, launched via the separate
Electron launcher app) is a real Metal build, not Wine — but it still embeds
a **Python 2** interpreter for UI/game logic (confirmed via `.so` names like
`_ctypes.so`, and later via struct RE — Python 2's `int`/`long` and
`str`/`unicode` splits are both present). The "walk the CPython object graph"
approach Sanderling uses on Windows applies here too, with different (RE'd
from scratch) struct offsets.

## Memory access: SIP must have Debugging Restrictions disabled

`task_for_pid`/`ptrace` against a target lacking `get-task-allow` (this game
binary) is blocked by SIP's Debugging Restrictions component — not
bypassable via entitlements, Developer Mode, or Developer Tools TCC. Fixed by
booting into Recovery Mode and running `csrutil enable --without debug`.
Current status: `csrutil status` → "Custom Configuration", "Debugging
Restrictions: disabled", everything else still enabled. **This is a
standing, system-wide reduction**, not scoped to this project — revert via
Recovery Mode + plain `csrutil enable` if ever needed.

## CPython struct layouts (this build, arm64, Python 2 semantics)

All addresses below are per-process-launch (ASLR) — re-derive each session,
never hardcode. The one process-independent invariant: **any valid
`PyTypeObject` has `ob_type` pointing at the `type` metaclass itself**
(`type(type) is type`) — the classifier in `re_helper.py` uses this to name
any pointer generically without per-class special-casing.

- **`PyObject` header** (stock): `ob_refcnt` `+0x00`, `ob_type` `+0x08`.
- **`PyTypeObject`** (stock): header + `ob_size` `+0x10`, `tp_name` `+0x18`
  (plain `const char*`).
- **Widget/engine-object wrapper** (the "Blue" C-extension binding layer,
  e.g. `User`, `HangarLayer`, every UI widget): 32 bytes — header +
  `dict_ptr` `+0x10` + `weakref_slot` `+0x18`. No `__dict__` in the stock
  sense; real state lives behind `dict_ptr`, which points at:
- **Custom dict** (not stock `PyDictObject`): header is `0x38` (56) bytes
  with 8 inline entries — `refcnt` `+0x00`, `ob_type` `+0x08` (real `dict`
  type), two duplicate `Py_ssize_t`-ish fields `+0x10`/`+0x18`, capacity
  mask `+0x20`, overflow-table pointer `+0x28` (populated once entries
  exceed the inline capacity), shared/constant vtable-ish pointer `+0x30`
  (identical across every dict instance — literal ARM64 code, not data).
  Entries are 24 bytes each (`hash: 8, key_ptr: 8, value_ptr: 8`), `key_ptr`
  always a `str`. Inline and overflow blocks can hold duplicate/stale
  copies of the same key — dedupe by key pointer; `re_helper.py` and
  `tree_walker.c` both use **last-wins** for ordinary attributes and
  **first-wins** for the `'children'` key specifically (preserves an old,
  never-fully-explained behavioral quirk rather than picking a new policy).
- **`PyASCIIObject`** (compact-ASCII `str`): header + `length` `+0x10` +
  cached `hash` `+0x18` + 4-byte state field + raw ASCII bytes at `+0x24`.
- **`PyIntObject`** (Python 2 `int`/`bool`): header + signed 8-byte
  `ob_ival` at `+0x10`. No arbitrary precision.
- **`PyLongObject`** (Python 2 `long`, a genuinely separate type from
  `int`): header + `ob_size` `+0x10` (digit count + sign) + a digit array
  at `+0x18`, each digit a 4-byte value `< 2^30`. Value =
  `sum(digit[i] * (2**30)**i)`, negated if `ob_size < 0`. Accumulate in
  ≥128-bit precision (a plain `double` loses precision above 2^53, which
  real in-game timestamps exceed).
- **`PyUnicodeObject`** (Python 2 `unicode`, separate from `str`): header +
  `length` `+0x10` + pointer to an externally-allocated **UCS-4** buffer
  `+0x18` + `hash` `+0x20`.
- **Stock `PyListObject`**: header + `ob_size` `+0x10` + `ob_item` `+0x18`
  (flat array of `ob_size` pointers) + `allocated` `+0x20`.
- **`PyWeakReference`**: header + `wr_object` `+0x10` (points back to the
  referent) + `wr_callback` `+0x18` (`NULL` in every case seen).

## UI tree walk (widget → children → JSON)

1. Widget wrapper → `dict_ptr` (`+0x10`) → custom dict → look up `'children'`.
2. That value is a `PyChildrenList` wrapper (same 32-byte shape) → its own
   `dict_ptr` → look up `'_childrenObjects'`.
3. That value is a **stock** `PyListObject` → `ob_item` array of child
   wrapper pointers → recurse from step 1.

Step 3's value is **not always a stock list on the first hop** — some
widgets nest one children-list wrapper inside another, so
`_childrenObjects` yields a second wrapper that has its own
`_childrenObjects`. Confirmed live on `ButtonGroup` (the Accept/Decline/
Delay/Track row in an agent conversation): `ButtonGroup.children` →
`ButtonGroupChildrenList._childrenObjects` → `PyChildrenList._childrenObjects`
→ stock `list`. Bailing out at the first non-`list` (what both walkers
originally did) made every such subtree read as *childless*, so the agent
dialogue's buttons were invisible to the bot while plainly rendered on
screen — a silent wrong answer, not an error. `tree_walker.c`'s
`get_children_addrs` now unwraps repeatedly (bounded by
`MAX_CHILDREN_UNWRAP`) until it reaches a stock list. `re_helper.py`'s
`get_children_addrs_from_wrapper` still has the old single-hop behaviour;
fix it there too if a Python-path walk ever needs these subtrees.

Dead end, don't retry: `PyChildrenList+0x20`/`+0x28` look like a linked
list but are CPython's own GC-tracked-object list (every GC object is
threaded into one process-wide cycle-detection list) — unrelated to actual
content.

**Root discovery** (`re_helper.find_ui_root`): regex-scan a full memory dump
for EVE's own debug-log repr text, `<ClassName object at 0X[hex]>` (a
scannable ring buffer — `re.finditer` directly against the `mmap`, no need
to load the file). This embeds live object addresses directly, sidestepping
any need for a memory pattern scan. Walk `_parentRef` (a weakref to the
parent) upward via `wr_object` until an object with no `_parentRef` key is
reached — that's `UIRoot`/`'Desktop'`. Guard: `_parentRef` can be present
but hold the actual `None` singleton (some containers sit directly under
root) — check the value is genuinely weakref-typed before dereferencing
`+0x10`, or you silently walk to garbage. Also try multiple repr-scan seeds
and prefer one whose own class is literally `UIRoot`, or take whichever
address the most seeds converge on — a single seed can be a dead-end
subtree (e.g. a popped-out window) whose `_parentRef` chain never reaches
the real root.

**Seed/metatype bootstrap gotcha (hit repeatedly, in three different
tools):** don't trust the *first* repr-scan hit to derive the metatype
pointer. The debug-log text can reference an object that's since been
destroyed/reallocated (UI widgets churn constantly), so `find_metatype` on
a stale address can return garbage or `None` even though the same dump has
plenty of valid candidates. Always scan up to ~200 hits and validate each
via the `type(type) is type` invariant before accepting one. Fixed in
`botlab_host.py`'s `_any_seed_addr`, `reload_drones.py`, and
`route_setter.py`'s `find_valid_seed_addr` — if a new tool needs this,
reuse the same validated-scan pattern, don't re-introduce the shortcut.

Two more real bugs from early live runs, worth knowing if either symptom
recurs: (1) the custom dict's `str`-type bootstrap can't blindly read a
fixed inline slot — it's a sparse hash table, slot 0 being empty is common;
must walk entries to find *any* real key. (2) a host's main loop must not
process only the *first* task in a response's `startTasks` — a real
per-cycle read offers several at once (memory read + screenshot read
together) and later responses can offer genuinely new tasks too (e.g. the
`SearchUIRootAddress` → `ReadFromWindow` transition) — drain a queue keyed
by `taskId`, extended from every response, until empty.

## Tools (`tools/macos-host/`)

| path | purpose |
|---|---|
| `probe/` | minimal `task_for_pid` feasibility check |
| `memory_sample/` + `save_process_sample.sh` | full process memory dump + `regions.tsv` index + correlated screenshot, for one-off RE |
| `re_helper/re_helper.py` | Python RE tool/library — `dump`/`find`/`walkdict`/`tree` CLI, plus reusable decoders (`read_pystr`, `read_pyint`, `read_pylong`, `read_pyunicode`, `read_pyfloat`, `classify`, `get_dict`, `walk_dict_entries`, `dict_items`, `build_tree`, `repr_scan`, `find_metatype`, `walk_to_root`, `find_ui_root`). Works against a dump (`Sample`) or a live process (`LiveSample`) interchangeably. |
| `live_reader/` | persistent live memory-read helper (binary protocol over stdin/stdout), backs `LiveSample` |
| `tree_walker/` | C rewrite of the entire UI-tree-walk hot path (memory read + struct decode + tree assembly, no per-field pipe protocol) — ~5x faster than the Python live path (~0.4-0.5s vs ~2s for a ~2,800-node tree); what `botlab_host.py` actually uses for `ReadFromWindow` |
| `window_probe/` | window enumeration via `CGWindowList` (bounds in points, backing scale); `--all` sees windows on any macOS Space, not just the active one |
| `cg_input/` | persistent `CGEventPost`-based input executor, one text command per stdin line (`move`/`down`/`up`/`drag`/`keydown`/`keyup`/`scroll`) |
| `botlab_host/botlab_host.py` | the actual BotLab.exe replacement — fetches bot source (GitHub URL or local path), patches `elm-version`, compiles with `Main.elm`, drives the compiled bot via `driver.js`, dispatches every `Task` type |
| `botlab_host/Main.elm`, `driver.js` | port wrapper + Node bridge (newline-delimited JSON) between the Python host and the compiled bot |
| `run_saxrat.sh` | launcher for `eve-online-saxrat` with sensible settings; one-bot-at-a-time guard (kills any prior `run_saxrat.sh`/`botlab_host.py`/`driver.js`/`tree_walker` before starting) |
| `reload_drones.py` | standalone one-off: refill drone bay from station hangar |
| `route_setter/route_setter.py` | standalone one-off: set the autopilot route from a chat channel's MOTD (see below) |

**Bot source acquisition** (both forms tested working): a local file/directory
path (or `file://`), or a GitHub URL — either a plain repo or a
`.../tree/<branch>/<subpath>` URL (needed since apps in *this* repo live
under `implement/applications/...`, not the repo root) via
`git clone --depth 1 --branch <branch>`. Both then search recursively for
`Bot.elm` if not found directly at the given location.

**Important:** `route_setter.py` and `reload_drones.py` are standalone
scripts that drive real input directly — they are **not** part of the bot
loop and must never run concurrently with a `run_saxrat.sh` session (both
fight for the same mouse/keyboard, producing chaotic, hard-to-diagnose
results — confirmed live: a stray saxrat run running unnoticed in the
background was the real cause of a long, confusing debugging detour).
Always confirm nothing else is running (`pgrep -f` the same patterns
`run_saxrat.sh`'s guard uses) before starting either.

## Coordinates and input execution

The game's internal UI coordinates (`_displayX`/`_displayY`/etc.) are laid
out against `UIRoot`'s own reported virtual-canvas size
(`_displayWidth`/`_displayHeight`), **not** a fixed Retina backing-scale
factor — self-calibrate `scale_x`/`scale_y = UIRoot's reported size / real
window point size` (from `window_probe`) every session; don't assume 2.0.
`cg_input` wants real screen points (confirmed via a `CGEventGetLocation`
round-trip: commanding a move to `(10,10)` reads back exactly `(10.0,
10.0)`, no backing-pixel conversion needed at that layer — the scale
mismatch is entirely in what the *bot* computes upstream, which is why the
fix lives in `ReadFromWindowMethod`'s reported rect and `_windows_input`'s
outbound conversion, not in `cg_input` itself). Windows virtual-key codes
(`Common/EffectOnWindow.elm`'s `vkey_*`) need an explicit lookup table to
macOS `CGKeyCode`s (`_VK_TO_CGKEYCODE` in `botlab_host.py`) — neither side
is contiguous for letters/digits, so no arithmetic mapping works.

**In-game hotkeys worth using instead of a context-menu cascade** (this
account's bindings, all confirmed live): `Shift+F` launches drones from the
bay, `F` engages the current target with them, `Shift+R` recalls them,
`Alt+F1` toggles the propulsion module, `F1`–`F4` are weapon slots 1-4. A
keypress is one effect where the equivalent cascade is a multi-tick
right-click → hover → click sequence with its own retry/discard logic, so
prefer the hotkey wherever one exists. Drones must be recalled before
taking an acceleration gate or they are left behind in the old pocket.

`window_bounds()`-style window resolution must pick the **largest** window
by area for a given pid, not the first one over a width threshold — a
fullscreen game window can have a smaller same-width overlay (the
reveal-on-hover menu-bar strip, ~1710×44) that a naive width check picks by
accident, producing a badly wrong y-scale and bogus click targets. Fixed in
`botlab_host.py`'s `find_eve_processes` (was already correct there),
`reload_drones.py`, and `route_setter.py`. `window_probe --all`
(`kCGWindowListOptionAll`) is what makes this reliable regardless of which
macOS Space the game's fullscreen window is on — the on-screen-only query
sees nothing for it when that Space isn't currently active.

`cg_input` must stay a **single persistent process** across an entire
move→down→up sequence — it tracks click position as process-local state set
by the last `move`; spawning a fresh process per command always clicks at
`(0, 0)` (looks exactly like the OS cursor teleporting to the top-left
corner).

Mouse moves should glide through a few intermediate points rather than
teleport (`botlab_host.py`'s `_move_mouse_eased`) — Photon UI evidently
cares about real cursor trajectories, not just final position, for more
than one kind of gesture (matches `reload_drones.py`'s earlier, independent
finding that drag recognition needs the same treatment). But **don't
re-issue an identical move** if the cursor is already at the target — a
hover-triggered flyout submenu needs sustained, *uninterrupted* dwell to
expand, and re-gliding to the same spot every decision tick (even from
itself to itself) can reset that dwell timer before it ever accumulates
enough, producing an endless "flapping" open/close retry loop that looks
like a hard failure but is actually just this.

`BringWindowToForeground` should check `_window_is_onscreen()` first and
skip the activate-and-sleep entirely if already there — it's prepended to
*every* input sequence by `BotFramework.elm`, so the common case is "already
frontmost," and paying an unconditional `osascript` + sleep there was the
real source of felt input sluggishness. Similarly, don't re-verify the
target window is still onscreen before *every individual* action in a
sequence (that can't meaningfully change between two `CGEventPost` calls a
few ms apart) — only at the sequence's own `BringWindowToForeground`/
`AbortIfWindowNotInForeground` checkpoints.

## Context-menu cascade robustness

`EveOnline.BotFrameworkSeparatingMemory.elm`'s shared cascade-follow logic
(`useContextMenuCascadeWithCustomConfig`) discards and reopens a context
menu if it looks unchanged across a lookback window of prior readings —
needs real patience for a hover-triggered Photon UI flyout to render
(currently 8 ticks; was 3, then 4, widened each time real cascades were
found giving up too early). `discardContextMenuIfTooDistantFromTargetElement`'s
distance tolerance is per-cascade-tunable via `useContextMenuCascadeWithCustomConfig`
— the shared default (70px) isn't enough for every element; the route-jump
icon and the locked-target-bar "unlock" icon both needed 200px.

`beginCascade`'s fallback for "target fully occluded by an existing menu"
should press **Escape** to dismiss it, not right-click a computed "empty
space" location — that location isn't reliably empty (can land on a real
Neocom icon), and whatever it accidentally opens can then sit in the way
of the *next* click, hitting an unrelated button. Confirmed live: this is
what caused an accidental "Clear All Waypoints" on a real autopilot route.

`Bot.elm`'s own `clearStrayContextMenu` (saxrat-specific) presses Escape if
a context menu has sat at the same depth, byte-for-byte unchanged, for 3+
consecutive ticks — catches a stray menu left open on a tick where the
decision tree isn't otherwise touching menu logic at all (the cascade's own
"no progress" recovery only runs while it's actively driving a cascade).

## Elm toolchain

`brew install elm` (arm64-native bottle) — **not** `npm install -g elm`,
which either grabs an unrelated package squatting the name or, pinned to
`elm@0.19.1`, fails on a broken arm64 download URL. Homebrew's build
self-reports `0.19.2`; every bot's checked-in `elm.json` says `"0.19.1"`
(application-type `elm.json` requires an *exact* version match) — patch
`elm-version` to `"0.19.2"` in a **working copy** before compiling, never
in the checked-in source. `botlab_host.py` does this automatically (not yet
automated: bootstrapping `elm` itself if it's missing from `PATH`).

## Screenshot / pixel data

Opt-in (`--capture-screenshots`, off by default — costs ~1.6s/cycle,
dominated by the `screencapture` CLI call, and most bots never read pixel
data at all). Format, reverse-engineered from `BotFramework.elm` source, not
guessed: `pixelsString` is a plain JSON array of `0x00RRGGBB` ints
(red<<16|green<<8|blue), row-major, height implied by `array length /
widthPixels`. `ImageCrop.offset` is in the same self-calibrated "game pixel"
units as `clientRectLeftUpperToScreen` for `_original` crops, but
pre-divided by the binning factor for `_binned_2x2`/`_binned_4x4`. All three
resolutions are genuine area-averaged downsamples of one capture (PIL's
`Image.BOX` filter — a true block-average, unlike a resize filter which
would blur). Pack with vectorized numpy
(`(arr[:,:,0]<<16)|(arr[:,:,1]<<8)|arr[:,:,2]`), not a per-pixel Python loop
— the naive fallback (triggered if `numpy` isn't installed) cost 5.2 of
8.2 total seconds on its own. `_original` is generated empty (`[]`, valid
per the type) by default since a full-resolution Retina crop packs to
~66MB of JSON text and `eve-online-warp-to-0-autopilot` never reads
`pixels_1x1` anyway — re-enable per-bot if one that actually reads it shows
up (the code to build it still exists, just isn't called).

## Current status

- **Memory reading, root discovery, UI tree walk:** fully working, fast
  (native `tree_walker`).
- **Input execution:** working (`cg_input`), gated behind `--execute-input`.
- **Full bot loop:** proven end-to-end for `eve-online-saxrat` and
  `eve-online-warp-to-0-autopilot`, from both a local path and a GitHub URL.
  `eve-online-mining-bot` still compiles (older host-interface version,
  untouched). `eve-online-wingus` exists on disk, untracked/unexplored.
- **saxrat-specific behavior:** deactivates the prop mod (Alt+F1) before
  warping; F1-F4 hotkeys for the first four weapon slots; clears a stray
  context menu that's sat open unchanged for 3+ ticks (Escape); force-closes
  a loot window that hasn't closed on its own after 2 ticks past clicking
  "Loot All" (Ctrl+W); anomaly route-setting waits for a matching anomaly
  and correctly resumes combat/looting even if the anomaly's own signature
  drops off the probe scanner mid-fight, as long as there's still something
  to attack or loot on grid; `run_saxrat.sh` currently filters to Sansha
  sites only.
- **`route_setter.py`:** works — reads a chat channel's MOTD, parses the
  embedded `showinfo:5//<systemID>` system links (tag-stripped, so a
  malformed link like `Sizamo</loc>d` still recovers as `"Sizamod"`),
  right-clicks each in the packed rich text, and picks "Set Destination"
  (first) / "Add Waypoint" (rest) from the resulting menu, self-verifying
  each click via the menu's own "Avoid X (Solar System)" text before
  committing. Genuinely fragile compared to the main bot loop (see next
  section) but functional; not part of the bot loop, run it standalone.
- **ESI (official API) — not viable for this user:** `POST
  /ui/autopilot/waypoint/` would be the correct, reliable way to set a
  route, but registering a developer app now requires a real-money EVE
  Store purchase, which conflicts with this user's stated no-spend policy.
  Sticking with UI automation.

## `route_setter.py` internals worth knowing before touching it again

Locating a specific system-name link inside the MOTD's packed rich text
(not a separately-addressable UI node — the whole block is one `Label`'s
`_setText`) needed several rounds of fixing, all live-verified:

- **Search must be able to steer both directions.** A miss's correction
  needs the full route's ordering (`route_names`/`target_index`) to jump by
  the *signed* line-count difference — a one-line-down-only fallback gets
  permanently stuck once it overshoots (confirmed: overshot "Ana", kept
  hitting later and later entries with no way back up).
- **The "landed on blank space" fallback must nudge in the last real
  steering direction, not always down** — otherwise a correct upward
  correction can be immediately undone by the very next attempt landing in
  an inter-line gap and nudging back down, producing an oscillation that
  looks identical to "stuck" (reports the same y and the same wrong hit
  twice in a row).
- **x-candidates need multiple values, not one.** Short names (e.g. "Nalu")
  don't extend as far right as a single fixed x; double-digit line numbers
  ("10." onward) have a wider prefix than single digits, shifting where the
  name text actually starts. Current list: `(30, 45, 60, 90, 120, 150,
  180)`.
- **The x-scan must not stop at the first non-empty menu.** Right-clicking
  plain text (e.g. a line's own "10." prefix) returns a real but useless
  "Copy | Copy All" menu — treating that the same as "found a real link"
  aborted the x-scan for that row on the very first x tried, every time.
- **`close_menu()` must verify the menu actually closed**, not just sleep a
  fixed delay after Escape — otherwise the next right-click (at a newly
  corrected position) can land while the old menu is still open/closing,
  silently re-reading stale state instead of a fresh attempt.
- EVE's "Search for anything" bar does **not** produce a readable results
  list in memory from simple type+Enter (tested as one continuous input
  sequence, with generous waits, both with and without a trailing hard
  Return) — swept the whole UI tree afterward for anything matching
  "search"/"result" in its type name and found nothing new. Not pursued
  further as a route-setting mechanism; if revisited, this needs real RE
  (screenshot-driven, watching exactly what UI element appears) rather than
  more blind polling.
- "Set Destination" replaces the *entire* route, not just the first stop —
  useful for recovering from a route that's drifted into an unexpected
  state (e.g. from manual play or a stray concurrent bot session): clicking
  "Set Destination" on the next intended system is a clean reset, no
  separate "clear" step needed first.

## Open gaps

- `dictEntriesOfInterest` doesn't recursively encode non-primitive
  "interesting" values the way Sanderling's original serialization does —
  `getDisplayText` in `ParseUserInterface.elm` falls back to decoding a
  non-string `_setText`/`_text` value as *another full `UITreeNode`* (a
  documented real case: it can hold a Python `Link` object whose own
  `_text` has the actual text). Symptom seen live: a bot printing "current
  solar system: Unknown" for a name field that isn't a plain string in
  memory. Not yet fixed.
- `MouseMoveRelative` and `CharacterDown`/`CharacterUp` (raw Unicode text
  input) aren't implemented in `botlab_host.py`.
- No automated Elm-toolchain bootstrap if `elm` isn't already on `PATH`.
- `reload_drones.py` only searches the root Item hangar, no sub-folders.
- Only tested against a handful of bot apps and one machine's display
  configuration (single display, specific Retina scale); non-EVE bots using
  `OpenWindowRequest`/browser automation are stubbed to always fail.
- A bot's own baked-in pacing (e.g. saxrat's explicit 2-second
  `setMillisecondsToNextReadingFromGameBase` override in its own `Bot.elm`)
  dominates real tick time once host-side overhead is optimized — this is
  bot-authored behavior, not a host bug; the user explicitly chose to leave
  bot source unmodified rather than patch it for speed.

## Repo state

First commit of the whole project pushed to a personal fork:
`origin` = `Viir/bots` (upstream, untouched), `fork` = `smerwin/bots`
(personal, `git remote add` — `gh repo fork`'s `--remote` flag reported
success but didn't actually add the remote). Root `.gitignore` excludes
`.DS_Store`, `__pycache__/`, `*.pyc`, and the ad-hoc-signed compiled tool
binaries (`probe`, `memory_sample`, `tree_walker`, `live_reader`,
`window_probe`, `cg_input` — each has adjacent `.c` source; binaries are
platform-specific build output, not source).
