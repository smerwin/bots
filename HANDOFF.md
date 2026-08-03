# Handoff

Transient state: what is in flight, what is unproven, and what to do next.
Durable facts about the client and the host live in `CLAUDE.md` — this file is
the part that goes stale, and it should be rewritten rather than appended to.

Last updated at `e2b56b0` (PR #49 merged).

## The one thing to know first

**Almost nothing merged in this batch has faced the live client.** Every PR was
verified by compiling all six apps, by unit tests, and in several cases by
running the real Elm through `elm repl` or by mutation-testing its own tests.
None of that is evidence the bot behaves correctly in space. Each PR body states
what to watch on its first live run; those notes are the actual test plan.

The failures that mattered most this session were all found by *running the bot*
and reading the log afterwards, not by inspection — a dead guard that compiled
(#15), a bound that could never be reached (#34), a swap that disarmed the ship
under fire (#50). Inspection finds unreachable code; only running finds code
that is reachable and wrong about the game.

## In flight

| issue | what | risk |
|---|---|---|
| #50 | ammo swap disarmed the ship mid-fight — shield 98% → 13% with five hostiles on grid, 25 readings of `Stop this weapon before loading` | **high** — safety, and the swap is currently latched off for a session when it fires |
| #47 | `approach-object` / `prefer-wreck` should take comma-separated lists like `attack-object` | low |

Both touch `mission-runner/Bot.elm`; #47 was told to yield to #50 on rebase.

#50 has two signals available that did not exist when the ammo swap was written,
and it was pointed at both: `stateFromDictEntries.isInActiveState` from #39
(ground truth that a switch-off actually landed) and `incomingDamageSinceLastReading`
from #37 (the bot can know it is being shot *before* it decides to disarm).

## What landed in this batch

Each row is one merge commit; `git revert -m 1 <sha>` backs out exactly that
feature. They are independently revertable **except** the drone-restock chain,
which must be taken in reverse order (#25 → #24 → #12) because each builds on
the last.

| sha | PR | what |
|---|---|---|
| `e2b56b0` | #49 | leave when the tracker says `Dock` instead of clearing the field |
| `14e529e` | #45 | loot the gate key the client names |
| `7967548` | #43 | engage whatever the client says is shooting us |
| `1a3443a` | #42 | read `This gate is locked!` and stop pressing |
| `7931bb7` | #39 | expose the module button's dict state, log it, act on none of it |
| `0b335da` | #38 | bound the whole period the ammo swap leaves the guns off |
| `6209db4` | #37 | retreat on reported damage, not the HUD gauge |
| `5ecb441` | #36 | recognise the ship is gone, fly the pod home |
| `62b961d` | #31 | act on the client's refusal of an ammo load |
| `a5edd34` | #30 | carry EVE's game log into the reading |
| `02534d5` | #29 | read the loaded charge from the module menu |
| `2d97d21` | #23 | ESI destination — **host side only, nothing can issue it** |
| `cc47490` | #22 | confirm the drone drop by the capacity gauge |
| `304ed90` | #21 | swap ammo by target range |
| `34ab533` | #18 | learn lock range from lock outcomes |
| `3466dbe` | #20 | `stall_watch` counts readings, not decision lines |
| `1fef6bc` | #25 | home station to travel to and restock at |
| `7736c41` | #24 | make the drone restock reachable |
| `bf7b99a` | #12 | drone restock as docked maintenance |

## Known incomplete, deliberately

- **ESI route-setting cannot be used.** #23 delivered a working host side
  (`SetAutopilotDestinationRequest`), but a running bot has no channel to issue
  it: `OperateBotConfiguration` offers only `buildTaskFromEffectSequence`, and
  every `RequestToVolatileProcess` comes from `getNextSetupTask`'s closed setup
  state machine. Finishing it needs a `BotFramework.elm` change plus the
  vendored decoders. The home station (#25) uses the search bar instead.
- **The hitpoint gauge parse is diagnosed, not fixed.** It produced
  `-1021821%`, `302023%`, `2132822%`, `8362%` across eight runs, each exactly
  three times — one reading — consistent with a read landing on a reallocated
  object. Clamping cannot help: the same accident could produce `0.42` as easily
  as `21328.22`. #37 routed the retreat around it rather than trusting it.
- **`isDeactivating` still has zero observations.** #39 exposed it and logged
  it; no sample has ever caught a module switching off. #50 may be the run that
  settles it.
- **Webbing is out of scope, not covered** (#43). A webifier dealing no damage
  writes no combat line. The status line now prints `rightAlignedIconsHints` so
  the next run records the literal.

## Working agreements

- **Push only to `fork` (`smerwin/bots`).** `origin` is upstream `Viir/bots`
  and is not to be touched. Agents' worktrees have started on
  `origin/main` — which has no `CLAUDE.md` and no `tools/` — so check the base
  before doing anything.
- **One feature per PR, merged as a merge commit**, so `git revert -m 1` backs
  out exactly one thing.
- **Work in a git worktree**, not the shared checkout — several sessions run
  against `/Users/smerwin/code/bots` at once, and a broad `git add` in one
  sweeps up another's work.
- **Never run the bot, launch the client, or drive input** without being asked.
  `reload_drones.py`, `route_setter.py` and the launchers all fight the running
  session for the mouse. Reading is safe: `eve_read.py` and `eve_repl.py`'s
  read-only methods touch no input at all, and were used live during a session
  to settle #35.
- A **filesystem/issue monitor** may be armed on `~/eve-bot-logs` and the issue
  list; it wakes on a run ending, a run starting, and new issues. It is a local
  poll, deliberately not a GitHub webhook — a webhook would need public ingress
  on the machine holding the EVE refresh token, and a cloud runner would lose
  the run logs, the local `elm`, and access to the live client, which is where
  most diagnoses came from.

## Where the evidence lives

`~/eve-bot-logs/mission_run*.log` — twelve runs, ~100 MB, **not in the repo**
and not reproducible. Most of this batch was diagnosed from them. They contain
the decision log, the status line every reading, and (from #30 onward) EVE's own
game-log lines echoed as `#   game log:`.
