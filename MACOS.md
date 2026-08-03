# Running EVE Online Elm bots on macOS (Apple Silicon)

A macOS-native replacement for the Windows-only `BotLab.exe`. It runs the
existing Elm bots in `implement/applications/eve-online/` against the native
Apple Silicon EVE Online client — no Windows, no Wine, and no account or
licensing dependency on reactor.botlab.org. The bot source is used completely
unmodified.

For non-commercial, personal use. Everything here reads and interacts with your
own client's memory and screen; nothing is sent anywhere except to the game
server, exactly as a human playing normally would.

## If you know BotLab, start here

The bot side is identical. Same Elm source, same `botMain`, same settings
strings, same `Bot.elm` header conventions. What changes is everything under it:

| BotLab on Windows | here |
|---|---|
| `BotLab.exe` (host, licensing, bot fetch, scheduling) | `tools/macos-host/botlab_host/botlab_host.py` |
| reactor.botlab.org account and online session | nothing — no account, no network dependency |
| "Pine" Elm interpreter | vanilla `elm make` plus a small `Platform.worker` port wrapper |
| `EveOnline/VolatileProcess.csx` (C#, reads client memory) | native tools under `tools/macos-host/` — the same CPython-object-graph walk, offsets re-derived for this build |
| BotLab session UI / recordings / catalogue | none. A run is a terminal process printing its decision tree |
| `botlab  play  <url>` | `python3 botlab_host.py <path-or-url>`, or a launcher script |

Two consequences worth knowing up front. There is **no dry-run-by-default
safety net in BotLab's sense** — but there is a better one here: input is off
unless you pass `--execute-input`, so the default run reads the game and prints
what it *would* do without touching your mouse. And there is **no session
recording**; the terminal log is the whole record, so redirect it to a file if
you want to keep it.

## Prerequisites

- **Apple Silicon Mac**, EVE Online installed via the native `eve-online.app`
  launcher (not through any Windows compatibility layer).
- **SIP's debugging restrictions must be disabled.** This is the one unusual,
  standing system change the project requires: SIP otherwise blocks any process
  from reading another process's memory, with no entitlement-based workaround.
  1. Reboot into Recovery Mode (hold the power button until "Loading startup
     options", then Options).
  2. Terminal from the Utilities menu: `csrutil enable --without debug`
  3. Reboot normally.
  4. Confirm `csrutil status` shows `Debugging Restrictions: disabled` with
     everything else enabled.

  This is a real tradeoff: it lowers macOS's anti-debugging protection
  **system-wide**, for every process, until you revert it (Recovery Mode, plain
  `csrutil enable`). Nothing else about your Mac's security posture changes.
- **Screen Recording permission** for the app you run this from (Terminal,
  iTerm2, …) — System Settings → Privacy & Security. Needed for window titles to
  resolve and for screenshot capture.
- **Accessibility permission** for the same app. Needed for `cg_input` to move
  the mouse and press keys.
- **Homebrew**, then `brew install elm node`.

  Do **not** `npm install -g elm`: the npm package of that name is unrelated
  software squatting it, and `elm@0.19.1` specifically fails on Apple Silicon
  because its installer's architecture detection is broken for arm64.
  Homebrew's `elm` is a real arm64 build, reporting `0.19.2`.
- **Python 3** with Pillow and numpy:
  ```
  python3 -m pip install --user --break-system-packages Pillow numpy
  ```
  (`--break-system-packages` because Homebrew's Python blocks plain
  `pip install` outside a virtualenv; `--user` keeps it out of Homebrew's own
  packages.)
- **Xcode Command Line Tools** (`xcode-select --install`) for `clang` and
  `codesign`.

## One-time setup: build the native helper tools

The compiled binaries are deliberately not in the repo — they are
platform-specific build output — so a fresh clone must build them:

```
cd tools/macos-host

clang -o probe/probe probe/probe.c
codesign -s - --entitlements probe/entitlements.plist -f probe/probe

clang -o memory_sample/memory_sample memory_sample/memory_sample.c
codesign -s - --entitlements memory_sample/entitlements.plist -f memory_sample/memory_sample

clang -O2 -o live_reader/live_reader live_reader/live_reader.c
codesign -s - --entitlements live_reader/entitlements.plist -f live_reader/live_reader

clang -O2 -o tree_walker/tree_walker tree_walker/tree_walker.c
codesign -s - --entitlements tree_walker/entitlements.plist -f tree_walker/tree_walker

clang -framework ApplicationServices -o window_probe/window_probe window_probe/window_probe.c
clang -O2 -framework ApplicationServices -o cg_input/cg_input cg_input/cg_input.c
```

`window_probe` and `cg_input` need no entitlements — they use public
`ApplicationServices` APIs gated by the Accessibility and Screen Recording
permissions above, not `task_for_pid`.

Redo this only if you edit the `.c` files, or after a macOS update invalidates
ad-hoc signatures.

## Running a bot

Set the in-game UI language to **English** — the bots match menu text literally
— and read the target bot's own `Bot.elm` header, which lists the client setup
it needs. Those requirements are real: overview columns, which row each module
sits in, and specific keybinds. A bot cannot work around a client configured
differently, and most "the bot is stuck" reports trace back to one of them.

Fullscreen and windowed both work. Fullscreen puts the game on its own macOS
Space, which the host handles — it switches Spaces when bringing the window
forward, and verifies it got there before clicking.

### The easy path

Two bots have launcher scripts that carry known-good settings:

```
cd tools/macos-host
./run_mission.sh          # eve-online-mission-runner
./run_saxrat.sh           # eve-online-saxrat
./run_mission.sh --help   # this bot's settings, and the host's flags
```

`--help` is worth reading before the first run: it prints the bot's own
documented settings, any settings its `parseBotSettings` accepts that the
documentation omits, the defaults the launcher passes, and the host's flags.
It is answered before the launcher's one-bot-at-a-time guard runs, so asking
never disturbs a session already going.

Both launchers pass `--execute-input`, so they drive the real mouse and
keyboard, and both kill any bot session already running first.

### The general path

```
cd tools/macos-host/botlab_host
python3 botlab_host.py <bot-source> [options]
```

`<bot-source>` is a local path, e.g.
`../../../implement/applications/eve-online/eve-online-warp-to-0-autopilot`,
or a GitHub URL — a plain repo, or a `.../tree/<branch>/<subpath>` URL for a
subdirectory, which this repo needs since apps live under
`implement/applications/…` rather than the root.

| flag | effect |
|---|---|
| `--settings "<text>"` | bot-settings string, exactly the format the bot's own documentation describes |
| `--execute-input` | **actually** send mouse and keyboard input. Without it the host reads the game and prints what it *would* click, touching nothing. Start here. |
| `--session-duration-minutes N` | tell the bot how long the session runs; `BotFramework`'s own wind-down docks it once ~200s remain |
| `--capture-screenshots` | capture real pixel data for screenshot-based parsing. Off by default: ~1.6s per cycle, and most bots never read it |
| `--max-ticks N` | stop after N decision cycles |
| `--keep-build-dir` | keep the temporary compiled-bot directory for inspection |

First run, do it without `--execute-input`:

```
python3 botlab_host.py ../../../implement/applications/eve-online/eve-online-warp-to-0-autopilot --max-ticks 15
```

Watch it work through setup — creating the volatile process, finding the game
window, locating the UI root (a few seconds the first time) — and then print
real decisions from what is actually on your screen, without touching your
mouse. Add `--execute-input` once you believe it is reading the game correctly.
Stop with `Ctrl-C`, or let `--max-ticks` run out.

### Watching a long run

`stall_watch.py` tails a running bot's log and screenshots the client the moment
it stalls, so an overnight run leaves evidence rather than just a stopped bot:

```
python3 stall_watch.py <logfile> --pid <game client pid> --out <screenshot dir>
```

A stall is the bot saying *"I am stuck here and need help to continue."*, or the
same decision repeating 60 times. It captures the game window by id rather than
the screen, which matters when the client is on another Space. Run the bot with
`2>&1 | tee somefile.log` to have a log for it to read.

## Watching and steering a run: the web console

Pass `--web-console` and the host serves a page on your tailnet -- session
stats, the log as a live filterable stream, and an editable settings box. It
binds to this machine's Tailscale address and refuses to start without one, so
it is never exposed beyond the tailnet.

The settings box is the part worth knowing about, because it changes settings
**without restarting the run**:

```
# read what the bot is using now
curl -s http://<tailnet-ip>:8787/api/state | python3 -c 'import json,sys; print(json.load(sys.stdin)["settings"])'

# replace it -- send the whole string, not a patch
curl -s -X POST http://<tailnet-ip>:8787/api/settings \
     -H 'Content-Type: application/json' \
     -d '{"settings": "orbit-in-combat=no\nkeep-at-range=yes\n..."}'
```

The loop applies it on its next tick and logs `applying settings change from the
console`. Under the hood it re-sends `BotSettingsChangedEvent`, the same event
the session opens with, so the bot re-reads every setting and nothing in the bot
needs to know the console exists.

This is the cheapest way to test a settings guess. A wrong `approach-object` or
`attack-object` is one POST away from being undone, whereas finding out by
restarting costs the whole session's progress -- and a two-hour run that has
already handed in seven missions is not something to throw away over one
misjudged line.

## What to expect, realistically

- **`eve-online-mission-runner`** is the most exercised bot here: it takes a
  security mission from an agent, flies out, clears each pocket through its
  acceleration gates, returns and hands in. Over 55 logged runs it completed 48
  missions, median ~5.4 minutes each. Combat featured in 79%, acceleration gates
  in 33%, looting in 21%.
- **`eve-online-saxrat`** (combat anomalies) and
  **`eve-online-warp-to-0-autopilot`** are also proven end to end, from both a
  local path and a GitHub URL. `eve-online-mining-bot` still compiles but has
  not been run against this host. `eve-online-wingus` is unexplored.
- **Cycle time is set by the bot, not the host.** `warp-to-0` runs ~2.5-2.8s per
  cycle because its own `Bot.elm` sets
  `setMillisecondsToNextReadingFromGameBase 2000`. The mission runner and saxrat
  use a `bot-step-delay` setting instead, 499ms by default, and land around 7s
  per cycle once the memory read and screenshot read are included. Host overhead
  is well under a second either way; the native `tree_walker` reads a
  ~2,800-node tree in roughly 0.4s.
- **Non-EVE bots are not supported.** Anything driving a browser via
  `OpenWindowRequest` (e.g. `tribal-wars-2-farmbot`) always fails here; only the
  EVE memory-reading path is implemented.
- **One display configuration tested** — a single Retina display. Multi-monitor
  or non-Retina setups may need adjustment to the coordinate scaling in
  `botlab_host.py`.
- **Expect to tune settings against your own fit and overview.** Several of the
  bots' settings match against the overview's *Type* column, so they depend on
  what your overview shows and how it is sorted. The `Bot.elm` headers say which.

## Driving the client by hand

For one-offs -- rescuing a ship, unsticking a window, checking what the bot can
actually see -- there is an interactive handle on the client:

```
cd tools/macos-host
python3 -i eve_repl.py
>>> eve.dock("Emperor Family Academy")
```

`REPL.md` covers it, including the coordinate conversion and the conventions
that have to be right for a click to land where you meant.

## Driving the EVE launcher (switching accounts)

The launcher and the game are separate apps: `/Applications/eve-online.app` (an
Electron shell) and the client itself out of `SharedCache/tq/EVE.app`. Different
pids, different windows, and `window_probe --all` sees both. The launcher's main
window is named `EVE Launcher`; the client's is named for the character, e.g.
`EVE - Gal Bistot`.

Screenshot a launcher window with `screencapture -x -o -l <window id>`. The
image is at backing scale 2, so image pixel / 2 = window point, and screen point
= window origin + window point. The window sits below the menu bar, so its
origin y is not zero.

**Clicking an account row selects it.** Verified by parking the cursor far away
afterwards and re-reading: the right-hand panel keeps the new account, so it is
a real selection and not a hover effect.

**PLAY NOW ignores synthetic clicks.** Three attempts -- centre of the button,
the play-icon side, and once with an approach gesture so it registered as real
movement -- left the status bar reading "EVE Online | Ready to play!" with no
client process and no error dialog. This is not a general problem with clicking
the launcher: the same mechanism selects accounts perfectly well.

**Press and hold the character's avatar for about five seconds instead.** That
launches that character directly, and skips the character-selection screen
entirely.

Quitting the client:

```
osascript -e 'tell application "EVE" to quit'
```

This reports `execution error: EVE got an error: User canceled. (-128)` and
quits anyway. Check with `pgrep -f "SharedCache/tq/EVE.app"` rather than
trusting the exit status.

One caution: the client's command line carries its SSO and refresh tokens, so
`ps`/`pgrep -fl` output for that process does not belong in a shared log or
a pasted transcript.

## Troubleshooting

- **`task_for_pid failed: (os/kern) failure (kr=5)`** — SIP's debugging
  restrictions are still on. Re-check `csrutil status`.
- **`no matching windows found`** — the client isn't running, or Screen
  Recording permission isn't granted to your terminal app.
- **Nothing happens with `--execute-input`** — check Accessibility permission is
  actually granted (not merely requested) to your terminal app, and that the
  game window isn't minimized.
- **Clicks land near but not on the target** — usually the game's UI-scale
  setting changed. It is read live and self-calibrated against the real window
  size each cycle, so it should correct itself within a cycle; restart the host
  if not.
- **`elm make` fails on a version mismatch** — the host patches a working copy's
  `elm.json` to match the installed `elm`, so this is rare. If you have several
  `elm` installs, make sure Homebrew's takes precedence.
- **`FinishSession` immediately, complaining about bot-settings** — run the
  launcher's `--help`, or read the bot's `Bot.elm` header, for the exact keys it
  accepts. Unknown keys are rejected outright rather than ignored.
- **The bot does nothing while sitting in space** — most often it cannot see
  what you expect it to. The overview only renders the rows that fit, and the
  bot only acts on rendered rows; objects far enough away for the distance to
  read in AU are ignored entirely.
- **A module toggles on and off** — a module button is a toggle, so anything
  clicking it twice before the client has shown the first result switches it
  back. Check the module row assignments in the bot's `Bot.elm` header.

## Reverting the SIP change

Restores full System Integrity Protection, and disables everything in this
guide:

1. Reboot into Recovery Mode.
2. Terminal → `csrutil enable`
3. Reboot normally.
