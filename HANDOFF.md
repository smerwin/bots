# Handoff

Transient state: what is in flight, what is unproven, and what to do next.
Durable facts about the client and the host live in `CLAUDE.md` — this file is
the part that goes stale, and it should be rewritten rather than appended to.

Last updated at `caa7f49` (PR #74 merged), with **run 22 in flight**.

## The one thing to know first

The previous handoff opened with "almost nothing merged in this batch has faced
the live client." That is no longer true, and the change is the point: **this
session ran the code, and running it found things inspection had not.**

Five features went from compiled-and-unit-tested to observed working. Three
separate bugs were found only by *reading the live client while it was still
stuck* — a mission panel layout no rule had heard of, a corrupt gauge reading
that was a transposition rather than noise, and a search that was never going to
match because the query never arrived. None of the three was visible in the
source, and two of them had already survived a green test suite.

The habit that produced all of it: when the log is ambiguous, attach to the
client and look. `eve_read.py` drives no input and is safe alongside a running
bot.

## Running right now

**Run 22**, three hours, started 17:31 **docked at Amarr VI (Zorast) - Moon 2 -
Theology Council Tribunal**. Client pid `74515` — the UI-root cache is keyed to
it, so relaunching the client invalidates `eve_read`/`eve_repl` until a bot run
repopulates it. Console on the tailnet at `:8787`.

Settings are the launcher defaults **plus** `decline-mission=Illegal Activity`,
`home-station=Amarr VIII (Oris) - Emperor Family Academy`, `drone-type` and the
ammo pair. It compiled after `caa7f49`, so it carries everything below.

Two monitors are armed: `stall_watch.py --keep-going`, and a signature watcher
that wakes the session if the bot dies and records the first sighting of
`stuck here`, `Traceback`, `EsiError`, `search results do not offer`,
`SHIP LOST`, `Abandoning the mission`, `get out get out`, plus the four that
mark the untested wind-down chain — `drone bay last seen empty`,
`@host set-destination`, `@host extend-session`, `Maintenance:`.

**The ship was repositioned by hand before this run started, and that is now a
routine step rather than an incident** — see PILOT.md, "Repositioning between
sessions".

## Proven live this session

Each of these had a "what to watch on the first live run" note. These are the
ones that can be closed out.

| what | evidence |
|---|---|
| #62 objective-chain travel step | full chain: `Set Destination → Undock → Undocking → Jump → Jumping → Warping → Destination Set → Warp to Location → Dock → Docking → Start Conversation`. The hand-in leg, flagged in the PR as inferred rather than observed, is observed |
| #73 ESI route from a bot decision | directive → host → `ESI: destination ... set (60008500)` → travel. **8 directive emissions, 1 ESI call**, so the host de-duplicates |
| #49 dock outranks the fight | 5 missions, 19–23 readings from the `Dock` label to hand-in, against run 11's 77 readings and 603 s |
| #31 game-log load refusal | fired for the first time, quoting the client: `You cannot load or unload ... while it is active` |
| #66 corrupt-armour withholding | `Readings withheld from the retreat this session: 2`, and **zero** false retreats where run 14 had three |

## Still unproven, and what each needs

- **#68, the bot-requested deadline extension.** Needs an empty drone bay: the
  extension is only asked for while a wind-down has somewhere to go, and every
  run so far has ended with the bay stocked. `@host extend-session` has never
  appeared in a log.
- **#25's home-station trip, end to end, and the drone restock.** Same trigger.
  Run 17 reached the route-setting step and failed there; nothing has yet
  travelled home and restocked.
- **#60's mission abandonment.** Never fired. Its verdict requires
  `shipUI /= Nothing` — a ship stuck *in space* — so the docked stall that
  wasted runs 16 and 17 could not have armed it, and did not.
- **#44's gate-key fetch.** Still needs a mission that locks its gate.

## In flight

| issue | what | risk |
|---|---|---|
| #75 | the search bar receives a mangled query — `Emperor Family Bureau` arrived as `eueu` | **high** — the root cause of #64 and #67, and it means every typed string is suspect |
| #72 | the ammo switch-off lands and the gun comes back on by itself | medium — the swap spends its budget on a gun that is already firing again |
| #71 | the `elm repl` test harness skips silently, so a mutation can pass unnoticed | medium — this is a test-integrity bug, and several suites use that harness |

#75 is the one worth doing first. Two runs and 1,538 `askForHelpToGetUnstuck`
came from it, and its blast radius is larger than the search bar:
`effectsToEnterString` is how the bot types *anything*.

## What landed today

Each row is one merge commit; `git revert -m 1 <sha>` backs out exactly that
feature.

| sha | PR | what |
|---|---|---|
| `caa7f49` | #74 | give the search-results branch patience before it gives up (#67) |
| `f92d5d7` | #73 | set the route through ESI, over the channel #68 opened (#69) |
| `d129b78` | #70 | let the ammo swap disarm when the gain is worth the risk (#63) |
| `10d3fdf` | #66 | stop the retreat firing on a corrupt armour reading (#56) |
| `c171317` | #68 | let a winding-down bot ask for time past the planned session end |
| `4b30e19` | #65 | drone abandonment |
| `714365f` | #62 | read the travel step from an objective-chain mission panel |
| `8ac5030` | #61 | give the home-station trip deadlines that fit the trip |
| `1a82fb7` | #60 | give back a mission that cannot be progressed (#54) |

## Corrections worth carrying forward

Five diagnoses were confidently wrong before they were right. The *mistake* is
the reusable part.

- **The hull is armour-tanked, and "armour untouched" is the tank working.** I
  read armour pinned at 100% while the shield swung as evidence the ship was
  shield-tanked. It is the opposite: in EVE damage always lands shield → armour
  → hull regardless of tank type, so a shield that swings while armour holds is
  the armour repairer keeping up. Armour below 70 means the repper is losing.
  `run-away-shield-hitpoints-threshold-percent=-1` is correct — the shield rests
  low by design, and 11% of readings sit under 25%.
- **The corrupt hitpoint reading is a transposition, not noise.** Run 14 read
  `Shield 3% / Armor 100%`, then `Shield 22% / Armor 3%`, then back. The armour
  gauge returned the value the *shield* gauge held one reading earlier — which
  is why it lands inside `[0, 100]` and no plausibility filter can catch it.
  Armour read below 70 on exactly 3 status prints in that run, and all three were
  this. Every firing of the armour retreat to date has been a false positive.
- **The host owns the deadline, and the bot's allowances were unreachable.**
  Four constants — 420 s, 120 s, 120 s, 60 s — were all measured *past* the
  planned end, and `run_bot` stopped the run the instant the end passed. Run 17
  was killed mid-trip with its own clock reading 420 s of headroom. #68 makes
  them reachable; #61 fixed a mismatch *between* them that was real but sat
  entirely inside time that could not happen.
- **Mission level follows the station you are docked at, not `home-station`.**
  The wind-down parks the ship at Oris, so the next session starts there and
  takes whatever that chain offers. Measured: 1,531,629 bounty ISK on a run
  working from Zorast against 81,750 on one working the Mabnen agent — about 9×.
  `home-station` is about *where the drones are* and nothing else.
- **The search was not failing on semantics, it was failing on delivery.** The
  live results window held `Characters (9)` and `Corporations (1)` and no
  `Stations` group, which reads as "this query matches no station". It was not
  the query the bot meant to send — see #75.

## Working agreements

- **Push only to `fork` (`smerwin/bots`).** `origin` is upstream `Viir/bots` and
  is not to be touched. Agents' worktrees have started on `origin/main` — which
  has no `CLAUDE.md` and no `tools/` — so check the base before doing anything.
- **One feature per PR, merged as a merge commit**, so `git revert -m 1` backs
  out exactly one thing. A test-data update forced by new recordings is a
  separate commit inside that PR, not a separate PR.
- **Commit before mutation-testing.** Undoing mutations with `git checkout`
  reverts uncommitted work — that cost a full reimplementation this session.
- **Work in a git worktree**, not the shared checkout — several sessions run
  against `/Users/smerwin/code/bots` at once, and a broad `git add` in one sweeps
  up another's work. The shared checkout is what a run compiles from, so
  fast-forward it before starting a run that is meant to carry a new fix.
- **Never run the bot, launch the client, or drive input without being asked.**
  Reading is always safe: `eve_read.py` and `eve_repl.py`'s read-only methods
  touch no input, and were used live three times this session to settle
  questions the logs could not.

## Where the evidence lives

`~/eve-bot-logs/mission_run*.log` — twenty-two runs, **not in the repo** and not
reproducible. They carry the decision log, the status line every reading, and
EVE's own game-log lines echoed as `#   game log:`.

Two facts about reading them that cost time to learn. The four travel labels
`Docking`, `Jump`, `Jumping ` (trailing space is the client's) and `Undocking`
appear only from run 17 onward, because #62 is what made that panel readable at
all. And run 15 is degenerate — started and cycled away seconds later, 256 lines,
never undocked — so any assertion that expects in-space readings from every run
has to skip it.
