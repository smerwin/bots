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

Two protocol details worth remembering. `ReadFromWindowResult.Completed
.memoryReadingSerialRepresentationJson` is `Maybe String`, and the UI tree JSON
inside it is **double-encoded** — a JSON string containing JSON, decoded via
`decodeMemoryReadingFromString`. And each cycle issues **two parallel reads**:
the memory-based `ReadFromWindow` *and* an `InvokeMethodOnWindowRequest
ReadFromWindowMethod` (screenshot-based, returning `windowRect`/`clientRect`/
`clientRectLeftUpperToScreen`/`imageData`). The latter supplies the rect that
translates memory-read UI positions into screen coordinates, so both are needed.

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
(`askForHelpToGetUnstuck`, never normal), or the same decision repeating 60
times. That threshold is calibrated against 55 past runs, where runs of ≥80
identical decisions are 0.74% of all decision runs — comfortably above ordinary
waiting and below the real pathologies, the worst of which reached 8,983 repeats
of "I see a message box to close". It screenshots the game **window by id**
(`screencapture -x -o -l`), not the screen, because the client is usually on
another macOS Space where a screen grab catches the wrong desktop.

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
against the first one's arrival distance. `APPROACH_PATIENCE` (60 decisions)
bounds it in both directions: a ship gets that long from first sighting, or from
its last gain, to show it is closing, and a ship that has genuinely stopped is
caught that much later than before rather than not at all.

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
lines are per shot, not per kill, and are no use for a kill count.

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

  **Untested against a live client.** It compiles and the parser now sees
  `ShipItemCard`, but nothing here has been watched running: it needs a docked
  ship with an empty bay and the drone in that station's root item hangar. The
  failure to watch for is the one `reload_drones.py`'s header names -- an
  inventory not anchored to the ship accepts the drag, shows the quantity
  dialog, and moves nothing. The bot's only evidence that its "Open Drone Bay"
  landed is the drone bay showing as the selected container
  (`droneBayOpenedFromShipCard`), which it remembers until the ship undocks;
  a client left with that container selected some other way would fool it.
  Read the decision log for the `Maintenance:` lines and check the drones
  window afterwards rather than trusting them.
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
  Name resolution is verified both ways; the authenticated half is untested
  pending a browser login. Note `/universe/ids/` does not index every NPC
  station — the agent's own "Amarr VI (Zorast) - Moon 2 - Theology Council
  Tribunal" comes back empty from it — so the tool falls back to resolving the
  system from the name's first token and enumerating its stations.
  ESI covers navigation only: CCP exposes no endpoint to request, accept or
  complete an agent mission, so the conversation stays UI automation either way.
  The search-bar route below needs no registration at all and is the fallback.

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
`_VK_TO_CGKEYCODE` — a hyphen in a query silently has no key to press.

## Open gaps

- `dictEntriesOfInterest` doesn't recursively encode non-primitive "interesting"
  values the way Sanderling's serialisation does. `getDisplayText` in
  `ParseUserInterface.elm` falls back to decoding a non-string `_setText`/`_text`
  as *another full `UITreeNode`* — a real case, since it can hold a Python `Link`
  whose own `_text` has the actual text. Symptom seen live: "current solar
  system: Unknown" for a name that isn't a plain string in memory.
- `MouseMoveRelative` and `CharacterDown`/`CharacterUp` (raw Unicode text input)
  aren't implemented in `botlab_host.py`.
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
