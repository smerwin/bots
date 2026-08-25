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
2. **Act on the fleet broadcast**, if the banner carries one of the two forms
   that have been read (below).
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

### The two broadcast forms are shaped differently

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
- **The trip home.** It returns a branch naming what is missing rather than
  `Nothing`, because `Nothing` reads as "nothing to do" and would fly past the
  session's end in silence.
- **`fleetCommanderName`** answers the first pilot in
  `follow-fleet-broadcast-from`. The header carries the real name beside `Boss`
  and `Fleet Commander` icons, but which label belongs to which role was not
  established from one capture, and a wrong answer points the drones at the
  wrong pilot.

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
| `follow-fleet-broadcast-from` | Pilot whose travel broadcasts to follow. Repeatable, matched exactly. Does **not** gate target broadcasts, which carry no sender. |
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

- **Nothing has been flown.** The decision root has never driven a client.
- **The remaining eight broadcast wordings**, as above.
- **Which header label is the commander**, as above.
- **Whether a target broadcast can name something that is not a pilot** — a
  structure, a wreck. Only a pilot has been observed, and the overview match
  would simply fail on anything else, which is the safe direction.
