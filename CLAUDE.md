# Project: macOS-native EVE Online bot host (no BotLab.exe / reactor.botlab.org)

A macOS-native replacement for the closed-source `BotLab.exe` "volatile host",
so the Elm bots in `implement/applications/eve-online/` run on Apple Silicon
without the Windows client and without reactor.botlab.org (BotLab's paid
licensing backend). Non-commercial, not for distribution.

**Status: working.** The host runs unmodified Elm bot source end to end against
the live client — real memory reads, real decisions, real mouse and keyboard
input. Remaining work is refinement, not architecture.

## Start here

Run a bot:

```
cd tools/macos-host
./run_mission.sh          # or ./run_saxrat.sh
./run_mission.sh --help   # this bot's settings and the host's flags
```

Both launchers pass `--execute-input`: they drive the real mouse and keyboard,
and they kill any bot session already running (two bots fighting over the cursor
is chaos). Each bot's `Bot.elm` header lists the game-client setup it needs —
overview columns, module rows, keybinds — and the bot cannot work around a
client that is set up differently.

Prerequisites, both one-time and both explained below: SIP debugging
restrictions off, and `brew install elm`.

The three things a newcomer most often needs to know:

- **A decision in the log is not an action.** The bot re-derives its decision on
  every framework event, several per game reading, but only dispatches input
  once per cycle. Repeated identical decision lines usually mean one action, not
  many. Read `send-effects` task lines for what actually reached the client.
- **The bot only sees what the overview shows.** Rows scrolled out of view are
  in the UI tree but not rendered, and clicking one acts on whatever row was
  recycled into its place.
- **Nothing here is timestamped.** Log lines carry `# [tick.substep] (Ns)`,
  where the `[N.0]` value is the gap since the previous tick. Summing those
  reconstructs wall-clock to within a couple of minutes per run.

## Architecture

The Elm bot never touches memory. It talks to a "volatile host" over a small
JSON protocol (`EveOnline/VolatileProcessInterface.elm`,
`EveOnline/MemoryReading.elm`): `ListGameClientProcessesRequest`,
`SearchUIRootAddress`, `ReadFromWindow` → a generic `UITreeNode` tree
(`pythonObjectAddress`, `pythonObjectTypeName`, `dictEntriesOfInterest`,
`children`). That shape comes from the open-source **Sanderling** project, which
`BotLab.exe` wraps on Windows. The protocol is OS-agnostic, so a macOS host that
emits the same JSON and executes the same effects runs the existing bot logic
unmodified.

BotLab.exe's own toolchain ("Pine", a custom Elm interpreter) isn't needed
either: a bot's `botMain : InterfaceToHost.BotConfig State` is a plain Elm value
that vanilla `elm make` compiles. `tools/macos-host/botlab_host/Main.elm` is a
port wrapper — copied alongside fetched bot source, not part of it — turning
`botMain` into a `Platform.worker` with hand-written JSON codecs for the
host-interface types. Only `EveOnline.VolatileProcessInterface`'s codecs (used
*inside* the opaque `RequestToVolatileProcess.request : String`) must match the
real protocol exactly, since that is unmodified bot source. On Windows,
BotLab.exe runs the bot's `EveOnline/VolatileProcess.csx` as a C# child process
for that sub-protocol; we don't run it at all, and fake a competent volatile
process in Python instead, dispatching the inner JSON to our own memory-reading
tools.

**Adding a request the real protocol does not have** — `handle_request` answers
`SetAutopilotDestinationRequest`, which no BotLab host has ever seen — belongs
in the Python host and *not* in `EveOnline/VolatileProcessInterface.elm`. The
`request` field is an opaque `String` at the `InterfaceToHost` boundary; that
module's encoder is the bot's convenience for building it, not the boundary
itself, so nothing forces a new request through the vendored codecs. Two costs
if it went there anyway. Bot source is fetched fresh from a GitHub URL in one of
the two supported source modes, so a variant that exists only in this fork's
checkout is simply absent under the other — and absent silently, since a request
never built is a request never missed. And the response half is worse than the
request half: `deserializeResponseFromVolatileHost` is a closed
`Json.Decode.oneOf`, so a response it does not recognise decodes as an `Err`
that lands in `lastRequestToVolatileProcessResult` — a field `BotFramework.elm`
writes and never reads. A whole reply class would vanish without a word, which
is exactly the failure this file keeps a section on.

So the Elm side of this is not merely unwritten, it is **blocked on a channel
that does not exist**. `OperateBotConfiguration` gives a running bot exactly one
way out — `buildTaskFromEffectSequence : List EffectOnWindowStruct -> Task` —
and that vocabulary is mouse moves, buttons, keys and scroll; a station name
cannot be spelled in it. Every `RequestToVolatileProcess` is issued by
`getNextSetupTask`'s closed setup state machine, which a decision cannot reach.
Wiring the bot to this request therefore means changing `BotFramework.elm`
(a new `OperateBotConfiguration` field and a builder beside
`buildTaskFromRequestToVolatileProcess`) *and* the vendored decoder — a change
worth its own live run, not a rider on the host-side plumbing.

Two protocol details worth remembering. `ReadFromWindowResult.Completed
.memoryReadingSerialRepresentationJson` is `Maybe String`, and the UI tree JSON
inside it is **double-encoded** — a JSON string containing JSON, decoded via
`decodeMemoryReadingFromString`. And each cycle issues **two parallel reads**:
the memory-based `ReadFromWindow` *and* an `InvokeMethodOnWindowRequest
ReadFromWindowMethod` (screenshot-based, returning `windowRect`/`clientRect`/
`clientRectLeftUpperToScreen`/`imageData`). The latter supplies the rect that
translates memory-read UI positions into screen coordinates, so both are needed.

**A reading carries one node the client never wrote.** EVE explains every
refusal in its own game log — `You cannot load or unload
<weapon> while it is active`, `You are already managing 6 targets, as many as
you have skill to`, `You cannot launch Acolyte I because you are already
controlling 5 drones` — and until issue #28 the bot could not read a word of it,
while `stall_watch.py` read the same file as ground truth. The watchdog watching
the bot had better information than the bot. The host now appends a
`MacOsHostSyntheticGameLog` node to the tree it emits, one
`MacOsHostSyntheticGameLogEntry` child per line carrying `timestamp`, `channel`
and `text`, and `ParseUserInterface.elm` lifts it into
`ParsedUserInterface.gameLogEntriesSinceLastReading : Maybe (List GameLogEntry)`.

**It rides the UI tree rather than extending the protocol**, for the same reason
#17 could not extend it either. `ReadFromWindowResult` is decoded by the closed
`deserializeResponseFromVolatileHost` `oneOf`, so a new field or a new response
shape needs the vendored decoder changed *and* `BotFramework.elm` changed to
carry it as far as a decision. Riding the tree needs neither: every bot already
calls the parser on every reading.

Four properties are what make injecting a fiction into a structure that
otherwise mirrors real memory safe rather than merely untested:

- **The type name says it is a fiction**, in full, because nothing else in the
  tree is one.
- **It has no display region.** `asUITreeNodeWithInheritedOffset` files a node
  with no `_displayX`/`_displayY`/`_displayWidth`/`_displayHeight` as a
  `ChildWithoutRegion`, and every existing parser here navigates by display
  region, so none of them can reach it.
- **The text sits under `text`, never `_setText` or `_text`.** Those two are
  what `getDisplayText` reads, and `getAllContainedDisplayTexts` runs over the
  raw tree with no region filtering — the mission runner asks it whether the
  whole reading contains "No room for more". A game log line landing in that
  answer would be a refusal dialog the client never showed.
- **`Nothing` and `Just []` are different answers.** The node is emitted even
  with nothing to report, so its absence means "this host provides no game log"
  (BotLab.exe, or `--no-game-log`) rather than "the client said nothing".
  Collapsing those two is how a bot concludes a command was accepted because no
  refusal arrived.

`(combat)` and `(bounty)` are withheld from the bot. Combat is per-shot and
4,484 of the 4,852 lines across five recorded runs, so carrying it would put the
whole cost of this channel in noise no decision uses; bounty is already the
host's own source for kills and ISK, and a second reader of those lines would be
a second source of truth for the same statistic. Everything else is carried,
including channels never seen here — the list is a deny-list, because a channel
silently dropped for being unfamiliar is this repo's signature failure.

**Scoped to the reading by construction.** `GameLogTail` drains its queue while
the tree is being built, so the node holds what the client said between the
previous read and this one, not a growing buffer that would have the bot
answering a refusal from four minutes ago. The tail fans one file offset out to
two queues, because the stderr echo consuming the lines is exactly what kept
them from the bot in the first place — a second caller of a single-cursor tail
would have given whichever ran first that cycle's lines and the other nothing,
intermittently and without a word.

**`ParseUserInterface.elm` is vendored six times, and the policy is all six,
identically.** Nothing in this parser is app-specific, and a change that lands
in one copy while the others silently lack it is its own bug. The one deliberate
divergence in this repo — `BotFrameworkSeparatingMemory.elm`'s
`previousStepsEffects`, mission-runner only — is documented as such below. The
consistency is *checked* rather than remembered: `test_game_log_channel.py`
compares the block byte for byte across the six copies and pins the type-name
string the host and the parser have to agree on across languages.

**Why a fork-local Elm change is acceptable here when #17 rejected one.** The
GitHub-URL source mode fetches a whole app directory, so the vendored parser and
the bot's decision logic travel together: a bot fetched from upstream has
neither the field nor anything reading it, and one fetched from this fork has
both. #17's case was the asymmetric one — the host would have answered a request
only fork-local Elm could build, so under the other source mode the host-side
machinery would exist complete and nothing would ever issue the request. There
is no such asymmetry here, and the node costs an upstream-sourced bot nothing:
having no display region, upstream's parser cannot see it either.

The native Apple Silicon client (`~/Library/Application Support/EVE
Online/SharedCache/tq/EVE.app/.../bin64/exefile`, launched from the separate
Electron launcher) is a real Metal build, not Wine — but still embeds a **Python
2** interpreter for UI and game logic (confirmed by `.so` names like
`_ctypes.so`, and later by struct RE: Python 2's `int`/`long` and `str`/`unicode`
splits are both present). Sanderling's "walk the CPython object graph" approach
applies, with offsets reverse-engineered from scratch.

## Memory access: SIP must have Debugging Restrictions disabled

`task_for_pid`/`ptrace` against a target lacking `get-task-allow` (this game
binary) is blocked by SIP's Debugging Restrictions — not bypassable via
entitlements, Developer Mode, or Developer Tools TCC. Fixed by booting into
Recovery Mode and running `csrutil enable --without debug`. Current state:
`csrutil status` → "Custom Configuration", "Debugging Restrictions: disabled",
everything else enabled. **This is a standing, system-wide reduction**, not
scoped to this project — revert with Recovery Mode and plain `csrutil enable`.

## Host permissions, and what actually blocks a launch

The full macOS permission set the tools need. All four are granted on this
machine; a failure in any one looks like a different bug, which is why they are
listed together:

| permission | granted to | what breaks without it |
|---|---|---|
| SIP Debugging Restrictions **disabled** | system-wide | `task_for_pid failed: (os/kern) failure (kr=5)` — no memory reads at all |
| Screen Recording | the terminal app you run from | window titles do not resolve; `screencapture` returns blank |
| Accessibility | the same terminal app | `cg_input` posts events that go nowhere |
| Developer Tools (TCC) | the same terminal app | contributes to `task_for_pid` failures |

These are **per-app**, so a run from iTerm2 can fail where the identical command
from Terminal.app succeeds — that exact mismatch cost a debugging session once.

**What is more often the blocker in practice is none of the above:**

- **The Mac must be unlocked.** Synthetic `CGEventPost` input cannot reach a
  locked session. The tell is that window captures still succeed but come back
  *stale* — two `screencapture -l <id>` grabs a minute apart are byte-identical
  and the launcher's own clock lags wall time. Combined with a WindowServer
  "Display Shield" window and full-screen `loginwindow` windows in
  `window_probe --all`, that is a locked screen, not a hung app. Restarting the
  launcher does not help and costs a re-authentication.
- **The target window must be frontmost before it will accept a click.** The
  first press-and-hold on the launcher did nothing but activate it. Run
  `osascript -e 'tell application "eve-online" to activate'` first, and confirm
  the gesture is on target by capturing the window and looking for the tooltip
  ("Click and hold to launch Gal Bistot") before committing to the hold.
- **`eve_read.py` needs a bot run first.** It reuses `botlab_host`'s UI-root
  cache and fails with "no usable UI-root cache" until one run has populated it,
  so it cannot be used to check the client *before* starting a bot.

Launching the client itself: press and hold the character's avatar for ~5s (see
MACOS.md — PLAY NOW ignores synthetic clicks). On this machine Gal Bistot's
avatar sits at screen point ~(489, 536) with the launcher window at
`x=0 y=39 w=1400 h=800`; re-derive it from a capture rather than trusting those
numbers, since they are per-layout.

This section covers technical prerequisites only. Whether to start a run is the
operator's call, as it always was.

## Driving a run from a Claude Code session

Claude Code is the wrapper around `cycle_run.sh` in practice: it starts the run,
watches for stalls, triages them and cycles to the next run. That works well,
but the harness imposes a few things that are not obvious and each cost real
time to discover.

**`cycle_run.sh` drives a `screen` session by stuffing keystrokes, so the target
session matters more than it looks.** `BOT_SCREEN` must never name the session
hosting the Claude Code terminal — stuffing there types the launcher into
Claude's own prompt, and `--stop` sends it Ctrl-C. `screen` reports success
either way. The default is now `evebot`, its own session, and
`refuse_if_target_is_our_own_terminal` walks this process's ancestry and refuses
if the target is in it. Note the ancestry check is the reliable test: a session
can host Claude in one window and an idle shell in another, so inspecting the
session's direct children finds the shell and misses the problem entirely.

**Start it in the background.** `start()` polls for up to five minutes waiting
for the first real decision, which overruns the default foreground tool timeout.
Use `run_in_background`, then wait on a condition rather than a fixed sleep:

```
until grep -qE '^\+ ' ~/eve-bot-logs/mission_run<N>.log; do sleep 5; done
```

**But wait on `cycle_run.sh`'s own exit, not only on that loop.** The loop above
never terminates for a run that died, which is the case `start()` now detects
for itself: a `Traceback` or an elm error report in the log fails on the next
poll, and so does a log that has stopped growing while nothing matching
`BOT_PATTERNS` is alive. Both print the last 15 log lines with the message, so
the diagnosis usually needs no second command. A non-zero exit does **not** mean
the bot is gone, though: only the "run is gone" verdict checks that nothing is
alive, while a fatal log pattern and the five-minute timeout both report failure
without looking — `elm make` can still be running under the first, and a merely
slow run under the second. So stop before trying again rather than assuming
there is nothing to stop. Cycling already does that; `start()` on its own
refuses with "refusing to start: a bot is still running".

**Arm two monitors, not one.** `stall_watch.py --keep-going` covers stalls, but
it says nothing when the bot or the client simply exits — and silence there
reads exactly like a healthy run:

```
python3 -u stall_watch.py <log> --pid <client pid> --out <dir> --keep-going
while true; do pgrep -f 'botlab_host\.py' >/dev/null || { echo "BOT GONE"; break; }; sleep 30; done
```

**Triage a stall alarm before acting on it.** Most are benign; see issue #3.
The fast check is whether the game is still moving, which takes one command:

```
NEWEST=$(ls -t ~/Documents/EVE/logs/Gamelogs/*.txt | head -1)
stat -f '%Sm' "$NEWEST"; grep -c "(combat)" "$NEWEST"; tail -2 "$NEWEST"
```

Fresh `(combat)` lines with real damage numbers mean the guns are landing and
the alarm is noise. Then apply the distance test from `/diagnose-stuck-run`:
monotonically falling is progress, flat or oscillating is not. Do not retune the
threshold to quiet the noise — it is calibrated against 55 runs.

**Reading the log by hand is free; typing is not.** The host checks system-wide
HID idle time before every input sequence, so keystrokes anywhere — including
in the attached `screen` window — trip the five-second stand-down and the bot
skips that tick's input. It resumes on its own, but continuous typing holds it
still. Scrolling costs nothing.

## CPython struct layouts (this build, arm64, Python 2 semantics)

All addresses are per-process-launch (ASLR): re-derive each session, never
hardcode. The one process-independent invariant is that **any valid
`PyTypeObject` has `ob_type` pointing at the `type` metaclass itself**
(`type(type) is type`) — `re_helper.py`'s classifier uses this to name any
pointer without per-class special-casing.

- **`PyObject` header** (stock): `ob_refcnt` `+0x00`, `ob_type` `+0x08`.
- **`PyTypeObject`** (stock): header + `ob_size` `+0x10`, `tp_name` `+0x18`
  (plain `const char*`).
- **Widget/engine-object wrapper** (the "Blue" C-extension binding layer, e.g.
  `User`, `HangarLayer`, every UI widget): 32 bytes — header + `dict_ptr`
  `+0x10` + `weakref_slot` `+0x18`. No `__dict__` in the stock sense; real state
  lives behind `dict_ptr`, which points at:
- **Custom dict** (not stock `PyDictObject`): `0x38` (56) byte header with 8
  inline entries — `refcnt` `+0x00`, `ob_type` `+0x08` (real `dict` type), two
  duplicate `Py_ssize_t`-ish fields `+0x10`/`+0x18`, capacity mask `+0x20`,
  overflow-table pointer `+0x28` (populated once entries exceed inline
  capacity), shared vtable-ish pointer `+0x30` (identical across every dict
  instance — literal ARM64 code, not data). Entries are 24 bytes
  (`hash: 8, key_ptr: 8, value_ptr: 8`), `key_ptr` always a `str`. Inline and
  overflow blocks can hold duplicate or stale copies of a key — dedupe by key
  pointer. `re_helper.py` and `tree_walker.c` both use **last-wins** for
  ordinary attributes and **first-wins** for `'children'` (preserving an old,
  never-fully-explained quirk rather than picking a new policy).
- **`PyASCIIObject`** (compact-ASCII `str`): header + `length` `+0x10` + cached
  `hash` `+0x18` + 4-byte state field + raw ASCII bytes at `+0x24`.
- **`PyIntObject`** (Python 2 `int`/`bool`): header + signed 8-byte `ob_ival` at
  `+0x10`. No arbitrary precision.
- **`PyLongObject`** (Python 2 `long`, genuinely separate from `int`): header +
  `ob_size` `+0x10` (digit count + sign) + digit array at `+0x18`, each digit
  4 bytes and `< 2^30`. Value = `sum(digit[i] * (2**30)**i)`, negated if
  `ob_size < 0`. Accumulate in ≥128-bit precision — a plain `double` loses
  precision above 2^53, which real in-game timestamps exceed.
- **`PyUnicodeObject`** (Python 2 `unicode`, separate from `str`): header +
  `length` `+0x10` + pointer to an externally-allocated **UCS-4** buffer `+0x18`
  + `hash` `+0x20`.
- **Stock `PyListObject`**: header + `ob_size` `+0x10` + `ob_item` `+0x18` (flat
  array of `ob_size` pointers) + `allocated` `+0x20`.
- **`PyWeakReference`**: header + `wr_object` `+0x10` (points back at the
  referent) + `wr_callback` `+0x18` (`NULL` in every case seen).

## UI tree walk (widget → children → JSON)

1. Widget wrapper → `dict_ptr` (`+0x10`) → custom dict → look up `'children'`.
2. That value is a `PyChildrenList` wrapper (same 32-byte shape) → its own
   `dict_ptr` → look up `'_childrenObjects'`.
3. That value is a **stock** `PyListObject` → `ob_item` array of child wrapper
   pointers → recurse from step 1.

Step 3's value is **not always a stock list on the first hop**. Some widgets
nest one children-list wrapper inside another, so `_childrenObjects` yields a
second wrapper with its own `_childrenObjects`. Confirmed live on `ButtonGroup`
(the Accept/Decline/Delay/Track row in an agent conversation). Bailing out at the
first non-`list`, which both walkers originally did, made every such subtree read
as *childless* — so the agent dialogue's buttons were invisible to the bot while
plainly rendered on screen. A silent wrong answer, not an error.
`tree_walker.c`'s `get_children_addrs` now unwraps repeatedly (bounded by
`MAX_CHILDREN_UNWRAP`) until it reaches a stock list. `re_helper.py`'s
`get_children_addrs_from_wrapper` still has the old single-hop behaviour; fix it
there too if a Python-path walk ever needs these subtrees.

**The walk is syscall-bound, not decode-bound.** Nearly every read is an 8-byte
pointer field, and uncached each one is its own `mach_vm_read_overwrite` — which
measured ~0.5ms per node, linear in node count, putting a real in-mission read at
1.78s and a 7,000-node docked tree at 3.4s. An object's header, its dict and that
dict's entries all sit within a page or two of each other, so `read_mem` now
serves from a direct-mapped 4K page cache: 3.36s → 0.39s on the same tree, 4x
in-host end to end. Two constraints hold it together. The cache is scoped to a
single request (bumped via `g_page_epoch`, so invalidation costs nothing) because
holding pages across reads would hand the bot a tree blended from moments seconds
apart — within one walk it is instead a consistency *gain*, since the uncached
walk already samples a live tree over several seconds. And a page that cannot be
read whole is not an unreadable field: the last page of a mapped region fails as
a page while the bytes asked for are fine, so that case falls back to a direct
read rather than reporting failure. Verified against the pre-cache binary on a
live client: same node count, 2,743 identical strings, and the only differences
were values that genuinely change between reads (distances, speed, a countdown).

Dead end, don't retry: `PyChildrenList+0x20`/`+0x28` look like a linked list but
are CPython's own GC-tracked-object list — every GC object is threaded into one
process-wide cycle-detection list, unrelated to content.

**Root discovery** (`re_helper.find_ui_root`): regex-scan a full memory dump for
EVE's own debug-log repr text, `<ClassName object at 0X[hex]>` — a scannable ring
buffer, so `re.finditer` straight against the `mmap` with no need to load the
file. That text embeds live object addresses, sidestepping any pattern scan.
Then walk `_parentRef` (a weakref to the parent) upward via `wr_object` until an
object has no `_parentRef` — that is `UIRoot`/`'Desktop'`. Two guards:
`_parentRef` can be present but hold the actual `None` singleton (some containers
sit directly under root), so check the value is genuinely weakref-typed before
dereferencing `+0x10` or you silently walk into garbage; and try several seeds,
preferring one whose own class is literally `UIRoot` or taking whichever address
most seeds converge on, since a single seed can be a dead-end subtree such as a
popped-out window.

**Seed/metatype bootstrap gotcha, hit in three separate tools:** don't trust the
*first* repr-scan hit to derive the metatype pointer. The debug-log text can name
an object since destroyed or reallocated — UI widgets churn constantly — so
`find_metatype` on a stale address returns garbage or `None` even when the same
dump holds plenty of valid candidates. Scan up to ~200 hits and validate each
against the `type(type) is type` invariant. Already fixed in `botlab_host.py`'s
`_any_seed_addr`, `reload_drones.py`, and `route_setter.py`'s
`find_valid_seed_addr`; reuse that pattern rather than reintroducing the
shortcut.

Two more real bugs from early runs, worth recognising if the symptoms recur.
The custom dict's `str`-type bootstrap cannot blindly read a fixed inline slot —
it is a sparse hash table and slot 0 is often empty, so walk entries to find any
real key. And the host's main loop must not process only the *first* task in a
response's `startTasks`: a real cycle offers several at once (memory read plus
screenshot read), and later responses offer genuinely new tasks such as the
`SearchUIRootAddress` → `ReadFromWindow` transition. Drain a queue keyed by
`taskId`, extended from every response, until empty.

## Skills (`.claude/skills/`)

Slash commands wrapping the workflows that recur here. They carry the
procedure and its traps; this file carries the facts.

| skill | use it when |
|---|---|
| `/diagnose-stuck-run` | a run may be looping — find out, and find the branch |
| `/check-ui-parse` | the bot seems blind to something on screen, or a guard's premise needs checking against the live client |
| `/bot-run` | start, stop, cycle or stall-watch a run |
| `/review-silent-success` | reviewing changes for the failure mode that reports success and does nothing |

## Tools (`tools/macos-host/`)

| path | purpose |
|---|---|
| `probe/` | minimal `task_for_pid` feasibility check |
| `memory_sample/` + `save_process_sample.sh` | full process memory dump + `regions.tsv` index + correlated screenshot, for one-off RE |
| `re_helper/re_helper.py` | Python RE tool and library — `dump`/`find`/`walkdict`/`tree` CLI, plus reusable decoders (`read_pystr`, `read_pyint`, `read_pylong`, `read_pyunicode`, `read_pyfloat`, `classify`, `get_dict`, `walk_dict_entries`, `dict_items`, `build_tree`, `repr_scan`, `find_metatype`, `walk_to_root`, `find_ui_root`). Works against a dump (`Sample`) or a live process (`LiveSample`) interchangeably. |
| `live_reader/` | persistent live memory-read helper (binary protocol over stdin/stdout), backs `LiveSample` |
| `tree_walker/` | C rewrite of the whole UI-tree-walk hot path — memory read, struct decode and tree assembly in one attached process, no per-field pipe protocol. ~5x faster than the Python path (~0.4s vs ~2s for a ~2,800-node tree); what `botlab_host.py` uses for `ReadFromWindow`. Reads go through a per-request page cache — see below |
| `window_probe/` | window enumeration via `CGWindowList` (bounds in points, backing scale); `--all` sees windows on any macOS Space, not just the active one |
| `cg_input/` | persistent `CGEventPost` input executor, one text command per stdin line (`move`/`down`/`up`/`drag`/`doubleclick`/`keydown`/`keyup`/`scroll`) |
| `botlab_host/botlab_host.py` | the BotLab.exe replacement — fetches bot source (GitHub URL or local path), patches `elm-version`, compiles with `Main.elm`, drives the compiled bot via `driver.js`, dispatches every `Task` type |
| `botlab_host/Main.elm`, `Main_2023_02_06.elm`, `driver.js` | port wrappers (one per host interface, picked from the bot's own import) + Node bridge (newline-delimited JSON) between the Python host and the compiled bot |
| `run_saxrat.sh`, `run_mission.sh` | launchers for `eve-online-saxrat` / `eve-online-mission-runner`; one-bot-at-a-time guard kills any prior launcher/`botlab_host.py`/`driver.js`/`tree_walker` first |
| `bot_help.py` | backs `--help` on the launchers |
| `stall_watch.py` | watches a running bot's log and screenshots the client when it stalls |
| `web_console.py` + `web_console.html` | tailnet-only status/log/settings console for a running session (`--web-console`) |
| `eve_read.py` | live reads of the client (overview, targets, modules, combat feed, window id, client pid) by reusing botlab_host's UI-root cache -- ~2s instead of rediscovering the root |
| `eve_repl.py` | interactive handle on the client for one-offs -- `python3 -i eve_repl.py`, then `eve.dock(...)`, `eve.warp_to(...)`, `eve.menu_click(...)`. See `REPL.md` |
| `compile_bot.sh` | compiles a bot the way the host does, without running it; verifies the scratch copy matches the source |
| `cycle_run.sh` | stops the running bot (escalating past a Ctrl-C that does not land) and starts the next run in the screen session, waiting for its first decision and failing fast with the log's tail if the run died instead |
| `reload_drones.py` | standalone one-off: refill drone bay from station hangar. Still the way to restock *outside* a session; the mission runner now does the same thing for itself while winding down |
| `route_setter/route_setter.py` | standalone one-off: set the autopilot route from a chat channel's MOTD |
| `esi_waypoint.py` | set the client's autopilot destination through ESI, the official API. A CLI (`auth`/`resolve`/`set`) and an importable module -- `botlab_host.py` calls `set_destination` in-process for `SetAutopilotDestinationRequest`, so failures arrive as `EsiError` values rather than exit codes with a reason on stdout |

**Launcher `--help`** is answered *before* the one-bot-at-a-time guard runs, so
asking what the settings are never kills a session in progress. `bot_help.py`
restates nothing: settings come from the bot's own `Bot.elm` — its
`## Configuration Settings` header section, plus every key `parseBotSettings`
accepts, reported separately where the header omits one — and flags from
`botlab_host.py --help`. A bot gaining a setting shows up with no launcher edit.

**`stall_watch.py`** takes a log path, `--pid` of the client and `--out` for
screenshots, and exits on the first stall so a caller can act on it:

```
python3 stall_watch.py <log> --pid <game pid> --out <dir>
```

A stall is either the bot saying *"I am stuck here and need help to continue."*
(`askForHelpToGetUnstuck`, never normal), or the decision tree going in circles
for `CIRCLING_THRESHOLD` **readings** while EVE's own game log stays silent. It
screenshots the game **window by id** (`screencapture -x -o -l`), not the screen,
because the client is usually on another macOS Space where a screen grab catches
the wrong desktop.

**The unit is the reading, not the decision line**, and this is the single
easiest thing to get wrong here. The bot re-derives its whole decision path on
every framework event, so one look at the game emits about a dozen decision
lines — 33,678 across 2,849 readings on the run this was calibrated against, at
4.7 decisions a second. A threshold of 40 *decisions* was therefore 3.4 readings,
or **8.5 seconds** of wall clock, and combat legitimately pauses far longer than
that while switching targets, between pockets, or in warp. Replaying that run
with the game log pinned silent, the old unit raised 295 alarms — one every 5.3
seconds — against 10 for the same run counted in readings, all 10 being one
pattern that dedupes to a single screenshot.

This is CLAUDE.md's own *"a decision in the log is not an action"* biting a tool
that had carefully calibrated a threshold against the wrong statistic — for the
second time, the first being the consecutive-identical counter the circling test
replaced. `stall_watch.py` reflects the unit in its structure: `observe` folds a
decision into the reading being assembled and reports nothing, and `end_reading`
judges the reading once, at the `# [tick.substep]` boundary where the tick moves.

`--keep-going` keeps watching after a stall instead of exiting, and is now safe
to leave on. Each distinct stall is screenshotted **once** — distinctness judged
on the reason with its numbers masked, since the quoted loop carries drifting
distances and tick counts — and `--max-shots` (default 20) caps the run
regardless. Without that dedupe it reported on a metronome: a shot per 40 stuck
decisions, and the worst pathology on record repeated one decision 8,983 times,
which is ~225 near-identical Retina grabs of a frozen screen at ~7.5 MB each,
or the 1.7 GB that actually accumulated.

The universal leaf `Wait for progress in game` is **passed over** when judging
whether a window of decisions is benign idling. Every benign state reaches that
leaf, so a window holding "I am in warp" and its leaf could never be all-benign,
and run 114 raised an alarm for a bot correctly sitting out a warp. It is still
never benign on its own — a window of nothing but leaves says nothing about
*why* the bot is waiting, and treating it as idle is what once dropped detection
to nothing.

**A falling distance counts as progress**, alongside a growing game log and a
changed decision. A long approach holds both of the original stall conditions
while the ship flies perfectly: the decision quantises distance to the nearest
1000 m at range, so one line repeats for a whole plateau, and EVE's game log
remarks on the approach only every 20-100 seconds. The bot already prints the
number, so the watcher parses the trailing `<N> m away` out of the decision and
treats a new smallest value as the ship working.

Judged against the **smallest** distance seen for that wording, not the previous
one, which is what keeps the documented "target drifting while the ship does
nothing" case alarming — an oscillating distance sets a new minimum once and
never again. A wording is forgotten once it leaves the decision window, so a
second container behind the same sentence is measured on its own rather than
against the first one's arrival distance. `APPROACH_PATIENCE` (20 readings, the
same unit as the threshold) bounds it in both directions: a ship gets that long
from first sighting, or from its last gain, to show it is closing, and a ship
that has genuinely stopped is caught that much later than before rather than not
at all. The measured worst case inside a real approach was 22 decisions between
two strict decreases — about two readings — so the headroom is an order of
magnitude.

Raising `CIRCLING_THRESHOLD` instead would have been the wrong fix — it is
calibrated to catch an 8,983-repeat pathology, and the problem was the progress
signal, not the sensitivity.

**`--web-console [PORT]`** (default 8787, off unless asked for) serves a live
console: session stats, the log as a filterable stream, an editable settings
box, and pause/resume/stop. `./run_mission.sh --web-console` works as-is, since
the launcher already forwards `"$@"`.

It binds to this machine's **Tailscale address and nothing else**, and **fails
to start** if no 100.64.0.0/10 address can be found rather than falling back to
a wider interface — the console can change what the bot does and stop it, so
guessing wrong means publishing a remote control. Tailscale is the
authentication; there is no login of its own, which is exactly why the bind must
stay narrow.

Two design points that are load-bearing rather than stylistic. **HTTP handlers
never touch the pipe to the bot process** — it is a strict request/response
conversation with the Elm runtime, and a second writer desynchronises it — so
handlers only queue intent and `run_bot`'s own loop performs it between ticks.
And **live settings reload needs no new bot machinery**: re-sending
`BotSettingsChangedEvent`, the same event the session opens with, makes the bot
re-read its whole settings string.

Stats come from EVE's game log, which the host already tails: a `(bounty) N ISK
added to next bounty payout` line is emitted once per rat killed and carries
what it paid, so kills and ISK are a count and a sum of those. The `(combat)`
lines are per shot, not per kill, and are no use for a kill count. Those two
channels are the ones deliberately withheld from the bot's own view of this log
(see the Architecture section), so this stays the only reader of them.

**Applying settings live** is the console's most useful trick and needs no
restart. `GET /api/state` returns the current settings string; `POST
/api/settings` with `{"settings": "<the whole string>"}` queues a replacement,
and the loop applies it on its next tick via `BotSettingsChangedEvent` — the
same event the session opens with, so the bot re-reads *everything* and no code
in `Bot.elm` need know the console exists. Send the complete string, not a
patch. The host logs `applying settings change from the console` when it lands.

Proven live on run 129: a bot raising the not-progressing alarm beside an
unreachable objective started acting on a newly added `approach-object` within
one tick, saving a session that was otherwise going to be restarted. It is also
the fastest way to *test* a settings guess — a wrong one is one POST away from
being undone, where a restart costs the whole session's progress.

**Bot source acquisition** (both tested): a local file or directory path (or
`file://`), or a GitHub URL — a plain repo, or a `.../tree/<branch>/<subpath>`
URL, needed since apps in *this* repo live under `implement/applications/...`
rather than the repo root, cloned with `git clone --depth 1 --branch <branch>`.
Both then search recursively for `Bot.elm`.

**Important:** `route_setter.py` and `reload_drones.py` drive real input directly
and are **not** part of the bot loop. Never run them alongside a launcher session
— both fight for the same mouse and keyboard, and a stray background run once
caused a long, confusing debugging detour. Check with `pgrep -f` on the same
patterns the launchers' guard uses before starting either.

**The bot does yield to a human, though.** Before executing any input sequence
the host checks how long ago a *person* last touched the mouse or keyboard, and
if that was under `HUMAN_INPUT_STAND_DOWN_SECONDS` (5.0) it skips the sequence
and says `standing down: someone used the mouse/keyboard Ns ago`. Nothing needs
unwinding: the bot re-derives its decision from a fresh reading every step, so a
skipped sequence costs one tick and is simply decided again once the machine is
quiet. It resumes on its own five seconds after the last human input, with
nothing to switch back on.

So taking the mouse mid-run is safe and does not require stopping the bot —
which is what makes reading the client by hand during a session practical. It is
*not* a licence to run the input-driving tools alongside it: those keep clicking
regardless, and each of their clicks also resets the bot's five-second timer, so
the two simply take turns badly. Read-only tools (`eve_read.py`, and
`eve_repl.py` as long as you only call its reading methods) touch no input at
all and are always safe.

**Never print the client's command line.** The launcher starts the game with the
account's `/ssoToken=` and `/refreshToken=` as arguments, so `ps aux | grep EVE`,
`pgrep -fl`, or `ps -o command=` dumps live credentials into whatever reads that
output — a terminal, a run log, a transcript pasted somewhere else. The
`ssoToken` expires in ten minutes but the `refreshToken` does not. Ask
`python3 eve_read.py pid` (or `eve_read.client_pid()`), which resolves the pid
from `lsappinfo`'s bundle id and never touches an argument vector. `pgrep -f`
without `-l` is also fine — it matches the command line without printing it,
which is what the launchers' own guard does.

## Coordinates and input execution

The game's internal UI coordinates (`_displayX`/`_displayY`) are laid out against
`UIRoot`'s own reported virtual-canvas size (`_displayWidth`/`_displayHeight`),
**not** a fixed Retina backing scale. Self-calibrate
`scale_x`/`scale_y = UIRoot's reported size / real window point size` (from
`window_probe`) every session; don't assume 2.0. `cg_input` wants real screen
points — confirmed by a `CGEventGetLocation` round-trip, where commanding a move
to `(10,10)` reads back exactly `(10.0, 10.0)`. The scale mismatch is entirely in
what the *bot* computes upstream, which is why the fix lives in
`ReadFromWindowMethod`'s reported rect and `_windows_input`'s outbound
conversion, not in `cg_input`. Windows virtual-key codes
(`Common/EffectOnWindow.elm`'s `vkey_*`) need an explicit lookup table to macOS
`CGKeyCode`s (`_VK_TO_CGKEYCODE` in `botlab_host.py`) — neither side is
contiguous for letters or digits, so no arithmetic mapping works.

**Input effects the bot can express.** `Common.EffectOnWindow` defines the
vocabulary; `EveOnline.BotFramework` maps it onto the host-interface items;
`botlab_host.py` and `cg_input` execute it. Three gestures need more than the
obvious:

- **Double click** is not two clicks. macOS only treats the second press as a
  double click if it carries `kCGMouseEventClickState = 2`, which is why
  `cg_input` has a dedicated `doubleclick` command. The bot emits two
  press/release pairs with nothing between them, and `botlab_host.py` collapses
  that shape into the one command. EVE reads a double click as "Open Cargo", and
  from outside looting range answers by flying there and opening on arrival — so
  it replaces a whole right-click cascade *and* the separate approach.
- **Drags must not pause after the press.** The framework interleaves a
  `WaitMilliseconds` between every pair of effects, and EVE reads a press
  followed by a pause as a click, with the later motion as the cursor wandering
  off. `botlab_host.py` skips those waits while a button is held, except the one
  before the release, which the drop still needs.
- **Scrolling** goes wherever the cursor is, so `effectsMouseScrollAtLocation`
  carries the move with it.

**Mouse movement.** Glide through intermediate points rather than teleport
(`_move_mouse_eased`) — Photon UI cares about real trajectories, not just final
position, for more than one kind of gesture. But **don't re-issue an identical
move**: a hover-triggered flyout needs sustained, uninterrupted dwell, and
re-gliding to the same spot every tick resets that timer before it accumulates,
producing an endless open/close flap that looks like hard failure.

**In-game hotkeys, preferred over a cascade wherever one exists** (this account's
bindings): `Shift+F` launches drones, `F` engages the current target, `Shift+R`
recalls, `Alt+F1` toggles the propulsion module, `F1`–`F4` are weapon slots 1-4,
`Ctrl+W` closes the active window — all confirmed live. `Alt+C` for the inventory
is EVE's default and is used by the courier-pickup path, but has not yet fired in
a real run.
A keypress is one effect where a cascade is a multi-tick right-click → hover →
click with its own retry logic. Note `Alt+F1` is a *toggle*, not a "deactivate" —
press it only when the module reads active.

**Window resolution must pick the largest window by area** for a pid, not the
first over a width threshold: a fullscreen game window has a smaller same-width
overlay (the reveal-on-hover menu-bar strip, ~1710×44) that a naive check picks
by accident, giving a badly wrong y-scale and bogus click targets. `window_probe
--all` (`kCGWindowListOptionAll`) makes this work regardless of which Space the
game is on — the on-screen-only query sees nothing when that Space is inactive.

**`cg_input` must stay one persistent process** across a whole move→down→up
sequence: it tracks click position as process-local state set by the last `move`,
so a fresh process per command always clicks at `(0, 0)`, which looks exactly
like the cursor teleporting to the top-left corner.

**`BringWindowToForeground`** should check `_window_is_onscreen()` first and skip
the activate-and-sleep when already there — `BotFramework.elm` prepends it to
*every* input sequence, so the common case is "already frontmost", and paying an
unconditional `osascript` plus sleep was the real source of felt sluggishness.
Equally, don't re-verify the window before every individual action in a sequence;
that cannot change between two `CGEventPost` calls milliseconds apart. Check only
at the sequence's own `BringWindowToForeground`/`AbortIfWindowNotInForeground`
checkpoints.

## A mission must be *tracked* or the mission runner cannot leave the station

`eve-online-mission-runner` navigates entirely from the mission tracker's own
travel button in the info panel — Undock, Set Destination, Warp to Location,
Dock. That entry (`AgentMissionInfoPanelEntry`, under `InfoPanelJobBoard`)
exists only for a mission that is **tracked**. Accepting one does not track it.

Untracked, the panel entry is absent, and the failure is a loop rather than an
error: the bot sees no mission, asks the agent for one, the agent offers
"Complete Mission" because a mission *is* in progress, `Bot.elm` reads that as
"still in progress — go fly it" and closes the conversation, and the next
reading starts over. Run 103 did that for 47 ticks — 87 conversation opens, 79
closes, 221 "assume we are docked", never undocked, and `askForHelpToGetUnstuck`
never fired because every individual branch believed it was making progress.

To track: **Opportunities (Alt-J) → Active tab → right-click the mission card →
"Track"**. The right-click menu is the only place it lives; the card's own
controls and the Agency window do not offer it, and neither does the Journal.
Confirm it took by checking the info panel gained a fourth
`ButtonIconInfoPanel` toggle and an `AgentMissionInfoPanelEntry` carrying the
objective text.

This is per character, and it is why the bot ran for weeks on one character and
failed instantly on another: missions tracked earlier stay tracked, a fresh
character's do not. Suspect it whenever a docked bot talks to an agent in a
loop.

**Only the first mission on a character needs this.** Tracking is inherited:
run 106 handed in Minmatar Plot (1 of 3), took (2 of 3), and the new mission
appeared in the info panel by itself with no intervention. So it is a one-time
setup step per character, not something to repeat each mission.

## Reading the overview

The overview **virtualises**: every object in space has an entry in the UI tree,
but only the rows that fit are rendered, and the rest keep whatever position they
last held while recycled. A hidden entry therefore reports a plausible region
pointing at a row that now belongs to something else, so clicking it is worse
than a no-op — it acts on the wrong object. `_display` is what distinguishes
them; the region does not. Filter on it before locking, looting or activating
anything.

To reach a row that is off screen, turn the mouse wheel over the overview a notch
at a time and re-read between notches. Do **not** compute a scrollbar position
from the target's rank by distance: that assumes the list is distance-sorted and
every row is a distinct live object, and neither holds. It failed silently in
practice — the arithmetic clamped to the top of the track, where the handle
already was, so a zero-length drag emitted no movement at all while the log
happily reported a scroll every tick.

Distances only parse as `m` and `km`. An **AU** distance is an `Err`, which every
consumer turned into a `999999` placeholder that reads as merely far rather than
unreachable — one run logged "Failed to read the distance" 444 times. Exclude
those objects from anything the ship might act on.

## Context-menu cascade robustness

`EveOnline.BotFrameworkSeparatingMemory.elm`'s shared cascade logic
(`useContextMenuCascadeWithCustomConfig`) discards and reopens a menu that looks
unchanged across a lookback window — currently 8 readings, widened from 3 then 4
each time real cascades were found giving up too early on a slow Photon UI
flyout. `discardContextMenuIfTooDistantFromTargetElement`'s distance tolerance is
per-cascade-tunable; the shared 70px default is not enough for every element, and
both the route-jump icon and the locked-target-bar unlock icon needed 200px.

`beginCascade`'s fallback for "target fully occluded by an existing menu" presses
**Escape** rather than right-clicking a computed "empty space" location — that
location is not reliably empty, can land on a real Neocom icon, and whatever it
opens then sits in the way of the next click. Confirmed live: this caused an
accidental "Clear All Waypoints" on a real route.

`clearStrayContextMenu` presses Escape if a menu has sat at the same depth,
byte-for-byte unchanged, for 3+ ticks — catching a stray menu on a tick where the
decision tree isn't touching menu logic at all, which the cascade's own recovery
cannot do since it only runs while actively driving a cascade.

## Ship modules

Module buttons come in rows, and the row list is **not a stable index space**:
the parser drops any node whose display region it cannot read, so a slot can
leave and rejoin while nothing moves on screen. Identify a module by position —
sort the row by `x` — not by index. Indexing clicked a neighbouring module live.

`isActive` reads `ramp_active` off the button, and on this client that entry does
not exist until the module has run: the `ShipModuleButtonRamps` widget holding it
is created when the module starts cycling and destroyed when it stops. So a
module reads `Nothing` when off-and-never-run, `Just True` when running, and
`Just False` only when off after having run. Treat `Nothing` as off. `isBusy` and
`isHiliteVisible` are permanently `False` here — their sprites don't exist in
this build — so they are no use as a second opinion.

A module button is a **toggle**, so a click repeated before the client has shown
its result switches the module back off. `moduleButtonClickSettlingSteps` gives a
click 5 steps to appear in a reading first.

**Module tooltips cannot be read the framework's way here.**
`getModuleButtonTooltipFromModuleButton` looks up a dictionary that
`integrateCurrentReadingsIntoShipModulesMemory` only ever writes to when some
module button reports `isHiliteVisible` — and that is the same missing "hilite"
sprite as above, so on this client the dictionary stays empty however long the
mouse rests on a module. `readShipUIModuleButtonTooltipWhereNotYetInMemory`, the
framework's own acquisition step, would therefore hover forever and store
nothing; the mission runner does not call it, and should not start.

The way through is to skip the client's attribution entirely: the bot knows
which button it hovered, because it decided to. `weaponOptimalRangeFromHover` in
`eve-online-mission-runner/Bot.elm` reads `readingFromGameClient
.moduleButtonTooltip` straight out of the reading and attributes it to the module
the previous step's effects moved the mouse onto. **Whether hovering raises a
`ModuleButtonTooltip` at all on this client is still unverified** — nothing had
ever hovered a module here before — which is why the ammo swap that depends on it
gives up and says so after a few readings rather than waiting.

## Lock range is learned from the client, not set

`targeting-range` (default 66000) decides whether `lockTargetFromOverviewEntry`
locks a target or approaches it. It is a guess about the ship, and wrong in
either direction costs: too low and the bot flies at rats it could have shot,
too high and it spends readings asking for locks the client will never grant.
The client answers that question every time it accepts or refuses a lock, so
the number is now derived the way the UI scale is — per session, from what the
client actually did — rather than asserted.

Two bounds in `BotMemory`, each moving one way only, so no oscillation is
possible: **`lockProvenAtMeters`** is the greatest distance at which a lock was
accepted and only rises, **`lockRefusedAtMeters`** the smallest at which one
provably failed and only falls. The threshold is the setting clamped into
`[proven, refused)`. With no evidence both are `Nothing` and the threshold is
exactly the setting, so a run where nothing is learned behaves exactly as
before. Where the two contradict each other, proven wins — a lock that
completed is unambiguous, a refusal is an inference.

**A refusal only counts on disambiguated evidence**, which is the whole
difficulty. A lock can fail because the target is out of range, because the
ship is at maximum locked targets, because the target died, or because the
click hit a recycled overview row. So it takes all of: the attempt has had
`lockAttemptReadingsBeforeVerdict` (8) readings to land; the row is still in
the overview and still `_display`ed; it still does not read targeted or
targeting; and **the target bar was empty at both ends of the attempt**. That
last one is what separates "too far" from "no free slot" — an empty bar is the
only thing a reading can say that proves a slot was free, since the client's
maximum is not in the reading at all. Without it the number ratchets down every
time the ship simply fills up. The price is that only the first lock of an
engagement can teach a refusal, which is also the case that costs the most.

**The attempt is read out of the effects, not the decision.**
`updateMemoryForNewReadingFromGame` is the only place that can write memory and
it never sees the decision, so `lockClickLocationFromStepEffects` recognises
the lock chord in the previous step's effects — Ctrl held over a left click,
the only place in this bot that presses Ctrl without Shift — and takes the
`MouseMoveTo` that travels with it. The row is then resolved by screen position
against the *following* reading, which is the right way round rather than a
compromise: the client acted on whatever was rendered at that point. Across
readings the row is tracked by `objectItemID`, falling back to the name only
when no other row shares it; a pocket of five identically-named rats with no
item id therefore teaches nothing, which is the correct answer rather than a
guess.

**Every bound move is logged once**, as a `Learned lock range:` line wrapped
around the whole decision at `missionBotDecisionRoot`. It is emitted there
rather than in the branch that learned it because the bounds move in the memory
update, which runs whatever the bot is doing. Once-per-change needs no "already
reported" flag: the bounds are monotone, so a repeated verdict moves nothing
and says nothing. The status line carries the current bounds and the pending
attempt continuously.

The bounds are **not reset within a session**. Resetting at each dock — the
other obvious choice — would throw the learning away at the end of every
mission, which is most of what there is to keep, and this bot does not swap
ships on its own. A consequence worth knowing: the setting cannot raise the
threshold back above a learned refusal, so a bound learned wrongly is sticky
until the session restarts.

Fixing this also had to bound `lockTargetFromOverviewEntry`'s
`"Locking target is in progress, wait for completion."`, which had no bound at
all — the same unbounded-wait shape as the drone recall below. Note that
neither caller can currently reach it, since `overviewEntriesToLock` filters
targeted and targeting rows out of its candidates; the reachable unbounded
shape was the *click* repeating every reading, and that is what the learned
bound ends.

## Ammo: the weapon's optimal range is what says which charge is loaded

`eve-online-mission-runner` swaps between two charges as the current target's
distance changes, and the whole design hangs on `ModuleButtonTooltipMemory
.optimalRange`: a weapon's optimal range moves with the charge in it, so one
number says which ammo is effectively loaded *and* confirms that a load landed.
Without it a reload would be the repo's signature bug — an action that reports
success and changes nothing.

It is **off unless both `short-range-ammo` and `long-range-ammo` are set**, and
the names must match the weapon's own right-click menu. Discovering the pair from
that menu instead of being told it would be better and is not implemented:
nothing has yet observed what a module's context menu contains on this client.
One charge type, or none, means there is no swap to make, and doing nothing is
the correct outcome — wrong ammo still does damage.

Not oscillating is the actual work, and each guard answers a specific way this
goes wrong:

- **Two thresholds, not one**, and the gap between them is not a matter of taste.
  Swapping moves the optimal range itself, so a deadband narrower than half the
  distance between the two charges' optimal ranges lets each swap re-arm the
  opposite one. The two ranges are *learned* — the first swap reveals the second
  number — and `ammoSwapDeadbandMeters` derives half the spread from them once
  both are known.
- **AU distances are excluded, not treated as very far.** An unparsed distance
  becoming the 999999 placeholder is exactly the input that would argue for
  long-range ammo forever.
- **Several consecutive readings** must agree before acting
  (`ammoSwapDistanceHoldTicks`), because rats die and the "current target" jumps
  between ranges without the fight changing.
- **A turning ramp only blocks a reload when the bot just asked for one**
  (`ammoReloadSettlingTicks`). `rampRotationMilli /= 0` is the client saying the
  module is mid-cycle, but a weapon that is *shooting* is mid-cycle almost all
  the time, so refusing to touch a turning ramp would mean never swapping during
  a fight at all.
- **Bounded, then quiet** (`ammoSwapNotConfirmedGiveUpTicks`), the way
  `maneuverNotConfirmedGiveUpTicks` bounds orbit and keep-at-range. The give-up
  is not silent: the branch names itself in the decision log on every reading it
  declines — the shape `returnDronesToBay` was changed to after #7 — and the
  status line carries the reason for the rest of the session.

**None of this has run against a live client.** The first run to use it should
be watched for the optimal range in the status line actually changing after a
swap, not for the decision log claiming one.

One cross-feature invariant, since both this and the learned lock range read the
previous step's effects. They cannot be confused for each other — the lock chord
is Ctrl over a *left* click, the ammo cascade a plain right click, and the
tooltip hover a bare mouse move with no button at all. And the hover, which holds
the mouse still for several readings, cannot age a pending lock attempt into a
false refusal: a refusal needs the target bar empty at both ends, and the ammo
path only runs with an active target.

## Drones: how long they have been out says nothing about a recall

Warping with drones in space loses them, so every warp, dock and retreat in
`eve-online-mission-runner` goes through `returnDronesToBay` first. Shift+R is a
bare keypress with nothing to aim at and no acknowledgement in the reading, so
the only evidence a recall landed is the in-space count falling — which means
the bot has to bound how long it keeps asking, and that bound is where this went
wrong.

**Time since launch is not evidence about a recall.** The give-up was originally
gated on `dronesInSpaceTicks`, which counts readings since the drones were
*launched* — and drones are deliberately left out for a whole fight. Any pocket
lasting more than 60 readings pushed the counter past the threshold, after which
`returnDronesToBay` declined for the rest of the session and every subsequent
warp abandoned whatever was in space. Run 1 lost all ten drones this way in two
batches of five: 91 readings between the second launch and the next warp, no
recall decision among them. `droneRecallUnansweredTicks` counts from the first
recall the client did not answer instead, and resets whenever the in-space count
falls, since a partial recall is the client answering.

**It was silent because the explanation was on an equality test.** The branch
that said "give up on them" fired only on the reading where the counter was
*exactly* 60, and `returnDronesToBay` is only called from the warp and travel
paths — so if the ship was mid-fight on that one reading, nothing was ever
logged and the `>` branch then declined forever without a word. A branch that
declines has to say so every time it declines. `returnDronesToBay` now takes the
caller's next step rather than returning a `Maybe`, so the give-up can name
itself in the decision log while handing the step on.

Two consequences worth knowing. The give-up **latches** once reached, because
giving up is what stops the asking — without the latch the counter resets two
readings later and the ship alternates forever between abandoning its drones and
recalling them. And measuring "how long ago did the bot *ask*" needs the
previous steps' effects, which `UpdateMemoryContext` did not carry; the mission
runner's copy of `BotFrameworkSeparatingMemory.elm` now passes
`previousStepsEffects` through, so that file diverges from the other apps'
copies.

## The home station: restocking where the drones actually are

The drone restock takes drones from whatever station the ship is docked at, and
that station is chosen by the mission chain, not by anyone who knows what is in
it. Observed directly: after run 1 the ship sat in Amarr VI (Zorast); the
station it was flown to for the restock, Amarr VIII (Oris) - Emperor Family
Academy, holds 13 item types — all fitting modules and Overseer's Effects, no
drones of any kind. There was nothing to restock from, and the log would have
said "this station's item hangar holds no 'Acolyte I'" for the rest of the
window.

`home-station` names the station that does have them. When the wind-down starts
and the drone bay is empty, the mission runner sets a route there, flies it,
docks and restocks; already docked there, it restocks without travelling. It
also gives the session a predictable end point, which a run that stops wherever
the last mission left it does not have.

**The name is one setting and is never typed.** `home-station` takes the full
name as the client writes it, parentheses and hyphens included, because the full
name is needed twice regardless — to pick the right row out of 26 search results,
and to tell "am I already home" from the info panel's own station name. What
gets *typed* is derived from it by `searchQueryForStation`: the tail after the
last `" - "`, which for an NPC station is the distinctive part and is free of
the punctuation that cannot be pressed. A second setting carrying the search
term was the obvious alternative and is worse — the two can silently disagree,
and a term that does not occur in the full name searches forever and matches no
row, which is this repo's signature failure rather than an error.

**The trigger cannot read the drone bay where it is asked.** The wind-down
decision happens while docked, and the drones window is not in the tree while
docked, so a live read of it answers "not empty" for an empty bay — a guard that
compiles, runs, and is false in the only state that matters, which is what
issue #15 was. `droneBayEmptyLastSeen` in `BotMemory` is written **only** from
readings that can see the bay at all, so it is the last real answer rather than
an inference: in space the drones window is open (the bot's own setup
instructions require it), so a run that loses its drones records `Just True` on
the next reading and carries it through the dock. `Nothing` — no reading this
session ever saw the bay — declines the trip rather than guessing.

**Two instruments, and they are not redundant.** #15's fix reads the bay's
capacity gauge out of an inventory window, which is the docked instrument and
the right one for the restock. It cannot answer this question, because it is
only readable once the bot has itself opened the bay from the ship's card —
and the home trip needs its answer *before* undocking, to decide whether to
leave at all. `droneBayFillWhileSelected` is therefore the docked view and
`droneBayIsEmptyFromDronesWindow` the in-space one, and they never overlap: the
drones window is absent while docked, and the inventory does not have the bay
selected while in space.

**The trip triggers on *empty*; the restock, once there, tops up anything not
full.** These disagree on purpose, and in two independent ways.

The reading forces it. The drones window titles the bay group with a bare
count — the `(current/maximum)` form the parser can read is what the *in space*
group carries, being bandwidth-limited — so there is no capacity to compare
against and "nothing in the bay" is the strongest thing an in-space reading can
say.

The cost argues for it too, and would even if the maximum were readable. The
restock tops up 9 drones of 10 because it is standing in the station and the
cost of acting is one drag. The trip decides whether to abandon the wind-down,
undock, fly several jumps and risk ending the session in space; 9 of 10 does not
justify that and 0 of 10 does. The asymmetry is in the cost of the action, not
in the reading of the bay. A ship that arrives home with a part-full bay is
still topped up, because the restock applies its own condition on arrival.

The trip additionally respects `droneBayWillTakeNoMore`, the restock's latched
verdict: a bay whose gauge already read full, or a drop the client already
refused, is not a reason to fly anywhere. It resets on undock, so it never
suppresses a trip decided in space.

**Route first, undock second.** Setting a destination is the step that can fail,
and failing it while still docked costs nothing; failing it after undocking
leaves the ship in space with the session ending. The search bar works from
inside a station, so there is nothing to gain from the other order.

**Whether the route is *ours* is not readable from the route panel.** It reports
that a destination exists, never which one, so a leftover mission route would be
followed to the wrong station with every log line reading like success. The
evidence used instead is the `Station: Information` window for the home station
— the window `routeToStationByName` clicks "Set Destination" in, which nothing
afterwards closes. Route panel plus that window is a conjunction only our own
sequence produces. If a future client closes that window on Set Destination the
symptom is the search repeating rather than travel starting, which the decision
log names.

**Bounded in both places, and the bound ends the session.** A trip gets
`homeStationTripSecondsPastSessionEnd` (420s) past the planned end instead of the
usual `secondsPastSessionEndBeforeGivingUpOnDocking` (120s), because a couple of
jumps and a dock do not fit in the 200-second wind-down. Once home, the restock
gets `homeStationRestockGraceSeconds` (60s) past the end, so arriving late does
not mean arriving pointlessly — though normally none of it is spent, since the
grace ends the moment the restock latches `droneBayWillTakeNoMore`. The clock
covers the case where no verdict arrives at all, which matters because the
restock's own give-up is to *fall silent* rather than to say anything. Both are
deadlines, not waits: when either expires the bot ends the session and says
which station it never reached. That distinction is the whole of issues #7 and
#14 — a longer bound is fine, a missing one is not.

The trade the setting buys: with `home-station` set, a wind-down that cannot
reach home ends the session **in space**, where before it would have docked
somewhere arbitrary. That is the point (an arbitrary dock is what makes the
restock useless) but it is a real change, and it only happens when the bay is
empty and a home station is configured.

ESI would need none of this — no typable substring, no row matching, no window
as evidence — and `botlab_host` already answers a `SetAutopilotDestination-
Request`. It is not reachable from a bot decision: `OperateBotConfiguration`
offers only mouse, keys and scroll, so nothing in a decision tree can issue a
volatile-process request at all. Until that framework gap is closed the search
bar is not an interim, it is the mechanism. The seam for swapping it later is
narrow on purpose — the travel path asks route-setting exactly two questions,
`homeStationRouteIsSet` and `routeToStationByName`, and knows nothing else about
where a destination comes from.

## Elm toolchain

`brew install elm` (arm64-native bottle) — **not** `npm install -g elm`, which
either grabs an unrelated package squatting the name or, pinned to `elm@0.19.1`,
fails on a broken arm64 download URL. Homebrew's build self-reports `0.19.2`
while every bot's checked-in `elm.json` says `"0.19.1"`, and an application-type
`elm.json` requires an exact match — so patch `elm-version` to `"0.19.2"` in a
**working copy** before compiling, never in the checked-in source.
`botlab_host.py` does this automatically.

## Screenshot / pixel data

Opt-in via `--capture-screenshots`, off by default: it costs ~1.6s per cycle,
dominated by the `screencapture` call, and most bots never read pixel data.
Format reverse-engineered from `BotFramework.elm`, not guessed. `pixelsString` is
a plain JSON array of `0x00RRGGBB` ints (`red<<16|green<<8|blue`), row-major,
height implied by `array length / widthPixels`. `ImageCrop.offset` is in the same
self-calibrated "game pixel" units as `clientRectLeftUpperToScreen` for
`_original` crops, but pre-divided by the binning factor for `_binned_2x2` and
`_binned_4x4`. All three resolutions are genuine area-averaged downsamples of one
capture (PIL's `Image.BOX`, a true block average rather than a blurring resize).
Pack with vectorised numpy — the naive per-pixel fallback, used when numpy is
missing, cost 5.2 of 8.2 total seconds by itself. `_original` is generated empty
(`[]`, valid per the type) by default, since a full-resolution Retina crop packs
to ~66MB of JSON and no bot in use reads `pixels_1x1`; the code to build it still
exists.

## Current status

- **Memory reading, root discovery, UI tree walk:** working and fast, via the
  native `tree_walker`.
- **Input execution:** working (`cg_input`), gated behind `--execute-input`.
- **Full bot loop:** proven end to end for `eve-online-mission-runner` and
  `eve-online-saxrat`, and for `eve-online-warp-to-0-autopilot`, from both a
  local path and a GitHub URL.
- **`eve-online-mining-bot` and `eve-online-wingus` compile now, but their input
  path is untested live.** Both are written against
  `BotLab.BotInterface_To_Host_2023_02_06` while `botlab_host/Main.elm` imports
  `..._2024_10_19`, so `elm make` used to fail on a missing module.
  `botlab_host/Main_2023_02_06.elm` is the wrapper for the older interface, and
  both `botlab_host.py` and `compile_bot.sh` now choose the wrapper from the
  interface the bot's own `Bot.elm` imports (read from the import, not from
  which interface modules the app vendors -- the mining bot ships two). All six
  apps build.

  The older interface has no `WindowsInputRequest` task: input travels inside
  the volatile-process request as `EffectSequenceOnWindow`, so `run_task`
  intercepts that and translates it into the same item list `_windows_input`
  already executes, keeping one input path with all its client-specific
  behaviour. Mouse buttons arrive as `KeyDown`/`KeyUp` carrying a mouse
  virtual-key code rather than as `ButtonDown`/`ButtonUp`; there is no scroll,
  relative move or raw character input in that vocabulary. The translation is
  unit-checked, **but no 2023-interface bot has yet been run against the live
  client** -- treat the first run as unproven, and watch that input actually
  lands rather than trusting the log.

  `VolatileProcess.handle_request`'s fallback used to answer *every*
  unrecognised request with `CompletedEffectSequenceOnWindow`, which is how a
  2023-interface bot would previously have reported every input as successful
  while executing nothing. It now logs what it could not handle.
- **`eve-online-mission-runner`** takes a security mission from an agent, flies
  out, clears each pocket through its acceleration gates, returns and hands in.
  Across 55 logged runs it completed 48 missions, median 58 ticks (~5.4 min).
  Combat features in 79% of them, gates 33%, looting 21%.

  It now also **restocks the drone bay while docked**, as maintenance in the
  wind-down window (`restockDroneBayWhileDocked`), so a run that ends with an
  empty bay does not hand the next one an empty bay too. This is a port of
  `reload_drones.py`'s sequence -- open the bay from the ship's own
  `ShipItemCard` context menu, filter the item hangar, drag the stack in,
  accept the quantity dialog -- driven by the bot's own input path instead of a
  standalone tool that fights it for the mouse. The drone is named by the
  `drone-type` setting, default `Acolyte I`.

  Note the dialog is *accepted* only once the reading has been checked for the
  refusal dialog first. Both are windows with an OK button and nothing else
  separates them, so clicking whichever OK is on screen and calling it "accept
  the quantity dialog" reports a success for a drop that moved nothing -- the
  same defect issue #19 found in the tool, inherited by the port.

  **What ends the task is the bay's own capacity gauge, read while the bay is
  the selected container.** The first version asked the *drones window* whether
  the bay was empty, and that window does not exist while docked -- the only
  state this task runs in. It answered "not empty" for every reading it would
  ever see, so the guard bailed every time and the whole feature was dead code
  that compiled and never once ran (issue #15). Nothing in a docked reading can
  answer the question before the bay is opened, so the first look now happens
  *after* opening it and costs the readings that takes.

  The gauge is also why the condition is **full**, not non-empty: a bay holding
  one drone of ten is not restocked, and only `used / maximum` can tell the
  difference. Its limit is that a drone's own volume is not readable, so a bay
  with less free space than one drone still reads as having room. That case
  ends in the client's refusal dialog, which is now recognised on its text and
  treated as the stronger answer -- it is the client saying directly that no
  more will fit.

  **Untested against a live client.** It compiles, the pure parts of the guard
  are unit-checked, and the parser sees `ShipItemCard`, but nothing here has
  been watched running: it needs a docked ship with a part-empty bay and the
  drone in that station's root item hangar. Two things to watch, both of which
  look like success from the log alone:

  - **An inventory not anchored to the ship** accepts the drag, shows the
    quantity dialog, and moves nothing. The bot's only evidence that its "Open
    Drone Bay" landed is the drone bay showing as the selected container
    (`droneBayOpenedFromShipCard`), remembered until the ship undocks; a client
    left with that container selected some other way would fool it.
  - **The gauge parsing.** `reload_drones.py` reads `50.0/50.0 m³` off
    `InvContCapacityGauge` on this build, so the text exists and has the shape
    the parser wants; what is unverified is the Elm parser picking that node
    out of an inventory window (it takes the first descendant whose type name
    contains `CapacityGauge`) and the bay reading `ShipDroneBay` as the
    selected container. If either misses, every look reads "a capacity gauge
    that does not say", the bot drags twice on the assumption there is room,
    and then gives up -- deliberately, because a condition that cannot see the
    bay must not be allowed to conclude the work is done. That is the failure
    #15 was.

  Read the decision log for the `Maintenance:` lines: one drag followed by one
  `look ... of 3` and then silence is a restock that landed. Silence right
  after the last look is the give-up. The drones window after the session is
  still the last word on what is actually in the bay.

  With `home-station` set it now also **goes where the drones are** rather than
  restocking wherever the mission chain left it — route, travel, dock, restock,
  or restock in place when it is already there. See "The home station" above for
  the naming, the trigger and the two deadlines. **Untested against a live
  client**, and the whole path only exists under `--session-duration-minutes`.
  What to watch first: whether the `Station: Information` window survives the
  "Set Destination" click, since that window is what tells the bot the route it
  is following is its own. The tell is `Home station: ... set the route to`
  repeating where `Home station: travelling to` should have taken over.
- **`route_setter.py`** works — reads a chat channel's MOTD, parses the embedded
  `showinfo:5//<systemID>` links (tag-stripped, so a malformed `Sizamo</loc>d`
  still recovers as `"Sizamod"`), right-clicks each in the packed rich text and
  picks "Set Destination" then "Add Waypoint", verifying each click against the
  menu's own "Avoid X (Solar System)" text first. Genuinely fragile next to the
  main bot loop; run it standalone.
- **ESI (the official API) is available after all**, via an older account that
  already had developer access — the earlier note here said registration now
  required a real-money EVE Store purchase and so ruled it out. `POST
  /ui/autopilot/waypoint/` is the correct way to set a route, and
  `tools/macos-host/esi_waypoint.py` implements it (PKCE, so no client secret
  exists; the refresh token lives in the macOS Keychain and is never printed).
  Name resolution is verified both ways. The authenticated half is **proven
  live** and this file's earlier "untested pending a browser login" was stale:
  issue #17 records `esi_waypoint.py set --name "Amarr VI (Zorast) - Moon 2 -
  Theology Council Tribunal"` resolving to 60008950 with the client's route
  panel flipping from `No Destination` to `Route 0 Jumps` immediately after,
  credentials taken from the Keychain (`eve-esi-client-id`, `eve-esi-refresh`)
  and no browser step needed. That name carries both a parenthesis and a
  hyphen, so it is exactly the destination the search bar below cannot express.
  Note `/universe/ids/` does not index every NPC
  station — the agent's own "Amarr VI (Zorast) - Moon 2 - Theology Council
  Tribunal" comes back empty from it — so the tool falls back to resolving the
  system from the name's first token and enumerating its stations.
  ESI covers navigation only: CCP exposes no endpoint to request, accept or
  complete an agent mission, so the conversation stays UI automation either way.
  The search-bar route below needs no registration at all and is the fallback.

  **`SetAutopilotDestinationRequest`** is the volatile-process request that
  brings this into the bot loop: `{"name": …}` or `{"destinationId": …}`,
  answered with `{"Completed": {"destinationId": N}}` or `{"Failed": "why"}`.
  Two shapes rather than one shape with a flag, because a destination that
  silently was not set followed by travel logic finding no route is this repo's
  signature failure — see #7. `handle_request` catches everything, including
  what it did not expect: an exception escaping to `run_task` becomes
  `ProcessNotFound`, which `BotFramework` reads as "the volatile process is
  gone" and answers by tearing it down and re-running root discovery.

  It is **bounded**, because `handle_request` runs inside the host's single
  request/response loop and an ESI that never answers would hold up the tick
  that asked and every tick behind it. The budget (15s, `--budget` on the CLI)
  covers the whole resolve-and-set rather than one request, since the
  enumerate-a-system fallback costs a round trip per station: measured through
  the dispatcher, that station resolves cold in 3.1s. Expiry is a `Failed`, not
  a wait. Resolutions and the universe GETs behind them are memoised for the
  life of the process — ids never change, and memoising each station the
  fallback looks at means an attempt that ran out of time gets further next time
  instead of starting over. The same name resolves in 0.00s after the first.

  **The host side is all of it that exists.** Nothing issues this request yet;
  see the Architecture section for why the bot has no channel that can carry a
  station name, and what would have to change to give it one. Until then this is
  reachable only from Python, and no bot has set a destination through it.
- **EVE's own game log reaches the bot**, as
  `ParsedUserInterface.gameLogEntriesSinceLastReading` — the refusals behind
  issues #14, #19 and #27, which those features each had to infer indirectly
  from something failing to change. The shape, the safety properties and the
  vendoring policy are in the Architecture section.

  **Verified without a live client, and that is most of what a live client
  would have added.** 30 unit tests in
  `tools/macos-host/tests/test_game_log_channel.py` cover the tail, the
  filtering, the node and `_read_from_window`, replaying the real lines the
  host echoed during five recorded runs — including a check that every one of
  those ~4,850 recorded lines parses. The Elm half was driven end to end
  off-line: a host-built reading, double-encoded exactly as the real one is,
  through `decodeMemoryReadingFromString` and the real vendored
  `parseUserInterfaceFromUITree` (mission-runner's copy and saxrat's), giving
  the three lines back with their timestamps and channels intact, `Just []`
  for a reading with nothing to report, `Nothing` for a host with no game log,
  and `getAllContainedDisplayTexts` over the whole tree unchanged by the
  node's presence.

  **What is unproven is that any of it changes what the bot does**, because
  nothing reads the field yet. A first consumer needs three things: a decision
  that matches on `channel == Just "notify"` and the refusal's own wording, a
  `BotMemory` field to carry the verdict (a reading's entries are gone by the
  next one, so a branch that does not record what it saw sees it once), and a
  live run that provokes the refusal — for #27's ammo load, guns firing and a
  swap attempted. A run in which no refusal occurs proves only that nothing
  broke.

## `route_setter.py` internals worth knowing before touching it again

Locating a system-name link inside the MOTD's packed rich text is the whole
difficulty: it is not a separately-addressable node, the entire block is one
`Label`'s `_setText`, so the only way in is to right-click at a guessed position
and check what menu comes back. Several rounds of live-verified fixing, each
guarding against a failure that looks like being stuck:

- **Steer both directions.** Correct a miss by the *signed* line-count
  difference, using the route's own ordering. A down-only fallback jams
  permanently once it overshoots.
- **On blank space, nudge in the last steering direction**, not always down, or
  a correct upward correction gets undone by the next attempt landing in an
  inter-line gap.
- **Try several x positions** — `(30, 45, 60, 90, 120, 150, 180)`. Short names
  don't reach as far right, and double-digit line numbers shift where the name
  starts.
- **Don't stop the x-scan at the first non-empty menu.** Right-clicking plain
  text returns a real but useless "Copy | Copy All".
- **Verify the menu closed** rather than sleeping after Escape, or the next
  right-click re-reads stale state.
- **"Set Destination" replaces the entire route**, so clicking it on the next
  intended system is a clean reset with no separate clear step.

## Setting a destination by name, via the search bar

This section previously recorded the "Search for anything" bar as a dead end
that yielded no readable results from type+Enter. **That was wrong**, and the
likely reason is instructive: the sweep that "found nothing new" ran while
`tree_walker` was truncating at 5,000 nodes in arbitrary DFS order, so the
results window was probably read and then discarded. The budget is 20,000 now.
Re-verified live end to end, and it is the only way the bot can originate a
destination — every route it sets otherwise comes from the mission tracker's own
travel buttons, which do not exist once a mission ends.

The working sequence, each step confirmed against the live client:

1. Click `InfoPanelSearch` (the field is its own node, canvas ~(60,71)), type the
   station name, press Return.
2. A `ListWindow` captioned **Search Results** opens, with collapsed group
   headers — `Corporations (1)`, `Stations (26)`.
3. Click the `Stations (N)` label to expand. Rows render as
   `<color=…>0.9</color> Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal (2 Jumps)`,
   so security, full name and jump count are all readable.
4. **Double-click** the row. This opens a `Station: Information` window.
5. Click that window's **Set Destination** button (a `ButtonWrapper`, 126×32).
6. `InfoPanelRoute` flips from `No Destination` to `Route N Jumps …`.

Two traps, both hit live:

- **Right-clicking a result row does nothing.** No context menu at any x position
  across the row — it only selects the row and raises a tooltip. Double-click to
  Show Info is the only route through. Do not spend time widening a cascade
  tolerance for a menu that never opens.
- **The hover tooltip is a separate label rendered outside the window**, to its
  left. A naive text search for the station name matches the tooltip before the
  real row, and right-clicking that hits empty space. Scope the row lookup to the
  `ListWindow` subtree — and note `eve_read.walk(node, x, y)` accumulates offsets
  from wherever it starts, so re-walking a subtree with its own absolute position
  as the base double-counts that offset. Identify the subtree by node identity
  and keep the coordinates from a single root-level walk.

Typing the query needs no new host capability: `Common/EffectOnWindow.elm`'s
`effectsToEnterString` already turns a string into `KeyDown`/`KeyUp` effects and
tracks shift state across the sequence. Its coverage is the limit — see
`getKeyboardKeyToEnterChar`, which handles letters, digits, space, `-` and `+`
and returns `Nothing` for everything else, which makes the whole string an `Err`.
A station name containing parentheses cannot be typed as-is. It does not need to
be: search on a distinctive parenthesis-free substring and pick the right row by
full-name match from the rendered list. Note also that `'-'` maps to
`vkey_SUBTRACT` (0x6D, the numpad key), which is **not** in `botlab_host.py`'s
`_VK_TO_CGKEYCODE` — a hyphen in a query silently has no key to press. (`0xBD`
OEM_MINUS *is* in that table; `getKeyboardKeyToEnterChar` simply does not pick
it. The mission runner's own `typeTextEffects` sidesteps the whole question by
emitting letters, digits and spaces only and dropping the rest.)

`eve-online-mission-runner`'s `routeToStationByName` is this sequence in Elm,
and the `home-station` trip is its second caller. Both rely on the substring
workaround being load-bearing rather than temporary — see "The home station"
for why ESI cannot replace it from inside a bot yet.

## Open gaps

- `dictEntriesOfInterest` doesn't recursively encode non-primitive "interesting"
  values the way Sanderling's serialisation does. `getDisplayText` in
  `ParseUserInterface.elm` falls back to decoding a non-string `_setText`/`_text`
  as *another full `UITreeNode`* — a real case, since it can hold a Python `Link`
  whose own `_text` has the actual text. Symptom seen live: "current solar
  system: Unknown" for a name that isn't a plain string in memory.
- `MouseMoveRelative` and `CharacterDown`/`CharacterUp` (raw Unicode text input)
  aren't implemented in `botlab_host.py`.
- Nothing reads `gameLogEntriesSinceLastReading` yet, so every guard that infers
  a refusal indirectly still does — #27's ammo load retries for 50 readings on a
  swap the client refused outright, and the learned lock range can still only be
  taught by the first lock of an engagement.
- No automated Elm-toolchain bootstrap if `elm` isn't on `PATH`.
- `reload_drones.py` only searches the root Item hangar, no sub-folders. The
  mission runner's port of it inherits that, and also takes the first
  `ShipItemCard` in the tree as the active ship, which is what the tool does --
  untested on a character with several ships in the same hangar.
- Tested against a handful of bots and one display configuration (single
  display, specific Retina scale). Non-EVE bots using
  `OpenWindowRequest`/browser automation are stubbed to always fail.
- Tick time, measured over run 57 (376 ticks, 3,025s): the memory read was 53%
  of the whole run, `send-effects` 22%, `bot-step-delay` 9%. The page cache
  below cut the read from 1.78s to 0.44s, which takes roughly 40% off total
  run time; after it, `send-effects` is the largest remaining cost. Most of
  that is not the input itself but the `WaitMilliseconds 210` the framework
  interleaves between every pair of effects, plus ~0.82s per eased mouse
  glide. Both are bot-authored pacing that the Photon UI genuinely needs —
  shortening either is a live-behaviour risk, not a free win.

## Repo state

`origin` = `Viir/bots` (upstream, untouched); `fork` = `smerwin/bots` (personal,
added with `git remote add` — `gh repo fork --remote` reported success but did
not actually add it). Work is committed and pushed to `fork` `main`.

Root `.gitignore` excludes `.DS_Store`, `__pycache__/`, `*.pyc`, and the
ad-hoc-signed compiled tool binaries (`probe`, `memory_sample`, `tree_walker`,
`live_reader`, `window_probe`, `cg_input`). Each has adjacent `.c` source;
binaries are platform-specific build output, so a fresh clone must rebuild them —
e.g. `clang -O2 -framework ApplicationServices -o cg_input cg_input.c`.
