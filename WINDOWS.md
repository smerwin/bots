# Running EVE Online Elm bots on Windows

The same host as `MACOS.md`, on the platform the bots were originally written
for. It runs the Elm bots in `implement/applications/eve-online/` against the
Windows EVE Online client without `BotLab.exe` and without an account on
reactor.botlab.org. The bot source is used completely unmodified.

For non-commercial, personal use. Everything here reads and interacts with your
own client's memory and screen; nothing is sent anywhere except to the game
server, exactly as a human playing normally would.

## How this differs from the macOS host

The host is the *same program* — `tools/macos-host/botlab_host/botlab_host.py`,
directory name and all. Platform differences live behind
`tools/windows-host/win_platform.py`, which the host imports when
`sys.platform == "win32"`.

| macOS | here |
|---|---|
| SIP debugging restrictions must be disabled | **nothing.** A process may read another process owned by the same user |
| Screen Recording / Accessibility permissions | nothing |
| `clang` + `codesign` for six native helpers | one optional helper, `tree_walker.exe` |
| `probe`, `memory_sample`, `live_reader`, `cg_input`, `window_probe` | `eve_mem.py`, `input.py`, `window_probe.py` — Python, using `ReadProcessMemory` and `SendInput` directly |
| Pillow and numpy required | **neither.** Both are guarded imports on Windows |
| `pkill -f botlab_host.py` | `stop_bots.ps1` — see below, this one has cost a session |

The single largest platform hazard is **not** memory access, which is
comparatively easy here. It is coordinates: see "DPI" under Troubleshooting.

## Prerequisites

- **Windows x64**, EVE Online installed and running the 64-bit client
  (`exefile.exe` under `bin64/`).
- **The client must not be elevated** unless the host is too. Windows blocks
  synthetic input from a lower integrity level to a higher one, silently — the
  bot would read the game perfectly and every click would do nothing. Running
  both as the ordinary user is the tested configuration.
- **Python 3.** Any current 3.x. **No third-party packages are needed** —
  everything under `tools/` is stdlib plus local modules. `botlab_host.py`
  guards its PIL import on Windows and falls back to pure Python for numpy, so
  a bare interpreter is enough.

  If the python.org installer fails with **MSI 2203 / `0x80070003`** — one
  payload, usually `core.msi`, never landing in `%LOCALAPPDATA%\Package Cache`
  while the others do — that is real-time AV interference with the Burn
  bundle's per-user cache. The Python core team publishes the same build as a
  plain zip on NuGet, which sidesteps MSI entirely:

  ```
  curl -L -o python.zip https://www.nuget.org/api/v2/package/python/3.14.7
  ```

  Extract `tools/` to somewhere on `PATH`. The cost is no `py` launcher and no
  Start Menu entry; the interpreter is identical.
- **Node.js.** Easy to miss, because nothing mentions it until it fails: the
  compiled Elm bot runs under Node. `botlab_host.run_bot` does
  `subprocess.Popen(["node", driver.js, bot.js])`, and without Node the run dies
  with `FileNotFoundError: [WinError 2]` **after** compiling successfully, which
  reads like a host bug rather than a missing prerequisite. Any current LTS. The
  `.zip` distribution avoids an installer.
- **Elm 0.19.1**, which is what the apps' `elm.json` pins and what the compiler
  project ships for Windows as a gzipped binary:

  ```
  https://github.com/elm/compiler/releases/download/0.19.1/binary-for-windows-64-bit.gz
  ```

  Ungzip to `elm.exe` and put it on `PATH`. Do **not** `npm install -g elm`; the
  npm package of that name is unrelated software squatting it.
- **Tailscale**, only if you want the web console. See below — it is optional
  and its absence does not stop a run.
- **A C compiler**, only for the optional native walker. See the next section.

Nothing here is a standing system change. There is no Windows equivalent of the
SIP tradeoff `MACOS.md` documents.

## One-time setup: build the native helper (optional)

`tree_walker.exe` is a C reimplementation of the UI-tree walk. It is genuinely
optional — the host falls back to the Python walker and says so on stderr:

```
# tree_walker.exe not built (...); using the Python walker -- run tree_walker/build.bat for an ~8.7x faster read
```

**With MSVC**, which is what the repo documents:

```
tools\windows-host\tree_walker\build.bat
```

It looks for `vcvarsall.bat` in four known Build Tools locations and tells you
to `winget install Microsoft.VisualStudio.2022.BuildTools` if it finds none.

**With MinGW-w64**, which also works and is ~270 MB against several GB. The
source needs only `windows.h` and standard C headers and links `kernel32`; its
one MSVC-ism, `unsigned __int64`, is a MinGW compatibility extension:

```
gcc -O2 -Wall -DNDEBUG -o tree_walker.exe tree_walker.c -lkernel32
```

The `strncpy` truncation warnings are expected — `build.bat`'s own comment
explains the bounds are explicit and deliberate. A GCC build has been run
against a live client and selected in production; `build.bat` is still
MSVC-only and was not changed.

Measured end-to-end read dispatch on one machine, same client, same bot:
**1.304s median with the Python walker against 0.516s with the native one.**
The 8.7x in `tools/windows-host/FINDINGS.md` is the tree walk in isolation
(1252ms vs 143ms); the smaller figure here is the whole read path, most of which
the walker does not touch.

## Running a bot

Set the in-game UI language to **English** — the bots match menu text literally
— and read the target bot's own `Bot.elm` header for the client setup it needs.
Overview columns, module row assignments and keybinds are real requirements, and
most "the bot is stuck" reports trace back to one of them.

### The easy path

```
tools/windows-host/run_saxrat.sh <run number> [minutes]
```

Git Bash, not `cmd`. Three things about it are Windows-specific and all three
are load-bearing:

- **It refuses to start if a host is already alive.** `pkill -f botlab_host.py`
  does not work here — Git Bash cannot see native processes or their command
  lines, so it matches nothing, exits non-zero, and reads exactly like a clean
  stop. One session accumulated *seven* hosts that way, all driving the same
  mouse. `stop_bots.ps1` uses `Win32_Process` and proves the stop.
- **It reads `EVE_BOT_REPO`**, defaulting to a path that will not be yours. Set
  it to the checkout in **POSIX form** — the script feeds it to both `cd` and
  `cygpath -w`, and the `C:\...` form breaks the second:

  ```
  setx EVE_BOT_REPO /c/path/to/bots
  ```

- **It checks the working tree before starting.** A settings string naming a
  rule the checked-out `Bot.elm` does not have compiles and flies as though it
  were configured, so it greps for three identifiers first and refuses on a
  mismatch.

Logs go to `~/eve-bot-logs/saxrat_run<N>.log`. **The run number matters**: the
script truncates that file, so reusing a number destroys the earlier run's log.

### The general path

```
cd tools/macos-host/botlab_host
python botlab_host.py <bot-source> [options]
```

Flags are the same as `MACOS.md` documents. As there, `--execute-input` is
opt-in: without it the host reads the game and prints what it *would* click,
touching nothing. Start there.

## Watching and steering a run: the web console

`--web-console` serves session stats, a live log stream and an **editable
settings box** — settings can be changed without restarting the run, which is
the difference between retuning a threshold in place and stopping a healthy
session to do it.

It binds to this machine's Tailscale address and nowhere else, refusing to fall
back to a wider interface. That is deliberate: the console can pause, stop and
reconfigure a bot, and must not be reachable from every network the machine
joins.

**Its own `--help` text is wrong about what happens without a tailnet.** It says
the run refuses to start. It does not — `botlab_host.py` catches `NoTailnet`,
prints `WEB CONSOLE NOT STARTED`, and continues, because *"The console is a
convenience; the run is the point."* You lose the settings box and remote
pause/stop, nothing else. The console binds at host startup only, so bringing
Tailscale up mid-run does not retroactively start it.

## Setting destinations through ESI

Bots that walk a circuit — saxrat's `hunt-system`, for one — ask the host to set
the client's autopilot destination through ESI, the official API. Without it the
bot parks once a system is hunted out instead of moving on.

```
cd tools/macos-host
python esi_waypoint.py client-id <id from developers.eveonline.com>
python esi_waypoint.py auth
```

Register the application as *Authentication & API Access*, scope
`esi-ui.write_waypoint.v1`, callback exactly `http://localhost:8635/callback`.
The flow is PKCE, so **no client secret exists at all**; the only sensitive
artifact is the refresh token.

On Windows both the client id and the refresh token go into the **Credential
Manager** (`eve-esi-client-id`, `eve-esi-refresh`) via `CredWriteW`, not a file
in the repo. They are `CRED_PERSIST_LOCAL_MACHINE` generic credentials, so they
do **not** appear in `cmdkey /list` — use `control /name
Microsoft.CredentialManager` → Windows Credentials → Generic to inspect or
revoke. The refresh token does not expire; revoking is the only way it goes
away.

## What to expect, realistically

- **`eve-online-saxrat` is proven end to end here** — attach, read, find
  anomaly, warp, engage, kill, move system on the ESI-set destination.
- **The other bots are not.** They compile, and the platform layer is shared, but
  only saxrat has been flown on Windows. Treat the rest as untested here.
- **`--capture-screenshots` is untested on Windows.** It is the one path that
  wants PIL, which is a guarded import — expect to install Pillow if you enable
  it.
- **The shield gauge is unreliable and that is not a Windows problem.** It is
  scraped from live memory and produces values like 212%, 340% and a spurious
  0%. On an armour-tanked hull the shield rests near zero by design, so a status
  line reading `ship 0/100` next to `Armor: 100%` is a healthy ship. Guard on
  armour, and on `run-away-incoming-damage-threshold`, which is summed from the
  combat log and needs no gauge.

## Troubleshooting

- **`FileNotFoundError: [WinError 2]` right after a successful compile** — Node
  is not installed or not on `PATH`. The traceback points at
  `subprocess.Popen`, not at anything Elm.
- **The bot reads the game perfectly and no click does anything** — an integrity
  level mismatch. Check whether the client is running elevated while the host is
  not.
- **Clicks land a third of the way across the window from where they were
  aimed** — DPI. A process that has not declared DPI awareness is handed
  *virtualised* coordinates, silently: at 150% scaling `GetClientRect` returns
  1518x994 for a window whose own canvas is 2276x1491. `SendInput` consumes the
  same virtualised space, so the two errors do **not** cancel.
  `window_probe.declare_dpi_awareness` is called at import by everything that
  touches a coordinate, and the calibration still measures the ratio afterwards
  rather than trusting the call worked. If you add a new entry point, call it.
- **"Stopping" left the bot running** — see `stop_bots.ps1` above. Verify with
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` rather than
  assuming.
- **`Unknown setting name` and the session ends at startup** — unknown keys are
  rejected outright, not ignored. Read the bot's `Bot.elm` header for the exact
  keys.
- **A right-click seems not to open a context menu** — give it several readings
  before concluding. The bot says so itself (*"we right-clicked within the last
  couple of steps -- give the game one more reading"*), and on the Python walker
  a reading is over a second, so what looks like a stall is often just slow.
  Build the native walker before chasing it.
