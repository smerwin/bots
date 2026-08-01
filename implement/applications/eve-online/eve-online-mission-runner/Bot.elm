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

   That tracker is the bot's only route out of the station, and it exists only
   for a mission that is **tracked** -- see the setup list below. Accepting a
   mission is not enough. Untracked, the panel entry is simply absent, which
   the bot reads as "no mission running": it asks the agent for one, the agent
   answers that a mission is already in progress, it closes the conversation,
   and it starts over. Run 103 did that 87 times without undocking.

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
   + Track the mission, so that it appears in the info panel. Open
     Opportunities (Alt-J), go to the "Active" tab, right-click the mission's
     card and choose "Track". Accepting a mission does not track it, and an
     untracked mission has no info-panel entry at all -- which is where every
     travel step comes from, so the bot never leaves the station. A character
     whose missions were tracked before keeps that; a fresh one does not, which
     is what makes this look like a bot fault rather than client setup.
   + In the ship UI, arrange the modules:
     + Place the modules to use in combat (to activate on targets) in the top row.
     + Place the propulsion module first in the middle row. The bot drives this
       slot on its own rule -- running while the ship crosses distance, off at a
       gate -- so it has to know which slot it is.
     + Place the modules to keep running (hardeners and the like) in the rest of
       the middle row.
     + Hide passive modules by disabling the check-box `Display Passive Modules`.
   + Keep the default drone keybinds: Shift+F launches, F engages, Shift+R recalls.
   + Configure the keyboard key 'W' to make the ship orbit.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit
   your use-case.

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

   + `agent-name` : Name of the agent to run missions for, as it appears in the
     station's Agents tab. Defaults to the first agent listed as available.
   + `decline-mission` : Name of a mission to skip rather than run. The bot uses
     the agent's "Delay" button rather than "Decline", since declining more than
     once every four hours costs standing. Repeatable.
   + `avoid-rat` : Name of a rat to avoid, as it appears in the overview. Repeatable.
   + `approach-object` : Name (or type) of an object to fly up to, e.g.
     `approach-object=Abandoned Mining Station`. Used in two places. When an
     objective says to approach something, these are tried after the name the
     objective gives, because its wording can name a decorative object rather
     than the one that actually satisfies it. And when the bot has run out of
     anything else to do on a grid -- nothing to shoot, no cargo it can find, no
     travel step, no gate, no route -- it closes on one of these as a last
     resort, which covers the objectives that are satisfied by proximity without
     ever saying so ("Interstellar Railroad" asks only for cargo, and the way to
     get it is to fly at a Large Collidable Object the brief never mentions).
     Repeatable.
   + `prefer-wreck` : Name (or type) of a wreck to search first when a mission
     wants cargo out of destroyed ships, e.g. `prefer-wreck=Personnel Transport`.
     Purely an optimisation -- the bot still opens every other wreck afterwards,
     so a wrong guess costs nothing but a wasted trip. Repeatable.
   + `attack-object` : Non-rat objects the bot should also shoot, as a
     comma-separated list -- `attack-object=Drone Silo, Repair Station`. The key
     may also be repeated; both accumulate. Each entry is matched **exactly**
     against the overview's Name or Type -- not as a substring of
     either. Give the full label as the overview shows it, e.g.
     `attack-object=Kruul's Pleasure Hub`. Substrings were tried and are a trap
     in both directions: `Warehouse` matched a station called "Bhizheba VIII -
     Moon 5 - Expert Distribution Warehouse", and `Habitat` matched every
     Habitation Module on every grid rather than the one the mission is about.
     Usually unnecessary: when a mission objective names a structure to destroy
     ("You need to destroy the <a ...>Drone Silo</a>"), the bot takes the name
     from the objective itself; this setting is the manual override for what
     that does not cover. Either way the object must be enabled in the
     overview's type filters (Large Collidable Objects are off by default) or
     the bot cannot see it at all. Repeatable.
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
import EveOnline.MemoryReading
import Json.Decode
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
        , EndDecisionPathStructure(..)
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
    , approachObjectNames = []
    , preferWreckNames = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No
    , targetingRangeMeters = 66000
    }


{-| One setting line, many values: `attack-object=Drone Silo, Repair Station`.

The list of structures a bot should shoot grows one mission at a time, and a
column of near-identical `attack-object=` lines is a poor way to hold it. Commas
separate, surrounding space is trimmed, and empties are dropped, so the line can
be edited like the list it is.

Comma rather than a JSON array because these settings reach the bot through a
shell string in the launcher: `["a","b"]` would need its quotes escaped there,
which is exactly the kind of punctuation that gets silently mangled. No EVE
object name in use contains a comma.

Repeating the key still works and still accumulates, so an existing settings
string keeps behaving as it did.
-}
splitSettingIntoNames : String -> List String
splitSettingIntoNames =
    String.split ","
        >> List.map String.trim
        >> List.filter (String.isEmpty >> not)


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
                (\objectNames settings ->
                    { settings
                        | attackObjectNames =
                            splitSettingIntoNames objectNames ++ settings.attackObjectNames
                    }
                )
           )
         , ( "approach-object"
           , AppSettings.valueTypeString
                (\objectName settings ->
                    { settings | approachObjectNames = String.trim objectName :: settings.approachObjectNames }
                )
           )
         , ( "prefer-wreck"
           , AppSettings.valueTypeString
                (\wreckName settings ->
                    { settings | preferWreckNames = String.trim wreckName :: settings.preferWreckNames }
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
    , approachObjectNames : List String
    , preferWreckNames : List String
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
    , shipApproachingTicks : Int
    , lootedWreckIds : List String
    , gateWithinReachTicks : Int
    , siteAdmitsThisShip : Maybe Bool
    , clearingNotRequired : Bool
    , agentConversationWithoutTrackerTicks : Int
    , keepAtRangeUnconfirmedTicks : Int
    , orbitUnconfirmedTicks : Int
    , readingsCount : Int
    , lowestShieldPercentSinceHealthy : Int
    , lowestArmorPercentSinceHealthy : Int
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
                                if secondsRemaining <= 0 then
                                    -- Parked with the session over, so stop.
                                    -- The host only *announces* the deadline --
                                    -- it does not stop its own loop -- so a bot
                                    -- that just parks here ticks on forever.
                                    -- Observed running 2h11m past a 180-minute
                                    -- session, printing "Already docked. Stay
                                    -- put." 7,633 times.
                                    describeBranch
                                        "Session over and docked -- finish."
                                        (Common.DecisionPath.endDecisionPath FinishSession)

                                else
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

                        else if labelReportsRouteAlreadySet label then
                            -- Nothing to click: the route is already set. In
                            -- space the caller travels it instead; docked,
                            -- there is nothing to do but wait for the button to
                            -- offer "Undock".
                            Nothing

                        else
                            Just ( label, button.uiNode )

                    Nothing ->
                        Nothing
            )


{-| Whether the autopilot actually has a destination.

Neither of the obvious tests works. `AutopilotDestinationIcon` is present in the
route panel whether or not a route exists, so the framework's
`infoPanelRouteFirstMarkerFromReadingFromGameClient` is always Just. And the
"No Destination" label keeps its *text* even once a route is set -- an earlier
attempt at this read that text and was simply wrong.

What does change is visibility: the panel hides `noDestinationLabel` and shows
`NextWaypointPanel` once a route exists. Confirmed by comparing two live
readings of the same panel, with and without a destination:

    no route:   NextWaypointPanel _display=False,  noDestinationLabel _display=True
    route set:  NextWaypointPanel _display=True,   noDestinationLabel _display=False
-}
routeIsSet : BotDecisionContext -> Bool
routeIsSet context =
    context.readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelRoute
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "NextWaypointPanel")
        |> List.any (.uiNode >> nodeIsDisplayed)


{-| The widget's own `_display` flag, defaulting to shown when absent (most
nodes never set it).
-}
nodeIsDisplayed : EveOnline.MemoryReading.UITreeNode -> Bool
nodeIsDisplayed uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


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


{-| How many readings to keep trying a gate that is already in range before
concluding it will not admit this ship. A working gate goes through in a few;
the restricted one was clicked 741 times over half an hour.
-}
gateRefusesThisShipTicks : Int
gateRefusesThisShipTicks =
    40


{-| Whether a mission's terms mention special ship restrictions at all.

This is only the question "is there a list?", **not** "are we excluded?" -- the
two were conflated for a long time and it was expensive. "After The Seven
(4 of 5)" reads "special ship restrictions" and grants a Caldari Shuttle because
its gates admit nothing larger; flown in a cruiser the bot sat at the gate and
clicked Activate Gate 741 times. But "Communications Cold War" carries the same
phrase and its restriction list *includes* the Omen Navy Issue we fly, and it
grants no ship at all. Treating the phrase as a refusal skipped a mission we
could fly and jammed the agent behind it -- 153 Delay clicks in one run, since a
deferred mission stays in the journal and stops the agent offering another.

So the phrase only decides whether to *ask*. `restrictionsAdmitThisShip` reads
the answer.

-}
missionHasSpecialShipRestrictions : EveOnline.ParseUserInterface.AgentConversationWindow -> Bool
missionHasSpecialShipRestrictions conversation =
    missionFinePrint conversation
        |> stringContainsIgnoringCase "special ship restrictions"


{-| The mission terms' "ship restrictions" link, which opens the site's permitted
list. It carries its caption in a `linkText` dict entry rather than the usual
`_setText`/`_text`, so an ordinary display-text sweep does not see it.
-}
shipRestrictionsLinkFromReading : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
shipRestrictionsLinkFromReading readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter
            (\node ->
                node.uiNode
                    |> EveOnline.ParseUserInterface.getStringPropertyFromDictEntries "linkText"
                    |> Maybe.map (stringContainsIgnoringCase "ship restrictions")
                    |> Maybe.withDefault False
            )
        |> List.head


{-| A window's close control, however this particular window carries it.

Three ways of asking, because the obvious two both failed on
`ShipRestrictionsWindow`. Matching the caption cannot work: the control is a
`ButtonIcon` whose text lives in `_hint`, and `getDisplayText` reads only
`_setText`/`_text`, so `findUiElementWithText "Close"` never matches and the
first version of this stalled the session outright. `parseWindowControlsFromWindow`
then returned Nothing too, and the Escape fallback did not close it either, so
the bot simply pressed Escape forever.

That second failure was not particular to that window. `parseWindowControls`
looked for a texture path containing `eveicon/window/close`, which this client
does not use -- across 112 logged runs the loot window's own close arm matched
it zero times and missed 77. It now also accepts this client's
`system_icons/close_16px`, so the standard parse does work here.

The fallback below stays regardless, because it is the more robust question:
the icon's own `_name`. Every window in this client carries a
`CloseButtonIcon`, whatever else differs about it, and that is what got
`ShipRestrictionsWindow` closed when the texture match could not.
-}
closeControlOfWindow : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
closeControlOfWindow window =
    case
        window
            |> EveOnline.ParseUserInterface.parseWindowControlsFromWindow
            |> Maybe.andThen .closeButton
    of
        Just closeButton ->
            Just closeButton

        Nothing ->
            window
                |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
                |> List.filter
                    (\node ->
                        (node.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries)
                            == Just "CloseButtonIcon"
                    )
                |> List.head


shipRestrictionsWindowFromReading : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
shipRestrictionsWindowFromReading readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ShipRestrictionsWindow")
        |> List.head


{-| Whether the site's permitted list covers the hull we are in.

The client answers this itself: the window opens with "you may use your Omen Navy
Issue to access it, or one of the following types of ship: ...". Matching that
clause needs no ship database here, and it names our own ship, so it cannot be
confused by the list of alternatives below it. A wording we fail to match reads
as "not admitted", which is the conservative direction -- it skips a mission we
might have flown rather than committing to one we cannot.
-}
restrictionsAdmitThisShip : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
restrictionsAdmitThisShip restrictionsWindow =
    EveOnline.ParseUserInterface.getAllContainedDisplayTexts restrictionsWindow.uiNode
        |> List.any (stringContainsIgnoringCase "you may use your")


{-| The mission's terms, as one line, logged when it is accepted: objective,
pickup and drop-off, cargo, rewards, bonus and its deadline, and any ship
restrictions. All of that sits in the conversation's `objectiveHtml`, which is
gone the moment the window closes, so it is worth capturing at the point of
acceptance rather than trying to recover it later from the mission tracker,
which carries only the current objective.
-}
missionFinePrint : EveOnline.ParseUserInterface.AgentConversationWindow -> String
missionFinePrint conversation =
    conversation.objectiveHtml
        |> Maybe.withDefault ""
        |> EveOnline.ParseUserInterface.stripHtmlTags
        |> String.replace "&nbsp;" " "
        |> String.words
        |> String.join " "


notAlreadyEmptied : BotDecisionContext -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
notAlreadyEmptied context entry =
    not (overviewEntryLooksLooted entry)
        && (case entry.objectItemID of
                Just itemID ->
                    not (List.member itemID context.memory.lootedWreckIds)

                Nothing ->
                    True
           )


{-| Whether a wreck has already been emptied.

EVE swaps the bracket icon when a wreck is looted -- `wreckNPC.png` becomes
`wreckLootedNPC.png`, and the row dims from full white to 55% grey -- so the
game already answers this and nothing needs remembering. Better than the id
memory below in every respect: stateless, correct across restarts, and right
about wrecks emptied by someone else.

The id memory is kept as a backstop. This test depends on the icon updating
promptly, and if it ever does not, the memory is what stops a repeat of the
73-times-into-the-same-wreck loop rather than merely making it less likely.
-}
overviewEntryLooksLooted : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryLooksLooted entry =
    entry.uiNode.uiNode
        :: EveOnline.MemoryReading.listDescendantsInUITreeNode entry.uiNode.uiNode
        |> List.filterMap EveOnline.ParseUserInterface.getTexturePathFromDictEntries
        |> List.any (stringContainsIgnoringCase "looted")


{-| Whether an overview row is really on screen.

The overview virtualises: every object in space has an entry in the UI tree,
but only the dozen or so rows that fit are rendered, and the rest keep whatever
position they last held while recycled. So a hidden entry reports a perfectly
plausible region pointing at a row that now belongs to something else. Clicking
it is worse than a no-op -- it acts on the wrong object. Seen live: the bot
approached an Asteroid Factory 18 times while trying to reach a Cargo Warehouse
that was scrolled out of sight, and parked at the factory.

`_display` is what distinguishes them; the region does not.
-}
overviewEntryIsDisplayed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    nodeIsDisplayed entry.uiNode.uiNode


{-| Rows worth opening for a wanted item: one that names the item, or any wreck
or cargo container. Shared by the picker and by the scroller, so the scroll only
fires for a row the picker would actually use.
-}
isLootableFor : BotDecisionContext -> String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isLootableFor context itemName entry =
    let
        texts =
            [ entry.objectName, entry.objectType ] |> List.filterMap identity

        alreadyOpened =
            not (notAlreadyEmptied context entry)
    in
    (not alreadyOpened)
        && ((texts |> List.any (stringContainsIgnoringCase itemName))
        || (texts
                |> List.any
                    (\text ->
                        [ "wreck", "cargo container", "warehouse" ]
                            |> List.any (\pattern -> containsWords pattern text)
                    )
           ))


{-| Whether `pattern` occurs in `text` as whole words rather than as a substring.

Substring matching keeps costing this project real bugs. "Warehouse" matched a
Caldari Trading Station called "Bhizheba VIII - Moon 5 - Expert Distribution
Warehouse" and had the bot shooting the station for a session. Narrowing that to
Type then made "Habitat" match every Habitation Module on the grid. And a live
rogue drone called a "Wrecker" contains "wreck", so the bot locked it as a rat
and then unlocked it again as debris on the next tick, unable to ever kill it.

EVE carries these words whole -- "Mission Generic Medium Wreck", "Cargo
Container" -- so comparing on word boundaries keeps every real match while
dropping "Wrecker". Whitespace is normalised and both sides padded, so a match
can neither begin nor end mid-word, and a multi-word pattern still matches as a
sequence.

Note this cannot help where the unwanted match really is a whole word: the
"Warehouse" station above still contains the word. That one is handled by
`attack-object` matching Name or Type exactly instead.
-}
containsWords : String -> String -> Bool
containsWords pattern text =
    let
        padded value =
            " " ++ (value |> String.toLower |> String.words |> String.join " ") ++ " "
    in
    String.contains (padded pattern) (padded text)


matchesOverviewName : String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
matchesOverviewName name entry =
    [ entry.objectName, entry.objectType ]
        |> List.filterMap identity
        |> List.any (stringContainsIgnoringCase name)


{-| Bring a wanted overview row into view by turning the mouse wheel over the
overview, a notch at a time, re-reading between notches.

This used to drag the scrollbar handle to a position computed from the target's
rank by distance. That cannot work, and the live logs say so plainly: the bot
asked 31 times in a row for "the row I want is #6 of 45" and the handle never
moved. Two reasons, either fatal on its own.

The arithmetic collapsed. `(rank - rowsOnScreen / 2) / scrollableRows` is
negative for anything in the first half-page, so it clamped to 0 -- and with the
handle already at the top of its track, the computed destination *was* where the
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
    if shipIsAlreadyApproaching context && context.memory.shipApproachingTicks < approachIndicationTrustedForTicks then
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


{-| Issue an Approach on an overview entry, unless the ship is already doing
exactly that.

An approach command runs until it completes, so re-issuing it every tick is
pure noise: it restarts the same manoeuvre and burns a context-menu cascade
each time. The ship's own indication reports `ManeuverApproach` while one is in
flight, which is the cheapest way to tell.

`ManeuverApproach` alone is not enough to trust indefinitely, though: it stays
set while the ship approaches *something*, which need not be the thing the
mission wants. Seen live sitting 29 km from a Cargo Warehouse, moving at
304 m/s, distance unchanged over 12 seconds -- approaching, but not that. With
no bound, the guard suppressed every re-issue and the bot never redirected. So
the indication is only believed for a bounded run of readings; past that the
approach is re-issued, which retargets the ship.
-}
approachIndicationTrustedForTicks : Int
approachIndicationTrustedForTicks =
    10


{-| The "do not restart what is already running" guard shared by everything that
acts on an object the ship has not reached yet.

The command puts the ship into an approach, and re-issuing it while that
approach is running restarts the manoeuvre and burns a step every tick for
nothing. `ManeuverApproach` is believed for a bounded run of readings only,
since it stays set while the ship approaches *something*, which need not be this
object.
-}
unlessAlreadyClosingIn : BotDecisionContext -> String -> DecisionPathNode -> DecisionPathNode
unlessAlreadyClosingIn context description action =
    if shipIsAlreadyApproaching context && context.memory.shipApproachingTicks < approachIndicationTrustedForTicks then
        describeBranch (description ++ " Already on the way -- let it run.")
            waitForProgressInGame

    else
        describeBranch description action


{-| Open an object's cargo, at whatever range.

A double click is EVE's own "Open Cargo", and from outside looting range the
client answers it by flying there and opening on arrival -- so this is the whole
interaction at any distance, and there is no separate in-range case to write.

That matters more than it sounds: the right-click cascade this replaces was
being re-run as the ship closed, once per distance step. One live pickup of a
single container spent thirty cascade clicks getting from 70 km to 8 km, each
one an open-menu / wait-for-render / find-entry / click sequence. A double click
is one step.
-}
openCargoOnOverviewEntry :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> DecisionPathNode
openCargoOnOverviewEntry context description entry =
    unlessAlreadyClosingIn context description (doubleClickUiElement entry.uiNode)


{-| Tell the client to act on an object the ship is not next to yet.

EVE's own commands -- "Activate Gate", "Open Cargo" -- fly the ship there and
act on arrival. Approaching first and issuing the real command on a later tick
cannot match that: the bot only learns it has arrived from the next reading, so
it sits next to the object doing nothing for at least a tick, having crossed the
whole distance to get there. Naming the command up front closes that gap.

The approach guard above applies to these commands exactly as it did to a plain
Approach, since that is what they put the ship into.

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


{-| Close in on an object with nothing to do on arrival but be near it.
-}
approachOverviewEntry :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> DecisionPathNode
approachOverviewEntry context description entry =
    let
        -- The range belongs in the decision text, not just in the reading.
        -- stall_watch calls a stall when the same decisions recur and EVE's
        -- game log stays silent, and a sublight approach is exactly that: no
        -- combat, nothing written, one decision repeating. Run 107 raised two
        -- alarms while the ship was closing perfectly well from 28 km to 2.7
        -- km, because "approach it" reads identically at every range.
        --
        -- With the range in it the text changes as the ship closes, so the
        -- circling test resets itself and the alarm only survives when the
        -- distance genuinely stops moving -- which is the case worth waking
        -- someone for. No special case in the watcher; it already keys on the
        -- decision changing.
        withRange =
            description ++ " (" ++ (entry.objectDistance |> Maybe.withDefault "range unknown") ++ ")"
    in
    unlessAlreadyClosingIn context
        withRange
        (selectThenPanelAction context "selectedItemApproach" entry withRange)


shipIsAlreadyApproaching : BotDecisionContext -> Bool
shipIsAlreadyApproaching context =
    context.readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
        |> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverApproach)
        |> Maybe.withDefault False


{-| Some missions are satisfied simply by getting close to something -- "You
need to approach <a ...>Fire Cloud</a>". The objective clears itself once the
ship is near enough, so there is nothing to detect beyond "is it still asking".

What the objective *names*, though, cannot be trusted to be what you approach.
On "Athran Exigency" the instruction points at an Acidic Cloud (typeID 10131)
which is flavour and is not even on the overview; the thing that actually
satisfies it is an Abandoned Mining Station (typeID 23615) sitting on the same
grid. Matching by the link's id would be no better than matching by its text --
both identify the cloud. So the objective's own name is tried first, and
`approach-object` from the settings covers the missions where it lies.
-}
approachMissionObjectIfNeeded : BotDecisionContext -> Maybe DecisionPathNode
approachMissionObjectIfNeeded context =
    case
        missionInfoPanelEntry context
            |> Maybe.map .objectNamesToApproach
            |> Maybe.withDefault []
            |> List.head
    of
        Nothing ->
            Nothing

        Just objectNameFromObjective ->
            let
                candidateNames =
                    objectNameFromObjective :: context.eventContext.botSettings.approachObjectNames

                entriesNamed name =
                    context.readingFromGameClient.overviewWindows
                        |> List.concatMap .entries
                        |> List.filter (matchesOverviewName name)
                        |> List.filter overviewEntryIsDisplayed
                        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
            in
            candidateNames
                |> List.concatMap entriesNamed
                |> List.head
                |> Maybe.map
                    (\entry ->
                        approachOverviewEntry context
                            ("The mission wants me close to the "
                                ++ (entry.objectName |> Maybe.withDefault objectNameFromObjective)
                                ++ " -- approach it."
                            )
                            entry
                    )


{-| Approach an `approach-object` from the settings when nothing in the mission
text asked for it.

`approachMissionObjectIfNeeded` above only runs when the objective says
"approach", and uses the settings to correct what it names. But an objective can
be satisfied by flying up to something without ever saying so. "Interstellar
Railroad (1 of 4)" asks only for an `Amarr Diplomat` in the cargo hold; what
produces one is closing on a Large Collidable Object on the grid -- no container
to open, no wording to parse, and nothing in the brief pointing at it. Live, the
bot cleared the pocket, found no wreck or container matching the item, and then
sat on "Nothing to fight and no travel step offered" indefinitely.

So the object has to come from the settings, and this is the same
`approach-object` list read without requiring the objective's permission.

Deliberately last in the decision tree, not alongside the other objective
actions: it fires only when there is nothing to shoot, no cargo to fetch, no
travel step offered, no gate to take and no route to fly. A named object sitting
on the grid would otherwise pull the ship away from all of those. Skipped once
the ship is already there, so arriving ends the manoeuvre rather than re-issuing
it forever if the objective turns out not to clear.
-}
approachConfiguredObjectIfPresent : BotDecisionContext -> Maybe DecisionPathNode
approachConfiguredObjectIfPresent context =
    context.eventContext.botSettings.approachObjectNames
        |> List.concatMap
            (\name ->
                context.readingFromGameClient.overviewWindows
                    |> List.concatMap .entries
                    |> List.filter (matchesOverviewName name)
                    |> List.filter overviewEntryIsDisplayed
                    |> List.filter overviewEntryDistanceIsOnGrid
                    |> List.filter
                        (\entry ->
                            interactionRangeInMeters
                                < (entry.objectDistanceInMeters |> Result.withDefault 999999)
                        )
                    |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
            )
        |> List.head
        |> Maybe.map
            (\entry ->
                approachOverviewEntry context
                    ("Nothing else to do here, and '"
                        ++ (entry.objectName |> Maybe.withDefault "an object")
                        ++ "' is one of my approach-object settings -- close on it in case that is what the objective wants."
                    )
                    entry
            )


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
                    case scrollOverviewToReveal context (isLootableFor context itemName) of
                      Just scrollIntoView ->
                        Just scrollIntoView

                      Nothing ->
                        lootableHoldingMissionItem context itemName
                            |> Maybe.map
                            (\containerEntry ->
                                let
                                    distanceInMeters =
                                        containerEntry.objectDistanceInMeters
                                            |> Result.withDefault 999999
                                in
                                -- One call, whatever the range. A double click
                                -- is "Open Cargo", and from further out the
                                -- client answers it by flying over and opening
                                -- on arrival, so there is no separate approach
                                -- and no in-range case to wait for. The
                                -- distance only colours the description.
                                openCargoOnOverviewEntry context
                                    (if
                                        [ containerEntry.objectName, containerEntry.objectType ]
                                            |> List.filterMap identity
                                            |> List.any (stringContainsIgnoringCase itemName)
                                     then
                                        "Open the container holding the "
                                            ++ itemName
                                            ++ ", "
                                            ++ String.fromInt distanceInMeters
                                            ++ " m away."

                                     else
                                        -- Nothing on the overview names the
                                        -- item, so this is a blind look inside
                                        -- a wreck. Said plainly, because a log
                                        -- claiming a precise match here would
                                        -- be misleading.
                                        "Look inside "
                                            ++ (containerEntry.objectName
                                                    |> Maybe.withDefault "this wreck"
                                               )
                                            ++ " for the "
                                            ++ itemName
                                            ++ ", "
                                            ++ String.fromInt distanceInMeters
                                            ++ " m away."
                                    )
                                    containerEntry
                            )


{-| How close the ship has to be before it can act on an object out in space --
open a container, or activate an acceleration gate. EVE's own limit is 2,500 m
for both; this stays inside that so the ship is not sitting exactly on the
boundary when the click lands.
-}
interactionRangeInMeters : Int
interactionRangeInMeters =
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
                |> List.filter overviewEntryIsDisplayed
                -- Skip anything already emptied. This exclusion lives here as
                -- well as in `isLootableFor` because the two are consulted by
                -- different callers: `isLootableFor` only gates the scroller,
                -- so putting the check there alone left this picker -- the one
                -- that actually chooses what to open -- still selecting looted
                -- wrecks, and the loop carried on unchanged.
                |> List.filter (notAlreadyEmptied context)
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
                            |> List.any (\pattern -> containsWords pattern text)
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
            -- No inventory window at all, so there is nothing to search and
            -- every step below is unreachable. This used to return Nothing,
            -- which the caller reads as "not loadable here" and answers by
            -- undocking to look for the item in space -- so a courier pickup
            -- sitting in the station hangar had the bot fly off without it and
            -- come back none the wiser. Open the window instead.
            Just (openInventoryWindow context)

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


{-| Open the inventory window with EVE's own Alt+C.

Alt+C is a toggle, not an "open", so pressing it again before the window has
appeared in a reading would close the one just opened -- the same trap the
propulsion module's Alt+F1 falls into. It gets the same settling window as every
other toggle the bot presses.

The window is part of this bot's setup instructions and is normally already
open; this is for the case where it is not, which otherwise leaves a courier
pickup quietly unable to proceed.
-}
openInventoryWindow : BotDecisionContext -> DecisionPathNode
openInventoryWindow context =
    if
        context.previousStepsEffects
            |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
            |> List.any (doEffectsPressKey EffectOnWindow.vkey_C)
    then
        describeBranch
            "I already pressed Alt+C -- wait for the inventory window to show up rather than toggling it shut again."
            waitForProgressInGame

    else
        describeBranch
            "I need the inventory window and do not see it -- open it (Alt+C)."
            (decideActionForCurrentStep
                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_MENU
                , EffectOnWindow.KeyDown EffectOnWindow.vkey_C
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_C
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_MENU
                ]
            )


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

        firstButtonNamed names =
            names
                |> List.filterMap buttonNamed
                |> List.head

        -- How to get rid of an offered mission the bot will never take, with
        -- the label to report. 'Decline' first: 'Delay' means "ask me later",
        -- so the agent re-offers the same mission on the next request and a
        -- permanent skip becomes an endless cycle -- run 101 delayed Worlds
        -- Collide 87 times, asked for a mission 88 times, and never saw a
        -- different one. Declining repeatedly inside four hours costs standing
        -- with the agent, which is the price of actually moving on; delaying
        -- costs the whole session. 'Delay' stays as the fallback for a
        -- conversation that offers no Decline at all.
        skipOfferedMissionButton =
            [ ( "Decline", "DeclineMission_Button" )
            , ( "Delay", "DeferMission_Button" )
            ]
                |> List.filterMap
                    (\( label, name ) -> buttonNamed name |> Maybe.map (Tuple.pair label))
                |> List.head

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
    -- Which button finishes a mission depends on where the ship is. Docked at
    -- the agent's station the conversation carries "CompleteMission_Button";
    -- out in space it carries "CompleteRemotely_Button" instead, and EVE is
    -- happy to settle the mission from there. Matching only the first meant a
    -- completed mission fell through to the ( Nothing, _ ) arm, so the bot
    -- opened the conversation, failed to find anything to press, and went back
    -- to flying with the reward sitting one click away -- seen live on Mission
    -- of Mercy with the bonus timer still running.
    case ( firstButtonNamed [ "CompleteMission_Button", "CompleteRemotely_Button" ], missionReadyToComplete ) of
        ( Just completeButton, True ) ->
            describeBranch "Hand the finished mission in." (clickUiElement completeButton)

        ( Just _, False ) ->
            -- "Complete Mission" is offered throughout the mission, not only
            -- once it can succeed, so a mission still in progress means we are
            -- done talking and should go fly it.
            --
            -- Unless there is nothing to go and fly. Every travel step comes
            -- from the mission's info-panel entry, and that entry exists only
            -- for a *tracked* mission -- accepting one does not track it. With
            -- the agent saying a mission is in progress and no entry to fly,
            -- closing the conversation only starts the cycle again: run 103
            -- opened it 87 times, closed it 79, and never undocked, with every
            -- branch individually convinced it was making progress.
            --
            -- Gated on the counter rather than this reading, because a mission
            -- just accepted shows in the conversation a reading or two before
            -- it shows in the panel, and that is not the same condition.
            if
                (context.memory.agentConversationWithoutTrackerTicks > missionNotTrackedTicks)
                    && (missionInfoPanelEntry context == Nothing)
            then
                describeBranch
                    ("The agent says a mission is in progress, but it has no entry in the info panel after "
                        ++ (context.memory.agentConversationWithoutTrackerTicks |> String.fromInt)
                        ++ " readings -- it is not tracked, so there is no travel step to follow and nothing here will change that. Track it: Opportunities (Alt-J) -> Active -> right-click the mission -> 'Track'."
                    )
                    askForHelpToGetUnstuck

            else
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
                    if
                        missionHasSpecialShipRestrictions conversation
                            && (context.memory.siteAdmitsThisShip
                                    /= Just True
                                    || shipRestrictionsWindowFromReading context.readingFromGameClient
                                    /= Nothing
                               )
                    then
                        -- The phrase means the site has a permitted list, not that
                        -- we are off it. Open the list, read the verdict, close it
                        -- again, and only then decide -- see
                        -- missionHasSpecialShipRestrictions for what conflating
                        -- those two cost.
                        case shipRestrictionsWindowFromReading context.readingFromGameClient of
                            Just restrictionsWindow ->
                                -- The verdict is already in memory by now: it is
                                -- read from this same reading.
                                -- Its close control is a ButtonIcon whose caption
                                -- lives in `_hint`, and getDisplayText reads only
                                -- `_setText`/`_text` -- so findUiElementWithText
                                -- "Close" can never match it, and the first
                                -- version of this stalled the session outright.
                                case closeControlOfWindow restrictionsWindow of
                                    Just closeButton ->
                                        describeBranch
                                            (if context.memory.siteAdmitsThisShip == Just True then
                                                "The site admits this ship -- close the restrictions and take the mission."

                                             else
                                                "The site does not admit this ship -- close the restrictions and skip the mission."
                                            )
                                            (clickUiElement closeButton)

                                    Nothing ->
                                        -- Escape rather than asking for help. A
                                        -- window whose control we cannot parse is
                                        -- not worth ending a session over, and
                                        -- Escape closes it without clicking
                                        -- anywhere something else could be.
                                        describeBranch
                                            "I see no close control on the ship restrictions window -- press Escape."
                                            (decideActionForCurrentStep
                                                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                                                , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                                                ]
                                            )

                            Nothing ->
                                case context.memory.siteAdmitsThisShip of
                                    Nothing ->
                                        case shipRestrictionsLinkFromReading context.readingFromGameClient of
                                            Just restrictionsLink ->
                                                describeBranch
                                                    "This site has ship restrictions -- open them and see whether they admit this ship."
                                                    (clickUiElement restrictionsLink)

                                            Nothing ->
                                                -- Nothing to ask with. Taking the
                                                -- mission is the better guess:
                                                -- gateRefusesThisShipTicks already
                                                -- bounds the cost of being wrong,
                                                -- while skipping parks the mission
                                                -- in the journal and stops the
                                                -- agent offering anything else.
                                                describeBranch
                                                    ("This site has ship restrictions and offers no link to read them -- take '"
                                                        ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                                        ++ "' and let the gate decide."
                                                    )
                                                    (clickUiElement acceptButton)

                                    Just _ ->
                                        -- Only reached when the answer was "no":
                                        -- an admitted ship falls through to the
                                        -- ordinary accept path above.
                                        case skipOfferedMissionButton of
                                            Just ( label, skipButton ) ->
                                                describeBranch
                                                    ("'"
                                                        ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                                        ++ "' does not admit this ship -- skip it with '"
                                                        ++ label
                                                        ++ "'. "
                                                        ++ missionFinePrint conversation
                                                    )
                                                    (clickUiElement skipButton)

                                            Nothing ->
                                                closeConversation
                                                    "This mission does not admit this ship and I see no way to skip it."

                    else if shouldDeclineMission context offeredMissionName then
                        case skipOfferedMissionButton of
                            Just ( label, skipButton ) ->
                                describeBranch
                                    ("Skip this mission ("
                                        ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                        ++ ") using '"
                                        ++ label
                                        ++ "'."
                                    )
                                    (clickUiElement skipButton)

                            Nothing ->
                                closeConversation "I want to skip this mission but see no way to."

                    else
                        describeBranch
                            ("Accept the mission '"
                                ++ (offeredMissionName |> Maybe.withDefault "unnamed")
                                ++ "'. "
                                ++ missionFinePrint conversation
                            )
                            (clickUiElement acceptButton)

                Nothing ->
                    case buttonNamed "RequestMission_Button" of
                        Just requestButton ->
                            describeBranch "Ask the agent for a mission."
                                (clickUiElement requestButton)

                        Nothing ->
                            -- Not worth waiting on. Tested by hand against a
                            -- live agent: after a remote hand-in it answers a
                            -- mission request with "Please drop by, so we can
                            -- formalize the mission contract" and offers only a
                            -- Close button, indefinitely. Missions cannot be
                            -- accepted remotely, so an empty conversation here
                            -- is a final answer rather than a slow one.
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
                -- An agent conversation is not a docked-only state. EVE offers
                -- "Complete Remotely", so a finished mission can be settled from
                -- space and the conversation window opens right there. Handling
                -- it only under decideActionWhenDocked -- its sole caller until
                -- now -- left the bot in space clicking the tracker's "Start
                -- Conversation" over and over with the reward one click away,
                -- while the window it had just opened sat unread.
                case context.readingFromGameClient.agentConversationWindows |> List.head of
                    Just conversation ->
                        decideActionInAgentConversation context conversation

                    Nothing ->
                        case manageMiddleRowModules context seeUndockingComplete of
                            Just moduleAction ->
                                moduleAction

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
                case
                    [ lootMissionItemFromContainerIfPresent context
                    , approachMissionObjectIfNeeded context
                    ]
                        |> List.filterMap identity
                        |> List.head
                of
                  Just objectiveAction ->
                    objectiveAction

                  Nothing ->
                    case missionTravelStep context of
                    Just ( label, buttonNode ) ->
                        ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                            (clickMissionTravelButton context label buttonNode)

                    Nothing ->
                        activateAccelerationGateIfPresent context
                            |> Maybe.withDefault
                                (closeSearchResultsWhenRouteIsSet context
                                    |> Maybe.withDefault
                                 (if routeIsSet context then
                                    travelTheRoute

                                 else
                                    approachConfiguredObjectIfPresent context
                                        |> Maybe.withDefault
                                            (case missionInfoPanelEntry context of
                                                Just _ ->
                                                    describeBranch
                                                        "Nothing to fight and no travel step offered -- wait for the mission to catch up."
                                                        waitForProgressInGame

                                                Nothing ->
                                                    -- No tracker means no mission, a state that could not
                                                    -- arise while every hand-in happened docked, since the
                                                    -- mission then ended with the ship already at the agent.
                                                    -- Completing remotely ends it in space instead, and the
                                                    -- agent will only offer the next one in person -- asked
                                                    -- remotely it answers "Please drop by, so we can
                                                    -- formalize the mission contract" and offers no buttons.
                                                    --
                                                    -- So route back to the station we last undocked from,
                                                    -- which is the agent's, and let the docked flow ask for
                                                    -- the next mission. dockAtStation is not the way: it
                                                    -- reads the surroundings menu, which lists only the
                                                    -- current system, so it cannot reach an agent two jumps
                                                    -- out, and inside a deadspace pocket it offers no
                                                    -- stations at all -- live, it fell through to clicking
                                                    -- "Approach" and "Warp to Within (0 m)" on whatever was
                                                    -- in the menu.
                                                    case context.memory.lastDockedStationNameFromInfoPanel of
                                                        Just stationName ->
                                                            routeToStationByName context stationName

                                                        Nothing ->
                                                            -- Only before the first dock of a session, so
                                                            -- there is nothing to aim at yet.
                                                            describeBranch
                                                                "No mission, and I have not docked anywhere this session to head back to."
                                                                waitForProgressInGame
                                            )
                                 )
                                )
        )

{-| "Destination Set" is the tracker reporting state, not offering an action:
the route already exists and clicking it again does nothing. "Set Destination"
is the action that creates the route. The two read almost identically, and
matching them both as one "route-related" case -- then trying to tell them apart
by whether a route appeared to exist -- is what made the bot click a dead button
84 times in a row. The label itself already carries the distinction, so no
inference is needed.
-}
labelReportsRouteAlreadySet : String -> Bool
labelReportsRouteAlreadySet label =
    stringContainsIgnoringCase "destination set" label


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
                                |> closeControlOfWindow
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

        -- The low-water mark, not the live reading: see runAwayRearmPercent for
        -- why a single threshold flip-flops. Trip on the configured level, stay
        -- committed until hitpoints climb back over the re-arm level.
        lowestShield =
            plausibleHitpointsPercent shipUI.hitpointsPercent.shield
                |> Maybe.map (\current -> min current context.memory.lowestShieldPercentSinceHealthy)
                |> Maybe.withDefault context.memory.lowestShieldPercentSinceHealthy

        lowestArmor =
            plausibleHitpointsPercent shipUI.hitpointsPercent.armor
                |> Maybe.map (\current -> min current context.memory.lowestArmorPercentSinceHealthy)
                |> Maybe.withDefault context.memory.lowestArmorPercentSinceHealthy

        runAwayWithShieldDescription =
            describeBranch
                ("Shield reached "
                    ++ (lowestShield |> String.fromInt)
                    ++ "% (now "
                    ++ (shipUI.hitpointsPercent.shield |> String.fromInt)
                    ++ "%), get out get out"
                )
                (runAway context)

        runAwayWithArmorDescription =
            describeBranch
                ("Armor reached "
                    ++ (lowestArmor |> String.fromInt)
                    ++ "% (now "
                    ++ (shipUI.hitpointsPercent.armor |> String.fromInt)
                    ++ "%), get out get out get out"
                )
                (runAway context)
    in
    if lowestShield < runAwayShieldThreshold then
        Just runAwayWithShieldDescription

    else if lowestArmor < runAwayArmorThreshold then
        Just runAwayWithArmorDescription

    else
        Nothing

{-| How many readings one escape choice stays put.

The choice has to outlive the two-tick select-then-press-the-panel manoeuvre, or
the bot selects one celestial and warps to whatever the next reading picked
instead. It also has to keep moving if a warp does not get us out of trouble,
which is why it rotates at all.
-}
runAwayCelestialStickyReadings : Int
runAwayCelestialStickyReadings =
    12


{-| Somewhere to run to: whatever the overview reports at AU range.

Distance in AU means off this grid, which is the only property that matters when
leaving. It is also self-correcting -- arriving turns that entry into a km-range
one that no longer qualifies, so the next warp necessarily picks somewhere else,
and the ship keeps moving until its armour recovers.

Deliberately *not* "anything whose name contains station". That is what killed
run 102: an "Angel Asteroid Outpost" carries the object type "Asteroid Station
- 1", matched as a station, and the bot then waited 119 readings for a Dock
button that site scenery never offers, while armour drained from 52% to nothing.
-}
escapeCelestialsOnOverview : BotDecisionContext -> List EveOnline.ParseUserInterface.OverviewWindowEntry
escapeCelestialsOnOverview context =
    context.readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter
            (.objectDistance
                >> Maybe.map (String.toUpper >> String.contains "AU")
                >> Maybe.withDefault False
            )


{-| Leave, and keep leaving until the hitpoints hysteresis says we are safe.

Warping to a celestial beats docking here: it needs no Dock button to exist, no
station to be a real station, and every grid worth fleeing has something at AU
range. Which celestial is picked rotates with the reading count, so a retreat
that has not worked yet tries a different corner of the system rather than
retrying one that did not help.
-}
runAway : BotDecisionContext -> DecisionPathNode
runAway context =
    case escapeCelestialsOnOverview context of
        [] ->
            describeBranch "Get out -- nothing at AU range on the overview to warp to."
                (tetherAtStructure context)

        celestials ->
            case
                celestials
                    |> Common.Basics.listElementAtWrappedIndex
                        (context.memory.readingsCount // runAwayCelestialStickyReadings)
            of
                Nothing ->
                    tetherAtStructure context

                Just celestial ->
                    returnDronesToBay context
                        |> Maybe.withDefault
                            (selectThenPanelAction context
                                "selectedItemWarpTo"
                                celestial
                                ("Get out -- warp to '"
                                    ++ (celestial.objectName |> Maybe.withDefault "a celestial")
                                    ++ "' at "
                                    ++ (celestial.objectDistance |> Maybe.withDefault "range")
                                )
                            )


tetherAtStructure : BotDecisionContext -> DecisionPathNode
tetherAtStructure context =
    -- Try the overview and the Selected Item panel first. The surroundings-button
    -- cascade below is the old path and it is too slow to be a retreat: measured
    -- live, it spent nineteen decisions clicking menu entries while armor fell
    -- from 58% to 31%, and the hysteresis gate that had correctly committed to
    -- leaving could do nothing about it. Docking or warping from the panel is two
    -- clicks with nothing to render in between.
    case escapeTargetOnOverview context of
        Just ( entry, buttonName, what ) ->
            returnDronesToBay context
                |> Maybe.withDefault
                    (selectThenPanelAction context
                        buttonName
                        entry
                        ("Get out -- '"
                            ++ (entry.objectName |> Maybe.withDefault "somewhere off this grid")
                            ++ "' is on the overview, "
                            ++ what
                        )
                    )

        Nothing ->
            tetherAtStructureViaSurroundings context


{-| The original surroundings-menu escape, kept as the fallback for a grid with
neither a station nor a stargate on the overview -- a deadspace pocket, most
often, which is exactly where a retreat is most likely to be needed and where
this has the worst chance of working. Better than nothing, and no longer the
first thing tried.
-}
tetherAtStructureViaSurroundings : BotDecisionContext -> DecisionPathNode
tetherAtStructureViaSurroundings context =
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


{-| The on-screen combat feed used to be printed with every status line, and it
was worse than useless: EVE's floating combat text lingers after a fight ends, so
the status kept reprinting the last exchange indefinitely. Seen with "40 to
Federation Nauclarius - Hits" sitting directly above "Rats in overview: 0.
Current target: None." -- six lines of screen space suggesting a fight that had
finished. A stale display reported faithfully, not stale data.

The host now follows EVE's own game log instead (GameLogTail in
botlab_host.py), which carries real wall-clock timestamps and cannot go stale,
so nothing is lost by leaving it out here.

`visibleCombatMessages` above is now unused, kept deliberately rather than
deleted: it encodes which UI nodes carry combat text and how to read them, which
is the expensive part to rediscover, and any future in-decision use of combat
state wants exactly that.
-}
combatFeedIsReportedByTheHostGameLog : ()
combatFeedIsReportedByTheHostGameLog =
    ()


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
        everythingWorthAttacking =
            overviewEntriesToAttackFromReadingFromGameClient
                (objectNamesToAttack context)
                context.readingFromGameClient
                -- Anything warp-disrupting us goes to the front, ahead of the
                -- distance order everything else is in. This list drives what
                -- gets locked and, through clickTargetBeforeShooting, what
                -- becomes the active target -- so putting the scrambler first
                -- also points keep-at-range at it, which is the one target
                -- worth holding range on. Stable sort, so the nearest
                -- scrambler leads and the rest keep their existing order.
                |> List.sortBy
                    (\entry ->
                        if overviewEntryIsWarpDisruptingMe entry then
                            0

                        else
                            1
                    )

        -- When the briefing says the rooms need not be cleared, drop everything
        -- that only qualified by looking like a rat. What the objective or the
        -- settings named by name still stands: those missions ask for a
        -- structure dead, and "clearing is optional" is about the pirates
        -- guarding it, not about the target itself.
        overviewEntriesToAttack =
            if context.memory.clearingNotRequired then
                everythingWorthAttacking
                    |> List.filter (isObjectToAttackByName (objectNamesToAttack context))

            else
                everythingWorthAttacking

        -- Locking clicks the row, so only rows actually rendered can be used: a
        -- hidden one's reported position belongs to whatever row was recycled
        -- into its place, and clicking it locks the wrong object. The filter
        -- comes before taking the nearest few, so a scrolled overview yields
        -- the nearest few it can actually click rather than an empty list.
        overviewEntriesToLock =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsDisplayed
                |> List.take context.eventContext.botSettings.maxTargetCount
                |> List.filter (overviewEntryIsTargetedOrTargeting >> not)

        -- Something to attack, but not one row of it rendered. The overview
        -- virtualises, so a mission structure sitting further down the list --
        -- a Habitation Module among a screen full of rats, say -- is simply not
        -- on screen, and nothing above can click it. Scroll to it instead of
        -- concluding there is nothing to shoot.
        revealEntryToLock =
            if overviewEntriesToAttack |> List.isEmpty then
                Nothing

            else
                scrollOverviewToReveal context
                    (shouldAttackOverviewEntry (objectNamesToAttack context))

        targetsToUnlock =
            targetsToUnlockFromReadingFromGameClient context.readingFromGameClient

        activeTargetEntry =
            overviewEntriesToAttack
                |> List.filter overviewEntryIsActiveTarget
                |> List.head

        ensureShipIsOrbitingDecision =
            activeTargetEntry
                |> Maybe.andThen (ensureShipIsOrbiting context seeUndockingComplete.shipUI)

        ensureShipIsKeepingRangeDecision =
            activeTargetEntry
                |> Maybe.andThen (ensureShipIsKeepingRange context seeUndockingComplete.shipUI)

        notableWreckEntries =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter isNotableWreck
                |> List.filter overviewEntryIsDisplayed
                -- `isNotableWreck` only asks whether a wreck is worth looting,
                -- never whether it still holds anything, so without this the
                -- branch reopens one it has already emptied for as long as the
                -- row is on the overview -- 844 repeats in a single run before
                -- it was caught. The courier picker needed the same filter for
                -- the same reason; see the note at `notAlreadyEmptied`'s other
                -- caller.
                |> List.filter (notAlreadyEmptied context)
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        decisionIfNoEnemyToAttack =
            case context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
                Just openLootWindow ->
                    if context.memory.lootWindowOpenTicks > lootWindowRefusesToCloseTicks then
                        describeBranch
                            ("The loot window has stayed open for "
                                ++ (context.memory.lootWindowOpenTicks |> String.fromInt)
                                ++ " readings and will not close."
                            )
                            askForHelpToGetUnstuck

                    else if context.memory.lootWindowOpenTicks > 2 then
                        -- Click the window's own Close control, not Ctrl+W. That
                        -- hotkey acts only on the *focused* window and nothing here
                        -- focuses the loot window first, so it reached the client
                        -- and closed nothing -- 650 presses in one run while the
                        -- window sat open. Confirmed live on a window that had been
                        -- stuck open for hours: Ctrl+W alone left it open, clicking
                        -- its title bar first then Ctrl+W closed it, and clicking
                        -- Close closed it with no focus step at all.
                        case openLootWindow.uiNode |> closeControlOfWindow of
                            Just closeButton ->
                                describeBranch "Loot window did not close on its own -- click its Close button."
                                    (clickUiElement closeButton)

                            Nothing ->
                                -- Wait rather than cry stuck. The genuine case is
                                -- already covered above: lootWindowRefusesToCloseTicks
                                -- gives up after 30 readings however the close fails,
                                -- so waiting here costs nothing and cannot loop.
                                describeBranch
                                    "Loot window did not close on its own, and its Close button is not in this reading -- wait for the next one."
                                    waitForProgressInGame

                    else
                        case openLootWindow.uiNode |> findUiElementWithText "Loot All" of
                            Just lootAllButton ->
                                describeBranch "Click 'Loot All'." (clickUiElement lootAllButton)

                            Nothing ->
                                case openLootWindow.uiNode |> closeControlOfWindow of
                                    Just closeButton ->
                                        describeBranch "Nothing left to loot. Close the wreck's cargo window."
                                            (clickUiElement closeButton)

                                    Nothing ->
                                        describeBranch "I do not see a way to close this inventory window."
                                            askForHelpToGetUnstuck

                Nothing ->
                    case notableWreckEntries of
                        wreckToLoot :: _ ->
                            -- Double click, not the right-click cascade, for the
                            -- reason openCargoOnOverviewEntry documents. The
                            -- cascade needs the row to hold still between opening
                            -- the menu and clicking the entry, and a pocket with
                            -- several commander wrecks at near-identical range
                            -- re-sorts the distance-ordered overview between
                            -- readings, so the click lands on whichever wreck
                            -- moved into that row. Measured live: 530 cascade
                            -- attempts to land 21 loots.
                            openCargoOnOverviewEntry context
                                "Open commander/overseer wreck's cargo before leaving."
                                wreckToLoot

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
                                    -- Unlock it, do not merely decline to shoot
                                    -- it. Holding fire leaves the wreck locked
                                    -- and active, so the next reading reaches
                                    -- exactly this branch again and the bot waits
                                    -- forever with a full target slot.
                                    --
                                    -- targetsToUnlock does not cover this case:
                                    -- it matches the *target bar's* own text,
                                    -- while this branch fires on what the
                                    -- *overview entry* says, and the two do not
                                    -- always agree -- see the note on
                                    -- targetsToUnlockFromReadingFromGameClient
                                    -- for how the bar's text resisted matching.
                                    -- Either detector spotting a wreck is reason
                                    -- enough to let it go.
                                    case context.readingFromGameClient.targets |> List.filter .isActiveTarget |> List.head of
                                        Just activeTarget ->
                                            describeBranch
                                                "The active target is a container/wreck, not a rat -- unlock it (Ctrl+Shift+Click)."
                                                (ctrlShiftClickUiElement
                                                    (activeTarget.barAndImageCont
                                                        |> Maybe.withDefault activeTarget.uiNode
                                                    )
                                                )

                                        Nothing ->
                                            describeBranch
                                                "The active target looks like a container/wreck, but I cannot find it in the target bar to unlock -- hold fire."
                                                waitForProgressInGame

                                 else if activateOneOfTheLockedTargets context /= Nothing then
                                    activateOneOfTheLockedTargets context
                                        |> Maybe.withDefault waitForProgressInGame

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
                                                                    revealEntryToLock
                                                                        |> Maybe.withDefault
                                                                            (describeBranch "Everything worth locking is locked."
                                                                                waitForProgressInGame
                                                                            )

                                                                nextOverviewEntryToLock :: _ ->
                                                                    describeBranch "Lock more targets."
                                                                        (lockTargetFromOverviewEntry context nextOverviewEntryToLock)
                                                            )
                                                        )
                                                )

                                        Just ( inactiveModuleIndex, inactiveModule ) ->
                                            clickTargetBeforeShooting context overviewEntriesToAttack
                                                |> Maybe.withDefault
                                                    (describeBranch "Cycle combat mod"
                                                        (activateWeaponModuleButWaitIfActivatedInPreviousStep context inactiveModuleIndex inactiveModule)
                                                    )
                                )
    in
    if overviewEntriesToAttack |> List.isEmpty then
        if context.memory.clearingNotRequired && not (List.isEmpty everythingWorthAttacking) then
            describeBranch
                ("The briefing says clearing is not required -- leaving "
                    ++ (everythingWorthAttacking |> List.length |> String.fromInt)
                    ++ " hostile(s) alone and getting on with the objective."
                )
                decisionIfNoEnemyToAttack

        else
            decisionIfNoEnemyToAttack

    else if context.eventContext.botSettings.orbitInCombat == AppSettings.Yes then
        ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToKillRats

    else if context.eventContext.botSettings.keepAtRange == AppSettings.Yes then
        ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToKillRats

    else
        decisionToKillRats


{-| How many readings to keep commanding a manoeuvre the client never confirms
before letting the ship get on with shooting instead.

Both keep-at-range and orbit report success only through the HUD's manoeuvre
indicator, and on this client `HudActionIndicationContainer` is often empty --
so `ManeuverRange`/`ManeuverOrbit` never arrives and the branch re-issues
forever. Run 111 spent a whole 180-minute session on the range one: 8,941
keypresses, no missions. Orbit is the same shape with less protection, having
no locked-target check at all.

Give up quietly rather than ask for help. Positioning is an optimisation, not a
prerequisite -- the guns and drones work regardless -- so the right answer when
it cannot be confirmed is to stop trying and fight, not to stop the run.
-}
maneuverNotConfirmedGiveUpTicks : Int
maneuverNotConfirmedGiveUpTicks =
    20


ensureShipIsKeepingRange : BotDecisionContext -> ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsKeepingRange context shipUI overviewEntryToKAR =
    if context.memory.keepAtRangeUnconfirmedTicks > maneuverNotConfirmedGiveUpTicks then
        Nothing

    else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverRange then
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

ensureShipIsOrbiting : BotDecisionContext -> ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsOrbiting context shipUI overviewEntryToOrbit =
        if context.memory.orbitUnconfirmedTicks > maneuverNotConfirmedGiveUpTicks then
            Nothing

        else if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverOrbit then
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


{-| A button in the Selected Item panel, by its own `_name`.

The panel is a far better action surface than a context-menu cascade: the
buttons are name-addressable, always in the same place, and need nothing to
render before they can be clicked. `ParseUserInterface` only exposes
`orbitButton`, so the rest are reached by name -- `selectedItemApproach`,
`selectedItemWarpTo`, `selectedItemJump`, `selectedItemDock` and friends.
-}
selectedItemButtonNamed : BotDecisionContext -> String -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
selectedItemButtonNamed context name =
    context.readingFromGameClient.selectedItemWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.filter
            (\node ->
                (node.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries) == Just name
            )
        |> List.head


{-| Whether the Selected Item panel is showing this overview entry.

Checked before pressing any of its buttons: they act on whatever is selected,
which is not necessarily what this decision is about.
-}
selectedItemIsOverviewEntry : BotDecisionContext -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
selectedItemIsOverviewEntry context entry =
    case ( context.readingFromGameClient.selectedItemWindow, entry.objectName ) of
        ( Just window, Just name ) ->
            EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode.uiNode
                |> List.any (containsWords name)

        _ ->
            False


{-| Select an overview row, then press one of the Selected Item panel's buttons.

The pattern that replaces context-menu cascades wherever an overview entry is the
subject. A cascade is three things that must all land -- right-click the row,
wait for the flyout to render, find and click the entry -- and this session it
failed on approach, on acceleration gates, and on the retreat, each time as a
silent no-op that the bot happily repeated for hundreds of readings. The panel's
buttons are name-addressable, always in the same place, and need nothing to
render first. Verified live: selecting the drone row and pressing
`selectedItemApproach` took the ship from 0.0 to 585 m/s after a cascade had
achieved nothing across 180 decisions.

Two ticks by design. The panel acts on whatever is selected, so this presses its
button only once the panel is showing the row we mean, and otherwise spends a
tick selecting. That is still far quicker than a cascade, and it cannot act on
the wrong object.
-}
selectThenPanelAction :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> String
    -> DecisionPathNode
selectThenPanelAction context buttonName entry description =
    if selectedItemIsOverviewEntry context entry then
        case selectedItemButtonNamed context buttonName of
            Just button ->
                describeBranch description (clickUiElement button)

            Nothing ->
                describeBranch
                    (description ++ " -- but the selected-item panel offers no '" ++ buttonName ++ "'.")
                    waitForProgressInGame

    else
        describeBranch (description ++ " (selecting it first)")
            (clickUiElement entry.uiNode)


{-| Somewhere off this grid, preferred nearest-first: a station to dock at, or a
stargate to warp to.

Used by the retreat, which previously drove the surroundings-button cascade and
was measured taking armor from 58% to 31% while it tried. Docking beats warping
-- it ends the fight outright rather than moving it -- so stations come first.
-}
escapeTargetOnOverview : BotDecisionContext -> Maybe ( EveOnline.ParseUserInterface.OverviewWindowEntry, String, String )
escapeTargetOnOverview context =
    let
        onGrid =
            context.readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter overviewEntryIsDisplayed
                |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)

        matching predicate =
            onGrid
                |> List.filter
                    (\entry ->
                        [ entry.objectName, entry.objectType ]
                            |> List.filterMap identity
                            |> List.any predicate
                    )
                |> List.head
    in
    case matching (containsWords "station") of
        Just station ->
            Just ( station, "selectedItemDock", "dock at it" )

        Nothing ->
            matching (containsWords "stargate")
                |> Maybe.map (\gate -> ( gate, "selectedItemWarpTo", "warp to it" ))


{-| Activate an acceleration gate from the Selected Item panel.

This held D and left-clicked the overview row before -- "D-click", EVE's own
gesture for it. That does not work, and it failed silently: run 104 issued 124
of them against a gate at 0 m and the objective never once changed, and run 99
managed 88 with the same result. Reproduced by hand, so it is the gesture and
not the host: the D key reaches the client (no mapping error, and the table has
0x44) and the click lands (the panel shows the gate selected), yet the gate
never opens. What a D-click degrades to when the D does nothing is a plain
select, which is exactly what was observed.

The panel's own `selectedItemActivateGate` button does work -- verified live on
the gate that had refused 124 D-clicks: the objective went from "You need to
activate the Acceleration Gate" to "Warping" and the overview turned over from
17 rows to 22. Same lesson as the loot window and the retreat: where the panel
offers a named button, press it rather than reaching for a keybind or a
cascade.

Wrapped in unlessAlreadyClosingIn like the other close-in commands: EVE flies the
ship to the gate and takes it on arrival, so re-issuing while already on the way
just restarts the manoeuvre.
-}
activateGateOnOverviewEntry :
    BotDecisionContext
    -> String
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> DecisionPathNode
activateGateOnOverviewEntry context description entry =
    unlessAlreadyClosingIn context
        description
        (selectThenPanelAction context
            "selectedItemActivateGate"
            entry
            "Activate the gate from the selected-item panel"
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
                -- Press the panel's own Approach button rather than a modifier
                -- click. This branch used to hold vkey_E, which is keep-at-range
                -- on this account -- it is what ensureShipIsKeepingRange presses
                -- -- so it said "Approach" while asking the client to hold
                -- station. Switching it to vkey_Q did not help either: measured
                -- live, the ship sat at 0.0 m/s for 100 seconds with the distance
                -- frozen, so the keystroke is not producing an approach whatever
                -- it is bound to. The click itself lands -- the Selected Item
                -- panel shows the row we clicked -- so only the key is in doubt,
                -- and the panel's button removes it from the picture.
                --
                -- Guarded on the panel actually showing this entry, since its
                -- buttons act on whatever is selected. When it is showing
                -- something else, clicking the row selects it and the next
                -- reading takes the branch above.
                if selectedItemIsOverviewEntry context overviewEntry then
                    case selectedItemButtonNamed context "selectedItemApproach" of
                        Just approachButton ->
                            describeBranch
                                ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away). Approach from the selected-item panel.")
                                (clickUiElement approachButton)

                        Nothing ->
                            describeBranch
                                ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away), and the selected-item panel offers no Approach.")
                                waitForProgressInGame

                else
                    describeBranch
                        ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away). Select it so the panel offers Approach.")
                        (clickUiElement overviewEntry.uiNode)
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
    , shipApproachingTicks = 0
    , lootedWreckIds = []
    , gateWithinReachTicks = 0
    , siteAdmitsThisShip = Nothing
    , clearingNotRequired = False
    , agentConversationWithoutTrackerTicks = 0
    , keepAtRangeUnconfirmedTicks = 0
    , orbitUnconfirmedTicks = 0
    , readingsCount = 0
    , lowestShieldPercentSinceHealthy = 100
    , lowestArmorPercentSinceHealthy = 100
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
                ++ ". "
                ++ describeModulesToActivateAlways readingFromGameClient

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


{-| Whether this object is holding the ship in place.

The client says so on the overview entry itself -- the parser has carried
`isWarpDisruptingMe` all along and nothing ever read it. It matters more than
any other property of a target, because everything the bot does when a fight
goes wrong assumes it can leave: the retreat warps to a celestial, and warping
is precisely what a scrambler prevents. Without this the bot issues warp after
warp that cannot succeed while its armour drains, which is how the Coercer was
lost in run 102 -- the retreat rewrite that followed did not fix it, because it
still only knew how to warp.

So a scrambler is shot first. Killing it is the only thing that restores the
option to leave.
-}
overviewEntryIsWarpDisruptingMe : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsWarpDisruptingMe overviewEntry =
    overviewEntry.commonIndications.isWarpDisruptingMe


{-| Whether to shoot this overview entry. Rats are recognised by their icon
colour, but some missions require destroying a structure -- a "Drone Silo" and
other Large Collidable Objects -- and those are neutral objects with no
hostile colouring at all, so no colour test will ever match them. They have to
be named explicitly via the `attack-object` setting.

Note the structure must also be *visible*: Large Collidable Objects are off by
default in the overview's type filters, and the bot can only act on what the
overview shows it.
-}
shouldAttackOverviewEntry : ObjectNamesToAttack -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry namesToAttack overviewEntry =
    (iconSpriteHasColorOfRat overviewEntry
        || isObjectToAttackFromObjective namesToAttack.fromObjective overviewEntry
        || isObjectToAttackFromSettings namesToAttack.fromSettings overviewEntry
    )
        && overviewEntryDistanceIsOnGrid overviewEntry


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

`attack-object` names are gated by this too: a mission structure is on the
grid you are sent to, never AU away, so a name match at that distance is a
different object with the same name elsewhere in the system.
-}
overviewEntryDistanceIsOnGrid : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryDistanceIsOnGrid overviewEntry =
    case overviewEntry.objectDistanceInMeters of
        Ok _ ->
            True

        Err _ ->
            False


{-| Whether the mission's own objective picks this object out.

Matched against Name and Type both. The objective names the exact structure the
mission means -- it is quoting the thing's own label -- and which column carries
that label varies: "Amarr Chapel" is both, while an Amarr Trade Post on the same
grid is named "Amarr-Caldari Mediation Center". Narrowing this to Type would
leave the bot unable to shoot what the mission just told it to shoot.
-}
isObjectToAttackFromObjective : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectToAttackFromObjective namesToAttack overviewEntry =
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


{-| Whether an `attack-object` from the settings picks this object out.

Matched **exactly** against the overview's Name or Type -- not as a substring of
either. Substring matching is what made this setting dangerous in both
directions. `attack-object=Warehouse` matched a Caldari Trading Station called
"Bhizheba VIII - Moon 5 - Expert Distribution Warehouse" and the bot spent a
session shooting the station; narrowing it to the Type column then meant
`attack-object=Habitat` matched every Habitation Module on any grid, including
the many a mission does not want touched.

An exact name is the discriminator that actually separates "the structure this
mission is about" from "every structure of that kind": on The Damsel In
Distress, `Kruul's Pleasure Hub` names one object on the grid and nothing else.
Comparison is case-insensitive and trims surrounding space, so a setting copied
out of the overview works whatever its capitalisation.

Either column is accepted because which one carries the identifying label
varies -- see `isObjectToAttackFromObjective`, where the same is true of the
names a mission gives.
-}
isObjectToAttackFromSettings : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectToAttackFromSettings namesToAttack overviewEntry =
    let
        normalize =
            String.trim >> String.toLower

        labels =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
                |> List.map normalize
    in
    namesToAttack
        |> List.any (\nameToAttack -> labels |> List.member (normalize nameToAttack))


{-| Non-rat objects worth shooting: whatever the mission objective names as a
destruction target, plus anything listed in the settings. The objective is the
primary source -- it already says which structure the mission means -- and the
`attack-object` setting stays as a manual override for cases it does not cover.

The two are kept apart rather than concatenated because they are matched
differently -- see `isObjectToAttackFromObjective` and
`isObjectToAttackFromSettings`.
-}
type alias ObjectNamesToAttack =
    { fromObjective : List String
    , fromSettings : List String
    }


objectNamesToAttack : BotDecisionContext -> ObjectNamesToAttack
objectNamesToAttack context =
    { fromObjective =
        missionInfoPanelEntry context
            |> Maybe.map .objectNamesToDestroy
            |> Maybe.withDefault []
    , fromSettings = context.eventContext.botSettings.attackObjectNames
    }


{-| Factored out of decideActionInCombat's own overviewEntriesToAttack /
targetsToUnlock let-bindings so updateMemoryForNewReadingFromGame can
compute the same "target to unlock" identity from just a reading (no bot
settings needed) -- used to track how long it's stayed in the same place,
see routeFirstMarkerUnchangedTicks-style tracking on BotMemory below.
-}
overviewEntriesToAttackFromReadingFromGameClient : ObjectNamesToAttack -> ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
overviewEntriesToAttackFromReadingFromGameClient namesToAttack readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.filter (shouldAttackOverviewEntry namesToAttack)


{-| Targets this mission actually named, as opposed to hostiles that merely
happen to share the grid. Distinguished by *why* the entry matched: an
objective- or settings-named structure still has to die when the briefing says
clearing is optional, a wandering pirate does not.
-}
isObjectToAttackByName : ObjectNamesToAttack -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectToAttackByName namesToAttack overviewEntry =
    isObjectToAttackFromObjective namesToAttack.fromObjective overviewEntry
        || isObjectToAttackFromSettings namesToAttack.fromSettings overviewEntry


{-| Whether the mission's own briefing says the pirates need not be cleared.

EVE says so in more than one wording, and the first version of this matched
only the first of them:

  + "The acceleration gates are not locked, hence clearing the pirates in the
    first two rooms is not required" -- Worlds Collide
  + "Destroying any pirates found in the area is not a requirement" -- Recon

Worth acting on either way. Run 102 spent over 400 combat decisions shooting
rats on a mission whose brief said not to bother, and run 106 did the same on
Recon while the objective read "You need to activate the Acceleration Gate".

So: the briefing must mention pirates *and* say they are not required. That
keeps it explicit -- getting this wrong the other way strands the ship at a
gate that will not open -- while not depending on the gates-not-locked clause,
which only one of the two wordings has. Checked against every briefing in the
run history: of 46 missions, it matches those two and nothing else.
-}
briefingSaysClearingIsOptional : String -> Bool
briefingSaysClearingIsOptional briefing =
    let
        normalised =
            briefing |> String.toLower
    in
    (normalised |> String.contains "pirate")
        && ([ "not required", "not a requirement" ]
                |> List.any (\phrase -> normalised |> String.contains phrase)
           )


{-| The answer from any briefing on screen right now, or `Nothing` when no
briefing is readable and the remembered answer should stand.
-}
clearingNotRequiredFromReading : ReadingFromGameClient -> Maybe Bool
clearingNotRequiredFromReading readingFromGameClient =
    case
        readingFromGameClient.agentConversationWindows
            |> List.filter (.objectiveHtml >> (/=) Nothing)
    of
        [] ->
            Nothing

        conversations ->
            Just (conversations |> List.any (missionFinePrint >> briefingSaysClearingIsOptional))


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


{-| How many readings an agent conversation may sit there insisting a mission
is in progress, with no mission tracked at all, before that is called what it
is rather than retried.

Generous on purpose: a mission just accepted appears in the conversation a
reading or two before it appears in the info panel, and mistaking that for an
untracked mission would halt every run at its first mission. The failure it
catches is unbounded, so waiting a few more readings costs nothing.
-}
missionNotTrackedTicks : Int
missionNotTrackedTicks =
    15


{-| How many readings to keep trying to close a loot window before giving up and
asking for help. Closing it works on the first attempt when it works at all, so
anything past a handful means the window is not responding; the version that
pressed Ctrl+W at it forever managed 650 attempts in one run without ever
saying so.
-}
lootWindowRefusesToCloseTicks : Int
lootWindowRefusesToCloseTicks =
    30


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
*change* the active target, so repeating it is not free.
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
    -- A scrambler outranks the target already selected. Everything else prefers
    -- to stay on the active target rather than flip between them, but a warp
    -- disruptor is the one thing worth switching for: until it dies the ship
    -- cannot leave, and it is also what keep-at-range should be holding range
    -- on, since keep-at-range follows whatever is active.
    [ entriesToAttack |> List.filter overviewEntryIsWarpDisruptingMe |> List.head
    , entriesToAttack |> List.filter overviewEntryIsActiveTarget |> List.head
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

Locking a target and *aiming* at it are separate things in EVE, and they can
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
                                |> List.any (\pattern -> containsWords pattern text)
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
anyAttackableInOverview : ObjectNamesToAttack -> ReadingFromGameClient -> Bool
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
    context.readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.head
        |> Maybe.andThen
            (\accelerationGateEntry ->
                let
                    distanceInMeters =
                        accelerationGateEntry.objectDistanceInMeters |> Result.withDefault 999999
                in
                if interactionRangeInMeters < distanceInMeters then
                    Just <|
                    -- "Activate Gate" from out here does the whole thing: the
                    -- client flies the ship over and takes the gate on arrival,
                    -- with no tick spent noticing it has arrived. The drones
                    -- come home first, since the gate fires with whatever is
                    -- still in space; the prop mod stays on, so the ship covers
                    -- the distance fast.
                    ensureDronesRecalledBeforeWarping context
                        (activateGateOnOverviewEntry context
                            ("The acceleration gate is "
                                ++ String.fromInt distanceInMeters
                                ++ " m away -- D-click it from here and let the client fly me in."
                            )
                            accelerationGateEntry
                        )

                else if gateRefusesThisShipTicks < context.memory.gateWithinReachTicks then
                    -- Hand the turn back rather than end the session. This used to
                    -- askForHelpToGetUnstuck, stopping everything on the strength
                    -- of a guess -- and the guess is often wrong: the message
                    -- blames "special ship restrictions", but it fired live on
                    -- Athran Exigency, whose terms say nothing of the sort and
                    -- whose objective is satisfied by approaching an object
                    -- elsewhere on the grid (see approach-object in
                    -- run_mission.sh). Returning Nothing lets the caller's own
                    -- fallbacks run -- travelling a set route, then
                    -- approachConfiguredObjectIfPresent -- which is the move that
                    -- mission actually needs.
                    Nothing

                else
                    Just <|
                    ensureDronesRecalledBeforeWarping context
                        (activateGateOnOverviewEntry context
                            "I see an acceleration gate -- D-click it to move to the next pocket."
                            accelerationGateEntry
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
                |> Maybe.map (containsWords "wreck")
                |> Maybe.withDefault False
    in
    containsNotableRatName && isWreck


anyNotableWreckInOverview : ReadingFromGameClient -> Bool
anyNotableWreckInOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.any isNotableWreck


{-| Route to a station by name, through the "Search for anything" bar.

This is the only way the bot can originate a destination. Every other route it
sets comes from the mission tracker's own travel buttons, and those stop existing
the moment a mission ends -- so a mission handed in remotely leaves the ship
wherever it finished with nothing left to follow, and no way to reach the agent
who will only offer the next one in person.

Progress is read off the screen rather than remembered, so an attempt interrupted
at any point simply resumes from whatever is showing.

Three things here are not guessable and were established against the live client:

  - **Result rows carry no context menu.** Right-clicking one selects it and
    raises a tooltip, at every position across the row, and opens nothing. A
    double click, which opens Show Info, is the only way in.
  - **That tooltip is drawn outside the results window** and repeats the station
    name, so a whole-tree text search matches it before the real row and sends
    the click into empty space. Every lookup below is scoped to the results
    window's own descendants.
  - **The full name cannot be typed.** `typeTextEffects` emits only letters,
    digits and spaces, so the parentheses and hyphens in "Amarr VI (Zorast) -
    Moon 2 - Theology Council Tribunal" are dropped and the remains match
    nothing. Search a typable tail of the name instead and match the full name
    against the rendered rows -- reading is not limited the way typing is.

-}
routeToStationByName : BotDecisionContext -> String -> DecisionPathNode
routeToStationByName context stationName =
    let
        query =
            searchQueryForStation stationName

        withinWindow window textToFind =
            findUiElementWithText textToFind window

        stationInfoWindow =
            allUiNodesInReading context
                |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoWindow")
                |> List.filter
                    (\window ->
                        EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode
                            |> List.any (stringContainsIgnoringCase stationName)
                    )
                |> List.head
    in
    case stationInfoWindow |> Maybe.andThen (\window -> withinWindow window "Set Destination") of
        Just setDestination ->
            describeBranch ("Set destination to '" ++ stationName ++ "'.")
                (clickUiElement setDestination)

        Nothing ->
            case searchResultsWindow context of
                Just resultsWindow ->
                    case withinWindow resultsWindow stationName of
                        Just row ->
                            describeBranch
                                ("Open '" ++ stationName ++ "' from the search results.")
                                (doubleClickUiElement row)

                        Nothing ->
                            case withinWindow resultsWindow "Stations (" of
                                Just stationsGroup ->
                                    -- The groups come back collapsed, so the rows
                                    -- are not in the tree at all until this is
                                    -- clicked -- not merely unrendered.
                                    describeBranch "Expand the Stations group in the search results."
                                        (clickUiElement stationsGroup)

                                Nothing ->
                                    describeBranch
                                        ("The search results do not offer '" ++ stationName ++ "'.")
                                        askForHelpToGetUnstuck

                Nothing ->
                    case searchInputField context of
                        Just searchField ->
                            if previousStepClickedMouse context then
                                describeBranch
                                    "I just clicked the search bar -- wait for the reading to catch up before typing."
                                    waitForProgressInGame

                            else
                                describeBranch ("Search for '" ++ query ++ "'.")
                                    (decideActionForCurrentStep
                                        (List.concat
                                            [ mouseClickOnUIElement MouseButtonLeft searchField
                                                |> Result.withDefault []
                                            , selectAllEffects
                                            , typeTextEffects query
                                            , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_RETURN
                                              , EffectOnWindow.KeyUp EffectOnWindow.vkey_RETURN
                                              ]
                                            ]
                                        )
                                    )

                        Nothing ->
                            describeBranch "I do not see the search bar." askForHelpToGetUnstuck


{-| A typable search term for a station name -- the tail after the last " - ",
which for an NPC station is the distinctive part and free of the punctuation
`typeTextEffects` has to drop.
-}
searchQueryForStation : String -> String
searchQueryForStation stationName =
    stationName
        |> String.split " - "
        |> List.reverse
        |> List.head
        |> Maybe.withDefault stationName


allUiNodesInReading : BotDecisionContext -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
allUiNodesInReading context =
    context.readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion


searchInputField : BotDecisionContext -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
searchInputField context =
    allUiNodesInReading context
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoPanelSearch")
        |> List.head


searchResultsWindow : BotDecisionContext -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
searchResultsWindow context =
    allUiNodesInReading context
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ListWindow")
        |> List.filter
            (\window ->
                EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode
                    |> List.any (stringContainsIgnoringCase "Search Results")
            )
        |> List.head


{-| Once a route exists the search windows have done their job, and a results
window left open sits over the screen for the rest of the trip.
-}
closeSearchResultsWhenRouteIsSet : BotDecisionContext -> Maybe DecisionPathNode
closeSearchResultsWhenRouteIsSet context =
    if not (routeIsSet context) then
        Nothing

    else
        searchResultsWindow context
            |> Maybe.andThen (findUiElementWithText "Close")
            |> Maybe.map
                (\closeButton ->
                    describeBranch "The route is set -- close the search results."
                        (clickUiElement closeButton)
                )


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

This is the single gate every warp/travel action goes through, so fixing
drone recall here covers every caller rather than each of them needing its
own explicit `returnDronesToBay` step.

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
    returnDronesToBay context
        |> Maybe.withDefault ifReadyToWarp


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


{-| A hitpoints reading, if it is one we can believe.

The parser returns nonsense occasionally -- measured across four runs, roughly
one reading in a few hundred, with values like 1862%, 2307%, 7711% and -213%.
That used to cost a single wrong tick, because every check compared the live
value and the next reading corrected it. Latching the low-water mark for the
retreat changed the stakes: one bogus -213% is below even a disabled threshold
of -1, and `min` then holds it until the ship is docked or fully healthy. Seen
live within one run of the latch going in -- "Shield reached -213% (now 70%),
get out get out" -- so the two changes have to land together.
-}
plausibleHitpointsPercent : Int -> Maybe Int
plausibleHitpointsPercent value =
    if value < 0 || 100 < value then
        Nothing

    else
        Just value


{-| Where the retreat's hysteresis actually lives.

Two levels, not one. The bot trips out on the configured threshold and keeps
going until hitpoints come back above `runAwayRearmPercent` -- so a dip that
repairs fully cancels the retreat, while a ship that keeps sliding stays
committed. Comparing the live reading alone gave neither: under fire with a
repairer running, armor oscillates across a single threshold and the decision
flips with it, observed firing "get out get out get out" at 76% then "All guns
cycling" at 82%, 64 times across four episodes without once completing a
retreat. Each reversal also recalled and relaunched the drones, which is how
they got chewed up.

This is the memory half: keep the low-water mark, and forget it once the ship
is healthy again or docked. `runAwayIfLowHealth` compares it against the
threshold, because `UpdateMemoryContext` carries only the reading -- the bot
settings are not visible from here, which is why the re-arm level is a constant
and the trip level is not.
-}
runAwayRearmPercent : Int
runAwayRearmPercent =
    90


lowWaterMark : ReadingFromGameClient -> ({ shield : Int, armor : Int, structure : Int } -> Int) -> Int -> Int
lowWaterMark readingFromGameClient getPercent previous =
    case readingFromGameClient.shipUI of
        Nothing ->
            100

        Just shipUI ->
            case plausibleHitpointsPercent (getPercent shipUI.hitpointsPercent) of
                Nothing ->
                    previous

                Just current ->
                    if runAwayRearmPercent <= current then
                        100

                    else
                        min previous current


updateMemoryForNewReadingFromGame : UpdateMemoryContext -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        -- The agent offering to complete a mission is the agent asserting one
        -- is in progress. Read here rather than in the decision tree so the
        -- assertion can be counted across readings, including the ones where
        -- the bot has closed the conversation again.
        agentSaysMissionInProgress =
            context.readingFromGameClient.agentConversationWindows
                |> List.concatMap .buttons
                |> List.any
                    (\button ->
                        [ "CompleteMission_Button", "CompleteRemotely_Button" ]
                            |> List.member button.name
                    )

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
    , lowestShieldPercentSinceHealthy =
        lowWaterMark context.readingFromGameClient
            (.shield)
            botMemoryBefore.lowestShieldPercentSinceHealthy
    , lowestArmorPercentSinceHealthy =
        lowWaterMark context.readingFromGameClient
            (.armor)
            botMemoryBefore.lowestArmorPercentSinceHealthy
    , readingsCount = botMemoryBefore.readingsCount + 1
    , orbitUnconfirmedTicks =
        -- The orbit twin of keepAtRangeUnconfirmedTicks below; same indicator,
        -- same way of never arriving.
        case context.readingFromGameClient.shipUI of
            Nothing ->
                0

            Just shipUI ->
                if
                    [ EveOnline.ParseUserInterface.ManeuverOrbit
                    , EveOnline.ParseUserInterface.ManeuverAlign
                    ]
                        |> List.member
                            (shipUI.indication
                                |> Maybe.andThen .maneuverType
                                |> Maybe.withDefault EveOnline.ParseUserInterface.ManeuverWarp
                            )
                then
                    0

                else if context.readingFromGameClient.targets |> List.isEmpty then
                    0

                else
                    botMemoryBefore.orbitUnconfirmedTicks + 1
    , keepAtRangeUnconfirmedTicks =
        -- How long the ship has been told to keep at range without the HUD ever
        -- saying it is. The command's only confirmation is the manoeuvre
        -- indicator, and on this client that container is frequently empty --
        -- so the check that ends the command can simply never come true.
        case context.readingFromGameClient.shipUI of
            Nothing ->
                0

            Just shipUI ->
                if
                    [ EveOnline.ParseUserInterface.ManeuverRange
                    , EveOnline.ParseUserInterface.ManeuverAlign
                    ]
                        |> List.member
                            (shipUI.indication
                                |> Maybe.andThen .maneuverType
                                |> Maybe.withDefault EveOnline.ParseUserInterface.ManeuverWarp
                            )
                then
                    0

                else if context.readingFromGameClient.targets |> List.isEmpty then
                    0

                else
                    botMemoryBefore.keepAtRangeUnconfirmedTicks + 1
    , agentConversationWithoutTrackerTicks =
        -- How many readings the agent has claimed a mission is in progress
        -- while nothing at all is tracked. Counted from the reading so the
        -- decision tree can tell "the panel has not caught up yet" from "this
        -- mission is not tracked", which look identical in any one reading.
        --
        -- Deliberately not reset when the conversation closes. The failure this
        -- catches is a cycle that closes and reopens it every few readings, so
        -- resetting there would hold the count near zero forever and the check
        -- would never fire -- which is the same silent-no-op shape it exists to
        -- report. Only a mission actually appearing in the panel clears it.
        if context.readingFromGameClient.agentMissionInfoPanelEntries |> List.isEmpty |> not then
            0

        else if agentSaysMissionInProgress then
            botMemoryBefore.agentConversationWithoutTrackerTicks + 1

        else
            botMemoryBefore.agentConversationWithoutTrackerTicks
    , clearingNotRequired =
        -- Kept far longer than siteAdmitsThisShip below, and deliberately: the
        -- briefing is only readable while the conversation is open, but the
        -- rooms it describes are fought long after it closes. Every briefing
        -- that appears overwrites the answer, so the next mission replaces this
        -- one rather than inheriting it.
        clearingNotRequiredFromReading context.readingFromGameClient
            |> Maybe.withDefault botMemoryBefore.clearingNotRequired
    , siteAdmitsThisShip =
        -- Read while the restrictions window is up, then kept so the answer
        -- outlives closing it. Forgotten once the conversation ends, since the
        -- next mission's site is a different question.
        case shipRestrictionsWindowFromReading context.readingFromGameClient of
            Just restrictionsWindow ->
                Just (restrictionsAdmitThisShip restrictionsWindow)

            Nothing ->
                if context.readingFromGameClient.agentConversationWindows |> List.isEmpty then
                    Nothing

                else
                    botMemoryBefore.siteAdmitsThisShip
    , routeFirstMarkerRegion = currentRouteFirstMarkerRegion
    , routeFirstMarkerUnchangedTicks =
        if currentRouteFirstMarkerRegion == Nothing then
            0

        else if currentRouteFirstMarkerRegion == botMemoryBefore.routeFirstMarkerRegion then
            botMemoryBefore.routeFirstMarkerUnchangedTicks + 1

        else
            0
    , lootedWreckIds =
        -- An emptied wreck is supposed to drop off the overview, and the setup
        -- instructions ask for that filter -- but it does not always hold:
        -- observed live re-opening the same Coreli Scout Wreck 73 times, hauling
        -- out ammo and scrap while the mission item was never in it. Nothing in
        -- a row's text tells an emptied wreck from a full one, so remember the
        -- ones already opened by object id.
        --
        -- The id recorded is the nearest lootable row at the moment a loot
        -- window is open, which is necessarily the one just opened, since that
        -- is the only one the bot ever opens. Capped so a long session cannot
        -- grow this without bound.
        if context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.isEmpty then
            botMemoryBefore.lootedWreckIds

        else
            case
                context.readingFromGameClient.overviewWindows
                    |> List.concatMap .entries
                    |> List.filter (\entry -> entry.objectItemID /= Nothing)
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
        -- gate normally takes a handful; a gate that refuses the ship never
        -- takes any, and there is no error dialog to notice -- see
        -- `missionNeedsADifferentShip`. Counting them is what turns that into
        -- something the bot can act on.
        if accelerationGateIsWithinReach context.readingFromGameClient then
            botMemoryBefore.gateWithinReachTicks + 1

        else
            0
    , shipApproachingTicks =
        if
            context.readingFromGameClient.shipUI
                |> Maybe.andThen .indication
                |> Maybe.andThen .maneuverType
                |> Maybe.map ((==) EveOnline.ParseUserInterface.ManeuverApproach)
                |> Maybe.withDefault False
        then
            botMemoryBefore.shipApproachingTicks + 1

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
            anyAttackableInOverview (objectNamesToAttack context) context.readingFromGameClient

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
waste of capacitor otherwise, which is the `anyAttackableInOverview` gate above.
The propulsion module is the reverse -- it earns its capacitor while the ship is
crossing distance, which is usually when there is nothing to shoot at all. See
`propulsionModuleShouldBeRunning`.
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
never came on, and a *tank* module went off instead -- an odd number of toggles
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
