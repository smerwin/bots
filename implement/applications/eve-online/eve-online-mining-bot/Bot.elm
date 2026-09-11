{- EVE Online mining bot version 2025-11-24

   This bot automates the complete mining process, including offloading the ore and traveling between the mining spot and the unloading location.

   In addition to the automation, the bot reports performance statistics such as the number of completed cycles and the aggregate volume of mined ore in a standardized format.

   This bot supports configuring multiple mining sites. It picks a random asteroid belt from the solar system menu if no mining site is configured. When the bot settings contain at least one mining site, the bot searches the 'Locations' window and overview windows to find one of the sites and initiate warping the ship there.

   If no station name or structure name is given with the bot-settings, the bot docks again at the station where it was last docked.

   Setup instructions for the EVE Online client:

   + Set the UI language to English.
   + In the ship UI in the 'Options' menu, tick the checkbox for 'Display Module Tooltips'.
   + In Overview window, make asteroids visible.
   + Open one inventory window.
   + If you want to use drones for defense against rats, place them in the drone bay, and open the 'Drones' window.
   + If flying in wormhole space with `wormhole = yes`, leave the Directional Scanner window open and its range and angle wide enough to cover the grid, bind its scan to `V` (the client's own default) and leave it bound, and leave the Local chat window open.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit your use-case.

   + `anomaly-name` : Name of a cosmic anomaly to warp to for mining, as it appears under 'Anomalies' in the solar system surroundings menu. Can be used multiple times. Checked before `mining-site` and before picking a random asteroid belt -- this is the setting to reach for when the mining spot is a cosmic anomaly rather than a bookmarked or named location.
   + `mining-site` : Name of a mining location, as it appears in the 'Label' column of the 'Locations' window.
   + `unload-station-name` : Name of a station to dock to when the mining hold is full.
   + `unload-structure-name` : Name of a structure to dock to when the mining hold is full.
   + `activate-module-always` : Text found in tooltips of ship modules that should always be active. For example: "shield hardener".
   + `hide-when-neutral-in-local` : Should we hide when a neutral or hostile pilot appears in the local chat? The only supported values are `no` and `yes`.
   + `unload-fleet-hangar-percent` : This will make the bot unload the mining hold at least XX percent full to the fleet hangar, you must be in a fleet with an orca or a rorqual and the fleet hangar must be visible within the inventory window.
   + `dock-when-without-drones` : This will make the bot dock when it's out of drones. The only supported values are `no` and `yes`.
   + `repair-before-undocking` : Repair the ship at the station before undocking. The only supported values are `no` and `yes`.
   + `afterburner-module-text` : Text found in tooltips of the afterburner module.
   + `afterburner-distance-threshold` : Distance threshold (in meters) at which to activate/deactivate the afterburner.
   + `return-drones-when-no-rats-visible` : Return drones to bay when no rats are visible in space. Default is `yes`.
   + `wormhole` : Turn on wormhole-space safety -- periodically refresh the Directional Scanner and run for the unload station/structure once it shows a ship that is not one of ours. Local chat carries no roster in a wormhole, unlike known space, which is why this exists as its own setting rather than relying on `hide-when-neutral-in-local`. The only supported values are `no` and `yes`, default `no`.
   + `friendly-ship-tag` : Only meaningful with `wormhole = yes`. A substring marking a ship on the Directional Scanner as one of ours; every other ship reads hostile, and so does every ship when this is unset.
   + `dscan-interval-seconds` : Only meaningful with `wormhole = yes`. How often to refresh the Directional Scanner, in seconds. Default 5.
   + `aggressive` : Fight rather than flee. Wherever this bot would otherwise run away, it launches drones, locks whatever on the overview reads hostile, and sends the drones after it instead -- see the setting's own description under `--help` for the detail. The only supported values are `no` and `yes`, default `no`.

   When using more than one setting, start a new line for each setting in the text input field.
   Here is an example of a complete settings string:

   ```
   mining-site = mining bookmark label
   unload-station-name = Noghere VII - Moon 15
   activate-module-always = shield hardener
   activate-module-always = afterburner
   return-drones-when-no-rats-visible = no
   ```

   The bot searches the configured structure or station name in the 'Locations' window and all overview windows.
   If the destination is not visible in the locations and overview windows, it opens the solar system menu to search for it.
   When using the 'Locations' window, enter the unload station/structure name as it appears in the 'Label' column.

   To learn more about the mining bot, see <https://to.botlab.org/guide/app/eve-online-mining-bot>

-}
{-
   catalog-tags:eve-online,mining
   authors-forum-usernames:viir
-}


module Bot exposing
    ( State
    , botMain
    )

import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost
import Common
import Common.Basics exposing (listElementAtWrappedIndex, stringContainsIgnoringCase)
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
        , UIElement
        , localChatWindowFromUserInterface
        , menuCascadeCompleted
        , mouseClickOnUIElement
        , shipUIIndicatesShipIsWarpingOrJumping
        , uiNodeVisibleRegionLargeEnoughForClicking
        , useMenuEntryInLastContextMenuInCascade
        , useMenuEntryWithTextContaining
        , useMenuEntryWithTextContainingFirstOf
        , useMenuEntryWithTextEqual
        , useRandomMenuEntry
        )
import EveOnline.BotFrameworkSeparatingMemory
    exposing
        ( DecisionPathNode
        , EndDecisionPathStructure(..)
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
import EveOnline.MemoryReading
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindowEntry
        , centerFromDisplayRegion
        , getAllContainedDisplayTextsWithRegion
        )
import Json.Decode
import List.Extra
import Maybe.Extra
import Result.Extra
import Set


{-| Sources for the defaults:

  - <https://forum.botlab.org/t/mining-bot-wont-approach/3162>

-}
defaultBotSettings : BotSettings
defaultBotSettings =
    { runAwayShieldHitpointsThresholdPercent = 70
    , unloadStationNames = []
    , unloadStructureNames = []
    , unloadFleetHangarPercent = -1
    , unloadMiningHoldPercent = 99
    , activateModulesAlways = []
    , hideWhenNeutralInLocal = Nothing
    , dockWhenWithoutDrones = Nothing
    , repairBeforeUndocking = Nothing
    , targetingRange = 8000
    , miningModuleRange = 5000
    , botStepDelayMilliseconds = { minimum = 1300, maximum = 1500 }
    , selectInstancePilotName = Nothing
    , includeAsteroidPatterns = []
    , miningSites = []
    , anomalyNamePatterns = []
    , afterburnerModuleText = Nothing
    , afterburnerDistanceThreshold = Nothing
    , compressFromMiningHold = PromptParser.No
    , returnDronesWhenNoRatsVisible = PromptParser.Yes
    , wormhole = PromptParser.No
    , friendlyShipTag = Nothing
    , dscanIntervalSeconds = defaultDscanIntervalSeconds
    , aggressive = PromptParser.No
    }


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    PromptParser.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "run-away-shield-hitpoints-threshold-percent"
           , { alternativeNames = []
             , description = "Threshold of shield hitpoints in percent to trigger running away."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\threshold settings -> { settings | runAwayShieldHitpointsThresholdPercent = threshold })
             }
           )
         , ( "unload-station-name"
           , { alternativeNames = []
             , description = "Name of a station to dock to when the mining hold is full."
             , valueParser =
                PromptParser.valueTypeString
                    (\stationName settings ->
                        { settings
                            | unloadStationNames = String.trim stationName :: settings.unloadStationNames
                        }
                    )
             }
           )
         , ( "unload-structure-name"
           , { alternativeNames = []
             , description = "Name of a structure to dock to when the mining hold is full."
             , valueParser =
                PromptParser.valueTypeString
                    (\structureName settings ->
                        { settings
                            | unloadStructureNames = String.trim structureName :: settings.unloadStructureNames
                        }
                    )
             }
           )
         , ( "unload-fleet-hangar-percent"
           , { alternativeNames = []
             , description = "This will make the bot to unload the mining hold at least XX percent full to the fleet hangar, you must be in a fleet with an orca or a rorqual and the fleet hangar must be visible within the inventory window."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\fleetHangarPercent settings -> { settings | unloadFleetHangarPercent = fleetHangarPercent })
             }
           )
         , ( "unload-mining-hold-percent"
           , { alternativeNames = []
             , description = "When the mining hold is filled at least this much, we start unloading the ore."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\percent settings -> { settings | unloadMiningHoldPercent = percent })
             }
           )
         , ( "activate-module-always"
           , { alternativeNames = []
             , description = "Text found in tooltips of ship modules that should always be active. For example: 'shield hardener'."
             , valueParser =
                PromptParser.valueTypeString
                    (\moduleName settings -> { settings | activateModulesAlways = moduleName :: settings.activateModulesAlways })
             }
           )
         , ( "hide-when-neutral-in-local"
           , { alternativeNames = []
             , description = "Should we hide when a neutral or hostile pilot appears in the local chat? The only supported values are `no` and `yes`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\hide settings -> { settings | hideWhenNeutralInLocal = Just hide })
             }
           )
         , ( "dock-when-without-drones"
           , { alternativeNames = []
             , description = "This will make the bot dock when it's out of drones. The only supported values are `no` and `yes`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\without settings -> { settings | dockWhenWithoutDrones = Just without })
             }
           )
         , ( "repair-before-undocking"
           , { alternativeNames = []
             , description = "Repair the ship at the station before undocking. The only supported values are `no` and `yes`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\repair settings -> { settings | repairBeforeUndocking = Just repair })
             }
           )
         , ( "targeting-range"
           , { alternativeNames = []
             , description = "Distance under which we try to target an object in space."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\range settings -> { settings | targetingRange = range })
             }
           )
         , ( "mining-module-range"
           , { alternativeNames = []
             , description = "Range of the mining modules in the current ship fitting."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\range settings -> { settings | miningModuleRange = range })
             }
           )
         , ( "select-instance-pilot-name"
           , { alternativeNames = []
             , description = "Name of EVE Online character to search for when selecting an instance of the game client."
             , valueParser =
                PromptParser.valueTypeString
                    (\pilotName settings -> { settings | selectInstancePilotName = Just pilotName })
             }
           )
         , ( "bot-step-delay"
           , { alternativeNames = []
             , description = "Minimum time between starting bot steps in milliseconds. You can also specify a range like `1000 - 2000`. The bot then picks a random value in this range."
             , valueParser =
                PromptParser.parseIntervalIntFromPointOrIntervalString
                    >> Result.map
                        (\delay settings -> { settings | botStepDelayMilliseconds = delay })
             }
           )
         , ( "include-asteroid-pattern"
           , { alternativeNames = []
             , description = "Names of asteroids to select for mining. Can be used multiple times. If the setting is used zero times, we mine all kinds of asteroids."
             , valueParser =
                PromptParser.valueTypeString
                    (\pattern settings ->
                        { settings | includeAsteroidPatterns = pattern :: settings.includeAsteroidPatterns }
                    )
             }
           )
         , ( "mining-site"
           , { alternativeNames = [ "mining-site-location" ]
             , description = "Name of a mining site as it appears in the 'Locations' window or under 'Locations' in the solar system surroundings menu."
             , valueParser =
                PromptParser.valueTypeString
                    (\miningSite settings ->
                        { settings | miningSites = List.concat [ settings.miningSites, [ miningSite ] ] }
                    )
             }
           )
         , ( "anomaly-name"
           , { alternativeNames = []
             , description = "Name of a cosmic anomaly (as listed under 'Anomalies' in the solar system surroundings menu) to warp to for mining. Can be used multiple times; the first one found each time we need a new site wins. Checked before 'mining-site' and before picking a random asteroid belt."
             , valueParser =
                PromptParser.valueTypeString
                    (\pattern settings ->
                        { settings | anomalyNamePatterns = List.concat [ settings.anomalyNamePatterns, [ pattern ] ] }
                    )
             }
           )
         , ( "afterburner-module-text"
           , { alternativeNames = []
             , description = "Text found in tooltips of the afterburner module."
             , valueParser =
                PromptParser.valueTypeString
                    (\moduleName settings -> { settings | afterburnerModuleText = Just moduleName })
             }
           )
         , ( "afterburner-distance-threshold"
           , { alternativeNames = []
             , description = "Distance threshold (in meters) to trigger the afterburner activation."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\distance settings -> { settings | afterburnerDistanceThreshold = Just distance })
             }
           )
         , ( "compress-from-mining-hold"
           , { alternativeNames = []
             , description = "Compress items from the mining hold, when the mining hold is filled at least 75 %. The only supported values are `no` and `yes`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\compress settings -> { settings | compressFromMiningHold = compress })
             }
           )
         , ( "return-drones-when-no-rats-visible"
           , { alternativeNames = []
             , description = "Return drones to bay when no rats are visible in space. The only supported values are `no` and `yes`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\returnDrones settings -> { settings | returnDronesWhenNoRatsVisible = returnDrones })
             }
           )
         , ( "wormhole"
           , { alternativeNames = []
             , description = "Turn on wormhole-space safety, ported from `eve-online-gas-huffer`: periodically refresh the Directional Scanner and, once it shows a ship this bot does not recognize as one of ours, run for the configured unload station or structure the same way a low shield percentage does. Local chat carries no passive roster in a wormhole, so this replaces `hide-when-neutral-in-local`'s security-status heuristic there -- see `friendly-ship-tag`. The only supported values are `no` and `yes`, default `no` so an existing settings string is unaffected."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\wormhole settings -> { settings | wormhole = wormhole })
             }
           )
         , ( "friendly-ship-tag"
           , { alternativeNames = []
             , description = "Only meaningful with `wormhole=yes`. A substring marking a ship seen on the Directional Scanner as one of ours; every other ship reads hostile, and so does every ship when this setting is unset -- an unset tag means trust nobody, never trust everybody. Matched ignoring case, so it can be a corporation ticker in brackets or a fleet naming convention."
             , valueParser =
                PromptParser.valueTypeString
                    (\tag settings ->
                        { settings
                            | friendlyShipTag =
                                case String.trim tag of
                                    "" ->
                                        Nothing

                                    trimmedTag ->
                                        Just trimmedTag
                        }
                    )
             }
           )
         , ( "dscan-interval-seconds"
           , { alternativeNames = []
             , description = "Only meaningful with `wormhole=yes`. How often to refresh the Directional Scanner, in seconds. Default " ++ String.fromInt defaultDscanIntervalSeconds ++ ", unmeasured against this bot's own runs -- see the doc comment on `defaultDscanIntervalSeconds`."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\seconds settings -> { settings | dscanIntervalSeconds = seconds })
             }
           )
         , ( "aggressive"
           , { alternativeNames = []
             , description = "Fight rather than flee. Wherever this bot would otherwise run away or leave a wormhole -- a shield percentage below `run-away-shield-hitpoints-threshold-percent`, or (with `wormhole=yes`) a ship the Directional Scanner does not recognize as one of ours -- it launches drones, locks whatever on the overview reads hostile (a rat by its icon colour, or anything reading as warp disrupting this ship, checked first since that is the one thing standing between this ship and leaving), and sends the drones to engage it instead. Only takes effect where there is something on the overview to engage; with nothing there to lock, it still runs away, since there is nothing here for it to fight. The only supported values are `no` and `yes`, default `no`."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\aggressive settings -> { settings | aggressive = aggressive })
             }
           )
         ]
            |> Dict.fromList
        )
        defaultBotSettings


{-|


## Wormhole safety (issue #490)

`hide-when-neutral-in-local`'s own fallback is a k-space idea: it reads the
current system's security-status percent, which a wormhole does not have, and
even where an operator sets it explicitly, local chat in a wormhole carries no
passive roster the way known-space local does -- a hostile pilot gives this
bot no warning there before they are already on top of it.

`eve-online-gas-huffer` was built for exactly this environment (issues #462,
#463) and this section is that bot's Directional-Scanner-based hostile
detection, ported to this bot's own decision tree rather than assumed to slot
in unchanged. Two differences from the huffer's own copy, both because this
bot is not that one:

  - **No cloak, no celestial-bounce escalation.** The huffer has nothing but
    open space to retreat into and no docking step of its own, so its
    escalation is cloak-then-bounce. This bot already has a retreat that ends
    somewhere real -- `runAway`, the same one a low shield percentage
    triggers -- so a hostile on D-Scan is composed with that machinery
    instead of a second one invented beside it.
  - **`harvestableCloudTypeMarker`** (the huffer's own gas cloud) is dropped
    from `notAShipOnDscanTypeMarkers` rather than replaced with an asteroid
    marker: nothing here has measured what an ore asteroid or anomaly reads as
    on this bot's Directional Scanner, and this file's own rule is that
    nothing goes in that list without a string somebody has read off a live
    client.

Everything below is `wormhole = no` by default, so an existing settings
string is unaffected -- see `wormholeSafetyStep`, the one place any of this is
read from the decision tree.

**Untested against a live client.** The huffer's own corpus (quoted in its
`Bot.elm`) is what every number and every doc comment below still leans on;
nothing here has watched a ship arrive on this bot's own Directional Scanner.

-}
type HostileTrust
    = TrustNobody
    | TrustShipsTagged String


hostileTrustFromSettings : BotSettings -> HostileTrust
hostileTrustFromSettings settings =
    case settings.friendlyShipTag of
        Nothing ->
            TrustNobody

        Just tag ->
            TrustShipsTagged tag


{-| Whether a ship named this way is one of ours.

Matched as a substring and ignoring case, because the tag is a naming
convention rather than a name. `TrustNobody` answers `False` for every name
there is, including the empty one -- and the settings handler for
`friendly-ship-tag` is what stops an empty tag ever reaching
`TrustShipsTagged`, where it would match every ship instead.

-}
shipReadsFriendly : HostileTrust -> String -> Bool
shipReadsFriendly trust shipName =
    case trust of
        TrustNobody ->
            False

        TrustShipsTagged tag ->
            stringContainsIgnoringCase tag shipName


describeHostileTrust : HostileTrust -> String
describeHostileTrust trust =
    case trust of
        TrustNobody ->
            "Friendly ships: none named, so every ship reads hostile ('friendly-ship-tag' is unset)."

        TrustShipsTagged tag ->
            "Friendly ships: those whose name carries '" ++ tag ++ "'; every other ship reads hostile."


chatUserFleetmateMarker : String
chatUserFleetmateMarker =
    "Pilot is in your fleet"


{-| Whether Local says this pilot is one of ours.

`Nothing` is a chat row whose standing icon this reading could not resolve,
and it answers `False` -- a stranger, the fail-closed direction for wormhole
safety.

-}
chatUserIsKnownFleetmate : EveOnline.ParseUserInterface.ChatUserEntry -> Bool
chatUserIsKnownFleetmate chatUser =
    case chatUser.standingIconHint of
        Nothing ->
            False

        Just standingIconHint ->
            stringContainsIgnoringCase chatUserFleetmateMarker standingIconHint


{-| Every pilot on the overview who Local does not say is a fleet-mate.

Ported from `eve-online-gas-huffer`'s copy of `getNamesOfOtherPilotsInOverview`
(`eve-online-combat-anomaly-bot`'s own shape): the chat rows are what say a
name belongs to a _player_, so an overview row is a pilot exactly where its
Name appears in Local, and the fleet-mates are filtered out of that list
before the match rather than after it.

Compared trimmed and ignoring case, because the two sides are two renderings
of one name by two widgets.

-}
pilotsOnTheOverviewNotInTheFleet :
    List EveOnline.ParseUserInterface.ChatUserEntry
    -> List OverviewWindowEntry
    -> List String
pilotsOnTheOverviewNotInTheFleet localChatUsers overviewEntries =
    let
        normalize =
            String.trim >> String.toLower

        strangers =
            localChatUsers
                |> List.filter (chatUserIsKnownFleetmate >> not)
                |> List.filterMap .name
                |> List.map normalize
    in
    overviewEntries
        |> List.filterMap .objectName
        |> List.filter (\name -> strangers |> List.member (normalize name))


{-| Every rat on the overview, by this bot's own icon-colour rule
(`iconSpriteHasColorOfRat`, defined below for `overviewShowsRat`), as rows
rather than names -- a rat whose Name column is not visible still fires this,
and `gridEvidenceFromReading` is what names it afterwards.
-}
ratsOnTheOverview : List OverviewWindowEntry -> List OverviewWindowEntry
ratsOnTheOverview =
    List.filter iconSpriteHasColorOfRat


{-| Every drone group the client writes carries this word, and no ship hull
does -- see `eve-online-gas-huffer`'s own copy of this constant for the
measurement (run 6 evaded on `Mining Drone I` rows and harvested nothing).
Matched on the Type cell only: a Name is whatever a player typed, and a ship
called "Dronebait" must still read hostile.
-}
droneTypeMarker : String
droneTypeMarker =
    "Drone"


{-| Type-column markers that say a D-Scan row is a structure or a deployable
rather than a ship, ported from `eve-online-gas-huffer`'s
`notAShipOnDscanTypeMarkers` with the gas huffer's own harvestable-cloud
marker dropped -- see this section's own doc comment for why nothing replaces
it.
-}
notAShipOnDscanTypeMarkers : List String
notAShipOnDscanTypeMarkers =
    [ "Astrahus"
    , "Fortizar"
    , "Keepstar"
    , "Raitaru"
    , "Azbel"
    , "Sotiyo"
    , "Athanor"
    , "Tatara"
    , "Ansiblex Jump Gate"
    , "Pharolux Cyno Beacon"
    , "Tenebrex Cyno Jammer"
    , "Metenox Moon Drill"
    , "Control Tower"
    , "Customs Office"
    , "Mobile "
    , droneTypeMarker
    ]


{-| Whether a D-Scan row's Type says it is not a ship. Matched ignoring case
as a substring. A Type cell this parser could not read is not a structure,
so an absent Type falls through to the ship branch in `dscanRowVerdict`.
-}
dscanTypeIsNotAShip : String -> Bool
dscanTypeIsNotAShip typeText =
    notAShipOnDscanTypeMarkers
        |> List.any (\marker -> stringContainsIgnoringCase marker typeText)


structureTypeThatIsNotAShip : String -> Maybe String
structureTypeThatIsNotAShip typeText =
    if dscanTypeIsNotAShip typeText then
        Just typeText

    else
        Nothing


{-| A probe is not a ship -- except a combat probe, which is a hunt in
progress. Ported from `eve-online-gas-huffer`'s `dscanRowIsHarmlessProbe`;
see that bot's own doc comment for the measurement behind the distinction
(evading combat probes is good, evading a system's own scanner probes is
paranoid) and for why both cells are tested.
-}
probeMarker : String
probeMarker =
    "Scanner Probe"


combatProbeMarker : String
combatProbeMarker =
    "Combat Scanner Probe"


dscanRowIsHarmlessProbe : { name : Maybe String, type_ : Maybe String } -> Bool
dscanRowIsHarmlessProbe row =
    let
        anyCellContains marker =
            [ row.name, row.type_ ]
                |> List.filterMap identity
                |> List.any (stringContainsIgnoringCase marker)
    in
    anyCellContains probeMarker && not (anyCellContains combatProbeMarker)


{-| The three cells of one D-Scan row, as a record a case can write out --
`eve-online-gas-huffer`'s own shape, kept separate from
`EveOnline.ParseUserInterface.DirectionalScanResult` because that type also
carries a `uiNode` nothing here reads.
-}
type alias DscanSighting =
    { name : Maybe String
    , type_ : Maybe String
    , distance : Maybe String
    }


dscanSightingsFromWindow : EveOnline.ParseUserInterface.DirectionalScannerWindow -> List DscanSighting
dscanSightingsFromWindow window =
    window.scanResults
        |> List.map (\row -> { name = row.name, type_ = row.type_, distance = row.distance })


{-| What this bot makes of one row on D-Scan. Ported whole from
`eve-online-gas-huffer`'s `dscanRowVerdict`; see that bot's own doc comment
for why absent evidence reads as hostile here (inverting this repo's usual
direction) and for the `RowCouldNotBeRead` case, added there after a
mid-redraw D-Scan reading flipped a system's own scanner probes between
harmless and hostile from one refresh to the next.
-}
type DscanRowVerdict
    = RowIsNotAShip String
    | ShipIsOneOfOurs String
    | ShipIsHostile DscanHostileReason
    | RowCouldNotBeRead


type DscanHostileReason
    = ShipNameCarriesNoFriendlyTag String
    | ShipNameCouldNotBeRead


dscanRowVerdict : HostileTrust -> DscanSighting -> DscanRowVerdict
dscanRowVerdict trust row =
    if dscanRowIsHarmlessProbe { name = row.name, type_ = row.type_ } then
        RowIsNotAShip (row.type_ |> Maybe.withDefault probeMarker)

    else
        case row.type_ |> Maybe.andThen structureTypeThatIsNotAShip of
            Just typeText ->
                RowIsNotAShip typeText

            Nothing ->
                case ( row.type_, row.name ) of
                    ( Nothing, Nothing ) ->
                        RowCouldNotBeRead

                    ( _, Nothing ) ->
                        ShipIsHostile ShipNameCouldNotBeRead

                    ( _, Just name ) ->
                        if shipReadsFriendly trust name then
                            ShipIsOneOfOurs name

                        else
                            ShipIsHostile (ShipNameCarriesNoFriendlyTag name)


dscanHostileReason : DscanRowVerdict -> Maybe String
dscanHostileReason verdict =
    case verdict of
        ShipIsHostile (ShipNameCarriesNoFriendlyTag name) ->
            Just ("'" ++ name ++ "'")

        ShipIsHostile ShipNameCouldNotBeRead ->
            Just "one whose Name cell this parser could not read at all"

        RowIsNotAShip _ ->
            Nothing

        ShipIsOneOfOurs _ ->
            Nothing

        RowCouldNotBeRead ->
            Nothing


describeDscanRowVerdict : DscanRowVerdict -> String
describeDscanRowVerdict verdict =
    case verdict of
        RowIsNotAShip typeText ->
            "not a ship (Type '" ++ typeText ++ "')"

        ShipIsOneOfOurs name ->
            "ours ('" ++ name ++ "')"

        ShipIsHostile (ShipNameCarriesNoFriendlyTag name) ->
            "HOSTILE, no friendly tag ('" ++ name ++ "')"

        ShipIsHostile ShipNameCouldNotBeRead ->
            "HOSTILE, Name cell unreadable"

        RowCouldNotBeRead ->
            "row unreadable this reading, not judged"


{-| What the Directional Scanner is telling this bot, including that it is
not. Four answers, ported from `eve-online-gas-huffer`'s `DscanState`, so "we
do not know" cannot collapse into "clean" the way `Nothing`/`Maybe.withDefault`
would.
-}
type DscanState
    = DscanWindowIsNotInTheReading
    | DscanHasNeverBeenScanned
    | DscanIsStale { secondsSinceScan : Int, staleAfterSeconds : Int }
    | DscanWasRead (List DscanRowVerdict)


{-| How many refresh intervals a scan may be old before it stops counting. A
multiple of `dscan-interval-seconds` rather than a bare number, so the two
cannot drift apart. Kept at the huffer's own value of 3, unmeasured against
this bot's own runs.
-}
dscanStaleAfterIntervals : Int
dscanStaleAfterIntervals =
    3


dscanStaleAfterSeconds : Int -> Int
dscanStaleAfterSeconds intervalSeconds =
    intervalSeconds * dscanStaleAfterIntervals


dscanState :
    HostileTrust
    ->
        { windowSightings : Maybe (List DscanSighting)
        , secondsSinceScan : Maybe Int
        , staleAfterSeconds : Int
        }
    -> DscanState
dscanState trust reading =
    case reading.windowSightings of
        Nothing ->
            DscanWindowIsNotInTheReading

        Just sightings ->
            case reading.secondsSinceScan of
                Nothing ->
                    DscanHasNeverBeenScanned

                Just secondsSinceScan ->
                    if reading.staleAfterSeconds < secondsSinceScan then
                        DscanIsStale
                            { secondsSinceScan = secondsSinceScan
                            , staleAfterSeconds = reading.staleAfterSeconds
                            }

                    else
                        DscanWasRead (sightings |> List.map (dscanRowVerdict trust))


{-| Everything one reading says about whether this ship should still be here.
A record of plain facts rather than a `BotDecisionContext`, so a case can
execute `gridVerdict` directly -- the same reason `eve-online-gas-huffer`
gives for its own copy.
-}
type alias GridEvidence =
    { ratsOnOverview : List String
    , pilotsNotInTheFleet : List String
    , localChatIsReadable : Bool
    , dscan : DscanState
    }


{-| The verdict, and the two ways of not being clean -- a grid this bot
cannot see is not one it may go on mining, and it is also not one it has seen
a hostile on. `gridReadsClean` answers `True` for `GridIsClean` and nothing
else.
-}
type GridVerdict
    = GridIsClean
    | SomethingIsOnTheGrid (List String)
    | CannotTellWhetherTheGridIsClean (List String)


gridReadsClean : GridVerdict -> Bool
gridReadsClean verdict =
    verdict == GridIsClean


gridVerdict : GridEvidence -> GridVerdict
gridVerdict evidence =
    let
        named what names =
            String.fromInt (List.length names)
                ++ " "
                ++ what
                ++ (if List.isEmpty names then
                        ""

                    else
                        ": " ++ String.join ", " names
                   )

        hostileReasons =
            [ if List.isEmpty evidence.ratsOnOverview then
                Nothing

              else
                Just (named "rat(s) on the overview by icon colour" evidence.ratsOnOverview)
            , if List.isEmpty evidence.pilotsNotInTheFleet then
                Nothing

              else
                Just
                    (named "pilot(s) on the overview who are not in this fleet"
                        evidence.pilotsNotInTheFleet
                    )
            ]
                |> List.filterMap identity

        hostileShips =
            case evidence.dscan of
                DscanWasRead verdicts ->
                    verdicts |> List.filterMap dscanHostileReason

                _ ->
                    []

        dscanHostileClause =
            if List.isEmpty hostileShips then
                []

            else
                [ named "ship(s) on D-Scan that are not ours" hostileShips ]

        doubts =
            [ case evidence.dscan of
                DscanWindowIsNotInTheReading ->
                    Just "there is no Directional Scanner window in this reading, so nothing here can see a ship that is not already on the overview"

                DscanHasNeverBeenScanned ->
                    Just "the Directional Scanner has not answered a refresh yet this session"

                DscanIsStale stale ->
                    Just
                        ("the last Directional Scan completed "
                            ++ String.fromInt stale.secondsSinceScan
                            ++ "s ago, past the "
                            ++ String.fromInt stale.staleAfterSeconds
                            ++ "s a scan is believed for"
                        )

                DscanWasRead _ ->
                    Nothing
            , if evidence.localChatIsReadable then
                Nothing

              else
                Just "Local chat is not readable, so nothing here can tell which overview rows are pilots at all"
            ]
                |> List.filterMap identity
    in
    case hostileReasons ++ dscanHostileClause of
        [] ->
            case doubts of
                [] ->
                    GridIsClean

                _ ->
                    CannotTellWhetherTheGridIsClean doubts

        reasons ->
            SomethingIsOnTheGrid reasons


{-| The evidence this reading carries, assembled from the client. Ported from
`eve-online-gas-huffer`'s `gridEvidenceFromReading`; see that bot's own doc
comment for why `overviewEntryIsDisplayed` is deliberately not applied here.
-}
gridEvidenceFromReading :
    HostileTrust
    -> { secondsSinceScan : Maybe Int, staleAfterSeconds : Int }
    -> ReadingFromGameClient
    -> GridEvidence
gridEvidenceFromReading trust scanAge readingFromGameClient =
    let
        localChatUsers =
            readingFromGameClient
                |> localChatWindowFromUserInterface
                |> Maybe.andThen .userlist
                |> Maybe.map .visibleUsers

        overviewEntries =
            readingFromGameClient.overviewWindows |> List.concatMap .entries
    in
    { ratsOnOverview =
        ratsOnTheOverview overviewEntries
            |> List.map (.objectName >> Maybe.withDefault "a rat whose Name column is not readable")
    , pilotsNotInTheFleet =
        pilotsOnTheOverviewNotInTheFleet
            (localChatUsers |> Maybe.withDefault [])
            overviewEntries
    , localChatIsReadable = localChatUsers /= Nothing
    , dscan =
        dscanState trust
            { windowSightings =
                readingFromGameClient.directionalScannerWindow
                    |> Maybe.map dscanSightingsFromWindow
            , secondsSinceScan = scanAge.secondsSinceScan
            , staleAfterSeconds = scanAge.staleAfterSeconds
            }
    }


gridEvidenceFromContext : BotDecisionContext -> GridEvidence
gridEvidenceFromContext context =
    let
        settings =
            context.eventContext.botSettings
    in
    gridEvidenceFromReading (hostileTrustFromSettings settings)
        { secondsSinceScan =
            secondsSinceLastScan
                { nowMilliseconds = context.eventContext.timeInMilliseconds
                , dscan = context.memory.dscan
                }
        , staleAfterSeconds = dscanStaleAfterSeconds settings.dscanIntervalSeconds
        }
        context.readingFromGameClient


describeGrid : GridEvidence -> String
describeGrid evidence =
    (case gridVerdict evidence of
        GridIsClean ->
            "Grid: CLEAN -- nothing on the overview or on D-Scan says otherwise."

        SomethingIsOnTheGrid reasons ->
            "Grid: SOMETHING IS HERE -- " ++ String.join "; " reasons ++ "."

        CannotTellWhetherTheGridIsClean doubts ->
            "Grid: CANNOT TELL, which is not the same as clean -- "
                ++ String.join "; " doubts
                ++ "."
    )
        ++ " "
        ++ describeDscanRows evidence.dscan


describeDscanRows : DscanState -> String
describeDscanRows state =
    case state of
        DscanWindowIsNotInTheReading ->
            "D-Scan: no window in this reading, so there are no rows to print."

        DscanHasNeverBeenScanned ->
            "D-Scan: the window is open and no refresh has completed yet this session."

        DscanIsStale stale ->
            "D-Scan: the window is open and its last completed scan is "
                ++ String.fromInt stale.secondsSinceScan
                ++ "s old, past the "
                ++ String.fromInt stale.staleAfterSeconds
                ++ "s bound, so its rows are not being judged."

        DscanWasRead [] ->
            "D-Scan: scanned, and nothing at all is on it."

        DscanWasRead verdicts ->
            "D-Scan judged "
                ++ String.fromInt (List.length verdicts)
                ++ " row(s): "
                ++ (verdicts |> List.map describeDscanRowVerdict |> String.join "; ")
                ++ "."


directionalScanHotkey : List EffectOnWindow.VirtualKeyCode
directionalScanHotkey =
    [ EffectOnWindow.vkey_V ]


{-| The keys one press holds down, in the order a chord wants them. Down in
order and up in reverse, so a modifier is released after the key it modifies.
-}
hotkeyEffects : List EffectOnWindow.VirtualKeyCode -> List EffectOnWindow.EffectOnWindowStruct
hotkeyEffects chord =
    (chord |> List.map EffectOnWindow.KeyDown)
        ++ (chord |> List.reverse |> List.map EffectOnWindow.KeyUp)


{-| Whether a dispatched step pressed **exactly** this chord and nothing
else. Equality on the step's own key-down sequence rather than "contains
every key of the chord".
-}
stepPressedExactly : List EffectOnWindow.VirtualKeyCode -> List EffectOnWindow.EffectOnWindowStruct -> Bool
stepPressedExactly chord effects =
    (effects
        |> List.filterMap
            (\effect ->
                case effect of
                    EffectOnWindow.KeyDown keyCode ->
                        Just keyCode

                    _ ->
                        Nothing
            )
    )
        == chord


{-| Unmeasured against this bot's own runs, and stated as such rather than
dressed up as a derived number -- ported from `eve-online-gas-huffer`, whose
own default this is, chosen there to cost roughly one reading in ten at the
shipped step delay rather than a figure derived from how long a hostile
takes to arrive.
-}
defaultDscanIntervalSeconds : Int
defaultDscanIntervalSeconds =
    5


{-| When the last refresh went out, and when a scan last came back. Two
clocks rather than one, ported from `eve-online-gas-huffer`'s `DscanMemory`:
`lastRefreshAskedAtMilliseconds` paces the keypress, `lastScanAtMilliseconds`
is what the staleness check believes.
-}
type alias DscanMemory =
    { lastRefreshAskedAtMilliseconds : Maybe Int
    , lastScanAtMilliseconds : Maybe Int
    }


initDscanMemory : DscanMemory
initDscanMemory =
    { lastRefreshAskedAtMilliseconds = Nothing
    , lastScanAtMilliseconds = Nothing
    }


dscanMemoryAfterReading :
    { nowMilliseconds : Int
    , refreshAskedInPreviousStep : Bool
    , windowIsInTheReading : Bool
    }
    -> DscanMemory
    -> DscanMemory
dscanMemoryAfterReading reading before =
    { lastRefreshAskedAtMilliseconds =
        if reading.refreshAskedInPreviousStep then
            Just reading.nowMilliseconds

        else
            before.lastRefreshAskedAtMilliseconds
    , lastScanAtMilliseconds =
        if reading.refreshAskedInPreviousStep && reading.windowIsInTheReading then
            Just reading.nowMilliseconds

        else
            before.lastScanAtMilliseconds
    }


secondsSinceLastScan : { nowMilliseconds : Int, dscan : DscanMemory } -> Maybe Int
secondsSinceLastScan { nowMilliseconds, dscan } =
    dscan.lastScanAtMilliseconds
        |> Maybe.map (\scannedAt -> (nowMilliseconds - scannedAt) // 1000)


{-| Whether it is time to press the scan key again. A floor rather than a
schedule: this host stands down for a human at the keyboard, so a refresh
that does not go out costs nothing here and is asked for again at the next
reading past the interval.
-}
dscanRefreshIsDue : { nowMilliseconds : Int, intervalSeconds : Int, dscan : DscanMemory } -> Bool
dscanRefreshIsDue { nowMilliseconds, intervalSeconds, dscan } =
    case dscan.lastRefreshAskedAtMilliseconds of
        Nothing ->
            True

        Just askedAt ->
            intervalSeconds * 1000 <= nowMilliseconds - askedAt


{-| Press the scan key, where the interval says one is due. `Nothing` rather
than a branch that waits, so a reading with no refresh due falls straight
through to mining -- and not asked at all on a reading with no ship UI, which
is a docked one.
-}
refreshTheDirectionalScanner : BotDecisionContext -> Maybe DecisionPathNode
refreshTheDirectionalScanner context =
    if context.readingFromGameClient.shipUI == Nothing then
        Nothing

    else if
        dscanRefreshIsDue
            { nowMilliseconds = context.eventContext.timeInMilliseconds
            , intervalSeconds = context.eventContext.botSettings.dscanIntervalSeconds
            , dscan = context.memory.dscan
            }
    then
        Just
            (describeBranch
                ("Refresh the Directional Scanner -- the last refresh went out at least "
                    ++ String.fromInt context.eventContext.botSettings.dscanIntervalSeconds
                    ++ "s ago."
                )
                (decideActionForCurrentStep (hotkeyEffects directionalScanHotkey))
            )

    else
        Nothing


{-| The one entry point the decision tree calls. `Nothing` unless
`wormhole = yes`, so an operator who never sets it gets exactly today's
behaviour -- no D-Scan refresh, no grid check, nothing changed.

Refreshing the scanner outranks the grid check on the same reading, the same
ordering `eve-online-gas-huffer` uses, so a reading that presses `V` does not
also judge a scan that is one keypress out of date.

Composed with this bot's own retreat rather than the huffer's cloak-and-bounce
escalation -- see this section's own opening doc comment -- `runAway` is what
a hostile on the grid triggers, exactly as a shield percentage below the
configured threshold does. That reuses the docking machinery, the unload
station/structure settings, and `runAway`'s own fallback to
`dockToRandomStationOrStructure` when none are configured, rather than
building a second way to leave.

**`aggressive = yes` replaces that `runAway` with `engageHostiles`**, the same
substitution `returnDronesAndRunAwayIfHitpointsAreTooLowOrWithoutDrones` makes
for its own shield-percentage trigger -- one setting, read in one place
(`engageHostiles` itself), rather than two copies of the same override. A
D-Scan-only sighting the ship has not met on grid yet still falls back to
`runAway`, since `engageHostiles` can only lock what is on the overview.

-}
wormholeSafetyStep : BotDecisionContext -> Maybe DecisionPathNode
wormholeSafetyStep context =
    if context.eventContext.botSettings.wormhole /= PromptParser.Yes then
        Nothing

    else
        case refreshTheDirectionalScanner context of
            Just refreshing ->
                Just refreshing

            Nothing ->
                let
                    evidence =
                        gridEvidenceFromContext context
                in
                if gridReadsClean (gridVerdict evidence) then
                    Nothing

                else
                    Just
                        (describeBranch
                            (describeGrid evidence)
                            (case engageHostiles context of
                                Just engaging ->
                                    engaging

                                Nothing ->
                                    describeBranch
                                        "This is a wormhole -- leave rather than keep mining."
                                        (runAway context)
                            )
                        )


goodStandingPatterns : List String
goodStandingPatterns =
    [ "good standing", "excellent standing", "is in your" ]


dockWhenDroneWindowInvisibleCount : Int
dockWhenDroneWindowInvisibleCount =
    4


{-| How many consecutive readings `dockedWithMiningHoldSelected` (and the fleet
hangar's own drag) may repeat the identical drag-and-drop before giving up.

20 is a multiple of the ordinary case rather than a guess against the incident:
a single stack drags in one or two readings when it lands at all, and a full
hold with several distinct ore stacks in it clears in well under this count
since every stack that actually drags resets the counter, one reading each. The
stuck run this bound answers reached 285 before an operator ended it by hand;
20 catches that within about a minute rather than nine.

-}
miningHoldDragGiveUpReadings : Int
miningHoldDragGiveUpReadings =
    20


{-| How many consecutive readings `ensureInfoPanelLocationInfoIsExpanded` (the
shared framework's own setup step, unchanged here) may go on reporting the
location info panel missing or collapsed -- and, for the collapsed case,
clicking to expand it -- before this bot stops waiting on it.

Confirmed live on 2026-09-06: that click can simply not land, the same way the
mining-hold drag above can. Unlike the drag, this step has **no** counter of
any kind today, in either of its two `Just` branches -- a collapsed panel that
does not respond to the click is retried forever, and the operator has no way
to tell from the log how long it has been going, only that it still is. The
underlying shared function is left as it is; it already tries the one thing
that can fix a collapsed panel, and adding a bound is a decision each app
using it can make about its own memory rather than a change every one of the
eight vendored copies has to take on together.

20 is picked for the same reason `miningHoldDragGiveUpReadings` is: several
times the one or two readings a landed click actually needs, and small next to
an incident with no bound to end it at all.

-}
infoPanelSetupGiveUpReadings : Int
infoPanelSetupGiveUpReadings =
    20


type alias BotSettings =
    { runAwayShieldHitpointsThresholdPercent : Int
    , unloadStationNames : List String
    , unloadStructureNames : List String
    , unloadFleetHangarPercent : Int
    , unloadMiningHoldPercent : Int
    , activateModulesAlways : List String
    , hideWhenNeutralInLocal : Maybe PromptParser.YesOrNo
    , dockWhenWithoutDrones : Maybe PromptParser.YesOrNo
    , repairBeforeUndocking : Maybe PromptParser.YesOrNo
    , targetingRange : Int
    , miningModuleRange : Int
    , botStepDelayMilliseconds : IntervalInt
    , selectInstancePilotName : Maybe String
    , includeAsteroidPatterns : List String
    , miningSites : List String
    , anomalyNamePatterns : List String
    , afterburnerModuleText : Maybe String
    , afterburnerDistanceThreshold : Maybe Int
    , compressFromMiningHold : PromptParser.YesOrNo
    , returnDronesWhenNoRatsVisible : PromptParser.YesOrNo
    , wormhole : PromptParser.YesOrNo
    , friendlyShipTag : Maybe String
    , dscanIntervalSeconds : Int
    , aggressive : PromptParser.YesOrNo
    }


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , timesUnloaded : Int
    , volumeUnloadedCubicMeters : Int
    , lastUsedCapacityInMiningHold : Maybe Int
    , miningHoldDragAttemptReadings : Int
    , infoPanelSetupAttemptReadings : Int
    , contextMenuLastDepth : Int
    , contextMenuStuckTicks : Int
    , shipModules : ShipModulesMemory
    , overviewWindows : OverviewWindowsMemory
    , lastReadingsInSpaceDronesWindowWasVisible : List Bool
    , lastTimeRatVisible : Maybe Int
    , dscan : DscanMemory
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias SelectedMineablesFromOverview =
    { clickableMineables : List OverviewWindowEntry
    , mineableMatchingSettings : Maybe ( OverviewWindowEntry, { closeEnoughForMining : Bool } )
    }


miningBotDecisionRoot : BotDecisionContext -> DecisionPathNode
miningBotDecisionRoot context =
    miningBotDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            (randomIntFromInterval context context.eventContext.botSettings.botStepDelayMilliseconds)


{-| A first outline of the decision tree for a mining bot came from <https://forum.botlab.org/t/how-to-automate-mining-asteroids-in-eve-online/628/109?u=viir>
-}
miningBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
miningBotDecisionRootBeforeApplyingSettings context =
    clearStrayContextMenu context
        |> Maybe.withDefault (miningBotDecisionRootAfterClearingStrayContextMenu context)


{-| Ahead of `generalSetupInUserInterface` rather than folded into it, and
checked regardless of docked-or-in-space state -- unlike `eve-online-saxrat`'s
own copy of this guard, which only runs from its in-space branch.

Confirmed live on 2026-09-06: the menu that stalled this bot was opened by
`dockToUnloadOre`'s solar-system-menu fallback while in space, was never
closed when that fallback gave way to something else, and was still open
several thousand readings later with the ship docked -- so a version of this
guard scoped to one docked-or-in-space state would have missed exactly the
incident it exists for.

-}
miningBotDecisionRootAfterClearingStrayContextMenu : BotDecisionContext -> DecisionPathNode
miningBotDecisionRootAfterClearingStrayContextMenu context =
    generalSetupInUserInterface
        context
        |> Maybe.withDefault
            (branchDependingOnDockedOrInSpace
                { ifDocked =
                    ensureMiningHoldIsSelectedInInventoryWindow
                        context.readingFromGameClient
                        (dockedWithMiningHoldSelected context)
                , ifSeeShipUI =
                    \shipUI ->
                        case returnDronesAndRunAwayIfHitpointsAreTooLowOrWithoutDrones context shipUI of
                            Just toRunAway ->
                                toRunAway

                            Nothing ->
                                case wormholeSafetyStep context of
                                    Just evading ->
                                        evading

                                    Nothing ->
                                        continueIfShouldHide
                                            { ifShouldHide =
                                                returnDronesToBay context
                                                    |> Maybe.withDefault (dockToUnloadOre context)
                                            }
                                            context
                                            |> Maybe.withDefault
                                                (ensureUserEnabledNameColumnInOverview
                                                    { ifEnabled =
                                                        ensureMiningHoldIsSelectedInInventoryWindow
                                                            context.readingFromGameClient
                                                            (inSpaceWithMiningHoldSelected context shipUI)
                                                    , ifDisabled =
                                                        describeBranch
                                                            "Please configure the overview to show objects names."
                                                            askForHelpToGetUnstuck
                                                    }
                                                    context.readingFromGameClient
                                                )
                }
                context.readingFromGameClient
            )


continueIfShouldHide : { ifShouldHide : DecisionPathNode } -> BotDecisionContext -> Maybe DecisionPathNode
continueIfShouldHide config context =
    case
        context.eventContext
            |> EveOnline.BotFramework.secondsToSessionEnd
            |> Maybe.andThen (nothingFromIntIfGreaterThan 200)
    of
        Just secondsToSessionEnd ->
            Just
                (describeBranch ("Session ends in " ++ (secondsToSessionEnd |> String.fromInt) ++ " seconds.")
                    config.ifShouldHide
                )

        Nothing ->
            case context |> quickMessageHasClusterShutdown of
                Just shutdownMessage ->
                    Just
                        (describeBranch
                            ("Quick Message: " ++ shutdownMessage)
                            config.ifShouldHide
                        )

                Nothing ->
                    if not (context |> shouldHideWhenNeutralInLocal) then
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


shouldHideWhenNeutralInLocal : BotDecisionContext -> Bool
shouldHideWhenNeutralInLocal context =
    case context.eventContext.botSettings.hideWhenNeutralInLocal of
        Just PromptParser.No ->
            False

        Just PromptParser.Yes ->
            True

        Nothing ->
            (context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .securityStatusPercent
                |> Maybe.withDefault 0
            )
                < 50


shouldDockWhenWithoutDrones : BotDecisionContext -> Bool
shouldDockWhenWithoutDrones context =
    context.eventContext.botSettings.dockWhenWithoutDrones == Just PromptParser.Yes


shouldRepairBeforeUndocking : BotDecisionContext -> Bool
shouldRepairBeforeUndocking context =
    context.eventContext.botSettings.repairBeforeUndocking == Just PromptParser.Yes


{-| The `aggressive` clause below is the one place this function's own
`runAway` gets replaced -- see `engageHostiles`'s own doc comment for why a
reading with nothing on the overview to fight still falls back to running
away rather than sitting still.

The "return drones" middle tier is skipped outright under `aggressive`,
rather than fought over: recalling drones while the setting wants them out
fighting would be two controllers for one drone bay, so an aggressive ship
simply falls through this tier and leaves the drones exactly where the
ordinary mining-time launch/return logic (`launchOrReturnDronesAccordingToSettings`)
already puts them.

-}
returnDronesAndRunAwayIfHitpointsAreTooLowOrWithoutDrones : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> Maybe DecisionPathNode
returnDronesAndRunAwayIfHitpointsAreTooLowOrWithoutDrones context shipUI =
    let
        returnDronesShieldHitpointsThresholdPercent =
            context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent + 5

        runAwayWithDescription =
            describeBranch
                ("Shield hitpoints are at " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%. Run away.")
                (runAway context)
    in
    if shipUI.hitpointsPercent.shield < context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent then
        Just
            (case engageHostiles context of
                Just engaging ->
                    describeBranch
                        ("Shield hitpoints are at " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%.")
                        engaging

                Nothing ->
                    runAwayWithDescription
            )

    else if
        not (aggressiveIsEnabled context)
            && (shipUI.hitpointsPercent.shield < returnDronesShieldHitpointsThresholdPercent)
    then
        returnDronesToBay context
            |> Maybe.map
                (describeBranch
                    ("Shield hitpoints are below " ++ (returnDronesShieldHitpointsThresholdPercent |> String.fromInt) ++ "%. Return drones.")
                )
            |> Maybe.withDefault runAwayWithDescription
            |> Just

    else if
        (context |> shouldDockWhenWithoutDrones)
            && shouldDockBecauseDroneWindowWasInvisibleTooLong context.memory
    then
        Just
            (describeBranch "I don't see the drone window, are we out of drones? configured to run away when without a drone. Run to the station!" (dockToUnloadOre context))

    else
        Nothing


{-| Ported from `eve-online-saxrat`, which has carried this since it started
losing whole sessions to exactly this shape: a context menu opened by one
cascade, abandoned before it closed, sitting open indefinitely because nothing
here ever checked for one outside of a cascade actively driving it.

**Cascade depth, not menu presence**, is what is counted. Context menus nest --
descending a level adds an entry to `readingFromGameClient.contextMenus` rather
than replacing it -- so `BotMemory.contextMenuStuckTicks` only increments when
the menu count has stayed the same (or dropped without reaching zero) since the
last reading; any tick that goes deeper resets it. A cascade that keeps
advancing, however slowly, never trips this; one stuck at the same depth does
within a few readings.

**12 readings, not saxrat's original 3**, carried over rather than re-derived:
this bot's own anomaly-warp cascade goes through the same
`useContextMenuCascadeOnListSurroundingsButton` -> `useContextMenuCascadeWithCustomConfig`
machinery saxrat's does, with the same 8-reading lookback before a stuck-but-open
menu is discarded and reopened on its own. 12 clears that with the same margin
saxrat measured, so a cascade that is about to recover on its own still gets the
chance to.

**No `ammoSwapOwnsTheMenu` clause here**, unlike saxrat's copy -- this bot has no
ammo swap, so there is nothing else here that legitimately holds a weapon's
context menu open across several readings for the swap's own reasons.

`Nothing` rather than an alarm, deliberately: the menu stays on the screen and
every branch below now works around it, which is worse than a cleared menu and
incomparably better than nothing running at all.

-}
clearStrayContextMenu : BotDecisionContext -> Maybe DecisionPathNode
clearStrayContextMenu context =
    if
        strayContextMenuIsStray
            { stuckTicks = context.memory.contextMenuStuckTicks }
    then
        Just
            (case emptyPointBesideTheInfoPanel context.readingFromGameClient of
                Just location ->
                    describeBranch
                        "A context menu has sat at the same depth for several ticks in a row without advancing to a deeper submenu -- likely a stray menu from an abandoned cascade or a misclick. Clear it (left click beside the info panel)."
                        (decideActionForCurrentStep
                            (EffectOnWindow.effectsMouseClickAtLocation
                                MouseButtonLeft
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


{-| Everything the stray-menu verdict turns on, as a record rather than the
whole context so a case can execute the rule directly.
-}
type alias StrayContextMenuCase =
    { stuckTicks : Int
    }


strayContextMenuIsStray : StrayContextMenuCase -> Bool
strayContextMenuIsStray strayCase =
    (strayContextMenuStuckTicksThreshold <= strayCase.stuckTicks)
        && (strayCase.stuckTicks < strayContextMenuGiveUpTicks)


strayContextMenuStuckTicksThreshold : Int
strayContextMenuStuckTicksThreshold =
    12


{-| How long the dismissal gets before the bot works around the menu instead,
written as a multiple of the threshold that arms it so the two cannot drift
apart. Twenty attempts is far past anything a working dismissal needs -- one
click ought to clear it -- and far short of a session.
-}
strayContextMenuGiveUpTicks : Int
strayContextMenuGiveUpTicks =
    strayContextMenuStuckTicksThreshold * 20


{-| How far right of the info panel's own edge to click, in the client's
coordinates. Wide enough to clear the panel's border and any hover affordance,
narrow enough that it stays in the gap rather than reaching whatever is laid
out further right.
-}
strayMenuClearGapFromInfoPanel : Int
strayMenuClearGapFromInfoPanel =
    80


{-| A point beside the info panel, for dismissing a stray context menu.

Escape does not reliably do this job (confirmed live on saxrat, see that app's
own copy of this function), and can open the client's own settings menu
instead -- so a computed point is the rule and Escape is the fallback rather
than the other way around.

The point is derived from the info panel's own parsed region every reading
rather than a remembered coordinate, so it moves with the layout the way every
other self-calibrated number here does, and it is checked against every open
context menu before being used: the point beside the panel is where the last
dismissal's click went, and the client opens a context menu at the cursor, so
the reading after a click lands the same point on a menu entry rather than on
empty canvas. Stepping below every open menu's lowest edge is what keeps a
retried dismissal a dismissal rather than a second stray menu.

`Nothing` when the info panel is not in the reading, because then there is no
anchor and no point known to be empty; the caller falls back to Escape there.

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


generalSetupInUserInterface : BotDecisionContext -> Maybe DecisionPathNode
generalSetupInUserInterface context =
    [ closeMessageBox
    , ensureInfoPanelLocationInfoIsExpandedOrGiveUp context.memory.infoPanelSetupAttemptReadings
    , ensureOverviewsSorted
        { sortColumnName = "Distance", skipSortingWhenNotScrollable = True }
        context.memory.overviewWindows
        >> List.filterMap
            (\( _, ( description, maybeAction ) ) ->
                maybeAction |> Maybe.map (describeBranch description)
            )
        >> List.head
    ]
        |> List.filterMap ((|>) context.readingFromGameClient)
        |> List.head


{-| `ensureInfoPanelLocationInfoIsExpanded` with the give-up it does not have.
See `infoPanelSetupGiveUpReadings` for why this bound lives here rather than in
the shared function itself.
-}
ensureInfoPanelLocationInfoIsExpandedOrGiveUp : Int -> ReadingFromGameClient -> Maybe DecisionPathNode
ensureInfoPanelLocationInfoIsExpandedOrGiveUp attemptReadingsSoFar readingFromGameClient =
    if infoPanelSetupGiveUpReadings <= attemptReadingsSoFar then
        Just
            (describeBranch
                ("The location info panel has been missing, or collapsed and not responding to a click to expand it, for "
                    ++ String.fromInt attemptReadingsSoFar
                    ++ " readings in a row. Clicking it again cannot be what is missing here."
                )
                askForHelpToGetUnstuck
            )

    else
        ensureInfoPanelLocationInfoIsExpanded readingFromGameClient


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


dockedWithMiningHoldSelected : BotDecisionContext -> EveOnline.ParseUserInterface.InventoryWindow -> DecisionPathNode
dockedWithMiningHoldSelected context inventoryWindowWithMiningHoldSelected =
    case inventoryWindowWithMiningHoldSelected |> itemHangarFromInventoryWindow |> Maybe.map .uiNode of
        Nothing ->
            describeBranch "I do not see the item hangar in the inventory." askForHelpToGetUnstuck

        Just itemHangar ->
            case inventoryWindowWithMiningHoldSelected |> selectedContainerFirstItemFromInventoryWindow of
                Nothing ->
                    describeBranch "I see no item in the mining hold. Checking if we should repaired ship and undock."
                        (if
                            (context |> shouldDockWhenWithoutDrones)
                                && shouldDockBecauseDroneWindowWasInvisibleTooLong context.memory
                         then
                            describeBranch "Stay docked because I didn't see the drone window. Are we out of drones?"
                                askForHelpToGetUnstuck

                         else
                            continueIfShouldHide
                                { ifShouldHide =
                                    describeBranch "Stay docked because we should hide." waitForProgressInGame
                                }
                                context
                                |> Maybe.withDefault
                                    (checkAndRepairBeforeUndockingUsingContextMenu context inventoryWindowWithMiningHoldSelected
                                        |> Maybe.withDefault
                                            (undockUsingStationWindow context
                                                { ifCannotReachButton =
                                                    describeBranch "Undock using context menu"
                                                        (undockUsingContextMenu context
                                                            { inventoryWindowWithMiningHoldSelected = inventoryWindowWithMiningHoldSelected }
                                                        )
                                                }
                                            )
                                    )
                        )

                Just itemInInventory ->
                    dragItemOutOfMiningHoldOrGiveUp context
                        { destinationName = "item hangar"
                        , dragToLocation = itemHangar.totalDisplayRegionVisible |> centerFromDisplayRegion
                        }
                        itemInInventory


inSpaceWithMiningHoldSelectedWithFleetHangar : BotDecisionContext -> EveOnline.ParseUserInterface.InventoryWindow -> DecisionPathNode
inSpaceWithMiningHoldSelectedWithFleetHangar context inventoryWindowWithMiningHoldSelected =
    case
        inventoryWindowWithMiningHoldSelected |> fleetHangarFromInventoryWindow |> Maybe.map .uiNode
    of
        Nothing ->
            describeBranch "I do not see the fleet hangar in the inventory." askForHelpToGetUnstuck

        Just fleetHangarFromInventory ->
            case inventoryWindowWithMiningHoldSelected |> selectedContainerFirstItemFromInventoryWindow of
                Nothing ->
                    describeBranch "I see no item in the mining hold. Click the tree entry representing the fleet Hangar."
                        (mouseClickOnUIElement MouseButtonLeft fleetHangarFromInventory
                            |> Result.Extra.unpack
                                (always (describeBranch "Failed to click" askForHelpToGetUnstuck))
                                decideActionForCurrentStep
                        )

                Just itemInInventory ->
                    dragItemOutOfMiningHoldOrGiveUp context
                        { destinationName = "fleet hangar"
                        , dragToLocation = fleetHangarFromInventory.totalDisplayRegionVisible |> centerFromDisplayRegion
                        }
                        itemInInventory


{-| The one drag-and-drop both callers above end in, with the give-up neither
of them had. Confirmed live: this drag can simply not land, with nothing else
in the reading -- no dialog, no message box -- to say so, and the branch it sat
in re-issued the identical gesture every reading for as long as an item
answered `Just`. `miningHoldDragAttemptReadings` (computed in
`updateMemoryForNewReadingFromGame`, the only place that can write memory) is
what notices: it counts consecutive readings the hold still holds an item and
its capacity gauge has not moved, and resets the moment either changes -- so a
hold with several distinct ore stacks in it still clears well under the bound,
since every stack that actually drags is progress by that measure.

Past `miningHoldDragGiveUpReadings` this stops dispatching the same input and
says so instead, naming the destination and the count, and asks for help
rather than trying something else the client has already shown it eleven or
more times in a row that it will not take.

-}
dragItemOutOfMiningHoldOrGiveUp :
    BotDecisionContext
    -> { destinationName : String, dragToLocation : EffectOnWindow.Location2d }
    -> UIElement
    -> DecisionPathNode
dragItemOutOfMiningHoldOrGiveUp context { destinationName, dragToLocation } itemInInventory =
    if miningHoldDragGiveUpReadings <= context.memory.miningHoldDragAttemptReadings then
        describeBranch
            ("An item has sat in the mining hold through "
                ++ (context.memory.miningHoldDragAttemptReadings |> String.fromInt)
                ++ " readings of dragging it to the "
                ++ destinationName
                ++ ", and the capacity gauge has not moved once in that time. The drag is not landing, and repeating the identical gesture again cannot be what fixes it."
            )
            askForHelpToGetUnstuck

    else
        describeBranch ("I see at least one item in the mining hold. Move this to the " ++ destinationName ++ ".")
            (describeBranch "Drag and drop."
                (decideActionForCurrentStep
                    (EffectOnWindow.effectsForDragAndDrop
                        { startLocation = itemInInventory.totalDisplayRegionVisible |> centerFromDisplayRegion
                        , mouseButton = MouseButtonLeft
                        , waypointsPositionsInBetween = []
                        , endLocation = dragToLocation
                        }
                    )
                )
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


undockUsingContextMenu :
    BotDecisionContext
    -> { inventoryWindowWithMiningHoldSelected : EveOnline.ParseUserInterface.InventoryWindow }
    -> DecisionPathNode
undockUsingContextMenu context { inventoryWindowWithMiningHoldSelected } =
    case inventoryWindowWithMiningHoldSelected |> activeShipTreeEntryFromInventoryWindow of
        Nothing ->
            describeBranch "I do not see the active ship in the inventory window." askForHelpToGetUnstuck

        Just activeShipEntry ->
            useContextMenuCascade
                ( "active ship", activeShipEntry.uiNode )
                (useMenuEntryWithTextContainingFirstOf [ "undock from station" ] menuCascadeCompleted)
                context


checkAndRepairBeforeUndockingUsingContextMenu : BotDecisionContext -> EveOnline.ParseUserInterface.InventoryWindow -> Maybe DecisionPathNode
checkAndRepairBeforeUndockingUsingContextMenu context inventoryWindowWithMiningHoldSelected =
    if not (context |> shouldRepairBeforeUndocking) then
        Nothing

    else
        case context.readingFromGameClient.repairShopWindow of
            Nothing ->
                case inventoryWindowWithMiningHoldSelected |> activeShipTreeEntryFromInventoryWindow of
                    Nothing ->
                        Just (describeBranch "I do not see the active ship in the inventory window." askForHelpToGetUnstuck)

                    Just activeShipEntry ->
                        Just
                            (useContextMenuCascade
                                ( "active ship", activeShipEntry.uiNode )
                                (useMenuEntryWithTextContaining "get repair quote" menuCascadeCompleted)
                                context
                            )

            Just repairShopWindow ->
                let
                    buttonUsed =
                        .mainText
                            >> Maybe.map
                                (String.trim
                                    >> String.toLower
                                    >> (\buttonText -> [ "repair all" ] |> List.member buttonText)
                                )
                            >> Maybe.withDefault False
                in
                case repairShopWindow.items |> List.head of
                    Nothing ->
                        Nothing

                    Just itemToRepair ->
                        Just
                            (describeBranch "There is at least one item to repair."
                                (case mouseClickOnUIElement MouseButtonLeft itemToRepair of
                                    Err _ ->
                                        describeBranch "Failed to click" askForHelpToGetUnstuck

                                    Ok clickItemToRepair ->
                                        case repairShopWindow.buttons |> List.filter buttonUsed |> List.head of
                                            Just btnRepairAll ->
                                                describeBranch "I see the repair all button, I'm going to click it."
                                                    (case mouseClickOnUIElement MouseButtonLeft btnRepairAll.uiNode of
                                                        Err _ ->
                                                            describeBranch "Failed to click" askForHelpToGetUnstuck

                                                        Ok clickButtonToRepair ->
                                                            decideActionForCurrentStep
                                                                ([ clickItemToRepair
                                                                 , clickButtonToRepair
                                                                 ]
                                                                    |> List.concat
                                                                )
                                                    )

                                            Nothing ->
                                                describeBranch
                                                    "I do not see the repair all button."
                                                    askForHelpToGetUnstuck
                                )
                            )


inSpaceWithMiningHoldSelected :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> DecisionPathNode
inSpaceWithMiningHoldSelected context shipUI inventoryWindowWithMiningHoldSelected =
    if shipUIIndicatesShipIsWarpingOrJumping shipUI then
        describeBranch "I see we are warping."
            ([ returnDronesToBay context
             , readShipUIModuleButtonTooltips context
             ]
                |> List.filterMap identity
                |> List.head
                |> Maybe.withDefault waitForProgressInGame
            )

    else
        case context |> knownModulesToActivateAlways |> List.filter (Tuple.second >> .isActive >> Maybe.withDefault False >> not) |> List.head of
            Just ( inactiveModuleMatchingText, inactiveModule ) ->
                describeBranch ("I see inactive module '" ++ inactiveModuleMatchingText ++ "' to activate always. Activate it.")
                    (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)

            Nothing ->
                case
                    if context.eventContext.botSettings.activateModulesAlways == [] then
                        Nothing

                    else
                        readModuleButtonTooltipForActivateAlwaysDiscovery context
                of
                    Just discoverTooltip ->
                        discoverTooltip

                    Nothing ->
                        modulesToActivateAlwaysActivated context inventoryWindowWithMiningHoldSelected


modulesToActivateAlwaysActivated :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> DecisionPathNode
modulesToActivateAlwaysActivated context inventoryWindowWithMiningHoldSelected =
    case inventoryWindowWithMiningHoldSelected |> capacityGaugeUsedPercent of
        Nothing ->
            describeBranch "I do not see the mining hold capacity gauge." askForHelpToGetUnstuck

        Just fillPercent ->
            let
                describeThresholdToUnload =
                    (context.eventContext.botSettings.unloadMiningHoldPercent |> String.fromInt) ++ "%"

                describeThresholdToUnloadFleetHangar =
                    (context.eventContext.botSettings.unloadFleetHangarPercent |> String.fromInt) ++ "%"

                knownMiningModules =
                    knownMiningModulesFromContext context
            in
            if context.eventContext.botSettings.unloadMiningHoldPercent <= fillPercent then
                describeBranch ("The mining hold is filled at least " ++ describeThresholdToUnload ++ ". Unload the ore.")
                    (returnDronesToBay context
                        |> Maybe.withDefault (dockToUnloadOre context)
                    )

            else if context.eventContext.botSettings.unloadFleetHangarPercent > 0 && context.eventContext.botSettings.unloadFleetHangarPercent <= fillPercent then
                describeBranch ("The mining hold is filled at least " ++ describeThresholdToUnloadFleetHangar ++ ". Unload the ore on fleet hangar.")
                    (ensureMiningHoldIsSelectedInInventoryWindow
                        context.readingFromGameClient
                        (inSpaceWithMiningHoldSelectedWithFleetHangar context)
                    )

            else
                case selectMineablesFromOverview context of
                    Err err ->
                        describeBranch ("Failed to select mineables from overview: " ++ err)
                            (dockToUnloadOre context)

                    Ok selectedMineables ->
                        describeBranch
                            ("The mining hold is not yet filled "
                                ++ describeThresholdToUnload
                                ++ ". Get more ore."
                            )
                            (case
                                context.readingFromGameClient.targets
                                    |> List.sortBy
                                        (\target ->
                                            if target.isActiveTarget then
                                                0

                                            else
                                                1
                                        )
                                    |> List.head
                             of
                                Nothing ->
                                    describeBranch "I see no locked target."
                                        (travelToMiningSiteAndLaunchDronesAndTargetMineable selectedMineables context)

                                Just nextTarget ->
                                    case unlockTargetsNotForMining context selectedMineables of
                                        Just unlockNonMiningTargetAction ->
                                            unlockNonMiningTargetAction

                                        Nothing ->
                                            describeBranch "I see a locked target."
                                                (ensureTargetIsInMiningRange
                                                    context
                                                    nextTarget
                                                    { whenInRange =
                                                        if shipManeuverIsApproaching context.readingFromGameClient then
                                                            describeBranch "Minable asteroid is close enough to stop the ship"
                                                                ([ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL
                                                                 , EffectOnWindow.KeyDown EffectOnWindow.vkey_SPACE
                                                                 , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL
                                                                 , EffectOnWindow.KeyUp EffectOnWindow.vkey_SPACE
                                                                 ]
                                                                    |> decideActionForCurrentStep
                                                                )

                                                        else
                                                            case
                                                                knownMiningModules
                                                                    |> List.filter (.isActive >> Maybe.withDefault False >> not)
                                                                    |> List.head
                                                            of
                                                                Nothing ->
                                                                    describeBranch
                                                                        (if knownMiningModules == [] then
                                                                            "Found no mining modules so far."

                                                                         else
                                                                            "All known mining modules found so far are active."
                                                                        )
                                                                        (case readShipUIModuleButtonTooltips context of
                                                                            Just readTooltips ->
                                                                                readTooltips

                                                                            Nothing ->
                                                                                case deactivateAfterburner context of
                                                                                    Just deactivateAfterburnerAction ->
                                                                                        describeBranch "Deactivate afterburner."
                                                                                            deactivateAfterburnerAction

                                                                                    Nothing ->
                                                                                        compressAndStackAllIfConditionsMet
                                                                                            context
                                                                                            inventoryWindowWithMiningHoldSelected
                                                                                            { miningHoldFillPercent = fillPercent
                                                                                            , ifNothingToCompress = waitForProgressInGame
                                                                                            }
                                                                        )

                                                                Just inactiveModule ->
                                                                    describeBranch "I see an inactive mining module. Activate it."
                                                                        (clickModuleButtonButWaitIfClickedInPreviousStep
                                                                            context
                                                                            inactiveModule
                                                                        )
                                                    }
                                                )
                            )


ensureTargetIsInMiningRange :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.Target
    -> { whenInRange : DecisionPathNode }
    -> DecisionPathNode
ensureTargetIsInMiningRange context target { whenInRange } =
    case readDistanceOfTargetInMeters target of
        Err err ->
            describeBranch ("Failed to read distance of target: " ++ err)
                askForHelpToGetUnstuck

        Ok distanceMeters ->
            if distanceMeters <= context.eventContext.botSettings.miningModuleRange then
                whenInRange

            else
                let
                    approachCommand =
                        useContextMenuCascade
                            ( "targeted object", target.uiNode )
                            (useMenuEntryWithTextContaining "approach" menuCascadeCompleted)
                            context
                in
                describeBranch ("Target is " ++ String.fromInt distanceMeters ++ " meters away. Approach it.")
                    (if shipManeuverIsApproaching context.readingFromGameClient then
                        case activateAfterburnerIfNeeded context distanceMeters of
                            Just afterburnerActivation ->
                                describeBranch "Afterburner is not active. Activate it."
                                    afterburnerActivation

                            Nothing ->
                                approachCommand

                     else
                        approachCommand
                    )


deactivateAfterburner : BotDecisionContext -> Maybe DecisionPathNode
deactivateAfterburner context =
    let
        afterburnerModules =
            knownAfterburnerModulesFromContext context

        activeAfterburnerModules =
            afterburnerModules
                |> List.filter
                    (\moduleButton ->
                        case moduleButton.isActive of
                            Nothing ->
                                False

                            Just isActive ->
                                isActive
                    )
    in
    case activeAfterburnerModules of
        [] ->
            Nothing

        activeModule :: _ ->
            Just (clickModuleButtonButWaitIfClickedInPreviousStep context activeModule)


activateAfterburnerIfNeeded : BotDecisionContext -> Int -> Maybe DecisionPathNode
activateAfterburnerIfNeeded context distance =
    let
        afterburnerModules =
            knownAfterburnerModulesFromContext context

        isActive m =
            m.isActive |> Maybe.withDefault False
    in
    case context.eventContext.botSettings.afterburnerDistanceThreshold of
        Just threshold ->
            if distance > threshold then
                case List.filter (not << isActive) afterburnerModules |> List.head of
                    Just inactiveModule ->
                        Just
                            (describeBranch
                                ("Distance to target is "
                                    ++ String.fromInt distance
                                    ++ "m, above "
                                    ++ String.fromInt threshold
                                    ++ "m. Activating afterburner."
                                )
                                (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)
                            )

                    Nothing ->
                        Nothing

            else
                Nothing

        Nothing ->
            Nothing


readDistanceOfTargetInMeters : EveOnline.ParseUserInterface.Target -> Result String Int
readDistanceOfTargetInMeters target =
    {- Example seen in session-recording-2023-04-22T21-26-45.zip:
       0 = "<center>Asteroid (Golden"
       1 = "<center>Omber)"
       2 = "<center>23 km"
    -}
    target.textsTopToBottom
        |> List.reverse
        |> List.concatMap (String.split ">")
        |> List.filterMap (EveOnline.ParseUserInterface.parseOverviewEntryDistanceInMetersFromText >> Result.toMaybe)
        |> List.head
        |> Maybe.map Ok
        |> Maybe.withDefault
            (Err
                ("Found no matching text in "
                    ++ String.fromInt (List.length target.textsTopToBottom)
                    ++ " lines ("
                    ++ String.join ", " target.textsTopToBottom
                    ++ ")."
                )
            )


unlockTargetsNotForMining : BotDecisionContext -> SelectedMineablesFromOverview -> Maybe DecisionPathNode
unlockTargetsNotForMining context selectedMineables =
    {-
       Observation session-recording-2025-11-21T11-27-31:
       Locked target does not contain text 'asteroid' anymore.
       ---
       Example of observed label on locked target:
       '<center>Scordite II-Grade <center>2,484 m'
       ---
       <https://forum.botlab.org/t/eve-mining-bot-23-02-issue-locks-an-asteroid-then-unlocks-it-and-repeats-this-over-and-over/5278>
    -}
    let
        mineableLabels : Set.Set String
        mineableLabels =
            selectedMineables.clickableMineables
                |> List.concatMap
                    (\overviewEntry ->
                        case overviewEntry.objectName of
                            Nothing ->
                                []

                            Just name ->
                                String.words name
                    )
                |> Set.fromList

        shouldUnlockTarget : EveOnline.ParseUserInterface.Target -> Bool
        shouldUnlockTarget target =
            let
                textItems =
                    target.textsTopToBottom
                        |> List.concatMap
                            (\targetString ->
                                {-
                                   String.words  "<center>Plagioclase" will return ["<center>Plagioclase"]
                                   ---
                                   TODO: Consider stripping XML tags more generally here?
                                -}
                                String.words (String.replace "<center>" "" targetString)
                            )

                looksLikeMineable =
                    List.any
                        (\word -> Set.member word mineableLabels)
                        textItems
            in
            not looksLikeMineable
    in
    case
        Common.listFind
            shouldUnlockTarget
            context.readingFromGameClient.targets
    of
        Nothing ->
            Nothing

        Just targetToUnlock ->
            Just
                (describeBranch
                    ("I see a target not for mining: '"
                        ++ String.join " " targetToUnlock.textsTopToBottom
                        ++ "'. Unlock this target."
                    )
                    (useContextMenuCascade
                        ( "target", targetToUnlock.barAndImageCont |> Maybe.withDefault targetToUnlock.uiNode )
                        (useMenuEntryWithTextContaining "unlock" menuCascadeCompleted)
                        context
                    )
                )


travelToMiningSiteAndLaunchDronesAndTargetMineable : SelectedMineablesFromOverview -> BotDecisionContext -> DecisionPathNode
travelToMiningSiteAndLaunchDronesAndTargetMineable selectedMineables context =
    let
        continueWithWarpToMiningSite =
            returnDronesToBay context
                |> Maybe.withDefault (warpToMiningSite context)
    in
    case selectedMineables.mineableMatchingSettings of
        Nothing ->
            case selectedMineables.clickableMineables of
                [] ->
                    describeBranch "I see no clickable mineable in the overview. Warp to mining site."
                        continueWithWarpToMiningSite

                clickableMineables ->
                    describeBranch
                        ("I see "
                            ++ String.fromInt (List.length clickableMineables)
                            ++ " clickable mineables in the overview. But none of these matches the filter from settings. Warp to other mining site."
                        )
                        continueWithWarpToMiningSite

        Just ( mineableInOverview, _ ) ->
            describeBranch ("Choosing mineable '" ++ (mineableInOverview.objectName |> Maybe.withDefault "Nothing") ++ "'")
                (warpToOverviewEntryIfFarEnough context mineableInOverview
                    |> Maybe.withDefault
                        (launchOrReturnDronesAccordingToSettings context
                            |> Maybe.withDefault
                                (lockTargetFromOverviewEntryAndEnsureIsInRange
                                    context
                                    (min context.eventContext.botSettings.targetingRange
                                        context.eventContext.botSettings.miningModuleRange
                                    )
                                    mineableInOverview
                                )
                        )
                )


selectMineablesFromOverview : BotDecisionContext -> Result String SelectedMineablesFromOverview
selectMineablesFromOverview context =
    let
        -- With more than one overview window open, the same physical object
        -- is represented once per window, and the two representations do not
        -- always agree: a narrower window can truncate a cell's text, and
        -- which copy `List.head` below lands on then depends on which window
        -- happened to render first. Confirmed live: the bot alternated every
        -- reading between "approach this rock" and "none of these match,
        -- warp elsewhere" for the *same* asteroid, because one overview
        -- window's copy of its row matched the asteroid-pattern setting and
        -- the other's did not. Matching is therefore asked of every
        -- representation sharing an identity, not just the specific one a
        -- click would land on -- a duplicate that reads the pattern text
        -- clearly rescues a duplicate that does not.
        allMineables =
            overviewWindowEntriesRepresentingMineable context.readingFromGameClient

        clickableMineables =
            clickableMineablesFromOverviewWindow context.readingFromGameClient

        continueWithMineableMatchingSettings mineableMatchingSettings =
            Ok
                { clickableMineables = clickableMineables
                , mineableMatchingSettings = mineableMatchingSettings
                }
    in
    clickableMineables
        |> List.filter (mineableOverviewEntryMatchesSettingsConsideringDuplicates context.eventContext.botSettings allMineables)
        |> List.sortBy (.uiNode >> .totalDisplayRegion >> .y)
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 9999999)
        |> List.head
        |> Maybe.map
            (\overviewEntry ->
                overviewEntry.objectDistanceInMeters
                    |> Result.mapError
                        ((++)
                            ("Failed to read the distance on overview entry "
                                ++ (overviewEntry.objectName |> Maybe.withDefault "")
                                ++ ": "
                            )
                        )
                    |> Result.andThen
                        (\distanceInMeters ->
                            ( overviewEntry
                            , { closeEnoughForMining =
                                    distanceInMeters
                                        <= min context.eventContext.botSettings.targetingRange
                                            context.eventContext.botSettings.miningModuleRange
                              }
                            )
                                |> Just
                                |> continueWithMineableMatchingSettings
                        )
            )
        |> Maybe.withDefault (continueWithMineableMatchingSettings Nothing)


warpToOverviewEntryIfFarEnough : BotDecisionContext -> OverviewWindowEntry -> Maybe DecisionPathNode
warpToOverviewEntryIfFarEnough context destinationOverviewEntry =
    case destinationOverviewEntry.objectDistanceInMeters of
        Ok distanceInMeters ->
            if distanceInMeters <= 150000 then
                Nothing

            else
                Just
                    (describeBranch "Far enough to use Warp"
                        (returnDronesToBay context
                            |> Maybe.withDefault
                                (useContextMenuCascadeOnOverviewEntry
                                    (useMenuEntryWithTextContaining "Warp to Within"
                                        (useMenuEntryWithTextContaining "Within 0 m" menuCascadeCompleted)
                                    )
                                    destinationOverviewEntry
                                    context
                                )
                        )
                    )

        Err error ->
            Just (describeBranch ("Failed to read the distance: " ++ error) askForHelpToGetUnstuck)


ensureMiningHoldIsSelectedInInventoryWindow : ReadingFromGameClient -> (EveOnline.ParseUserInterface.InventoryWindow -> DecisionPathNode) -> DecisionPathNode
ensureMiningHoldIsSelectedInInventoryWindow readingFromGameClient continueWithInventoryWindow =
    case readingFromGameClient |> inventoryWindowWithMiningHoldSelectedFromGameClient of
        Just inventoryWindow ->
            continueWithInventoryWindow inventoryWindow

        Nothing ->
            case readingFromGameClient.inventoryWindows |> List.head of
                Nothing ->
                    case findInventoryButtonInNeocom readingFromGameClient of
                        Just inventoryButton ->
                            describeBranch "Opening the inventory window."
                                (case mouseClickOnUIElement MouseButtonLeft inventoryButton of
                                    Err _ ->
                                        describeBranch "Failed to click inventory button" askForHelpToGetUnstuck

                                    Ok clickAction ->
                                        decideActionForCurrentStep clickAction
                                )

                        Nothing ->
                            describeBranch "Could not find the inventory button in the Neocom." askForHelpToGetUnstuck

                Just inventoryWindow ->
                    describeBranch
                        "mining hold is not selected. Select the mining hold."
                        (case inventoryWindow |> activeShipTreeEntryFromInventoryWindow of
                            Nothing ->
                                describeBranch "I do not see the active ship in the inventory." askForHelpToGetUnstuck

                            Just activeShipTreeEntry ->
                                let
                                    maybeMiningHoldTreeEntry =
                                        activeShipTreeEntry
                                            |> miningHoldFromInventoryWindowShipEntry
                                in
                                case maybeMiningHoldTreeEntry of
                                    Nothing ->
                                        describeBranch "I do not see the mining hold under the active ship in the inventory."
                                            (case activeShipTreeEntry.toggleBtn of
                                                Nothing ->
                                                    describeBranch "I do not see the toggle button to expand the active ship tree entry."
                                                        askForHelpToGetUnstuck

                                                Just toggleBtn ->
                                                    describeBranch "Click the toggle button to expand."
                                                        (mouseClickOnUIElement MouseButtonLeft toggleBtn
                                                            |> Result.Extra.unpack
                                                                (always (describeBranch "Failed to click" askForHelpToGetUnstuck))
                                                                decideActionForCurrentStep
                                                        )
                                            )

                                    Just miningHoldTreeEntry ->
                                        describeBranch "Click the tree entry representing the mining hold."
                                            (mouseClickOnUIElement MouseButtonLeft miningHoldTreeEntry.uiNode
                                                |> Result.Extra.unpack
                                                    (always (describeBranch "Failed to click" askForHelpToGetUnstuck))
                                                    decideActionForCurrentStep
                                            )
                        )


{-| Returns the inventory button in the neocom (Ready to be clicked on)
-}
findInventoryButtonInNeocom : ReadingFromGameClient -> Maybe UIElement
findInventoryButtonInNeocom readingFromGameClient =
    case readingFromGameClient.neocom of
        Nothing ->
            Nothing

        Just insideNeoCom ->
            insideNeoCom.inventoryButton


lockTargetFromOverviewEntryAndEnsureIsInRange : BotDecisionContext -> Int -> OverviewWindowEntry -> DecisionPathNode
lockTargetFromOverviewEntryAndEnsureIsInRange context rangeInMeters overviewEntry =
    case overviewEntry.objectDistanceInMeters of
        Ok distanceInMeters ->
            if distanceInMeters <= rangeInMeters then
                if overviewEntry.commonIndications.targetedByMe || overviewEntry.commonIndications.targeting then
                    describeBranch "Locking target is in progress, wait for completion." waitForProgressInGame

                else
                    describeBranch "Object is in range. Lock target."
                        (lockTargetFromOverviewEntry overviewEntry context)

            else
                describeBranch ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " meters away). Approach.")
                    (if shipManeuverIsApproaching context.readingFromGameClient then
                        describeBranch "I see we already approach." waitForProgressInGame

                     else
                        useContextMenuCascadeOnOverviewEntry
                            (useMenuEntryWithTextContaining "approach" menuCascadeCompleted)
                            overviewEntry
                            context
                    )

        Err error ->
            describeBranch ("Failed to read the distance: " ++ error) askForHelpToGetUnstuck


lockTargetFromOverviewEntry : OverviewWindowEntry -> BotDecisionContext -> DecisionPathNode
lockTargetFromOverviewEntry overviewEntry context =
    describeBranch
        ("Lock target from overview entry '"
            ++ (overviewEntry.objectName |> Maybe.withDefault "")
            ++ "' ("
            ++ (overviewEntry.objectDistance |> Maybe.withDefault "")
            ++ ")"
        )
        (useContextMenuCascadeOnOverviewEntry
            (useMenuEntryWithTextEqual "Lock target" menuCascadeCompleted)
            overviewEntry
            context
        )


dockToStationOrStructureWithMatchingName :
    { namesFromSettingOrInfoPanel : List String }
    -> BotDecisionContext
    ->
        { viaLocationsWindow : Maybe DecisionPathNode
        , viaOverview : Maybe DecisionPathNode
        , viaSolarSystemMenu : () -> DecisionPathNode
        }
dockToStationOrStructureWithMatchingName { namesFromSettingOrInfoPanel } context =
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
        (useMenuEntryWithTextContaining "dock" menuCascadeCompleted)
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
                |> List.filter overviewEntryIsDisplayed
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
                        (useMenuEntryWithTextContainingFirstOf
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


dockToStationOrStructureUsingSurroundingsButtonMenu :
    { prioritizeStructures : Bool
    , describeChoice : String
    , chooseEntry : List EveOnline.ParseUserInterface.ContextMenuEntry -> Maybe EveOnline.ParseUserInterface.ContextMenuEntry
    }
    -> BotDecisionContext
    -> DecisionPathNode
dockToStationOrStructureUsingSurroundingsButtonMenu { prioritizeStructures, describeChoice, chooseEntry } =
    useContextMenuCascadeOnListSurroundingsButton
        (useMenuEntryWithTextContainingFirstOf
            ([ "stations", "structures" ]
                |> (if prioritizeStructures then
                        List.reverse

                    else
                        identity
                   )
            )
            (useMenuEntryInLastContextMenuInCascade { describeChoice = describeChoice, chooseEntry = chooseEntry }
                (useMenuEntryWithTextContaining "dock" menuCascadeCompleted)
            )
        )


warpToMiningSite : BotDecisionContext -> DecisionPathNode
warpToMiningSite context =
    case context.eventContext.botSettings.anomalyNamePatterns of
        [] ->
            warpToMiningSiteOrRandomAsteroidBelt context

        anomalyNamePatterns ->
            warpToAnomaly anomalyNamePatterns context


{-| `mining-site` and the random-belt fallback, unchanged from before `anomaly-name`
existed -- separated out so `warpToMiningSite` can check `anomaly-name` first
without duplicating either of them.
-}
warpToMiningSiteOrRandomAsteroidBelt : BotDecisionContext -> DecisionPathNode
warpToMiningSiteOrRandomAsteroidBelt context =
    case context.eventContext.botSettings.miningSites of
        [] ->
            warpToRandomAsteroidBelt context

        miningSites ->
            let
                miningSitesSimplified : List String
                miningSitesSimplified =
                    List.map
                        simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry
                        miningSites

                travelOptions =
                    useContextMenuOnLocationWithMatchingName
                        (\displayName ->
                            List.any
                                (\miningSite ->
                                    String.contains
                                        miningSite
                                        (simplifyStationOrStructureNameFromSettingsBeforeComparingToMenuEntry
                                            displayName
                                        )
                                )
                                miningSitesSimplified
                        )
                        (useMenuEntryWithTextContaining "Warp to"
                            (useMenuEntryWithTextContaining "Within 0 m" menuCascadeCompleted)
                        )
                        context
            in
            case travelOptions.viaLocationsWindow of
                Just viaLocationsWindow ->
                    viaLocationsWindow

                Nothing ->
                    case travelOptions.viaOverview of
                        Just viaOverview ->
                            viaOverview

                        Nothing ->
                            describeBranch "I do not see a matching name in the Locations or overview windows. Therefore, we are falling back to the solar system menu."
                                (travelOptions.viaSolarSystemMenu ())


{-| The surroundings button's own 'Anomalies' entry -- a plain list of the
system's cosmic anomalies, with no probe scanner involved. `anomaly-name`
patterns are tried in order via `useMenuEntryWithTextContainingFirstOf`, so
an operator naming several anomaly types gets whichever is present rather
than needing all of them on grid at once. Same "Warp to" -> "Within 0 m"
tail as the random-belt path, so a found anomaly is warped to the same way.
-}
warpToAnomaly : List String -> BotDecisionContext -> DecisionPathNode
warpToAnomaly anomalyNamePatterns context =
    useContextMenuCascadeOnListSurroundingsButton
        (useMenuEntryWithTextContaining "anomalies"
            (useMenuEntryWithTextContainingFirstOf anomalyNamePatterns
                (useMenuEntryWithTextContaining "Warp to"
                    (useMenuEntryWithTextContaining "Within 0 m" menuCascadeCompleted)
                )
            )
        )
        context


warpToRandomAsteroidBelt : BotDecisionContext -> DecisionPathNode
warpToRandomAsteroidBelt context =
    useContextMenuCascadeOnListSurroundingsButton
        (useMenuEntryWithTextContaining "asteroid belts"
            (useRandomMenuEntry (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                (useMenuEntryWithTextContaining "Warp to"
                    (useMenuEntryWithTextContaining "Within 0 m" menuCascadeCompleted)
                )
            )
        )
        context


runAway : BotDecisionContext -> DecisionPathNode
runAway context =
    let
        defaultRoute : () -> DecisionPathNode
        defaultRoute () =
            dockToRandomStationOrStructure context
    in
    case unloadStationOrStructureNames context of
        [] ->
            defaultRoute ()

        stationAndStructureNames ->
            {-
               Prioritize unload station and overview entry, because that will be faster than using the surroundings button menu. If that fails, fall back to surroundings menu.
               <https://forum.botlab.org/t/the-mining-robot-cant-find-its-way-home/4922/4>
            -}
            let
                routesToStation =
                    dockToStationOrStructureWithMatchingName
                        { namesFromSettingOrInfoPanel = stationAndStructureNames }
                        context
            in
            case routesToStation.viaLocationsWindow of
                Just viaLocationsWindow ->
                    viaLocationsWindow

                Nothing ->
                    case routesToStation.viaOverview of
                        Just viaOverview ->
                            viaOverview

                        Nothing ->
                            defaultRoute ()


dockToUnloadOre : BotDecisionContext -> DecisionPathNode
dockToUnloadOre context =
    case unloadStationOrStructureNames context of
        [] ->
            describeBranch
                "At which station should I dock?. There is no station or structure name configured and I was never docked in a station in this session."
                askForHelpToGetUnstuck

        stationAndStructureNames ->
            let
                routesToStation :
                    { viaLocationsWindow : Maybe DecisionPathNode
                    , viaOverview : Maybe DecisionPathNode
                    , viaSolarSystemMenu : () -> DecisionPathNode
                    }
                routesToStation =
                    dockToStationOrStructureWithMatchingName
                        { namesFromSettingOrInfoPanel = stationAndStructureNames }
                        context
            in
            case routesToStation.viaLocationsWindow of
                Just viaLocationsWindow ->
                    viaLocationsWindow

                Nothing ->
                    case routesToStation.viaOverview of
                        Just viaOverview ->
                            viaOverview

                        Nothing ->
                            describeBranch
                                "I do not see a matching name in the Locations or overview windows. Therefore, we are falling back to the solar system menu."
                                (routesToStation.viaSolarSystemMenu ())


unloadStationOrStructureNames : BotDecisionContext -> List String
unloadStationOrStructureNames context =
    let
        fromSettings : List String
        fromSettings =
            List.concat
                [ context.eventContext.botSettings.unloadStationNames
                , context.eventContext.botSettings.unloadStructureNames
                ]
    in
    if fromSettings == [] then
        case context.memory.lastDockedStationNameFromInfoPanel of
            Just lastDocked ->
                [ lastDocked ]

            Nothing ->
                []

    else
        fromSettings


dockToRandomStationOrStructure : BotDecisionContext -> DecisionPathNode
dockToRandomStationOrStructure context =
    dockToStationOrStructureUsingSurroundingsButtonMenu
        { prioritizeStructures = False
        , describeChoice = "Pick random station"
        , chooseEntry = listElementAtWrappedIndex (context.randomIntegers |> List.head |> Maybe.withDefault 0)
        }
        context


launchOrReturnDronesAccordingToSettings : BotDecisionContext -> Maybe DecisionPathNode
launchOrReturnDronesAccordingToSettings context =
    let
        dronesShouldBeLaunched : Bool
        dronesShouldBeLaunched =
            if context.eventContext.botSettings.returnDronesWhenNoRatsVisible == PromptParser.Yes then
                case context.memory.lastTimeRatVisible of
                    Nothing ->
                        False

                    Just lastTimeRatVisible ->
                        let
                            timeSinceLastRatVisibleInSeconds =
                                (context.eventContext.timeInMilliseconds // 1000)
                                    - lastTimeRatVisible
                        in
                        timeSinceLastRatVisibleInSeconds < 10

            else
                True
    in
    if dronesShouldBeLaunched then
        launchDrones context

    else
        returnDronesToBay context


launchDrones : BotDecisionContext -> Maybe DecisionPathNode
launchDrones context =
    context.readingFromGameClient.dronesWindow
        |> Maybe.andThen
            (\dronesWindow ->
                case ( dronesWindow.droneGroupInBay, dronesWindow.droneGroupInSpace ) of
                    ( Just droneGroupInBay, Just droneGroupInSpace ) ->
                        let
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
                        in
                        if 0 < dronesInBayQuantity && dronesInSpaceQuantityCurrent < dronesInSpaceQuantityLimit then
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

                    _ ->
                        Nothing
            )


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


{-|


## `aggressive`: fight rather than flee

`returnDronesAndRunAwayIfHitpointsAreTooLowOrWithoutDrones` and
`wormholeSafetyStep` both call this before falling back to `runAway`, so
`aggressive = no` (the default) leaves both of those exactly as they were --
this function itself is the one place the setting is read, and it answers
`Nothing` immediately when it is off.

-}
aggressiveIsEnabled : BotDecisionContext -> Bool
aggressiveIsEnabled context =
    context.eventContext.botSettings.aggressive == PromptParser.Yes


{-| Every overview entry this bot is willing to fight under `aggressive = yes`.

Two rules, reused rather than restated: a rat by the client's own icon colour
(`ratsOnTheOverview`, the same test `overviewShowsRat` already uses for drone
bookkeeping above), and anything reading `commonIndications.isWarpDisruptingMe`
-- a scrambler can be a player ship carrying none of a rat's icon tint, and it
is the one thing here that takes away the option to leave, which is why it is
named explicitly rather than left to the colour rule to catch by accident.

De-duplicated by `overviewEntryObjectIdentity`, since a warp-disrupting rat
would otherwise appear in both halves at once.

-}
hostileOverviewEntries : ReadingFromGameClient -> List OverviewWindowEntry
hostileOverviewEntries readingFromGameClient =
    let
        overviewEntries =
            readingFromGameClient.overviewWindows |> List.concatMap .entries
    in
    (ratsOnTheOverview overviewEntries
        ++ (overviewEntries |> List.filter (.commonIndications >> .isWarpDisruptingMe))
    )
        |> List.Extra.uniqueBy overviewEntryObjectIdentity


{-| Which hostile to lock next. A row warp disrupting this ship sorts first
regardless of distance -- it is the one thing standing between this ship and
leaving, the same priority `overviewEntryIsWarpDisruptingMe` gets in every
combat-capable bot in this repo -- and otherwise the nearest one wins, since a
mining ship's drones have to close the distance themselves.
-}
hostileEngagementPriority : OverviewWindowEntry -> ( Int, Int )
hostileEngagementPriority entry =
    ( if entry.commonIndications.isWarpDisruptingMe then
        0

      else
        1
    , entry.objectDistanceInMeters |> Result.withDefault 999999999
    )


chooseHostileToEngage : List OverviewWindowEntry -> Maybe OverviewWindowEntry
chooseHostileToEngage entries =
    entries |> List.sortBy hostileEngagementPriority |> List.head


{-| `aggressive = yes`'s whole answer to a hostile: launch drones, lock the
highest-priority one, and send the drones after whatever this ship has
locked.

`Nothing` where there is nothing on the overview to fight at all -- a
wormhole hostile the Directional Scanner has seen but that has not yet
arrived on grid, for instance -- so both callers fall back to their own
flight response rather than sitting still commanding an engagement against
nothing. Also `Nothing`, unconditionally, while `aggressive = no`, which is
what keeps both callers' default behaviour unchanged.

-}
engageHostiles : BotDecisionContext -> Maybe DecisionPathNode
engageHostiles context =
    if not (aggressiveIsEnabled context) then
        Nothing

    else
        case hostileOverviewEntries context.readingFromGameClient |> chooseHostileToEngage of
            Nothing ->
                Nothing

            Just target ->
                Just
                    (describeBranch
                        ("Aggressive: engage '"
                            ++ (target.objectName |> Maybe.withDefault "the hostile")
                            ++ "'"
                            ++ (if target.commonIndications.isWarpDisruptingMe then
                                    " (warp disrupting this ship)"

                                else
                                    ""
                               )
                            ++ "."
                        )
                        (case launchDrones context of
                            Just launching ->
                                launching

                            Nothing ->
                                if target.commonIndications.targetedByMe then
                                    engageTargetWithDrones context
                                        |> Maybe.withDefault
                                            (describeBranch "No drones in space yet to send after it." waitForProgressInGame)

                                else
                                    lockTargetFromOverviewEntryAndEnsureIsInRange
                                        context
                                        context.eventContext.botSettings.targetingRange
                                        target
                        )
                    )


{-| Order every drone in space to attack the ship's current target, through
the drones window's own "Engage Target" menu entry -- the same cascade shape
`launchDrones` and `returnDronesToBay` already use on the sibling group.

`Nothing` with no drones in space, so the caller waits for the launch it just
commanded to land rather than opening a menu on an empty group.

-}
engageTargetWithDrones : BotDecisionContext -> Maybe DecisionPathNode
engageTargetWithDrones context =
    context.readingFromGameClient.dronesWindow
        |> Maybe.andThen .droneGroupInSpace
        |> Maybe.andThen
            (\droneGroupInSpace ->
                let
                    dronesInSpaceQuantityCurrent =
                        droneGroupInSpace.header.quantityFromTitle
                            |> Maybe.map .current
                            |> Maybe.withDefault 0
                in
                if dronesInSpaceQuantityCurrent < 1 then
                    Nothing

                else
                    Just
                        (describeBranch "Engage target with drones."
                            (useContextMenuCascade
                                ( "drones group", droneGroupInSpace.header.uiNode )
                                (useMenuEntryWithTextContaining "Engage" menuCascadeCompleted)
                                context
                            )
                        )
            )


readShipUIModuleButtonTooltips : BotDecisionContext -> Maybe DecisionPathNode
readShipUIModuleButtonTooltips =
    EveOnline.BotFrameworkSeparatingMemory.readShipUIModuleButtonTooltipWhereNotYetInMemory


{-| The framework's own `readShipUIModuleButtonTooltipWhereNotYetInMemory`
picks its target from _every_ module button, top row included -- and since
`knownMiningModulesFromContext` no longer needs a mining laser's tooltip at
all (it reads `moduleButtonsRows.top` directly), a discovery attempt landing
on a top-row button is now a wasted hover on a module whose identity this bot
never asks the tooltip for. Confirmed live: with `activate-module-always`
set and both lasers already known and active, the ship carried on mining with
the afterburner and hardener never even attempted, because every discovery
slot the framework was given kept re-landing on the mining lasers' own
still-undiscovered tooltips. Scoped to `middle` and `bottom` -- the rows
`activate-module-always` modules actually live in on this fit -- so a
discovery attempt can only ever advance toward the module this bot is still
missing.
-}
readModuleButtonTooltipForActivateAlwaysDiscovery : BotDecisionContext -> Maybe DecisionPathNode
readModuleButtonTooltipForActivateAlwaysDiscovery context =
    context.readingFromGameClient.shipUI
        |> Maybe.map (\shipUI -> shipUI.moduleButtonsRows.middle ++ shipUI.moduleButtonsRows.bottom)
        |> Maybe.withDefault []
        |> List.filter
            (EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton context.memory.shipModules >> (==) Nothing)
        |> List.head
        |> Maybe.map
            (\moduleButtonWithoutMemoryOfTooltip ->
                describeBranch "Read tooltip for module button to find modules to activate always."
                    (decideActionForCurrentStep
                        (EveOnline.BotFramework.mouseMoveToUIElement moduleButtonWithoutMemoryOfTooltip.uiNode)
                    )
            )


{-| The top row (high slots) is read straight off `moduleButtonsRows`, present
on every reading with no hover involved -- unlike identifying a mining laser
by its tooltip, which needs `isHiliteVisible` to catch a genuinely sustained
hover across two consecutive readings (`integrateCurrentReadingsIntoShipModulesMemory`).
Confirmed live: with two mining lasers fitted, the tooltip path only ever
locked in one of them, because `readShipUIModuleButtonTooltipWhereNotYetInMemory`
is reached only when there is otherwise nothing to do, and locking a new
target or approaching a rock keeps taking the mouse and the two readings' worth
of attention the hover needs before it gets there -- so the ship spent the whole
session firing at half its mining yield without saying so. High slots hold only
weapons and mining lasers on this game's own fitting rules, and this fit's
`activate-module-always` settings (afterburner, hardener) both name modules
that never live there, so every top-row button is safely a mining module.
-}
knownMiningModulesFromContext : BotDecisionContext -> List EveOnline.ParseUserInterface.ShipUIModuleButton
knownMiningModulesFromContext context =
    context.readingFromGameClient.shipUI
        |> Maybe.map (.moduleButtonsRows >> .top)
        |> Maybe.withDefault []


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
        >> List.map Tuple.first
        >> List.filterMap
            (\tooltipText ->
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


quickMessageHasClusterShutdown : BotDecisionContext -> Maybe String
quickMessageHasClusterShutdown context =
    context.readingFromGameClient
        |> EveOnline.BotFramework.quickMessageFromReadingFromGameClient
        |> Maybe.Extra.filter (Common.Basics.stringContainsIgnoringCase "Cluster Shutdown")


botMain : InterfaceToHost.BotConfig State
botMain =
    { init = EveOnline.BotFrameworkSeparatingMemory.initState initBotMemory
    , processEvent =
        EveOnline.BotFrameworkSeparatingMemory.processEvent
            { parseBotSettings = parseBotSettings
            , selectGameClientInstance =
                Maybe.andThen .selectInstancePilotName
                    >> Maybe.map EveOnline.BotFramework.selectGameClientInstanceWithPilotName
                    >> Maybe.withDefault EveOnline.BotFramework.selectGameClientInstanceWithTopmostWindow
            , updateMemoryForNewReadingFromGame = updateMemoryForNewReadingFromGame
            , statusTextFromDecisionContext = statusTextFromDecisionContext
            , decideNextStep = miningBotDecisionRoot
            }
    }


initBotMemory : BotMemory
initBotMemory =
    { lastDockedStationNameFromInfoPanel = Nothing
    , timesUnloaded = 0
    , volumeUnloadedCubicMeters = 0
    , lastUsedCapacityInMiningHold = Nothing
    , miningHoldDragAttemptReadings = 0
    , infoPanelSetupAttemptReadings = 0
    , contextMenuLastDepth = 0
    , contextMenuStuckTicks = 0
    , shipModules = EveOnline.BotFramework.initShipModulesMemory
    , overviewWindows = EveOnline.BotFramework.initOverviewWindowsMemory
    , lastReadingsInSpaceDronesWindowWasVisible = []
    , lastTimeRatVisible = Nothing
    , dscan = initDscanMemory
    }


statusTextFromDecisionContext : BotDecisionContext -> String
statusTextFromDecisionContext context =
    let
        readingFromGameClient : ReadingFromGameClient
        readingFromGameClient =
            context.readingFromGameClient

        describeSessionPerformance : String
        describeSessionPerformance =
            [ ( "times unloaded", context.memory.timesUnloaded )
            , ( "volume unloaded / m³", context.memory.volumeUnloadedCubicMeters )
            ]
                |> List.map (\( metric, amount ) -> metric ++ ": " ++ (amount |> String.fromInt))
                |> String.join ", "

        describeShip : String
        describeShip =
            case readingFromGameClient.shipUI of
                Just shipUI ->
                    [ "Shield HP at " ++ (shipUI.hitpointsPercent.shield |> String.fromInt) ++ "%."
                    , "Found " ++ (context |> knownMiningModulesFromContext |> List.length |> String.fromInt) ++ " mining modules."
                    ]
                        |> String.join " "

                Nothing ->
                    case
                        readingFromGameClient.infoPanelContainer
                            |> Maybe.andThen .infoPanelLocationInfo
                            |> Maybe.andThen .expandedContent
                            |> Maybe.andThen .currentStationName
                    of
                        Just stationName ->
                            "I am docked at '" ++ stationName ++ "'."

                        Nothing ->
                            "I do not see if I am docked or in space. Please set up game client first."

        describeDrones : String
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

        describeMiningHold : String
        describeMiningHold =
            "mining hold filled "
                ++ (readingFromGameClient
                        |> inventoryWindowWithMiningHoldSelectedFromGameClient
                        |> Maybe.andThen capacityGaugeUsedPercent
                        |> Maybe.map String.fromInt
                        |> Maybe.withDefault "Unknown"
                   )
                ++ "%."

        describeCurrentReading : String
        describeCurrentReading =
            [ describeMiningHold, describeShip, describeDrones ] |> String.join " "

        describeWormholeSafety : List String
        describeWormholeSafety =
            if context.eventContext.botSettings.wormhole == PromptParser.Yes then
                [ describeHostileTrust (hostileTrustFromSettings context.eventContext.botSettings)
                , describeGrid (gridEvidenceFromContext context)
                ]

            else
                []

        describeAggressive : List String
        describeAggressive =
            if aggressiveIsEnabled context then
                case hostileOverviewEntries readingFromGameClient |> chooseHostileToEngage of
                    Just target ->
                        [ "Aggressive: fighting '" ++ (target.objectName |> Maybe.withDefault "a hostile") ++ "'." ]

                    Nothing ->
                        [ "Aggressive: nothing hostile on the overview right now." ]

            else
                []
    in
    ([ "Session performance: " ++ describeSessionPerformance
     , "---"
     , "Current reading: " ++ describeCurrentReading
     ]
        ++ describeWormholeSafety
        ++ describeAggressive
    )
        |> String.join "\n"


updateMemoryForNewReadingFromGame : EveOnline.BotFrameworkSeparatingMemory.UpdateMemoryContext -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

        lastUsedCapacityInMiningHold =
            context.readingFromGameClient
                |> inventoryWindowWithMiningHoldSelectedFromGameClient
                |> Maybe.andThen .selectedContainerCapacityGauge
                |> Maybe.andThen Result.toMaybe
                |> Maybe.map .used

        completedUnloadSincePreviousReading =
            case botMemoryBefore.lastUsedCapacityInMiningHold of
                Nothing ->
                    False

                Just previousUsedCapacityInMiningHold ->
                    lastUsedCapacityInMiningHold == Just 0 && 0 < previousUsedCapacityInMiningHold

        volumeUnloadedSincePreviousReading =
            case botMemoryBefore.lastUsedCapacityInMiningHold of
                Nothing ->
                    0

                Just previousUsedCapacityInMiningHold ->
                    case lastUsedCapacityInMiningHold of
                        Nothing ->
                            0

                        Just currentUsedCapacityInMiningHold ->
                            -- During mining, when new ore appears in the inventory, this difference is negative.
                            max 0 (previousUsedCapacityInMiningHold - currentUsedCapacityInMiningHold)

        timesUnloaded =
            botMemoryBefore.timesUnloaded
                + (if completedUnloadSincePreviousReading then
                    1

                   else
                    0
                  )

        volumeUnloadedCubicMeters =
            botMemoryBefore.volumeUnloadedCubicMeters + volumeUnloadedSincePreviousReading

        {- Confirmed live on 2026-09-06: a drag-and-drop out of the mining hold
           can simply not land -- no dialog, no message box, nothing else in the
           reading changes -- and `dockedWithMiningHoldSelected` had nothing that
           could ever notice. It re-issues the identical gesture from the
           identical two points every reading for as long as the hold's item
           list still answers `Just`, with no counter and no confirmation that a
           previous attempt worked. One run sat there for over nine minutes and
           285 readings, unloaded nothing, and only cleared when the operator
           dragged it by hand. That is #34's family exactly: a wait with no
           bound and nothing it consults about its own progress.

           `volumeUnloadedSincePreviousReading` is already computed above from
           the same capacity gauge this counts against, and reusing it rather
           than adding a second read is what keeps a legitimate multi-stack
           unload from tripping this: each stack that actually drags resets the
           count, because the gauge falls whether the drag empties the hold
           outright or only takes one stack off it. Only a reading where the
           gauge does not move at all, with an item still sitting there, adds to
           it -- which is exactly the shape the stuck run had on every one of
           its 285 readings.
        -}
        miningHoldHasAnItemNow =
            context.readingFromGameClient
                |> inventoryWindowWithMiningHoldSelectedFromGameClient
                |> Maybe.andThen selectedContainerFirstItemFromInventoryWindow
                |> (\item -> item /= Nothing)

        miningHoldDragAttemptReadings =
            if not miningHoldHasAnItemNow then
                0

            else if 0 < volumeUnloadedSincePreviousReading then
                0

            else
                botMemoryBefore.miningHoldDragAttemptReadings + 1

        {- Same shape as the drag counter above: count readings the shared
           setup step still has something to do about the location info
           panel (whether that is "I do not see it at all" or "it is
           collapsed, click to expand"), and reset the moment it reports
           nothing left to do. Calling the pure function a second time here
           is cheap and keeps the counter from needing its own copy of the
           panel-reading logic, which could drift from the real one.
        -}
        infoPanelSetupAttemptReadings =
            case ensureInfoPanelLocationInfoIsExpanded context.readingFromGameClient of
                Nothing ->
                    0

                Just _ ->
                    botMemoryBefore.infoPanelSetupAttemptReadings + 1

        {- Ported from eve-online-saxrat alongside clearStrayContextMenu. Depth
           rather than presence: a reading that goes deeper than the last one
           is a cascade making progress and resets the count; one that stays at
           the same depth or drops without reaching zero is not, and adds to it.
        -}
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        contextMenuStuckTicks =
            if currentContextMenuDepth == 0 then
                0

            else if currentContextMenuDepth > botMemoryBefore.contextMenuLastDepth then
                0

            else
                botMemoryBefore.contextMenuStuckTicks + 1

        lastReadingsInSpaceDronesWindowWasVisible =
            if context.readingFromGameClient.shipUI == Nothing then
                botMemoryBefore.lastReadingsInSpaceDronesWindowWasVisible

            else
                (context.readingFromGameClient.dronesWindow /= Nothing)
                    :: botMemoryBefore.lastReadingsInSpaceDronesWindowWasVisible
                    |> List.take dockWhenDroneWindowInvisibleCount

        ratsVisibleNow =
            overviewShowsRat context.readingFromGameClient

        lastTimeRatVisible : Maybe Int
        lastTimeRatVisible =
            if ratsVisibleNow then
                Just (context.timeInMilliseconds // 1000)

            else
                botMemoryBefore.lastTimeRatVisible

        dscan =
            dscanMemoryAfterReading
                { nowMilliseconds = context.timeInMilliseconds
                , refreshAskedInPreviousStep =
                    context.previousStepsEffects
                        |> List.head
                        |> Maybe.map (stepPressedExactly directionalScanHotkey)
                        |> Maybe.withDefault False
                , windowIsInTheReading =
                    context.readingFromGameClient.directionalScannerWindow /= Nothing
                }
                botMemoryBefore.dscan
    in
    { lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , timesUnloaded = timesUnloaded
    , volumeUnloadedCubicMeters = volumeUnloadedCubicMeters
    , lastUsedCapacityInMiningHold = lastUsedCapacityInMiningHold
    , miningHoldDragAttemptReadings = miningHoldDragAttemptReadings
    , infoPanelSetupAttemptReadings = infoPanelSetupAttemptReadings
    , contextMenuLastDepth = currentContextMenuDepth
    , contextMenuStuckTicks = contextMenuStuckTicks
    , shipModules =
        botMemoryBefore.shipModules
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory context.readingFromGameClient
    , overviewWindows =
        botMemoryBefore.overviewWindows
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoOverviewWindowsMemory context.readingFromGameClient
    , lastReadingsInSpaceDronesWindowWasVisible = lastReadingsInSpaceDronesWindowWasVisible
    , lastTimeRatVisible = lastTimeRatVisible
    , dscan = dscan
    }


shouldDockBecauseDroneWindowWasInvisibleTooLong : BotMemory -> Bool
shouldDockBecauseDroneWindowWasInvisibleTooLong memory =
    (dockWhenDroneWindowInvisibleCount <= List.length memory.lastReadingsInSpaceDronesWindowWasVisible)
        && List.all ((==) False) memory.lastReadingsInSpaceDronesWindowWasVisible


ensureUserEnabledNameColumnInOverview :
    { ifEnabled : DecisionPathNode, ifDisabled : DecisionPathNode }
    -> ReadingFromGameClient
    -> DecisionPathNode
ensureUserEnabledNameColumnInOverview { ifEnabled, ifDisabled } readingFromGameClient =
    if
        readingFromGameClient.overviewWindows
            |> List.any
                (\overviewWindow ->
                    (overviewWindow.entries |> List.all (.objectName >> (==) Nothing))
                        && (0 < List.length overviewWindow.entries)
                )
    then
        describeBranch "The 'Name' column in the overview window seems disabled." ifDisabled

    else
        ifEnabled


activeShipTreeEntryFromInventoryWindow : EveOnline.ParseUserInterface.InventoryWindow -> Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
activeShipTreeEntryFromInventoryWindow =
    .leftTreeEntries
        -- Assume upmost entry is active ship.
        >> List.sortBy (.uiNode >> .totalDisplayRegion >> .y)
        >> List.head


clickableMineablesFromOverviewWindow : ReadingFromGameClient -> List OverviewWindowEntry
clickableMineablesFromOverviewWindow =
    overviewWindowEntriesRepresentingMineable
        >> List.filter overviewEntryIsDisplayed
        >> List.filter (.uiNode >> uiNodeVisibleRegionLargeEnoughForClicking)
        >> List.filter (.opacityPercent >> Maybe.map ((<=) 50) >> Maybe.withDefault True)
        >> List.sortBy (.uiNode >> .totalDisplayRegion >> .y)


mineableOverviewEntryMatchesSettings : BotSettings -> OverviewWindowEntry -> Bool
mineableOverviewEntryMatchesSettings settings overviewEntry =
    let
        textMatchesPattern text =
            (settings.includeAsteroidPatterns == [])
                || (settings.includeAsteroidPatterns
                        |> List.any (\pattern -> String.contains (String.toLower pattern) (String.toLower text))
                   )
    in
    overviewEntry.cellsTexts
        |> Dict.values
        |> List.any textMatchesPattern


{-| The same object read through two open overview windows is two distinct
`OverviewWindowEntry` values with no shared id in this parser, only whatever
each window happened to render -- so `mineableOverviewEntryMatchesSettings`
alone answers the question for one copy rather than for the object. Asked of
every entry sharing `overviewEntryObjectIdentity` with `overviewEntry`, so a
readable duplicate rescues a truncated one instead of the pick depending on
which window's copy the caller is holding.
-}
mineableOverviewEntryMatchesSettingsConsideringDuplicates :
    BotSettings
    -> List OverviewWindowEntry
    -> OverviewWindowEntry
    -> Bool
mineableOverviewEntryMatchesSettingsConsideringDuplicates settings allMineables overviewEntry =
    allMineables
        |> List.filter (overviewEntryObjectIdentity >> (==) (overviewEntryObjectIdentity overviewEntry))
        |> List.any (mineableOverviewEntryMatchesSettings settings)


{-| `objectName` and `objectDistance` (the client's own distance text, not
the parsed meters) are read off the same underlying object at the same
instant regardless of which overview window rendered them, so the pair is
enough to recognise "two windows' copies of one rock" without this parser
carrying a real item id.
-}
overviewEntryObjectIdentity : OverviewWindowEntry -> ( Maybe String, Maybe String )
overviewEntryObjectIdentity overviewEntry =
    ( overviewEntry.objectName, overviewEntry.objectDistance )


overviewWindowEntriesRepresentingMineable : ReadingFromGameClient -> List OverviewWindowEntry
overviewWindowEntriesRepresentingMineable =
    .overviewWindows
        >> List.map (.entries >> List.filter overviewWindowEntryRepresentsMineable)
        >> List.concat


{-| The widget's own `_display` flag, defaulting to shown when absent (most
nodes never set it).
-}
nodeIsDisplayed : EveOnline.MemoryReading.UITreeNode -> Bool
nodeIsDisplayed uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


{-| With more than one overview window open, the same physical object gets one
entry per window, and only the rows that fit on screen are actually rendered
-- the rest keep whatever region they last occupied while recycled (#479). A
hidden entry's region therefore points at whatever real object now sits in
that spot, so clicking it acts on the wrong thing rather than doing nothing.
`_display` is what distinguishes a rendered row from a stale one; the region
alone does not.
-}
overviewEntryIsDisplayed : OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    nodeIsDisplayed entry.uiNode.uiNode


overviewWindowEntryRepresentsMineable : OverviewWindowEntry -> Bool
overviewWindowEntryRepresentsMineable entry =
    if
        (entry.textsLeftToRight |> List.any (stringContainsIgnoringCase "asteroid"))
            && (entry.textsLeftToRight |> List.any (stringContainsIgnoringCase "belt") |> not)
    then
        True

    else
        {-
           2025-11-12: Squids4daddy:
           One important addition that it needs.  Please add "Harvestable Cloud" as a recognized type of ore in the overview.a
           The bot currently tries to warp out of gas sites because it doesn't recognize that as what the ship is there for
           Note that there are at least 8 varieties, but they all start with the Harvestable Cloud label.
        -}
        entry.textsLeftToRight |> List.any (stringContainsIgnoringCase "harvestable cloud")


capacityGaugeUsedPercent : EveOnline.ParseUserInterface.InventoryWindow -> Maybe Int
capacityGaugeUsedPercent =
    .selectedContainerCapacityGauge
        >> Maybe.andThen Result.toMaybe
        >> Maybe.andThen
            (\capacity -> capacity.maximum |> Maybe.map (\maximum -> capacity.used * 100 // maximum))


compressAndStackAllIfConditionsMet :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> { miningHoldFillPercent : Int, ifNothingToCompress : DecisionPathNode }
    -> DecisionPathNode
compressAndStackAllIfConditionsMet context inventoryWindowWithMiningHold config =
    let
        closeCompressionWindow =
            case context.readingFromGameClient.compressionWindow of
                Nothing ->
                    stackAllIfSeeingStackableItems
                        inventoryWindowWithMiningHold
                        { ifNotSeeingStackableItems = config.ifNothingToCompress }

                Just compressionWindow ->
                    case compressionWindow.windowControls |> Maybe.andThen .closeButton of
                        Nothing ->
                            describeBranch "Close window button is missing"
                                -- Assume buttons appear on mouse hover
                                (decideActionForCurrentStep
                                    (EveOnline.BotFramework.mouseMoveToUIElement compressionWindow.uiNode)
                                )

                        Just closeButton ->
                            mouseClickOnUIElement MouseButtonLeft closeButton
                                |> Result.Extra.unpack
                                    (always (describeBranch "Failed click on close button" askForHelpToGetUnstuck))
                                    decideActionForCurrentStep
    in
    if context.eventContext.botSettings.compressFromMiningHold /= PromptParser.Yes then
        closeCompressionWindow

    else
        case
            inventoryWindowWithMiningHold
                |> selectedContainerItemsFromInventoryWindow
                |> Maybe.withDefault []
                |> List.filter inventoryItemIsCandidateForCompression
                |> List.head
        of
            Nothing ->
                closeCompressionWindow

            Just itemToCompress ->
                describeBranch "I see at least one item to compress"
                    (if
                        config.miningHoldFillPercent
                            < (context.eventContext.botSettings.unloadMiningHoldPercent // 2)
                     then
                        closeCompressionWindow

                     else
                        case context.readingFromGameClient.compressionWindow of
                            Nothing ->
                                useContextMenuCascade
                                    ( "item to compress", itemToCompress )
                                    (useMenuEntryWithTextContaining "compress" menuCascadeCompleted)
                                    context

                            Just compressionWindow ->
                                case compressionWindow.compressButton of
                                    Nothing ->
                                        describeBranch "Compress button is missing" closeCompressionWindow

                                    Just compressButton ->
                                        mouseClickOnUIElement MouseButtonLeft compressButton
                                            |> Result.Extra.unpack
                                                (always (describeBranch "Failed click on compress button" askForHelpToGetUnstuck))
                                                decideActionForCurrentStep
                    )


stackAllIfSeeingStackableItems :
    EveOnline.ParseUserInterface.InventoryWindow
    -> { ifNotSeeingStackableItems : DecisionPathNode }
    -> DecisionPathNode
stackAllIfSeeingStackableItems inventoryWindow { ifNotSeeingStackableItems } =
    let
        inventoryItemsWithLongestDisplayText =
            inventoryWindow
                |> selectedContainerItemsFromInventoryWindow
                |> Maybe.withDefault []
                |> List.filterMap
                    (\itemNode ->
                        itemNode
                            |> getAllContainedDisplayTextsWithRegion
                            |> List.map Tuple.first
                            |> List.sortBy String.length
                            |> List.reverse
                            |> List.head
                            |> Maybe.map (Tuple.pair itemNode)
                    )

        inventoryItemsGroupedByDisplayText =
            inventoryItemsWithLongestDisplayText
                |> List.Extra.gatherEqualsBy Tuple.second

        stackableItems =
            inventoryItemsGroupedByDisplayText
                |> List.filter (Tuple.second >> List.length >> (<) 1)
    in
    if stackableItems == [] then
        ifNotSeeingStackableItems

    else
        describeBranch
            ("Seeing "
                ++ String.fromInt (List.sum (List.map (Tuple.second >> List.length) stackableItems))
                ++ " stackable items in "
                ++ String.fromInt (List.length stackableItems)
                ++ " groups"
            )
            (case inventoryWindow.buttonToStackAll of
                Nothing ->
                    describeBranch "Missing button to stack all"
                        ifNotSeeingStackableItems

                Just buttonToStackAll ->
                    mouseClickOnUIElement MouseButtonLeft buttonToStackAll
                        |> Result.Extra.unpack
                            (always (describeBranch "Failed click on button" askForHelpToGetUnstuck))
                            decideActionForCurrentStep
            )


inventoryItemIsCandidateForCompression : UIElement -> Bool
inventoryItemIsCandidateForCompression =
    EveOnline.ParseUserInterface.getAllContainedDisplayTextsWithRegion
        >> List.all (Tuple.first >> String.toLower >> String.contains "compressed" >> not)


inventoryWindowWithMiningHoldSelectedFromGameClient : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.InventoryWindow
inventoryWindowWithMiningHoldSelectedFromGameClient =
    .inventoryWindows
        >> List.filter inventoryWindowSelectedContainerIsMiningHold
        >> List.head


inventoryWindowSelectedContainerIsMiningHold : EveOnline.ParseUserInterface.InventoryWindow -> Bool
inventoryWindowSelectedContainerIsMiningHold inventoryWindow =
    inventoryWindowSelectedContainerIsMiningHold_PhotonUI inventoryWindow
        || inventoryWindowSelectedContainerIsMiningHold_pre_PhotonUI inventoryWindow


inventoryWindowSelectedContainerIsMiningHold_PhotonUI : EveOnline.ParseUserInterface.InventoryWindow -> Bool
inventoryWindowSelectedContainerIsMiningHold_PhotonUI =
    activeShipTreeEntryFromInventoryWindow
        >> Maybe.andThen miningHoldFromInventoryWindowShipEntry
        >> Maybe.map (.uiNode >> containsSelectionIndicatorPhotonUI)
        >> Maybe.withDefault False


inventoryWindowSelectedContainerIsMiningHold_pre_PhotonUI : EveOnline.ParseUserInterface.InventoryWindow -> Bool
inventoryWindowSelectedContainerIsMiningHold_pre_PhotonUI =
    .subCaptionLabelText >> Maybe.map (stringContainsIgnoringCase "mining hold") >> Maybe.withDefault False


selectedContainerFirstItemFromInventoryWindow : EveOnline.ParseUserInterface.InventoryWindow -> Maybe UIElement
selectedContainerFirstItemFromInventoryWindow =
    selectedContainerItemsFromInventoryWindow
        >> Maybe.andThen List.head


selectedContainerItemsFromInventoryWindow : EveOnline.ParseUserInterface.InventoryWindow -> Maybe (List UIElement)
selectedContainerItemsFromInventoryWindow =
    .selectedContainerInventory
        >> Maybe.andThen .itemsView
        >> Maybe.map
            (\itemsView ->
                case itemsView of
                    EveOnline.ParseUserInterface.InventoryItemsListView { items } ->
                        items |> List.map .uiNode

                    EveOnline.ParseUserInterface.InventoryItemsNotListView { items } ->
                        items
            )


miningHoldFromInventoryWindowShipEntry :
    EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    -> Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
miningHoldFromInventoryWindowShipEntry =
    .children
        >> List.map EveOnline.ParseUserInterface.unwrapInventoryWindowLeftTreeEntryChild
        >> List.filter (.text >> stringContainsIgnoringCase "mining hold")
        >> List.head


itemHangarFromInventoryWindow :
    EveOnline.ParseUserInterface.InventoryWindow
    -> Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
itemHangarFromInventoryWindow =
    .leftTreeEntries
        >> List.filter (.text >> stringContainsIgnoringCase "item hangar")
        >> List.head


fleetHangarFromInventoryWindow :
    EveOnline.ParseUserInterface.InventoryWindow
    -> Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
fleetHangarFromInventoryWindow =
    .leftTreeEntries
        >> List.filter (.text >> stringContainsIgnoringCase "fleet hangar")
        >> List.head


shipManeuverIsApproaching : ReadingFromGameClient -> Bool
shipManeuverIsApproaching =
    .shipUI
        >> Maybe.andThen .indication
        >> Maybe.andThen .maneuverType
        >> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverApproach)
        -- If the ship is just floating in space, there might be no indication displayed.
        >> Maybe.withDefault False


containsSelectionIndicatorPhotonUI : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
containsSelectionIndicatorPhotonUI =
    EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        >> List.any
            (.uiNode
                >> (\uiNode ->
                        (uiNode.pythonObjectTypeName
                            |> String.startsWith "SelectionIndicator"
                        )
                            && (uiNode
                                    |> EveOnline.ParseUserInterface.getColorPercentFromDictEntries
                                    |> Maybe.map (.a >> (<) 10)
                                    |> Maybe.withDefault False
                               )
                   )
            )


overviewShowsRat : ReadingFromGameClient -> Bool
overviewShowsRat readingFromGameClient =
    List.any
        (\overviewWindow ->
            List.any iconSpriteHasColorOfRat overviewWindow.entries
        )
        readingFromGameClient.overviewWindows


iconSpriteHasColorOfRat : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
iconSpriteHasColorOfRat overviewEntry =
    case overviewEntry.iconSpriteColorPercent of
        Nothing ->
            False

        Just colorPercent ->
            (colorPercent.g * 3 < colorPercent.r)
                && (colorPercent.b * 3 < colorPercent.r)
                && (60 < colorPercent.r && 50 < colorPercent.a)


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt


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


knownAfterburnerModulesFromContext : BotDecisionContext -> List EveOnline.ParseUserInterface.ShipUIModuleButton
knownAfterburnerModulesFromContext context =
    case context.eventContext.botSettings.afterburnerModuleText of
        Nothing ->
            []

        Just afterburnerText ->
            context.readingFromGameClient.shipUI
                |> Maybe.map .moduleButtons
                |> Maybe.withDefault []
                |> List.filter
                    (\moduleButton ->
                        moduleButton
                            |> EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton context.memory.shipModules
                            |> Maybe.map
                                (\tooltipMemory ->
                                    tooltipMemory.allContainedDisplayTextsWithRegion
                                        |> List.map Tuple.first
                                        |> List.any (stringContainsIgnoringCase afterburnerText)
                                )
                            |> Maybe.withDefault False
                    )
