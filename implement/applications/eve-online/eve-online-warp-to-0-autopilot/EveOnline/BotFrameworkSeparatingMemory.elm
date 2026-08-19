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

import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost
import Common
import Common.DecisionPath
import Common.EffectOnWindow
import Dict
import EveOnline.BotFramework
    exposing
        ( OverviewWindowMemorySnapshot
        , ReadingFromGameClient
        , ReadingFromGameClientMemory
        , ReadingFromGameClientScreenshot
        , ShipModulesMemory
        , UIElement
        , UseContextMenuCascadeNode
        , asReadingFromGameClientMemory
        , closestPointOnRectangleEdge
        , doEffectsClickModuleButton
        , getModuleButtonTooltipFromModuleButton
        , growRegionOnAllSides
        , isPointInRectangle
        , mouseClickOnUIElement
        )
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindow
        , centerFromDisplayRegion
        , subtractRegionsFromRegion
        )
import List.Extra
import Result.Extra


type EndDecisionPathStructure
    = ContinueSession ContinueSessionStructure
    | FinishSession


type alias ContinueSessionStructure =
    { effectsOnGameClient : List Common.EffectOnWindow.EffectOnWindowStruct
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
    , previousStepsEffects : List (List Common.EffectOnWindow.EffectOnWindowStruct)
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
    , lastStepsEffects : List (List Common.EffectOnWindow.EffectOnWindowStruct)
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
    , lastStepsEffects = []
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
                readingFromGameClient : EveOnline.ParseUserInterface.ParsedUserInterface
                readingFromGameClient =
                    readingFromGameClientCompleted.parsed

                screenshot =
                    readingFromGameClientCompleted.screenshot

                updateMemoryContext =
                    { timeInMilliseconds = eventContext.timeInMilliseconds
                    , readingFromGameClient = readingFromGameClient
                    , screenshot = screenshot
                    }

                botMemory : botMemory
                botMemory =
                    stateBefore.botMemory
                        |> config.updateMemoryForNewReadingFromGame updateMemoryContext

                lastReadingFromGameClientContextMenus : List EveOnline.BotFramework.ContextMenu
                lastReadingFromGameClientContextMenus =
                    stateBefore.lastReadingsFromGameClient
                        |> List.head
                        |> Maybe.map .contextMenus
                        |> Maybe.withDefault []

                contextMenuCascadeLevelAlreadyInPreviousReading : Int
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

                contextMenuCascadeLevel : Int
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
                    , previousStepsEffects = stateBefore.lastStepsEffects
                    , previousReadingsFromGameClient = stateBefore.lastReadingsFromGameClient
                    , readingsWithoutShipUI = readingsWithoutShipUI
                    , contextMenuCascadeLevel = contextMenuCascadeLevel
                    , randomIntegers = readingFromGameClientCompleted.randomIntegers
                    }

                ( decisionStagesDescriptions, decisionLeaf ) =
                    config.decideNextStep decisionContext
                        |> Common.DecisionPath.unpackToDecisionStagesDescriptionsAndLeaf

                effectsOnGameClientWindow : List Common.EffectOnWindow.EffectOnWindowStruct
                effectsOnGameClientWindow =
                    case decisionLeaf of
                        ContinueSession act ->
                            act.effectsOnGameClient

                        FinishSession ->
                            []

                describeActivity : String
                describeActivity =
                    decisionStagesDescriptions
                        |> List.indexedMap
                            (\decisionLevel -> (++) (("+" |> List.repeat (decisionLevel + 1) |> String.join "") ++ " "))
                        |> String.join "\n"

                statusText : String
                statusText =
                    [ config.statusTextFromDecisionContext decisionContext
                    , describeActivity
                    ]
                        |> String.join "\n"

                readingFromGameClientMemory : ReadingFromGameClientMemory
                readingFromGameClientMemory =
                    asReadingFromGameClientMemory readingFromGameClient

                lastStepsEffects : List (List Common.EffectOnWindow.EffectOnWindowStruct)
                lastStepsEffects =
                    -- Same trap the reading history below fell into: this was
                    -- capped at 2, so no consumer could look back further than
                    -- two steps no matter what it asked for. That is not enough
                    -- to cover a click whose result the client has not shown yet
                    -- -- see `moduleButtonClickSettlingSteps`, where a too-short
                    -- window made the bot click a module a second time and
                    -- toggle it back off.
                    effectsOnGameClientWindow
                        :: stateBefore.lastStepsEffects
                        |> List.take 10
            in
            ( { botMemory = botMemory
              , lastStepsEffects = lastStepsEffects
              , lastReadingsFromGameClient =
                    -- The "no progress" discard check in
                    -- useContextMenuCascadeWithCustomConfig looks back up to
                    -- 8 readings (widened from 4 there, on the strength of
                    -- live findings about slow-to-render flyouts) -- but
                    -- this storage cap was never widened to match, so that
                    -- widening was a no-op the entire time: with at most 4
                    -- readings ever retained here, `List.take 8` on the
                    -- consuming side had nothing beyond 4 to find regardless
                    -- of what its own comment claimed. Caught live: a
                    -- 3-level-deep flyout (surroundings button -> Stations
                    -- -> a specific station list) kept discarding and
                    -- reopening from scratch after only 4 real ticks,
                    -- visually already rendered on screen (confirmed via
                    -- screenshot) but not yet visible to our own reads.
                    readingFromGameClientMemory
                        :: stateBefore.lastReadingsFromGameClient
                        |> List.take 8
              , readingsWithoutShipUI = readingsWithoutShipUI
              }
            , case decisionLeaf of
                ContinueSession continueSession ->
                    let
                        millisecondsToNextReadingFromGame : Int
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
        ( "overview entry '" ++ (overviewEntry.objectName |> Maybe.withDefault "") ++ "'"
        , overviewEntry.uiNode
        )
        useContextMenu
        context


useContextMenuCascadeOnListSurroundingsButton :
    UseContextMenuCascadeNode
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascadeOnListSurroundingsButton useContextMenu context =
    case context.readingFromGameClient.infoPanelContainer of
        Nothing ->
            Common.DecisionPath.describeBranch
                "I do not see any info panel."
                askForHelpToGetUnstuck

        Just infoPanelContainer ->
            case infoPanelContainer.infoPanelLocationInfo of
                Nothing ->
                    Common.DecisionPath.describeBranch
                        "I do not see the location info panel."
                        askForHelpToGetUnstuck

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
        case
            -- See filterToDiscardContextMenuDefault for why 70, not 40:
            -- same real per-cycle latency on this host, same on-screen
            -- drift risk for the target element between read and click.
            discardContextMenuIfTooDistantFromTargetElement
                { toleratedDistance = 70 }
                target
                context
                cascadeFirstElement
        of
            Nothing ->
                Nothing

            Just reasonToDiscard ->
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


filterToDiscardContextMenuDefault : FilterToDiscardContextMenu a b
filterToDiscardContextMenuDefault =
    {-
       This host's own per-cycle latency (RequestToVolatileProcess dispatch
       measured at 1.8-2.0s in real runs) is higher than a native
       Windows/BotLab.exe host's, and the target elements this filter
       protects (overview rows, target-bar icons) track a moving 3D
       object's on-screen projection, not a fixed UI panel -- their
       position can genuinely drift by more than a few pixels in that
       window. Observed live: a locked-target icon's own previous click
       fell outside its ~30-40px bounding box entirely (the discard
       reason's first coordinate showed "none"), forcing the fallback
       "assume it was the exact center" comparison and discarding a menu
       that had, in fact, opened correctly. Widened from 40 to reduce
       these false discards; still tight enough that two distinct UI
       elements' menus won't plausibly land within tolerance of each
       other.
    -}
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


{-| How many steps back a right-click of our own still counts as "the menu may
still be rendering", so the cascade waits instead of clicking again.

Sized on the client, not on taste. A freshly opened menu's widget exists and is
visibly on screen before its display-region entries are populated, and the
parser drops nodes without a region -- so a real, open menu reads back as zero
menus for the length of that gap, measured live at 10+ readings. Clicking again
in that window does not merely fail to help: a second right-click on an
already-open menu dismisses it, which converts rendering lag into an endless
open/close loop.

The effects history holds 10 steps, so this is bounded by construction however
large it is written.

-}
readingsToWaitForAFirstContextMenu : Int
readingsToWaitForAFirstContextMenu =
    10


useContextMenuCascadeWithCustomConfig :
    FilterToDiscardContextMenu a b
    -> { targetUIElement : UIElement, targetUIElementName : String }
    -> UseContextMenuCascadeNode
    -> StepDecisionContext a b
    -> DecisionPathNode
useContextMenuCascadeWithCustomConfig filterToDiscardContextMenu target useContextMenu context =
    let
        readingFromGameClient : ReadingFromGameClient
        readingFromGameClient =
            context.readingFromGameClient

        describeDisplayRegion : EveOnline.ParseUserInterface.DisplayRegion -> String
        describeDisplayRegion region =
            "x="
                ++ String.fromInt region.x
                ++ " y="
                ++ String.fromInt region.y
                ++ " w="
                ++ String.fromInt region.width
                ++ " h="
                ++ String.fromInt region.height

        beginCascade : Common.DecisionPath.DecisionPathNode EndDecisionPathStructure
        beginCascade =
            let
                occludingRegionsWithSafetyMargin : List EveOnline.ParseUserInterface.DisplayRegion
                occludingRegionsWithSafetyMargin =
                    readingFromGameClient.contextMenus
                        |> List.map (.uiNode >> .totalDisplayRegion >> growRegionOnAllSides 2)

                regionsRemainingAfterOcclusion : List EveOnline.ParseUserInterface.DisplayRegion
                regionsRemainingAfterOcclusion =
                    subtractRegionsFromRegion
                        { minuend = target.targetUIElement.totalDisplayRegion
                        , subtrahend = occludingRegionsWithSafetyMargin
                        }
            in
            case
                regionsRemainingAfterOcclusion
                    |> List.filter (\region -> 3 < region.width && 3 < region.height)
                    |> List.sortBy (\region -> negate (min region.width region.height))
                    |> List.head
            of
                Nothing ->
                    {-
                       This used to right-click a computed "somewhere else"
                       location to dismiss the occluding menu(s) -- either
                       just above the neocom clock, or a bottom-left
                       fallback (x=4, y=height-30) when no clock was found.
                       Feedback from a live run: that location isn't
                       reliably empty space -- it can land on a real
                       Neocom icon or another clickable element near the
                       clock, opening a *different* menu (or acting on
                       whatever's there) instead of dismissing anything.
                       When the next step then moves to click its real
                       target (e.g. an overview entry), it can hit a
                       button from that stray menu sitting in the way
                       instead -- observed live wiping the autopilot
                       route via an accidentally-triggered "Clear All
                       Waypoints". Escape closes an open context menu
                       reliably without clicking anywhere at all, so
                       nothing can be in the way to hit by accident --
                       same fix already proven for stray menus elsewhere
                       (see clearStrayContextMenu in Bot.elm).
                    -}
                    Common.DecisionPath.describeBranch
                        ("All of "
                            ++ target.targetUIElementName
                            ++ " ("
                            ++ describeDisplayRegion target.targetUIElement.totalDisplayRegion
                            ++ ") is occluded by "
                            ++ String.fromInt (List.length occludingRegionsWithSafetyMargin)
                            ++ " context menu region(s)."
                        )
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
                        ("Open context menu on "
                            ++ target.targetUIElementName
                            ++ " (cascade level "
                            ++ String.fromInt context.contextMenuCascadeLevel
                            ++ ", "
                            ++ String.fromInt (List.length readingFromGameClient.contextMenus)
                            ++ " menu(s) currently open)"
                        )
                        (preferredRegion
                            |> centerFromDisplayRegion
                            |> Common.EffectOnWindow.effectsMouseClickAtLocation Common.EffectOnWindow.MouseButtonRight
                            |> decideActionForCurrentStep
                        )

        discardExistingContextMenu : String -> Common.DecisionPath.DecisionPathNode EndDecisionPathStructure
        discardExistingContextMenu reasonToDiscard =
            Common.DecisionPath.describeBranch
                ("Discard existing context menu (" ++ reasonToDiscard ++ ")")
                beginCascade
    in
    case
        -- "no progress" below compares the current reading against the
        -- oldest of the last N readings: feedback from a real run was
        -- that this discard-and-reopen was firing on jumpToNextSystem's
        -- cascade (the route icon, which sits in a strip that can shift
        -- slightly between reads) before the menu had genuinely finished
        -- settling -- widened from 3 to 4 for that. Feedback from a later
        -- run: still firing too eagerly on two more cascades that expand
        -- a hover-triggered Photon-UI flyout submenu (enterAnomaly's
        -- "Warp to Within..." distance list, and the wreck loot menu's
        -- "Loot All"/"Open Cargo" cascade) -- both got dismissed before
        -- the flyout had a chance to open, and both "eventually
        -- succeeded" only after several wasted discard-and-reopen
        -- cycles. Widened further, from 4 to 8, to give a slow-to-render
        -- flyout enough real ticks to appear before giving up on it.
        context.previousReadingsFromGameClient
            |> List.take 8
            |> List.reverse
            |> List.head
    of
        Nothing ->
            beginCascade

        Just previousReadingFromGameClient ->
            case List.reverse context.readingFromGameClient.contextMenus of
                [] ->
                    -- Root-caused live (2026-07-28, via a memory dump
                    -- correlated with the parsing code): a freshly opened
                    -- context menu's own widget object can exist in the
                    -- game -- and be visibly rendered on screen -- before
                    -- its display-region dict entries are populated.
                    -- EveOnline.ParseUserInterface.asUITreeNodeWithInheritedOffset
                    -- drops any node without a parseable display region
                    -- (ChildWithoutRegion), and parseContextMenusFromUITreeRoot
                    -- depends on exactly that filtered traversal to find
                    -- the 'l_menu' layer's children -- so a real, open
                    -- menu can read back as zero context menus for however
                    -- many ticks that gap lasts. Immediately right-clicking
                    -- again in that state (the previous unconditional
                    -- fallback here) doesn't just fail to help -- a second
                    -- right-click on an already-open menu commonly
                    -- dismisses it, turning a few ticks of real rendering
                    -- lag into a self-inflicted endless open/close loop
                    -- (confirmed live: repeated identical "click"/"open"
                    -- decisions with the menu never showing as open, for
                    -- as long as 10+ real ticks in one observed case).
                    -- If our own last step or two already fired a
                    -- right-click, give the game one more reading to
                    -- finish populating the new menu's layout before
                    -- concluding it isn't there and clicking again.
                    --
                    -- The `List.take` is what makes the wait literal, and how
                    -- far it looks back is the whole of this fix. It was 2 --
                    -- while the paragraph above, from the session that
                    -- root-caused the rendering gap, records that gap lasting
                    -- "as long as 10+ real ticks in one observed case". A cap
                    -- set below the phenomenon it caps is the loop rather than
                    -- the guard against it: saxrat's run 46 right-clicked a
                    -- scan result 385 times, spent 1,340 readings waiting, and
                    -- read the menu back **zero** times, because every third
                    -- reading it clicked again and dismissed the menu it was
                    -- waiting for.
                    --
                    -- Bounded by the history itself, which holds 10 steps, so
                    -- this cannot become the unbounded search the original was
                    -- guarding against. And it costs a healthy cascade nothing:
                    -- the arm below runs the moment *any* menu is in the
                    -- reading, so waiting longer only ever delays the case that
                    -- would otherwise have destroyed its own menu.
                    if
                        context.previousStepsEffects
                            |> List.take readingsToWaitForAFirstContextMenu
                            |> List.any
                                (List.member
                                    (Common.EffectOnWindow.ButtonDown Common.EffectOnWindow.MouseButtonRight)
                                )
                    then
                        Common.DecisionPath.describeBranch
                            "No context menu in this reading yet, but we right-clicked within the last couple of steps -- give the game one more reading before assuming it isn't there."
                            waitForProgressInGame

                    else
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
                            -- Root-caused live (2026-07-28, via `screen -X
                            -- hardcopy` on a real stuck session plus a
                            -- memory dump of the actual rendered menu):
                            -- this used to check "did the open menu(s)'
                            -- own on-screen region change since N readings
                            -- ago" *before* ever trying
                            -- getNextContextMenu (the thing that actually
                            -- reads the entries and decides what to click)
                            -- -- so a menu that finished rendering and then
                            -- sat perfectly stable (the *good*, normal end
                            -- state once a flyout is done animating) read
                            -- as "no progress" and got discarded and
                            -- reopened forever, without getNextContextMenu
                            -- ever running even once. Confirmed live: for
                            -- the surroundings-button cascade specifically,
                            -- whose own 2023-01-12 comment already
                            -- documents that opening it can auto-expand a
                            -- second level (here, "Stations") immediately
                            -- -- exactly the stable-after-one-tick shape
                            -- this bug silently ate every time.
                            --
                            -- Now tries getNextContextMenu unconditionally
                            -- first, and only consults region-stability
                            -- to decide *how to react to a failure*: a
                            -- fresh Err (the menu hasn't rendered deep
                            -- enough yet, still changing) waits for another
                            -- reading rather than reopening -- reopening on
                            -- an incompletely-rendered menu is what risks
                            -- toggling a real, working menu closed, the
                            -- same class of self-inflicted loop as the
                            -- empty-reading case above. Only once the SAME
                            -- Err persists with the menu(s) themselves
                            -- unchanged across the lookback does it give up
                            -- and discard-and-reopen -- preserving the
                            -- original patience for slow renders while no
                            -- longer skipping the actual attempt.
                            case
                                EveOnline.BotFramework.getNextContextMenu
                                    useContextMenu
                                    readingFromGameClient
                                    (min
                                        (List.length cascadeFollowingElements)
                                        (context.contextMenuCascadeLevel - 1)
                                    )
                            of
                                Err err ->
                                    if
                                        (context.readingFromGameClient.contextMenus |> List.map identifyingInfoFromContextMenu)
                                            == (previousReadingFromGameClient.contextMenus |> List.map identifyingInfoFromContextMenu)
                                    then
                                        discardExistingContextMenu
                                            ("failed to continue ("
                                                ++ err
                                                ++ "), no progress across the last "
                                                ++ String.fromInt (min 8 (List.length context.previousReadingsFromGameClient))
                                                ++ " reading(s) -- still "
                                                ++ String.fromInt (List.length context.readingFromGameClient.contextMenus)
                                                ++ " menu(s) open at cascade level "
                                                ++ String.fromInt context.contextMenuCascadeLevel
                                                ++ ", first menu region ("
                                                ++ describeDisplayRegion cascadeFirstElement.uiNode.totalDisplayRegion
                                                ++ ")"
                                            )

                                    else
                                        Common.DecisionPath.describeBranch
                                            ("Failed to continue context menu for now (" ++ err ++ ") -- still changing, give it another reading before giving up.")
                                            waitForProgressInGame

                                Ok EveOnline.BotFramework.CompletedMenuCascade ->
                                    Common.DecisionPath.describeBranch
                                        ("Completed cascade on " ++ target.targetUIElementName)
                                        beginCascade

                                Ok (EveOnline.BotFramework.ContinueMenuCascade ( stepDescription, effectsToGameClient )) ->
                                    Common.DecisionPath.describeBranch stepDescription
                                        (decideActionForCurrentStep effectsToGameClient)


discardContextMenuIfTooDistantFromTargetElement :
    { toleratedDistance : Int }
    -> FilterToDiscardContextMenu a b
discardContextMenuIfTooDistantFromTargetElement { toleratedDistance } =
    \{ targetUIElement } context cascadeFirstElement ->
        let
            previousStepClickOnTargetLocation : Maybe EveOnline.BotFramework.Location2d
            previousStepClickOnTargetLocation =
                case context.previousStepsEffects of
                    [] ->
                        Nothing

                    previousStepEffects :: _ ->
                        previousStepEffects
                            |> EveOnline.BotFramework.findMouseButtonClickLocationsInListOfEffects
                                Common.EffectOnWindow.MouseButtonRight
                            |> Common.listFind (isPointInRectangle targetUIElement.totalDisplayRegion)

            projectedTargetClickLocation : EveOnline.ParseUserInterface.Location2d
            projectedTargetClickLocation =
                previousStepClickOnTargetLocation
                    |> Maybe.withDefault (centerFromDisplayRegion targetUIElement.totalDisplayRegion)

            cascadeFirstElementEdgesClosestPointToTargetUIElement : EveOnline.BotFramework.Location2d
            cascadeFirstElementEdgesClosestPointToTargetUIElement =
                projectedTargetClickLocation
                    |> closestPointOnRectangleEdge cascadeFirstElement.uiNode.totalDisplayRegion

            distanceSquared : Int
            distanceSquared =
                EveOnline.BotFramework.distanceSquaredBetweenLocations
                    projectedTargetClickLocation
                    cascadeFirstElementEdgesClosestPointToTargetUIElement

            -- Rounded pixel distance, purely for the diagnostic message
            -- below -- the actual pass/fail comparison stays in the
            -- squared domain (cascadeFirstElementIsCloseToInitialUIElement)
            -- to avoid a Float round-trip on the value that decides
            -- behavior.
            distance : Int
            distance =
                distanceSquared |> toFloat |> sqrt |> round

            cascadeFirstElementIsCloseToInitialUIElement : Bool
            cascadeFirstElementIsCloseToInitialUIElement =
                distanceSquared < (toleratedDistance * toleratedDistance)

            cascadeFirstElementIsInExpectedRegion : Bool
            cascadeFirstElementIsInExpectedRegion =
                cascadeFirstElementIsCloseToInitialUIElement

            describeLocation location =
                String.fromInt location.x ++ ", " ++ String.fromInt location.y
        in
        if not cascadeFirstElementIsInExpectedRegion then
            Just
                (String.fromInt distance
                    ++ "px from target, tolerance "
                    ++ String.fromInt toleratedDistance
                    ++ "px (previous click "
                    ++ Maybe.withDefault "none" (Maybe.map describeLocation previousStepClickOnTargetLocation)
                    ++ ", projected target "
                    ++ describeLocation projectedTargetClickLocation
                    ++ ", cascade element x="
                    ++ String.fromInt cascadeFirstElement.uiNode.totalDisplayRegion.x
                    ++ " y="
                    ++ String.fromInt cascadeFirstElement.uiNode.totalDisplayRegion.y
                    ++ " w="
                    ++ String.fromInt cascadeFirstElement.uiNode.totalDisplayRegion.width
                    ++ " h="
                    ++ String.fromInt cascadeFirstElement.uiNode.totalDisplayRegion.height
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
doEffectsClickUIElement : UIElement -> List Common.EffectOnWindow.EffectOnWindowStruct -> Bool
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

-}
infoPanelRepairClickIsSettling :
    List (List Common.EffectOnWindow.EffectOnWindowStruct)
    -> ReadingFromGameClient
    -> Bool
infoPanelRepairClickIsSettling previousStepsEffects readingFromGameClient =
    case readingFromGameClient.infoPanelContainer of
        Nothing ->
            False

        Just infoPanelContainer ->
            previousStepsEffects
                |> List.take moduleButtonClickSettlingSteps
                |> List.any (doEffectsClickUIElement infoPanelContainer.uiNode)


{-| Gets the location info panel back when the client is not showing it.

**While a repair click is settling this answers `Nothing`, not
`waitForProgressInGame`, and that is the second half of #297.** This function is
reached from `generalSetupInUserInterface`, which sits above the pod recovery
and above `branchDependingOnDockedOrInSpace` -- so every `Just` here is the
whole tree below held for that reading, `runAwayIfLowHealth` included. #227
deliberately left a give-up out of the branch it fixed ("one click that lands
ought to be enough, and if it demonstrably is not, that is a separate finding");
#297 is that finding -- it counts the pair on 22 of the 27 runs it read, one of
them 240 minutes into a 180 minute session with the wind-down never reached.

So the repair still clicks -- once per `moduleButtonClickSettlingSteps` readings,
which is as often as a toggle can usefully be clicked -- and on every other
reading it stands aside and lets the rest of the tree run. That bounds what this
branch can cost at one reading in `moduleButtonClickSettlingSteps + 1`, whatever
the client does with the clicks, which is the property #101 and #133 are about:
an entry in this list that can repeat forever freezes the bot rather than one
branch of it.

**What standing aside costs.** The readings it gives back are readings on which
the location info panel is absent or collapsed, so everything below that reads
it -- the surroundings button, the station name, the system name -- does not
match and does not fire on them. That is the trade, taken deliberately: a bot
that cannot name the system it is in is worth strictly more than a bot that
cannot retreat out of it.

The one wait left here is for a container with no icons in it at all, which is
the client still drawing its UI. No click of ours produces that state, so the
alternation above cannot reach it.

-}
ensureInfoPanelLocationInfoIsExpanded :
    List (List Common.EffectOnWindow.EffectOnWindowStruct)
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
ensureInfoPanelLocationInfoIsExpanded previousStepsEffects readingFromGameClient =
    if infoPanelRepairClickIsSettling previousStepsEffects readingFromGameClient then
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
                                case mouseClickOnUIElement Common.EffectOnWindow.MouseButtonLeft iconLocationInfoPanel of
                                    Err _ ->
                                        Common.DecisionPath.describeBranch "Failed to click the icon to enable the info panel."
                                            askForHelpToGetUnstuck

                                    Ok clickEffect ->
                                        Common.DecisionPath.describeBranch
                                            "Click on the icon to enable the info panel."
                                            (decideActionForCurrentStep clickEffect)
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


ensureOverviewsSorted :
    { sortColumnName : String, skipSortingWhenNotScrollable : Bool }
    -> EveOnline.BotFramework.OverviewWindowsMemory
    -> ReadingFromGameClient
    -> List ( OverviewWindow, ( String, Maybe DecisionPathNode ) )
ensureOverviewsSorted config overviewWindowsMemory readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.map
            (\overviewWindow ->
                ( overviewWindow
                , if config.skipSortingWhenNotScrollable && not (overviewWindowIsScrollable overviewWindow) then
                    ( "Overview window is not scrollable", Nothing )

                  else
                    ensureOverviewSorted
                        { sortColumnName = config.sortColumnName }
                        overviewWindowsMemory
                        overviewWindow
                )
            )


ensureOverviewSorted :
    { sortColumnName : String }
    -> EveOnline.BotFramework.OverviewWindowsMemory
    -> OverviewWindow
    -> ( String, Maybe DecisionPathNode )
ensureOverviewSorted config overviewWindowsMemory overviewWindow =
    let
        ( _, overviewWindowMemory ) =
            EveOnline.BotFramework.integrateCurrentReadingsIntoOverviewWindowMemory overviewWindow overviewWindowsMemory

        bubbleSortDistanceFromListOfLengths : List (Result String Int) -> Int
        bubbleSortDistanceFromListOfLengths =
            List.filterMap Result.toMaybe
                >> bubbleSortCountingIterations identity
                >> Tuple.second

        bubbleSortDistanceFromSnapshot : OverviewWindowMemorySnapshot -> Int
        bubbleSortDistanceFromSnapshot =
            .entriesSortedFromTop
                >> List.map
                    (.cellsTexts
                        >> Dict.toList
                        >> List.Extra.find (Tuple.first >> String.toLower >> (==) (String.toLower config.sortColumnName))
                        >> Maybe.map Tuple.second
                        >> Maybe.map EveOnline.ParseUserInterface.parseOverviewEntryDistanceInMetersFromText
                        >> Maybe.withDefault (Err ("Sort column '" ++ config.sortColumnName ++ "' not found"))
                    )
                >> bubbleSortDistanceFromListOfLengths

        bubbleSortDistanceMinimum =
            overviewWindowMemory.previousSnapshots
                |> List.map bubbleSortDistanceFromSnapshot
                |> List.minimum
                |> Maybe.withDefault 0
    in
    case
        overviewWindow.entriesHeaders
            |> List.filter (Tuple.first >> String.toLower >> (==) (String.toLower config.sortColumnName))
            |> List.head
    of
        Nothing ->
            ( "Sort header for distance not found", Nothing )

        Just sortColumnHeader ->
            if bubbleSortDistanceMinimum <= 1 then
                ( "Already sorted enough", Nothing )

            else
                ( "The bubble-sort distance of overview entries was at least "
                    ++ String.fromInt bubbleSortDistanceMinimum
                    ++ " in each of the last "
                    ++ String.fromInt (List.length overviewWindowMemory.previousSnapshots)
                    ++ " readings"
                , Just
                    (mouseClickOnUIElement Common.EffectOnWindow.MouseButtonLeft (Tuple.second sortColumnHeader)
                        |> Result.Extra.unpack
                            (always (Common.DecisionPath.describeBranch "Failed to click" askForHelpToGetUnstuck))
                            decideActionForCurrentStep
                    )
                )


overviewWindowIsScrollable : OverviewWindow -> Bool
overviewWindowIsScrollable overviewWindow =
    case overviewWindow.scrollControls of
        Nothing ->
            False

        Just scrollControls ->
            case scrollControls.scrollHandle of
                Nothing ->
                    False

                Just _ ->
                    True


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
    , ifSeeShipUI : EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
    }
    -> Int
    -> ReadingFromGameClient
    -> DecisionPathNode
branchDependingOnDockedOrInSpace { ifDocked, ifSeeShipUI } readingsWithoutShipUI readingFromGameClient =
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


{-| How many steps to let a module-button click settle before believing a
reading that still shows the module unchanged.

A module button is a toggle, so a click issued because the module "looks
inactive" is only safe while that look is current. It is not current
immediately: the bot decides from a reading taken before the click was sent,
the client needs a moment to act on it, and the module ramps up rather than
flipping. Every step inside that gap reads exactly like "still inactive".

The window used to be two steps -- and the framework only stored two, so it was
really "as long as we can see", with no margin at all. Any module slower than
that got a second click, which turned it _off_, and a third, which turned it on
again. That on/off/on flicker is what this number exists to prevent.

Bounded rather than "wait for confirmation forever" because a click genuinely
can fail to land (a lost input focus, a click that arrives while the client is
busy), and a module that is still inactive well after the fact is one that never
got the click at all.

-}
moduleButtonClickSettlingSteps : Int
moduleButtonClickSettlingSteps =
    5


clickModuleButtonButWaitIfClickedInPreviousStep :
    StepDecisionContext s m
    -> EveOnline.ParseUserInterface.ShipUIModuleButton
    -> DecisionPathNode
clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton =
    case
        context.previousStepsEffects
            |> List.take moduleButtonClickSettlingSteps
            |> List.Extra.findIndex (doEffectsClickModuleButton moduleButton)
    of
        Just stepsAgo ->
            Common.DecisionPath.describeBranch
                ("I clicked this module button "
                    ++ String.fromInt (stepsAgo + 1)
                    ++ " step(s) ago and the client has not shown the change yet -- wait rather than click it again, which would toggle it back."
                )
                waitForProgressInGame

        Nothing ->
            Common.DecisionPath.describeBranch "Click on this module button."
                (mouseClickOnUIElement Common.EffectOnWindow.MouseButtonLeft moduleButton.uiNode
                    |> Result.Extra.unpack
                        (always (Common.DecisionPath.describeBranch "Failed to click" askForHelpToGetUnstuck))
                        decideActionForCurrentStep
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


updateDecisionPathEndContinueSession :
    (ContinueSessionStructure -> ContinueSessionStructure)
    -> DecisionPathNode
    -> DecisionPathNode
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


decideActionForCurrentStep : List Common.EffectOnWindow.EffectOnWindowStruct -> DecisionPathNode
decideActionForCurrentStep effects =
    Common.DecisionPath.endDecisionPath
        (ContinueSession
            { effectsOnGameClient = effects
            , millisecondsToNextReadingFromGameBase = Nothing
            , millisecondsToNextReadingFromGameModifierPercent = 0
            }
        )


bubbleSortCountingIterations : (a -> comparable) -> List a -> ( List a, Int )
bubbleSortCountingIterations toComparable list =
    let
        sortedWithCount currentList iterations =
            let
                newList =
                    bubbleSortSingleIteration toComparable currentList
            in
            if newList == currentList then
                ( newList, iterations )

            else
                sortedWithCount newList (iterations + 1)
    in
    sortedWithCount list 0


bubbleSortSingleIteration : (a -> comparable) -> List a -> List a
bubbleSortSingleIteration toComparable list =
    let
        iter xs =
            case xs of
                [] ->
                    []

                [ x ] ->
                    [ x ]

                x :: y :: rest ->
                    if toComparable x > toComparable y then
                        y :: iter (x :: rest)

                    else
                        x :: iter (y :: rest)
    in
    iter list
