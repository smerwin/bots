# Piloting a session

How to pick this up cold: start a run, watch it, tell a real problem from noise,
and hand it back. CLAUDE.md carries the *facts* about the client and the bot;
this carries the *procedure* for operating one.

**Everything below is macOS unless it says otherwise. On the Windows machine,
read "## On Windows" first** — the tooling is different enough that following
this document top-down there will waste a session.

What transfers is the *reasoning*, not the commands. "Triage: is this real?" and
"Changing settings without restarting" transfer whole. The dispatch-counting
diagnostic transfers as a method — `send-effects` lines are in the Windows log
too — but not as commands, since the client's own log lives elsewhere and
`eve_read.py` is macOS. Everything about processes, the launcher and file paths
does not transfer at all.

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

**Fast-forward the shared checkout first if the run is meant to carry a fix.**
`run_mission.sh` compiles from `/Users/smerwin/code/bots`, not from your
worktree, so a run started while main is behind silently tests the old code.
This happened once: the run looked like a test of two merged PRs and contained
neither, and the tell was subtle -- a status-line clause that the merged source
emits unconditionally was simply absent.

**Check ESI before a run that depends on it.** The route path (#73) fails on its
first use if the Keychain refresh token has gone stale, and that failure looks
exactly like the search-bar bug it replaced. Two seconds, no side effects worth
worrying about -- setting the destination to the station you are already docked
at is a no-op in game terms:

```zsh
python3 esi_waypoint.py set --name "Amarr VIII (Oris) - Emperor Family Academy"
```

## Repositioning between sessions

**Which missions the bot gets is decided by the station it is docked in, and
nothing in the settings controls that.** `home-station` is about where the
*drones* are: the wind-down flies there, docks, and the next session therefore
starts there and takes whatever that agent chain offers.

Measured across two runs with identical settings: **1,531,629** bounty ISK
working from Amarr VI (Zorast) against **81,750** working the Mabnen agent,
roughly 9x. The rewards tell the same story at a glance -- 126k + 103k bonus
against 58k-83k.

So repositioning is a manual step between sessions, and it is quick:

1. **Stop the run in a docked window, never mid-pocket.** See "Handing back".
2. Set the route through ESI, which can name a station the search bar cannot
   type -- parentheses and hyphens included:
   ```zsh
   python3 esi_waypoint.py set --name "Amarr VI (Zorast) - Moon 2 - Theology Council Tribunal"
   ```
3. Read `InfoPanelRoute` for the jump count and the systems it names, then fly it
   one gate at a time with `eve_repl`, polling `InfoPanelLocationInfo` for the
   system name between hops rather than sleeping a fixed time:
   ```python
   eve.undock()                      # if docked
   eve.jump("Hedion"); eve.jump("Amarr")
   eve.dock("Theology Council Tribunal")
   ```
4. Confirm with the location panel -- the station name is the **second to last**
   entry, with the empire name after it, so taking the last entry gives you
   "Amarr Empire" and looks like a failure.

Leaving `home-station` pointing at the drone station is deliberate: it keeps the
restock able to restock. The cost is that every session ends parked there, so
this repositioning is owed again next time.

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

**Check the literal against the live client before you send it.** Every name
setting is matched against what the client renders, so a name that is *almost*
right matches nothing and fails in the silent direction -- the setting present,
the branch never firing, and nothing in the log complaining. Asked to add
`Wreck of Geeral Tash-Murkon` to `prefer-wreck`, the overview turned out to
render it `Wreck of: Geeral Tash-Murkon`, with a colon. One read settles it:

```zsh
python3 eve_read.py overview | grep -i "<the name>"
```

Verify against the *client*, not the run log -- a name the bot has not acted on
yet does not appear in the log at all, so a zero there proves nothing.

**Then confirm it landed**, rather than trusting the `{"queued": true}`: look for
`applying settings change from the console` in the log and read the setting back
from `/api/state`.

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

## On Windows

The Windows machine runs `eve-online-saxrat` against the native client. There is
no `cycle_run.sh`, no `screen`, no `stall_watch.py` (it screenshots through
macOS `screencapture`), and no `~/eve-bot-logs`. The operating scripts live in
the session scratchpad rather than the repo, because they are about this
machine.

**Read `tools/windows-host/FINDINGS.md` § 8 before diagnosing anything.** It
carries the traps this section only points at: `pgrep`/`pkill` blindness in both
directions, the `SetForegroundWindow` foreground lock, the four-minute cold
UI-root scan that looks exactly like a hang, and echo inflation.

### First minute

```bash
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |
    Where-Object { \$_.CommandLine -match 'botlab_host' } | ForEach-Object { \$_.CreationDate }"
ls -lt "$SCRATCH"/saxrat_run*.log | head -3
gh issue list --repo smerwin/bots --state open
```

**`pgrep`/`pkill` answer nothing here and exit as though they worked.** Git Bash
cannot see native Windows processes or their command lines, so
`pkill -f botlab_host.py` matches nothing, returns 1, and reads as success —
which is how seven hosts once accumulated, one per "restart", all driving the
same mouse. Every process question goes through PowerShell and `Win32_Process`.

Note this is the *opposite* failure to the macOS one above, and the two want
opposite habits: there `pgrep -f` matches too much (a shell command containing
the string), here it matches nothing at all. A pattern tightened for one is not
safe on the other.

**Never print the client's command line**, for the macOS reason: it carries live
`/ssoToken=` and `/refreshToken=`. Match on it, never print it.

### Starting and stopping a run

Through the scripts, never by hand:

```bash
./start_run.sh <n> <minutes>          # refuses if a host is already alive
powershell -NoProfile -ExecutionPolicy Bypass -File stop_bots.ps1
```

`start_run.sh` carries the settings string inline and **refuses to start** if the
working tree is missing marker identifiers (`anomalyNameMatches`,
`strayContextMenuGiveUpTicks`, `followFleetBroadcastFrom`) — runs 23 and 24 were
flown from a tree left on a feature branch and silently lacked the wildcard.

Two things that have each cost a run:

**Comments belong outside the quoted settings string.** Every line inside it goes
to the bot verbatim, and `AppSettings` answers an unrecognised key with
`Unknown setting name`, which `BotFramework` turns into a session that ends at
startup. A verification that filters `^#` will hide exactly this.

**The host compiles the working tree, not a commit.** Fast-forward before
starting a run that is meant to carry a fix, and check the log's own
`# bot version:` line rather than assuming.

### The client

Relaunching, which is now proven rather than inferred:

```bash
python -u tools/windows-host/launch_character.py "Joan d'Arkonor" --wait-in-game
```

It resolves the avatar from a stored fraction of the launcher window, presses and
holds, and waits for the window title to become `EVE - <character>`.
`--wait-in-game` waits further for an overview or station window, because **the
character-selection screen reads as a running process and as a parsed
`ShipUI`** — "the process exists" is not "in game".

Kill the old client by pid through PowerShell first; the launcher itself stays
running between clients. **Stop the run before the client**, for the reason
"Handing back" gives: quitting the client is not a way to stop a run, and a host
left alive keeps driving a client that is no longer there.

**Re-arm both watchers after a relaunch.** The host rediscovers the new pid and
the run survives, but a watcher holding the old one is silently blind — the same
trap as on macOS, and the engagement watcher here follows the log rather than the
pid, so only the process watch is affected.

### Watching a run

Arm two, both writing to files rather than the terminal:

```bash
./watch_run.sh saxrat_runN.log runN_watch.txt &
python -u tools/windows-host/engagement_watch.py saxrat_runN.log \
    --out shots/runN --patterns-proven-by <a previous run's log> --max-shots 200 &
```

`watch_run.sh` is deliberately **not** a stall detector — `stall_watch.py` is the
calibrated one and cannot run here, and a second hastily-tuned threshold would be
worse than none. It checks the coarse pair a threshold cannot argue with: the
host being gone, and the log no longer growing. **A quiet file is a healthy run.**

`engagement_watch.py` screenshots on anomaly arrival and first lock.
`--patterns-proven-by` makes it refuse to start if its patterns match nothing in
a log that should contain them — a watcher that silently matches nothing looks
exactly like a quiet run.

**A liveness check must never terminate the watch**, and the comparison must
tolerate `\r`: PowerShell emits it, so `"0\r" != "0"` and a naive check never
fires. That defect ran unnoticed for hours once.

### Reading the client by hand

`eve_repl` works here since #192 — `tools/windows-host/repl_platform.py` supplies
the platform half. Reading methods take no input and are safe alongside a running
bot; the virtual-key tables differ per platform, so do not carry a key code
across from the macOS notes.

The scratchpad also holds single-purpose readers built when the repl was not yet
ported: `overview_now.py`, `read_local.py`, `scanner.py`, `shot.py`,
`raise_window.py`, `wait_ready.py`.

### Handing back

saxrat docks itself at session end, so the clean handover is to let the run reach
its own planned end rather than stopping it. The log says so plainly:

```
# session duration elapsed 1s ago and the bot has not finished the session -- stopping
```

Stop early only in a docked window, and stop the watchers too — they outlive the
host and will sit watching a log that has stopped growing.

Rewrite the handover file rather than appending to it. On this machine it is
**`HANDOFF.md`**, which is what `.gitignore` actually ignores (line 23), so it
never travels with a branch. It describes this machine's client, runs and next
steps, and every machine would otherwise fight over it. Pin it to a commit and a
run number so the next reader can see at a glance how stale it is.

## Handing back

Leave the ship docked if you can -- `cycle_run.sh --stop` mid-mission strands it
in space. Wait for `assume we are docked` in the log, then cycle.

**Mid-pocket is the case that has actually cost a ship**, and it is worth being
patient about: the next run takes minutes to compile, and that gap is when run
7's ship died with 9,286 hitpoints of incoming fire landing between one run's
last log line and the next run's first reading. Stopping is safe while docked and
merely risky while travelling; it is not safe with rats on the grid.

The docked window can be short -- the bot takes a new mission and undocks again
-- so poll for it rather than checking by hand, and act as soon as it fires:

```zsh
until tail -40 ~/eve-bot-logs/mission_runN.log | grep -qa "assume we are docked"; do sleep 5; done
```

Waiting also lets the mission in progress pay out instead of being thrown away;
run 21 banked 13 kills and 115k ISK in the minutes between "we should move" and
a safe stop.

Say plainly in the handover: what is running, which log, what is open on GitHub,
and anything corrected live through the console that is not yet in a file.
