# #402 -- an unrecognised message box owned wingman's session

2026-08-29. `eve-online-wingman` had no `MessageBoxStandoff` at all, and its
give-up named nothing about the dialog it had given up on. Both are fixed, and
the fix needed a **third** piece the issue does not mention.

Nothing here has been flown. Every rule is executed through the real `Bot.elm`
in `elm repl`, and every message box the cases are asked about is built as a UI
tree and run through the real `EveOnline.ParseUserInterface`, so what is
asserted on is what the bot would have been handed.

## The two defects, as filed

**The give-up named nothing.** `closeMessageBox` accepted only a button whose
`mainText` lower-cases to `close` or `ok`; anything else reached
`askForHelpToGetUnstuck`, and that line carried no display texts and no button
names. So a dialog nobody can name is a dialog nobody can write a matcher for --
#164's lesson on the other two bots, in the same words. Live, 2026-08-28,
`fbf4c2e`: a 400-line scrollback holding nothing but

```
+ I see a message box to close.
++ I see no way to close this message box.
+++ I am stuck here and need help to continue.
```

**And there was no bound.** No counter, no Escape rung, no give-up that hands
the reading back. `generalSetupInUserInterface` is evaluated above the
docked-or-in-space split, so an unrecognised dialog owned every reading for the
rest of the session. That is the mission runner's run 30 shape -- 32,585
readings, three hours and forty-four minutes -- unguarded here.

## The third piece: wingman had no `closeSystemSettingsMenu`

#402's second Unverified item asks whether wingman's setup list has that branch
ahead of `closeMessageBox`. **The answer is no, and it had no such branch at
all** -- the only occurrence of the identifier in the whole file was a
doc-comment mention inside `clearStrayContextMenu`, which presses Escape and
says that branch "exists because that happened live". It was naming a
declaration that did not exist. Both siblings have it as the **first** entry of
their setup list (saxrat `Bot.elm:1899`, mission runner `:7415`).

This is a prerequisite rather than a tidy-up. #109's argument is that Escape is
safe *because of that placement*: a naked Escape can open the client's own
Settings/pause menu, that menu covers everything the tree looks for, and the
recorded recovery from it was a person closing it by hand. Porting the Escape
rung without the branch would have traded a bounded message-box standoff for an
unbounded pause menu -- a different session-owning state, arrived at by the fix.

So it is ported, first in the list, and `getElementIdFromDictEntries` is added
to wingman's vendored `ParseUserInterface.elm` -- present in the mission
runner's, saxrat's and the haulerbot's copies, absent from this one, and what
the `closeMenuClick` lookup reads. That is the one way this port could not have
failed silently: without it the branch does not compile.

Wingman presses Escape in **three** places now, and the branch covers all of
them: `clearStrayContextMenu`'s fallback, `beginCascade`'s occlusion fallback,
and this rung.

## The ladder

#109's shape, unchanged. `messageBoxAnswersBeforeEscape` (60) readings of the
ordinary declining answer, then Escape at the same box for another 60
(`messageBoxStandoffGiveUpReadings = messageBoxAnswersBeforeEscape * 2`, written
as the multiple so the argument cannot drift away from the number), then
`Nothing` so the rest of the tree runs with the box still on the screen.

**60 is the mission runner's measurement, not wingman's.** There is no recorded
wingman run on the machine this was written on, so there is nothing here to
place a threshold in and a wingman-specific number would be invented. What
transfers is a measurement about *the client*: the same widget, matched by the
same `pythonObjectTypeName` filter in both parsers. That bot's recovered runs
give stretches of 6, 10, 11, 18, 20 and 44 readings and nothing else, while its
run 30's one box ran to 32,585; 60 sits in a gap rather than cutting a
distribution. `TheMissionRunnersCorpusIsWhatSizesThisBound` recounts that where
the corpus is present and skips where it is not.

**The count is per box**, keyed on the box's own display texts plus its buttons'
`_name`s and labels, and deliberately **not** its display region --
`routeFirstMarkerUnchangedTicks` is a region comparison and records what that
costs, which is a widget re-rendered each tick differing sub-pixel while looking
identical and a count that therefore never accumulates at all.

**The counter is written in `updateMemoryForNewReadingFromGame`** and read by
the branch, and both ask one question -- "is a message box the head of this
reading's boxes", answered by one `messageBoxIdentity`. A counter advanced by
one condition and read by another is #102's defect.

**The give-up hands the reading back.** It is not an alarm: an alarm leaves
every starved branch exactly as starved, which is what wingman already had.

## The answer set, and what is deliberately not in it

The operator's comment on #402 names three buttons -- `Close` for informational
popups, `No` for dangerous actions, `Ok` for "can't warp to fleet member not in
system". `close` and `ok` were already matched. `No` is the addition, taken in
two rungs: by the `_name` the client gives it (`no_dialog_button`, stable across
client languages) and then by its rendered label, for a declining button the
client did not name.

**No affirmative is anywhere in the automatic path**, which is #54's standing
rule: these dialogs guard destructive actions. Two cases pin it -- one executes
the branch against a box offering only `Yes` and requires it to click nothing,
one reads the source.

**The window's own close ('X') control is not a rung**, though both siblings
have it as their last one. saxrat run 22 lost its client to exactly that: EVE's
`Connection Lost` modal carries a single `Quit`, no `Close`/`OK` and no
`no_dialog_button`, so both recognising options missed, the close control was
clicked, and the log stops with no client process left. **The operator's own
note says the box seen here was a "client disconnected" box**, so that is the
shape wingman is known to meet.

`messageBoxSaysTheConnectionIsLost` is ported with it and answers
`LeaveTheMessageBoxAlone` at every rung -- because Escape at a modal whose only
action is Quit is the same keypress by another route. `botlab_host.py`
recognises the same box by the same two substrings and clicks the Quit itself,
which is where that decision belongs and is bot-agnostic already.

## One consequence worth knowing

A "Join Fleet?" invitation from a pilot **not** named in
`accept-fleet-invite-from` used to fall through the Close/OK matcher and reach
`askForHelpToGetUnstuck`, owning the session. It is now *declined* -- clicked on
`no_dialog_button` -- which is what the standing rule says an unread dialog
gets, and what saxrat already does. A case executes it.

## What #402 deliberately does not change

`acceptFleetInviteFromNamedPilot` is untouched and still its own entry above
`closeMessageBox`. **It carries no bound of its own**: an invitation from a
named pilot whose Yes click never lands would own the tree exactly as the
message box did. That needs the setting armed (it defaults to nobody) and the
click to fail, so it is narrow -- but it is a remaining hole rather than an
absence, and `TheFleetInviteBranchIsUntouchedAndStillUnbounded` records it so a
later change argues against it rather than rediscovering it.

`parseMessageBoxesFromUITreeRoot` is **not** narrowed. Narrowing treats the
instance and leaves the shape: anything the client draws on that widget which
the answer does not close reproduces the incident exactly.

## Unverified

- **Any of it running.** No wingman run has been flown since. What to watch:
  `Message box: N/120` in the status line with the dialog **named** beside it,
  appearing briefly and vanishing -- the recorded dialogs close in 2 to 44
  readings. A count that climbs is the first live instance of this shape; a
  count that never appears at all on a run that meets a dialog means the
  standoff is not being written.
- **What Greta's dialog was.** Still unknown, which is defect 1 and the reason
  the identity is now printed on every counted reading rather than only at the
  give-up.
- **Whether Escape closes a window the answer does not.** Its whole live outing
  across both siblings is one press (#164), so this rung is exactly as unproven
  here as it is there. What the give-up needs is readings spent, which the rung
  supplies whether or not the key works.
- **Whether `closeSystemSettingsMenu` fires on this client.** It has never run
  on wingman. It fails closed -- no `l_systemmenu` node means `Nothing` and the
  list moves on -- so the cost of it being wrong is the pause-menu risk the
  Escape rung was going to carry anyway.
