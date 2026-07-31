---
name: bot-run
description: Start, stop, cycle and observe an EVE bot run safely, including stall watching. Use when asked to start or stop the bot, begin the next run, check what is running, or watch a run for stalls.
user-invocable: true
allowed-tools:
  - Read
  - Bash
---

# /bot-run — run control and observation

Only one bot at a time. The launchers kill any existing session on startup, so
starting a run while another is live silently ends the first one. Check before
starting.

## Status, stop, next run

```
cd tools/macos-host
./cycle_run.sh --status     # what is running, and the newest log
./cycle_run.sh --stop       # Ctrl-C, escalating to TERM then KILL
./cycle_run.sh              # stop, then start the next numbered run
```

`cycle_run.sh` is **one shot** — it starts exactly one more run and does not
loop. Nothing re-launches a finished run on its own; there is no cron or
launchd job for this.

Defaults it uses, all overridable by environment variable: screen session
`saxrat` (`BOT_SCREEN`), launcher `run_mission.sh` (`BOT_LAUNCHER`), log
directory and prefix (`BOT_LOG_DIR`, `BOT_LOG_PREFIX`).

To start a bot directly instead:

```
./run_mission.sh            # or ./run_saxrat.sh
./run_mission.sh --help     # settings and flags; answered before the kill guard
```

`--help` is safe: it is handled before the one-bot guard runs, so asking what
the settings are never ends a session in progress.

## Never run these alongside a bot

`route_setter.py` and `reload_drones.py` drive real mouse and keyboard directly
and are not part of the bot loop. Running either during a session makes both
fight for the cursor. Check with the launchers' own process patterns first.

## Watch for stalls

```
python3 stall_watch.py <log> --pid <game pid> --out <dir>
```

The game pid is the argument `tree_walker` was started with — `pgrep -fl
tree_walker/tree_walker` shows it.

**It exits on the first stall.** That is by design so a caller can act, but it
means one invocation gives one alarm and then coverage silently stops. For a
long run, either re-launch it after each firing or wrap it in a loop. If you
started it and later find it gone, check its output before assuming it crashed
— firing and exiting looks identical to dying from the outside.

It screenshots the client **by window id**, because the client is usually on
another macOS Space where a screen grab catches the wrong desktop.

A stall is either `askForHelpToGetUnstuck` ("I am stuck here and need help to
continue"), which is never normal, or the same decision repeating past
`--threshold`. The threshold is worth knowing before trusting a quiet watcher:
it is printed on startup, and a legitimately repetitive stretch such as a long
combat can trip it. A firing is a prompt to look, not proof of a defect —
confirm with `/diagnose-stuck-run`.

## Reading a run in progress

Logs come from the `tee` in the pipeline, not from the bot process — see
`/diagnose-stuck-run` for finding them. To read the screen session itself,
`screen -S <pid>.<name> -X hardcopy -h <file>` works while it is attached, and
needs the full session name from `screen -ls`.
