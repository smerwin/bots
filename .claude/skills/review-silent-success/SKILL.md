---
name: review-silent-success
description: Review changes for this repo's signature bug class — code that reports success while doing nothing. Use when reviewing edits to the host, the parser, or bot decision logic, or when something "works" but has no observable effect.
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Bash
---

# /review-silent-success — did anything actually happen?

Almost every expensive bug in this project has the same shape: an operation
that cannot succeed, reports success, and gets retried forever. Nothing throws,
the log looks busy, and the run accomplishes nothing. Ordinary review catches
wrong answers; this catches *no answer wearing a success mask*.

Review the changed code with one question in front: **if this fails, does
anything say so?**

## The pattern, in real instances

- A parser filtered on a type name the client does not use, so a window read as
  absent rather than as an error. The guard behind it could never pass; the bot
  re-clicked the same row 842 times over 13 minutes.
- The volatile-process request handler answered *every* unrecognised request
  with `CompletedEffectSequenceOnWindow`. Any unimplemented request reported
  completion, having done nothing.
- A scrollbar drag computed from a target's rank clamped to where the handle
  already was, emitting a zero-length drag — while the log cheerfully reported
  a scroll every tick.
- An AU distance failed to parse and every consumer substituted `999999`, which
  reads as "far away" rather than "unreachable". One run logged the failure 444
  times.
- A children walk bailed at the first non-list, so whole subtrees read as
  childless and their buttons were invisible while plainly on screen.
- A keystroke bound to the wrong action left the ship at 0.0 m/s for 100
  seconds with the distance frozen, and the decision looked correct throughout.

## What to look for

**Catch-all returns.** A fallback that returns success for anything it does not
recognise. Make it name what it could not handle, at minimum to stderr.

**`Maybe`/`Result` collapsed to a default.** `Maybe.withDefault`, a bare `_ ->
False`, a placeholder number. Ask what upstream failure that default is
disguising and whether the caller can tell the difference between "no" and
"could not tell".

**Guards that can never pass.** For any new `if <predicate> then <act> else
<try to make predicate true>`, ask what proves the predicate ever becomes true
on this client. If the "act" side has never been observed in a log, treat that
as unproven, not as untested-but-fine.

**Names matched against the client.** Any string compared to
`pythonObjectTypeName`, `_name`, a column header, or a texture path is an
assumption about this specific build. Verify with `/check-ui-parse` rather than
trusting the upstream name.

**Input that is dispatched but not executed.** Effects translated, logged, or
counted, but never reaching `cg_input`. A "completed steps" count that
increments regardless of what the executor did is not evidence.

**Retry loops with no ceiling.** If the recovery path is "do it again", ask
what changes between attempts. If nothing does, it is an infinite loop with
good manners.

## Bias for loud failure

Prefer an error that stops the run over a plausible default that continues it.
This codebase's own history is the argument: every entry above cost far more
time than a crash would have, precisely because the log looked healthy.

Where loudness is genuinely too risky — a change to a working path with live
behaviour at stake — say so explicitly and add the observability instead, so
the next occurrence is diagnosable from the log alone.
