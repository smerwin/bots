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

## 6. What is here

| file | what it is |
|---|---|
| `eve_mem.py` | the reader: `ReadProcessMemory`, region enumeration, PE export parsing, and the CPython 2.7 decoders. The counterpart of `re_helper.py`. |
| `probe.py` | the feasibility probe and the layout derivation — everything in sections 2–4 |
| `tree_walker.py` | the UI-tree walk, ported from `tree_walker.c` step for step |
| `window_probe.py` | `EnumWindows`/`GetWindowRect`, with the largest-by-area rule carried over |
| `measure_cost.py` | section 5 |
| `verify/VerifyTree.elm`, `verify/verify_tree.py` | runs a captured tree through the **real** `EveOnline.ParseUserInterface` |

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

The issue's order of work is 1–5. **Steps 1 and 2 are done and step 3 is a third
done.** Steps 4 and 5 are not started.

- **`cg_input` → `SendInput` is not ported.** No input has been sent to the client
  by any of this. That means the issue's fourth unverified item — whether
  `SendInput` reproduces the pacing the macOS host tuned, the 30 ms hold and
  210 ms gap — is exactly as open as it was, and so is everything about
  `BringWindowToForeground`, the double-click click-state, and the drag that must
  not pause after the press. **Driving a live account's client is an outward
  action and it is the operator's call, not this port's.**
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
```

Needs 64-bit Python 3 and, for the verifier, `elm` and `node`. The client's
`elm.json` pins 0.19.1, which is what Windows installs, so the `elm-version`
patch `botlab_host.py` does on macOS is not needed here.
