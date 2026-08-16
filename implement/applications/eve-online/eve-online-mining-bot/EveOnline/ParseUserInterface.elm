module EveOnline.ParseUserInterface exposing (..)

{-| A library of building blocks to build programs that read from the EVE Online game client.

The EVE Online client's UI tree can contain thousands of nodes and tens of thousands of individual properties. Because of this large amount of data, navigating in there can be time-consuming.

This library helps us navigate the UI tree with functions to filter out redundant data and extract the interesting bits.

The types in this module provide names more closely related to players' experience, such as the overview window or ship modules.

To learn about the user interface structures in the EVE Online game client, see the guide at <https://to.botlab.org/guide/parsed-user-interface-of-the-eve-online-game-client>

-}

import Common.EffectOnWindow
import Dict
import EveOnline.MemoryReading
import Json.Decode
import List.Extra
import Maybe.Extra
import Regex
import Result.Extra
import Set


type alias ParsedUserInterface =
    { uiTree : UITreeNodeWithDisplayRegion
    , contextMenus : List ContextMenu
    , shipUI : Maybe ShipUI
    , targets : List Target
    , infoPanelContainer : Maybe InfoPanelContainer
    , overviewWindows : List OverviewWindow
    , selectedItemWindow : Maybe SelectedItemWindow
    , dronesWindow : Maybe DronesWindow
    , fittingWindow : Maybe FittingWindow
    , probeScannerWindow : Maybe ProbeScannerWindow
    , directionalScannerWindow : Maybe DirectionalScannerWindow
    , stationWindow : Maybe StationWindow
    , inventoryWindows : List InventoryWindow
    , chatWindowStacks : List ChatWindowStack
    , agentConversationWindows : List AgentConversationWindow
    , marketOrdersWindow : Maybe MarketOrdersWindow
    , surveyScanWindow : Maybe SurveyScanWindow
    , bookmarkLocationWindow : Maybe BookmarkLocationWindow
    , repairShopWindow : Maybe RepairShopWindow
    , characterSheetWindow : Maybe CharacterSheetWindow
    , fleetWindow : Maybe FleetWindow
    , watchListPanel : Maybe WatchListPanel
    , standaloneBookmarkWindow : Maybe StandaloneBookmarkWindow
    , moduleButtonTooltip : Maybe ModuleButtonTooltip
    , heatStatusTooltip : Maybe HeatStatusTooltip
    , neocom : Maybe Neocom
    , messageBoxes : List MessageBox
    , layerAbovemain : Maybe UITreeNodeWithDisplayRegion
    , keyActivationWindow : Maybe KeyActivationWindow
    , gameLogEntriesSinceLastReading : Maybe (List GameLogEntry)
    , incomingDamageSinceLastReading : Maybe IncomingDamage
    , outgoingDamageSinceLastReading : Maybe (List OutgoingDamageToTarget)
    }


type alias UITreeNodeWithDisplayRegion =
    { uiNode : EveOnline.MemoryReading.UITreeNode
    , children : Maybe (List ChildOfNodeWithDisplayRegion)
    , selfDisplayRegion : DisplayRegion
    , totalDisplayRegion : DisplayRegion
    , totalDisplayRegionVisible : DisplayRegion
    }


type ChildOfNodeWithDisplayRegion
    = ChildWithRegion UITreeNodeWithDisplayRegion
    | ChildWithoutRegion EveOnline.MemoryReading.UITreeNode


type alias DisplayRegion =
    { x : Int
    , y : Int
    , width : Int
    , height : Int
    }


type alias Location2d =
    { x : Int
    , y : Int
    }


type alias ContextMenu =
    { uiNode : UITreeNodeWithDisplayRegion
    , entries : List ContextMenuEntry
    }


type alias ContextMenuEntry =
    { uiNode : UITreeNodeWithDisplayRegion
    , text : String
    }


type alias ShipUI =
    { uiNode : UITreeNodeWithDisplayRegion
    , capacitor : ShipUICapacitor
    , hitpointsPercent : Hitpoints
    , indication : Maybe ShipUIIndication
    , moduleButtons : List ShipUIModuleButton
    , moduleButtonsRows :
        { top : List ShipUIModuleButton
        , middle : List ShipUIModuleButton
        , bottom : List ShipUIModuleButton
        }
    , offensiveBuffButtonNames : List String
    , squadronsUI : Maybe SquadronsUI
    , stopButton : Maybe UITreeNodeWithDisplayRegion
    , maxSpeedButton : Maybe UITreeNodeWithDisplayRegion
    , heatGauges : Maybe ShipUIHeatGauges
    }


type alias ShipUIIndication =
    { uiNode : UITreeNodeWithDisplayRegion
    , maneuverType : Maybe ShipManeuverType
    }


type alias ShipUIModuleButton =
    { uiNode : UITreeNodeWithDisplayRegion
    , slotUINode : UITreeNodeWithDisplayRegion
    , isActive : Maybe Bool
    , isHiliteVisible : Bool
    , rampRotationMilli : Maybe Int
    , stateFromDictEntries : ShipUIModuleButtonState
    }


type alias ShipUICapacitor =
    { uiNode : UITreeNodeWithDisplayRegion
    , pmarks : List ShipUICapacitorPmark
    , levelFromPmarksPercent : Maybe Int
    }


type alias ShipUICapacitorPmark =
    { uiNode : UITreeNodeWithDisplayRegion
    , colorPercent : Maybe ColorComponents
    }


type alias ShipUIHeatGauges =
    { uiNode : UITreeNodeWithDisplayRegion
    , gauges : List ShipUIHeatGauge
    }


type alias ShipUIHeatGauge =
    { uiNode : UITreeNodeWithDisplayRegion
    , rotationPercent : Maybe Int
    , heatPercent : Maybe Int
    }


type alias Hitpoints =
    { structure : Int
    , armor : Int
    , shield : Int
    }


type ShipManeuverType
    = ManeuverWarp
    | ManeuverJump
    | ManeuverOrbit
    | ManeuverApproach


type alias SquadronsUI =
    { uiNode : UITreeNodeWithDisplayRegion
    , squadrons : List SquadronUI
    }


type alias SquadronUI =
    { uiNode : UITreeNodeWithDisplayRegion
    , abilities : List SquadronAbilityIcon
    , actionLabel : Maybe UITreeNodeWithDisplayRegion
    }


type alias SquadronAbilityIcon =
    { uiNode : UITreeNodeWithDisplayRegion
    , quantity : Maybe Int
    , ramp_active : Maybe Bool
    }


type alias InfoPanelContainer =
    { uiNode : UITreeNodeWithDisplayRegion
    , icons : Maybe InfoPanelIcons
    , infoPanelLocationInfo : Maybe InfoPanelLocationInfo
    , infoPanelRoute : Maybe InfoPanelRoute
    , infoPanelAgentMissions : Maybe InfoPanelAgentMissions
    }


type alias InfoPanelIcons =
    { uiNode : UITreeNodeWithDisplayRegion
    , search : Maybe UITreeNodeWithDisplayRegion
    , locationInfo : Maybe UITreeNodeWithDisplayRegion
    , route : Maybe UITreeNodeWithDisplayRegion
    , agentMissions : Maybe UITreeNodeWithDisplayRegion
    , dailyChallenge : Maybe UITreeNodeWithDisplayRegion
    }


type alias InfoPanelRoute =
    { uiNode : UITreeNodeWithDisplayRegion
    , routeElementMarker : List InfoPanelRouteRouteElementMarker
    }


type alias InfoPanelRouteRouteElementMarker =
    { uiNode : UITreeNodeWithDisplayRegion
    , numJumps : Maybe Int
    }


type alias InfoPanelLocationInfo =
    { uiNode : UITreeNodeWithDisplayRegion
    , listSurroundingsButton : UITreeNodeWithDisplayRegion
    , currentSolarSystemName : Maybe String
    , securityStatusPercent : Maybe Int
    , expandedContent : Maybe InfoPanelLocationInfoExpandedContent
    }


type alias InfoPanelLocationInfoExpandedContent =
    { currentStationName : Maybe String
    }


type alias InfoPanelAgentMissions =
    { uiNode : UITreeNodeWithDisplayRegion
    , entries : List InfoPanelAgentMissionsEntry
    }


type alias InfoPanelAgentMissionsEntry =
    { uiNode : UITreeNodeWithDisplayRegion
    }


type alias Target =
    { uiNode : UITreeNodeWithDisplayRegion
    , barAndImageCont : Maybe UITreeNodeWithDisplayRegion
    , textsTopToBottom : List String
    , isActiveTarget : Bool
    , assignedContainerNode : Maybe UITreeNodeWithDisplayRegion
    , assignedIcons : List UITreeNodeWithDisplayRegion
    }


type alias OverviewWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , entriesHeaders : List ( String, UITreeNodeWithDisplayRegion )
    , entries : List OverviewWindowEntry
    , scrollControls : Maybe ScrollControls
    }


type alias OverviewWindowEntry =
    { uiNode : UITreeNodeWithDisplayRegion
    , textsLeftToRight : List String
    , cellsTexts : Dict.Dict String String
    , objectDistance : Maybe String
    , objectDistanceInMeters : Result String Int
    , objectName : Maybe String
    , objectType : Maybe String
    , objectAlliance : Maybe String
    , iconSpriteColorPercent : Maybe ColorComponents
    , namesUnderSpaceObjectIcon : Set.Set String
    , bgColorFillsPercent : List ColorComponents
    , rightAlignedIconsHints : List String
    , commonIndications : OverviewWindowEntryCommonIndications
    , opacityPercent : Maybe Int
    }


type alias OverviewWindowEntryCommonIndications =
    { targeting : Bool
    , targetedByMe : Bool
    , isJammingMe : Bool
    , isWarpDisruptingMe : Bool
    , isTrackingDisruptingMe : Bool
    , isSensorDampeningMe : Bool
    }


type alias SelectedItemWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , orbitButton : Maybe UITreeNodeWithDisplayRegion
    }


type alias FittingWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    }


type alias MarketOrdersWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    }


type alias SurveyScanWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , scanEntries : List UITreeNodeWithDisplayRegion
    }


type alias RepairShopWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , items : List UITreeNodeWithDisplayRegion
    , buttonGroup : Maybe UITreeNodeWithDisplayRegion
    , buttons : List { uiNode : UITreeNodeWithDisplayRegion, mainText : Maybe String }
    }


type alias CharacterSheetWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , skillGroups : List UITreeNodeWithDisplayRegion
    }


type alias ColorComponents =
    { a : Int, r : Int, g : Int, b : Int }


type alias DronesWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , droneGroups : List DronesWindowEntryGroupStructure
    , droneGroupInBay : Maybe DronesWindowEntryGroupStructure
    , droneGroupInSpace : Maybe DronesWindowEntryGroupStructure
    }


type alias DronesWindowEntryGroupStructure =
    { header : DronesWindowDroneGroupHeader
    , children : List DronesWindowEntry
    }


type DronesWindowEntry
    = DronesWindowEntryGroup DronesWindowEntryGroupStructure
    | DronesWindowEntryDrone DronesWindowEntryDroneStructure


type alias DronesWindowDroneGroupHeader =
    { uiNode : UITreeNodeWithDisplayRegion
    , mainText : Maybe String
    , quantityFromTitle : Maybe DronesWindowDroneGroupHeaderQuantity
    }


type alias DronesWindowDroneGroupHeaderQuantity =
    { current : Int
    , maximum : Maybe Int
    }


type alias DronesWindowEntryDroneStructure =
    { uiNode : UITreeNodeWithDisplayRegion
    , mainText : Maybe String
    , hitpointsPercent : Maybe Hitpoints
    }


type alias ProbeScannerWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , scanResults : List ProbeScanResult
    }


type alias ProbeScanResult =
    { uiNode : UITreeNodeWithDisplayRegion
    , textsLeftToRight : List String
    , cellsTexts : Dict.Dict String String
    , warpButton : Maybe UITreeNodeWithDisplayRegion
    }


type alias DirectionalScannerWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , scrollNode : Maybe UITreeNodeWithDisplayRegion
    , scanResults : List UITreeNodeWithDisplayRegion
    }


type alias StationWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , undockButton : Maybe UITreeNodeWithDisplayRegion
    , abortUndockButton : Maybe UITreeNodeWithDisplayRegion
    }


type alias InventoryWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , leftTreeEntries : List InventoryWindowLeftTreeEntry
    , subCaptionLabelText : Maybe String
    , selectedContainerCapacityGauge : Maybe (Result String InventoryWindowCapacityGauge)
    , selectedContainerInventory : Maybe Inventory
    , buttonToSwitchToListView : Maybe UITreeNodeWithDisplayRegion
    , buttonToStackAll : Maybe UITreeNodeWithDisplayRegion
    }


type alias Inventory =
    { uiNode : UITreeNodeWithDisplayRegion
    , itemsView : Maybe InventoryItemsView
    , scrollControls : Maybe ScrollControls
    }


type InventoryItemsView
    = InventoryItemsListView { items : List UITreeNodeWithDisplayRegion }
    | InventoryItemsNotListView { items : List UITreeNodeWithDisplayRegion }


type alias InventoryWindowLeftTreeEntry =
    { uiNode : UITreeNodeWithDisplayRegion
    , toggleBtn : Maybe UITreeNodeWithDisplayRegion
    , selectRegion : Maybe UITreeNodeWithDisplayRegion
    , text : String
    , children : List InventoryWindowLeftTreeEntryChild
    }


type InventoryWindowLeftTreeEntryChild
    = InventoryWindowLeftTreeEntryChild InventoryWindowLeftTreeEntry


type alias InventoryWindowCapacityGauge =
    { used : Int
    , maximum : Maybe Int
    , selected : Maybe Int
    }


type alias ChatWindowStack =
    { uiNode : UITreeNodeWithDisplayRegion
    , chatWindow : Maybe ChatWindow
    }


type alias ChatWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , name : Maybe String
    , userlist : Maybe ChatWindowUserlist
    }


type alias ChatWindowUserlist =
    { uiNode : UITreeNodeWithDisplayRegion
    , visibleUsers : List ChatUserEntry
    , scrollControls : Maybe ScrollControls
    }


type alias ChatUserEntry =
    { uiNode : UITreeNodeWithDisplayRegion
    , name : Maybe String
    , standingIconHint : Maybe String
    }


type alias ModuleButtonTooltip =
    { uiNode : UITreeNodeWithDisplayRegion
    , shortcut : Maybe { text : String, parseResult : Result String (List Common.EffectOnWindow.VirtualKeyCode) }
    , optimalRange : Maybe { asString : String, inMeters : Result String Int }
    }


type alias HeatStatusTooltip =
    { uiNode : UITreeNodeWithDisplayRegion
    , lowPercent : Maybe Int
    , mediumPercent : Maybe Int
    , highPercent : Maybe Int
    }


type alias Neocom =
    { uiNode : UITreeNodeWithDisplayRegion
    , iconInventory : Maybe UITreeNodeWithDisplayRegion
    , clock : Maybe NeocomClock
    }


type alias NeocomClock =
    { uiNode : UITreeNodeWithDisplayRegion
    , text : String
    , parsedText : Result String { hour : Int, minute : Int }
    }


type alias AgentConversationWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    }


type alias BookmarkLocationWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , submitButton : Maybe UITreeNodeWithDisplayRegion
    , cancelButton : Maybe UITreeNodeWithDisplayRegion
    }


type alias MessageBox =
    { uiNode : UITreeNodeWithDisplayRegion
    , buttonGroup : Maybe UITreeNodeWithDisplayRegion
    , buttons : List { uiNode : UITreeNodeWithDisplayRegion, mainText : Maybe String }
    }


type alias ScrollControls =
    { uiNode : UITreeNodeWithDisplayRegion
    , scrollHandle : Maybe UITreeNodeWithDisplayRegion
    }


type alias FleetWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , fleetMembers : List UITreeNodeWithDisplayRegion
    }


type alias WatchListPanel =
    { uiNode : UITreeNodeWithDisplayRegion
    , entries : List UITreeNodeWithDisplayRegion
    }


type alias StandaloneBookmarkWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , entries : List UITreeNodeWithDisplayRegion
    }


type alias KeyActivationWindow =
    { uiNode : UITreeNodeWithDisplayRegion
    , activateButton : Maybe UITreeNodeWithDisplayRegion
    }


parseUITreeWithDisplayRegionFromUITree : EveOnline.MemoryReading.UITreeNode -> UITreeNodeWithDisplayRegion
parseUITreeWithDisplayRegionFromUITree uiTree =
    let
        selfDisplayRegion =
            uiTree |> getDisplayRegionFromDictEntries |> Maybe.withDefault { x = 0, y = 0, width = 0, height = 0 }
    in
    uiTree
        |> asUITreeNodeWithDisplayRegion
            { selfDisplayRegion = selfDisplayRegion
            , totalDisplayRegion = selfDisplayRegion
            , occludedRegions = []
            }


parseUserInterfaceFromUITree : UITreeNodeWithDisplayRegion -> ParsedUserInterface
parseUserInterfaceFromUITree uiTree =
    { uiTree = uiTree
    , contextMenus = parseContextMenusFromUITreeRoot uiTree
    , shipUI = parseShipUIFromUITreeRoot uiTree
    , targets = parseTargetsFromUITreeRoot uiTree
    , infoPanelContainer = parseInfoPanelContainerFromUIRoot uiTree
    , overviewWindows = parseOverviewWindowsFromUITreeRoot uiTree
    , selectedItemWindow = parseSelectedItemWindowFromUITreeRoot uiTree
    , dronesWindow = parseDronesWindowFromUITreeRoot uiTree
    , fittingWindow = parseFittingWindowFromUITreeRoot uiTree
    , probeScannerWindow = parseProbeScannerWindowFromUITreeRoot uiTree
    , directionalScannerWindow = parseDirectionalScannerWindowFromUITreeRoot uiTree
    , stationWindow = parseStationWindowFromUITreeRoot uiTree
    , inventoryWindows = parseInventoryWindowsFromUITreeRoot uiTree
    , moduleButtonTooltip = parseModuleButtonTooltipFromUITreeRoot uiTree
    , heatStatusTooltip = parseHeatStatusTooltipFromUITreeRoot uiTree
    , chatWindowStacks = parseChatWindowStacksFromUITreeRoot uiTree
    , agentConversationWindows = parseAgentConversationWindowsFromUITreeRoot uiTree
    , marketOrdersWindow = parseMarketOrdersWindowFromUITreeRoot uiTree
    , surveyScanWindow = parseSurveyScanWindowFromUITreeRoot uiTree
    , bookmarkLocationWindow = parseBookmarkLocationWindowFromUITreeRoot uiTree
    , repairShopWindow = parseRepairShopWindowFromUITreeRoot uiTree
    , characterSheetWindow = parseCharacterSheetWindowFromUITreeRoot uiTree
    , fleetWindow = parseFleetWindowFromUITreeRoot uiTree
    , watchListPanel = parseWatchListPanelFromUITreeRoot uiTree
    , standaloneBookmarkWindow = parseStandaloneBookmarkWindowFromUITreeRoot uiTree
    , neocom = parseNeocomFromUITreeRoot uiTree
    , messageBoxes = parseMessageBoxesFromUITreeRoot uiTree
    , layerAbovemain = parseLayerAbovemainFromUITreeRoot uiTree
    , keyActivationWindow = parseKeyActivationWindowFromUITreeRoot uiTree
    , gameLogEntriesSinceLastReading = parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTree
    , incomingDamageSinceLastReading = parseIncomingDamageSinceLastReadingFromUITreeRoot uiTree
    , outgoingDamageSinceLastReading = parseOutgoingDamageSinceLastReadingFromUITreeRoot uiTree
    }


{-| One line EVE's own client wrote to its game log, as carried into a reading
by the macOS host in this fork. `channel` is the client's own bracketed
category -- `notify` for a refusal, `None` for travel -- and is a `Maybe`
because a node missing it is a host that did not say, not a line without one.
-}
type alias GameLogEntry =
    { timestamp : Maybe String
    , channel : Maybe String
    , text : String
    }


{-| What the client said in its own game log since the previous reading.

The client explains every refusal there and nowhere else -- "You cannot load or
unload <weapon> while it is active", "You are already managing 6 targets, as
many as you have skill to", "You cannot launch Acolyte I because you are already
controlling 5 drones" -- while a bot that sees only the UI tree has to infer each
of them from something else failing to change.

`Nothing` and `Just []` are different answers and must stay so. `Nothing` is a
host that provides no game log at all -- BotLab.exe, or this fork's host run
with `--no-game-log` -- and reading that as "the client said nothing" is how a
bot concludes a command was accepted because no refusal arrived.

The node this reads is **not from the game client**: the macOS host appends it
to the tree it emits, which is why its type name says so in full. It carries no
display region, so it is invisible to every other parser in this module, and its
text sits under `text` rather than `_setText`/`_text` so `getDisplayText` cannot
reach it and mistake a logged line for something rendered on screen.

Scoped to the reading by the host, which drains its queue as it builds the tree:
these are the lines written since the previous read, not a growing buffer that
would have a bot answering a refusal from four minutes ago.

-}
parseGameLogEntriesSinceLastReadingFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe (List GameLogEntry)
parseGameLogEntriesSinceLastReadingFromUITreeRoot uiTreeRoot =
    uiTreeRoot.uiNode.children
        |> Maybe.withDefault []
        |> List.map EveOnline.MemoryReading.unwrapUITreeNodeChild
        |> List.filter (.pythonObjectTypeName >> (==) syntheticGameLogNodeTypeName)
        |> List.head
        |> Maybe.map
            (\gameLogNode ->
                gameLogNode.children
                    |> Maybe.withDefault []
                    |> List.map EveOnline.MemoryReading.unwrapUITreeNodeChild
                    |> List.filterMap parseGameLogEntry
            )


syntheticGameLogNodeTypeName : String
syntheticGameLogNodeTypeName =
    "MacOsHostSyntheticGameLog"


parseGameLogEntry : EveOnline.MemoryReading.UITreeNode -> Maybe GameLogEntry
parseGameLogEntry entryNode =
    case getStringPropertyFromDictEntries "text" entryNode of
        Nothing ->
            Nothing

        Just text ->
            Just
                { timestamp = getStringPropertyFromDictEntries "timestamp" entryNode
                , channel = getStringPropertyFromDictEntries "channel" entryNode
                , text = text
                }


{-| How much damage the client's own combat log says arrived since the last
reading, as carried by the macOS host in this fork.

`damage` is the total in hitpoints, `hits` the number of shots that landed
(misses cost nothing and are not counted), and `topAttacker` whichever name did
the most of it -- enough for a decision to say what is shooting without carrying
a list of shots.

**This is the one instrument here that does not go through the ship's HUD.**
`ShipUI.hitpointsPercent` is a float read out of a gauge widget in live memory,
and it is not reliably true: across eight recorded runs it produced -1021821%,
2132822% and 8362% among others, always for exactly one reading and always
surrounded by sane values, which is what a read landing on a reallocated object
looks like. A number the client states outright cannot fail that way.

`Nothing` and `Just { damage = 0, ... }` are different answers and must stay so,
for the same reason they are for `gameLogEntriesSinceLastReading`. `Nothing` is
a host that does not carry this at all -- BotLab.exe, or this fork's host run
with `--no-game-log` -- and reading it as "no damage taken" is how a bot
concludes it is safe because nothing is listening.

The node this reads is **not from the game client**: the macOS host appends it
to the tree it emits, which is why its type name says so in full. It carries no
display region, so no other parser in this module can reach it, and its values
sit under plain keys rather than `_setText`/`_text` so `getDisplayText` cannot
mistake them for something rendered on screen.

Scoped to the reading by the host, which drains its queue as it builds the tree,
so this is the fire taken since the previous read rather than a running total.

-}
type alias IncomingDamage =
    { damage : Int
    , hits : Int
    , topAttacker : Maybe String
    }


parseIncomingDamageSinceLastReadingFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe IncomingDamage
parseIncomingDamageSinceLastReadingFromUITreeRoot uiTreeRoot =
    uiTreeRoot.uiNode.children
        |> Maybe.withDefault []
        |> List.map EveOnline.MemoryReading.unwrapUITreeNodeChild
        |> List.filter (.pythonObjectTypeName >> (==) syntheticIncomingDamageNodeTypeName)
        |> List.head
        |> Maybe.map
            (\damageNode ->
                { damage = damageNode |> getIntPropertyFromDictEntries "damage" |> Maybe.withDefault 0
                , hits = damageNode |> getIntPropertyFromDictEntries "hits" |> Maybe.withDefault 0
                , topAttacker = getStringPropertyFromDictEntries "topAttacker" damageNode
                }
            )


syntheticIncomingDamageNodeTypeName : String
syntheticIncomingDamageNodeTypeName =
    "MacOsHostSyntheticIncomingDamage"


getIntPropertyFromDictEntries : String -> EveOnline.MemoryReading.UITreeNode -> Maybe Int
getIntPropertyFromDictEntries dictEntryKey node =
    node.dictEntriesOfInterest
        |> Dict.get dictEntryKey
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.int >> Result.toMaybe)


{-| What this ship's own shots achieved since the last reading, per target, as
carried by the macOS host in this fork.

`hits` counts the shots that **landed** on that target -- a miss carries no
damage number in the client's log and is not counted -- and `damage` is what
those hits took off it. So `hits = 12, damage = 0` is the client stating that
twelve shots connected with an object and achieved nothing, which is a fact
about that object that no other reading in this system reports.

**Issue #90.** Run 27 locked an `Infested Asteroid` and shot it for roughly 290
consecutive readings, every shot landing for zero, while nine real rats sat on
the same overview untouched and the mission objective was already finished. The
bot could not see it: the host summed the _incoming_ half of the combat channel
for #32 and matched the outgoing half nowhere, so no field in any reading said
how much damage this ship was dealing.

**Per target rather than one total**, unlike `IncomingDamage`, because the
question is about one object. Guns and drones engage different things in the
same reading -- run 27's drones were landing real damage on a rat in the very
readings its guns were achieving nothing on the asteroid -- so a single sum
would have read as healthy throughout the incident this exists for.

`Nothing` and `Just []` are different answers, and the fail-safe direction here
is the **opposite** of the retreat's. `Just []` is "the client reported no shot
landing this reading"; `Nothing` is "this host does not carry the channel", and
a bot that read the second as evidence would conclude every target is immune on
a host that simply has no game log. Absent means unknown, and unknown must keep
shooting.

The node this reads is **not from the game client**: the macOS host appends it
to the tree it emits, which is why its type name says so in full. It carries no
display region, so no other parser in this module can reach it, and its values
sit under plain keys rather than `_setText`/`_text` so `getDisplayText` cannot
mistake a target's name for something rendered on screen.

Scoped to the reading by the host, which drains its queue as it builds the tree,
so this is what the shots since the previous read achieved rather than a running
total.

**`hits` and `misses` are separate counts and summing them is the one mistake to
avoid here.** A landed shot for zero damage says the guns cannot hurt this
object; a miss says they cannot hit it, which is a range or tracking problem and
resolves on its own. Issue #267 measured the difference rather than assuming it:
across 5,631 episodes in the client's own logs, no target that ever landed a
shot for zero was hurt afterwards, while targets the guns went on to kill
absorbed runs of up to 702 consecutive misses first. So a rule may read both,
and no rule may treat one as the other.

`misses` defaults to zero rather than to `Nothing`, which is the one place this
record takes a default instead of reporting absence. A host older than #267
writes no such key, and reading that as "no shots missed" is exactly the
behaviour those hosts already had -- so the default degrades to the previous
rule rather than inventing evidence. The distinction that must not be lost, "is
this channel here at all", is carried by the `Maybe` around the whole list and
is untouched.

-}
type alias OutgoingDamageToTarget =
    { name : String
    , hits : Int
    , damage : Int
    , misses : Int
    }


parseOutgoingDamageSinceLastReadingFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe (List OutgoingDamageToTarget)
parseOutgoingDamageSinceLastReadingFromUITreeRoot uiTreeRoot =
    uiTreeRoot.uiNode.children
        |> Maybe.withDefault []
        |> List.map EveOnline.MemoryReading.unwrapUITreeNodeChild
        |> List.filter (.pythonObjectTypeName >> (==) syntheticOutgoingDamageNodeTypeName)
        |> List.head
        |> Maybe.map
            (\outgoingDamageNode ->
                outgoingDamageNode.children
                    |> Maybe.withDefault []
                    |> List.map EveOnline.MemoryReading.unwrapUITreeNodeChild
                    |> List.filterMap parseOutgoingDamageToTarget
            )


parseOutgoingDamageToTarget : EveOnline.MemoryReading.UITreeNode -> Maybe OutgoingDamageToTarget
parseOutgoingDamageToTarget targetNode =
    case getStringPropertyFromDictEntries "name" targetNode of
        Nothing ->
            Nothing

        Just name ->
            Just
                { name = name
                , hits = targetNode |> getIntPropertyFromDictEntries "hits" |> Maybe.withDefault 0
                , damage = targetNode |> getIntPropertyFromDictEntries "damage" |> Maybe.withDefault 0
                , misses = targetNode |> getIntPropertyFromDictEntries "misses" |> Maybe.withDefault 0
                }


syntheticOutgoingDamageNodeTypeName : String
syntheticOutgoingDamageNodeTypeName =
    "MacOsHostSyntheticOutgoingDamage"


asUITreeNodeWithDisplayRegion :
    { selfDisplayRegion : DisplayRegion, totalDisplayRegion : DisplayRegion, occludedRegions : List DisplayRegion }
    -> EveOnline.MemoryReading.UITreeNode
    -> UITreeNodeWithDisplayRegion
asUITreeNodeWithDisplayRegion { selfDisplayRegion, totalDisplayRegion, occludedRegions } uiNode =
    { uiNode = uiNode
    , children =
        uiNode.children
            |> Maybe.map
                (List.foldl
                    (\currentChild mappedSiblings ->
                        let
                            occludingSiblingsRegions =
                                mappedSiblings
                                    |> List.filterMap justCaseWithDisplayRegion
                                    |> List.filter (.uiNode >> typeOccludesFollowingSiblingNodes)
                                    |> List.map .totalDisplayRegion
                        in
                        (currentChild
                            |> EveOnline.MemoryReading.unwrapUITreeNodeChild
                            |> asUITreeNodeWithInheritedOffset
                                { x = totalDisplayRegion.x, y = totalDisplayRegion.y }
                                { occludedRegions = occludedRegions ++ occludingSiblingsRegions }
                        )
                            :: mappedSiblings
                    )
                    []
                    >> List.reverse
                )
    , selfDisplayRegion = selfDisplayRegion
    , totalDisplayRegion = totalDisplayRegion
    , totalDisplayRegionVisible =
        subtractRegionsFromRegion { minuend = totalDisplayRegion, subtrahend = occludedRegions }
            |> List.sortBy (areaFromDisplayRegion >> Maybe.withDefault -1 >> negate)
            |> List.head
            |> Maybe.withDefault { x = -1, y = -1, width = 0, height = 0 }
    }


asUITreeNodeWithInheritedOffset :
    { x : Int, y : Int }
    -> { occludedRegions : List DisplayRegion }
    -> EveOnline.MemoryReading.UITreeNode
    -> ChildOfNodeWithDisplayRegion
asUITreeNodeWithInheritedOffset inheritedOffset { occludedRegions } rawNode =
    case rawNode |> getDisplayRegionFromDictEntries of
        Nothing ->
            ChildWithoutRegion rawNode

        Just selfRegion ->
            ChildWithRegion
                (asUITreeNodeWithDisplayRegion
                    { selfDisplayRegion = selfRegion
                    , totalDisplayRegion =
                        { selfRegion | x = inheritedOffset.x + selfRegion.x, y = inheritedOffset.y + selfRegion.y }
                    , occludedRegions = occludedRegions
                    }
                    rawNode
                )


getDisplayRegionFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe DisplayRegion
getDisplayRegionFromDictEntries uiNode =
    let
        fixedNumberFromJsonValue =
            Json.Decode.decodeValue
                (Json.Decode.oneOf
                    [ jsonDecodeIntFromIntOrString
                    , Json.Decode.field "int_low32" jsonDecodeIntFromIntOrString
                    ]
                )

        fixedNumberFromPropertyName propertyName =
            uiNode.dictEntriesOfInterest
                |> Dict.get propertyName
                |> Maybe.andThen (fixedNumberFromJsonValue >> Result.toMaybe)
    in
    case
        ( ( fixedNumberFromPropertyName "_displayX", fixedNumberFromPropertyName "_displayY" )
        , ( fixedNumberFromPropertyName "_displayWidth", fixedNumberFromPropertyName "_displayHeight" )
        )
    of
        ( ( Just displayX, Just displayY ), ( Just displayWidth, Just displayHeight ) ) ->
            Just { x = displayX, y = displayY, width = displayWidth, height = displayHeight }

        _ ->
            Nothing


parseContextMenusFromUITreeRoot : UITreeNodeWithDisplayRegion -> List ContextMenu
parseContextMenusFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listChildrenWithDisplayRegion
            |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map String.toLower >> (==) (Just "l_menu"))
            |> List.head
    of
        Nothing ->
            []

        Just layerMenu ->
            layerMenu
                |> listChildrenWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "menu")
                |> List.map parseContextMenu


parseInfoPanelContainerFromUIRoot : UITreeNodeWithDisplayRegion -> Maybe InfoPanelContainer
parseInfoPanelContainerFromUIRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoPanelContainer")
            |> List.sortBy (.uiNode >> EveOnline.MemoryReading.countDescendantsInUITreeNode >> negate)
            |> List.head
    of
        Nothing ->
            Nothing

        Just containerNode ->
            Just
                { uiNode = containerNode
                , icons = parseInfoPanelIconsFromInfoPanelContainer containerNode
                , infoPanelLocationInfo = parseInfoPanelLocationInfoFromInfoPanelContainer containerNode
                , infoPanelRoute = parseInfoPanelRouteFromInfoPanelContainer containerNode
                , infoPanelAgentMissions = parseInfoPanelAgentMissionsFromInfoPanelContainer containerNode
                }


parseInfoPanelIconsFromInfoPanelContainer : UITreeNodeWithDisplayRegion -> Maybe InfoPanelIcons
parseInfoPanelIconsFromInfoPanelContainer infoPanelContainerNode =
    case
        infoPanelContainerNode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "iconCont") >> Maybe.withDefault False)
            |> List.sortBy (.totalDisplayRegion >> .y)
            |> List.head
    of
        Nothing ->
            Nothing

        Just iconContainerNode ->
            let
                iconNodeFromTexturePathEnd texturePathEnd =
                    iconContainerNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter
                            (.uiNode
                                >> getTexturePathFromDictEntries
                                >> Maybe.map (String.endsWith texturePathEnd)
                                >> Maybe.withDefault False
                            )
                        |> List.head
            in
            Just
                { uiNode = iconContainerNode
                , search = iconNodeFromTexturePathEnd "search.png"
                , locationInfo = iconNodeFromTexturePathEnd "LocationInfo.png"
                , route = iconNodeFromTexturePathEnd "Route.png"
                , agentMissions = iconNodeFromTexturePathEnd "Missions.png"
                , dailyChallenge = iconNodeFromTexturePathEnd "dailyChallenge.png"
                }


parseInfoPanelLocationInfoFromInfoPanelContainer : UITreeNodeWithDisplayRegion -> Maybe InfoPanelLocationInfo
parseInfoPanelLocationInfoFromInfoPanelContainer infoPanelContainerNode =
    case
        infoPanelContainerNode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoPanelLocationInfo")
            |> List.head
    of
        Nothing ->
            Nothing

        Just infoPanelNode ->
            let
                securityStatusPercent =
                    infoPanelNode.uiNode
                        |> getAllContainedDisplayTexts
                        |> List.filterMap parseSecurityStatusPercentFromUINodeText
                        |> List.head

                currentSolarSystemName =
                    infoPanelNode.uiNode
                        |> getAllContainedDisplayTexts
                        |> List.filterMap parseCurrentSolarSystemFromUINodeText
                        |> List.head
                        |> Maybe.map String.trim

                maybeListSurroundingsButton =
                    infoPanelNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ListSurroundingsBtn")
                        |> List.head

                expandedContent =
                    infoPanelNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter
                            (\uiNode ->
                                (uiNode.uiNode.pythonObjectTypeName |> String.contains "Container")
                                    && (uiNode.uiNode |> getNameFromDictEntries |> Maybe.withDefault "" |> String.contains "mainCont")
                            )
                        |> List.head
                        |> Maybe.map
                            (\expandedContainer ->
                                { currentStationName =
                                    expandedContainer.uiNode
                                        |> getAllContainedDisplayTexts
                                        |> List.filterMap parseCurrentStationNameFromInfoPanelLocationInfoLabelText
                                        |> List.head
                                }
                            )
            in
            maybeListSurroundingsButton
                |> Maybe.map
                    (\listSurroundingsButton ->
                        { uiNode = infoPanelNode
                        , listSurroundingsButton = listSurroundingsButton
                        , currentSolarSystemName = currentSolarSystemName
                        , securityStatusPercent = securityStatusPercent
                        , expandedContent = expandedContent
                        }
                    )


parseSecurityStatusPercentFromUINodeText : String -> Maybe Int
parseSecurityStatusPercentFromUINodeText =
    Maybe.Extra.oneOf
        [ getSubstringBetweenXmlTagsAfterMarker "hint='Security status'"
        , getSubstringBetweenXmlTagsAfterMarker "hint=\"Security status\"><color="
        ]
        >> Maybe.andThen (String.trim >> String.toFloat)
        >> Maybe.map ((*) 100 >> round)


parseCurrentSolarSystemFromUINodeText : String -> Maybe String
parseCurrentSolarSystemFromUINodeText =
    Maybe.Extra.oneOf
        [ getSubstringBetweenXmlTagsAfterMarker "alt='Current Solar System'"
        , getSubstringBetweenXmlTagsAfterMarker "alt=\"Current Solar System\""
        ]


parseCurrentStationNameFromInfoPanelLocationInfoLabelText : String -> Maybe String
parseCurrentStationNameFromInfoPanelLocationInfoLabelText =
    getSubstringBetweenXmlTagsAfterMarker "alt='Current Station'"
        >> Maybe.map String.trim


parseInfoPanelRouteFromInfoPanelContainer : UITreeNodeWithDisplayRegion -> Maybe InfoPanelRoute
parseInfoPanelRouteFromInfoPanelContainer infoPanelContainerNode =
    case
        infoPanelContainerNode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoPanelRoute")
            |> List.head
    of
        Nothing ->
            Nothing

        Just infoPanelRouteNode ->
            let
                routeElementMarker =
                    infoPanelRouteNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "AutopilotDestinationIcon")
                        |> List.map
                            (\uiNode ->
                                { uiNode = uiNode
                                , numJumps = uiNode.uiNode |> getIntPropertyFromDictEntries "numJumps"
                                }
                            )
            in
            Just { uiNode = infoPanelRouteNode, routeElementMarker = routeElementMarker }


parseInfoPanelAgentMissionsFromInfoPanelContainer : UITreeNodeWithDisplayRegion -> Maybe InfoPanelAgentMissions
parseInfoPanelAgentMissionsFromInfoPanelContainer infoPanelContainerNode =
    case
        infoPanelContainerNode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoPanelAgentMissions")
            |> List.head
    of
        Nothing ->
            Nothing

        Just infoPanelNode ->
            let
                entries =
                    infoPanelNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "MissionEntry")
                        |> List.map (\uiNode -> { uiNode = uiNode })
            in
            Just
                { uiNode = infoPanelNode
                , entries = entries
                }


parseContextMenu : UITreeNodeWithDisplayRegion -> ContextMenu
parseContextMenu contextMenuUINode =
    let
        entriesUINodes =
            contextMenuUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "menuentry")

        entries =
            entriesUINodes
                |> List.map
                    (\entryUINode ->
                        let
                            text =
                                entryUINode
                                    |> listDescendantsWithDisplayRegion
                                    |> List.filterMap (.uiNode >> getDisplayText)
                                    |> List.sortBy (String.length >> negate)
                                    |> List.head
                                    |> Maybe.withDefault ""
                        in
                        { text = text
                        , uiNode = entryUINode
                        }
                    )
                |> List.sortBy (.uiNode >> .totalDisplayRegion >> .y)
    in
    { uiNode = contextMenuUINode
    , entries = entries
    }


parseShipUIFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe ShipUI
parseShipUIFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ShipUI")
            |> List.head
    of
        Nothing ->
            Nothing

        Just shipUINode ->
            case
                shipUINode
                    |> listDescendantsWithDisplayRegion
                    |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "CapacitorContainer")
                    |> List.head
            of
                Nothing ->
                    Nothing

                Just capacitorUINode ->
                    let
                        descendantNodesFromPythonObjectTypeNameEqual pythonObjectTypeName =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) pythonObjectTypeName)

                        capacitor =
                            capacitorUINode |> parseShipUICapacitorFromUINode

                        {-
                           speedGaugeElement =
                               shipUINode
                                   |> listDescendantsWithDisplayRegion
                                   |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SpeedGauge")
                                   |> List.head
                        -}
                        maybeIndicationNode =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.toLower >> String.contains "indicationcontainer") >> Maybe.withDefault False)
                                |> List.head

                        indication =
                            maybeIndicationNode
                                |> Maybe.map (parseShipUIIndication >> Just)
                                |> Maybe.withDefault Nothing

                        moduleButtons =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ShipSlot")
                                |> List.filterMap
                                    (\slotNode ->
                                        slotNode
                                            |> listDescendantsWithDisplayRegion
                                            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ModuleButton")
                                            |> List.head
                                            |> Maybe.map
                                                (\moduleButtonNode ->
                                                    parseShipUIModuleButton { slotNode = slotNode, moduleButtonNode = moduleButtonNode }
                                                )
                                    )

                        getLastValuePercentFromGaugeName gaugeName =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) gaugeName) >> Maybe.withDefault False)
                                |> List.head
                                |> Maybe.andThen (.uiNode >> .dictEntriesOfInterest >> Dict.get "_lastValue")
                                |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)
                                |> Maybe.map ((*) 100 >> round)

                        maybeHitpointsPercent =
                            case ( getLastValuePercentFromGaugeName "structureGauge", getLastValuePercentFromGaugeName "armorGauge", getLastValuePercentFromGaugeName "shieldGauge" ) of
                                ( Just structure, Just armor, Just shield ) ->
                                    Just { structure = structure, armor = armor, shield = shield }

                                _ ->
                                    Nothing

                        offensiveBuffButtonNames =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "OffensiveBuffButton")
                                |> List.filterMap (.uiNode >> getNameFromDictEntries)

                        squadronsUI =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SquadronsUI")
                                |> List.head
                                |> Maybe.map parseSquadronsUI

                        heatGauges =
                            shipUINode
                                |> listDescendantsWithDisplayRegion
                                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "HeatGauges")
                                |> List.head
                                |> Maybe.map parseShipUIHeatGaugesFromUINode
                    in
                    maybeHitpointsPercent
                        |> Maybe.map
                            (\hitpointsPercent ->
                                { uiNode = shipUINode
                                , capacitor = capacitor
                                , hitpointsPercent = hitpointsPercent
                                , indication = indication
                                , moduleButtons = moduleButtons
                                , moduleButtonsRows = groupShipUIModulesIntoRows capacitor moduleButtons
                                , offensiveBuffButtonNames = offensiveBuffButtonNames
                                , squadronsUI = squadronsUI
                                , stopButton = descendantNodesFromPythonObjectTypeNameEqual "StopButton" |> List.head
                                , maxSpeedButton = descendantNodesFromPythonObjectTypeNameEqual "MaxSpeedButton" |> List.head
                                , heatGauges = heatGauges
                                }
                            )


parseShipUIModuleButton : { slotNode : UITreeNodeWithDisplayRegion, moduleButtonNode : UITreeNodeWithDisplayRegion } -> ShipUIModuleButton
parseShipUIModuleButton { slotNode, moduleButtonNode } =
    let
        rotationFloatFromRampName rampName =
            slotNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just rampName))
                |> List.filterMap (.uiNode >> getRotationFloatFromDictEntries)
                |> List.head

        rampRotationMilli =
            case ( rotationFloatFromRampName "leftRamp", rotationFloatFromRampName "rightRamp" ) of
                ( Just leftRampRotationFloat, Just rightRampRotationFloat ) ->
                    if
                        (leftRampRotationFloat < 0 || pi * 2.01 < leftRampRotationFloat)
                            || (rightRampRotationFloat < 0 || pi * 2.01 < rightRampRotationFloat)
                    then
                        Nothing

                    else
                        Just (max 0 (min 1000 (round (1000 - ((leftRampRotationFloat + rightRampRotationFloat) * 500) / pi))))

                _ ->
                    Nothing
    in
    { uiNode = moduleButtonNode
    , slotUINode = slotNode
    , isActive =
        moduleButtonNode.uiNode.dictEntriesOfInterest
            |> Dict.get "ramp_active"
            |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
    , isHiliteVisible =
        slotNode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "Sprite")
            |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just "hilite"))
            |> List.isEmpty
            |> not
    , rampRotationMilli = rampRotationMilli
    , stateFromDictEntries = parseShipUIModuleButtonState moduleButtonNode.uiNode
    }


{-| What a module button says about **itself**, straight out of its own
`dictEntriesOfInterest`.

The module-state fields above this one all read the slot's sprites, and #35
walked a top-row button's whole subtree to see which sprites are there. One is:
`underlay`. There is no `hilite` and no `busy` on this build, so
`isHiliteVisible` and `isBusy` cannot be anything but `False` however the module
behaves. That much of the note in CLAUDE.md was right. The conclusion drawn from
it -- that this client does not expose the state -- was not: the state is on the
button itself, as twelve dict entries nothing had ever read.

**`ramp_active` is a duty cycle, not an on/off state.** That is the correction
that matters most here, and it is measured rather than argued: 92 read-only
samples over 240s of run 9 caught the weapon's `ramp_active` flipping fourteen
times while `isInActiveState` stayed `True` throughout -- the gun never switched
off. The `False` half of that oscillation is the gap between cycles. `isActive`
reads this entry and reports it as "running", and #34 is what that costs: a
counter gated on "no gun reads as firing" resets inside every cycle, and a wait
for "the ramp to stop" is satisfied by the gap rather than by the guns going
quiet.

**Absent and `False` are different facts.** For the first ~60s of that sample no
module carried `ramp_active` at all -- not `False`, missing -- and it appeared
per module as each one first cycled. `waitingForActiveTarget` did the same later,
absent until 141s and then `0` on all four modules at once. So every field here
is a `Maybe`, and an entry that does not decode stays `Nothing` rather than
becoming a guessed `False`: only one of those two answers is safe to act on.

**Nothing decides anything from these.** The meanings above come from one 240s
window on one fit, and the leg #34 actually needed has no observations at all:
`isDeactivating` -- named for exactly the state that wait cared about -- was
never once `True`, because nothing switched a module off while the sampler ran.
`effect_activating` was seen pulsing `1` exactly once, 2.6s before a cycle
began. So these are parsed to be logged and read back, and `isActive`, `isBusy`
and `isHiliteVisible` keep the meanings they had.

Both decoders accept either JSON shape. This build sends booleans for
`ramp_active` and its neighbours and plain numbers for `waitingForActiveTarget`
and the rest, but one that sent `true` where this one sends `1` would otherwise
turn a field silently into `Nothing` -- which is the same "the signal is dead"
reading this whole issue is about.

The field names are the client's own keys, unchanged, so that a value in the log
and a value in the tree are the same name and no translation table has to be
right. Reading them costs twelve dictionary lookups on a node the caller already
holds -- no traversal, which each sprite field above does do. That is why this
takes the bare `UITreeNode` and not the node with its display region: it has
nothing to walk with.

-}
type alias ShipUIModuleButtonState =
    { ramp_active : Maybe Bool
    , isInActiveState : Maybe Bool
    , isDeactivating : Maybe Bool
    , effect_activating : Maybe Int
    , online : Maybe Bool
    , blinking : Maybe Bool
    , grey : Maybe Bool
    , quantity : Maybe Int
    , autoreload : Maybe Int
    , autorepeat : Maybe Int
    , isMaster : Maybe Bool
    , waitingForActiveTarget : Maybe Int
    }


parseShipUIModuleButtonState : EveOnline.MemoryReading.UITreeNode -> ShipUIModuleButtonState
parseShipUIModuleButtonState moduleButtonNode =
    let
        flag dictEntryKey =
            getModuleButtonStateFlagFromDictEntries dictEntryKey moduleButtonNode

        number dictEntryKey =
            getModuleButtonStateNumberFromDictEntries dictEntryKey moduleButtonNode
    in
    { ramp_active = flag "ramp_active"
    , isInActiveState = flag "isInActiveState"
    , isDeactivating = flag "isDeactivating"
    , effect_activating = number "effect_activating"
    , online = flag "online"
    , blinking = flag "blinking"
    , grey = flag "grey"
    , quantity = number "quantity"
    , autoreload = number "autoreload"
    , autorepeat = number "autorepeat"
    , isMaster = flag "isMaster"
    , waitingForActiveTarget = number "waitingForActiveTarget"
    }


getModuleButtonStateFlagFromDictEntries : String -> EveOnline.MemoryReading.UITreeNode -> Maybe Bool
getModuleButtonStateFlagFromDictEntries dictEntryKey uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get dictEntryKey
        |> Maybe.andThen (Json.Decode.decodeValue jsonDecodeBoolFromBoolOrInt >> Result.toMaybe)


getModuleButtonStateNumberFromDictEntries : String -> EveOnline.MemoryReading.UITreeNode -> Maybe Int
getModuleButtonStateNumberFromDictEntries dictEntryKey uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get dictEntryKey
        |> Maybe.andThen (Json.Decode.decodeValue jsonDecodeIntFromIntOrBool >> Result.toMaybe)


jsonDecodeBoolFromBoolOrInt : Json.Decode.Decoder Bool
jsonDecodeBoolFromBoolOrInt =
    Json.Decode.oneOf
        [ Json.Decode.bool
        , Json.Decode.int |> Json.Decode.map ((/=) 0)
        ]


jsonDecodeIntFromIntOrBool : Json.Decode.Decoder Int
jsonDecodeIntFromIntOrBool =
    Json.Decode.oneOf
        [ Json.Decode.int
        , Json.Decode.bool
            |> Json.Decode.map
                (\asBool ->
                    if asBool then
                        1

                    else
                        0
                )
        ]


parseShipUICapacitorFromUINode : UITreeNodeWithDisplayRegion -> ShipUICapacitor
parseShipUICapacitorFromUINode capacitorUINode =
    let
        pmarks =
            capacitorUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "pmark") >> Maybe.withDefault False)
                |> List.map
                    (\pmarkUINode ->
                        { uiNode = pmarkUINode
                        , colorPercent = pmarkUINode.uiNode |> getColorPercentFromDictEntries
                        }
                    )

        maybePmarksFills =
            pmarks
                |> List.map (.colorPercent >> Maybe.map (\colorPercent -> colorPercent.a < 20))
                |> Maybe.Extra.combine

        levelFromPmarksPercent =
            maybePmarksFills
                |> Maybe.andThen
                    (\pmarksFills ->
                        if (pmarksFills |> List.length) < 1 then
                            Nothing

                        else
                            Just (((pmarksFills |> List.filter identity |> List.length) * 100) // (pmarksFills |> List.length))
                    )
    in
    { uiNode = capacitorUINode
    , pmarks = pmarks
    , levelFromPmarksPercent = levelFromPmarksPercent
    }


parseShipUIHeatGaugesFromUINode : UITreeNodeWithDisplayRegion -> ShipUIHeatGauges
parseShipUIHeatGaugesFromUINode gaugesUINode =
    let
        heatGaugesRotationZeroValues =
            [ -213, -108, -3 ]

        heatValuePercentFromRotationPercent rotationPercent =
            heatGaugesRotationZeroValues
                |> List.map
                    (\gaugeRotationZero ->
                        if rotationPercent <= gaugeRotationZero && gaugeRotationZero - 100 <= rotationPercent then
                            Just -(rotationPercent - gaugeRotationZero)

                        else
                            Nothing
                    )
                |> List.filterMap identity
                |> List.head

        gauges =
            gaugesUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "heatGauge") >> Maybe.withDefault False)
                |> List.map
                    (\gaugeUiNode ->
                        let
                            rotationPercent =
                                gaugeUiNode.uiNode
                                    |> getRotationFloatFromDictEntries
                                    |> Maybe.map ((*) 100 >> round)
                        in
                        { uiNode = gaugeUiNode
                        , rotationPercent = rotationPercent
                        , heatPercent = rotationPercent |> Maybe.andThen heatValuePercentFromRotationPercent
                        }
                    )
    in
    { uiNode = gaugesUINode
    , gauges = gauges
    }


groupShipUIModulesIntoRows :
    ShipUICapacitor
    -> List ShipUIModuleButton
    -> { top : List ShipUIModuleButton, middle : List ShipUIModuleButton, bottom : List ShipUIModuleButton }
groupShipUIModulesIntoRows capacitor modules =
    let
        verticalDistanceThreshold =
            20

        verticalCenterOfUINode uiNode =
            uiNode.totalDisplayRegion.y + uiNode.totalDisplayRegion.height // 2

        capacitorVerticalCenter =
            verticalCenterOfUINode capacitor.uiNode
    in
    modules
        |> List.foldr
            (\shipModule previousRows ->
                if verticalCenterOfUINode shipModule.uiNode < capacitorVerticalCenter - verticalDistanceThreshold then
                    { previousRows | top = shipModule :: previousRows.top }

                else if verticalCenterOfUINode shipModule.uiNode > capacitorVerticalCenter + verticalDistanceThreshold then
                    { previousRows | bottom = shipModule :: previousRows.bottom }

                else
                    { previousRows | middle = shipModule :: previousRows.middle }
            )
            { top = [], middle = [], bottom = [] }


parseShipUIIndication : UITreeNodeWithDisplayRegion -> ShipUIIndication
parseShipUIIndication indicationUINode =
    let
        displayTexts =
            indicationUINode.uiNode |> getAllContainedDisplayTexts

        maneuverType =
            [ ( "Warp", ManeuverWarp )
            , ( "Jump", ManeuverJump )
            , ( "Orbit", ManeuverOrbit )
            , ( "Approach", ManeuverApproach )

            -- Sample `session-2022-05-23T23-00-32-87ba97.zip` shared by Abaddon at https://forum.botlab.org/t/i-want-to-add-korean-support-on-eve-online-bot-what-should-i-do/4370/9
            , ( "워프 드라이브 가동", ManeuverWarp )

            -- Sample `session-2022-05-26T03-13-42-83df2b.zip` shared by Abaddon at https://forum.botlab.org/t/i-want-to-add-korean-support-on-eve-online-bot-what-should-i-do/4370/14
            , ( "점프 중", ManeuverJump )
            ]
                |> List.filterMap
                    (\( pattern, candidateManeuverType ) ->
                        if displayTexts |> List.any (String.contains pattern) then
                            Just candidateManeuverType

                        else
                            Nothing
                    )
                |> List.head
    in
    { uiNode = indicationUINode, maneuverType = maneuverType }


parseSquadronsUI : UITreeNodeWithDisplayRegion -> SquadronsUI
parseSquadronsUI squadronsUINode =
    { uiNode = squadronsUINode
    , squadrons =
        squadronsUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SquadronUI")
            |> List.map parseSquadronUI
    }


parseSquadronUI : UITreeNodeWithDisplayRegion -> SquadronUI
parseSquadronUI squadronUINode =
    { uiNode = squadronUINode
    , abilities =
        squadronUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "AbilityIcon")
            |> List.map parseSquadronAbilityIcon
    , actionLabel =
        squadronUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SquadronActionLabel")
            |> List.head
    }


parseSquadronAbilityIcon : UITreeNodeWithDisplayRegion -> SquadronAbilityIcon
parseSquadronAbilityIcon abilityIconUINode =
    { uiNode = abilityIconUINode
    , quantity =
        abilityIconUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.toLower >> String.contains "quantity") >> Maybe.withDefault False)
            |> List.concatMap (.uiNode >> getAllContainedDisplayTexts)
            |> List.head
            |> Maybe.andThen (String.trim >> String.toInt)
    , ramp_active =
        abilityIconUINode.uiNode.dictEntriesOfInterest
            |> Dict.get "ramp_active"
            |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
    }


parseTargetsFromUITreeRoot : UITreeNodeWithDisplayRegion -> List Target
parseTargetsFromUITreeRoot =
    listDescendantsWithDisplayRegion
        >> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "TargetInBar")
        >> List.map parseTarget


parseTarget : UITreeNodeWithDisplayRegion -> Target
parseTarget targetNode =
    let
        textsTopToBottom =
            targetNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> .y)
                |> List.map Tuple.first

        barAndImageCont =
            targetNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just "barAndImageCont"))
                |> List.head

        isActiveTarget =
            targetNode.uiNode
                |> EveOnline.MemoryReading.listDescendantsInUITreeNode
                |> List.any (.pythonObjectTypeName >> (==) "ActiveTargetOnBracket")

        assignedContainerNode =
            targetNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.toLower >> String.contains "assigned") >> Maybe.withDefault False)
                |> List.sortBy (.totalDisplayRegion >> .width)
                |> List.head

        assignedIcons =
            assignedContainerNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (\uiNode -> [ "Sprite", "Icon" ] |> List.member uiNode.uiNode.pythonObjectTypeName)
    in
    { uiNode = targetNode
    , barAndImageCont = barAndImageCont
    , textsTopToBottom = textsTopToBottom
    , isActiveTarget = isActiveTarget
    , assignedContainerNode = assignedContainerNode
    , assignedIcons = assignedIcons
    }


parseOverviewWindowsFromUITreeRoot : UITreeNodeWithDisplayRegion -> List OverviewWindow
parseOverviewWindowsFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter
            (.uiNode
                >> .pythonObjectTypeName
                >> (List.member >> (|>) [ "OverView", "OverviewWindow", "OverviewWindowOld" ])
            )
        |> List.map parseOverviewWindow


parseOverviewWindow : UITreeNodeWithDisplayRegion -> OverviewWindow
parseOverviewWindow overviewWindowNode =
    let
        scrollNode =
            overviewWindowNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "scroll")
                |> List.head

        scrollControlsNode =
            scrollNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "ScrollControls")
                |> List.head

        headersContainerNode =
            scrollNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "headers")
                |> List.head

        entriesHeaders =
            headersContainerNode
                |> Maybe.map getAllContainedDisplayTextsWithRegion
                |> Maybe.withDefault []

        entries =
            overviewWindowNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "OverviewScrollEntry")
                |> List.map (parseOverviewWindowEntry entriesHeaders)
    in
    { uiNode = overviewWindowNode
    , entriesHeaders = entriesHeaders
    , entries = entries
    , scrollControls = scrollControlsNode |> Maybe.map parseScrollControls
    }


parseOverviewWindowEntry : List ( String, UITreeNodeWithDisplayRegion ) -> UITreeNodeWithDisplayRegion -> OverviewWindowEntry
parseOverviewWindowEntry entriesHeaders overviewEntryNode =
    let
        textsLeftToRight =
            overviewEntryNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> .x)
                |> List.map Tuple.first

        cellsTexts =
            overviewEntryNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.filterMap
                    (\( cellText, cell ) ->
                        let
                            cellMiddle =
                                cell.totalDisplayRegion.x + (cell.totalDisplayRegion.width // 2)

                            maybeHeader =
                                entriesHeaders
                                    |> List.filter
                                        (\( _, header ) ->
                                            header.totalDisplayRegion.x
                                                < cellMiddle
                                                + 1
                                                && cellMiddle
                                                < header.totalDisplayRegion.x
                                                + header.totalDisplayRegion.width
                                                - 1
                                        )
                                    |> List.head
                        in
                        maybeHeader
                            |> Maybe.map (\( headerText, _ ) -> ( headerText, cellText ))
                    )
                |> Dict.fromList

        objectDistance =
            cellsTexts
                |> Dict.get "Distance"

        objectDistanceInMeters =
            objectDistance
                |> Maybe.map parseOverviewEntryDistanceInMetersFromText
                |> Maybe.withDefault (Err "Did not find the 'Distance' cell text.")

        spaceObjectIconNode =
            overviewEntryNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SpaceObjectIcon")
                |> List.head

        iconSpriteColorPercent =
            spaceObjectIconNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just "iconSprite"))
                |> List.head
                |> Maybe.andThen (.uiNode >> getColorPercentFromDictEntries)

        namesUnderSpaceObjectIcon =
            spaceObjectIconNode
                |> Maybe.map (.uiNode >> EveOnline.MemoryReading.listDescendantsInUITreeNode)
                |> Maybe.withDefault []
                |> List.filterMap getNameFromDictEntries
                |> Set.fromList

        bgColorFillsPercent =
            overviewEntryNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "Fill")
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "bgColor") >> Maybe.withDefault False)
                |> List.filterMap (\fillUiNode -> fillUiNode.uiNode |> getColorPercentFromDictEntries)

        rightAlignedIconsHints =
            overviewEntryNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "rightAlignedIconContainer") >> Maybe.withDefault False)
                |> List.concatMap listDescendantsWithDisplayRegion
                |> List.filterMap (.uiNode >> getHintTextFromDictEntries)

        rightAlignedIconsHintsContainsTextIgnoringCase textToSearch =
            rightAlignedIconsHints |> List.any (String.toLower >> String.contains (textToSearch |> String.toLower))

        commonIndications =
            { targeting = namesUnderSpaceObjectIcon |> Set.member "targeting"
            , targetedByMe = namesUnderSpaceObjectIcon |> Set.member "targetedByMeIndicator"
            , isJammingMe = rightAlignedIconsHintsContainsTextIgnoringCase "is jamming me"
            , isWarpDisruptingMe = rightAlignedIconsHintsContainsTextIgnoringCase "is warp disrupting me"
            , isTrackingDisruptingMe = rightAlignedIconsHintsContainsTextIgnoringCase "is tracking disrupting me"
            , isSensorDampeningMe = rightAlignedIconsHintsContainsTextIgnoringCase "is sensor dampening me"
            }

        opacityPercent =
            overviewEntryNode.uiNode
                |> getOpacityFloatFromDictEntries
                |> Maybe.map ((*) 100 >> round)
    in
    { uiNode = overviewEntryNode
    , textsLeftToRight = textsLeftToRight
    , cellsTexts = cellsTexts
    , objectDistance = objectDistance
    , objectDistanceInMeters = objectDistanceInMeters
    , objectName = cellsTexts |> Dict.get "Name"
    , objectType = cellsTexts |> Dict.get "Type"
    , objectAlliance = cellsTexts |> Dict.get "Alliance"
    , iconSpriteColorPercent = iconSpriteColorPercent
    , namesUnderSpaceObjectIcon = namesUnderSpaceObjectIcon
    , bgColorFillsPercent = bgColorFillsPercent
    , rightAlignedIconsHints = rightAlignedIconsHints
    , commonIndications = commonIndications
    , opacityPercent = opacityPercent
    }


parseOverviewEntryDistanceInMetersFromText : String -> Result String Int
parseOverviewEntryDistanceInMetersFromText distanceDisplayTextBeforeTrim =
    case distanceDisplayTextBeforeTrim |> String.trim |> String.split " " |> List.reverse of
        unitText :: reversedNumberTexts ->
            case parseDistanceUnitInMeters unitText of
                Nothing ->
                    Err ("Failed to parse distance unit text of '" ++ unitText ++ "'")

                Just unitInMeters ->
                    case
                        reversedNumberTexts |> List.reverse |> String.join " " |> parseNumberTruncatingAfterOptionalDecimalSeparator
                    of
                        Err parseNumberError ->
                            Err ("Failed to parse number: " ++ parseNumberError)

                        Ok parsedNumber ->
                            Ok (parsedNumber * unitInMeters)

        _ ->
            Err "Expecting at least one whitespace character separating number and unit."


parseDistanceUnitInMeters : String -> Maybe Int
parseDistanceUnitInMeters unitText =
    case String.trim unitText of
        "m" ->
            Just 1

        "km" ->
            Just 1000

        _ ->
            Nothing


parseSelectedItemWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe SelectedItemWindow
parseSelectedItemWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        -- The macOS client names this window 'SelectedItemWnd'; 'ActiveItem' is
        -- the name the upstream parser was written against and matches nothing
        -- here, which read as "no panel" rather than as an error.
        |> List.filter
            (.uiNode
                >> .pythonObjectTypeName
                >> (\typeName -> List.member typeName [ "ActiveItem", "SelectedItemWnd" ])
            )
        |> List.head
        |> Maybe.map parseSelectedItemWindow


parseSelectedItemWindow : UITreeNodeWithDisplayRegion -> SelectedItemWindow
parseSelectedItemWindow windowNode =
    let
        actionButtonFromTexturePathEnding texturePathEnding =
            windowNode
                |> listDescendantsWithDisplayRegion
                |> List.filter
                    (.uiNode
                        >> getTexturePathFromDictEntries
                        >> Maybe.map (String.toLower >> String.endsWith (String.toLower texturePathEnding))
                        >> Maybe.withDefault False
                    )
                |> List.head

        orbitButton =
            actionButtonFromTexturePathEnding "44_32_21.png"
    in
    { uiNode = windowNode, orbitButton = orbitButton }


parseDronesWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe DronesWindow
parseDronesWindowFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter
                (.uiNode
                    >> .pythonObjectTypeName
                    >> (List.member >> (|>) [ "DroneView", "DronesWindow" ])
                )
            |> List.head
    of
        Nothing ->
            Nothing

        Just windowNode ->
            let
                {-
                   scrollNode =
                       windowNode
                           |> listDescendantsWithDisplayRegion
                           |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "scroll")
                           |> List.head
                -}
                droneGroupHeaders =
                    windowNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "DroneGroupHeader")
                        |> List.filterMap parseDronesWindowDroneGroupHeader

                droneEntries =
                    windowNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter
                            (.uiNode
                                >> .pythonObjectTypeName
                                >> (\pythonTypeName ->
                                        {-
                                           2023-01-02 Observed: 'DroneInBayEntry'
                                        -}
                                        String.startsWith "Drone" pythonTypeName
                                            && String.endsWith "Entry" pythonTypeName
                                   )
                            )
                        |> List.map parseDronesWindowDroneEntry

                droneGroups =
                    [ droneEntries |> List.map DronesWindowEntryDrone
                    , droneGroupHeaders
                        |> List.map (\header -> { header = header, children = [] })
                        |> List.map DronesWindowEntryGroup
                    ]
                        |> List.concat
                        |> dronesGroupTreesFromFlatListOfEntries

                droneGroupFromHeaderTextPart headerTextPart =
                    droneGroups
                        |> List.filter (.header >> .mainText >> Maybe.withDefault "" >> String.toLower >> String.contains (headerTextPart |> String.toLower))
                        |> List.sortBy (.header >> .mainText >> Maybe.map String.length >> Maybe.withDefault 999)
                        |> List.head
            in
            Just
                { uiNode = windowNode
                , droneGroups = droneGroups
                , droneGroupInBay = droneGroupFromHeaderTextPart "in bay"
                , droneGroupInSpace = droneGroupFromHeaderTextPart "in space"
                }


dronesGroupTreesFromFlatListOfEntries : List DronesWindowEntry -> List DronesWindowEntryGroupStructure
dronesGroupTreesFromFlatListOfEntries entriesBeforeOrdering =
    let
        verticalOffsetFromEntry entry =
            case entry of
                DronesWindowEntryDrone droneEntry ->
                    droneEntry.uiNode.totalDisplayRegion.y

                DronesWindowEntryGroup groupEntry ->
                    groupEntry.header.uiNode.totalDisplayRegion.y

        entriesOrderedVertically =
            entriesBeforeOrdering
                |> List.sortBy verticalOffsetFromEntry
    in
    entriesOrderedVertically
        |> List.filterMap
            (\entry ->
                case entry of
                    DronesWindowEntryDrone _ ->
                        Nothing

                    DronesWindowEntryGroup group ->
                        Just group
            )
        |> List.head
        |> Maybe.map
            (\topmostGroupEntry ->
                let
                    entriesUpToSibling =
                        entriesOrderedVertically
                            |> List.Extra.dropWhile
                                (verticalOffsetFromEntry
                                    >> (\offset -> offset <= verticalOffsetFromEntry (DronesWindowEntryGroup topmostGroupEntry))
                                )
                            |> List.Extra.takeWhile
                                (\entry ->
                                    case entry of
                                        DronesWindowEntryDrone _ ->
                                            True

                                        DronesWindowEntryGroup group ->
                                            topmostGroupEntry.header.uiNode.totalDisplayRegion.x
                                                < (group.header.uiNode.totalDisplayRegion.x - 3)
                                )

                    childGroupTrees =
                        dronesGroupTreesFromFlatListOfEntries entriesUpToSibling

                    childDrones =
                        entriesUpToSibling
                            |> List.Extra.takeWhile
                                (\entry ->
                                    case entry of
                                        DronesWindowEntryDrone _ ->
                                            True

                                        DronesWindowEntryGroup _ ->
                                            False
                                )

                    children =
                        [ childDrones, childGroupTrees |> List.map DronesWindowEntryGroup ]
                            |> List.concat
                            |> List.sortBy verticalOffsetFromEntry

                    topmostGroupTree =
                        { header = topmostGroupEntry.header
                        , children = children
                        }

                    bottommostDescendantOffset =
                        enumerateDescendantsOfDronesGroup topmostGroupTree
                            |> List.map verticalOffsetFromEntry
                            |> List.maximum
                            |> Maybe.withDefault (verticalOffsetFromEntry (DronesWindowEntryGroup topmostGroupTree))

                    entriesBelow =
                        entriesOrderedVertically
                            |> List.Extra.dropWhile (verticalOffsetFromEntry >> (\offset -> offset <= bottommostDescendantOffset))
                in
                topmostGroupTree :: dronesGroupTreesFromFlatListOfEntries entriesBelow
            )
        |> Maybe.withDefault []


enumerateAllDronesFromDronesGroup : DronesWindowEntryGroupStructure -> List DronesWindowEntryDroneStructure
enumerateAllDronesFromDronesGroup =
    enumerateDescendantsOfDronesGroup
        >> List.filterMap
            (\entry ->
                case entry of
                    DronesWindowEntryDrone drone ->
                        Just drone

                    DronesWindowEntryGroup _ ->
                        Nothing
            )


enumerateDescendantsOfDronesGroup : DronesWindowEntryGroupStructure -> List DronesWindowEntry
enumerateDescendantsOfDronesGroup group =
    group.children
        |> List.concatMap
            (\child ->
                case child of
                    DronesWindowEntryDrone _ ->
                        [ child ]

                    DronesWindowEntryGroup childGroup ->
                        child :: enumerateDescendantsOfDronesGroup childGroup
            )


parseDronesWindowDroneGroupHeader : UITreeNodeWithDisplayRegion -> Maybe DronesWindowDroneGroupHeader
parseDronesWindowDroneGroupHeader groupHeaderUiNode =
    case
        groupHeaderUiNode
            |> getAllContainedDisplayTextsWithRegion
            |> List.sortBy (Tuple.second >> .totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0)
            |> List.map Tuple.first
            |> List.head
    of
        Nothing ->
            Nothing

        Just mainText ->
            let
                quantityFromTitle =
                    mainText
                        |> parseQuantityFromDroneGroupTitleText
                        |> Result.withDefault Nothing
            in
            Just
                { uiNode = groupHeaderUiNode
                , mainText = Just mainText
                , quantityFromTitle = quantityFromTitle
                }


parseQuantityFromDroneGroupTitleText : String -> Result String (Maybe DronesWindowDroneGroupHeaderQuantity)
parseQuantityFromDroneGroupTitleText droneGroupTitleText =
    case droneGroupTitleText |> String.split "(" |> List.drop 1 of
        [] ->
            Ok Nothing

        [ textAfterOpeningParenthesis ] ->
            case textAfterOpeningParenthesis |> String.split ")" |> List.head of
                Nothing ->
                    Err "Missing closing parens"

                Just textInParens ->
                    case
                        textInParens
                            |> String.split "/"
                            |> List.map String.trim
                            |> List.map
                                (\numberText ->
                                    numberText
                                        |> String.toInt
                                        |> Result.fromMaybe ("Failed to parse to integer from '" ++ numberText ++ "'")
                                )
                            |> Result.Extra.combine
                    of
                        Err err ->
                            Err ("Failed to parse numbers in parentheses: " ++ err)

                        Ok integersInParens ->
                            case integersInParens of
                                [ singleNumber ] ->
                                    Ok (Just { current = singleNumber, maximum = Nothing })

                                [ firstNumber, secondNumber ] ->
                                    Ok (Just { current = firstNumber, maximum = Just secondNumber })

                                _ ->
                                    Err "Found unexpected number of numbers in parentheses."

        _ ->
            Err "Found unexpected number of parentheses."


parseDronesWindowDroneEntry : UITreeNodeWithDisplayRegion -> DronesWindowEntryDroneStructure
parseDronesWindowDroneEntry droneEntryNode =
    let
        mainText =
            droneEntryNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0)
                |> List.map Tuple.first
                |> List.head

        gaugeValuePercentFromContainerName containerName =
            droneEntryNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just containerName))
                |> List.head
                |> Maybe.andThen
                    (\gaugeNode ->
                        let
                            gaudeDescendantFromName gaugeDescendantName =
                                gaugeNode
                                    |> listDescendantsWithDisplayRegion
                                    |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just gaugeDescendantName))
                                    |> List.head
                        in
                        gaudeDescendantFromName "droneGaugeBar"
                            |> Maybe.andThen
                                (\gaugeBar ->
                                    gaudeDescendantFromName "droneGaugeBarDmg"
                                        |> Maybe.map
                                            (\droneGaugeBarDmg ->
                                                ((gaugeBar.totalDisplayRegion.width - droneGaugeBarDmg.totalDisplayRegion.width) * 100)
                                                    // gaugeBar.totalDisplayRegion.width
                                            )
                                )
                    )

        hitpointsPercent =
            gaugeValuePercentFromContainerName "gauge_shield"
                |> Maybe.andThen
                    (\shieldPercent ->
                        gaugeValuePercentFromContainerName "gauge_armor"
                            |> Maybe.andThen
                                (\armorPercent ->
                                    gaugeValuePercentFromContainerName "gauge_struct"
                                        |> Maybe.map
                                            (\structPercent ->
                                                { shield = shieldPercent
                                                , armor = armorPercent
                                                , structure = structPercent
                                                }
                                            )
                                )
                    )
    in
    { uiNode = droneEntryNode
    , mainText = mainText
    , hitpointsPercent = hitpointsPercent
    }


parseProbeScannerWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe ProbeScannerWindow
parseProbeScannerWindowFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ProbeScannerWindow")
            |> List.head
    of
        Nothing ->
            Nothing

        Just windowNode ->
            let
                scanResultsNodes =
                    windowNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ScanResultNew")

                scrollNode =
                    windowNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.contains "ResultsContainer") >> Maybe.withDefault False)
                        |> List.concatMap listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "scroll")
                        |> List.head

                headersContainerNode =
                    scrollNode

                entriesHeaders =
                    headersContainerNode
                        |> Maybe.map getAllContainedDisplayTextsWithRegion
                        |> Maybe.withDefault []

                scanResults =
                    scanResultsNodes
                        |> List.map (parseProbeScanResult entriesHeaders)
            in
            Just { uiNode = windowNode, scanResults = scanResults }


parseProbeScanResult : List ( String, UITreeNodeWithDisplayRegion ) -> UITreeNodeWithDisplayRegion -> ProbeScanResult
parseProbeScanResult entriesHeaders scanResultNode =
    let
        textsLeftToRight =
            scanResultNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> .x)
                |> List.map Tuple.first

        cellsTexts =
            scanResultNode
                |> getAllContainedDisplayTextsWithRegion
                |> List.filterMap
                    (\( cellText, cell ) ->
                        let
                            cellMiddle =
                                cell.totalDisplayRegion.x + (cell.totalDisplayRegion.width // 2)

                            maybeHeader =
                                entriesHeaders
                                    |> List.filter
                                        (\( _, header ) ->
                                            header.totalDisplayRegion.x
                                                < cellMiddle
                                                + 1
                                                && cellMiddle
                                                < header.totalDisplayRegion.x
                                                + header.totalDisplayRegion.width
                                                - 1
                                        )
                                    |> List.head
                        in
                        maybeHeader
                            |> Maybe.map (\( headerText, _ ) -> ( headerText, cellText ))
                    )
                |> Dict.fromList

        warpButton =
            scanResultNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getTexturePathFromDictEntries >> Maybe.map (String.endsWith "44_32_18.png") >> Maybe.withDefault False)
                |> List.head
    in
    { uiNode = scanResultNode
    , textsLeftToRight = textsLeftToRight
    , cellsTexts = cellsTexts
    , warpButton = warpButton
    }


parseDirectionalScannerWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe DirectionalScannerWindow
parseDirectionalScannerWindowFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "DirectionalScanner")
            |> List.head
    of
        Nothing ->
            Nothing

        Just windowNode ->
            let
                scrollNode =
                    windowNode
                        |> listDescendantsWithDisplayRegion
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> String.toLower >> String.contains "scroll")
                        |> List.sortBy (.totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0 >> negate)
                        |> List.head

                scanResultsNodes =
                    scrollNode
                        |> Maybe.map listDescendantsWithDisplayRegion
                        |> Maybe.withDefault []
                        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "DirectionalScanResultEntry")
            in
            Just
                { uiNode = windowNode
                , scrollNode = scrollNode
                , scanResults = scanResultsNodes
                }


parseStationWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe StationWindow
parseStationWindowFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "LobbyWnd")
            |> List.head
    of
        Nothing ->
            Nothing

        Just windowNode ->
            let
                buttonFromDisplayText textToSearch =
                    let
                        textToSearchLowercase =
                            String.toLower textToSearch

                        textMatches text =
                            text == textToSearchLowercase || (text |> String.contains (">" ++ textToSearchLowercase ++ "<"))
                    in
                    findButtonInDescendantsByDisplayTextsPredicate
                        (List.any (String.toLower >> textMatches))
                        windowNode

                {- One button occupies this slot and it carries three labels in
                   turn: "Undock" while docked, then "Abort Undock", then
                   "Undocking...". Only the first is a button to press. Pressing
                   either of the others cancels the undock that is already under
                   way, which is the loop.

                   `buttonFromDisplayText` matches a *whole* label -- equality, or
                   the label wrapped in tags -- so "Abort Undock" matched neither
                   "undock" nor "undocking", and "Undocking..." misses the
                   `"undocking"` matcher that was plainly written for it, because
                   the ellipsis is part of the label. Both states therefore left
                   `undockButton` and `abortUndockButton` empty, which every caller
                   reads as "I do not see the undock button".

                   saxrat's run 43 spent 10,310 readings there, asking for help
                   while docked, against only 12 that reached the already-undocking
                   branch the bot already had, and clicked undock 20,486 times in
                   between. Matching "abort" alone cut that to 3 in three minutes
                   but did not free the ship: 256 clicks still met 132 waits,
                   because the third label was still invisible.

                   Matched on substrings, because these are phrases rather than
                   words and the client decorates them. "abort" is the wording the
                   mission runner's `labelUndoesStepInProgress` has flown without
                   looping; "undocking" is the word this parser already chose for
                   the same state.
                -}
                buttonUndoingTheUndock =
                    findButtonInDescendantsByDisplayTextsPredicate
                        (List.any
                            (String.toLower
                                >> (\text ->
                                        String.contains "abort" text
                                            || String.contains "undocking" text
                                   )
                            )
                        )
                        windowNode
            in
            Just
                { uiNode = windowNode
                , undockButton =
                    case buttonUndoingTheUndock of
                        Just _ ->
                            Nothing

                        Nothing ->
                            buttonFromDisplayText "undock"
                , abortUndockButton = buttonUndoingTheUndock
                }


parseInventoryWindowsFromUITreeRoot : UITreeNodeWithDisplayRegion -> List InventoryWindow
parseInventoryWindowsFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (\uiNode -> [ "InventoryPrimary", "ActiveShipCargo" ] |> List.member uiNode.uiNode.pythonObjectTypeName)
        |> List.map parseInventoryWindow


parseInventoryWindow : UITreeNodeWithDisplayRegion -> InventoryWindow
parseInventoryWindow windowUiNode =
    let
        selectedContainerCapacityGaugeNode =
            windowUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "CapacityGauge")
                |> List.head

        selectedContainerCapacityGauge =
            selectedContainerCapacityGaugeNode
                |> Maybe.map (.uiNode >> EveOnline.MemoryReading.listDescendantsInUITreeNode)
                |> Maybe.withDefault []
                |> List.filterMap getDisplayText
                |> List.sortBy (String.length >> negate)
                |> List.head
                |> Maybe.map parseInventoryCapacityGaugeText

        leftTreeEntriesRootNodes =
            windowUiNode |> getContainedTreeViewEntryRootNodes

        leftTreeEntries =
            leftTreeEntriesRootNodes |> List.map parseInventoryWindowTreeViewEntry

        rightContainerNode =
            windowUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter
                    (\uiNode ->
                        (uiNode.uiNode.pythonObjectTypeName == "Container")
                            && (uiNode.uiNode |> getNameFromDictEntries |> Maybe.map (String.contains "right") |> Maybe.withDefault False)
                    )
                |> List.head

        subCaptionLabelText =
            rightContainerNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.startsWith "subCaptionLabel") >> Maybe.withDefault False)
                |> List.concatMap (.uiNode >> getAllContainedDisplayTexts)
                |> List.head

        maybeSelectedContainerInventoryNode =
            rightContainerNode
                |> Maybe.andThen
                    (listDescendantsWithDisplayRegion
                        >> List.filter
                            (\uiNode ->
                                [ "ShipCargo", "ShipDroneBay", "ShipGeneralMiningHold", "StationItems", "ShipFleetHangar", "StructureItemHangar" ]
                                    |> List.member uiNode.uiNode.pythonObjectTypeName
                            )
                        >> List.head
                    )

        selectedContainerInventory =
            maybeSelectedContainerInventoryNode
                |> Maybe.map
                    (\selectedContainerInventoryNode ->
                        let
                            listViewItemNodes =
                                selectedContainerInventoryNode
                                    |> listDescendantsWithDisplayRegion
                                    |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "Item")

                            scrollControlsNode =
                                selectedContainerInventoryNode
                                    |> listDescendantsWithDisplayRegion
                                    |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "ScrollControls")
                                    |> List.head

                            notListViewItemNodes =
                                selectedContainerInventoryNode
                                    |> listDescendantsWithDisplayRegion
                                    |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "InvItem")

                            itemsView =
                                if 0 < (listViewItemNodes |> List.length) then
                                    Just (InventoryItemsListView { items = listViewItemNodes })

                                else if 0 < (notListViewItemNodes |> List.length) then
                                    Just (InventoryItemsNotListView { items = notListViewItemNodes })

                                else
                                    Nothing
                        in
                        { uiNode = selectedContainerInventoryNode
                        , itemsView = itemsView
                        , scrollControls = scrollControlsNode |> Maybe.map parseScrollControls
                        }
                    )

        buttonToSwitchToListView =
            rightContainerNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter
                    (\uiNode ->
                        (uiNode.uiNode.pythonObjectTypeName |> String.contains "ButtonIcon")
                            && ((uiNode.uiNode |> getTexturePathFromDictEntries |> Maybe.withDefault "") |> String.endsWith "38_16_190.png")
                    )
                |> List.head

        buttonToStackAll =
            rightContainerNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter
                    (\uiNode ->
                        (uiNode.uiNode.pythonObjectTypeName |> String.contains "ButtonIcon")
                            && (uiNode.uiNode |> getHintTextFromDictEntries |> Maybe.map (String.contains "Stack All") |> Maybe.withDefault False)
                    )
                |> List.head
    in
    { uiNode = windowUiNode
    , leftTreeEntries = leftTreeEntries
    , subCaptionLabelText = subCaptionLabelText
    , selectedContainerCapacityGauge = selectedContainerCapacityGauge
    , selectedContainerInventory = selectedContainerInventory
    , buttonToSwitchToListView = buttonToSwitchToListView
    , buttonToStackAll = buttonToStackAll
    }


getContainedTreeViewEntryRootNodes : UITreeNodeWithDisplayRegion -> List UITreeNodeWithDisplayRegion
getContainedTreeViewEntryRootNodes parentNode =
    let
        leftTreeEntriesAllNodes =
            parentNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.startsWith "TreeViewEntry")

        isContainedInTreeEntry candidate =
            leftTreeEntriesAllNodes
                |> List.concatMap listDescendantsWithDisplayRegion
                |> List.member candidate
    in
    leftTreeEntriesAllNodes
        |> List.filter (isContainedInTreeEntry >> not)


parseInventoryWindowTreeViewEntry : UITreeNodeWithDisplayRegion -> InventoryWindowLeftTreeEntry
parseInventoryWindowTreeViewEntry treeEntryNode =
    let
        topContNode =
            treeEntryNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.startsWith "topCont_") >> Maybe.withDefault False)
                |> List.sortBy (.totalDisplayRegion >> .y)
                |> List.head

        toggleBtn =
            topContNode
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map ((==) "toggleBtn") >> Maybe.withDefault False)
                |> List.head

        text =
            topContNode
                |> Maybe.map getAllContainedDisplayTextsWithRegion
                |> Maybe.withDefault []
                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> .y)
                |> List.head
                |> Maybe.map Tuple.first
                |> Maybe.withDefault ""

        childrenNodes =
            treeEntryNode |> getContainedTreeViewEntryRootNodes

        children =
            childrenNodes |> List.map (parseInventoryWindowTreeViewEntry >> InventoryWindowLeftTreeEntryChild)
    in
    { uiNode = treeEntryNode
    , toggleBtn = toggleBtn
    , selectRegion = topContNode
    , text = text
    , children = children
    }


unwrapInventoryWindowLeftTreeEntryChild : InventoryWindowLeftTreeEntryChild -> InventoryWindowLeftTreeEntry
unwrapInventoryWindowLeftTreeEntryChild child =
    case child of
        InventoryWindowLeftTreeEntryChild unpacked ->
            unpacked


parseInventoryCapacityGaugeText : String -> Result String InventoryWindowCapacityGauge
parseInventoryCapacityGaugeText capacityText =
    let
        parseMaybeNumber =
            Maybe.map (String.trim >> parseNumberTruncatingAfterOptionalDecimalSeparator >> Result.map Just)
                >> Maybe.withDefault (Ok Nothing)

        continueWithTexts { usedText, maybeMaximumText, maybeSelectedText } =
            case usedText |> parseNumberTruncatingAfterOptionalDecimalSeparator of
                Err parseNumberError ->
                    Err ("Failed to parse used number: " ++ parseNumberError)

                Ok used ->
                    case maybeMaximumText |> parseMaybeNumber of
                        Err parseNumberError ->
                            Err ("Failed to parse maximum number: " ++ parseNumberError)

                        Ok maximum ->
                            case maybeSelectedText |> parseMaybeNumber of
                                Err parseNumberError ->
                                    Err ("Failed to parse selected number: " ++ parseNumberError)

                                Ok selected ->
                                    Ok { used = used, maximum = maximum, selected = selected }

        continueAfterSeparatingBySlash { beforeSlashText, afterSlashMaybeText } =
            case beforeSlashText |> String.trim |> String.split ")" of
                [ onlyUsedText ] ->
                    continueWithTexts { usedText = onlyUsedText, maybeMaximumText = afterSlashMaybeText, maybeSelectedText = Nothing }

                [ firstPart, secondPart ] ->
                    continueWithTexts { usedText = secondPart, maybeMaximumText = afterSlashMaybeText, maybeSelectedText = Just (firstPart |> String.replace "(" "") }

                _ ->
                    Err ("Unexpected number of components in text before slash '" ++ beforeSlashText ++ "'")
    in
    case capacityText |> String.replace "m³" "" |> String.split "/" of
        [ withoutSlash ] ->
            continueAfterSeparatingBySlash { beforeSlashText = withoutSlash, afterSlashMaybeText = Nothing }

        [ partBeforeSlash, partAfterSlash ] ->
            continueAfterSeparatingBySlash { beforeSlashText = partBeforeSlash, afterSlashMaybeText = Just partAfterSlash }

        _ ->
            Err ("Unexpected number of components in capacityText '" ++ capacityText ++ "'")


parseModuleButtonTooltipFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe ModuleButtonTooltip
parseModuleButtonTooltipFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ModuleButtonTooltip")
            |> List.head
    of
        Nothing ->
            Nothing

        Just uiNode ->
            Just (parseModuleButtonTooltip uiNode)


parseModuleButtonTooltip : UITreeNodeWithDisplayRegion -> ModuleButtonTooltip
parseModuleButtonTooltip tooltipUINode =
    let
        upperRightCornerFromDisplayRegion region =
            { x = region.x + region.width, y = region.y }

        distanceSquared a b =
            let
                distanceX =
                    a.x - b.x

                distanceY =
                    a.y - b.y
            in
            distanceX * distanceX + distanceY * distanceY

        shortcutCandidates =
            tooltipUINode
                |> getAllContainedDisplayTextsWithRegion
                |> List.map
                    (\( text, textUINode ) ->
                        { text = text
                        , distanceUpperRightCornerSquared =
                            distanceSquared
                                (textUINode.totalDisplayRegion |> upperRightCornerFromDisplayRegion)
                                (tooltipUINode.totalDisplayRegion |> upperRightCornerFromDisplayRegion)
                        }
                    )
                |> List.sortBy .distanceUpperRightCornerSquared

        shortcut =
            shortcutCandidates
                |> List.filter (\textAndDistance -> textAndDistance.distanceUpperRightCornerSquared < 1000)
                |> List.head
                |> Maybe.map (\{ text } -> { text = text, parseResult = text |> parseModuleButtonTooltipShortcut })

        optimalRangeString =
            tooltipUINode.uiNode
                |> getAllContainedDisplayTexts
                |> List.filterMap
                    (\text ->
                        "Optimal range (|within)\\s*([\\d\\.]+\\s*[km]+)"
                            |> Regex.fromString
                            |> Maybe.andThen (\regex -> text |> Regex.find regex |> List.head)
                            |> Maybe.andThen (.submatches >> List.drop 1 >> List.head)
                            |> Maybe.andThen identity
                            |> Maybe.map String.trim
                    )
                |> List.head

        optimalRange =
            optimalRangeString
                |> Maybe.map (\asString -> { asString = asString, inMeters = asString |> parseOverviewEntryDistanceInMetersFromText })
    in
    { uiNode = tooltipUINode
    , shortcut = shortcut
    , optimalRange = optimalRange
    }


parseModuleButtonTooltipShortcut : String -> Result String (List Common.EffectOnWindow.VirtualKeyCode)
parseModuleButtonTooltipShortcut shortcutText =
    shortcutText
        |> String.split "-"
        |> List.concatMap (String.split "+")
        |> List.map String.trim
        |> List.filter (String.length >> (<) 0)
        |> List.foldl
            (\nextKeyText previousResult ->
                previousResult
                    |> Result.andThen
                        (\previousKeys ->
                            case nextKeyText |> parseKeyShortcutText of
                                Just nextKey ->
                                    Ok (nextKey :: previousKeys)

                                Nothing ->
                                    Err ("Unknown key text: '" ++ nextKeyText ++ "'")
                        )
            )
            (Ok [])
        |> Result.map List.reverse


parseHeatStatusTooltipFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe HeatStatusTooltip
parseHeatStatusTooltipFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "TooltipPanel")
        |> List.filter
            (getAllContainedDisplayTextsWithRegion
                >> List.sortBy (Tuple.second >> .totalDisplayRegion >> .y)
                >> List.head
                >> Maybe.map (Tuple.first >> String.contains "Heat Status")
                >> Maybe.withDefault False
            )
        |> List.head
        |> Maybe.map parseHeatStatusTooltip


parseHeatStatusTooltip : UITreeNodeWithDisplayRegion -> HeatStatusTooltip
parseHeatStatusTooltip tooltipNode =
    let
        parsePercentFromPrefix prefix =
            tooltipNode.uiNode
                |> getAllContainedDisplayTexts
                |> List.map String.trim
                |> List.filter (String.toLower >> String.startsWith prefix)
                |> List.head
                |> Maybe.map (String.split " " >> List.filter (String.isEmpty >> not) >> List.drop 1 >> String.join "")
                |> Maybe.andThen (String.split "%" >> List.head)
                |> Maybe.andThen String.toInt
    in
    { uiNode = tooltipNode
    , lowPercent = parsePercentFromPrefix "low"
    , mediumPercent = parsePercentFromPrefix "medium"
    , highPercent = parsePercentFromPrefix "high"
    }


parseKeyShortcutText : String -> Maybe Common.EffectOnWindow.VirtualKeyCode
parseKeyShortcutText keyText =
    [ ( "CTRL", Common.EffectOnWindow.vkey_LCONTROL )
    , ( "STRG", Common.EffectOnWindow.vkey_LCONTROL )
    , ( "ALT", Common.EffectOnWindow.vkey_LMENU )
    , ( "SHIFT", Common.EffectOnWindow.vkey_LSHIFT )
    , ( "UMSCH", Common.EffectOnWindow.vkey_LSHIFT )
    , ( "F1", Common.EffectOnWindow.vkey_F1 )
    , ( "F2", Common.EffectOnWindow.vkey_F2 )
    , ( "F3", Common.EffectOnWindow.vkey_F3 )
    , ( "F4", Common.EffectOnWindow.vkey_F4 )
    , ( "F5", Common.EffectOnWindow.vkey_F5 )
    , ( "F6", Common.EffectOnWindow.vkey_F6 )
    , ( "F7", Common.EffectOnWindow.vkey_F7 )
    , ( "F8", Common.EffectOnWindow.vkey_F8 )
    , ( "F9", Common.EffectOnWindow.vkey_F9 )
    , ( "F10", Common.EffectOnWindow.vkey_F10 )
    , ( "F11", Common.EffectOnWindow.vkey_F11 )
    , ( "F12", Common.EffectOnWindow.vkey_F12 )
    ]
        |> Dict.fromList
        |> Dict.get (keyText |> String.toUpper)


parseChatWindowStacksFromUITreeRoot : UITreeNodeWithDisplayRegion -> List ChatWindowStack
parseChatWindowStacksFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ChatWindowStack")
        |> List.map parseChatWindowStack


parseChatWindowStack : UITreeNodeWithDisplayRegion -> ChatWindowStack
parseChatWindowStack chatWindowStackUiNode =
    let
        chatWindowNode =
            chatWindowStackUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "XmppChatWindow")
                |> List.head
    in
    { uiNode = chatWindowStackUiNode
    , chatWindow = chatWindowNode |> Maybe.map parseChatWindow
    }


parseChatWindow : UITreeNodeWithDisplayRegion -> ChatWindow
parseChatWindow chatWindowUiNode =
    let
        userlistNode =
            chatWindowUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> getNameFromDictEntries >> Maybe.map (String.toLower >> String.contains "userlist") >> Maybe.withDefault False)
                |> List.head
    in
    { uiNode = chatWindowUiNode
    , name = getNameFromDictEntries chatWindowUiNode.uiNode
    , userlist = userlistNode |> Maybe.map parseChatWindowUserlist
    }


parseChatWindowUserlist : UITreeNodeWithDisplayRegion -> ChatWindowUserlist
parseChatWindowUserlist userlistNode =
    let
        visibleUsers =
            userlistNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (\uiNode -> [ "XmppChatSimpleUserEntry", "XmppChatUserEntry" ] |> List.member uiNode.uiNode.pythonObjectTypeName)
                |> List.map parseChatUserEntry

        scrollControls =
            userlistNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "ScrollControls")
                |> List.head
                |> Maybe.map parseScrollControls
    in
    { uiNode = userlistNode, visibleUsers = visibleUsers, scrollControls = scrollControls }


parseChatUserEntry : UITreeNodeWithDisplayRegion -> ChatUserEntry
parseChatUserEntry chatUserUiNode =
    let
        standingIconNode =
            chatUserUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "FlagIconWithState")
                |> List.head

        name =
            chatUserUiNode.uiNode
                |> getAllContainedDisplayTexts
                |> List.sortBy String.length
                |> List.reverse
                |> List.head

        standingIconHint =
            standingIconNode
                |> Maybe.andThen (.uiNode >> getHintTextFromDictEntries)
    in
    { uiNode = chatUserUiNode
    , name = name
    , standingIconHint = standingIconHint
    }


parseAgentConversationWindowsFromUITreeRoot : UITreeNodeWithDisplayRegion -> List AgentConversationWindow
parseAgentConversationWindowsFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "AgentDialogueWindow")
        |> List.map parseAgentConversationWindow


parseAgentConversationWindow : UITreeNodeWithDisplayRegion -> AgentConversationWindow
parseAgentConversationWindow windowUINode =
    { uiNode = windowUINode
    }


parseMarketOrdersWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe MarketOrdersWindow
parseMarketOrdersWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "MarketOrdersWnd")
        |> List.head
        |> Maybe.map parseMarketOrdersWindow


parseMarketOrdersWindow : UITreeNodeWithDisplayRegion -> MarketOrdersWindow
parseMarketOrdersWindow windowUINode =
    { uiNode = windowUINode
    }


parseFittingWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe FittingWindow
parseFittingWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "FittingWindow")
        |> List.head
        |> Maybe.map parseFittingWindow


parseFittingWindow : UITreeNodeWithDisplayRegion -> FittingWindow
parseFittingWindow windowUINode =
    { uiNode = windowUINode
    }


parseSurveyScanWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe SurveyScanWindow
parseSurveyScanWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SurveyScanView")
        |> List.head
        |> Maybe.map parseSurveyScanWindow


parseSurveyScanWindow : UITreeNodeWithDisplayRegion -> SurveyScanWindow
parseSurveyScanWindow windowUINode =
    { uiNode = windowUINode
    , scanEntries =
        windowUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "SurveyScanEntry")
    }


parseBookmarkLocationWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe BookmarkLocationWindow
parseBookmarkLocationWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "BookmarkLocationWindow")
        |> List.head
        |> Maybe.map parseBookmarkLocationWindow


parseBookmarkLocationWindow : UITreeNodeWithDisplayRegion -> BookmarkLocationWindow
parseBookmarkLocationWindow windowUINode =
    { uiNode = windowUINode
    , submitButton = findButtonInDescendantsContainingDisplayText "submit" windowUINode
    , cancelButton = findButtonInDescendantsContainingDisplayText "cancel" windowUINode
    }


parseRepairShopWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe RepairShopWindow
parseRepairShopWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "RepairShopWindow")
        |> List.head
        |> Maybe.map parseRepairShopWindow


parseRepairShopWindow : UITreeNodeWithDisplayRegion -> RepairShopWindow
parseRepairShopWindow windowUINode =
    let
        buttonGroup =
            windowUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "ButtonGroup")
                |> List.head

        buttons =
            buttonGroup
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "Button")
                |> List.map
                    (\buttonNode ->
                        { uiNode = buttonNode
                        , mainText =
                            buttonNode
                                |> getAllContainedDisplayTextsWithRegion
                                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0)
                                |> List.map Tuple.first
                                |> List.head
                        }
                    )
    in
    { uiNode = windowUINode
    , items =
        windowUINode
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "Item")
    , buttonGroup = buttonGroup
    , buttons = buttons
    }


parseCharacterSheetWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe CharacterSheetWindow
parseCharacterSheetWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "CharacterSheetWindow")
        |> List.head
        |> Maybe.map parseCharacterSheetWindow


parseCharacterSheetWindow : UITreeNodeWithDisplayRegion -> CharacterSheetWindow
parseCharacterSheetWindow windowUINode =
    let
        skillGroups =
            windowUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "SkillGroupGauge")
    in
    { uiNode = windowUINode
    , skillGroups = skillGroups
    }


parseFleetWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe FleetWindow
parseFleetWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "FleetWindow")
        |> List.head
        |> Maybe.map parseFleetWindow


parseFleetWindow : UITreeNodeWithDisplayRegion -> FleetWindow
parseFleetWindow windowUINode =
    let
        fleetMembers =
            windowUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "FleetMember")
    in
    { uiNode = windowUINode
    , fleetMembers = fleetMembers
    }


parseWatchListPanelFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe WatchListPanel
parseWatchListPanelFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "WatchListPanel")
        |> List.head
        |> Maybe.map parseWatchListPanel


parseWatchListPanel : UITreeNodeWithDisplayRegion -> WatchListPanel
parseWatchListPanel windowUINode =
    let
        entries =
            windowUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "WatchListEntry")
    in
    { uiNode = windowUINode
    , entries = entries
    }


parseStandaloneBookmarkWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe StandaloneBookmarkWindow
parseStandaloneBookmarkWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "StandaloneBookmarkWnd")
        |> List.head
        |> Maybe.map parseStandaloneBookmarkWindow


parseStandaloneBookmarkWindow : UITreeNodeWithDisplayRegion -> StandaloneBookmarkWindow
parseStandaloneBookmarkWindow windowUINode =
    let
        entries =
            windowUINode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "PlaceEntry")
    in
    { uiNode = windowUINode
    , entries = entries
    }


parseNeocomFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe Neocom
parseNeocomFromUITreeRoot uiTreeRoot =
    case
        uiTreeRoot
            |> listDescendantsWithDisplayRegion
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "Neocom")
            |> List.head
    of
        Nothing ->
            Nothing

        Just uiNode ->
            Just (parseNeocom uiNode)


parseNeocom : UITreeNodeWithDisplayRegion -> Neocom
parseNeocom neocomUiNode =
    let
        maybeClockTextAndNode =
            neocomUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InGameClock")
                |> List.concatMap getAllContainedDisplayTextsWithRegion
                |> List.head

        nodeFromTexturePathEnd texturePathEnd =
            neocomUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter
                    (.uiNode
                        >> getTexturePathFromDictEntries
                        >> Maybe.map (String.endsWith texturePathEnd)
                        >> Maybe.withDefault False
                    )
                |> List.head

        clock =
            maybeClockTextAndNode
                |> Maybe.map
                    (\( clockText, clockNode ) ->
                        { uiNode = clockNode
                        , text = clockText
                        , parsedText = parseNeocomClockText clockText
                        }
                    )
    in
    { uiNode = neocomUiNode
    , iconInventory = nodeFromTexturePathEnd "items.png"
    , clock = clock
    }


parseNeocomClockText : String -> Result String { hour : Int, minute : Int }
parseNeocomClockText clockText =
    case clockText |> String.split ":" of
        [ hourText, minuteText ] ->
            case hourText |> String.trim |> String.toInt of
                Nothing ->
                    Err ("Failed to parse hour: '" ++ hourText ++ "'")

                Just hour ->
                    case minuteText |> String.trim |> String.toInt of
                        Nothing ->
                            Err ("Failed to parse minute: '" ++ minuteText ++ "'")

                        Just minute ->
                            Ok { hour = hour, minute = minute }

        _ ->
            Err "Expecting exactly two substrings separated by a colon (:)."


parseKeyActivationWindowFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe KeyActivationWindow
parseKeyActivationWindowFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "KeyActivationWindow")
        |> List.head
        |> Maybe.map parseKeyActivationWindow


parseKeyActivationWindow : UITreeNodeWithDisplayRegion -> KeyActivationWindow
parseKeyActivationWindow windowUiNode =
    let
        activateButton =
            windowUiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ActivateButton")
                |> List.head
    in
    { uiNode = windowUiNode
    , activateButton = activateButton
    }


parseMessageBoxesFromUITreeRoot : UITreeNodeWithDisplayRegion -> List MessageBox
parseMessageBoxesFromUITreeRoot uiTreeRoot =
    let
        messageBoxNodes =
            uiTreeRoot
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "MessageBox")

        modalLayers =
            uiTreeRoot
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "LayerCore")
                |> List.filter
                    (.uiNode
                        >> getNameFromDictEntries
                        >> Maybe.map (String.toLower >> String.contains "modal")
                        >> Maybe.withDefault False
                    )

        modalHybridWindowNodes =
            modalLayers
                |> List.concatMap listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "HybridWindow")
    in
    [ messageBoxNodes
    , modalHybridWindowNodes
    ]
        |> List.concat
        |> List.map parseMessageBox


parseMessageBox : UITreeNodeWithDisplayRegion -> MessageBox
parseMessageBox uiNode =
    let
        buttonGroup =
            uiNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "ButtonGroup")
                |> List.head

        buttons =
            buttonGroup
                |> Maybe.map listDescendantsWithDisplayRegion
                |> Maybe.withDefault []
                |> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "Button")
                |> List.map
                    (\buttonNode ->
                        { uiNode = buttonNode
                        , mainText =
                            buttonNode
                                |> getAllContainedDisplayTextsWithRegion
                                |> List.sortBy (Tuple.second >> .totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0)
                                |> List.map Tuple.first
                                |> List.head
                        }
                    )
    in
    { buttonGroup = buttonGroup
    , buttons = buttons
    , uiNode = uiNode
    }


findButtonInDescendantsContainingDisplayText : String -> UITreeNodeWithDisplayRegion -> Maybe UITreeNodeWithDisplayRegion
findButtonInDescendantsContainingDisplayText displayText =
    findButtonInDescendantsByDisplayTextsPredicate
        (List.any (String.toLower >> String.contains (String.toLower displayText)))


findButtonInDescendantsByDisplayTextsPredicate : (List String -> Bool) -> UITreeNodeWithDisplayRegion -> Maybe UITreeNodeWithDisplayRegion
findButtonInDescendantsByDisplayTextsPredicate displayTextsPredicate =
    listDescendantsWithDisplayRegion
        {-
           2023-01-12 discovered name: UndockButton
        -}
        >> List.filter (.uiNode >> .pythonObjectTypeName >> String.contains "Button")
        >> List.filter (.uiNode >> getAllContainedDisplayTexts >> displayTextsPredicate)
        >> List.sortBy (.totalDisplayRegion >> areaFromDisplayRegion >> Maybe.withDefault 0)
        >> List.head


parseScrollControls : UITreeNodeWithDisplayRegion -> ScrollControls
parseScrollControls scrollControlsNode =
    let
        scrollHandle =
            scrollControlsNode
                |> listDescendantsWithDisplayRegion
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ScrollHandle")
                |> List.head
    in
    { uiNode = scrollControlsNode
    , scrollHandle = scrollHandle
    }


parseLayerAbovemainFromUITreeRoot : UITreeNodeWithDisplayRegion -> Maybe UITreeNodeWithDisplayRegion
parseLayerAbovemainFromUITreeRoot uiTreeRoot =
    uiTreeRoot
        |> listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> getNameFromDictEntries >> (==) (Just "l_abovemain"))
        |> List.head


getSubstringBetweenXmlTagsAfterMarker : String -> String -> Maybe String
getSubstringBetweenXmlTagsAfterMarker marker =
    String.split marker
        >> List.drop 1
        >> List.head
        >> Maybe.andThen (String.split ">" >> List.drop 1 >> List.head)
        >> Maybe.andThen (String.split "<" >> List.head)


parseNumberTruncatingAfterOptionalDecimalSeparator : String -> Result String Int
parseNumberTruncatingAfterOptionalDecimalSeparator numberDisplayText =
    let
        expectedSeparators =
            [ ",", ".", "’", " ", "\u{00A0}", "\u{202F}" ]

        groupsTexts =
            expectedSeparators
                |> List.foldl (\separator -> List.concatMap (String.split separator))
                    [ String.trim numberDisplayText ]

        lastGroupIsFraction =
            case List.reverse groupsTexts of
                lastGroupText :: _ :: _ ->
                    String.length lastGroupText < 3

                _ ->
                    False

        integerText =
            String.join ""
                (if lastGroupIsFraction then
                    groupsTexts |> List.reverse |> List.drop 1 |> List.reverse

                 else
                    groupsTexts
                )
    in
    integerText
        |> String.toInt
        |> Result.fromMaybe ("Failed to parse to integer: " ++ integerText)


centerFromDisplayRegion : DisplayRegion -> Location2d
centerFromDisplayRegion region =
    { x = region.x + region.width // 2, y = region.y + region.height // 2 }


getDisplayText : EveOnline.MemoryReading.UITreeNode -> Maybe String
getDisplayText uiNode =
    [ "_setText", "_text" ]
        |> List.filterMap
            (\displayTextPropertyName ->
                uiNode.dictEntriesOfInterest
                    |> Dict.get displayTextPropertyName
                    |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.string >> Result.toMaybe)
            )
        |> List.sortBy (String.length >> negate)
        |> List.head


getAllContainedDisplayTexts : EveOnline.MemoryReading.UITreeNode -> List String
getAllContainedDisplayTexts uiNode =
    uiNode
        :: (uiNode |> EveOnline.MemoryReading.listDescendantsInUITreeNode)
        |> List.filterMap getDisplayText


getAllContainedDisplayTextsWithRegion : UITreeNodeWithDisplayRegion -> List ( String, UITreeNodeWithDisplayRegion )
getAllContainedDisplayTextsWithRegion uiNode =
    uiNode
        :: (uiNode |> listDescendantsWithDisplayRegion)
        |> List.filterMap
            (\descendant ->
                let
                    displayText =
                        descendant.uiNode |> getDisplayText |> Maybe.withDefault ""
                in
                if 0 < (displayText |> String.length) then
                    Just ( displayText, descendant )

                else
                    Nothing
            )


getNameFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe String
getNameFromDictEntries =
    getStringPropertyFromDictEntries "_name"


getHintTextFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe String
getHintTextFromDictEntries =
    getStringPropertyFromDictEntries "_hint"


getTexturePathFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe String
getTexturePathFromDictEntries =
    getStringPropertyFromDictEntries "texturePath"


getStringPropertyFromDictEntries : String -> EveOnline.MemoryReading.UITreeNode -> Maybe String
getStringPropertyFromDictEntries dictEntryKey uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get dictEntryKey
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.string >> Result.toMaybe)


getColorPercentFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe ColorComponents
getColorPercentFromDictEntries =
    .dictEntriesOfInterest
        >> Dict.get "_color"
        >> Maybe.andThen (Json.Decode.decodeValue jsonDecodeColorPercent >> Result.toMaybe)


jsonDecodeColorPercent : Json.Decode.Decoder ColorComponents
jsonDecodeColorPercent =
    Json.Decode.map4 ColorComponents
        (Json.Decode.field "aPercent" jsonDecodeIntFromIntOrString)
        (Json.Decode.field "rPercent" jsonDecodeIntFromIntOrString)
        (Json.Decode.field "gPercent" jsonDecodeIntFromIntOrString)
        (Json.Decode.field "bPercent" jsonDecodeIntFromIntOrString)


getRotationFloatFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe Float
getRotationFloatFromDictEntries =
    .dictEntriesOfInterest
        >> Dict.get "_rotation"
        >> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)


getOpacityFloatFromDictEntries : EveOnline.MemoryReading.UITreeNode -> Maybe Float
getOpacityFloatFromDictEntries =
    .dictEntriesOfInterest
        >> Dict.get "_opacity"
        >> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)


jsonDecodeIntFromIntOrString : Json.Decode.Decoder Int
jsonDecodeIntFromIntOrString =
    Json.Decode.oneOf
        [ Json.Decode.int
        , Json.Decode.string
            |> Json.Decode.andThen
                (\asString ->
                    case asString |> String.toInt of
                        Just asInt ->
                            Json.Decode.succeed asInt

                        Nothing ->
                            Json.Decode.fail ("Failed to parse integer from string '" ++ asString ++ "'")
                )
        ]


getHorizontalOffsetFromParentAndWidth : EveOnline.MemoryReading.UITreeNode -> Maybe { offset : Int, width : Int }
getHorizontalOffsetFromParentAndWidth uiNode =
    let
        roundedNumberFromPropertyName propertyName =
            uiNode.dictEntriesOfInterest
                |> Dict.get propertyName
                |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)
                |> Maybe.map round
    in
    case ( roundedNumberFromPropertyName "_displayX", roundedNumberFromPropertyName "_width" ) of
        ( Just offset, Just width ) ->
            Just { offset = offset, width = width }

        _ ->
            Nothing


areaFromDisplayRegion : DisplayRegion -> Maybe Int
areaFromDisplayRegion region =
    if region.width < 0 || region.height < 0 then
        Nothing

    else
        Just (region.width * region.height)


getVerticalOffsetFromParent : EveOnline.MemoryReading.UITreeNode -> Maybe Int
getVerticalOffsetFromParent =
    .dictEntriesOfInterest
        >> Dict.get "_displayY"
        >> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)
        >> Maybe.map round


getMostPopulousDescendantMatchingPredicate : (EveOnline.MemoryReading.UITreeNode -> Bool) -> EveOnline.MemoryReading.UITreeNode -> Maybe EveOnline.MemoryReading.UITreeNode
getMostPopulousDescendantMatchingPredicate predicate parent =
    EveOnline.MemoryReading.listDescendantsInUITreeNode parent
        |> List.filter predicate
        |> List.sortBy EveOnline.MemoryReading.countDescendantsInUITreeNode
        |> List.reverse
        |> List.head


listDescendantsWithDisplayRegion : UITreeNodeWithDisplayRegion -> List UITreeNodeWithDisplayRegion
listDescendantsWithDisplayRegion parent =
    parent
        |> listChildrenWithDisplayRegion
        |> List.concatMap (\child -> child :: listDescendantsWithDisplayRegion child)


listChildrenWithDisplayRegion : UITreeNodeWithDisplayRegion -> List UITreeNodeWithDisplayRegion
listChildrenWithDisplayRegion parent =
    parent.children
        |> Maybe.withDefault []
        |> List.filterMap justCaseWithDisplayRegion


justCaseWithDisplayRegion : ChildOfNodeWithDisplayRegion -> Maybe UITreeNodeWithDisplayRegion
justCaseWithDisplayRegion child =
    case child of
        ChildWithoutRegion _ ->
            Nothing

        ChildWithRegion childWithRegion ->
            Just childWithRegion


typeOccludesFollowingSiblingNodes : EveOnline.MemoryReading.UITreeNode -> Bool
typeOccludesFollowingSiblingNodes node =
    -- session-recording-2022-12-09T12-32-56.zip: In Overview window: "SortHeaders"
    node.pythonObjectTypeName == "SortHeaders"


subtractRegionsFromRegion :
    { minuend : DisplayRegion
    , subtrahend : List DisplayRegion
    }
    -> List DisplayRegion
subtractRegionsFromRegion { minuend, subtrahend } =
    subtrahend
        |> List.foldl
            (\subtrahendPart previousResults ->
                previousResults
                    |> List.concatMap
                        (\minuendPart ->
                            subtractRegionFromRegion { subtrahend = subtrahendPart, minuend = minuendPart }
                        )
            )
            [ minuend ]


subtractRegionFromRegion :
    { minuend : DisplayRegion
    , subtrahend : DisplayRegion
    }
    -> List DisplayRegion
subtractRegionFromRegion { minuend, subtrahend } =
    let
        minuendRight =
            minuend.x + minuend.width

        minuendBottom =
            minuend.y + minuend.height

        subtrahendRight =
            subtrahend.x + subtrahend.width

        subtrahendBottom =
            subtrahend.y + subtrahend.height
    in
    {-
       Similar to approach from https://stackoverflow.com/questions/3765283/how-to-subtract-a-rectangle-from-another/15228510#15228510
       We want to support finding the largest rectangle, so we let them overlap here.

       ----------------------------
       |  A  |       A      |  A  |
       |  B  |              |  C  |
       |--------------------------|
       |  B  |  subtrahend  |  C  |
       |--------------------------|
       |  B  |              |  C  |
       |  D  |      D       |  D  |
       ----------------------------
    -}
    [ { left = minuend.x
      , top = minuend.y
      , right = minuendRight
      , bottom = minuendBottom |> min subtrahend.y
      }
    , { left = minuend.x
      , top = minuend.y
      , right = minuendRight |> min subtrahend.x
      , bottom = minuendBottom
      }
    , { left = minuend.x |> max subtrahendRight
      , top = minuend.y
      , right = minuendRight
      , bottom = minuendBottom
      }
    , { left = minuend.x
      , top = minuend.y |> max subtrahendBottom
      , right = minuendRight
      , bottom = minuendBottom
      }
    ]
        |> List.map
            (\rect ->
                { x = rect.left
                , y = rect.top
                , width = rect.right - rect.left
                , height = rect.bottom - rect.top
                }
            )
        |> List.filter (\rect -> 0 < rect.width && 0 < rect.height)
        |> listUnique


regionsOverlap : DisplayRegion -> DisplayRegion -> Bool
regionsOverlap regionA regionB =
    subtractRegionFromRegion
        { minuend = regionA
        , subtrahend = regionB
        }
        /= [ regionA ]


{-| Remove duplicate values, keeping the first instance of each element which appears more than once.
-}
listUnique : List element -> List element
listUnique =
    List.foldr
        (\nextElement elements ->
            if elements |> List.member nextElement then
                elements

            else
                nextElement :: elements
        )
        []
