# Porting the memory-reading host to Windows — what the client says

Issue [#176](https://github.com/smerwin/bots/issues/176). This is the report its
step 1 asks for, plus what step 2 turned up, written against a **live Windows
client** — the thing the issue says the environment does not have:

> **None of this can be verified from here.** There is no Windows machine in this
> environment. Everything this project does well — measure it, mutate the rule,
> prove the case bites — depends on running the thing. A Windows host would ship
> wholly unexercised, which is a different risk posture from anything else in
> this repo.

There is one now. Everything below is read off `bin64/exefile.exe` while it was
running, and every number is reproducible with the tools in this directory. The
host is **read-only so far**: it opens the process with `PROCESS_VM_READ |
PROCESS_QUERY_INFORMATION`, and it has never sent the client an input event.

## The short version

**The port is smaller than the issue expects, and the risk it names is real but
lands in two specific fields rather than across the decoder.**

- `ReadProcessMemory` against the client is **permitted**, with no privilege
  beyond the same user, and nothing interfered with it.
- The Windows client is **the same CPython 2.7 and the same Blue layer** as
  macOS — `python27.dll` and `blue.DLL` are both loaded.
- **Blue's custom dict transfers byte for byte**: same 0x38 header, same 8 inline
  entries, same 24-byte entries, same mask at +0x20 and overflow at +0x28. That
  is the structure the issue calls "precisely the part `tree_walker` does
  natively", and it needed no change at all.
- **Two offsets do not transfer**, and both are the same fact: Windows x64 is
  LLP64, so `long` is 4 bytes where macOS's arm64 LP64 gives it 8. In CPython 2.7
  that moves a `str`'s characters from `+0x24` to `+0x20` and halves an `int`'s
  value field. Reading either the macOS way yields plausible nonsense rather than
  an error — exactly the failure shape the issue names.
- **The root cannot be found the macOS way.** The debug-log repr text
  `<ClassName object at 0X…>` that `re_helper.find_ui_root` seeds from is not in
  this client's memory anywhere.
- A full UI tree — 4,059 nodes — reads in about 2.4s and **parses cleanly through
  the real `EveOnline.ParseUserInterface`**.

## 1. What the 2019 C# reader establishes, and what it cannot

The issue is right that it should be read first, and right that it is the thing
that decides how big the job is. What it decides, though, is mostly in the
negative.

**Its structural account is correct and still current.** `UITreeNode.cs` walks
exactly what `tree_walker.c` walks, step for step:

```
widget  ->  dict at a fixed offset  ->  'children'
        ->  PyChildrenList  ->  its own dict  ->  '_childrenObjects'
        ->  stock PyListObject  ->  ob_item array  ->  recurse
```

That is the whole algorithm, it was true in 2019, and it is true of the client
running now — this host walks it unchanged. Confirmed live: a `UIRoot`'s dict
holds `'children'` → a `PyChildrenList`, and following it reaches the tree.

**Its offsets establish nothing about a modern client, because it is 32-bit
throughout.** Every pointer it reads is a `UInt32`, and
`CastToIntPtrAvoidOverflow` refuses any address above `UInt32.MaxValue`
outright. Its constants are the ILP32 layout:

| | 2019 C# (ILP32) | macOS host (LP64) |
|---|---:|---:|
| `ob_type` | 4 | 0x08 |
| `ob_size` | 8 | 0x10 |
| `tp_name` | 12 | 0x18 |
| instance dict | 8 | 0x10 |
| dict entry size | 12 | 24 |

Those are the same layout at two widths, not two layouts — which is why the file
is worth reading and why its numbers cannot be used. The 2019 Windows client was
`bin/exefile.exe`; the one running here is `bin64/exefile.exe`, and
`IsWow64Process` says it is a genuine 64-bit process.

**And its dict is not the dict this client has.** `PyDict.cs` decodes a *stock*
`PyDictObject` — `ma_fill`, `ma_used`, `ma_mask`, `ma_table`, with entries in a
separately allocated table. `tree_walker.c` decodes Blue's *custom* dict: a 0x38
header with eight entries inline and an overflow block behind a pointer. Those
are different data structures, not a width difference, so the file cannot
corroborate the part of the decoder that most needed corroborating. What settles
it is the client itself, in section 2.

**Its root discovery is the one part worth taking, and this port takes it.** See
section 3.

So the issue's hope that reading it "may shrink the job considerably" is half
right, and by a different route than expected: it shrinks the job by confirming
the *walk*, and it contributes nothing to the *offsets*, which had to be measured.

## 2. The struct layout, measured against the running client

`probe.py` derives each of these rather than asserting it. Where a field is the
same as macOS that is a finding too, and the evidence is given.

| field | macOS | Windows x64 | how it was established |
|---|---:|---:|---|
| `ob_refcnt` | +0x00 | +0x00 | plausible refcounts on live objects |
| `ob_type` | +0x08 | +0x08 | `type(type) is type` holds against `python27.dll`'s exported `PyType_Type` |
| `ob_size` | +0x10 | +0x10 | string lengths agree with their NUL terminators |
| `tp_name` | +0x18 | +0x18 | all ten exported type objects name themselves correctly |
| **`str` characters** | **+0x24** | **+0x20** | **differs — see below** |
| **`int` value width** | **8** | **4** | **differs — same cause** |
| **`unicode` char width** | **4 (UCS-4)** | **2 (UCS-2)** | **differs — see 2a** |
| widget wrapper size | 32 | 32 | the type object's own `tp_basicsize` |
| widget instance dict | +0x10 | +0x10 | the type object's own `tp_dictoffset` |
| widget weakref slot | +0x18 | +0x18 | the type object's own `tp_weaklistoffset` |
| Blue dict header | 0x38 | 0x38 | first inline entry decodes at +0x38 |
| Blue dict capacity mask | +0x20 | +0x20 | reads 0x7F on a dict with 64 used entries |
| Blue dict overflow pointer | +0x28 | +0x28 | populated exactly when entries exceed 8 |
| Blue dict entry size | 24 | 24 | `(hash, key, value)` triples decode at that stride |
| Blue dict inline entries | 8 | 8 | the ninth slot's key is never a valid pointer |
| stock list `ob_item` | +0x18 | +0x18 | child pointer arrays decode |

### The one that differs, and why it is one fact rather than two

`PyStringObject` is `PyObject_VAR_HEAD; long ob_shash; int ob_sstate; char
ob_sval[1]`. With an 8-byte `ob_shash` the characters land at `+0x24`, which is
what macOS reads; with a 4-byte one they land at `+0x20`. `PyIntObject.ob_ival`
is a bare `long` and moves for the same reason. Windows x64 is LLP64 and macOS
arm64 is LP64, so this is `sizeof(long)` and nothing else.

**Decided by reading, not by reasoning**, because the reasoning would have been
just as confident if the client were built some other way. Over 4,000 candidate
`str` objects:

| characters read at | NUL-terminated at `ob_size` | fully printable | the word just before them |
|---|---:|---:|---|
| **+0x20** | **3996** | **3107** | `{1: 3352, 0: 644}` |
| +0x24 | 3172 | 6 | arbitrary |

The third column is the decisive one and it is independent of the first two:
`ob_sstate` is 0, 1 or 2 (not interned, interned mortal, interned immortal), and
at `+0x20` the preceding word is only ever 0 or 1. At `+0x24` it is noise. The
strings that come back are what settles it for a human — `'FILE_NOTIFY_INFORMATION'`,
`'watchdog.observers.api'`, `'itemId'`, `'renderObject'`, `'_childrenObjects'` —
against six accidentally-printable fragments the other way.

**This is precisely the failure the issue is worried about.** Read at `+0x24`,
3,172 of 4,000 strings still "decode": the length is right, a NUL turns up, and
the result is garbage. Nothing raises an error. A host built by carrying the
macOS constants across would have produced a UI tree full of plausible rubbish.

## 2a. The one that hid: `unicode` is UCS-2 here, and reading it wrong drops it

This is the third difference, it is not an LLP64 consequence, and it is the one
worth reading if only one of these is read. `Py_UNICODE` is `wchar_t`, so its
width is a **build option** rather than a platform constant: a CPython 2.7
configured `--enable-unicode=ucs4` stores 4 bytes per character and the stock
Windows build stores 2. macOS reads UCS-4. This client is UCS-2.

**Getting it wrong does not garble a string, it deletes one.** UTF-16 bytes
decoded as UTF-32 land on unassigned planes and raise, so the decoder answered
`None` and the walker omitted the key. Nothing errored, nothing looked wrong, and
`str` values — which are most of what a casual look at the tree shows — decoded
perfectly throughout. What went missing was only the values EVE happens to store
as `unicode`.

**What those turned out to be:**

| | before | after |
|---|---:|---:|
| display texts the real Elm parser can see | **57** | **269** |
| nodes with a display region | 2548 | 2670 |

Roughly **80% of the client's readable text** was invisible to the bot. And the
two things it hid were each blocking a bot outright:

- **Every context-menu entry's text.** The menu opened, the bot saw it, and it
  had no entries it could read — so `Could not find menu entry with text
  containing … 'jump'` on every attempt. That is why the mission runner never
  jumped a gate across a whole 60-tick run. Fixed, the same right-click reads
  `['Jump Through Stargate', 'Show Info', 'Set Destination', 'Add Waypoint', …]`.
- **Every probe-scanner anomaly name.** saxrat reported `I see 4 scan results,
  and no matching anomaly` for its whole first run, because the names it matches
  `anomaly-name` against were among the dropped values. Fixed, it finds anomalies
  and warps to them.

**Two symptoms, one bug, and neither pointed at it.** Both looked like a cascade
problem or a settings problem — which is exactly the shape issue #176 warns
about, arriving as *absence* rather than as wrong data. It was found by chasing a
menu that opened and had nothing in it, and dumping one node's every field with
its value's type beside it. `probe.py` now measures the width the same way it
measures the other two, so the next build is asked rather than assumed.

**It fails safe, and that is the only reason it was survivable.** A width guess
that produced *plausible* text instead of nothing would have put fabricated menu
entries in front of a cascade.

### One thing Windows offers that macOS does not

The macOS client is a single statically linked binary, so `re_helper.py` has to
bootstrap the `type` metaclass by scanning for the `type(type) is type`
invariant, and CLAUDE.md records the stale-seed trap that caused "hit in three
separate tools". The Windows client loads a real `python27.dll`, which **exports
`PyType_Type`, `PyString_Type`, `PyInt_Type` and the rest as data symbols**.
Reading its export directory out of the target's own memory gives those
addresses authoritatively. The bootstrap, its trap, and the whole-address-space
scan the 2019 C# code needed to find the metaclass all disappear.

The same goes for the widget wrapper: the type object states `tp_basicsize`,
`tp_dictoffset` and `tp_weaklistoffset`, so three offsets the macOS host has to
hardcode are simply *asked for* here.

## 3. Finding the root: the macOS route does not exist here

`re_helper.find_ui_root` regex-scans a memory dump for EVE's own debug-log repr
text, `<ClassName object at 0X[hex]>`, and walks `_parentRef` upward. On this
client that text **is not there**: a scan of the entire readable address space
returns **zero** matches, where the macOS host relies on hundreds and validates
up to 200 candidates. So there is nothing to seed from and no `_parentRef` walk
to make.

What replaces it is the 2019 C# reader's approach, which is available on Windows
precisely because the exported metaclass makes it cheap: find the type object
whose `tp_name` is `UIRoot`, then find objects whose `ob_type` is that type.

Two things had to be added to make it correct:

- **Most words pointing at the type are not instances.** They are entries in some
  class's `__mro__` tuple, which is what a naive `hit - 8` picks up. Three
  conditions separate them and all three are needed: a plausible refcount, a
  non-null pointer at `tp_dictoffset`, and that pointer's `ob_type` really being
  `dict`. Without them the first "instance" found was a fragment of
  `UIRoot → Container → … → object`.
- **The client keeps more than one `UIRoot`.** There are two, and one is the
  blurred desktop backdrop. `EveOnline.cs` takes the candidate with the largest
  tree and so does this; the numbers make the choice obvious rather than close:

  ```
  0x16C29F41B38  _name='desktopBlurred'     5 nodes to depth 6
  0x16C29F41D68  _name='Desktop'         1018 nodes to depth 6
  ```

It costs two whole-address-space scans, about 30 seconds, so it is a
session-start cost cached exactly as the macOS host caches its own root.

## 4. The four unverified items

| the issue's item | answer |
|---|---|
| **None of this can be verified from here** | No longer true. Everything in sections 1–3 and 5 is read off a running client. |
| **Whether `ReadProcessMemory` is permitted** under current Windows protections and anti-cheat | **Yes.** `OpenProcess(PROCESS_VM_READ \| PROCESS_QUERY_INFORMATION)` succeeds in under a millisecond as the same user, with no elevation and no debug privilege. 9,298 readable regions, 5.24 GiB, enumerable and readable. Nothing rate-limited, blocked or nulled a read across hundreds of thousands of them. **This is one client on one machine at one patch level and is not a general claim.** |
| **Whether the Windows client is the same Python build** | **Same interpreter, different ABI.** `python27.dll` and `blue.DLL` are both loaded, and it is Stackless (`launchdarkly_stackless_client_sdk.pyd`). Everything structural transfers; the two `long`-width fields in section 2 do not. |
| **Whether the screenshot is actually the cost** | **Partly answered, and it does not hold as stated** — section 5. |
| **Whether `SendInput` reproduces the input pacing** | **Not answered.** No input has been sent. See "What is not built". |

## 5. What a reading costs

`measure_cost.py`, on this client, same moment:

```
window 2281x1539, client 1518x994

1. One window capture (BitBlt of the client area + GetDIBits)
   raw frame           5.8 MiB
   median              33.0 ms

2. One full UI-tree read (the ported walker)
   root discovery      31.2 s   (once per session, then cached)
   nodes               4020
   median              2405 ms
```

**So the capture is not the expensive half.** Dropping the screenshot saves 33 ms
per reading against a memory read costing 73 times that. The issue's "if the
expense is the capture rather than the decode, then simply not capturing may win
most of it without porting `tree_walker` at all" does not hold on this machine:
not capturing wins 33 ms.

**Three things this does not establish, stated rather than left to be
discovered.**

- **It prices the capture, not "the screenshot".** What BotLab.exe does with
  those pixels afterwards is not visible from outside, and this repo's own notes
  say the encoding is where that cost lives: packing a full-resolution frame to
  JSON measured 5.2 of 8.2 seconds on macOS, and "a full-resolution Retina crop
  packs to ~66MB of JSON". If BotLab is paying that, not capturing would avoid it
  too, and the saving would be far more than 33 ms. **That remains unmeasured**,
  and it is the half that would vindicate the issue's premise.
- **BotLab.exe was idle while it was watched** — 0.1s of CPU over 20s, 0% of one
  core. So its own figures say nothing about a running session. Its working set
  was 4.1 GiB earlier in the same session and 1.29 GiB while idle, which says the
  4 GiB is elastic rather than resident.
- **2,405 ms is this implementation's number, not the design's.** The macOS C
  walker does a comparable tree in 390 ms. This one is Python, and the gap is
  implementation rather than platform — see "What is not built".

## 5a. Input: the port, and the bug it turned up before sending anything

`cg_input.c` → `SendInput` is the API swap the issue's table asks for, and it is
about forty lines of the file. What carries the weight is the behaviour the macOS
host tuned against this client over many runs, which lives in `botlab_host.py`
rather than in `cg_input.c` — the glide, the dwell-preserving skip, the
`force_movement` nudge before a click, the drag that must not pause after the
press, the 30 ms key hold, the five-second human stand-down. **None of that is
reimplemented.** `win_platform.CgInput` speaks `cg_input`'s own line protocol, so
`_windows_input`'s two hundred lines are shared between the platforms and there
is one copy of each finding rather than two.

**Two things get simpler.** The key mapping disappears entirely:
`Common/EffectOnWindow.elm`'s `vkey_*` values *are* Windows virtual key codes
(`vkey_RETURN` is `0x0D`, `vkey_A` is `0x41`), because the framework was written
for Windows. macOS needs `_VK_TO_CGKEYCODE` and that table has cost this repo two
real bugs — `vkey_SUBTRACT` missing from it, and a letter bound of `<= 26`
turning an untypable character into `vkey_LWIN`, putting Command down underneath
the typing. Here there is nothing to be wrong. And the double click needs no
special event field: macOS requires `kCGMouseEventClickState` to say 2, Windows
does the detection in the receiving application.

**And one thing is much harder, which is where a real bug was found.** A process
that has not declared DPI awareness is handed *virtualised* coordinates, silently
and consistently. On this machine at 150% scaling:

| | before declaring awareness | after |
|---|---:|---:|
| `GetClientRect` on the EVE window | 1518 x 994 | **2277 x 1492** |
| the client's own `UIRoot` canvas | 2276 x 1491 | 2276 x 1491 |
| implied scale | 1.4993 / 1.5000 | **1.0 / 1.0** |

Nothing errors either way. `SendInput` consumes the same virtualised space, so
the two errors do not cancel — a click computed from the unaware numbers lands a
third of the way across the window from where it was aimed. This is the hazard
macOS's `scale_x`/`scale_y` self-calibration exists for ("don't assume 2.0")
arriving from the other direction: there the ratio is real and must be measured,
here it is an artefact and the right answer is to make it 1.0.
`window_probe.declare_dpi_awareness` is called at import by everything that
touches a coordinate, and the calibration still measures the ratio afterwards
rather than trusting that the call worked.

### Input reaches the client, and that is now observed rather than assumed

One right-click on an overview row, sent by `SendInput`, then a memory read:

```
before: 3974 nodes, 0 ContextMenu
target OverviewScrollEntry canvas region (1444,1151 431x24) -> centre (1659,1163)
scale 0.99956/0.99933 -> screen (3182,1354)
bring to foreground: True
right-click sent
  after 0.4s cumulative: 1 ContextMenu
```

So the chain closes: a coordinate computed from the client's own canvas, through
the scale calibration and the window origin, into `SendInput`, into EVE, and back
out through the memory read as a menu that was not there before. The `Escape`
that follows closes it again.

Issue #176's fourth unverified item is therefore **partly** answered. Input
lands. Whether `SendInput` reproduces the *pacing* the macOS host tuned — the
30 ms hold and the 210 ms gap, and the per-event cost #163 measured — is still
open, and one click is not evidence about pacing.

## 5b. The first Windows bot run

`eve-online-mission-runner`, unmodified, from its own directory.

**What worked.** `elm make` compiled 15 modules (0.19.1 is what Windows installs
and what the app's `elm.json` pins, so the `elm-version` patch macOS needs is not
needed here). The host attached, listed the client, searched the root, and read.
92 readings across 45 ticks at a steady **2.4–2.5s** each. The status line came
out whole — `rats 0 | no target | Lock range: 66000 m (setting 66000, proven -,
refused -, attempt none). | Max targets: 4 …` — and so did the quick-message
clause. With `--execute-input` the glide and the nudge both fired, and both look
exactly like their macOS descriptions:

```
move: glided (1637.7, 485.3) -> (2032.9, 419.3) distance=400.7px in 0.235s
move: already at (2032.9, 419.3) but this is a click -- nudged off and
      glided back for a real movement gesture
```

**The calibration is right to a pixel and says so.** The host reported
`window canvas 2276x1491 does not fit a 2277x1492 pt window at any single scale
(backing 1); falling back to per-axis`, giving 0.99956 / 0.99933. A one-pixel
disagreement between the client's canvas and its own client area, which costs
sub-pixel accuracy. Worth knowing it is there rather than wondering later.

**What the run did not do is complete a gate jump**, and this is the honest state
of it rather than a fix. Every reading decided `A route is set -- travel towards
the mission's system`, then declined the panel path with `The route panel does
not name a next system`, then fell back to right-clicking the route marker, and
that cascade never came back with a menu.

Two things are established about that and a third is not:

- **The panel path declining is consistent with a question CLAUDE.md already has
  open.** PR #170's rule needs the route panel's `Next System in Route` label,
  and a search of the whole captured tree finds no such label and no
  `showinfo:5//` text at all. CLAUDE.md lists "whether a multi-jump route's first
  marker names the next system" as unread.
- **It is not the decoder dropping text.** That was checked rather than assumed:
  of 341 label nodes, 62 carry `_setText`, and the ones that do not have no text
  key in their dict at all. Everything the decoder omits from a label is
  `NoneType`, `tuple`, `dict`, `weakref`, `instancemethod` or a trinity render
  object — which is exactly what `describe_primitive_json` omits on macOS.
- **Whether the route-marker cascade fails here for a Windows reason is not
  established.** It is the cascade CLAUDE.md calls "the worst-behaved in the
  codebase", whose own comment records "'Jump Through Stargate' took 3-4 menu
  opens before being recognized" against an 8x8 icon, and which carries a widened
  200px tolerance because of it. A right-click on an ordinary-sized target opens
  a menu first time, as above. So the mechanism works and this particular target
  is the known-hard one; that is a reason to suspect the cascade rather than
  evidence about it.

## 6. What is here

| file | what it is |
|---|---|
| `eve_mem.py` | the reader: `ReadProcessMemory`, region enumeration, PE export parsing, and the CPython 2.7 decoders. The counterpart of `re_helper.py`. |
| `probe.py` | the feasibility probe and the layout derivation — everything in sections 2–4 |
| `tree_walker.py` | the UI-tree walk, ported from `tree_walker.c` step for step |
| `window_probe.py` | `EnumWindows`/`GetWindowRect`, with the largest-by-area rule carried over, and the DPI declaration everything else depends on |
| `input.py` | the `cg_input` port: `SendInput`, the glide, the foreground lock workaround |
| `win_platform.py` | the Windows side of `botlab_host.py`'s dispatch — issue step 4 |
| `measure_cost.py` | section 5 |
| `verify/VerifyTree.elm`, `verify/verify_tree.py` | runs a captured tree through the **real** `EveOnline.ParseUserInterface` |

`botlab_host.py` itself gains one guarded early return per platform-bound
function and nothing else. On macOS it is the code it was, reached the same way,
with one boolean test in front of it — which is the most this port can offer
towards "macOS stays primary and must not be destabilised" given that nothing
here can run a macOS test.

### The tree the bot would have been handed

This is the check that matters, because "the tree looks right" is not this repo's
standard and the failure mode under discussion is invisible to any check the
reader marks its own homework with. A captured tree, through the real parser:

```
decoded                     yes
nodes in the tree           4059
nodes with a display region 2562
display texts               60

  contextMenus                     0        shipItemCards                  0
  shipUI                           1        inventoryWindows               0
  targets                          0        chatWindowStacks               2
  infoPanelContainer               1        agentConversationWindows       0
  overviewWindows                  3        agentMissionInfoPanelEntries   0
  selectedItemWindow               1        neocom                         1
  dronesWindow                     0        messageBoxes                   0
  probeScannerWindow               1        layerAbovemain                 1
  stationWindow                    0        moduleButtonTooltip            0
```

The zeros are as informative as the ones: no context menu was open, no target was
locked, the drones window was closed, and the ship was in space with an overview,
a selected item and a probe scanner — which is what was on screen. `layerAbovemain`
is where `quickMessage` lives, and the raw tree carries `l_abovemain`, `l_main`,
`l_modal` and `l_menu` under a root whose `_name` is `Desktop`.

## 7. What is not built, and what nobody should assume about it

The issue's order of work is 1–5. **All five are done**, in the sense that each
has been attempted and the result recorded — which is not the same as the host
being finished. A bot runs, reads, decides and drives the mouse; it has not yet
been watched completing a mission, or a gate jump, or anything else end to end.

**No run has been flown to any outcome.** The longest was 60 ticks, bounded on
purpose, and it spent all of them in one branch. Nothing here has exercised
combat, looting, docking, an agent conversation, the ammo swap, the retreat, or
any of the guards CLAUDE.md spends most of its length on. **A green reading is
not a working bot**, and the distance between the two is most of this repo.

- **`memory_sample`, `live_reader` and `probe` (the C ones) are not ported and
  probably should not be.** All three exist to work around
  `mach_vm_read_overwrite` being priced per call: `live_reader` is a persistent
  helper so the Python path does not pay a process launch per field, and
  `memory_sample` dumps the process because reading it live was too slow to
  explore. `ReadProcessMemory` is callable directly from Python at any size, so
  `eve_mem.py` covers what all three were for. That is a claim about the platform
  and it is worth someone disagreeing with.
- **`botlab_host.py` is untouched.** Nothing is wired into the host's dispatch,
  no bot has been run, and the Elm side has never been driven by this.
- **The 2.4s read wants work before it drives anything**, and the obvious lever
  is already spent. 4,059 nodes take about 10,900 `ReadProcessMemory` calls, and
  the macOS host got 8.6x out of a 4K page cache. Reading in bigger blocks --
  which `ReadProcessMemory` allows and `mach_vm_read_overwrite` does not -- looked
  like the free win and is not:

  | block | median | RPM calls | MiB read |
  |---:|---:|---:|---:|
  | **4 KiB** | **2418 ms** | **10,721** | 41.9 |
  | 8 KiB | 2561 ms | 8,204 | 56.8 |
  | 32 KiB | 4043 ms | 15,463 | 98.0 |
  | 64 KiB | 6606 ms | 111,737 | 127.2 |
  | 128 KiB | 10991 ms | 240,548 | 161.8 |

  Past 8 KiB the *call count* rises, which is the opposite of what a cache is
  for. `ReadProcessMemory` is all-or-nothing: a block straddling the end of a
  mapped region fails entirely rather than returning its readable prefix, and
  falls back to an uncached read. The client's object heap is many modest regions
  rather than a few large ones, so a bigger block straddles one more often and
  each straddle costs a wasted read plus an uncached one. **The remaining cost is
  Python, not the read strategy** — which is the argument for a native helper
  here, and the only argument for one this port has found.
- **One reading, one client, one machine, one patch level.** Every number here
  comes from a single session against a single account's client. The layout in
  section 2 is a measurement of *this build*, and `probe.py` exists so the next
  build can be measured rather than assumed.

## Running it

```bash
cd tools/windows-host
python probe.py                          # is it readable, and what is the layout
python tree_walker.py --out tree.json    # capture a tree
python verify/verify_tree.py tree.json   # through the real Elm parser
python measure_cost.py                   # section 5
python window_probe.py                   # the client's window, in physical pixels
python input.py                          # input self-test; sends nothing without --execute
```

And the host itself, which is the macOS one with the dispatch in it:

```bash
cd tools/macos-host/botlab_host
python botlab_host.py <bot source> --max-ticks 45
```

Add `--execute-input` to make it drive the real mouse and keyboard. Without it
the host logs what it would have sent, which is how every reading in this
document was taken.

Needs 64-bit Python 3 and, for the verifier, `elm` and `node`. The client's
`elm.json` pins 0.19.1, which is what Windows installs, so the `elm-version`
patch `botlab_host.py` does on macOS is not needed here.
