# #439 -- the follow arrived on a budget the ordinary permission had spent

2026-08-30. #411 gives the wingman a licence to take a gate nobody named. Live,
on one reading, it granted that licence to a ship that had nothing left to use
it with, and the ship did not move:

```
Acceleration gate: on the overview, GIVEN UP after 41 readings of asking.
Commander on this grid: SEEN AND GONE for 138 readings -- taken as him having
left. Acceleration gates on this grid: 1. FOLLOWING HIM THROUGH IT, rats on the
grid or not.
```

`FOLLOWING HIM THROUGH IT` is the permission granted; `GIVEN UP after 41
readings` is the budget for asking that gate already spent. The bot decided to
go and had nothing to go with.

Nothing here has been flown. Every rule is executed through the real `Bot.elm`
in `elm repl`, and every reading the cases fold is built as a UI tree and run
through the real `EveOnline.ParseUserInterface`, so what is asserted on is what
the bot would have been handed.

## This is #428's defect in the gate arm

`gateAskedReadings` advanced only while `askingTheGateToOpen` -- which is
`gateMayBeTaken` -- and reached zero only where **no gate was on the overview at
all**; on any other reading with a gate drawn it was *held*. So a budget spent
under one licence was never restored when a different one arrived, and the two
licences that arrive **mid-grid** are exactly the ones that need it:
`commanderLeftTheGrid` (#411) and `rejoiningAfterARetreat` (#429) both turn on
without the gate, the overview row or the grid changing, so no reset could fire.
On the grid above the ship spent its forty readings on the gate while the field
was clear, and by the time #411's licence appeared the gate had been given up on.

`accelerationGateRefusesThisShipTicks` is 40, hence the 41.

## What ships is #430's arrangement over a licence rather than a landing

`askedReadingsRefilledByANewLicence` answers the budget the counter carries
**into** this reading, refilled by a reason nothing has yet been spent against.

- **Both branches of the counter read that one value**, and the decision reads
  the count they write, so the arm and the memory update cannot come to disagree
  about whether the new licence bought anything -- #102's defect. A refill
  applied to the increment alone would leave a licence that arrives while the
  panel is showing something else spending nothing, and the next reading that
  selects the gate would find the budget still gone.
- **It is the budget carried in rather than the value written out**, so the
  reading that asks under the new licence is still charged. A counter refilled
  after the increment never charges the first reading of a new licence, which is
  #102's defect in the direction that under-counts.

## The permission is now defined over the licence rather than beside it

`gateMayBeTaken` is `gateIsLicensed (gateLicenceFromCase gateCase)`, so the four
reasons are enumerated once. A fifth reason added to the guard and left out of
the licence would be a refill that never sees it while the arm goes on behaving
exactly as it does today -- this repo's signature failure. Both read one closed
record type, so the compiler is what refuses that rather than a reviewer.

`GateLicence` spells the reasons positively, which is why it carries
`gridIsClearOfRats` where the case carries `ratsOnTheGrid`: a record where three
fields mean "this licenses it" and the fourth means the opposite is one a later
reader gets wrong.

## "The licence changed" is a reason not already spent under

This is the one judgement in the change, and the looser reading -- the licence
differs from the one it was -- **cannot be used**. `gridIsClearOfRats` is why:
rats arrive and die on a grid constantly, so that reason comes and goes on its
own, and a refill on every difference would hand the budget back every time the
last rat died. `accelerationGateRefusesThisShipTicks` would then bound nothing
at all, which is the failure this must not introduce while fixing the one it is
for.

`gateLicenceSpentUnderAfter` therefore **accumulates** the reasons already spent
against, on the readings that ask, and clears on the same reading the count
itself resets -- the count and the licence it was spent under are one episode.
So a reason returning is not a new one, and one gate can spend at most four
budgets before it is given up on for good.

Storing only the *last* reason asked under would be the same runaway reached
from the memory rather than from the rule: the commander gone while rats come
and go would alternate two reasons and refill on every swap.

## Verified without a live client

`tools/macos-host/tests/test_wingman_gate_licence_refills_the_budget.py`, 27
cases. The sessions are folded through the real
`updateMemoryForNewReadingFromGame` on one gate that is the same overview row
throughout, with the control -- the same grid, the same length of session, no
second licence -- beside each; without that control a session that ends
un-given-up says nothing, since any counter that only rises reaches any bound.

The case that matters most is the one the looser definition fails: a session
whose rats come and go still gives up at the bound. The case that matters second
is the live shape itself: forty-one readings under the ordinary permission, then
the commander's row gone for `commanderGoneReadingsBeforeFollowing` readings on
a grid that still has rats on it, and the arm answers `PressActivateGate` rather
than `GiveUpOnThisGate`.

Confirmed by mutation, eleven of them, each failing named cases listed in that
file -- including the looser definition, the memory replacing rather than
accumulating, a reason dropped from the licence, and `gateMayBeTaken` given back
its own disjunction.

## Unverified

**Any of it running.** No wingman run has been flown since, and this bot still
has no corpus of its own.

What to watch on the first run that meets a gate is `readings spent asking: N of
40` **going back to a low number** on the reading the status line starts saying
`CALLED by the commander`, `gating back to its commander after a retreat` or
`FOLLOWING HIM THROUGH IT` -- and then a press rather than another `GIVEN UP`.
The failure to watch for is the opposite: `readings spent asking` never climbing
past a handful on a grid whose rats come and go, which would mean the refill is
firing on a reason already spent and the bound is no longer bounding.

**What is deliberately not changed**: `gateAskedReadings` still advances past the
give-up for as long as a gate is drawn and the panel is showing it, where the
other counters in this file hold once their budget is spent. It costs nothing
here -- a refill sets the count to zero whatever it had climbed to -- but the
status line's "GIVEN UP after N readings" is a count that runs away, and
narrowing it is a behaviour change with its own evidence to gather.
