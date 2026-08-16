# Project: macOS-native EVE Online bot host (no BotLab.exe / reactor.botlab.org)

A macOS-native replacement for the closed-source `BotLab.exe` "volatile host",
so the Elm bots in `implement/applications/eve-online/` run on Apple Silicon
without the Windows client and without reactor.botlab.org (BotLab's paid
licensing backend). Non-commercial, not for distribution.

**Status: working.** The host runs unmodified Elm bot source end to end against
the live client — real memory reads, real decisions, real mouse and keyboard
input. Remaining work is refinement, not architecture.

## Start here

**Picking up a session cold — resuming after a context clear, or taking over a
run someone else started — is `PILOT.md`.** This file is the facts about the
client, the bot and what has been learned about both; PILOT.md is the procedure
for operating them: what to check first, how to start a run without silently
losing its settings, what to watch, how to tell a real stall from noise, and how
to hand back. Read it before touching a running session.

The short version of it, for orientation:

```
cd tools/macos-host
./cycle_run.sh --status                 # is a run going, and which log
ls -lt ~/eve-bot-logs | head -3         # runs, newest first
gh issue list --repo smerwin/bots --state open
```

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

So the Elm side of this was **blocked on a channel that did not exist**.
`OperateBotConfiguration` gives a running bot exactly one way out —
`buildTaskFromEffectSequence : List EffectOnWindowStruct -> Task` — and that
vocabulary is mouse moves, buttons, keys and scroll; a station name cannot be
spelled in it. Every `RequestToVolatileProcess` is issued by `getNextSetupTask`'s
closed setup state machine, which a decision cannot reach. Issuing this *request*
from a decision therefore still means changing `BotFramework.elm` (a new
`OperateBotConfiguration` field and a builder beside
`buildTaskFromRequestToVolatileProcess`) *and* the vendored decoder.

**Nothing has to.** #68 needed a bot to tell the host something the protocol has
no type for and solved it the way #30 solved the game log — by riding a field
that already crosses the boundary. `ContinueSession.statusText` is free prose the
host reads every tick, so the bot writes a directive into it and the host scans
for a token that ordinary prose cannot produce:

```
@host extend-session 480
@host set-destination Amarr VIII (Oris) - Emperor Family Academy
```

`hostDirectivePrefix` in `Bot.elm` is the token both sides agree on, pinned by a
cross-language test in each direction — a drift is silent, and reads exactly
like a bot that never asked. The channel is **one-way and unacknowledged**, which
is a property rather than a limitation: the bot's confirmation that a route was
set is the client's own route panel, which is stronger evidence than the host's
report of what it asked for. The status text is also *printed*, on every reading,
so a station name may travel this way and a credential may not.

An upstream-sourced bot simply never writes a directive, exactly as it never
asks for a deadline extension, so the asymmetry #17 rejected does not arise: the
host side existed and was merged first, and the cost of a bot that does not use
it is zero.

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
`MacOsHostSyntheticGameLogEntry` child per **entry** carrying `timestamp`,
`channel` and `text`, and `ParseUserInterface.elm` lifts it into
`ParsedUserInterface.gameLogEntriesSinceLastReading : Maybe (List GameLogEntry)`.

**An entry is not a line, and reading it as one cost half of every wrapped
message.** The client puts the `[ timestamp ] (channel) ` prefix on the first
physical line of a long message and on none of the rest, so `parse_game_log_line`
answered `None` for the continuations and `_poll` dropped them — issue #124, and
113 times in run 35 the bot was handed a `(question)` standings-penalty warning
with `Do you wish to proceed?` cut off the end of it. **The loss was in the
parser, not the capture**: the continuations reached the echo, which is why the
recorded runs contain them and the fix could be measured before it was written.

A prefix-less line now continues the entry above it, and the client's own logs
are what say that rule is safe rather than merely plausible. Across the 214,630
lines in `~/Documents/EVE/logs/Gamelogs`, not one prefix-less line begins with
`[`, so no continuation can pass for a new entry — the half #124 flagged as
unverified. The wrapping goes deeper than the bot-run corpus shows (138 entries
of two lines, 7 of three, 3 of four), so nothing counts to two. And the only
prefix-less lines that are *not* continuations are the header block a file opens
with, all 143 of which sit above their file's first entry, so a rule phrased as
"continues the entry above it" declines them by having nothing to continue.
There is no wording those share that a continuation could not also have, which
is why the rule is about position rather than about the line.

**The continuation is appended to `text`, not carried as a fourth key**, because
`ParseUserInterface.elm` reads exactly three and does so in six vendored copies —
a new key is six Elm edits before a decision can see the second half of a
sentence. Every consumer of this channel is a substring test over `text`, so
appending can only widen what matches and can never break a match that used to
happen; checked over the whole corpus rather than assumed, where folding leaves
the entry count, every timestamp and every channel identical, changes the text of
exactly the 113 wrapped entries, and leaves `loadRefusalFromGameLog`'s matches and
both damage summaries byte for byte as they were. Nothing wraps on `(combat)` or
`(bounty)`, so the damage half of this channel is untouched.

The one thing this does not do is hold an entry back waiting for a continuation.
`GameLogTail` carries the open entry across polls, so a wrapped entry split
between two reads still arrives whole, but a drain hands the entry over as it
stands — delaying a refusal until the client says something else would be worse
than losing a clause. So a wrap whose halves fall either side of a *reading* is
delivered as its first half, and the rest is dropped rather than becoming an
entry with no timestamp and no channel.

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

**And the other direction is a third node.** Issue #90 needed the half that was
matched nowhere: `MacOsHostSyntheticOutgoingDamage`, one child per target
carrying `name`, `hits` and `damage`, lifted into
`ParsedUserInterface.outgoingDamageSinceLastReading`. It is per target rather
than one total, unlike the incoming node, because the question it answers is
about one object — see "What the bot gives up on: shots that land and achieve
nothing". Its `Nothing` points the opposite way from the retreat's: a host that
cannot answer must not read as "everything is immune".

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
four queues — the echo, the entries, and one per damage direction — because the
stderr echo consuming the lines is exactly what kept them from the bot in the
first place, and a second caller of a single-cursor tail would have given
whichever ran first that cycle's lines and the others nothing, intermittently
and without a word.

**`ParseUserInterface.elm` is vendored six times, and the policy is all six,
identically.** Nothing in this parser is app-specific, and a change that lands
in one copy while the others silently lack it is its own bug.
`BotFrameworkSeparatingMemory.elm`'s `previousStepsEffects` was the one
deliberate divergence, mission-runner only; it is no longer one, because it was
never app-specific — saxrat's drone recall is exactly the shape that needs it
(see below), so the port closed the divergence rather than widening it, and
`test_saxrat_ported_guards.py` compares the two copies byte for byte. The
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

## The other documents

| file | what it is for |
|---|---|
| `PILOT.md` | **operating a session** — resume cold, start a run, watch it, triage an alarm, hand back. The procedure; this file is the facts |
| `MACOS.md` | setting the host up from nothing: SIP, permissions, building the native tools, running a bot for the first time |
| `REPL.md` | driving the client by hand through `eve_repl` |
| `HOTAS.md` | pinned sketch: flying the client with a stick and throttle |

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
| `cg_record/` | passive **listen-only** `CGEventTap`, the mirror of `cg_input`: one line per mouse or key event on stdout, in the same screen points `cg_input` takes. Needs the same Accessibility grant, and says so on stderr rather than recording nothing when it lacks it |
| `action_shape.py` | records the *shape* of manual actions rather than their coordinates -- resolves each click against the UI tree to "the overview row of typeID N", "the menu entry containing 'Warp to'", "`selectedItemWarpTo`" -- then collapses a right-click-then-menu-entry pair into the one cascade it is, and emits an Elm **sketch**. `self-test` and `resolve` run anywhere `eve_repl` does; `record` is macOS-only since it drives `cg_record` |

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

**`--web-console [PORT]`** (default port 8787; `run_mission.sh` now passes it on
every run, so it is on unless you are calling `botlab_host.py` directly) serves a live
console: session stats, the log as a filterable stream, an editable settings
box, and pause/resume/stop. `./run_mission.sh --web-console` works as-is, since
the launcher already forwards `"$@"`.

It binds to this machine's **Tailscale address and nothing else**, and **refuses
to bind** if no 100.64.0.0/10 address can be found rather than falling back to
a wider interface — the console can change what the bot does and stop it, so
guessing wrong means publishing a remote control. Tailscale is the
authentication; there is no login of its own, which is exactly why the bind must
stay narrow.

That refusal used to abort the whole run, which stopped mattering the moment the
launcher started passing the flag on every run: a tailnet that happened to be
down would have killed every session after compiling and before the first
decision. `NoTailnet` is now caught, logged as `WEB CONSOLE NOT STARTED`, and
the run continues without a console. The safety property is unchanged — it still
never binds anywhere else — and the warning is loud because a console silently
absent is worse than none, since the operator goes looking for one.

### The console says which bot it is driving, and what that bot was built from

Its title and heading were the literal string `Host Console` and `ConsoleState`
carried no notion of a version, so neither the page nor the log said which of
the two bots was running or what code it was running — while the *log* printed
the same `# bot source:` path on every run this machine has ever flown, as the
code underneath it moved constantly. Seven consecutive runs flew five different
trees (`655053c`, `776a202`, `bfbe090`, `ab7bae7`, `1b7c731`), and establishing
which took reading git ancestry and grepping the compiled `bot.js` for string
literals — a method that is itself a trap, since Elm strips doc comments at
compile time, and it produced a confident false negative before it was caught.

Three things now travel together: the app's own name (the bot directory's leaf,
`eve-online-mission-runner` against `eve-online-saxrat`), the source path, and a
version stamp. The name is in `<title>` so two consoles open at once are
distinguishable tabs, all three are in the console header, and the version is
printed to stderr beside `# bot source:` — the log is where "which code did this
run fly" gets asked afterwards, and it outlives every console.

**The version is the part that had to be got right, and `git rev-parse HEAD`
alone is a wrong answer that looks like a right one.** It would be
commit-shaped, authoritative-looking, and wrong in two directions this repo has
already paid for:

- **The host compiles the working tree, not a commit.** `prepare_build_dir`
  copies `bot_dir` as it stands and `elm make` builds the copy, and the mission
  runner is edited while runs are in flight, so a clean-looking SHA beside
  modified sources describes something that never ran. Dirtiness is judged over
  the **bot source directory** rather than the whole checkout — that directory
  is what gets copied, so an edit to the host or to a test elsewhere changes
  nothing about what this bot compiled — and untracked files count, because the
  copy takes them too.
- **The commit may exist nowhere but this machine.** Run 29 flew `776a202`, a
  local revert never pushed, and a reader handed that SHA cannot resolve it
  against anything. Reachability is asked of the remote-tracking refs this
  machine holds (`git branch --remotes --contains`), which is local and needs no
  network; a fetch that has not happened can make a pushed commit read
  LOCAL-ONLY, which understates rather than overstates what a reader can go and
  look at.

So the four states read:

```
1b7c731 (clean, on a remote-tracking branch)
1b7c731 (DIRTY, on a remote-tracking branch)
776a202 (clean, LOCAL-ONLY)
unknown (not a git checkout)
```

**Absent evidence is never dressed up as a finding**, which is
`loadRefusalFromGameLog`'s register applied to a version string. `fetch_bot_source`
takes a plain directory as readily as a GitHub URL, so "not a git checkout" is a
supported answer rather than a failure; a git that cannot be started or that runs
past its timeout is `unknown (git could not be run)`; and either half alone can
be unknown (`dirtiness unknown`, `remote reachability unknown`) rather than
taking the reassuring default. **Nothing here can fail a launch**: every git call
is bounded by `BOT_VERSION_GIT_TIMEOUT_SECONDS` (5s, because a hung git would
hang the launch behind it) and the whole computation is wrapped, so the worst
case is a bot that starts without a stamp rather than a bot that does not start.

Verified in `tools/macos-host/tests/test_bot_source_version.py` (22 cases), and
the git cases are *executed* rather than described: each builds a real throwaway
checkout shaped like this one and runs the real `git`, because a Python
restatement of "is this tree dirty" would only test the restatement. Confirmed by
mutation, twelve of them, each failing a named case: dirtiness always reading
clean, dirtiness judged over the whole repository, a commit on no remote-tracking
branch reading as pushed, an unanswerable question taking the reassuring default,
a git that cannot be started raising instead of degrading, the catch-all removed,
the timeout removed, the stderr line dropped, the version computed from the
host's own location instead of the bot's, the console not told the app name, the
snapshot dropping it, and the page no longer naming the tab.

**Unverified: the page itself.** No browser has rendered the new header — the
console's markup is checked as text, not opened — and no run has been started
since. What to watch on the first one is `# bot version:` on stderr immediately
under `# bot source:`, then the tab reading `eve-online-mission-runner — Host
Console`. A stamp reading `unknown` on a run launched from this checkout would
mean the version is being computed against something that is not the bot's
source directory.

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

### Strings and identities read off a live client

Captured during a saxrat run on an **armour-tanked Coercer** -- a much smaller
hull than the battlecruiser most of this file is calibrated on, which is what
makes several of these separate.

**`Pilot is in your fleet`**, on `FlagIconWithState` nodes inside local chat
rows (`XmppChatUserEntry`). The parser already lifts it, per pilot, as
`ChatUserEntry.standingIconHint` (`ParseUserInterface.elm:483`). It is **not**
on the overview row: five rows were checked and none carried a
`rightAlignedIconContainer` hint at all. That matters because
`getNamesOfOtherPilotsInOverview` already reads exactly these chat rows to build
its names, so excluding fleetmates is a filter on a list the function already
holds -- see #224.

**`Pilot is tracking disrupting me`**, in an overview row's own cell text. The
open gap below said the EWAR hints "appear nowhere in the ten recorded runs";
this is one of that family, captured. **That gap is closed for this one and for
the dampener** — the corpus now carries five distinct EWAR literals and #231
matches two of them, off the strings `Overview indications:` recorded rather
than off a guess. `Pilot is webifying me` is in the corpus too (306 readings
across 5 runs) and is still **unread**, which is now a scope decision rather
than an absence of evidence: a webifier makes the ship slow rather than unable
to fight, so #231 leaves it and the painter alone.

**Overview rows carry three ids in `dictEntriesOfInterest`**, and the parser's
`objectItemID` is its own name for the first -- there is no dict key spelled
that way, which is worth knowing before reading for one:

| key | what it is |
|---|---|
| `itemID`, `stateItemID` | the **instance**. What `overviewEntryLockHandle` attributes a lock outcome with. Gone by the next session -- that rat is dead |
| `typeID` | the **kind** of object. Survives sessions, and is what "I clicked a Centior Abomination" actually means |

Which of the two a consumer wants is decided by whether it is reasoning about
*this* object or about a class of them, and they are easy to confuse because
both are unique-looking integers on the same node.

**The overview's icon colour is on the row**, as `iconSprite` colour
percentages under `mainIcon` -- the mechanism `iconSpriteHasColorOfRat` already
uses. Live, every rat read
`{'aPercent': 100, 'rPercent': 100, 'gPercent': 10, 'bPercent': 10}` against
white and yellow for the stargates and the sun. **The purple a fleet member
draws is still uncaptured**, because none was on the overview during the read --
so a fleet test built on colour today would be guessing an RGB triple, which is
the same trap as guessing a string.

**The damage-rate retreat has now fired, for the first time on either bot.**
This file records it as having fired "not once on the damage window" across 36
runs, every retreat having come from a gauge. On this Coercer, with
`run-away-incoming-damage-threshold` at 900:

```
+ The client's combat log says this ship has taken 919 hitpoints in the last 45 s,
  against a threshold of 900. Get out -- this does not depend on the HUD gauge.
```

The attacker was `Tower Sentry Sansha I`, a sentry, which neither misses nor
stops. **Raising the threshold to 1000 did not stop it firing** -- peak window
1294 afterwards -- so on a hull this size a sentry site crosses any threshold
that is still a guard. What the operator wanted from it was the retreat itself:
warp off, let the repairer cycle, come back, since the tower cannot follow.

**The armour gauge on this hull is corrupt at a high rate, and the filtering
holds.** Ten consecutive live samples of `armorGauge._lastValue` gave `67.5766,
1.0, None, None, 0.99, 1.0, 0.98, 400288.0, 0.99, 0.5412` -- three impossible or
absent out of ten. Over the run the bot printed 1,745 armour values, minimum
**-213%**, maximum **40,028,800%**, and one large enough to overflow a 32-bit
int (43,158,732,982,400). **97 of those prints read below the 80% threshold and
the guard fired once**, which is `plausibleHitpointsPercent` and `believed`
doing precisely what they were built to do, measured rather than assumed. The
shield read 0% throughout while the armour read 99%, so this is a second hull
confirming that the shield is a fuse rather than a buffer and that
`run-away-shield-hitpoints-threshold-percent` belongs at `-1`.

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

### A briefing nobody read is not a briefing that said "clear them"

Run 32 lost a whole session to the mission the matcher above names by name.
`Recon (1 of 3)` was accepted in run **31**; run 32 was cycled onto it
mid-flight, clicked `Accept the mission` zero times across its 784 readings, and
spent all 2,861 of its decision blocks trying to kill eleven cruisers on a
pocket whose briefing says in writing that destroying them is not a requirement.
The operator stopped it and flew the ship out by hand.

**The matcher is not the bug.** `briefingSaysClearingIsOptional` matches both of
the client's wordings and, run against every mission briefing the recordings
hold, reads exactly one of them as optional — this one. It never ran, because a
briefing is readable only while the agent conversation is open, and run 32 never
opened one.

**The bug was the remembered answer.** `clearingNotRequired : Bool` initialised
to `False`, so *the briefing said clear them* and *I have never seen a briefing*
were the same value — CLAUDE.md's own "distinguish absent from false", in
`BotMemory` rather than in a parser, and collapsed in the expensive direction.
It was also **one answer for the whole session**, overwritten by whatever
briefing appeared next, so a "clearing is optional" verdict read for mission A
stood over mission B until B's briefing happened to be read.

**Flying a mission whose briefing this session never read is the ordinary
case**, which is what makes the second value worth having. Of the 34 recorded
runs, **13 never had a briefing on screen at any point** — 3,688 readings — and
27 of the 33 that ever tracked a mission began on one they did not accept.

So the verdict is now one entry per mission (`BotMemory.briefingsRead`, the way
`missionNamesAbandoned` is a list), filed under the name the *briefing* gives
and looked up under the name the tracker gives. Those are the same string where
both exist: across the recordings **331 of 361** accepted missions later appear
in the tracker under exactly the briefing's name, 324 of them on the very next
reading carrying a tracker, and the 30 that never do are accepts the tracker
never showed at all — the untracked-mission state
`agentConversationWithoutTrackerTicks` already exists for. Compared whole rather
than chain-wide, unlike `missionNameForDeclining`: the rooms of a chain differ
only by `(N of 3)` and they do not share an answer.

**Which direction the unknown fails in is chosen, and it is the same direction
as before.** `clearingCase` answers four things, and only one of them —
a briefing read *for this mission* saying so — leaves the rats alive. Both kinds
of not knowing clear the field. That is not free and the cost is run 32 again:
a session spent fighting a pocket the client said to skip. It is chosen against
the other cost, which is worse and less visible — reading "no briefing seen" as
"clearing is optional" would leave rats alive on most missions on most runs, and
the client's *other* locked-gate sentence is `There are synchronized gate
scramblers on all hostile entities in this area … you must simply clear the
vicinity of enemy ships`, so the bot would sit at a gate that will not open with
the pocket alive behind it. A stranded ship is worse than a wasted session.

**What actually changes for a run like 32 is that it says so.**
`describeClearing` is in the status line on every reading a mission is tracked,
naming which of the four cases the bot is in —

```
clearing 'Recon (1 of 3)': NO BRIEFING READ this session (0 read, none of them
this mission's) -- clearing the field, which is an assumption rather than a
reading.
```

— printed on the ordinary case too, not only while guessing, because run 32's
log carries no line at all recording that an assumption was being made and a
clause that appeared only under the assumption would still leave the two states
grepping the same. **Nothing here narrows the gap between the two answers**;
what it does is stop them being one value, and give a later rule something to
act on. The obvious follow-up — going and reading the briefing rather than
assuming — is not in this change and is in "Open gaps".

**Verified without a live client**, in
`tools/macos-host/tests/test_clearing_needs_a_briefing.py` (30 cases). The three
pure rules are executed through the real `Bot.elm` in `elm repl` rather than
mirrored in Python: run 32's own state, the per-mission lookup against a session
holding several verdicts, the chain's two rooms not sharing an answer, a
nameless briefing being dropped rather than attributed, and a verdict outliving
the conversation that produced it. Every mission briefing the recordings hold
goes through `clearingVerdictFromBriefing`, and exactly the Recon one comes back
optional while each carries the name the log quoted. The corpus counts above are
recounted as *relations* — a large share of runs saw no briefing, the two names
agree for the large majority of accepts — so a growing corpus cannot make a true
claim red. Confirmed by mutation, eleven of them, each failing a named case: the
unknown answering "optional" (the flip this change refuses), the unread case
collapsed back into "said nothing", the name matched chain-wide, the lookup
ignoring the mission the way the old `Bool` did, a nameless briefing attributed
anyway, terms that are not on screen reading as a briefing, remembering
appending instead of replacing, the matcher losing one of the client's two
wordings, the status line no longer naming the case, the fight reading the
memory instead of the rule, and the memory update defaulting the answer again.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one is the `clearing '<mission>':` clause appearing on every reading a
mission is tracked, and saying `NO BRIEFING READ this session` on a run cycled
onto an inherited mission and something else on a run that took its own. A run
that never prints the clause at all is a tracker the status line cannot read,
which is the direction this would fail silently in.

**Webbing is not damage, and that case is not covered.** A webifier can apply no
damage at all, and then it writes no combat line, so a signal built on damage
cannot see it — which is precisely run 10's two frigates, whose rows the issue
reports rendering "Pilot is webifying me". They happened also to deal damage, so
run 10 itself is covered; a pure webifier would not be. When this was written
that string appeared **nowhere in the ten recorded runs** — nothing had ever
printed these hints — so matching it would have been a guard resting on a
premise no evidence supports. The hints are printed instead
(`Overview indications:` in the status line, distinct strings from rendered rows
only), which is what turns the next run into the evidence a follow-up can be
built on.

**It did, and #231 is what was built on it** — see "The client names two other
kinds of EWAR and the bot read neither" below. `commonIndications` now reads
four literals: the two it inherited (`is jamming me`, which this client has
written **not once** in the whole corpus, and `is warp disrupting me`) plus
`is tracking disrupting me` and `is sensor dampening me`. The webifier's is
still unread and so is the painter's, though both are now in the corpus —
they are not damage-suppressing and #231 leaves them deliberately out of scope.

Every engagement of this kind names itself in the decision log —
`Shooting back at '…': the client's combat log names it as having hit this ship
in the last 45 s, and nothing else here marks it as a target.` — and only when
nothing else would have selected the row, so the line means "this is new" rather
than appearing beside every rat in the pocket.

### The client names two other kinds of EWAR and the bot read neither

Issue #231. `overviewEntryIsWarpDisruptingMe` shoots a warp scrambler first, on
the argument that everything the bot does when a fight goes wrong assumes it can
leave. The client names two other EWAR types on the same overview row and the
bot read **neither** — so it acted on the rarest of the three and ignored the
most common by a factor of nineteen.

**The evidence was already there and nobody had read it.** #130's
`Overview indications:` clause has been printing the rendered rows'
`rightAlignedIconsHints` since it was added for exactly this. Counted across
`~/eve-bot-logs`, per *reading* as well as per line, because the status line is
reprinted under every decision:

| literal, as the client writes it | lines | readings | runs |
|---|---:|---:|---:|
| `Pilot is tracking disrupting me` | 5,320 | **1,640** | 13 |
| `Pilot is webifying me`           |   992 |      306 |  5 |
| `Pilot is target painting me`     |   732 |      228 |  4 |
| `Pilot is warp disrupting me`     |   290 |       86 |  3 |
| `Pilot is sensor dampening me`    |   265 |       89 |  1 |
| `Pilot is jamming me`             |     0 |        0 |  0 |

87 runs, 288,912 readings. The line counts reproduce the issue's exactly; the
reading counts are three to four times smaller, which is this file's own "a
decision in the log is not an action" applied to counting — the unit that has
cost `stall_watch.py` two threshold calibrations, #141 a retreat measurement and
#164 an issue's whole diagnosis.

**"dampening", not "damping"**, which is the client's own spelling and exactly
the detail a matcher written from memory gets wrong. Both literals were cut out
of the corpus rather than typed from the issue.

**`is jamming me` is the shape in reverse**: matched by all six vendored parsers
since upstream and written by this client **not once** in 288,912 readings, and
read by no decision in any app. Either the literal is wrong for this client or
jamming genuinely never happens here, and the corpus cannot tell those apart.
Recorded as a scope note; a case goes red the day a run writes it.

### Three tiers, because "cannot leave" and "shooting badly" are not one priority

`combatPriorityTier` replaces the two-way sort in both apps:

- **Tier 0, holding the ship in place** — `overviewEntryIsWarpDisruptingMe`.
  Survival, and the only one of the three that takes an option away.
- **Tier 1, stopping the ship fighting** — `overviewEntryIsStoppingUsFighting`,
  the two new literals. Effectiveness: the ship can still leave, it is just bad
  at the fight.
- **Tier 2, everything else**, in the distance order it arrived in.

**It is a reordering and not a widening**, which is stronger than the property
#40 needed and is what makes it safe by placement rather than by argument. The
sort is applied *after*
`overviewEntriesToAttackFromReadingFromGameClient`, so every row a tier can move
is a row `shouldAttackOverviewEntry` already admitted: `overviewEntryDistanceIsOnGrid`
still holds by construction, `overviewEntryIsDisplayed` still runs at the lock
site, and a row under EWAR that nothing else would have shot is still not shot.
#231's own phrasing — "adds rows to the target set at their own distance rank" —
is #40's carried over and is not what this does.

**saxrat read none of it, and that is the bigger half.** `isWarpDisruptingMe`
was parsed on every reading of every recorded run and the only read site in the
repository was the mission runner's, so the bot that flies unattended in the
hull that was lost twice had no scrambler priority whatever. It has all three
tiers now.

### Both of the issue's harm arguments are unobserved, and the change does not rest on them

Measured rather than repeated, and this is the part a reviewer should weigh.

- **The #90 interaction is not in the corpus.** #231 argues that the bot's
  answer to "my shots achieve nothing" is to give up on the *target*, which is
  backwards when a third party is jamming the guns. Six recorded runs carry both
  the tracking-disruption hint and #90's own tally clause, and across **12,496**
  readings -- 39,757 lines, which is the same over-count this file warns
  about -- that clause reads `shots landing for zero: none` on every one of
  them, the tally never once leaving zero. `did zero damage` — the give-up line — has fired in **no** recorded run
  at all. That is consistent with the mechanism rather than surprising:
  #90 counts *landed* shots at zero and says in its own words that "a miss
  builds no case, because the host never counts one", while tracking disruption
  produces misses and glancing hits, and a glancing hit reads a real number.
  **Making the give-up rule aware of tracking disruption is therefore a scope
  increase resting on a premise the corpus does not support**, and it is
  deliberately not done.
- **The sticky lock-range bound is not in the corpus either.** #231 argues a
  dampener teaches `lockRefusedAtMeters` an artefact that only ever moves down.
  Run 20 is the one run carrying the dampening hint and its `Lock range:` clause
  reads `refused -` on every reading of it — the bound never moved. The refusal
  test needs an empty target bar at both ends of an attempt, which is a strict
  condition that rarely fires; nothing says a dampener would not do this, only
  that nothing has watched one do it.

What the change does rest on is the client's own statement of fact about a row
and the frequency it makes it at, which is #40's standard, not a measured harm.

### Verified without a live client

`tools/macos-host/tests/test_ewar_priority_targets.py` (41 cases, run against
**both** apps). The parse and the tier are executed through the real `Bot.elm`
in `elm repl` and the overview rows they are asked about come from the **real**
`EveOnline.ParseUserInterface`, so the parser half is executed rather than read
— a Python restatement of "what does this matcher make of this hint" would test
the restatement. The discriminating case for the spelling is the plainest one:
the corpus literal fed in byte for byte, since `is sensor damping me` is no
substring of `Pilot is sensor dampening me` and a misspelled matcher answers
`False`. The corpus is recounted as **relations** — tracking disruption dwarfs
warp disruption, the misspelling occurs nowhere, `is jamming me` occurs nowhere,
lines exceed readings — so a growing corpus cannot turn a true claim red.

**One case is weaker than the rest and says so.** `test_the_sort_puts_them_in_
that_order` applies the real `combatPriorityTier` with a real `List.sortBy` over
really parsed rows, but that `List.sortBy` is written in the case rather than
reached through `decideActionInCombat`, which takes a whole
`BotDecisionContext`. A source read beside it pins the decision to that
expression, and #40's own
`test_a_scrambler_still_outranks_something_merely_shooting_us` reads it too —
that case moved with the code rather than being deleted.

### The vendored-parser question, checked rather than assumed

`CLAUDE.md` states the policy over the whole file; what the repo **enforces** is
`test_game_log_channel.VendoredParserTest` over the game-log block, and outside
that block the six copies have already diverged — PR #252 concluded from that
divergence that an app-local panel parser lands in **one** copy.

**This lands in all six, and the difference is a measurement rather than an
appeal to the stated policy.** `OverviewWindowEntryCommonIndications` is a field
on a *shared* overview type that five of the six `Bot.elm`s read, and it is one of the
places the six have **not** diverged: the type alias and the matcher block were
byte-identical across all six before this change, and are again after it. Adding
to one copy would put a divergence into a block that has none, in a type whose
readers are spread across the apps, so #252's app-local argument does not reach
it. `TheVendoredParserPolicy` asserts all four halves — both fields in all six,
the literals in all six, the two blocks identical across the six, and the whole
files still differing, which is what makes "identical here" a property of this
block rather than an accident.

### Unverified: any of it running, and what it costs #178

No run has been flown; this was written with a saxrat run in flight. What to
watch on the first run that meets one of these: a row the overview marks under
tracking disruption being locked and shot **ahead of** a nearer rat, and
`Overview indications:` carrying the hint on the same reading. A run that meets
the hint and never changes its lock order means the field is parsed and the sort
is not reaching it, which is the direction this fails silently in.

**The cost to #178 is predicted and not measured.** `lockBatchRowsInReach`
counts the in-range *prefix* of the candidate list precisely because a priority
row that is out of reach sits ahead of rats that are in reach. Moving the head
of that list from something seen on 86 readings to something also seen on 1,640
means the head will be out of reach more often, so batches will collapse to a
single lock more often and part of #178's ramp is given back. Nothing here
measures how much — it needs a run, and the tell is `Lock batch:` asking for one
row on readings whose `Overview indications:` names one of these two.

Also unverified, and inherited: whether the hint text is stable across clients.
Every count above comes from one account on one client build. And the counts are
of rows the client **rendered** — `Overview indications:` reports distinct
strings from rendered rows only — so a virtualised row carrying one of these
hints is in none of these numbers.

## What the bot gives up on: shots that land and achieve nothing

Everything above adds rows to the target set. This is the one rule that takes
one away, and it exists because run 27 locked an `Infested Asteroid` and shot it
with every gun for roughly **290 consecutive readings** — every shot landing,
every one doing **zero damage**, nine or ten real rats untouched on the same
overview, and the mission tracker already reading `no instruction (next step:
Set Destination)`. It ended with the shield at 0% and armour going while three
named attackers hit the ship and its own guns were still on the rock.

**The bot could not see any of it, and that was the whole issue.** The host
matched `^(\d+) from (?P<attacker>.+)$` — the incoming half, summed for #32's
retreat. Outgoing `N to <target>` lines were matched nowhere, so no field in any
reading said how much damage this ship was *dealing* and no decision could ask.
That gap had already been named once: `ammoSwapRangeErrorPercent` is documented
as "the weak half" precisely because what decides whether the other charge is
better is whether the guns are landing, "which the client states on its outgoing
combat lines and which this does not read". Same missing instrument, second
consumer, and the summary now serves both.

**The client distinguishes the three cases in the line itself**, so none of this
is inferred from a health bar that never moves: a miss carries no damage number
(`Your Hobgoblin II misses Vigilant Sentry Tower completely`), a landed shot
reads `104 to Mammon Apis - Hits`, and a landed shot that did nothing reads
`0 to Infested Asteroid - Hits`.

**Summarised host-side, per target.** `MacOsHostSyntheticOutgoingDamage` is the
third synthetic node, one child per target carrying `name`, `hits` and `damage`,
lifted into `ParsedUserInterface.outgoingDamageSinceLastReading : Maybe (List
OutgoingDamageToTarget)`. Same four safety properties as the other two. The raw
lines stay withheld — there are 158,850 `(combat)` lines across the recorded
sessions and 77,316 of them are outgoing, more than twice the incoming count.

**Per target rather than one total**, which is the one place this differs from
the incoming node, and run 27 is why: its drones were landing real damage on a
`Mercenary Commander` in the very readings its guns were achieving nothing on
the asteroid, so a single sum would have read as healthy throughout the incident
the whole change exists to catch.

**Absent means unknown, and unknown keeps shooting.** `Nothing` from the parser
is "this host does not carry the channel" and never adds to the evidence or to
the verdict. The fail-safe direction is the *opposite* of #37's — there an
absent channel must not read as "the grid is quiet", here it must not read as
"everything is immune" — and the status line reports
`zero-damage check: NO COMBAT LOG` rather than leaving it to be inferred from a
verdict that never arrives.

**Eight landed hits at zero, and what it has to clear is a run rather than a
target.** #90 calibrated it on a disjointness — across 77,316 outgoing lines
naming 294 distinct targets, eight targets ever produced a zero and none of
those eight ever produced a nonzero — and called eight "margin rather than a
separator" on the ground that there was no observed overlap for it to sit in.
**That claim has expired.** The corpus is now 165,420 outgoing lines naming 317
targets, ten of them ever read zero, and one of the ten — a `Centii Servant`,
from the live saxrat runs — also read nonzero. Nothing about the rule changed;
the evidence did, which is #158.

**The number survives and the re-derived reason is the sharper of the two.**
`zeroDamageMemoryAfterReading` tallies *consecutive* readings whose whole
summary for a target was zero and clears the tally outright on any reading that
target took damage, so the quantity eight has to clear is the run length and
never was the count of targets. Counted that way the corpus separates cleanly:
the longest run of consecutive zeros on a target the guns were hurting is
**one**, and the zero-only episodes still run 3, 3, 5, 10, 28, 74, 86, 101 and
108 landed hits. So eight sits in a measured gap between one and ten — a
separator now, where #90 could only say the gap was empty — and it is still the
largest value that catches every episode worth catching, firing 20–75 s into
each in place of the 41–414 s those episodes actually ran.

**The overlap never reached the bot at all**, which is what makes this a
measurement rather than a reprieve. All three `Centii Servant` zeros were
written in the same second as a real hit on the same target from the same drone
— `0 to Centii Servant - Acolyte I - Hits` beside `55 to Centii Servant -
Acolyte I - Smashes` — and the host carries `{name, hits, damage}` summed per
target per reading rather than lines, so the summary handed over reads
`damage = 55` and clears the tally instead of adding to it. Folded at the
client's own second, which is shorter than any real reading and so the fold most
favourable to a zero standing alone, the tally for that target never leaves
zero. Resists and glancing hits still do not round to zero on these fits either
— a glancing hit reads `15 to Mercenary Commander - Acolyte I - Glances Off`.

**It is a number about this ship's guns, not about the game**, and the overlap
sharpens that warning rather than softening it: the three zeros came from a
**drone**, and the rule tallies drone hits and gun hits alike because the
client's outgoing lines give it no way to tell them apart. What the corpus no
longer is, is one hull — the sustained zero-only episodes were shot with
`Focused Modulated Medium Energy Beam I`, `Dual Anode Light Particle Stream I`
and `Small Focused Beam Laser II` across two characters, so the separation now
holds over three fits rather than the one #90 measured. A fit whose shots are
small enough to round to zero against a heavily resisted target would still
accumulate against something it could eventually kill, and nothing here covers
that — the same warning `defaultRunAwayIncomingDamageThreshold` carries.
`give-up-after-zero-damage-hits` sets it; `-1` disables it.

**A miss builds no case**, because the host never counts one. Missing is a range
problem and giving up is not the answer to it — without that, a gun firing out
of range would give up on everything it could not reach.

**The verdict is latched in `BotMemory.zeroDamage` and kept for the session**,
the way `missionNamesAbandoned` is. A reading's summary is gone by the next one,
so a branch that read the zero and wrote nothing down would see it once and go
straight back to shooting the same rock — `loadRefusedByClient`'s failure. It
does not un-latch on later damage, deliberately: after giving up the bot stops
shooting the object, so no further evidence can arrive and a rule waiting for
some would wait forever.

**Two consumers, and both are needed** — which is what run 27 settles about the
selection question the issue left open. The bot **never chose that asteroid**:
across 265 `Lock target from overview entry '…'` lines in that run, not one
names it. The reading before it appeared shows the bot Ctrl+clicking the row for
`Sunder Alvi`, and the next reading reads `target Infested Asteroid`. That is
the distance-sorted overview re-sorting between the reading and the click, the
same row shift already documented for the loot cascade — so the icon rule is
exonerated, and **a `never-attack` name list would not have helped, because no
name-based rule was ever consulted for this object.**

So `shouldAttackOverviewEntry` gains the subtraction (one choke point, since the
lock candidates, the scroll-to-reveal and `anyAttackableInOverview` all ask it),
and the branch that matters unlocks it from the *target bar*:
`activeTargetGivenUpAsImmune` reads the whole overview rather than
`overviewEntriesToAttack`, because giving up has already removed the row from
that list. Nothing here chooses which locked target EVE calls the active one, so
declining to shoot would leave the object in the slot and reach the same branch
again next reading — run 27 with a different decision line. Freeing the slot is
all it has to do; `activateOneOfTheLockedTargets` clicks another locked target
on the next reading. The unlock is the locked-target-bar icon that already
exists, one of the two cascades needing a 200px tolerance.

**It says so out loud**, which `askForHelpToGetUnstuck` never did for run 27:

```
Every shot that has landed on 'Infested Asteroid' did zero damage, 8 of them by
the client's own count -- these shots are achieving nothing. Unlock it
(Ctrl+Shift+Click) and leave it alone for the rest of the session.
```

and the status line carries
`shots achieving nothing: 'X' 3/8 (3 landed for zero, 0 missed)` every reading,
so a target climbing towards the threshold and one that never climbs are
distinguishable while watching a run. (The clause was `shots landing for zero:`
until #267 gave a miss a way to join a tally; the two halves are printed because
the sum alone cannot say which kind of evidence a case rests on.)

**No `never-attack` setting was added.** `attack-object` is a positive list and
this bot still has no negative one — the scope matters, because read as a claim
about the repo this sentence is false and #125 was filed on that misreading;
`eve-online-saxrat` and `eve-online-combat-anomaly-bot` both implement one. But a
name list is exactly what failed here:
nobody had predicted `Infested Asteroid`, and the object was never selected by
name in the first place. What the operator gets instead is a threshold to tune
and a run that learns the name itself. The lever an operator actually lacked
mid-run is covered by the web console, which applies a settings change without a
restart.

**Untested against a live client.** The rule is executed through the real
`Bot.elm` in `elm repl` and the threshold is checked against the client's own
recorded lines, but no run has given up on anything. What to watch on the first
one: the status line's `shots achieving nothing:` clause appearing at all — if it
never does on a run that fights, the outgoing summary is not reaching the bot —
then the unlock line above, then `GIVEN UP ON` for the rest of the session with
the object never locked again. The failure to watch for is a lock/unlock
oscillation: the row shift that produced run 27's asteroid can produce it again,
and the verdict then costs one reading each time instead of 290, which is a fix
rather than a cure.

## The status line named the target and said nothing about its condition

`target Render Alvi` told an operator what the guns were pointed at and nothing
whatever about it, while the ship's own line beside it has always carried
`Shield: 58%  Armor: 100%`. It is not a rare line: run 27 names a target on
7,917 readings, run 29 on 5,065, run 30 on 1,812 and run 34 on 1,329.

**#90 is what the gap costs.** Nothing told the bot its shots were doing zero
damage, and the fix had to reconstruct that from the combat log's outgoing lines
because no field in any reading said what the target's health was doing. Run 27
shot an `Infested Asteroid` for roughly 290 consecutive readings, every shot
landing for zero — and a health bar that never moved would have said so on the
second reading.

**It is a parse and not a hover**, which is the question #112 left open and a
read of the live client answered. Under every `TargetInBar` the client draws

```
Container  _name=barAndImageCont
  Container  _name=iconPar
    TargetHealthBars
      Container  _name=shieldBar   Sprite _name=shieldBar_Left  Sprite _name=shieldBar_Right
      Container  _name=armorBar    Sprite _name=armorBar_Left   Sprite _name=armorBar_Right
      Container  _name=hullBar     Sprite _name=hullBar_Left    Sprite _name=hullBar_Right
      Sprite     _name=healthBarBackground
```

so there is an answer on every reading, no mouse involved, no tooltip to go
unanswered, and no competition with the ammo swap's own weapon hover — the risk
#112 was chiefly worried about, and #106 is the open issue about it.

### The bars are a ring, so there is no width to take a ratio of

This is the part that had to be measured rather than assumed, and the obvious
reading of it is wrong. `DronesWindowEntryDroneStructure.hitpointsPercent` next
door derives a drone's bar from the width of `droneGaugeBarDmg` against its
gauge bar, and that technique answers nothing here: **every node under
`TargetHealthBars` — all three containers, all six sprites and the background —
reports the identical 141x141 region**, which is the bounding box of the whole
ring. The paired `_Left`/`_Right` sprites are two half-circle textures
(`res:/UI/Texture/classes/Target/shieldLeft.png` and `shieldRight.png`, carrying
`baseRotation` 0 and -3pi/4), so the fraction is drawn by rotating an arc and
never appears in a display region at all. A width ratio here answers one
constant for a full shield and a dead one alike.

**The client stores the fraction itself**, as `lastState` on the named
container, which makes this `ShipUI`'s `_lastValue` read rather than the drone's
geometry. Watched changing under fire on one `Centii Plague`: `shieldBar` went
1 → 0.8089 → 4.39e-06 as the shield collapsed and then climbed back through
1.88e-05, 4.29e-05 and 1.24e-04 as it regenerated, while `armorBar` went
1 → 0.2484 in the same window and `hullBar` stayed at 1. A layer that has taken
nothing carries the JSON integer `1` rather than `1.0`, which is the ordinary
reading and is why the decoder has to accept both.

### Three values, and absent is not zero

**The three stay distinct.** The zero-damage case is a shield that does not move
while armour and hull sit at 100%, which any combined figure hides, so
`Target.hitpointsPercent : Maybe Hitpoints` answers the record and the clause
prints three numbers:

```
rats 8 | target Render Alvi (Shield: 58%  Armor: 100%  Hull: 100%) | Lock range: ...
rats 8 | target Render Alvi (Shield/Armor/Hull unknown) | Lock range: ...
rats 0 | no target | Lock range: ...
```

**Absent reads as absent.** A target whose bars cannot be read prints `unknown`,
never `0%` — a fabricated zero is a hull about to explode as far as any later
rule is concerned, and `loadRefusalFromGameLog`'s doc comment is the register.
It is all three layers or none, like the ship's gauge and the drone's. The
condition is printed only where there is a target to have one: run 27 has 10,372
readings naming none, and `unknown` on every one of them would be noise rather
than a reading.

**The value is not clamped or filtered.** `ShipUI.hitpointsPercent` is the same
kind of read and this file records it producing -1021821% and 2132822% for single
readings; a garbage value silently clamped into [0, 100] reads exactly like a
real one, and this field's whole job on its first run is to show whether it reads
sanely, which a clamp would make impossible to tell.

**Nothing decides anything on it.** It is an instrument and it earns the right to
drive a rule once a run has shown it reads sanely — PR #130's posture for
`quickMessage`, which PR #153 later relaxed deliberately once there was a corpus.
`TheFieldIsAnInstrumentAndNothingActsOnIt` holds that line: the field is reached
through one named lookup, that lookup and the rendering are read by the status
line and by nothing else, and no decision branch names either.

**Both maintained apps, and only those two.** `parseTarget` and the `Target`
alias were byte-identical in the mission runner and saxrat before this and are
again after it, so the change is the same declarations under the same names in
both and a case compares them byte for byte. The other four vendored copies are
left alone: their `parseTarget` already diverges (they recognise only
`ActiveTargetOnBracket`, where this fork added `ActiveTargetIndicator`), so the
maintained pair is the unit this repo already keeps in step.

**Verified without a live client**, in
`tools/macos-host/tests/test_target_hitpoints.py` (31 cases, run against **both**
apps). The parse and the two rules are executed through the real `Bot.elm` in
`elm repl` and the readings are built by running UI trees through the **real**
`EveOnline.ParseUserInterface`, so what the cases assert on is what the bot would
have been handed. The fixtures give every ring node one region, exactly as the
live client does, which is what makes `TheRingCarriesNoWidthToTakeARatioOf` a
measurement rather than a comment: three trees whose nodes are all the same size
answer three different things only if the value came from somewhere other than a
width. The corpus is recounted as relations — a target is named on a large share
of readings and its hull was never printed on any of them — rather than as the
counts above.

Confirmed by mutation, nine of them, each failing a named case: **an unreadable
bar reporting `0%` instead of unknown**, which is the failure this whole design
refuses; the drone's width ratio used where there is no width; one bar read three
times so the three layers collapse; a decoder that rejects the integer a full
layer carries; the percentages clamped in the parse; the hull dropped from the
clause; the condition printed on the no-target branch; **a decision starting to
consult the field**; and saxrat's copy drifting from the mission runner's.

**Unverified: any of it running.** No run has been flown since. The geometry and
the values above were read off the live client, so what a run has to show is the
clause itself: `target <name> (Shield: N%  Armor: M%  Hull: K%)` on the readings
that name a target, with the numbers *moving* while the guns fire. A run that
names targets and prints `(Shield/Armor/Hull unknown)` on every one of them means
the containers are not where this reading found them — which is the direction
this would fail silently in, and is why the clause says `unknown` in words rather
than answering a number. **How often the bars are readable while a target is
locked is still not measured**, so the unknown branch is a design requirement
rather than a frequency; and whether the ring can produce a garbage percentage
the way the ship's gauge does is unknown, which is the second thing to watch.

## When the objective is done and the tracker offers a trip, the fight is over

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
`Rats in overview: 0`.

**#49 fixed that for the label `Dock` and for no other, which turned out to be
the rarest case there is.** Counted across every recorded run on the readings
that cost something — in space, objective complete, rats on the overview:

| travel step | readings | avg rats |
|---|---:|---:|
| `Set Destination` | **1,443** | 7.0 |
| `Destination Set` | **812** | 3.0 |
| `Start Conversation` | 71 | 1.7 |
| `Dock` | 35 | 1.8 |
| `Preparing` | 15 | 2.0 |
| `Warping` | 3 | 2.0 |

So the label #49 handled is 35 readings and the ones it did not are 2,344, on
grids carrying up to four times the rats — at two to three seconds a reading,
about an hour of the corpus spent shooting bounties on a finished mission.

**`travelOutranksTheFight` is the whole exception**, and it is placed rather
than conditioned: it wraps the combat call inside `decideActionInMissionPocket`,
so the fight becomes the fallback exactly where travel used to be. It fires when
the objective's `instructionTexts` is empty or blank **and** the tracker is
offering a travel step at all — whichever step it is.

**The label is no longer part of the condition, and the measurement is why.**
The words that mean the mission is still running do not appear beside a finished
objective on a grid with a fight on it. `Warp to Location` is the one that would
matter, since taking it would leave a pocket that has not been cleared: 10,032
readings beside a live objective, **three** beside a finished one — a flicker
between two `Dock` readings as a mission ended — and **none at all** with a rat
on the overview. `Read Details`, `Docking`, `Undocking` and `Jump` never meet a
finished objective; `Undock` and `Abort Undock` do, but only on readings with no
ship UI, which is in station, where this branch is never reached. The objective
half is what excludes them, and a list of permitted words would repeat #49's own
mistake — it handles what has been measured and leaves whatever the client
writes next. The vocabulary has already grown twice without anyone deciding to:
#62's objective-chain panel added four labels, and run 22 added one that is not
text.

**`Preparing` and `Warping` are covered too, and that is the one judgement the
data settles rather than decides.** They read like states rather than commands —
if the ship is already warping, disengaging is moot rather than wrong — and the
recordings say the distinction is unobservable from here: on every costly
reading carrying one, the ship was in warp (15 of 15, and 3 of 3), where
`decideActionWhenInSpace` answers `I am in warp` long before this branch is
consulted. Covering them changes no recorded reading; excluding them would be a
list to maintain for nothing.

**Widening the rule flips the failure direction, so the direction is now
chosen.** #49's equality test against `Dock` declined a label with no text *by
accident* — run 11 rendered a travel step three times as

```
U+0002 U+0000 U+AD1D8 U+0001 U+0001 U+0000 U+0001
```

six C0 control characters around one codepoint that is **unassigned** (category
`Cn`, plane 10), *not* private-use. That distinction is still the trap: a rule
recognising "not text" by private-use membership would classify this as text. A
rule of the form "any travel step is offered" **matches** it, and would
disengage on a button the client failed to draw.

`travelLabelIsReadableText` refuses that, and the choice is fail-**closed**: an
unreadable label is not a step, and the bot keeps fighting, which is exactly
what it does today. The test is printable ASCII with at least one letter in it —
every label the client has ever written here is ASCII, and the alternative
(accepting anything) is the only way this change could make the bot leave a
pocket it should not.

**The corpus contains the case that makes this load-bearing rather than
theoretical.** Run 22 rendered a travel step as `U+0000 U+0000 . 5 0 <space> A U
U+0000` — a distance readout wrapped in NULs — on `Avenge a Fallen Comrade --
**no instruction**`. Run 11's glyph sat beside an objective still asking for
something, so both halves declined it and fail-closed was free. This one sits on
a finished objective, so the label rule is the only thing declining it.

The stated cost of that rule: a client rendering this button in a non-Latin
script switches the branch off entirely and the bot behaves as it did before the
change. That is the safe direction, and it is the same assumption about the
client's language the rest of this file already makes.

**What still keeps the guns firing**, since the point of the branch is to stop:

- **Anything warp disrupting the ship.** Docking is a warp, so a scrambler makes
  leaving impossible and killing it is the only thing that restores the option —
  the same reason `overviewEntryIsWarpDisruptingMe` sorts to the front of the
  combat candidates. The branch hands the fight back **and says so every reading
  it declines**, for `returnDronesToBay`'s reason. This is the one case where
  being shot outranks leaving.
- **An objective still carrying an instruction**, whatever the button offers.
- **A tracker with nothing to travel to.** The step has to be one the bot can
  actually take — a button `missionTravelStep` would click, or a route the panel
  confirms exists — so a reading where the tracker says the route is set and no
  route is there keeps the old order instead of disengaging into the bottom of
  the travel branch, where the stall counter and #54's abandonment live.
- **A lost ship and the two retreats.** `recoverPodAfterShipLoss` still
  short-circuits the docked-or-in-space split above all of this, and
  `runAwayIfLowHealth` still runs before `decideActionWhenInSpace` is called at
  all, so #32's damage-rate retreat outranks this branch. That is the right way
  round: the retreat is the controller for "leave now, this is going badly" and
  this one is for "the job is done, go home". There is no second one — this
  branch takes the tracker's own step and owns no clock, no counter and no
  memory.

**Being shot, otherwise, does not keep the guns on**, and that is a decision.
#40's rule stands while there is a fight to be in; once the objective is done the
answer to being shot is to leave. The recordings say the trade is cheap: over run
11's 77 readings the client's combat log reported any incoming damage at all on
**4** of them, at most **7 hitpoints** in a 45-second window against a threshold
of 3,500. Were the damage real, the retreat above would have taken the reading
before this branch saw it.

**Nothing new is done to leave, and that is structural rather than careful.**
The step handed back is `travelTheStepTheTrackerOffers`, the *same value* the
fight itself falls through to. So the click still goes through
`ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping` and
`clickMissionTravelButton`'s settling window, and an acceleration gate on the
grid still outranks flying a route — which is what keeps a multi-pocket mission
from being stranded short of its next gate. The branch changes *when* that step
is taken, never what it is. That also covers `Destination Set`, the second of
the two labels #49 missed: it is not a click at all (`labelReportsRouteAlreadySet`
filters it out of `missionTravelStep`), and the trip it names is travelling the
route the tracker already set, which the same branch does.

**It clears itself, so it needs no bound.** Every condition is re-derived from
the live reading: the moment the tracker stops offering a step — the ship
docked, the mission moved on, the tracker collapsed and took the button out of
the tree — the fight is the bot's job again on that same reading. Nothing
latches.

Two decision-log lines carry it, and the wording is #49's so an operator's
existing grep still works:

```
+ The objective is complete and the mission tracker says 'Set Destination' -- stop fighting and leave the rest of the field alone.
+ The mission tracker says 'Dock' and the objective asks for nothing more, but 'X' is warp disrupting this ship -- nothing leaves until that is dead, so keep fighting.
```

**Verified without a live client**, in
`tools/macos-host/tests/test_travel_outranks_the_fight.py` (33 cases): the two
pure rules are run through the real `Bot.elm` in `elm repl` rather than mirrored
in Python — every text label the recordings carry reads as a step, both non-text
ones are declined, and the objective rule is asked about the strings each sat
beside; the bot's label rule is cross-checked against this file's own
`Cc/Cf/Cs/Co/Cn` classifier over every label in the corpus, so a client that
starts writing something new has to be wrong about it in both places to pass;
the counts above are recounted from `~/eve-bot-logs` as *relations* (these
labels dwarf `Dock`, the grids are the busy ones, `Warp to Location` never costs
anything, the transient labels are only ever reached in warp) rather than as
numbers, since a corpus that grows must not turn a true claim red; and the
ordering, the scrambler decline, the shared step and the absence of a counter
are read out of the source through a whitespace-collapsing reader.

Confirmed by mutation, eleven of them, each failing a named case: accepting any
label as text (the fail-open version of this change), classifying by private-use
membership, dropping the readable-text clause or conjoining it into never
firing, the same two against the objective clause, disengaging on a route the
panel does not confirm, dropping the scrambler decline, re-wrapping travel
inside combat, giving the branch a travel path of its own — and, on the tests'
own premises, removing a known label from the vocabulary and making every
Unicode category count as text.

**Not verified: any of this running.** No bot was started for it. What to watch
on the first live run is `The objective is complete and the mission tracker
says 'Set Destination'` arriving within a reading or two of the label, followed
by the drone recall and the route being set — rather than another stretch of
`I see a locked target`. The two things that would show the widening wrong are a
disengagement on a grid that still has an objective (which would mean the
tracker's own "no instruction" is not what it says) and a disengagement between
pockets, which the gate-before-route ordering above is what prevents. The
looting question is deliberately still open: a wreck holding the mission item is
not optional the way ordinary salvage is, and this change does not answer it.

## A mission that cannot be progressed is given back, not asked about forever

The bot already knew it was stuck. `decideActionInMissionPocket`'s "over 300
readings of it — this mission is not going to progress on its own" branch has
been right every time it has fired; what it did next was raise
`askForHelpToGetUnstuck` and raise it again. Run 12 did that **817 times** on
`Illegal Activity (1 of 3) -- Retrieve Gallente Light Marines` and was stopped by
hand. Run 13 restarted on the same mission and reached the same state in **29
readings** — a fresh process cannot escape, because the mission is still
accepted and still impossible. Recovery took a person: fly Irnin → Amarr, dock,
open the agent conversation, `Quit Mission`, confirm, restart with
`decline-mission=Illegal Activity`.

**The verdict was right and the response was inert.** Issue #54 adds the
response and does not retune the verdict — #41 and #53 both confirmed it firing
on real stalls, and a test asserts the alarm's threshold and wording are
unchanged. #53 went further: PR #57 found run 12's wrecks were genuinely all
looted and the mission item was in a `Cargo Container` that left the grid
sixteen readings later, so that session's mission really had become impossible.
This is not an escape hatch around a bug — it is the only remaining response to
a mission that has genuinely stopped being completable, and it fires on a
verdict that has now been shown correct at least once.

**Quitting is the last resort it is, and the threshold says so as a relation.**
`missionStalledReadingsBeforeAbandoning` is `nothingToDoTicksBeforeCryingStuck *
2` — 600 readings — written as a multiple rather than a number so the argument
cannot drift away from it. `missionStalledReadings` counts a strict *subset* of
the readings `nothingToDoTicks` counts (every reading that advances the first
advances the second; every reading that resets the second resets the first), so
the abandonment cannot be reached without the alarm having been raised for at
least 300 readings first — roughly twenty minutes of an operator being told,
before anything irreversible happens. Standing is the cost, and a mission cannot
be un-quit.

**A bot that is merely busy cannot reach it.** The counter is narrower than the
alarm's premise on purpose, and two of its conditions are not the alarm's at
all: any reading where the ship reports a manoeuvre of any kind is excluded (an
approach reads `ManeuverApproach` for as long as it runs — the recordings show
it 68 to 94 times per run as `Already on the way -- let it run.`), and so is any
reading where the previous step put effects on the client, which covers combat,
looting, gate activation and every context-menu cascade. What is left is a ship
sitting still with a tracked mission, no travel step, no route and nothing being
clicked, which is what run 12 was.

**The verdict is latched in `BotMemory`**, like #33's ship loss and for the same
reason: the decision tree cannot write memory, and the state behind the verdict
disappears the moment the response starts — the trip back sets a route, which
reads as travel, and docking clears `nothingToDoTicks` outright. One thing
un-latches it: the mission leaving the info panel, which is what quitting
produces. So a successful quit ends the abandonment on the reading the client
shows it worked, and the bot goes back to ordinary work.

**Nothing new drives the UI.** In space it is `travelToStationByName` — the one
route-set, fly, dock path, already shared by #16's restock trip and #33's pod
recovery, and already recalling drones through `jumpToNextSystem`. Docked it is
`openAgentConversation`, the same helper the docked flow uses to take and hand
in missions. The only new click is `QuitMission_Button`, gated on
`previousStepClickedMouse` for that guard's original reason: the Accept and Quit
Mission rows overlap by three pixels, which is how this very dialog was once
opened by accident.

**The confirmation is the one dialog this bot ever answers yes to.**
`closeMessageBox`'s standing rule is that a confirmation is always declined, and
it names "Quit Mission?" as the reason. The exception is stated as narrowly as
it can be — a verdict latched, an agent conversation open, and a click issued
into it on the previous step — and the dialog is recognised by *shape* rather
than wording: a `no_dialog_button` with exactly one other button beside it, the
other one being the affirmative whatever it is called.
`closeMessageBoxByDeclining` still contains no affirmative at all, which a test
pins.

**Bounded, and the bound ends the session.**
`abandonMissionGiveUpReadings` (200) from the reading the verdict latches —
larger than the 150 `podRecoveryGiveUpReadings` budgets for the same trip, plus
the station work. Every way quitting can fail (cannot dock, no agent in the
station returned to, no Quit Mission button, an unrecognised confirmation) runs
under that one clock, so none of them can become a second forever-loop. When it
expires the session ends naming the mission, so an operator knows what to quit
by hand.

### A bound counted on every reading and tested on a few is not a bound

That last paragraph was true of the arithmetic and false of the code, and issue
#102 is the difference. `readingsSince` is advanced in
`updateMemoryForNewReadingFromGame`, which runs on **every** reading
unconditionally — that is the whole point of writing verdicts there. The
comparison that reads it sat inside `abandonMissionThatCannotProgress`, below the
docked-or-in-space split, and was therefore only asked on readings the decision
tree got that far.

Run 30 is the first live firing of the whole feature and it separates the two
completely. The verdict latched on a genuinely unwinnable objective, the bot
routed to the agent's station, travelled, docked, opened the conversation and
clicked Quit Mission three times — every piece of machinery that had never run,
ran. What failed is the bound:

| | count |
|---|---:|
| `quitting it for N of 200` reached | **10,811** |
| readings the status clause printed on | 32,813 |
| readings the branch printed a decision line on | **211** |

The counter had every reading and the comparison had 0.7% of them, because an
undismissable window held `generalSetupInUserInterface` for three hours and
forty-four minutes (#101). **And the comparison was never wrong**: on the last
reading of the run the box was gone, the tree reached the branch for the first
time since the onset, and the deadline fired *on that reading* at 10,811 and
ended the session. A bound that is correct and fires immediately when it is
finally asked, 54 times late, is a bound whose only defect is where it is asked.

**This is #34's family with the halves swapped**, and worth naming as its own
shape. There a counter could never reach its bound; here it reaches it easily and
the comparison is never put. Both present identically from outside — a bound that
is printed, looks armed and does not fire — and both survive review because the
arithmetic reads correctly in isolation.

**The fix is placement.** `abandonmentOutOfTime` is the comparison, extracted as
a pure rule over a record, and `endSessionOnAnExpiredBound` asks it from the
**head** of `missionBotDecisionRootBeforeApplyingSettings` — above
`generalSetupInUserInterface`, above the pod recovery, above the wind-down, above
the split. It is the one entry in that list with no work to do and no state to
reach: it neither clicks nor waits, so it can be evaluated on any reading at all,
and nothing has a reason to be placed over it. `abandonMissionThatCannotProgress`
lost its "out of time" branch entirely, so there is one comparison rather than
two places that could disagree about whether the attempt still has time.

**Fixing #101 is not this fix**, and the temptation to close it that way is the
thing to resist. PR #109 removed *one* way the tree can be held above this
branch. The two retreats, the pod recovery and the wind-down all sit above it
legitimately, and every future entry in that list is another one.

**The counter still counts readings and not attempts, and that is a choice with
a cost.** The other shape available — advance the counter only on readings the
branch was actually evaluated, so 200 means 200 *attempts* — is cleaner
semantically and wrong for this bound: a bot held elsewhere would then spend none
of the budget, which is precisely the runaway. Run 30 reached the branch on 211
readings in three and three-quarter hours, so an attempt counter would have stood
at 211 and gone on standing there. #54's own promise is that "every way quitting
can fail runs under that one clock", and a clock that stops while the bot is
stuck elsewhere is not one. The cost is stated rather than hidden: a bot starved
above this branch for an unrelated reason now ends its session at 200 readings
with the quit never attempted, where before it ran until something else stopped
it. The give-up line says so — the count is *readings since the verdict rather
than attempts*, so an operator whose session ends here having never reached the
agent is being pointed at the rest of the bot rather than at the quit.

**`droneRecallUnansweredTicks` is the counter-example, and the two are not in
conflict.** It deliberately advances only on readings the branch acted, reading
the ask out of `previousStepsEffects`, and it is right to: its give-up *declines
an action and hands the caller's own step back*, so a fight that legitimately
kept the bot elsewhere must not spend a budget whose purpose is to bound a
repeated ask. What decides the shape is what the give-up does. **A give-up that
ends the session bounds elapsed time and belongs where nothing can decline to ask
it; a give-up that declines an action bounds effort and belongs where the action
is.**

**Four other bounds in this file share the asymmetry, and none has cost anything
yet.** Stated so the next one is recognised rather than rediscovered:

- **`podRecoveryGiveUpReadings`** was the identical shape and is **fixed in
  #126** — see the section below. Left alone here deliberately at the time,
  because moving a bound is a behaviour change and wants its own evidence.
- **`messageBoxStandoffGiveUpReadings`** counts every reading with a box and is
  tested in `closeMessageBox`, which sits below `closeSystemSettingsMenu` in the
  same list. It over-counts if the pause menu holds it, which makes it give up
  *sooner* and hand the tree back — the safe direction.
- **`dockingRunInPatienceReadings`** and the loot window's
  `lootWindowOutOfRangeTicks` / `lootAllRefusedTicks` both advance from the
  reading and are tested deep under the split. Over-counting costs one
  re-commanded dock and one abandoned wreck respectively, not a runaway.
- **`gateWithinReachTicks`** counts the client's *offer* rather than the branch,
  and its own comment argues the case: anything that keeps the ship parked
  beside the gate was spending the budget too. Deliberate rather than
  accidental, and the failure direction is a gate declined.

`lockAttempt` is the clean one: its verdict is reached in the memory update
itself, so the counter and the test are the same code on the same reading.

**Verified without a live client**, in
`tools/macos-host/tests/test_abandonment_deadline_reachable.py` (22 cases). The
two pure rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python — the deadline at both sides of its boundary, at zero, at run
30's own 10,811, and against a verdict that never stalled and one with no name,
so that nothing conjoined onto the comparison can hide; and the give-up line,
which has to name the mission, carry both counts, say the count is readings and
not attempts, and say the mission still needs a person. The placement, the
absence of a second comparison, the branch doing nothing but ending the session,
and the counter's own unconditional advance are read out of the source through a
whitespace-collapsing reader. Run 30 is recounted as the relations rather than
the numbers: the count ran past 50x the bound, the branch was reached on two
orders of magnitude fewer readings than the verdict was latched for, and the
give-up fired exactly once, at the highest count the run ever printed.

Confirmed by mutation, ten of them, each failing a named case: the comparison
moved by one in either direction; the deadline conditioned on the attempt having
stalled as well; the deadline placed after `generalSetupInUserInterface` instead
of before it; the branch left out of the list entirely; the comparison left in
`abandonMissionThatCannotProgress` as well as in the rule; the clock advanced
only on readings the branch acted (the attempt-counting shape, which run 30's own
numbers refute); the give-up dropping the mission's name; the give-up dropping
the readings-not-attempts clause; the expired-deadline branch waiting instead of
ending the session; and the drone recall's counter changed to advance on every
reading, which is the same mistake in the direction the other rule needs.

**Unverified: any of it running.** No run has been flown since. The whole path
needs a mission that genuinely cannot progress *and* a bot that cannot finish
quitting it, which is not something to stage. What to watch on the first run that
abandons anything: `quitting it for N of 200` in the status line climbing and
then stopping — a run that ends the session at N=200 having never printed
`Travelling to '<station>' to give the mission back.` is the new failure mode and
means something above the branch is holding the tree, which is now what the
give-up line says to go and look for.

**The abandoned name feeds the session's own decline list.**
`BotMemory.missionNamesAbandoned` is consulted by `shouldDeclineMission`
alongside `decline-mission`, so the agent cannot hand the same mission straight
back — which is exactly what the human recovery did. The name is recorded with
its `(N of 3)` counter dropped (`missionNameForDeclining`), so quitting
`Illegal Activity (1 of 3)` also refuses `(2 of 3)`. It is memory rather than a
setting because settings are parsed once per session and are not writable from a
decision — and because it *should not* outlive the session: an operator who sees
the same mission abandoned twice promotes it to `decline-mission` themselves.

**It is never silent.** The decision log carries
`Abandoning the mission 'X': it cannot be progressed, so I am giving it back to
the agent rather than asking for help until the session ends.` on every reading
of the attempt — with **no reading count in it**, for the reason the give-up
alarm it responds to already documents: a counter makes every repeat a distinct
line and defeats `stall_watch.py`'s dedupe, as run 126's 151 variants of one
alarm showed. The counts live in the status line, which also carries
`abandoned and now declined this session: ...` for the rest of the run — the
signal that a mission type is worth adding to `decline-mission` permanently.

**Placed below the retreats.** It sits inside the docked-or-in-space split
rather than in the pre-split list, so `recoverPodAfterShipLoss`,
`windDownBeforeSessionEnd` and `runAwayIfLowHealth` all still outrank it: a lost
ship, a session ending and a ship being taken apart are each more urgent than an
errand. Everything that would otherwise fly the stuck mission is below it.

**Verified without a live client**, in
`tools/macos-host/tests/test_abandon_stuck_mission.py` (33 cases). The two pure
rules are executed through the real `Bot.elm` in `elm repl` rather than mirrored
in Python: `missionNameForDeclining` against **every** mission name the twelve
recorded runs contain, in both the tracker's spelling and the agent's own offer,
with the whole cross product checked so that a stripped name can neither miss
its own chain nor match an unrelated mission; and `previousStepDispatchedEffects`
against real effect values, including a keypress, since typing a station name
presses no mouse button. Everything else — the subset relation, the counter
properties, the bound, the ordering, the reuse, the confirmation's three
conditions — is read out of the source, through a whitespace-collapsing reader
so that the next `elm-format` pass cannot break them the way #58's broke three
others. Confirmed by mutation, **twenty-seven** of them, each failing a named
case: pinning the counter at `1`, removing its reset, freezing the attempt
clock, conjoining a second condition onto the un-latch, writing the threshold as
a bare 600, retuning the alarm, dropping the manoeuvre, idle or route exclusion,
shrinking or replacing the deadline, adding a second travel path, putting an
affirmative into the declining path, dropping either condition from the
confirmation, matching the dialog loosely, hoisting the branch above the retreat
or into the pre-split list, dropping the mission's name from the give-up, adding
a reading count to the repeating line, dropping the abandoned names from the
status line, ignoring the session decline list, recording the name on every
reading rather than once, keeping the `(N of 3)` counter, stripping at the first
space instead, and counting only mouse effects — or the whole history — as
acting.

**Not verified: any of it running.** In particular `yes_dialog_button` has never
been read out of a live UI tree here — which is why the affirmative is
identified by the dialog's shape and not by that name — and the whole path needs
a mission that genuinely cannot progress, which is not something to stage. What
to watch on the first one: `ABANDONING '<mission>'` in the status line, then
`Travelling to '<station>' to give the mission back.`, then
`Quit the mission '<mission>' with the agent.`, then
`This is the 'Quit Mission' confirmation I just asked for -- confirm it.`, and
then the status line's `abandoned and now declined this session:` while the bot
takes other work. A stall at the confirmation means the dialog is not a
two-button `no_dialog_button` pair after all, and the tell is 200 readings of
the abandonment line followed by the session ending.

## A decline costs standing, so the entry that armed it has to be nameable

`decline-mission` is matched as a **substring** of the offered mission name, and
it was parsed with no empty check at all:

```elm
( "decline-mission"
, AppSettings.valueTypeString
     (\missionName settings ->
         { settings | missionNamesToDecline = String.trim missionName :: settings.missionNamesToDecline })
)
```

The empty string is a substring of every mission name, so one `decline-mission=`
line with nothing after it puts `""` in that list and hands back **every mission
the agent ever offers**, one standing hit at a time, while the log reports each
as an ordinary skip. **The codebase already knew.** `missionNameFromTracker`'s
own comment says an empty entry "is a filter that declines every mission the
agent ever offers", and `splitSettingIntoNames` filters `String.isEmpty >> not`
for exactly that reason. The tracker side was guarded and the settings side was
not.

**Rejected rather than dropped, and the two conventions already here are what
decide it.** An empty value has two documented meanings in this file and neither
covers this one. `nonEmptySettingValue` reads it as *unset*, which is how
`short-range-ammo=` switches the ammo swap off from the web console without
deleting the line. `splitSettingIntoNames` drops it, because a trailing comma is
how one gets written by accident and the other entries on the line still carry
what was meant. Neither applies where the whole assigned value is empty: nothing
is left to read the intent from, and "I meant to delete this line" and "I meant
to paste a name here" want opposite behaviour. Dropping picks one without saying
so, which is this repo's signature failure; `AppSettings`' own answer to a value
it cannot use is an `Err` naming the setting, which `valueTypeInteger` and
`listAllSupportedValues` already give. `valueTypeNonEmptyString` is that answer
for the four settings that name one thing.

**The price is stated rather than hidden.** `BotFramework` answers a settings
parse error with `InternalFinishSession`, and that is the same event the web
console's live settings change sends — so a bad value typed mid-run ends the
session. That is what every other unusable value in the file already costs, and
it is paid here on a string one keystroke from declining everything.

**Three other handlers had the identical unguarded shape**, and all three are
now guarded by the same helper:

| setting | what an empty value did |
|---|---|
| `agent-name` | `stringContainsIgnoringCase ""` matches every agent in the station, so the bot picks the first row rather than the documented default of the first *available* agent in this station |
| `drone-type` | `droneNameNeedle` becomes empty, so the restock drags whatever item the hangar view lists first |
| `avoid-rat` | nothing, because **nothing reads `avoidRats` at all** |

That last one is a finding rather than a fix. `avoidRats` is written by the
parser, carried in `BotSettings`, documented in the bot's own header and
reported by `--help`, and read by no decision anywhere — a setting that does
nothing. It is guarded anyway, because "no filter is armed" is a fact about a
dead setting rather than a property to leave a hole under, and
`AvoidRatIsParsedAndNeverRead` pins the three uses so a fourth has to be
noticed. **That setting has since been removed from this bot** — see "A setting
this bot documented, parsed and never read" below — so the guard now covers the
three that remain, and the case that counted the uses is retired.

**The second half is that a decline said why.** The branch printed
`Skip this mission (<name>) using '<label>'.` and nothing else, which reads
identically whether the match came from an operator's own `decline-mission`
line, from this session's `missionNamesAbandoned`, or from an entry matching
everything. Run 25 clicked Decline 105 times, so a wrongly armed filter is a
bill that starts running on the first offer. `declineMatchFromLists` now names
the list **and the entry** — the entry because a list of several does not say
which one matched and a substring does not read back off the mission's name:

```
++ Skip this mission (Illegal Activity (1 of 3)) using 'Decline' -- the 'decline-mission' setting matches it on 'Illegal Activity'.
```

The setting is asked first and wins a tie, because it is the answer an operator
can act on: an entry they wrote is a line they can delete, where the session's
own list is gone at the next restart. The give-up beside it carries the same
clause, which matters more there than here — `I want to skip this mission but
see no way to.` has never fired in any recorded run, and a branch that fires
once a session is the one whose single line has to carry everything.

**No warning for a short entry.** A one-character entry matches almost every
mission, and the obvious follow-up is to warn about entries below some length.
There is nothing to place such a threshold in: the only entries the corpus
carries are `Illegal Activity` and `Survey Rendezvous`, and the abandoned list's
entries come from `missionNameForDeclining`, which strips only a `(N of 3)`
suffix. That is no distribution at all, unlike the 44-versus-32,585 gap the
message-box escalation sits in. With the empty value rejected the remaining
cases are all deliberate, and the decision line now names the entry on the
**first** offer it refuses, which is the evidence a later threshold would need.

**Verified without a live client**, in
`tools/macos-host/tests/test_decline_mission_entries.py` (34 cases; 35 until #125
retired `AvoidRatIsParsedAndNeverRead` along with the setting it counted). Both
rules are executed through the real `Bot.elm` in `elm repl` rather than restated:
the parser is asked what it does with an empty value for each of the four
settings,
with the three that mean *unset* by being empty and the three comma-separated
lists asserted unchanged beside them; and `declineMatchFromLists` is asked which
list refuses a name, on which entry, which of the two wins a tie, and what it
would have printed for the empty entry the parser now refuses to build. The
wiring is read out of the source through a whitespace-collapsing reader. The
corpus is asserted as the relation a decline-everything filter would break — a
run that declined anything also accepted something — rather than as the issue's
own counts, which a growing corpus would turn red.

Confirmed by mutation, **fourteen** of them, each failing a named case:
accepting the empty entry, dropping it silently instead of rejecting it, judging
the untrimmed value, putting `decline-mission` back on `AppSettings
.valueTypeString`, applying the guard to `short-range-ammo` or to the list
settings, asking the abandoned list first, collapsing the two lists into one
labelled as the setting's, naming the list without the entry, dropping the
reason from the line that clicks the button or from the give-up beside it,
giving `shouldDeclineMission` its own copy of the matching rule, dropping the
entry from the sentence — and, on the tests' own premises, giving `avoidRats` a
reader.

**Two mutations survived the first time and both were real holes.** The guard's
own `String.trim` was unreachable through `parseBotSettings`, because
`parseSimpleListOfAssignments` trims every assigned value before a handler sees
it — so a guard that only worked because its caller trimmed passed every case;
`valueTypeNonEmptyString` is now asked directly. And the reason clause was
asserted over the whole branch, where the give-up's copy of it satisfied the
assertion with the clicking line reverted.

**Unverified: any of it running, and the incident the issue was filed on.** The
operator's report of `Save A Man's Career` being declined at a cost in standing
is **not explained by this and is not claimed to be**. Nothing in
`~/eve-bot-logs` records it: the decline branch has fired 486 times across every
recorded run, on `Illegal Activity (1 of 3)` (480) and `Survey Rendezvous` (6),
both configured, and `Save a Man's Career` appears once in the whole corpus — in
run 1, where the bot **accepted** it. The shipped `run_mission.sh` carries one
non-empty entry, so the empty-filter failure was latent rather than active and
cannot be what happened either. What the issue's second half points at is the
indiscriminate message-box matcher, which is #101's and merged as PR #109; this
change deliberately does not touch `closeMessageBoxByDeclining` or
`parseMessageBoxesFromUITreeRoot`, and a case asserts both are as #109 left
them. What to watch on the next run that declines anything is the new clause
naming a list and an entry an operator recognises — a decline whose clause names
an entry nobody wrote is the case this was built for.

## A setting this bot documented, parsed and never read

`avoid-rat` named a rat to leave alone. The mission runner listed it in its own
header, `--help` reported it (that text is generated from the header by
`bot_help.py`), and `parseBotSettings` filled `BotSettings.avoidRats` from it —
and **no decision anywhere in this bot ever read that field**. Three occurrences
and no fourth: the default, the parser handler, the field in the record type.
Elm has no dynamic field access, so three is a proof rather than a search that
came up empty. An operator who set it got exactly the bot they would have got
without it, while `--help` told them otherwise. It is **removed** rather than
implemented, and can be brought back if it is ever wanted.

**The argument is about this app, not about the repo.** #125 as first written
said the repo had declined to grow a negative name list beside `attack-object`'s
positive one, and that is false. `eve-online-saxrat` (`Bot.elm:772`) and
`eve-online-combat-anomaly-bot` (`:442`) both implement `avoid-rat`, wired from
the overview's rows through `getRatsToAvoidSeenInAnomaly` and `FoundRatToAvoid`
to three decision sites that skip a scan result or leave the anomaly. saxrat's
was proved to *execute* in `elm repl`: with `avoid-rat = Infested Carrier`,
`shouldAvoidRatAccordingToSettings` answers `True` for `Infested Carrier`, `True`
for `infested carrier` and `False` for `Sunder Alvi`. Both implementations stay
untouched. What is true is narrower and is enough on its own — this app
documented and parsed a setting two sibling apps honour, so its copy was a
promise it could not keep.

**A future implementation here would not be a port.** saxrat's rule is
*anomaly*-granularity: it abandons the whole anomaly a named rat was seen in.
The mission runner has no anomalies, and what run 27's operator wanted was to
decline a single *target*. That is a different rule in a different place, so
starting from saxrat's would be starting from the wrong shape.

**The one cost of removing a setting rather than ignoring it.**
`Common.AppSettings` answers an unrecognised key with `Unknown setting name
'avoid-rat'`, so a settings file still carrying the line now ends the session at
startup instead of doing nothing. Nothing carries it: not `run_mission.sh`, not
`run_saxrat.sh`, not `bot_help.py`, and none of the 49 recorded runs in
`~/eve-bot-logs`. The header says what happened to the setting and that the line
has to be deleted, beside the same note `activate-module-always`' removal left,
because that paragraph is what `--help` prints.

**Verified without a live client**, in
`tools/macos-host/tests/test_avoid_rat_removed.py` (14 cases). The removal is
executed rather than restated: the real parser is asked what it does with
`avoid-rat=Infested Carrier` (rejects it, naming the key), what one such line
does to a whole settings string (rejects that too), whether `run_mission.sh`'s
own string still parses, and whether the three named settings beside it still
take a value and still refuse an empty one. The source half asserts zero
occurrences of the field and no bullet for it in the section `--help` prints,
through a block reader sliced by **indentation** — `parseBotSettings` is one long
list literal, and the readers that stop at a blank line or a record's opening
brace have already cost PRs #147, #156 and #159 an assertion that passed having
read nothing.

**The general rule is asserted over every EVE app**: one whose `parseBotSettings`
accepts `avoid-rat` must read `avoidRats` somewhere outside the default, the
handler and the record type. That is what goes red if saxrat's read is ever
deleted — the mistake #125 as written would have caused — and what goes red if
another app grows the parser half without the decision half. The converse shape,
**documented but never parsed**, is `eve-online-wingus`' today and is #161's: it
ends a session at startup rather than doing nothing, and fixing it is not this
change, so it is deliberately not asserted here.

Confirmed by mutation, seven of them, each failing a named case: putting the
setting back whole — field, default and parser entry, with no read — which is the
silent reintroduction and fails eight cases including the cross-app rule; putting
the field and its default back *without* the parser entry, which no repl case can
see and which the source half catches; restoring the `+ avoid-rat` bullet to the
header; gutting the paragraph that tells an operator to delete the line;
deleting saxrat's `shouldAvoidRatAccordingToSettings` read; deleting the combat
anomaly bot's; and narrowing the key reader to `AppSettings.valueType`, which is
what `bot_help.py` matches on — the combat anomaly bot is on `PromptParser` and
its thirteen keys then read as none, so the cross-app rule would pass by seeing
nothing.

## A message box the answer does not close is bounded, and the bot stops answering it

Dismissing message boxes is the first thing `generalSetupInUserInterface` does
after the pause menu, and that list is evaluated **above the docked-or-in-space
split** — above the two retreats, the pod recovery, the wind-down and the
abandonment. `closeMessageBoxByDeclining` had no counter, no bound and no
give-up, so it answered a dialog the same way on the first reading and on the
thirty-thousandth.

Run 30 found the window that does not care. Something the client draws on the
`MessageBox` widget — an emoji picker, by every sign — carried a
`no_dialog_button`, so `Dismiss it using No.` was the right-looking answer and
the box was still there afterwards:

```
++ Dismiss it using No.        32,585 readings, 3h44m
```

**Nothing else in the bot ran for any of them.** The section above is the other
end of the same incident: `abandonMissionThatCannotProgress` held a live verdict
on `Technological Secrets (1 of 3)` throughout and its own 200-reading bound
never fired, because the branch holding it was unreachable. The status line
counted `quitting it for 10811 of 200` while the tree never reached the branch
that reads the number. This is the fifth time this repo has paid for an
unbounded wait — the drone recall before #11, the ammo swap's ramp wait before
#38, the loot window before #53, the locked-target wait alongside the learned
lock range — and it is worse only in position.

**What is bounded is the box, not message boxes.** #54's standing lesson holds:
the automatic reply to a dialog stays the declining one, because these guard
destructive actions and the "Quit Mission?" one has cost a mission's standing
already. `closeMessageBoxByDeclining` still contains no affirmative at all.
What #101 adds is a ladder over one box: the ordinary answer for
`messageBoxAnswersBeforeEscape` (60) readings, then **Escape** at it for another
60, then `closeMessageBox` answers `Nothing` and the rest of the tree runs.

**`Nothing` rather than an alarm is the point.** The box stays on the screen and
every branch below now works around it, which is worse than a closed box and
incomparably better than nothing running at all — run 30's abandonment would
have reached its own bound and ended the session naming the mission, which is
what an operator can act on.

**The count is per box, and the identity is what the box says and offers.** A
global tally of dismissals accumulates across a run that legitimately closes
many dialogs: runs 10, 22, 25, 26 and 27 answer 175 separate stretches of
message box between them. `clearStrayContextMenu` compares its menu across
readings for exactly this reason. The identity is the box's own display texts
plus its buttons' `_name`s and labels, and deliberately **not** its display
region — `strayContextMenuStuckTicksThreshold` records what a coordinate-based
identity costs, which is a widget re-rendered each tick differing sub-pixel
while looking identical, and a count that therefore never accumulates at all.
The side effect is that a dialog whose wording changes starts a fresh count,
which is the wanted direction.

**60 is placed in a gap rather than cut through a distribution.** Counting
consecutive readings with a message box on the screen, the 175 stretches in the
runs that recovered are 6, 10, 11, 18, 20 and 44 readings long and nothing else
— 44 is run 26's worst, the median is 6, 1,267 readings in all — while run 30's
one box ran to 32,585. Nothing recorded lies between 44 and the incident. A
stretch is an upper bound on any single box, since one can hold several dialogs
in succession, so the real separation is wider still.

**Escape rather than Ctrl+W**, though the issue offers both and Ctrl+W is
confirmed live as the client's own "close the active window". Escape is what
this codebase already escalates with — `beginCascade` presses it rather than
right-clicking a computed empty point, `clearStrayContextMenu` presses it at a
menu that has not advanced in three ticks — and it needs no focus. Ctrl+W does:
`lootWindowRefusesToCloseTicks` records a version that pressed it at an
unfocused window 650 times in one run and closed nothing, and the live recovery
needed the title bar clicked first. Clicking an unidentified modal to focus it
is a click into a dialog nobody has read. A naked Escape can open the client's
own pause menu — `closeSystemSettingsMenu` records that happening live from
exactly this key — and that is covered rather than risked, since that branch is
the entry *before* this one in the same list.

**It says so, once, and then keeps saying so in the status line.** 32,585
identical lines is what an operator got, and `stall_watch.py` deduped them into
a single alarm so nothing escalated. The give-up names the box and both rungs it
tried, at the root, on the reading it is reached —
`dronesLeftBehindLastChange`'s mechanism, for its reason: the verdict is settled
in the memory update, and the branch that would otherwise say so is precisely
the branch that has just stopped running. The status line then carries
`message box N/120` continuously, with `(pressing Escape at it)` and
`(GIVEN UP ON, still open)`, which is the only thing on a reading that says a
box is still there once the decision line has gone.

**Narrowing `parseMessageBoxesFromUITreeRoot` is explicitly not the fix**, and a
test asserts it is unchanged. It matches `pythonObjectTypeName == "MessageBox"`
and nothing else, so anything the client implements on that widget is a message
box as far as the bot is concerned — but treating the emoji picker leaves the
shape, and any window on that widget the declining answer does not close
reproduces run 30 exactly.

**Verified without a live client**, in
`tools/macos-host/tests/test_message_box_standoff.py` (42 cases, up from 35).
The four pure rules are executed through the real `Bot.elm` in `elm repl` rather
than restated
in Python — the standoff folded over the states a run passes through, the ladder
at both of its boundaries and either side of each, the identity over boxes built
out of real UI-tree nodes, and the give-up line — and the corpus is recounted as
the *relations* the threshold rests on: every stretch in a run that recovered is
below the escalation, run 30's is more than ten times the give-up, and nothing
but the box ran in run 30 after the onset. The wiring, the placement and the
parser's deliberate unchangedness are read out of the source through a
whitespace-collapsing reader. Confirmed by mutation, **fifteen** of them, each
failing a named case: the escalation cut to 44 so it slices the recorded
distribution, either boundary comparison moved by one, the give-up written as a
bare number instead of a multiple, the give-up retuned, the give-up applied only
in a band so the ladder wraps back to answering, the identity dropping the box's
text or its buttons, the count not resetting on a different box, the count
surviving a reading with no box at all, the give-up raising
`askForHelpToGetUnstuck` instead of handing the tree back, the escalation
clicking the box instead of pressing Escape, the give-up line dropping the box's
name or its truncation, the status line dropping the clause, and the branch not
consulting the verdict at all.

**Unverified: any of it running on this bot.** No mission run has been flown
since, and the box that caused this had been closed by hand long before it was
investigated — so which node an emoji picker presents as, and whether it carried
a `no_dialog_button` at all, is still inferred from `Dismiss it using No.` being
printed on the path that requires one. The identical ladder **has** now run, in
saxrat's run 11, and what that settles and what it does not is in "The ladder is
not what froze; the readings stopped coming back" below: the counter advances
once per reading exactly as documented, Escape's whole live outing is one press,
and the give-up rung has still never been reached by either bot. What to watch
on the first mission run that meets one: `message box N/120` in the status line
climbing at all — on a healthy run it should appear briefly and vanish, since
the recorded dialogs close in 6 readings — with the dialog **named** in the same
clause, then the Escape line, then the give-up, and then ordinary decisions
resuming while `(GIVEN UP ON, still open)` stays in the status line. A give-up on
a run where boxes are being answered normally means the identity is churning less
than it should; a `message box` clause that never appears at all on a run that
dismisses one means the standoff is not being written.

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

## Docking is a run-in the ship has to fly, and commanding it again restarts it

`travelToStationByName`'s last step right-clicks the route panel's first marker
and takes the menu entry containing `"dock"` or `"jump"`. That is right for a
**jump**, which is instantaneous once commanded, and it cannot finish a **dock**.

Run 27 measured the difference. The ship reached Amarr with the station 17 km
off and never docked: **1,227** readings of `A route is set`, **414**
`Click on menu entry 'Dock'` decisions across **117 readings**, and in the
client's own log **36** × `Setting course to docking perimeter` plus 5 ×
`Session change already in progress`. The two accepted course-settings at
readings 346 and 467 are **486 seconds apart** — the run-in's own length, so the
ship had precisely enough time to arrive — and the bot commanded Dock on **120
of the 121 readings in between**. The control is one click on the Selected Item
panel's `selectedItemDock` at the same 17 km, which docked the ship about eight
minutes later with no further input.

**The bug is not the mechanism, it is the repetition**, and this is the thing
most likely to be missed: a panel click repeated every reading restarts the
perimeter run exactly as effectively as a cascade click did. So the fix is two
parts and the second is the essential one.

**`DockingRunIn` is what stops the re-command.** The client writes
`Setting course to docking perimeter` on `notify` when it accepts a Dock, and
that sentence is the *only* evidence a reading carries that a dock is under way
— `ShipManeuverType` has no docking member (Warp, Jump, Orbit, Approach, Range,
Align, and none of them is this), the ship keeps its ordinary UI, and the
station's overview row looks like any other. Latched in
`updateMemoryForNewReadingFromGame` for the usual reason: a reading's entries
are gone by the next one.

**That is also why the jump case is untouched, with no test for which leg the
bot is on.** The client writes the line for a dock and never for a gate jump,
so the latch cannot be armed by a jump and the declining branch is unreachable
on one. The alternative — predicting the menu's contents before opening it — is
both more machinery and less certain than the client's own statement.

**What ends the wait is not a clock**, and picking a number here is the mistake.
Eight minutes is roughly sixty readings, an order of magnitude past every
settling window in `Bot.elm` (`approachIndicationTrustedForTicks` is 10, so ten
readings into run 27's dock the old guard would have commanded another one), and
a station 200 km off is a longer run-in and just as legitimate. The wait is
bounded by the run-in *working*: the smallest range to a station seen since the
course was set, and how long it has been since that fell. A ship that is closing
gets as long as the distance requires; a ship that has stopped closing gets
`dockingRunInPatienceReadings` and then the command again. That is
`stall_watch.py`'s `APPROACH_PATIENCE` — same question, same signal, same unit,
same value of 20 — so the bot and the watchdog watching it cannot disagree about
what a stalled approach looks like.

An unreadable range counts as **no gain**, not as a reason to drop the latch.
`Nothing` covers no station on the overview, a row that is not rendered, and a
distance in AU, and none of them is evidence the ship is closing. The worst that
degrades to is one Dock per patience window against run 27's one per reading.

**The panel click is the other half, and it is `selectThenPanelAction`'s
argument on the one branch never wired to it** — `selectedItemButtonNamed`'s own
comment already names `selectedItemDock` among the buttons reachable that way,
and `selectedItemApproach` is recorded taking the ship from 0.0 to 585 m/s after
a cascade achieved nothing across 180 decisions. `dockAtDestinationStation`
applies three conditions, each guarding a way it could act on the wrong thing:
the route panel rendering **exactly one** `AutopilotDestinationIcon` (otherwise a
station on an intermediate system's gate grid is a station too, and docking
there would end the trip in the wrong place with every log line reading like
success); `selectedItemIsOverviewEntry`, because the panel acts on whatever is
selected; and the Dock button being present at all, which is absent out of
docking range and is the natural gate between the two mechanisms — the same
shape as `selectedItemActivateGate`. On that last one it falls back to the
cascade rather than waiting, which is why `selectThenPanelAction` could not be
reused directly: its answer to a missing button is to wait and eventually ask for
help, which here would strand a ship that simply has to fly further first.

**A fourth condition, and the one those three were missing.** #98: the marker
count says the destination is in *this system* and says nothing about the
destination being a station, let alone which one — so "nearest" filled the gap,
and the nearest station to a ship in an undock is the one it just left, at 0 m,
with its Dock button necessarily offered. Run 28 docked straight back in **498
times** while the tracker's own next step read `Undock`. The guard is identity
plus a latch: `undockedFromStationAfterReading` carries the name from the one
reading that can name it — not docked now, docked in the last reading — and drops
it on the warp, the ship being demonstrably somewhere else.

Neither cheaper signal works, and both were tried on the corpus before this was
written. **The tracker's step does not**: bucketing every zero-metre dock by the
step on the same reading gives 357 under `Destination Set` and **none** under
`Undock` or `Abort Undock`, because those land on *docked* readings where the bot
correctly clicks Undock and the dock decision happens on the next one, in space.
**Distance does not either**: 0 m reads the same on the way out as on the way in,
so no floor separates "just undocked from" from "just arrived at".
`lastDockedStationNameFromInfoPanel` on its own does not, either — it still names
the agent station on the trip *back* to it, where docking is the entire point.

The fail direction is stated: a name neither window read declines to block, which
leaves the dock available. Refusing on a name nobody read would strand a ship
that has arrived, and a declined dock costs only the panel optimisation — it
falls through to the cascade, which still travels the route.

**Verified without a live client**, in
`tools/macos-host/tests/test_docking_run_in.py` (31 cases). The rule is
*executed* through the real `Bot.elm` in `elm repl` rather than restated in
Python: a run-in folded over 200 readings of a falling range survives all of
them, one folded over exactly `dockingRunInPatienceReadings` readings without a
gain ends and one reading fewer does not, a growing range is not a gain, an
unreadable one is not either, docking clears the latch and a second course-
setting restarts it and counts. The marker is read out of the source and checked
against every `Setting course to docking perimeter` line in
`~/Documents/EVE/logs/Gamelogs` — all of them on `notify` — and against the
three carried into run 27's own log by the game-log channel, which is what makes
the latch reachable rather than a guard resting on a sentence the bot never
sees. Run 27's own measurement is re-derived from the log by the test, in
readings rather than decision lines. Confirmed by mutation, thirteen of them,
each failing a named case: the patience comparison moved either way, the counter
pinned, a falling range no longer counting as progress, the marker drifting from
the client's wording, docking not clearing the latch, course-settings not being
counted, the jump entry dropped from the cascade, the matcher moved to `info`, an
AU distance becoming a real range, the panel pressed without confirming what is
selected, the destination no longer required to be in this system, the dock leg
no longer consulting the latch, and the status line dropping the count.

**Unverified: any of it running.** The re-command hypothesis is still an
inference — nobody has watched a single un-repeated Dock succeed from 17 km, and
the panel click succeeding is the one directly observed part. Two premises have
never been read off a live client: that the route panel renders exactly one
marker when the destination is in the current system, and that the destination
station appears on the overview as a displayed row at all. **Both fail safe** —
the panel path simply never fires and the bot behaves as it does today, with the
run-in guard still in place, which is the half that matters. What to watch on
the first run that docks: the status line's `docking run-in (1 course-setting(s),
… m, 0/20 since closer)` with the count staying at **1** and the range falling,
then the dock. A count climbing is the run-in still being restarted; a run-in
that expires its patience every twenty readings while the range never moves is
the station not being on the overview, and the tell is `range unreadable` in the
same clause.

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
doing its job" is repeating the mistake.

**#76 is that mistake found in one more place, and it cost every swap in every
run.** `weaponIsFiring` — the predicate deciding both whether the ammo swap may
start and whether it presses the switch-off — read `isActive`. Run 21's first
weapon read `ramp_active` `True` on 69 of 674 module clauses and `False` or
absent on the other 605, with `isInActiveState` `T` on all of them, so on nine
readings in ten the swap decided no gun was firing, skipped the switch-off and
opened a menu on a running gun. `GUNS OFF` appears zero times in that run. It now
reads `isInActiveState` and is called `weaponIsSwitchedOn`, because the old name
is the misreading.

**The separation is total across the whole corpus, which is what makes it a
measurement.** Over runs 11, 18, 21 and 22 the branch taken is predicted by
`ramp_active` with no exceptions at all:

| decision | readings | `ramp_active` | `isInActiveState` |
|---|---:|---|---|
| `Stop this weapon before loading` | 58 | **`T` on every one** | `T` |
| `No weapon reads as firing` | 260 | **`F` on every one** | `T` |

One counterexample anywhere would break it, and there is none.

**And it presents as a run-to-run coin flip, which is why one run could never
settle it.** Run 22 reached `GUNS OFF` **29** times on the same code and build
that gave run 21 **zero** — whether a run catches a gun mid-cycle at the moment
a verdict comes due is luck. A run that never swaps and a run that swaps
sometimes look like different bugs and are the same one.

`isInActiveState` is the entry that means *switched on*, and it backs three
things: since #50, whether the ammo swap's switch-off landed; since #72, a report
of the client having taken the guns back; and since #76, whether a gun needs
stopping before a load. That third one is the **positive** direction, which #50
had ruled out — a considered departure, and the reason it is safe is that the
claim is unchanged. Run 11 showed `True` for eighteen readings on a gun that
fired nothing at all, so it is still not evidence the module is doing its job;
what it is evidence of is the toggle being on, which is precisely the condition
the client's own refusal names (`while it is active`). Reading it as "the guns
are working" would be #12 and #34 a third time and nothing does.

The keep-active filter and `decisionToKillRats` still consult `isActive`, which
#39 refused to rewire on one sample and #76 still refuses.

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
| `isDeactivating` | `False` throughout that sample; **`True` in run 11**, on every reading a swap had a gun switched off | switching off, cycle not yet finished — see below |
| `effect_activating` | `0`, except a single `1` at 175.3s, 2.6s before a cycle began | a brief pulse at **activation** |
| `waitingForActiveTarget` | absent until 141.3s, then `0` on all four at once | `0` = not waiting; appears late, needs more observation |
| `online` | `True` throughout | |
| `blinking` / `grey` / `quantity` | `0` throughout | |
| `autoreload` / `autorepeat` | `1` / `1000` throughout | settings, not state |
| `isMaster` | `1` on the high slot only | identifies the weapon group's master |

**Capturing the switch-off is what the status line was for.** The mission runner
prints five entries every reading —
`Top-row modules (ramp_active/isInActiveState/isDeactivating/effect_activating/waitingForActiveTarget)`
— with `T`/`F` for a boolean, the number for a numeric entry, and `-` for an
entry **absent from the tree**, which is a distinct output from `F` and `0` on
purpose. So a run that performs an ammo swap records the switch-off without
anyone watching. The other seven entries are parsed and available but not
printed, since this line goes out thousands of times a run and all seven were
constant across the whole sample.

### Run 11 recorded the switch-off, and it says the click lands

Four ammo swaps, and all four read identically. The column goes
`T/T/F` → **`T/F/T`** on the reading straight after the swap clicks the module
button: `isInActiveState` `True` → `False` and `isDeactivating` `False` → `True`
together, with `ramp_active` still `True` because the gun is finishing its cycle.
**The switch-off lands, first time, in one reading**, which is the observation #35
and #39 both asked for and neither had.

Two readings later the column becomes `F/T/F` and stays there. The guns are
switched back **on**, and **not by anything in the bot** — see "The switch-off
does not hold" below, where #72 read the dispatched effects across that window
and found no press of the button in either recorded run. This file used to
attribute it to `decisionToKillRats`; that was wrong, and it was wrong in the
direction that made the swap's own failure look like correct behaviour by its
intended owner. What is true either way is that the swap kept going: its
`gunsSilencedTicks` counter consults nothing the module says (deliberately, #38)
so it counted to its bound of 20 while the guns had been back on since reading 3.

**`isInActiveState` is decisive about the switch-off and says nothing about the
guns working.** In that same window the weapon fired *not once* — all 33 outgoing
`(combat)` lines came from a drone, against 195 gun lines across the run — while
`isInActiveState` read `True` and `ramp_active` sat pinned at `False` for
eighteen readings. So the flag means the toggle is on, not that the gun is doing
anything, and treating `Just True` as "the guns are working" would be #12 and #34
a third time. What it supports is the negative: `Just False` is the client
confirming a switch-off, and `Just True` after a confirmed `Just False` is the
client saying it has been undone.

**One field is now wired to a decision; the other eleven are not.** #50 gives the
ammo swap `moduleReadsSwitchedOff` and `moduleReadsSwitchedOn` over
`isInActiveState`, and both are `Just`-only so a build without the entry behaves
exactly as before. The direction is one-way and asserted as such: consulting the
module can only make the swap release the guns *sooner*, never hold them longer,
which is what keeps #38's deadline independent of a signal that could stall it.
`test_module_button_dict_state.py` pins that nothing else reads any of the twelve.

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

**A single reading is not evidence, and that is now the rule.** `0` is a legal
armour percentage, so the filter above cannot touch a garbage read that lands on
it — and it is the worst value to be wrong about, because it clears every
threshold at once. Run 11 printed `Armor reached 0% (now 0%)` forty times with
the armour really at 82-96%: one corrupt reading, held by `lowWaterMark`'s `min`
for ten readings, because none of the real values that followed reached
`runAwayRearmPercent` and released it.

Every consumer of a gauge now reads `BotMemory.hitpoints.<gauge>.believed`, the
**healthier of the last two believable readings**, so a drop has to survive a
second look before the low-water mark, the frozen-reading guard or the retreat
sees it. Measured across the fourteen recorded runs: of the excursions where a
value is contradicted by the readings either side of it — 34 on armour, 200 on
shield — 22 and 127 are exactly one reading wide. Against the armour threshold
of 70 the raw gauge produces 20 firing episodes and this rule leaves exactly
one, run 10's genuine decline through `75, 75, 70, 65, 68, 60, 63, 60`.

**It delays; it cannot suppress.** On any non-increasing series the believed
value is the previous reading's, whatever the size of the step, so a hull losing
armour retreats one reading later than it used to and a hull genuinely at 0%
still retreats. The largest one-reading armour step in the corpus is 8 points,
which is what that reading costs.

**The damage window is deliberately not consulted here**, against the issue's own
first suggestion. Two reasons, and the first is decisive: armour does not repair
itself, so a hull sitting at 5% with a quiet 45-second window is a ship that
nearly died a minute ago, and "no damage, therefore ignore the gauge" would
disarm the guard exactly there — and on any host with no game log at all, where
`Nothing` reads as no damage. The second is that it would not have worked: run
11's three armour zeros arrived with 874, 1288 and 2006 hitpoints in the window.

**What it does not do is cure the parse.** #32's remaining half is still open. A
corrupt reading still arrives every few hundred readings; nothing acts on it,
and the status line says so in place and keeps a running count.

**Two-reading corruptions exist, and the rule does not catch them.** Stated
rather than left to be discovered: run 10's shield went `84, 14, 17, 84` and run
11's `96, 7, 7, 96`, and a rule wanting three readings would have removed those
four episodes across the corpus at the cost of a second reading of delay. Two
was chosen because the armour gauge — the one this issue is about — has exactly
one such episode in fourteen runs, and because the damage-rate guard is watching
a ship being taken apart fast either way.

**The shield's 9% and 12% below are single-reading excursions**, found while
measuring the above, and the calibration that rests on them is worth redoing:
run 5's shield reads `98, 12, 98` and its lowest confirmed value is 49, and
run 3's lowest confirmed is 20 against a raw 9. The 25 that `run_mission.sh`
ships was set from the raw minima. Not changed here — a threshold is its own
change with its own evidence — but it is not the number it was thought to be.
The same measurement says no recorded run's armour ever went below 59% for two
consecutive readings, so the armour threshold of 70 has fired on real evidence
exactly once in fourteen runs.

**Armour on this hull is not a second opinion, it is the whole tank**, and this
paragraph used to say the opposite. It read "the ship is shield-tanked, so
armour takes no damage until the shield is at zero", inferred from runs 2-8
where the armour gauge sat at exactly 100% while the shield reached 9%, 12% and
44% — and concluded that the launcher should ship
`run-away-shield-hitpoints-threshold-percent=25`. Those runs simply never got
into a long fight.

**This hull is armour-tanked**, which #119's own measurement independently
confirms: it repairs its armour and does not boost its shield, which is why the
shield ratio derives a consistent pool and the armour one does not. The shield
is a fuse rather than a buffer. Across the 9,461 readings taken under fire in
the 19 recorded runs that fought, the believed shield sits at or below 5% on
**60%** of them, and in every run whose shield fell at all it went from over 95%
to under 5% within 15 to 168 seconds *with the armour still reading 98-100%*,
and then stayed there for the rest of the fight. 0% shield is this ship's resting
condition, not a warning.

So a shield threshold of 25 does not guard anything — it trips a minute into
every fight and, since the low-water mark only re-arms above 90%, never releases.
Run 10 raised the retreat 142 times that way in one session and had to be
corrected live through the web console. `run_mission.sh` has shipped
`run-away-armor-hitpoints-threshold-percent=70` with the shield one disabled ever
since, and its own comments have said why for longer than this file has; #129 is
what finally propagated the correction into `Bot.elm`'s settings documentation,
which was still telling operators to "set the shield one".

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

### The threshold is a number about one hull, and the session works out which hull

That last sentence — carrying it to another ship fails silently in whichever
direction that ship is different — is issue #119, and the level 4 question is
what made it urgent: moving to a battleship changes the tank by a large multiple
in one step and the number does not move with it.

**The client states both halves of the arithmetic on every reading it is being
shot on.** The combat log says how much damage arrived, already summed
host-side; the gauge says how many percentage points it moved; their ratio is
the pool that moved, in hitpoints. This is the move `targeting-range` made when
it stopped asserting a lock range and learned one, and the move the host made
when it stopped assuming a Retina backing scale and read `UIRoot`'s own canvas
size.

**Why "make it a percentage of shield/armour HP" is not the fix**, since it is
the obvious formulation and it fails three ways. `ParseUserInterface.Hitpoints`
is three percentages of a maximum the client never states, so the bot cannot
evaluate "20% of my shield". It would put a common-mode failure in the one place
the design avoids one — this is the only one of the three guards that does not
read the gauge, so a corrupt gauge today costs two guards and leaves this one
armed, and a live comparison against the gauge would disarm all three at once in
the direction that keeps the ship in the pocket. And share-of-maximum is the
wrong control anyway: absorbing 20% of the tank in 45 seconds is routine at full
health and fatal at 25%.

**The measurement came before any bot code, and it is what chose the gauge.**
Over the 27,710 readings in the 22 recorded runs that carry this channel, the
shield ratio agrees with itself across runs and the armour ratio does not:
twelve runs reach enough shield observations to derive anything and answer 1833,
1855, 1885, 1909, 1921, 1922, 1924, 1942, 1944, 1958, 2028 and 2095 hitpoints —
a 14% spread — while the seven that reach enough armour observations span 2262
to 6550, a factor of nearly three. The reason is the second noise source the
issue names: **this ship repairs its armour and does not boost its shield**, so
armour points recovered while damage lands break the ratio outright and shield
points do not.

**The pairing is the trap, and it is not the obvious one.** `believed` is the
healthier of the last two readings, so on a falling gauge it *is* the previous
reading's value — which means the movement it shows at this reading is the
movement the *previous* reading's damage caused.
`shipScaleObservationFromReading` therefore takes `damageOnTheLastReading`.
Measured: the naive pairing yields 63 admissible observations and three runs
that derive anything, spanning 1108 to 2675; the lagged one yields 202 and
twelve runs, spanning 1625 to 2095. It does not merely lose evidence, it
disagrees with itself.

**Four things make an observation admissible, and the corpus places each.** Both
gauges believable at both ends; the other gauge unmoved (23 of the 179
damage-bearing shield drops are spills, and apportioning one needs the number
being derived); the movement between 2 and 60 points; and at least 150 damage.
The two bounds guard opposite directions and only one of them is about safety:

- **The floor is the dangerous direction.** Grouped by movement size, readings
  carrying at least 100 damage against a two-point drop imply a median of 7750
  hitpoints, three points 5900, four points 5100, and five points and up settle
  at 1900 to 2100. Every mechanism behind that — shield regeneration,
  quantisation of a small drop, damage summed a reading either side of the one
  the gauge answered on — shrinks the movement without shrinking the damage, so
  all of it reads as *more* tank than there is, which raises the threshold and
  keeps the ship in the pocket.
- **The ceiling is the cheap direction and exists for the corruption `believed`
  cannot see.** A single garbage reading never produces a movement, because the
  healthier of two readings is never the bad one; a *two*-reading corruption
  does, and run 10's shield went `84, 14, 17, 84` and run 11's `96, 7, 7, 96`,
  leaving believed movements of 67 and 89 points. 60 sits in a gap the corpus
  draws: the largest credible movement anywhere is 52 points against 1054
  hitpoints (implying 2026, squarely with everything else), the only two over 60
  that carry real damage are 70 against 653 and 80 against 475 (implying 932 and
  593, half of everything else), and eleven further movements of 62 to 89 points
  occur on readings carrying no damage at all.

**The statistic is the lower quartile, and the asymmetry above is what picks
it.** Pooled over the corpus the quartiles are 1909, 2083 and 2500 — a long high
tail and a short low one, individual runs reaching 29,133. Per-run lower
quartiles span 1833 to 2095, a factor of 1.14; per-run medians span 1980 to
2700, a factor of 1.36. What it costs is sitting a little low, which retreats a
little early.

**A spread test was measured and deliberately not built.** Refusing to derive
when the observations disagree with each other is the obvious extra
corroboration and the corpus says it would not work: the twelve deriving runs
carry inter-quartile ratios from 1.07 to 14.88 while answering 1833 to 2095, so
a test tight enough to bite would have refused four runs that were right — and
it would not have caught the gauge it needs to catch, since the armour ratios
(2.67 to 4.88) sit inside the shield's range. Corroboration is by count
(`shipScaleObservationsBeforeTrusted`, 6) and contamination is answered by the
quartile.

**What it costs on the hull it was calibrated on is bounded, and that is the
point.** `shieldHitpointsWhereTheThresholdWasCalibrated` is 1909, the corpus's
own pooled lower quartile, so this hull answers 1.0 by construction. Scaling
3500 by each of the twelve per-run answers gives **3360 to 3841** — every one
above the 3114 the worst surviving session absorbed and below the 4101 the
session that lost the ship peaked at. So the derivation moves the threshold only
*inside* the band the original calibration already established: it cannot
introduce a retreat on a session that survived, and cannot miss the one that did
not.

**Failure is today, exactly.** No usable derivation means the configured
`run-away-incoming-damage-threshold` unchanged, which is what ten of the 22
recorded runs would get and what a host with no combat log already gets, and
`-1` stays `-1` — no derivation may switch a guard back on that an operator
switched off. Reaching six observations takes between 57 and 2,710 readings
depending on how hard a run is fought.

**The per-reading comparison stays gauge-free**, which is the property the whole
change is built around rather than a detail of it. The derivation feeds a number
computed at session scope from many readings;
`incomingDamageThresholdForThisShip` takes the setting and `ShipScaleMemory` and
nothing else, and neither the latch nor `runAwayIfLowHealth` reads a gauge. A
gauge that starts lying mid-session cannot disarm this guard, only fail to have
scaled it.

**`ammoSwapDisarmDamageBudget` deliberately does not inherit the scaling**, and
that is the ripple the issue asked to be asserted rather than inherited. It is
an eighth of the retreat threshold, and letting it follow the derived one would
move it to between 420 and 480 over the runs that derive anything — 480 is past
the 445 at which the recordings stop saying the fire does not escalate. The
eighth was measured against this corpus and this corpus is one hull's worth of
evidence, so the budget stays pinned to the number an operator set. The cost is
stated rather than hidden: on a hull whose setting nobody retunes, the retreat
re-derives itself and this budget does not, so the swap defers more often than
it needs to — the direction that keeps the guns firing.

**The one way this fails dangerously is the gauge being repaired.** A hull with
a shield booster would corrupt the readable gauge the way the repairer corrupts
the armour one here, in the direction that raises the threshold, and nothing in
this corpus calibrates a detector for it. Stated here rather than left to be
found.

**Verified without a live client**, in
`tools/macos-host/tests/test_ship_scale_from_the_gauge.py` (37 cases). The three
pure rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python — the admissibility rule against each of the four clauses and
against run 10's and run 11's own recorded corruptions, the estimate at both
sides of its evidence bound and against a set whose median and quartile differ,
and the scaling against a disabled guard, an absent derivation, the calibration
hull and a hull three times its size. The corpus is recomputed from
`~/eve-bot-logs` as *relations* rather than as the numbers above — the shield
agrees with itself and the armour does not, the lagged pairing yields more than
twice the evidence of the naive one, the reference is the corpus's own answer to
within 5%, every deriving run lands inside the calibrated band, and most runs
derive nothing at all — so a growing corpus cannot turn a true claim red. The
placement, the ordering against the latch, the gauge-free comparison and the
ammo budget's deliberate unchangedness are read out of the source through a
whitespace-collapsing reader.

Confirmed by mutation, **fourteen** of them, each failing a named case: the
ceiling raised past run 10's corruption and past run 11's, the floor on the
damage or on the movement dropped, the spill clause dropped, the ratio read as
hitpoints per point rather than as the whole pool, the observation reading the
live gauge instead of `believed`, the pairing taking this reading's damage
instead of the previous one's, the quartile replaced by the median or by the
minimum, the evidence bound cut to one observation, a disabled threshold scaled
anyway, the scale folded in after the latch instead of before it, and the ammo
budget pointed at the scaled threshold.

**Four mutations survived the first time and three were real holes**, all of one
shape: a case that reads a threshold out of `Bot.elm` and then asks only about
`constant - 1` and `constant` passes for *any* constant, including one that
admits everything. Dropping the damage floor to 0, the movement floor to 1 and
the evidence bound to 1 each did exactly that. Every one of those cases now
carries a fixed value beside the boundary pair — 20 hitpoints, a one-point move,
three observations — and asserts the constant is above it. The fourth was a
substring: `"shield.believed" in body` is satisfied by any one of the rule's four
gauge ends, so a version reading `believed` at three of them and the live value
at the fourth passed; all four are now named exactly.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one is the status line's `Ship scale:` clause — it should read
`0/6 observations` on a quiet run and climb on one that is fought, then
`shield reads N hitpoints from M observations` with N near 1900 on this hull. A
run that fights hard and never leaves `0/6` means the shield is not the gauge
taking the damage, which on this hull would itself be news. The failure to watch
for is N drifting far from 1900 on the ship the number came from, which would
mean the gauge is being repaired or the pairing has come apart, and the tell is
`dmg N/T` carrying a `T` that is not 3500.

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
state is the host, where one file offset now feeds four queues — see the
Architecture section, and `TailFanOutTest` for the assertion that each sees every
line exactly once in either drain order.

The status line reports the window, the threshold, whether the reading moved,
and **whether the host is carrying the channel at all**, because "0 hitpoints in
the last 45 s" reads identically whether the grid is quiet or nothing is
listening. It also now annotates an implausible gauge value in place: #32 was
filed partly on the status line printing `Shield: 385%`, which the retreat guard
had already rejected and never acted on while the log gave every appearance that
it had.

### The three guards are independent, and the independence is asymmetric

#120 established the property that keeps them independent: the damage-rate guard
must not become a function of the gauge, so that a corrupt HUD costs two guards
and leaves the third armed. #129 is the same relationship read the other way, and
it had never been written down. **Against a burst, the gauge-free guard is cover
for a corrupt gauge. Against attrition there is no cover at all** — the
gauge-based guard is the only instrument, and the gauge-free one is not weakly
armed, it is inert.

Run 36 is the shape. Believed armour walked from 95% to 17% over 34 readings,
about 53 seconds, under `Tower Sentry Gallente I` and a `Gallente Light Missile
Battery`. The 45-second damage window's peak *for the whole run* — 1854 against
3500 — arrived at reading 1290, with the armour still at 78% and the ship in no
trouble. At the ship's worst it read 1232, and at the moment the armour gauge
showed 1% it read 602. **The guard read higher while the ship was healthy than
while it was dying.**

**No threshold on that instrument separates those two, and the reason is
structural.** The combat log reports *gross* incoming damage; survival is
governed by *net*; and this hull's armour repairer is of the same order as the
fire it was under — run 36's armour climbed back from 17% to 48% while the log
still reported 1232 falling to 378 hitpoints a window, reaching 29% before that
window dropped below a thousand at all. A gauge-free instrument
cannot see the repairer, and cumulative damage over a longer clock is not bounded
by the tank on a ship that repairs, so a longer window does not rescue it either.
Only the gauge reads net.

**Three things that look like fixes and are not.** Lowering
`run-away-incoming-damage-threshold` trades this failure for the one 3500 exists
to avoid, since it sits between 3114 (the worst window any surviving session
absorbed) and 4101 (the window the session that lost the ship peaked at). #120's
EHP scaling does not reach it, because 1854 never approaches 3500 whatever the
hull is. And a fourth guard on time-to-death was measured and deliberately not
built: it separates run 36 (a projected 10.5 s to zero) from every genuine
decline in the corpus (next is 42.7 s), but it fires *later* than the armour
threshold already did in run 36 — 22 readings later — and it fires spuriously on
the two-reading gauge corruptions in runs 14 and 26 that `believed` cannot
filter. A guard calibrated on one incident, on the retreat path, that adds nothing
where the existing guard is armed, is not worth the corruption it inherits.

**What the corpus says about which guard has ever mattered.** Across all 36
recorded mission runs the retreat has fired **1054 times on the armour percentage
and 142 on the shield percentage, and not once on the damage window or on the
frozen reading**; `IncomingDamageMemory.retreating` has never been set on any
recorded reading. That is not an argument the gauge-free guard is useless — it is
calibrated to a burst nothing recorded has produced, and the session that did
produce one predates the channel. It is the measurement behind the asymmetry:
every retreat this bot has ever made came from a gauge.

**How rare the shape is** — #129 lists this as unmeasured. Run 36's is the only
one. Measuring it needs care, because the raw gauge minimum gets it badly wrong:
nine runs appear to reach 0-11% armour and run 36 looks ordinary. Every one of
those is a corruption two to four readings wide bracketed by 91-100% either side.
Taking the deepest level the *believed* armour was held at or below for four
consecutive readings — one past the longest corruption anywhere — run 36 answers
20% and the next deepest run answers 74%.

**So what shipped is documentation and a report, not a guard.** `attritionIsUnguarded`
is a pure rule over the two percentage thresholds, read by the status line and by
no decision, that says on every reading when the configuration leaves this shape
uncovered:

```
ATTRITION UNGUARDED: both percentage thresholds are off, and the damage window
only bounds a burst -- nothing here can see the ship being ground down. Set
run-away-armor-hitpoints-threshold-percent.
```

Both percentage thresholds default to `-1`, so that is exactly what a run started
without `run_mission.sh` gets. The bound is read off `runAwayIfLowHealth`'s own
`lowestArmor < threshold` rather than off the `-1` convention, so a threshold of
`0` — a keystroke away, and equally unable to fire — reads as uncovered too. The
status line also now carries the low-water marks themselves, which nothing
reported before: reconstructing run 36's decline meant replaying the whole log.

**Verified without a live client**, in
`tools/macos-host/tests/test_attrition_is_unguarded.py` (19 cases). The rule is
executed through the real `Bot.elm` in `elm repl` at both sides of each
threshold's boundary *and* against fixed values either side of it — the hole four
of #120's own cases had was a boundary pair that any constant satisfies. #120's
gauge-free property is re-asserted here because this change sits next to it: the
scaled threshold and the latch's `retreating` verdict are read out of the source
and must name no gauge, while the latch's *sample* record still may, since the
frozen-reading guard is what reads it. The corpus is recounted as relations —
the damage guard has never fired, run 36 is the deepest sustained decline, every
believed zero recovers within four readings, the shield collapses ahead of the
armour in every run that fought, most readings under fire are taken with the
shield already gone.

Confirmed by mutation, ten of them, each failing a named case: `&&` for `||` so
one armed threshold no longer counts as cover; `<= 0` weakened to `< 0` so a
threshold of `0` reads as armed; either clause dropped; the damage threshold
counted as cover; `runAwayIfLowHealth` made to decide on the rule; the
gauge-free threshold made to read `shipUI.hitpointsPercent`; the latch's verdict
made a function of the believed gauge; the status-line clause dropped; and the
launcher's armour threshold disabled.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one is `Retreat marks: shield N% / armour M% since healthy` on every
in-space reading, tracking the gauges as they fall and resetting to 100% when the
ship recovers past 90%. `ATTRITION UNGUARDED` should **not** appear on a run
started by `run_mission.sh`; if it does, the launcher's settings are not reaching
the bot. It should appear on every reading of a run started without it. What this
does **not** protect against is unchanged and stated plainly: a run configured
with no percentage threshold is exactly as exposed to attrition as it was
before — the change makes that visible, not survivable.

### Deciding to leave is not leaving, and nothing measured the gap

If the armour percentage guard *is* the attrition guard, then what stands between
the ship and the thing grinding it down is how long the retreat takes to execute.
Issue #136: run 36's guard fired correctly at 66% believed armour and the armour
went on falling to 17% while the bot printed `get out get out get out`, and **no
reading recorded any of that interval.** Reconstructing it meant replaying a log
by hand.

**The issue attributes the interval to the drone recall, and the corpus does
not.** `returnDronesToBay` sits in front of the warp (#11, #59), the client was
not answering Shift+R, and `Drones are not coming back -- click the drones window
…` appears 107 times in run 36 — which reads like the cause and is not. Those 107
are *decision blocks across the whole run*, 23 of which are inside the retreat;
the recall held it for **seven** readings, the drones came home at 53% armour,
and the decline that nearly killed the ship — 53% to 17% — happened **entirely
afterwards**, with the bot issuing `Get out -- warp to …` into a client that did
not warp.

**This was the first time retreat latency had been measured at all, and it needed
care in two places.**

**Deciding is not the same as being slow.** `runAwayRearmPercent` keeps the
verdict latched until the gauge recovers past 90%, so a retreat that *worked*
goes on firing all the way home: run 36 printed the verdict on 325 blocks and was
off the grid for the last two-thirds of them, recovering. Counting readings the
retreat was decided reports a completed retreat as a two-hundred-reading failure,
which is the instrument reporting success as failure. What is counted instead is
readings the retreat is decided **and the ship is not in warp**.

**The logs have no per-reading identity, which is itself part of #136's third
point.** `# [N.M]` is a framework step, and one step spans fifteen readings when
the client stalls — run 36's does. So the corpus was measured in decision blocks,
the same unit the issue's own "107 occurrences" and "325 times" are in, and the
end of an episode was proxied by hostiles leaving the overview, since no recorded
run carries the counter this change adds.

Measured that way, across all 36 runs the retreat fired on **29 episodes in 9
runs**, and the blocks spent still under the guns after a verdict are:

| | blocks |
|---|---:|
| median episode | **7** |
| longest, run 36 | **154** |
| longest outside run 36, run 10 | 142 |
| corpus total | 748 |
| of which the drone recall | **147 (a fifth)** |

**Run 36 is an outlier, not the norm** — twenty times the median. And the recall
is a minority everywhere it appears: 29 blocks against 125 in run 36, six of 142
in run 10, and **none at all** in run 31's two episodes (46 and 89 blocks) or run
11's (30). A slow retreat is fully reachable with the recall nowhere in it.

**So the ordering is not changed, and that is the finding rather than caution.**
Reordering would have bought run 36 seven readings, cost five drones, and left
the other 125 blocks exactly as they were. `droneRecallGiveUpTicks` is 60 and **has
never been reached in any recorded run** — the give-up names itself on every
reading it declines since #11, so zero is evidence rather than silence — so
tightening it would be retuning a number nothing recorded has approached, on the
retreat path, on n=1. The asymmetry the issue names is real and points the other
way from the bound: abandoning drones is a certain, bounded, recoverable cost and
losing the ship is not. It is the measurement that does not support acting on it
yet.

**The focus-recovery click is untouched for the same reason**, and for one more.
It is 45 of the 748 blocks, 20 of them in run 36 — and it cannot explain the 125:
the warp is a *mouse* action, select-then-press on the Selected Item panel, so a
client not taking keyboard input does not account for a warp that did not happen.
Why it did not is unanswered and is where the next run has to look.

**What ships is `retreatProgressAfterReading`**, a pure rule over a record, read
by the status line and by no decision — #135's precedent, and the right one while
the population is 29 episodes and one outlier:

```
RETREAT NOT EXECUTING: 34 consecutive readings deciding to leave with the ship
not in warp (worst this session 34).
```

**The verdict behind it is `runAwayIfLowHealth`'s own.** The counter lives in
`updateMemoryForNewReadingFromGame`, the only place that can write memory and the
one place that never sees the decision, so the four guards were extracted into
`retreatReason : RetreatCase -> Maybe RetreatReason` and both callers ask it —
`hitpointsReadingWithheld`'s rule applied to the most consequential condition in
the file. Same four conditions, same precedence, same inputs; what moved is where
they live. `lowestPercentSinceHealthy` went the same way for the same reason.

**Gated on the ship UI**, because that is `runAwayIfLowHealth`'s own gate — it is
only reached through `branchDependingOnDockedOrInSpace`'s `ifSeeShipUI`, and
without it a docked reading with the damage latch still set would count against a
retreat there is no ship to make. **Not** gated on the tree having reached the
branch: a reading where the retreat's condition is true and the ship is not
warping is a reading under the guns whatever the tree spent it on, and #101 is
precisely the case where that is the thing worth counting.

**Verified without a live client**, in
`tools/macos-host/tests/test_retreat_latency.py` (29 cases). The two rules are
executed through the real `Bot.elm` in `elm repl` — every guard at both sides of
its boundary *and* against fixed values either side, every precedence pair, and
the progress rule folded over whole sessions including run 36's own shape. The
corpus is recomputed as relations rather than as the numbers above (the recall is
a minority, a slow retreat exists with none of it in, the give-up has never
fired), so a growing corpus cannot turn a true claim red. The ordering, the
bounds, the single copy of the conditions and #120's gauge-free property are read
out of the source through a whitespace-collapsing reader.

Confirmed by mutation, **twenty** of them, each failing a named case: the armour
comparison weakened to `<=`; the armour guard asked before the shield guard; an
unanswerable reading counted as frozen; the damage guard reading the live window
instead of the latch; the frozen-reading guard's damage floor dropped; the mark
ignored so the retreat goes by one reading; the warping clause dropped so the
hysteresis inflates every retreat; the peak made the latest interval rather than
the largest; the peak discarded when the interval ends; the counter no longer
requiring the ship UI; the memory update carrying a second copy of the
conditions; the drone recall taken out of the warp path; the recall's give-up
tightened to 10; **the gauge-free threshold made to read the gauge**; the latch's
verdict made a function of the believed gauge; the rule made to reach into a
reading; the retreat made to decide on the measurement; the status-line clause
dropped; and — against the neighbouring case #135 owns, which this change had to
update — a guard dropped from the rule, and a guard given another's decision line.

**Two mutations survived the first pass and both were real holes in the cases.**
The single-copy case counted comparisons of the *record's* field names, so a
second copy reaching for `runAwayArmorHitpointsThresholdPercent` instead passed;
it now refuses either threshold setting as an operand of a comparison anywhere.
And the latch's forbidden list did not include `hitpoints`, the sample record's
own field, so a verdict consulting the stored gauge readings passed.

**Unverified: any of it running, and why the warp did not take.** No run has been
flown since, and the 125 blocks run 36 spent issuing a warp that did not happen
are **not explained by this change and are not claimed to be** — the measurement
says where the time goes, not why. What to watch on the first run that retreats
is `RETREAT NOT EXECUTING: N` appearing at all and then going away within a few
readings; a run whose worst reaches double figures is run 36's shape recurring,
and it is the first evidence anyone will have had. A run that retreats and never
prints the clause means the counter is not being written. **What this does not
protect against is the retreat itself being slow** — nothing here shortens the
interval by one reading, and run 36 replayed today would go exactly as it did.

### The unit was the problem, and in readings run 36 is not an outlier

Issue #141 asked for a bound on #139's counter, on the ground that run 36 is "an
outlier by twenty times" and that the bot "commanded a warp 296 times and never
formed the thought that none of them had worked". The bound shipped. **Three of
the numbers behind it did not survive being recounted, and the recount is what
decided where the bound goes.**

**The per-reading identity #139 says the logs do not have is in them**, just not
in a decision line, which is where it was looked for: the framework issues exactly
one `RequestToVolatileProcess` memory read per reading, so every decision printed
between two of them belongs to one reading. Run 36 carries a second and
independent counter to check that against — the ammo swap's `given up N readings
ago`, advanced in the memory update — and over its retreat the two agree to within
3%. `test_retreat_not_executing.TheUnitIsTheReading` pins that, because everything
below is a reading rather than a block only if it holds.

Recounted that way, from the verdict until hostiles leave the overview — #139's
own episode proxy, unchanged — the 29 episodes in 9 runs are a **median of 3
readings**, with 19 of the 29 at four or fewer, and ten longer ones at 8, 11, 11,
11, 11, 16, 24, 29, **43** and **44**.

- **Run 36's 154 blocks are 44 readings and run 10's 142 blocks are 43.** The same
  number, in a run nobody had looked at. Run 36 is not an outlier by twenty times;
  it is tied for first in a corpus of two.
- **Run 36's warp did take.** Its overview went to `rats 0` and the escape target
  closed 13.9 → 8.8 → 4.7 → 2.6 → 0.7 AU while the believed armour recovered 17% →
  48% and the damage window drained 1170 → 331. #139 says this in passing; the
  issue reads its 296 as one uninterrupted failure.
- **The 1% armour is one corrupt reading.** Shield and armour both read 1% on the
  same reading, taken with nothing on the overview and the ship already off the
  grid, bracketed by 37% either side — the single-reading corruption #120 exists
  because of, which `believed` rejects and the status line prints raw. The deepest
  value the retreat ever saw is 17%.
- **The 296 warp commands are two different things.** 124 of those blocks were
  issued with something still on the overview and **172 after it had emptied**,
  because the hysteresis keeps the verdict latched and `runAwayIfLowHealth`
  short-circuits the `I am in warp` branch that would otherwise have taken those
  readings. In readings the failure is 34 of them.

**And the failure is not one step.** `selectThenPanelAction` is two — click the
overview row, then press the panel's `selectedItemWarpTo` — and it prints
`(selecting it first)` for the first and the bare description for the second.
**163 of run 36's 296 blocks are the first**, the panel never having come to show
the row, including one stretch of 55 consecutive blocks on one celestial. Run 31's
28-reading retreat alternates the two the same way. So whatever is wrong is wrong
about a click on an overview row at least as often as about the panel button.

**What ships is a bound and a line, and no change to the retreat.**
`retreatNotExecutingAlarm` is a pure rule over two `Int`s that answers on the one
reading the interval crosses `retreatNotExecutingAlarmReadings`, and the line goes
out at the root:

```
+ RETREAT NOT EXECUTING: I have decided to leave on 36 consecutive readings --
readings, not decisions -- and the ship has not been in warp on any of them. The
warp is being commanded and it is not taking. I do not know why, I have no other
way out of a pocket, and I am still commanding it because stopping cannot help.
I am stuck here and need help to continue.
```

That last sentence is `stall_watch.py`'s `STUCK_TEXT`, matched as a substring of
any log line, so the alarm is answered by a screenshot of the client and by the
watchdog stopping. It is **carried into the line rather than reached by branching
to `askForHelpToGetUnstuck`**, because that leaf dispatches no effects: taking it
would stop the retreat commanding the warp, which is the one thing that must not
happen while the ship is in the pocket. `askForHelpToGetUnstuckText` is the shared
literal and a case reads all three copies — `Bot.elm`'s, the vendored framework's
and the watchdog's — because a drift there is silent in the direction that looks
like a healthy run.

**36, written as `runAwayCelestialStickyReadings * 3`.** The escape choice rotates
every 12 readings so that "a retreat that has not worked yet tries a different
corner of the system"; three full rotations is where the only self-correction the
retreat owns has been spent on three separate destinations and the ship is still
on the grid. `missionStalledReadingsBeforeAbandoning`'s form, for its reason: the
argument cannot drift away from the number. The measurement independently puts it
in the same place — above run 31's 28 and below run 10's 43 and run 36's 40, which
is the only gap the upper tail has.

**It will fire on retreats that would have recovered, and that is chosen.** All
ten long episodes ended in a warp that took, run 36's included, so there is no
threshold that separates the incident from the rest — there is nothing to
separate, and a bound above 44 is a bound that never fires. What the corpus does
separate is a manoeuvre that works, at two to four readings, from one being
retried, at eight and up. A retreat retried for three rotations while the ship is
being shot is worth a person's attention whether or not it would have fixed
itself: a false alarm costs a screenshot and a line, a late one costs the ship.

**Three escalations were considered and all three are worse than reporting.**

- **A different destination** is what the retreat already does and what every
  recorded episode did — three celestials in run 36, three in run 31, seven in run
  10. It is the thing that has already failed.
- **A different mechanism** is what this repo escalates with elsewhere
  (`beginCascade` and `clearStrayContextMenu` press Escape; #109 goes declining
  button, Escape, stand aside) and **there is not one here.** The only other way
  this bot can act on an overview row is a context-menu cascade, which begins with
  a click on the same row at the same coordinates — the half run 36 says stalls
  more often — and then adds a flyout that has to render and an entry that has to
  be found, on the retreat path, under fire. It would replace the working half and
  keep the failing one. Escape closes menus rather than warping ships, and the two
  branches that press it already run above this one on every reading.
- **Ending the session** is worse than doing nothing. The bot is the only thing
  still commanding a warp, and ending leaves a ship under fire in a pocket with
  nobody at the controls — which is how run 7 lost its ship, in the four minutes
  between one run's last reading and the next run's first. `FinishSession` is the
  right answer to a bound whose subject is an errand (#102, #126) and the wrong
  one to a bound whose subject is the ship.

**Said at the root, where nothing can decline to ask it.** #102's placement rule,
and it applies here for a reason particular to this bound: `runAwayIfLowHealth`
sits inside the docked-or-in-space split, so a message-box standoff above it can
hold the tree off the retreat entirely — and a held tree is one of the ways a
retreat comes to be 36 readings long in the first place. The verdict is settled in
`updateMemoryForNewReadingFromGame` beside the counter and folded in at
`missionBotDecisionRoot` alongside `dronesLeftBehindLastChange`, first in that
list because it is the only one of them about the ship being destroyed.

**Verified without a live client**, in
`tools/macos-host/tests/test_retreat_not_executing.py` (32 cases). The alarm and
the status clause are executed through the real `Bot.elm` in `elm repl` — the
crossing at both sides and against fixed values either side, run 36's own shape
folded through the rule as one line rather than two, a second interval saying so
again, and the longest recorded retreat *below* the bound saying nothing. The
corpus is recomputed as relations rather than as the numbers above: run 36 is not
the only retreat within a fifth of the worst, most of its warp commands were
issued after the grid emptied, a large share of them are the selection half, and
its 1% readings are taken off the grid beside healthy neighbours.

Confirmed by mutation, **twenty** of them, each failing a named case: the bound
removed entirely; written as a bare number; tightened to one rotation so it cuts
the distribution; loosened past everything recorded so it never fires; the
crossing weakened to `<=` so the line repeats; the crossing no longer judged
against the previous reading; the alarm made to end the session; the root no
longer printing it; the retreat made to consult the bound; the watchdog's sentence
drifted in `Bot.elm` and, separately, in the vendored framework; the line dropping
its "still commanding it" clause and its "readings, not decisions" clause; **the
alarm rule made to read the gauge** and made to reach for the whole context; **the
gauge-free threshold made to read the gauge**; the status line no longer naming
the bound; the drone recall taken out of the warp path; `droneRecallGiveUpTicks`
tightened; and, on the cases' own premise, the per-reading identity swapped for
the framework tick.

**Two mutations survived the first pass and both were real holes.** The status
line's bound was read out of the source, and a mutation that dropped it from the
count while leaving it in the sentence below passed — so the rendering is now
`describeRetreatLatencyFromProgress`, a function of the record, and the case
executes it. And the "reads nothing but its own record" case was mutated with an
expression that named nothing forbidden, which proved nothing; it is now mutated
by giving the record a gauge field and by reaching for the context.

**Unverified: why the warp did not take, and it is not addressed here.** Nothing
in this change makes a warp take, and run 36 replayed today would go exactly as it
did — with one line more in its log. The two shapes the corpus shows are a panel
that never comes to show the row and a panel button pressed dozens of times with
nothing happening, and neither is explained. Whether the click reaches the client
at all cannot be read from a recording. What to watch on the first run that
retreats: `RETREAT NOT EXECUTING: N of 36` in the status line, climbing and then
going away within a few readings. A run that reaches 36 and prints the alarm is the
first live instance of run 36's shape, and the screenshot `stall_watch.py` takes on
that reading is the evidence a repair would need — specifically whether the
Selected Item panel is showing the celestial at all. **A run that retreats and
never prints the clause at all means the counter is not being written**, which is
#139's own tell rather than this change's.

Two things this leaves as they are, stated so they are not rediscovered.
`retreatProgressAfterReading` resets on any reading that is not a retreat,
including one whose ship UI failed to parse, so a single unparsed reading inside a
long retreat restarts the interval and delays the alarm by the whole of it; #139
chose that reset and this does not revisit it. And the retreat goes on commanding
a warp at a ship that is already in one — 172 of run 36's 296 blocks — because
`runAwayIfLowHealth` outranks `decideActionWhenInSpace`'s `I am in warp` branch.
That is noise rather than damage, it is most of what made the issue's count
misleading, and changing it is a behaviour change on the retreat path that wants
its own evidence.

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

## The lock-slot ceiling is stated by the client, not hardcoded

`maxTargetCount = 4` was a hardcoded constant in **both** apps -- a field in
`BotSettings` with no setting able to reach it -- and the real number on this
character is **6**. saxrat paid for that on **2,149 readings** across its runs 2
to 5, printing `Enough locked targets.` with two lock slots sitting unused; the
mission runner paid silently, since its `List.take` says nothing at all.

**The client had been stating the answer the whole time, on a channel the bot
already reads.** `You are already managing 6 targets, as many as you have skill
to.` arrives on `(notify)` -- the same channel `loadRefusalFromGameLog` reads --
**228 distinct entries** across the recorded runs of both apps, and **491**
across the client's own game logs in `~/Documents/EVE/logs/Gamelogs`. So this
needed no new plumbing, only somebody reading it.

**The number is not a constant even for one character**, which is the argument
against a constant rather than against this particular value. Across the client's
own logs it reads **5** from 19:16:52 to 20:46:12 on 31 July 2026 and **6**
before and since -- a targeting skill completing. A hardcoded ceiling is
therefore not merely wrong once; it is wrong in a way that drifts under the bot
while nothing notices, which is the argument `targeting-range` was rewritten on.

### Two halves, and they fail differently

- **The floor is the target bar**, and it is the half that costs nothing and
  cannot be wrong. A reading whose bar holds N is this ship holding N -- the bar
  is the ship's own state, not an overview row that could have belonged to
  something else. It only ever rises. **This is also what covers the ship
  auto-locking past whatever the bot asked for**, which is how six targets came
  to be held while the shipped ceiling was four.
- **The stated maximum is the client's own sentence**, and it can move either
  way. It replaces the setting rather than clamping it, because it is the client
  stating a fact about this character where the setting was a guess about it.

Where the two disagree the floor wins: a bar demonstrably holding six is not
contradicted by a sentence the client wrote before a skill finished.

**No row identity is involved anywhere in this, and that is a finding rather
than an omission.** The lock range needs `overviewEntryLockHandle` because it
attributes a *lock outcome* to an *object*, and in an anomaly of identically
named rats that rule correctly yields no evidence at all. Nothing here attributes
anything: the target bar is a count of this ship's own slots and the game log is
the client speaking about itself. So the rule fires on every reading in an
anomaly where the lock range's would stay silent, without weakening the
discipline by one line -- `TheRowIdentityDisciplineIsUntouched` pins that the
ceiling reaches for no overview row, so a later version that starts to has to
notice it is taking on a problem this one does not have.

### Absent evidence never raises the ceiling

`loadRefusalFromGameLog`'s register, applied to a ceiling. With no statement and
no bar ever seen carrying anything, `maxTargetsCeiling` is **exactly** the
setting, so a session that learns nothing behaves as it always did.

The direction matters more here than for a lock range, and asymmetrically:
a ceiling raised on a guess makes the bot spend readings asking for locks the
client will never grant, and **nothing would ever teach it back down**. The bot
learns only from what the client grants, and a slot that does not exist grants
nothing. A lock range has a refusal that walks the bound back; this has no such
thing.

### The sentence is not the drone one, and it is excluded three times over

The client writes a refusal of exactly this shape about **drones**: `You cannot
launch Acolyte I because you are already controlling 5 drones, as much as you
have skill to.` -- and it is the *more* common of the two, 188 live sightings
against 40 in saxrat's run 5. Reading it as a lock ceiling would cap this ship at
the number of drones it can fly, on a reading that said nothing about targeting.

It is declined by `controlling` not being `managing`, by `much` not being `many`,
and by the number being sliced out *after* `maxTargetsStatedMarker` rather than
taken as the first integer in the line -- so it lands on a word rather than a
digit. That was expected to be one exclusion and turned out to be three; no
single loosening admits the sentence, and the mutation that does is the naive
matcher with all three gone. `maxTargetsStatedMarker` is the one constant both
the matcher and the slice use, so an extraction can never succeed on a sentence
the matcher would have rejected -- `gateKeyClosingMarker`'s arrangement.

### The popup channel captured it too, which settles #123's first question

`Quick message (on screen now): "<center>You are already managing 6 targets, as
many as you have skill to."` appears **40 times live** in saxrat's run 5. That
is the black status popup the operator reported, so `quickMessage` **is** the
widget they are seeing -- the first Unverified item in #123, answered by PR
#130's clause doing exactly what it was built to do, with no new machinery and
nobody watching.

**The game log is what the rule reads all the same**, and the choice is not
arbitrary: game-log entries are scoped to the reading and drained by the host,
where a quick message is carried forward with an age and would have to be dated
before it could be believed. The two agree word for word, modulo the popup's
`<center>` wrapper.

Counted **live**, as #130's clause requires -- `on screen now` rather than the
carried-forward form, whose totals are three orders of magnitude larger and rank
the wordings differently.

### `max-targets`, and the empty value

The setting mirrors `targeting-range`: a starting value clamped by what the
client reveals, defaulting to the 4 both apps shipped so no existing settings
string changes behaviour. It is parsed with `AppSettings.valueTypeInteger`, which
is what carries PR #116's rule here -- `String.toInt ""` is `Nothing`, so
`max-targets=` with nothing after it answers `Err` naming the value and
`BotFramework` ends the session, rather than silently leaving a ceiling of 4 that
reads exactly like one an operator set.

**Verified without a live client**, in
`tools/macos-host/tests/test_learned_max_targets.py` (38 cases, run against
**both** apps). The rules are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python, and the game-log entries they are asked about
come from the real `EveOnline.ParseUserInterface` -- which is also the evidence
that saxrat's diverged copy of that parser carries this channel. **Neither
parser needed a change.** The corpus is recounted as *relations* rather than as
the numbers above: every statement the runs hold names a number and every one is
above the shipped 4, the shipped markers read all of them and recover the count
the client wrote, the drone refusal really occurs, and saxrat's cap really did
stop it on readings it wanted more.

Confirmed by mutation, **sixteen** of them, each failing a named case, listed in
that file -- including the ceiling raised on absent evidence, which is the one
failure this whole design refuses, and `overviewEntryLockHandle`'s same-name
exclusion loosened, which fails the lock-range suite next door.

**Run 6 flew it, and it learned nothing** -- which is #150 rather than a fault
in this. saxrat's run 6 launched from this change's own merge commit and carried
`Max targets: 4 (setting 4, client stated -, most held at once N)` on **every one
of 2,193 readings**, with `client stated` never leaving `-`, the client's
sentence arriving **not once**, and `Learned max targets:` never printed. The
clause works, the plumbing works, and there was nothing for either half to learn
because the lock site stops at the ceiling it already believes in. See "Neither
half could move on its own, so the bot asks for one more" below.

**Unverified: one thing about the ceiling itself.** **Why six targets were held
while the bot's own ceiling was four is still not established** -- an auto-targeting module is the obvious
candidate (there is an `Auto Targeting System I` in the character's hangar) and
EVE's own "auto-target back" setting is another, and neither is confirmed. It
does not change what the rule learns, since a bar holding six proves six slots
whatever filled them, but it does mean the *floor* may be reached without the bot
having asked for it.

What to watch on the first run: `Max targets: 4 (setting 4, client stated -, most
held at once -, probing for 5)` on every reading, then `client stated 6` within a
reading or two of the first refusal, then `Learned max targets: ... max-targets
moves from 4 to 6.` once in the decision log and never again. A run that fights
and never leaves `client stated -` means the game log is not reaching the bot; a
run whose `most held at once` never rises past the ceiling is the ordinary case
and not a fault. The failure to watch for is `Enough locked targets.` still
appearing at four locked rats after the ceiling has moved, which would mean the
decision is reading something other than the rule.

### Neither half could move on its own, so the bot asks for one more

Issue #150. `maxTargetsCeiling` is what the lock site's `List.take` took, so the
bot locked four, saw four held and learned four -- **the floor cannot rise past
the ceiling, because the ceiling is what it asks for.** And `statedByClient`
comes from a refusal the client writes only when a lock is attempted *beyond*
the cap, which stopping at the ceiling never provokes. Both halves were inert
for the same reason: the constraint being learned is the one that prevents the
attempt. The corpus above is hand-fed -- all 228 statements exist because a
person locked the extra targets.

So while `statedByClient` is unknown the lock site takes **one row more than it
believes in**. A probe that lands raises `heldAtOnce`, which raises the ceiling,
so the next probe is one higher and it ratchets; a probe the client declines
produces the sentence, which sets `statedByClient` and ends the probing for the
session. The refused attempt is not waste, it *is* the measurement, and there is
one of them per session rather than one per reading.

**The first live run of #149 is the proof that it is inert.** saxrat's run 6 was
launched from that change's merge commit while this one was being written: 2,193
readings, the clause on every one of them, `client stated -` on every one of
them, not one statement from the client and not one ceiling moved. The bot held
at most three targets against a believed four, so the *floor* had nothing to say
either. That is the argument above observed rather than reasoned.

**The mission runner already provokes the statement, and run 37 is the
evidence.** That run was in flight and unattended when this was written, and it
holds eight distinct `(notify) You are already managing 6 targets` entries, each
on the reading *after* the bot's own `Lock more targets.` click, with no
`standing down: someone used the mouse` anywhere in the window. So the sentence
is one a click provokes, it arrives within one reading, and the issue's
"hand-fed" is true of saxrat's corpus and not of the newest mission run. What it
could not do is *ratchet*, because those clicks are aimed at rows inside the
believed ceiling that happened not to be locked.

**Taking one more row rather than a different one is what keeps the probe from
displacing a real target.** `List.take (n + 1)` extends `List.take n`, so the
rows the ceiling covers keep their order and their places and the extra one is
reachable only once every one of them is locked -- which is also what
`maxTargetsProbe` says, answering `MaxTargetsProbeFillingSlots` while the bar is
below the ceiling.

**A refused probe must not read as a stuck lock, and measuring what one costs
turned up a defect in the lock range.** `lockAttempt` bounds a lock the client
*accepted* and never finished, and its give-up is only asked of a row that reads
`targeting` -- which a lock the client declines never does. So a declined lock
ran the attempt to `lockAttemptReadingsBeforeVerdict` and **latched there**:
`for 8 readings` appears on **more than three thousand** status lines across 22
recorded runs, while
`stop waiting for it` has fired **zero** times in the whole corpus. Run 37 shows
nineteen consecutive status lines reporting a lock that had not landed, on a
click the client had already answered.

`lockAttemptCanTeachRange` ends that, and it needs nothing new to know: the
refusal test already requires **an empty target bar at both ends** of an
attempt, so an attempt begun with a target already held can never move either
bound however long it is carried -- it fails that condition rather than the
wait. Such an attempt is now discharged on the reading it fails to land instead
of being carried to a verdict it cannot reach. Every probe is by definition
asked with the bar at the ceiling, so a probe spends none of that budget and the
give-up can never see one. What it costs is the *proven* bound: a lock that
lands slowly with a target already held is credited from the reading the bot
re-asked rather than the first, which is the weaker claim of two.

**Nothing to spare means no probe.** With the bar at the ceiling and no lockable
row left *in range* beyond it there is nothing to attempt, so the reading says so
rather than counting one. Range is part of that on purpose:
`lockTargetFromOverviewEntry` answers an out-of-range row by approaching it,
which is right for a target the bot wants and wrong for a measurement -- flying
at a rat to find out whether a fifth slot exists spends the ship's position on a
question the next row in range answers for nothing.

**The probing stops on the statement and on no count.** A client that never
names a number is asked again rather than given up on, because a count would
stop the learning before the answer arrived and what it would save is one lock
click on a reading the bot was going to spend waiting anyway. All 228 recorded
refusals name the number, so the evidence there is says the statement comes. The
status line carries `probing for N` exactly while `client stated` is `-`, so the
two clauses cannot disagree about whether the question is still open.

**saxrat needed a second fix its own gate had hidden.** Its candidate window was
`List.take 4` -- the shipped ceiling written out a second time -- so a client
stating six left two slots unreachable however far `Enough locked targets.` was
raised. That take is the learned count now, and the gate compares against the
same rule, so the two cannot disagree about whether there is room.

**Verified without a live client**, in
`tools/macos-host/tests/test_max_targets_probe.py` (31 cases, run against
**both** apps). The rules are executed through the real `Bot.elm` in `elm repl`,
and the lock-range half is folded over whole sessions through saxrat's own
`updateLockRangeLearning`, which is a function of records -- so "a declined lock
is discharged and an empty-bar one is still judged exactly as before" is run
rather than read. The corpus is recounted as *relations*: a declined lock does
reach the verdict count in the recorded runs, the give-up never fired on one,
and at least one statement follows the bot's own click with no human at the
keyboard.

Confirmed by mutation, **fifteen** of them, each failing a named case, listed in
that file -- including the take back at the ceiling, which is the shape that
cannot bootstrap; the probe due below the ceiling and a row dropped ahead of the
take, which are the two ways it would displace a real target; and
`lockAttemptCanTeachRange` made to answer `True`, which is a refused probe
spending the give-up's budget again.

**Unverified: any of *this* running, and what a refused lock costs in the game.**
No run has been flown with the probe in it -- run 6 is #149's code, and what it
shows is the state this change is trying to leave. What the corpus establishes is what a refusal costs
*the bot* -- a reading, a click, and (until now) the whole lock-attempt budget.
Whether it costs anything **in game** -- aggression, a module cycle, an alarm --
is still not established, and it is what decides whether "always" is right or
whether the probe should be rarer. The recorded refusals are accompanied by no
other client sentence and by no change the bot records, which is evidence of
absence only as far as the bot can see. Also still unverified: whether every
client states the cap at all, since all 228 entries come from one account with
one skill set, and whether the probe interacts with an auto-targeting module
filling the bar without the bot asking -- a bar the ship filled itself raises the
ceiling rather than making a probe due, so that case reads as a ceiling that rose
and not as a probe that failed.

What to watch on the first run that probes: `probing for 5` in the status line,
then `Probing for lock slot 5:` in the decision log, then `most held at once 5`
and `probing for 6` -- the ratchet -- and then `client stated 6` with the probing
clause gone for the rest of the session. `Probing for lock slot 5` repeating for
many readings with the number never moving is a probe nothing is answering, which
is the case the corpus says should not happen and the one that would argue for
bounding it. `attempt N m for 8 readings` should now be rare rather than routine.

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
| which charge is loaded | menu membership where a read arrives; otherwise, since #85, the charge the last load asked for |
| did the load land | the client's own refusal **not** arriving (#31), since #85; menu membership where a read happens to arrive |
| where to change over | `ammo-swap-range`, else the midpoint of the two optimal ranges |
| does this gun need stopping first | `isInActiveState` — the toggle, since #76; it read `ramp_active` before, which is the duty cycle |

The second row is the one that changed direction, and #85 is the argument —
see "Trusting the load" below. The inference is still never "no refusal
arrived, so it worked" on its own: it is "the bot dispatched this load, and the
client did not disown it".

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
Three things switch the swap off beyond the one attempt, because only they should
not be retried straight away: the menu offering neither charge, there being no
crossover distance, and reaching the silence deadline on a ship the client left
disarmed. **Only the first two last the session.** The third is retried on the
next warp since #157, and it now asks whether the guns actually stayed off — see
"The disarm budget bounds an attempt, and it was read as a statement about the
guns" below, which is where the whole of that argument lives.

The middle one is the weakest of the three and #106 is why: it is the only one
that is not a permanent fact about the ship or the client, so it now rests on six
hovers asked at six different moments rather than on five readings of one — see
"The tooltip is asked where the mouse is free, and one hover is not evidence".

### The bound is a backstop; the policy is gain against risk

Run 11 reached that deadline, latched the feature off, and it still cost most of
a tank: the swap had begun on a ship at 26% shield with twelve hostiles on grid
and 1679 hitpoints already in its 45-second window, and by the twentieth reading
the shield was at zero and the armour had started going. **The bound did exactly
what it promised. Twenty readings under fire is still most of a tank.** A bound
answers "what if this never ends"; it does not answer "should this have started".

So `swapMayDisarmTheGuns` is the policy, ahead of the backstop. #50 wrote it as
**zero** — no disarming while the client reports any incoming damage at all — on
the argument that a threshold "would license disarming under light fire, which is
what heavy fire starts as". That was right about run 11 and it made the feature
unable to fire.

**Run 17 is what zero cost.** Three verdict attempts wanting Multifrequency M,
271 readings holding one, and the charge never loaded: `GUNS OFF` appears **zero
times** in the run, and 188 status prints carry `not disarming` instead, blocked
by windows of 128, 190, 301, 309 and 371 hitpoints against a retreat threshold of
3500 — a rat plinking the shield. (Counts are a snapshot of a run still being
written; the shape is what matters, not the totals.) In a mission pocket there is
always *some* incoming damage, so a zero-damage rule fires only between waves,
and the ship fought whole engagements with the wrong charge while the feature
reported itself working. #50 measured that itself and called it the trade: 26% of
the moments the swap wanted to act.

So the question is no longer "is anything shooting" but **is this worth it**.

- **The risk is the same rolling window**, the client's own combat log rather
  than a HUD sprite and already summed for every reading, compared against
  `ammoSwapDisarmDamageBudget` — **an eighth of `run-away-incoming-damage-
  threshold`**, 437 on this hull. A share rather than a number, for the same
  reason 3500 is a fact about this hull: the next ship re-derives it.
- **The eighth is read out of the recordings.** For all 22,452 readings in the
  seventeen recorded runs, take the window and then the worst window reached
  within the next 20 readings — `ammoSwapSilencedGiveUpTicks`, the longest the
  swap can hold the guns. The curve is flat and then it is not: up to a window of
  **445** the worst that ever followed was 1226 hitpoints (35% of the threshold);
  at 446 it is 1436, and at 469 it is 1683 — past the 1679 run 11's fourth swap
  began on. 445 is where the recorded data stops saying "this does not escalate",
  and an eighth is 437, just inside it.
- **The gain is `ammoSwapRangeErrorPercent`** — how wrong the loaded charge's
  range is, as a share of the crossover — and below
  `ammoSwapWorthwhileRangeErrorPercent` (50%) the budget is zero. Half the
  crossover is where the target sits at or past the *other* charge's own optimal:
  the two ranges on this fit are 21000 and 67000 about a 44000 midpoint, so each
  is about 52% away from it. **It is the weak half and #63 says so** — what
  actually decides whether the other charge is better is whether the guns are
  landing, which the client states on its outgoing combat lines and which this
  does not read.
- **Where the gain cannot be measured the budget is zero**, which is #50's rule
  exactly. No crossover, no active target to measure a distance to, or a retreat
  threshold set to `-1` and so not a scale to take a share of. That also answers
  "worth nothing if the fight ends first": a target that has gone leaves no
  distance, so a swap already holding the guns lets go on any fire at all.
- **An absent channel declines.** `Nothing` and `Just 0` are different facts and
  only one may be read as "the grid is quiet". A host that cannot answer gets the
  answer that keeps the guns firing — which costs the whole feature on such a
  host, stated rather than hidden.
- **Deferring is not failing.** Nothing is given up and no counter is spent: the
  verdict stays live, the guns keep shooting what they have, and
  `ammoSwapVerdictGiveUpTicks` drops the attempt if the moment never comes.
- **The trade going bad mid-swap abandons the attempt** rather than waiting out
  the deadline, because letting go is what re-arms the guns — `decisionToKillRats`
  presses the hotkey on the very next reading, which run 11 shows it doing. It is
  the *same* rule as the entry, deliberately: keeping #50's zero here while
  relaxing the entry would disarm and abandon on the next reading, which is churn
  with the guns rather than a swap.

**Nothing #50 permitted is refused.** The budget is never negative, so a quiet
window passes whatever the gain is, and the change can only add readings. Against
run 11's four swaps it declines the fourth — 1679 against a budget of 437 — and
permits the other three; #50 also declined the first, at 110 hitpoints on a window
that was *falling* (329, 282, 220, 162, 110) as that engagement ended.

**Run 17 separates within itself, which is what makes it evidence.** Its first
attempt is permitted at the fourth reading, the first the hold ticks allow. Its
third attempt is a shield collapse — window 309, 362, 436, 505, 567, 654 while
the shield fell 49% to 0% and the armour started going — and the rule permits
exactly one reading of it, the 436 that sits one hitpoint under the budget, then
abandons on the 505. One reading of disarmament on the worst slide in the
recorded corpus, against run 11's twenty.

**And the gate is not the only thing in the way — run 18 says so.** That run's
`not disarming` count is **zero**: both of its swaps began on an empty window, so
#50 permitted them and this permits them unchanged. They still failed, one
reading later, and how is in "The switch-off does not hold" below. So the two
runs answer different questions and both are needed: run 17 measures what the
gate costs, run 18 measures that the gate is not all of it.

**The deadline is the invariant and is untouched.** `ammoSwapSilencedGiveUpTicks`
is still 20 and still consults nothing above. *Failing to a firing gun with the
wrong ammo beats failing to a silent gun*, and the mid-swap release is an early
exit from the bound rather than a replacement for it.

**Separately, the client's confirmation ends the guessing.** `gunsConfirmedOff`
is `isInActiveState` reading `Just False` on a gun the swap commanded off. It
shortens the settle — measured landing on the first reading after the click every
time — and, once it has been true and the gun reads switched on again,
`switchOffHasBeenUndone` says the switch-off did not hold. Replayed against run
11's twenty status-line columns that fires at reading 3 rather than 21. **Since
#72 that is a report and not a verdict**: the client re-arms the gun on every
swap, so abandoning there guaranteed no attempt could reach its load. See "The
switch-off does not hold".

**The deadline itself is unchanged, and so is its independence.** `gunsSilencedTicks`
still consults nothing the module says. Every use of the module reading can only
make the swap release the guns *sooner*, never hold them longer, and that
direction is asserted as a property of the source in
`tools/macos-host/tests/test_ammo_no_disarm_under_fire.py` — which also executes
the rules through `elm repl` rather than restating them in Python. The bound's
size was left at 20 deliberately: shortening a bound on a policy that should not
have started is treating the symptom.

### The switch-off does not hold, and that is what stops the swap now

**Run 18 is the first run in which a swap got past the disarm gate and was
watched.** Two swaps, both on an empty window, and both dead two readings later.
The top-row module column is the whole story, identically on each:

```
T/T/F   the reading the swap clicks the module button   switched on
T/F/T   GUNS OFF for 1 of 20, "the client confirmed the switch-off"
F/T/F   "gave up on this one"                           switched on again
```

The gun is back on **the reading after the confirmation**, with the swap still
holding the fight and its own decision line reading `Open this weapon's menu`.

**The cheap hypothesis was that this is our own code, and it is not.** #72 was
told to rule that out first, because `decisionToKillRats` presses an inactive
top-row module on a locked target and #50 deliberately relies on that to bring
the guns back — so two controllers fighting over one button would have made this
an ordering fix needing no knowledge of the client at all. The decision log
settles it, on all four swaps across the two runs that have one:

- **The branch that presses is `Cycle combat mod`, and through the disarmed
  window it prints `All guns cycling` instead.** `isActive` reads `ramp_active`,
  which stays `True` while the gun finishes its cycle, so the fight sees nothing
  inactive to press.
- **The one reading it did reach `Cycle combat mod`** — run 11's second swap —
  the gun was *already* back on, and the press was suppressed by
  `activateWeaponModuleButWaitIfActivatedInPreviousStep`. Reached one reading
  after the re-arm, so it could not have caused one.
- **What was dispatched in between** was a drone launch (run 11's second swap), a
  left click on an *overview entry* (run 11's first), and the swap's own
  right-click on the module (both of run 18's). Run 11 is the control that
  matters: there the host's own gesture log shows the mouse glided *away* from
  the module button before the gun came back on, so a re-arm happens with
  nothing touching it.

So this is the *client* turning the weapon back on. Auto-repeat remains the
candidate explanation and is **not** established: `autorepeat` reads `1000` on
these guns and has since #39 parsed it, and the weapon's own context menu offers
`Set Auto-Repeat Off`, which nothing has tried. What is established is only that
the bot did not do it — which is all the fix rests on.

**`switchOffHasBeenUndone` then abandoned the attempt on the reading the menu
would have arrived on.** The right-click was issued on the confirmation reading;
a context menu is in the tree on the *next* one; and that was the reading the
verdict was abandoned, so the menu was never read. That matters more than losing
one swap, because menu membership is the swap's only answer to *which charge is
loaded* — which is why runs 17 and 18 print `loaded charge reads unknown` on
every ammo status line they have, while run 11, which predates the confirmation,
resolved it on 358 of its 488.

**#72's fix is that the re-arm reports and decides nothing.** Since the client
does it on *every* swap, that clause was not a detector — it was a guarantee that
no attempt could reach its load, which is what runs 11, 18 and 22 all did. Every
episode across those runs where a gun read `isInActiveState` `F` ends with it
reading `T` again, the longest running four readings; none held. Run 22 is the
one that makes the count worth quoting: it reached `GUNS OFF` 29 times, two of
those got a gun genuinely off, and both were abandoned on the reading after,
exactly as run 18's two were, on a different mission and a different target.

**The length varies and is not what the fix depends on.** Run 11's first swap
read `T/F/T` then `F/F/T` — the ramp stopping with the gun still off — before
coming back on. What holds across the corpus is only that the client always takes
the guns back, which is the assertion made, after a stricter one was written and
run 11 falsified it.

And it
fired precisely where the swap had stopped costing anything the bounds exist to
protect: the predicate is true exactly when the guns are firing again, so
*failing to a firing gun beats failing to a silent gun* has nothing left to
choose between. What ends an attempt now is what always could —
`ammoSwapSilencedGiveUpTicks` (20, untouched) and the client's own load refusal
(#31) — and neither consults the module, which is why the clause could go without
taking a bound with it. `switchOffUndoneByClient` survives as a latched report:
the status line stops saying `GUNS OFF for N` once the guns are back and says so
instead, because a counter that means "readings this attempt has held the fight"
and a sentence that means "the guns are off" came apart at that moment and only
one of them was ever true afterwards.

The swap now goes on to its load on the reading the menu arrives, which is what
run 11 did before #50 and which is where the next observation has to come from —
see "What is verified and what is not" below for why the two recorded loads into
a switched-on gun disagree with each other, and why that makes proceeding the
experiment rather than the gamble.

**So `loaded charge reads unknown` is a symptom with two different causes**, and
neither is a fault in the menu read itself:

| run | live verdicts | declined by the gate | reached `GUNS OFF` | what stops it |
|---|---:|---:|---:|---|
| 11 | 149 | — (predates #50) | 37 | the silence deadline |
| 17 | 271 | 52 | **0** | the disarm gate |
| 18 | 25 | **0** | 2 | the switch-off being undone |

Run 17 is gate-bound and run 18 is not, which is why a change to the gate has to
name which run it answers. #63 answers run 17. Run 18's failure is #50's
confirmation logic meeting a client that re-arms the gun by itself, and it is
#72.

### Run 21: nothing refused the swap and it still never disarmed

Run 21 is the first run in which everything *upstream* of the swap works. The
menu read resolves — `loaded charge reads long-range`, where runs 17 and 18
printed `unknown` on every line — the crossover is derived from two optimal
ranges (44000 m), 161 readings carry a live verdict, and `not disarming` appears
**zero** times, so #63's budget never declined it.

`GUNS OFF` appears zero times too, and `T/F/T` never occurs, so #72's re-arm is
not what stops it. The cause is `weaponIsFiring` reading the duty cycle, and it
is **#76** — see "Ship modules" above for the field and the counts. Decision
counts for the run: `No weapon reads as firing` **90**, `Stop this weapon before
loading` 8, `Open this weapon's menu` **0**.

One reading did reach the switch-off and dispatched it —
`move: glided (1565.7, 182.9) -> (917.3, 1023.7)`, `send-effects-317` — and the
next reading lost the target, so `rangeVerdict` went `Nothing` and
`gunsSilencedTicks` reset before it could reach 1. That is the swap behaving
correctly against a rat that died, and it is why a press went out with `GUNS OFF`
never printing. It is also why run 21 says nothing about whether the click lands:
one reading, and a dying target.

### Run 22: the same code reaching `GUNS OFF` 29 times, and still no swap

Run 22 is run 21's build with better luck — 29 `GUNS OFF` prints against zero —
and it is the run that turns several inferences into observations.

- **The client's refusal is real, reaches the bot, and is quoted.** `You cannot
  load or unload Focused Modulated Medium Energy Beam I while it is active.`
  appears **134** times in run 22's game log and the bot printed
  `The client refused the load. It said: …` **65** times. #31 had never fired in
  a recorded bot run before this. So the arbiter every part of this design
  leans on works.
- **The switch-off click often does not land.** Run 22's longest episode presses
  at `T/T/F` and reads `Told the guns to stop 1 of 3 readings ago and none has
  yet read switched off` three readings later, with `isInActiveState` still `T`
  and an `effect_activating` pulse of `1` in the middle — a gun starting a new
  cycle, not stopping. The fixed settle then expires, the load goes in anyway,
  and the client refuses it. That is the 134.
- **Every switch-off that *did* land was then abandoned.** Two episodes reached
  `T/F/T` or `F/F/T`, and both read `F/T/F` on the very next reading and gave
  up — #72's shape exactly, on a different mission and a different target from
  run 18's two. Four instances now, across three runs, and **no counterexample:
  no confirmed switch-off in any recorded run has ever survived to the reading
  after it.**
- **No swap completed.** `(satisfied)` appears **zero** times. `loaded charge
  reads` went `unknown` → `short-range` once, when the menu read finally
  resolved, and never changed again while the swap asked for `Radio M` on 277
  prints. A resolved charge is the *menu read* working, not a load landing —
  those are different claims and the status line says only the first.

### Trusting the load, because the client says when it fails

Run 26 is the first run in which the swap works: 7 disarms, loads that land, and
a crossover that self-calibrated to `44000 m (from the midpoint of the two
optimal ranges seen)` off `seen low: 21000, seen high: 67000`. **What it does
badly is finish.** Its guns-off windows peak at 3, 7, 10, 16, 17, 18 and 19
readings against a bound of 20, and almost all of that is spent proving a load
that has never failed.

Counted over the 90 readings inside those seven windows:

| phase | readings |
|---|---:|
| `re-open the last one's menu to see whether it took` | **55** |
| stale-menu and pause-menu cleanup, downstream of that re-opening | 18 |
| `Told the guns to stop N of 3 readings ago` | 10 |
| `Open this weapon's menu` | 6 |
| the fight getting a reading | 1 |

**And the verification answered on one of the seven swaps.** Run 26's
`loaded charge reads` went `unknown` → `short-range` exactly once, at step
`148.2`, and never moved again across 4,138 further status prints — including
the four later swaps that asked for `Radio M`. The reason is `menuOpenOnGunAtX`:
it attributes an open context menu to a weapon only where the *previous step*
right-clicked it, and the client usually takes two or three readings to draw the
menu, by which time the attribution is gone. So the re-opened menu is read only
when the client happens to be fast.

**The branch was also not a read.** `loadTheWantedCharge` is a cascade that ends
in clicking the charge entry, so every re-open re-issued the load. What run 26
did seven times over was load, re-load, re-load, and time out still asking.

**The replacement is that a load that does not land is not silent.** #31 reads
`You cannot load or unload <weapon> while it is active` off the game log, and
the two runs are a control pair:

| run | refusals in the game log | `(satisfied)` prints |
|---|---:|---:|
| 22 — every load into a running gun | **134** | 0 |
| 26 — the guns stopped first | **0** | 2,628 |

So the swap dispatches the load and finishes on the next reading.
`ammoSwapLoadIsTrusted` is the rule, and its five inputs are each a way it can
be wrong: the verdict must be the one that issued the load, every gun must have
been told, the load must have *gone out*, the client must not have refused it,
and any menu read on that reading wins if it disagrees.

**The dispatch is read from the previous reading, and that is the trap in this
design.** `loadCascadeReachedTheMenu` is true on the reading a menu offering the
wanted charge is in the tree, which is the reading the cascade clicks that
entry — so satisfying the verdict *there* would send the acting path to `idle`
before the click was dispatched, and the swap would be trusting a load it never
issued. It is therefore only ever read as `memoryBefore.loadCascadeReachedTheMenu`.
A menu is judged to be a weapon's by its offering the charge by name, which is a
wider and steadier test than `menuOpenOnGunAtX` and needs no attribution.

**The identity is kept rather than dropped, which is the part that needed care.**
The menu read did two jobs and only one was redundant: it is also how the bot
learns *which* charge is loaded (#26 / #29), and dropping it outright brings back
`loaded charge reads unknown` — the state runs 17 and 18 were stuck in, which
stops the next verdict forming. So the trust *writes* the charge it asked for
into `chargeLoaded`, flags it `chargeLoadedIsAssumed`, and says so on the status
line as `(assumed from the load, not read back)`. Any menu read overwrites it,
in both directions. That is strictly more identity than the old design
delivered: one read in seven swaps becomes an answer on every completed load.

**The optimal-range forget had to follow it.** The number belongs to the charge
that was in the gun, so an assumed change makes it as stale as a read one does —
and forgetting it is the only thing that sends the hover back to read the new
charge's range, which is how the second of the two optimal ranges is ever seen.
Without `optimalRangeAfterTheLoad` run 26 would have stayed on its 67000 m
bootstrap instead of reaching the 44000 m midpoint.

**The assumption is exactly as good as #31, and that is recorded in the code.**
`loadRefusalFromGameLog`'s own doc comment says so, because someone editing that
matcher is not reading this file: remove it or let it drift, and a discarded
load goes silent *and* the swap starts reporting a charge the gun does not have.
Two failures rather than one. `verdictSatisfied` also asks the refusal *before*
the trust, so a refusal arriving one reading after the click un-satisfies a
verdict the trust had already closed.

**The bounds are untouched.** `ammoSwapSilencedGiveUpTicks` is still 20 and
`ammoSwapSilenceSettleTicks` still 3; the window is expected to fall because the
swap finishes sooner, not because anything was loosened.

**The settle was measured and left alone.** Across run 26's seven disarms, four
paid nothing for it — the client's own `isInActiveState` confirmation ended the
settle at one reading or none — and on the other three the client never reported
the gun off at all within seven readings, so the count of 3 is the only thing
that ends the wait there. It cost 10 of the 90 readings, and no recorded run
shows a load accepted earlier than the third reading, while run 22's 134
refusals are what loading too early costs. Lowering it would be a guess against
the one number that argues for it.

`tools/macos-host/tests/test_ammo_trusted_load.py` executes the rule through the
shared `elm repl` harness and reads the rest out of the source through a
whitespace-collapsing reader. Confirmed by mutation, nine of them, each failing a
named case: dropping the refusal veto, reading the cascade state from this
reading instead of the previous one, asking the refusal after the trust rather
than before, storing only the read charge, keeping the stale optimal range,
aiming the cascade at the reference gun instead of the gun last right-clicked,
re-introducing the verification branch, taking the `#31` note out of the
matcher's doc comment, and hiding the assumption from the status line.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one — the guns-off window peaking around **4 to 7** readings rather
than 16 to 19; `(satisfied)` still appearing, at least as often as run 26's;
`cannot load or unload` staying at **0**, since a refusal appearing is the
client saying the trust was misplaced; and `loaded charge reads` *changing* with
each swap rather than latching once, with `(assumed from the load, not read
back)` beside it. A run where the charge tracks the verdict and no refusal
appears is the whole claim. A refusal appearing means the load is going into a
running gun again, which is #76's territory and not this.

### The tooltip is asked where the mouse is free, and one hover is not evidence

Run 32 turned the whole ammo swap off **at tick 61**, four minutes into a
three-hour session:

```
Ammo swap: given up -- no crossover distance: 'ammo-swap-range' is not set and
the weapon's tooltip never appeared, so there is no distance to swap at even
though the menu says which charge is loaded.
```

The status line the reading before reads `tooltip unanswered 5`. That is the
whole of the evidence: five readings of **one** hover, and one of only three
verdicts that switch this feature off for a session — alongside the ship carrying
neither charge and the silence deadline, both of which are permanent facts where
this one is not. Nothing about five unanswered readings says the tooltip will
never appear. Run 32 then spent the remaining 2,593 of its ammo status lines
reporting the feature off.

**The tooltip works on this client**, which is what makes five readings too small
a sample rather than a conclusion. Run 17 answered on the reading straight after
the hover; run 26 derived its 44000 m crossover from two observed optimal ranges;
run 30 answered on the third reading of its own hover.

**Combat is not what starved it, and this is where the issue that prompted the
fix is wrong.** The obvious explanation is that run 32's hover landed mid-fight —
`Recon (1 of 3) -- You need to activate the Acceleration Gate`, under fire from a
`Centum Loyal Slaughterer` — where the mouse is wanted for locking rows and
clicking the overview, so the sustained dwell a Photon flyout needs never
accumulates. The log refutes it twice:

- Across the **eleven steps** of that hover the bot dispatched **exactly one**
  effect — `move: glided (1179.0, 155.5) -> (478.5, 978.5)` — and nothing else.
  Twelve seconds of wall clock by the game log's own timestamps, the cursor
  parked on the module, and no flyout.
- **Run 30's hover was answered mid-fight**, with twelve rats on the overview,
  726 hitpoints in the 45-second window and the shield at 62% — the same
  conditions run 32 failed in, at the same screen point (478.5, 978.5).

So whatever decides whether the flyout comes, incoming fire is not a proxy for
it, and the fix carries **no damage clause** — `swapMayDisarmTheGuns`'s shape
would have been the wrong shape here.

**What changed is the sample and the moment.** The readings now bound one
*hover*; the feature is given up only after `weaponTooltipAttemptsBeforeGivingUp`
(6) separate hovers, each asked at a different moment. And the moments after the
first are **warps**: `decideActionWhenInSpace` already answers `I am in warp` and
issues nothing, so the mouse is free by construction and holding it still costs
literally nothing — the branch the hover replaces there is
`waitForProgressInGame`, after `returnDronesToBay` has had its say.

**The first hover still happens in the pocket**, because that is where the three
runs that got an answer asked. What the pocket no longer gets is a second one:
`weaponTooltipIsWorthAsking` permits a hover out of warp only while none has been
spent, so a fight can never burn the session's evidence on consecutive readings
of a single moment.

**One hover per warp**, which is the clause that stops the fix reproducing the
bug at a larger scale. A warp holds enough readings to run six budgets back to
back, and six hovers inside one warp are one moment sampled six times.
`hoverAttemptSpentThisWarp` clears whenever the ship is not warping, so each
warp is one sample.

**Six is read off the runs' own warps**, counting warp episodes in the recorded
logs: run 30 warped about 15 times over three hours, run 26 about 14, run 17 six
in half an hour — and the median warp is 16 to 18 readings, comfortably more than
the 5 a hover is allowed. So six moments are reachable in the shortest recorded
session, and a client that genuinely never answers still says so early. The
status line carries both numbers, `tooltip unanswered N, hovers spent M of 6`,
because run 32's operator could watch the first climb to 5 with no way to see
that it was about to end the feature.

**`ammo-swap-range` removes the dependency, not this bug**, and the two changes
are complementary rather than alternatives. With the setting the give-up cannot
fire at all — but the tooltip is also the only way the *second* optimal range is
ever learned, and a run whose hover is only ever attempted at one bad moment
never refines its crossover whether the setting is present or not. The hover is
still not attempted while the setting is set, which is deliberate and is the one
thing here that is left as it was: that would be more mouse work for a
refinement, and it wants its own evidence.

**Verified without a live client**, in
`tools/macos-host/tests/test_ammo_tooltip_retry.py` (28 cases). The rule is
*executed* through the real `Bot.elm` in `elm repl` rather than restated — which
the version it replaces could not be, since it was reachable only through a whole
`BotDecisionContext`, and that is exactly why the shipped version was checked by
reading it. Run 32's episode is re-derived from its log as relations (one hover,
one dispatched effect sequence, the counter reaching the budget, more readings
spanned than the budget counts), run 30's answered hover is asserted to sit
beside real damage and real rats, and the budget's sizing is asserted against the
warp episodes and warp lengths the corpus carries rather than against numbers
written down here. Confirmed by mutation, thirteen of them, each failing a named
case: dropping the in-warp branch of the rule, letting the pocket ask on every
reading, letting one warp spend every hover, moving either bound's comparison,
setting the hover budget back to one, dropping the `ammo-swap-range` clause,
never clearing the per-warp flag, reading the hover count from before this
reading's increment, letting a spent hover keep holding the fight, reverting the
warp branch to `waitForProgressInGame`, pinning the hover counter at a constant,
and putting "never appeared" back into the give-up's sentence.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one is `hovers spent 0 of 6` on the ammo status line while a hover is
in progress, then `Rest the mouse on a weapon` appearing again on a reading whose
decision log reads `I am in warp` — that second hover is the whole change, and it
has never happened. The failure to watch for is the opposite of run 32's: the
counter climbing to `hovers spent 5 of 6` across several warps means the client
really does not answer here and the give-up is doing its job, while a run that
never prints a second hover at all means the warp branch is not reached — the
tell for that would be `I am in warp` beside `hovers spent 1 of 6` and no
`Holding still`.

### The disarm budget bounds an attempt, and it was read as a statement about the guns

Issue #157, which is PR #156's fix for saxrat ported to the bot that reaches the
defect more often. Run 11 switched the whole ammo swap off 21 readings into its
attempt and printed the give-up 763 times afterwards:

```
Ammo swap: given up -- the guns were switched off to load and were still not
back 21 readings later -- a disarmed ship is worse than the wrong charge, so
this will not be attempted again this session.
```

**The guns were not off, and this bot's own module column says so on the same
reading.** `Top-row modules (ramp_active/isInActiveState/...): F/T/F.` —
`isInActiveState` `True`, the gun switched **on** — and it had read that way
since reading 3 of the 21, the client having taken the guns back two readings
after confirming the switch-off. **The ship was disarmed for two readings and
the sentence claimed twenty-one.** Run 27 is the same shape said in words rather
than read off a column, because it postdates #72's status clause: its ammo clause
read `the client switched a gun back on by itself 3 of 20 readings in` and went
on climbing to 18 before the give-up.

**`gunsSilencedTicks` is right, and that is exactly why it cannot be read as a
statement about the guns.** #34's correction made it consult nothing the module
says, because a counter that reads the duty cycle can be stalled by it. What that
buys is a bound nothing can stop. What it does not buy is an account of the ship's
state, and the give-up was written as though it did. The distinction already
existed one function away: `describeAmmoSwapState` stops printing `GUNS OFF` the
moment `switchOffUndoneByClient` latches, and #72's comment there says why. The
status line had it right and the verdict did not.

**It is more reachable here than in saxrat, and #72 is why.** On this bot the
client re-arms the gun by itself on *every* swap, so the condition that made
saxrat's verdict a misreading two times in three is the normal case.

#### The census over `mission_run*.log`

Thirty-two of the 37 recorded runs carry an ammo clause. Two ever reached the
disarm give-up, and **both are the misreading**:

| run | ammo clauses | `GUNS OFF` prints | deepest `GUNS OFF` | re-arm clause | `GUNS OFF` taken with the module reading **on** | disarm give-up | warps | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 11 | 3,802 | 141 | 20 | — (predates #72) | **115** | **1** | 20 | **misread** — the module column reads the gun on from reading 3 of the attempt that gave up |
| 27 | 18,289 | 90 | 14 | 99 | 61 | **1** | 78 | **misread** — its own clause says the client took the guns back at reading 3 |
| 34 | 6,383 | 196 | **20** | 41 | 169 | 0 | 28 | the shape the latch is for, one reading short of firing |
| 35 | 23,913 | 305 | **20** | 19 | 288 | 0 | 74 | the same, twice |
| 26 | 4,508 | 131 | 19 | 192 | 105 | 0 | 14 | the control — swaps complete, no give-up |
| 29 | 10,741 | 148 | 7 | 39 | 106 | 0 | 46 | ditto |
| 36 | 5,110 | 48 | 13 | — | 48 | 0 | 21 | ditto (its own give-up is the neither-charge one) |
| 32 | 2,806 | 0 | 0 | — | 0 | 0 | 2 | the *no-crossover* give-up, #106's |

(The other 24 swapping runs never reached the give-up either; runs 4-9, 13, 17,
19-21, 23, 25 and 33 never printed `GUNS OFF` at all.)

**So the split is 2 misreads to 0 genuine**, where saxrat's was 2 to 1. That is
the census sizing the change: on this bot the narrowed latch is close to
unreachable, which is the *correct* outcome rather than an argument for deleting
it.

**It narrows rather than removes, and runs 34 and 35 are why.** `GUNS OFF for N`
is printed only while `switchOffUndoneByClient` is unset, so a deep count is an
attempt the narrowed rule would still latch on — and both those runs took it to
**20 of 20**, one reading short of the give-up. Removing the latch would leave a
swap that genuinely cannot finish re-disarming the ship at every change of range
for a whole session, which is the runaway #34 is about.

**There is a limit to what the latch can see, and it is worth stating.**
`switchOffUndoneByClient` requires the client to have *confirmed* the switch-off
before it can report it undone, so an attempt whose click never landed cannot set
it. Split by that confirmation across the corpus, every `GUNS OFF` print where
the client confirmed has the module reading the gun **off** and none reaches past
4; every print where it did not is a gun the module reads **on**, and those are
the ones that run to 20. Runs 34 and 35 are that second kind. So the shape the
narrowed latch would still fire on is a ship the module says is firing — the bot
simply has no *latched* evidence of it, and reading the module live here is the
thing #34 refused. That is a real limit and not a regression: today's code latches
on both.

**So the session consequence asks the client's own answer and the attempt bound
is untouched.** `ammoSwapDisarmEndsTheSession` is the rule: the budget expired
**and** the client never reported a gun back on. The budget still ends the attempt
at exactly the reading it always did — nothing is loosened, nothing holds the
fight one reading longer — and only what that costs afterwards changes. That is
PR #151's shape on `lockAttempt`. Reading `switchOffUndoneByClient` here cannot
stall anything, which keeps #34 intact: it is a *latch*, monotone within one
attempt and cleared exactly where `gunsSilencedTicks` is cleared, and it is only
ever consulted to make the outcome milder.

**And the disarm verdict is retried after a warp — the other two are not.**
`ShipCarriesNeitherCharge` is a fact about the ship's hold that nothing short of
docking alters. **`NoCrossoverDistance` is this bot's third latch, which saxrat
does not have, and it gets its own answer rather than inheriting one: it is not
retried, because #106 already spent the warp boundary at the evidence.** That ask
is one hover per warp by construction, so `weaponTooltipAttemptsBeforeGivingUp`
moments are six different warps and `optimalRangeGivenUp` latches only once all
six are gone — and it never clears. Retrying the *verdict* on a warp would change
nothing at all: `weaponTooltipAskIsGivenUp` is still true, so no hover is asked,
no optimal range arrives, `threshold` is still `Nothing`, and the verdict
re-latches on the very reading it was cleared on. What it would buy is the long
sentence reprinted once a warp. (The Open gaps entry PR #156 left here guessed
the opposite, from #111's argument that a hover asked in a new pocket is a
different moment. That argument is right and is already implemented one level
down.)

**A warp is a *subset* of "a new pocket" here, where in saxrat it is a superset.**
This bot enters pockets by acceleration gate as well as by warp, and a gate
leaves no reading that says a site changed — the drone bookkeeping already
records that as the second silent route out. So the retry is at most one per
pocket and sometimes none, which is the conservative side of the trade and the
side to be on for a latch about a disarmed ship. It is the same
`weJustFinishedWarping` the drone abandonment reads, one definition, and a case
pins that.

**The cost is stated rather than hidden**: a swap failing for a persistent reason
now retries once per warp rather than once per session. The runs that gave up
warped 20 and 78 times, so that is tens of attempts over a long session instead
of one — bounded, and named on every reading, where the present behaviour is one
line and silence for hours. The status line says which of the three it is
(`off until the next warp` against `off for this session`).

**`givenUp` is a case rather than a sentence now**, and that is the shape change
under both halves. A `Maybe String` is what let the verdict go on claiming
something the memory beside it already contradicted: a string can be printed and
cannot be asked. `describeAmmoSwapGiveUp` derives the wording from the case, so
the two cannot drift, and the disarm sentence now says how many readings the
*attempt* ran rather than how many the ship spent disarmed — on run 11 those were
21 and 2.

**Verified without a live client**, in
`tools/macos-host/tests/test_ammo_silenced_bound.py` (33 cases, up from 21). The
two new rules are executed through the real `Bot.elm` in `elm repl` — the latch at
both sides of its bound *and* against fixed values either side, with the guns back
and not back at each; the unlatch asked of all three verdicts and folded over a
whole session of readings rather than asked once; and all three sentences
rendered. The corpus is recounted as *relations* and the runs are globbed rather
than numbered, so a run 38 is read without an edit: a run gave up while the bot's
own readings said the guns were firing, a run held the counter to at least half
the budget with no re-arm recorded, and every run that gave up warped many times
more often than it gave up.

Confirmed by mutation, **eighteen** of them, each failing a named case: the
`switchOffUndoneByClient` clause dropped, so an attempt spent entirely on a firing
ship latches the session off (run 11 restored); the disarm verdict made to survive
a warp; the no-crossover verdict retried every warp; the neither-charge verdict
retried every warp; a verdict reached *on* the warp reading cleared by it; the
bound's comparison moved by one; the abandonment conditioned on the same clause,
so the attempt is held longer; the session verdict comparing the bound itself
instead of asking the rule; the call site handing the rule `gunsConfirmedOff`,
which is the same type and the opposite question; the status line no longer saying
which give-up it is; the memory update never seeing a warp; the shared warp
definition weakened to "is not warping"; the latch re-derived each reading instead
of persisting; the sentence dropping the count; the sentence claiming the guns
were still off; the give-up storing its sentence beside the case; the bound raised
past everything the corpus reached; and the two readers each carrying their own
wording.

**The extractor trap PRs #147 and #156 both hit is avoided by construction here.**
A `let` reader that ends at the next ` <name> = ` stops at a *record literal*, so
an assertion about a rule's later fields passes vacuously — and the give-up hands
`ammoSwapDisarmEndsTheSession` a two-field record. `indented_let_binding` slices
by indentation instead, and the case asserting the rule is handed
`switchOffUndoneByClient` reads through the brace.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one: the give-up, when it comes, saying `off until the next warp` and
then **going away** on the next warp with a fresh `wants short-range for N
reading(s)` after it — that retry is the whole of the second half and it has never
happened. A give-up still saying `off for this session` on a disarm verdict means
the case is not being carried; a latch that never comes back across many warps
means `weJustFinishedWarping` is not reaching the swap. Also unverified, and
inherited from #156: **why an attempt that has been given back its guns still
cannot finish**. Runs 34 and 35 reached the budget with the client never
confirming the switch-off at all, which is the "click that does not land" case run
22 recorded and #76's territory, and nothing here addresses it.

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
land between engagements. **Run 11 added the switch-off leg** — four swaps, all
four showing `isInActiveState` going `Just True` → `Just False` on the reading
after the click, the guns back on by reading 3, and the deadline firing at 21.

**Run 17 settles the module tooltip, which this file has called unverified since
#26.** It raises one: eight `Rest the mouse on a weapon to read its optimal range`
prints, then `Optimal range now: 67000 m` on the remaining 2,079 ammo status
lines, with `tooltip unanswered` reading `0` on every one of the run's 2,473 —
so the tooltip came back on the reading straight after the hover and
`optimalRangeGivenUp` never latched. `weaponOptimalRangeFromHover` works on this
client, and the crossover in that run is derived rather than configured.

**Runs 30 and 32 are the two halves of the follow-up.** Run 30 answered on the
third reading of a hover asked in the middle of a fight — twelve rats, 726
hitpoints in the window — and run 32 got nothing across twelve seconds of
perfectly still cursor at the same screen point, then latched the feature off for
three hours. So the hover works, it does not always work, and what separates the
two is not incoming fire. That is #106, and the response is in "The tooltip is
asked where the mouse is free, and one hover is not evidence".

Not verified: **the disarm rule's own code running, in either version.** Run 17
did reach #50's guard — 188 readings of `not disarming` are the evidence #63 was
filed on — but nothing below it has ever run, and #63's rule is executed off-line
against runs 11 and 17's recorded numbers, so what is checked is that it answers
correctly on the inputs those runs produced. Four things to watch on the next run
with `short-range-ammo` and `long-range-ammo` set:

1. **The swap actually firing.** That is the whole of #63, and the tell is
   `GUNS OFF` appearing at all: run 17 printed it zero times across 2,473 ammo
   status prints. The `not disarming` clause now carries the budget beside the
   window, so a run that still never swaps says which half refused.
2. **`GUNS OFF for N of 20 readings, the client confirmed the switch-off`.** The
   two halves should agree — N small, and the confirmation arriving by reading 2.
   A high N beside "has not confirmed the switch-off" is the click not landing,
   which is a different bug from anything here and nothing has ever seen it.
3. **A swap starting and then abandoning on the next reading**, repeatedly. That
   is the budget sitting where the fire in this pocket oscillates across it, and
   it is churn with the guns rather than a swap — the case that argues for a
   smaller share, which no recorded run shows.
4. **That `Ammo swap: given up` appears once** and then as the short flag.

**`loaded charge reads unknown` was not one bug.** It printed on all 2,473 of run
17's ammo status lines and all of run 18's, and the two runs got there
differently — run 17 never opened a menu because the gate never let it, run 18
opened one and abandoned the verdict before reading it. #63 addressed the first
and #72 the second, and **run 21 shows the menu read itself working**: it prints
`loaded charge reads long-range` and derives a crossover from two optimal ranges,
which is the strongest evidence yet that nothing is wrong downstream of the menu.

**Run 26 is where a load was finally watched landing.** The menu re-opened after
a load and no longer offered `Multifrequency M`, which is the client stating the
gun now carries it, and `(satisfied)` appears 2,628 times against run 22's zero.
It is one confirmed read out of seven swaps, for the attribution reason in
"Trusting the load" above — the other six completed on the trust rather than on
a read, and that is what the next run has to show working.

Up to run 22 nobody had watched one. `(satisfied)` appears **zero** times in run
22 — the run that reached `GUNS OFF` 29 times — and its `loaded charge reads`
went `unknown` → `short-range` once, when the menu read resolved, and never
changed again while the swap asked for `Radio M` on 277 prints. **A resolved
charge is the menu read working, not a load landing**, and reading the first as
the second is the mistake to avoid here.

**What run 22 does settle is the arbiter.** `You cannot load or unload Focused
Modulated Medium Energy Beam I while it is active.` appears **134 times** in its
game log and the bot printed `The client refused the load. It said: …` **65**
times. #31 had never fired in a recorded bot run before. So the client does
refuse a load into a gun it considers active, it says so on a channel the bot
reads, and the branch that quotes it works. Every part of the ammo path that
says "if that was wrong, the refusal says so" now has one observation behind it
instead of none.

**Those refusals are the case where the switch-off never landed**, not the case
#72 makes reachable. Run 22's longest episode pressed the button at `T/T/F` and
still read `isInActiveState` `T` three readings later — `none has yet read
switched off` — with an `effect_activating` pulse in the middle, a gun starting a
cycle rather than ending one. The fixed settle then expired and the load went in
regardless. So a click that does not take, and a switch-off the client undoes,
are two different failures and only the second is #72.

**What a load into a *re-armed* gun does is still unknown, and the two recorded
attempts disagree.** Run 11 clicked `Radio M [5]` into a gun reading `F/T/F` and
the client neither refused it (`cannot load or unload` appears nowhere in run 11)
nor changed the charge. Run 22 shows the same client refusing loudly when the gun
read `T/T/F`. `F/T/F` and `T/T/F` are both `isInActiveState = True`, so either
the refusal depends on the cycle rather than the toggle, or run 11's menu click
never reached the entry. **That is exactly the experiment #72 makes possible**,
and it is why proceeding to the load beats abandoning: the client's own answer is
the only thing that can settle it, the guns are firing while it is asked, and the
bounds cap the asking.

One cross-feature invariant, since this and the learned lock range both read the
previous step's effects. They cannot be confused: the lock chord is Ctrl over a
*left* click, the ammo cascade a plain right click, the module switch-off a left
click inside a module button, and the tooltip hover a bare mouse move with no
button at all. And the hover, which holds the mouse still for several readings,
cannot age a pending lock attempt into a false refusal: a refusal needs the
target bar empty at both ends, and the ammo path only runs with an active target.

## The client's transient popup was parsed on every reading and read by nothing

`ParsedUserInterface.layerAbovemain` carries `quickMessage : Maybe QuickMessage`,
which is `{ uiNode, text }` — the literal text of EVE's transient centre-screen
popup, lifted off the `l_abovemain` node on **every** reading since the mission
runner was added. It appears five times in each app's
`EveOnline/ParseUserInterface.elm` and, until #123, **zero times in either
`Bot.elm`**. So every message this client has ever shown a bot was decoded into a
string and discarded, unexamined, on every reading of every recorded run.

**The corpus looked empty because nobody was looking at the right place.** The
operator reports a black popup on trying to lock beyond the ship's capacity,
which is exactly the signal "Lock range is learned from the client" is missing —
and the search that concluded no distinguishable slot-limit refusal exists looked
in the *game log*, where the channels are `combat`, `notify`, `bounty`,
`question`, `info` and `hint`. A quick message is a UI-tree widget, not a log
line, so it was never going to appear there. This is the same shape as
`avoidRats` (parsed, documented, advertised by `--help`, read by no decision —
removed from the mission runner by #125, and still working in saxrat) and
as the game log's `(question)` continuation (`Do you wish to proceed?` parses to
`None` and is dropped), and it is the worse one: evidence that arrived, was
decoded, and was thrown away.

**Logging it is the whole of #123, and the ordering is the point.** No wording
has ever been captured, so a matcher written now would rest on guessed strings —
precisely the trap #92 documents, where a rule keyed on a word list the client's
vocabulary then grew past, twice, without anyone noticing, and precisely what
`briefingSaysClearingIsOptional` avoided by being checked against all 46 recorded
briefings. Both apps now print the message in the status line and **nothing
decides anything on it**, which a case asserts by name: the memory field is read
in exactly two declarations, the update that writes it and the status line that
prints it.

**The clause is carried forward with an age rather than reported live**, and
which of the two it is saying is never left to be inferred:

```
Quick message: none on this reading, and none seen this session.
Quick message (on screen now): "<the client's words>".
Quick message (NOT on screen now -- last seen 12 readings ago): "<the client's words>".
```

A reading is about eight seconds apart and the popup is not, so a live-only
clause would put each message on one line of a log holding thousands of
near-identical ones. Two things need it to persist. The first Unverified item in
#123 is whether `quickMessage` is even the widget the operator is seeing, and
only the operator watching the console can answer that — which nobody can do for
a string that flashes for one reading and is gone. And a popup has to be
readable *beside the decision that followed it*, which is the whole point for a
lock refusal: the popup lands on the reading of the click and the failure is
diagnosed several readings later. The risk carrying it forward creates — a stale
message read as current — is the one this file already answers everywhere by
naming what a number is, and it is named here. The risk live-only creates is the
message being missed, which is not recoverable.

Nothing expires the sighting within a session, for `ShipLossVerdict`'s reason:
an expiry would be a number with no evidence behind it, and the age already says
how stale the message is.

**The text is reproduced, not tidied.** Case, punctuation and interior spacing
are exactly what the client wrote, because the next matcher will be written
against this string and a normalisation applied here is one nobody downstream can
undo. Two transformations only: a cap at `quickMessageStatusCharacterBudget`
(400) which the clause announces with both numbers whenever it bites, and
newline/tab/carriage-return escaped rather than emitted, because the status line
is line-structured — the host prints it after the tick marker and
`stall_watch.py` reads the first line.

**One `l_abovemain` can hold more than one message, and the parser drops all but
the first — in two places.** `parseQuickMessage` filters the layer's descendants
for `pythonObjectTypeName == "QuickMessage"` and takes `List.head`, then takes
`List.head` of that node's `getAllContainedDisplayTexts`. So a second popup is
lost, and so is the second line of a single popup whose text spans two labels.
Nothing in the recordings says whether either happens, so the clause **counts
both and says what it dropped** — `(1 of 2 quick messages in the layer -- the
parser keeps the first and drops the rest)` — which turns the question into
something the next run answers rather than something the parser's `Maybe` leaves
open. The counts are silent when there is one of each, so an ordinary reading is
unaffected.

**Placed outside the ship-UI case in both apps**, because a quick message can be
shown while docked and `describeCurrentReading` is only built for a reading with
a ship UI. The two apps' status lines differ and the clause follows each: the
mission runner's is its own line in the outer list, ahead of the host directive
that has to stay last; saxrat's is its own line ahead of `describeCurrentReading`.

**Verified without a live client**, in
`tools/macos-host/tests/test_quick_message_logged.py` (29 cases, run against
**both** apps). The rules are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python, and the readings go through the real
`EveOnline.ParseUserInterface` from a UI tree carrying two `QuickMessage` nodes
and a message split across two labels, so the counts the clause prints are the
parser's own arithmetic. Confirmed by mutation, fifteen of them, each failing a
named case: the age never advancing, nothing being carried forward at all (the
live-only version of this change), a stale message reading as current, the text
lower-cased, the cap cut to a few characters, the cap biting silently, a newline
emitted rather than escaped, the dropped-message counts pinned at one, the quiet
reading saying nothing, the clause moved inside the ship-UI case in either app,
the memory update no longer ageing the sighting, a decision starting to consult
the message, saxrat's cap drifting from the mission runner's, and saxrat's rule
diverging from it.

One of those mutations survived the first time and the hole was real. The newline
case compared the rendered string in Python, and `elm repl` escapes a control
character on its way out — so a message that really carried a newline and one
that carried the two characters `\` and `n` printed identically and the case
passed with the escape removed. It is compared inside Elm now.

**Settled by saxrat's run 5, which is what this was built for.** Popups survive
long enough to land in a reading — dozens of distinct wordings, the commonest
being `<center>Cargo is too far away. Ship is on automatic approach to cargo.` at
340 live sightings — and **`quickMessage` is the widget the operator was
describing**, since the lock-capacity refusal they reported is among them:
`<center>You are already managing 6 targets, as many as you have skill to.`, 40
times on screen. That was the first Unverified item here, answered with no new
machinery and nobody watching, which is the whole argument for logging a channel
before matching on it. Note the `<center>` wrapper the client puts on these and
the game log does not.

**Count them live.** The clause carries a stale message forward with an age, so
`on screen now` and `NOT on screen now` have to be separated before anything is
counted: the carried-forward totals are three orders of magnitude larger and rank
the wordings differently.

**Still unverified: whether `l_abovemain` ever holds more than one message**,
which the parser drops without a word and the clause counts — a run that prints
`1 of 2 quick messages in the layer` settles that in the direction that says the
parser needs fixing.

**One message is now read, and exactly one.** #146 wires the drone-launch
refusal, in both apps — see the section below. #110 still reads the *targeting*
capacity refusal off the game log rather than off this channel, and the two must
not come to read each other's sentence. What replaced "nothing decides anything
on a quick message" as the case pinning the boundary is a count: exactly one
declaration per app takes a `QuickMessageSighting` and compares its text, and its
name is written down. A second one fails that case, which is the point at which
somebody has to argue for it against a vocabulary this corpus shows growing.

## The client names the drone cap the drones window does not

The drones-in-space group's title carries a maximum, and `launchAndEngageDrones`
in **both** apps took it as the number of drones the ship may have out. That is
bandwidth and bay. The binding constraint on this character is the drone-control
skill, the two differ, and the client says so every time it refuses a launch:

```
<center>You cannot launch Hammerhead I because you are already controlling 5 drones, as much as you have skill to.
```

saxrat's run 6 read `In bay: 3, in space: 5` on **17,919 readings**, pressed
Shift+F **826** times, and had **1,316** of those refusals live on the screen when
a reading was taken — the single most common thing the client said to either bot
in that run, and about a quarter of every live quick message in the corpus. The
mission runner's run 37 shows the same shape at 101 live and saxrat's run 5 at
224. The bot could not tell the launch was refused, so it pressed again on the
next reading, all session.

**This is #110's rule applied to drones, and the two are deliberately kept
apart.** `You are already managing 6 targets, as many as you have skill to.` is
the same sentence to within two words and is already consumed, off the game log,
to set the lock-slot ceiling. Two rules reading each other's sentence would be
two wrong ceilings — a lock ceiling capped at the number of drones, or a drone
ceiling capped at the number of lock slots — so the exclusion is over-determined
in both directions, exactly as #151's is: `controlling` is not `managing`, `much`
is not `many`, and the count is sliced after `already controlling`, a clause the
targeting sentence does not contain at all.

**The matcher is checked against every wording the corpus holds**, which is
`briefingSaysClearingIsOptional`'s discipline applied to a channel with a much
larger vocabulary: **108 distinct quick messages** across mission run 37 and
saxrat runs 5 and 6. Two of them match both markers and both are this refusal,
differing only in the drone's name — `Acolyte I` and `Hammerhead I`, which is why
nothing in the matcher reads the name. Everything else is declined, including the
four nearest misses: `Acolyte I cannot be dropped because it is not in your drone
bay.`, `Drone cannot be commanded as it is not actually present.`, `The drones
fail to execute your commands as the target … is not within your … drone command
range.`, and the narration `Drones engaging …`.

**`Cargo is too far away. Ship is on automatic approach to cargo.` is declined,
and it is the reason there is no general rule.** It is the commonest message in
the mission runner's run 37 at 795 live, and it is **not** a refusal — the client
is confirming it took the command and is flying there. A rule keyed on "a quick
message means something went wrong" would be wrong about it 795 times in one run,
and a case executes the shipped matcher against it for that reason.

**Counted live, and the rule refuses an aged sighting itself.**
`quickMessageAfterReading` carries the last message forward with an age until
another replaces it, so carried-forward totals are three orders of magnitude
larger and rank the wordings differently — the ranking this whole section rests
on inverts if they are counted. `droneLaunchRefusalStatedInQuickMessage` requires
`readingsSince == 0` inside itself rather than trusting its callers, because
`memory.quickMessage` and `quickMessageOnScreen` both type-check at the call
site and a rule wired to the first would learn a cap from a popup shown before
the last dock.

**`min`, not replacement, because neither number is a guess.** Unlike
`maxTargetsCeiling` — where the setting was an operator's guess and the client's
sentence a fact — both halves here are read off the client: the window's maximum
is a real bound this ship has, the sentence is a real bound this character has,
and the lower of two real bounds is the one that binds. A statement naming a
number *above* what the window offers raises nothing.

**Absent evidence never moves the limit.** With nothing stated the ceiling is
exactly the window's own number, so a session in which the client never refuses a
launch behaves precisely as every session did before this rule existed. And
nothing latches across sessions: `initBotMemory` starts at `Nothing`, so each
session launches up to the window's maximum, is refused at most once, and stops —
one refusal per session against run 6's 1,316. That is also what keeps this from
freezing a character whose drone skill is still training, and within a session the
latest statement wins.

**The status line carries both halves separately**, because they fail
differently: `Drone launch ceiling: 5 (drones window says 8, client stated 5).`
A run whose `client stated` never leaves `-` is one whose popups are not reaching
the rule; a window number that never drops below the ceiling is a ship whose skill
was not the binding constraint. The move is announced once at the root, beside
`maxTargetsLastChange`, through `lockRangeLastChange`'s mechanism.

**The bot re-issues commands the client has already accepted, and this change
does not fix that.** Measured on the readings the automatic-approach message was
live: the mission runner re-commanded an open-cargo or loot on **691 of 795**, and
saxrat re-issued an approach (`Press the 'W' key and click on the overview entry`)
on **307 of 340**. Whether that is harmful is not established — the client may
simply be re-accepting a command it is already executing, as it appears to for
the approach — and the same shape is what the docking run-in section already
records costing run 27 an eight-minute dock. It is recorded here because it is the
next thing this corpus points at, not because #146 acts on it.

**`Drone cannot be commanded as it is not actually present.` was considered
alongside and deliberately left**, at 76 live in run 37, 117 in run 5 and 449 in
run 6. It does not share a consumer: the launch refusal is answered by the launch
branch's own limit, where "cannot be commanded" arrives from the engage and recall
commands and has no existing bound to feed. Wiring it is its own change with its
own evidence.

**Verified without a live client**, in
`tools/macos-host/tests/test_drone_launch_refusal.py` (35 cases, run against
**both** apps). The rules are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python, and the sightings they are asked about come from
the real `EveOnline.ParseUserInterface` off a UI tree — **neither parser needed a
change**. The corpus is recounted as *relations* rather than as the numbers above:
the refusal really occurs and names more than one drone, the shipped markers read
every recorded refusal and recover the count, the shipped markers admit nothing
else out of the 108 wordings, the automatic-approach message is among the ones
declined, and the bot really did press launch again on a reading whose screen
already carried the refusal.

Confirmed by mutation, **twelve** of them, each failing a named case: a general
"any live quick message means the launch failed" rule (which admits the
automatic-approach message, and is the rule #146 forbids by name); the naive
matcher with all three exclusions gone (which admits the targeting sentence);
the live-only guard dropped so a carried-forward sighting teaches a cap;
`min` for `max` so a stated skill cap raises the launch site above the window;
absent evidence taking a default; the smallest statement winning rather than the
latest; the launch site reading the window's maximum directly again; the count
taken as the first integer in the sentence; the status clause neutralised; the
move never announced at the root; the rule landing in one app only; and a second
matcher on the quick message, which fails #123's own boundary case next door.

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one is `Drone launch ceiling: N (drones window says M, client stated -)`
on every in-space reading, then `client stated 5` within a reading or two of the
first refusal, then `Learned drone launch ceiling: …` once in the decision log and
never again — and then `You cannot launch` disappearing from the quick-message
clause for the rest of the session. A run that fights and never leaves
`client stated -` while the refusal is on screen means the sighting is not
reaching the rule. The failure to watch for is the opposite: a ceiling learned
from a *stale* popup, whose tell is `client stated N` appearing on a reading whose
quick-message clause reads `NOT on screen now`.

## The route panel names the next system, so the panel can jump the right gate

Ordinary gate-to-gate travel goes through `routeMarkerCascade`: right-click the
route panel's first marker, take the menu's `Jump Through Stargate`. It is the
worst-behaved cascade in the codebase and its own comment says why — it carries a
distance tolerance of 200 rather than the shared 70 because *"'Jump Through
Stargate' took 3-4 menu opens before being recognized"* against an 8x8 icon in a
strip that shifts as the route updates. `selectedItemJump` is the one-click
alternative and is now **read** rather than inferred, off a live client with a
**stargate** selected:

```
selectedItemApproach    selectedItemJump       selectedItemKeepAtRange
selectedItemLockTarget  selectedItemOrbit      selectedItemResetCamera
selectedItemSetInterest selectedItemShowInfo   selectedItemWarpTo
```

**The panel's button set is object-specific, and that is what made #167 look
unbuildable twice.** An acceleration gate in a mission pocket draws
`selectedItemActivateGate` and `selectedItemLookAt` and **no jump**; a stargate
draws `selectedItemJump` and `selectedItemResetCamera` and no `LookAt`. Two
readings taken with a gate selected concluded the button does not exist, and both
were reading the wrong kind of gate. A capture of one gate says nothing about the
other.

### The marker cannot name the gate; two other renderings can

`InfoPanelRouteRouteElementMarker` carries a `uiNode` and **no name**, which is
what blocked the original approach and is still true — the parser lifts every
`AutopilotDestinationIcon` and nothing else. What answers instead is two things
the client renders and nobody had read, both taken off the live client:

```
route panel   <a href="showinfo:5//30005001" alt="Next System in Route">Arnon</a>
overview row  Name "Adirain"   Type "Stargate (Gallente System)"
```

So the identity is a name match between the system the route says is next and the
system a gate's own row says it leads to. `routeIsSet` already reads that
`NextWaypointPanel` for its *visibility* and had never read its text; the label
has the same two quote styles `parseCurrentSolarSystemFromUINodeText` handles,
this client writing `alt="…"` and the 2019 recording in `explore/` writing
`alt='…'`.

**Only the row's Name is matched, never its Type**, and the column order was read
off the live client's headers (`Icon | Distance | Name | Type | Size | Velocity |
Angular Velocity`) rather than assumed. A type reads `Stargate (Amarr Border)` and
**Amarr is a real system**, so a rule looking at both columns would match a gate
leading somewhere else entirely on the strength of the region it borders. The
"is this a stargate at all" question still reads both, because which column
carries the word is a matter of overview preset.

**Matched on word boundaries with punctuation read as a separator.** A plain
substring rule takes `Ami` out of `Amir`; `containsWords` alone cannot match
`Adirain` inside `Stargate (Adirain)`, which is what a different preset renders;
and both sides get the same normalisation so a hyphenated system name like
`1DQ1-A` is compared as the same sequence of words on each side.

### Every clause is a way it could act on the wrong object

**A jump to the wrong gate is a wrong system, not a wasted tick**, so
`routeStargateJump` refuses on anything it cannot identify and the fall-back is
`routeMarkerCascade` — which right-clicks the route's own marker and cannot pick
the wrong gate at all. Five refusals: no next system named, no gate named for it,
**more than one** gate named for it, the panel showing something else, and the
panel not offering the button.

**Where the panel is showing something else this falls back rather than selecting
the row first**, which is the one place it departs from `selectThenPanelAction`.
Selecting spends the very reading this exists to save, and the cascade travels
the route regardless.

### The saving is one to two readings, and that is the finding

Recounted from `~/eve-bot-logs` in **readings** rather than decision lines — this
file's own first orientation note, and the unit that has cost a threshold
calibration twice — the cascade costs:

| run | readings in the cascade | jump legs | median | mean | worst leg |
|---|---:|---:|---:|---:|---:|
| 35 | 123 | 31 | 3 | 4.0 | 11 |
| 37 | 64 | 20 | 2 | 3.2 | 9 |

So *"3-4 menu opens"* describes the tail rather than the normal case, and **the
saving is one to two readings on the median leg**. That is stated small
deliberately and is a legitimate answer to the issue's own first question: this
is a cheaper way to issue a command that mostly works, not a rescue of one that
does not, and what it is weighed against is a wrong system. It is worth having
only because the identity condition makes the risk unreachable rather than small.
`test_route_stargate_panel_jump` reads those counts back out of the doc comment
and recomputes them, so a claim the corpus stops supporting goes red.

### A finding this turned up, and #171 is what fixed it

**`dockAtDestinationStation`'s "exactly one route marker means the destination is
in this system" was not what the panel draws.** Read live: the header said `Route
1 Jump`, the panel held **one** `AutopilotDestinationIcon`, and that marker
carried `solarSystemID 30005001`, `destinationID 60012607` (a station) and
`numJumps 1` — a destination one jump away, not in this system. The 2019
recording agrees from the other end: `Route <fontsize=12></b>3 Jumps` with
**three** markers. So the count is jumps remaining, and `destinationIsInThisSystem`
was true one system early. Run 37 shows it live, reaching the dock branch mid-route
and being saved only by #98's undocked-from guard.

**Not fixed at the time this section was written** — that was #98's area, and
changing it was a behaviour change on the dock path wanting its own evidence.
Issue #171 is that evidence and that change:
`InfoPanelRouteRouteElementMarker.numJumps` is lifted into all six vendored
parser copies (`getIntPropertyFromDictEntries "numJumps"`, identical across all
six), and `dockAtDestinationStation`'s `destinationIsInThisSystem` now asks
`destinationIsInThisSystemFromRouteMarkers` — exactly one marker, and that
marker's own `numJumps` reading `Just 0` — instead of counting icons. Neither
`routeMarkerCascade` (which right-clicks the head marker's `uiNode` and never
counts) nor #170's `routeStargateJump` / `jumpThroughRouteStargate` (which
reads the `Next System in Route` label and the overview, and never touches
`routeElementMarker` at all) depended on the count meaning waypoints, checked
rather than assumed. #98's `stationIsTheOneJustUndockedFrom` guard is
untouched — it was doing real work for a reason unrelated to the marker count,
and still runs on every dock this branch attempts.

**What the client writes on genuine arrival is still unread.** Every live
reading available had at least one jump remaining, so whether `numJumps` reads
`Just 0`, `Nothing`, or something else there is not established. The rule
fails closed on that: an empty list, several markers, or an
unreadable/nonzero `numJumps` all decline and send the ship to the cascade
fall-back, which still travels the route. **Untested against a live client**;
see `tools/macos-host/tests/test_route_marker_num_jumps.py` for the parser and
the rule, both executed through the real `Bot.elm` and the real
`EveOnline.ParseUserInterface` rather than restated in Python. What to watch
on the first run that reaches this branch: whether `destinationIsInThisSystem`
ever answers `True` at all — if it never does, the client is not writing `0`
where this rule expects it, and the branch is falling through to the cascade
exactly as before #171.

**Verified without a live client**, in
`tools/macos-host/tests/test_route_stargate_panel_jump.py` (44 cases). The rule is
executed through the real `Bot.elm` in `elm repl` at each of its six answers,
asked as six equalities per case so a rule answering two things at once — or none
— fails rather than passing on whichever constructor a case named; the label parse
is run against the client's own markup in both quote styles and against the
panel's *other* system-naming label; and the wording is rendered rather than
asserted by substring over the branch, which is how a case written to catch a
press aimed at the wrong button once passed on the branch's own log text. The
wiring is read out of the source through a reader sliced by **indentation**, since
the binding under test builds a record and the `let_binding` shape stops at its
opening brace — PRs #147, #156, #159 and #162 each paid for that once. The corpus
is recounted as relations as well as as the quoted numbers: the cascade costs more
than one reading a leg, the median leg is small, and some leg is far larger.

Confirmed by mutation, **fifteen** of them, each failing a named case: **the
panel-identity clause dropped, so it jumps while the panel is showing a different
gate** — the failure this whole design refuses; two gates named for one system no
longer declining; the identity match reading the row's type as well as its name;
the name match weakened to a substring; the punctuation normalisation dropped; the
jump button no longer required; the label marker loosened so the route's
*destination* reads as its next hop; the empty-name filter dropped, so a nameless
system matches every gate; the panel path dropped from the travel leg; the panel
identity computed once rather than per row; the virtualised-row filter dropped;
the fall-back waiting instead of handing the caller's step back; the retreat given
its own second copy of the stargate predicate; a fall-back sentence no longer
naming the route marker; and the measured saving in the doc comment changed.

**Unverified: any of it running, and one premise about the panel.** No run has
been flown since. `selectedItemIsOverviewEntry` compares the overview row's Name
against the Selected Item panel's display texts, and **no capture of that panel
with a stargate selected has ever recorded its texts** — only its buttons. If the
panel names a gate some other way the branch simply never fires and the bot
behaves exactly as it does today, which is the safe direction and the reason this
ships without it. Also unread: whether `selectedItemJump` is drawn on a gate that
is *out* of jump range. Either answer is safe — drawn, the press is the client's
own warp-and-jump at the right gate; absent, this falls back to the cascade, which
is what flies the ship there.

What to watch on the first run that travels a route: `Jump through '<system>' from
the selected-item panel, which is already showing it.` appearing at all. A run
that jumps gates and never prints it — printing
`The selected-item panel is not showing the stargate to '<system>'` instead on
every leg — means the panel is never found to be showing the gate, which is the
direction this fails silently in and costs nothing. The one to escalate on is the
opposite: a jump followed by the route panel naming a system nobody asked for.

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

## "The nearest lootable object" was the nearest object of any kind

Run 12 raised `askForHelpToGetUnstuck` 817 times on `Illegal Activity (1 of 3)
-- Retrieve Gallente Light Marines`, having opened six wreck types and taken
109 loot decisions first. Issue #53 read the overview as 63 rows of wrecks 28 m
away that the bot had wrongly written off, and proposed expiring the emptied
set. **All three parts of that are wrong, and reading the live client while it
was still stuck is what showed it.**

- **"28 m" is the Size column, not Distance.** The overview's headers on this
  client are `Icon | Distance | Name | Type | Size | Velocity | Angular
  Velocity`, and a Gallente Small Wreck's radius is 28 m. The wrecks were
  2,699 m to 57 km away. The bot reads cells by header region and was never
  confused; the operator's read was.
- **There were 12 wrecks, not 63.** The other 51 rows are 41 Sharded Rocks,
  three stargates, a sun, an Azbel, a trade post, a Ruined Neon Sign, a storage
  silo, a mining post and a beacon.
- **All twelve carried the texture `wreckLootedNPC.png`.** So
  `overviewEntryLooksLooted` retired them — statelessly, from the client's own
  icon, not from anything remembered. They really were empty.

The item was in the mission's own `Cargo Container`, which the bot found at
43,000 m, ranked first (`prefer-wreck` ships `Cargo Container, Personnel
Transport` since #52, and that is what put a 43 km container ahead of wrecks at
11 km), and was flying to when the client wrote

```
[ 2026.08.03 15:20:42 ] (notify) Cargo Container has just left Irnin as of 2 seconds ago
```

Sixteen readings, 43,000 m → 42,000 m, and it was gone. The client was still
rendering `You need Gallente Light Marines in your cargohold` hours later with
nothing matching "marine" anywhere else in the UI tree.

**Run 13 is the disproof of every accumulating explanation.** Restarted onto the
same accepted mission with an empty `BotMemory`, it reached the same dead end on
its *third* reading and stayed there for all 495: 483 `Nothing to fight and no
travel step offered`, and across 6,069 log lines not one `Look inside`, not one
`loot-open`, not one `A row I want is off screen`. A fresh process cannot be
carrying a stale candidate set or a per-type "already opened" record. **The
objective was unwinnable and the bot was right about the grid.** Recovering from
an objective that can no longer complete is a separate problem — issue #54.

**What was genuinely broken, found while establishing that:**

```elm
nearestLootableEntry readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter (\entry -> entry.objectItemID /= Nothing)
        |> List.sortBy overviewEntryDistanceOrFarInMeters
        |> List.head
```

`missionObjectiveText`'s own comment, fifteen lines below it in the same file,
says why that is not a filter: *"Every row has one — stargates, stations, the
sun."* The identical mistake, in the identical field, and this copy survived it.
So "the nearest lootable object" answered with the nearest object of any kind,
and two callers believed it:

- **`shipIsWithinLootRange`** asks whether the container the bot has open is
  within 2,000 m and was answered about whatever was physically closest. Its
  false branch — `Still on the way to the container` — appears **zero times
  across all thirteen recorded runs**, while run 12 alone decided `Click 'Loot
  All'` 109 times. A guard that has never once been false is #34's shape again.
- **`openWreckLootWindowAndId`** hands that row's id to `lootedWreckIds` and
  `unlootableWreckIds`. On run 12's own grid, 51 of 63 candidate rows could not
  hold anything, so an emptied wreck could be recorded under an asteroid's id
  while the wreck itself went unmarked.

The fix is one shared rule, `textNamesALootableObject` (whole words, for
`containsWords`' reasons — a rogue drone called a "Wrecker" contains "wreck"),
asked by the picker, the scroller and this function, plus a `_display` filter
because this sorts by a distance a virtualised row reports staler than it looks.
The scroller keeps its extra `warehouse` word, written at its own call site
rather than folded in, since it wants a Cargo Warehouse brought into view and
the picker does not open one.

**Making a guard answerable makes the branch behind it reachable**, and that
branch waits. `lootWindowOutOfRangeTicks` bounds it, and it used to reset
whenever `openWreckLootWindowAndId` could not resolve a row — which is precisely
the state the fix creates, a loot window open with no lootable row on the
overview to measure against. Both it and `lootAllRefusedTicks` now count from
the open *window*; only the two id memories still need a resolved row, because
an id is what they store.

**Verified without a live client**, in
`tools/macos-host/tests/test_lootable_object_identity.py`: the word rule is run
through the real `Bot.elm` in `elm repl` against all sixteen distinct
Type/Name pairs the stuck client was holding, plus the traps this repo has
already paid for; run 13's log is asserted line by line as the cold-start
disproof; the wiring, the counters' arithmetic and the scroller's extra word are
read out of the source. Confirmed by mutation: a substring match admits
"Wrecker", reverting the filter to the item id alone breaks the wiring tests,
and pointing either counter back at `openWreckLootWindowAndId` breaks its bound.

**Unverified: any of it running.** Nothing in the recordings exercises the fixed
path, because the branch it makes reachable has never been reached. The first
run that opens a container from outside 2,000 m should print `Still on the way
to the container -- wait until inside 2000 m before taking anything.` and then
`Click 'Loot All'` on arrival; if it instead prints that line for 250 readings
and gives up, the range read is wrong in the other direction. Whether the
container id now recorded is the right one cannot be checked from a log at all —
the bot never prints it — so the tell is negative: no repeat of a wreck already
emptied.

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
previous steps' effects, which `UpdateMemoryContext` did not carry;
`BotFrameworkSeparatingMemory.elm` now passes `previousStepsEffects` through.
That was a mission-runner-only divergence until saxrat was given the same bound
— see "What saxrat has of this, and what it does not" — and the two copies are
now identical and checked to be.

### #11 held, and the seventeen lost drones were three different things

Issue #59 proposed going back for abandoned drones and asked first whether the
bot still abandons any. Measured across the sixteen finished runs in
`~/eve-bot-logs`, **it does not, and has not since run 1.**

The runs are separable by their own status lines rather than by when a pull
request merged: #11 added `unanswered recall for N` beside the drone counts and
the later status rewrite made it `Nbay/Msp out K`, and both are unconditional.
Run 1 carries neither; runs 2, 7, 15 and 16 never got to space with a bay to look
at; every other run carries one.

- **`returnDronesToBay`'s give-up has fired zero times in any recorded run.**
  Since #11 that branch names itself on every reading it declines, so zero is
  evidence rather than the silence it was before — the branch was reachable and
  was never reached.
- **Only run 1 ever left a grid with drones in space.** 24 readings of
  `I am in warp` and 12 of `Jump Through Stargate`, all with five drones out.
- **Recalls land.** Runs 9, 10, 11, 12 and 14 completed 41 between them, each
  ending with the in-space count at zero and the bay holding what came back.

The seventeen drones the issue counts are three unrelated things, and only the
first is what it describes:

- **Ten, in run 1, genuinely abandoned** — the pre-#11 failure.
- **Five, in run 8, not lost at all.** That run *ended* 3 in bay / 5 in space
  because an operator stopped it mid-pocket, and run 9 started in the same place
  and had all five back 40 readings later. That is also the only direct evidence
  here that abandoned drones persist and can be reclaimed.
- **Two, in run 5, destroyed in space by rats** while the ship was still on grid
  and fighting, with the survivors recalled normally at tick 450. Run 14 lost
  three the same way and run 17 its last one, mid-fight, on the reading the
  client was still logging hits on the rat that killed it.

**Counting the drone bay at the start and end of a run cannot tell those apart**,
which is what made the issue's estimate look like a recovery opportunity. What
separates them is where the ship was when the count fell.

So there is nothing yet to build a recovery path *for*, and the observation is
what landed instead. `droneAbandonmentAfterReading` records what was in space and
where, and says so on the reading the ship leaves without it — a decision-log
line once, and a `LEFT BEHIND N at <place>` clause in the status line for the
rest of the session. Nothing acts on it, which a test pins.

**The departure is read at its far end, and run 11 is why.** A ship lining up to
warp still has time to get its drones home: run 11 spent 21 readings of
`I am in warp` with five drones out and had all five in the bay by the reading
the warp finished. Firing on the *start* of a departure would have reported an
abandonment that did not happen, which is worse than reporting none. The trigger
is therefore `weJustFinishedWarping`, plus the reading the info panel first names
a station — the other way a site is left, and the one where the drones window has
already gone, which is why the count and the place are written down beforehand.

`Nothing` from the drones window means "this reading cannot say", never "the sky
is empty": `dronesInSpaceCountReadable` is the `Maybe` the bookkeeping needs and
`dronesInSpaceCount` is that value defaulted to 0, so every existing caller is
unchanged. The place is the solar system and the mission, which does not
distinguish two pockets of one mission — the client never names the pocket, and
a recovery path would need something this reading cannot give it.

**Two silent routes out remain, and neither has cost anything yet.** The docked
branch's travel step (`decideActionWhenDockedWithMissionTracker`) does not recall
drones, correctly while docked — but that branch is entered whenever the ship UI
fails to parse. Run 11 went through it at tick 232: three consecutive readings
printing `I see no ship UI, assume we are docked` followed by
`The mission tracker offers the next travel step: 'Dock'`, and one input
dispatched. Those readings could see nothing of the drones, because a reading
with no ship UI prints no drone status — but the readings either side of them
report `In bay: 3, in space: 5`, and the client's combat log inside the same
window records this ship's guns hitting a rat, which a docked ship cannot do. The
other route is an acceleration gate, which changes pocket without a warp. The
observation covers the consequences of both, since it watches arrivals rather
than departures; what it does not do is stop either.

### The mission runner's warp half was the dead half, and two consumers were waiting on it

Issue #205, and it is #194's condition found in this bot rather than a new
defect. `weJustFinishedWarping` read

```elm
(botMemoryBefore.shipWarpingInLastReading == Just True) && (shipIsWarping == Just False)
```

and `shipIsWarping` is a `Maybe` over the manoeuvre the client **names**. At the
end of a warp the client names none, so the transition is `Just True -> Nothing`
and that condition could not answer `True` at the end of a warp in any recorded
run. The argument, the captured indication container and the replacement are all
#194's — see "The on-arrival pilot check could not fire" above.
`shipWarpingFromReading` and `warpJustEnded` are ported byte-identical, so all
four apps now carry one rule.

**Which is why this was a behaviour change and #233 deferred it rather than
overlooking it.** Two live consumers read that value here, and neither had ever
seen it answer `True`:

- **`droneAbandonmentAfterReading`'s `shipLeftThisReading`** is
  `weJustFinishedWarping || (dockedNow && not dockedInLastReading)`. Only the
  docking half worked, so drones left in space were noticed when the ship docked
  and **never when it warped out of a pocket** — which is the case the rule's own
  comment says it exists for. It now records the count and the *sighting's*
  place on the arrival and drops the sighting, so the warp home and the dock
  that follows it are one event rather than two. **Nothing acts on it**: the
  verdict is read by `missionBotDecisionRoot`'s one-line change report and by
  the status line, and by no decision. That was cheap to hold while the half was
  dead and is pinned now that it is live.
- **#154's per-warp ammo-swap give-up retry**, through
  `ammoSwapGiveUpAfterReading`. A `GunsDidNotComeBack` verdict is cleared on the
  next warp and was never cleared at all, so a swap that failed once stayed
  given up for the session — **while the status line said `off until the next
  warp` on every reading of it**, which is a promise the bot could not keep. It
  can now: the abandonment clears `gunsSilencedTicks` on the reading after the
  budget expires, so the cleared verdict cannot re-latch on the reading it was
  cleared on. The other two verdicts still survive a warp, and
  `NoCrossoverDistance` surviving is #157's argument rather than an oversight —
  #106 already spends the warp boundary at the *evidence*, one hover per warp,
  so retrying the verdict would re-latch it immediately and buy nothing but the
  long sentence reprinted once a warp. That is the tooltip/optimal-range hover
  family, which is mission-runner-only on purpose and is untouched here.

**The ship-UI clause is load-bearing here in a way it is not in the anomaly
bots.** `Nothing` is equally what a reading with no ship UI answers, and this
bot **docks** — so a fix written as `/= Just True` and nothing else would make
every docking reading a warp ending, and `shipLeftThisReading` would fire twice
for one departure.

**Verified without a live client**, in
`tools/macos-host/tests/test_mission_runner_warp_end_trigger.py` (25 cases). The
transition is executed through the real `Bot.elm` in `elm repl` against readings
built by the real `EveOnline.ParseUserInterface` from the shape captured during
saxrat run 29, reusing `test_arrival_pilot_window.py`'s own `WARP_READINGS`; and
**both consumers are folded over the same readings twice**, once through the
shipped trigger and once through the condition it replaces, so what separates
the two answers is the trigger and not the fixture. Confirmed by mutation,
twelve of them, each failing a named case, listed in that file — including the
ship-UI clause dropped, which fails once on the trigger and again on the docking
reading the drone rule would then double-count; `ammoSwapGiveUpSurvivesAWarp`
flipped for `GunsDidNotComeBack` and, separately, for `NoCrossoverDistance`,
which is the hover family being pulled across; and a decision starting to
consult `dronesLeftBehind`.

**`TheMissionRunnerIsUntouched` was PR #233's deferral marker and is replaced
rather than deleted.** It asserted this bot **still had** the dead condition, so
it collides with the change that fixes it — which this repo has now been bitten
by twice. What replaces it,
`test_wingus_warp_end_trigger.TheFourAppsCarryTheSameWorkingTrigger`, keeps what
was worth keeping: four apps carry one rule that is app-specific in no part of
it, so it compares all four byte for byte and refuses the dead shape in any of
them. A future divergence is then a decision somebody argues for rather than one
the suite lets happen.

**Unverified: any of it running.** No run has been flown, and by construction
neither consumer has ever fired on the warp half in a recorded run. What to
watch on the first run that warps out of a pocket with drones in space is
`Left drones behind:` in the decision log and then `LEFT BEHIND N at ...` in the
status line — this bot has not abandoned drones since run 1, so a quiet run
proves nothing either way. On the first run whose swap reaches
`GunsDidNotComeBack`, the give-up saying `off until the next warp` and then
**going away** on the next warp with a fresh `wants short-range for N
reading(s)` after it; that give-up has fired twice in 37 runs and #157 narrowed
it further, so it may be a long wait. The failure to watch for is a
`Left drones behind:` line on a reading the ship merely docked, which would mean
the ship-UI clause is not doing its work.

## What saxrat has of this, and what it does not

Almost everything above is about *the client and the ship* rather than about
missions, agents and stations, and all of that applies to `eve-online-saxrat`
unchanged. Until this port it had almost none of it, and the gaps were the
shipped configuration rather than edge cases:

| guard | saxrat before | now |
|---|---|---|
| the HUD gauges | compared **live** against the threshold, no confirmation, no low-water mark | `believed` values behind a low-water mark, as above |
| both hitpoint thresholds | default `-1` — so **no retreat guard at all** | unchanged defaults, and a third guard that is armed |
| damage-rate retreat (#32) | absent | ported, `run-away-incoming-damage-threshold`, default 3500 |
| ship loss (#33) | absent — a destroyed ship meant ratting in a capsule, which reads 100/100 | ported, above the docked-or-in-space split, bounded at 150 readings |
| the pod recovery's bound (#133) | the comparison sat inside `recoverPodAfterShipLoss`, below `generalSetupInUserInterface`, over a counter that advanced anyway — and with no message-box standoff, nothing here ends the starvation | `podRecoveryOutOfTime`, asked from `endSessionOnAnExpiredBound` at the head of the decision root |
| the message-box standoff (#138) | `closeMessageBox` clicked its dismissal every reading for as long as a box was showing and **counted nothing** — neither of the mission runner's two bounds existed here | `MessageBoxStandoff`, the same ladder: answer, Escape, then `Nothing` so the rest of the tree runs |
| drone recall (#11) | **no bound of any kind**, in front of every warp, tether and dock | `droneRecallUnansweredTicks`, give-up, focus-recovery click |
| what it will shoot (#40) | the overview's icon colour and nothing else | plus whatever the combat log names as hitting the ship |
| setting its own route | could only *follow* one a human set | `hunt-system` circuit, asked for through the host's ESI directive |
| the client's transient popup (#123) | parsed on every reading and read by nothing — the same five references and the same zero readers | printed in the status line, carried forward with an age, and since #146 read by exactly one decision (the drone-launch cap) |
| the lock range (#121) | `targeting-range` asserted and never revised — `lockProvenAtMeters` appeared 0 times | the setting clamped into `[proven, refused)`, learned from the client's own answers, with the row-identity discipline unchanged |
| the lock-slot ceiling (#110, #150) | `maxTargetCount = 4` hardcoded with no setting able to reach it, against a real maximum of 6 — 2,149 readings of `Enough locked targets.` across runs 2-5, and a `List.take 4` candidate window that would have capped it there anyway | `max-targets`, clamped by the maximum the client states on the game log and by what the target bar has held, and asking for one row more than that until the client states the number |
| the ammo swap (#122, #154) | absent, not unconfigured — `ammoSwap`, `Charge`, `chargeName` and `optimalRange` all appeared 0 times, and there was no setting to turn on | ported without its tooltip half, with `ammo-swap-range` **required** rather than optional; and since run 10, a disarm give-up that asks whether the guns came back and is retried after a warp — see the two sections below |
| an in-range acceleration gate (#145, #147) | a context-menu cascade, and a give-up counting readings *near* a gate rather than readings spent asking one — `selectedItem` appeared 0 times in `Bot.elm`, so it had never pressed a panel button for anything. And the branch was **unreachable inside a site at all**: a "Warp to Site" button anywhere in the tree outranked it, and the panel goes on drawing one after arrival | `selectThenPanelAction`'s shape over `selectedItemActivateGate`, inside `unlessAlreadyClosingIn`; the counter counts the ask; and `siteProgressStep` asks the gate first and declines a site offered while a gate is in reach — see the two sections below |
| the route's next stargate (#169) | the route-marker cascade on every leg, at a median of **12 and 13 readings a leg** and 23% and 38% of every reading in runs 13 and 14 — against the mission runner's 3 and 2 and its 2% and 3% | #170's rule ported whole: the route panel's own `Next System in Route` label matched against the overview row's Name, and `selectedItemJump` pressed only where the panel is already showing that gate — see the section below |
| the combat feed (#190) | six lines of the client's `CombatMessage` widget in the status text on every reading — a third of runs 20 and 21, 99.5% of it repeating the block before it, and in run 20 mostly printed while docked | removed, as the mission runner removed it; the incoming half of that channel is `describeIncomingDamage`, already on every reading — see the section below |
| leaving an anomaly somebody was already sitting in (#194) | reachable code that could not fire: `weJustFinishedWarping` demanded `shipIsWarping == Just False`, which the client only ever answers while some **other** manoeuvre is named — a warp ending answers `Nothing` — so the trigger was unreachable and `FoundOtherPilotOnArrival` has never been constructed in a recorded run | `warpJustEnded`, on `Just True` followed by anything that is not `Just True`, with the ship UI's presence read separately so a reading that could not see the ship is not an arrival; "arrival" stays the landing reading, which is what the corpus measures — see the section below |
| the overview's EWAR hints (#267) | read and never shown: `combatPriorityTier` acts on two of the five literals the corpus holds, through `commonIndications`, which the parser derives from exactly these strings — and across saxrat's 227,749 recorded readings there is no `Overview indications:` line or equivalent, because that clause was mission-runner-only | `describeOverviewIndicationHints`, in saxrat's own words (`hints 2 ('…' '…')`): distinct strings from rendered rows only, capped at eight with the count taken before the cap |
| nothing watching the ship's health (#267) | `attritionIsUnguarded` was mission-runner-only, and saxrat's shipped defaults are exactly the state it names — both hitpoint thresholds at `-1`, so a run started without settings had the damage window armed and neither gauge guard able to see a grind, and said so nowhere | the rule byte for byte as the mission runner has it, and `describeRetreatCover` **without** its low-water-mark half, which saxrat already prints beside the withheld-readings count |
| what its own guns achieved | `outgoingDamageSinceLastReading` read in **zero** places: every shot the bot ever fired was summed by the host, decoded by the parser and thrown away, on every reading of every recorded run | `OutgoingFireMemory` and `describeOutgoingFire`, both halves of the channel printed beside each other. An instrument: nothing decides on it, and the corpus says there is no threshold to decide on — see the section below |
| the weapons' own dict entries (#267) | parsed on every reading, printed on none — which is why #154's Unverified note asks for exactly this reading and could not get it: `switchOffUndoneByClient` is a latch derived from `isInActiveState` with nothing printing the field it derives from | `describeTopRowModuleDictState`, five entries a module, `-` for absent against `F` and `0` |

Two things about the port are worth keeping in view.

**The drone recall was the worst of them, and not for the reason #11 was.** The
mission runner's bug was a counter measuring the wrong thing; saxrat had no
counter, so Shift+R went out on every reading for as long as the drones stayed
in space — and because every caller took the recall *instead of* its own next
step, a recall the client never answered meant the ship never docked and never
tethered either. That is why `returnDronesToBay` takes the caller's next step
here too: the shape is what makes the give-up expressible at all.

**It can now originate a route, which is the one thing it never could.**
saxrat could always *follow* a route — `jumpToNextSystem` right-clicks the route
panel's first marker and takes the jump entry — but with the anomalies in a
system exhausted and no route set it fell through to `tetherAtStructure` and
parked. `noProbeScanResultsAndNoRouteLastTimeInSpace` exists precisely because
it would otherwise undock straight back into the same dead end. Moving to the
next system was a human's job.

The gap was never the travelling; it was that a solar system name cannot be
spelled in the vocabulary a decision has. So the ask rides the status text, the
same channel #69 opened: `hunt-system` gives the bot a circuit,
`setRouteToNextHuntingGround` writes `@host set-destination <system>` from
`jumpToNextSystem`'s no-route case, and the host — whose directive regex is
bot-agnostic and was already live for saxrat — sets it through ESI.

**Solar systems are the easy ESI case, unlike the stations #17 struggled with.**
`resolve_name` answers them straight out of `/universe/ids/`'s `systems` bucket;
the fallback that enumerates a system's stations exists because that endpoint
does not index every NPC station, and no such problem applies to a system name.

Three things make it bounded rather than another forever-loop. The rotation is
an *index* advanced when the ship is standing in the system it points at, not a
"first name that is not here" rule — that one ping-pongs between the first two
entries and never reaches the third. `routeAskGiveUpReadings` (20) bounds the
asking and **latches**, because a host with no ESI credentials will never
answer. And the counter behind it advances only while the ship is in space with
no route and an empty probe scanner — narrower than the condition the ask
itself fires on, deliberately, so it can never run up while the bot is happily
fighting in a system that still has anomalies. Counting that would be #11's
mistake a third time.

`home-system` is consulted only once the circuit has been walked once. With no
`hunt-system` at all the bot names nowhere and parks exactly as before, so an
existing settings string is unaffected.

**Pod recovery deliberately does *not* use it.** A pod is safe the moment it
docks, and `dockAtRandomStationOrStructure` gets it there immediately; routing a
capsule across systems to reach the staging system trades that for a longer trip
through whatever killed the ship. Docking locally is the safer answer even
though it is the less tidy one.

**Unverified: any of it running.** No route has ever been set from a bot
decision on any bot here — the plumbing is proven, the ask is not. What to watch
on the first run: `Hunt circuit: A -> B -> C, next B` in the status line, then
`@host set-destination 'B'` in the decision log, then the host's own
`# ESI: destination … set` on stderr, then the route panel flipping from `No
Destination` and `jumpToNextSystem` taking over. `Asked for 'B' N/20 readings
ago with no route yet` climbing to `ROUTE SETTING GIVEN UP` is the host not
answering, and its own log says why.

### The lock range is learned here too, and the "no evidence" branch is the common one

The rule is the mission runner's, ported whole: two bounds in `BotMemory`, each
moving one way only, and `lockRangeThresholdInMeters` clamping `targeting-range`
into `[lockProvenAtMeters, lockRefusedAtMeters)`. See "Lock range is learned from
the client, not set" for the argument and the calibration; what follows is only
what saxrat changes about it.

**The row-identity discipline is unchanged and the two apps' copies of it are
compared byte for byte.** `overviewEntryLockHandle` keys on EVE's `itemID`, falls
back to the row's name only where no other row shares it, and yields no evidence
at all from a pocket of same-named rats. That last branch is the *ordinary* case
here rather than the exception the mission runner meets: an anomaly is a pocket
of identically named rats by construction. Loosening it to make the feature fire
more often is the one change that must not be made — a wrong bound is sticky for
the session, where a rule that stays silent costs only the learning.

**The rules are functions of records rather than of a `BotDecisionContext`**,
which is the one deliberate shape difference from the mission runner's copy.
`lockRangeThresholdInMeters`, `describeLockRange` and `updateLockRangeLearning`
take `LockRangeState` and `LockRangeReading`, assembled by two thin callers, so a
case can fold a whole session through the rule in `elm repl`. #106 records what
the other shape costs: a rule reachable only through a whole decision context
"could not be executed ... which is exactly why the shipped version was checked
by reading it".

**One premise of the mission runner's is not true here and is not relied on.**
Its `lockClickLocationFromStepEffects` argues that the lock chord "is the only
place in this bot that presses Ctrl without Shift". saxrat presses Ctrl in three
places: the lock, `ctrlShiftClickUiElement` (which holds Shift too), and the loot
window's Ctrl+W. The third has no mouse effect at all, so there is no
`MouseMoveTo` for the rule to take — both conditions are load-bearing here where
one was there, and a case asks each of the three.

**What the refusal costs more of here.** Only the first lock of an engagement can
ever teach a refusal, because the evidence needs the target bar empty at both
ends — and this bot locks up to `max-target-count` rats and holds them. Nothing
in a reading states the *client's* own maximum; `max-target-count` is the bot's
ceiling, not the client's, so it cannot stand in for one.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_learned_lock_range.py` (31 cases). The rules
are executed through the real `Bot.elm` in `elm repl` and folded over sessions
rather than single readings, and the overview rows they are asked about come from
the real `EveOnline.ParseUserInterface` — which is also the evidence that
saxrat's diverged copy of that parser exposes `objectItemID`, the lock indicators
and the per-row region the identity rule needs. It does; **no parser change was
required**. Confirmed by mutation, thirteen of them, each failing a named case,
listed in that file.

**The recordings settle half of "do the rats carry item ids".** The field
reaches this client: `lootedWreckIds` only grows through
`Maybe.andThen .objectItemID` on an overview row, and saxrat runs 2 and 3 reach
`Wrecks already opened: 4` and `3` — so real ids were resolved off real rows,
tens of thousands of readings' worth. What that does *not* say is whether a
**rat's** row carries one, because a wreck is the only consumer saxrat had. No
recorded run carries a `Lock range:` clause at all, so a rat's row has never been
asked; both relations are pinned as cases rather than remembered.

**Unverified, and only a run can answer it: whether an anomaly's rats carry
`itemID`s**, which decides how much evidence this ever collects. If they do,
attribution is by id and the name rule rarely runs; if they do not, an anomaly of
identical rats teaches nothing at all. Both are correct behaviour and the clause
tells them apart: `Lock range: 66000 m (setting 66000, proven -, refused -,
attempt none)` never moving on a run that fights means no evidence was collected,
which is the expected outcome here and not a fault. What *would* be a fault is a
bound moving on a grid of identically named rats, since that is the rule
attributing something it should have refused.

### Several locks in one step, and the first one still asked alone

Issue #177. `lockTargetFromOverviewEntry` issued one Ctrl+click and handed the
step back, so the next lock waited for the next reading. Measured on
`saxrat_run16.log`: **490 lock commands dispatched, and the median gap between
two of them is 2 readings** — one lock per decision cycle, not a client that was
slow to answer. With the learned ceiling now 6 (#110/#149/#151), filling the bar
is most of the opening of every engagement, and a wingman who locks several rats
in quick succession has six dying from the start where this bot ramps.

**The framework permits it, and that had to be settled before anything else.**
`ContinueSession.effectsOnGameClient` is an unbounded `List`;
`EveOnline.BotFramework` maps the whole of it into **one** `WindowsInputRequest`
with a `WaitMilliseconds 210` interspersed between every pair; and
`botlab_host.py`'s `_windows_input` walks the list item by item, deciding
`force_movement` and the click settle from the *next real tag* rather than from
position, so a click late in a sequence is treated exactly like the first. The
corpus shows a long one already: mission run 38's `send-effects-816` dispatched
a click plus a whole typed station name in one request over 12.9 s. So the
median gap of a reading was a **cost**, not a floor.

**Attribution is what makes it safe, and the answer is that a batched step
teaches the lock-range rule nothing.** #121/#134 built
`lockRangeThresholdInMeters` on evidence keyed to a *specific row*, and a batch
breaks that in both directions at once: the next reading's outcome belongs to no
one click in particular, and the target bar the refusal test reads to prove a
slot was free is the bar the batch itself is filling. So a reading whose previous
step carried more than one lock click moves neither bound and **discharges any
pending attempt**, which is `overviewEntryLockHandle`'s posture applied to the
step rather than to the row.

**That costs nothing, and `lockAttemptCanTeachRange` is why.** PR #151
established that an attempt begun with the bar occupied can never move either
bound — it fails the empty-bar condition rather than the wait — and discharges it
at once. So `lockBatchSize` batches **exactly the locks that could never have
taught anything**: the first lock of an engagement, taken with the bar empty, is
still issued alone, still attributed, and still judged as before. The two rules
are made disjoint by construction rather than by hoping they do not collide.
#150's probe is asked alone for the same reason one level up: it is a
measurement, deliberately one row beyond the ceiling, and an answer arriving
beside five other locks is an answer to none of them.

**A dropped click is silent, so it is counted.** #163 found posted input being
dropped under load here — 53-100 ms per event in the two runs that lost a typed
query against under 18 ms everywhere else — and #75's `Emperor Family Bureau`
arriving as `eueu` is the same mechanism. A burst of clicks is exactly that
shape and a lost lock leaves nothing behind but a bar with fewer targets in it.
`updateLockBatchAccounting` writes down how many clicks went out and reads the
bar back `lockBatchReadingsBeforeVerdict` (4) readings later, against the count
on the reading the step was **decided from** rather than the one that observes
it — some of a batch may already have landed by then. The number asked for is
counted out of the dispatched effects themselves
(`lockClickLocationsFromStepEffects` now returns every point rather than the
first), so what was asked for and what was dispatched cannot disagree.

**It reports and never decides**, and the two confounds are stated rather than
designed around: a rat dying inside the window lowers the bar and reads as a
dropped click, and a lock the ship took by itself raises it and reads as one that
landed. Neither is separable inside one reading, which is why the session totals
are the instrument — `asked N and the bar answered M` trailing all evening is
input being dropped, where one short batch is a rat that died. A case asserts the
accounting names nothing the range rule owns.

**Three clicks a step, and the bound is measured.** A batch is a step with no
reading in it, so its whole length is time the retreat and every other guard
cannot act on. Over all 16 recorded saxrat runs and their **50,043**
`send-effects` steps this bot's longest input step ever dispatched is **4.68 s**,
the median is 1.03 s, and a lock step's own median is **2.56 s** — mostly the
host's eased glide and its click settle. So `lockBatchMaximumClicks = 3` is about
seven seconds and is deliberately the first thing this bot does that runs past
its own recorded longest step; the bound is what keeps "past it" to roughly one
reading's worth. It also caps how many locks one dropped-input episode can take.

**A batch is not re-issued while the bar catches up.** The bar lags the clicks
and `overviewEntriesToLock` filters on the rows' own indicators, so without
`lockBatchIsSettling` the next reading would find the same rows unlocked and
click every one of them again — `moduleButtonClickSettlingSteps`' problem at the
lock site, and here it costs a whole batch. The wait is ended by the accounting's
own verdict, either because the bar caught up or because the bound ran out, so it
cannot outlive the count watching it. Only batches settle; a single lock is left
exactly as it was, repeated clicks and all, because that is the behaviour every
recorded run was flown on.

The batch keeps `Lock more targets.` at the head of its decision line — the
string an operator has been grepping for since before any of this — and names the
rows it clicked, since it is the one decision here that acts on more than one
object. The status line carries `Lock batch: up to 3 clicks a step, asked N and
the bar answered M this session`.

**The mission runner shared the defect and was deliberately untouched here.**
Its `lockTargetFromOverviewEntry` had the identical shape — one Ctrl+click, then
the step is handed back — and `TheMissionRunnerStillLocksOnePerStepTest`
recorded that rather than leaving it as a claim, so a later port had to notice
it was taking on the attribution problem this one solves. It also has the harder
version of it: an anomaly is a pocket of identically named rats, so saxrat's
range rule is usually silent anyway and the mission runner's is not. **That port
has since happened** — see "The mission runner batches too, and the gain had
been counted in the wrong unit" below — so the marker is spent and is replaced
by `TheMissionRunnerTookThisOnWithItsDisciplineTest`, which asserts the batch
arrived *with* the two rules that make it safe.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_batched_lock_clicks.py` (32 cases). The rules
are executed through the real `Bot.elm` in `elm repl` and the overview rows they
are asked about come from the real `EveOnline.ParseUserInterface`: the chord the
bot builds for three rows is read back as three points in order (the round trip
that makes the count trustworthy), the batch size is asked at every clause and at
fixed values either side of its bound, the range rule is folded over batched and
single readings **with the single-click control beside each** so the case is
about batching rather than about the fixture, and the accounting is folded over
whole sessions. The wiring is read out of the source through a reader sliced by
**indentation**, since the bindings under test build record literals and the
`let_binding` shape stops at the opening brace. The corpus is recounted as
relations rather than as the numbers above.

Confirmed by mutation, fifteen of them, each failing a named case: the effects
reader taking only the first click again; **a batched reading teaching the range
rule from an outcome it cannot attribute**, which is the failure this whole
design refuses; a pending attempt carried across a batch rather than discharged;
the first lock of an engagement batched; the probe batched; the click cap raised
past everything this bot has ever dispatched in one step, and lowered so nothing
batches; the free-slot bound dropped; the lockable-row bound dropped; the
settling window removed so a whole batch is re-issued; the batch judged against
the reading that observes it rather than the one it was decided from; the
shortfall never reported; the session totals not accumulating; the accounting
reaching into the range rule; and the batch built from rows the ship cannot
reach.

**Unverified: any of it running, and one thing about the client.** No run has
been flown since. **Whether EVE accepts several Ctrl+clicks inside one input
burst is not established** — the framework and the host will dispatch them, which
is what was checked, but the client's own answer needs a run and this change was
written with saxrat live and input driving forbidden. Both failure directions are
visible rather than silent: clicks the client ignores show up as
`Lock batch came up short`, and the settling window bounds the retry. What to
watch on the first run is `Lock more targets. Asking for 3 locks in this one
step` in the decision log, then `Lock batch: ... asked N and the bar answered N`
with the two numbers tracking each other. Answered trailing asked all run is
either #163's dropped input or a client that takes one lock per burst, and the
tell between them is whether the shortfall is always exactly the batch minus one.

### The mission runner batches too, and the gain had been counted in the wrong unit

The port of the section above into `eve-online-mission-runner`. The design is
not re-derived — a batched reading teaches the lock-range rule nothing and
discharges any pending attempt, that costs nothing because
`lockAttemptCanTeachRange` already discharges an attempt begun with the bar
occupied, the first lock of an engagement stays single and attributed, and the
probe is asked alone. What follows is only what this bot changes about it.

**The finding is a unit, and it is `stall_watch.py`'s own mistake in a third
place.** The first draft of this port measured the ramp in `# [tick.substep]`
integers and concluded the mission runner's gain was much smaller than saxrat's:
a median gap of 5 readings, 76% of lock runs standing alone, "batching applies
to under half of this bot's locks". **A tick is not a reading.** The framework
issues exactly one `RequestToVolatileProcess` per reading, and run 35 alone
carries **6,573 ticks against 8,191 memory reads** — so counting in ticks
reports 38% of consecutive lock commands as landing in the *same* reading, which
the single lock site cannot do.

Recounted in readings, the two bots are the same shape:

| | lock commands | readings | median gap | commands inside a run |
|---|---:|---:|---:|---:|
| mission runner, 39 runs | 2,833 | 83,225 | **2** | **81%** |
| saxrat, 17 runs | 6,802 | 109,086 | **2** | 84% |

So the ramp is the same and what is genuinely smaller here is how *often* this
bot locks at all. `TheUnitIsTheReadingAndNotTheTick` executes the disagreement
rather than remembering it, and a mutation pointing the corpus reader back at
ticks fails a named case. This is the third time the unit has cost a
measurement: `stall_watch.py`'s threshold, #141's retreat recount, and this.

**The cap is re-measured on this bot's own corpus and still lands on 3.** Over
39 recorded mission runs and their **40,903** `send-effects` steps the median
step is 1.02 s, the 99th percentile 4.53 s and a **lock** step's own median
1.30 s — so three clicks is about 3.9 s and stays inside what an ordinary step
already reaches, where on saxrat the same three ran past everything it had ever
dispatched. This bot has precedent for a long step (12.9 s, a typed station name
in one `WindowsInputRequest`), so the bound is not about what the host can carry
but about how long the guards go unasked.

The flattening is argued in the readings a cap removes rather than in a
percentile, because that is the thing the cap costs. Replayed over the corpus, a
cap of three turns those 2,833 lock steps into **1,475**, four into 1,361 and
five into 1,290 — so batching at all removes 1,358 readings, the third click
accounts for 322 of them, and the fourth buys 114 more while the blind interval
grows from 3.9 s to 5.2 s. 631 runs of consecutive locks, 493 (78%) of three or
fewer.

**One cross-bot claim was dropped rather than restated.** The doc comment as
first written put a lock step's median at "half saxrat's 2.56 s". Measured the
same way — the `dispatch=` field on the `send-effects` line, which reproduces
#178's own overall median of 1.03 s exactly — saxrat's lock step median is
**1.271 s** against this bot's 1.304 s. The comparison was an artifact of two
different derivations, so only this bot's own numbers are stated now.

**The one rule this bot needed that saxrat did not, until #253 made saxrat need
it too — see "saxrat filtered where it had to take a prefix, and the comment
saying otherwise had expired" below.** `everythingWorthAttacking` puts a
warp-disrupting entry at the **front, ahead of the distance order** — so a
scrambler out of reach can sit in front of rats that are in reach, and a batch
built by *filtering* would silently skip the one row the bot most wants, lock
the rats behind it, and never approach the scrambler at all.
`lockBatchRowsInReach` counts the in-range **prefix** instead: a head the ship
cannot reach answers 0, which drops the batch to one row and hands the reading
back to `lockTargetFromOverviewEntry`, whose out-of-range branch approaches it
exactly as before. A batch therefore always begins with the row the single lock
would have clicked and never reaches past a row it skipped.

**Its learned ceiling is 6 as well**, so a batch fills the same slots: 11,012
readings carry `Max targets: 6 (setting 4, client stated 6, most held at once
6)` and the corpus holds 345 `You are already managing 6 targets` statements.

**The lock-range rule is read rather than executed here**, which is the one
place the cases are weaker than saxrat's. The mission runner's
`updateLockRangeLearning` takes a whole `UpdateMemoryContext` where saxrat's
takes records — the divergence #106 records the cost of — so the batched-reading
guard is read out of the source, in the shape `test_max_targets_probe` already
uses for this same function in both apps. Everything that is a function of
records is executed.

**Verified without a live client**, in
`tools/macos-host/tests/test_mission_runner_batched_lock_clicks.py` (37 cases).
The wiring is read through a reader sliced by **indentation**, since the
bindings under test build record literals and the `let_binding` shape stops at
the opening brace. The decision-root adjacencies `test_learned_max_targets` and
`test_drone_launch_refusal` pin are undisturbed — `lockBatchLastChange` goes at
the end of that list — and a case says so. The corpus is recounted as relations.

Confirmed by mutation, **eighteen** of them, each failing a named case: the
in-range prefix replaced by a filter, which is the scrambler-skipping failure
this port exists to refuse; the prefix rule counting past a row out of reach;
the effects reader taking only the first click again; the batched-reading guard
dropped from the range rule; the pending attempt carried across a batch rather
than discharged; the first lock of an engagement batched; the probe batched; the
cap raised past this bot's 99th-percentile step and lowered so nothing batches;
the free-slot bound dropped; the settling window removed; the batch judged
against the reading that observes it; the shortfall never reported; the session
totals not accumulating; the accounting reaching into the range rule; the
batch's line no longer opening with the string operators grep for; and — on the
cases' own premises — the corpus reader counting ticks, and the lock decision no
longer scoped to its own step.

**One survived the first pass and the hole was real.** `{ unchanged | attempt =
Nothing }` is what **three** branches of `updateLockRangeLearning` answer — the
row that is gone, the lock the client declined with the bar occupied, and the
batched one — so asserting that string over the whole rule passed with the
batched branch reverted to `unchanged`. That is a pending attempt carried across
a batch and then judged against the bar the batch itself filled, which is the
one thing the guard exists to stop. The branch is *sliced* now rather than
searched — "assert the form, not the substring", which #109's status clause,
#122's trust rule and #145's named-button case each paid for once already.

**Unverified: any of it running**, and the same client question saxrat's port
left open — whether EVE accepts several Ctrl+clicks inside one input burst. Also
unmeasured is what the settling window costs in practice: a batch the bar
answers at once costs no settling reading, and one the client drops runs the
full `lockBatchReadingsBeforeVerdict`, but no run has shown the distribution
between those. What to watch is the same pair as saxrat's — `Lock more targets.
Asking for 3 locks in this one step`, then `Lock batch: ... asked N and the bar
answered N` with the two numbers tracking each other.

### saxrat filtered where it had to take a prefix, and the comment saying otherwise had expired

saxrat's `overviewEntriesToLockInOneStep` was a `List.filter` down to the rows in
lock range. That is safe only while the candidate list is in distance order, so
that the rows in range are a prefix of it and filtering can reorder nothing —
and the comment at the site said exactly that, in those words.

**It stopped being true when #253 landed.** `decideActionInAnomaly` now puts
`|> List.sortBy combatPriorityTier` ahead of the distance order the helper
returns rows in, and `overviewEntriesToLock` derives from that sorted list. So a
warp-disrupting row the ship cannot reach can lead the list, filtering drops it,
and the batch locks the rats behind it — never approaching the one row the tier
exists to put first. That is precisely the failure the mission runner's own
`lockBatchRowsInReach` doc comment describes while asserting saxrat could not
suffer it.

**Nothing failed when the premise expired**, which is the reusable half. Both
comments went on reading correctly — one defending a filter the reordering had
just made unsafe, the other asserting a divergence the reordering had just
closed — and a reordering is not the kind of change anybody re-reads a batch
comment for. Both are corrected here, in both files, and
`TheExpiredJustificationIsCorrectedInBothFiles` refuses the three sentences that
carried the claim, in `Bot.elm` rather than in a PR body.

`lockBatchRowsInReach` is ported whole and the two bodies are compared byte for
byte; the doc comments are deliberately **not**, because each argues from its own
app's history. `overviewEntriesToLockInRange` stays exactly where it was — #150's
probe is a measurement and may only be made with a row the ship can already lock,
so `rowsToSpare` is still a count of everything in range. The prefix is about the
*batch*, which is a different question about the same list.

#### Whether this has happened is not answerable from the corpus, and the reason is structural

Counted per *reading* (`RequestToVolatileProcess`, one per reading) over all 90
logs in `~/eve-bot-logs` — 311,406 readings — because the status line is
reprinted under every decision:

| | saxrat | mission runner |
|---|---:|---:|
| runs | 51 | 39 |
| readings | 227,749 | 83,350 |
| readings carrying `Overview indications:` | **0** | 46,536 |
| readings the lock site chose a row out of lock range on | 13,918 | 866 |
| readings carrying a tier-0 or tier-1 hint | **0** | 1,815 |
| both at once | **0** | **7** |
| both at once, tier 0 (`is warp disrupting me`) | **0** | **0** |

**saxrat has never printed the EWAR hints at all.** `describeOverviewIndicationHints`
is #130's and is mission-runner-only, so the bot that has the defect cannot say
whether it ever met the situation — 227,749 readings of silence, which is an
absent instrument rather than an absent event. The 866-to-13,918 split in the
other row is the same asymmetry from the other side: saxrat meets an out-of-reach
head constantly and can say nothing about what was on it.

**And the 7 are not instances.** That clause reports *distinct strings across
rendered rows*, deduplicated, naming no row and carrying no distance, so a
reading where some row was under EWAR and some row was out of reach does not say
they were the same row. They are a necessary condition, in the app that already
counts the prefix, and all 7 are tier 1. **No reading in the corpus carries a
tier-0 hint beside an out-of-reach head at all.**

**So this change rests on the expired premise and not on observed harm**, and the
two are different reasons. What makes it worth making anyway is that the
reachability is a property of the code rather than a guess — the tier sort is
above the distance order, the filter reads the sorted list, and
`test_a_scrambler_out_of_reach_is_no_longer_skipped` runs both constructions over
the same really-parsed rows and shows the old one skipping the scrambler. The
frequency is unmeasured and stays unmeasured.

#### What the bot does in the new edge case

A head the ship cannot reach makes `lockBatchRowsInReach` answer 0,
`lockBatchSize` answer `max 1 0` = 1, and the batch **one row — never zero**. The
call site's `1 < List.length` guard therefore declines to batch and hands the
reading to `lockTargetFromOverviewEntry`, whose out-of-range branch double-clicks
the row inside `approachRangeLimitMeters` and warps to it beyond. So the reading
is spent closing distance rather than declined.

That is asserted rather than described, because a batch coming back empty where
it used to come back non-empty is PR #257's shape — a step on a hot path that can
decline forever, which blocked the bot for 108 minutes.
`TheShortBatchIsStillAnAnswer` pins the batch never being empty (over the whole
grid of `lockBatchSize` inputs, since `max 1` is what makes it true) and pins the
branch it falls through to acting rather than waiting.

**The cost is stated rather than hidden**: where the head is out of reach and two
or more rows behind it are in reach, saxrat used to dispatch a batch and now
dispatches a single approach. It batches strictly less often, in exactly the
state where batching was locking the wrong rows.

#### Verified without a live client

`tools/macos-host/tests/test_saxrat_lock_batch_prefix.py` (16 cases). The prefix
rule and both batch constructions are executed through the real `Bot.elm` in
`elm repl`, and the rows they are asked about come from the real
`EveOnline.ParseUserInterface` through the real
`overviewEntriesToAttackFromReadingFromGameClient` and the real
`List.sortBy combatPriorityTier` — so the out-of-reach head is at the head
because the tier put it there, on the furthest row on the grid. `inReach` is the
one thing restated rather than reached for, because
`overviewEntryIsWithinLockRange` takes a whole `BotDecisionContext` while
`lockRangeThresholdInMeters` under it takes a record; it is defined once and
handed to **both** constructions, so what separates them is the change and not
two notions of reach. Two controls ride along — a reachable head, where the two
constructions agree, and a grid with no priority row at all — so the case is
about the situation rather than about the fixture.

**Two cases are weaker than the rest and say so.** `oldBatch` and `newBatch` are
written in the case rather than reached through `decideActionInAnomaly`, which
takes a whole `BotDecisionContext` — so the executable comparison shows what the
two constructions *do* and cannot notice the site being reverted to the filter.
What pins the site is the source read beside it, and
`test_saxrat_batched_lock_clicks`' own wiring case reads it too. That is the same
shape #231's `test_the_sort_puts_them_in_that_order` records, and the mutations
below are what establish the division of labour rather than assuming it.

Confirmed by mutation, **eleven** of them, each failing a named case: the binding
reverted to `overviewEntriesToLockInRange |> List.take`, and `rowsLockableNow`
reverted to a count of everything in range while the take stays on the candidate
list — the half-revert, which is the shape that batches past the head, and both
caught by the source read and by nothing else; the prefix rule made to count
rather than stop (`List.filter identity >> List.length`), which fails five cases
including the scrambler one; `lockBatchSize`'s `max 1` dropped, which is the
empty-batch hazard and fails four; the tier sort removed from saxrat, which
falsifies the premise the whole change rests on; the probe's `rowsToSpare`
pointed at the candidate list, which is a measurement made with a row the ship
would have to fly at first; an expired sentence restored in each file; `#253`
dropped from a doc comment, so the reordering that made the rule necessary is
unfindable from the file; the mission runner's copy of the prefix rule drifted
from saxrat's; and the out-of-range branch made to wait rather than approach,
which is the short batch becoming a reading spent on nothing.

#### Unverified

**Any of it running.** No saxrat run has been flown since, and no run of either
bot has ever recorded the situation. What to watch on the first run that meets a
scrambler out of lock range is `Lock more targets.` followed by
`Object is not in range (N m away). Approach.` naming the warp-disrupting row —
rather than `Asking for N locks in this one step` naming the rats behind it. A
run that meets one and still batches means the sort is not reaching the lock
site, which is the direction this fails silently in.

**How often it happens.** Unmeasured, and unmeasurable from saxrat's logs as they
stand. The cheap thing that would make it measurable is #130's
`Overview indications:` clause in saxrat's status line, which is one line and
would turn the next run into the evidence a frequency claim would need. It is
deliberately not in this change.

### saxrat swaps ammo at a distance it is told, not one it works out

Issue #122. The capability was **absent rather than unconfigured**: `ammoSwap`
appeared 165 times in the mission runner and 0 times here, as did `Charge`,
`chargeName` and `optimalRange`, and none of `short-range-ammo`,
`long-range-ammo` or `ammo-swap-range` existed in the settings. There was no
switch to turn on. Nothing structural blocked it either — neither app's
`ParseUserInterface` exposes charges (the count is 0 in both), and the mission
runner's swap is built entirely on tooltip and menu interaction, so this was a
port rather than a new instrument.

**The tooltip half is not here, and requiring `ammo-swap-range` is what makes
that a simplification rather than a loss of function.** The mission runner has
three sources for its crossover distance: the setting, the midpoint of two
optimal ranges read off a weapon's tooltip, and the loaded charge's own optimal
range as a bootstrap. The second and third depend on resting the mouse on a
module until a Photon flyout appears, which is the fragile half — #106 exists
because five unanswered hover readings latched the whole swap off for a session,
and #128 is still open against it. And `weaponTooltipIsWorthAsking`'s own first
clause is `not crossoverIsConfigured`: **with the setting present the hover is
never asked at all.** So making it required makes the whole hover unreachable,
and porting it would have been porting dead code. `ammoSwapConfigFromSettings`
is the one place that says the swap needs all three settings, and it answers
`Err` naming the ones that are absent rather than `Nothing`, because an operator
who set two of the three and got silence cannot otherwise tell a decision from a
typo.

**The stated cost.** The tooltip is the only way a *second* optimal range is ever
observed, so saxrat never refines its crossover and uses the number it is given.
For a bot whose ships and ranges are operator-known that is a reasonable trade,
and it is the trade the mission runner already makes on every run where the
setting is present — its run 34 read `crossover 29000 m (+/-3000, from the
ammo-swap-range setting)` with `tooltip unanswered 0` for the whole run.

**Issue #122's premise about saxrat's warps is measurably wrong, and it does not
change the answer.** The issue argues the in-warp hover window "may barely exist
here", from 7 warp-related source references against 103 anomaly ones. That is a
count of identifiers, not of behaviour. Across the recorded saxrat runs the bot
warps between anomalies constantly: run 2 spent 3,018 of 24,865 readings in warp
across **64** separate warp episodes, run 3 4,548 of 24,030 across **119**, with
median episodes of 42 to 57 readings. The mission runner's own median episode is
45 and its busiest recorded run has 28. So the in-warp dwell #111's fix depends
on is *more* available here, not less — and it is still irrelevant, because the
setting being required is what switches the hover off. Worth recording so a
later change rests on the measurement rather than on the reference count.

**What came across whole is the swap's own safety**, which is where the design
earns its keep and is most of what the cases are about:

- **`ammoSwapLoadIsTrusted` and `loadRefusalFromGameLog` are a pair, and a port
  that keeps one and drops the other compiles.** The trust rule takes a
  `Maybe String` and `Nothing` is a perfectly good value for it, so the failure
  is silent and it is exactly the one the removed menu read existed to prevent:
  the swap starts reporting charges the guns do not have. Run 22 recorded 134
  refusals when every load was going into a running gun; run 26 recorded none
  against 819 satisfied readings. `TheTrustRuleReadsTheRefusalTest` asserts the
  wiring between them, and the matcher's own doc comment carries the argument,
  because somebody editing it is not reading this file.
- **`ammoSwapDisarmDamageBudget` reads its configured setting**, at every call
  site, which is what PR #120 kept deliberately in the mission runner. saxrat
  scales nothing yet, so the constraint is presently free — which is why it is
  asserted, since the port that adds #119's scaling is the one that would sweep
  it up. Note also that the damage-rate retreat has never fired in 36 runs: the
  budget is an *eighth* of its threshold, so 437 declines swaps on windows that
  3500 never sees, and the shield is the fuse rather than this number. Nothing
  in the swap reads a hitpoint gauge, deliberately.
- **`ammoSwapRangeErrorPercent`'s documented weakness carries over unchanged.**
  What decides whether the other charge is better is whether the guns are
  landing, not the geometry; the client says so on its outgoing combat lines and
  neither app reads them here.

**One rule has no counterpart in the mission runner, and it is the only part of
this that is new rather than moved.** saxrat's `clearStrayContextMenu` presses
Escape at a context menu that has sat at the same cascade depth for
`strayContextMenuStuckTicksThreshold` (3) readings, and it is reached from the
head of `decideNextActionWhenInSpace` — above everything. The swap holds a
weapon's context menu open across `ammoSwapSilenceSettleTicks` (also 3) while it
waits for the guns to go quiet, and `menuOpenOnGunAtX` attributes a menu to a gun
only where the right-click was the immediately previous step, which run 26 shows
is usually not the case. So from that branch the swap's own menu looks exactly
like a stray one, and without a guard the two take turns: Escape closes the menu,
the swap re-opens it, and the attempt runs out its bound having loaded nothing.
`strayContextMenuIsStray` is the rule, over a record, and the suppression is
bounded by the swap's own deadlines — `ammoSwapIsActingOnAVerdict` goes false the
moment the verdict is satisfied or abandoned, and both `ammoSwapVerdictGiveUpTicks`
(25) and `ammoSwapSilencedGiveUpTicks` (20) abandon it. The stray-menu guard's
promise, that a menu cannot sit forever, therefore survives. What it costs is
stated: a genuinely stray menu opened while the swap is working a verdict waits
that window out instead of being cleared on the third reading.

**Two other divergences, both consequences of saxrat firing its guns by hotkey.**
`decideActionInAnomaly` presses F1–F4 and reads `.isActive` to decide whether to;
the swap reads `isInActiveState` through `weaponIsSwitchedOn`, because `.isActive`
is `ramp_active`, the duty cycle, and reading it here was the mission runner's
#76 — run 21 was told no gun was firing on 605 of 674 module clauses of a ship
that was. And the swap switches a gun *off* by clicking its button rather than by
pressing its hotkey, because `doEffectsClickModuleButton` is what
`swapJustCommandedAGunOff` reads and it attributes the press to a gun by region,
where a hotkey covers only the first four weapons and names one by list position.
The cost is that the fight's own settling window does not see that click, so it
may re-arm the gun on the next reading — which no bound depends on, and which is
the state `switchOffUndoneByClient` already reports for the mission runner's own
reason (#72: the client does it there anyway, on every swap).

Both readers of the weapon row go through one `weaponModuleButtonsLeftToRight`,
because the swap silences a gun the fight re-arms by its list position and two
sorts would be two opinions about which physical weapon that is.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_ammo_swap.py` (58 cases). The pure rules are
executed through the real `Bot.elm` in `elm repl` rather than restated in Python:
the settings gate over all eight combinations of present and absent, the trust
rule with each of its five inputs falsified on its own, the disarm budget at both
sides of every boundary it has, the range error symmetric about the crossover and
`Nothing` where it cannot be measured, the refusal matcher against a real parsed
reading, and the stray-menu rule at both sides of its threshold and with the swap
holding. The wiring, the placement and the counters' arithmetic are read out of
the source through a whitespace-collapsing reader; `gunsSilencedTicks` is checked
to evaluate to `0`, `1` or `previous + 1` in every branch and to consult nothing
the module says, which is the property #34 was. The tooltip half's absence is
asserted as a *relation* between the two files rather than as a count in one, so
a case cannot pass on a file where the swap itself was deleted. The corpus is
recounted as relations: no recorded saxrat run carries an ammo clause at all, and
the warp figures above.

Confirmed by mutation, **eleven** of them, each failing a named case: removing
the refusal matcher while keeping the trust rule, dropping the refusal from the
trust rule's five inputs, reading the cascade state from this reading instead of
the previous one, making `ammo-swap-range` optional again, the disarm budget
reading a scaled threshold rather than the setting, its worthwhile-percent
comparison moved by one, `gunsSilencedTicks` pinned at a constant,
`weaponIsSwitchedOn` reading `.isActive`, the stray-menu guard reverted to the
bare threshold, one arm of the movement dispatch left on the fight so the swap is
never reached, and the memory update never called at all.

**The first of those survived on the first attempt, and the hole was real.**
`TheTrustRuleReadsTheRefusalTest` asserted `loadRefusedByClient =
loadRefusedByClient` over the whole of `updateAmmoSwapMemoryWithConfig` — and
the record that function *returns* carries a field of exactly that shape, so the
assertion was satisfied by the output record while the trust rule was being
handed `Nothing`. That is this port's worst available failure passing a case
written to catch it. Both the slice and a second case asserting none of the five
inputs is a literal are what catch it now, which is the "mutate the code and
watch a test fail" convention doing the thing it is for.

**It has flown since, and what that settled is in the section below.** The
paragraph that stood here said no recorded saxrat run carried an ammo clause at
all; runs 5 and later do, the stray-menu guard this section names as the thing
most likely to be wrong turns out to be right, and the thing that was wrong is
the give-up beside it.

### The disarm budget bounds an attempt, and it was read as a statement about the guns

Issue #154. saxrat's run 10 switched the whole ammo swap off **21 readings into a
three-hour session** and spent the remaining 3,832 status lines reporting it
`off for this session`. (That run was still being written while this was
measured — the issue counts 2,578 of those lines and 66,744 in the log against
3,832 and 96,834 here — so every claim below is a relation the cases recount from
the corpus rather than one of these numbers.)

```
Ammo swap: given up -- the guns were switched off to load and were still not
back 21 readings later -- a disarmed ship is worse than the wrong charge, so
this will not be attempted again this session.
```

**The guns were not off, and the bot's own status line said so on the same
reading.** Its ammo clause had read

```
(a gun has been switched back on 20 of 20 readings in -- the guns are firing,
and this attempt is going on to its load anyway)
```

for the previous **seventeen consecutive readings**. `GUNS OFF` printed for
readings 1, 2 and 3 of that attempt and never again: the transition is clean and
in the log, `GUNS OFF for 3 of 20` followed on the very next reading by
`a gun has been switched back on 4 of 20 readings in`. **The ship was disarmed
for three readings and the sentence claimed twenty-one**, and on that sentence
the harshest outcome this feature has — the per-session latch — fired.

**The issue's own diagnosis is not what the log says either, and it matters that
it is not.** #154 reads the episode as menu *latency*: the swap waiting for a
weapon's context menu to render, the budget spent on the wait, and the menu
arriving on the very next reading. The waiting is real, but the menu was **open
throughout** — `Context menus open: 1 (cascade level 1)` — and did not offer the
charge: `Could not find menu entry with text containing 'Multifrequency M'` on
every reading of the wait. The two readings the issue quotes as "no context menu
in this reading yet" are the last two, after the cascade's own lookback discarded
the stale menu at reading 19. So the readings were not spent on a menu that was
slow to come; they were spent on a menu that was there and said nothing the swap
could use, while the guns fired the whole time.

**`gunsSilencedTicks` is right, and that is exactly why it cannot be read as a
statement about the guns.** #34's correction made it consult nothing the module
says, because a counter that reads the duty cycle can be stalled by it. What that
buys is a bound nothing can stop. What it does not buy is an account of the ship's
state, and the give-up was written as though it did.

**The distinction already existed one function away.** `describeAmmoSwapState`
stops printing `GUNS OFF` the moment `switchOffUndoneByClient` latches, and its
own comment says why — *"saying `GUNS OFF` here would be a lie"*. The status line
had it right and the verdict did not. #72 established the underlying fact on the
mission runner: **the client re-arms the gun by itself on every swap**, which is
why that field exists and why it is a report rather than a verdict.

**So the session consequence asks the client's own answer and the attempt bound
is untouched.** `ammoSwapDisarmEndsTheSession` is the rule: the budget expired
**and** the client never reported a gun back on. The budget still ends the attempt
at exactly the reading it always did — nothing is loosened, nothing holds the
fight one reading longer — and only what that costs afterwards changes. That is
PR #151's shape on `lockAttempt`, an outcome discharged on the rule's own terms
rather than a bound retuned.

**Reading `switchOffUndoneByClient` here cannot stall anything**, which is what
keeps #34 intact. It is a *latch*, monotone within an attempt and cleared exactly
where `gunsSilencedTicks` is cleared, so unlike a live module read it cannot
flicker between cycles; and it is only ever consulted to make the outcome milder.

**And a single failure no longer ends a three-hour session.** The disarm verdict
is retried after a warp. The two verdicts end differently on purpose:
`ShipCarriesNeitherCharge` is a fact about the ship's hold that nothing short of
docking alters, so retrying it buys a menu cascade per pocket and the same answer
each time — it still latches for the session. Three boundaries were weighed:

- **A new target** is not a boundary. Rats die and are replaced every few
  readings, so unlatching there is the same as having no latch at all.
- **A new anomaly** is the tightest reading of "a fresh fight" and the one this
  bot cannot always answer: the identity comes from
  `getCurrentAnomalyIDAsSeenInProbeScanner`, which is `Nothing` whenever the
  scanner holds nothing on grid, and `visitedAnomalies` already discards those
  readings. A boundary some readings cannot answer never arrives.
- **A warp** needs no read this bot does not already take — it is the same
  `weJustFinishedWarping` the anomaly bookkeeping uses, one definition — and it is
  a superset of the anomaly boundary, since every pocket is reached by a warp.
  Run 10's own counts say the two are nearly the same in practice, about ten warp
  episodes against eight anomalies visited, and only one of them is always
  readable.

**The cost is stated rather than hidden**: a swap failing for a persistent reason
now retries once per warp rather than once per session. That is tens of attempts
over a long session instead of one — bounded, and named on every reading, where
the present behaviour is one line at tick 21 and silence for hours. The status
line says which of the two it is (`off until the next warp` against `off for this
session`), because run 10's operator read `off for this session` 3,832 times about
a verdict a warp would have cleared.

**`givenUp` is a case rather than a sentence now**, and that is the shape change
under both halves. A `Maybe String` is what let the verdict go on claiming
something the memory beside it already contradicted: a string can be printed and
cannot be asked. `describeAmmoSwapGiveUp` derives the wording from the case, so
the two cannot drift, and the disarm sentence now says how many readings the
*attempt* ran rather than how many the ship spent disarmed — on run 10 those were
21 and 3.

**How often this shape occurs.** Across saxrat runs 6 to 10: run 7 never swapped;
run 8 reached `GUNS OFF` 181 times, had the client re-arm the guns 51 times, and
never gave up at all — the control above; runs 6, 9 and 10 each latched the swap
off once. **Two of those three are the misreading** — run 9 held `GUNS OFF` to 6
and run 10 to 3 before the client took the guns back — and **run 6 is genuine**,
with the count running 1 to 20 and not one switched-back-on clause anywhere in
the run. So the latch keeps a case it is right about, which is why this narrows
it rather than removing it.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_ammo_swap.py` (78 cases, up from 58). The two
new rules are executed through the real `Bot.elm` in `elm repl` — the latch at
both sides of its bound *and* against fixed values either side, with the guns
back and not back at each; the unlatch folded over a whole session of readings
rather than asked once; and both sentences rendered. The corpus is recounted as
*relations* rather than as the numbers above and the runs are globbed rather than
numbered, so a run 11 is read without an edit: a run gave up having recorded the
client re-arming the guns and never reaching half the budget in `GUNS OFF`, a run
gave up with the guns demonstrably still off all the way to the budget, and every
run that gave up warped many times more often than it gave up.

Confirmed by mutation, **thirteen** of them, each failing a named case: the
`switchOffUndoneByClient` clause dropped, so an attempt spent entirely on a firing
ship latches the session off (run 10 restored); the disarm verdict made to survive
a warp; the neither-charge verdict made to be retried every pocket; a verdict
reached *on* the warp reading cleared by it; the bound's comparison moved by one;
the abandonment conditioned on the same clause, so the attempt is held longer; the
session verdict comparing the bound itself instead of asking the rule; the call
site handing the rule `gunsConfirmedOff`, which is the same type and the opposite
question; the status line no longer saying which give-up it is; the memory update
never seeing a warp; the latch re-derived each reading instead of persisting; the
sentence dropping the count; and the sentence claiming the guns were still off.

**One case was passing vacuously and the extractor was why.** `let_binding` ends
at the next ` <name> = `, which a *record literal* inside the binding satisfies —
so the assertion that the rule is handed `switchOffUndoneByClient` was reading
text that stopped at the record's opening brace. `indented_let_binding` slices by
indentation instead, which is the same correction #147 made to its own reader.

**The swap does complete on this bot, and run 8 is the control this change is
measured against.** That run reached `GUNS OFF` 181 times, had the client re-arm
the guns 51 times, printed `(satisfied)` **2,712** times, tracked
`loaded charge reads` through `unknown`, `short-range` and `long-range`, and
**never gave up at all**. So the feature works when the sequence finishes, which
is what makes ending it on one bad reading expensive rather than academic. Run 8
also carries **422** `cannot load or unload` refusals, so a good share of its
loads were still going into running guns — #76's territory, untouched here.

**Unverified: any of it running, and why run 10's swap could not finish.** No run
has been flown since. Run 10 printed `(satisfied)` zero times and its
`loaded charge reads` never left `unknown` across all 150 of its ammo clauses,
with the weapon menu open and not offering the wanted charge on every reading of
the wait. Whether that is the gun *already carrying* `Multifrequency M` — in which
case the menu is correct and the verdict was asking for a load it did not need —
or the menu being attributed to the wrong module, is **not established**, and
nothing here claims that attempt would have succeeded. It is the next thing to
look at. What to watch on the first run: the give-up, when it comes, saying `off until
the next warp` and then *going away* on the next warp with a fresh `wants
short-range for N reading(s)` after it — that retry is the whole of the second
half and it has never happened. A run whose give-up still says `off for this
session` on a disarm verdict means the case is not being carried; a run that
latches and never comes back across many warps means `weJustFinishedWarping` is
not reaching the swap.

**One rule is deliberately not identical, and it is the first reading.**
`updateHitpointsGaugeMemory` believes a reading that has no previous reading to
confirm against — the session's first, or the one after a gap — where the
mission runner's `Maybe.map2 max` answers `Nothing` and withholds it. Both are
pinned by their own suites (`test_hitpoint_reading_confirmation.py` asserts
`(memoryAfter 70 [ Just 0 ]).believed == Nothing`;
`test_saxrat_ported_guards.py` asserts a lone `Just 75` is believed), so this is
a divergence with two specs behind it rather than a drift. What it costs is
narrow but real: a reading following one that `plausibleHitpointsPercent`
rejected is acted on unconfirmed. What the mission runner's version costs
instead is that a gauge readable only every other reading is never believed at
all. **Neither has been run against a live client**, and the recorded
corruptions are all *plausible* values, which both versions treat identically —
so nothing in the corpus separates them.

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
followed to the wrong station with every log line reading like success. Each
mechanism brings its own evidence and either will do.

The search bar's evidence is the `Station: Information` window for the home
station — the window `routeToStationByName` clicks "Set Destination" in, which
nothing afterwards closes. Route panel plus that window is a conjunction only our
own sequence produces. If a future client closes that window on Set Destination
the symptom is the search repeating rather than travel starting, which the
decision log names.

ESI leaves no window behind, so its evidence is that **nothing was clicked**.
Setting a destination in the client takes a click — a search result's "Set
Destination", the tracker's own travel button, a route marker's menu — and the
`@host set-destination` ask takes none: it is a line of status text and a wait.
So a route that appears across a step which dispatched no input at all was set
from outside the client, and the host is the only thing here that can do that.
`BotMemory.routeAppearedWithoutInput` latches that while the route stands and
clears the moment the panel is empty, so it can never outlive the route it
describes. It records that *a* route came from the host and not which one, which
is why `travelToStationByName` re-asserts the destination on every travelling
reading: the host acts only on a change, so the cost is a string comparison and
the client is always holding the station the bot currently wants.

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

ESI needs none of this — no typable substring, no row matching, no window kept
open as evidence — and since #69 the bot reaches it, through the status-text
directive rather than through the volatile-process request a decision still
cannot issue. That seam was narrow on purpose: the travel path asks route-setting
exactly two questions, `homeStationRouteIsSet` and `routeToStation`, and knows
nothing else about where a destination comes from, so adding the second mechanism
touched those two functions and nothing downstream of them. The search bar
remains as the fallback, unchanged, and is what runs with `route-by-esi=no`, on a
host that does not read the directive, or after an ask goes unanswered.

The travel half of it is now shared. `travelToStationByName` is the route-set,
fly, dock sequence, and both the restock trip and the pod recovery below call
it — the callers differ only in the two log lines they hand it, because the
*reason* is what an operator reads and the mechanism is not something this bot
should have two of.

## A station with no agent in it is a place to leave, not a reason to stop

Run 35 printed `I do not see an agent to talk to in this station` on **371
readings**, each with `I am stuck here and need help to continue` under it, and
on every one of them the status line read `Home station: 'Amarr VIII (Oris) -
Emperor Family Academy' (... docked elsewhere)`. The bot knew a station with an
agent in it, knew it was not standing in that station, and asked a person to
come and fix it.

**The docking was correct, and that is the finding, because the issue assumed
the opposite.** #127 named "why the bot was docked there at all" as the likely
real defect. It is not. Run 35's mission was the courier `The Heir's Favorite
Slave -- Bring Slaves to Ashokon Bofazan`; the mission tracker's own travel
steps flew the ship to Bofazan's station, the tracker offered `Dock` and then
`Start Conversation`, and the mission was handed in there. A courier mission
ends at somebody else's agent, by design. What follows the hand-in is the gap:
the bot asks whatever station it is standing in for the next mission, and when
the Agents panel yields nobody it has nothing else to try.

**The stall's size was overstated by an order of magnitude, in the unit this
file keeps a section on.** The issue's "roughly 12,800 readings" is the *line*
count of the span. It is **1,064 readings across 304 framework steps and 383
seconds** — six and a half minutes. `[N.M]` is a step spanning several readings,
and counting in steps or in lines instead of readings is how a six-minute stall
was written up as an all-session one.

**The trip is bounded by the wind-down and nothing else.**
`travelToAnAgentWhenThisStationHasNone` fires only from the "no mission running"
caller, only on a reading whose Agents tab is *selected* and holds no usable
row, and only when `agentStationTrip` — a pure rule over a record — says there is
somewhere to go and time to get there. It drops the station the info panel says
the ship is already in, so `lastDockedStationNameFromInfoPanel` naming the
current station falls through to `home-station` rather than routing the ship to
its own hangar; it refuses outright when the panel cannot name the station,
which is `goToHomeStationWhileDocked`'s rule for its reason. The clock bound is
`secondsBeforeSessionEndToWindDown + strandedAgentTripSeconds`: the trip has to
fit *before* the wind-down starts, since the wind-down sits above this branch
and takes the tree back at that point.

600 seconds is three times the longer of the two trips of this shape in the
corpus — run 35's own six gate jumps from Penirgman to Bhizheba, 120 steps and
190 seconds, and run 30's abandonment trip to Amarr VI (Zorast), 15 steps and
106 seconds. It is generous because the asymmetry runs the other way from most
bounds here: overshooting hands the ship to the wind-down, which docks it or
ends the session where it is, while refusing a trip that would have fitted costs
every mission the rest of the session could have run.

**Only the two steps before the undock are new.** Run 35 flew the rest of this
trip already: a person undocked the ship mid-stall, and the bot — no mission, a
route standing — took `decideActionInMissionPocket`'s `travelTheRoute` branch,
flew six jumps and docked at Bhizheba unaided. Setting the route and undocking
are what #127 added; the flight and the dock at the far end were already
exercised.

**Asking for help is still the answer with nowhere to go**, and the log now says
which "nowhere" it was. `describeNoAgentToTalkTo` carries what the tab held,
because the bare sentence could not tell an empty panel — a station with no
agents, or a parse that missed — from a populated one every row of which
`selectedAgentEntry` rejected for not being `isAvailable` or for having an
`agentLocation` somewhere else. Both kinds of row really occur: runs 18 and 19
list `Fisten Akulf, Security, here, not available` alongside an agent the bot
could use. Which of them run 35 hit is still unknown and this change does not
claim to have found out — see "Open gaps".

**What ended run 35's stall was a person.** For the 284 readings before it the
bot dispatched no input at all, the help branch clicking nothing; then an agent
conversation appeared in a single reading with `Seek and Destroy` in it, and the
framework's next dispatch carried `standing down: someone used the mouse/keyboard
1.5s ago`. The stand-down note is only written on a step that had effects to
send, which is why a person at the keyboard is invisible for the whole of a stall
and shows up on the reading after it breaks.

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

### The same bound, asked where a held tree could not starve it

Issue #126 is #102 a second time, in the same file, on the bound PR #115's own
report named as the next one worth fixing. `shipLoss.readingsSince` is advanced
in `updateMemoryForNewReadingFromGame`, unconditionally and with no reference to
what the bot managed to do with the reading; the comparison sat inside
`recoverPodAfterShipLoss`, which is in the pre-split list but *below*
`generalSetupInUserInterface`. Anything answering up there starved the bound
while the number it is compared against went on climbing.

**Run 30 starved it and it cost nothing by luck.** The undismissable window held
the setup entry for 32,585 readings, three hours and forty-four minutes, and
`recoverPodAfterShipLoss` is the very next entry in a list resolved by
`List.head` — so it was not consulted once. What saved it is that no ship-loss
verdict was ever latched: the ship-loss status clause printed on 39,843 lines of
that run and every one of them reads `ship ok`, so the counter was not running
and the bound had nothing to be late for. A ship lost during that same standoff
would have reproduced run 30 with the pod recovery as the victim, and the bot
sitting in a capsule in the pocket that killed the ship.

**Which kind of give-up it is, is the question #115's rule asks, and the answer
is the first kind.** *A give-up that ends the session bounds elapsed time and
belongs where nothing can decline to ask it; a give-up that declines an action
bounds effort and belongs where the action is.* This one is a `describeBranch`
around `FinishSession` and nothing else — no click, no travel, no dock, no menu
— so it hoists. `podRecoveryOutOfTime` is the comparison, extracted as a pure
rule over a record, and `endSessionOnAnExpiredBound` asks it from the head of
`missionBotDecisionRootBeforeApplyingSettings` alongside the abandonment's.
`recoverPodAfterShipLoss` lost that branch entirely, so there is one comparison
rather than two places that could disagree.

**What does *not* hoist is the recovery, and that is the half worth stating.**
Flying a pod to a station is an errand: it sets a route, travels and docks, and
it needs the location info panel expanded and stray menus cleared, which is
exactly why the branch sits below `generalSetupInUserInterface` and still does.
Nor does the *docked* outcome hoist, though it also ends the session — it names
the station out of `dockedStationNameFromInfoPanel`, and that read needs
`ensureInfoPanelLocationInfoIsExpanded` to have run. Having state to reach is
precisely the property the hoisted entry must lack.

**So the ship UI is a condition on the rule**, not decoration. A deadline asked
without it would end a docked session printing "has not got there" about a pod
that had. `shipUI` is a parse of the reading rather than a state the tree has to
reach, so requiring it costs the bound nothing it needs, and what is left
uncovered — a pod that is docked and safe while something above holds the tree —
is the state the bound exists to produce.

**The pod is asked before the abandonment** where both are expired on the same
reading. A capsule is what an operator has to go and deal with; a mission still
accepted can wait for them, and every other ordering in this file already says a
lost ship outranks a stuck mission.

**The counter still counts readings and not attempts, and the stakes make that
argument stronger here, not weaker.** An attempt counter means a bot held
elsewhere spends none of the budget, which is precisely the runaway — and here
the runaway is a capsule sitting still where the ship died, where the abandonment's
was a mission going unquit. The cost is stated rather than hidden: a bot starved
above this branch for an unrelated reason now ends its session at 150 readings
with the recovery never attempted, where before it ran until something else
stopped it. That is the better half of the trade, because the pod was not being
flown anywhere on any of those readings either; what changes is whether a person
is told within twenty minutes or after the session runs out. The give-up line
says so — *readings since the ship was lost rather than attempts* — and names the
`home-station` the pod was routed to, or says there was none and it was taking
whatever the surroundings menu offered.

**The four other bounds were re-read and all four still fail safe**, after #109
and #115 moved things. None is changed, and three of them turn out to be safer
than #115 recorded:

- **`messageBoxStandoffGiveUpReadings`** — unchanged in kind. Over-counting makes
  it give up sooner, and giving up is `closeMessageBox` answering `Nothing` so
  the rest of the tree runs. Safe direction, and it is the mechanism #109 built.
- **`dockingRunInPatienceReadings`** is not actually in this family any more:
  the comparison lives inside `dockingRunInAfterReading`, which the memory update
  calls, so the counter and the test are the same code on the same reading and
  nothing can starve it. What sits under the split only reads the latch, and
  losing it early costs one re-commanded dock.
- **`lootWindowOutOfRangeTicks` / `lootAllRefusedTicks`** — the *effect* of both
  bounds is applied in the memory update too: `unlootableWreckIds` is written
  there on the reading the bound is reached, so the write-off cannot be starved.
  `giveUpOnOpenContainerReason`, down under the split, only supplies the log
  line. Over-counting costs one abandoned wreck.

**Verified without a live client**, in
`tools/macos-host/tests/test_pod_recovery_deadline_reachable.py` (31 cases). The
two pure rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python — the deadline at both sides of its boundary, at zero, at run
30's own 10,811, against a verdict whose reason is empty so nothing conjoined
onto the comparison can hide, and against a docked pod at the bound and far past
it; and the give-up line, which has to name the station or say there was none,
carry the count, say the count is readings and not attempts, and say the pod
still needs a person. A control row rides along so a repl answering `True` to
everything cannot pass. The placement, the ordering against the abandonment, the
absence of a second comparison, the branch doing nothing but ending the session,
the rule reaching for nothing the setup list produces, and the counter's own
unconditional advance are read out of the source through a whitespace-collapsing
reader — as are the three fail-safe claims above. Run 30 is recounted as
relations: the box held the tree for more than fifty times this bound, the
memory update printed on more readings than the box did, and the run never lost
its ship.

Confirmed by mutation, twelve of them, each failing a named case: the comparison
as `<` instead of `<=`; the comparison one reading early; the ship-UI condition
dropped so a docked pod expires; the verdict's reason conjoined onto the
deadline; the pod deadline dropped from the expired-bounds entry; the abandonment
asked before it; the expired-deadline branch waiting instead of ending the
session; the give-up dropping the station's name; the give-up dropping the
readings-not-attempts clause; the clock advanced only on readings the client said
something (the attempt-counting shape); **the comparison put back inside
`recoverPodAfterShipLoss` where it is today**; and the message box's give-up made
to act rather than hand the tree back, which is the fail-safe claim above.

**Unverified: any of it running.** No run has been flown since, and no run has
ever latched a ship-loss verdict at all — the whole path needs a ship destroyed
while the bot is watching, which is not something to stage. **The new failure
mode has never been seen either**: a session that ends at exactly 150 readings
with the pod never flown anywhere is now possible where it was not before. What
to watch on the first real loss is the status line's `SHIP LOST:` with
`N of 150 readings spent` climbing, then `Pod recovery: travelling to …` and a
dock. A session ending at N=150 having printed no `Pod recovery:` line at all is
something above this branch holding the tree, which is what the give-up line now
tells the operator to go and look for.

**saxrat carried the same defect and is fixed in #133** — see "The same bound in
saxrat, hoisted above the same starvation" below. It was left alone here
deliberately, because #126 is about the mission runner and moving a bound in a
second bot is a second behaviour change.

### The same bound in saxrat, hoisted above the same starvation

Issue #133 is the section above, in `eve-online-saxrat`, and the argument that
decides the shape is #132's rather than a new one: the expired branch is a
`describeBranch` around `FinishSession` and nothing else, so it hoists; the
recovery is an errand and does not; the counter stays a reading counter, because
an attempt counter spends none of its budget in exactly the runaway the bound
exists for. What had to be checked against saxrat's own source rather than
assumed is everything else, and two of those came back different.

**saxrat's decision root had no always-evaluated head to hoist into.** The
mission runner's `missionBotDecisionRootBeforeApplyingSettings` is a list
resolved by `List.head` and `endSessionOnAnExpiredBound` was already its first
entry. `anomalyBotDecisionRootBeforeApplyingSettings` is a chain of
`Maybe.withDefault` beginning at `generalSetupInUserInterface`, so the head is
new here: `endSessionOnAnExpiredBound` sits above the setup list, above the pod
recovery, above the docked-or-in-space split. It holds one bound rather than two
— there is no mission to abandon in this bot — so it is a `Maybe.map` rather
than a filtered list.

**The docked outcome can be hoisted here, and is deliberately not.** #132's
stated reason for the `shipUIIsShowing` condition does not hold in saxrat: the
mission runner names the station through `dockedStationNameFromInfoPanel`, a
live parse needing `ensureInfoPanelLocationInfoIsExpanded` to have run, while
saxrat reads `context.memory.lastDockedStationNameFromInfoPanel` — memory, which
every reading can answer. So nothing about the reading stops that outcome
hoisting. It stays where it is because it is *success* rather than a bound, and
hoisting it would change when an ordinary session ends as well as a starved one,
which is a behaviour change this issue has no evidence for.

**The condition is needed anyway, for the other half of #132's argument.** With
the docked outcome left below the setup list, a starved-but-docked session
reaches only the hoisted rule — and without the ship UI that rule would end the
session saying the pod never got there, which is false on the reading it would be
printed. `shipUI` is a parse of the reading rather than a state the tree has to
reach, so requiring it costs the bound nothing, and it is the very test
`recoverPodAfterShipLoss` already uses to mean "docked". What is left uncovered
is a pod that is docked and safe while something above holds the tree, which is
the state the bound exists to produce.

**Why it mattered more here than there when this landed.** The mission runner
answered #101 with `MessageBoxStandoff` — the ladder that makes
`closeMessageBox` eventually hand the tree back — and none of it had been
ported, so the starvation that held that bot's tree for three hours and
forty-four minutes was not only possible here but unguarded, in a bot that rats
unattended. #138 ported it (see "The message box that will not close is bounded
here too"), so this hoist and that ladder now cover the same starvation from
both ends. **Neither makes the other redundant**, and the hoist is the one that
generalises: the ladder bounds one known way the setup list can repeat forever,
while the hoist means this bound is asked whatever holds the list.

**The give-up line says what an operator can act on**, which for this bot is not
a `home-station` — there is no such setting, and pod recovery deliberately does
not use the `hunt-system` circuit either (see the section above for why). It
names the station `dockAtRandomStationOrStructure` was preferring, or says there
was none docked at this session, and it carries #102's clause: `That count is
readings since the ship was lost rather than attempts, so if the decision log
shows no 'Pod recovery:' line, something above this branch was holding the whole
tree.`

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_pod_recovery_deadline_reachable.py` (31
cases). The two pure rules are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python: the deadline at both sides of its boundary, at
zero, at the mission runner's own run 30 count, against a verdict whose reason is
empty so nothing conjoined onto the comparison can hide, and against a docked pod
at the bound and far past it; and the give-up line, which has to name the station
or say there was none, carry the count, say the count is readings and not
attempts, and say the pod still needs a person. A control row rides along so a
repl answering `True` to everything cannot pass. The placement, the absence of a
second comparison, the branch doing nothing but ending the session, the rule
reaching for nothing the setup list produces, the counter's unconditional
advance, the docked outcome's memory read (against the mission runner's live
parse, so the divergence is read out of both sources) and the message-box
standoff's relation to this bound are read out of the source through a
whitespace-collapsing reader. The three
recorded saxrat runs are asked what they can say, which is that they are silent:
plenty of status lines, no `SHIP LOST:` and no message box at all.

Confirmed by mutation, fourteen of them, each failing a named case: the
comparison as `<` instead of `<=`; the comparison one reading early; the ship-UI
condition dropped so a docked pod expires; the ship-UI condition inverted; the
verdict's reason conjoined onto the deadline; the deadline dropped from the head
of the decision root; **the deadline asked below `generalSetupInUserInterface`,
where it starves**; the expired branch waiting instead of ending the session; the
give-up dropping the station's name; the give-up dropping the
readings-not-attempts clause; the clock advanced only on readings the branch
could act (the attempt-counting shape); **the comparison put back inside
`recoverPodAfterShipLoss` where it was**; the status line dropping the count
against the bound; and the docked outcome re-parsing the info panel instead of
reading memory, which is the divergence above going stale.

**Unverified: any of it running, and rather more than in the mission runner.** No
saxrat run has ever latched a ship-loss verdict — that machinery has never run
here at all, let alone its bound — and no recorded saxrat run has ever met a
message box, so the starvation this guards against is reasoned from saxrat's
source and from the mission runner's run 30 rather than from anything saxrat has
been watched doing. The new failure mode has never been seen either: a session
that ends at exactly 150 readings with the pod never flown anywhere is now
possible where it was not before. What to watch on the first real loss is
`SHIP LOST: … (N readings since, giving up at 150)` climbing with
`Pod recovery: docking at …` in between; a session that ends at N=150 having
printed no `Pod recovery:` line is something above this branch holding the tree,
which is what the give-up line now says to go and look for.

### The message box that will not close is bounded here too

Issue #138 is the mission runner's #101 in `eve-online-saxrat`, and the design
is PR #109's ported whole rather than re-derived: the ordinary declining answer
for `messageBoxAnswersBeforeEscape` (60) readings, then **Escape** at the same
box for another 60, then `closeMessageBox` answers `Nothing` and the rest of the
tree runs with the box still on the screen. See "A message box the answer does
not close is bounded" above for the argument; what follows is only what saxrat
changes about it, and what had to be established here rather than assumed.

**Why it is worse in this bot.** `closeMessageBox` here clicked its dismissal
every reading for as long as a box was showing and counted nothing at all --
neither bound existed. saxrat's `generalSetupInUserInterface` is evaluated in
the same place as the mission runner's, above the docked-or-in-space split, and
`parseMessageBoxesFromUITreeRoot` in saxrat's vendored parser matches
`pythonObjectTypeName == "MessageBox"` and nothing else, exactly as the other
copy does -- a case compares the two declarations. So the same window produces
the same standoff, and this bot rats **unattended**, with nobody at the console
to notice 32,585 identical lines. #133 hoisted the pod recovery's deadline above
the starvation for this reason; that protects one bound and nothing else in the
tree.

**The bound's size rests on the mission runner's corpus, and saxrat's own says
nothing.** `saxrat_run1.log`, `saxrat_run2.log` and `saxrat_run3.log` hold
**49,235 readings and not one message box** -- no `Dismiss it using`, no `I see
a message box to close`, nothing on any channel. So there is no distribution
here to place a threshold in, and inventing a saxrat-specific number would be
inventing it. What transfers is a measurement about *the client* rather than
about that bot: the same widget, the same parser filter, the same three
dismissal options in the same order. Against the mission runner's corpus, the
recovered runs' stretches are 6, 10, 11, 18, 20 and 44 readings and nothing
else, while run 30's one box ran to 32,585, so 60 sits in a gap rather than
cutting a distribution. Both halves are checked:
`TheRecordedSaxratRunsCannotSizeThisBoundTest` asserts the silence with a
positive control beside it, and `TheMissionRunnersCorpusIsWhatSizesThisBoundTest`
recounts the separation. The two apps' constants are compared, so a retune of
one that leaves the other behind is caught.

**The parser already exposed what the identity needs, and no parser change was
required.** The identity is the box's display texts plus its buttons' `_name`s
and labels, deliberately not its display region -- and saxrat's diverged
`ParseUserInterface` copy carries `MessageBox.buttons` as
`{ uiNode, mainText }`, with `getNameFromDictEntries` and
`getAllContainedDisplayTexts` both present and the module exposing everything.
The identity cases build UI trees and run them through that **real** parser
rather than hand-rolling a `MessageBox`, so what they assert is what the bot
would have been handed: two dialogs whose labels are identical and whose
`_name`s differ read as different boxes, and the same box drawn at a different
origin reads as the same box.

**Escape is safe here for the mission runner's reason, and the reason is a
placement.** A naked Escape can open the client's own Settings/pause menu --
`closeSystemSettingsMenu` records that happening live *in this file*, from
exactly this key. What covers it is that `closeSystemSettingsMenu` is the entry
**before** `closeMessageBox` in `generalSetupInUserInterface`, and that list
answers with `List.head` after a `filterMap`, so a pause menu opened on one
reading is closed on the next by the branch that exists for it. saxrat's
ordering was read rather than inherited, and all three halves are pinned: the
order, the head-resolution that makes "before" mean anything, and that the
earlier branch really is the one that closes that menu.

**What is deliberately unchanged.** The declining answer is still the default
rung and `closeMessageBoxByDeclining` still contains no affirmative at all; the
parser is not narrowed, because narrowing treats the instance and leaves the
shape; and the give-up hands the tree back rather than raising
`askForHelpToGetUnstuck`, which is the entire point -- an alarm leaves every
starved branch exactly as starved. The status line carries
`Message box: N/120` with `(pressing Escape at it)` and
`(GIVEN UP ON, still open)`, which is the only thing on a reading that says a
box is still there once the decision line has gone, and the give-up names the
box and both rungs once at the root through `lockRangeLastChange`'s mechanism.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_message_box_standoff.py` (56 cases, up from
46). The four pure rules are executed through the real `Bot.elm` in `elm repl`
rather than restated in Python -- the standoff folded over a whole session of
readings as well as asked at single numbers, the ladder at both boundaries and
either side of each, the identity over boxes the real parser produced, and the
give-up line -- and the wiring, the placement, the ordering and the parser's
deliberate unchangedness are read out of the source through a
whitespace-collapsing reader.

Confirmed by mutation, **fifteen** of them, each failing a named case: the
escalation cut to 44 so it slices the recorded distribution; either boundary
comparison moved by one; the give-up written as a bare `120` instead of a
multiple; the give-up raising `askForHelpToGetUnstuck` instead of handing the
tree back; the escalation clicking the box instead of pressing Escape; the
identity dropping the box's text or its buttons; the count not resetting on a
different box; the count surviving a reading with no box at all;
`closeSystemSettingsMenu` reordered after `closeMessageBox`, which uncovers the
pause-menu risk; the status clause neutralised; the branch not consulting the
verdict at all; the give-up line dropping the box's name; the doc comment in
`endSessionOnAnExpiredBound` left saying the standoff is absent; and saxrat's
constant retuned away from the mission runner's.

**One mutation survived the first run and the hole was real** -- the same one
#109 found on the other bot. The status clause was asserted by substring, so a
version that still named `context.memory.messageBoxStandoff` while answering
`Nothing` for every standoff printed nothing and passed. The case now reads the
clause's *form*: a `case` directly on the memory field, the verdict consulted,
and both numbers printed.

**It has met one since, and the run refutes the issue filed on it.** See "The
ladder is not what froze; the readings stopped coming back" below.

### The ladder is not what froze; the readings stopped coming back

saxrat run 11 met the first message box either bot has met since #138 shipped,
and issue #164 reads it as the ladder's third rung being unreachable: the
standoff counter climbs to 60, escalates to Escape, and holds at 60 for **2,439
readings** while `pressing Escape at it` fires 2,439 times and
`GIVEN UP ON, still open` fires none. **Neither of the two causes that issue
names is what happened, and neither is the counter.**

Recounted from the log, grouping every line by the count the status clause was
carrying:

| count | clause printed | effect sequences dispatched | read requests issued |
|---:|---:|---:|---:|
| 1 to 59 | 3 or 4 each | **1 each** | 1 or 2 each |
| **60** | **2,439** | **1** | **608** |

**The counter is advanced correctly, once per reading, on the Escape rung as on
the one below it.** What stopped is the reading pipeline. The client's own quick
message on every one of those readings is
`<center>Cluster Shutdown in Less than one second` -- EVE's daily downtime -- and
from the reading the count reached 60 the framework issued 608 further
`RequestToVolatileProcess` reads and completed none of them. No
`ReadingFromGameClientCompleted` means no `updateMemoryForNewReadingFromGame`,
so **every** counter written there froze at the same instant: the ammo swap's
`given up 2578 readings ago`, the damage window's `(45s, 33rd)`,
`Visited anomalies: 65`, `Route marker unchanged ticks: 2428`. The run ended
when its own session duration elapsed, with the whole memory line byte-identical
on all 2,439.

**So the 2,439 lines are one decision.** The host prints the last status text on
every log line it writes, and this file's own first orientation note --
*a decision in the log is not an action* -- is what the issue's headline count
falls to. It has now cost a threshold calibration twice (`stall_watch.py`), a
retreat measurement once (#141), and an issue's whole diagnosis here.

**Two of that incident's claims flip, and one is about the design.** Escape's
entire live outing is **one press**, not 2,439, so #109's open question --
whether Escape closes a window the answer does not -- is exactly as open as it
was. The rung stays: deleting it would be answering that question from a sample
of one, and what the give-up needs is readings spent, which the rung supplies
whether or not the key works. And the third rung is *unobserved* rather than
unreachable -- the fold in `test_saxrat_message_box_standoff` runs a standoff to
120 through the real `Bot.elm` and reaches `LeaveTheMessageBoxAlone` on exactly
the reading its own name says.

**The mission runner does not share the defect, because there is no defect.**
Its `messageBoxStandoffAfterReading`, `messageBoxStandoffVerdict` and memory
update are the same declarations under the same names; mission run 35 never took
the counter past 2, which is absence of evidence and now also unnecessary.

**What the run genuinely could not say is what the window was**, which is #164's
own first Unverified item and the one thing that shipped as a change.
`describeMessageBoxGivenUpOn` is the only thing in either bot that ever printed a
box's identity, and it is written on the one reading the count crosses 120 -- so
a standoff that ends any other way, as this one did, leaves a 125 MB log that
cannot name the dialog. The status clause now carries it on every counted
reading, cut by `messageBoxIdentityForOperator`, the same cut the give-up
sentence takes so the two cannot drift:

```
Message box: 60/120 (pressing Escape at it), message box saying '<the dialog's own words>' with buttons [...].
```

The clause is a rule over the record in both apps rather than inline in the
status line, so a case executes what an operator reads instead of asserting a
substring -- which is the trap that let a clause printing nothing at all pass
#109's own file once.

**What the run does say about the box**: its decision line is
`Dismiss it using the window's close button`, 186 times over the 59 readings it
was answered. That is the *third* and last of `closeMessageBoxByDeclining`'s
options, the one a dialog whose buttons this file does not recognise at all falls
through to -- so this window offered neither a Close/OK nor a `no_dialog_button`,
unlike the emoji picker #101 was filed on, and the X did not close it in 59
tries. saxrat run 5's box, by contrast, was answered with `OK` and closed in 2
readings, which is the positive control that the branch works.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_message_box_standoff.py` (56 cases, up from
46) and `test_message_box_standoff.py` (42, up from 35). The clause is executed
through the real `Bot.elm` at all three rungs and against a paragraph-length
dialog, the two
apps' renderings are compared, and the run is recounted as *relations* over every
`saxrat_run*.log` on the machine rather than as the numbers above: the counter
advanced once per reading with one dispatch each below the escalation, the
escalation dispatched at most one against thousands of printed clauses, and the
reads issued at the escalation outnumber the whole answering rung's by orders of
magnitude while the count never moved.

Confirmed by mutation, **eleven** of them, each failing a named case: the counter
pinned at the escalation, which is run 11's shape as the issue reads it; the
give-up rung answering `PressEscapeAtTheMessageBox` so it is never reached; the
Escape rung deleted, which is the change this PR considered and declined; the
identity dropped from the clause; the clause given a second cut length; the
clause re-inlined in the status line; the clause speaking on a reading with no
box; the truncation removed; the rung wordings dropped; a decision consulting the
clause; the identity dropped from the mission runner's copy only; and the
escalation retuned to 44, which no longer matches the answering rung the run
recorded.

**Unverified.** Whether Escape closes such a window -- one press, no
observation. What that window was, since the identity was added after the run
that needed it. And the give-up rung itself, which no run of either bot has
reached. What to watch on the next saxrat run that meets a box:
`Message box: N/120` appearing briefly and vanishing with the dialog **named** in
it, since the recorded dialogs close in 2 to 44 readings. A count that stops
moving while the rest of the status line also stops moving is the client having
gone away, not this branch; the tell is every other counter in the same line
frozen with it.

### The combat feed was a third of the log and none of it was new

Issue #190. `describeVisibleCombatMessages` printed up to six lines of the
client's `CombatMessage` widget into saxrat's status text on **every reading**,
and it was the single largest thing in the log: 9,639 of run 20's 25,762 lines,
98,700 of run 21's 296,465, a third of each. It is removed. Nothing replaces it.

**It was almost entirely repetition.** The widget is a rolling on-screen window,
so consecutive readings mostly re-render the same six lines — **1,376 of run
20's 1,377 feed blocks were byte-identical to the block before them**, and 99.5%
of run 21's. That is not a property of a quiet grid: the same measurement over
run 23, which fought, gives 93%.

**And it outlived the fight, because messages age off the *screen* rather than
off the grid.** In run 20, **1,344 of those 1,377 blocks were printed on readings
whose own decision line says the ship is docked** — combat that could not be
happening, reprinted at the operator for the whole run. Run 21 shows almost none
of that, so it depends on the run's shape, and **nothing in the feed
distinguished the two**. A summary line would not have fixed that half; only
reading a channel that is scoped to the reading does.

**Nothing replaces it, and the reason is that the replacement is already there.**
The obvious alternative is a short clause derived from the channel the host
already sums — hits and damage this reading, in and out. The incoming half of
exactly that is `describeIncomingDamage`, in the status line on every reading
since the port: the 45-second window, the threshold, whether the host carries the
channel at all, whether the reading is frozen, and the attackers named. A second
clause off the same channel would say what that one already says, on a reading
whose whole problem is the log's size. `test_the_channel_is_still_reported` is what
goes red if that clause is ever dropped, since dropping it is what would turn
this removal into a loss.

**The outgoing half was genuinely unreported here**, and adding it was a
separate change with its own evidence: saxrat read
`outgoingDamageSinceLastReading` nowhere, so a clause for it is a new instrument
rather than a replacement for a removed one. That change has since landed — see
"saxrat reads what its own guns achieved, and there is no threshold to put on
it" below — so both directions of the channel are printed now, and this
removal's replacement is the whole summary rather than half of one.

**`visibleCombatMessages` is kept, unused**, which is the mission runner's own
answer to the same question — its `combatFeedIsReportedByTheHostGameLog` marker
has recorded that decision since it dropped this clause. The scraper encodes
which UI nodes carry combat text and how to read them, which is the expensive
part to rediscover, and any future in-decision use of combat state wants exactly
that. saxrat now carries the same marker under the same name, so the two bots
read alike here.

**This changes no behaviour.** The clause was read by the status line at one site
and by **no decision**, which is what makes it a removal rather than a retuning.

**Verified without a live client**, in
`tools/macos-host/tests/test_combat_feed_removed.py` (14 cases). The scraper is
*executed* through the real `Bot.elm` in `elm repl` against a `CombatMessage`
tree run through the real `EveOnline.ParseUserInterface` — a message split across
four labels with EVE's own colour tagging on it comes back joined and stripped —
because a declaration kept but broken teaches nobody which nodes carry combat
text. The removal is read out of the source through the declaration reader that
strips doc comments, so the marker may go on naming what it replaced while no
declaration reads the scraper and none prints `Combat feed`. The corpus is
recounted as *relations* rather than as the numbers above — the feed was a large
share of the log, nearly every block repeated the one before it, some run printed
most of its blocks while docked, and the client's own `(combat)` lines are echoed
into the same log — so a growing corpus cannot turn a true claim red. Run 23 was
still being written while this was measured, which is why.

Confirmed by mutation, ten of them, each failing a named case: the clause and its
call site restored; the clause restored but left uncalled, which is the half a
wiring case cannot see; the feed rebuilt under another name; the scraper deleted;
the scraper pointed at a node type the client does not draw; the marker renamed
so the argument is unfindable; the marker's doc no longer naming what reports
this channel instead; **`describeIncomingDamage` dropped from the status line**,
which is the mutation that turns this removal into a loss; the mission runner's
marker renamed, so the two bots stop reading alike; and — on the cases' own
premise — quiet blocks counted among the repeats, which would let a run of
`Combat feed: quiet.` satisfy the repetition measurement.

**One mutation survived the first pass and the hole was in this file's own
premise.** The repetition case was satisfied whether or not quiet blocks were
excluded, so the doc comment's reason for excluding them was a claim nothing
held. `test_the_quiet_blocks_are_not_what_is_being_counted` asserts the corpus
really holds them and that no counted block is one.

**Unverified: nothing, and that is unusual for a section here.** The removal
needs no run to confirm — there is no new branch, no new bound and no new
matcher, and the status line simply stops carrying a clause. What a run would
show is negative: `Combat feed` no longer appearing, and `dmg N/T (45s, Nrd)`
appearing exactly as before. A run whose log still carries the feed is one flying
an older tree, which is what `# bot version:` is for.

### saxrat reads what its own guns achieved, and there is no threshold to put on it

The ask was *"if we see lots of missed shots from us, we swap ammo and/or
manoeuvre class"*. PR #271 made a miss reach the bot for the first time —
`misses` sits beside `hits` on `OutgoingDamageToTarget` in all six vendored
parser copies — so the signal was available with no host or parser work.

**What ships is the instrument and not the trigger.** The rule has no threshold,
and the client's own logs are what say so rather than caution about saying so.

**First, the gap that was already there.** saxrat read
`outgoingDamageSinceLastReading` in **zero** places. Every shot this bot has ever
fired was counted by the host, decoded by the parser and thrown away, on every
reading of every recorded run — the same shape as `quickMessage` before #123 and
`avoidRats` before #125, and the worse kind: evidence that arrived and was
discarded. `OutgoingFireMemory` folds it per reading and `describeOutgoingFire`
prints it, beside `describeIncomingDamage`, which is the same channel in the
other direction.

#### The measurement, against the client's own kill signal

Over the 40 sessions carrying outgoing fire in `~/Documents/EVE/logs/Gamelogs`
(207,313 shots), cut at every `(bounty)` line — the only thing in this corpus
that states a rat died, and a channel the bot is deliberately not given, so it is
genuinely independent of anything the bot decided:

| | miss share |
|---|---|
| worst kill-free stretch that then **produced a kill** | **100%** |
| the next one down | **99.1%**, over 467 shots and 456 seconds |
| worst stretch that **never** produced a kill | no higher than either |

**The top row does the work and needs no second population.** A stretch that
missed nearly every shot for 456 seconds went on to kill its rat, so any
threshold on a miss rate below 100% fires on that fight and breaks it off. The
"never produced a kill" group is thin — seven stretches, each the last of its
session — and nothing here rests on it.

**The two populations do not separate, at any share, at any length.** And read
the other way round they separate *backwards*: over 30-second windows the median
miss share is **5% where a rat died and 2% where none did**. A rule keyed on
missing would fire hardest on the grids that were paying.

**Whether they appear to separate at all depends on how the corpus is cut**,
which is itself the evidence. At a 30-second window the two look separated at
82% against 90%; at 45 and 60 seconds the population that produced kills reaches
100% as well and the gap is gone. A gap that moves with the window length is an
artefact of the window.

**The stalls this bot actually suffers are low-miss stalls**, which is PR #272's
own finding restated from this side: *"the guns were landing and the repairs were
faster"*. Most kill-free fighting in the corpus sits below a 50% miss share. So a
miss signal could not have caught run 48 however it was tuned, and
`combatStalemate` is not made faster or more specific by one.

#### The 702-consecutive-miss hazard is worse than recorded, not better

`parse_outgoing_miss`' doc comment reads it as *"a target the guns went on to
hurt absorbed 702 consecutive misses first"*. Located in the corpus, that run is
a `Hunter Alvi` in `20260814_161640`: **702 shots, 2,650 seconds, not one
landing**, at a steady 32 shots per two minutes to the end of the session, with
zero kills in the whole stretch.

**It was never a fight that recovered.** That reading comes from a name-keyed
fold — the same *name* had been hurt earlier in the session, on a different rat —
and scored against the bounty channel the run produced nothing at all. So the one
episode that looks like the signal working is a genuine unwinnable stall, and it
is indistinguishable by share and by length from the 99.1% stretch that
recovered. The hazard is that the two cannot be told apart, not that long miss
runs are usually benign.

#### Why neither actuator was wired

- **The manoeuvre half is expressible and was not widened.**
  `ensureShipIsKeepingRange` holds `vkey_E` and `ensureShipIsOrbiting` holds
  `vkey_W` over a click, and they are the last two key-wrapped clicks on the hot
  path — PR #243 removed the third (`vkey_Q` on approach) because a posted key
  inherits the session's modifiers, and with the Fn bit set the bot pressed
  macOS Quick Note at itself 241 times in one run. They are also the *outermost*
  dispatch in `decideActionInAnomaly` and re-issue on every reading until the
  client reports the manoeuvre, so changing class more often makes them fire
  more often on a path that has no bound of its own. **They should be converted
  the way PR #249 converted the approach before anything drives them harder**;
  that is a prerequisite rather than a nicety, and it is not this change.
- **The ammo half is fed by a distance and by nothing else.** `rangeVerdict` is
  a pure function of the active target's distance and the configured crossover,
  so "swap because we are missing" would need a second input to a rule that has
  one. And the actuator does not finish what it starts — see below.

#### The ammo swap abandons the attempts it already starts, and why

Run 50 carries **127 `Gave up on loading` lines**, 79 abandoning
`Multifrequency M` and 48 abandoning `Radio M`. Counted as *attempts* rather than
as lines those are **6 attempts**, against 26 started — 13 of which completed and
7 of which were dropped when the target went away. Two causes, and neither is the
disarm bound being too short:

- **The weapon's context menu does not offer the wanted charge.** `Could not find
  menu entry with text containing 'Radio M'` appears 100 times and the
  `Multifrequency M` form 14, and the cascade then waits until
  `clearStrayContextMenu` clears the menu and the budget expires. The menu omits
  the charge *already loaded*, so this is the swap asking for a charge the gun
  may already carry while `chargeLoaded` reads `(assumed from the load, not read
  back)` — which is #154's own open question, now with a run behind it.
- **The guns never go quiet.** The other four attempts spend the budget on
  `Stop this weapon before loading` (8 to 23 times each), `Told the guns to stop
  3 of 3 readings ago and none has yet read switched off`, and the disarm gate
  deferring under incoming fire. That is #76's territory — a switch-off click
  that does not land — and nothing here addresses it.

**The client refuses nothing**: `cannot load or unload` appears **zero** times in
run 50, so the guns are being stopped properly when they are stopped at all.

So the swap completes 13 of the 19 attempts that get an answer and abandons the
other 6, bounded and retried at the next change of range. **Triggering more swaps
on a miss signal would make the bot worse rather than better**, and there is no
miss signal to trigger on in any case.

#### Verified without a live client

`tools/macos-host/tests/test_saxrat_outgoing_fire.py` (20 cases). The rule is
executed through the real `Bot.elm` in `elm repl` and folded over whole sessions
rather than asked once, and the readings it is asked about carry the host's own
`MacOsHostSyntheticOutgoingDamage` node — built by `botlab_host.py`'s emitter and
decoded by the real `EveOnline.ParseUserInterface`, so the `misses` key the host
writes strictly is the one under test. The corpus is recomputed as **relations**
rather than as the numbers above, so a corpus that grows cannot turn a true claim
red — and if one of them ever fails, the finding has changed and the trigger has
become writable, which is what that file exists to make visible.

The hazard case is the one to keep: **a thousand readings of nothing but misses**
folded through the rule leave `combatStalemateVerdict` exactly where it was,
because the two do not share an input. That is what "nothing decides on this"
means operationally rather than as a claim about occurrences.

Confirmed by mutation, ten of them, each failing a named case: the run advanced
on a landed zero, so #90's failure and this one collapse; the run reset on a
reading with no shot in it, which is `gunsSilencedTicks` pinned at 1 again; an
absent channel counted as a reading that missed nothing; `hits` and `misses`
summed, which is the one mistake the parser's doc comment names; the ship-wide
run advanced by a reading that hit one target and missed another; the worst-run
high-water mark following the live run down; the status clause dropping its
"Nothing decides on this"; a decision reading the field; a second call site given
to either manoeuvre verb; and the wanted charge given a second input.

#### Unverified

**Any of it running.** No run has been flown; this was written with the corpus
and the repl. What to watch on the first one is `Outgoing fire:` on every
reading, with the landed and missed counts *moving* while the guns fire. A run
that fights and reads `NO COMBAT LOG` throughout is a host not carrying the
channel; a run whose two counts stay at zero while the guns cycle is the summary
not reaching the bot, which is the direction this fails silently in.

**Whether a bot-side reading separates the populations where a client-side second
does not.** Every number above is folded at the client's own second, which is
finer than a real reading (one to eight seconds) — the fold most favourable to a
long run, and the same argument #271 makes. What no corpus can supply is the
*bot's* view: saxrat has never printed an outgoing number, so there is no run in
which the miss share sits beside the target, the range and the charge the bot
believed it had. That is exactly what this clause makes the next run produce.

**Why run 50's menu did not offer the charge.** Whether the gun already carried
it — in which case the menu is correct and `chargeLoaded` is wrong — or the menu
was attributed to the wrong module is still not established, and nothing here
claims those attempts would have succeeded.

### An in-range acceleration gate is opened from the panel here too

Issue #145 is `activateGateOnOverviewEntry` in `eve-online-saxrat`: an in-range
gate was driven with `useContextMenuCascadeOnOverviewEntry`, and the mission
runner stopped doing that on evidence its own doc comment carries — the panel's
`selectedItemActivateGate` verified live on the gate that had refused 124
D-clicks, the objective going from "You need to activate the Acceleration Gate"
to "Warping" on the press and the overview turning over from 17 rows to 22.
Ported whole, wrapped in `unlessAlreadyClosingIn` because EVE flies the ship the
last of the way and takes the gate on arrival, so re-issuing restarts the
manoeuvre.

**The case for it is one gate, not 829 failures, and the recount is most of what
this change is.** The two newest saxrat runs carry 829 `has not taken me
anywhere` lines. That give-up prints on every reading once
`gateRefusesThisShipTicks` (40) is passed, so 829 lines are **two** in-reach
episodes — one per run, and the only two in the whole recorded corpus that ever
passed the bound. Counted as episodes rather than as lines:

| run | in-reach episodes | peaks |
|---|---:|---|
| 1, 2 | 0 | — |
| 3 | 4 | 5, 10, 15, 18 |
| 4 | 3 | 1, 6, **282** |
| 5 | 3 | 1, 8, **3,504** |

**Only run 4's is this mechanism failing.** In the 40 readings before its give-up
the bot completed 30 context-menu cascades and clicked `Activate Gate` on an
`Ancient Acceleration Gate` inside 2,000 m; the gate never opened, the client
wrote no refusal on any channel, and after 238 readings of the give-up the bot
went back to ratting. That is the same silent no-op signature the mission
runner's D-clicks had.

**Run 5's is not about the mechanism at all, and it is the more useful finding.**
Its counter reached 3,504 while the bot printed `I see a 'Warp to Site'
opportunity -- warp there` **10,353** times and reached an in-range gate
activation decision **three** times. `warpToOpportunitySiteIfAvailable` is
consulted before the gate branch, so for that whole stretch the gate was merely
nearby and was never asked to open — and `gateWithinReachTicks` was counting
`accelerationGateIsWithinReach`, the ship's proximity, so it ran up anyway and
produced 108 give-ups about a gate this session had made three attempts on. That
is #42's correction arriving in the second bot, and #102's shape underneath it: a
counter and the thing it is supposed to bound measuring different quantities.

**Why the branch went unreached is #147, and the recordings confirm that reading
rather than contradict it.** `warpToOpportunitySiteIfAvailable` answers `Just`
whenever a "Warp to Site" button is anywhere in the tree, and
`pickAnotherAnomalyOrLeave` puts it ahead of the gate branch, so the gate is
unreachable for as long as that button is drawn — which stays true after arrival.
The give-ups cluster exactly as that predicts: **one contiguous block per run**,
run 5's holding 108 lines with **zero** opportunity-warp lines inside it and the
last one 20 lines before it, against 10,485 in the run as a whole. Run 4 is the
control — one block too, and 12 opportunity lines in the entire run, none near
it. So a low give-up count in a saxrat run is not evidence a gate opened; it can
equally be the branch never being asked, and any before-and-after comparison on
this bot has to say which. **Fixing that ordering was deliberately not part of
this change and is #147, the section below**, but the counter here is what stops
the shadowing being *paid for*: counting the ask, run 5's shadowed readings hold
at 0 and its reachable window is about 36 readings, short of the bound, so that
give-up would not have fired at all.

So the counter now counts the **ask** — `askingAnAccelerationGateToOpen`, the
Selected Item panel showing an acceleration gate that is already in reach — holds
on a reading in reach that did not ask, and resets only on leaving reach. The
hold is the mission runner's, for its reason: a reset on a reading that did not
ask is the shape that pinned `gunsSilencedTicks` at 1 forever, so anything
holding the tree between two attempts would wipe the evidence.

**One deliberate divergence from the mission runner's rule, and it is a bound
rather than a preference.** That one counts only the readings the panel made the
offer, and leaves "the gate is selected and the panel offers nothing" to
`nothingToDoTicks` from the bottom of its decision tree. saxrat has no such
counter and this branch answers `Just`, so an uncounted no-button state is a ship
parked at a gate with nothing to end it. Counting it keeps one bound over both
shapes — a gate the panel offers and does not open, and a gate the panel will not
offer to open at all.

**The bound stays at 40, and the corpus rather than caution is why.** The worry
is real — a number placed against a failing cascade may be wrong for a working
panel press — but what it bounds is how long the ship stands at a gate that is
not opening, and that cost is the same whichever way the bot is asking. The
recorded episodes leave nothing in the middle: every one peaks at 1 to 18
readings or at 282 and 3,504. 40 sits in that gap with an order of magnitude
either side, and no version of this mechanism moves an episode across it. What
was wrong was the counter, not the number.

**That last paragraph is this section's own reasoning and #147 overturned it.**
The number survived; the argument did not. Every one of those peaks was counted
while the opportunity branch held the tree, so they are readings spent *near* a
gate — the quantity this very change argues is the wrong one — and a distribution
of those cannot size a budget for readings spent *asking*. What sizes it is the
mission runner's corpus, where the branch is reached: see "The gate is worked
before the site is warped to again" below.

**The give-up no longer names a cause.** It said the gate "most likely will not
admit this ship", which is an inference, and run 4's is the case where it is
wrong: the client said nothing at all, so the reading that is available is the
silence and not the restriction. Sending an operator to look at the hull when the
evidence points at the click is the cost. The wording now names what it was
doing, says the client was silent, and names the three readings it cannot tell
apart. The mission runner *can* say a gate wants an item — it reads `This gate is
locked! … in your cargo hold` off the `info` channel — and that sentence appears
in **no** recorded saxrat run beside either episode, which is what makes the
weaker claim the honest one.

**The out-of-range branch is untouched**, deliberately. saxrat's own comment
records that "Activate Gate" from a distance does the whole thing, and the panel
carries `selectedItemActivateGate` only while the gate is in range — that absence
is the natural gate between the two mechanisms, the same argument
`dockAtDestinationStation` makes.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_gate_panel_button.py` (44 cases). The four
pure rules are executed through the real `Bot.elm` in `elm repl` rather than
restated in Python — the step rule asked as four equalities per case so a rule
answering two things at once or none would fail, at both sides of the bound and
against fixed values either side; the counter folded over whole sessions
including run 5's own 3,504-reading shape; the give-up and the status clause
rendered. The panel reads go through the real `EveOnline.ParseUserInterface`,
which is also the evidence that saxrat's diverged copy exposes the selected-item
window — the part of that parser this bot had never used, `Bot.elm` naming
`selectedItem` zero times before this. The wiring and the range split are read
out of the source through a whitespace-collapsing reader. The corpus is recounted
as *relations* rather than as the numbers above: give-up lines far outnumber
episodes, the episodes separate around the bound by more than a factor of four,
run 5's opportunity branch dwarfs its gate activations, and no client refusal was
ever recorded beside a gate.

Confirmed by mutation, **thirteen** of them, each failing a named case: the
in-range branch reverted to the context-menu cascade; the press no longer wrapped
in `unlessAlreadyClosingIn`; the lookup pointed at `selectedItemApproach`; the
counter advanced on proximity again, which is run 5's defect; the counter
resetting rather than holding; a gate selected with no button no longer counted;
the bound's comparison moved either way; the select-first step dropped so the
panel is pressed while showing something else; the range split neutralised so a
40 km gate takes the panel path; the ship-restriction sentence restored; the
give-up dropping its reading count; and the status clause no longer separating
asking from being near.

**Two mutations survived the first pass and both were real holes.** The
named-button case asserted the string occurred anywhere in the branch, and the
branch's own wait message quotes the button by name — so pointing the *lookup* at
`selectedItemApproach` passed, which is the press acting on the wrong button
while the log still names the right one. And the "a gate selected with no button
is still an ask" case was written over the counter, which is *handed* `asking` as
an input and therefore cannot notice that rule being narrowed; it is asked of
`askingAnAccelerationGateToOpen` directly now.

**Unverified: any of it running, and whether either recorded gate would have
opened.** No run has been flown since. Nothing here establishes that run 4's gate
was openable at all — the panel press is proven on the mission runner's client
and not on this one, and a gate that genuinely restricts this hull would produce
the same give-up with the same silence. What to watch on the first saxrat run
that meets a gate in range: `Readings spent asking an acceleration gate to open:
N of 40` in the status line, `(asking now)` beside it, and the count staying in
single figures before the pocket changes. A count that climbs to 41 with
`(asking now)` throughout is a gate that will not open for this ship whatever the
mechanism, and is the first evidence anyone will have of that. A count that
climbs while the clause reads `(a gate is in reach, not being asked)` means
something above this branch is holding the tree, which is run 5's shape and is
now visible rather than being spent as budget.

### The gate is worked before the site is warped to again

Issue #147, and the branch above is what it makes reachable.
`pickAnotherAnomalyOrLeave` asked `warpToOpportunitySiteIfAvailable` first and
`activateAccelerationGateIfPresent` only where that answered `Nothing`, while the
comment over both said they "take priority over the normal probe-scan hunt loop"
— which is a claim about the pair against the third option and says nothing about
which of the two wins. The code answered "the first one, always", because its
condition is a whole-tree text search for a "Warp to Site" button and the
Opportunities panel goes on drawing that after the ship has arrived. So inside a
multi-pocket site the gate branch was unreachable and the site was re-warped
instead of followed.

**The crux is whether a reading can tell "an opportunity exists" from "the ship
still needs to go there". It can — off the grid rather than off the panel.**

Run 5's shadowed stretch is the measurement, and it is worse than the issue's
count of decision lines suggests. It runs **3,458 readings**, about 75 minutes of
a three-hour session, with:

| | |
|---|---:|
| opportunity-warp decision lines | 10,469 |
| clicks dispatched, all at one screen position | 3,460 |
| distinct screen positions clicked | **1** |
| in-warp readings after the two the arrival ends on | **0** |
| readings with an acceleration gate in reach | **every one** |
| **on-screen quick messages** | **0** |

The counter runs 2 → 3,463 unbroken, so the ship never left the gate; the combat
feed and the overview are unchanged throughout; and it ended only when a person
warped the ship by hand. **The client never answered one of those 3,460 clicks**,
which is what rules out reading the client instead — there is no sentence to
match on, in a run that carries dozens of distinct quick-message wordings
elsewhere.

The grid does answer. Gates exist only inside sites, so a gate on the overview
means the ship has already arrived somewhere, and every recorded episode agrees:

- **three stretches began with a gate in reach** (run 3 line 124489, run 4 line
  23016, run 5 line 101277) and **none ever produced a warp** — two ended within
  a handful of readings when the button went away and the gate branch finally got
  its turn;
- **the two that began with no gate in reach** (run 4 line 21172, run 5 line
  99710) were in warp within three readings.

**So the fix is two halves, and the second is what keeps it from swapping one
shadow for another.** `siteProgressStep` is the ordering as a pure rule over a
record — the gate branch first, then a "Warp to Site" **only where no gate is in
reach**, then the hunt loop. Ordering alone would not do: the gate branch answers
`Nothing` once it has given up, so the very next reading would fall straight back
into the dead click with nothing left to bound it. Declining sends it to the
scanner instead, which is the recovery run 4 eventually made on its own after 238
wasted readings.

**The give-up hands the reading back**, where it used to answer
`askForHelpToGetUnstuck` — a leaf that dispatches nothing and waits. Asked first,
that would have shadowed the warp branch permanently rather than being shadowed
by it, which is the reverse of the failure being fixed. It is the mission
runner's answer for the mission runner's reason, and it costs the decision line:
a `Nothing` cannot carry one, so `describeGateActivationAsk` carries the give-up
in the status line on every reading afterwards instead. Run 10 on the other bot
is what an unreported decline costs — 1,325 readings of "nothing is happening"
beside a gate 32 m away.

**A far gate now outranks an offered site, and that is a delay rather than a
loss.** The panel is persistent, so the site is still offered after the gate is
taken, and the recorded far-gate episodes close on their own: run 5's ran 23,000
m → 2,405 m and run 4's 10,000 m → 2,508 m, both handing off to something else
when they arrived. The reverse shadow — a gate present while a genuinely
un-warped site waits — costs those readings. The shadow being removed cost 40% of
run 5's session and, on the issue's own figures, 38% of its income.

**`gateRefusesThisShipTicks` stays at 40 and its argument is replaced.** #145
placed it against saxrat's peaks of 1 to 18 versus 282 and 3,504 and called that
an order of magnitude of clearance. Those are readings spent *near* a gate under
this very shadowing, so they cannot size a budget for readings spent *asking*.
The mission runner's corpus can, because its gate branch is reached and takes
gates: across every episode in its 37 runs where the nearest gate came inside
2,000 m, **89 of 93 ended in a warp and 88 of those had spent 0 to 4 readings in
reach** — usually 0, since the client takes the gate on the approach — with the
longest that still opened spending **15**. The largest count that corpus records
on a gate its branch gave up on is **335**. So the gap is real and its edges are
15 and 335 rather than 18 and 282; 40 sits inside it at 2.7 times the largest
success and an eighth of the failure. Being early also costs less than it did,
now that the give-up hands back rather than parking the session.

**Run 6 is the newest run and says nothing about any of this.** It flew #149's
merge for ten hours, 1.4 million log lines, and met **no acceleration gate and no
opportunity at all** — zero gate decisions of any kind, zero "Warp to Site" lines,
the status clause reading `0 of 40` throughout. Worth recording so it is not
mistaken for a run that exercised the path.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_opportunity_shadow.py` (32 cases). The
ordering rule is executed through the real `Bot.elm` in `elm repl` at every
combination of its three inputs, asked as three equalities per case so a rule
answering two things at once or none would fail; the search's *inability* is
asserted over readings the real `EveOnline.ParseUserInterface` produced, with the
grid answering differently on the same two trees; the give-up's comparison is
asked at both sides of the bound and at a fixed value past it; and the status
clause is rendered. The corpus is recounted as relations rather than as the
numbers above — a stretch beside a gate in reach in which the ship never warped,
no client answer inside it, and every stretch that *did* end in a warp taken with
no gate in reach — and the bound's two edges are recomputed from the mission runs.

Confirmed by mutation, **thirteen** of them, each failing a named case: the
ordering restored to warp-first; a plain gate-first nesting that skips the rule
(and so drops the guard that matters after the give-up); the rule moved into a
second binding with the old nesting left under the real name; the two arms
swapped; the in-reach clause dropped from the rule; the rule's own ifs reordered;
the reach input neutralised to `False`; the give-up answering
`askForHelpToGetUnstuck` again; a second comparison of the bound inside the
branch; the status clause dropping the give-up; the bound cut to 10, which slices
the mission corpus's successes; the bound raised to 400, past the recorded
failure; and the comparison moved one reading early.

**One mutation survived the first pass and the hole was real.** The reader for
`pickAnotherAnomalyOrLeave` — which is a `let` binding rather than a top-level
declaration — read from the binding's name to the next `in`, so a mutation that
left the old nesting under that name and moved the real ordering into a second
binding beside it passed every case: the text asserted on still held both. It
ends at the next line indented no further than the binding's own name now, and
that mutation is kept as one of the thirteen.

**Unverified: any of it running.** No run has been flown since, and run 6 met
neither a gate nor an opportunity, so nothing here has been watched. What to
watch on the first saxrat run that enters a multi-pocket site: `I see a 'Warp to
Site' opportunity -- warp there` falling from five figures to roughly the number
of sites actually entered, with gate decisions rising to meet it. Two failures to
watch for, in opposite directions. A run that never warps to a site at all would
mean the gate branch is answering `Just` where it should not, and the tell is
gate decisions climbing while `Found matching anomaly` and the warp line both go
quiet. And a gate that will not open now ends in the status line's give-up
followed by ordinary hunting rather than by the session parking — if instead the
log shows the bot warping back to the same site and standing at the same gate
again, that is the oscillation this does not bound: the opportunity is still
offered once the ship leaves reach, and nothing remembers that its gate was given
up on. **Income is the outcome measure and there is a clean control**: run 38 did
1,536,545 ISK/hr on these settings before this path started dominating.

### The host says so when reads stop completing

Issue #166. In run 11 the client stopped answering read requests and the bot did
not notice -- 18,158 issued, 17,263 completed, 895 that never came back. From that
moment `ReadingFromGameClientCompleted` never fired again, so
`updateMemoryForNewReadingFromGame` never ran, so every counter it writes froze at
the same instant and the whole memory line was byte-identical for the rest of the
run.

**There is no rule to fix**, which is why this is host-side. PR #165 established
the message-box ladder was correct as written; nothing in `Bot.elm` can advance a
counter on a reading that never arrived. The cost is that the log lies: the host
reprints the current decision on every line, so a stalled pipeline reads exactly
like thousands of healthy readings -- and by #165's count that has already cost a
threshold calibration twice, a retreat measurement in #141, and the whole
diagnosis of #164.

`ReadCompletionWatch` counts consecutive volatile-process reads that came back
`Err` and prints once at three, again every sixtieth, and once on recovery naming
how many were missed. **Only the volatile-process read is judged**: the 2023 host
interface routes input through a volatile-process request, so a read-shaped `Err`
can arrive from a task that was never a read, and judging by shape would put "the
client did not answer" in the log for a failed keystroke.

**Unverified:** nothing has been flown, and the threshold of three is a judgement
rather than a measurement -- run 11 carried 895 consecutive failures, so anything
in this range catches it early, but no run has shown how often a single read fails
harmlessly.
### The route panel can say 'No Destination' beside a marker, and the marker lies

Issue #191. saxrat run 23 spent 1,200+ consecutive readings on `No stargate on
the overview is named for 'Hutian'` and never moved. It was travelling a route
the client had never computed. The panel, read live while it was stuck, carried
`No Destination`, a `Next System in Route` label naming Hutian, and `No
Destination` again -- with one marker icon.

`infoPanelRouteFirstMarkerFromReadingFromGameClient` answers the panel's
**visibility** and has never read its text, so a stale pip reads as a route.
`routePanelSaysNoDestination` reads the words, and `jumpToNextSystem` asks it
before the marker.

**The answer is `setRouteToNextHuntingGround`, not a counter.** The travel leg is
a fall-back to a cascade and has no bound; asking for a route is bounded by
`routeAskGiveUpReadings` and ends in the circuit moving on. Letting the reading
reach the branch that already has a bound is what ends the loop -- a second
counter here would only have made the parking quieter.

It is the destination rather than the client: from the same position, `Hamse`
gave `Route 5 Jumps` and `Amarr` `Route 6 Jumps`, while `Hutian` gave no route.
So `hunt-system` can hold a system the client will not route to, and the circuit
rotates onto it eventually.

**Unverified:** whether Hutian is unreachable by gate at all or excluded by an
autopilot route preference is **not established**, and #191 says so -- that
distinction decides whether a bot could detect it in advance, and nothing here
rests on it. Nothing has been flown.
### The client states its lock range in words, and it now outranks the ratchet

Issue #206. `lockProvenAtMeters` only rises, so an attribution error crediting a
lock to a more distant row is permanent. Run 28 ratcheted to 77 km on a hull whose
real range is 49 km while `lockRefusedAtMeters` fell to 33 km -- the two crossed,
`lockRangeThresholdInMeters` resolved it in favour of proven, and
`targeting-range=49000` sat inert with only a restart able to clear it.

The client had said the number outright, 1,277 live sightings in that same run:
`The target <b>Centii Minion</b> is too far away. It must be within <b>49 km</b>.`

`lockRangeStatedInQuickMessage` reads it and the threshold takes it as
`min fromSetting stated`, so a measurement can no longer raise the bound past what
the client stated. The setting still wins when it is _narrower_, which is the one
direction this rule has never overridden.

**Overwritten, never narrowed.** The ceiling is not a constant even for one hull:
only 49 km and 39 km occur across the corpus and runs 13 and 14 carry both within
one session, a sensor booster being the obvious candidate. A monotone bound here
would be #206 again in the other direction, and a case pins the absence of any
`min` or `max` at the write site.

**Read from the live quick message, not the game log echo**, which reprints the
sentence under every decision -- counting those would make one refusal look like
hundreds. And read as a **pair** (`too far away` with `must be within`), because
the first phrase alone is written about warping, approaching and containers.

**Unverified:** nothing has been flown, and the sensor-booster explanation for the
ceiling moving is consistent with the corpus but unconfirmed. Only `km` is
accepted; a sighting in other units would be declined rather than guessed at, and
none is known to exist.
### `anomaly-name` replaces the shipped defaults rather than joining them

Issue #198. `BotSettings.anomalyNames` started as `[ "sansha rally point",
"angel rally point" ]` and the handler prepended, so an operator naming six
hideaways hunted those six **and** two rally points. The widening runs the wrong
way -- a rally point is a considerably harder site than a hideaway, so it is the
operator narrowing the filter who pays, and on an unfamiliar hull that is the
difference between a long run and a loss. `--help` already read like replacement
("Choose the name of anomalies to take"), so the code and the documentation were
answering different questions.

The defaults are kept as a **fallback**: the field starts empty,
`anomalyNamesInEffect` answers `shippedAnomalyNames` when nothing was named, and
anything named replaces them. An unconfigured bot is unchanged.

**"Take anything" did not exist before and does now.** The filter carried a
`List.isEmpty` shortcut meaning exactly that, which could never fire -- the
handler only prepends, so a list starting with two entries is never empty. It is
gone, and `anomaly-name=*` says it through #188's prefix rule.

**Unverified:** whether any recorded run ever set `anomaly-name`, so whether this
has cost anything in practice is not established -- only that the launcher's own
string names six sites and would have hunted eight. `eve-online-combat-anomaly-bot`
and `eve-online-wingus` both carry an anomaly-name setting and neither was
examined.

### The comma the settings parser eats: one of the two columns is read, one cannot be

Issue #197, and it is a reading rather than a change -- nothing about
`splitSettingIntoNames` moves. #182 made saxrat's `hunt-system`, `anomaly-name`
and `avoid-rat` split their value on commas, and the split is applied to the
value of **every** line, so there is no form -- one name per line, several per
line, any mixture -- in which a name containing a comma reaches the bot. For a
character name and a solar system name that costs nothing, because the client's
own naming rules forbid a comma. For the other two it was an open question, and
the issue's point was that it was *unread* rather than known-safe.

**`avoid-rat` is answered: no client-written object name in any recording carries
a comma.** Two independent readings, both from the recorded corpus:

| reading | distinct names | mentions | runs |
|---|---:|---:|---:|
| a Name the bots quoted off an overview row | **231** | 637,060 | 68 |
| a name the client wrote in a `(combat)` line | **225** | 306,756 | 68 |
| the two together | **245** | | 69 of 86 |

and the client's own logs say it a third time from a source this repo does not
parse at all: **348** distinct actors across **360,788** `(combat)` lines in 40
sessions of `~/Documents/EVE/logs/Gamelogs`. Not one of any of them contains a
comma.

**What makes that a measurement rather than a search that came up empty is that
these are not plain words.** The same names carry apostrophes
(`Kruul's Henchman`, 501 sightings), full stops (`R.S. Officer`), hyphens
(`Rent-A-Dream Pleasure Gardens`), brackets and parentheses
(`Acolyte I[MNRLG](Acolyte I)`) and a slash (`Gas/Storage Silo`). A column that
admitted a comma had every opportunity to show one. That is the case a mutation
would otherwise pass: a corpus of letters and spaces says nothing about whether
a comma is possible, so `test_the_column_does_carry_other_punctuation` is what
stops the finding resting on a narrow sample.

**`anomaly-name` is not answered, and the corpus is structurally unable to answer
it.** Neither bot ever logs the probe scanner's Name cell. `Dict.get "Name"`
occurs once in saxrat's `Bot.elm`, inside `matchesAnomalyNameFromSettings`, where
it is folded into a `Bool` and dropped; what a run prints about an anomaly is the
**ID** the scanner gives it (`We are in anomaly 'AIC-176'`). So the site words
`run_saxrat.sh` itself asks for -- `Hideaway`, `Refuge`, `Burrow`, `Rally Point`,
`Sanctum`, `Haven`, `Forsaken`, `Forlorn` -- occur across all 86 recorded runs
**zero** times. There is no reading to go back to, and no amount of corpus makes
one.

**The five names anybody has written down are the whole of the direct evidence,
and one of them is the useful one.** `test_saxrat_anomaly_name_wildcard.py` keeps
what a live scanner showed for #188: `Sansha Burrow`, `Sansha Hideaway`,
`Sansha Refuge`, `Drone Assembly`, and **`Dread Assault: Blood Raider Temple`**.
Five is not a sample and this is not claimed as one. What the fifth does settle
is that the column is not letters and spaces -- it carries a colon -- so the
naming-rules argument that covers a character and a solar system has nothing to
say here, and the question stays open on its own terms rather than by analogy.

**Recorded as a test rather than as a sentence**, in
`tools/macos-host/tests/test_saxrat_comma_split_settings.py` (four new classes).
The corpus half reads `~/eve-bot-logs` in one cached pass -- 1.6 GB, about two
minutes -- and skips on a machine that has none, so it runs locally and not in
CI, like every other corpus-reading case here. The counts above are asserted as *relations*
against floors far below them, and a sample thinner than the floor **skips**
rather than passing, since an absence found in a handful of names is not a
finding. The scanner half is pinned the other way round: a case reads the source
for the single `Dict.get "Name"` and a case asserts the site words are absent
from the corpus, so **the day a run starts printing an anomaly's name, that case
goes red** -- which is the day the question becomes answerable and somebody
should be looking.

**One extraction trap, kept because it is the shape of the bug being looked
for.** A `'A', 'B', 'C'` clause -- the lock batch's, and the attacker list's --
cannot be read with `'([^']*)'`, because `Kruul's Henchman` splits it into
`Kruul` and `, `. The second of those *contains a comma*, so the naive reader
reports a comma-bearing name that is entirely its own doing. The first pass of
this measurement did exactly that and it is why `names_in_a_quoted_list` splits
on the separator instead.

**One mutation survived the first pass and the hole was real.** The punctuation
case asked its question of the *union* of the two readings, so flattening the
bots' own overview names to letters and spaces still passed on the strength of
the client's `(combat)` lines -- a defect in this repo's parsing hidden by a
source that does not use it. It is asked of each reading separately now.

**Unverified: whether an anomaly's name can contain a comma**, which is the
question #197 was filed on and the half this does not close. `/check-ui-parse`
against a live scanner is the procedure, and one reading of a system's scan
results would settle it. Also unverified in the other direction: nothing here
establishes that an overview Name *cannot* carry a comma, only that across
245 distinct names and three readings none does. And #197's second Unverified
item stands untouched -- the mission runner's own name lists were not audited.

### A shut probe window hid the gate and the opportunity from the whole path

Issue #204. `decideNextActionWhenInSpace` splits on `probeScannerWindow`, and both
`accelerationGateStep` and `opportunityWarpStep` were `let`-bound inside the
`Just` arm. So with the scanner window closed, a gate standing on grid and a
"Warp to Site" on offer were equally invisible: that arm's entire repertoire was
a middle-row module, whatever was already on the overview, and jumping to the
next system. #202 found the gate half; the opportunity half is the one that
matters for running escalations, and the docked branch was already assuming
otherwise -- it consults `warpToOpportunitySiteIfAvailable` as a predicate and
undocks so "the next tick's in-space chain" can take it, and that chain was the
unreachable one.

The dispatch is now `siteProgressStepOrElse`, a declaration both arms call, with
the caller supplying the floor -- scan results for the arm that has a scanner,
leaving the system for the arm that does not. `siteProgressStep` is still the
arbiter and is untouched. What keeps it safe is where it is reached from:
`decideActionInAnomaly` asks for its continuation only once there is nothing left
to attack, loot or unlock, so an opportunity appearing mid-fight still cannot
pull the ship out of one.

**The arrival age on that arm was a literal that matched a default by accident.**
It passed `600` while `anomalyWaitTimeSeconds` also defaulted to `600`, so
`waitTimeRemainingSeconds` was exactly `0` -- the wait treated as spent, the
120-second loot backstop still live. Two constants agreeing, not a decision: an
operator setting `anomaly-wait-time-seconds = 900` silently turned that arm into
one that tethers for five minutes. It now passes the setting itself, which
reproduces today's behaviour on shipped settings and goes on meaning it when the
setting changes. **Passing the real age would have been a bug**: the anomaly
memory is filed under the ID the scanner gives, so with no scanner
`arrivalInAnomalyAgeSecondsFromMemory` answers its `Maybe.withDefault 0` and the
ship tethers for the full wait at a site it cannot name.

**Unverified:** nothing has been flown, and how often a gate or an opportunity is
actually on grid while the scanner is shut is not measured -- only that the path
is entered, which run 25's log shows.

### The route's next stargate is jumped from the panel here too, and the share is why

Issue #169 is PR #170 ported. The rule is that one whole -- the route panel's own
`Next System in Route` label matched against the overview row's Name, exactly one
match, the panel already showing that gate, the button present, and every other
answer falling back to the route-marker cascade. See "The route panel names the
next system, so the panel can jump the right gate" for the argument, the
`Stargate (Amarr Border)` trap that keeps the Type column out of the match, and
the word-boundary rule. What follows is only what saxrat changes about it.

**The per-leg cost is the finding, and it is not the mission runner's.** #170
measured that bot at a median of 3 and 2 readings a jump leg and argued the
saving down to "one to two readings". Recounted the same way -- the same three
rung wordings, grouped into legs, in *readings* rather than decision lines --
saxrat's runs answer:

| run | readings in the cascade | jump legs | median | worst leg | share of the run |
|---|---:|---:|---:|---:|---:|
| saxrat 13 | **400** | 27 | **12** | 84 | 400 of 1,706 = **23%** |
| saxrat 14 | **348** | 26 | **13** | 17 | 348 of 910 = **38%** |
| mission 35 | 123 | 31 | 3 | 11 | 123 of 6,573 = 1.9% |
| mission 37 | 64 | 20 | 2 | 9 | 64 of 2,393 = 2.7% |

So saxrat's legs are **four to six times** the mission runner's and the cascade
holds roughly a quarter and a third of every reading in the run against that
bot's two and three per cent. **Almost none of it is the jump completing**:
counting only up to the reading carrying the last `Jump Through Stargate` click,
run 13's 400 becomes 371 and run 14's 348 becomes 345, so the readings are spent
getting the command out rather than waiting for the ship afterwards. Robust to
the grouping: at a gap of 3 readings rather than 10 the medians are 11 and 13.

**The issue's own reading counts recount slightly lower and the direction is
unchanged.** #169 quotes 204 cascades in 1,959 readings and 169 in 1,092; the
cascade counts are exact, and PR #170's reading definition -- the integer part of
`# [tick.substep]`, several framework steps to a reading -- gives 1,706 and 910
for the same runs. The share moves from 10% and 15% to 12% and 19% counted that
way, or to 23% and 38% counted as *readings the cascade occupied* rather than
lines it printed, which is what the table above uses and what the doc comment
argues on.

**The panel's texts with a stargate selected are no longer unverified.** That was
#170's first open item -- every capture of that panel with a gate selected had
recorded its buttons and never its text, so `selectedItemIsOverviewEntry` was
matching something nobody had seen. Read off this account's live client while
this was written, with a stargate selected:

```
panel     nameLabel  'Tar (<color=#ff4ecef8>0.8</color>)'
          buttons    selectedItemApproach selectedItemWarpTo selectedItemJump
                     selectedItemOrbit selectedItemKeepAtRange selectedItemLockTarget
                     selectedItemResetCamera selectedItemSetInterest selectedItemShowInfo
overview  Distance '8,998 m'  Name 'Tar'  Type 'Stargate (CONCORD System)'
```

So the panel names the gate by the *system* it leads to, which is the same string
the overview row's Name carries, and `containsWords` matches it through the
security-status markup. `ThePanelNamesTheGateTest` runs that pair through the
real parser and the shipped predicate rather than asserting it in prose.

**Behind the settling guard rather than beside it.** saxrat's `jumpToNextSystem`
waits for the route panel's first marker to hold still for a tick before
right-clicking it, against a window in which the strip is "empty, partial, or
still shifting". The panel press touches no marker, so that guard is not
protecting it from a click landing nowhere -- what it protects is the **label**.
While the route recomputes, `Next System in Route` can still name the *previous*
route's next hop, and jumping the gate an old route wanted is exactly the wrong
system this refuses everywhere else. So the panel path sits inside the `else`,
and inside `returnDronesToBay` with the cascade, since a jump abandons whatever
is in space whichever way it is commanded.

**saxrat's decision root needed no new shape, unlike #133's.** That hoist needed
an always-evaluated head because the thing being placed was a *bound*, and
`anomalyBotDecisionRootBeforeApplyingSettings` is a `Maybe.withDefault` chain
with no head to put one in. This is not a bound: it is a wrapper around one step
of one branch, so it is placed where the cascade already was. Three shape
differences did have to be read rather than assumed, and none of them is
structural: saxrat has no `routeMarkerCascade` function (the cascade is a literal
inside `jumpToNextSystem`, so the fall-back is that expression rather than a
named one), no `dockAtDestinationStation` to sit between them (the no-marker case
is `setRouteToNextHuntingGround`), and `selectedItemButtonNamed` /
`selectedItemIsOverviewEntry` take a `ReadingFromGameClient` rather than a
`BotDecisionContext` -- the divergence `selectedItemIsOverviewEntry`'s own
comment records, because `updateMemoryForNewReadingFromGame` has to ask the same
question and never sees a decision.

**The anomaly warp is not ported, and that is established rather than assumed.**
#170's rule replaces a cascade aimed at an *overview row*; saxrat's `enterAnomaly`
cascades on `anomalyScanResult.uiNode`, a row in the probe scanner window. Two
independent reasons, and either alone settles it. The Selected Item panel acts on
the object selected **in space**, and a scan result is not one -- a cosmic anomaly
has no overview row at all until the ship is in it, which is why the scanner has
its own window with its own Signal/Distance/ID/Name/Group columns (read live: the
overview beside it carried gates, wrecks, rats and a beacon and no anomaly).
`selectedItemIsOverviewEntry` takes an `OverviewWindowEntry`, so a scan result
cannot even be handed to it. And the warp **chooses a distance** -- `to within`
then `Within N km` from the `warp-at` setting -- where the panel offers one
`selectedItemWarpTo` carrying no argument, so pressing it would warp to whatever
default the client holds and silently ignore the setting. `TheWarpHalfIsNot
ServableTest` pins both halves so a later port has to argue against them.

**#171 has no analogue here, which was checked rather than assumed.** saxrat
reads `infoPanelRouteFirstMarkerFromReadingFromGameClient` in three places and
counts the markers in none: the travel leg asks whether one exists, the docked
branch asks whether one exists (`noProbeScanResultsAndNoRouteLastTimeInSpace`),
and the memory update takes the first one's display region for the settling
guard. `routeElementMarker` appears nowhere in `Bot.elm`, so there is no
`destinationIsInThisSystem` here and nothing that could be true a system early.

**Verified without a live client**, in
`tools/macos-host/tests/test_saxrat_route_stargate_panel_jump.py` (60 cases). The
rule is executed through the real `Bot.elm` in `elm repl` at each of its six
answers, asked as six equalities per case so a rule answering two things at once
-- or none -- fails rather than passing on whichever constructor a case named.
The label parse and the panel identity go through the real
`EveOnline.ParseUserInterface` off UI trees, which is also what makes the live
capture above evidence rather than a note. The wordings are **rendered** rather
than asserted by substring over the branch, which is how a case written to catch
a press aimed at the wrong button once passed on the branch's own log text in
`test_saxrat_gate_panel_button`. The wiring is read through a reader sliced by
**indentation**, since `verdict` builds a record and the `let_binding` shape stops
at its opening brace. The corpus is recounted as relations -- the median leg is
large, the cascade holds a large share of the run, and saxrat's legs and share
both dwarf the mission runner's on the same measurement -- plus the doc comment's
own two counts, read back out and recomputed.

**One harness defect had to be fixed to test the live label at all**, and this
file's own fixture is what found it: the shared `reading_binding` dropped
`json.dumps`' output into an Elm `"""…"""` literal, Elm processes backslash
escapes inside one, and a fixture carrying a double quote therefore decoded to
`Nothing`. This client's label is `alt="Next System in Route"` in double quotes
against the 2019 recording's single ones, so it is exactly that fixture. PR #173
worked around it in a local `JumpRepl` and deliberately left the shared helper
alone, since changing it reached eleven other files. **#174 is that sweep and
the real fix**, and the workaround here is gone -- see "A fixture that never
arrived reads exactly like a rule that answered nothing" for what the audit of
the other callers found, which is that no other fixture in the suite was
affected.

Confirmed by mutation, **eighteen** of them, each failing a named case: **the
panel-identity clause dropped, so it jumps while the panel is showing a different
gate** -- the failure this whole design refuses; two gates named for one system no
longer declining; the identity match reading the row's type as well as its name;
the name match weakened to a plain substring; the punctuation normalisation
dropped; the jump button no longer required; the label marker loosened so the
route's *destination* reads as its next hop; the empty-name filter dropped, so a
nameless system matches every gate; the panel path dropped from the travel leg;
the panel identity computed once rather than per row; the virtualised-row filter
dropped; the fall-back waiting instead of handing the caller's own step back; the
press aimed at `selectedItemWarpTo`; a fall-back sentence no longer naming the
route marker; the measured saving in the doc comment changed; a second inline copy
of the stargate predicate; the warp's distance level dropped, which is the shape
that would make it look panel-servable; and `selectedItemIsOverviewEntry`
narrowed to exact equality, which is the mutation the live panel capture catches.

**One mutation survived the first pass and the hole was real.** Telling the rule
`panelOffersJump = True` rather than handing it the lookup left every case
passing: `test_no_jump_button_declines` asks the *rule* directly, so it cannot
see the wiring, and the tuple match below still declines to press without a
button. What it produces is a decision log claiming `Jump through '<system>'
from the selected-item panel` on every reading the panel offers nothing --
exactly the two-places-disagreeing failure `describeRouteStargateJump` is derived
from the verdict to avoid. `test_the_rule_is_told_whether_the_button_is_really_
there` reads that field out of the binding now.

**Unverified: any of it running, and the same two premises #170 shipped open.**
No saxrat run has been flown since. Whether `selectedItemJump` is drawn on a gate
that is *out* of jump range is still unread -- either answer is safe, since drawn
it is the client's own warp-and-jump at the right gate and absent it falls back to
the cascade, which is what flies the ship there. And **whether a multi-jump
route's first marker names the next system** is still unread; nothing in this
change reads the markers, so it matters to #171 rather than to the jump. What is
no longer unverified is the panel's text, read above. What to watch on the first
run that travels a route: `Jump through '<system>' from the selected-item panel,
which is already showing it.` appearing at all, and the route cascade's share of
the run falling from a quarter. A run that jumps gates and prints
`The selected-item panel is not showing the stargate to '<system>'` on every leg
instead means the panel is never found to be showing the gate -- the direction
this fails silently in, and it costs nothing. The one to escalate on is the
opposite: a jump followed by the route panel naming a system nobody asked for.

### The on-arrival pilot check could not fire: the warp-end trigger was dead

Issue #194. saxrat is supposed to leave an anomaly it lands in with somebody
already on the grid, and it never has. The reason is the trigger, and it took
two wrong diagnoses to get to it — both recorded here, because the shape of the
mistake is more reusable than the fix.

`weJustFinishedWarping` was

```elm
(botMemoryBefore.shipWarpingInLastReading == Just True) && (shipIsWarping == Just False)
```

and `shipIsWarping` is a `Maybe` over the manoeuvre the client **names**:
`Just True` for `Warp`, `Just False` for some *other* named manoeuvre — `Orbit`,
`Approach`, `Aligning` — and `Nothing` when the client names none at all. So
`Just False` never meant "the ship is not warping". It meant "the ship is doing
something else with a name". A ship that has simply stopped answers `Nothing`.

**Captured off the live client during run 29**, sampling the ship UI's
indication container about once a second across two warps:

```
while warping   ['Warp Drive Active', 'Destination: AreraDistance: 416 km', 'Mikhir', 'Sansha Hideaway']
warp ends       ['Mikhir', 'Sansha Hideaway']
```

The container is still **present** when the warp ends; it holds only the
location labels. No manoeuvre word, so `maneuverType` is `Nothing`, so
`shipIsWarping` is `Nothing`, so the condition that demanded `Just False` could
not fire at the end of a warp. Two independent warps, identical shape.
`EveOnline.BotFramework.shipUIIndicatesShipIsWarpingOrJumping` already treated
an absent indication as "not manoeuvring", with a comment saying so; this was
the one place that did not.

The rule is now `warpJustEnded`, and it reads three things rather than two:
the previous reading was `Just True`, **the ship UI is present now**, and the
current reading is not `Just True`. The middle one is load-bearing.
`shipWarpingInLastReading` stores the same three-valued answer, and `Nothing` is
equally what a reading with no ship UI at all gives — docked, a client that did
not render, a reading across a session change. A fix written as `/= Just True`
and nothing else calls every one of those an arrival, and the bot takes an
arrival snapshot of a grid it never landed on.

**Two wrong diagnoses came first, and the correction pattern is the point.** The
issue was filed blaming the probe scanner: the snapshot needed
`weJustFinishedWarping` **and** `getCurrentAnomalyIDAsSeenInProbeScanner` on the
same reading, and the scanner was assumed to be late naming the anomaly. Measured
over every warp-end reading in runs 16, 21, 23 and 24, that is false — the
anomaly is named **on** the warp-end reading in 123 of the 123 arrivals that ever
name one, median 0, p90 0, max 0. The second diagnosis was the trigger, from the
source, and it was right but still a hypothesis until a tree was read off the
live client. Neither the code nor the first round of cases had ever executed the
transition, which is exactly how a total defect survived in reachable code: every
case downstream of a condition that is always `False` passes.

**"Arrival" is the landing reading, and the corpus is why.** The distinction the
design already had right is the one the fix has to keep: a neutral *already there
when we land* means leave; a neutral *arriving while we are fighting* means tough
it out. That is why the memory records pilots seen on arrival rather than pilots
seen now, and why reading `getNamesOfOtherPilotsInOverview` on every reading
closes this bug and opens the opposite one. The first attempt at #194 widened
"arrival" to a 30-reading window, to cover the scanner lag that turns out not to
exist. Priced against the same corpus, over 250 arrivals, the number that would
record at least one pilot is

| bound | 0 | 1 | 3 | 10 | 30 |
|---|---:|---:|---:|---:|---:|
| arrivals recording a pilot | 19 | 19 | 20 | 25 | 34 |

Every arrival a wider bound adds is one where the overview held nobody when the
ship landed and somebody afterwards — a pilot who arrived while the bot was
already fighting, which is the one thing this feature must not fire on. At 30
readings nearly half of everything recorded would have been the wrong half. And a
bound of **1** records the same 19 as a bound of 0 across all 250, so the
overview never took an extra reading to draw a pilot who was already on the grid
— the only thing a wider bound could honestly have bought.

So `otherPilotArrivalWindowReadings` is **0**. The window machinery stays: the
counter, the accumulation and the status clause are what make a later widening a
change to one number with an argument beside it, rather than a rewrite of the
rule. `arrivalWindowIsOpen` is still written as `readings <= bound` rather than
`== Just 0` for the same reason, and a case says so.

**The unit is readings**, which is what every other bound in these bots is
counted in — `approachIndicationTrustedForTicks` is 10,
`dockingRunInPatienceReadings` 20, `gateRefusesThisShipTicks` 40 and
`droneRecallGiveUpTicks` 60 — so any future widening is comparable to those
without a conversion done in the reader's head. Confusing this unit with a clock
has cost `stall_watch.py` a threshold calibration twice, #141 a retreat
measurement and #164 an issue's whole diagnosis. In wall-clock terms a reading is
one to eight seconds by this file's own two disagreeing figures, so the 30 that
was first proposed was 30 s to 4 minutes of grid to be wrong about. The counter
is advanced in `updateMemoryForNewReadingFromGame`, which is #102's and #126's
placement rule and the only thing that runs on every reading unconditionally.

**The list accumulates rather than being overwritten, and that is the latch.**
Adding only can never unsay a reason, so the verdict is written during arrival
and untouched afterwards, which is what the do-not-come-back half reads. Order is
first-seen first, because `findReasonToAvoidAnomalyFromMemory` reports the head
and the pilot who was already there is the one an operator wants named. At a
bound of 0 that rule folds over one reading, and it is still the rule: it is what
a widening would rest on.

**Two things #194 offered and this deliberately does not do.** The memory keying
is untouched, and the snapshot still sits inside the branch that has an anomaly
ID to file it under — the issue's other option was to make the snapshot
independent of the scanner, and that is not what shipped. Cases assert both, so a
later change has to argue against them rather than drift into them.

**Nothing about this was visible on a reading before**, which is most of why it
took a corpus sweep to find: a snapshot that never ran and a grid with nobody on
it printed identically. `describeArrivalWindow` separates the three ways the
feature can still be inert —

```
Arrival window: OPEN, 0 of 0 readings since the last warp ended; no anomaly named in the probe scanner, so nothing can be recorded.
Arrival window: closed, 91 of 0 readings since the last warp ended; found on arrival here: Vladimir Barmin.
Arrival window: no warp has finished this session; nobody recorded on arrival here.
```

— and it is read by the status line and by no decision.

**Both apps.** `eve-online-combat-anomaly-bot` carries the same
`otherPilotsFoundOnArrival`, and its `weJustFinishedWarping` had already been
corrected upstream to the `Just True -> not Just True` shape — so its trigger was
**not** dead, which is worth knowing before assuming two copies share a bug. Both
now share `shipWarpingFromReading` and `warpJustEnded`, which also gives the
combat bot the ship-UI-presence guard it lacked and removes a real drift: the two
apps derived `shipIsWarping` inline in two different shapes, a pipeline and a
`case`. Six declarations are byte-identical across the two and a case compares
them rather than merely checking both are present.

**`eve-online-mission-runner` and `eve-online-wingus` carried the dead trigger
too, and that was #205 rather than this change.** Both have it now — wingus in
#233 and the mission runner in #205 — so all four apps carry
`shipWarpingFromReading` and `warpJustEnded` byte for byte, which
`test_wingus_warp_end_trigger.TheFourAppsCarryTheSameWorkingTrigger` compares
rather than leaving to be assumed. Wingus had #194 verbatim: the same
single-reading snapshot on the same unreachable condition. The mission runner
has no arrival snapshot, but the same condition gated its drone abandonment
(`shipLeftThisReading`, whose other half — docking — does work) and #154's
per-warp ammo-swap retry, which is why it was a behaviour change to two live
consumers rather than a third copy of this one — see "The mission runner's warp
half was the dead half, and two consumers were waiting on it" below.

**Verified without a live client**, in
`tools/macos-host/tests/test_arrival_pilot_window.py` (43 cases against **both**
apps, 2 of them reading `~/eve-bot-logs` and skipping where it is absent). The
transition is executed end to end: readings built in the captured shape go
through the real `EveOnline.ParseUserInterface`, and the real `warpJustEnded`
is asked about them in `elm repl`. The condition it replaces is executed on the
same pair and asserted to answer `False`, so restoring the old shape fails with
the reason rather than with an arithmetic mismatch six rules away. The corpus
numbers above are **recomputed** by the cases rather than quoted, per run, so a
machine holding only some of the runs still checks those.

Confirmed by mutation. Beyond the twenty the window carried already: the
`Just False` condition restored, which the captured warp-end reading kills; the
ship-UI-presence guard dropped, which makes an unreadable client an arrival;
`shipWarpingFromReading` reading `ManeuverJump` instead of `ManeuverWarp`; and
the bound returned to 30, which fails the constant's case, the corpus case that
prices it and the boundary either side.

**Unverified: any of it running.** `FoundOtherPilotOnArrival` has still never been
constructed by either bot. What to watch on the first run is the
`Arrival window:` clause. `no warp has finished this session` on every reading
would mean the trigger is still not firing, and is now the one thing that would
say the capture was not representative. `OPEN` on the landing reading with
`no anomaly named in the probe scanner` beside it, on every arrival, would mean
the scanner is later than 123 out of 123 arrivals say and the bound of 0 is
wrong. And `found on arrival here:` naming somebody who warped in mid-fight would
mean the window is not closing, which is the direction this must never fail in.

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
  being empty is the stronger form of that, inferred rather than observed. Since
  #126 the recovery's own 150-reading deadline is asked from the head of the
  decision root rather than from inside the branch, where run 30 would have
  starved it — see "The same bound, asked where a held tree could not starve
  it". A session that ends at N=150 having printed no `Pod recovery:` line is
  the new failure mode and means something above the branch held the tree.

  And it now **stops fighting once the objective carries no instruction and the
  tracker offers any travel step**, instead of clearing the field first — run 11
  spent ten minutes and 386 combat decisions doing that after the mission was
  over, and #49's fix, which acted on the label `Dock` alone, covered 35 of the
  2,379 readings that cost anything. Which labels that covers, why the word is
  no longer part of the condition, and why an unreadable label now fails closed
  on purpose rather than by accident are in "When the objective is done and the
  tracker offers a trip, the fight is over" above. **Untested against a live
  client**; the two pure rules behind it are run through the real `Bot.elm` in
  `elm repl`. Watch for `The objective is complete and the mission tracker says
  'Set Destination'` arriving within a reading or two of the label, rather than
  another stretch of `I see a locked target`.

  And it now **gives back a mission it cannot progress** instead of asking for
  help until the session ends — flies to the agent, quits the mission, refuses
  it for the rest of the session and takes other work. Run 12 raised the same
  alarm 817 times and had to be stopped by hand; run 13 reached the same state
  in 29 readings. The threshold, the bound and what is unverified are in "A
  mission that cannot be progressed is given back, not asked about forever"
  above. Run 30 flew the whole thing for the first time and every piece of it
  worked except the bound: the trip, the dock, the conversation and three clicks
  on Quit Mission are all confirmed live, and the 200-reading deadline ran to
  **10,811** because the comparison sat in a branch the tree was not reaching.
  Since #102 that deadline is asked from the head of the decision root, where
  nothing can decline to ask it — see "A bound counted on every reading and
  tested on a few is not a bound", and the four other bounds named there that
  share the shape. **The abandonment itself is still untested against a live
  client**; only the machinery under it has run.

  And it now **stops answering a message box that will not close**, after
  sixty readings of the ordinary declining answer and another sixty of Escape,
  and lets the rest of the decision tree run with the box still on the screen.
  Run 30 dismissed one window 32,585 times over three hours and forty-four
  minutes and nothing else in the bot ran for any of them, because
  `closeMessageBox` is reached above the docked-or-in-space split — the
  abandonment that was supposed to end that session held a live verdict
  throughout and could not be reached. The ladder, why the count is per box, why
  Escape rather than Ctrl+W, and why narrowing the message-box parser is not the
  fix are in "A message box the answer does not close is bounded" above.
  **Untested against a live client on this bot**, and whether Escape closes such
  a window is still the open question after saxrat run 11 pressed it once (#164)
  — watch the status line's `message box N/120`, which should appear briefly and
  vanish on a healthy run, and which now **names the dialog** so that a standoff
  ending any way other than the give-up still says what the window was.

  And it now **refuses an empty `decline-mission` value instead of arming a
  filter with it**, and says which list refused a mission and on what entry.
  That setting is matched as a substring, so `decline-mission=` put `""` in the
  list and would have handed back every mission the agent ever offered, each one
  a standing hit logged as an ordinary skip; `agent-name`, `drone-type` and —
  until #125 removed it — `avoid-rat` had the same unguarded shape and are
  guarded with it. Why an
  `Err` rather than a silent drop, what the empty value did in each of the four,
  that `avoidRats` turns out to be read nowhere at all, and why no warning for a
  short entry are in "A decline costs standing, so the entry that armed it has
  to be nameable" above. **Untested against a live client**, and the operator
  report the issue was filed on — `Save A Man's Career` declined at a cost in
  standing — remains **unexplained**: nothing in the recordings shows the
  decline branch firing on anything but the two configured missions, and this
  does not claim to fix it. Watch the new clause on the next run that declines:
  it should name an entry an operator recognises.

  And it no longer **advertises `avoid-rat`**, a setting it documented, reported
  through `--help` and parsed into a field no decision ever read. Removed rather
  than implemented; `eve-online-saxrat` and `eve-online-combat-anomaly-bot`
  implement the same setting for real and keep theirs. The one operator-visible
  consequence is that a settings file still carrying the line is now refused with
  `Unknown setting name 'avoid-rat'` instead of ignored — nothing sets it
  anywhere, so no run should meet that. See "A setting this bot documented,
  parsed and never read" above.

  And it now **says when it leaves drones behind** — how many and where, once in
  the decision log and then in the status line for the rest of the session. This
  is issue #59's observation and not its recovery path: the sixteen finished runs
  say abandonment stopped happening at run 1, so there is nothing to recover yet.
  The measurement, the three different things the "seventeen lost drones" turn
  out to be, and the two silent routes out that remain are in "#11 held, and the
  seventeen lost drones were three different things" above. **Untested against a
  live client, and by construction unprovable by a run that goes well**: the line
  only appears when the thing it watches for happens, so a quiet run is not
  evidence the instrument works.

  And it now **stops shooting an object whose every landed shot does zero
  damage**, unlocks it and leaves it alone for the rest of the session. Run 27
  shot an `Infested Asteroid` for roughly 290 consecutive readings with the
  objective already finished, and no field in any reading could say so — the
  host summed only the incoming half of the combat channel. The third synthetic
  node, the threshold and its calibration, and why a `never-attack` setting
  would not have helped are in "What the bot gives up on: shots that land and
  achieve nothing" above. **Untested against a live client**, though the rule is
  executed through the real `Bot.elm` and the threshold is checked against the
  client's own recorded lines. What to watch first is the status line's `shots
  landing for zero:` clause appearing at all on a run that fights; a run where it
  never does means the outgoing summary is not reaching the bot, which is the
  direction this whole change would fail silently in.

  And its status line now **says what condition the active target is in** —
  `target Render Alvi (Shield: 58%  Armor: 100%  Hull: 100%)` — where it named
  the target and said nothing else, on the 7,917 readings of run 27 that name
  one. It is a parse rather than the hover #112 was framed around: the client
  draws `shieldBar`, `armorBar` and `hullBar` as named containers under every
  `TargetInBar`, so there is an answer on every reading and no competition with
  the ammo swap's own weapon hover. The bars are a *ring* and carry no width to
  take a ratio of — the value is the client's own `lastState` — which is the one
  thing here that had to be measured rather than assumed; see "The status line
  named the target and said nothing about its condition" above, including why an
  unreadable bar prints `unknown` and never `0%`, and why nothing decides
  anything on it yet. **Untested against a live client**, though the geometry and
  the values were read off one. Watch for the three numbers *moving* while the
  guns fire; a run that names targets and prints `(Shield/Armor/Hull unknown)` on
  every one of them means the containers are not where this reading found them.

  And since #157 its ammo swap **stops reading the disarm budget as a statement
  about the guns, and retries after a warp.** Run 11 latched the whole feature
  off 21 readings into an attempt on the sentence "the guns were switched off to
  load and were still not back 21 readings later", while its own module column
  read `isInActiveState` `T` — the gun switched on — from reading 3 of that
  attempt; the ship was disarmed for two readings. Run 27 is the same shape with
  the bot saying so in words. Those are the only two disarm give-ups in 37 runs
  and **both are the misreading**, where saxrat's split was two in three. The
  budget is right to consult nothing the module says (#34) and that is exactly
  why it cannot say what the guns were doing; the *session* consequence now asks
  the client's own latched answer, the attempt is still abandoned at the same
  reading, and the disarm verdict is retried on the next warp. The third latch,
  #106's "no crossover", is deliberately **not** retried — that ask already
  spends one hover per warp, so clearing the verdict would re-latch on the same
  reading. See "The disarm budget bounds an attempt, and it was read as a
  statement about the guns" above for the census, including why runs 34 and 35
  reaching the budget one reading short of the give-up is what makes this narrow
  the latch rather than remove it. **Untested against a live client.** Watch for
  the give-up saying `off until the next warp` and then going away on the next
  warp.

  And it now **acts on a hitpoint reading only once a second reading agrees**,
  rather than on whatever the gauge said this reading. Run 11 retreated forty
  printed decisions on `Armor reached 0%` with the armour at 82-96%, which is a
  single corrupt read that `plausibleHitpointsPercent` cannot reject because `0`
  is a legal percentage. The rule, what it costs and what it deliberately does
  not consult are in "Retreating: the HUD hitpoint gauge is the weakest
  instrument here" above. **Untested against a live client**, though what it has
  to reject is replayed from run 11's own 739 readings through the real
  `Bot.elm`. Watch the status line for a withheld reading naming what the
  retreat is going by instead, and for `Readings withheld from the retreat this
  session` climbing: a couple over a run is the gauge behaving as recorded, a
  count climbing every few readings is a gauge that has started lying properly
  and a different problem.

  And it now **says when nothing is watching for the ship being ground down**,
  and reports the retreat's own low-water marks. Run 36 walked from 95% to 17%
  armour while `run-away-incoming-damage-threshold` peaked at 1854 of 3500 — its
  highest reading all run, taken while the ship was still healthy — and survived
  only because the armour percentage threshold was set. **No guard was added**:
  the honest reading of the corpus is that the percentage guards already are the
  attrition guard and that no gauge-free instrument could be one, since the
  combat log reports gross damage while survival is governed by net. See "The
  three guards are independent, and the independence is asymmetric" for the
  measurement, for the time-to-death guard that was measured and deliberately not
  built, and for the settings advice this corrects — `Bot.elm` was telling
  operators to set the *shield* threshold on a hull whose shield rests at 0%.
  **Untested against a live client.** Watch for `Retreat marks:` on every
  in-space reading, and for `ATTRITION UNGUARDED` appearing only on a run started
  without `run_mission.sh`.

  And it now **says how long it has been trying to leave**. Run 36's guard fired
  correctly at 66% armour and the ship reached 17% while the retreat could not
  execute, and nothing recorded that interval — it had to be counted by hand out
  of a log. `retreatProgressAfterReading` counts consecutive readings on which
  the retreat is decided and the ship is not in warp, which is narrower than
  "readings the retreat was decided" for a reason the hysteresis makes
  load-bearing. **No behaviour changed**: the drone recall still sits in front of
  the warp and its give-up bound is still 60, because the corpus says the recall
  is a fifth of retreat latency and none of it in the longest retreats outside
  run 36 — see "Deciding to leave is not leaving, and nothing measured the gap"
  for the 29 episodes this was measured over and for why the focus-recovery click
  was left alone too. **Untested against a live client**, and nothing here
  shortens a retreat by one reading. Watch for `RETREAT NOT EXECUTING: N`
  appearing and then going away within a few readings; a worst that reaches
  double figures is run 36's shape recurring, and it is the first evidence anyone
  will have had.

  And since #141 it **asks for a person when that interval reaches 36 readings**,
  once, in a line carrying the sentence `stall_watch.py` answers by screenshotting
  the client — and goes on commanding the warp while it does, because the bot is
  the only thing still trying and ending the session would leave a ship under fire
  with nobody at the controls. Why there is no mechanical escalation to take
  instead, and what recounting the corpus in readings rather than in decision
  blocks says about run 36 — that its warp did take, that its 1% armour is one
  corrupt reading, and that run 10 did the same thing at the same length — are in
  "The unit was the problem, and in readings run 36 is not an outlier" above.
  **Untested against a live client, and it does not make a warp take**: run 36
  replayed today would go exactly as it did, with one line more in its log. Watch
  the status line's `RETREAT NOT EXECUTING: N of 36`; a run that reaches 36 is the
  first live instance of that shape, and the screenshot taken on that reading is
  the evidence a repair would need.

  And it now **leaves a dock it has already commanded alone** instead of
  re-issuing it every reading. Docking is a run-in the ship has to fly, and run
  27 spent 486 seconds — the run-in's own length — commanding Dock on 120 of 121
  consecutive readings and never arriving. The client's own `Setting course to
  docking perimeter` is what says a run-in is under way, a falling range to the
  station is what says it is working, and the dock itself now goes through the
  Selected Item panel's `selectedItemDock` where the panel offers it. The two
  halves, why the jump leg is unaffected, and what bounds the wait are in
  "Docking is a run-in the ship has to fly" above. **Untested against a live
  client**, and two of its premises are unread — watch the status line's
  `docking run-in (N course-setting(s), …)` for N staying at 1 while the range
  falls.

  And it now **asks the host to set its route through ESI** rather than driving
  the search bar, which is the only way it can originate a destination carrying a
  character it cannot type — `Amarr VIII (Oris) - Emperor Family Academy` has
  both a parenthesis, which has no key at all, and a hyphen, which maps to a
  virtual key the host cannot press. The directive, the choice between the two
  mechanisms and the evidence that a route is the bot's own are in "The home
  station" and in the ESI bullet below. **Untested against a live client, and
  deliberately not fired**: setting a destination is an outward action on a live
  account and a session was running. What to watch on the first run is
  `@host set-destination '<station>'` in the decision log, then the host's
  `# the bot asked for the route to …` and `# ESI: destination … set (N)` on
  stderr, then the client's route panel flipping from `No Destination` — and then
  `Home station: travelling to` taking over, which is the bot accepting the route
  as its own. Three readings of the ask followed by `Search for '<tail>'` is the
  fallback firing, which means the host did not set the route and its own log
  says why.

  And it now **knows whether it has read a briefing at all**, rather than
  treating a session that has never seen one as a session whose briefing said
  "clear the pocket". Run 32 spent 784 readings fighting the one mission whose
  briefing says in writing that the pirates need not be cleared, because it was
  cycled onto that mission mid-flight and never opened an agent conversation.
  The verdict is now one entry per mission rather than one `Bool` per session,
  filed under the briefing's own mission name; which direction the unknown fails
  in, and why it is still "clear the field", are in "A briefing nobody read is
  not a briefing that said clear them" above. **Untested against a live client**,
  and the behaviour on the unknown is deliberately unchanged — what changes is
  that the status line now carries `clearing '<mission>':` on every reading a
  mission is tracked, saying which of the four cases the bot is in. A run that
  never prints that clause is the one to look into.

  And it now **works out how big the ship it is flying is, and scales the
  damage-rate retreat to it**, instead of comparing every hull against a number
  measured on one. `run-away-incoming-damage-threshold` is 3500 because that is
  where a battlecruiser's recorded sessions separate, and moving to a battleship
  changes the tank by a large multiple in one step. The client states both
  halves of the arithmetic — the combat log says how much damage arrived and the
  gauge says how many percentage points it moved — so the session divides them,
  many times, and takes the lower quartile. Why the shield gauge and not the
  armour one, why the observation is paired with the *previous* reading's
  damage, what makes one admissible, and why the ammo swap's disarm budget
  deliberately does not inherit the scaling are in "The threshold is a number
  about one hull, and the session works out which hull" above. **Untested
  against a live client**, though the whole derivation is replayed through the
  real `Bot.elm` and every number in it is recomputed from `~/eve-bot-logs`.
  Watch the status line's `Ship scale:` clause: `0/6 observations` on a quiet
  run, then `shield reads N hitpoints` with N near 1900 on this hull. A run that
  fights hard and stays at `0/6` means the shield is not the gauge taking the
  damage.

  And it now **prints the client's transient centre-screen popup** rather than
  parsing it into a string and throwing it away, which is what has happened on
  every reading of every recorded run since this app was added. Nothing decides
  anything on it and a case asserts so: no wording has ever been captured, so a
  matcher would rest on guessed strings, which is #92's trap. The clause, why it
  carries the last message forward with an age instead of reporting only the
  live value, and the two places the parser's head-only read drops a message are
  in "The client's transient popup was parsed on every reading and read by
  nothing" above. **Untested against a live client, and the run is the point** —
  watch for `Quick message:` on every reading, then a quoted string with
  `(on screen now)` the first time the client shows one.

  And since #146 it **reads one of those popups**: the client's refusal to launch
  more drones than the pilot's skill allows, which caps the launch site at the
  number the client names instead of at the drones window's own maximum. Run 37
  pressed Shift+F into that refusal on 101 readings and saxrat's run 6 on 1,316,
  the drones window offering more while three drones sat in the bay. Why the rule
  is per message rather than "a quick message means failure", why it declines
  `Cargo is too far away. Ship is on automatic approach to cargo.` (the commonest
  message in either bot, and a *success*), and how it is kept off #110's
  near-identical targeting sentence are in "The client names the drone cap the
  drones window does not" above. **Untested against a live client**; watch the
  status line's `Drone launch ceiling: N (drones window says M, client stated -)`
  for `client stated` filling in within a reading or two of the first refusal, and
  then the refusal not recurring.

  And it now **learns how many targets the ship can hold** rather than carrying
  a hardcoded `maxTargetCount = 4` no setting could reach, against a client that
  states its own maximum of **6** on the game log 228 distinct times across the
  recorded corpus. The floor is the target bar, which needs no attribution at
  all; the ceiling is the client's own sentence, which is not a constant even
  for one character. See "The lock-slot ceiling is stated by the client, not
  hardcoded" above for the drone refusal it must not be confused with, and for
  why absent evidence must never raise it. **Untested against a live client**,
  and why six targets were held while the bot's own ceiling was four is still
  unexplained — watch the status line's `Max targets:` clause for
  `client stated 6` arriving within a reading or two of the first refusal.

  And since #150 it **asks for one more than it believes in** until the client
  states that number, because neither half of that rule could move on its own:
  the floor cannot rise past the ceiling when the ceiling is what the bot asks
  for, and the client writes its sentence only for a lock beyond the cap. The
  probe is one extra row rather than a different one, is only taken from rows
  the ship can already lock, and is discharged from the lock-range machinery
  rather than spending its budget — which fixed a defect of its own, since a
  declined lock used to latch at the verdict count on thousands of recorded
  readings while the give-up written for it never once fired. See "Neither half
  could move on its own, so the bot asks for one more" above. **Untested against
  a live client**; watch `probing for 5` in the status line and then
  `Probing for lock slot 5:` in the decision log.

  And it now **flies to a station it knows has an agent** when the one it is
  standing in has none, instead of asking for help there until somebody
  notices. Run 35 raised that alarm on 371 readings with `home-station` in its
  settings the whole time. The docking itself was correct and the issue's
  suspicion of it is answered against — the mission was a courier delivering to
  another agent's station, and the tracker's own travel steps took it there — so
  what is new is only the two steps before the undock; run 35 flew the rest of
  the trip unaided once a person had undocked it. The trip drops the station the
  info panel says the ship is already in, refuses when the panel cannot name it,
  and must fit before the wind-down starts. See "A station with no agent in it is
  a place to leave, not a reason to stop" above, including the recount that puts
  the stall at 1,064 readings rather than the issue's 12,800. **Untested against
  a live client**; watch for `No agent here to take a mission from -- set the
  route to '<station>' before undocking.` followed by an undock, and note that
  whether those stations really had no agent is still unknown.

  And it now **jumps the route's next stargate from the Selected Item panel**
  where that panel is already showing that gate, instead of right-clicking the
  route panel's 8x8 marker — the cascade whose own comment records "3-4 menu
  opens before being recognized" and which carries a widened tolerance because of
  it. `selectedItemJump` is read off a live client with a **stargate** selected;
  two earlier readings concluded the button does not exist and both were taken
  with an *acceleration* gate selected, which draws a different button set. The
  identity — which is the whole safety of it, since a jump to the wrong gate is a
  wrong system — is a name match between the route panel's own `Next System in
  Route` label and the overview row's Name column, neither of which anything had
  read; the marker itself still carries no name. See "The route panel names the
  next system, so the panel can jump the right gate" above for why only the Name
  column is matched, for the **one to two readings** this actually saves, and for
  the finding it turned up about `dockAtDestinationStation`'s marker count that is
  deliberately not fixed here. **Untested against a live client**, and the panel's
  texts with a stargate selected have never been recorded; watch for `Jump through
  '<system>' from the selected-item panel` appearing at all.

  And it now **asks the client for up to three locks in one step**, which is
  #177's saxrat change ported into the bot that PR left a marker in. The design
  is not re-derived: the first lock of an engagement is still asked **alone** and
  a batched reading teaches the lock-range rule nothing, which costs nothing
  because `lockAttemptCanTeachRange` already discharges an attempt begun with the
  bar occupied. **The finding is a unit.** The port's first draft measured the
  ramp in `# [tick.substep]` integers and reported a gain a third of the real
  one; a tick is not a reading, run 35 carries 6,573 of the first against 8,191
  memory reads, and recounted properly this bot dispatched 2,833 lock commands a
  median of **2** readings apart with 81% of them inside a run of consecutive
  locks — the same shape as saxrat rather than a smaller one. The cap is
  re-measured here and still lands on 3, and the one rule this bot needed that
  saxrat did not is the in-range **prefix**, since `everythingWorthAttacking`
  sorts a scrambler to the front ahead of the distance order and a batch built by
  filtering would skip it. See "The mission runner batches too, and the gain had
  been counted in the wrong unit" above. **Untested against a live client**, and
  whether EVE takes several Ctrl+clicks in one burst is still not established;
  watch `Lock batch: ... asked N and the bar answered N` with the two numbers
  tracking each other.
- **`eve-online-saxrat`** now carries the general guards the mission runner
  learned — the confirmed hitpoint readings behind a low-water mark, the
  damage-rate retreat, ship-loss detection and pod recovery, a bounded drone
  recall, and shooting back at whatever the client's combat log names. See
  "What saxrat has of this, and what it does not" for the table, for the
  recall's own failure (which was worse than #11's), and for the one rule that
  is deliberately not identical. **None of it has been run against a live
  client**: 36 cases execute the ported rules through the real `Bot.elm` in
  `elm repl` and the app compiles, which is the same standing as every other
  entry here that says "untested against a live client". The first run to watch
  it on should show `dmg N/3500 (45s, Nrd)` and `Drones: ... unanswered recall
  N/60` on every status line — a `NO COMBAT LOG` there instead means the
  damage retreat is unarmed and the two gauge thresholds, which ship at `-1`,
  are again the only guards.

  It also carries the mission runner's quick-message clause, identically: the
  rules are the same declarations under the same names and a case compares them
  byte for byte, while the line each is placed in follows each app's own status
  conventions. Since #146 that includes the **drone-launch cap read off one of
  those popups**, and this is the bot the corpus indicts: run 6 pressed Shift+F
  826 times with three drones in the bay and five in space, and was refused on
  1,316 readings — a quarter of every live quick message ever recorded from either
  bot. The rule is identical in both apps and a case compares all ten shared
  declarations byte for byte. **Untested against a live client**; watch
  `Drone launch ceiling:` in the status line.

  And it now **swaps ammo**, which it could not do at all — the capability was
  absent rather than unconfigured, with `ammoSwap` appearing 165 times in the
  mission runner and 0 times here. The port leaves the tooltip half behind and
  makes `ammo-swap-range` required rather than optional, which is what turns that
  into a simplification: the mission runner only ever hovers a module when the
  setting is *unset*, so requiring it makes the whole fragile half unreachable.
  What the swap's own safety needed — the game-log refusal matcher under the
  trust rule, the disarm budget on the operator's own setting — came across
  whole. See "saxrat swaps ammo at a distance it is told, not one it works out"
  for the argument, for the one rule that is new rather than moved (the
  stray-menu guard, which would otherwise close the menu the load is clicked out
  of), and for issue #122's own premise about this bot's warps, which the
  recordings contradict without changing the answer. **It has flown**, and the
  stray-menu guard that section names as the thing most likely to be wrong is
  right — it suppressed itself correctly through every swap in run 10.

  And since #154 it **stops reading the disarm budget as a statement about the
  guns, and retries after a warp.** Run 10 latched the whole feature off 21
  readings into a three-hour session on the sentence "the guns were switched off
  to load and were still not back 21 readings later" — while its own status line
  had read `a gun has been switched back on ... the guns are firing` for the
  previous seventeen readings, the client having taken the guns back at reading
  4. The ship was disarmed for three readings. The budget is right to consult
  nothing the module says (#34) and that is exactly why it cannot say what the
  guns were doing; the *session* consequence now asks the client's own latched
  answer, the attempt is still abandoned at the same reading, and the disarm
  verdict is retried on the next warp rather than ending the run. See "The
  disarm budget bounds an attempt, and it was read as a statement about the
  guns" above, including which of the three recorded give-ups was genuine and
  why run 8 — 2,712 `(satisfied)` prints and no give-up at all — is the control
  that makes ending the feature on one bad reading expensive. **Untested against
  a live client.** Watch for the give-up saying `off until the next warp` and
  then going away on the next warp.

  Its status line now **says what condition the active target is in** too —
  `Current target: Render Alvi (Shield: 58%  Armor: 100%  Hull: 100%).` — and
  this is the one place where the port needed no thought at all: `parseTarget`
  and the `Target` alias were byte-identical in the two apps before this and are
  again after it, so the parse and both rules are the same declarations under the
  same names and a case compares them byte for byte. Only the sentence each is
  placed in differs. See "The status line named the target and said nothing about
  its condition" above. **Untested against a live client**, and no recorded
  saxrat run has ever printed a target's condition; watch for the three numbers
  moving while the guns fire.

  And it now **learns its lock range from the client** rather than carrying
  `targeting-range=66000` and never revising it — the setting clamped into
  `[proven, refused)` from what the client has actually granted, with the
  row-identity discipline carried across unchanged and compared byte for byte
  against the mission runner's. See "The lock range is learned here too" above
  for what saxrat changes about it, for the Ctrl chord premise that is not true
  here, and for why the "no evidence" branch is the ordinary case in an anomaly.
  saxrat's diverged parser needed **no change**: it already exposes
  `objectItemID`, the lock indicators and the per-row region. **Untested against
  a live client**, and the open question is whether anomaly rats carry `itemID`s
  at all — watch the status line's `Lock range:` clause, where `attempt none` on
  every reading of a fight means the identity rule is declining to attribute,
  which is correct rather than broken.

  And it now **learns how many rats it may hold locked at once**, which cost it
  more than the mission runner: `maxTargetCount = 4` stopped it on **2,149
  readings** across runs 2 to 5, printing `Enough locked targets.` while the
  client was stating a maximum of 6 on a channel the bot already read. Both
  apps got the same rule and both parsers needed **no change**. The half that
  matters here is the target bar, because it needs no row identity — an anomaly
  is a pocket of identically named rats, so the lock range's attribution rule
  correctly yields nothing there while this one answers on every reading. See
  "The lock-slot ceiling is stated by the client, not hardcoded" above.
  **Untested against a live client**; watch `Max targets:` in the status line
  and `Enough locked targets.` becoming rarer once it moves.

  And since #150 it **asks for one more than it believes in** until the client
  states that number, which took a second fix here that its own gate had hidden:
  saxrat's candidate window was `List.take 4`, the shipped ceiling written out
  again, so a client stating six left two slots unreachable however far the gate
  was raised. Both are the learned count now, and `Enough locked targets.` never
  fires while the question is still open — the bot has one more to ask for. See
  "Neither half could move on its own, so the bot asks for one more" above.
  **Untested against a live client**; watch `probing for 5` in the status line
  and the number climbing before `client stated` fills in.

  And since #177 it **asks the client for up to three locks in one step**
  instead of one per decision cycle — run 16 dispatched 490 lock commands a
  median of two readings apart, which with a six-slot bar is most of the opening
  of every engagement. The framework was never the constraint:
  `effectsOnGameClient` is an unbounded list that becomes one
  `WindowsInputRequest`, and the corpus already holds a 12.9 s step carrying a
  click and a whole typed name. What had to be arranged is the attribution, and
  the arrangement is that the two rules are disjoint by construction: the first
  lock of an engagement is still asked **alone**, because
  `lockAttemptCanTeachRange` means a lock asked with the bar occupied could never
  have taught either bound anyway — so a batched reading teaches the range rule
  nothing and gives up nothing. A dropped click is silent (#163), so
  `updateLockBatchAccounting` writes down what was asked for and reads the bar
  back. See "Several locks in one step, and the first one still asked alone"
  above for the 4.68 s longest recorded input step that sizes the cap. The
  mission runner shared the defect and was untouched by that change; it has
  since taken the port, so the marker recording the gap is spent — see "The
  mission runner batches too, and the gain had been counted in the wrong unit".
  **Untested against a live client, and whether EVE takes several Ctrl+clicks in
  one burst is not established**; watch `Lock batch: ... asked N and the bar
  answered N` with the two numbers tracking each other.

  And it now **asks the pod recovery's deadline where nothing can decline to ask
  it**, which is #126 in this second bot: the comparison over
  `podRecoveryGiveUpReadings` sat inside `recoverPodAfterShipLoss`, below
  `generalSetupInUserInterface`, while the counter it reads advanced on every
  reading regardless. It mattered more here than there when it landed, because
  saxrat then had no message-box standoff at all, so the three-hour hold that
  starved run 30 was unguarded in a bot that rats unattended. What differs from
  #132, and it is the docked outcome rather than the deadline, is in "The same
  bound in saxrat, hoisted above the same starvation" above. **Untested against a
  live client**, and more thoroughly so than most: no saxrat run has ever latched
  a ship-loss verdict, so neither the recovery nor its bound has ever run here.

  And it now **stops answering a message box that will not close**, after sixty
  readings of the ordinary declining answer and another sixty of Escape, and
  lets the rest of the decision tree run with the box still on the screen. This
  is #109 ported whole (#138): saxrat's `closeMessageBox` clicked its dismissal
  every reading for as long as a box was showing and counted nothing, while
  meeting the same client through the same parser filter — and unattended, so
  nobody would have seen the 32,585 identical lines run 30 produced. **The
  bound's size is the mission runner's measurement, not saxrat's**: the three
  recorded saxrat runs hold 49,235 readings and not one message box, which is
  checked rather than remembered. saxrat's diverged parser needed **no change**
  — it already exposes the button `_name`s and labels the identity needs — and
  Escape is safe here for the same placement reason, `closeSystemSettingsMenu`
  being the entry before this one in a list resolved by `List.head`. See "The
  message box that will not close is bounded here too" above.

  **It has flown, and run 11 is the first box either bot has met since.** The
  counter advanced once per reading up the answering rung and the escalation
  pressed Escape once; what looked like a frozen counter is the client going away
  at EVE's downtime, taking every other counter in the same status line with it.
  Since #164 the clause **names the dialog** on every counted reading, because
  that run's 125 MB log cannot say what the window was. See "The ladder is not
  what froze; the readings stopped coming back". Watch `Message box: N/120` with
  the dialog named beside it, appearing briefly and vanishing on a healthy run.

  And it now **presses the Selected Item panel's own `selectedItemActivateGate`**
  on a gate the ship is already sitting on, rather than driving a context-menu
  cascade at it — the mechanism the mission runner verified live on a gate that
  had refused 124 D-clicks. Before this, `Bot.elm` named `selectedItem` zero
  times: it had never pressed a panel button for anything. The out-of-range
  branch is deliberately unchanged, since the panel carries that button only
  while the gate is in range. **The give-up's counter is the other half and is
  the finding**: it counted readings *near* a gate, so run 5 took it to 3,504
  while the opportunity-warp branch held the tree and the gate was asked three
  times, and 829 give-up lines across two runs turn out to be two gates rather
  than 829 failures. See "An in-range acceleration gate is opened from the panel
  here too" above for the recount, for why the bound stays at 40, and for the
  give-up that no longer claims the gate "will not admit this ship" on a reading
  where the client said nothing. **Untested against a live client**; watch
  `Readings spent asking an acceleration gate to open: N of 40` with
  `(asking now)` beside it and N staying in single figures.

  And since #147 it **works that gate before warping to a site again**, which is
  what makes the branch above reachable at all: the "Warp to Site" search
  outranked it and answers `Just` while the button is drawn, which the panel goes
  on doing after arrival, so run 5 spent 3,458 readings — 75 minutes — clicking
  one screen position beside a gate it never asked, and was freed by a person.
  The grid is what separates "an opportunity exists" from "we are not there yet",
  since the client never answered one of those clicks; so the gate is asked first
  **and** a site offered while a gate is in reach is declined. The give-up now
  hands the reading back rather than parking the session, which is what stops the
  new ordering shadowing the warp branch in turn. See "The gate is worked before
  the site is warped to again" above, including the bound's replaced argument —
  40 survives, on the mission runner's corpus rather than on saxrat's shadowed
  peaks. **Untested against a live client**, and run 6 met neither a gate nor an
  opportunity in ten hours; watch the opportunity-warp line falling to roughly
  the number of sites entered with gate decisions rising to meet it.

  And since #169 it **jumps the route's next stargate from the Selected Item
  panel** where that panel is already showing that gate, instead of right-clicking
  the route panel's 8x8 marker. This is PR #170's rule ported whole, and what
  makes it worth more here than there is the **share**: counted in readings, the
  route cascade holds 400 of run 13's 1,706 and 348 of run 14's 910 across 27 and
  26 jump legs — a median of 12 and 13 readings a leg and roughly a quarter and a
  third of the whole run, against the mission runner's 3 and 2 and its 2% and 3%.
  The identity that makes it safe is unchanged and is the whole of it, since a
  jump to the wrong gate is a wrong system. Two things this port settles that
  #170 could not: the Selected Item panel's *text* with a stargate selected, read
  live (`nameLabel 'Tar (…0.8…)'` beside an overview row named `Tar`), and that
  the anomaly warp is **not** servable by the panel — it acts on a probe-scanner
  scan result rather than an object in space, and picks a distance the panel's
  single `selectedItemWarpTo` cannot express. See "The route's next stargate is
  jumped from the panel here too, and the share is why" above, including why the
  panel path sits *behind* the route-settling guard. **Untested against a live
  client**; watch for `Jump through '<system>' from the selected-item panel`
  appearing at all, and the cascade's share of the run falling from a quarter.

  And since #190 it **no longer reprints the client's combat widget into the
  status text on every reading**, which was the largest single thing in its log
  and almost none of its information: a third of runs 20 and 21, with 1,376 of
  run 20's 1,377 feed blocks byte-identical to the block before them and 1,344 of
  them printed on readings whose own decision line says the ship is docked.
  **Nothing replaces it** — the incoming half of that channel is already in the
  status line on every reading as `describeIncomingDamage`, summed host-side and
  scoped to the reading, where the widget retains messages and outlives the
  fight. `visibleCombatMessages` is kept unused under the mission runner's own
  `combatFeedIsReportedByTheHostGameLog` marker, so the two bots read alike here.
  See "The combat feed was a third of the log and none of it was new" above.
  **No behaviour changed**: the clause was read by the status line at one site
  and by no decision. What a run shows is negative — `Combat feed` gone and
  `dmg N/T (45s, Nrd)` exactly as before.

  And since #194 it **can leave an anomaly somebody was already sitting in**,
  which it never could: the arrival snapshot needed `weJustFinishedWarping` and
  the probe scanner naming the anomaly on the *same* reading, and the scanner is
  late, so `FoundOtherPilotOnArrival` has never been constructed in a recorded
  run. "Arrival" is a bounded window after warp ends now — 30 readings, the
  same unit as every other bound in these bots — and the
  window's *closing* is the half that matters, since a neutral arriving
  mid-fight must still be fought rather than fled. See "The on-arrival pilot
  check could not fire, so 'arrival' is a window now" above for why the list
  accumulates rather than being overwritten, and for the one premise this
  inherits rather than fixes. **Untested against a live client**, and this path
  has never run at all; watch the status line's `Arrival window:` clause going
  `OPEN` after each warp and then `closed`, and escalate on a pilot named there
  who warped in during a fight.
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

  **The bot reaches it through the status text, not through the request.**
  Issuing a `RequestToVolatileProcess` from a decision is still impossible (see
  the Architecture section), so the mission runner writes
  `@host set-destination <full station name>` as a decision line instead and
  `run_bot` calls the same `_set_autopilot_destination` the request answers with.
  One code path, so the two ways in cannot report a failure differently. The host
  acts only when the name *changes* and forgets the name when the ask goes away,
  so a standing ask is one authenticated call rather than one per tick, and the
  same station asked for again later is acted on again.

  **Which mechanism the bot uses, and what happens when ESI cannot.** ESI is
  preferred while `route-by-esi` is on (the default) and the search-bar sequence
  has not already started; after `esiRouteReadingsBeforeSearchBar` (3) readings
  in which the bot dispatched nothing and no route appeared, it falls through to
  the search bar, which is untouched. So a host with no ESI credentials, or
  BotLab.exe, costs three readings per route and then behaves exactly as before.
  A failure is loud in the host's log (`# ESI: destination … not set: …`) and
  attempted once per distinct destination.

  **No route has yet been set this way.** The plumbing and its unit tests are
  merged; nothing has travelled the full path from a bot decision to a real
  route change, because firing one is an outward action on a live account.
- **EVE's own game log reaches the bot**, as
  `ParsedUserInterface.gameLogEntriesSinceLastReading` — the refusals behind
  issues #14, #19 and #27, which those features each had to infer indirectly
  from something failing to change. The shape, the safety properties and the
  vendoring policy are in the Architecture section.

  **Verified without a live client, and that is most of what a live client
  would have added.** 58 unit tests in
  `tools/macos-host/tests/test_game_log_channel.py` cover the tail, the
  filtering, the node, `_read_from_window` and #124's wrapped entries,
  replaying the real lines the host echoed during the recorded runs — including
  a check that every one of those 64,000-odd recorded lines is read, as an
  entry or as the rest of the one above it, and that folding the wrapped ones
  leaves every other entry and both damage summaries exactly as they were.
  Confirmed by mutation, eleven of them, each failing a named case: the tail
  dropping continuations again (the revert), the pure fold dropping them,
  folding only the first continuation (hard-coding two lines), a continuation
  becoming an entry of its own, joining with no separator, prepending instead
  of appending, the open entry surviving a file change or surviving being
  handed to a reading, the tail folding only within one poll, the echo joining
  too, and a continuation recognised by its wording rather than by its
  position. The Elm half was driven end to end
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

  And it carries **what this ship's own shots achieved, per target**, as
  `outgoingDamageSinceLastReading` — the other half of the same channel, and the
  instrument run 27 did not have. See "What the bot gives up on: shots that land
  and achieve nothing". Verified without a live client: 46 unit tests in
  `tools/macos-host/tests/test_zero_damage_target.py`, with the accumulation
  rule executed through the real `Bot.elm` rather than restated in Python and
  the threshold recounted from the client's own outgoing damage lines — as
  *relations* since #158, because the disjointness #90 asserted is what a
  growing corpus turned red. The sessions carrying that overlap are themselves
  folded into readings and run through the rule, with their damage stripped out
  beside them as the control: same target, same readings, and the rule gives up
  on the second.

  **Five consumers now, and none has been proven live.** #31's ammo-load
  refusal (`loadRefusedByClient`), #33's capsule refusal (`shipLossFromGameLog`),
  #41's locked acceleration gate (`gateLockedForWantOfAnItem`), #32's
  damage-rate retreat and #90's zero-damage verdict, the last two reading a
  summary rather than the lines. All five take the same three parts a consumer
  needs: a
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

`eve-online-mission-runner`'s `routeToStationByName` is this sequence in Elm, and
`routeToStation` is what chooses between it and the ESI ask. It is the fallback
rather than the mechanism since #69, but it is still the only one that works with
no credentials and from a cold start, so the substring workaround stays
load-bearing — see "The home station".

### The query is not mangled where it looked like it was

Issue #75 read run 19's search-results window off the live client while it was
still open — `ListWindow noContentHint 'No results returned for "eueu"'` against
a decision log reading `Search for 'Emperor Family Bureau'` — and named three
places the characters could be lost: `effectsToEnterString`, `_VK_TO_CGKEYCODE`,
and `cg_input`. **Two of the three do not lose anything, and the first is not in
the path at all.**

**`effectsToEnterString` is called by no bot.** It appears in all nine vendored
copies of `Common/EffectOnWindow.elm` and in zero `Bot.elm`s. The search bar is
typed by the mission runner's own `typeTextEffects`, which emits one
`KeyDown`/`KeyUp` pair per character and **presses no modifier at all** — so the
shift-state tracking the issue points at never runs, and neither does
`getKeyboardKeyToEnterChar`.

**The table is right and the host posts every character.** Driving the real
`_windows_input` over the real sequence shape — click, 21 characters, Return —
posts 44 key events in order, every one decoding back to the query, with no
errors and nothing aborted; and the table agrees with the standard US-layout
`kVK_ANSI_*` constants character by character.

**Pacing is not implicated either, and the timings say so from the runs
themselves.** A 22-character query costs 6.7s in run 35 and 11.1s in run 17 —
but the same runs' *glides* separate the same way, and a glide is ten posted
`move` commands plus nine fixed 25ms sleeps, so its duration measures what one
posted event costs. Across the corpus that separation is total and has no
overlap:

| runs | every logged glide |
|---|---|
| **17 and 19** — the two that lost the query | 0.759 – 1.222 s |
| 27, 29, 30, 31, 34, 35, 36, 37 | 0.232 – 0.401 s |

A glide's own sleeps are 0.225s of that, so a posted event cost **53–100 ms in
runs 17 and 19 and under 18 ms in every other recorded run**. Both runs were
therefore flying the shipped 30ms hold and 210ms gap — the arithmetic only
reconciles under that pacing once the per-event cost is put in — and what was
different about them is that every `CGEventPost` was going into a saturated
window server. **That is below every layer #75 names**, and nothing in the log
said it: it had to be reconstructed from glide durations.

**No occurrence since.** `The search results do not offer` appears in runs 17 and
19 and in no later run, and no run since PR #74 has printed a `noContentHint` at
all. That is weaker than it looks — since #69 the bot prefers ESI and reaches the
search bar much less often — so it is recorded as a relation rather than as a
cure. What *is* positive evidence is the quick filter, the one typed field the
bot reads back: runs 30, 34 and 37 each typed a 15- to 29-character name **with
spaces** and moved on without retyping or clearing the box.

### A key the sequence does not release stays down for the session

What the investigation did turn up is a real defect, in the direction this repo
keeps a section on. `_keys_down` was written on every `KeyDown` and **read
nowhere**, so a key pressed by a sequence that never released it stayed pressed
underneath every keystroke and click that followed — for the rest of the run,
since nothing else in the host takes one back.

**`effectsToEnterString` builds exactly that sequence.** Its fold emits `KeyUp
vkey_SHIFT` only when the *next* character does not want Shift, so a string
ending in a capital reaches the end with Shift down and nothing after it.
`releaseShiftAtTheEnd` closes it.

**And `getKeyboardKeyToEnterChar` could put Command underneath the typing.** Both
letter bounds read `<= 26` where the alphabet is 26 letters at offsets 0 to 25,
so offset 26 — `{` past `a`, `[` past `A` — answered `VirtualKeyCodeFromInt
(vkey_A + 26)`, which is `vkey_LWIN`, which this host maps to **Command**. A
character that cannot be typed became a modifier press rather than the `Err`
`getSequenceOfKeyboardKeysToEnterString` exists to raise. Both bounds are `< 26`
now.

**This is the failure mode #75 describes, arriving from a direction the issue
did not consider**: every effect dispatched, every event posted, every layer
reporting success, and the characters gone because the client was reading
shortcuts. `Bot.elm` already records the far end of it — Command "leaves the
field swallowing every keystroke that follows", which cost run 116 its whole
attempt, 128 typings that changed the box by not one character.

**The host now takes back whatever a sequence leaves held**, and says so.
Driven by what was actually *posted* rather than by `keys_left_held(items)`, so
that it also covers a sequence cut short — the foreground-check `break`, or a
`cg_input` that died between a press and its release, which the item list reads
as perfectly balanced. `keys_left_held` is the pure half and names what the
*bot* asked for, which is the half an operator can take to the bot. The release
is wrapped, because the likeliest reason a key is held is a `cg_input` that has
just died, so the repair runs in exactly the state where posting can fail again.

**Verified without driving input**, in
`tools/macos-host/tests/test_typed_text_key_sequence.py` (30 cases). The real
`_windows_input` is executed over the real sequence shapes with `cg_input`
replaced by a recorder, so what is asserted is what would have been posted; the
key table is checked against an independently written `kVK_ANSI_*` list, so a
typo in either is a disagreement rather than a shared mistake; and the Elm half
is read out of `Common/EffectOnWindow.elm` through a whitespace-collapsing
reader, since no bot calls it and there is nothing to execute it through. The
corpus is recounted as the relations above rather than as the numbers.

Confirmed by mutation, **fourteen** of them, each failing a named case: the
release removed entirely; the release in press order rather than reverse; the
release driven by the item list instead of by what was posted (which is the half
a dead `cg_input` produces); `keys_left_held` counting an unmapped key; it
ignoring the releases; the key hold put back at the framework's own 210ms and
removed altogether; the wait skip scoped to any held key again, which is #71's
own shape; one letter mapped to the wrong `CGKeyCode`; space dropped from the
table; the Elm fold no longer releasing Shift; the Elm release pressing Shift
instead of raising it; and each letter bound put back to `<= 26`.

**Two things were found while writing the cases and are worth keeping.** The
release, as first written, was outside the loop's `try` — so a `cg_input` that
had died would have taken the whole task down at exactly the moment the repair
was needed. And `_keys_down` was a `set`, which cannot say what order the presses
came in; it is a list, because the undo of two modifiers is the presses in
reverse.

**Unverified, and it is the half that matters: none of this explains `eueu`.**
The host posted all 21 characters of run 19's query with the right key codes and
the shipped pacing, and no sequence in that run's search path presses a modifier
at all, so neither fix here would have changed what that run typed. **Where those
characters went cannot be established without driving input into the client**,
which is the one thing this investigation was not allowed to do — the remaining
suspects are `cg_input`'s `CGEventPost` (which creates every event from a `NULL`
event source, and was measured costing 53–100 ms a call in exactly those two
runs) and the client itself. What to watch on the next run that types anything:
`KEYS LEFT HELD` should **never** appear — if it does, some sequence is
unbalanced and the message names the codes — and a run whose glides climb past
0.4s is a run posting into a saturated window server, which is the one measurable
thing runs 17 and 19 had in common.

**Eight other copies of `Common/EffectOnWindow.elm` carry both defects**, saxrat's
among them. They are deliberately not touched here: this change is scoped to the
app #75 is about, and `effectsToEnterString` is dead code in all nine, so the
divergence costs nothing until something calls it.

## Open gaps

- `dictEntriesOfInterest` doesn't recursively encode non-primitive "interesting"
  values the way Sanderling's serialisation does. `getDisplayText` in
  `ParseUserInterface.elm` falls back to decoding a non-string `_setText`/`_text`
  as *another full `UITreeNode`* — a real case, since it can hold a Python `Link`
  whose own `_text` has the actual text. Symptom seen live: "current solar
  system: Unknown" for a name that isn't a plain string in memory.
- `MouseMoveRelative` and `CharacterDown`/`CharacterUp` (raw Unicode text input)
  aren't implemented in `botlab_host.py`.
- **Whether run 35's stations really had no agent is still unknown**, and it is
  the one question #127 raised that measurement could not close. `Start a
  conversation with` never printed once in that run's 26,487 readings, so
  `selectedAgentEntry` chose nothing at either station — but the failure line
  carried no evidence about what the panel held, and the run is over. Both
  causes are live and they want opposite fixes: an empty panel is a parse
  problem, where a populated one is `isAvailable` or `agentIsInThisStation`
  being too strict. `describeNoAgentToTalkTo` now prints the rows, so the next
  occurrence answers it in one line; until then nothing should be relaxed on a
  guess. Note that a conversation with a usable agent appeared at *both*
  stations shortly afterwards, which is evidence against "these stations have no
  agents" and for something the panel path could not see.
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
- **A swap that reaches the disarm budget with the client having never confirmed
  the switch-off is still latched off, and the module says it should not be.**
  #157 closed the case where the client *took the guns back*, which needs
  `switchOffUndoneByClient` — and that latch can only report an undoing it saw
  land in the first place. Across the mission runner's corpus every `GUNS OFF`
  print where the client confirmed the switch-off has the module reading the gun
  off and none exceeds 4, while every print where it did not is a gun the module
  reads **on**, and those are the ones that reach 20. Runs 34 and 35 are that
  second kind and stopped one reading short of the give-up. The obvious fix —
  asking the module directly — is what #34 refused, and the honest one is
  probably #76's: work out why a switch-off click sometimes does not land at all,
  which run 22 recorded and nothing has explained.
- **Nothing remembers that a gate was given up on, so saxrat can go back for
  it.** #147 makes the gate branch hand the reading back and the warp branch
  decline while that gate is in reach, so the bot leaves through the hunt loop —
  but the opportunity is still offered, and once the ship is out of reach the
  warp branch is available again and may take it straight back to the same site.
  Each cycle costs `gateRefusesThisShipTicks` readings rather than the session,
  which is why it is a gap rather than a blocker, and the corpus holds one gate
  that never opened in five saxrat runs. The fix would be memory — a site or a
  gate whose verdict outlives leaving reach — and it wants a run that shows the
  oscillation before anyone designs one.
- **The out-of-range gate branch has no bound of its own.** Its counter resets
  whenever no gate is in reach, so a gate the client will not close on is
  answered by "activate it from here" every reading forever. It has never
  happened — every recorded far-gate episode closed the distance and handed off
  (23,000 m → 2,405 m in run 5, 10,000 m → 2,508 m in run 4) — but #147 makes
  that branch outrank the opportunity warp, so the state it would fail in is now
  reachable where the warp branch used to mask it.
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
  contain: `You cannot do that while warping` and `while docking`
  (6 between them), and `You cannot activate that module as the target is no
  longer present`. **`You cannot launch <drone> because you are already
  controlling N drones` is no longer among them either** — #146 reads it, in both
  apps, off the *quick message* rather than the game log, and both channels carry
  it (215 `(notify)` entries in saxrat's run 6 against 1,316 live popups). It was
  read off the popup because the popup is on the reading whatever the game-log
  window is doing, and because #146 is the issue that asked for the quick-message
  corpus to be used. **`You are already managing N targets` is no longer among
  them** — #110 reads it, in both apps, to learn the lock-slot ceiling. What it
  does *not* yet do is hand that line to the **lock range**, whose refusal test
  still requires the target bar empty at both ends of an attempt precisely
  because "the client's maximum is not in the reading at all". It is now in the
  reading, in `BotMemory.maxTargetsStatedByClient`, so the condition that throws
  away the common case could be replaced by one that compares the bar against the
  learned ceiling. That is a change to the lock-range rule and wants its own
  evidence; #110 deliberately does not make it, and #150 only went as far as
  *discharging* such an attempt rather than judging it —
  `lockAttemptCanTeachRange` reads the bar the attempt began with and nothing the
  client said. The prize is still the one #134 named: only the first lock of an
  engagement can teach a refusal today, and the client's own sentence would
  separate "no free slot" from "too far" outright.
- **A run cycled inside a mission pocket leaves the ship unattended for
  minutes.** `run_mission.sh` kills the previous bot before the new one compiles,
  and the slow `elm make` path takes several minutes; that gap is when run 7's
  ship died, with 9,286 hitpoints of incoming fire landing between the old run's
  last log line and the new run's first reading. Nothing inside the bot can see
  that window. Dock or clear the grid before cycling.

  **It also costs the new run everything the old one had read.** A mission
  inherited across a restart is a mission whose briefing the bot has not read,
  and run 32 is what that cost once: 784 readings fighting a Recon pocket the
  client had said in writing to skip. The verdict is per session by
  construction — `BotMemory` does not outlive a process — so cycling mid-mission
  hands the next run a mission it can only guess about. Since #108 the guess is
  at least visible: the status line's `clearing '<mission>':` clause says
  `NO BRIEFING READ this session` for the whole of such a run.
- **A mission whose briefing was never read is guessed about rather than
  looked up.** #108 made "no briefing read for this mission" its own value and
  chose the direction it fails in — the bot clears the field — but it did not
  make the bot go and *get* the answer, so run 32's behaviour is unchanged and
  only its log is different. Two routes were considered and neither is built.
  The tracker's own `Read Details` step would be the cheap one and the corpus
  says it is not there when it is wanted: 53 occurrences across every recorded
  run, all of them on Recon missions, and **none in run 32**. Opening the agent
  conversation on an in-progress mission is the other, and rests on a premise
  no recording settles — whether such a conversation carries `objectiveHtml` and
  a briefing subheader at all. The bot reaches that state (14 occurrences of
  `The mission is still in progress -- go fly it.`) and never prints what the
  window held, so the first thing a follow-up needs is a live read of one.
- **Looting has not been asked the question the travel step was asked.** Once
  the objective is done and the tracker offers a trip, combat stops (see "When
  the objective is done and the tracker offers a trip, the fight is over"), but
  the looting branch keeps its old place under the fight and is simply skipped
  along with it. That is right for ordinary salvage and wrong for a wreck
  holding the mission item, and the two are not distinguished today —
  `isNotableWreck` only asks whether a wreck is worth looting. #92 widened the
  disengage to 2,344 readings from 35, so the branch this skips is skipped
  sixty-odd times more often than it was.
- **Quitting a mission has never been driven by the bot**, only by hand. The
  affirmative half of the confirmation dialog is the weakest link: no live UI
  tree in this repo contains one, so the affirmative is identified as "the other
  button of a two-button dialog that has a `no_dialog_button`" rather than by a
  name anyone has read. If that shape is wrong the abandonment ends the session
  at its bound instead of quitting, which is bounded and loud but is still a
  session lost — see "A mission that cannot be progressed is given back".
- **A mission can only be quit at the station the bot last undocked from.** The
  abandonment routes there (falling back to `home-station`), and if the agent
  turns out not to be in it, `openAgentConversation` says so and the attempt
  runs out its bound. A bot that had been flying a mission taken from a
  different station than it last docked at would hit that; nothing has, because
  the tracker's own travel steps lead back to the agent.
- The damage-rate retreat's latch clears when nothing has hit the ship for a
  whole window, so a bot driven out of a pocket will be brought back into it by
  the mission logic and driven out again. Survivable, and better than the
  alternative it replaced, but it is a loop and it has not been seen live.
- **The lock click still lands on whatever row the overview re-sorted into
  place.** Run 27's asteroid was never chosen: 265 lock commands in that run and
  not one names it, the reading before it appeared shows a Ctrl+click aimed at
  `Sunder Alvi`, and the next reading reads `target Infested Asteroid`. #90
  unlocks the object once it has proved itself unhurtable, which turns 290
  readings into one per recurrence — a fix, not a cure, and a lock/unlock
  oscillation is what to watch for. The row shift itself is the same one
  `openCargoOnOverviewEntry` documents for the loot cascade and is unaddressed;
  nothing verifies that the row clicked is the row locked.
- **Nothing reads the outgoing damage summary except #90.** The gap it was built
  for is named twice in this file: `ammoSwapRangeErrorPercent` is "the weak
  half" precisely because what decides whether the other charge is better is
  whether the guns are landing, and the summary now says so per target and per
  reading. Wiring it into the swap's gain term is the obvious follow-up and is
  deliberately not part of #90 — that rule is being tuned separately.
- **A webifier that deals no damage is still invisible to the bot.** #40's
  attacker set is built from the combat log, and an EWAR module that applies no
  damage writes no line there. The overview row carries the answer — the client
  renders "Pilot is webifying me" on it — but that string occurs in none of the
  recorded runs, so there is nothing to derive a matcher from without a live
  reading. The status line now prints the rendered rows'
  `rightAlignedIconsHints`, so the next run that meets one records the literal.
- **Quick messages have now been recorded, and the first two questions are
  answered.** #123 put the client's transient popup into the status line of both
  apps and deliberately stopped there; saxrat's run 5 is the run that paid it
  off. Popups **do** survive long enough to land in a reading — dozens of
  distinct wordings, the commonest being
  `<center>Cargo is too far away. Ship is on automatic approach to cargo.` at 340
  live sightings — and the lock-capacity refusal the operator described is among
  them, `<center>You are already managing 6 targets, as many as you have skill
  to.` at 40, which settles that `quickMessage` **is** the widget they were
  seeing. #110 reads that fact off the game log rather than off this channel, for
  the scoping reason given there, so **nothing yet decides anything on a quick
  message** and the case asserting so still holds. What a run has still not
  settled is whether `l_abovemain` ever holds more than one message, which the
  parser drops without a word and the clause counts.
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

In the suite that recipe is `tools/macos-host/tests/prerequisites.py` and there
is exactly one of it. `open_repl` hands a class the app's scratch copy — patched,
compiled and probed **once per app per process** since #172 — and returns a repl
that has been shown to evaluate; expressions go in as one `[ a, b, c ]` rather
than a line each, because the repl recompiles the module for every *entry* it is
given (#84: twenty expressions, 36.5s against 5.8s). Ask for `Bool`s with
`evaluate`, `String`s with `strings`, and anything else with `values`, which is
the one caller still asking one expression per entry — inside a list the printed
form is the list's rather than each answer's.

### What a question costs is entries, and that is where the suite's time went

Issue #172 was filed on a suite taking 20-25 minutes and led with the per-class
scratch copy: 131 classes, each copying 1.4 MB and compiling its own
`elm-stuff`. **Profiled before it was optimised, and the ordering changed.**
On the container it was measured on, `copytree` is **0.003 s** — the copy the
issue leads with was never the cost. What an `elm repl` costs is *entries*: an
empty session is 0.02 s, `import Bot` against the mission runner's 21,705-line
`Bot.elm` is **1.55 s**, and every entry after it costs about the same again
whether it holds one expression or ten. That last clause is why #84's batching
worked, and it is also what nobody had followed through: a preamble of six
bindings was six compiles charged to one answer, on every question that class
asked.

So two changes, in the order the numbers put them. `built_app` builds one copy
of an app per process and hands the same directory to every class — a sixth of
the time. And `ElmRepl.script` folds every binding a caller wrote (a subclass's
`BINDINGS`, a case's `definitions`) into the single `let ... in` entry that asks
the question, leaving only imports as entries of their own, because a `let`
cannot hold an import. Measured over a six-module subset asking the same 94
questions: **763 s → 646 s → 343 s**. The folded script has *more lines* than
the one it replaced, which is the measurement's own evidence that what is paid
for is entries.

**Sharing one built tree between classes is checked rather than trusted**, since
a suite whose classes can edit each other's compiler input is this repo's
signature failure with the tests as its subject. `fingerprint_of_app` hashes the
whole tree bar `elm-stuff` — build output, which `elm repl` rewrites by design —
at the moment the build's probe passes, and `check_unchanged` re-asks it on
every hand-out and in every `close`, so a class that writes into the tree is
named by its own `tearDownClass` rather than deciding what the next class
compiles. That is also what makes probing **once** as strong as probing 131
times: the tree handed over is byte for byte the tree that answered the probe.

Two things this leaves alone. `--dist loadfile` in the workflow was justified by
the per-file scratch build, and that reason is now spent — one build per worker
process happens whatever the distribution — but the granularity is not what
bounds a parallel run either, and #199 measured that on CI itself rather than
inheriting it. Two consecutive runs of the job: 86 files and 3,643 s of case
time with the longest file at 256 s against a 911 s packing floor, then 4,203 s
with the longest at 290 s against 1,051 s. **The seconds move with the runner
and the relation does not** — the longest file is 28% of the floor in both, and
#172 saw 310 s against 1,020 s on its own container. So `loadscope` has of the
order of **20 s of a 15-to-17-minute run** to recover, and the flag stays — a
*measured* choice with a stated margin, neither a constraint nor an unexamined
default.

**A margin is a claim that stops holding without saying so**, which is what #199
was filed on: revert the shared build, or let one file grow past the floor, and
the measurement above quietly stops describing this suite while every run still
looks healthy. So it is asserted rather than remembered.
`check_file_packing.py` re-takes it from every CI run's own report — the longest
file's case time against the case time spread evenly over the workers, two
numbers from the same run, so a loaded runner stretches both and it reads the
shape of the suite rather than the speed of the machine — and fails when a
single file grows past the floor, naming it. The other half of the premise, that
the build really is one per app per *process*, is what
`test_prerequisites.OneBuiltAppIsHandedToEveryClass` pins.

And **how much of a local run is the corpus-reading cases is still unmeasured**:
they skip wherever `~/eve-bot-logs` is absent, which is CI and was the machine
these numbers came from, so a local run that reads a 122 MB log carries a cost
none of this touches.

### A fixture that never arrived reads exactly like a rule that answered nothing

A reading is handed to the repl as JSON inside an Elm string literal, and the
obvious way to write that literal is `"""..."""`. **Elm processes backslash
escapes inside a triple-quoted string**, so `\"` -- which `json.dumps` writes
for every double quote in the data -- reached the decoder as a bare `"`, the
JSON was malformed, and the whole reading decoded to `Nothing`.

That is worse than a broken fixture, and it is why #174 was a sweep rather than
a one-line fix. A case over such a reading reports *the parser answering
nothing* where the truth is *the fixture never arrived*, and from outside those
are one answer: a rule that correctly answers `Nothing` for absent input passes,
and so does a rule that would have answered something for input it never
received. It is this file's signature failure sitting in the shared harness
rather than in one file's assertions, so it could weaken any case in any file
whose fixture happened to carry a quote.

`elm_json_literal` encodes twice instead. `json.dumps` of an ASCII string emits
only `\"` and `\\`, which Elm reads exactly as JSON does; the one form the two
spell differently is `\uXXXX` (Elm wants `\u{XXXX}`), and the inner call has
already turned every non-ASCII character into one, so the outer call escapes its
backslash and Elm never meets it. Every reading in the suite goes through that
one function -- the three copies of `reading_binding`, and
`test_objective_chain_travel_step.py`, which builds a reading without ever using
that name and which nobody had counted as a caller.

**The claim about the language is executed rather than asserted in a doc
comment.** `AFixtureRoundTripsWhateverJsonItIsHandedTest` builds a fixture
carrying `alt="Next System in Route"`, requires it to reach the parser and to
come back byte for byte, and runs the *old* construction beside it and requires
that one to answer `Nothing`. `NoFileCarriesItsOwnHarness` refuses the
triple-quoted shape in every test module, because a fourteenth builder written
by hand is how this comes back.

**The sweep of the callers is the point, and the answer is that it had cost
nothing yet.** Instrumenting the shared builder and running the whole suite, 191
fixtures are built across thirteen files, and **four carry a double quote**: two
in the case above, and two in `test_saxrat_route_stargate_panel_jump.py`, which
PR #173 had already worked around locally on the day it found the defect. No
fixture in any other file carries a double quote, a backslash, or a non-ASCII
character, so every one of them decoded correctly and every result those cases
have reported stands. **No shipped rule rested on a case that was passing
vacuously.**

The one affected file also shows what the shape looks like from either side,
which is worth keeping. Restoring the old escaping fails
`test_the_live_client_s_label_names_the_next_system`, because it wanted a value
and got nothing -- that is the half PR #173 noticed. It leaves
`test_an_empty_name_answers_nothing` **passing**, because a fixture that never
arrived and a label with no name in it are the same answer. A file whose cases
all happened to be of the second kind would have reported `OK` and checked
nothing.

**A missing prerequisite is not one kind of thing.** #71 is the failure that
makes this worth stating. Eleven files each carried their own copy of the
harness, each decided for itself whether the toolchain worked by probing a real
function's current behaviour, and each answered "no" by *skipping*. Mutating
`<=` to `<` in the ammo swap's disarm budget flipped one file's probe, seventeen
cases were skipped, and the run reported `OK` for a rule nothing had executed —
which is exactly what the convention above reads as "the test is real".

So the two prerequisites get opposite answers, and the reason is what the
absence means:

| absent | answer |
|---|---|
| the recorded corpus (`~/eve-bot-logs`), the client's game logs | **skip**, reason stated — the case cannot report on evidence it does not have, and a suite that goes red for "no data" teaches people to ignore red |
| the `elm` toolchain | **fail** — the rule still exists and simply was not checked, and `OK` must not mean that |

`recorded_runs(*names)` is the first (evidence present and disagreeing is a
*failure*, which is the third answer people forget); `open_repl` is the second,
raising `ElmToolchainMissing` rather than skipping. `ELM_HARNESS_MAY_SKIP=1`
downgrades it for a machine with no Elm, and the skip it leaves is one CI
refuses. The probe is a declaration the harness appends to the *scratch* copy of
`Bot.elm`, so nothing under test can change its answer while it still cannot be
reached unless the app compiles.

**CI asserts the skip reasons, not the skip count.** Zero is the wrong
assertion — the runner has no `~/eve-bot-logs`, so 43 corpus cases skip there
correctly, and that number moves as corpus-reading cases are added.
`tools/macos-host/check_expected_skips.py` reads the JUnit report and fails on
any reason not named in its `EXPECTED` list, so a new kind of skip has to be
added by somebody who has thought about whether the runner should have had that
prerequisite.

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

**And say what guarantees the branch holding it is evaluated on the reading it
becomes true.** That is the second half of the same standard and #102 is what it
costs to leave it off: `abandonMissionGiveUpReadings` was a correct comparison
over a counter advanced on every reading, sitting in a branch the tree reached on
0.7% of them, and it ran to 10,811 against 200 before anything asked it. A
counter and the comparison that reads it are two different pieces of code on two
different schedules unless something makes them one. Where the answer is "nothing
does", either move the comparison to where nothing can decline to ask it, or
count only the readings it is asked on — and which of those is right depends on
what the give-up does, not on which is tidier. See "A bound counted on every
reading and tested on a few is not a bound".

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
