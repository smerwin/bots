# #429 -- a retreated wingman could only rejoin a commander who was broadcasting

2026-08-29. Four wingmen retreated to repair in an escalation in Bika under a
**human** fleet commander -- Gal Bistot flown by hand, its own bot not running
-- and not one of them got back. They parked healthy for the rest of the
session, and the two halves of the cause are quoted verbatim in their own status
lines.

Nothing here has been flown. Every rule is executed through the real `Bot.elm`
in `elm repl`, and every reading the cases are asked about is built as a UI tree
and run through the real `EveOnline.ParseUserInterface`, so what is asserted on
is what the bot would have been handed.

## Every route back was gated on something a human commander does not produce

Kara Kernite, stuck, states the first half:

```
Retreat recovery: the commander is off this grid and nothing names a place to
fly to, so the reading is handed back. Nowhere remembered: no broadcast has
named a place since this ship was last with its commander.
```

and all four report the second:

```
Warp to a fleet-mate: nobody this ship is flying to has a row on this overview.
Approach on the commander: 'Gal Bistot' has NO OVERVIEW ROW. Either they are not
on this grid, or the active overview preset does not show fleet members
```

Three gates, and each of them is a broadcast in disguise:

- **#415's recovery routes to `fleetPlaceBroadcast`**, which
  `fleetPlaceBroadcastAfterReading` writes only from the banner. A commander who
  never broadcasts leaves it `Nothing` for the whole session, and the arm's last
  answer -- `NowhereToRejoinTheCommander` -- hands the reading back.
- **The warp-to-a-fleet-mate arm needs an overview row**, which the operator's
  preset does not draw for fleet members, and which the bot cannot change and
  cannot tell apart from "not on this grid".
- **#348's guard refuses an acceleration gate while rats are on the grid**
  unless the commander *called* it, which is another broadcast -- and an
  escalation is one or two gates deep, so this bites on the way back even with
  the first two solved.

That is reasonable for a bot commander and wrong for a human one: the operator
has to remember to broadcast before each ship gets hurt, and a ship that
retreats without a recent broadcast is lost for the rest of the session.

## The rejoin, in four parts

**A row that is always there.** The fleet window is open for the roster on every
reading whatever anybody broadcasts, and `fleetCommanderNameFromFleetWindowHeader`
already reads the commander's name out of it. What no function could do was
*click* it. `fleetWindowRowForPilot` answers the same question as nodes rather
than as strings, and `warpToFleetMateFromTheirFleetWindowRow` drives the client's
own `Fleet Member` -> `Warp to Member` off it.

**The header is searched as well as the member rows, and it is where the
commander is.** `fleetMemberNames`' own comment records the boss being drawn in
the window's header rather than in a `FleetMember` row -- so a lookup over the
rows alone would answer `Nothing` for the one pilot it exists for.

**The menu node is shared rather than copied.**
`warpToMemberFromTheBroadcastBanner` keeps its name, which records where the two
rungs were captured live, not the only element they may be driven from: the
question it answers -- `Warp to Member` directly, else inside a `Fleet Member`
submenu -- is about what the client offers rather than about which node was
right-clicked.

**A gate, asked before that warp, and the ordering is what terminates.**
`Warp to Member` lands this ship at the mouth of the pocket rather than beside
its commander, so a rule offering the warp first would warp, land, find the
commander still off grid and warp again until the budget was gone. The gate
clause reuses `accelerationGateStep` -- the select-then-press, its bound and its
drone recall -- rather than adding a second gate mechanism.

**One uncalled gate, scoped to the reading rather than to the retreat.**
`gateMayBeTaken` gains a third input and `rejoinIsTakingThisGate` is the one
declaration that answers it, asked of the shipped `RetreatRecoveryStep`. So the
permission exists only where `recoverFromRetreat` is itself dispatching this
gate: a recovery past its bound, a recovery routing to a remembered place, and a
bot that is not recovering at all each leave #348's guard exactly what it was.
`rejoinIsTakingThisGate` has four readers -- the arm, the press's own wording,
the memory update's counter and the status clause -- and the memory update asks
it of `recoveringStepNow`, the same answer that decides whether the reading
spends the recovery's budget, so the counter and the permission cannot disagree
about which reading it is.

**And the press says which authority it is on.** Without that the rejoin would
print `The overview is clear of rats -- activate the acceleration gate` on
exactly the readings this change is about, which is a status line disagreeing
with the decision it is on.

## The bound is #415's, and no new counter was added

Both new answers are in `retreatRecoveryAnswersThatSpendAReading`, because both
dispatch -- so they are advanced and read by the same rule, and #102's defect is
a counter advanced by one condition and read by another. Past
`retreatRecoveryAskedReadingsBound` (30, still written as
`fleetMateWarpAskedReadingsBound`) the arm hands the reading back rather than
parking, which is #415's posture and what makes the arms below reachable.

**#430's `askedReadingsRefilledByLanding` deliberately does not apply here**, and
the reason is that this arm already had the property that rule adds. It refills
the approach and fleet-mate-warp budgets on a *completed* warp because neither
counter had a matching reset; `retreatRecoveryAskedReadings` resets on every
reading `AlreadyOnTheWayBackToTheCommander` answers, which is the same event at a
finer grain -- so a rejoin gating across a pocket gets the whole allowance for
each leg, and what accumulates is clicking with the ship standing still.

## What is preserved, and what it costs

The two broadcast-fed answers keep their places ahead of the two new ones, so a
reading #415 could act on is a reading #429 does not touch. The cost is stated
in `recoverFromRetreat`'s own doc comment rather than hidden: a place broadcast
before the retreat outranks a gate standing right here, so a ship part of the way
back on an earlier leg routes to the remembered system instead of gating on.
That is the behaviour #415 shipped and this change is scoped to the readings on
which it had nothing at all.

## Verified without a live client

`tools/macos-host/tests/test_wingman_rejoins_without_a_broadcast.py`, **51
cases**, plus the existing recovery suite's 60 kept green. The rules are
executed through the real `Bot.elm` in `elm repl`: the step rule rendered as one
constructor name per case so a rule answering two things at once -- or none --
fails rather than passing on whichever one a case named; the bound at both sides
*and* against fixed values either side, since a case asking only `constant - 1`
and `constant` passes for any constant; `gateMayBeTaken` over the whole grid of
its three inputs; and `fleetWindowRowForPilot` rendered as the answered node's
own `totalDisplayRegion.y`, so a case can say *which* node was answered rather
than only that some node was.

**The discriminating case is one grid asked twice.** Rats and an acceleration
gate on one overview, the commander off it: asked as a rejoin the gate is taken,
asked with nothing recovering it is refused, and what separates the two answers
is the rejoin rather than the fixture. Two more ask the same grid with the
budget spent and with a place remembered, and both put #348's guard back --
which is what makes the permission the rejoin's *reading* rather than the
retreat's latch.

Confirmed by mutation, **ten** of them, each failing a named case: the rejoin
dropped from `gateMayBeTaken`, which is the whole change reverted; the
permission widened to "this ship is recovering", which is the scoping the issue
asks for undone; the warp asked before the gate, which is the shape that warps
forever; the two new answers hoisted above the remembered place, which is #415's
path displaced; both dropped from the answers that spend a reading; the row
matched as a substring; the header dropped from the row lookup, so the commander
has no row at all; the press wording reverted to claiming a clear overview; and
the bound removed, which fails five cases across four classes.

**One mutation survived the first pass and the hole was real.** The row lookup
was written with `fleetMemberNames`' own timestamp filter, to keep the broadcast
history out -- and no mutation could kill it, because the exact match already
had: `02:59:30 - Gal Bistot is at location Amarr` is not equal to `Gal Bistot`.
A second filter no case can kill is #42's shape, so it is gone and the case that
was written for it now asks the exactness instead, where the loose-match
mutation does kill it.

## Unverified

**Any of it running**, and one premise about the client. The
`Fleet Member` -> `Warp to Member` rungs are recorded live off the broadcast
banner and off nothing else, and on this account the element this rejoin
right-clicks is usually a **header label** rather than a `FleetMember` row -- so
whether the client offers that menu there is not established. It fails safe: a
menu without the entry resolves nothing, the bound ends the attempt, and the arm
hands the reading back to the arms below.

What to watch on the first run that retreats under a commander who is not
broadcasting: `Retreat recovery: nothing has broadcast, so warping to the
commander from their own fleet-window row.` in the status line, then the cascade
in the decision log, then `Acceleration gate: on the overview and this ship is
gating back to its commander after a retreat,` on the reading it lands. A run
that prints the warp clause and then `GAVE UP after 30 readings` with the ship
never having moved is the header-label premise being wrong, and it is the one
thing a run has to settle. A gate taken while the bot is *hunting* with rats on
the grid would mean the permission is not scoped, and is the failure to escalate
on.
