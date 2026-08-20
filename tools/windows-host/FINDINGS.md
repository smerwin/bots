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
| **Whether `SendInput` reproduces the input pacing** | **Yes, for everything a run needs.** 28 runs have driven the real mouse and keyboard: anomalies entered, rats locked and killed, gates jumped, stations docked, a fleet invitation accepted. One thing is *not* clean — see "Clicks the client does not answer" in section 8, where a batched lock step asked for 372 clicks and the target bar answered 151. |

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
| `run_saxrat.sh`, `stop_bots.ps1` | start one run, refusing if a host is still alive — see section 8 |
| `launch_character.py` | press-and-hold a character's avatar in the launcher, and wait for the client to reach the game |
| `engagement_watch.py` | screenshot the client on each anomaly arrival, first lock and departure |
| `window_capture.py` | one BitBlt-and-PNG, shared; reports whether the window was frontmost |
| `raise_window.py` | raise a window past the foreground lock, by hand, verified afterwards |
| `scan_results.py` | read the probe scanner's own rows, so `anomaly-name` is a reading rather than a guess |

### These four came out of the session scratchpad, and two of them are merges

`raise_window.py`, `window_capture.py`, `scan_results.py` and the two run
scripts were written ad hoc while operating runs and lived in a temp directory,
which is a poor place for the only copy of the thing that starts a run. Folding
them in was mostly deletion:

- **The foreground lock had one workaround and needed two.**
  `input.bring_window_to_foreground` does the documented `AttachThreadInput`
  dance and *still* returned `False` for the EVE launcher — Windows keeps a
  foreground **lock** the attach alone does not clear, and a synthetic ALT is
  what drops it. So the escalation moved into that one function rather than
  beside it, as **`allow_synthetic_alt`, defaulting off**. It must stay off by
  default: `GetLastInputInfo` cannot tell a synthetic key from a person, the
  host reads it to stand down for five seconds after human input, and
  `BotFramework.elm` prepends `BringWindowToForeground` to *every* input
  sequence — so a default-on ALT would have the bot press ALT at itself and
  then idle for the human it just imitated, forever. The bot pays a failed
  raise; tools that are not the bot pass the flag.

  What it cost while missing: a press-and-hold aimed at correct screen
  coordinates landed on whatever was on top instead, and `launch_character.py`
  reported only that no client appeared within 300 s. The capture taken to
  diagnose it showed the terminal that was covering the launcher.

- **There were two BitBlt-and-PNG encoders.** `engagement_watch.py` had a
  `StretchBlt` downscale with row-sliced BGR→RGB; the scratchpad's `shot.py` had
  a full-size grab and a per-pixel Python loop — 3.8 million iterations on this
  client for an identical picture. `window_capture.py` is the one that survived,
  and `engagement_watch.py` now imports it.

  The property worth keeping is that `capture_window` returns **`frontmost`**.
  `BitBlt` from the desktop DC copies whatever is actually on top, so a covered
  window yields a flawless screenshot of the wrong application — and that
  picture is indistinguishable from a good one.

- **`scan_results.py` answers a question the corpus cannot.** `anomaly-name`
  matches the probe scanner's **Name** cell and no bot has ever logged it, so
  the site words the launcher asks for appear zero times across every recorded
  run and CLAUDE.md's open comma question is unanswerable at any corpus size.
  A closed scanner and an empty one are given different words, deliberately.

### Both branches have now run, and the Name cell has been read for the first time

The no-`ProbeScannerWindow` path ran first and reported correctly, naming the
eight scanner-ish types that were open instead. The populated path ran an hour
later, when run 48's hour-one hedge opened the scanner:

```
ScanResults     ['Signal', 'Distance', 'ID', 'Name', 'Group',
                 '32 km', 'EGC-528', 'Sansha Refuge', 'Combat Site',
                 '<center>No signatures or anomalies in current system</center>']
ScanResultNew   ['32 km', 'EGC-528', 'Sansha Refuge', 'Combat Site']
```

**That is the first reading of the scanner's Name cell this project has.**
CLAUDE.md's §197 records that neither bot has ever logged it — a run prints the
*ID* (`We are in anomaly 'EGC-528'`), never the name — so the site words the
launcher itself asks for occur zero times across every recorded run, and no
corpus of any size can answer what that column may contain. `Sansha Refuge`
carries no comma, which is one data point against the open question rather than
an answer to it: one name is not a distribution, and the `Dread Assault: Blood
Raider Temple` already on record shows the column takes punctuation.

Note the last cell. The window carries `No signatures or anomalies in current
system` **while a result is in it** — a placeholder the client leaves in the
tree rather than removes, so anything reading the window's joined text would
conclude the system is empty while a Sansha Refuge sits 32 km away. Read the
row nodes, not the window's text.

**Still unverified: `raise_window.py`'s CLI wrapper**, run only as `--help`. Its
raise path is the scratchpad original's, proven on the launcher; raising a
window out from under a working bot is the one thing its own docstring says not
to do.

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

**That paragraph is superseded.** It read "no run has been flown to any
outcome ... the longest was 60 ticks", which was true when written and stopped
being true the same week. saxrat has since flown 28 runs on this machine, the
longest **eight hours to its own planned end** — run 28: 32,559 decisions, 76
anomalies visited, bounties landing, gate jumps taken from the selected-item
panel, and a clean dock at session end.

What that leaves genuinely unexercised is narrower and worth keeping separate
from what has now run:

- **`eve-online-mission-runner` has never been flown here.** Only saxrat has.
  So agent conversations, missions, briefings, the acceleration-gate path and
  the abandonment are all untested *on Windows*, whatever their macOS standing.
- **The 2023-interface bots** are unchanged from CLAUDE.md: unit-checked, never
  run live, on either platform.
- **Nothing has lost a ship here**, so the ship-loss verdict and pod recovery
  have never latched on this machine either.

**A green reading is still not a working bot.** What the runs have moved is
which half of that sentence applies.

- **`memory_sample`, `live_reader` and `probe` (the C ones) are not ported and
  probably should not be.** All three exist to work around
  `mach_vm_read_overwrite` being priced per call: `live_reader` is a persistent
  helper so the Python path does not pay a process launch per field, and
  `memory_sample` dumps the process because reading it live was too slow to
  explore. `ReadProcessMemory` is callable directly from Python at any size, so
  `eve_mem.py` covers what all three were for. That is a claim about the platform
  and it is worth someone disagreeing with.
- **`botlab_host.py` is no longer untouched**, and this bullet is kept only
  because it was wrong rather than deleted. The Windows reader, the native
  walker and `input.py` are wired into its dispatch; it has driven the Elm side
  for 28 runs; and it carries one Windows-motivated change of its own, the ESI
  character guard — `game_window_title` is stored from
  `ListGameClientProcessesRequest` and passed as `expected_character`, so a
  token belonging to a different pilot raises rather than routing somebody
  else's client. That failure had already cost a whole session here.
- **The read is 1.37s and it is not memory reading.** This was measured rather
  than assumed, and the answer overturns the obvious framing.

  A 4 KiB `ReadProcessMemory` costs **9.6 µs** and an 8-byte one **5.2 µs**
  (`ProcessReader.call_overhead`). A walk makes ~10,000 of them, so **the reads
  are 0.10s of it**. Everything else is CPython interpreter overhead — which is
  exactly where the macOS project was before it wrote `tree_walker.c`: "profiling
  showed the Python implementation had become genuinely CPU-bound on CPython
  interpreter overhead (millions of small operations for one tree read) once
  round-trip count and data volume were no longer the bottleneck."

  Profiling one tree found **1,163,675 reads for 3,617 nodes** — a 15.5x repeat
  factor, one address read 60,824 times — because `primitive` tries decoders in
  turn and each re-read `ob_type` to see whether it applied. Three changes, each
  measured:

  | | median |
  |---|---:|
  | as first written | 2405 ms |
  | + per-request memo on `type_of` and `read_str` | 2046 ms |
  | + single-page fast path in `read_cached` | 1486 ms |
  | + `iter_unpack` over dict entries | **1370 ms** |

  **43% off, and the floor is still ~13x the read cost.** Two things were tried
  to beat it and both lost, recorded in `read_cached` so they are not retried:
  bigger fixed blocks (call count *rose* to 111,737 at 64 KiB, because a block
  straddling the end of a mapped region fails whole), and bigger blocks clipped
  to the containing region, which removes the straddling and still loses because
  read cost scales with bytes copied — 256 KiB blocks moved 1.6 GB per walk and
  took 5.8s.

  So the case for a native helper is the same one macOS made, and it is now
  quantified: **the work is interpreter overhead, and there is no caching
  strategy that removes it.** A C compiler was found and `tree_walker.c` was
  written, so this *was* attempted — the walk is **143 ms** against the Python
  path's 2,405, and the table below is what that bought. The sentence that stood
  here ("not attempted") contradicted the measurement two bullets down for two
  days, which is the hazard of a findings document that is appended to rather
  than re-read.

- **Read time is a correctness property here, not only a throughput one**, which
  is the part that was not expected. `ShipUI.hitpointsPercent` is read out of a
  widget the client is mutating, and CLAUDE.md names the mechanism for a garbage
  value: "a read landing on a reallocated object". Over one saxrat run, **143 of
  893 ship-gauge readings (16%) were implausible** (>100%), against a macOS
  record of corruption that is "always for exactly one reading and always
  surrounded by sane values". Worse, they arrive in *runs* — `2991600, 2991600,
  44, 44, 44, 44, 44, 0, 0, 0, 0, 0` — and `believed`, the healthier of the last
  two readings, is built to absorb a single bad reading and cannot absorb
  consecutive ones. The retreat fired on it: 229 `get out get out get out` lines
  on a hull that was never below full armour, ending that run's usefulness.
  A longer walk means more of the tree is reallocated mid-walk, so this should
  fall with read time. **It does, and the effect is total.** Same bot, same
  settings, same client, the only change being which walker read the tree:

  | | walk | gauge readings | implausible | false retreats |
  |---|---:|---:|---:|---:|
  | Python walker | 2405 ms | 893 | **143 (16%)** | 229 |
  | C walker | 143 ms | 671 | **0 (0%)** | **0** |

  In-host the read went from 2.4–2.5s to **0.25–0.36s**, and the corruption that
  ended a three-hour run did not occur once. That settles the mechanism CLAUDE.md
  named — a garbage gauge value really is a read landing on a reallocated object
  — and it is the clearest argument this port has for the native walker: not
  throughput, but the difference between a retreat that fires on nothing and one
  that does not.

  **It does not explain the ship-UI parse misses**, which is worth stating
  because it would be easy to assume one fix covered both. Those ran at
  **10.4% (78 of 749)** on the C walker against 4.6–6.7% on the Python one — no
  better, and possibly worse. They are a separate phenomenon and remain
  unexplained.
- **One reading, one client, one machine, one patch level.** Every number here
  comes from a single session against a single account's client. The layout in
  section 2 is a measurement of *this build*, and `probe.py` exists so the next
  build can be measured rather than assumed.

## 8. Operating a long run on Windows

Sections 1–7 are about reading the client. This one is about everything around
it, and every entry has already cost a wrong diagnosis on this machine. The
architecture, the struct layouts and the bot logic all transfer from macOS
unchanged; the *tooling* does not, and that is where the time went.

### Git Bash cannot see native Windows processes, in both directions

`pgrep` answers "not found" for a perfectly healthy bot, and **`pkill -f`
matches nothing, exits 1, and looks exactly like success.** Both halves have
cost a session:

- A watchdog used `pgrep`, reported `BOT GONE` falsely, and *broke out of its
  loop* on that — so nothing watched an eight-hour run.
- Every "restart" for half a day used `pkill -f botlab_host.py` and killed
  nothing, silently. **Seven hosts accumulated**, started 13:01 through 15:54,
  all driving the same mouse. The web console served whichever bound port 8787
  first, so its numbers described a run three hours stale while reading as
  current, and the mouse contention is a plausible contributor to the
  stray-context-menu storm of that afternoon.

Ask Windows instead, and match on the command line rather than the image name —
`Get-Process python` calls a dead run healthy the moment any other Python is up,
which during a session of probe scripts is most of the time:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*botlab_host*' }
```

**Never let a liveness check terminate the watch**, and have the stop script
*verify* rather than report — the first version of `stop_bots.ps1` printed
`all stopped` while its own query was malformed, which is the failure it was
written to prevent.

### `SetForegroundWindow` is a request, and the documented workaround is not enough

`input.bring_window_to_foreground` does the documented `AttachThreadInput`
dance and **still returns `False`** against the EVE launcher: Windows keeps a
foreground *lock* the attach alone does not clear. A synthetic ALT press
releases it, after which `SetForegroundWindow` takes on the first attempt.

This matters more than a failed focus, because **a screen capture of a window
that was not raised looks exactly like a capture of one that was.** A grab taken
at the launcher's coordinates while it sat behind other windows returned those
other windows, and was read as the launcher. Verify by reading
`GetForegroundWindow` back; never trust the call. `launch_character.py` does
this and refuses to click otherwise, on the grounds that the click would
otherwise land in whatever is really there.

### The UI-root cache is per boot, and a cold scan looks like a hang

After a reboot the cached root address is stale, so the host does a full scan:
**about four minutes of silence** before the first reading, with the log
repeating `Search the address of the UI root in process N` and not growing. It
is working — the tell is the host's CPU time climbing and the log jumping by
tens of kilobytes when the scan lands. Do not restart it.

### "In game" is not "the process exists", and `ShipUI` does not settle it

A freshly launched client sits on the character-selection screen with a
perfectly readable UI tree **containing a `ShipUI` node**, so a readiness check
that counts nodes or trusts `ShipUI` declares victory about a minute early —
observed at 453 nodes with the window still titled plain `EVE`. The honest
signals are an `OverviewWindow` (in space) or a `LobbyWnd`/`StationWindow`
(docked), and the window title becoming `EVE - <character>`.

### The launcher does not expose its character list

Chromium keeps its accessibility tree off, so UI Automation sees one child
called `Chrome Legacy Window` and nothing else — no character names, no
buttons. The launcher's own state is no better: `state.json` is a DPAPI-encrypted
`v10` blob (it holds auth tokens; do not go decrypting it), and
`launcher-data.json` carries settings but no roster.

What *is* readable and worth reading is `launcher-data.json`'s
`actionToActivateMethod` and `actionToActivateSpeed`. That answers a question
CLAUDE.md files under macOS quirks — "PLAY NOW ignores synthetic clicks" is
neither a quirk nor macOS: **PLAY NOW launches whichever character the launcher
has selected**, and `autoSelectCharacter` is on, so it is the last one played
rather than the one you meant. Holding a character's avatar launches that
character. `launch_character.py` reads the setting rather than assuming the
gesture, stores avatar positions as fractions of the launcher window so they
survive a resize, and verifies the character it got from the client's window
title afterwards.

### Clicks the client does not answer

Run 28 ended with `Lock batch: asked 372 and the bar answered 151` — a **59%
shortfall**. Two candidates, and they are distinguishable: input dropped under
load (the macOS side records posted events costing 53–100 ms in exactly the two
runs that lost a typed query, against under 18 ms elsewhere), or the client
taking one lock per input burst, in which case the shortfall is consistently
batch-minus-one. Unresolved, and it matters beyond throughput: the same window
is where an overview row can shift under a click, which is the likeliest feeder
of the lock-range ratchet in issue #206.

### A window on top of the overview: clicks that land somewhere else

Run 2 lost **3 hours 45 minutes** to this, in one anomaly, with the ship safe
and the host healthy the whole time. It is the sharpest edge found on Windows so
far, it is not a Windows bug, and it explains two things this file already
carries as unresolved.

**What happened.** The client's Probe Scanner sat over the top of the PVE
overview. Measured live, mid-stall:

| | origin | size | spans |
|---|---|---|---|
| `ProbeScannerWindow` | (454, 122) | 373 x 379 | x 454-827, y 122-**501** |
| `OverviewWindow` (PVE) | (385, 431) | 310 x 471 | x 385-695, y 431-902 |
| the one rat row | (394, 487) | 292 x 17 | x 394-686, y 487-504 |

`lockTargetFromOverviewEntry` clicks the row's centre, which is
(394 + 146, 487 + 8) = **(540, 495)** -- six pixels above the Probe Scanner's
bottom edge. Every lock click for three and three quarter hours went into the
Probe Scanner. About 20,000 input events, no lock, no menu, no shot fired
(`Outgoing fire: 0 landed / 0 missed`), and the row sitting there at 3,786 m
inside a proven 42,000 m lock range.

**The rule that misses it.** `overviewEntryIsDisplayed` asks whether a row is
rendered *within its own window*. It has no notion of another window on top,
because the UI tree carries geometry and not z-order. So a row can be
`_display`ed and unclickable at the same time, and nothing in the bot can
currently tell the difference between "the client refused" and "the click never
arrived".

**Nothing escalates, which is why it ran for hours.** `stalemate` is the counter
that would give up (`200 to close in and 300 to leave`), and it only advances
while there is an *active target*. An occluded row never becomes one, so the
counter sat at 0 for the whole stall. `approach`, `menus` and `stuck` likewise.
`I am stuck here and need help to continue` fired three times in 124k lines, and
from an unrelated ship-UI blip rather than from this. The same shape as run 41's
2,266 km double-click, which got a fix for the approach path specifically rather
than a general one.

**It poisons the lock-range learning, and that is the part worth reading twice.**
`recordLockRangeAnswer`'s refusal test takes four things at once: the attempt has
had its readings to land, the row is still in the overview and still `_display`ed,
the row still does not read targeted or targeting, and the target bar was empty at
both ends. **An occluded row satisfies all four.** Occlusion does not change
`_display`, and the click never reaches the client's targeting code at all, so the
bot books a refusal at a distance the client never actually refused.
`lockRefusedAtMeters` only falls. Observed at the end of the stall:

```
lock 42000m (set 39000 client - proven 42000 refused 3786 attempt none)
```

A refusal at 3,786 m standing against a proof at 42,000 m -- the bounds crossed,
from a click that never landed. This is a concrete feeder for the ratchet in
issue #206, and it is the first one that has been observed rather than suspected.

**It is also a candidate for the lock shortfall above.** Run 28: asked 372,
answered 151, **40.6%**. Run 2: asked 39, got 16, **41.0%**. A window that
covers part of an overview drops a stable fraction of clicks, which is what a
consistent percentage across unrelated runs looks like. Not proven -- run 28's
window layout was not recorded -- but it is a third candidate beside the two
listed above, and the cheapest to rule in or out on the next run by writing the
window rectangles into the log.

**The fix: click a visible sub-region, not the centre.** For a row rectangle R,
subtract the rectangles of the other windows that overlap it, and click the
centroid of the largest surviving rectangle instead of the centre of R. Here the
row's left 60 px (x 394-454) and its bottom 3 px (y 501-504) were clear, so the
lock was reachable the whole time and the bot was aiming at the one part of the
row that was not.

Two properties make this worth doing rather than merely tidy:

- **It needs no z-order.** Subtracting *every* overlapping window's rectangle,
  whether or not it is on top, only ever over-excludes: the worst case is
  declining to click a row that would have worked. Z-order would make it exact,
  but the conservative version is safe and can be written today. Whether the
  tree exposes layering at all is the open question -- sibling order is a guess
  and has not been tested.
- **An empty result is the honest answer.** If nothing survives the subtraction
  the row is genuinely unclickable, and it should then be excluded from
  `overviewEntriesToLock` *and* barred from teaching a refusal. That single
  change would have turned this from a 3h45m silent livelock into a bot that
  says the row is buried and moves on, and would have kept the lock-range
  bounds clean.

### Smaller ones, each having cost something

- **The run logs are PowerShell-captured and wrapped.** A status clause
  continues on the next line, so `grep -o` truncates it and a 16-system circuit
  can read as `… -> Ana`. Grep with context, not `-o`. The logs also carry NUL
  bytes, so `grep` calls them binary — pass `-a`.
- **`/tmp` is not the same path to Git Bash and to Windows Python.** Bash writes
  `C:\Users\…\AppData\Local\Temp\x`; Python reads `\tmp\x` and fails. That
  emptied a pull request body once, through a `>` redirect that created an empty
  file.
- **Echo inflation makes raw counts wrong.** Every game-log line is reprinted
  under each decision, so `grep -c` answered 3,435 for a run with 50 distinct
  bounties. Count distinct `[timestamp] (channel)` entries, and prefer
  `Quick message (on screen now)` over raw occurrences for anything about
  popups.
- **`elm` here is 0.19.1**, which is what every bot's `elm.json` pins, so the
  `elm-version` patch CLAUDE.md describes for macOS must *not* be applied — it
  stops the app compiling.
- **`elm-format` every Elm edit and write LF.** Python's `write_text` produces
  CRLF, which turns a small change into a whole-file rewrite that conflicts with
  everything.
- **Game logs are at `C:\Users\<user>\Documents\EVE\logs\Gamelogs`**, resolved by
  `win_platform.game_log_directory()`.
- **`git push --force-with-lease` refuses with "stale info" when no
  remote-tracking ref exists**, which is the state a fresh branch is in here.
  Name the expected commit — `--force-with-lease=<branch>:<sha>` — rather than
  reaching for `--force`.

### Settings have to travel in a file, not in arguments

`Start-Process -ArgumentList` flattens its array into one command line with
naive quoting, so a settings value containing a space is split. The first run
that tried it died at startup on

```
botlab_host.py: error: unrecognized arguments: Bistot
```

from `accept-fleet-invite-from=Gal Bistot`. Write the settings to a file and
have a shim read it and hand the host one string. This is also why the launcher
here cannot be a thin wrapper the way `run_saxrat.sh` is on macOS.

**And a console settings POST is runtime-only.** `/api/settings` changes the
running session and does **not** write the settings file, so the next launch
silently reverts to whatever is on disk. A run started at a corrected threshold
of 1000 came back at 900 with a removed setting live again, and followed a fleet
broadcast across the map before it was caught. Change the file *and* the
session, every time.

### Restarting a run costs about three seconds, not minutes

Measured on this box, kill to first decision. CLAUDE.md's warning — run 7's ship
lost in a four-minute gap — is about a **cold dependency fetch**
(`Verifying dependencies 0/17`), not about every cycle. With a warm build,
cycling mid-fight is far cheaper here than that note implies, so the thing to
check before restarting is the damage window rather than the clock.

**A session cannot be extended without one** (#230): the host parses
`@host extend-session` and the mission runner writes it, but saxrat never does,
and the console's only commands are `pause`, `resume` and `stop`.

### Never ask the circuit for a route to the system the ship is in

Asking for a destination the ship already occupies returns `Route 0 Jumps` with
no marker, which `routePanelSaysNoDestination` correctly reads as no route. The
ask can therefore never be satisfied, and after `routeAskGiveUpReadings` the bot
concludes **the host** is broken and latches route-setting off for the whole
session:

```
Asked for a destination for more than 20 readings and no route ever appeared
-- this host does not set destinations, so stop asking and wait where it is safe.
```

486 of those in one run, while the host's own stderr said
`# ESI: destination 'Hamse' set (30003547)` — it worked, and the two are never
compared. The run spent its last three hours confined to one system: one kill in
45 minutes, against 82 in the first 115. Filed as #262; until it lands, seed the
destination to a system the ship is **not** in before starting.

### `eve_repl` has two dead ends worth knowing before relying on it

- **`KEYS` has ten entries and `s` is not one of them**, so `eve.key("ctrl","s")`
  raises `KeyError` and the autopilot is simply unreachable from the repl. The
  letters all exist in the separate `KEYCODE` table, so the two tables disagree
  about which keys exist.
- **`eve.jump`, `warp_to` and `dock` act on an overview row by name, so they
  cannot resolve anything that is not on the grid the ship is on.** In a
  deadspace pocket — an anomaly or an escalation site — there are no stargates
  on grid at all, so none of them can take the ship out of one; warp to a
  celestial first, or let the bot travel the route. **This is about the pocket
  and not about the client.** An hour went into concluding the overview preset
  itself carried no stargate rows, which is wrong: from ordinary space
  `eve.jump("Hamse")` resolved the gate and flew it in a single call, with four
  stargates on the overview at the time. The earlier reading was taken inside a
  pocket and generalised.

### `engagement_watch.py` is the screenshot tool, and it does not post input

`screencapture` does not exist here. `tools/windows-host/engagement_watch.py`
follows a live run log and grabs the client on anomaly **arrival** and on the
**first lock** inside it — one of each per site, so a four-hundred-reading site
costs two pictures rather than four hundred.

It deliberately posts nothing: the host stands down for five seconds after any
human mouse or keyboard event and `GetLastInputInfo` cannot tell a synthetic
key from a real one, so the ALT press that beats the foreground lock would idle
the bot on every screenshot. It records which window was foreground in the
filename instead, because a `BitBlt` of an occluded window copies whatever was
really on top and that picture looks exactly like a good one.

Its `sys.path.insert` points at a checkout that need not exist; run it from its
own directory. And **the client pid and window handle both change on every
relaunch** — re-resolve both, never carry either across a restart.

## 9. One machine, no toolchain: the native walker was never built here

This machine (host for `Olivia Ochre`'s saxrat runs) runs measurably slower
than others flying the same bot, and the first hypothesis was thermal
throttling — a plausible guess for a mobile CPU (AMD Ryzen 5 5500U, 6c/12t,
2.1 GHz base) under sustained load. `\Processor Information(_Total)\% Processor
Performance` (the reliable real-throughput counter on modern AMD parts;
`\Processor Information(_Total)\Processor Frequency` is documented-unreliable
on this family, and `Win32_Processor.MaxClockSpeed`/`CurrentClockSpeed`
reflects the rated label rather than real-time boost) showed no sustained
drop, and `MSAcpi_ThermalZoneTemperature` is not exposed at all on this box —
no OEM sensor driver. Thermal throttling was ruled out rather than found.

**The real cause was narrower and specific to this one machine:
`tree_walker.exe` had never been built here.** `TreeWalkerClient` falls back
silently to the pure-Python walker whenever the compiled binary is absent —
one line to stderr and nothing else, deliberately (see section 6, "falls back
... rather than failing") — so the host runs correctly and simply slower,
which is exactly the shape that goes unnoticed. No MSVC toolchain had ever
been installed on this machine, so `tree_walker/build.bat` had nothing to
compile against.

Fixed by installing Visual Studio 2022 Build Tools with the C++ workload via
`winget`, then running `tree_walker/build.bat` with its fully-qualified path
(a first attempt via `Set-Location` + a relative filename failed with
`'build.bat' is not recognized` — the working directory set in one PowerShell
call did not carry into the `cmd.exe` subprocess it spawned). Result:
`tree_walker.exe`, 164,352 bytes, and the next saxrat launch printed
`# tree_walker: native (tree_walker.exe)` in place of the "not built" line.

**The gain measured here is real and much smaller than section 7's
143ms/2405ms figure, and the reason is the read budget rather than the
walker.** That comparison was taken at `max_depth=16, max_nodes=5000` against
a 3,495-node tree on a different machine; `_read_from_window`'s own budget has
since been raised twice (its comments record why — content sitting 19 levels
deep, a mission grid with 5,554 nodes silently truncated at the old 5,000-node
cap) and is now `max_depth=24, max_nodes=20000`. Measured on this machine,
same character, same settings, comparing the saxrat run immediately before the
build against the one immediately after — the only variable changed being
which walker answers `ReadFromWindow`:

| | `RequestToVolatileProcess` (tree_walker read) dispatch | `InvokeMethodOnWindowRequest` (screenshot) dispatch |
|---|---:|---:|
| pre-build, Python walker (`saxrat_20260819-205456.log`, n=171) | mean **3.335s**, min 3.203s, max 4.235s | mean 4.847s, max 6.156s |
| post-build, native walker (`saxrat_20260819-214548.log`, n=110) | mean **2.359s**, min 2.171s, max 2.907s | mean 4.279s, max 5.625s |

**About 1.4x, not 8.7x**, on the memory read specifically — real, and worth
having, but a fraction of the isolated-benchmark figure. A larger tree at a
larger depth/node budget means more nodes for the C walker's own fixed
per-node cost to add up over, and a much larger JSON payload to marshal across
the stdin/stdout pipe and decode with `json.loads` on the Python side — both
untouched by moving the walk itself from Python to C. Nobody has profiled
which of those two dominates on this machine; the number above is what
shipped, not a diagnosis of where the remaining ~2.2-2.4s goes.

**The screenshot read (`InvokeMethodOnWindowRequest`) is untouched by this fix
and is now the larger of the two per-cycle costs** — mean 4.28-4.85s against
the memory read's 2.36-3.34s. It is not memory reading at all: it is the
second, independent per-cycle read the framework issues alongside
`ReadFromWindow` (see the Architecture section of `CLAUDE.md`), returning
`windowRect`/`clientRect`/`imageData` so the host can translate the memory
tree's internal coordinates into real screen pixels for clicking — the bot's
sole answer to "where on screen is this button". Both reads are dispatched
serially in `run_bot`'s task queue, so the two costs simply add: pre-build
~8.18s of read time per cycle, post-build ~6.64s, both dominated by the
screenshot rather than the walk. **If this machine still feels slow relative
to its neighbours after this fix, the screenshot capture path is where to look
next, not the tree walker.**

**Unverified: whether the same before/after ratio holds on a quiet, docked
reading.** Both logs compared here are mid-session, in-space readings, likely
close to the 20,000-node budget; a much smaller tree — docked, few overview
rows — may show a ratio closer to the isolated benchmark's, since the fixed
IPC/JSON cost would be a smaller share of a smaller payload. Nobody has run
that comparison.

## 10. `bring_window_to_foreground` was un-maximizing the client on every call

`input.py`'s `bring_window_to_foreground` called `ShowWindow(hwnd, SW_RESTORE)`
unconditionally, commented "in case minimised". `SW_RESTORE` (value 9) does not
mean "if minimised, restore to normal" — it means "leave whichever of minimised
or maximised state the window is in, and go to the last windowed size and
position", every time it is called, on a window in either state. So a call
aimed at a window that was already maximised silently un-maximised it, on
every single invocation — and `BotFramework.elm` prepends this call to *every*
input sequence, so the common case (already frontmost, already maximised) paid
it regardless.

The result read as several unrelated bugs before the mechanism was found: an
avatar press-and-hold aimed at launcher-window-relative coordinates that used
to be right and stopped landing, undock clicks that stopped landing, the
client window observed at an old, sometimes off-screen rect (`(-397, 221)
1726x1090` on one capture) with other windows overlapping it. Confirmed live: a
`ShowWindow(hwnd, SW_MAXIMIZE)` + `SetForegroundWindow` restored the window to
its expected maximized geometry, and the very next undock click — which had
been silently missing — landed.

**Fixed by guarding on `IsIconic(hwnd)` first** — one extra syscall, and the
only question `SW_RESTORE` was ever needed to answer (is this window genuinely
minimised). A maximised or already-normal window is now left exactly as it
was:

```python
if _user32.IsIconic(wintypes.HWND(hwnd)):
    _user32.ShowWindow(wintypes.HWND(hwnd), 9)  # SW_RESTORE, genuinely minimised
```

`IsIconic` is called through the same informal ctypes style already used for
`ShowWindow`/`SetForegroundWindow` in this function, with no new
`argtypes`/`restype` declared, matching the file's existing convention for
this block.

**Verified live, once, not through an automated test** — no `tests/` directory
exists yet in `tools/windows-host/`. Called `win_input.bring_window_to_foreground`
directly against the real, already-maximized EVE client and confirmed
`client_width`/`client_height` unchanged before and after (1710x1051 both
times). Not verified: the genuinely-minimised case still restoring correctly
after the guard (nothing changed about that branch, but nothing has re-run it
either), and whether the launcher window — which goes through the same
function — shows the identical symptom; it was not captured mid-bug.

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
