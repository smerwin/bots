{- EVE Online wing goose 2023-03-30

    Adapted from anomaly bot; all bugs introduced are my own damn fault

   This bot follows fleet warps and shoots rats.

   ## Features

   + Automatically detects if another pilot is in an anomaly on arrival and switches to another anomaly if necessary.
   + Filtering for specific anomalies using bot settings.
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

   An `avoid-rat` setting used to be listed here, and this bot never parsed it. The bullet
   and the example line below were inherited from the combat anomaly bot this one was
   adapted from, and the parser was not: `parseBotSettings` has no entry for the key and
   `BotSettings` has no field for it. So a settings string copied out of this header was
   **rejected** with `Unknown setting name 'avoid-rat'`, and since a settings parse error
   ends the session, the bot stopped before it started. Delete the line if a settings file
   still carries one.

   The documentation is deleted rather than the setting implemented. `eve-online-saxrat`
   and `eve-online-combat-anomaly-bot` do implement it, at _anomaly_ granularity -- they
   abandon the whole anomaly a named rat was seen in -- and whether this bot wants that
   rule has never been established. It can be added if it is ever wanted.

   A `hated-rat` setting used to be accepted here too, and removed for #195's reason
   rather than #161's: this one parsed and had a real reader, `getPriorityRatsSeenInAnomaly`
   -- and nothing ever called that reader, so an operator who set it got a bot that
   behaved exactly as if they had not, with no error to say so. #125's mission-runner
   case was the same shape one step shallower (parsed and never read at all); this one
   passed the usual "is this field read anywhere" check, because a real reader existed,
   was written, and type-checked. Delete the line if a settings file still carries one.

   + `anomaly-name` : Choose the name of anomalies to take. You can use this setting multiple times to select multiple names.
   + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat.
   + `activate-module-always` : Text found in tooltips of ship modules that should always be active. For example: "shield hardener".
   + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.

   When using more than one setting, start a new line for each setting in the text input field.
   Here is an example of a complete settings string:

   ```
   anomaly-name = Drone Patrol
   anomaly-name = Drone Horde
   hide-when-neutral-in-local = yes
   activate-module-always = shield hardener
   ```

   To learn more about the anomaly bot, see <https://to.botlab.org/guide/app/eve-online-combat-anomaly-bot>

-}
{-
   catalog-tags:eve-online,anomaly,ratting
   authors-forum-usernames:viir
-}


module Bot exposing
    ( State
    , botMain
    )

import BotLab.BotInterface_To_Host_2023_02_06 as InterfaceToHost
import Common.AppSettings as AppSettings
import Common.Basics exposing (listElementAtWrappedIndex, stringContainsIgnoringCase)
import Common.DecisionPath exposing (describeBranch)
import Common.EffectOnWindow as EffectOnWindow exposing (MouseButton(..))
import Dict
import EveOnline.BotFramework
    exposing
        ( ModuleButtonTooltipMemory
        , ReadingFromGameClient
        , SeeUndockingComplete
        , ShipModulesMemory
        , UseContextMenuCascadeNode(..)
        , doEffectsClickModuleButton
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
        , UpdateMemoryContext
        , askForHelpToGetUnstuck
        , branchDependingOnDockedOrInSpace
        , decideActionForCurrentStep
        , ensureInfoPanelLocationInfoIsExpanded
        , useContextMenuCascade
        , useContextMenuCascadeOnListSurroundingsButton
        , useContextMenuCascadeOnOverviewEntry
        , waitForProgressInGame
        )
import EveOnline.MemoryReading
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindowEntry
        , ShipUI
        , ShipUIModuleButton
        )
import Json.Decode
import Set


defaultBotSettings : BotSettings
defaultBotSettings =
    { runAwayShieldHitpointsThresholdPercent = 35
    , hideWhenNeutralInLocal = AppSettings.No
    , anomalyNames = []
    , activateModulesAlways = []
    , maxTargetCount = 5
    , botStepDelayMilliseconds = 900
    , anomalyWaitTimeSeconds = 15
    , orbitInCombat = AppSettings.No
    }


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    AppSettings.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "run-away-shield-hitpoints-threshold-percent"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayShieldHitpointsThresholdPercent = threshold })
           )
         , ( "hide-when-neutral-in-local"
           , AppSettings.valueTypeYesOrNo
                (\hide settings -> { settings | hideWhenNeutralInLocal = hide })
           )
         , ( "anomaly-name"
           , AppSettings.valueTypeString
                (\anomalyName settings ->
                    { settings | anomalyNames = String.trim anomalyName :: settings.anomalyNames }
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
         , ( "bot-step-delay"
           , AppSettings.valueTypeInteger
                (\delay settings ->
                    { settings | botStepDelayMilliseconds = delay }
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
    { runAwayShieldHitpointsThresholdPercent : Int
    , hideWhenNeutralInLocal : AppSettings.YesOrNo
    , anomalyNames : List String
    , activateModulesAlways : List String
    , maxTargetCount : Int
    , anomalyWaitTimeSeconds : Int
    , botStepDelayMilliseconds : Int
    , orbitInCombat : AppSettings.YesOrNo
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , shipWarpingInLastReading : Maybe Bool
    , visitedAnomalies : Dict.Dict String MemoryOfAnomaly
    }


type alias MemoryOfAnomaly =
    { arrivalTime : { milliseconds : Int }
    , otherPilotsFoundOnArrival : List String
    , ratsSeen : Set.Set String
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory


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


anomalyBotDecisionRoot : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRoot context =
    anomalyBotDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


anomalyBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRootBeforeApplyingSettings context =
    generalSetupInUserInterface context.previousStepEffects context.readingFromGameClient
        |> Maybe.withDefault
            (branchDependingOnDockedOrInSpace
                { ifDocked =
                    continueIfShouldHide
                        { ifShouldHide =
                            describeBranch "Stay docked." waitForProgressInGame
                        }
                        context
                        |> Maybe.withDefault (undockUsingStationWindow context)
                , ifSeeShipUI =
                    always
                        (continueIfShouldHide
                            { ifShouldHide =
                                returnDronesToBay context
                                    |> Maybe.withDefault
                                        (describeBranch
                                            "Dock to station or structure."
                                            (dockAtRandomStationOrStructure context)
                                        )
                            }
                            context
                        )
                , ifUndockingComplete = decideNextActionWhenInSpace context
                }
                context
            )


generalSetupInUserInterface :
    List EffectOnWindow.EffectOnWindowStructure
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
generalSetupInUserInterface previousStepEffects readingFromGameClient =
    [ closeMessageBox, ensureInfoPanelLocationInfoIsExpanded previousStepEffects ]
        |> List.filterMap
            (\maybeSetupDecisionFromGameReading ->
                maybeSetupDecisionFromGameReading readingFromGameClient
            )
        |> List.head


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
                                    (mouseClickOnUIElement MouseButtonLeft buttonToUse.uiNode)
                                )
                    )
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

        chooseNextMenuEntry =
            { describeChoice = "Use 'Dock' if available or a random entry."
            , chooseEntry =
                pickEntryFromLastContextMenuInCascade
                    (\menuEntries ->
                        let
                            suitableMenuEntries =
                                List.filter menuEntryIsSuitable menuEntries
                        in
                        [ withTextContainingIgnoringCase "dock"
                        , List.filter (.text >> stringContainsIgnoringCase "station")
                            >> Common.Basics.listElementAtWrappedIndex
                                (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                        , Common.Basics.listElementAtWrappedIndex
                            (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                        ]
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                    )
            }
    in
    useContextMenuCascadeOnListSurroundingsButton
        (useMenuEntryWithTextContainingFirstOf [ "stations", "structures" ]
            (MenuEntryWithCustomChoice chooseNextMenuEntry
                (MenuEntryWithCustomChoice chooseNextMenuEntry
                    (MenuEntryWithCustomChoice chooseNextMenuEntry MenuCascadeCompleted)
                )
            )
        )
        context


decideNextActionWhenInSpace : BotDecisionContext -> SeeUndockingComplete -> DecisionPathNode
decideNextActionWhenInSpace context seeUndockingComplete =
    if seeUndockingComplete.shipUI |> shipUIIndicatesShipIsWarpingOrJumping then
        describeBranch "I see we are warping."
            ([ returnDronesToBay context
             , readShipUIModuleButtonTooltips context
             ]
                |> List.filterMap identity
                |> List.head
                |> Maybe.withDefault waitForProgressInGame
            )

    else
        case context |> knownModulesToActivateAlways |> List.filter (Tuple.second >> moduleIsActiveOrReloading >> not) |> List.head of
            Just ( inactiveModuleMatchingText, inactiveModule ) ->
                describeBranch ("I see inactive module '" ++ inactiveModuleMatchingText ++ "' to activate always. Activate it.")
                    (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)

            Nothing ->
                let
                    returnDronesAndEnterAnomalyOrWait =
                        describeBranch "Wait for a fleet warp." waitForProgressInGame
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
                                    (decideActionInAnomaly
                                        { arrivalInAnomalyAgeSeconds = arrivalInAnomalyAgeSeconds }
                                        context
                                        seeUndockingComplete
                                        returnDronesAndEnterAnomalyOrWait
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
                    describeBranch "Click on the button to undock."
                        (decideActionForCurrentStep
                            (mouseClickOnUIElement MouseButtonLeft undockButton)
                        )


decideActionInAnomaly :
    { arrivalInAnomalyAgeSeconds : Int }
    -> BotDecisionContext
    -> SeeUndockingComplete
    -> DecisionPathNode
    -> DecisionPathNode
decideActionInAnomaly { arrivalInAnomalyAgeSeconds } context seeUndockingComplete continueIfCombatComplete =
    let
        overviewEntriesToAttack =
            seeUndockingComplete.overviewWindows
                |> List.concatMap .entries
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
                |> List.filter shouldAttackOverviewEntry

        overviewEntriesToLock =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsDisplayed
                |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

        targetsToUnlock =
            if overviewEntriesToAttack |> List.any overviewEntryIsActiveTarget then
                []

            else
                context.readingFromGameClient.targets |> List.filter .isActiveTarget

        ensureShipIsOrbitingDecision =
            overviewEntriesToAttack
                |> List.head
                |> Maybe.andThen (\overviewEntryToAttack -> ensureShipIsOrbiting seeUndockingComplete.shipUI overviewEntryToAttack)

        waitTimeRemainingSeconds =
            context.eventContext.botSettings.anomalyWaitTimeSeconds - arrivalInAnomalyAgeSeconds

        decisionIfNoEnemyToAttack =
            if overviewEntriesToAttack |> List.isEmpty then
                if waitTimeRemainingSeconds <= 0 then
                    returnDronesToBay context
                        |> Maybe.withDefault
                            (describeBranch "No drones to return." continueIfCombatComplete)

                else
                    describeBranch
                        ("Wait before considering the anomaly finished: " ++ String.fromInt waitTimeRemainingSeconds ++ " seconds")
                        waitForProgressInGame

            else
                describeBranch "Wait for target locking to complete." waitForProgressInGame

        decisionToKillRats =
            case targetsToUnlock |> List.head of
                Just targetToUnlock ->
                    describeBranch "I see a target to unlock."
                        (useContextMenuCascade
                            ( "locked target", targetToUnlock.barAndImageCont |> Maybe.withDefault targetToUnlock.uiNode )
                            (useMenuEntryWithTextContaining "unlock" menuCascadeCompleted)
                            context
                        )

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
                                            (lockTargetFromOverviewEntry
                                                nextOverviewEntryToLock
                                                context
                                            )
                                )

                        Just _ ->
                            describeBranch "I see a locked target."
                                (case seeUndockingComplete |> shipUIModulesToActivateOnTarget |> List.filter (.isActive >> Maybe.withDefault False >> not) |> List.head of
                                    Nothing ->
                                        describeBranch "All attack modules are active."
                                            (launchAndEngageDrones context
                                                |> Maybe.withDefault
                                                    (describeBranch "No idling drones."
                                                        (if context.eventContext.botSettings.maxTargetCount <= (context.readingFromGameClient.targets |> List.length) then
                                                            describeBranch "Enough locked targets." waitForProgressInGame

                                                         else
                                                            case overviewEntriesToLock of
                                                                [] ->
                                                                    describeBranch "I see no more overview entries to lock." waitForProgressInGame

                                                                nextOverviewEntryToLock :: _ ->
                                                                    describeBranch "Lock more targets."
                                                                        (lockTargetFromOverviewEntry
                                                                            nextOverviewEntryToLock
                                                                            context
                                                                        )
                                                        )
                                                    )
                                            )

                                    Just inactiveModule ->
                                        describeBranch "I see an inactive module to activate on targets. Activate it."
                                            (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)
                                )
    in
    if context.eventContext.botSettings.orbitInCombat == AppSettings.Yes then
        ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToKillRats

    else
        decisionToKillRats


ensureShipIsOrbiting : ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsOrbiting shipUI overviewEntryToOrbit =
    Nothing



{- -- if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverOrbit then
   --     Nothing

   -- else
   --     Just
   --         (describeBranch "Press the 'W' key and click on the overview entry."
   --             (decideActionForCurrentStep
   --                 ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_W ]
   --                  , overviewEntryToOrbit.uiNode |> mouseClickOnUIElement MouseButtonLeft
   --                  , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_W ]
   --                  ]
   --                     |> List.concat
   --                 )
   --             )
   --         )
-}


launchAndEngageDrones : BotDecisionContext -> Maybe DecisionPathNode
launchAndEngageDrones context =
    Nothing


returnDronesToBay : BotDecisionContext -> Maybe DecisionPathNode
returnDronesToBay context =
    Nothing


lockTargetFromOverviewEntry : OverviewWindowEntry -> BotDecisionContext -> DecisionPathNode
lockTargetFromOverviewEntry overviewEntry context =
    describeBranch ("Lock target from overview entry '" ++ (overviewEntry.objectName |> Maybe.withDefault "") ++ "'")
        (useContextMenuCascadeOnOverviewEntry
            (useMenuEntryWithTextEqual "Lock target" menuCascadeCompleted)
            overviewEntry
            context
        )


readShipUIModuleButtonTooltips : BotDecisionContext -> Maybe DecisionPathNode
readShipUIModuleButtonTooltips =
    EveOnline.BotFrameworkSeparatingMemory.readShipUIModuleButtonTooltipWhereNotYetInMemory


knownModulesToActivateAlways : BotDecisionContext -> List ( String, EveOnline.ParseUserInterface.ShipUIModuleButton )
knownModulesToActivateAlways context =
    context.readingFromGameClient.shipUI
        |> Maybe.map .moduleButtons
        |> Maybe.withDefault []
        |> List.filterMap
            (\moduleButton ->
                moduleButton
                    |> EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton context.memory.shipModules
                    |> Maybe.andThen (tooltipLooksLikeModuleToActivateAlways context)
                    |> Maybe.map (\moduleName -> ( moduleName, moduleButton ))
            )


tooltipLooksLikeModuleToActivateAlways : BotDecisionContext -> ModuleButtonTooltipMemory -> Maybe String
tooltipLooksLikeModuleToActivateAlways context =
    .allContainedDisplayTextsWithRegion
        >> List.filterMap
            (\( tooltipText, _ ) ->
                context.eventContext.botSettings.activateModulesAlways
                    |> List.filterMap
                        (\moduleToActivateAlways ->
                            if tooltipText |> stringContainsIgnoringCase moduleToActivateAlways then
                                Just tooltipText

                            else
                                Nothing
                        )
                    |> List.head
            )
        >> List.head


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
    }


statusTextFromState : BotDecisionContext -> String
statusTextFromState context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        describePerformance =
            "Visited anomalies: " ++ (context.memory.visitedAnomalies |> Dict.size |> String.fromInt) ++ "."

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
                            "Shield HP at " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%."

                        describeDrones =
                            case readingFromGameClient.dronesWindow of
                                Nothing ->
                                    "no drones lol"

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
                    in
                    [ [ describeShip ]
                    , [ describeDrones ]
                    , [ describeAnomaly, describeOverview ]
                    ]
                        |> List.map (String.join " ")
    in
    [ [ describePerformance ]
    , describeCurrentReading
    ]
        |> List.concat
        |> String.join "\n"


clickModuleButtonButWaitIfClickedInPreviousStep : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUIModuleButton -> DecisionPathNode
clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton =
    if doEffectsClickModuleButton moduleButton context.previousStepEffects then
        describeBranch "Already clicked on this module button in previous step." waitForProgressInGame

    else
        describeBranch "Click on this module button."
            (decideActionForCurrentStep
                (mouseClickOnUIElement MouseButtonLeft moduleButton.uiNode)
            )


overviewEntryIsTargetedOrTargeting : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsTargetedOrTargeting overviewEntry =
    overviewEntry.commonIndications.targetedByMe || overviewEntry.commonIndications.targeting


overviewEntryIsActiveTarget : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsActiveTarget =
    .namesUnderSpaceObjectIcon
        >> Set.member "myActiveTargetIndicator"


shouldAttackOverviewEntry : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry overviewEntry =
    iconSpriteHasColorOfRat overviewEntry && overviewEntryDistanceIsOnGrid overviewEntry


{-| The overview shows a distance in AU once an object is far enough away, and
distance parsing understands only "m" and "km" -- so an AU distance is an
`Err`, and nothing measured in AU is within targeting range in the first
place. Excluded here, at the one point that decides what counts as something
to shoot, rather than at each place that would otherwise try to lock it.
-}
overviewEntryDistanceIsOnGrid : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryDistanceIsOnGrid overviewEntry =
    case overviewEntry.objectDistanceInMeters of
        Ok _ ->
            True

        Err _ ->
            False


{-| The widget's own `_display` flag, defaulting to shown when absent (most
nodes never set it).
-}
nodeIsDisplayed : EveOnline.MemoryReading.UITreeNode -> Bool
nodeIsDisplayed uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


{-| The overview virtualises: every object in space has an entry in the UI
tree, but only the rows that fit are rendered, and the rest keep whatever
position they last held while recycled. A hidden entry reports a plausible
region pointing at a row that now belongs to something else, so locking it is
worse than a no-op -- it locks the wrong object. `_display` is what
distinguishes them; the region does not.
-}
overviewEntryIsDisplayed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    nodeIsDisplayed entry.uiNode.uiNode


moduleIsActiveOrReloading : EveOnline.ParseUserInterface.ShipUIModuleButton -> Bool
moduleIsActiveOrReloading moduleButton =
    (moduleButton.isActive |> Maybe.withDefault False)
        || ((moduleButton.rampRotationMilli |> Maybe.withDefault 0) /= 0)


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
        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

        shipIsWarping =
            shipWarpingFromReading context.readingFromGameClient

        namesOfRatsInOverview =
            getNamesOfRatsInOverview context.readingFromGameClient

        weJustFinishedWarping =
            warpJustEnded
                { warpingLastReading = botMemoryBefore.shipWarpingInLastReading
                , readingNow = context.readingFromGameClient
                }

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


shipUIModulesToActivateOnTarget : SeeUndockingComplete -> List ShipUIModuleButton
shipUIModulesToActivateOnTarget =
    .shipUI >> .moduleButtonsRows >> .top


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt
