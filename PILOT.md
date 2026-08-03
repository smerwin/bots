# Piloting a session

How to pick this up cold: start a run, watch it, tell a real problem from noise,
and hand it back. CLAUDE.md carries the *facts* about the client and the bot;
this carries the *procedure* for operating one.

## First minute: what is the state?

```
cd tools/macos-host
./cycle_run.sh --status                  # bot running? which log?
pgrep -f "SharedCache/tq/EVE.app" | head -1   # client pid, never `pgrep -fl`
ls -lt ~/eve-bot-logs | head -3          # runs, newest first
gh issue list --repo smerwin/bots --state open
```

`--status` is answered without touching a running session. `--help` on the
launchers likewise.

**Never print the client's command line.** It carries `/ssoToken=` and
`/refreshToken=`. `pgrep -f` without `-l` matches without printing; `python3
eve_read.py pid` resolves it from the bundle id.

## Starting a run

The launcher's own defaults are good and are calibrated per hull. Two rules keep
them that way:

**Rebuild the settings string from `run_mission.sh`, never from a saved copy.**
`--settings` replaces the defaults *wholesale*, so a stale file silently
reinstates old values -- this is how a corrected `run-away-shield-hitpoints-threshold-percent`
came back as `-1` after being fixed, and how it could come back as `25` now that
it is correctly `-1`.

```python
import re
base = re.search(r'^SETTINGS="(.*?)"$', open("run_mission.sh").read(), re.S|re.M).group(1)
extra = """home-station=Amarr VIII (Oris) - Emperor Family Academy
drone-type=Acolyte I
short-range-ammo=Multifrequency M
long-range-ammo=Radio M"""
open("/tmp/runN_settings.txt","w").write(base + "\n" + extra + "\n")
```

**A multi-line settings string cannot be passed through `cycle_run.sh`.** It
stuffs the launcher command into a screen session as *text*, so 20 newlines
become 20 commands and nothing runs -- silently, with no output at all. Use a
one-line wrapper:

```zsh
cat > /tmp/runN_launcher.sh <<'WRAP'
#!/bin/zsh
exec /Users/smerwin/code/bots/tools/macos-host/run_mission.sh \
     --session-duration-minutes 180 \
     --settings "$(cat /tmp/runN_settings.txt)"
WRAP
chmod +x /tmp/runN_launcher.sh
BOT_LAUNCHER=/tmp/runN_launcher.sh ./cycle_run.sh
```

Run it with `run_in_background`: `start()` polls up to five minutes for the
first decision. An exit code of **144 is SIGPIPE from `tail`**, not a failure --
check `cycle_run.sh --status` before believing a run did not start.

## The client

Relaunching after a quit, or from cold:

1. `osascript -e 'tell application "eve-online" to activate'` -- **the launcher
   must be frontmost or the click only activates it**;
2. capture the launcher window and confirm the tooltip reads "Click and hold to
   launch <character>" before committing;
3. press and hold the avatar ~6s (PLAY NOW ignores synthetic clicks);
4. wait for the window title to become `EVE - <character>`, not merely for the
   process.

**A relaunched client invalidates the UI-root cache.** Addresses are
per-process-launch, so `eve_read.py` and `eve_repl` refuse with "cache names pid
N" until a bot run repopulates it. Until then, read the client by screenshotting
the window (`screencapture -x -o -l <window id>`) and converting coordinates by
hand: image pixel / 2 = window point, screen = window origin + window point.

**If the Mac is locked, nothing works and it does not look like it.** Window
captures still succeed but return *stale* frames. The tell is two captures a
minute apart being byte-identical while a clock in the image lags wall time.

## Watching a run

Arm two things, against the *current* client pid:

```zsh
python3 -u stall_watch.py ~/eve-bot-logs/mission_runN.log \
    --pid <client pid> --out <dir> --keep-going
```

and a process watch for the bot or client disappearing.

**The trap, hit repeatedly: do not match a string the bot prints every
reading.** `Head for a station and dock` is both a retreat *and* ordinary
wind-down; `get out get out` prints once per reading for as long as a retreat
lasts. Either will flood the channel hundreds of times. Match the transition,
not the state, and prefer `tail -f` over re-reading a window (a fixed `tail -n`
re-reports the same line until it scrolls away).

Filter the known-benign signatures rather than lowering `stall_watch`'s
threshold -- it is calibrated against 55 runs and catches pathologies that
repeated thousands of times.

## Triage: is this real?

Most alarms are not. In order of cost:

1. **Is the game still moving?** Freshness and content of EVE's own log settles
   most questions in one command:
   ```zsh
   N=$(ls -t ~/Documents/EVE/logs/Gamelogs/*.txt | head -1)
   stat -f '%Sm' "$N"; grep -c "(combat)" "$N"; tail -2 "$N"
   ```
   Fresh `(combat)` lines with real damage numbers mean the guns are landing.
2. **Is a number moving?** A distance falling monotonically is progress however
   slow; flat or oscillating is not. Repeated identical decisions are normal --
   the bot re-derives its whole path several times per reading.
3. **Is it a loop?** Measure the *deepest* decision line, and count consecutive
   repeats, not totals:
   ```zsh
   grep -aE '^\+ ' "$LOG" | uniq -c | sort -rn | head -4
   ```
4. **Read the client directly** when the log is ambiguous -- `eve_repl`'s
   reading methods take no input and are safe alongside a running bot.

`askForHelpToGetUnstuck` ("stuck here and need help") is never normal, but a
count of zero is not health: the two worst pathologies on record never reached
it.

## Changing settings without restarting

The console is on by default and binds to the tailnet address only.

```zsh
curl -s http://<tailnet-ip>:8787/api/state | python3 -c 'import json,sys; print(json.load(sys.stdin)["settings"])'
# edit, then POST the WHOLE string back -- not a patch
```

The loop applies it on the next tick and logs `applying settings change from the
console`. This is the cheapest way to test a settings guess, and it saved run 10
mid-session when a threshold was firing on the ship's resting state. It dies
with the run: anything worth keeping goes into `run_mission.sh`.

## Intervening by hand

Reading the client during a run is free. Driving it is not, but it is safe: the
host stands down for 5 s after any human input, so a manual click costs one tick.

Never run `reload_drones.py` or `route_setter.py` alongside a session -- they
keep clicking regardless and the two take turns badly.

To rescue a ship: `python3 -i eve_repl.py`, then `eve.dock("<distinctive part of
the station name>")`. Docking works from any range; **warp needs 150 km**, so
anything closer is an approach.

**Flying to another system** is one call per gate, then dock:

```python
eve.jump("Amarr")                      # selects the gate, presses Jump
# poll InfoPanelLocationInfo until the system name changes (~40 s)
eve.dock("Theology Council Tribunal")  # ~40 s more
```

**Quitting a mission the bot cannot finish** — the path is not where you would
look for it:

1. `Alt-J` for Opportunities, then click the **Active** tab (the default view is
   available opportunities, not accepted ones);
2. right-click the `AgentMissionCard`. Its menu offers `Start Conversation /
   View Details / Untrack` — **there is no Quit here**;
3. `Start Conversation`, and the conversation window carries `QuitMission_Button`;
4. confirm the **Yes/No** dialog;
5. the info panel's mission entry disappears when it has taken.

Then add the name to `decline-mission` for the next run.
`shouldDeclineMission` matches with `stringContainsIgnoringCase`, so
`Illegal Activity` also covers `(2 of 3)` and `(3 of 3)`.

**A stray right-click in station opens a "New Location" bookmark dialog.** It is
the same hazard CLAUDE.md documents for computed empty space, and it will sit
over the UI swallowing later clicks. Cancel it before continuing. Aim
right-clicks at a node's own centre from the tree, never at a guessed point.

## Handing back

Leave the ship docked if you can -- `cycle_run.sh --stop` mid-mission strands it
in space. Wait for `assume we are docked` in the log, then cycle.

Say plainly in the handover: what is running, which log, what is open on GitHub,
and anything corrected live through the console that is not yet in a file.
