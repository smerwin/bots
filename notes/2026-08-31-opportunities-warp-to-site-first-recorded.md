# `Warp to Site` from the Opportunities tracker, recorded for the first time

`saxrat_run67.log`, 2026-08-31, bot version `32f40c1`. Watched live by the
operator and confirmed in the log afterwards.

## Why this is worth a note

`warpToOpportunitySiteIfAvailable` prints

    The Opportunities tracker offers '<label>' for <site> -- take it.

and `travelLabelIsACommand`'s own doc comment describes `Warp to Site` as
"what this branch has been matching all along". Until this run, **it had never
been observed doing so.** Across every `saxrat_run*.log` in `~/eve-bot-logs`,
that sentence had only ever carried three labels:

| label | occurrences |
|---|---|
| `Jump` | 754 |
| `Set Destination` | 53 |
| `Undock` | 1 |

`Warp to Site` did appear 577 times in the corpus, but only under the earlier
wording this branch replaced — `I see a 'Warp to Site' opportunity -- warp
there.` (`saxrat_run12`, `run19`, `run27` among others, and it resolved into a
warp there too). So the behaviour was proven under code that has since been
rewritten, and unobserved under the code that ships. This run closes that gap.

## What was recorded

Two takes, both in Hahda, both for the same escalation:

    12579:+++++ The Opportunities tracker offers 'Warp to Site' for
           Sansha's Command Relay Outpost -- take it.
    12857:+++++ (again, reading 459)

The first, at reading 444, resolves end to end: the click, then 45 readings of
`IN WARP`, a `HOOOOONK in warp`, and `Arrival window: OPEN`. An acceleration
gate is on the overview on arrival, which is the shape of a Command Relay
Outpost, and the next decision is `I see an acceleration gate -- select it, so
the panel's own Activate Gate acts on it`. The second take at reading 459 has
the same shape and also ends in a warp and an arrival.

`FC off` on this run, so nothing here depends on the fleet-commander path.

## What this does and does not settle

**Settles:** the current implementation takes a `Warp to Site` step and the ship
arrives. The label is in `travelLabelIsACommand`'s allow-list for a reason and
the allow-list matches what the client actually renders.

**Does not settle:** the label's rarity. Two takes in one run against 754
`Jump`s across the corpus is consistent with the tracker usually offering travel
to another system rather than a warp within this one — escalations are mostly
elsewhere. Nothing here measures how often a `Warp to Site` is on offer and
missed, only that one on offer was taken.
