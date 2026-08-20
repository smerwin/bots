# Launching an EVE bot on Windows

Companion to `MACOS.md`, scoped to one thing: getting `eve-online-saxrat`
running against the native Windows client through
`tools/windows-host/run_saxrat.sh`. For everything else about operating a
run once it's up — stopping it, watching it for stalls, relaunching the
client, handing it back — see `PILOT.md`'s "## On Windows" section and
`tools/windows-host/FINDINGS.md` § 8. This file is only the launch step,
because that step has its own traps that aren't written down anywhere else.

## The command

```bash
cd tools/windows-host
EVE_SHIP=dragoon ./run_saxrat.sh <run number> [minutes]
```

`EVE_SHIP` picks the hull profile baked into the script (`oni` is the
default if the variable is omitted; `dragoon` is the other profile
currently defined); `[minutes]` defaults to 360. The settings string for
each profile is a `case "$SHIP" in ... esac` block **inside**
`run_saxrat.sh` itself, not something typed at the command line — see the
`saxrat-windows-run-settings` memory for why: the run's own log never
echoes back what it was started with, so a settings string improvised at a
shell prompt is unrecoverable the moment the run ends. The profile name is
the only thing worth remembering; the numbers live in the script.

## Picking the run number

Don't trust a memory note or a handoff doc's "last run was N" — a run may
have finished since that note was written. Check the log directory
directly:

```bash
ls -t ~/eve-bot-logs | grep -E 'saxrat_run[0-9]+\.log' | head -5
```

and use one past the highest number found there. `run_saxrat.sh` does not
pick a number for you, and will silently overwrite an existing log if
given a number that's already taken.

## `--help` is not answered here — it launches a real run

The macOS launchers intercept `--help` before their one-bot-at-a-time
guard runs, so asking what the settings are can never end a session in
progress — CLAUDE.md documents this explicitly for that platform.
**`run_saxrat.sh` has no such interception.** Its first lines are:

```bash
N="$1"
MINUTES="${2:-360}"
[ -z "$N" ] && { echo "usage: ..."; exit 1; }
```

`$1` is taken as the run number whatever it is. `./run_saxrat.sh --help`
sets `N=--help`, passes the emptiness check, stops any existing host,
checks out the tree, and starts a real 360-minute run under the default
`oni` profile — logging to `saxrat_run--help.log`, a filename that looks
like an aborted invocation and is actually a live session. **Confirmed
live this session**: it cost about a minute of wrong-profile running
(caught only because the client happened to already be docked) before
being noticed and stopped.

Never invoke this script with a flag expecting help text back. To see what
a profile sets, read the script instead:

```bash
sed -n '/^case "\$SHIP" in/,/^esac/p' run_saxrat.sh
```

## The launcher is fire-and-forget — the shell returning proves nothing

`run_saxrat.sh` stops any existing host (`stop_bots.ps1`, which verifies
through `Win32_Process` rather than assuming — `pgrep`/`pkill` see nothing
on this platform and exit as though they'd succeeded), checks the working
tree for three marker identifiers, then backgrounds the real host with
`nohup python -u botlab_host.py ... &` and immediately prints
`started run N (...) -> <log>`. Run it with the Bash tool's
`run_in_background: true` and the tool call itself reports "exited with
code 0" within a few seconds — that only means the *wrapper script*
finished, not that the bot has done anything. The real process
(`python.exe` running `botlab_host.py`, `node.exe`, `tree_walker.exe`)
keeps running detached from that shell, invisible to any `ps`/`pgrep`
check run from Git Bash.

Confirm it actually started in two separate steps, neither of which is the
script's own exit code:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'node|python|tree_walker' } |
    Select-Object Id, ProcessName, StartTime
```

then wait for the first real decision in the log rather than trusting the
launcher's exit or the process list alone (a process can be alive and
still be minutes from its first reading — see the cold UI-root scan note
below):

```bash
until grep -qE '^\+ ' ~/eve-bot-logs/saxrat_run<N>.log 2>/dev/null; do sleep 5; done
```

A run that hasn't cleared that loop after a minute or two isn't
necessarily stuck — the UI-root cache is per boot, and a cold scan after a
reboot takes about four minutes of silence before the first reading
(`tools/windows-host/FINDINGS.md` § 8). Give it time before concluding
something is wrong; check the host's CPU time and the log's byte count
growing rather than restarting on a hunch.

## If you started the wrong thing

`stop_bots.ps1` is the only reliable stop on this platform:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows-host\stop_bots.ps1
```

It kills every `python.exe` whose command line matches `botlab_host.py`,
then `node` and `tree_walker` by image name, then re-queries and prints
`STILL RUNNING: N` if anything survived — never infer a clean stop from
the absence of complaints; read what it actually reports.
`run_saxrat.sh` already calls this before every launch, so calling it by
hand is only needed to abort a run started by mistake (as above) or to
clear state before diagnosing something else.

## Confirming a profile actually took

The log carries no line naming the settings string it was started with —
true of every saxrat run, on any platform, not a Windows-specific gap. Two
ways to check after the fact:

- Read `run_saxrat.sh`'s `case "$SHIP" in` block for the profile that was
  selected that run.
- Infer it from the status line once readings are coming in: `dmg N/1200`
  says the `dragoon` threshold is armed, `dmg N/3500` says `oni`'s is;
  `Ammo swap: off (needs ...)` on every reading is expected and correct
  for `dragoon` (a drone hull with no turret to load), where `oni` should
  instead show ammo-swap decisions firing.
