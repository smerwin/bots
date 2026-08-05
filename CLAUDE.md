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

**Eight landed hits at zero, and the corpus is cleaner than the issue expects.**
Across 77,316 outgoing lines naming 294 distinct targets, **eight targets ever
produced a zero and none of those eight ever produced a nonzero**; the other 286
never read zero once. Resists and glancing hits do not round to zero on this fit
— a glancing hit reads `15 to Mercenary Commander - Acolyte I - Glances Off` —
and the longest run of zeros anywhere later broken by a real hit is **zero**. So
there is no observed overlap for a threshold to clear, and eight is margin
rather than a separator: it is the largest value that still catches every
episode worth catching, the eight zero-only episodes having run 3, 3, 10, 28,
74, 86, 101 and 108 landed hits. It fires 20–75 s into each of the six it
catches, in place of the 41–414 s those episodes actually ran.

**It is a number about this ship's guns, not about the game.** A fit whose shots
are small enough to round to zero against a heavily resisted target would
accumulate against something it could eventually kill, and nothing in this
corpus covers that — the same warning `defaultRunAwayIncomingDamageThreshold`
carries. `give-up-after-zero-damage-hits` sets it; `-1` disables it.

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

and the status line carries `shots landing for zero: 'X' 3/8` every reading, so
a target climbing towards the threshold and one that never climbs are
distinguishable while watching a run.

**No `never-attack` setting was added.** `attack-object` is a positive list and
there is still no negative one — but a name list is exactly what failed here:
nobody had predicted `Infested Asteroid`, and the object was never selected by
name in the first place. What the operator gets instead is a threshold to tune
and a run that learns the name itself. The lever an operator actually lacked
mid-run is covered by the web console, which applies a settings change without a
restart.

**Untested against a live client.** The rule is executed through the real
`Bot.elm` in `elm repl` and the threshold is checked against the client's own
recorded lines, but no run has given up on anything. What to watch on the first
one: the status line's `shots landing for zero:` clause appearing at all — if it
never does on a run that fights, the outgoing summary is not reaching the bot —
then the unlock line above, then `GIVEN UP ON` for the rest of the session with
the object never locked again. The failure to watch for is a lock/unlock
oscillation: the row shift that produced run 27's asteroid can produce it again,
and the verdict then costs one reading each time instead of 290, which is a fix
rather than a cure.

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
noticed.

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
`tools/macos-host/tests/test_decline_mission_entries.py` (35 cases). Both rules
are executed through the real `Bot.elm` in `elm repl` rather than restated: the
parser is asked what it does with an empty value for each of the four settings,
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
`tools/macos-host/tests/test_message_box_standoff.py` (35 cases). The four pure
rules are executed through the real `Bot.elm` in `elm repl` rather than restated
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

**Unverified: any of it running.** No run has been flown since, and the box that
caused this had been closed by hand long before it was investigated — so which
node an emoji picker presents as, and whether it carried a `no_dialog_button` at
all, is still inferred from `Dismiss it using No.` being printed on the path
that requires one. Whether **Escape** closes such a window is the open question
this fix cannot answer off-line; if it does not, the ladder costs 60 extra
readings and ends in the same place, which is why the give-up rather than the
escalation is the half that matters. What to watch on the first run that meets
one: `message box N/120` in the status line climbing at all — on a healthy run
it should appear briefly and vanish, since the recorded dialogs close in 6
readings — then the Escape line, then the give-up naming the box, and then
ordinary decisions resuming while `(GIVEN UP ON, still open)` stays in the
status line. A give-up on a run where boxes are being answered normally means
the identity is churning less than it should; a `message box` clause that never
appears at all on a run that dismisses one means the standoff is not being
written.

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
Three things latch the swap off for the session, because only they should not be
retried: the menu offering neither charge, there being no crossover distance, and
reaching the silence deadline. That last one is the newcomer and deliberately so.
Having disarmed the ship once and been unable to finish, doing it again is not an
optimisation worth the risk.

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
`avoidRats` (parsed, documented, advertised by `--help`, read by no decision) and
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

**Unverified: everything about what the popup actually says.** No wording has
been captured, whether `quickMessage` is the widget the operator is seeing is
still an inference from `l_abovemain` being the natural place for a transient
centre-screen notice, and whether a popup survives long enough to land in a
reading at all is the first thing a run will answer. What to watch on the first
one: `Quick message:` on every reading, saying `none ... none seen this session`
on a quiet run and carrying a quoted string with `(on screen now)` the first time
the client shows one — then the age climbing on the readings after it. A run that
never prints the clause at all means the status line is not carrying it. A run
that prints `1 of 2 quick messages in the layer` settles the head-only question
in the direction that says the parser needs fixing.

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
| the client's transient popup (#123) | parsed on every reading and read by nothing — the same five references and the same zero readers | printed in the status line, carried forward with an age, and still read by no decision |
| the lock range (#121) | `targeting-range` asserted and never revised — `lockProvenAtMeters` appeared 0 times | the setting clamped into `[proven, refused)`, learned from the client's own answers, with the row-identity discipline unchanged |
| the ammo swap (#122) | absent, not unconfigured — `ammoSwap`, `Charge`, `chargeName` and `optimalRange` all appeared 0 times, and there was no setting to turn on | ported without its tooltip half, with `ammo-swap-range` **required** rather than optional — see "saxrat swaps ammo at a distance it is told" below |

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

**Unverified: any of it running, and whether saxrat's ships have two ammo types
worth switching between.** The three recorded saxrat runs carry no ammo clause at
all, so the corpus cannot say what a swap would have gained — that is the issue's
own assumption from the operator's request and it is not measured. What to watch
on the first run with all three settings: `Ammo swap: loaded charge reads …,
crossover N m (+/-3000, from the ammo-swap-range setting)` in the status line at
all, then `GUNS OFF for N of 20` with N small and the client confirming the
switch-off by reading 2, then `(satisfied)` and `loaded charge reads` *changing*
with each swap. `cannot load or unload` appearing in the game log means the load
is going into a running gun. A run where the swap opens a menu and the next
reading reads `A context menu has sat at the same depth` means the stray-menu
guard is still firing on the swap's own menu, which is the one new rule here and
the thing most likely to be wrong.

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
`tools/macos-host/tests/test_saxrat_message_box_standoff.py` (46 cases). The
four pure rules are executed through the real `Bot.elm` in `elm repl` rather
than restated in Python -- the standoff folded over a whole session of readings
as well as asked at single numbers, the ladder at both boundaries and either
side of each, the identity over boxes the real parser produced, and the give-up
line -- and the wiring, the placement, the ordering and the parser's deliberate
unchangedness are read out of the source through a whitespace-collapsing reader.

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

**Unverified: any of it running, and more thoroughly than in the mission
runner.** No recorded saxrat run has ever met a message box, so the starvation
this bounds is reasoned from saxrat's source and from run 30 rather than from
anything saxrat has been watched doing -- the argument is that saxrat had
nothing that would end one, not that one has happened. Whether Escape closes
such a window is the same open question it is over there; if it does not, the
ladder costs 60 extra readings and ends in the same place, which is why the
give-up rather than the escalation is the half that matters. What to watch on
the first saxrat run that meets a box: `Message box: N/120` appearing briefly
and vanishing, since the recorded dialogs close in 6 readings. A give-up on a
run where boxes are being answered normally means the identity is churning; a
`Message box:` clause that never appears on a run that dismisses one means the
standoff is not being written.

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
  **Untested against a live client**, and whether Escape closes such a window is
  the open question — watch the status line's `message box N/120`, which should
  appear briefly and vanish on a healthy run.

  And it now **refuses an empty `decline-mission` value instead of arming a
  filter with it**, and says which list refused a mission and on what entry.
  That setting is matched as a substring, so `decline-mission=` put `""` in the
  list and would have handed back every mission the agent ever offered, each one
  a standing hit logged as an ordinary skip; `agent-name`, `drone-type` and
  `avoid-rat` had the same unguarded shape and are guarded with it. Why an
  `Err` rather than a silent drop, what the empty value did in each of the four,
  that `avoidRats` turns out to be read nowhere at all, and why no warning for a
  short entry are in "A decline costs standing, so the entry that armed it has
  to be nameable" above. **Untested against a live client**, and the operator
  report the issue was filed on — `Save A Man's Career` declined at a cost in
  standing — remains **unexplained**: nothing in the recordings shows the
  decline branch firing on anything but the two configured missions, and this
  does not claim to fix it. Watch the new clause on the next run that declines:
  it should name an entry an operator recognises.

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
  conventions.

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
  recordings contradict without changing the answer. **Untested against a live
  client**, and no recorded saxrat run carries an ammo clause at all, so the
  corpus cannot say what a swap would have gained here. Watch for `Ammo swap:`
  in the status line naming a crossover, then `GUNS OFF for N of 20` with the
  client confirming the switch-off, then `(satisfied)`.

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
  message box that will not close is bounded here too" above. **Untested against
  a live client**; watch the status line's `Message box: N/120`, which should
  appear briefly and vanish on a healthy run.
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
  the threshold recounted from the client's own 77,316 outgoing damage lines.

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
- **No quick message has ever been recorded, so nothing can be matched on one
  yet.** #123 put the client's transient popup into the status line of both
  apps — see "The client's transient popup was parsed on every reading and read
  by nothing" — and deliberately stopped there. The follow-up needs a run: the
  lock-capacity refusal the operator describes is the first candidate, and it
  would give the learned lock range the direct signal it currently infers from
  the target bar being empty at both ends of an attempt. Two things that run
  also settles and neither is answerable off-line: whether a popup survives long
  enough to land in a reading at all, and whether `l_abovemain` ever holds more
  than one message, which the parser drops without a word and the clause now
  counts.
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
is exactly one of it. `open_repl` copies the app to scratch, patches
`elm-version`, opens `Bot.elm`'s exports and returns a repl that has been shown
to evaluate; expressions go in as one `[ a, b, c ]` rather than a line each,
because the repl recompiles the module per line (#84: twenty expressions, 36.5s
against 5.8s). Ask for `Bool`s with `evaluate`, `String`s with `strings`, and
anything else with `values`, which is the one caller still asking line by line —
inside a list the printed form is the list's rather than each answer's.

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
