{- EVE Online combat anomaly bot version 2023-02-22

      This bot uses the probe scanner to find combat anomalies and kills rats using drones and weapon modules.

      ## Features

      + Automatically detects if another pilot is in an anomaly on arrival and switches to another anomaly if necessary.
      + Filtering for specific anomalies using bot settings.
      + Avoiding dangerous or too-powerful rats using bot settings.
      + Remembers observed properties of anomalies, like other pilots or dangerous rats, to inform the selection of anomalies in the future.

      ## Setting up the Game Client

      Despite being quite robust, this bot is less intelligent than a human. For example, its perception is more limited than ours, so we need to set up the game to ensure that the bot can see everything it needs. Following is the list of setup instructions for the EVE Online client:

      + Set the UI language to English.
      + Undock, open probe scanner, overview window and drones window.
      + Set the Overview window to sort objects in space by distance with the nearest entry at the top.
      + In the ship UI, arrange the modules:
        + Place the modules to use in combat (to activate on targets) in the top row.
        + Place the propulsion module first in the middle row. The bot drives this
          slot on its own rule -- running while the ship crosses distance, off at a
          gate -- so it has to know which slot it is.
        + Place the modules to keep running (hardeners and the like) in the rest of
          the middle row.
        + Hide passive modules by disabling the check-box `Display Passive Modules`.
      + Configure the keyboard key 'W' to make the ship orbit.

      ## Configuration Settings

      All settings are optional; you only need them in case the defaults don't fit your use-case.

      There is no setting for which modules to keep running: the bot takes that
      from where the modules sit in the ship UI. The middle row after its first
      slot is kept active whenever there is something to fight. The first slot is
      the propulsion module, which runs on a different rule -- on whenever the ship
      is actually covering distance, off once an acceleration gate is in reach or a
      warp is being set up. (An `activate-module-always` setting used to be listed
      here. It
      named modules by their tooltip text, which this bot never reads, so it did
      nothing at all -- removed rather than left as a setting that looks like it
      works.)

      + `anomaly-name` : Choose the name of anomalies to take. You can use this setting multiple times to select multiple names, or separate several with commas on one line. The comma always separates, so a name that itself contains one cannot be written here in either form. **Naming any replaces the shipped defaults** (`sansha rally point` and `angel rally point`) rather than adding to them, so the list is exactly what you write; with no `anomaly-name` at all those two are what the bot hunts. Matched whole and ignoring case, so the name must be written as the probe scanner's own Name column shows it -- except that an entry ending in `*` matches any name starting with the rest of it, so `anomaly-name=Sansha*` takes every Sansha site and `anomaly-name=*` takes every combat anomaly. Note a wildcard cannot tell an easy site from one that will kill this ship: it matches Havens and Sanctums as readily as Burrows.
      + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot leave when a neutral or hostile appears in the 'local' chat. Two steps rather than one: first the same celestial warp `runAwayIfLowHealth` takes -- whatever the overview already shows at AU range, falling back to the surroundings-menu tether/dock cascade only when it offers nothing to warp to -- and then, once the ship is off that grid, the same "leave this system" travel the hunt circuit already uses when there is nothing left to hunt (`jumpToNextSystem`), so the ship keeps moving toward the next hunting ground rather than settling for a different rock in the same system the neutral is still in local of. Docking was the whole answer here until this line, and it was the wrong one for the reason `runAway`'s own doc comment gives for the health guards: a search for a station or structure can fail, can be far away, or can point at a structure that is not friendly, where the celestial is already on screen and the warp is one panel button. If already docked when this fires, the bot simply stays docked. See `hideFromNeutralInLocal`.
      + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. You can use this setting multiple times to select multiple names, or separate several with commas on one line. The comma always separates, so a name that itself contains one cannot be written here in either form.
      + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.
      + `warp-at`: Distance in km to warp to when warping to an anomaly, e.g. `warp-at=30`. Must match one of the game client's own preset "Warp to Within" distances offered in that menu (typically 0, 5, 10, 15, 20, 30, 50, 70, 100) -- an arbitrary value will not match any menu entry and will leave the bot stuck. Defaults to 100.
      + `accept-fleet-invite-from`: Name of a pilot whose fleet invitations this bot should accept, exactly as the client writes it. You can use this setting multiple times to name several pilots. With no such setting the bot accepts no invitation at all and declines every dialog as it always has -- and note the client renders a fleet invitation as an ordinary message box, so before this setting existed the bot actively clicked 'No' on them. Accepting means the fleet commander can warp this ship, so name only pilots you would hand the ship to.
      + `fleet-commander`: Set this to 'yes' to make the bot **send** fleet broadcasts as well as read them. Off by default, and with it off nothing about this bot changes at all. With it on the bot broadcasts four things, each fired from a fact the client has reported rather than from what the bot means to do next: `Broadcast: Jump to` on the route's next stargate, once the Selected Item panel is showing that gate and offering its own Jump button; `Broadcast: At Location` once the client shows a locked target with rats on the overview, so the fleet is told the ship is engaged rather than on its way; `Broadcast: Target` on the rat the client marks as this ship's active target, which is never a fleet-mate because a row whose name is in Local is a pilot and is excluded before anything is clicked; and `Broadcast: Need Backup` once the retreat is actually under way -- the combat log past `run-away-incoming-damage-threshold` and the client reporting the ship in warp -- so it costs the retreat nothing. Every call is sent at most once: the client's own broadcast banner is read back to confirm it, and the bot latches on what it reads there, because that banner never clears and real people are on the other end of it. A call the banner does not read back within 20 readings is given up on, said in the status line, and the reading handed back to flying the ship. The bot does **not** use `Warp Fleet (Point)`, which moves other players' ships rather than telling them where to go.
      + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping range or aligning.
      + `keep-at-range`: Set this to 'yes' to keep range from the target instead of orbiting or aligning.
      + `approach-in-combat`: Set this to 'yes' to approach the target and close right up to it, instead of keeping range or aligning. For a brawler fit -- webs, scramblers, short-range guns -- that has to be on top of the rat, which neither of the two settings above does: orbit holds transversal at a distance and keep-at-range holds a distance on purpose. The three are mutually exclusive and are read in the order they are listed here, so `orbit-in-combat=yes` wins over `keep-at-range=yes`, which wins over this; with none of them set the bot aligns as it always has. The approach is a double click on the overview row and presses no key, so unlike `orbit-in-combat` this needs no keyboard binding set up in the client. It has no distance and takes none: the ship closes all the way and stays there, which is the point of it and is also its cost -- a ship sitting on top of a rat has zero transversal against anything that tracks, so do not set this on a fit that wants to be moving across its target.
      + `targeting-range`: Maximum distance in meters to lock a target from the overview, e.g. `targeting-range=50000`. Beyond this, the bot approaches instead of locking. Defaults to 66000. This is a starting value, not the last word: the bot narrows it during the session from the client's own answers -- the greatest distance at which a lock was accepted and the smallest at which one was provably refused -- and the setting is clamped between the two. Set it to pin the starting point; it still gives way to what the client has actually granted. See `lockRangeThresholdInMeters`.
      + `max-targets`: How many rats to hold locked at once, e.g. `max-targets=6`. Defaults to 4. This is a starting value, not the last word: the client states its own maximum on the game log -- `You are already managing 6 targets, as many as you have skill to.` -- and the target bar proves a floor by holding that many, so the bot raises or lowers this from what the client has actually granted. With no evidence it is exactly the setting. Until the client has stated its maximum the bot asks for one more than it believes in, once per reading it has a row to spare, because that sentence is only written when a lock is attempted beyond the cap. See `maxTargetsCeiling` and `maxTargetsRowsToTake`.
      + `hunt-system`: Name of a solar system to hunt anomalies in, e.g. `hunt-system=Irnin`. Use it several times to give the bot a circuit, or write the circuit as one comma-separated line -- either way the circuit is walked in the order written. When a system has nothing left worth hunting and no route is set, the bot asks the host to set the autopilot destination to the next system on this list and flies there on its own. Without this setting the bot behaves as it always did: it parks and waits for a human to set a route.
      + `home-system`: Name of the solar system to fall back to once every `hunt-system` has been tried, e.g. `home-system=Amarr`. Optional, and only consulted after the circuit is exhausted.
      + `run-away-incoming-damage-threshold`: Hitpoints of incoming damage, summed from the client's own combat log over a rolling 45-second window, past which the bot breaks off and runs. Unlike the two hitpoint settings above this needs no HUD gauge, which is the point of it: the gauge is scraped out of the client's live memory and produces values like 2132822% and a spurious 0%. Defaults to 3500, calibrated against sixteen recorded sessions of one hull -- the worst any session the ship survived absorbed was 3114, and the session it was lost in peaked at 4101. **That is a number about a hull, not about the game**, so re-derive it for a different ship. Set to -1 to disable.
      + `short-range-ammo`, `long-range-ammo`, `ammo-swap-range`: the ammo swap, off unless **all three** are set. The first two name the charges as the weapon's own right-click menu writes them, e.g. `short-range-ammo=Multifrequency M` and `long-range-ammo=Radio M`. The third is the distance in meters at which the bot changes over, e.g. `ammo-swap-range=29000`: inside it the ship wants the short-range charge, outside it the long-range one, with a 3000 m deadband either side so a target sitting on the line does not swap every reading. There is no way to leave the distance out and have the bot work it out -- the mission runner derives one from the weapon's tooltip and this bot does not read tooltips at all, so the number is asked for rather than guessed. Loading takes the guns offline for a few readings, which the bot will not do while the client's combat log reports more incoming damage than an eighth of `run-away-incoming-damage-threshold`. Setting either ammo name to nothing (`short-range-ammo=`) switches the swap off without deleting the line.

      When using more than one setting, start a new line for each setting in the text input field.
      Here is an example of a complete settings string:

      ```
   anomaly-name=blood hideaway
   anomaly-name=blood refuge
   anomaly-name=blood burrow
   anomaly-name=blood raider forsaken hideaway
   anomaly-name=blood raider hidden hideaway
   anomaly-name=blood raider forlorn hideaway
   anomaly-name=sansha hideaway
   anomaly-name=sansha refuge
   anomaly-name=sansha burrow
   anomaly-name=sansha forsaken hideaway
   anomaly-name=sansha hidden hideaway
   anomaly-name=sansha forlorn hideaway
   anomaly-name=drone assembly
   anomaly-name=drone cluster
   hide-when-neutral-in-local = no
   orbit-in-combat=yes
   run-away-shield-hitpoints-threshold-percent=69
   run-away-armor-hitpoints-threshold-percent=80
      ```

      To learn more about the anomaly bot, see <https://to.botlab.org/guide/app/eve-online-combat-anomaly-bot>

-}
{-
   catalog-tags:eve-online,anomaly,ratting
   authors-forum-usernames:viir
-}
{-
   anomaly-name=blood hideaway
   anomaly-name=blood refuge
   anomaly-name=blood burrow
   anomaly-name=blood raider forsaken hideaway
   anomaly-name=blood raider hidden hideaway
   anomaly-name=blood raider forlorn hideaway
   anomaly-name=sansha hideaway
   anomaly-name=sansha refuge
   anomaly-name=sansha burrow
   anomaly-name=sansha forsaken hideaway
   anomaly-name=sansha hidden hideaway
   anomaly-name=sansha forlorn hideaway
   anomaly-name=drone assembly
   anomaly-name=drone cluster
   hide-when-neutral-in-local = no
   orbit-in-combat=yes
   run-away-shield-hitpoints-threshold-percent=69
   run-away-armor-hitpoints-threshold-percent=80

   anomaly-name=angel rally point
   hide-when-neutral-in-local = no
   orbit-in-combat=yes
   run-away-shield-hitpoints-threshold-percent=69
-}


module Bot exposing
    ( State
    , botMain
    )

import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost
import Common.AppSettings as AppSettings
import Common.Basics exposing (listElementAtWrappedIndex, stringContainsIgnoringCase)
import Common.DecisionPath exposing (describeBranch)
import Common.EffectOnWindow as EffectOnWindow exposing (MouseButton(..))
import Dict
import EveOnline.BotFramework
    exposing
        ( ReadingFromGameClient
        , SeeUndockingComplete
        , ShipModulesMemory
        , UIElement
        , UseContextMenuCascadeNode(..)
        , doEffectsClickModuleButton
        , infoPanelRouteFirstMarkerFromReadingFromGameClient
        , localChatWindowFromUserInterface
        , menuCascadeCompleted
        , mouseClickOnUIElement
        , pickEntryFromLastContextMenuInCascade
        , shipUIIndicatesShipIsWarpingOrJumping
        , useMenuEntryWithTextContaining
        , useMenuEntryWithTextContainingFirstOf
        , useMenuEntryWithTextEqual
        )
import EveOnline.BotFrameworkSeparatingMemory
    exposing
        ( DecisionPathNode
        , EndDecisionPathStructure(..)
        , UpdateMemoryContext
        , askForHelpToGetUnstuck
        , branchDependingOnDockedOrInSpace
        , clickModuleButtonButWaitIfClickedInPreviousStep
        , decideActionForCurrentStep
        , discardContextMenuIfTooDistantFromTargetElement
        , ensureInfoPanelLocationInfoIsExpanded
        , useContextMenuCascade
        , useContextMenuCascadeOnListSurroundingsButton
        , useContextMenuCascadeOnOverviewEntry
        , useContextMenuCascadeWithCustomConfig
        , waitForProgressInGame
        )
import EveOnline.MemoryReading
import EveOnline.ParseUserInterface
    exposing
        ( FleetWindow
        , OverviewWindowEntry
        , ShipUI
        , ShipUIModuleButton
        )
import Json.Decode
import Set


defaultBotSettings : BotSettings
defaultBotSettings =
    { hideWhenNeutralInLocal = AppSettings.Yes
    , runAwayShieldHitpointsThresholdPercent = -1
    , runAwayArmorHitpointsThresholdPercent = -1
    , anomalyNames = []
    , avoidRats = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , anomalyWaitTimeSeconds = 600
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No

    -- Off, like its two siblings, so an existing settings string is unchanged
    -- and a bot nobody configures still aligns exactly as it did.
    , approachInCombat = AppSettings.No
    , warpAt = 100
    , targetingRangeMeters = 66000

    -- The two gauges above ship disabled, so before this setting existed the
    -- shipped configuration had no retreat at all. This one is armed by
    -- default because it is the guard that depends on no gauge: it reads the
    -- client's own combat log, which states what hit the ship and for how
    -- much, where `hitpointsPercent` is a float scraped out of a widget the
    -- client is concurrently mutating.
    , runAwayIncomingDamageThreshold = defaultRunAwayIncomingDamageThreshold
    , escalationMinimumSecurity = defaultEscalationMinimumSecurity

    -- No circuit by default, which is what keeps this change free for an
    -- existing settings string: with no `hunt-system` the bot never asks for a
    -- destination and parks exactly as it did before.
    , huntSystemNames = []
    , homeSystemName = Nothing

    -- All three absent, so the swap ships off. `ammoSwapConfigFromSettings` is
    -- the one place that says what "on" needs, and it needs all three.
    , shortRangeAmmoName = Nothing
    , longRangeAmmoName = Nothing
    , ammoSwapRangeMeters = Nothing

    -- Empty, so with no setting the bot accepts nothing and every dialog is
    -- still declined exactly as it was. Absent evidence never accepts: this is
    -- the one place the standing "always decline" rule is departed from, and a
    -- default that accepted anyone would hand the ship's position to whoever
    -- asked first.
    , acceptFleetInviteFrom = []

    -- Empty for the same reason, and the cost of a wrong entry is larger: a
    -- pilot on this list can send this ship anywhere in New Eden.
    , followFleetBroadcastFrom = []

    -- Off, so a bot nobody configures broadcasts nothing and behaves exactly as
    -- it did before this setting existed. Every broadcasting arm is gated on
    -- this one answer through `fleetBroadcastStep`, rather than each arm asking
    -- for itself -- one gate is one thing to get wrong.
    , fleetCommander = AppSettings.No
    }


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    AppSettings.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "hide-when-neutral-in-local"
           , AppSettings.valueTypeYesOrNo
                (\hide settings -> { settings | hideWhenNeutralInLocal = hide })
           )
         , ( "run-away-shield-hitpoints-threshold-percent"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayShieldHitpointsThresholdPercent = threshold })
           )
         , ( "run-away-armor-hitpoints-threshold-percent"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayArmorHitpointsThresholdPercent = threshold })
           )
         , ( "hunt-system"
           , AppSettings.valueTypeString
                (\systemNames settings ->
                    { settings
                        | huntSystemNames =
                            settings.huntSystemNames ++ splitSettingIntoNames systemNames
                    }
                )
           )
         , ( "home-system"
           , AppSettings.valueTypeString
                (\systemName settings -> { settings | homeSystemName = Just (String.trim systemName) })
           )
         , ( "accept-fleet-invite-from"
           , -- Non-empty, and this is the setting where that guard earns the
             -- most. The name is matched against the inviter the dialog names,
             -- so an empty entry would match every invitation there is and turn
             -- "accept from this pilot" into "accept from anyone" -- the
             -- mission runner's `decline-mission` lesson pointed at something
             -- that costs a ship rather than standing.
             valueTypeNonEmptyString
                (\pilotNames settings ->
                    { settings
                        | acceptFleetInviteFrom =
                            settings.acceptFleetInviteFrom ++ splitSettingIntoNames pilotNames
                    }
                )
           )
         , ( "follow-fleet-broadcast-from"
           , -- Same guard and the same reason, one step further: an empty entry
             -- would follow a "Travel to" from anybody in the fleet, and this
             -- setting does not merely join a fleet, it hands over navigation.
             valueTypeNonEmptyString
                (\pilotNames settings ->
                    { settings
                        | followFleetBroadcastFrom =
                            settings.followFleetBroadcastFrom ++ splitSettingIntoNames pilotNames
                    }
                )
           )
         , ( "fleet-commander"
           , -- Yes-or-no rather than a list of pilots, because a broadcast is
             -- addressed to the fleet this ship is already in rather than to a
             -- pilot named here: there is nothing for a name to select. The
             -- two settings above are the ones that decide whose word this ship
             -- takes; this one decides whether it says anything of its own.
             AppSettings.valueTypeYesOrNo
                (\commanding settings -> { settings | fleetCommander = commanding })
           )
         , ( "run-away-incoming-damage-threshold"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayIncomingDamageThreshold = threshold })
           )
         , ( "escalation-minimum-security"
           , AppSettings.valueTypeInteger
                (\tenths settings ->
                    { settings | escalationMinimumSecurity = toFloat tenths / 10 }
                )
           )
         , ( "anomaly-name"
           , AppSettings.valueTypeString
                (\anomalyNames settings ->
                    { settings
                        | anomalyNames =
                            splitSettingIntoNames anomalyNames ++ settings.anomalyNames
                    }
                )
           )
         , ( "avoid-rat"
           , AppSettings.valueTypeString
                (\ratsToAvoid settings ->
                    { settings
                        | avoidRats =
                            splitSettingIntoNames ratsToAvoid ++ settings.avoidRats
                    }
                )
           )
         , ( "anomaly-wait-time"
           , AppSettings.valueTypeInteger
                (\anomalyWaitTimeSeconds settings ->
                    { settings | anomalyWaitTimeSeconds = anomalyWaitTimeSeconds }
                )
           )
         , ( "orbit-in-combat"
           , AppSettings.valueTypeYesOrNo
                (\orbitInCombat settings ->
                    { settings | orbitInCombat = orbitInCombat }
                )
           )
         , ( "keep-at-range"
           , AppSettings.valueTypeYesOrNo
                (\keepAtRange settings ->
                    { settings | keepAtRange = keepAtRange }
                )
           )
         , ( "approach-in-combat"
           , AppSettings.valueTypeYesOrNo
                (\approachInCombat settings ->
                    { settings | approachInCombat = approachInCombat }
                )
           )
         , ( "bot-step-delay"
           , AppSettings.valueTypeInteger
                (\delay settings ->
                    { settings | botStepDelayMilliseconds = delay }
                )
           )
         , ( "warp-at"
           , AppSettings.valueTypeInteger
                (\warpAt settings ->
                    { settings | warpAt = warpAt }
                )
           )
         , ( "targeting-range"
           , AppSettings.valueTypeInteger
                (\targetingRangeMeters settings ->
                    { settings | targetingRangeMeters = targetingRangeMeters }
                )
           )

         -- `valueTypeInteger` is what refuses `max-targets=` with nothing after
         -- it: `String.toInt ""` is `Nothing`, so the parse answers `Err` naming
         -- the value and `BotFramework` ends the session. That is PR #116's rule
         -- -- an empty value is rejected rather than dropped -- reached by
         -- picking the value type that already carries it, since a ceiling
         -- silently defaulting to 4 reads exactly like one an operator set.
         , ( "max-targets"
           , AppSettings.valueTypeInteger
                (\maxTargetCount settings ->
                    { settings | maxTargetCount = maxTargetCount }
                )
           )
         , ( "short-range-ammo"
           , AppSettings.valueTypeString
                (\ammoName settings -> { settings | shortRangeAmmoName = nonEmptySettingValue ammoName })
           )
         , ( "long-range-ammo"
           , AppSettings.valueTypeString
                (\ammoName settings -> { settings | longRangeAmmoName = nonEmptySettingValue ammoName })
           )
         , ( "ammo-swap-range"
           , AppSettings.valueTypeInteger
                (\rangeMeters settings -> { settings | ammoSwapRangeMeters = Just rangeMeters })
           )
         ]
            |> Dict.fromList
        )
        defaultBotSettings


{-| A setting whose absence has to be distinguishable from its being blank.

`short-range-ammo=` with nothing after it is how an operator switches the ammo
swap back off from the web console without deleting the line, and an empty
string would otherwise match every context-menu entry.

-}
nonEmptySettingValue : String -> Maybe String
nonEmptySettingValue value =
    case String.trim value of
        "" ->
            Nothing

        trimmed ->
            Just trimmed


{-| One setting line holding several names, split on commas.

**A comma cannot occur in an EVE character name** -- the client's own naming
rules allow letters, digits, spaces, hyphens and apostrophes and nothing else --
so the separator cannot eat part of a name.

**What repeatability buys is not what this comment used to claim.** It said a
name this splitter would cut "can still be given a line of its own", and that is
false: the split is applied to the value of every line, so `avoid-rat=Foo, Bar`
is two entries whether it shares a line with anything or not, and a name that
really contains a comma cannot be expressed in _either_ form. Executed rather
than reasoned -- `TheCommaIsUnconditionalTest` asks the shipped parser. What
repeatability actually buys is that nothing _forces_ the comma form: one name per
line still parses to exactly what it always did, which is what makes this change
free for every settings string in the repo, `run_saxrat.sh`'s included.

So the naming-rules claim is load-bearing after all, and it does not cover all
five settings equally. `accept-fleet-invite-from` and `follow-fleet-broadcast-from`
name characters and `hunt-system` names a solar system, whose names have the same
property. `anomaly-name` and `avoid-rat` name neither: they are matched against
the probe scanner's own Name column and against an overview row, and both of
those the _client_ writes. Issue #197 is the read of what those two columns are
recorded as containing, and it answers one of them and not the other.

**`avoid-rat`: measured, and no name carries a comma.** Across the 86 recorded
runs the bots quote **231** distinct names off an overview row and the client
writes **225** into the `(combat)` lines the host echoes beside them -- 245
distinct between the two, on 69 runs, and **not one contains a comma**. That is
not a column of plain words, which is what makes the absence a reading rather
than a narrow sample: the same names carry apostrophes (`Kruul's Henchman`), full
stops (`R.S. Officer`), hyphens, brackets and a slash (`Gas/Storage Silo`). The
client's own game logs say it again independently -- 348 distinct actors across
360,788 `(combat)` lines in 40 sessions, no comma.

**`anomaly-name`: now logged, so the next corpus can read it.** Until #197 was
acted on, nothing here ever logged the scanner's Name cell -- the cell was read
once, folded into a `Bool` and dropped, and `We are in anomaly '...'` printed the
ID the scanner gives. So no recorded run carried a site name, and the words the
launcher itself asks for (`Hideaway`, `Refuge`, `Burrow`, `Rally Point`, ...)
occur in all 86 runs exactly **zero** times -- which made the question
unanswerable from recordings rather than merely unanswered.

`describeAnomalyIdentity` now prints the Name and Group beside the ID on every
reading that names a site, so a run flown from here writes the column down. The
86 runs behind this file still cannot answer it, and nothing about the counts
above changes; what changes is that run 49 onwards can.

The only probe-scanner names anybody had written down before were the five read
off a live scanner for #188 and kept in `test_saxrat_anomaly_name_wildcard.py`,
one of them `Dread Assault: Blood Raider Temple` -- a colon, so this column is
not restricted to the letters and spaces the other four suggest. A sixth was
read off the live scanner during run 48, `Sansha Refuge`, carrying no comma.

The cost is unchanged and still stated rather than hidden: an anomaly whose name
carries a comma is unmatchable here, because `splitSettingIntoNames` splits every
setting value on commas. Six names are not a distribution and none of this says
no such name exists -- it says the instrument that would find one is finally
running.

Splitting these three at all is issue #182. The two fleet settings split and
these did not, so a comma-separated value parsed with no complaint into **one**
entry that is not a system, an anomaly or a rat: `hunt-system` then asked the
host to set the destination to the whole string, and `anomaly-name` and
`avoid-rat` matched nothing -- the second of those in the direction that engages
a rat which should have been left alone.

An empty entry is dropped rather than kept, because a trailing comma is how one
gets written by accident and the other names on the line still carry what was
meant. That is the opposite of what `valueTypeNonEmptyString` does to a wholly
empty _value_, and deliberately so: there, nothing is left to read the intent
from.

-}
splitSettingIntoNames : String -> List String
splitSettingIntoNames =
    String.split ","
        >> List.map String.trim
        >> List.filter (String.isEmpty >> not)


{-| A setting that names one thing and is useless -- or dangerous -- empty.

The mission runner's PR #116 is the argument, and it applies here in a sharper
form. An empty value has two established meanings in this codebase and neither
covers a name list: `nonEmptySettingValue` reads it as _unset_, which is how the
ammo swap is switched off from the console, and `splitSettingIntoNames` drops it
because a trailing comma is how one gets written by accident. Where the whole
assigned value is empty there is nothing left to read the intent from, so
dropping it silently picks one meaning without saying so.

**`AppSettings`' own answer to a value it cannot use is an `Err` naming the
setting**, which `valueTypeInteger` already gives. The price is stated rather
than hidden: `BotFramework` answers a settings parse error with
`InternalFinishSession`, and that is also the event the web console's live
settings change sends, so a bad value typed mid-run ends the session. That is
what every other unusable value here already costs, and on
`accept-fleet-invite-from` it is paid on a string one keystroke away from
accepting a fleet invitation from anybody who sends one.

-}
valueTypeNonEmptyString : (String -> BotSettings -> BotSettings) -> AppSettings.SettingValueType BotSettings
valueTypeNonEmptyString integrateSettingValue settingValueAsString =
    case String.trim settingValueAsString of
        "" ->
            Err emptySettingValueRejected

        trimmed ->
            Ok (integrateSettingValue trimmed)


{-| What an operator is told when a name setting is left empty. The framework
prepends the setting's own name, so this carries the reason and the fix.
-}
emptySettingValueRejected : String
emptySettingValueRejected =
    "this setting names one thing and was given nothing. Delete the line to leave it unset, or write the name after the '='."


goodStandingPatterns : List String
goodStandingPatterns =
    [ "good standing", "excellent standing", "is in your" ]


type alias BotSettings =
    { hideWhenNeutralInLocal : AppSettings.YesOrNo
    , runAwayShieldHitpointsThresholdPercent : Int
    , runAwayArmorHitpointsThresholdPercent : Int
    , anomalyNames : List String
    , avoidRats : List String
    , maxTargetCount : Int
    , anomalyWaitTimeSeconds : Int
    , botStepDelayMilliseconds : Int
    , orbitInCombat : AppSettings.YesOrNo
    , keepAtRange : AppSettings.YesOrNo
    , approachInCombat : AppSettings.YesOrNo
    , warpAt : Int
    , targetingRangeMeters : Int
    , runAwayIncomingDamageThreshold : Int
    , escalationMinimumSecurity : Float
    , huntSystemNames : List String
    , homeSystemName : Maybe String
    , shortRangeAmmoName : Maybe String
    , longRangeAmmoName : Maybe String
    , ammoSwapRangeMeters : Maybe Int
    , acceptFleetInviteFrom : List String
    , followFleetBroadcastFrom : List String
    , fleetCommander : AppSettings.YesOrNo
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , shipWarpingInLastReading : Maybe Bool

    -- Whether this `hide-when-neutral-in-local` episode has already gotten the
    -- ship moving -- set the first reading it is seen warping or jumping while
    -- `neutralOrHostileInLocal` answers `Just True`, cleared the moment that
    -- answer stops being `Just True`. What `hideFromNeutralInLocal` reads to
    -- tell "just fled, still landing" from "already moving, keep going toward
    -- the next hunting ground" apart, across however many hops that takes. See
    -- `hideFromNeutralInLocal`.
    , hidingFromNeutralPastFirstHop : Bool

    -- How many readings ago the last warp finished, which is what opens the
    -- arrival window the other-pilot snapshot is taken inside. `Nothing` means
    -- no warp has finished this session and is a closed window, never an open
    -- one. See `otherPilotArrivalWindowReadings`.
    , readingsSinceWarpEnded : Maybe Int

    -- Readings since the session began, used only to rotate which
    -- celestial `runAway` heads for. Monotone by construction: it is
    -- advanced unconditionally beside every other verdict here.
    , readingsCount : Int
    , visitedAnomalies : Dict.Dict String MemoryOfAnomaly
    , contextMenuLastDepth : Int
    , contextMenuStuckTicks : Int
    , lootWindowOpenTicks : Int
    , routeFirstMarkerRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , routeFirstMarkerUnchangedTicks : Int

    -- The route-marker cascade's own right-click on the route panel's first
    -- marker, counted rather than the readings elapsed -- a reading spent
    -- waiting for a menu to render ("give the game one more reading") is not
    -- a sign of being stuck, where a *repeated* right-click at the same
    -- marker (the cascade discarding what it found and reopening) is. Reset
    -- whenever the next system on the route changes (a leg completed, or a
    -- new route was set) or the reading offers no next system at all.
    -- `jumpCascadeStuckReopens` past this count is what `jumpToNextSystem`
    -- reads to fall back to `jumpToNextSystemViaSurroundingsButton` instead
    -- of continuing to retry the marker. See that function's own doc comment
    -- for why: saxrat run 23 spent 27 readings and 7 discard-and-reopen
    -- cycles on the marker cascade alone for one leg, well past the "3-4
    -- menu opens" that cascade's own comment expects.
    , jumpCascadeSystem : Maybe String
    , jumpCascadeReopens : Int
    , targetToUnlockRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , targetToUnlockUnchangedTicks : Int
    , noProbeScanResultsAndNoRouteLastTimeInSpace : Bool
    , shipApproachingTicks : Int
    , lootedWreckIds : List String
    , gateWithinReachTicks : Int

    -- The box `closeMessageBox` is trying to close and how many readings it has
    -- been at it, so a window the dismissal does not close eventually hands the
    -- tree back rather than holding it forever. `messageBoxLastChange` holds a
    -- sentence only on the reading the give-up was reached, which is what makes
    -- one line per give-up need no "already reported" flag. See
    -- `MessageBoxStandoff`.
    , messageBoxStandoff : Maybe MessageBoxStandoff
    , messageBoxLastChange : Maybe String

    -- The client's own transient popup, carried forward with its age because a
    -- reading is seconds apart and the popup is not. Read by no decision, and
    -- deliberately so until a run has recorded what one says. See
    -- `QuickMessageSighting`.
    , quickMessage : Maybe QuickMessageSighting

    -- The HUD gauges as this bot is willing to believe them, rather than as
    -- the last reading happened to report them. See `updateHitpointsGaugeMemory`.
    , hitpoints : HitpointsMemory

    -- The lowest believed value seen since the last recovery or dock. A single
    -- live threshold has no hysteresis, so a retreat decided on one reading is
    -- un-decided by the next one the moment a repairer catches up.
    , hitpointsLowWaterMark : { shield : Int, armor : Int }

    -- What the client's own combat log says has been hitting this ship, over a
    -- rolling window. The one retreat instrument here that reads no sprite.
    , incomingDamage : IncomingDamageMemory

    -- Latched, and never cleared: the cost is asymmetric in one direction
    -- only. Docking early costs the rest of the session; un-concluding a ship
    -- loss on a reading that happens to look normal costs the clone.
    , shipLoss : Maybe ShipLossVerdict
    , shipUIWithoutModuleButtonsReadings : Int

    -- Readings since the bot last *asked* for a drone recall that the client
    -- has not answered -- never readings since the drones were launched, which
    -- is issue #11: drones are deliberately left out for a whole fight.
    , droneRecallUnansweredTicks : Int
    , dronesInSpaceCountLastReading : Int
    , dronesInSpaceTicks : Int

    -- Where the circuit has got to. Advanced when the ship is standing in the
    -- system this points at, which is what makes the rotation move on rather
    -- than ping-ponging between the first two names on the list.
    , huntSystemIndex : Int

    -- The destination last asked for, and how many readings have passed since
    -- with no route to show for it. The ask is one line of status text and the
    -- host acts on it only when it changes, so repeating it costs nothing --
    -- but it has to be bounded, or a name that never resolves is a bot that
    -- asks forever and never hunts again.
    , destinationAskedFor : Maybe String

    -- The fleet travel broadcast this session has already routed to, as the
    -- banner's own text. The client's banner does not go away, so without this
    -- the ask would repeat on every reading for the rest of the session. See
    -- `fleetBroadcastToFollow`.
    , fleetBroadcastFollowed : Maybe String

    -- The banner as the *previous* reading saw it. `decideNextStep` is handed
    -- the memory this update produces, so latching `fleetBroadcastFollowed` on
    -- the reading the banner first appears would stop the branch ever firing --
    -- `loadCascadeReachedTheMenu`'s trap, in a place with no dispatched effect
    -- to read it out of. Latching on the second sighting instead makes the ask
    -- go out exactly once.
    , fleetBroadcastSeen : Maybe String

    -- The "needs backup" call this session has already warped to, identified
    -- by its own text. Latched on a real, directly-observable fact each
    -- reading -- the ship warping while the pilot is in local chat -- rather
    -- than on a "seen N readings" counter, because the underlying action is
    -- a real multi-reading UI cascade (right-click, wait for the menu, click
    -- an entry) and not the idempotent host-directive `fleetBroadcastFollowed`
    -- latches for. A reading-count latch here would (and, live, did) cut the
    -- cascade off before it had a chance to complete: see
    -- `respondToFleetBackupBroadcast`. Never latches for a call whose pilot
    -- is not in this system -- there is no verified way to act on one, so it
    -- is simply left unlatched and re-checked every reading, harmlessly,
    -- unless the ship later arrives in her system on its own.
    --
    -- Latching on "in local chat and warping" alone has a real gap: if the
    -- call is first read on a reading where this ship *already* happens to
    -- be warping for an unrelated reason (between anomalies, retreating --
    -- which happens constantly), it credits that warp as the click's own
    -- success and never dispatches one at all. `fleetBackupInSystemStanding`
    -- is what closes it: a call only latches here once a *previous* reading
    -- saw the pilot in system and this ship standing still, which is the
    -- one state a dispatched click can actually be given credit from.
    , fleetBackupBroadcastFollowed : Maybe String

    -- The identity of a backup call seen with its pilot already in local
    -- chat and this ship *not* warping -- the one state in which a "Warp to
    -- Member" click just dispatched could plausibly be the reason the ship
    -- is warping on the very next reading. See `fleetBackupBroadcastFollowed`.
    , fleetBackupInSystemStanding : Maybe String

    -- The "at location" call this session has already warped to *in person*.
    -- Deliberately separate from the not-in-system ask below: arriving in
    -- her system by whatever route does not mean this ship has actually
    -- reached her, so the in-system branch must still get its own turn even
    -- after a route has already been asked for and travelled. Shaped exactly
    -- like `fleetBackupBroadcastFollowed` -- a real cascade needs a real
    -- click credited, not a reading count. See
    -- `respondToFleetAtLocationBroadcast`.
    , fleetAtLocationBroadcastFollowed : Maybe String

    -- Same role as `fleetBackupInSystemStanding`, for an at-location call's
    -- own in-system warp.
    , fleetAtLocationInSystemStanding : Maybe String

    -- The identity of an at-location call this ship has already asked the
    -- host to route toward, latched like `fleetBroadcastFollowed` -- an
    -- idempotent directive is safe to latch on the second sighting, since it
    -- is not a multi-step click that can be cut off mid-cascade. Once
    -- latched this ship hands the reading back to ordinary travel for the
    -- rest of the trip, the same restraint `followFleetBroadcast` states for
    -- itself, and it does **not** stop the in-system branch above from later
    -- firing once she is actually reached.
    , fleetAtLocationDestinationAsked : Maybe String

    -- Seen at all, regardless of the pilot's location -- the lag signal for
    -- `fleetAtLocationDestinationAsked` above, same shape as
    -- `fleetBroadcastSeen`.
    , fleetAtLocationBroadcastSeen : Maybe String

    -- The other direction of the same window: what this ship has broadcast to
    -- the fleet, rather than what the fleet broadcast to it. Written on every
    -- reading whatever the bot is doing, and read by the arms that send. See
    -- `FleetBroadcastMemory`.
    , fleetBroadcast : FleetBroadcastMemory
    , destinationAskReadings : Int
    , routeSettingGivenUp : Bool

    -- Readings in a row the hunt circuit has stood down on for an escalation the
    -- Opportunities tracker is working (#279). Advanced on exactly the readings
    -- `setRouteToNextHuntingGround` holds the grid on, through the same
    -- `standingDownForATrackedEscalation` the decision asks, so the counter and
    -- the bound it feeds cannot come to be about different things.
    , escalationStandDownReadings : Int

    -- What the client has answered about how far this ship can lock, and the
    -- lock still waiting for an answer. Both bounds move one way only, so no
    -- oscillation is possible; `lockRangeLastChange` holds a sentence only on
    -- the reading a bound moved, which is what makes one line per change need
    -- no "already reported" flag. See `lockRangeThresholdInMeters`.
    , lockAttempt : Maybe LockAttempt
    , lockRangeStatedMeters : Maybe Int
    , lockProvenAtMeters : Maybe Int
    , lockRefusedAtMeters : Maybe Int
    , lockRangeLastChange : Maybe String

    -- The batch of lock clicks the last batched step asked for, and what the
    -- target bar has done about it since. The totals are for the session and
    -- only ever rise; `lockBatchLastChange` holds a sentence only on the
    -- reading a batch was judged short, `lockRangeLastChange`'s mechanism for
    -- its reason. See `updateLockBatchAccounting`.
    , lockBatch : Maybe LockBatchDispatch
    , lockBatchClicksAsked : Int
    , lockBatchClicksAnswered : Int
    , lockBatchLastChange : Maybe String

    -- The size of the target bar on the previous reading, which is the reading
    -- a step's effects were decided on. Written down rather than re-derived
    -- because the batch accounting has to compare the bar against what it was
    -- *before* the clicks it is judging, and the memory update only ever sees
    -- the reading after them.
    , targetsCountLastReading : Int

    -- How long the guns have been busy with nothing dying, in readings. See
    -- `CombatStalemate`.
    , combatStalemate : CombatStalemate

    -- What this ship's own guns achieved, off the half of the combat channel
    -- this bot has never read. An instrument: nothing decides on it. See
    -- `OutgoingFireMemory` and `outgoingFireAfterReading`.
    , outgoingFire : OutgoingFireMemory

    -- How many rats the client has paid a bounty for this session, off the
    -- `(bounty)` channel the host sums. An instrument: nothing decides on it.
    -- See `KillCountMemory` and `killCountAfterReading` for what the number may
    -- and may not be read as.
    , kills : KillCountMemory

    -- What the client has answered about how many targets this ship can hold at
    -- once: the maximum it stated in its own game log, and the most the target
    -- bar has actually carried. `maxTargetsLastChange` holds a sentence only on
    -- the reading the ceiling moved, `lockRangeLastChange`'s mechanism for its
    -- reason. See `maxTargetsCeiling`.
    , maxTargetsStatedByClient : Maybe Int
    , maxTargetsHeldAtOnce : Maybe Int
    , maxTargetsLastChange : Maybe String

    -- How many drones the client has said this ship is already controlling,
    -- read off the quick message on the reading it refused a launch.
    -- `droneLaunchLastChange` holds a sentence only on the reading that number
    -- moved, `maxTargetsLastChange`'s mechanism for its reason. See
    -- `droneLaunchCeiling`.
    , droneLaunchRefusedAbove : Maybe Int
    , droneLaunchLastChange : Maybe String

    -- Everything the ammo swap knows, in one field so the rest of this record
    -- is untouched by a feature that is off unless three settings are set.
    -- See `AmmoSwapMemory`.
    , ammoSwap : AmmoSwapMemory
    }


{-| A lock the bot has asked for and the client has not yet answered.

`handle` is `overviewEntryLockHandle`'s answer for the row the click went to,
and an attempt exists only where that answered -- a row this bot cannot tell
apart from another one teaches nothing, which in an anomaly full of identically
named rats is the ordinary case rather than the exception.

`distanceInMeters` is what the row showed on the reading the attempt started
and `targetsCount` the number of locked targets then. Both are needed at the
verdict and both can have changed by the time it is reached, which is why they
are written down rather than re-read.

-}
type alias LockAttempt =
    { handle : String
    , distanceInMeters : Int
    , targetsCount : Int
    , readingsWaited : Int
    }


{-| A step's worth of lock clicks, waiting to be counted.

`clicksAsked` is counted out of the **effects that were actually dispatched**
rather than out of the rows the decision picked, so the two cannot come to
disagree: a row whose click point could not be computed contributes no chord and
is therefore never asked for. `targetsCountBefore` is the bar on the reading the
step was decided from, which is the only number the answer can be measured
against -- the bar on the reading that _observes_ the click may already carry
some of the batch.

-}
type alias LockBatchDispatch =
    { clicksAsked : Int
    , targetsCountBefore : Int
    , readingsWaited : Int
    }


{-| The last transient centre-screen popup the client showed, and how stale it is.

`ParsedUserInterface.layerAbovemain.quickMessage` has been parsed on every
reading since this app was added and read by nothing -- #123. So every message
this client has ever shown the bot was decoded into a string and discarded, and
**the wording of one has never been recorded**. The operator reports a black
popup on trying to lock past the ship's capacity, which is the signal #110 is
blocked on; that search looked in the game log, where the channels are `combat`,
`notify`, `bounty`, `question`, `info` and `hint`, and a quick message is a UI
widget rather than a log line, so it was never going to be found there.

Nothing decides anything on this, deliberately. A matcher written now would rest
on guessed strings, which is #92's trap exactly -- a rule keyed on a word list
the client's vocabulary outgrew twice with nobody noticing. The corpus comes
first; the matcher comes after there is one.

**Carried forward rather than reported live, with the age beside it.** The
message is transient and a reading is seconds apart, so a live-only clause would
put each one on a single line of a log holding thousands of near-identical ones.
Two things need it to persist. The first Unverified item in #123 is whether
`quickMessage` is even the widget the operator is seeing, and the only person who
can answer that is the operator watching the console -- who cannot confirm a
string that flashes for one reading and is gone. The second is correlating a
popup with the decision that followed it, which is the whole point for a lock
refusal: the popup lands on the reading of the click and the failure is
diagnosed several readings later.

The failure this risks -- a stale message read as current -- is answered by
`describeQuickMessage` naming which it is: `on screen now` against `NOT on screen
now -- last seen N readings ago`. The failure live-only risks is the message
being missed, which is not recoverable and is the one #123 exists to end.

`messagesInLayer` and `displayTextsInMessage` answer #123's last Unverified item
with evidence rather than reasoning. `parseQuickMessage` filters the layer's
descendants for `QuickMessage` and takes `List.head`, then takes the head of the
chosen node's display texts, so **both** are places a second message or a second
line of one message is dropped without a word. Counting them costs one walk of a
layer that is almost always absent, and a run that meets a `2` settles the
question the parser's `Maybe` cannot.

-}
type alias QuickMessageSighting =
    { text : String
    , messagesInLayer : Int
    , displayTextsInMessage : Int
    , readingsSince : Int
    }


type alias MemoryOfAnomaly =
    { arrivalTime : { milliseconds : Int }
    , otherPilotsFoundOnArrival : List String
    , ratsSeen : Set.Set String
    }


{-| How long the guns have been busy with nothing dying, in readings.

**Run 48 is what this exists to end.** The bot sat in anomaly `OTC-000` printing
`All locked up; bounce?` on 1,563 consecutive readings and answering "wait" to
every one of them -- the anomaly's own age clause reached **4,759 seconds**, and
the run was still being written when the incident was reported at 3,883. Three
rats the whole time, none of them dying, a `Centii Loyal Enslaver`
out-regenerating the guns from a hull the bot had already taken down to 12%, no
drones left to launch, and the ship in no danger at all. Nothing below that
branch could act, so nothing did.

**`ratsInOverview` is the whole progress signal, and the hitpoint ring is
deliberately not part of it.** The obvious reading of run 48 -- a shield climbing
while the guns fire -- does not survive the log. Over the longest stretch of that
stall with a readable ring, 821 consecutive readings, the target's triple rises
on 154 of them, holds on 642 and **falls on 24**: the damage was landing and the
repairs were faster. What that costs a rule keyed on the ring is the run length
rather than the share -- the longest stretch inside that stall with no fall in it
is **113 readings**, so a counter reset by the triple never reaches the bound
below and the incident repeats. The one thing that stayed true for all 1,563
readings is that the overview still showed three rats.

Measured across the twenty-two recorded saxrat logs whose status line carries a
reading index, the longest a fight went between kills and still produced one is
**130 readings**; the three recorded stalls ran **932, 1443 and 1582**. The
bounds below sit in that gap, which is a sevenfold separation against the ring's
1.8x.

**Nothing here is keyed on a rat's name.** An anomaly is a pocket of identically
named rats, so a verdict latched by name would blacklist every `Centii Loyal
Enslaver` for the session -- which is why the mission runner's zero-damage rule
was not ported here. This is a count of rows and a count of readings, and it is
cleared by the fight moving rather than by anything being remembered.

`ratsInOverview` is the previous reading's count, written down for the same
reason `targetsCountLastReading` is: the comparison is against the reading
_before_ this one, and the memory update only ever sees the reading after.

-}
type alias CombatStalemate =
    { readings : Int
    , ratsInOverview : Int
    }


type alias HitpointsMemory =
    { shield : HitpointsGaugeMemory
    , armor : HitpointsGaugeMemory
    }


type alias HitpointsGaugeMemory =
    { previousReading : Maybe Int
    , believed : Maybe Int
    , readingsWithheld : Int
    , lastWithheld : Maybe Int
    }


type alias IncomingDamageMemory =
    { samples : List IncomingDamageSample
    , hostCarriesTheChannel : Bool
    , lastAttacker : Maybe String
    , retreating : Bool
    }


type alias IncomingDamageSample =
    { atMilliseconds : Int
    , damage : Int

    -- The HUD reading this sample's own reading was allowed to believe, or
    -- `Nothing` where there was none: no ship UI, a value
    -- `plausibleHitpointsPercent` rejected, or one no second reading has
    -- confirmed yet. A `Nothing` is never counted as the gauge moving, so a
    -- corrupt reading cannot pass for a gauge that is still working.
    , hitpoints : Maybe ( Int, Int )

    -- Who the client said hit hardest on this reading, kept per sample rather
    -- than only in `lastAttacker`, because the *window* of these names is what
    -- the target selection reads. `topAttacker` is one name and a pocket has
    -- several, so the set is accumulated across readings rather than widened
    -- host-side into a list.
    , attacker : Maybe String
    }


{-| What this ship's own shots did, as the client counted them.

**The other half of the channel, which this bot has never read.** The host has
summed `outgoingDamageSinceLastReading` per target per reading since #90, and
PR #271 put `misses` beside `hits` on it in all six vendored parser copies --
and `outgoingDamage` appeared **zero times** in this file before this change.
So every shot this bot has ever fired was counted, decoded and thrown away, on
every reading of every recorded run. `incomingDamage` is the same channel read
in the other direction and is the shape this follows.

**Nothing decides anything on it**, and that is the whole of the change rather
than a stage it is passing through. See `outgoingFireAfterReading` for what the
corpus says about the rule somebody would want to write here, which is that
there is no threshold to write it at.

`hostCarriesTheChannel` keeps the distinction the parser's `Maybe` carries:
`Nothing` is "this host has no game log" and `Just []` is "the client reported
no shot landing this reading". Both produce `hits = 0, misses = 0` and only the
first may ever be read as not knowing.

`hits` and `misses` are kept apart here for the reason the parser's own doc
comment gives: a landed shot for zero says the guns cannot hurt this object, a
miss says they cannot hit it, and summing them is the one mistake to avoid.
This record never adds them; `describeOutgoingFire` prints both.

-}
type alias OutgoingFireMemory =
    { hostCarriesTheChannel : Bool
    , hits : Int
    , misses : Int
    , readingsEveryShotMissed : Int
    , longestRunEveryShotMissed : Int
    , sessionHits : Int
    , sessionMisses : Int
    }


type alias ShipLossVerdict =
    { reason : String
    , readingsSince : Int
    }


{-| The message box the bot has been trying to close, and how many readings it
has been at it.

**Issue #138, which is the mission runner's #101 in this file.** `closeMessageBox`
here had no counter, no bound and no give-up: it clicked its dismissal on the
first reading and would have clicked it identically on the thirty-thousandth.
The mission runner's run 30 is what that costs. Something the client draws on
the `MessageBox` widget -- an emoji picker, by every sign -- carried a
`no_dialog_button`, so `Dismiss it using No.` was the right-looking answer and
the box was still there afterwards: **32,585 readings, three hours and
forty-four minutes**, with everything below `generalSetupInUserInterface`
unreachable for all of them. This bot's copy of that list is evaluated in the
same place and `parseMessageBoxesFromUITreeRoot` here matches the same widget on
`pythonObjectTypeName` alone, so the same window produces the same standoff --
and this bot rats unattended, with nobody at the console to notice.

**`identity` is what makes the count mean something.** A global tally of
dismissals accumulates across a session that legitimately closes many dialogs
and reaches a give-up it should never reach; the mission runner's recovered runs
answer 175 separate stretches of message box between them. Counted per box,
those stretches are 6 to 44 readings long and nothing else, against run 30's
32,585 on one box. So the count is keyed on the thing it bounds, the way
`lootedWreckIds` is keyed on the wreck rather than counting wrecks.

**What the identity is made of, and what it deliberately leaves out.** The box's
own display texts and its buttons, and _not_ its display region.
`targetToUnlockUnchangedTicks` and `routeFirstMarkerUnchangedTicks` are both
region comparisons and both record what that costs: a widget re-rendered every
tick can differ sub-pixel while looking identical, and an exact-equality test
over its region then never accumulates at all -- which is precisely the failure
this bound exists to prevent. What a dialog says and what buttons it offers are
read out of the tree as strings and do not drift that way. The side effect is
that a dialog whose wording changes starts a fresh count, which is the wanted
direction: a box saying something new is one the next answer has not been tried
on.

**`readings` counts readings the framework completed, and run 11 is why that is
worth writing down.** It is advanced in `updateMemoryForNewReadingFromGame`,
which runs once per `ReadingFromGameClientCompleted` and not once per log line
or per framework step. In saxrat run 11 the count reached 60, the client stopped
answering `ReadFromWindow` on that same reading -- its own quick message read
`Cluster Shutdown in Less than one second` -- and the framework then issued 608
further pairs of read tasks and completed none of them. Every counter written
here froze together at that instant, this one and the ammo swap's and the damage
window's alike, while the host went on reprinting the last status text 2,439
times. A count that has stopped moving is therefore evidence about the reading
pipeline and not about this branch, and the log cannot tell the two apart by
repetition alone.

-}
type alias MessageBoxStandoff =
    { identity : String
    , readings : Int
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory


{-| The two things "would this bot hunt that anomaly" depends on.

Named rather than taken as a `BotDecisionContext` because
`updateMemoryForNewReadingFromGame` has to ask the same question and never sees
a decision -- the same split `nextHuntingGroundFrom` was made for, and for the
same reason: the counter that bounds the route ask has to measure the state the
ask fires on, and it cannot do that through a rule only the decision can call.

**Both callers hand it the same two things**, which is what keeps them from
drifting apart the way #263's two pickers could. `visitedAnomalies` is the
freshly written value in the memory update rather than `botMemoryBefore`'s, so
the decision -- which the framework hands the memory this update has already
written -- is asking about the same set.

-}
type alias AnomalyChoiceContext =
    { botSettings : BotSettings
    , visitedAnomalies : Dict.Dict String MemoryOfAnomaly
    }


type ReasonToIgnoreProbeScanResult
    = ScanResultHasNoID
    | AvoidAnomaly ReasonToAvoidAnomaly


type ReasonToAvoidAnomaly
    = IsNoCombatAnomaly
    | IsNoDistantAnomaly
    | DoesNotMatchAnomalyNameFromSettings
    | FoundOtherPilotOnArrival String
    | FoundRatToAvoid String


describeReasonToAvoidAnomaly : ReasonToAvoidAnomaly -> String
describeReasonToAvoidAnomaly reason =
    case reason of
        IsNoCombatAnomaly ->
            "Is not a combat anomaly"

        IsNoDistantAnomaly ->
            "Is the current anomaly?"

        DoesNotMatchAnomalyNameFromSettings ->
            "Does not match an anomaly name from the settings"

        FoundOtherPilotOnArrival otherPilot ->
            "Found another pilot on arrival: " ++ otherPilot

        FoundRatToAvoid rat ->
            "Found a rat to avoid: " ++ rat



-- getFleetMembers: BotDecisionContext -> EveOnline.ParseUserInterface.FleetWindow -> Maybe FleetWindow
-- getFleetMembers context fleetWindow =
--     case fleetWindow.fleetMembers


{-| The scan results this bot would go and hunt, out of everything on the scanner.

One filter, read by the decision that picks an anomaly and by the memory update
that bounds the ask for a route out of a system with none. Before #273 the
memory update asked a _different_ question -- "is the probe scanner empty" --
and with a narrow `anomaly-name` beside two signatures that do not match it, the
two answers disagree on every reading: the decision asks for a route and the
counter meant to bound that asking resets to zero. 442 readings of zero against
3 of one, in one run.

An absent scanner window answers `[]` rather than `Nothing`, deliberately: the
decision's own no-scanner arm falls through to leaving the system, so a reading
with no window is a reading the ask can fire on.

-}
anomaliesWorthHunting :
    AnomalyChoiceContext
    -> ReadingFromGameClient
    -> List EveOnline.ParseUserInterface.ProbeScanResult
anomaliesWorthHunting anomalyChoice readingFromGameClient =
    readingFromGameClient.probeScannerWindow
        |> Maybe.map .scanResults
        |> Maybe.withDefault []
        |> List.filter (findReasonToIgnoreProbeScanResult anomalyChoice >> (==) Nothing)


anomalyChoiceFromDecisionContext : BotDecisionContext -> AnomalyChoiceContext
anomalyChoiceFromDecisionContext context =
    { botSettings = context.eventContext.botSettings
    , visitedAnomalies = context.memory.visitedAnomalies
    }


{-| The framework's warp-or-jump indication, over a whole reading.

`decideNextActionWhenInSpace` answers `HOOOOONK in warp` before it can reach the
route ask, so the counter that bounds that ask has to decline the same readings.
A ship crossing a system takes longer than `routeAskGiveUpReadings` at this
bot's step delay, so counting through a warp would latch the give-up on a bot
that was travelling perfectly well.

-}
shipIsWarpingOrJumping : ReadingFromGameClient -> Bool
shipIsWarpingOrJumping readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map shipUIIndicatesShipIsWarpingOrJumping
        |> Maybe.withDefault False


{-| Something on this grid to shoot, loot or unlock right now.

The anomaly's own signature drops off the probe scanner while rats are still
alive and wrecks are still on the overview, so `decideNextActionWhenInSpace`
asks this before it will consider leaving. The counter that bounds the route ask
asks it too, and that shared use is the whole reason it is a declaration: it is
the guard the ask's own condition does _not_ imply, so a counter keyed on "no
anomaly worth hunting" alone would run up through exactly the good fight #273's
predecessor comment feared -- and two copies of it would be the drift that issue
is about.

-}
gridStillHasSomethingToDo : IncomingDamageMemory -> ReadingFromGameClient -> Bool
gridStillHasSomethingToDo incomingDamage readingFromGameClient =
    anyAttackableInOverview (namesOfRecentAttackers incomingDamage) readingFromGameClient
        || anyNotableWreckInOverview readingFromGameClient
        || (targetsToUnlockIncludingActiveIfStray readingFromGameClient |> List.isEmpty |> not)


findReasonToIgnoreProbeScanResult : AnomalyChoiceContext -> EveOnline.ParseUserInterface.ProbeScanResult -> Maybe ReasonToIgnoreProbeScanResult
findReasonToIgnoreProbeScanResult context probeScanResult =
    case probeScanResult.cellsTexts |> Dict.get "ID" of
        Nothing ->
            Just ScanResultHasNoID

        Just scanResultID ->
            let
                isCombatAnomaly2025 =
                    probeScanResult.cellsTexts
                        |> Dict.get "Group"
                        |> Maybe.map (stringContainsIgnoringCase "combat")
                        |> Maybe.withDefault False

                isCombatAnomaly2026 =
                    {-
                       EVE Online game client update, ~2026-05: the probe
                       scanner's combat-anomaly indicator moved from the
                       "Group" column to a "Signal" column for some
                       anomaly types. See commit 2998f4a in this repo
                       (eve-online-combat-anomaly-bot) for the same fix.
                    -}
                    probeScanResult.cellsTexts
                        |> Dict.get "Signal"
                        |> Maybe.map (stringContainsIgnoringCase "combat")
                        |> Maybe.withDefault False

                isCombatAnomaly =
                    isCombatAnomaly2025 || isCombatAnomaly2026

                isDistantAnomaly =
                    probeScanResult.cellsTexts
                        |> Dict.get "Distance"
                        |> Maybe.map (\text -> text |> String.contains " AU")
                        |> Maybe.withDefault False

                matchesAnomalyNameFromSettings =
                    probeScanResult.cellsTexts
                        |> Dict.get "Name"
                        |> Maybe.map
                            (\name ->
                                anomalyNamesInEffect context.botSettings
                                    |> List.any (anomalyNameMatches name)
                            )
                        |> Maybe.withDefault False
            in
            if not isCombatAnomaly then
                Just (AvoidAnomaly IsNoCombatAnomaly)

            else if not isDistantAnomaly then
                Just (AvoidAnomaly IsNoDistantAnomaly)

            else if not matchesAnomalyNameFromSettings then
                Just (AvoidAnomaly DoesNotMatchAnomalyNameFromSettings)

            else
                findReasonToAvoidAnomalyFromMemory context { anomalyID = scanResultID }
                    |> Maybe.map AvoidAnomaly


findReasonToAvoidAnomalyFromMemory : AnomalyChoiceContext -> { anomalyID : String } -> Maybe ReasonToAvoidAnomaly
findReasonToAvoidAnomalyFromMemory context { anomalyID } =
    case Dict.get anomalyID context.visitedAnomalies of
        Nothing ->
            Nothing

        Just memoryOfAnomaly ->
            case memoryOfAnomaly.otherPilotsFoundOnArrival of
                otherPilotFoundOnArrival :: _ ->
                    Just (FoundOtherPilotOnArrival otherPilotFoundOnArrival)

                [] ->
                    let
                        ratsToAvoidSeen =
                            getRatsToAvoidSeenInAnomaly context.botSettings memoryOfAnomaly
                    in
                    case ratsToAvoidSeen |> Set.toList of
                        ratToAvoid :: _ ->
                            Just (FoundRatToAvoid ratToAvoid)

                        [] ->
                            Nothing


getRatsToAvoidSeenInAnomaly : BotSettings -> MemoryOfAnomaly -> Set.Set String
getRatsToAvoidSeenInAnomaly settings =
    .ratsSeen >> Set.filter (shouldAvoidRatAccordingToSettings settings)


{-| What the bot hunts when the operator has named nothing.

These are a **fallback**, not a floor. Before #198 they were the initial value of
`BotSettings.anomalyNames` and the `anomaly-name` handler prepended to them, so an
operator naming six hideaways got those six _and_ these two -- and a rally point is
a considerably harder site than a hideaway, which is not what "choose the name of
anomalies to take" reads like. Naming one now replaces them.

-}
shippedAnomalyNames : List String
shippedAnomalyNames =
    [ "sansha rally point", "angel rally point" ]


{-| The list the scan-result filter actually consults.

Empty means the operator named none, which is the only way the list can be empty
-- the handler prepends and nothing removes. **"Take anything" is still
expressible** and is now the operator's to write rather than a shortcut here:
`anomaly-name=*` is a prefix match on the empty string, which every name starts
with. The `List.isEmpty` shortcut this replaces meant the same thing and could
never fire, because the defaults it was defending against were never empty.

-}
anomalyNamesInEffect : BotSettings -> List String
anomalyNamesInEffect settings =
    if settings.anomalyNames |> List.isEmpty then
        shippedAnomalyNames

    else
        settings.anomalyNames


{-| Whether one `anomaly-name` entry matches the name the scanner shows.

**Exact by default, prefix only where the operator asked for it.** An entry
ending in `*` matches any name that starts with the rest of it, so
`anomaly-name=Sansha*` takes every Sansha site; every other entry is compared
whole, exactly as before. Opt-in rather than a switch to substring matching
everywhere, because widening a filter silently is how a bot ends up in a site
that kills it, and `attack-object` already records what an accidental substring
costs -- a wreck's Type is its owner's name with " Wreck" appended, so a
substring rule had the bot firing on the corpse of what it had just killed.

Only a _trailing_ `*`, not a general glob. Site names read
`Sansha <adjective> <noun>`, so the prefix is the case the client's own naming
produces; anything more would be surface with no evidence behind it.

**What `Sansha*` costs is worth knowing before setting it.** It matches the
whole family, including the Havens and Sanctums that will kill a destroyer as
readily as a Burrow will not. The filter cannot tell them apart, and neither can
the bot -- what keeps a lowsec run safe is that those do not spawn there, which
is a fact about where the ship is rather than about this setting.

-}
anomalyNameMatches : String -> String -> Bool
anomalyNameMatches scannerName entry =
    let
        wanted =
            entry |> String.trim |> String.toLower

        found =
            scannerName |> String.trim |> String.toLower
    in
    if String.endsWith "*" wanted then
        found |> String.startsWith (wanted |> String.dropRight 1 |> String.trimRight)

    else
        found == wanted


shouldAvoidRatAccordingToSettings : BotSettings -> String -> Bool
shouldAvoidRatAccordingToSettings settings ratName =
    settings.avoidRats |> List.map String.toLower |> List.member (ratName |> String.toLower)


memoryOfAnomalyWithID : String -> BotMemory -> Maybe MemoryOfAnomaly
memoryOfAnomalyWithID anomalyID =
    .visitedAnomalies >> Dict.get anomalyID


{-| Whether the ship is warping, as far as this reading can say.

**Three answers rather than two, and the third one is issue #194.** `Just True`
is the client naming `Warp`; `Just False` is the client naming some other
maneuver -- `Orbit`, `Approach`, `Aligning`; and `Nothing` is the client naming
none, which is what a ship that has stopped maneuvering looks like and also what
a reading with no ship UI at all looks like. Whoever reads this has to decide
which of the last two they meant, because the type cannot.

Lifted out of `updateMemoryForNewReadingFromGame` so that a case can execute it
against a real parsed reading. Both apps derived it inline, and in two different
shapes -- one a pipeline, one a `case` -- which is a drift that compiles.

-}
shipWarpingFromReading : ReadingFromGameClient -> Maybe Bool
shipWarpingFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
        |> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverWarp)


{-| Whether this reading is the one a warp ended on.

**Issue #194: the form this replaces could never answer `True` at the end of a
warp.** It asked for `shipWarpingInLastReading == Just True` together with
`shipIsWarping == Just False`, and `shipIsWarping` is a `Maybe` over the
maneuver the client _names_: `Just True` for `Warp`, `Just False` for some
**other** named maneuver, and `Nothing` when no maneuver is named at all. So
`Just False` never meant "the ship is not warping" -- it meant "the ship is
orbiting, or approaching, or aligning". A ship that has simply stopped answers
`Nothing`.

Captured off the live client during saxrat run 29, sampling the ship UI's
indication about once a second across two warps: while warping the container
holds `Warp Drive Active` and the destination, and on the reading the warp ends
the container is still present and holds only the location labels -- no maneuver
word anywhere in it. The parser reads no `maneuverType` from that, so the
transition a warp really makes is `Just True -> Nothing`, and the condition that
demanded `Just False` was unreachable in every recorded run.
`EveOnline.BotFramework.shipUIIndicatesShipIsWarpingOrJumping` already treats an
absent indication as "not maneuvering", and says so in a comment; this was the
one place that did not.

So the transition is `Just True` followed by anything that is _not_ `Just True`.

**And the ship UI has to be present to say so.** `Nothing` is equally what a
reading with no ship UI at all answers -- docked, a client that did not render,
a reading taken across a session change -- and none of those is an arrival,
because nothing arrived. The presence of the ship UI is read separately for
exactly that reason: it is what keeps "the ship stopped maneuvering" apart from
"we could not see the ship", which the `Maybe Bool` cannot distinguish on its
own and which `shipWarpingInLastReading` stores in the same shape.

-}
warpJustEnded :
    { warpingLastReading : Maybe Bool
    , readingNow : ReadingFromGameClient
    }
    -> Bool
warpJustEnded { warpingLastReading, readingNow } =
    (warpingLastReading == Just True)
        && (readingNow.shipUI /= Nothing)
        && (shipWarpingFromReading readingNow /= Just True)


{-| How many readings after a warp ends a pilot on the overview still counts as
_found on arrival_.

**Zero, so the arrival is the reading the ship lands on and no other.** The
window this constant bounds was built to cover a lag that has since been
measured and is not there, and every reading of it past the landing one is
exposure to the opposite bug.

The lag it was meant to cover is the probe scanner not having named the anomaly
yet, since the snapshot has nowhere to be filed until it has. Measured over
saxrat runs 16, 21, 23 and 24 -- taking every reading on which `HOOOOONK in
warp` stops, then reading the `Current anomaly:` line forward from it -- the
anomaly is named **on** the warp-end reading in 123 of the 123 arrivals that
ever name one: median 0, p90 0, max 0. The remaining 127 arrivals name no
anomaly at all before the next warp, and no bound reaches those either. A wider
window therefore converts no arrival into a recorded one.

**The cost is measured on the same corpus.** Of those 250 arrivals, the number
that would record at least one pilot is 19 at a bound of 0, 19 at 1, 20 at 3,
25 at 10 and 34 at 30. The fifteen a 30-reading window adds are by construction
arrivals where nobody was on the overview when the ship landed and somebody
turned up afterwards -- which is the case this feature must **not** fire on. A
neutral already there when we land means leave; a neutral arriving while we are
already fighting means tough it out. At 30 readings, nearly half of everything
recorded would have been the wrong half.

A bound of 1 records the same 19 arrivals as a bound of 0 across all 250, so on
this corpus the overview never took an extra reading to draw a pilot who was
already on the grid. That is the only thing a wider bound could honestly buy
here, and it did not happen once.

**The unit stays readings**, which is what every other bound in these bots is
counted in -- `approachIndicationTrustedForTicks` is 10,
`dockingRunInPatienceReadings` 20, `gateRefusesThisShipTicks` 40 and
`droneRecallGiveUpTicks` 60 -- so a later widening is comparable to those
without a conversion done in the reader's head, and has to argue against the
counts above rather than merely feel safer. In wall-clock terms a reading is one
to eight seconds by this repo's own two figures, so the 30 this shipped with was
30 s to 4 minutes of grid to be wrong about.

-}
otherPilotArrivalWindowReadings : Int
otherPilotArrivalWindowReadings =
    0


{-| Whether this reading is still close enough to the last warp to be arrival.

**`Nothing` is a closed window, not an open one.** No warp has finished this
session -- the bot started already sitting in an anomaly, or the transition has
never been seen -- so there is no arrival to be inside of, and nothing is
recorded. That is both the conservative direction and what the bot does today:
`warpJustEnded` is false on every one of those readings too.

The comparison is inclusive, so the reading a warp ends on -- zero readings
elapsed -- is arrival. At the bound this shipped with that is the whole of the
window, which is what the corpus behind `otherPilotArrivalWindowReadings` asks
for; the comparison is written as a bound rather than as `== Just 0` so that
widening it is a change to the number and an argument against those counts,
rather than a change to this rule.

-}
arrivalWindowIsOpen : { readingsSinceWarpEnded : Maybe Int } -> Bool
arrivalWindowIsOpen { readingsSinceWarpEnded } =
    case readingsSinceWarpEnded of
        Nothing ->
            False

        Just readings ->
            readings <= otherPilotArrivalWindowReadings


{-| The pilots this anomaly's arrival has found, after one more reading.

**It accumulates rather than overwrites, and that is what keeps the memory
latched.** The snapshot it replaces ran on exactly one reading, so whatever it
wrote was final; a window of readings that each _replaced_ the list would forget
a pilot who was on the grid when the ship landed and warped off two readings
later -- and forgetting is the half #194 says is dead, since the same list is
what makes the scan result be skipped later. Adding only can never unsay a
reason, so the verdict behaves exactly as the single-reading one did: written
once during arrival, and untouched for the lifetime of that anomaly's memory.

Order is first-seen first, because `findReasonToAvoidAnomalyFromMemory` reports
the head of this list, and the pilot who was already there when the ship landed
is the one an operator wants named.

A closed window adds nothing, which is the sentence that stops this becoming the
mid-fight check the issue exists to refuse.

-}
otherPilotsFoundOnArrivalAfterReading :
    { windowIsOpen : Bool
    , foundBefore : List String
    , seenNow : List String
    }
    -> List String
otherPilotsFoundOnArrivalAfterReading { windowIsOpen, foundBefore, seenNow } =
    if not windowIsOpen then
        foundBefore

    else
        foundBefore
            ++ (seenNow |> List.filter (\pilot -> not (List.member pilot foundBefore)))


{-| The arrival window, for the status line -- read by no decision.

Nothing about the window was visible on a reading before this, which is most of
why #194 took a corpus sweep to find: the snapshot's silence and a grid with
nobody on it print identically. The three things this separates are the three
ways the feature can still be inert.

  - `no warp has finished this session` all run means the window never opens, so
    nothing below it can fire. That is what #194 actually was: the trigger
    demanded `shipIsWarping == Just False` where a warp ending answers `Nothing`,
    so it could not fire at the end of a warp at all. `warpJustEnded` is the
    fix, and this clause is how a run says whether it stayed fixed.
  - `no anomaly named in the probe scanner` while the window is open is #194's
    own diagnosis happening in front of the operator -- and the window closing
    with that clause on every reading of it would mean 30 readings is not long
    enough.
  - a name recorded here is the leave branch about to fire, and the first time
    `FoundOtherPilotOnArrival` will ever have been constructed.

-}
describeArrivalWindow :
    { readingsSinceWarpEnded : Maybe Int
    , windowIsOpen : Bool
    , otherPilotsFoundOnArrival : Maybe (List String)
    }
    -> String
describeArrivalWindow { readingsSinceWarpEnded, windowIsOpen, otherPilotsFoundOnArrival } =
    let
        describeWindow =
            case readingsSinceWarpEnded of
                Nothing ->
                    "no warp has finished this session"

                Just sinceWarpEnded ->
                    (if windowIsOpen then
                        "OPEN, "

                     else
                        "closed, "
                    )
                        ++ String.fromInt sinceWarpEnded
                        ++ " of "
                        ++ String.fromInt otherPilotArrivalWindowReadings
                        ++ " readings since the last warp ended"

        describeFound =
            case otherPilotsFoundOnArrival of
                Nothing ->
                    "no anomaly named in the probe scanner, so nothing can be recorded"

                Just [] ->
                    "nobody recorded on arrival here"

                Just pilots ->
                    "found on arrival here: " ++ String.join ", " pilots
    in
    "Arrival window: " ++ describeWindow ++ "; " ++ describeFound ++ "."


{-| The anomaly we most recently arrived in, found by picking the memory
entry with the latest `arrivalTime` -- used when the anomaly's own
signature has dropped off the probe scanner (so we can no longer look it
up by ID) but we still want to honor its wait/loot timers instead of
treating our arrival as having just happened.
-}
mostRecentlyVisitedAnomalyMemory : BotMemory -> Maybe MemoryOfAnomaly
mostRecentlyVisitedAnomalyMemory botMemory =
    botMemory.visitedAnomalies
        |> Dict.values
        |> List.sortBy (.arrivalTime >> .milliseconds)
        |> List.reverse
        |> List.head


arrivalInAnomalyAgeSecondsFromMemory : BotDecisionContext -> Int
arrivalInAnomalyAgeSecondsFromMemory context =
    context.memory
        |> mostRecentlyVisitedAnomalyMemory
        |> Maybe.map (\memoryOfAnomaly -> (context.eventContext.timeInMilliseconds - memoryOfAnomaly.arrivalTime.milliseconds) // 1000)
        |> Maybe.withDefault 0


anomalyBotDecisionRoot : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRoot context =
    -- Anything the memory update concluded on its own announces itself here, at
    -- the root, rather than in a branch -- it is settled in
    -- `updateMemoryForNewReadingFromGame`, which runs on every reading whatever
    -- the bot is doing, so the branch that learned it is not reliably the branch
    -- being evaluated. The field holds a message only on the reading its
    -- conclusion changed, so this is one line per change with no separate
    -- "already reported" flag to get wrong.
    ([ context.memory.messageBoxLastChange
     , context.memory.lockRangeLastChange
     , context.memory.maxTargetsLastChange
     , context.memory.droneLaunchLastChange
     , context.memory.lockBatchLastChange
     , context.memory.fleetBroadcast.lastChange
     ]
        |> List.filterMap identity
        |> List.foldr describeBranch (anomalyBotDecisionRootBeforeApplyingSettings context)
    )
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


anomalyBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRootBeforeApplyingSettings context =
    -- The head is a bound whose expiry ends the session and nothing else, so it
    -- sits above `generalSetupInUserInterface` rather than below it. Everything
    -- from the setup list down needs some state the client has to be in --
    -- a menu cleared, a panel expanded, a ship UI showing -- and a bound
    -- counted in readings must be asked on readings where none of that holds.
    -- See `endSessionOnAnExpiredBound`.
    endSessionOnAnExpiredBound context
        |> Maybe.withDefault
            (generalSetupInUserInterface context.memory.messageBoxStandoff
                context.eventContext.botSettings.acceptFleetInviteFrom
                context.previousStepsEffects
                context.readingFromGameClient
                |> Maybe.withDefault
                    (recoverPodAfterShipLoss context
                        |> Maybe.withDefault
                            -- Read directly off the reading rather than
                            -- waiting for `branchDependingOnDockedOrInSpace`
                            -- to reach `ifSeeShipUI`, so a ship worth
                            -- retreating still retreats even though
                            -- `respondToFleetBackupBroadcast` sits above that
                            -- split -- a lost ship helps nobody. Below the
                            -- retreat's own doc comment says this is below
                            -- it; it previously was not, and a critically
                            -- damaged ship would have warped *toward* a
                            -- fleet-mate's fight rather than away from its
                            -- own. `runAwayIfLowHealth` is still reached the
                            -- ordinary way further down for every reading
                            -- this does not fire on -- calling it twice on
                            -- the same context and reading is redundant, not
                            -- wrong.
                            ((context.readingFromGameClient.shipUI
                                |> Maybe.andThen (runAwayIfLowHealth context)
                                -- The backup call, and only that one, on a
                                -- reading the retreat would have spent
                                -- re-warping a ship already in warp. See
                                -- `runAwayAndTellTheFleet` for why it cannot
                                -- sit below this arm instead.
                                |> Maybe.map (runAwayAndTellTheFleet context)
                             )
                                |> Maybe.withDefault
                                    -- Below the retreat, so a ship worth saving
                                    -- is saved before anything is said about
                                    -- it, and above everything that flies the
                                    -- ship, so a call goes out beside the
                                    -- action it is about rather than after it.
                                    -- Answers `Nothing` on every reading with
                                    -- nothing to say and on every reading
                                    -- `fleet-commander` is unset, which is
                                    -- every reading of a bot that does not set
                                    -- it.
                                    (sendFleetBroadcastAsFleetCommander fleetBroadcastVerbsSent context
                                        |> Maybe.withDefault
                                            (respondToFleetAtLocationBroadcast context
                                                |> Maybe.withDefault
                                                    (respondToFleetBackupBroadcast context
                                                        |> Maybe.withDefault
                                                            (followFleetBroadcast context
                                                                |> Maybe.withDefault
                                                                    (branchDependingOnDockedOrInSpace
                                                                        { ifDocked =
                                                                            continueIfShouldHide
                                                                                { ifShouldHide =
                                                                                    describeBranch "Stay docked." waitForProgressInGame
                                                                                }
                                                                                context
                                                                                |> Maybe.withDefault
                                                                                    (if
                                                                                        context.memory.noProbeScanResultsAndNoRouteLastTimeInSpace
                                                                                            && (context.readingFromGameClient
                                                                                                    |> infoPanelRouteFirstMarkerFromReadingFromGameClient
                                                                                                    |> (==) Nothing
                                                                                               )
                                                                                            -- A "Warp to Site" opportunity takes
                                                                                            -- precedence over staying docked: the
                                                                                            -- Opportunities panel this comes from is
                                                                                            -- part of the persistent left sidebar
                                                                                            -- (like the route panel), so it's
                                                                                            -- checkable even while docked. Undocking
                                                                                            -- here rather than trying to click it
                                                                                            -- directly from dock -- untested whether
                                                                                            -- that even works -- lets the very next
                                                                                            -- tick's normal in-space priority chain
                                                                                            -- (which already puts this ahead of
                                                                                            -- tether/dock) pick it up once genuinely
                                                                                            -- in space.
                                                                                            && (context.readingFromGameClient
                                                                                                    |> escalationEntriesPermitted context.eventContext.botSettings
                                                                                                    |> warpToOpportunitySiteIfAvailable
                                                                                                    |> (==) Nothing
                                                                                               )
                                                                                     then
                                                                                        describeBranch
                                                                                            "No anomalies to hunt and no route set last time we were in space, and still no route now -- stay docked instead of undocking right back into the same dead end."
                                                                                            waitForProgressInGame

                                                                                     else
                                                                                        undockUsingStationWindow context
                                                                                    )
                                                                        , ifSeeShipUI =
                                                                            \shipUI ->
                                                                                runAwayIfLowHealth context shipUI
                                                                                    |> Maybe.withDefault
                                                                                        (continueIfShouldHide
                                                                                            { ifShouldHide = hideFromNeutralInLocal context
                                                                                            }
                                                                                            context
                                                                                            |> Maybe.withDefault
                                                                                                (decideNextActionWhenInSpace context { shipUI = shipUI })
                                                                                        )
                                                                        }
                                                                        context
                                                                    )
                                                            )
                                                    )
                                            )
                                    )
                            )
                    )
            )


{-| The bounds whose expiry ends the session, asked where nothing can decline to
ask them.

Issue #133, which is the mission runner's #126 in this file and #102 before that.
`shipLoss.readingsSince` is advanced in `updateMemoryForNewReadingFromGame` --
unconditionally, on every reading, with no reference to what the bot managed to
do with the reading -- while the comparison over it sat inside
`recoverPodAfterShipLoss`, below `generalSetupInUserInterface`. Anything
answering up there starved the bound while the number it is compared against
went on climbing.

**A give-up that ends the session is counted in elapsed readings and belongs
where nothing can decline to ask it**, which is PR #115's rule and what decides
the shape. A give-up that declines an _action_ bounds effort and belongs where
the action is. This one is a `describeBranch` around `FinishSession` and nothing
else -- no click, no dock, no menu, no wait -- so it needs no state reached and
can be evaluated on any reading at all.

**The largest starvation this list can produce is now bounded, and the hoist is
still what makes the bound reachable.** #138 ported `MessageBoxStandoff` from
the mission runner's #109: `closeMessageBox` counts the readings one box has
survived and answers `Nothing` once it has survived
`messageBoxStandoffGiveUpReadings`, so a window nothing closes no longer holds
this list forever. That is a bound on one known starver, not a guarantee about
the list -- everything else in it is still evaluated above this branch, and a
new entry without a bound of its own would starve the pod recovery exactly as
run 30 starved the mission runner's abandonment. A ship lost while something up
there repeats is a capsule sitting in the pocket that killed it, and this rule
is what stops the session ending only when a person notices.

One bound so far, so this is a `Maybe.map` rather than the mission runner's list
of them: it has a second (`abandonmentOutOfTime`) and there is no mission to
abandon here.

-}
endSessionOnAnExpiredBound : BotDecisionContext -> Maybe DecisionPathNode
endSessionOnAnExpiredBound context =
    podRecoveryOutOfTime
        { shipLoss = context.memory.shipLoss
        , shipUIIsShowing = context.readingFromGameClient.shipUI /= Nothing
        }
        |> Maybe.map
            (\verdict ->
                describeBranch
                    (describePodRecoveryOutOfTime
                        { lastDockedStationName = context.memory.lastDockedStationNameFromInfoPanel
                        , verdict = verdict
                        }
                    )
                    (Common.DecisionPath.endDecisionPath FinishSession)
            )


{-| The three things that have to be dealt with before any decision can be made
about the game itself.

`messageBoxStandoff` is passed down rather than read in `closeMessageBox`
because it is not a fact about this reading: it is how many readings the box in
front of the bot has already survived, and only `BotMemory` can say. Everything
else here is answerable from the reading alone -- except
`ensureInfoPanelLocationInfoIsExpanded`'s own settling guard, which reads the
previous steps' effects for the same reason a module button's click-settling
guard does.

**This whole list is evaluated above the docked-or-in-space split**, so anything
in it that can repeat forever freezes the entire bot rather than one branch.
That is #101 in the mission runner and #138 here. Two of the three now carry a
bound of their own and may not lose it: `closeMessageBox` gives up on a box
nothing closes, and `ensureInfoPanelLocationInfoIsExpanded` answers `Nothing`
while its own repair click settles rather than waiting on it (#297, where the
two halves of that repair alternated and held the tree for 364 readings of one
recorded run). `closeSystemSettingsMenu` is the one left unbounded, which is why
`endSessionOnAnExpiredBound` is still asked above this list rather than below
it.

-}
generalSetupInUserInterface :
    Maybe MessageBoxStandoff
    -> List String
    -> List (List EffectOnWindow.EffectOnWindowStruct)
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
generalSetupInUserInterface messageBoxStandoff acceptFleetInviteFrom previousStepsEffects readingFromGameClient =
    [ closeSystemSettingsMenu
    , closeMessageBox messageBoxStandoff acceptFleetInviteFrom
    , ensureInfoPanelLocationInfoIsExpanded previousStepsEffects
    ]
        |> List.filterMap
            (\maybeSetupDecisionFromGameReading ->
                maybeSetupDecisionFromGameReading readingFromGameClient
            )
        |> List.head


{-| Recovers from the game's own Settings/pause menu covering the whole
screen -- a real incident, not a hypothetical: it opened live during a
session (most likely from a bare Escape press meant for
`clearStrayContextMenu`/the context-menu-occlusion fallback landing when no
context menu was actually open, since EVE treats a "naked" Escape as "open
the pause menu" the same way it would from any other screen). Once open, it
blocks everything else this bot's decision tree looks for (ship UI,
overview, etc.), so nothing else in the tree would ever recognize the state
enough to close it on its own -- confirmed live: the bot only recovered
after a person closed the menu manually. Placed in
`generalSetupInUserInterface` (checked before even docked-vs-in-space) so it
preempts everything else the moment it's detected.

Targets the close ('X') icon in the menu's own header rather than any of
the page-specific buttons in its footer (e.g. "Return to Game"): the header
and its close button are common to every page this menu can show (Settings,
the base pause screen, etc.), while the footer's buttons and their
positions are specific to whichever page happens to be open -- confirmed
live via a memory dump correlated with the running client that this
button's `_elementId` is the stable, page-independent `"closeMenuClick"`,
found by walking up from the `l_systemmenu`-named layer
(`parseContextMenusFromUITreeRoot` uses the same `_name`-lookup convention
for the analogous `l_menu` layer). Also confirmed live, while recovering
from this by hand: a mouse move straight to the button's coordinates (no
intermediate points) did nothing at all, not even register a hover
tooltip -- only worked once the cursor got there via a real multi-step
glide. That was diagnosed against `cg_input` directly, bypassing
botlab\_host.py's own input path entirely; a normal bot-driven click here
goes through `_windows_input`'s `_move_mouse_eased`, which already glides
every `MouseMoveAbsolute` by default, so plain `mouseClickOnUIElement` is
sufficient -- nothing extra needed on the Elm side for this.

-}
closeSystemSettingsMenu : ReadingFromGameClient -> Maybe DecisionPathNode
closeSystemSettingsMenu readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "l_systemmenu")
            )
        |> List.head
        |> Maybe.andThen
            (EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
                >> List.filter
                    (.uiNode
                        >> EveOnline.ParseUserInterface.getElementIdFromDictEntries
                        >> (==) (Just "closeMenuClick")
                    )
                >> List.head
            )
        |> Maybe.map
            (\closeButton ->
                describeBranch
                    "The game's own Settings/pause menu is open, covering everything else -- close it."
                    (decideActionForCurrentStep
                        (mouseClickOnUIElement MouseButtonLeft closeButton
                            |> Result.withDefault []
                        )
                    )
            )


closeMessageBox : Maybe MessageBoxStandoff -> List String -> ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox standoff acceptFleetInviteFrom readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.andThen
            (\messageBox ->
                case messageBoxStandoffVerdictForBox standoff messageBox of
                    LeaveTheMessageBoxAlone ->
                        -- The whole of #138: `Nothing` here is what lets the
                        -- rest of the tree run. The box is still on the screen
                        -- and every branch below is now working around it,
                        -- which is worse than a closed box and incomparably
                        -- better than nothing running at all -- the pod
                        -- recovery's deadline included, since a capsule left
                        -- in the pocket is what an unattended bot pays for a
                        -- held tree. The give-up said so once at the root on
                        -- the reading it was reached, and the status line
                        -- keeps saying so.
                        Nothing

                    PressEscapeAtTheMessageBox ->
                        Just
                            (describeBranch
                                ("This message box has not closed in "
                                    ++ String.fromInt messageBoxAnswersBeforeEscape
                                    ++ " readings of answering it, so the answer does not fit it -- press Escape at it instead."
                                )
                                (decideActionForCurrentStep
                                    [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                                    , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                                    ]
                                )
                            )

                    AnswerTheMessageBox ->
                        -- The accept is asked first and answers `Nothing` for
                        -- everything that is not a permitted invitation, so the
                        -- declining answer remains what every other box gets.
                        case
                            fleetInvitationToAccept acceptFleetInviteFrom messageBox
                                |> Maybe.andThen
                                    (\inviter -> acceptFleetInvitationFrom inviter messageBox)
                        of
                            Just accept ->
                                Just accept

                            Nothing ->
                                Just (closeMessageBoxByDeclining messageBox)
            )


{-| What to do about the box in front of the bot, given how long it has been
there.

**The declining answer stays the default and that is not negotiable** -- #54's
standing lesson in the mission runner, and the reason the ladder starts where
this branch always did rather than at something cleverer. These dialogs guard
destructive actions. What #138 adds is only what happens once the answer has
demonstrably not worked.

-}
type MessageBoxStandoffVerdict
    = AnswerTheMessageBox
    | PressEscapeAtTheMessageBox
    | LeaveTheMessageBoxAlone


{-| How many readings the ordinary answer gets before the escalation.

**60, and it rests on the mission runner's corpus rather than on this bot's.**
The three recorded saxrat runs hold **49,235 readings and not one message box**
-- `TheRecordedSaxratRunsCannotSizeThisBoundTest` checks that silence rather
than leaving it remembered -- so there is nothing here to measure a threshold
against, and inventing a saxrat-specific number would be inventing it. What the
mission runner measured transfers because the thing being measured is the
client's, not the bot's: the same widget, parsed by the same
`parseMessageBoxesFromUITreeRoot` matching on `pythonObjectTypeName` alone, and
dismissed by the same three options in the same order. Counting consecutive
readings with a box on the screen, that bot's recovered runs give 175 stretches
of 6, 10, 11, 18, 20 and 44 readings and nothing else, while run 30's one box
ran to 32,585. **Nothing recorded lies between 44 and the incident**, so 60 is
placed in a gap rather than cut through a distribution: a third again on top of
the slowest dialog anyone has recorded, and still an end inside a minute where
run 30 spent three hours and forty-four.

A stretch is an upper bound on any one box, since a stretch can hold several
dialogs back to back, so the real separation is wider than those numbers. That
is the safe direction for a threshold that must never fire on a box the answer
was about to close. Mission runner run 35 is the one live outing the ladder has
had: 728 boxes dismissed with the counter never above **2**.

**It is not the count of clicks dispatched**, which is roughly half of it -- the
framework reads on some readings and acts on others. Readings are the unit
`contextMenuStuckTicks` and `lootWindowOpenTicks` are already counted in, they
are what the corpus above was measured in, and a reading spent looking at a box
that will not close is spent either way, because nothing else in the tree runs
on it.

-}
messageBoxAnswersBeforeEscape : Int
messageBoxAnswersBeforeEscape =
    60


{-| How many readings the whole standoff gets before the bot stops answering.

Twice `messageBoxAnswersBeforeEscape`, so Escape gets exactly as long to work as
the answer it replaced -- written as a multiple for `routeAskGiveUpReadings`'s
reason, so the argument cannot drift away from the number.

-}
messageBoxStandoffGiveUpReadings : Int
messageBoxStandoffGiveUpReadings =
    messageBoxAnswersBeforeEscape * 2


{-| The ladder, over the standoff `updateMemoryForNewReadingFromGame` recorded.

**Escape is what this codebase already escalates with**, and it needs no focus:
`clearStrayContextMenu` presses it at a menu that has not advanced in three
ticks. A message box that has not closed in sixty readings is the same shape.

**Ctrl+W is deliberately not in the ladder**, though it is the client's own
"close the active window". It acts on the _focused_ window, and the loot window
paid for that lesson twice -- 650 presses at an unfocused window in one run and
919 decision lines in another, closing nothing either time; see
`lootWindowCloseRung`, which presses `Alt+C` instead. Clicking an unidentified
modal to focus it is a click into a dialog nobody has read, which is the one
thing `closeMessageBoxByDeclining` refuses to do -- and the loot window says a
focus click was not what was missing anyway, since one unfocused `Alt+C` shut
it. There is no equivalent toggle for a message box, which is why this ladder
escalates with Escape rather than with a key of its own.

**A naked Escape can open the client's own pause menu**, which
`closeSystemSettingsMenu` records happening live in this very file from exactly
this key. That is covered rather than risked here for the same reason it is
there: `closeSystemSettingsMenu` is the entry _before_ this one in
`generalSetupInUserInterface`, so a pause menu opened on one reading is closed
on the next by the branch that exists for it, and it is closed first because
that list answers with its head.

**Escape's one live outing is one press, and it settles nothing.** saxrat run 11
reached this rung and the client stopped answering reads on the same reading, so
the bot processed exactly one reading here and dispatched exactly one effect
sequence -- against 59 dispatched on the rung below it, one per reading. The
2,439 `pressing Escape at it` lines in that log are one status text reprinted,
which is this file's own "a decision in the log is not an action" arriving in the
place it is least expected. So whether Escape closes a window the answer does not
is still the open question #101 left, and the rung stays: deleting it would be
answering that question from a sample of one press, and what the give-up needs is
readings spent, which this rung supplies whether or not the key works.

-}
messageBoxStandoffVerdict : Maybe MessageBoxStandoff -> MessageBoxStandoffVerdict
messageBoxStandoffVerdict standoff =
    case standoff of
        Nothing ->
            AnswerTheMessageBox

        Just { readings } ->
            if messageBoxStandoffGiveUpReadings <= readings then
                LeaveTheMessageBoxAlone

            else if messageBoxAnswersBeforeEscape <= readings then
                PressEscapeAtTheMessageBox

            else
                AnswerTheMessageBox


{-| The standoff's verdict, except that one box is never answered at all.

`closeMessageBoxByDeclining`'s promise is that the automatic reply is always the
declining one, because these dialogs guard destructive actions. EVE's Connection
Lost modal inverts that: it carries a single `Quit` button, no `Close`/`OK` and
no `no_dialog_button`, so both of the recognising options miss and the answer
falls through to the third -- the window's own close control, the one meant for
"a dialog whose buttons we do not recognise at all". On this box **the declining
answer is the destructive one**, and saxrat run 22 lost its client to it six
minutes into an eight-hour tour:

    12:28:31 (info) Network communication between your computer and the EVE
                    Online server has been interrupted.

    + I see a message box to close.
    ++ Dismiss it using the window's close button.

and then the log stops, with no client process and no EVE window left.

**The escape rung had to be covered too, which is why this is here rather than
in `closeMessageBoxByDeclining`.** #138's ladder answers for
`messageBoxAnswersBeforeEscape` readings and then presses Escape, and Escape at
a modal whose only action is Quit is the same keypress by another route. Both
rungs are what this skips.

**It is not a bound and it does not wait**, because there is nothing to wait
for: a client with no server connection cannot be recovered by anything the bot
can press, and quitting takes it away from the operator who _can_ reconnect. So
the answer is the one #138 already built for a box that will not close --
`LeaveTheMessageBoxAlone`, so `closeMessageBox` answers `Nothing` and the rest
of the tree runs -- reached immediately rather than after 120 readings of
pressing things at it.

The cost is the one that verdict already carries: `Nothing` cannot hold a
decision line, so the decision log says nothing about this box. What does say so
is the status clause, which counts every reading a box is up and, since #165,
names it -- `Message box: N/120 ... 'Quit / Connection Lost / Connection to
server was lost.'` is what an operator sees on every reading.

Run 21 met the same dialog and sat at it for five hours rather than quitting,
because the screen was locked and no input could land. That is the same defect
with the input path removed, not a second one.

-}
messageBoxStandoffVerdictForBox :
    Maybe MessageBoxStandoff
    -> EveOnline.ParseUserInterface.MessageBox
    -> MessageBoxStandoffVerdict
messageBoxStandoffVerdictForBox standoff messageBox =
    if messageBoxSaysTheConnectionIsLost messageBox then
        LeaveTheMessageBoxAlone

    else
        messageBoxStandoffVerdict standoff


{-| Whether the box is the client saying it has lost the server.

Matched on the client's own words, and on two of them rather than one:
`Connection Lost` is the title and `connection to server was lost` the body, and
both were read off the box that took the client down. Two substrings for #31's
reason -- a single common word would reach dialogs this must not silence, and
silencing a dialog is exactly how a bot stops answering something it should.

The button is deliberately not what this reads. `Quit` is a plausible label on
boxes that have a safe answer beside it, and the identity that would settle it
is not available: `messageBoxIdentityForOperator` truncates before the
`with buttons [...]` section, so neither recorded instance says what this box's
buttons were.

-}
messageBoxSaysTheConnectionIsLost : EveOnline.ParseUserInterface.MessageBox -> Bool
messageBoxSaysTheConnectionIsLost messageBox =
    let
        texts =
            messageBox.uiNode.uiNode
                |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                |> List.map String.toLower

        says needle =
            texts |> List.any (String.contains needle)
    in
    says "connection lost" && says "connection to server was lost"


{-| What a message box is, for the purpose of counting how long this one has
been in the way.

Its own display texts and its buttons, joined into one string -- see
`MessageBoxStandoff` for why the display region is deliberately not in it, and
why a box that changes its wording is treated as a new box.

The buttons carry their `_name` as well as their label, because the label is
what a person reads and the name is what this file acts on: `no_dialog_button`
is the one name relied on across client languages, and a dialog offering it is a
different dialog from one offering an unnamed OK even where both render the same
word. Reading both also means the identity is never empty for a box that has
buttons, which the window that started this had.

-}
messageBoxIdentity : EveOnline.ParseUserInterface.MessageBox -> String
messageBoxIdentity messageBox =
    let
        nonEmpty =
            List.map String.trim >> List.filter (String.isEmpty >> not)

        textOfBox =
            messageBox.uiNode.uiNode
                |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                |> nonEmpty
                |> String.join " / "

        describeButton button =
            [ button.uiNode.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries
            , button.mainText
            ]
                |> List.filterMap identity
                |> nonEmpty
                |> String.join "="
    in
    "message box saying '"
        ++ textOfBox
        ++ "' with buttons ["
        ++ (messageBox.buttons |> List.map describeButton |> String.join ", ")
        ++ "]"


{-| The one line the operator gets when the bot stops answering a box.

32,585 identical `Dismiss it using No.` lines is what the mission runner's run
30 gave instead, and `stall_watch.py` deduped them into a single alarm, so
nothing escalated. This says which box it was and everything that was tried on
it, once, at the root -- `lockRangeLastChange`'s mechanism, for its reason: the
verdict is reached in the memory update, which runs whatever the bot is doing,
and the branch that would otherwise say so is precisely the branch that has just
stopped running.

The identity is cut by `messageBoxIdentityForOperator` because it carries the
box's whole rendered text, and a dialog with a paragraph in it would otherwise
push the rest of the sentence off whatever the operator is reading.

-}
describeMessageBoxGivenUpOn : String -> String
describeMessageBoxGivenUpOn identity =
    "Nothing closes this "
        ++ messageBoxIdentityForOperator identity
        ++ " -- answered it "
        ++ String.fromInt messageBoxAnswersBeforeEscape
        ++ " readings running and then pressed Escape at it for another "
        ++ String.fromInt (messageBoxStandoffGiveUpReadings - messageBoxAnswersBeforeEscape)
        ++ ", and it is still there. Leaving it open and getting on with the rest of the bot rather than answering it forever -- it needs closing by hand."


{-| How much of a box's identity a line prints.
-}
messageBoxGiveUpIdentityLength : Int
messageBoxGiveUpIdentityLength =
    200


{-| A box's identity, cut to what one line can carry.

One function for both readers rather than the cut written out twice, so the
give-up sentence and the status clause cannot come to disagree about how much of
a dialog an operator is shown.

-}
messageBoxIdentityForOperator : String -> String
messageBoxIdentityForOperator identity =
    if messageBoxGiveUpIdentityLength < String.length identity then
        String.left messageBoxGiveUpIdentityLength identity ++ "..."

    else
        identity


{-| The one clause on a reading that says a box is in front of the bot, and now
the only thing that says which box.

Two things make it the only one. Once the give-up is reached `closeMessageBox`
answers `Nothing` and prints no decision line at all, so nothing else on the
reading mentions the box; and `describeMessageBoxGivenUpOn`, which does name it,
is written on the one reading the count crosses
`messageBoxStandoffGiveUpReadings` and on no other.

**saxrat run 11 is what that cost.** One box held that bot for the 59 readings
its answer was clicked and the one reading Escape was pressed, and the run ended
there -- so the give-up was never reached, the identity was never printed, and
what the window was cannot be recovered from a 125 MB log. The only thing the
run says about it is `Dismiss it using the window's close button`, which is the
third and last of `closeMessageBoxByDeclining`'s options and the one a dialog
whose buttons this file does not recognise at all falls through to. Naming the
box on every reading it is counted is the cheapest thing that would have
answered it, and it costs a clause on the readings a box is up and nothing on
any other.

-}
describeMessageBoxStandoff : Maybe MessageBoxStandoff -> String
describeMessageBoxStandoff standoff =
    case standoff of
        Nothing ->
            ""

        Just present ->
            " Message box: "
                ++ String.fromInt present.readings
                ++ "/"
                ++ String.fromInt messageBoxStandoffGiveUpReadings
                ++ (case messageBoxStandoffVerdict (Just present) of
                        AnswerTheMessageBox ->
                            " (answering it)"

                        PressEscapeAtTheMessageBox ->
                            " (pressing Escape at it)"

                        LeaveTheMessageBoxAlone ->
                            " (GIVEN UP ON, still open)"
                   )
                ++ ", "
                ++ messageBoxIdentityForOperator present.identity
                ++ "."


{-| The standoff as it stands after this reading.

No box in the reading ends it outright, which is what keeps the count about
_this_ box: a session that closes forty dialogs starts from zero at each one,
and only a box in front of the bot on every consecutive reading can accumulate
towards the give-up.

-}
messageBoxStandoffAfterReading :
    { before : Maybe MessageBoxStandoff, identityNow : Maybe String }
    -> Maybe MessageBoxStandoff
messageBoxStandoffAfterReading { before, identityNow } =
    identityNow
        |> Maybe.map
            (\identity ->
                case before of
                    Just standoff ->
                        if standoff.identity == identity then
                            { standoff | readings = standoff.readings + 1 }

                        else
                            { identity = identity, readings = 1 }

                    Nothing ->
                        { identity = identity, readings = 1 }
            )


{-| The client's own sentence for a fleet invitation, read off a live one.

Captured from this account's client on 2026-08-10, the whole dialog:

    MessageBox  _name='modal'
      TextHeadline  _setText='Join Fleet?'
      TextBody      _setText='<a href="showinfo:1385//2120724228">Gal Bistot</a>
                              wants you to join their fleet, do you accept?<br><br>NOTE: ...'
      Button _name='yes_dialog_button'  label 'Yes'
      Button _name='no_dialog_button'   label 'No'

Two things that dialog settles beyond this rule. **It is a `MessageBox`**, so
before this change `closeMessageBoxByDeclining` answered it with
`no_dialog_button` and the bot actively _rejected_ every invitation -- observed,
nine `Dismiss it using No.` decisions in saxrat run 13 with the operator
confirming the rejection at the other end. And **`yes_dialog_button` is now read
out of a live UI tree**, which the mission runner's abandonment has wanted since
#54: its Quit Mission confirmation identifies the affirmative by the dialog's
_shape_ precisely because that name had never been seen here.

One marker constant, used by both the test and the slice, so the extraction can
never succeed on a box the matcher would have rejected -- `gateKeyClosingMarker`'s
arrangement, for its reason.

-}
fleetInvitationMarker : String
fleetInvitationMarker =
    "wants you to join their fleet"


{-| The client writes the inviter's name inside a `showinfo` link, so the raw
text is `<a href="showinfo:1385//2120724228">Gal Bistot</a> wants you to ...`.

Stripping the markup before matching is not a nicety: the route setter's MOTD
parse already paid for reading a name through a tag, where a malformed
`Sizamo</loc>d` had to recover as `Sizamod`. A rule reading the raw string would
look for a pilot called `<a href="...">Gal Bistot</a>` and never match one.

-}
textWithoutMarkupTags : String -> String
textWithoutMarkupTags =
    String.foldl
        (\char ( depth, acc ) ->
            if char == '<' then
                ( depth + 1, acc )

            else if char == '>' then
                ( max 0 (depth - 1), acc )

            else if 0 < depth then
                ( depth, acc )

            else
                ( depth, acc ++ String.fromChar char )
        )
        ( 0, "" )
        >> Tuple.second


{-| Who this box says is inviting, if it is a fleet invitation at all.

Each display text is matched on its own rather than the box's texts being joined
first, because the headline `Join Fleet?` would otherwise land in front of the
body and the name would be sliced out of the wrong sentence.

-}
fleetInvitationInviter : EveOnline.ParseUserInterface.MessageBox -> Maybe String
fleetInvitationInviter messageBox =
    let
        inviterFromText text =
            case String.indexes fleetInvitationMarker text of
                [] ->
                    Nothing

                index :: _ ->
                    text |> String.left index |> String.trim |> nonEmptySettingValue
    in
    messageBox.uiNode.uiNode
        |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
        |> List.map textWithoutMarkupTags
        |> List.filterMap inviterFromText
        |> List.head


{-| The invitation this bot is permitted to accept, if this box is one.

**Matched exactly, never as a substring**, which `attack-object` learned in both
directions and which matters more here: a substring rule armed with `Gal` would
accept an invitation from anyone whose name contains it. Case is ignored because
an operator types the setting by hand and the client renders the name as the
character carries it.

-}
fleetInvitationToAccept : List String -> EveOnline.ParseUserInterface.MessageBox -> Maybe String
fleetInvitationToAccept permittedInviters messageBox =
    fleetInvitationInviter messageBox
        |> Maybe.andThen
            (\inviter ->
                if
                    permittedInviters
                        |> List.any
                            (\permitted ->
                                String.toLower (String.trim permitted) == String.toLower inviter
                            )
                then
                    Just inviter

                else
                    Nothing
            )


{-| A button of this box by the `_name` the client gives it.

Top-level rather than reused out of `closeMessageBoxByDeclining`, whose own copy
is deliberately left where it is: that function's standing property is that it
contains no affirmative at all, and a test pins it.

-}
messageBoxButtonNamed :
    String
    -> EveOnline.ParseUserInterface.MessageBox
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
messageBoxButtonNamed name messageBox =
    messageBox.buttons
        |> List.filter
            (.uiNode
                >> .uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just name)
            )
        |> List.head
        |> Maybe.map .uiNode


{-| The one dialog this bot ever answers yes to.

**The standing rule is unchanged and this is stated as narrowly as it can be.**
`closeMessageBoxByDeclining`'s comment -- that these dialogs guard destructive
actions, so the automatic reply must always be the one that declines -- is why
this is a separate branch above it rather than a fourth entry in its list of
dismissal options. Three conditions have to hold together: the box carries the
client's own fleet-invitation sentence, the pilot it names is one an operator
wrote into `accept-fleet-invite-from`, and the affirmative button is present
under the name the live dialog gave it. Anything else falls straight through to
the declining answer, unchanged.

**What accepting costs, since it is a real exception.** A fleet member can be
fleet-warped by the commander, so this hands a stranger the ship's position if
it is ever armed with the wrong name -- which is the whole reason the setting
takes a name rather than a yes, defaults to accepting nobody, and refuses an
empty value.

-}
acceptFleetInvitationFrom : String -> EveOnline.ParseUserInterface.MessageBox -> Maybe DecisionPathNode
acceptFleetInvitationFrom inviter messageBox =
    messageBoxButtonNamed "yes_dialog_button" messageBox
        |> Maybe.map
            (\button ->
                describeBranch
                    ("This is a fleet invitation from '"
                        ++ inviter
                        ++ "', who is named in 'accept-fleet-invite-from' -- accept it."
                    )
                    (decideActionForCurrentStep
                        (mouseClickOnUIElement MouseButtonLeft button
                            |> Result.withDefault []
                        )
                    )
            )


closeMessageBoxByDeclining : EveOnline.ParseUserInterface.MessageBox -> DecisionPathNode
closeMessageBoxByDeclining messageBox =
    describeBranch "I see a message box to close."
        (let
            buttonCanBeUsedToClose =
                .mainText
                    >> Maybe.map (String.trim >> String.toLower >> (\buttonText -> [ "close", "ok" ] |> List.member buttonText))
                    >> Maybe.withDefault False

            namedButton name =
                messageBox.buttons
                    |> List.filter
                        (.uiNode
                            >> .uiNode
                            >> EveOnline.ParseUserInterface.getNameFromDictEntries
                            >> (==) (Just name)
                        )
                    |> List.head

            labelled description button =
                ( description, button.uiNode )

            {- Dismissal options in descending order of confidence.
               They deliberately never include a positive answer:
               these dialogs guard destructive actions, so the bot's
               automatic reply must always be the one that declines.

               1. A plain "Close"/"OK" acknowledgement.
               2. "No" on a confirmation dialog -- which has no
                  Close/OK button at all, so nothing above matches
                  it. `no_dialog_button` is stable across client
                  languages.
               3. The window's own close ('X') control, for a
                  dialog whose buttons we do not recognise at all.
                  Seen live sitting in front of one of these for
                  several ticks with nothing to click.
            -}
            dismissOptions =
                [ messageBox.buttons
                    |> List.filter buttonCanBeUsedToClose
                    |> List.head
                    |> Maybe.map
                        (\button ->
                            labelled (button.mainText |> Maybe.withDefault "close") button
                        )
                , namedButton "no_dialog_button"
                    |> Maybe.map (labelled "No")
                , messageBox.uiNode
                    |> EveOnline.ParseUserInterface.parseWindowControlsFromWindow
                    |> Maybe.andThen .closeButton
                    |> Maybe.map (\node -> ( "the window's close button", node ))
                ]
         in
         case dismissOptions |> List.filterMap identity |> List.head of
            Nothing ->
                describeBranch "I see no way to close this message box." askForHelpToGetUnstuck

            Just ( description, nodeToClick ) ->
                describeBranch ("Dismiss it using " ++ description ++ ".")
                    (decideActionForCurrentStep
                        (mouseClickOnUIElement MouseButtonLeft nodeToClick
                            |> Result.withDefault []
                        )
                    )
        )


{-| Shared by `tetherAtStructure`, `alignToStructure` and
`dockAtRandomStationOrStructure`: the first menu entry whose text matches
`textToSearch` exactly, ignoring case.
-}
withTextContainingIgnoringCase : String -> List EveOnline.ParseUserInterface.ContextMenuEntry -> Maybe EveOnline.ParseUserInterface.ContextMenuEntry
withTextContainingIgnoringCase textToSearch =
    List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head


{-| Shared by `tetherAtStructure`, `alignToStructure` and
`dockAtRandomStationOrStructure`: excludes entries that would jump the ship
through a gate or light a cyno rather than dock/warp/align at a structure.
-}
menuEntryIsSuitable : EveOnline.ParseUserInterface.ContextMenuEntry -> Bool
menuEntryIsSuitable menuEntry =
    [ "cyno beacon", "jump gate" ]
        |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
        |> not


{-| The token both sides of the status-text channel agree on.

Issuing a `RequestToVolatileProcess` from a decision is not possible -- every
one of them is issued by `getNextSetupTask`'s closed setup state machine, which
a decision cannot reach, and `OperateBotConfiguration` gives a running bot only
`buildTaskFromEffectSequence`, whose vocabulary is mouse moves, buttons, keys
and scroll. A solar system name cannot be spelled in it.

So the ask rides a field that already crosses the boundary. `ContinueSession
.statusText` is free prose the host reads every tick, and the host scans it for
a token ordinary prose cannot produce.

**One-way and unacknowledged, which is a property rather than a limitation.**
The bot's confirmation that a route was set is the client's own route panel --
stronger evidence than the host's report of what it asked for. The status text
is also _printed_, on every reading, so a system name may travel this way and a
credential may not.

-}
hostDirectivePrefix : String
hostDirectivePrefix =
    "@host "


hostDirectiveSetDestination : String -> String
hostDirectiveSetDestination systemName =
    hostDirectivePrefix ++ "set-destination " ++ systemName


{-| The client's own wording for a fleet travel broadcast, read off a live one.

Captured from this account's client on 2026-08-11, three separate broadcasts,
all of this shape:

    FleetBroadcastCont          _name='broadcastCont'
      ContainerAutoSize         _name='mainCont'
        Container               _name='lastBroadcastCont'
          Container             _name='lastBroadcastBanner'
            EveLabelMedium      _name='bannerLabel'
                                _setText='Gal Bistot: Travel to Riramia'

One marker constant, shared by the test and the slice, so the extraction can
never succeed on a banner the matcher would have rejected.

-}
fleetTravelBroadcastMarker : String
fleetTravelBroadcastMarker =
    ": Travel to "


{-| Every descendant of the fleet window itself, so a search for a `_name`
the client reuses elsewhere (`entryLabel`, confirmed live to also be the
drones window's own row name) cannot pick up a node from some other window
instead. Fixes a real bug: `fleetBroadcastHistoryEntryText` used to search
`readingFromGameClient.uiTree` whole, and with drones actively engaged --
each rendering an `entryLabel` row such as `'Integrated' Acolyte Fighting`
-- `List.head` over the unscoped tree returned the drone's row rather than
the broadcast's, every single time a "needs backup" call was checked during
active combat, which is exactly when a call is most likely to be genuine.
The marker split then finds no `" needs backup"` in a drone status string
and answers `Nothing`, silently, on every reading -- confirmed live on
saxrat run 20, where Martha's banner and a fresh history entry were both
present and `respondToFleetBackupBroadcast` never printed a line at all.
`Nothing` for an absent fleet window, not a crash -- there is nothing to
search.
-}
fleetWindowDescendants : ReadingFromGameClient -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
fleetWindowDescendants readingFromGameClient =
    readingFromGameClient.fleetWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []


{-| The banner naming the client's most recent fleet broadcast.

Found by the `_name` the client gives it rather than by position, because the
banner sits four containers deep and every one of those is a `Container` that
carries no other identity. Scoped to the fleet window -- see
`fleetWindowDescendants`.

-}
fleetBroadcastBannerText : ReadingFromGameClient -> Maybe String
fleetBroadcastBannerText readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "bannerLabel")
            )
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.head


{-| Who broadcast a travel destination, and where to.

**The banner persists**, which is the whole difficulty and is observed rather
than assumed: it was still reading `Gal Bistot: Travel to Riramia` when the tree
was read again long after that broadcast. It is a _last broadcast_ display, not
a transient. So this answers what the banner currently says and nothing about
when it was said, and the caller is what makes it fire once -- see
`fleetBroadcastToFollow`.

**Matched exactly against the permitted list, never as a substring**, for
`fleetInvitationToAccept`'s reason: this hands a pilot the ship's destination.

-}
fleetTravelBroadcast : List String -> ReadingFromGameClient -> Maybe { pilot : String, system : String, banner : String }
fleetTravelBroadcast permittedPilots readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen
            (\banner ->
                case String.indexes fleetTravelBroadcastMarker banner of
                    [] ->
                        Nothing

                    index :: _ ->
                        let
                            pilot =
                                banner |> String.left index |> String.trim

                            system =
                                banner
                                    |> String.dropLeft
                                        (index + String.length fleetTravelBroadcastMarker)
                                    |> String.trim
                        in
                        if String.isEmpty pilot || String.isEmpty system then
                            Nothing

                        else if
                            permittedPilots
                                |> List.any
                                    (\permitted ->
                                        String.toLower (String.trim permitted) == String.toLower pilot
                                    )
                        then
                            Just { pilot = pilot, system = system, banner = banner }

                        else
                            Nothing
            )


{-| The broadcast this reading should act on, if any.

**The latch is the whole of it.** The banner does not go away, so a rule that
merely read it would re-ask for the same destination on every reading for the
rest of the session and fight `setRouteToNextHuntingGround` for the ship. The
verdict is recorded in `BotMemory.fleetBroadcastFollowed` -- the banner's own
text -- and a banner that has already been acted on answers `Nothing`.

Keying on the text rather than on a counter means a _repeated_ broadcast to the
same system is correctly ignored, since it renders identically and the ship is
already going there, while a broadcast to somewhere else is a different string
and fires. That is `messageBoxIdentity`'s choice for `messageBoxIdentity`'s
reason.

-}
fleetBroadcastToFollow : BotDecisionContext -> Maybe { pilot : String, system : String, banner : String }
fleetBroadcastToFollow context =
    fleetTravelBroadcast
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.readingFromGameClient
        |> Maybe.andThen
            (\broadcast ->
                if context.memory.fleetBroadcastFollowed == Just broadcast.banner then
                    Nothing

                else
                    Just broadcast
            )


{-| Ask the host to route to a destination a fleet-mate broadcast.

Placed above the hunt circuit and below the retreats and the setup list, so a
person's broadcast outranks the bot's own idea of where to go while a lost ship,
a message box and a pod recovery all still outrank the broadcast.

It asks once per distinct broadcast and hands the reading back, because the
route it produces is travelled by `jumpToNextSystem`, which already exists. It
owns no clock, no counter and no second travel path.

-}
followFleetBroadcast : BotDecisionContext -> Maybe DecisionPathNode
followFleetBroadcast context =
    fleetBroadcastToFollow context
        |> Maybe.map
            (\broadcast ->
                describeBranch
                    ("'"
                        ++ broadcast.pilot
                        ++ "' broadcast a travel destination and is named in "
                        ++ "'follow-fleet-broadcast-from' -- asking the host to set "
                        ++ "the route to '"
                        ++ broadcast.system
                        ++ "'. "
                        ++ hostDirectiveSetDestination broadcast.system
                    )
                    waitForProgressInGame
            )


{-| The client's own words for a fleet "needs backup" broadcast, read off a
live one.

Captured live: `"Martha Mercoxit needs backup"` on the persistent banner and
`"15:16:16 - Martha Mercoxit needs backup"` on the broadcast-history panel's
own entry for it. **No colon**, unlike the travel broadcast's
`"Gal Bistot: Travel to Riramia"` -- this is a suffix marker, not an infix one,
and the pilot's name is everything before it.

-}
fleetBackupBroadcastMarker : String
fleetBackupBroadcastMarker =
    " needs backup"


{-| The most recent entry in the fleet window's broadcast-history panel, if
that panel happens to be showing.

Read the same way `fleetBroadcastBannerText` reads the persistent banner --
filter by the `_name` the client gives the text node, take the first, scoped
to the fleet window (`fleetWindowDescendants`). Captured live:
`TextBody name='entryLabel' text='15:16:16 - Martha Mercoxit needs
backup'`, one child deep inside a `BroadcastEntry` inside the
`BroadcastHistoryPanel`. **The scoping is load-bearing, not tidiness** -- see
`fleetWindowDescendants`'s own comment for the confirmed live collision with
the drones window's identically-named rows.

**Unverified: entry order when more than one broadcast has fired.** Only one
entry was ever live when this was written, so this takes the tree's own list
order and cannot say whether that is newest-first. It is only ever used to
tell two _different_ calls apart from each other (see
`fleetLastBroadcastText`), and picking the wrong one of several stacked
entries would at worst let one repeat go unanswered rather than mis-identify
the pilot, since the marker split still runs on whichever text this returns.

-}
fleetBroadcastHistoryEntryText : ReadingFromGameClient -> Maybe String
fleetBroadcastHistoryEntryText readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "entryLabel")
            )
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.head


{-| The string a "needs backup" call is identified by, for the latch in
`fleetBackupBroadcastFollowed` and, since it names no broadcast type of its
own, reused identically by `fleetAtLocationBroadcast` below.

**Why this differs from the travel broadcast's plain banner text.** The banner
is a _last broadcast_ display with no timestamp, so a second, later call for
help from the same pilot renders identically to the first and would read as
"already handled" under the travel broadcast's own latch shape -- fine there,
since a repeated identical travel broadcast really is redundant (the ship is
already going there), and wrong here, since a second cry for help is not the
same event as the first. The history panel's own entry carries a timestamp, so
it is used as the identity whenever that panel is showing; the plain banner is
the fallback when it is not, which accepts the travel broadcast's own
limitation rather than requiring an operator to keep a particular fleet-window
tab open.

**One history panel, one entry, whatever the type.** The panel interleaves
every broadcast type in one timestamped list, so `List.head` here is simply
"whatever the last broadcast was" -- a backup call and an at-location call
each look for their own marker in it and correctly find nothing when the top
entry is the other type, which is what lets an operator's later broadcast of
either kind supersede an earlier one of the other without either detector
needing to know the other exists.

-}
fleetLastBroadcastText : ReadingFromGameClient -> Maybe String
fleetLastBroadcastText readingFromGameClient =
    case fleetBroadcastHistoryEntryText readingFromGameClient of
        Just historyEntry ->
            Just historyEntry

        Nothing ->
            fleetBroadcastBannerText readingFromGameClient


{-| Who is calling for backup, and the text identifying this particular call.

**Matched exactly against the permitted list, never as a substring**, for
`fleetTravelBroadcast`'s reason: this hands a pilot the ship's own warp.

-}
fleetNeedsBackupBroadcast : List String -> ReadingFromGameClient -> Maybe { pilot : String, identity : String }
fleetNeedsBackupBroadcast permittedPilots readingFromGameClient =
    fleetLastBroadcastText readingFromGameClient
        |> Maybe.andThen
            (\identity ->
                case String.indexes fleetBackupBroadcastMarker identity of
                    [] ->
                        Nothing

                    index :: _ ->
                        let
                            -- The history entry carries a leading "HH:MM:SS - "
                            -- the banner does not; splitting from the *end* on
                            -- the marker's own index, rather than assuming a
                            -- fixed prefix, reads the pilot's name correctly out
                            -- of either shape.
                            pilot =
                                identity |> String.left index |> String.trim

                            pilotFromEitherShape =
                                case String.split " - " pilot of
                                    [ _, afterDash ] ->
                                        afterDash

                                    _ ->
                                        pilot
                        in
                        if String.isEmpty pilotFromEitherShape then
                            Nothing

                        else if
                            permittedPilots
                                |> List.any
                                    (\permitted ->
                                        String.toLower (String.trim permitted) == String.toLower pilotFromEitherShape
                                    )
                        then
                            Just { pilot = pilotFromEitherShape, identity = identity }

                        else
                            Nothing
            )


{-| The client's own words for a fleet "at location" broadcast, read off a
live one.

Captured live: `"Martha Mercoxit is at location Toshabia"` on the persistent
banner and `"17:36:53 - Martha Mercoxit is at location Toshabia"` on the
broadcast-history panel's own entry -- an **infix** marker, like the travel
broadcast's `": Travel to "`, with the pilot's name before it and a real
solar-system name after it. Unlike the "needs backup" call, this one names
somewhere navigable, which is what lets `respondToFleetAtLocationBroadcast`
route toward it through the same reliable ESI directive
`followFleetBroadcast` already uses, rather than through a client-side click
that a "needs backup" call proved the client will refuse outright.

-}
fleetAtLocationBroadcastMarker : String
fleetAtLocationBroadcastMarker =
    " is at location "


{-| Who broadcast being at a location, where, and the text identifying this
particular call.

Reads the same shared last-broadcast text `fleetNeedsBackupBroadcast` does
(`fleetLastBroadcastText`) and looks for its own marker in it, so an
operator's later broadcast of either kind supersedes an earlier one of the
other -- see `fleetLastBroadcastText`'s own comment. **Matched exactly
against the permitted list, never as a substring**, for `fleetTravelBroadcast`'s
reason: this hands a pilot the ship's own warp or its route.

-}
fleetAtLocationBroadcast : List String -> ReadingFromGameClient -> Maybe { pilot : String, system : String, identity : String }
fleetAtLocationBroadcast permittedPilots readingFromGameClient =
    fleetLastBroadcastText readingFromGameClient
        |> Maybe.andThen
            (\identity ->
                case String.indexes fleetAtLocationBroadcastMarker identity of
                    [] ->
                        Nothing

                    index :: _ ->
                        let
                            beforeMarker =
                                identity |> String.left index |> String.trim

                            pilotFromEitherShape =
                                case String.split " - " beforeMarker of
                                    [ _, afterDash ] ->
                                        afterDash

                                    _ ->
                                        beforeMarker

                            system =
                                identity
                                    |> String.dropLeft (index + String.length fleetAtLocationBroadcastMarker)
                                    |> String.trim
                        in
                        if String.isEmpty pilotFromEitherShape || String.isEmpty system then
                            Nothing

                        else if
                            permittedPilots
                                |> List.any
                                    (\permitted ->
                                        String.toLower (String.trim permitted) == String.toLower pilotFromEitherShape
                                    )
                        then
                            Just { pilot = pilotFromEitherShape, system = system, identity = identity }

                        else
                            Nothing
            )


{-| The broadcast banner as a clickable element, for right-clicking it
directly. **Confirmed live**: right-clicking this exact node (the same one
`fleetBroadcastBannerText` reads for its text) opens a context menu offering
`Set Destination`, `Add Waypoint`, a `Fleet Member` submenu (`Warp to Member`,
`Warp to Member Within`, `Show Info`, `Add to Watch List`), and `Ignore this
type of broadcast` -- no fleet-member roster window needs to be open. Scoped
to the fleet window -- see `fleetWindowDescendants`.
-}
fleetBroadcastBannerElement : ReadingFromGameClient -> Maybe UIElement
fleetBroadcastBannerElement readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "bannerLabel")
            )
        |> List.head


{-| Whether a pilot is currently in this solar system, read off local chat.

Local chat lists everyone in the system by definition, so this is the same
`localChatWindowFromUserInterface |> .userlist |> .visibleUsers` read
`getNamesOfOtherPilotsInOverview` already does (`Bot.elm` -- see "Strings and
identities read off a live client" in `CLAUDE.md`), just without that
function's own fleetmate exclusion: that function wants _other_ pilots, this
one wants to find a specific fleetmate.

-}
pilotIsInLocalChat : String -> ReadingFromGameClient -> Bool
pilotIsInLocalChat pilotName readingFromGameClient =
    readingFromGameClient
        |> localChatWindowFromUserInterface
        |> Maybe.andThen .userlist
        |> Maybe.map .visibleUsers
        |> Maybe.withDefault []
        |> List.filterMap .name
        |> List.any (\name -> String.toLower (String.trim name) == String.toLower (String.trim pilotName))


{-| Warp to a fleet-mate who broadcast "needs backup", when the ship is
already in her system.

**Placed above `followFleetBroadcast`**: an emergency call outranks a routine
travel broadcast if both are pending. Below the retreats, the pod recovery and
the setup list, same as the travel broadcast -- a lost ship or a stuck menu
still outranks going to someone else's fight.

**Only the in-system case is handled at all**, and that narrowing is load
-bearing rather than an oversight. The first version also tried to route
toward a caller who was _not_ yet in this system, right-clicking the banner
and taking "Set Destination" -- confirmed live to be offered on this exact
broadcast type. What live running then showed is that the client refuses to
act on it: saxrat run 16 clicked it every reading for twelve straight minutes
and the game log answered `You can't set that as a waypoint` every single
time, without exception. That is EVE's own refusal to compute an autopilot
route to a fleet member's live in-space position -- unlike a travel
broadcast, which names a real system and which the client happily routes
to, a "needs backup" call carries no navigable destination at all. No amount
of retrying, and no different latch shape, was going to make that click land;
the earlier two-reading-lag version merely hid the failure by giving up
after one attempt, and the fix to _that_ (retry until the client confirms it
worked) turned a quiet non-event into a loud, useless spam loop instead. Both
are downstream of the same wrong premise, so the premise -- not the retry
policy -- is what changed.

So this now does the one thing that is actually observed working: when the
caller is **already in this system**, right-click the banner, `Fleet Member`
then `Warp to Member` (exact text at both steps -- `"Warp to Member"` is a
substring of `"Warp to Member Within"`, confirmed live in the same menu),
re-issued every reading exactly like `jumpToNextSystem`'s own cascade until
the client shows the ship actually warping -- that is what latches
`fleetBackupBroadcastFollowed`, not a click count. Idempotent by the same
argument the file already makes for its other repeated cascades: a
right-click that finds no menu yet waits, one that finds a stale menu
discards and reopens, and clicking "Warp to Member" again before the first
has landed simply repeats the same command.

**A caller who is not in this system gets nothing from this branch at all**
-- `Nothing`, falling through to ordinary hunting, exactly as if the call had
never been seen. That is a real capability gap, stated rather than hidden:
there is currently no verified way for this bot to travel toward a "needs
backup" caller across systems. The fleet window's per-member location column,
if the client renders one, would be the way to learn a real system name and
hand it to the same `@host set-destination` mechanism `followFleetBroadcast`
already uses reliably -- but that is unread and unverified, and belongs in a
follow-up built against a live client rather than guessed at again here.

-}
respondToFleetBackupBroadcast : BotDecisionContext -> Maybe DecisionPathNode
respondToFleetBackupBroadcast context =
    fleetNeedsBackupBroadcast
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.readingFromGameClient
        |> Maybe.andThen
            (\backup ->
                if context.memory.fleetBackupBroadcastFollowed == Just backup.identity then
                    Nothing

                else
                    Just backup
            )
        |> Maybe.andThen
            (\backup ->
                if pilotIsInLocalChat backup.pilot context.readingFromGameClient then
                    fleetBroadcastBannerElement context.readingFromGameClient
                        |> Maybe.map
                            (\bannerElement ->
                                describeBranch
                                    ("'"
                                        ++ backup.pilot
                                        ++ "' broadcast needing backup and is in this system -- recall drones and warp to them."
                                    )
                                    (ensureDronesRecalledBeforeWarping context
                                        (useContextMenuCascade
                                            ( "fleet broadcast", bannerElement )
                                            (useMenuEntryWithTextEqual "Fleet Member"
                                                (useMenuEntryWithTextEqual "Warp to Member" menuCascadeCompleted)
                                            )
                                            context
                                        )
                                    )
                            )

                else
                    Nothing
            )


{-| Warp to a fleet-mate who broadcast being at a location, or ask the host
to route there.

**Placed beside `respondToFleetBackupBroadcast`, same tier**: both outrank
the routine travel broadcast and the anomaly grid, both are outranked by the
retreats, the pod recovery and the setup list. Which of the two wins when
both are pending is decided by which the client currently shows as the last
broadcast (`fleetLastBroadcastText`) -- there is only one banner, so only one
of them can ever answer `Just` on a given reading.

Two states, mirroring `followFleetBroadcast` and `respondToFleetBackupBroadcast`
respectively rather than inventing a third shape:

  - **In this system** -- the same "Fleet Member" -> "Warp to Member" cascade
    `respondToFleetBackupBroadcast` uses, re-issued every reading and
    credited only once a _previous_ reading saw her in system with this ship
    standing still (`fleetAtLocationInSystemStanding`), for the identical
    reason given there.
  - **Not in this system** -- unlike a "needs backup" call, this broadcast
    names a real solar system (confirmed live: `"<pilot> is at location
    <system>"`), so this asks the host to route there through the same
    reliable `@host set-destination` directive `followFleetBroadcast` already
    uses, rather than repeating the click-based mistake that broadcast type
    proved the client refuses. Latches `fleetAtLocationDestinationAsked` on
    the second sighting and hands the reading back to ordinary travel for the
    rest of the trip -- this owns no second travel path. That latch does
    **not** stop the in-system branch above from firing once she is actually
    reached; the two track separately (`fleetAtLocationBroadcastFollowed` vs
    `fleetAtLocationDestinationAsked`) for exactly that reason.

-}
respondToFleetAtLocationBroadcast : BotDecisionContext -> Maybe DecisionPathNode
respondToFleetAtLocationBroadcast context =
    fleetAtLocationBroadcast
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.readingFromGameClient
        |> Maybe.andThen
            (\call ->
                if context.memory.fleetAtLocationBroadcastFollowed == Just call.identity then
                    Nothing

                else
                    Just call
            )
        |> Maybe.andThen
            (\call ->
                if pilotIsInLocalChat call.pilot context.readingFromGameClient then
                    fleetBroadcastBannerElement context.readingFromGameClient
                        |> Maybe.map
                            (\bannerElement ->
                                describeBranch
                                    ("'"
                                        ++ call.pilot
                                        ++ "' broadcast being at location '"
                                        ++ call.system
                                        ++ "' and is in this system -- recall drones and warp to them."
                                    )
                                    (ensureDronesRecalledBeforeWarping context
                                        (useContextMenuCascade
                                            ( "fleet broadcast", bannerElement )
                                            (useMenuEntryWithTextEqual "Fleet Member"
                                                (useMenuEntryWithTextEqual "Warp to Member" menuCascadeCompleted)
                                            )
                                            context
                                        )
                                    )
                            )

                else if context.memory.fleetAtLocationDestinationAsked == Just call.identity then
                    Nothing

                else
                    Just
                        (describeBranch
                            ("'"
                                ++ call.pilot
                                ++ "' broadcast being at location '"
                                ++ call.system
                                ++ "' and is not in this system -- asking the host to set the route to '"
                                ++ call.system
                                ++ "'. "
                                ++ hostDirectiveSetDestination call.system
                            )
                            waitForProgressInGame
                        )
            )


{-| The client's own broadcast verbs, all of them, read off a live client
rather than written from the English.

Eight sit on the fleet window as buttons and the rest on an object's context
menu, and the two need different mechanisms -- see
`fleetBroadcastVerbMechanism`. Only four are ever sent
(`fleetBroadcastVerbsSent`). The rest are defined and unsent on purpose: what
the client calls a verb is the half that cannot be re-derived from this source,
and sending one more should be an entry added to a list rather than another
capture session against somebody's live client.

**Six of the eight buttons carry `_elementId = fleetwindow.<lambda>`**, which
is not an identifier -- so matching a button on `_elementId` silently maps six
of them to one name, and the match has to be on `_hint`. Their positions are
36px apart and shift when the set changes, so no indexing either. See
`fleetWindowBroadcastButton`.

**`Broadcast: Jump to` has a lowercase `to`.** A matcher written from the
English would have got that wrong and failed in this repo's usual direction:
nothing matches, the branch never fires, and nothing complains.

Two entries a stargate's menu also offers are deliberately **not** here.
`Warp Fleet (Point)` and `Warp Fleet (Point) to Within` are not broadcasts at
all -- they move other players' ships rather than telling them where to go,
which is a materially different thing to hand a bot, and it is not what this
setting is for.

Captured 2026-08-19 for issue #417: the eight buttons off the fleet window,
three verbs off a stargate's context menu, and two off a `Centii Minion`'s.

-}
type FleetBroadcastVerb
    = BroadcastNeedBackup
    | BroadcastJumpTo
    | BroadcastAtLocation
    | BroadcastTarget
    | BroadcastInPositionAt
    | BroadcastSpottedAnEnemy
    | BroadcastNeedArmor
    | BroadcastNeedShield
    | BroadcastNeedCapacitor
    | BroadcastHoldPosition
    | BroadcastWarpTo
    | BroadcastAlignTo
    | BroadcastRepairTarget


{-| What the client writes for each verb: the button's `_hint` on the fleet
window, the entry's own text on an object's menu.
-}
fleetBroadcastVerbText : FleetBroadcastVerb -> String
fleetBroadcastVerbText verb =
    case verb of
        BroadcastNeedBackup ->
            "Broadcast: Need Backup"

        BroadcastJumpTo ->
            "Broadcast: Jump to"

        BroadcastAtLocation ->
            "Broadcast: At Location"

        BroadcastTarget ->
            "Broadcast: Target"

        BroadcastInPositionAt ->
            "Broadcast: In Position at"

        BroadcastSpottedAnEnemy ->
            "Broadcast: Spotted an Enemy"

        BroadcastNeedArmor ->
            "Broadcast: Need Armor"

        BroadcastNeedShield ->
            "Broadcast: Need Shield"

        BroadcastNeedCapacitor ->
            "Broadcast: Need Capacitor"

        BroadcastHoldPosition ->
            "Broadcast: Request That the Fleet Hold Position"

        BroadcastWarpTo ->
            "Broadcast: Warp to"

        BroadcastAlignTo ->
            "Broadcast: Align to"

        BroadcastRepairTarget ->
            "Broadcast: Repair Target"


{-| Which of the two things this verb is: a button on the fleet window, or an
entry on the menu of the object the call is about.

The split is not cosmetic. A fleet-window button is a single click and says
something about this ship; an object menu entry is a multi-reading cascade and
says something about a particular object, which first has to be the one the
Selected Item panel is showing.

-}
type FleetBroadcastMechanism
    = FleetWindowButton
    | SelectedItemMenu


fleetBroadcastVerbMechanism : FleetBroadcastVerb -> FleetBroadcastMechanism
fleetBroadcastVerbMechanism verb =
    case verb of
        BroadcastJumpTo ->
            SelectedItemMenu

        BroadcastTarget ->
            SelectedItemMenu

        BroadcastWarpTo ->
            SelectedItemMenu

        BroadcastAlignTo ->
            SelectedItemMenu

        BroadcastRepairTarget ->
            SelectedItemMenu

        _ ->
            FleetWindowButton


{-| The four this bot sends, and the list nothing else may grow past.

Everything outside it is defined and never sent. `fleetBroadcastCall` is what
actually decides -- this list is the same claim written where it can be read and
executed, so "which verbs does this bot send" has one answer rather than four
scattered warrant functions to be counted by hand.

-}
fleetBroadcastVerbsSent : List FleetBroadcastVerb
fleetBroadcastVerbsSent =
    [ BroadcastNeedBackup
    , BroadcastJumpTo
    , BroadcastAtLocation
    , BroadcastTarget
    ]


{-| One call: the verb to send, what identifies it, and what the client's own
banner has to say for it to count as sent.

`identity` is the de-duplication key and the status text, so a call that is
genuinely a new thing to say -- a different gate, a different primary, a
different site -- reads as a different identity, and one that is the same thing
said twice reads as the same.

`bannerMustContain` is the confirmation. The banner carries the exact text of
the last broadcast the client rendered, so success is read back rather than
assumed from having dispatched a click.

-}
type alias FleetBroadcastCall =
    { verb : FleetBroadcastVerb
    , identity : String
    , bannerMustContain : List String
    }


{-| The one call this reading warrants, if any -- and nothing about whether the
bot is allowed to send it.

**Every warrant is a fact the client has reported, never an intention.** A jump
is warranted by the client's own panel offering to jump that gate, a target call
by the client marking a row as this ship's active target, an at-location call by
the client showing a lock with rats on the overview, and a backup call by the
combat log plus the client reporting the ship already in warp. Nothing here asks
what the decision tree is about to do, which is the whole of the issue's
"a fleet told 'in position' by a ship still aligning is being misled".

Ordered rather than filtered, because only one call can be in flight: the ship's
own emergency first, then the gate the fleet has to follow through, then arrival,
then the primary. A reading warrants at most one thing to say.

Free of the `fleet-commander` gate on purpose -- `fleetBroadcastStep` is where
that lives, so there is one gate rather than four.

-}
fleetBroadcastCall :
    { incomingDamagePastTheThreshold : Bool }
    -> ReadingFromGameClient
    -> Maybe FleetBroadcastCall
fleetBroadcastCall situation readingFromGameClient =
    [ fleetNeedBackupCall situation readingFromGameClient
    , fleetJumpToCall readingFromGameClient
    , fleetAtLocationCall readingFromGameClient
    , fleetTargetCall readingFromGameClient
    ]
        |> List.filterMap identity
        |> List.head


{-| Backup, from the retreat's own armed signal and from the ship being in warp.

Both halves are the client speaking. The first is the combat log summed over
`incomingDamageWindowSeconds` past `run-away-incoming-damage-threshold`, which is
the one retreat guard saxrat ships armed; the second is the ship UI reporting a
warp or a jump.

**The warp half is what makes this cost the retreat nothing**, and it is why this
is the only call sent from inside the retreat's own branch (see
`runAwayAndTellTheFleet`). On a reading where the ship is already in warp,
`runAway`'s own action is a warp command re-issued at a ship that is already
warping; spending that reading on one click of a fleet-window button takes
nothing away from getting out. Firing on the damage alone would have put a click
in front of the warp that saves the ship, which is not a trade a broadcast gets
to make.

-}
fleetNeedBackupCall :
    { incomingDamagePastTheThreshold : Bool }
    -> ReadingFromGameClient
    -> Maybe FleetBroadcastCall
fleetNeedBackupCall situation readingFromGameClient =
    if not situation.incomingDamagePastTheThreshold then
        Nothing

    else if not (shipIsWarpingOrJumping readingFromGameClient) then
        Nothing

    else
        Just
            { verb = BroadcastNeedBackup
            , identity =
                "Need Backup leaving "
                    ++ (currentSolarSystemNameFromReading readingFromGameClient
                            |> Maybe.withDefault "an unnamed system"
                       )
            , bannerMustContain = [ fleetBackupBroadcastMarker ]
            }


{-| The gate call, from the same verdict that presses the Jump button.

`routeStargateJumpFromReading` answering `PressTheJumpButton` means the client's
Selected Item panel is showing the stargate the route names for the next system
_and_ offering its own Jump for it -- so the ship is at that gate and can take
it now. That is a fact about where the ship is, not a plan, and it is the same
declaration `jumpThroughRouteStargate` decides on, so the broadcast and the jump
cannot come to disagree about which gate is being taken.

Two further conditions narrow it to the readings the jump path actually runs on.
A ship in warp is not at a gate whatever the panel is showing, and a fight
underway means the panel is showing something left over rather than the next leg
of a trip. Without them this arm sits above the fight in the decision tree and
could take a reading from it on the strength of a stale panel.

**The gate's own name is the confirmation.** The wording the client wraps a
`Broadcast: Jump to` in was not captured -- only the menu entry was -- so this
claims the least it can claim and no more: the banner has to name the gate this
call is about, and to have changed since the call started. Where a measured
wording exists (`fleetBackupBroadcastMarker`, `fleetAtLocationBroadcastMarker`)
that wording is what the call asks for instead.

-}
fleetJumpToCall : ReadingFromGameClient -> Maybe FleetBroadcastCall
fleetJumpToCall readingFromGameClient =
    if shipIsWarpingOrJumping readingFromGameClient then
        Nothing

    else if combatFightIsUnderway readingFromGameClient then
        Nothing

    else
        case routeStargateJumpFromReading readingFromGameClient of
            PressTheJumpButton gateName ->
                Just
                    { verb = BroadcastJumpTo
                    , identity = "Jump to '" ++ gateName ++ "'"
                    , bannerMustContain = [ gateName ]
                    }

            _ ->
                Nothing


{-| Arrival, from the client reporting the ship engaged rather than on its way.

`combatFightIsUnderway` is the client holding a lock _and_ drawing rats on the
overview -- a lock the client reports, which is the issue's own example of the
right signal. A ship still aligning, still warping, or still deciding has
neither.

The site is part of the identity, so the next anomaly gets its own call and the
one the ship is standing in does not get a second. Where the probe scanner names
no site -- a deadspace pocket behind an acceleration gate -- the system alone is
the identity, which means one call for the whole system rather than one per
pocket. That is the quiet direction, and it is the one to fail in.

-}
fleetAtLocationCall : ReadingFromGameClient -> Maybe FleetBroadcastCall
fleetAtLocationCall readingFromGameClient =
    if not (combatFightIsUnderway readingFromGameClient) then
        Nothing

    else
        Just
            { verb = BroadcastAtLocation
            , identity =
                "At Location in "
                    ++ (currentSolarSystemNameFromReading readingFromGameClient
                            |> Maybe.withDefault "an unnamed system"
                       )
                    ++ (getCurrentAnomalyIDAsSeenInProbeScanner readingFromGameClient
                            |> Maybe.map (\anomalyID -> ", site " ++ anomalyID)
                            |> Maybe.withDefault ", no site on the scanner"
                       )
            , bannerMustContain = [ fleetAtLocationBroadcastMarker ]
            }


{-| The target call, about the row the client itself marks as active.

**Nothing here picks a rat by name**, which is #413's problem and the reason the
row is taken from `myActiveTargetIndicator` instead: a rat's overview row carries
its name three times over, so two rats of one type are indistinguishable by name
and a name match against rows is not selective. The client knows which object
this ship's guns are pointed at, and that is the one the fleet is being told
about.

-}
fleetTargetCall : ReadingFromGameClient -> Maybe FleetBroadcastCall
fleetTargetCall readingFromGameClient =
    ratToCallAsTarget readingFromGameClient
        |> Maybe.andThen .objectName
        |> Maybe.map
            (\name ->
                { verb = BroadcastTarget
                , identity = "Target '" ++ name ++ "'"

                -- `Target Centii Minion (Centii Minion)` is what the banner
                -- read back live, so both halves are asserted: the verb the
                -- client renders and the object it named.
                , bannerMustContain = [ "Target", name ]
                }
            )


{-| The one row a target call may be made about, or nothing.

Four filters and every one of them is about not calling the wrong thing.

**A row that is not `_display`ed is not clicked**, this file's standing rule: a
virtualised row keeps the region of whatever was recycled into its place.

**The active target is the client's answer to "which object", not this bot's.**

**A fleet-mate is excluded before anything is clicked, and so is every other
pilot.** The fleet's own ships are on this overview -- `Imperial Navy Slicer`
rows sat beside the rats in the capture this was written from -- and a target
call on one of them is a fleet told to shoot a friendly. The exclusion is the
membership reading saxrat already has, used the other way round: Local lists
every pilot in the system by name and a rat never appears there, so a row whose
name is in Local is a player. `chatUserIsKnownFleetmate` is what proves the
fleet's own ships are in that list; this filter does not need the hint, because
it excludes every pilot rather than only the fleet's.

**A row with no name is excluded**, since absent evidence must not read as
"harmless rat" -- the direction this has to fail in.

-}
ratToCallAsTarget : ReadingFromGameClient -> Maybe OverviewWindowEntry
ratToCallAsTarget readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter overviewEntryIsActiveTarget
        |> List.filter iconSpriteHasColorOfRat
        |> List.filter (overviewEntryIsAPilot readingFromGameClient >> not)
        |> List.head


{-| Every pilot Local is showing, fleet-mates included.

`getNamesOfOtherPilotsInOverview` drops fleet-mates on purpose -- it is looking
for strangers in an anomaly. This one wants the whole list, because what it
feeds is a guard against clicking a _player's_ row, and a fleet-mate's row is
the most dangerous one of all.

-}
pilotNamesInLocalChat : ReadingFromGameClient -> List String
pilotNamesInLocalChat readingFromGameClient =
    readingFromGameClient
        |> localChatWindowFromUserInterface
        |> Maybe.andThen .userlist
        |> Maybe.map .visibleUsers
        |> Maybe.withDefault []
        |> List.filterMap .name


{-| Whether this overview row is a player rather than a rat.

A row with no name answers `True`: absent evidence is a pilot here, since the
cost of being wrong is a target call broadcast on a fleet-mate.

-}
overviewEntryIsAPilot : ReadingFromGameClient -> OverviewWindowEntry -> Bool
overviewEntryIsAPilot readingFromGameClient entry =
    case entry.objectName of
        Nothing ->
            True

        Just name ->
            pilotNamesInLocalChat readingFromGameClient
                |> List.any
                    (\pilot ->
                        String.toLower (String.trim pilot) == String.toLower (String.trim name)
                    )


{-| How many readings one call gets before the bot stops trying to send it.

Sized on the mechanism rather than on taste. A fleet-window button is one click
and reads back on the next reading or two; an object menu is a real cascade, and
`readingsToWaitForAFirstContextMenu` alone is 10, because a freshly opened menu
reads back as no menu at all while it renders. So a cascade that is behaving
normally can legitimately spend a dozen readings, and a bound under that would
give up on menus that were about to work.

Past it the arm hands the reading back -- see `describeFleetBroadcastGaveUp`,
which is a status clause rather than a decision line for exactly the reason
`describeGateGaveUp` is.

-}
fleetBroadcastGiveUpReadings : Int
fleetBroadcastGiveUpReadings =
    20


{-| How many calls one session may confirm, as a backstop under the
de-duplication rather than instead of it.

Nothing plausible reaches this: a call is sent once per gate, per site and per
primary, and a long session takes tens of gates. What it bounds is the shape
this file has shipped three times -- a rule that turns out to fire on every
reading -- with real people on the other end of it.

-}
fleetBroadcastsPerSession : Int
fleetBroadcastsPerSession =
    100


{-| How many confirmed calls are remembered, which is what de-duplication costs.

A call that has fallen out of this list can be sent again. Sixteen is more than
one grid's worth of primaries, so what falls out is a gate or a site the ship
left long ago -- and re-announcing a site the fleet has come back to is a
sentence the fleet wants rather than spam. An unbounded list would be a session's
worth of strings held for the sake of never repeating anything, which is the
wrong side of the trade.

-}
fleetBroadcastsRemembered : Int
fleetBroadcastsRemembered =
    16


{-| What this ship has told the fleet, and what it is in the middle of telling.

`broadcast` is the de-duplication: an identity in it has been read back off the
client's own banner and is never sent again while it is remembered.
`asking`/`askedReadings` are the bound, and `bannerWhenAsked` is what stops a
fleet-mate's older broadcast being mistaken for this ship's own -- the banner
never clears, so "it contains our marker" is not by itself evidence that our
call is what put it there.

-}
type alias FleetBroadcastMemory =
    { asking : Maybe String
    , askedReadings : Int
    , bannerWhenAsked : Maybe String
    , broadcast : List String
    , sent : Int
    , givenUp : Int
    , lastChange : Maybe String
    }


initFleetBroadcastMemory : FleetBroadcastMemory
initFleetBroadcastMemory =
    { asking = Nothing
    , askedReadings = 0
    , bannerWhenAsked = Nothing
    , broadcast = []
    , sent = 0
    , givenUp = 0
    , lastChange = Nothing
    }


{-| What to do about broadcasting on this reading.

A pure function over a small record, with three readers -- the memory update
that advances the counters, the arm that sends, and the status clause that says
what is happening -- so a broadcast decided in one place and reported in another
cannot be two places that disagree.

**This is where `fleet-commander` is gated, and it is the only place.** Every
arm reaches the client through this one answer, so the setting cannot be
half-honoured by an arm that forgot to ask.

The order of the clauses is load-bearing. A call already broadcast is dropped
before anything else looks at it, so the banner persisting cannot re-send it. A
confirmation is taken before the give-up, so a call the banner reads back on the
very last reading still latches instead of being recorded as abandoned. And the
session cap sits below the confirmation for the same reason: reaching it stops
new calls, it does not throw away one already in flight.

-}
type alias FleetBroadcastCase =
    { commanderMode : Bool
    , call : Maybe FleetBroadcastCall
    , alreadyBroadcast : Bool
    , bannerConfirmsTheCall : Bool
    , asking : Maybe String
    , askedReadings : Int
    , broadcastsSent : Int
    }


type FleetBroadcastStep
    = NoBroadcastToMake
    | RecordTheBroadcastAsSent String
    | SendTheBroadcast FleetBroadcastCall
    | GiveUpOnTheBroadcast String


fleetBroadcastStep : FleetBroadcastCase -> FleetBroadcastStep
fleetBroadcastStep broadcastCase =
    case broadcastCase.call of
        Nothing ->
            NoBroadcastToMake

        Just call ->
            if not broadcastCase.commanderMode then
                NoBroadcastToMake

            else if broadcastCase.alreadyBroadcast then
                NoBroadcastToMake

            else if
                (broadcastCase.asking == Just call.identity)
                    && broadcastCase.bannerConfirmsTheCall
            then
                RecordTheBroadcastAsSent call.identity

            else if fleetBroadcastsPerSession <= broadcastCase.broadcastsSent then
                NoBroadcastToMake

            else if fleetBroadcastGiveUpReadings < broadcastCase.askedReadings then
                GiveUpOnTheBroadcast call.identity

            else
                SendTheBroadcast call


{-| Whether this call has already gone out and been read back.
-}
fleetBroadcastAlreadyMade : Maybe FleetBroadcastCall -> FleetBroadcastMemory -> Bool
fleetBroadcastAlreadyMade call memory =
    case call of
        Nothing ->
            False

        Just theCall ->
            memory.broadcast |> List.member theCall.identity


{-| Whether the client's banner is reading this ship's own call back.

Two conditions, and the second is the one that is easy to leave out. The banner
carries whatever the _fleet_ last broadcast and it never clears, so a fleet-mate
who broadcast "is at location" an hour ago would otherwise confirm this ship's
at-location call before it was ever sent -- a latch with no broadcast behind it,
which is this repo's signature bug with the fleet as its subject. So the text has
to have changed since the ask began as well as carrying what the call is about.

A fleet-mate broadcasting the same kind of thing during the few readings one ask
is in flight would still confirm it wrongly. That is bounded rather than
eliminated: the cost is one call that does not go out, and silence is the
direction this fails in.

-}
fleetBroadcastBannerConfirms :
    { call : Maybe FleetBroadcastCall
    , bannerNow : Maybe String
    , bannerWhenAsked : Maybe String
    }
    -> Bool
fleetBroadcastBannerConfirms input =
    case ( input.call, input.bannerNow ) of
        ( Just call, Just banner ) ->
            (Just banner /= input.bannerWhenAsked)
                && (call.bannerMustContain
                        |> List.all (\marker -> stringContainsIgnoringCase marker banner)
                   )

        _ ->
            False


{-| The broadcast memory after one more reading.

Advanced in `updateMemoryForNewReadingFromGame` and nowhere else, which is this
file's placement rule for anything a bound is counted in: that is the one thing
running on every reading, so an arm that stops being reached cannot freeze the
count that is supposed to bound it.

**The counter advances only on `SendTheBroadcast`** -- the one answer that spends
a reading -- and resets whenever the call changes or there is nothing to say. It
can over-count, because a reading the arm never got (a message box, the retreat
holding the tree) still shows the same warrant and still counts. Over-counting
gives up sooner and broadcasts less, which is the direction to be wrong in.

-}
fleetBroadcastMemoryAfterReading :
    { commanderMode : Bool
    , call : Maybe FleetBroadcastCall
    , bannerNow : Maybe String
    , before : FleetBroadcastMemory
    }
    -> FleetBroadcastMemory
fleetBroadcastMemoryAfterReading input =
    let
        before : FleetBroadcastMemory
        before =
            input.before
    in
    case
        fleetBroadcastStep
            { commanderMode = input.commanderMode
            , call = input.call
            , alreadyBroadcast = fleetBroadcastAlreadyMade input.call before
            , bannerConfirmsTheCall =
                fleetBroadcastBannerConfirms
                    { call = input.call
                    , bannerNow = input.bannerNow
                    , bannerWhenAsked = before.bannerWhenAsked
                    }
            , asking = before.asking
            , askedReadings = before.askedReadings
            , broadcastsSent = before.sent
            }
    of
        NoBroadcastToMake ->
            { before
                | asking = Nothing
                , askedReadings = 0
                , bannerWhenAsked = Nothing
                , lastChange = Nothing
            }

        RecordTheBroadcastAsSent identity ->
            { before
                | asking = Nothing
                , askedReadings = 0
                , bannerWhenAsked = Nothing
                , broadcast = identity :: before.broadcast |> List.take fleetBroadcastsRemembered
                , sent = before.sent + 1
                , lastChange =
                    Just
                        ("Told the fleet: "
                            ++ identity
                            ++ ". The client's own broadcast banner read it back, which is what makes it sent rather than clicked."
                        )
            }

        GiveUpOnTheBroadcast identity ->
            let
                -- The reading the bound is crossed on, counted once. The call
                -- goes on being warranted afterwards, so this answer repeats
                -- until the state changes -- and a `givenUp` advanced on every
                -- one of those readings would be a count of readings dressed as
                -- a count of calls.
                justCrossed : Bool
                justCrossed =
                    before.askedReadings == fleetBroadcastGiveUpReadings + 1
            in
            { before
                | askedReadings = before.askedReadings + 1
                , givenUp =
                    if justCrossed then
                        before.givenUp + 1

                    else
                        before.givenUp
                , lastChange =
                    if justCrossed then
                        Just (describeFleetBroadcastGaveUp identity before.askedReadings)

                    else
                        Nothing
            }

        SendTheBroadcast call ->
            let
                sameCallAsBefore : Bool
                sameCallAsBefore =
                    before.asking == Just call.identity
            in
            { before
                | asking = Just call.identity
                , askedReadings =
                    if sameCallAsBefore then
                        before.askedReadings + 1

                    else
                        0
                , bannerWhenAsked =
                    if sameCallAsBefore then
                        before.bannerWhenAsked

                    else
                        input.bannerNow
                , lastChange = Nothing
            }


{-| The step, asked of a decision's context.

The memory it reads has already been advanced for this reading, so the arm and
the update are answering the same question about the same reading rather than
one about the last one.

-}
fleetBroadcastStepFrom : BotDecisionContext -> FleetBroadcastStep
fleetBroadcastStepFrom context =
    let
        call : Maybe FleetBroadcastCall
        call =
            fleetBroadcastCall
                { incomingDamagePastTheThreshold = context.memory.incomingDamage.retreating }
                context.readingFromGameClient
    in
    fleetBroadcastStep
        { commanderMode = context.eventContext.botSettings.fleetCommander == AppSettings.Yes
        , call = call
        , alreadyBroadcast = fleetBroadcastAlreadyMade call context.memory.fleetBroadcast
        , bannerConfirmsTheCall =
            fleetBroadcastBannerConfirms
                { call = call
                , bannerNow = fleetBroadcastBannerText context.readingFromGameClient
                , bannerWhenAsked = context.memory.fleetBroadcast.bannerWhenAsked
                }
        , asking = context.memory.fleetBroadcast.asking
        , askedReadings = context.memory.fleetBroadcast.askedReadings
        , broadcastsSent = context.memory.fleetBroadcast.sent
        }


{-| One of the eight fleet-window buttons, found by the text the client puts in
its tooltip.

`_hint` rather than `_elementId` for the reason `FleetBroadcastVerb` gives: six
of the eight have no usable id. Matched whole and ignoring case, the rule
`useMenuEntryWithTextEqual` already uses for menu entries -- a `contains` match
would let `Broadcast: Need Armor` be found by asking for `Broadcast: Need`.

Scoped to the fleet window through `fleetWindowDescendants`, which is what stops
a `_hint` elsewhere in the tree answering for one of these.

-}
fleetWindowBroadcastButton : String -> ReadingFromGameClient -> Maybe UIElement
fleetWindowBroadcastButton hint readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getHintTextFromDictEntries
                >> Maybe.map (\nodeHint -> String.toLower (String.trim nodeHint) == String.toLower hint)
                >> Maybe.withDefault False
            )
        |> List.head


{-| The row that has to be selected before the Selected Item panel's own menu is
about the right object, if it is not selected already.

**Right-clicking the panel rather than the overview row is the whole reason this
exists.** Three consecutive right-clicks on moving overview rows failed during
the capture this was written from -- the overview re-sorts between the read and
the click, which this file already records as having shot an asteroid for 290
readings -- and the panel does not re-sort, so it worked first time.

`Nothing` means the panel is already showing what the call is about. For
`BroadcastJumpTo` that is the call's own warrant, since
`routeStargateJumpFromReading` only answers `PressTheJumpButton` where the panel
is showing that gate.

-}
fleetBroadcastRowToSelect : FleetBroadcastCall -> ReadingFromGameClient -> Maybe OverviewWindowEntry
fleetBroadcastRowToSelect call readingFromGameClient =
    case call.verb of
        BroadcastTarget ->
            ratToCallAsTarget readingFromGameClient
                |> Maybe.andThen
                    (\row ->
                        if selectedItemIsOverviewEntry readingFromGameClient row then
                            Nothing

                        else
                            Just row
                    )

        _ ->
            Nothing


{-| Say the one thing this reading warrants saying, or decline the reading.

`Nothing` on every reading there is nothing to say, on every reading the setting
is off, and on every reading a call has already gone out -- so a bot without
`fleet-commander` never reaches a client through here at all.

`verbsThisSiteMaySend` is what keeps the retreat's own site from sending
anything but a backup call: see `runAwayAndTellTheFleet`.

-}
sendFleetBroadcastAsFleetCommander : List FleetBroadcastVerb -> BotDecisionContext -> Maybe DecisionPathNode
sendFleetBroadcastAsFleetCommander verbsThisSiteMaySend context =
    case fleetBroadcastStepFrom context of
        SendTheBroadcast call ->
            if not (verbsThisSiteMaySend |> List.member call.verb) then
                Nothing

            else
                let
                    describeIt : String
                    describeIt =
                        "Fleet commander: "
                            ++ fleetBroadcastVerbText call.verb
                            ++ " -- "
                            ++ call.identity
                            ++ ", "
                            ++ describeFleetBroadcastAsk context.memory.fleetBroadcast
                in
                case fleetBroadcastVerbMechanism call.verb of
                    FleetWindowButton ->
                        fleetWindowBroadcastButton (fleetBroadcastVerbText call.verb)
                            context.readingFromGameClient
                            |> Maybe.map (clickUiElement >> describeBranch describeIt)

                    SelectedItemMenu ->
                        case fleetBroadcastRowToSelect call context.readingFromGameClient of
                            Just rowToSelect ->
                                Just
                                    (describeBranch
                                        (describeIt ++ " Select it first, so the panel's own menu is about it.")
                                        (clickUiElement rowToSelect.uiNode)
                                    )

                            Nothing ->
                                context.readingFromGameClient.selectedItemWindow
                                    |> Maybe.map
                                        (\panel ->
                                            describeBranch describeIt
                                                (useContextMenuCascade
                                                    ( "the Selected Item panel", panel.uiNode )
                                                    (useMenuEntryWithTextEqual
                                                        (fleetBroadcastVerbText call.verb)
                                                        menuCascadeCompleted
                                                    )
                                                    context
                                                )
                                        )

        _ ->
            Nothing


{-| The retreat, with one thing said to the fleet on the way out.

The retreat's branch is the only place a backup call can be sent from, because
`runAwayIfLowHealth` answers `Just` for as long as `incomingDamage.retreating` is
latched and everything below it is starved for the duration -- so a backup arm
placed under the retreat would be counted, bounded, and given up on without ever
having been reached. That is a broadcast that reports success and does nothing,
which is this project's signature bug.

Only `BroadcastNeedBackup` may be sent here, and it is warranted only while the
client reports the ship already warping, so what this spends is a reading in
which `runAway` would have re-issued a warp command at a ship that is already
warping. Nothing else may preempt getting out.

-}
runAwayAndTellTheFleet : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
runAwayAndTellTheFleet context retreat =
    sendFleetBroadcastAsFleetCommander [ BroadcastNeedBackup ] context
        |> Maybe.withDefault retreat


{-| The give-up, which says what was tried and stops there.

A status clause rather than a decision line, for `describeGateGaveUp`'s reason:
the arm answers `Nothing` past the bound so the rest of the tree gets the
reading, and a `Nothing` cannot carry a decision line. Without this the only
visible trace of a broadcast that never landed would be its absence.

-}
describeFleetBroadcastGaveUp : String -> Int -> String
describeFleetBroadcastGaveUp identity askedReadings =
    "I have been trying to send the fleet broadcast '"
        ++ identity
        ++ "' for "
        ++ String.fromInt askedReadings
        ++ " readings and the client's own broadcast banner has not read it back, which is past "
        ++ String.fromInt fleetBroadcastGiveUpReadings
        ++ ". Stopping rather than sending it again, and getting on with flying the ship."


{-| Where one ask has got to, for the decision line that dispatches it.
-}
describeFleetBroadcastAsk : FleetBroadcastMemory -> String
describeFleetBroadcastAsk memory =
    "reading "
        ++ String.fromInt memory.askedReadings
        ++ " of "
        ++ String.fromInt fleetBroadcastGiveUpReadings
        ++ ", confirmed off the client's own banner before it counts as sent."


{-| The fleet-commander clause in the status line.

Off is said in two words rather than left blank, because "this bot broadcasts
nothing" is the answer an operator most often wants confirmed. Past the bound it
carries the give-up itself, which is the only place that sentence appears.

-}
describeFleetCommander : BotDecisionContext -> String
describeFleetCommander context =
    if context.eventContext.botSettings.fleetCommander /= AppSettings.Yes then
        "FC off"

    else
        let
            memory : FleetBroadcastMemory
            memory =
                context.memory.fleetBroadcast
        in
        "FC "
            ++ String.fromInt memory.sent
            ++ " sent, "
            ++ String.fromInt memory.givenUp
            ++ " given up, "
            ++ String.fromInt (List.length memory.broadcast)
            ++ " remembered"
            ++ (case fleetBroadcastStepFrom context of
                    SendTheBroadcast call ->
                        " (saying '" ++ call.identity ++ "', " ++ describeFleetBroadcastAsk memory ++ ")"

                    GiveUpOnTheBroadcast identity ->
                        " -- " ++ describeFleetBroadcastGaveUp identity memory.askedReadings

                    RecordTheBroadcastAsSent identity ->
                        " (the banner read '" ++ identity ++ "' back)"

                    NoBroadcastToMake ->
                        ""
               )


{-| How long to keep asking before concluding nobody is listening.

The ask costs one line of status text and the host acts on it only when the
name changes, so repeating it is nearly free -- but "nearly free forever" is
this repo's signature stall. A host with no ESI credentials, one running
BotLab.exe, or a system name that does not resolve will never answer, and the
bot has to go back to hunting rather than stand in space asking.

-}
routeAskGiveUpReadings : Int
routeAskGiveUpReadings =
    20


huntSystemAtIndex : BotSettings -> Int -> Maybe String
huntSystemAtIndex botSettings index =
    if List.isEmpty botSettings.huntSystemNames then
        Nothing

    else
        botSettings.huntSystemNames
            |> List.drop (modBy (List.length botSettings.huntSystemNames) index)
            |> List.head


{-| The solar system the ship is in, as the client's own panel names it.

Three places have to agree about this: the picker below skips a hunting ground
the ship is already standing in, `updateMemoryForNewReadingFromGame` names the
destination the decision will ask for, and the status line prints it. Three
copies of the same two `Maybe.andThen`s would drift, and a guard that read the
panel differently from the pointer's own advance would skip systems the
rotation never moves past.

Trimmed here because the parser does not trim it: only the older
`alt='Current Solar System'` variant does, and the branch this client takes
(`headerLabelSystemName`, observed 2024-05-26) hands the label over as the
client drew it.

-}
currentSolarSystemNameFromReading : ReadingFromGameClient -> Maybe String
currentSolarSystemNameFromReading readingFromGameClient =
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelLocationInfo
        |> Maybe.andThen .currentSolarSystemName
        |> Maybe.map String.trim


{-| Where to go next, or `Nothing` if there is nowhere left to ask for.

The circuit first, then `home-system` once every name on it has been visited.
"Visited" needs no record of its own: `huntSystemIndex` is advanced by the
memory update whenever the ship is standing in the system it points at, so a
full lap has happened exactly when the index has passed the end of the list.

-}
nextHuntingGround : BotDecisionContext -> Maybe String
nextHuntingGround context =
    nextHuntingGroundFrom context.eventContext.botSettings
        context.memory.huntSystemIndex
        context.readingFromGameClient
        context.memory.lastDockedStationNameFromInfoPanel


{-| The picker itself, over the three things it actually needs.

Split out because `updateMemoryForNewReadingFromGame` has to name the same
destination the decision will ask for, and it has the settings and the index
but no `BotDecisionContext`. Two copies of this choice would drift, and the
memory would then be counting readings against a system the bot was not asking
for.

**A hunting ground equal to the system the ship is in is skipped rather than
asked for** (#262). A destination in the current system is `Route 0 Jumps` with
no marker, which `routePanelSaysNoDestination` reads -- correctly -- as no
route, so the ask can never be satisfied and `routeAskGiveUpReadings` turns it
into `routeSettingGivenUp`, latched for the session. The lap fallback is what
makes that reachable without anything misreading: once a lap is complete this
answers `home-system` at _every_ index, and the pointer goes on advancing while
the ship stands in a system the circuit names, so a ship parked in its own
staging system asks for the system it is in on every reading.

The reading is also what keeps the two callers agreeing. The framework hands
the decision the memory this update has already written, so on the reading the
ship arrives the two are called with indices one apart -- and skipping "here"
is exactly what makes that step invisible, since the first candidate that is
not the current system is the same one from either index. Recorded in the
corpus as `Sys Hamse -> Lashkai asked 'Hamse' 1/20`.

**The station the ship last undocked from is the last rung**, below the circuit
and below `home-system`, which is the preference the operator asked for. It
needs no record of its own: `lastDockedStationNameFromInfoPanel` is already in
`BotMemory` and already read by the pod recovery. Two things about it a reader
should not have to derive. It is the most recent station the _info panel named
while docked_, which equals "where the ship undocked from" only because nothing
but a docked reading can write it -- a station passed through in space never
lands there. And it is `Nothing` for a session that began in space and has not
docked since, which is a perfectly ordinary state and simply leaves this rung
empty. The host's ESI resolver takes a station name as readily as a system name,
which is what makes a station usable as a destination at all.

**A station in the system the ship is already in is declined**, which is #262's
guard for #262's reason and is the one thing the equality above cannot do for
it: a station name is not a system name, so `Just stationName /=
currentSolarSystemName` is true of the station the ship is standing at. Asking
for that is `Route 0 Jumps` with no marker, the ask can never be satisfied, and
the give-up latches for the session.

The test is `containsWords`, the same word-boundary match #170 uses to name a
stargate's system, and **it is deliberately loose rather than an exact match.**
A false skip falls through to `tetherAtStructure`, which is what this bot did
before there was a fallback at all, so being wrong that way costs the trip home
and cannot cost a session; being wrong the other way costs the session. Anything
that tightened this into an equality would be trading the cheap failure for the
expensive one, on a comparison between two kinds of name that do not have to
agree in the first place.

`Nothing` where every candidate is the system the ship is in and nothing else is
configured, which `setRouteToNextHuntingGround` already has an answer for: there
is nowhere to ask for, so it tethers and goes on hunting whatever spawns, rather
than asking for a route the client cannot give.

-}
nextHuntingGroundFrom : BotSettings -> Int -> ReadingFromGameClient -> Maybe String -> Maybe String
nextHuntingGroundFrom botSettings huntSystemIndex readingFromGameClient lastDockedStationName =
    let
        currentSolarSystemName =
            currentSolarSystemNameFromReading readingFromGameClient

        stationIsSomewhereElse stationName =
            currentSolarSystemName
                |> Maybe.map (\here -> not (containsWords here stationName))
                |> Maybe.withDefault True
    in
    case
        List.range huntSystemIndex (huntSystemIndex + List.length botSettings.huntSystemNames)
            |> List.filterMap (huntingGroundAtIndex botSettings)
            |> List.filter (\systemName -> Just systemName /= currentSolarSystemName)
            |> List.head
    of
        Just systemName ->
            Just systemName

        Nothing ->
            lastDockedStationName
                |> Maybe.andThen
                    (\stationName ->
                        if stationIsSomewhereElse stationName then
                            Just stationName

                        else
                            Nothing
                    )


{-| The name the circuit points at, before the guard above has had its say.
-}
huntingGroundAtIndex : BotSettings -> Int -> Maybe String
huntingGroundAtIndex botSettings index =
    let
        lapsCompleted =
            -- **An empty circuit is a circuit already walked**, which is what
            -- makes `home-system` reachable at all when no `hunt-system` is
            -- configured. Written as 0 here, the division below is the only
            -- thing that could ever raise the lap count, so an empty list
            -- pinned it at zero and the `home-system` fallback was code nothing
            -- could reach in the one configuration an operator most obviously
            -- wants it in: no circuit, one place to come back to.
            if List.isEmpty botSettings.huntSystemNames then
                1

            else
                index // List.length botSettings.huntSystemNames
    in
    if 0 < lapsCompleted then
        case botSettings.homeSystemName of
            Just homeSystem ->
                Just homeSystem

            Nothing ->
                huntSystemAtIndex botSettings index

    else
        huntSystemAtIndex botSettings index


{-| Whether an escalation's destination is somewhere this bot may be sent.

The client writes the security status of the trip's end on the objective
chain's progress bar -- `0.6 Andabiar` -- and until it was lifted into
`OpportunityDestination` nothing read it. What that cost: an escalation
fourteen jumps into `0.3 Arodan` sat in the queue from the first minute of the
session, the bot eventually took it, and the ship was killed there by a pilot
with nineteen thousand kills and a 94% efficiency. Eleven million ISK of
escalation loot went with it. Everything the bot has is calibrated against
rats -- `isObjectShootingAtUs` would have added that Succubus to the _target
list_ -- so the only defence available is not to go.

**An unreadable security refuses the trip.** `Nothing` from the parser is the
client not saying, and this is the one place in this file where absent must
read as dangerous rather than as unknown-so-carry-on: the cost of declining an
escalation is some ISK, and the cost of accepting one that turns out to be
lowsec is the hull, the loot and the implants. `loadRefusalFromGameLog`'s
register inverted, deliberately, and said out loud because the rest of the file
argues the other way.

-}
escalationDestinationIsPermitted : BotSettings -> EveOnline.ParseUserInterface.OpportunityInfoPanelEntry -> Bool
escalationDestinationIsPermitted botSettings entry =
    case entry.destination of
        Nothing ->
            True

        Just destination ->
            case destination.systemName of
                -- A step that names no remote system is not a trip anywhere:
                -- verified live against saxrat run 6's own tracked entry, a
                -- Sansha's Command Relay Outpost step reading 'Undock', whose
                -- destination parses as `Just { jumps = Nothing, security =
                -- Nothing, systemName = Nothing }` -- all three fields absent
                -- together, because there is no destination system distinct
                -- from the one the ship is already in. The strict `absent =
                -- refuse` rule this used to be treated that the same as a
                -- client naming an unknown system, and filtered every entry
                -- of every escalation out on every reading, at every step,
                -- for the whole session: `escalationEntriesPermitted` handed
                -- `opportunityTravelStep` an empty list regardless of what
                -- was actually offered, and the docked-branch and in-space
                -- branches both fell through to the hunt circuit and route
                -- asking as if no escalation existed at all.
                --
                -- The safety argument this rule exists for is untouched: a
                -- step that *does* name a system is still refused unless
                -- that system's security is known and high enough. What
                -- changes is only the case a real destination and a merely
                -- local one used to share -- no system named at all.
                Nothing ->
                    True

                Just _ ->
                    destination.security
                        |> securityIsPermitted botSettings.escalationMinimumSecurity


{-| The reading with escalations this bot may not be sent to removed.

Applied to the _reading_ rather than pushed into `opportunityTravelStep`,
because that function is asked about by some ninety-five existing cases and
widening its signature would have rewritten every one of them to prove
something none of them is about. Narrowing the entries first says the same
thing and leaves "what is the tracker offering" a question anybody can still
ask without a settings record.

-}
escalationEntriesPermitted : BotSettings -> ReadingFromGameClient -> ReadingFromGameClient
escalationEntriesPermitted botSettings readingFromGameClient =
    { readingFromGameClient
        | opportunityInfoPanelEntries =
            readingFromGameClient.opportunityInfoPanelEntries
                |> List.filter (escalationDestinationIsPermitted botSettings)
    }


{-| The decision itself, over the two numbers, so a case can run it.

Split out from `escalationDestinationIsPermitted` because that one takes a
parsed panel entry and a whole settings record, and a rule reachable only
through those is a rule checked by reading rather than by running -- which is
what #106 records the cost of, and what let the first version of the
destination parse ship reading `8 jumps` as a security status.

-}
securityIsPermitted : Float -> Maybe Float -> Bool
securityIsPermitted minimumSecurity security =
    case security of
        Just value ->
            value >= minimumSecurity

        Nothing ->
            False


{-| Whether the Opportunities tracker is working an escalation on this reading.

**The tracker holding an escalation is something having said where to go**, which
is the whole of #279: an empty `hunt-system` is not "go nowhere", it is "nobody
has configured a circuit", and a tracked escalation is somebody answering the
same question the circuit exists to answer.

**Read off the entries rather than off the step the branch would press.**
`opportunityTravelStep` refuses a label that is a state -- `Warping`, `Jumping`
and `Docking` are the client saying the trip is already happening, and clicking
one re-commands a manoeuvre already under way -- but a reading it refuses is
still a reading with a trip in progress, and it is exactly the reading the floor
owns. Keying on the button's presence rather than on its wording is what makes
this true across the whole trip instead of only on the readings the panel
happens to be offering a command.

**So this deliberately does not consult `travelLabelIsACommand`**, and that
independence is worth keeping rather than being an accident of how it was
written. The allow-list is about whether a label may be _clicked_, which is a
question about one button; this is about whether anything has answered where to
go, which is a question about the trip. The two have already moved apart once --
the list was carrying `Dock`, which nobody had read off this widget, while
lacking a word the client really writes -- so a signal that inherited its
verdicts would move with it for reasons that have nothing to do with the
circuit.

**The label still has to be text the client rendered** (`travelLabelIsReadableText`).
Run 11 on the mission runner drew a travel step as six C0 control characters and
run 22 as a distance wrapped in NULs, and a button whose label the client failed
to draw is not evidence of anything. Declining there leaves the bot behaving
exactly as it did before this change, which is the fail-closed direction.

**Scoped to a shut probe scanner, which is #260's switch and not a second one.**
With the window open, `siteProgressStep` declines the tracker's step outright, so
the bot is not working the escalation at all and holding it in the system would
be holding it away from the hunt it _is_ doing. Recounted over this machine's 53
saxrat runs that reached space, the scanner is open on 160,171 in-space readings
against 1,862 shut -- 1.15% -- and 36 of the 53 never shut it once, so this reads
the same switch #260 does and fires in the same 1% of readings. If that gate is
ever dropped, this clause has to be looked at with it.

**Gated on the same permission as the travel step, and that is the whole
point.** #291 is what an escalation the bot can see and cannot act on costs:
the stand-down held every dry grid for forty readings waiting for a step that
never came, 234 times in three hours. Refusing a lowsec destination in
`opportunityTravelStep` alone would rebuild exactly that -- the bot would stand
down for an escalation it had already decided never to travel to. So both
readers ask the same question, and an escalation below the threshold is simply
not an escalation as far as this bot is concerned.

-}
escalationIsBeingWorked : ReadingFromGameClient -> Bool
escalationIsBeingWorked readingFromGameClient =
    (readingFromGameClient.probeScannerWindow == Nothing)
        && (readingFromGameClient.opportunityInfoPanelEntries
                |> List.any
                    (\entry ->
                        entry.travelButton
                            |> Maybe.andThen .label
                            |> Maybe.map travelLabelIsReadableText
                            |> Maybe.withDefault False
                    )
           )


{-| How long the bot holds a grid for an escalation the tracker is not yet
offering a step for.

**An unbounded hold is PR #257's shape**, which shipped green and blocked the bot
for 108 minutes because something on a hot decision path could decline forever
with nothing else able to act, and #272's, which waited 8,770 readings at a branch
that asked "bounce?" and never bounced. So the hold is bounded, and past the bound
the hunt circuit is consulted exactly as it is today -- the change can cost at
most this many readings against the behaviour it replaces.

**The number is placed in a gap the corpus draws.** Counted in readings rather
than decision lines, over the four recorded saxrat runs that ever took a step
from the tracker (43, 44, 46 and 52), there are 307 gaps between two consecutive
readings on which the panel offered a pressable command, and **every one of them
is 30 readings or fewer** -- median 1, p95 20, largest 30, and nothing at all
between 31 and the end of a run. Against that, #279's run held the floor for 414
consecutive readings. So a legitimate tracker-led leg has never gone more than 30
readings without a command, and the failure it has to be told apart from is an
order of magnitude past that.

Written as a multiple of `routeAskGiveUpReadings` rather than as a bare 40 so the
argument cannot drift away from the number, and because the two coincide: the
thing this hold displaces is the circuit's own ask, which gets 20 readings before
it gives up for the session, and a hold shorter than that could be out-waited by
the branch it is standing in for.

**Those 307 gaps are measured on the travel-to-location row only**, because #280
is the enter-dungeon row's `Warp to Site` being invisible to the parser -- so
once that lands the panel offers a command on _more_ readings and the gaps can
only shrink. That is the safe direction for a bound placed above them.

-}
escalationStandDownGiveUpReadings : Int
escalationStandDownGiveUpReadings =
    routeAskGiveUpReadings * 2


{-| Whether this reading is one the bot stands down on for the tracker.

Split out from `huntCircuitStep` because `updateMemoryForNewReadingFromGame` has
to advance the counter on exactly the readings the decision holds on, and it
never sees the decision. Two copies of this comparison would drift, and the
counter would then be bounding something other than the thing it counts -- which
is #145's `gateWithinReachTicks` and #11's `dronesInSpaceTicks`, twice each.

-}
standingDownForATrackedEscalation : { escalationIsBeingWorked : Bool, standDownReadings : Int } -> Bool
standingDownForATrackedEscalation standDownCase =
    standDownCase.escalationIsBeingWorked
        && (standDownCase.standDownReadings < escalationStandDownGiveUpReadings)


{-| What the hunt circuit should do with a reading, which is not always to ask.

**The circuit is a second opinion about a question a tracked escalation has
already answered**, and #279's contention half is what that costs. Run 46 is the
recorded shape, counted in readings: the circuit asks the host for `Shumam`, the
tracker's own `Set Destination` puts the escalation back, the ship jumps for
eighteen readings, and the circuit asks for `Shumam` again -- four complete
cycles, 25 ask readings interleaved into 123 opportunity readings, every one of
them naming `Sansha's Command Relay Outpost`. Runs 43 and 44 carry the same
shape. Two controllers, two destinations, each overwriting the other's.

**`StandDownForATrackedEscalation` is asked first, above the give-up**, because
the give-up's own answer is `tetherAtStructure` and docking is precisely what
must not happen beside a live escalation -- see the branch below.

**#279 names two decisions and they are one clause, which is worth recording
because the first has no content on its own.** _Whether the floor may ask at all
when the circuit is empty_ changes nothing by itself: with no `hunt-system`
configured, `nextHuntingGround` is already `Nothing`, so the floor never asks --
it goes straight to `NowhereToAskFor` and tethers. Removing the ask removes
nothing. What parks the ship is what the ask falls through to. So the load-bearing
decision is the second one -- _whether an escalation in progress suppresses the
circuit outright_ -- and the first is satisfied by it: an existing route is still
travelled by `jumpToNextSystem`, which this function is only reached from when
there is none.

-}
type HuntCircuitStep
    = StandDownForATrackedEscalation
    | StopAskingForARoute
    | AskForTheHuntingGround String
    | NowhereToAskFor


huntCircuitStep :
    { escalationIsBeingWorked : Bool
    , standDownReadings : Int
    , routeSettingGivenUp : Bool
    , nextHuntingGround : Maybe String
    }
    -> HuntCircuitStep
huntCircuitStep circuitCase =
    if
        standingDownForATrackedEscalation
            { escalationIsBeingWorked = circuitCase.escalationIsBeingWorked
            , standDownReadings = circuitCase.standDownReadings
            }
    then
        StandDownForATrackedEscalation

    else if circuitCase.routeSettingGivenUp then
        StopAskingForARoute

    else
        case circuitCase.nextHuntingGround of
            Just systemName ->
                AskForTheHuntingGround systemName

            Nothing ->
                NowhereToAskFor


{-| Ask the host to set the autopilot destination, when there is nowhere to go.

This is the one branch that lets the bot originate a route. Everything else it
does with a route follows one that already exists -- set by a human, or by an
earlier pass through here -- and with no `hunt-system` configured the answer is
`tetherAtStructure`, exactly as before.

The ask is repeated every reading until the route panel shows something,
because the channel is unacknowledged: there is no reply to wait for, and the
client's own route panel is the confirmation. `routeAskGiveUpReadings` bounds
it, and the give-up latches for the session.

**Beside an escalation the tracker is working, neither of those answers is
right, and the tether is the worse of the two.** `tetherAtStructure` docks --
`Dock` is the first entry in its own menu priority -- so the reading that meant
"nothing to do here" takes the ship off the grid it crossed six systems to reach,
the docked branch undocks it again on the next reading because the tracker is
still offering something, and the pair repeats. #279's run spent 414 readings and
three hours in exactly that cycle, dock and undock, beside two tracked
`Sansha's Command Relay Outpost` escalations.

**What the bot does instead is hold the grid, and it says so with a count on
every reading it does it.** That is the property both #257 and #272 lacked: a
branch that declines silently is indistinguishable from a bot that is working.
Nothing above this is suppressed -- the two retreats, the pod recovery, the
message-box ladder, the fight and the loot all still run, and the tracker's own
step outranks this by two tiers, so the very reading the panel offers a command
is a reading this branch is never reached on. And the hold is bounded: at
`escalationStandDownGiveUpReadings` the circuit is consulted exactly as it is
today.

**How much of #279's run this fixes is small, and saying so is the point.** The
414 readings are #280's -- `Warp to Site` lives on a second task widget the
parser's type-name prefix does not match, so the arriving step was invisible and
`siteProgressStep` had nothing to press. With that fixed the tracker offers a
command on those readings and this branch is not reached at all. What is left
here is the contention, which #280 does not touch, and a guard on the tether.

-}
setRouteToNextHuntingGround : BotDecisionContext -> DecisionPathNode
setRouteToNextHuntingGround context =
    case
        huntCircuitStep
            { escalationIsBeingWorked =
                escalationIsBeingWorked
                    (escalationEntriesPermitted context.eventContext.botSettings context.readingFromGameClient)
            , standDownReadings = context.memory.escalationStandDownReadings
            , routeSettingGivenUp = context.memory.routeSettingGivenUp
            , nextHuntingGround = nextHuntingGround context
            }
    of
        StandDownForATrackedEscalation ->
            describeBranch
                ("Nothing left to hunt here and no route set, but the Opportunities tracker is working an escalation -- where to go is already answered, so not asking the hunt circuit and not docking ("
                    ++ String.fromInt context.memory.escalationStandDownReadings
                    ++ "/"
                    ++ String.fromInt escalationStandDownGiveUpReadings
                    ++ " readings). Holding this grid so the tracker's own step can be taken as soon as it offers one."
                )
                waitForProgressInGame

        StopAskingForARoute ->
            describeBranch
                ("Asked for a destination for more than "
                    ++ String.fromInt routeAskGiveUpReadings
                    ++ " readings and no route ever appeared -- this host does not set destinations, so stop asking and wait where it is safe."
                )
                (tetherAtStructure context)

        NowhereToAskFor ->
            describeBranch
                "Nothing left to hunt here and no route set. Nowhere to ask for: either no 'hunt-system' is configured, or every system on the circuit is the one this ship is already in."
                (tetherAtStructure context)

        AskForTheHuntingGround systemName ->
            describeBranch
                ("Nothing left to hunt here and no route set. Asking the host to set the destination to '"
                    ++ systemName
                    ++ "' ("
                    ++ String.fromInt context.memory.destinationAskReadings
                    ++ "/"
                    ++ String.fromInt routeAskGiveUpReadings
                    ++ " readings). "
                    ++ hostDirectiveSetDestination systemName
                )
                waitForProgressInGame


jumpToNextSystem : BotDecisionContext -> DecisionPathNode
jumpToNextSystem context =
    if routePanelSaysNoDestination context.readingFromGameClient then
        -- #191. The marker strip and the panel's own words disagree, and the
        -- words are the ones that turned out to be true: run 23 spent 1,200+
        -- consecutive readings travelling a route the client had never
        -- computed, because a stale pip reads as a route to
        -- `infoPanelRouteFirstMarkerFromReadingFromGameClient` and nothing ever
        -- read the text beside it.
        --
        -- Answering it as "no route" is what bounds this. The travel leg itself
        -- has no limit -- it is a fall-back to a cascade, and a cascade that
        -- keeps finding its icon never gives up -- where asking for a route is
        -- bounded by `routeAskGiveUpReadings` and ends in the hunt circuit
        -- moving on. So the fix is not a counter here; it is letting the
        -- reading reach the branch that already has one.
        describeBranch
            "The route panel says there is no destination while still showing a marker -- the marker is stale, so there is no route to travel here."
            (setRouteToNextHuntingGround context)

    else
        case context.readingFromGameClient |> infoPanelRouteFirstMarkerFromReadingFromGameClient of
            Nothing ->
                setRouteToNextHuntingGround context

            Just infoPanelRouteFirstMarker ->
                -- Feedback: right after the route is reset and a new
                -- destination is set (whether by the bot or manually), EVE's
                -- own route panel needs a moment to actually compute the new
                -- multi-jump path -- during that brief window the marker
                -- strip can be empty, partial, or still shifting. Clicking
                -- during that window means right-clicking a position that
                -- has no clickable icon there yet (or not there anymore by
                -- the time the click lands) -- observed live as hundreds of
                -- consecutive ticks of "open context menu on route element
                -- icon" with no menu ever actually appearing, not even a
                -- wrong one to discard. A live, isolated check (read the
                -- same marker 5 times, 300ms apart) found its position
                -- perfectly stable under normal conditions, so this is a
                -- real but transient settling window, not a persistent
                -- coordinate bug -- guard against it by requiring the first
                -- marker's own display region to have stayed the same for
                -- at least one full tick (tracked in BotMemory --
                -- previousReadingsFromGameClient only retains contextMenus,
                -- not route/info-panel data, so this can't be checked
                -- directly against a prior reading the way the context-menu
                -- "no progress" check does) before acting on it.
                if context.memory.routeFirstMarkerUnchangedTicks < 1 then
                    describeBranch
                        "Route panel's first marker just appeared or moved since the last reading -- wait for the route to finish (re)computing before clicking it."
                        waitForProgressInGame

                else if jumpCascadeStuckReopens < context.memory.jumpCascadeReopens then
                    jumpToNextSystemViaSurroundingsButton context

                else
                    returnDronesToBay context
                        (jumpThroughRouteStargate context
                            (useContextMenuCascadeWithCustomConfig
                                -- Feedback: "Jump Through Stargate" took 3-4 menu
                                -- opens before being recognized. The route icon is
                                -- small and sits in a strip that can shift as the
                                -- route updates, so the default distance tolerance
                                -- (70, already once widened from 40 for this same
                                -- kind of drift on other elements) was plausibly
                                -- discarding a menu that had, in fact, opened
                                -- correctly. Widened just for this one cascade
                                -- rather than the shared default, since other
                                -- cascades' tolerance is already tuned from past
                                -- observations and this is a different UI element.
                                (discardContextMenuIfTooDistantFromTargetElement { toleratedDistance = 200 })
                                { targetUIElement = infoPanelRouteFirstMarker.uiNode, targetUIElementName = "route element icon" }
                                (useMenuEntryWithTextContainingFirstOf
                                    [ "dock"
                                    , "jump"
                                    ]
                                    menuCascadeCompleted
                                )
                                context
                            )
                        )


{-| How many times `jumpToNextSystem`'s route-marker cascade may (re)open its
menu for the _same_ next system before giving up on it and falling back to
`jumpToNextSystemViaSurroundingsButton` instead.

**Counted in menu opens, not readings.** A reading spent waiting for a menu
to render ("give the game one more reading") is not evidence of being stuck;
a _repeated_ right-click at the marker -- the cascade discarding what it
found and reopening -- is. `BotMemory.jumpCascadeReopens` counts exactly that,
read off the previous step's own dispatched effects
(`previousStepRightClickedElement`), so waiting readings hold the count
rather than resetting or advancing it.

**An operator's own choice, not a measured figure**, and set deliberately at
the edge of what the marker cascade's own comment calls ordinary ("3-4 menu
opens") rather than above it. The one recorded incident this reasoning has
behind it (saxrat run 23) took 7 discard-and-reopen cycles before
self-resolving; 3 does not wait to find out whether a given stall is that
incident or an unremarkable retry -- it treats the marker cascade as worth
one ordinary attempt and switches to the surroundings-button path readily
rather than as a rare last resort. The cost of that choice: a cascade that
would have completed on its fourth or fifth open now gets interrupted and
redone through a different, heavier path instead.

-}
jumpCascadeStuckReopens : Int
jumpCascadeStuckReopens =
    3


{-| Jump to the route's next system by right-clicking the persistent
"surroundings" button rather than the route panel's own marker.

**Confirmed live, in one pass** (a menu this transient does not survive
between two separate live-inspection scripts): right-clicking
`ListSurroundingsBtn` -- the same button `tetherAtStructure` and
`alignToStructure` already use to reach "Stations"/"Structures" -- also offers
a **Stargates** category, listing this system's gates by the name of the
system each one leads to, and hovering a system name reveals a **Jump**
entry. Three levels: `Stargates -> <system name> -> Jump`.

**Why this exists at all rather than just widening the marker cascade's own
tolerance again.** The marker cascade discards and reopens when the icon
looks too far from where the previous click landed -- a _geometry_ problem,
already tolerant to 200px (widened once already from the shared default of
70). Run 23's 7-cycle stall was not fixed by that tolerance, so whatever kept
discarding it is not simply "a little further away than expected" in the way
widening the number again would fix. The surroundings button is a fixed,
never-moving UI element (unlike the route strip, which "sits in a strip that
can shift as the route updates"), so this is a different _kind_ of target
rather than a more patient version of the same one.

**The system name is matched as a substring, not exactly**, unlike the
identity-sensitive matches elsewhere in this file (`fleetNeedsBackupBroadcast`,
the route panel's own name-vs-overview-row match in `routeStargateJump`).
Those guard against handing a pilot's own warp or a route to the wrong
target; this one is choosing among the _current_ system's own gates, each
leading to a name the client itself put there, so a substring collision would
need two of this system's neighbours to share a name -- solar system names in
EVE are unique, so that cannot happen. `useMenuEntryWithTextContaining` is
used rather than `useMenuEntryWithTextEqual` because the live capture did not
confirm whether the row carries markup (a security-status colour tag, as the
route panel's own labels do) around the bare name.

All three levels confirmed live, the third by direct operator observation
rather than a read this file's own tooling could keep up with (the flyout
does not stay open long enough to right-click it, hover it, and read the
result across separate process launches -- it has to be one continuous
session): the entry really does read exactly `Jump`, matched with
`useMenuEntryWithTextEqual` rather than a substring for that reason.

**Unverified: the cascade running end to end.** Nothing has driven all three
levels in one live sequence and watched a jump land this way -- the pieces
are each confirmed, the whole is not. It also does not fire in the ordinary
course of things, since it is reached only past `jumpCascadeStuckReopens`;
the first real test of this function is whatever run next gets stuck long
enough to reach it. Whether recalling drones first (mirroring
`jumpToNextSystem`'s own `returnDronesToBay`) is actually necessary at this
point in the tree -- rather than merely harmless -- is also unconfirmed.

-}
jumpToNextSystemViaSurroundingsButton : BotDecisionContext -> DecisionPathNode
jumpToNextSystemViaSurroundingsButton context =
    case context.readingFromGameClient |> nextSystemOnRouteFromReading of
        Nothing ->
            describeBranch
                "Was going to fall back to the surroundings-button cascade, but the route panel no longer names a next system -- nothing to jump toward this way either."
                waitForProgressInGame

        Just systemName ->
            describeBranch
                ("The route-marker cascade has (re)opened its menu "
                    ++ String.fromInt context.memory.jumpCascadeReopens
                    ++ " time(s) trying to jump toward '"
                    ++ systemName
                    ++ "', past "
                    ++ String.fromInt jumpCascadeStuckReopens
                    ++ " -- right-click the surroundings button instead and cascade to this gate by name."
                )
                (returnDronesToBay context
                    (useContextMenuCascadeOnListSurroundingsButton
                        (useMenuEntryWithTextEqual "Stargates"
                            (useMenuEntryWithTextContaining systemName
                                (useMenuEntryWithTextEqual "Jump" menuCascadeCompleted)
                            )
                        )
                        context
                    )
                )


{-| What the panel may be asked to do about the route's next stargate.

A verdict rather than a sentence, so a case can execute the rule and compare the
answer whole -- `AmmoSwapGiveUp`'s shape, and for its reason: a rule that only
produced log text could be asserted on by substring, and a branch's own wording
quotes the same names the assertion would look for.

Each fall-back carries the system it was reasoning about where it has one, so
`describeRouteStargateJump` can say which system rather than only what went
wrong.

-}
type RouteStargateJump
    = PressTheJumpButton String
    | NoNextSystemOnRoute
    | NoStargateNamedForTheNextSystem String
    | SeveralStargatesNamedForTheNextSystem String
    | ThePanelIsShowingSomethingElse String
    | ThePanelOffersNoJump String


{-| Whether to press the Selected Item panel's Jump, and which gate it would be.

**A jump to the wrong gate is a wrong system, not a wasted tick**, so every
clause below is a way this could act on the wrong object and the answer to each
is to fall back to the route-marker cascade -- which right-clicks the route's own
marker and cannot pick the wrong gate at all. The mission runner's
`dockAtDestinationStation` shipped assuming one route marker meant the nearest
station was the destination, #98 was the regression, and nothing had checked
identity.

**The identity, and what makes it possible.**
`InfoPanelRouteRouteElementMarker` carries a `uiNode` and no name -- which is why
the marker cannot say which gate it is. What answers instead is the route panel's
_own label_, read live from this client:

    <a href="showinfo:5//30005001" alt="Next System in Route">Arnon</a>

and the overview's stargate rows, which carry the system a gate leads to in the
Name column and the word in the Type column. Read live off this account's client
while this was written, with that very gate selected:

    Name "Tar" Type "Stargate (CONCORD System)"

So "the gate to the next system in the route" is a name match between two
readings the client itself renders, and needs nothing from the marker.

**Only the row's own name is matched, never its type.** A type reads
`Stargate (Amarr Border)` and Amarr is a real system, so a rule that looked at
both would match a gate leading somewhere else entirely on the strength of the
region it borders.

**Exactly one match, or fall back.** Two rows naming one system is not something
this reading can choose between, and a system's name is unique, so more than one
means the match is not the one this rule thinks it is.

**The panel is already showing that gate.** Where it is showing something else
this falls back rather than selecting the row first: selecting spends the very
reading this exists to save, and the cascade is what the fall-back does anyway.
That is the one place this departs from `activateAccelerationGateIfPresent`'s
select-then-press shape.

**The panel offers the button.** Whether `selectedItemJump` is drawn on a gate
out of jump range is unread; if it is, pressing it is still the right gate and
the client's own warp-and-jump, and if it is not this falls back to the cascade,
which is what flies the ship there. Either way the gate is the route's.

-}
routeStargateJump :
    { nextSystemOnRoute : Maybe String
    , stargatesOnOverview : List { name : String, panelIsShowingIt : Bool }
    , panelOffersJump : Bool
    }
    -> RouteStargateJump
routeStargateJump input =
    case input.nextSystemOnRoute of
        Nothing ->
            NoNextSystemOnRoute

        Just nextSystem ->
            case input.stargatesOnOverview |> List.filter (.name >> stargateNameLeadsToSystem nextSystem) of
                [] ->
                    NoStargateNamedForTheNextSystem nextSystem

                [ gate ] ->
                    if not gate.panelIsShowingIt then
                        ThePanelIsShowingSomethingElse nextSystem

                    else if not input.panelOffersJump then
                        ThePanelOffersNoJump nextSystem

                    else
                        PressTheJumpButton gate.name

                _ ->
                    SeveralStargatesNamedForTheNextSystem nextSystem


{-| What the decision log says about `routeStargateJump`'s answer.

Derived from the verdict rather than stored beside it, for
`describeAmmoSwapGiveUp`'s reason: two places that can disagree about why a
branch did something eventually do.

Every fall-back names the route marker, because that is what runs next and an
operator reading a stretch of these needs to see the cascade is still travelling
the route rather than that the jump has stopped happening.

-}
describeRouteStargateJump : RouteStargateJump -> String
describeRouteStargateJump jump =
    case jump of
        PressTheJumpButton gateName ->
            "Jump through '" ++ gateName ++ "' from the selected-item panel, which is already showing it."

        NoNextSystemOnRoute ->
            "The route panel does not name a next system, so nothing here says which stargate is the route's -- right-click the route marker instead."

        NoStargateNamedForTheNextSystem nextSystem ->
            "No stargate on the overview is named for '" ++ nextSystem ++ "' -- right-click the route marker instead."

        SeveralStargatesNamedForTheNextSystem nextSystem ->
            "More than one stargate on the overview is named for '" ++ nextSystem ++ "', so which one the route means is not readable here -- right-click the route marker instead."

        ThePanelIsShowingSomethingElse nextSystem ->
            "The selected-item panel is not showing the stargate to '" ++ nextSystem ++ "' -- selecting it would spend the reading this saves, so right-click the route marker instead."

        ThePanelOffersNoJump nextSystem ->
            "The selected-item panel is showing the stargate to '" ++ nextSystem ++ "' and offers no 'selectedItemJump' -- right-click the route marker instead, which is what closes the distance."


{-| Whether an overview row's name says this stargate leads to `systemName`.

`containsWords`' whole-word rule, with punctuation read as a separator first.
The rows this client draws name the system alone -- `Tar` -- and an overview
preset that renders `Stargate (Tar)` in the Name column has to match too;
without the normalisation the parentheses make that a different word and the
match is lost, and with a plain substring rule `Ami` would match `Amir`.

Both sides get the same treatment, so a system whose own name carries punctuation
-- `1DQ1-A` -- is compared as the same sequence of words on each side.

-}
stargateNameLeadsToSystem : String -> String -> Bool
stargateNameLeadsToSystem systemName gateName =
    containsWords (punctuationAsSeparators systemName) (punctuationAsSeparators gateName)


punctuationAsSeparators : String -> String
punctuationAsSeparators =
    String.map
        (\character ->
            if Char.isAlphaNum character then
                character

            else
                ' '
        )


{-| The system the route panel says this ship jumps to next, if it says.

`NextWaypointPanel`'s label, which nothing in this bot had ever read -- the route
panel was only ever asked whether it held a marker. Both quote styles, exactly as
`parseCurrentSolarSystemFromUINodeText` takes them: this client writes
`alt="Next System in Route"` and the 2019 recording in `explore/` writes
`alt='Next System in Route'`.

-}
nextSystemOnRouteFromReading : ReadingFromGameClient -> Maybe String
nextSystemOnRouteFromReading readingFromGameClient =
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelRoute
        |> Maybe.map (.uiNode >> .uiNode >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts)
        |> Maybe.withDefault []
        |> List.filterMap parseNextSystemInRouteFromLabelText
        |> List.head


parseNextSystemInRouteFromLabelText : String -> Maybe String
parseNextSystemInRouteFromLabelText labelText =
    [ "alt='Next System in Route'", "alt=\"Next System in Route\"" ]
        |> List.filterMap
            (\marker ->
                labelText |> EveOnline.ParseUserInterface.getSubstringBetweenXmlTagsAfterMarker marker
            )
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)
        |> List.head


{-| The words the route panel writes when the client has no route at all.

Lower-cased before comparing, because the panel's own casing is not something
this has evidence about beyond the one capture.

-}
routePanelNoDestinationMarker : String
routePanelNoDestinationMarker =
    "no destination"


{-| Whether the route panel says outright that there is no destination.

**A reading can carry this _and_ a next-system label at the same time**, and that
is #191. Read off the live client while saxrat run 23 was stuck, the panel held

    No Destination
    <a href="showinfo:5//30002217" alt="Next System in Route">Hutian</a>
    No Destination

with one marker icon. The bot read the label, looked for an overview row named
`Hutian`, found none, fell back to the route-marker cascade, and repeated -- 1,200+
consecutive readings, never moving, because the client had not computed a route to
that system and the label was left over.

`infoPanelRouteFirstMarkerFromReadingFromGameClient` answers the panel's
_visibility_ and has never read its text, so a stale pip reads as a route. The
panel's own sentence is the one piece of evidence that contradicts it, and this is
the reading of it.

-}
routePanelSaysNoDestination : ReadingFromGameClient -> Bool
routePanelSaysNoDestination readingFromGameClient =
    (routePanelTexts readingFromGameClient
        |> List.any
            (\text ->
                text |> String.toLower |> String.contains routePanelNoDestinationMarker
            )
    )
        && not (routePanelShowsARoute readingFromGameClient)


{-| Every string the route panel is carrying, markup and all.

One definition because three rules read it and the markup matters to two of
them: `getAllContainedDisplayTexts` returns `_setText` as the client wrote it,
so the `alt=` attributes below survive into the answer.

-}
routePanelTexts : ReadingFromGameClient -> List String
routePanelTexts readingFromGameClient =
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelRoute
        |> Maybe.map (.uiNode >> .uiNode >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts)
        |> Maybe.withDefault []


{-| What the panel writes when a route really is set.

`No Destination` is not the absence of these -- it is a label the client leaves
in the tree beside them, under a node whose own `_name` is `noDestinationLabel`,
and that is the whole of #191's second half. Run 31 sat in Hama for 48 minutes
and asked the host for a route **2,494 times** while the panel read:

    Route <fontsize=12>5 Jumps
    No Destination                                     <- _name=noDestinationLabel
    <a href="showinfo:5//30003525" alt="Next System in Route">Bagodan</a>
    <a href="showinfo:5//30003547" alt="Current Destination">Hamse</a>

The route was real: five jumps, next hop Bagodan, destination Hamse, set by the
bot's own ESI call three readings earlier.

-}
routePanelDestinationMarker : String
routePanelDestinationMarker =
    "current destination"


routePanelJumpsMarker : String
routePanelJumpsMarker =
    "jump"


{-| Whether the panel carries positive evidence of a route.

**Positive rather than negative, and that is the point.** The two recorded
captures are separated by exactly these words and by nothing else:

  - run 23, stuck with no route the client had ever computed: `No Destination`,
    a `Next System in Route` label, `No Destination` again, and one marker pip.
    Neither marker below appears.
  - run 31, stuck with a five-jump route it refused to travel: both markers
    below, beside the same stale `No Destination`.

So a rule that reads the absence of `No Destination`, or the presence of a
marker pip, cannot tell them apart -- and each of those is what the two halves
of this bot were separately doing. `Next System in Route` is deliberately _not_
one of the markers: it is present in both captures, being the label run 23's
client left behind.

-}
routePanelShowsARoute : ReadingFromGameClient -> Bool
routePanelShowsARoute readingFromGameClient =
    routePanelTexts readingFromGameClient
        |> List.any
            (\text ->
                let
                    lowered =
                        text |> String.toLower
                in
                (lowered |> String.contains routePanelDestinationMarker)
                    || (lowered |> String.contains routePanelJumpsMarker)
            )


{-| Whether an overview row's own words say it is a stargate.

Name _and_ type, because the two columns carry the word differently depending on
the overview preset -- this client puts `Stargate (CONCORD System)` in Type and
the destination system alone in Name.

One definition rather than an inline `containsWords "stargate"` at the call site,
which is the mission runner's arrangement: this bot has only the one reader
today, and the reader it has decides which object a jump command acts on.

-}
overviewEntryIsAStargate : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsAStargate entry =
    [ entry.objectName, entry.objectType ]
        |> List.filterMap identity
        |> List.any (containsWords "stargate")


{-| The verdict, taken from a reading alone.

Split out of `jumpThroughRouteStargate` so `fleetJumpToCall` can ask the same
question: the gate the fleet is told to jump has to be the gate this ship is
about to jump, and two constructions of that verdict are two answers that can
come to disagree about which gate that is.

-}
routeStargateJumpFromReading : ReadingFromGameClient -> RouteStargateJump
routeStargateJumpFromReading readingFromGameClient =
    routeStargateJump
        { nextSystemOnRoute = nextSystemOnRouteFromReading readingFromGameClient
        , stargatesOnOverview =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter overviewEntryIsDisplayed
                |> List.filter overviewEntryIsAStargate
                |> List.map
                    (\gate ->
                        { name = gate.objectName |> Maybe.withDefault ""
                        , panelIsShowingIt =
                            selectedItemIsOverviewEntry readingFromGameClient gate
                        }
                    )
        , panelOffersJump =
            selectedItemButtonNamed readingFromGameClient "selectedItemJump" /= Nothing
        }


{-| Take the route's next stargate by pressing the Selected Item panel's own
Jump button, where the panel is already showing that gate.

**What this replaces on the readings it can, and how much.** The cascade below is
the worst-behaved in this file, carrying a tolerance of its own widened to 200
because "'Jump Through Stargate' took 3-4 menu opens before being recognized"
against an 8x8 icon in a strip that shifts as the route updates. Counted over the
recorded runs in _readings_ rather than decision lines, that cascade cost run 13
**400 readings across 27 jump legs** and run 14 **348 across 26** -- a median of
12 and 13 readings a leg, and it is spent getting the command out rather than
waiting for the jump afterwards. The mission runner's own copy of this cascade
costs 3 and 2 on the same measurement, so **saxrat's legs are four to six times
the price** and the cascade holds **23% and 38% of every reading in the run**
against that bot's 2% and 3%. That share is what makes this worth doing here,
where on the mission runner it was worth one to two readings a leg.

Against the saving sits a wrong system, which is why `routeStargateJump` refuses
on every reading it cannot identify the gate from the client's own two renderings
of the system's name.

**Behind the settling guard, not beside it.** The panel press touches no marker,
so the guard above is not protecting it from a click that lands nowhere -- what
it protects is the _label_. During the window the route is recomputing, the panel
can still be naming the previous route's next system, and jumping the gate the
old route wanted is exactly the wrong system this refuses everywhere else.

**Inside `returnDronesToBay`, like the cascade it replaces.** A jump leaves
whatever is in space behind, and the panel press is no gentler about that than
the menu entry.

-}
jumpThroughRouteStargate : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
jumpThroughRouteStargate context ifThePanelCannotDoIt =
    let
        jumpButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        jumpButton =
            selectedItemButtonNamed context.readingFromGameClient "selectedItemJump"

        verdict : RouteStargateJump
        verdict =
            routeStargateJumpFromReading context.readingFromGameClient
    in
    case ( verdict, jumpButton ) of
        ( PressTheJumpButton _, Just buttonToPress ) ->
            describeBranch (describeRouteStargateJump verdict) (clickUiElement buttonToPress)

        _ ->
            describeBranch (describeRouteStargateJump verdict) ifThePanelCannotDoIt


{-| Leave, on the strongest of three instruments rather than on the weakest.

The gauges are read through `BotMemory.hitpointsLowWaterMark`, never live off
the reading. Two things happen on the way there and both matter. A value has to
be _believed_ -- confirmed by a second reading -- before anything acts on it,
because a single corrupt reading is a routine occurrence on this gauge and `0`
is as reachable as `21328.22` while being the worst possible value to be wrong
about, clearing every threshold at once. And the believed value is then held at
its low-water mark until the ship genuinely recovers, so a retreat stays
committed instead of flipping back the moment a repairer catches up.

The third instrument needs no gauge at all, which is the point of it: the
client's own combat log, summed over a rolling window. It is the only one of
the three that was armed in saxrat's shipped configuration, where both
hitpoint thresholds default to `-1`.

-}
runAwayIfLowHealth : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> Maybe DecisionPathNode
runAwayIfLowHealth context _ =
    let
        runAwayShieldThreshold =
            context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent

        runAwayArmorThreshold =
            context.eventContext.botSettings.runAwayArmorHitpointsThresholdPercent

        damageInWindow =
            incomingDamageInWindow context.memory.incomingDamage

        hitpointsReadingIsFrozen =
            (damageThatMustMoveTheHitpointsReading <= damageInWindow)
                && (hitpointsReadingMovedInWindow context.memory.incomingDamage == Just False)
    in
    if context.memory.hitpointsLowWaterMark.shield < runAwayShieldThreshold then
        Just
            (describeBranch
                ("Shield HP " ++ (context.memory.hitpointsLowWaterMark.shield |> String.fromInt) ++ "%, get out get out")
                (runAway context)
            )

    else if context.memory.hitpointsLowWaterMark.armor < runAwayArmorThreshold then
        Just
            (describeBranch
                ("Armor at " ++ (context.memory.hitpointsLowWaterMark.armor |> String.fromInt) ++ "%, get out get out get out")
                (runAway context)
            )

    else if context.memory.incomingDamage.retreating then
        -- Latched in the memory update, and released only by a window that is
        -- completely empty. A live comparison would cancel its own retreat:
        -- the moment the ship warps clear the window starts draining.
        Just
            (describeBranch
                ("The client's combat log says this ship has taken "
                    ++ String.fromInt damageInWindow
                    ++ " hitpoints in the last "
                    ++ String.fromInt incomingDamageWindowSeconds
                    ++ " s, against a threshold of "
                    ++ String.fromInt context.eventContext.botSettings.runAwayIncomingDamageThreshold
                    ++ ". Get out -- this does not depend on the HUD gauge."
                )
                (runAway context)
            )

    else if hitpointsReadingIsFrozen then
        -- A ship that cannot see what is happening to it gets less rope than
        -- one that can, which is why this threshold sits below the one above.
        -- A `Nothing` sample never counts as movement, so a window of nothing
        -- but unreadable values reads as frozen -- the conservative direction.
        Just
            (describeBranch
                ("This ship has taken "
                    ++ String.fromInt damageInWindow
                    ++ " hitpoints while its shield and armour readings have not moved at all. A reading that cannot move is not a reading -- get out."
                )
                (runAway context)
            )

    else
        Nothing


{-| Is nothing watching for the ship being ground down?

The mission runner's #129, ported because saxrat's shipped configuration **is**
the state this names: both percentage thresholds default to `-1`, so a run
started without settings has the damage window armed and neither gauge guard
able to see an attrition. The damage window bounds a _burst_ -- it reports gross
incoming damage where survival is governed by net, and a hull that repairs
reads a smaller window while dying than while healthy.

The bound is read off `runAwayIfLowHealth`'s own `hitpointsLowWaterMark <
threshold` rather than off the `-1` convention, so a threshold of `0` -- a
keystroke away, and equally unable to fire, since a percentage never goes below
zero -- reads as uncovered too. The two cannot drift apart.

**Read by the status line and by no decision.** `runAwayIfLowHealth` is
untouched: a run that was covered before is covered identically now, and one
that was not is not. What changes is that it says so on every reading rather
than leaving it to be reconstructed from a log afterwards.

-}
attritionIsUnguarded : { shieldThresholdPercent : Int, armorThresholdPercent : Int } -> Bool
attritionIsUnguarded coverCase =
    (coverCase.shieldThresholdPercent <= 0) && (coverCase.armorThresholdPercent <= 0)


{-| Whether anything is watching the ship's health, in the status line.

**The mission runner's clause prints the low-water marks too and this one does
not**, because saxrat already carries them --
`describeMenuAndSettlingCounters` prints `retreat is going by shield N%, armor
M%` off `hitpointsLowWaterMark`. Two clauses for one pair of numbers is two
places to disagree about them.

**That clause is conditional where the mission runner's is not**, and the gap is
stated rather than papered over: saxrat prints the marks only on readings where
the gauge has withheld something, so a run whose gauge behaves never shows them
at all. Widening it is a change to a clause this one does not own, and it wants
its own evidence.

Printed on the guarded case as well, in saxrat's own register, rather than only
when it fires. A clause that appeared only under the warning would leave "the
thresholds are armed" and "this bot does not carry the clause" grepping the
same, which is `describeClearing`'s rule and the reason the corpus could not
answer #265's question about saxrat in the first place.

-}
describeRetreatCover : { shieldThresholdPercent : Int, armorThresholdPercent : Int } -> String
describeRetreatCover coverCase =
    let
        thresholds =
            " (shield "
                ++ (coverCase.shieldThresholdPercent |> String.fromInt)
                ++ " armor "
                ++ (coverCase.armorThresholdPercent |> String.fromInt)
                ++ ")"
    in
    if attritionIsUnguarded coverCase then
        "attrition UNGUARDED"
            ++ thresholds
            ++ " -- the damage window only bounds a burst; set run-away-armor-hitpoints-threshold-percent."

    else
        "attrition guarded" ++ thresholds ++ "."


plausibleHitpointsPercent : Int -> Maybe Int
plausibleHitpointsPercent value =
    if value < 0 || 100 < value then
        Nothing

    else
        Just value


initHitpointsGaugeMemory : HitpointsGaugeMemory
initHitpointsGaugeMemory =
    { previousReading = Nothing
    , believed = Nothing
    , readingsWithheld = 0
    , lastWithheld = Nothing
    }


{-| Fold one reading into what this gauge is willing to be believed about.

`believed` is the healthier of the last two believable readings. `Maybe.map2`
is what makes an unbelievable value -- or a reading with no ship UI at all --
leave nothing behind for the next reading to confirm against, so values either
side of a gap in the gauge are never treated as agreement across it.

**It delays; it cannot suppress.** On any non-increasing series the believed
value is the previous reading's, whatever the size of the step, so a hull
losing armour retreats one reading later than it used to and a hull genuinely
at 0% still retreats.

-}
updateHitpointsGaugeMemory : Int -> Maybe Int -> HitpointsGaugeMemory -> HitpointsGaugeMemory
updateHitpointsGaugeMemory retreatThreshold reading memoryBefore =
    let
        believed =
            case memoryBefore.previousReading of
                -- Nothing to confirm against: the session's first reading, or
                -- the one after a gap. The reading stands on its own rather
                -- than being withheld indefinitely -- a gauge that is only
                -- readable every other reading would otherwise never be
                -- believed at all, and a hull really at 0% would never retreat.
                Nothing ->
                    reading

                -- Otherwise the healthier of the two, so a drop has to survive
                -- a second look. An unbelievable reading is `Nothing` here and
                -- stays `Nothing`, which is what stops the readings either side
                -- of a gap vouching for each other.
                Just previous ->
                    reading |> Maybe.map (max previous)

        wasWithheld =
            hitpointsReadingWithheld retreatThreshold reading believed
    in
    { previousReading = reading
    , believed = believed
    , readingsWithheld =
        memoryBefore.readingsWithheld
            + (if wasWithheld then
                1

               else
                0
              )
    , lastWithheld =
        if wasWithheld then
            reading

        else
            memoryBefore.lastWithheld
    }


{-| Would this reading have tripped the retreat that the believed one does not?

Counted only against _this gauge's_ own threshold, so a gauge nobody is reading
reports nothing -- which matters here, where both hitpoint thresholds ship
disabled.

-}
hitpointsReadingWithheld : Int -> Maybe Int -> Maybe Int -> Bool
hitpointsReadingWithheld retreatThreshold reading believed =
    let
        trips value =
            value |> Maybe.map (\percent -> percent < retreatThreshold) |> Maybe.withDefault False
    in
    trips reading && not (trips believed)


{-| The lowest believed value seen, until the ship recovers or docks.

Docking forgets outright -- there is no ship UI to read and the next undock is
a fresh hull. In space it is kept until the gauge reads at or above
`runAwayRearmPercent`, which is what gives the retreat hysteresis: without it a
single live threshold flips back the moment a repairer catches up, and the ship
oscillates between fleeing and returning.

-}
lowWaterMark : ReadingFromGameClient -> Maybe Int -> Int -> Int
lowWaterMark readingFromGameClient believed previous =
    case readingFromGameClient.shipUI of
        Nothing ->
            100

        Just _ ->
            case believed of
                Nothing ->
                    previous

                Just current ->
                    if runAwayRearmPercent <= current then
                        100

                    else
                        min previous current


{-| Where the mark is released. Above every sane trip level, or it would never
release at all.
-}
runAwayRearmPercent : Int
runAwayRearmPercent =
    90


incomingDamageInWindow : IncomingDamageMemory -> Int
incomingDamageInWindow memory =
    memory.samples |> List.map .damage |> List.sum


{-| Every attacker the client named across the window, deduplicated.

`topAttacker` is one name and a pocket has several, so the set is accumulated
per reading rather than the host being widened to carry a list. Measured over
the recorded runs, accumulating the per-reading top attacker across the window
recovers 97.5% of the name-in-window pairs that carrying every name would have.

-}
namesOfRecentAttackers : IncomingDamageMemory -> List String
namesOfRecentAttackers memory =
    memory.samples
        |> List.filterMap .attacker
        |> Common.Basics.listUnique


{-| Has the HUD reading moved across the window? `Nothing` while the window is
too short to mean anything either way.
-}
hitpointsReadingMovedInWindow : IncomingDamageMemory -> Maybe Bool
hitpointsReadingMovedInWindow memory =
    if List.length memory.samples < readingsBeforeAFrozenHitpointsReadingCounts then
        Nothing

    else
        Just
            (memory.samples
                |> List.filterMap .hitpoints
                |> Common.Basics.listUnique
                |> List.length
                |> (<) 1
            )


incomingDamageWindowSeconds : Int
incomingDamageWindowSeconds =
    45


damageThatMustMoveTheHitpointsReading : Int
damageThatMustMoveTheHitpointsReading =
    1500


readingsBeforeAFrozenHitpointsReadingCounts : Int
readingsBeforeAFrozenHitpointsReadingCounts =
    4


{-| Calibrated from peak 45-second incoming damage across sixteen recorded
client sessions: the worst any session the ship survived absorbed was 3114, and
the session it was lost in peaked at 4101. About 12% clear either way, which is
a real separation rather than a comfortable one -- and **a number about a hull,
not about the game**.
-}
defaultRunAwayIncomingDamageThreshold : Int
defaultRunAwayIncomingDamageThreshold =
    3500


{-| The lowest security status an escalation may send this bot to.

**0.5 is the empire line**, not a tuning parameter: at 0.5 and above CONCORD
answers an aggression, and below it nobody does. That is the whole of the
argument, which is why this is a constant with a name rather than a number
somebody picked -- every guard in this file is calibrated against rats, and
below 0.5 the thing that kills this ship is not a rat.

Paid for once. An escalation fourteen jumps into `0.3 Arodan` was in the queue
from the first minute of a session; the bot took it, and the ship was killed
there by a pilot with 19,739 kills and 94% efficiency, flying a Succubus --
warp scrambled, so the retreat could not have worked either. Eleven million ISK
of escalation loot went with the hull.

`escalation-minimum-security` overrides it, in **tenths**, because
`AppSettings` has no float reader and inventing one for this is more surface
than the setting is worth: `escalation-minimum-security=5` is 0.5, `=0` allows
anything including nullsec. An operator who wants the bot in lowsec has to say
so in a number.

-}
defaultEscalationMinimumSecurity : Float
defaultEscalationMinimumSecurity =
    0.5


incomingDamageSampleLimit : Int
incomingDamageSampleLimit =
    200


updateIncomingDamageMemory : UpdateMemoryContext BotSettings -> HitpointsMemory -> IncomingDamageMemory -> IncomingDamageMemory
updateIncomingDamageMemory context hitpoints memoryBefore =
    let
        hitpointsNow =
            Maybe.map2 Tuple.pair hitpoints.shield.believed hitpoints.armor.believed

        keptSamples =
            memoryBefore.samples
                |> List.filter
                    (\sample ->
                        context.timeInMilliseconds
                            - sample.atMilliseconds
                            < incomingDamageWindowSeconds
                            * 1000
                    )
                |> List.take incomingDamageSampleLimit

        samples =
            case context.readingFromGameClient.incomingDamageSinceLastReading of
                Nothing ->
                    keptSamples

                Just reading ->
                    { atMilliseconds = context.timeInMilliseconds
                    , damage = reading.damage
                    , hitpoints = hitpointsNow
                    , attacker = reading.topAttacker
                    }
                        :: keptSamples

        updated =
            { samples = samples
            , hostCarriesTheChannel =
                context.readingFromGameClient.incomingDamageSinceLastReading /= Nothing
            , lastAttacker =
                case context.readingFromGameClient.incomingDamageSinceLastReading of
                    Just reading ->
                        case reading.topAttacker of
                            Just attacker ->
                                Just attacker

                            Nothing ->
                                memoryBefore.lastAttacker

                    Nothing ->
                        memoryBefore.lastAttacker
            , retreating = memoryBefore.retreating
            }

        damageInWindow =
            incomingDamageInWindow updated

        threshold =
            context.botSettings.runAwayIncomingDamageThreshold
    in
    { updated
        | retreating =
            if damageInWindow <= 0 then
                False

            else if 0 <= threshold && threshold <= damageInWindow then
                True

            else
                memoryBefore.retreating
    }


{-| The window, the threshold, and whether the host carries the channel at all.

That last clause is what makes reading this guard's silence safe: "0 hitpoints
in the last 45 s" reads identically whether the grid is quiet or nothing is
listening, and only one of those means the ship is fine.

-}
describeIncomingDamage : BotDecisionContext -> String
describeIncomingDamage context =
    let
        memory =
            context.memory.incomingDamage

        threshold =
            context.eventContext.botSettings.runAwayIncomingDamageThreshold
    in
    if not memory.hostCarriesTheChannel then
        "dmg: NO COMBAT LOG -- damage retreat and frozen-reading check unarmed"

    else
        "dmg "
            ++ (incomingDamageInWindow memory |> String.fromInt)
            ++ "/"
            ++ (if threshold < 0 then
                    "off"

                else
                    String.fromInt threshold
               )
            ++ " ("
            ++ (incomingDamageWindowSeconds |> String.fromInt)
            ++ "s, "
            ++ (List.length memory.samples |> String.fromInt)
            ++ "rd)"
            ++ (if memory.retreating then
                    " RETREATING"

                else
                    ""
               )
            ++ (case hitpointsReadingMovedInWindow memory of
                    Just False ->
                        " hp frozen"

                    _ ->
                        ""
               )
            ++ (case namesOfRecentAttackers memory of
                    [] ->
                        " Attackers named in the window: none."

                    names ->
                        " Attackers named in the window: "
                            ++ (names |> List.map (\name -> "'" ++ name ++ "'") |> String.join ", ")
                            ++ " (any overview row with one of these names is a target)."
               )


{-| This ship's own fire after one more reading, and the run of readings on
which every shot of it missed.

Advanced in `updateMemoryForNewReadingFromGame`, which is #102's and #126's
placement rule and the only thing that runs unconditionally on every reading --
so this count cannot be frozen by a branch that stops being reached, the way the
mission runner's abandonment deadline was.

**A reading with no shot in it holds the run rather than clearing it.** That is
`gateWithinReachTicks`' hold, for its reason: resetting on a reading that
carries no evidence either way is the shape that pinned `gunsSilencedTicks` at 1
forever, and a reload, a target dying or a menu cascade all produce readings a
firing ship put no shot into. A reading the host could not answer for at all
holds it too, and for the stronger reason -- an absent channel is not a quiet
grid.

**Any landed shot clears the run, including one that landed for zero.** The run
is about the guns being unable to _hit_, which is what a miss says; a shot that
lands and achieves nothing is the other failure and is #90's, whose tally is
kept separately in the mission runner and is deliberately not duplicated here.


# There is no threshold to put on this, and that is a measurement

The rule somebody would want to write -- "lots of misses, so swap ammo or
manoeuvre" -- has no number, and the client's own logs are what say so. Measured
over the 40 sessions carrying outgoing fire in `~/Documents/EVE/logs/Gamelogs`
(207,313 shots), cut at every `(bounty)` line, which is the only thing in this
corpus that states a rat died:

  - **The worst miss share on a stretch of fighting that then produced a kill is
    100%**, and the interval below it is a 467-shot, 456-second stretch at
    **99.1%** that killed its rat afterwards. **No stretch that never produced a
    kill missed more than that.** The two populations do not separate at any
    share, at any length, in either direction.
  - Read the other way round, the fights that miss most are the ones being
    _won_: over 30-second windows the median miss share is 5% where a rat died
    and 2% where none did. A rule keyed on missing would fire hardest on the
    grids that were paying.
  - The stalls PR #272 bounds are **low-miss** stalls. That is its own finding
    restated from this side -- "the guns were landing and the repairs were
    faster" -- so a miss signal could not have caught run 48 however it was
    tuned, and `combatStalemate` is not made faster or more specific by one.

The 702-consecutive-miss run the parser's doc comment warns about is real and is
in this corpus, on a `Hunter Alvi`: 702 shots, 2,650 seconds, not one landing.
What it is _not_ is a target the guns went on to kill. That reading comes from a
name-keyed fold -- the same _name_ had been hurt earlier in the session, on a
different rat -- and scored against the client's own kill signal the run
produced nothing and ran to the end of the session. So the hazard is worse than
recorded, not better: the one episode that looks like the signal working is
indistinguishable, by share and by length, from the 99.1% stretch that recovered.

`test_saxrat_outgoing_fire.py` recomputes every one of those as relations, so a
corpus that grows cannot make a true claim red -- and if it ever stops holding,
that file is what goes red and the threshold becomes writable.

-}
outgoingFireAfterReading :
    { before : OutgoingFireMemory
    , summaries : Maybe (List EveOnline.ParseUserInterface.OutgoingDamageToTarget)
    }
    -> OutgoingFireMemory
outgoingFireAfterReading { before, summaries } =
    case summaries of
        Nothing ->
            { before | hostCarriesTheChannel = False, hits = 0, misses = 0 }

        Just targets ->
            let
                hits =
                    targets |> List.map .hits |> List.sum

                misses =
                    targets |> List.map .misses |> List.sum

                run =
                    if 0 < hits then
                        0

                    else if 0 < misses then
                        before.readingsEveryShotMissed + 1

                    else
                        before.readingsEveryShotMissed
            in
            { hostCarriesTheChannel = True
            , hits = hits
            , misses = misses
            , readingsEveryShotMissed = run
            , longestRunEveryShotMissed = max before.longestRunEveryShotMissed run
            , sessionHits = before.sessionHits + hits
            , sessionMisses = before.sessionMisses + misses
            }


{-| What the guns are achieving, in the words an operator can act on.

Printed on every reading and read by no decision, which is PR #130's posture for
`quickMessage` and #135's for `attritionIsUnguarded`: an instrument earns the
right to drive a rule once a run has shown it reads sanely, and this one has
never been printed at all. A run that fights and never leaves `NO COMBAT LOG` is
a host not carrying the channel; a run whose landed and missed counts both stay
at zero while the guns cycle is the summary not reaching the bot.

-}
describeOutgoingFire : OutgoingFireMemory -> String
describeOutgoingFire memory =
    if not memory.hostCarriesTheChannel then
        "Outgoing fire: NO COMBAT LOG -- this host does not carry what the guns are doing."

    else
        "Outgoing fire: "
            ++ String.fromInt memory.hits
            ++ " landed / "
            ++ String.fromInt memory.misses
            ++ " missed this reading, "
            ++ String.fromInt memory.readingsEveryShotMissed
            ++ " reading(s) running with every shot missed (worst "
            ++ String.fromInt memory.longestRunEveryShotMissed
            ++ " this session; session "
            ++ String.fromInt memory.sessionHits
            ++ " landed / "
            ++ String.fromInt memory.sessionMisses
            ++ " missed). Nothing decides on this."


{-| How many rats the client has paid this character a bounty for.

**The first thing this bot has ever known about whether it is killing
anything.** Every other combat instrument here reports effort -- shots landed,
shots missed, readings spent on a target, damage taken -- and
`combatStalemate` had to infer "nothing is dying" from the guns being busy,
because no field of any reading said whether anything died. The client says it
outright, once per rat, on `(bounty)`.

**What it counts and what it cannot claim**, stated here rather than left to a
reader of the header:

  - It counts **bounty payouts to this character**, not kills by this ship. A
    rat a fleetmate finished that this ship damaged still pays, and is counted.
    A rat this ship killed whose bounty went entirely elsewhere is not. Anything
    with no bounty -- a structure, an asteroid, a wreck -- writes no line at all,
    however thoroughly it is destroyed.
  - It is a **session total and cannot be split**. The client writes no target
    name on this channel, so no rule can ever ask "how many of these were
    `Centii Loyal Enslaver`", or attribute one to an anomaly, or to a fight.

**That second point is the design rather than a shortfall**, and PR #274 is why
it is worth stating. An anomaly is a pocket of identically named rats, and a
fold keyed on the name reported "702 consecutive misses on a target the guns
went on to hurt" for what was in fact the same name on a different rat. A count
that never attributes cannot mis-attribute. An approximate total that says what
it is beats a per-rat figure that is quietly wrong.

**`Nothing` is not zero.** A host that does not carry the channel leaves
`hostCarriesTheChannel` false and the session total wherever it was, and the
header says `no kill log` rather than `0 kills` -- because a run that killed
nothing and a run nobody counted read identically otherwise, which is the
collapse this file keeps a section on.

Advanced in `updateMemoryForNewReadingFromGame`, which is #102's and #126's
placement rule and the only thing that runs unconditionally on every reading, so
this total cannot be frozen by a branch that stops being reached.

-}
type alias KillCountMemory =
    { hostCarriesTheChannel : Bool
    , thisReading : Int
    , session : Int
    }


killCountAfterReading :
    { before : KillCountMemory
    , kills : Maybe Int
    }
    -> KillCountMemory
killCountAfterReading { before, kills } =
    case kills of
        Nothing ->
            -- The session total is *kept* rather than cleared. A host that
            -- stops answering has not un-killed anything, and a total that
            -- fell back to zero would report a three-hour run as a fresh one.
            { before | hostCarriesTheChannel = False, thisReading = 0 }

        Just count ->
            { hostCarriesTheChannel = True
            , thisReading = count
            , session = before.session + count
            }


{-| The kill count as the header prints it, in saxrat's own abbreviated idiom.

`no kill log` rather than a number when the host does not carry the channel, for
`describeOutgoingFire`'s reason: a bot that printed `0 kills` there would be
reporting a quiet grid for an absent instrument.

-}
describeKillCount : KillCountMemory -> String
describeKillCount memory =
    if not memory.hostCarriesTheChannel then
        "no kill log"

    else
        String.fromInt memory.session ++ " kills"


{-| The client never announces the ship's destruction -- there is no such line
anywhere in the recorded logs. It states the _consequence_ instead, and only
when something asks the capsule to lock.
-}
shipLossFromGameLog : ReadingFromGameClient -> Maybe String
shipLossFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase "ship you are piloting" entry.text
                    && stringContainsIgnoringCase "does not have targeting systems" entry.text
            )
        |> List.head
        |> Maybe.map .text


gameLogEntryIsFromNotifyChannel : EveOnline.ParseUserInterface.GameLogEntry -> Bool
gameLogEntryIsFromNotifyChannel entry =
    case entry.channel of
        Nothing ->
            True

        Just channel ->
            (channel |> String.trim |> String.toLower) == "notify"


{-| A docked reading has no ship UI and is no evidence either way, so it answers
`False` rather than accumulating towards a verdict.
-}
shipUIHasNoModuleButtons : ReadingFromGameClient -> Bool
shipUIHasNoModuleButtons readingFromGameClient =
    case readingFromGameClient.shipUI of
        Nothing ->
            False

        Just shipUI ->
            List.isEmpty shipUI.moduleButtons


shipUIWithoutModuleButtonsReadingsAfter : ReadingFromGameClient -> Int -> Int
shipUIWithoutModuleButtonsReadingsAfter readingFromGameClient countBefore =
    if shipUIHasNoModuleButtons readingFromGameClient then
        countBefore + 1

    else
        0


{-| Several readings rather than one, because the parser drops any slot whose
display region it cannot read -- so one reading finding none may be a parse that
missed.
-}
shipLossReadingsWithoutModulesBeforeVerdict : Int
shipLossReadingsWithoutModulesBeforeVerdict =
    3


{-| Once set, returned unchanged forever with only its age moving.

The latch is the cost asymmetry written into the code: docking early costs the
rest of the session, and un-concluding a loss on a reading that happens to look
normal costs the clone.

-}
shipLossVerdictAfter :
    ReadingFromGameClient
    -> { withoutModulesReadings : Int, verdictBefore : Maybe ShipLossVerdict }
    -> Maybe ShipLossVerdict
shipLossVerdictAfter readingFromGameClient { withoutModulesReadings, verdictBefore } =
    case verdictBefore of
        Just latched ->
            Just { latched | readingsSince = latched.readingsSince + 1 }

        Nothing ->
            case shipLossFromGameLog readingFromGameClient of
                Just clientSentence ->
                    Just
                        { reason =
                            "the client said \""
                                ++ clientSentence
                                ++ "\", which only a capsule hears"
                        , readingsSince = 0
                        }

                Nothing ->
                    if shipLossReadingsWithoutModulesBeforeVerdict <= withoutModulesReadings then
                        Just
                            { reason =
                                "the ship UI has carried no modules at all for "
                                    ++ String.fromInt withoutModulesReadings
                                    ++ " readings, which is the shape of a capsule and not of any ship this bot flies"
                            , readingsSince = 0
                            }

                    else
                        Nothing


{-| How long the pod gets to reach a station before the session ends anyway.

A pod that has been trying to dock for this long is not going to, and an
unbounded retry loop reads in the log exactly like a bot working. When it
expires the session _ends_, so an operator finds out rather than discovering a
capsule parked in a hostile pocket hours later.

Counted in readings, at the eight seconds a reading the recorded runs average --
so about twenty minutes of trying, for a dock that needs no route and no jumps
at all here (`dockAtRandomStationOrStructure` takes whatever this system offers).

**Where the comparison over it is asked is issue #133**, and it is the mission
runner's #126 in this file. See `podRecoveryOutOfTime`, which owns the
comparison now, and `endSessionOnAnExpiredBound`, which asks it from the head of
the decision root.

-}
podRecoveryGiveUpReadings : Int
podRecoveryGiveUpReadings =
    150


{-| The pod recovery that has run past that bound, as a value a case can build.

**Issue #133.** The comparison used to sit inside `recoverPodAfterShipLoss`,
which is below `generalSetupInUserInterface` -- so it was asked only on readings
the tree got that far, while `shipLoss.readingsSince` climbed on every reading
whatever the bot was doing. It is a rule over a record rather than a branch for
the reason `LockRangeState` gives: a rule reachable only through a whole
`BotDecisionContext` can be checked by reading it and no other way.

**The ship UI is a condition and not decoration, and the argument here is not
the mission runner's.** There, the docked outcome names its station through
`dockedStationNameFromInfoPanel`, a live parse that needs
`ensureInfoPanelLocationInfoIsExpanded` to have run, and that is why it cannot
be hoisted. saxrat's docked outcome reads
`context.memory.lastDockedStationNameFromInfoPanel` instead -- memory, readable
on any reading at all -- so nothing about the _reading_ stops it hoisting. It
stays where it is anyway: it is success rather than a bound, and hoisting a
success outcome would change when an ordinary session ends as well as a starved
one, which is a behaviour change this issue has no evidence for.

Which leaves the condition doing the same job it does there for a different
reason. The docked outcome is below the setup list, so a starved-but-docked
session reaches only this rule -- and without the ship UI it would end the
session saying the pod never reached a station, which is false on the reading it
would be printed. `shipUI` is a parse of the reading rather than a state the tree
has to reach, so requiring it costs this bound nothing it needs, and it is the
very test `recoverPodAfterShipLoss` already uses to mean "docked". What is left
uncovered is a pod that is docked and safe while something above holds the tree,
and a docked pod is the state this bound exists to produce.

**Counted in readings rather than attempts.** The other shape -- advance the
counter only on readings this branch was reached -- means a bot held elsewhere
spends none of the budget, which is precisely the runaway the bound exists for.
The cost is stated rather than hidden: a bot starved above this branch for an
unrelated reason now ends its session at 150 readings with the recovery never
attempted, where before it ran until something else stopped it. That is the
better half of the trade, because the pod was not being flown anywhere on any of
those readings either.

-}
podRecoveryOutOfTime :
    { shipLoss : Maybe ShipLossVerdict, shipUIIsShowing : Bool }
    -> Maybe ShipLossVerdict
podRecoveryOutOfTime { shipLoss, shipUIIsShowing } =
    if not shipUIIsShowing then
        Nothing

    else
        shipLoss
            |> Maybe.andThen
                (\verdict ->
                    if podRecoveryGiveUpReadings <= verdict.readingsSince then
                        Just verdict

                    else
                        Nothing
                )


{-| The one line an operator gets when the pod recovery runs out of time.

It names the station the dock was preferring, where one had been docked at this
session, because "which station was it trying to reach" is what a person needs
in order to go and find the capsule. Without one there was never a named
destination, only whatever the surroundings menu offered, which the sentence says
rather than inventing a name.

It also says what the count is. The number is readings since the verdict, not
attempts, so a session that ends here having never printed a `Pod recovery:` line
is telling the operator something about the _rest_ of the bot rather than about
the recovery -- and this bot has no message-box standoff, so that is the likelier
of the two.

-}
describePodRecoveryOutOfTime : { lastDockedStationName : Maybe String, verdict : ShipLossVerdict } -> String
describePodRecoveryOutOfTime { lastDockedStationName, verdict } =
    "The pod has spent "
        ++ String.fromInt verdict.readingsSince
        ++ " readings trying to dock at whatever this system offers"
        ++ (lastDockedStationName
                |> Maybe.map (\name -> ", preferring '" ++ name ++ "'")
                |> Maybe.withDefault " (no station has been docked at this session, so there was none to prefer)"
           )
        ++ ", and has not got there. Ending the session in space rather than retrying forever -- the pod needs recovering by hand. That count is readings since the ship was lost rather than attempts, so if the decision log shows no 'Pod recovery:' line, something above this branch was holding the whole tree."


{-| Stop hunting anomalies and get the pod out.

Placed above the docked-or-in-space split rather than conditioned, so "stop
fighting" is structural: locking, drones, modules and looting all live below
that split and are simply never reached once this answers `Just`.

Ending the session once the pod is docked is deliberate -- the remaining hours
are worth nothing without a ship, and the operator has to find out. That outcome
stays here rather than joining the deadline above because it is success rather
than a bound: hoisting it would change when an ordinary session ends as well as
a starved one.

**The out-of-time outcome is gone from here, and that is #133.** Running out of
time was tested in this branch, below `generalSetupInUserInterface`, over a
counter advanced on every reading -- so anything holding the tree starved the
bound while the number it is compared against went on climbing.
`podRecoveryOutOfTime` owns that comparison now, from the head of
`anomalyBotDecisionRootBeforeApplyingSettings`, and this function is reached only
while the recovery still has time. There is deliberately no second copy of the
test: two places could disagree about whether the pod still has time, and the one
in here is the one a starved tree never reaches.

-}
recoverPodAfterShipLoss : BotDecisionContext -> Maybe DecisionPathNode
recoverPodAfterShipLoss context =
    context.memory.shipLoss
        |> Maybe.map
            (\shipLoss ->
                describeBranch
                    ("The ship is gone -- "
                        ++ shipLoss.reason
                        ++ ". Stop hunting anomalies and get the pod out ("
                        ++ String.fromInt shipLoss.readingsSince
                        ++ " readings since)."
                    )
                    (case context.readingFromGameClient.shipUI of
                        Nothing ->
                            describeBranch
                                ("The pod is docked at "
                                    ++ (context.memory.lastDockedStationNameFromInfoPanel
                                            |> Maybe.map (\name -> "'" ++ name ++ "'")
                                            |> Maybe.withDefault "a station"
                                       )
                                    ++ " and safe. Ending the session: there is no ship left to hunt anomalies with, and that is for the operator to fix."
                                )
                                (Common.DecisionPath.endDecisionPath FinishSession)

                        Just _ ->
                            describeBranch
                                ("Pod recovery: docking at whatever this system offers"
                                    ++ (context.memory.lastDockedStationNameFromInfoPanel
                                            |> Maybe.map (\name -> ", preferring '" ++ name ++ "'")
                                            |> Maybe.withDefault ""
                                       )
                                    ++ "."
                                )
                                (dockAtRandomStationOrStructure context)
                    )
            )


{-| How long the retreat sticks with one celestial before trying another.

A retreat that has not worked yet should try a different corner of the system
rather than re-commanding the one that did not help; rotating on every reading
would instead mean selecting one celestial and warping to whatever the next
reading picked. Twelve readings is the mission runner's number, and its own
alarm is written as three rotations of it.

-}
runAwayCelestialStickyReadings : Int
runAwayCelestialStickyReadings =
    12


{-| Somewhere off this grid, at AU range, that the ship can warp to.

`objectDistanceInMeters` is an `Err` for an AU distance -- the parser reads only
`m` and `km` -- so the placeholder that makes an AU object read as merely far is
exactly what identifies one here. Displayed rows only: the overview virtualises,
and a row that is not rendered reports a region belonging to whatever was
recycled into its place, so selecting one would act on the wrong object.

-}
escapeCelestialsOnOverview : ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
escapeCelestialsOnOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter
            (.objectDistance
                >> Maybe.map (String.toUpper >> String.contains "AU")
                >> Maybe.withDefault False
            )


{-| What the retreat does with the celestial it has chosen.

The panel acts on whatever is selected, so this is two steps rather than one and
the order matters: select the row, then press the button. Extracted as a rule
over plain booleans so the cases can execute it -- `gateActivationStep`'s shape,
for its reason.

-}
type RetreatWarpStep
    = SelectTheCelestial
    | WaitForTheWarpButton
    | PressWarpTo


retreatWarpStep : { panelShowsTheCelestial : Bool, panelOffersWarpTo : Bool } -> RetreatWarpStep
retreatWarpStep { panelShowsTheCelestial, panelOffersWarpTo } =
    if not panelShowsTheCelestial then
        SelectTheCelestial

    else if not panelOffersWarpTo then
        WaitForTheWarpButton

    else
        PressWarpTo


{-| Leave the grid, by the fastest exit the reading offers.

**This was `tetherAtStructure` -- an alias, not a caller** -- so the branch
meaning _this ship is dying, leave now_ was the same one meaning _nothing to do
here, sit somewhere safe_, and it inherited that branch's surroundings-menu
cascade with `Dock` at the top of its entry priority. Run 35 died inside it.

The measurement is what makes the exit worth changing rather than tuning. The
armour guard fired 90 seconds before the loss, into a grid that was quiet:

    first 10 s of the retreat      0 hp
    first 20 s                     0 hp
    first 30 s                    23 hp
    the last 30 s              2,124 hp   (73% of the whole episode)

and the bot spent that free window opening context menus -- `Move mouse to entry
'Safilbab I (Barren)'` seventeen times, `Open context menu on surroundings
button` four times, not one of its 36 blocks in warp. **Nothing was scrambling
or disrupting the ship at any point in the three minutes before it died**, so
the warp was available the whole time. A warp commanded when the guard fired
leaves having taken 23 hitpoints.

So the exit is now select-then-press on the Selected Item panel: two clicks with
nothing to render in between, against a three-level menu cascade that this
codebase already records needing several opens before an entry is recognised.

**Docking is not preferred and is not reached.** It is right for the wind-down
and wrong for a hull losing 57 hp/s; `tetherAtStructure` keeps its own callers
and is reached from here only when the overview offers nothing at AU range at
all, which is the case where there is no celestial to warp to.

The drones still come home first. #139 measured the recall as a fifth of retreat
latency and absent from the longest retreats, so it is not what to cut.

-}
runAway : BotDecisionContext -> DecisionPathNode
runAway context =
    case
        escapeCelestialsOnOverview context.readingFromGameClient
            |> Common.Basics.listElementAtWrappedIndex
                (context.memory.readingsCount // runAwayCelestialStickyReadings)
    of
        Nothing ->
            describeBranch
                "Get out -- nothing at AU range on the overview to warp to, so fall back to the surroundings menu."
                (tetherAtStructure context)

        Just celestial ->
            let
                celestialName =
                    celestial.objectName |> Maybe.withDefault "a celestial"

                warpToButton =
                    selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo"
            in
            case
                retreatWarpStep
                    { panelShowsTheCelestial =
                        selectedItemIsOverviewEntry context.readingFromGameClient celestial
                    , panelOffersWarpTo = warpToButton /= Nothing
                    }
            of
                SelectTheCelestial ->
                    describeBranch
                        ("Get out -- select '" ++ celestialName ++ "', so the panel's own Warp To acts on it.")
                        (clickUiElement celestial.uiNode)

                WaitForTheWarpButton ->
                    describeBranch
                        ("Get out -- '" ++ celestialName ++ "' is selected but the panel offers no 'selectedItemWarpTo' yet.")
                        waitForProgressInGame

                PressWarpTo ->
                    case warpToButton of
                        Nothing ->
                            describeBranch "Get out -- the warp button went away between reading it and pressing it."
                                waitForProgressInGame

                        Just button ->
                            describeBranch
                                ("Get out -- warp to '"
                                    ++ celestialName
                                    ++ "' at "
                                    ++ (celestial.objectDistance |> Maybe.withDefault "range")
                                    ++ "."
                                )
                                (ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                                    (clickUiElement button)
                                )


continueIfShouldHide : { ifShouldHide : DecisionPathNode } -> BotDecisionContext -> Maybe DecisionPathNode
continueIfShouldHide config context =
    case
        context.eventContext |> EveOnline.BotFramework.secondsToSessionEnd |> Maybe.andThen (nothingFromIntIfGreaterThan 200)
    of
        Just secondsToSessionEnd ->
            Just
                (describeBranch ("Session ends in " ++ (secondsToSessionEnd |> String.fromInt) ++ " seconds.")
                    config.ifShouldHide
                )

        Nothing ->
            if context.eventContext.botSettings.hideWhenNeutralInLocal /= AppSettings.Yes then
                Nothing

            else
                case neutralOrHostileInLocal context.readingFromGameClient of
                    Nothing ->
                        Just (describeBranch "I don't see the local chat window." askForHelpToGetUnstuck)

                    Just True ->
                        Just (describeBranch "There is an enemy or neutral in local chat." config.ifShouldHide)

                    Just False ->
                        Nothing


{-| Whether local chat carries anyone this bot does not have good standing
with. `Nothing` when the local chat window itself is not in the reading --
distinct from `Just False`, which is "the window is there and everyone in it
reads as friendly" -- so a caller that cannot tell the difference does not
default to "safe".

Pulled out of `continueIfShouldHide` so `updateMemoryForNewReadingFromGame` can
ask the same question `hideFromNeutralInLocal` is answering, which is what lets
`hidingFromNeutralPastFirstHop` be latched from the reading rather than from a
decision the memory update never sees. Two callers reading two copies of this
would drift the moment one of them is retuned and the other is not, the way
`ammoSwapDisarmDamageBudget` stays deliberately un-inherited elsewhere in this
file for the opposite reason -- here the two questions are the same question and
should never be two answers.

-}
neutralOrHostileInLocal : ReadingFromGameClient -> Maybe Bool
neutralOrHostileInLocal readingFromGameClient =
    readingFromGameClient
        |> localChatWindowFromUserInterface
        |> Maybe.map
            (\localChatWindow ->
                let
                    chatUserHasGoodStanding chatUser =
                        goodStandingPatterns
                            |> List.any
                                (\goodStandingPattern ->
                                    chatUser.standingIconHint
                                        |> Maybe.map (stringContainsIgnoringCase goodStandingPattern)
                                        |> Maybe.withDefault False
                                )

                    subsetOfUsersWithNoGoodStanding =
                        localChatWindow.userlist
                            |> Maybe.map .visibleUsers
                            |> Maybe.withDefault []
                            |> List.filter (chatUserHasGoodStanding >> not)
                in
                1 < (subsetOfUsersWithNoGoodStanding |> List.length)
            )


{-| The response to `hide-when-neutral-in-local`: get off the current grid
first, then keep moving toward the next hunting ground, rather than either
alone.

`runAway` by itself is right for the first reaction and wrong as the whole
answer here -- it rotates among whatever is at AU range on the overview every
`runAwayCelestialStickyReadings` readings and nothing in it ever leaves the
system, so a ship that only ever changes which rock it orbits is still standing
in the same local chat the neutral is in. `jumpToNextSystem` by itself is wrong
the other way: reached with no route yet set, its first move is to _ask_ the
host for one and wait, which is exactly the readings this setting exists to
react to fastest -- the ship sitting still, exposed, on whatever grid it was
already on when the neutral showed up.

So this is the two-step sequence the setting's own name suggests, and the order
is fixed rather than chosen fresh each reading:

1.  **Not yet moving**: `runAway`'s own celestial warp -- immediate, needs
    nothing from ESI or the hunt circuit, and is the fastest exit this bot has.
2.  **Currently warping or jumping**: wait it out, `decideNextActionWhenInSpace`'s
    own `HOOOOONK in warp` guard reused rather than a second copy of it -- acting
    on route or gate UI mid-transit is not a state any other branch here risks
    either.
3.  **Landed since the transit began**: `jumpToNextSystem`, unchanged -- asking
    the host for the next hunting ground and travelling the route it sets exactly
    as when there is nothing left to hunt in this system. Reused rather than
    reimplemented so a route already in flight (set by ordinary hunting before
    the neutral ever showed up) is simply continued rather than abandoned.

**Which of the three applies is `hidingFromNeutralPastFirstHop`, latched in the
memory update rather than derived here**, because a decision cannot write
memory and the transition (has this hide episode already gotten the ship moving
at all) has to survive across however many readings and however many hops it
takes. It is set the first reading the ship is seen warping or jumping while
the neutral condition holds -- covering a celestial warp just issued by step 1
_and_ a gate jump `jumpToNextSystem` has already put the ship on the far side
of, so a second neutral met after the first jump does not fall back to a
pointless celestial hop before continuing on -- and cleared the moment the
neutral condition itself clears, so the next hide episode starts fresh at step
1 rather than inheriting a stale "already moving".

-}
hideFromNeutralInLocal : BotDecisionContext -> DecisionPathNode
hideFromNeutralInLocal context =
    if shipIsWarpingOrJumping context.readingFromGameClient then
        describeBranch
            "Hiding from local: already warping or jumping clear of this grid -- let it land before deciding the next hop."
            (returnDronesToBay context waitForProgressInGame)

    else if context.memory.hidingFromNeutralPastFirstHop then
        describeBranch
            "Hiding from local: off the grid this hide episode already fled, so keep moving toward the next hunting ground."
            (jumpToNextSystem context)

    else
        runAway context


{-| Root-caused live: this only ever searched the surroundings-button menu
for "structures" (a player-owned Upwell citadel/etc.), with no fallback.
A system with only NPC stations -- no player structures at all, confirmed
live via a memory dump of the actual menu tree, which had no entry
containing "structures" anywhere -- has no way for that search to
succeed, ever, regardless of how many ticks it's given: the entry simply
does not exist. `getNextContextMenu` only runs when the framework's own
"no progress" check sees the open menu(s) change between readings, so
once the (accidentally, from repeatedly right-clicking the same screen
position) hover-triggered submenu stabilizes, that search never even
gets attempted again -- it just discards and reopens forever, which is
what actually showed up live (confirmed via `screen -X hardcopy` on the
bot's own session and a live memory dump correlated with the rendered
UI). Mirrors `dockAtRandomStationOrStructure`'s already-proven
`[ "structures", "station" ]` fallback and its "Dock" priority (ahead of
Warp/Approach) -- tethering at a player structure is still preferred
when one exists, but an NPC station to dock at is a real, working
fallback when it doesn't, rather than looping on a search that can never
succeed.
-}
tetherAtStructure : BotDecisionContext -> DecisionPathNode
tetherAtStructure context =
    let
        chooseNextMenuEntry followingChoice =
            MenuEntryWithCustomChoice
                { describeChoice = "dock, else warp/approach tether"
                , chooseEntry =
                    \currentMenu ->
                        let
                            suitableMenuEntries =
                                List.filter menuEntryIsSuitable currentMenu.entries
                        in
                        [ withTextContainingIgnoringCase "Dock"
                        , withTextContainingIgnoringCase "Warp Fleet"
                        , withTextContainingIgnoringCase "Warp Wing"
                        , withTextContainingIgnoringCase "Warp Squad"
                        , withTextContainingIgnoringCase "Warp"
                        , withTextContainingIgnoringCase "Approach"
                        , Common.Basics.listElementAtWrappedIndex 0
                        ]
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                            |> Maybe.map (\menuEntry -> ( menuEntry, followingChoice ))
                }
    in
    ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
        (useContextMenuCascadeOnListSurroundingsButton
            (useMenuEntryWithTextContainingFirstOf [ "structures", "station" ]
                (chooseNextMenuEntry
                    (chooseNextMenuEntry MenuCascadeCompleted)
                )
            )
            context
        )


alignToStructure : ShipUI -> BotDecisionContext -> Maybe DecisionPathNode
alignToStructure shipUI context =
    let
        chooseNextMenuEntry followingChoice =
            MenuEntryWithCustomChoice
                { describeChoice = "align"
                , chooseEntry =
                    \currentMenu ->
                        let
                            suitableMenuEntries =
                                List.filter menuEntryIsSuitable currentMenu.entries
                        in
                        [ withTextContainingIgnoringCase "Align to"
                        , Common.Basics.listElementAtWrappedIndex 0
                        , withTextContainingIgnoringCase "Track"
                        ]
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                            |> Maybe.map (\menuEntry -> ( menuEntry, followingChoice ))
                }
    in
    -- this is what case statements are for, dude
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverAlign then
        Nothing

    else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverRange then
        Nothing

    else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverOrbit then
        Nothing

    else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverWarp then
        Nothing

    else
        Just
            (useContextMenuCascadeOnListSurroundingsButton
                (useMenuEntryWithTextContainingFirstOf [ "structures" ]
                    (chooseNextMenuEntry
                        (chooseNextMenuEntry MenuCascadeCompleted)
                    )
                )
                context
            )


{-| The combat messages currently faded onto the screen, oldest first.

EVE keeps the floating damage feed in the UI tree, so the same lines it writes
to ~/Documents/EVE/logs/Gamelogs are readable live with no file involved. One
`CombatMessage` node holds the whole feed, with one child per message and the
message split across several labels ("43", " to ", "Mercenary Elite Fighter",
the effect) -- so a message is its child's texts joined, not any single label.

This is a display buffer, not a log: messages age off the screen and disappear
from the tree with them. It answers "what just happened to whom, for how much"
over the last few seconds; anything needing history should read the gamelog file
instead.

The markup is EVE's own colour and font tagging, stripped here because whatever
reads this is a human in a terminal.

-}
visibleCombatMessages : ReadingFromGameClient -> List String
visibleCombatMessages readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "CombatMessage")
        |> List.concatMap EveOnline.ParseUserInterface.listChildrenWithDisplayRegion
        |> List.map
            (\messageNode ->
                messageNode.uiNode
                    |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                    |> List.map EveOnline.ParseUserInterface.stripHtmlTags
                    |> String.join " "
                    |> String.words
                    |> String.join " "
            )
        |> List.filter (String.isEmpty >> not)


{-| The on-screen combat feed used to be printed with every status line, and it
was the largest thing in the log while being almost none of its information.

Issue #190. `describeVisibleCombatMessages` rendered up to six lines of the
widget on every reading: 9,639 of run 20's 25,762 lines and 98,700 of run 21's
296,465, a third of each log. The widget is a rolling on-screen window, so
consecutive readings mostly re-render the same six lines -- 1,376 of run 20's
1,377 blocks were byte-identical to the one before, and 99.5% of run 21's. It
also outlives the fight it describes, because messages age off the screen rather
than off the grid: 1,344 of run 20's 1,377 blocks were printed on readings whose
own decision line says the ship is docked.

Nothing a decision uses is lost, because no decision ever read it. Nothing an
operator uses is lost either: the host reads EVE's `(combat)` channel directly
and sums the incoming half into `incomingDamageSinceLastReading`, which
`describeIncomingDamage` already prints on every reading -- scoped to the
reading, with the attackers named, and unable to go stale the way a display
buffer does. The client's own lines are in the same log a second time besides,
echoed by the host as `game log: ... (combat) ...`.

`visibleCombatMessages` above is now unused, kept deliberately rather than
deleted, for the reason the mission runner kept its copy when it dropped the same
clause: it encodes which UI nodes carry combat text and how to read them, which
is the expensive part to rediscover, and any future in-decision use of combat
state wants exactly that.

**Both directions of the channel are printed now**, which is the one sentence in
this argument that has moved. #190 recorded the outgoing half as genuinely
unreported here and said adding it would be a separate change with its own
evidence; that change is `describeOutgoingFire`, and its evidence is in
`outgoingFireAfterReading`. So the summary this removal pointed at as its
replacement is now the whole summary rather than half of one, and neither half
is a display buffer that can outlive the fight.

-}
combatFeedIsReportedByTheHostGameLog : ()
combatFeedIsReportedByTheHostGameLog =
    ()


{-| The quick message this reading carries, with what the parser dropped to get it.

Reads the same two `List.head`s `parseQuickMessage` does, and reports how many
candidates each of them chose from -- see `QuickMessageSighting` for why those
counts are the evidence rather than an ornament. `readingsSince` is `0` here
because this is a message on the screen now; ageing it is
`quickMessageAfterReading`'s job.

The text is trimmed of surrounding whitespace and nothing else. Case,
punctuation and interior spacing are exactly what the client wrote, because the
next matcher is going to be written against this string and a normalisation
applied here is one nobody downstream can undo.

-}
quickMessageOnScreen : ReadingFromGameClient -> Maybe QuickMessageSighting
quickMessageOnScreen readingFromGameClient =
    readingFromGameClient.layerAbovemain
        |> Maybe.andThen
            (\layerAbovemain ->
                layerAbovemain.quickMessage
                    |> Maybe.map
                        (\quickMessage ->
                            { text = String.trim quickMessage.text
                            , messagesInLayer =
                                layerAbovemain.uiNode
                                    |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
                                    |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "QuickMessage")
                                    |> List.length
                            , displayTextsInMessage =
                                quickMessage.uiNode.uiNode
                                    |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                                    |> List.length
                            , readingsSince = 0
                            }
                        )
            )


{-| The sighting to carry into the next reading.

A message on the screen replaces whatever was remembered and starts the age at
zero; a reading with no message ages the last one by one. Nothing expires it
within the session, because an expiry would be a number with no evidence behind
it and the age already says how stale the sighting is -- the same reasoning
`ShipLossVerdict` is latched on.

Written as a rule over a record rather than inline in
`updateMemoryForNewReadingFromGame` so a case can fold it over a sequence of
readings and see the age advance, which is the half that can be wrong.

-}
quickMessageAfterReading :
    { onScreenNow : Maybe QuickMessageSighting
    , before : Maybe QuickMessageSighting
    }
    -> Maybe QuickMessageSighting
quickMessageAfterReading state =
    case state.onScreenNow of
        Just onScreenNow ->
            Just { onScreenNow | readingsSince = 0 }

        Nothing ->
            state.before
                |> Maybe.map (\before -> { before | readingsSince = before.readingsSince + 1 })


{-| How much of a quick message the status line will carry.

Generous on purpose. The point of printing this at all is that the wording
becomes evidence, and a message clipped to a few characters is a message nobody
can write a matcher from -- the cap exists so one pathological string cannot push
the rest of the status line out of the host's own 4,000-character log truncation,
not to keep the line tidy.

-}
quickMessageStatusCharacterBudget : Int
quickMessageStatusCharacterBudget =
    400


{-| How long a quick message stays in the status line after it left the screen.

The sighting is carried forward with an age so a notice can be read beside the
decision that followed it, which is a reading or two rather than minutes. Past
this it is a notice from minutes ago printed next to a reading it has nothing to
do with, so the clause says "none recent" instead of reprinting it.

-}
quickMessageStaleAfterReadings : Int
quickMessageStaleAfterReadings =
    100


{-| A quick message rendered as one line, losing nothing that cannot be undone.

Two transformations and no others. The text is cut to
`quickMessageStatusCharacterBudget` characters -- and `describeQuickMessage` says
so, with the original length, whenever it cuts. And a newline, carriage return or
tab is escaped rather than emitted, because the status line is line-structured:
the host prints it after the tick marker, `stall_watch.py` reads the first line,
and a message carrying a newline would otherwise split a clause across two lines
of the log. Backslash is escaped first so the mapping stays reversible.

Case, punctuation and interior spacing are untouched.

-}
quickMessageTextForStatusLine : String -> String
quickMessageTextForStatusLine text =
    text
        |> String.left quickMessageStatusCharacterBudget
        |> String.replace "\\" "\\\\"
        |> String.replace "\n" "\\n"
        |> String.replace "\u{000D}" "\\r"
        |> String.replace "\t" "\\t"


{-| The quick message clause, which says what the client wrote and how old it is.

Printed on every reading, including the ones with nothing to report: a clause
that appears only when there is something to say leaves "the client said nothing"
and "nothing is reading the client" grepping identically, and telling those apart
is the first thing #123 wants from a run.

Whether the message is on the screen _now_ is the first thing in the clause and
is never implied. A stale message printed as if it were current would be worse
than not printing one at all, since a later reader would date the wording to the
wrong decision.

-}
describeQuickMessage : Maybe QuickMessageSighting -> String
describeQuickMessage sighting =
    case sighting of
        Nothing ->
            "Quick message: none on this reading, and none seen this session."

        Just seen ->
            if quickMessageStaleAfterReadings < seen.readingsSince then
                "Quick message: none recent."

            else
                "Quick msg"
                    ++ (if seen.readingsSince == 0 then
                            " (now)"

                        else
                            " (" ++ String.fromInt seen.readingsSince ++ " ago)"
                       )
                    ++ ": \""
                    ++ quickMessageTextForStatusLine seen.text
                    ++ "\""
                    ++ (if String.length seen.text <= quickMessageStatusCharacterBudget then
                            ""

                        else
                            " (CAPPED "
                                ++ String.fromInt quickMessageStatusCharacterBudget
                                ++ "/"
                                ++ String.fromInt (String.length seen.text)
                                ++ ")"
                       )
                    ++ (if seen.messagesInLayer <= 1 then
                            ""

                        else
                            " (1 of "
                                ++ String.fromInt seen.messagesInLayer
                                ++ " quick messages in the layer -- the parser keeps the first and drops the rest)"
                       )
                    ++ (if seen.displayTextsInMessage <= 1 then
                            ""

                        else
                            " (1 of "
                                ++ String.fromInt seen.displayTextsInMessage
                                ++ " display texts in the message -- the parser keeps the first and drops the rest)"
                       )
                    ++ "."


{-| 2020-07-11 Discovery by Viktor:
The entries for structures in the menu from the SurroundingsButton can be nested one level deeper than the ones for stations.
In other words, not all structures appear directly under the "structures" entry.
-}
dockAtRandomStationOrStructure : BotDecisionContext -> DecisionPathNode
dockAtRandomStationOrStructure context =
    let
        chooseNextMenuEntry followingChoice =
            MenuEntryWithCustomChoice
                { describeChoice = "Dock if we can?"
                , chooseEntry =
                    \currentMenu ->
                        let
                            suitableMenuEntries =
                                List.filter menuEntryIsSuitable currentMenu.entries
                        in
                        [ withTextContainingIgnoringCase "Dock"
                        , List.filter (.text >> stringContainsIgnoringCase "station")
                            >> Common.Basics.listElementAtWrappedIndex 0
                        , Common.Basics.listElementAtWrappedIndex 0
                        ]
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                            |> Maybe.map (\menuEntry -> ( menuEntry, followingChoice ))
                }
    in
    returnDronesToBay context
        (describeBranch "g'wan, git"
            (useContextMenuCascadeOnListSurroundingsButton
                (useMenuEntryWithTextContainingFirstOf [ "structures", "station" ]
                    (chooseNextMenuEntry
                        (chooseNextMenuEntry MenuCascadeCompleted)
                    )
                )
                context
            )
        )


decideNextActionWhenInSpace : BotDecisionContext -> SeeUndockingComplete -> DecisionPathNode
decideNextActionWhenInSpace context seeUndockingComplete =
    clearStrayContextMenu context
        |> Maybe.withDefault
            (if shipIsWarpingOrJumping context.readingFromGameClient then
                describeBranch "HOOOOONK in warp"
                    (returnDronesToBay context waitForProgressInGame)

             else
                case context.readingFromGameClient.probeScannerWindow of
                    Nothing ->
                        describeBranch "No probe window"
                            (case manageMiddleRowModules context seeUndockingComplete of
                                Just moduleAction ->
                                    moduleAction

                                Nothing ->
                                    decideActionInAnomaly
                                        -- The clock, said rather than spelled. This
                                        -- branch has no anomaly to be in: the memory
                                        -- is filed under the ID the probe scanner
                                        -- gives, and there is no scanner here, so
                                        -- `arrivalInAnomalyAgeSecondsFromMemory` would
                                        -- answer its `Maybe.withDefault 0` and tether
                                        -- the ship for the full wait at a site it
                                        -- cannot name. What this path means is that
                                        -- the wait is already over, so it passes the
                                        -- setting itself: `waitTimeRemainingSeconds`
                                        -- is 0 and the 120-second loot backstop is
                                        -- still live, which is what the literal `600`
                                        -- here did while `anomalyWaitTimeSeconds`
                                        -- happened to also be 600 -- and goes on
                                        -- meaning it when an operator changes that.
                                        { arrivalInAnomalyAgeSeconds =
                                            context.eventContext.botSettings.anomalyWaitTimeSeconds
                                        }
                                        context
                                        seeUndockingComplete
                                        (siteProgressStepOrElse context (jumpToNextSystem context))
                            )

                    Just probeScannerWindow ->
                        case context.readingFromGameClient |> getCurrentAnomalyIDAsSeenInProbeScanner of
                            Nothing ->
                                let
                                    pickAnotherAnomalyOrLeaveViaScanResults =
                                        case
                                            anomaliesWorthHunting
                                                (anomalyChoiceFromDecisionContext context)
                                                context.readingFromGameClient
                                                |> listElementAtWrappedIndex (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                                        of
                                            Nothing ->
                                                describeBranch
                                                    ("I see "
                                                        ++ (probeScannerWindow.scanResults |> List.length |> String.fromInt)
                                                        ++ " scan results, and no matching anomaly. Git!"
                                                    )
                                                    (jumpToNextSystem context)

                                            Just _ ->
                                                describeBranch "Found matching anomaly." (enterAnomaly { ifNoAcceptableAnomalyAvailable = tetherAtStructure context } context)

                                    -- "Warp to Site" opportunities (e.g. "Sansha's
                                    -- Command Relay Outpost") and following acceleration
                                    -- gates through a multi-pocket site both take
                                    -- priority over the normal probe-scan hunt loop --
                                    -- but only once there's nothing left to fight or
                                    -- loot right now (checked by the caller before
                                    -- falling through to this), so an opportunity
                                    -- appearing mid-combat doesn't pull the ship away
                                    -- from a fight already in progress.
                                    --
                                    -- Which of the two comes first is `siteProgressStep`,
                                    -- which carries the measurement: the gate is the work
                                    -- in front of the ship, and a "Warp to Site" offered
                                    -- while a gate is in reach is the panel still showing
                                    -- the site the ship is standing in.
                                    pickAnotherAnomalyOrLeave =
                                        siteProgressStepOrElse context pickAnotherAnomalyOrLeaveViaScanResults
                                in
                                -- The anomaly's own signature can drop off the probe
                                -- scanner (site "resolved"/expired) while rats are
                                -- still alive or wrecks are still sitting on the
                                -- overview -- don't abandon those just because the
                                -- site itself stopped showing up here; keep fighting
                                -- and looting until the grid is actually clear. Same
                                -- for a stray locked target (e.g. a cargo container):
                                -- warping away drops the lock as a side effect without
                                -- ever running the unlock cascade, so check for one
                                -- here too rather than only inside decideActionInAnomaly.
                                if gridStillHasSomethingToDo context.memory.incomingDamage context.readingFromGameClient then
                                    describeBranch "The anomaly no longer shows on the scanner, but there is still something to attack or loot here."
                                        (decideActionInAnomaly
                                            { arrivalInAnomalyAgeSeconds = arrivalInAnomalyAgeSecondsFromMemory context }
                                            context
                                            seeUndockingComplete
                                            pickAnotherAnomalyOrLeave
                                        )

                                else
                                    pickAnotherAnomalyOrLeave

                            Just _ ->
                                case manageMiddleRowModules context seeUndockingComplete of
                                    Just moduleAction ->
                                        moduleAction

                                    Nothing ->
                                        let
                                            returnDronesAndEnterAnomaly { ifNoAcceptableAnomalyAvailable } =
                                                returnDronesToBay context
                                                    (describeBranch "No drones to return."
                                                        (enterAnomaly { ifNoAcceptableAnomalyAvailable = ifNoAcceptableAnomalyAvailable } context)
                                                    )

                                            returnDronesAndEnterAnomalyOrWait =
                                                returnDronesAndEnterAnomaly
                                                    { ifNoAcceptableAnomalyAvailable =
                                                        describeBranch "Try autopilot?" (jumpToNextSystem context)
                                                    }
                                        in
                                        case context.readingFromGameClient |> getCurrentAnomalyIDAsSeenInProbeScanner of
                                            Nothing ->
                                                describeBranch "Looks like we are not in an anomaly." returnDronesAndEnterAnomalyOrWait

                                            Just anomalyID ->
                                                case memoryOfAnomalyWithID anomalyID context.memory of
                                                    Nothing ->
                                                        describeBranch
                                                            ("Program error: Did not find memory of anomaly " ++ anomalyID)
                                                            waitForProgressInGame

                                                    Just memoryOfAnomaly ->
                                                        let
                                                            arrivalInAnomalyAgeSeconds =
                                                                (context.eventContext.timeInMilliseconds - memoryOfAnomaly.arrivalTime.milliseconds) // 1000
                                                        in
                                                        describeBranch
                                                            ("We are in anomaly "
                                                                ++ (context.readingFromGameClient
                                                                        |> getCurrentAnomalyIdentityAsSeenInProbeScanner
                                                                        |> Maybe.withDefault { id = anomalyID, name = Nothing, group = Nothing }
                                                                        |> describeAnomalyIdentity
                                                                   )
                                                                ++ " since "
                                                                ++ String.fromInt arrivalInAnomalyAgeSeconds
                                                                ++ " seconds."
                                                            )
                                                            (case findReasonToAvoidAnomalyFromMemory (anomalyChoiceFromDecisionContext context) { anomalyID = anomalyID } of
                                                                Just reasonToAvoidAnomaly ->
                                                                    describeBranch
                                                                        ("Found a reason to avoid this anomaly: "
                                                                            ++ describeReasonToAvoidAnomaly reasonToAvoidAnomaly
                                                                        )
                                                                        (returnDronesAndEnterAnomaly
                                                                            { ifNoAcceptableAnomalyAvailable =
                                                                                describeBranch "Get out of this anomaly."
                                                                                    (enterAnomaly { ifNoAcceptableAnomalyAvailable = tetherAtStructure context } context)
                                                                            }
                                                                        )

                                                                Nothing ->
                                                                    decideActionInAnomaly
                                                                        { arrivalInAnomalyAgeSeconds = arrivalInAnomalyAgeSeconds }
                                                                        context
                                                                        seeUndockingComplete
                                                                        returnDronesAndEnterAnomalyOrWait
                                                            )
            )


undockUsingStationWindow : BotDecisionContext -> DecisionPathNode
undockUsingStationWindow context =
    case context.readingFromGameClient.stationWindow of
        Nothing ->
            describeBranch "I do not see the station window." askForHelpToGetUnstuck

        Just stationWindow ->
            case stationWindow.undockButton of
                Nothing ->
                    case stationWindow.abortUndockButton of
                        Nothing ->
                            describeBranch "I do not see the undock button." askForHelpToGetUnstuck

                        Just _ ->
                            describeBranch "I see we are already undocking." waitForProgressInGame

                Just undockButton ->
                    case stationWindow.abortUndockButton of
                        Nothing ->
                            case undockClickedStepsAgo context.previousStepsEffects undockButton.totalDisplayRegion of
                                Just stepsAgo ->
                                    describeBranch
                                        ("I clicked undock "
                                            ++ String.fromInt stepsAgo
                                            ++ " step(s) ago and the client is still showing the undock button -- wait rather than click it again, which would abort the undock."
                                        )
                                        waitForProgressInGame

                                Nothing ->
                                    describeBranch "Click on the button to undock."
                                        (decideActionForCurrentStep
                                            (mouseClickOnUIElement MouseButtonLeft undockButton
                                                |> Result.withDefault []
                                            )
                                        )

                        Just _ ->
                            describeBranch "I see we are already undocking." waitForProgressInGame


{-| One button occupies the undock slot and it changes what it does under the
cursor: "Undock" while docked, then "Abort Undock" and "Undocking..." once the
undock is under way. `parseStationWindowFromUITreeRoot` reads all three, so a
_decision_ can never choose to abort -- `undockButton` is `Nothing` for the
whole of the second state.

That is not enough, because the decision and the click are not the same moment.
The bot re-derives its decision on every framework event and dispatches at most
once per cycle, and run 20 dispatched the undock click **twice inside one tick**
-- at substeps `.2` and `.5`, three steps apart -- on every tick, 214 times. The
first click starts the undock; a second or two later the second lands on the same
screen point, which by then reads "Abort Undock", and the ship goes back into the
station. The client says so in its own log:

    05:39:27 (None)   Undocking from Amarr VIII (Oris) ... to Amarr solar system.
    05:39:36 (notify) Can't do that while undocking. You should be squeezed out in 2 seconds.
    05:39:41 (notify) Docking operation already in progress. Estimated time left: 10 seconds.

An undock leaves no line when it is _clicked_, only when it _starts_, so those
three lines are the whole of what the client will say about a loop that ran for
289 readings.

This is `moduleButtonClickSettlingSteps`' failure exactly -- "a second click,
which turned it _off_" -- on a button whose second click is much more expensive,
since it puts the ship back in the station rather than switching a module off.

**Eight steps rather than the framework's five**, because the two costs are not
symmetric. Steps here run about 3.4 to a reading, so eight is roughly two
readings: comfortably past the observed three-step gap between the two
dispatches, and short of the ten steps `lastStepsEffects` actually stores, so the
bound is a real bound rather than "as long as we can see" -- the margin the
framework's own comment records the original version lacking.

It bounds the _re-click_ and nothing else. A click that genuinely never landed is
retried on the next tick, and the cross-tick case is left to the abort button
above, which is the client's own evidence rather than a count -- it fired 71
times in run 20, so it works and was simply being outrun.

-}
undockClickSettlingSteps : Int
undockClickSettlingSteps =
    8


undockClickedStepsAgo :
    List (List EffectOnWindow.EffectOnWindowStruct)
    -> EveOnline.ParseUserInterface.DisplayRegion
    -> Maybe Int
undockClickedStepsAgo previousStepsEffects undockButtonRegion =
    previousStepsEffects
        |> List.take undockClickSettlingSteps
        |> List.indexedMap Tuple.pair
        |> List.filter
            (\( _, stepEffects ) ->
                stepEffects
                    |> EveOnline.BotFramework.findMouseButtonClickLocationsInListOfEffects MouseButtonLeft
                    |> List.any
                        (EveOnline.BotFramework.isPointInRectangle
                            (EveOnline.BotFramework.growRegionOnAllSides 1 undockButtonRegion)
                        )
            )
        |> List.head
        |> Maybe.map (Tuple.first >> (+) 1)


{-| Readings a fight may go nowhere for before the bot closes the range on it.

**Derived from the corpus rather than picked.** Replayed over the twenty-two
recorded saxrat logs whose status line carries a reading index -- runs 31 through
50, counting _readings_ and not decision lines, since the status text is
reprinted under every decision -- the two populations are:

  - stretches of a fight that ended in a kill: the longest went **130** readings
    between kills (run 36's `QRH-534`, itself an ammo-swap deadlock that broke on
    its own), then 55, 43, 34 and 27, with the other 440 of 445 at 19 or below;
  - stretches that never produced a kill: 73 at the top of the ordinary ones --
    fights the bot broke off by leaving the anomaly -- and then **932, 1443 and
    1582**, which are run 48's `OTC-000` and run 43's own stall.

So the gap between "a fight that was still going to win" and "a fight that was
never going to" is 130 to 932, and it is empty. This sits inside it with margin
both ways: half again as long as the longest fight the guns ever won from here,
and less than a quarter of the shortest stall on record.

The reading before this one is what makes the number cheap to be wrong about in
the _early_ direction: what happens at this bound is an approach, and approaching
a rat the guns are already killing costs the fight nothing. `combatStalemateLeaveReadings`
is the expensive one and is argued separately.

-}
combatStalemateApproachReadings : Int
combatStalemateApproachReadings =
    200


{-| Readings a fight may go nowhere for before the bot gives the grid up.

A hundred readings after the approach, which is what closing the range is given
to work. Run 48's target sat at 20,000 m, exactly on the ammo swap's crossover
and inside its dead band, so the swap could not decide and the guns held a
long-range charge at knife range. Measured on the readings the corpus records the
ship actually approaching on, it closes **1,000 m per reading** -- so leaving the
dead band takes three or four readings and crossing the whole 20 km takes twenty.
A hundred is five times the second and twenty-five times the first.

Still inside the measured gap: 300 is well under the 932 of the shortest recorded
stall, and more than twice the 130 of the longest fight the guns ever won from
this branch.

-}
combatStalemateLeaveReadings : Int
combatStalemateLeaveReadings =
    300


{-| What to do about a fight that has stopped killing anything.

Three rungs rather than two, because the cheap answer and the expensive one are
not the same answer. Closing the range costs the fight nothing and is very likely
the fix -- run 48's deadlock is the target parked on the ammo swap's crossover --
while leaving abandons a fight the bot may still win, and is only right once
closing the range has been tried and has not helped.

-}
type CombatStalemateVerdict
    = FightIsStillGettingSomewhere
    | CloseTheRangeOnTheTarget
    | LeaveThisGrid


combatStalemateVerdict : Int -> CombatStalemateVerdict
combatStalemateVerdict readings =
    if readings < combatStalemateApproachReadings then
        FightIsStillGettingSomewhere

    else if readings < combatStalemateLeaveReadings then
        CloseTheRangeOnTheTarget

    else
        LeaveThisGrid


{-| Whether this reading is one a stalemate could even be accumulating on.

The target bar is not empty and the overview still shows a rat: the guns have
something to shoot and something to shoot at. Everything else -- travelling,
warping, docked, a cleared grid -- is not a fight and clears the count rather
than carrying it into the next anomaly, which is what would let a bound fire on
arrival somewhere it had never been.

-}
combatFightIsUnderway : ReadingFromGameClient -> Bool
combatFightIsUnderway readingFromGameClient =
    not (List.isEmpty readingFromGameClient.targets)
        && not (List.isEmpty (getNamesOfRatsInOverview readingFromGameClient))


{-| The stalemate count after one more reading.

Advanced in `updateMemoryForNewReadingFromGame` and nowhere else, which is #102's
and #126's placement rule and the reason this can be a count of readings at all:
that is the one thing running unconditionally on every reading, so a branch that
stops being reached cannot freeze the count that is supposed to bound it. The
mission runner's message-box standoff records what the other placement costs.

The count only ever rises while the fight stands still, so the bound is crossed
once and stays crossed -- the branch does not fall back to waiting on the reading
after it acts.

-}
combatStalemateAfterReading :
    { before : CombatStalemate
    , fightIsUnderway : Bool
    , ratsInOverview : Int
    }
    -> CombatStalemate
combatStalemateAfterReading { before, fightIsUnderway, ratsInOverview } =
    if not fightIsUnderway then
        { readings = 0, ratsInOverview = ratsInOverview }

    else if ratsInOverview < before.ratsInOverview then
        { readings = 0, ratsInOverview = ratsInOverview }

    else
        { readings = before.readings + 1, ratsInOverview = ratsInOverview }


describeCombatStalemate : CombatStalemate -> String
describeCombatStalemate stalemate =
    "stalemate "
        ++ String.fromInt stalemate.readings
        ++ " readings, "
        ++ String.fromInt combatStalemateApproachReadings
        ++ " to close in and "
        ++ String.fromInt combatStalemateLeaveReadings
        ++ " to leave"


decideActionInAnomaly :
    { arrivalInAnomalyAgeSeconds : Int }
    -> BotDecisionContext
    -> SeeUndockingComplete
    -> DecisionPathNode
    -> DecisionPathNode
decideActionInAnomaly { arrivalInAnomalyAgeSeconds } context seeUndockingComplete continueIfCombatComplete =
    let
        overviewEntriesToAttack =
            overviewEntriesToAttackFromReadingFromGameClient (namesOfRecentAttackers context.memory.incomingDamage) context.readingFromGameClient
                -- `combatPriorityTier`'s three tiers, ahead of the distance
                -- order the helper returns rows in. saxrat had no scrambler
                -- priority at all before #231, in the hull that was lost twice.
                -- Stable sort, so the nearest row in each tier leads and the
                -- rest keep their existing order.
                --
                -- Sorted here rather than inside
                -- `overviewEntriesToAttackFromReadingFromGameClient`, which is
                -- where `shouldAttackOverviewEntry` applies every guard this
                -- must not disturb. A tier only moves a row that rule already
                -- admitted -- it adds none -- so `overviewEntryDistanceIsOnGrid`
                -- still holds by construction, and the `overviewEntryIsDisplayed`
                -- filter below still runs before anything is clicked.
                |> List.sortBy combatPriorityTier

        overviewEntriesToAttackFirst =
            overviewEntriesToAttack
                |> List.filter shouldAttackOverviewEntryFirst

        -- Locking clicks the row, so only rows actually rendered can be used --
        -- a hidden one's position belongs to whatever row was recycled into its
        -- place, and clicking it locks the wrong object (see
        -- `overviewEntryIsDisplayed`). The filter comes before taking the
        -- nearest few, so a scrolled overview yields the nearest few rats it
        -- can actually click rather than an empty list.
        -- The `4` this used to take was the shipped ceiling written out a
        -- second time, so a client stating six left the two extra slots
        -- unreachable however far `Enough locked targets.` was raised. It is
        -- the learned ceiling now, plus the one row #150 probes with while the
        -- client has not stated its maximum. The `2` above is the
        -- attack-first rule's own window and is not a capacity at all, so it
        -- stays where it is.
        overviewEntriesToLock =
            if (List.length <| overviewEntriesToAttackFirst) > 0 then
                overviewEntriesToAttackFirst
                    |> List.filter overviewEntryIsDisplayed
                    |> List.take 2
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

            else
                overviewEntriesToAttack
                    |> List.filter overviewEntryIsDisplayed
                    |> List.take (maxTargetsRowsToTake (maxTargetsStateFrom context))
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

        -- The candidates the ship can lock from where it is. Only these can be
        -- probed with: `lockTargetFromOverviewEntry` approaches a row it cannot
        -- reach, and moving the ship is not a price a measurement gets to
        -- charge. A real target is still approached, exactly as before.
        overviewEntriesToLockInRange : List OverviewWindowEntry
        overviewEntriesToLockInRange =
            overviewEntriesToLock |> List.filter (overviewEntryIsWithinLockRange context)

        maxTargetsProbeNow : MaxTargetsProbe
        maxTargetsProbeNow =
            maxTargetsProbe
                { state = maxTargetsStateFrom context
                , targetsHeld = context.readingFromGameClient.targets |> List.length
                , rowsToSpare = overviewEntriesToLockInRange |> List.length
                }

        -- The row a lock is asked of now, which is the nearest candidate as
        -- ever except where the probe is due. `MaxTargetsProbeNothingToSpare`
        -- answers `Nothing` rather than falling back to the nearest, since the
        -- bar is full at the believed ceiling and the only row left is one the
        -- ship would have to fly at first.
        nextOverviewEntryToLockOrProbe : Maybe OverviewWindowEntry
        nextOverviewEntryToLockOrProbe =
            case maxTargetsProbeNow of
                MaxTargetsProbeOneMore _ ->
                    overviewEntriesToLockInRange |> List.head

                MaxTargetsProbeNothingToSpare _ ->
                    Nothing

                _ ->
                    overviewEntriesToLock |> List.head

        -- The rows one step asks the client to lock, when it asks for more than
        -- one. Taken as the in-range **prefix** of the candidate list rather
        -- than by filtering it, because `overviewEntriesToAttack` above sorts a
        -- warp-disrupting entry to the front ahead of the distance order -- see
        -- `lockBatchRowsInReach`, which is where that argument lives.
        overviewEntriesToLockInOneStep : List OverviewWindowEntry
        overviewEntriesToLockInOneStep =
            overviewEntriesToLock
                |> List.take
                    (lockBatchSize
                        (lockBatchSituationFrom context
                            { rowsLockableNow =
                                overviewEntriesToLock
                                    |> List.map (overviewEntryIsWithinLockRange context)
                                    |> lockBatchRowsInReach
                            , probe = maxTargetsProbeNow
                            }
                        )
                    )

        -- Something to attack, but not one candidate row rendered: the overview
        -- has been scrolled away from them (the scroll to reach a distant wreck
        -- does exactly that), and nothing can be locked until it comes back.
        revealEntryToLock =
            if overviewEntriesToAttack |> List.isEmpty then
                Nothing

            else
                scrollOverviewToReveal context (shouldAttackOverviewEntry (namesOfRecentAttackers context.memory.incomingDamage))

        -- #303: run 50 held a wreck locked and active for 39 unbroken ticks
        -- (154s) with rats on the same grid, because the bar-text match found
        -- nothing to unlock while `activeTargetOverviewEntryIsStray` fired on
        -- every one of those readings -- the branch that reads it only held
        -- fire, it never freed the slot. `targetsToUnlockIncludingActiveIfStray`
        -- is the fix; see its own doc comment for why this reads that shared
        -- definition rather than `targetsToUnlockFromReadingFromGameClient`
        -- directly.
        targetsToUnlock =
            targetsToUnlockIncludingActiveIfStray context.readingFromGameClient

        ensureShipIsOrbitingDecision =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head
                |> Maybe.andThen (\overviewEntryToAttack -> ensureShipIsOrbiting seeUndockingComplete.shipUI overviewEntryToAttack)

        ensureShipIsKeepingRangeDecision =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head
                |> Maybe.andThen (\overviewEntryToAttack -> ensureShipIsKeepingRange seeUndockingComplete.shipUI overviewEntryToAttack)

        ensureShipIsApproachingDecision =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head
                |> Maybe.andThen (\overviewEntryToAttack -> ensureShipIsApproaching seeUndockingComplete.shipUI overviewEntryToAttack)

        ensureShipIsAlignedDecision =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head
                |> Maybe.andThen (\overviewEntryToAttack -> alignToStructure seeUndockingComplete.shipUI context)

        waitTimeRemainingSeconds =
            context.eventContext.botSettings.anomalyWaitTimeSeconds - arrivalInAnomalyAgeSeconds

        -- Wrecks still worth opening: `notAlreadyEmptied` is what keeps this
        -- list shrinking, so the bot works through the wrecks on grid instead
        -- of reopening the nearest one until its time budget runs out.
        -- `overviewEntryIsDisplayed` excludes rows scrolled out of view, whose
        -- reported position belongs to whatever row was recycled into their
        -- place -- see `scrollOverviewToReveal` for how those are reached.
        notableWreckEntries =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter isNotableWreck
                |> List.filter (notAlreadyEmptied context)
                |> List.filter overviewEntryIsDisplayed
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        -- Extra time budget (beyond anomalyWaitTimeSeconds) to spend looting
        -- commander/overseer wrecks before giving up and leaving anyway. Now
        -- that emptied wrecks drop out of notableWreckEntries this is only a
        -- backstop, for the case where the looted-icon swap and the id memory
        -- both miss.
        lootWreckTimeRemainingSeconds =
            (context.eventContext.botSettings.anomalyWaitTimeSeconds + 120) - arrivalInAnomalyAgeSeconds

        -- What every give-up in this function means by leaving: bring the
        -- drones in, then hand the reading to whatever the caller does about a
        -- finished grid. All three call sites pass something that acts -- pick
        -- another anomaly, follow a site's own progression, or jump -- so this
        -- can neither decline nor come back here.
        leaveThisGrid =
            returnDronesToBay context
                (describeBranch "No drones to return." continueIfCombatComplete)

        -- The row the guns are already pointed at, where the ship could
        -- actually reach it. Inside `approachRangeLimitMeters` rather than
        -- around it: past 150 km the client discards the gesture, and run 41
        -- double-clicked a row 2,266 km away 13,541 times over three hours with
        -- the ship never moving. A row this cannot answer for is not a range
        -- the bot can close, so the stalemate escalates instead of asking
        -- anyway.
        rowToCloseTheRangeOn : Maybe OverviewWindowEntry
        rowToCloseTheRangeOn =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.filter overviewEntryIsDisplayed
                |> List.filter
                    (\entry ->
                        entry.objectDistanceInMeters
                            |> Result.map (\distanceInMeters -> distanceInMeters <= approachRangeLimitMeters)
                            |> Result.withDefault False
                    )
                |> List.head

        -- The branch that used to answer "wait" to its own question. See
        -- `CombatStalemate` for what the count means and
        -- `combatStalemateApproachReadings` for where the two bounds come from.
        breakTheCombatStalemate =
            case combatStalemateVerdict context.memory.combatStalemate.readings of
                FightIsStillGettingSomewhere ->
                    waitForProgressInGame

                CloseTheRangeOnTheTarget ->
                    case rowToCloseTheRangeOn of
                        Just entry ->
                            unlessAlreadyClosingIn context
                                (describeCombatStalemate context.memory.combatStalemate
                                    ++ ". Close the range on the target: at the ammo swap's crossover it cannot decide which charge the fight wants, and the guns hold the wrong one."
                                )
                                (doubleClickUiElement entry.uiNode)

                        Nothing ->
                            describeBranch
                                (describeCombatStalemate context.memory.combatStalemate
                                    ++ ". Nothing on the overview is both the active target and near enough to approach, so there is no range to close -- leave instead."
                                )
                                leaveThisGrid

                LeaveThisGrid ->
                    describeBranch
                        (describeCombatStalemate context.memory.combatStalemate
                            ++ ". Closing the range did not help either -- leave this grid."
                        )
                        leaveThisGrid

        decisionAfterLootingNotableWrecks =
            if waitTimeRemainingSeconds <= 0 then
                leaveThisGrid

            else
                describeBranch
                    ("Wait before considering the anomaly finished: " ++ String.fromInt waitTimeRemainingSeconds ++ " seconds")
                    (tetherAtStructure context)

        -- The wreck path taken when no loot window is in the reading -- and,
        -- since the loot window's own escalation is bounded, the branch that
        -- one stands aside into once its bound expires. It always acts: it
        -- opens the next notable wreck, scrolls one into view, or leaves the
        -- grid. Nothing here waits.
        lootAnotherWreckOrLeaveTheGrid =
            case notableWreckEntries of
                wreckToLoot :: _ ->
                    if lootWreckTimeRemainingSeconds <= 0 then
                        describeBranch "Giving up on looting commander/overseer wreck(s) -- out of time."
                            decisionAfterLootingNotableWrecks

                    else
                        -- The same command whether the wreck is
                        -- alongside or across the pocket: the client
                        -- flies the ship there and opens it on
                        -- arrival. Routed through
                        -- `closeInOnOverviewEntry` for its approach
                        -- guard, which this branch never had -- it
                        -- re-ran the whole cascade every tick while
                        -- the ship was still on its way, restarting
                        -- the approach each time.
                        -- Double click rather than the
                        -- right-click cascade: the client reads it
                        -- as Open Cargo directly, and from outside
                        -- looting range it closes the distance
                        -- first, so one step replaces both the
                        -- cascade and the separate approach.
                        openCargoOnOverviewEntry context
                            "Open commander/overseer wreck's cargo before leaving."
                            wreckToLoot

                [] ->
                    -- Nothing to loot on screen, but a wreck worth
                    -- opening can be scrolled out of the overview.
                    -- Under the same time budget as looting itself,
                    -- so a scroll that never lands cannot hold the
                    -- bot in the anomaly forever.
                    case
                        if lootWreckTimeRemainingSeconds <= 0 then
                            Nothing

                        else
                            scrollOverviewToReveal context
                                (\entry -> isNotableWreck entry && notAlreadyEmptied context entry)
                    of
                        Just scrollToWreck ->
                            scrollToWreck

                        Nothing ->
                            decisionAfterLootingNotableWrecks

        decisionIfNoEnemyToAttack =
            if overviewEntriesToAttack |> List.isEmpty then
                case context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
                    Just openInventoryWindow ->
                        -- A wreck's loot window is open (from opening a
                        -- commander/overseer wreck's cargo below) -- handle
                        -- it to completion (loot, then close) before
                        -- touching anything else, regardless of what's left
                        -- in notableWreckEntries. "Loot All" has no
                        -- dedicated field on InventoryWindow, so this is
                        -- a plain text search within the window.
                        --
                        -- Feedback: this window sometimes fails to close
                        -- after clicking its own "Loot All"/close button
                        -- (button click not registering, or the button
                        -- not found) and just sits open forever. See
                        -- `lootWindowCloseRung` for the ladder over that,
                        -- for why the escalation is Alt+C rather than the
                        -- Ctrl+W this used to press at an unfocused window,
                        -- and for what the bound falls through to.
                        let
                            closeControl =
                                openInventoryWindow.uiNode
                                    |> EveOnline.ParseUserInterface.parseWindowControlsFromWindow
                                    |> Maybe.andThen .closeButton

                            forceItShutWithTheInventoryToggle =
                                describeBranch
                                    "Loot window did not close on its own -- force it shut (Alt+C, the inventory toggle, which needs no focus)."
                                    (decideActionForCurrentStep pressInventoryToggleEffects)
                        in
                        case
                            lootWindowCloseRung
                                { readingsOpen = context.memory.lootWindowOpenTicks
                                , closeControlIsInTheReading = closeControl /= Nothing
                                , togglePressedRecently =
                                    context.previousStepsEffects
                                        |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
                                        |> List.any doEffectsPressInventoryToggle
                                }
                        of
                            LeaveTheLootWindowAlone ->
                                describeBranch
                                    ("Loot window has been open for "
                                        ++ String.fromInt context.memory.lootWindowOpenTicks
                                        ++ " readings and neither its own controls nor Alt+C shut it, which is past "
                                        ++ String.fromInt lootWindowForceCloseGiveUpReadings
                                        ++ " -- leave it open and get on with the rest of the grid."
                                    )
                                    lootAnotherWreckOrLeaveTheGrid

                            PressTheInventoryToggle ->
                                forceItShutWithTheInventoryToggle

                            ClickTheWindowsCloseControl ->
                                -- `closeControl` is what the rung was told
                                -- about, so this cannot be reached without one.
                                -- The fall-back is the keystroke rather than a
                                -- wait, for the reason the rung's own comment
                                -- gives.
                                closeControl
                                    |> Maybe.map
                                        (\closeButton ->
                                            describeBranch "Loot window did not close on its own -- click its own Close control."
                                                (clickUiElement closeButton)
                                        )
                                    |> Maybe.withDefault forceItShutWithTheInventoryToggle

                            UseTheWindowsOwnControls ->
                                case openInventoryWindow.uiNode |> findUiElementWithText "Loot All" of
                                    Just lootAllButton ->
                                        describeBranch "Click 'Loot All'." (clickUiElement lootAllButton)

                                    Nothing ->
                                        -- Unreachable while
                                        -- `wreckLootWindowsFromReadingFromGameClient`
                                        -- selects a window by this very text,
                                        -- and it is where that filter widening
                                        -- should land: the close controls above,
                                        -- never `askForHelpToGetUnstuck`, which
                                        -- is what used to sit here and which a
                                        -- bounded ladder must not reach for.
                                        describeBranch "Nothing left to loot in this window."
                                            (closeControl
                                                |> Maybe.map
                                                    (\closeButton ->
                                                        describeBranch "Close the wreck's cargo window."
                                                            (clickUiElement closeButton)
                                                    )
                                                |> Maybe.withDefault forceItShutWithTheInventoryToggle
                                            )

                    Nothing ->
                        lootAnotherWreckOrLeaveTheGrid

            else
                describeBranch "Locking..."
                    (if activeTargetOverviewEntryIsStray context.readingFromGameClient then
                        describeBranch "The active target looks like a container/wreck, not a rat -- hold fire."
                            waitForProgressInGame

                     else
                        case seeUndockingComplete |> shipUIModulesToActivateOnTarget |> List.indexedMap Tuple.pair |> List.filter (Tuple.second >> .isActive >> Maybe.withDefault False >> not) |> List.head of
                            Nothing ->
                                describeBranch "Scoot!"
                                    waitForProgressInGame

                            Just ( inactiveModuleIndex, inactiveModule ) ->
                                describeBranch "Shoot!"
                                    (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
                    )

        -- The ammo swap sits in front of the fight rather than beside it: it
        -- declines on most readings and hands the fight straight on, and the
        -- readings where it does act are ones where firing this instant matters
        -- less than firing the right charge for the next minute.
        --
        -- Below the movement branches rather than above them, which is where
        -- this bot differs from the mission runner: orbiting or keeping range is
        -- a command about where the ship is, the swap is a command about the
        -- guns, and the movement one is already the outer decision here.
        decisionToFight =
            ensureAmmoSuitsTargetRange context decisionToKillRats

        decisionToKillRats =
            case targetsToUnlock |> List.head of
                Just targetToUnlock ->
                    -- Feedback: the right-click context-menu cascade used
                    -- here previously (with a 200px discard-distance
                    -- tolerance) never worked reliably -- confirmed live,
                    -- repeatedly: "Open context menu on locked target" kept
                    -- firing fresh every tick with no matching "Click on
                    -- menu entry" for 'unlock' ever appearing in the log,
                    -- meaning the right-click essentially never landed a
                    -- usable menu. Replaced with EVE's own direct
                    -- Ctrl+Shift+Click-to-unlock shortcut on the target
                    -- bar entry instead -- one click, no menu to land, no
                    -- cascade to get stuck discarding and reopening. Still
                    -- gated on the icon's position having settled for at
                    -- least a tick (tracked in BotMemory, since this
                    -- target isn't necessarily "the same locked target"
                    -- across ticks in any other identifiable way), since a
                    -- freshly-appeared/moved icon may not be click-ready.
                    if context.memory.targetToUnlockUnchangedTicks < 1 then
                        describeBranch
                            "I see a target to unlock, but its position just appeared or changed since the last reading -- wait for it to settle before clicking it."
                            waitForProgressInGame

                    else
                        describeBranch "I see a target to unlock -- Ctrl+Shift+Click it to unlock directly."
                            (ctrlShiftClickUiElement (targetToUnlock.barAndImageCont |> Maybe.withDefault targetToUnlock.uiNode))

                Nothing ->
                    case context.readingFromGameClient.targets |> List.head of
                        Nothing ->
                            describeBranch "I see no locked target."
                                (case overviewEntriesToLock of
                                    [] ->
                                        case revealEntryToLock of
                                            Just scrollToEntry ->
                                                scrollToEntry

                                            Nothing ->
                                                describeBranch "I see no overview entry to lock."
                                                    decisionIfNoEnemyToAttack

                                    nextOverviewEntryToLock :: _ ->
                                        describeBranch "I see an overview entry to lock."
                                            (lockTargetFromOverviewEntry context nextOverviewEntryToLock)
                                )

                        Just _ ->
                            describeBranch "I see a locked target."
                                (if activeTargetOverviewEntryIsStray context.readingFromGameClient then
                                    -- Second opinion, independent of the
                                    -- Target<->overview name matching that
                                    -- targetsToUnlockFromReadingFromGameClient
                                    -- relies on: if it disagrees and says
                                    -- the active target is a container/
                                    -- wreck, don't fire weapons or send
                                    -- drones at it (both target whatever is
                                    -- currently active) -- hold fire and let
                                    -- the primary classification catch up
                                    -- on a later tick instead.
                                    describeBranch "The active target looks like a container/wreck, not a rat -- hold fire."
                                        waitForProgressInGame

                                 else if activateOneOfTheLockedTargets context /= Nothing then
                                    activateOneOfTheLockedTargets context
                                        |> Maybe.withDefault waitForProgressInGame

                                 else
                                    case seeUndockingComplete |> shipUIModulesToActivateOnTarget |> List.indexedMap Tuple.pair |> List.filter (Tuple.second >> .isActive >> Maybe.withDefault False >> not) |> List.head of
                                        Nothing ->
                                            describeBranch "All guns cycling"
                                                (launchAndEngageDrones context
                                                    |> Maybe.withDefault
                                                        (describeBranch "No idling drones."
                                                            (if maxTargetsRowsToTake (maxTargetsStateFrom context) <= (context.readingFromGameClient.targets |> List.length) then
                                                                -- The rows the lock site takes rather than the
                                                                -- ceiling, so a session that has not heard the
                                                                -- client's maximum never says it has enough: it
                                                                -- has one more to ask for, which is the whole
                                                                -- of #150. Once the client has stated the
                                                                -- number this is the ceiling again.
                                                                --
                                                                -- TODO branch if bouncing or brawling
                                                                -- describeBranch "Enough locked targets." (enterAnomaly { ifNoAcceptableAnomalyAvailable = tetherAtStructure context } context)
                                                                describeBranch "Enough locked targets." waitForProgressInGame

                                                             else
                                                                case nextOverviewEntryToLockOrProbe of
                                                                    Nothing ->
                                                                        revealEntryToLock
                                                                            |> Maybe.withDefault
                                                                                (describeBranch
                                                                                    (describeMaxTargetsNothingToLock maxTargetsProbeNow
                                                                                        "All locked up; bounce?"
                                                                                    )
                                                                                    breakTheCombatStalemate
                                                                                )

                                                                    Just nextOverviewEntryToLock ->
                                                                        if lockBatchIsSettling context.memory.lockBatch then
                                                                            describeBranch
                                                                                (describeLockBatchSettling context.memory.lockBatch)
                                                                                waitForProgressInGame

                                                                        else if 1 < (overviewEntriesToLockInOneStep |> List.length) then
                                                                            describeBranch
                                                                                (describeLockBatchAsked overviewEntriesToLockInOneStep)
                                                                                (lockTargetsFromOverviewEntries overviewEntriesToLockInOneStep)

                                                                        else
                                                                            describeBranch (describeMaxTargetsProbe maxTargetsProbeNow)
                                                                                (lockTargetFromOverviewEntry context nextOverviewEntryToLock)
                                                            )
                                                        )
                                                )

                                        --   (overviewEntriesToAttack
                                        --     |> List.filter (overviewEntryIsTargetedOrTargeting)
                                        --     |> List.head
                                        --     |> Maybe.andThen (\overviewEntryToAttack -> ensureShipIsOrbiting seeUndockingComplete.shipUI overviewEntryToAttack)
                                        --         |> Maybe.withDefault waitForProgressInGame)
                                        Just ( inactiveModuleIndex, inactiveModule ) ->
                                            -- A turret stuck unable to activate (interference, a
                                            -- target it cannot hurt) must not starve drones of the
                                            -- 'F' that keeps them on the active target -- see the
                                            -- 'No idling drones.' branch above, which only runs once
                                            -- every top-row module already reads active. Asking here
                                            -- too means drones get re-engaged every reading a fight
                                            -- is on, whether or not the guns are cooperating.
                                            launchAndEngageDrones context
                                                |> Maybe.withDefault
                                                    (clickTargetBeforeShooting context overviewEntriesToAttack
                                                        |> Maybe.withDefault
                                                            (describeBranch "Cycle combat mod"
                                                                (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
                                                            )
                                                    )
                                )
    in
    case combatManoeuvreFromSettings context.eventContext.botSettings of
        ManoeuvreOrbit ->
            ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToFight

        ManoeuvreKeepAtRange ->
            ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToFight

        ManoeuvreApproach ->
            ensureShipIsApproachingDecision |> Maybe.withDefault decisionToFight

        ManoeuvreAlign ->
            ensureShipIsAlignedDecision |> Maybe.withDefault decisionToFight


enterAnomaly : { ifNoAcceptableAnomalyAvailable : DecisionPathNode } -> BotDecisionContext -> DecisionPathNode
enterAnomaly { ifNoAcceptableAnomalyAvailable } context =
    case context.readingFromGameClient.probeScannerWindow of
        Nothing ->
            describeBranch "I do not see the probe scanner window." askForHelpToGetUnstuck

        Just probeScannerWindow ->
            let
                scanResultsWithReasonToIgnore =
                    probeScannerWindow.scanResults
                        |> List.map
                            (\scanResult ->
                                ( scanResult
                                , findReasonToIgnoreProbeScanResult (anomalyChoiceFromDecisionContext context) scanResult
                                )
                            )

                warp =
                    "Within " ++ (context.eventContext.botSettings.warpAt |> String.fromInt) ++ " km"
            in
            case
                scanResultsWithReasonToIgnore
                    |> List.filter (Tuple.second >> (==) Nothing)
                    |> List.map Tuple.first
                    -- |> listElementAtWrappedIndex (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                    |> listElementAtWrappedIndex 0
            of
                Nothing ->
                    describeBranch
                        ("I see "
                            ++ (probeScannerWindow.scanResults |> List.length |> String.fromInt)
                            ++ " scan results, and no matching anomaly. Wait for a matching anomaly to appear."
                        )
                        ifNoAcceptableAnomalyAvailable

                Just anomalyScanResult ->
                    ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                        (describeBranch "Warp to anomaly."
                            (useContextMenuCascade
                                ( "Scan result", anomalyScanResult.uiNode )
                                (useMenuEntryWithTextContaining "to within"
                                    (useMenuEntryWithTextContaining warp menuCascadeCompleted)
                                 -- (useMenuEntryWithTextContaining "Within 100 km" menuCascadeCompleted)
                                 -- (useMenuEntryWithTextContaining "Within 30 km" menuCascadeCompleted)
                                 -- TODO THIS PROBABLY OUGHTa be configurable
                                 -- (useMenuEntryWithTextContaining "Within 70 km" menuCascadeCompleted)
                                )
                                context
                            )
                        )


{-| Which of the four things the ship does with its position while it fights.

The three settings are mutually exclusive, and this is where that is decided
rather than in three separate `if`s at the call site. It is a rule over the
settings record so a case can execute it -- all eight combinations of the three
answers, in `elm repl` -- where a chain buried inside `decideActionInAnomaly`
is reachable only through a whole `BotDecisionContext` and would have to be read
instead. #106 records what reading rather than running a rule costs.

The order is the order the chain already had, with approach appended: a settings
string that already sets `orbit-in-combat` or `keep-at-range` picks exactly what
it picked before, whatever else is now set beside it. `ManoeuvreAlign` is what
no setting at all means, which is also what saxrat has always done.

-}
type CombatManoeuvre
    = ManoeuvreOrbit
    | ManoeuvreKeepAtRange
    | ManoeuvreApproach
    | ManoeuvreAlign


combatManoeuvreFromSettings : BotSettings -> CombatManoeuvre
combatManoeuvreFromSettings botSettings =
    if botSettings.orbitInCombat == AppSettings.Yes then
        ManoeuvreOrbit

    else if botSettings.keepAtRange == AppSettings.Yes then
        ManoeuvreKeepAtRange

    else if botSettings.approachInCombat == AppSettings.Yes then
        ManoeuvreApproach

    else
        ManoeuvreAlign


{-| Close on the target and stay on it, for a fit that has to be on top of a rat.

Webs, scramblers and short-range guns all want the ship next to the thing it is
shooting, and neither of the two manoeuvres beside this does that: orbit holds
transversal at a distance and keep-at-range holds a distance on purpose.

**A double click on the overview row, and no keystroke.** That is the gesture
this bot already uses to approach, and `doubleClickUiElement`'s own doc comment
carries the argument: EVE answers a double click on an object with that object's
default action, which for a hostile ship with no cargo to open is an approach,
and `cg_input` posts a key event without stamping flags on it, so a posted `Q`
carries whatever modifier state the session happens to hold -- with the Fn bit
set that is macOS Quick Note, and one recorded run took the old approach branch
1,571 times while Notes came to the front 241 times with nobody at the machine.
PR #241 stopped the mis-stamping; PR #243 stopped the keystroke existing, and
nothing here brings one back. The two siblings still wrap a click in `vkey_E`
and `vkey_W`, which is recorded rather than fixed and is not this change.

**The dispatched click is not the confirmation.** `ManeuverApproach` is, exactly
as `ManeuverOrbit` confirms the orbit arm next door: this answers `Just` -- keeps
commanding -- on every reading the client has not reported the manoeuvre on, and
`Nothing` on the readings it has. A click that went out and did nothing therefore
costs one reading and is re-issued, where reading the dispatch back would be this
repo's signature failure: a branch that prints an action and believes it worked.

**It approaches for the whole engagement rather than stopping at a range, and
the cost of that is stated rather than hidden.** A ship sitting on top of a rat
has zero transversal against anything that tracks, which is a question about the
fit rather than about this code -- a brawler wants exactly that and a kiter must
not set this setting. The alternative -- stop once inside some distance -- was
declined because it needs a distance, and PILOT.md records what that costs: `no
bot setting carries an engagement distance`, so `orbit-in-combat` and
`keep-at-range` fall back on a client default nobody can read back, which shipped
at 7,500 m and was suicidal on a hull whose guns reach tens of kilometres.
Approach closes to zero and so has no distance to get wrong. A range setting is
deliberately not built here.

`ManeuverApproach` stays set while the ship approaches _something_, which need
not be this target -- the bot issues approaches elsewhere, at a wreck or a gate.
The two siblings have the identical exposure on `ManeuverOrbit` and
`ManeuverRange`, and this mirrors them rather than inventing a bound of its own;
`approachIndicationTrustedForTicks` is what a bounded belief looks like where one
is wanted, and `unlessAlreadyClosingIn` is where it is used.

-}
ensureShipIsApproaching : ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsApproaching shipUI overviewEntryToApproach =
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverApproach then
        Nothing

    else
        Just
            (describeBranch
                ("Approach the target '"
                    ++ (overviewEntryToApproach.objectName |> Maybe.withDefault "")
                    ++ "' -- double click on the overview entry."
                )
                (doubleClickUiElement overviewEntryToApproach.uiNode)
            )


ensureShipIsKeepingRange : ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsKeepingRange shipUI overviewEntryToKAR =
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverRange then
        Nothing

    else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverAlign then
        Nothing

    else if not (overviewEntryToKAR |> overviewEntryIsTargetedOrTargeting) then
        Nothing

    else
        Just
            (describeBranch "Press the 'E' key and click on the overview entry."
                (decideActionForCurrentStep
                    ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_E ]
                     , overviewEntryToKAR.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
                     , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_E ]

                     --  , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_C ]
                     --  , overviewEntryToKAR.uiNode |> mouseClickOnUIElement MouseButtonLeft
                     --  , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_C ]
                     --  , overviewEntryToKAR.uiNode |> mouseClickOnUIElement MouseButtonLeft
                     ]
                        |> List.concat
                    )
                )
            )


ensureShipIsOrbiting : ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsOrbiting shipUI overviewEntryToOrbit =
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverOrbit then
        Nothing

    else
        Just
            (describeBranch "Press the 'W' key and click on the overview entry."
                (decideActionForCurrentStep
                    ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_W ]
                     , overviewEntryToOrbit.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
                     , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_W ]

                     -- , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_C ]
                     -- , overviewEntryToOrbit.uiNode |> mouseClickOnUIElement MouseButtonLeft
                     -- , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_C ]
                     -- , overviewEntryToOrbit.uiNode |> mouseClickOnUIElement MouseButtonLeft
                     ]
                        |> List.concat
                    )
                )
            )


{-| The clause a drone-launch refusal is recognised by, and the one the count is
sliced out after.

One constant for both, so an extraction can never succeed on a sentence the
matcher would have rejected -- `maxTargetsStatedMarker`'s arrangement, for its
reason.

-}
droneLaunchRefusedMarker : String
droneLaunchRefusedMarker =
    "already controlling"


{-| The second clause, and it is what keeps this rule off the targeting refusal
#110 already consumes.

`You are already managing 6 targets, as many as you have skill to.` is the same
sentence to within two words, and `maxTargetsStatedInGameLog` reads it off the
game log to set the lock-slot ceiling. Two rules reading each other's sentence
would be two wrong ceilings -- a lock ceiling capped at the number of drones, or
a drone ceiling capped at the number of lock slots -- so the exclusion is
deliberately over-determined and holds in both directions: `controlling` is not
`managing`, `much` is not `many`, and the count is sliced after
`droneLaunchRefusedMarker`, a clause the targeting sentence does not contain at
all. No single loosening admits the other sentence.

Checked against every wording the corpus holds: 108 distinct quick messages
across mission run 37 and saxrat runs 5 and 6. Two of them match both markers and
both are this refusal, differing only in the drone's name.

-}
droneLaunchSkillMarker : String
droneLaunchSkillMarker =
    "as much as you have skill to"


{-| How many drones the client says this ship is already flying, off the quick
message that is on the screen **now**.

`<center>You cannot launch Acolyte I because you are already controlling 5
drones, as much as you have skill to.` -- 101 live sightings in mission run 37,
224 in saxrat run 5 and 1,316 in saxrat run 6, which is the single most common
thing the client said to either bot in run 6. The drone's name varies with what
is in the bay (`Acolyte I` and `Hammerhead I` both occur) and nothing here reads
it.

**A carried-forward sighting teaches nothing, and is refused here rather than at
the call site.** `quickMessageAfterReading` keeps the last message with an age
until another replaces it, so the same popup is still in memory hundreds of
readings after the launch it refused -- carried-forward totals across these runs
are three orders of magnitude above the live ones and rank the wordings
differently. A ceiling learned from an age-200 sighting would be learned from a
ship that has since docked, restocked and undocked. So `readingsSince` must be
`0`, and the one call site that could pass an aged sighting cannot make this rule
believe it.

The count is sliced out after `droneLaunchRefusedMarker` rather than taken as the
first integer in the sentence, so it is the number that clause is about: the text
in front of the clause is the drone's own name, which is client text this rule
does not control. No recorded wording puts a digit there, and the slice is what
keeps one that did from being read as a drone count. A sentence that matches both
markers and yields no number is **no evidence** and never a default -- see
`droneLaunchCeiling` for why that direction is the whole safety of this.

-}
droneLaunchRefusalStatedInQuickMessage : Maybe QuickMessageSighting -> Maybe Int
droneLaunchRefusalStatedInQuickMessage sighting =
    sighting
        |> Maybe.andThen
            (\seen ->
                if seen.readingsSince /= 0 then
                    Nothing

                else if
                    stringContainsIgnoringCase droneLaunchRefusedMarker seen.text
                        && stringContainsIgnoringCase droneLaunchSkillMarker seen.text
                then
                    droneLaunchCountInStatement seen.text

                else
                    Nothing
            )


{-| The count the client named, out of a sentence already matched.

Lowercased before slicing only so that the marker matches the way the matcher's
own `stringContainsIgnoringCase` does; nothing lowercased here is stored or
printed. A capitalisation the slice misses therefore yields `Nothing`, which is
the safe direction rather than a guess -- and so does the client wrapping the
number in markup the way it wraps `<b>86 km</b>` elsewhere in this corpus.

-}
droneLaunchCountInStatement : String -> Maybe Int
droneLaunchCountInStatement text =
    case text |> String.toLower |> String.split droneLaunchRefusedMarker of
        _ :: afterMarker :: _ ->
            afterMarker |> String.words |> List.head |> Maybe.andThen String.toInt

        _ ->
            Nothing


{-| The two numbers that bound a launch, kept as a record so a case can execute
the rule that combines them.

`fromWindow` is what the drones-in-space group's own title says; `statedByClient`
is what the client said when it refused a launch. Neither is a setting -- both
are read off the client -- which is why this pair has no `fromSetting` the way
`MaxTargetsState` does.

-}
type alias DroneLaunchState =
    { fromWindow : Int
    , statedByClient : Maybe Int
    }


{-| The pair as this reading has it, assembled in one place.

One reader of the drones window's maximum per side of a reading, so the launch
decision and the status clause cannot come to hold two opinions about the
ceiling -- `maxTargetsStateFrom`'s reason.

-}
droneLaunchStateFrom : BotDecisionContext -> DroneLaunchState
droneLaunchStateFrom context =
    { fromWindow = dronesInSpaceLimitFromWindow context.readingFromGameClient
    , statedByClient = context.memory.droneLaunchRefusedAbove
    }


{-| The limit assumed where the drones-in-space group's title carries no maximum.

The value both apps have always used. It is kept as a constant rather than
inlined so that the launch site and the status clause cannot come to assume
different ones.

-}
droneLaunchLimitWithoutATitle : Int
droneLaunchLimitWithoutATitle =
    2


{-| How many drones the drones window says this ship may have out.

The window's own arithmetic and nothing else, so that "what the window says" and
"what the client says" stay two separate readings a status clause can print side
by side. A reading with no drones window answers the same default the launch site
always used, since a launch is not attempted without one anyway.

-}
dronesInSpaceLimitFromWindow : ReadingFromGameClient -> Int
dronesInSpaceLimitFromWindow readingFromGameClient =
    readingFromGameClient.dronesWindow
        |> Maybe.andThen .droneGroupInSpace
        |> Maybe.andThen (.header >> .quantityFromTitle)
        |> Maybe.andThen .maximum
        |> Maybe.withDefault droneLaunchLimitWithoutATitle


{-| How many drones the launch site will try to have in space.

**The drones window's maximum is not the drone-control skill cap, and the launch
site had been treating it as one.** saxrat's run 6 read `In bay: 3, in space: 5`
on 17,919 readings -- three drones sitting in the bay, a window whose title
admitted more, and a client that answered `You cannot launch Hammerhead I because
you are already controlling 5 drones, as much as you have skill to.` to every one
of the 826 launches the bot pressed. 1,316 of those refusals were on screen when
a reading was taken. Mission run 37 shows the same shape at 101, saxrat run 5 at

1.  The bot could not tell the launch was refused, so it pressed again on the
    next reading, for the whole session.

`min` rather than replacement, because unlike `maxTargetsCeiling` neither number
here is a guess: the window's maximum is a real bound this ship has (bandwidth
and bay), and the client's sentence is a real bound this character has (the
drone-control skill). The lower of two real bounds is the one that binds, and a
statement naming a number **above** what the window offers must not raise
anything.

**Absent evidence never moves the limit.** With `statedByClient` unknown this is
exactly the window's own number, so a session in which the client never refuses a
launch behaves precisely as every session did before this rule existed. That
direction is the whole safety of it: a ceiling raised on a guess spends readings
pressing a launch the client will never grant, which is the failure being fixed.

**And nothing latches across sessions**, which is what keeps this from freezing a
character whose drone skill is still training. `initBotMemory` starts at
`Nothing`, so every session launches up to the window's maximum, is refused at
most once, and stops -- one refusal per session against run 6's 1,316. Within a
session the latest statement wins, so a cap that moves while the bot is flying
moves this with it.

-}
droneLaunchCeiling : DroneLaunchState -> Int
droneLaunchCeiling state =
    case state.statedByClient of
        Just stated ->
            min stated state.fromWindow

        Nothing ->
            state.fromWindow


{-| What the rule knows after this reading.

Returned as one record rather than written field by field, so the whole of the
rule lives in one place -- `MaxTargetsLearning`'s reason.

-}
type alias DroneLaunchLearning =
    { statedByClient : Maybe Int
    , change : Maybe String
    }


{-| Move the learned cap on what the client has just refused.

The **latest** statement wins rather than the smallest, for `maxTargetsCeiling`'s
reason: it is the client's answer about this character now, and a skill
completing mid-session moves it up. Taking the smallest would make one refusal
permanent for the session and unable to follow that.

`change` is set on the reading the learned number moves and on no other, by
comparing what this reading stated against what was believed. That needs no
"already reported" flag: the same popup sits on screen for several readings in a
row -- 1,316 live sightings against 215 refusals in saxrat run 6's own game log --
and every reading after the first states the number already held, which moves
nothing and says nothing.

-}
updateDroneLaunchLearning :
    { onScreenNow : Maybe QuickMessageSighting
    , statedBefore : Maybe Int
    }
    -> DroneLaunchLearning
updateDroneLaunchLearning state =
    let
        statedOnThisReading : Maybe Int
        statedOnThisReading =
            droneLaunchRefusalStatedInQuickMessage state.onScreenNow
    in
    { statedByClient =
        case statedOnThisReading of
            Just stated ->
                Just stated

            Nothing ->
                state.statedBefore
    , change =
        case statedOnThisReading of
            Nothing ->
                Nothing

            Just stated ->
                if Just stated == state.statedBefore then
                    Nothing

                else
                    Just
                        ("Learned drone launch ceiling: the client refused a launch, saying this ship is already controlling "
                            ++ String.fromInt stated
                            ++ " drones, as much as this character has skill to -- no further launch is attempted above "
                            ++ String.fromInt stated
                            ++ (case state.statedBefore of
                                    Just before ->
                                        ", rather than the " ++ String.fromInt before ++ " learned earlier this session."

                                    Nothing ->
                                        ", whatever maximum the drones window's own title offers."
                               )
                        )
    }


{-| The launch ceiling and where each half of it came from, for the status line.

Continuous rather than once-per-change, unlike the decision-log line, and both
halves are named separately because they fail differently -- a run whose `client
stated` never leaves `-` is one whose popups are not reaching the rule, where a
window number that never drops below the ceiling is a ship whose skill is not the
binding constraint at all. `describeMaxTargets`' argument, applied to this pair.

-}
describeDroneLaunchCeiling : DroneLaunchState -> String
describeDroneLaunchCeiling state =
    "dronecap "
        ++ (droneLaunchCeiling state |> String.fromInt)
        ++ " (window "
        ++ (state.fromWindow |> String.fromInt)
        ++ " client "
        ++ (state.statedByClient |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ")."


launchAndEngageDrones : BotDecisionContext -> Maybe DecisionPathNode
launchAndEngageDrones context =
    context.readingFromGameClient.dronesWindow
        |> Maybe.andThen
            (\dronesWindow ->
                case ( dronesWindow.droneGroupInBay, dronesWindow.droneGroupInSpace ) of
                    ( Just droneGroupInBay, Just droneGroupInSpace ) ->
                        let
                            idlingDrones =
                                droneGroupInSpace
                                    |> EveOnline.ParseUserInterface.enumerateAllDronesFromDronesGroup
                                    |> List.filter
                                        (.uiNode
                                            >> .uiNode
                                            >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                                            >> List.any (stringContainsIgnoringCase "idle")
                                        )

                            dronesInBayQuantity =
                                droneGroupInBay.header.quantityFromTitle
                                    |> Maybe.map .current
                                    |> Maybe.withDefault 0

                            dronesInSpaceQuantityCurrent =
                                droneGroupInSpace.header.quantityFromTitle
                                    |> Maybe.map .current
                                    |> Maybe.withDefault 0

                            -- The window's own maximum is a real bound and
                            -- the drone-control skill is another, and until
                            -- #146 only the first was consulted. See
                            -- `droneLaunchCeiling`.
                            dronesInSpaceQuantityLimit =
                                droneLaunchCeiling (droneLaunchStateFrom context)
                        in
                        if 0 < (idlingDrones |> List.length) then
                            -- `F` engages the currently locked/active target directly,
                            -- the same hotkey the mission runner uses (see "In-game
                            -- hotkeys" in CLAUDE.md). The menu cascade this replaced
                            -- opened on 'Assist' -> 'Gal Bistot' when present, which
                            -- costs several readings of right-click/hover/click before
                            -- a drone fires a shot -- and Gal is frequently not even on
                            -- the grid, so those readings bought nothing. A locked
                            -- target already exists by the time this branch is reached
                            -- (the caller is inside "I see a locked target", below the
                            -- container/wreck stray check), so F always has something
                            -- to aim at here.
                            Just
                                (describeBranch "Engage target with drones (F)"
                                    (decideActionForCurrentStep
                                        [ EffectOnWindow.KeyDown EffectOnWindow.vkey_F
                                        , EffectOnWindow.KeyUp EffectOnWindow.vkey_F
                                        ]
                                    )
                                )

                        else if 0 < dronesInBayQuantity && dronesInSpaceQuantityCurrent < dronesInSpaceQuantityLimit then
                            Just
                                (describeBranch "Launch drones"
                                    (decideActionForCurrentStep
                                        ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT ]
                                         , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_F ]
                                         , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_F ]
                                         , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT ]
                                         ]
                                            |> List.concat
                                        )
                                    )
                                 -- (useContextMenuCascade
                                 --     ( "drones group", droneGroupInBay.header.uiNode )
                                 --     (useMenuEntryWithTextContaining "Launch drone" menuCascadeCompleted)
                                 --     context
                                 -- )
                                )

                        else
                            Nothing

                    _ ->
                        Nothing
            )


{-| Recall the drones, and give up rather than asking forever.

Warping with drones in space loses them, so this sits in front of every warp,
every tether and every dock. Shift+R is a bare keypress with nothing to aim at
and no acknowledgement anywhere in the reading, so the only evidence a recall
landed is the in-space count falling -- which means the asking has to be
bounded, and before this port it was not bounded at all. The keypress went out
on every reading for as long as the drones stayed in space, and because the
callers took the recall _instead of_ their own next step, a recall that never
landed meant the ship never docked either.

**It takes the caller's next step rather than returning a `Maybe`.** A give-up
that returns nothing at all is one an operator cannot see: the log then reads
exactly like a bot that never had drones out. Handing the continuation in lets
the branch that abandons the drones name itself, every reading it declines --
not once, which is the other half of issue #11. The equality test its give-up
was first written as fired only on the reading the counter was _exactly_ at the
threshold, and if the ship was mid-fight on that one reading nothing was ever
logged at all.

-}
returnDronesToBay : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
returnDronesToBay context ifNothingToRecall =
    context.readingFromGameClient.dronesWindow
        |> Maybe.andThen .droneGroupInSpace
        |> Maybe.andThen
            (\droneGroupInLocalSpace ->
                if
                    (droneGroupInLocalSpace.header.quantityFromTitle
                        |> Maybe.map .current
                        |> Maybe.withDefault 0
                    )
                        < 1
                then
                    Nothing

                else if droneRecallGiveUpTicks < context.memory.droneRecallUnansweredTicks then
                    -- Stop asking, and go on with whatever the caller wanted to
                    -- do. Giving up has to latch -- which it does, because the
                    -- counter holds past the threshold rather than resetting --
                    -- or the ship alternates forever between abandoning its
                    -- drones and recalling them.
                    Just
                        (describeBranch
                            ("Drones have not answered "
                                ++ String.fromInt context.memory.droneRecallUnansweredTicks
                                ++ " readings of recall and will not come back -- leave without them so the ship can move on."
                            )
                            ifNothingToRecall
                        )

                else if
                    (droneRecallFocusRecoveryTicks < context.memory.dronesInSpaceTicks)
                        && not (previousStepClickedMouse context)
                then
                    -- Shift+R does nothing at all when the client is not taking
                    -- keyboard input, and nothing in the reading says so: the
                    -- decision looks identical whether the key landed or was
                    -- swallowed. Clicking inside the client first is the
                    -- documented remedy, and the drone group header is a real
                    -- target inside the window we are already acting on that
                    -- does nothing but move focus.
                    --
                    -- Gated on not having just clicked, so this alternates
                    -- click, press, click, press rather than clicking forever.
                    Just
                        (describeBranch
                            "Drones are not coming back -- click the drones window to put keyboard focus back in the client, then press again."
                            (clickUiElement droneGroupInLocalSpace.header.uiNode)
                        )

                else
                    Just
                        (describeBranch "I see there are drones in space. Return those to bay."
                            (decideActionForCurrentStep
                                ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT ]
                                 , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_R ]
                                 , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_R ]
                                 , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT ]
                                 ]
                                    |> List.concat
                                )
                            )
                        )
            )
        |> Maybe.withDefault ifNothingToRecall


droneRecallGiveUpTicks : Int
droneRecallGiveUpTicks =
    60


droneRecallFocusRecoveryTicks : Int
droneRecallFocusRecoveryTicks =
    20


{-| How far back to look for the bot's own recall keypress.

Wide enough to span the focus-recovery branch above, which alternates a click
and a keypress, and no wider -- so a bot that has gone back to fighting stops
counting readings against a recall nobody is making any more.

-}
droneRecallAskedLookbackSteps : Int
droneRecallAskedLookbackSteps =
    3


{-| Did the bot ask for a recall recently?

Read out of the effects rather than the decision, because
`updateMemoryForNewReadingFromGame` is the only place that can write memory and
it never sees the decision. `vkey_R` is used for nothing else in this bot --
`vkey_E` is the keep-at-range, `vkey_W` the orbit and `vkey_C` the loot
window's Alt+C -- so the chord is unambiguous. It used to be `vkey_Q` that carried the
approach; that is a double click on the row now and presses no key at all, so
this argument has one fewer key to be unambiguous against rather than one more.

-}
recentStepAskedForDroneRecall : List (List EffectOnWindow.EffectOnWindowStruct) -> Bool
recentStepAskedForDroneRecall previousStepsEffects =
    previousStepsEffects
        |> List.take droneRecallAskedLookbackSteps
        |> List.any (List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_R))


previousStepClickedMouse : BotDecisionContext -> Bool
previousStepClickedMouse context =
    context.previousStepsEffects
        |> List.take 1
        |> List.any
            (List.any
                (\effect ->
                    case effect of
                        EffectOnWindow.ButtonDown _ ->
                            True

                        _ ->
                            False
                )
            )


{-| The circuit, and whether the bot is currently asking to move along it.

Printed every reading rather than only while asking, because the useful
diagnosis on a run that fails this way is "the bot asked and no route ever
appeared", and a clause that shows up only on success cannot say that.

-}
describeHuntCircuit : BotDecisionContext -> String
describeHuntCircuit context =
    let
        currentSystem =
            currentSolarSystemNameFromReading context.readingFromGameClient
                |> Maybe.withDefault "?"
    in
    if List.isEmpty context.eventContext.botSettings.huntSystemNames then
        "Sys " ++ currentSystem ++ " (no hunt circuit)."

    else
        "Sys "
            ++ currentSystem
            ++ " -> "
            ++ (nextHuntingGround context |> Maybe.withDefault "nowhere")
            ++ (case context.memory.destinationAskedFor of
                    Nothing ->
                        ""

                    Just asked ->
                        " asked '"
                            ++ asked
                            ++ "' "
                            ++ String.fromInt context.memory.destinationAskReadings
                            ++ "/"
                            ++ String.fromInt routeAskGiveUpReadings
               )
            ++ (if context.memory.routeSettingGivenUp then
                    " ROUTE SETTING GIVEN UP -- this host does not set destinations"

                else
                    ""
               )
            ++ "."


describeDroneRecall : BotDecisionContext -> String
describeDroneRecall context =
    "drones "
        ++ (context.memory.dronesInSpaceCountLastReading |> String.fromInt)
        ++ " out ("
        ++ (context.memory.dronesInSpaceTicks |> String.fromInt)
        ++ "rd) recall "
        ++ (context.memory.droneRecallUnansweredTicks |> String.fromInt)
        ++ "/"
        ++ (droneRecallGiveUpTicks |> String.fromInt)
        ++ (if droneRecallGiveUpTicks < context.memory.droneRecallUnansweredTicks then
                " GIVEN UP -- the ship will leave without them"

            else
                ""
           )
        ++ "."


{-| Lock a row, or close on it where the client will not grant a lock yet.

The approach is a **double click on the row** and presses no key. It used to
wrap a left click in a `Q` chord, which the client reads the same way -- and
`cg_input` posts a keystroke without stamping flags on it, so a posted `Q`
carries whatever modifier state the session happens to hold. With the Fn bit
set that is macOS Quick Note, and one recorded run took this branch 1,571 times
while Notes came to the front 241 times with nobody at the machine. PR #241
stops the mis-stamping; this stops the keystroke existing, and takes a
modifier-timing dependency off the hottest path in the bot.

It adds no row-shift exposure over the click it replaces. #90's concern is the
overview re-sorting between the reading and the click; a double click is one
gesture dispatched in one step, with no re-derivation between its two presses,
so it is exactly as exposed as the single click already here and no more.

-}
lockTargetFromOverviewEntry : BotDecisionContext -> OverviewWindowEntry -> DecisionPathNode
lockTargetFromOverviewEntry context overviewEntry =
    let
        targetingRange : Int
        targetingRange =
            lockRangeThresholdInMeters (lockRangeStateFrom context)
    in
    case overviewEntry.objectDistanceInMeters of
        Ok distanceInMeters ->
            if distanceInMeters <= targetingRange then
                if overviewEntry.commonIndications.targetedByMe || overviewEntry.commonIndications.targeting then
                    describeBranch "Locking target is in progress, wait for completion." waitForProgressInGame

                else
                    describeBranch ("Lock target from overview entry '" ++ (overviewEntry.objectName |> Maybe.withDefault "") ++ "'")
                        (decideActionForCurrentStep (lockChordForOverviewEntry overviewEntry))

            else if distanceInMeters <= approachRangeLimitMeters then
                describeBranch ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away). Approach.")
                    (doubleClickUiElement overviewEntry.uiNode)

            else
                warpToDistantOverviewEntry context overviewEntry distanceInMeters

        Err error ->
            describeBranch ("Failed to read the distance: " ++ error) askForHelpToGetUnstuck


{-| Past this, approaching is the wrong gesture and the client agrees.

EVE will not warp to anything closer than 150 km and an approach is how you
close the last of that distance -- so this is the game's own boundary rather
than a number picked here, and the two branches either side of it are the two
gestures the client actually offers.

Run 41 is what it costs to have no bound at all. The bot double-clicked a row
**2,266 km** away 13,541 times across three hours, `Already on the way` fired
**zero** times, and the ship never moved: three anomalies and 39 kills for a
session that had done 31 anomalies on the same settings a week earlier. A double
click at that range is not a slow approach, it is a gesture the client discards,
and nothing in the loop could tell the difference because the row stayed exactly
where it was and stayed the nearest thing worth attacking.

This is #168's shape one branch over. That issue is about an acceleration gate
chased at 1,395 km for four hours; the same failure reaches a lock candidate,
and a bound written only for gates would not have covered run 41.

-}
approachRangeLimitMeters : Int
approachRangeLimitMeters =
    150000


{-| Warp to a row too far to approach, or leave it alone.

Select-then-press on the Selected Item panel, the shape `runAway` already uses:
the panel acts on whatever is selected, so the order is load-bearing and
pressing first would warp to whatever the panel happened to be showing.

**A panel that offers no Warp To ends the attempt rather than falling back to
the approach.** That is the "do nothing" half and it is the point of the whole
change: the row is out of reach by both gestures, so spending the reading on it
is what run 41 did 13,541 times.

-}
warpToDistantOverviewEntry : BotDecisionContext -> OverviewWindowEntry -> Int -> DecisionPathNode
warpToDistantOverviewEntry context overviewEntry distanceInMeters =
    let
        name =
            overviewEntry.objectName |> Maybe.withDefault "it"

        howFar =
            " (" ++ (distanceInMeters // 1000 |> String.fromInt) ++ " km away, too far to approach)"
    in
    if not (selectedItemIsOverviewEntry context.readingFromGameClient overviewEntry) then
        describeBranch
            ("Select '" ++ name ++ "'" ++ howFar ++ ", so the panel's own Warp To acts on it.")
            (clickUiElement overviewEntry.uiNode)

    else
        case selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo" of
            Just button ->
                describeBranch
                    ("Warp to '" ++ name ++ "'" ++ howFar ++ ".")
                    (ensureDronesRecalledBeforeWarping context (clickUiElement button))

            Nothing ->
                describeBranch
                    ("Leaving '" ++ name ++ "' alone" ++ howFar ++ " -- the panel offers no Warp To, so neither gesture reaches it.")
                    waitForProgressInGame


{-| The lock chord for one row: Ctrl held over a plain left click.

Written once because a batch is literally N copies of it, so the shape
`lockClickLocationsFromStepEffects` recognises and the shape the bot dispatches
cannot come apart. `Result.withDefault []` on a row whose click point cannot be
computed leaves a bare Ctrl press, which is what this branch has always
dispatched there -- and it carries no `MouseMoveTo`, so the accounting below
counts it as the nothing it is rather than as a lock that was asked for.

-}
lockChordForOverviewEntry : OverviewWindowEntry -> List EffectOnWindow.EffectOnWindowStruct
lockChordForOverviewEntry overviewEntry =
    [ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]
    , overviewEntry.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
    , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]
    ]
        |> List.concat


{-| Ask the client for several locks in one step.

Each row gets the whole chord rather than Ctrl being held across the run, so the
batch is N repetitions of the single lock this bot has always dispatched and no
new key timing is introduced. It also keeps the host's double-click collapsing
away from it: that recogniser skips only `WaitMilliseconds` between a
press/release pair and the next press, and every chord here puts a `KeyUp`, a
`KeyDown` and a `MouseMoveTo` in between.

-}
lockTargetsFromOverviewEntries : List OverviewWindowEntry -> DecisionPathNode
lockTargetsFromOverviewEntries overviewEntries =
    decideActionForCurrentStep (overviewEntries |> List.concatMap lockChordForOverviewEntry)


{-| How many rows from the **front** of the candidate list the ship can reach.

**A prefix, not a count, because the candidate list is not in distance order.**
`decideActionInAnomaly` sorts by `combatPriorityTier` ahead of the distance order
the helper returns rows in, so a warp-disrupting entry out of reach can sit in
front of rats that are in reach -- and a batch built by _filtering_ would silently
skip the one row the bot most wants, lock the rats behind it, and never approach
the scrambler at all.

**This bot filtered until now, on a premise that had already expired.** The
comment at the batch site defended the filter on the ground that both lists ran
in the same distance order -- true when it was written, and false from the moment
PR #253 put the tier sort above that order. Nothing failed when it did: the
sentence went on reading correctly beside code the reordering had falsified.

Counting the prefix instead makes the skip impossible: a head the ship cannot
reach answers 0, which drops the batch to one row and hands the reading back to
`lockTargetFromOverviewEntry`, whose out-of-range branch approaches it exactly as
before. A batch therefore always begins with the row the single lock would have
clicked and never reaches past a row it skipped.

Takes the reachability of each row rather than the rows themselves, so a case can
execute it on plain booleans.

-}
lockBatchRowsInReach : List Bool -> Int
lockBatchRowsInReach rowsAreInReach =
    case rowsAreInReach of
        True :: rest ->
            1 + lockBatchRowsInReach rest

        _ ->
            0


{-| Everything the batch size is a function of.

`rowsToTake` is `maxTargetsRowsToTake`'s answer rather than the ceiling, so the
batch and `Enough locked targets.` cannot come to disagree about whether there
is room; `rowsLockableNow` is `lockBatchRowsInReach`'s prefix rather than a
count of everything in range, since a row out of range is answered by
approaching and an approach cannot be batched with anything.

-}
type alias LockBatchSituation =
    { targetsHeld : Int
    , rowsToTake : Int
    , rowsLockableNow : Int
    , probeIsDue : Bool
    }


lockBatchSituationFrom : BotDecisionContext -> { rowsLockableNow : Int, probe : MaxTargetsProbe } -> LockBatchSituation
lockBatchSituationFrom context { rowsLockableNow, probe } =
    { targetsHeld = context.readingFromGameClient.targets |> List.length
    , rowsToTake = maxTargetsRowsToTake (maxTargetsStateFrom context)
    , rowsLockableNow = rowsLockableNow
    , probeIsDue =
        case probe of
            MaxTargetsProbeOneMore _ ->
                True

            _ ->
                False
    }


{-| How many rows one step asks the client to lock.

**The first lock of an engagement is always asked alone, and that is what keeps
the lock-range rule whole rather than a hope that batching and learning do not
collide.** `lockAttemptCanTeachRange` is `targetsCount == 0`: an attempt begun
with the bar occupied is discharged rather than judged, because the refusal
bound needs the bar empty at both ends and no later reading can undo the count
it started with. So a lock issued with a target already held could never have
taught a refusal, and batching exactly those costs the learning nothing. The one
lock that could -- the bar empty -- is still issued on its own, still attributed
by `overviewEntryLockHandle`, and still judged exactly as before. Today's caller
cannot reach this rule with an empty bar at all, since it sits under the branch
that has already found a locked target; the clause is written out anyway,
because it is this condition rather than that placement that makes the claim
true, and a later version that batches from the other lock site must not
silently start batching the one lock a refusal can be learned from.

The probe is asked alone for the same discipline one level up: #150's probe is a
_measurement_, deliberately one row beyond the ceiling, and an answer arriving
alongside five other locks is an answer to none of them in particular.

The bound is `lockBatchMaximumClicks` and the free slots, whichever is smaller.
`max 1` because every caller of this is a branch that is about to click
something -- a batch of zero is not an answer, it is a different branch.

-}
lockBatchSize : LockBatchSituation -> Int
lockBatchSize situation =
    if situation.probeIsDue || (situation.targetsHeld < 1) then
        1

    else
        max 1
            (min lockBatchMaximumClicks
                (min situation.rowsLockableNow (situation.rowsToTake - situation.targetsHeld))
            )


{-| The most lock clicks one step will ask for.

**A batch is a step with no reading in it**, so its whole length is time the
retreat, the ship-loss verdict and every other guard cannot act on. Measured over
all 16 recorded saxrat runs and their 50,043 `send-effects` steps, this bot's
longest input step ever dispatched is **4.68 s** and its median is 1.03 s; a lock
step's own median is 2.56 s, of which the host's eased glide and its click settle
are most. So three clicks is about 7 s and is deliberately the first thing this
bot does that runs past its own recorded longest step -- the bound is what keeps
"past it" to roughly one reading's worth rather than to an open-ended one.

The second reason is #163's: posted input is dropped silently under load in this
environment, at 53-100 ms per event in the two runs that lost a typed query
against under 18 ms everywhere else, and a burst is exactly the shape that fails
that way. A bound caps how many locks one such episode can take with it, which is
worth having even though `updateLockBatchAccounting` counts what went missing.

-}
lockBatchMaximumClicks : Int
lockBatchMaximumClicks =
    3


{-| Whether a batch already dispatched is still waiting for the target bar.

The bar lags the clicks -- a lock takes a moment to register -- and
`overviewEntriesToLock` filters on the rows' own indicators, so without this the
next reading would find the same rows still unlocked and click every one of them
a second time. That is `moduleButtonClickSettlingSteps`' problem in the lock
site, and it costs more here: a whole batch re-issued is several seconds of the
engagement spent asking for locks already granted.

Only batches settle. A single lock is left exactly as it was, repeated clicks
and all, because that is the behaviour every recorded run was flown on and
narrowing it is not this change.

-}
lockBatchIsSettling : Maybe LockBatchDispatch -> Bool
lockBatchIsSettling dispatch =
    dispatch /= Nothing


{-| The setting and both learned bounds, as one value a case can build.

Every rule below is a function of this record rather than of a whole
`BotDecisionContext`, which is what makes them executable in `elm repl` at all:
a decision context carries a screenshot and a framework event context, and a
rule reachable only through one can be checked by reading it and no other way.

-}
type alias LockRangeState =
    { fromSetting : Int
    , statedMeters : Maybe Int
    , provenAtMeters : Maybe Int
    , refusedAtMeters : Maybe Int
    , attempt : Maybe LockAttempt
    }


lockRangeStateFrom : BotDecisionContext -> LockRangeState
lockRangeStateFrom context =
    { fromSetting = context.eventContext.botSettings.targetingRangeMeters
    , statedMeters = context.memory.lockRangeStatedMeters
    , provenAtMeters = context.memory.lockProvenAtMeters
    , refusedAtMeters = context.memory.lockRefusedAtMeters
    , attempt = context.memory.lockAttempt
    }


{-| The distance at which the bot switches from locking to approaching.

The `targeting-range` setting is a guess about the ship, and a wrong one is
costly both ways: too low and the bot flies at rats it could simply shoot, too
high and it spends readings asking for locks the client will never grant. The
client answers this question every time it accepts or refuses a lock, so the
setting is treated as a starting value and clamped into the interval the
client's own answers have established -- `[lockProvenAtMeters,
lockRefusedAtMeters)`, the same shape as the self-calibrated UI scale the host
derives per session rather than assuming.

With no evidence yet both bounds are `Nothing` and this is exactly the setting,
so nothing changes until something is learned. When the two contradict each
other -- possible after a refit, since the bounds are not reset mid-session --
the proven distance wins: a lock that completed is unambiguous evidence, where
a refusal is an inference from several conditions holding at once.

-}
lockRangeThresholdInMeters : LockRangeState -> Int
lockRangeThresholdInMeters state =
    let
        loweredByRefusal : Int
        loweredByRefusal =
            case state.refusedAtMeters of
                Nothing ->
                    state.fromSetting

                Just refusedAt ->
                    min state.fromSetting (refusedAt - 1)

        fromMeasurements : Int
        fromMeasurements =
            case state.provenAtMeters of
                Nothing ->
                    loweredByRefusal

                Just provenAt ->
                    max provenAt loweredByRefusal
    in
    case state.statedMeters of
        -- The client naming the number outranks both measurements, and #206 is
        -- what happens when it does not. `provenAtMeters` only ever rises, so an
        -- attribution error that credits a lock to a more distant row is
        -- permanent -- run 28 ratcheted to 77 km on a hull whose real range is
        -- 49 km, crossing its own refusal at 33 km, while the client had said
        -- `It must be within 49 km` on 1,277 live sightings of that run. A bound
        -- inferred from several conditions holding at once cannot outweigh the
        -- client answering in words.
        --
        -- Still `min` with the setting, because an operator asking for a
        -- narrower range than the ship can manage is asking for something the
        -- client will grant, and this rule has never overridden that direction.
        Just stated ->
            min state.fromSetting stated

        Nothing ->
            fromMeasurements


{-| Whether the ship can lock this row from where it is standing.

Only used to choose a row to **probe** with. `lockTargetFromOverviewEntry`
answers an out-of-range row by approaching it, which is right for a target the
bot wants and wrong for a measurement: flying at a rat to find out whether a
fifth lock slot exists would spend the ship's position on a question the next
row in range answers for nothing. A row whose distance does not parse is not
one the ship can reach either -- an AU distance is an `Err`, and the whole
overview section of CLAUDE.md is about not treating that as merely far.

-}
overviewEntryIsWithinLockRange : BotDecisionContext -> OverviewWindowEntry -> Bool
overviewEntryIsWithinLockRange context entry =
    case entry.objectDistanceInMeters of
        Ok distanceInMeters ->
            distanceInMeters <= lockRangeThresholdInMeters (lockRangeStateFrom context)

        Err _ ->
            False


allOverviewEntries : ReadingFromGameClient -> List OverviewWindowEntry
allOverviewEntries readingFromGameClient =
    readingFromGameClient.overviewWindows |> List.concatMap .entries


{-| A handle on an overview row that survives to the next reading, or nothing
when this row cannot be told apart from another.

Screen position answers "what did that click hit", but it cannot answer "is
this the same object as last reading": the overview re-sorts and virtualises,
so a position is about a row, not about an object, and matching a lock outcome
to the wrong object is exactly the mistake that would teach the bot a wrong
range. EVE's own `itemID` is the right answer where the row carries one.

Where it does not, the row's name is used, but only when no other row in the
overview shares it -- one of five identical rats says nothing about which one
the client answered. A pocket of same-named rats therefore yields no evidence
at all, which is the correct outcome rather than a guess.

**This bot is the worst case for that, and the branch is not to be loosened.**
An anomaly is a pocket of identically named rats by construction, so "no
evidence" is the ordinary answer here rather than the exception the mission
runner meets. A rule that fires often and sometimes teaches a wrong range is
worse than one that rarely fires: the wrong range is sticky for the session,
where a rule that stays silent costs only the learning.

-}
overviewEntryLockHandle : List OverviewWindowEntry -> OverviewWindowEntry -> Maybe String
overviewEntryLockHandle allEntries entry =
    case entry.objectItemID of
        Just itemID ->
            Just ("id:" ++ itemID)

        Nothing ->
            case entry.objectName of
                Nothing ->
                    Nothing

                Just name ->
                    if (allEntries |> List.filter (\other -> other.objectName == Just name) |> List.length) == 1 then
                        Just ("name:" ++ name)

                    else
                        Nothing


{-| The screen points the lock clicks of one step went to, in dispatch order.

The lock chord is Ctrl held over a plain left click
(`lockChordForOverviewEntry`). Ctrl is pressed in one other place here and it
cannot be mistaken for this one: `ctrlShiftClickUiElement`, the unlock, holds
Shift as well. Both conditions are still checked rather than only the first,
because the second used to be load-bearing and the reason it stopped is a
change to a different branch: the loot window pressed a keys-only `Ctrl+W`
until #285, which carried no `MouseMoveTo` for this to take. Its `Alt+C`
presses no Ctrl at all, so a bot that grows another keys-only chord should
fail to attribute rather than attribute wrongly.

**Every point rather than the first**, which is what makes a batched step
distinguishable from a single lock at all. A reader answering `Maybe` cannot
tell "one lock" from "six locks, of which this is the one I happened to take",
so it would have gone on attributing the next reading's outcome to the first row
of a batch -- the feature working while the measurement behind it quietly
stopped, which is what this repo keeps finding. The count is also what the batch
accounting is asked for, so what was _asked for_ is counted out of the effects
themselves and can never disagree with what was dispatched.

Reading the attempt out of the effects rather than out of the decision is not a
detour: `updateMemoryForNewReadingFromGame` is the only place that can write
memory, and it sees the previous steps' effects but not the decision that
produced them.

-}
lockClickLocationsFromStepEffects : List EffectOnWindow.EffectOnWindowStruct -> List EffectOnWindow.Location2d
lockClickLocationsFromStepEffects effects =
    if
        (effects |> List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL))
            && not (effects |> List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT))
    then
        effects
            |> List.filterMap
                (\effect ->
                    case effect of
                        EffectOnWindow.MouseMoveTo location ->
                            Just location

                        _ ->
                            Nothing
                )

    else
        []


locationIsInDisplayRegion : EffectOnWindow.Location2d -> EveOnline.ParseUserInterface.DisplayRegion -> Bool
locationIsInDisplayRegion location region =
    (region.x <= location.x)
        && (location.x < region.x + region.width)
        && (region.y <= location.y)
        && (location.y < region.y + region.height)


{-| Everything about one reading the lock-range rule looks at.

The rule takes this rather than an `UpdateMemoryContext` so that a case can
build one and fold a whole session through it. Nothing is pre-digested on the
way in beyond picking the fields out: the ship UI arrives whole, because
"docked, so nothing could have been locked" is a judgement that belongs in the
rule and not in the caller that assembles its input.

`lastStepEffects` is the _most recent_ step's effects only. A lock click is
answered by the very next reading or not at all, and a longer lookback would
re-open an attempt the bot has already moved on from.

-}
type alias LockRangeReading =
    { entries : List OverviewWindowEntry
    , shipUI : Maybe ShipUI
    , targetsCount : Int
    , lastStepEffects : List EffectOnWindow.EffectOnWindowStruct
    }


lockRangeReadingFrom : UpdateMemoryContext BotSettings -> LockRangeReading
lockRangeReadingFrom context =
    { entries = allOverviewEntries context.readingFromGameClient
    , shipUI = context.readingFromGameClient.shipUI
    , targetsCount = context.readingFromGameClient.targets |> List.length
    , lastStepEffects = context.previousStepsEffects |> List.head |> Maybe.withDefault []
    }


{-| What the two learned bounds and the pending attempt look like after this
reading.

Returned as one record rather than written field by field, so the whole of the
rule lives in one place and `updateMemoryForNewReadingFromGame` gains four
lines rather than four blocks that would each have to re-derive the others.

-}
type alias LockRangeLearning =
    { attempt : Maybe LockAttempt
    , provenAtMeters : Maybe Int
    , refusedAtMeters : Maybe Int
    , change : Maybe String
    }


{-| Move the lock-range bounds on what the client has just answered.

Two values, each moving in one direction only, so no oscillation is possible:
`lockProvenAtMeters` is the greatest distance at which a lock has succeeded and
only rises, `lockRefusedAtMeters` the smallest distance at which one has
provably failed and only falls.

Success is unambiguous -- a row that reads `targetedByMe` or `targeting` is the
client having accepted, and nothing else makes a row read that way. Failure is
not, which is why it takes all of the following at once:

  - the attempt has had `lockAttemptReadingsBeforeVerdict` readings to land, so
    a merely slow lock is not read as a refused one;
  - the row is still in the overview and still `_display`ed, so the object did
    not die and we are not looking at a different object recycled into that
    row;
  - the row still does not read as targeted or targeting;
  - and the target bar was empty at both ends of the attempt, which covers both
    "the count of locked targets did not go up" and "the ship had a slot to
    lock into".

That last one is what separates "too far" from "no free slot". An empty target
bar is the only thing a reading can say that _proves_ a slot was free -- the
client's maximum is not in the reading at all, and `max-target-count` is the
bot's own ceiling rather than the client's. It costs more here than it does in
the mission runner: this bot locks up to four rats and holds them, so only the
first lock of an anomaly can ever teach a refusal. That is also the case that
costs the most -- everything on the grid out of reach, and the bot asking for a
lock it will never get, reading after reading.

The bot's own target selection is not visible from here, so this does not try
to work out whether the row _should_ have been locked. It only follows the
click the bot actually made, which also keeps it out of the way of whatever
`decideActionInAnomaly`'s candidate list grows into.

The bounds are not reset within a session: `BotMemory` starts fresh with each
one, and the ship does not change mid-session in the way this bot flies.

**A step that asked for more than one lock teaches this rule nothing, and
discharges whatever was pending.** Attribution is the whole safety of the rule
and a batch breaks it in both directions at once: the next reading's outcome
belongs to no one click in particular, and the bar the batch itself filled is
the very thing the refusal test reads to decide whether a slot was free. So a
batched reading is treated as the absence of evidence it is, which is
`overviewEntryLockHandle`'s posture applied to the step rather than to the row.
`lockBatchSize` is what makes that cost nothing: it issues a batch only where
the bar is already occupied, and such a lock could never have moved either bound
anyway -- see `lockAttemptCanTeachRange`.

-}
updateLockRangeLearning : LockRangeReading -> LockRangeState -> LockRangeLearning
updateLockRangeLearning reading stateBefore =
    let
        entries : List OverviewWindowEntry
        entries =
            reading.entries

        targetsCount : Int
        targetsCount =
            reading.targetsCount

        unchanged : LockRangeLearning
        unchanged =
            { attempt = stateBefore.attempt
            , provenAtMeters = stateBefore.provenAtMeters
            , refusedAtMeters = stateBefore.refusedAtMeters
            , change = Nothing
            }

        -- Nothing can be locked in warp or from inside a station, so an attempt
        -- that runs into either is abandoned rather than judged. The bot cannot
        -- *start* one there, but it can be halfway through one when the ship
        -- warps out of a pocket it is losing, and a lock nobody could have
        -- granted must not read as a lock the ship was too far away for.
        shipCannotLock : Bool
        shipCannotLock =
            case reading.shipUI of
                Nothing ->
                    True

                Just shipUI ->
                    shipUIIndicatesShipIsWarpingOrJumping shipUI

        lockClickLocations : List EffectOnWindow.Location2d
        lockClickLocations =
            reading.lastStepEffects |> lockClickLocationsFromStepEffects

        -- The step asked for several locks at once, so nothing this reading
        -- shows can be attributed to any one of them. See the doc comment.
        stepWasBatched : Bool
        stepWasBatched =
            1 < (lockClickLocations |> List.length)

        -- The row the step just dispatched aimed its lock click at, if it did.
        -- Resolved by screen position against this reading, which is a reading
        -- later than the one the click was decided on -- and that is the right
        -- way round rather than a compromise: the client acted on whatever was
        -- rendered at that point, so if the overview re-sorted in between, the
        -- row found here is the row the click actually hit. Only rendered rows
        -- are considered, for the reason the whole overview section of CLAUDE.md
        -- exists: a hidden row's region belongs to whatever was recycled into
        -- it.
        entryJustClicked : Maybe OverviewWindowEntry
        entryJustClicked =
            lockClickLocations
                |> List.head
                |> Maybe.andThen
                    (\location ->
                        entries
                            |> List.filter overviewEntryIsDisplayed
                            |> List.filter (\entry -> locationIsInDisplayRegion location entry.uiNode.totalDisplayRegion)
                            |> List.head
                    )

        attemptAfterClick : Maybe LockAttempt
        attemptAfterClick =
            case entryJustClicked of
                Nothing ->
                    stateBefore.attempt

                Just entry ->
                    case ( overviewEntryLockHandle entries entry, entry.objectDistanceInMeters ) of
                        ( Just handle, Ok distanceInMeters ) ->
                            case stateBefore.attempt of
                                Just pending ->
                                    if pending.handle == handle then
                                        -- The bot asking again for the same row
                                        -- is the same attempt, not a new one.
                                        Just pending

                                    else
                                        -- It has moved on to another row. The
                                        -- old attempt is abandoned rather than
                                        -- judged: nobody is waiting on it.
                                        Just
                                            { handle = handle
                                            , distanceInMeters = distanceInMeters
                                            , targetsCount = targetsCount
                                            , readingsWaited = 0
                                            }

                                Nothing ->
                                    Just
                                        { handle = handle
                                        , distanceInMeters = distanceInMeters
                                        , targetsCount = targetsCount
                                        , readingsWaited = 0
                                        }

                        _ ->
                            stateBefore.attempt
    in
    if stepWasBatched then
        -- Nothing is learned and nothing is carried. Discharging rather than
        -- merely declining to open one, because an attempt still pending when a
        -- batch goes out is an attempt whose verdict would be read against a bar
        -- the batch itself is filling.
        { unchanged | attempt = Nothing }

    else
        case attemptAfterClick of
            Nothing ->
                unchanged

            Just attempt ->
                let
                    entryNow : Maybe OverviewWindowEntry
                    entryNow =
                        if shipCannotLock then
                            Nothing

                        else
                            entries
                                |> List.filter overviewEntryIsDisplayed
                                |> List.filter (\entry -> overviewEntryLockHandle entries entry == Just attempt.handle)
                                |> List.head
                in
                case entryNow of
                    Nothing ->
                        -- The row is gone or is no longer rendered, or the ship
                        -- cannot lock anything just now. It may have died, or
                        -- scrolled out of view, or the overview may have re-sorted
                        -- -- none of which says anything about range. A second row
                        -- taking the same name also lands here, since the handle
                        -- stops resolving the moment the name is shared.
                        { unchanged | attempt = Nothing }

                    Just entry ->
                        let
                            -- Held at the bound rather than allowed to run on, for
                            -- the same reason the drone give-up latches: the number
                            -- is shown to an operator, and one that climbs forever
                            -- while nothing is waiting on it reads as a fault.
                            attemptCarried : Maybe LockAttempt
                            attemptCarried =
                                Just
                                    { attempt
                                        | readingsWaited =
                                            min lockAttemptReadingsBeforeVerdict (attempt.readingsWaited + 1)
                                    }

                            -- The distance a bound moves to lies somewhere between
                            -- the reading the attempt started on and this one. Each
                            -- bound takes the end that makes the weaker claim -- the
                            -- smaller distance for the one that only rises, the
                            -- larger for the one that only falls -- so neither is
                            -- ever moved further than the evidence reaches.
                            distanceNow : Int
                            distanceNow =
                                entry.objectDistanceInMeters |> Result.withDefault attempt.distanceInMeters
                        in
                        if overviewEntryIsTargetedOrTargeting entry then
                            let
                                provenAt : Int
                                provenAt =
                                    min attempt.distanceInMeters distanceNow

                                -- A completed lock ends the attempt. One still
                                -- spooling up does not: `targeting` is the client
                                -- having accepted the request, not having finished
                                -- it, and a lock that is accepted and never finishes
                                -- is exactly the wait this bound exists to end.
                                attemptAfter : Maybe LockAttempt
                                attemptAfter =
                                    if entry.commonIndications.targetedByMe then
                                        Nothing

                                    else
                                        attemptCarried
                            in
                            if provenAt > (stateBefore.provenAtMeters |> Maybe.withDefault 0) then
                                { attempt = attemptAfter
                                , provenAtMeters = Just provenAt
                                , refusedAtMeters = stateBefore.refusedAtMeters
                                , change =
                                    Just
                                        ("Learned lock range: the client accepted a lock at "
                                            ++ (provenAt |> String.fromInt)
                                            ++ " m, further than anything locked before -- lock-proven-at rises from "
                                            ++ (stateBefore.provenAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "unset")
                                            ++ " to "
                                            ++ (provenAt |> String.fromInt)
                                            ++ " m."
                                        )
                                }

                            else
                                { unchanged | attempt = attemptAfter }

                        else if not (lockAttemptCanTeachRange attempt) then
                            -- The client did not take this lock and the bar was not
                            -- empty when it was asked, so there is nothing here for
                            -- either bound and nothing to wait for. See
                            -- `lockAttemptCanTeachRange`.
                            { unchanged | attempt = Nothing }

                        else if attempt.readingsWaited < lockAttemptReadingsBeforeVerdict then
                            { unchanged | attempt = attemptCarried }

                        else if (attempt.targetsCount /= 0) || (targetsCount /= 0) then
                            -- The ship held a locked target at one end of the
                            -- attempt or the other, so it may simply have had no free
                            -- slot -- and it may equally have locked something else
                            -- while this one was waiting. An empty target bar at both
                            -- ends is the one reading that rules out both at once,
                            -- and only then is a lock that never landed evidence
                            -- about range rather than about capacity.
                            --
                            -- The first of the two is unreachable now, since
                            -- `lockAttemptCanTeachRange` discharges such an attempt
                            -- several branches above. It is written out anyway
                            -- because it is this condition rather than that
                            -- placement that makes the claim true, and a later
                            -- version that moves the discharge must not silently
                            -- start learning a range from a full bar.
                            { unchanged | attempt = attemptCarried }

                        else
                            let
                                refusedAt : Int
                                refusedAt =
                                    max attempt.distanceInMeters distanceNow
                            in
                            if refusedAt < (stateBefore.refusedAtMeters |> Maybe.withDefault (refusedAt + 1)) then
                                { attempt = attemptCarried
                                , provenAtMeters = stateBefore.provenAtMeters
                                , refusedAtMeters = Just refusedAt
                                , change =
                                    Just
                                        ("Learned lock range: '"
                                            ++ (entry.objectName |> Maybe.withDefault "a target")
                                            ++ "' at "
                                            ++ (refusedAt |> String.fromInt)
                                            ++ " m did not lock in "
                                            ++ (lockAttemptReadingsBeforeVerdict |> String.fromInt)
                                            ++ " readings with the target bar empty throughout -- lock-refused-at falls from "
                                            ++ (stateBefore.refusedAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "unset")
                                            ++ " to "
                                            ++ (refusedAt |> String.fromInt)
                                            ++ " m."
                                        )
                                }

                            else
                                -- The verdict stands, but the bound is already at
                                -- least this tight, so nothing moves and nothing is
                                -- said. That is what keeps the log line one per
                                -- change rather than one per reading, with no
                                -- separate "already reported" flag to get wrong.
                                { unchanged | attempt = attemptCarried }


{-| How many readings a lock the bot asked for gets to land before the outcome
is called.

Generous, because a legitimate lock is not instant -- a big ship locking a
small one takes seconds, and a reading is a couple of seconds -- and calling a
slow lock a refusal would teach the bot a range that is too short and make it
fly at rats it could have shot. A refusal, by contrast, is immediate: the
client answers an out-of-range lock at once and nothing about the row ever
changes, so waiting longer than necessary costs only how quickly the bounds
converge, never their correctness.

-}
lockAttemptReadingsBeforeVerdict : Int
lockAttemptReadingsBeforeVerdict =
    8


{-| Whether a lock the bot asked for can still teach the lock range anything.

The refusal below needs the target bar **empty at both ends** of the attempt,
so an attempt begun while the ship already held a target can never move either
bound however long it is carried: it fails that condition rather than the wait,
and no later reading can undo the count it started with.

That makes the wait pure cost, and it is a measured one. The pending attempt
sits at `for 8 readings` -- the verdict count, latched -- on **more than three
thousand** status lines across 22 recorded runs, while `stop waiting for it` has
fired **zero** times in the whole corpus: the give-up is only asked of a row that
reads `targeting`, and a lock the client declines never does. Run 37 is the shape,
live and unattended: `Lock more targets.` clicked a row while the bar was full
at six, the client answered `You are already managing 6 targets, as many as you
have skill to.` on the next reading, and the attempt climbed to the bound and
stayed there for nineteen readings of an operator's status line saying a lock
had not landed.

So a click the client declines with the bar occupied is discharged at once
rather than waited out. That is also what keeps #150's probe out of this
machinery entirely -- a probe is by definition asked with the bar at the ceiling
-- so a refused probe spends none of this budget and can never trip the give-up.
What it costs is the _proven_ bound: a lock that lands slowly with a target
already held is now credited from the reading the bot re-asked rather than the
first, which is the weaker claim of two and so the safe direction.

-}
lockAttemptCanTeachRange : LockAttempt -> Bool
lockAttemptCanTeachRange attempt =
    attempt.targetsCount == 0


{-| The first of the pair the client's own sentence has to carry.

`#31`'s reason: one common phrase matches sentences this must not read. "too far
away" alone is written about warping, about approaching, and about interacting
with a container; only the pairing with a stated ceiling makes it the lock range.

-}
lockRangeTooFarMarker : String
lockRangeTooFarMarker =
    "too far away"


{-| The second, and the one carrying the number.

    The target <b>Centii Minion</b> is too far away. It must be within <b>49 km</b>.

-}
lockRangeCeilingMarker : String
lockRangeCeilingMarker =
    "must be within"


{-| The ceiling the client stated on this reading, in meters, if it stated one.

**Only `km`.** The corpus writes this sentence one way and every sighting is in
kilometres; a bare number or a unit this does not know is answered `Nothing`
rather than guessed at, because the failure of a guess here is a threshold the
bot then trusts over its own measurements.

Markup is stripped first -- the number arrives inside `<b>` tags -- which is
`textWithoutMarkupTags`' job and the same thing the fleet-invitation reader does
with a `showinfo` link.

-}
lockRangeStatedInText : String -> Maybe Int
lockRangeStatedInText text =
    let
        plain : String
        plain =
            text |> textWithoutMarkupTags |> String.toLower
    in
    if not (plain |> String.contains lockRangeTooFarMarker) then
        Nothing

    else
        case plain |> String.split lockRangeCeilingMarker of
            _ :: afterMarker :: _ ->
                case afterMarker |> String.words of
                    number :: unit :: _ ->
                        if unit |> String.startsWith "km" then
                            number |> String.toInt |> Maybe.map ((*) 1000)

                        else
                            Nothing

                    _ ->
                        Nothing

            _ ->
                Nothing


{-| What the client said about the lock range on this reading, if anything.

Read from the quick message **on screen now** rather than from the game log's
echo of it: the same sentence is reprinted under every decision for as long as it
is remembered, and counting those would make one refusal look like hundreds.

-}
lockRangeStatedInQuickMessage : ReadingFromGameClient -> Maybe Int
lockRangeStatedInQuickMessage readingFromGameClient =
    readingFromGameClient
        |> quickMessageOnScreen
        |> Maybe.andThen (.text >> lockRangeStatedInText)


{-| The lock-range bounds, for the status line.

Continuous rather than once-per-change, unlike the decision-log line: a number
the bot adjusts for itself is worth being able to read at any moment, not only
on the reading it moved. The pending attempt is here too, because a bot that
keeps clicking a lock it will never get shows up as an attempt sitting at the
verdict count long before either bound has anything to say -- and, in an
anomaly, an attempt that reads `none` reading after reading is the row-identity
rule declining to attribute, which is the expected answer here and not a fault.

-}
describeLockRange : LockRangeState -> String
describeLockRange state =
    "lock "
        ++ (lockRangeThresholdInMeters state |> String.fromInt)
        ++ "m (set "
        ++ (state.fromSetting |> String.fromInt)
        ++ " client "
        ++ (state.statedMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ " proven "
        ++ (state.provenAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ " refused "
        ++ (state.refusedAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ " attempt "
        ++ (state.attempt
                |> Maybe.map (\attempt -> String.fromInt attempt.distanceInMeters ++ "m/" ++ String.fromInt attempt.readingsWaited ++ " readings")
                |> Maybe.withDefault "none"
           )
        ++ ")."


{-| Everything the batch accounting looks at on one reading.

`targetsCountBefore` is the bar on the _previous_ reading, which is the reading a
step's effects were decided from -- so it is what the batch expected to add to,
and the only number the client's answer can be measured against. `targetsCount`
is this reading's.

`clicksAsked` is counted out of the effects that were dispatched rather than out
of the rows the decision picked, so a row whose click point could not be computed
contributes no `MouseMoveTo` and is never counted as a lock that was asked for.

-}
type alias LockBatchReading =
    { clicksAsked : Int
    , targetsCount : Int
    , targetsCountBefore : Int
    }


lockBatchReadingFrom : UpdateMemoryContext BotSettings -> Int -> LockBatchReading
lockBatchReadingFrom context targetsCountBefore =
    { clicksAsked =
        context.previousStepsEffects
            |> List.head
            |> Maybe.withDefault []
            |> lockClickLocationsFromStepEffects
            |> List.length
    , targetsCount = context.readingFromGameClient.targets |> List.length
    , targetsCountBefore = targetsCountBefore
    }


{-| What the batch bookkeeping looks like after this reading.

The two totals are for the session and only ever rise. `change` holds a sentence
only on the reading a batch was judged short, `lockRangeLastChange`'s mechanism
for its reason: one line per shortfall, with no separate "already reported" flag.

-}
type alias LockBatchAccounting =
    { dispatch : Maybe LockBatchDispatch
    , clicksAsked : Int
    , clicksAnswered : Int
    , change : Maybe String
    }


{-| The state the accounting carries between readings.
-}
type alias LockBatchState =
    { dispatch : Maybe LockBatchDispatch
    , clicksAsked : Int
    , clicksAnswered : Int
    }


lockBatchStateFrom : BotDecisionContext -> LockBatchState
lockBatchStateFrom context =
    { dispatch = context.memory.lockBatch
    , clicksAsked = context.memory.lockBatchClicksAsked
    , clicksAnswered = context.memory.lockBatchClicksAnswered
    }


{-| Count what a batch asked the client for against what the target bar did.

**This exists because a dropped lock click is silent.** #163 established that in
this environment posted input is dropped under load -- in the two runs that lost
a typed query every posted event cost 53-100 ms against under 18 ms everywhere
else, and characters vanished with nothing noticing -- and #75's
`Emperor Family Bureau` arriving as `eueu` is the same mechanism. A burst of
clicks is exactly that shape, and the failure it produces is a bar with fewer
targets in it, which reads identically to a bar that was only ever asked for
fewer. So the number asked for is written down, and the bar is read back.

The bar is measured from `targetsCountBefore`, the reading the step was decided
from, rather than from the reading that observes the click: some of the batch may
already have landed by then, which would understate what the client answered.

**Two confounds, and both are stated rather than designed around, because this
only ever reports.** A rat dying inside the window lowers the bar and reads as a
click that went missing; a lock the ship took by itself raises it and reads as
one that landed. Neither can be told apart from a drop by anything in a reading,
which is exactly why nothing decides on this number -- it is an instrument for an
operator, and in particular it never reaches the lock-range rule, which declines
to learn from a batched reading at all.

The verdict also ends the settling window `lockBatchIsSettling` holds the lock
site in, so this is what bounds that wait: the bar catching up ends it early, and
`lockBatchReadingsBeforeVerdict` ends it whatever the client does.

-}
updateLockBatchAccounting : LockBatchReading -> LockBatchState -> LockBatchAccounting
updateLockBatchAccounting reading stateBefore =
    let
        unchanged : LockBatchAccounting
        unchanged =
            { dispatch = stateBefore.dispatch
            , clicksAsked = stateBefore.clicksAsked
            , clicksAnswered = stateBefore.clicksAnswered
            , change = Nothing
            }

        judged : LockBatchDispatch -> Int -> LockBatchAccounting
        judged dispatch answered =
            { dispatch = Nothing
            , clicksAsked = stateBefore.clicksAsked + dispatch.clicksAsked
            , clicksAnswered = stateBefore.clicksAnswered + answered
            , change =
                if answered < dispatch.clicksAsked then
                    Just
                        ("Lock batch came up short: asked the client for "
                            ++ (dispatch.clicksAsked |> String.fromInt)
                            ++ " locks in one step with the target bar at "
                            ++ (dispatch.targetsCountBefore |> String.fromInt)
                            ++ ", and "
                            ++ (lockBatchReadingsBeforeVerdict |> String.fromInt)
                            ++ " readings later it holds "
                            ++ (reading.targetsCount |> String.fromInt)
                            ++ " -- "
                            ++ (dispatch.clicksAsked - answered |> String.fromInt)
                            ++ " unaccounted for. A rat dying inside that window reads the same way, so this is a count to watch rather than a verdict."
                        )

                else
                    Nothing
            }
    in
    let
        answeredFor : LockBatchDispatch -> Int
        answeredFor dispatch =
            max 0 (reading.targetsCount - dispatch.targetsCountBefore)
    in
    if 1 < reading.clicksAsked then
        let
            -- A batch was just dispatched. Any dispatch still open is
            -- unreachable here, since the lock site waits out the settling
            -- window that only a verdict ends -- this replaces it anyway,
            -- because it is that rather than the placement which keeps one
            -- batch from being credited with another's locks.
            dispatched : LockBatchDispatch
            dispatched =
                { clicksAsked = reading.clicksAsked
                , targetsCountBefore = reading.targetsCountBefore
                , readingsWaited = 0
                }
        in
        if dispatched.clicksAsked <= answeredFor dispatched then
            -- The bar already holds every lock the batch asked for, on the very
            -- reading the clicks are seen. Judged now rather than opened, so a
            -- client that answers at once costs no settling reading at all --
            -- which would otherwise be a third of what batching three clicks
            -- saves.
            judged dispatched (answeredFor dispatched)

        else
            { unchanged | dispatch = Just dispatched }

    else
        case stateBefore.dispatch of
            Nothing ->
                unchanged

            Just dispatch ->
                if dispatch.clicksAsked <= answeredFor dispatch then
                    judged dispatch (answeredFor dispatch)

                else if dispatch.readingsWaited < lockBatchReadingsBeforeVerdict then
                    { unchanged | dispatch = Just { dispatch | readingsWaited = dispatch.readingsWaited + 1 } }

                else
                    judged dispatch (answeredFor dispatch)


{-| How many readings a batch gets before its locks are counted.

Shorter than `lockAttemptReadingsBeforeVerdict`, and for the opposite reason:
that one bounds a _verdict about the client_ and is generous because calling a
slow lock a refusal would teach a wrong range, where this one bounds a **wait**
-- the lock site holds still while it runs -- and nothing is concluded from it
beyond a number in the status line. Four readings is roughly the six to ten
seconds a lock takes to register at this bot's cadence, and being wrong costs one
line of an operator's status text rather than any decision at all.

-}
lockBatchReadingsBeforeVerdict : Int
lockBatchReadingsBeforeVerdict =
    4


{-| The batch bookkeeping, for the status line.

The session totals are the point: one batch coming up short is a rat that died,
and a run whose answered count trails its asked count all evening is input being
dropped -- which is the distinction #163 says a reading cannot make on its own and
an operator can make across a session.

-}
describeLockBatch : LockBatchState -> String
describeLockBatch state =
    "batch "
        ++ (lockBatchMaximumClicks |> String.fromInt)
        ++ " asked "
        ++ (state.clicksAsked |> String.fromInt)
        ++ " got "
        ++ (state.clicksAnswered |> String.fromInt)
        ++ " this session"
        ++ (case state.dispatch of
                Nothing ->
                    ", none waiting"

                Just dispatch ->
                    ", waiting on "
                        ++ (dispatch.clicksAsked |> String.fromInt)
                        ++ " asked with the bar at "
                        ++ (dispatch.targetsCountBefore |> String.fromInt)
                        ++ " for "
                        ++ (dispatch.readingsWaited |> String.fromInt)
                        ++ "/"
                        ++ (lockBatchReadingsBeforeVerdict |> String.fromInt)
                        ++ " readings"
           )
        ++ "."


{-| What the lock site says on the reading it asks for a batch.

Opens with `Lock more targets.` because that is the line an operator has been
grepping for since before any of this, and a reading where the bot asked for
three locks is still a reading where it asked for more targets -- see
`describeMaxTargetsProbe`, whose wording this keeps rather than replaces. The
rows are named because the batch is the one decision here that acts on more than
one object, and a log line saying only how many were clicked cannot be checked
against the bar afterwards.

-}
describeLockBatchAsked : List OverviewWindowEntry -> String
describeLockBatchAsked overviewEntries =
    "Lock more targets. Asking for "
        ++ (overviewEntries |> List.length |> String.fromInt)
        ++ " locks in this one step, at "
        ++ (overviewEntries
                |> List.map (\entry -> "'" ++ (entry.objectName |> Maybe.withDefault "") ++ "'")
                |> String.join ", "
           )
        ++ " -- the bar already holds a target, so no lock in this step could have taught the lock range anything and none of them is asked to."


{-| What the lock site says while a batch it already asked for is settling.

The bar lags the clicks, so without this wait the next reading finds the same
rows unlocked and clicks every one of them again -- a whole batch re-issued,
which is several seconds of an engagement spent asking for locks the client has
already granted. `updateLockBatchAccounting` is what ends it, either because the
bar caught up or because `lockBatchReadingsBeforeVerdict` ran out, so the wait
cannot outlive the count that is watching it.

-}
describeLockBatchSettling : Maybe LockBatchDispatch -> String
describeLockBatchSettling dispatch =
    case dispatch of
        Nothing ->
            -- Unreachable from a branch that only runs while one is open. Said
            -- the ordinary way rather than invented, so a caller that reaches it
            -- anyway reports the wait it is in rather than a batch it has not made.
            "Waiting for the target bar to catch up with the last batch of locks."

        Just open ->
            "Asked for "
                ++ (open.clicksAsked |> String.fromInt)
                ++ " locks in one step "
                ++ (open.readingsWaited |> String.fromInt)
                ++ " reading(s) ago and the target bar has not caught up -- wait rather than click those rows again, which would ask for locks the client has already granted."


{-| The setting, and everything the client has said about this ship's lock slots.

Every rule below is a function of this record rather than of a whole
`BotDecisionContext`, which is what makes them executable in `elm repl` at all:
a decision context carries a screenshot and a framework event context, and a
rule reachable only through one can be checked by reading it and in no other
way. `LockRangeState`'s reason, and #106's.

-}
type alias MaxTargetsState =
    { fromSetting : Int
    , statedByClient : Maybe Int
    , heldAtOnce : Maybe Int
    }


maxTargetsStateFrom : BotDecisionContext -> MaxTargetsState
maxTargetsStateFrom context =
    { fromSetting = context.eventContext.botSettings.maxTargetCount
    , statedByClient = context.memory.maxTargetsStatedByClient
    , heldAtOnce = context.memory.maxTargetsHeldAtOnce
    }


{-| The same state, on the side of the reading where memory is written.

One reader of `max-targets` per side, so the decision and the memory update
cannot come to hold two opinions about the ceiling -- `updateLockRangeLearning`
asks this too, to tell a probe it made on purpose from a lock that never
completed.

-}
maxTargetsStateBefore : UpdateMemoryContext BotSettings -> BotMemory -> MaxTargetsState
maxTargetsStateBefore context botMemoryBefore =
    { fromSetting = context.botSettings.maxTargetCount
    , statedByClient = botMemoryBefore.maxTargetsStatedByClient
    , heldAtOnce = botMemoryBefore.maxTargetsHeldAtOnce
    }


{-| The clause the client's own statement is recognised by, and the one the
number is sliced out after.

One constant for both, so an extraction can never succeed on a sentence the
matcher would have rejected -- `gateKeyClosingMarker`'s arrangement, for its
reason.

-}
maxTargetsStatedMarker : String
maxTargetsStatedMarker =
    "already managing"


{-| The second clause, and it is not a guard against a rewording the way #31's
pair is -- it carries a distinction the corpus contains.

The client writes a refusal of exactly this shape about **drones**:
`You cannot launch Acolyte I because you are already controlling 5 drones, as
much as you have skill to.` -- 188 live sightings in saxrat's run 5 against 40
of the targeting one. It differs in two words, `controlling` for `managing` and
`much` for `many`, and both matchers here decline it on both. Reading a drone
count as a lock ceiling would cap this ship at five targets on a reading that
said nothing about targeting at all.

-}
maxTargetsSkillMarker : String
maxTargetsSkillMarker =
    "as many as you have skill to"


{-| A second wording for the same refusal, on a hardware- rather than
skill-based cap: `You are already managing N targets, as many as your ship's
electronics are capable of.` Reported live rather than recorded in the corpus
yet -- no run here has ever printed it -- so it is trusted on the operator's
word rather than checked against a recorded sighting. `maxTargetsStatedInGameLog`
accepts either qualifier; neither is required alongside the other, since the
client only ever writes one per refusal.
-}
maxTargetsElectronicsMarker : String
maxTargetsElectronicsMarker =
    "as many as your ship's electronics are capable of"


{-| The maximum the client stated on this reading, if it stated one.

`You are already managing 6 targets, as many as you have skill to.` on
`(notify)` -- the channel `loadRefusalFromGameLog` already reads, so this needed
no new plumbing. 228 distinct entries across the recorded runs of both apps, and
491 across the client's own game logs. The client also writes a second,
hardware-capped wording for the same refusal -- see `maxTargetsElectronicsMarker`.

**The same sentence arrives on the quick-message channel too**, as
`<center>You are already managing 6 targets, as many as you have skill to.`, 40
times on screen in saxrat's run 5 -- which is what settles #123's first open
question, since that is the black popup the operator reported. The game log is
what this reads all the same: those entries are scoped to the reading and drained
by the host, where a quick message is carried forward with an age and would have
to be dated before it could be believed.

The number is sliced out after `maxTargetsStatedMarker` rather than taken as the
first integer in the sentence, so it is the count that clause is about. A
sentence that matches both markers and yields no number is **no evidence** and
never a default -- see `maxTargetsCeiling` for why that direction is the whole
safety of this.

-}
maxTargetsStatedInGameLog : List EveOnline.ParseUserInterface.GameLogEntry -> Maybe Int
maxTargetsStatedInGameLog entries =
    entries
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase maxTargetsStatedMarker entry.text
                    && (stringContainsIgnoringCase maxTargetsSkillMarker entry.text
                            || stringContainsIgnoringCase maxTargetsElectronicsMarker entry.text
                       )
            )
        |> List.filterMap (.text >> maxTargetsInStatement)
        |> List.head


{-| The count the client named, out of a sentence already matched.

Lowercased before slicing only so that the marker matches the way the matcher's
own `stringContainsIgnoringCase` does; nothing lowercased here is stored or
printed, so no normalisation reaches a later reader. A capitalisation the slice
misses therefore yields `Nothing`, which is the safe direction rather than a
guess.

-}
maxTargetsInStatement : String -> Maybe Int
maxTargetsInStatement text =
    case text |> String.toLower |> String.split maxTargetsStatedMarker of
        _ :: afterMarker :: _ ->
            afterMarker |> String.words |> List.head |> Maybe.andThen String.toInt

        _ ->
            Nothing


{-| How many targets the bot will hold locked at once.

`max-targets` is a guess about the ship and a wrong one is costly in both
directions: too low and the bot leaves lock slots empty on every engagement, too
high and it spends readings asking for locks the client will never grant. It
shipped as a hardcoded 4 in both apps, and **the real number on this character is
6** -- so saxrat declined to lock a fifth rat on 2,149 readings across its runs
2 to 5, printing `Enough locked targets.` while two slots sat unused.

The client answers the question itself, in two ways, and neither is inferred
from several conditions holding at once the way a lock-range refusal is:

  - **It states the maximum outright**, on the game log -- see
    `maxTargetsStatedInGameLog`. That number is not a constant even for one
    character: across the client's own logs it reads **5** from 19:16:52 to
    20:46:12 on 31 July 2026 and **6** before and since, which is a targeting
    skill completing. A hardcoded ceiling is therefore not merely wrong once, it
    is wrong in a way that drifts under the bot while nothing notices.
  - **The target bar proves a floor.** A reading whose bar holds N is this ship
    holding N, which needs no attribution at all -- the bar is the ship's own
    state, not a row that could have been somebody else's. It only ever rises.
    This is the half that costs nothing and cannot be wrong, and it is also what
    covers the ship auto-locking past whatever the bot asked for.

With neither, this is exactly the setting, so a session that learns nothing
behaves as it always did. **That direction is the whole safety of it.** Absent
evidence never raises the cap, because a ceiling raised on a guess makes the bot
spend readings asking for locks the client will never grant -- and, unlike a lock
range, nothing would ever teach it back down: the bot only learns from what the
client grants, and a slot that does not exist grants nothing. That is
`loadRefusalFromGameLog`'s register applied to a ceiling.

The stated maximum replaces the setting rather than clamping it, because it is
the client stating a fact about this character where the setting was a guess
about it. The floor wins over both, since a bar demonstrably holding N is not
contradicted by a sentence the client wrote before a skill finished.

-}
maxTargetsCeiling : MaxTargetsState -> Int
maxTargetsCeiling state =
    max
        (state.heldAtOnce |> Maybe.withDefault 0)
        (state.statedByClient |> Maybe.withDefault state.fromSetting)


{-| How many overview rows the lock site takes, which is one more than the
ceiling until the client has stated its maximum.

**Without this the ceiling cannot bootstrap, and #110's two halves were both
inert.** `maxTargetsCeiling` is the larger of the setting and what the client
has granted, and it is that number the lock site takes -- so the bot locks four,
sees four held, and learns four. It cannot discover a fifth slot because it
never asks for one, and `statedByClient` comes from a refusal the client only
writes when a lock is attempted **beyond** the cap. The constraint being learned
is the one that prevents the attempt, which is why #110's corpus is hand-fed:
all 228 recorded statements exist because a person locked the extra targets.

So while `statedByClient` is unknown the lock site takes one row more than it
believes in. A probe that **lands** raises `heldAtOnce`, which raises the
ceiling, so the next probe is one higher -- it ratchets until the client
declines. A probe the client **declines** produces the sentence, which sets
`statedByClient`, and this drops back to the ceiling for the rest of the
session. The refused attempt is not waste; it _is_ the measurement, and there is
one of them per session rather than one per reading.

Taking one _more_ row rather than choosing a different one is what keeps the
probe from displacing a real target: the rows the ceiling covers keep their
order and their places, and the extra one is only ever reached once every one of
them is already locked. `maxTargetsProbe` is what decides whether the row about
to be clicked is that extra one.

-}
maxTargetsRowsToTake : MaxTargetsState -> Int
maxTargetsRowsToTake state =
    case state.statedByClient of
        Just _ ->
            maxTargetsCeiling state

        Nothing ->
            maxTargetsCeiling state + 1


{-| Everything the lock site needs to know about whether to probe now.

`rowsToSpare` is the lockable rows the bot has in hand **and can reach from
here**. Range is part of it because a row beyond the lock range is not something
to probe with: `lockTargetFromOverviewEntry` approaches a row it cannot reach,
and moving the ship is not a price a measurement gets to charge.

-}
type alias MaxTargetsProbeSituation =
    { state : MaxTargetsState
    , targetsHeld : Int
    , rowsToSpare : Int
    }


type MaxTargetsProbe
    = MaxTargetsProbeSettled Int
    | MaxTargetsProbeFillingSlots
    | MaxTargetsProbeOneMore Int
    | MaxTargetsProbeNothingToSpare Int


{-| Whether the next lock the bot asks for is the probe.

Four answers rather than a `Bool`, because three of them are different enough at
the lock site to want their own words in the decision log, and because the one
that decides nothing -- `MaxTargetsProbeFillingSlots`, the bot still working
through the slots it already believes in -- is the common case and must keep the
wording an operator greps for.

**The probing ends on the client's statement and on nothing else.**
`MaxTargetsProbeSettled` is the only answer that stops it, so a client that
never names a number is probed at forever rather than given up on after some
count nobody has evidence for. That direction is deliberate: a count would stop
the learning before the answer arrived, and the cost of being wrong about it is
one lock click on a reading the bot was otherwise going to spend waiting. All
228 recorded refusals name the number, so the evidence there is says the
statement comes.

The bar reaching the ceiling is what makes the _next_ click a probe, and the
ceiling already includes `heldAtOnce` -- so a bar the ship filled by itself,
past whatever the bot asked for, is a ceiling that rose rather than a probe that
is due.

-}
maxTargetsProbe : MaxTargetsProbeSituation -> MaxTargetsProbe
maxTargetsProbe situation =
    case situation.state.statedByClient of
        Just stated ->
            MaxTargetsProbeSettled stated

        Nothing ->
            if situation.targetsHeld < maxTargetsCeiling situation.state then
                MaxTargetsProbeFillingSlots

            else if situation.rowsToSpare < 1 then
                MaxTargetsProbeNothingToSpare (maxTargetsCeiling situation.state + 1)

            else
                MaxTargetsProbeOneMore (maxTargetsCeiling situation.state + 1)


{-| What the lock site says about the attempt it is about to make.

`Lock more targets.` wherever nothing is being probed, so the line an operator
has been grepping for since before any of this is unchanged on the readings it
was already about.

The two probing answers say the slot number they are about, because that is what
tells a run that ratcheted from a run that did not: `Probing for lock slot 5`
followed by `Probing for lock slot 6` is the ceiling climbing, where the same
number reading after reading is a probe nothing is answering.

-}
describeMaxTargetsProbe : MaxTargetsProbe -> String
describeMaxTargetsProbe probe =
    case probe of
        MaxTargetsProbeSettled _ ->
            "Lock more targets."

        MaxTargetsProbeFillingSlots ->
            "Lock more targets."

        MaxTargetsProbeOneMore attemptingToHold ->
            "Probing for lock slot "
                ++ (attemptingToHold |> String.fromInt)
                ++ ": the client has not stated its maximum, so this attempt is one beyond the "
                ++ (attemptingToHold - 1 |> String.fromInt)
                ++ " this session believes in. It either lands, which proves the slot, or the client states the number and the probing stops for the session."

        MaxTargetsProbeNothingToSpare _ ->
            -- Unreachable from a branch that clicks, since what produces this
            -- answer is there being no row to click. Said the ordinary way
            -- rather than invented, so a caller that reaches it anyway reports
            -- the lock it is making instead of a probe it is not.
            "Lock more targets."


{-| What the lock site says on a reading where it has nothing to click at all.

`otherwise` is the app's own wording for that, which the two bots have never
said the same way -- so the shared part is the probe clause and each caller
keeps its own sentence for the ordinary case.

A probe that is due with no row to spare is **not** an attempt and must not be
counted as one: there is nothing to ask, so the reading says so and the ceiling
stays where it is. Without this the branch would read `Everything worth locking
is locked.` on a reading where the bot had also just declined to find out
whether it could hold one more, which are different facts about the same
reading.

-}
describeMaxTargetsNothingToLock : MaxTargetsProbe -> String -> String
describeMaxTargetsNothingToLock probe otherwise =
    case probe of
        MaxTargetsProbeNothingToSpare attemptingToHold ->
            otherwise
                ++ " Nothing to spare for a probe either: no lockable row in range beyond the ones already held, so lock slot "
                ++ (attemptingToHold |> String.fromInt)
                ++ " goes untested on this reading rather than counting as an attempt."

        _ ->
            otherwise


{-| Everything about one reading this rule looks at.

Takes the two fields rather than an `UpdateMemoryContext` so that a case can
build one and fold a whole session through it.

-}
type alias MaxTargetsReading =
    { targetsCount : Int
    , gameLogEntries : List EveOnline.ParseUserInterface.GameLogEntry
    }


maxTargetsReadingFrom : UpdateMemoryContext BotSettings -> MaxTargetsReading
maxTargetsReadingFrom context =
    { targetsCount = context.readingFromGameClient.targets |> List.length
    , gameLogEntries =
        context.readingFromGameClient.gameLogEntriesSinceLastReading
            |> Maybe.withDefault []
    }


{-| What the two learned halves look like after this reading.

Returned as one record rather than written field by field, so the whole of the
rule lives in one place -- `LockRangeLearning`'s reason.

-}
type alias MaxTargetsLearning =
    { statedByClient : Maybe Int
    , heldAtOnce : Maybe Int
    , change : Maybe String
    }


{-| Move the ceiling on what the client has just said or just shown.

The stated maximum takes the **latest** statement rather than the largest or the
smallest, because it is the client's answer about this character now and the
recorded logs show it changing as a skill completes. The floor takes the largest
bar ever seen and never falls: an empty bar is a ship between engagements, not a
ship that has lost slots.

A reading holding no targets is left out of the floor entirely rather than
recorded as `Just 0`, so the status line can tell "the bar has never been seen
carrying anything" from "it carried nothing on this reading" -- absent against
false, in a field an operator reads.

`change` is set on the reading the ceiling moves and on no other, by comparing
the rule's own answer before and against after. That needs no "already reported"
flag: a repeated statement of the same number moves nothing and says nothing.

-}
updateMaxTargetsLearning : MaxTargetsReading -> MaxTargetsState -> MaxTargetsLearning
updateMaxTargetsLearning reading stateBefore =
    let
        statedOnThisReading : Maybe Int
        statedOnThisReading =
            maxTargetsStatedInGameLog reading.gameLogEntries

        statedAfter : Maybe Int
        statedAfter =
            case statedOnThisReading of
                Just stated ->
                    Just stated

                Nothing ->
                    stateBefore.statedByClient

        heldAfter : Maybe Int
        heldAfter =
            if reading.targetsCount <= 0 then
                stateBefore.heldAtOnce

            else
                Just (max reading.targetsCount (stateBefore.heldAtOnce |> Maybe.withDefault 0))

        stateAfter : MaxTargetsState
        stateAfter =
            { fromSetting = stateBefore.fromSetting
            , statedByClient = statedAfter
            , heldAtOnce = heldAfter
            }

        ceilingBefore : Int
        ceilingBefore =
            maxTargetsCeiling stateBefore

        ceilingAfter : Int
        ceilingAfter =
            maxTargetsCeiling stateAfter
    in
    { statedByClient = statedAfter
    , heldAtOnce = heldAfter
    , change =
        if ceilingAfter == ceilingBefore then
            Nothing

        else
            Just
                ("Learned max targets: "
                    ++ (case statedOnThisReading of
                            Just stated ->
                                "the client says it is already managing "
                                    ++ (stated |> String.fromInt)
                                    ++ " targets, as many as this character has skill to"

                            Nothing ->
                                "the target bar is holding "
                                    ++ (reading.targetsCount |> String.fromInt)
                                    ++ " targets at once, more than it ever has"
                       )
                    ++ " -- max-targets moves from "
                    ++ (ceilingBefore |> String.fromInt)
                    ++ " to "
                    ++ (ceilingAfter |> String.fromInt)
                    ++ "."
                )
    }


{-| The ceiling and where each half of it came from, for the status line.

Continuous rather than once-per-change, unlike the decision-log line: a number
the bot adjusts for itself is worth being able to read at any moment, not only on
the reading it moved. Both halves are named separately because they fail
differently -- a run whose `client stated` never leaves `-` is one whose game log
is not reaching the bot, where a `most held at once` stuck below the ceiling is
simply a ship that has not filled its slots yet.

`probing for N` is present exactly while `client stated` is `-`, since the
statement is the only thing that ends the probing. The two are printed side by
side on purpose: a run that says `client stated 6` and still says `probing for`
anything has a rule reading something other than its own state.

-}
describeMaxTargets : MaxTargetsState -> String
describeMaxTargets state =
    "maxtgt "
        ++ (maxTargetsCeiling state |> String.fromInt)
        ++ " (setting "
        ++ (state.fromSetting |> String.fromInt)
        ++ " client "
        ++ (state.statedByClient |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ " held "
        ++ (state.heldAtOnce |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ (case state.statedByClient of
                Just _ ->
                    ""

                Nothing ->
                    " probing " ++ (maxTargetsCeiling state + 1 |> String.fromInt)
           )
        ++ ")."


botMain : InterfaceToHost.BotConfig State
botMain =
    { init = EveOnline.BotFrameworkSeparatingMemory.initState initBotMemory
    , processEvent =
        EveOnline.BotFrameworkSeparatingMemory.processEvent
            { parseBotSettings = parseBotSettings
            , selectGameClientInstance = always EveOnline.BotFramework.selectGameClientInstanceWithTopmostWindow
            , updateMemoryForNewReadingFromGame = updateMemoryForNewReadingFromGame
            , statusTextFromDecisionContext = statusTextFromState
            , decideNextStep = anomalyBotDecisionRoot
            }
    }


initBotMemory : BotMemory
initBotMemory =
    { lastDockedStationNameFromInfoPanel = Nothing
    , shipModules = EveOnline.BotFramework.initShipModulesMemory
    , shipWarpingInLastReading = Nothing
    , hidingFromNeutralPastFirstHop = False
    , readingsSinceWarpEnded = Nothing
    , readingsCount = 0
    , visitedAnomalies = Dict.empty
    , contextMenuLastDepth = 0
    , contextMenuStuckTicks = 0
    , lootWindowOpenTicks = 0
    , routeFirstMarkerRegion = Nothing
    , routeFirstMarkerUnchangedTicks = 0
    , jumpCascadeSystem = Nothing
    , jumpCascadeReopens = 0
    , targetToUnlockRegion = Nothing
    , targetToUnlockUnchangedTicks = 0
    , noProbeScanResultsAndNoRouteLastTimeInSpace = False
    , shipApproachingTicks = 0
    , lootedWreckIds = []
    , gateWithinReachTicks = 0
    , messageBoxStandoff = Nothing
    , messageBoxLastChange = Nothing
    , quickMessage = Nothing
    , hitpoints = { shield = initHitpointsGaugeMemory, armor = initHitpointsGaugeMemory }
    , hitpointsLowWaterMark = { shield = 100, armor = 100 }
    , incomingDamage =
        { samples = []

        -- Assumed absent until a reading says otherwise, so a host that never
        -- carries the channel is reported as unarmed rather than as a quiet
        -- grid.
        , hostCarriesTheChannel = False
        , lastAttacker = Nothing
        , retreating = False
        }
    , shipLoss = Nothing
    , shipUIWithoutModuleButtonsReadings = 0
    , droneRecallUnansweredTicks = 0
    , dronesInSpaceCountLastReading = 0
    , dronesInSpaceTicks = 0
    , huntSystemIndex = 0
    , destinationAskedFor = Nothing
    , fleetBroadcastFollowed = Nothing
    , fleetBroadcastSeen = Nothing
    , fleetBackupBroadcastFollowed = Nothing
    , fleetBackupInSystemStanding = Nothing
    , fleetAtLocationBroadcastFollowed = Nothing
    , fleetAtLocationInSystemStanding = Nothing
    , fleetAtLocationDestinationAsked = Nothing
    , fleetAtLocationBroadcastSeen = Nothing
    , fleetBroadcast = initFleetBroadcastMemory
    , destinationAskReadings = 0
    , routeSettingGivenUp = False
    , escalationStandDownReadings = 0
    , lockAttempt = Nothing

    -- No evidence yet, in both directions -- which is a different fact from
    -- "the client refused at 0 m", and is why these are `Maybe Int` rather
    -- than a defaulted number. With both absent the threshold is exactly the
    -- setting, so a session that learns nothing behaves as it always did.
    , lockRangeStatedMeters = Nothing
    , lockProvenAtMeters = Nothing
    , lockRefusedAtMeters = Nothing
    , lockRangeLastChange = Nothing
    , lockBatch = Nothing
    , lockBatchClicksAsked = 0
    , lockBatchClicksAnswered = 0
    , lockBatchLastChange = Nothing
    , targetsCountLastReading = 0
    , combatStalemate = { readings = 0, ratsInOverview = 0 }
    , outgoingFire =
        { hostCarriesTheChannel = False
        , hits = 0
        , misses = 0
        , readingsEveryShotMissed = 0
        , longestRunEveryShotMissed = 0
        , sessionHits = 0
        , sessionMisses = 0
        }

    -- Assumed absent until a reading says otherwise, so a host that never
    -- carries the channel is reported as unarmed rather than as a session that
    -- killed nothing -- `incomingDamage.hostCarriesTheChannel`'s rule, for its
    -- reason.
    , kills = { hostCarriesTheChannel = False, thisReading = 0, session = 0 }
    , maxTargetsStatedByClient = Nothing
    , maxTargetsHeldAtOnce = Nothing
    , maxTargetsLastChange = Nothing
    , droneLaunchRefusedAbove = Nothing
    , droneLaunchLastChange = Nothing
    , ammoSwap = initAmmoSwapMemory
    }


{-| Which of the two charges a distance calls for.

Two named cases rather than a distance, because the whole of the swap's job is to
decide between the ship's two loaded types and every other reading here is about
that decision rather than about the number behind it.

-}
type AmmoRange
    = ShortRangeAmmo
    | LongRangeAmmo


{-| Where the swap changes its mind, and how far past it a target has to be.

**One source, and that is the deliberate difference from the mission runner.**
There the crossover has three sources -- the setting, the midpoint of two optimal
ranges read off the weapon's tooltip, and the loaded charge's own optimal range
as a bootstrap -- and two of the three depend on a hover this bot does not
perform. Porting them would have brought `weaponOptimalRangeFromHover`, its hover
budgets and the two open issues against them into a bot whose only use for them
would be to derive a number the operator has already been asked for. So
`ammo-swap-range` is required here rather than optional, and there is exactly one
crossover.

The cost is real and is stated rather than discovered later: the tooltip is the
only way a _second_ optimal range is ever observed, so this bot never refines its
crossover and uses the number it is given. That is the mission runner's issue
#128, and it is also what the mission runner already does on every run where the
setting is present -- its run 34 read
`crossover 29000 m (+/-3000, from the ammo-swap-range setting)` with
`tooltip unanswered 0` for the whole run.

-}
type alias AmmoSwapThreshold =
    { crossoverInMeters : Int
    , deadbandInMeters : Int
    }


{-| The three settings the swap needs, once it has them all.

Carried as one value so that nothing below has to re-ask whether the feature is
configured: a branch holding an `AmmoSwapConfig` is a branch the operator has
switched on, and the two charge names and the crossover cannot be present in some
combinations and absent in others.

-}
type alias AmmoSwapConfig =
    { shortRangeAmmoName : String
    , longRangeAmmoName : String
    , threshold : AmmoSwapThreshold
    }


{-| Why the swap switched itself off for the session, as a case rather than a
sentence.

It was a `Maybe String`, and a string is the wrong shape for it now that
something other than the status line has to ask _which_ verdict this is. Run 10
is why: a give-up whose sentence was written once and then read back by nobody
went on claiming for three thousand status lines that the ship's guns were off,
on a ship whose guns the bot itself had recorded coming back on. A case can be
asked; a sentence can only be printed.

`GunsDidNotComeBack` carries the count it was reached at, so the sentence is a
function of the case and the two cannot drift apart.

-}
type AmmoSwapGiveUp
    = ShipCarriesNeitherCharge
    | GunsDidNotComeBack Int


{-| Whether a session-wide give-up is a fact a warp cannot change.

**Only one of the two survives**, and the difference is what the verdict is about.
`ShipCarriesNeitherCharge` is a fact about what is in the ship's hold, which
nothing short of docking alters -- retrying it every pocket buys a menu cascade
per pocket and the same answer each time, forever, on a reading that already
knows. `GunsDidNotComeBack` is a fact about how one attempt went in one fight,
and a warp means a new pocket and a fresh fight.

The cost of that is stated rather than hidden: a swap failing for a _persistent_
reason now retries once per warp instead of once per session. saxrat's run 10
carries about ten warp episodes and eight anomalies visited, so that is tens of
retries over a three-hour session rather than one -- bounded, and visible in the
status line on every reading, where the present behaviour is one line at tick 21
and silence for the rest of the run.

-}
ammoSwapGiveUpSurvivesAWarp : AmmoSwapGiveUp -> Bool
ammoSwapGiveUpSurvivesAWarp giveUp =
    case giveUp of
        ShipCarriesNeitherCharge ->
            True

        GunsDidNotComeBack _ ->
            False


{-| What an operator is told, derived from the case rather than stored beside it.

The disarm sentence is careful about a distinction run 10 shows the old one was
not: it says how many readings the _attempt_ ran, not how many the ship spent
disarmed, because on that run those were 21 and 3. `ammoSwapDisarmEndsTheSession`
is what guarantees the sentence is true when it is printed at all -- the case can
only be reached where the client never took the guns back.

-}
describeAmmoSwapGiveUp : AmmoSwapConfig -> AmmoSwapGiveUp -> String
describeAmmoSwapGiveUp config giveUp =
    case giveUp of
        ShipCarriesNeitherCharge ->
            "the weapon's own menu offers neither '"
                ++ config.shortRangeAmmoName
                ++ "' nor '"
                ++ config.longRangeAmmoName
                ++ "', so the ship is carrying neither and there is nothing to swap between"

        GunsDidNotComeBack readings ->
            "the guns were switched off to load and the client never reported one switched back on across the "
                ++ String.fromInt readings
                ++ " readings of that attempt -- a disarmed ship is worse than the wrong charge, so this will not be attempted again until the next warp"


{-| The give-up as it stands after this reading.

A pure rule over a record so the unlatch can be executed rather than read. The
warp is the boundary, and the two obvious alternatives were weighed against it
rather than assumed:

  - **A new target** is not a boundary at all. Rats die and are replaced every few
    readings, so unlatching there is the same as having no latch -- a swap that
    genuinely cannot finish would re-disarm the ship every few readings for the
    whole session, which is exactly the runaway the latch exists to stop.
  - **A new anomaly** is the tightest reading of "a fresh fight", and it is the
    one this bot cannot always answer. The anomaly's identity comes from
    `getCurrentAnomalyIDAsSeenInProbeScanner`, which is `Nothing` whenever the
    scanner holds nothing on grid -- `visitedAnomalies` already discards those
    readings. A boundary that some readings cannot answer is a boundary that
    silently never arrives.
  - **A warp** needs no read this bot does not already take, and it is a superset
    of the anomaly boundary: every pocket is reached by a warp, so this gives at
    least one retry per pocket and occasionally one more (a warp inside a site, a
    warp to a structure to tether). Each extra one costs a single attempt. Run
    10's counts say the two boundaries are nearly the same in practice -- ten warp
    episodes against eight anomalies -- and only one of them is always readable.

-}
ammoSwapGiveUpAfterReading :
    { before : Maybe AmmoSwapGiveUp
    , reachedThisReading : Maybe AmmoSwapGiveUp
    , justFinishedWarping : Bool
    }
    -> Maybe AmmoSwapGiveUp
ammoSwapGiveUpAfterReading giveUpCase =
    case giveUpCase.before of
        Just before ->
            if giveUpCase.justFinishedWarping && not (ammoSwapGiveUpSurvivesAWarp before) then
                Nothing

            else
                Just before

        Nothing ->
            giveUpCase.reachedThisReading


{-| The one place that says what "the ammo swap is on" means.

`Err` carries the settings that are missing, which is the whole reason this is a
`Result` rather than a `Maybe`: an operator who set both charge names and no
crossover sees a swap reporting itself off, and "off" on its own does not say
whether that is a decision or a typo. One function answering both cannot let the
status line and the gate disagree about which settings are wanted.

**All three, not two.** The mission runner runs on the two charge names and
treats `ammo-swap-range` as an optimisation, because it can derive a crossover
from the weapon's tooltip. Nothing here reads a tooltip, so two out of three
would leave the bot knowing which charge is loaded and having nothing to say
about which one should be -- the mission runner's `optimalRangeGivenUp` state,
reached on the first reading and never left. Refusing to start is the honest form
of that.

Takes the three fields rather than a whole `BotSettings`, so a case can execute
it without building one and so the rule reads exactly the settings it names.

-}
ammoSwapConfigFromSettings :
    { a
        | shortRangeAmmoName : Maybe String
        , longRangeAmmoName : Maybe String
        , ammoSwapRangeMeters : Maybe Int
    }
    -> Result (List String) AmmoSwapConfig
ammoSwapConfigFromSettings settings =
    case ( settings.shortRangeAmmoName, settings.longRangeAmmoName, settings.ammoSwapRangeMeters ) of
        ( Just shortRangeAmmoName, Just longRangeAmmoName, Just crossoverInMeters ) ->
            Ok
                { shortRangeAmmoName = shortRangeAmmoName
                , longRangeAmmoName = longRangeAmmoName
                , threshold =
                    { crossoverInMeters = crossoverInMeters
                    , deadbandInMeters = ammoSwapDeadbandMeters
                    }
                }

        _ ->
            Err
                ([ ( "short-range-ammo", settings.shortRangeAmmoName == Nothing )
                 , ( "long-range-ammo", settings.longRangeAmmoName == Nothing )
                 , ( "ammo-swap-range", settings.ammoSwapRangeMeters == Nothing )
                 ]
                    |> List.filter Tuple.second
                    |> List.map Tuple.first
                )


{-| Everything the ammo swap knows, kept in one field so the rest of `BotMemory`
is untouched.

`chargeLoaded` is the primary reading and it comes from the weapon's own context
menu, which lists the charges the gun can be switched **to** and omits the one
already in it. Verified live on the mission runner's client: a weapon holding
Radio M offered `Multifrequency M [4]` and no Radio M at all. So the charge that
is _absent_ is the charge that is loaded, and that answer needs no tooltip and
none of the sprites this client does not have.

It is also written without a menu read, by `ammoSwapLoadIsTrusted`: a load the
swap dispatched and the client did not refuse puts the charge the swap asked for
in the gun. `chargeLoadedIsAssumed` says which of the two answers is on the
status line, because they are not equally good and an operator has to be able to
tell them apart. A menu read always outranks the assumption -- it is the client's
own word and it costs nothing when it happens to arrive.

`loadCascadeReachedTheMenu` is how the assumption knows a load actually went out.
It is true on the reading a context menu offering the wanted charge is in the
tree with every gun already told to load, which is the reading the cascade clicks
that entry out of it -- and it is read on the **next** reading, never on its own.
Satisfying the verdict on the reading the menu arrives would send the acting path
to `idle` before the click was dispatched, so the swap would be trusting a load
it never issued.

`rangeVerdictTicks` counts consecutive readings the same verdict has gone
_unsatisfied_, and carries two guards at once. Below `ammoSwapDistanceHoldTicks`
it is target churn and nothing is done; above `ammoSwapVerdictGiveUpTicks` the
load has been commanded and the menu still offers the charge, so this attempt is
abandoned. It resets the moment the verdict is satisfied, so a struggle cannot
leave a count behind for the next verdict to inherit.

`gunsSilencedTicks` is the one bound over the whole period the ship's guns are
switched off, counted from the reading the swap first told one to stop and
advanced on every reading until it lets go. It answers a question every waiting
state in this path has to answer -- _and what if this never comes?_ -- once, for
all of them. The mission runner's issue #34 is what it is for: the previous shape
bounded one phase and left the next unbounded, and a ship sat disarmed in a
hostile pocket for 298 readings.

`gunsConfirmedOff` is the client's own word that the switch-off landed, taken
from `isInActiveState` on a gun the swap commanded off, measured going
`True` -> `False` on the reading straight after the click on all four swaps of
the mission runner's run 11. It is used in the two directions a confirmation is
good for and in no other: to stop settling early, and -- once it has been `True`
and the gun reads switched on again -- to record in `switchOffUndoneByClient`
that the switch-off did not hold. It can only make the swap release the guns
sooner, never hold them longer.

`switchOffUndoneByClient` is that second reading, latched. It is a _report_ and
drives no branch, which is the whole of the mission runner's issue #72: the
client re-arms the gun by itself on every swap, so having it abandon the attempt
meant no attempt could reach its load. **Here it has a second cause and the same
answer.** saxrat's fight activates weapons by hotkey
(`activateWeaponModuleButWaitIfActivatedInPreviousStep`) while the swap switches
one off by clicking its button, so the two do not share a settling window and
`decideActionInAnomaly` can press F1 on the very next reading. Nothing about the
_bounds_ changes: the guns firing again is the state in which this attempt has
stopped costing anything, and the two deadlines that end it consult no module at
all. What it does decide, since run 10, is what an expired disarm budget costs
afterwards -- see `ammoSwapDisarmEndsTheSession`.

`verdictAbandoned` is the ordinary per-attempt give-up: the guns go back to
firing whatever is in them and the next change of range tries again. Failing to a
firing gun with the wrong ammo is always better than failing to a silent gun. The
silence deadline abandons the attempt like everything else and, where the ship
really was left disarmed, additionally stops the swap until the next warp.

`givenUp` names which of the two verdicts was reached rather than carrying the
sentence, because one of them is retryable and the other is not; the sentence is
derived from it by `describeAmmoSwapGiveUp`. `givenUpReadingsAgo` exists only so
the latch is _said_ once -- printing its sentence on every reading buries the
readings that carry news, 763 times in the mission runner's run 11 and 3,832
times in saxrat's run 10.

`loadRefusedByClient` holds the client's own sentence when it says it discarded
the load, and it is kept because the entries it came from are not: a reading's
game log lines are gone by the next reading, so a branch that reads them and
records nothing sees a refusal once and then behaves exactly as it did before.

`gunsCommandedThisVerdictAtX` is how the walk across a multi-gun row remembers
where it got to, keyed on each gun's `x` because the row is not a stable index
space. `menuOpenOnGunAtX` is how the bot knows an open context menu is a
weapon's, and which weapon's: nothing in the menu says where it came from, but
the bot opened it and the previous step's effects say where it clicked. It
answers only where the _previous step_ did the right-clicking, so it is `Nothing`
whenever the client took longer than one reading to draw the menu -- which the
mission runner's run 26 shows is most of the time, and is why the read it gates
cannot be what a swap waits for.

-}
type alias AmmoSwapMemory =
    { chargeLoaded : Maybe AmmoRange
    , chargeLoadedIsAssumed : Bool
    , rangeVerdict : Maybe AmmoRange
    , rangeVerdictTicks : Int
    , verdictSatisfied : Bool
    , verdictAbandoned : Bool
    , loadRefusedByClient : Maybe String
    , gunsSilencedTicks : Int
    , gunsConfirmedOff : Bool
    , switchOffUndoneByClient : Bool
    , gunsCommandedThisVerdictAtX : List Int
    , menuOpenOnGunAtX : Maybe Int
    , loadCascadeReachedTheMenu : Bool
    , givenUp : Maybe AmmoSwapGiveUp
    , givenUpReadingsAgo : Int
    }


initAmmoSwapMemory : AmmoSwapMemory
initAmmoSwapMemory =
    { chargeLoaded = Nothing
    , chargeLoadedIsAssumed = False
    , rangeVerdict = Nothing
    , rangeVerdictTicks = 0
    , verdictSatisfied = False
    , verdictAbandoned = False
    , loadRefusedByClient = Nothing
    , gunsSilencedTicks = 0
    , gunsConfirmedOff = False
    , switchOffUndoneByClient = False
    , gunsCommandedThisVerdictAtX = []
    , menuOpenOnGunAtX = Nothing
    , loadCascadeReachedTheMenu = False
    , givenUp = Nothing
    , givenUpReadingsAgo = 0
    }


{-| How many consecutive readings the distance has to say the same thing before
the bot swaps ammo.

The "current target" is not a stable thing to measure: rats die, the next one is
promoted, and the distance jumps from 8 km to 40 km between two readings without
the ship or the fight changing. An anomaly is the worst case for that by
construction -- a pocket of identically named rats dying in sequence -- so acting
on a single reading would let target churn drive the guns.

-}
ammoSwapDistanceHoldTicks : Int
ammoSwapDistanceHoldTicks =
    4


{-| How many readings one verdict gets before the bot abandons that swap and gets
back to shooting.

This bounds **one attempt**, not the feature. That distinction is the correction
the mission runner's issue #27 forced. The number it replaced was fifty readings
and it latched the whole ammo swap off for the session, on the theory that a swap
which never confirms is a swap that cannot work here. What it was actually
measuring was the client discarding every load because the guns were active -- a
transient, fixable condition that it read as a permanent one, and then disabled
the feature over.

So a failed attempt costs one verdict. The guns go back to firing whatever is in
them, and the next time the range calls for a change the bot tries again. Only
the structural impossibilities latch for the session, because only they are
genuinely permanent.

Sized for the whole sequence on a multi-gun row -- silence the guns, then a menu
per gun, several readings each -- with enough headroom for one retry.

-}
ammoSwapVerdictGiveUpTicks : Int
ammoSwapVerdictGiveUpTicks =
    25


{-| How long the swap may leave the ship's guns switched off, counted from the
reading it first told one to stop.

**One deadline over the whole silent period, not one per phase.** That is the
correction the mission runner's issue #34 forced, and the distinction is the
whole point. The previous version bounded _getting the guns quiet_ and left the
phase after it -- waiting for the ramp to finish -- with no counter at all. Run 8
sat in that second phase for 298 readings with the guns off and eleven hostiles
on the overview, because the branch that would have handed the fight back is
downstream of the wedge.

So this counts readings, unconditionally, from the first switch-off command until
the swap lets go. It is advanced by nothing more specific than "the swap is still
holding a verdict it has silenced the guns for", which is what makes it
structural: a phase added inside that window cannot escape it by forgetting to
count, and no reading of the module's own state can stall it -- which matters
because those readings are exactly what turned out to be untrustworthy.

**A weapon that will not go quiet keeps shooting the wrong charge.** Reaching
this deadline always abandons the attempt, and -- where the ship really was still
disarmed -- switches the swap off until the next warp; see
`ammoSwapDisarmEndsTheSession` for the half of that this counter cannot answer
and `ammoSwapVerdictGiveUpTicks` for why every other failure only ever costs one
attempt.

Comfortably longer than the sequence needs and comfortably shorter than
`ammoSwapVerdictGiveUpTicks`, so the dangerous state is always the first to time
out.

-}
ammoSwapSilencedGiveUpTicks : Int
ammoSwapSilencedGiveUpTicks =
    20


{-| Whether an expired disarm budget is evidence of a ship that was left
disarmed.

**It is not, on its own, and saxrat's run 10 is where that stopped being a
theory.** The budget above counts readings from the first switch-off command and
consults nothing the module says, deliberately (#34: a counter that reads the
duty cycle can be stalled by it). What that buys is a bound nothing can stop. What
it does not buy is a statement about the guns, and the give-up beside it was
written as though it did:

    Ammo swap: given up -- the guns were switched off to load and were still not
    back 21 readings later.

On the reading that printed, run 10's own status line had been reading
`a gun has been switched back on 20 of 20 readings in -- the guns are firing` for
seventeen consecutive readings, the client having re-armed the gun at reading 4
of the 21. `GUNS OFF` printed for readings 1 to 3 and never again. The ship was
disarmed for three readings; the sentence claimed twenty-one; and on that
sentence the whole feature switched itself off for a three-hour session, which is
the harshest outcome this design has.

**The distinction already existed one function away.** `describeAmmoSwapState`
declines to print `GUNS OFF` the moment `switchOffUndoneByClient` latches, and
says why in its own comment -- "saying GUNS OFF here would be a lie". The status
line had it right and the verdict did not.

So the _session_ consequence asks the same question the status line asks, and the
attempt bound is untouched: the budget still ends the attempt at exactly the
reading it always did, and only what that costs afterwards changes. This is PR
#151's shape on `lockAttempt` -- a bound counting readings that belong to a
different outcome, discharged on the rule's own terms rather than retuned.

**Reading `switchOffUndoneByClient` here cannot stall anything**, which is what
keeps #34 intact. It is a _latch_, monotone within one attempt and cleared only
where `gunsSilencedTicks` is cleared, so unlike a live module read it cannot
flicker; and it is only ever consulted to make the outcome _milder_, never to
hold the guns longer or to postpone the abandonment by one reading.

Nothing here claims the attempt was going to succeed. It says only that a ship
whose guns the client has demonstrably given back is not the ship this latch was
built to protect.

-}
ammoSwapDisarmEndsTheSession :
    { gunsSilencedTicks : Int
    , switchOffUndoneByClient : Bool
    }
    -> Bool
ammoSwapDisarmEndsTheSession disarmOutcome =
    (ammoSwapSilencedGiveUpTicks < disarmOutcome.gunsSilencedTicks)
        && not disarmOutcome.switchOffUndoneByClient


{-| How many readings to let a switch-off settle before loading anyway.

A count, deliberately, and not a condition on the module. The condition this
replaces was "wait until the ramp stops turning", which is the wait that hung:
`rampRotationMilli` is derived from a widget the client creates and destroys
around a cycle, `isActive` reads `ramp_active`, and `ramp_active` was measured
reading `False` on a module that was switched **on**. A wait on a signal that may
never say what it is being asked is a wait that may never end, however patient.

A count always ends. And it can afford to be short, because the bot no longer has
to be _sure_ the gun is quiet before trying: the client's own refusal says when a
load was thrown away, so an attempt made too early is answered in one reading
rather than guessed at.

**It is an upper bound rather than the whole settle.** `gunsConfirmedOff` ends it
early when the client says the switch-off landed. Only ever earlier: the count
still applies unchanged, so a module that says nothing about itself settles
exactly as it did before.

-}
ammoSwapSilenceSettleTicks : Int
ammoSwapSilenceSettleTicks =
    3


{-| How many entries a weapon's context menu must have before the bot will
believe what is missing from it.

The whole design reads the _absence_ of a charge as proof that it is loaded, so a
menu caught half-built would say every charge is loaded at once. Verified live, a
weapon's menu carries seven entries; the five commands are there whatever is
loadable, so this is comfortably below any real menu and above one that has not
arrived.

-}
ammoSwapMenuEntriesBeforeTrusted : Int
ammoSwapMenuEntriesBeforeTrusted =
    3


{-| How far past the crossover distance the target has to be before the swap
fires, in meters.

A single threshold makes a target sitting near it swap on every reading. Two
thresholds fix that, and because the crossover here is always the setting -- a
fixed number, never one that moves when the swap fires -- any positive deadband
is stable and a plain constant is enough.

That is worth saying because the mission runner needs a second, much wider
deadband for the case where the crossover is the loaded charge's own optimal
range and therefore moves with every swap. That case does not exist here: with
`ammo-swap-range` required there is nothing to bootstrap from and nothing to
bootstrap to.

-}
ammoSwapDeadbandMeters : Int
ammoSwapDeadbandMeters =
    3000


{-| Everything the disarm decision weighs, on the reading it is asked.

Both halves, in one value, so that the rule and the sentence explaining it cannot
be given different inputs -- they take this and nothing else.

`rangeErrorPercent` is the gain and `incomingDamage` the risk;
`runAwayIncomingDamageThreshold` is the scale the risk is measured against,
carried rather than read from settings here so the whole thing can be executed
without a `BotSettings`.

-}
type alias AmmoSwapDisarmCase =
    { runAwayIncomingDamageThreshold : Int
    , rangeErrorPercent : Maybe Int
    , incomingDamage : IncomingDamageMemory
    }


{-| How wrong the loaded charge's range is, as a percentage of the crossover.

The swap's only measurement of what it stands to _gain_, and its documented
weakness carries over from the mission runner unchanged: what actually decides
whether the other charge is better here is whether the guns are landing, which
turns on tracking and angular velocity as much as distance. The client states
that on its outgoing combat lines and nothing here reads them, so what is left is
the geometry.

**Why half the crossover is the line.** On the fit this was measured against, the
two charges' optimal ranges are 21000 m and 67000 m, so the midpoint crossover is
44000 m and each charge's own optimal sits about 52% away from it. A range error
of half the crossover is therefore, almost exactly, "the target is at or past the
range the _other_ charge was designed for" -- the other charge being better not
marginally but by its own design. That is a fact about a fit rather than about
the game, and an operator whose two charges sit closer together is being held to
a ratio measured on a different ship.

`Nothing` where there is no crossover or no target distance, which is a real
answer and not a zero: the swap cannot tell what it would gain, and the budget
below gives it nothing.

-}
ammoSwapRangeErrorPercent : Maybe AmmoSwapThreshold -> Maybe Int -> Maybe Int
ammoSwapRangeErrorPercent threshold distanceInMeters =
    case ( threshold, distanceInMeters ) of
        ( Just crossover, Just distance ) ->
            if crossover.crossoverInMeters <= 0 then
                Nothing

            else
                Just
                    (abs (distance - crossover.crossoverInMeters)
                        * 100
                        // crossover.crossoverInMeters
                    )

        _ ->
            Nothing


{-| The share of the retreat threshold a swap may spend on getting the guns off.

**An eighth, and the eighth is read out of the mission runner's recordings rather
than chosen.** For every reading in its seventeen recorded runs -- 22,452 of them
-- take the 45-second incoming-damage window, then take the worst window reached
within the next `ammoSwapSilencedGiveUpTicks` readings, which is the longest the
swap can hold the guns. The curve is flat and then it is not: up to a window of
**445** the worst that ever followed was 1226 hitpoints, 35% of the retreat
threshold; from 446 it is 1436, and from 469 it is 1683. So 445 is where the
recorded data stops saying "this does not escalate", and an eighth of the retreat
threshold is 437 on that hull, just inside it.

A share rather than a number for `defaultRunAwayIncomingDamageThreshold`'s own
reason: 3500 is a fact about a hull, so anything derived from it has to move with
it rather than being re-measured by hand on the next ship.

**The share is of the _setting_, and that has to stay true.** The mission
runner's retreat scales its own threshold per session from the ship's derived
shield pool, and letting this budget follow that scaling would have moved it too
-- over the twelve recorded runs that derive anything, to somewhere between 420
and 480. 480 is past the 445 above, so the upper end would license disarming on
exactly the windows the recordings show escalating. Nothing here scales anything
yet, so the constraint is presently free; it is written down because the port
that adds the scaling is the one that would sweep this up with it. Every call
site takes `botSettings.runAwayIncomingDamageThreshold`.

**The retreat's own threshold has never been reached in 36 recorded runs, and
that does not make this comparison dead.** It is an eighth, so a window of 437 is
what declines a swap where 3500 is what ends a session, and the recorded windows
routinely sit in that range while a fight is on. What the never-firing retreat
does say is that a swap declined here is declined on a ship that was in no danger
of having to leave -- the direction that keeps the guns firing, which is the one
this whole rule prefers. It also says the shield is the fuse rather than this
number: nothing in the swap reads a hitpoint gauge, deliberately, so a hull whose
shield goes before its damage window climbs is protected by `runAwayIfLowHealth`
and not by anything here.

-}
ammoSwapDisarmDamageBudgetDivisor : Int
ammoSwapDisarmDamageBudgetDivisor =
    8


{-| How wrong the range has to be before the swap may take any risk at all.

See `ammoSwapRangeErrorPercent` for why half the crossover is the line. Below it
the budget is zero, so a marginal verdict still waits for a lull and only a badly
wrong one buys the swap any room.

-}
ammoSwapWorthwhileRangeErrorPercent : Int
ammoSwapWorthwhileRangeErrorPercent =
    50


{-| Hitpoints in the window the swap may disarm through, given what it gains.

Never negative, so a quiet window always passes. Three things reduce it to zero,
and each is a case where the swap cannot tell what it would be buying:

  - **No gain measurable.** No crossover, or no active target to measure a
    distance to -- which is also what a fight ending under a swap looks like, and
    the right answer to "the target I formed this verdict about is gone" is to
    stop holding the guns.
  - **A gain too small to be worth risk.** See
    `ammoSwapWorthwhileRangeErrorPercent`.
  - **No retreat threshold to take a share of.** `run-away-incoming-damage-
    threshold` can be set to `-1` to disable the retreat, and a share of a
    disabled number is not a budget. The swap falls back to needing silence.

-}
ammoSwapDisarmDamageBudget : AmmoSwapDisarmCase -> Int
ammoSwapDisarmDamageBudget disarmCase =
    case disarmCase.rangeErrorPercent of
        Nothing ->
            0

        Just rangeErrorPercent ->
            if rangeErrorPercent < ammoSwapWorthwhileRangeErrorPercent then
                0

            else
                max 0
                    (disarmCase.runAwayIncomingDamageThreshold
                        // ammoSwapDisarmDamageBudgetDivisor
                    )


{-| Whether the swap is allowed to switch the ship's guns off at all right now.

**A swap is an optimisation; the tank is not.** Loading a charge requires taking
the guns offline, which is a fair trade on a quiet grid and a bad one in the
middle of a fight. The mission runner's run 11 began a swap on a ship already
absorbing 1679 hitpoints a window from twelve hostiles at 26% shield, and by the
time `ammoSwapSilencedGiveUpTicks` fired the shield was at zero and the armour
had started going. The bound did what it promised -- and twenty readings under
fire is still most of a tank, because the bound is a backstop and not a policy.

The first answer to that was **zero**: no disarming while the client reports any
incoming damage at all. Run 17 is what it cost -- the swap held a live verdict
wanting the other charge on 271 readings and loaded it not once, 52 of those
declined here by windows of 128, 190, 301, 309 and 371 hitpoints against a
retreat threshold of 3500. In a pocket there is essentially always _some_
incoming damage, so a zero-damage rule fires only between waves, and an anomaly
is a pocket by definition.

So the question is not "is anything shooting" but **is this worth it**: what the
swap gains, against what the client says it would cost.

**An absent channel still declines the swap.** A host that does not carry the
combat log cannot answer the question, and the safe answer to not knowing is the
one that keeps the guns firing -- `Nothing` and `Just 0` being different facts is
this repo's standing rule, and only one of them may be read as "the grid is
quiet". The cost is that the swap does nothing at all on a host without the
channel, which is stated rather than hidden.

**Deferring is not failing.** Nothing is given up and no counter is spent: the
verdict stays live, the guns keep shooting the charge they have, and
`ammoSwapVerdictGiveUpTicks` drops the attempt if the moment never comes.

-}
swapMayDisarmTheGuns : AmmoSwapDisarmCase -> Bool
swapMayDisarmTheGuns disarmCase =
    disarmCase.incomingDamage.hostCarriesTheChannel
        && (incomingDamageInWindow disarmCase.incomingDamage
                <= ammoSwapDisarmDamageBudget disarmCase
           )


{-| The same case, for the status line, which runs where no fight is in scope.

`ensureAmmoSuitsTargetRangeWithGuns` builds its own from the fight's distance,
which is the same number by a shorter path -- both come from the active target
and `activeTargetDistanceInMeters` is what put it there. Separate because the
status line has to answer on readings where the acting path was never reached,
and it must never report a different verdict from the one the branch took.

-}
ammoSwapDisarmCaseForStatus : BotDecisionContext -> AmmoSwapDisarmCase
ammoSwapDisarmCaseForStatus context =
    { runAwayIncomingDamageThreshold =
        context.eventContext.botSettings.runAwayIncomingDamageThreshold
    , rangeErrorPercent =
        ammoSwapRangeErrorPercent
            (ammoSwapConfigFromSettings context.eventContext.botSettings
                |> Result.toMaybe
                |> Maybe.map .threshold
            )
            (activeTargetDistanceInMeters context.readingFromGameClient)
    , incomingDamage = context.memory.incomingDamage
    }


{-| Which half of `swapMayDisarmTheGuns` said no, in the client's own numbers.

Three answers, because they want three different things from an operator. A host
that will never carry the channel means the swap is off for good. A gain too
small to measure or too small to matter means the swap is waiting for a lull. And
a window over the budget is a fight, which passes on its own -- and prints both
numbers, since "301 hitpoints" says nothing without what the swap was willing to
sit through.

-}
describeWhyTheSwapMayNotDisarm : AmmoSwapDisarmCase -> String
describeWhyTheSwapMayNotDisarm disarmCase =
    if not disarmCase.incomingDamage.hostCarriesTheChannel then
        "this host is not carrying the client's combat log, so there is no way to tell whether the ship is under fire, and a guess is not worth the guns."

    else
        let
            budget =
                ammoSwapDisarmDamageBudget disarmCase

            window =
                "the client's combat log reports "
                    ++ (incomingDamageInWindow disarmCase.incomingDamage |> String.fromInt)
                    ++ " hitpoints of incoming damage in the last "
                    ++ (incomingDamageWindowSeconds |> String.fromInt)
                    ++ " s"
        in
        case disarmCase.rangeErrorPercent of
            Nothing ->
                window ++ ", and there is no crossover or no target distance to say what a swap would gain, so it waits for silence."

            Just rangeErrorPercent ->
                if rangeErrorPercent < ammoSwapWorthwhileRangeErrorPercent then
                    window
                        ++ ", and the range is only wrong by "
                        ++ (rangeErrorPercent |> String.fromInt)
                        ++ "% of the crossover -- under the "
                        ++ (ammoSwapWorthwhileRangeErrorPercent |> String.fromInt)
                        ++ "% that buys this swap any room, so it waits for silence."

                else
                    window
                        ++ ", over the "
                        ++ (budget |> String.fromInt)
                        ++ " this swap may disarm through for a range "
                        ++ (rangeErrorPercent |> String.fromInt)
                        ++ "% wrong."


{-| Does the client say this module is switched off?

**`isInActiveState` is not the toggle, and #286 is the measurement.** Over every
log carrying `describeTopRowModuleDictState` -- 34 runs, 55,921 readings, 61,948
module observations -- it is the exact complement of `isDeactivating`, with no
exceptions at all, and the two are separate dictionary keys read by separate
`Dict.get`s. So `Just False` means _this module is in the act of shutting down_,
not that it is off: on the 20,095 observations where `ramp_active` is absent from
the tree entirely -- the ramp widget does not exist, so the module is not running
-- this entry reads `True` on 100% of them.

What that costs **this** predicate is bounded, which is why #286 left it alone.
`Just False` really is the client saying the switch-off landed, so this is a
sound _positive_ signal; what it cannot say is that a switch-off did not land,
because the transient is short -- median two readings, longest seven -- and a
reading that misses it is indistinguishable from a click that never arrived. That is the shape of
`none has yet read switched off`. See CLAUDE.md, "`isInActiveState` is not the
toggle; it is the deactivation transient", before repointing anything here.

**Three answers, not two.** An entry that did not decode is `Nothing`, and a
module that says nothing about itself is not a module saying it is off. Both of
these are therefore `Just`-only, and both answer `False` for `Nothing`, so on a
build that does not carry the entry every caller behaves as though the signal did
not exist.

-}
moduleReadsSwitchedOff : EveOnline.ParseUserInterface.ShipUIModuleButtonState -> Bool
moduleReadsSwitchedOff state =
    state.isInActiveState == Just False


{-| Does the client say this module is switched on? See `moduleReadsSwitchedOff`.
-}
moduleReadsSwitchedOn : EveOnline.ParseUserInterface.ShipUIModuleButtonState -> Bool
moduleReadsSwitchedOn state =
    state.isInActiveState == Just True


{-| Has a switch-off the client confirmed since been undone?

The question only means anything once the client has said the guns went off, so
the previous answer to that is the first argument -- with no confirmation there
is no undoing to detect, whatever the modules read.

**This is a report, not a verdict.** Having it abandon the attempt was the
mission runner's issue #72: across four swaps in two runs the only effects
dispatched between the confirmation and the re-arm were a drone launch, an
overview click and the swap's own right-click, so nothing in the bot pressed the
button, and a rule that abandons on that is a guarantee that no swap can ever
finish.

**What #72 read as the client re-arming the gun is measured false, and this
predicate is where it enters.** #286: over the 35 windows in which this latch has
ever been set, across eight runs and both bots, the client's combat log records
**zero** gun lines and `ramp_active` reads `True` on **zero** of the 191
readings -- against 0.177 gun lines a reading and 37.7% `ramp_active` in the ten
readings before the swap started, and 0.224 and 40.6% in the ten after the
window cleared. 146 _drone_ lines were written inside those same windows, so the
channel was live and the guns contributed none of it. The gun was
switched off, stayed off, and `isInActiveState` came back to `True` because the
deactivation _finished_ (see `moduleReadsSwitchedOff`). That nothing in the bot
pressed the button is the corroboration rather than the mystery.

Nothing is changed on that measurement, deliberately: what this latch does is
make `ammoSwapDisarmEndsTheSession` decline, and repointing it is a behaviour
change on the path that disarms the ship. What it means today is that the guard
which exists because _a disarmed ship is worse than the wrong charge_ is stood
down by a report of guns that did not come back. CLAUDE.md carries the argument
and the numbers.

**Both halves of the test are load-bearing.** Requiring that nothing reads
switched off keeps a reading whose entries simply did not decode from being read
as the guns coming back; requiring that something reads switched on keeps a
second weapon in the row -- one the swap never commanded off, since it commands
exactly one -- from answering for the one it did.

-}
switchOffHasBeenUndone : Bool -> List EveOnline.ParseUserInterface.ShipUIModuleButtonState -> Bool
switchOffHasBeenUndone confirmedOffBefore moduleStates =
    confirmedOffBefore
        && not (moduleStates |> List.any moduleReadsSwitchedOff)
        && (moduleStates |> List.any moduleReadsSwitchedOn)


{-| Whether the client says this weapon's toggle is on.

**Reads `isInActiveState` and not `isActive`, which is a deliberate divergence
from the fight below.** `decideActionInAnomaly` decides whether to press a weapon
hotkey from `.isActive`, which reads `ramp_active` -- the duty cycle, `False` for
a good part of every cycle on a gun that is firing. The mission runner's run 21
is what that costs a swap: its first weapon read `ramp_active` `True` on 69 of
674 module clauses and `False` or absent on the other 605, with `isInActiveState`
`True` on all of them, so on nine readings in ten the swap decided no gun was
firing, skipped the switch-off and opened a menu on a running gun. `GUNS OFF`
appears zero times in that run.

The question this asks is not whether the gun is doing its job but whether its
toggle is on, and **the entry does not answer that either** -- #286 measured it
to be `not isDeactivating`, which is true on 99.7% of every module observation in
the corpus, so this predicate is close to a constant. What that costs is an entry
gate that opens on a ship whose guns are idle, and a switch-off pressed at a
module that may already be off -- and the button is a toggle, so such a press
turns it **on**. That last step is a mechanism rather than an observation: the
fight presses the weapon hotkey on the same readings, and no log attributes a
cycle to one of the two. Not repointed here: see `moduleReadsSwitchedOff` and
CLAUDE.md. What the entry still is not is the duty cycle, which is the whole of
what #76 fixed.

**`Nothing` is not `False`.** An entry that did not decode answers `False` here,
so a build that does not carry it never opens the entry gate and the swap never
starts.

-}
weaponIsSwitchedOn : ShipUIModuleButton -> Bool
weaponIsSwitchedOn moduleButton =
    moduleReadsSwitchedOn moduleButton.stateFromDictEntries


{-| The top (weapon) row as read from a reading rather than from a
`SeeUndockingComplete`.

`updateMemoryForNewReadingFromGame` is the only place that can write memory and
it is handed a reading, not the undocking-complete record the decision path gets
-- so the swap's memory update cannot call `shipUIModulesToActivateOnTarget`.
Both go through `weaponModuleButtonsLeftToRight`, because the swap silences a gun
that the fight will re-arm by its list position (F1-F4), and two orderings would
be two opinions about which physical weapon that is.

-}
weaponModuleButtonsFromReading : ReadingFromGameClient -> List ShipUIModuleButton
weaponModuleButtonsFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map (.moduleButtonsRows >> .top)
        |> Maybe.withDefault []
        |> weaponModuleButtonsLeftToRight


{-| The distance to the target the guns are actually shooting at, in meters, or
nothing at all.

`Nothing` covers three different situations that all mean "do not swap": no
locked target is active, no overview row belongs to it, or the row shows a
distance in AU. That last one is the point. AU distances do not parse, and the
placeholder every other consumer falls back to (999999) reads as merely far,
which is precisely the input that would argue for long-range ammo. Nothing in AU
is in weapons range of anything, so it is excluded here rather than converted.

-}
activeTargetDistanceInMeters : ReadingFromGameClient -> Maybe Int
activeTargetDistanceInMeters readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsActiveTarget
        |> List.head
        |> Maybe.andThen (.objectDistanceInMeters >> Result.toMaybe)


{-| Strip the quantity a charge entry carries in a weapon's context menu.

Observed live: right-clicking a weapon holding Radio M offered
`Multifrequency M [4]`, twice. So an entry's text is the charge name plus a
count, and a setting naming the charge will never equal it.

-}
stripChargeQuantitySuffix : String -> String
stripChargeQuantitySuffix text =
    case text |> String.split "[" of
        beforeBracket :: _ :: _ ->
            String.trim beforeBracket

        _ ->
            String.trim text


{-| Whether a weapon's context menu offers this charge.

Exact match after stripping the quantity, because a substring test is a trap in
both directions -- this bot's own target rule learned that live, where a wreck's
Type is its owner's name with " Wreck" appended. The substring test is kept only
as a fallback for a menu where nothing matched exactly, so a client that formats
the quantity differently degrades rather than failing outright.

Duplicates need no handling beyond using `any`: the same charge is listed twice
in the one menu observed, and two entries for one charge must not read as two
different charges.

-}
weaponMenuOffersCharge : String -> List String -> Bool
weaponMenuOffersCharge chargeName entryTexts =
    let
        wantedNormalised : String
        wantedNormalised =
            chargeName |> String.trim |> String.toLower

        matchesAfterStrippingQuantity : String -> Bool
        matchesAfterStrippingQuantity entryText =
            (entryText |> stripChargeQuantitySuffix |> String.toLower) == wantedNormalised
    in
    if entryTexts |> List.any matchesAfterStrippingQuantity then
        True

    else
        entryTexts |> List.any (stringContainsIgnoringCase chargeName)


{-| Whether the step just executed right-clicked this element -- which for a
module button is the bot opening its context menu, and so the one observable sign
that this gun has been visited.

Cannot be confused with anything else this bot reads out of the effects. The lock
attempt is Ctrl held over a _left_ click (`lockClickLocationFromStepEffects`),
the unlock adds Shift, and the swap's own switch-off is a left click inside a
module button.

-}
previousStepRightClickedElement : List (List EffectOnWindow.EffectOnWindowStruct) -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
previousStepRightClickedElement previousStepsEffects element =
    previousStepsEffects
        |> List.take 1
        |> List.any (\effects -> effectsRightClickElement effects element)


effectsRightClickElement : List EffectOnWindow.EffectOnWindowStruct -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
effectsRightClickElement effects element =
    (effects |> List.any (effectMovesMouseInto element.totalDisplayRegion))
        && (effects |> List.member (EffectOnWindow.ButtonDown MouseButtonRight))


effectMovesMouseInto : EveOnline.ParseUserInterface.DisplayRegion -> EffectOnWindow.EffectOnWindowStruct -> Bool
effectMovesMouseInto region effect =
    case effect of
        EffectOnWindow.MouseMoveTo location ->
            locationIsInDisplayRegion location region

        _ ->
            False


{-| The client's own words for having discarded a load, if it said them since the
last reading.

Matched on the two parts of the sentence that do not vary. The weapon's name sits
between them -- `You cannot load or unload Focused Modulated Medium Energy Beam I
while it is active.` -- so a whole-line match would be per-fitting, and matching
`cannot` alone would catch every other refusal the client makes: across five
recorded runs those were 17 drone-control refusals, 4 "while warping", 2 "while
docking" and 1 module-activation, none of which should touch the guns.

The channel is checked where the host gave one. A `Nothing` channel is a host
that did not say which, not a line without one, so it is judged on its text alone
rather than dropped -- exactly as `shipLossFromGameLog` does.

Note what this does _not_ do. `Nothing` from the game log and `Just []` are
collapsed here, and that is safe only because of the direction of the inference:
finding no refusal is never read as the load having been accepted. Nothing
anywhere may conclude "no refusal arrived, so it worked" _on its own_.

**Anything changing this must read `ammoSwapLoadIsTrusted` first.** The swap does
not re-open a weapon's menu to see whether a load took: it dispatches the load
and records the charge it asked for as the charge in the gun, and this sentence
is what makes that sound. The whole argument is measured -- the mission runner's
run 22 recorded 134 of these refusals when every load was going into a running
gun, and run 26 recorded none against 819 satisfied readings -- so a load that
does not land is not silent.

Take this matcher away, or let it drift from the client's wording, and the
failure is two failures rather than one: a discarded load goes silent again _and_
the swap starts reporting a charge the gun does not have, which is the thing the
removed menu read existed to prevent. Whatever replaces it has to keep saying
"the client threw that load away" on the reading the client says it, or the trust
rule has to go back to being a menu read.

-}
loadRefusalFromGameLog : ReadingFromGameClient -> Maybe String
loadRefusalFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase "cannot load or unload" entry.text
                    && stringContainsIgnoringCase "while it is active" entry.text
            )
        |> List.head
        |> Maybe.map .text


{-| Whether the load the swap dispatched may be taken as having landed.

The swap used to answer this by re-opening a weapon's menu and looking for the
charge to have gone from the list. That read is the client's own word and nothing
here is better than it -- but it is not free, and the mission runner's run 26
measured the price: **55 of the 90 readings that run spent with its guns off**
went on re-opening a menu after the load, and it produced an answer on **one of
its seven swaps**. The other six ran out their attempt still asking. A
verification that costs the majority of the disarmed window and answers one time
in seven is not buying the safety it looks like it is buying.

What replaces it is not "assume it worked". It is **the client is asked, and it
answers when the answer is no**: `loadRefusalFromGameLog` reads
`You cannot load or unload <weapon> while it is active` off the game log, run 22
recorded 134 of them when every load was going into a running gun, and run 26
recorded none against 819 satisfied readings.

The five inputs are each a way this can be wrong, which is why they are named
rather than inlined:

  - `verdictIsTheSameOneAsBefore` -- a load belongs to the verdict that issued
    it. A verdict that has just changed has dispatched nothing yet.
  - `everyGunVisited` -- every weapon on the row has been told to load, so there
    is no gun still waiting for its turn. On a multi-weapon row this is what
    stops the first gun's menu from ending the whole walk.
  - `loadWasDispatched` -- `loadCascadeReachedTheMenu` as it stood on the
    **previous** reading, because that is the reading the cascade clicked the
    charge entry. Read on the same reading it becomes true, the verdict would be
    satisfied before the click went out and the swap would be trusting a load it
    never issued.
  - `loadRefusedByClient` -- the whole safety of this. See
    `loadRefusalFromGameLog` for what happens to the rest of the design if that
    matcher is ever removed or allowed to drift.
  - `menuContradictsTheLoad` -- a menu read on this reading that still offers the
    wanted charge. The assumption always yields to a read, in both directions.

**Being wrong is one swap's worth of wrong, and it is self-correcting.** The next
verdict opens a menu on its way to its own load, and that read overwrites
whatever this recorded. What it must not do is what runs 17 and 18 did, which is
report `loaded charge reads unknown` and never form the next verdict at all.

-}
ammoSwapLoadIsTrusted :
    { verdictIsTheSameOneAsBefore : Bool
    , everyGunVisited : Bool
    , loadWasDispatched : Bool
    , loadRefusedByClient : Maybe String
    , menuContradictsTheLoad : Bool
    }
    -> Bool
ammoSwapLoadIsTrusted trustCase =
    trustCase.verdictIsTheSameOneAsBefore
        && trustCase.everyGunVisited
        && trustCase.loadWasDispatched
        && (trustCase.loadRefusedByClient == Nothing)
        && not trustCase.menuContradictsTheLoad


updateAmmoSwapMemory :
    UpdateMemoryContext BotSettings
    -> IncomingDamageMemory
    -> { justFinishedWarping : Bool }
    -> AmmoSwapMemory
    -> AmmoSwapMemory
updateAmmoSwapMemory context incomingDamage warp memoryBefore =
    case ammoSwapConfigFromSettings context.botSettings of
        Ok config ->
            updateAmmoSwapMemoryWithConfig context incomingDamage warp config memoryBefore

        Err _ ->
            -- The swap is off, so nothing here means anything. Reset rather than
            -- freeze, so that turning it on from the web console mid-session
            -- starts from a clean state instead of one assembled before the
            -- settings existed.
            initAmmoSwapMemory


updateAmmoSwapMemoryWithConfig :
    UpdateMemoryContext BotSettings
    -> IncomingDamageMemory
    -> { justFinishedWarping : Bool }
    -> AmmoSwapConfig
    -> AmmoSwapMemory
    -> AmmoSwapMemory
updateAmmoSwapMemoryWithConfig context incomingDamage warp config memoryBefore =
    let
        guns =
            weaponModuleButtonsFromReading context.readingFromGameClient

        gunJustRightClickedAtX =
            guns
                |> List.filter (.uiNode >> previousStepRightClickedElement context.previousStepsEffects)
                |> List.map (.uiNode >> .totalDisplayRegion >> .x)
                |> List.head

        -- Which gun the open context menu belongs to. The bot opened it, so it
        -- knows: nothing in the menu itself says which module it came from.
        menuOpenOnGunAtX =
            if context.readingFromGameClient.contextMenus |> List.isEmpty then
                Nothing

            else
                case gunJustRightClickedAtX of
                    Just justClicked ->
                        Just justClicked

                    Nothing ->
                        memoryBefore.menuOpenOnGunAtX

        openContextMenuEntryTexts =
            context.readingFromGameClient.contextMenus
                |> List.head
                |> Maybe.map (.entries >> List.map .text)
                |> Maybe.withDefault []

        weaponMenuEntryTexts =
            if menuOpenOnGunAtX == Nothing then
                []

            else
                openContextMenuEntryTexts

        menuWasRead =
            weaponMenuEntryTexts |> List.isEmpty |> not

        shortRangeOffered =
            weaponMenuOffersCharge config.shortRangeAmmoName weaponMenuEntryTexts

        longRangeOffered =
            weaponMenuOffersCharge config.longRangeAmmoName weaponMenuEntryTexts

        -- The menu lists what the gun can be switched *to*, so the charge that
        -- is absent is the charge that is in it. Verified live: a weapon holding
        -- Radio M offered Multifrequency M and not Radio M.
        --
        -- Both offered means some third charge is loaded, and neither means the
        -- ship is carrying neither -- handled separately below, because that one
        -- is worth saying rather than retrying.
        chargeLoaded =
            if not menuWasRead then
                memoryBefore.chargeLoaded

            else if shortRangeOffered && not longRangeOffered then
                Just LongRangeAmmo

            else if longRangeOffered && not shortRangeOffered then
                Just ShortRangeAmmo

            else
                Nothing

        -- A weapon's menu offering neither charge means the ship carries
        -- neither, which is worth saying rather than retrying for fifty
        -- readings. The entry count keeps a half-built menu from latching that
        -- for the session -- see `ammoSwapMenuEntriesBeforeTrusted`.
        neitherChargeCarried =
            menuWasRead
                && (ammoSwapMenuEntriesBeforeTrusted <= List.length weaponMenuEntryTexts)
                && not shortRangeOffered
                && not longRangeOffered

        rangeVerdict =
            case activeTargetDistanceInMeters context.readingFromGameClient of
                Just distance ->
                    if config.threshold.crossoverInMeters + config.threshold.deadbandInMeters < distance then
                        Just LongRangeAmmo

                    else if distance < config.threshold.crossoverInMeters - config.threshold.deadbandInMeters then
                        Just ShortRangeAmmo

                    else
                        Nothing

                Nothing ->
                    Nothing

        verdictIsTheSameOneAsBefore =
            (rangeVerdict /= Nothing) && (rangeVerdict == memoryBefore.rangeVerdict)

        gunsCommandedBefore =
            if verdictIsTheSameOneAsBefore then
                memoryBefore.gunsCommandedThisVerdictAtX

            else
                []

        gunsCommandedThisVerdictAtX =
            case gunJustRightClickedAtX of
                Just justClicked ->
                    if gunsCommandedBefore |> List.member justClicked then
                        gunsCommandedBefore

                    else
                        justClicked :: gunsCommandedBefore

                Nothing ->
                    gunsCommandedBefore

        everyGunVisited =
            (guns |> List.isEmpty |> not)
                && (guns |> List.all (\gun -> gunsCommandedThisVerdictAtX |> List.member gun.uiNode.totalDisplayRegion.x))

        -- A context menu offering the charge this verdict wants is a weapon's
        -- menu: nothing else the client opens lists a charge by name. That is a
        -- wider and steadier test than `menuOpenOnGunAtX`, which only answers
        -- where the right-click was the immediately previous step.
        wantedChargeIsOfferedByAnOpenMenu =
            case rangeVerdict of
                Just ShortRangeAmmo ->
                    weaponMenuOffersCharge config.shortRangeAmmoName openContextMenuEntryTexts

                Just LongRangeAmmo ->
                    weaponMenuOffersCharge config.longRangeAmmoName openContextMenuEntryTexts

                Nothing ->
                    False

        -- The reading the cascade clicks the charge out of the menu it opened:
        -- every gun has been told to load, and the menu is in the tree offering
        -- the charge. Read on the *next* reading and never on this one -- see
        -- `ammoSwapLoadIsTrusted`, where satisfying a verdict here would idle
        -- the acting path before the click was dispatched.
        loadCascadeReachedTheMenu =
            everyGunVisited && wantedChargeIsOfferedByAnOpenMenu

        -- A menu read on this reading that still offers the charge the load was
        -- supposed to put in. The client is saying the gun does not have it, so
        -- there is nothing to trust.
        menuContradictsTheLoad =
            menuWasRead && (chargeLoaded /= rangeVerdict)

        loadIsTrusted =
            ammoSwapLoadIsTrusted
                { verdictIsTheSameOneAsBefore = verdictIsTheSameOneAsBefore
                , everyGunVisited = everyGunVisited
                , loadWasDispatched = memoryBefore.loadCascadeReachedTheMenu
                , loadRefusedByClient = loadRefusedByClient
                , menuContradictsTheLoad = menuContradictsTheLoad
                }

        -- The swap is done when the last gun's own menu says so -- the wanted
        -- charge has gone from the list, which is the client reporting the
        -- effect rather than the bot reporting its intent -- or when the load
        -- has been dispatched and the client has not refused it.
        --
        -- A verdict that arrives with the wanted charge already loaded is
        -- satisfied on the spot, without opening a menu to find that out. This
        -- matters more than it looks: the verdict re-arms every time a target's
        -- distance wanders back out through the deadband, and without this the
        -- bot would re-open every gun's menu, mid-fight, to be told nothing had
        -- changed.
        verdictSatisfied =
            if not verdictIsTheSameOneAsBefore then
                (chargeLoaded /= Nothing) && (chargeLoaded == rangeVerdict)

            else if everyGunVisited && menuWasRead && (chargeLoaded == rangeVerdict) then
                True

            else if loadRefusedByClient /= Nothing then
                -- The client says this attempt's load was thrown away, so
                -- nothing this attempt did may stand as having landed --
                -- including a trust that fired on an earlier reading, if the
                -- refusal took one more reading to arrive than the click did.
                -- Placed below the menu read on purpose: a read that says the
                -- charge is in the gun is the client contradicting its own
                -- earlier sentence, and the read wins.
                False

            else if loadIsTrusted then
                True

            else
                memoryBefore.verdictSatisfied

        -- What the swap will say is in the gun from here on. The read is used
        -- where there is one; otherwise the charge the load asked for.
        chargeLoadedOrAssumed =
            if loadIsTrusted then
                rangeVerdict

            else
                chargeLoaded

        chargeLoadedIsAssumed =
            if chargeLoadedOrAssumed == Nothing then
                False

            else if menuWasRead then
                False

            else if loadIsTrusted then
                True

            else
                memoryBefore.chargeLoadedIsAssumed

        -- Counts only the readings a verdict has gone *unsatisfied*, which is
        -- what the give-up is about. Reset rather than held once satisfied, so
        -- that a long struggle cannot leave a count behind for the next verdict
        -- to inherit and trip over.
        rangeVerdictTicks =
            if rangeVerdict == Nothing then
                0

            else if verdictSatisfied then
                0

            else if not verdictIsTheSameOneAsBefore then
                1

            else if memoryBefore.verdictAbandoned then
                memoryBefore.rangeVerdictTicks

            else
                memoryBefore.rangeVerdictTicks + 1

        -- Whether the swap has told a gun to stop for this verdict. The step's
        -- own effects, not the module's reported state: what the bot asked for
        -- is knowable, where what the client did with it turned out not to be.
        swapJustCommandedAGunOff =
            case context.previousStepsEffects |> List.head of
                Nothing ->
                    False

                Just effects ->
                    guns |> List.any (\gun -> doEffectsClickModuleButton gun effects)

        -- Readings since the guns were first told to stop, for this verdict.
        --
        -- **Nothing about the module can stall this.** The shape it replaces is
        -- worth keeping in view: the old counter reset whenever no gun *read* as
        -- firing, so a weapon flickering between cycles reset it every other
        -- reading and it never reached its bound at all. Run 8's log shows it
        -- stuck at "1 of 8" for all eight readings it was printed, and then the
        -- next phase, which had no counter, ran for 298.
        --
        -- So the only inputs here are whether the swap is still holding the guns
        -- and whether the bot has asked. It advances on every reading in
        -- between, whatever the guns say about themselves.
        --
        -- Note what is deliberately *not* a reset: the verdict changing. A
        -- target drifting back across the deadband flips short to long with the
        -- guns still switched off, and a counter that restarted there would let
        -- a flickering distance hold the ship disarmed indefinitely. Only the
        -- swap letting go clears it.
        gunsSilencedTicks =
            if rangeVerdict == Nothing then
                0

            else if verdictSatisfied then
                0

            else if memoryBefore.verdictAbandoned then
                -- The swap has let go, so the fight owns the guns again and this
                -- is no longer measuring anything. Reset here and nowhere else.
                0

            else if memoryBefore.gunsSilencedTicks > 0 then
                memoryBefore.gunsSilencedTicks + 1

            else if swapJustCommandedAGunOff then
                1

            else
                0

        gunStates =
            guns |> List.map .stateFromDictEntries

        gunsReadSwitchedOff =
            gunStates |> List.any moduleReadsSwitchedOff

        -- Whether the client has confirmed, at any point in this verdict, that
        -- the switch-off the swap commanded actually landed.
        --
        -- Latched rather than re-read, because it is evidence and evidence does
        -- not expire: the reading after it is what says whether the guns stayed
        -- off, and that question can only be asked of a bot that saw them go
        -- off. Cleared exactly where `gunsSilencedTicks` is cleared, so it
        -- belongs to one verdict and cannot be inherited.
        gunsConfirmedOff =
            if rangeVerdict == Nothing then
                False

            else if verdictSatisfied then
                False

            else if memoryBefore.verdictAbandoned then
                False

            else if memoryBefore.gunsConfirmedOff then
                True

            else
                (gunsSilencedTicks > 0) && gunsReadSwitchedOff

        -- The guns were confirmed off and now read switched on again. Latched
        -- for the same reason `gunsConfirmedOff` is: the status line has to be
        -- able to say it on the readings afterwards, and the reading that
        -- observed it is gone by the next one.
        switchOffUndoneByClient =
            if rangeVerdict == Nothing then
                False

            else if verdictSatisfied then
                False

            else if memoryBefore.verdictAbandoned then
                False

            else if memoryBefore.switchOffUndoneByClient then
                True

            else
                switchOffHasBeenUndone memoryBefore.gunsConfirmedOff gunStates

        -- The same trade the acting path weighs before it starts, re-asked on
        -- every reading the swap holds the guns, and read off this reading
        -- rather than the one the verdict was formed on.
        disarmCase =
            { runAwayIncomingDamageThreshold =
                context.botSettings.runAwayIncomingDamageThreshold
            , rangeErrorPercent =
                ammoSwapRangeErrorPercent (Just config.threshold)
                    (activeTargetDistanceInMeters context.readingFromGameClient)
            , incomingDamage = incomingDamage
            }

        -- The trade has stopped being worth it while the swap holds the guns.
        -- The precondition in `ensureAmmoSuitsTargetRangeWithGuns` stops a swap
        -- *starting* on a bad trade; this is the same rule applied to one that
        -- started on a good one, and it abandons rather than waiting out the
        -- deadline. Letting go is what re-arms the guns -- the fight owns
        -- activation and presses the hotkey on the very next reading -- so this
        -- hands the ship back its guns roughly seventeen readings earlier than
        -- the backstop would.
        --
        -- It also covers the fight ending under the swap: a target that has gone
        -- leaves no distance to measure a gain from, the budget falls to zero,
        -- and any fire at all lets go.
        fireArrivedWhileHoldingTheGuns =
            (gunsSilencedTicks > 0) && not (swapMayDisarmTheGuns disarmCase)

        -- The client's own account of having thrown the load away. Recorded
        -- rather than acted on where it is read, because the entries carrying it
        -- are gone by the next reading and this is the only place that can write
        -- memory.
        --
        -- Only while a verdict is live: this wording can only be answering a
        -- load, and the ammo swap is the only thing here that loads, but a
        -- refusal with nothing outstanding belongs to whoever provoked it.
        loadRefusedByClient =
            if rangeVerdict == Nothing then
                Nothing

            else if not verdictIsTheSameOneAsBefore then
                loadRefusalFromGameLog context.readingFromGameClient

            else
                case loadRefusalFromGameLog context.readingFromGameClient of
                    Just refusal ->
                        Just refusal

                    Nothing ->
                        memoryBefore.loadRefusedByClient

        -- Abandoning is per verdict and says nothing about the next one -- see
        -- `ammoSwapVerdictGiveUpTicks`. The guns go back to firing the moment
        -- this is set, because the branch hands the fight on.
        verdictAbandoned =
            if not verdictIsTheSameOneAsBefore then
                False

            else if verdictSatisfied then
                False

            else if loadRefusedByClient /= Nothing then
                -- The client has said the load was discarded, so waiting for the
                -- menu to confirm it is waiting for something that cannot
                -- happen. The same outcome the bounds below reach, arrived at on
                -- the reading the client answered instead of twenty-five
                -- readings later.
                True

            else if fireArrivedWhileHoldingTheGuns then
                -- A swap begun in a lull is not worth finishing under fire, and
                -- abandoning is what hands the guns back.
                True

            else if ammoSwapSilencedGiveUpTicks < gunsSilencedTicks then
                True

            else if ammoSwapVerdictGiveUpTicks < rangeVerdictTicks then
                True

            else
                memoryBefore.verdictAbandoned

        -- Readings since the give-up latched, so it can be *said* once. `1` on
        -- the reading it happened and climbing after -- the ordinary counter
        -- shape rather than a flag, so the property that holds the bounds above
        -- holds this too and it is checked beside them.
        givenUpReadingsAgo =
            if givenUp == Nothing then
                0

            else if memoryBefore.givenUp == Nothing then
                1

            else
                memoryBefore.givenUpReadingsAgo + 1

        givenUp =
            ammoSwapGiveUpAfterReading
                { before = memoryBefore.givenUp
                , reachedThisReading = giveUpReachedThisReading
                , justFinishedWarping = warp.justFinishedWarping
                }

        giveUpReachedThisReading =
            case memoryBefore.givenUp of
                Just _ ->
                    Nothing

                Nothing ->
                    if neitherChargeCarried then
                        Just ShipCarriesNeitherCharge

                    else if
                        ammoSwapDisarmEndsTheSession
                            { gunsSilencedTicks = gunsSilencedTicks
                            , switchOffUndoneByClient = switchOffUndoneByClient
                            }
                    then
                        Just (GunsDidNotComeBack gunsSilencedTicks)

                    else
                        -- Two verdicts rather than the mission runner's three.
                        -- Its third is "no crossover distance", which cannot
                        -- happen here: `ammo-swap-range` is required, so a swap
                        -- that is running has a crossover by construction and a
                        -- swap without one never starts.
                        --
                        -- A load that does not land is *not* here either, and
                        -- neither is an expired disarm budget on a ship the
                        -- client gave its guns back to. Both abandon the one
                        -- verdict and the guns go back to shooting.
                        Nothing
    in
    { chargeLoaded = chargeLoadedOrAssumed
    , chargeLoadedIsAssumed = chargeLoadedIsAssumed
    , rangeVerdict = rangeVerdict
    , rangeVerdictTicks = rangeVerdictTicks
    , verdictSatisfied = verdictSatisfied
    , verdictAbandoned = verdictAbandoned
    , loadRefusedByClient = loadRefusedByClient
    , gunsSilencedTicks = gunsSilencedTicks
    , gunsConfirmedOff = gunsConfirmedOff
    , switchOffUndoneByClient = switchOffUndoneByClient
    , gunsCommandedThisVerdictAtX = gunsCommandedThisVerdictAtX
    , menuOpenOnGunAtX = menuOpenOnGunAtX
    , loadCascadeReachedTheMenu = loadCascadeReachedTheMenu
    , givenUp = givenUp
    , givenUpReadingsAgo = givenUpReadingsAgo
    }


{-| Load the charge that suits how far away the current target is, or get on with
the fight.

Takes the caller's next step rather than returning a `Maybe`, so that every
branch which declines to swap can still say why in the decision log while handing
the fight on -- the shape `returnDronesToBay` was changed to, where a give-up
that only spoke on one exact reading ended up never speaking at all.

Off unless `short-range-ammo`, `long-range-ammo` and `ammo-swap-range` are all
set. Discovering the charge pair by reading the menu is possible now that the
menu is read at all, and is still not done: the menu lists every charge the ship
carries that fits, which is not the same as the two the operator wants
alternated, and picking two of them by guess is a swap nobody asked for.

-}
ensureAmmoSuitsTargetRange : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
ensureAmmoSuitsTargetRange context nextStep =
    let
        ammoSwap =
            context.memory.ammoSwap

        guns =
            weaponModuleButtonsFromReading context.readingFromGameClient
    in
    case ammoSwapConfigFromSettings context.eventContext.botSettings of
        Err _ ->
            nextStep

        Ok config ->
            case ammoSwap.givenUp of
                Just giveUp ->
                    -- The reason in full on the reading it latched, and a line
                    -- an operator can skip while it stands. It repeats about a
                    -- dozen times per reading; the mission runner's run 11
                    -- carries 763 copies of the long form.
                    if ammoSwap.givenUpReadingsAgo <= 1 then
                        describeBranch
                            ("Not swapping ammo any more: " ++ describeAmmoSwapGiveUp config giveUp ++ " -- keep shooting with what is loaded.")
                            nextStep

                    else
                        describeBranch
                            "Not swapping ammo any more (see the status line) -- keep shooting with what is loaded."
                            nextStep

                Nothing ->
                    if
                        (guns |> List.all weaponIsSwitchedOn |> not)
                            && not (ammoSwapIsActingOnAVerdict ammoSwap)
                    then
                        -- Get the guns going first. Opening a weapon's menu takes
                        -- the mouse and a load takes a gun offline -- both are
                        -- things to do to a ship that is already shooting, not to
                        -- one that has not started.
                        --
                        -- This asks whether the guns are switched *on*, through
                        -- `weaponIsSwitchedOn` rather than through the
                        -- `.isActive` the fight below uses. See that function:
                        -- reading the duty cycle here closed this gate on most
                        -- readings of a ship that was shooting.
                        --
                        -- The second clause is what stops this becoming a flap.
                        -- Once the swap is under way it switches the guns off on
                        -- purpose, and bailing out here would hand the fight back
                        -- to the branch that switches them straight on again.
                        nextStep

                    else
                        case ( guns |> List.reverse |> List.head, activeTargetDistanceInMeters context.readingFromGameClient ) of
                            ( Nothing, _ ) ->
                                nextStep

                            ( _, Nothing ) ->
                                -- No active target, or its distance reads in AU
                                -- and does not parse. Either way there is no
                                -- number to decide on, and the placeholder the
                                -- rest of the bot uses for an unparsed distance
                                -- would argue for long-range ammo every time.
                                nextStep

                            ( Just referenceGun, Just distance ) ->
                                ensureAmmoSuitsTargetRangeWithGuns context
                                    { guns = guns
                                    , referenceGun = referenceGun
                                    , distance = distance
                                    , config = config
                                    }
                                    nextStep


{-| Whether the swap has taken charge of the guns for a verdict it is working on.

While this holds, the ammo path keeps control even with every weapon switched
off, because it is the thing that switched them off. It stops holding the moment
the verdict is satisfied or abandoned, and the fight then switches them back on
by its ordinary route -- there is no separate re-activation step, and there
should not be one: the branch that already knows how to start a weapon on a
target is the right owner of that, and a second one would be two controllers for
the same button.

**`clearStrayContextMenu` reads this too**, which is the one piece of wiring this
bot needs and the mission runner does not. See `strayContextMenuIsStray`.

-}
ammoSwapIsActingOnAVerdict : AmmoSwapMemory -> Bool
ammoSwapIsActingOnAVerdict ammoSwap =
    (ammoSwap.rangeVerdict /= Nothing)
        && not ammoSwap.verdictSatisfied
        && not ammoSwap.verdictAbandoned
        && (ammoSwapDistanceHoldTicks <= ammoSwap.rangeVerdictTicks)


ensureAmmoSuitsTargetRangeWithGuns :
    BotDecisionContext
    ->
        { guns : List ShipUIModuleButton
        , referenceGun : ShipUIModuleButton
        , distance : Int
        , config : AmmoSwapConfig
        }
    -> DecisionPathNode
    -> DecisionPathNode
ensureAmmoSuitsTargetRangeWithGuns context fight nextStep =
    let
        ammoSwap =
            context.memory.ammoSwap

        gunWithMenuOpen =
            case ammoSwap.menuOpenOnGunAtX of
                Nothing ->
                    Nothing

                Just menuGunX ->
                    fight.guns
                        |> List.filter (\gun -> gun.uiNode.totalDisplayRegion.x == menuGunX)
                        |> List.head

        openMenuEntryTexts =
            if ammoSwap.menuOpenOnGunAtX == Nothing then
                []

            else
                context.readingFromGameClient.contextMenus
                    |> List.head
                    |> Maybe.map (.entries >> List.map .text)
                    |> Maybe.withDefault []

        gunsStillToVisit =
            fight.guns
                |> List.filter
                    (\gun ->
                        ammoSwap.gunsCommandedThisVerdictAtX
                            |> List.member gun.uiNode.totalDisplayRegion.x
                            |> not
                    )

        -- The gun whose cascade is still running, which is the most recent entry
        -- in the walk. Aiming this at `referenceGun` whatever was just
        -- right-clicked is the same gun only on a one-weapon row -- and this
        -- branch is the load itself rather than a re-read, so pointing it at the
        -- wrong weapon would leave the last one holding the old charge.
        gunCommandedLast =
            ammoSwap.gunsCommandedThisVerdictAtX
                |> List.head
                |> Maybe.andThen
                    (\commandedX ->
                        fight.guns
                            |> List.filter (\gun -> gun.uiNode.totalDisplayRegion.x == commandedX)
                            |> List.head
                    )
                |> Maybe.withDefault fight.referenceGun

        -- Whether the switch-off is still settling: a count with a confirmation
        -- in front of it. The asymmetry is the safety property -- this can only
        -- make the settle **shorter**, and a module that reports nothing settles
        -- on the count exactly as before.
        stillSettling =
            (ammoSwap.gunsSilencedTicks <= ammoSwapSilenceSettleTicks)
                && not ammoSwap.gunsConfirmedOff

        -- What the deadline is counting, said in whichever of its two states the
        -- swap is actually in. It counts the readings this attempt has held the
        -- fight, which is the guns being off only until something takes them
        -- back -- and something does, on every swap. Two branches printing
        -- "Guns off for N" through a window where the guns are firing is the
        -- reading that made the mission runner's run 11 look like a
        -- twenty-reading disarmament.
        describeTheHold =
            if ammoSwap.switchOffUndoneByClient then
                " A gun has been switched back on, so the guns are firing; "
                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                    ++ " of "
                    ++ String.fromInt ammoSwapSilencedGiveUpTicks
                    ++ " readings of this attempt spent."

            else
                " Guns off for "
                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                    ++ " of "
                    ++ String.fromInt ammoSwapSilencedGiveUpTicks
                    ++ " readings."

        -- What the swap would gain and what the client says it would cost, on
        -- this reading. `fight.distance` is the active target's own distance and
        -- is what the verdict was formed from, so gain and verdict cannot
        -- disagree about which target is being talked about.
        disarmCase =
            { runAwayIncomingDamageThreshold =
                context.eventContext.botSettings.runAwayIncomingDamageThreshold
            , rangeErrorPercent =
                ammoSwapRangeErrorPercent (Just fight.config.threshold) (Just fight.distance)
            , incomingDamage = context.memory.incomingDamage
            }

        describeRanges =
            "target "
                ++ String.fromInt fight.distance
                ++ " m away, crossover "
                ++ String.fromInt fight.config.threshold.crossoverInMeters
                ++ " m from the ammo-swap-range setting"

        pressEscape =
            decideActionForCurrentStep
                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                ]
    in
    case ammoSwap.rangeVerdict of
        Nothing ->
            nextStep

        Just verdict ->
            let
                wantedChargeName =
                    case verdict of
                        ShortRangeAmmo ->
                            fight.config.shortRangeAmmoName

                        LongRangeAmmo ->
                            fight.config.longRangeAmmoName

                loadTheWantedCharge gun =
                    useContextMenuCascade
                        ( "weapon module", gun.uiNode )
                        (useMenuEntryWithTextContaining wantedChargeName menuCascadeCompleted)
                        context
            in
            if ammoSwap.verdictSatisfied then
                nextStep

            else if ammoSwap.verdictAbandoned then
                case ammoSwap.loadRefusedByClient of
                    Just refusal ->
                        -- The client's own sentence, quoted rather than
                        -- paraphrased. The whole value of reading its log is
                        -- that an operator sees what EVE said, not what the bot
                        -- made of it.
                        describeBranch
                            ("The client refused the load. It said: \""
                                ++ refusal
                                ++ "\" -- so '"
                                ++ wantedChargeName
                                ++ "' is not going in this time. Back to shooting with what is loaded; the next change of range tries again."
                            )
                            nextStep

                    Nothing ->
                        describeBranch
                            ("Gave up on loading '"
                                ++ wantedChargeName
                                ++ "' for this target ("
                                ++ describeRanges
                                ++ ") -- back to shooting with what is loaded, rather than standing here with the guns off. The next change of range tries again."
                            )
                            nextStep

            else if ammoSwap.rangeVerdictTicks < ammoSwapDistanceHoldTicks then
                describeBranch
                    ("The range wants '"
                        ++ wantedChargeName
                        ++ "' ("
                        ++ describeRanges
                        ++ "), but only for "
                        ++ String.fromInt ammoSwap.rangeVerdictTicks
                        ++ " reading(s) -- a target dying and being replaced looks exactly like this, so wait."
                    )
                    nextStep

            else if (ammoSwap.gunsSilencedTicks < 1) && not (swapMayDisarmTheGuns disarmCase) then
                -- The guns come off only when what the swap gains is worth what
                -- the client says it would cost. See `swapMayDisarmTheGuns` for
                -- the rule and what an absent channel means.
                --
                -- Placed here rather than beside the click, and conditioned on
                -- the swap not having started, for two reasons. Nothing below
                -- this point is free -- the first thing the acting path does is
                -- open a weapon's context menu, and a menu opened under fire
                -- would only be closed again on the next reading. And a swap
                -- already holding the guns is not this branch's business: the
                -- trade going bad then abandons the verdict in the memory
                -- update, which is a stronger response than declining, because
                -- letting go is what hands the guns back.
                describeBranch
                    ("Not switching the guns off to load '"
                        ++ wantedChargeName
                        ++ "' -- "
                        ++ describeWhyTheSwapMayNotDisarm disarmCase
                        ++ " A swap has to be worth the guns: wrong ammo still does damage and a disarmed ship does not."
                    )
                    nextStep

            else
                case gunWithMenuOpen of
                    Just gunWithMenu ->
                        if not (weaponMenuOffersCharge wantedChargeName openMenuEntryTexts) then
                            -- The menu lists what the gun can switch *to*, so a
                            -- charge missing from it is the charge already in the
                            -- gun. That is the confirmation the whole design
                            -- turns on, and it needs no tooltip.
                            describeBranch
                                ("The menu does not offer '"
                                    ++ wantedChargeName
                                    ++ "', which is the client saying this weapon already has it -- close the menu."
                                )
                                pressEscape

                        else if ammoSwap.gunsSilencedTicks < 1 then
                            -- Reading the menu is free while the guns fire;
                            -- loading is not. Close it, so the module button is
                            -- not underneath it when the next branch switches
                            -- the gun off.
                            describeBranch
                                ("The menu offers '"
                                    ++ wantedChargeName
                                    ++ "', but nothing has told this weapon to stop yet and the client refuses a load into a running weapon -- close the menu and stop the gun first."
                                )
                                pressEscape

                        else if stillSettling then
                            describeBranch
                                ("Told this weapon to stop "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilenceSettleTicks
                                    ++ " readings ago and it has not yet read switched off -- let the cycle end before loading '"
                                    ++ wantedChargeName
                                    ++ "'."
                                )
                                nextStep

                        else
                            -- Loaded without checking whether the gun reads
                            -- quiet, on purpose. The client answers that
                            -- question itself: a load into a running module
                            -- comes back as a refusal in the game log, and one
                            -- wasted reading is a better price than a wait that
                            -- cannot end.
                            describeBranch
                                ("The menu offers '"
                                    ++ wantedChargeName
                                    ++ "', so this weapon is not carrying it, and it has had "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " reading(s) to stop -- load it. "
                                    ++ describeRanges
                                    ++ "."
                                )
                                (loadTheWantedCharge gunWithMenu)

                    Nothing ->
                        if ammoSwap.gunsSilencedTicks < 1 then
                            case fight.guns |> List.filter weaponIsSwitchedOn |> List.head of
                                Just gunStillFiring ->
                                    -- Switch it off, once. The button is a
                                    -- toggle, so the settling window in
                                    -- `clickModuleButtonButWaitIfClickedInPreviousStep`
                                    -- is what keeps a second press from turning
                                    -- it straight back on -- and from here on
                                    -- `gunsSilencedTicks` is non-zero, so this
                                    -- branch is not revisited for this verdict
                                    -- however the module reports itself.
                                    --
                                    -- The click rather than the weapon hotkey
                                    -- the fight presses, because
                                    -- `doEffectsClickModuleButton` is what
                                    -- `swapJustCommandedAGunOff` reads and it
                                    -- attributes the press to a gun by region. A
                                    -- hotkey covers only the first four weapons
                                    -- and identifies one by list position. The
                                    -- cost is that the fight's own settling
                                    -- window does not see this press, so it may
                                    -- re-arm the gun on the next reading --
                                    -- which no bound depends on, and which
                                    -- `switchOffUndoneByClient` reports.
                                    --
                                    -- Everything after this point is inside the
                                    -- window `ammoSwapSilencedGiveUpTicks`
                                    -- bounds.
                                    describeBranch
                                        ("Stop this weapon before loading '"
                                            ++ wantedChargeName
                                            ++ "' -- the client refuses to load a charge into a module that is running, and says so only in its game log."
                                        )
                                        (clickModuleButtonButWaitIfClickedInPreviousStep context gunStillFiring)

                                Nothing ->
                                    -- No gun says it is switched on, so there is
                                    -- nothing to switch off and the load can be
                                    -- tried directly. If that reading was wrong
                                    -- -- an entry that did not decode reads this
                                    -- way -- the refusal says so.
                                    describeBranch
                                        ("No weapon reads as switched on, so open one's menu to see whether it already carries '"
                                            ++ wantedChargeName
                                            ++ "'."
                                        )
                                        (loadTheWantedCharge
                                            (gunsStillToVisit |> List.head |> Maybe.withDefault fight.referenceGun)
                                        )

                        else if stillSettling then
                            -- Handing the fight on here is what turns the guns
                            -- straight back on: the branch below owns
                            -- activation, sees an inactive weapon on a locked
                            -- target, and presses the hotkey. That is the right
                            -- owner and the right behaviour -- what was wrong is
                            -- spending readings here at all, and
                            -- `gunsConfirmedOff` is what cuts this to the one or
                            -- two readings the client actually needs.
                            describeBranch
                                ("Told the guns to stop "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilenceSettleTicks
                                    ++ " readings ago and none has yet read switched off -- let the cycle end before loading '"
                                    ++ wantedChargeName
                                    ++ "'."
                                )
                                nextStep

                        else
                            case gunsStillToVisit |> List.head of
                                Just gunToVisit ->
                                    describeBranch
                                        ("Open this weapon's menu to see whether it already carries '"
                                            ++ wantedChargeName
                                            ++ "'. "
                                            ++ String.fromInt (List.length gunsStillToVisit)
                                            ++ " of "
                                            ++ String.fromInt (List.length fight.guns)
                                            ++ " weapon(s) still to check."
                                            ++ describeTheHold
                                        )
                                        (loadTheWantedCharge gunToVisit)

                                Nothing ->
                                    -- The cascade opened on the last gun has not
                                    -- put its menu in the tree yet. This branch
                                    -- keeps driving it, and that is all it does:
                                    -- it *is* the load, not a check of one. The
                                    -- re-read it replaces was 55 of the 90
                                    -- readings the mission runner's run 26 spent
                                    -- with its guns off and answered on one of
                                    -- its seven swaps.
                                    describeBranch
                                        ("Every weapon has been told to load '"
                                            ++ wantedChargeName
                                            ++ "' -- waiting for the last one's menu so the charge can be clicked out of it. Once it goes the load is taken as landed, because the client says so when it is not."
                                            ++ describeTheHold
                                        )
                                        (loadTheWantedCharge gunCommandedLast)


{-| The ammo swap's whole state on one line, so an operator can watch the charge
the client reports rather than trust the decision log's claim that it swapped.

The `Err` case names the settings that are missing rather than saying only "off",
because an operator who set two of the three and got silence has no way to tell a
decision from a typo. See `ammoSwapConfigFromSettings`.

-}
describeAmmoSwapState : BotDecisionContext -> String
describeAmmoSwapState context =
    let
        ammoSwap =
            context.memory.ammoSwap

        describeAmmoRange ammoRange =
            case ammoRange of
                Nothing ->
                    "unknown"

                Just ShortRangeAmmo ->
                    "short-range"

                Just LongRangeAmmo ->
                    "long-range"
    in
    case ammoSwapConfigFromSettings context.eventContext.botSettings of
        Err [] ->
            -- Unreachable while `ammoSwapConfigFromSettings` is the only thing
            -- that builds an `Err`, since it names every absent setting. Said
            -- rather than defaulted, so a rule that grew a second `Err` shows up
            -- here instead of reading as a swap that is configured.
            "Ammo swap: off, and this bot cannot say which setting is missing."

        Err missing ->
            "Ammo swap: off (needs " ++ (missing |> String.join ", ") ++ ")."

        Ok config ->
            case ammoSwap.givenUp of
                Just giveUp ->
                    -- Said in full on the reading it happened, and as a flag
                    -- while it stands.
                    if ammoSwap.givenUpReadingsAgo <= 1 then
                        "Ammo swap: given up -- " ++ describeAmmoSwapGiveUp config giveUp ++ "."

                    else
                        -- The flag says which of the two this is, because they
                        -- now end differently: run 10 printed "off for this
                        -- session" 3,832 times about a verdict that a warp
                        -- would have cleared, and an operator reading that had
                        -- no way to know whether to expect the swap back.
                        "Ammo swap: "
                            ++ (if ammoSwapGiveUpSurvivesAWarp giveUp then
                                    "off for this session"

                                else
                                    "off until the next warp"
                               )
                            ++ " (given up "
                            ++ String.fromInt ammoSwap.givenUpReadingsAgo
                            ++ " readings ago)."

                Nothing ->
                    "Ammo swap: loaded charge reads "
                        ++ describeAmmoRange ammoSwap.chargeLoaded
                        ++ (if ammoSwap.chargeLoadedIsAssumed then
                                -- The two answers are not equally good and an
                                -- operator has to be able to tell which one is
                                -- on the line: one is the client's own menu
                                -- omitting the charge in the gun, the other is
                                -- the swap taking its own load at its word
                                -- because the client did not refuse it.
                                " (assumed from the load, not read back)"

                            else
                                ""
                           )
                        ++ ", crossover "
                        ++ String.fromInt config.threshold.crossoverInMeters
                        ++ " m (+/-"
                        ++ String.fromInt config.threshold.deadbandInMeters
                        ++ ", from the ammo-swap-range setting), target distance "
                        ++ (activeTargetDistanceInMeters context.readingFromGameClient
                                |> Maybe.map String.fromInt
                                |> Maybe.withDefault "unknown"
                           )
                        ++ " m, wants "
                        ++ describeAmmoRange ammoSwap.rangeVerdict
                        ++ " for "
                        ++ String.fromInt ammoSwap.rangeVerdictTicks
                        ++ " reading(s)"
                        ++ (if ammoSwap.verdictSatisfied then
                                " (satisfied)"

                            else if ammoSwap.verdictAbandoned then
                                case ammoSwap.loadRefusedByClient of
                                    Just refusal ->
                                        " (the client refused it: \"" ++ refusal ++ "\")"

                                    Nothing ->
                                        " (gave up on this one, will try again on the next change of range)"

                            else if ammoSwap.switchOffUndoneByClient then
                                -- Saying `GUNS OFF` here would be a lie, and it
                                -- was the lie the mission runner's run 11 told
                                -- for eighteen readings: the counter is the
                                -- bound on the attempt, not a statement about
                                -- the guns, and once a gun has been re-armed the
                                -- two have come apart. The bound still shows,
                                -- because it is still what ends this.
                                " (a gun has been switched back on "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilencedGiveUpTicks
                                    ++ " readings in -- the guns are firing, and this attempt is going on to its load anyway)"

                            else if 0 < ammoSwap.gunsSilencedTicks then
                                -- The number an operator should be watching: how
                                -- long this ship has had its guns switched off.
                                -- The client's own word about the switch-off
                                -- rides beside it.
                                " (GUNS OFF for "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilencedGiveUpTicks
                                    ++ " readings, the client "
                                    ++ (if ammoSwap.gunsConfirmedOff then
                                            "confirmed the switch-off"

                                        else
                                            "has not confirmed the switch-off"
                                       )
                                    ++ ")"

                            else if (ammoSwap.rangeVerdict /= Nothing) && not (swapMayDisarmTheGuns (ammoSwapDisarmCaseForStatus context)) then
                                -- Why nothing is happening to a live verdict. A
                                -- branch that declines has to say so on every
                                -- reading it declines, and the decision line
                                -- only appears once the hold ticks are past.
                                " (not disarming: "
                                    ++ describeWhyTheSwapMayNotDisarm (ammoSwapDisarmCaseForStatus context)
                                    ++ ")"

                            else
                                ""
                           )
                        ++ "."


{-| The name of whatever EVE currently calls the active target.

One declaration because two now want it -- the header row and the row that
names the target's condition below it -- and two copies of "which overview row
is the active one" is the drift this file has paid for elsewhere. It is the
_name_ that is shared; the condition beside it is `describeTargetHitpoints`,
which is deliberately unshared between this bot and the mission runner and is
called by both readers rather than reimplemented by either.

-}
activeTargetNameFromReading : ReadingFromGameClient -> Maybe String
activeTargetNameFromReading readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsActiveTarget
        |> List.head
        |> Maybe.andThen .objectName


{-| Where the ship is, in the one field that can answer it.

Three states this reading can actually distinguish, and no fourth invented:
warping, standing in an anomaly the probe scanner names, and neither. A reading
with no ship UI is in station, which is a different answer again and is worth
one word since every counter below behaves differently there.

`DEADSPACE` is deliberately **not** a fourth case. A deadspace pocket entered
through an acceleration gate has no scan-result row of its own, so the scanner
names nothing and this answers `-` -- which is the truthful "the client is not
telling me where I am" rather than a guess dressed as a reading.

-}
describeWhereTheShipIs : ReadingFromGameClient -> String
describeWhereTheShipIs readingFromGameClient =
    if readingFromGameClient.shipUI == Nothing then
        "DOCKED"

    else if shipWarpingFromReading readingFromGameClient == Just True then
        "IN WARP"

    else
        case getCurrentAnomalyIdentityAsSeenInProbeScanner readingFromGameClient of
            Just anomaly ->
                describeAnomalyIdentityForHeader anomaly

            Nothing ->
                "-"


{-| The whole run on one line, and the only line the log carries every time.

The status text is recomputed for every decision, and the host prints this line
under every one of them while printing each line below it only when that line
moved. So what an operator reads thousands of times a run is whatever this
function puts first, and everything else is read when it changes. Measured over
saxrat run 52 -- 27.7 MB, 5,102 readings, 16,742 decisions -- **79.8% of the log
was status text**, of which this line was 2.6% and the twelve diagnostic lines
under it were the rest. So the question this answers is not "what else could be
printed" but "what is worth printing on every one of sixteen thousand
decisions".

The six fields the operator asked for, in their order and their words:

    Amarr AIC-176 Centii Devourer [10/100/100] 5 rats 273 kills 12 anoms | ship 58/100 | dmg 604/3500

and two more, because run 48 sat in one anomaly for 3,883 seconds and the first
question anybody asked was whether the ship was in trouble. **The answer that
settled it was a shield at 0%, an armour that was not moving, and incoming
damage far below the retreat threshold** -- three numbers that were in the log
and took a replay to find, because they were spread across three of the
diagnostic lines below.

`ship` is the **believed** pair, not the live gauge, so the header says what the
guards are going by: `plausibleHitpointsPercent` rejects the impossible readings
and `believed` withholds a fall a second reading has not confirmed, and this
hull's gauge produced values from -213% to 40,028,800% on one recorded run. A
gauge that has not answered yet reads `?`, never a number.

`dmg` is `describeIncomingDamage`'s own two numbers rather than a second copy of
them, for the reason `describeTargetHitpoints` is reused below rather than
reimplemented: two renderings of one measurement drift, and this file has paid
for that twice.

**The target's condition is `describeTargetHitpoints`, called rather than
copied.** PR #244 pinned that clause as deliberately unshared between this bot
and the mission runner -- saxrat's is the abbreviated `[10/100/100]` and the
mission runner's the spelled-out one -- and a header that spelled the triple out
again here would be a third rendering for two apps to drift between.

-}
describeStatusHeader : BotDecisionContext -> String
describeStatusHeader context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        gauge =
            Maybe.map String.fromInt >> Maybe.withDefault "?"

        target =
            activeTargetNameFromReading readingFromGameClient
                |> Maybe.map
                    (\name ->
                        name
                            ++ " "
                            ++ describeTargetHitpoints
                                (activeTargetHitpointsPercent readingFromGameClient)
                    )
                |> Maybe.withDefault "no target"

        incomingDamage =
            context.memory.incomingDamage
    in
    String.join " "
        [ currentSolarSystemNameFromReading readingFromGameClient
            |> Maybe.withDefault "?"
        , describeWhereTheShipIs readingFromGameClient
        , target
        , (readingFromGameClient |> getNamesOfRatsInOverview |> List.length |> String.fromInt)
            ++ " rats"
        , describeKillCount context.memory.kills
        , (context.memory.visitedAnomalies |> Dict.size |> String.fromInt) ++ " anoms"
        , "| ship "
            ++ gauge context.memory.hitpoints.shield.believed
            ++ "/"
            ++ gauge context.memory.hitpoints.armor.believed
        , "| "
            ++ (if not incomingDamage.hostCarriesTheChannel then
                    "dmg NO COMBAT LOG"

                else
                    "dmg "
                        ++ (incomingDamageInWindow incomingDamage |> String.fromInt)
                        ++ "/"
                        ++ (if context.eventContext.botSettings.runAwayIncomingDamageThreshold < 0 then
                                "off"

                            else
                                String.fromInt
                                    context.eventContext.botSettings.runAwayIncomingDamageThreshold
                           )
               )
        ]


{-| Everything an operator reads, with the header first and the rest below it.

**The first row is the header and the rest are diagnostics, and the order is
what decides which a clause is.** The host prints the first line of this text
beside the decision marker and the rest below it, and since #284 it prints that
rest only when it has changed since the last decision it printed -- so a clause
in the first row is seen on every one of a run's sixteen thousand decisions and
a clause below it is seen on the readings it moves. Nothing here is deleted or
made conditional; what changed is that the repetition ended at the layer that
was creating it.

Two structural constraints, both of which cases hold and one of which this
change nearly broke. `describeQuickMessage` is a row of the outer list rather
than part of `describeCurrentReading`, because that binding is only built for a
reading with a ship UI and a docked reading is exactly where an unread client
notice sits. And **no comment may sit between this function's `in` and its
list**: `test_quick_message_logged` locates the outer list by splitting the
collapsed source on `in [`, so a comment there does not fail that case -- it
makes it pass having read the whole function instead, which is worse.

-}
statusTextFromState : BotDecisionContext -> String
statusTextFromState context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        describePerformance =
            "Visited anomalies: " ++ (context.memory.visitedAnomalies |> Dict.size |> String.fromInt) ++ "."

        -- Surfaces the tick counters BotMemory already tracks (see
        -- updateMemoryForNewReadingFromGame) but that were previously
        -- invisible outside the source -- added so a slow menu-cascade
        -- or a stuck "waiting for element to settle" branch (route
        -- marker, target-to-unlock icon, loot window) shows up directly
        -- in the per-tick log instead of only being inferable from how
        -- many consecutive ticks repeat the same decision-path text.
        describeMenuAndSettlingCounters =
            "menus "
                ++ (readingFromGameClient.contextMenus |> List.length |> String.fromInt)
                ++ "/L"
                ++ (context.contextMenuCascadeLevel |> String.fromInt)
                ++ " stuck "
                ++ (context.memory.contextMenuStuckTicks |> String.fromInt)
                ++ " | route "
                ++ (context.memory.routeFirstMarkerUnchangedTicks |> String.fromInt)
                ++ " | unlock "
                ++ (context.memory.targetToUnlockUnchangedTicks |> String.fromInt)
                ++ " | "
                ++ describeLootWindowStandoff
                    { readingsOpen = context.memory.lootWindowOpenTicks
                    , lootWindowOpen =
                        readingFromGameClient
                            |> wreckLootWindowsFromReadingFromGameClient
                            |> List.isEmpty
                            |> not
                    }
                ++ " | dead-end "
                ++ (if context.memory.noProbeScanResultsAndNoRouteLastTimeInSpace then
                        "yes"

                    else
                        "no"
                   )
                ++ " | approach "
                ++ (context.memory.shipApproachingTicks |> String.fromInt)
                -- Beside the approach counter, because the first thing this
                -- count reaches for is an approach.
                ++ " | "
                ++ describeCombatStalemate context.memory.combatStalemate
                ++ " | "
                ++ describeGateActivationAsk
                    { asked = askingAnAccelerationGateToOpen readingFromGameClient
                    , gateWithinReach = accelerationGateIsWithinReach readingFromGameClient
                    , askedReadings = context.memory.gateWithinReachTicks
                    }
                -- Appended rather than folded into the record above, so a gate
                -- ignored for its distance and one asked and not opened stay
                -- separate sentences: the first is a gate this bot declines to
                -- fly at, the second a gate it has been flying at all along.
                -- The gate spoken about is `nearestAccelerationGateOnOverview`,
                -- which is the one the branch itself decided about.
                ++ (readingFromGameClient
                        |> nearestAccelerationGateOnOverview
                        |> Maybe.map (.objectDistanceInMeters >> distantGateVerdict >> describeDistantGate)
                        |> Maybe.withDefault ""
                   )
                ++ " | "
                ++ describeFleetCommander context
                ++ " | wrecks "
                ++ (context.memory.lootedWreckIds |> List.length |> String.fromInt)
                ++ " | "
                ++ describeModulesToActivateAlways readingFromGameClient
                ++ " | "
                ++ describeTopRowModuleDictState readingFromGameClient
                ++ "\n"
                ++ describeIncomingDamage context
                -- Beside the incoming half, because they are the two directions
                -- of one channel and a reading that carries neither is a host
                -- with no game log rather than a quiet grid.
                ++ " "
                ++ describeOutgoingFire context.memory.outgoingFire
                ++ " "
                -- Beside the damage window rather than beside the gauges,
                -- because what it says is that the window is the only guard
                -- left. The marks themselves are already printed further down.
                ++ describeRetreatCover
                    { shieldThresholdPercent = context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent
                    , armorThresholdPercent = context.eventContext.botSettings.runAwayArmorHitpointsThresholdPercent
                    }
                ++ " "
                ++ describeDroneRecall context
                ++ " "
                ++ describeDroneLaunchCeiling (droneLaunchStateFrom context)
                ++ " "
                ++ describeHuntCircuit context
                ++ " "
                ++ describeLockRange (lockRangeStateFrom context)
                ++ " "
                ++ describeLockBatch (lockBatchStateFrom context)
                ++ " "
                ++ describeMaxTargets (maxTargetsStateFrom context)
                ++ " "
                ++ describeAmmoSwapState context
                ++ (case context.memory.shipLoss of
                        Nothing ->
                            ""

                        Just shipLoss ->
                            " SHIP LOST: "
                                ++ shipLoss.reason
                                ++ " ("
                                ++ String.fromInt shipLoss.readingsSince
                                ++ " readings since, giving up at "
                                ++ String.fromInt podRecoveryGiveUpReadings
                                ++ ")."
                   )
                -- #138's counter and #164's naming of the box, rendered by
                -- `describeMessageBoxStandoff` rather than here so a case can
                -- execute what an operator reads.
                ++ describeMessageBoxStandoff context.memory.messageBoxStandoff
                ++ (let
                        withheld =
                            context.memory.hitpoints.shield.readingsWithheld
                                + context.memory.hitpoints.armor.readingsWithheld
                    in
                    if withheld < 1 then
                        ""

                    else
                        -- Evidence that the gauge has started lying, and how
                        -- often. A couple over a run is the gauge behaving as
                        -- recorded; a count climbing every few readings is a
                        -- different problem.
                        " Readings withheld from the retreat this session: "
                            ++ String.fromInt withheld
                            ++ " (retreat is going by shield "
                            ++ String.fromInt context.memory.hitpointsLowWaterMark.shield
                            ++ "%, armor "
                            ++ String.fromInt context.memory.hitpointsLowWaterMark.armor
                            ++ "%)."
                   )

        describeCurrentReading =
            case readingFromGameClient.shipUI of
                Nothing ->
                    -- Which of the two it is, rather than the guess the split
                    -- itself stopped making (#304). A header that says "docked"
                    -- on a reading the bot has declined to draw that conclusion
                    -- from is one the operator has to disbelieve.
                    [ case readingFromGameClient.stationWindow of
                        Just _ ->
                            "I do not see the ship UI and I do see the station window. Docked."

                        Nothing ->
                            "I see neither the ship UI nor the station window, so this reading does not say where the ship is."
                    ]

                Just shipUI ->
                    let
                        describeShip =
                            "Shield: "
                                ++ (shipUI.hitpointsPercent.shield |> String.fromInt)
                                ++ "% "
                                ++ " Armor: "
                                ++ (shipUI.hitpointsPercent.armor |> String.fromInt)
                                ++ "%"

                        describeDrones =
                            case readingFromGameClient.dronesWindow of
                                Nothing ->
                                    "No drones"

                                Just dronesWindow ->
                                    "I see the drones window: In bay: "
                                        ++ (dronesWindow.droneGroupInBay
                                                |> Maybe.andThen (.header >> .quantityFromTitle)
                                                |> Maybe.map (.current >> String.fromInt)
                                                |> Maybe.withDefault "Unknown"
                                           )
                                        ++ ", in space: "
                                        ++ (dronesWindow.droneGroupInSpace
                                                |> Maybe.andThen (.header >> .quantityFromTitle)
                                                |> Maybe.map (.current >> String.fromInt)
                                                |> Maybe.withDefault "Unknown"
                                           )
                                        ++ "."

                        namesOfOtherPilotsInOverview =
                            getNamesOfOtherPilotsInOverview readingFromGameClient

                        namesOfRatsInOverview =
                            getNamesOfRatsInOverview readingFromGameClient

                        currentTargetName =
                            activeTargetNameFromReading readingFromGameClient

                        describeAnomaly =
                            "Current anomaly: "
                                ++ (getCurrentAnomalyIdentityAsSeenInProbeScanner readingFromGameClient
                                        |> Maybe.map describeAnomalyIdentity
                                        |> Maybe.withDefault "None"
                                   )
                                ++ "."

                        describeArrivalWindowClause =
                            describeArrivalWindow
                                { readingsSinceWarpEnded = context.memory.readingsSinceWarpEnded
                                , windowIsOpen =
                                    arrivalWindowIsOpen
                                        { readingsSinceWarpEnded = context.memory.readingsSinceWarpEnded }
                                , otherPilotsFoundOnArrival =
                                    getCurrentAnomalyIDAsSeenInProbeScanner readingFromGameClient
                                        |> Maybe.andThen (\anomalyID -> memoryOfAnomalyWithID anomalyID context.memory)
                                        |> Maybe.map .otherPilotsFoundOnArrival
                                }

                        describeOverview =
                            ("Seeing "
                                ++ (namesOfOtherPilotsInOverview |> List.length |> String.fromInt)
                                ++ " other pilots in the overview"
                            )
                                ++ (if namesOfOtherPilotsInOverview == [] then
                                        ""

                                    else
                                        ": " ++ (namesOfOtherPilotsInOverview |> String.join ", ")
                                   )
                                ++ "."

                        describeRatsInOverview =
                            "rats " ++ (namesOfRatsInOverview |> List.length |> String.fromInt) ++ "."

                        describeCurrentTarget =
                            case currentTargetName of
                                Nothing ->
                                    -- No condition clause here: there is
                                    -- nothing whose condition it would be.
                                    "no target."

                                Just name ->
                                    "target "
                                        ++ name
                                        ++ " "
                                        ++ describeTargetHitpoints
                                            (activeTargetHitpointsPercent readingFromGameClient)
                                        ++ "."
                    in
                    -- The hints get a line of their own: they are absent on
                    -- most readings and long when present, so folding them in
                    -- would make the row line jump between short and unwieldy.
                    [ [ describeShip ]
                    , [ describeDrones ]
                    , [ describeAnomaly, describeArrivalWindowClause, describeOverview ]
                    , [ describeRatsInOverview, describeCurrentTarget ]
                    , [ describeOverviewIndicationHints readingFromGameClient ]
                    ]
                        |> List.map (String.join " ")
    in
    [ [ describeStatusHeader context ]
    , [ describePerformance ]
    , [ describeMenuAndSettlingCounters ]

    -- Ahead of `describeCurrentReading`, which is only built when there is a
    -- ship UI: a quick message can be shown while docked, and the docked case
    -- is exactly where a client notice nobody has read is most likely to be
    -- sitting.
    , [ describeQuickMessage context.memory.quickMessage ]
    , describeCurrentReading
    ]
        |> List.concat
        |> String.join "\n"


overviewEntryIsTargetedOrTargeting : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsTargetedOrTargeting overviewEntry =
    overviewEntry.commonIndications.targetedByMe || overviewEntry.commonIndications.targeting


overviewEntryIsActiveTarget : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsActiveTarget =
    .namesUnderSpaceObjectIcon
        >> Set.member "myActiveTargetIndicator"


{-| Whether this object is holding the ship in place.

The client says so on the overview entry itself, and saxrat had read it **not
once**: `isWarpDisruptingMe` was parsed on every reading of every recorded run
and the only read site in the repository was the mission runner's. It matters
more than any other property of a target, because everything the bot does when a
fight goes wrong assumes it can leave -- the retreat warps to a celestial, and
warping is precisely what a scrambler prevents.

So a scrambler is shot first, ahead of `overviewEntryIsStoppingUsFighting` and
ahead of the distance order. Killing it is the only thing that restores the
option to leave.

-}
overviewEntryIsWarpDisruptingMe : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsWarpDisruptingMe overviewEntry =
    overviewEntry.commonIndications.isWarpDisruptingMe


{-| Whether this object is stopping the ship fighting, as opposed to stopping it
leaving.

The client names both of these on the same overview row it names the scrambler
on, and the bot read neither until #231. They sit in their own tier _behind_
`overviewEntryIsWarpDisruptingMe` and _ahead_ of the distance order: a scrambler
takes an option away, where these two make the ship worse at using one.

**"dampening", not "damping"** -- that is the client's own spelling, and it is
exactly the detail a matcher written from memory gets wrong. Both literals were
cut out of `~/eve-bot-logs` rather than guessed, which is what made #40's
attacker rule safe and is the same discipline. Tracking disruption is the most
common indication in the whole corpus, at nineteen times the warp disruption the
bot was already acting on.

**Neither of the two harms #231 argues for has been observed**, and this rule
deliberately does not rest on them -- see the PR for the recount. A tracking
disruptor was expected to drive #90's zero-damage give-up, and #90's own tally
reads `none` on every reading of every run carrying both. A dampener was
expected to teach `lockRefusedAtMeters` an artefact bound that only ever moves
down, and the one run carrying the dampening hint never moved that bound. What
this rests on instead is the client's own statement of fact about a row, and how
often it makes it.

Target painting and webifying are deliberately not here. A painter makes the ship
easier to hit rather than less able to fight, and a webifier is #40's open case.

-}
overviewEntryIsStoppingUsFighting : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsStoppingUsFighting overviewEntry =
    overviewEntry.commonIndications.isTrackingDisruptingMe
        || overviewEntry.commonIndications.isSensorDampeningMe


{-| Where an attackable row sorts, ahead of the distance order.

Three tiers rather than two, and the split is between _taking an option away_
and _making the ship worse at using one_:

  - **Tier 0, holding the ship in place** -- `overviewEntryIsWarpDisruptingMe`.
    Everything the bot does when a fight goes wrong assumes it can leave, and
    warping is precisely what a scrambler prevents, so killing it is the only
    thing that restores the option. Survival, and it stays ahead of the rest.
  - **Tier 1, stopping the ship fighting** --
    `overviewEntryIsStoppingUsFighting`. Effectiveness rather than survival: the
    ship can still leave, it is just bad at the fight while these are on it.
  - **Tier 2, everything else**, in the distance order it arrived in.

This is a **reordering and not a widening**, which is what makes it safe by
placement rather than by argument: every row it can move is a row
`shouldAttackOverviewEntry` already admitted, so no guard is bypassed and no row
is added. A tier is a number about a row and reads nothing else -- no memory, no
settings, no reading -- so it can be executed on rows the parser built.

-}
combatPriorityTier : EveOnline.ParseUserInterface.OverviewWindowEntry -> Int
combatPriorityTier entry =
    if overviewEntryIsWarpDisruptingMe entry then
        0

    else if overviewEntryIsStoppingUsFighting entry then
        1

    else
        2


{-| The EWAR hints the client has written on the rendered overview rows.

**saxrat reads these hints and has never once shown them.** `combatPriorityTier`
above consumes two of the five literals the corpus holds, off
`commonIndications`, which the parser derives from exactly the strings printed
here -- so the bot acts on this evidence and prints none of it. Across saxrat's
227,749 recorded readings there is no `Overview indications:` line and no
equivalent, because the mission runner's clause was never ported. #265 is what
that costs: saxrat chose an out-of-range overview row on 13,918 readings and the
corpus cannot say what was on any of them.

The webifier's and the target painter's literals are parsed and read by no rule
in this bot. Printing them is how the evidence for a rule about them
accumulates, which is how #231's two literals were cut out of a log rather than
guessed at -- and is the same move `describeQuickMessage` made before anything
matched on a quick message.

Capped and deduplicated: distinct strings across **rendered** rows only, since a
virtualised row's contents belong to whatever was recycled into its place. The
count is taken before the cap, so a reading carrying more than
`overviewIndicationHintsShown` says so by the number exceeding the strings.

-}
describeOverviewIndicationHints : ReadingFromGameClient -> String
describeOverviewIndicationHints readingFromGameClient =
    let
        hints =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter overviewEntryIsDisplayed
                |> List.concatMap .rightAlignedIconsHints
                |> Common.Basics.listUnique
    in
    case hints of
        [] ->
            "hints 0."

        _ ->
            "hints "
                ++ (hints |> List.length |> String.fromInt)
                ++ " ("
                ++ (hints
                        |> List.take overviewIndicationHintsShown
                        |> List.map (\hint -> "'" ++ hint ++ "'")
                        |> String.join " "
                   )
                ++ ")."


{-| How many distinct overview hints the status line spells out.

A bound rather than a policy: the strings are the client's own sentences and a
grid under several kinds of EWAR would otherwise put a paragraph on every
reading. The count beside them is not capped, so a reading past this bound is
still visible as one.

-}
overviewIndicationHintsShown : Int
overviewIndicationHintsShown =
    8


{-| Whatever the client says is shooting this ship is a valid target.

The rule used to be the overview's icon colour alone -- a sprite palette test,
so it requires somebody to have predicted the object. Anything the palette does
not cover is invisible **including while it is shooting the ship**, and the
failure is silent in the worst available direction: "Rats in overview: 0" is
what the bot prints either way.

The second rule is the client's own statement of fact. EVE's combat log names
every attacker (`49 from Centior Monster - Penetrates`), the host already
aggregates that channel, and the names it carries are the same strings the
overview shows -- 33 of the 37 distinct attackers across the recorded runs
appear byte for byte as an overview entry's Name.

**Matched exactly, never as a substring.** A wreck's Type is its owner's name
with " Wreck" appended, so a substring rule would have the bot open fire on the
corpse of the thing that stopped shooting it -- forever, since a wreck cannot
die.

**It widens the set; it does not reorder it.** An entry qualifying only because
it shot us enters the same list at its own distance rank and is subject to every
guard the colour rule's entries are -- which is why the on-grid test stays
outside the disjunction rather than being one more alternative inside it. An AU
distance does not parse as meters and nothing measured in AU is reachable in
combat.

-}
shouldAttackOverviewEntry : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry attackerNames overviewEntry =
    (iconSpriteHasColorOfRat overviewEntry
        || isObjectShootingAtUs attackerNames overviewEntry
    )
        && overviewEntryDistanceIsOnGrid overviewEntry


{-| Does the client's combat log name this overview row as having hit us?

Case-insensitive and trimmed, because the two sources are different renderings
of one name and nothing guarantees the client capitalises them alike. Both the
Name and the Type column are accepted, which exactness makes safe; the recorded
evidence is for the Name column specifically.

An empty `attackerNames` matches nothing at all, which is the answer both a
quiet grid and a host carrying no combat log arrive here as.

-}
isObjectShootingAtUs : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectShootingAtUs attackerNames overviewEntry =
    let
        normalize =
            String.trim >> String.toLower

        labels =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
                |> List.map normalize
    in
    attackerNames
        |> List.any (\attackerName -> labels |> List.member (normalize attackerName))


{-| Whether the entry's distance is one the bot can act on at all.

The overview shows a distance in AU once an object is far enough away, and
`parseDistanceUnitInMeters` understands only "m" and "km" -- so an AU distance
does not parse and `objectDistanceInMeters` is an `Err`. Everything that wants a
number from it falls back to a placeholder and carries on as though the object
were merely far, which is how something on the other side of the system reaches
the lock candidates: it sorts last, but with nothing nearer it is still the head
of the list, and `lockTargetFromOverviewEntry` cannot read its distance, so it
stops and asks for help.

Nothing measured in AU is reachable in combat -- the longest targeting range in
the game is a few hundred km -- so these are dropped here, at the one point that
decides what counts as something to shoot, rather than at each of the places
that would otherwise try to lock, approach or wait for it.

-}
overviewEntryDistanceIsOnGrid : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryDistanceIsOnGrid overviewEntry =
    case overviewEntry.objectDistanceInMeters of
        Ok _ ->
            True

        Err _ ->
            False


{-| Factored out of decideActionInAnomaly's own overviewEntriesToAttack /
targetsToUnlock let-bindings so updateMemoryForNewReadingFromGame can
compute the same "target to unlock" identity from just a reading (no bot
settings needed) -- used to track how long it's stayed in the same place,
see routeFirstMarkerUnchangedTicks-style tracking on BotMemory below.
-}
overviewEntriesToAttackFromReadingFromGameClient : List String -> ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
overviewEntriesToAttackFromReadingFromGameClient attackerNames readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.filter (shouldAttackOverviewEntry attackerNames)


{-| Whether the ship's own persistent cargo-hold "Inventory" window (open
throughout this whole session, same as the probe scanner/overview/drones
windows the bot's setup instructions call for) currently has a wreck's
loot showing, as opposed to just sitting on the ship's own hangar view.
`EveOnline.ParseUserInterface.InventoryWindow` has no dedicated field for
this (same gap noted at the "Loot All" text-search call site), and
`readingFromGameClient.inventoryWindows |> List.head` used to just grab
the window unconditionally -- since it's _always_ present, that meant the
looting logic thought a wreck was open even when nothing had ever been
opened at all, forcing it to force-close a window the player never
wanted closed (stuck 650+ seconds live with zero rats and zero commander
wrecks anywhere in the overview).

First fix attempt here checked `leftTreeEntries |> List.isEmpty`, on the
assumption that opening a wreck's cargo shows a separate flat popup with
no hangar tree. Wrong, confirmed live immediately after shipping it: a
wreck opened via "Open Cargo" shows up as one more row _in the same
sidebar tree_ as the ship's own hangar (Drone Bay, PLEX Vault, etc.), not
a separate window -- so `leftTreeEntries` is non-empty either way, and
that check excluded the real, already-open loot view every single tick,
which made the bot think "Open Cargo" had never been clicked and re-click
it forever even while the wreck's contents (and a working "Loot All"
button) were sitting right there on screen.

Checking for a findable "Loot All" button instead: not a structural
property of the window, but the actual thing this code needs to already
be true before it can act -- present only once a wreck is both open _and_
selected in the tree (confirmed live: "Open Cargo" both adds and selects
the row in one step, so this becomes findable immediately, no separate
select-click needed). Doesn't cover the fully-looted-and-emptied case (no
button left to find) as elegantly -- that degrades to the existing
"harmless, just wasted ticks" fallback of re-clicking "Open Cargo" on the
same already-empty wreck, bounded by `lootWreckTimeRemainingSeconds`
elsewhere in this file, rather than a clean close -- but that's a correct,
bounded, wasted-tick nuisance, not a real stall like the two bugs above.

-}
wreckLootWindowsFromReadingFromGameClient : ReadingFromGameClient -> List EveOnline.ParseUserInterface.InventoryWindow
wreckLootWindowsFromReadingFromGameClient readingFromGameClient =
    readingFromGameClient.inventoryWindows
        |> List.filter (.uiNode >> findUiElementWithText "Loot All" >> (/=) Nothing)


{-| Readings a loot window gets to close through its own controls before the
escalation starts.

Above the whole recorded distribution of windows that closed, rather than a
number picked to feel patient: across the recorded saxrat runs that carry the
`loot N` status counter, every stretch with a loot window in the reading peaks
at exactly 2 and there are no others, so a window still open on the third
reading is one that outlasted every close this corpus has ever watched work.

-}
lootWindowOwnControlsReadings : Int
lootWindowOwnControlsReadings =
    2


{-| Readings a loot window gets the window's own **Close** control before the
keystroke is tried.

The mission runner reached this rung and this bot never could -- see
`lootWindowCloseRung`. Three times the rung above, so a Close control the client
draws gets several clicks before anything else is tried.

-}
lootWindowCloseControlReadings : Int
lootWindowCloseControlReadings =
    lootWindowOwnControlsReadings * 3


{-| Readings a loot window is worked at all before the bot leaves it open and
gets on with the rest of the tree.

Written as a multiple so the argument cannot drift away from the number: eight
times the rung that closes every loot window the corpus records closing. That
is enough for several clicks on the Close control and several `Alt+C` presses at
the settling window below, and it sits under the shortest escalation any
recorded run ever ran -- the five saxrat runs that reached the force-close spent
2, 3, 23, 29 and 303 consecutive readings in it, none of them closing anything.
The recorded `loot N` peaks are 1, 2 and 301 and nothing lies between, so this
is placed in a gap rather than cut through a distribution.

-}
lootWindowForceCloseGiveUpReadings : Int
lootWindowForceCloseGiveUpReadings =
    lootWindowOwnControlsReadings * 8


{-| What to do about a loot window that is in this reading.
-}
type LootWindowCloseRung
    = UseTheWindowsOwnControls
    | ClickTheWindowsCloseControl
    | PressTheInventoryToggle
    | LeaveTheLootWindowAlone


{-| The ladder over a loot window, and the bound on it.

`readingsOpen` is `BotMemory.lootWindowOpenTicks`, which is derived from the
window being in the reading rather than accumulated across windows -- it is
zero on any reading with no wreck loot window in it. So a close that lands ends
the escalation by itself and the next wreck starts from the first rung, which
is why nothing here has to be reset on success.

The rungs, in order:

  - "Loot All", the window's own control for the thing the window is open to do,
    for `lootWindowOwnControlsReadings` readings;
  - the window's own **Close** control, to
    `lootWindowCloseControlReadings`. **This bot could never reach that click**,
    and that is a defect of its own rather than a rung being added for symmetry:
    `wreckLootWindowsFromReadingFromGameClient` selects a window _by_ its
    carrying "Loot All", and the close-button lookup sat under a `Nothing`
    branch of a second lookup for that same text on the same node -- so it, and
    the `askForHelpToGetUnstuck` under it, were unreachable by construction. The
    mission runner reached the equivalent click and its comment records what
    happened: "Confirmed live on a window that had been stuck open for hours:
    Ctrl+W alone left it open, clicking its title bar first then Ctrl+W closed
    it, and clicking Close closed it with no focus step at all";
  - `Alt+C`, EVE's inventory toggle, which needs no focus. This replaces
    `Ctrl+W`, which is the client's _close the active window_ and therefore
    needs the window focused: measured live on 2026-08-16 at an escalation room
    in Uchat, 919 `force it shut (Ctrl+W)` decision lines across 303 readings
    closed nothing at all, and one `Alt+C` pressed by hand at the same client
    took the tree from `['InventoryPrimary']` to `[]`. That is the second
    recorded instance of the same keystroke failing the same way; `CLAUDE.md`
    had the first, and the mission runner acted on it while this bot did not.
    It is also what a reading with no Close control in it falls to, so a window
    the parser cannot find controls on is not a reading spent waiting;
  - then nothing. Past `lootWindowForceCloseGiveUpReadings` the branch stands
    aside and the caller goes on looting the next wreck or leaves the grid, with
    the window still on the screen. A loot window nobody can close is worth
    strictly less than a bot that goes on ratting, which is
    `closeMessageBox`'s own answer to the same shape.

`togglePressedRecently` is the settling window, and it falls back to the rung
below rather than to a wait: `Alt+C` is a _toggle_, so pressing it again before
the client has shown the result re-opens what the last press closed --
`moduleButtonClickSettlingSteps`' problem, at a window rather than at a module
button. The live measurement says the propagation is not instant, so a press
per reading is a press into an answer that has not arrived.

-}
lootWindowCloseRung :
    { readingsOpen : Int
    , closeControlIsInTheReading : Bool
    , togglePressedRecently : Bool
    }
    -> LootWindowCloseRung
lootWindowCloseRung { readingsOpen, closeControlIsInTheReading, togglePressedRecently } =
    if readingsOpen > lootWindowForceCloseGiveUpReadings then
        LeaveTheLootWindowAlone

    else if readingsOpen <= lootWindowOwnControlsReadings then
        UseTheWindowsOwnControls

    else if readingsOpen <= lootWindowCloseControlReadings && closeControlIsInTheReading then
        ClickTheWindowsCloseControl

    else if togglePressedRecently then
        UseTheWindowsOwnControls

    else
        PressTheInventoryToggle


{-| The `Alt+C` chord, built the way every other modifier chord in this app is.

`cg_input` stamps each posted event with the modifiers _this process_ is
holding, which is what PR #241 fixed -- so the modifier has to be pressed and
released as its own effect rather than assumed, exactly as `Alt+F1` does for
the propulsion module. `vkey_MENU` maps to Option and `vkey_C` to `C` in the
host's own `_VK_TO_CGKEYCODE`.

-}
pressInventoryToggleEffects : List EffectOnWindow.EffectOnWindowStruct
pressInventoryToggleEffects =
    [ EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU
    , EffectOnWindow.KeyDown EffectOnWindow.vkey_C
    , EffectOnWindow.KeyUp EffectOnWindow.vkey_C
    , EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU
    ]


{-| Both KeyDowns, so this cannot be satisfied by the plain `C` of some other
chord or by the `Alt` of `Alt+F1` -- `doEffectsDeactivatePropulsionModule`'s
arrangement, for its reason.
-}
doEffectsPressInventoryToggle : List EffectOnWindow.EffectOnWindowStruct -> Bool
doEffectsPressInventoryToggle effects =
    doEffectsPressKey EffectOnWindow.vkey_MENU effects
        && doEffectsPressKey EffectOnWindow.vkey_C effects


{-| What the status line says about a loot window, on every reading one is open.

The decision line goes away on the reading the branch stands aside -- that is
what standing aside means -- so this is the only thing on a later reading that
says a window is still there and is being left alone. `describeMessageBoxStandoff`'s
mechanism, for its reason.

-}
describeLootWindowStandoff : { readingsOpen : Int, lootWindowOpen : Bool } -> String
describeLootWindowStandoff { readingsOpen, lootWindowOpen } =
    if not lootWindowOpen then
        "loot 0"

    else
        "loot "
            ++ String.fromInt readingsOpen
            ++ "/"
            ++ String.fromInt lootWindowForceCloseGiveUpReadings
            ++ (if readingsOpen > lootWindowForceCloseGiveUpReadings then
                    " (GIVEN UP ON, still open)"

                else if readingsOpen > lootWindowCloseControlReadings then
                    " (pressing Alt+C at it)"

                else if readingsOpen > lootWindowOwnControlsReadings then
                    -- Both, because the count is all this clause has: which of
                    -- the two the reading takes turns on whether the parser
                    -- found a Close control on it, and that is not a number.
                    " (clicking its Close control, or Alt+C if it has none)"

                else
                    ""
               )


{-| Whether a row is loot rather than something to shoot.

Whole words rather than substrings, which is `containsWords`' own reason for
existing and is the mission runner's `textNamesALootableObject` rule: the live
rat `Wrecker Alvum` contains "wreck", and a substring test therefore reads it as
a container. Run 44 is what that costs -- `activeTargetOverviewEntryIsStray` then
answers `True` for a rat the guns are pointed at, the branch above holds fire,
and the rat sits at 99% shield while the anomaly runs 36 minutes.

Holding fire is the expensive direction, which is why this is the site that
matters more than the unlock beside it: declining to shoot needs no cascade to
land and nothing bounds it.

-}
overviewEntryIsStrayLockTarget : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsStrayLockTarget overviewEntry =
    let
        textsToCheck =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
    in
    [ "container", "wreck" ]
        |> List.any (\pattern -> textsToCheck |> List.any (containsWords pattern))


{-| Click the object we are about to shoot, before shooting it.

Locking a target is not the same as the client treating it as the thing your
weapons act on. Seen live and then confirmed by hand: the Kruul's Pleasure Hub
was locked, carried `ActiveTargetIndicator` in the target bar, and the bot
pressed F1 at it for fifteen minutes with the weapon never leaving
`ramp_active=False` and not one line in the game log. A plain left click on its
overview row, and the very next moment the beam fired for 242 and five idle
drones engaged.

So a click on the row goes out before the guns do. `overviewEntryIsActiveTarget`
is preferred where the overview marks one, since that is the row the client
already agrees with; otherwise the nearest thing worth attacking, which is what
the bot locks from anyway.

Returns Nothing once the click has gone out, so the guns follow on the next
step rather than the row being re-clicked every tick -- a click is also how you
_change_ the active target, so repeating it is not free.

-}
clickTargetBeforeShooting :
    BotDecisionContext
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
    -> Maybe DecisionPathNode
clickTargetBeforeShooting context entriesToAttack =
    let
        alreadyClicked entry =
            context.previousStepsEffects
                |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
                |> List.any
                    (\stepEffects ->
                        stepEffects
                            |> EveOnline.BotFramework.findMouseButtonClickLocationsInListOfEffects
                                MouseButtonLeft
                            |> List.any
                                (EveOnline.BotFramework.isPointInRectangle
                                    (EveOnline.BotFramework.growRegionOnAllSides 1
                                        entry.uiNode.totalDisplayRegion
                                    )
                                )
                    )
    in
    [ entriesToAttack |> List.filter overviewEntryIsActiveTarget |> List.head
    , entriesToAttack |> List.head
    ]
        |> List.filterMap identity
        |> List.head
        |> Maybe.andThen
            (\entry ->
                if alreadyClicked entry then
                    Nothing

                else
                    Just
                        (describeBranch
                            ("Click '"
                                ++ (entry.objectName |> Maybe.withDefault "the target")
                                ++ "' on the overview first -- locking it is not enough to make the guns act on it."
                            )
                            (clickUiElement entry.uiNode)
                        )
            )


{-| Promote one of the locked targets to being the active one, if none is.

Locking a target and _aiming_ at it are separate things in EVE, and they can
come apart: seen live with a full set of locks and no active target at all,
which quietly makes every weapon hotkey a no-op -- F1 fires whatever is fitted
at whatever is active, and nothing was. The bot went on pressing it and hitting
nothing.

Pairing the hotkey with the lock click would not fix it. At the moment the lock
is clicked the target is not locked yet -- locking takes time -- so a hotkey
sent alongside would fire at nothing just as reliably. What is needed is to
notice the gap and close it, which is what this does: a plain left click on a
target's portrait in the target bar promotes it to active.

Nearest first, so the ship shoots what is closest rather than whichever target
happens to sit leftmost in the bar.

-}
activateOneOfTheLockedTargets : BotDecisionContext -> Maybe DecisionPathNode
activateOneOfTheLockedTargets context =
    let
        targets =
            context.readingFromGameClient.targets
    in
    if targets |> List.any .isActiveTarget then
        Nothing

    else
        targets
            |> List.head
            |> Maybe.map
                (\target ->
                    describeBranch
                        ("I have "
                            ++ String.fromInt (List.length targets)
                            ++ " locked target(s) but none of them is the active one, so the guns have nothing to shoot at -- click one to make it active."
                        )
                        (clickUiElement (target.barAndImageCont |> Maybe.withDefault target.uiNode))
                )


{-| The condition of whatever EVE currently calls the active target.

Read off the target bar rather than off the overview, because the bars are drawn
in the bar and the overview row carries no health at all. It is the same target
either way -- `activeTargetOverviewEntryIsStray` and this both mean the one the
guns and drones go to -- but the two are found by different routes, so a reading
can name a target from the overview and answer `Nothing` here, which is why the
clause below has to be able to say so.

-}
activeTargetHitpointsPercent : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.Hitpoints
activeTargetHitpointsPercent readingFromGameClient =
    readingFromGameClient.targets
        |> List.filter .isActiveTarget
        |> List.head
        |> Maybe.andThen .hitpointsPercent


{-| The target's three layers, in the ship's own `Shield: 58%  Armor: 100%` form.

**Three numbers, never one.** Issue #90 exists because nothing told the bot its
shots were doing zero damage, and the fix had to reconstruct that from the
combat log's outgoing lines because no field said what the target's health was
doing. Run 27 shot an `Infested Asteroid` for roughly 290 readings with every
shot landing for zero; a bar that never moved would have said so on the second
reading. What it looks like is a shield that does not move while armour and hull
sit at 100%, which any combined figure hides.

**Absent reads as absent.** A target whose bars this reading could not read
prints `unknown` for all three, never `0%`: a fabricated zero is a hull about to
explode as far as any later rule is concerned. `loadRefusalFromGameLog`'s
register, and the same rule `Nothing` versus `Just []` carries for the game log.

This is an instrument and nothing decides on it -- see
`test_target_hitpoints.py`, which pins that this and
`activeTargetHitpointsPercent` are read by the status line and by nothing else,
the way PR #130 pinned `quickMessage` until a run had shown what it records.

-}
describeTargetHitpoints : Maybe EveOnline.ParseUserInterface.Hitpoints -> String
describeTargetHitpoints hitpoints =
    case hitpoints of
        Nothing ->
            "[?/?/?]"

        Just percent ->
            "["
                ++ (percent.shield |> String.fromInt)
                ++ "/"
                ++ (percent.armor |> String.fromInt)
                ++ "/"
                ++ (percent.structure |> String.fromInt)
                ++ "]"


{-| Safety net for the weapon/drone-activation branches, independent of the
Target<->overview name matching `targetsToUnlockFromReadingFromGameClient`
relies on (so a gap in that matching doesn't also sneak past this check):
whether the overview row for whichever target EVE currently reports as
"active" -- the one weapons and drones actually go to when activated, since
neither one lets you choose which locked target to hit -- looks like a
container or wreck rather than a rat.

**Also feeds the unlock candidate list, since #303.** Holding fire on a stray
active target and freeing its lock slot used to be two different questions
answered from two different sources, and the second one could answer "no
evidence" while this one kept firing "hold fire" -- the ship then sat holding
a wreck it would never shoot and never let go of. The call site building
`targetsToUnlock` now adds the active target here whenever this answers
`True`, so the same signal that stops the guns also frees the slot.

-}
activeTargetOverviewEntryIsStray : ReadingFromGameClient -> Bool
activeTargetOverviewEntryIsStray readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsActiveTarget
        |> List.any overviewEntryIsStrayLockTarget


{-| Checks the locked target's own display text directly, instead of
cross-referencing by name against a separate overview entry. Two earlier
versions of this cross-referenced instead (first against rat-colored
overview entries by exact name; then, after that misfired on an active rat,
against container/wreck-typed overview entries by exact name) and both
still ended up stuck live: even with the overview side correctly reporting
`objectName = "Cargo Container"` (confirmed via the "Current target" status
line, which reads that same field), the locked target never matched --
meaning `Target.textsTopToBottom` apparently isn't an exact match for
whatever the overview shows (likely bundled with other text, different
whitespace, etc. -- never actually confirmed, since matching on the
target's own text sidesteps the question entirely). Matching directly on the
target bar's own text removes that cross-tree assumption.

Whole words rather than substrings, for `containsWords`' reason and for
`overviewEntryIsStrayLockTarget`'s: `Wrecker Alvum` contains "wreck", so a
substring test asks the bot to unlock a live rat, which is run 44's 387 unlock
decisions. The bar carries the object's own name -- that is _why_ the rat
matched here at all -- so the pattern still has a name to find.

What is unconfirmed is punctuation, and the comment above says why: nothing has
ever read this field's exact shape. `containsWords` normalises whitespace and
not punctuation, so a bar that renders `Cargo Container(1)` would stop matching
here where the substring test matched. That used to fail toward _not_ unlocking
a real container and leaving it held forever, run 50's own incident -- see
#303. `activeTargetOverviewEntryIsStray` still catches the case off the
overview's own clean `objectName`/`objectType`, but it no longer only holds
fire: the call site building `targetsToUnlock` adds the active target as a
candidate whenever that check answers `True`, so a miss here is now covered
rather than stuck. This function stays the primary source -- it can name a
non-active locked target the overview check never looks at -- and the two are
unioned rather than one gating the other.

-}
targetsToUnlockFromReadingFromGameClient : ReadingFromGameClient -> List EveOnline.ParseUserInterface.Target
targetsToUnlockFromReadingFromGameClient readingFromGameClient =
    readingFromGameClient.targets
        |> List.filter
            (\target ->
                target.textsTopToBottom
                    |> List.any
                        (\text ->
                            [ "container", "wreck" ]
                                |> List.any (\pattern -> containsWords pattern text)
                        )
            )


{-| `targetsToUnlockFromReadingFromGameClient`, plus the active target when
`activeTargetOverviewEntryIsStray` disagrees with it -- see #303 and that
function's own doc comment for why. **One definition**, read at both the
decision site that clicks the unlock and the memory update that drives the
settling-window guard in front of that click: a target this function finds
only through the overview-stray half has no bar-text region of its own for
`targetToUnlockUnchangedTicks` to track, so if the settling guard read a
narrower list than the click site it would never see the region settle and
would wait on it forever -- reporting "waiting for it to settle" while never
actually clicking. Two copies of this list would have drifted into exactly
that silently.
-}
targetsToUnlockIncludingActiveIfStray : ReadingFromGameClient -> List EveOnline.ParseUserInterface.Target
targetsToUnlockIncludingActiveIfStray readingFromGameClient =
    targetsToUnlockFromReadingFromGameClient readingFromGameClient
        ++ (if activeTargetOverviewEntryIsStray readingFromGameClient then
                readingFromGameClient.targets |> List.filter .isActiveTarget

            else
                []
           )


{-| Whether there is currently anything in the overview worth fighting.
Used to gate the "keep these modules always active" enforcement (see
`shipUIModulesToActivateAlways` call sites): that enforcement exists to
protect us while fighting, but it has no way to tell an active-tank
module apart from the propulsion module sitting in the same row, so it
was fighting `ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`
over the propulsion module's state every time we tried to warp away with
nothing left to shoot -- deactivate for warp, then "always active"
reactivates it next tick, forever. Only enforcing "always active" while
there is something to attack breaks that fight without needing to know
which module is which.
-}
anyAttackableInOverview : List String -> ReadingFromGameClient -> Bool
anyAttackableInOverview attackerNames readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.any (shouldAttackOverviewEntry attackerNames)


shouldAttackOverviewEntryFirst : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntryFirst overviewEntry =
    case overviewEntry.objectName of
        Nothing ->
            False

        Just objectName ->
            objectName |> String.contains "Tower"


{-| The widget's own `_display` flag, defaulting to shown when absent (most
nodes never set it).
-}
nodeIsDisplayed : EveOnline.MemoryReading.UITreeNode -> Bool
nodeIsDisplayed uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


{-| Whether an overview row is really on screen.

The overview virtualises: every object in space has an entry in the UI tree,
but only the dozen or so rows that fit are rendered, and the rest keep whatever
position they last held while recycled. So a hidden entry reports a perfectly
plausible region pointing at a row that now belongs to something else. Clicking
it is worse than a no-op -- it acts on the wrong object. Seen live in the
mission bot: it approached an Asteroid Factory 18 times while trying to reach a
Cargo Warehouse that was scrolled out of sight, and parked at the factory.

`_display` is what distinguishes them; the region does not.

-}
overviewEntryIsDisplayed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    nodeIsDisplayed entry.uiNode.uiNode


{-| Whether a wreck has already been emptied.

EVE swaps the bracket icon when a wreck is looted -- `wreckNPC.png` becomes
`wreckLootedNPC.png` -- so the game already answers this and nothing needs
remembering: stateless, correct across restarts, and right about wrecks emptied
by someone else.

The id memory in `notAlreadyEmptied` is kept as a backstop, since this test
depends on the icon updating promptly.

-}
overviewEntryLooksLooted : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryLooksLooted entry =
    entry.uiNode.uiNode
        :: EveOnline.MemoryReading.listDescendantsInUITreeNode entry.uiNode.uiNode
        |> List.filterMap EveOnline.ParseUserInterface.getTexturePathFromDictEntries
        |> List.any (stringContainsIgnoringCase "looted")


notAlreadyEmptied : BotDecisionContext -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
notAlreadyEmptied context entry =
    not (overviewEntryLooksLooted entry)
        && (case entry.objectItemID of
                Just itemID ->
                    not (List.member itemID context.memory.lootedWreckIds)

                Nothing ->
                    True
           )


{-| How close the ship has to be before it can act on an object out in space --
open a container, or activate an acceleration gate. EVE's own limit is 2,500 m
for both; this stays inside that so the ship is not sitting exactly on the
boundary when the click lands.
-}
interactionRangeInMeters : Int
interactionRangeInMeters =
    2000


shipIsApproaching : ReadingFromGameClient -> Bool
shipIsApproaching readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
        |> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverApproach)
        |> Maybe.withDefault False


{-| How long to believe the ship's own "approaching" indication before issuing
a fresh Approach anyway.

`ManeuverApproach` stays set while the ship approaches _something_, which need
not be the thing we asked for. The mission bot was seen live sitting 29 km from
its target, moving at 304 m/s with the distance unchanged over 12 seconds --
approaching, but not that. With no bound the guard suppressed every re-issue
and the bot never redirected.

-}
approachIndicationTrustedForTicks : Int
approachIndicationTrustedForTicks =
    10


{-| The "do not restart what is already running" guard shared by everything that
acts on an object the ship has not reached yet.

The command puts the ship into an approach, and re-issuing it while that
approach is running restarts the manoeuvre and burns a step every tick for
nothing. `ManeuverApproach` is believed for a bounded run of readings only,
since it stays set while the ship approaches _something_, which need not be this
object.

-}
unlessAlreadyClosingIn : BotDecisionContext -> String -> DecisionPathNode -> DecisionPathNode
unlessAlreadyClosingIn context description action =
    if
        shipIsApproaching context.readingFromGameClient
            && (context.memory.shipApproachingTicks < approachIndicationTrustedForTicks)
    then
        describeBranch (description ++ " Already on the way -- let it run.")
            waitForProgressInGame

    else
        describeBranch description action


{-| Open an object's cargo, at whatever range.

A double click is EVE's own "Open Cargo", and from outside looting range the
client answers it by flying there and opening on arrival -- so this is the whole
interaction at any distance, with no separate approach to arrange.

-}
openCargoOnOverviewEntry :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> DecisionPathNode
openCargoOnOverviewEntry context description entry =
    unlessAlreadyClosingIn context description (doubleClickUiElement entry.uiNode)


{-| Tell the client to act on an object the ship is not next to yet.

EVE's own commands -- "Activate Gate" and the like -- fly the ship there and act
on arrival. Approaching first and issuing the real command on a later tick
cannot match that: the bot only learns it has arrived from the next reading, so
it sits next to the object doing nothing for at least a tick, having crossed the
whole distance to get there. Naming the command up front closes that gap.

The approach guard stays either way. The command puts the ship into an approach,
and re-issuing it while that approach is running restarts the manoeuvre and
burns a context-menu cascade every tick for nothing. `ManeuverApproach` is only
believed for a bounded run of readings, since it stays set while the ship
approaches _something_, which need not be this object.

`menuEntries` is a priority list, so ending it with "approach" leaves the ship
closing the distance even on an object whose own command is missing from the
menu.

-}
closeInOnOverviewEntry :
    BotDecisionContext
    -> { description : String, menuEntries : List String }
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> DecisionPathNode
closeInOnOverviewEntry context { description, menuEntries } entry =
    unlessAlreadyClosingIn context
        description
        (useContextMenuCascadeOnOverviewEntry
            (useMenuEntryWithTextContainingFirstOf menuEntries menuCascadeCompleted)
            entry
            context
        )


{-| Whether `pattern` occurs in `text` as whole words rather than as a substring.

Substring matching has cost this codebase real bugs -- a live rogue drone called
a "Wrecker" contains "wreck", and a station named "Expert Distribution Warehouse"
contains "warehouse" -- so the panel test below compares on word boundaries.
Whitespace is normalised and both sides padded, so a match can neither begin nor
end mid-word and a multi-word pattern still matches as a sequence.

-}
containsWords : String -> String -> Bool
containsWords pattern text =
    let
        padded value =
            " " ++ (value |> String.toLower |> String.words |> String.join " ") ++ " "
    in
    String.contains (padded pattern) (padded text)


{-| A button in the Selected Item panel, by its own `_name`.

`ParseUserInterface` exposes only `orbitButton` off this window, so every other
button is reached by name. `selectedItemActivateGate` is the one this bot presses
and, before this, the only panel button it had ever pressed for anything.

-}
selectedItemButtonNamed :
    ReadingFromGameClient
    -> String
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
selectedItemButtonNamed readingFromGameClient name =
    readingFromGameClient.selectedItemWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.filter
            (\node ->
                (node.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries) == Just name
            )
        |> List.head


{-| Whether the Selected Item panel is showing this overview entry.

Asked before pressing any of the panel's buttons, because they act on whatever is
selected rather than on whatever the decision is about.

A function of the reading rather than of a `BotDecisionContext`, which is the one
shape difference from the mission runner's copy of this and is deliberate:
`updateMemoryForNewReadingFromGame` never sees a decision and has to ask this
same question, since the readings the bot spends asking a gate to open are
exactly the readings that gate is the selected item. Two copies of "is the panel
showing this row" would be two answers that could disagree.

-}
selectedItemIsOverviewEntry :
    ReadingFromGameClient
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> Bool
selectedItemIsOverviewEntry readingFromGameClient entry =
    case ( readingFromGameClient.selectedItemWindow, entry.objectName ) of
        ( Just window, Just name ) ->
            EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode.uiNode
                |> List.any (containsWords name)

        _ ->
            False


{-| Bring a wanted overview row into view by turning the mouse wheel over the
overview, a notch at a time, re-reading between notches.

This used to drag the scrollbar handle to a position computed from the target's
rank by distance. That cannot work, and the live logs say so plainly: the bot
asked 31 times in a row for "the row I want is #6 of 45" and the handle never
moved. Two reasons, either fatal on its own.

The arithmetic collapsed. `(rank - rowsOnScreen / 2) / scrollableRows` is
negative for anything in the first half-page, so it clamped to 0 -- and with the
handle already at the top of its track, the computed destination _was_ where the
handle already sat. The drag was zero-length, and a zero-length drag emits no
movement at all, so nothing was ever sent.

And the premise was wrong anyway: rank by distance is only the row's index if
the overview is sorted by distance and every row is a distinct live object.
Neither held -- rows recycle, and hidden ones keep stale positions.

A wheel notch needs none of that. It does not have to know where the row is,
only which way to look, and it re-reads after every notch. Direction comes from
where the handle sits in its track: room below means scroll down, otherwise turn
around and sweep back up, so a list gets swept rather than pinned against one
end.

-}
scrollOverviewToReveal :
    BotDecisionContext
    -> (EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool)
    -> Maybe DecisionPathNode
scrollOverviewToReveal context entryIsWanted =
    let
        windowsHidingAWantedEntry =
            context.readingFromGameClient.overviewWindows
                |> List.filter
                    (\overviewWindow ->
                        (overviewWindow.entries |> List.any entryIsWanted)
                            && (overviewWindow.entries
                                    |> List.filter entryIsWanted
                                    |> List.all (overviewEntryIsDisplayed >> not)
                               )
                    )
    in
    if
        shipIsApproaching context.readingFromGameClient
            && (context.memory.shipApproachingTicks < approachIndicationTrustedForTicks)
    then
        -- Do not chase the row while closing on it: an object being approached
        -- climbs a distance-sorted list on its own and arrives in view without
        -- help, and scrolling meanwhile only fights the sort.
        Nothing

    else
        case windowsHidingAWantedEntry |> List.head of
            Nothing ->
                Nothing

            Just overviewWindow ->
                let
                    track =
                        (overviewWindow.scrollControls
                            |> Maybe.map .uiNode
                            |> Maybe.withDefault overviewWindow.uiNode
                        ).totalDisplayRegion

                    handle =
                        overviewWindow.scrollControls
                            |> Maybe.andThen .scrollHandle
                            |> Maybe.map .totalDisplayRegion
                            |> Maybe.withDefault track

                    roomBelow =
                        (track.y + track.height) - (handle.y + handle.height)

                    -- Scroll down while the handle has anywhere left to go,
                    -- then sweep back up. A couple of pixels of slack, since the
                    -- handle rarely lands flush against the end of the track.
                    notches =
                        if 2 < roomBelow then
                            -overviewScrollNotchesPerStep

                        else
                            overviewScrollNotchesPerStep

                    scrollOver =
                        overviewWindow.uiNode.totalDisplayRegion
                            |> EveOnline.ParseUserInterface.centerFromDisplayRegion
                in
                Just
                    (describeBranch
                        ("A row I want is off screen ("
                            ++ String.fromInt (overviewWindow.entries |> List.filter overviewEntryIsDisplayed |> List.length)
                            ++ " of "
                            ++ String.fromInt (List.length overviewWindow.entries)
                            ++ " rows rendered) -- turn the wheel "
                            ++ (if notches < 0 then
                                    "down"

                                else
                                    "up"
                               )
                            ++ " over the overview."
                        )
                        (decideActionForCurrentStep
                            (EffectOnWindow.effectsMouseScrollAtLocation scrollOver notches)
                        )
                    )


{-| How far one scroll step turns the wheel. Small enough that a wanted row is
not skipped past between readings.
-}
overviewScrollNotchesPerStep : Int
overviewScrollNotchesPerStep =
    3


{-| Matches the "Ancient Acceleration Gate" (and any other "\* Acceleration
Gate") objects that link the separate rooms ("pockets") inside a multi-room
site like the "Sansha's Command Relay Outpost" opportunity: checks both
`objectName` and `objectType` the same defensive way `isNotableWreck`
does, since which field actually carries the "acceleration gate" text for
this specific object class hasn't been confirmed live yet.
-}
isAccelerationGate : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isAccelerationGate overviewEntry =
    [ overviewEntry.objectName, overviewEntry.objectType ]
        |> List.filterMap identity
        |> List.any (stringContainsIgnoringCase "acceleration gate")


{-| Whether an acceleration gate is close enough to use.

Shared by the memory counter that notices a gate refusing the ship and by the
propulsion-module rule, which switches the module off on arrival -- a gate is
taken from a standstill, so once the ship is here the module has nothing left
to contribute.

-}
accelerationGateIsWithinReach : ReadingFromGameClient -> Bool
accelerationGateIsWithinReach readingFromGameClient =
    accelerationGatesWithinReach readingFromGameClient |> List.isEmpty |> not


accelerationGatesWithinReach :
    ReadingFromGameClient
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
accelerationGatesWithinReach readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.filter
            (\entry ->
                (entry.objectDistanceInMeters |> Result.withDefault 999999)
                    <= interactionRangeInMeters
            )


{-| Whether this reading is one the bot spent asking a gate to open.

The Selected Item panel showing an acceleration gate that is already in reach.
That is what the in-range branch below produces -- it selects the row and then
presses the panel's own button -- so it is the condition under which the gate
failing to open says something about the gate.

**Proximity is not that condition, and saxrat's own runs are what say so.** The
counter this feeds used to advance on `accelerationGateIsWithinReach`, and run 5
took it to 3,504 while the bot pressed `warpToOpportunitySiteIfAvailable` 10,353
times: that branch outranks this one, so for the whole of those readings the
gate was merely nearby and was never once asked to open. 108 give-ups came out
of it, about a gate this session had made three attempts on. The mission
runner's `gateWithinReachTicks` carries the same correction for the same reason
(#42), and what saxrat needs on top of it is that a missing button counts too --
see `gateAskedReadingsAfterReading`.

**Why the branch was not reached was #147, and it is fixed in
`siteProgressStep`** -- the gate is asked before a travelling opportunity step
now, and a `Jump` offered while a gate is in reach is declined as the panel still
showing a site the ship has not gone to. An _arrival_ is asked above the gate
since #261, so a "Warp to Site" with the probe scanner shut can shadow the gate
again by one reading; the scanner is open on 98.7% of every reading the corpus
holds, so what that costs this counter is close to nothing and is bounded by the
same give-up either way. The reading of the corpus that made
this counter necessary is unchanged and is what that fix rests on:
`warpToOpportunitySiteIfAvailable` answers `Just` whenever a "Warp to Site"
button is anywhere in the tree, so while the old ordering held, the gate was
unreachable for as long as one was drawn. Run 5's give-ups are one contiguous
block of 108 lines with **zero** opportunity-warp lines inside it and the last
one 20 lines before it -- the window where the button went away and the branch
became reachable, arriving with a counter already past the bound because
proximity had been spending it for thousands of readings. Run 4 is the control:
one contiguous block too, and **12** opportunity lines in the whole run, none of
them anywhere near it.

So counting the ask changed run 5's outcome outright rather than merely tidying
it. Shadowed readings held the count at 0, and the reachable window is about 36
readings -- short of 40 -- so that give-up would not have fired at all, which is
the correct answer for a gate the bot asked three times. What the ordering fix
adds is that the branch is now asked on those readings rather than shadowed
through them, so the count is spent on a gate the bot is really working.

-}
askingAnAccelerationGateToOpen : ReadingFromGameClient -> Bool
askingAnAccelerationGateToOpen readingFromGameClient =
    accelerationGatesWithinReach readingFromGameClient
        |> List.any (selectedItemIsOverviewEntry readingFromGameClient)


{-| Readings in a row spent asking one gate to open, and it did not open.

Advances on a reading the bot was asking (`askingAnAccelerationGateToOpen`),
**holds** on a reading with a gate in reach that the bot was not asking, and
resets only when the ship leaves reach.

The hold is the mission runner's, for its reason: a reset on a reading that did
not ask is the shape that pinned `gunsSilencedTicks` at 1 forever, and anything
that legitimately holds the tree beside a gate -- a message box, a fight, an
opportunity warp -- would otherwise wipe the evidence between attempts. Leaving
reach resets, because that is the ship no longer asking this gate for anything.

**A reading with the gate selected and no Activate Gate button on the panel is
counted, not held**, which is where this differs from the mission runner's rule.
That one counts only the readings the panel made the offer, and leaves the
no-button state to be bounded by `nothingToDoTicks` from the bottom of its
decision tree. saxrat has no such counter, and this branch answers `Just`, so an
uncounted no-button state is a ship parked at a gate with nothing to end it.
Counting it keeps one bound over both shapes: a gate the panel offers and does
not open, and a gate the panel will not offer to open at all. Both are the ship
asking and getting nowhere, which is what the give-up says.

-}
gateAskedReadingsAfterReading :
    { asking : Bool, gateWithinReach : Bool, before : Int }
    -> Int
gateAskedReadingsAfterReading readingCase =
    if readingCase.asking then
        readingCase.before + 1

    else if readingCase.gateWithinReach then
        readingCase.before

    else
        0


{-| What to do about an acceleration gate the ship is already sitting on.

A pure function over a record so a case can execute it rather than describe it.

-}
type alias GateActivationCase =
    { panelShowsTheGate : Bool
    , panelOffersActivateGate : Bool
    , askedReadings : Int
    }


type GateActivationStep
    = SelectTheGate
    | PressActivateGate
    | WaitForTheActivateButton
    | GiveUpOnThisGate


{-| Whether the budget for asking one gate to open has been spent.

One comparison with three readers -- the step rule, the branch that hands the
turn back, and the status clause that says so on every reading afterwards --
because a give-up that is decided in one place and reported in another is two
places that can disagree about whether the gate was given up on.

-}
gateHasBeenGivenUpOn : Int -> Bool
gateHasBeenGivenUpOn askedReadings =
    gateRefusesThisShipTicks < askedReadings


gateActivationStep : GateActivationCase -> GateActivationStep
gateActivationStep gateCase =
    if gateHasBeenGivenUpOn gateCase.askedReadings then
        GiveUpOnThisGate

    else if not gateCase.panelShowsTheGate then
        SelectTheGate

    else if gateCase.panelOffersActivateGate then
        PressActivateGate

    else
        WaitForTheActivateButton


{-| The give-up, which says what is known and stops there.

It used to say the gate "most likely will not admit this ship", and that
inference is wrong whenever the mechanism is what failed -- which is what run 4
was: 30 completed context-menu cascades clicking `Activate Gate` on an
`Ancient Acceleration Gate` at under 2,000 m, the gate never opening, and the
client's game log carrying **no** refusal of any kind. A sentence naming a ship
restriction sends an operator to look at the hull, and the hull was not what the
evidence pointed at.

So the wording names the three readings this bot cannot tell apart and says the
client is silent, which is the fact that makes them indistinguishable from here.
The client does have a sentence for a gate that wants an item -- the mission
runner reads `This gate is locked! ... in your cargo hold` off the `info`
channel -- and its absence here is why nothing stronger can be claimed.

**It is a status clause rather than a decision line, because the branch now hands
the turn back** -- see `activateAccelerationGateIfPresent`, which answers
`Nothing` here so the caller's own fallbacks run. A `Nothing` cannot carry a
decision line, and the mission runner records what that costs unreported: its own
gate branch gave up on a gate 32 m away and the log said only that nothing was
happening, 1,325 times. So this goes out in the status line on every reading
instead, where it is visible while it is happening.

-}
describeGateGaveUp : Int -> String
describeGateGaveUp askedReadings =
    "I have been asking this acceleration gate to open for "
        ++ String.fromInt askedReadings
        ++ " readings -- selecting it and pressing the panel's Activate Gate where it offers one -- and it has not taken me anywhere. The client has said nothing at all, so I cannot tell a gate that will not admit this ship from one whose button is not landing. Stopping rather than asking it any longer, and letting the rest of the decision tree have the reading."


{-| The gate clause in the status line.

`stall_watch.py` reads decision lines and this is not one; what it is for is an
operator watching a run, who could previously see only a count of readings spent
near a gate and had no way to tell that from readings spent asking one.

Past the bound it carries the give-up itself, for the reason `describeGateGaveUp`
gives: the branch declines rather than deciding there, so this line is the only
thing on the reading that says a gate has been given up on.

-}
describeGateActivationAsk : { asked : Bool, gateWithinReach : Bool, askedReadings : Int } -> String
describeGateActivationAsk gateCase =
    "Readings spent asking an acceleration gate to open: "
        ++ String.fromInt gateCase.askedReadings
        ++ " of "
        ++ String.fromInt gateRefusesThisShipTicks
        ++ (if gateHasBeenGivenUpOn gateCase.askedReadings then
                " -- " ++ describeGateGaveUp gateCase.askedReadings

            else if gateCase.asked then
                " (asking now)"

            else if gateCase.gateWithinReach then
                " (a gate is in reach, not being asked)"

            else
                ""
           )


{-| The acceleration gate this bot acts on, if the overview is showing one.

One definition rather than two, because the status line speaks about the gate the
branch decided about: `describeDistantGate` reports an ignored one, and a second
copy of "which gate" here would let the line and the decision disagree about
which gate that was.

Rows that are not `_display`ed are dropped first. A virtualised row keeps a
plausible region belonging to whatever was recycled into its place, so it can
neither be clicked nor believed about its range.

-}
nearestAccelerationGateOnOverview :
    ReadingFromGameClient
    -> Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
nearestAccelerationGateOnOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.filter overviewEntryIsDisplayed
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.head


{-| Past how many metres an acceleration gate stops being somewhere to fly to.

A gate this far away is not a gate to fly to; it is evidence that something else
went wrong -- the grid was not cleared, the wrong object was picked, or the bot
is looking at a gate on someone else's grid -- and flying at it converts one
mistake into a whole session. Run 51 spent four hours closing on one at
1,395,000 m, returning about 122,500 ISK an hour against the 1.36M saxrat was
measured at. Nothing bounded the approach, because nothing thought a distance
could be absurd, and `gateWithinReachTicks` could not: that counter is for a gate
_in reach_ that will not open and only advances inside `interactionRangeInMeters`,
which a gate 1,395 km away never enters.

**The separation is between what a real gate has ever measured and everything
above it.** These counts are issue #168's, over every
`acceleration gate is N m away` line in `~/eve-bot-logs` with the AU placeholder
excluded, and are cited rather than re-derived here:

    source                  readings   furthest gate
    ---------------------   --------   -------------
    24 mission runs            1,385        77,000 m
    saxrat run 49              3,503       314,000 m
    mission run 51            11,200     1,395,000 m

So across twenty-four mission runs the furthest gate ever seen is 77,000 m, and
run 51's is eighteen times that. 150,000 sits in that gap at roughly twice
anything ever observed working.

**300,000 was the number the issue was filed at, and its own measurement argues
lower.** saxrat's run 49 reached 314,000 m with 1,629 readings above 150 km and
only 196 above 300 km, so a 300 km rule catches a tenth of that run's long-gate
readings and leaves the rest -- and run 49 is not a healthy control either, at
770k ISK/hr against run 48's 1,357k on identical code, with 28
`askForHelpToGetUnstuck` alarms. The issue files 300 km as "the safe choice; it
is not necessarily the effective one" and puts the real gap at 100-150 km.
150,000 is the top of that range, which is its conservative end.

**It is a number about how these sites are laid out, not about the game**, the
same warning `defaultRunAwayIncomingDamageThreshold` carries about a hull. A site
type whose gates are genuinely further out than this would need it re-derived,
and until it is the bot would ignore a gate it ought to fly to. What makes that
recoverable rather than silent is that the status line names the gate, its range
and this number on every reading it declines one, so the evidence for a retune is
in the log and the retune is one edit.

-}
distantAccelerationGateMeters : Int
distantAccelerationGateMeters =
    150000


{-| Whether the nearest acceleration gate is somewhere to fly to at all.

A pure function over the overview row's own `objectDistanceInMeters` so a case
can execute it, and over the `Result` rather than over the `999999` fallback
every other consumer of an overview distance takes, so that the two ways of not
being a gate to fly to stay apart.

That fallback stands in for a distance the client wrote in AU, and it is past any
threshold this could carry -- so a rule reading it would decline such a row for
the right reason under the wrong sentence, and an operator reading "past 150000
m" would go looking for a gate that is far away rather than for one whose range
did not parse. "Reading the overview" is why an AU distance is excluded on its
own terms: it is the unparsed-distance placeholder rather than a distance, and
nothing the ship might act on may be chosen on it.

-}
type DistantGateVerdict
    = GateIsCloseEnoughToFlyTo Int
    | GateIsTooFarToBeSomewhereToFlyTo Int
    | GateDistanceDoesNotReadAsARange


distantGateVerdict : Result String Int -> DistantGateVerdict
distantGateVerdict distanceRead =
    case distanceRead of
        Err _ ->
            GateDistanceDoesNotReadAsARange

        Ok distanceInMeters ->
            if distantAccelerationGateMeters < distanceInMeters then
                GateIsTooFarToBeSomewhereToFlyTo distanceInMeters

            else
                GateIsCloseEnoughToFlyTo distanceInMeters


{-| The ignored-gate clause in the status line.

Empty on the ordinary reading, where the gate is one to fly to and the status
line's own gate clause already covers it.

**A decline this branch does not say out loud is this repo's signature failure**,
and the gate branch has already paid for it once: run 10's give-up answered
`Nothing` about a gate 32 m away and the log said only that nothing was
happening, 1,325 readings running. A gate plainly on the overview that the bot
stops acting on reads to the next operator as a bot that has gone blind to gates,
so this says which of the two verdicts it is, at what range, and against what
number -- which is also the evidence a retune of that number would rest on.

-}
describeDistantGate : DistantGateVerdict -> String
describeDistantGate verdict =
    case verdict of
        GateIsCloseEnoughToFlyTo _ ->
            ""

        GateIsTooFarToBeSomewhereToFlyTo distanceInMeters ->
            " IGNORING the nearest one: "
                ++ String.fromInt distanceInMeters
                ++ " m is past the "
                ++ String.fromInt distantAccelerationGateMeters
                ++ " m this bot will fly at a gate, so it is evidence something else went wrong rather than somewhere to go. Leaving it alone and letting the rest of the decision tree have the reading."

        GateDistanceDoesNotReadAsARange ->
            " IGNORING the nearest one: its distance does not read as a range in m or km, which is the unparsed-distance placeholder rather than a distance, so there is nothing here to fly to. Leaving it alone and letting the rest of the decision tree have the reading."


{-| Takes the nearest acceleration gate, to move on to the next pocket.

**A gate far enough away is ignored before any of that**, which is
`distantGateVerdict` and is asked first. It is not a give-up on the grid: the
answer is `Nothing`, so `siteProgressStep` hands the reading to the hunt loop,
and the status line says which gate was ignored and why.

**In range this presses the Selected Item panel's own `selectedItemActivateGate`
rather than driving a context-menu cascade**, which is what it did before and
what the mission runner's `activateGateOnOverviewEntry` records the argument
against. That comment's evidence is a live one: on the very gate that had
refused 124 D-clicks, the panel button took the ship through -- the objective
went from "You need to activate the Acceleration Gate" to "Warping" and the
overview turned over from 17 rows to 22. Where the panel offers a named button,
press it rather than reaching for a keybind or a cascade.

saxrat's own evidence is thinner than the give-up count suggests, and the honest
version is worth having here rather than in a pull request nobody re-reads. Its
two newest runs carry 829 `has not taken me anywhere` lines, but that give-up
prints on every reading once the bound is passed, so 829 lines are **two**
in-reach episodes -- one per run, and the only two in the whole recorded corpus
that ever passed 40. Only run 4's is this mechanism failing: 30 completed
cascades clicking `Activate Gate` on an `Ancient Acceleration Gate` inside
2,000 m, the gate never opening, no refusal on any game-log channel, and then
238 readings of the give-up before the bot went back to ratting. Run 5's is not
about the mechanism at all -- see `askingAnAccelerationGateToOpen`, whose counter
this changes for that reason. No saxrat run has ever demonstrably taken a gate:
run 3 has the only sub-bound episodes and each of those ends in a retreat or in
a warp that the "Warp to Site" branch firing in the same window can equally
explain.

So this is one gate's worth of evidence for a mechanism that is proven elsewhere,
not 829 failures, and it is scoped as such.

Two ticks by design, `selectThenPanelAction`'s shape: the panel acts on whatever
is selected, so this presses the button only once the panel is showing the gate
and otherwise spends a tick selecting it. That cannot act on the wrong object,
where a cascade fired at a re-sorted overview row can.

**The out-of-range branch is deliberately untouched.** From further out the same
"Activate Gate" command is what gets issued: the
client flies the ship in and takes the gate on arrival, so the bot never spends
a tick sitting at the gate working out that it has arrived. That leaves no
arrival step to prepare in, so whatever has to be settled before the ship leaves
has to be settled before the command goes out.

Which is only the drones (`ensureDronesRecalledBeforeWarping`), not the
propulsion module, unlike every other warp this bot makes. Preparing the prop
mod up front would mean crawling the whole way to the gate with it off, and the
gate is often tens of km away. Leaving it running costs a slower align into the
gate's own warp; that is the cheaper end of the trade and the one deliberately
chosen here. Drones get no such choice -- ones left in space stay in the old
pocket.

The panel carries `selectedItemActivateGate` only while the gate is in range, so
the button's absence out there is the natural gate between the two mechanisms --
the same argument `dockAtDestinationStation` makes in the mission runner. There
is nothing to press from 40 km away, and the command that flies the ship in is
one the cascade does land.

-}
activateAccelerationGateIfPresent : BotDecisionContext -> Maybe DecisionPathNode
activateAccelerationGateIfPresent context =
    case nearestAccelerationGateOnOverview context.readingFromGameClient of
        Nothing ->
            -- Either there is no gate at all, or the only one is scrolled out
            -- of the overview -- where its reported region belongs to whatever
            -- row is recycled into its place, so it cannot be clicked.
            scrollOverviewToReveal context isAccelerationGate

        Just accelerationGateEntry ->
            case distantGateVerdict accelerationGateEntry.objectDistanceInMeters of
                GateIsTooFarToBeSomewhereToFlyTo _ ->
                    -- A gate this far out is not a gate to fly to; it is
                    -- evidence something else went wrong, and the mission
                    -- runner's run 51 spent four hours converting that into a
                    -- whole session. See `distantAccelerationGateMeters` for
                    -- where the number comes from and what it is a number
                    -- about.
                    --
                    -- Ignoring the gate rather than giving up on the grid: the
                    -- same `Nothing` `GiveUpOnThisGate` answers below, so
                    -- `siteProgressStep` sends the reading to the hunt loop and
                    -- the bot goes back to ratting. Answering
                    -- `askForHelpToGetUnstuck` here would swap a four-hour
                    -- chase for a four-hour alarm, which is the give-up this
                    -- branch has already stopped doing once.
                    --
                    -- Silent by construction, which is the one thing this may
                    -- not be: `describeDistantGate` carries it in the status
                    -- line on every reading instead.
                    Nothing

                GateDistanceDoesNotReadAsARange ->
                    -- An AU distance is the unparsed-distance placeholder
                    -- rather than a distance, so this row says nothing about
                    -- where the gate is. Declined on its own terms rather than
                    -- as a large number, since the two want different sentences
                    -- in the status line.
                    Nothing

                GateIsCloseEnoughToFlyTo distanceInMeters ->
                    let
                        activateGateButton =
                            selectedItemButtonNamed context.readingFromGameClient "selectedItemActivateGate"

                        waitForTheActivateButton =
                            describeBranch
                                "The acceleration gate is selected but the panel offers no 'selectedItemActivateGate' yet."
                                waitForProgressInGame
                    in
                    if interactionRangeInMeters < distanceInMeters then
                        -- "Activate Gate" from out here does the whole thing: the
                        -- client flies the ship over and takes the gate on arrival,
                        -- with no tick spent noticing it has arrived. The drones
                        -- come home first, since the gate fires with whatever is
                        -- still in space; the prop mod stays on, so the ship covers
                        -- the distance fast.
                        Just
                            (ensureDronesRecalledBeforeWarping context
                                (closeInOnOverviewEntry context
                                    { description =
                                        "The acceleration gate is "
                                            ++ String.fromInt distanceInMeters
                                            ++ " m away -- activate it from here and let the client fly me in."
                                    , menuEntries = [ "activate gate", "activate", "approach" ]
                                    }
                                    accelerationGateEntry
                                )
                            )

                    else
                        case
                            gateActivationStep
                                { panelShowsTheGate =
                                    selectedItemIsOverviewEntry context.readingFromGameClient accelerationGateEntry
                                , panelOffersActivateGate = activateGateButton /= Nothing
                                , askedReadings = context.memory.gateWithinReachTicks
                                }
                        of
                            GiveUpOnThisGate ->
                                -- Hand the turn back rather than park the session. This
                                -- used to answer `askForHelpToGetUnstuck`, which
                                -- dispatches nothing and waits, so run 4 spent 238
                                -- readings and the rest of its session standing at a
                                -- gate that was never going to open. The mission
                                -- runner's copy of this branch already answers `Nothing`
                                -- for the same reason, and the fallbacks it hands the
                                -- reading to are what this bot needs too: the hunt loop,
                                -- which is the recovery run 4 eventually made anyway.
                                --
                                -- `siteProgressStep` is what keeps that from becoming
                                -- run 5's dead click -- a "Warp to Site" offered while
                                -- this gate is still in reach is the panel showing the
                                -- site the ship is standing in, so the reading goes to
                                -- the scanner rather than to the button.
                                --
                                -- Silent by construction, which is the one thing this may
                                -- not be: `describeGateActivationAsk` carries the give-up
                                -- in the status line on every reading instead.
                                Nothing

                            SelectTheGate ->
                                Just
                                    (describeBranch
                                        "I see an acceleration gate -- select it, so the panel's own Activate Gate acts on it."
                                        (clickUiElement accelerationGateEntry.uiNode)
                                    )

                            WaitForTheActivateButton ->
                                Just waitForTheActivateButton

                            PressActivateGate ->
                                Just
                                    (activateGateButton
                                        |> Maybe.map
                                            (\button ->
                                                -- Wrapped in `unlessAlreadyClosingIn`
                                                -- like every other close-in command: EVE
                                                -- flies the ship the last of the way and
                                                -- takes the gate on arrival, so
                                                -- re-issuing this while that is running
                                                -- restarts the manoeuvre.
                                                unlessAlreadyClosingIn context
                                                    "I see an acceleration gate -- activate it to move to the next pocket."
                                                    (ensureDronesRecalledBeforeWarping context
                                                        (clickUiElement button)
                                                    )
                                            )
                                        |> Maybe.withDefault waitForTheActivateButton
                                    )


{-| How many readings to keep asking a gate that is already in range before
giving up on it. A working gate goes through in a few; the mission bot hit one
that would not open and clicked it 741 times over half an hour, with no error
dialog and nothing to notice.

**Still 40 now that the branch is genuinely reachable, and the argument for it
has changed.** #148 kept the number on saxrat's own peaks -- 1, 5, 6, 8, 10, 15
and 18 against 282 and 3,504 -- and called that "an order of magnitude of
clearance on both sides". Those peaks do not support it: every one of them was
counted on _proximity_ under #147's shadowing, which is the quantity that PR's
own change argued was the wrong one, and the two large ones are a ship standing
beside a gate it never asked. A distribution of readings-spent-near cannot size a
budget for readings-spent-asking.

**The mission runner's corpus can, because its gate branch is the one that gets
asked.** Taking every episode across its 37 runs where the nearest gate came
inside `interactionRangeInMeters`, and counting the readings spent there before
the ship went into warp: **89 of 93 episodes ended in a warp, and 88 of those had
spent 0 to 4 readings in reach**, the great majority of them 0 -- the client
takes the gate on the approach, so the ship is usually already warping by the
reading the overview reads 2,000 m. The longest that still opened spent **15**.
At the other end, the largest count that corpus records on a gate its own branch
gave up on is **335** -- of readings the panel offered and the gate did not open,
which is a wider condition than this counter's and so if anything an
underestimate of how far a genuine failure runs.

So the gap is real and its edges are 15 and 335 rather than 18 and 282. 40 sits
inside it at 2.7 times the largest recorded success and an eighth of the recorded
failure, which is the clearance that was claimed -- on the other bot's evidence,
and only on the near side of it.

**Being early costs less than it used to, which is the other half.** The give-up
no longer parks the session: it answers `Nothing` and the hunt loop takes the
reading, so a gate abandoned one reading too soon costs a pocket rather than the
rest of the run. Being late costs idle readings at a dead gate. Neither argues
for moving a number that no recorded episode of either kind comes near.

-}
gateRefusesThisShipTicks : Int
gateRefusesThisShipTicks =
    40


{-| What to do with a grid the probe scanner no longer names an anomaly on:
take the acceleration gate, warp to an offered site, or go back to hunting.

A pure function over a record so a case can execute it, because the ordering is
what was wrong. `pickAnotherAnomalyOrLeave` asked
`warpToOpportunitySiteIfAvailable` first and `activateAccelerationGateIfPresent`
only where that answered `Nothing` -- and the first answers `Just` whenever a
"Warp to Site" button is anywhere in the tree, which stays true after the ship
has arrived, so the gate branch was unreachable inside the very sites it exists
to follow.

**The whole-tree search cannot tell "an opportunity exists" from "we are not
there yet", and the grid can.** The button is drawn identically before and after
arrival and the client says nothing when it is clicked in the stale state, so
there is no reading of the panel that separates them.

**#200 removed the search and the panel can now answer that after all**, which
narrows this argument without retiring it: the tracker's own button carries a
_label_, and it reads `Warping` once the ship is under way, so
`warpToOpportunitySiteIfAvailable` declines the state run 5 spent 3,458 readings
in. The clause below stays for the readings where the label is silent -- a
tracker the parser cannot read, an escalation nobody has expanded, a word the
client has invented -- and because #147's ordering is a claim about work rather
than about a search: a gate on the grid is the job in front of the ship whatever
the panel says. Run 5's measurement is what the ordering rests on and stands as
recorded.

An acceleration gate is a
different question with the same answer: gates exist only inside sites, so one on
the overview means the ship has already arrived somewhere, and every recorded
opportunity episode agrees --

  - **Three began with a gate already in reach** (run 3 line 124489, run 4 line
    23016, run 5 line 101277) and **not one of them ever produced a warp**. Two
    ended within a handful of readings when the button went away and the gate
    branch finally got its turn. Run 5's ran **3,458 readings**, about 75 minutes
    of a three-hour session, clicking one screen position 3,460 times with the
    overview, the combat feed and the counter's own in-reach run all unbroken
    throughout -- and it ended only when a person warped the ship by hand.
  - **The two that began with no gate in reach** (run 4 line 21172, run 5 line
    1.  were in warp within three readings.

**The client never answered the stale click**, which is what rules out asking it
instead: not one on-screen quick message in the whole of run 5's episode, against
dozens of distinct wordings elsewhere in that run. There is nothing to match on.

So the gate is asked first, **and** the warp branch declines while a gate is in
reach. That second half is not redundant with the ordering: once
`activateAccelerationGateIfPresent` gives up on a gate it answers `Nothing`, and
without the clause the very next reading would fall into run 5's dead click with
nothing left to bound it. Declining sends it to the hunt loop instead, which is
the recovery run 4 eventually made on its own after 238 wasted readings.

**#147's ordering is reversed for an arrival, and for nothing else.** That
argument is about a label the ship has not travelled to yet: `Jump` and
`Set Destination` are the tracker offering to leave for a site somewhere else,
and a gate on the grid is work inside the site the ship is already in, so the
gate wins. An **arrival** -- `opportunityArrivalCommandLabels`, which is
`warp to site`, `warp to location` and `dock` -- is not that. It is the client
saying the escalation is reachable from where the ship is standing, and it is
the step run 38 pressed `Jump` 1,989 times instead of taking (#256). So
`arrivalIsOffered` is asked **above** the gate, and the travelling case keeps
`not gateWithinReach` exactly as #147 wrote it. Nothing about a `Jump` moved.

**The scope of the reversal is one tier and the rest of #147 stands**: a gate
still outranks a travelling step, still outranks the hunt loop, and is still
consulted with no reference whatever to the scanner window.

**`arrivalIsOffered` is the narrower of the two inputs and `warpToSiteIsOffered`
is not what its name says.** That one is true for _any_ label the tracker offers
that the branch would click, `Jump` and `Set Destination` included -- it is
named after the one word the whole-tree search this branch replaced used to look
for. The new input is the one that means what it says: the entry the branch
would press carries an arrival label. Where an arrival is on offer both are
true, so the tiers are ordered rather than exclusive.

**Both still outrank the probe-scan hunt loop**, which is all the comment at the
call site ever claimed and is compatible with either order -- what it never said
is which of the pair wins, and the code answered "the first one, always" because
its condition is almost always true. `HuntWithTheProbeScanner` is reached only
where the gate branch has nothing to do and the button is either absent or being
offered to a ship that is standing on a gate.

**The opportunity is taken only while the probe scanner window is closed**, and
that clause is an operator's switch rather than a reading of the site. Closing
the scanner is a deliberate act nothing in the client does on its own, so it is
the one thing on a reading that can carry an intent: with it closed the bot goes
and works escalations, with it open it hunts locally. It is a hard gate and not a
preference -- with the window open the tracker's step is not taken at all,
whatever the panel is offering. **The arrival tier carries the same clause**, so
the switch is one switch: an arrival with the scanner open is declined exactly as
a travelling step is, and the reading falls through to the gate.

**How rarely the arrival tier will be reached is measured rather than hoped
for.** Recounted over every `saxrat_run*.log` this machine holds -- 49 of them --
the scanner window was open on **139,904 in-space readings against 1,856 shut**,
**31 of the 47 runs that reached space never closed it once**, and of the 3,926
readings that ever took an opportunity step **exactly one** had it shut. So
until somebody flies with the scanner closed on purpose this tier is close to
unreachable. That was measured before it was built and chosen with the caveat
stated: the switch is what makes the escalation work deliberate, and a fallback
that fired the tier anyway would be the switch not existing.
`test_saxrat_opportunity_needs_the_probe_window_closed.py` recounts those as
relations, so a growing corpus cannot turn the claim red.

**Only the opportunity is gated.** `WorkTheAccelerationGate` does not consult the
scanner window at all, in either direction: a gate on the grid is the job in
front of the ship whether or not anybody has a scanner open, and #202 and #204
are what a scanner window deciding the gate's visibility costs.

-}
type SiteProgressStep
    = WorkTheAccelerationGate
    | WarpToTheOpportunitySite
    | HuntWithTheProbeScanner


siteProgressStep :
    { gateBranchOffersAStep : Bool
    , arrivalIsOffered : Bool
    , warpToSiteIsOffered : Bool
    , gateWithinReach : Bool
    , probeScannerWindowIsClosed : Bool
    }
    -> SiteProgressStep
siteProgressStep progressCase =
    if progressCase.arrivalIsOffered && progressCase.probeScannerWindowIsClosed then
        WarpToTheOpportunitySite

    else if progressCase.gateBranchOffersAStep then
        WorkTheAccelerationGate

    else if
        progressCase.warpToSiteIsOffered
            && progressCase.probeScannerWindowIsClosed
            && not progressCase.gateWithinReach
    then
        WarpToTheOpportunitySite

    else
        HuntWithTheProbeScanner


{-| `siteProgressStep`, resolved against the reading, with what to do when it
answers neither.

**The reason this is a function rather than a `let` in one branch: it used to be
one, and the probe-scanner branch was that branch.** `decideNextActionWhenInSpace`
splits on `probeScannerWindow`, and both steps were bound inside the `Just` arm,
so a shut scanner window made a gate standing on grid and a "Warp to Site" on
offer equally invisible -- see #204 and #202. The steps were reachable code that
nothing could reach.

The caller supplies the floor, which is the only thing that legitimately differs:
the scanner branch falls back to its own scan results, and the branch without a
scanner falls back to leaving the system. Neither can now grow a repertoire the
other silently lacks.

**The scanner window decides the opportunity step, which is a coupling this very
function was written to remove -- deliberately, and in the opposite polarity.**
#202 and #204 are about a **closed** window hiding both steps: a shut scanner
made a gate standing on grid and a "Warp to Site" on offer equally invisible,
which is the reachable-code-nothing-could-reach defect above. What
`probeScannerWindowIsClosed` does is the reverse -- closed _enables_ the
opportunity, and a window nobody has touched leaves the bot hunting exactly as it
does today. So no step is hidden by a reading the operator did not choose, and
`siteProgressStep` still gives the gate no scanner clause in either direction:
a shut scanner can move the gate down one place, and no reading of the window can
make it invisible.

**`arrivalIsOffered` is derived from the tracker's parsed entries and not from a
search.** `opportunityTravelStep` is the same read the click itself is aimed at,
and `opportunityStepArrivingFirst` already prefers an arrival over a travelling
step -- so the step whose label is asked about here is exactly the step
`WarpToTheOpportunitySite` would press. That is what keeps the tier and the click
from disagreeing about which entry the panel is offering, and it is why the
answer cannot come from `findUiElementWithText`, which is the whole-tree search
#252 removed and which answered `Just` on a panel the ship had already arrived
at.

**Declining is not a wait, which is the property to keep, and the new tier makes
it matter more.** Every answer this function can give runs a branch: an arrival
declined for an open scanner falls through to the gate and then to `ifNeither`,
which is the hunt loop or leaving the system. And the arrival answer cannot
decline: `arrivalIsOffered` is read off the very step `opportunityWarpStep`
carries, so the `Maybe.withDefault ifNeither` beside it is unreachable rather
than load-bearing. PR #257 put an unbounded wait on this exact path and stopped
the bot dead for 108 minutes; nothing here may become one.

**Where this is reached is what keeps it safe.** `decideActionInAnomaly` asks for
its continuation only once there is nothing left to attack, loot or unlock, so an
opportunity appearing mid-fight still cannot pull the ship out of one.

-}
siteProgressStepOrElse : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
siteProgressStepOrElse context ifNeither =
    let
        accelerationGateStep =
            activateAccelerationGateIfPresent context

        opportunityWarpStep =
            warpToOpportunitySiteIfAvailable
                (escalationEntriesPermitted context.eventContext.botSettings context.readingFromGameClient)

        arrivalIsOffered =
            opportunityTravelStep
                (escalationEntriesPermitted context.eventContext.botSettings context.readingFromGameClient)
                |> Maybe.map (.label >> opportunityLabelArrivesAtTheSite)
                |> Maybe.withDefault False
    in
    case
        siteProgressStep
            { gateBranchOffersAStep = accelerationGateStep /= Nothing
            , arrivalIsOffered = arrivalIsOffered
            , warpToSiteIsOffered = opportunityWarpStep /= Nothing
            , gateWithinReach = accelerationGateIsWithinReach context.readingFromGameClient
            , probeScannerWindowIsClosed = context.readingFromGameClient.probeScannerWindow == Nothing
            }
    of
        WorkTheAccelerationGate ->
            accelerationGateStep |> Maybe.withDefault ifNeither

        WarpToTheOpportunitySite ->
            opportunityWarpStep |> Maybe.withDefault ifNeither

        HuntWithTheProbeScanner ->
            ifNeither


{-| The step the Opportunities tracker is offering, where it is offering one the
bot may take.

**The tracker draws one button whose label changes with what the trip needs**,
and this used to be a whole-tree text search for one of that label's values.
Read off the live client with five `Sansha's Command Relay Outpost` escalations
in the panel, the widget renders `Jump` while the destination is several jumps
out, `Warping` once the ship is under way, `Warp to Site` in system, and
`Set Destination` before a route exists. So `Warp to Site` was one value of four
and the other three were invisible: runs 25 and 26 made 44 and 168 route-panel
stargate jumps between them and used the tracker **zero** times.

**Adding `Jump` to the old search is the wrong fix and that is why this is a
parse.** The Selected Item panel carries its own `Jump` button -- read live at
canvas (1517,142) in the same reading, and the one `selectedItemJump` presses --
so a whole-tree search for that word collides with it on the first reading and
nothing afterwards can say which was clicked. Matching on the widget's own type
name, inside a `DungeonInfoPanelEntry`, cannot reach the panel at all.

Three things decide whether a label is a step, and each excludes a different
failure:

  - **It has to be text the client rendered** (`travelLabelIsReadableText`).
    Run 11 on the mission runner rendered a travel step as six C0 control
    characters around one unassigned codepoint, and run 22 as a distance wrapped
    in NULs. Accepting anything is the only way this change could send a ship
    somewhere nobody asked for.
  - **It has to be a command rather than a state** (`travelLabelIsACommand`).
    `Warping`, `Jumping` and `Docking` are the client saying the trip is already
    happening; clicking one is re-commanding a manoeuvre already under way, which
    is #99's docking run-in with a different button.
  - **The button has to be one the client is showing.** That is the parser's
    `_display` filter, where it belongs -- the chain hides the tasks that are not
    available rather than removing them.

**#147's ordering is untouched for a travelling label and reversed for an
arrival**, which is a distinction this function is what makes readable. `Jump`
and `Set Destination` are the ship leaving for a site somewhere else, so
`siteProgressStep` still asks the acceleration gate first and still declines
them while a gate is in reach: a gate is progress _inside_ the site and those
labels are how the ship reaches the next one. `opportunityArrivalCommandLabels`
is the ship arriving at a site it is already in the system for, and that is
asked above the gate. What does change for both is that the old search's own
premise no longer holds -- it answered `Just` whether or not the ship had
arrived, and the label answers `Warping` once it has, so the panel now separates
the two states the grid was brought in to separate. The gate clause stays on the
travelling case anyway, because it is what bounds this branch on a reading whose
label the parser could not read.

-}
opportunityTravelStep :
    ReadingFromGameClient
    ->
        Maybe
            { siteName : Maybe String
            , label : String
            , buttonNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
            }
opportunityTravelStep readingFromGameClient =
    readingFromGameClient.opportunityInfoPanelEntries
        |> List.filterMap
            (\entry ->
                entry.travelButton
                    |> Maybe.andThen
                        (\button ->
                            button.label
                                |> Maybe.andThen
                                    (\label ->
                                        if travelLabelIsACommand label then
                                            Just
                                                { siteName = entry.siteName
                                                , label = label
                                                , buttonNode = button.uiNode
                                                }

                                        else
                                            Nothing
                                    )
                        )
            )
        |> opportunityStepArrivingFirst


warpToOpportunitySiteIfAvailable : ReadingFromGameClient -> Maybe DecisionPathNode
warpToOpportunitySiteIfAvailable readingFromGameClient =
    opportunityTravelStep readingFromGameClient
        |> Maybe.map
            (\step ->
                describeBranch
                    ("The Opportunities tracker offers '"
                        ++ step.label
                        ++ "' for "
                        ++ (step.siteName |> Maybe.withDefault "an escalation it does not name")
                        ++ " -- take it."
                    )
                    (clickUiElement step.buttonNode)
            )


{-| Whether the tracker's travel label names a step to take, rather than one
already under way or a word nobody has seen this button carry.

**An allow-list rather than a list of the states to refuse**, which is the
direction this rule chooses and the deliberate part. A deny-list fires on
anything the client's vocabulary grows next, and that vocabulary has already
grown twice without anyone deciding to -- `View Details` is on a collapsed
escalation in the very capture this was written from, and it is not a trip. So a
label nobody has read leaves the bot behaving exactly as it did before this
change, which is a route-panel stargate cascade rather than a click into a panel
listing several escalations.

The five words this list originally had are the ones the mission runner's own
`missionTravelStep` sorts as commands -- `Set Destination`, `Jump`,
`Warp to Location`, `Dock` -- plus `Warp to Site`, which is what this branch has
been matching all along. `Dock` has never been read off _this_ widget and is
carried on the strength of that separation rather than on an observation here.

**`Undock` was missing, and it is read off this widget** -- captured live from
saxrat run 6, docked at Nafomeh with an escalation tracked: the panel's own
travel step read `Undock` in as many words, and this list not carrying the word
meant `travelLabelIsACommand` answered `False` for it regardless of what else
was true. Combined with `escalationDestinationIsPermitted`'s own gap on the same
run (see its comment), the escalation was invisible from both directions at
once -- the docked branch's `warpToOpportunitySiteIfAvailable == Nothing` check
never saw a reason to undock, and once undocked by another route entirely, the
next step (`Warp to Site`, which _was_ on this list) still could not be reached
because the entry never survived the destination filter to be asked about.

Compared case-insensitively on the trimmed label, so a client that changes its
capitalisation does not switch the branch off; the comparison is still an
equality, so it cannot widen to a different word the way a substring test would
take `Dock` out of `Dock in Station`.

-}
travelLabelIsACommand : String -> Bool
travelLabelIsACommand label =
    travelLabelIsReadableText label
        && (opportunityTravelCommandLabels
                |> List.member (label |> String.trim |> String.toLower)
           )


opportunityTravelCommandLabels : List String
opportunityTravelCommandLabels =
    [ "set destination", "jump", "warp to site", "warp to location", "dock", "undock" ]


{-| Of the steps the tracker is offering, the one that gets the ship _into_ a
site, preferring it over one that travels somewhere else.

`List.head` was the whole of this, and with several escalations open it is not a
choice at all -- it takes whichever entry the panel happens to list first. Run 38
is what that costs. The panel held three `Sansha's Command Relay Outpost`
entries; the ship arrived in the system holding one of them, where that entry
offers `Warp to Site`; and the branch took the _first_ entry's `Jump` instead and
travelled on. Over three hours it pressed `Jump` 1,989 times and
`Set Destination` 257, **never once warped to a site**, crossed from Domain into
Kor-Azor, and finished the session having visited two anomalies.

The ordering is between the two kinds of label rather than between entries: a
warp or a dock is the ship arriving at a site it is already in the system for,
where `jump` and `set destination` are it leaving for another one. Arriving wins,
because arriving is what the travelling was for.

**It is a preference, not a filter.** With nothing arriving on offer the answer
is the first travelling step exactly as before, so a run with one distant
escalation behaves as it does today.

-}
opportunityStepArrivingFirst :
    List { siteName : Maybe String, label : String, buttonNode : a }
    -> Maybe { siteName : Maybe String, label : String, buttonNode : a }
opportunityStepArrivingFirst offered =
    case offered |> List.filter (.label >> opportunityLabelArrivesAtTheSite) of
        arriving :: _ ->
            Just arriving

        [] ->
            offered |> List.head


opportunityLabelArrivesAtTheSite : String -> Bool
opportunityLabelArrivesAtTheSite label =
    opportunityArrivalCommandLabels
        |> List.member (label |> String.trim |> String.toLower)


{-| The subset of `opportunityTravelCommandLabels` that ends travelling.

Read off the same widget as the rest: `Warp to Site` is what the panel showed
beside the outpost the ship had reached in run 38's own screenshot, while `Jump`
and `Set Destination` are what it showed for the two it had not.

-}
opportunityArrivalCommandLabels : List String
opportunityArrivalCommandLabels =
    [ "warp to site", "warp to location", "dock" ]


{-| Whether the tracker's travel label is something the client rendered for a
person to read.

Ported from the mission runner, where the corpus is. Run 11 there rendered a
travel step three times as the codepoints `U+0002 U+0000 U+AD1D8 U+0001 U+0001
U+0000 U+0001` -- six C0 controls around one codepoint that is unassigned
(category `Cn`, plane 10) rather than private-use, which is the trap: a rule
recognising "not text" by private-use membership calls that text. Run 22
rendered one as `U+0000 U+0000 . 5 0 space A U U+0000`, a distance readout
wrapped in NULs.

The test is printable ASCII with at least one letter in it. Every label either
bot has recorded on this widget is ASCII, and neither non-text one is: the first
has no printable character at all, the second has letters with NULs around them.

The cost is stated rather than hidden: a client rendering this button in a
non-Latin script disables the branch entirely and the bot travels by route panel
as it does today. That is the safe direction, and it is the same assumption the
rest of this file already makes about the client's language.

`travelLabelIsACommand`'s allow-list already refuses both recorded non-text
labels on its own, since neither trims to one of five English words. This is kept
in front of it deliberately: it is the clause that would still hold if that list
were ever widened, and it is the one this file can point at when asked where
unreadable input is declined.

-}
travelLabelIsReadableText : String -> Bool
travelLabelIsReadableText label =
    let
        trimmed =
            String.trim label

        characterIsPrintableAscii character =
            let
                code =
                    Char.toCode character
            in
            0x20 <= code && code <= 0x7E
    in
    not (String.isEmpty trimmed)
        && String.all characterIsPrintableAscii trimmed
        && String.any Char.isAlpha trimmed


{-| The rank words that mark a rat whose wreck is worth looting. See
`isNotableWreck` for why this is a list and why "leader" is safe as a substring.
-}
notableRatRankWords : List String
notableRatRankWords =
    [ "commander", "overseer", "leader" ]


{-| A rank-bearing rat's wreck, worth sticking around to loot before leaving
the anomaly. Checks both name and type since which one carries the rank seems
to vary; requires "wreck" in the type so we don't also match the (still-living)
rat itself while it's on the overview.

**The rank words are a list because EVE does not use one word.** "commander"
and "overseer" alone silently skipped `Sansha Black Ops Squad Leader`, whose
wreck is worth exactly as much as the `Centus Black Ops Commander` beside it --
reported live, and the recorded runs bear it out: those are the only two
rank-bearing rats in the whole corpus, at 17,542 and 1,619 mentions, and only
the first was ever looted. Nothing else was broken; the loot path ran 4,616
times in the same runs.

"leader" rather than "squad leader" covers the _Wing Leader_ rank in the same
family for one word, as "commander" already covers _Fleet Commander_. That half
is inference from EVE's rank naming -- only Squad Leader is observed here. It is
safe as a substring: every occurrence of "leader" anywhere in the recorded logs
is this rat, so there is no "Wrecker contains wreck" trap of the kind
`containsWords` exists to guard against.

-}
isNotableWreck : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isNotableWreck overviewEntry =
    let
        containsNotableRatName =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
                |> (\texts -> notableRatRankWords |> List.any (\pattern -> texts |> List.any (stringContainsIgnoringCase pattern)))

        isWreck =
            overviewEntry.objectType
                |> Maybe.map (stringContainsIgnoringCase "wreck")
                |> Maybe.withDefault False
    in
    containsNotableRatName && isWreck


{-| Whether there is still a commander/overseer wreck here worth staying for.
Emptied ones do not count: they keep their overview row, so without the looted
check this stays true and holds the bot on a grid it is finished with. Only the
stateless half of `notAlreadyEmptied` is available here, since the caller has a
reading but no bot memory -- the id memory backs it up at the point of choosing
which wreck to open.
-}
anyNotableWreckInOverview : ReadingFromGameClient -> Bool
anyNotableWreckInOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter (overviewEntryLooksLooted >> not)
        |> List.any isNotableWreck


{-| First descendant (by depth-first order) whose displayed text contains
`textToFind`, e.g. a "Loot All" button in an inventory window -- there is
no dedicated field for that button in `InventoryWindow`, unlike
`buttonToStackAll`.
-}
findUiElementWithText : String -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
findUiElementWithText textToFind uiNode =
    EveOnline.ParseUserInterface.getAllContainedDisplayTextsWithRegion uiNode
        |> List.filter (Tuple.first >> stringContainsIgnoringCase textToFind)
        |> List.map Tuple.second
        |> List.head


clickUiElement : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
clickUiElement uiElement =
    decideActionForCurrentStep
        (mouseClickOnUIElement MouseButtonLeft uiElement |> Result.withDefault [])


{-| Double-click a UI element, and say so where the element cannot be clicked.

EVE answers a double click on an object in space or its overview row with that
object's own default action, and that is not one action. A container opens its
cargo, which is the whole context-menu cascade -- right-click, wait for the
flyout to render, find the entry, click it -- in a single step, and from
outside looting range the client flies there and opens on arrival. A hostile
ship has no cargo to open, and the client answers by approaching it instead.
Both are operator-confirmed rather than read out of any documentation, which is
why this comment names them as behaviours seen rather than as a rule.

`mouseDoubleClickOnUIElement` answers `Err` for an element whose visible region
is too small to click, and `Result.withDefault []` on that is a branch that
prints an action and dispatches nothing -- this repo's signature failure. So
the decline is spoken instead.

-}
doubleClickUiElement : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
doubleClickUiElement uiElement =
    case EveOnline.BotFramework.mouseDoubleClickOnUIElement MouseButtonLeft uiElement of
        Ok doubleClickEffects ->
            decideActionForCurrentStep doubleClickEffects

        Err () ->
            describeBranch
                "The visible part of this element is too small to click, so there is nothing to dispatch."
                waitForProgressInGame


{-| EVE's own shortcut for unlocking a target directly from the target bar:
hold Ctrl+Shift and left-click its portrait, no context menu involved.
-}
ctrlShiftClickUiElement : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
ctrlShiftClickUiElement uiElement =
    decideActionForCurrentStep
        (case mouseClickOnUIElement MouseButtonLeft uiElement of
            Ok clickEffects ->
                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL
                , EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT
                ]
                    ++ clickEffects
                    ++ [ EffectOnWindow.KeyUp EffectOnWindow.vkey_SHIFT
                       , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL
                       ]

            Err () ->
                []
        )


moduleIsActiveOrReloading : EveOnline.ParseUserInterface.ShipUIModuleButton -> Bool
moduleIsActiveOrReloading moduleButton =
    (moduleButton.isActive |> Maybe.withDefault False)
        || ((moduleButton.rampRotationMilli |> Maybe.withDefault 0) /= 0)


{-| Weapons are in the ship UI's top module row (see this bot's setup
instructions: "put combat modules in the top row"), and with the default
EVE keybinds F1-F4 activate the first four high-slot modules directly --
faster and more reliable than moving the mouse to click each module
button. Only the first four weapons get a hotkey; a fifth or later falls
back to the previous mouse-click behavior.
-}
weaponHotkeyFromIndex : Int -> Maybe EffectOnWindow.VirtualKeyCode
weaponHotkeyFromIndex index =
    case index of
        0 ->
            Just EffectOnWindow.vkey_F1

        1 ->
            Just EffectOnWindow.vkey_F2

        2 ->
            Just EffectOnWindow.vkey_F3

        3 ->
            Just EffectOnWindow.vkey_F4

        _ ->
            Nothing


doEffectsPressKey : EffectOnWindow.VirtualKeyCode -> List EffectOnWindow.EffectOnWindowStruct -> Bool
doEffectsPressKey keyCode =
    List.member (EffectOnWindow.KeyDown keyCode)


{-| The prop mod (afterburner/MWD) deactivation is bound to Alt+F1 (see
bot feedback: deactivate prop mods before warping). Checking for both
KeyDown events distinguishes this from a plain F1 weapon-hotkey press.
-}
doEffectsDeactivatePropulsionModule : List EffectOnWindow.EffectOnWindowStruct -> Bool
doEffectsDeactivatePropulsionModule effects =
    doEffectsPressKey EffectOnWindow.vkey_MENU effects
        && doEffectsPressKey EffectOnWindow.vkey_F1 effects


activateWeaponModuleButWaitIfActivatedInPreviousStep :
    BotDecisionContext
    -> Int
    -> EveOnline.ParseUserInterface.ShipUIModuleButton
    -> DecisionPathNode
activateWeaponModuleButWaitIfActivatedInPreviousStep context weaponIndex moduleButton =
    case weaponHotkeyFromIndex weaponIndex of
        Nothing ->
            clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton

        Just keyCode ->
            if
                context.previousStepsEffects
                    |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
                    |> List.any (doEffectsPressKey keyCode)
            then
                -- A weapon hotkey is a toggle like the module button it
                -- stands in for, so it gets the same settling window: a
                -- second press before the reading catches up switches the
                -- weapon back off.
                describeBranch
                    "Already pressed this weapon hotkey in a previous step."
                    waitForProgressInGame

            else
                describeBranch
                    ("Press weapon hotkey F" ++ String.fromInt (weaponIndex + 1))
                    (decideActionForCurrentStep
                        [ EffectOnWindow.KeyDown keyCode, EffectOnWindow.KeyUp keyCode ]
                    )


{-| Recall drones and deactivate the propulsion module (Alt+F1) before
warping -- warping away with drones still out abandons them in space,
and an active prop mod can block or interfere with warping. Drones take
priority: if any are out, this spends the step recalling them (via
`returnDronesToBay`) and does not even look at the prop mod yet. Once
none are out, it deactivates the prop mod (skipped if already pressed in
the previous step), then proceeds to `ifReadyToWarp`.

Feedback: this is the single gate every warp/tether-approach action goes
through -- fixing drone recall here (once) covers every caller, including
ones that call `enterAnomaly` directly without their own explicit
`returnDronesToBay` step, which is what let a warp leave drones behind
before.

Acceleration gates are the exception and use `ensureDronesRecalledBeforeWarping`
instead -- see `activateAccelerationGateIfPresent` for why.

-}
ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping :
    BotDecisionContext
    -> DecisionPathNode
    -> DecisionPathNode
ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context ifReadyToWarp =
    ensureDronesRecalledBeforeWarping context
        (deactivatePropulsionModuleBeforeWarping context ifReadyToWarp)


{-| Get the drones home, and nothing else.

The half of the preparation above that is never optional: drones still in space
when the ship leaves are simply lost, whereas an active propulsion module only
costs a slower align. Acceleration gates use this on its own -- see
`activateAccelerationGateIfPresent`.

-}
ensureDronesRecalledBeforeWarping :
    BotDecisionContext
    -> DecisionPathNode
    -> DecisionPathNode
ensureDronesRecalledBeforeWarping context ifReadyToWarp =
    returnDronesToBay context ifReadyToWarp


deactivatePropulsionModuleBeforeWarping :
    BotDecisionContext
    -> DecisionPathNode
    -> DecisionPathNode
deactivatePropulsionModuleBeforeWarping context ifReadyToWarp =
    let
        -- Alt+F1 is a toggle on this keybind setup, not a dedicated
        -- "deactivate" -- confirmed live: pressing it unconditionally turned
        -- the prop mod back ON right before warping whenever it was already
        -- off. The propulsion module is the first module in the middle row;
        -- `manageMiddleRowModules` is what switches it on while the ship is
        -- moving, and this is the shutdown that happens ahead of an ordinary
        -- warp, as opposed to the one at an acceleration gate.
        --
        -- `isActive` is Maybe, and an unreadable state must not count as
        -- "active" here either -- pressing the toggle on a guess is what turns
        -- the module on when the intent was to leave it off.
        propulsionModuleIsActive : Bool
        propulsionModuleIsActive =
            context.readingFromGameClient.shipUI
                |> Maybe.andThen
                    (.moduleButtonsRows
                        >> .middle
                        >> List.sortBy (.uiNode >> .totalDisplayRegion >> .x)
                        >> List.head
                    )
                |> Maybe.andThen .isActive
                |> Maybe.withDefault False
    in
    if not propulsionModuleIsActive then
        ifReadyToWarp

    else if
        context.previousStepsEffects
            |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
            |> List.any doEffectsDeactivatePropulsionModule
    then
        -- Already pressed it; give the reading a chance to catch up rather
        -- than pressing a toggle a second time on a reading that has not
        -- caught up yet -- the same settling window a module-button click
        -- gets, and for the same reason. One step of grace was not enough:
        -- the second press turned the prop mod back on.
        ifReadyToWarp

    else
        describeBranch
            "Deactivate propulsion module before warping (Alt+F1)."
            (decideActionForCurrentStep
                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU
                , EffectOnWindow.KeyDown EffectOnWindow.vkey_F1
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_F1
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU
                ]
            )


{-| Number of consecutive ticks _any_ context menu has been open before we
treat it as stray rather than as a cascade we (or the framework's own
`useContextMenuCascade`) are actively progressing through.

Originally this compared each reading's context menu against the previous
few readings for exact equality (same `totalDisplayRegion`), on the theory
that a cascade actively being clicked through changes every tick while a
truly stray menu sits still. Live use falsified that: a real stuck case
(a `tetherAtStructure` cascade landing on a menu with no "Warp"/"Approach"
entry, whose fallback -- clicking whatever is first -- kept re-clicking
"Show Info" every tick) kept the menu open, unchanged in every visible
way, for over a minute without ever tripping the exact-equality check.
Possibly the menu was actually being closed and freshly reopened each
tick (a genuinely new object) with some sub-pixel difference in its
rendered position while animating open, which would defeat an
exact-`==` comparison indefinitely without ever looking different in a
screenshot.

First replacement: count consecutive ticks where _some_ menu -- any
menu, open regardless of whether it's literally the same instance --
has been open at all, resetting to 0 whenever `contextMenus` is empty.
That also turned out wrong, the opposite way: a genuine multi-level
cascade (e.g. a 3-deep menu select) keeps _some_ menu open continuously
across every level, by design, until the final entry is clicked -- if
that takes more ticks than the threshold (real render/network latency
per level adds up over 3 levels), this fired mid-cascade and cancelled
real progress.

The actual fix: track cascade _depth_, not just presence. Context menus
nest -- descending a level adds one more entry to
`readingFromGameClient.contextMenus` rather than replacing it (this is
also how the framework's own `contextMenuCascadeLevel` works). So
`BotMemory.contextMenuStuckTicks` only increments when the menu count
has stayed the same (or dropped without reaching zero) since the last
reading; any tick that goes _deeper_ than before resets it to 0,
regardless of how many ticks the cascade has taken in total. A
genuinely stuck cascade -- sitting at the same depth, unable to find its
next entry -- still trips this after a few ticks; a cascade that keeps
advancing, no matter how many levels or how slowly, never does.

**This raced the cascade's own recovery and usually won.**
`useContextMenuCascadeWithCustomConfig`'s `beginCascade` gives a stuck-but-open
menu up to 8 readings of "no progress" (widened from 3 -> 4 -> 8 specifically
for `enterAnomaly`'s own "Warp to Within..." distance flyout, per its comment)
before discarding and reopening itself -- on the same target, respecting
whatever of it is not occluded. With this threshold at 3, `clearStrayContextMenu`
fired first on every single occasion the cascade needed more than three readings
to render, since it sits at the head of `decideNextActionWhenInSpace` and
pre-empts everything below it. That is not a stray menu at that point -- it is
a cascade still within its own documented patience, being torn down by a
completely different, cascade-blind recovery mechanism that then clicks beside
the info panel: nowhere near the probe scanner row the cascade was working, and
discarding whatever level of progress the cascade had made. Confirmed live: a
Sansha Refuge scan result was repeatedly abandoned this way before its "to
within"/"Within N km" flyout ever finished rendering.

Raised to clear the cascade's own 8-reading lookback with margin, so a cascade
that is going to recover on its own gets the chance to. It still trips on a
menu that outlasts the cascade's own patience -- that is the case this exists
for -- and `strayContextMenuGiveUpTicks` (a multiple of this) still bounds the
worst case.

-}
strayContextMenuStuckTicksThreshold : Int
strayContextMenuStuckTicksThreshold =
    12


{-| Everything the stray-menu verdict turns on.

A record rather than the whole context, so a case can execute the rule -- and so
the second clause, which is new and is the one thing about this that could be
wrong, is asked in one place rather than restated at the branch.

-}
type alias StrayContextMenuCase =
    { stuckTicks : Int
    , ammoSwapOwnsTheMenu : Bool
    }


{-| Is the menu that has stopped advancing a stray one, or the ammo swap's?

The threshold on its own was right until this bot could swap ammo. The swap holds
a weapon's context menu open across the settle -- `ammoSwapSilenceSettleTicks` is
3, well inside `strayContextMenuStuckTicksThreshold` -- and `menuOpenOnGunAtX`
answers only where the right-click was the immediately previous step, so most of
those readings look from here exactly like a menu nobody is driving. Escape would then
close the menu the load is about to be clicked out of, the swap would re-open it,
and the two would take turns until `ammoSwapVerdictGiveUpTicks` ended the attempt.

**The suppression is bounded by the swap's own deadlines, which is what keeps
this guard's promise intact.** `ammoSwapIsActingOnAVerdict` is false the moment
the verdict is satisfied or abandoned, and a verdict is abandoned after at most
`ammoSwapVerdictGiveUpTicks` readings -- or `ammoSwapSilencedGiveUpTicks` if the
guns are off, which is sooner. So a menu cannot sit here forever, which is the
property this branch exists to guarantee.

What it costs is stated rather than hidden: a genuinely stray menu opened while
the swap is working a verdict is left alone for up to those readings instead of
being cleared on the third. That window is the swap's own, so it ends by itself.

-}
strayContextMenuIsStray : StrayContextMenuCase -> Bool
strayContextMenuIsStray strayCase =
    (strayContextMenuStuckTicksThreshold <= strayCase.stuckTicks)
        && (strayCase.stuckTicks < strayContextMenuGiveUpTicks)
        && not strayCase.ammoSwapOwnsTheMenu


{-| How long the dismissal gets before the bot works around the menu instead.

**This branch had no bound at all, and run 18 is what that costs**: 10,845 of
15,153 decisions were this one rescue, three quarters of an eight-hour session,
with nothing killed. It is reached from the head of `decideNextActionWhenInSpace`,
so a rescue that does not work owns the whole bot -- the same position, and the
same failure, as the message box in the mission runner's run 30.

`Nothing` rather than an alarm, for `MessageBoxStandoff`'s reason: the menu stays
on the screen and every branch below now works around it, which is worse than a
cleared menu and incomparably better than nothing running at all. The status line
keeps saying it is there.

Written as a multiple of the threshold that arms it so the two cannot drift
apart. Twenty attempts is far past anything a working dismissal needs -- the
measured one clears the menu in a single click -- and far short of a session.

-}
strayContextMenuGiveUpTicks : Int
strayContextMenuGiveUpTicks =
    strayContextMenuStuckTicksThreshold * 20


{-| `Just` a decision to press Escape if a context menu has sat at the same
cascade depth (not advancing to a deeper submenu) for at least
`strayContextMenuStuckTicksThreshold` consecutive ticks and the ammo swap is not
the thing holding it open; `Nothing` otherwise, so callers can fall through to
their normal decision tree.
-}
clearStrayContextMenu : BotDecisionContext -> Maybe DecisionPathNode
clearStrayContextMenu context =
    if
        strayContextMenuIsStray
            { stuckTicks = context.memory.contextMenuStuckTicks
            , ammoSwapOwnsTheMenu = ammoSwapIsActingOnAVerdict context.memory.ammoSwap
            }
    then
        Just
            (case emptyPointBesideTheInfoPanel context.readingFromGameClient of
                Just location ->
                    describeBranch
                        "A context menu has sat at the same depth for several ticks in a row without advancing to a deeper submenu -- likely a stray menu from a misclick or a cascade stuck on a menu with no entry it recognizes. Clear it (right-click beside the info panel)."
                        (decideActionForCurrentStep
                            -- **A left click, and only a left click.** The
                            -- right-click that used to lead this is what
                            -- created the thing it was clearing: the client
                            -- opens a context menu *at the cursor*, so the
                            -- right-click put a fresh menu exactly where the
                            -- following left click was aimed, and that click
                            -- then landed on a menu entry rather than on empty
                            -- canvas. Run 47 did that 16,791 times; run 18 did
                            -- it 10,845 times in eight hours and killed
                            -- nothing, with the solar-system menu standing open
                            -- the whole time and the computed point sitting on
                            -- its top-left corner.
                            --
                            -- The pair could never have worked, because the two
                            -- clicks were at the same location and a menu is
                            -- always drawn at the click. What the comment
                            -- before this said about the left click is right,
                            -- and is now the whole action: measured live
                            -- against the real stuck menu, one left click on
                            -- empty canvas dismissed it and opened nothing.
                            (EffectOnWindow.effectsMouseClickAtLocation
                                EffectOnWindow.MouseButtonLeft
                                location
                            )
                        )

                Nothing ->
                    describeBranch
                        "A context menu has sat at the same depth for several ticks in a row without advancing to a deeper submenu, and this reading has no info panel to measure an empty point beside -- press Escape instead, which can open the client's own settings menu and is why it is the fallback rather than the rule."
                        (decideActionForCurrentStep
                            [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                            , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                            ]
                        )
            )

    else
        Nothing


{-| How far right of the info panel's own edge to click, in the client's
coordinates. Wide enough to clear the panel's border and any hover affordance,
narrow enough that it stays in the gap rather than reaching whatever is laid out
further right.
-}
strayMenuClearGapFromInfoPanel : Int
strayMenuClearGapFromInfoPanel =
    80


{-| A point beside the info panel, for dismissing a stray context menu.

**Escape does not do this job**, which is what this replaces. Measured live on
saxrat's run 45 against a stray drone menu: the bot pressed Escape at it 48
times and a hand-sent Escape into a frontmost client did nothing at all, while a
left click elsewhere dismissed it immediately. Meanwhile a naked Escape can open
the client's own settings menu -- `closeSystemSettingsMenu` exists because that
happened live -- so the old rule could both fail to clear the menu and add a
second window to clear.

**Why a computed point is acceptable here when `beginCascade` refuses one.**
That fallback rejects "empty space" because a remembered coordinate is not
reliably empty and once opened _Clear All Waypoints_ on a real route. This point
is not remembered: it is derived from the info panel's own parsed region every
reading, so it moves with the layout the way the UI scale and every other
self-calibrated number here do. The panel is anchored top-left under the Neocom,
and the gap immediately right of it carries no widget -- verified against a live
tree, where the point this returns was covered by zero nodes.

`Nothing` when the info panel is not in the reading, because then there is no
anchor and no point known to be empty. The caller falls back to Escape there,
which is the weaker rescue rather than a guess at a location.

-}
emptyPointBesideTheInfoPanel : ReadingFromGameClient -> Maybe EffectOnWindow.Location2d
emptyPointBesideTheInfoPanel readingFromGameClient =
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen
            (\infoPanelContainer ->
                let
                    region =
                        infoPanelContainer.uiNode.totalDisplayRegion

                    beside =
                        { x = region.x + region.width + strayMenuClearGapFromInfoPanel
                        , y = region.y + (region.height // 2)
                        }

                    canvas =
                        readingFromGameClient.uiTree.totalDisplayRegion

                    menuCovers point menu =
                        let
                            menuRegion =
                                menu.uiNode.totalDisplayRegion
                        in
                        (menuRegion.x <= point.x)
                            && (point.x <= menuRegion.x + menuRegion.width)
                            && (menuRegion.y <= point.y)
                            && (point.y <= menuRegion.y + menuRegion.height)

                    covered point =
                        readingFromGameClient.contextMenus
                            |> List.any (menuCovers point)

                    belowEveryMenu =
                        readingFromGameClient.contextMenus
                            |> List.map
                                (\menu ->
                                    menu.uiNode.totalDisplayRegion.y
                                        + menu.uiNode.totalDisplayRegion.height
                                )
                            |> List.maximum
                            |> Maybe.map
                                (\lowest ->
                                    { beside | y = lowest + strayMenuClearGapFromInfoPanel }
                                )
                in
                if not (covered beside) then
                    Just beside

                else
                    -- The point beside the panel is where the *last* click was,
                    -- so on the reading after one the menu is drawn over it --
                    -- the client opens a context menu at the cursor. Clicking
                    -- there again does not land on empty canvas, it lands on a
                    -- menu entry, and this menu carries `Clear All Waypoints`.
                    -- Stepping below the menu is what keeps the dismissal a
                    -- dismissal.
                    belowEveryMenu
                        |> Maybe.andThen
                            (\below ->
                                if
                                    (below.y < canvas.y + canvas.height)
                                        && not (covered below)
                                then
                                    Just below

                                else
                                    Nothing
                            )
            )


iconSpriteHasColorOfRat : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
iconSpriteHasColorOfRat =
    .iconSpriteColorPercent
        >> Maybe.map
            (\colorPercent ->
                colorPercent.g * 3 < colorPercent.r && colorPercent.b * 3 < colorPercent.r && 60 < colorPercent.r && 50 < colorPercent.a
            )
        >> Maybe.withDefault False


updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        -- Every verdict this bot draws from a reading has to be written here:
        -- this is the only place that can write memory, and a reading's game
        -- log entries are gone by the next one. A branch that recognised
        -- something where it acts on it would see it once and then behave
        -- exactly as it did before.
        hitpointsReading gauge =
            context.readingFromGameClient.shipUI
                |> Maybe.map (.hitpointsPercent >> gauge)
                |> Maybe.andThen plausibleHitpointsPercent

        hitpoints =
            { shield =
                updateHitpointsGaugeMemory
                    context.botSettings.runAwayShieldHitpointsThresholdPercent
                    (hitpointsReading .shield)
                    botMemoryBefore.hitpoints.shield
            , armor =
                updateHitpointsGaugeMemory
                    context.botSettings.runAwayArmorHitpointsThresholdPercent
                    (hitpointsReading .armor)
                    botMemoryBefore.hitpoints.armor
            }

        standingInADeadEnd =
            -- Asks the panel and the scanner the same questions the decision
            -- asks them, which is twice something this counter got wrong.
            --
            -- It used to test the marker pip while `jumpToNextSystem` tested the
            -- panel's words, and with a real route beside a stale
            -- `No Destination` the two disagreed in the worst available
            -- direction: the decision asked the host for a route on every
            -- reading, and this counter -- the only thing bounding that asking
            -- -- stayed at 0 because the pip was there. Run 31 asked 2,494 times
            -- in 48 minutes and reported `0/20 readings` on every one of them.
            --
            -- #273 is the same shape one clause along. This read "nothing at all
            -- on the probe scanner" while the ask fires on "no anomaly matching
            -- the settings", and with a narrow `anomaly-name` beside two
            -- signatures that do not match it, *every* reading took the other
            -- branch and reset the counter. Across the 411 readings the recorded
            -- runs ever printed an ask on, 397 carry a count of 0 or 1 and the
            -- highest any of them carries is 16 against a bound of 20 -- so the
            -- give-up has never once been reached while this bot was asking.
            -- `anomaliesWorthHunting` is now the one filter both sides read.
            (context.readingFromGameClient.shipUI /= Nothing)
                && not (shipIsWarpingOrJumping context.readingFromGameClient)
                && not (routePanelShowsARoute context.readingFromGameClient)
                && List.isEmpty
                    (anomaliesWorthHunting
                        { botSettings = context.botSettings
                        , visitedAnomalies = visitedAnomalies
                        }
                        context.readingFromGameClient
                    )
                && not (gridStillHasSomethingToDo incomingDamageNow context.readingFromGameClient)

        anEscalationIsBeingWorkedInADeadEnd =
            -- What the counter advances on, which is deliberately the hold's
            -- condition *without* its bound. Conjoined with `standingInADeadEnd`
            -- for the reason the ask below is: that is the condition under which
            -- `setRouteToNextHuntingGround` is reached at all, so counting
            -- anything wider would spend the bound on readings the branch never
            -- ran on -- #145's `gateWithinReachTicks` and #11's
            -- `dronesInSpaceTicks`, which each counted the ship being *near*
            -- something rather than the branch asking for it.
            --
            -- **Leaving the bound out here is what makes it a bound.** Advancing
            -- on `standingDownForATrackedEscalation` instead would reset the
            -- count on the very reading the hold expired, so the next reading
            -- would hold again -- a duty cycle of forty held readings and one
            -- ask, forever, rather than a give-up. That is `gunsSilencedTicks`
            -- pinned at 1 by a reset the thing it was waiting on could trigger.
            standingInADeadEnd
                && escalationIsBeingWorked
                    (escalationEntriesPermitted context.botSettings context.readingFromGameClient)

        standingDownForAnEscalationNow =
            -- The reading the decision holds the grid on, re-derived here
            -- because the memory update never sees the decision.
            anEscalationIsBeingWorkedInADeadEnd
                && standingDownForATrackedEscalation
                    { escalationIsBeingWorked = True
                    , standDownReadings = botMemoryBefore.escalationStandDownReadings
                    }

        destinationAskedForNow =
            -- What the decision branch is asking for, named by the *same* picker
            -- it uses. Forgotten the moment a route exists, so arriving and
            -- going dry again asks afresh rather than reading as already asked.
            --
            -- `Nothing` where the circuit has nowhere to send the ship, which is
            -- the answer `setRouteToNextHuntingGround` tethers on rather than
            -- asking (#262). That is why the counter below is keyed on this
            -- value and not on `standingInADeadEnd`: runs 12, 26 and 27 latched
            -- the give-up having issued no ask at all, two of them with no
            -- `hunt-system` configured, because the counter ran while nothing
            -- was being asked for.
            --
            -- `Nothing` while the circuit is standing down for a tracked
            -- escalation (#279), for that same reason and it is the same
            -- defect: no ask goes out on those readings, so a counter that ran
            -- through them would latch `routeSettingGivenUp` for the session
            -- against asks nobody made.
            if standingInADeadEnd && not standingDownForAnEscalationNow then
                nextHuntingGroundFrom context.botSettings
                    botMemoryBefore.huntSystemIndex
                    context.readingFromGameClient
                    botMemoryBefore.lastDockedStationNameFromInfoPanel

            else
                Nothing

        dronesInSpaceCountNow =
            context.readingFromGameClient.dronesWindow
                |> Maybe.andThen .droneGroupInSpace
                |> Maybe.andThen (.header >> .quantityFromTitle)
                |> Maybe.map .current
                |> Maybe.withDefault 0

        currentRouteFirstMarkerRegion =
            context.readingFromGameClient
                |> infoPanelRouteFirstMarkerFromReadingFromGameClient
                |> Maybe.map (.uiNode >> .totalDisplayRegion)

        currentTargetToUnlockRegion =
            -- Reads the same combined list the click site does (#303) --
            -- see `targetsToUnlockIncludingActiveIfStray`'s own doc comment
            -- for why the narrower, bar-text-only list would silently pin
            -- this at `Nothing` for a target the overview-stray half found.
            context.readingFromGameClient
                |> targetsToUnlockIncludingActiveIfStray
                |> List.head
                |> Maybe.map (\target -> (target.barAndImageCont |> Maybe.withDefault target.uiNode).totalDisplayRegion)

        currentSolarSystemName =
            currentSolarSystemNameFromReading context.readingFromGameClient

        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

        shipIsWarping =
            shipWarpingFromReading context.readingFromGameClient

        -- Off entirely unless the setting is armed, so a session that never
        -- uses this pays nothing for it -- `ammoSwap`'s own posture, for the
        -- same reason. `neutralOrHostileInLocal` walking the chat window's
        -- userlist is cheap but not free, and every other reading here already
        -- has enough to compute.
        hidingFromNeutralPastFirstHopNow =
            if context.botSettings.hideWhenNeutralInLocal /= AppSettings.Yes then
                False

            else if neutralOrHostileInLocal context.readingFromGameClient == Just True then
                botMemoryBefore.hidingFromNeutralPastFirstHop
                    || shipIsWarpingOrJumping context.readingFromGameClient

            else
                False

        namesOfRatsInOverview =
            getNamesOfRatsInOverview context.readingFromGameClient

        incomingDamageNow =
            updateIncomingDamageMemory context hitpoints botMemoryBefore.incomingDamage

        lockRangeLearning =
            updateLockRangeLearning (lockRangeReadingFrom context)
                { fromSetting = context.botSettings.targetingRangeMeters
                , statedMeters = botMemoryBefore.lockRangeStatedMeters
                , provenAtMeters = botMemoryBefore.lockProvenAtMeters
                , refusedAtMeters = botMemoryBefore.lockRefusedAtMeters
                , attempt = botMemoryBefore.lockAttempt
                }

        lockBatchAccounting =
            updateLockBatchAccounting
                (lockBatchReadingFrom context botMemoryBefore.targetsCountLastReading)
                { dispatch = botMemoryBefore.lockBatch
                , clicksAsked = botMemoryBefore.lockBatchClicksAsked
                , clicksAnswered = botMemoryBefore.lockBatchClicksAnswered
                }

        maxTargetsLearning =
            updateMaxTargetsLearning (maxTargetsReadingFrom context)
                (maxTargetsStateBefore context botMemoryBefore)

        droneLaunchLearning =
            updateDroneLaunchLearning
                { onScreenNow = quickMessageOnScreen context.readingFromGameClient
                , statedBefore = botMemoryBefore.droneLaunchRefusedAbove
                }

        -- Written here rather than where the box is answered, because the
        -- branch that would keep the count is the branch that stops running
        -- the moment the count reaches its bound. See `MessageBoxStandoff`.
        messageBoxStandoff =
            messageBoxStandoffAfterReading
                { before = botMemoryBefore.messageBoxStandoff
                , identityNow =
                    context.readingFromGameClient.messageBoxes
                        |> List.head
                        |> Maybe.map messageBoxIdentity
                }

        -- Said on the reading the give-up is reached and on no other, like
        -- `lockRangeLastChange`. The bound is crossed once, because the count
        -- only ever rises while one box stays.
        messageBoxLastChange =
            case ( botMemoryBefore.messageBoxStandoff, messageBoxStandoff ) of
                ( Just before, Just now ) ->
                    if
                        (before.readings < messageBoxStandoffGiveUpReadings)
                            && (messageBoxStandoffGiveUpReadings <= now.readings)
                    then
                        Just (describeMessageBoxGivenUpOn now.identity)

                    else
                        Nothing

                _ ->
                    Nothing

        weJustFinishedWarping =
            warpJustEnded
                { warpingLastReading = botMemoryBefore.shipWarpingInLastReading
                , readingNow = context.readingFromGameClient
                }

        -- Restarted at zero on the one reading a warp ends and advanced on every
        -- other, here in the memory update because that is the only thing that
        -- runs on every reading unconditionally -- #102's and #126's placement
        -- rule, and the reason this can be a reading count at all. It is never
        -- cleared: it ages out of the bound on its own, and a `Nothing` restored
        -- here would read as "no warp this session", which is a different fact.
        readingsSinceWarpEnded =
            if weJustFinishedWarping then
                Just 0

            else
                botMemoryBefore.readingsSinceWarpEnded |> Maybe.map ((+) 1)

        -- Note this subsumes the single-reading trigger it replaces rather than
        -- sitting beside it: on the reading a warp just ended the count is zero,
        -- so the window is open by construction.
        arrivalWindowIsOpenNow =
            arrivalWindowIsOpen { readingsSinceWarpEnded = readingsSinceWarpEnded }

        visitedAnomalies =
            if shipIsWarping == Just True then
                botMemoryBefore.visitedAnomalies

            else
                case context.readingFromGameClient |> getCurrentAnomalyIDAsSeenInProbeScanner of
                    Nothing ->
                        botMemoryBefore.visitedAnomalies

                    Just currentAnomalyID ->
                        let
                            anomalyMemoryBefore =
                                botMemoryBefore.visitedAnomalies
                                    |> Dict.get currentAnomalyID
                                    |> Maybe.withDefault
                                        { arrivalTime = { milliseconds = context.timeInMilliseconds }
                                        , otherPilotsFoundOnArrival = []
                                        , ratsSeen = Set.empty
                                        }

                            anomalyMemoryWithOtherPilotsOnArrival =
                                { anomalyMemoryBefore
                                    | otherPilotsFoundOnArrival =
                                        otherPilotsFoundOnArrivalAfterReading
                                            { windowIsOpen = arrivalWindowIsOpenNow
                                            , foundBefore = anomalyMemoryBefore.otherPilotsFoundOnArrival
                                            , seenNow = getNamesOfOtherPilotsInOverview context.readingFromGameClient
                                            }
                                }

                            anomalyMemory =
                                { anomalyMemoryWithOtherPilotsOnArrival
                                    | ratsSeen =
                                        Set.union anomalyMemoryBefore.ratsSeen (Set.fromList namesOfRatsInOverview)
                                }
                        in
                        botMemoryBefore.visitedAnomalies |> Dict.insert currentAnomalyID anomalyMemory
    in
    { lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , shipModules =
        botMemoryBefore.shipModules
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory context.readingFromGameClient
    , shipWarpingInLastReading = shipIsWarping
    , hidingFromNeutralPastFirstHop = hidingFromNeutralPastFirstHopNow
    , readingsSinceWarpEnded = readingsSinceWarpEnded
    , readingsCount = botMemoryBefore.readingsCount + 1
    , visitedAnomalies = visitedAnomalies
    , contextMenuLastDepth = currentContextMenuDepth
    , contextMenuStuckTicks =
        if currentContextMenuDepth == 0 then
            0

        else if currentContextMenuDepth > botMemoryBefore.contextMenuLastDepth then
            0

        else
            botMemoryBefore.contextMenuStuckTicks + 1
    , lootWindowOpenTicks =
        if context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.isEmpty then
            0

        else
            botMemoryBefore.lootWindowOpenTicks + 1
    , routeFirstMarkerRegion = currentRouteFirstMarkerRegion
    , routeFirstMarkerUnchangedTicks =
        if currentRouteFirstMarkerRegion == Nothing then
            0

        else if currentRouteFirstMarkerRegion == botMemoryBefore.routeFirstMarkerRegion then
            botMemoryBefore.routeFirstMarkerUnchangedTicks + 1

        else
            0
    , jumpCascadeSystem = context.readingFromGameClient |> nextSystemOnRouteFromReading
    , jumpCascadeReopens =
        case context.readingFromGameClient |> infoPanelRouteFirstMarkerFromReadingFromGameClient of
            Nothing ->
                0

            Just marker ->
                let
                    sameSystemAsBefore =
                        (context.readingFromGameClient |> nextSystemOnRouteFromReading) == botMemoryBefore.jumpCascadeSystem

                    justRightClickedTheMarker =
                        previousStepRightClickedElement context.previousStepsEffects marker.uiNode
                in
                if sameSystemAsBefore then
                    if justRightClickedTheMarker then
                        botMemoryBefore.jumpCascadeReopens + 1

                    else
                        -- A reading spent waiting for the menu to render is
                        -- not evidence of being stuck -- hold, don't reset.
                        botMemoryBefore.jumpCascadeReopens

                else if justRightClickedTheMarker then
                    1

                else
                    0
    , targetToUnlockRegion = currentTargetToUnlockRegion
    , targetToUnlockUnchangedTicks =
        if currentTargetToUnlockRegion == Nothing then
            0

        else if currentTargetToUnlockRegion == botMemoryBefore.targetToUnlockRegion then
            botMemoryBefore.targetToUnlockUnchangedTicks + 1

        else
            0
    , noProbeScanResultsAndNoRouteLastTimeInSpace =
        -- Used to decide whether to stay docked rather than immediately
        -- undocking again into the same dead end: root-caused live that
        -- with no anomalies to hunt in the current system and no route to
        -- move to another one, tetherAtStructure's fallback (park at an
        -- NPC station) was being followed right back out again on the very
        -- next tick by the unconditional undock in branchDependingOnDockedOrInSpace,
        -- for as long as that stayed true. Deliberately weaker than "no
        -- anomaly matching the bot's settings" (which would need
        -- BotSettings, not available in UpdateMemoryContext) -- "zero probe
        -- scan results at all" undercounts real dead ends (a system with
        -- non-matching scan results still won't trip this), but that's the
        -- safe direction to be wrong in: it only ever *skips* staying
        -- docked, falling back to the existing undock-and-look-again
        -- behavior, never suppresses hunting when there's genuinely
        -- something on the scanner. Frozen while docked (no fresh space
        -- reading to update it from) and re-checked against the route
        -- fresh every tick at the call site, so setting a route while
        -- docked still un-sticks it immediately rather than waiting for
        -- another trip into space.
        if context.readingFromGameClient.shipUI == Nothing then
            botMemoryBefore.noProbeScanResultsAndNoRouteLastTimeInSpace

        else
            (currentRouteFirstMarkerRegion == Nothing)
                && (context.readingFromGameClient.probeScannerWindow
                        |> Maybe.map (.scanResults >> List.isEmpty)
                        |> Maybe.withDefault True
                   )
    , shipApproachingTicks =
        if shipIsApproaching context.readingFromGameClient then
            botMemoryBefore.shipApproachingTicks + 1

        else
            0
    , lootedWreckIds =
        -- Wrecks already opened, by object id. An emptied wreck stays on the
        -- overview looking exactly like a full one as far as its text goes, so
        -- without this the bot re-opens the same wreck for as long as its time
        -- budget allows -- observed live in the mission bot, 73 times into the
        -- same Coreli Scout Wreck.
        --
        -- The id recorded while a loot window is open is the nearest wreck the
        -- picker in `decideActionInAnomaly` would still choose, which is the one
        -- just opened: its icon does not flip to "looted" until the contents are
        -- actually taken, so it is still the nearest un-emptied notable wreck at
        -- this point. Capped so a long session cannot grow this without bound.
        if context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.isEmpty then
            botMemoryBefore.lootedWreckIds

        else
            case
                context.readingFromGameClient.overviewWindows
                    |> List.concatMap .entries
                    |> List.filter isNotableWreck
                    |> List.filter (overviewEntryLooksLooted >> not)
                    |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
                    |> List.head
                    |> Maybe.andThen .objectItemID
            of
                Nothing ->
                    botMemoryBefore.lootedWreckIds

                Just nearestId ->
                    if List.member nearestId botMemoryBefore.lootedWreckIds then
                        botMemoryBefore.lootedWreckIds

                    else
                        nearestId :: botMemoryBefore.lootedWreckIds |> List.take 200
    , gateWithinReachTicks =
        -- Readings in a row spent asking one gate to open, and it did not open.
        -- The name is the mission runner's and is kept so the two bots' copies
        -- read alike; what it counts is the ask rather than the proximity, and
        -- `gateAskedReadingsAfterReading` carries the argument and run 5's
        -- measurement.
        gateAskedReadingsAfterReading
            { asking = askingAnAccelerationGateToOpen context.readingFromGameClient
            , gateWithinReach = accelerationGateIsWithinReach context.readingFromGameClient
            , before = botMemoryBefore.gateWithinReachTicks
            }
    , messageBoxStandoff = messageBoxStandoff
    , messageBoxLastChange = messageBoxLastChange
    , quickMessage =
        quickMessageAfterReading
            { onScreenNow = quickMessageOnScreen context.readingFromGameClient
            , before = botMemoryBefore.quickMessage
            }
    , hitpoints = hitpoints
    , hitpointsLowWaterMark =
        { shield =
            lowWaterMark context.readingFromGameClient
                hitpoints.shield.believed
                botMemoryBefore.hitpointsLowWaterMark.shield
        , armor =
            lowWaterMark context.readingFromGameClient
                hitpoints.armor.believed
                botMemoryBefore.hitpointsLowWaterMark.armor
        }
    , incomingDamage = incomingDamageNow
    , shipLoss =
        shipLossVerdictAfter context.readingFromGameClient
            { withoutModulesReadings =
                shipUIWithoutModuleButtonsReadingsAfter context.readingFromGameClient
                    botMemoryBefore.shipUIWithoutModuleButtonsReadings
            , verdictBefore = botMemoryBefore.shipLoss
            }
    , shipUIWithoutModuleButtonsReadings =
        shipUIWithoutModuleButtonsReadingsAfter context.readingFromGameClient
            botMemoryBefore.shipUIWithoutModuleButtonsReadings
    , droneRecallUnansweredTicks =
        -- Readings since the bot *asked* and the client did not answer -- never
        -- readings since the drones were launched. That was issue #11: drones
        -- are deliberately left out for a whole fight, so a counter started at
        -- the launch reaches any threshold during an ordinary engagement,
        -- after which the recall declines for the rest of the session and
        -- every warp abandons whatever is in space.
        if dronesInSpaceCountNow < 1 then
            0
            -- A partial recall is the client answering, so it resets the
            -- patience rather than counting against it.

        else if dronesInSpaceCountNow < botMemoryBefore.dronesInSpaceCountLastReading then
            0
            -- Past the give-up, hold rather than reset. Giving up is what stops
            -- the asking, so a reset would unwind it and the ship would
            -- alternate forever between abandoning its drones and recalling
            -- them.

        else if droneRecallGiveUpTicks < botMemoryBefore.droneRecallUnansweredTicks then
            botMemoryBefore.droneRecallUnansweredTicks

        else if recentStepAskedForDroneRecall context.previousStepsEffects then
            botMemoryBefore.droneRecallUnansweredTicks + 1

        else
            botMemoryBefore.droneRecallUnansweredTicks
    , dronesInSpaceCountLastReading = dronesInSpaceCountNow
    , dronesInSpaceTicks =
        -- How long the drones have been out, which is what the focus-recovery
        -- click is timed against. Deliberately *not* what the give-up counts.
        if dronesInSpaceCountNow < 1 then
            0

        else
            botMemoryBefore.dronesInSpaceTicks + 1
    , huntSystemIndex =
        -- Advance when the ship is standing in the system the circuit
        -- currently points at. That is the whole rotation, and it needs no
        -- record of which systems were dry: arriving somewhere is what moves
        -- the pointer past it. A simple "first name that is not here" would
        -- ping-pong between the first two entries and never reach the third.
        --
        -- This used to claim the picker could therefore never name the system
        -- the ship is already in, and #262 is what that cost: once a lap is
        -- complete the picker answers `home-system` whatever the index does,
        -- so a ship parked in its staging system asked for the system it was
        -- standing in. `nextHuntingGroundFrom` skips it now; the rotation is
        -- unchanged.
        case currentSolarSystemName of
            Nothing ->
                botMemoryBefore.huntSystemIndex

            Just systemName ->
                if huntSystemAtIndex context.botSettings botMemoryBefore.huntSystemIndex == Just systemName then
                    botMemoryBefore.huntSystemIndex + 1

                else
                    botMemoryBefore.huntSystemIndex
    , fleetBroadcastSeen =
        fleetTravelBroadcast context.botSettings.followFleetBroadcastFrom
            context.readingFromGameClient
            |> Maybe.map .banner
    , fleetBroadcastFollowed =
        -- Latched on the *second* consecutive sighting of the same banner, so
        -- the reading the branch fires on still sees an unlatched verdict. The
        -- banner persists, so the second sighting always arrives.
        case
            fleetTravelBroadcast context.botSettings.followFleetBroadcastFrom
                context.readingFromGameClient
                |> Maybe.map .banner
        of
            Nothing ->
                botMemoryBefore.fleetBroadcastFollowed

            Just banner ->
                if botMemoryBefore.fleetBroadcastSeen == Just banner then
                    Just banner

                else
                    botMemoryBefore.fleetBroadcastFollowed
    , fleetBackupBroadcastFollowed =
        -- Latched on the ship actually **warping** while the pilot is in
        -- local chat -- a fact read straight off this reading, not off a
        -- "seen N readings" counter. Two earlier designs both got this wrong
        -- live, in opposite directions, and both are why the field is shaped
        -- this way now:
        --
        -- The first latched after the identity had merely been *seen*
        -- twice, on the same shape `fleetBroadcastFollowed` uses for the
        -- idempotent host-directive above. The persistent banner reads
        -- identically on every reading it is up, so "seen twice" was reached
        -- one or two readings after the first sighting regardless of
        -- whether any click had landed -- saxrat run 15 shows three separate
        -- attempts, each cut off at "cascade level 0" with no click ever
        -- reaching the client, three stray menus left behind, and the ship
        -- never warped anywhere.
        --
        -- The second dropped the counter for exactly that reason and instead
        -- tried to route toward a caller who was not yet in this system,
        -- retrying the click every reading until the client confirmed it.
        -- Live, that confirmed something worse than a timing bug: EVE simply
        -- refuses to compute an autopilot route to a fleet member's live
        -- in-space position at all -- run 16's game log answered
        -- `You can't set that as a waypoint` on every single one of several
        -- hundred consecutive attempts. So the not-in-system case is no
        -- longer attempted here at all (see `respondToFleetBackupBroadcast`)
        -- and this field only ever latches for the in-system case, which is
        -- the one observed actually working.
        --
        -- A third gap was found live rather than engineered around in
        -- advance and is closed here: a ship already warping for an
        -- unrelated reason (this bot is warping constantly -- between
        -- anomalies, retreating) on the reading a call is first read would
        -- credit that warp as the click's own success and never dispatch
        -- one at all. `fleetBackupInSystemStanding`, below, is read from the
        -- *previous* reading rather than this one for exactly the reason
        -- `fleetBroadcastFollowed`'s own two-reading lag exists: crediting
        -- this reading's own "standing" fact would let a ship that starts
        -- this very reading already stationary in her system immediately
        -- satisfy both halves at once with no click in between.
        case fleetNeedsBackupBroadcast context.botSettings.followFleetBroadcastFrom context.readingFromGameClient of
            Nothing ->
                botMemoryBefore.fleetBackupBroadcastFollowed

            Just backup ->
                if
                    pilotIsInLocalChat backup.pilot context.readingFromGameClient
                        && (shipWarpingFromReading context.readingFromGameClient == Just True)
                        && (botMemoryBefore.fleetBackupInSystemStanding == Just backup.identity)
                then
                    Just backup.identity

                else
                    botMemoryBefore.fleetBackupBroadcastFollowed
    , fleetBackupInSystemStanding =
        case fleetNeedsBackupBroadcast context.botSettings.followFleetBroadcastFrom context.readingFromGameClient of
            Nothing ->
                Nothing

            Just backup ->
                if
                    pilotIsInLocalChat backup.pilot context.readingFromGameClient
                        && (shipWarpingFromReading context.readingFromGameClient /= Just True)
                then
                    Just backup.identity

                else
                    Nothing
    , fleetAtLocationBroadcastFollowed =
        -- Same shape as `fleetBackupBroadcastFollowed`: latched only on the
        -- ship actually warping while the pilot is in local chat, credited
        -- only once a *previous* reading saw her in system with this ship
        -- standing still (`fleetAtLocationInSystemStanding`).
        case fleetAtLocationBroadcast context.botSettings.followFleetBroadcastFrom context.readingFromGameClient of
            Nothing ->
                botMemoryBefore.fleetAtLocationBroadcastFollowed

            Just call ->
                if
                    pilotIsInLocalChat call.pilot context.readingFromGameClient
                        && (shipWarpingFromReading context.readingFromGameClient == Just True)
                        && (botMemoryBefore.fleetAtLocationInSystemStanding == Just call.identity)
                then
                    Just call.identity

                else
                    botMemoryBefore.fleetAtLocationBroadcastFollowed
    , fleetAtLocationInSystemStanding =
        case fleetAtLocationBroadcast context.botSettings.followFleetBroadcastFrom context.readingFromGameClient of
            Nothing ->
                Nothing

            Just call ->
                if
                    pilotIsInLocalChat call.pilot context.readingFromGameClient
                        && (shipWarpingFromReading context.readingFromGameClient /= Just True)
                then
                    Just call.identity

                else
                    Nothing
    , fleetAtLocationBroadcastSeen =
        fleetAtLocationBroadcast context.botSettings.followFleetBroadcastFrom
            context.readingFromGameClient
            |> Maybe.map .identity
    , fleetBroadcast =
        -- The counters that bound a broadcast, advanced here for the reason
        -- every other bound in this file is advanced here: this runs on every
        -- reading whatever the bot is doing, so an arm that stops being reached
        -- cannot freeze the count that is supposed to stop it asking.
        --
        -- `incomingDamageNow.retreating` rather than the previous reading's, so
        -- a backup call is warranted by the same latched fact
        -- `runAwayIfLowHealth` is reading on the reading it fires on.
        fleetBroadcastMemoryAfterReading
            { commanderMode = context.botSettings.fleetCommander == AppSettings.Yes
            , call =
                fleetBroadcastCall
                    { incomingDamagePastTheThreshold = incomingDamageNow.retreating }
                    context.readingFromGameClient
            , bannerNow = fleetBroadcastBannerText context.readingFromGameClient
            , before = botMemoryBefore.fleetBroadcast
            }
    , fleetAtLocationDestinationAsked =
        -- Same second-sighting lag `fleetBroadcastFollowed` uses for the
        -- idempotent host directive: safe here because asking again before
        -- this latches costs nothing (the host dedupes on the name), and
        -- once latched this ship hands the reading back to ordinary travel
        -- for the rest of the trip rather than asking forever.
        case fleetAtLocationBroadcast context.botSettings.followFleetBroadcastFrom context.readingFromGameClient of
            Nothing ->
                Nothing

            Just call ->
                if botMemoryBefore.fleetAtLocationBroadcastSeen == Just call.identity then
                    Just call.identity

                else
                    botMemoryBefore.fleetAtLocationDestinationAsked
    , destinationAskedFor = destinationAskedForNow
    , destinationAskReadings =
        -- Counts the readings the branch is asking on, which is what
        -- `routeAskGiveUpReadings` is a bound on. `destinationAskedForNow` is
        -- the whole condition: it is `Just` exactly when the ship is in a dead
        -- end and the circuit has somewhere to send it, so the counter and the
        -- ask cannot disagree about whether an ask is happening or about which
        -- system it is for.
        --
        -- **The comment this replaces reasoned correctly and priced it wrong.**
        -- It said counting a narrower state "can under-count and delay the
        -- give-up", which would be tolerable. Narrowing to an *empty* probe
        -- scanner does not delay the give-up, it removes it: a non-empty
        -- scanner is the steady state in the very situation the ask exists for,
        -- so the counter reset on every reading and the bound was unreachable.
        -- #273, and it is #11's own mistake in the shape that comment cites
        -- while walking into it -- a counter measuring something other than the
        -- thing it bounds.
        --
        -- The fear behind the narrowing is answered by the ask's own condition
        -- rather than by a second one: `standingInADeadEnd` already requires
        -- that no anomaly on the scanner is worth hunting, and the one thing it
        -- does not imply -- a fight still going on with the site's signature
        -- gone -- is `gridStillHasSomethingToDo`, which the decision reads at
        -- the same site through the same declaration.
        if destinationAskedForNow == Nothing then
            0

        else
            botMemoryBefore.destinationAskReadings + 1
    , routeSettingGivenUp =
        -- Latched for the session. A host with no ESI credentials, or one that
        -- does not read the directive at all, will never answer -- and a bot
        -- that keeps asking is one that never goes back to hunting.
        botMemoryBefore.routeSettingGivenUp
            || (routeAskGiveUpReadings < botMemoryBefore.destinationAskReadings)
    , escalationStandDownReadings =
        -- Resets on any reading the hold does not apply to -- a route
        -- appearing, the escalation leaving the tracker, the ship docking, an
        -- anomaly worth hunting turning up, or anything left to do on the grid
        -- -- so the bound measures one uninterrupted hold rather than a
        -- session's worth of them.
        if anEscalationIsBeingWorkedInADeadEnd then
            botMemoryBefore.escalationStandDownReadings + 1

        else
            0
    , lockBatch = lockBatchAccounting.dispatch
    , lockBatchClicksAsked = lockBatchAccounting.clicksAsked
    , lockBatchClicksAnswered = lockBatchAccounting.clicksAnswered
    , lockBatchLastChange = lockBatchAccounting.change
    , targetsCountLastReading = context.readingFromGameClient.targets |> List.length
    , combatStalemate =
        combatStalemateAfterReading
            { before = botMemoryBefore.combatStalemate
            , fightIsUnderway = combatFightIsUnderway context.readingFromGameClient
            , ratsInOverview = namesOfRatsInOverview |> List.length
            }
    , outgoingFire =
        outgoingFireAfterReading
            { before = botMemoryBefore.outgoingFire
            , summaries = context.readingFromGameClient.outgoingDamageSinceLastReading
            }
    , kills =
        killCountAfterReading
            { before = botMemoryBefore.kills
            , kills = context.readingFromGameClient.killsSinceLastReading
            }
    , lockAttempt = lockRangeLearning.attempt
    , lockRangeStatedMeters =
        -- Overwritten rather than narrowed: the ceiling is not a constant even
        -- for one hull. Only 49 km and 39 km occur across the corpus and runs 13
        -- and 14 carry both within one session, so a monotone bound here would
        -- be #206 again in the other direction. A reading that says nothing
        -- keeps the last thing the client said.
        case lockRangeStatedInQuickMessage context.readingFromGameClient of
            Just stated ->
                Just stated

            Nothing ->
                botMemoryBefore.lockRangeStatedMeters
    , lockProvenAtMeters = lockRangeLearning.provenAtMeters
    , lockRefusedAtMeters = lockRangeLearning.refusedAtMeters
    , lockRangeLastChange = lockRangeLearning.change
    , maxTargetsStatedByClient = maxTargetsLearning.statedByClient
    , maxTargetsHeldAtOnce = maxTargetsLearning.heldAtOnce
    , maxTargetsLastChange = maxTargetsLearning.change
    , droneLaunchRefusedAbove = droneLaunchLearning.statedByClient
    , droneLaunchLastChange = droneLaunchLearning.change
    , ammoSwap =
        -- This reading's damage window rather than the previous one's, which is
        -- why `incomingDamageNow` is a binding: `swapMayDisarmTheGuns` is
        -- re-asked on every reading the swap holds the guns, and asking it
        -- about a window one reading stale would let the swap sit through the
        -- first reading of a fight arriving.
        --
        -- The warp is the boundary a give-up is retried across, and it is the
        -- same `weJustFinishedWarping` the anomaly bookkeeping reads -- one
        -- definition, so the two cannot come to disagree about when a pocket
        -- ended. See `ammoSwapGiveUpAfterReading`.
        updateAmmoSwapMemory context
            incomingDamageNow
            { justFinishedWarping = weJustFinishedWarping }
            botMemoryBefore.ammoSwap
    }


getCurrentAnomalyIDAsSeenInProbeScanner : ReadingFromGameClient -> Maybe String
getCurrentAnomalyIDAsSeenInProbeScanner =
    getCurrentAnomalyIdentityAsSeenInProbeScanner >> Maybe.map .id


{-| The scanner's own words for the site the ship is in: its ID, Name and Group.

**Nothing keys on this.** `visitedAnomalies` is filed under the ID and stays
that way, because the ID is what the client gives uniquely per site on this grid
while a Name is shared by every site of a kind -- an anomaly memory keyed on
`Sansha Refuge` would confuse the one just cleared with the next one. This is
for _saying_ which site that is, in the client's own words.

The three cells come off the **same** scan-result row rather than from three
lookups, so they cannot be answered from different rows if the scanner re-sorts
between reads. That is not a hypothetical tidiness: the overview's own re-sort
between a read and a click is documented here as having locked the wrong object
and shot an asteroid for 290 readings.

`Nothing` for a cell is the scanner not giving one, and it is not an empty name.
The renderer says so in words for the same reason `loadRefusalFromGameLog` does:
a fabricated blank reads as a site the client declined to name, which is a
different fact from one nobody read.

Reading it at all is #197. `anomaly-name` is matched against the Name cell, and
until now that cell was read once, folded into a `Bool` and dropped -- so what a
run recorded was the ID, no recorded run carried a site name, and the question of
what that column may contain was unanswerable from the corpus at any size rather
than merely unanswered.

-}
type alias AnomalyIdentity =
    { id : String
    , name : Maybe String
    , group : Maybe String
    }


getCurrentAnomalyIdentityAsSeenInProbeScanner : ReadingFromGameClient -> Maybe AnomalyIdentity
getCurrentAnomalyIdentityAsSeenInProbeScanner =
    .probeScannerWindow
        >> Maybe.map getScanResultsForSitesOnGrid
        >> Maybe.withDefault []
        >> List.head
        >> Maybe.andThen
            (\scanResult ->
                scanResult.cellsTexts
                    |> Dict.get "ID"
                    |> Maybe.map
                        (\id ->
                            { id = id
                            , name = scanResult.cellsTexts |> Dict.get "Name"
                            , group = scanResult.cellsTexts |> Dict.get "Group"
                            }
                        )
            )


{-| `'EGC-528' 'Sansha Refuge' (Combat Site)`, for the lines a run is read back from.

**The ID stays first and stays single-quoted.** `engagement_watch.py` names every
screenshot it takes from `We are in anomaly '([^']+)'`, which takes the first
quoted group out of the line -- so a name appended after the ID is invisible to
it, and a name put in front would silently rename every screenshot of every run
while the watcher went on looking healthy.

-}
describeAnomalyIdentity : AnomalyIdentity -> String
describeAnomalyIdentity anomaly =
    "'"
        ++ anomaly.id
        ++ "' "
        ++ (anomaly.name |> Maybe.map (\name -> "'" ++ name ++ "'") |> Maybe.withDefault "(name unread)")
        ++ " "
        ++ (anomaly.group |> Maybe.map (\group -> "(" ++ group ++ ")") |> Maybe.withDefault "(group unread)")


{-| `EGC-528/Sansha Refuge`, for the one-line header printed on every decision.

Joined by a slash rather than a space because the header's next field is the
active target's name, and two bare names running together read as one. The Group
is left out: it is `Combat Site` for everything this bot hunts, so in the line
printed most often it would be a column of one repeated word.

-}
describeAnomalyIdentityForHeader : AnomalyIdentity -> String
describeAnomalyIdentityForHeader anomaly =
    anomaly.id
        ++ (anomaly.name |> Maybe.map (\name -> "/" ++ name) |> Maybe.withDefault "")


getScanResultsForSitesOnGrid : EveOnline.ParseUserInterface.ProbeScannerWindow -> List EveOnline.ParseUserInterface.ProbeScanResult
getScanResultsForSitesOnGrid probeScannerWindow =
    probeScannerWindow.scanResults
        |> List.filter (scanResultLooksLikeItIsOnGrid >> Maybe.withDefault False)


scanResultLooksLikeItIsOnGrid : EveOnline.ParseUserInterface.ProbeScanResult -> Maybe Bool
scanResultLooksLikeItIsOnGrid =
    .cellsTexts
        >> Dict.get "Distance"
        >> Maybe.map (\text -> (text |> String.contains " m") || (text |> String.contains " km"))


getNamesOfRatsInOverview : ReadingFromGameClient -> List String
getNamesOfRatsInOverview readingFromGameClient =
    let
        overviewEntryRepresentsRatOnGrid overviewEntry =
            iconSpriteHasColorOfRat overviewEntry
                && (overviewEntry.objectDistanceInMeters
                        |> Result.map (\distanceInMeters -> distanceInMeters < 300000)
                        |> Result.withDefault False
                   )
    in
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryRepresentsRatOnGrid
        |> List.map (.objectName >> Maybe.withDefault "do not see name of overview entry")


{-| The client's own words for a fleetmate's icon in local chat -- captured live
on `FlagIconWithState` nodes inside `XmppChatUserEntry` rows, and never on an
overview row (five were checked live and none carried a `rightAlignedIconContainer`
hint at all). See #224 and CLAUDE.md's "Strings and identities read off a live
client".
-}
chatUserStandingHintFleetmateMarker : String
chatUserStandingHintFleetmateMarker =
    "Pilot is in your fleet"


{-| Absent evidence must not read as "fleetmate". A chat row this bot cannot
resolve a hint for is a stranger, exactly as it always was, so the anomaly is
still avoided if such a row lands at the head of `otherPilotsFoundOnArrival`.
-}
chatUserIsKnownFleetmate : EveOnline.ParseUserInterface.ChatUserEntry -> Bool
chatUserIsKnownFleetmate chatUser =
    case chatUser.standingIconHint of
        Nothing ->
            False

        Just standingIconHint ->
            stringContainsIgnoringCase chatUserStandingHintFleetmateMarker standingIconHint


{-| A real pilot on grid also shows up by name in the Local chat
userlist; a rat/NPC never does. Cross-referencing overview entries
against Local is how the sibling `eve-online-wingus` bot already does
this (ported verbatim from there -- same `ChatWindow`/`ChatUserEntry`
shape in this bot's own `ParseUserInterface.elm`).

**Fleetmates are excluded here, not read for the first time elsewhere** (#224).
The overview row itself carries no fleet hint to read, so this bot's own
`findReasonToAvoidAnomalyFromMemory` was avoiding the anomaly whenever the head
of `otherPilotsFoundOnArrival` was anybody at all, fleet commander included --
the pilot this bot is by far most likely to land beside, since
`follow-fleet-broadcast-from` is what sent it there. The fix is a filter on the
list this function already builds: a chat row with the fleetmate hint drops out
before its name ever reaches the overview cross-reference, so it can never
become the "other pilot" the memory records. A chat row with no hint at all
stays in the list -- absent evidence reads as a stranger, which is today's
behaviour and the direction this must fail in.

-}
getNamesOfOtherPilotsInOverview : ReadingFromGameClient -> List String
getNamesOfOtherPilotsInOverview readingFromGameClient =
    let
        pilotNamesFromLocalChat =
            readingFromGameClient
                |> localChatWindowFromUserInterface
                |> Maybe.andThen .userlist
                |> Maybe.map .visibleUsers
                |> Maybe.withDefault []
                |> List.filter (chatUserIsKnownFleetmate >> not)
                |> List.filterMap .name

        overviewEntryRepresentsOtherPilot overviewEntry =
            (overviewEntry.objectName |> Maybe.map (\objectName -> pilotNamesFromLocalChat |> List.member objectName))
                |> Maybe.withDefault False
    in
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryRepresentsOtherPilot
        |> List.map (.objectName >> Maybe.withDefault "do not see name of overview entry")


{-| The top (weapon) row, left to right.

Same reasoning as `middleRowLeftToRight`: `moduleButtonsRows.top` arrives in
UI-tree order, not screen order, and a slot can drop out of the parsed list
and rejoin without moving on screen. This row's list index feeds directly
into `weaponHotkeyFromIndex` (F1-F4), so an unsorted list here means the
hotkey pressed does not reliably correspond to the same physical weapon
twice -- the same failure mode caught live for the middle row.

-}
shipUIModulesToActivateOnTarget : SeeUndockingComplete -> List ShipUIModuleButton
shipUIModulesToActivateOnTarget =
    .shipUI >> .moduleButtonsRows >> .top >> weaponModuleButtonsLeftToRight


{-| The one ordering of the weapon row.

Shared by this bot's two readers of it: the fight, which turns a list index into
a hotkey, and the ammo swap, which reaches the same row from a reading through
`weaponModuleButtonsFromReading`. Two sorts would be two opinions about which
physical weapon a position names, and the swap silences a gun the fight then
re-arms by that position.

-}
weaponModuleButtonsLeftToRight : List ShipUIModuleButton -> List ShipUIModuleButton
weaponModuleButtonsLeftToRight =
    List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


{-| Put the middle row into the state the moment calls for, if it is not already.

Tank modules first: they matter while something is shooting back, and are left
alone otherwise rather than idling capacitor away on an empty grid.

Then the propulsion module, which follows the ship rather than the fight -- on
while covering distance, off once a gate is in reach. Both directions are
handled, because "should be off and is on" is a real state here: the module gets
switched on out in the middle of a pocket and has to come off again at the far
end.

-}
manageMiddleRowModules : BotDecisionContext -> SeeUndockingComplete -> Maybe DecisionPathNode
manageMiddleRowModules context seeUndockingComplete =
    let
        somethingToFight =
            anyAttackableInOverview (namesOfRecentAttackers context.memory.incomingDamage) context.readingFromGameClient

        inactiveTankModule =
            if somethingToFight then
                seeUndockingComplete |> inactiveModulesToActivateAlways |> List.head

            else
                Nothing

        propulsionModuleAction =
            propulsionModuleButton seeUndockingComplete
                |> Maybe.andThen
                    (\moduleButton ->
                        let
                            isRunning =
                                moduleButton.isActive |> Maybe.withDefault False
                        in
                        if propulsionModuleShouldBeRunning context somethingToFight && not isRunning then
                            Just
                                ( "The ship is on the move -- run the propulsion module."
                                , moduleButton
                                )

                        else if not isRunning then
                            Nothing

                        else if accelerationGateIsWithinReach context.readingFromGameClient then
                            Just
                                ( "The acceleration gate is in reach -- shut the propulsion module down."
                                , moduleButton
                                )

                        else if shipIsEnteringWarp context.readingFromGameClient then
                            Just
                                ( "The ship is lining up to warp -- shut the propulsion module down, it only makes that slower."
                                , moduleButton
                                )

                        else
                            Nothing
                    )
    in
    case inactiveTankModule of
        Just moduleButton ->
            Just
                (describeBranch "This module should always be active"
                    (clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton)
                )

        Nothing ->
            propulsionModuleAction
                |> Maybe.map
                    (\( description, moduleButton ) ->
                        describeBranch description
                            (clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton)
                    )


{-| The tank modules: the middle row, minus the propulsion module in its first
slot.

The two halves of that row want opposite things and so are driven separately.
Hardeners and the like are worth running whenever there is a fight and are a
waste of capacitor otherwise, which is the `anyAttackableInOverview` gate at the
call site. The propulsion module is the reverse -- it earns its capacitor while
the ship is crossing distance, which is usually when there is nothing to shoot
at all. See `propulsionModuleShouldBeRunning`.

-}
shipUIModulesToActivateAlways : SeeUndockingComplete -> List ShipUIModuleButton
shipUIModulesToActivateAlways =
    middleRowLeftToRight >> List.drop 1


{-| The middle row in the order the player sees it, leftmost first.

`moduleButtonsRows.middle` arrives in UI-tree order, and while that traversal is
a stable depth-first walk, the list it produces is not a stable index space: the
parser drops any node whose display region it cannot read, so a slot can leave
and rejoin the list without anything moving on screen. Taking "the first slot" by
index therefore does not reliably mean the same module twice.

Caught live: with both tank modules already running, the bot decided three times
in a row to switch on what it called the propulsion module, the propulsion module
never came on, and a _tank_ module went off instead -- an odd number of toggles
landing on a neighbour. Sorting by x is what makes "first in the middle row" mean
the thing the setup instructions point at, and it cannot be shifted by a slot
dropping out of the list.

-}
middleRowLeftToRight : SeeUndockingComplete -> List ShipUIModuleButton
middleRowLeftToRight =
    .shipUI
        >> .moduleButtonsRows
        >> .middle
        >> List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


{-| The propulsion module: the leftmost slot of the middle row, per the setup
instructions.
-}
propulsionModuleButton : SeeUndockingComplete -> Maybe ShipUIModuleButton
propulsionModuleButton =
    middleRowLeftToRight >> List.head


{-| Whether the ship is under a movement order that covers ground.

Approach is the obvious one, but combat manoeuvres count for exactly the same
reason: orbiting a rat or holding a range is the ship working to stay where it
wants to be, and that is what the propulsion module is for. Reading only
`ManeuverApproach` was the bug -- with `orbit-in-combat` or `keep-at-range` the
ship sits in `ManeuverOrbit` or `ManeuverRange` for the whole fight, so the
module was never switched on in the one place it matters most.

Align, Warp and Jump are deliberately absent: those are the ship leaving, and
`shipIsEnteringWarp` exists to switch the module off for them.

-}
shipIsUnderway : ReadingFromGameClient -> Bool
shipIsUnderway readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
        |> Maybe.map
            (\maneuverType ->
                [ EveOnline.ParseUserInterface.ManeuverApproach
                , EveOnline.ParseUserInterface.ManeuverOrbit
                , EveOnline.ParseUserInterface.ManeuverRange
                ]
                    |> List.member maneuverType
            )
        |> Maybe.withDefault False


{-| Whether the ship is in the act of leaving -- lined up for warp, or already
in one.

The propulsion module has to come off here. An active afterburner or MWD adds
mass, and mass is exactly what makes aligning and entering warp slow, so leaving
it running spends the ship the seconds it was switched on to save.

In practice this fires on `ManeuverAlign`, the lining-up phase. Both callers
short-circuit on `shipUIIndicatesShipIsWarpingOrJumping` before the module logic
is reached, so by the time the indication reads Warp this step no longer runs at
all -- Warp and Jump are listed anyway, so the rule says what it means instead of
depending on that ordering holding.

-}
shipIsEnteringWarp : ReadingFromGameClient -> Bool
shipIsEnteringWarp readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
        |> Maybe.map
            (\maneuverType ->
                [ EveOnline.ParseUserInterface.ManeuverAlign
                , EveOnline.ParseUserInterface.ManeuverWarp
                , EveOnline.ParseUserInterface.ManeuverJump
                ]
                    |> List.member maneuverType
            )
        |> Maybe.withDefault False


{-| Whether the propulsion module should be running right now.

On whenever the ship is covering ground, or has something to fight. Both matter:
an acceleration gate is often tens of km off and crossing that with the module
idle is the difference between a moment and a crawl, while in a fight the module
is what holds the orbit or the range the bot is trying to hold. `somethingToFight`
is passed in rather than re-derived because it is the same test the tank modules
use, and it covers the ticks where a combat manoeuvre has not yet shown up in the
ship's indication. Movement is read from the ship's own indication rather than
from what the bot last decided, so it is true whether the manoeuvre was ordered
by this bot or came from the client's own "fly there and act on arrival"
behaviour.

Off again once a gate is within reach. The gate is taken from a standstill and
the module has nothing further to contribute, so leaving it burning capacitor
into the jump is pure waste.

The last clause keeps this from fighting `deactivatePropulsionModuleBeforeWarping`,
which switches the module off ahead of an ordinary warp. Without it, a ship still
showing `ManeuverApproach` in the moment after that deliberate shutdown would
have this rule turn it straight back on -- the same two-controllers flicker that
splitting the row was meant to end.

-}
propulsionModuleShouldBeRunning : BotDecisionContext -> Bool -> Bool
propulsionModuleShouldBeRunning context somethingToFight =
    (shipIsUnderway context.readingFromGameClient || somethingToFight)
        && not (accelerationGateIsWithinReach context.readingFromGameClient)
        && not (shipIsEnteringWarp context.readingFromGameClient)
        && not
            (context.previousStepsEffects
                |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
                |> List.any doEffectsDeactivatePropulsionModule
            )


{-| The always-active modules that want a click: anything not known to be on.

The test looks lax and is not. `isActive` reads `ramp_active` off the module
button, and on this client that entry does not exist at all until the module has
been activated: the whole `ShipModuleButtonRamps` widget holding it is created
when the module starts cycling and destroyed when it stops. Measured against the
live client over 40 seconds, a middle-row module reads

    off, never yet run   ->  isActive = Nothing      (no ramps widget)
    running              ->  isActive = Just True
    off, but ran before  ->  isActive = Just False   (ramps widget still there)

so "off" arrives as `Nothing` at least as often as `Just False`. Requiring
`Just False` -- which this briefly did -- therefore skipped exactly the modules
that needed switching on, and the bot activated nothing at all.

Clicking on `Nothing` is safe because the click is not repeated until the client
has had a chance to show the result: see `moduleButtonClickSettlingSteps`, which
is the actual fix for the on/off/on flicker. Before that window was widened, the
ramps widget took longer to appear than the guard remembered the click, so the
bot clicked a second time and switched the module back off.

`isBusy` is no use as a second opinion here: it looks for a sprite named "busy"
in the slot, and this client's slots only ever carry "mainshape", "overloadBtn"
and (on an active slot) "underlay". Same for `isHiliteVisible` and its "hilite"
sprite. Both are permanently False rather than informative.

-}
inactiveModulesToActivateAlways : SeeUndockingComplete -> List ShipUIModuleButton
inactiveModulesToActivateAlways seeUndockingComplete =
    seeUndockingComplete
        |> shipUIModulesToActivateAlways
        |> List.filter (.isActive >> Maybe.withDefault False >> not)


{-| Per-module state of the middle row, for the status text. The first slot is
named separately because it is the propulsion module, which runs on its own rule
(`propulsionModuleShouldBeRunning`) rather than with the rest of the row.
-}
describeModulesToActivateAlways : ReadingFromGameClient -> String
describeModulesToActivateAlways readingFromGameClient =
    case readingFromGameClient.shipUI of
        Nothing ->
            "Middle-row modules: no ship UI."

        Just shipUI ->
            let
                describeOne moduleButton =
                    case moduleButton.isActive of
                        Just True ->
                            "on"

                        Just False ->
                            "off"

                        Nothing ->
                            -- No ramps widget on the button, which on this
                            -- client means it has not been switched on yet.
                            "off (never run)"
            in
            case shipUI.moduleButtonsRows.middle |> List.sortBy (.uiNode >> .totalDisplayRegion >> .x) of
                [] ->
                    "Middle-row modules: none."

                propulsionModule :: rest ->
                    "Middle-row modules: prop mod "
                        ++ describeOne propulsionModule
                        ++ ", keep-active ["
                        ++ (rest |> List.map describeOne |> String.join ", ")
                        ++ "]."


{-| What the weapons' own dict entries say, per module, every reading.

The mission runner's clause, ported because saxrat's own Unverified note for
#154 asks for exactly this reading and cannot get it: that run could not say
whether the guns came back, and `switchOffUndoneByClient` is a latch derived
from `isInActiveState` with nothing printing the field it derives from. The
parser has carried all twelve entries in this app since they were added; nothing
here has ever printed one.

`isInActiveState` is printed beside `ramp_active` rather than instead of it,
because it is what makes `ramp_active` readable at all: `False` there means
"between cycles" while the gun is on and "not running" once it is off, and only
the switched-on flag separates those two. The switch-off leg is exactly where
they disagree, and that leg is what #154 could not see.

`-` is an entry **absent from the tree**, printed differently from `0` and `F`
on purpose. Absent and `False` are different facts and both were seen live: no
module carried `ramp_active` for the first ~60s of the mission runner's sample,
and `waitingForActiveTarget` appeared on all four modules at once at 141s. A
format collapsing them would drop the transition worth recording. (An entry
present but undecodable also prints `-`.)

Sorted by position rather than taken in list order, for
`describeModulesToActivateAlways`' reason: the row is not a stable index space,
so two readings taken in list order can put one gun's values in another's
column.

**Read by the status line and by no decision**, which is the whole of its
placement -- `weaponIsSwitchedOn` and the ammo swap's own mapping are the only
things in this bot that read a dict entry, and both go through
`moduleReadsSwitchedOn` / `moduleReadsSwitchedOff` rather than naming a field.

-}
describeTopRowModuleDictState : ReadingFromGameClient -> String
describeTopRowModuleDictState readingFromGameClient =
    let
        describeFlag maybeFlag =
            case maybeFlag of
                Just True ->
                    "T"

                Just False ->
                    "F"

                Nothing ->
                    "-"

        describeNumber maybeNumber =
            case maybeNumber of
                Just number ->
                    String.fromInt number

                Nothing ->
                    "-"

        describeOne moduleButton =
            [ describeFlag moduleButton.stateFromDictEntries.ramp_active
            , describeFlag moduleButton.stateFromDictEntries.isInActiveState
            , describeFlag moduleButton.stateFromDictEntries.isDeactivating
            , describeNumber moduleButton.stateFromDictEntries.effect_activating
            , describeNumber moduleButton.stateFromDictEntries.waitingForActiveTarget
            ]
                |> String.join "/"
    in
    case readingFromGameClient.shipUI of
        Nothing ->
            "topmods no ship UI."

        Just shipUI ->
            case shipUI.moduleButtonsRows.top |> List.sortBy (.uiNode >> .totalDisplayRegion >> .x) of
                [] ->
                    "topmods none."

                topRowModules ->
                    "topmods (ramp_active/isInActiveState/isDeactivating/effect_activating/waitingForActiveTarget) "
                        ++ (topRowModules |> List.map describeOne |> String.join " ")
                        ++ "."


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt
