{- EVE Online combat mission bot version 2026-07-29

   Runs security missions for an agent end to end: takes the mission from the
   agent in station, flies out to the site, clears each pocket, follows the
   acceleration gates between them, returns, and turns the mission in. Forked
   from the combat anomaly bot ("saxrat"), whose combat, looting and travel
   logic it reuses; what is new here is the agent conversation, the mission
   tracker in the info panel, and the decision tree that ties them together.

   ## How it navigates

   The mission tracker in the info panel carries a single button whose label is
   always the next travel step -- "Undock", "Set Destination", "Warp to
   Location", "Dock" -- and which carries no label at all while the ship is on
   grid and it is the bot's turn to act. The bot clicks that button whenever it
   has a label and there is nothing to fight, which removes any need to set
   routes or drive the autopilot itself.

   ## Setting up the Game Client

   Despite being quite robust, this bot is less intelligent than a human. For
   example, its perception is more limited than ours, so we need to set up the
   game to ensure that the bot can see everything it needs. Following is the
   list of setup instructions for the EVE Online client:

   + Set the UI language to English.
   + Open the overview window and the drones window, and keep them open.
   + Set the Overview window to sort objects in space by distance with the
     nearest entry at the top.
   + Make sure the overview shows acceleration gates, or the bot cannot follow
     a mission from one pocket to the next.
   + In the ship UI, arrange the modules:
     + Place the modules to use in combat (to activate on targets) in the top row.
     + Place the propulsion module first in the middle row.
     + Hide passive modules by disabling the check-box `Display Passive Modules`.
   + Keep the default drone keybinds: Shift+F launches, F engages, Shift+R recalls.
   + Configure the keyboard key 'W' to make the ship orbit.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit
   your use-case.

   + `agent-name` : Name of the agent to run missions for, as it appears in the
     station's Agents tab. Defaults to the first agent listed as available.
   + `decline-mission` : Name of a mission to skip rather than run. The bot uses
     the agent's "Delay" button rather than "Decline", since declining more than
     once every four hours costs standing. Repeatable.
   + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. Repeatable.
   + `prefer-wreck` : Name (or type) of a wreck to search first when a mission
     wants cargo out of destroyed ships, e.g. `prefer-wreck=Personnel Transport`.
     Purely an optimisation -- the bot still opens every other wreck afterwards,
     so a wrong guess costs nothing but a wasted trip. Repeatable.
   + `attack-object` : Name (or type) of a non-rat object the bot should also
     shoot, as it appears in the overview. Usually unnecessary: when a mission
     objective names a structure to destroy ("You need to destroy the
     <a ...>Drone Silo</a>"), the bot takes the name from the objective itself.
     This setting is the manual override for anything that does not cover.
     Either way the object must be enabled in the overview's type filters
     (Large Collidable Objects are off by default) or the bot cannot see it at
     all. Repeatable.
   + `activate-module-always` : Text found in tooltips of ship modules that
     should always be active. For example: "shield hardener".
   + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping
     range or aligning.
   + `keep-at-range`: Set this to 'yes' to keep range from the target instead of
     orbiting or aligning.
   + `targeting-range`: Maximum distance in meters to lock a target from the
     overview. Beyond this, the bot approaches instead of locking. Defaults to 66000.
   + `run-away-shield-hitpoints-threshold-percent` /
     `run-away-armor-hitpoints-threshold-percent`: Dock up when the ship drops
     below these. Disabled by default.

   When using more than one setting, start a new line for each setting in the
   text input field. Here is an example of a complete settings string:

   ```
agent-name=Nehrnah Gorouyar
orbit-in-combat=yes
run-away-shield-hitpoints-threshold-percent=50
run-away-armor-hitpoints-threshold-percent=80
   ```

-}
{-
   catalog-tags:eve-online,mission,ratting
   authors-forum-usernames:viir
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
        , secondsToSessionEnd
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
    { agentName = Nothing
    , missionNamesToDecline = []
    , runAwayShieldHitpointsThresholdPercent = -1
    , runAwayArmorHitpointsThresholdPercent = -1
    , avoidRats = []
    , attackObjectNames = []
    , preferWreckNames = []
    , activateModulesAlways = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No
    , targetingRangeMeters = 66000
    }


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    AppSettings.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "agent-name"
           , AppSettings.valueTypeString
                (\agentName settings -> { settings | agentName = Just (String.trim agentName) })
           )
         , ( "decline-mission"
           , AppSettings.valueTypeString
                (\missionName settings ->
                    { settings | missionNamesToDecline = String.trim missionName :: settings.missionNamesToDecline }
                )
           )
         , ( "run-away-shield-hitpoints-threshold-percent"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayShieldHitpointsThresholdPercent = threshold })
           )
         , ( "run-away-armor-hitpoints-threshold-percent"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayArmorHitpointsThresholdPercent = threshold })
           )
         , ( "avoid-rat"
           , AppSettings.valueTypeString
                (\ratToAvoid settings ->
                    { settings | avoidRats = String.trim ratToAvoid :: settings.avoidRats }
                )
           )
         , ( "attack-object"
           , AppSettings.valueTypeString
                (\objectName settings ->
                    { settings | attackObjectNames = String.trim objectName :: settings.attackObjectNames }
                )
           )
         , ( "prefer-wreck"
           , AppSettings.valueTypeString
                (\wreckName settings ->
                    { settings | preferWreckNames = String.trim wreckName :: settings.preferWreckNames }
                )
           )
         , ( "activate-module-always"
           , AppSettings.valueTypeString
                (\moduleName settings ->
                    { settings | activateModulesAlways = moduleName :: settings.activateModulesAlways }
                )
           )
         , ( "orbit-in-combat"
           , AppSettings.valueTypeYesOrNo
                (\orbitInCombat settings -> { settings | orbitInCombat = orbitInCombat })
           )
         , ( "keep-at-range"
           , AppSettings.valueTypeYesOrNo
                (\keepAtRange settings -> { settings | keepAtRange = keepAtRange })
           )
         , ( "bot-step-delay"
           , AppSettings.valueTypeInteger
                (\delay settings -> { settings | botStepDelayMilliseconds = delay })
           )
         , ( "targeting-range"
           , AppSettings.valueTypeInteger
                (\targetingRangeMeters settings -> { settings | targetingRangeMeters = targetingRangeMeters })
           )
         ]
            |> Dict.fromList
        )
        defaultBotSettings


type alias BotSettings =
    { agentName : Maybe String
    , missionNamesToDecline : List String
    , runAwayShieldHitpointsThresholdPercent : Int
    , runAwayArmorHitpointsThresholdPercent : Int
    , avoidRats : List String
    , attackObjectNames : List String
    , preferWreckNames : List String
    , activateModulesAlways : List String
    , maxTargetCount : Int
    , botStepDelayMilliseconds : Int
    , orbitInCombat : AppSettings.YesOrNo
    , keepAtRange : AppSettings.YesOrNo
    , targetingRangeMeters : Int
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


type alias BotMemory =
    { lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory
    , shipWarpingInLastReading : Maybe Bool
    , contextMenuLastDepth : Int
    , contextMenuStuckTicks : Int
    , lootWindowOpenTicks : Int
    , routeFirstMarkerRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , routeFirstMarkerUnchangedTicks : Int
    , targetToUnlockRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , targetToUnlockUnchangedTicks : Int
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory


missionBotDecisionRoot : BotDecisionContext -> DecisionPathNode
missionBotDecisionRoot context =
    missionBotDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


missionBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
missionBotDecisionRootBeforeApplyingSettings context =
    case
        [ generalSetupInUserInterface context.readingFromGameClient
        , windDownBeforeSessionEnd context
        ]
            |> List.filterMap identity
            |> List.head
    of
        Just decision ->
            decision

        Nothing ->
            branchDependingOnDockedOrInSpace
                { ifDocked = decideActionWhenDocked context
                , ifSeeShipUI =
                    \shipUI ->
                        runAwayIfLowHealth context shipUI
                            |> Maybe.withDefault (decideActionWhenInSpace context { shipUI = shipUI })
                }
                context.readingFromGameClient



{-| How long before the planned session end to stop taking new work and park.
Enough time to finish a warp and a dock, not so much that a short session
never gets anything done.
-}
secondsBeforeSessionEndToWindDown : Int
secondsBeforeSessionEndToWindDown =
    200


{-| Wind the session down cleanly instead of being killed mid-flight: once the
planned end is close, recall drones and dock rather than starting another leg.

This only does anything when the host was given `--session-duration-minutes`;
without it `secondsToSessionEnd` is Nothing and this never fires. Worth knowing
that the host merely *announces* the deadline -- it does not stop its own loop
-- so if nothing here acted on it the flag would be inert. The anomaly bot this
was forked from reacted to it inside `continueIfShouldHide`, which this bot does
not have (its hide-when-neutral behaviour did not apply to running missions).
-}
windDownBeforeSessionEnd : BotDecisionContext -> Maybe DecisionPathNode
windDownBeforeSessionEnd context =
    case secondsToSessionEnd context.eventContext of
        Nothing ->
            Nothing

        Just secondsRemaining ->
            if secondsBeforeSessionEndToWindDown < secondsRemaining then
                Nothing

            else
                Just
                    (describeBranch
                        ("The session ends in "
                            ++ String.fromInt secondsRemaining
                            ++ " seconds -- wind down rather than start another leg."
                        )
                        (case context.readingFromGameClient.shipUI of
                            Nothing ->
                                describeBranch "Already docked. Stay put." waitForProgressInGame

                            Just _ ->
                                returnDronesToBay context
                                    |> Maybe.withDefault
                                        (dockAtStation
                                            context.memory.lastDockedStationNameFromInfoPanel
                                            context
                                        )
                        )
                    )



-- Reading the mission's state


{-| The mission tracker for the agent we are running, if one is showing. When
no agent name is configured we take whichever mission is being tracked, so a
mission already in progress when the bot starts is picked up rather than
ignored.
-}
missionInfoPanelEntry : BotDecisionContext -> Maybe EveOnline.ParseUserInterface.AgentMissionInfoPanelEntry
missionInfoPanelEntry context =
    case selectedAgentEntry context |> Maybe.andThen .characterID of
        Just agentCharacterID ->
            case
                context.readingFromGameClient.agentMissionInfoPanelEntries
                    |> List.filter (.agentCharacterID >> (==) (Just agentCharacterID))
                    |> List.head
            of
                Just matching ->
                    Just matching

                Nothing ->
                    context.readingFromGameClient.agentMissionInfoPanelEntries |> List.head

        Nothing ->
            context.readingFromGameClient.agentMissionInfoPanelEntries |> List.head


{-| The agent to run missions for: the one named in the settings, else the
first one the station lists as available to us.
-}
selectedAgentEntry : BotDecisionContext -> Maybe EveOnline.ParseUserInterface.StationAgentEntry
selectedAgentEntry context =
    context.readingFromGameClient.stationWindow
        |> Maybe.map .agentEntries
        |> Maybe.withDefault []
        |> (\agentEntries ->
                case context.eventContext.botSettings.agentName of
                    Just agentName ->
                        agentEntries
                            |> List.filter
                                (.name
                                    >> Maybe.map (stringContainsIgnoringCase agentName)
                                    >> Maybe.withDefault False
                                )
                            |> List.head

                    Nothing ->
                        agentEntries
                            |> List.filter .isAvailable
                            |> List.filter agentIsInThisStation
                            |> List.head
           )


{-| Agents based elsewhere are listed in the station's Agents panel too, with
their location and distance in `agentLocation` (e.g. "Sarum Prime 0.9 - 1
jump"); an agent in this station has that field empty. Talking to a remote
agent works, but accepting its mission does not -- the game answers with a
"This mission cannot be accepted remotely" dialog, which the bot then sat in
front of forever. Seen live when a remote agent appeared at the top of the
list and was picked over the local one.
-}
agentIsInThisStation : EveOnline.ParseUserInterface.StationAgentEntry -> Bool
agentIsInThisStation agentEntry =
    case agentEntry.agentLocation of
        Nothing ->
            True

        Just location ->
            String.trim location |> String.isEmpty


{-| Every objective is done and the only thing left is to report back. The
mission tracker announces this by adding a "Complete Mission" objective, which
is a cleaner signal than an empty overview -- the overview is also empty
between waves of a fight.
-}
missionIsReadyToComplete : EveOnline.ParseUserInterface.AgentMissionInfoPanelEntry -> Bool
missionIsReadyToComplete mission =
    mission.objectiveTitles
        |> List.any (stringContainsIgnoringCase "complete mission")


{-| The label on the mission tracker's travel button, if it currently has one
and it names a step worth taking. No label means the ship is on grid and it is
the bot's own job to act (fight, loot, or take an acceleration gate) rather
than to travel.

Feedback: the same button turns into "Abort Undock" for the several seconds
an undock takes, and clicking whatever label it happens to show made the bot
cancel its own undock and then start it again, forever. Observed live as an
Undock/Abort Undock loop. Labels that undo the step in progress are therefore
not travel steps at all -- while one is showing, the right move is to wait for
the action already under way to finish.
-}
missionTravelStep : BotDecisionContext -> Maybe ( String, EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion )
missionTravelStep context =
    missionInfoPanelEntry context
        |> Maybe.andThen .locationButton
        |> Maybe.andThen
            (\button ->
                case button.label of
                    Just label ->
                        if labelUndoesStepInProgress label then
                            Nothing

                        else if routeIsSet context && labelSetsRoute label then
                            -- The route already exists; "Set Destination" /
                            -- "Destination Set" would only re-set it. In space
                            -- the caller travels the route instead; docked,
                            -- there is nothing to do but wait for the button
                            -- to offer "Undock".
                            Nothing

                        else
                            Just ( label, button.uiNode )

                    Nothing ->
                        Nothing
            )


routeIsSet : BotDecisionContext -> Bool
routeIsSet context =
    context.readingFromGameClient
        |> infoPanelRouteFirstMarkerFromReadingFromGameClient
        |> (/=) Nothing


labelUndoesStepInProgress : String -> Bool
labelUndoesStepInProgress label =
    [ "abort", "cancel" ]
        |> List.any (\pattern -> stringContainsIgnoringCase pattern label)


{-| Clicking the tracker's travel button changes what that button says next,
so the same "act at most once per reading" rule the agent conversation needs
applies here too -- see `previousStepClickedMouse`.
-}
clickMissionTravelButton :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> DecisionPathNode
clickMissionTravelButton context label buttonNode =
    if previousStepClickedMouse context then
        describeBranch
            ("The mission tracker offers '"
                ++ label
                ++ "', but I clicked on the previous step -- wait for the reading to catch up."
            )
            waitForProgressInGame

    else
        describeBranch
            ("The mission tracker offers the next travel step: '" ++ label ++ "'.")
            (clickUiElement buttonNode)



{-| The mission cargo a courier objective wants in the hold, if any. Empty for
combat missions, and empty again once the objective moves on -- which is what
tells the bot the load succeeded, without having to re-select the ship in the
inventory to inspect its hold.
-}
courierCargoToLoad : BotDecisionContext -> Maybe String
courierCargoToLoad context =
    missionInfoPanelEntry context
        |> Maybe.map .objectNamesToCarry
        |> Maybe.withDefault []
        |> List.head


loadCourierCargoDescribed : BotDecisionContext -> String -> Maybe DecisionPathNode
loadCourierCargoDescribed context itemName =
    loadCourierCargo context itemName
        |> Maybe.map
            (describeBranch ("This mission wants '" ++ itemName ++ "' in the cargo hold."))


{-| Some missions want an item that is sitting in a cargo container on grid
rather than in the station hangar -- "Get the Relic" asks for an `Ancient
Amarrian Relic` that is inside a `Cargo Container - Ancient Amarrian Relic`
27 km away. Same objective wording as a courier pickup, different place to get
it from, so the in-space case is handled here and the station case in
`loadCourierCargo`.

Reuses the wreck-looting shape the anomaly bot already had: open the container's
cargo, then click its "Loot All". The menu-entry priority list includes
"approach" for the same reason the acceleration gate's does -- from outside
looting range the menu offers that instead, and a later tick's fresh right-click
finds the loot entries once in range.
-}
lootMissionItemFromContainerIfPresent : BotDecisionContext -> Maybe DecisionPathNode
lootMissionItemFromContainerIfPresent context =
    case courierCargoToLoad context of
        Nothing ->
            Nothing

        Just itemName ->
            case context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
                Just openLootWindow ->
                    Just
                        (describeBranch ("A container is open -- take the " ++ itemName ++ ".")
                            (case openLootWindow.uiNode |> findUiElementWithText "Loot All" of
                                Just lootAllButton ->
                                    describeBranch "Click 'Loot All'." (clickUiElement lootAllButton)

                                Nothing ->
                                    describeBranch "I see no 'Loot All' in the open container."
                                        askForHelpToGetUnstuck
                            )
                        )

                Nothing ->
                    lootableHoldingMissionItem context itemName
                        |> Maybe.map
                            (\containerEntry ->
                                let
                                    distanceInMeters =
                                        containerEntry.objectDistanceInMeters
                                            |> Result.withDefault 999999
                                in
                                if lootingRangeInMeters < distanceInMeters then
                                    -- "Open Cargo" is offered at any distance but
                                    -- silently does nothing from outside looting
                                    -- range -- observed live, re-clicked once per
                                    -- tick at 7,875 m with no window ever opening
                                    -- and no error. Unlike an acceleration gate,
                                    -- which turns the same click into an approach,
                                    -- a container has to be approached explicitly.
                                    describeBranch
                                        ("The container holding the "
                                            ++ itemName
                                            ++ " is "
                                            ++ String.fromInt distanceInMeters
                                            ++ " m away -- too far to loot, approach it first."
                                        )
                                        (useContextMenuCascadeOnOverviewEntry
                                            (useMenuEntryWithTextContainingFirstOf
                                                [ "approach" ]
                                                menuCascadeCompleted
                                            )
                                            containerEntry
                                            context
                                        )

                                else
                                    describeBranch
                                        (if
                                            [ containerEntry.objectName, containerEntry.objectType ]
                                                |> List.filterMap identity
                                                |> List.any (stringContainsIgnoringCase itemName)
                                         then
                                            "I see a container holding the " ++ itemName ++ " -- open it."

                                         else
                                            -- Nothing on the overview names the
                                            -- item, so this is a blind look
                                            -- inside a wreck. Said plainly,
                                            -- because a log claiming a precise
                                            -- match here would be misleading.
                                            "Look inside "
                                                ++ (containerEntry.objectName
                                                        |> Maybe.withDefault "this wreck"
                                                   )
                                                ++ " for the "
                                                ++ itemName
                                                ++ "."
                                        )
                                        (useContextMenuCascadeOnOverviewEntry
                                            (useMenuEntryWithTextContainingFirstOf
                                                [ "Loot All", "Open Cargo" ]
                                                menuCascadeCompleted
                                            )
                                            containerEntry
                                            context
                                        )
                            )


{-| How close the ship has to be before a container can be opened. EVE's own
limit is 2,500 m; this stays inside that so the ship is not sitting exactly on
the boundary when the click lands.
-}
lootingRangeInMeters : Int
lootingRangeInMeters =
    2000


{-| Where to look next for a wanted item, nearest first.

Two cases, and the distinction matters. A container the mission *placed* names its
contents in its own overview row ("Cargo Container - Ancient Amarrian Relic"), so
it can be picked out precisely by the item name. A wreck cannot: its overview row
carries the name of the ship that died, never a hint of what is inside it. So for
the missions that want cargo out of ships you destroy, there is nothing to match
on and the only option is to open wrecks and see -- which is exactly what a player
does. The objective clearing is what tells us the right one was found.

Named containers are preferred over wrecks so a mission with both does not waste
ticks rummaging through wrecks first, and the `prefer-wreck` setting can push
particular hulls ahead of the rest -- on "Smuggler Interception" the Militants
are all in the Blood Raider Personnel Transports, which cut 26 wreck-opens down
to a handful. That mapping is domain knowledge the objective does not contain,
which is why it is a setting rather than something derived.

This terminates because the overview is configured to hide empty wrecks (see the
setup instructions at the top of this file): each one the bot empties drops out
of the candidate list, so the search shrinks rather than cycling. That setting is
load-bearing here, not cosmetic.
-}
lootableHoldingMissionItem :
    BotDecisionContext
    -> String
    -> Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
lootableHoldingMissionItem context itemName =
    let
        entriesMatching predicate =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter predicate
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        textsOfEntry entry =
            [ entry.objectName, entry.objectType ] |> List.filterMap identity

        namedForTheItem entry =
            textsOfEntry entry |> List.any (stringContainsIgnoringCase itemName)

        isLootableHulk entry =
            textsOfEntry entry
                |> List.any
                    (\text ->
                        [ "wreck", "cargo container" ]
                            |> List.any (\pattern -> stringContainsIgnoringCase pattern text)
                    )

        isPreferredWreck entry =
            isLootableHulk entry
                && (context.eventContext.botSettings.preferWreckNames
                        |> List.any
                            (\preferred ->
                                textsOfEntry entry |> List.any (stringContainsIgnoringCase preferred)
                            )
                   )
    in
    [ entriesMatching namedForTheItem
    , entriesMatching isPreferredWreck
    , entriesMatching isLootableHulk
    ]
        |> List.concat
        |> List.head


{-| Put the mission cargo in the ship's hold: narrow the hangar down with the
quick filter, then drag the item onto the ship's own inventory entry.

The steps are ordered by what is *observable* rather than by what a human would
do, because this client build gives no way to tell which container is currently
selected -- it has no `subCaptionLabel` node, so `subCaptionLabelText` is always
Nothing here. So instead of "select hangar, then filter, then drag", the order is
"drag if the item is visible; if not, fix the filter; if that is already right,
switch container". Each branch changes something the next reading can see, so the
sequence converges without ever needing to know the selection directly.
-}
loadCourierCargo : BotDecisionContext -> String -> Maybe DecisionPathNode
loadCourierCargo context itemName =
    case context.readingFromGameClient.inventoryWindows |> List.head of
        Nothing ->
            Nothing

        Just inventoryWindow ->
            let
                -- The ship's cargo hold carries the ship's own name ("Middling
                -- (Omen Navy Issue)"), so it cannot be found by label; it is
                -- identified by its node type instead.
                shipCargoTreeEntry =
                    inventoryWindow.leftTreeEntries
                        |> List.filter
                            (.uiNode >> .uiNode >> .pythonObjectTypeName >> (==) "TreeViewEntryInventoryCargo")
                        |> List.head

                itemHangarTreeEntry =
                    inventoryWindow.leftTreeEntries
                        |> List.filter (.text >> stringContainsIgnoringCase "item hangar")
                        |> List.head

                itemsInView =
                    case inventoryWindow.selectedContainerInventory |> Maybe.andThen .itemsView of
                        Just (EveOnline.ParseUserInterface.InventoryItemsListView listView) ->
                            listView.items |> List.map .uiNode

                        Just (EveOnline.ParseUserInterface.InventoryItemsNotListView notListView) ->
                            notListView.items

                        Nothing ->
                            []

                matchingItem =
                    itemsInView
                        |> List.filter
                            (\itemNode ->
                                itemNode.uiNode
                                    |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                                    |> List.any (stringContainsIgnoringCase itemName)
                            )
                        |> List.head

                lookingAtACapacityLimitedContainer =
                    case inventoryWindow.selectedContainerCapacityGauge of
                        Just (Ok gauge) ->
                            gauge.maximum /= Nothing

                        _ ->
                            False

                filterIsAlreadySet =
                    inventoryWindow.quickFilterText
                        |> Maybe.map (\current -> String.toLower current == expectedQuickFilterText itemName)
                        |> Maybe.withDefault False
            in
            case ( matchingItem, shipCargoTreeEntry ) of
                ( Just itemNode, Just shipCargo ) ->
                    Just <|
                    if previousStepClickedMouse context then
                        -- A drag needs the same one-reading pause a click does.
                        -- Observed live: the first drag landed, but two more
                        -- went out before the reading caught up with it. Harmless
                        -- for a single indivisible item, not harmless for a
                        -- stack, where a repeat drag can open a quantity dialog
                        -- or move part of it somewhere unintended.
                        describeBranch
                            "I just dragged -- wait for the reading to catch up before dragging again."
                            waitForProgressInGame

                    else
                        describeBranch
                            ("Drag '" ++ itemName ++ "' into the ship's cargo hold.")
                            (dragAndDropUiElement itemNode
                                (shipCargo.selectRegion |> Maybe.withDefault shipCargo.uiNode)
                            )

                ( Just _, Nothing ) ->
                    Just
                        (describeBranch
                            "I found the mission cargo but no ship cargo hold in the inventory to drag it into."
                            askForHelpToGetUnstuck
                        )

                ( Nothing, _ ) ->
                    if not filterIsAlreadySet then
                        inventoryWindow.quickFilterInputBox
                            |> Maybe.map
                                (\filterBox ->
                                    if previousStepClickedMouse context then
                                        describeBranch
                                            "I just clicked the quick-filter box -- wait for the reading to catch up before typing."
                                            waitForProgressInGame

                                    else
                                        describeBranch
                                            ("Filter the inventory for '" ++ itemName ++ "'.")
                                            (decideActionForCurrentStep
                                                (List.concat
                                                    [ mouseClickOnUIElement MouseButtonLeft filterBox
                                                        |> Result.withDefault []
                                                    , selectAllEffects
                                                    , typeTextEffects itemName
                                                    ]
                                                )
                                            )
                                )

                    else if lookingAtACapacityLimitedContainer && itemHangarTreeEntry /= Nothing then
                        -- Filtered, but looking at a hold with a capacity limit
                        -- (the ship's own, most likely) rather than the station
                        -- hangar, which reports no maximum. Switch once and let
                        -- the next reading decide.
                        itemHangarTreeEntry
                            |> Maybe.map
                                (\itemHangar ->
                                    describeBranch
                                        ("Look for '" ++ itemName ++ "' in the item hangar.")
                                        (clickUiElement (itemHangar.selectRegion |> Maybe.withDefault itemHangar.uiNode))
                                )

                    else
                        -- Filtered the station hangar and it is not there, so it
                        -- is not something we can load here. Give up rather than
                        -- loop: missions like "Get the Relic" want an item that
                        -- is in a container out in space, and returning Nothing
                        -- lets the caller undock and go find it.
                        Nothing


{-| What the quick-filter box will read once `typeTextEffects` has typed the
item name into it: lowercase, and without the characters that have no plain
virtual-key code. Used to tell "the filter is already what I want" from "the
filter still needs setting", so the bot does not retype it every tick.
-}
expectedQuickFilterText : String -> String
expectedQuickFilterText itemName =
    itemName
        |> String.toList
        |> List.filter (\char -> virtualKeyCodeForTypedCharacter char /= Nothing)
        |> String.fromList
        |> String.toLower


{-| Ctrl+A, so typing replaces whatever the filter box already held rather than
appending to it.
-}
selectAllEffects : List EffectOnWindow.EffectOnWindowStruct
selectAllEffects =
    [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL
    , EffectOnWindow.KeyDown EffectOnWindow.vkey_A
    , EffectOnWindow.KeyUp EffectOnWindow.vkey_A
    , EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL
    ]


{-| Type plain text as individual key presses.

`CharacterDown`/`CharacterUp` -- the effects meant for real text input -- are not
implemented by the macOS host, but the Windows virtual-key code for an ASCII
letter, digit or space is just the character's own uppercase code point, and
those the host does map. Unsupported characters are dropped rather than guessed:
the filter is a substring match, so a name that loses its punctuation still
narrows the hangar down.
-}
typeTextEffects : String -> List EffectOnWindow.EffectOnWindowStruct
typeTextEffects text =
    text
        |> String.toList
        |> List.filterMap virtualKeyCodeForTypedCharacter
        |> List.concatMap (\key -> [ EffectOnWindow.KeyDown key, EffectOnWindow.KeyUp key ])


virtualKeyCodeForTypedCharacter : Char -> Maybe EffectOnWindow.VirtualKeyCode
virtualKeyCodeForTypedCharacter char =
    let
        code =
            char |> Char.toUpper |> Char.toCode
    in
    if (0x41 <= code && code <= 0x5A) || (0x30 <= code && code <= 0x39) || code == 0x20 then
        Just (EffectOnWindow.VirtualKeyCodeFromInt code)

    else
        Nothing


{-| Drag one UI element onto another.

Both endpoints go through the same visible-region check a click does, so a
covered node is refused rather than dragged from a place the player cannot see.
The waypoint in the middle is what makes EVE read this as a drag at all -- see
the host's own `_cg_move`, which only emits macOS drag events while a button is
held.
-}
dragAndDropUiElement :
    EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> DecisionPathNode
dragAndDropUiElement fromElement toElement =
    let
        centerOf element =
            element.totalDisplayRegionVisible |> EveOnline.ParseUserInterface.centerFromDisplayRegion

        from =
            centerOf fromElement

        to =
            centerOf toElement
    in
    decideActionForCurrentStep
        (EffectOnWindow.effectsForDragAndDrop
            { startLocation = from
            , mouseButton = MouseButtonLeft
            , waypointsPositionsInBetween =
                [ { x = (from.x + to.x) // 2, y = (from.y + to.y) // 2 } ]
            , endLocation = to
            }
        )


{-| The mission tracker can be collapsed to just its title row, which removes
the objectives and the travel button from the tree altogether. That reads
exactly like "there is no travel step right now", so the bot would quietly
wait for a step that can never appear -- seen live mid-mission. Expanding it
again is cheap and safe, so do that before trusting anything else the tracker
does or does not say.
-}
expandMissionTrackerIfCollapsed : BotDecisionContext -> Maybe DecisionPathNode
expandMissionTrackerIfCollapsed context =
    case missionInfoPanelEntry context of
        Nothing ->
            Nothing

        Just mission ->
            if mission.isExpanded then
                Nothing

            else if previousStepClickedMouse context then
                Just
                    (describeBranch
                        "The mission tracker is collapsed, but I clicked on the previous step -- wait for the reading to catch up."
                        waitForProgressInGame
                    )

            else
                -- Deliberately not the title label: the header row's last
                -- child (`progress_fill_container`) spans the whole row and
                -- covers every label and button in it, so the framework's
                -- occlusion-aware click refuses those nodes and emits no
                -- effects at all -- seen live as this branch repeating
                -- forever without a single mouse event. Click whatever is
                -- genuinely on top at that spot instead, by picking the
                -- descendant with the largest *visible* area.
                (mission.uiNode
                    :: EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion mission.uiNode
                )
                    |> List.sortBy
                        (.totalDisplayRegionVisible
                            >> EveOnline.ParseUserInterface.areaFromDisplayRegion
                            >> Maybe.withDefault 0
                            >> negate
                        )
                    |> List.head
                    |> Maybe.map
                        (\clickTarget ->
                            describeBranch
                                "The mission tracker is collapsed -- expand it so I can see the objectives again."
                                (clickUiElement clickTarget)
                        )


shouldDeclineMission : BotDecisionContext -> Maybe String -> Bool
shouldDeclineMission context missionName =
    case missionName of
        Nothing ->
            False

        Just name ->
            context.eventContext.botSettings.missionNamesToDecline
                |> List.any (\toDecline -> stringContainsIgnoringCase toDecline name)



-- Docked


decideActionWhenDocked : BotDecisionContext -> DecisionPathNode
decideActionWhenDocked context =
    case context.readingFromGameClient.agentConversationWindows |> List.head of
        Just conversation ->
            decideActionInAgentConversation context conversation

        Nothing ->
            decideActionWhenDockedWithoutConversation context


decideActionWhenDockedWithoutConversation : BotDecisionContext -> DecisionPathNode
decideActionWhenDockedWithoutConversation context =
    -- The tracker is expanded first, before even the readiness test: a
    -- collapsed tracker hides the objectives as well as the travel button, so
    -- "is the mission ready to hand in?" also reads False while collapsed.
    case expandMissionTrackerIfCollapsed context of
        Just expandTracker ->
            expandTracker

        Nothing ->
            case courierCargoToLoad context |> Maybe.andThen (loadCourierCargoDescribed context) of
                Just loadCargo ->
                    -- Load freight before travelling: the objective keeps asking
                    -- for it until it is in the hold, and flying on without it
                    -- just wastes the trip.
                    loadCargo

                Nothing ->
                    decideActionWhenDockedWithMissionTracker context


decideActionWhenDockedWithMissionTracker : BotDecisionContext -> DecisionPathNode
decideActionWhenDockedWithMissionTracker context =
            case missionInfoPanelEntry context of
                Just mission ->
                    -- The tracker's button is consulted before anything else,
                    -- including the "ready to hand in" case: once docked with a
                    -- finished mission it reads "Start Conversation", and going
                    -- through it guarantees we talk to the agent whose mission
                    -- this actually is rather than picking one out of the
                    -- station's list and hoping.
                    case missionTravelStep context of
                        Just ( label, buttonNode ) ->
                            clickMissionTravelButton context label buttonNode

                        Nothing ->
                            if missionIsReadyToComplete mission then
                                describeBranch "The mission is done -- talk to the agent to hand it in."
                                    (openAgentConversation context)

                            else
                                describeBranch
                                    "A mission is running but the tracker offers no travel step from here."
                                    waitForProgressInGame

                Nothing ->
                    describeBranch "No mission running -- get one from the agent."
                        (openAgentConversation context)


{-| Opens the conversation with the chosen agent. The lobby keeps the Agents
panel's nodes in the tree even while another tab is showing, so the agent's
chat button can be found without the panel being visible -- but clicking it
only works once the tab is actually selected, hence the explicit tab check.
-}
openAgentConversation : BotDecisionContext -> DecisionPathNode
openAgentConversation context =
    case context.readingFromGameClient.stationWindow of
        Nothing ->
            describeBranch "I do not see the station window." askForHelpToGetUnstuck

        Just stationWindow ->
            case stationWindow.agentsTab of
                Nothing ->
                    describeBranch "I do not see the station's Agents tab." askForHelpToGetUnstuck

                Just agentsTab ->
                    if not agentsTab.isSelected then
                        describeBranch "Select the station's Agents tab."
                            (clickUiElement agentsTab.uiNode)

                    else
                        case selectedAgentEntry context of
                            Nothing ->
                                describeBranch
                                    "I do not see an agent to talk to in this station."
                                    askForHelpToGetUnstuck

                            Just agentEntry ->
                                case agentEntry.conversationButton of
                                    Nothing ->
                                        describeBranch
                                            "I see the agent but not its conversation button."
                                            askForHelpToGetUnstuck

                                    Just conversationButton ->
                                        describeBranch
                                            ("Start a conversation with "
                                                ++ (agentEntry.name |> Maybe.withDefault "the agent")
                                                ++ "."
                                            )
                                            (clickUiElement conversationButton)


{-| Whether the previous step clicked a mouse button. Used to make the agent
conversation act at most once per reading.

Feedback: this is the fix for a real, expensive incident. Clicking a button
in the conversation re-lays out the whole button row, and the rows of the
two states overlap almost exactly -- "Accept" in the offer state spans
x=1262-1345, centre 1303, while "Quit Mission" in the accepted state spans
x=1300-1436. So a second click at the coordinates computed for "Accept",
issued before the reading caught up with the state the first click caused,
lands three pixels inside "Quit Mission" and opens its confirmation dialog.
Observed live on the first real run. Waiting a step after any click, rather
than trusting the coordinates, is the only thing that makes this safe --
re-reading is not enough on its own, because the danger is precisely that
the reading is one step behind the UI.
-}
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


decideActionInAgentConversation :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.AgentConversationWindow
    -> DecisionPathNode
decideActionInAgentConversation context conversation =
    if previousStepClickedMouse context then
        describeBranch
            "I clicked in the conversation on the previous step -- wait for the reading to catch up before clicking again."
            waitForProgressInGame

    else
        decideActionInAgentConversationAfterReadingSettled context conversation


decideActionInAgentConversationAfterReadingSettled :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.AgentConversationWindow
    -> DecisionPathNode
decideActionInAgentConversationAfterReadingSettled context conversation =
    let
        buttonNamed name =
            conversation.buttons
                |> List.filter (.name >> (==) name)
                |> List.head
                |> Maybe.map .uiNode

        missionReadyToComplete =
            missionInfoPanelEntry context
                |> Maybe.map missionIsReadyToComplete
                |> Maybe.withDefault False

        closeConversation reason =
            case buttonNamed "CloseAgentConversation_Button" of
                Just closeButton ->
                    describeBranch reason (clickUiElement closeButton)

                Nothing ->
                    describeBranch (reason ++ " (but I see no button to close the conversation)")
                        waitForProgressInGame
    in
    case ( buttonNamed "CompleteMission_Button", missionReadyToComplete ) of
        ( Just completeButton, True ) ->
            describeBranch "Hand the finished mission in." (clickUiElement completeButton)

        ( Just _, False ) ->
            -- "Complete Mission" is offered throughout the mission, not only
            -- once it can succeed, so a mission still in progress means we are
            -- done talking and should go fly it.
            closeConversation "The mission is still in progress -- go fly it."

        ( Nothing, _ ) ->
            case buttonNamed "AcceptMission_Button" of
                Just acceptButton ->
                    let
                        -- From the agent's own briefing, not the info panel:
                        -- the mission tracker does not exist until the mission
                        -- is accepted, so it cannot name a mission we are still
                        -- deciding whether to take.
                        offeredMissionName =
                            conversation.offeredMissionName
                    in
                    if shouldDeclineMission context offeredMissionName then
                        case buttonNamed "DeferMission_Button" of
                            Just deferButton ->
                                -- "Delay" rather than "Decline": declining more
                                -- than once every four hours costs standing
                                -- with the agent, delaying does not.
                                describeBranch
                                    ("Skip this mission ("
                                        ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                        ++ ") using 'Delay'."
                                    )
                                    (clickUiElement deferButton)

                            Nothing ->
                                closeConversation "I want to skip this mission but see no 'Delay' button."

                    else
                        describeBranch
                            ("Accept the mission '"
                                ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                ++ "'."
                            )
                            (clickUiElement acceptButton)

                Nothing ->
                    case buttonNamed "RequestMission_Button" of
                        Just requestButton ->
                            describeBranch "Ask the agent for a mission."
                                (clickUiElement requestButton)

                        Nothing ->
                            closeConversation "This conversation offers nothing I need."



-- In space


decideActionWhenInSpace : BotDecisionContext -> SeeUndockingComplete -> DecisionPathNode
decideActionWhenInSpace context seeUndockingComplete =
    clearStrayContextMenu context
        |> Maybe.withDefault
            (if seeUndockingComplete.shipUI |> shipUIIndicatesShipIsWarpingOrJumping then
                describeBranch "I am in warp."
                    (returnDronesToBay context |> Maybe.withDefault waitForProgressInGame)

             else
                case
                    if anyAttackableInOverview (objectNamesToAttack context) context.readingFromGameClient then
                        seeUndockingComplete
                            |> shipUIModulesToActivateAlways
                            |> List.filter (.isActive >> Maybe.withDefault False >> not)
                            |> List.head

                    else
                        Nothing
                of
                    Just inactiveModule ->
                        describeBranch "Inactive module should be active"
                            (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)

                    Nothing ->
                        decideActionInMissionPocket context seeUndockingComplete
            )


{-| Priority on grid: finish the fight, then the looting, and only then
travel. The mission tracker's own travel step is checked before acceleration
gates because it is the authoritative "where to next" -- while a pocket still
has to be entered the tracker carries no label at all, so the gate branch is
reached; once the mission is done the tracker says "Dock", which correctly
wins over a gate that is still sitting on the overview.
-}
decideActionInMissionPocket : BotDecisionContext -> SeeUndockingComplete -> DecisionPathNode
decideActionInMissionPocket context seeUndockingComplete =
    let
        travelTheRoute =
            -- A mission in another solar system: the tracker's button only
            -- sets the route, it does not fly it, so travel gate by gate
            -- until the tracker has something else to offer.
            describeBranch "A route is set -- travel towards the mission's system."
                (jumpToNextSystem context)
    in
    decideActionInCombat context seeUndockingComplete
        (case expandMissionTrackerIfCollapsed context of
            Just expandTracker ->
                expandTracker

            Nothing ->
                case lootMissionItemFromContainerIfPresent context of
                  Just lootIt ->
                    lootIt

                  Nothing ->
                    case missionTravelStep context of
                    Just ( label, buttonNode ) ->
                        ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                            (clickMissionTravelButton context label buttonNode)

                    Nothing ->
                        activateAccelerationGateIfPresent context
                            |> Maybe.withDefault
                                (if routeIsSet context then
                                    travelTheRoute

                                 else
                                    describeBranch
                                        "Nothing to fight and no travel step offered -- wait for the mission to catch up."
                                        waitForProgressInGame
                                )
        )

{-| Whether the tracker's button is talking about the route rather than
offering a step to take right now. The button says "Set Destination" before
the route exists and "Destination Set" afterwards, and neither one flies the
route -- so once a route is set, both mean "travel", not "click me".
-}
labelSetsRoute : String -> Bool
labelSetsRoute label =
    stringContainsIgnoringCase "destination" label


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
                           these dialogs guard destructive actions (the
                           "Quit Mission?" one cost a mission's standing once
                           already), so the bot's automatic reply must always
                           be the one that declines.

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

{-| Dock, preferring a particular station by name when one is given.

The preferred name is only a priority, not a requirement: if no menu entry
matches it -- most often because that station is in another solar system and so
is not in the surroundings menu at all -- this falls through to the previous
behaviour of taking the first station offered. Being parked somewhere safe beats
staying in space, and at session end there is not necessarily time to fly home.

2020-07-11 discovery by Viktor, which is why the cascade nests the same choice
twice: the entries for structures in the menu from the SurroundingsButton can be
nested one level deeper than the ones for stations, so not all structures appear
directly under the "structures" entry.
-}
dockAtStation : Maybe String -> BotDecisionContext -> DecisionPathNode
dockAtStation preferredStationName context =
    let
        withTextContainingIgnoringCase textToSearch =
            List.filter (.text >> String.toLower >> (==) (textToSearch |> String.toLower)) >> List.head

        menuEntryIsSuitable menuEntry =
            [ "cyno beacon", "jump gate" ]
                |> List.any (\toAvoid -> menuEntry.text |> stringContainsIgnoringCase toAvoid)
                |> not

        preferredStationPriority =
            case preferredStationName of
                Nothing ->
                    []

                Just stationName ->
                    [ List.filter (.text >> stringContainsIgnoringCase stationName) >> List.head ]

        chooseNextMenuEntry followingChoice =
            MenuEntryWithCustomChoice
                { describeChoice =
                    case preferredStationName of
                        Just stationName ->
                            "'" ++ stationName ++ "' if offered, else dock wherever we can"

                        Nothing ->
                            "Dock if we can?"
                , chooseEntry =
                    \currentMenu ->
                        let
                            suitableMenuEntries =
                                List.filter menuEntryIsSuitable currentMenu.entries
                        in
                        (preferredStationPriority
                            ++ [ withTextContainingIgnoringCase "Dock"
                               , List.filter (.text >> stringContainsIgnoringCase "station")
                                    >> Common.Basics.listElementAtWrappedIndex 0
                               , Common.Basics.listElementAtWrappedIndex 0
                               ]
                        )
                            |> List.filterMap (\priority -> suitableMenuEntries |> priority)
                            |> List.head
                            |> Maybe.map (\menuEntry -> ( menuEntry, followingChoice ))
                }
    in
    returnDronesToBay context
        |> Maybe.withDefault
            (describeBranch "Head for a station and dock."
                (useContextMenuCascadeOnListSurroundingsButton
                    (useMenuEntryWithTextContainingFirstOf [ "structures", "station" ]
                        (chooseNextMenuEntry
                            (chooseNextMenuEntry MenuCascadeCompleted)
                        )
                    )
                    context
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
                    


{-| The fight itself. Structurally the anomaly bot's combat loop with the
anomaly-specific parts removed: there is no "wait in case more rats arrive"
timer and no tethering, because the mission tracker tells us when the pocket
is actually finished. `continueIfCombatComplete` is what to do once there is
nothing left to shoot or loot.
-}
decideActionInCombat :
    BotDecisionContext
    -> SeeUndockingComplete
    -> DecisionPathNode
    -> DecisionPathNode
decideActionInCombat context seeUndockingComplete continueIfCombatComplete =
    let
        overviewEntriesToAttack =
            overviewEntriesToAttackFromReadingFromGameClient
                (objectNamesToAttack context)
                context.readingFromGameClient

        overviewEntriesToLock =
            overviewEntriesToAttack
                |> List.take context.eventContext.botSettings.maxTargetCount
                |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

        targetsToUnlock =
            targetsToUnlockFromReadingFromGameClient context.readingFromGameClient

        activeTargetEntry =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head

        ensureShipIsOrbitingDecision =
            activeTargetEntry
                |> Maybe.andThen (ensureShipIsOrbiting seeUndockingComplete.shipUI)

        ensureShipIsKeepingRangeDecision =
            activeTargetEntry
                |> Maybe.andThen (ensureShipIsKeepingRange seeUndockingComplete.shipUI)

        notableWreckEntries =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter isNotableWreck
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        decisionIfNoEnemyToAttack =
            case context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
                Just openInventoryWindow ->
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
                            continueIfCombatComplete

        decisionToKillRats =
            case targetsToUnlock |> List.head of
                Just targetToUnlock ->
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
                                    describeBranch "The active target looks like a container/wreck, not a rat -- hold fire."
                                        waitForProgressInGame

                                 else
                                    case
                                        seeUndockingComplete
                                            |> shipUIModulesToActivateOnTarget
                                            |> List.indexedMap Tuple.pair
                                            |> List.filter (Tuple.second >> .isActive >> Maybe.withDefault False >> not)
                                            |> List.head
                                    of
                                        Nothing ->
                                            describeBranch "All guns cycling"
                                                (launchAndEngageDrones context
                                                    |> Maybe.withDefault
                                                        (describeBranch "No idling drones."
                                                            (case overviewEntriesToLock of
                                                                [] ->
                                                                    describeBranch "Everything worth locking is locked."
                                                                        waitForProgressInGame

                                                                nextOverviewEntryToLock :: _ ->
                                                                    describeBranch "Lock more targets."
                                                                        (lockTargetFromOverviewEntry context nextOverviewEntryToLock)
                                                            )
                                                        )
                                                )

                                        Just ( inactiveModuleIndex, inactiveModule ) ->
                                            describeBranch "Cycle combat mod"
                                                (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
                                )
    in
    if overviewEntriesToAttack |> List.isEmpty then
        decisionIfNoEnemyToAttack

    else if context.eventContext.botSettings.orbitInCombat == AppSettings.Yes then
        ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToKillRats

    else if context.eventContext.botSettings.keepAtRange == AppSettings.Yes then
        ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToKillRats

    else
        decisionToKillRats


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
            , decideNextStep = missionBotDecisionRoot
            }
    }


initBotMemory : BotMemory
initBotMemory =
    { lastDockedStationNameFromInfoPanel = Nothing
    , shipModules = EveOnline.BotFramework.initShipModulesMemory
    , shipWarpingInLastReading = Nothing
    , contextMenuLastDepth = 0
    , contextMenuStuckTicks = 0
    , lootWindowOpenTicks = 0
    , routeFirstMarkerRegion = Nothing
    , routeFirstMarkerUnchangedTicks = 0
    , targetToUnlockRegion = Nothing
    , targetToUnlockUnchangedTicks = 0
    }


statusTextFromState : BotDecisionContext -> String
statusTextFromState context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        describePerformance =
            case missionInfoPanelEntry context of
                Just mission ->
                    "Mission: "
                        ++ (mission.missionName |> Maybe.withDefault "unnamed")
                        ++ " -- "
                        ++ (mission.instructionTexts |> List.head |> Maybe.withDefault "no instruction")
                        ++ (case mission.locationButton |> Maybe.andThen .label of
                                Just label ->
                                    " (next step: " ++ label ++ ")"

                                Nothing ->
                                    ""
                           )

                Nothing ->
                    "No mission running."

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
                    , [ describeOverview ]
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


{-| Whether to shoot this overview entry. Rats are recognised by their icon
colour, but some missions require destroying a structure -- a "Drone Silo" and
other Large Collidable Objects -- and those are neutral objects with no
hostile colouring at all, so no colour test will ever match them. They have to
be named explicitly via the `attack-object` setting.

Note the structure must also be *visible*: Large Collidable Objects are off by
default in the overview's type filters, and the bot can only act on what the
overview shows it.
-}
shouldAttackOverviewEntry : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry namesToAttack overviewEntry =
    iconSpriteHasColorOfRat overviewEntry
        || isObjectToAttackByName namesToAttack overviewEntry


isObjectToAttackByName : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectToAttackByName namesToAttack overviewEntry =
    let
        textsToCheck =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
    in
    namesToAttack
        |> List.any
            (\nameToAttack ->
                textsToCheck |> List.any (stringContainsIgnoringCase nameToAttack)
            )


{-| Non-rat objects worth shooting: whatever the mission objective names as a
destruction target, plus anything listed in the settings. The objective is the
primary source -- it already says which structure the mission means -- and the
`attack-object` setting stays as a manual override for cases it does not cover.
-}
objectNamesToAttack : BotDecisionContext -> List String
objectNamesToAttack context =
    (missionInfoPanelEntry context
        |> Maybe.map .objectNamesToDestroy
        |> Maybe.withDefault []
    )
        ++ context.eventContext.botSettings.attackObjectNames


{-| Factored out of decideActionInCombat's own overviewEntriesToAttack /
targetsToUnlock let-bindings so updateMemoryForNewReadingFromGame can
compute the same "target to unlock" identity from just a reading (no bot
settings needed) -- used to track how long it's stayed in the same place,
see routeFirstMarkerUnchangedTicks-style tracking on BotMemory below.
-}
overviewEntriesToAttackFromReadingFromGameClient : List String -> ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
overviewEntriesToAttackFromReadingFromGameClient namesToAttack readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.filter (shouldAttackOverviewEntry namesToAttack)


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
anyAttackableInOverview : List String -> ReadingFromGameClient -> Bool
anyAttackableInOverview namesToAttack readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.any (shouldAttackOverviewEntry namesToAttack)


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
loot before leaving the pocket. Checks both name and type since which one
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

This is the single gate every warp/travel action goes through, so fixing
drone recall here covers every caller rather than each of them needing its
own explicit `returnDronesToBay` step.
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

    in
    { lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , shipModules =
        botMemoryBefore.shipModules
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory context.readingFromGameClient
    , shipWarpingInLastReading = shipIsWarping
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
    }


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
