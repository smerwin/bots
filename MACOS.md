# Running EVE Online Elm bots on macOS (Apple Silicon)

This is a macOS-native replacement for the Windows-only `BotLab.exe`. It
lets you run the existing Elm bots in `implement/applications/eve-online/`
(mining bot, combat anomaly bot, warp-to-0 autopilot) against the native
Apple Silicon EVE Online client, without Windows, without Wine, and
without any account/licensing dependency on reactor.botlab.org — the bot
code itself is used completely unmodified.

For non-commercial, personal use. Everything here reads and interacts
with your own EVE Online client's memory and screen; nothing is sent
anywhere except to the game server, exactly as a human playing normally
would.

## How this works, in one paragraph

The Elm bot logic never touches memory directly — it talks to a "volatile
process" via a small JSON protocol, expecting a stream of UI-tree
readings (what's on screen, structurally) and issuing mouse/keyboard
commands in response. On Windows, `BotLab.exe` supplies that volatile
process. Here, a small set of native macOS tools reads the game client's
memory directly (the same way BotLab.exe does on Windows, just
re-derived for this build's binary layout) and a Python host
(`botlab_host.py`) emulates the rest of BotLab.exe's job: fetching and
compiling the bot, feeding it readings, and executing the actions it
asks for.

## Prerequisites

- **Apple Silicon Mac**, EVE Online installed via the native
  `eve-online.app` launcher (not through any Windows compatibility
  layer).
- **System Integrity Protection's debugging restrictions must be
  disabled.** This is the one unusual, standing system change this
  project requires — SIP normally blocks any process (including this
  project's tools) from reading another process's memory at all, with no
  entitlement-based workaround. To disable just that part:
  1. Reboot into Recovery Mode (hold the power button at startup until
     you see "Loading startup options", then choose Options).
  2. Open Terminal from the Utilities menu and run:
     ```
     csrutil enable --without debug
     ```
  3. Reboot normally.
  4. Confirm with `csrutil status` — you should see `Debugging
     Restrictions: disabled` while everything else stays enabled.

  This is a genuine, standing tradeoff: it lowers macOS's anti-debugging
  protection **system-wide**, for every process, not just this project's
  tools, until you revert it (Recovery Mode, plain `csrutil enable`).
  Nothing else about your Mac's security posture changes.
- **Screen Recording permission** for whichever app you run this from
  (Terminal.app, iTerm2, etc.) — System Settings → Privacy & Security →
  Screen Recording. Needed for window titles to resolve and for
  screenshot capture to work.
- **Accessibility permission** for the same app — System Settings →
  Privacy & Security → Accessibility. Needed for `cg_input` to actually
  move the mouse and press keys.
- **Homebrew**, then:
  ```
  brew install elm node
  ```
  Do **not** `npm install -g elm` — the official npm package for `elm`
  is unrelated software that happens to squat the name, and even
  `elm@0.19.1` specifically fails on Apple Silicon (its installer's
  architecture detection is broken for arm64). Homebrew's `elm` is a
  real, arm64-native build (reports itself as `0.19.2`).
- **Python 3** (Homebrew's `python@3.x` is fine) with `Pillow` and
  `numpy`:
  ```
  python3 -m pip install --user --break-system-packages Pillow numpy
  ```
  (`--break-system-packages` is needed because Homebrew's Python blocks
  plain `pip install` outside a virtualenv; `--user` keeps it scoped to
  your account, not Homebrew's own managed packages.)
- **Xcode Command Line Tools** (`xcode-select --install`) for `clang`
  and `codesign`, used to build the small native helper tools below.

## One-time setup: build the native helper tools

All of this project's memory-reading and input tools live under
`tools/macos-host/`. Build and ad-hoc sign each one:

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

clang -framework ApplicationServices -o cg_input/cg_input cg_input/cg_input.c
```

(`window_probe` and `cg_input` need no entitlements — they use public
`ApplicationServices` APIs gated by the Accessibility/Screen Recording
permissions above, not `task_for_pid`.)

You only need to redo this if you edit the `.c` files, or after a macOS
update that invalidates ad-hoc signatures.

## Running a bot

1. **Launch EVE Online normally** through the native launcher and log
   in. Fullscreen or windowed both work — fullscreen puts the game on
   its own macOS Space, which the host handles automatically (it will
   switch Spaces as needed when bringing the window to the foreground).
   Set the in-game UI language to **English** — the bots match menu text
   literally. For the autopilot bot specifically, also set an in-game
   autopilot route and make sure the route info panel is expanded so the
   route is visible on screen (check the specific bot's own `Bot.elm`
   header comment for its exact prerequisites — they vary per bot).

2. **From `tools/macos-host/botlab_host/`, run:**
   ```
   python3 botlab_host.py <bot-source> [options]
   ```

   `<bot-source>` is either:
   - a local path, e.g.
     `../../../implement/applications/eve-online/eve-online-warp-to-0-autopilot`
   - a GitHub URL, either a plain repo or a `.../tree/<branch>/<subpath>`
     URL pointing at a subdirectory (needed for this repo, since apps
     live under `implement/applications/...`, not the repo root), e.g.
     `https://github.com/Viir/bots/tree/main/implement/applications/eve-online/eve-online-warp-to-0-autopilot`

   Options:
   | flag | effect |
   |---|---|
   | `--settings "<text>"` | bot-settings string, same format the bot's own documentation describes (e.g. `activate-module-always = cloaking device`) |
   | `--execute-input` | **actually** send mouse/keyboard input. Without this flag, the host runs in a safe dry-run mode: it reads the game and prints what it *would* click, but never touches your mouse/keyboard. Start here first. |
   | `--capture-screenshots` | capture real screenshot pixel data for the bot's screenshot-based fallback parsing. Off by default — costs roughly 1.5s per cycle and most bots don't read this data at all (only used for message-box/repair-shop-window button-label matching in the tested bot). Turn on only if a specific bot needs it. |
   | `--max-ticks N` | stop after N decision cycles — useful for testing |
   | `--keep-build-dir` | don't delete the temporary compiled-bot directory on exit (handy for inspecting what got compiled) |

3. **First run, do a dry run:**
   ```
   python3 botlab_host.py ../../../implement/applications/eve-online/eve-online-warp-to-0-autopilot --max-ticks 15
   ```
   Watch the status text scroll by. You should see it progress through
   setup (creating the "volatile process", finding the game window,
   locating the UI root — this last step takes a few seconds the first
   time) and then into normal operation, printing real decisions based
   on what's actually on your screen ("I see the ship is warping...",
   "Open context menu on route element icon", etc.) without touching
   your mouse.

4. **Once you're confident it's reading the game correctly**, add
   `--execute-input` to let it actually act. **This takes over your real
   mouse and keyboard while it runs** — don't use your computer for
   anything else while a bot is running with this flag, the same way you
   wouldn't while BotLab.exe is driving on Windows.

   The host brings the game window to the foreground automatically
   before every input action (switching macOS Spaces if needed for a
   fullscreen game) and verifies it actually got there before clicking
   anything — if focus can't be confirmed, it aborts that action rather
   than risk clicking into the wrong window.

5. **To stop**, `Ctrl-C` in the terminal, or let `--max-ticks` run out.

## What to expect, realistically

- **Per-cycle speed** for the tested bot (`eve-online-warp-to-0-autopilot`)
  is roughly **2.5-2.8 seconds per decision cycle** on the reference
  machine — dominated by the bot's *own* built-in 2-second pacing
  (`Bot.elm`'s `setMillisecondsToNextReadingFromGameBase 2000`), not host
  overhead. The host's own memory-read + dispatch work is well under a
  second. A different bot with tighter pacing would see faster real
  cycles automatically, with no host changes needed.
- **Only `eve-online-warp-to-0-autopilot` has been exercised
  end-to-end** so far. Other EVE bots in this repo (mining bot, combat
  anomaly bot) use the same framework and *should* work the same way,
  but haven't been run against this host yet — try them in dry-run mode
  first.
- **Non-EVE bots** (e.g. `tribal-wars-2-farmbot`, which drives a web
  browser via `OpenWindowRequest`) are **not supported** — that task type
  always fails on this host. Only the EVE Online memory-reading path is
  implemented.
- **Only tested on one display configuration** (a single Retina
  display). Multi-monitor or non-Retina setups haven't been exercised
  and may need adjustment to the coordinate-scaling logic in
  `botlab_host.py`.

## Troubleshooting

- **`task_for_pid failed: (os/kern) failure (kr=5)`** — SIP's debugging
  restrictions are still enabled. Re-check `csrutil status` shows
  `Debugging Restrictions: disabled`; if not, redo the Recovery Mode
  step above.
- **`no matching windows found`** — the game client isn't running, or
  Screen Recording permission isn't granted to the terminal app you're
  running this from.
- **Clicks land near, but not exactly on, the right spot** — this
  usually means the game's own UI-scale setting changed (it's read live
  every cycle and self-calibrated against the actual window size, so it
  should self-correct within one cycle; if it doesn't, restart the
  host).
- **`elm make` fails with a version-mismatch error** — check `elm
  --version`; the host automatically patches a working copy's
  `elm.json` to match whatever's installed, so this should be rare, but
  if you have multiple `elm` installs on your `PATH`, make sure the
  Homebrew one takes precedence.
- **The bot immediately says `FinishSession` with an error about
  bot-settings** — check the bot's own documentation/comments at the top
  of its `Bot.elm` for the exact settings format it expects.
- **Nothing happens when `--execute-input` is on** — check Accessibility
  permission is actually granted (not just requested) to your terminal
  app in System Settings, and that the game window isn't minimized.

## Reverting the SIP change

If you want to restore full System Integrity Protection later (this
also disables everything in this guide):

1. Reboot into Recovery Mode.
2. Open Terminal → `csrutil enable`.
3. Reboot normally.
