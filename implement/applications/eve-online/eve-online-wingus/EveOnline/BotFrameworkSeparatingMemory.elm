module EveOnline.BotFrameworkSeparatingMemory exposing (..)

{-| A framework to build EVE Online bots and intel tools.
Features:

  - Read from the game client using Sanderling memory reading and parse the user interface from the memory reading (<https://github.com/Arcitectus/Sanderling>).
  - Play sounds.
  - Send mouse and keyboard input to the game client.
  - Parse the bot-settings and inform the user about the result.

The framework automatically selects an EVE Online client process and finishes the session when that process disappears.
When multiple game clients are open, the framework prioritizes the one with the topmost window. This approach helps users control which game client is picked by an app.

To learn more about developing for EVE Online, see the guide at <https://to.botlab.org/guide/developing-for-eve-online>

-}

import BotLab.BotInterface_To_Host_2023_02_06 as InterfaceToHost
import Common.DecisionPath
import Common.EffectOnWindow
import EveOnline.BotFramework
    exposing
        ( ReadingFromGameClient
        , ReadingFromGameClientMemory
        , ReadingFromGameClientScreenshot
        , SeeUndockingComplete
        , ShipModulesMemory
        , UIElement
        , UseContextMenuCascadeNode
        , asReadingFromGameClientMemory
        , closestPointOnRectangleEdge
        , getModuleButtonTooltipFromModuleButton
        , growRegionOnAllSides
        , isPointInRectangle
        , mouseClickOnUIElement
        , unpackContextMenuTreeToListOfActionsDependingOnReadings
        )
import EveOnline.ParseUserInterface
    exposing
        ( centerFromDisplayRegion
        , subtractRegionsFromRegion
        )
import List.Extra


type EndDecisionPathStructure
    = ContinueSession ContinueSessionStructure
    | FinishSession


type alias ContinueSessionStructure =
    { effectsOnGameClient : List Common.EffectOnWindow.EffectOnWindowStructure
    , millisecondsToNextReadingFromGameBase : Maybe Int
    , millisecondsToNextReadingFromGameModifierPercent : Int
    }


type alias DecisionPathNode =
    Common.DecisionPath.DecisionPathNode EndDecisionPathStructure


type alias UpdateMemoryContext =
    { timeInMilliseconds : Int
    , readingFromGameClient : ReadingFromGameClient
    , screenshot : ReadingFromGameClientScreenshot
    }


type alias StepDecisionContext botSettings botMemory =
    { eventContext : EveOnline.BotFramework.BotEventContext botSettings
    , readingFromGameClient : ReadingFromGameClient
    , screenshot : ReadingFromGameClientScreenshot
    , memory : botMemory
    , previousStepEffects : List Common.EffectOnWindow.EffectOnWindowStructure
    , previousReadingsFromGameClient : List ReadingFromGameClientMemory

    -- How many readings in a row, counting this one, have had no ship UI.
    -- `previousReadingsFromGameClient` cannot answer this: it keeps only the
    -- context menus of a reading, so nothing downstream can tell a reading
    -- whose ship UI was missing from one where it was there.
    , readingsWithoutShipUI : Int
    , contextMenuCascadeLevel : Int
    , randomIntegers : List Int
    }


type alias StateIncludingFramework botSettings botMemory =
    EveOnline.BotFramework.StateIncludingFramework botSettings (BotState botMemory)


type alias BotState botMemory =
    { botMemory : botMemory
    , lastStepEffects : List Common.EffectOnWindow.EffectOnWindowStructure
    , lastReadingsFromGameClient : List ReadingFromGameClientMemory
    , readingsWithoutShipUI : Int
    }


type alias BotConfiguration botSettings botMemory =
    { parseBotSettings : String -> Result String botSettings
    , selectGameClientInstance : Maybe botSettings -> List EveOnline.BotFramework.GameClientProcessSummary -> Result String { selectedProcess : EveOnline.BotFramework.GameClientProcessSummary, report : List String }
    , updateMemoryForNewReadingFromGame : UpdateMemoryContext -> botMemory -> botMemory
    , statusTextFromDecisionContext : StepDecisionContext botSettings botMemory -> String
    , decideNextStep : StepDecisionContext botSettings botMemory -> DecisionPathNode
    }


type alias Rect2dStructure =
    { x : Int
    , y : Int
    , width : Int
    , height : Int
    }


type alias FilterToDiscardContextMenu settings memory =
    { targetUIElement : UIElement }
    -> StepDecisionContext settings memory
    -> EveOnline.ParseUserInterface.ContextMenu
    -> Maybe String


millisecondsToNextReadingFromGameDefault : Int
millisecondsToNextReadingFromGameDefault =
    1500


initState : botMemory -> EveOnline.BotFramework.StateIncludingFramework botSettings (BotState botMemory)
initState botMemory =
    EveOnline.BotFramework.initState (initStateInBaseFramework botMemory)


initStateInBaseFramework : botMemory -> BotState botMemory
initStateInBaseFramework botMemory =
    { botMemory = botMemory
    , lastStepEffects = []
    , lastReadingsFromGameClient = []

    -- A session that starts docked reads 0 here and undocks on its first
    -- reading all the same: the station window decides that case, and the
    -- count is only consulted where nothing corroborates.
    , readingsWithoutShipUI = 0
    }


processEvent :
    BotConfiguration botSettings botMemory
    -> InterfaceToHost.BotEvent
    -> EveOnline.BotFramework.StateIncludingFramework botSettings (BotState botMemory)
    -> ( EveOnline.BotFramework.StateIncludingFramework botSettings (BotState botMemory), InterfaceToHost.BotEventResponse )
processEvent botConfiguration =
    EveOnline.BotFramework.processEvent
        { parseBotSettings = botConfiguration.parseBotSettings
        , selectGameClientInstance = botConfiguration.selectGameClientInstance
        , processEvent =
            processEventInBaseFramework
                { updateMemoryForNewReadingFromGame = botConfiguration.updateMemoryForNewReadingFromGame
                , statusTextFromDecisionContext = botConfiguration.statusTextFromDecisionContext
                , decideNextStep = botConfiguration.decideNextStep
                }
        }


processEventInBaseFramework :
    { updateMemoryForNewReadingFromGame : UpdateMemoryContext -> botMemory -> botMemory
    , statusTextFromDecisionContext : StepDecisionContext botSettings botMemory -> String
    , decideNextStep : StepDecisionContext botSettings botMemory -> DecisionPathNode
    }
    -> EveOnline.BotFramework.BotEventContext botSettings
    -> EveOnline.BotFramework.BotEvent
    -> BotState botMemory
    -> ( BotState botMemory, EveOnline.BotFramework.BotEventResponse )
processEventInBaseFramework config eventContext event stateBefore =
    case event of
        EveOnline.BotFramework.ReadingFromGameClientCompleted readingFromGameClientCompleted ->
            let
                readingFromGameClient =
                    readingFromGameClientCompleted.parsed

                screenshot =
                    readingFromGameClientCompleted.screenshot

                updateMemoryContext =
                    { timeInMilliseconds = eventContext.timeInMilliseconds
                    , readingFromGameClient = readingFromGameClient
                    , screenshot = screenshot
                    }

                botMemory =
                    stateBefore.botMemory
                        |> config.updateMemoryForNewReadingFromGame updateMemoryContext

                lastReadingFromGameClientContextMenus =
                    stateBefore.lastReadingsFromGameClient
                        |> List.head
                        |> Maybe.map .contextMenus
                        |> Maybe.withDefault []

                contextMenuCascadeLevelAlreadyInPreviousReading =
                    List.map2
                        Tuple.pair
                        (List.reverse readingFromGameClient.contextMenus)
                        (List.reverse lastReadingFromGameClientContextMenus)
                        |> List.Extra.takeWhile
                            (\( inCurrent, inPrev ) ->
                                identifyingInfoFromContextMenu inCurrent == identifyingInfoFromContextMenu inPrev
                            )
                        |> List.length

                contextMenuCascadeLevel =
                    min (contextMenuCascadeLevelAlreadyInPreviousReading + 1)
                        (List.length readingFromGameClient.contextMenus)

                readingsWithoutShipUI : Int
                readingsWithoutShipUI =
                    countReadingsWithoutShipUI readingFromGameClient
                        stateBefore.readingsWithoutShipUI

                decisionContext =
                    { eventContext = eventContext
                    , memory = botMemory
                    , readingFromGameClient = readingFromGameClient
                    , screenshot = screenshot
                    , previousStepEffects = stateBefore.lastStepEffects
                    , previousReadingsFromGameClient = stateBefore.lastReadingsFromGameClient
                    , readingsWithoutShipUI = readingsWithoutShipUI
                    , contextMenuCascadeLevel = contextMenuCascadeLevel
                    , randomIntegers = readingFromGameClientCompleted.randomIntegers
                    }

                ( decisionStagesDescriptions, decisionLeaf ) =
                    config.decideNextStep decisionContext
                        |> Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf

                effectsOnGameClientWindow =
                    case decisionLeaf of
                        ContinueSession act ->
                            act.effectsOnGameClient

                        FinishSession ->
                            []

                describeActivity =
                    decisionStagesDescriptions
                        |> List.indexedMap
                            (\decisionLevel -> (++) (("+" |> List.repeat (decisionLevel + 1) |> String.join "") ++ " "))
                        |> String.join "\n"

                statusText =
                    [ config.statusTextFromDecisionContext decisionContext
                    , describeActivity
                    ]
                        |> String.join "\n"

                readingFromGameClientMemory =
                    asReadingFromGameClientMemory readingFromGameClient
            in
            ( { botMemory = botMemory
              , lastStepEffects = effectsOnGameClientWindow
              , lastReadingsFromGameClient =
                    readingFromGameClientMemory
                        :: stateBefore.lastReadingsFromGameClient
                        |> List.take 8
              , readingsWithoutShipUI = readingsWithoutShipUI
              }
            , case decisionLeaf of
                ContinueSession continueSession ->
                    let
                        millisecondsToNextReadingFromGame =
                            ((continueSession.millisecondsToNextReadingFromGameModifierPercent + 100)
                                * (continueSession.millisecondsToNextReadingFromGameBase
                                    |> Maybe.withDefault millisecondsToNextReadingFromGameDefault
                                  )
                            )
                                // 100
                    in
                    EveOnline.BotFramework.ContinueSession
                        { effects = effectsOnGameClientWindow
                        , millisecondsToNextReadingFromGame = millisecondsToNextReadingFromGame
                        , statusText = statusText
                        }

                FinishSession ->
                    EveOnline.BotFramework.FinishSession { statusText = statusText }
            )


useContextMenuCascadeOnOverviewEntry :
    UseContextMenuCascadeNode
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascadeOnOverviewEntry useContextMenu overviewEntry context =
    useContextMenuCascade
        ( "overview entry '" ++ (overviewEntry.objectName |> Maybe.withDefault "") ++ "'", overviewEntry.uiNode )
        useContextMenu
        context


useContextMenuCascadeOnListSurroundingsButton :
    UseContextMenuCascadeNode
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascadeOnListSurroundingsButton useContextMenu context =
    case context.readingFromGameClient.infoPanelContainer |> Maybe.andThen .infoPanelLocationInfo of
        Nothing ->
            Common.DecisionPath.describeBranch "I do not see the location info panel." askForHelpToGetUnstuck

        Just infoPanelLocationInfo ->
            useContextMenuCascadeWithCustomConfig
                filterToDiscardContextMenuOnListSurroundingsButton
                { targetUIElement = infoPanelLocationInfo.listSurroundingsButton
                , targetUIElementName = "surroundings button"
                }
                useContextMenu
                context


filterToDiscardContextMenuOnListSurroundingsButton : FilterToDiscardContextMenu a b
filterToDiscardContextMenuOnListSurroundingsButton =
    \target context cascadeFirstElement ->
        discardContextMenuIfTooDistantFromTargetElement { toleratedDistance = 70 } target context cascadeFirstElement
            |> Maybe.andThen
                (\reasonToDiscard ->
                    if
                        (cascadeFirstElement.uiNode.totalDisplayRegion.x < 100)
                            && (cascadeFirstElement.uiNode.totalDisplayRegion.y < 100)
                    then
                        {-
                           Adapt to game client from session-recording-2023-02-11T16-17-12, shared by Foivos Saropoulos at <https://forum.botlab.org/t/mining-bot-warping-to-a-new-asteroid-belt-if-a-spacific-npc-is-present/4571/14>

                           In event 708, we see how the game client differed from the previous ones: When clicking on the surroundings button in the info panel, it placed the new context menu at the upper left corner of the game client window.
                           In the earlier training data, the game clients always opened the context menu so that at least an edge was close to the mouse cursor.
                           The unusual placement is why you got the 'Existing cascade is too far away' error: When seeing this inconsistency, the bot assumed the context menu belonged to another entity.
                        -}
                        Nothing

                    else
                        Just reasonToDiscard
                )


filterToDiscardContextMenuDefault : FilterToDiscardContextMenu a b
filterToDiscardContextMenuDefault =
    discardContextMenuIfTooDistantFromTargetElement { toleratedDistance = 70 }


useContextMenuCascade :
    ( String, UIElement )
    -> UseContextMenuCascadeNode
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascade ( targetUIElementName, targetUIElement ) =
    useContextMenuCascadeWithCustomConfig
        filterToDiscardContextMenuDefault
        { targetUIElement = targetUIElement, targetUIElementName = targetUIElementName }


useContextMenuCascadeWithCustomConfig :
    FilterToDiscardContextMenu a b
    -> { targetUIElement : UIElement, targetUIElementName : String }
    -> UseContextMenuCascadeNode
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascadeWithCustomConfig filterToDiscardContextMenu target useContextMenu context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        beginCascade =
            let
                occludingRegionsWithSafetyMargin =
                    readingFromGameClient.contextMenus
                        |> List.map (.uiNode >> .totalDisplayRegion >> growRegionOnAllSides 2)

                regionsRemainingAfterOcclusion =
                    subtractRegionsFromRegion
                        { minuend = target.targetUIElement.totalDisplayRegion, subtrahend = occludingRegionsWithSafetyMargin }
            in
            case
                regionsRemainingAfterOcclusion
                    |> List.filter (\region -> 3 < region.width && 3 < region.height)
                    |> List.sortBy (\region -> negate (min region.width region.height))
                    |> List.head
            of
                Nothing ->
                    {-
                       Used to right-click a computed "somewhere else" location
                       (near the neocom clock, or a bottom-left fallback) to
                       dismiss the occluding menu(s). That location isn't
                       reliably empty space -- it can land on a real Neocom icon
                       or another clickable element, opening a different menu
                       (or acting on whatever's there) instead of dismissing
                       anything, and the next click can then hit whatever that
                       opened. Confirmed live elsewhere: this wiped an autopilot
                       route via an accidentally triggered "Clear All
                       Waypoints". Escape closes an open context menu reliably
                       without clicking anywhere, so nothing can be in the way
                       to hit by accident.
                    -}
                    Common.DecisionPath.describeBranch
                        ("All of " ++ target.targetUIElementName ++ " is occluded by context menus.")
                        (Common.DecisionPath.describeBranch
                            "Press Escape to get rid of the occluding elements."
                            (decideActionForCurrentStep
                                [ Common.EffectOnWindow.KeyDown Common.EffectOnWindow.vkey_ESCAPE
                                , Common.EffectOnWindow.KeyUp Common.EffectOnWindow.vkey_ESCAPE
                                ]
                            )
                        )

                Just preferredRegion ->
                    Common.DecisionPath.describeBranch
                        ("Open context menu on " ++ target.targetUIElementName)
                        (preferredRegion
                            |> centerFromDisplayRegion
                            |> Common.EffectOnWindow.effectsMouseClickAtLocation Common.EffectOnWindow.MouseButtonRight
                            |> decideActionForCurrentStep
                        )

        discardExistingContextMenu reasonToDiscard =
            Common.DecisionPath.describeBranch
                ("Discard existing context menu (" ++ reasonToDiscard ++ ")")
                beginCascade
    in
    case context.previousReadingsFromGameClient |> List.take 8 |> List.reverse |> List.head of
        Nothing ->
            beginCascade

        Just previousReadingFromGameClient ->
            case List.reverse context.readingFromGameClient.contextMenus of
                [] ->
                    beginCascade

                cascadeFirstElement :: cascadeFollowingElements ->
                    case
                        filterToDiscardContextMenu
                            { targetUIElement = target.targetUIElement }
                            context
                            cascadeFirstElement
                    of
                        Just reasonToDiscard ->
                            discardExistingContextMenu reasonToDiscard

                        Nothing ->
                            if
                                (context.readingFromGameClient.contextMenus |> List.map identifyingInfoFromContextMenu)
                                    == (previousReadingFromGameClient.contextMenus |> List.map identifyingInfoFromContextMenu)
                            then
                                discardExistingContextMenu "no progress in previous step"

                            else
                                case
                                    useContextMenu
                                        |> unpackContextMenuTreeToListOfActionsDependingOnReadings
                                        {-
                                           2023-01-12 Adapt to behavior of menu from surroundings button:
                                           When opening that menu, the game client opens not only the first level but sometimes also expands the 'stations' entry so that we immediately also have the second level on screen.
                                        -}
                                        |> List.drop
                                            (min
                                                (List.length cascadeFollowingElements)
                                                (context.contextMenuCascadeLevel - 1)
                                            )
                                        |> List.head
                                of
                                    Nothing ->
                                        beginCascade

                                    Just descriptionAndEffectsFromReading ->
                                        let
                                            readingFromGameClientForSelectingMenuEntry =
                                                { readingFromGameClient
                                                    | contextMenus =
                                                        readingFromGameClient.contextMenus
                                                            |> List.reverse
                                                            |> List.take context.contextMenuCascadeLevel
                                                            |> List.reverse
                                                }

                                            ( stepDescription, maybeEffectsToGameClient ) =
                                                descriptionAndEffectsFromReading readingFromGameClientForSelectingMenuEntry
                                        in
                                        Common.DecisionPath.describeBranch stepDescription
                                            (case maybeEffectsToGameClient of
                                                Nothing ->
                                                    beginCascade

                                                Just effectsToGameClient ->
                                                    decideActionForCurrentStep effectsToGameClient
                                            )


discardContextMenuIfTooDistantFromTargetElement :
    { toleratedDistance : Int }
    -> FilterToDiscardContextMenu a b
discardContextMenuIfTooDistantFromTargetElement { toleratedDistance } =
    \{ targetUIElement } context cascadeFirstElement ->
        let
            previousStepClickOnTargetLocation =
                context.previousStepEffects
                    |> EveOnline.BotFramework.findMouseButtonClickLocationsInListOfEffects Common.EffectOnWindow.MouseButtonRight
                    |> List.filter (isPointInRectangle targetUIElement.totalDisplayRegion)
                    |> List.head

            projectedTargetClickLocation =
                previousStepClickOnTargetLocation
                    |> Maybe.withDefault (centerFromDisplayRegion targetUIElement.totalDisplayRegion)

            cascadeFirstElementEdgesClosestPointToTargetUIElement =
                projectedTargetClickLocation
                    |> closestPointOnRectangleEdge cascadeFirstElement.uiNode.totalDisplayRegion

            cascadeFirstElementIsCloseToInitialUIElement =
                EveOnline.BotFramework.distanceSquaredBetweenLocations
                    projectedTargetClickLocation
                    cascadeFirstElementEdgesClosestPointToTargetUIElement
                    < (toleratedDistance * toleratedDistance)

            cascadeFirstElementIsInExpectedRegion =
                cascadeFirstElementIsCloseToInitialUIElement

            describeLocation location =
                String.fromInt location.x ++ ", " ++ String.fromInt location.y
        in
        if not cascadeFirstElementIsInExpectedRegion then
            Just
                ("not in expected region ("
                    ++ Maybe.withDefault "none" (Maybe.map describeLocation previousStepClickOnTargetLocation)
                    ++ ")"
                )

        else
            Nothing


identifyingInfoFromContextMenu : { a | uiNode : { b | totalDisplayRegion : c } } -> c
identifyingInfoFromContextMenu =
    .uiNode >> .totalDisplayRegion


{-| Whether these effects already clicked this UI element.

Generalizes `EveOnline.BotFramework.doEffectsClickModuleButton` to any element
carrying a display region, for the reason that function's own comment gives: a
widget that is a toggle must not be clicked again while an earlier click's
effect on it is still in flight, or the second click undoes the first.

-}
doEffectsClickUIElement : UIElement -> List Common.EffectOnWindow.EffectOnWindowStructure -> Bool
doEffectsClickUIElement uiElement =
    let
        regionsAimedAt =
            [ uiElement.totalDisplayRegionVisible
            , uiElement.totalDisplayRegion
            ]
                |> List.map (growRegionOnAllSides 1)
    in
    EveOnline.BotFramework.findMouseButtonClickLocationsInListOfEffects Common.EffectOnWindow.MouseButtonLeft
        >> List.any (\location -> regionsAimedAt |> List.any (\region -> isPointInRectangle region location))


{-| Whether a repair click on the info panel is still waiting to show its effect.

One settling window for both of `ensureInfoPanelLocationInfoIsExpanded`'s repair
branches, keyed on `infoPanelContainer` rather than on whichever element that
branch clicks. That choice is #297's fix and is the whole of it.

#227 gave the "panel absent" branch a settling guard, for a reason written on
the branch: the icon it clicks is a toggle. The "panel collapsed" branch next to
it kept clicking once per reading with no guard at all, and the two then
alternated -- the icon click makes the panel appear in the tree but drawn
collapsed, which stops the first branch matching and starts the second; the
second's click at `(x + 8, y + 8)` takes the panel back out of the tree, which
stops the second matching and starts the first.

A second guard, per branch, would not have stopped that: **each branch's element
is missing from the tree on exactly the reading the other branch clicks**, so
neither guard can be asked about the click it needs to see. The container is the
one element in the tree on both readings, and both clicks land inside it -- the
icon is a descendant of it, and so is the panel whose corner the other click is
offset from.

`StepDecisionContext` on this host interface carries the immediately previous
step's effects rather than several steps of them, so the window here is one
reading where the mission runner's is `moduleButtonClickSettlingSteps`. Same
rule, the history this shape has to give it.

-}
infoPanelRepairClickIsSettling :
    List Common.EffectOnWindow.EffectOnWindowStructure
    -> ReadingFromGameClient
    -> Bool
infoPanelRepairClickIsSettling previousStepEffects readingFromGameClient =
    case readingFromGameClient.infoPanelContainer of
        Nothing ->
            False

        Just infoPanelContainer ->
            doEffectsClickUIElement infoPanelContainer.uiNode previousStepEffects


{-| Gets the location info panel back when the client is not showing it.

**While a repair click is settling this answers `Nothing`, not
`waitForProgressInGame`, and that is the second half of #297.** This function is
reached from `generalSetupInUserInterface`, which sits above
`branchDependingOnDockedOrInSpace` -- so every `Just` here is the whole tree
below held for that reading, the run-away-when-shields-are-low branch included.
#227 deliberately left a give-up out of the branch it fixed ("one click that
lands ought to be enough, and if it demonstrably is not, that is a separate
finding"); #297 is that finding, counted on 22 of the 27 runs it read of
the bot that carries the same declaration.

So the repair still clicks -- every other reading, which is as often as a toggle
can usefully be clicked with one step of history -- and on the readings between
it stands aside and lets the rest of the tree run. That bounds what this branch
can cost, whatever the client does with the clicks.

**What standing aside costs.** The readings it gives back are readings on which
the location info panel is absent or collapsed, so everything below that reads
it -- the surroundings button, the station name, the system name -- does not
match and does not fire on them. That is the trade, taken deliberately: a bot
that cannot name the system it is in is worth strictly more than a bot that
cannot leave it.

-}
ensureInfoPanelLocationInfoIsExpanded :
    List Common.EffectOnWindow.EffectOnWindowStructure
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
ensureInfoPanelLocationInfoIsExpanded previousStepEffects readingFromGameClient =
    if infoPanelRepairClickIsSettling previousStepEffects readingFromGameClient then
        Nothing

    else
        case readingFromGameClient.infoPanelContainer |> Maybe.andThen .infoPanelLocationInfo of
            Nothing ->
                Just
                    (Common.DecisionPath.describeBranch "I do not see the location info panel. Enable the info panel."
                        (case readingFromGameClient.infoPanelContainer |> Maybe.andThen .icons |> Maybe.andThen .locationInfo of
                            Nothing ->
                                Common.DecisionPath.describeBranch "I do not see the icon for the location info panel." askForHelpToGetUnstuck

                            Just iconLocationInfoPanel ->
                                Common.DecisionPath.describeBranch
                                    "Click on the icon to enable the info panel."
                                    (iconLocationInfoPanel
                                        |> mouseClickOnUIElement Common.EffectOnWindow.MouseButtonLeft
                                        |> decideActionForCurrentStep
                                    )
                        )
                    )

            Just infoPanelLocationInfo ->
                if 35 < infoPanelLocationInfo.uiNode.totalDisplayRegion.height then
                    Nothing

                else
                    -- `(x + 8, y + 8)` is unchanged and **unverified**. #297 reads
                    -- it as the panel's own header corner, which on this client
                    -- toggles the panel rather than expanding it -- that is the
                    -- issue's account of why the panel leaves the tree after this
                    -- click. Nothing in the recorded corpus or in the parser names
                    -- an expander control to aim at instead, and no reading of a
                    -- collapsed panel's subtree has been captured, so the target
                    -- stays where it was and is guarded rather than moved. Moving
                    -- it needs a live client with the panel collapsed.
                    Just
                        (Common.DecisionPath.describeBranch "Location info panel seems collapsed."
                            (Common.DecisionPath.describeBranch "Click to expand the info panel."
                                ({ x = infoPanelLocationInfo.uiNode.totalDisplayRegion.x + 8
                                 , y = infoPanelLocationInfo.uiNode.totalDisplayRegion.y + 8
                                 }
                                    |> Common.EffectOnWindow.effectsMouseClickAtLocation
                                        Common.EffectOnWindow.MouseButtonLeft
                                    |> decideActionForCurrentStep
                                )
                            )
                        )


{-| How many readings in a row without a ship UI it takes before _docked_ is a
conclusion the split will draw with nothing else to go on.

An absent ship UI has at least three causes, and the split below used to collapse
them into the one that is almost never true here:

1.  genuinely docked -- and then it stays absent for as long as the ship is in
    the station, and the station window is there to say so;
2.  **a reading the parser could not complete** -- and then it is back within a
    few readings and nothing else is there either;
3.  a session change or a client stall.

Issue #304 records four `I am stuck here and need help to continue.` alarms
across three runs, and every one of them is case 2: the reading before the alarm
and the reading after it both show a live ship in space, with real hitpoints,
rats on the overview and incoming damage. The ship never docked.

**The number is the longest case-2 episode in the recorded corpus, plus two.**
Measured over every `*.log` under `~/eve-bot-logs` -- 111 files, 1,082,795 host
ticks -- there are 107 episodes where the ship UI was absent while the ship was
demonstrably in space. Counted in _readings_ rather than in log entries, which is
the unit this bound is in: the host prints roughly three entries per completed
memory read, and the bot only decides on the entry where the read completes.
100 of the 107 are one reading, five are two, one is three, and one is **ten** --
`mission_run35.log`, ticks 2540.5 to 2550.1, ten consecutive failed reads over
17.1 seconds. So the issue's proposed two would have left most of the tail, and
twelve clears all of it with a reading to spare on a tail that has exactly one
point in it above three.

**Twelve is affordable because a genuine dock does not pay it.** The split takes
the docked arm at once when the station window is there, which is what a docked
client shows and what a ship in space cannot; the count is only consulted where
nothing corroborates, which is the case that used to raise the alarm. So the
price of the bound is paid on the readings the bot could not read anyway, not on
every dock cycle.

**The alarm is delayed, not removed.** A ship that really is stuck shows no ship
UI on any reading, so the count reaches this bound and stays there, and
`askForHelpToGetUnstuck` is raised on the twelfth reading and on every reading
after it -- some 35 seconds later than before, for a signal whose whole purpose
is to fetch a human.

**Not a bound on `askForHelpToGetUnstuck`.** The alarm is the symptom. The cause
is a bot concluding it is docked from one dropped reading and then choosing on
that arm -- so the corroboration is at the split, where the conclusion is drawn,
rather than at the one branch that happened to shout about it.

-}
readingsWithoutShipUIBeforeAssumingDocked : Int
readingsWithoutShipUIBeforeAssumingDocked =
    12


{-| The count the split is corroborated against, advanced by one reading.

A declaration of its own rather than a `let` inside
`processEventInBaseFramework`, for the reason #297 pulled
`infoPanelRepairClickIsSettling` out of the branch that consulted it: a rule
reachable only by driving the whole event handler is a rule no case can ask
about, and a case that drives the handler asserts on the handler.

The argument order is `reading` then `before` so that
`List.foldl countReadingsWithoutShipUI 0` is the whole history of a session,
which is how the cases in `test_docked_assumption_needs_corroboration.py` get
the number they hand to the split.

**Capped rather than left to climb.** Since #284 the host suppresses a status
line only while it is unchanged, so a count that keeps rising is the docked
branch's description rewritten on every reading -- a status block reprinted for
as long as the ship sits in the station. Nothing above the cap is asked
anything: the split compares against the cap and no other number.

-}
countReadingsWithoutShipUI : ReadingFromGameClient -> Int -> Int
countReadingsWithoutShipUI readingFromGameClient before =
    case readingFromGameClient.shipUI of
        Nothing ->
            min readingsWithoutShipUIBeforeAssumingDocked (before + 1)

        Just _ ->
            0


branchDependingOnDockedOrInSpace :
    { ifDocked : DecisionPathNode
    , ifSeeShipUI : EveOnline.ParseUserInterface.ShipUI -> Maybe DecisionPathNode
    , ifUndockingComplete : SeeUndockingComplete -> DecisionPathNode
    }
    -> Int
    -> ReadingFromGameClient
    -> DecisionPathNode
branchDependingOnDockedOrInSpace { ifDocked, ifSeeShipUI, ifUndockingComplete } readingsWithoutShipUI readingFromGameClient =
    case readingFromGameClient.shipUI of
        Nothing ->
            case readingFromGameClient.stationWindow of
                Just _ ->
                    -- The positive half of the corroboration, and the reason
                    -- the bound above is affordable. A missing ship UI is the
                    -- absence of evidence; a station window is evidence, and
                    -- one the client cannot show to a ship in space. Every dock
                    -- the corpus records arrives with it, so the common case
                    -- costs no readings at all.
                    Common.DecisionPath.describeBranch
                        "I see no ship UI and I do see the station window -- we are docked."
                        ifDocked

                Nothing ->
                    if readingsWithoutShipUI < readingsWithoutShipUIBeforeAssumingDocked then
                        -- Not `ifDocked`, which is the conclusion this reading
                        -- does not support, and not the in-space arm either,
                        -- which has no ship UI to be handed. Nothing else is
                        -- waiting on the reading: this split is the last entry
                        -- in every app's decision root, so what is given back
                        -- is a reading on which the bot could only have
                        -- guessed.
                        Common.DecisionPath.describeBranch
                            ("I see no ship UI and no station window either, and only on the last "
                                ++ String.fromInt readingsWithoutShipUI
                                ++ " reading(s) -- not yet enough to conclude we docked. Wait for the next reading rather than acting on it."
                            )
                            waitForProgressInGame

                    else
                        Common.DecisionPath.describeBranch
                            "I have seen no ship UI and no station window for long enough that a dropped reading cannot explain it -- assume we are docked."
                            ifDocked

        Just shipUI ->
            ifSeeShipUI shipUI
                |> Maybe.withDefault
                    (case readingFromGameClient.overviewWindows of
                        [] ->
                            Common.DecisionPath.describeBranch
                                "I see no overview window, wait until undocking completed."
                                waitForProgressInGame

                        overviewWindows ->
                            Common.DecisionPath.describeBranch "I see ship UI and overview, undocking complete."
                                (ifUndockingComplete
                                    { shipUI = shipUI, overviewWindows = overviewWindows }
                                )
                    )


waitForProgressInGame : DecisionPathNode
waitForProgressInGame =
    Common.DecisionPath.describeBranch "Wait for progress in game"
        (decideActionForCurrentStep [])
        |> updateMillisecondsToNextReadingFromGameModifierPercent (always 100)


askForHelpToGetUnstuck : DecisionPathNode
askForHelpToGetUnstuck =
    Common.DecisionPath.describeBranch "I am stuck here and need help to continue."
        (decideActionForCurrentStep [])
        |> updateMillisecondsToNextReadingFromGameModifierPercent (always 100)


readShipUIModuleButtonTooltipWhereNotYetInMemory :
    { a
        | readingFromGameClient : ReadingFromGameClient
        , memory : { b | shipModules : ShipModulesMemory }
    }
    -> Maybe DecisionPathNode
readShipUIModuleButtonTooltipWhereNotYetInMemory context =
    context.readingFromGameClient.shipUI
        |> Maybe.map .moduleButtons
        |> Maybe.withDefault []
        |> List.filter (getModuleButtonTooltipFromModuleButton context.memory.shipModules >> (==) Nothing)
        |> List.head
        |> Maybe.map
            (\moduleButtonWithoutMemoryOfTooltip ->
                Common.DecisionPath.describeBranch "Read tooltip for module button"
                    (decideActionForCurrentStep
                        (EveOnline.BotFramework.mouseMoveToUIElement moduleButtonWithoutMemoryOfTooltip.uiNode)
                    )
            )


updateMillisecondsToNextReadingFromGameModifierPercent : (Int -> Int) -> DecisionPathNode -> DecisionPathNode
updateMillisecondsToNextReadingFromGameModifierPercent update decisionPath =
    updateDecisionPathEndContinueSession
        (\continueSession ->
            { continueSession
                | millisecondsToNextReadingFromGameModifierPercent =
                    update continueSession.millisecondsToNextReadingFromGameModifierPercent
            }
        )
        decisionPath


setMillisecondsToNextReadingFromGameBase : Int -> DecisionPathNode -> DecisionPathNode
setMillisecondsToNextReadingFromGameBase millisecondsToNextReadingFromGameBase decisionPath =
    updateDecisionPathEndContinueSession
        (\continueSession ->
            { continueSession | millisecondsToNextReadingFromGameBase = Just millisecondsToNextReadingFromGameBase }
        )
        decisionPath


updateDecisionPathEndContinueSession : (ContinueSessionStructure -> ContinueSessionStructure) -> DecisionPathNode -> DecisionPathNode
updateDecisionPathEndContinueSession updateContinueSession decisionPath =
    Common.DecisionPath.continueDecisionPath
        (\pathEnd ->
            Common.DecisionPath.endDecisionPath
                (case pathEnd of
                    ContinueSession continueSession ->
                        ContinueSession (updateContinueSession continueSession)

                    FinishSession ->
                        pathEnd
                )
        )
        decisionPath


decideActionForCurrentStep : List Common.EffectOnWindow.EffectOnWindowStructure -> DecisionPathNode
decideActionForCurrentStep effects =
    Common.DecisionPath.endDecisionPath
        (ContinueSession
            { effectsOnGameClient = effects
            , millisecondsToNextReadingFromGameBase = Nothing
            , millisecondsToNextReadingFromGameModifierPercent = 0
            }
        )
