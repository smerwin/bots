{- EVE Online Combat Anomaly Bot version 2026-05-24

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
   + In the ship UI, arrange the modules:
     + Place the modules to use in combat (to activate on targets) in the top row.
     + Hide passive modules by disabling the check-box `Display Passive Modules`.
   + Configure the keyboard key 'W' to make the ship orbit.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit your use-case.

   + `anomaly-name` : Name of anomalies to select. Use this setting multiple times to select multiple names.
   + `hide-when-neutral-in-local` : Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat.
   + `avoid-rat` : Name of a rat to avoid by warping away. Enter the name as it appears in the overview. Use this setting multiple times to select multiple names.
   + `prioritize-rat` : Name of a rat to prioritize when locking targets. Enter the name as it appears in the overview. Use this setting multiple times to select multiple names.
   + `activate-module-always` : Text found in tooltips of ship modules that should always be active. For example: "shield hardener".
   + `anomaly-wait-time`: Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid.
   + `warp-to-anomaly-distance`: Defaults to 'Within 0 m'
   + `deactivate-module-on-warp` : Name of a module to deactivate when warping. Enter the name as it appears in the tooltip. Use this setting multiple times to select multiple modules.
   + `hide-location-name` : Name of a location to hide. Enter the name as it appears in the 'Locations' window.

   When using more than one setting, start a new line for each setting in the text input field.
   Here is an example of a complete settings string:

   ```
   anomaly-name = Drone Patrol
   anomaly-name = Drone Horde
   hide-when-neutral-in-local = yes
   avoid-rat = Infested Carrier
   activate-module-always = shield hardener
   hide-location-name = Dock me here
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

import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost
import Common
import Common.Basics exposing (listElementAtWrappedIndex, resultFirstSuccessOrFirstError, stringContainsIgnoringCase)
import Common.DecisionPath exposing (describeBranch)
import Common.EffectOnWindow as EffectOnWindow exposing (MouseButton(..))
import Common.PromptParser as PromptParser exposing (IntervalInt)
import Dict
import EveOnline.BotFramework
    exposing
        ( ModuleButtonTooltipMemory
        , OverviewWindowsMemory
        , ReadingFromGameClient
        , ShipModulesMemory
        , UseContextMenuCascadeNode(..)
        , localChatWindowFromUserInterface
        , menuCascadeCompleted
        , mouseClickOnUIElement
        , shipUIIndicatesShipIsWarpingOrJumping
        , uiNodeVisibleRegionLargeEnoughForClicking
        , useMenuEntryInLastContextMenuInCascade
        , useMenuEntryWithTextContaining
        , useMenuEntryWithTextContainingFirstOf
        , useMenuEntryWithTextContainingFirstOfCommonContinuation
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
        , ensureOverviewsSorted
        , useContextMenuCascade
        , useContextMenuCascadeOnListSurroundingsButton
        , useContextMenuCascadeOnOverviewEntry
        , waitForProgressInGame
        )
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindowEntry
        , ShipUI
        , ShipUIModuleButton
        )
import EveOnline.UnstuckBot
import List.Extra
import Result.Extra
import Set


defaultBotSettings : BotSettings
defaultBotSettings =
    { hideWhenNeutralInLocal = PromptParser.No
    , anomalyNames = []
    , avoidRats = []
    , prioritizeRats = []
    , activateModulesAlways = []
    , maxTargetCount = 3
    , botStepDelayMilliseconds = { minimum = 1300, maximum = 1500 }
    , anomalyWaitTimeSeconds = 15
    , orbitInCombat = PromptParser.Yes
    , orbitObjectNames = []
    , warpToAnomalyDistance = "Within 0 m"
    , sortOverviewBy = Nothing
    , deactivateModuleOnWarp = []
    , hideLocationNames = []
    }


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    PromptParser.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "hide-when-neutral-in-local"
           , { alternativeNames = []
             , description = "Set this to 'yes' to make the bot dock in a station or structure when a neutral or hostile appears in the 'local' chat."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\hide settings -> { settings | hideWhenNeutralInLocal = hide })
             }
           )
         , ( "anomaly-name"
           , { alternativeNames = []
             , description = "Name of anomalies to select. Use this setting multiple times to select multiple names."
             , valueParser =
                PromptParser.valueTypeString
                    (\anomalyName settings ->
                        { settings | anomalyNames = String.trim anomalyName :: settings.anomalyNames }
                    )
             }
           )
         , ( "avoid-rat"
           , { alternativeNames = []
             , description = "Name of a rat to avoid by warping away. Enter the name as it appears in the overview. Use this setting multiple times to select multiple names."
             , valueParser =
                PromptParser.valueTypeString
                    (\ratToAvoid settings ->
                        { settings | avoidRats = String.trim ratToAvoid :: settings.avoidRats }
                    )
             }
           )
         , ( "prioritize-rat"
           , { alternativeNames = [ "prio-rat", "priority-rat" ]
             , description = "Name of a rat to prioritize when locking targets. Enter the name as it appears in the overview. Use this setting multiple times to select multiple names."
             , valueParser =
                PromptParser.valueTypeString
                    (\ratToPrioritize settings ->
                        { settings | prioritizeRats = String.trim ratToPrioritize :: settings.prioritizeRats }
                    )
             }
           )
         , ( "activate-module-always"
           , { alternativeNames = []
             , description = "Text found in tooltips of ship modules that should always be active. For example: 'shield hardener'."
             , valueParser =
                PromptParser.valueTypeString
                    (\moduleName settings ->
                        { settings | activateModulesAlways = moduleName :: settings.activateModulesAlways }
                    )
             }
           )
         , ( "anomaly-wait-time"
           , { alternativeNames = []
             , description = "Minimum time to wait after arriving in an anomaly before considering it finished. Use this if you see anomalies in which rats arrive later than you arrive on grid."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\anomalyWaitTimeSeconds settings ->
                        { settings | anomalyWaitTimeSeconds = anomalyWaitTimeSeconds }
                    )
             }
           )
         , ( "orbit-in-combat"
           , { alternativeNames = []
             , description = "Whether to keep the ship orbiting during combat"
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\orbitInCombat settings ->
                        { settings | orbitInCombat = orbitInCombat }
                    )
             }
           )
         , ( "warp-to-anomaly-distance"
           , { alternativeNames = []
             , description = "Defaults to 'Within 0 m'"
             , valueParser =
                PromptParser.valueTypeString
                    (\warpToAnomalyDistance settings ->
                        { settings | warpToAnomalyDistance = warpToAnomalyDistance }
                    )
             }
           )
         , ( "sort-overview-by"
           , { alternativeNames = []
             , description = "Name of the overview column to use for sorting. For example: 'distance' or 'size'"
             , valueParser =
                PromptParser.valueTypeString
                    (\columnName settings ->
                        { settings | sortOverviewBy = Just columnName }
                    )
             }
           )
         , ( "bot-step-delay"
           , { alternativeNames = [ "step-delay" ]
             , description = "Minimum time between starting bot steps in milliseconds. You can also specify a range like `1000 - 2000`. The bot then picks a random value in this range."
             , valueParser =
                PromptParser.parseIntervalIntFromPointOrIntervalString
                    >> Result.map
                        (\delay settings -> { settings | botStepDelayMilliseconds = delay })
             }
           )
         , ( "orbit-object-name"
           , { alternativeNames = []
             , description = "Choose the name of large collidable objects to orbit. You can use this setting multiple times to select multiple objects."
             , valueParser =
                PromptParser.valueTypeString
                    (\orbitObjectName settings ->
                        { settings
                            | orbitObjectNames = String.trim orbitObjectName :: settings.orbitObjectNames
                            , orbitInCombat = PromptParser.Yes
                        }
                    )
             }
           )
         , ( "deactivate-module-on-warp"
           , { alternativeNames = []
             , description = "Name of a module to deactivate when warping. Enter the name as it appears in the tooltip. Use this setting multiple times to select multiple modules."
             , valueParser =
                PromptParser.valueTypeString
                    (\moduleName settings ->
                        { settings | deactivateModuleOnWarp = moduleName :: settings.deactivateModuleOnWarp }
                    )
             }
           )
         , ( "hide-location-name"
           , { alternativeNames = []
             , description = "Name of a location to hide. Enter the name as it appears in the 'Locations' window."
             , valueParser =
                PromptParser.valueTypeString
                    (\locationName settings ->
                        { settings
                            | hideLocationNames = String.trim locationName :: settings.hideLocationNames
                        }
                    )
             }
           )
         ]
            |> Dict.fromList
        )
        defaultBotSettings


goodStandingPatterns : List String
goodStandingPatterns =
    [ "good standing", "excellent standing", "is in your" ]


type alias BotSettings =
    { hideWhenNeutralInLocal : PromptParser.YesOrNo
    , anomalyNames : List String
    , avoidRats : List String
    , prioritizeRats : List String
    , activateModulesAlways : List String
    , maxTargetCount : Int
    , anomalyWaitTimeSeconds : Int
    , botStepDelayMilliseconds : IntervalInt
    , orbitInCombat : PromptParser.YesOrNo
    , orbitObjectNames : List String
    , warpToAnomalyDistance : String
    , sortOverviewBy : Maybe String
    , deactivateModuleOnWarp : List String
    , hideLocationNames : List String
    }


type alias State =
    EveOnline.UnstuckBot.UnstuckBotState
        (EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory)


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , overviewWindows : OverviewWindowsMemory
    , shipWarpingInLastReading : Maybe Bool

    -- How many readings ago the last warp finished, which is what opens the
    -- arrival window the other-pilot snapshot is taken inside. `Nothing` means
    -- no warp has finished this session and is a closed window, never an open
    -- one. See `otherPilotArrivalWindowReadings`.
    , readingsSinceWarpEnded : Maybe Int
    , visitedAnomalies : Dict.Dict String MemoryOfAnomaly
    , notEnoughBandwidthToLaunchDrone : Bool
    , droneBandwidthLimitatatinEvents : List { timeMilliseconds : Int, dronesInSpaceCount : Int }
    , contextMenuLastDepth : Int
    , contextMenuStuckTicks : Int
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
    | DoesNotMatchAnomalyNameFromSettings
    | FoundOtherPilotOnArrival String
    | FoundRatToAvoid String


type alias RatsByAttackPriority =
    { overviewEntriesByPrio : List ( OverviewWindowEntry, List OverviewWindowEntry )
    , targetsByPrio : List ( EveOnline.ParseUserInterface.Target, List EveOnline.ParseUserInterface.Target )
    }


describeReasonToAvoidAnomaly : ReasonToAvoidAnomaly -> String
describeReasonToAvoidAnomaly reason =
    case reason of
        IsNoCombatAnomaly ->
            "Is not a combat anomaly"

        DoesNotMatchAnomalyNameFromSettings ->
            "Does not match an anomaly name from the settings"

        FoundOtherPilotOnArrival otherPilot ->
            "Found another pilot on arrival: " ++ otherPilot

        FoundRatToAvoid rat ->
            "Found a rat to avoid: " ++ rat


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
                       Observed in session-recording-2026-05-20T15-15-351:
                       'Signal' = "Combat Site
                    -}
                    probeScanResult.cellsTexts
                        |> Dict.get "Signal"
                        |> Maybe.map (stringContainsIgnoringCase "combat")
                        |> Maybe.withDefault False

                isCombatAnomaly =
                    isCombatAnomaly2025 || isCombatAnomaly2026

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


anomalyBotDecisionRoot : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRoot context =
    anomalyBotDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            (randomIntFromInterval context context.eventContext.botSettings.botStepDelayMilliseconds)


anomalyBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
anomalyBotDecisionRootBeforeApplyingSettings context =
    generalSetupInUserInterface context
        |> Maybe.withDefault
            (branchDependingOnDockedOrInSpace
                { ifDocked =
                    case
                        continueIfShouldHide
                            { ifShouldHide =
                                describeBranch "Stay docked." waitForProgressInGame
                            }
                            context
                    of
                        Just stayDocked ->
                            stayDocked

                        Nothing ->
                            undockUsingStationWindow context
                                { ifCannotReachButton =
                                    describeBranch "No alternative for undocking" askForHelpToGetUnstuck
                                }
                , ifSeeShipUI =
                    decideNextActionWhenInSpace context
                }
                context
            )


generalSetupInUserInterface : BotDecisionContext -> Maybe DecisionPathNode
generalSetupInUserInterface context =
    [ closeMessageBox
    , ensureInfoPanelLocationInfoIsExpanded context.previousStepsEffects
    , case context.eventContext.botSettings.sortOverviewBy of
        Nothing ->
            always Nothing

        Just sortOverviewBy ->
            ensureOverviewsSorted
                { sortColumnName = sortOverviewBy, skipSortingWhenNotScrollable = False }
                context.memory.overviewWindows
                >> List.filterMap
                    (\( _, ( description, maybeAction ) ) ->
                        maybeAction |> Maybe.map (describeBranch description)
                    )
                >> List.head
    ]
        |> List.filterMap ((|>) context.readingFromGameClient)
        |> List.head


closeMessageBox : ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.map
            (\messageBox ->
                describeBranch "I see a message box to close."
                    (let
                        buttonCanBeUsedToClose button =
                            case button.mainText of
                                Nothing ->
                                    False

                                Just buttonText ->
                                    let
                                        buttonTextLower =
                                            String.toLower buttonText
                                    in
                                    List.member buttonTextLower [ "close", "ok" ]
                     in
                     case List.filter buttonCanBeUsedToClose messageBox.buttons of
                        [] ->
                            describeBranch "I see no way to close this message box." askForHelpToGetUnstuck

                        buttonToUse :: _ ->
                            describeBranch
                                ("Click on button '" ++ (buttonToUse.mainText |> Maybe.withDefault "") ++ "'.")
                                (case mouseClickOnUIElement MouseButtonLeft buttonToUse.uiNode of
                                    Err _ ->
                                        describeBranch "Failed to click" askForHelpToGetUnstuck

                                    Ok clickAction ->
                                        decideActionForCurrentStep clickAction
                                )
                    )
            )


continueIfShouldHide : { ifShouldHide : DecisionPathNode } -> BotDecisionContext -> Maybe DecisionPathNode
continueIfShouldHide config context =
    case checkIfShouldHide context of
        Nothing ->
            Nothing

        Just ( reason, justAskForHelp ) ->
            Just
                (describeBranch
                    reason
                    (if justAskForHelp then
                        askForHelpToGetUnstuck

                     else
                        config.ifShouldHide
                    )
                )


checkIfShouldHide : BotDecisionContext -> Maybe ( String, Bool )
checkIfShouldHide context =
    let
        hasNoShipModules : Bool
        hasNoShipModules =
            case context.readingFromGameClient.shipUI of
                Nothing ->
                    False

                Just shipUI ->
                    shipUI.moduleButtons == []
    in
    if hasNoShipModules then
        Just
            ( "Ship UI contains zero module buttons."
            , False
            )

    else
        case
            context.eventContext
                |> EveOnline.BotFramework.secondsToSessionEnd
                |> Maybe.andThen (nothingFromIntIfGreaterThan 200)
        of
            Just secondsToSessionEnd ->
                Just
                    ( "Session ends in " ++ String.fromInt secondsToSessionEnd ++ " seconds."
                    , False
                    )

            Nothing ->
                if context.eventContext.botSettings.hideWhenNeutralInLocal /= PromptParser.Yes then
                    Nothing

                else
                    case context.readingFromGameClient |> localChatWindowFromUserInterface of
                        Nothing ->
                            Just
                                ( "I don't see the local chat window."
                                , True
                                )

                        Just localChatWindow ->
                            let
                                chatUserHasGoodStanding chatUser =
                                    goodStandingPatterns
                                        |> List.any
                                            (\goodStandingPattern ->
                                                case chatUser.standingIconHint of
                                                    Nothing ->
                                                        False

                                                    Just standingIconHint ->
                                                        stringContainsIgnoringCase
                                                            goodStandingPattern
                                                            standingIconHint
                                            )

                                subsetOfUsersWithNoGoodStanding : List { uiNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion, name : Maybe String, standingIconHint : Maybe String }
                                subsetOfUsersWithNoGoodStanding =
                                    case localChatWindow.userlist of
                                        Nothing ->
                                            []

                                        Just userlist ->
                                            userlist.visibleUsers
                                                |> List.filter (chatUserHasGoodStanding >> not)
                            in
                            if 1 < List.length subsetOfUsersWithNoGoodStanding then
                                Just
                                    ( "There is an enemy or neutral in local chat."
                                    , False
                                    )

                            else
                                Nothing


runAway : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
runAway context shipUI =
    case context.eventContext.botSettings.hideLocationNames of
        [] ->
            dockAtRandomStationOrStructure context shipUI

        hideLocationNames ->
            let
                routesToHideLocation =
                    dockOrWarpToLocationWithMatchingName
                        { namesFromSettingOrInfoPanel = hideLocationNames }
                        context
            in
            case routesToHideLocation.viaLocationsWindow of
                Just viaLocationsWindow ->
                    viaLocationsWindow

                Nothing ->
                    case routesToHideLocation.viaOverview of
                        Just viaOverview ->
                            viaOverview

                        Nothing ->
                            describeBranch
                                (String.concat
                                    [ "Did not find any of the "
                                    , String.fromInt (List.length hideLocationNames)
                                    , " configured locations ("
                                    , String.join ", " hideLocationNames
                                    , ") in the locations window or any overview window. "
                                    , "Defaulting to solar system menu."
                                    ]
                                )
                                (routesToHideLocation.viaSolarSystemMenu ())


dockOrWarpToLocationWithMatchingName :
    { namesFromSettingOrInfoPanel : List String }
    -> BotDecisionContext
    ->
        { viaLocationsWindow : Maybe DecisionPathNode
        , viaOverview : Maybe DecisionPathNode
        , viaSolarSystemMenu : () -> DecisionPathNode
        }
dockOrWarpToLocationWithMatchingName { namesFromSettingOrInfoPanel } context =
    {-
       session-2025-04-29T00-59:
       A location given with settings is in space and is NOT directly at a structure.
       In the context menu for that location, we see following entries at the top:
       ----
       Warp to Within (0 m) -> This one appears to be expandable.
       Align to
       Show Info
       ...
    -}
    let
        destNamesSimplified : List String
        destNamesSimplified =
            List.map
                simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry
                namesFromSettingOrInfoPanel

        {-
           2023-01-11 Observation by Dean: Text in surroundings context menu entry sometimes wraps station name in XML tags:
           <color=#FF58A7BF>Niyabainen IV - M1 - Caldari Navy Assembly Plant</color>
        -}
        displayTextRepresentsMatchingStation : String -> Bool
        displayTextRepresentsMatchingStation displayName =
            let
                displayNameSimplified =
                    simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry
                        displayName
            in
            List.any
                (\destName ->
                    String.contains destName displayNameSimplified
                )
                destNamesSimplified
    in
    useContextMenuOnLocationWithMatchingName
        displayTextRepresentsMatchingStation
        (useMenuEntryWithTextContainingFirstOf
            [ ( "dock"
              , menuCascadeCompleted
              )
            , ( "Warp to Within (0 m)"
              , menuCascadeCompleted
              )
            , ( "Warp to"
              , useMenuEntryWithTextContaining "Within 0 m" menuCascadeCompleted
              )
            ]
        )
        context


useContextMenuOnLocationWithMatchingName :
    (String -> Bool)
    -> EveOnline.BotFramework.UseContextMenuCascadeNode
    -> BotDecisionContext
    ->
        { viaLocationsWindow : Maybe DecisionPathNode
        , viaOverview : Maybe DecisionPathNode
        , viaSolarSystemMenu : () -> DecisionPathNode
        }
useContextMenuOnLocationWithMatchingName nameMatches useMenu context =
    let
        viaLocationsWindow : Maybe DecisionPathNode
        viaLocationsWindow =
            case context.readingFromGameClient.locationsWindow of
                Nothing ->
                    Nothing

                Just locationsWindow ->
                    case
                        locationsWindow.placeEntries
                            |> List.filter (.mainText >> nameMatches)
                            |> List.head
                    of
                        Nothing ->
                            Nothing

                        Just placeEntry ->
                            Just
                                (EveOnline.BotFrameworkSeparatingMemory.useContextMenuCascade
                                    ( placeEntry.mainText, placeEntry.uiNode )
                                    useMenu
                                    context
                                )

        matchingOverviewEntry : Maybe OverviewWindowEntry
        matchingOverviewEntry =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter
                    (.objectName
                        >> Maybe.map nameMatches
                        >> Maybe.withDefault False
                    )
                |> List.head

        viaOverview =
            case matchingOverviewEntry of
                Just overviewEntry ->
                    Just
                        (EveOnline.BotFrameworkSeparatingMemory.useContextMenuCascadeOnOverviewEntry
                            useMenu
                            overviewEntry
                            context
                        )

                Nothing ->
                    Nothing
    in
    { viaLocationsWindow = viaLocationsWindow
    , viaOverview = viaOverview
    , viaSolarSystemMenu =
        \() ->
            let
                overviewWindowScrollControls =
                    context.readingFromGameClient.overviewWindows
                        |> List.filterMap .scrollControls
                        |> List.head
            in
            overviewWindowScrollControls
                |> Maybe.andThen scrollDown
                |> Maybe.withDefault
                    (useContextMenuCascadeOnListSurroundingsButton
                        (useMenuEntryWithTextContainingFirstOfCommonContinuation
                            [ "locations" ]
                            (useMenuEntryInLastContextMenuInCascade
                                { describeChoice = "select using the configured predicate"
                                , chooseEntry =
                                    List.filter (.text >> nameMatches)
                                        >> List.head
                                }
                                useMenu
                            )
                        )
                        context
                    )
    }


scrollDown : EveOnline.ParseUserInterface.ScrollControls -> Maybe DecisionPathNode
scrollDown scrollControls =
    case scrollControls.scrollHandle of
        Nothing ->
            Nothing

        Just scrollHandle ->
            let
                scrollControlsTotalDisplayRegion =
                    scrollControls.uiNode.totalDisplayRegion

                scrollControlsBottom =
                    scrollControlsTotalDisplayRegion.y + scrollControlsTotalDisplayRegion.height

                freeHeightAtBottom =
                    scrollControlsBottom
                        - (scrollHandle.totalDisplayRegion.y + scrollHandle.totalDisplayRegion.height)
            in
            if 10 < freeHeightAtBottom then
                Just
                    (describeBranch "Click at scroll control bottom"
                        (decideActionForCurrentStep
                            (EffectOnWindow.effectsMouseClickAtLocation
                                EffectOnWindow.MouseButtonLeft
                                { x = scrollControlsTotalDisplayRegion.x + 3
                                , y = scrollControlsBottom - 8
                                }
                                ++ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_END
                                   , EffectOnWindow.KeyUp EffectOnWindow.vkey_END
                                   ]
                            )
                        )
                    )

            else
                Nothing


{-| Prepare a station name or structure name coming from bot-settings for comparing with menu entries.

  - The user could take the name from the info panel:
    The names sometimes differ between info panel and menu entries: 'Moon 7' can become 'M7'.

  - Do not distinguish between the comma and period characters:
    Besides the similar visual appearance, also because of the limitations of popular bot-settings parsing frameworks.
    The user can remove a comma or replace it with a full stop/period, whatever looks better.

-}
simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry : String -> String
simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry =
    String.toLower
        >> String.replace "moon " "m"
        >> String.replace "," ""
        >> String.replace "." ""
        >> String.trim


{-| 2020-07-11 Discovery by Viktor:
The entries for structures in the menu from the SurroundingsButton can be nested one level deeper than the ones for stations.
In other words, not all structures appear directly under the "structures" entry.
-}
dockAtRandomStationOrStructure :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
dockAtRandomStationOrStructure context seeUndockingComplete =
    case fightRatsIfShipIsPointed context seeUndockingComplete of
        Just fightPointingRats ->
            fightPointingRats

        Nothing ->
            let
                withTextContainingIgnoringCase textToSearch =
                    List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head

                menuEntryIsSuitable menuEntry =
                    [ "cyno beacon", "jump gate" ]
                        |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
                        |> not

                chooseNextMenuEntryDockOrRandom : Int -> UseContextMenuCascadeNode
                chooseNextMenuEntryDockOrRandom remainingDepth =
                    MenuEntryWithCustomChoice
                        { describeChoice = "Use 'Dock' if available or a random entry."
                        , chooseEntry =
                            \menu ->
                                let
                                    suitableMenuEntries =
                                        List.filter menuEntryIsSuitable menu.entries
                                in
                                case
                                    [ withTextContainingIgnoringCase "dock"
                                    , List.filter (.text >> stringContainsIgnoringCase "station")
                                        >> Common.Basics.listElementAtWrappedIndex
                                            (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                                    , Common.Basics.listElementAtWrappedIndex
                                        (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                                    ]
                                        |> Common.listMapFind (\priority -> suitableMenuEntries |> priority)
                                of
                                    Nothing ->
                                        Nothing

                                    Just menuEntry ->
                                        if remainingDepth <= 0 then
                                            Just ( menuEntry, MenuCascadeCompleted )

                                        else
                                            Just
                                                ( menuEntry
                                                , chooseNextMenuEntryDockOrRandom (remainingDepth - 1)
                                                )
                        }
            in
            useContextMenuCascadeOnListSurroundingsButton
                (useMenuEntryWithTextContainingFirstOfCommonContinuation [ "stations", "structures" ]
                    (chooseNextMenuEntryDockOrRandom 3)
                )
                context


decideNextActionWhenInSpace : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
decideNextActionWhenInSpace context shipUI =
    clearStrayContextMenu context
        |> Maybe.withDefault (decideNextActionWhenInSpaceNotStuckOnContextMenu context shipUI)


decideNextActionWhenInSpaceNotStuckOnContextMenu : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
decideNextActionWhenInSpaceNotStuckOnContextMenu context shipUI =
    case
        continueIfShouldHide
            { ifShouldHide =
                returnDronesToBay context
                    |> Maybe.withDefault
                        (describeBranch
                            "Hide at configured location."
                            (runAway context shipUI)
                        )
            }
            context
    of
        Just hideAction ->
            hideAction

        Nothing ->
            decideNextActionWhenInSpaceNotHiding context shipUI


decideNextActionWhenInSpaceNotHiding :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
decideNextActionWhenInSpaceNotHiding context shipUI =
    if shipUIIndicatesShipIsWarpingOrJumping shipUI then
        describeBranch "I see we are warping."
            ([ returnDronesToBay context
             , deactivateModulesForWarp context
             , readShipUIModuleButtonTooltips context
             ]
                |> List.filterMap identity
                |> List.head
                |> Maybe.withDefault waitForProgressInGame
            )

    else
        readShipUIModuleButtonTooltips context
            |> Maybe.withDefault
                (case
                    context
                        |> knownModulesToActivateAlways
                        |> List.filter (Tuple.second >> moduleIsActiveOrReloading >> not)
                        |> List.head
                 of
                    Just ( inactiveModuleMatchingText, inactiveModule ) ->
                        describeBranch ("I see inactive module '" ++ inactiveModuleMatchingText ++ "' to activate always. Activate it.")
                            (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)

                    Nothing ->
                        modulesToActivateAlwaysActivated context shipUI
                )


modulesToActivateAlwaysActivated :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
modulesToActivateAlwaysActivated context shipUI =
    case fightRatsIfShipIsPointed context shipUI of
        Just fightPointingRats ->
            {-
               Adapt to observation shared with session-recording-2024-05-15T13-11-03:
               The anomaly is not visible anymore, since 'site has despawned',
               but there are still rats pointing the player ship.
               Therefore, we increase priority of fighting pointing rats to be independent of an anomaly.
            -}
            fightPointingRats

        Nothing ->
            let
                returnDronesAndEnterAnomaly { ifNoAcceptableAnomalyAvailable } =
                    returnDronesToBay context
                        |> Maybe.withDefault
                            (describeBranch "No drones to return."
                                (enterAnomaly { ifNoAcceptableAnomalyAvailable = ifNoAcceptableAnomalyAvailable }
                                    context
                                    shipUI
                                )
                            )

                returnDronesAndEnterAnomalyOrWait =
                    returnDronesAndEnterAnomaly
                        { ifNoAcceptableAnomalyAvailable =
                            describeBranch "Wait for a matching anomaly to appear." waitForProgressInGame
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

                                continueInAnomaly : () -> DecisionPathNode
                                continueInAnomaly () =
                                    decideActionInAnomaly
                                        { arrivalInAnomalyAgeSeconds = arrivalInAnomalyAgeSeconds }
                                        context
                                        shipUI
                                        returnDronesAndEnterAnomalyOrWait
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
                                                        (dockAtRandomStationOrStructure
                                                            context
                                                            shipUI
                                                        )
                                                }
                                            )

                                    Nothing ->
                                        continueInAnomaly ()
                                )


undockUsingStationWindow :
    BotDecisionContext
    -> { ifCannotReachButton : DecisionPathNode }
    -> DecisionPathNode
undockUsingStationWindow context { ifCannotReachButton } =
    case context.readingFromGameClient.stationWindow of
        Nothing ->
            describeBranch "I do not see the station window." ifCannotReachButton

        Just stationWindow ->
            case stationWindow.undockButton of
                Nothing ->
                    case stationWindow.abortUndockButton of
                        Nothing ->
                            describeBranch "I do not see the undock button." ifCannotReachButton

                        Just _ ->
                            describeBranch "I see we are already undocking." waitForProgressInGame

                Just undockButton ->
                    describeBranch "Click on the button to undock."
                        (mouseClickOnUIElement MouseButtonLeft undockButton
                            |> Result.Extra.unpack
                                (always ifCannotReachButton)
                                decideActionForCurrentStep
                        )


decideActionInAnomaly :
    { arrivalInAnomalyAgeSeconds : Int }
    -> BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
    -> DecisionPathNode
decideActionInAnomaly { arrivalInAnomalyAgeSeconds } context shipUI continueIfCombatComplete =
    let
        ratsToAttackByPriority =
            ratsToAttackByPriorityFromContext context

        overviewEntriesToAttack : List OverviewWindowEntry
        overviewEntriesToAttack =
            ratsToAttackByPriority.overviewEntriesByPrio
                |> List.concatMap (\( first, rest ) -> first :: rest)

        overviewEntriesToLock =
            overviewEntriesToAttack
                |> List.filter (overviewEntryIsTargetedOrTargeting >> not)
                |> List.map (lockTargetFromOverviewEntry context)

        targetsToUnlock =
            if overviewEntriesToAttack |> List.any overviewEntryIsActiveTarget then
                []

            else
                context.readingFromGameClient.targets |> List.filter .isActiveTarget

        overviewsAllEntries =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries

        maybeObjectToOrbit =
            case findObjectToOrbitByName context.eventContext.botSettings.orbitObjectNames overviewsAllEntries of
                Just fromName ->
                    Just fromName

                Nothing ->
                    List.Extra.last overviewEntriesToAttack

        ensureShipIsOrbitingDecision =
            case maybeObjectToOrbit of
                Nothing ->
                    Nothing

                Just objectToOrbit ->
                    ensureShipIsOrbiting shipUI objectToOrbit

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

        continueLockOverviewEntries { ifNoEntryToLock } =
            case resultFirstSuccessOrFirstError overviewEntriesToLock of
                Nothing ->
                    describeBranch "I see no more overview entries to lock."
                        ifNoEntryToLock

                Just nextOverviewEntryToLockResult ->
                    describeBranch "I see an overview entry to lock."
                        (nextOverviewEntryToLockResult
                            |> Result.Extra.unpack
                                (describeBranch >> (|>) askForHelpToGetUnstuck)
                                identity
                        )

        decisionToKillRats =
            case targetsToUnlock of
                targetToUnlock :: _ ->
                    describeBranch "I see a target to unlock."
                        (useContextMenuCascade
                            ( "locked target"
                            , targetToUnlock.barAndImageCont |> Maybe.withDefault targetToUnlock.uiNode
                            )
                            (useMenuEntryWithTextContaining "unlock" menuCascadeCompleted)
                            context
                        )

                [] ->
                    fightUsingDronesAndModules
                        { ifNoTarget = continueLockOverviewEntries { ifNoEntryToLock = decisionIfNoEnemyToAttack }
                        , lockNextTarget = continueLockOverviewEntries { ifNoEntryToLock = waitForProgressInGame }
                        , waitForProgress = waitForProgressInGame
                        }
                        context
                        shipUI
    in
    if context.eventContext.botSettings.orbitInCombat == PromptParser.Yes then
        ensureShipIsOrbitingDecision
            |> Maybe.withDefault (Ok decisionToKillRats)
            |> Result.Extra.unpack
                (describeBranch >> (|>) decisionToKillRats)
                identity

    else
        decisionToKillRats


findObjectToOrbitByName : List String -> List OverviewWindowEntry -> Maybe OverviewWindowEntry
findObjectToOrbitByName orbitObjectNames overviewEntries =
    overviewEntries
        |> List.Extra.find
            (\entry ->
                case entry.objectName of
                    Nothing ->
                        False

                    Just objectName ->
                        let
                            objectNameLower =
                                String.toLower objectName
                        in
                        List.any
                            (\objectNamePattern ->
                                String.contains (String.toLower objectNamePattern) objectNameLower
                            )
                            orbitObjectNames
            )


enterAnomaly :
    { ifNoAcceptableAnomalyAvailable : DecisionPathNode }
    -> BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
enterAnomaly { ifNoAcceptableAnomalyAvailable } context shipUI =
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
                            ++ " scan results, and no matching anomaly. Wait for a matching anomaly to appear."
                        )
                        ifNoAcceptableAnomalyAvailable

                Just anomalyScanResult ->
                    describeBranch "Warp to anomaly."
                        (useContextMenuCascade
                            ( "Scan result", anomalyScanResult.uiNode )
                            (useMenuEntryWithTextContaining "Warp to Within"
                                (useMenuEntryWithTextContaining
                                    context.eventContext.botSettings.warpToAnomalyDistance
                                    menuCascadeCompleted
                                )
                            )
                            context
                        )


deactivateModulesForWarp : BotDecisionContext -> Maybe DecisionPathNode
deactivateModulesForWarp context =
    let
        modulesToDeactivate : List ( String, EveOnline.ParseUserInterface.ShipUIModuleButton )
        modulesToDeactivate =
            case context.readingFromGameClient.shipUI of
                Nothing ->
                    []

                Just shipUI ->
                    shipUI.moduleButtons
                        |> List.filterMap
                            (\moduleButton ->
                                case moduleButton.isActive of
                                    Nothing ->
                                        Nothing

                                    Just False ->
                                        Nothing

                                    Just True ->
                                        moduleButton
                                            |> EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton
                                                context.memory.shipModules
                                            |> Maybe.andThen
                                                (\tooltipMemory ->
                                                    let
                                                        tooltipText =
                                                            tooltipMemory.allContainedDisplayTextsWithRegion
                                                                |> List.map Tuple.first
                                                                |> String.join " "
                                                    in
                                                    if
                                                        context.eventContext.botSettings.deactivateModuleOnWarp
                                                            |> List.any (\moduleName -> tooltipText |> stringContainsIgnoringCase moduleName)
                                                    then
                                                        Just ( tooltipText, moduleButton )

                                                    else
                                                        Nothing
                                                )
                            )
    in
    case modulesToDeactivate of
        [] ->
            Nothing

        ( moduleName, moduleToDeactivate ) :: _ ->
            Just
                (describeBranch ("Click module to deactivate '" ++ moduleName ++ "' to speed up warp.")
                    (clickModuleButtonButWaitIfClickedInPreviousStep context moduleToDeactivate)
                )


fightRatsIfShipIsPointed :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> Maybe DecisionPathNode
fightRatsIfShipIsPointed context shipUI =
    {- Based on observation from 2024-04-24:

       [...] "f" is the command to order the drones to fight the rat that is targeted.

       1.  If a human is playing the game, he will hold the "ctrl" key while left clicking the "pointed" symbol. THis will cause the game to target the rat that is pointing you.
       2.  once target is locked he will then hit the 'f' key to make the drones fight that rat. OR he can do the same by right clicking the drones bar and engage.
       3.  In the case of being targeted by multiple points, the above gets repeated.

    -}
    case offensiveBuffButtonsIndicatingSelfShipIsPointed shipUI of
        [] ->
            Nothing

        firstPointingBuffButton :: _ ->
            let
                lockTarget =
                    case mouseClickOnUIElement MouseButtonLeft firstPointingBuffButton of
                        Err _ ->
                            describeBranch "Failed to click"
                                askForHelpToGetUnstuck

                        Ok effectToClick ->
                            describeBranch "hold the 'ctrl' key while left clicking the 'pointed' symbol"
                                (decideActionForCurrentStep
                                    (List.concat
                                        [ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]
                                        , effectToClick
                                        , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]
                                        ]
                                    )
                                )
            in
            Just
                (describeBranch "I see a buff indicating the ship is pointed."
                    (fightUsingDronesAndModules
                        { ifNoTarget = lockTarget
                        , lockNextTarget = lockTarget
                        , waitForProgress = waitForProgressInGame
                        }
                        context
                        shipUI
                    )
                )


fightUsingDronesAndModules :
    { ifNoTarget : DecisionPathNode, lockNextTarget : DecisionPathNode, waitForProgress : DecisionPathNode }
    -> BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
fightUsingDronesAndModules config context shipUI =
    let
        ratsToAttackByPriority =
            ratsToAttackByPriorityFromContext context

        highPrioTargets : List EveOnline.ParseUserInterface.Target
        highPrioTargets =
            case ratsToAttackByPriority.targetsByPrio of
                [] ->
                    []

                ( first, rest ) :: _ ->
                    first :: rest
    in
    case context.readingFromGameClient.targets of
        [] ->
            describeBranch "I see no locked target."
                config.ifNoTarget

        _ :: _ ->
            describeBranch "I see a locked target."
                (case checkActiveTargetIsOfHighestPriority ratsToAttackByPriority context.readingFromGameClient of
                    Just selectHighPrio ->
                        selectHighPrio

                    Nothing ->
                        case
                            shipUI
                                |> shipUIModulesToActivateOnTarget
                                |> List.filter (.isActive >> Maybe.withDefault False >> not)
                                |> List.head
                        of
                            Nothing ->
                                describeBranch "All attack modules are active."
                                    (launchAndEngageDrones { redirectToTargets = Just highPrioTargets } context
                                        |> Maybe.withDefault
                                            (describeBranch "No idling drones."
                                                (if context.eventContext.botSettings.maxTargetCount <= (context.readingFromGameClient.targets |> List.length) then
                                                    describeBranch "Enough locked targets." config.waitForProgress

                                                 else
                                                    config.lockNextTarget
                                                )
                                            )
                                    )

                            Just inactiveModule ->
                                describeBranch "I see an inactive module to activate on targets. Activate it."
                                    (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)
                )


ratsToAttackByPriorityFromContext : BotDecisionContext -> RatsByAttackPriority
ratsToAttackByPriorityFromContext context =
    let
        prioritizedRatsPatterns : List String
        prioritizedRatsPatterns =
            List.map String.toLower context.eventContext.botSettings.prioritizeRats

        isPriorityRat : { a | labelText : String } -> Bool
        isPriorityRat objectInSpace =
            prioritizedRatsPatterns
                |> List.any
                    (\priorityRat ->
                        String.contains
                            priorityRat
                            (String.toLower objectInSpace.labelText)
                    )

        attackPriority : { a | labelText : String } -> Int
        attackPriority objectInSpace =
            if isPriorityRat objectInSpace then
                0

            else
                1

        overviewEntriesToAttack =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter shouldAttackOverviewEntry

        overviewEntriesByPrio : List ( OverviewWindowEntry, List OverviewWindowEntry )
        overviewEntriesByPrio =
            overviewEntriesToAttack
                {-
                   2023-03-30
                   Change to sort by display location after Wombat shared his experience in EVE Online at https://forum.botlab.org/t/eve-online-anomaly-ratting-bot-release/87/340
                   |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
                -}
                |> List.sortBy (.uiNode >> .totalDisplayRegion >> .y)
                |> Common.Basics.listGatherEqualsBy
                    (\overviewEntry -> attackPriority { labelText = Maybe.withDefault "" overviewEntry.objectName })
                |> List.sortBy Tuple.first
                |> List.map Tuple.second

        targetsByPrio : List ( EveOnline.ParseUserInterface.Target, List EveOnline.ParseUserInterface.Target )
        targetsByPrio =
            context.readingFromGameClient.targets
                |> Common.Basics.listGatherEqualsBy
                    (\target -> attackPriority { labelText = String.join " " target.textsTopToBottom })
                |> List.sortBy Tuple.first
                |> List.map Tuple.second
    in
    { overviewEntriesByPrio = overviewEntriesByPrio
    , targetsByPrio = targetsByPrio
    }


ensureShipIsOrbiting : ShipUI -> OverviewWindowEntry -> Maybe (Result String DecisionPathNode)
ensureShipIsOrbiting shipUI overviewEntryToOrbit =
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverOrbit then
        Nothing

    else
        Just
            (case mouseClickOnUIElement MouseButtonLeft overviewEntryToOrbit.uiNode of
                Err _ ->
                    Err "Failed to click"

                Ok effectToClick ->
                    Ok
                        (describeBranch "Press the 'W' key and click on the overview entry."
                            (decideActionForCurrentStep
                                ([ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_W ]
                                 , effectToClick
                                 , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_W ]
                                 ]
                                    |> List.concat
                                )
                            )
                        )
            )


launchAndEngageDrones :
    { redirectToTargets : Maybe (List EveOnline.ParseUserInterface.Target) }
    -> BotDecisionContext
    -> Maybe DecisionPathNode
launchAndEngageDrones config context =
    case context.readingFromGameClient.dronesWindow of
        Nothing ->
            Nothing

        Just dronesWindow ->
            case ( dronesWindow.droneGroupInBay, dronesWindow.droneGroupInSpace ) of
                ( Just droneGroupInBay, Just droneGroupInSpace ) ->
                    let
                        idlingDrones : List EveOnline.ParseUserInterface.DronesWindowEntryDroneStructure
                        idlingDrones =
                            droneGroupInSpace
                                |> EveOnline.ParseUserInterface.enumerateAllDronesFromDronesGroup
                                |> List.filter
                                    (.uiNode
                                        >> .uiNode
                                        >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                                        >> List.any (stringContainsIgnoringCase "idle")
                                    )

                        dronesInBayQuantity : Int
                        dronesInBayQuantity =
                            case droneGroupInBay.header.quantityFromTitle of
                                Nothing ->
                                    0

                                Just quantityFromTitle ->
                                    quantityFromTitle.current

                        dronesInSpaceQuantityCurrent : Int
                        dronesInSpaceQuantityCurrent =
                            case droneGroupInSpace.header.quantityFromTitle of
                                Nothing ->
                                    0

                                Just quantityFromTitle ->
                                    quantityFromTitle.current

                        dronesInSpaceQuantityLimit : Int
                        dronesInSpaceQuantityLimit =
                            case droneGroupInSpace.header.quantityFromTitle of
                                Nothing ->
                                    2

                                Just quantityFromTitle ->
                                    case quantityFromTitle.maximum of
                                        Nothing ->
                                            2

                                        Just maximum ->
                                            maximum

                        {-
                           Observation from session-recording-2024-05-07T11-55-13.zip-event-482-eve-online-memory-reading:
                           The 'Sprite' UI node referenced from 'assignedIcons' has the following property we can use as indication:
                           _hint = "Drones\nWasp II: 5"
                        -}
                        targetsWithDronesAssigned : List EveOnline.ParseUserInterface.Target
                        targetsWithDronesAssigned =
                            context.readingFromGameClient.targets
                                |> List.filter
                                    (\target ->
                                        target.assignedIcons
                                            |> List.any
                                                (\assignedIcon ->
                                                    assignedIcon.uiNode
                                                        |> EveOnline.ParseUserInterface.getHintTextFromDictEntries
                                                        |> Maybe.map (stringContainsIgnoringCase "drone")
                                                        |> Maybe.withDefault False
                                                )
                                    )

                        engageDrones : DecisionPathNode
                        engageDrones =
                            useContextMenuCascade
                                ( "drones group", droneGroupInSpace.header.uiNode )
                                (useMenuEntryWithTextContaining "engage target" menuCascadeCompleted)
                                context

                        considerLaunch : () -> Maybe DecisionPathNode
                        considerLaunch () =
                            if 0 < dronesInBayQuantity && dronesInSpaceQuantityCurrent < dronesInSpaceQuantityLimit then
                                if assumeNotEnoughBandwidthToLaunchDrone context then
                                    Nothing

                                else
                                    Just
                                        (describeBranch "Launch drones"
                                            (useContextMenuCascade
                                                ( "drones group", droneGroupInBay.header.uiNode )
                                                (useMenuEntryWithTextContaining "Launch drone" menuCascadeCompleted)
                                                context
                                            )
                                        )

                            else
                                Nothing
                    in
                    if 0 < List.length idlingDrones then
                        Just
                            (describeBranch "Engage idling drone(s)" engageDrones)

                    else
                        case config.redirectToTargets of
                            Nothing ->
                                considerLaunch ()

                            Just redirectToTargets ->
                                let
                                    targetsWithDronesAssignedLowPrio : List EveOnline.ParseUserInterface.Target
                                    targetsWithDronesAssignedLowPrio =
                                        List.filter
                                            (\target -> not (List.member target redirectToTargets))
                                            targetsWithDronesAssigned
                                in
                                if 0 < List.length targetsWithDronesAssignedLowPrio then
                                    Just
                                        (describeBranch "Redirect drones to high prio target"
                                            (case checkActiveTargetIsInGroup redirectToTargets context.readingFromGameClient of
                                                Just selectHighPrio ->
                                                    selectHighPrio

                                                Nothing ->
                                                    engageDrones
                                            )
                                        )

                                else
                                    considerLaunch ()

                _ ->
                    Nothing


checkActiveTargetIsOfHighestPriority :
    RatsByAttackPriority
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
checkActiveTargetIsOfHighestPriority ratsToAttackByPriority readingFromGameClient =
    case ratsToAttackByPriority.targetsByPrio of
        [] ->
            Nothing

        ( first, rest ) :: _ ->
            checkActiveTargetIsInGroup
                (first :: rest)
                readingFromGameClient


checkActiveTargetIsInGroup :
    List EveOnline.ParseUserInterface.Target
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
checkActiveTargetIsInGroup priorityTargets readingFromGameClient =
    case priorityTargets of
        [] ->
            Nothing

        firstHighPrio :: _ ->
            let
                activeTargets : List EveOnline.ParseUserInterface.Target
                activeTargets =
                    List.filter .isActiveTarget readingFromGameClient.targets

                activeTargetsLowPrio : List EveOnline.ParseUserInterface.Target
                activeTargetsLowPrio =
                    List.filter (\target -> not (List.member target priorityTargets)) activeTargets
            in
            case activeTargetsLowPrio of
                [] ->
                    Nothing

                _ :: _ ->
                    Just
                        (describeBranch "The active target is not the highest priority. Activating highest priority target."
                            {-
                               As shared 2024-05-08:
                               > [...] Once a rat is targeted, a player will left click the targeted rat from the target list [...]
                            -}
                            (case mouseClickOnUIElement MouseButtonLeft firstHighPrio.uiNode of
                                Err _ ->
                                    describeBranch "Failed to click"
                                        askForHelpToGetUnstuck

                                Ok effectToClick ->
                                    decideActionForCurrentStep effectToClick
                            )
                        )


assumeNotEnoughBandwidthToLaunchDrone : BotDecisionContext -> Bool
assumeNotEnoughBandwidthToLaunchDrone context =
    case
        context.readingFromGameClient.dronesWindow
            |> Maybe.andThen .droneGroupInSpace
            |> Maybe.andThen (.header >> .quantityFromTitle)
    of
        Nothing ->
            True

        Just inSpaceQuantity ->
            let
                limitsFromPreviousEvents =
                    context.memory.droneBandwidthLimitatatinEvents
                        |> List.filter
                            (\limitEvent ->
                                context.eventContext.timeInMilliseconds < limitEvent.timeMilliseconds + 300 * 1000
                            )
                        |> List.map .dronesInSpaceCount

                limitFromPreviousEvents =
                    limitsFromPreviousEvents
                        |> List.sort
                        -- Require confirmation via multiple observations
                        |> List.drop 1
                        |> List.head
                        |> Maybe.withDefault 999
            in
            context.memory.notEnoughBandwidthToLaunchDrone
                || (limitFromPreviousEvents <= inSpaceQuantity.current)


returnDronesToBay : BotDecisionContext -> Maybe DecisionPathNode
returnDronesToBay context =
    case context.readingFromGameClient.dronesWindow of
        Nothing ->
            Nothing

        Just dronesWindow ->
            case dronesWindow.droneGroupInSpace of
                Nothing ->
                    Nothing

                Just droneGroupInLocalSpace ->
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
                                (useContextMenuCascade
                                    ( "drones group", droneGroupInLocalSpace.header.uiNode )
                                    (useMenuEntryWithTextContaining "Return to drone bay" menuCascadeCompleted)
                                    context
                                )
                            )


lockTargetFromOverviewEntry :
    BotDecisionContext
    -> OverviewWindowEntry
    -> Result String DecisionPathNode
lockTargetFromOverviewEntry context overviewEntry =
    if uiNodeVisibleRegionLargeEnoughForClicking overviewEntry.uiNode then
        Ok
            (describeBranch ("Lock target from overview entry '" ++ (overviewEntry.objectName |> Maybe.withDefault "") ++ "'")
                (useContextMenuCascadeOnOverviewEntry
                    (useMenuEntryWithTextEqual "Lock target" menuCascadeCompleted)
                    overviewEntry
                    context
                )
            )

    else
        Err "Unable to click this overview entry because more of it needs to be visible."


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
        |> EveOnline.UnstuckBot.botResolvingStuck


initBotMemory : BotMemory
initBotMemory =
    { lastDockedStationNameFromInfoPanel = Nothing
    , shipModules = EveOnline.BotFramework.initShipModulesMemory
    , overviewWindows = EveOnline.BotFramework.initOverviewWindowsMemory
    , shipWarpingInLastReading = Nothing
    , readingsSinceWarpEnded = Nothing
    , visitedAnomalies = Dict.empty
    , notEnoughBandwidthToLaunchDrone = False
    , droneBandwidthLimitatatinEvents = []
    , contextMenuLastDepth = 0
    , contextMenuStuckTicks = 0
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
                    [ "I do not see the ship UI. Looks like we are docked." ]

                Just shipUI ->
                    let
                        describeShip =
                            "Shield HP at " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%."

                        describeDrones =
                            case readingFromGameClient.dronesWindow of
                                Nothing ->
                                    "I do not see the drones window."

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
                    in
                    [ [ describeShip ]
                    , [ describeDrones ]
                    , [ describeAnomaly, describeArrivalWindowClause, describeOverview ]
                    ]
                        |> List.map (String.join " ")
    in
    [ [ describePerformance ]
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


moduleIsActiveOrReloading : EveOnline.ParseUserInterface.ShipUIModuleButton -> Bool
moduleIsActiveOrReloading moduleButton =
    (moduleButton.isActive |> Maybe.withDefault False)
        || ((moduleButton.rampRotationMilli |> Maybe.withDefault 0) /= 0)


iconSpriteHasColorOfRat : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
iconSpriteHasColorOfRat overviewEntry =
    case overviewEntry.iconSpriteColorPercent of
        Nothing ->
            False

        Just colorPercent ->
            (colorPercent.g * 3 < colorPercent.r)
                && (colorPercent.b * 3 < colorPercent.r)
                && (60 < colorPercent.r && 50 < colorPercent.a)


{-| `BotMemory.contextMenuStuckTicks` only increments when the context menu
cascade depth has stayed the same (or dropped without reaching zero) since the
last reading; any tick that goes deeper than before resets it to 0, regardless
of how many ticks the cascade has taken in total. A genuinely stuck cascade --
sitting at the same depth, unable to find its next entry -- still trips this
after a few ticks; a cascade that keeps advancing, no matter how many levels or
how slowly, never does.
-}
strayContextMenuStuckTicksThreshold : Int
strayContextMenuStuckTicksThreshold =
    3


{-| How long the dismissal gets before the bot works around the menu instead.

**This branch had no bound at all**, and it sits at the head of the in-space
decision list, so a rescue that does not work owns the whole bot -- the same
position, and the same failure, as the message box in this repo's run 30. saxrat
measured the cost: one run spent three quarters of an eight-hour session on this
one rescue with nothing killed.

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
`strayContextMenuStuckTicksThreshold` consecutive ticks; `Nothing` otherwise, so
callers can fall through to their normal decision tree.
-}
clearStrayContextMenu : BotDecisionContext -> Maybe DecisionPathNode
clearStrayContextMenu context =
    if
        (strayContextMenuStuckTicksThreshold <= context.memory.contextMenuStuckTicks)
            && (context.memory.contextMenuStuckTicks < strayContextMenuGiveUpTicks)
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


updateMemoryForNewReadingFromGame : UpdateMemoryContext -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentStationNameFromInfoPanel : Maybe String
        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

        shipIsWarping : Maybe Bool
        shipIsWarping =
            shipWarpingFromReading context.readingFromGameClient

        namesOfRatsInOverview : List String
        namesOfRatsInOverview =
            getNamesOfRatsInOverview context.readingFromGameClient

        weJustFinishedWarping : Bool
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
        readingsSinceWarpEnded : Maybe Int
        readingsSinceWarpEnded =
            if weJustFinishedWarping then
                Just 0

            else
                botMemoryBefore.readingsSinceWarpEnded |> Maybe.map ((+) 1)

        -- Note this subsumes the single-reading trigger it replaces rather than
        -- sitting beside it: on the reading a warp just ended the count is zero,
        -- so the window is open by construction.
        arrivalWindowIsOpenNow : Bool
        arrivalWindowIsOpenNow =
            arrivalWindowIsOpen { readingsSinceWarpEnded = readingsSinceWarpEnded }

        visitedAnomalies : Dict.Dict String MemoryOfAnomaly
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
                        botMemoryBefore.visitedAnomalies
                            |> Dict.insert currentAnomalyID anomalyMemory

        currentContextMenuDepth : Int
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        notEnoughBandwidthToLaunchDrone : Bool
        notEnoughBandwidthToLaunchDrone =
            readingFromGameClientSaysNotEnoughBandwidthToLaunchDrone context.readingFromGameClient

        droneBandwidthLimitatatinEvents =
            case context.readingFromGameClient.dronesWindow of
                Nothing ->
                    -- Also reset when docked
                    []

                Just dronesWindow ->
                    let
                        dronesInSpaceCount =
                            dronesWindow.droneGroupInSpace
                                |> Maybe.andThen (.header >> .quantityFromTitle)
                                |> Maybe.map .current
                                |> Maybe.withDefault 0

                        newEvents =
                            if notEnoughBandwidthToLaunchDrone && not botMemoryBefore.notEnoughBandwidthToLaunchDrone then
                                [ { timeMilliseconds = context.timeInMilliseconds
                                  , dronesInSpaceCount = dronesInSpaceCount
                                  }
                                ]

                            else
                                []
                    in
                    newEvents ++ botMemoryBefore.droneBandwidthLimitatatinEvents
    in
    { lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , shipModules =
        botMemoryBefore.shipModules
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory context.readingFromGameClient
    , overviewWindows =
        botMemoryBefore.overviewWindows
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoOverviewWindowsMemory context.readingFromGameClient
    , shipWarpingInLastReading = shipIsWarping
    , readingsSinceWarpEnded = readingsSinceWarpEnded
    , visitedAnomalies = visitedAnomalies
    , notEnoughBandwidthToLaunchDrone = notEnoughBandwidthToLaunchDrone
    , droneBandwidthLimitatatinEvents = droneBandwidthLimitatatinEvents |> List.take 4
    , contextMenuLastDepth = currentContextMenuDepth
    , contextMenuStuckTicks =
        if currentContextMenuDepth == 0 then
            0

        else if currentContextMenuDepth > botMemoryBefore.contextMenuLastDepth then
            0

        else
            botMemoryBefore.contextMenuStuckTicks + 1
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


shipUIModulesToActivateOnTarget : EveOnline.ParseUserInterface.ShipUI -> List ShipUIModuleButton
shipUIModulesToActivateOnTarget shipUI =
    shipUI.moduleButtonsRows.top


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt


readingFromGameClientSaysNotEnoughBandwidthToLaunchDrone : ReadingFromGameClient -> Bool
readingFromGameClientSaysNotEnoughBandwidthToLaunchDrone reading =
    reading.layerAbovemain
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.getAllContainedDisplayTextsWithRegion)
        |> Maybe.withDefault []
        |> List.map Tuple.first
        |> List.any abovemainMessageSaysNotEnoughBandwidthToLaunchDrone


{-| Returns the subsequence of offensive buff buttons from the ship UI that indicated that our own ship is pointed.

Classifation sources:

  - Discussion of session-recording-2024-04-05T17

-}
offensiveBuffButtonsIndicatingSelfShipIsPointed :
    EveOnline.ParseUserInterface.ShipUI
    -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
offensiveBuffButtonsIndicatingSelfShipIsPointed shipUI =
    List.filterMap
        (\offensiveBuffButton ->
            if offensiveBuffButtonNameIndicatesSelfShipIsPointed offensiveBuffButton.name then
                Just offensiveBuffButton.uiNode

            else
                Nothing
        )
        shipUI.offensiveBuffButtons


offensiveBuffButtonNameIndicatesSelfShipIsPointed : String -> Bool
offensiveBuffButtonNameIndicatesSelfShipIsPointed offensiveBuffButtonName =
    case String.toLower offensiveBuffButtonName of
        "warpscrambler" ->
            True

        "webify" ->
            True

        _ ->
            False


abovemainMessageSaysNotEnoughBandwidthToLaunchDrone : String -> Bool
abovemainMessageSaysNotEnoughBandwidthToLaunchDrone message =
    {-
       Observed in session-recording-2023-04-08T19-20-34.zip-event-285-eve-online-memory-reading:
       <center>You don't have enough bandwidth to launch Berserker II. You need 25.0 Mbit/s but only have 0.0 Mbit/s available.
    -}
    String.contains "don't have enough bandwidth to launch" message


randomIntFromInterval : BotDecisionContext -> IntervalInt -> Int
randomIntFromInterval context interval =
    let
        randomInteger =
            context.randomIntegers
                |> List.head
                |> Maybe.withDefault 0

        intervalLength =
            interval.maximum - interval.minimum
    in
    if intervalLength < 1 then
        interval.minimum

    else
        interval.minimum + (randomInteger |> modBy intervalLength)
