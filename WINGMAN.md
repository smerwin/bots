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

0. **Accept a fleet invitation** named in `accept-fleet-invite-from`, ahead of
   the docked-or-in-space split — this is `generalSetupInUserInterface`, not
   the space-only root below, since the confirmation can land while docked.
   Verified live 2026-08-25: `closeMessageBox`'s Close/OK-only matcher fell
   through to `askForHelpToGetUnstuck` on the invite's `yes_dialog_button` /
   `no_dialog_button` pair, so an invite the setting named sat unanswered
   forever until this was added.
1. **Undock** if docked, through `undockUsingStationWindow`.
2. **Head home** if the session is ending, through `sessionIsEnding`.
3. **Break off and rejoin the commander** if this ship's health or the
   incoming damage rate says to, through `retreatToTheCommander`. **Off in the
   shipped settings** — see below.
4. **Unlock a fleet member sitting in the target bar**, through
   `unlockFleetPilotInTargetBar`. See "Never shooting the fleet" below for why
   it is this high.
5. **Activate the always-on modules** named in `activate-module-always`, and
   then **manage the middle row by position** — `manageMiddleRowModules`
   (#394), bounded by `middleRowAskedReadingsBound` and reading the client's
   own `isDeactivating` before it clicks anything off (#408). Past the bound it
   hands the reading back and the status line says `GAVE UP`. Directly under
   those, and above everything below them, sits one
   window rather than an arm: `closeOnTheCommanderAfterLanding` (#397),
   which outranks 6, 7 and 8 from the reading a warp ends until the client
   reports the manoeuvre. It sits *below* the module arms on purpose —
   #394 ties the propulsion module to the client naming `Approach`, and a
   window that answers for as long as it is closing would starve the very
   module the closing is meant to run. See both sections below.
6. **Act on the fleet broadcast** — in practice only the `Target …` form,
   which is the one and only form that reaches a branch. Everything else the
   fleet broadcasts falls into a named wait. See "Live runs". It stands down
   the moment the called target is locked, which the client's own overview
   indicator decides (#389) — see below. A `Target` on an **acceleration gate**
   is read as the commander sending the fleet through it rather than as a call
   to shoot it, and is taken from here rather than from arm 10 (#393).
7. **Drones assist the commander**, `F` on the locked target as the fallback.
8. **Fire on whatever is locked**, through `fireOnActiveTarget` — unless the
   friendly fire guard is holding the trigger.
9. **Keep station on the commander** by approaching their overview row,
   through `approachTheFleetCommander` (#365). See below.
10. **Take the acceleration gate**, but only with the overview clear of rats —
    unless the commander broadcast a `Target` on the gate itself, which is
    taken from arm 6 with the drones recalled first (#393). See below.
11. **Self-defense**, through `fightPointedRatsOrReturnDrones` — fight back
    only if a rat has actually pointed this ship, otherwise sit still, and
    never while the friendly fire guard is holding the trigger.

### Keeping station on the commander is an approach, not an orbit

It started as an orbit at a distance the operator chose, taken from the
overview row's own `Orbit` context-menu flyout — that being the only way to
command a distance without changing the client's persistent default, which
#359 made a thing nothing here may touch. **That flyout does not drive.**
PILOT.md recorded it mis-clicking when a person glided into it by hand, and on
2026-08-27 all four pilots reproduced it at once: gliding into the flyout
collapsed it and the click landed on a neighbour, **Kara opened an `InfoWindow`
and Heather a `LoggerWindow`**, and every pilot spent its whole 30-reading menu
budget and fell back to the key. Per-command range is not achievable from here.

So the manoeuvre is an **approach**, commanded by a **double click on the
commander's overview row**. One reading per ask, no menu to open, nothing to
mis-click into, and no key. It closes to the client's own approach distance —
which is why the operator's call was that an approach is close enough for
station-keeping, and why `orbit-fc-range` no longer means anything.

**It was a `Q` chord first, and #387 is why it is not.** #384 built the ask as
`KeyDown vkey_Q`, click, `KeyUp vkey_Q` — the exact mechanism
`eve-online-saxrat` had deliberately removed. `cg_input` posts a key event
without stamping flags on it, so a posted `Q` carries whatever modifier state
the session holds, and with the Fn bit set that is macOS **Quick Note**: one
recorded saxrat run took the equivalent branch **1,571 times** while Notes came
to the front **241 times** with nobody at the machine. This arm is reached
whenever the commander is on grid, so it is on a hot path by exactly the same
design. The wingmen fly on the Windows hosts today, where Quick Note does not
exist, but the Mac flies bots too and `ensureShipIsApproaching` is generic.

The gesture is a port rather than an invention: `mouseDoubleClickOnUIElement`
and `effectsMouseDoubleClickAtLocation` were **absent from this app's vendored
framework** — three of the six apps had them and this was not one — and were
copied in from saxrat byte-identical, so the wingman converges on the majority
rather than growing a fourth dialect. saxrat's own
`test_saxrat_approach_by_double_click.py` is the authority for all of this.

**Behind it is a better-evidenced half.** What is still unwitnessed is the
manoeuvre rather than the gesture: saxrat double clicks a *rat's* row for
exactly this, but `ManeuverApproach` appears **nowhere** in 1.8 GB of logs, on
any row. So past `approachFleetCommanderDoubleClickAskedReadingsBound` (20) the
arm selects the commander's row and presses the Selected Item panel's own
`selectedItemApproach` instead. That name is not invented here: it is
`eve-online-mission-runner`'s, and that bot's `selectThenPanelAction` note
records it live, taking a ship from 0.0 to 585 m/s after a cascade had achieved
nothing across 180 decisions.

**Be precise about what the corpus does and does not say about that button.**
`selectedItemApproach` appears three times in the logs and *all three are the
mission runner reporting the panel offered none* — for an acceleration gate
5,843 m away. That is a statement about range, not about the name. The corpus
holds no parsed UI trees at all, so it cannot confirm any `_name`;
`selectedItemActivateGate` has zero occurrences and is shipped and working.
The evidence for the name is the sibling bot's recorded live use, and nothing
stronger is available without a run.

The unproven mechanism is primary because it costs one reading against the
panel's two; a run that has to fall back prints `FELL BACK to the panel's
Approach button`, which is the measurement that would swap them.

**This needs the commander to be on the active overview preset.** The double
click lands on an overview row, so a preset that hides fleet members leaves the
arm with nothing to click — and that is indistinguishable from a commander who is
genuinely off the grid. The bot cannot change the preset and does not pretend
to know which case it is in: the status line says `has NO OVERVIEW ROW` and
names the preset as a possible cause.

**Success is the client's own word and nothing else.** The ship UI's manoeuvre
indication reading `Approach` is what stops the ask; a dispatched click never
counts. Past `approachFleetCommanderAskedReadingsBound` (40 — twenty for the
double click and twenty for the panel, both being this file's key-over-a-click
allowance `weaponsAskedReadingsBound`) the arm hands the reading back and the
status line says `GAVE UP`, so a mechanism that turns out not to work is
visible and bounded rather than a bot that believes it is on station.

### The middle row is switched on by position, not by tooltip (#394)

**No wingman was activating any module at all**, and nothing in the bot was
defective. The settings block the four pilots are actually launched with, read
off Greta Gneiss's console on 2026-08-27, carries no `activate-module-always`
line:

    accept-fleet-invite-from=Gal Bistot
    follow-fleet-broadcast-from=Gal Bistot
    approach-fc=yes
    run-away-shield-hitpoints-threshold-percent=-1
    run-away-armor-hitpoints-threshold-percent=90
    run-away-incoming-damage-threshold=600

So `knownModulesToActivateAlways` was empty and `activateAlwaysOnModules`
correctly did nothing. Note what that failure looks like from outside: a bot
doing exactly what it was told, on a setting nobody passed, with nothing on the
bot side able to report a key that never arrived.

**And the setting was the wrong instrument anyway.** It matches tooltip text,
so it needs `readShipUIModuleButtonTooltips` to have run first, and it cannot
express either of the two things this ship wants — "everything except the
propulsion module", and "this one only while moving".

`eve-online-saxrat` already had the shape, and it is ported here whole:

    shipUIModulesToActivateAlways = middleRowLeftToRight >> List.drop 1
    propulsionModuleButton        = middleRowLeftToRight >> List.head

**The x-sort inside `middleRowLeftToRight` is the load-bearing half and is
ported rather than simplified.** `moduleButtonsRows.middle` arrives in UI-tree
order, and while that traversal is a stable depth-first walk the list it
produces is not a stable index space: the parser drops any node whose display
region it cannot read, so a slot can leave and rejoin the list without anything
moving on screen. saxrat recorded what taking "the first slot" by index cost
live — with both tank modules already running it decided three times in a row
to switch on the propulsion module, the propulsion module never came on, and a
*tank* module went off instead. An odd number of toggles landing on a
neighbour. `List.sortBy (.uiNode >> .totalDisplayRegion >> .x)` is what makes
"first in the middle row" mean the slot the setup instructions point at.

**The always-on half is not gated on a fight, and that was decided rather than
inherited.** saxrat gates its own set on `anyAttackableInOverview`, because a
rat-hunter spends most of a session crossing empty belts where a hardener buys
nothing for its capacitor. Three things make a wingman the other case. It sits
on the commander's grid rather than crossing to the next one, so the empty
stretches that gate is worth having for are not what this bot's session is made
of. It does not choose its fights — the fleet does, and the first this bot
learns of one can be a broadcast or a volley landing. And what is shooting it
may never appear on its own overview at all: the preset this bot depends on is
the one that shows *fleet members*, and `shouldAttackOverviewEntry` answers
about rats this ship would attack rather than about anything attacking it. A
hardener switched on once damage is already landing is on for the readings
after the ones that mattered, and those are exactly the readings the health
retreat is measured over. So the row is held on and the capacitor is spent.

**The propulsion module runs while approaching the commander and not
otherwise.** That is narrower than saxrat's `propulsionModuleShouldBeRunning`,
which reasons about crossing distance generally, and it is the operator's own
rule: on the instant after the ship starts approaching, off when it is not.
It reads `shipIsApproachingFromReading` — the client's own manoeuvre indication
naming `Approach` — rather than whether `approachTheFleetCommander` decided to
ask for one, so the module follows what the ship is doing rather than what the
bot last intended. That matters because that arm treats no dispatched click as
a manoeuvre either: a module tied to the ask would run through every reading of
a double click that commanded nothing. It also means an orbit is not an
approach, so a ship the client says is orbiting has the module shut down —
where saxrat's `shipIsUnderway` would keep it running.

**Client setup requirement.** The leftmost slot of the middle row **must be the
propulsion module**, and the modules to keep running go in the rest of that
row. Nothing reads a tooltip to check this, so whatever is in that slot is
treated as the propulsion module: put a hardener there and it is switched on
and off with the approaches instead of being held on. The status line prints
the row it resolved on every reading — `Middle row: prop mod off and this ship
is not approaching, keep-active [on, on].` — including the case where it found
no slots at all, so the console can tell an unfound row from a row that needs
nothing.

`activate-module-always` still works and is unchanged, for anything genuinely
tooltip-matched outside that row.

### The prop mod was being switched back on, not failing to switch off (#408)

**All four pilots stalled on this arm at once.** Twenty-three of Greta's last
twenty-three top-level decisions were one line, with Heather and Kara word for
word the same:

    Middle row: prop mod on and this ship is not approaching, keep-active [on].
    + This ship is not approaching anything. Shut the propulsion module down.
    ++ I clicked this module button 2 step(s) ago and the client has not shown
       the change yet

None of them was following the commander, and the travel arm was not at fault:
it was **unreachable**. `manageMiddleRowModules` sits directly under
`activateAlwaysOnModules` and above the broadcast arm, the drones, the guns,
the gate and the travel forms, and #394 shipped it with no bound and no
give-up, so an arm that answered `Just` on every reading owned the whole bot.
That is the same shape as the acceleration gate's #321 and the third time it
has hit this bot (#360, #395).

**The mechanism underneath it is a cycle, not a lost click.** The propulsion
module has a ten-second cycle and goes on reading `ramp_active` on for the
whole of it after being told to stop. `clickModuleButtonButWaitIfClickedInPreviousStep`
waits `moduleButtonClickSettlingSteps` — two steps, roughly four seconds — so
the debounce expires well inside the cycle, the module still reads on, and the
arm clicks again. The button is a toggle, so **that second click re-activates
it**. saxrat's "odd number of toggles" hazard, arriving through timing rather
than through position.

**The instrument that answers it is `isDeactivating`**, in this app's own
vendored parser (`ShipUIModuleButton.stateFromDictEntries`) and read by this
bot zero times before now. `isActive` reads `ramp_active`, which cannot say
whether a click took while a cycle is running; `isDeactivating` is the client
saying the switch-off landed. A propulsion module the client reports as
deactivating is now left to finish, however long `isActive` stays true.

**Absent is not `False`, and the arm has three answers rather than two.** The
parser's own doc block is explicit that an entry which did not decode is
missing rather than false, that the two are different facts, and that only one
of them is safe to act on — the neighbouring `ramp_active` is a duty cycle and
not an on/off state, and misreading it that way is what #34 cost. So
`isDeactivating = Nothing` gets its own answer and buys no click. The cost is
stated: on a build that does not carry the entry the propulsion module is never
switched off, which loses the module and keeps the bot. The guard is on the
**shutdown only** — switching a module on has no deactivation transient to
misread, so a cold module is still clicked whatever the entry says.

**A warp or a jump is left to the manoeuvre.** "Not approaching" is true in
warp too, and the wingman's own root has no warp gate above this arm, so
without the guard every reading of a warp met "module on, not approaching, shut
it down" — clicks that change nothing about a warp already under way and that
re-arm a module still running its cycle out, so the ship would drop out of warp
with the prop mod lit.

**Aligning is deliberately not special-cased, because the client does not name
it.** `ShipManeuverType` has `Warp`, `Jump`, `Orbit` and `Approach` and no
`Align`: a ship lining up reads no manoeuvre at all, which is the same
`Nothing` as a ship floating still. It is also the state where shutting the
module down is worth the most, since the extra mass is what makes aligning
slow — #394's own argument — so the arm goes on asking there, and what stops it
repeating is `isDeactivating` and then the bound rather than a manoeuvre test
that would have to guess.

**And the arm is bounded.** `middleRowAskedReadingsBound` is
`weaponsAskedReadingsBound` — twenty, the allowance every other per-reading ask
in this file gets. Past it the arm answers `Nothing` rather than parking on
`askForHelpToGetUnstuck`, so the broadcast, the drones, the guns, the gate and
the trip home all still run, and the status line carries the give-up:

    Middle row: prop mod on and this ship is not approaching, keep-active [on].
    GAVE UP after 20 readings clicking a middle-row module the client never
    showed the change on.

`middleRowAskedReadings` advances only on the three answers that actually click
and holds once the budget is spent, so the number in that line counts readings
this arm asked on rather than readings it happened to be reached on — #389's
correction, applied here from the start. It resets on every reading the row
wants nothing, which is what stops a give-up being permanent: a ship that
starts approaching again wants the module it already has running, so the row
needs nothing and the next stretch gets the whole allowance back.

**One counter covers both halves of the row, and that couples them.** A tank
module that can never be switched on spends the budget and the give-up then
covers the propulsion module too, so such a ship stops managing its prop mod
for as long as that slot reads inactive. Accepted rather than overlooked: the
arm answers one `Just` and so needs one give-up, and the cost is a module left
alone rather than a bot that stops following its commander.

### Clicking a module twice inside its cycle is a toggle, not a retry

#408 is one instance of a general mismatch and only that instance was fixed.
`clickModuleButtonButWaitIfClickedInPreviousStep` waits
`moduleButtonClickSettlingSteps` — two steps, roughly four seconds — before it
will click a module button again, and its own message says what a second click
does: *"wait rather than click it again, which would toggle it back."* Any
module whose cycle is longer than that window will still read unchanged when
the window expires, and the retry is a toggle. Four other arms in this file
click module buttons through that helper, and none of them was touched:

- **`deactivateModulesForWarp`** is #408's shape exactly, in the other
  direction. It clicks a module the operator named in `deactivate-module-on-warp`
  while `.isActive == Just True`, which is the same "still cycling" reading
  that trapped the propulsion module — so a ten-second module would be switched
  off, still read active, and be switched back on mid-warp. It is unreached in
  the shipped settings (`deactivateModuleOnWarp` defaults to `[]`), but it is
  live code: `warpAwayFromDanger` calls it on the retreat, not only the
  inherited root. Reading `isDeactivating` there is the same one-line change.
- **`activateAlwaysOnModules`** and the always-on half of the middle row click
  in the *activation* direction, gated on `moduleIsActiveOrReloading`. The
  transient is the other one — a module told to switch on does not carry
  `ramp_active` until it starts cycling — and nothing has measured how long
  that takes on these fits. Both are now bounded (the middle row by #408, the
  tooltip path by its own emptiness in the shipped settings), so the failure
  costs readings rather than a session.
- **`fightUsingDronesAndModules`** and **`fireOnActiveTarget`** click top-row
  weapons whose `isActive` *is* the duty cycle: `ramp_active` reads `False` for
  part of every cycle on a gun that is firing, which is what saxrat's #76 and
  #286 measured. So a gun already firing can be clicked and silenced. The guns
  are bounded by `weaponsAskedReadingsBound`, so this costs twenty readings and
  a `GAVE UP` rather than a session, and repointing them at `isInActiveState`
  is a behaviour change on the arm that shoots — deliberately not made here.

### On landing, closing outranks the fight — for as long as the client is silent

That arm was **last** in the root, and the root's own comment above
`retreatToTheCommander` already said why that is fatal: each of the fighting
arms answers `Just` for the whole of a fight and the first arm to answer ends
the reading — the broadcast banner does not clear while a target is called
(#360), the drone arm answers on every reading a drone idles (#326), the guns
answer on every reading a weapon is not cycling. So on any grid worth landing
on the approach was unreachable, and the ship landed at range, opened fire and
never closed. A wingman at range on its own is outside logistics and outside
support; failing to close is what gets it killed.

**A permanent hoist would invert the problem**, since the ship would then never
fight while the commander was on grid and unapproached. What ships instead is a
window: from the reading the warp ends (`warpJustEnded`, the corrected trigger
#205 gave this bot) until the client names the manoeuvre `Approach`, the close
outranks the three fighting arms. After that the arm keeps the place #365 gave
it, below the guns and above the gate, and station-keeping is unchanged.

**The window is sized by what ends it rather than by a number**, which is #194's
own history read as a warning — its arrival window was first sized by guesswork
and the corpus later contradicted it by a wide margin. The closing condition is
the client's own word, the same read that already stops the ask. What bounds a
window nothing ever closes is not a new number either: only the five answers in
`approachFleetCommanderAnswersThatSpendAReading` can hold a reading in this arm,
and those are exactly the answers the counter advances on, so the fight can be
outranked for at most `approachFleetCommanderAskedReadingsBound` readings and
then the give-up hands every reading back.

**Below the two arms that take the ship off the grid**, which is #364's measured
ordering: a ship past its threshold breaks off and does not close on anyone
first. Below `unlockFleetPilotInTargetBar` too, whose veto on the guns is
independent of its placement, and below `activateAlwaysOnModules`, whose answers
stop the moment the hardeners are on.

**It does not depend on `orbit-fc`, and that is a behaviour change for every
existing settings string** — including one that switched the key off
deliberately. A survival behaviour is not opt-in. With `orbit-fc=no` the bot
closes once per landing and then leaves station-keeping alone, and the status
line says so rather than printing a bare `off`.

**The status line carries the window on every reading it is open**, as
`CLOSING SINCE LANDING (this outranks the fight until the client names the
manoeuvre 'Approach')`, because from outside the tree a reading in which the
close outranked the fight and one in which it merely came last read identically.

### Why the guns are their own arm, below the drones

Reported from the field on 2026-08-25: travel and locking worked, engaging a
locked target was a D-. The cause was ordering, not any rule being wrong.

**A `Target` broadcast's banner does not clear when the target is locked.** It
stays up for the rest of the call. So the broadcast arm answered "lock it" on
every reading for as long as the banner was up — and since the first arm to
answer ends the reading, the bot never reached arm 5 or below while a target
was called. It locked exactly what it was told to, repeatedly, and then never
shot it.

Nothing else would have fired either. Before `fireOnActiveTarget`, the only
thing in this bot that activated a weapon was `fightUsingDronesAndModules`,
reachable only through `fightRatsIfShipIsPointed` — which answers nothing
unless a rat has pointed *this* ship. A target the commander called is not
pointing anybody, so even a clear path down the root would have ended in
silence.

The guns sit **below** the drones and never above them, which is #326's rule
restated: reaching the drone arm must not require the weapons to read active
first. That issue measured a turret that could not activate holding the
decision for 262 consecutive readings with the drones out and idle.
`weaponsAskedReadingsBound` (20 readings) is the matching bound on this side,
and a give-up is reported in the status line rather than by falling silent —
`fireOnActiveTarget` hands the reading back so the drones, the gate and the
trip home all still run.

One more thing had to change with it: `fightPointedRatsOrReturnDrones`
recalled the drones whenever the ship was not pointed, which with a called
target locked would have fought the assist on every reading and left the bot
pulling drones in and sending them back out for as long as the target lived.

### "Already locked" is a question for the overview, not the target bar

#360 fixed the ordering above by standing the broadcast arm down once the
called target was locked. **#361 then decided "locked" the wrong way and #389
is what that cost.** On 2026-08-27 all four pilots looped on

```
+ Lock the called target 'Centus Black Ops Agent'.
++ Failed to continue context menu for now (Could not find menu entry with
   text equal 'Lock Target'.)
```

while the same status lines reported **3, 2 and 1 targets already locked**. One
cause, two symptoms: the arm asked `lockedTargetNamed`, which matches the
broadcast's name against the *target bar's* rendered labels; the match failed;
so the arm answered "lock it" every reading — and the cascade could not
succeed, because the thing was already locked and the client offers `Unlock
Target` for something in the bar. Everything below the broadcast arm — the
drones, the guns — was unreachable for the whole call, which is #360's defect
arriving by a different route.

**The bar cannot answer that question and #303 already knew why.** Read off a
live client with a rat locked:

```
TargetInBar -> ['Tower Sentry', 'Sansha I', '20 km']
```

The name is **split across labels at a wrap point**, and `targetTextsCarryName`
asks whether any *one* label carries the whole name. A two-word name — which is
most of them, `Centus Black Ops Agent` included — is invisible to it however
long it sits in the bar.

**So the recognition asks the client instead.** `OverviewWindowEntry.commonIndications.targetedByMe`
is set from the `targetedByMeIndicator` icon the client draws on a row this
ship has locked, and `calledTargetIsLocked` reads it off the row the broadcast
named — the same row `lockCalledTarget` right-clicks, through the same
`overviewEntryForPilot`, so the half that decides and the half that acts cannot
end up on two different objects. That is #303's own prescription, applied here.

The bar is kept as a *second opinion* rather than dropped: either signal alone
stands the arm down. The two go quiet in opposite directions — the bar on a
wrapped name, the icon if this client draws it under some other name, which
nothing here has yet watched — and a false stand-down costs one reading falling
through to the drones and the guns, which is where the reading was wanted
anyway.

### The weapons budget counts asks, not readings

The same run reported

```
Weapons: GAVE UP after 46 readings asking a weapon to come active on a
locked target.
```

on three pilots — 46, 36 and 50 against a bound of 20 — **for guns that had
never been asked once**. `weaponsAskedReadings` advanced from state alone
(something locked, some top-row module not cycling) without asking whether
`fireOnActiveTarget` had run, so while the broadcast arm above held every
reading the budget drained anyway and the arm was given up on before it was
ever reached.

The fix is the discipline #382's approach arm already uses, and its own
mutation matrix had caught this exact hole: the counter advances only on
`weaponsAnswersThatSpendAReading`, which is `[ ActivateAWeapon ]` — the one
answer of `weaponsStep` that dispatches anything. The friendly-fire veto and
"is there a ship UI" became answers of that rule rather than conditions wrapped
around it, because a refusal the counter cannot see is a reading charged to a
budget nobody spent. `describeWeaponsAsk` cases over the same six answers, so
the status line reports the decision taken rather than a fourth restatement of
it, and prints the bound beside the count.

What this still cannot see is a reading taken by an arm *above* the guns: the
memory update runs before the decision and has no view of it, so the drone arm
holding a reading still charges the budget when a weapon happens to be silent
at the same moment. That over-counts rather than under-counts, which is the
safe direction for a bound whose job is to stop an unbounded ask.

### A `Target` broadcast on a gate is the fleet being sent through it

#393. There is no fleet broadcast that says *take this gate*. `Align to` was
the first choice and **does not name the gate**, so nothing in the broadcast
tells a wingman which object was meant; `Target` is the only form carrying an
object's identity. So on an acceleration gate it is read as licence to
**activate** the gate rather than as a call to shoot it. That is a deliberate
reinterpretation of one verb where the named object is a gate, and nowhere
else — everything that is not a gate still goes to the lock, unchanged.

Pointed at a gate the lock was a wasted cascade at best, and by #389's own
argument it could not succeed either: a structure that will not lock never
reads `targetedByMe` and never appears in the bar, so the arm re-asks forever.

**Most of the machinery already existed.** `overviewEntryIsAnAccelerationGate`,
`nearestAccelerationGateOnOverview` and `accelerationGateStep` — which presses
the Selected Item panel's own `selectedItemActivateGate` and bounds its asking
— are all this bot's already. What is new is a branch ahead of the lock that
recognises the called row as a gate and hands it to that machinery, rather than
a second copy of it: `takeTheAccelerationGate` is one select-and-press shared by
the called gate and the nearest one.

**The check is ahead of the lock, and that is about #366 rather than about
today.** That change replaces the cascade with a ctrl-click on the broadcast
banner, and a ctrl-click will lock whatever the banner refers to — so a gate
check placed behind the lock would be dead the moment it lands. Same reason #366
gives for keeping the fleet-member guard ahead of the click; and that guard is
transparent here, since it refuses a name in `fleetPilotNames` and a gate is not
a pilot.

#### The call overrides #348's rats guard, and nothing else does

`accelerationGateStep` refuses a gate while rats are on the grid, because taking
one mid-fight "abandons whatever the fleet is still fighting and leaves the
commander a ship short in the pocket this bot just left". **A `Target` broadcast
on a gate overrides that hold**: there are occasions when the fleet must take a
gate with rats still up, and the FC calling it is the explicit instruction to
send the crew through. The guard exists to stop a wingman wandering off on its
own judgement; it is not there to overrule the FC.

**Scoped to the called gate.** `gateMayBeTaken` is one rule with three readers —
the arm, the memory update's counter and the status clause — and
`accelerationGateStep` hands it `calledByTheCommander = False`, so absent a
broadcast #348's guard is exactly what it was. The discriminating case is one
grid asked twice: same rats, same gate, same drones, the called arm acting and
the uncalled arm staying to fight, so what separates the two answers is the
broadcast rather than the fixture.

#### The drones come home first, and the recall is bounded

`accelerationGateStep` recalls nothing — it presses Activate Gate directly. That
was survivable only while the guard required a clear grid: with rats up the
drones are out essentially by construction, since `dronesAssistTheCommander` is
what puts them there, so taking a called gate without recalling would abandon
them every time. CLAUDE.md records run 1 losing ten drones to exactly that
shape.

So the called-gate path recalls first, through the **`returnDronesToBay` every
other departing arm already uses** rather than a second copy of one.

**The bound is what keeps the FC's call from being lost.**
`calledGateDroneRecall` is saxrat's `droneRecallUnansweredTicks` in this bot's
vocabulary: the counter starts from the first recall the client did not answer,
resets whenever the in-space count falls (a partial recall is the client
answering), holds once the give-up is reached — because giving up is what stops
the asking, and a reset would have the ship alternating forever between
abandoning its drones and recalling them — and the give-up **names itself on
every reading it declines**, which is the other half of #11. Abandoning drones
to make a called gate is a certain, bounded, recoverable cost; abandoning the
commander's gate to wait on drones that are not coming is not.

`calledGateDroneRecallGiveUpReadings` is **60, copied rather than chosen**. It is
the only drone-recall number in this repository with any evidence behind it, and
CLAUDE.md records it having never been reached in a recorded run of either bot
that carries it. This bot has no corpus of its own for it: no wingman run has
ever recalled drones before a gate. The tension is stated rather than hidden —
60 readings is a long time to hold an FC's gate — and the direction to move it on
evidence is *down*, from a run that shows what a recall this fleet's drones
actually answer in.

**The counter counts readings the arm asked on**, taken from the shipped rule
rather than restated beside it (#102). It over-counts only in the direction #393
chose: an arm above the broadcast holding the tree spends budget the recall did
not use, which gives up on the drones sooner and takes the gate.

#### The decision line says which path it is on

`The overview is clear of rats -- activate the acceleration gate` is **false**
when the gate was called mid-fight, and a log claiming a clear grid on readings
that had rats on it is worse than no line at all. So the called press has its own
wording naming the broadcast as the authority, the uncalled one keeps the
sentence an operator already greps for, and the recall says it is holding the
gate for the drones — otherwise the hold is a pause nobody can account for.

```
+ The commander broadcast a Target on the acceleration gate 'X' -- that is the fleet being sent through it, so take it.
++ Holding the called acceleration gate until the drones are back -- 3 of 60 readings of recall so far.
++ The commander called this acceleration gate -- activate it and take the fleet through, rats on the grid or not.
```

#### Unverified, and it is the thing to establish first

**Nobody has captured a `Target` broadcast naming an acceleration gate.** Two
string derivations have to agree for the row to be found at all —
`targetBroadcastPilotName` parses the name out of the banner, and
`overviewRowsForPilot` matches it against `objectName` by exact equality — and
whether a broadcast on a gate renders the string the overview carries is
**unknown**. It cannot be settled without a client, so what the change does
instead is refuse to do nothing silently about it.

`calledObjectOnOverview` answers four things rather than two, and the two
silences are kept apart: `CalledNameNamesNoOverviewRow` is what a name the
overview does not carry looks like, and `describeCalledObject` says so in the
status line on every reading —

```
Called target 'X': NO OVERVIEW ROW names it, so nothing here can lock it and
nothing here can tell whether it is an acceleration gate. The active overview
preset may be hiding it, or the banner's own wording may not be the overview's
Name cell.
```

That is the failure direction if the two derivations disagree: the gate reads as
an ordinary called target, goes to the lock path this bot takes today, and says
`is not on the overview` — loudly, and no worse than before this change.

The fourth answer is `CalledGateIsNotDisplayed`. A gate row that is in the tree
and not drawn reports a plausible region belonging to whatever was recycled into
its place, so this arm will not click it and hands the reading back instead —
the drones and the guns still get their turn, which is #389's own closing note.
Note this is the one place a `_display` filter belongs and `calledTargetIsLocked`
is where it does not: that read uses no region, this one hands a row to a click
that ends in a gate being activated.

**Verified without a live client**, in
`tools/macos-host/tests/test_wingman_called_gate.py` (44 cases). The rules are
executed through the real `Bot.elm` in `elm repl` and the readings they are asked
about go through the real `EveOnline.ParseUserInterface`; the classification is
asked as one equality per answer, so a rule answering two things at once — or
none, which is what a fixture that never arrived produces — fails rather than
passing on whichever constructor a case named; and the recall counter is folded
over whole sessions rather than asked once. **Neither parser needed a change.**

What to watch on the first run that meets one: `Called target 'X': it is an
ACCELERATION GATE` in the status line, then the recall's own
`I see there are drones in space. Return those to bay.`, then the press. A run
where the clause reads `NO OVERVIEW ROW names it` while a gate is plainly called
is the unverified premise failing, and is the one thing a capture pass with
`eve_read.py` would settle outright.

### A called target that dies leaves the banner naming it

#395, and it is the third variant of one defect. #360 fixed *the banner names a
target that is already locked*; #389 fixed *the target is locked and not
recognised as locked*; this is **the target is not there any more**, and that
branch had never had an answer other than waiting.

On 2026-08-28, on `fbf4c2e`, three of four wingmen killed **37 rats each** and
stopped together, all repeating

```
+ Lock the called target 'Centus Black Ops Veteran'.
++ 'Centus Black Ops Veteran' is not on the overview.
+++ Wait for progress in game
```

25 of each in a 400-line scrollback, `Weapons: nothing locked`, nothing below
the broadcast arm running. **Identical kill counts across the three is the
tell** — they stopped at the same moment, when the commander's called target
died.

**The broadcast banner is a last-broadcast display and never clears**, which is
the fact all three variants are about. With the rat dead, `calledTargetIsLocked`
is false because the thing is gone, `bringCalledTargetUnderFire` answered
`Just (lock it)`, and `lockCalledTarget` — finding no overview row —
answered `waitForProgressInGame`, a wait with no bound and no give-up. The arm
sits above the drones, the guns, the gate and the approach, and the first arm to
answer `Just` ends the reading, so all of them were unreachable for the rest of
the session or until the FC called something else.

#### Why the counter rather than the latch

The issue offers two shapes and calls the latch — `fleetBroadcastFollowed` for
the `Target` form — the more general fix. **What shipped is the counter, with
the latch's identity half folded into it**, and the reason is what the two forms
ask for.

`fleetBroadcastFollowed` bounds a **one-shot** action: the ESI route ask goes out
once per banner and repeating it is pure waste, so "this banner has been acted
on" is a complete answer. A target call is a **standing** instruction. #360's own
fix is that the arm answers `Nothing` while the target is locked and `Just` again
the moment it is not, because a lock can break while the call is still live — so
a latch fired when the arm first acts would stop the bot re-locking a target it
lost. The only event a latch could honestly fire on here is *this call names
nothing on the grid*, which is the counter's verdict; the latch and the counter
are the same rule, one reading apart.

What the latch does contribute is the **name**.
`BotMemory.calledTargetGone : Maybe { calledTarget, readings }` carries the
called name beside the count, so a second call is never given up on with none of
its own readings spent — a bare counter would hand one call's arrears to the
next, which is the shape #145's gate counter was filed on.

**What clears it** is one clause covering all three ways the state ends:
`calledTargetGoneAfterReading` answers `Nothing` on any reading
`calledTargetWithNoOverviewRow` does not answer `Just` for — the row coming back,
the commander calling something else, and the banner going away. A different call
starts from one rather than inheriting.

#### No overview row is not evidence the target is dead

This section's own title says *a called target that dies*, and that is the
incident rather than the state. **Three things produce `CalledNameNamesNoOverviewRow`
and only one of them is death:**

1. the object really is gone — run 395's rat, killed by the fleet;
2. **this pilot's overview preset does not show it.** Four characters fly this
   bot and their presets are not identical, so a target one wingman can see is
   one another has no row for at all;
3. the wording the banner carries is not the overview's Name cell, which is
   #393's own unverified premise about a called gate.

The give-up is correct for all three — there is nothing more this arm can do
about the call, whichever it is — but **what it means is "nothing here can act
on this", not "it died"**, and reading it as the second is what would make a
wingman that cannot see a target conclude the fleet had killed it. #366 is the
change that acts on that distinction: ctrl-clicking the broadcast banner needs
no row, so causes 2 and 3 stop being dead ends and the give-up comes to mean
*the banner was tried too and nothing locked*. See "The banner is ctrl-clicked
to lock, and it is tried precisely when there is no row" below.

**The virtualised row is a fourth case and it lands elsewhere.** A row scrolled
out of view is still in the tree and `overviewRowsForPilot` filters on the Name
cell rather than on `_display`, so it answers `CalledObjectIsNotAGate` and the
lock has a row to work with — one whose region belongs to whatever was recycled
into its place, which is CLAUDE.md's "worse than a no-op". That is a hazard for
the *cascade* rather than for this counter, and it is one more reason the
ctrl-click is the primary path rather than the fall-back.

#### The bound is three, and what it bounds is a parse rather than a range

`CalledNameNamesNoOverviewRow` is **not the overview virtualising**, as above.
This state is the stronger one — no window holds a row
with that name at all — which a live target reaches only by leaving the
overview's own range filter, through a preset that does not carry it, or through
a reading whose overview did not parse.

So the number bounds a parse that missed, and three is the count this repo
already gives that doubt: CLAUDE.md's ship-loss signal wants three consecutive
readings of an empty module row *"because the parser drops any slot whose display
region it cannot read, so one reading finding none may be a parse that missed"*.
Both costs are small and asymmetric — being late costs three readings of this arm
holding, being early costs one lock not issued on a target whose row is back next
reading, and the count resets the moment it is, so the arm re-arms itself. It
sits far below `weaponsAskedReadingsBound` (20) and
`accelerationGateRefusesThisShipTicks` (40) deliberately: those bound a *click*
the client keeps refusing, where this bounds a reading with nothing to click.

#### One rule, both readers, and the give-up says so

`calledTargetWithNoOverviewRow` is the arm's own precondition —
**including the fleet-member guard**, since `actOnFleetBroadcast` refuses a call
on a fleetmate above this arm and those readings are not readings this arm spent
— and `updateMemoryForNewReadingFromGame`, which never sees a decision, asks it
rather than restating it. The same arrangement `askingForTheCalledGateRecall`
already uses next door, for #145's reason.

**It also makes #393's own stated fall-through true.** That section says a
called gate whose banner text is not the overview's Name cell "falls through to
the lock path this bot takes today rather than to a wait" — and the lock path
*was* a wait, unbounded, for exactly the same reason. So the premise #393 ships
unverified now costs three readings and a named clause rather than the session.

The give-up hands the reading back, so a `Nothing` carries no decision line and
`describeCalledObject` is the only thing that says it happened:

```
Called target 'Centus Black Ops Veteran': NO OVERVIEW ROW names it, ...
  No row has named it for 2 of 3 readings; past that this call is left alone.
Called target 'Centus Black Ops Veteran': NO OVERVIEW ROW names it, ...
  GIVEN UP ON after 4 readings naming no row -- the banner never clears, so this
  call is left alone and the drones, the guns and the gate get their turn. A new
  broadcast starts this over.
```

**Verified without a live client**, in
`tools/macos-host/tests/test_wingman_called_target_gone.py` (34 cases). The rules
are executed through the real `Bot.elm` in `elm repl` and the readings they are
asked about go through the real `EveOnline.ParseUserInterface`; the counter is
folded over whole sessions rather than asked once; and the property asserted is
#360's own — **the reading falls through the whole broadcast arm** — with a
control in the same call that must still act, so a rule answering `Nothing` for
everything cannot pass. The strongest of them folds the shipped
`updateMemoryForNewReadingFromGame` over a session of #395's own reading and asks
the shipped arm about the memory that fold produced, so the counter, the verdict
and the arm are executed together. Confirmed by mutation, eighteen of them, each
failing a named case, listed in that file — including the give-up dropped, which
is #395 restored, and the count never cleared, which is the next call ignored.
**No parser change was required.**

**Unverified: any of it running.** No run has been flown since. What to watch on
the first one that loses a called target: `No row has named it for N of 3
readings`, then `GIVEN UP ON after N readings naming no row`, with ordinary
decisions — drones, guns, the gate — resuming underneath it on the same readings.
A run that meets one and never prints either clause means the counter is not
being written, which is the direction this fails silently in. In the other
direction, the clause appearing on a call the bot could have acted on would mean
the row was there and `overviewRowsForPilot` did not match it. And **whether a
live target's row can vanish and return at all** is still unread; if it can, the
tell is the count climbing to 1 or 2 and resetting over and over while the bot
goes on locking the target normally.

### The banner is ctrl-clicked to lock, and it is tried precisely when there is no row

#366. Holding Ctrl over the fleet broadcast's `Target:` display locks the object
the broadcast refers to — one dispatch, no context menu, no overview lookup.
What it replaces is `lockCalledTarget`'s long way round: find the row by matching
`targetBroadcastPilotName`'s parse of the banner against `objectName` by **exact
equality**, then run a `Lock Target` cascade on it.

Three costs went with that:

- **it needed the target on the overview**, so a target outside this pilot's
  active preset was one this wingman simply never shot;
- **it matched by exact string equality** between two derivations that both have
  to agree, about an object the client itself already knows the identity of;
- **it spent a cascade**, which is where this bot's readings and its bugs go —
  #329's `entryLabel` collision, `contextMenuStuckTicks`, #285's unbounded
  loot-window branch.

#### It is attempted *because* there is no row, not in spite of one

The rule is `lockCalledTargetStep` and its first clause asks only whether the
banner offers a click and whether the budget is spent. **It does not ask whether
a row exists**, and a version that did — "find the row, and ctrl-click the banner
if there is one" — would change the gesture and leave the defect exactly where it
was: causes 2 and 3 above are precisely the readings that have no row, and they
are the readings this exists for.

So a call whose name no overview row carries is now **clicked** rather than
waited on, for every reading #395's give-up allows. That give-up is asked in
`bringCalledTargetUnderFire`, before the lock, and fires at
`calledTargetGoneReadings` (3) — which sits *below*
`bannerCtrlClickAskedReadingsBound` (5), so every reading it allows is a reading
the banner was clicked on, and it comes to mean *the banner was tried too and
nothing locked* rather than *there was no row, so we assumed it died*. It still
hands the reading back, which is still right once there is nothing left to try.

#### The two guards stay ahead of the click, by placement

A ctrl-click locks a **fleet member** as happily as a rat, and it locks an
**acceleration gate** as happily as a ship. Both checks are ahead of the click
because of where they sit rather than because the lock consults them:

- `actOnFleetBroadcast` refuses a called target named in `fleetPilotNames`
  before `bringCalledTargetUnderFire` is called at all — which is why
  `targetBroadcastPilotName` is still needed for the *decision* long after the
  lock stopped needing it;
- `bringCalledTargetUnderFire` dispatches on `calledObjectOnOverviewFromReading`
  and hands a called gate to the gate machinery before it builds the lock (#393,
  whose own text says a gate check placed behind the lock "would be dead the
  moment that lands").

`lockCalledTarget` names neither, and a case asserts that: a copy of either
inside it would be a second answer that could disagree with the first.

#### The cascade is kept as the fall-back, because of what is unknown

**Whether the ctrl-click works when the object is out of lock range, already
locked, or is a structure rather than a ship is not established** — nobody has
captured it, and there was no client on the machine this was written on. #366
asks for a capture pass with `eve_read.py` before the fall-back is wired, and
that pass has not happened.

So the fall-back is reachable on **any** failure to lock rather than on a
diagnosis this bot cannot make. Two ways in: the banner offering nothing to
click (absent from the reading, or a visible region too small for
`mouseClickOnUIElement`), and `bannerCtrlClickAskedReadingsBound` readings of
clicking with the target still not reading locked. *Nothing happened* and
*cannot be locked* want different answers and this bot cannot tell them apart,
so it treats both as the first and says which path it is on.

**The cascade cannot serve a call with no row**, which is why the two dead ends
are separate clauses in the status line rather than one:

```
Lock: CTRL-CLICKING THE BROADCAST BANNER, asked on 2 of 5 readings -- one dispatch, no context menu and no overview row needed.
Lock: THE BANNER CLICK DID NOT LOCK IT in 5 readings, so the overview row's own 'Lock Target' cascade has it instead. A new call starts the click over.
Lock: no banner in this reading to click, so the overview row's own 'Lock Target' cascade has it.
Lock: NOTHING HERE CAN LOCK IT -- no broadcast banner to click and no overview row to open a menu on.
```

The clause speaks only on readings the lock is actually the question — not on a
locked target, a called gate, a fleetmate, or a call #395 has given up on —
because a clause claiming a click on any of those is a decision this bot did not
take.

#### Five, and the budget counts asks

`bannerCtrlClickAskedReadingsBound` is not a measurement; this bot still has no
corpus of its own. What sizes it is what the click *is*: one dispatch with no
menu to render and no flyout to wait on, so unlike a cascade it either reaches
the client or it does not, and the readings are for the client's own lock-in
time. It sits far below the three bounds here that budget a cascade
(`weaponsAskedReadingsBound` 20, `fleetMateWarpAskedReadingsBound` 30,
`accelerationGateRefusesThisShipTicks` 40) and above `calledTargetGoneReadings`
(3), for the ordering reason above.

**The counter advances only on readings the click is asked on**, which is #389's
lesson and this bot has already paid for it once — `weaponsAskedReadings`
advanced from state alone and reported `GAVE UP after 46 readings` on an arm that
had never been asked. `bannerCtrlClickThisReading` is the shipped rule answering
`CtrlClickTheBroadcastBanner`, asked by `updateMemoryForNewReadingFromGame`
rather than restated beside it.

It **holds** rather than clearing on a reading that did not ask, which is the one
place it differs from `calledTargetGone`'s shape: past the bound the rule stops
asking, so a counter that cleared there would clear on the very reading the bound
was reached, and the fall-back would last exactly one reading before the click
was re-issued for ever. It clears when the lock is no longer the question at all
— the target coming up locked, a different call, a gate, a fleetmate, #395's
give-up, or the banner going away — and the name travels with the count, so a
second call is never sent straight to the cascade on the first call's arrears.

#### The chord has one copy now

`ctrlClickEffects` is the gesture: `KeyDown` Ctrl, the click, `KeyUp` Ctrl. It
was written inline in `fightRatsIfShipIsPointed` (the pointed-buff path) and that
copy is folded into it rather than left beside it — a chord built wrong is one
the client reads as a plain click, which locks nothing and says nothing, so two
copies are two chances for one to drift. saxrat's `ctrlShiftClickUiElement` is
the two-modifier version of the same gesture and is the *unlock*, which is what a
Shift creeping in here would turn this into.

It answers `Maybe` rather than dispatching `[]` on an element too small to click,
because dispatching nothing while printing an action is this repo's signature
failure — and what saxrat's copy still does. Each caller answers the decline in
its own words: the pointed path asks for help, the lock path falls back to the
cascade.

#### Verified without a live client

`tools/macos-host/tests/test_wingman_banner_ctrl_click.py` (45 cases). The rules
are executed through the real `Bot.elm` in `elm repl` and the readings they are
asked about go through the real `EveOnline.ParseUserInterface`; the counter is
folded through the shipped `updateMemoryForNewReadingFromGame` over whole
sessions rather than asked once. The strongest cases read the **effects the arm
would dispatch** off the decision's own leaf rather than its description, since
a branch that prints an action and dispatches nothing is exactly what this repo
keeps finding — so "the fleet-member guard is ahead of the click" and "a called
gate is taken rather than clicked" are shown by there being no `CTRL-DOWN` in
what the arm would put on the client, not by an ordering read out of the source.

Confirmed by mutation, seventeen of them, each failing a named case, listed in
that file — including **the guard moved behind the click**, **the gate check
bypassed**, **the bound removed**, **the fall-back made unreachable** and **the
counter advanced from state alone**.

**One survived the first pass and the hole was in the fixture.** Aiming the
click at the head of `fleetWindowDescendants` rather than at the banner element
changed nothing any case could see, because the fixture's fleet window had the
banner label as its first child — so the two were one node. A clickable decoy
drawn first, at a different point, is what discriminates them now. And one
mutation was applied to `Bot.elm` for real, by a run this container killed before
it could restore the file; the two cases named for it are what found it.

#### Unverified

**Any of it running.** No wingman run has been flown since. What to watch on the
first call: `Ctrl-click the fleet broadcast banner to lock '<name>'` in the
decision log and `Lock: CTRL-CLICKING THE BROADCAST BANNER, asked on 1 of 5` in
the status line, then the target reading locked on the next reading or two and
the clause going away.

A run that clicks and clicks and always ends at `THE BANNER CLICK DID NOT LOCK
IT in 5 readings` means the gesture does not do what #366 says it does, and the
bot falls back to the cascade it used before — which is the direction this fails
safely in, and costs five readings a call. A run that *never* prints the
ctrl-click clause at all means the banner element is not being found, which is
the other safe direction and reads as the old behaviour exactly.

**What the client does with a ctrl-click on an object out of lock range, already
locked, or a structure.** The capture that would settle it: broadcast a `Target`
on each of those in turn and read the banner element and the target bar either
side of one ctrl-click with `eve_read.py`. Until then the bound is what covers
all three, and it cannot tell them apart.

### The health retreat, and why it ships switched off

Until #364 this bot had **no health-based retreat of any kind**. The only place
it touched a hitpoint gauge was one raw live shield percentage printed in the
status line, read by no decision. `runAway` in `Bot.elm` reads like saxrat's
`runAwayIfLowHealth` and is not it — it is the neutral-in-local hiding logic
reached through `continueIfShouldHide`, and it docks or warps to a configured
hide location without ever looking at a hitpoint. So the ship flew hour-long
and six-hour fleet tours with nothing watching its health at all.

`retreatToTheCommander` is the guard, ported from saxrat and the mission runner,
and it reads **two instruments that fail in different directions**:

- **The two percentage thresholds** read the *believed* gauge behind a
  low-water mark, never the live reading. CLAUDE.md's "Retreating: the HUD
  hitpoint gauge is the weakest instrument here" is the full argument; the
  short version is that the gauge is scraped out of the client's live memory
  and has produced `2132822%` and, worse, a spurious `0%` that clears every
  threshold at once. `believed` is the healthier of the last two believable
  readings, so a drop has to survive a second look. It delays a retreat by one
  reading; it cannot suppress one.
- **The damage window** sums the client's own combat log over a rolling 45
  seconds and needs no gauge, which is the point of it: a HUD that starts lying
  mid-session cannot disarm it. The verdict is latched in the memory update and
  released only by a window that is completely empty — a live comparison would
  cancel its own retreat, since the window starts draining the moment the ship
  warps clear.

**Where it runs to is the fleet.** It hands `goToFleetMate` the commander's
name, which is the mechanism the broadcast arms already use: the Selected Item
panel's own Warp To on the commander's overview row when they are on this grid
and no broadcast of theirs is on the banner, `@host set-destination` when they
are not. (Until #373 this said "Warp to Member" here, and that cascade was
being driven from the wrong element — see "Not verified" below.) Nothing new
was invented for it, and it picks no celestial or station of its own. That
manoeuvre is exactly the one saxrat's retreat is placed *above*
`respondToFleetBackupBroadcast` to prevent — a damaged ship warping toward
someone else's fight. The difference is the reason: this ship is not answering
a call, it is leaving one.

**Where it sits: below `sessionIsEnding`, above everything that fights.** Every
arm below it answers `Just` for the whole of a fight — the target banner does
not clear (#360), the drone arm answers whenever a drone idles (#326), the guns
answer whenever a weapon is not cycling — and the first arm to answer ends the
reading. A retreat under any of them is reachable only on the readings the
fleet is doing nothing, which is every reading except the ones it exists for.
It stays below `sessionIsEnding` because that is the only arm here carrying a
hard deadline (#350, and `tripHomeSecondsPastSessionEnd` bounding the trip home
past it), and a latched retreat above it could warp a damaged ship back to its
commander for the rest of a session that was supposed to be over.

**Bounded by `retreatAskedReadingsBound` (36 readings).** The mission runner
deliberately has *no* give-up in its retreat, because the leaf it would branch
to dispatches no effects and taking it would stop the bot commanding the warp.
That argument does not carry over unchanged: this bot's run-to can itself
dispatch nothing, since `goToFleetMate` with a commander who is neither on the
overview nor routable ends in a wait, and an arm this high in the tree parked
there owns the whole bot (#321). Past the bound the arm hands the reading back
so the drones and the guns at least fight, and the status line carries the
give-up on every reading.

**All three thresholds default to `-1`, which is off, and that is the point of
this entry.** A threshold is a fact about a hull. Saxrat's numbers — armour 70,
incoming damage 3500 — were calibrated against sixteen recorded sessions of an
Omen Navy Issue, and its shield threshold is `-1` precisely *because* that hull
was measured and found to rest near 0% shield. **There is no recorded wingman
corpus anywhere**, so carrying any of those numbers here would be a guess
wearing a measurement's clothes. What ships is the mechanism, disarmed, with
`Retreat: DISARMED` on the status line of every reading so a run that was never
armed cannot be mistaken for a healthy one.

### The arm reached after every retreat was the one arm that could never act

Issue #381. Three of four wingmen parked, all healthy, all saying the same
thing:

```
+ Recovering from a retreat -- rejoin the fleet commander before resuming.
++ 'Gal Bistot' is this fleet's commander and this ship is recovering,
   rejoining and is not on this grid, and nothing names a place to route to,
   so there is nothing to fly toward.
+++ Wait for progress in game
```

`recoverFromRetreat` handed `goToFleetMate` the **empty string** as the place to
route to, and that function's off-grid half needs a place name — so it took the
branch that says so and waited. `goToFleetMate`'s own doc comment already
recorded that branch as deliberate. What was not thought through is that it is
not an edge case: **the retreat is what puts the commander off grid.**
`warpAwayFromDanger` warps to a celestial at AU range or docks, so by the time
recovery begins the commander is off grid essentially by construction.

And it was not merely idle. This arm sits above the broadcast and combat arms —
deliberately, so a ship flying back is not pulled into the next fight — and
answered `Just` for as long as `recoveringFromRetreat` was latched. **A ship
that could not rejoin did not fight either**: Greta at tick 706, Heather at 464,
Kara at 749, all at 86-100% shield, for tens of readings each. That is #321's
shape, an unbounded arm at the head of the tree owning the whole bot.

**Routing to the commander's live position is not the fix**, and saxrat settled
that: the client refuses a waypoint to a fleet-mate's live position, on every
one of several hundred attempts. That is why `goToFleetMate` declines to fetch
one, and nothing here changes it.

#### Two levers, and they answer different questions

`retreatRecoveryStep` is the rule — eight named answers over five facts and a
counter, `backupCallStep`'s shape and for its reason: a rule reachable only
through a whole `BotDecisionContext` is a rule nothing can execute in a test.
Two of its answers act on something new:

- **`Fleet Member` -> `Warp to Member` off the broadcast banner**, where the
  banner is the commander's own call for company. A *live* signal — he is
  broadcasting from where he is now — and one action that lands this ship on his
  grid. It is the cascade `answerTheBackupCall` already drives off the banner
  for a caller with no overview row, so it works off grid, and
  `fleetMateBroadcastBannerElement` is what keeps it off a stale banner:
  `recoverFromRetreat` is exactly the caller that arrives with somebody else's
  banner still up.
- **Where the commander last said he was**, carried across the retreat in
  `BotMemory.fleetPlaceBroadcast` and handed to `goToFleetMate` as a real place.
  A *historical* signal, and the cross-system one.

**The banner is asked first**, because after `warpAwayFromDanger` this ship is
usually in the same system as its commander and on a different grid — where the
banner's warp is exactly right and a route to a system the ship is already in is
an empty route `navigateTowardFleetCommander` has nothing to click. It is also
the cheaper of the two: one cascade against a host round trip and a multi-jump
flight.

#### Where the place comes from, and what invalidates it

`fleetPlaceBroadcastAnyPilot` reads the three broadcast forms that carry a place
— `Travel to`, `is at location`, `is in position at` — with the pilot who named
it. `TravelTo` is in that list because the issue's own reading is the proof the
place was there: on the same reading three wingmen had nothing to fly to, Olivia
was routing toward `'Madirmilire'` off `Gal Bistot: Travel to Madirmilire`.
`fleetMatePlaceAnyPilot` next door deliberately does **not** read that form —
what it feeds is the ask that goes out when a mate calls this ship to *them*,
and a travel broadcast is not that call.

**The pilot travels with the place and the decision does the filtering.** The
memory update *could* filter — `UpdateMemoryContext` carries `botSettings` here,
and the comment on `fleetTravelBroadcastAnyPilot` saying otherwise is stale —
but `fleetCommanderNameFromReading`'s primary source is the fleet window's own
header, which comes and goes. A place filtered in at a moment the header was
readable and refused at a moment it was not would be a memory whose contents
depend on a transient. Storing the sender means one reading's answer decides
both halves, and the status line can say whose place it is when the answer is
"not the commander's".

**Three rules clear it**, and the second is the invalidation the arm needs:

- a place named on this reading replaces whatever was remembered, whoever named
  it;
- **the reunion drops it**, on the same reading `recoveringFromRetreat` clears —
  wherever the commander last said he was is superseded by his being right
  there. So no place this arm ever routes to was broadcast before the last time
  this ship was with its commander;
- otherwise it is held, because the banner persists between broadcasts and a
  reading naming no place is not a reading saying the fleet moved.

A place seen *this* reading beats the reunion, which is the ordering rather than
a detail of it: a commander who broadcasts `Travel to X` on the very reading
this ship rejoins him has said where the fleet is going next.

**The cost of one slot is stated rather than hidden**: another pilot's place
displaces the commander's, the recovery then has nothing, and it gives up rather
than routing somewhere arbitrary — which is the refusal `goToFleetMate`'s own
doc comment already makes. There is **no age bound**: this bot has no corpus to
place one against, and the arm's give-up is what stops a stale place costing a
session.

#### The bound counts asks, and the give-up does not clear the latch

`retreatRecoveryAskedReadingsBound` is `fleetMateWarpAskedReadingsBound` (30)
written as that constant, `backupCallAskedReadingsBound`'s arrangement: this arm
drives the same banner cascade that bound was sized for and the route half
drives `routeMarkerCascade`, so a second number would be two opinions about the
same two mechanisms on a bot with no corpus of its own.

**It counts only the answers that dispatch.** `retreatRecoveryAnswersThatSpendAReading`
is the list, and `NowhereToRejoinTheCommander` is deliberately not in it: that
answer dispatches nothing, so charging it would be #389 exactly — a counter
advanced from state alone reporting a give-up at 46 readings against a bound of
20 with the arm never having been asked. It needs no budget either, because it
already hands the reading back.

**It is not a bound on the flight**, which is what makes thirty enough for a
multi-jump route. `AlreadyOnTheWayBackToTheCommander` sits above every
actionable answer, so every reading the ship is actually warping or jumping
resets the count — `retreatAskedReadings`' own rule. What accumulates is
readings spent clicking with the ship standing still, which is the only shape
that can run forever. A warp cannot undo a spent budget, because the rule asks
the give-up before it asks the warp.

**And a reading the retreat itself is holding spends nothing.**
`recoveringFromRetreat` is set on the reading the retreat is *decided*, and
`retreatToTheCommander` sits directly above this arm and answers `Just` for as
long as its verdict is latched — so every reading of the retreat is one where
the rule answers something actionable and the arm was never reached. Charging
them is #389 again, and worse than in #389: a retreat long enough to spend
thirty readings out of warp (the mission runner's corpus has one at 44) would
hand the recovery a spent budget and a give-up on its first reading. It is a
**reset** rather than a hold, because the recovery has not begun — the reading
the retreat clears is the reading this arm first gets, and it gets the whole
allowance. `retreatIsDecided` is the memory update's own binding, the one the
arm above reads through `retreatReason`, rather than a second condition beside
it.

**The give-up hands the reading back and does not clear
`recoveringFromRetreat`.** Clearing it would report this ship as rejoined when it
is not — this repo's signature failure — and would silently change what
`fleetMateToWarpToOnThisGrid` answers, which reads the latch to decide which mate
this ship is trying to reach on this grid. So the counter is **held** past the
bound rather than reset, or the give-up would un-give-up on the next reading, and
the one thing that clears the latch is what always cleared it: the commander
getting an overview row. A second retreat gets a fresh budget; one recovery does
not get two.

**Nothing is lost by keeping the latch**, which is what makes that choice cheap:
a commander who broadcasts a new place after the budget is spent is followed by
`actOnFleetBroadcast` below, which is reachable precisely because the give-up
handed the reading back.

**Everything that is not an action hands the reading back**, refusals included —
#360's lesson and #385's arrangement. A commander nothing names, a budget spent,
a ship already in warp and a grid with nowhere to rejoin are each *nothing more
to do about the recovery*, not a reason to spend the reading saying so.
`describeRetreatRecovery` says it instead, on every reading, since a `Nothing`
cannot carry a decision line.

#### Verified without a live client

`tools/macos-host/tests/test_wingman_recovers_from_a_retreat.py`, 58 cases. The
rules are executed through the real `Bot.elm` in `elm repl` — the step rule
rendered as one constructor name per case, so a rule answering two things at
once or none fails rather than passing on whichever one a case named; the bound
at both sides *and* against fixed values either side, since a case asking only
`constant - 1` and `constant` passes for any constant; and the place memory
folded over the readings a session passes through. The readings come from the
real `EveOnline.ParseUserInterface`.

**The control is run rather than asserted.** The arm answering `Nothing` is only
worth anything if something below it then acts, so
`TheArmsBelowGetTheirReadingsBackTest` runs the real
`wingmanDecisionRootInSpace` on one reading and compares the give-up's answer
against the same root with nothing recovering at all — with a positive control
beside it that must still act, and a negative one where a recovery that *can* act
still owns the reading.

Confirmed by mutation, **twenty** of them, each failing a named case, listed in
that file — including the bound removed, the counter advanced from state alone,
the give-up parking instead of handing back, a stale place never invalidated,
the arm hoisted above the retreat itself, and the retreat-holding clause dropped
so the retreat spends the recovery's budget before the recovery starts. **Three survived a
first version of a case and each hole was real**: a question asked of the
reading where the arm answers `Nothing` whatever it is handed, a status-line
assertion satisfied by the clause's own definition head, and an equality between
two roots that a give-up satisfies by breaking both — which is what the positive
control beside it is for, and that control is what killed it.

#### Unverified: any of it running

No run has been flown. What to watch on the first retreat: `Retreat recovery:`
on every reading, then — once the retreat clears — either `warping from the
commander's own broadcast banner` or `routing to where the commander last said
he was` with `Last place broadcast:` naming a place and the commander.

The failure to watch for is `Nowhere remembered: no broadcast has named a place
since this ship was last with its commander.` on every reading of a run whose
commander has been broadcasting — that would mean `fleetPlaceBroadcastAnyPilot`
is not reaching the memory, and it is the direction this fails silently in. A
clause naming a place `by` somebody who is not the commander, with
`which is not this fleet's commander, so it is not routed to.` beside it, is the
one-slot cost above behaving as designed rather than a fault. And
`GAVE UP after N readings` on a run whose commander is on the grid would mean
the reunion is not clearing the latch.

**Two things are unmeasured and stay so.** How often the commander's banner is
up while this ship is recovering — which decides whether the banner lever or the
place lever is the one that carries the arm — and whether the banner's
`Warp to Member` is offered at all for a mate on another grid in the same
system. Both fail safe: an unavailable cascade spends the bound and falls to the
give-up, which hands the reading back.

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

**The travel form was documented and not wired at all, until 2026-08-25.**
`actOnFleetBroadcast` had a matcher for `Target …` and nothing for
`… : Travel to …` — the eight verbs in `broadcastVerbsNotYetRead` fell through
to a named wait, and so, silently, did every travel broadcast, despite this
file and the bot's own header both listing it as one of the two forms already
read. Fixed by porting `eve-online-saxrat`'s `fleetTravelBroadcastMarker` /
`fleetTravelBroadcast` / the two-reading `fleetBroadcastSeen` →
`fleetBroadcastFollowed` latch whole, adapted for one real difference: saxrat's
copy of `EveOnline.BotFrameworkSeparatingMemory` was extended to parameterize
`UpdateMemoryContext` with `BotSettings`, and this freshly-vendored copy was
not, so the latch is computed unfiltered by `follow-fleet-broadcast-from` and
permission is checked only where the memory update cannot reach — in
`fleetTravelBroadcast` itself, at decision time.

**That last difference is gone as of #364.** This copy now carries
`botSettings` too, because the retreat's give-up counter has to be written in
the memory update and "is the retreat decided" is not a question a reading
answers on its own. The travel latch was left exactly as it is: it works, and
moving the permission check is a change with its own evidence to gather.

Verified live end to end: the banner `Gal Bistot: Travel to Bhizheba` (no
timestamp — the marker is an infix, matched the same way on the timestamped
history panel and the plain persistent banner, though only the banner is ever
actually read) produced `@host set-destination Bhizheba` in the decision log,
the host logged `# ESI: destination 'Bhizheba' set (30002282)`, and the
client's own route panel came up `Route 1 Jump` naming Bhizheba. The very next
reading printed `Already asked the host to route to 'Bhizheba', ...` instead of
repeating the call — the latch holding.

**Setting the destination used to be all this did — the ship then sat still
until a person, or the client's own Autopilot toggle, flew it.** That was
never quite right about `eve-online-warp-to-0-autopilot` either: read live,
that bot's `decideStepWhenInSpace` presses the Selected Item panel's own Jump
button (falling back to the route marker's right-click cascade) whether or
not the client's Autopilot toggle is on — it never reads that toggle at all.
The trip home below is still exactly the "nothing flies it" posture this
paragraph used to claim for both; the travel broadcast is not, since
2026-08-25.

### `needs backup` never matched, because the matcher carried the button's wording

Issue #385, and the defect is one character. `parseBroadcastVerb` tested

```elm
else if stringContainsIgnoringCase "need backup" rest then
```

and the client renders **`needs backup`** — third person. `"needs backup"` does
not contain `"need backup"`, because after `need` comes `s` rather than a
space, so the test was false on every reading and every backup call this bot has
ever seen fell through to `Unrecognized`. `Need Backup` is the fleet window's
own **button** label, and this file's own words two sections down are the rule
it broke: *a button's wording is not the broadcast's*. It is the one verb
somebody wired from the button list without a capture to check it against.

**The file was internally inconsistent about it too**, which is the tell that
was there to be read: `Need Backup` was in `broadcastVerbsNotYetRead` while
`parseBroadcastVerb` claimed to read it, so one of the two was wrong on every
reading. It is out of that list now — the list is seven — and the other five
button labels are still in it, unwired. `Need Armor`, `Need Capacitor`,
`Need Shield`, `Request That the Fleet Hold Position` and `Spotted an Enemy`
have never been observed rendered, and wiring one from the button's wording is
exactly what produced this bug.

**Both shapes are read**, because the issue's own quote elides the sender and
this client writes both: `<Sender>: Travel to X` beside
`<Sender> is at location X`. The colon form is tried first, so the no-colon
matcher can never cut a sender with the colon still stuck to it — and this bot
matches a pilot name exactly, so `'Gal Bistot:'` would match nobody.
`needsBackupMarker` is the one constant both halves read, `gateKeyClosingMarker`'s
arrangement: two copies of a client wording are two things that can drift apart
silently.

#### What the arm does, and where it sits

`answerTheBackupCall` closes on the caller, by whichever of the two mechanisms
the reading offers. **This is wiring rather than a new mechanism**: the approach
is `ensureShipIsApproaching`, the helper `approachTheFleetCommander` already
drives and with the same confirmation — the client's own `ManeuverApproach`,
never a dispatched click. The warp is
`warpToFleetMateFromTheBroadcastBanner`, which is the cascade
`warpToFleetMateOnThisGrid` was already driving for `is at location` and
`is in position at`, lifted into a declaration of its own so the two callers
cannot come to disagree about the rungs.

- **On grid** — approach them.
- **Not on grid** — the banner's own `Fleet Member` → `Warp to Member`, which
  needs no overview row and is the only thing that can reach a mate who is in
  this system and not on this grid.

**It sits above the travel broadcasts in the decision root**, which is #237's
argument for saxrat: being slow to a backup call costs a ship where being slow
to an `is at location` costs a few seconds of alignment. Below the retreat, the
recovery, `sessionIsEnding`, the friendly-fire unlock and the always-on modules
— a ship past its own threshold leaves rather than joining somebody else's
fight, and the two above it are a safety condition and one click.

#### The trust boundary is the fleet, not `follow-fleet-broadcast-from`

The old arm refused a caller not named in `follow-fleet-broadcast-from`. Those
are different policies: that allowlist says whose *travel* this ship follows,
and a fleet-mate who needs help is not necessarily one of them. So
`answer-backup-calls` is its own setting, defaulting to **yes**, and the caller
has to be someone `fleetPilotNames` recognises — the fleet window's own member
rows, its header's commander, or a pilot local chat's standing icon marks as a
fleetmate. That is the same boundary the friendly-fire guard already uses.

**The cost is stated rather than hidden**: a wingman now breaks off for *any*
fleet member's backup call, where before it answered none at all.

**The failure direction is the quiet one, and #380 is why that matters.** Those
member rows are known to be under-reported — four wingmen in one fleet read 0,
2, 4 and 4 rows from the same Fleet window at the same moment. Under-reporting
here declines a call and this ship goes on doing what it was doing; it never
sends a ship anywhere. Over-reporting would be the dangerous direction and
nothing in that issue shows it: every source of a name here is the client
stating fleet membership, and the commander fallback is the operator's own
setting. So a wingman whose Fleet window lists nobody answers no backup calls at
all, and `describeBackupCall` says so on every reading.

#### In system only, and every other answer hands the reading back

A backup call names **no place** — the broadcast carries a pilot and nothing
else — and saxrat found the client refuses a waypoint to a fleet-mate's live
position, so there is nothing to route to and `goToFleetMate`'s place-less
branch is deliberately not reached from here. What this bot can do is
in-system, and an out-of-system caller is indistinguishable from an in-system
one at the reading: the banner's cascade is tried either way, the client offers
`Warp to Member` where it can, and the bound ends it. The give-up names
out-of-system as the likely reason and #381 as what would have to answer first.

**Every answer that is not an action answers `Nothing`**, refusals included, so
this arm cannot starve what sits under it while a banner that does not clear
stays up — #360's lesson, which #395 and #397 each paid for again. A call this
ship will not answer is *nothing more to do about the call*, not a reason to
spend the reading saying so; `describeBackupCall` is what says it instead, since
a `Nothing` cannot carry a decision line. Bounded at
`backupCallAskedReadingsBound`, which is `fleetMateWarpAskedReadingsBound`
written as that constant rather than as a number, because this arm drives the
same cascade that bound was sized for.

**`NeedBackup` left `fleetMateCallingForCompany`** with the verb. That function
feeds `goToFleetMateWarpAskedReadings` and `describeFleetMateWarp`, so leaving
it would have that counter advancing and that clause reporting a warp no branch
was attempting — a status line disagreeing with the decision.

**Verified without a live client**, in
`tools/macos-host/tests/test_wingman_answers_a_backup_call.py` (43 cases). The
matcher and the rule are executed through the real `Bot.elm` in `elm repl`, and
the arm is run over readings the **real** `EveOnline.ParseUserInterface`
produced from UI trees carrying a fleet window, its banner, its member rows, an
overview and a ship UI — so what the branch is handed is what the bot would have
been handed. Confirmed by mutation, sixteen of them, each failing a named case
and listed in that file — including the matcher reverted to the button's
wording, the arm holding the reading forever, the trust boundary reverted to the
travel allowlist, and one of the five unobserved verbs wired on a guess.

### Navigating to the fleet commander when out of system

`navigateTowardFleetCommander` flies the route the ESI directive above set,
using `eve-online-warp-to-0-autopilot`'s own mechanism ported rather than
reinvented: press the Selected Item panel's Jump button where it already
shows the route's next gate, falling back to the route marker's own
right-click cascade otherwise. Nothing about that mechanism changed in the
port — `RouteStargateJump` down to `nodeIsDisplayed` in `Bot.elm` is that
bot's code unchanged, and the doc comments there say so at each declaration.

**Gated on the commander being off this grid, and nothing else asks that
question.** `actOnFleetBroadcast` calls `pilotIsOnOverview` — a name match
against the current overview's rows, the same identity `lockCalledTarget`
already uses — and only calls `navigateTowardFleetCommander` while that
answers `False`. The moment the commander's row reappears, the travel branch
goes back to `waitForProgressInGame` and the ship holds wherever the last
jump left it, which is the right place to stop: arriving *is* what "not out
of system anymore" means. Two things follow from that placement rather than
being separately argued: a commander broadcasting from the same system this
ship is already in never triggers navigation (nothing needs flying), and a
target broadcast is still checked first in `actOnFleetBroadcast`, ahead of
travel, so a called target does not have to compete with a jump in progress.

**Two rungs are ported, not three.** `eve-online-warp-to-0-autopilot` has a
third — `jumpCascadeStuckReadings`, falling back to a surroundings-button
cascade after 30 readings of the route panel naming the same next system with
no jump landing — built on a `lastSolarSystemName`/`jumpsCompleted` pair this
bot keeps no other use for. Approximating the same signal off
`nextSystemOnRouteFromReading` changing would misread exactly the case that
bot's own comment names as the reason it uses the more careful signal: a
route that revisits a system it has already named, where the label repeats on
a leg that genuinely completed. Shipping a stuck-detector that can misfire on
the one case it exists to catch is worse than not having one, so it is left
out; `jumpThroughRouteStargate`'s own two rungs are what run here, and a leg
this bot cannot identify a gate for has no further fallback and keeps
retrying the marker cascade.

**Untested against a live client.** The type-checks are proven — `elm make`
succeeds on this file paired with the real host's `Main.elm` — but nothing
has watched a commander broadcast travel from another system, and nothing has
watched a jump land from either the panel button or the marker cascade under
this bot's own decision root. What to watch on the first run that meets this:
`'<pilot>' is not on the overview -- navigating toward the route to
'<system>'.` appearing, then either `Jump through '<gate>' from the
selected-item panel, which is already showing it.` or one of
`describeRouteStargateJump`'s fall-back sentences, then the commander's own
row appearing on the overview and the branch reading `is on the overview --
no longer out of system` on the next reading. A run that reaches the travel
branch and never prints a jump-related line at all past the first "no route
in the info panel yet" wait means the ESI destination never took, which is
`hostDirectiveSetDestination`'s own territory rather than this one's.

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

## Never shooting the fleet

**It stopped being hypothetical in run 9.** This bot fired `Small Focused Beam
Laser II` at `Sonya Spodumain[MNRLG](Imperial Navy Slicer)` — a real player,
named twice by this bot's own "other pilots" line — in two clusters of hits,
penetrations and grazes about thirty seconds each. #367 is the write-up; what
landed for it is three guards and a status line, and the third guard is the one
worth reading twice.

**The trigger refuses on its own, not only the lock.** `fireOnActiveTarget`
consults `friendlyFireVetoesTheGuns` before it consults `weaponsStep`, and so
does `fightPointedRatsOrReturnDrones`. Guarding the lock could never have been
enough: `weaponsStep` reads `targetLocked` and three other facts, none of them
a name, and two paths put a target in the bar without passing the one fleet
check that existed — `fightRatsIfShipIsPointed` ctrl-clicks whoever is pointing
this ship, and a hand-locked target was never asked about at all. Both failures
now have to coincide before a friendly takes damage.

**The lock bar is scanned every reading.** `unlockFleetPilotInTargetBar` walks
`readingFromGameClient.targets`, matches each one's rendered text through
`targetTextsCarryName` — `lockedTargetNamed`'s own matcher, so there is exactly
one comparison and it cannot disagree with itself — and right-clicks a match
for the client's `Unlock` entry. That cascade existed only as a sketch inside
`decideActionInAnomaly`, which nothing on the live decision path calls. It sits
fourth in the root, above the broadcast arm and above the drones and the guns,
because each of those answers `Just` for the whole of a fight and an unlock
below them would be reachable only on the readings nothing is happening.

**An empty membership list is not a clean bill of health.** This is the half
that makes the rest mean anything. `fleetMemberNames` reads the Fleet window
and answers `[]` when it is shut — a fleet of forty and a pilot flying alone
produce the same empty list — and `List.member` over `[]` is `False` for
everybody. A guard that stopped there would pass every target through while
leaving a log indistinguishable from one where the check had run, which is
exactly the silence #367 was filed on. So `friendlyFireStep` asks two questions,
not one:

| the Fleet window | a locked pilot | a locked NPC |
|---|---|---|
| open | checked: shot unless the list names them | shot |
| **shut** | **held, and the status line says why** | shot |

With membership unverifiable it falls back to a question the client can still
answer — is the locked thing a *pilot*? — against
`getNamesOfOtherPilotsInOverview`, which is how this bot independently named
Sonya twice in the run that shot her. **NPC rats are never in that list**, so
PvE is untouched; the whole cost of the refusal falls on shooting players with
the Fleet window shut.

**What the fallback does not close.** `getNamesOfOtherPilotsInOverview` needs
local chat's user list as well as the overview, and answers `[]` when that
window is not rendering one — so a reading with the Fleet window shut *and*
local chat unread falls back to "clear to fire", which is the original hole in
a narrower place. `Seeing N other pilots in the overview` is printed on every
reading and is the line to count that from. It has not been counted: no
`wingman_run*.log` is in this Mac's `~/eve-bot-logs`, and run 9 lives on the
Windows host that flew it.

**The guard asks two instruments, because the one it had was defeated by the
client's own line wrapping.** Until #390 it decided "is this pilot locked" from
the target bar's rendered labels alone, through `targetTextsCarryName` — and
the bar wraps a long name across labels, which is what made the called-target
recognition fail on four pilots at once (see "Already locked" above). A
fleetmate whose name the bar wraps was therefore **not recognised as locked**,
the membership branch answered `Nothing`, and with the Fleet window open that
fell through to `ClearToFire`. It failed in the *firing* direction — the one
direction #367 exists to prevent — on two-word character names, which is most
of them and `Sonya Spodumain` among them.

So the rule now asks both and **holds fire if either answers**:

| | the bar's labels | the pilot's overview row |
|---|---|---|
| what it reads | `textsTopToBottom`, as rendered | `commonIndications.targetedByMe`, the client's own icon |
| goes quiet when | the name wraps across labels | the pilot has no row here at all |

`lockSignalForPilot` is that union — the two questions and which of them
answered — and `&&` in its place would be the defect rather than a variation:
it would hold fire only where the two agreed, which is every case except the
ones this rule exists for. The second column goes quiet on an overview preset
that hides fleet members (already a recorded hazard for
`approachTheFleetCommander`) and on a pilot who left the grid still holding a
lock, so it is *added* to the first and never put in its place. **An added
signal can only add refusals.** `NothingIsLocked` needs both to be empty for the
same reason: a row carrying the indicator with nothing parsed in the bar is a
lock, and calling it "nothing is locked" would release the guns.

`unlockFleetPilotInTargetBar` still needs the bar entry, because it right-clicks
a `Target`. A pilot seen only by the row indicator gives it nothing to click, so
it hands the reading on and the veto holds the guns without an unlock — and
`targetBarSawThePilot` keeps `unlockFleetPilotAskedReadingsBound` from being
charged for the ask that could not be made, which is #389's second defect
arriving in this counter.

**The rule is still a function of plain values.** The overview signal reaches it
as a list of names, built by `friendlyFireStepFromReading` from
`overviewRowSaysThisShipHasItLocked`, so a case still executes the guard against
six plain facts without constructing a reading — the property every case in
`test_wingman_holds_fire_on_fleetmates.py` rests on.

**What #390 does not close**, stated because both instruments can go quiet on
one reading: a name the bar wraps *and* a row with no indicator drawn (or no row
at all) reads exactly as it did before. That is `test_what_this_change_still_does_not_close`.

**The bound stops the asking and not the refusal.** Every other give-up in this
file hands the reading back to the arms below it.
`unlockFleetPilotAskedReadingsBound` (20) does not: a context menu that will
not open is no reason at all to start shooting the pilot it would have
unlocked, so `GaveUpUnlockingAFleetPilot` still vetoes the guns.

**And it is loud.** Two clauses on every reading, whether or not anything is
locked — because run 9's whole problem was that `grep "is in this fleet"` over
18,974 lines returned nothing, and from outside there was no telling whether
the guard had never had a candidate or never had a list:

```
Fleet membership: corroborated -- the Fleet window's header states 5 pilots
and 5 are resolved. Member rows: 4 (Greta Gneiss, ...). Commander: 'Gal
Bistot' (fleet window header). Local chat's standing icons mark 2: ...
Friendly fire guard: 3 locked, none of them a fleet pilot -- clear to fire.
```

```
Fleet membership: NOT CORROBORATED -- the Fleet window's header states 5
pilots and only 1 could be resolved, so an empty or short member list would
otherwise read as 'nobody here is a fleetmate'. Open the Fleet window and
expand its wings and squads to fire on players again. Member rows: 0 (none).
...
Friendly fire guard: HOLDING FIRE on 'Sonya Spodumain' -- a pilot on the
overview, seen by the overview row's lock indicator, and this bot cannot tell
whether they are a fleetmate because the Fleet window's header states 5
pilots and only 1 could be resolved.
```

**And every refusal names the instrument that saw the pilot**, which is #390's
half of the same argument one level down: two signals that fail in opposite
directions means a line saying only "held" leaves the next incident reasoning
from silence about which one was working. `the target bar's labels`, `the
overview row's lock indicator`, or both — and the two together are what a run
would have to print before either could be trusted alone.

### Local chat's standing icons add names and cannot certify a list

#367 asked whether `chatUserIsKnownFleetmate` — the client's own per-pilot
`Pilot is in your fleet` hint, already computed, needing no window open —
should feed membership. **It does now, on the naming side**, through
`fleetmateNamesFromLocalChat`, and the reason is a hole rather than a
preference: `getNamesOfOtherPilotsInOverview` *excludes* known fleetmates, so a
fleetmate the icon does mark would have been absent from `fleetPilotNames` with
the window shut **and** absent from the overview list the fallback checks —
the one combination that reads as "a stranger, shoot away".

**It is not what decides whether membership is verifiable**, and that is
deliberate. `chatUserIsKnownFleetmate` answers `False` for a chat row carrying
no hint at all — correctly, since absent evidence must not read as "fleetmate"
— so a fleet whose icons this bot cannot resolve looks exactly like no fleet.
That is the same collapse the Fleet window's `[]` makes, so it cannot be the
thing that rules it out. **The window's presence is not it either**, which is
the section below; what rules it out is the size the window's own header
states.

**What nobody has measured** is how promptly that icon updates when a pilot
joins or leaves a fleet mid-session, which is what would be needed before it
could be trusted as the primary source rather than an additive one. Run 9 is
two sampled readings, not a series.

### An open Fleet window is not a verified roster

Issue #380. Four wingmen read the same fleet at the same moment (console
readings 2026-08-27 15:23 and 15:31) and reported **different** member lists,
while every one of them read the commander correctly out of the header:

| pilot | member rows | local chat standing icons |
|---|---:|---:|
| Greta Gneiss | **0** | 0 |
| Kara Kernite | **2** | 4 |
| Heather Hemorphite | 4 | 4 |
| Olivia Ochre | 4 | 4 |

`fleetMembershipIsVerifiable` asked whether the Fleet **window was present**,
deliberately not whether it listed anybody, because a fleet of one is a real
reading and requiring a row would put the rule back to reasoning from an empty
list. That argument is right about a fleet of one and wrong about Greta, who
had a target locked:

```
Fleet membership: the Fleet window is open and lists 0 member rows: none.
Friendly fire guard: 1 locked, none of them a fleet pilot -- clear to fire.
```

**A fleetmate missing from that list is one she would shoot, while the line
says membership was verified.** It is #367's own incident with the guard
installed and reporting confidently, and the fallback that would have caught
it — refusing to fire on any recognised pilot — never runs, because it was
gated on the window being *absent* and the window was present.

#### Neither of #380's own two shapes catches it

The issue offers corroborating the rows against local chat's icons and treating
disagreement as unverified, or dropping the boolean and refusing on any
recognised pilot where the two sources disagree. **Both are keyed on
disagreement, and Greta's two sources agree — at zero** — so both verify the
exact reading the issue was filed on. Kara's 2-against-4 is caught by either,
and #396's union already folds her chat icons in and gives her four names, so
the half those shapes do catch was largely answered before them.
`test_the_two_sources_agreeing_at_zero_is_not_corroboration` executes that
argument rather than asserting it.

Requiring a non-empty row count is the other obvious move and is what the
existing doc comment already declined: it reintroduces reasoning from an empty
list, and it breaks a genuine fleet of one, whose window legitimately lists no
rows because the only pilot is the boss in the header.

#### The window states its own size, and that is the third instrument

The captured header reads `Fleet (5)` beside **four** `FleetMember` rows —
already recorded under "The member rows are not the whole fleet", where it is
the evidence for unioning the commander in. Read the other way it is a
statement of how many pilots there are, which nothing had ever read.

`fleetRosterVerdict` compares that number against the count of **distinct**
pilots `fleetPilotNamesFromReading` resolved, and answers four things:
`FleetWindowIsShut`, `FleetSizeNotStated`, `RosterIsShort` and
`RosterIsComplete`. Only the last lets an empty membership list mean "nobody".

| reading | header | resolved | verdict |
|---|---|---:|---|
| Greta | `Fleet (5)` | 1 (the commander) | **short** |
| Kara | `Fleet (5)` | 4 | **short** |
| Heather, Olivia | `Fleet (5)` | 5 | complete |
| a genuine fleet of one | `Fleet (1)` | 1 | complete |

**Greta's reading and a fleet of one are otherwise identical** — window open,
no member rows, no chat icons, the header naming the boss — so the stated size
is the only thing on the reading that separates them. The two fixtures in
`test_wingman_fleet_roster_corroborated.py` differ in one character.

**It needs no theory of _why_ the rows differ**, which is the half #380 says
nobody has established and this cannot establish either. Every candidate the
issue names makes the rows a *subset* of the fleet, and a count catches a
subset however it arose.

**The count folds duplicates and case.** `fleetPilotNamesFromReading`
concatenates three sources, so a pilot in the rows *and* in the chat icons
appears twice — Kara's own reading resolves seven entries and four pilots.
Counting the list would read seven against a stated five and call a roster
short by two pilots complete. Over-merging two spellings of one name lowers the
count, which reads as short and refuses; under-merging inflates it and
verifies a roster that is not there, so the fold is the safe direction.

**Both kinds of not-knowing refuse.** A shut window and a header that states no
size are each "this reading cannot answer", never "the roster is complete" —
`loadRefusalFromGameLog`'s register applied to a roster. Refusing is cheap
here: `getNamesOfOtherPilotsInOverview` is built from local chat's userlist and
never holds an NPC, so PvE is untouched and the cost falls entirely on shooting
*players* whose fleet membership this reading cannot certify.
`test_the_guard_still_fires_on_a_rat_beside_it` shows that with a control on
the same reading — the same short roster, the same pilot on the same overview
merely not locked, and a rat in the bar — rather than claiming it.

**Kara now reads as short on a roster that is arguably complete enough**, and
that is stated rather than hidden: the one name she is missing is *herself*,
which no source on her own reading carries and which she cannot shoot. So she
holds fire on strangers for a shortfall that is not dangerous. That is the
direction chosen, and the header's own count is what would have to change to
avoid it.

#### What it means for the lock guard

`fleetPilotNames` also feeds "do not lock a called target who is in the fleet",
and **that list is deliberately untouched** — it is an *input* to the verdict
and never the other way round, so there is no path by which a verdict can take
a name off it. The lock guard therefore refuses exactly the names it refused
before, never fewer; narrowing it by the verdict is the one change that would
make it *quieter*, on exactly the readings where the roster is least
trustworthy, and `TheLockGuardsConsumerIsNotQuieterTest` is what refuses that.

What the lock guard gains is only that its shortfall is now named on every
reading rather than being invisible, which is the evidence a follow-up would
need. And the consequence is covered downstream: the two lists partition the
pilots on the overview — a fleetmate the chat icons resolve is in
`fleetPilotNames` and unlocked, and one they do not is in
`getNamesOfOtherPilotsInOverview` and held — so a called fleetmate the roster
missed is still not *fired* on while the roster is short.

#### Verified without a live client

`tools/macos-host/tests/test_wingman_fleet_roster_corroborated.py` (34 cases).
The rules are executed through the real `Bot.elm` in `elm repl` and the
readings they are asked about come from the real
`EveOnline.ParseUserInterface` — **no parser change was required**. The
issue's own table is read back off those readings before anything rests on
them, and the comparison is asked at its boundary *and* against fixed values
well clear of it in both directions, since a case that asks only about
`constant - 1` and `constant` passes for any constant.

Confirmed by mutation, **fourteen** of them, each failing a named case:
`fleetMembershipIsVerifiable` reverted to `fleetWindow /= Nothing`, which is
the shipped defect exactly; `RosterIsShort` made to corroborate; the
comparison inverted so a fleet of one reads as unverified; a non-empty row
count used as the rule instead; `FleetSizeNotStated` corroborating, so absent
evidence reads as a finding; `FleetWindowIsShut` corroborating, which is #367
undone; the distinct-name fold dropped and, separately, the case fold dropped;
the guard handed a literal instead of the verdict; **the no-shoot list
narrowed by the verdict**, which is the lock guard made quieter and fails 24
cases; the status line still calling an open window verified; the two clauses
given separate wordings so they can disagree about one reading; the size read
as any integer in the header, so `Squad 1 (4)` answers; and the marker
inlined twice so the match and the slice can drift.

**One kill was thin and the case was added rather than accepted.** Handing
`friendlyFireStep` a literal `membershipIsVerifiable = True` was caught by one
executed case, because the rule is a function of plain lists (#396's own
property) and no plain-list case can see its caller. `test_the_guard_is_told_
the_real_verdict` reads that wiring out of the source.

## What is deliberately unfinished

Each of these answers a *named* branch rather than doing something plausible,
because a bot that guesses reads exactly like one that knows.

- **Five of the ten broadcasts.** The window's own buttons enumerate them
  (`broadcastVerbsNotYetRead`), but **a button's wording is not the
  broadcast's** — the button says `Broadcast: Spotted an Enemy` and the history
  says something nobody has observed. An unmatched banner reaches a wait that
  says so.

  **That list was eight until #385, and the three that left it are the reason
  it is worth keeping honest.** `Need Backup` was in it *and* claimed by
  `parseBroadcastVerb`, whose matcher carried the button's first-person wording
  against a client that renders `needs backup` — so the two contradicted each
  other on every reading and no backup call was ever read. `At Location` and
  `In Position at` were the same disagreement with the halves the other way
  round: both wordings were captured live and both are acted on, while the list
  went on calling them unread. A list that names a verb the parser reads is a
  list nobody can check the parser against, which is what let one wrong matcher
  sit in it unnoticed.

  **`…: Travel to …` is the fourth shape of the same thing, and its own is the
  opposite: see "First live run" below.** Its wording has been known since the
  capture at the top of this file, and nothing was written to dispatch on it
  until 2026-08-25 — `actOnFleetBroadcast` called only
  `targetBroadcastPilotName` — so it reached the same wait as the genuinely
  uncaptured verbs while being neither unknown nor, after that, unwritten. The
  live vocabulary is also *wider* than the buttons: `Jump Stargate` and
  `Align Stargate` are matched and are on no button at all.
- **The trip home.** It returns a branch naming what is missing rather than
  `Nothing`, because `Nothing` reads as "nothing to do" and would fly past the
  session's end in silence.
- **Which header label is the commander.** `fleetCommanderName` now prefers the
  fleet window's own header and falls back to `follow-fleet-broadcast-from`
  (#367 unified the three resolvers this bot had grown), but the header read
  itself is still an inference from shape: the pilot is the one label that
  carries no parenthesis. The `Boss` and `Fleet Commander` icons are better
  evidence and which label belongs to which was never established from the one
  capture.

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

#390 is the deliberate exception and the difference is worth being precise
about. The guard now reads *both* sources and refuses on either, while
`unlockFleetPilotInTargetBar` still reads the bar alone, because it right-clicks
a bar entry and nothing else can be right-clicked. The two do not disagree about
what is locked: when only the row saw the pilot, the guard holds the guns and
the unlock arm simply has nothing to click, which is the safe half of #303's
divergence rather than a repeat of it.

**Logi is the exception and needs a setting.** A logistics pilot locks fleet
members deliberately — that is the job. So this cannot be an unconditional rule;
it wants a setting defaulting to unlock, which a logi fit turns off, in the
shape `assist-fleet-commander` already uses.

Note the two halves. The wingman already refuses to *lock* a called target that
is in the fleet. Unlocking handles the case where the lock happened some other
way — a stray ctrl-click, or a broadcast arriving after the lock. Both halves
read the same `fleetPilotNames`.

### 5. The trip home -- built, not yet flown (#350)

`home-station`, defaulting to `Amarr VIII (Oris) - Emperor Family Academy`,
routed by ESI and flown with the same jump/dock mechanism
`navigateTowardFleetCommander` already uses, budgeting 420 seconds past the
planned end through `@host extend-session` (the mission runner's own
precedent, for the same reason: run 17 was killed mid-trip with its own clock
reading 420 s of headroom). Also fixes the docked branch, which used to mean
"undock" unconditionally and would have undocked again the moment the ship
reached home. See `notes/350-trip-home.md` for the write-up.

This only fires when `secondsToSessionEnd` is set, so **the launcher must pass
`--session-duration-minutes`** or the trip home never happens at all.

### 6. Retire wingus, and `legacy_search_ui_root` with it

Only after this bot has flown. See the top of this file.

## Settings

| setting | what it does |
|---|---|
| `accept-fleet-invite-from` | Pilot whose invitations to accept, exactly as the client writes it. Repeatable. **This is where the trust is**: accepting means the fleet can warp this ship and call its targets. |
| `follow-fleet-broadcast-from` | Pilot whose travel broadcasts to follow. Repeatable, matched exactly. Does **not** gate target broadcasts, which carry no sender. Also the fallback behind `fleetCommanderName` when the fleet window's header names nobody — which since #367 is the only time it is consulted for that. |
| `activate-module-always` | Tooltip text of modules to keep active. **Optional and usually unnecessary since #394**: the middle row right of the propulsion module is already held on by position. Use it only for a module outside that row, and note it acts only once the bot has read that module's tooltip. |
| `home-station` | Station to return to when the session ends. Defaults to `Amarr VIII (Oris) - Emperor Family Academy`. |
| `assist-fleet-commander` | `no` keeps drones on this ship's own target. Defaults to `yes`. |
| `run-away-shield-hitpoints-threshold-percent`, `run-away-armor-hitpoints-threshold-percent` | Percentages below which the bot breaks off and warps back to the commander, read through the believed gauge behind a low-water mark. **Both default to -1, which is off.** |
| `run-away-incoming-damage-threshold` | Hitpoints of incoming damage over a rolling 45-second window, past which the bot breaks off. Needs no HUD gauge. **Defaults to -1, which is off.** |
| `orbit-fc` | Keep this ship on station beside the fleet commander by approaching their overview row (#365, #368). Defaults to `yes`. Also spelled `approach-fc`; the `orbit` spelling is kept so a settings string written for an earlier version still starts a session. **It does not govern the close on landing** — since #397 that happens whatever this key says, and the key governs only the steady-state station-keeping after the client reports the manoeuvre. |
| `orbit-fc-range` | **Accepted and ignored.** It named a rung of the client's `Orbit` submenu, which this bot no longer drives. Still parsed so a settings string carrying it does not end the session before it starts (#161), and named as ignored in the status line whenever it is set to anything but `500 m`. |
| `orbit-in-combat` | Inherited, and **superseded by `orbit-fc` rather than sitting beside it** (#368): with `orbit-fc=yes`, `decideActionInAnomaly` does not issue its own orbit at all. |
| `deactivate-module-on-warp` | Inherited, unchanged. |

**These live in the launcher's profile, not in the console.** A settings change
applied through the web console lasts exactly as long as the session: it is
re-sent to the running bot and nothing writes it back, so the next launch reads
the profile block again. Four ships were pointed at a new commander through
their consoles on 2026-08-22 and were back on the old one after their next
restart.

## Not verified

- **Any of the retreat-recovery arm running** (#381), and two things about the
  situation it acts in. How often the commander's banner is up while this ship
  is recovering decides which of the arm's two levers carries it, and whether
  the banner's `Warp to Member` is offered for a mate on another grid in the
  same system has never been read. Both fail safe: an unavailable cascade
  spends the bound and falls to the give-up, which hands the reading back. What
  to watch is in that section; the direction it fails silently in is
  `Nowhere remembered:` on every reading of a run whose commander has been
  broadcasting.
- **Why the four wingmen's member rows differ, which #380 leaves open and this
  does not close.** The candidates are a window collapsed or scrolled so only
  rendered rows parse, a fleet in wings and squads with only some branches
  expanded, and a parse that depends on window size — and `FleetWindow
  .fleetMembers` being a list of raw unparsed nodes while `fleetMemberNames`
  scrapes `entryLabel` display texts out of the window's descendants is
  consistent with all three, since a row that is not rendered contributes
  nothing. **The roster rule is correct under all three**, because each makes
  the rows a subset of the fleet and it compares against the header's own
  count rather than reasoning about rows. What would settle it is one capture
  per client, side by side at the same moment: `/check-ui-parse` against each
  wingman's Fleet window with the wings and squads expanded, recording the
  `FleetMember` node count, the `entryLabel` texts under them, the window's
  display region, and whether a scrollbar is present. #411 is the separate
  issue about what else those raw nodes carry; a capture for this one wants
  the geometry, not the fields.
- **Any of the roster verdict running.** No wingman log is on this Mac, so
  nothing has watched the clause. What to watch on the first run: `Fleet
  membership: corroborated -- the Fleet window's header states N pilots and N
  are resolved.` on an ordinary reading. `NOT CORROBORATED ... states no fleet
  size` on **every** reading would mean `Fleet (N)` is not where this parse
  looks, and the bot would then hold fire on every player all session — safe,
  visible, and the direction to expect if the capture is unrepresentative.
  `NOT CORROBORATED ... states N pilots and only M could be resolved` standing
  all evening with M one short of N is a client whose member rows do not list
  the reading pilot themselves, which the issue's own arithmetic argues against
  (Heather reads 4 rows in a five-pilot fleet whose fifth is the boss, which
  leaves no other assignment) but which nothing has read directly.
- **Whether the header states a size at genuine fleet sizes other than five.**
  `Fleet (5)` is the one capture. A fleet of one is the case the rule most
  needs and the one nobody has read: whether such a window draws `Fleet (1)`,
  draws nothing, or is not opened at all is unknown, and the middle answer
  makes a solo pilot hold fire on every player. That fails safe and says so on
  every reading.
- **Any of the backup-call arm running, and what the banner actually says.**
  #385's matcher is written from the issue's own live sighting, `...needs
  backup`, whose sender is elided — so **which of the two shapes this client
  draws is not established**, only that both are read. The rest of the arm has
  never run either: no wingman log on this Mac records a backup call at all,
  because until this change none could be read. What to watch on the first run
  that meets one: `Backup call:` in the status line naming the caller, then
  either `they are on this grid -- approach them.` or
  `warp to them from the broadcast banner's own menu.` in the decision log, and
  then the clause going away. Two failures point in opposite directions —
  `none on this reading.` while the banner plainly reads `needs backup` means
  the matcher is still not reading the client's wording, and
  `nothing on this reading says they are in this fleet` for a pilot who plainly
  is means #380's under-reported member rows are costing this arm — which the
  roster verdict now *reports* on the same reading without fixing, since
  `fleetPilotNames` is deliberately untouched.
- **The five remaining button labels.** A capture pass — one click per button,
  then read the history panel — is what turns them into matchable strings, and
  nothing here should match one before that happens. It would settle whether
  the `needs` / `Need` split is general (`X needs armor`, `X needs capacitor`)
  or particular to the backup call, which is the one thing that would let the
  rest be wired without a capture each.
- **Whether a backup caller can be out of system at all**, and what the client
  does with `Fleet Member` → `Warp to Member` when they are. The arm tries the
  cascade either way and lets the bound end it, because a backup call names no
  place and #381 is the issue that has to answer routing first. A run that
  spends the whole bound on one call and gives up is that case; a run that
  reaches a caller it could not see on the overview is the cascade working
  across the system.
- **Whether this client draws `targetedByMeIndicator` at all.** #389's fix
  decides "the called target is already locked" from
  `OverviewWindowEntry.commonIndications.targetedByMe`, which the vendored
  parser sets from a sprite of that name under the row's space-object icon, and
  **#390 put the friendly-fire guard on the same icon** — so two arms now
  depend on a flag nothing here has watched come back. The field and the icon
  name are the parser's, unchanged and shared by all six apps, but **nothing in
  `~/eve-bot-logs` records the flag coming back true**, and no
  `wingman_run*.log` is on this Mac to look in. The target-bar matcher is kept
  beside it in both places precisely so a client that names the icon something
  else degrades to the old behaviour rather than to a bot that never stands
  down — and, for the guard, so the added signal can only add refusals.
  What a run shows: `Lock the called target 'X'.` appearing **once** and then
  the reading reaching `dronesAssistTheCommander` and `Weapons:` — against the
  #389 signature, which is that line every reading with targets locked in the
  same status block.
- **What a `Target` broadcast on an acceleration gate renders as.** #393 reads
  one as licence to take the gate, and the row is found by matching the name
  `targetBroadcastPilotName` parses out of the banner against the overview's
  `objectName` by exact equality — two string derivations that both have to
  agree, and **nobody has ever captured such a broadcast**. One capture pass
  with `eve_read.py` settles it: broadcast a `Target` on a gate and read the
  banner text beside that row's `objectName` and `objectType`. Until then the
  recognition is built to say so rather than to do nothing silently — see
  "A `Target` broadcast on a gate is the fleet being sent through it" for the
  clause and the failure direction. Also unread: what the client does if a lock
  is aimed at a gate at all, which is the same question #366 lists for
  out-of-range and already-locked objects.
- **How often the friendly-fire guard is defeated by a wrapped name.** The
  weakness is established (#303's live read; see "Never shooting the fleet"),
  the frequency is not: it depends on how the client wraps the pilot names this
  fleet actually flies with, and no wingman log on this machine holds a locked
  player. `Friendly fire guard: N locked, none of them a fleet pilot -- clear
  to fire.` printed while the Fleet window names somebody who *is* in the bar is
  what it looks like.
- **Every number the health retreat would need (#364).** The mechanism is
  built and proven by `elm make` and by
  `test_wingman_retreats_to_the_commander.py`; **none of its thresholds has a
  measurement behind it**, which is why all three ship at `-1`. What a run has
  to record before any of them can be set:
  - **What this hull's shield actually does under fire.** Saxrat's hull rests
    at or below 5% shield on 60% of the readings it takes under fire, with the
    armour still at 98-100%, which is why its shield threshold is `-1` rather
    than a number — 0% shield is that ship's resting condition, not a warning.
    Whether that is true here is a fact about *this* hull and nobody has looked.
    Watch `Believed hitpoints:` in the status line across a fought run.
  - **What the armour threshold should be**, from the same series. Saxrat's 70
    was set from a corpus of fourteen runs; there is no wingman equivalent.
  - **The incoming-damage number.** Saxrat's 3500 sits between the 3114 the
    worst surviving session absorbed and the 4101 the session it lost the ship
    in peaked at — *on an Omen Navy Issue*. Carrying it to another hull fails
    silently in whichever direction that hull is different. Watch
    `Incoming damage: N/off over 45 s` and take the peak from a fought run.
  - **Whether `retreatAskedReadingsBound` (36) is right here.** Borrowed from
    the mission runner's `retreatNotExecutingAlarmReadings`, the same way
    `accelerationGateRefusesThisShipTicks` borrowed its 40. That bot has
    recorded retreats of 30, 89 and 142 readings that eventually worked, so
    this bound will sometimes hand back a retreat that was still going to
    succeed. Watch for `Retreat: GAVE UP` in the status line.
  - **Whether the retreat's own warp works at all.** This entry used to read
    that `goToFleetMate`'s "Warp to Member" cascade was "proven for the
    broadcast arms, not for this caller" — and #373 established that it was not
    proven for *either*, because it was attached to the wrong element. That
    cascade belongs to the fleet broadcast banner's menu, not to a pilot's
    overview row, and driving it from a row could never resolve at any range.
    The banner cascade is now used only where a banner from that pilot is up;
    the recovery path presses the Selected Item panel's own Warp To instead.
    Nothing has yet watched either half fly for a ship that was hurt.
- **Anything about the landing window running (#397).** No run has been flown,
  and by construction this path has never fired: the arm it hoists was
  unreachable on every grid with a fight on it, which is the defect. What a run
  shows on the reading after a warp ends is
  `Approach on the commander: CLOSING SINCE LANDING (…)` and then the approach
  taking the reading rather than `Weapons:` or the broadcast arm — and the
  clause **going away** within a reading or two, on the reading the client names
  the manoeuvre. Two failures to watch for, in opposite directions. A run whose
  clause never appears at all means the window is never opening, which would
  mean `warpJustEnded` is not firing here — #205's own tell, and the direction
  this fails silently in, since the bot then behaves exactly as it did before.
  And a clause that stays up while the count in the same line climbs towards 40
  is a landing on which the manoeuvre never took: the fight is being held off
  for that whole budget, which is the stated cost, and the give-up is what ends
  it. **How long a landing close normally takes is unmeasured**, so nothing here
  says whether that budget is generous or tight for this ship.
- **Whether a double click on a *pilot's* overview row commands an approach.**
  The gesture is proven — `eve-online-saxrat` double clicks a rat's row for
  exactly this, and the framework function is that bot's, ported unchanged —
  but no run in the corpus has recorded `ManeuverApproach` coming back, on any
  row, so what the client answers for a fleet member is unwatched. A first run
  either shows
  `Approach on the commander: approaching, commander at N m`, or falls back and
  prints `FELL BACK to the panel's Approach button`, or spends both budgets and
  prints `GAVE UP after 40 readings`. It cannot fail silently, because a
  dispatched click is never counted as success — and if the fall-back is what
  carries the session, the fix is to swap the two, which is a reordering of one
  `if`.
- **Whether `selectedItemApproach` is offered for a *pilot* row, and at what
  range.** The name is not a guess — `eve-online-mission-runner` reaches the
  button by it and its own note records it working — but the only live use
  recorded is on a **drone row**, not another player's ship, and every one of
  the three corpus mentions is that bot reporting the panel offered **none**,
  for a gate 5,843 m away. So the button may well be range-gated. If the client
  offers no Approach for the commander, the status line says
  `the panel offers no 'selectedItemApproach' yet` for the twenty readings the
  fall-back gets and then gives up — which is the bounded, visible failure, not
  a silent one.
- **What the four pilots actually have in the middle row (#394).** The rule
  reads the row by position and cannot check what is fitted, so the whole thing
  rests on the leftmost middle slot being the propulsion module on every ship.
  Nobody has looked at the four fits, and a ship with a hardener in that slot
  gets it cycled with the approaches rather than held on. What a run shows: the
  status line's `Middle row:` clause names the row it resolved, so one console
  reading per pilot settles it — `keep-active []` with modules visibly fitted
  means one slot was found and the rest were not, and `no module slots read`
  means the middle row was not resolved at all.
- **That the propulsion module comes on at all, and comes off again (#394).**
  `ManeuverApproach` still appears nowhere in `~/eve-bot-logs`, which is the
  same gap `approachTheFleetCommander` has: if the client never names the
  manoeuvre, this module never runs, and the failure is silent apart from
  `this ship is not approaching` sitting in the status line while the ship
  visibly moves. The shutdown direction is the one to watch on arrival — the
  module has to come off when the approach ends, and nothing has watched a
  reading where it does.
- **That `isDeactivating` ever reads `True` on these clients (#408).** This is
  the load-bearing unknown in the fix, and the parser's own doc block says as
  much: across the 240-second sampling window that mapped these entries,
  `isDeactivating` was **never once `True`**, because nothing switched a module
  off while the sampler ran. The complement of it — `isInActiveState` — is
  measured by saxrat's #286 across 61,948 module observations, and the
  transient it names is short: median two readings, longest seven. Against a
  ten-second cycle read every two seconds that is most of the cycle but not all
  of it, so a reading can land in the gap and buy one more click. What a run
  shows: the status line now says which of the three answers the client gave.
  `already deactivating` on the reading after a shutdown click is the fix
  working. `says nothing about whether the propulsion module is deactivating`
  for a whole session means this build does not carry the entry at all, and the
  propulsion module will never be switched off — bot still flying, module
  stuck on. And a `GAVE UP` after twenty means the click is landing on
  something that is not the propulsion module, which sends this back to #394's
  position assumption rather than to the cycle.
- **Whether twenty readings is the right allowance against a ten-second
  cycle.** The bound is `weaponsAskedReadingsBound` for consistency, not from a
  measurement of this arm. Twenty readings is roughly forty seconds, and with
  the debounce that is about ten clicks — five net toggles of a module the
  operator would rather have off. With `isDeactivating` read it should never
  get near that; nothing has watched a run to confirm it does not.
- **Whether the middle row's capacitor cost is bearable ungated.** The choice
  not to gate the always-on set on a fight is argued rather than measured, and
  the counter-evidence would be a wingman running its capacitor dry sitting on
  station. Nothing has watched the capacitor gauge over a session.
- **Whether the commander's overview row is there to be clicked.** The
  approach acts on an overview row, so the active overview preset has to show
  fleet members. Nobody has confirmed which preset the four pilots are flying,
  and the bot cannot tell a hidden fleet member from an absent one — see
  "Keeping station on the commander is an approach, not an orbit".
- **Whether the unified `fleetCommanderName` aims the retreat at the right
  pilot.** #367 made it prefer the fleet window's header and keep
  `follow-fleet-broadcast-from` as the fallback, which fixes the case #369
  flagged — a retreat decided with nowhere to go because the setting was unset
  — but it also means the retreat now inherits the header inference (see
  "Which header label is the commander"). Nothing has watched a retreat aim at
  a header-derived name.
- **Everything about the friendly fire guard, on a live client.** `elm make`
  and `test_wingman_holds_fire_on_fleetmates.py` prove the rule and its
  placement; no client has been watched. What to watch on the first run:
  whether `Fleet membership:` ever reads `NOT CORROBORATED` for a session that
  was in a fleet the whole time (which would mean the guard is running in its
  degraded mode by default — since #380 that has three causes and the clause
  names which, the window being shut being only one of them), whether
  `Friendly fire guard: UNLOCKING` is ever followed by the
  same name still being locked on the next reading, and whether
  `GAVE UP unlocking` appears at all — which would mean the `Unlock` menu entry
  is worded differently from the sketch that was ported.
- **Whether refusing to fire on any overview pilot with the window shut costs
  a real fight.** The refusal is deliberate and its remedy is documented, but
  nobody has flown a session where a genuine hostile went unengaged because of
  it.
- **How fast local chat's fleetmate icon reacts to a join or a leave.** See
  "Local chat's standing icons add names and cannot certify a list".
- **Whether a target broadcast can name something that is not a pilot** — a
  structure, a wreck. Only a pilot has been observed, and the overview match
  would simply fail on anything else, which is the safe direction.
- **The remaining eight broadcast wordings**, as above.
- **Which header label is the commander**, as above.
- **Firing on a called target.** The ordering fix that makes the guns
  reachable at all is proven by `elm make` and by
  `test_wingman_engages_the_called_target.py`, not by a client. What to watch
  on the first run: whether `Weapons:` in the status line moves off `nothing
  locked` once a target is called, and whether it ever reaches `GAVE UP` —
  which would mean the weapons are reachable but something else (range, a
  wrong active target) is stopping them from cycling.
- **Whether the called target ends up the *active* target.** `fireOnActiveTarget`
  activates weapons on whatever the client considers active; it does not force
  the called target into that slot. In practice a fresh lock becomes active on
  its own, but a ship that already had something else locked may fire on the
  wrong thing, and nothing has watched this happen either way. **This was
  filed as an accuracy caveat and that was the wrong frame** — the same gap is
  how a fleet member gets shot, which is a safety property. #367 is what
  closed the safety half; the accuracy half is still open.
- **The trip home.** Has not flown.
- **Navigating to the commander when out of system.** `elm make` proves the
  types; nothing has proven a jump. See "Navigating to the fleet commander
  when out of system" above for what to watch on the first run that reaches
  it — in particular whether the panel or the marker cascade ends up doing
  the flying, and whether the surroundings-button fallback's absence is ever
  actually missed.
- **The trip home (#350).** `elm make` proves the types; nothing has watched
  the ship actually reach `home-station` and stay docked. See
  `notes/350-trip-home.md` for what to watch on the first run.
- **Whether a *live* called target's overview row can vanish and come back.**
  #395's bound is three readings, sized against a reading whose overview did not
  parse rather than against a target drifting, because
  `CalledNameNamesNoOverviewRow` is not virtualisation — a scrolled-out row is
  still in the tree. The other way to reach it is the overview's own range
  filter, and nobody has watched that happen. If it is common, the tell is
  `No row has named it for 1 of 3 readings` appearing and resetting over and
  over while the bot goes on locking the target normally; the fix would be a
  larger bound rather than a different rule. See "A called target that dies
  leaves the banner naming it".

## Flown

- **Accepting a fleet invitation** (2026-08-25, live). See "What it does now",
  step 0.
- **Reading and following a travel broadcast** (2026-08-25, live). See "The
  two broadcast forms are shaped differently", above.
- **Locking a called target** (2026-08-25, live). Reported from the field as
  working well, alongside travel — and in the same breath as engaging that
  target being a D-, which is what "Why the guns are their own arm, below the
  drones" above is about. The lock was never the broken half.
