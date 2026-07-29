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
     + Hide passive modules by disabling the check-box `Display Passive Modules`.
   + Configure the keyboard key 'W' to make the ship orbit.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit your use-case.

   + `anomaly-name` : Choose the name of anomalies to take. You can use this setting multiple times to select multiple names.
   + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat.
   + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. You can use this setting multiple times to select multiple names.
   + `activate-module-always` : Text found in tooltips of ship modules that should always be active. For example: "shield hardener".
   + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.
   + `warp-at`: Distance in km to warp to when warping to an anomaly, e.g. `warp-at=30`. Must match one of the game client's own preset "Warp to Within" distances offered in that menu (typically 0, 5, 10, 15, 20, 30, 50, 70, 100) -- an arbitrary value will not match any menu entry and will leave the bot stuck. Defaults to 100.
   + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping range or aligning.
   + `keep-at-range`: Set this to 'yes' to keep range from the target instead of orbiting or aligning.
   + `targeting-range`: Maximum distance in meters to lock a target from the overview, e.g. `targeting-range=50000`. Beyond this, the bot approaches instead of locking. Defaults to 66000.

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
        , localChatWindowFromUserInterface
        , menuCascadeCompleted
        , infoPanelRouteFirstMarkerFromReadingFromGameClient
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
        , UpdateMemoryContext
        , askForHelpToGetUnstuck
        , branchDependingOnDockedOrInSpace
        , clickModuleButtonButWaitIfClickedInPreviousStep
        , decideActionForCurrentStep
        , ensureInfoPanelLocationInfoIsExpanded
        , discardContextMenuIfTooDistantFromTargetElement
        , useContextMenuCascade
        , useContextMenuCascadeOnListSurroundingsButton
        , useContextMenuCascadeOnOverviewEntry
        , useContextMenuCascadeWithCustomConfig
        , waitForProgressInGame
        )
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindowEntry
        , ShipUI
        , ShipUIModuleButton
        )
import Set
import EveOnline.ParseUserInterface exposing (FleetWindow)


defaultBotSettings : BotSettings
defaultBotSettings =
    { hideWhenNeutralInLocal = AppSettings.Yes
    , runAwayShieldHitpointsThresholdPercent = -1
    , runAwayArmorHitpointsThresholdPercent = -1
    , anomalyNames = ["sansha rally point", "angel rally point"]
    , avoidRats = []
    , activateModulesAlways = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , anomalyWaitTimeSeconds = 600
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No
    , warpAt = 100
    , targetingRangeMeters = 66000
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
         , ( "activate-module-always"
           , AppSettings.valueTypeString
                (\moduleName settings ->
                    { settings | activateModulesAlways = moduleName :: settings.activateModulesAlways }
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
    , activateModulesAlways : List String
    , maxTargetCount : Int
    , anomalyWaitTimeSeconds : Int
    , botStepDelayMilliseconds : Int
    , orbitInCombat : AppSettings.YesOrNo
    , keepAtRange : AppSettings.YesOrNo
    , warpAt : Int
    , targetingRangeMeters : Int
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
    }


type alias MemoryOfAnomaly =
    { arrivalTime : { milliseconds : Int }
    , otherPilotsFoundOnArrival : List String
    , ratsSeen : Set.Set String
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
                        |> Maybe.map (\text -> (text |> String.contains " AU"))
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
    anomalyBotDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


anomalyBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRootBeforeApplyingSettings context =
    generalSetupInUserInterface context.readingFromGameClient
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
                                            |> Maybe.withDefault (dockAtRandomStationOrStructure context)
                                    }
                                    context
                                    |> Maybe.withDefault
                                        (decideNextActionWhenInSpace context { shipUI = shipUI })
                                )
                }
                context.readingFromGameClient
            )

             

generalSetupInUserInterface : ReadingFromGameClient -> Maybe DecisionPathNode
generalSetupInUserInterface readingFromGameClient =
    [ closeSystemSettingsMenu, closeMessageBox, ensureInfoPanelLocationInfoIsExpanded ]
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
botlab_host.py's own input path entirely; a normal bot-driven click here
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


closeMessageBox : ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.map
            (\messageBox ->
                describeBranch "I see a message box to close."
                    (let
                        buttonCanBeUsedToClose =
                            .mainText
                                >> Maybe.map (String.trim >> String.toLower >> (\buttonText -> [ "close", "ok" ] |> List.member buttonText))
                                >> Maybe.withDefault False
                     in
                     case messageBox.buttons |> List.filter buttonCanBeUsedToClose |> List.head of
                        Nothing ->
                            describeBranch "I see no way to close this message box." askForHelpToGetUnstuck

                        Just buttonToUse ->
                            describeBranch ("Click on button '" ++ (buttonToUse.mainText |> Maybe.withDefault "") ++ "'.")
                                (decideActionForCurrentStep
                                    (mouseClickOnUIElement MouseButtonLeft buttonToUse.uiNode
                                        |> Result.withDefault []
                                    )
                                )
                    )
            )

jumpToNextSystem : BotDecisionContext -> DecisionPathNode
jumpToNextSystem context =
    case context.readingFromGameClient |> infoPanelRouteFirstMarkerFromReadingFromGameClient of
        Nothing ->
         tetherAtStructure context

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
                 |> Maybe.withDefault
                    ( useContextMenuCascadeWithCustomConfig
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
                    context )

runAwayIfLowHealth : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> Maybe DecisionPathNode
runAwayIfLowHealth context shipUI = 
    let 
        runAwayShieldThreshold = 
            context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent

        runAwayArmorThreshold = 
            context.eventContext.botSettings.runAwayArmorHitpointsThresholdPercent

        runAwayWithShieldDescription = 
            describeBranch 
            ("Shield HP " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%, get out get out")
            (runAway context)

        runAwayWithArmorDescription = 
            describeBranch 
            ("Armor at " ++ (shipUI.hitpointsPercent.armor |> String.fromInt) ++ "%, get out get out get out")
            (runAway context)
    in
    if shipUI.hitpointsPercent.shield < runAwayShieldThreshold then
        Just runAwayWithShieldDescription
    else if shipUI.hitpointsPercent.armor < runAwayArmorThreshold then
        Just runAwayWithArmorDescription
    else
      Nothing

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
        withTextContainingIgnoringCase textToSearch =
            List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head

        menuEntryIsSuitable menuEntry =
            [ "cyno beacon", "jump gate" ]
                |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
                |> not

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
                        , Common.Basics.listElementAtWrappedIndex (0)
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
        withTextContainingIgnoringCase textToSearch =
            List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head

        menuEntryIsSuitable menuEntry =
            [ "cyno beacon", "jump gate" ]
                |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
                |> not

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
                         , Common.Basics.listElementAtWrappedIndex (0)
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
                context)

{-| 2020-07-11 Discovery by Viktor:
The entries for structures in the menu from the SurroundingsButton can be nested one level deeper than the ones for stations.
In other words, not all structures appear directly under the "structures" entry.
-}

dockAtRandomStationOrStructure : BotDecisionContext -> DecisionPathNode
dockAtRandomStationOrStructure context =
    let
        withTextContainingIgnoringCase textToSearch =
            List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head

        menuEntryIsSuitable menuEntry =
            [ "cyno beacon", "jump gate" ]
                |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
                |> not

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
                            >> Common.Basics.listElementAtWrappedIndex (0)
                        , Common.Basics.listElementAtWrappedIndex (0)
                        ]
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                            |> Maybe.map (\menuEntry -> ( menuEntry, followingChoice ))
                }
    in
    returnDronesToBay context
    |> Maybe.withDefault
        (describeBranch "g'wan, git"
            (
                useContextMenuCascadeOnListSurroundingsButton
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
    clearStrayContextMenu context |> Maybe.withDefault
    (if seeUndockingComplete.shipUI |> shipUIIndicatesShipIsWarpingOrJumping then
        describeBranch "HOOOOONK in warp"
            ([ returnDronesToBay context
             ]
                |> List.filterMap identity
                |> List.head
                |> Maybe.withDefault waitForProgressInGame
            )

    else
    case context.readingFromGameClient.probeScannerWindow of
        Nothing ->
            describeBranch "No probe window" (
                case
                    if anyAttackableInOverview context.readingFromGameClient then
                        seeUndockingComplete |> shipUIModulesToActivateAlways |> List.filter (.isActive >> Maybe.withDefault False >> not) |> List.head

                    else
                        Nothing
                of
                        Just inactiveModule ->
                            describeBranch "Inactive module should be active"
                                (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)


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
                    if anyAttackableInOverview context.readingFromGameClient
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
                    case
                        if anyAttackableInOverview context.readingFromGameClient then
                            seeUndockingComplete |> shipUIModulesToActivateAlways |> List.filter (.isActive >> Maybe.withDefault False >> not) |> List.head

                        else
                            Nothing
                    of
                        Just inactiveModule ->
                            describeBranch "This module should always be active"
                                (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)


                        Nothing ->
                            let
                                returnDronesAndEnterAnomaly { ifNoAcceptableAnomalyAvailable } =
                                    returnDronesToBay context
                                        |> Maybe.withDefault
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
            overviewEntriesToAttackFromReadingFromGameClient context.readingFromGameClient
        overviewEntriesToAttackFirst =
            overviewEntriesToAttack 
                |> List.filter shouldAttackOverviewEntryFirst

        overviewEntriesToLock =
            if (List.length <| overviewEntriesToAttackFirst) > 0 then 
                overviewEntriesToAttackFirst
                    |> List.take 2
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)
                else
                overviewEntriesToAttack
                    |> List.take 4
                    |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

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

        notableWreckEntries =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter isNotableWreck
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        -- Extra time budget (beyond anomalyWaitTimeSeconds) to spend
        -- looting commander/overseer wrecks before giving up and leaving
        -- anyway -- a bounded timeout rather than tracking which specific
        -- wrecks we've already looted, since a looted wreck stays on the
        -- overview (just empty) with no clean way to tell from here.
        -- Re-looting an empty wreck is harmless, just wasted ticks, so
        -- the timeout is the actual guard against getting stuck forever.
        lootWreckTimeRemainingSeconds =
            (context.eventContext.botSettings.anomalyWaitTimeSeconds + 120) - arrivalInAnomalyAgeSeconds

        decisionAfterLootingNotableWrecks =
            if waitTimeRemainingSeconds <= 0 then
                returnDronesToBay context
                    |> Maybe.withDefault
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
                                    describeBranch "Open commander/overseer wreck's cargo before leaving."
                                        (useContextMenuCascadeOnOverviewEntry
                                            (useMenuEntryWithTextContainingFirstOf
                                                [ "Loot All", "Open Cargo" ]
                                                menuCascadeCompleted
                                            )
                                            wreckToLoot
                                            context
                                        )

                            [] ->
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
                                    (waitForProgressInGame)


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
                                                                        describeBranch "All locked up; bounce?" waitForProgressInGame

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
                                            describeBranch "Cycle combat mod"
                                                (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
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
                 ("Within " ++ (context.eventContext.botSettings.warpAt |> String.fromInt) ++ " km")
            in
            case
                scanResultsWithReasonToIgnore
                    |> List.filter (Tuple.second >> (==) Nothing)
                    |> List.map Tuple.first
                    -- |> listElementAtWrappedIndex (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                    |> listElementAtWrappedIndex (0)
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

returnDronesToBay : BotDecisionContext -> Maybe DecisionPathNode
returnDronesToBay context =
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
                            -- (useContextMenuCascade
                            --     ( "drones group", droneGroupInLocalSpace.header.uiNode )
                            --     (useMenuEntryWithTextContaining "Assist" menuCascadeCompleted)
                            --     context
                            -- )
                        )
            )


lockTargetFromOverviewEntry : BotDecisionContext -> OverviewWindowEntry -> DecisionPathNode
lockTargetFromOverviewEntry context overviewEntry =
    let
        targetingRange : Int
        targetingRange =
            context.eventContext.botSettings.targetingRangeMeters
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
                ++ "."

        describeCurrentReading =
            case readingFromGameClient.shipUI of
                Nothing ->
                    [ "I do not see the ship UI. Looks like we are docked." ]

                Just shipUI ->
                    let
                        describeShip =
                            "Shield: " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "% "
                            ++ " Armor: " ++ (shipUI.hitpointsPercent.armor |> String.fromInt) ++ "%"

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


shouldAttackOverviewEntry : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry =
    iconSpriteHasColorOfRat


{-| Factored out of decideActionInAnomaly's own overviewEntriesToAttack /
targetsToUnlock let-bindings so updateMemoryForNewReadingFromGame can
compute the same "target to unlock" identity from just a reading (no bot
settings needed) -- used to track how long it's stayed in the same place,
see routeFirstMarkerUnchangedTicks-style tracking on BotMemory below.
-}
overviewEntriesToAttackFromReadingFromGameClient : ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
overviewEntriesToAttackFromReadingFromGameClient readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.filter shouldAttackOverviewEntry


{-| Whether the ship's own persistent cargo-hold "Inventory" window (open
throughout this whole session, same as the probe scanner/overview/drones
windows the bot's setup instructions call for) currently has a wreck's
loot showing, as opposed to just sitting on the ship's own hangar view.
`EveOnline.ParseUserInterface.InventoryWindow` has no dedicated field for
this (same gap noted at the "Loot All" text-search call site), and
`readingFromGameClient.inventoryWindows |> List.head` used to just grab
the window unconditionally -- since it's *always* present, that meant the
looting logic thought a wreck was open even when nothing had ever been
opened at all, forcing it to Ctrl+W-close a window the player never
wanted closed (stuck 650+ seconds live with zero rats and zero commander
wrecks anywhere in the overview).

First fix attempt here checked `leftTreeEntries |> List.isEmpty`, on the
assumption that opening a wreck's cargo shows a separate flat popup with
no hangar tree. Wrong, confirmed live immediately after shipping it: a
wreck opened via "Open Cargo" shows up as one more row *in the same
sidebar tree* as the ship's own hangar (Drone Bay, PLEX Vault, etc.), not
a separate window -- so `leftTreeEntries` is non-empty either way, and
that check excluded the real, already-open loot view every single tick,
which made the bot think "Open Cargo" had never been clicked and re-click
it forever even while the wreck's contents (and a working "Loot All"
button) were sitting right there on screen.

Checking for a findable "Loot All" button instead: not a structural
property of the window, but the actual thing this code needs to already
be true before it can act -- present only once a wreck is both open *and*
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
anyAttackableInOverview : ReadingFromGameClient -> Bool
anyAttackableInOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.any shouldAttackOverviewEntry


shouldAttackOverviewEntryFirst : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntryFirst overviewEntry = case overviewEntry.objectName of
    Nothing -> False
    Just objectName ->
        objectName |> String.contains "Tower"


{-| Matches the "Ancient Acceleration Gate" (and any other "* Acceleration
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


{-| Right-clicks the nearest acceleration gate and activates it to move on to
the next pocket. Priority list covers both the "already close enough" case
(EVE's own menu text for these is "Activate Gate", mirrored on
`jumpToNextSystem`'s "dock"/"jump" cascade for regular stargates) and the
"still need to close distance first" case (falls back to warping/
approaching, the same two-step pattern already proven live for
`tetherAtStructure`'s NPC-station fallback -- a later tick's fresh right-
click then finds "Activate Gate" once in range). Goes through
`ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping` first,
same as every other warp/tether action, since drones left behind in the
current pocket are stranded once the gate carries the ship to the next one.
-}
activateAccelerationGateIfPresent : BotDecisionContext -> Maybe DecisionPathNode
activateAccelerationGateIfPresent context =
    context.readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.head
        |> Maybe.map
            (\accelerationGateEntry ->
                describeBranch "I see an acceleration gate -- activate it to move to the next pocket."
                    (ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                        (useContextMenuCascadeOnOverviewEntry
                            (useMenuEntryWithTextContainingFirstOf
                                [ "activate gate", "activate", "warp to within", "approach" ]
                                menuCascadeCompleted
                            )
                            accelerationGateEntry
                            context
                        )
                    )
            )


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


anyNotableWreckInOverview : ReadingFromGameClient -> Bool
anyNotableWreckInOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
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
                    |> List.take 2
                    |> List.any (doEffectsPressKey keyCode)
            then
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
-}
ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping :
    BotDecisionContext
    -> DecisionPathNode
    -> DecisionPathNode
ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context ifReadyToWarp =
    returnDronesToBay context
        |> Maybe.withDefault
            (let
                -- Alt+F1 is a toggle on this keybind setup, not a
                -- dedicated "deactivate" -- confirmed live: pressing it
                -- unconditionally turned the prop mod back ON right
                -- before warping whenever it was already off. The
                -- propulsion module is the first module in the middle
                -- row (same row as the always-active tank modules,
                -- which is also why it used to fight
                -- shipUIModulesToActivateAlways -- see that check's own
                -- anyAttackableInOverview guard).
                propulsionModuleIsActive : Bool
                propulsionModuleIsActive =
                    context.readingFromGameClient.shipUI
                        |> Maybe.andThen (.moduleButtonsRows >> .middle >> List.head)
                        |> Maybe.andThen .isActive
                        |> Maybe.withDefault False
             in
             if not propulsionModuleIsActive then
                ifReadyToWarp

             else if
                context.previousStepsEffects
                    |> List.take 1
                    |> List.any doEffectsDeactivatePropulsionModule
             then
                -- Already pressed it last step; give the read a chance to
                -- catch up before checking again, rather than pressing
                -- (and re-toggling) a second time on a stale reading.
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
            )


{-| Number of consecutive ticks *any* context menu has been open before we
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

First replacement: count consecutive ticks where *some* menu -- any
menu, open regardless of whether it's literally the same instance --
has been open at all, resetting to 0 whenever `contextMenus` is empty.
That also turned out wrong, the opposite way: a genuine multi-level
cascade (e.g. a 3-deep menu select) keeps *some* menu open continuously
across every level, by design, until the final entry is clicked -- if
that takes more ticks than the threshold (real render/network latency
per level adds up over 3 levels), this fired mid-cascade and cancelled
real progress.

The actual fix: track cascade *depth*, not just presence. Context menus
nest -- descending a level adds one more entry to
`readingFromGameClient.contextMenus` rather than replacing it (this is
also how the framework's own `contextMenuCascadeLevel` works). So
`BotMemory.contextMenuStuckTicks` only increments when the menu count
has stayed the same (or dropped without reaching zero) since the last
reading; any tick that goes *deeper* than before resets it to 0,
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


updateMemoryForNewReadingFromGame : UpdateMemoryContext -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        currentRouteFirstMarkerRegion =
            context.readingFromGameClient
                |> infoPanelRouteFirstMarkerFromReadingFromGameClient
                |> Maybe.map (.uiNode >> .totalDisplayRegion)

        currentTargetToUnlockRegion =
            context.readingFromGameClient
                |> targetsToUnlockFromReadingFromGameClient
                |> List.head
                |> Maybe.map (\target -> (target.barAndImageCont |> Maybe.withDefault target.uiNode).totalDisplayRegion)

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


shipUIModulesToActivateOnTarget : SeeUndockingComplete -> List ShipUIModuleButton
shipUIModulesToActivateOnTarget =
    .shipUI >> .moduleButtonsRows >> .top

shipUIModulesToActivateAlways : SeeUndockingComplete -> List ShipUIModuleButton
shipUIModulesToActivateAlways =
    .shipUI >> .moduleButtonsRows >> .middle

nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt
