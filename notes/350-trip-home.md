# #350 -- the wingman's trip home

DMC-MPC-003, 2026-08-25. Implements the trip home
`sessionIsEnding` used to announce as "not implemented yet", which two live
runs (`DMC-MPC-001`, `DMC-MPC-003`) had already shown means: the ship sits
undocked and unpiloted until a person docks it by hand.

## What it does

While in space and inside the wind-down window (`secondsBeforeSessionEndToWindDown`,
200s before the planned end -- the same constant `sessionIsEnding` already
gated on), the wingman now:

1. Asks the host to set the ESI destination to `home-station` on every
   reading of the trip, via the same `hostDirectiveSetDestination` the travel
   broadcast already uses. Re-asked every reading rather than latched once,
   because the host only acts on a *change* of destination, so repeating it
   is a string comparison, not a repeated ESI call.
2. Flies the route with `flyRouteHome`, a second copy of
   `navigateTowardFleetCommander`'s body -- press the Selected Item panel's
   Jump button where it already shows the route's next gate, falling back to
   the route marker's right-click cascade otherwise. The same mechanism docks
   at the far end too: the route marker's own menu offers "Dock" once the
   destination station is reached, so nothing here has to know the difference
   between another jump and arrival.
3. Asks the host for more time via `@host extend-session`, budgeting 420
   seconds past the planned end (the mission runner's own precedent, and the
   same number -- run 17 there was killed mid-trip with its own clock reading
   420s of headroom). This is a lease, re-derived every reading: it stops
   being asked the moment the ship docks.
4. Gives up and ends the session in place if 420 seconds pass without
   docking, rather than asking for the lease forever -- the same "a longer
   bound, not a missing one" argument the mission runner's own
   `homeStationTripSecondsPastSessionEnd` makes.

## The docked-branch fix, which is not optional

`wingmanDecisionRootBeforeApplyingSettings`'s docked branch has always meant
"undock", unconditionally. Without a fix, a ship that reached `home-station`
would have been undocked again on the very next reading -- the trip would
have "succeeded" and then immediately reproduced #350's own stall one system
later.

`dockedSessionIsEnding` is the fix, and it is gated on *actually being at the
home station* (`context.memory.lastDockedStationNameFromInfoPanel == Just
stationName`), not merely on being docked somewhere with the wind-down window
open. The simpler rule -- "docked and the window is open, so stay" -- has a
real failure mode found while writing this: a session that starts docked (the
ordinary way to launch this bot) and is given a short
`--session-duration-minutes` would end on its first reading, never undocking
at all. Docked anywhere else, this falls through to the ordinary "Undock."
branch, so the ship still undocks and gets a chance to route home before the
session ends.

## What is deliberately not built

Same posture as `navigateTowardFleetCommander`: no third rung. There is no
restock and no pod recovery here, so `sessionIsEnding` (flying) and
`dockedSessionIsEnding` (staying put once actually home) are the whole of the
wind-down -- no separate docked-but-not-home phase, no maintenance while
docked.

Whether the wingman should abandon a fight to go home, or finish the grid
first, is explicitly out of scope per the issue -- `sessionIsEnding` is
reached from `wingmanDecisionRootInSpace`, ahead of the broadcast and drone
arms, so as written it *does* interrupt combat. Not defended here; noted
because it was not evaluated.

## Verified

`elm make` succeeds on `Bot.elm` paired with the real host's `Main.elm`.
`elm-format --validate` passes. Self-reviewed with `/review-silent-success`;
the docked-branch gap above is what that review found and this note
documents the fix for.

## Not verified

Nothing has flown. What to watch on the first run that reaches the wind-down
window:

- `Home station: heading to '<station>'. @host set-destination <station>`
  appearing in the decision log within a reading or two of the window
  opening, then the host's own `# ESI: destination ... set` on stderr, then
  the client's route panel naming the station.
- The same jump/dock messages `navigateTowardFleetCommander` already
  produces (`Jump through '<gate>' from the selected-item panel...` or one
  of the marker-cascade fall-backs), now firing for the trip home instead of
  for a fleet broadcast.
- The client's route marker offering "Dock" at the final leg, and the ship
  actually docking.
- `Session ending and docked at the home station '<station>' -- stay here
  rather than undock again.` appearing once the ship is home, and **not**
  another "Undock." on the reading after it.
- If the ship never reaches home: `Home station: gave up -- the session
  ended N seconds ago and I never reached '<station>'.` at N=420, and the
  session ending there rather than running on.
- Whether the extend-session lease is actually granted by the host for the
  full window -- if the process is killed before 420s past the deadline
  while still in space, that is the host not honoring the ask rather than
  this bot's own bound failing.
