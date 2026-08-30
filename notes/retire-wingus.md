# Retiring `eve-online-wingus`, and the host code that existed only for it

`WINGMAN.md`'s roadmap section 6 -- "Retire wingus, and `legacy_search_ui_root`
with it. Only after this bot has flown." This is that, plus everything on the
host side that had exactly one caller.

## The precondition, and why it was met

That line was written into `WINGMAN.md`'s skeleton commit (`be47b3fc`,
2026-08-24) **before any wingman run existed**, so it was a promise rather than
a judgement about the wingman. It has since flown at least nine sessions, two of
which `WINGMAN.md` writes up itself: the 45-minute watched smoke test on
`DMC-MPC-001` (~1,467 readings, no exceptions) and the 25- and 60-minute runs on
`DMC-MPC-002`, which drove a real client end to end with no crash, no stall and
no `askForHelpToGetUnstuck`.

**Those runs found unwired features rather than a bot that could not fly** --
the travel-broadcast dispatch, the trip home -- which is the distinction the
condition was about. It was set so the last 2023-interface bot would not
disappear before its replacement was *proven*, and what "proven" had to mean is
that the job is servable on the current interface. It is.

No wingman log is on this Mac, so the flight record above is `WINGMAN.md`'s
rather than anything re-derived here. That is stated rather than glossed: this
change is graded on the suite and on the compiler, not on a run.

## Why the wrapper existed, kept because it is expensive to rediscover

`Main_2023_02_06.elm`'s own header is the reason it was not simply `Main.elm`
with different imports, and the reasoning outlives the file:

> This is the older host interface, kept alongside `Main.elm` (2024_10_19)
> because a bot's own source fixes which one it imports and the two are not
> interchangeable. The difference that matters: 2023_02_06 has no
> `WindowsInputRequest` task, so input is not a host-level task at all -- it
> travels inside the volatile-process request as
> `EveOnline.VolatileProcessInterface`'s `EffectSequenceOnWindow`, which the
> Python host translates and executes.

So the two interfaces differed in more than type names, and three pieces of host
code existed for that one difference plus one more:

- **`_effect_sequence_of_request` / `_effect_sequence_as_input_items`.** Input
  arrived inside a volatile-process request rather than as its own task, so
  `run_task` intercepted it and *translated* it into the item list
  `_windows_input` already executes -- deliberately translating rather than
  executing directly, so that everything the input path had learned about this
  client (eased movement, the double-click collapse, not pausing mid-drag,
  standing down for a human at the keyboard) applied to both interfaces
  unchanged. The 2023 vocabulary was narrower: mouse buttons were
  `KeyDown`/`KeyUp` carrying a mouse virtual-key code rather than their own
  `ButtonDown`/`ButtonUp`, and there was no scroll, no relative move and no raw
  character input.
- **`legacy_search_ui_root` and `_search_ui_root_blocking`.** #332. That
  interface's `VolatileProcessInterface.elm` had no notion of an in-progress
  search: it decoded only a flat `SearchUIRootAddressResult {processId,
  uiRootAddress}`. Answering it with the 2024 interface's staged
  `SearchUIRootAddressResponse` is a shape its own decoder's closed `oneOf` never
  matches, so the request failed to decode **silently** and the bot's setup state
  never learned the search had happened -- it re-asked forever while the host had
  already found and cached the root within the first second. That is this repo's
  signature failure arriving through a protocol boundary, and it is worth
  remembering the *shape* rather than the interface: a closed `oneOf` turns an
  unrecognised response into an `Err` that `BotFramework.elm` writes and never
  reads.
- **The wrapper map's second entry.** One wrapper per interface, chosen from the
  bot's own `import`.

## What was removed

| | |
|---|---|
| `implement/applications/eve-online/eve-online-wingus/` | the app, whole |
| `tools/macos-host/botlab_host/Main_2023_02_06.elm` | the port wrapper |
| `botlab_host.py` | the wrapper map's second entry; `MOUSE_BUTTON_VK_CODES`; `_effect_sequence_of_request`; `_effect_sequence_as_input_items`; `legacy_search_ui_root` (constructor argument, field, and its plumbing through `TaskDispatcher`, `run_bot` and `main`); the flat `SearchUIRootAddressResult` arm of `handle_request`; `_search_ui_root_blocking`; and the `EffectSequenceOnWindow` interception in `run_task` |
| `compile_bot.sh`, `.github/workflows/build-and-test.yml` | the second `case` arm |
| `tests/test_legacy_search_ui_root.py`, `test_hated_rat_removed.py`, `test_wingus_warp_end_trigger.py` | files whose whole subject was the removed code or the removed app |

### Two of those three carried a finding, and the findings are kept here

A test file deleted with its subject takes its doc comment with it, and a doc
comment is where two of these kept an argument nothing else states.

**`test_hated_rat_removed.py` is #125's check one step deeper, and the deeper
one is the reusable half.** #125's shape is a setting parsed and read *nowhere*
-- three occurrences and no fourth, which in Elm is a proof rather than a search
that came up empty. `hated-rat` passed that check: `BotSettings.priorityRats`
had a real reader, `getPriorityRatsSeenInAnomaly`, typed and compiled -- and
**nothing called the reader**. So "is the field read anywhere?" answered yes for
a setting that did exactly as much as one that was read nowhere at all. The
question that catches it is whether the *reader* has a call site, and it is the
one to ask of any future setting whose field looks honestly consumed.
`test_avoid_rat_removed.py`'s cross-app rule is still the shallower form and is
still asserted over every EVE app; nothing here weakens it, and no case is lost
by this deletion, since every case in the deleted file was scoped to wingus.

**`test_wingus_warp_end_trigger.py` held a case that is not about wingus**, and
it was narrowed rather than deleted -- see below. The file name and the class
name both counted apps, which is why the case had to move rather than stay:
`TheFourAppsCarryTheSameWorkingTrigger` names a population, and a population is
what a retirement changes.

## What was deliberately *not* removed

**`host_interface_of_bot` and `MAIN_ELM_TEMPLATE_BY_INTERFACE`**, which now hold
one entry. Collapsing the map into a constant would remove the one thing that
makes an unsupported interface fail *by name* -- `prepare_build_dir` raises
`no Main.elm wrapper for host interface ...` rather than compiling a bot against
the wrong wrapper. `compile_bot.sh` and the CI job keep their own single-arm
`case` for the same reason: each *names and skips* an app it has no wrapper for.
A one-armed `case` reads like dead weight and is a fail-loud guard.

**The `CompletedEffectSequenceOnWindow` fallback reply** in
`handle_request`. It is vestigial -- it was the shape a 2023 bot's input request
expected -- but every vendored `EveOnline/VolatileProcessInterface.elm` still
decodes that constructor, so it remains a response a live bot understands.
Changing what the host answers on a path every current bot runs is a behaviour
change, and nothing here is evidence for one. The `print` beside it, which is
what stops an unhandled request reporting success in silence, is untouched.

**`vk_to_mouse_button`**, which reads like part of the removed translation and
is not: the 2024 input path's `ButtonDown`/`ButtonUp` items carry virtual-key
codes too, and three call sites use it. `MOUSE_BUTTON_VK_CODES` next to it *was*
2023-only and went.

## Evidence that the 2024 path is unchanged

There is no live client here, so the strongest available evidence is a
before/after comparison of the host that ignores comments entirely. Both
revisions of `botlab_host.py` were parsed, their docstrings stripped, and
`ast.unparse`d -- so what is diffed is executable code with every comment and
doc comment removed. The result is **60 lines removed and 8 added**, and every
one of the 8 is the same statement with the `legacy_search_ui_root` parameter or
argument deleted:

    -MAIN_ELM_TEMPLATE_BY_INTERFACE = {'...2024_10_19': MAIN_ELM_TEMPLATE, '...2023_02_06': ...}
    +MAIN_ELM_TEMPLATE_BY_INTERFACE = {'...2024_10_19': MAIN_ELM_TEMPLATE}
    -    def __init__(self, game_log=None, legacy_search_ui_root=False):
    -        self.legacy_search_ui_root = legacy_search_ui_root
    +    def __init__(self, game_log=None):
    -    def __init__(self, execute_input=False, ..., legacy_search_ui_root=False):
    -        self.volatile = VolatileHost(game_log=game_log, legacy_search_ui_root=...)
    +    def __init__(self, execute_input=False, capture_screenshots=False, game_log=None):
    +        self.volatile = VolatileHost(game_log=game_log)
    -                effect_sequence = _effect_sequence_of_request(request_str)
    -                if effect_sequence is not None:
    -                    self._windows_input(_effect_sequence_as_input_items(effect_sequence))
    -                    response_json = json.dumps({'CompletedEffectSequenceOnWindow': True})
    -                else:
    -                    response_json = self.volatile.handle_request(request_str)
    +                response_json = self.volatile.handle_request(request_str)

**No statement on a 2024 path was rewritten, reordered or re-indented into a
different meaning.** Every removal is a branch reachable only when
`legacy_search_ui_root` was true, or a function only that branch called.

Beyond that: every remaining EVE app compiles through the CI job's own loop --
combat-anomaly-bot, haulerbot, mining-bot, mission-runner, saxrat,
warp-to-0-autopilot, wingman, all seven with `Main.elm`.

## The removal had nothing guarding it, so it has one now

**Re-adding `legacy_search_ui_root` to the host failed no case**, which is the
honest starting point: the tests that covered the removed code were *about* the
removed code and went with it. A removal nothing pins is one that can come back
in half -- the translation without the interception, say, which compiles and
does nothing.

`tools/macos-host/tests/test_host_interface_wrappers.py` is that guard, and it
covers a second hazard this change made worse rather than created. The rule that
picks a wrapper lives in **three** places -- `botlab_host.py`'s
`MAIN_ELM_TEMPLATE_BY_INTERFACE`, `compile_bot.sh`'s `main_elm_for`, and the CI
job's own `case` -- each carrying a comment telling the next person to keep them
in step, and nothing compared them. Two of those are what a developer and CI
build with, so a wrapper they choose and the host does not is a green build for
something no run would ever produce. This change edited all three.

Confirmed by mutation, eight of them, each failing a named case:

| mutation | case |
|---|---|
| the 2023 wrapper entry back in the host's map | `test_every_wrapper_the_map_names_exists`, plus both three-copy cases and the refusal |
| `legacy_search_ui_root` back on `VolatileHost` | `test_none_of_the_retired_paths_are_back` |
| `_search_ui_root_blocking` back on `VolatileHost` | the same |
| `_effect_sequence_*` and `MOUSE_BUTTON_VK_CODES` back | the same, three times |
| the request thread made to block on the search | `test_the_search_is_answered_without_waiting_for_it` |
| the refusal replaced by an unconditional wrapper | `test_an_unknown_interface_stops_the_launch_and_names_it` and both cases beside it |
| `compile_bot.sh` given an arm the host does not have | `test_compile_bot_sh_offers_the_same_interfaces_as_the_host` |
| the CI job given an arm the host does not have | `test_the_ci_job_offers_the_same_interfaces_as_the_host`, `test_no_copy_still_names_a_wrapper_the_host_has_dropped` |

One case in that file was **racy on the first pass and the fix is the point**:
"the search is answered off the request thread" was written as a call counter on
`_find_ui_root`, which the worker thread is free to have called by the time the
assertion runs -- and which would also have passed for a blocking answer. It
holds the search open and requires an `InProgress` stage anyway, which is the
property rather than a proxy for it.

`test_legacy_search_ui_root.test_default_still_answers_the_staged_shape` is
relocated there rather than deleted: it asserted the **2024** path, beside the
flag it was named for.

## Tests that were narrowed rather than deleted

Three files lost a case whose *subject* was wingus; in each the finding was
kept, because the finding was never about that app.

- **`TheFourAppsCarryTheSameWorkingTrigger`** is the one `CLAUDE.md` cites by
  name. It compares `shipWarpingFromReading` and `warpJustEnded` byte for byte
  across apps and refuses #194's dead `== Just False` shape in any of them.
  Deleting `test_wingus_warp_end_trigger.py` without relocating it would have
  lost a load-bearing case, so it moved to
  `test_mission_runner_warp_end_trigger.TheThreeAppsCarryTheSameWorkingTrigger`,
  merged with that file's own byte-identical check, which asserted exactly its
  first half. **It has now been relocated twice for the same reason**: it
  replaced PR #233's `TheMissionRunnerIsUntouched`, which asserted the mission
  runner *still had* the defect and so collided with the change that fixed it,
  and it has now shed a count in its own name. The population moves; the rule
  does not.
- **`test_click_matcher_reads_its_own_click.py`** had two dialect groups and the
  older one is now empty. `test_the_2023_interface_apps_have_no_button_down_to_
  match` would have passed by seeing nothing, so it went -- but the general rule
  it was an instance of,
  `test_the_arm_matches_the_encoding_the_app_actually_emits`, derives what arm an
  app needs from that app's own `effectsMouseClickAtLocation` and therefore
  answers for an app that arrives after the file was written. `DIALECTS` is kept
  as a list of groups rather than collapsed to one.
- **`test_info_panel_repair_deadlock.py` and
  `test_info_panel_icon_click_settling.py`** each folded over a
  `StepDecisionContext` shape carrying one step of history rather than several.
  Wingus was that shape's only app. The folds went; the finding is written into
  each file's doc comment, because it is what says the bound is a property of
  the rule rather than of how deep a context's history happens to be -- a future
  app on a one-step context needs a narrower expectation and no second design.
- **`test_documented_settings_are_parsed.py`** is #161's file and wingus was the
  app the rule was written *for*. The two classes that asked that app about
  itself went with it; the cross-app rule -- every key any app's header offers
  must appear in that app's `parseBotSettings` -- iterates `eve_apps()` and is
  untouched. What is genuinely lost is the execution: that file is now a source
  read in full, because no other app has ever carried the defect for a repl to
  demonstrate. Its doc comment says so rather than implying the coverage is
  unchanged.

## Two count-shaped names corrected while passing

Neither is caused by this change and both would have become false because of it,
which is the reason to touch them rather than leave them:

- `test_route_marker_num_jumps.TheSixCopiesTest` -> `TheVendoredCopiesTest`, and
  its two `..._across_all_six_copies` methods.
- `test_abort_undock_button_parse.test_the_six_copies_agree` -> `..._copies_
  agree`, with the number in its failure message now computed from
  `PARSER_COPIES` rather than written down.

`SIX_VENDORED_FRAMEWORKS` in `test_info_panel_icon_click_settling.py` is
**deliberately left named as it is** and annotated instead: it already held five
entries before this change (the mining bot is excluded on its own grounds), so
the name was a fossil rather than a claim this change falsified, and renaming it
reaches two other files for no assertion's benefit.

## Unverified

- **Nothing has been flown.** No EVE client and no `~/eve-bot-logs` corpus
  exists on the machine this was done on, so every corpus-reading case skipped
  with its declared reason and no claim here rests on a run.
- **The wingman flight record is `WINGMAN.md`'s**, not re-derived. No wingman log
  is on this Mac.
- **A 2023-interface bot was never run against this host at all**, which is why
  the input translation could be removed with no behavioural evidence to weigh:
  `CLAUDE.md` recorded it as "unit-checked, but no 2023-interface bot has yet
  been run against the live client" for its whole life. Its unit tests went with
  it. If such a bot is ever wanted again, this file and the git history are
  where the design is, and reinstating it is a wrapper, a map entry and one
  translation function.
- **What the first mission-runner or saxrat run after this shows** is expected
  to be nothing at all: the host prints
  `# host interface BotLab.BotInterface_To_Host_2024_10_19 -> Main.elm` as it
  always did. A launch that instead prints `no Main.elm wrapper for host
  interface ...` is a bot on an interface this host does not carry, which is the
  fail-loud path being taken correctly rather than a regression.
