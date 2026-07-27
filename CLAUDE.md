# Project: macOS-native EVE Online bot host (no BotLab.exe / reactor.botlab.org)

## Goal

Build a macOS-native replacement for the closed-source `BotLab.exe` "volatile
host" so the existing Elm bot programs in `implement/applications/eve-online/`
(mining bot, combat anomaly bot, warp-to-0 autopilot) can run on Apple Silicon
without the Windows client and without phoning home to reactor.botlab.org
(BotLab's paid licensing/session-credit backend).

Non-commercial, not for distribution (user's stated intent).

## Key architectural finding: the Elm bot logic is already OS-agnostic

The Elm code never touches memory directly. It talks to a "volatile host"
process via a small JSON protocol:

- `implement/applications/eve-online/eve-online-mining-bot/EveOnline/VolatileProcessInterface.elm`
  defines the request/response types: `ListGameClientProcessesRequest`,
  `SearchUIRootAddress`, `ReadFromWindow`, plus mouse/keyboard effect
  encoding.
- `implement/applications/eve-online/eve-online-mining-bot/EveOnline/MemoryReading.elm`
  decodes the response into a generic `UITreeNode` tree: `pythonObjectAddress`,
  `pythonObjectTypeName`, `dictEntriesOfInterest`, `children`.

This JSON shape comes from the open-source **Sanderling** project
(`github.com/Arcitectus/Sanderling`), which is what `BotLab.exe` wraps on
Windows to do the actual memory reading and CPython-object-graph walking.

**Conclusion:** if a macOS-native host emits the same `UITreeNode` JSON shape
and executes the same effect commands (mouse move/click, key press), all
~8,500 lines of existing Elm bot logic (`Bot.elm`, `ParseUserInterface.elm`,
`BotFramework.elm`, etc.) work unmodified. We only need to build the host,
not touch the bot logic.

There is also an existing screenshot/OCR-based fallback parser already in the
repo (`EveOnline/ParseGuiFromScreenshot.elm`) — user explicitly rejected this
approach as too slow/computationally expensive. We're going the memory-reading
route.

## Key finding: EVE's native Apple Silicon client is not Wine/CrossOver/a VM

CCP shipped a native Apple Silicon client (Metal-based) since 2021 — confirmed
live on this machine:

- Launching `/Applications/eve-online.app` (Electron, bundle
  `com.ccpgames.eve-online-launcher`) is just the **launcher/portal**, not the
  game.
- The launcher spawns the actual game client as a separate native process:
  bundle `com.ccpgames.eveonline`, executable at
  `~/Library/Application Support/EVE Online/SharedCache/tq/EVE.app/Contents/Resources/build/bin64/exefile`
  — a universal Mach-O binary (x86_64 + arm64), PIE, hardened runtime on.
  - PID is ephemeral (new each launch). Find it with:
    `lsappinfo list | grep -B2 -A8 'com.ccpgames.eveonline'` or
    `ps aux | grep 'SharedCache.*exefile'`.
- Codesigning: `Authority=Developer ID Application: CCP ehf. (PC6EP52JKP)`,
  `flags=0x10000(runtime)`, only entitlement present is
  `com.apple.security.cs.allow-unsigned-executable-memory`. **No
  `get-task-allow`.** This is what makes external memory reading hard (see
  below).
- The `bin64/` directory next to `exefile` contains `.so` files that are
  literally named after CPython stdlib C-extension modules: `_ctypes.so`,
  `_ssl.so`, `_sqlite3.so`, `_csv.so`, `_io.so`, `_lsprof.so` — plus
  EVE-specific ones: `_destiny.so`, `_trinity_metal.so`,
  `_pyevepathfinder.so`, `_eveplanetresources.so`, `_evelocalization.so`.
  **This confirms the native Mac client still embeds a Python interpreter for
  UI/game logic**, recompiled for arm64/Metal — so the "walk the CPython
  object graph in memory" approach Sanderling uses on Windows is conceptually
  valid here too. The actual struct offsets will differ from the documented
  Windows ones and need fresh reverse engineering (different build/version,
  not a Wine-translated Windows binary).

## Feasibility probe: can we read the target process's memory at all?

Wrote a minimal Mach VM probe (`task_for_pid` + `mach_vm_region` +
`mach_vm_read_overwrite`), ad-hoc signed with `com.apple.security.cs.debugger`
+ `com.apple.security.get-task-allow` entitlements.

**Location (now checked into the repo, not tmp):**
```
tools/macos-host/probe/
  probe.c
  probe            (compiled binary, gitignored-worthy but currently present)
  entitlements.plist
```
Build/sign commands used:
```
clang -o probe probe.c
codesign -s - --entitlements entitlements.plist -f probe
./probe <pid>
```

### Diagnosis chain (each step ruled out one candidate blocker)

1. Unprivileged, ad-hoc signed → `task_for_pid failed: (os/kern) failure
   (kr=5)`.
2. Tried `sudo` through Claude Code's Bash tool → fails, no TTY for password.
   **Must run sudo from a real interactive Terminal.app window**, not through
   the agent's shell.
3. Enabled Developer Mode: `sudo DevToolsSecurity -enable` (done, confirmed
   "Developer mode is now enabled") → did **not** fix it alone.
4. Developer Tools TCC permission (System Settings → Privacy & Security →
   Developer Tools): Terminal.app granted, iTerm2 not. Re-ran from Terminal.app
   → still `kr=5`.
5. **Root cause identified:** `csrutil status` → "System Integrity Protection
   status: enabled" (no exceptions). SIP has a specific **Debugging
   Restrictions** component that blocks `task_for_pid`/`ptrace` against any
   target lacking `get-task-allow` — applies to *every* caller, including
   Apple's own `lldb`, and is not bypassable via entitlements, Developer Mode,
   or the Developer Tools TCC toggle. This is also why Cheat Engine-style
   tools generally don't work on stock macOS against hardened, non-dev-signed
   targets — same wall for everyone.

### Resolved (2026-07-25): Recovery Mode step completed, probe confirmed working

User booted into Recovery Mode and ran `csrutil enable --without debug`.
Current `csrutil status`:
```
System Integrity Protection status: unknown (Custom Configuration).
Debugging Restrictions: disabled
```
(Everything else — Filesystem Protections, Kext Signing, etc. — remains
enabled. Only the debugging restriction was dropped.)

Re-ran the probe (rebuilt from source, see location above) against:
1. A throwaway `sleep` process — `task_for_pid` + `mach_vm_read_overwrite`
   succeeded, confirming the SIP change took effect.
2. The live EVE game client (`exefile`, pid varies per launch, found via
   `lsappinfo list | grep -B2 -A8 'com.ccpgames.eveonline'`) — **also
   succeeded.** Walked ~20 VM regions, read bytes from each readable one
   (Mach-O headers, `__DATA` pages, etc.) with no `kr=5` or other failure.

**This confirms the hard blocker from last session is fully cleared** — we
can now read the EVE client's process memory from an unprivileged, ad-hoc
signed tool. The remaining work is entirely reverse-engineering /
implementation, not permissions.

**Tradeoff still in effect:** this is a standing, system-wide SIP reduction,
not scoped to just this project — any process on the machine gains the same
debugger-attach ability until reverted (Recovery Mode, plain
`csrutil enable`).

## Resume here — next steps now that memory reading works

### Done (2026-07-25): memory sampling tool built and verified working

Built `tools/macos-host/memory_sample/` (`memory_sample.c`, entitlements same
as `probe/`) and `tools/macos-host/save_process_sample.sh`, which together
are the macOS analog of the Windows `read-memory-64-bit.exe
save-process-sample` tool. Usage:
```
save_process_sample.sh --memory-pid=<exefile pid> --window-pid=<launcher pid> [--out=<dir>]
```
Writes `memory.bin` (raw bytes of all readable, non-shared regions),
`regions.tsv` (address/size/protection/status index mapping regions to
offsets in the dump), `screenshot.png`, and `manifest.json` tying it together
with timestamps and a sha256 of the memory dump.

First real run (pid 2832 / 2355): 2,397 regions total, 2,259 dumped (24
skipped as shared dyld cache, 105 skipped no-read), 5.84 GB dumped. Screen
Recording permission is now granted (was the missing piece last session) —
confirmed because the window title resolved to "EVE Launcher" instead of
null, and `screencapture -l` produced a real, non-blank image.

**Caveat found on this run:** the on-screen window (owned by the
`eve-online` launcher process, pid varies) was still sitting at the
launcher's account-portal screen ("CLIENT IS RUNNING" button showing, not
actual game content) even though the `exefile` game process was live —
apparently the launcher window and the actual in-game view don't fully merge
until you're further into a play session. A useful correlation sample needs
the screenshot taken while real game UI is on screen (station hangar, ship
in space, an overview/cargo window open), not the idle launcher portal.
Next sample should be taken after actually entering the game and opening a
few UI panels.

### Done (2026-07-25): fullscreen game window found on a separate macOS Space; real sample taken

The game was running fullscreen, which macOS puts on its own Space — this is
why `window_probe` (which only sees the *current* Space's on-screen windows
via `kCGWindowListOptionOnScreenOnly`) found nothing for it. Switching Spaces
with `osascript -e 'tell application "System Events" to key code 124 using
control down'` (Control+Right = next Space) revealed it.

**Correction to the two-process-split finding above:** that finding
(launcher owns the window, `exefile` owns memory, two different pids) only
holds when the game is sitting at the launcher's windowed account-portal
screen. Once actually in the fullscreen game view, the window is owned by
**the same pid as the memory target** — `owner="EVE"`, `owner_pid=2832`,
matching the `com.ccpgames.eveonline`/`exefile` pid, window `"EVE - Kira
Langosta"`, bounds `{x=0, y=38, w=1710, h=1069}` points. So
`ListGameClientProcessesRequest`-equivalent resolution needs to handle both
shapes: portal mode (two pids, look up by two bundle IDs) and in-game
fullscreen mode (one pid serves both roles). Windowed (non-fullscreen)
in-game mode hasn't been checked yet — worth confirming which shape it
follows too.

Also fixed a latent bug this surfaced: `save_process_sample.sh` picked the
window via `window_probe | head -1`, but `window_probe`'s output order is
window-server z-order, not size — a fullscreen game window can have a
smaller `layer=25` overlay (e.g. the reveal-on-hover menu bar strip) sorted
ahead of it. Script now scans all `layer=0` windows for the given pid and
picks the largest by area.

Took a real correlation sample (`sample2`, not checked into the repo —
5.85 GB) with the game actually showing content: docked in Jita, station
UI, ship model, local/corp chat, guest list. Sanity-checked that UI text
appears as plaintext in the raw dump — grepped `memory.bin` for strings
visible in the screenshot ("CONCORD Assembly", "Caldari Business", "Kira
Langosta", "State War Academy") and each hit 4-11 times; confirms the
string data needed to anchor the CPython object-graph walk (step 2/3 below)
is there and findable by direct byte search, not obfuscated/compressed.
("Board my Corvette" didn't hit — likely UTF-16 or composed from a
localization key rather than a literal C string; not investigated further
yet.)

### Done (2026-07-25/26): first real object-graph RE — confirmed PyObject layout, found a ground-truth-address technique

Wrote `re_helper.py` (currently only in the scratchpad, not checked into the
repo — should be moved into `tools/macos-host/` if this line of work
continues) that: loads `regions.tsv`, converts between dump file offsets and
target-process virtual addresses in both directions, and can search
`memory.bin` for a byte string and dump the surrounding bytes as 8-byte
little-endian words for manual inspection.

**Key technique discovered:** grepping `memory.bin` for names visible in the
screenshot (e.g. "Kira Langosta", a corp-chat guest) turned up debug/log
text embedded in a larger buffer that includes the *live Python object's own
address*, e.g.:
```
<bound method User.OnSuspectsAndCriminalsUpdate of <User object at
0X00000358051470, name=Kira Langosta, destroyed=False>>
```
EVE's own `__repr__`/logging apparently formats object addresses as
`0X%014X`. Because our memory dump preserves real addresses (no need to
correct for ASLR-vs-dump-time skew — the dump *is* a snapshot of the live
address space), that hex address can be fed straight back into
`regions.tsv` to jump directly to the object's header — sidestepping the
planned "memory pattern scan for root object" step, at least for any object
class whose instances show up in such log lines. Worth specifically hunting
for a similar log line naming a **UI/window root object**, not just game
entities like `User`.

**Confirmed CPython object layout for this build (arm64, presumably a
recent CPython 3.x, exact version not yet pinned):**
- `PyObject` header: `ob_refcnt` at `+0x00` (8 bytes), `ob_type` at `+0x08`
  (8-byte pointer). Verified two different `User` instances (Kira Langosta's
  and S1MPLE-JACK's, found via the address technique above) both have
  `refcnt=2` and an **identical** pointer at `+0x08`, which resolves to the
  shared type object.
- `PyTypeObject` (`PyVarObject_HEAD` + `tp_name`): `ob_refcnt` `+0x00`,
  `ob_type` `+0x08`, `ob_size` `+0x10`, `tp_name` `+0x18` — a pointer to a
  plain C string. Confirmed by dereferencing the `User` instances' shared
  type pointer and reading `tp_name` → literal ASCII `"User"`. This matches
  stock CPython layout exactly, i.e. no custom header fields were added
  ahead of the standard ones for this build.
- A `User` instance's `+0x18` field dereferences to a 4-word struct
  `[refcnt, type_ptr, wr_object, wr_callback]` where `wr_object` points
  **back** to the `User` instance itself and `wr_callback` is `NULL` — this
  is a near-exact match for CPython's `PyWeakReference` layout
  (`wr_object` at `+0x10`, `wr_callback` at `+0x18` within the weakref
  object). Further confirms stock, unmodified struct offsets.
- `+0x10` field of a `User` instance dereferences to something with two
  `0x42` words in it — not yet identified (candidate: a `PyLongObject`, but
  the value doesn't obviously read as a small int; unresolved).
- **Not yet found:** the `__dict__` pointer / instance attribute storage
  for `User` objects (needed to walk arbitrary attributes generically, the
  way `dictEntriesOfInterest` in `EveOnline/MemoryReading.elm` expects), and
  no UI widget tree object has been located yet — everything confirmed so
  far is on a game-entity (`User`) object, not a UI tree node.

**Next step (superseded — see below, this was resolved same session):** find
a debug/log string that names a UI object the same way the `User` repr did.

### Done (2026-07-26): repr-scanning technique found more classes; confirmed the wrapper is a universal 32-byte "handle" object, not `__dict__`-based

**Technique:** the debug/log text isn't a one-off — it's a scannable ring
buffer. Regexing the whole 5.85 GB dump for the pattern
`<ClassName object at 0X[hex]` (EVE's own repr format) found 32 hits across
5 distinct classes in about 3 seconds (`re.finditer` works directly against
an `mmap` object, no need to read the file into memory first):
```
18  User               e.g. 0x358056E10
11  XmppChatUserEntry  e.g. 0x37C8A2BA8
 1  InGameClock        e.g. 0x37C4F3128
 1  TiDiIndicator      e.g. 0x37C8D4DD8
 1  HangarLayer        e.g. 0x1338A9048
```
`InGameClock`, `TiDiIndicator`, and `HangarLayer` are genuine UI/scene
objects (the clock readout, a lag indicator, the hangar background layer) —
this is the technique to reuse for finding more UI class ground-truth
addresses generally: grep/regex the dump for repr patterns rather than
hoping to find one string at a time. Worth widening the regex to also catch
whatever repr format non-"object at 0X" classes use, since this only caught
one specific `__repr__` convention.

**Checked `HangarLayer`'s instance layout against `User`'s — identical
shape, confirming a universal pattern, not a `User`-specific quirk:**
- `tp_basicsize` for both is `0x20` (32 bytes): `PyObject` header (16
  bytes: refcnt + type) plus exactly two more 8-byte slots. No `__dict__`
  — these are C-extension ("Blue" binding layer, CCP's internal
  Python/C++ interop, not stock `boost::python`) proxy objects, not
  ordinary Python-defined classes.
- `+0x10`: a pointer to a **small boxed-integer object of a custom shared
  type** — dereferencing it gives `[refcnt, type_ptr, value, value]`
  (the value is duplicated across two words for both instances checked,
  not yet understood why). The **type pointer at this slot is identical
  across both `User` and `HangarLayer` instances** (`0x101209f50`), and the
  boxed values themselves are small and close together — `0x42` (66) for
  one `User` instance, `0x43` (67) for `HangarLayer` — consistent with a
  small sequential **handle/index**, not a raw pointer. Working theory:
  this is an index into a native handle table that the "Blue" binding layer
  uses to find the real C++ object; the boxed-int class is probably some
  internal handle-wrapper type shared by all bound classes.
- `+0x18`: confirmed (for both classes) to be the **weakref list slot** —
  dereferences to a 4-word struct `[refcnt, type_ptr=0x101217e60 (same for
  both), wr_object=<points back to the instance itself>, wr_callback=NULL]`,
  an exact match for CPython's `PyWeakReference` layout. Not useful for
  reading game/UI state, but a fully solved, reusable landmark: any object
  with this exact pattern at `+0x18` is a weakref, letting future RE work
  quickly rule that slot out and focus on the handle slot.

**Implication — this reframes the remaining project scope.** The
`pythonObjectAddress`/`dictEntriesOfInterest` walk `MemoryReading.elm`
expects cannot be a generic "read `__dict__`, recurse into children"
routine for these core engine/UI classes, because there is no `__dict__` to
read — real state lives behind the handle indirection. **The actual next
target is finding and decoding the handle table** (where it lives, what
each entry's layout is, how a handle integer maps to a native object
address) — that unlocks reading real fields (name, position, children,
widget text, etc.) for every wrapper object we can find an address for,
which is now cheap thanks to the repr-scanning technique above. This is a
bigger and more central task than originally scoped as "step 4, generic
JSON walker" — it's closer to being the crux of the whole project.

### Done (2026-07-26): CRACKED — the custom dict layout is decoded, and a working generic attribute walker exists

This is the big one. Built `tools/macos-host/re_helper/re_helper.py` into a
real tool (checked into the repo, not scratch) with:
- `find <needle>...` — locate byte strings and report their virtual addresses.
- `dump <addr>` — hexdump an address as 8-byte words, auto-classifying each
  word as `NULL`, a small int, an "instance of `<ClassName>`", or a "TYPE
  OBJECT `<Name>`" using the `ob_type`-must-equal-the-`type`-metaclass
  invariant (see below) — no more manual pointer-chasing by eye.
- `walkdict <dict_addr>` — walks a wrapper object's `+0x10` dict field and
  prints every real `key: value` pair, with string values decoded to their
  actual text.

**The `type` metaclass invariant, used throughout:** every valid
`PyTypeObject` we've found has `ob_type == 0x101215508` (this is
`PyType_Type`, i.e. `type(type) is type`, a CPython universal). Any 8-byte
word in memory can be checked against this cheaply: if it points at
something whose own `+0x08` field equals `0x101215508`, it's a real class,
and its `tp_name` (`+0x18`, a plain `const char*`) can be read to name it.
This one invariant is what makes the generic classifier in `dump`/
`walkdict` possible — no per-class special-casing needed to at least *name*
what a pointer refers to.

**The `PyASCIIObject` (compact-ASCII `str`) layout for this build, fully
decoded and verified by hand before automating:** `refcnt` `+0x00`,
`ob_type` `+0x08`, `length` `+0x10`, cached `hash` `+0x18`, then a 4-byte
state field, then raw ASCII bytes starting at `+0x24`. Verified against a
real string (`"renderObject"`, length 12, whose cached hash exactly matched
the hash word found in the owning dict's entry table — not a coincidence).
The `str` type object itself is at `0x101210cd0` for this process run.

**The custom dict layout (the thing flagged as unresolved last session) is
now fully decoded:**
- Header, 0x50 (80) bytes: `refcnt` `+0x00`, `ob_type` `+0x08` (always
  `0x101209f50`, the real `dict` type — confirmed via an isolated,
  non-coincidental `"dict"` string at its `tp_name`), then two duplicate
  `Py_ssize_t`-ish fields at `+0x10`/`+0x18` (equal to each other; likely
  `ma_used` and a redundant/derived count, not fully pinned down), then a
  capacity-mask-shaped field at `+0x20` (seen `0x7f` and `0x1ff` — i.e. 128-
  and 512-slot tables, both one-less-than-a-power-of-2), then an
  **overflow-table pointer** at `+0x28` (per-instance, valid only when the
  dict has entries beyond what fits inline), then a **shared/constant**
  function-or-vtable pointer at `+0x30` (identical value —`0x1010906e4`—
  across every dict instance checked regardless of class or size; not
  per-instance data, and 8-byte-aligned words at that address decode as
  literal ARM64 instructions, e.g. `0xd503201f` = `nop`).
- Entries, both inline (right after the header, capacity 7: `(248-80)/24`)
  and in the overflow table pointed to by `+0x28` (capacity = mask+1 from
  `+0x20`): each entry is 24 bytes, `(hash: 8, key_ptr: 8, value_ptr: 8)`,
  `key_ptr` always a `str` object, empty slots are all-zero. The inline
  slots and the overflow table can contain **overlapping/duplicate**
  copies of the same entries (harmless for reading, just dedupe by key
  pointer) — not yet clear why, possibly a small "recently touched" cache
  vs. the authoritative backing store, not investigated further.

**Validated against two real, complex, independently-identifiable
objects** (both matched ground truth from the screenshot/UI, not just
"looks plausible"):
- `InGameClock` (found via the repr-scan technique) — 46 attributes, all
  sensible for a UI widget base class: `renderObject` →
  `trinity.Tr2Sprite2dContainer`, `children` → `PyChildrenList`,
  `_displayX`/`_displayY`/`_opacity`/`_align`/`_clipChildren`, a real
  `clock_label` → `Label` instance, `_parentRef` → a `weakref`.
- `OverviewWindow` — 139 attributes, including `_name` and `windowID` both
  reading back as the literal string `'overview'`, and `_elementId` as
  `'unique_UI_overviewWnd'` — this **is** the actual overview panel visible
  in the screenshot, confirmed from inside the object's own data, not
  inferred. Also found `scroll` → `BasicDynamicScroll` and
  `_scrollNodesByItemID` → a `dict` — walked the latter and got real
  `Bunch` instances (EVE's generic namespace/attribute-bag class) keyed by
  what are presumably item IDs, one per overview row. This is the live
  in-memory backing store for the Overview list rows shown on screen.

**Open thread, not yet resolved:** `Bunch` instances themselves don't
follow this dict pattern — every `Bunch` checked (multiple, from the
`_scrollNodesByItemID` walk) shows the *same small-varying-integer* shape
at `+0x10`/`+0x18` that was originally seen (and later dismissed) on
`User`/`HangarLayer` before the `dict` identification: two duplicated
small integers (e.g. `0x34`, `0x2d`, `0x29`, `0x35` — different per
instance, too small to be pointers), no dict, no weakref. Whatever this
slot means for classes that don't carry a dict there is still an open
question — possibly relevant again now that it's recurred on a second,
independent class family.

**Next step:** decode `Bunch`'s actual field storage (whatever it is) to
pull real per-row Overview data (ship name, distance, velocity — matching
the visible screenshot table) all the way through.

### Done (2026-07-26): SOLVED — the full recursive UI-tree walk, end to end, validated

This is the crux result the whole project needed. Full recipe, every step
checked against real live data:

1. A widget is a 32-byte wrapper instance: `refcnt` `+0x00`, `ob_type`
   `+0x08`, `dict_ptr` `+0x10`, `weakref_slot` `+0x18` (see above).
2. `dict_ptr` → the custom dict (decoded above). Look up the key
   `'children'` in it.
3. Its value is a `PyChildrenList` instance (its own 32-byte wrapper, type
   `0x138cfea18`). Get **its** `dict_ptr` (`+0x10`) the same way, then look
   up the key `'_childrenObjects'` inside *that* dict.
4. `_childrenObjects`'s value is a **genuine, stock CPython `PyListObject`**
   — not a custom type. Standard 40-byte layout: `refcnt` `+0x00`,
   `ob_type` `+0x08` (the real `list` type, `0x101207828` for this
   process), `ob_size` `+0x10`, `ob_item` `+0x18` (pointer to a flat, plain
   array of `ob_size` child pointers), `allocated` `+0x20`.
5. Each pointer in the `ob_item` array is another widget wrapper — recurse
   from step 1.

**Validated on `OverviewWindow`:** its `_childrenObjects` list has
`ob_size=4`, and the 4 child pointers resolve (via the class-name
classifier) to `Container`, `Resizer`, `Container`, `WindowUnderlay` — and
critically, the `Resizer` pointer (`0x123cfca90`) is byte-for-byte
identical to the `_Window__resizer` attribute value found independently
via the dict walk earlier in this session. Two unrelated paths (attribute
lookup vs. children-list walk) landing on the exact same address is about
as strong a confirmation as this kind of RE gets.

**Dead end, worth recording so it isn't retried:** before finding this,
spent real effort following pointers at `PyChildrenList+0x20`/`+0x28`,
which looked like a doubly-linked list (each node points back to a
neighbor, `-3`/tag pattern repeating). Followed it 30 hops deep without
cycling back, through wildly unrelated object types (`dict`, `tuple`,
`list`, `set`, `weakref`) — this is almost certainly CPython's own
internal GC-tracked-object list (every GC-trackable object is threaded
into one big process-wide doubly-linked list for cyclic collection), not
anything to do with `PyChildrenList`'s actual content. `+0x20`/`+0x28` on
any GC-tracked object are likely to show this same pattern and are a trap,
not a lead. The `_childrenObjects` route above is the real one.

**Practical technique that cracked it:** rather than guessing the pointer
struct's semantics, took several attribute values already known by name
(`scroll`, `sortHeaders`, `tabGroup`, `_tab_line`, `_Window__resizer`) and
searched the raw dump for their exact address bytes appearing anywhere
else in memory (`Sample.find_all` on `struct.pack("<Q", addr)`). Three of
those addresses turned out to sit 8 bytes apart, back-to-back — instantly
revealing a flat array without needing to understand any struct at all.
This "search for where a known address is referenced from" approach is
far more reliable than trying to reverse-engineer container internals from
first principles, and is the technique to reach for first on future
unknown structures too.

**Done, same session: implemented and it actually works.** `re_helper.py`
now has a `tree <addr>` command implementing steps 1-5 above recursively,
emitting real `UITreeNode`-shaped JSON (`pythonObjectAddress`,
`pythonObjectTypeName`, `dictEntriesOfInterest`, `children`) with
`--max-depth`/`--max-nodes` safety caps. Ran it against `OverviewWindow`
(`tree 0x38FC2A7F0 --max-depth 3 --max-nodes 60`): produced a clean
33-node, 4-level-deep tree with no crashes, no infinite loops, and
completely recognizable structure — `Container` → `DefaultWindowControls`
→ `WindowControls` (with `_menu_unique_name: "unique_UI_overviewHeaderIcon"`),
`Resizer` → `ResizeHandle` (`_cursor: "res:/UI/cursor/cursor13.png"`) →
`Container`, etc. This is a working, if early, prototype of the exact
walk the whole project needs.

`dictEntriesOfInterest` currently only decodes `str` and `float` values
properly (verified against real data); `bool` is detected by type name but
not decoded to an actual `True`/`False` (shows a placeholder string);
`int`/`long` and nested object references are omitted entirely rather than
guessed at — `PyLong`'s actual bit layout for this build hasn't been
reverse-engineered yet (attempted once, early in the session, on `User`'s
`+0x10` field before that was reassigned to the dict theory; never
revisited). That's real, scoped follow-up work, not a blocker.

**Still open for next session:**
- Confirm leaf nodes (widgets with no children) correctly show up with
  `dict_ptr` for `'children'` absent/`None` rather than erroring — hasn't
  been explicitly tested, though the 4-level-deep tree run didn't crash on
  any leaf, which is a good sign.

### Done (2026-07-26): SOLVED — found the true root UI object, and fixed an off-by-one that was dropping every dict's first entry

**Root object found by walking `_parentRef` upward, not by pattern
scanning.** Widgets carry a `_parentRef` attribute — a `weakref` pointing
at their parent (a weak reference specifically so the child doesn't keep
the parent alive, avoiding a reference cycle). Walking
`obj.__dict__['_parentRef'] → weakref.wr_object → parent`, repeated, from
`OverviewWindow` converged in exactly 2 hops: `OverviewWindow` →
`LayerCore` → an object with **no `_parentRef` key at all**, at
`0x133454438`. Its own attributes confirm it beyond doubt: class name
`UIRoot`, `_name` = `'Desktop'`, `_elementId` = `'Desktop'`, a
`renderObject` of type `trinity.Tr2Sprite2dScene` (a whole-scene render
object, not a widget-level sprite), a `camera` slot, and a `renderSteps`
list — exactly what a genuine top-of-tree desktop/scene root should look
like, not a coincidental match. Its 14 children are 13 `LayerCore`
instances plus one `ResourceLoadingIndicator`, and the specific `LayerCore`
this walk passed through on the way up is present among them, closing the
loop. This is a much simpler and more reliable technique than the
originally-planned "memory pattern scan for a root address" (see the old
numbered plan at the bottom of this file, step 3 — superseded by this) —
any live widget's address (found via the repr-scan technique, or anything
else) can serve as a starting point and be walked up to the root for free.

**Also found and fixed a real bug while re-examining `Bunch` for the item
above:** the custom dict's header was assumed to be `0x50` (80 bytes) with
7 inline entries, based on the very first dict this session where reading
from `+0x50` happened to still produce sensible-looking output. Rechecking
against `Bunch`'s type object showed the header is actually **`0x38` (56
bytes) with 8 inline entries** — `0x38 + 8*24 = 248`, matching
`tp_basicsize` exactly (the old `0x50 + 7*24` assumption also totals 248,
which is exactly why the bug went unnoticed: both arithmetic paths hit the
same total size, but the old one silently skipped each dict's first entry
by starting 24 bytes too late). Fixed in `walk_dict_entries` and the
`walkdict`/`tree` bootstrap code in `re_helper.py`. This means every
`dictEntriesOfInterest` list produced earlier this session was missing
exactly one attribute — not wrong, just incomplete; worth a mental note if
comparing old output to fresh runs.

**`Bunch`'s "mystery" structure from earlier this session is fully
resolved, and it was never actually mysterious** — just measured wrong.
`Bunch`'s `tp_basicsize` is **264 bytes**, not the 32 bytes originally
read (only the first 4 words were dumped, which happened to be exactly the
custom-dict header prefix, making it look like the same thin-wrapper shape
as `User`/`HangarLayer`). With a full 264-byte read, a `Bunch` instance for
one of `OverviewWindow`'s scroll-list rows decodes as a completely regular
instance of the now-fully-understood dict pattern, `__guid__` =
`'listentry.OverviewScrollEntry'`, holding exactly the fields you'd expect
for an Overview row: `itemID` (`long`), `display_NAME`/`display_DISTANCE`/
`display_TYPE`/`display_VELOCITY`/`display_ANGULARVELOCITY`/`display_SIZE`
(all `unicode` — the pre-formatted column text actually rendered on
screen), and `rawDistance`/`rawVelocity`/`rawAngularVelocity`/
`rawTransveralVelocity` (`float` — the underlying numeric values before
formatting). Decoded one real instance and got `display_TYPE: 'Caldari
Shuttle'` and `display_NAME: 'Goth Cowgirl'` — both fully plausible,
real-looking live game data (a shuttle owned by a player named "Goth
Cowgirl" sitting in the Overview list), not placeholder/garbage.

**Net effect: both major open threads from earlier this session are now
closed**, and the fix + these two findings mean `re_helper.py`'s `tree`
command, run from `0x133454438` (`UIRoot`), is — as far as this session
can tell — a working prototype of a complete top-to-bottom UI tree walker
producing genuinely correct, useful data. It has only been run with small
`--max-depth`/`--max-nodes` caps so far (kept deliberately small during
development); a full, uncapped walk of the whole live tree from the real
root has not yet been attempted and would be a reasonable next check
(mainly to see how large/slow it gets and whether anything anywhere in the
much bigger real tree breaks these assumptions).

### Done (2026-07-26): `PyLong`/`PyInt`/`PyUnicode` all decoded — this is a Python 2 type system, not Python 3

Picked up the "numbers aren't decoded yet" gap from the tree walker.
Found real values for both a `bool` (`True`/`False`) and several `int`
attributes by grabbing their live addresses out of `OverviewWindow`'s dict
and inspecting the raw bytes directly — result is a much simpler layout
than modern CPython 3.12's tagged/bit-packed small-int scheme:

- **`int`** (and `bool`, which behaves identically): classic **Python 2
  `PyIntObject`** — `refcnt` `+0x00`, `ob_type` `+0x08`, a single plain
  signed 8-byte `ob_ival` at `+0x10`. No arbitrary precision, no digit
  array. Confirmed by finding the two singleton `bool` addresses (used by
  dozens of different attributes each) and seeing `ob_ival` read exactly
  `1` for the True-associated address and `0` for the False-associated
  one.
- **`long`** (a genuinely separate type from `int` — this build keeps
  Python 2's int/long split): classic **Python 2 `PyLongObject`** —
  `PyObject_VAR_HEAD` (`refcnt`, `type`, `ob_size` at `+0x10` — digit
  count, sign of the whole number), then a **digit array** starting at
  `+0x18`, each digit a 4-byte slot holding a value under `2^30` (30-bit
  digits, the standard Python 2 64-bit-build digit size). Decoded value =
  `sum(digit[i] * (2**30)**i)`, negated if `ob_size < 0`.
- **`unicode`** (also separate from the compact-ASCII `str` decoded
  earlier — another Python 2 str/unicode split signal): `PyObject_HEAD` +
  `length` at `+0x10` + a **pointer** to an externally-allocated buffer at
  `+0x18` (not inline, unlike `str`) + `hash` at `+0x20`. The buffer is
  **UCS-4** (4 bytes/char, not UCS-2) — confirmed by decoding
  `OverviewWindow._Window__caption` and getting back the exact string
  `"Overview (General: General)"`, an exact match for the actual tab label
  visible in the game's UI.

**Bigger-picture conclusion:** the combination of a separate `int`/`long`
split and a separate `str`/`unicode` split is Python 2's type system, not
Python 3's (which unified both pairs years ago). This build — despite
being a modern 2021+-era native Apple Silicon/Metal recompile — is
structurally still Python 2, consistent with EVE's long history on
Stackless Python 2.7. Worth keeping in mind for any future struct RE on
this codebase: reach for Python 2 CPython source (specifically the 2.7
branch) as the reference implementation, not Python 3.

All four decoders (`read_pyint`, `read_pylong`, `read_pyunicode`, plus the
earlier `read_pyfloat`/`read_pystr`) are wired into `describe_primitive`
in `re_helper.py`, so `tree`'s `dictEntriesOfInterest` output now shows
real numbers and real unicode strings, not placeholders — verified via
internal self-consistency (`_left` and `default_left` both read `1338`,
as they should) and one exact external match (the caption string above).

**Not yet done:** locating the handle table itself. Candidate approach:
take the boxed handle values (66, 67 observed) as small integers, and
search memory for a table/array that indexes cleanly by small integers like
that (e.g. an array of pointers where `table[66]` and `table[67]` land on
plausible object headers) — akin to how Python's own small-int cache or a
CPython `PyLong` free-list is found, but for CCP's custom handle table.

### Done (2026-07-26): second sample (in space, Overview panel open); `+0x10` confirmed as a genuine but non-stock `dict`

Took a third sample (`sample3`, 10.1 GB — process had grown from 5.8 GB
since last sample, more regions too: 4768 vs 2442) after undocking into
space near a wreck, with the Overview panel populated (~24 rows: ships,
wrecks, a station, columns for distance/name/type/size/velocity/angular).
Note: the fullscreen game window's macOS window layer isn't stable — it was
`layer=0` in `sample2` and `layer=25` in `sample3` for the same window
number, so `save_process_sample.sh`'s "largest `layer=0` window" filter
missed it this time. Worked around it manually (`screencapture -l
<window_number>` + `memory_sample` run separately); **the layer filter in
`save_process_sample.sh` still needs a proper fix** (should probably accept
any layer up to some small cutoff, or explicitly exclude only the known
menu-bar-strip window rather than filtering by layer at all).

Reran the repr-scan technique on the new sample and got a much better class
list, several clearly UI widgets tied to what's visible on screen:
`ShipUI`, `OverviewWindow`, `OverviewTab`, `SelectedItemWnd`,
`BuffBarContainer`, `CombatMessage`, `CapacitorContainer`, `SpeedGauge`,
`Timer`, plus repeats of `InGameClock`/`TiDiIndicator`. These are exactly
the kind of ground-truth addresses needed going forward — `OverviewWindow`
in particular should eventually lead to the row data backing the Overview
list seen in the screenshot.

**Resolved the `+0x10` ambiguity flagged earlier — it is a real `dict`,
but a non-stock one.** Re-checked the `"dict"` `tp_name` string with wider
context and it's a genuinely isolated, null-terminated 5-byte string
(`"...bases\0dict\0SOO\0__del__\0__cmp__\0compari..."` — looks like an
internal CPython interned-identifier table) — not a coincidental substring
match. Combined with the `ob_type` invariant (every valid `PyTypeObject`
we've checked has `ob_type == 0x101215508`, presumably `PyType_Type`/the
`type` metaclass, and `0x101209f50` satisfies this), the `+0x10` field is
confidently a real `dict` instance, not a small-int handle.

But it is **not a stock-layout CPython dict**: the `dict` type's own
`tp_basicsize` reads as `248` bytes (stock CPython's `PyDictObject` header
is ~48 bytes: refcnt, type, `ma_used`, `ma_version_tag`, `ma_keys`,
`ma_values`). Tried reading `OverviewWindow`'s dict instance at the classic
offsets anyway: `+0x10`/`+0x18` both read `0x8b` (139 — plausible as
`ma_used` for a widget with many attributes, but suspicious that two
adjacent fields matched exactly, same pattern seen on the smaller `User`/
`HangarLayer` dicts too), `+0x28` dereferenced to a pointer whose target is
all zeros beyond one non-zero word (plausible empty/sparse structure), and
`+0x30` dereferenced to **recognizable ARM64 machine code** (instruction
encodings like `0xd503201f`, which is the literal ARM64 `nop`), definitively
proving that offset is not `ma_values` under the classic layout. Working
theory: this build's dict variant inlines several key/value slots directly
into the object (`(248-48)/24 ≈ 8` triples of hash+key+value would roughly
fit) rather than allocating a separate keys/values structure — a plausible
performance optimization for a heavily-patched Stackless-derived CPython —
but the exact field layout isn't decoded yet. **This is a materially bigger
task than everything before it in this file**: it means walking real
attribute names/values out of these objects requires reverse-engineering a
custom, undocumented dict implementation, not just applying known stock
CPython offsets.

**Caution, checked same session:** chased the `+0x10` field's type pointer
(`0x101209f50`) and its `tp_name` read back as ASCII `"dict"` — tempting to
conclude `+0x10` is a real `__dict__` after all. But dereferencing *that*
object showed the same `[refcnt=1, type=0x101209f50, N, N]` shape
recursively (both `User`'s and `HangarLayer`'s `+0x10` targets look
"self-typed" one level down too), which is a red flag: it's more consistent
with the `tp_name` read landing mid-string inside something coincidentally
containing "dict" (e.g. "pre**dict**able") than with a real, distinctly-typed
`PyDictObject`. Treat the `+0x10` slot's meaning as **still unresolved,
not confirmed to be `dict`** — the small-int-handle theory and the
real-`__dict__` theory are both live; this needs a cleaner discriminator
(e.g. checking whether the candidate `tp_name` pointer is 8-byte aligned
and preceded by a plausible `PyASCIIObject` header, the way `read_cstr`
should really validate before trusting a `tp_name` hit) before either can be
trusted.

### Done (2026-07-26): performance — a live, no-dump-file reader, 8x faster than the naive version

Prompted by "how fast can we make this." Two genuinely different things
were slow, for different reasons, and both got addressed:

**1. The dump-based (`Sample`) pipeline's per-node walk was already fast**
(~0.17ms/node once dumped — 2000 nodes in ~0.36s) because it's backed by
`mmap` over a file the OS page-caches after writing it. The real cost
there is the ~4.4s, multi-GB `memory_sample` dump itself, which is fine
for one-off RE but is a non-starter for anything that needs to re-read
state repeatedly (a live bot loop needs updates many times a second, not
once every 4+ seconds).

**2. Built a second backend, `LiveSample`, that skips the dump file
entirely** — `tools/macos-host/live_reader/live_reader.c` is a small,
persistent, entitled helper process (same `task_for_pid` +
`mach_vm_read_overwrite` approach as `probe`/`memory_sample`, same
entitlements) that stays attached to the target process and serves an
open-ended stream of small reads over a binary protocol on stdin/stdout
(`8 bytes address + 8 bytes length` in, `8 bytes length + that many bytes`
out) instead of writing anything to disk. `re_helper.py` gained a
`--live-pid <pid>` flag (`--sample <dir>` for the old dump-based mode);
every existing decode/walk function (`classify`, `get_dict`,
`walk_dict_entries`, `build_tree`, ...) works unchanged against either
backend, because both `Sample` and the new `LiveSample` implement the same
`read_bytes`/`read_u64`/`read_cstr`/`read_pystr` interface (factored out
into a shared `MemoryReaderBase`). Confirmed correct by running the exact
same `tree` walk through both backends and diffing the JSON output byte
for byte — identical.

**First live run was slow (2.9s for an 800-node walk) — the interesting
part was figuring out why and fixing it, iteratively, with a
`round_trips`/`reads`/`bytes_read` counter printed after every run to
measure each change honestly rather than guessing:**

- **Batched the custom dict's entry table.** `walk_dict_entries` was
  issuing one 24-byte read *per slot* — up to 512+ for a big dict's
  overflow table — instead of one read for the whole contiguous block.
  Fixed to read the inline block and the overflow block each in a single
  call. (This also surfaced the off-by-one header-size bug documented
  above, while re-examining the code.)
- **Cached type-name resolution by type pointer.** A tree walk touches
  the same handful of classes (`bool`, `int`, `float`, `NoneType`, `str`,
  `dict`, ...) over and over across hundreds of attributes; caching
  `type_ptr -> tp_name` turns the second-and-later lookup of any given
  class from 2 reads into a dict hit.
- **Removed a redundant read** in `describe_primitive` (`value_is()` was
  re-reading a value's `ob_type` that `get_type_name()` had just read).
- **Made string/int/long/unicode decoding "optimistic single-read"**:
  instead of reading a small header first and then a precisely-sized
  second read for the data (2 reads, always), read a generously-sized
  chunk covering header-plus-typical-data in one shot, only falling back
  to a second read for the rare oversized value. Applies to `read_pystr`,
  `read_pylong`, `read_pyunicode`.
- **Eliminated a fully duplicate dict walk.** `build_tree` walked a
  widget's dict once to build `dictEntriesOfInterest`, then
  `get_children_addrs` walked the *same* dict again from scratch just to
  find the `'children'` key. Replaced with `dict_items()`, one pass that
  serves both needs (introduced via `get_children_addrs_from_wrapper`,
  which takes the already-found `children` pointer instead of
  re-deriving it).
- **Added real pipelining** (`read_bytes_batch`): write many requests to
  the helper process before reading *any* responses, instead of the usual
  stop-and-wait request/response cycle. This is the one that mattered
  most, because the actual `mach_vm_read_overwrite` work is fast (single-
  digit microseconds) but each *round trip* was costing about the same
  again in IPC/context-switch overhead — with ~150 reads needed per node,
  that overhead was almost the entire runtime. Applied it twice:
  - **All of a node's attribute *type* lookups** (`value+8`, one per
    attribute) batched into one round trip instead of N.
  - **All of a node's attribute *value* decodes** for the common scalar
    kinds (`str`/`int`/`bool`/`float`, which are always a single
    fixed-size read at `value+0x10`) batched into one more round trip;
    rarer kinds (`long`, `unicode`, nested objects) fall back to the
    normal per-value path.
  - **All of a dict's *key name* decodes** batched into one round trip —
    this was the single biggest remaining win, since decoding 50-140
    attribute *names* one at a time (to find out what they're even
    called, before touching values at all) was contributing as many round
    trips as everything else combined.

**Net result, 800-node live walk (real timings, `round_trips` printed by
the tool itself, not estimated):**
| stage | elapsed | round trips |
|---|---|---|
| naive (first working version) | 2.896s | ~330,000 *(reads, ≈round trips at this stage)* |
| + batched dict entry table, type-name cache, redundant-read removal, optimistic single-read decoders | 1.264s | — |
| + eliminated duplicate children/attribute dict walk | 1.123s | — |
| + batched per-node type-pointer fetch | 0.854s | — |
| + batched per-node scalar-value decode | 0.663s | — |
| + batched per-dict key-name decode | **0.353s** | **11,873** |

**~8.2x faster overall** (2.896s → 0.353s), and the *live* 800-node walk
(0.353s, zero dump needed) now comfortably beats even just the ~4.4s dump
step the file-based approach requires before it can do anything — for any
use case that needs fresh state repeatedly (a bot loop), `--live-pid` is
now unambiguously the right tool, not just the more elegant one. Verified
correctness held throughout: every optimization step was checked against
the file-backed `Sample` path (which stayed a byte-for-byte-identical
JSON oracle throughout, since its output doesn't depend on round-trip
count at all) before being trusted.

**Remaining lever, not pursued (diminishing returns for the effort):**
per-node round trips are down to ~15 (dict header, inline block, overflow
block if present, key-name batch, type-pointer batch, scalar-value batch,
plus a few more for children resolution) — the next step down would mean
pipelining *across* nodes too (batch requests for many sibling/cousin
nodes' dict headers together, one giant round trip per tree "level"
instead of per node), which would need restructuring `build_tree` from
depth-first recursion into an explicit breadth-first batch loop. Flagging
as the obvious next move if more speed is ever needed, not attempting it
now.

### Done (2026-07-25): window discovery, and a two-process-split finding

### Done (2026-07-25): window discovery, and a two-process-split finding

Built `tools/macos-host/window_probe/window_probe.c` (`clang -framework
ApplicationServices -o window_probe window_probe.c`, no entitlements needed).
Takes an optional pid filter, prints each on-screen window's number, owner
pid/name, layer, bounds in **points** (same coordinate space
`CGEventPost`/`CGWindowListCreateImage` use), and the backing scale factor
of the display it's on (`CGDisplayModeGetPixelWidth` /
`CGDisplayModeGetWidth` ratio).

**Important finding: the on-screen window and the memory-bearing process are
different PIDs, unlike the Windows/BotLab case.**
- `com.ccpgames.eveonline` (`exefile`, the process we `task_for_pid` for
  memory reads) owns **no on-screen window**.
- The actual visible game window — confirmed via `window_probe <launcher
  pid>` — is owned by `/Applications/eve-online.app/Contents/MacOS/eve-online`,
  bundle `com.ccpgames.eve-online-launcher` (the Electron launcher process).
  Example observed: bounds `{x=0, y=39, w=1400, h=800}` points,
  `backing_scale=2.00` (Retina). Window name comes back null for both
  processes (needs Screen Recording permission to populate, not granted —
  wasn't needed since the launcher pid owns exactly one on-screen window, no
  title-based disambiguation required).
- **Implication for the host:** resolve the on-screen frame via the
  launcher's bundle ID (`com.ccpgames.eve-online-launcher`), and resolve the
  memory-read target via the game's bundle ID (`com.ccpgames.eveonline`,
  `exefile`) — two separate `lsappinfo`/bundle-ID lookups feeding one merged
  `ListGameClientProcessesRequest`-equivalent result, not one process serving
  both roles.

Next up:
1. Memory sampling tool: macOS analog of the Windows
   `read-memory-64-bit.exe save-process-sample` tool (see
   `guide/how-to-collect-samples-for-64-bit-memory-reading-development.md`)
   — dump raw process memory + a screenshot together to correlate UI state
   with bytes.
2. CPython/Stackless struct reverse engineering for this specific arm64
   build/version (type object, dict, list, string layouts) — won't match
   Sanderling's documented Windows offsets.
3. Root UI object discovery (`SearchUIRootAddress` equivalent): a memory
   pattern scan that bootstraps the walk without hardcoded addresses (ASLR
   moves things every run).
4. Generic CPython object-graph walker → JSON, matching the exact
   `UITreeNode` shape from `EveOnline/MemoryReading.elm` so the existing Elm
   decoders work unchanged.
5. Input execution: `CGEventCreateMouseEvent`/`CGEventPost` for clicks/keys,
   mapping `Common.EffectOnWindow` effect types to CGEvents, with coordinate
   mapping from the window discovery step above.
6. Host glue: run the compiled Elm bot (`elm make --output=bot.js`, via Node
   or an embedded JS engine) in a loop, replacing what `BotLab.exe`
   orchestrates — feed it `ReadFromWindowResult` JSON, execute whatever
   `RequestToVolatileHost`/effect commands it emits.

Recommended language for the host: Swift (better-integrated codesigning/
entitlements story in Xcode) or Rust (`mach2` crate) as an alternative —
user's RE background was self-rated "limited," so favor whichever gives
clearer error messages/tooling during development.

## New goal (2026-07-26): drop-in BotLab.exe replacement, launches a bot from a GitHub or file URL

Scope grew significantly from "read memory" to "actually run a real,
unmodified Elm bot end-to-end." Progress below; this reuses everything
above (memory reading, live tree walker) as the `RequestToVolatileProcess`
backend, but adds a much bigger new layer: actually compiling and running
the bot's Elm code, and emulating the rest of BotLab.exe's host interface.

### Key architectural discovery: BotLab.exe's bots don't need BotLab.exe's actual toolchain to run

Read `BotLab/BotInterface_To_Host_2024_10_19.elm` (the interface contract
between a bot and BotLab.exe) in each bot app directory (e.g.
`implement/applications/eve-online/eve-online-warp-to-0-autopilot/`) and
`EveOnline/VolatileProcessInterface.elm`/`EveOnline/MemoryReading.elm` (the
sub-protocol for the memory-reading "volatile process"). Key findings:

- `Bot.elm` exposes `botMain : InterfaceToHost.BotConfig State`, where
  `BotConfig state = { init : state, processEvent : BotEvent -> state ->
  (state, BotEventResponse) }` — **a plain Elm value, not a runnable
  `Program`**. BotLab.exe's actual toolchain is built on "Pine" (a custom
  Elm interpreter/VM referenced via `Pine.Json.JsonConverterForChoiceType`
  in a code comment), not vanilla `elm make` — it apparently interprets
  `botMain` directly and auto-derives JSON codecs for the interface types
  by some reflection-like mechanism, which we do **not** have and are
  **not** trying to replicate.
- Instead: **the bot's own source code is 100% ordinary, standard Elm**
  that compiles fine with vanilla `elm make` (confirmed — see below). The
  fix is to write our own small wrapper module (`Main.elm`, added
  alongside the fetched bot source, not part of it) that turns `botMain`
  into a real `Platform.worker` program with two `port`s (`eventIn`,
  `responseOut`) carrying JSON strings, with **hand-written** encoders/
  decoders for the `BotEvent`/`BotEventResponse`/`Task`/etc. type surface.
  Since we control both sides (the Elm wrapper and the Python host), the
  JSON convention doesn't need to match Pine's real wire format — only
  `EveOnline.VolatileProcessInterface`'s hand-written codecs (used
  *inside* the opaque `RequestToVolatileProcess.request : String` field)
  need to match exactly, since those are unmodified bot source we don't
  touch.
- **The memory-reading protocol is carried as an opaque string, not a
  top-level host interface type.** `Task = ... | RequestToVolatileProcess
  RequestToVolatileProcessConsideringInputFocusStructure | ...`, where
  the actual request is `{ processId : String, request : String }` — that
  inner `request` string is JSON built by
  `VolatileProcessInterface.buildRequestStringToGetResponseFromVolatileHost`
  (`ListGameClientProcessesRequest` / `SearchUIRootAddress { processId }`
  / `ReadFromWindow { windowId, uiRootAddress }`), and the response comes
  back the same way, deserialized with
  `VolatileProcessInterface.deserializeResponseFromVolatileHost`. On
  Windows, BotLab.exe actually runs the C# `EveOnline/VolatileProcess.csx`
  (whose literal source is what
  `CompilationInterface.SourceFiles.file____EveOnline_VolatileProcess_csx`
  normally gets replaced with at Pine-toolchain build time — currently a
  placeholder string `"The compiler replaces this declaration."`, confirmed
  live below) as a real child process and forwards these request strings
  to it. **We do not run this C# code at all.** Since
  `RequestToVolatileProcess`'s `programCode`/response are opaque strings
  as far as the top-level interface is concerned, our host can fake being
  a competent volatile process entirely in Python: parse the incoming
  `VolatileProcessInterface`-shaped JSON, dispatch
  `ReadFromWindow`/`SearchUIRootAddress`/`ListGameClientProcessesRequest`
  to our own macOS memory-reading tools (`re_helper.py`'s `tree` walker
  IS a `ReadFromWindow` implementation — its JSON output shape already
  matches `EveOnline.MemoryReading.uiTreeNodeDecoder` almost exactly:
  `pythonObjectAddress`/`pythonObjectTypeName`/`dictEntriesOfInterest`/
  `children`), and hand back a JSON string in the exact shape
  `VolatileProcessInterface.elm`'s decoders expect.
- `ReadFromWindowResult.Completed.memoryReadingSerialRepresentationJson`
  is itself `Maybe String` — **the actual UI tree JSON is double-encoded**
  (a JSON string containing JSON), decoded downstream via
  `EveOnline.MemoryReading.decodeMemoryReadingFromString`. Our
  `RequestToVolatileProcess` response needs to nest our tree JSON as a
  string inside the outer `ReadFromWindowResult` envelope, not inline it
  directly.
- **`dictEntriesOfInterest` values are not all primitives.**
  `getDisplayText` in `ParseUserInterface.elm` looks up `_setText`/`_text`
  and, if the raw value isn't a JSON string, falls back to decoding it as
  *another full `UITreeNode`* (`Json.Decode.oneOf [string, ...
  uiTreeNodeDecoder ...]`) — a documented real case: `_setText` can hold a
  Python `Link` object whose own `_text` sub-attribute has the actual
  text. This means Sanderling's original serialization recursively
  encodes "interesting" non-primitive attribute values in the same
  `UITreeNode` shape too, not just the `children` list. **Our
  `describe_primitive` in `re_helper.py` currently drops any non-primitive
  value entirely** rather than recursively encoding it — a known,
  not-yet-fixed gap for full fidelity (primitives: confirmed working;
  `_displayX`/`_displayY`/etc. are read via `Json.Decode.float`, which
  happily accepts our plain JSON integers too, so no compatibility issue
  there specifically).
- The main operating loop (`getSetupTaskWhenVolatileProcessSetupCompleted`
  in `EveOnline/BotFramework.elm`) issues **two parallel reads per
  cycle**: the memory-based `ReadFromWindow` (via
  `RequestToVolatileProcess`, with `acquireInputFocus` — it wants
  keyboard/mouse focus before this read) *and* `InvokeMethodOnWindowRequest
  ("winapi-" ++ mainWindowId) ReadFromWindowMethod` (a **screenshot-based**
  read returning `windowRect`/`clientRect`/`clientRectLeftUpperToScreen`/
  `imageData` pixel crops) — the latter supplies
  `lastReadFromGameClientRectLeftUpperToScreen`, used to translate
  memory-read UI element positions into absolute screen coordinates for
  effects. **We need both**, not just the memory read: window-rect/DPI
  info from our existing `window_probe`, pixel data from `screencapture`
  (exact `pixelsString` encoding format not yet reverse-engineered — next
  thing to check, probably in `ParseGuiFromScreenshot.elm` or wherever
  decodes it).
- Effects go out as `WindowsInputRequest (List WindowsInputSequenceItem)`
  — `KeyDown`/`KeyUp`/`MouseMoveAbsolute`/`ButtonDown`/`ButtonUp`/
  `ButtonScroll`/`CharacterDown`/`CharacterUp`/`BringWindowToForeground`/
  `AbortIfWindowNotInForeground`/`WaitMilliseconds`, always preceded by
  `BringWindowToForeground` + a 100 ms wait in the actual bot code. Key
  codes here are **Windows virtual-key codes** (see
  `Common/EffectOnWindow.elm`'s `VirtualKeyCode` type/
  `virtualKeyCodeAsInteger`) — need a VK-code -> macOS `CGKeyCode`
  translation table; not yet built.

### Done: Elm toolchain set up and working on this arm64 Mac

- `elm` wasn't installed; `npm install -g elm` silently grabbed an
  unrelated, much newer npm package that happens to squat the name `elm`
  (real Elm's last npm-published version is `0.19.1`; the npm `elm`
  package's `latest` dist-tag point at something else entirely, `2.0.0`
  at the time of checking) — **don't use bare `npm install -g elm`**.
  Explicitly requesting `elm@0.19.1` also failed here: its postinstall
  script tries to download
  `https://github.com/elm/compiler/releases/download/0.19.1/binary-for-mac-undefined.gz`
  — literally `-undefined-` in the URL, i.e. the installer's
  architecture-detection is broken for arm64 Macs (official Elm 0.19.1
  binaries were only ever published for Intel Mac).
  **Fix: `brew install elm`** — Homebrew ships a bottled, arm64-native
  build, self-reported version `0.19.2` (not an official Elm release
  number; presumably Homebrew's own patched build for arm64 support).
- That version string then collides with `elm.json`'s strict
  `"elm-version"` field (application-type `elm.json` requires an *exact*
  match, unlike package-type's ranges) — every existing bot app's
  `elm.json` says `"0.19.1"`, causing `elm make` to refuse to run at all.
  **Fix: rewrite `elm-version` to `"0.19.2"`** in a working copy of the
  bot's `elm.json` before compiling (never edit the original checked-in
  file — this is host-side preprocessing, done automatically by the
  launcher on a fetched copy). No functional/language-level
  incompatibility found from this so far — the genuinely unmodified
  `eve-online-warp-to-0-autopilot` app (16 modules) compiled clean on the
  first real attempt after this one-line patch.

### Done: wrote `Main.elm` (the port wrapper) and validated it against a real, unmodified bot end-to-end

Built (currently in scratch, at
`/private/tmp/.../scratchpad/bot-test/Main.elm` — **needs to move into
the repo**, e.g. `tools/macos-host/botlab-launcher/Main.elm`, as a
template the launcher copies alongside any fetched bot source before
compiling) the full wrapper described above: `port module Main`, hand-
written `encodeBotEventResponse`/`decodeBotEvent` (and everything they
recursively need — `Task`, `WindowsInputSequenceItem`,
`TaskResultStructure`, `ReadFromWindowCompleteStruct`, etc.) covering the
whole `BotInterface_To_Host_2024_10_19` type surface, `Platform.worker`
wiring `Bot.botMain`. OpenWindow/WebView-specific branches are stubbed
minimally (encoded/decoded just enough to satisfy exhaustiveness
checking) since the EVE bots don't use them — would need filling in for
a browser-based bot (e.g. `tribal-wars-2-farmbot`).

**Compiled clean on the first real attempt** against the totally
unmodified `eve-online-warp-to-0-autopilot` app.

**Ran it in Node and got fully correct, real bot logic back**, proving
the entire compile + port-wiring approach end to end:
1. Sent `{"BotSettingsChangedEvent": ""}` → bot replied
   `ContinueSession` accepting empty settings, asking to be called back
   immediately.
2. Sent `{"TimeArrivedEvent": null}` → bot replied with the *exact*
   expected real startup sequence: a `CreateVolatileProcess` task (two of
   them actually — one from `EveOnline.BotFramework` itself, one from a
   `NotificationsShim` sub-system bundled into the framework, not yet
   investigated but probably safe to no-op/fail harmlessly), plus a
   `RandomBytesRequest 300` task.
3. First attempt without step 1 correctly produced `FinishSession` with
   the real error message the framework itself generates ("Unexpected
   order of events: I did not receive any bot-settings changed event"),
   confirming decode/encode fidelity rather than a lucky accident.

### Not yet done — the actual host, and everything after initial setup

This is the real remaining work, roughly in dependency order:

1. **Move `Main.elm` into the repo as a template** (`tools/macos-host/`
   somewhere) and write the bot-fetching layer: given a GitHub URL
   (`git clone`/download+extract) or a local file/directory path, locate
   `Bot.elm` + its sibling framework `.elm` files + `elm.json`, copy to a
   working directory, patch `elm-version`, copy `Main.elm` in, run
   `elm make Main.elm --output=bot.js --optimize`.
2. **Write the Python host's task dispatcher** — the real engineering
   core. Needs handlers for: `CreateVolatileProcess` (fake success,
   ignore `programCode`), `RandomBytesRequest` (real random bytes),
   `RequestToVolatileProcess` (parse the inner JSON per
   `VolatileProcessInterface.elm` above, dispatch
   `ListGameClientProcessesRequest` to `lsappinfo`/`window_probe`-style
   process/window enumeration, `SearchUIRootAddress` to our root-finding
   technique — **note: our root-finding so far always started from a
   known widget found via the repr-scan-on-a-full-dump technique; doing
   this live, without a dump, from a cold start with zero known addresses
   is a genuinely new problem, not yet solved** — and `ReadFromWindow` to
   `re_helper.py`'s live tree walker), `InvokeMethodOnWindowRequest
   ReadFromWindowMethod` (window rect/DPI + screenshot pixel data, format
   TBD), `WindowsInputRequest` (VK-code -> CGEventPost translation, TBD).
3. **The main loop**: `init`, then repeatedly send `TimeArrivedEvent` (or
   whatever `notifyWhenArrivedAtTime` asks for), dispatch `startTasks`
   concurrently/in whatever order, feed `TaskCompletedEvent`s back in,
   stop on `FinishSession`.
4. Fix the `dictEntriesOfInterest` non-primitive gap noted above
   (recursively encode "interesting" nested objects in `UITreeNode` shape
   instead of dropping them) if/when a bot actually breaks on it.
5. GitHub-URL fetching specifically (vs. the file-path case, which is
   nearly free once step 1's directory-locating logic exists) — decide
   git-clone vs. tarball download, handle the app potentially living in a
   subdirectory of a larger repo (this very repo is an example: apps live
   under `implement/applications/...`).

### Done (2026-07-26): built and validated the full host — real bot, real decisions, from both a file path and a GitHub URL

Everything in "Not yet done" above got built in this session. Code lives
in `tools/macos-host/botlab_host/` (`botlab_host.py`, `Main.elm`,
`driver.js`). This is the actual "drop-in BotLab.exe replacement" —
working, not just planned.

**Bot source acquisition, both URL forms work:**
- Local file/directory path (also `file://` prefix): used directly.
- GitHub URL, either a plain repo (`https://github.com/owner/repo`) or a
  `.../tree/<branch>/<subpath>` URL pointing at a subdirectory (needed
  since apps in *this* repo live under `implement/applications/...`, not
  at the repo root) — `git clone --depth 1 --branch <branch>`, then the
  subpath. Both cases then search recursively for `Bot.elm` if it's not
  found directly at the given location.
- Tested for real against `https://github.com/Viir/bots/tree/main/implement/applications/eve-online/eve-online-warp-to-0-autopilot`
  (this repo's own real GitHub remote) — clone, locate, patch, compile,
  and run all succeeded identically to the local-path case.

**`driver.js`**: a thin Node bridge from `Main.elm`'s ports to
newline-delimited JSON over stdin/stdout, so the Python host can drive
the compiled bot as an ordinary subprocess (write one `BotEvent` JSON
line in, read one `BotEventResponse` JSON line out) without needing a
browser or any bot-specific JS.

**`TaskDispatcher`/`VolatileHost` in `botlab_host.py`** implement the
task types real EVE bots actually use:
- `CreateVolatileProcess` — fake success, ignores `programCode` entirely
  (we never run the Windows C# `.csx`; see the architecture note above
  for why this is fine).
- `RandomBytesRequest` — real `os.urandom`.
- `RequestToVolatileProcess` — parses the inner JSON per
  `VolatileProcessInterface.elm` and dispatches:
  - `ListGameClientProcessesRequest` — `lsappinfo list` for the
    `com.ccpgames.eveonline` pid, `window_probe --all` (new flag, see
    below) for its window, picking the largest `layer >= 0` window by
    area (same anti-overlay-strip heuristic as `save_process_sample.sh`).
  - `SearchUIRootAddress` — genuinely async (matches the real protocol's
    `InProgress`/`Completed` staging): spawns a background thread that
    takes a one-time `memory_sample` dump, repr-scans it for `UIRoot`
    (falling back to any known widget class + `walk_to_root` via
    `_parentRef`, both now proper reusable functions in `re_helper.py` —
    `repr_scan`, `walk_to_root`, `find_ui_root`), caches the result; all
    *later* `ReadFromWindow` calls for that process then use the fast
    `LiveSample` path, no more dumps needed. First real run took a few
    seconds, same order of magnitude as BotLab.exe's own Windows
    implementation (the bot's own status text literally says "This can
    take several seconds").
  - `ReadFromWindow` — `re_helper.py`'s `build_tree`, live, wrapped as
    `memoryReadingSerialRepresentationJson` (a JSON **string** nested
    inside the response, matching `MemoryReading.elm`'s double-encoding).
- `InvokeMethodOnWindowRequest ReadFromWindowMethod` — real window rect
  via `window_probe --all` (see below); `imageData` (screenshot pixel
  crops) is still an empty stub (format not reverse-engineered), which
  the bot has tolerated fine so far for this particular app.
- `WindowsInputRequest` — **not yet executed**, deliberately. Logged
  instead of sent to `CGEventPost`, because actually wiring this up means
  the host takes over the real mouse/keyboard on the user's live game
  session — held off pending explicit go-ahead rather than silently
  starting to click things. See "Deliberately not done" below.

**`window_probe` gained an `--all` flag** (`kCGWindowListOptionAll`
instead of `kCGWindowListOptionOnScreenOnly`) — confirmed empirically
that this returns correct bounds for windows on *any* macOS Space,
including a fullscreen game window on a Space that isn't currently
active, without needing the Space-switch dance every other tool in this
project has needed so far. This directly fixes the earlier `mainWindowTitle`
mismatch bug (`find_eve_processes` was falling back to the launcher's
on-screen "EVE Launcher" window instead of the real fullscreen game
window, since the old on-screen-only query couldn't see the latter at
all when it wasn't the active Space) and is what the corrected
`ReadFromWindowMethod` rect now uses.

**Two real bugs found and fixed by actually running this against the
live game, not just reading the protocol:**
1. `re_helper.py`'s `str`-type bootstrap (`cmd_walkdict`/`cmd_tree`, and
   now `botlab_host.py`) assumed a dict's first inline slot (`+0x38`) is
   always populated — it's a sparse hash table, and slot 0 being empty is
   common. Fixed with a proper `bootstrap_str_type()` that uses
   `walk_dict_entries` to find *any* real key instead of blindly reading
   one fixed offset. This bug existed all session but was never
   triggered by the specific objects tested against until now.
2. The host's main loop only processed the *first* task in a response's
   `startTasks`, silently discarding the rest whenever a response offered
   several at once — which the real per-cycle read does (memory read +
   screenshot read together). Also needed to pick up genuinely *new*
   tasks appearing in a later response (e.g. the `SearchUIRootAddress` ->
   `ReadFromWindow` transition). Fixed with a proper queue keyed by
   `taskId`, seeded from each response's full `startTasks` and extended
   with any not-yet-seen task from every subsequent response, drained
   until empty.

**End-to-end result, live against the running game (pid varies per
launch, both file-path and GitHub-URL source), no game-specific special
casing anywhere in the host:** the bot correctly worked through the
*entire* real startup sequence (settings -> create volatile process ->
random bytes -> list game clients -> search UI root (several seconds,
async, correctly polled) -> first successful `ReadFromWindow`), then
entered its normal operating loop and made **genuinely correct decisions
from live game memory**: `"I see the ship is warping or jumping. I wait
until that maneuver ends."`, `"+ Open context menu on route element
icon"`, and computed real screen coordinates for the click it would
send. This is not a scripted demo — it's the bot's own unmodified
decision-tree logic (`EveOnline/BotFrameworkSeparatingMemory.elm`'s
`DecisionPathNode` machinery) running against real, live-read UI state.

**Deliberately not done, holding for explicit confirmation before
proceeding:** actually executing `WindowsInputRequest` via
`CGEventPost`. Two reasons to pause here rather than wire it up
silently: (1) it means the host takes over the real mouse and keyboard
on the user's live, running game session — a consequential,
outward-facing action, not a reversible local one; (2) the computed
coordinates in testing (e.g. `y=1684` for a window only `1069` points
tall) look like they may have a points-vs-backing-pixels scale mismatch
(this display reports `backing_scale=2.0`) that should be understood
*before* anything actually clicks, not discovered by watching a
misclick happen live.

**Smaller known gaps, not blocking anything so far:**
- `dictEntriesOfInterest` still only encodes primitives (see the
  Python-2-type-system section above) — the documented case where
  Sanderling's original serialization recursively encodes "interesting"
  non-primitive attribute values (e.g. `_setText` holding a `Link`
  object) in full `UITreeNode` shape isn't implemented. Symptom observed
  live: the bot printed `"current solar system: Unknown"` — plausibly
  this exact gap (a name field that isn't a plain string in memory).
- Screenshot pixel data (`imageData`) is an empty stub; format not
  reverse-engineered. Tolerated fine by this bot so far, may not be for
  others (a bot using `ParseGuiFromScreenshot.elm`'s OCR fallback path
  would need it).
- Elm toolchain setup (npm gotcha, Homebrew version patch,
  `elm-version` rewrite) is currently manual/undocumented-as-a-script —
  works, but `botlab_host.py` doesn't check/bootstrap it itself yet if
  `elm` isn't on `PATH`.

### Done (2026-07-26): real input execution wired up and confirmed working live, closing the loop completely

User explicitly said to proceed with real input execution ("wire it up, my
body is ready") after reviewing the coordinate-scale concern above.

**Built `tools/macos-host/cg_input/cg_input.c`** — a persistent process
(same pattern as `live_reader`) that reads text commands from stdin
(`move x y`, `down/up <button>`, `drag x y <button>`, `keydown/keyup
<code>`, `scroll dx dy`) and executes them via `CGEventPost`. Coordinates
are in points, the same space `window_probe` reports (confirmed
authoritatively — see below, not assumed).

**Resolved the coordinate-scale question empirically instead of
guessing.** Wrote a tiny diagnostic (`CGEventGetLocation` round-trip):
commanded a move to `(10, 10)` via `cg_input`, then immediately queried
the actual cursor position independently — it read back exactly `(10.0,
10.0)`. This proves two things at once: `CGEventPost` needs real points
(not backing pixels) with no permission issues, **and** the earlier
out-of-range coordinates (`y=1684` on a `1069`-point-tall window) must
come from a units mismatch *upstream*, in what the bot itself computes,
not in how input gets executed.

Traced the real cause: `effectOnWindowAsWindowsInputSequenceItem` in
`BotFramework.elm` does a plain, unscaled addition — `uiRelativePosition
+ clientRectLeftUpperToScreen` — with no DPI correction anywhere in the
bot's own code. Cross-checked a known UI element's raw `_displayX` value
(~2007, from earlier in this session) against the window's actual point
width (1710) — 2007 only makes sense if the game's internal UI coordinate
system spans the full **backing-pixel** resolution (3420 for a
1710-point/2x-backing-scale window), not points. So both terms of that
addition need to already be in the same ("game pixel") units for the sum
to come out right.

**Fix, entirely on the host side, bot code untouched:** `window_probe`'s
`--all` output already reports `backing_scale` per window/display;
`ReadFromWindowMethod`'s response now multiplies `windowRect`/
`clientRect`/`clientRectLeftUpperToScreen` by that scale before handing
them to the bot (so its internal arithmetic lands in "game pixel" units,
matching `_displayX`/`_displayY`), and `_windows_input` divides
`MouseMoveAbsolute` coordinates by the same scale immediately before
calling `cg_input` (converting back to the real points `CGEventPost`
needs). One consistent scale factor at both boundaries, nothing guessed
mid-pipeline.

**Built the Windows-VK-code -> macOS `CGKeyCode` table** (`_VK_TO_CGKEYCODE`
in `botlab_host.py`) — explicit lookup, not arithmetic, since neither
side is contiguous for letters/digits (`Common/EffectOnWindow.elm`'s
`vkey_*` are standard Windows virtual-key codes; macOS `kVK_*` constants
follow a physical-key-position ordering with no relationship to either
ASCII or the Windows numbering). Covers letters, digits, function keys,
common punctuation, arrows, and modifiers/whitespace/backspace/escape.
Not yet exercised live (the tested bot's `send-effects` tasks were mouse-
only so far), but compiles and is wired into `KeyDown`/`KeyUp` handling.

**`--execute-input` flag, off by default.** Without it, `WindowsInputRequest`
still just logs what would have been sent (yesterday's safe default,
preserved for dry runs). With it, `_windows_input` actually dispatches
each `WindowsInputSequenceItem` to `cg_input` (mouse) or the VK table
(keyboard), plus `BringWindowToForeground` via `osascript`/System Events
using the real game pid (now tracked on `VolatileHost.game_pid`,
populated from `ListGameClientProcessesRequest`). `MouseMoveRelative` and
`CharacterDown`/`CharacterUp` (raw Unicode text input) are recognized but
not implemented yet — not exercised by the tested bot, reported as
explicit errors in `WindowsInputResponse` rather than silently
mishandled if a bot does ask for them.

**Confirmed working against the live game, for real:** ran with
`--execute-input`, watched the bot repeatedly attempt "open context menu
on route element icon", then took a screenshot mid-run —
**a real context menu was genuinely open on screen** ("Look At My Ship",
"Show Info", "Show Solar System in Map Browser", "Asteroid Belts",
"Planets", "Stargates", "Anomalies", "Clear All Waypoints"), opened by an
actually-executed right-click landing exactly on the route element icon
in the top-left panel. The bot's own follow-up complaint ("Could not find
menu entry with text containing first available of 'dock'... 'jump'...")
is *correct, sensible bot behavior* given this specific menu genuinely
doesn't have those entries right now (no stargate/station immediately
actionable from the current route waypoint) — not a host bug. This is the
full loop, closed: real memory read -> real decision -> real click ->
real menu opens -> real next read -> real next decision.

**What's left, all refinements rather than open architectural
questions at this point:**
- `dictEntriesOfInterest` non-primitive gap (documented above) — likely
  behind the `"current solar system: Unknown"` symptom.
- Screenshot pixel data (`imageData`) still an empty stub.
- `MouseMoveRelative` / `CharacterDown` / `CharacterUp` unimplemented.
- No automated Elm-toolchain bootstrap if `elm` isn't already on `PATH`.
- Only tested against one bot app (`eve-online-warp-to-0-autopilot`) and
  one machine/display config — other bots (especially non-EVE ones using
  `OpenWindowRequest`/browser automation, which is stubbed to always
  fail) or a different display arrangement (single monitor, no Retina
  scaling, multiple displays) haven't been exercised.

### Done (2026-07-26): input latency fix, then real screenshot pixel encoding implemented

**Bug found from real usage, not inspection: input felt sluggish.** User
reported a long delay between a context menu opening and the click on it
landing. Root cause was two things the earlier safety-gating work (see
"real input execution" above) had introduced:
1. `bring_window_to_foreground` unconditionally ran `osascript` +
   `time.sleep(0.35)` on *every* `BringWindowToForeground` task, even
   when the game was already frontmost — which is the overwhelmingly
   common case, since `BotFramework.elm` prepends this task to every
   single input sequence. Fixed with a fast path: check
   `_window_is_onscreen()` first, skip the activate-and-sleep entirely
   if already there.
2. A per-action safety check (verify the target window is still
   onscreen) was being run before *every individual* mouse/keyboard
   action in a sequence, each spawning a `window_probe` subprocess —
   redundant, since that condition can't meaningfully change between two
   `CGEventPost` calls a few milliseconds apart. Narrowed to check only
   at the sequence's actual checkpoints (`BringWindowToForeground`/
   `AbortIfWindowNotInForeground`, which the bot's own protocol already
   controls), not per action.

Verified the fix didn't just move the cost: ran a real 60-tick session
against the live game with `--execute-input` and confirmed zero
foreground-recovery failures throughout (i.e., the game never actually
lost focus during real unattended operation — the checks are cheap
*because* the common case is genuinely "already fine", not because
safety was cut). A misleading 439ms-overhead measurement from an
isolated benchmark turned out to be a testing artifact (a concurrent
tool call had stolen focus to the terminal's own macOS Space mid-test) —
worth remembering: an isolated timing test can be contaminated by
whatever else is competing for foreground/Space state on the machine at
that moment; the real signal is whether the *live, unattended* run shows
recovery events, not a one-off benchmark number.

That same 60-tick run is a strong end-to-end validation on its own: the
ship genuinely warped, jumped through a stargate, and picked up a new
onward route — real navigation driven entirely by memory-read decisions
and executed clicks, not a fluke. ("jumps completed: 0" in the bot's own
status line never incremented because that counter resets whenever the
bot's internal decision state restarts, not because nothing happened —
the screenshot evidence and the route panel updating to a fresh
77-jump route confirm real progress.)

**Then: implemented the screenshot pixel encoding** (`pixelsString`
format), the last major documented gap. Fully reverse-engineered from
source, not guessed:
- `ImageCrop.pixelsString` is a plain JSON array of integers, one per
  pixel, row-major (`index = y * widthPixels + x`); height is implied by
  `array length / widthPixels` (no separate height field). Confirmed by
  reading `parseImageCropPixelsArrayFromPixelsString`
  (`Json.Decode.array Json.Decode.int`) in `BotFramework.elm`.
- Each int packs a pixel as `0x00RRGGBB` — red at bits 16-23, green at
  8-15, blue at 0-7 — confirmed via `colorFromInt_R8G8B8`
  (`BotFramework.elm:1302`): `shiftRightZfBy 16 |> and 0xFF` etc.
- `ImageCrop.offset` is in the same coordinate space as
  `clientRectLeftUpperToScreen` (our self-calibrated "game pixel" units,
  see the coordinate-scale section above) for the `_original` crops, but
  **pre-divided by the binning factor** for `_binned_2x2`/`_binned_4x4` —
  confirmed via `pixelFromCropsInClientArea`'s `clientRectOffset.x //
  binningFactor` in `BotFramework.elm:879`.
- The three resolutions (`_original`, `_binned_2x2`, `_binned_4x4`) are
  genuine area-averaged downsamples of the same capture, not independent
  images — implemented with PIL's `Image.BOX` filter, which is a true
  block-average, the semantically correct operation for "pixel binning"
  (as opposed to a resize filter like bilinear/Lanczos, which would blur
  rather than average discrete blocks).

**Implementation: `capture_image_data()` in `botlab_host.py`** —
`screencapture -x -o -l <window_number>` for the real pixels, then PIL
resize/pack. Verified byte-for-byte correct by round-tripping a real
capture: decoded a `pixelsString` back into an image and it exactly
matched the live game screen (ship, UI panels, everything legible).

**Two real performance findings, both addressed rather than shipped
silently:**
1. **A genuine bug**: `numpy` wasn't installed, so the packing function's
   try/except fell back to a pure-Python per-pixel loop — 5.2s of an
   8.2s total capture, just for that one loop. Installed numpy
   (`pip install --user --break-system-packages numpy` — Homebrew's
   Python blocks unscoped installs per PEP 668; `--user` keeps it scoped
   to this account, not the Homebrew-managed site-packages). Vectorized
   packing (`(arr[:,:,0]<<16)|(arr[:,:,1]<<8)|arr[:,:,2]`) brought total
   capture time from 8.2s down to 2.65s for all three crops.
2. **An inherent, not-a-bug cost**: even fixed, a full-resolution
   `_original` crop covering the whole window packs to ~66MB of JSON
   text per read cycle — a real, unavoidable property of sending every
   pixel of a Retina window as individual JSON integers, not something
   further optimization removes. Checked whether this bot's code even
   uses that data before paying for it: **it doesn't** —
   `EveOnline.BotFramework`'s `screenshot` record only ever reads
   `pixels_1x1`/`pixels_2x2` (from `_original`/`_binned_2x2`
   respectively), and grepping the whole bot source found **zero** call
   sites that actually read `pixels_1x1`; `_binned_4x4` isn't even wired
   into the `screenshot` record at all. Asked the user how to handle
   this rather than silently deciding; chose to **stop generating
   `screenshotCrops_original`** (send `[]`, which is valid per the type)
   while still fully computing `_binned_2x2` and `_binned_4x4` — cuts
   capture time to 1.58s, dominated by `screencapture` itself (~0.77s)
   and the one crop (`_binned_2x2`, ~16MB) this bot's framework can
   actually consume. `_original` support can be added back trivially
   (the code to build it already existed and worked, just isn't called)
   if a bot that genuinely reads `pixels_1x1` shows up.

**Verified against the real Elm decoder, not just Python-side:** ran the
full bot loop again with the new `capture_image_data` wired in --
reached `InvokeMethodOnWindowRequest`/`ReadFromWindowMethod` multiple
times with the real (now non-empty) `imageData` payload, no decode
errors, no `FinishSession`, loop kept advancing normally. Confirms the
JSON shape produced (`{"offset", "widthPixels", "pixelsString"}` per
crop) matches what `Main.elm`'s hand-written `decodeImageCrop` actually
expects, not just what the format spec implied on paper.

**Still open:** `screenshotCrops_original` is now deliberately empty by
default rather than unimplemented — worth remembering the distinction if
revisiting this. `dictEntriesOfInterest` non-primitive gap (recursively
encoding nested "interesting" objects like a `Link`'s `_text`) remains
the one other documented gap from the original protocol writeup.

### Done (2026-07-26): sub-1s tick push — screenshot capture made opt-in, then a real breadth-first rewrite of build_tree, which surfaced and fixed a genuine pipe deadlock bug

Follow-up to the input-latency fix above. User's goal: each bot-loop tick
under 1 second, ideally. Root-caused two independent, much larger costs
than input latency.

**1. Screenshot capture made opt-in (`--capture-screenshots`, default
off).** Even the scoped-down (binned-only) capture from the earlier
session still costs ~1.6s/cycle, dominated by the `screencapture` CLI
call itself. `eve-online-warp-to-0-autopilot` never reads screenshot
pixel data at all (confirmed via `dictEntriesOfInterest` -- er, via grep,
see the screenshot-encoding section above), so paying that cost by
default for every bot regardless of need was the wrong tradeoff once
speed became the explicit goal. Same `--execute-input`-style opt-in
pattern; a bot that needs it can request it, but nothing pays for it
unless asked.

**2. Root cause of the *real* remaining cost: `build_tree`'s live UI tree
is much bigger than anything benchmarked so far.** Measured directly:
`ReadFromWindow`'s memory-read tree walk alone (`max_depth=12,
max_nodes=4000`) took **3.08s** for a real 2664-node tree on this
machine's live game session -- nearly 10x the size of the 800-node
tree all the earlier per-node round-trip-batching work
(the "8.2x faster" result) had been benchmarked against. At ~13.5 round
trips/node, that's ~36,000 round trips for one single memory read, once
per bot-loop tick.

**Rewrote `build_tree` from per-node depth-first recursion to
breadth-first, level-batched traversal** -- collapses every node at the
same tree depth into a handful of shared batched round trips (one
combined type+dict-pointer fetch, one dict-header fetch, one inline-block
fetch, one overflow-block fetch, one key-name-decode fetch, etc. -- each
covering the *whole level*, not one node), instead of paying that same
~13-item sequence once per individual node. New helper functions
`_batch_dict_walk` (the dict-header/inline/overflow-block engine, shared
between node-attribute dicts and the smaller `PyChildrenList` bookkeeping
dict) and `_batch_decode_keys` (batched key-string decoding) factor out
the now-cross-node-shared logic; `build_tree`'s outer loop processes one
level (`current_level`) at a time and assembles the final nested
`UITreeNode` structure only at the very end, once every node's data has
been collected, via a cheap in-memory recursive `assemble()` pass (no
round trips -- pure dict lookups).

**Verified correctness rigorously before trusting it, given the size of
the rewrite:** reconstructed the old per-node implementation in a
throwaway module (`old_build_tree.py`) and diff-compared its full,
uncapped output against the new implementation's, node-by-node,
attribute-by-attribute, over the entire ~2759-node live tree (captured in
a fresh sample) -- **zero diffs** after one real bug was found and fixed
(below). Cross-checking against a reconstructed "old" implementation
rather than just trusting the new code's own internal consistency is
what caught the one genuine behavioral regression this rewrite
introduced.

**Real bug #1, found by the correctness diff, not by inspection: a
silent semantic change in duplicate-key handling.** The custom dict's
inline block and overflow block can hold genuine duplicate keys with
*different* values -- a known, previously-unexplained oddity from much
earlier this session ("possibly a small recently-touched cache vs the
authoritative backing store, not investigated further"). The old
per-node code's duplicate-resolution was *implicit and accidental*: `dict_items`
didn't dedupe at all, and `build_tree`'s dict-assignment loop
(`node["dictEntriesOfInterest"][key] = value`) naturally kept
whichever occurrence came *last* in iteration order (inline-then-overflow,
so overflow wins) for ordinary attributes, but used `next(...)`
(first-match) specifically for finding the `'children'` key. The new
batched code deduped explicitly but picked *first*-occurrence-wins
uniformly, silently flipping real attribute values (e.g. a `busy` flag
read `True` vs `False` depending on which implementation walked it) for
any node with duplicate dict entries. Fixed to replicate the old
behavior exactly (last-wins for ordinary attributes, first-wins for
`children`), since which underlying copy is actually "correct" remains
genuinely unresolved -- this wasn't the place to pick a new policy, only
to preserve established, working behavior.

**Real bug #2, much more serious, found only once testing scaled past
what earlier development had exercised: a genuine, unconditional pipe
deadlock in `LiveSample.read_bytes_batch`.** Discovered when a live run
with `max_depth=12` (deep enough to reach a wide tree level, ~110 nodes,
each with many attributes) simply hung forever -- not slow, actually
stuck, confirmed via `ps` showing `live_reader` at a static 0% CPU for
several minutes. Root-caused with targeted, flushed debug prints added
directly into the traversal (binary-search-style: narrowed from
"which level" to "which batch call" to "which specific request count")
rather than guessing: a single `_batch_decode_keys` call for that
level needed to fetch 6,458 keys in one round trip -- a **103KB request
payload**, comfortably over the OS's default pipe buffer size (~64KB on
macOS). `read_bytes_batch`'s original design wrote the *entire* request
payload in one blocking `stdin.write()` call, only *then* looping to
read responses. Once a request payload exceeds the pipe buffer, that
`write()` blocks waiting for the reader to drain it -- but
`live_reader.c`'s own reply-writing can *also* block once *its* output
pipe fills (since Python hasn't started reading responses yet, still
stuck inside the initial write) -- both sides end up blocked waiting on
each other, forever. This had been a latent, unconditional bug in the
protocol's design since the pipelining work was first built (not
something the breadth-first rewrite introduced -- it just increased
individual batch sizes enough to finally trigger the pre-existing
threshold). **Fixed with the standard technique for this exact class of
bidirectional-pipe problem** (the same reason `subprocess.communicate()`
itself uses threads/select internally): a background thread now performs
the `stdin.write()` while the main thread concurrently reads responses,
so neither direction can ever block the other regardless of batch size.
Re-verified correctness held after this fix too (same zero-diff
comparison against the reconstructed old implementation).

**Net result, measured, not assumed:** the standalone live tree-walk
benchmark that used to hang *forever* past a certain tree width now
completes reliably in **2.277s** for a 2,988-node tree, using only
**2,010 round trips** (down from ~35,956 for the same-sized tree under
the old per-node approach -- roughly an 18x reduction in round-trip
count). Real end-to-end bot-loop ticks (the actual thing the user's goal
was measuring), with both this fix and the screenshot opt-in change
active, dropped from **8-11s/tick to 4-5s/tick** in a real 25-tick run
against the live game.

**Honest status against the "under 1 second" goal: not yet met.** The
critical, correctness-threatening bug (the deadlock) is fixed and the
walk is meaningfully faster, but round-trip *count* is no longer the
dominant cost at this point -- the remaining ~2.3s for the memory-read
step is now dominated by the sheer *data volume* a ~3,000-node live UI
tree requires (megabytes of key names, dict headers, and attribute
values crossing the pipe and being parsed in Python), not per-round-trip
latency. Next levers, not yet attempted, roughly in order of
expected-effort-to-payoff:
- Check whether `max_nodes=4000` (currently: walk essentially the
  *entire* on-screen UI, every single cycle) is actually necessary for
  this bot's real decision logic, versus whether it could be scoped down
  -- risky to do blindly (the tree search for named windows conceptually
  needs to reach anywhere in the tree), but worth checking empirically
  whether specific large subtrees (e.g. background scene layers, chat
  history) are ever actually consulted by `ParseUserInterface.elm`'s
  parsers for this specific bot.
- Reduce the `_PYSTR_OPTIMISTIC_CHUNK` size (currently 256 bytes,
  requested for *every* string-shaped read including short attribute
  names) if profiling shows most real strings are much shorter --
  smaller requested chunk sizes directly cut response data volume.
  Symmetric idea also came up mid-session ("what if we made EVE not
  fullscreen to save on rendering cycles") -- worth trying independently,
  since the EVE client itself was observed consuming ~75% CPU
  continuously during testing, a real, environmental contention factor
  outside this codebase's control.
- A genuine C rewrite of the hot path (the tree-walk logic itself, not
  just `live_reader`'s raw-read serving loop) was discussed with the user
  directly: likely a smaller win than the round-trip-count reduction
  already banked (round-trip *count* was the dominant cost until this
  session's fix; eliminating the Python<->C pipe IPC boundary entirely
  would cut the cost of each remaining round trip, worth real
  consideration now that round-trip count is no longer the primary
  bottleneck, but not yet attempted).

**Also tried and kept, smaller win:** reduced `_PYSTR_OPTIMISTIC_CHUNK`
from 256 to 96 bytes (sized from real observed attribute-name/label
lengths this session, not a round number), since most real strings are
well under 50 characters and the 256-byte chunk was pure over-fetch for
the common case. Verified correctness held (same zero-diff comparison).
**Informative negative result, worth remembering:** this halved total
data volume for a full tree read (58MB -> 30MB) but did *not*
meaningfully reduce wall time (2.119s -> 2.185s, within noise) --
concrete evidence that the remaining bottleneck at this depth of
optimization is **Python-level per-read processing overhead** (struct
packing/unpacking and object construction across ~435,000 individual
reads, ~145/node), not I/O throughput or round-trip latency anymore.
This is the correct diagnostic basis for prioritizing a native rewrite
of the hot path over further Python-side tuning, if/when that work is
picked up.

**Stopped here for tonight, by user's explicit choice** (offered:
continue tuning Python further, start a C rewrite now, or stop) --
correctly judged as a substantially bigger undertaking than warranted
at the end of an already-long session. Current state is a good
stopping point: no known correctness bugs, no known hangs, real
before/after numbers recorded above for whoever picks this up next
(including this session, next time). **Next session should start here**
if pursuing further speed: either (a) investigate whether `max_nodes`
can be safely scoped down for this specific bot without breaking
correctness, or (b) begin a native (C or Rust) rewrite of the tree-walk
hot path itself -- not just `live_reader`'s raw-read serving loop --
now that round-trip count and data volume are no longer the dominant
costs and per-operation Python overhead is the clearly-diagnosed
remaining bottleneck.

### Done (2026-07-26): pushed the Python-side optimization to its actual measured ceiling, with cProfile evidence, not a guess

User's `/goal` for sub-1s ticks stayed active; pushed one more real round
rather than stop on an unmet goal without exhausting the cheap options.

**Profiled the live tree walk directly (`cProfile`) instead of guessing
further.** Top finding: **813,809 individual `BufferedReader.read()`
calls** (0.792s of 2.794s total, ~28%) -- two per response (an 8-byte
length header, then the payload) across ~407,000 individual protocol
responses in one tree read. That's a bigger cost than `build_tree`'s own
Python-level loop overhead.

**Added a self-managed read-ahead buffer (`LiveSample._read_exact`)** so
many small protocol-level reads are served from an in-memory buffer
(refilled in up to 1MB chunks) instead of issuing a real `.read()` call
per length-header and per payload. **Found and fixed a real bug in this
fix before trusting it**: initially used `.read(n)`, which blocks until
it gets *exactly* `n` bytes (or EOF) -- for a batch whose total
remaining response is smaller than the 1MB fill size, that blocks
forever waiting for more data live_reader was never going to send until
the *next* batch (an EOF never comes; the process stays alive). Fixed by
using `read1(n)` instead, which does at most one underlying read and
returns whatever's immediately available without over-blocking. Verified
correctness held (same zero-diff comparison against the reconstructed
old implementation) before trusting it on the live path.

**Result, measured, not assumed:** raw `read1()` syscalls dropped from
813,809 to **128,132** (an 84% reduction) -- but wall time barely moved
(2.185s -> 2.031s for the same tree). **This is the important, honest
finding: syscall/round-trip count is no longer the bottleneck at all.**
Re-profiling after the fix shows `_read_exact` itself (now called
813,807 times -- once per logical read, same count as before, just each
call now usually hits the buffer instead of the OS) still costs 0.372s
in its own code, and the *total* op count for one tree read is **7.4
million Python-level function calls**. This is unambiguously CPU-bound
CPython interpreter overhead now (building/appending to lists, `struct`
pack/unpack, dict lookups, `len()` calls -- all individually cheap, but
millions of them add up), not I/O, not round trips, not data volume.

**Real end-to-end bot-loop ticks with every fix from this session
active: ~4.0-4.2s**, only marginally better than the 4-5s measured
*before* this final buffering pass, despite the isolated tree-walk
benchmark itself dropping to ~2.0s. There's still a real, not-yet
profiled gap between "isolated tree-walk benchmark" and "actual full
tick" (which also includes the window-rect `InvokeMethodOnWindowRequest`
call and the bot's own baked-in `WindowsInputRequest` wait times,
100+210+210=520ms) -- worth profiling the *full* tick, not just the
memory-read step, if this is picked up again.

**Honest conclusion, backed by profiling evidence rather than
intuition: further large wins from this point require a native
rewrite of the hot path** (moving the struct-unpack/dict-lookup/
tree-assembly logic itself into C or Rust, not just the raw-read
serving loop `live_reader` already is), not more Python-side tuning.
The cheap, low-risk levers (round-trip batching, buffering, right-sized
chunk reads) have now been tried, measured, and exhausted -- each one
gave a real, verified improvement, but the *combined* effect tops out
around 4s/tick on this machine's real, ~3,000-node live UI tree, still
4x the "under a second, ideally" target. Next session, if pursuing this
further: profile the *full* tick end-to-end first (not just
`ReadFromWindow`) to confirm where the remaining 4s actually goes before
committing to a rewrite, since the isolated-vs-full-tick gap found here
is still unexplained.

### Done (2026-07-26): the C rewrite -- `tree_walker`, ~5x faster than Python, rigorously verified; then the crucial final finding that most of the "remaining gap" was never the host's to fix

User's goal condition stayed active; pushed the actually-justified next
step (a native rewrite of the hot path, scoped by the profiling evidence
above) rather than stop with an unmet numeric target and further
untried, cheap options on the table.

**Built `tools/macos-host/tree_walker/tree_walker.c`** -- a persistent,
entitled process (same `task_for_pid` pattern as `live_reader`/
`memory_sample`) that does the *entire* memory-read + CPython struct
decode + tree assembly in one C process, attached directly to the
target -- no pipe protocol at all for the hot path, unlike
`live_reader` (which still serves individual reads to Python over a
pipe). Reimplements every struct layout this whole project derived by
hand: the custom dict (header/inline/overflow, with the exact
duplicate-key semantics -- last-wins for attributes, first-wins for
`children` -- matching the Python implementation intentionally, not by
accident), `PyASCIIObject`/`str`, Python-2-style `PyIntObject`/
`PyLongObject`/`PyUnicodeObject`, `PyFloatObject`, the
type-metaclass-invariant classifier (with a small type-name cache), and
the `children` -> `PyChildrenList` -> `_childrenObjects` -> stock
`PyListObject` recipe. Protocol: a 32-byte binary request (root addr,
metatype addr, str-type addr, max depth, max nodes) -> a length-prefixed
JSON response, matching the exact `UITreeNode` shape the rest of the
system already expects.

**One genuine bug found and fixed before trusting it, via the same
rigorous methodology used throughout this session (diff against a
proven-correct implementation, not just eyeballing output):** the
initial `long` decoder accumulated digits into a C `double`, which
silently loses precision above 2^53 -- real timestamps in this game
(Python-2-style 60-bit `PyLongObject` values) exceed that, so decoded
values were off by a handful of units versus the proven Python
implementation. Fixed by accumulating in `__int128` (exact for up to 4
digits / 120 bits, comfortably covering every real value seen) and only
falling back to `double` for genuinely larger bignums.

**A second class of apparent discrepancy, investigated rather than
dismissed, turned out to be an already-understood, non-bug artifact
recurring:** comparing Python vs C output at `max_nodes=500` showed many
"C finds more children than Python" diffs. Ruled out both live-timing
noise and a structural C bug with two decisive tests instead of
guessing: (1) two back-to-back C-only runs were byte-for-byte identical,
ruling out non-determinism; (2) *swapping which implementation ran
first* left the exact same diff pattern (C always finding more,
regardless of run order), ruling out "whichever ran second sees a
changed live UI." That signature -- consistent regardless of order,
concentrated right at the node-count boundary -- is exactly the
DFS-vs-BFS budget-truncation difference already documented for the
Python breadth-first rewrite earlier this session (C's walker is a
straightforward recursive DFS; current Python `build_tree` is
breadth-first; the two select different node subsets once a `max_nodes`
cap actually gets hit mid-tree). Confirmed by re-running with
`max_nodes` far above the real tree size (so the cap never triggers):
**node counts matched exactly (3164 = 3164)**, and only 11 diffs
remained, all on values with an obvious real-time explanation --
rotation angles (one was exactly `3.141592653589793`, i.e. a spinning
loading indicator mid-animation), opacity fades, and toggle states --
i.e. genuine game-state drift between two temporally-separated live
reads, the same kind of noise any two live snapshots would show,
Python-vs-Python included.

**Wired into `botlab_host.py`** as `TreeWalkerClient`, replacing the
Python `build_tree` call in `_read_from_window` entirely for the hot
`ReadFromWindow` path (the Python `re_helper.py` implementation stays in
place and in use for `re_helper.py`'s own CLI and for
`SearchUIRootAddress`'s one-time bootstrap, which doesn't need to be
fast).

**Measured, not assumed, at every step:**
| stage | isolated memory-read time (production params: depth=12, nodes=4000) |
|---|---|
| Python, before this session's fixes | 3.08s (2664 nodes) |
| Python, after round-trip batching + pipe-deadlock fix + buffering + chunk-size tuning | ~2.0s (2988 nodes) |
| **C (`tree_walker`)** | **~0.41-0.5s (2836 nodes)** |

Real end-to-end bot-loop ticks, live against the game, with everything
from this session active: **~2.65-2.76s**, down from the session's
starting point of 8-11s (which also carried a latent, unconditional
hang risk that's now fixed) -- roughly a 3-4x improvement, with the
per-task timing breakdown (kept as a permanent diagnostic, not removed
after use) showing the memory read is now consistently the *smallest*
major cost at ~0.55-0.7s, not the dominant one anymore.

**The crucial final finding, and the honest resolution of the "under 1
second" goal: most of the remaining gap between ~1s of real host work
and the observed ~2.7s tick was never the host's to fix.** Added
one more timing probe around the outer loop's `notifyWhenArrivedAtTime`
sleep (the delay the *bot itself* requests before its next decision
cycle) and found it accounts for **1.1-2.0s of every tick** -- and
traced it to source: `EveOnline/BotFramework.elm:732` hardcodes
`notifyWhenArrivedAtTime = stateBefore.timeInMilliseconds + 2000`, a
literal, deliberate 2-second pacing delay built into the bot's own
*unmodified* framework code (presumably to avoid hammering the game
client with reads, or to approximate human reaction pacing) --
completely outside host control without editing bot source, which this
entire project has deliberately never done.

**Reframed, honest conclusion:** the host's own controllable overhead
per cycle (memory read + window-rect lookup + input-dispatch overhead,
excluding the bot's own baked-in `WindowsInputRequest` wait times) is
now approximately **0.75-1.05s** -- at or very close to the "under a
second, ideally" target on its own. The ~2.7s figure observed for a
full "tick" (one `TimeArrivedEvent` to the next) is dominated by the
*bot's own* 2-second self-imposed pacing choice, not host
slowness -- the same category of "can't reduce without modifying
unmodified bot code" as the `WindowsInputRequest` intrinsic waits
documented earlier. Further host-side speed work past this point would
be optimizing something that's no longer the bottleneck.

**Traced the 2-second pacing to its exact, specific source line, not
just "somewhere in the framework":** `Bot.elm:178` --
`|> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase 2000`.
This matters because it's a call in the *specific application file*
(`eve-online-warp-to-0-autopilot/Bot.elm`), not merely an unexamined
generic default -- the framework's own built-in default
(`millisecondsToNextReadingFromGameDefault` in
`BotFrameworkSeparatingMemory.elm`) is actually 1500ms; *this bot*
explicitly overrides it to 2000ms as a deliberate authoring choice.
There is no host-side lever left to pull here: the host now completes
its own work (memory read + window lookup + input dispatch) faster than
the bot ever asks it to run again. Getting the observed wall-clock
per-tick number under 1 second from this point forward would require
editing this line of the bot's own application source (e.g. lowering
`2000` to something smaller) -- which is a direct, explicit violation of
this project's foundational premise (run the existing ~8,500 lines of
Elm bot logic *unmodified*; see the very top of this file). Flagged to
the user as an explicit choice rather than silently either doing it or
refusing to engage further.

**User's explicit decision: leave it as-is.** Given the choice between
patching `Bot.elm` (in a working copy, not the checked-in source) to
lower the 2-second pacing, versus keeping the host a strictly
unmodified-bot-only replacement for BotLab.exe, the user chose to keep
bots unmodified. **This closes out the speed goal for this session.**
The host-side work is genuinely done: real ticks for THIS bot stay
~2.7s not because the host is slow, but because the bot itself
(deliberately, in its own application code) doesn't want to be read
more often than every 2 seconds. A *different* bot that requests
faster reading (a smaller or zero
`setMillisecondsToNextReadingFromGameBase` argument) would automatically
see sub-1s ticks from this same, unmodified host -- nothing about the
host imposes the 2-second floor; it's entirely bot-specific and already
handled correctly (the host just honors whatever `notifyWhenArrivedAtTime`
each bot requests, as it should).

### Done (2026-07-26): first real live run of saxrat — found and fixed a real `SearchUIRootAddress` bug, caused by a busy trade hub

User asked to "undock and run saxrat until we're out of waypoints" (the
character had a 94-jump EVE-native autopilot route already queued up in
Gal Bistot, a busy Amarr trade hub). Launched via `run_saxrat.sh`; the
bot compiled and started, but got stuck immediately after undocking on
"I do not see the icon for the location info panel" — one of the
genuinely-stuck `askForHelpToGetUnstuck` leaves, not a crash.

**Root cause, found by taking a fresh dump and manually re-deriving the
root address:** `find_ui_root` normally locates the UI root by
repr-scanning the dump for EVE's own debug-log string
`<UIRoot object at 0X...>`. With 246 people in local chat at this
station, that string had been evicted from EVE's internal debug-log
ring buffer by chat spam before the scan ran, forcing the fallback path
(`walk_to_root`, following `_parentRef` weakrefs upward from any known
widget). That fallback had a real, previously-undetected bug: a
widget's `_parentRef` can be present in its dict but hold the
interpreter's actual `None` object (not just "key absent") — e.g. a
permanent HUD-layer container's `_parentRef` is genuinely `None`, not a
weakref. The old code dereferenced `None`'s address as if it were a
`PyWeakReference` (reading `+0x10` as `wr_object`) and silently walked
to garbage, landing on a bogus "root" address that didn't contain the
info panel at all.

**Fix, in `tools/macos-host/re_helper/re_helper.py`:**
`walk_to_root` now checks `get_type_name(sample, pref, metatype_addr) ==
b"weakref"` before dereferencing `pref+0x10`, stopping (treating it as
"no further parent") on anything else. `find_ui_root` was also made more
robust generally: instead of walking up from just the *first* repr-scan
hit and trusting it blindly, it now tries every available seed, prefers
any result whose own class name is actually `"UIRoot"`, and otherwise
takes whichever root address the most seeds agree on (some seeds, like
a HUD container or a popped-out inventory window, are themselves
self-contained trees whose `_parentRef` walk dead-ends before reaching
the real desktop root — this discards those instead of trusting them).

Verified against a fresh dump: of ~20 repr-scanned seeds, most now
converge on the same address, correctly classified as `UIRoot`/`Desktop`
— and a full tree walk from that root found both `InfoPanelContainer`
and `InfoPanelLocationInfo`, using only 1405 of the 5000-node budget
(ruling out "busy hub blew the node budget" as an alternative theory —
it was purely the wrong-root bug). Restarted the bot with the fix in
place: it found the real root, undocked cleanly, and started reading
real game state and making real decisions immediately.

**Confirmed working end-to-end, live:** the ship undocked, resumed the
pre-existing 94-jump EVE-native autopilot route (unrelated to saxrat's
own logic — saxrat doesn't drive interstellar autopiloting at all; it
just correctly detects `shipUIIndicatesShipIsWarpingOrJumping` and waits
during each jump/warp), and opportunistically dove into a matching
"Sansha Refuge" anomaly in Murzi between jumps: drones launched and
fighting, shields dipped from 100% to ~55% then stabilized once weapons
were actually landing hits, armor untouched (the configured 80%
run-away threshold never came close to triggering). This is the
bot's own unmodified decision-tree logic making real combat decisions
against live memory-read state, not a scripted demo.

Set up a background watcher (`poll_route.py` + `watch_route.sh`,
scratch-only, not checked into the repo) that read the live UI tree
every 60s looking for the route panel's "`N Jumps`" label, to notify
once the route hit zero ("out of waypoints") or the bot errored out.
**User then asked to kill the bot** before that condition was reached;
stopped `botlab_host.py`, the Node `driver.js`, `tree_walker`, and the
watcher script. Real mouse/keyboard control was restored to the user;
the ship was left wherever it was (mid-anomaly in Murzi).

### Done (2026-07-26): `run_saxrat.sh` gained a one-bot-at-a-time guard

User feedback: "we're strictly a one-bot-at-a-time shop for now." Added
a guard at the top of `run_saxrat.sh` that kills any previous
`run_saxrat.sh` process (matched by basename via `pgrep -f`, so it finds
a prior run regardless of whether it was launched with a relative or
absolute path) plus any `botlab_host.py`/`driver.js`/`tree_walker`
processes, before launching. The script's own just-started process
would otherwise match its own basename pattern too — guarded against by
excluding `$$` (its own pid) from the kill loop. Verified with a
simulated stale process (a `sleep` given `argv[0]=run_saxrat.sh` via
`exec -a`): the guard correctly killed the impostor and left the real
invocation's own pid alone.

### Done (2026-07-26): saxrat behavior feedback — prop mod deactivation and weapon hotkeys

Two pieces of bot-behavior feedback, both implemented in
`eve-online-saxrat/Bot.elm` (this bot's own application file, not the
shared framework):

1. **Deactivate the prop mod (Alt+F1) before warping.** Added
   `ensurePropulsionModuleIsDeactivatedBeforeWarping`, which spends one
   tick sending `Alt+F1` (skipped if already sent the previous tick,
   using the same `previousStepsEffects` bookkeeping pattern used
   elsewhere) before letting the actual warp action proceed. Wired into
   both places the bot initiates a warp: `enterAnomaly` (warp to a
   matching anomaly) and `tetherAtStructure` (the warp/approach-back
   cascade). Deliberately *not* added to `alignToStructure`, since
   aligning doesn't actually engage warp.
2. **F1-F4 hotkeys instead of mouse clicks for weapons.** Added
   `activateWeaponModuleButWaitIfActivatedInPreviousStep`, which presses
   F1/F2/F3/F4 for the first four top-row (weapon) module slots by
   position (matching this bot's own setup instructions: "put combat
   modules in the top row"), falling back to the old mouse-click
   behavior for a 5th+ weapon. Wired into both places the bot cycles
   weapons in combat (initial "Shoot!" and the ongoing "Cycle combat
   mod" step in `decideActionInAnomaly`). The middle-row
   (always-on/defensive) modules are untouched, still mouse-clicked —
   only asked about weapons.

Confirmed the VK codes for F1-F4 and Alt/`MENU` were already correctly
mapped to macOS `CGKeyCode`s in `botlab_host.py`'s
`_VK_TO_CGKEYCODE` table from earlier session work — no host-side
changes needed, only `Bot.elm`. Verified the whole module still compiles
via the usual elm-version-patched-copy-plus-`Main.elm` check. **Not yet
exercised live** (no bot session was running when this was
implemented) — this will be the first real test of the keyboard-effect
path; only mouse effects had been exercised live before now.

### Done (2026-07-26): saxrat behavior feedback — clear stray context menus

User spotted (via screenshot) a two-level context-menu cascade (a
right-click menu plus an "Anomalies" submenu preview) sitting open over
the Overview window — apparently left over from a misclick — and asked
for "some capacity to clear this state," since a stray menu like this
can occlude the Overview and intercept clicks meant for whatever is
underneath it.

`useContextMenuCascade` already has its own recovery for a menu that
isn't advancing *while it's actively driving a cascade* (same-target
discard-and-reopen if the menu list hasn't changed since the previous
reading) — the actual gap was a menu left open on a tick where the
decision tree isn't touching any menu logic at all, so that recovery
code never even runs.

Added `clearStrayContextMenu` in `Bot.elm`: if
`readingFromGameClient.contextMenus` is non-empty and has stayed
byte-for-byte identical (via `identifyingInfoFromContextMenu`, reused
from the framework) across at least 3 consecutive
`previousReadingsFromGameClient` entries, press Escape before anything
else runs that tick. The threshold of 3 is deliberate — long enough
(several seconds) not to interrupt a normal, still-progressing cascade
or the framework's own single-retry recovery, short enough to actually
clear a genuinely stuck menu within a few ticks. Wired in as the very
first check in `decideNextActionWhenInSpace`, via
`clearStrayContextMenu context |> Maybe.withDefault (<existing ~120-line
function body>)` specifically to avoid re-indenting that whole existing
body (Elm's layout rule only requires everything inside the parens to
stay right of column 0, not fastidiously realigned). Compiles clean.

### Done (2026-07-26): first git commit of this entire project, pushed to a personal fork

None of this session's work (or any prior session's) had ever been
committed — `git status` showed ~35 changed/untracked paths accumulated
across every session in this file. Reviewed before committing:

- No root `.gitignore` existed. Added one excluding `.DS_Store`,
  `__pycache__/`, `*.pyc`, and the six ad-hoc-signed compiled tool
  binaries that each have adjacent `.c` source and are platform-specific
  build output, not source (`probe`, `memory_sample`, `tree_walker`,
  `live_reader`, `window_probe`, `cg_input`).
- `git add -A` correctly detected renames — `Common.elm`,
  `EveOnline/ParseGuiFromScreenshot.elm`, and
  `BotLab/BotInterface_To_Host_2024_10_19.elm` moved from
  `eve-online-mining-bot` to `eve-online-saxrat`, consistent with saxrat
  having been bootstrapped by copying the mining bot's framework files
  earlier in this project.
- Found `eve-online-wingus` on disk — a third bot app, untracked, not
  otherwise mentioned anywhere in this file. Not investigated; committed
  as-is alongside everything else, since it's clearly part of the same
  body of work. Worth a closer look in a future session if it comes up.
- Sanity-checked `eve-online-mining-bot` still compiles despite its own
  heavy modifications (several framework files deleted/replaced,
  pinned to the older `BotLab.BotInterface_To_Host_2023_02_06` interface
  rather than saxrat's `2024_10_19`) — `elm make Bot.elm --output=/dev/null`-style
  check passed ("NO MAIN" is expected and harmless; the actual
  type-check reported "Success!"). Not broken, just a different,
  internally-consistent interface version than saxrat.

Created the fork with `gh repo fork Viir/bots` (logged in as `smerwin`,
`repo` scope) — note for next time: `gh`'s `--remote=true` flag reported
success but did *not* actually add the git remote; had to add it
manually (`git remote add fork https://github.com/smerwin/bots.git`).
`origin` remains `Viir/bots` (upstream, untouched); `fork` is the new
personal remote. Pushed `main` to `fork` in two commits: `10f14fc` (the
whole accumulated project — the macOS host, saxrat, wingus, and the
mining-bot framework updates) and a same-day follow-up `f974111` for the
stray-context-menu fix above.
