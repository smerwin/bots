---
name: diagnose-stuck-run
description: Work out whether a running EVE bot is stuck in an unrecoverable decision loop, and find the code responsible. Use when asked "is the bot stuck", "is it looping", "what is it doing", or when a run seems to be making no progress.
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Bash
---

# /diagnose-stuck-run — is the bot looping, and why

Gather evidence before changing anything. **Do not stop the run** until the
user asks or you have captured what you need — a stopped run cannot be
re-examined, and the live client is often the only place the answer exists.

The deliverable is an assessment: stuck or not, since when, and which branch.
Fix only when asked.

## 1. Is a run alive?

```
cd tools/macos-host && ./cycle_run.sh --status
```

That uses the same process set as the launchers' one-bot-at-a-time guard:
`run_mission.sh`, `run_saxrat.sh`, `botlab_host.py`, `driver.js`,
`tree_walker/tree_walker`, `cg_input/cg_input`.

## 2. Find the log

The log is **not** in the repo and **not** visible via `lsof` on the bot's own
pids — output is piped to `tee`, which is downstream in the pipeline and the
only process holding the file open. Looking at the bot pids shows stdout as a
tty and suggests, wrongly, that no log exists.

```
pgrep -fl tee
```

`cycle_run.sh` writes `${BOT_LOG_DIR}/mission_run<N>.log`, defaulting to a
scratchpad path hardcoded in that script. If there is no `tee`, read the screen
session directly — this works while it is attached, and needs the **full**
session name from `screen -ls`, not the bare name:

```
screen -ls
screen -S <pid>.<name> -X hardcopy -h /tmp/screen_dump.txt
```

## 3. Hard stuck signal

```
grep -ac "stuck here and need help" "$LOG"
```

That is `askForHelpToGetUnstuck` and is never normal. A count of zero does
**not** mean healthy — most real loops never reach it, because the branch that
loops is usually one that thinks it is making progress.

## 4. Repetition, measured at the right depth

Measure the **deepest** decision line, not the top level. Top-level `^+` lines
are shared by many different states, so they under-report badly: in the run
this skill was written from, the top level showed a maximum run of 11 while the
actual loop was 842 deep.

```
grep -aE '^\++ ' "$LOG" | tail -200 | uniq -c | tail -20
grep -ac "<the exact repeated decision text>" "$LOG"
```

Remember: **a decision is not an action.** The bot re-derives its decision on
every framework event, several per reading, but dispatches input once per
cycle. Repeated identical lines usually mean one action, not many. Long runs of
one decision during combat ("I see a locked target") are normal waiting.

## 5. Is any state actually changing?

This is what separates slow from stuck. Pull the numbers embedded in the
repeated decision and look at the trend, not the first and last value:

```
grep -aoE '^# \[[0-9]+\.|is not in range \([0-9]+ m' "$LOG" \
  | awk '/^#/{t=$0; gsub(/[^0-9.]/,"",t)} /range/{d=$0; gsub(/[^0-9]/,"",d); if(d!=p){print t, d; p=d}}' | tail -25
```

Oscillating between two values is not progress — that is usually the target
drifting while the ship does nothing. Monotonic movement toward the threshold
is progress, however slow.

Nothing is timestamped. `# [N.0] (Xs)` is the gap since the previous tick;
summing those reconstructs elapsed time.

## 6. What actually reached the client

`send-effects` lines are the truth about input. A repeated
`move: already at (x, y)` at identical coordinates every cycle means the same
click is being issued over and over — the input is landing, so the fault is in
what the bot expects to happen next, not in the clicking.

## 7. Find the branch

Decision strings are literals in the bot's source:

```
grep -rn "<exact decision text>" implement/applications/eve-online/<bot>/
```

Read the surrounding branch and identify the **guard** that is never passing.
Count how often each side of it fired — a guard whose "success" branches show
zero occurrences across the whole log is the bug, not a coincidence.

## 8. Test the guard's premise against the live client

Whatever the guard reads — a window, a node type, a name, a column — verify it
exists in the running client with `/check-ui-parse`. That is where the answer
usually is: the click landed, the state changed, and the parser could not see
it.

## Reporting

Say plainly: stuck or not, for how long (ticks and minutes), which decision,
which guard, and what evidence rules out "merely slow". If it is genuinely
looping, note that nothing will break it out on its own and say whether
`stall_watch` was running.
