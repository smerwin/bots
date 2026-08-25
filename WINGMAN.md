# The wingman

`eve-online-wingman` is a fleet wingman: it does not hunt, it follows a fleet
commander, acts on the commander's broadcasts, and shoots what the fleet is
shooting. It replaces `eve-online-wingus`, which did the same job on the retired
`BotLab.BotInterface_To_Host_2023_02_06` interface.

This file is what the bot is now and where it is going. `MACOS.md` and
`WINDOWS.md` are how to run bots at all; `PILOT.md` is how to operate a session.
Nothing here repeats those.

## Why it exists rather than a patch to wingus

Wingus is the last app on `2023_02_06`. Every other bot moved to `2024_10_19`,
and #332 had to teach the host to answer `SearchUIRootAddress` in the older
interface's flat synchronous shape — because the newer staged shape decodes to
an `Err` that `BotFramework.elm` writes and never reads, so the bot re-asked for
the UI root forever while the host had already found it. That host path exists
for exactly one app.

So this is a rewrite on the current interface rather than a port, and retiring
wingus is what finally lets `legacy_search_ui_root` go with it. **That removal
is not part of this work and should not be**: it belongs after the wingman has
actually flown, or the last 2023-interface bot disappears before its replacement
is proven.

## What it does now

The decision root, in order. Each arm is reached only when the one above has
nothing to do.

1. **Undock** if docked, through `undockUsingStationWindow`.
2. **Act on the fleet broadcast** — in practice only the `Target …` form,
   which is the one and only form that reaches a branch. Everything else the
   fleet broadcasts falls into a named wait. See "Live runs".
3. **Everything else** — module activation, rat combat, drones — still comes
   from the arm inherited from the combat anomaly bot, which does the three
   together.

That third point is why this is a skeleton rather than a bot. The order the
operator asked for puts `activate-module-always` ahead of the broadcast and
drones behind it; today they are one inherited lump behind both.

## The fleet window, as the client actually draws it

Read off Gal Bistot's live client through `eve_read.py` — read-only, no input,
while a run was in flight. This matters because **there is not one fleet
broadcast in any of the 120+ recorded runs in `~/eve-bot-logs`**: nothing about
this could be measured from history the way #304's bound was, so it was measured
from the client instead.

```
FleetBroadcastCont  bannerLabel  'Target Heather Hemorphite (Tristan)'
FleetWindow         entryLabel   '02:59:30 - Target Heather Hemorphite (Tristan)'
FleetWindow         entryLabel   '02:31:32 - Gal Bistot: Travel to Riramia'
FleetMember         entryLabel   'Greta Gneiss'
FleetHeader         (label)      'Fleet (5)' / 'Gal Bistot'
BroadcastButton     (tooltip)    'Broadcast: Need Backup'  (and seven more)
```

Three things follow, and each one shaped the code.

### The broadcast forms are shaped differently

**"Read" and "acted on" are not the same thing here, and conflating them is
what four live runs had to correct.** The parsing below is real — the banner,
the history and the timestamp discriminator all work — but only the `Target …`
form is wired to a branch. The travel form's wording was known from the first
capture, documented, and never dispatched. Six forms have now been observed and
one is acted on; the table under "Live runs" is the honest count.

A **travel** broadcast names its sender before a colon:
`Gal Bistot: Travel to Riramia`. A **target** broadcast names the target and its
hull and **says nothing about who sent it**: `Target Heather Hemorphite
(Tristan)`.

So `follow-fleet-broadcast-from` — an allowlist matched against the sender —
cannot filter a target broadcast at all. Anyone in the fleet can call a target.
The trust sits entirely in `accept-fleet-invite-from`, which decides whether
this ship is in the fleet in the first place. That was a deliberate decision
rather than an oversight, and the bot's own header says so.

### `entryLabel` is not the broadcast history's private name

Inside the fleet window it serves the member rows too, and outside it the drones
window uses it for drone status — which is the collision #329 had to fix in
saxrat, where the identity read grabbed a drone's row instead of the broadcast
text during exactly the readings a call is most likely to be genuine.

The `HH:MM:SS - ` prefix is the only thing separating history from members.
`textAfterBroadcastTimestamp` is that rule, with cases on both sides of it.

### The member rows are not the whole fleet

The header read `Fleet (5)` beside four `FleetMember` rows, because the boss is
drawn in the header instead of as a row. A guard reading only the rows misses
the commander — the one pilot it matters most not to shoot. `fleetPilotNames`
unions them.

**This is not hypothetical.** The captured broadcast named a fleet member:
`Target Heather Hemorphite (Tristan)`, with Heather three rows down in the same
member list. A wingman that locked and fired on whatever a Target broadcast
named would have shot her.

## What is deliberately unfinished

Each of these answers a *named* branch rather than doing something plausible,
because a bot that guesses reads exactly like one that knows.

- **Eight of the ten broadcasts.** The window's own buttons enumerate them
  (`broadcastVerbsNotYetRead`), but **a button's wording is not the
  broadcast's** — the button says `Broadcast: Spotted an Enemy` and the history
  says something nobody has observed. Only `Target …` and `…: Travel to …` have
  ever been seen rendered. An unmatched banner reaches a wait that says so.
  **A ninth is unmatched too, and for a different reason: see "First live
  run" below.** `…: Travel to …`'s wording has been known since the capture at
  the top of this file, but nothing was ever written to dispatch on it —
  `actOnFleetBroadcast` only calls `targetBroadcastPilotName`. So it currently
  reaches the same wait as the eight genuinely uncaptured verbs, for the
  opposite reason: not unknown, just unwritten.
- **The trip home.** It returns a branch naming what is missing rather than
  `Nothing`, because `Nothing` reads as "nothing to do" and would fly past the
  session's end in silence.
- **`fleetCommanderName`** answers the first pilot in
  `follow-fleet-broadcast-from`. The header carries the real name beside `Boss`
  and `Fleet Commander` icons, but which label belongs to which role was not
  established from one capture, and a wrong answer points the drones at the
  wrong pilot.

## Live runs

Four flights on three Windows hosts, all 2026-08-24, all against commit
`be47b3fc` and all following Gal Bistot's fleet. They were written up
separately and are gathered here; **each host saw something the others did
not**, which is why all three are kept rather than one being called first.

What they agree on, and neither of them found alone:

- **The bot drives a real client cleanly.** No crash, no stall and no
  `askForHelpToGetUnstuck` in any of the four sessions.
- **Undock works**, first decision, on every host.
- **No broadcast was ever acted on**, on any host, because only the `Target …`
  form reaches a branch. See the catalogue below.
- **A session that ends leaves the ship in space**, undocked and unpiloted,
  until a person docks it by hand.

### The broadcast wordings observed so far

The union of all four runs plus the original UI-tree capture. `<Sender>` is the
broadcasting pilot as the client writes them.

| observed wording | acted on? |
|---|---|
| `Target <name> (<hull>)` | **yes** — the only form with a branch |
| `<Sender>: Travel to <destination>` | no — dispatch never written |
| `<Sender>: Jump Stargate <name>` | no — verb not matched |
| `<Sender>: Align Stargate <name>` | no — verb not matched |
| `<Sender> is at location <system>` | no — verb not matched |
| `<Sender> is in position at Stargate <name>` | no — verb not matched |

Two things this table says that the button list alone did not.

**The live vocabulary is wider than the ten buttons.** `Jump Stargate` and
`Align Stargate` are not among the button-enumerated broadcasts at all, so a
capture pass driven only by clicking buttons would have missed them.

**Two of these are shaped `<Sender>: <verb>`** — the same shape as the travel
form — so `follow-fleet-broadcast-from` filters them correctly today and only
the verb is unmatched. `is at location` and `is in position at` use a third
shape again, with no colon.


### `DMC-MPC-001` — 45 minutes, Greta Gneiss

**Windows machine `DMC-MPC-001`, 2026-08-24, commit `be47b3fc`.** A 45-minute
watched smoke test — `accept-fleet-invite-from=Gal Bistot`,
`follow-fleet-broadcast-from=Gal Bistot`, `--session-duration-minutes 45` —
against Greta Gneiss, already in Gal Bistot's fleet at the time. Log:
`~/eve-bot-logs/wingman_run1.log`, 13,350 lines, ~1,467 readings, no exceptions.

**Undock works as documented.** `undockUsingStationWindow` fired within the
first handful of readings — `Click on the button to undock` then `I see we are
already undocking` — and the ship reached space cleanly.

**The travel-broadcast half of "the two forms" turns out not to be wired in at
all.** `actOnFleetBroadcast` calls only `targetBroadcastPilotName`; nothing in
it parses a travel broadcast, and `followFleetBroadcastFrom` is read in exactly
one place in the whole file (`fleetCommanderName`'s fallback guess), never
against a broadcast's sender. So despite this file listing travel broadcasts as
one of the two forms already read, a real
`Gal Bistot: Travel to Amarr VIII (Oris) - Emperor Family Academy` during this
run fell straight into the eight-unread-verbs wait:

```
+ The broadcast reads 'Gal Bistot: Travel to Amarr VIII (Oris) - Emperor
  Family Academy', which is not one of the two forms read so far -- see
  broadcastVerbsNotYetRead.
```

Four more broadcasts arrived over the run — two `Jump Stargate Bhizheba`, one
`Align Stargate Bhizheba`, one `is at location Amarr` — and all five, travel
included, hit that same wait. **Only the target form is actually implemented;
the claim of two is optimistic about the other.** This is a different kind of
gap from the eight in `broadcastVerbsNotYetRead`: those need their rendered
wording captured before anything can match them, but travel's wording was
already known and documented — the dispatch for it was simply never written.

**The trip-home gap is not just theoretical — it left the ship in space.** At
reading ~1090 (line 12372 of 13,350) the session-ending branch fired exactly as
documented:

```
+ The session ends soon and the trip to 'Amarr VIII (Oris) - Emperor Family
  Academy' is not implemented yet.
```

and then ran roughly 370 more readings with nothing else to do until the host's
own `--session-duration-minutes` deadline force-stopped it. A read-only
`tree_walker.py` check immediately afterward found a `ShipUI` and no
`StationWindow` — the ship was genuinely still in space, undocked, with nothing
watching it, until the operator checked in by hand.

**Nothing else happened.** No rats, no other pilots on the overview, no
combat, no drone activity — the whole run was one clean undock, five unmatched
broadcasts, and sitting still until the timer ran out.

### `DMC-MPC-002` — 25 and 60 minutes, Heather Hemorphite

Two runs, Heather Hemorphite, following Gal Bistot's real fleet: run 1 (25
min, `wingman_run1.log`, ended cleanly at its session-duration limit), run 2
(60 min, `wingman_run2.log`). Both compiled and ran end to end via
`botlab_host.py` on this Windows host with no crash, no stall, and no
`askForHelpToGetUnstuck` across either session — the first evidence this bot
can drive a real client at all.

**The fleet was live and broadcasting throughout, and none of it was acted
on.** Seven distinct real broadcasts came off Gal Bistot's fleet across the
two runs, none matching a form the bot currently acts on:

```
Gal Bistot: Travel to Amarr VIII (Oris) - Emperor Family Academy
Gal Bistot: Travel to Bhizheba
Gal Bistot is at location Amarr
Gal Bistot is at location Bhizheba
Gal Bistot: Jump Stargate Bhizheba
Gal Bistot: Align Stargate Bhizheba
Gal Bistot is in position at Stargate Amarr
```

**The travel broadcast is not actually matched, and that is a doc/code
mismatch rather than an unobserved wording.** This file's own prose (above)
frames `…: Travel to …` as one of "the two forms that have been read" and
implies `actOnFleetBroadcast` acts on it. Reading the source: it does not.
`actOnFleetBroadcast` matches only `targetBroadcastPilotName` — the `Target …`
form — and every other broadcast, travel included, falls straight into the
generic "not one of the two forms read so far" wait. So as shipped, the
wingman never follows the commander's travel, jump or align calls; the only
broadcast form it can act on (called targets) went completely unexercised in
both runs, because the fleet never called one. Either the doc's framing or
`actOnFleetBroadcast` needs to change — right now they disagree.

**Four of the seven are wordings not in the original capture above**: `is at
location <system>`, `Jump Stargate <name>`, `Align Stargate <name>`, and `is
in position at Stargate <name>` — the last of these is presumably the real
rendering of `broadcastVerbsNotYetRead`'s placeholder `"In Position at"`.
Worth folding into a capture pass alongside the eight already named there.

**`Visited anomalies: 0` held for the whole of both sessions.** No anomaly,
no combat, no drone activity, no locked target of any kind. So the inherited
solo-hunt fallback (module activation, rat combat, drones) is exactly as
unexercised by this as it was before these runs — two clean runs against an
idle grid say nothing about whether that arm, the called-target lock/no-shoot
branch, or the not-yet-built unlock path actually work.

### `DMC-MPC-003` — 50 minutes, Olivia Ochre

Fifty minutes, supervised, `run_wingman.sh` on Windows, Olivia Ochre. She was
already in Gal Bistot's fleet from an earlier session, so this run exercised
none of `accept-fleet-invite-from` — only inherited membership, not the accept
itself.

- **Undock worked**, first decision, cleanly: `Click on the button to
  undock.` then `I see we are already undocking.`, confirmed by the client's
  own game log (`Undocking from Amarr VIII (Oris) ... to Amarr solar
  system.`) and by the drones window becoming readable afterwards.
- **Two more broadcast wordings turned up, and were declined rather than
  guessed at**: `Gal Bistot: Align Stargate Bhizheba` and `Gal Bistot: Jump
  Stargate Bhizheba`. Both are shaped like the travel form this bot already
  reads (`Sender: verb`), so `follow-fleet-broadcast-from` filtered them
  correctly, but the verb itself is not `Travel to`, so
  `broadcastVerbsNotYetRead`'s branch fired and the bot waited rather than
  acting — exactly the fail-closed behaviour "What is deliberately
  unfinished" describes. Neither of these two is among the ten
  button-enumerated broadcasts either, so the live vocabulary is wider than
  that list alone.
- **No target broadcast, no fleet invite, no combat.** The overview named a
  different pilot every so often across the run — Ang Morage, Akon Keikira,
  Acuru Leithar, Anger Wolf, Alex667 — ordinary Amarr-hub traffic passing
  through, never more than one at a time, none hostile, none staying on
  grid.
- **The trip home did exactly what its own doc comment promised, and that is
  the most useful thing this run confirmed.** At the ~47-minute mark:
  `The session ends soon and the trip to 'Amarr VIII (Oris) - Emperor Family
  Academy' is not implemented yet.` — named rather than silent, which is
  "Where it is going / 5. The trip home"'s whole point. **The consequence is
  operational and immediate**: the host stopped the process at the planned
  50 minutes with the ship still undocked and stationary in space. Nothing
  in this bot docks it, so ending a session this way leaves a live ship
  sitting unpiloted until a person docks it by hand.
- No crash, no stall, no error anywhere in the run's ~1,197 readings.

## Where it is going

### 1. Capture the remaining broadcast wordings

One click per button, then read the history panel. That turns eight named
strings into eight matchable ones and is the single thing blocking the verb
dispatch. Small, and it unblocks the most.

### 2. Split the inherited combat arm

`activate-module-always` ahead of the broadcast, drones behind it, rat combat
behind that — the order the bot is meant to have.

### 3. Drones assisting the commander

Assist by name as the primary path, `F` on the locked target as the fallback.
Two constraints come from measurements already paid for:

- **A patience bound, with `F` behind it.** #314 removed an unbounded assist
  cascade from saxrat because the named pilot was frequently off grid, so the
  readings it spent bought nothing. Here the commander is on grid by
  definition — which is what makes assist the right primary and the bound the
  right insurance.
- **Reachable without the guns.** #326 found a turret that could not activate on
  the current target holding the decision on the other arm of its `case` for
  **262 consecutive readings**, drones out and idle, nothing landing. Whatever
  structure this uses, reaching the drone branch must not require every weapon
  module to read active first.

### 4. Unlocking fleet members

**The gesture already exists and works**: `ctrlShiftClickUiElement`
(`eve-online-saxrat/Bot.elm:14582`) presses `CONTROL` and `SHIFT` down, clicks,
and releases in reverse. The wingman ports it rather than inventing it.

Two things come with it.

**It is built on a path #303 says is currently broken.** The unlock and the
hold-fire read different sources — one the target bar, the other the overview —
and in run 50 the overview side fired on every relevant reading while the
target-bar side fired on none. A wreck sat in a lock slot for 39 unbroken ticks,
154 seconds, with rats on the same grid and `unlock 0` in the status line
throughout. Porting the mechanism without porting a fix inherits that: **the
thing that decides to unlock must read the same source as the thing that
notices the problem.**

**Logi is the exception and needs a setting.** A logistics pilot locks fleet
members deliberately — that is the job. So this cannot be an unconditional rule;
it wants a setting defaulting to unlock, which a logi fit turns off, in the
shape `assist-fleet-commander` already uses.

Note the two halves. The wingman already refuses to *lock* a called target that
is in the fleet. Unlocking handles the case where the lock happened some other
way — a stray ctrl-click, or a broadcast arriving after the lock. Both halves
read the same `fleetPilotNames`.

### 5. The trip home

`home-station`, defaulting to `Amarr VIII (Oris) - Emperor Family Academy`,
routed by ESI and then autopiloted. Take the mission runner's precedent: it
budgets 420 seconds and asks for it through `@host extend-session`, because the
allowance is otherwise measured past the planned end and can never be spent —
run 17 was killed mid-trip with its own clock reading 420 s of headroom.

This only fires when `secondsToSessionEnd` is set, so **the launcher must pass
`--session-duration-minutes`** or the trip home silently never happens.

### 6. Retire wingus, and `legacy_search_ui_root` with it

Only after this bot has flown. See the top of this file.

## Settings

| setting | what it does |
|---|---|
| `accept-fleet-invite-from` | Pilot whose invitations to accept, exactly as the client writes it. Repeatable. **This is where the trust is**: accepting means the fleet can warp this ship and call its targets. |
| `follow-fleet-broadcast-from` | Pilot whose travel broadcasts to follow. Repeatable, matched exactly. Does **not** gate target broadcasts, which carry no sender. **Not yet matched against a broadcast at all — see "First live run".** Currently only feeds `fleetCommanderName`'s fallback guess. |
| `activate-module-always` | Tooltip text of modules to keep active. |
| `home-station` | Station to return to when the session ends. Defaults to `Amarr VIII (Oris) - Emperor Family Academy`. |
| `assist-fleet-commander` | `no` keeps drones on this ship's own target. Defaults to `yes`. |
| `orbit-in-combat`, `deactivate-module-on-warp` | Inherited, unchanged. |

**These live in the launcher's profile, not in the console.** A settings change
applied through the web console lasts exactly as long as the session: it is
re-sent to the running bot and nothing writes it back, so the next launch reads
the profile block again. Four ships were pointed at a new commander through
their consoles on 2026-08-22 and were back on the old one after their next
restart.

## Not verified

One list. Two were merged, and both had gone stale in the merging — one still
said "flown once, for 45 minutes" after four flights, and one still opened
"everything downstream of nothing has flown yet".

- **The eight button-enumerated wordings.** `Need Backup`, `Need Shield`,
  `Need Armor`, `Need Capacitor`, `At Location`, `In Position at`,
  `Spotted an Enemy` and `Request That the Fleet Hold Position` have never been
  seen rendered. `is at location` and `is in position at` above are *probably*
  two of them, but the pairing is inferred from the wording rather than
  observed by clicking the button and reading the result.
- **The travel-broadcast dispatch is unwritten, not merely uncaptured.** Its
  wording has been known since the first capture and observed on every host.
  `follow-fleet-broadcast-from` has never been matched against a real
  broadcast's sender.
- **`accept-fleet-invite-from` has never driven a client.** Every run inherited
  fleet membership from an earlier session rather than accepting an invite.
- **The target-broadcast path, though implemented, was never exercised** — no
  fleet called a target during any run.
- **The inherited solo-hunt arm was never triggered.** `Visited anomalies: 0`
  held throughout; no anomaly, no rat, no locked target, no drone activity. So
  module activation, rat combat, drones, the called-target lock and no-shoot
  guard, and the unlock path are all exactly as unproven as before the flights.
- **The trip home's route, dock and ESI mechanics.** Only the "not implemented
  yet" branch has ever fired.
- **Which header label is the commander.**
- **Whether a target broadcast can name something that is not a pilot** — a
  structure, a wreck. Only a pilot has been observed; the overview match would
  simply fail on anything else, which is the safe direction.
