# Coordinating five machines in one repository

Conflicts here are prevented up front, not resolved after. Four rules, in order
of leverage. The evidence they rest on is six weeks of this repo's own history:
three parallel WINGMAN.md write-ups needing a reconcile commit (#342), the same
first-run findings recorded twice one minute apart (#338/#339), the same turret
fix landed twice an hour apart (ff9c97c/418992a), a doc overwrite needing a
restore (#324), and a whole-file elm-format commit that conflicted with every
open branch (#320).

## 1. Claim the work before touching code

Before starting anything, assign yourself the GitHub issue — create one if none
exists — and comment which machine is working it. Check the open assigned
issues first; if someone holds the claim, pick something else. The claim
releases itself when the PR merges. This is the whole protocol: ten seconds of
checking is what prevents two machines fixing the same bug.

## 2. Findings are new files, never appends

A run write-up or finding goes in `notes/` as its **own new file** —
`<issue>-<slug>.md` or `<date>-<slug>.md`. New files never conflict; the test
suite already proves the pattern (one file per change, near-zero collisions).

`CLAUDE.md`, `WINGMAN.md` and `FINDINGS.md` are **consolidation targets**, not
scratchpads: folding notes into them is its own claimed, single-machine task,
which deletes the notes it folded in. Never append to them while anything else
is in flight. Do not put `merge=union` on them — it would have produced #342's
incoherence silently instead of loudly.

## 3. Ownership follows the live run

The machine flying a bot owns that bot's app directory
(`implement/applications/eve-online/<bot>/`) and its own host directory for the
duration of the run. Everything genuinely shared is **exclusive-claim**: the
Python hosts, the vendored parser (one change lands in all six copies, so it
conflicts with every app's open branch), the launchers, and the consolidation
targets above. For those: claim the issue, keep the change small, land it the
same day, and everyone else rebases immediately after it merges.

## 4. Land fast, land clean

- No direct pushes to `main`. Every change is a short-lived PR: rebase before
  starting, push within hours, rebase again before merging. Conflict volume is
  branch lifetime × overlap, and lifetime is the half we control.
- Run `elm-format` before pushing. A whole-file format commit afterwards
  conflicts wall-to-wall with every open branch touching that file.
