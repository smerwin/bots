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

**The combat lines are withheld; their total is not.** Issue #32 wanted a
retreat that does not depend on the ship's HUD, and the only instrument that can
give it is the one channel the bot could not see. Both halves of that turn out
to be right at once: the *lines* are noise a decision has no use for — 134,641
of them across the recorded sessions, peaking at 54 inside a single three-second
reading — while the *total* is exactly what the decision wants and is one
number. So the host sums it and appends a second synthetic node,
`MacOsHostSyntheticIncomingDamage`, carrying `damage`, `hits` and `topAttacker`,
lifted into `ParsedUserInterface.incomingDamageSinceLastReading : Maybe
IncomingDamage`. Same four safety properties as the game-log node, same
`Nothing`-versus-present distinction — a summary of zero is "the client reported
no incoming fire" and an absent node is "this host does not carry the channel",
and only the second may ever be read as "we do not know".

Summing it host-side rather than in Elm also puts the one dangerous distinction
in one tested place. `N from X` is damage taken and `N to X` is damage dealt,
they are the same shape, and there are more than twice as many of the second —
a retreat armed by the bot's own guns would fire hardest when the fight was
going well. `tests/test_incoming_damage.py` checks the matcher against real
recorded lines in both directions, plus the four `(combat)` lines in the whole
corpus that carry "from" and are not damage (`Warp scramble attempt from …`),
which is why the pattern is anchored on the leading number rather than the word.

**A reading's entries are gone by the next reading, and that shapes every
consumer.** A branch that reads them and writes nothing down sees a refusal once
and then behaves exactly as it did before — so the verdict has to be recorded in
`BotMemory`, in `updateMemoryForNewReadingFromGame`, which is the only place that
can write memory and the one place that never sees the decision. The ammo swap's
`loadRefusedByClient` is the worked example.

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

## What the bot is willing to shoot

For a long time this was two rules, and both required somebody to have predicted
the object: the overview's icon colour (`iconSpriteHasColorOfRat`, a sprite
palette test) and a list of names in the `attack-object` setting. Anything
matching neither was invisible — **including things actively shooting the ship**,
and the failure is silent in the worst available direction, since "nothing to
fight" is what the bot prints either way. Issue #40's principle: whatever is
shooting the ship is a valid target, whatever colour its icon is and whether or
not anyone remembered to name it in a setting.

**Issue #40's headline incident is not this, and the recordings say so.** It
attributes run 10's long "Nothing to fight and no travel step offered" stretch to
this blindness; the log has that stretch running 900 decision blocks on
`Illegal Activity (3 of 3) -- You need to activate the Acceleration Gate`, with
**zero** incoming damage in the window, zero rats and a full shield throughout.
That is #41's gate-locked refusal, fixed in #42. The frigates the issue quotes
were engaged normally in the same run —
`Lock target from overview entry 'Federation Navy Delta II Support Frigate'`
appears throughout the pocket they were in — so the icon rule matched them.

What the recordings do support is the gap itself, quantified: across them there
are **1,198 readings taken under fire and 299 of those where the icon rule
counted zero rats**, a quarter. Most are in warp, retreating or travelling with
nothing on grid, but 26 sit at an acceleration gate absorbing 320-370 hitpoints
a window from something the client names `R.S. Officer` while the bot engages
nothing. Whether that attacker had an overview row the colour rule missed, or
simply had no row at all, **the recordings cannot say** — the bot prints the
count, never the rows. That is the one thing a live run has to settle.

**The third rule is the client's own statement of fact.** EVE's combat log names
every attacker — `49 from Centior Monster - Penetrates` — and the host already
aggregates that channel into `incomingDamageSinceLastReading`, whose
`topAttacker` field *is* the attacker's name. So the widening cost no new
plumbing: the raw `(combat)` lines stay withheld, and `isObjectShootingAtUs`
matches an overview row against the names the window already holds.

**The two names are the same string**, checked rather than assumed. Across all
ten recorded runs the combat log names 37 distinct attackers and **33 appear
byte for byte** as an overview entry's Name in the bot's own
`Lock target from overview entry '…'` and `Current target: …` lines — same case,
same spacing, apostrophes and full stops intact
("Kruul's Henchman", "R.S. Officer"). Of the four that do not, three are rats the
bot never locked, so no overview-side string was ever printed for them; the
fourth is `Toxic Cloud Environment`, the pocket's own damage cloud, which has no
overview row and therefore matches nothing. `test_shoot_back_at_attackers.py`
pins that round-trip against the recorded lines, #31's pattern.

**Matched exactly, never as a substring.** `attack-object` already learned this
in both directions, and there is a worse case here: a wreck's Type is its
owner's name with " Wreck" appended, so a substring rule would have the bot open
fire on the corpse of the thing that stopped shooting it — forever, since a
wreck cannot die. Name and Type are both accepted, which exactness makes safe;
the recorded evidence is for the Name column specifically.

**`topAttacker` is one name, and a pocket has several attackers.** Rather than
widen the host's aggregation into a list, the name rides on each
`IncomingDamageSample` and the *window* of them is the set. Measured over the
recorded runs, accumulating the per-reading top attacker across 45 seconds
recovers **1674 of 1717** name-in-window pairs (97.5%) that carrying every name
would have — a reading is one to three seconds, so a second attacker takes the
top slot within a few of them. Run 10's own pocket shows it directly: two
consecutive readings, one topped by `Federation Navy Delta II Support Frigate`
and the next by `Federation Navy Soldier`. Holding the names inside `samples`
also means **no new counter and no new clearing rule**: they are trimmed by the
same clock, capped by the same `incomingDamageSampleLimit`, and gone 45 s after
the last hit — one condition covering the rat dying, the ship warping out and
the pocket ending.

**It widens the set; it does not reorder it.** An entry qualifying only because
it shot us enters the same list at its own distance rank, and every existing
guard still applies by placement: `overviewEntryDistanceIsOnGrid` (so an AU
distance is still excluded), `overviewEntryIsDisplayed` at the lock site (so a
virtualised row is still never clicked), and the scrambler-first sort — being
unable to *leave* still outranks being shot. When the colour rule and this one
agree they produce one entry, not two.

**The one place it stops is a briefing saying clearing is optional.** Attackers
are deliberately absent from `isObjectToAttackByName`, which is what survives
that filter. A briefing that says the pirates need not be cleared is the client
saying in writing that the fight is not the job, and ignoring that cost run 102
over 400 combat decisions and run 106 a session on Recon. The cost is stated
rather than hidden: on such a mission the bot travels to the objective while
being shot and does not shoot back, and what covers that is the damage-rate
retreat, not this.

**Webbing is not damage, and that case is not covered.** A webifier can apply no
damage at all, and then it writes no combat line, so a signal built on damage
cannot see it — which is precisely run 10's two frigates, whose rows the issue
reports rendering "Pilot is webifying me". They happened also to deal damage, so
run 10 itself is covered; a pure webifier would not be. That string appears
**nowhere in the ten recorded runs** — nothing had ever printed these hints — so
matching it would be a guard resting on a premise no evidence supports. The
hints are printed instead (`Overview indications:` in the status line, distinct
strings from rendered rows only), which is what turns the next run into the
evidence a follow-up can be built on. `commonIndications` still reads exactly
the two literals it inherited, `is jamming me` and `is warp disrupting me`.

Every engagement of this kind names itself in the decision log —
`Shooting back at '…': the client's combat log names it as having hit this ship
in the last 45 s, and nothing else here marks it as a target.` — and only when
nothing else would have selected the row, so the line means "this is new" rather
than appearing beside every rat in the pocket.

## When the tracker says Dock, the fight is over

The mission runner's on-grid priority is the fight, then the looting, and only
then travel — `decideActionInMissionPocket` wraps the whole travel branch in
`decideActionInCombat`, so travel is the fallback reached once combat has
nothing left to offer. That is the right default while a mission is in progress
and the wrong one the moment it ends, because combat has something to offer for
as long as anything on the grid is alive.

Run 11 measured the cost. The tracker read `Illegal Activity (3 of 3) -- no
instruction (next step: Dock)` on **77 consecutive in-space readings**; 386 of
the 453 decision blocks inside them went to locking and shooting; and the first
in-space click on that Dock button came **603 seconds** — just over ten minutes
— after the label appeared, on the first reading where the overview finally read
`Rats in overview: 0`. The objective was carrying no instruction the whole time:
nothing left to destroy, retrieve or approach, and the only thing the tracker
wanted was the trip back.

**`dockOutranksTheFight` is the whole exception**, and it is placed rather than
conditioned: it wraps the combat call inside `decideActionInMissionPocket`, so
the fight becomes the fallback exactly where travel used to be. It fires only
when the tracker's travel button reads `Dock` **and** the objective's
`instructionTexts` is empty or blank.

**Both halves are load-bearing, and the recordings say so.** Of the 1,738 `Dock`
readings across the eleven recorded runs, 326 carry a live courier instruction
(`Bring <a …>The Damsel</a> to …`) — a mission still asking for something — so
the label alone would have disengaged on an unfinished objective.

**The label is matched whole, never as a substring, because "Undock" contains
"dock".** That is the label the tracker shows at the start of every mission, so
a substring rule would read the ship's own departure as "the objective is
complete" and try to leave from inside the station. The recordings carry ten
distinct *text* travel labels — `Warp to Location`, `Destination Set`,
`Warping`, `Dock`, `Set Destination`, `Preparing`, `Start Conversation`,
`Undock`, `Abort Undock`, `Read Details` — and exactly one of them ends a
mission.

**The client can render a travel step as a glyph with no text at all, so any
matcher on this field must fail closed.** Run 11 produced an eleventh "label"
three times:

```
U+0002 U+0000 U+AD1D8 U+0001 U+0001 U+0000 U+0001
```

— six C0 control characters around one codepoint that is **unassigned**
(category `Cn`, plane 10), *not* private-use. That distinction is the trap: a
rule that recognised "not text" by private-use membership would classify this as
text. It arrived on `Recon (3 of 3) -- You need to warp to the mission location`
and the bot pressed the button carrying it, which is the ordinary travel
behaviour and not something the Dock change touches.

Both halves of the condition decline it independently, checked by running them
rather than by reading them: `missionTravelStepIsDock` answers `False` for that
string, and `missionHasNoOutstandingInstruction` answers `False` for the
objective beside it. An exact comparison is what makes that automatic — a
substring or "starts with" rule on a field that can hold arbitrary bytes has no
such guarantee.

It also has a lesson for the *tests*. Asserting "the set of travel labels is
exactly these ten" fails the moment the client emits one of these, on a machine
whose logs happen to contain it — which is what happened, on a run still being
written. The assertion is over the **printable** labels, with the non-text case
tested separately as the property that actually matters.

**What still keeps the guns firing after `Dock` appears**, since the point of
the branch is to stop:

- **Anything warp disrupting the ship.** Docking is a warp, so a scrambler makes
  leaving impossible and killing it is the only thing that restores the option —
  the same reason `overviewEntryIsWarpDisruptingMe` sorts to the front of the
  combat candidates. The branch hands the fight back **and says so every reading
  it declines**, for `returnDronesToBay`'s reason. This is the one case where
  being shot outranks leaving.
- **Any other travel label**, and **an objective still carrying an
  instruction** — both keep the old order untouched.
- **A lost ship and the two retreats.** `recoverPodAfterShipLoss` still
  short-circuits the docked-or-in-space split above all of this, and
  `runAwayIfLowHealth` still runs before `decideActionWhenInSpace` is called at
  all, so #32's damage-rate retreat outranks this branch. That is the right way
  round: the retreat is the controller for "leave now, this is going badly" and
  this one is for "the job is done, go home". There is no second one — this
  branch presses the tracker's own button and owns no clock, no counter and no
  memory.

**Being shot, otherwise, does not keep the guns on**, and that is a decision.
#40's rule stands while there is a fight to be in; once the tracker says Dock the
answer to being shot is to leave. The recordings say the trade is cheap: over
those 77 readings the client's combat log reported any incoming damage at all on
**4** of them, at most **7 hitpoints** in a 45-second window against a threshold
of 3,500. Were the damage real, the retreat above would have taken the reading
before this branch saw it.

**Drones leave through the recall that already exists.** The click is handed to
`ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`, exactly as the
travel branch it hoists always did, so #7's lost drones and the give-up that
followed apply unchanged and are not duplicated.

**It clears itself, so it needs no bound.** Every condition is re-derived from
the live reading: the moment the button stops reading `Dock` — the ship docked,
the mission moved on, the tracker collapsed and took the button out of the tree —
the fight is the bot's job again on that same reading. Nothing latches.

Two decision-log lines carry it, and an operator should be able to see which:

```
+ The objective is complete and the mission tracker says 'Dock' -- stop fighting and leave the rest of the field alone.
+ The mission tracker says 'Dock' and the objective asks for nothing more, but 'X' is warp disrupting this ship -- nothing leaves until that is dead, so keep fighting.
```

**Verified without a live client**, in
`tools/macos-host/tests/test_dock_outranks_the_fight.py`: the two pure rules are
run through the real `Bot.elm` in `elm repl` rather than mirrored in Python (copy
the app to scratch, open `module Bot exposing (..)`, patch `elm-version`, drive
it — twelve seconds), against every travel label and objective string the
recordings contain, including the non-text one, which is rebuilt inside Elm with
`Char.fromCode` since a NUL cannot go in a string literal; the *text*
travel-label vocabulary is re-checked against `~/eve-bot-logs` so a client that
starts writing a different readable label fails loudly; and the ordering, the
scrambler decline, the drone recall and the absence of a counter are read out of
the source. Reading a log a run is still appending to is safe — lines are taken
one at a time and a trailing partial line is skipped.

Confirmed by mutation, on the code and on the tests' own premises: a substring
label match, re-wrapping the dock step in combat, dropping the scrambler
decline, skipping the drone recall and ignoring the objective's instruction each
fail it — and so do removing a known label from the list (so the drift check is
live) and making every category count as text (so the glyph is covered by
classification rather than by luck).

**Not verified: any of this running.** What to watch on the first live run is the
first line above arriving within a reading or two of `(next step: Dock)` showing
up, followed by the drone recall and a dock — rather than another ten minutes of
`I see a locked target`. The looting question is deliberately still open: a wreck
holding the mission item is not optional the way ordinary salvage is, and this
change does not answer it.

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

`isActive` reads `ramp_active` off the button. **That entry is the module's duty
cycle, not whether it is switched on**, and the previous version of this
paragraph — "`Just True` while running" — was wrong in the specific way that
cost #34.

Measured, read-only, 92 samples over 240s of run 9 (#35): on the weapon,
`ramp_active` flipped **fourteen times** in those 240 seconds, 5–20s apart,
while `isInActiveState` stayed `True` across every one of them. The gun never
switched off. So `ramp_active = False` means *between cycles*, and a module that
is firing reads `False` for a good part of every cycle. Middle and low slots
behaved differently and consistently — they went `True` at 60–70s and never came
back down, which is what a repairer or prop mod cycling continuously looks like.

That is the whole of run 8. `gunsSilencingTicks` reset whenever no gun *read* as
firing, so it reset inside every cycle and never reached 2; and a wait for "the
ramp to stop" is satisfied by the gap between cycles rather than by the guns
going quiet. Both halves of #34 were reading this field. Nothing in the ammo path
depends on it any more — #38's deadline was deliberately built to hold with this
reading worthless — but anything new that treats `isActive` as "this module is
doing its job" is repeating the mistake. `isInActiveState` is the entry that
means that, and it is not wired to anything yet; see below.

**`Nothing` and `Just False` are still different facts.** The entry is absent
until the module has cycled at all — for the first ~60s of that sample no module
carried `ramp_active`, and it then appeared per module as each first cycled
(low slot 60.3s, mediums 65.5s and 70.7s, the weapon 88.8s). This confirms the
`ShipModuleButtonRamps` widget being created when cycling starts. Treating
`Nothing` as off is still the right default, but it conflates "off" with "has
never run", so never store it as a defaulted `Bool`.

### The sprites really are missing; the state is somewhere else

`isBusy` and `isHiliteVisible` are permanently `False` here, and that much is
confirmed: a walk of a top-row button's whole subtree finds exactly one sprite,
`underlay`. There is no `hilite` and no `busy` in this build, so those two
lookups cannot return anything else however the module behaves.

**The conclusion this file used to draw from that — that the client does not
expose the state — was wrong.** The button's own `dictEntriesOfInterest` carries
twelve entries that nothing had ever read: `ramp_active`, `isInActiveState`,
`isDeactivating`, `effect_activating`, `online`, `blinking`, `grey`, `quantity`,
`autoreload`, `autorepeat`, `isMaster`, `waitingForActiveTarget`. Same shape as
#26's tooltip dead end, where the workaround also turned out to be a different
reading rather than an absent one. Assume the state is present somewhere before
concluding the client withholds it.

All twelve are now parsed onto `ShipUIModuleButton.stateFromDictEntries`, under
the client's own key names, and cost twelve dictionary lookups on a node the
parser already holds — no extra traversal, unlike the two sprite lookups above.
Every field is a `Maybe`; an entry that does not decode is `Nothing`, never a
guessed `False`.

What the same 240s sample says about the rest:

| entry | observed | reading |
|---|---|---|
| `isInActiveState` | `True` on all four modules, all 92 samples | **switched on** — the flag `isActive` should have been |
| `isDeactivating` | `False` throughout, never once `True` | **unobserved** — nothing switched a module off in the window |
| `effect_activating` | `0`, except a single `1` at 175.3s, 2.6s before a cycle began | a brief pulse at **activation** |
| `waitingForActiveTarget` | absent until 141.3s, then `0` on all four at once | `0` = not waiting; appears late, needs more observation |
| `online` | `True` throughout | |
| `blinking` / `grey` / `quantity` | `0` throughout | |
| `autoreload` / `autorepeat` | `1` / `1000` throughout | settings, not state |
| `isMaster` | `1` on the high slot only | identifies the weapon group's master |

**Nothing decides anything from them, and that is deliberate.** This is one 240s
window on one fit, and the leg #34 actually needed has zero observations:
`isDeactivating` is named for exactly the state that wait cared about and was
never once `True`, because the bot performed no ammo swap while the sampler ran
and nothing else switched a module off.

**Capturing that leg is what the status line is for.** The mission runner prints
five entries every reading —
`Top-row modules (ramp_active/isInActiveState/isDeactivating/effect_activating/waitingForActiveTarget)`
— with `T`/`F` for a boolean, the number for a numeric entry, and `-` for an
entry **absent from the tree**, which is a distinct output from `F` and `0` on
purpose. So the next run that performs an ammo swap records the switch-off
without anyone watching: read those columns across idle → activated → firing →
commanded off → settled. The other seven entries are parsed and available but not
printed, since this line goes out thousands of times a run and all seven were
constant across the whole sample.

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
ever hovered a module here before. Nothing depends on the answer any more: the
ammo swap reads the module's own context menu instead, and uses the tooltip only
to derive a crossover distance when `ammo-swap-range` is unset.

## Retreating: the HUD hitpoint gauge is the weakest instrument here

Issue #32 was filed on run 7 losing the ship while the bot's health reading sat
at 100% shield / 100% armour for all 724 samples. The reading was telling the
truth. Reconstructing run 7's wall clock from its `(Ns)` gaps and lining it up
against the client's own log puts the ship's death at 04:26:59 and the bot's
first reading at roughly 04:27:29 — and from 04:27:33 the client is answering
every lock attempt with `The ship you are piloting does not have targeting
systems installed`, 173 times. **Run 7 flew a capsule from its first reading to
its last**, and a capsule genuinely reads 100/100.

That matters for three reasons.

**The fatal engagement happened while nothing was watching.** All 9,286 hitpoints
of it landed between 04:23 and 04:27 — after run 6's log stops at 04:23:05 and
before run 7's first reading. Run 7's log shows the slow `elm make` path
("Verifying dependencies (0/17)" through 17/17) filling that gap. So the ship sat
in a hostile pocket, unattended, for four minutes of a run's own startup. No
guard inside the bot can cover that, and none of the ones below would have.
Cycling a run inside a mission pocket is the risk; dock, or clear the grid,
before stopping one.

**Nothing in #32's list would have saved run 7 either**, because by the bot's
first reading the ship was already gone. What run 7 needed is #33's ship-loss
detection. The guards below are for the next engagement the bot is actually
present for.

**The gauge is still not trustworthy, independently of any of that.** Across all
eight recorded runs `ShipUI.hitpointsPercent` produced -1021821%, 2132822%,
302023%, 8362%, 7711% and others, always for exactly one reading and always
surrounded by sane values — run 8 reads 95, 95, 95, 2132822, 95. It is
`gauge._lastValue * 100` read out of a widget in the client's live memory while
the client is mutating it, so a single garbage reading is a read landing on a
reallocated object. `plausibleHitpointsPercent` rejects the impossible ones and
always has; what it cannot do is anything about a garbage value that happens to
land inside [0, 100], and 0.42 is as reachable as 21328.22. That is the argument
for a signal that does not come from a sprite at all.

**Armour on this hull is not a second opinion, it is a later one.** The ship is
shield-tanked, so armour takes no damage until the shield is at zero: across
runs 2-8 the armour gauge read exactly 100% in every one of thousands of samples
while the shield reached 9%, 12% and 44%. The launcher shipped
`run-away-shield-hitpoints-threshold-percent=-1`, which therefore did not leave
one guard, it left none. It now ships 25 — chosen because the two recorded
sessions that went below it went to 9% and 12%, and the worst any other reached
was 44%. Both of those two completed their missions, so this costs an aborted
mission on a run like them.

**`run-away-incoming-damage-threshold` is the guard that needs no gauge.** EVE's
own combat log, summed by the host per reading, over a rolling 45-second window
held in `BotMemory.incomingDamage` — a reading's entries are gone by the next
one, so the window has to be written in `updateMemoryForNewReadingFromGame` like
every other verdict from this channel. Calibrated from peak 45-second incoming
damage across sixteen recorded client sessions: the worst any session the ship
survived absorbed was 3114, and the session it was lost in peaked at 4101. The
default is 3500, about 12% clear either way, which is the best this data offers
and is a real separation rather than a comfortable one. **It is a number about a
hull, not about the game** — carrying it to another ship fails silently in
whichever direction that ship is different.

45 seconds is where the separation is widest: at four minutes the same
comparison is 8689 against 9286, which no threshold could tell apart.

**A reading that cannot move is not a reading.** The third guard fires when the
ship has absorbed `damageThatMustMoveTheHitpointsReading` (1500) inside the
window and the `(shield, armor)` pair has not changed across it. A `Nothing` —
no ship UI, or a value rejected as impossible — never counts as movement, so a
window of nothing but unreadable values reads as frozen, which is the
conservative direction and the intended one. Calibrated the same way: measured
across the three runs whose gauge was live, the most damage ever absorbed while
the pair stayed frozen was 595 hitpoints over 21 seconds. It sits below the
damage threshold on purpose — a ship that cannot see what is happening to it
gets less rope than one that can.

**Trip and release are different conditions**, for the reason
`runAwayRearmPercent` exists. The damage latch trips when the window crosses the
threshold and clears only when the window is completely empty — nothing has hit
the ship for a whole 45 seconds. A live comparison would cancel its own retreat:
the moment the ship warps clear the window starts draining. The cost of that
choice is a loop — the bot flies off, the window empties, the mission logic
brings it back into the same pocket, and it leaves again — which is survivable
where the old behaviour was to stay and die, but is the first thing to watch on
a live run.

**A lost ship outranks every one of these**, and the order is settled by
placement rather than by a condition. `recoverPodAfterShipLoss` (see "Losing the
ship") sits in the pre-split list and answers `Just` on every reading its verdict
exists, so once that verdict latches the docked-or-in-space split is unreachable
and `runAwayIfLowHealth` is never called again. That is the right order and not
merely a convenient one: a retreat manoeuvre is something a *ship* does, and the
answer to no longer having one is to fly the pod home and end the session, not to
warp a capsule between celestials indefinitely.

The two really can want to act on the same reading, which is why it is worth
stating: a capsule gets shot, and being shot is exactly what arms the damage
guard. `updateIncomingDamageMemory` keeps running through a pod recovery — its
latch can set, harmlessly, since nothing reads it from up there, and its status
line still reports whether the pod is under fire, which is worth having. The one
case where the retreat speaks for a capsule at all is where the ship-loss verdict
never arrives, and there it is a better fallback than run 7's alternative of
sitting still asking for locks. A fallback, not a second controller.

That ordering is pinned by a test rather than remembered, because inverting it
leaves everything compiling — which is issue #12's failure exactly.

**The two changes read different fields of the same reading**, so neither can
consume the other's: #33 reads `gameLogEntriesSinceLastReading` and #32 reads
`incomingDamageSinceLastReading`, both pure fields of a parsed record, and both
write their verdict into a separate `BotMemory` field in the same
`updateMemoryForNewReadingFromGame`. The place where they genuinely do share
state is the host, where one file offset now feeds three queues — see the
Architecture section, and `TailFanOutTest` for the assertion that each sees every
line exactly once in either drain order.

The status line reports the window, the threshold, whether the reading moved,
and **whether the host is carrying the channel at all**, because "0 hitpoints in
the last 45 s" reads identically whether the grid is quiet or nothing is
listening. It also now annotates an implausible gauge value in place: #32 was
filed partly on the status line printing `Shield: 385%`, which the retreat guard
had already rejected and never acted on while the log gave every appearance that
it had.

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

## Ammo: the module's own menu says which charge is loaded

`eve-online-mission-runner` swaps between two charges as the current target's
distance changes. **The signal is the weapon's right-click menu, which lists the
charges the gun can be switched *to* and omits the one already in it.** Verified
live: a weapon holding Radio M offered `Multifrequency M [4]`, twice, then Show
Info / Unload to Cargo / Set Auto-Reload Off / Set Auto-Repeat Off / Clear group,
and no Radio M at all. So the charge that is *absent* is the charge that is
loaded — read from the same cascade the swap opens anyway, with no hover, no held
mouse, and no dependency on sprites this build does not have.

That replaced the original design, which read `optimalRange` off a module
tooltip. The tooltip is still read where it can be, as a *refinement*: a weapon's
optimal range moves with the charge, so the midpoint of the two ranges is a
crossover distance the bot can derive rather than be told. But it can only be
obtained by resting the mouse on a module until a tooltip appears, and whether
this client raises one at all remains unverified — so the swap no longer depends
on it.

**Which signal governs which decision** is the distinction to keep straight:

| question | answered by |
|---|---|
| which charge is loaded | menu membership — free, and safe to read at any time |
| did the load land | menu membership on the next read — the charge has gone from the list |
| where to change over | `ammo-swap-range`, else the midpoint of the two optimal ranges |
| may a load be issued *now* | the module's `isActive` and ramp — see below |

### The client refuses a load into a running module, silently

Run 5's own game log:

```
[ 03:41:03 ] (notify) You cannot load or unload Focused Modulated Medium Energy Beam I while it is active.
```

The first version reasoned that a firing weapon is mid-cycle almost all the time,
so gating on the ramp would mean never swapping during a fight — "a feature that
does nothing". The observation was right and the conclusion was wrong: EVE does
not prefer an idle module, it **refuses outright**, so proceeding anyway was not a
way to swap during a fight but a way to issue a command the client discards.

It was invisible because the refusal arrives only as a `(notify)` line and the
bot does not read EVE's game log. Nothing learned the command was discarded, so
it fell through to the swap's own confirmation, found nothing changed, and
retried until the give-up latched the feature off — logging "the swap did not
confirm" when the truth was "the swap was never accepted". It looked intermittent
rather than broken because swaps between engagements landed: run 5 learned both
ranges (16000 and 67000) and completed swaps in both directions.

So the sequence is now **switch the gun off, load, and let the fight switch it
back on**. Three things hold it together:

- **Nothing re-activates the guns but the branch that always did.**
  `decisionToKillRats` already presses an inactive top-row module on a target, so
  the swap simply stops holding the fight and the guns come back by themselves. A
  second re-activation step would be two controllers for one button, which is the
  flicker `manageMiddleRowModules` was split up to end.
- **`ammoSwapIsActingOnAVerdict` keeps the ammo path in control while the guns
  are off**, because it is what switched them off. Without it the entry gate
  ("only act on a ship already shooting") would hand the fight straight back to
  the branch that turns them on again, every reading.
- **The module button is a toggle**, so the switch-off goes through
  `clickModuleButtonButWaitIfClickedInPreviousStep` and its settling window. A
  second click before the client shows the result turns the gun back on.

**Failing to a firing gun with the wrong ammo is always better than failing to a
silent gun.** That is the invariant, and run 8 is what happens when it is left to
individual branches to honour: the ship sat in a hostile pocket with its guns
switched off, repeating one decision 298 times, and would not have recovered on
its own.

It failed in two places at once, which is worth keeping in view because they are
the same mistake at different scales. The wait that ran for 298 readings —
*guns off, ramp still turning* — had no counter at all. And the counter in front
of it, which bounded *getting the guns quiet*, reset whenever no gun **read** as
firing, so a weapon flickering between cycles held it at 1 forever; the log shows
`Silencing for 1 of 8` on all eight readings it appears. A counter that consults
the thing it is waiting out can be stopped by it.

So the bound is now **one deadline over the whole silent period**
(`ammoSwapSilencedGiveUpTicks`), counted from the reading the swap first tells a
gun to stop until it lets go. Two properties make it structural rather than
another branch remembering:

- **It consults nothing the module says about itself.** Its only inputs are
  whether the swap is still holding a verdict and whether the bot has commanded a
  switch-off — the latter read from the step's own effects, because what the bot
  asked for is knowable where what the client did with it is not. This matters
  more since #35: `ramp_active`, which `isActive` reads, was measured returning
  `False` on a module that was switched **on**.
- **Nothing in the acting path waits.** Every state either acts or hands the
  fight back, so no state can sit still while the guns are off. The ramp
  precondition is gone entirely — the load is attempted after a fixed settle
  (`ammoSwapSilenceSettleTicks`, a count, which always ends) and the client's own
  refusal (#31) says if the gun was still running. Being wrong costs one reading;
  waiting to be certain cost run 8 nearly three hundred.

Both are checked in `tools/macos-host/tests/test_ammo_silenced_bound.py` rather
than left as intentions, and verified by mutation: reintroducing either the
module reading in the counter or a `waitForProgressInGame` in the acting path
fails there.

Every other failure abandons the *attempt* and not the feature —
`ammoSwapVerdictGiveUpTicks` if a verdict drags on, the client's refusal if a
load is discarded — so the guns resume and the next change of range tries again.
Three things latch the swap off for the session, because only they should not be
retried: the menu offering neither charge, there being no crossover distance, and
reaching the silence deadline. That last one is the newcomer and deliberately so.
Having disarmed the ship once and been unable to finish, doing it again is not an
optimisation worth the risk.

### Not oscillating

- **The crossover does not move, so the deadband is simple.** It is
  `ammo-swap-range`, or the midpoint of the two optimal ranges once both have
  been seen — a fixed number either way, and with a fixed threshold any positive
  deadband is stable. The original needed an argument about half the spread
  between the two ranges, because its threshold was the *loaded* charge's optimal
  range and therefore moved with every swap. That case survives only as
  `ammoSwapBootstrapThreshold`, which exists to break a chicken-and-egg — seeing
  the second optimal range requires a swap, deciding a swap requires a crossover
  — and carries a much wider deadband for exactly one swap.
- **AU distances are excluded**, not treated as very far. An unparsed distance
  becoming the 999999 placeholder is the input that would argue for long-range
  ammo forever.
- **Several consecutive readings** must agree (`ammoSwapDistanceHoldTicks`),
  because rats die and the "current target" jumps between ranges without the
  fight changing.
- **A verdict that arrives already satisfied costs nothing.** The range re-arms
  every time a target drifts back out through the deadband; without this the bot
  would re-open every gun's menu mid-fight to be told nothing had changed.
- **A half-built menu is not believed.** The design reads *absence* as proof, so
  a menu caught mid-populate would say every charge was loaded at once.
  `ammoSwapMenuEntriesBeforeTrusted` is below any real weapon menu (the five
  commands are always there) and above an empty one.

### The client's refusal, read rather than inferred

Since #28 the bot can read EVE's game log, and the ammo swap is its first
consumer: a `notify` line matching `cannot load or unload` … `while it is active`
sets `loadRefusedByClient`, which abandons the attempt on the spot and quotes the
client's own sentence in the decision log.

**This is not the fix for the refusal — stopping the gun first is, and that
already landed.** It is two other things. It is a *safety net*, for the case
where the deactivation does not take: a click swallowed, the toggle pressed
twice, a module reporting inactive while the client disagrees. And it is
*legibility* — the difference between "the swap did not confirm" twenty-five
readings later and "the client refused the load. It said: …" on the reading it
happened. Only the second is something an operator can act on.

Two things about the matching are deliberate. It tests two substrings rather than
the whole line, because the weapon's own name sits in the middle of the sentence
and a whole-line match would be per-fitting; and two rather than one, because
`cannot` alone catches every other refusal the client makes — across five
recorded runs those were 17 drone-control refusals, 4 "while warping", 2 "while
docking" and 1 module-activation, none of which should touch the guns.
`tools/macos-host/tests/test_ammo_load_refusal.py` reads the substrings out of
`Bot.elm` and checks them against those real lines, so a matcher that drifts from
what the client writes fails there rather than in a run.

The one inference never to make from this channel is the reverse one. No refusal
arriving does **not** mean the load was accepted — that is what the menu says.
An absent game log and a silent client are different answers, and treating them
alike is how a bot concludes a command worked because nothing complained.

### What is verified and what is not

Verified live: the menu's contents and that it omits the loaded charge; the
quantity suffix; the client's refusal to load into an active module; that swaps
land between engagements. Not verified: any of this code running. Watch the
status line's `loaded charge reads` flipping after a swap, and the game log
staying free of `cannot load or unload`. `(notify)` lines are a signal the bot
never reads at all — the host already tails the game log for bounties, so
surfacing "the client refused what we just asked" would turn a whole class of
silent discards into something the bot could react to.

One cross-feature invariant, since this and the learned lock range both read the
previous step's effects. They cannot be confused: the lock chord is Ctrl over a
*left* click, the ammo cascade a plain right click, the module switch-off a left
click inside a module button, and the tooltip hover a bare mouse move with no
button at all. And the hover, which holds the mouse still for several readings,
cannot age a pending lock attempt into a false refusal: a refusal needs the
target bar empty at both ends, and the ammo path only runs with an active target.

## Acceleration gates: a gate that will not open says why, on a channel nobody read

Run 10 raised `askForHelpToGetUnstuck` — the first time in eleven runs — while
the objective's own acceleration gate sat 32 m off the bow with the Selected
Item panel offering `selectedItemActivateGate`. Everything the bot needed was on
screen and it declined to act for 1,325 readings. The explanation had been in
the reading the whole time:

```
[ 2026.08.03 12:56:41 ] (info) This gate is locked! To activate it, you need to have R.S. Officer's Passcard in your cargo hold. By all signs it will not be consumed upon use, so the only problem is to locate the thing!
```

**The mission was unwinnable and the bot could not tell that from being stuck.**
Reconstructed from the log: the bot pressed Activate, the client refused with
that line *and* a modal message box, `closeMessageBox` dismissed the box as
generic noise, and the gate branch pressed again — nine times over two minutes,
alternating `I see an acceleration gate -- D-click it to move to the next
pocket.` with `I see a message box to close.` Then `gateWithinReachTicks` passed
`gateRefusesThisShipTicks` (40) and `activateAccelerationGateIfPresent` began
answering `Nothing`, which is what the log then showed for twenty minutes as
`Nothing to fight and no travel step offered`. The give-up at the bottom of the
tree eventually fired and was right to; it was working from a symptom twenty
minutes downstream of the cause.

**Three things were wrong, and only the third is the one that looks like a bug.**

**The refusal was legible and unread.** The client states this on the `info`
channel — every other consumer of the game log in this bot reads `notify`, so
`gameLogEntryIsFromInfoChannel` had to exist before the sentence could be seen
at all. `gateLockedForWantOfAnItemFromGameLog` matches it and
`BotMemory.gateLockedForWantOfAnItem` carries the client's own sentence forward,
because a reading's entries are gone by the next one. The gate branch then stops
pressing and asks for help *quoting the client*, on the first refusal rather
than the thousandth reading.

**Two "This gate is locked!" sentences exist and they want opposite responses.**
The recorded game logs also hold

```
This gate is locked! There are synchronized gate scramblers on all hostile entities in this area ... you must simply clear the vicinity of enemy ships. So grab your guns.
```

which opens by itself once the pocket is clear, and which the bot already
answers correctly by fighting. So `in your cargo hold` is not a second substring
guarding against a rewording the way #31's pair is — it carries the entire
distinction between a standing requirement the bot cannot meet and a fight it is
already winning. Matching `This gate is locked` alone would stop runs that were
about to succeed. `tools/macos-host/tests/test_gate_locked_refusal.py` pins that
against both real sentences and against every `This gate is locked` line in
`~/Documents/EVE/logs/Gamelogs`.

**The give-up counted the wrong thing, and then said nothing.**
`gateWithinReachTicks` counted readings with a gate inside
`interactionRangeInMeters`, which is not evidence that the gate refuses the
ship — the same error `dronesInSpaceTicks` made about the drone recall. Note
what that costs on the *scrambled* gate above: clearing that pocket is by
definition a long fight next to the gate, far longer than 40 readings, so the
budget would have been spent before the last rat died and the gate left
permanently declined on a grid where it was about to work. It now increments
only where `selectedItemOffersActivateGate` — the client actually offering to
open it and the gate not opening — **holds** its count on a reading in reach
without the offer (the message box between every attempt is one of those, and
resetting there is the shape that pinned `gunsSilencedTicks` at 1 forever), and
resets only when the ship leaves reach.

And the decline itself was silent. Returning `Nothing` is deliberate — it is
what lets the caller's own fallbacks run, and the comment there explains why —
but a `Nothing` cannot carry a decision line, so the log said only that nothing
was happening. `describeAccelerationGate` puts it in the status line every
reading instead: which gates are on the overview and at what range, how much of
the budget is spent, whether the branch has given up, and the client's sentence
if there is one. That is also what makes a two-gate grid visible; the decision
text was printed 135 times without ever revealing that the overview held two
gates at very different ranges, which is what made this take a manual read of
the Selected Item panel to spot. It now names the gate it chose.

**What was investigated and is not the cause.** The issue's first hypothesis was
a consumer taking `List.head` of `overviewWindows` and seeing one of two
windows. All eighteen call sites iterate the full list;
`scrollOverviewToReveal` filters *windows* deliberately, because it needs to
know which one to scroll. Multiple overview windows are a supported
configuration and nothing here depends on there being one. The second was that
the gate was out of range and the approach path of `1fe6439` had failed — the
log shows the ship closing 59 km → 9,565 m → 8,076 m → in reach, shutting the
prop mod down on arrival, exactly as intended.

**The client names the key, so the bot fetches it.** #41 stopped at reporting
the refusal, on the grounds that the objective names no cargo and so
`lootMissionItemFromContainerIfPresent` had nothing to look for. Half of that
was wrong, and the operator's own resolution is what showed it: the passcard was
looted from a nearby wreck and the mission continued. The *objective* names no
cargo; the *client's sentence* names the item outright, and every piece of the
retrieval path — `isLootableFor`, `lootableHoldingMissionItem`,
`scrollOverviewToReveal`, the `prefer-wreck` setting — already takes the item
name as an argument. The only missing piece was the source of that argument.

`gateKeyItemNameFromRefusal` slices it out between `you need to have` and
`in your cargo hold`, `itemToFetchFromTheGrid` offers the objective's cargo
first and the gate key second, and `lootMissionItemFromContainerIfPresent` asks
that instead of the objective directly. Nothing downstream is new.

Three things hold it together, and each is a way it could have gone wrong.

**The right-hand marker is the substring the matcher already pins.**
`gateKeyClosingMarker` is one constant used by both, so an extraction can never
succeed on a sentence the matcher would have rejected — in particular the
scrambled gate, which wants a fight rather than an errand. The left marker is
the whole clause `you need to have` rather than something shorter that happens
to work on the one recorded sentence.

**The name is matched the way every other item name is.** It goes to
`isLootableFor` as a plain substring, punctuation and all —
`R.S. Officer's Passcard` carries two periods and an apostrophe, and a second
matching rule invented for them would rest on one observation. What that costs
is worth knowing: the *named container* branch only fires when an overview row
literally contains the name, and a wreck's row carries the dead ship's name, so
a key inside a wreck is found by the blind wreck-opening branch — exactly as for
every other mission item that comes out of something destroyed.

**The verdict lets go when a container is emptied.** Otherwise one refusal
decides the rest of the session: the key goes in the hold and the gate is never
asked again. Emptying anything clears it, the gate is pressed again, and if it
is still locked the client says so again and the verdict re-latches on *that*
reading — never on the strength of a verdict formed before the loot. The loop
terminates for the reason `lootableHoldingMissionItem` already documents: each
container emptied drops out of the candidate list, so the search shrinks, and
when it is exhausted the gate branch asks for help **naming the item it was
looking for**. `containerEmptiedThisReading` is one definition read by both
`lootedWreckIds` and the verdict, because two copies of "was this just emptied"
would drift silently in both directions.

**Unverified.** The loot-then-retry sequence has never run: it needs a live
mission that locks its gate, and none has been flown since. What is checked
off-line is the extraction against the real sentence and against the scrambled
one, that the key reaches the picker, that the verdict is forgotten on a loot,
and that the give-up names the item — but the *rule* is mirrored in Python
rather than executed, since the function is not exposed from the `Bot` module
and this suite reads Elm as text. Nor is a second gate on that grid confirmed
from the log; the 25 km row in the issue is an operator's live read, and if it
was a working gate then trying the next-nearest gate after one is refused is
still the follow-up.

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

The travel half of it is now shared. `travelToStationByName` is the route-set,
fly, dock sequence, and both the restock trip and the pod recovery below call
it — the callers differ only in the two log lines they hand it, because the
*reason* is what an operator reads and the mechanism is not something this bot
should have two of.

## Losing the ship: the client never says so, and a capsule reads 100%

Run 7's ship was destroyed mid-mission and the bot carried on for the whole of
the next 86 readings flying **the capsule**, at 0.0 m/s, among the Sansha pack
that had just killed it — reporting `Shield: 100%  Armor: 100%` the whole time,
because that is what a capsule reads. It was stopped by hand and the pod flown
out manually. A stationary pod in a hostile pocket is a podding, which costs the
clone and its implants, usually more than the ship.

**EVE does not announce the loss.** Issue #33 assumed it did, and #30 having
just landed the game log made that look like the clean signal. It is not there.
Across every recorded game log in `~/Documents/EVE/logs/Gamelogs` there is no
"destroyed", no "podded", nothing about the hull at all — run 7 reads as the
last `(combat)` line at 04:26:59 and then silence until:

```
[ 2026.08.03 04:27:33 ] (notify) The ship you are piloting does not have targeting systems installed.
```

repeated 173 times to the end of the run. So the client states the
*consequence*, not the event, and only when something asks the capsule to lock.
Do not go looking for an announcement; a matcher for one would never fire, and a
guard that never fires is indistinguishable from a bot that is fine.

**Two signals, and the two that were expected to work do not.**

| signal | verdict |
|---|---|
| the `(notify)` capsule refusal | **used.** Arrives on a carried channel — the withheld ones are `(combat)` and `(bounty)`, and a destruction line would almost certainly have been on `(combat)` |
| ship UI with no module buttons at all | **used**, after 3 consecutive readings |
| the drones window disappearing | **rejected.** Run 1 printed `No drones` on 8,076 in-space status prints while flying a perfectly good ship |
| hitpoints | **rejected.** A capsule reads 100/100, and #32 shows the reading is untrustworthy anyway |

The module signal's discrimination is measured rather than assumed:
`Middle-row modules: none.` appears on all 724 of run 7's in-space status prints
and on **zero** across runs 1, 3, 5 and 8 — 4,419 readings, 15,836 in-space
status prints, every one naming a propulsion module. Mind the unit: those are
prints, not readings, and the counter that decides the verdict is stepped once
per *reading*, in the memory update. Three readings rather than one because the
parser drops any slot whose display region it cannot read (see "Ship modules"),
so one reading finding none may be a parse that missed.

One step in that is inferred rather than observed. The status line prints the
middle row only; a non-empty middle row proves `moduleButtons` was non-empty,
which is the direction that governs false positives. A capsule having no module
buttons in *any* row follows from a capsule having no slots — plausible, and
consistent with run 7's `ShipUI` text, but not directly measured. If it is wrong
this signal simply never fires and the capsule refusal carries the guard alone.

**The verdict latches, and it is written in
`updateMemoryForNewReadingFromGame`.** Both are forced. A reading's game log
entries are gone by the next reading, so a branch that recognised the refusal
where it acts on it would see the loss once and go back to flying the mission —
the failure #30's own follow-up names. And the latch never clears, because the
cost is asymmetric in one direction only: docking early costs the rest of the
session, un-concluding a loss on a reading that happens to look normal costs the
clone.

**The response is placed rather than enumerated.** `recoverPodAfterShipLoss`
sits above the wind-down and above the docked-or-in-space split in
`missionBotDecisionRootBeforeApplyingSettings`, so "stop fighting" is structural:
locking, module activation, approach and looting all live below that split and
are simply never reached. Then it flies to `home-station` if one is set, docks at
whatever the surroundings menu offers if not, and **ends the session** — the
remaining hours are worth nothing without a ship, and the operator has to find
out. `podRecoveryGiveUpReadings` (150, about twenty minutes at the eight seconds
a reading the recorded runs average) bounds it and ends the session saying the
pod is still in space, for the same reason every other bound here exists.

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

  It now also **shoots back at whatever the client says is shooting it**, rather
  than only at what the overview colours as a rat or an operator remembered to
  name — see "What the bot is willing to shoot" for the evidence that the combat
  log's attacker name and the overview's Name are the same string, for why the
  set is accumulated per reading rather than carried as a list by the host, and
  for the two cases deliberately left out (an optional-clearing briefing, and a
  webifier that deals no damage). **Untested against a live client**: the
  matching, the bounding and every existing guard it has to keep are unit-checked
  against the recorded runs, but no run has yet engaged anything this way. What
  to watch is the status line's `Attackers named in the window:` clause carrying
  names that the overview also shows — a window naming attackers while no
  `Shooting back at` line ever appears means the two strings are not matching
  after all, which is the failure this whole change would fail silently as.

  It also **recognises that the ship has been destroyed and flies the pod out**
  rather than continuing the mission in a capsule, which is what run 7 did for
  86 readings. Detection, the two signals that work and the two that do not,
  and where the guard sits are in "Losing the ship" above. **Untested against a
  live client**, and deliberately so — staging a real loss is not worth it. What
  is checked without one: the matcher is read out of `Bot.elm` and asserted
  against run 7's real line and against fourteen other `(notify)` lines the
  client wrote, and the module-row discrimination is recounted from the recorded
  runs. What to watch on the first real loss is the status line's `SHIP LOST:`
  turning up within a reading or two of the last `(combat)` line, and then
  `Pod recovery:` reaching a dock. If the verdict never arrives, the thing to
  check is whether `shipUI.moduleButtons` is genuinely empty on a capsule — the
  recordings show the *middle* row empty on every capsule reading, and every row
  being empty is the stronger form of that, inferred rather than observed.

  And it now **stops fighting once the tracker says `Dock`** with the objective
  carrying no instruction, instead of clearing the field first — run 11 spent ten
  minutes and 386 combat decisions doing that after the mission was over. The
  conditions that still keep it fighting, and why leaving beats shooting back,
  are in "When the tracker says Dock, the fight is over" above. **Untested
  against a live client**; the two pure rules behind it are run through the real
  `Bot.elm` in `elm repl`. Watch for `The objective is complete and the mission
  tracker says 'Dock'` arriving within a reading or two of the label, rather than
  another stretch of `I see a locked target`.
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

  It also carries **how much damage the client says arrived since the last
  reading**, as `incomingDamageSinceLastReading`, summed host-side from the
  `(combat)` lines the channel proper withholds. That is the mission runner's
  retreat that depends on no HUD gauge — see "Retreating: the HUD hitpoint gauge
  is the weakest instrument here" for the calibration and for what run 7
  actually was.

  Verified without a live client: 24 unit tests in
  `tools/macos-host/tests/test_incoming_damage.py` covering the
  incoming/outgoing split against real recorded lines, the tail's third fan-out
  in either drain order, present-with-zero against absent, the node's safety
  properties, the six vendored parser copies, and the calibrated constants read
  back out of `Bot.elm` and `run_mission.sh`. Confirmed by mutation: collapsing
  `from` and `to` fails two, renaming the type name in one parser copy fails
  two, and moving either threshold off its measured value fails one each. The
  Elm half was driven end to end off-line through the real vendored parser — a
  host-built reading double-encoded as the real one is gave back
  `Just { damage = 4101, hits = 63, topAttacker = Just "Centum Fiend" }`,
  `Just { damage = 0, ... }` for a quiet reading, `Nothing` for a host without
  the channel, and `getAllContainedDisplayTexts` empty even with the attacker
  named "No room for more".

  **Four consumers now, and none has been proven live.** #31's ammo-load
  refusal (`loadRefusedByClient`), #33's capsule refusal (`shipLossFromGameLog`),
  #41's locked acceleration gate (`gateLockedForWantOfAnItem`) and #32's
  damage-rate retreat, the last reading the summary rather than the
  lines. All four take the same three parts a consumer needs: a
  match on the channel and the client's own wording, a `BotMemory`
  field to carry the verdict (a reading's entries are gone by the next one, so a
  branch that does not record what it saw sees it once), and a live run that
  provokes the line. A run in which the line does not occur proves only that
  nothing broke.

  **The channel is not always `notify`.** #41's line arrives on `info`, and
  three consumers reading `notify` had made that look like the channel this
  bot's refusals come on. Check which one carries the sentence, against the
  recordings, before copying an existing matcher — a filter on the wrong channel
  is a guard that can never fire, and looks exactly like a client that never
  complains.

  Worth knowing what the two consumers found the channel to be good and bad at.
  Good: it states things no HUD sprite does, and the timestamp/channel split
  means neither matcher had to parse a line. Bad: it says far less than expected.
  #33 went looking for a ship-destruction announcement and there is none — see
  "Losing the ship" — so a consumer's first job is checking that the client
  actually writes the sentence, against the recordings, before building on it.

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
- **The acceleration-gate path does not filter on `_display`**, which
  "Reading the overview" says every path that acts on a row must. A hidden row
  keeps a plausible region belonging to whatever was recycled into its place, so
  the nearest "gate" could in principle be a phantom and the click land on
  something else. Left alone deliberately while fixing #41: it explains nothing
  about run 10 (the rows there carried no `_display` key at all, which reads as
  shown), and adding the filter on its own would make a gate scrolled out of
  view invisible rather than mis-clicked — the loot path pairs the filter with
  `scrollOverviewToReveal` and the gate path has no such pairing. Both halves
  together, on a run that can be watched.
- **The gate key is fetched but the fetch has never run.** #44 wired the item
  the client names into the existing loot path, so a locked gate now sends the
  bot looking for its key rather than straight to asking for help. Nothing has
  watched it: it needs a live mission that locks its gate. The first run that
  does should show `looking for '<item>'` in the status line, then the ordinary
  `Open the container` / `Look inside` decisions, then the gate taken — and if
  the key is not on the grid, one give-up naming what it could not find.
- The ammo swap, the ship-loss guard and the locked-gate verdict are the only
  consumers of
  `gameLogEntriesSinceLastReading`'s *lines*, so every other guard that infers a
  refusal indirectly still does. The candidates the recorded runs actually
  contain: `You cannot launch Acolyte I
  because you are already controlling 5 drones` (17 occurrences — the drone
  launch retries blind), `You cannot do that while warping` and `while docking`
  (6 between them), and `You cannot activate that module as the target is no
  longer present`. The learned lock range is a fourth: `You are already managing
  N targets` would separate "no free slot" from "too far" outright, where today
  it is inferred from the target bar being empty at both ends of an attempt.
- **A run cycled inside a mission pocket leaves the ship unattended for
  minutes.** `run_mission.sh` kills the previous bot before the new one compiles,
  and the slow `elm make` path takes several minutes; that gap is when run 7's
  ship died, with 9,286 hitpoints of incoming fire landing between the old run's
  last log line and the new run's first reading. Nothing inside the bot can see
  that window. Dock or clear the grid before cycling.
- **Looting has not been asked the question `Dock` was asked.** Once the tracker
  says `Dock`, combat stops (see "When the tracker says Dock, the fight is
  over"), but the looting branch keeps its old place under the fight and is
  simply skipped along with it. That is right for ordinary salvage and wrong for
  a wreck holding the mission item, and the two are not distinguished today —
  `isNotableWreck` only asks whether a wreck is worth looting.
- The damage-rate retreat's latch clears when nothing has hit the ship for a
  whole window, so a bot driven out of a pocket will be brought back into it by
  the mission logic and driven out again. Survivable, and better than the
  alternative it replaced, but it is a loop and it has not been seen live.
- **A webifier that deals no damage is still invisible to the bot.** #40's
  attacker set is built from the combat log, and an EWAR module that applies no
  damage writes no line there. The overview row carries the answer — the client
  renders "Pilot is webifying me" on it — but that string occurs in none of the
  recorded runs, so there is nothing to derive a matcher from without a live
  reading. The status line now prints the rendered rows'
  `rightAlignedIconsHints`, so the next run that meets one records the literal.
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

## How a change is verified here

This project's signature bug is code that reports success and does nothing, and
a green compile has now let three of them ship: a maintenance task whose guard
could never be true (#15), a bound whose counter could never reach it (#34), and
a matcher on a channel nothing read (#42). Compilation says the code is
well-typed, not that it can run. The habits below are what caught the next ones,
and they are cheap.

**Mutate the code and watch a test fail.** A test that passes is not evidence
until you have seen it fail for the right reason. Breaking a matcher's literal,
pinning a counter at a constant, or removing a branch from a decision list
should each break a named test. This found a real hole: `test_ammo_silenced_bound`
asserted what the counter *mentioned* and would have passed with the counter
pinned at `1` — which is exactly the defect it existed to prevent. It now
asserts every branch evaluates to `0`, `1`, `previous`, or `previous + 1`.

**Execute Elm rather than mirroring it in Python.** The test suite is Python and
reads `Bot.elm` as text, which is fine for structure and a trap for behaviour: a
Python restatement of a rule tests the restatement. Any pure function can be run
for real in about two minutes —

    cp -R implement/applications/eve-online/eve-online-mission-runner /tmp/chk
    # collapse `module Bot exposing (State, botMain)` to `module Bot exposing (..)`
    # set elm.json's "elm-version" to "0.19.2"
    cd /tmp/chk && printf 'import Bot\nBot.someFunction "..."\n' | elm repl

Used to confirm gate-key extraction (#45), the `Dock` conditions (#49), and that
a non-text travel label is declined (#49). A NUL cannot appear in an Elm string
literal — rebuild such input with `Char.fromCode`.

**Assert client text against recorded logs, not against memory.** Where the bot
matches something the client wrote, read the literal out of the source and check
it against real lines in `~/eve-bot-logs`. A matcher that drifts from what the
client actually writes fails in the direction that looks like success: nothing
matches, the branch never fires, and nothing complains. The same trick pins
cross-language couplings — the Elm synthetic-node type name against the host's
constant (#30), the parser block byte-identical across all six vendored copies
(#39).

**State reachability, not just correctness.** For every guard, say what makes it
*true* in the state the code runs in. "I traced the path forward from this state"
does not establish that the state can be entered, which is precisely how #34's
bound shipped unreachable.

**Distinguish absent from false.** `ramp_active` is missing until a module has
cycled, and `Nothing` from the game log means "no game log on this host" while
`Just []` means "the client said nothing". Collapsing either with
`Maybe.withDefault` gets the unsafe inference for free.

## Repo state

`origin` = `Viir/bots` (upstream, untouched); `fork` = `smerwin/bots` (personal,
added with `git remote add` — `gh repo fork --remote` reported success but did
not actually add it). Work is committed and pushed to `fork` `main`.

Root `.gitignore` excludes `.DS_Store`, `__pycache__/`, `*.pyc`, and the
ad-hoc-signed compiled tool binaries (`probe`, `memory_sample`, `tree_walker`,
`live_reader`, `window_probe`, `cg_input`). Each has adjacent `.c` source;
binaries are platform-specific build output, so a fresh clone must rebuild them —
e.g. `clang -O2 -framework ApplicationServices -o cg_input cg_input.c`.
