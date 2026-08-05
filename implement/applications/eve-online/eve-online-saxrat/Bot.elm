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

      + `anomaly-name` : Choose the name of anomalies to take. You can use this setting multiple times to select multiple names.
      + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat.
      + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. You can use this setting multiple times to select multiple names.
      + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.
      + `warp-at`: Distance in km to warp to when warping to an anomaly, e.g. `warp-at=30`. Must match one of the game client's own preset "Warp to Within" distances offered in that menu (typically 0, 5, 10, 15, 20, 30, 50, 70, 100) -- an arbitrary value will not match any menu entry and will leave the bot stuck. Defaults to 100.
      + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping range or aligning.
      + `keep-at-range`: Set this to 'yes' to keep range from the target instead of orbiting or aligning.
      + `targeting-range`: Maximum distance in meters to lock a target from the overview, e.g. `targeting-range=50000`. Beyond this, the bot approaches instead of locking. Defaults to 66000. This is a starting value, not the last word: the bot narrows it during the session from the client's own answers -- the greatest distance at which a lock was accepted and the smallest at which one was provably refused -- and the setting is clamped between the two. Set it to pin the starting point; it still gives way to what the client has actually granted. See `lockRangeThresholdInMeters`.
      + `hunt-system`: Name of a solar system to hunt anomalies in, e.g. `hunt-system=Irnin`. Use it several times to give the bot a circuit. When a system has nothing left worth hunting and no route is set, the bot asks the host to set the autopilot destination to the next system on this list and flies there on its own. Without this setting the bot behaves as it always did: it parks and waits for a human to set a route.
      + `home-system`: Name of the solar system to fall back to once every `hunt-system` has been tried, e.g. `home-system=Amarr`. Optional, and only consulted after the circuit is exhausted.
      + `run-away-incoming-damage-threshold`: Hitpoints of incoming damage, summed from the client's own combat log over a rolling 45-second window, past which the bot breaks off and runs. Unlike the two hitpoint settings above this needs no HUD gauge, which is the point of it: the gauge is scraped out of the client's live memory and produces values like 2132822% and a spurious 0%. Defaults to 3500, calibrated against sixteen recorded sessions of one hull -- the worst any session the ship survived absorbed was 3114, and the session it was lost in peaked at 4101. **That is a number about a hull, not about the game**, so re-derive it for a different ship. Set to -1 to disable.

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
         ]
            |> Dict.fromList
        )
        defaultBotSettings


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
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , shipWarpingInLastReading : Maybe Bool
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
                        || (context.eventContext.botSettings.anomalyNames
                                |> List.any
                                    (\anomalyName ->
                                        probeScanResult.cellsTexts
                                            |> Dict.get "Name"
                                            |> Maybe.map (String.toLower >> (==) (anomalyName |> String.toLower |> String.trim))
                                            |> Maybe.withDefault False
                                    )
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


shouldAvoidRatAccordingToSettings : BotSettings -> String -> Bool
shouldAvoidRatAccordingToSettings settings ratName =
    settings.avoidRats |> List.map String.toLower |> List.member (ratName |> String.toLower)


memoryOfAnomalyWithID : String -> BotMemory -> Maybe MemoryOfAnomaly
memoryOfAnomalyWithID anomalyID =
    .visitedAnomalies >> Dict.get anomalyID


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
                context.readingFromGameClient
                |> Maybe.withDefault
                    (recoverPodAfterShipLoss context
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
generalSetupInUserInterface : Maybe MessageBoxStandoff -> ReadingFromGameClient -> Maybe DecisionPathNode
generalSetupInUserInterface messageBoxStandoff readingFromGameClient =
    [ closeSystemSettingsMenu
    , closeMessageBox messageBoxStandoff
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


closeMessageBox : Maybe MessageBoxStandoff -> ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox standoff readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.andThen
            (\messageBox ->
                case messageBoxStandoffVerdict standoff of
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

The identity is cut to `messageBoxGiveUpIdentityLength` because it carries the
box's whole rendered text, and a dialog with a paragraph in it would otherwise
push the rest of the sentence off whatever the operator is reading.

-}
describeMessageBoxGivenUpOn : String -> String
describeMessageBoxGivenUpOn identity =
    "Nothing closes this "
        ++ (if messageBoxGiveUpIdentityLength < String.length identity then
                String.left messageBoxGiveUpIdentityLength identity ++ "..."

            else
                identity
           )
        ++ " -- answered it "
        ++ String.fromInt messageBoxAnswersBeforeEscape
        ++ " readings running and then pressed Escape at it for another "
        ++ String.fromInt (messageBoxStandoffGiveUpReadings - messageBoxAnswersBeforeEscape)
        ++ ", and it is still there. Leaving it open and getting on with the rest of the bot rather than answering it forever -- it needs closing by hand."


{-| How much of a box's identity the give-up line prints.
-}
messageBoxGiveUpIdentityLength : Int
messageBoxGiveUpIdentityLength =
    200


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
over the last few seconds, which is the question the status text wants; anything
needing history should read the gamelog file instead.

The markup is EVE's own colour and font tagging, stripped here because the
status text is read by a human in a terminal.

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


{-| The combat feed for the status text, newest last, capped so a busy fight
does not push everything else out of view.
-}
describeVisibleCombatMessages : ReadingFromGameClient -> String
describeVisibleCombatMessages readingFromGameClient =
    case visibleCombatMessages readingFromGameClient of
        [] ->
            "Combat feed: quiet."

        messages ->
            let
                shown =
                    messages |> List.reverse |> List.take 6 |> List.reverse

                omitted =
                    List.length messages - List.length shown
            in
            "Combat feed"
                ++ (if 0 < omitted then
                        " (" ++ String.fromInt omitted ++ " older not shown)"

                    else
                        ""
                   )
                ++ ":\n  "
                ++ String.join "\n  " shown


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

Printed on every reading, including the ones with nothing to report, for
`describeVisibleCombatMessages`' reason: a clause that appears only when there is
something to say leaves "the client said nothing" and "nothing is reading the
client" grepping identically, and telling those apart is the first thing #123
wants from a run.

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
                                        { arrivalInAnomalyAgeSeconds = 600 }
                                        context
                                        seeUndockingComplete
                                        (jumpToNextSystem context)
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
                                    pickAnotherAnomalyOrLeave =
                                        warpToOpportunitySiteIfAvailable context.readingFromGameClient
                                            |> Maybe.withDefault
                                                (activateAccelerationGateIfPresent context
                                                    |> Maybe.withDefault pickAnotherAnomalyOrLeaveViaScanResults
                                                )
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
                            describeBranch "Click on the button to undock."
                                (decideActionForCurrentStep
                                    (mouseClickOnUIElement MouseButtonLeft undockButton
                                        |> Result.withDefault []
                                    )
                                )

                        Just _ ->
                            describeBranch "I see we are already undocking." waitForProgressInGame


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
        overviewEntriesToLock =
            if (List.length <| overviewEntriesToAttackFirst) > 0 then
                overviewEntriesToAttackFirst
                    |> List.filter overviewEntryIsDisplayed
                    |> List.take 2
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

            else
                overviewEntriesToAttack
                    |> List.filter overviewEntryIsDisplayed
                    |> List.take 4
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

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
                                                            (if context.eventContext.botSettings.maxTargetCount <= (context.readingFromGameClient.targets |> List.length) then
                                                                -- TODO branch if bouncing or brawling
                                                                -- describeBranch "Enough locked targets." (enterAnomaly { ifNoAcceptableAnomalyAvailable = tetherAtStructure context } context)
                                                                describeBranch "Enough locked targets." waitForProgressInGame

                                                             else
                                                                case overviewEntriesToLock of
                                                                    [] ->
                                                                        -- Ditto above
                                                                        -- describeBranch "All locked up; bounce?" (tetherAtStructure context)
                                                                        revealEntryToLock
                                                                            |> Maybe.withDefault
                                                                                (describeBranch "All locked up; bounce?" waitForProgressInGame)

                                                                    nextOverviewEntryToLock :: _ ->
                                                                        describeBranch "Lock more targets."
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
        ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToKillRats

    else if context.eventContext.botSettings.keepAtRange == AppSettings.Yes then
        ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToKillRats

    else
        ensureShipIsAlignedDecision |> Maybe.withDefault decisionToKillRats


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

                            dronesInSpaceQuantityLimit =
                                droneGroupInSpace.header.quantityFromTitle
                                    |> Maybe.andThen .maximum
                                    |> Maybe.withDefault 2
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
                        (decideActionForCurrentStep
                            ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]
                             , overviewEntry.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
                             , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]
                             ]
                                |> List.concat
                            )
                        )

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


{-| The screen point a lock click went to, from the effects of one step.

The lock chord is Ctrl held over a plain left click
(`lockTargetFromOverviewEntry`). Ctrl is pressed in two other places here and
neither can be mistaken for it: `ctrlShiftClickUiElement`, the unlock, holds
Shift as well, and the loot window's Ctrl+W carries no mouse effect at all, so
there is no `MouseMoveTo` for this to take. Both conditions are checked rather
than only the first -- the Ctrl+W case is a saxrat-only chord, and a bot that
grew a third one should fail to attribute rather than attribute wrongly.

Reading the attempt out of the effects rather than out of the decision is not a
detour: `updateMemoryForNewReadingFromGame` is the only place that can write
memory, and it sees the previous steps' effects but not the decision that
produced them.

-}
lockClickLocationFromStepEffects : List EffectOnWindow.EffectOnWindowStruct -> Maybe EffectOnWindow.Location2d
lockClickLocationFromStepEffects effects =
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
            |> List.head

    else
        Nothing


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
            reading.lastStepEffects
                |> lockClickLocationFromStepEffects
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
    }


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
                ++ ". Ticks on an acceleration gate in reach: "
                ++ (context.memory.gateWithinReachTicks |> String.fromInt)
                ++ ". Wrecks already opened: "
                ++ (context.memory.lootedWreckIds |> List.length |> String.fromInt)
                ++ ". "
                ++ describeModulesToActivateAlways readingFromGameClient
                ++ "\n"
                ++ describeIncomingDamage context
                ++ " "
                ++ describeDroneRecall context
                ++ " "
                ++ describeHuntCircuit context
                ++ " "
                ++ describeLockRange (lockRangeStateFrom context)
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
                ++ (case context.memory.messageBoxStandoff of
                        Nothing ->
                            ""

                        Just standoff ->
                            -- #138's counter, and the one clause here that
                            -- keeps speaking after its branch has stopped:
                            -- once the give-up is reached `closeMessageBox`
                            -- answers `Nothing` and prints no decision line at
                            -- all, so this is the only thing on a reading that
                            -- says a box is still in front of the bot.
                            " Message box: "
                                ++ String.fromInt standoff.readings
                                ++ "/"
                                ++ String.fromInt messageBoxStandoffGiveUpReadings
                                ++ (case messageBoxStandoffVerdict (Just standoff) of
                                        AnswerTheMessageBox ->
                                            " (answering it)."

                                        PressEscapeAtTheMessageBox ->
                                            " (pressing Escape at it)."

                                        LeaveTheMessageBoxAlone ->
                                            " (GIVEN UP ON, still open)."
                                   )
                   )
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
                ++ "\n"
                ++ describeVisibleCombatMessages readingFromGameClient

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
                            "Current target: " ++ (currentTargetName |> Maybe.withDefault "None") ++ "."
                    in
                    [ [ describeShip ]
                    , [ describeDrones ]
                    , [ describeAnomaly, describeOverview ]
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
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.any
            (\entry ->
                (entry.objectDistanceInMeters |> Result.withDefault 999999)
                    <= interactionRangeInMeters
            )


{-| Right-clicks the nearest acceleration gate and activates it to move on to
the next pocket (EVE's own menu text for these is "Activate Gate", mirrored on
`jumpToNextSystem`'s "dock"/"jump" cascade for regular stargates).

From further out the same "Activate Gate" command is what gets issued: the
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
            in
            Just
                (if interactionRangeInMeters < distanceInMeters then
                    -- "Activate Gate" from out here does the whole thing: the
                    -- client flies the ship over and takes the gate on arrival,
                    -- with no tick spent noticing it has arrived. The drones
                    -- come home first, since the gate fires with whatever is
                    -- still in space; the prop mod stays on, so the ship covers
                    -- the distance fast.
                    ensureDronesRecalledBeforeWarping context
                        (closeInOnOverviewEntry context
                            { description =
                                "The acceleration gate is "
                                    ++ String.fromInt distanceInMeters
                                    ++ " m away -- activate it from here and let the client fly me in."
                            , menuEntries = [ "activate gate", "activate", "approach" ]
                            }
                            accelerationGateEntry
                        )

                 else if gateRefusesThisShipTicks < context.memory.gateWithinReachTicks then
                    describeBranch
                        ("I have been sitting on this acceleration gate for "
                            ++ String.fromInt context.memory.gateWithinReachTicks
                            ++ " readings and it has not taken me anywhere. It most likely will not admit this ship. Stopping rather than clicking it any longer."
                        )
                        askForHelpToGetUnstuck

                 else
                    describeBranch "I see an acceleration gate -- activate it to move to the next pocket."
                        (ensureDronesRecalledBeforeWarping context
                            (useContextMenuCascadeOnOverviewEntry
                                (useMenuEntryWithTextContainingFirstOf
                                    [ "activate gate", "activate" ]
                                    menuCascadeCompleted
                                )
                                accelerationGateEntry
                                context
                            )
                        )
                )


{-| How many readings to keep trying a gate that is already in range before
concluding it will not admit this ship. A working gate goes through in a few;
the mission bot hit a restricted one and clicked it 741 times over half an
hour, with no error dialog and nothing to notice.
-}
gateRefusesThisShipTicks : Int
gateRefusesThisShipTicks =
    40


{-| The "Opportunities" panel (e.g. "Sansha's Command Relay Outpost") is a
separate mechanism from the probe-scanner anomalies this bot otherwise
hunts -- confirmed live it has no existing parsing anywhere in this
codebase. Rather than adding a dedicated parser for that whole panel, this
just looks for a clickable "Warp to Site" button anywhere on screen (the
same generic whole-tree text search already proven for the "Loot All" and
message-box-close buttons) and clicks it directly.
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


{-| A "commander"- or "overseer"-type rat's wreck, worth sticking around to
loot before leaving the anomaly. Checks both name and type since which one
carries "Commander"/"Overseer" seems to vary; requires "wreck" in the type
so we don't also match the (still-living) commander/overseer rat itself
while it's on the overview.
-}
isNotableWreck : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isNotableWreck overviewEntry =
    let
        containsNotableRatName =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
                |> (\texts -> [ "commander", "overseer" ] |> List.any (\pattern -> texts |> List.any (stringContainsIgnoringCase pattern)))

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


{-| `Just` a decision to press Escape if a context menu has sat at the same
cascade depth (not advancing to a deeper submenu) for at least
`strayContextMenuStuckTicksThreshold` consecutive ticks; `Nothing`
otherwise, so callers can fall through to their normal decision tree.
-}
clearStrayContextMenu : BotDecisionContext -> Maybe DecisionPathNode
clearStrayContextMenu context =
    if strayContextMenuStuckTicksThreshold <= context.memory.contextMenuStuckTicks then
        Just
            (describeBranch
                "A context menu has sat at the same depth for several ticks in a row without advancing to a deeper submenu -- likely a stray menu from a misclick or a cascade stuck on a menu with no entry it recognizes. Clear it (Escape)."
                (decideActionForCurrentStep
                    [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                    , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                    ]
                )
            )

    else
        Nothing


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
            context.readingFromGameClient.shipUI
                |> Maybe.andThen .indication
                |> Maybe.andThen .maneuverType
                |> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverWarp)

        namesOfRatsInOverview =
            getNamesOfRatsInOverview context.readingFromGameClient

        lockRangeLearning =
            updateLockRangeLearning (lockRangeReadingFrom context)
                { fromSetting = context.botSettings.targetingRangeMeters
                , provenAtMeters = botMemoryBefore.lockProvenAtMeters
                , refusedAtMeters = botMemoryBefore.lockRefusedAtMeters
                , attempt = botMemoryBefore.lockAttempt
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
            (botMemoryBefore.shipWarpingInLastReading == Just True) && (shipIsWarping == Just False)

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
                                if weJustFinishedWarping then
                                    { anomalyMemoryBefore
                                        | otherPilotsFoundOnArrival = getNamesOfOtherPilotsInOverview context.readingFromGameClient
                                    }

                                else
                                    anomalyMemoryBefore

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
        -- Readings in a row with an acceleration gate close enough to use. A
        -- gate that works goes through in a handful of them; one that refuses
        -- the ship never goes through at all and reports no error, so counting
        -- them is what turns "clicking forever" into something the bot can act
        -- on. See `activateAccelerationGateIfPresent`.
        if accelerationGateIsWithinReach context.readingFromGameClient then
            botMemoryBefore.gateWithinReachTicks + 1

        else
            0
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
    , incomingDamage =
        updateIncomingDamageMemory context hitpoints botMemoryBefore.incomingDamage
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
    , lockAttempt = lockRangeLearning.attempt
    , lockProvenAtMeters = lockRangeLearning.provenAtMeters
    , lockRefusedAtMeters = lockRangeLearning.refusedAtMeters
    , lockRangeLastChange = lockRangeLearning.change
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
    .shipUI >> .moduleButtonsRows >> .top >> List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


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
