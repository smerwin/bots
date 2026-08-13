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

      + `anomaly-name` : Choose the name of anomalies to take. You can use this setting multiple times to select multiple names. Matched whole and ignoring case, so the name must be written as the probe scanner's own Name column shows it -- except that an entry ending in `*` matches any name starting with the rest of it, so `anomaly-name=Sansha*` takes every Sansha site. Note a wildcard cannot tell an easy site from one that will kill this ship: it matches Havens and Sanctums as readily as Burrows.
      + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat.
      + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. You can use this setting multiple times to select multiple names.
      + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.
      + `warp-at`: Distance in km to warp to when warping to an anomaly, e.g. `warp-at=30`. Must match one of the game client's own preset "Warp to Within" distances offered in that menu (typically 0, 5, 10, 15, 20, 30, 50, 70, 100) -- an arbitrary value will not match any menu entry and will leave the bot stuck. Defaults to 100.
      + `accept-fleet-invite-from`: Name of a pilot whose fleet invitations this bot should accept, exactly as the client writes it. You can use this setting multiple times to name several pilots. With no such setting the bot accepts no invitation at all and declines every dialog as it always has -- and note the client renders a fleet invitation as an ordinary message box, so before this setting existed the bot actively clicked 'No' on them. Accepting means the fleet commander can warp this ship, so name only pilots you would hand the ship to.
      + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping range or aligning.
      + `keep-at-range`: Set this to 'yes' to keep range from the target instead of orbiting or aligning.
      + `targeting-range`: Maximum distance in meters to lock a target from the overview, e.g. `targeting-range=50000`. Beyond this, the bot approaches instead of locking. Defaults to 66000. This is a starting value, not the last word: the bot narrows it during the session from the client's own answers -- the greatest distance at which a lock was accepted and the smallest at which one was provably refused -- and the setting is clamped between the two. Set it to pin the starting point; it still gives way to what the client has actually granted. See `lockRangeThresholdInMeters`.
      + `max-targets`: How many rats to hold locked at once, e.g. `max-targets=6`. Defaults to 4. This is a starting value, not the last word: the client states its own maximum on the game log -- `You are already managing 6 targets, as many as you have skill to.` -- and the target bar proves a floor by holding that many, so the bot raises or lowers this from what the client has actually granted. With no evidence it is exactly the setting. Until the client has stated its maximum the bot asks for one more than it believes in, once per reading it has a row to spare, because that sentence is only written when a lock is attempted beyond the cap. See `maxTargetsCeiling` and `maxTargetsRowsToTake`.
      + `hunt-system`: Name of a solar system to hunt anomalies in, e.g. `hunt-system=Irnin`. Use it several times to give the bot a circuit. When a system has nothing left worth hunting and no route is set, the bot asks the host to set the autopilot destination to the next system on this list and flies there on its own. Without this setting the bot behaves as it always did: it parks and waits for a human to set a route.
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
    , anomalyNames = [ "sansha rally point", "angel rally point" ]
    , avoidRats = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , anomalyWaitTimeSeconds = 600
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No
    , warpAt = 100
    , targetingRangeMeters = 66000

    -- The two gauges above ship disabled, so before this setting existed the
    -- shipped configuration had no retreat at all. This one is armed by
    -- default because it is the guard that depends on no gauge: it reads the
    -- client's own combat log, which states what hit the ship and for how
    -- much, where `hitpointsPercent` is a float scraped out of a widget the
    -- client is concurrently mutating.
    , runAwayIncomingDamageThreshold = defaultRunAwayIncomingDamageThreshold

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
                (\systemName settings ->
                    { settings | huntSystemNames = settings.huntSystemNames ++ [ String.trim systemName ] }
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
         , ( "run-away-incoming-damage-threshold"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayIncomingDamageThreshold = threshold })
           )
         , ( "anomaly-name"
           , AppSettings.valueTypeString
                (\anomalyName settings ->
                    { settings | anomalyNames = String.trim anomalyName :: settings.anomalyNames }
                )
           )
         , ( "avoid-rat"
           , AppSettings.valueTypeString
                (\ratToAvoid settings ->
                    { settings | avoidRats = String.trim ratToAvoid :: settings.avoidRats }
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
so the separator cannot eat part of a name. That claim is not load-bearing all
the same: every setting that uses this is _also_ repeatable, so a name this
splitter would cut can still be given a line of its own. The design does not
rest on the naming rules being remembered correctly.

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
    , warpAt : Int
    , targetingRangeMeters : Int
    , runAwayIncomingDamageThreshold : Int
    , huntSystemNames : List String
    , homeSystemName : Maybe String
    , shortRangeAmmoName : Maybe String
    , longRangeAmmoName : Maybe String
    , ammoSwapRangeMeters : Maybe Int
    , acceptFleetInviteFrom : List String
    , followFleetBroadcastFrom : List String
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , shipWarpingInLastReading : Maybe Bool

    -- How many readings ago the last warp finished, which is what opens the
    -- arrival window the other-pilot snapshot is taken inside. `Nothing` means
    -- no warp has finished this session and is a closed window, never an open
    -- one. See `otherPilotArrivalWindowReadings`.
    , readingsSinceWarpEnded : Maybe Int
    , visitedAnomalies : Dict.Dict String MemoryOfAnomaly
    , contextMenuLastDepth : Int
    , contextMenuStuckTicks : Int
    , lootWindowOpenTicks : Int
    , routeFirstMarkerRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , routeFirstMarkerUnchangedTicks : Int
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
    , destinationAskReadings : Int
    , routeSettingGivenUp : Bool

    -- What the client has answered about how far this ship can lock, and the
    -- lock still waiting for an answer. Both bounds move one way only, so no
    -- oscillation is possible; `lockRangeLastChange` holds a sentence only on
    -- the reading a bound moved, which is what makes one line per change need
    -- no "already reported" flag. See `lockRangeThresholdInMeters`.
    , lockAttempt : Maybe LockAttempt
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


findReasonToIgnoreProbeScanResult : BotDecisionContext -> EveOnline.ParseUserInterface.ProbeScanResult -> Maybe ReasonToIgnoreProbeScanResult
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
                    (context.eventContext.botSettings.anomalyNames |> List.isEmpty)
                        || (probeScanResult.cellsTexts
                                |> Dict.get "Name"
                                |> Maybe.map
                                    (\name ->
                                        context.eventContext.botSettings.anomalyNames
                                            |> List.any (anomalyNameMatches name)
                                    )
                                |> Maybe.withDefault False
                           )
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


findReasonToAvoidAnomalyFromMemory : BotDecisionContext -> { anomalyID : String } -> Maybe ReasonToAvoidAnomaly
findReasonToAvoidAnomalyFromMemory context { anomalyID } =
    case memoryOfAnomalyWithID anomalyID context.memory of
        Nothing ->
            Nothing

        Just memoryOfAnomaly ->
            case memoryOfAnomaly.otherPilotsFoundOnArrival of
                otherPilotFoundOnArrival :: _ ->
                    Just (FoundOtherPilotOnArrival otherPilotFoundOnArrival)

                [] ->
                    let
                        ratsToAvoidSeen =
                            getRatsToAvoidSeenInAnomaly context.eventContext.botSettings memoryOfAnomaly
                    in
                    case ratsToAvoidSeen |> Set.toList of
                        ratToAvoid :: _ ->
                            Just (FoundRatToAvoid ratToAvoid)

                        [] ->
                            Nothing


getRatsToAvoidSeenInAnomaly : BotSettings -> MemoryOfAnomaly -> Set.Set String
getRatsToAvoidSeenInAnomaly settings =
    .ratsSeen >> Set.filter (shouldAvoidRatAccordingToSettings settings)


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
                context.readingFromGameClient
                |> Maybe.withDefault
                    (recoverPodAfterShipLoss context
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
                                                            { ifShouldHide =
                                                                returnDronesToBay context
                                                                    (dockAtRandomStationOrStructure context)
                                                            }
                                                            context
                                                            |> Maybe.withDefault
                                                                (decideNextActionWhenInSpace context { shipUI = shipUI })
                                                        )
                                        }
                                        context.readingFromGameClient
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
else here is answerable from the reading alone and stays that way.

**This whole list is evaluated above the docked-or-in-space split**, so anything
in it that can repeat forever freezes the entire bot rather than one branch.
That is #101 in the mission runner and #138 here. `closeMessageBox` is the one
entry with a bound of its own and may not lose it; the other two are unbounded,
which is why `endSessionOnAnExpiredBound` is asked above this list rather than
below it.

-}
generalSetupInUserInterface : Maybe MessageBoxStandoff -> List String -> ReadingFromGameClient -> Maybe DecisionPathNode
generalSetupInUserInterface messageBoxStandoff acceptFleetInviteFrom readingFromGameClient =
    [ closeSystemSettingsMenu
    , closeMessageBox messageBoxStandoff acceptFleetInviteFrom
    , ensureInfoPanelLocationInfoIsExpanded
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
"close the active window". It acts on the _focused_ window, and the mission
runner's loot window paid for that lesson already -- a version that pressed it
at an unfocused window managed 650 presses in one run and closed nothing, and
the live recovery needed the window's title bar clicked first. Clicking an
unidentified modal to focus it is a click into a dialog nobody has read, which
is the one thing `closeMessageBoxByDeclining` refuses to do.

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


{-| The banner naming the client's most recent fleet broadcast.

Found by the `_name` the client gives it rather than by position, because the
banner sits four containers deep and every one of those is a `Container` that
carries no other identity.

-}
fleetBroadcastBannerText : ReadingFromGameClient -> Maybe String
fleetBroadcastBannerText readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
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


{-| Where to go next, or `Nothing` if there is nowhere configured.

The circuit first, then `home-system` once every name on it has been visited.
"Visited" needs no record of its own: `huntSystemIndex` is advanced by the
memory update whenever the ship is standing in the system it points at, so a
full lap has happened exactly when the index has passed the end of the list.

-}
nextHuntingGround : BotDecisionContext -> Maybe String
nextHuntingGround context =
    nextHuntingGroundFrom context.eventContext.botSettings context.memory.huntSystemIndex


{-| The picker itself, over the two things it actually needs.

Split out because `updateMemoryForNewReadingFromGame` has to name the same
destination the decision will ask for, and it has the settings and the index
but no `BotDecisionContext`. Two copies of this choice would drift, and the
memory would then be counting readings against a system the bot was not asking
for.

-}
nextHuntingGroundFrom : BotSettings -> Int -> Maybe String
nextHuntingGroundFrom botSettings huntSystemIndex =
    let
        lapsCompleted =
            if List.isEmpty botSettings.huntSystemNames then
                0

            else
                huntSystemIndex // List.length botSettings.huntSystemNames
    in
    if 0 < lapsCompleted then
        case botSettings.homeSystemName of
            Just homeSystem ->
                Just homeSystem

            Nothing ->
                huntSystemAtIndex botSettings huntSystemIndex

    else
        huntSystemAtIndex botSettings huntSystemIndex


{-| Ask the host to set the autopilot destination, when there is nowhere to go.

This is the one branch that lets the bot originate a route. Everything else it
does with a route follows one that already exists -- set by a human, or by an
earlier pass through here -- and with no `hunt-system` configured the answer is
`tetherAtStructure`, exactly as before.

The ask is repeated every reading until the route panel shows something,
because the channel is unacknowledged: there is no reply to wait for, and the
client's own route panel is the confirmation. `routeAskGiveUpReadings` bounds
it, and the give-up latches for the session.

-}
setRouteToNextHuntingGround : BotDecisionContext -> DecisionPathNode
setRouteToNextHuntingGround context =
    if context.memory.routeSettingGivenUp then
        describeBranch
            ("Asked for a destination for more than "
                ++ String.fromInt routeAskGiveUpReadings
                ++ " readings and no route ever appeared -- this host does not set destinations, so stop asking and wait where it is safe."
            )
            (tetherAtStructure context)

    else
        case nextHuntingGround context of
            Nothing ->
                describeBranch
                    "Nothing left to hunt here and no route set. No 'hunt-system' is configured, so there is nowhere to ask for."
                    (tetherAtStructure context)

            Just systemName ->
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
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelRoute
        |> Maybe.map (.uiNode >> .uiNode >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts)
        |> Maybe.withDefault []
        |> List.any
            (\text ->
                text |> String.toLower |> String.contains routePanelNoDestinationMarker
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
            routeStargateJump
                { nextSystemOnRoute = nextSystemOnRouteFromReading context.readingFromGameClient
                , stargatesOnOverview =
                    context.readingFromGameClient.overviewWindows
                        |> List.concatMap .entries
                        |> List.filter overviewEntryIsDisplayed
                        |> List.filter overviewEntryIsAStargate
                        |> List.map
                            (\gate ->
                                { name = gate.objectName |> Maybe.withDefault ""
                                , panelIsShowingIt =
                                    selectedItemIsOverviewEntry context.readingFromGameClient gate
                                }
                            )
                , panelOffersJump = jumpButton /= Nothing
                }
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


runAway : BotDecisionContext -> DecisionPathNode
runAway =
    tetherAtStructure


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
                case context.readingFromGameClient |> localChatWindowFromUserInterface of
                    Nothing ->
                        Just (describeBranch "I don't see the local chat window." askForHelpToGetUnstuck)

                    Just localChatWindow ->
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
                        if 1 < (subsetOfUsersWithNoGoodStanding |> List.length) then
                            Just (describeBranch "There is an enemy or neutral in local chat." config.ifShouldHide)

                        else
                            Nothing


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
            "Quick message"
                ++ (if seen.readingsSince == 0 then
                        " (on screen now)"

                    else
                        " (NOT on screen now -- last seen "
                            ++ String.fromInt seen.readingsSince
                            ++ " readings ago)"
                   )
                ++ ": \""
                ++ quickMessageTextForStatusLine seen.text
                ++ "\""
                ++ (if String.length seen.text <= quickMessageStatusCharacterBudget then
                        ""

                    else
                        " (CAPPED at "
                            ++ String.fromInt quickMessageStatusCharacterBudget
                            ++ " of "
                            ++ String.fromInt (String.length seen.text)
                            ++ " characters)"
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
            (if seeUndockingComplete.shipUI |> shipUIIndicatesShipIsWarpingOrJumping then
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
                                        let
                                            scanResultsWithReasonToIgnore =
                                                probeScannerWindow.scanResults
                                                    |> List.map
                                                        (\scanResult ->
                                                            ( scanResult
                                                            , findReasonToIgnoreProbeScanResult context scanResult
                                                            )
                                                        )
                                        in
                                        case
                                            scanResultsWithReasonToIgnore
                                                |> List.filter (Tuple.second >> (==) Nothing)
                                                |> List.map Tuple.first
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
                                if
                                    anyAttackableInOverview (namesOfRecentAttackers context.memory.incomingDamage) context.readingFromGameClient
                                        || anyNotableWreckInOverview context.readingFromGameClient
                                        || (targetsToUnlockFromReadingFromGameClient context.readingFromGameClient |> List.isEmpty |> not)
                                then
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
                                                        describeBranch ("We are in anomaly '" ++ anomalyID ++ "' since " ++ String.fromInt arrivalInAnomalyAgeSeconds ++ " seconds.")
                                                            (case findReasonToAvoidAnomalyFromMemory context { anomalyID = anomalyID } of
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
        -- one. Taken from the in-range candidates rather than from
        -- `overviewEntriesToLock`, because a row out of range is answered by
        -- approaching it and an approach cannot be batched with anything -- and
        -- because both lists are sorted by distance, so where the nearest row is
        -- in range this batch begins with exactly the row a single lock would
        -- have clicked. Where it is not, `lockBatchSize` sees no lockable row
        -- and the single path approaches it, as ever.
        overviewEntriesToLockInOneStep : List OverviewWindowEntry
        overviewEntriesToLockInOneStep =
            overviewEntriesToLockInRange
                |> List.take
                    (lockBatchSize
                        (lockBatchSituationFrom context
                            { rowsLockableNow = overviewEntriesToLockInRange |> List.length
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

        targetsToUnlock =
            targetsToUnlockFromReadingFromGameClient context.readingFromGameClient

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

        decisionAfterLootingNotableWrecks =
            if waitTimeRemainingSeconds <= 0 then
                returnDronesToBay context
                    (describeBranch "No drones to return." continueIfCombatComplete)

            else
                describeBranch
                    ("Wait before considering the anomaly finished: " ++ String.fromInt waitTimeRemainingSeconds ++ " seconds")
                    (tetherAtStructure context)

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
                        -- not found) and just sits open forever. Once it
                        -- has stayed open for more than two ticks past
                        -- when we would have clicked "Loot All", force it
                        -- shut with Ctrl+W (EVE's own close-active-window
                        -- hotkey) instead of continuing to poke at the
                        -- window's own controls.
                        if context.memory.lootWindowOpenTicks > 2 then
                            describeBranch "Loot window did not close on its own -- force it shut (Ctrl+W)."
                                (decideActionForCurrentStep
                                    [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL
                                    , EffectOnWindow.KeyDown EffectOnWindow.vkey_W
                                    , EffectOnWindow.KeyUp EffectOnWindow.vkey_W
                                    , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL
                                    ]
                                )

                        else
                            case openInventoryWindow.uiNode |> findUiElementWithText "Loot All" of
                                Just lootAllButton ->
                                    describeBranch "Click 'Loot All'." (clickUiElement lootAllButton)

                                Nothing ->
                                    case
                                        openInventoryWindow.uiNode
                                            |> EveOnline.ParseUserInterface.parseWindowControlsFromWindow
                                            |> Maybe.andThen .closeButton
                                    of
                                        Just closeButton ->
                                            describeBranch "Nothing left to loot. Close the wreck's cargo window."
                                                (clickUiElement closeButton)

                                        Nothing ->
                                            describeBranch "I do not see a way to close this inventory window."
                                                askForHelpToGetUnstuck

                    Nothing ->
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
                                                                        -- Ditto above
                                                                        -- describeBranch "All locked up; bounce?" (tetherAtStructure context)
                                                                        revealEntryToLock
                                                                            |> Maybe.withDefault
                                                                                (describeBranch
                                                                                    (describeMaxTargetsNothingToLock maxTargetsProbeNow
                                                                                        "All locked up; bounce?"
                                                                                    )
                                                                                    waitForProgressInGame
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
                                            clickTargetBeforeShooting context overviewEntriesToAttack
                                                |> Maybe.withDefault
                                                    (describeBranch "Cycle combat mod"
                                                        (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
                                                    )
                                )
    in
    if context.eventContext.botSettings.orbitInCombat == AppSettings.Yes then
        ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToFight

    else if context.eventContext.botSettings.keepAtRange == AppSettings.Yes then
        ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToFight

    else
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
                                , findReasonToIgnoreProbeScanResult context scanResult
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
    "Drone launch ceiling: "
        ++ (droneLaunchCeiling state |> String.fromInt)
        ++ " (drones window says "
        ++ (state.fromWindow |> String.fromInt)
        ++ ", client stated "
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
                            Just
                                (describeBranch "Assist Gal if available, else engage target"
                                    (useContextMenuCascade
                                        ( "drones group", droneGroupInSpace.header.uiNode )
                                        (MenuEntryWithCustomChoice
                                            { describeChoice = "'Assist' if present, else 'Engage Target'"
                                            , chooseEntry =
                                                \currentMenu ->
                                                    case
                                                        currentMenu.entries
                                                            |> List.filter (.text >> stringContainsIgnoringCase "Assist")
                                                            |> List.head
                                                    of
                                                        Just assistEntry ->
                                                            Just
                                                                ( assistEntry
                                                                , useMenuEntryWithTextContaining "Gal Bistot" menuCascadeCompleted
                                                                )

                                                        Nothing ->
                                                            currentMenu.entries
                                                                |> List.filter (.text >> stringContainsIgnoringCase "Engage Target")
                                                                |> List.head
                                                                |> Maybe.map (\entry -> ( entry, menuCascadeCompleted ))
                                            }
                                        )
                                        context
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
`vkey_E` is the approach chord and `vkey_W` the orbit -- so the chord is
unambiguous.

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
    if List.isEmpty context.eventContext.botSettings.huntSystemNames then
        "Hunt circuit: none configured (no 'hunt-system'), so this bot waits for a route rather than setting one."

    else
        "Hunt circuit: "
            ++ (context.eventContext.botSettings.huntSystemNames |> String.join " -> ")
            ++ ", next "
            ++ (nextHuntingGround context |> Maybe.withDefault "nowhere")
            ++ (case context.memory.destinationAskedFor of
                    Nothing ->
                        ""

                    Just asked ->
                        ". Asked for '"
                            ++ asked
                            ++ "' "
                            ++ String.fromInt context.memory.destinationAskReadings
                            ++ "/"
                            ++ String.fromInt routeAskGiveUpReadings
                            ++ " readings ago with no route yet"
               )
            ++ (if context.memory.routeSettingGivenUp then
                    ". ROUTE SETTING GIVEN UP -- this host does not set destinations"

                else
                    ""
               )
            ++ "."


describeDroneRecall : BotDecisionContext -> String
describeDroneRecall context =
    "Drones: "
        ++ (context.memory.dronesInSpaceCountLastReading |> String.fromInt)
        ++ " in space ("
        ++ (context.memory.dronesInSpaceTicks |> String.fromInt)
        ++ " readings), unanswered recall "
        ++ (context.memory.droneRecallUnansweredTicks |> String.fromInt)
        ++ "/"
        ++ (droneRecallGiveUpTicks |> String.fromInt)
        ++ (if droneRecallGiveUpTicks < context.memory.droneRecallUnansweredTicks then
                " GIVEN UP -- the ship will leave without them"

            else
                ""
           )
        ++ "."


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

            else
                describeBranch ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away). Approach.")
                    (decideActionForCurrentStep
                        ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_E ]
                         , overviewEntry.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
                         , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_E ]
                         ]
                            |> List.concat
                        )
                    )

        Err error ->
            describeBranch ("Failed to read the distance: " ++ error) askForHelpToGetUnstuck


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


{-| Everything the batch size is a function of.

`rowsToTake` is `maxTargetsRowsToTake`'s answer rather than the ceiling, so the
batch and `Enough locked targets.` cannot come to disagree about whether there
is room; `rowsLockableNow` counts only rows the ship can lock from where it is
standing, since a row out of range is answered by approaching and an approach
cannot be batched with anything.

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
    , provenAtMeters : Maybe Int
    , refusedAtMeters : Maybe Int
    , attempt : Maybe LockAttempt
    }


lockRangeStateFrom : BotDecisionContext -> LockRangeState
lockRangeStateFrom context =
    { fromSetting = context.eventContext.botSettings.targetingRangeMeters
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
    in
    case state.provenAtMeters of
        Nothing ->
            loweredByRefusal

        Just provenAt ->
            max provenAt loweredByRefusal


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
(`lockChordForOverviewEntry`). Ctrl is pressed in two other places here and
neither can be mistaken for it: `ctrlShiftClickUiElement`, the unlock, holds
Shift as well, and the loot window's Ctrl+W carries no mouse effect at all, so
there is no `MouseMoveTo` for this to take. Both conditions are checked rather
than only the first -- the Ctrl+W case is a saxrat-only chord, and a bot that
grew a third one should fail to attribute rather than attribute wrongly.

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
    "Lock range: "
        ++ (lockRangeThresholdInMeters state |> String.fromInt)
        ++ " m (setting "
        ++ (state.fromSetting |> String.fromInt)
        ++ ", proven "
        ++ (state.provenAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ", refused "
        ++ (state.refusedAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ", attempt "
        ++ (state.attempt
                |> Maybe.map (\attempt -> String.fromInt attempt.distanceInMeters ++ " m for " ++ String.fromInt attempt.readingsWaited ++ " readings")
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
    "Lock batch: up to "
        ++ (lockBatchMaximumClicks |> String.fromInt)
        ++ " clicks a step, asked "
        ++ (state.clicksAsked |> String.fromInt)
        ++ " and the bar answered "
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


{-| The maximum the client stated on this reading, if it stated one.

`You are already managing 6 targets, as many as you have skill to.` on
`(notify)` -- the channel `loadRefusalFromGameLog` already reads, so this needed
no new plumbing. 228 distinct entries across the recorded runs of both apps, and
491 across the client's own game logs.

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
                    && stringContainsIgnoringCase maxTargetsSkillMarker entry.text
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
    "Max targets: "
        ++ (maxTargetsCeiling state |> String.fromInt)
        ++ " (setting "
        ++ (state.fromSetting |> String.fromInt)
        ++ ", client stated "
        ++ (state.statedByClient |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ", most held at once "
        ++ (state.heldAtOnce |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ (case state.statedByClient of
                Just _ ->
                    ""

                Nothing ->
                    ", probing for " ++ (maxTargetsCeiling state + 1 |> String.fromInt)
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
    , readingsSinceWarpEnded = Nothing
    , visitedAnomalies = Dict.empty
    , contextMenuLastDepth = 0
    , contextMenuStuckTicks = 0
    , lootWindowOpenTicks = 0
    , routeFirstMarkerRegion = Nothing
    , routeFirstMarkerUnchangedTicks = 0
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
    , destinationAskReadings = 0
    , routeSettingGivenUp = False
    , lockAttempt = Nothing

    -- No evidence yet, in both directions -- which is a different fact from
    -- "the client refused at 0 m", and is why these are `Maybe Int` rather
    -- than a defaulted number. With both absent the threshold is exactly the
    -- setting, so a session that learns nothing behaves as it always did.
    , lockProvenAtMeters = Nothing
    , lockRefusedAtMeters = Nothing
    , lockRangeLastChange = Nothing
    , lockBatch = Nothing
    , lockBatchClicksAsked = 0
    , lockBatchClicksAnswered = 0
    , lockBatchLastChange = Nothing
    , targetsCountLastReading = 0
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

`isInActiveState` is the entry that means switched on, measured rather than
assumed: across 92 samples of a 240 s window it held `True` on all four modules
while `ramp_active` oscillated fourteen times underneath it, so `ramp_active` is
the duty cycle and this is the state.

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
overview click and the swap's own right-click, so the client re-arms the gun by
itself, and a rule that abandons on that is a guarantee that no swap can ever
finish. What replaces abandoning is nothing, and the invariant is what makes that
safe: this is true exactly when the guns are back on, which is the moment the
swap stops costing anything the deadlines exist to protect.

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
toggle is on, which is what the entry measurably means and is exactly the
condition the client's own refusal names: `while it is active`. Reading
`Just True` as "the guns are working" would be the mistake `ramp_active` has
already cost twice.

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
            "Context menus open: "
                ++ (readingFromGameClient.contextMenus |> List.length |> String.fromInt)
                ++ " (cascade level "
                ++ (context.contextMenuCascadeLevel |> String.fromInt)
                ++ ", stuck ticks "
                ++ (context.memory.contextMenuStuckTicks |> String.fromInt)
                ++ "). Route marker unchanged ticks: "
                ++ (context.memory.routeFirstMarkerUnchangedTicks |> String.fromInt)
                ++ ". Target-to-unlock unchanged ticks: "
                ++ (context.memory.targetToUnlockUnchangedTicks |> String.fromInt)
                ++ ". Loot window open ticks: "
                ++ (context.memory.lootWindowOpenTicks |> String.fromInt)
                ++ ". No scan results and no route last time in space: "
                ++ (if context.memory.noProbeScanResultsAndNoRouteLastTimeInSpace then
                        "yes"

                    else
                        "no"
                   )
                ++ ". Approaching ticks: "
                ++ (context.memory.shipApproachingTicks |> String.fromInt)
                ++ ". "
                ++ describeGateActivationAsk
                    { asked = askingAnAccelerationGateToOpen readingFromGameClient
                    , gateWithinReach = accelerationGateIsWithinReach readingFromGameClient
                    , askedReadings = context.memory.gateWithinReachTicks
                    }
                ++ ". Wrecks already opened: "
                ++ (context.memory.lootedWreckIds |> List.length |> String.fromInt)
                ++ ". "
                ++ describeModulesToActivateAlways readingFromGameClient
                ++ "\n"
                ++ describeIncomingDamage context
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
                    [ "I do not see the ship UI. Looks like we are docked." ]

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
                            readingFromGameClient.overviewWindows
                                |> List.concatMap .entries
                                |> List.filter overviewEntryIsActiveTarget
                                |> List.head
                                |> Maybe.andThen .objectName

                        describeAnomaly =
                            "Current anomaly: "
                                ++ (getCurrentAnomalyIDAsSeenInProbeScanner readingFromGameClient |> Maybe.withDefault "None")
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
                            "Rats in overview: " ++ (namesOfRatsInOverview |> List.length |> String.fromInt) ++ "."

                        describeCurrentTarget =
                            case currentTargetName of
                                Nothing ->
                                    -- No condition clause here: there is
                                    -- nothing whose condition it would be.
                                    "Current target: None."

                                Just name ->
                                    "Current target: "
                                        ++ name
                                        ++ " "
                                        ++ describeTargetHitpoints
                                            (activeTargetHitpointsPercent readingFromGameClient)
                                        ++ "."
                    in
                    [ [ describeShip ]
                    , [ describeDrones ]
                    , [ describeAnomaly, describeArrivalWindowClause, describeOverview ]
                    , [ describeRatsInOverview, describeCurrentTarget ]
                    ]
                        |> List.map (String.join " ")
    in
    [ [ describePerformance ]
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
opened at all, forcing it to Ctrl+W-close a window the player never
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


overviewEntryIsStrayLockTarget : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsStrayLockTarget overviewEntry =
    let
        textsToCheck =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
    in
    [ "container", "wreck" ]
        |> List.any (\pattern -> textsToCheck |> List.any (stringContainsIgnoringCase pattern))


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
            "(Shield/Armor/Hull unknown)"

        Just percent ->
            "(Shield: "
                ++ (percent.shield |> String.fromInt)
                ++ "%  Armor: "
                ++ (percent.armor |> String.fromInt)
                ++ "%  Hull: "
                ++ (percent.structure |> String.fromInt)
                ++ "%)"


{-| Safety net for the weapon/drone-activation branches, independent of the
Target<->overview name matching `targetsToUnlockFromReadingFromGameClient`
relies on (so a gap in that matching doesn't also sneak past this check):
whether the overview row for whichever target EVE currently reports as
"active" -- the one weapons and drones actually go to when activated, since
neither one lets you choose which locked target to hit -- looks like a
container or wreck rather than a rat.
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
target's own text sidesteps the question entirely). Checking substrings
directly on the target bar's own text removes that cross-tree assumption.
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
                                |> List.any (\pattern -> stringContainsIgnoringCase pattern text)
                        )
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
`siteProgressStep`** -- the gate is asked before the opportunity warp now, and a
"Warp to Site" offered while a gate is in reach is declined as the panel still
showing the site the ship is standing in. The reading of the corpus that made
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


{-| Takes the nearest acceleration gate, to move on to the next pocket.

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
    case
        context.readingFromGameClient.overviewWindows
            |> List.concatMap .entries
            |> List.filter isAccelerationGate
            |> List.filter overviewEntryIsDisplayed
            |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
            |> List.head
    of
        Nothing ->
            -- Either there is no gate at all, or the only one is scrolled out
            -- of the overview -- where its reported region belongs to whatever
            -- row is recycled into its place, so it cannot be clicked.
            scrollOverviewToReveal context isAccelerationGate

        Just accelerationGateEntry ->
            let
                distanceInMeters =
                    accelerationGateEntry.objectDistanceInMeters |> Result.withDefault 999999

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
there is no reading of the panel that separates them. An acceleration gate is a
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

**Both still outrank the probe-scan hunt loop**, which is all the comment at the
call site ever claimed and is compatible with either order -- what it never said
is which of the pair wins, and the code answered "the first one, always" because
its condition is almost always true. `HuntWithTheProbeScanner` is reached only
where the gate branch has nothing to do and the button is either absent or being
offered to a ship that is standing on a gate.

-}
type SiteProgressStep
    = WorkTheAccelerationGate
    | WarpToTheOpportunitySite
    | HuntWithTheProbeScanner


siteProgressStep :
    { gateBranchOffersAStep : Bool
    , warpToSiteIsOffered : Bool
    , gateWithinReach : Bool
    }
    -> SiteProgressStep
siteProgressStep progressCase =
    if progressCase.gateBranchOffersAStep then
        WorkTheAccelerationGate

    else if progressCase.warpToSiteIsOffered && not progressCase.gateWithinReach then
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
            warpToOpportunitySiteIfAvailable context.readingFromGameClient
    in
    case
        siteProgressStep
            { gateBranchOffersAStep = accelerationGateStep /= Nothing
            , warpToSiteIsOffered = opportunityWarpStep /= Nothing
            , gateWithinReach = accelerationGateIsWithinReach context.readingFromGameClient
            }
    of
        WorkTheAccelerationGate ->
            accelerationGateStep |> Maybe.withDefault ifNeither

        WarpToTheOpportunitySite ->
            opportunityWarpStep |> Maybe.withDefault ifNeither

        HuntWithTheProbeScanner ->
            ifNeither


{-| The "Opportunities" panel (e.g. "Sansha's Command Relay Outpost") is a
separate mechanism from the probe-scanner anomalies this bot otherwise
hunts -- confirmed live it has no existing parsing anywhere in this
codebase. Rather than adding a dedicated parser for that whole panel, this
just looks for a clickable "Warp to Site" button anywhere on screen (the
same generic whole-tree text search already proven for the "Loot All" and
message-box-close buttons) and clicks it directly.

**What that search answers is "an opportunity exists", never "the ship still
needs to go there"**, because the panel goes on offering the button after
arrival. Narrowing the search is not the repair -- the button legitimately stays
drawn, and a search trying to tell "offered" from "already taken" would be
guessing at panel state this bot deliberately does not parse. `siteProgressStep`
is what separates them, off the grid rather than off the panel, and carries the
measurement.

-}
warpToOpportunitySiteIfAvailable : ReadingFromGameClient -> Maybe DecisionPathNode
warpToOpportunitySiteIfAvailable readingFromGameClient =
    readingFromGameClient.uiTree
        |> findUiElementWithText "Warp to Site"
        |> Maybe.map
            (\warpToSiteButton ->
                describeBranch "I see a 'Warp to Site' opportunity -- warp there."
                    (clickUiElement warpToSiteButton)
            )


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


{-| Double-click a UI element. EVE reads a double click on an object in space
or its overview row as "Open Cargo", which is the whole context-menu cascade --
right-click, wait for the flyout to render, find the entry, click it -- in a
single step.
-}
doubleClickUiElement : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
doubleClickUiElement uiElement =
    decideActionForCurrentStep
        (EveOnline.BotFramework.mouseDoubleClickOnUIElement MouseButtonLeft uiElement
            |> Result.withDefault []
        )


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

-}
strayContextMenuStuckTicksThreshold : Int
strayContextMenuStuckTicksThreshold =
    3


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
3 and so is `strayContextMenuStuckTicksThreshold`, and `menuOpenOnGunAtX` answers
only where the right-click was the immediately previous step, so most of those
readings look from here exactly like a menu nobody is driving. Escape would then
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
            (context.readingFromGameClient.shipUI /= Nothing)
                && (currentRouteFirstMarkerRegion == Nothing)
                && (context.readingFromGameClient.probeScannerWindow
                        |> Maybe.map (.scanResults >> List.isEmpty)
                        |> Maybe.withDefault True
                   )

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
            context.readingFromGameClient
                |> targetsToUnlockFromReadingFromGameClient
                |> List.head
                |> Maybe.map (\target -> (target.barAndImageCont |> Maybe.withDefault target.uiNode).totalDisplayRegion)

        currentSolarSystemName =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .currentSolarSystemName
                |> Maybe.map String.trim

        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

        shipIsWarping =
            shipWarpingFromReading context.readingFromGameClient

        namesOfRatsInOverview =
            getNamesOfRatsInOverview context.readingFromGameClient

        incomingDamageNow =
            updateIncomingDamageMemory context hitpoints botMemoryBefore.incomingDamage

        lockRangeLearning =
            updateLockRangeLearning (lockRangeReadingFrom context)
                { fromSetting = context.botSettings.targetingRangeMeters
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
    , readingsSinceWarpEnded = readingsSinceWarpEnded
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
        -- the pointer past it, so the picker below can never name the system
        -- the ship is already in. A simple "first name that is not here"
        -- would ping-pong between the first two entries and never reach the
        -- third.
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
    , destinationAskedFor =
        -- What the decision branch is asking for, named by the *same* picker it
        -- uses. Forgotten the moment a route exists, so arriving and going dry
        -- again asks afresh rather than reading as already asked.
        --
        -- Tracked only while the ship is in space with no route and nothing at
        -- all on the probe scanner -- which is narrower than the condition the
        -- ask itself fires on (that one is "no anomaly *matching the
        -- settings*"). Narrower is the safe direction and the same one
        -- `noProbeScanResultsAndNoRouteLastTimeInSpace` above argues for: the
        -- counter advances only in a state where the branch is certainly
        -- asking, so it can under-count and delay the give-up, and can never
        -- run up while the bot is happily fighting in a system it has anomalies
        -- in. Counting that would be issue #11's mistake again -- a counter
        -- measuring something other than the thing it bounds.
        if standingInADeadEnd then
            nextHuntingGroundFrom context.botSettings botMemoryBefore.huntSystemIndex

        else
            Nothing
    , destinationAskReadings =
        if standingInADeadEnd then
            botMemoryBefore.destinationAskReadings + 1

        else
            0
    , routeSettingGivenUp =
        -- Latched for the session. A host with no ESI credentials, or one that
        -- does not read the directive at all, will never answer -- and a bot
        -- that keeps asking is one that never goes back to hunting.
        botMemoryBefore.routeSettingGivenUp
            || (routeAskGiveUpReadings < botMemoryBefore.destinationAskReadings)
    , lockBatch = lockBatchAccounting.dispatch
    , lockBatchClicksAsked = lockBatchAccounting.clicksAsked
    , lockBatchClicksAnswered = lockBatchAccounting.clicksAnswered
    , lockBatchLastChange = lockBatchAccounting.change
    , targetsCountLastReading = context.readingFromGameClient.targets |> List.length
    , lockAttempt = lockRangeLearning.attempt
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
    .probeScannerWindow
        >> Maybe.map getScanResultsForSitesOnGrid
        >> Maybe.withDefault []
        >> List.head
        >> Maybe.andThen (.cellsTexts >> Dict.get "ID")


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


{-| A real pilot on grid also shows up by name in the Local chat
userlist; a rat/NPC never does. Cross-referencing overview entries
against Local is how the sibling `eve-online-wingus` bot already does
this (ported verbatim from there -- same `ChatWindow`/`ChatUserEntry`
shape in this bot's own `ParseUserInterface.elm`).
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


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt
