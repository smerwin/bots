# Handoff

Transient state: what is in flight, what is unproven, and what to do next.
Durable facts about the client and the host live in `CLAUDE.md` — this file is
the part that goes stale, and it should be rewritten rather than appended to.

Last updated at `07e5e07` (PR #57 merged), with **run 14 in flight**.

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

## Running right now

**Run 14**, three hours, started docked at Amarr VI (Zorast). Client pid `74515`
— note the UI-root cache is keyed to it, so relaunching the client invalidates
`eve_read`/`eve_repl` until a bot run repopulates it. Console on the tailnet at
`:8787`. Settings are the launcher defaults **plus**
`decline-mission=Illegal Activity`, `home-station`, `drone-type` and the ammo
pair.

Healthy as of the last check: 981 readings, 80 kills, zero `stuck here`.

## In flight

| issue | what | risk |
|---|---|---|
| #56 | retreat fires on a corrupt `Armor reached 0%` the plausibility filter cannot catch | medium — a false retreat abandons a mission the ship was winning |
| #54 | quit a mission it cannot progress, instead of asking for help until the session ends | **high leverage** — cause-independent recovery |

#54 is the one worth doing first, and the argument is in the issue: every stall
this session had a *different* cause and the same consequence — a session that
keeps running while accomplishing nothing. Fixing causes one at a time is
endless; abandoning unworkable missions converts every future unknown cause from
"session over" into "one mission skipped".

It has a price already measured. Runs 12 and 13 were both lost to one mission
(`Illegal Activity (1 of 3) -- Retrieve Gallente Light Marines`): run 12 raised
`askForHelpToGetUnstuck` **817 times**, run 13 reached the same state in 29
readings from a *fresh* start, and recovery took a human — fly Irnin → Amarr,
dock, quit the mission, restart. Two runs and an intervention for one mission
the bot could not do and could not put down.

**The quit path, since it is not obvious and cost time to find:** the mission
card's own context menu offers only `Start Conversation / View Details /
Untrack` — **no Quit**. Quit lives in the agent conversation as
`QuitMission_Button`, behind a Yes/No confirmation.

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

## Corrections worth carrying forward

Three diagnoses in this batch were confidently wrong before they were right.
Recorded because the *mistake* is the reusable part.

- **The hull is armour-tanked, not shield-tanked.** `run_mission.sh` briefly
  shipped `run-away-shield-hitpoints-threshold-percent=25` on the reasoning that
  armour cannot be damaged until the shield is gone. It is the other way round:
  the shield rests at 0 by design, so that threshold fires on the ship's normal
  condition — run 10 raised the retreat 142 times before it was corrected live
  through the console. Back to `-1`; armour (70) and the damage guard (3500) are
  the ones that mean something here.
- **Armour reading 100% through run 7's death was not a parse failure.** It was
  a sampling artefact: the ship died between two readings. The gauge does move
  (run 9 showed 46%, 97%, 99%). The durable lesson is the one #37 acted on — a
  threshold on a sampled value can never catch a death inside one interval,
  which is why the damage-rate guard exists.
- **A stall with an obvious cause may not have it.** #53 was filed blaming a
  wreck-candidate set that only grows; a restart with empty memory reproduced
  the stall in 29 readings and disproved it. Check whether a restart clears a
  suspected state bug *before* writing the diagnosis down.

## Where the evidence lives

`~/eve-bot-logs/mission_run*.log` — fourteen runs, **not in the repo**
and not reproducible. Most of this batch was diagnosed from them. They contain
the decision log, the status line every reading, and (from #30 onward) EVE's own
game-log lines echoed as `#   game log:`.
