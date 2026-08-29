{- EVE Online wingman 2026-08-24

   A fleet wingman. It does not hunt: it follows a fleet commander, acts on the
   commander's broadcasts, and shoots what the fleet is shooting. Replaces
   `eve-online-wingus`, which did the same job on the retired
   `BotInterface_To_Host_2023_02_06` interface.

   ## What it does, in the order it decides

   + Undocks if it is docked.
   + Keeps the ship UI's **middle row** switched on, every slot except the
     leftmost -- by position, needing no setting and no tooltip. The leftmost
     slot is the propulsion module, which runs only while this ship is
     approaching the commander. Also activates whatever
     `activate-module-always` names by tooltip text, if anything.
   + Accepts a fleet invitation, if it is not in a fleet and the inviting pilot
     is named by `accept-fleet-invite-from`.
   + Breaks off and warps back to the fleet commander when its health or the
     incoming damage rate says to -- see `retreatToTheCommander`. **Off unless
     a `run-away-*` threshold is set**, and the status line says so on every
     reading.
   + Acts on the fleet commander's broadcasts -- see below.
   + Launches drones and assists the fleet commander while rats are on grid.
   + Closes on the fleet commander the moment it lands on a grid, ahead of the
     fight, until the client reports the manoeuvre -- and then keeps station on
     the commander whenever they have an overview row and this ship is not
     already approaching. Only the second half is governed by `orbit-fc`.
   + Routes to `home-station` through ESI and docks when the session is ending.

   ## Broadcasts

   Two forms are read, and they are shaped differently -- captured live from the
   client rather than assumed:

       Target Heather Hemorphite (Tristan)
       02:31:32 - Gal Bistot: Travel to Riramia

   A **travel** broadcast names its sender before a colon, so
   `follow-fleet-broadcast-from` can filter it. A **target** broadcast names the
   target and its ship type and **does not say who sent it**, so that allowlist
   cannot filter it: any pilot in the fleet can call a target. Fleet membership
   is itself gated by `accept-fleet-invite-from`, which is where the trust in
   this bot is placed.

   A **backup** call uses a third shape again, with no colon and the verb in the
   third person: `Gal Bistot needs backup`. It is answered by closing on the
   caller -- see `answerTheBackupCall` and `answer-backup-calls`.

   The remaining broadcasts the client offers -- `Need Shield`, `Need Armor`,
   `Need Capacitor`, `Spotted an Enemy`,
   `Request That the Fleet Hold Position` -- are enumerated from the fleet
   window's own buttons but **their rendered wording has not been observed**,
   so nothing here matches them yet. See `broadcastVerbsNotYetRead`.

   ## Setting up the Game Client

   + Set the UI language to English.
   + Undock, and open the fleet window, overview window and drones window.
   + Keep the fleet window's Broadcasts tab visible: the banner and the
     broadcast history are both read from it.
   + Set the Overview window to sort objects in space by distance with the
     nearest entry at the top.
   + In the ship UI, arrange the modules:
     + Place the modules to use in combat (to activate on targets) in the top row.
     + **Put the propulsion module in the leftmost slot of the middle row, and
       the modules to keep running -- hardeners and the like -- in the rest of
       that row.** This bot reads the row by position and never by tooltip, so
       the leftmost middle slot is the propulsion module whatever is actually
       fitted there: put something else in it and that module is switched on
       and off with the approaches instead of being held on.
     + Hide passive modules by disabling the check-box `Display Passive Modules`.
   + **Show fleet members on the active overview preset.** This bot keeps
     station on the fleet commander by double clicking the commander's
     *overview row*, so a preset that hides fleet members leaves it with
     nothing to click. It cannot change the preset and cannot tell that case
     apart from a commander who is genuinely off the grid -- the status line
     says so and names this as a possible cause.
   + Configure the keyboard key 'W' (orbit) to its default. It is used by the
     `orbit-in-combat` path. Keeping station on the commander presses no key
     at all.
   + **Nothing here changes the client's default Orbit or Approach distance,
     and nothing should.** Those defaults live in the client rather than the
     ship, so they survive losing the hull and apply to whatever is boarded
     next -- and since #359 hard-linked `core_char_*.dat` across six
     characters, a default changed while flying one of them follows the others,
     including any that later fly `eve-online-saxrat` into a belt.

   ## Configuration Settings

   All settings are optional; you only need them in case the defaults don't fit
   your use-case.

   + `accept-fleet-invite-from` : Name of a pilot whose fleet invitations this
     bot should accept, exactly as the client writes it. Repeatable. With none
     given the bot accepts no invitation at all. **Accepting means the fleet
     can warp this ship and call its targets, so name only pilots you would
     hand the ship to.**
   + `follow-fleet-broadcast-from` : Name of a pilot whose travel broadcasts
     this bot should follow. Repeatable. Matched exactly, never as a substring.
     Does not gate target broadcasts, which carry no sender, and does not gate
     backup calls either -- see `answer-backup-calls`.
   + `answer-backup-calls` : Set to 'no' to ignore `<pilot> needs backup`.
     Defaults to 'yes'. **Its trust boundary is the fleet, not
     `follow-fleet-broadcast-from`**: a fleet-mate who needs help is not
     necessarily one whose _travel_ broadcasts you follow, so the caller has to
     be someone `fleetPilotNames` recognises -- the fleet window's own member
     rows, its header's commander, or a pilot local chat's standing icon marks
     as a fleetmate. With 'yes' this ship breaks off for any of them.
   + `activate-module-always` : Text found in tooltips of ship modules that
     should always be active. For example: "shield hardener". **Optional and
     usually unnecessary**: the middle row right of the propulsion module is
     already held on by position. Use this only for a module outside that row,
     and note it takes effect only once the bot has read that module's tooltip.
   + `home-station` : Full name of the station to return to when the session is
     ending, exactly as the client renders it. Defaults to
     `Amarr VIII (Oris) - Emperor Family Academy`.
   + `assist-fleet-commander` : Set to 'no' to keep drones on this ship's own
     locked target instead of assisting the commander. Defaults to 'yes'.
   + `orbit-fc` : Set to 'no' to stop keeping station on the fleet commander.
     Defaults to 'yes', which **supersedes `orbit-in-combat`**: a wingman that
     orbits whatever it is shooting drifts off the commander's grid, which is
     the one place it is supposed to be. Also spelled `approach-fc`, which is
     the manoeuvre it actually commands: the orbit spelling is kept so a
     settings string written for an earlier version still starts a session.
     **It does not govern the close on landing.** Since #397 this bot closes on
     the commander when it lands on a grid whatever this key says, because a
     wingman that lands at range and stays there is outside logistics and
     outside support. The key governs the steady-state station-keeping it was
     written for, on every reading after the client reports the manoeuvre.
   + `orbit-fc-range` : **Accepted and ignored.** It named a rung of the
     client's Orbit submenu, and this bot no longer drives that submenu --
     keeping station is an approach at the client's own approach distance, and
     nothing here can ask for a distance. The key still parses so that a
     settings string carrying it does not end a session before it starts, and
     the status line names it as ignored on every reading it is set to anything
     other than `500 m`.
   + `orbit-in-combat` : Set to 'no' to stop orbiting the target. Read only
     when `orbit-fc` is 'no'.
   + `deactivate-module-on-warp` : Name of a module to deactivate when warping.
     Repeatable.
   + `run-away-shield-hitpoints-threshold-percent`,
     `run-away-armor-hitpoints-threshold-percent` : Percentages below which the
     bot breaks off and warps back to the fleet commander. Read through the
     believed gauge behind a low-water mark, never off the live reading.
   + `run-away-incoming-damage-threshold` : Hitpoints of incoming damage,
     summed from the client's own combat log over a rolling 45-second window,
     past which the bot breaks off. Needs no HUD gauge, which is the point of
     it.

     **All three default to -1, which is off, and that is deliberate.** They
     are facts about a hull, and no run of this bot has recorded what this one
     does under fire -- saxrat's numbers were calibrated on an Omen Navy Issue
     and carrying them here would fail silently in whichever direction this
     ship is different. Set them from a run's own recorded gauge values; see
     WINGMAN.md's "Not verified".

      When using more than one setting, start a new line for each setting in the
      text input field. Here is an example of a complete settings string:

   accept-fleet-invite-from=Gal Bistot
   follow-fleet-broadcast-from=Gal Bistot
   activate-module-always=shield hardener
   home-station=Amarr VIII (Oris) - Emperor Family Academy

-}
{-
   catalog-tags:eve-online,fleet,wingman,ratting
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
        , infoPanelRouteFirstMarkerFromReadingFromGameClient
        , localChatWindowFromUserInterface
        , menuCascadeCompleted
        , mouseClickOnUIElement
        , mouseDoubleClickOnUIElement
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
        , discardContextMenuIfTooDistantFromTargetElement
        , ensureInfoPanelLocationInfoIsExpanded
        , ensureOverviewsSorted
        , useContextMenuCascade
        , useContextMenuCascadeOnListSurroundingsButton
        , useContextMenuCascadeOnOverviewEntry
        , useContextMenuCascadeWithCustomConfig
        , waitForProgressInGame
        )
import EveOnline.MemoryReading
import EveOnline.ParseUserInterface
    exposing
        ( OverviewWindowEntry
        , ShipUI
        , ShipUIModuleButton
        )
import EveOnline.UnstuckBot
import Json.Decode
import List.Extra
import Result.Extra
import Set


defaultBotSettings : BotSettings
defaultBotSettings =
    { acceptFleetInviteFrom = []
    , followFleetBroadcastFrom = []
    , answerBackupCalls = PromptParser.Yes
    , assistFleetCommander = PromptParser.Yes
    , homeStation = Nothing
    , hideWhenNeutralInLocal = PromptParser.No
    , anomalyNames = []
    , avoidRats = []
    , prioritizeRats = []
    , activateModulesAlways = []
    , maxTargetCount = 3
    , botStepDelayMilliseconds = { minimum = 1300, maximum = 1500 }
    , anomalyWaitTimeSeconds = 15
    , orbitFleetCommander = PromptParser.Yes
    , orbitFleetCommanderRange = defaultOrbitFleetCommanderRange
    , orbitInCombat = PromptParser.Yes
    , orbitObjectNames = []
    , runAwayShieldHitpointsThresholdPercent = -1
    , runAwayArmorHitpointsThresholdPercent = -1
    , runAwayIncomingDamageThreshold = -1
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
         , ( "accept-fleet-invite-from"
           , { alternativeNames = []
             , description = "Name of a pilot whose fleet invitations this bot should accept, exactly as the client writes it. Repeatable. Accepting hands the fleet this ship."
             , valueParser =
                PromptParser.valueTypeString
                    (\pilotNames settings ->
                        { settings
                            | acceptFleetInviteFrom =
                                settings.acceptFleetInviteFrom ++ splitSettingIntoNames pilotNames
                        }
                    )
             }
           )
         , ( "follow-fleet-broadcast-from"
           , { alternativeNames = []
             , description = "Name of a pilot whose travel broadcasts this bot should follow. Repeatable, matched exactly. Does not gate target broadcasts, which carry no sender."
             , valueParser =
                PromptParser.valueTypeString
                    (\pilotNames settings ->
                        { settings
                            | followFleetBroadcastFrom =
                                settings.followFleetBroadcastFrom ++ splitSettingIntoNames pilotNames
                        }
                    )
             }
           )
         , ( "answer-backup-calls"
           , { alternativeNames = [ "answer-backup-call", "answer-need-backup" ]
             , description = "Whether to break off and close on a fleet-mate who broadcasts 'needs backup'. Defaults to 'yes'. The caller has to be someone this reading recognises as a fleet pilot -- the fleet window's member rows, its header's commander, or a local-chat standing icon -- rather than someone named in 'follow-fleet-broadcast-from'."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\answerBackupCalls settings ->
                        { settings | answerBackupCalls = answerBackupCalls }
                    )
             }
           )
         , ( "run-away-shield-hitpoints-threshold-percent"
           , { alternativeNames = []
             , description = "Percentage of shield hitpoints below which the bot breaks off and warps back to the fleet commander. Read through the believed gauge and a low-water mark, never the live reading. Defaults to -1, which is off: no run of this bot has recorded what this hull's shield actually does under fire, and a threshold nobody measured is a guess about the one gauge this repo trusts least."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\threshold settings ->
                        { settings | runAwayShieldHitpointsThresholdPercent = threshold }
                    )
             }
           )
         , ( "run-away-armor-hitpoints-threshold-percent"
           , { alternativeNames = []
             , description = "Percentage of armor hitpoints below which the bot breaks off and warps back to the fleet commander. Read through the believed gauge and a low-water mark, never the live reading. Defaults to -1, which is off, for the same reason as the shield setting above."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\threshold settings ->
                        { settings | runAwayArmorHitpointsThresholdPercent = threshold }
                    )
             }
           )
         , ( "run-away-incoming-damage-threshold"
           , { alternativeNames = []
             , description = "Hitpoints of incoming damage, summed from the client's own combat log over a rolling 45-second window, past which the bot breaks off and warps back to the fleet commander. Needs no HUD gauge, which is the point of it. Defaults to -1, which is off: this is a number about a hull, and nothing has measured this one."
             , valueParser =
                PromptParser.valueTypeInteger
                    (\threshold settings ->
                        { settings | runAwayIncomingDamageThreshold = threshold }
                    )
             }
           )
         , ( "assist-fleet-commander"
           , { alternativeNames = []
             , description = "Set to 'no' to keep drones on this ship's own locked target instead of assisting the commander."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\assist settings -> { settings | assistFleetCommander = assist })
             }
           )
         , ( "home-station"
           , { alternativeNames = []
             , description = "Full name of the station to return to when the session is ending, exactly as the client renders it."
             , valueParser =
                PromptParser.valueTypeString
                    (\stationName settings -> { settings | homeStation = Just stationName })
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
         , ( "orbit-fc"
           , { alternativeNames = [ "orbit-FC", "orbit-fleet-commander", "approach-fc", "approach-FC" ]
             , description = "Whether to keep the ship on station beside the fleet commander, by approaching their overview row. Defaults to 'yes', and supersedes 'orbit-in-combat'. The distance is the client's own default Approach distance."
             , valueParser =
                PromptParser.valueTypeYesOrNo
                    (\orbitFleetCommander settings ->
                        { settings | orbitFleetCommander = orbitFleetCommander }
                    )
             }
           )
         , ( "orbit-fc-range"
           , { alternativeNames = [ "orbit-FC-range" ]
             , description = "ACCEPTED AND IGNORED. It named a rung of the client's Orbit submenu, which this bot no longer drives; keeping station is now an approach at the client's own distance. Still parsed so a settings string carrying it does not end the session, and named as ignored in the status line."
             , valueParser =
                PromptParser.valueTypeString
                    (\orbitRange settings ->
                        { settings | orbitFleetCommanderRange = String.trim orbitRange }
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
    { acceptFleetInviteFrom : List String
    , followFleetBroadcastFrom : List String
    , answerBackupCalls : PromptParser.YesOrNo
    , assistFleetCommander : PromptParser.YesOrNo
    , homeStation : Maybe String
    , hideWhenNeutralInLocal : PromptParser.YesOrNo
    , anomalyNames : List String
    , avoidRats : List String
    , prioritizeRats : List String
    , activateModulesAlways : List String
    , maxTargetCount : Int
    , anomalyWaitTimeSeconds : Int
    , botStepDelayMilliseconds : IntervalInt
    , orbitFleetCommander : PromptParser.YesOrNo
    , orbitFleetCommanderRange : String
    , orbitInCombat : PromptParser.YesOrNo
    , orbitObjectNames : List String
    , runAwayShieldHitpointsThresholdPercent : Int
    , runAwayArmorHitpointsThresholdPercent : Int
    , runAwayIncomingDamageThreshold : Int
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

    -- The banner as the *previous* reading saw it, ported from
    -- `eve-online-saxrat`'s field of the same name. `actOnFleetBroadcast` is
    -- handed the memory this update produces, so latching `fleetBroadcastFollowed`
    -- on the reading the banner first appears would stop the branch that reads
    -- it from ever firing on it -- latching on the *second* sighting instead
    -- makes the ask go out exactly once, since the banner persists and the
    -- second sighting always arrives. See `fleetTravelBroadcastAnyPilot`'s own
    -- comment for why this is unfiltered by `follow-fleet-broadcast-from`.
    , fleetBroadcastSeen : Maybe String

    -- The fleet travel broadcast this session has already asked the host to
    -- route to, as the banner's own text. The client's banner does not go
    -- away, so without this the ask would repeat on every reading for the
    -- rest of the session.
    , fleetBroadcastFollowed : Maybe String

    -- The `Target` form's own answer to the same persistence, and #395 is what
    -- its absence cost: the banner goes on naming a called target after the
    -- thing dies, so `bringCalledTargetUnderFire` answered "lock it" forever
    -- at a name no overview row carried, and every arm below it -- the drones,
    -- the guns, the gate, the approach -- was unreachable for the rest of the
    -- session. Which called name, and how many consecutive readings it has
    -- named no row. `Nothing` on any reading that is not that state, so a row
    -- coming back, a different call and the banner going away all clear it.
    -- See `calledTargetGoneAfterReading`.
    , calledTargetGone : Maybe CalledTargetGone

    -- The same two-reading latch as `fleetBroadcastSeen`/`fleetBroadcastFollowed`,
    -- for the place (system or gate) an `AtLocation`/`InPositionAt` broadcast
    -- names -- see `fleetMatePlaceAnyPilot`'s own comment for why this is
    -- unfiltered by `follow-fleet-broadcast-from`, same as that pair. Without
    -- `goToFleetMateDestinationAsked`, `goToFleetMate` asked the host once for
    -- the route and then waited forever for a pilot who was never coming back
    -- to this grid -- it had no second half telling it the ask had already
    -- gone out and it was time to fly the route instead.
    , goToFleetMatePlaceSeen : Maybe String
    , goToFleetMateDestinationAsked : Maybe String

    -- Readings in a row spent asking the client to warp this ship to a
    -- fleet-mate who already has a row on this overview, bounded for #373's
    -- reason: the cascade this used to drive could never resolve, and an arm
    -- this high in the tree with no bound owns the whole bot (#321). Advances
    -- while a mate this ship is flying to is on the grid, holds once the
    -- budget is spent, and resets the moment there is no such mate. See
    -- `fleetMateWarpStep`.
    , goToFleetMateWarpAskedReadings : Int

    -- Ported from `eve-online-warp-to-0-autopilot`'s fields of the same name
    -- -- see `navigateTowardFleetCommander` for what they drive. Not renamed,
    -- so a reader who knows that bot recognises them immediately. That bot's
    -- third rung (a `jumpCascadeStuckReadings` count falling back to the
    -- surroundings-button cascade past 30 stuck readings) is deliberately not
    -- ported -- see `navigateTowardFleetCommander`'s own comment for why.
    , routeFirstMarkerRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
    , routeFirstMarkerUnchangedTicks : Int

    -- Readings in a row spent asking one acceleration gate to open, ported
    -- from `eve-online-saxrat`'s `gateWithinReachTicks` -- see
    -- `accelerationGateStep` for why a bound matters here at all. Advances
    -- while actually asking, holds while a gate is on the overview but this
    -- bot is not asking it (rats present, most often), and resets only once
    -- no gate is on the overview at all.
    , gateAskedReadings : Int

    -- Readings in a row spent ctrl-clicking the fleet broadcast banner to lock
    -- the called target, carried with the name being clicked at. #366. Advances
    -- only on readings the click is actually asked on, holds while the same
    -- call is the lock's question and this reading did not ask, and clears the
    -- moment the lock is no longer the question -- the target coming up locked,
    -- the commander calling something else, the call turning out to be a gate
    -- or a fleetmate, or #395 giving up on it. Past
    -- `bannerCtrlClickAskedReadingsBound` the overview cascade has the lock
    -- instead; see `bannerCtrlClickAfterReading`.
    , bannerCtrlClick : Maybe BannerCtrlClickAsk

    -- Readings in a row spent asking the drones home before taking a gate the
    -- commander broadcast a `Target` on, ported from `eve-online-saxrat`'s
    -- `droneRecallUnansweredTicks` -- see `calledGateDroneRecall`. Counts from
    -- the first recall the client did not answer, resets whenever the in-space
    -- count falls (a partial recall is the client answering), and holds once
    -- the give-up is reached, because giving up is what stops the asking.
    , calledGateRecallAskedReadings : Int

    -- How many drones were in space on the previous reading, which is the only
    -- thing that can say the count *fell*. `dronesInSpaceCountFromReading`
    -- answers 0 for a reading with no drones window, so a docked reading resets
    -- the counter above rather than being read as a recall that landed.
    , dronesInSpaceCountLastReading : Int

    -- What the two HUD hitpoint gauges are willing to be believed about, and
    -- how low each has been since the ship was last healthy. See
    -- `updateHitpointsGaugeMemory` and `lowWaterMarkAfterReading` -- and CLAUDE.md's
    -- "Retreating: the HUD hitpoint gauge is the weakest instrument here" for
    -- why nothing reads the live percentage.
    , hitpoints : HitpointsMemory
    , lowestShieldPercentSinceHealthy : Int
    , lowestArmorPercentSinceHealthy : Int

    -- The rolling window of what the client's own combat log says has landed
    -- on this ship, and the latched verdict taken off it. A reading's
    -- `incomingDamageSinceLastReading` is gone by the next one, so the window
    -- has to be accumulated here.
    , incomingDamage : IncomingDamageMemory

    -- Readings in a row on which the retreat was decided and the ship was not
    -- in warp -- the mission runner's `retreatProgressAfterReading` in one
    -- field. Bounded because this bot's run-to can dispatch nothing at all;
    -- see `retreatAskedReadingsBound`.
    , retreatAskedReadings : Int

    -- Whether this ship still needs to fly back to the fleet after a retreat.
    -- Set the moment a retreat is decided and held through the retreat itself,
    -- so it survives the moment health recovers and the retreat's own verdict
    -- clears -- without it, "no longer retreating" and "back with the fleet"
    -- would be the same reading, which they are not: `warpAwayFromDanger` puts
    -- the ship wherever the nearest AU-range object was, not anywhere near the
    -- commander. Cleared only once the commander has an overview row again,
    -- the same test `commanderIsOnGridToOrbit` already makes. See
    -- `recoverFromRetreat`.
    , recoveringFromRetreat : Bool

    -- Where a fleet-mate last said they were, and who said it: the place a
    -- `Travel to`/`is at location`/`is in position at` broadcast named, carried
    -- across the retreat so `recoverFromRetreat` has somewhere to fly to.
    -- #381 is what its absence cost -- the retreat is what puts the commander
    -- off grid, so the one arm reached after every successful retreat was the
    -- one arm that could never do anything, and three of four live wingmen sat
    -- in it healthy while the fleet fought.
    --
    -- **Unfiltered by `follow-fleet-broadcast-from`, and the pilot travels with
    -- the place**, which is what lets the decision ask the question rather than
    -- the memory. `fleetCommanderNameFromReading`'s primary source is the fleet
    -- window's own header, which comes and goes; a place filtered in at a moment
    -- the header was readable and refused at a moment it was not would be a
    -- memory whose contents depend on a transient. Storing the sender means one
    -- reading's answer decides both halves, and the status line can say whose
    -- place this is when the answer is "not the commander's".
    --
    -- **What clears it**: a newer place broadcast replaces it, from any pilot;
    -- and the reunion drops it, on the same reading `recoveringFromRetreat`
    -- clears, because "he is right here" supersedes wherever he last said he
    -- was. So a place this arm routes to was always broadcast since the last
    -- time this ship was with its commander. There is no age bound, because
    -- there is no wingman corpus to place one against (WINGMAN.md) and the
    -- arm's own give-up is what stops a stale place costing a session. See
    -- `fleetPlaceBroadcastAfterReading`.
    , fleetPlaceBroadcast : Maybe { pilot : String, place : String }

    -- Readings in a row spent by `recoverFromRetreat` asking the client to get
    -- this ship back to its commander, bounded for #321's reason: an arm this
    -- high in the tree that answers `Just` forever owns the whole bot.
    -- Advances only on the answers that dispatch, resets on a reading the ship
    -- is warping or jumping (the ask worked -- the ship is moving, which is
    -- `retreatAskedReadings`' own rule), holds once spent, and resets to zero
    -- when the recovery ends. See `retreatRecoveryStep`.
    , retreatRecoveryAskedReadings : Int

    -- Readings in a row spent clicking a weapon that will not come active on
    -- the locked target, bounded for the reason #326 measured: a turret that
    -- could not activate held that bot's decision for 262 consecutive
    -- readings. Advances only while actually clicking, and resets the moment
    -- nothing is locked -- so a fight that ends clears it and the next called
    -- target gets the full allowance again.
    , weaponsAskedReadings : Int

    -- Readings in a row spent asking this ship to approach the fleet
    -- commander's overview row without the client ever naming the manoeuvre
    -- `Approach`, bounded for the same reason as the two counters above -- see
    -- `approachFleetCommanderAskedReadingsBound`. Advances only while the ask
    -- is actually going out, holds once the budget is spent and the commander
    -- is still on the grid, and resets the moment the ship reads as
    -- approaching or the commander leaves the overview.
    , approachFleetCommanderAskedReadings : Int

    -- Readings in a row the Selected Item panel has not come to show the object
    -- `ensureShipIsOrbiting` wants to orbit, which is what bounds that arm's
    -- selection click. See `panelSelectReadingsAfterReading` and
    -- `panelManoeuvreStep`.
    , panelSelectUnansweredReadings : Int

    -- Whether this ship has landed on a grid and has not since been seen
    -- closing on the fleet commander. #397. Opened on the reading a warp ends
    -- (`warpJustEnded`) and closed by the client naming the manoeuvre
    -- `Approach` -- by nothing else, so it is not a clock. While it is open,
    -- closing on the commander outranks the fighting arms; see
    -- `closeOnTheCommanderAfterLanding` for the whole argument, including what
    -- bounds an open window that nothing ever closes.
    --
    -- `False` at the start of a session, so a bot that begins already on grid
    -- has no landing to close from -- `arrivalWindowIsOpen`'s posture, and the
    -- conservative direction.
    , closingOnTheCommanderSinceLanding : Bool

    -- Readings in a row spent trying to reach a fleet-mate who broadcast
    -- `needs backup`, bounded like the counters above -- see
    -- `backupCallAskedReadingsBound`. Advances only on the answers that
    -- actually spend a reading (`backupCallAnswersThatSpendAReading`), holds
    -- once the budget is spent while the call is still up, and resets the
    -- moment the banner stops naming a backup call this ship may answer.
    , backupCallAskedReadings : Int

    -- Readings in a row spent right-clicking a locked fleet pilot's target-bar
    -- entry to unlock it, bounded like the three counters above -- see
    -- `unlockFleetPilotAskedReadingsBound`. The bound stops the *asking* only:
    -- `friendlyFireStep` keeps vetoing the guns for as long as that pilot is
    -- locked, spent budget or not.
    , unlockFleetPilotAskedReadings : Int

    -- Readings in a row spent clicking a middle-row module the client never
    -- shows the change on, bounded like the counters above -- see
    -- `middleRowAskedReadingsBound`. Advances only on the answers that
    -- actually click (`middleRowAnswersThatSpendAReading`), holds once the
    -- budget is spent, and resets on every reading the row wants nothing --
    -- which is what lets a ship that starts approaching again get the whole
    -- allowance back.
    , middleRowAskedReadings : Int

    -- The message box `closeMessageBox` is trying to answer and how many
    -- readings it has been at it, ported from `eve-online-saxrat` (#138, which
    -- is the mission runner's #101). `generalSetupInUserInterface` is evaluated
    -- above everything, so a dialog the answer does not close owns every
    -- reading for the rest of the session -- see `MessageBoxStandoff`.
    , messageBoxStandoff : Maybe MessageBoxStandoff

    -- What `describeMessageBoxGivenUpOn` says, on the one reading the standoff
    -- crosses its bound and on no other. Folded in at the root, because the
    -- branch that would otherwise say so is precisely the branch that has just
    -- stopped running.
    , messageBoxLastChange : Maybe String
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


{-| One gauge, and what two readings of it agree on.

`previousReading` is the last believable percentage this gauge produced, or
`Nothing` for a reading the gauge was unreadable or implausible on. `believed`
is the healthier of the last two -- the value every guard reads.

-}
type alias HitpointsGaugeMemory =
    { previousReading : Maybe Int
    , believed : Maybe Int
    }


{-| The rolling damage window, ported from `eve-online-saxrat`.

`hostCarriesTheChannel` is what makes this guard's silence safe to read: an
empty window reads identically whether the grid is quiet or the host has no
game log at all, and only one of those means the ship is fine.

-}
type alias IncomingDamageMemory =
    { samples : List { atMilliseconds : Int, damage : Int }
    , hostCarriesTheChannel : Bool
    , retreating : Bool
    }


{-| A called target the banner still names and no overview row does, and for how
long.

**The name travels with the count, which is the half `fleetBroadcastFollowed`
contributes to #395's fix.** A bare counter would carry one call's readings into
the next one, so a second target called while the first was still missing would
be given up on with none of its own readings spent -- the "a counter and the
thing it bounds are measuring different quantities" shape #145's own gate counter
was filed on. `calledTargetHasBeenGivenUpOn` therefore takes the name being asked
about as well as this record and refuses to answer for any other.

-}
type alias CalledTargetGone =
    { calledTarget : String
    , readings : Int
    }


{-| How many readings in a row the ctrl-click on the broadcast banner has been
asked to lock this call, carried with the name it is counting for.

`CalledTargetGone`'s shape and for its reason: a bare counter would hand one
call's arrears to the next, so a second target called while the first was still
being clicked at would go straight to the cascade with none of its own readings
spent. See `bannerCtrlClickAfterReading`.

-}
type alias BannerCtrlClickAsk =
    { calledTarget : String
    , readings : Int
    }


{-| The message box the bot has been trying to answer, and how many readings it
has been at it.

**Issue #402, which is the mission runner's #101 and saxrat's #138 in this
file.** `closeMessageBox` here had no counter, no bound and no give-up: it
clicked its dismissal on the first reading and would have clicked it identically
on the thirty-thousandth, and anything it could not recognise reached
`askForHelpToGetUnstuck` -- which dispatches nothing. `generalSetupInUserInterface`
is evaluated above the docked-or-in-space split, so either way an unrecognised
dialog owned every reading for the rest of the session. Observed live on
2026-08-28: a wingman with a 400-line scrollback holding nothing but
`I see a message box to close` / `I see no way to close this message box` /
`I am stuck here and need help to continue`.

**`identity` is what makes the count mean something.** A global tally of
dismissals accumulates across a session that legitimately closes many dialogs
and reaches a give-up it should never reach; the mission runner's recovered runs
answer 175 separate stretches of message box between them. Counted per box,
those stretches are 6 to 44 readings long and nothing else, against run 30's
32,585 on one box.

**What the identity is made of, and what it deliberately leaves out.** The box's
own display texts and its buttons, and _not_ its display region.
`routeFirstMarkerUnchangedTicks` is a region comparison and records what that
costs: a widget re-rendered every tick can differ sub-pixel while looking
identical, and an exact-equality test over its region then never accumulates at
all -- which is precisely the failure this bound exists to prevent. What a
dialog says and what buttons it offers are read out of the tree as strings and
do not drift that way. The side effect is that a dialog whose wording changes
starts a fresh count, which is the wanted direction: a box saying something new
is one the next answer has not been tried on.

**`readings` counts readings the framework completed.** It is advanced in
`updateMemoryForNewReadingFromGame`, which runs once per
`ReadingFromGameClientCompleted` and not once per log line or per framework
step. saxrat's run 11 is why that is worth writing down: the count reached 60,
the client stopped answering reads on that same reading, and every counter
written there froze together while the host went on reprinting the last status
text 2,439 times. A count that has stopped moving is therefore evidence about
the reading pipeline and not about this branch.

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
    -- Anything the memory update concluded on its own announces itself here, at
    -- the root, rather than in a branch -- it is settled in
    -- `updateMemoryForNewReadingFromGame`, which runs on every reading whatever
    -- the bot is doing, so the branch that learned it is not reliably the branch
    -- being evaluated. The field holds a message only on the reading its
    -- conclusion changed, so this is one line per change with no separate
    -- "already reported" flag to get wrong.
    ([ context.memory.messageBoxLastChange ]
        |> List.filterMap identity
        |> List.foldr describeBranch (anomalyBotDecisionRootBeforeApplyingSettings context)
    )
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


{-| The things that have to be dealt with before any decision can be made about
the game itself.

**This whole list is evaluated above the docked-or-in-space split**, so anything
in it that can repeat forever freezes the entire bot rather than one branch.
That is #101 in the mission runner, #138 in saxrat and #402 here.
`closeMessageBox` carries a bound of its own and may not lose it: it gives up on
a box nothing closes and hands the reading back.

**`closeSystemSettingsMenu` is first, and that placement is what makes
`closeMessageBox`'s Escape rung safe.** A naked Escape can open the client's own
Settings/pause menu, and that branch is the only thing in this bot that closes
it. This list answers with its head after a `filterMap`, so a pause menu opened
on one reading is closed on the next, and closed before anything else is
attempted. Reordering these two uncovers the risk.

-}
generalSetupInUserInterface : BotDecisionContext -> Maybe DecisionPathNode
generalSetupInUserInterface context =
    [ closeSystemSettingsMenu
    , acceptFleetInviteFromNamedPilot context
    , closeMessageBox context.memory.messageBoxStandoff
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


{-| `accept-fleet-invite-from` was parsed into settings and never read by any
decision -- the same shape as `avoid-rat` before it was removed from the
mission runner. The client's own confirmation ("Join Fleet?", `yes_dialog_button`
/ `no_dialog_button`) falls through `closeMessageBox`'s Close/OK-only matcher
and lands on `askForHelpToGetUnstuck`, so an invite the setting names sits
unanswered forever. This is the one exception `closeMessageBoxByDeclining`'s own
family allows: verified live, the box's own text reads

    <a href="showinfo:1385//2120724228">Gal Bistot</a> wants you to join their fleet, do you accept?...

and its two buttons read "Yes" and "No". Only a sender named in
`accept-fleet-invite-from` is answered; anything else falls through to
`closeMessageBox` unchanged, so the trust stays exactly where the setting's own
documentation says it is.

-}
acceptFleetInviteFromNamedPilot : BotDecisionContext -> ReadingFromGameClient -> Maybe DecisionPathNode
acceptFleetInviteFromNamedPilot context readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.filterMap
            (\messageBox ->
                fleetInviteSenderFromMessageBox messageBox
                    |> Maybe.map (\sender -> ( messageBox, sender ))
            )
        |> List.head
        |> Maybe.andThen
            (\( messageBox, sender ) ->
                if List.member sender context.eventContext.botSettings.acceptFleetInviteFrom then
                    messageBox.buttons
                        |> List.filter (\button -> button.mainText == Just "Yes")
                        |> List.head
                        |> Maybe.map
                            (\yesButton ->
                                describeBranch
                                    ("Accept the fleet invitation from '"
                                        ++ sender
                                        ++ "', named in accept-fleet-invite-from."
                                    )
                                    (case mouseClickOnUIElement MouseButtonLeft yesButton.uiNode of
                                        Err _ ->
                                            describeBranch "Failed to click" askForHelpToGetUnstuck

                                        Ok clickAction ->
                                            decideActionForCurrentStep clickAction
                                    )
                            )

                else
                    Nothing
            )


fleetInviteMarker : String
fleetInviteMarker =
    " wants you to join their fleet"


fleetInviteSenderFromMessageBox :
    { uiNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , buttonGroup : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , buttons : List { uiNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion, mainText : Maybe String }
    }
    -> Maybe String
fleetInviteSenderFromMessageBox messageBox =
    messageBox.uiNode.uiNode
        |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
        |> List.filterMap fleetInviteSenderFromText
        |> List.head


fleetInviteSenderFromText : String -> Maybe String
fleetInviteSenderFromText text =
    case String.split fleetInviteMarker text of
        before :: _ :: _ ->
            before
                |> stripHtmlTags
                |> String.trim
                |> (\name ->
                        if String.isEmpty name then
                            Nothing

                        else
                            Just name
                   )

        _ ->
            Nothing


{-| The sender's name arrives wrapped in an `<a href="showinfo:...">`/`</a>`
pair, and a naive split on the last `>` takes the trailing empty string after
the closing tag's own `>` -- caught live, the first version of this function
answered `Nothing` for every reading of a real invite. This strips every
`<...>` span rather than assuming one specific tag shape, the way
`route_setter.py` strips tags out of a chat MOTD elsewhere in this repo, so a
sender rendered with no tag at all still comes through unchanged.
-}
stripHtmlTags : String -> String
stripHtmlTags text =
    text
        |> String.foldl
            (\char state ->
                if char == '<' then
                    { state | inTag = True }

                else if char == '>' then
                    { state | inTag = False }

                else if state.inTag then
                    state

                else
                    { state | kept = state.kept ++ String.fromChar char }
            )
            { inTag = False, kept = "" }
        |> .kept


{-| Recovers from the game's own Settings/pause menu covering the whole screen.

Ported from `eve-online-saxrat`, where it exists because that happened live: a
bare Escape press meant for a context menu landed with no menu open, and EVE
reads a "naked" Escape as "open the pause menu". Once open it blocks everything
else this bot's decision tree looks for -- the ship UI, the overview, the fleet
window -- so nothing else in the tree would ever recognise the state well enough
to close it, and the recorded recovery was a person closing it by hand.

**This bot pressed Escape in two places and had no branch that could close that
menu.** `clearStrayContextMenu`'s fallback presses it and its own comment
already said `closeSystemSettingsMenu` "exists because that happened live" --
naming a declaration that was nowhere in this file. #402 adds the Escape rung to
`closeMessageBox`, which is a third place, so the branch is a prerequisite for
that rather than a tidy-up: an Escape rung without it trades a bounded
message-box standoff for an unbounded pause menu.

Targets the close ('X') icon in the menu's own header rather than any of the
page-specific buttons in its footer: the header and its close button are common
to every page this menu can show, while the footer's buttons are specific to
whichever page happens to be open. Its `_elementId` is the stable,
page-independent `"closeMenuClick"`, found by walking down from the
`l_systemmenu`-named layer.

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


{-| The ladder over one message box: answer it, then press Escape at it, then
leave it alone and let the rest of the bot run.

`standoff` is passed down rather than read here because it is not a fact about
this reading: it is how many readings the box in front of the bot has already
survived, and only `BotMemory` can say.

-}
closeMessageBox : Maybe MessageBoxStandoff -> ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox standoff readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.andThen
            (\messageBox ->
                case messageBoxStandoffVerdictForBox standoff messageBox of
                    LeaveTheMessageBoxAlone ->
                        -- The whole of #402: `Nothing` here is what lets the
                        -- rest of the tree run. The box is still on the screen
                        -- and every branch below is now working around it,
                        -- which is worse than a closed box and incomparably
                        -- better than nothing running at all. The give-up said
                        -- so once at the root on the reading it was reached,
                        -- and the status line keeps saying so.
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


{-| The ordinary answer, which is always a declining one.

**No affirmative appears anywhere in this path**, which is #54's standing rule in
the mission runner: these dialogs guard destructive actions, so a bot answering
one without having read it must answer the way that declines. The fleet
invitation is the one exception this bot makes and it is a separate branch
_above_ `closeMessageBox` in `generalSetupInUserInterface`, gated on the sender
being named in `accept-fleet-invite-from` -- so it is a decision an operator
wrote down rather than one this function takes.

**`no` is the addition #402 makes**, on the operator's own field note: the boxes
this bot meets want `Close` (informational popups), `No` (dangerous actions) or
`Ok` (cannot warp to a fleet member who is not in system). Two of the three were
already matched; `No` is the declining answer by definition, so adding it is
consistent with the rule above rather than a departure from it.

**The window's own close ('X') control is deliberately _not_ a rung**, though
both sibling bots have it as their last one. saxrat run 22 lost its client to
exactly that: EVE's `Connection Lost` modal carries a single `Quit`, no
`Close`/`OK` and no `no_dialog_button`, so both recognising options missed, the
close control was clicked, and the log stops with no client process left. The
operator's own note on #402 says the box seen here was a "client disconnected"
box, so that is the shape this bot is known to meet. Declining to click anything
on an unrecognised dialog costs the readings the ladder bounds; clicking an
unread control costs the session.

-}
closeMessageBoxByDeclining : EveOnline.ParseUserInterface.MessageBox -> DecisionPathNode
closeMessageBoxByDeclining messageBox =
    describeBranch "I see a message box to close."
        (let
            labelledOneOf labels button =
                case button.mainText of
                    Nothing ->
                        False

                    Just buttonText ->
                        List.member (buttonText |> String.trim |> String.toLower) labels

            firstButtonWhere isWanted =
                messageBox.buttons |> List.filter isWanted |> List.head

            namedButton name =
                firstButtonWhere
                    (.uiNode
                        >> .uiNode
                        >> EveOnline.ParseUserInterface.getNameFromDictEntries
                        >> (==) (Just name)
                    )

            {- Dismissal options in descending order of confidence, and never a
               positive answer:

               1. A plain "Close"/"OK" acknowledgement.
               2. "No" on a confirmation dialog, by the `_name` the client gives
                  it -- `no_dialog_button` is stable across client languages,
                  and such a dialog has no Close/OK button at all.
               3. "No" by its rendered label, for a declining button the client
                  did not name.
            -}
            dismissOptions =
                [ firstButtonWhere (labelledOneOf [ "close", "ok" ])
                , namedButton "no_dialog_button"
                , firstButtonWhere (labelledOneOf [ "no" ])
                ]
         in
         case dismissOptions |> List.filterMap identity |> List.head of
            Nothing ->
                describeBranch
                    ("I see no way to close this message box: "
                        ++ messageBoxIdentityForOperator (messageBoxIdentity messageBox)
                        ++ "."
                    )
                    askForHelpToGetUnstuck

            Just buttonToUse ->
                describeBranch
                    ("Click on button '" ++ (buttonToUse.mainText |> Maybe.withDefault "") ++ "'.")
                    (case mouseClickOnUIElement MouseButtonLeft buttonToUse.uiNode of
                        Err _ ->
                            describeBranch "Failed to click" askForHelpToGetUnstuck

                        Ok clickAction ->
                            decideActionForCurrentStep clickAction
                    )
        )


{-| What to do about the box in front of the bot, given how long it has been
there.

**The declining answer stays the default and that is not negotiable** -- #54's
standing lesson, and the reason the ladder starts where this branch always did
rather than at something cleverer. What #402 adds is only what happens once the
answer has demonstrably not worked.

-}
type MessageBoxStandoffVerdict
    = AnswerTheMessageBox
    | PressEscapeAtTheMessageBox
    | LeaveTheMessageBoxAlone


{-| How many readings the ordinary answer gets before the escalation.

**60, and it rests on the mission runner's corpus rather than on this bot's.**
No wingman run has been recorded on the machine this was written on, so there is
nothing here to measure a threshold against and inventing a wingman-specific
number would be inventing it. What the mission runner measured transfers because
the thing being measured is the client's, not the bot's: the same widget, parsed
by the same `parseMessageBoxesFromUITreeRoot` matching on `pythonObjectTypeName`
alone. Counting consecutive readings with a box on the screen, that bot's
recovered runs give stretches of 6, 10, 11, 18, 20 and 44 readings and nothing
else, while its run 30's one box ran to 32,585. **Nothing recorded lies between
44 and the incident**, so 60 is placed in a gap rather than cut through a
distribution.

-}
messageBoxAnswersBeforeEscape : Int
messageBoxAnswersBeforeEscape =
    60


{-| How many readings the whole standoff gets before the bot stops answering.

Twice `messageBoxAnswersBeforeEscape`, so Escape gets exactly as long to work as
the answer it replaced -- written as a multiple so the argument cannot drift away
from the number.

-}
messageBoxStandoffGiveUpReadings : Int
messageBoxStandoffGiveUpReadings =
    messageBoxAnswersBeforeEscape * 2


{-| The ladder, over the standoff `updateMemoryForNewReadingFromGame` recorded.

**Escape is what this codebase already escalates with**, and it needs no focus:
`clearStrayContextMenu` presses it at a menu that has not advanced in three
ticks. A message box that has not closed in sixty readings is the same shape.

**Ctrl+W is deliberately not in the ladder**, though it is the client's own
"close the active window". It acts on the _focused_ window, and the loot window
paid for that lesson twice in saxrat -- 650 presses at an unfocused window in one
run and 919 decision lines in another, closing nothing either time. Clicking an
unidentified modal to focus it is a click into a dialog nobody has read, which is
the one thing `closeMessageBoxByDeclining` refuses to do.

**A naked Escape can open the client's own pause menu**, which is covered rather
than risked: `closeSystemSettingsMenu` is the entry _before_ this one in
`generalSetupInUserInterface`, and that list answers with its head, so a pause
menu opened on one reading is closed on the next by the branch that exists for
it.

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


{-| The standoff's verdict, except that one box is never answered at all.

`closeMessageBoxByDeclining`'s promise is that the automatic reply is always the
declining one, because these dialogs guard destructive actions. EVE's Connection
Lost modal inverts that: every control on it quits the client, and Escape at a
modal whose only action is Quit is the same keypress by another route. saxrat run
22 lost its client to that box six minutes into an eight-hour tour, and the
operator's note on #402 says the box this bot met was a "client disconnected"
one.

**It is not a bound and it does not wait**, because there is nothing to wait for:
a client with no server connection cannot be recovered by anything the bot can
press, and quitting takes it away from the operator who _can_ reconnect. So the
answer is the one the ladder already builds for a box that will not close --
`LeaveTheMessageBoxAlone`, so `closeMessageBox` answers `Nothing` and the rest of
the tree runs -- reached immediately rather than after 120 readings of pressing
things at it. `botlab_host.py` recognises the same box by the same two substrings
and clicks the Quit itself, which is where that decision belongs.

The cost is the one that verdict already carries: `Nothing` cannot hold a
decision line, so the decision log says nothing about this box. What does say so
is the status clause, which counts every reading a box is up and names it.

-}
messageBoxStandoffVerdictForBox :
    Maybe MessageBoxStandoff
    -> EveOnline.ParseUserInterface.MessageBox
    -> MessageBoxStandoffVerdict
messageBoxStandoffVerdictForBox standoff messageBox =
    if messageBoxSaysTheConnectionIsLost messageBox then
        LeaveTheMessageBoxAlone

    else
        messageBoxStandoffVerdict standoff


{-| Whether the box is the client saying it has lost the server.

Matched on the client's own words, and on two of them rather than one:
`Connection Lost` is the title and `connection to server was lost` the body, and
both were read off the box that took saxrat's client down. Two substrings for
#31's reason -- a single common word would reach dialogs this must not silence,
and silencing a dialog is exactly how a bot stops answering something it should.

The button is deliberately not what this reads. `Quit` is a plausible label on
boxes that have a safe answer beside it.

-}
messageBoxSaysTheConnectionIsLost : EveOnline.ParseUserInterface.MessageBox -> Bool
messageBoxSaysTheConnectionIsLost messageBox =
    let
        texts =
            messageBox.uiNode.uiNode
                |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                |> List.map String.toLower

        says needle =
            texts |> List.any (String.contains needle)
    in
    says "connection lost" && says "connection to server was lost"


{-| What a message box is, for the purpose of counting how long this one has
been in the way.

Its own display texts and its buttons, joined into one string -- see
`MessageBoxStandoff` for why the display region is deliberately not in it, and
why a box that changes its wording is treated as a new box.

The buttons carry their `_name` as well as their label, because the label is what
a person reads and the name is what this file acts on: `no_dialog_button` is the
one name relied on across client languages, and a dialog offering it is a
different dialog from one offering an unnamed OK even where both render the same
word. Reading both also means the identity is never empty for a box that has
buttons.

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


{-| How much of a box's identity a line prints.
-}
messageBoxGiveUpIdentityLength : Int
messageBoxGiveUpIdentityLength =
    200


{-| A box's identity, cut to what one line can carry.

One function for every reader rather than the cut written out three times, so the
give-up sentence, the status clause and the ask-for-help line cannot come to
disagree about how much of a dialog an operator is shown.

-}
messageBoxIdentityForOperator : String -> String
messageBoxIdentityForOperator identity =
    if messageBoxGiveUpIdentityLength < String.length identity then
        String.left messageBoxGiveUpIdentityLength identity ++ "..."

    else
        identity


{-| The one line the operator gets when the bot stops answering a box.

Said at the root on the reading the count crosses the bound and on no other,
because the verdict is reached in `updateMemoryForNewReadingFromGame`, which runs
whatever the bot is doing, and the branch that would otherwise say so is
precisely the branch that has just stopped running.

-}
describeMessageBoxGivenUpOn : String -> String
describeMessageBoxGivenUpOn identity =
    "Nothing closes this "
        ++ messageBoxIdentityForOperator identity
        ++ " -- answered it "
        ++ String.fromInt messageBoxAnswersBeforeEscape
        ++ " readings running and then pressed Escape at it for another "
        ++ String.fromInt (messageBoxStandoffGiveUpReadings - messageBoxAnswersBeforeEscape)
        ++ ", and it is still there. Leaving it open and getting on with the rest of the bot rather than answering it forever -- it needs closing by hand."


{-| The one clause on a reading that says a box is in front of the bot, and the
only thing that says which box.

Two things make it the only one. Once the give-up is reached `closeMessageBox`
answers `Nothing` and prints no decision line at all, so nothing else on the
reading mentions the box; and `describeMessageBoxGivenUpOn`, which does name it,
is written on the one reading the count crosses
`messageBoxStandoffGiveUpReadings` and on no other.

**#402's first defect is what this answers**, and saxrat run 11 is what it cost
there: one box held that bot for 60 readings and the run ended before the give-up,
so what the window was cannot be recovered from a 125 MB log. Naming the box on
every reading it is counted costs a clause on the readings a box is up and
nothing on any other.

-}
describeMessageBoxStandoff : Maybe MessageBoxStandoff -> String
describeMessageBoxStandoff standoff =
    case standoff of
        Nothing ->
            ""

        Just present ->
            "Message box: "
                ++ String.fromInt present.readings
                ++ "/"
                ++ String.fromInt messageBoxStandoffGiveUpReadings
                ++ (case messageBoxStandoffVerdict (Just present) of
                        AnswerTheMessageBox ->
                            " (answering it)"

                        PressEscapeAtTheMessageBox ->
                            " (pressing Escape at it)"

                        LeaveTheMessageBoxAlone ->
                            " (GIVEN UP ON, still open)"
                   )
                ++ ", "
                ++ messageBoxIdentityForOperator present.identity
                ++ "."


{-| The standoff as it stands after this reading.

No box in the reading ends it outright, which is what keeps the count about
_this_ box: a session that closes forty dialogs starts from zero at each one, and
only a box in front of the bot on every consecutive reading can accumulate
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
                (activateAlwaysOnModules context
                    |> Maybe.withDefault (fightPointedRatsOrReturnDrones context shipUI)
                )


{-| The next inactive module that `activate-module-always` names, if any --
`Just` a click if one is inactive, `Nothing` once every named module already
reads active.

Extracted out of what is now `decideNextActionWhenInSpaceNotHiding`'s own
inline check (that function is this app's inherited, unreachable copy of the
combat anomaly bot's root, kept for reference) so the wingman's own root can
reach the same behaviour instead of never checking it at all -- #349 found
that `wingmanDecisionRootInSpace` called straight into
`modulesToActivateAlwaysActivated` (now `fightPointedRatsOrReturnDrones`) and
never activated an always-on module in its own right.

-}
activateAlwaysOnModules : BotDecisionContext -> Maybe DecisionPathNode
activateAlwaysOnModules context =
    case
        context
            |> knownModulesToActivateAlways
            |> List.filter (Tuple.second >> moduleIsActiveOrReloading >> not)
            |> List.head
    of
        Nothing ->
            Nothing

        Just ( inactiveModuleMatchingText, inactiveModule ) ->
            Just
                (describeBranch ("I see inactive module '" ++ inactiveModuleMatchingText ++ "' to activate always. Activate it.")
                    (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)
                )


{-| The middle row: everything right of the leftmost slot held on, and the
leftmost slot -- the propulsion module -- run only while this ship is
approaching the fleet commander.

**By position, with no tooltip read**, which is `eve-online-saxrat`'s shape
ported whole: `shipUIModulesToActivateAlways` and `propulsionModuleButton` over
`middleRowLeftToRight`. #394 is why it exists. The settings block these bots
are actually launched with carries no `activate-module-always` line at all, so
`knownModulesToActivateAlways` is empty and `activateAlwaysOnModules` correctly
does nothing -- and the setting was the wrong instrument anyway, since it
matches tooltip text, needs `readShipUIModuleButtonTooltips` to have run first,
and has no way to say "everything except the propulsion module" or "this one
only while moving". The setting stays for anything genuinely tooltip-matched;
this is the path that does not depend on one being set.

**The always-on half is not gated on a fight, and that is a decision rather
than something inherited.** saxrat gates its own on `anyAttackableInOverview`,
because a rat-hunter spends most of a session crossing empty belts where a
hardener buys nothing for its capacitor. A wingman is the other case and the
gate is wrong for it three times over: it sits on the commander's grid rather
than crossing to the next one, so the empty stretches the gate saves capacitor
on are not what this bot's session is made of; it does not choose its fights,
the fleet does, so the first it learns of one can be the commander's broadcast
or a volley landing; and what is shooting it may never appear on its own
overview at all, since the preset this bot depends on is the one that shows
_fleet members_ (`approachTheFleetCommander`) and `shouldAttackOverviewEntry`
answers about rats this ship would attack rather than about anything attacking
it. A hardener switched on once damage is already landing is on for the
readings after the ones that mattered -- and those are exactly the readings
#364's retreat is measured over. So the row is held on and the capacitor is
spent.

**The propulsion module is the opposite half and is driven separately.** The
operator's rule is narrower than saxrat's `propulsionModuleShouldBeRunning`,
which reasons about crossing distance generally: on the instant after the ship
starts approaching the commander, off when it is not approaching. It reads
`shipIsApproachingFromReading` -- the client's own word, `ManeuverApproach` --
rather than whether `approachTheFleetCommander` decided to ask for an approach,
so the module follows what the ship is doing rather than what the bot last
intended. That arm's own success test is the same reading, and it treats no
dispatched click as a manoeuvre; a module tied to the ask instead would run on
every reading of a double click that commanded nothing. It also switches the
module off for free where an active afterburner costs the most, the ship lining
up to warp -- see `middleRowStep` for what the client does and does not say
about that state.

**Bounded, since #408.** This arm sits high enough in
`wingmanDecisionRootInSpaceOrdinary` that answering `Just` forever starves the
broadcast, the drones, the guns, the gate and the travel forms -- which is what
a propulsion module that would not switch off did to all four pilots at once.
Past `middleRowAskedReadingsBound` it answers `Nothing`, and
`describeMiddleRowAsk` keeps the give-up visible in the status line.

**Takes no `ShipUI` any more.** Every fact it needs comes off the reading
through `middleRowStepFromContext`, so the rule the memory update advances the
counter from, the rule the status line prints and the rule this arm executes
are one call and cannot be asked with different numbers -- `fireOnActiveTarget`
and `inactiveWeaponFromReading`'s arrangement, for #102's reason.

-}
manageMiddleRowModules : BotDecisionContext -> Maybe DecisionPathNode
manageMiddleRowModules context =
    let
        click description moduleButton =
            describeBranch description
                (clickModuleButtonButWaitIfClickedInPreviousStep context moduleButton)
    in
    case middleRowStepFromContext context of
        MiddleRowNeedsNothing ->
            Nothing

        LeaveThePropulsionModuleToTheWarp ->
            Nothing

        PropulsionModuleIsAlreadyShuttingDown ->
            Nothing

        PropulsionModuleSaysNothingAboutShuttingDown ->
            Nothing

        GaveUpOnTheMiddleRow ->
            Nothing

        ActivateAnAlwaysOnModule ->
            inactiveAlwaysOnModuleFromReading context.readingFromGameClient
                |> Maybe.map
                    (click "A middle-row module right of the propulsion module is not running. Switch it on.")

        RunThePropulsionModule ->
            propulsionModuleFromReading context.readingFromGameClient
                |> Maybe.map
                    (click "This ship is approaching the fleet commander. Run the propulsion module.")

        ShutThePropulsionModuleDown ->
            propulsionModuleFromReading context.readingFromGameClient
                |> Maybe.map
                    (click "This ship is not approaching anything. Shut the propulsion module down.")


{-| What the middle row asks for on one reading. See `middleRowStep`.
-}
type MiddleRowStep
    = ActivateAnAlwaysOnModule
    | RunThePropulsionModule
    | ShutThePropulsionModuleDown
    | PropulsionModuleIsAlreadyShuttingDown
    | PropulsionModuleSaysNothingAboutShuttingDown
    | LeaveThePropulsionModuleToTheWarp
    | GaveUpOnTheMiddleRow
    | MiddleRowNeedsNothing


{-| The middle-row rule, as one expression over six plain facts and a counter.

The always-on modules are answered before the propulsion module, which is
saxrat's own ordering and holds for the same reason: a tank module that is off
is off in a fight, and the propulsion module can wait the one reading that
costs.

**Both directions of the propulsion module are answered**, because "should be
off and is on" is a real state here rather than a symmetry kept for its own
sake. The module is switched on out on the approach and has to come off again
the moment the ship stops approaching -- when it arrives, when the commander
warps off and the row loses its manoeuvre, and when this ship lines up to
follow, where the added mass is what makes aligning slow.

`propulsionModulePresent` keeps the rule total rather than letting the arm ask
for a click it has no button for: a ship whose middle row is empty, or which is
still showing an unparsed row, must answer "nothing" rather than fall through
to a branch that assumes a slot.

**`isDeactivating` is what says whether the last click took, and #408 is what
not reading it cost.** The propulsion module has a ten-second cycle and goes on
reading `isActive` for the whole of it after being told to stop, while
`clickModuleButtonButWaitIfClickedInPreviousStep` waits two steps -- roughly
four seconds. So the click landed, the debounce expired inside the cycle, the
module still read on, and the next click switched it **back on**: saxrat's odd
number of toggles arriving through timing rather than through position. `isActive`
cannot answer "did my click take" during a cycle and this entry can, so a module
the client says is deactivating is left to finish however long `isActive` stays
true.

**`Nothing` is not `False` here, and that is the whole reason this fact is a
`Maybe` rather than a `Bool`.** `ParseUserInterface`'s own doc block is explicit
that an entry which did not decode is absent rather than false, that absent and
`False` are different facts, and that only one of them is safe to act on -- the
neighbouring `ramp_active` is a duty cycle rather than an on/off state, and #34
is what reading it as a state cost. Collapsing `Nothing` to "not deactivating"
would licence exactly the click this rule exists to withhold, so it gets its own
answer: the client said nothing, so nothing is clicked. The cost is stated
rather than hidden -- on a build that does not carry the entry the propulsion
module is never switched off, which loses the module and keeps the bot, and is
the direction #408 asks for. The guard is on the shutdown only: switching a
module **on** has no deactivation transient to misread, so a cold module is
still clicked whatever this entry says.

**A warp or a jump is left alone**, and this is the one manoeuvre state the
client actually names. `wingmanDecisionRootInSpaceOrdinary` has no warp gate
above it, so without this the arm meets every reading of a warp with "not
approaching, module on, shut it down" -- and each of those clicks is both wasted
(a module toggled in warp changes nothing about a warp already under way) and
the exact click that re-arms a module still running out its cycle, so the ship
would drop out of warp with the propulsion module lit.

**Aligning is deliberately not special-cased, because it is not observable.**
`ShipManeuverType` has `Warp`, `Jump`, `Orbit` and `Approach` and no `Align`: a
ship lining up reads no manoeuvre at all, which is the same `Nothing` as a ship
floating still, and a rule cannot decline a state it cannot see. It is also the
state where shutting the module down is worth the most -- an active propulsion
module is what makes aligning slow, which is #394's own argument -- so the arm
goes on asking there, and what stops it repeating is `isDeactivating` and then
the bound rather than a manoeuvre test that would have to guess.

**The bound is applied to the clicks and to nothing else.** Only
`ActivateAnAlwaysOnModule`, `RunThePropulsionModule` and
`ShutThePropulsionModuleDown` can become `GaveUpOnTheMiddleRow`; the answers
that decline to click are reported as themselves, so a give-up in the status
line always means "this bot clicked a module button
`middleRowAskedReadingsBound` times and the client never showed the change".
That also keeps `MiddleRowNeedsNothing` reachable after a give-up, which is what
resets the counter -- see `middleRowAskedReadingsBound` for the one coupling
this costs.

-}
middleRowStep :
    { inactiveAlwaysOnModulePresent : Bool
    , propulsionModulePresent : Bool
    , propulsionModuleIsRunning : Bool
    , propulsionModuleIsDeactivating : Maybe Bool
    , shipIsApproaching : Bool
    , shipIsWarpingOrJumping : Bool
    , askedReadings : Int
    }
    -> MiddleRowStep
middleRowStep step =
    let
        clickOrGiveUp : MiddleRowStep -> MiddleRowStep
        clickOrGiveUp answer =
            if middleRowAskedReadingsBound <= step.askedReadings then
                GaveUpOnTheMiddleRow

            else
                answer
    in
    if step.inactiveAlwaysOnModulePresent then
        clickOrGiveUp ActivateAnAlwaysOnModule

    else if not step.propulsionModulePresent then
        MiddleRowNeedsNothing

    else if step.shipIsApproaching && not step.propulsionModuleIsRunning then
        clickOrGiveUp RunThePropulsionModule

    else if step.propulsionModuleIsRunning && not step.shipIsApproaching then
        if step.shipIsWarpingOrJumping then
            LeaveThePropulsionModuleToTheWarp

        else if step.propulsionModuleIsDeactivating == Just True then
            PropulsionModuleIsAlreadyShuttingDown

        else if step.propulsionModuleIsDeactivating == Nothing then
            PropulsionModuleSaysNothingAboutShuttingDown

        else
            clickOrGiveUp ShutThePropulsionModuleDown

    else
        MiddleRowNeedsNothing


{-| How many readings in a row this bot will go on clicking a middle-row module
button the client never shows the change on, before it stops asking and hands
the reading back.

**Twenty, written as `weaponsAskedReadingsBound` rather than as a number**, the
same allowance every other per-reading ask in this file gets and for the same
reason: a click that is going to land does so in a handful of readings, and
twenty is several attempts' worth while being nowhere near a session. #408 is
the measurement it exists for -- 23 of Greta's last 23 top-level decisions were
this one arm, with Heather and Kara word for word the same, and nothing below it
ran on any of them.

Past the bound the arm answers `Nothing` rather than parking on
`askForHelpToGetUnstuck`, for the reason `accelerationGateStep` gives at its own
give-up: handing the reading back is what lets the broadcast, the drones, the
guns, the gate and the trip home still run, and `describeMiddleRowAsk` keeps the
give-up visible instead of hiding it. That is the half of #408 which gets the
ships moving again whether or not the module ever obeys.

**One counter for both halves of the row, and the coupling is real.** A tank
module that can never be switched on spends this budget and the give-up then
covers the propulsion module too, so that ship stops managing its propulsion
module for as long as the broken slot reads inactive. That is accepted rather
than overlooked: the arm answers one `Just` and so needs one give-up, the cost
is a module left unmanaged rather than a bot that stops following its commander,
and #408 is the second failure and not the first (#321, #360, #395) of an arm
that had no give-up at all.

-}
middleRowAskedReadingsBound : Int
middleRowAskedReadingsBound =
    weaponsAskedReadingsBound


{-| The answers on which this arm actually clicks something, and therefore the
answers `middleRowAskedReadings` advances on.

`weaponsAnswersThatSpendAReading`'s arrangement, for #389's reason: a counter
advanced by conditions written beside the arm rather than by the arm's own rule
charges the budget for readings nobody spent, and then reports a give-up on an
arm that was never asked. Everything not listed here either declines to click
(`PropulsionModuleIsAlreadyShuttingDown`,
`PropulsionModuleSaysNothingAboutShuttingDown`,
`LeaveThePropulsionModuleToTheWarp`), has already given up, or has nothing to
do, and none of those may spend a reading of the budget.

-}
middleRowAnswersThatSpendAReading : List MiddleRowStep
middleRowAnswersThatSpendAReading =
    [ ActivateAnAlwaysOnModule
    , RunThePropulsionModule
    , ShutThePropulsionModuleDown
    ]


{-| The rule above, asked of a reading, so that the memory update, the arm and
the status line are all reading one decision -- `weaponsStepFromReading`'s
arrangement, for #102's reason.

A reading with no ship UI answers `MiddleRowNeedsNothing`: nothing that is not
in space has a module row to manage, and that is also the answer which resets
the counter, so a docked stretch hands the next undock a full allowance.

-}
middleRowStepFromReading : Int -> ReadingFromGameClient -> MiddleRowStep
middleRowStepFromReading askedReadings readingFromGameClient =
    let
        propulsionModule : Maybe ShipUIModuleButton
        propulsionModule =
            propulsionModuleFromReading readingFromGameClient
    in
    middleRowStep
        { inactiveAlwaysOnModulePresent =
            inactiveAlwaysOnModuleFromReading readingFromGameClient /= Nothing
        , propulsionModulePresent = propulsionModule /= Nothing
        , propulsionModuleIsRunning =
            propulsionModule
                |> Maybe.map moduleIsActiveOrReloading
                |> Maybe.withDefault False
        , propulsionModuleIsDeactivating =
            propulsionModule
                |> Maybe.andThen (.stateFromDictEntries >> .isDeactivating)
        , shipIsApproaching = shipIsApproachingFromReading readingFromGameClient
        , shipIsWarpingOrJumping = shipIsWarpingOrJumpingFromReading readingFromGameClient
        , askedReadings = askedReadings
        }


middleRowStepFromContext : BotDecisionContext -> MiddleRowStep
middleRowStepFromContext context =
    middleRowStepFromReading context.memory.middleRowAskedReadings context.readingFromGameClient


{-| The propulsion module of the ship in this reading, if there is one.

One lookup with three readers -- the rule's `propulsionModulePresent`, the two
facts it reads off the same button, and the click the arm makes -- so the arm
cannot decide to click the propulsion module and then find none to click.
`inactiveWeaponFromReading`'s arrangement.

-}
propulsionModuleFromReading : ReadingFromGameClient -> Maybe ShipUIModuleButton
propulsionModuleFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.andThen propulsionModuleButton


{-| The first middle-row module right of the propulsion module that is not
running, if there is one. See `propulsionModuleFromReading`.
-}
inactiveAlwaysOnModuleFromReading : ReadingFromGameClient -> Maybe ShipUIModuleButton
inactiveAlwaysOnModuleFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map shipUIModulesToActivateAlways
        |> Maybe.withDefault []
        |> List.filter (moduleIsActiveOrReloading >> not)
        |> List.head


{-| The middle row in the order the player sees it, leftmost first.

Ported from `eve-online-saxrat`'s function of the same name, sort and all.
`moduleButtonsRows.middle` arrives in UI-tree order, and while that traversal is
a stable depth-first walk, the list it produces is not a stable index space: the
parser drops any node whose display region it cannot read, so a slot can leave
and rejoin the list without anything moving on screen. Taking "the first slot"
by index therefore does not reliably mean the same module twice.

saxrat caught live what that costs. With both tank modules already running, the
bot decided three times in a row to switch on what it called the propulsion
module, the propulsion module never came on, and a _tank_ module went off
instead -- an odd number of toggles landing on a neighbour. Sorting by x is what
makes "first in the middle row" mean the slot WINGMAN.md's setup section points
at, and it cannot be shifted by a slot dropping out of the list.

Takes the `ShipUI` where saxrat takes its `SeeUndockingComplete`; this bot's
arms are handed the ship UI directly, and the ordering is the part that has to
be identical.

-}
middleRowLeftToRight : ShipUI -> List ShipUIModuleButton
middleRowLeftToRight =
    .moduleButtonsRows
        >> .middle
        >> List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


{-| The tank modules: the middle row, minus the propulsion module in its first
slot.

The two halves of that row want opposite things and so are driven separately --
`manageMiddleRowModules` is which and why.

-}
shipUIModulesToActivateAlways : ShipUI -> List ShipUIModuleButton
shipUIModulesToActivateAlways =
    middleRowLeftToRight >> List.drop 1


{-| The propulsion module: the leftmost slot of the middle row, per WINGMAN.md's
setup section.
-}
propulsionModuleButton : ShipUI -> Maybe ShipUIModuleButton
propulsionModuleButton =
    middleRowLeftToRight >> List.head


{-| Self-defense only: fight back if a rat has pointed this ship, otherwise
return drones to the bay and wait.

**Deliberately does not hunt anomalies.** This function used to be named
`modulesToActivateAlwaysActivated` and, once no rat was pointing the ship,
used the probe scanner to warp itself into an anomaly on an idle grid --
which is not following a commander, and is exactly the behaviour #349 names
as what made a six-hour unattended run a bad idea. WINGMAN.md's own first
line says what this bot is: "it does not hunt, it follows a fleet commander."
So an idle wingman now sits still rather than going looking for a fight.
`enterAnomaly` and `decideActionInAnomaly` are still in this file, reachable
only from the inherited, unreachable `anomalyBotDecisionRoot` -- nothing on
the wingman's own path calls them any more.

Fighting a rat that has actually pointed this ship is kept, because that is
self-defense rather than hunting: the ship did not choose the fight, and
refusing to shoot back at something already attacking it would be worse than
either hunting or standing down.

-}
fightPointedRatsOrReturnDrones :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> DecisionPathNode
fightPointedRatsOrReturnDrones context shipUI =
    if friendlyFireVetoesTheGuns (friendlyFireStepFromContext context) then
        -- #367. The other trigger in this file, and the one whose lock is made
        -- by ctrl-clicking a buff button that names nobody:
        -- `fightRatsIfShipIsPointed` locks whoever is pointing this ship and
        -- hands straight to `fightUsingDronesAndModules`. Self-defense is
        -- still self-defense when the thing shooting back would be a
        -- fleetmate, so the veto is asked here too -- see
        -- `describeFriendlyFireGuard` for what is holding it.
        describeBranch
            "Holding fire: the friendly fire guard is refusing this lock bar."
            waitForProgressInGame

    else
        case fightRatsIfShipIsPointed context shipUI of
            Just fightPointingRats ->
                fightPointingRats

            Nothing ->
                if not (List.isEmpty context.readingFromGameClient.targets) then
                    -- Something is still locked, so this is a fight in progress
                    -- that simply is not pointing this ship -- which is the normal
                    -- case for a target the commander called. Recalling the drones
                    -- here would undo `dronesAssistTheCommander`'s work on the very
                    -- next reading and leave the bot pulling its drones in and
                    -- sending them back out for as long as the target lived.
                    if dronesAreInSpace context.readingFromGameClient then
                        describeBranch "A target is locked -- leaving the drones out." waitForProgressInGame

                    else
                        -- #374 is what this wording is for. The branch above
                        -- said "leaving the drones out" whether or not any
                        -- were, and run 12 printed it four times with fifteen
                        -- drones in the bay and none in space -- a line that
                        -- reads like a bot deliberately holding its drones on
                        -- the field, describing a bay that never opened.
                        describeBranch
                            "A target is locked, and no drones are in space -- nothing to recall."
                            waitForProgressInGame

                else
                    returnDronesToBay context
                        |> Maybe.withDefault (describeBranch "Nothing to do. Wait." waitForProgressInGame)


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

        maybeObjectToOrbit =
            objectToOrbitFromReading
                { orbitObjectNames = context.eventContext.botSettings.orbitObjectNames
                , prioritizeRats = context.eventContext.botSettings.prioritizeRats
                }
                context.readingFromGameClient

        ensureShipIsOrbitingDecision =
            case maybeObjectToOrbit of
                Nothing ->
                    Nothing

                Just objectToOrbit ->
                    ensureShipIsOrbiting context shipUI objectToOrbit

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
    if context.eventContext.botSettings.orbitFleetCommander == PromptParser.Yes then
        {- #365: `orbit-fc` supersedes `orbit-in-combat` rather than sitting
           beside it. Orbiting the rat this ship happens to be shooting is what
           walks a wingman off the commander's grid, and
           `approachTheFleetCommander` is already holding the ship on the
           commander -- issuing an orbit at a different object from here would
           fight it every reading. The setting is still spelled `orbit-fc`
           though the manoeuvre it commands is now an approach; see that
           function.
        -}
        decisionToKillRats

    else if context.eventContext.botSettings.orbitInCombat == PromptParser.Yes then
        ensureShipIsOrbitingDecision
            |> Maybe.withDefault decisionToKillRats

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
                    -- The chord itself is `ctrlClickEffects`, shared with
                    -- `lockCalledTarget` since #366 rather than written out
                    -- twice. This caller's own answer to an element too small
                    -- to click is unchanged.
                    case ctrlClickEffects firstPointingBuffButton of
                        Nothing ->
                            describeBranch "Failed to click"
                                askForHelpToGetUnstuck

                        Just effectToClick ->
                            describeBranch "hold the 'ctrl' key while left clicking the 'pointed' symbol"
                                (decideActionForCurrentStep effectToClick)
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
    ratsToAttackByPriorityFrom
        { prioritizeRats = context.eventContext.botSettings.prioritizeRats }
        context.readingFromGameClient


{-| The same answer over the reading and the one setting it consults.

Split out for `objectToOrbitFromReading`, which `updateMemoryForNewReadingFromGame`
has to ask and which never sees a decision -- the divergence
`selectedItemIsOverviewEntry`'s own comment records, and the reason a counter and
the branch that reads it cannot come to disagree about what was counted (#102).

-}
ratsToAttackByPriorityFrom : { prioritizeRats : List String } -> ReadingFromGameClient -> RatsByAttackPriority
ratsToAttackByPriorityFrom config readingFromGameClient =
    let
        context =
            { readingFromGameClient = readingFromGameClient }

        prioritizedRatsPatterns : List String
        prioritizedRatsPatterns =
            List.map String.toLower config.prioritizeRats

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


{-| The object `ensureShipIsOrbiting` would be asked to orbit on this reading.

One definition, asked by the arm and by the counter that bounds it, because two
copies of "what is being orbited" would be two answers about whether a reading
was spent asking for it -- and a counter that resets on a reading the arm was
asking on is a bound the arm can never reach.

-}
objectToOrbitFromReading :
    { orbitObjectNames : List String, prioritizeRats : List String }
    -> ReadingFromGameClient
    -> Maybe OverviewWindowEntry
objectToOrbitFromReading config readingFromGameClient =
    let
        overviewsAllEntries =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
    in
    case findObjectToOrbitByName config.orbitObjectNames overviewsAllEntries of
        Just fromName ->
            Just fromName

        Nothing ->
            ratsToAttackByPriorityFrom { prioritizeRats = config.prioritizeRats } readingFromGameClient
                |> .overviewEntriesByPrio
                |> List.concatMap (\( first, rest ) -> first :: rest)
                |> List.Extra.last


{-| Whether this reading is one spent asking the panel to show the object to
orbit.

Reading-and-settings only, so this and the arm read the same thing.

-}
askingThePanelToShowTheObjectToOrbit :
    { orbitObjectNames : List String, prioritizeRats : List String }
    -> ReadingFromGameClient
    -> Bool
askingThePanelToShowTheObjectToOrbit config readingFromGameClient =
    case objectToOrbitFromReading config readingFromGameClient of
        Nothing ->
            False

        Just entry ->
            not (selectedItemIsOverviewEntry readingFromGameClient entry)


{-| What to do about a manoeuvre the ship is not making yet, given a row to make
it on. A pure function over a record so a case can execute it rather than
describe it.
-}
type PanelManoeuvreStep
    = ManoeuvreIsAlreadyRunning
    | SelectTheRowFirst
    | PressThePanelButton
    | WaitForThePanelButton
    | GaveUpOnSelectingTheRow


{-| Command a manoeuvre through the Selected Item panel rather than by clicking
the row that names it.

**Why this is not the chord it replaces.** The orbit held `W` down over a click
on the overview row, and that click is a screen position computed from a
reading. The overview is sorted by distance and rats move, so the row order
changes between the reading and the click, and with two identically named rats
the chord lands on the neighbour and _commands the orbit on it_. That is #413.

**The panel acts on the selected object rather than on a position**, so the
command half of the exposure is gone outright: the button sits in the panel and
is found by name in the same reading it is pressed in. What remains is the
selection click, which lands on whatever the row's position now holds -- and the
difference is that the panel then **names what was selected**, so
`selectedItemIsOverviewEntry` catches a click that went astray _before_ the
manoeuvre is commanded. The chord had no such check: it commanded immediately.

**It does not eliminate the exposure for two identically named rats**, and that
is stated rather than implied: the panel names the object, and two rats of one
type share a name, so a selection that lands on the neighbour reads as correct.
It is the shape `warpAwayFromDanger` and the gate arm already accept.

**It also takes the last modifier chord off this bot's hot path.** #387 removed
the approach's `Q` because `cg_input` posts a key event without stamping flags
on it, so a posted key carries whatever modifier state the session happens to
hold -- with the Fn bit set that is macOS Quick Note, and one recorded saxrat
run took that branch 1,571 times while Notes came to the front 241 times with
nobody at the machine. PR #241 fixed the stamping; this removes the last place
this bot depended on it.

**The distance is unchanged.** The panel's Orbit uses the client's own default
distance -- and so did the `W` chord it replaces. WINGMAN.md and PILOT.md are
explicit that no bot setting carries an engagement distance (`orbit-fc-range` is
accepted and ignored, and says so), so this changes the gesture and not the
range.

**Absence is normal, not a failure.** The panel's button set is contextual, and
a ship in warp offers less again. So a reading whose panel shows the row and
offers no button hands the reading **back to the fight** rather than waiting on
it. Nothing is retried, nothing is counted against it, and the next reading asks
again.

**The selection is what needs the bound.** A panel that never comes to show the
row would otherwise be clicked at every reading forever while the guns never
fire. `selectionUnansweredReadings` is that counter, and past
`panelSelectGiveUpReadings` this answers `GaveUpOnSelectingTheRow`, which also
hands the reading to the fight -- which is exactly what a bot with
`orbit-in-combat` unset already does, so the give-up degrades to a shipped
configuration rather than to a stall.

**Success is the client's own word and never the press.** The greyed-out state
is not readable -- every button in every reading #414 recorded carried
`isDisabled = None` and full opacity -- so a dimmed button and a live one are
indistinguishable, and only the ship UI's indication naming `command.maneuver`
stops the ask, exactly as `approachFleetCommanderStep` rests on it.

-}
panelManoeuvreStep :
    { manoeuvreIsRunning : Bool
    , panelShowsTheRow : Bool
    , panelOffersTheButton : Bool
    , selectionUnansweredReadings : Int
    }
    -> PanelManoeuvreStep
panelManoeuvreStep manoeuvreCase =
    if manoeuvreCase.manoeuvreIsRunning then
        ManoeuvreIsAlreadyRunning

    else if manoeuvreCase.panelShowsTheRow then
        if manoeuvreCase.panelOffersTheButton then
            PressThePanelButton

        else
            WaitForThePanelButton

    else if manoeuvreCase.selectionUnansweredReadings >= panelSelectGiveUpReadings then
        GaveUpOnSelectingTheRow

    else
        SelectTheRowFirst


{-| Readings in a row with an object to manoeuvre on that the Selected Item
panel is not showing, before the manoeuvre arm stops asking for it.

The selection lands on the next reading when it works at all, so this is an order
of magnitude more than the one reading it should take -- and small enough that a
panel that never answers costs the fight a handful of readings rather than a
session. **It is not calibrated against a corpus**, because no recorded run has
ever driven a manoeuvre through the panel; what the direction rests on is that
expiry hands the reading to the fight, so being early costs a manoeuvre and being
late costs readings the guns would have had.

It clears itself: the counter resets on any reading where the panel _is_ showing
the object to orbit, or where there is none, and rats die constantly.

-}
panelSelectGiveUpReadings : Int
panelSelectGiveUpReadings =
    10


{-| Readings in a row the panel has not come to show the object to orbit.

Advances on a reading that was asking, resets on anything else -- including a
reading with nothing to orbit, which is not the ship failing to select one.

-}
panelSelectReadingsAfterReading : { asking : Bool, before : Int } -> Int
panelSelectReadingsAfterReading readingCase =
    if readingCase.asking then
        readingCase.before + 1

    else
        0


{-| A left click that declines out loud rather than dispatching nothing.

`clickUiElement` and `clickUiElementForNavigation` answers `Result.withDefault []` for an element whose visible
part is too small to click, which prints a decision line over an empty effect
list -- this repo's signature failure, and the one `doubleClickUiElement`
already refuses in exactly these words. The select-then-press of #414 makes two
clicks per manoeuvre where the gesture it replaced made one, so both go through
here.

-}
clickUiElementOrSayItCannotBeClicked : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
clickUiElementOrSayItCannotBeClicked uiElement =
    case mouseClickOnUIElement MouseButtonLeft uiElement of
        Ok clickEffects ->
            decideActionForCurrentStep clickEffects

        Err () ->
            describeBranch
                "The visible part of this element is too small to click, so there is nothing to dispatch."
                waitForProgressInGame


{-| The shared select-then-press body the manoeuvre arm takes.

Written as a shape rather than inline because #414 puts the identical ordering
into `eve-online-saxrat`'s three arms, and an ordering copied per arm is an
ordering that can end up with a press ahead of its selection in one of them.

**The cost is a reading, not a click, and that is the form that matters here.**
The selection is dispatched on one reading and the panel only shows it on the
_next_, so the orbit now starts one reading later than the `W` chord did --
one reading of transversal not being held.

What the reading buys is the check that cannot be made without it. The chord
commanded immediately, on a screen position computed from a reading the
overview had already re-sorted under -- so a selection that went astray was
discovered by the ship orbiting the wrong object, which for a wingman is the
fleet commander's neighbour. Spending the reading puts
`selectedItemIsOverviewEntry` between the two, so a selection that landed on
someone else is caught _before_ anything is commanded rather than after.

-}
commandManoeuvreFromSelectedItemPanel :
    { button : SelectedItemPanelButton
    , maneuver : EveOnline.ParseUserInterface.ShipManeuverType
    , describe : String
    }
    -> BotDecisionContext
    -> ShipUI
    -> OverviewWindowEntry
    -> Maybe DecisionPathNode
commandManoeuvreFromSelectedItemPanel command context shipUI overviewEntry =
    let
        name =
            overviewEntry.objectName |> Maybe.withDefault "it"

        button =
            selectedItemPanelButton context.readingFromGameClient command.button
    in
    case
        panelManoeuvreStep
            { manoeuvreIsRunning = (shipUI.indication |> Maybe.andThen .maneuverType) == Just command.maneuver
            , panelShowsTheRow = selectedItemIsOverviewEntry context.readingFromGameClient overviewEntry
            , panelOffersTheButton = button /= Nothing
            , selectionUnansweredReadings = context.memory.panelSelectUnansweredReadings
            }
    of
        ManoeuvreIsAlreadyRunning ->
            Nothing

        SelectTheRowFirst ->
            Just
                (describeBranch
                    ("Select '" ++ name ++ "', so the panel's own " ++ command.describe ++ " acts on it.")
                    (clickUiElementOrSayItCannotBeClicked overviewEntry.uiNode)
                )

        PressThePanelButton ->
            button
                |> Maybe.map
                    (\buttonNode ->
                        describeBranch
                            (command.describe ++ " '" ++ name ++ "' with the selected-item panel's own button.")
                            (clickUiElementOrSayItCannotBeClicked buttonNode)
                    )

        WaitForThePanelButton ->
            -- Absence is not a failure: the panel's button set is contextual and
            -- a ship in warp offers fewer. Hand the reading to the fight and ask
            -- again next reading rather than spending readings on a button that
            -- may simply not belong to this object.
            Nothing

        GaveUpOnSelectingTheRow ->
            Nothing


ensureShipIsOrbiting : BotDecisionContext -> ShipUI -> OverviewWindowEntry -> Maybe DecisionPathNode
ensureShipIsOrbiting =
    commandManoeuvreFromSelectedItemPanel
        { button = selectedItemOrbitButton
        , maneuver = EveOnline.ParseUserInterface.ManeuverOrbit
        , describe = "Orbit"
        }


{-| What the manoeuvre arm's select-then-press is doing on this reading.

A rule over the record rather than text built inline in the status line, so a
case executes what an operator reads. Without it the whole select-then-press has
no reading in the log at all: `WaitForThePanelButton` and
`GaveUpOnSelectingTheRow` both answer `Nothing`, which cannot carry a decision
line, so a panel that never offers the button and a manoeuvre that is running
happily print identically.

-}
describePanelManoeuvreSelection : { asking : Bool, unansweredReadings : Int } -> String
describePanelManoeuvreSelection selectionCase =
    "panel "
        ++ (selectionCase.unansweredReadings |> String.fromInt)
        ++ "/"
        ++ (panelSelectGiveUpReadings |> String.fromInt)
        ++ (if selectionCase.unansweredReadings >= panelSelectGiveUpReadings then
                " (GIVEN UP on selecting the object to manoeuvre on -- fighting without a manoeuvre)"

            else if selectionCase.asking then
                " (selecting the object to manoeuvre on)"

            else
                ""
           )


{-| Ask the client to approach an object by **double clicking its overview
row**, which presses no key at all. See `approachTheFleetCommander` for why
this bot commands an approach in the first place.

**The keystroke this replaces is one `eve-online-saxrat` removed for cause**
(#387, and saxrat's own #243). `lockTargetFromOverviewEntry` answered a row
beyond lock range by wrapping a left click in a `Q` chord, exactly as this
function did until now. `cg_input` posts a key event without stamping flags on
it, so a posted `Q` carries whatever modifier state the session happens to
hold; with the Fn bit set that is macOS Quick Note, and one recorded saxrat run
took that branch 1,571 times while Notes came to the front 241 times with
nobody at the machine. Fixing the mis-stamping is a separate thing already
done: this removes the keystroke, which also takes a modifier-timing dependency
off a station-keeping arm that is on a hot path by design.

**A double click asks the client for the same thing.** It is the gesture
saxrat's `doubleClickUiElement` already sends on the same kind of row, and
`mouseDoubleClickOnUIElement` is that bot's framework function ported here
unchanged rather than reinvented.

**A row too small to click declines out loud rather than dispatching nothing.**
`Err` reaches `approachTheFleetCommander`, which prints the reason and spends
the reading -- a branch that says "Approach." over an empty effect list is this
repo's signature failure, and it would be a total one here where the chord at
least still sent `Q`.

**Success is still only the client's own word.** The ship UI's indication
naming `Approach` is what stops the ask; a dispatched double click is no more a
manoeuvre than a dispatched chord was.

-}
ensureShipIsApproaching : ShipUI -> OverviewWindowEntry -> Maybe (Result String DecisionPathNode)
ensureShipIsApproaching shipUI overviewEntry =
    if (shipUI.indication |> Maybe.andThen .maneuverType) == Just EveOnline.ParseUserInterface.ManeuverApproach then
        Nothing

    else
        Just
            (case mouseDoubleClickOnUIElement MouseButtonLeft overviewEntry.uiNode of
                Err _ ->
                    Err "the visible part of the overview row is too small to click"

                Ok effectToDoubleClick ->
                    Ok
                        (describeBranch
                            "Double click on the overview entry."
                            (decideActionForCurrentStep effectToDoubleClick)
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


{-| Whether any drone is actually in space right now.

One definition, used by both the recall and the branch that declines to
recall. They asked the same question in two places before #374, and only one
of them was asking it -- the decline said "leaving the drones out" without
looking, so a session that never launched a drone logged as one that was
deliberately keeping them deployed.

-}
dronesAreInSpace : ReadingFromGameClient -> Bool
dronesAreInSpace readingFromGameClient =
    0 < dronesInSpaceCountFromReading readingFromGameClient


{-| How many drones the client says are in space, or `0` where it does not say.

The same question `dronesAreInSpace` answers, as the number rather than the
`Bool`, because `calledGateRecallAskedReadings` has to know whether the count
_fell_ -- a partial recall is the client answering, and only a count can see
one. `dronesAreInSpace` is expressed in terms of this so the two cannot come
apart the way the recall and its decline did before #374.

A reading with no drones window answers `0`, which is right for both readers:
docked, or a client that did not draw it, is not a ship with drones out.

-}
dronesInSpaceCountFromReading : ReadingFromGameClient -> Int
dronesInSpaceCountFromReading readingFromGameClient =
    readingFromGameClient.dronesWindow
        |> Maybe.andThen .droneGroupInSpace
        |> Maybe.andThen (.header >> .quantityFromTitle)
        |> Maybe.map .current
        |> Maybe.withDefault 0


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
                    if not (dronesAreInSpace context.readingFromGameClient) then
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
            , decideNextStep = wingmanDecisionRoot
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
    , fleetBroadcastSeen = Nothing
    , fleetBroadcastFollowed = Nothing
    , goToFleetMatePlaceSeen = Nothing
    , goToFleetMateDestinationAsked = Nothing
    , goToFleetMateWarpAskedReadings = 0
    , routeFirstMarkerRegion = Nothing
    , routeFirstMarkerUnchangedTicks = 0
    , hitpoints =
        { shield = initHitpointsGaugeMemory
        , armor = initHitpointsGaugeMemory
        }
    , lowestShieldPercentSinceHealthy = 100
    , lowestArmorPercentSinceHealthy = 100
    , incomingDamage =
        { samples = []
        , hostCarriesTheChannel = False
        , retreating = False
        }
    , retreatAskedReadings = 0
    , recoveringFromRetreat = False
    , fleetPlaceBroadcast = Nothing
    , retreatRecoveryAskedReadings = 0
    , gateAskedReadings = 0
    , calledTargetGone = Nothing
    , bannerCtrlClick = Nothing
    , calledGateRecallAskedReadings = 0
    , dronesInSpaceCountLastReading = 0
    , weaponsAskedReadings = 0
    , approachFleetCommanderAskedReadings = 0
    , panelSelectUnansweredReadings = 0
    , closingOnTheCommanderSinceLanding = False
    , backupCallAskedReadings = 0
    , unlockFleetPilotAskedReadings = 0
    , middleRowAskedReadings = 0
    , messageBoxStandoff = Nothing
    , messageBoxLastChange = Nothing
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
                        -- The believed pair, not the live gauge, so the header
                        -- says what the guards are going by rather than what
                        -- the widget said this once. `plausibleHitpointsPercent`
                        -- rejects the impossible readings and `believed`
                        -- withholds a fall no second reading has confirmed, so
                        -- a header printing the raw value would disagree with
                        -- the retreat on exactly the readings that matter.
                        describeGauge : Maybe Int -> String
                        describeGauge believed =
                            case believed of
                                Nothing ->
                                    "?"

                                Just percent ->
                                    String.fromInt percent ++ "%"

                        describeShip =
                            "Believed hitpoints: shield "
                                ++ describeGauge context.memory.hitpoints.shield.believed
                                ++ ", armor "
                                ++ describeGauge context.memory.hitpoints.armor.believed
                                ++ " (this reading's raw shield gauge: "
                                ++ (shipUI.hitpointsPercent.shield |> String.fromInt)
                                ++ "%)."

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
                    , [ describeMiddleRowModules context, describeMiddleRowAsk context ]
                    , [ describeAnomaly, describeArrivalWindowClause, describeOverview ]
                    , [ describeRetreat context, describeRetreatRecovery context ]
                    , [ describeFleetMembership context, describeFriendlyFireGuard context ]
                    , [ describeAccelerationGateAsk context ]
                    , [ describeCalledObject context ]
                    , [ describeWeaponsAsk context ]
                    , [ describeApproachFleetCommanderAsk context ]
                    , [ describePanelManoeuvreSelection
                            { asking =
                                askingThePanelToShowTheObjectToOrbit
                                    { orbitObjectNames = context.eventContext.botSettings.orbitObjectNames
                                    , prioritizeRats = context.eventContext.botSettings.prioritizeRats
                                    }
                                    context.readingFromGameClient
                            , unansweredReadings = context.memory.panelSelectUnansweredReadings
                            }
                      ]
                    , [ describeFleetMateWarp context ]
                    , [ describeBackupCall context ]
                    ]
                        -- Empties are dropped inside a group as well as
                        -- between them, so a describer with nothing to say
                        -- costs no stray space in the line beside it.
                        |> List.map (List.filter (String.isEmpty >> not) >> String.join " ")
    in
    [ [ describePerformance ]
    , -- Outside `describeCurrentReading`, which is only built for a reading
      -- with a ship UI: a message box can be up while docked, and a box that
      -- holds the tree is exactly the state an operator needs named. Silent on
      -- every reading with no box, so an ordinary run pays nothing for it.
      [ describeMessageBoxStandoff context.memory.messageBoxStandoff ]
    , describeCurrentReading
    , -- Last, and on its own line, matching the mission runner's own
      -- placement: the host prints the status text inline after the tick
      -- marker, so the first line is what an operator reads as "what is
      -- this reading about", and that has to stay the mission rather than
      -- the wind-down bookkeeping.
      [ hostDirectiveExtendSession context ]
    ]
        |> List.concat
        |> List.filter (String.isEmpty >> not)
        |> String.join "\n"


{-| Per-slot state of the middle row, for the status line. The leftmost slot is
named on its own because it is the propulsion module, which runs on its own rule
(`manageMiddleRowModules`) rather than with the rest of the row.

#394's whole evidence was read off a pilot's console, and what it could not show
was why nothing was being activated -- an empty setting and an unfound row look
identical from outside. So this prints the row the bot actually resolved,
including the case where it found none, and says whether the client is naming
the manoeuvre the propulsion module is waiting on.

-}
describeMiddleRowModules : BotDecisionContext -> String
describeMiddleRowModules context =
    case context.readingFromGameClient.shipUI of
        Nothing ->
            ""

        Just shipUI ->
            let
                describeOne moduleButton =
                    if moduleIsActiveOrReloading moduleButton then
                        "on"

                    else
                        "off"
            in
            case middleRowLeftToRight shipUI of
                [] ->
                    "Middle row: no module slots read, so nothing is kept active by position."

                propulsionModule :: alwaysOn ->
                    "Middle row: prop mod "
                        ++ describeOne propulsionModule
                        ++ " and this ship "
                        ++ (if shipIsApproachingFromReading context.readingFromGameClient then
                                "is approaching"

                            else
                                "is not approaching"
                           )
                        ++ ", keep-active ["
                        ++ (alwaysOn |> List.map describeOne |> String.join ", ")
                        ++ "]."


{-| What the middle-row arm is doing about that row, in one clause beside it.

Exists for the reason `describeWeaponsAsk` and `describeAccelerationGateAsk` do,
and #408 is the reading that needed it: `manageMiddleRowModules` answers
`Nothing` when it gives up and `Nothing` when it declines to click, and without
this every one of those looks from a console exactly like a row that is already
as it should be. It reports `middleRowStep`'s own answer rather than restating
the conditions beside it, so what an operator reads is the decision that was
taken.

The two `isDeactivating` lines are named apart on purpose. "The client says the
module is deactivating" and "the client says nothing about it" are different
facts -- the parser's doc block is what insists on that -- and only the first of
them is evidence the last click landed. A console showing the second one for a
whole session is a build that does not carry the entry, which is worth being
able to see.

-}
describeMiddleRowAsk : BotDecisionContext -> String
describeMiddleRowAsk context =
    let
        spent : String
        spent =
            String.fromInt context.memory.middleRowAskedReadings
                ++ " of "
                ++ String.fromInt middleRowAskedReadingsBound
                ++ " readings spent clicking."
    in
    case middleRowStepFromContext context of
        MiddleRowNeedsNothing ->
            ""

        ActivateAnAlwaysOnModule ->
            "Switching a keep-active module on, " ++ spent

        RunThePropulsionModule ->
            "Switching the propulsion module on, " ++ spent

        ShutThePropulsionModuleDown ->
            "Switching the propulsion module off, " ++ spent

        PropulsionModuleIsAlreadyShuttingDown ->
            "The client says the propulsion module is already deactivating, so it runs its cycle out unclicked."

        PropulsionModuleSaysNothingAboutShuttingDown ->
            "The client says nothing about whether the propulsion module is deactivating, and absent is not 'not deactivating', so no click goes out."

        LeaveThePropulsionModuleToTheWarp ->
            "The ship is warping or jumping, so the propulsion module is left to the manoeuvre."

        GaveUpOnTheMiddleRow ->
            "GAVE UP after "
                ++ String.fromInt context.memory.middleRowAskedReadings
                ++ " readings clicking a middle-row module the client never showed the change on."


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


updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings -> BotMemory -> BotMemory
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

        -- Ported from `eve-online-warp-to-0-autopilot`'s field of the same
        -- name -- see that bot's own `BotMemory` doc comment for the full
        -- argument: right after a route is (re)set, the route panel's marker
        -- strip needs a moment to finish computing, and clicking during that
        -- window means clicking a position with no clickable icon there yet.
        currentRouteFirstMarkerRegion : Maybe EveOnline.ParseUserInterface.DisplayRegion
        currentRouteFirstMarkerRegion =
            infoPanelRouteFirstMarkerFromReadingFromGameClient context.readingFromGameClient
                |> Maybe.map (.uiNode >> .totalDisplayRegion)

        -- The gate this bot would act on, and on whose authority -- taken from
        -- the shipped rule rather than restated beside it, so the counters and
        -- the arm cannot disagree about which gate is being asked. A gate the
        -- commander broadcast a `Target` on wins over the nearest one (#393).
        gateToAct : Maybe AccelerationGateToAct
        gateToAct =
            accelerationGateToAct context.readingFromGameClient

        gateOnOverview : Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
        gateOnOverview =
            gateToAct |> Maybe.map .gate

        -- Whether this reading is one the called gate is being held on for the
        -- drones, asked through the rule the arm itself asks. Advancing on a
        -- reading the arm did not spend is #389's second defect, and this is
        -- narrower than "a called gate exists": with the drones home, or past
        -- the give-up, no recall goes out and no budget should move.
        askingForTheCalledGateRecall : Bool
        askingForTheCalledGateRecall =
            case gateToAct of
                Nothing ->
                    False

                Just gate ->
                    calledGateDroneRecall
                        { calledByTheCommander = gate.calledByTheCommander
                        , dronesAreInSpace = dronesAreInSpace context.readingFromGameClient
                        , askedReadings = botMemoryBefore.calledGateRecallAskedReadings
                        }
                        == RecallTheDronesFirst

        -- Same shape as `askingAnAccelerationGateToOpen` in saxrat: the gate
        -- is on the overview, the panel is already showing it, and nothing
        -- else is holding this bot back from pressing it -- rats on the
        -- overview count as holding back, since #348 is what this counter
        -- exists for, unless the commander called this gate, which is #393's
        -- override and is asked through `gateMayBeTaken` rather than restated.
        -- A reading spent recalling drones is not a reading spent asking the
        -- gate, so it holds the count rather than advancing it.
        askingTheGateToOpen : Bool
        askingTheGateToOpen =
            case gateToAct of
                Nothing ->
                    False

                Just gate ->
                    gateMayBeTaken
                        { ratsOnTheGrid = not (List.isEmpty namesOfRatsInOverview)
                        , calledByTheCommander = gate.calledByTheCommander
                        }
                        && not askingForTheCalledGateRecall
                        && selectedItemIsOverviewEntry context.readingFromGameClient gate.gate

        gaugeReading : (EveOnline.ParseUserInterface.Hitpoints -> Int) -> Maybe Int
        gaugeReading whichGauge =
            context.readingFromGameClient.shipUI
                |> Maybe.map (.hitpointsPercent >> whichGauge)
                |> Maybe.andThen plausibleHitpointsPercent

        hitpointsNow : HitpointsMemory
        hitpointsNow =
            { shield =
                updateHitpointsGaugeMemory (gaugeReading .shield) botMemoryBefore.hitpoints.shield
            , armor =
                updateHitpointsGaugeMemory (gaugeReading .armor) botMemoryBefore.hitpoints.armor
            }

        shipUIIsShowing : Bool
        shipUIIsShowing =
            context.readingFromGameClient.shipUI /= Nothing

        lowestShieldNow : Int
        lowestShieldNow =
            lowWaterMarkAfterReading
                { shipUIIsShowing = shipUIIsShowing
                , believed = hitpointsNow.shield.believed
                , previous = botMemoryBefore.lowestShieldPercentSinceHealthy
                }

        lowestArmorNow : Int
        lowestArmorNow =
            lowWaterMarkAfterReading
                { shipUIIsShowing = shipUIIsShowing
                , believed = hitpointsNow.armor.believed
                , previous = botMemoryBefore.lowestArmorPercentSinceHealthy
                }

        incomingDamageNow : IncomingDamageMemory
        incomingDamageNow =
            updateIncomingDamageMemory context botMemoryBefore.incomingDamage

        -- The same question `retreatToTheCommander` asks, asked here so the
        -- counter below measures the retreat rather than a settings-free
        -- stand-in for it. Gated on the ship UI parsing because that is the
        -- decision's own gate: `branchDependingOnDockedOrInSpace` only reaches
        -- the retreat through `ifSeeShipUI`, and a docked reading whose damage
        -- latch is still set would otherwise count against a retreat there is
        -- no ship to make.
        retreatIsDecided : Bool
        retreatIsDecided =
            (context.readingFromGameClient.shipUI /= Nothing)
                && (retreatReason
                        (retreatCaseFromMemory context.botSettings
                            { botMemoryBefore
                                | hitpoints = hitpointsNow
                                , lowestShieldPercentSinceHealthy = lowestShieldNow
                                , lowestArmorPercentSinceHealthy = lowestArmorNow
                                , incomingDamage = incomingDamageNow
                            }
                        )
                        /= Nothing
                   )

        commanderIsOnGrid : Bool
        commanderIsOnGrid =
            fleetCommanderOverviewEntry context.readingFromGameClient /= Nothing

        recoveringFromRetreatNow : Bool
        recoveringFromRetreatNow =
            if retreatIsDecided then
                True

            else if commanderIsOnGrid then
                False

            else
                botMemoryBefore.recoveringFromRetreat

        -- #381. The place travels with the pilot who named it and the reunion
        -- drops it, both stated in `fleetPlaceBroadcastAfterReading`. The clear
        -- is keyed on the same `commanderIsOnGrid` that clears
        -- `recoveringFromRetreat` one binding up, deliberately: the two are one
        -- event -- this ship is back with its commander -- and two conditions
        -- for it would be two definitions drifting apart.
        fleetPlaceBroadcastNow : Maybe { pilot : String, place : String }
        fleetPlaceBroadcastNow =
            fleetPlaceBroadcastAfterReading
                { seenThisReading = fleetPlaceBroadcastAnyPilot context.readingFromGameClient
                , commanderIsOnGrid = commanderIsOnGrid
                , before = botMemoryBefore.fleetPlaceBroadcast
                }

        -- Taken from the shipped rule rather than restated beside it, the same
        -- arrangement as `answeringABackupCall` and for its reason: the arm and
        -- this counter ask one rule, so they cannot disagree about which
        -- reading was spent. `retreatRecoveryAnswersThatSpendAReading` is the
        -- list, so an answer that dispatches nothing -- no commander named, a
        -- budget already spent, a ship already in warp, and above all a grid
        -- with nowhere to rejoin -- spends none of the budget. Charging that
        -- last one would be #389 exactly: a give-up counted out of state the
        -- arm never acted on.
        recoveringStepNow : RetreatRecoveryStep
        recoveringStepNow =
            retreatRecoveryStepFromReading
                context.botSettings.followFleetBroadcastFrom
                { recovering = recoveringFromRetreatNow
                , fleetPlaceBroadcast = fleetPlaceBroadcastNow
                , askedReadings = botMemoryBefore.retreatRecoveryAskedReadings
                }
                context.readingFromGameClient

        shipIsApproachingNow : Bool
        shipIsApproachingNow =
            shipIsApproachingFromReading context.readingFromGameClient

        -- #397's window, settled here for the reason every verdict on this
        -- channel is: the memory update is the only thing that runs on every
        -- reading unconditionally, and `warpJustEnded` is a transition between
        -- two readings that only this function can see.
        --
        -- Read by the counter below rather than `botMemoryBefore`'s value,
        -- because the decision reads this reading's answer -- so a window that
        -- opens on this reading with `orbit-fc=no` would otherwise have the
        -- decision asking while the counter believed the ask was off, and
        -- `approachFleetCommanderAskedReadingsBound` would be unreachable
        -- during the very window it bounds. That is #34's shape.
        closingOnTheCommanderSinceLandingNow : Bool
        closingOnTheCommanderSinceLandingNow =
            landingCloseAfterReading
                { closeWasOwed = botMemoryBefore.closingOnTheCommanderSinceLanding
                , justLanded = weJustFinishedWarping
                , shipIsApproaching = shipIsApproachingNow
                }

        -- The same shape as `askingTheGateToOpen` and `weaponsNow`,
        -- and taken from the shipped rule itself rather than restated beside
        -- it: a counter advanced by one condition and read by another is
        -- #102's defect, and `approachFleetCommanderStep` is the only thing
        -- that decides whether the ask goes out. `retreatIsDecided` above is
        -- the same arrangement, and #364 is what made it possible here --
        -- `UpdateMemoryContext` carries the settings since that change, so
        -- this reads the real `orbit-fc` rather than the `True` it had to
        -- assume when the settings were not visible from a memory update --
        -- and #397 is why the setting is asked through
        -- `approachFleetCommanderIsAsked` rather than compared here.
        askingTheCommanderForAnApproach : Bool
        askingTheCommanderForAnApproach =
            List.member
                (approachFleetCommanderStep
                    { settingIsYes =
                        approachFleetCommanderIsAsked
                            { settingIsYes = context.botSettings.orbitFleetCommander == PromptParser.Yes
                            , closingSinceLanding = closingOnTheCommanderSinceLandingNow
                            }
                    , commanderOnGrid = commanderIsOnGrid
                    , shipIsWarpingOrJumping = shipIsWarpingOrJumpingFromReading context.readingFromGameClient
                    , shipIsApproaching = shipIsApproachingNow
                    , strayWindowIsOpen = windowOpenedOverTheClient context.readingFromGameClient /= Nothing
                    , panelShowsTheCommander = panelIsShowingTheFleetCommander context.readingFromGameClient
                    , panelOffersApproach =
                        selectedItemButtonNamed context.readingFromGameClient selectedItemApproachButtonName /= Nothing
                    , askedReadings = botMemoryBefore.approachFleetCommanderAskedReadings
                    }
                )
                approachFleetCommanderAnswersThatSpendAReading

        -- The same shape as `askingTheGateToOpen`, and asked through the rule
        -- the decision itself asks rather than restated beside it: a fleet-mate
        -- this ship is flying to has a row on this overview, which is exactly
        -- the state `warpToFleetMateOnThisGrid` spends a reading in. It counts
        -- a reading an arm *above* the broadcast happened to take, so it
        -- over-counts rather than under-counts -- the safe direction for a
        -- bound whose whole job is to end #373's loop.
        fleetMateOnThisGrid : Maybe String
        fleetMateOnThisGrid =
            fleetMateToWarpToOnThisGrid
                { followFleetBroadcastFrom = context.botSettings.followFleetBroadcastFrom
                , recoveringFromRetreat = botMemoryBefore.recoveringFromRetreat
                }
                context.readingFromGameClient

        -- The same arrangement again, and the same reason: the arm and this
        -- counter ask one rule rather than two conditions that could disagree
        -- about whether a reading was spent. `backupCallAnswersThatSpendAReading`
        -- is the list, so an answer that dispatches nothing -- a call this ship
        -- will not answer, one it has given up on, a ship already closing --
        -- spends none of the budget.
        answeringABackupCall : Maybe { pilot : String, step : BackupCallStep }
        answeringABackupCall =
            backupCallStepFromReading
                { followFleetBroadcastFrom = context.botSettings.followFleetBroadcastFrom
                , answerBackupCalls = context.botSettings.answerBackupCalls == PromptParser.Yes
                }
                botMemoryBefore.backupCallAskedReadings
                context.readingFromGameClient

        -- Taken from the shipped rule rather than restated beside it, the same
        -- arrangement as `askingTheCommanderForAnOrbit` above and for #102's
        -- reason: a counter advanced by one condition and read by another is
        -- two rules on two schedules.
        friendlyFireNow : FriendlyFireStep
        friendlyFireNow =
            friendlyFireStepFromReading
                context.botSettings.followFleetBroadcastFrom
                botMemoryBefore.unlockFleetPilotAskedReadings
                context.readingFromGameClient

        -- The same arrangement again, and #389 is the reading of it that had a
        -- hole: this used to be a state test written beside the guns rather
        -- than the guns' own rule, so it charged the budget on readings
        -- `fireOnActiveTarget` refused -- and, while an arm above held every
        -- reading, on readings it never ran at all. See
        -- `weaponsAnswersThatSpendAReading`.
        weaponsNow : WeaponsStep
        weaponsNow =
            weaponsStepFromReading
                friendlyFireNow
                botMemoryBefore.weaponsAskedReadings
                context.readingFromGameClient

        -- The same arrangement once more, and #408 is why this counter exists
        -- at all: the arm it bounds answered `Just` on every reading a
        -- propulsion module read on and the ship was not approaching, and
        -- nothing below it ran for whole sessions.
        middleRowNow : MiddleRowStep
        middleRowNow =
            middleRowStepFromReading
                botMemoryBefore.middleRowAskedReadings
                context.readingFromGameClient

        -- Written here rather than where the box is answered, because the
        -- branch that would keep the count is the branch that stops running the
        -- moment the count reaches its bound. It counts readings a box was in
        -- front of the bot with no reference to what the bot managed to do with
        -- them, which is what the bound is about -- a clock that stopped while
        -- the tree was held is not a clock. See `MessageBoxStandoff`.
        messageBoxStandoff : Maybe MessageBoxStandoff
        messageBoxStandoff =
            messageBoxStandoffAfterReading
                { before = botMemoryBefore.messageBoxStandoff
                , identityNow =
                    context.readingFromGameClient.messageBoxes
                        |> List.head
                        |> Maybe.map messageBoxIdentity
                }

        -- Said on the reading the give-up is reached and on no other. The bound
        -- is crossed once, because the count only ever rises while one box
        -- stays.
        messageBoxLastChange : Maybe String
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
    , fleetBroadcastSeen =
        fleetTravelBroadcastAnyPilot context.readingFromGameClient |> Maybe.map .banner
    , fleetBroadcastFollowed =
        case fleetTravelBroadcastAnyPilot context.readingFromGameClient |> Maybe.map .banner of
            Nothing ->
                botMemoryBefore.fleetBroadcastFollowed

            Just banner ->
                if botMemoryBefore.fleetBroadcastSeen == Just banner then
                    Just banner

                else
                    botMemoryBefore.fleetBroadcastFollowed
    , calledTargetGone =
        calledTargetGoneAfterReading
            botMemoryBefore.calledTargetGone
            (calledTargetWithNoOverviewRow
                context.botSettings.followFleetBroadcastFrom
                context.readingFromGameClient
            )
    , bannerCtrlClick =
        -- #366. The rule the arm itself asks, rather than a restatement of when
        -- it might have asked -- `calledTargetGone` above takes the same shape
        -- and #389 is what the other one cost.
        bannerCtrlClickAfterReading
            botMemoryBefore.bannerCtrlClick
            (bannerCtrlClickThisReading
                { followFleetBroadcastFrom = context.botSettings.followFleetBroadcastFrom
                , calledTargetGone = botMemoryBefore.calledTargetGone
                , bannerCtrlClick = botMemoryBefore.bannerCtrlClick
                }
                context.readingFromGameClient
            )
    , goToFleetMatePlaceSeen =
        fleetMatePlaceAnyPilot context.readingFromGameClient
    , goToFleetMateDestinationAsked =
        case fleetMatePlaceAnyPilot context.readingFromGameClient of
            Nothing ->
                botMemoryBefore.goToFleetMateDestinationAsked

            Just place ->
                if botMemoryBefore.goToFleetMatePlaceSeen == Just place then
                    Just place

                else
                    botMemoryBefore.goToFleetMateDestinationAsked
    , goToFleetMateWarpAskedReadings =
        if fleetMateOnThisGrid == Nothing then
            0

        else if fleetMateWarpHasBeenGivenUpOn botMemoryBefore.goToFleetMateWarpAskedReadings then
            -- Held rather than advanced, `unlockFleetPilotAskedReadings`'s own
            -- arrangement: the mate is still there and this bot has stopped
            -- asking, and a counter that ran away would make the status line's
            -- "after N readings" meaningless.
            botMemoryBefore.goToFleetMateWarpAskedReadings

        else
            botMemoryBefore.goToFleetMateWarpAskedReadings + 1
    , routeFirstMarkerRegion = currentRouteFirstMarkerRegion
    , routeFirstMarkerUnchangedTicks =
        if currentRouteFirstMarkerRegion == Nothing then
            0

        else if currentRouteFirstMarkerRegion == botMemoryBefore.routeFirstMarkerRegion then
            botMemoryBefore.routeFirstMarkerUnchangedTicks + 1

        else
            0
    , gateAskedReadings =
        if askingTheGateToOpen then
            botMemoryBefore.gateAskedReadings + 1

        else if gateOnOverview /= Nothing then
            botMemoryBefore.gateAskedReadings

        else
            0
    , calledGateRecallAskedReadings =
        calledGateRecallAskedReadingsAfter
            { askedThisReading = askingForTheCalledGateRecall
            , dronesInSpaceNow = dronesInSpaceCountFromReading context.readingFromGameClient
            , dronesInSpaceBefore = botMemoryBefore.dronesInSpaceCountLastReading
            , before = botMemoryBefore.calledGateRecallAskedReadings
            }
    , dronesInSpaceCountLastReading =
        dronesInSpaceCountFromReading context.readingFromGameClient
    , weaponsAskedReadings =
        if List.isEmpty context.readingFromGameClient.targets then
            -- An empty lock bar ends the episode, so the next fight starts on
            -- a fresh allowance rather than inheriting the last one's.
            0

        else if List.member weaponsNow weaponsAnswersThatSpendAReading then
            botMemoryBefore.weaponsAskedReadings + 1

        else
            -- Held rather than advanced, `unlockFleetPilotAskedReadings`'s own
            -- arrangement: something is still locked and this arm did not ask
            -- this reading, and a counter that ran away would make the status
            -- line's "after N readings" meaningless -- which is exactly what
            -- #389 read off three pilots at 46, 36 and 50 against a bound
            -- of 20.
            botMemoryBefore.weaponsAskedReadings
    , hitpoints = hitpointsNow
    , lowestShieldPercentSinceHealthy = lowestShieldNow
    , lowestArmorPercentSinceHealthy = lowestArmorNow
    , incomingDamage = incomingDamageNow
    , retreatAskedReadings =
        if not retreatIsDecided then
            0

        else if shipIsWarping == Just True then
            -- The ship is leaving, so the retreat is executing however long the
            -- verdict stays latched afterwards. `retreatProgressAfterReading`'s
            -- own rule, and the reason a slow-but-working retreat is not
            -- charged for its own warp.
            0

        else
            botMemoryBefore.retreatAskedReadings + 1
    , recoveringFromRetreat = recoveringFromRetreatNow
    , fleetPlaceBroadcast = fleetPlaceBroadcastNow
    , retreatRecoveryAskedReadings =
        if recoveringStepNow == NotRecoveringFromARetreat then
            -- The episode is over -- the ship is back with its commander, or a
            -- fresh retreat has not started one yet. A second retreat gets a
            -- fresh budget; one recovery does not get two.
            0

        else if retreatIsDecided then
            -- **The retreat is still holding the tree**, so `recoverFromRetreat`
            -- cannot have been reached on this reading whatever the rule
            -- answers -- `retreatToTheCommander` sits directly above it and
            -- answers `Just` on every reading its verdict is latched. Charging
            -- these is #389 exactly: a budget spent on asks nobody made, and
            -- worse here than there, because `recoveringFromRetreat` is set on
            -- the reading the retreat is *decided* and the verdict then latches
            -- until the gauge recovers past `runAwayRearmPercent`. A retreat
            -- long enough to spend thirty readings out of warp -- the mission
            -- runner's corpus has one at 44 -- would hand the recovery a budget
            -- already gone and a give-up on its first reading.
            --
            -- Reset rather than held, because the recovery has not begun: the
            -- reading the retreat clears is the reading this arm first gets,
            -- and it gets the whole allowance.
            0

        else if recoveringStepNow == AlreadyOnTheWayBackToTheCommander then
            -- The ship is warping or jumping, so the recovery is executing
            -- however long it takes -- `retreatAskedReadings`' own rule, and
            -- what keeps a legitimate multi-jump route off a bound sized for a
            -- cascade. It cannot undo a spent budget, because the rule asks the
            -- give-up before it asks this.
            0

        else if List.member recoveringStepNow retreatRecoveryAnswersThatSpendAReading then
            botMemoryBefore.retreatRecoveryAskedReadings + 1

        else
            -- Held rather than advanced, `goToFleetMateWarpAskedReadings`'s own
            -- arrangement: this ship is still away from its commander and this
            -- arm did not ask this reading. Holding is also what makes the
            -- give-up stick -- a reset here would un-give-up on the very next
            -- reading -- and it keeps the status line's "after N readings"
            -- meaningful, which is #389's own lesson.
            botMemoryBefore.retreatRecoveryAskedReadings
    , panelSelectUnansweredReadings =
        -- Readings in a row the panel has not come to show the object to orbit.
        -- Asked through `objectToOrbitFromReading`, the rule the arm itself
        -- asks, rather than restated here: a counter advanced by one condition
        -- and read by another is #102's defect.
        panelSelectReadingsAfterReading
            { asking =
                askingThePanelToShowTheObjectToOrbit
                    { orbitObjectNames = context.botSettings.orbitObjectNames
                    , prioritizeRats = context.botSettings.prioritizeRats
                    }
                    context.readingFromGameClient
            , before = botMemoryBefore.panelSelectUnansweredReadings
            }
    , approachFleetCommanderAskedReadings =
        if askingTheCommanderForAnApproach then
            botMemoryBefore.approachFleetCommanderAskedReadings + 1

        else if commanderIsOnGrid && not shipIsApproachingNow then
            botMemoryBefore.approachFleetCommanderAskedReadings

        else
            0
    , closingOnTheCommanderSinceLanding = closingOnTheCommanderSinceLandingNow
    , backupCallAskedReadings =
        case answeringABackupCall of
            Nothing ->
                -- No backup call on this reading at all: the next one starts
                -- from a full budget.
                0

            Just { step } ->
                if List.member step backupCallAnswersThatSpendAReading then
                    botMemoryBefore.backupCallAskedReadings + 1

                else if step == GaveUpOnTheBackupCall then
                    -- Held rather than advanced, `unlockFleetPilotAskedReadings`'s
                    -- own arrangement: the call is still up and this bot has
                    -- stopped trying, and a counter that ran away would make the
                    -- status line's "after N readings" meaningless.
                    botMemoryBefore.backupCallAskedReadings

                else
                    -- A call this ship is not answering, or one it is already on
                    -- its way to. Neither spent a reading, so neither may spend
                    -- the budget -- and a ship that has arrived and is
                    -- approaching gets the whole allowance again if the caller
                    -- moves off the grid.
                    0
    , unlockFleetPilotAskedReadings =
        case friendlyFireNow of
            UnlockAFleetPilot _ signal ->
                if targetBarSawThePilot signal then
                    botMemoryBefore.unlockFleetPilotAskedReadings + 1

                else
                    -- Held for the same reason as the give-up below, and for
                    -- #389's: only the overview row saw this pilot, so there is
                    -- no bar entry for `unlockFleetPilotInTargetBar` to
                    -- right-click and no ask goes out. A budget charged for
                    -- asks nobody made reports a give-up on an arm that was
                    -- never reached.
                    botMemoryBefore.unlockFleetPilotAskedReadings

            GaveUpUnlockingAFleetPilot _ _ ->
                -- Held rather than advanced: the pilot is still locked and the
                -- guns are still refused, and a counter that ran away would
                -- make the status line's "after N readings" meaningless.
                botMemoryBefore.unlockFleetPilotAskedReadings

            NothingIsLocked ->
                0

            HoldFireOnAnUnverifiedPilot _ _ ->
                0

            ClearToFire ->
                0
    , middleRowAskedReadings =
        if List.member middleRowNow middleRowAnswersThatSpendAReading then
            botMemoryBefore.middleRowAskedReadings + 1

        else if middleRowNow == GaveUpOnTheMiddleRow then
            -- Held rather than advanced, `unlockFleetPilotAskedReadings`'s own
            -- arrangement: the row is still wrong and this bot has stopped
            -- clicking at it, and a counter that ran away would make the status
            -- line's "after N readings" meaningless.
            botMemoryBefore.middleRowAskedReadings

        else
            -- Every answer that declined to click, and `MiddleRowNeedsNothing`
            -- with it. The last of those is what ends an episode here: a ship
            -- that starts approaching again wants the module it already has
            -- running, so the row needs nothing and the next stretch of
            -- not-approaching gets the whole allowance back.
            0
    , messageBoxStandoff = messageBoxStandoff
    , messageBoxLastChange = messageBoxLastChange
    }


{-| The values this gauge is allowed to have at all.

`ShipUI.hitpointsPercent` is `gauge._lastValue * 100` scraped out of the
client's live memory while the client is mutating it, and across the mission
runner's recorded runs it has produced -1021821%, 2132822% and 8362%, always
for exactly one reading and always surrounded by sane values. This rejects the
impossible ones; nothing can reject a garbage value that lands inside [0, 100],
which is what `updateHitpointsGaugeMemory` is for.

-}
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
    }


{-| Fold one reading into what this gauge is willing to be believed about.

`believed` is the healthier of the last two believable readings, so a drop has
to survive a second look before the low-water mark or the retreat sees it. A
single corrupt reading of `0` is as reachable as one of `21328.22` and is the
worst value to be wrong about, since it clears every threshold at once: the
mission runner's run 11 printed `Armor reached 0%` forty times with the armour
really at 82-96%.

An unbelievable value -- or a reading with no ship UI at all -- is `Nothing`
here and leaves `Nothing` behind for the next reading to confirm against, which
is what stops values either side of a gap in the gauge vouching for each other.

**It delays; it cannot suppress.** On any non-increasing series the believed
value is the previous reading's, whatever the size of the step, so a hull
losing armour retreats one reading later than it used to and a hull genuinely
at 0% still retreats.

-}
updateHitpointsGaugeMemory : Maybe Int -> HitpointsGaugeMemory -> HitpointsGaugeMemory
updateHitpointsGaugeMemory reading memoryBefore =
    { previousReading = reading
    , believed =
        case memoryBefore.previousReading of
            -- Nothing to confirm against: the session's first reading, or the
            -- one after a gap. The reading stands on its own rather than being
            -- withheld indefinitely -- a gauge readable only every other
            -- reading would otherwise never be believed at all, and a hull
            -- really at 0% would never retreat.
            Nothing ->
                reading

            Just previous ->
                reading |> Maybe.map (max previous)
    }


{-| The lowest believed value seen, until the ship recovers or docks.

Docking forgets outright -- there is no ship UI to read and the next undock is
a fresh hull. In space it is kept until the gauge reads at or above
`runAwayRearmPercent`, which is what gives the retreat hysteresis: without it a
single live threshold flips back the moment a repairer catches up, and the ship
oscillates between fleeing and returning.

Takes what a reading says about the ship UI rather than the reading, so a case
can execute it -- the shape `weaponsStep` and `accelerationGateActivationStep`
already use in this file.

-}
lowWaterMarkAfterReading : { shipUIIsShowing : Bool, believed : Maybe Int, previous : Int } -> Int
lowWaterMarkAfterReading markCase =
    if not markCase.shipUIIsShowing then
        100

    else
        case markCase.believed of
            Nothing ->
                markCase.previous

            Just current ->
                if runAwayRearmPercent <= current then
                    100

                else
                    min markCase.previous current


{-| Where the mark is released. Above every sane trip level, or it would never
release at all.
-}
runAwayRearmPercent : Int
runAwayRearmPercent =
    90


{-| The low-water mark the retreat compares, folding in this reading's own value.

The mark alone is one reading behind: `lowWaterMarkAfterReading` folds a
reading in after the decision has read it, so a gauge that has just dropped is
not in the mark yet. Taking the `min` of the two is what makes the retreat act
on the reading the drop arrives on rather than the one after.

-}
lowestPercentSinceHealthy : Maybe Int -> Int -> Int
lowestPercentSinceHealthy believed markSinceHealthy =
    believed
        |> Maybe.map (\current -> min current markSinceHealthy)
        |> Maybe.withDefault markSinceHealthy


incomingDamageInWindow : IncomingDamageMemory -> Int
incomingDamageInWindow memory =
    memory.samples |> List.map .damage |> List.sum


{-| The window the damage guard sums over.

45 seconds is where the mission runner's corpus put the separation widest: at
four minutes the worst session the ship survived and the one it was lost in are
8689 against 9286, which no threshold could tell apart.

-}
incomingDamageWindowSeconds : Int
incomingDamageWindowSeconds =
    45


incomingDamageSampleLimit : Int
incomingDamageSampleLimit =
    200


{-| Fold this reading's combat-log total into the rolling window, and latch.

**The latch is the point, not the live comparison.** The moment the ship warps
clear, the window starts draining -- so a guard that re-asked "is the window
still over the threshold" on every reading would cancel its own retreat
halfway through it. Released only by a window that is completely empty.

-}
updateIncomingDamageMemory : UpdateMemoryContext BotSettings -> IncomingDamageMemory -> IncomingDamageMemory
updateIncomingDamageMemory context memoryBefore =
    let
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
                    }
                        :: keptSamples

        updated =
            { samples = samples
            , hostCarriesTheChannel =
                context.readingFromGameClient.incomingDamageSinceLastReading /= Nothing
            , retreating = memoryBefore.retreating
            }
    in
    { updated
        | retreating =
            incomingDamageLatchAfterReading
                { damageInWindow = incomingDamageInWindow updated
                , threshold = context.botSettings.runAwayIncomingDamageThreshold
                , latchedBefore = memoryBefore.retreating
                }
    }


{-| The damage guard's verdict after one more reading, as a rule a case can run.

Set once the window reaches the threshold, released only by a window that is
completely empty, and never set at all by a negative threshold -- which is what
`-1` means and what this bot ships with.

-}
incomingDamageLatchAfterReading : { damageInWindow : Int, threshold : Int, latchedBefore : Bool } -> Bool
incomingDamageLatchAfterReading latchCase =
    if latchCase.damageInWindow <= 0 then
        False

    else if 0 <= latchCase.threshold && latchCase.threshold <= latchCase.damageInWindow then
        True

    else
        latchCase.latchedBefore


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


{-| The default station this bot flies home to when the session is ending.
-}
defaultHomeStation : String
defaultHomeStation =
    "Amarr VIII (Oris) - Emperor Family Academy"


{-| A settings value that may name several pilots at once.

`accept-fleet-invite-from=Gal Bistot, Olivia Ochre` and two separate lines mean
the same thing, which is what the rest of this repo's list settings already do.

-}
splitSettingIntoNames : String -> List String
splitSettingIntoNames settingValue =
    settingValue
        |> String.split ","
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)


{-| Every node under the fleet window.

**Scoped, and that is the whole point.** `entryLabel` is not the fleet window's
private name: the drones window uses it for its own status rows, and reading it
tree-wide grabbed a drone's row instead of the broadcast text during exactly the
readings a call is most likely to be genuine. Scoping to the fleet window is
what #329 fixed that with, and this carries the fix rather than repeating the
bug.

-}
fleetWindowDescendants : ReadingFromGameClient -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
fleetWindowDescendants readingFromGameClient =
    readingFromGameClient.fleetWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []


{-| What the broadcast banner currently says, if anything.

**The banner persists.** It is a _last broadcast_ display rather than a
transient -- observed still reading `Gal Bistot: Travel to Riramia` long after
that broadcast -- so this answers what it says now and nothing about when it was
said. Acting on it once is the caller's job, not this one's.

-}
fleetBroadcastBannerText : ReadingFromGameClient -> Maybe String
fleetBroadcastBannerText readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "bannerLabel")
            )
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.head


{-| The broadcast history, newest first, with the timestamp prefix removed.

The prefix is the discriminator, not decoration: `entryLabel` inside the fleet
window serves both the member rows (`Greta Gneiss`) and the history
(`02:59:30 - Target Heather Hemorphite (Tristan)`), and only the `HH:MM:SS -`
tells them apart.

-}
fleetBroadcastHistoryEntries : ReadingFromGameClient -> List String
fleetBroadcastHistoryEntries readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "entryLabel")
            )
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.filterMap textAfterBroadcastTimestamp


{-| The text of a broadcast history line, or `Nothing` if it is not one.

`02:59:30 - Target Heather Hemorphite (Tristan)` answers
`Target Heather Hemorphite (Tristan)`; a bare member row answers `Nothing`.

-}
textAfterBroadcastTimestamp : String -> Maybe String
textAfterBroadcastTimestamp entryText =
    case String.split " - " entryText of
        timestamp :: rest ->
            let
                looksLikeTimestamp : Bool
                looksLikeTimestamp =
                    (String.length (String.trim timestamp) == 8)
                        && (String.trim timestamp
                                |> String.toList
                                |> List.all (\c -> Char.isDigit c || c == ':')
                           )
            in
            if looksLikeTimestamp && rest /= [] then
                Just (String.join " - " rest |> String.trim)

            else
                Nothing

        [] ->
            Nothing


{-| The pilots the fleet window lists as members, and the commander.

**The member rows are not the whole fleet.** The window read
`Fleet (5)` while carrying four `FleetMember` rows -- Greta Gneiss, Heather
Hemorphite, Joan d'Arkonor, Olivia Ochre -- because the fifth, the boss, is
drawn in the header instead. A guard that reads only the rows therefore misses
the commander, which is the one pilot it is most important not to shoot at.

Captured from the live client rather than assumed; see `fleetCommanderName`.

-}
fleetMemberNames : ReadingFromGameClient -> List String
fleetMemberNames readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "entryLabel")
            )
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.filter (textAfterBroadcastTimestamp >> (==) Nothing)
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)


{-| The pilots local chat's own standing icons mark as fleetmates.

The client answers this per pilot, in real time, with no window open -- it is
the same `Pilot is in your fleet` hint `getNamesOfOtherPilotsInOverview`
already filters _out_, read here for who it names rather than for who it
excludes. #367 is what put it on this side: with the Fleet window shut, a
fleetmate the icon does mark would otherwise have been absent from
`fleetPilotNames` _and_ absent from the overview's "other pilots" list, which
is the one combination that reads as "a stranger, shoot away".

**It adds names and cannot certify a list.** `chatUserIsKnownFleetmate`
answers `False` for a row with no hint at all -- deliberately, so absent
evidence never reads as "fleetmate" -- so a fleet whose icons this bot cannot
resolve looks exactly like no fleet. That is why `fleetMembershipIsVerifiable`
asks the Fleet window and not this.

-}
fleetmateNamesFromLocalChat : ReadingFromGameClient -> List String
fleetmateNamesFromLocalChat readingFromGameClient =
    readingFromGameClient
        |> localChatWindowFromUserInterface
        |> Maybe.andThen .userlist
        |> Maybe.map .visibleUsers
        |> Maybe.withDefault []
        |> List.filter chatUserIsKnownFleetmate
        |> List.filterMap .name


{-| The size the Fleet window's own header states, if it states one.

The captured header carries `Fleet (5)` beside the boss's name and the wing and
squad labels -- see `fleetCommanderNameFromFleetWindowHeader`, which reads the
same node and keeps the label _without_ a parenthesis while this one wants the
one that opens with `Fleet (`.

**`fleetSizeStatedMarker` is the one constant both the match and the slice use**,
so a number can never be extracted out of a label the match would have rejected
-- `gateKeyClosingMarker`'s arrangement in the mission runner, for its reason.

`Nothing` is "this header states no size" and is never a zero: it is what makes
`FleetSizeNotStated` a case of its own rather than a roster that reads complete
because nothing contradicted it.

-}
fleetSizeStatedByFleetWindowHeader : ReadingFromGameClient -> Maybe Int
fleetSizeStatedByFleetWindowHeader readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> .pythonObjectTypeName
                >> String.contains "FleetHeader"
            )
        |> List.concatMap
            EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.map String.trim
        |> List.filterMap fleetSizeFromHeaderLabel
        |> List.head


{-| The marker the size label opens with, shared by the match and the slice.
-}
fleetSizeStatedMarker : String
fleetSizeStatedMarker =
    "Fleet ("


fleetSizeFromHeaderLabel : String -> Maybe Int
fleetSizeFromHeaderLabel label =
    if String.startsWith fleetSizeStatedMarker label && String.endsWith ")" label then
        label
            |> String.dropLeft (String.length fleetSizeStatedMarker)
            |> String.dropRight 1
            |> String.trim
            |> String.toInt

    else
        Nothing


{-| What this reading can say about the completeness of the no-shoot list.
-}
type FleetRosterVerdict
    = FleetWindowIsShut
    | FleetSizeNotStated
    | RosterIsShort { statedSize : Int, resolvedPilots : Int }
    | RosterIsComplete { statedSize : Int, resolvedPilots : Int }


{-| Whether anything on this reading is in a position to answer "who is in
this fleet" completely.

**The distinction this whole guard rests on.** `fleetMemberNames` answers `[]`
for a fleet of forty whose window is shut exactly as it does for a pilot flying
alone, and `List.member` over `[]` is `False` for everybody -- so a guard that
only asked `fleetPilotNames` would pass every target through and look
identical to a guard that had checked. While membership is unverifiable
`friendlyFireStep` refuses to fire on any _pilot_ rather than inferring anything
from silence.

**The window's presence is not that answer, and #380 is the reading that says
so.** Four wingmen read the same fleet at the same moment and reported member
rows of 0, 2, 4 and 4; Greta read **zero rows and zero chat icons with the
window open**, in a four-pilot fleet, with a target locked -- and the guard
concluded it had checked, found nobody, and reported `clear to fire`. A
fleetmate missing from that list is one she would shoot while the status line
says membership was verified.

**Corroborating the rows against local chat's icons does not catch it**, which
is why #380's own two shapes are both declined here: Greta's two sources
_agree_, at zero, so a rule that treats disagreement as unverified verifies
exactly the reading the issue was filed on. Kara's 2-against-4 is caught by
either, and the union in `fleetPilotNamesFromReading` already folds her chat
icons in.

**The window states its own size, and that is the third instrument.** The
captured header reads `Fleet (5)` beside four member rows, the boss being drawn
in the header instead. So the roster is corroborated when the bot resolved at
least as many _distinct_ pilots as the window says there are, and short
otherwise -- which does not need to know **why** the rows differ. Every
candidate #380 names (a collapsed or scrolled window, a fleet in wings and
squads with only some branches expanded, a parse that depends on window size)
makes the rows a subset of the fleet, and a count catches a subset however it
came about.

**A fleet of one still verifies**, which requiring a non-empty row count would
have broken: the header states 1, the boss is the pilot themselves, one name is
resolved, and the roster is complete. Greta's reading states 5 against 1
resolved and is short. Those two readings are identical in rows and in chat
icons, so the stated size is the only thing on the reading that separates them.

**Both kinds of not-knowing refuse**, which is `loadRefusalFromGameLog`'s
register: a window that is shut and a header that states no size are each
"this reading cannot answer", never "the roster is complete". Refusing to fire
is cheap here -- this bot shoots rats, `getNamesOfOtherPilotsInOverview` never
holds an NPC, and a pilot is a rare target -- and firing on a fleetmate is what
#367 exists to prevent.

-}
fleetRosterVerdict : List String -> ReadingFromGameClient -> FleetRosterVerdict
fleetRosterVerdict followFleetBroadcastFrom readingFromGameClient =
    if readingFromGameClient.fleetWindow == Nothing then
        FleetWindowIsShut

    else
        case fleetSizeStatedByFleetWindowHeader readingFromGameClient of
            Nothing ->
                FleetSizeNotStated

            Just statedSize ->
                let
                    resolvedPilots : Int
                    resolvedPilots =
                        fleetPilotNamesFromReading followFleetBroadcastFrom readingFromGameClient
                            |> List.map String.toLower
                            |> Set.fromList
                            |> Set.size
                in
                if resolvedPilots < statedSize then
                    RosterIsShort { statedSize = statedSize, resolvedPilots = resolvedPilots }

                else
                    RosterIsComplete { statedSize = statedSize, resolvedPilots = resolvedPilots }


{-| Whether the verdict above lets an empty membership list mean "nobody".

Only `RosterIsComplete` does. The three others are the reading saying it cannot
answer, and the guard holds fire on any recognised pilot for each of them.

-}
fleetRosterIsCorroborated : FleetRosterVerdict -> Bool
fleetRosterIsCorroborated verdict =
    case verdict of
        FleetWindowIsShut ->
            False

        FleetSizeNotStated ->
            False

        RosterIsShort _ ->
            False

        RosterIsComplete _ ->
            True


fleetMembershipIsVerifiable : List String -> ReadingFromGameClient -> Bool
fleetMembershipIsVerifiable followFleetBroadcastFrom readingFromGameClient =
    fleetRosterIsCorroborated
        (fleetRosterVerdict followFleetBroadcastFrom readingFromGameClient)


{-| Everyone this bot must not shoot: the member rows, the commander, and
whoever local chat's standing icons mark as a fleetmate.

Empty names are dropped because the matcher contains rather than equals, and
`""` is contained in every target's text -- an empty entry would answer "that
is a fleetmate" for the whole lock bar.

-}
fleetPilotNamesFromReading : List String -> ReadingFromGameClient -> List String
fleetPilotNamesFromReading followFleetBroadcastFrom readingFromGameClient =
    [ fleetMemberNames readingFromGameClient
    , fleetCommanderNameFromReading followFleetBroadcastFrom readingFromGameClient
        |> Maybe.map List.singleton
        |> Maybe.withDefault []
    , fleetmateNamesFromLocalChat readingFromGameClient
    ]
        |> List.concat
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)


fleetPilotNames : BotDecisionContext -> List String
fleetPilotNames context =
    fleetPilotNamesFromReading
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.readingFromGameClient


{-| Who the fleet commander is: the fleet window's own header, and the
`follow-fleet-broadcast-from` setting only when the header gives no answer.

**This is #367's unification and there used to be three of these.** The header
read landed with #365's orbit as `fleetCommanderNameFromPanel`, while this
function stayed settings-only and #364's `retreatToTheCommander` ran to it --
so on a reading where the window named one pilot and the setting named another,
the retreat and the orbit were about different ships. Preferring the header
here and deleting the panel sibling leaves two: this one, and
`fleetCommanderNameFromFleetWindowHeader`, which is the header half alone and
exists because `updateMemoryForNewReadingFromGame`'s
`fleetCommanderOverviewEntry` asks the question over a reading.

**It also fixes what #369 flagged rather than only tidying names.** The retreat
used to answer `Nothing` whenever `follow-fleet-broadcast-from` was unset,
which is a break-off decided with nowhere to run to; a fleet window that is
open now answers it whether or not the operator filled the setting in.

The header inference is stated in `fleetCommanderNameFromFleetWindowHeader` and
is not repeated here.

-}
fleetCommanderNameFromReading : List String -> ReadingFromGameClient -> Maybe String
fleetCommanderNameFromReading followFleetBroadcastFrom readingFromGameClient =
    case fleetCommanderNameFromFleetWindowHeader readingFromGameClient of
        Just fromHeader ->
            Just fromHeader

        Nothing ->
            List.head followFleetBroadcastFrom


fleetCommanderName : BotDecisionContext -> Maybe String
fleetCommanderName context =
    fleetCommanderNameFromReading
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.readingFromGameClient


{-| The target a `Target` broadcast names, if the current banner is one.

    Target Heather Hemorphite (Tristan)  ->  Just "Heather Hemorphite"

**The ship type is dropped.** The broadcast names the target and its hull in
parentheses, and it is the pilot name that matches an overview row.

**It carries no sender**, unlike a travel broadcast (`Gal Bistot: Travel to
Riramia`), so `follow-fleet-broadcast-from` cannot filter it. Anyone in the
fleet can call a target; the trust is in `accept-fleet-invite-from`.

-}
targetBroadcastPilotName : String -> Maybe String
targetBroadcastPilotName broadcastText =
    if String.startsWith "Target " broadcastText then
        broadcastText
            |> String.dropLeft (String.length "Target ")
            |> String.split "("
            |> List.head
            |> Maybe.map String.trim
            |> Maybe.andThen
                (\name ->
                    if String.isEmpty name then
                        Nothing

                    else
                        Just name
                )

    else
        Nothing


{-| The broadcasts the fleet window offers that nothing here reads yet.

Enumerated from the window's own `BroadcastButton` tooltips, so the list is the
client's rather than a guess. **What is missing is how each one renders** once
broadcast: the button says `Broadcast: Spotted an Enemy` and the history says
something else. A capture pass -- one click per button, then read the history
panel -- is what turns these into matchable strings.

**Three names left this list in #385, and the first of them is why that issue
exists.** `parseBroadcastVerb` claimed to read `Need Backup` while it was still
listed here, so one of the two was wrong on every reading -- and it was the
matcher, which carried the button's first-person `need backup` against a banner
that renders `needs backup`. `At Location` and `In Position at` were the same
disagreement with the halves the other way round: `parseFleetBroadcast` has read
`<Sender> is at location <system>` and
`<Sender> is in position at Stargate <name>` since those wordings were captured
live, and `actOnBroadcastVerb` acts on both, while this list went on calling
them unread. A list that names a verb the parser reads is a list nobody can
check the parser against, which is what let one wrong matcher sit here
unnoticed.

**The five that remain are named on a button and have never been seen
rendered.** `Need Armor`, `Need Capacitor`, `Need Shield`,
`Request That the Fleet Hold Position` and `Spotted an Enemy` -- and wiring any
of them from the button's wording is exactly the mistake this list exists to
record. Note also that the live vocabulary is _wider_ than the buttons:
`Jump Stargate` and `Align Stargate` were observed in real runs, are matched,
and are on no button at all.

-}
broadcastVerbsNotYetRead : List String
broadcastVerbsNotYetRead =
    [ "Need Armor"
    , "Need Capacitor"
    , "Need Shield"
    , "Request That the Fleet Hold Position"
    , "Spotted an Enemy"
    ]


{-| The client's own wording for a fleet travel broadcast, ported from
`eve-online-saxrat`'s `fleetTravelBroadcastMarker` -- captured live on this same
account: `Gal Bistot: Travel to Riramia`. An infix marker rather than a prefix
one, so it reads correctly off both the timestamped history panel
(`02:31:32 - Gal Bistot: Travel to Riramia`) and the plain persistent banner
(`Gal Bistot: Travel to Bhizheba`) with no separate handling for either shape --
`actOnFleetBroadcast` had no travel-form matcher at all before this, despite
`WINGMAN.md` and this file's own header both listing it as one of the two forms
already read: the header's example was one of the timestamped-history captures,
and the live banner this bot actually decides from carries no timestamp.
-}
fleetTravelBroadcastMarker : String
fleetTravelBroadcastMarker =
    ": Travel to "


fleetTravelBroadcastFromBannerText : String -> Maybe { pilot : String, system : String, banner : String }
fleetTravelBroadcastFromBannerText banner =
    case String.indexes fleetTravelBroadcastMarker banner of
        [] ->
            Nothing

        index :: _ ->
            let
                pilot : String
                pilot =
                    banner |> String.left index |> String.trim

                system : String
                system =
                    banner
                        |> String.dropLeft (index + String.length fleetTravelBroadcastMarker)
                        |> String.trim
            in
            if String.isEmpty pilot || String.isEmpty system then
                Nothing

            else
                Just { pilot = pilot, system = system, banner = banner }


{-| Whoever broadcast a travel destination, and where to, with no permission
filter.

**Unfiltered on purpose.** This is what the memory update latches
(`fleetBroadcastSeen` / `fleetBroadcastFollowed`) to stop the banner asking for
the same route on every reading for the rest of the session, and the memory
update cannot filter by `follow-fleet-broadcast-from`: `UpdateMemoryContext`
here carries no settings at all -- `eve-online-saxrat`'s copy of
`EveOnline.BotFrameworkSeparatingMemory` was extended to parameterize it with
`BotSettings` for exactly this, and this freshly-vendored copy was not.
Permission is checked instead in `fleetTravelBroadcast` below, which is what
`actOnFleetBroadcast` actually calls -- the trust stays exactly where the
setting's own documentation says it is, and an unpermitted sender's broadcast
can latch here harmlessly, since nothing ever compares this latch against an
unpermitted broadcast's text.

-}
fleetTravelBroadcastAnyPilot : ReadingFromGameClient -> Maybe { pilot : String, system : String, banner : String }
fleetTravelBroadcastAnyPilot readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen fleetTravelBroadcastFromBannerText


{-| Wherever an `AtLocation`/`InPositionAt` broadcast currently names, with no
permission filter -- `fleetTravelBroadcastAnyPilot`'s own reason:
`UpdateMemoryContext` carries no `BotSettings`, so the memory update cannot
check `follow-fleet-broadcast-from`, and an unpermitted broadcast latching
this harmlessly is what `fleetBroadcastFollowed`'s own comment already
accepts for the travel form. `goToFleetMate` itself is only ever called for a
permitted pilot, so what this latch decides -- ask once, then fly -- is never
compared against a place an unpermitted sender named.
-}
fleetMatePlaceAnyPilot : ReadingFromGameClient -> Maybe String
fleetMatePlaceAnyPilot readingFromGameClient =
    case fleetBroadcastBannerText readingFromGameClient of
        Nothing ->
            Nothing

        Just bannerText ->
            case parseFleetBroadcast bannerText of
                AtLocation { system } ->
                    Just system

                InPositionAt { gate } ->
                    Just gate

                _ ->
                    Nothing


{-| Every place a broadcast can name, with whoever named it -- the three forms
that carry one, in one answer.

`fleetMatePlaceAnyPilot` above is deliberately **not** this function narrowed:
it answers the two _company_ verbs only, because what it feeds
(`goToFleetMateDestinationAsked`) is the ask that goes out when a mate calls
this ship to them, and a travel broadcast is not that call -- it reaches
`actOnFleetBroadcast`'s own branch. This one answers "where did anybody last
say they were", which is a different question with a different consumer
(`recoverFromRetreat`), and the Olivia reading in #381 is why it has to include
`TravelTo`: the place that was demonstrably available on the very reading three
wingmen had nothing to fly to was `Gal Bistot: Travel to Madirmilire`.

Both drop the pilot's own ship type and neither trims anything else -- the place
is handed to `@host set-destination` and to ESI beyond it, so a normalisation
applied here is one nothing downstream can undo.

-}
fleetPlaceBroadcastAnyPilot : ReadingFromGameClient -> Maybe { pilot : String, place : String }
fleetPlaceBroadcastAnyPilot readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen
            (\bannerText ->
                case parseFleetBroadcast bannerText of
                    TravelTo { pilot, destination } ->
                        Just { pilot = pilot, place = destination }

                    AtLocation { pilot, system } ->
                        Just { pilot = pilot, place = system }

                    InPositionAt { pilot, gate } ->
                        Just { pilot = pilot, place = gate }

                    _ ->
                        Nothing
            )
        |> Maybe.andThen
            (\seen ->
                if String.isEmpty seen.pilot || String.isEmpty seen.place then
                    Nothing

                else
                    Just seen
            )


{-| What this ship remembers about where its fleet last said it was, after one
reading.

Three rules, and the second is the one that keeps a remembered place from
outliving its usefulness silently:

  - **A place named on this reading replaces whatever was remembered**, whoever
    named it. Latest wins, and the decision -- not this -- is what refuses a
    place the commander did not name; see `fleetPlaceBroadcast`'s own comment.
    That the new place can be somebody else's is a real cost: Olivia broadcasting
    `is in position at` displaces the commander's travel destination, and the
    recovery then has nothing and gives up rather than routing somewhere
    arbitrary, which is the refusal `goToFleetMate`'s own doc comment already
    makes.

  - **The reunion drops it.** On the reading the commander gets an overview row
    -- the same reading `recoveringFromRetreat` clears -- wherever he last said
    he was is superseded by his being right there. So no place this arm ever
    routes to was broadcast before the last time this ship was with its
    commander, which is the invalidation `recoverFromRetreat` needs and the one
    an age bound would only approximate.

  - **Otherwise it is held**, because the banner persists between broadcasts and
    a reading that names no place is not a reading that says the fleet moved.

**A place seen this reading beats the reunion**, which is the ordering rather
than a detail of it: a commander who broadcasts `Travel to X` on the very
reading this ship rejoins him has said where the fleet is going next, and that
is the most useful thing this memory ever holds.

-}
fleetPlaceBroadcastAfterReading :
    { seenThisReading : Maybe { pilot : String, place : String }
    , commanderIsOnGrid : Bool
    , before : Maybe { pilot : String, place : String }
    }
    -> Maybe { pilot : String, place : String }
fleetPlaceBroadcastAfterReading placeCase =
    case placeCase.seenThisReading of
        Just seen ->
            Just seen

        Nothing ->
            if placeCase.commanderIsOnGrid then
                Nothing

            else
                placeCase.before


{-| The same broadcast, filtered against the pilots this bot trusts with its
own route. Matched exactly, never as a substring -- `fleetInviteSenderFromMessageBox`'s
reason: this hands a pilot the ship's own destination.
-}
fleetTravelBroadcast : List String -> ReadingFromGameClient -> Maybe { pilot : String, system : String, banner : String }
fleetTravelBroadcast permittedPilots readingFromGameClient =
    fleetTravelBroadcastAnyPilot readingFromGameClient
        |> Maybe.andThen
            (\broadcast ->
                if
                    permittedPilots
                        |> List.any
                            (\permitted ->
                                String.toLower (String.trim permitted) == String.toLower broadcast.pilot
                            )
                then
                    Just broadcast

                else
                    Nothing
            )


{-| The channel a decision uses to ask the host for a route, since a system
name cannot be spelled in the mouse/keyboard vocabulary a decision has. Ported
from `eve-online-saxrat`'s `hostDirectivePrefix` / `hostDirectiveSetDestination`
-- see the Architecture section of `CLAUDE.md` for the full argument. One-way
and unacknowledged: the client's own route panel is the confirmation, not
anything the host reports back.

**This sets the destination; flying it is `navigateTowardFleetCommander`'s
job, not this directive's.** The sentence this doc comment used to carry --
that nothing here flies the route, and that `eve-online-warp-to-0-autopilot`
is "built entirely around" the client's own Autopilot toggle -- was wrong
about that other bot as well as about this one: read live,
`eve-online-warp-to-0-autopilot`'s `decideStepWhenInSpace` presses the
Selected Item panel's own Jump button (falling back to the route marker's
context menu) whether or not the client's Autopilot toggle is on at all; it
never reads that toggle. `sessionIsEnding`'s trip home is still exactly the
posture the old sentence described -- nothing drives it -- but the travel
broadcast is not, since `navigateTowardFleetCommander` below is that same
mechanism, ported.

-}
hostDirectivePrefix : String
hostDirectivePrefix =
    "@host "


hostDirectiveSetDestination : String -> String
hostDirectiveSetDestination systemName =
    hostDirectivePrefix ++ "set-destination " ++ systemName


{-| Whether a named pilot has a row on the current overview -- the proxy for
"is the fleet commander in this system right now", since nothing here reads a
pilot's system directly. Matched on the row's own Name, exactly as
`lockCalledTarget` matches a called target's.
-}
pilotIsOnOverview : String -> ReadingFromGameClient -> Bool
pilotIsOnOverview pilotName readingFromGameClient =
    overviewEntryForPilot pilotName readingFromGameClient /= Nothing


{-| The overview row whose Name cell is exactly this string -- a pilot's, or a
called target's -- which is the thing a manoeuvre or a lock is issued against.
`ensureShipIsOrbiting` selects it before pressing the panel's own Orbit, and
`lockCalledTarget` clicks it.

`pilotIsOnOverview` is this same question with the row thrown away, and asks it
through here rather than beside it: a bot that decides "the commander is on the
grid" one way and then looks for the row another way can answer yes to the
first and find nothing to click for the second. `calledTargetIsLocked` is the
same argument for the lock indicator.

-}
overviewEntryForPilot : String -> ReadingFromGameClient -> Maybe OverviewWindowEntry
overviewEntryForPilot pilotName readingFromGameClient =
    overviewRowsForPilot pilotName readingFromGameClient |> List.head


{-| Every overview row whose Name cell is exactly this name.

The selection `overviewEntryForPilot` takes its head of, lifted out because
#393's `calledObjectOnOverview` needs the whole list -- "does any row naming it
say acceleration gate" and "is that row drawn" are questions a head cannot
answer on a grid where the head is something else. One definition with two
readers, so the rule that classifies the called object and the arm that clicks
it cannot end up on two different rows, which is #303's lesson and what put the
lock and its recognition on one lookup in the first place.

-}
overviewRowsForPilot : String -> ReadingFromGameClient -> List OverviewWindowEntry
overviewRowsForPilot pilotName readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter (.objectName >> (==) (Just pilotName))


{-| Fly toward the fleet commander's broadcast destination, using
`eve-online-warp-to-0-autopilot`'s own mechanism for actually flying a route --
ported rather than reinvented, since that bot's `decideStepWhenInSpace` is
exactly this problem already solved and measured. Everything from
`RouteStargateJump` down to `nodeIsDisplayed` below is that bot's code,
unchanged; only this function and the two memory fields it reads
(`routeFirstMarkerRegion`, `routeFirstMarkerUnchangedTicks`) are new.

**Called only while the commander is off this grid.** `actOnFleetBroadcast`
is what decides that, by asking `pilotIsOnOverview` -- this function does not
re-ask it, so it has no opinion of its own about when it should run. Once the
commander reappears on the overview, `actOnFleetBroadcast` stops calling this
and the ship holds wherever the last jump left it, which is the correct
place to be: arriving is what "not out of system anymore" means.

**Two rungs, not three.** `eve-online-warp-to-0-autopilot` has a third:
`jumpCascadeStuckReadings`, which counts consecutive readings the route panel
names the same next system with no jump landing, and falls back to a
surroundings-button cascade past 30 of them. That count is derived from
`newJumpsCompleted`, which is itself derived from `lastSolarSystemName`
changing -- bookkeeping this bot has no other use for and does not otherwise
keep. Approximating it off `nextSystemOnRouteFromReading` changing instead
would misread the one case that bot's own comment names as the reason for
the more careful signal -- a route that revisits a system it has already
named, where the label repeats on a leg that did complete. Rather than ship
a stuck-detector that can misfire on exactly the case it exists to catch,
this bot's third rung is not ported; `jumpThroughRouteStargate`'s own two
rungs (the panel button, then the marker's right-click cascade) are what
run here. The cost is stated rather than hidden: a route this bot cannot
identify a gate for, gone stuck at the marker cascade, has no further
fallback and keeps retrying it.

-}
navigateTowardFleetCommander : BotDecisionContext -> ShipUI -> DecisionPathNode
navigateTowardFleetCommander context shipUI =
    case infoPanelRouteFirstMarkerFromReadingFromGameClient context.readingFromGameClient of
        Nothing ->
            -- Two different situations read identically here and this cannot
            -- tell them apart: the ESI ask has not taken effect yet, or the
            -- route was flown to the end and there is nothing left of it --
            -- this bot keeps no "did we ever see a marker for this broadcast"
            -- memory the way `eve-online-warp-to-0-autopilot`'s
            -- `didTravelEnRoute` does, so the message says so honestly rather
            -- than asserting the first when it could be either.
            describeBranch
                "No route in the info panel -- either the destination has not taken effect yet, or the route has already been flown to its end and the commander has moved again since."
                waitForProgressInGame

        Just infoPanelRouteFirstMarker ->
            if shipUIIndicatesShipIsWarpingOrJumping shipUI then
                describeBranch
                    "I see the ship is warping or jumping. I wait until that maneuver ends."
                    waitForProgressInGame

            else if context.memory.routeFirstMarkerUnchangedTicks < 1 then
                describeBranch
                    "Route panel's first marker just appeared or moved since the last reading -- wait for the route to finish (re)computing before clicking it."
                    waitForProgressInGame

            else
                jumpThroughRouteStargate context
                    (routeMarkerCascade context infoPanelRouteFirstMarker)


{-| Right-click the route panel's first marker and take whichever of "dock" or
"jump" the client offers. Ported from `eve-online-warp-to-0-autopilot`'s
function of the same name, unchanged -- see that bot's own doc comment for why
"dock" stays first in the list.
-}
routeMarkerCascade :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.InfoPanelRouteRouteElementMarker
    -> DecisionPathNode
routeMarkerCascade context infoPanelRouteFirstMarker =
    useContextMenuCascadeWithCustomConfig
        (discardContextMenuIfTooDistantFromTargetElement { toleratedDistance = 200 })
        { targetUIElement = infoPanelRouteFirstMarker.uiNode, targetUIElementName = "route element icon" }
        (useMenuEntryWithTextContainingFirstOfCommonContinuation
            [ "dock"

            -- https://forum.botlab.org/t/i-want-to-add-korean-support-on-eve-online-bot-what-should-i-do/4370/14
            , "도킹"
            , "jump"

            -- https://forum.botlab.org/t/i-want-to-add-korean-support-on-eve-online-bot-what-should-i-do/4370
            , "점프 - 스타게이트 사용"
            ]
            menuCascadeCompleted
        )
        context


{-| Whether to press the Selected Item panel's Jump, and which gate it would
be. Ported byte for byte from `eve-online-warp-to-0-autopilot`'s function of
the same name -- see that bot's own doc comment for the full argument (#170's
rule, identical across saxrat, the mission runner and that bot).
-}
type RouteStargateJump
    = PressTheJumpButton String
    | NoNextSystemOnRoute
    | NoStargateNamedForTheNextSystem String
    | SeveralStargatesNamedForTheNextSystem String
    | ThePanelIsShowingSomethingElse String
    | ThePanelOffersNoJump String


routeStargateJump :
    { nextSystemOnRoute : Maybe String
    , stargatesOnOverview : List { name : String, panelIsShowingIt : Bool }
    , panelOffersJump : Bool
    }
    -> RouteStargateJump
routeStargateJump input =
    case input.nextSystemOnRoute of
        Nothing ->
            NoNextSystemOnRoute

        Just nextSystem ->
            case input.stargatesOnOverview |> List.filter (.name >> stargateNameLeadsToSystem nextSystem) of
                [] ->
                    NoStargateNamedForTheNextSystem nextSystem

                [ gate ] ->
                    if not gate.panelIsShowingIt then
                        ThePanelIsShowingSomethingElse nextSystem

                    else if not input.panelOffersJump then
                        ThePanelOffersNoJump nextSystem

                    else
                        PressTheJumpButton gate.name

                _ ->
                    SeveralStargatesNamedForTheNextSystem nextSystem


describeRouteStargateJump : RouteStargateJump -> String
describeRouteStargateJump jump =
    case jump of
        PressTheJumpButton gateName ->
            "Jump through '" ++ gateName ++ "' from the selected-item panel, which is already showing it."

        NoNextSystemOnRoute ->
            "The route panel does not name a next system, so nothing here says which stargate is the route's -- right-click the route marker instead."

        NoStargateNamedForTheNextSystem nextSystem ->
            "No stargate on the overview is named for '" ++ nextSystem ++ "' -- right-click the route marker instead."

        SeveralStargatesNamedForTheNextSystem nextSystem ->
            "More than one stargate on the overview is named for '" ++ nextSystem ++ "', so which one the route means is not readable here -- right-click the route marker instead."

        ThePanelIsShowingSomethingElse nextSystem ->
            "The selected-item panel is not showing the stargate to '" ++ nextSystem ++ "' -- selecting it would spend the reading this saves, so right-click the route marker instead."

        ThePanelOffersNoJump nextSystem ->
            "The selected-item panel is showing the stargate to '" ++ nextSystem ++ "' and offers no 'selectedItemJump' -- right-click the route marker instead, which is what closes the distance."


{-| Whether an overview row's name says this stargate leads to `systemName`.
Ported unchanged from `eve-online-warp-to-0-autopilot`.
-}
stargateNameLeadsToSystem : String -> String -> Bool
stargateNameLeadsToSystem systemName gateName =
    containsWords (punctuationAsSeparators systemName) (punctuationAsSeparators gateName)


punctuationAsSeparators : String -> String
punctuationAsSeparators =
    String.map
        (\character ->
            if Char.isAlphaNum character then
                character

            else
                ' '
        )


{-| A broadcast-named gate, found on the overview -- matched the same way
`routeStargateJumpFromReading` matches the route panel's own next system, since
a `Jump Stargate X` or `Align Stargate X` broadcast names a gate directly
rather than a place `@host set-destination` would have to compute a route
for. #347: **the named gate may not be on the overview**, and this answers
`Nothing` rather than a different row when it is not -- `jumpToCalledGate` and
`alignToCalledGate` both say so rather than guessing.
-}
gateOverviewEntry : String -> ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
gateOverviewEntry gateName readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter overviewEntryIsAStargate
        |> List.filter
            (.objectName
                >> Maybe.map (stargateNameLeadsToSystem gateName)
                >> Maybe.withDefault False
            )
        |> List.head


{-| `routeStargateJump` fed a broadcast's own gate name instead of the route
panel's next system. `routeStargateJump` -- the pure decision underneath
`navigateTowardFleetCommander` -- is already generic over "which system", so
this reuses it unchanged rather than porting a fourth copy of the jump logic,
the way #347 asked for.
-}
routeStargateJumpForNamedGate : String -> ReadingFromGameClient -> RouteStargateJump
routeStargateJumpForNamedGate gateName readingFromGameClient =
    routeStargateJump
        { nextSystemOnRoute = Just gateName
        , stargatesOnOverview =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter overviewEntryIsDisplayed
                |> List.filter overviewEntryIsAStargate
                |> List.map
                    (\gate ->
                        { name = gate.objectName |> Maybe.withDefault ""
                        , panelIsShowingIt = selectedItemIsOverviewEntry readingFromGameClient gate
                        }
                    )
        , panelOffersJump = routeStargateJumpButton readingFromGameClient /= Nothing
        }


{-| Take a broadcast-named gate: press the Selected Item panel's Jump button
where it already shows that gate, falling back to a right-click on the gate's
own overview row and its "Jump Through Stargate" entry -- the fallback
`routeMarkerCascade` uses for the route panel's marker, retargeted at an
overview entry because this gate was never necessarily the target of any ESI
route. See `gateOverviewEntry` and `routeStargateJumpForNamedGate` for the two
pieces this composes, both reused rather than reinvented per #347.
-}
jumpToCalledGate : BotDecisionContext -> String -> DecisionPathNode
jumpToCalledGate context gateName =
    case gateOverviewEntry gateName context.readingFromGameClient of
        Nothing ->
            describeBranch
                ("'" ++ gateName ++ "' is not on the overview -- nothing to jump through.")
                waitForProgressInGame

        Just overviewEntry ->
            let
                verdict : RouteStargateJump
                verdict =
                    routeStargateJumpForNamedGate gateName context.readingFromGameClient
            in
            case ( verdict, routeStargateJumpButton context.readingFromGameClient ) of
                ( PressTheJumpButton _, Just buttonToPress ) ->
                    describeBranch (describeRouteStargateJump verdict)
                        (clickUiElementForNavigation buttonToPress)

                _ ->
                    describeBranch (describeRouteStargateJump verdict)
                        (useContextMenuCascadeOnOverviewEntry
                            (useMenuEntryWithTextContainingFirstOfCommonContinuation
                                [ "jump"

                                -- https://forum.botlab.org/t/i-want-to-add-korean-support-on-eve-online-bot-what-should-i-do/4370
                                , "점프 - 스타게이트 사용"
                                ]
                                menuCascadeCompleted
                            )
                            overviewEntry
                            context
                        )


{-| Open a broadcast-named gate's own context menu, so the next reading
records what the client offers for "Align" -- the same
`openTheBroadcastsOwnMenu` pattern #347 pointed at: aligning is not a cascade
this repo has driven before and the client's own menu wording for it has
never been read, so guessing at it is exactly the failure this repo's own
testing discipline refuses. Nothing here clicks a menu entry.
-}
alignToCalledGate : BotDecisionContext -> String -> DecisionPathNode
alignToCalledGate context gateName =
    case gateOverviewEntry gateName context.readingFromGameClient of
        Nothing ->
            describeBranch
                ("'" ++ gateName ++ "' is not on the overview -- nothing to align to.")
                waitForProgressInGame

        Just overviewEntry ->
            describeBranch
                ("'"
                    ++ gateName
                    ++ "' is on the overview. Opening its own menu so the next"
                    ++ " reading records what 'Align' offers."
                )
                (useContextMenuCascadeOnOverviewEntry menuCascadeCompleted overviewEntry context)


{-| The system the route panel says this ship jumps to next, if it says.
Ported unchanged from `eve-online-warp-to-0-autopilot`.
-}
nextSystemOnRouteFromReading : ReadingFromGameClient -> Maybe String
nextSystemOnRouteFromReading readingFromGameClient =
    readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelRoute
        |> Maybe.map (.uiNode >> .uiNode >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts)
        |> Maybe.withDefault []
        |> List.filterMap parseNextSystemInRouteFromLabelText
        |> List.head


parseNextSystemInRouteFromLabelText : String -> Maybe String
parseNextSystemInRouteFromLabelText labelText =
    [ "alt='Next System in Route'", "alt=\"Next System in Route\"" ]
        |> List.filterMap
            (\marker ->
                labelText |> EveOnline.ParseUserInterface.getSubstringBetweenXmlTagsAfterMarker marker
            )
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)
        |> List.head


{-| Whether an overview row's own words say it is a stargate. Ported unchanged
from `eve-online-warp-to-0-autopilot`.
-}
overviewEntryIsAStargate : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsAStargate entry =
    [ entry.objectName, entry.objectType ]
        |> List.filterMap identity
        |> List.any (containsWords "stargate")


{-| Whether an overview row's own words say it is an acceleration gate.
-}
overviewEntryIsAnAccelerationGate : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsAnAccelerationGate entry =
    [ entry.objectName, entry.objectType ]
        |> List.filterMap identity
        |> List.any (containsWords "acceleration gate")


{-| The nearest displayed acceleration gate on the overview, if there is one.
A hidden row's region belongs to whatever was recycled into its place, so a
row that is not `_display`ed is excluded rather than clicked. `Result.withDefault`
pushes an unreadable (AU) distance to the back rather than dropping it, since a
gate whose distance cannot be read is still a gate worth reporting on.
-}
nearestAccelerationGateOnOverview : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
nearestAccelerationGateOnOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter overviewEntryIsAnAccelerationGate
        |> List.sortBy (.objectDistanceInMeters >> Result.withDefault 999999)
        |> List.head


{-| Take the route's next stargate by pressing the Selected Item panel's own
Jump button, where the panel is already showing that gate. Ported unchanged
from `eve-online-warp-to-0-autopilot`.
-}
jumpThroughRouteStargate : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
jumpThroughRouteStargate context ifThePanelCannotDoIt =
    let
        jumpButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        jumpButton =
            routeStargateJumpButton context.readingFromGameClient

        verdict : RouteStargateJump
        verdict =
            routeStargateJumpFromReading context.readingFromGameClient
    in
    case ( verdict, jumpButton ) of
        ( PressTheJumpButton _, Just buttonToPress ) ->
            describeBranch (describeRouteStargateJump verdict) (clickUiElementForNavigation buttonToPress)

        _ ->
            describeBranch (describeRouteStargateJump verdict) ifThePanelCannotDoIt


{-| The three readings `routeStargateJump` decides from, taken off one
reading. Ported unchanged from `eve-online-warp-to-0-autopilot`.
-}
routeStargateJumpFromReading : ReadingFromGameClient -> RouteStargateJump
routeStargateJumpFromReading readingFromGameClient =
    routeStargateJump
        { nextSystemOnRoute = nextSystemOnRouteFromReading readingFromGameClient
        , stargatesOnOverview =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter overviewEntryIsDisplayed
                |> List.filter overviewEntryIsAStargate
                |> List.map
                    (\gate ->
                        { name = gate.objectName |> Maybe.withDefault ""
                        , panelIsShowingIt =
                            selectedItemIsOverviewEntry readingFromGameClient gate
                        }
                    )
        , panelOffersJump = routeStargateJumpButton readingFromGameClient /= Nothing
        }


{-| The Selected Item panel's Jump button, named once. Ported unchanged from
`eve-online-warp-to-0-autopilot`.
-}
routeStargateJumpButton : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
routeStargateJumpButton readingFromGameClient =
    selectedItemButtonNamed readingFromGameClient "selectedItemJump"


{-| Whether `pattern` occurs in `text` as whole words rather than as a
substring. Ported unchanged from `eve-online-warp-to-0-autopilot`.
-}
containsWords : String -> String -> Bool
containsWords pattern text =
    let
        padded value =
            " " ++ (value |> String.toLower |> String.words |> String.join " ") ++ " "
    in
    String.contains (padded pattern) (padded text)


{-| A button in the Selected Item panel, by its own `_name`. Ported unchanged
from `eve-online-warp-to-0-autopilot`.
-}
selectedItemButtonNamed :
    ReadingFromGameClient
    -> String
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
selectedItemButtonNamed readingFromGameClient name =
    readingFromGameClient.selectedItemWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.filter
            (\node ->
                (node.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries) == Just name
            )
        |> List.head


{-| One of the Selected Item panel's buttons, by **both** the identifiers the
client carries for it.

The client writes an id on the node (`_name` / `_elementId`, which read alike on
every panel button this bot has ever pressed) and a `cmdName` beside it --
`selectedItemOrbit` and `CmdOrbitItem` name the same button. Matching either
survives a rename of one, which is cheap insurance on a widget name: that is the
class of thing that has cost this repo several sessions, and #414's own
`selectedItemUnLockTarget` -- a capital `L` its Lock sibling does not have -- is
what a guessed name looks like when it is wrong.

-}
type alias SelectedItemPanelButton =
    { elementId : String, cmdName : String }


selectedItemOrbitButton : SelectedItemPanelButton
selectedItemOrbitButton =
    { elementId = "selectedItemOrbit", cmdName = "CmdOrbitItem" }


{-| The panel's Unlock, which is **not** `selectedItemLockTarget` with a prefix.

`selectedItemUnLockTarget` carries a capital `L` in the middle that its Lock
sibling does not, read off a live client with a locked target selected. A
guessed `selectedItemUnlockTarget` matches nothing -- and "no button" is
indistinguishable here from "nothing to unlock", so the guess would have failed
silently, in a guard whose whole job is not to.

Lock and Unlock occupy the **same slot** and swap with the target's lock state,
so the panel offering this one is the client saying the object is locked.

-}
selectedItemUnLockTargetButton : SelectedItemPanelButton
selectedItemUnLockTargetButton =
    { elementId = "selectedItemUnLockTarget", cmdName = "CmdUnlockTargetItem" }


{-| Free a lock slot with the panel's own Unlock, where the panel is showing the
pilot to unlock.

**Why this is worth having beside the cascade it does not replace.**
`unlockFleetPilotInTargetBar` right-clicks the _target bar's_ own entry and takes
an `unlock` menu entry, which is a screen position computed from a reading plus a
flyout that has to render -- and the bar reorders as targets are taken and lost,
so it carries #413's exposure as the overview does. The panel button does not: it
is found by name in the same reading it is pressed in, and it acts on the
selected object.

**And it needs no bar entry.** #390 kept `lockedTargetNamed` alive precisely
because the cascade has to right-click something in the bar, after the overview's
own indicator became the deciding signal. A panel press needs neither a bar entry
nor a menu -- so where the panel is showing the pilot this fires with the bar
never consulted. `lockedTargetNamed` stays because it is still the fall-back's
only way to find something to right-click, and because #389's own reason for it
is unchanged.

**It adds no way to select and so cannot loop.** This answers `Nothing` unless
the panel is _already_ showing the pilot, and the caller then does exactly what
it always did. No reading is ever spent selecting for the unlock, no new bound is
needed, and a client that never selects the pilot costs nothing at all.

**Which makes the cascade's own right-click the thing that reaches this
branch**, and that is stated rather than assumed: right-clicking a target-bar
entry is expected to select the object as well as opening the menu, so a cascade
that does not land should leave the panel showing the pilot and the next reading
presses the button. **No reading has ever confirmed that**, and the direction it
fails in is the safe one -- the panel path never fires and the cascade goes on
being the only mechanism.

**The panel offering Unlock is the client saying this object is locked**, since
Lock and Unlock share the slot, so the press is declined outright where the panel
offers Lock instead.

-}
unlockFromSelectedItemPanel : BotDecisionContext -> String -> Maybe DecisionPathNode
unlockFromSelectedItemPanel context pilotName =
    if not (panelIsShowingText context.readingFromGameClient pilotName) then
        Nothing

    else
        selectedItemPanelButton context.readingFromGameClient selectedItemUnLockTargetButton
            |> Maybe.map clickUiElementOrSayItCannotBeClicked


{-| Whether the Selected Item panel's own texts carry this string.

`selectedItemIsOverviewEntry` asks the same question of an overview row; a
target-bar entry is not one, so this is the half of that rule that takes the
text. One `containsWords` test, so the two cannot come to disagree about what
"the panel is showing it" means -- and an empty name matches nothing rather than
everything, which is `valueTypeNonEmptyString`'s register applied to a lookup.

-}
panelIsShowingText : ReadingFromGameClient -> String -> Bool
panelIsShowingText readingFromGameClient text =
    case ( readingFromGameClient.selectedItemWindow, String.trim text ) of
        ( _, "" ) ->
            False

        ( Just window, trimmed ) ->
            EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode.uiNode
                |> List.any (containsWords trimmed)

        ( Nothing, _ ) ->
            False


{-| Find one of those buttons in **this** reading, by name and never by
position.

`selectedItemOrbit` was read live at x=1515 in one reading and x=1551 in another
moments later, because two buttons left the row and everything shifted -- so an
arm that remembers where a button was, or picks by index, is pressing a
different command a reading later. Nothing here may be optimised into a
position.

Absence is a normal answer, not an error: the panel's button set is contextual
(a station offers Dock and Align To, a gate offers Jump and Approach, a rat
offers Approach), and a ship in warp offers less again.

-}
selectedItemPanelButton :
    ReadingFromGameClient
    -> SelectedItemPanelButton
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
selectedItemPanelButton readingFromGameClient button =
    let
        property name node =
            node.uiNode |> EveOnline.ParseUserInterface.getStringPropertyFromDictEntries name
    in
    readingFromGameClient.selectedItemWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.filter
            (\node ->
                [ property "_name" node
                , property "_elementId" node
                ]
                    |> List.member (Just button.elementId)
                    |> (||) (property "cmdName" node == Just button.cmdName)
            )
        |> List.head


{-| Whether the Selected Item panel is showing this overview entry. Ported
unchanged from `eve-online-warp-to-0-autopilot`.
-}
selectedItemIsOverviewEntry :
    ReadingFromGameClient
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> Bool
selectedItemIsOverviewEntry readingFromGameClient entry =
    case ( readingFromGameClient.selectedItemWindow, entry.objectName ) of
        ( Just window, Just name ) ->
            EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode.uiNode
                |> List.any (containsWords name)

        _ ->
            False


{-| Whether an overview row is actually drawn. Ported unchanged from
`eve-online-warp-to-0-autopilot`.
-}
overviewEntryIsDisplayed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    nodeIsDisplayed entry.uiNode.uiNode


{-| The widget's own `_display` flag, defaulting to shown when absent. Ported
unchanged from `eve-online-warp-to-0-autopilot`.
-}
nodeIsDisplayed : EveOnline.MemoryReading.UITreeNode -> Bool
nodeIsDisplayed uiNode =
    uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


clickUiElementForNavigation : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DecisionPathNode
clickUiElementForNavigation uiElement =
    decideActionForCurrentStep
        (mouseClickOnUIElement MouseButtonLeft uiElement |> Result.withDefault [])


{-| The wingman's decision root, in the order the operator asked for it.

Each arm is reached only when the one above it has nothing to do, which is the
shape every bot in this repo uses. Two of them are deliberately unfinished and
say so in the log rather than doing something plausible: the broadcast verbs
nobody has captured yet, and the trip home.

-}
wingmanDecisionRoot : BotDecisionContext -> DecisionPathNode
wingmanDecisionRoot context =
    wingmanDecisionRootBeforeApplyingSettings context
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            (randomIntFromInterval context context.eventContext.botSettings.botStepDelayMilliseconds)


wingmanDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
wingmanDecisionRootBeforeApplyingSettings context =
    generalSetupInUserInterface context
        |> Maybe.withDefault
            (branchDependingOnDockedOrInSpace
                { ifDocked =
                    case dockedSessionIsEnding context of
                        Just stayDocked ->
                            stayDocked

                        Nothing ->
                            describeBranch "Undock."
                                (undockUsingStationWindow context
                                    { ifCannotReachButton = askForHelpToGetUnstuck }
                                )
                , ifSeeShipUI = wingmanDecisionRootInSpace context
                }
                context
            )


{-| The order the operator asked for (#349): undock, activate always-on
modules, act on the broadcast, drones assist the commander, everything else --
with the health retreat inserted at the top of the fighting half (#364).
Accepting a fleet invite sits ahead of all of it, in `generalSetupInUserInterface`,
since that can land while still docked.
-}
wingmanDecisionRootInSpace : BotDecisionContext -> ShipUI -> DecisionPathNode
wingmanDecisionRootInSpace context shipUI =
    case sessionIsEnding context shipUI of
        Just goHome ->
            goHome

        Nothing ->
            case retreatToTheCommander context shipUI of
                Just breakOff ->
                    -- #364. Above every arm that fights and below the one arm
                    -- that has a deadline, and both halves of that are
                    -- measured rather than chosen for symmetry.
                    --
                    -- **Above the fighting arms**, because each of them
                    -- answers `Just` for the whole of a fight and the first
                    -- arm to answer ends the reading: the broadcast banner
                    -- does not clear while a target is called (#360), the
                    -- drone arm answers on every reading a drone idles
                    -- (#326), and the guns answer on every reading a weapon
                    -- is not cycling. A retreat placed under any of them is
                    -- reachable only on the readings the fleet is doing
                    -- nothing, which is every reading except the ones it
                    -- exists for. `activateAlwaysOnModules` is above the
                    -- fight in #349's order and still below this: a hardener
                    -- click is worth a reading when the ship is staying and
                    -- is not when it is leaving.
                    --
                    -- **Above the broadcast arm in particular** is saxrat's
                    -- own ordering, and it recorded why: its retreat used to
                    -- sit below `respondToFleetBackupBroadcast`, so a
                    -- critically damaged ship would warp *toward* a
                    -- fleet-mate's fight rather than away from its own. This
                    -- bot is that failure by construction, since following
                    -- broadcasts is the whole job.
                    --
                    -- **Below `sessionIsEnding`**, because that is the only
                    -- arm here carrying a hard deadline -- #350's stall, and
                    -- `tripHomeSecondsPastSessionEnd` bounding the trip home
                    -- past it. The retreat's verdict latches until the gauge
                    -- recovers past `runAwayRearmPercent` or the window
                    -- empties, and `retreatAskedReadings` resets on every
                    -- reading the ship is in warp, so a retreat placed above
                    -- the wind-down could keep warping a damaged ship away
                    -- for the rest of a session that was supposed to be
                    -- ending. Saxrat's `endSessionOnAnExpiredBound` sits above
                    -- its retreat for the same reason.
                    breakOff

                Nothing ->
                    case recoverFromRetreat context shipUI of
                        Just rejoinTheFleet ->
                            -- Same placement as the retreat itself and for the
                            -- same reason: a ship still flying back from a
                            -- break-off should not be pulled into the next
                            -- fight or the next broadcast before it gets
                            -- there. See `recoverFromRetreat`.
                            rejoinTheFleet

                        Nothing ->
                            wingmanDecisionRootInSpaceOrdinary context shipUI


wingmanDecisionRootInSpaceOrdinary : BotDecisionContext -> ShipUI -> DecisionPathNode
wingmanDecisionRootInSpaceOrdinary context shipUI =
    case unlockFleetPilotInTargetBar context of
        Just unlockFleetmate ->
            -- #367. A fleet member in the target bar is a
            -- safety condition, so this outranks every arm
            -- that would rather be doing something else --
            -- each of which answers `Just` for the whole of a
            -- fight, which is precisely when a friendly is in
            -- there. Below the retreat only: a ship past its
            -- threshold leaves the grid, which ends the
            -- engagement more thoroughly than an unlock does.
            -- The full argument is in
            -- `unlockFleetPilotInTargetBar`.
            unlockFleetmate

        Nothing ->
            case activateAlwaysOnModules context of
                Just activate ->
                    activate

                Nothing ->
                    -- #394. The second half of #349's module step, and it
                    -- sits with the first rather than below the broadcast
                    -- for the reason #349 established: a hardener click is
                    -- worth a reading when the ship is staying, and every
                    -- arm under the broadcast answers `Just` for the whole
                    -- of a fight. `activateAlwaysOnModules` stays ahead of
                    -- it: a module an operator named by tooltip is one they
                    -- asked for by hand, and the row this finds by position
                    -- is the standing default underneath that.
                    case manageMiddleRowModules context of
                        Just manageTheMiddleRow ->
                            manageTheMiddleRow

                        Nothing ->
                            case answerTheBackupCall context shipUI of
                                Just goToTheirAid ->
                                    -- #385. Above the travel forms in
                                    -- `actOnFleetBroadcast`, because being slow to a
                                    -- backup call costs a ship where being slow to an
                                    -- `is at location` costs a few seconds of
                                    -- alignment -- the argument #237 makes for saxrat.
                                    -- Below the retreat and below `sessionIsEnding` by
                                    -- the whole tree, as everything here is: a ship
                                    -- past its own threshold leaves rather than
                                    -- joining somebody else's fight, which is the
                                    -- ordering saxrat's own retreat records having
                                    -- needed. And below the module step --
                                    -- `unlockFleetPilotInTargetBar`,
                                    -- `activateAlwaysOnModules` and #394's
                                    -- `manageMiddleRowModules` -- which are a
                                    -- safety condition and two clicks. #394's own
                                    -- argument for keeping that step together is
                                    -- what settles the order between it and this:
                                    -- a hardener or a prop mod is worth a reading
                                    -- while the ship is staying, and this arm is
                                    -- the first one that decides to go somewhere.
                                    --
                                    -- It answers `Nothing` for every case that is not
                                    -- an action, so it starves nothing below it while
                                    -- a banner that does not clear stays up -- see
                                    -- `answerTheBackupCall`.
                                    goToTheirAid

                                Nothing ->
                                    case closeOnTheCommanderAfterLanding context shipUI of
                                        Just closeOnTheCommander ->
                                            -- Below the backup call, and that was neither
                                            -- author's decision: #385 and #397 were written
                                            -- against this same slot without knowing of each
                                            -- other, and the order was chosen when they met.
                                            -- A backup call costs a ship and this window costs
                                            -- seconds, and `answerTheBackupCall` answers
                                            -- `Nothing` for everything that is not an action,
                                            -- so it starves nothing by sitting above. The
                                            -- reverse would swallow a backup call for this
                                            -- whole window, which opens on landing -- when a
                                            -- fight is most likely starting.
                                            -- #397, and it is a window rather than a
                                            -- placement. From the reading the warp ends
                                            -- until the client names the manoeuvre
                                            -- `Approach`, closing on the commander
                                            -- outranks the arms below -- each of which
                                            -- answers `Just` for the whole of a fight,
                                            -- which is what made
                                            -- `approachTheFleetCommander` unreachable at
                                            -- the foot of this list on every grid worth
                                            -- landing on.
                                            --
                                            -- **Below the middle-row arm, not above it.**
                                            -- #394 ties the propulsion module to the
                                            -- client naming `Approach`; this arm answers
                                            -- `Just` for as long as it is closing, so
                                            -- above the module arm it would starve the
                                            -- prop mod during exactly the window the
                                            -- module exists for. The module arm is a
                                            -- state check and a click and can block on
                                            -- nothing, which is why it is safe ahead.
                                            closeOnTheCommander

                                        Nothing ->
                                            case actOnFleetBroadcast context shipUI of
                                                Just actOnBroadcast ->
                                                    actOnBroadcast

                                                Nothing ->
                                                    case dronesAssistTheCommander context of
                                                        Just assist ->
                                                            assist

                                                        Nothing ->
                                                            case fireOnActiveTarget context of
                                                                Just fire ->
                                                                    -- Strictly below the drone arm and
                                                                    -- strictly above the gate: a locked
                                                                    -- target means a fight, and a bot
                                                                    -- that would rather take a gate
                                                                    -- than shoot what the commander
                                                                    -- called has left the fleet a ship
                                                                    -- short in the pocket it just left.
                                                                    fire

                                                                Nothing ->
                                                                    case approachTheFleetCommander context shipUI of
                                                                        Just approachTheCommander ->
                                                                            -- #365. Below the drone arm
                                                                            -- and below the guns so it
                                                                            -- can starve neither
                                                                            -- (#326), and above the
                                                                            -- gate so the gate arm's
                                                                            -- own "rats are still on
                                                                            -- the grid" wait cannot
                                                                            -- starve it in the one
                                                                            -- state it is most for.
                                                                            -- Below #364's retreat by
                                                                            -- the whole tree: a damaged
                                                                            -- ship breaks off rather
                                                                            -- than holds station, so
                                                                            -- nothing that keeps this
                                                                            -- ship on the grid may ever
                                                                            -- answer before that arm
                                                                            -- does. The full argument
                                                                            -- is in
                                                                            -- `approachTheFleetCommander`.
                                                                            approachTheCommander

                                                                        Nothing ->
                                                                            case accelerationGateStep context of
                                                                                Just takeTheGate ->
                                                                                    -- #348. Sits after the
                                                                                    -- drone arm and after the
                                                                                    -- guns, never before
                                                                                    -- them, so a gate this
                                                                                    -- bot can see is never
                                                                                    -- taken while drones are
                                                                                    -- still owed a command on
                                                                                    -- a live grid -- the same
                                                                                    -- ordering argument #326
                                                                                    -- established for the
                                                                                    -- drone arm itself.
                                                                                    takeTheGate

                                                                                Nothing ->
                                                                                    {- The inherited
                                                                                       combat-anomaly-bot arm
                                                                                       is gone from here
                                                                                       (#349): it hunted
                                                                                       anomalies on an idle
                                                                                       grid, which is not
                                                                                       following a commander.
                                                                                       What remains is
                                                                                       self-defense only --
                                                                                       and it is now genuinely
                                                                                       the last resort it
                                                                                       reads as, because
                                                                                       `fireOnActiveTarget`
                                                                                       above it fires on
                                                                                       anything locked whether
                                                                                       or not a rat has
                                                                                       pointed this ship.
                                                                                    -}
                                                                                    fightPointedRatsOrReturnDrones context shipUI


{-| What the current broadcast asks for, if this bot can act on it yet.

**Only observed forms are matched.** A travel broadcast names its sender, so it
is filtered against `follow-fleet-broadcast-from`; a target broadcast does not,
and is acted on for anyone in the fleet. A backup call is neither: it reaches
`answerTheBackupCall`, above this branch, whose boundary is fleet membership --
see #385.

The verbs in `broadcastVerbsNotYetRead` fall through to a named wait rather than
to a guess, because the button's wording is not the broadcast's and nothing has
observed the difference yet.

-}
actOnFleetBroadcast : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
actOnFleetBroadcast context shipUI =
    case fleetBroadcastBannerText context.readingFromGameClient of
        Nothing ->
            Nothing

        Just bannerText ->
            case targetBroadcastPilotName bannerText of
                Just calledTarget ->
                    if List.member calledTarget (fleetPilotNames context) then
                        Just
                            (describeBranch
                                ("The called target '"
                                    ++ calledTarget
                                    ++ "' is in this fleet. Not shooting it."
                                )
                                waitForProgressInGame
                            )

                    else
                        bringCalledTargetUnderFire context calledTarget

                Nothing ->
                    case
                        fleetTravelBroadcast
                            context.eventContext.botSettings.followFleetBroadcastFrom
                            context.readingFromGameClient
                    of
                        Just broadcast ->
                            if context.memory.fleetBroadcastFollowed == Just broadcast.banner then
                                if pilotIsOnOverview broadcast.pilot context.readingFromGameClient then
                                    Just
                                        (describeBranch
                                            ("'"
                                                ++ broadcast.pilot
                                                ++ "' is on the overview -- no longer out of system, so nothing more to fly toward."
                                            )
                                            waitForProgressInGame
                                        )

                                else
                                    Just
                                        (describeBranch
                                            ("'"
                                                ++ broadcast.pilot
                                                ++ "' is not on the overview -- navigating toward the route to '"
                                                ++ broadcast.system
                                                ++ "'."
                                            )
                                            (navigateTowardFleetCommander context shipUI)
                                        )

                            else
                                Just
                                    (describeBranch
                                        ("'"
                                            ++ broadcast.pilot
                                            ++ "' broadcast a travel destination and is named in "
                                            ++ "'follow-fleet-broadcast-from' -- asking the host to set "
                                            ++ "the route to '"
                                            ++ broadcast.system
                                            ++ "'. "
                                            ++ hostDirectiveSetDestination broadcast.system
                                        )
                                        waitForProgressInGame
                                    )

                        Nothing ->
                            actOnBroadcastVerb context shipUI bannerText


{-| Lock the called target, then get out of the way.

**Answering `Nothing` once it is locked is the whole point of this function.**
The broadcast banner does not clear when the target is locked -- it stays up
for the rest of the call -- so the target arm of `actOnFleetBroadcast` used to
answer `Just (lock it)` on every single reading for as long as the banner was
up. Because that arm sits above `dronesAssistTheCommander` and above the
combat arm in `wingmanDecisionRootInSpace`, and the first arm to answer `Just`
ends the reading, the bot could never reach its drones or its guns while a
target was called. It locked what it was told to, correctly and repeatedly,
and then never shot it: locking read as working, engaging read as broken.

So this answers `Just` only while there is something left to do about the
lock. Once the target is locked, the reading falls through to the drone arm and
then to `fireOnActiveTarget`.

**How "locked" is decided is the whole of #389** -- the first shape of this
asked the target bar's rendering and got the wrong answer on every reading of
four live sessions. `calledTargetIsLocked` is that argument.

**What the broadcast named is asked before any of that, and #393 is why.** A
`Target` on an acceleration gate is the commander sending the crew through it
rather than a call to shoot it, so that case never reaches the lock at all --
see `calledObjectOnOverview`. The check sits at the head of this function rather
than behind the lock because #366 replaces the cascade below with a ctrl-click
on the broadcast banner, and a ctrl-click will lock a gate as happily as the
cascade does: a gate check placed behind the lock would be dead the moment that
lands. That is the same reason #366 gives for keeping the fleet-member guard
ahead of the click, and the fleet-member guard itself is transparent here, since
a gate is not a pilot.

-}
bringCalledTargetUnderFire : BotDecisionContext -> String -> Maybe DecisionPathNode
bringCalledTargetUnderFire context calledTarget =
    let
        shootIt : Maybe DecisionPathNode
        shootIt =
            if calledTargetIsLocked calledTarget context.readingFromGameClient then
                Nothing

            else
                Just
                    (describeBranch
                        ("Lock the called target '" ++ calledTarget ++ "'.")
                        (lockCalledTarget context calledTarget)
                    )
    in
    case calledObjectOnOverviewFromReading calledTarget context.readingFromGameClient of
        CalledObjectIsAnAccelerationGate gateEntry ->
            takeTheCalledAccelerationGate context calledTarget gateEntry

        CalledGateIsNotDisplayed ->
            -- The row names a gate and is not drawn, so its region belongs to
            -- whatever was recycled into its place and clicking it is worse
            -- than a no-op. Hand the reading back rather than park on a wait:
            -- `describeCalledObject` says so on every reading, and the drones
            -- and the guns still get their turn -- which is #389's own closing
            -- note about an arm above them answering `Just` forever.
            Nothing

        CalledObjectIsNotAGate ->
            shootIt

        CalledNameNamesNoOverviewRow ->
            -- #395: the banner is a last-broadcast display and never clears, so
            -- a called target that dies leaves this arm asking for a lock at a
            -- name nothing on the grid carries -- and the drones, the guns, the
            -- gate and the approach below it are all unreachable while it does.
            -- Past the bound there is nothing more this arm can do about the
            -- call, so it hands the reading back; `describeCalledObject` is what
            -- goes on saying the call is unanswerable, since a `Nothing` carries
            -- no decision line. Asked before the lock rather than inside it,
            -- because the give-up is the arm's answer and `lockCalledTarget`
            -- answers a `DecisionPathNode` that cannot decline.
            if calledTargetHasBeenGivenUpOn calledTarget context.memory.calledTargetGone then
                Nothing

            else
                shootIt


{-| The called target this arm would be trying to lock and can find no row for,
if this reading is one of those.

**One rule, both readers**, which is what keeps #395's counter measuring the
readings its own give-up bounds. `updateMemoryForNewReadingFromGame` never sees a
decision, so without this it would have had to restate the arm's precondition --
and the two restatements drifting is the defect `gateAskedReadings` was filed on
(#145: a counter advancing on readings spent merely _near_ a gate, against a
give-up about readings spent _asking_ one).

Both of the arm's own conditions are here. The fleet-member guard in
`actOnFleetBroadcast` answers above this arm and never reaches it, so a call on a
fleetmate must spend none of the budget; and the classification is the same
`calledObjectOnOverviewFromReading` the arm dispatches on, so a called gate whose
row is merely not drawn is not counted as a name nothing carries.

-}
calledTargetWithNoOverviewRow : List String -> ReadingFromGameClient -> Maybe String
calledTargetWithNoOverviewRow followFleetBroadcastFrom readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen targetBroadcastPilotName
        |> Maybe.andThen
            (\calledTarget ->
                if
                    List.member calledTarget
                        (fleetPilotNamesFromReading followFleetBroadcastFrom readingFromGameClient)
                then
                    Nothing

                else
                    case calledObjectOnOverviewFromReading calledTarget readingFromGameClient of
                        CalledNameNamesNoOverviewRow ->
                            Just calledTarget

                        _ ->
                            Nothing
            )


{-| How many consecutive readings the banner's called target has named no
overview row, carried with the name it is counting for.

**What clears it is every one of the three ways the state can end**, and all
three are the same clause: this reading is not one
`calledTargetWithNoOverviewRow` answers `Just` for. A row coming back, the
commander calling something else, and the banner going away are all `Nothing`
here, so the count starts from one again -- which is what stops a give-up latched
on a dead target from being spent on the next call the fleet makes.

-}
calledTargetGoneAfterReading : Maybe CalledTargetGone -> Maybe String -> Maybe CalledTargetGone
calledTargetGoneAfterReading before calledTargetWithNoRow =
    case calledTargetWithNoRow of
        Nothing ->
            Nothing

        Just calledTarget ->
            case before of
                Just gone ->
                    if gone.calledTarget == calledTarget then
                        Just { gone | readings = gone.readings + 1 }

                    else
                        Just { calledTarget = calledTarget, readings = 1 }

                Nothing ->
                    Just { calledTarget = calledTarget, readings = 1 }


{-| How many readings in a row the banner may name a target no overview row
carries before this arm stops trying to lock it and hands the reading back.

**Three, and what it is protecting against is a reading rather than a range.**
`CalledNameNamesNoOverviewRow` is not the overview _virtualising_: a row scrolled
out of view is still in the tree, and `overviewRowsForPilot` filters on the Name
cell rather than on `_display`, so a hidden row still answers
`CalledObjectIsNotAGate`. This state is the stronger one -- no window holds a row
with that name at all -- which a live target reaches only by leaving the
overview's own range filter, or by a reading whose overview did not parse.

So the number bounds a parse that missed rather than a target drifting, and
three is the count this repo already gives that doubt: CLAUDE.md's ship-loss
signal wants three consecutive readings of an empty module row "because the
parser drops any slot whose display region it cannot read, so one reading
finding none may be a parse that missed". The two costs are asymmetric and both
small -- being late costs three readings of this arm holding, being early costs
one lock not issued on a target whose row is back next reading, and the count
resets the moment it is, so the arm re-arms itself.

Deliberately far below `weaponsAskedReadingsBound` (20) and
`accelerationGateRefusesThisShipTicks` (40): those bound a _click_ the client
keeps refusing, where this bounds a reading in which there is nothing to click.

-}
calledTargetGoneReadings : Int
calledTargetGoneReadings =
    3


{-| Whether the call for this name has been given up on. One comparison with two
readers -- the arm and the status clause -- so a give-up decided in one place and
reported in another cannot disagree about whether it happened;
`accelerationGateHasBeenGivenUpOn`'s arrangement, and the same `bound < count`
so the two bounds are read the same way.

**It refuses to answer for any name but its own.** The memory update runs before
the decision on the same reading, so the record cannot be about a different call
than the arm is asking about -- but a rule that would answer anyway is one a
later caller could ask from somewhere that does not hold, and the name is right
there.

-}
calledTargetHasBeenGivenUpOn : String -> Maybe CalledTargetGone -> Bool
calledTargetHasBeenGivenUpOn calledTarget gone =
    case gone of
        Nothing ->
            False

        Just goneTarget ->
            (goneTarget.calledTarget == calledTarget)
                && (calledTargetGoneReadings < goneTarget.readings)


{-| Whether the called target is already in this ship's lock bar.

**Ask the client, do not pattern-match a name against a rendering.** #361 asked
this of the target bar alone, through `lockedTargetNamed`, and #389 is what
that cost: all four pilots looped on `Lock the called target 'Centus Black Ops
Agent'` while their own status lines reported 3, 2 and 1 targets locked, and
every cascade died on `Could not find menu entry with text equal 'Lock Target'`
-- because the thing was already locked and the client was offering `Unlock
Target`. The arm never stood down, so the drones and the guns below it were
never reached.

The bar cannot answer this reliably. #303 read one off a live client with a rat
locked and got `['Tower Sentry', 'Sansha I', '20 km']`: **the name is split
across labels at a wrap point**, and `targetTextsCarryName` asks whether any one
label carries the whole name. A called target whose name wraps -- which is most
of them -- is invisible to that question however long it sits in the bar.

`targetedByMe` is the client's own answer, off the `targetedByMeIndicator` icon
the overview draws on a row this ship has locked, and it is read from the row
the broadcast named -- the same row `lockCalledTarget` right-clicks, so the
thing that decides and the thing that acts cannot disagree about which object
they mean. That is #303's own prescription, applied here.

**The bar is kept as a second opinion rather than dropped.** Either signal
standing alone is enough to stand down. Nothing in this repo has yet watched
`targetedByMeIndicator` come back from a client (see WINGMAN.md), and the two
fail in opposite directions: the bar goes quiet on a wrapped name, the icon
would go quiet if this client draws it under a different name. Standing down on
either is the safe direction -- a false stand-down costs one reading falling
through to the drones and the guns, which is where the reading is wanted
anyway, while a false "not locked" is the loop above.

-}
calledTargetIsLocked : String -> ReadingFromGameClient -> Bool
calledTargetIsLocked calledTarget reading =
    overviewRowSaysThisShipHasItLocked calledTarget reading
        || (lockedTargetNamed calledTarget reading /= Nothing)


{-| Whether the client draws its own lock indicator on this pilot's overview
row.

`targetedByMe` is set from the `targetedByMeIndicator` sprite, and the row is
resolved through `overviewEntryForPilot` -- the same lookup `lockCalledTarget`
clicks and `ensureShipIsOrbiting` selects, so the half that decides and the half
that acts cannot end up on two different objects.

**Lifted out by #390 so there is exactly one of it**, the same argument
`targetTextsCarryName`'s own note makes for the bar: `calledTargetIsLocked` asks
this of the broadcast's name, and `friendlyFireStepFromReading` asks it of every
name in the two no-shoot lists. A second copy is a second instrument that can
disagree with the first.

**It needs the pilot to have a row on this overview**, which is why it is only
ever _added_ to the target bar's answer and never put in its place: an overview
preset that hides fleet members is already a recorded hazard for
`approachTheFleetCommander`, and a locked pilot who has left the grid is
another.

-}
overviewRowSaysThisShipHasItLocked : String -> ReadingFromGameClient -> Bool
overviewRowSaysThisShipHasItLocked pilotName reading =
    overviewEntryForPilot pilotName reading
        |> Maybe.map (.commonIndications >> .targetedByMe)
        |> Maybe.withDefault False


{-| What kind of object the commander's `Target` broadcast named, as four named
answers over the overview rows carrying that name -- the shape
`accelerationGateActivationStep` uses, so a case can execute it rather than
needing a whole `BotDecisionContext` to reach it.

**A gate is licence to activate it, not to shoot it, and only a gate.** There is
no fleet broadcast that says _take this gate_ -- `Align to` names no object at
all -- so `Target` is the only form carrying an object's identity, and on an
acceleration gate it is the commander sending the crew through. That is a
deliberate reinterpretation of one verb where the named object is a gate, and
nowhere else: everything that is not a gate still goes to the lock.

**The answer carries the row**, so the press and the classification are about
one object by construction. A `Bool` beside a second `List.head` is exactly the
shape #303 and #389 both cost this bot -- a state read off one row while the
click is aimed at another.

**Four answers rather than two, because the two silences are different
diagnoses**, and one of them is the risk this change ships with.
`CalledNameNamesNoOverviewRow` is what a broadcast whose rendering does **not**
match the overview's Name cell looks like -- and nobody has ever captured a
`Target` broadcast naming an acceleration gate, so whether
`targetBroadcastPilotName`'s string and `objectName` agree for a gate is
**unknown**. It cannot be settled from here: there is no client. So the two are
kept apart, both are named in the status line by `describeCalledObject`, and the
failure direction is that a gate reads as an ordinary called target and goes to
the lock path this bot takes today -- which then says `is not on the overview`,
loudly.

**`CalledGateIsNotDisplayed` is where a `_display` filter belongs and
`calledTargetIsLocked` is where it does not.** That one takes a name and an
indicator off a node and uses no **region**; this one hands a row to a click,
and CLAUDE.md's rule names the region as what a hidden row makes untrustworthy:
"a hidden entry reports a plausible region pointing at a row that now belongs to
something else, so clicking it is worse than a no-op". This click ends in a gate
being activated.

-}
calledObjectOnOverview : List OverviewWindowEntry -> CalledObjectOnOverview
calledObjectOnOverview rowsNamingIt =
    let
        gateRows : List OverviewWindowEntry
        gateRows =
            rowsNamingIt |> List.filter overviewEntryIsAnAccelerationGate
    in
    case gateRows |> List.filter overviewEntryIsDisplayed |> List.head of
        Just gateEntry ->
            CalledObjectIsAnAccelerationGate gateEntry

        Nothing ->
            if not (List.isEmpty gateRows) then
                CalledGateIsNotDisplayed

            else if List.isEmpty rowsNamingIt then
                CalledNameNamesNoOverviewRow

            else
                CalledObjectIsNotAGate


type CalledObjectOnOverview
    = CalledNameNamesNoOverviewRow
    | CalledObjectIsNotAGate
    | CalledGateIsNotDisplayed
    | CalledObjectIsAnAccelerationGate OverviewWindowEntry


{-| The rule above, asked of a reading, so the arm and the status clause ask one
rule rather than two restatements of it. `overviewRowsForPilot` is the same row
selection `lockCalledTarget` and `calledTargetIsLocked` take their head of.
-}
calledObjectOnOverviewFromReading : String -> ReadingFromGameClient -> CalledObjectOnOverview
calledObjectOnOverviewFromReading calledTarget readingFromGameClient =
    overviewRowsForPilot calledTarget readingFromGameClient
        |> calledObjectOnOverview


{-| The acceleration gate the current `Target` broadcast names, if it names one.

The same question `bringCalledTargetUnderFire` asks, over a reading rather than
a name, so that `updateMemoryForNewReadingFromGame` -- which never sees a
decision -- can ask it too. Both go through `calledObjectOnOverviewFromReading`,
so the arm and the counters cannot disagree about which gate is called.

The one thing this does not repeat is `actOnFleetBroadcast`'s fleet-member
guard, which refuses a called target named in `fleetPilotNames`. A gate is not a
pilot, so the two cannot select the same row unless a fleet member is named
after an acceleration gate.

-}
calledAccelerationGateFromReading : ReadingFromGameClient -> Maybe OverviewWindowEntry
calledAccelerationGateFromReading readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen targetBroadcastPilotName
        |> Maybe.andThen
            (\calledTarget ->
                case calledObjectOnOverviewFromReading calledTarget readingFromGameClient of
                    CalledObjectIsAnAccelerationGate gateEntry ->
                        Just gateEntry

                    _ ->
                        Nothing
            )


{-| The locked target whose target-bar text carries this name, if it is
locked at all.

Matched against `textsTopToBottom`, which is the only field that names what is
in the bar -- and the reason `unlockFleetPilotInTargetBar` has to come through
here: the unlock right-clicks a `Target`, so it needs the bar entry itself and
not merely the knowledge that something is locked. The texts carry distance and
other decoration alongside the name, so this contains rather than equals.

**This is a weak instrument and `calledTargetIsLocked` says why.** A name the
bar wraps across two labels is not found here at all. Read that note before
adding a third caller.

-}
lockedTargetNamed : String -> ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.Target
lockedTargetNamed name reading =
    reading.targets
        |> List.filter (.textsTopToBottom >> targetTextsCarryName name)
        |> List.head


{-| The comparison `lockedTargetNamed` is, over the texts alone.

**Lifted out so there is exactly one of it.** #367's guard has to ask the same
question of every locked target on every reading, and a second matcher that
can disagree with this one is the defect that guard exists to avoid: a lock bar
the guard reads as clean and `lockedTargetNamed` reads as holding the pilot
would fire on somebody nobody could then find. It is also what lets
`friendlyFireStep` be a rule over plain lists rather than over a reading.

An empty `name` would contain into every text, so callers building the name
list filter empties out -- see `fleetPilotNamesFromReading`.

**What it cannot see, recorded because #389 was filed on it.** The bar wraps a
long name across labels -- a live read in #303 with a rat locked returned
`['Tower Sentry', 'Sansha I', '20 km']` -- and this asks whether any _one_ label
carries the whole name, so a wrapped name is not matched at all. #389 moved the
called-target recognition off this and onto the overview's own `targetedByMe`
for that reason, and #390 did the same for the friendly-fire guard -- a
fleetmate whose name the bar wraps was not recognised as locked, and the guard
fell through to `ClearToFire`, which fails in the direction #367 exists to
prevent.

**Neither of them dropped this.** Both ask it _and_ the row indicator and take
the answer that refuses, because the two go quiet in opposite directions: this
one on a wrapped name, the row when the pilot has no row on this overview at
all. See `lockSignalForPilot`.

-}
targetTextsCarryName : String -> List String -> Bool
targetTextsCarryName name textsTopToBottom =
    textsTopToBottom |> List.any (stringContainsIgnoringCase name)


{-| Lock the object a `Target` broadcast named.

**Ctrl-clicking the broadcast banner is what does it, and #366 is why.** Holding
Ctrl over the banner's own `Target:` display locks the object the broadcast
refers to: one dispatch, no context menu, and no overview lookup at all. What it
replaces is a `Lock Target` cascade on a row found by matching
`targetBroadcastPilotName`'s parse of the banner against `objectName` by exact
equality -- two string derivations that both have to agree, about an object the
client itself already knows the identity of. Three costs go with them: a target
outside the active overview preset was one this bot simply never shot, a
rendering the parse and the Name cell spell differently was the same, and a
cascade is where this bot's readings and its bugs go (#329's `entryLabel`
collision, `contextMenuStuckTicks`, #285's unbounded loot-window branch).

**The two guards that must be ahead of the click are ahead of it by placement,
and neither of them is in here.** A ctrl-click locks a fleet member as happily
as a rat, so `actOnFleetBroadcast` refuses a called target named in
`fleetPilotNames` before this function is reached at all -- which is why
`targetBroadcastPilotName` is still needed for the _decision_ long after the
lock stopped needing it. And a ctrl-click locks a gate as happily as a ship, so
`bringCalledTargetUnderFire` dispatches on `calledObjectOnOverviewFromReading`
and hands a called acceleration gate to the gate machinery before it builds the
lock at all (#393). Both are placements rather than conditions, which is what
`test_the_gate_check_is_what_the_arm_dispatches_on` already pins.

**The cascade is kept as the fall-back rather than deleted**, and the reason is
an unknown rather than caution: what the client does with a ctrl-click on the
banner when the object is out of lock range, already locked, or a structure
rather than a ship is **not established** -- nobody has captured it and there is
no client here to capture it with. So the fall-back is reachable on _any_
failure to lock rather than on a diagnosis this bot cannot make.
`bannerCtrlClickAskedReadingsBound` readings of clicking with the target still
not reading locked hands it to the cascade, and so does a reading whose banner
offers nothing to click.

**What a called target with no overview row does now, and it is the case this
change is for.** The click is attempted -- the banner is on screen whatever the
overview is showing -- and it is attempted **because** there is no row rather
than in spite of one. Nothing here is gated on finding one: written as "find the
row, and ctrl-click the banner if there is one", the whole defect would survive
and only the gesture would change.

**A missing row is not evidence that the target is dead**, and reading it that
way is the mistake this paragraph exists to stop. Three states produce it and
only one of them is death: the object really is gone, _this pilot's overview
preset does not show it_ (four characters, non-identical presets), or the
wording the banner carries is not the overview's Name cell. In the second and
third the ctrl-click is the only thing in this bot that can lock the target at
all, because the cascade needs the row it has not got.

**The ordering against #395 is what that buys.** That give-up is asked in
`bringCalledTargetUnderFire`, before the lock, and fires at
`calledTargetGoneReadings` -- below this bound, so every reading it allows is a
reading the click is attempted on. It comes to mean _the banner was tried too
and nothing locked_ rather than _there was no row, so we assumed it died_, and
it still hands the reading back, which is still right once there is nothing left
to try.

-}
lockCalledTarget : BotDecisionContext -> String -> DecisionPathNode
lockCalledTarget context calledTarget =
    let
        nothingToLockItWith : DecisionPathNode
        nothingToLockItWith =
            describeBranch
                ("'"
                    ++ calledTarget
                    ++ "' is not on the overview and its broadcast banner is not in this reading either, so there is nothing here to lock it with."
                )
                waitForProgressInGame
    in
    case lockCalledTargetStepFromReading context.memory.bannerCtrlClick context.readingFromGameClient calledTarget of
        CtrlClickTheBroadcastBanner ->
            -- One lookup with two readers -- the rule's own
            -- `bannerOffersACtrlClick` and the click made here -- so the rule
            -- cannot decide to click a banner this branch then fails to find.
            -- `inactiveWeaponFromReading`'s arrangement, and the fall-back
            -- below is what makes the impossible case honest rather than
            -- silent.
            calledTargetBannerCtrlClick context.readingFromGameClient
                |> Maybe.map
                    (\effectsToClick ->
                        describeBranch
                            ("Ctrl-click the fleet broadcast banner to lock '"
                                ++ calledTarget
                                ++ "' -- one dispatch, no context menu and no overview row needed."
                            )
                            (decideActionForCurrentStep effectsToClick)
                    )
                |> Maybe.withDefault nothingToLockItWith

        LockFromTheOverviewRow ->
            overviewEntryForPilot calledTarget context.readingFromGameClient
                |> Maybe.map
                    (\overviewEntry ->
                        describeBranch
                            ("Lock '"
                                ++ calledTarget
                                ++ "' from its overview row, which is the fall-back for a banner this bot could not lock it with."
                            )
                            (useContextMenuCascadeOnOverviewEntry
                                (useMenuEntryWithTextEqual "Lock Target" menuCascadeCompleted)
                                overviewEntry
                                context
                            )
                    )
                |> Maybe.withDefault nothingToLockItWith

        NoWayToLockTheCalledTarget ->
            nothingToLockItWith


{-| Which of the two ways of locking a called target this reading offers, as
three named answers over two facts and a counter -- `weaponsStep`'s shape, for
its reason: a rule reachable only through a whole `BotDecisionContext` is a rule
nothing can execute in a test, and this one is asked by three readers.

**The bound is asked with the banner rather than after it**, so a click that has
been given up on hands the reading to the cascade instead of being re-issued
forever. That ordering is the whole of the fall-back: `weaponsStep` puts its own
give-up above "is there anything to do" for the same reason.

**`NoWayToLockTheCalledTarget` is not a third mechanism**, it is the state in
which neither exists on this reading -- the banner absent and no overview row
carrying the name. The arm speaks it and waits, and what bounds that wait is
#395's give-up in `bringCalledTargetUnderFire`, unchanged: the only route to
this answer is `CalledNameNamesNoOverviewRow`, since the other caller of the
lock has a row by construction.

-}
lockCalledTargetStep :
    { bannerOffersACtrlClick : Bool
    , overviewRowIsInTheReading : Bool
    , askedReadings : Int
    }
    -> LockCalledTargetStep
lockCalledTargetStep { bannerOffersACtrlClick, overviewRowIsInTheReading, askedReadings } =
    if bannerOffersACtrlClick && not (bannerCtrlClickHasBeenGivenUpOn askedReadings) then
        CtrlClickTheBroadcastBanner

    else if overviewRowIsInTheReading then
        LockFromTheOverviewRow

    else
        NoWayToLockTheCalledTarget


type LockCalledTargetStep
    = CtrlClickTheBroadcastBanner
    | LockFromTheOverviewRow
    | NoWayToLockTheCalledTarget


{-| The rule above, asked of a reading and a memory, so the arm, the counter and
the status clause are all reading one decision -- `weaponsStepFromReading`'s
arrangement, for #102's reason.
-}
lockCalledTargetStepFromReading : Maybe BannerCtrlClickAsk -> ReadingFromGameClient -> String -> LockCalledTargetStep
lockCalledTargetStepFromReading bannerCtrlClick readingFromGameClient calledTarget =
    lockCalledTargetStep
        { bannerOffersACtrlClick = calledTargetBannerCtrlClick readingFromGameClient /= Nothing
        , overviewRowIsInTheReading = overviewEntryForPilot calledTarget readingFromGameClient /= Nothing
        , askedReadings = bannerCtrlClickAskedReadings calledTarget bannerCtrlClick
        }


{-| The ctrl-click on the broadcast banner, as the effects that dispatch it.

One lookup answering both "is there a banner to click" and "what does clicking
it dispatch", so the rule and the arm cannot disagree -- and `Nothing` covers
the element being absent from the reading _and_ its visible region being too
small to click, which are two ways of failing to click that want one answer.

-}
calledTargetBannerCtrlClick : ReadingFromGameClient -> Maybe (List EffectOnWindow.EffectOnWindowStruct)
calledTargetBannerCtrlClick readingFromGameClient =
    fleetBroadcastBannerElement readingFromGameClient
        |> Maybe.andThen ctrlClickEffects


{-| EVE's own shortcut for acting on an object directly: hold Ctrl and left
click it, no context menu involved.

**One copy of the chord, because it was written twice.**
`fightRatsIfShipIsPointed` has held Ctrl over the pointed buff since the
original skeleton and `lockCalledTarget` holds it over the broadcast banner
since #366; saxrat's `ctrlShiftClickUiElement` is the two-modifier version of
the same gesture. A chord built wrong is one the client reads as a plain click,
which locks nothing and says nothing, so two copies are two chances for one of
them to drift.

**`Nothing` is a decline the caller has to speak, not an empty effect list.**
`mouseClickOnUIElement` answers `Err` for an element whose visible region is too
small to click, and dispatching `[]` on that is a branch that prints an action
and dispatches nothing -- this repo's signature failure, and what saxrat's copy
of this gesture still does. Each caller answers it in its own words because the
two want different answers: the pointed path asks for help, the lock path falls
back to the cascade.

-}
ctrlClickEffects : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Maybe (List EffectOnWindow.EffectOnWindowStruct)
ctrlClickEffects uiElement =
    case mouseClickOnUIElement MouseButtonLeft uiElement of
        Err _ ->
            Nothing

        Ok effectToClick ->
            Just
                (List.concat
                    [ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]
                    , effectToClick
                    , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]
                    ]
                )


{-| How many readings in a row this bot ctrl-clicks the broadcast banner for one
called target before it stops and lets the overview cascade have it.

**Five, and it is not a measurement.** This bot has no corpus of its own; see
WINGMAN.md. What sizes it is what the click _is_: one dispatch with no menu to
render and no flyout to wait on, so unlike a cascade it either reaches the
client or it does not, and what the readings are for is the client's own lock-in
time -- a lock takes seconds and a reading is one to eight. So it sits far below
the three bounds in this file that budget a cascade the client keeps refusing
(`weaponsAskedReadingsBound` 20, `fleetMateWarpAskedReadingsBound` 30,
`accelerationGateRefusesThisShipTicks` 40), which have a menu to open on every
attempt.

**Above `calledTargetGoneReadings` (3) deliberately, and the ordering is the
point rather than the arithmetic.** #395's give-up is asked before the lock, on
exactly the state where there is no overview row -- so with this bound above it,
**every reading that give-up allows is a reading the banner was clicked on**.
That is what turns it from _there was no row, so we assumed it died_ into _the
banner was tried too and nothing locked_. The other order would have this budget
run out first and hand a no-row call to a cascade that has no row to open a menu
on, which is a fall-back that cannot work; see `lockCalledTarget` for why a
missing row is not evidence the target is dead.

So what this bound is really for is the other case: a call that **does** have a
row, on which the click does not land. That is the one thing about the
ctrl-click nobody has watched, and the cascade is a mechanism that can serve it.

Past it `lockCalledTargetStep` answers `LockFromTheOverviewRow` rather than
handing the reading back, because there is a second mechanism here to try --
which is what makes this bound unlike every other give-up in this file.

-}
bannerCtrlClickAskedReadingsBound : Int
bannerCtrlClickAskedReadingsBound =
    5


{-| Whether the banner click has been given up on for this call. One comparison
with two readers -- the step rule and the status clause --
`accelerationGateHasBeenGivenUpOn`'s arrangement, for its reason.
-}
bannerCtrlClickHasBeenGivenUpOn : Int -> Bool
bannerCtrlClickHasBeenGivenUpOn askedReadings =
    bannerCtrlClickAskedReadingsBound <= askedReadings


{-| How many readings the banner click has been asked on for this call.

**It refuses to answer for any name but its own**, which is
`calledTargetHasBeenGivenUpOn`'s posture and for the same reason: a record about
the last call must not spend the next call's budget, which is the shape #145's
gate counter was filed on.

-}
bannerCtrlClickAskedReadings : String -> Maybe BannerCtrlClickAsk -> Int
bannerCtrlClickAskedReadings calledTarget bannerCtrlClick =
    case bannerCtrlClick of
        Nothing ->
            0

        Just ask ->
            if ask.calledTarget == calledTarget then
                ask.readings

            else
                0


{-| The counter behind that bound, folded one reading at a time.

**It advances only on the readings the click is actually asked on**, which is
#389's lesson and this file has already paid for it once: `weaponsAskedReadings`
advanced from state alone and reported `GAVE UP after 46 readings` on an arm
that had never been asked, on three pilots at 46, 36 and 50 against a bound
of 20. `asked` here is the shipped rule answering `CtrlClickTheBroadcastBanner`,
not a restatement of when it might.

**It holds rather than clearing on a reading that did not ask**, while the same
call is still the lock's question -- `weaponsAskedReadings`' own arrangement. A
counter that cleared there would clear on the very reading the bound was
reached, since past the bound the rule stops asking: the fall-back would last
exactly one reading and the click would be re-issued for ever.

**It clears when the lock is no longer the question at all**, which is one
clause covering every way this ends: the target coming up locked (the click
worked), the commander calling something else, the call turning out to be a
gate or a fleetmate, #395 giving up on it, and the banner going away. A
different call starts from its own first reading rather than inheriting the last
one's arrears.

-}
bannerCtrlClickAfterReading :
    Maybe BannerCtrlClickAsk
    -> { calledTarget : Maybe String, asked : Bool }
    -> Maybe BannerCtrlClickAsk
bannerCtrlClickAfterReading before thisReading =
    case thisReading.calledTarget of
        Nothing ->
            Nothing

        Just calledTarget ->
            let
                spent : Int
                spent =
                    if thisReading.asked then
                        1

                    else
                        0
            in
            case before of
                Just ask ->
                    if ask.calledTarget == calledTarget then
                        Just { ask | readings = ask.readings + spent }

                    else
                        Just { calledTarget = calledTarget, readings = spent }

                Nothing ->
                    Just { calledTarget = calledTarget, readings = spent }


{-| What this reading is, to the counter above: which call the lock is working
on, and whether the click was asked for it.

**One rule, both readers**, the arrangement `calledTargetWithNoOverviewRow`
already uses next door and for #145's reason: `updateMemoryForNewReadingFromGame`
never sees a decision, so without this it would restate the arm's precondition
and the two restatements would drift.

Every one of the arm's own conditions is here, and each is a way the budget
could be charged for a reading nothing spent. The fleet-member guard in
`actOnFleetBroadcast` answers above this arm; `bringCalledTargetUnderFire`
answers `Nothing` for a target already locked and hands a called gate to the
gate machinery; and #395's give-up answers before the lock. All four are asked
through the shipped rules rather than restated.

-}
bannerCtrlClickThisReading :
    { followFleetBroadcastFrom : List String
    , calledTargetGone : Maybe CalledTargetGone
    , bannerCtrlClick : Maybe BannerCtrlClickAsk
    }
    -> ReadingFromGameClient
    -> { calledTarget : Maybe String, asked : Bool }
bannerCtrlClickThisReading state readingFromGameClient =
    case calledTargetTheLockIsWorkingOn state.followFleetBroadcastFrom state.calledTargetGone readingFromGameClient of
        Nothing ->
            { calledTarget = Nothing, asked = False }

        Just calledTarget ->
            { calledTarget = Just calledTarget
            , asked =
                lockCalledTargetStepFromReading state.bannerCtrlClick readingFromGameClient calledTarget
                    == CtrlClickTheBroadcastBanner
            }


{-| The called target `lockCalledTarget` is being asked to lock on this reading,
if there is one.

The arm's route to the lock, over a reading rather than a decision, so the
counter and the status clause can ask it. Everything it declines is a reading on
which no lock is issued: a call on a fleetmate (refused above this arm), a call
on an acceleration gate or one whose gate row is not drawn (#393 answers both),
a target already locked (#360's stand-down, read through the client's own
indicator since #389), and a call #395 has given up on.

-}
calledTargetTheLockIsWorkingOn : List String -> Maybe CalledTargetGone -> ReadingFromGameClient -> Maybe String
calledTargetTheLockIsWorkingOn followFleetBroadcastFrom calledTargetGone readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen targetBroadcastPilotName
        |> Maybe.andThen
            (\calledTarget ->
                if
                    List.member calledTarget
                        (fleetPilotNamesFromReading followFleetBroadcastFrom readingFromGameClient)
                        || calledTargetIsLocked calledTarget readingFromGameClient
                then
                    Nothing

                else
                    case calledObjectOnOverviewFromReading calledTarget readingFromGameClient of
                        CalledObjectIsAnAccelerationGate _ ->
                            Nothing

                        CalledGateIsNotDisplayed ->
                            Nothing

                        CalledObjectIsNotAGate ->
                            Just calledTarget

                        CalledNameNamesNoOverviewRow ->
                            if calledTargetHasBeenGivenUpOn calledTarget calledTargetGone then
                                Nothing

                            else
                                Just calledTarget
            )


{-| Launch drones from the bay, with nothing yet to redirect them to.

**Unwired scaffolding from the original wingman skeleton (#337), predating
`dronesAssistTheCommander`, and left dead until #374.** Its "Assist first, `F`
second" cascade choice was superseded by the `MenuEntryWithCustomChoice` now
built into `dronesAssistTheCommander` itself, which is why this is a plain
launch rather than a second assist cascade -- two arms both choosing between
`Assist` and `Engage Target` would be two answers to the same question. What
it still supplies, and what nothing else on this bot's reachable decision path
did, is the bay-launch half of `launchAndEngageDrones`: `considerLaunch`'s own
quantity, space-limit and bandwidth gating, reused rather than duplicated.

`dronesAssistTheCommander` is this function's only caller, reached when it has
no idling drone to redirect -- so a session that never sees this launch
anything is a session whose bay was already empty or already at the space
limit, not one where the call site is unreached.

-}
dronesForTheFleet : BotDecisionContext -> Maybe DecisionPathNode
dronesForTheFleet context =
    launchAndEngageDrones { redirectToTargets = Nothing } context


{-| How long before the planned session end to stop taking new work and head
home. Named the same as the mission runner's constant of the same name and
the same value (200s), because it is the same question -- "enough time to
finish a warp and a dock, not so much that a short session never gets
anything done" -- asked by both `sessionIsEnding` and
`dockedSessionIsEnding` below and by `hostDirectiveExtendSession`, so the
three cannot silently disagree about when the wind-down starts.
-}
secondsBeforeSessionEndToWindDown : Int
secondsBeforeSessionEndToWindDown =
    200


{-| How long past the planned session end the trip home may run before this
bot gives up trying to reach it and ends the session where it is instead.
Ported from the mission runner's `homeStationTripSecondsPastSessionEnd` --
same number (420s), same argument: a couple of jumps plus a dock is several
minutes, well past the 200s window the wind-down starts in, and cutting the
trip off mid-flight strands the ship exactly where #350 found it. #7 and #14
are both the same shape this refuses to repeat: a wait with no end reads in
the log exactly like a bot working. This is a longer bound, not a missing
one -- past it the session ends, loudly, naming the station it never reached.
-}
tripHomeSecondsPastSessionEnd : Int
tripHomeSecondsPastSessionEnd =
    420


{-| The `@host extend-session` directive, asking the host to hold the session
open past its planned end while the trip home is under way. Ported from the
mission runner's `hostDirectiveExtendSession` and flattened to this bot's one
wind-down phase -- fly home, then dock, no restock and no pod recovery to
budget separately for.

**A lease, not a setting**, exactly as `hostDirectiveSetDestination` above:
re-derived from live state every reading, so a bot that stops needing the
extension (because it has docked) stops asking for it on the very next
reading, and the host is never handed a deadline it does not also get to see
lapse. Placed as its own last line of the status text -- see
`statusTextFromState` -- because the host scans the whole text for the
`@host` token, but an operator reads the first line as "what is this reading
about", and that has to stay whatever `wingmanDecisionRootInSpace` decided
rather than this bookkeeping.

**Docked asks for nothing.** Once the ship is docked, either the trip
succeeded or was never needed, and `dockedSessionIsEnding` below is what ends
the session from there -- asking for more time here would extend a session
this bot has already decided to finish.

-}
hostDirectiveExtendSession : BotDecisionContext -> String
hostDirectiveExtendSession context =
    case EveOnline.BotFramework.secondsToSessionEnd context.eventContext of
        Nothing ->
            ""

        Just secondsRemaining ->
            if secondsBeforeSessionEndToWindDown < secondsRemaining then
                ""

            else
                case context.readingFromGameClient.shipUI of
                    Nothing ->
                        ""

                    Just _ ->
                        hostDirectivePrefix ++ "extend-session " ++ String.fromInt tripHomeSecondsPastSessionEnd


{-| The trip home, when the session is nearly over.

Sets the destination to `home-station` (default `defaultHomeStation`) through
the same `@host set-destination` directive the travel broadcast already uses,
then flies it with `flyRouteHome` -- which docks at the far end too, since
the route marker's own menu offers "Dock" once the destination station is
reached, the same property `navigateTowardFleetCommander`'s own mechanism
already has. Nothing here needs to know the difference between another jump
and arrival.

**Bounded by `tripHomeSecondsPastSessionEnd`.** Past it, this stops asking
the ship to keep flying and ends the session where it is instead of
repeating #350's own incident under a longer deadline -- see that constant's
own comment.

-}
sessionIsEnding : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
sessionIsEnding context shipUI =
    case EveOnline.BotFramework.secondsToSessionEnd context.eventContext of
        Nothing ->
            Nothing

        Just secondsRemaining ->
            if secondsBeforeSessionEndToWindDown < secondsRemaining then
                Nothing

            else
                let
                    stationName =
                        Maybe.withDefault defaultHomeStation context.eventContext.botSettings.homeStation
                in
                Just
                    (if secondsRemaining <= -tripHomeSecondsPastSessionEnd then
                        describeBranch
                            ("Home station: gave up -- the session ended "
                                ++ String.fromInt -secondsRemaining
                                ++ " seconds ago and I never reached '"
                                ++ stationName
                                ++ "'. Stopping here rather than flying on past the deadline."
                            )
                            (Common.DecisionPath.endDecisionPath EveOnline.BotFrameworkSeparatingMemory.FinishSession)

                     else
                        describeBranch
                            ("Home station: heading to '"
                                ++ stationName
                                ++ "'. "
                                ++ hostDirectiveSetDestination stationName
                            )
                            (flyRouteHome context shipUI)
                    )


{-| Whether a docked ship should stay docked and end the session, once the
session is inside its wind-down window, rather than undocking again.

**Without this, the trip home above is pointless.** `wingmanDecisionRootBeforeApplyingSettings`'s
docked branch has always meant "undock", unconditionally -- nothing before
this distinguished a ship that just arrived home, as the trip's own endpoint,
from a ship docked somewhere else with the wind-down window merely open. A
ship that reached `home-station` would have been undocked again on the very
next reading, reproducing #350's stall one system later instead of fixing
it.

**Gated on actually being at the home station, not merely on being
docked somewhere.** The obvious simpler rule -- "docked and the window is
open, so stay" -- has a real failure mode: a session that starts docked (the
ordinary way to launch this bot) and is given a short
`--session-duration-minutes` would end on its very first reading, never
undocking at all. Comparing `context.memory.lastDockedStationNameFromInfoPanel`
against `home-station` is the same identity `dockedAtHomeStation` uses in the
mission runner, and it is what tells "just arrived home" apart from "docked
somewhere else, or docked before the trip has even started" -- only the
first stays put; the second falls through to the ordinary "Undock." branch,
so the ship still undocks and `sessionIsEnding` above still gets a chance to
route it home before the session actually ends.

**Ends the session rather than waiting**, because there is nothing left to
do once the ship is genuinely home: this bot has no restock and no
maintenance to run while docked, so `sessionIsEnding` above and this
together cover the whole wind-down -- flying while in space, staying put
once docked at the right place.

-}
dockedSessionIsEnding : BotDecisionContext -> Maybe DecisionPathNode
dockedSessionIsEnding context =
    case EveOnline.BotFramework.secondsToSessionEnd context.eventContext of
        Nothing ->
            Nothing

        Just secondsRemaining ->
            if secondsBeforeSessionEndToWindDown < secondsRemaining then
                Nothing

            else
                let
                    stationName =
                        Maybe.withDefault defaultHomeStation context.eventContext.botSettings.homeStation
                in
                if context.memory.lastDockedStationNameFromInfoPanel == Just stationName then
                    Just
                        (describeBranch
                            ("Session ending and docked at the home station '"
                                ++ stationName
                                ++ "' -- stay here rather than undock again."
                            )
                            (Common.DecisionPath.endDecisionPath EveOnline.BotFrameworkSeparatingMemory.FinishSession)
                        )

                else
                    Nothing


{-| Fly the current route home, docking at the far end. The same body as
`navigateTowardFleetCommander`, kept as a separate function rather than a
shared one that both call: the two memory fields it reads
(`routeFirstMarkerRegion`, `routeFirstMarkerUnchangedTicks`) already track
"whatever route the client currently has" rather than anything
commander-specific, so sharing them costs nothing, but a rename touching
`navigateTowardFleetCommander`'s existing call site and every place WINGMAN.md
already names it is exactly the kind of file-wide churn COORDINATION.md's
"land fast, land clean" asks changes on a shared file to avoid while other
machines have their own open branches against it (#347, #348, #349). See
`navigateTowardFleetCommander`'s own comment for the full argument this body
makes, including why the third rung
(`eve-online-warp-to-0-autopilot`'s `jumpCascadeStuckReadings`) is not ported.
-}
flyRouteHome : BotDecisionContext -> ShipUI -> DecisionPathNode
flyRouteHome context shipUI =
    case infoPanelRouteFirstMarkerFromReadingFromGameClient context.readingFromGameClient of
        Nothing ->
            describeBranch
                "No route in the info panel -- either the destination has not taken effect yet, or the route has already been flown to its end and this reading has not yet seen the station window appear."
                waitForProgressInGame

        Just infoPanelRouteFirstMarker ->
            if shipUIIndicatesShipIsWarpingOrJumping shipUI then
                describeBranch
                    "I see the ship is warping or jumping. I wait until that maneuver ends."
                    waitForProgressInGame

            else if context.memory.routeFirstMarkerUnchangedTicks < 1 then
                describeBranch
                    "Route panel's first marker just appeared or moved since the last reading -- wait for the route to finish (re)computing before clicking it."
                    waitForProgressInGame

            else
                jumpThroughRouteStargate context
                    (routeMarkerCascade context infoPanelRouteFirstMarker)


{-| What a fleet broadcast is asking for.

**Six shapes, all observed live**, across four runs on three hosts plus the
original UI-tree capture. They fall into three grammars rather than one, which
is why this is a parser and not a prefix test:

  - `Target <name> (<hull>)` -- no sender at all;
  - `<Sender>: <verb> <argument>` -- sender behind a colon;
  - `<Sender> is at location <system>` -- sender with no colon.

`Unrecognized` is not a failure. It carries the text so the caller can open the
broadcast's own context menu and read what the client offers for it, which is
how the remaining wordings get captured without guessing at them.

-}
type FleetBroadcast
    = CalledTarget String
    | TravelTo { pilot : String, destination : String }
    | JumpGate { pilot : String, gate : String }
    | AlignGate { pilot : String, gate : String }
    | AtLocation { pilot : String, system : String }
    | InPositionAt { pilot : String, gate : String }
    | NeedBackup { pilot : String }
    | Unrecognized String


{-| Read a broadcast banner, whatever shape it is in.

Ordered most specific first: `is in position at Stargate X` also contains
`is at`, and `Jump Stargate X` is a colon form whose verb happens to start with
a word that appears in others. Matching loosely here would route a broadcast to
the wrong arm, which is worse than not matching it at all.

-}
parseFleetBroadcast : String -> FleetBroadcast
parseFleetBroadcast bannerText =
    let
        trimmed : String
        trimmed =
            String.trim bannerText

        afterColon : Maybe { pilot : String, rest : String }
        afterColon =
            case String.indexes ": " trimmed of
                firstColon :: _ ->
                    Just
                        { pilot = String.left firstColon trimmed |> String.trim
                        , rest =
                            String.dropLeft (firstColon + 2) trimmed |> String.trim
                        }

                [] ->
                    Nothing

        withoutSender : String -> Maybe { pilot : String, argument : String }
        withoutSender marker =
            case String.indexes marker trimmed of
                firstMarker :: _ ->
                    Just
                        { pilot = String.left firstMarker trimmed |> String.trim
                        , argument =
                            String.dropLeft (firstMarker + String.length marker) trimmed
                                |> String.trim
                        }

                [] ->
                    Nothing
    in
    case targetBroadcastPilotName trimmed of
        Just calledTarget ->
            CalledTarget calledTarget

        Nothing ->
            case withoutSender " is in position at Stargate " of
                Just inPosition ->
                    InPositionAt
                        { pilot = inPosition.pilot, gate = inPosition.argument }

                Nothing ->
                    case withoutSender " is at location " of
                        Just atLocation ->
                            AtLocation
                                { pilot = atLocation.pilot
                                , system = atLocation.argument
                                }

                        Nothing ->
                            case afterColon of
                                Nothing ->
                                    -- The colon shapes are exhausted, so the
                                    -- one remaining observed shape is
                                    -- `<Sender> needs backup` -- third person,
                                    -- no colon, the same shape as the two
                                    -- `withoutSender` forms above. It is asked
                                    -- *after* `afterColon` rather than beside
                                    -- them because a banner carrying `": "`
                                    -- would otherwise yield a sender with the
                                    -- colon still stuck to it, and this bot
                                    -- matches a pilot name exactly.
                                    case backupCallSender trimmed of
                                        Just sender ->
                                            NeedBackup { pilot = sender }

                                        Nothing ->
                                            Unrecognized trimmed

                                Just { pilot, rest } ->
                                    parseBroadcastVerb pilot rest trimmed


{-| The sender of a `<Sender> needs backup` broadcast, which carries no colon.

**The marker is the broadcast's own wording and not the button's**, which is
the whole of #385: `parseBroadcastVerb` tested `"need backup"` -- the fleet
window's `Broadcast: Need Backup` button label, first person -- and the client
renders `needs backup`. `"needs backup"` does not contain `"need backup"`,
because after `need` comes `s` rather than a space, so the test was false on
every reading and every backup call this bot has ever seen fell through to
`Unrecognized`. WINGMAN.md already carried the rule in its own words -- _"a
button's wording is not the broadcast's"_ -- and this is the one verb somebody
wired from the button list without a capture to check it against.

`needsBackupMarker` is the single constant both this and `parseBroadcastVerb`
read, `gateKeyClosingMarker`'s arrangement: two copies of a client wording are
two things that can drift apart silently, and a matcher that stops matching is
this repo's signature failure rather than an error.

**A sender is required.** A banner that is nothing but the verb names nobody to
fly to, and `Unrecognized` is the better answer for it -- that opens the
broadcast's own menu, which is how an unread wording gets captured.

-}
backupCallSender : String -> Maybe String
backupCallSender trimmed =
    case String.indexes needsBackupMarker (String.toLower trimmed) of
        firstMarker :: _ ->
            case String.left firstMarker trimmed |> String.trim of
                "" ->
                    Nothing

                sender ->
                    Just sender

        [] ->
            Nothing


{-| How the client writes a backup call, in the third person the banner renders
rather than the first person the button offers. See `backupCallSender`.
-}
needsBackupMarker : String
needsBackupMarker =
    "needs backup"


{-| The verb half of a `<Sender>: <verb> <argument>` broadcast.
-}
parseBroadcastVerb : String -> String -> String -> FleetBroadcast
parseBroadcastVerb pilot rest whole =
    if String.startsWith "Travel to " rest then
        TravelTo
            { pilot = pilot
            , destination = String.dropLeft (String.length "Travel to ") rest
            }

    else if String.startsWith "Jump Stargate " rest then
        JumpGate
            { pilot = pilot
            , gate = String.dropLeft (String.length "Jump Stargate ") rest
            }

    else if String.startsWith "Align Stargate " rest then
        AlignGate
            { pilot = pilot
            , gate = String.dropLeft (String.length "Align Stargate ") rest
            }

    else if stringContainsIgnoringCase needsBackupMarker rest then
        NeedBackup { pilot = pilot }

    else
        Unrecognized whole


{-| Who a broadcast came from, where the shape carries a sender.

`CalledTarget` answers `Nothing`: that form names the target and says nothing
about who called it, which is why `follow-fleet-broadcast-from` cannot gate it.

-}
fleetBroadcastSender : FleetBroadcast -> Maybe String
fleetBroadcastSender broadcast =
    case broadcast of
        CalledTarget _ ->
            Nothing

        TravelTo { pilot } ->
            Just pilot

        JumpGate { pilot } ->
            Just pilot

        AlignGate { pilot } ->
            Just pilot

        AtLocation { pilot } ->
            Just pilot

        InPositionAt { pilot } ->
            Just pilot

        NeedBackup { pilot } ->
            Just pilot

        Unrecognized _ ->
            Nothing


{-| Act on a broadcast that is not a called target and not a travel destination.

The travel and target forms are handled above, where they already were. This is
the rest of the vocabulary, and the arm that faces a wording nobody has read.

**An unrecognized broadcast opens its own context menu rather than waiting.**
That is the one place this bot deliberately acts without knowing what it will
get: the client's menu for a broadcast names what can be done with it, so
opening it and letting the next reading record the entries is how the remaining
wordings get captured. Waiting instead -- which is what this did before -- means
the vocabulary can only ever be learned by a person clicking through the fleet
window by hand.

It costs a right-click on a UI element this bot already has, and the cascade's
own discard rule closes it again if nothing matches.

-}
actOnBroadcastVerb : BotDecisionContext -> ShipUI -> String -> Maybe DecisionPathNode
actOnBroadcastVerb context shipUI bannerText =
    let
        permitted : String -> Bool
        permitted pilot =
            List.member pilot context.eventContext.botSettings.followFleetBroadcastFrom

        say : String -> Maybe DecisionPathNode
        say reason =
            Just (describeBranch reason waitForProgressInGame)
    in
    case parseFleetBroadcast bannerText of
        CalledTarget _ ->
            say "Handled above -- a called target reaches its own branch."

        TravelTo _ ->
            say "Handled above -- a travel destination reaches its own branch."

        AtLocation { pilot, system } ->
            if not (permitted pilot) then
                say
                    ("'"
                        ++ pilot
                        ++ "' is at "
                        ++ system
                        ++ " but is not named in 'follow-fleet-broadcast-from'."
                    )

            else
                goToFleetMate context shipUI pilot system "is at location"

        InPositionAt { pilot, gate } ->
            if not (permitted pilot) then
                say
                    ("'"
                        ++ pilot
                        ++ "' is in position at "
                        ++ gate
                        ++ " but is not named in 'follow-fleet-broadcast-from'."
                    )

            else
                goToFleetMate context shipUI pilot gate "is in position at"

        NeedBackup _ ->
            -- #385. This verb has its own arm, `answerTheBackupCall`, placed
            -- above this whole branch in the decision root: being slow to a
            -- backup call costs a ship where being slow to a travel broadcast
            -- costs a few seconds of alignment. It is also the one verb whose
            -- trust boundary is fleet membership rather than
            -- `follow-fleet-broadcast-from`, so `permitted` is the wrong
            -- question to ask about it -- which is why this says "handled
            -- above" rather than refusing here.
            say "Handled above -- a backup call reaches its own branch."

        JumpGate { pilot, gate } ->
            if not (permitted pilot) then
                say
                    ("'"
                        ++ pilot
                        ++ "' called a jump at "
                        ++ gate
                        ++ " but is not named in 'follow-fleet-broadcast-from'."
                    )

            else
                Just
                    (describeBranch
                        ("'" ++ pilot ++ "' called a jump at '" ++ gate ++ "'.")
                        (jumpToCalledGate context gate)
                    )

        AlignGate { pilot, gate } ->
            if not (permitted pilot) then
                say
                    ("'"
                        ++ pilot
                        ++ "' called an align at "
                        ++ gate
                        ++ " but is not named in 'follow-fleet-broadcast-from'."
                    )

            else
                Just
                    (describeBranch
                        ("'" ++ pilot ++ "' called an align at '" ++ gate ++ "'.")
                        (alignToCalledGate context gate)
                    )

        Unrecognized text ->
            Just (openTheBroadcastsOwnMenu context text)


{-| Warp to a fleet-mate who is on this grid, or route toward them if not.

The in-system half is `warpToFleetMateOnThisGrid`, and #373 is what it cost to
get wrong. The out-of-system half hands the place name to `@host set-destination`, the
same ESI directive the travel broadcast already uses. **`needs backup` carries
no place**, and neither does `recoverFromRetreat` (the only caller left after
#364's retreat stopped warping to the commander itself -- see
`warpAwayFromDanger`), so there is nothing to route to and it says so rather
than routing somewhere arbitrary -- saxrat found the client refuses a waypoint
to a member's live position on every one of several hundred attempts.

**The second half used to end there, and that was the bug.** Once a place was
asked for, this answered `waitForProgressInGame` forever, on the premise that
the pilot might reappear on the overview -- which cannot happen for a pilot who
is not coming to this grid, which is the whole reason a route was asked for. A
pilot broadcasting `is at location`/`is in position at` from another system
left the ship parked wherever the ask fired, with the client's own route panel
showing a destination nothing here ever looked at again.
`goToFleetMateDestinationAsked` is the same one-reading-later latch
`fleetBroadcastFollowed` uses for the travel-broadcast form, so the ask fires
exactly once per place and every reading after it drives the route through
`navigateTowardFleetCommander` instead of repeating the ask.

**`Nothing` is the give-up and nothing else.** Every branch below answers
`Just`; the one answer that does not is `warpToFleetMateOnThisGrid`'s spent
budget, which hands the reading back to the arms under the broadcast rather
than parking on a wait. That is `accelerationGateStep`'s own arrangement, and
`describeFleetMateWarp` is what keeps the give-up visible.

-}
goToFleetMate : BotDecisionContext -> ShipUI -> String -> String -> String -> Maybe DecisionPathNode
goToFleetMate context shipUI pilot place calledIt =
    case overviewEntryForPilot pilot context.readingFromGameClient of
        Just overviewEntry ->
            warpToFleetMateOnThisGrid context pilot calledIt overviewEntry

        Nothing ->
            Just
                (if String.isEmpty place then
                    describeBranch
                        ("'"
                            ++ pilot
                            ++ "' "
                            ++ calledIt
                            ++ " and is not on this grid, and nothing names a"
                            ++ " place to route to, so there is nothing to fly toward."
                        )
                        waitForProgressInGame

                 else if context.memory.goToFleetMateDestinationAsked == Just place then
                    describeBranch
                        ("'"
                            ++ pilot
                            ++ "' "
                            ++ calledIt
                            ++ " '"
                            ++ place
                            ++ "' and is not on this grid -- navigating toward the route."
                        )
                        (navigateTowardFleetCommander context shipUI)

                 else
                    describeBranch
                        ("'"
                            ++ pilot
                            ++ "' "
                            ++ calledIt
                            ++ " '"
                            ++ place
                            ++ "' and is not on this grid -- asking the host for the route. "
                            ++ hostDirectiveSetDestination place
                        )
                        waitForProgressInGame
                )


{-| Warp to a fleet-mate whose overview row is right there, by whichever of the
two mechanisms this reading actually offers.

**#373 is what one mechanism cost.** This drove saxrat's
`Fleet Member` -> `Warp to Member` cascade from the pilot's _overview row_, and
that entry is not in an overview row's menu -- it is a submenu of the fleet
**broadcast banner's** menu, which is where
`eve-online-saxrat`'s `respondToFleetBackupBroadcast` right-clicks it. #373's
live capture of a pilot's overview-row menu is the whole list and `Fleet
Member` is not in it:

    Warp to Within (0 m), Approach, Orbit (5,000 m), Keep at Range (5,000 m),
    Look at, Look At My Ship, Show Info, Overview visibility for Frigate,
    Pilot (Gal Bistot), Broadcast: Target, Broadcast: Repair Target

So the cascade could not resolve at any range, on any reading, and with no
bound it reopened the same menu for hundreds of readings on all four wingman
pilots at once, with nothing else in the bot running.

**Two callers reach here and they get two different mechanisms**, because only
one of them has a banner to right-click.

_A broadcast from this pilot is on the banner_ -- `is at location`,
`is in position at`, `needs backup`. Then saxrat's cascade is available exactly
as saxrat drives it, from `fleetMateBroadcastBannerElement`.
`useMenuEntryWithTextEqual` stays at both rungs: `"Warp to Member"` is a prefix
of `"Warp to Member Within"`, and a containing match takes the wrong entry.

_No banner names this pilot_ -- `recoverFromRetreat`'s path. Then no context
menu is opened at all. The overview row is selected and the Selected Item
panel's own `selectedItemWarpTo` is pressed, which is what `warpAwayFromDanger`
already does for a celestial in this same file: a proven path here, needing no
flyout. **The overview row's `Warp to Within` distance flyout is deliberately
not driven**, and the corpus draws that line exactly where it matters: the
parent entry `Warp to Within` is recorded 3,918 times, hovered by saxrat's own
cascade, while its distance rung is recorded **zero** times. The rung is the
channel nothing has read (#42); the panel button needs no rung, which is why
this path takes it.

**Bounded either way**, which is the half #373 asked for and the half neither
mechanism supplies on its own. The banner persists after a broadcast is
answered, so a ship that arrives beside its mate goes on being told to warp to
them; a mate at 0 m is a warp the client will not offer at all. Past
`fleetMateWarpAskedReadingsBound` this answers `Nothing` and the drones, the
guns, the orbit and the gate get their readings back.

-}
warpToFleetMateOnThisGrid : BotDecisionContext -> String -> String -> OverviewWindowEntry -> Maybe DecisionPathNode
warpToFleetMateOnThisGrid context pilot calledIt overviewEntry =
    let
        preamble : String
        preamble =
            "'" ++ pilot ++ "' " ++ calledIt ++ " and is on this grid -- "

        bannerElement : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        bannerElement =
            fleetMateBroadcastBannerElement
                context.eventContext.botSettings.followFleetBroadcastFrom
                pilot
                context.readingFromGameClient

        warpToButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        warpToButton =
            selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo"

        waitForTheWarpToButton : DecisionPathNode
        waitForTheWarpToButton =
            describeBranch
                (preamble ++ "their row is selected but the panel offers no 'selectedItemWarpTo' yet.")
                waitForProgressInGame
    in
    case
        fleetMateWarpStep
            { broadcastBannerNamesThisMate = bannerElement /= Nothing
            , panelShowsTheMate = selectedItemIsOverviewEntry context.readingFromGameClient overviewEntry
            , panelOffersWarpTo = warpToButton /= Nothing
            , askedReadings = context.memory.goToFleetMateWarpAskedReadings
            }
    of
        GaveUpOnReachingTheMate ->
            -- Hand the reading back rather than wait on it. This arm sits
            -- above the drones, the guns, the orbit and the gate, so a wait
            -- here is not a give-up at all -- it is #321's "a branch at the
            -- head of the tree with no bound owns the whole bot" with a
            -- politer status line. `describeFleetMateWarp` carries the give-up
            -- instead, on every reading.
            Nothing

        WarpToTheMateFromTheBroadcast ->
            Just
                (bannerElement
                    |> Maybe.map
                        (\banner ->
                            describeBranch
                                (preamble ++ "warping to them from the broadcast banner's own menu.")
                                (warpToFleetMateFromTheBroadcastBanner context banner)
                        )
                    |> Maybe.withDefault
                        (describeBranch
                            (preamble ++ "the broadcast banner went away between reading it and clicking it.")
                            waitForProgressInGame
                        )
                )

        SelectTheMate ->
            Just
                (describeBranch
                    (preamble ++ "select their overview row, so the panel's own Warp To acts on it.")
                    (clickUiElementForNavigation overviewEntry.uiNode)
                )

        WaitForTheMatesWarpButton ->
            Just waitForTheWarpToButton

        PressWarpToTheMate ->
            Just
                (warpToButton
                    |> Maybe.map
                        (\button ->
                            describeBranch
                                (preamble ++ "warp to them with the panel's own Warp To.")
                                (clickUiElementForNavigation button)
                        )
                    |> Maybe.withDefault waitForTheWarpToButton
                )


{-| Right-click the fleet broadcast banner and take `Fleet Member` ->
`Warp to Member`: `eve-online-saxrat`'s `respondToFleetBackupBroadcast` cascade,
unchanged.

**One cascade, two callers.** `warpToFleetMateOnThisGrid` drives it for the
`is at location` and `is in position at` forms, and `answerTheBackupCall`
(#385) for the one broadcast that names no place at all -- a backup call, whose
caller may have no overview row on this grid to select. Writing the rungs out
twice is how the two would come to disagree about what the client offers.

`useMenuEntryWithTextEqual` at **both** rungs is the part that must not drift:
`"Warp to Member"` is a prefix of `"Warp to Member Within"`, and a containing
match takes the wrong entry.

-}
warpToFleetMateFromTheBroadcastBanner :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> DecisionPathNode
warpToFleetMateFromTheBroadcastBanner context banner =
    useContextMenuCascade
        ( "fleet broadcast", banner )
        warpToMemberFromTheBroadcastBanner
        context


{-| Take `Warp to Member` from the banner's menu, wherever the client put it.

**The client puts it in two different places and which one is contextual.**
Read live off a `needs backup` banner, the first menu offers `Warp to Member`
directly; read live off the same banner showing other broadcasts, it is inside
a `Fleet Member` submenu alongside `Warp to Member Within`, `Show Info` and
`Add to Watch List`. Both observations are the operator's, minutes apart, on
the same element -- so neither path alone is correct and a cascade that assumes
either one fails silently on the other, which is the failure this bot's
cascades produce most often.

**Exact text at whichever rung it lands on.** `"Warp to Member"` is a prefix of
`"Warp to Member Within"`, so a containing match takes the wrong entry and
warps to a range nobody asked for. `menuEntryIsWarpToMember` makes the same
comparison `useMenuEntryWithTextEqual` does -- trimmed and case-folded -- so
the direct rung and the submenu rung cannot disagree about what counts.

-}
warpToMemberFromTheBroadcastBanner : UseContextMenuCascadeNode
warpToMemberFromTheBroadcastBanner =
    MenuEntryWithCustomChoice
        { describeChoice = "'Warp to Member' where the first menu offers it, else the 'Fleet Member' submenu"
        , chooseEntry =
            \currentMenu ->
                case currentMenu.entries |> List.filter menuEntryIsWarpToMember |> List.head of
                    Just direct ->
                        Just ( direct, menuCascadeCompleted )

                    Nothing ->
                        currentMenu.entries
                            |> List.filter (menuEntryTextEquals "Fleet Member")
                            |> List.head
                            |> Maybe.map
                                (\submenu ->
                                    ( submenu
                                    , useMenuEntryWithTextEqual "Warp to Member" menuCascadeCompleted
                                    )
                                )
        }


menuEntryIsWarpToMember : { a | text : String } -> Bool
menuEntryIsWarpToMember =
    menuEntryTextEquals "Warp to Member"


menuEntryTextEquals : String -> { a | text : String } -> Bool
menuEntryTextEquals expected entry =
    (entry.text |> String.trim |> String.toLower) == String.toLower expected


{-| The broadcast banner as a clickable element, but only while the broadcast
it is showing is this pilot's own call for company.

**The banner persists** -- `fleetBroadcastBannerText` records it still reading
`Gal Bistot: Travel to Riramia` long after that broadcast -- so "a banner is
present" is not "this pilot is calling". Driving the banner's `Fleet Member`
cascade off a stale banner would warp this ship to whoever last broadcast, and
`recoverFromRetreat` is exactly the caller that arrives with somebody else's
banner still up.

-}
fleetMateBroadcastBannerElement :
    List String
    -> String
    -> ReadingFromGameClient
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
fleetMateBroadcastBannerElement followFleetBroadcastFrom pilot readingFromGameClient =
    if fleetMateCallingForCompany followFleetBroadcastFrom readingFromGameClient == Just pilot then
        fleetBroadcastBannerElement readingFromGameClient

    else
        Nothing


{-| The fleet-mate whose current broadcast asks this ship to come to them.

The two verbs `actOnBroadcastVerb` hands to `goToFleetMate`, filtered by
`follow-fleet-broadcast-from` the same way that function filters them -- an
exact match, never a substring, `fleetInviteSenderFromMessageBox`'s reason:
this decides which pilot this ship flies to.

**`NeedBackup` was a third and is deliberately gone from here** (#385). That
verb no longer reaches `goToFleetMate` at all: it has its own arm, its own
mechanism split (approach on grid, the banner's cascade off it), its own bound
and its own trust boundary, which is fleet membership rather than this
allowlist. Leaving it here would have advanced `goToFleetMateWarpAskedReadings`
and made `describeFleetMateWarp` report a warp that no branch was attempting --
a status line disagreeing with the decision, which is the failure that clause
exists to prevent.

-}
fleetMateCallingForCompany : List String -> ReadingFromGameClient -> Maybe String
fleetMateCallingForCompany followFleetBroadcastFrom readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen
            (\bannerText ->
                case parseFleetBroadcast bannerText of
                    AtLocation { pilot } ->
                        Just pilot

                    InPositionAt { pilot } ->
                        Just pilot

                    _ ->
                        Nothing
            )
        |> Maybe.andThen
            (\pilot ->
                if List.member pilot followFleetBroadcastFrom then
                    Just pilot

                else
                    Nothing
            )


{-| Which fleet-mate this ship is trying to reach on this grid, if any.

One question with two readers -- `warpToFleetMateOnThisGrid` and the counter in
`updateMemoryForNewReadingFromGame` that bounds it -- rather than a condition
restated beside the rule, which is #102's defect.

The order is the decision root's own: `recoverFromRetreat` sits directly under
the retreat and above `actOnFleetBroadcast`, so a ship still flying back from a
break-off is rejoining its commander whatever the banner currently says.

**What makes the recovery arm reachable here at all is worth stating**, since a
counter for a state that cannot be entered is #34's shape.
`updateMemoryForNewReadingFromGame` clears `recoveringFromRetreat` on the same
reading the commander gets an overview row -- but it resolves the commander
through `fleetCommanderNameFromFleetWindowHeader` alone, while
`recoverFromRetreat` resolves him through `fleetCommanderName`, which falls
back to `follow-fleet-broadcast-from`. So the recovery reaches the on-grid
branch exactly when the fleet window's header names nobody and the setting
names the commander, and that is the state the panel path exists for.

-}
fleetMateToWarpToOnThisGrid :
    { followFleetBroadcastFrom : List String, recoveringFromRetreat : Bool }
    -> ReadingFromGameClient
    -> Maybe String
fleetMateToWarpToOnThisGrid { followFleetBroadcastFrom, recoveringFromRetreat } readingFromGameClient =
    let
        onThisGrid : String -> Maybe String
        onThisGrid pilot =
            if pilotIsOnOverview pilot readingFromGameClient then
                Just pilot

            else
                Nothing
    in
    case
        ( recoveringFromRetreat
        , fleetCommanderNameFromReading followFleetBroadcastFrom readingFromGameClient
        )
    of
        ( True, Just commander ) ->
            onThisGrid commander

        _ ->
            fleetMateCallingForCompany followFleetBroadcastFrom readingFromGameClient
                |> Maybe.andThen onThisGrid


{-| What to do about a fleet-mate on this grid, as five named answers over
three facts and a counter -- the shape `accelerationGateActivationStep` and
`approachFleetCommanderStep` already use here, and for the stated reason: a rule
reachable only through a full `BotDecisionContext` is a rule nothing can
execute in a test.

**The give-up is asked first**, before any of the three facts, which is
`approachFleetCommanderStep`'s ordering and for its reason: a spent budget must
never be masked by a moment that happens to look actionable.

**The banner is asked before the panel.** Where a broadcast from this pilot is
up, the client's own `Warp to Member` is the mechanism saxrat has flown for
several hundred broadcasts, and it needs no row selected first.

-}
fleetMateWarpStep :
    { broadcastBannerNamesThisMate : Bool
    , panelShowsTheMate : Bool
    , panelOffersWarpTo : Bool
    , askedReadings : Int
    }
    -> FleetMateWarpStep
fleetMateWarpStep mateCase =
    if fleetMateWarpHasBeenGivenUpOn mateCase.askedReadings then
        GaveUpOnReachingTheMate

    else if mateCase.broadcastBannerNamesThisMate then
        WarpToTheMateFromTheBroadcast

    else if not mateCase.panelShowsTheMate then
        SelectTheMate

    else if mateCase.panelOffersWarpTo then
        PressWarpToTheMate

    else
        WaitForTheMatesWarpButton


type FleetMateWarpStep
    = GaveUpOnReachingTheMate
    | WarpToTheMateFromTheBroadcast
    | SelectTheMate
    | WaitForTheMatesWarpButton
    | PressWarpToTheMate


{-| Whether the budget for getting one warp to a fleet-mate started has been
spent. One comparison with two readers -- the step rule and the status clause
-- `accelerationGateHasBeenGivenUpOn`'s arrangement, for its reason.
-}
fleetMateWarpHasBeenGivenUpOn : Int -> Bool
fleetMateWarpHasBeenGivenUpOn askedReadings =
    fleetMateWarpAskedReadingsBound <= askedReadings


{-| How many readings this bot spends trying to warp to one fleet-mate on this
grid before it stops asking.

**Thirty, and not a measurement.** A cascade costs several readings --
right-click, wait for the menu, hover `Fleet Member`, wait for the flyout,
click `Warp to Member` -- and `useContextMenuCascadeWithCustomConfig` waits up
to `readingsToWaitForAFirstContextMenu` for a slow render before it even
reopens, so thirty leaves room for a handful of complete cycles. It is the same
allowance the commander-orbit cascade got before that cascade was removed for
mis-clicking (see `approachTheFleetCommander`), written out rather than shared
with anything, because the two ends have nothing to do with each other and a
shared name would say they did. This bot still has no corpus of its own; see
WINGMAN.md. A run that spends this says so in the status line, which is what
would replace it with a measured value.

-}
fleetMateWarpAskedReadingsBound : Int
fleetMateWarpAskedReadingsBound =
    30


{-| The pilot the banner is currently calling backup for, with no permission
filter of any kind.

Kept separate from `fleetMateCallingForCompany` because the two answer to
different trust boundaries -- that one to `follow-fleet-broadcast-from`, this
one to fleet membership -- and because the memory update has to ask this
question over a bare reading. Permission is `backupCallStep`'s first two
clauses and is never folded in here, so a reader can see which of the two a call
was refused by.

-}
backupCallOnTheBanner : ReadingFromGameClient -> Maybe String
backupCallOnTheBanner readingFromGameClient =
    fleetBroadcastBannerText readingFromGameClient
        |> Maybe.andThen
            (\bannerText ->
                case parseFleetBroadcast bannerText of
                    NeedBackup { pilot } ->
                        Just pilot

                    _ ->
                        Nothing
            )


{-| What to do about a fleet-mate calling for backup, as six named answers over
five facts and a counter -- `fleetMateWarpStep`'s shape, for its reason: a rule
reachable only through a whole `BotDecisionContext` is a rule nothing can
execute in a test.

**The trust boundary is the fleet, not `follow-fleet-broadcast-from`.** Those
are different policies: that allowlist says whose _travel_ this ship follows,
and a fleet-mate who needs help is not necessarily one of them. So the caller
has to be someone `fleetPilotNames` recognises -- the fleet window's own member
rows, its header's commander, or a pilot local chat's standing icon marks as a
fleetmate -- which is the same boundary the friendly-fire guard already uses,
and matched exactly rather than as a substring for
`fleetInviteSenderFromMessageBox`'s reason.

**The failure direction is the quiet one, and #380 is why that matters.** Those
member rows are known to be under-reported: four wingmen in one fleet read 0, 2,
4 and 4 rows from the same Fleet window at the same moment. Under-reporting here
declines a call and this ship goes on doing what it was doing -- it never sends
a ship anywhere. Over-reporting would be the dangerous direction and nothing in
that issue shows it: every source of a name here is the client stating fleet
membership, and the commander fallback is the operator's own setting. Stated
plainly rather than hidden: a wingman whose Fleet window lists nobody answers no
backup calls at all, and says so on every reading.

**Permission is asked before the give-up**, which is
`approachFleetCommanderStep`'s ordering rather than `fleetMateWarpStep`'s, and
for that rule's stated reason: a session that never permits a call must not read
as one that gave up on one. Nothing is lost by it either -- the counter only
advances on the answers that act, so an unpermitted call never spends a reading
to give up on.

**On grid it approaches; off grid it warps.** That is the issue's own split and
it is what the two mechanisms are for. An approach needs the caller's overview
row and closes the last of the distance without a warp the client may refuse at
short range; the banner's `Fleet Member` -> `Warp to Member` needs no row at all,
which is the only thing that can reach a mate who is in this system and not on
this grid.

**A warp already under way is left alone**, and so is an approach the client has
confirmed -- `ManeuverApproach` is the only thing that stops the ask, since a
dispatched click is not a manoeuvre (`ensureShipIsApproaching`). Both hand the
reading back rather than holding it, so the drones, the guns and the gate get
their readings while this ship is on its way.

-}
backupCallStep :
    { settingIsYes : Bool
    , callerIsInThisFleet : Bool
    , callerIsOnThisGrid : Bool
    , shipIsWarpingOrJumping : Bool
    , shipIsApproaching : Bool
    , askedReadings : Int
    }
    -> BackupCallStep
backupCallStep backupCase =
    if not backupCase.settingIsYes then
        BackupCallsAreOff

    else if not backupCase.callerIsInThisFleet then
        TheCallerIsNotAFleetPilot

    else if backupCallHasBeenGivenUpOn backupCase.askedReadings then
        GaveUpOnTheBackupCall

    else if backupCase.shipIsWarpingOrJumping then
        AlreadyOnTheWayToTheCaller

    else if backupCase.callerIsOnThisGrid then
        if backupCase.shipIsApproaching then
            AlreadyOnTheWayToTheCaller

        else
            ApproachTheCaller

    else
        WarpToTheCallerFromTheBroadcast


type BackupCallStep
    = BackupCallsAreOff
    | TheCallerIsNotAFleetPilot
    | GaveUpOnTheBackupCall
    | AlreadyOnTheWayToTheCaller
    | ApproachTheCaller
    | WarpToTheCallerFromTheBroadcast


{-| The answers on which this arm actually spends a reading, and therefore the
answers the counter advances on.

One list with two readers -- `updateMemoryForNewReadingFromGame` and the status
clause -- rather than a condition restated beside the rule, which is #102's
defect. Only the two that dispatch are here: a call this ship is not answering,
one it has given up on, and a ship already closing all cost nothing, so charging
them would spend a budget on readings this arm never asked for.

-}
backupCallAnswersThatSpendAReading : List BackupCallStep
backupCallAnswersThatSpendAReading =
    [ ApproachTheCaller
    , WarpToTheCallerFromTheBroadcast
    ]


{-| Whether the budget for reaching one backup call has been spent. One
comparison with two readers -- the step rule and the status clause --
`fleetMateWarpHasBeenGivenUpOn`'s arrangement, for its reason.
-}
backupCallHasBeenGivenUpOn : Int -> Bool
backupCallHasBeenGivenUpOn askedReadings =
    backupCallAskedReadingsBound <= askedReadings


{-| How many readings this bot spends reaching one backup call before it stops.

**`fleetMateWarpAskedReadingsBound`, written as that constant rather than as a
number**, because this arm drives the same banner cascade that bound was sized
for and a second number would be two opinions about one mechanism. The approach
half costs one reading an attempt where the cascade costs several, so thirty is
generous for it and about right for the warp.

**The give-up hands the reading back rather than waiting**, which is what makes
this a bound at all: this arm sits above the whole fight, so a give-up that
parks on `waitForProgressInGame` is #321's "a branch at the head of the tree
with no bound owns the whole bot" with a politer status line.
`describeBackupCall` is what keeps it visible afterwards.

-}
backupCallAskedReadingsBound : Int
backupCallAskedReadingsBound =
    fleetMateWarpAskedReadingsBound


{-| The backup call this reading carries and what to do about it, resolved the
one way both the decision and the memory update can resolve it.

One question with two readers, `fleetMateToWarpToOnThisGrid`'s arrangement and
for its reason: a counter advanced by one condition and read by another is
#102's defect. `UpdateMemoryContext` carries no decision, so everything here is
a function of the reading, the settings and the counter.

-}
backupCallStepFromReading :
    { followFleetBroadcastFrom : List String, answerBackupCalls : Bool }
    -> Int
    -> ReadingFromGameClient
    -> Maybe { pilot : String, step : BackupCallStep }
backupCallStepFromReading settings askedReadings readingFromGameClient =
    backupCallOnTheBanner readingFromGameClient
        |> Maybe.map
            (\pilot ->
                { pilot = pilot
                , step =
                    backupCallStep
                        { settingIsYes = settings.answerBackupCalls
                        , callerIsInThisFleet =
                            List.member pilot
                                (fleetPilotNamesFromReading
                                    settings.followFleetBroadcastFrom
                                    readingFromGameClient
                                )
                        , callerIsOnThisGrid =
                            overviewEntryForPilot pilot readingFromGameClient /= Nothing
                        , shipIsWarpingOrJumping =
                            shipIsWarpingOrJumpingFromReading readingFromGameClient
                        , shipIsApproaching =
                            shipIsApproachingFromReading readingFromGameClient
                        , askedReadings = askedReadings
                        }
                }
            )


backupCallStepNow : BotDecisionContext -> Maybe { pilot : String, step : BackupCallStep }
backupCallStepNow context =
    backupCallStepFromReading
        { followFleetBroadcastFrom = context.eventContext.botSettings.followFleetBroadcastFrom
        , answerBackupCalls = context.eventContext.botSettings.answerBackupCalls == PromptParser.Yes
        }
        context.memory.backupCallAskedReadings
        context.readingFromGameClient


{-| Answer a fleet-mate's `needs backup`: close on them, by whichever of the two
mechanisms this reading offers.

**This is wiring rather than a new mechanism.** The approach is
`ensureShipIsApproaching`, the same helper `approachTheFleetCommander` drives
and with the same confirmation -- the client's own `ManeuverApproach`, never a
dispatched click. The warp is `warpToFleetMateFromTheBroadcastBanner`, the
cascade `warpToFleetMateOnThisGrid` drives for the other two company verbs.
Neither is written twice.

**It sits above the travel broadcasts in the decision root**, because being slow
to a backup call costs a ship where being slow to an `is at location` costs a
few seconds of alignment -- #237's argument for saxrat. Below the retreat and
below the session-ending arm, as everything is: a ship past its own threshold
leaves rather than joining somebody else's fight, which is exactly the ordering
saxrat's own retreat records having needed.

**Every answer that is not an action hands the reading back**, so nothing under
this arm is starved by a banner that does not clear -- #360's lesson, and the
one that #395 and #397 each paid for again. That includes the refusals: a call
this ship will not answer is _nothing more to do about the call_, not a reason
to spend the reading saying so. `describeBackupCall` is what says it instead,
on every reading, since a `Nothing` cannot carry a decision line.

**Out of system it cannot help, and it says so rather than waiting.** A backup
call names no place -- the broadcast carries a pilot and nothing else -- and
saxrat found the client refuses a waypoint to a fleet-mate's live position, so
there is nothing to route to and `goToFleetMate`'s place-less branch is
deliberately not reached from here. What this bot can do is in-system: the
banner's own `Warp to Member`, which the client offers where it can and declines
where it cannot. So an out-of-system caller looks exactly like an in-system one
here, the cascade is tried, and the bound ends it -- with
`describeBackupCall`'s give-up naming out-of-system as the likely reason and
#381 as the issue that would have to answer first.

-}
answerTheBackupCall : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
answerTheBackupCall context shipUI =
    backupCallStepNow context
        |> Maybe.andThen
            (\{ pilot, step } ->
                let
                    preamble : String
                    preamble =
                        "'" ++ pilot ++ "' needs backup -- "
                in
                case step of
                    BackupCallsAreOff ->
                        Nothing

                    TheCallerIsNotAFleetPilot ->
                        Nothing

                    GaveUpOnTheBackupCall ->
                        Nothing

                    AlreadyOnTheWayToTheCaller ->
                        Nothing

                    ApproachTheCaller ->
                        overviewEntryForPilot pilot context.readingFromGameClient
                            |> Maybe.andThen (ensureShipIsApproaching shipUI)
                            |> Maybe.map
                                (Result.Extra.unpack
                                    (\error ->
                                        describeBranch
                                            (preamble ++ "could not approach them: " ++ error)
                                            waitForProgressInGame
                                    )
                                    (describeBranch
                                        (preamble ++ "they are on this grid -- approach them.")
                                    )
                                )

                    WarpToTheCallerFromTheBroadcast ->
                        fleetBroadcastBannerElement context.readingFromGameClient
                            |> Maybe.map
                                (\banner ->
                                    describeBranch
                                        (preamble ++ "they are not on this grid -- warp to them from the broadcast banner's own menu.")
                                        (warpToFleetMateFromTheBroadcastBanner context banner)
                                )
            )


{-| What this bot is doing about a backup call, in one line.

Exists for `describeFleetMateWarp`'s reason: `answerTheBackupCall` answers
`Nothing` for four of its six cases, and from outside the decision tree a
refusal, a spent budget, a ship already on its way and a grid with no backup
call on it are the same silence.

-}
describeBackupCall : BotDecisionContext -> String
describeBackupCall context =
    "Backup call: "
        ++ (case backupCallStepNow context of
                Nothing ->
                    "none on this reading."

                Just { pilot, step } ->
                    let
                        spentOf : String
                        spentOf =
                            " Readings spent: "
                                ++ String.fromInt context.memory.backupCallAskedReadings
                                ++ " of "
                                ++ String.fromInt backupCallAskedReadingsBound
                                ++ "."
                    in
                    case step of
                        BackupCallsAreOff ->
                            "'"
                                ++ pilot
                                ++ "' is calling, and 'answer-backup-calls' is set to 'no'."

                        TheCallerIsNotAFleetPilot ->
                            "'"
                                ++ pilot
                                ++ "' is calling, but nothing on this reading says they are in this fleet"
                                ++ " -- not the fleet window's member rows, not its header, not local chat's"
                                ++ " standing icons. Not going."

                        GaveUpOnTheBackupCall ->
                            "GAVE UP after "
                                ++ String.fromInt context.memory.backupCallAskedReadings
                                ++ " readings trying to reach '"
                                ++ pilot
                                ++ "'. They are most likely not in this system: a backup call names no place,"
                                ++ " so nothing here can route to one -- see #381."

                        AlreadyOnTheWayToTheCaller ->
                            "on the way to '" ++ pilot ++ "'." ++ spentOf

                        ApproachTheCaller ->
                            "approaching '" ++ pilot ++ "', who is on this grid." ++ spentOf

                        WarpToTheCallerFromTheBroadcast ->
                            "warping to '"
                                ++ pilot
                                ++ "' from the banner's own 'Fleet Member' menu; they are not on this grid."
                                ++ spentOf
           )


{-| Right-click a broadcast nobody has read, so the next reading records its menu.
-}
openTheBroadcastsOwnMenu : BotDecisionContext -> String -> DecisionPathNode
openTheBroadcastsOwnMenu context bannerText =
    case fleetBroadcastBannerElement context.readingFromGameClient of
        Nothing ->
            describeBranch
                ("The broadcast reads '"
                    ++ bannerText
                    ++ "', which is a wording this bot does not read -- and its"
                    ++ " banner is not in this reading, so there is nothing to"
                    ++ " open."
                )
                waitForProgressInGame

        Just bannerElement ->
            describeBranch
                ("The broadcast reads '"
                    ++ bannerText
                    ++ "', which is a wording this bot does not read. Opening its"
                    ++ " own menu so the next reading records what the client"
                    ++ " offers for it."
                )
                (useContextMenuCascade
                    ( "fleet broadcast banner", bannerElement )
                    menuCascadeCompleted
                    context
                )


{-| The banner as a clickable element, rather than as text.
-}
fleetBroadcastBannerElement : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
fleetBroadcastBannerElement readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> EveOnline.ParseUserInterface.getNameFromDictEntries
                >> (==) (Just "bannerLabel")
            )
        |> List.head


{-| The fleet commander's name as the fleet window's own header writes it, and
nothing else -- the header half of `fleetCommanderName`, over a reading rather
than a decision, which is the divergence `selectedItemIsOverviewEntry`'s own
comment records and for the same reason: `updateMemoryForNewReadingFromGame`
has to ask this question too and never sees a decision.

**Inferred from the header's shape, and that inference is stated rather than
buried.** The captured header carried five labels beside a `Boss` icon and a
`Fleet Commander` icon:

    no commander Fleet 5 Gal Bistot Squad 1 4 Wing 1 4

Four of the five describe the fleet's structure and every one of them contains
a parenthesis; the pilot's name is the one that does not. So that is the rule,
rather than reading the icons -- which would be better evidence, but which
label belongs to which icon was not established from the capture, and a wrong
answer here points the drones at the wrong pilot.

**`fleetCommanderOverviewEntry` asks it in this form and not the other**, which
is the one place in this bot that reads the commander without the
`follow-fleet-broadcast-from` fall-back behind it. That is deliberate: the
orbit is issued against the commander's _overview row_, so a name the client
itself did not write is a name there may be no row for, and the status line
says the header gave no answer rather than letting the ship drift silently.

-}
fleetCommanderNameFromFleetWindowHeader : ReadingFromGameClient -> Maybe String
fleetCommanderNameFromFleetWindowHeader readingFromGameClient =
    readingFromGameClient
        |> fleetWindowDescendants
        |> List.filter
            (.uiNode
                >> .pythonObjectTypeName
                >> String.contains "FleetHeader"
            )
        |> List.concatMap
            EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filterMap (.uiNode >> EveOnline.ParseUserInterface.getDisplayText)
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)
        |> List.filter (String.contains "(" >> not)
        |> List.head


{-| Drones out, and assisting the commander rather than this ship's own target.

**Assist first, `F` behind it, and the fallback is the point.** #314 deleted an
unbounded assist cascade from saxrat, and its reason was measured rather than
stylistic: the named pilot was frequently not on the grid, so the readings the
cascade spent bought nothing. A wingman is the case where that reasoning
inverts -- the commander is on the grid by definition -- but "by definition" is
not "always", so `MenuEntryWithCustomChoice` takes `Engage Target` whenever the
menu has no `Assist`, in the same reading rather than a later one.

**Reached without asking whether the guns are cycling.** #326 found a turret
that could not activate on the current target holding the decision on the other
arm of its `case` for 262 consecutive readings -- drones out, drones idle,
nothing landing the whole time. So this sits in the decision root beside the
other arms, not behind the combat one.

`assist-fleet-commander=no` keeps the drones on this ship's own target, which
is `launchAndEngageDrones`' existing behaviour.

**With nothing idling to redirect, this falls through to launching some.**
#374: every reading this arm answered `Nothing` for "nothing idling" fell
straight through to the guns and the orbit, so drones sat in the bay for a
whole six-hour run regardless of `assist-fleet-commander`. `dronesForTheFleet`
is the launch this arm was missing -- unwired scaffolding from the original
wingman skeleton, predating this function -- and reusing it here rather than
duplicating `launchAndEngageDrones`' own bandwidth and quantity gating is what
keeps `considerLaunch`'s checks in one place.

-}
dronesAssistTheCommander : BotDecisionContext -> Maybe DecisionPathNode
dronesAssistTheCommander context =
    if context.eventContext.botSettings.assistFleetCommander /= PromptParser.Yes then
        Nothing

    else
        case ( context.readingFromGameClient.dronesWindow, fleetCommanderName context ) of
            ( Just dronesWindow, Just commander ) ->
                case dronesWindow.droneGroupInSpace of
                    Nothing ->
                        dronesForTheFleet context

                    Just droneGroupInSpace ->
                        let
                            idlingDrones : Int
                            idlingDrones =
                                droneGroupInSpace
                                    |> EveOnline.ParseUserInterface.enumerateAllDronesFromDronesGroup
                                    |> List.filter
                                        (.uiNode
                                            >> .uiNode
                                            >> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                                            >> List.any (stringContainsIgnoringCase "idle")
                                        )
                                    |> List.length
                        in
                        if idlingDrones < 1 then
                            dronesForTheFleet context

                        else
                            Just
                                (describeBranch
                                    ("Assist '" ++ commander ++ "' with the idling drones, else engage this ship's target.")
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
                                                                , useMenuEntryWithTextContaining commander menuCascadeCompleted
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

            _ ->
                Nothing


{-| How long the retreat sticks with one celestial before trying another --
ported unchanged from `eve-online-saxrat`'s `runAwayCelestialStickyReadings`,
except the count it divides is `retreatAskedReadings` (readings _this attempt_
has spent, reset by every fresh retreat) rather than saxrat's session-wide
`readingsCount`, which this bot does not keep -- a rotation that restarts with
each new retreat rather than drifting across the whole session is the more
correct choice for this bot anyway, not merely the cheaper one.
-}
retreatCelestialStickyReadings : Int
retreatCelestialStickyReadings =
    12


{-| Somewhere off this grid, at AU range, that the ship can warp to -- ported
unchanged from `eve-online-saxrat`'s `escapeCelestialsOnOverview`.
`objectDistance` is an `Err` for an AU distance (the parser reads only `m` and
`km`), so the placeholder that makes an AU object read as merely far is exactly
what identifies one here. Displayed rows only: the overview virtualises, and a
row that is not rendered reports a region belonging to whatever was recycled
into its place, so selecting one would act on the wrong object.
-}
escapeCelestialsOnOverview : ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
escapeCelestialsOnOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter
            (.objectDistance
                >> Maybe.map (String.toUpper >> String.contains "AU")
                >> Maybe.withDefault False
            )


{-| What the retreat does with the celestial it has chosen -- ported unchanged
from `eve-online-saxrat`'s `RetreatWarpStep`/`retreatWarpStep`. The panel acts
on whatever is selected, so this is two steps rather than one and the order
matters: select the row, then press the button.
-}
type RetreatWarpStep
    = SelectTheCelestial
    | WaitForTheWarpButton
    | PressWarpTo


retreatWarpStep : { panelShowsTheCelestial : Bool, panelOffersWarpTo : Bool } -> RetreatWarpStep
retreatWarpStep { panelShowsTheCelestial, panelOffersWarpTo } =
    if not panelShowsTheCelestial then
        SelectTheCelestial

    else if not panelOffersWarpTo then
        WaitForTheWarpButton

    else
        PressWarpTo


{-| Leave the grid, by the fastest exit the reading offers -- ported from
`eve-online-saxrat`'s health-retreat `runAway` (not this file's own `runAway`,
which is the neutral-in-local hide response and a different thing entirely;
see the note below).

**This replaces warping to the commander as the retreat's own action, and the
live evidence is why.** The commander is not a safe destination on the
instrument this decision has: reaching them needs either the commander already
on this grid -- `goToFleetMate`'s own cascade, measured live getting stuck
reopening the same context menu at increasing cascade levels without ever
resolving -- or an ESI route to wherever they last broadcast from, which
`goToFleetMate` explicitly declines to fetch for a live position (saxrat found
the client refuses a waypoint to a fleet-mate's live position on every one of
several hundred attempts). A run watched live took a break-off decision 226
times across a session and never once completed a warp: `I am in warp` never
appears in that run's log at all. A retreat that depends on either path is a
retreat that usually cannot leave.

This needs neither. Any AU-range object on the current overview is enough --
nearly always true, and stopping being shot is what leaving _this_ grid
requires. Rejoining the fleet is a separate question, asked once this ship is
no longer under threat -- see `recoverFromRetreat`, which is what used to be
here.

**Docking is not preferred and is not reached** except when the overview
offers nothing at AU range at all, matching saxrat's own reasoning: `Dock` at
the top of a surroundings-menu cascade is right for the wind-down and wrong for
a ship taking damage right now.

The drones and the propulsion module still come home first, the same list
`decideNextActionWhenInSpaceNotHiding` already uses for a ship that is warping.

-}
warpAwayFromDanger : BotDecisionContext -> ShipUI -> DecisionPathNode
warpAwayFromDanger context shipUI =
    case
        [ returnDronesToBay context, deactivateModulesForWarp context ]
            |> List.filterMap identity
            |> List.head
    of
        Just prepareToWarp ->
            prepareToWarp

        Nothing ->
            case
                escapeCelestialsOnOverview context.readingFromGameClient
                    |> listElementAtWrappedIndex
                        (context.memory.retreatAskedReadings // retreatCelestialStickyReadings)
            of
                Nothing ->
                    describeBranch
                        "Get out -- nothing at AU range on the overview to warp to, so fall back to the surroundings menu."
                        (dockAtRandomStationOrStructure context shipUI)

                Just celestial ->
                    let
                        celestialName =
                            celestial.objectName |> Maybe.withDefault "a celestial"

                        warpToButton =
                            selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo"
                    in
                    case
                        retreatWarpStep
                            { panelShowsTheCelestial =
                                selectedItemIsOverviewEntry context.readingFromGameClient celestial
                            , panelOffersWarpTo = warpToButton /= Nothing
                            }
                    of
                        SelectTheCelestial ->
                            describeBranch
                                ("Get out -- select '" ++ celestialName ++ "', so the panel's own Warp To acts on it.")
                                (clickUiElementForNavigation celestial.uiNode)

                        WaitForTheWarpButton ->
                            describeBranch
                                ("Get out -- '" ++ celestialName ++ "' is selected but the panel offers no 'selectedItemWarpTo' yet.")
                                waitForProgressInGame

                        PressWarpTo ->
                            case warpToButton of
                                Nothing ->
                                    describeBranch "Get out -- the warp button went away between reading it and pressing it."
                                        waitForProgressInGame

                                Just button ->
                                    describeBranch
                                        ("Get out -- warp to '"
                                            ++ celestialName
                                            ++ "' at "
                                            ++ (celestial.objectDistance |> Maybe.withDefault "range")
                                            ++ "."
                                        )
                                        (clickUiElementForNavigation button)


{-| Break off from danger when health or the incoming damage rate says to, on
the strongest instruments this bot can read rather than on the weakest.

**`runAway` in this file is not this, and that is the trap #364 names.** That
name belongs to the neutral-in-local hiding logic reached through
`continueIfShouldHide` -- it docks or warps to a configured hide location and
never reads a hitpoint. Until this function there was no health guard here at
all: the only gauge this bot ever touched was the raw live shield percentage
printed once in the status line, read by no decision.

**Two instruments, and they fail in different directions on purpose.** The two
percentage thresholds read `lowestPercentSinceHealthy` over the _believed_
gauge, never the live reading, for the reason CLAUDE.md's "Retreating: the HUD
hitpoint gauge is the weakest instrument here" sets out at length. The damage
window reads the client's own combat log and needs no gauge at all, so a gauge
that starts lying mid-session cannot disarm it.

**The action itself is `warpAwayFromDanger`, not a warp to the commander.**
That was this function's first shape, defended here on the argument that "the
ship is not answering a call, it is leaving one, toward the only pilot in the
game this bot is configured to trust" -- and the argument does not survive
contact with a live run. See `warpAwayFromDanger`'s own note for the measured
cost: 226 break-off cycles, three attempts where the commander actually was on
the overview, and zero completed warps. Getting off the grid and getting back
to the fleet are two different questions with two different answers, and
conflating them is what made this retreat unable to retreat.

**Bounded, and the bound is on the readings the retreat spends dispatching
nothing.** The mission runner deliberately has no give-up in its retreat: the
leaf it would branch to dispatches no effects, so taking it would stop the bot
commanding the warp, which is the one thing that must not happen while the ship
is in the pocket. `warpAwayFromDanger` dispatches something on every reading it
is reachable at all (a celestial to select, a button to wait for, or the
surroundings-menu fallback), so the give-up here is a much rarer safety net
than the commander-chasing version needed -- `retreatAskedReadingsBound` still
exists, and `describeRetreat` keeps the give-up in the status line on every
reading.

-}
retreatToTheCommander : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
retreatToTheCommander context shipUI =
    case retreatStep (retreatCaseFromMemory context.eventContext.botSettings context.memory) of
        NoRetreat ->
            Nothing

        GaveUpOnRejoining _ ->
            Nothing

        RejoinTheCommander reason ->
            Just
                (describeBranch
                    (describeRetreatReason context reason)
                    (warpAwayFromDanger context shipUI)
                )


{-| Once a retreat has cleared, fly back to the fleet commander before
resuming ordinary duty, rather than leaving reunion to whatever the broadcast
or `orbit-fc` happens to ask for next.

**This is the action `retreatToTheCommander` used to take _as_ the retreat.**
It belongs here instead: the ship has already gotten clear with
`warpAwayFromDanger`, it is no longer under threat, and the coordinate it
should now fly toward really is the commander. `goToFleetMate` does the flying
-- the Selected Item panel's own Warp To when the commander is on this grid and
no broadcast of his is on the banner, the `@host set-destination` route the
travel broadcast already uses when he is not. **This is the caller #373's
banner-less path exists for**, and `fleetMateToWarpToOnThisGrid` states what
makes it reachable.

**Gated on `recoveringFromRetreat`**, latched in `updateMemoryForNewReadingFromGame`
from the reading a retreat is decided until the commander has an overview row
again -- a decision cannot write memory, and "no longer retreating" and "back
with the fleet" are not the same reading, so something has to remember the gap
between them.

**Placed where the retreat used to sit**, above the broadcast and combat arms,
for the same reason the retreat itself is: a ship still flying back from a
break-off should not be pulled into the next fight or the next broadcast
before it gets there. **Never above the retreat**, which is the one arm that
outranks it: a ship whose health says leave must leave, and a recovery that
outranked the retreat would fly a damaged ship back toward the fight it just
broke off from.

**#381 is what this arm cost as first written.** It handed `goToFleetMate` the
empty string as the place to route to, and that function's off-grid half needs
a place name -- so it took the branch that says so and waited. That branch is
not an edge case here: `warpAwayFromDanger` warps to a celestial at AU range or
docks, so **the retreat is what puts the commander off grid**, and the arm
reached after every successful retreat was the one arm that could never do
anything. It is not merely idle either, since this arm answers `Just` for as
long as `recoveringFromRetreat` is latched and sits above the broadcast and
combat arms: three of four live wingmen sat here healthy, at 86-100% shield,
for tens of readings each, not fighting.

**Two levers, and they answer different questions**, which is why both are
here and why neither replaces the other:

  - `Fleet Member` -> `Warp to Member` **from the broadcast banner**, where the
    banner is the commander's own call for company. That is a _live_ signal --
    he is broadcasting from where he is now -- and it is one action that lands
    this ship on his grid. It is the same cascade `answerTheBackupCall` drives
    off the banner for a caller with no overview row, so it works off grid, and
    `fleetMateBroadcastBannerElement` is what keeps it off a stale banner: this
    is exactly the caller that arrives with somebody else's banner still up.

  - **Where the commander last said he was**, remembered across the retreat in
    `fleetPlaceBroadcast` and handed to `goToFleetMate` as a real place. That is
    a _historical_ signal and it is the cross-system one.

**The banner is asked first**, because after `warpAwayFromDanger` this ship is
usually in the same system as its commander and on a different grid -- where the
banner's warp is exactly right and a route to a system the ship is already in is
an empty route `navigateTowardFleetCommander` has nothing to click. It is also
the cheaper of the two: one cascade against a host round trip and a multi-jump
flight.

**A place another pilot named is refused**, not used. `fleetPlaceBroadcast`
carries the sender for exactly this, and routing to wherever anybody last
broadcast is the "somewhere arbitrary" `goToFleetMate`'s own doc comment
declines to fly to.

**Everything that is not an action hands the reading back**, refusals included
-- #360's lesson, and #385's arrangement. A commander nothing names, a budget
spent, a ship already in warp and a grid with nowhere to rejoin are each
_nothing more to do about the recovery_, not a reason to spend the reading
saying so. `describeRetreatRecovery` is what says it instead, on every reading,
since a `Nothing` cannot carry a decision line.

-}
recoverFromRetreat : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
recoverFromRetreat context shipUI =
    let
        calledIt : String
        calledIt =
            "is this fleet's commander and this ship is recovering, rejoining"

        named : DecisionPathNode -> Maybe DecisionPathNode
        named =
            describeBranch "Recovering from a retreat -- rejoin the fleet commander before resuming."
                >> Just
    in
    case ( retreatRecoveryStepNow context, fleetCommanderName context ) of
        ( RejoinTheCommanderOnThisGrid, Just commander ) ->
            -- The on-grid half, unchanged and bounded by its own
            -- `goToFleetMateWarpAskedReadings`. The place is never read down
            -- this branch, and it is handed over anyway rather than blanked,
            -- so no caller of `goToFleetMate` has to know which half it will
            -- take.
            goToFleetMate context shipUI commander (rememberedCommanderPlace context |> Maybe.withDefault "") calledIt
                |> Maybe.andThen named

        ( WarpToTheCommanderFromTheBroadcast, Just commander ) ->
            fleetMateBroadcastBannerElement
                context.eventContext.botSettings.followFleetBroadcastFrom
                commander
                context.readingFromGameClient
                |> Maybe.map
                    (\banner ->
                        describeBranch
                            ("'"
                                ++ commander
                                ++ "' "
                                ++ calledIt
                                ++ " -- warping to them from the broadcast banner's own menu."
                            )
                            (warpToFleetMateFromTheBroadcastBanner context banner)
                    )
                |> Maybe.andThen named

        ( RouteToWhereTheCommanderLastSaidHeWas, Just commander ) ->
            rememberedCommanderPlace context
                |> Maybe.andThen (\place -> goToFleetMate context shipUI commander place calledIt)
                |> Maybe.andThen named

        _ ->
            -- Every other answer -- not recovering, nothing naming the
            -- commander, a budget spent, a ship already on its way, and a grid
            -- with nowhere to rejoin -- hands the reading back so the drones,
            -- the guns, the gate and the broadcasts below become reachable.
            Nothing


{-| Where this ship's own fleet commander last said he was, if that is who said
it.

The filter is here rather than in the memory update, and
`fleetPlaceBroadcast`'s own comment says why: `fleetCommanderNameFromReading`
reads the fleet window's header first and that header comes and goes, so asking
once per reading keeps both halves of the question on one answer.

Matched exactly, never as a substring -- `fleetInviteSenderFromMessageBox`'s
reason, and it decides where this ship flies.

-}
rememberedCommanderPlace : BotDecisionContext -> Maybe String
rememberedCommanderPlace context =
    rememberedCommanderPlaceFromReading
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.memory.fleetPlaceBroadcast
        context.readingFromGameClient


{-| The same question over a bare reading, so `updateMemoryForNewReadingFromGame`
can ask it too -- `backupCallStepFromReading`'s arrangement, for #102's reason.
-}
rememberedCommanderPlaceFromReading :
    List String
    -> Maybe { pilot : String, place : String }
    -> ReadingFromGameClient
    -> Maybe String
rememberedCommanderPlaceFromReading followFleetBroadcastFrom fleetPlaceBroadcast readingFromGameClient =
    Maybe.map2 Tuple.pair
        fleetPlaceBroadcast
        (fleetCommanderNameFromReading followFleetBroadcastFrom readingFromGameClient)
        |> Maybe.andThen
            (\( remembered, commander ) ->
                if remembered.pilot == commander then
                    Just remembered.place

                else
                    Nothing
            )


{-| What to do about getting back to the commander after a retreat, as eight
named answers over five facts and a counter -- `backupCallStep`'s shape, for its
reason: a rule reachable only through a whole `BotDecisionContext` is a rule
nothing can execute in a test.

**A commander nothing names is asked before the give-up**, `backupCallStep`'s
own ordering: a ship with no fleet-mate to rejoin has not given up on rejoining
one, and reporting it as a spent budget would send an operator to look at the
bound when what is wrong is `follow-fleet-broadcast-from`.

**The give-up is asked before every actionable clause**, which is
`approachFleetCommanderStep`'s ordering and for its reason: a spent budget must
never be masked by a moment that happens to look actionable.

**A ship in warp or jumping spends nothing and is told to do nothing.** The
manoeuvre is the recovery executing, and charging it would bill this arm for the
very flight it asked for -- `retreatAskedReadings`' own rule, and what keeps a
legitimate multi-jump route from reaching a bound sized for a cascade.

-}
retreatRecoveryStep :
    { recovering : Bool
    , commanderIsNamed : Bool
    , commanderIsOnThisGrid : Bool
    , bannerNamesTheCommander : Bool
    , remembersWhereTheCommanderWas : Bool
    , shipIsWarpingOrJumping : Bool
    , askedReadings : Int
    }
    -> RetreatRecoveryStep
retreatRecoveryStep recoveryCase =
    if not recoveryCase.recovering then
        NotRecoveringFromARetreat

    else if not recoveryCase.commanderIsNamed then
        NothingNamesTheCommander

    else if retreatRecoveryHasBeenGivenUpOn recoveryCase.askedReadings then
        GaveUpOnRejoiningTheCommander

    else if recoveryCase.shipIsWarpingOrJumping then
        AlreadyOnTheWayBackToTheCommander

    else if recoveryCase.commanderIsOnThisGrid then
        RejoinTheCommanderOnThisGrid

    else if recoveryCase.bannerNamesTheCommander then
        WarpToTheCommanderFromTheBroadcast

    else if recoveryCase.remembersWhereTheCommanderWas then
        RouteToWhereTheCommanderLastSaidHeWas

    else
        NowhereToRejoinTheCommander


type RetreatRecoveryStep
    = NotRecoveringFromARetreat
    | NothingNamesTheCommander
    | GaveUpOnRejoiningTheCommander
    | AlreadyOnTheWayBackToTheCommander
    | RejoinTheCommanderOnThisGrid
    | WarpToTheCommanderFromTheBroadcast
    | RouteToWhereTheCommanderLastSaidHeWas
    | NowhereToRejoinTheCommander


{-| The answers on which this arm actually spends a reading, and therefore the
answers the counter advances on.

One list with two readers -- `updateMemoryForNewReadingFromGame` and the status
clause -- rather than a condition restated beside the rule, which is #102's
defect, and #389 is what the wrong half costs: a counter advanced from state
alone reported a give-up at 46 readings against a bound of 20 with the arm never
having been asked.

**`NowhereToRejoinTheCommander` is deliberately not here.** It dispatches
nothing -- it is precisely the reading this arm has nothing to do with -- so
charging it would be exactly #389's defect, and it needs no budget: it already
hands the reading back, so the arms below it run whether or not anything is ever
remembered.

-}
retreatRecoveryAnswersThatSpendAReading : List RetreatRecoveryStep
retreatRecoveryAnswersThatSpendAReading =
    [ RejoinTheCommanderOnThisGrid
    , WarpToTheCommanderFromTheBroadcast
    , RouteToWhereTheCommanderLastSaidHeWas
    ]


{-| Whether the budget for getting one ship back to its commander has been
spent. One comparison with two readers -- the step rule and the status clause --
`fleetMateWarpHasBeenGivenUpOn`'s arrangement, for its reason.
-}
retreatRecoveryHasBeenGivenUpOn : Int -> Bool
retreatRecoveryHasBeenGivenUpOn askedReadings =
    retreatRecoveryAskedReadingsBound <= askedReadings


{-| How many readings this bot spends getting back to its commander before it
stops asking.

**`fleetMateWarpAskedReadingsBound`, written as that constant rather than as a
number**, `backupCallAskedReadingsBound`'s own arrangement and for its reason:
this arm drives the same banner cascade that bound was sized for, and the route
half drives `routeMarkerCascade`, so a second number would be two opinions about
the same two mechanisms on a bot that still has no corpus of its own
(WINGMAN.md).

**It is not a bound on the flight**, which is what makes thirty enough for a
multi-jump route: `AlreadyOnTheWayBackToTheCommander` sits above every
actionable answer, so every reading the ship is actually warping or jumping
resets the count. What accumulates is readings spent clicking with the ship
standing still, which is the only shape that can run forever.

-}
retreatRecoveryAskedReadingsBound : Int
retreatRecoveryAskedReadingsBound =
    fleetMateWarpAskedReadingsBound


{-| The shipped rule over this reading, for the arm and for the status clause.

Two callers, one question -- `backupCallStepNow`'s arrangement, for #102's
reason: a status line derived from a second copy of the conditions is a status
line that can disagree with the decision it is reporting on.

-}
retreatRecoveryStepNow : BotDecisionContext -> RetreatRecoveryStep
retreatRecoveryStepNow context =
    retreatRecoveryStepFromReading
        context.eventContext.botSettings.followFleetBroadcastFrom
        { recovering = context.memory.recoveringFromRetreat
        , fleetPlaceBroadcast = context.memory.fleetPlaceBroadcast
        , askedReadings = context.memory.retreatRecoveryAskedReadings
        }
        context.readingFromGameClient


{-| The same rule over a bare reading and the three memory fields it reads.

`updateMemoryForNewReadingFromGame` is the second caller and the reason this
exists: the counter has to advance on the answers this arm spends a reading on,
and asking the rule is the only way the counter and the arm cannot come to
disagree about which reading was spent -- #102's defect, and #389 is the shape
it takes when the counter is advanced from state instead.

-}
retreatRecoveryStepFromReading :
    List String
    ->
        { recovering : Bool
        , fleetPlaceBroadcast : Maybe { pilot : String, place : String }
        , askedReadings : Int
        }
    -> ReadingFromGameClient
    -> RetreatRecoveryStep
retreatRecoveryStepFromReading followFleetBroadcastFrom recoveryMemory readingFromGameClient =
    let
        commander : Maybe String
        commander =
            fleetCommanderNameFromReading followFleetBroadcastFrom readingFromGameClient
    in
    retreatRecoveryStep
        { recovering = recoveryMemory.recovering
        , commanderIsNamed = commander /= Nothing
        , commanderIsOnThisGrid =
            commander
                |> Maybe.map (\pilot -> pilotIsOnOverview pilot readingFromGameClient)
                |> Maybe.withDefault False
        , bannerNamesTheCommander =
            (commander
                |> Maybe.andThen
                    (\pilot ->
                        fleetMateBroadcastBannerElement
                            followFleetBroadcastFrom
                            pilot
                            readingFromGameClient
                    )
            )
                /= Nothing
        , remembersWhereTheCommanderWas =
            rememberedCommanderPlaceFromReading
                followFleetBroadcastFrom
                recoveryMemory.fleetPlaceBroadcast
                readingFromGameClient
                /= Nothing
        , shipIsWarpingOrJumping = shipIsWarpingOrJumpingFromReading readingFromGameClient
        , askedReadings = recoveryMemory.askedReadings
        }


{-| What this bot is doing about getting back to its commander, in one line.

Exists for `describeBackupCall`'s reason, and #381 is the incident that makes it
load-bearing here: `recoverFromRetreat` now answers `Nothing` for five of its
eight cases, and from outside the decision tree a ship that is not recovering,
one with no commander named, one whose budget is spent, one already in warp and
one with nowhere at all to fly are the same silence. Naming the case on every
reading is what would have made #381 one line rather than a live read of four
clients.

-}
describeRetreatRecovery : BotDecisionContext -> String
describeRetreatRecovery context =
    let
        remembered : String
        remembered =
            case context.memory.fleetPlaceBroadcast of
                Nothing ->
                    " Nowhere remembered: no broadcast has named a place since this ship was last with its commander."

                Just { pilot, place } ->
                    " Last place broadcast: '"
                        ++ place
                        ++ "' by '"
                        ++ pilot
                        ++ "'"
                        ++ (if rememberedCommanderPlace context == Nothing then
                                ", which is not this fleet's commander, so it is not routed to."

                            else
                                "."
                           )

        spentOf : String
        spentOf =
            " Readings spent: "
                ++ String.fromInt context.memory.retreatRecoveryAskedReadings
                ++ " of "
                ++ String.fromInt retreatRecoveryAskedReadingsBound
                ++ "."
    in
    "Retreat recovery: "
        ++ (case retreatRecoveryStepNow context of
                NotRecoveringFromARetreat ->
                    "this ship is not flying back from a retreat."

                NothingNamesTheCommander ->
                    "nothing names the fleet commander -- 'follow-fleet-broadcast-from' is unset and no fleet window header names one -- so there is no fleet-mate to rejoin, and the reading is handed back."

                GaveUpOnRejoiningTheCommander ->
                    "GAVE UP after "
                        ++ String.fromInt context.memory.retreatRecoveryAskedReadings
                        ++ " readings -- this ship is still away from its commander and is fighting where it is."
                        ++ remembered

                AlreadyOnTheWayBackToTheCommander ->
                    "warping or jumping back." ++ spentOf

                RejoinTheCommanderOnThisGrid ->
                    "the commander is on this grid." ++ spentOf

                WarpToTheCommanderFromTheBroadcast ->
                    "warping from the commander's own broadcast banner." ++ spentOf

                RouteToWhereTheCommanderLastSaidHeWas ->
                    "routing to where the commander last said he was." ++ remembered ++ spentOf

                NowhereToRejoinTheCommander ->
                    "the commander is off this grid and nothing names a place to fly to, so the reading is handed back."
                        ++ remembered
           )


{-| Which guard says leave, in the order they are asked.

**Extracted so the memory update can ask the same question the decision asks**,
which is the mission runner's #136: `retreatAskedReadings` has to be written in
`updateMemoryForNewReadingFromGame`, the one place that runs on every reading
and the one place that never sees the decision. A second copy of "is the
retreat firing" there would be two definitions of the most consequential
condition in this file, drifting silently, and the one that drifted would be
the instrument rather than the guard.

The order decides which reason an operator reads on a reading where two guards
agree, and it is saxrat's own: shield, then armour, then the damage window.

-}
type RetreatReason
    = RetreatOnShieldMark
    | RetreatOnArmorMark
    | RetreatOnDamageWindow


{-| Everything the retreat decides from, as one record a test can build by hand.

Holds what the memory and the settings say and nothing else -- module constants
are referenced by the rules rather than carried here, so a case constructs one
without knowing them.

-}
type alias RetreatCase =
    { lowestShieldPercent : Int
    , shieldThresholdPercent : Int
    , lowestArmorPercent : Int
    , armorThresholdPercent : Int

    -- The latch, not the live comparison. Set and released in
    -- `updateIncomingDamageMemory`, which is the only place that can hold a
    -- verdict across readings -- and holding it is the whole point: the moment
    -- the ship warps clear the window starts draining, so a live comparison
    -- would cancel its own retreat halfway through.
    , damageLatchIsRetreating : Bool
    , askedReadings : Int
    }


retreatReason : RetreatCase -> Maybe RetreatReason
retreatReason retreatCase =
    if retreatCase.lowestShieldPercent < retreatCase.shieldThresholdPercent then
        Just RetreatOnShieldMark

    else if retreatCase.lowestArmorPercent < retreatCase.armorThresholdPercent then
        Just RetreatOnArmorMark

    else if retreatCase.damageLatchIsRetreating then
        Just RetreatOnDamageWindow

    else
        Nothing


type RetreatStep
    = NoRetreat
    | RejoinTheCommander RetreatReason
    | GaveUpOnRejoining RetreatReason


{-| The retreat decision on its own, as three named answers over one record --
the same shape as `weaponsStep` and `accelerationGateActivationStep`, and for
the same reason: a rule reachable only through a full `BotDecisionContext` is a
rule nothing can execute in a test.

**"Is a retreat wanted" is asked before the bound, which is the opposite order
from `weaponsStep`**, and the difference is deliberate. There a give-up must be
reported even on a reading where the guns happen to be fine, because the
counter only advances while the guns are being asked. Here the counter advances
only while a retreat is decided, so asking the bound first would report a
give-up on a healthy ship that had merely once been hurt -- a status line
saying the retreat has been abandoned when no retreat was ever wanted.

-}
retreatStep : RetreatCase -> RetreatStep
retreatStep retreatCase =
    case retreatReason retreatCase of
        Nothing ->
            NoRetreat

        Just reason ->
            if retreatHasBeenGivenUpOn retreatCase.askedReadings then
                GaveUpOnRejoining reason

            else
                RejoinTheCommander reason


{-| Whether the budget for getting this ship out has been spent. One comparison
with two readers -- the step rule and the status clause -- so a give-up decided
in one place and reported in another cannot disagree about whether it happened.
-}
retreatHasBeenGivenUpOn : Int -> Bool
retreatHasBeenGivenUpOn askedReadings =
    retreatAskedReadingsBound <= askedReadings


{-| How many readings the retreat may be decided while the ship is not in warp
before this arm hands the reading back.

Taken from `eve-online-mission-runner`'s `retreatNotExecutingAlarmReadings`,
which is where that bot's own corpus puts a commanded warp that is not
happening: three times the twelve readings it will keep one celestial selected
for. **This bot has no corpus of its own** -- no recorded wingman run exists on
any of these machines -- so this is a borrowed number, exactly as
`accelerationGateRefusesThisShipTicks` is. See WINGMAN.md's "Not verified".

The mission runner's own measurement says retreats of 30, 89 and 142 readings
have happened there and eventually worked, so a bound of 36 will sometimes hand
back a retreat that was still going to succeed. That direction was chosen on
purpose: what this bot falls through to is its drones and its guns, which is
fighting back, where the mission runner's give-up leaf would have been silence.

-}
retreatAskedReadingsBound : Int
retreatAskedReadingsBound =
    36


{-| The line the operator reads on the reading the ship decides to leave.

Prints the mark and the threshold together, because "Armor reached 4%" without
the number it was compared against leaves an operator unable to tell a genuine
decline from a threshold set too high.

-}
describeRetreatReason : BotDecisionContext -> RetreatReason -> String
describeRetreatReason context reason =
    let
        retreatCase : RetreatCase
        retreatCase =
            retreatCaseFromMemory context.eventContext.botSettings context.memory
    in
    case reason of
        RetreatOnShieldMark ->
            "Shield reached "
                ++ (retreatCase.lowestShieldPercent |> String.fromInt)
                ++ "% against a threshold of "
                ++ (retreatCase.shieldThresholdPercent |> String.fromInt)
                ++ "% -- break off and rejoin the fleet commander."

        RetreatOnArmorMark ->
            "Armor reached "
                ++ (retreatCase.lowestArmorPercent |> String.fromInt)
                ++ "% against a threshold of "
                ++ (retreatCase.armorThresholdPercent |> String.fromInt)
                ++ "% -- break off and rejoin the fleet commander."

        RetreatOnDamageWindow ->
            "The client's combat log says this ship has taken "
                ++ (incomingDamageInWindow context.memory.incomingDamage |> String.fromInt)
                ++ " hitpoints in the last "
                ++ (incomingDamageWindowSeconds |> String.fromInt)
                ++ " s, against a threshold of "
                ++ (context.eventContext.botSettings.runAwayIncomingDamageThreshold |> String.fromInt)
                ++ " -- break off and rejoin the fleet commander. This does not depend on the HUD gauge."


{-| The retreat's inputs, gathered from a memory this reading has updated.

Built twice from two different contexts -- the decision has a
`BotDecisionContext` and the memory update has an `UpdateMemoryContext` -- so
this takes the two records both can produce rather than either context. The
_rule_ is `retreatReason` and there is one of it; only the gathering happens in
two places, and the gathering is a field read.

-}
retreatCaseFromMemory : BotSettings -> BotMemory -> RetreatCase
retreatCaseFromMemory botSettings memory =
    { lowestShieldPercent =
        lowestPercentSinceHealthy memory.hitpoints.shield.believed
            memory.lowestShieldPercentSinceHealthy
    , shieldThresholdPercent = botSettings.runAwayShieldHitpointsThresholdPercent
    , lowestArmorPercent =
        lowestPercentSinceHealthy memory.hitpoints.armor.believed
            memory.lowestArmorPercentSinceHealthy
    , armorThresholdPercent = botSettings.runAwayArmorHitpointsThresholdPercent
    , damageLatchIsRetreating = memory.incomingDamage.retreating
    , askedReadings = memory.retreatAskedReadings
    }


{-| Whether any of the three guards is armed at all.

**This bot ships with all three disabled**, which makes the clause below the
normal case rather than the exceptional one. The bound is read off
`retreatReason`'s own `mark < threshold` comparison rather than off the `-1`
convention, so a threshold of `0` -- a keystroke away, and equally unable to
fire, since a percentage never goes below zero -- reads as uncovered too. The
two cannot drift apart.

-}
retreatIsDisarmed : { shieldThresholdPercent : Int, armorThresholdPercent : Int, damageThreshold : Int } -> Bool
retreatIsDisarmed coverCase =
    (coverCase.shieldThresholdPercent <= 0)
        && (coverCase.armorThresholdPercent <= 0)
        && (coverCase.damageThreshold < 0)


{-| What the retreat is going by, in one line, on every reading.

Exists for the same reason `describeWeaponsAsk` does: this arm answers
`Nothing` both when nothing is wrong and when it has given up, and those two
must not read the same from a console. It also carries the disarmed case, which
is what this bot does by default -- a run whose thresholds were never set would
otherwise look exactly like a run whose ship is fine.

-}
describeRetreat : BotDecisionContext -> String
describeRetreat context =
    let
        settings : BotSettings
        settings =
            context.eventContext.botSettings

        retreatCase : RetreatCase
        retreatCase =
            retreatCaseFromMemory settings context.memory

        marks : String
        marks =
            "Retreat marks: shield "
                ++ (retreatCase.lowestShieldPercent |> String.fromInt)
                ++ "% / armor "
                ++ (retreatCase.lowestArmorPercent |> String.fromInt)
                ++ "% since healthy, thresholds "
                ++ (retreatCase.shieldThresholdPercent |> String.fromInt)
                ++ "/"
                ++ (retreatCase.armorThresholdPercent |> String.fromInt)
                ++ ". "
                ++ describeIncomingDamage context
    in
    if
        retreatIsDisarmed
            { shieldThresholdPercent = settings.runAwayShieldHitpointsThresholdPercent
            , armorThresholdPercent = settings.runAwayArmorHitpointsThresholdPercent
            , damageThreshold = settings.runAwayIncomingDamageThreshold
            }
    then
        "Retreat: DISARMED -- no run-away-* threshold is set, so nothing is watching this ship's health. "
            ++ marks

    else
        case retreatStep retreatCase of
            NoRetreat ->
                "Retreat: armed, not firing. " ++ marks

            RejoinTheCommander _ ->
                "Retreat: FIRING, "
                    ++ (retreatCase.askedReadings |> String.fromInt)
                    ++ " of "
                    ++ (retreatAskedReadingsBound |> String.fromInt)
                    ++ " readings decided to leave with the ship not in warp. "
                    ++ marks

            GaveUpOnRejoining _ ->
                "Retreat: GAVE UP after "
                    ++ (retreatCase.askedReadings |> String.fromInt)
                    ++ " readings deciding to leave with the ship not in warp. The verdict stands; this arm has stopped holding the reading. "
                    ++ marks


{-| The window, the threshold, and whether the host carries the channel at all.

That last clause is what makes reading this guard's silence safe: "0 hitpoints
in the last 45 s" reads identically whether the grid is quiet or nothing is
listening, and only one of those means the ship is fine.

-}
describeIncomingDamage : BotDecisionContext -> String
describeIncomingDamage context =
    let
        memory : IncomingDamageMemory
        memory =
            context.memory.incomingDamage

        threshold : Int
        threshold =
            context.eventContext.botSettings.runAwayIncomingDamageThreshold
    in
    if not memory.hostCarriesTheChannel then
        "Incoming damage: NO COMBAT LOG -- this host does not carry the channel, so the gauge-free guard is blind."

    else
        "Incoming damage: "
            ++ (incomingDamageInWindow memory |> String.fromInt)
            ++ "/"
            ++ (if threshold < 0 then
                    "off"

                else
                    String.fromInt threshold
               )
            ++ " over "
            ++ (incomingDamageWindowSeconds |> String.fromInt)
            ++ " s"
            ++ (if memory.retreating then
                    ", LATCHED."

                else
                    "."
               )


{-| How many readings in a row this bot will go on clicking a weapon that
never comes active before it stops asking and lets the rest of the reading
run. #326 is the measurement: a turret that could not activate on the current
target held that bot's decision for **262 consecutive readings**, drones out
and idle, nothing landing. Twenty is well past the handful of readings a
module legitimately needs to start cycling and nowhere near a session.

Past the bound this answers `Nothing` rather than parking on
`askForHelpToGetUnstuck`, for the reason `accelerationGateStep` gives at its
own give-up: handing the reading back lets the drones, the gate and the trip
home still run, and `describeWeaponsAsk` keeps the give-up visible in the
status line instead of hiding it.

-}
weaponsAskedReadingsBound : Int
weaponsAskedReadingsBound =
    20


{-| Weapons cycling on whatever is locked.

**This is the arm that was missing.** Before it, the only thing in this bot
that ever activated a weapon was `fightUsingDronesAndModules`, reachable only
through `fightRatsIfShipIsPointed` -- which answers `Nothing` unless a rat has
actually pointed this ship. A target the fleet commander called and this bot
dutifully locked is not pointing anybody, so nothing ever fired on it.

**Placed after `dronesAssistTheCommander`, never before it.** #326's lesson is
that reaching the drone arm must not require every weapon to read active
first; keeping the guns strictly below the drones is what makes that true
here regardless of what the guns do.

-}
fireOnActiveTarget : BotDecisionContext -> Maybe DecisionPathNode
fireOnActiveTarget context =
    case weaponsStepFromContext context of
        FriendlyFireHoldsTheTrigger ->
            -- #367. Deliberately part of this rule and not only of the arm
            -- that makes the lock. This arm is what shot Sonya Spodumain in
            -- run 9, and it did so through a lock no fleet check ever saw:
            -- the rest of `weaponsStep` reads `targetLocked` and nothing about
            -- who is locked, so the one guard that existed -- on the broadcast
            -- path, before the lock -- was bypassed by every other way a
            -- target reaches the bar.
            Nothing

        NoShipUIToFireFrom ->
            Nothing

        NoTargetToFireOn ->
            Nothing

        AllWeaponsCycling ->
            Nothing

        GaveUpOnWeapons ->
            Nothing

        ActivateAWeapon ->
            inactiveWeaponFromReading context.readingFromGameClient
                |> Maybe.map
                    (\inactiveModule ->
                        describeBranch
                            "I see a locked target and a weapon that is not cycling. Activate it."
                            (clickModuleButtonButWaitIfClickedInPreviousStep context inactiveModule)
                    )


{-| The weapon decision on its own, as six named answers over four facts and a
counter -- the same shape as `approachFleetCommanderStep` and
`accelerationGateActivationStep`, and for the same reason: the interesting rule
here is an ordering between a bound and a state check, and a rule that can only
be reached through a full `BotDecisionContext` is a rule nothing can execute in
a test.

The bound is checked **before** "are all the weapons already cycling", so a
give-up is reported as a give-up rather than being masked by a fight that
happens to be going fine at that moment.

**The friendly-fire veto and the ship UI are answers of this rule rather than
conditions wrapped around it, and #389 is why.** `updateMemoryForNewReadingFromGame`
advances `weaponsAskedReadings` from this rule; anything the arm refuses on that
the rule cannot see is a reading charged to a budget nobody spent. The veto in
particular held the trigger on readings the old counter still billed for.

-}
weaponsStep :
    { friendlyFireHoldsTheTrigger : Bool
    , shipUIIsShowing : Bool
    , targetLocked : Bool
    , inactiveWeaponPresent : Bool
    , askedReadings : Int
    }
    -> WeaponsStep
weaponsStep { friendlyFireHoldsTheTrigger, shipUIIsShowing, targetLocked, inactiveWeaponPresent, askedReadings } =
    if friendlyFireHoldsTheTrigger then
        FriendlyFireHoldsTheTrigger

    else if not shipUIIsShowing then
        NoShipUIToFireFrom

    else if not targetLocked then
        NoTargetToFireOn

    else if weaponsAskedReadingsBound <= askedReadings then
        GaveUpOnWeapons

    else if not inactiveWeaponPresent then
        AllWeaponsCycling

    else
        ActivateAWeapon


{-| The answers on which this arm actually spends a reading, and therefore the
answers the counter advances on.

`approachFleetCommanderAnswersThatSpendAReading`'s arrangement, and #389 is the
hole it closes here. The condition this replaced advanced the counter from state
alone -- something locked, some top-row module not cycling -- without asking
whether `fireOnActiveTarget` had run. While #389's broadcast arm held every
reading above the guns, that counter still climbed past its bound of 20 and
reported **`GAVE UP after 46 readings`** on an arm that had never once been
asked. Three pilots reported 46, 36 and 50.

**One answer, not four.** `ActivateAWeapon` is the only one that dispatches
anything; `AllWeaponsCycling` is a fight going fine, and the other four are the
arm declining to act at all. Nothing here counts a wait, unlike
`approachFleetCommanderAnswersThatSpendAReading`'s `WaitForTheApproachButton`,
because this arm has no wait to buy readings with -- it either clicks a module
or hands the reading back.

**What it still cannot see** is the reading being taken by an arm _above_ the
guns: the memory update runs before the decision and has no view of it. So the
drone arm holding a reading (#326: on every reading a drone idles) still charges
this budget when a weapon happens to be silent at the same moment. That
over-counts rather than under-counts, which is the safe direction for a bound
whose job is to stop an unbounded ask -- the same trade `fleetMateOnThisGrid`
states. What #389 broke was not that margin but the whole arm being unreachable,
and the recognition fix is what ends that.

-}
weaponsAnswersThatSpendAReading : List WeaponsStep
weaponsAnswersThatSpendAReading =
    [ ActivateAWeapon ]


type WeaponsStep
    = FriendlyFireHoldsTheTrigger
    | NoShipUIToFireFrom
    | NoTargetToFireOn
    | AllWeaponsCycling
    | GaveUpOnWeapons
    | ActivateAWeapon


{-| The rule above, asked of a reading, so that the memory update, the arm and
the status line are all reading one decision -- `friendlyFireStepFromReading`'s
arrangement, for #102's reason.

The friendly-fire verdict is passed in rather than recomputed because
`updateMemoryForNewReadingFromGame` has already worked it out for its own
counter, and two evaluations of that rule on one reading are two chances for it
to be asked with different numbers.

-}
weaponsStepFromReading : FriendlyFireStep -> Int -> ReadingFromGameClient -> WeaponsStep
weaponsStepFromReading friendlyFire askedReadings readingFromGameClient =
    weaponsStep
        { friendlyFireHoldsTheTrigger = friendlyFireVetoesTheGuns friendlyFire
        , shipUIIsShowing = readingFromGameClient.shipUI /= Nothing
        , targetLocked = not (List.isEmpty readingFromGameClient.targets)
        , inactiveWeaponPresent = inactiveWeaponFromReading readingFromGameClient /= Nothing
        , askedReadings = askedReadings
        }


weaponsStepFromContext : BotDecisionContext -> WeaponsStep
weaponsStepFromContext context =
    weaponsStepFromReading
        (friendlyFireStepFromContext context)
        context.memory.weaponsAskedReadings
        context.readingFromGameClient


{-| The first top-row module that is not cycling, if there is one.

One lookup with two readers -- the rule's `inactiveWeaponPresent` and the click
`ActivateAWeapon` makes -- so the arm cannot decide to activate a weapon and
then find none to activate.

-}
inactiveWeaponFromReading : ReadingFromGameClient -> Maybe ShipUIModuleButton
inactiveWeaponFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map shipUIModulesToActivateOnTarget
        |> Maybe.withDefault []
        |> List.filter (.isActive >> Maybe.withDefault False >> not)
        |> List.head


{-| How many readings the unlock cascade gets before this bot stops asking.

Twenty, the same allowance `weaponsAskedReadingsBound` gives the other
per-reading ask in this file, and for the same reason: a context-menu cascade
that is going to work does so in a handful of readings, and twenty is far short
of a session while being several attempts' worth.

**What the bound stops is the asking, and only the asking.** Every other
give-up in this file hands the reading back to the arms below it;
`GaveUpUnlockingAFleetPilot` still vetoes the guns, because the reason not to
shoot a fleetmate does not expire when a context menu turns out to be
unclickable. Spending the budget makes the bot quiet about the lock bar, not
willing to fire into it.

-}
unlockFleetPilotAskedReadingsBound : Int
unlockFleetPilotAskedReadingsBound =
    20


{-| The friendly-fire rule, over plain lists so a case can execute it -- the
same shape as `weaponsStep` and `accelerationGateActivationStep`, and #367 is
the reason there is one rule rather than a check per firing arm.

**Three answers refuse, and the third is the one worth reading twice.**

`UnlockAFleetPilot` and `GaveUpUnlockingAFleetPilot` are the ordinary case: a
locked target carries the name of somebody `fleetPilotNames` lists, so it comes
out of the lock bar and nothing fires at it meanwhile.

`HoldFireOnAnUnverifiedPilot` is the case that would otherwise be invisible.
`fleetMemberNames` answers `[]` for a fleet of forty whose window is shut
exactly as it does for a pilot flying alone, and `List.member` over it is
`False` for everybody. A guard that stopped at the membership list would
therefore pass every target through while looking exactly like a guard that had
checked, which is the "reasoning from silence" #367 was filed on. So when
membership is not verifiable this asks a different question the client can
still answer: is the locked thing a _pilot_? `getNamesOfOtherPilotsInOverview`
is how this bot independently named Sonya Spodumain twice in the very run that
shot her. **NPC rats are not in that list**, so a PvE fight is unaffected and
the cost of the refusal falls entirely on shooting players whose fleet
membership this reading cannot certify -- which is the shot nobody can
currently justify having taken.

**What "not verifiable" means is `fleetRosterVerdict`'s and has widened**, which
is #380: an open window is no longer sufficient. Greta read zero member rows
with the window open in a four-pilot fleet and this branch was skipped, so the
bot was clear to fire on a fleetmate while the status line said membership had
been verified.

**It refuses rather than unlocking in that case**, because the evidence is
asymmetric: "this is a pilot and I cannot check whether they are a fleetmate"
is a reason to hold the trigger, not a reason to drop a lock that may be a
genuine hostile the fleet is engaging.

**What it does not close**, stated because it is the same shape as the defect
above: `getNamesOfOtherPilotsInOverview` needs the local chat window's user
list as well as the overview, and answers `[]` when that window is not
rendering one. A reading whose roster is not corroborated _and_ whose local
chat is unread therefore falls back to `ClearToFire`, which is the original
hole in a narrower place -- and #380 widened the first half of that condition
without touching the second. Nothing in the recorded runs says how often chat
is unread --
`Seeing N other pilots in the overview` is printed on every reading and is the
line to count it from.

The bound is checked after the membership match and before anything is asked
of the client, so a give-up is reported as a give-up rather than as a clean
lock bar.

**Two instruments answer "is this pilot locked", and #390 is why there are
two.** `lockSignalForPilot` is that argument; the short of it is that the
target bar wraps a long name across labels, so the bar alone did not recognise
a two-word character name -- `Sonya Spodumain` included, the pilot run 9 shot --
and the rule fell through to `ClearToFire`. It asks the pilot's overview row for
the client's own lock indicator beside it and refuses if _either_ answers. An
added signal can only add refusals.

`NothingIsLocked` therefore needs both to be empty. A row carrying the
indicator with nothing parsed in the bar is still a lock, and answering "nothing
is locked" to it would be the guard going quiet in the firing direction again.

-}
friendlyFireStep :
    { lockedTargetTexts : List (List String)
    , pilotsLockedOnTheOverview : List String
    , fleetPilots : List String
    , membershipIsVerifiable : Bool
    , otherPilotsOnOverview : List String
    , askedReadings : Int
    }
    -> FriendlyFireStep
friendlyFireStep { lockedTargetTexts, pilotsLockedOnTheOverview, fleetPilots, membershipIsVerifiable, otherPilotsOnOverview, askedReadings } =
    if List.isEmpty lockedTargetTexts && List.isEmpty pilotsLockedOnTheOverview then
        NothingIsLocked

    else
        case firstLockedPilotAmong lockedTargetTexts pilotsLockedOnTheOverview fleetPilots of
            Just ( fleetPilot, signal ) ->
                if unlockFleetPilotAskedReadingsBound <= askedReadings then
                    GaveUpUnlockingAFleetPilot fleetPilot signal

                else
                    UnlockAFleetPilot fleetPilot signal

            Nothing ->
                if membershipIsVerifiable then
                    ClearToFire

                else
                    case firstLockedPilotAmong lockedTargetTexts pilotsLockedOnTheOverview otherPilotsOnOverview of
                        Just ( pilot, signal ) ->
                            HoldFireOnAnUnverifiedPilot pilot signal

                        Nothing ->
                            ClearToFire


type FriendlyFireStep
    = NothingIsLocked
    | UnlockAFleetPilot String LockedPilotSignal
    | GaveUpUnlockingAFleetPilot String LockedPilotSignal
    | HoldFireOnAnUnverifiedPilot String LockedPilotSignal
    | ClearToFire


{-| Which instrument saw the pilot in this ship's lock, carried on the answer so
the status line reports it rather than a future incident having to reason from
silence about which one was working.
-}
type LockedPilotSignal
    = TargetBarLabels
    | OverviewRowIndicator
    | BothSignals


{-| The first of `names` this ship has locked, and what saw it.

**Two questions, and the answer is the union -- this is #390.** The bar renders
a name across as many labels as it needs, and `targetTextsCarryName` asks
whether any _one_ label carries the whole of it, so a two-word character name
was invisible to it: #303 read `['Tower Sentry', 'Sansha I', '20 km']` off a
live client and #389 measured the same failure on every reading of four
sessions. The row indicator is the client's own answer and does not care how the
bar wrapped anything.

They go quiet in opposite directions and neither is sound alone: the bar on a
wrapped name, the row when the pilot has no row on this overview -- a preset
that hides fleet members, or a pilot who left the grid still holding a lock. So
this refuses on either, which is the only combination that cannot make the guard
quieter than one instrument already made it. **`&&` here would be the defect,
not a variation**: it would hold fire only when both agreed, and the case that
matters is exactly the one where they do not.

-}
firstLockedPilotAmong : List (List String) -> List String -> List String -> Maybe ( String, LockedPilotSignal )
firstLockedPilotAmong lockedTargetTexts pilotsLockedOnTheOverview names =
    names
        |> List.filterMap
            (\name ->
                lockSignalForPilot lockedTargetTexts pilotsLockedOnTheOverview name
                    |> Maybe.map (Tuple.pair name)
            )
        |> List.head


{-| What, if anything, says this ship has that pilot locked.

The bar is matched through `targetTextsCarryName`, which is `lockedTargetNamed`'s
own comparison so the guard and the unlock cannot disagree about the bar. The
overview side is a list of names built by `friendlyFireStepFromReading` from
`overviewRowSaysThisShipHasItLocked`, so the rule stays a function of plain
values and a case can execute it without constructing a reading.

-}
lockSignalForPilot : List (List String) -> List String -> String -> Maybe LockedPilotSignal
lockSignalForPilot lockedTargetTexts pilotsLockedOnTheOverview name =
    case
        ( lockedTargetTexts |> List.any (targetTextsCarryName name)
        , pilotsLockedOnTheOverview |> List.member name
        )
    of
        ( True, True ) ->
            Just BothSignals

        ( True, False ) ->
            Just TargetBarLabels

        ( False, True ) ->
            Just OverviewRowIndicator

        ( False, False ) ->
            Nothing


{-| Whether the target bar is one of the instruments that saw this pilot, which
is the same question as "is there a bar entry to right-click".

`unlockFleetPilotInTargetBar` needs one, and so does the counter behind
`unlockFleetPilotAskedReadingsBound`: a pilot held on the row indicator alone
gives that arm nothing to ask for, and a budget charged for asks nobody made is
#389's second defect.

-}
targetBarSawThePilot : LockedPilotSignal -> Bool
targetBarSawThePilot signal =
    case signal of
        TargetBarLabels ->
            True

        BothSignals ->
            True

        OverviewRowIndicator ->
            False


{-| The rule above, asked of a reading and the settings behind it, so that
`updateMemoryForNewReadingFromGame` can advance the counter from the shipped
rule rather than from a restatement of it -- #102's arrangement, the same one
`askingTheCommanderForAnOrbit` uses.

**This is also where the reading becomes plain values**, and deliberately all of
it: #390 gave the rule a second signal that lives on the overview, and putting
the reading into `friendlyFireStep` to get it would have cost the property that
a case can execute the guard against five lists. Only the names already on one
of the two no-shoot lists are asked about, because those are the only names the
rule can refuse on.

-}
friendlyFireStepFromReading : List String -> Int -> ReadingFromGameClient -> FriendlyFireStep
friendlyFireStepFromReading followFleetBroadcastFrom askedReadings readingFromGameClient =
    let
        fleetPilots : List String
        fleetPilots =
            fleetPilotNamesFromReading followFleetBroadcastFrom readingFromGameClient

        otherPilotsOnOverview : List String
        otherPilotsOnOverview =
            getNamesOfOtherPilotsInOverview readingFromGameClient
    in
    friendlyFireStep
        { lockedTargetTexts = readingFromGameClient.targets |> List.map .textsTopToBottom
        , pilotsLockedOnTheOverview =
            (fleetPilots ++ otherPilotsOnOverview)
                |> List.filter (\name -> overviewRowSaysThisShipHasItLocked name readingFromGameClient)
        , fleetPilots = fleetPilots
        , membershipIsVerifiable =
            fleetMembershipIsVerifiable followFleetBroadcastFrom readingFromGameClient
        , otherPilotsOnOverview = otherPilotsOnOverview
        , askedReadings = askedReadings
        }


friendlyFireStepFromContext : BotDecisionContext -> FriendlyFireStep
friendlyFireStepFromContext context =
    friendlyFireStepFromReading
        context.eventContext.botSettings.followFleetBroadcastFrom
        context.memory.unlockFleetPilotAskedReadings
        context.readingFromGameClient


{-| Whether the guns must stay silent this reading.

**Independent of the unlock arm on purpose.** #367's own comment on the
incident: guarding the lock is not enough, because two paths put a target in
the bar without asking anybody -- `fightRatsIfShipIsPointed` ctrl-clicks
whoever is pointing this ship, and a hand-locked target was never asked about
at all. Every arm that can pull a trigger consults this, so a friendly takes
damage only if the unlock _and_ this both fail on the same reading.

-}
friendlyFireVetoesTheGuns : FriendlyFireStep -> Bool
friendlyFireVetoesTheGuns step =
    case step of
        NothingIsLocked ->
            False

        ClearToFire ->
            False

        UnlockAFleetPilot _ _ ->
            True

        GaveUpUnlockingAFleetPilot _ _ ->
            True

        HoldFireOnAnUnverifiedPilot _ _ ->
            True


{-| Take a locked fleet pilot back out of the target bar.

**Where it sits, and why it is that high.** Under `sessionIsEnding`,
`retreatToTheCommander` and `recoverFromRetreat`, and above everything else --
`wingmanDecisionRootInSpace` handles the first three, `wingmanDecisionRootInSpaceOrdinary`
this and everything below it. Above the broadcast arm, the drones and the guns
because each of those answers `Just` for the whole of a fight -- the banner does
not clear while a target is called (#360), the drone arm answers on every
reading a drone idles (#326), the guns on every reading a weapon is not
cycling -- so an unlock placed under any of them would be reachable only on the
readings the fleet is doing nothing, which is every reading except the ones it
exists for. Below the retreat because a ship past its threshold is leaving the
grid, which settles the lock bar more thoroughly than a context menu can.

The cascade is the one `decideActionInAnomaly` sketched and nothing reachable
ever ran: right-click the target-bar entry, take the entry containing
`unlock`.

**It needs the bar entry and the guard no longer does**, which is #390: the
guard holds fire on the overview row's lock indicator too, and a name the bar
wraps across labels is not found here at all. `lockedTargetNamed` answering
`Nothing` is then this arm having nothing to right-click rather than the two
halves disagreeing -- the veto holds the guns for that reading either way, and
`targetBarSawThePilot` is what keeps the unlock budget from being charged for
the ask that could not be made.

-}
unlockFleetPilotInTargetBar : BotDecisionContext -> Maybe DecisionPathNode
unlockFleetPilotInTargetBar context =
    case friendlyFireStepFromContext context of
        UnlockAFleetPilot fleetPilot _ ->
            case unlockFromSelectedItemPanel context fleetPilot of
                Just pressThePanelButton ->
                    Just
                        (describeBranch
                            ("'"
                                ++ fleetPilot
                                ++ "' is in this fleet and is locked. Unlocking, and holding fire meanwhile."
                            )
                            pressThePanelButton
                        )

                Nothing ->
                    lockedTargetNamed fleetPilot context.readingFromGameClient
                        |> Maybe.map
                            (\targetToUnlock ->
                                describeBranch
                                    ("'"
                                        ++ fleetPilot
                                        ++ "' is in this fleet and is locked. Unlocking, and holding fire meanwhile."
                                    )
                                    (useContextMenuCascade
                                        ( "locked target"
                                        , targetToUnlock.barAndImageCont |> Maybe.withDefault targetToUnlock.uiNode
                                        )
                                        (useMenuEntryWithTextContaining "unlock" menuCascadeCompleted)
                                        context
                                    )
                            )

        NothingIsLocked ->
            Nothing

        GaveUpUnlockingAFleetPilot _ _ ->
            Nothing

        HoldFireOnAnUnverifiedPilot _ _ ->
            Nothing

        ClearToFire ->
            Nothing


{-| Keep this ship next to the fleet commander, by commanding an **approach**
on the commander's overview row. #365, and #373's sibling change.

**This replaced a two-rung context-menu cascade, and the live evidence is
why.** The first shape right-clicked the commander's overview row, hovered
`Orbit`, and clicked the `orbit-fc-range` rung, so that the range came from the
menu rather than from the client's persistent default. PILOT.md already
recorded that flyout mis-clicking when driven by hand, and every wingman pilot
reproduced it on the same day: gliding into the flyout collapsed it, the click
landed on a neighbouring entry, **Kara opened an `InfoWindow` and Heather a
`LoggerWindow`**, and all four pilots spent the whole 30-reading menu budget
and fell back to the orbit key. Per-command range through that flyout is not
achievable from here, and the operator's call is that an approach is close
enough for keeping station.

**So the manoeuvre is Approach and the mechanism is a double click on the
commander's overview row** -- `ensureShipIsApproaching`. One reading per ask,
no menu to open, nothing to mis-click into, and no key.

**It was a `Q` chord first, and #387 is why it is not.** That shape --
`KeyDown vkey_Q`, click, `KeyUp vkey_Q` -- is the one `eve-online-saxrat`
deliberately removed: `cg_input` posts a key event without stamping flags on
it, so a posted `Q` carries whatever modifier state the session holds, and with
the Fn bit set that is macOS Quick Note. One recorded saxrat run took the
equivalent branch 1,571 times while Notes came to the front 241 times with
nobody at the machine. This arm is reached whenever the commander is on grid,
so it is on a hot path by exactly the same design.

**The mechanism is a port, not an invention.** saxrat answers a row beyond lock
range with `doubleClickUiElement`, over `mouseDoubleClickOnUIElement`, which
was absent from this app's vendored framework and is now present in it
unchanged. What remains unwitnessed is the manoeuvre rather than the gesture:
`ManeuverApproach` appears nowhere in `~/eve-bot-logs`, so what a first run
still measures is whether the client answers a double click on a _pilot_ row by
naming the manoeuvre `Approach`.

**So the fall-back behind it is the better-evidenced half.** Past
`approachFleetCommanderDoubleClickAskedReadingsBound` this selects the
commander's row and presses the Selected Item panel's own `selectedItemApproach` --
`eve-online-mission-runner`'s `selectThenPanelAction`, whose note records that
exact button taking a ship from 0.0 to 585 m/s after a cascade had achieved
nothing across 180 decisions. The unproven mechanism is primary because it
costs one reading against the panel's two, and a run that has to fall back says
so in the status line, which is what would justify swapping them.

**Be exact about what the corpus says about that button, because it is not what
it looks like.** `selectedItemApproach` does appear in `~/eve-bot-logs` -- three
times, and all three are the mission runner reporting that the panel offered
**none**, for an acceleration gate 5,843 m away. That is evidence about range,
not about the name. The corpus holds no parsed UI trees at all, so it can
confirm no `_name` whatever: `selectedItemActivateGate` has zero occurrences
and is shipped and working elsewhere in this file. The evidence for the name is
the sibling bot's recorded live use, and the risk that leaves open is that the
button may not be offered for a _pilot_ row, or at range -- which
`WaitForTheApproachButton` absorbs, bounded and named.

The check that decides between them is the client's own word -- the ship UI's
indication naming `ManeuverApproach` -- so a first run either shows the
manoeuvre, or falls back and says so, or spends both budgets and says that.

**Nothing here reads the Selected Item panel to decide the commander is
reachable.** `panelIsShowingTheFleetCommander` only says whether the panel is
already showing his row, which is what decides between the fall-back's two
ticks; the manoeuvre is still confirmed by the ship UI and nothing else.

**`orbit-fc-range` is accepted and ignored, and says so.** Removing the key
would end a session that has it set, which is #161's failure -- so it still
parses, and `describeApproachFleetCommanderAsk` names it as ignored on every
reading an operator has set it to something other than the default. Nothing
here changes the client's default Orbit distance either; that prohibition is
unchanged and `TheClientDefaultIsNeverTouchedTest` still refuses the modal
route.

**The commander must be on an overview preset that shows fleet members**, which
this bot cannot arrange -- see WINGMAN.md's setup section. `NoCommanderOnGrid`
therefore reads as "no overview row", naming the preset as a possible cause,
rather than asserting the commander is not on this grid.

**Where it sits, and why that is not the obvious place.** A wingman's whole job
is to be where the commander is, so the tempting placement is at the head of
the decision root -- and that is the placement #326 spent 262 readings proving
wrong for the guns. Anything above the drone arm can hold the reading while the
drones sit idle, and a manoeuvre that cannot be established would do exactly
that. So this sits **below `dronesAssistTheCommander` and below
`fireOnActiveTarget`**, where it can starve neither.

**And below `retreatToTheCommander` and `recoverFromRetreat`, which is not a
trade-off at all.** #364's guard sits second in the root, under
`sessionIsEnding` and over everything else, because a ship past its shield or
armour threshold has to break off -- and since the break-off itself now warps
to whatever is at AU range rather than to the commander (see
`warpAwayFromDanger`), a `recoverFromRetreat` arm sits directly under it to fly
back once the ship is safe, before anything else gets a turn. This arm does the
opposite of both -- it holds the ship on the grid it is being shot on -- so it
must never be able to answer first.

**And above `accelerationGateStep`, which is the half worth arguing.** That arm
answers `Just (wait)` on _every_ reading a gate is on the overview while rats
are still on the grid -- #348's deliberate refusal to abandon a fight. That is
precisely the state this bot most needs to be next to its commander in, so
putting this below the gate would starve it in the one situation it exists for.
Above the gate the cost is bounded and small in the other direction: a gate is
taken a few readings later than it might have been, and the fleet's pocket does
not move.

**It supersedes `orbit-in-combat` rather than sitting beside it.** With
`orbit-fc=yes`, `decideActionInAnomaly` does not issue its own orbit at all --
orbiting whatever this ship is shooting is what pulls a wingman off the
commander's grid, which is the drift the issue was filed on.

-}
approachTheFleetCommander : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
approachTheFleetCommander context shipUI =
    let
        commanderEntry : Maybe OverviewWindowEntry
        commanderEntry =
            fleetCommanderOverviewEntry context.readingFromGameClient

        approachButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        approachButton =
            selectedItemButtonNamed context.readingFromGameClient selectedItemApproachButtonName
    in
    case
        approachFleetCommanderStep
            { settingIsYes =
                approachFleetCommanderIsAsked
                    { settingIsYes = context.eventContext.botSettings.orbitFleetCommander == PromptParser.Yes
                    , closingSinceLanding = context.memory.closingOnTheCommanderSinceLanding
                    }
            , commanderOnGrid = commanderEntry /= Nothing
            , shipIsWarpingOrJumping = shipIsWarpingOrJumpingFromReading context.readingFromGameClient
            , shipIsApproaching = shipIsApproachingFromReading context.readingFromGameClient
            , strayWindowIsOpen = windowOpenedOverTheClient context.readingFromGameClient /= Nothing
            , panelShowsTheCommander = panelIsShowingTheFleetCommander context.readingFromGameClient
            , panelOffersApproach = approachButton /= Nothing
            , askedReadings = context.memory.approachFleetCommanderAskedReadings
            }
    of
        ApproachFleetCommanderIsOff ->
            Nothing

        NoCommanderOnGrid ->
            Nothing

        ShipIsWarpingOrJumping ->
            Nothing

        AlreadyApproaching ->
            -- The confirmation, and it is the client's own word rather than
            -- ours: nothing here counts a dispatched click as a manoeuvre. The
            -- ship UI's indication reading `Approach` is the only thing that
            -- stops the ask, and `updateMemoryForNewReadingFromGame` clears the
            -- counter on the same reading it does.
            Nothing

        GaveUpOnTheApproach ->
            -- Hand the reading back rather than park on
            -- `askForHelpToGetUnstuck`, the answer `accelerationGateStep` and
            -- `fireOnActiveTarget` both give at their own give-ups: the gate
            -- and the trip home still have to run.
            -- `describeApproachFleetCommanderAsk` is what keeps this visible.
            Nothing

        CloseAWindowLeftOverTheClient ->
            case windowOpenedOverTheClient context.readingFromGameClient of
                Nothing ->
                    Nothing

                Just strayWindow ->
                    case EveOnline.ParseUserInterface.parseWindowControlsFromWindow strayWindow |> Maybe.andThen .closeButton of
                        Nothing ->
                            -- Nothing is clicked at a window this bot cannot
                            -- close by its own close button. Clicking at a
                            -- guessed point is what #321's stray-menu rescue
                            -- did 16,791 times in one run, and it is how a
                            -- rescue becomes the damage.
                            Nothing

                        Just closeButton ->
                            Just
                                (describeBranch
                                    ("A '"
                                        ++ strayWindow.uiNode.pythonObjectTypeName
                                        ++ "' is sitting over the client while this ship is being asked to"
                                        ++ " approach -- the mis-click PILOT.md records. Close it before"
                                        ++ " asking again."
                                    )
                                    (clickUiElementForNavigation closeButton)
                                )

        ApproachByDoubleClick ->
            commanderEntry
                |> Maybe.andThen (ensureShipIsApproaching shipUI)
                |> Maybe.map
                    (Result.Extra.unpack
                        (\error ->
                            describeBranch
                                ("Could not approach the fleet commander: " ++ error)
                                waitForProgressInGame
                        )
                        (describeBranch
                            "Approach the fleet commander -- double click their overview row."
                        )
                    )

        SelectTheCommandersRow ->
            commanderEntry
                |> Maybe.map
                    (\entry ->
                        describeBranch
                            ("The double click spent its budget without the client naming the manoeuvre"
                                ++ " -- select the commander's row, so the panel's own Approach acts on it."
                            )
                            (clickUiElementForNavigation entry.uiNode)
                    )

        WaitForTheApproachButton ->
            Just
                (describeBranch
                    ("The commander's row is selected but the panel offers no '"
                        ++ selectedItemApproachButtonName
                        ++ "' yet."
                    )
                    waitForProgressInGame
                )

        PressTheApproachButton ->
            approachButton
                |> Maybe.map
                    (\button ->
                        describeBranch
                            "Approach the fleet commander with the panel's own Approach button."
                            (clickUiElementForNavigation button)
                    )


{-| Close on the commander while the landing window is open, ahead of the
fight. #397.

**The defect this answers is an ordering, not a rule.** `approachTheFleetCommander`
was the last arm of `wingmanDecisionRootInSpaceOrdinary`, and the root's own
comment above `retreatToTheCommander` already says why that is fatal for
anything under the fighting arms: each of them answers `Just` for the whole of
a fight and the first arm to answer ends the reading -- the broadcast banner
does not clear while a target is called (#360), the drone arm answers on every
reading a drone idles (#326), and the guns answer on every reading a weapon is
not cycling. So on any grid worth landing on the approach was unreachable, and
the ship landed at range, opened fire and never closed.

**A permanent hoist is the wrong fix and is not what this is.** Putting the
approach above the fight unconditionally means the ship never fights while the
commander is on grid and unapproached, which inverts the problem. This is a
window: from the reading the warp ends until the client names the manoeuvre,
closing outranks the fight, and after that the arm keeps its old place and the
existing order applies unchanged.

**It calls the same arm rather than doing anything new**, which is #92's shape
in the mission runner -- _the branch changes when that step is taken, never what
it is_. Everything the ask already guarantees therefore still holds inside the
window: the double click first and the panel fall-back behind it, the stray
window closed before asking again, `approachFleetCommanderAskedReadingsBound`
bounding the whole ask, and the manoeuvre confirmed by the client's own word
rather than by a dispatched click.

**What bounds the hoist is that arm's own budget, and it needs no new number.**
The five answers that can hold a reading here are exactly
`approachFleetCommanderAnswersThatSpendAReading`, which is exactly what the
counter advances on -- so the fight can be outranked for at most
`approachFleetCommanderAskedReadingsBound` readings, after which
`GaveUpOnTheApproach` answers `Nothing` and every arm below runs again. The
other four answers hand the reading back on the spot. That is the honest cost
and it is stated rather than hidden: on a landing where the manoeuvre never
takes, the bot spends up to that budget closing before it fights -- which is
the same budget the arm has always been allowed to spend, moved to where it is
reached.

**Where it sits, and what is still above it.** Below `sessionIsEnding`,
`retreatToTheCommander` and `recoverFromRetreat`, which is #364's measured
ordering and not up for trade: a ship past its threshold breaks off, and it does
not close on anyone first. Below `unlockFleetPilotInTargetBar`, a bounded safety
arm (#367) whose veto on the guns is independent of its placement anyway, and
below `activateAlwaysOnModules`, whose answers stop the moment the hardeners are
on -- a tank worth having while landing at range. Above `actOnFleetBroadcast`,
`dronesAssistTheCommander` and `fireOnActiveTarget`, which is the whole change.

**So this does outrank the drone arm for the length of the window**, which is
the trade #326 refused for a _permanent_ placement and which is only tolerable
because this one ends: on the ordinary landing the client names the manoeuvre
within a reading or two and the drones are commanded immediately after.

-}
closeOnTheCommanderAfterLanding : BotDecisionContext -> ShipUI -> Maybe DecisionPathNode
closeOnTheCommanderAfterLanding context shipUI =
    if context.memory.closingOnTheCommanderSinceLanding then
        approachTheFleetCommander context shipUI

    else
        Nothing


{-| The value `orbit-fc-range` holds when nobody has set it.

**Nothing reads this to decide anything any more**, and that is the point of
keeping it. The key used to carry the rung of the Orbit flyout this bot took;
`approachTheFleetCommander` no longer drives that flyout, so the range is not
this bot's to choose. Deleting the key would end a session that has it set,
which is #161's failure, so it still parses and this default is what
`describeApproachFleetCommanderAsk` compares against to decide whether an
operator asked for a range that is being ignored -- a setting that silently
does nothing is the thing that must not exist.

500 m is the value it has always had: the bottom rung of the list PILOT.md
recorded (`500 m` ... `30 km`) and the least the client's own modal will accept
(`between 500 and 1,000,000 meters`, captured in saxrat run 15).

-}
defaultOrbitFleetCommanderRange : String
defaultOrbitFleetCommanderRange =
    "500 m"


{-| A window sitting over the client that this bot neither opened nor uses.

**Structural rather than named, and that is deliberate.** PILOT.md records the
mis-click this exists for: the flyout collapsed mid-glide and the click landed
on `Show Info`, opening a Database Information window. No run in
`~/eve-bot-logs` carried that window's type name when this was written, so a
matcher on the literal would have been a matcher on a channel nothing has read,
which is #42's shape and this file's signature failure. So this asks the tree
instead: a node whose type name ends in `Window`, that carries its own close
button, and that is neither one of the windows the parser already accounts for
nor inside one.

**The structural reader is what recorded the two names the corpus lacked**,
which is the arrangement working rather than a reason to replace it: driving
the Orbit flyout live opened windows on two of the four wingman pilots, and
this printed both type names into the status line. They stay out of the matcher
-- a third one is exactly as likely as the first two were, and a list of names
is a reader that goes quiet the next time the client invents one.

**Two guards keep it from closing something that matters.** The close button
requirement means nothing is ever clicked at a guessed point -- #321's
stray-menu rescue is what that costs. And `approachFleetCommanderStep` only
ever consults this while the ask is already in flight: a window an operator
opened on a healthy session is not this bot's to close. That the cascade which
produced the two recorded windows is gone does not make the arm unreachable --
this bot still drives a context menu for `warpToFleetMateOnThisGrid`'s banner
cascade, on the arm directly above.

`describeApproachFleetCommanderAsk` prints the type name of whatever this
finds, the same arrangement the overview's `rightAlignedIconsHints` and the
client's quick messages got.

-}
windowOpenedOverTheClient : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
windowOpenedOverTheClient readingFromGameClient =
    let
        knownWindowNodes : List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        knownWindowNodes =
            List.concat
                [ readingFromGameClient.overviewWindows |> List.map .uiNode
                , readingFromGameClient.inventoryWindows |> List.map .uiNode
                , readingFromGameClient.chatWindowStacks |> List.map .uiNode
                , readingFromGameClient.agentConversationWindows |> List.map .uiNode
                , readingFromGameClient.messageBoxes |> List.map .uiNode
                , [ readingFromGameClient.selectedItemWindow |> Maybe.map .uiNode
                  , readingFromGameClient.dronesWindow |> Maybe.map .uiNode
                  , readingFromGameClient.fittingWindow |> Maybe.map .uiNode
                  , readingFromGameClient.probeScannerWindow |> Maybe.map .uiNode
                  , readingFromGameClient.directionalScannerWindow |> Maybe.map .uiNode
                  , readingFromGameClient.stationWindow |> Maybe.map .uiNode
                  , readingFromGameClient.marketOrdersWindow |> Maybe.map .uiNode
                  , readingFromGameClient.surveyScanWindow |> Maybe.map .uiNode
                  , readingFromGameClient.bookmarkLocationWindow |> Maybe.map .uiNode
                  , readingFromGameClient.repairShopWindow |> Maybe.map .uiNode
                  , readingFromGameClient.characterSheetWindow |> Maybe.map .uiNode
                  , readingFromGameClient.fleetWindow |> Maybe.map .uiNode
                  , readingFromGameClient.locationsWindow |> Maybe.map .uiNode
                  , readingFromGameClient.standaloneBookmarkWindow |> Maybe.map .uiNode
                  , readingFromGameClient.keyActivationWindow |> Maybe.map .uiNode
                  , readingFromGameClient.compressionWindow |> Maybe.map .uiNode
                  ]
                    |> List.filterMap identity
                ]

        addressesOfKnownWindowsAndTheirDescendants : Set.Set String
        addressesOfKnownWindowsAndTheirDescendants =
            knownWindowNodes
                |> List.concatMap
                    (\windowNode ->
                        windowNode
                            :: EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion windowNode
                    )
                |> List.map (.uiNode >> .pythonObjectAddress)
                |> Set.fromList
    in
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> String.endsWith "Window")
        |> List.filter
            (\node ->
                not (Set.member node.uiNode.pythonObjectAddress addressesOfKnownWindowsAndTheirDescendants)
            )
        |> List.filter
            (\node -> (EveOnline.ParseUserInterface.parseWindowControlsFromWindow node |> Maybe.andThen .closeButton) /= Nothing)
        |> List.head


{-| The approach decision on its own, as seven named answers over five facts
and a counter -- the shape `weaponsStep` and `accelerationGateActivationStep`
already use here, and for the stated reason: a rule reachable only through a
full `BotDecisionContext` is a rule nothing can execute in a test.

**The order carries four arguments.**

The commander is checked before anything counted, so a session that never has
the commander on grid does not read as a give-up.

`GaveUpOnTheApproach` is checked before the stray-window close, not after.
Closing a window is itself a click that repeats every reading, and a close that
does not land would otherwise be the unbounded rescue #321 names -- a branch at
the head of a tree with no bound owns the whole bot. Past the budget the status
line still names the window; nothing goes on poking at it.

The stray window is checked before "already approaching", because a window left
over the client is a problem whatever the ship is doing, and it is only
consulted at all once `0 < askedReadings` -- a window an operator opened on a
healthy session is not this bot's to close.

**Two mechanisms and two bounds, and the fall-back is the proven half.**
`approachFleetCommanderDoubleClickAskedReadingsBound` ends the double click and
`approachFleetCommanderAskedReadingsBound` ends the whole ask, so the readings
between them go to the Selected Item panel's own Approach button --
`selectedItemApproach`, which `eve-online-mission-runner` drives and whose own
note records it taking a ship from 0.0 to 585 m/s after a cascade had achieved
nothing across 180 decisions. The unproven mechanism is the primary on purpose:
the double click costs one reading against the panel's two, and a run that has
to fall back says so in the status line, which is exactly the measurement that would
swap them.

-}
approachFleetCommanderStep :
    { settingIsYes : Bool
    , commanderOnGrid : Bool
    , shipIsWarpingOrJumping : Bool
    , shipIsApproaching : Bool
    , strayWindowIsOpen : Bool
    , panelShowsTheCommander : Bool
    , panelOffersApproach : Bool
    , askedReadings : Int
    }
    -> ApproachFleetCommanderStep
approachFleetCommanderStep approachCase =
    if not approachCase.settingIsYes then
        ApproachFleetCommanderIsOff

    else if not approachCase.commanderOnGrid then
        NoCommanderOnGrid

    else if approachCase.shipIsWarpingOrJumping then
        ShipIsWarpingOrJumping

    else if approachFleetCommanderHasBeenGivenUpOn approachCase.askedReadings then
        GaveUpOnTheApproach

    else if approachCase.strayWindowIsOpen && 0 < approachCase.askedReadings then
        CloseAWindowLeftOverTheClient

    else if approachCase.shipIsApproaching then
        AlreadyApproaching

    else if approachCase.askedReadings < approachFleetCommanderDoubleClickAskedReadingsBound then
        ApproachByDoubleClick

    else if not approachCase.panelShowsTheCommander then
        SelectTheCommandersRow

    else if approachCase.panelOffersApproach then
        PressTheApproachButton

    else
        WaitForTheApproachButton


{-| The answers on which this arm actually spends a reading, and therefore the
answers the counter advances on.

One list with two readers -- `updateMemoryForNewReadingFromGame` and the cases
that check it -- rather than a condition restated beside the rule, which is
#102's defect. Five of the seven answers are here: the double click, both
ticks of the panel fall-back, the reading the panel spends not yet offering its
button, and the click that closes a window sitting over the client. The close
counts against the same budget on purpose, so a rescue that does not land
cannot outlive the ask it is rescuing, and `WaitForTheApproachButton` counts
for the reason `askingTheGateToOpen` counts its own wait: a panel that showed
the row and never produced the button would otherwise buy unlimited readings by
doing nothing.

-}
approachFleetCommanderAnswersThatSpendAReading : List ApproachFleetCommanderStep
approachFleetCommanderAnswersThatSpendAReading =
    [ ApproachByDoubleClick
    , SelectTheCommandersRow
    , PressTheApproachButton
    , WaitForTheApproachButton
    , CloseAWindowLeftOverTheClient
    ]


type ApproachFleetCommanderStep
    = ApproachFleetCommanderIsOff
    | NoCommanderOnGrid
    | ShipIsWarpingOrJumping
    | AlreadyApproaching
    | CloseAWindowLeftOverTheClient
    | GaveUpOnTheApproach
    | ApproachByDoubleClick
    | SelectTheCommandersRow
    | PressTheApproachButton
    | WaitForTheApproachButton


{-| Whether the budget for getting one approach started has been spent at all.
One comparison with two readers -- the step rule and the status clause --
`accelerationGateHasBeenGivenUpOn`'s arrangement, for its reason.
-}
approachFleetCommanderHasBeenGivenUpOn : Int -> Bool
approachFleetCommanderHasBeenGivenUpOn askedReadings =
    approachFleetCommanderAskedReadingsBound <= askedReadings


{-| Whether this ship has landed and has not yet been seen closing on the
commander. #397.

**Opened by the warp ending and closed by the client's own word, and by nothing
else.** `warpJustEnded` is the corrected trigger (#194 / #205 -- previous
reading `Just True`, a ship UI present now, this reading not `Just True`), and
`shipIsApproachingFromReading` is the same `ManeuverApproach` read that already
stops the ask. So the window is sized by the manoeuvre landing rather than by a
number picked for feel, which is the half #194's own arrival window got wrong
first and the corpus later contradicted by a wide margin.

**The confirmation is asked before the opening**, so a warp that ends with the
client already naming `Approach` opens nothing. That inherits
`shipIsApproachingFromReading`'s known limitation -- it says the ship is
approaching _something_, not that it is approaching the commander -- which the
ask itself has always had and which nothing here makes worse.

**Nothing else closes it, and the two candidates were declined for the same
reason.** Closing on the commander leaving the overview would make the window
un-openable on the ordinary landing where the grid has not drawn his row yet;
closing on the ask giving up would only tidy a flag, since a given-up ask
answers `Nothing` at both call sites and holds no reading. What an open window
costs while the commander is off grid is therefore exactly nothing: the arm
answers `NoCommanderOnGrid` and hands the reading straight back.

-}
landingCloseAfterReading :
    { closeWasOwed : Bool
    , justLanded : Bool
    , shipIsApproaching : Bool
    }
    -> Bool
landingCloseAfterReading state =
    if state.shipIsApproaching then
        False

    else
        state.justLanded || state.closeWasOwed


{-| Whether the approach on the commander is asked for on this reading at all.

**The landing close does not depend on `orbit-fc`, and that is a deliberate
behaviour change for every existing settings string** -- including one that
switched the key off on purpose. A wingman that lands at range and does not
close is a ship on its own outside logistics and outside support, and the
operator's framing is that failing to close is what gets it killed. A survival
behaviour is not opt-in. The key goes on governing the steady-state
station-keeping it was written for, which is what it does on every reading the
landing window is shut.

So with `orbit-fc=no` the bot closes once per landing, stops the moment the
client names the manoeuvre, and leaves station-keeping alone for the rest of
that grid. `orbit-in-combat` is unaffected in either direction: it is consulted
only where `orbit-fc` is `no`, which this does not change.

One rule with three readers -- `approachTheFleetCommander`,
`updateMemoryForNewReadingFromGame` and `describeApproachFleetCommanderAsk` --
because a counter advanced under one notion of "the ask is on" and read under
another is #102's defect, and here it would make
`approachFleetCommanderAskedReadingsBound` unreachable during the very window
that bounds the hoist.

-}
approachFleetCommanderIsAsked :
    { settingIsYes : Bool
    , closingSinceLanding : Bool
    }
    -> Bool
approachFleetCommanderIsAsked ask =
    ask.settingIsYes || ask.closingSinceLanding


{-| How many readings the double click on the commander's row gets before this
bot falls back to the Selected Item panel's own button.

**Twenty, written as `weaponsAskedReadingsBound` rather than as a number**:
this file's allowance for an ask that is a key or a click rather than a
cascade. A double click costs one reading, so this is twenty complete attempts
against the one thing that can stop them -- the client naming the manoeuvre
`Approach`.

-}
approachFleetCommanderDoubleClickAskedReadingsBound : Int
approachFleetCommanderDoubleClickAskedReadingsBound =
    weaponsAskedReadingsBound


{-| How many readings the whole ask gets, double click and panel button
together, before this bot hands the reading back for good.

Forty: the twenty above plus the same twenty again for the panel. Written as a
sum of the two so the fall-back's own allowance cannot be squeezed to nothing
by moving either end -- the arrangement the two bounds this replaced already
had. The panel path costs two readings per attempt rather than one (select the
row, then press), so twenty is ten attempts, and a panel that shows the row and
never offers the button spends the same budget rather than waiting for free.

Round rather than measured, and this bot still has no corpus of its own (see
WINGMAN.md). A run that spends it says so in the status line, which is where a
first run also reports whether a double click on a pilot's overview row commands
an approach at all, and whether the fall-back had to carry the session.

-}
approachFleetCommanderAskedReadingsBound : Int
approachFleetCommanderAskedReadingsBound =
    approachFleetCommanderDoubleClickAskedReadingsBound + weaponsAskedReadingsBound


{-| The commander's overview row, resolved the one way the memory update can
resolve it too. See `fleetCommanderNameFromFleetWindowHeader`.
-}
fleetCommanderOverviewEntry : ReadingFromGameClient -> Maybe OverviewWindowEntry
fleetCommanderOverviewEntry readingFromGameClient =
    fleetCommanderNameFromFleetWindowHeader readingFromGameClient
        |> Maybe.andThen (\commander -> overviewEntryForPilot commander readingFromGameClient)


{-| The Selected Item panel's Approach button, by its own `_name`.

**Not a guess, and not corpus-confirmed either** -- see
`approachTheFleetCommander` for why those are different things.
`eve-online-mission-runner` reaches this button by this name, and its own note
records the live result: selecting a row and pressing `selectedItemApproach`
took that ship from 0.0 to 585 m/s after a context-menu cascade had achieved
nothing across 180 decisions. That is the evidence. The three times the name
appears in `~/eve-bot-logs` are that same bot reporting the panel offered none,
which says nothing about the name.

Named here rather than written inline because the status line prints it -- a
run where the panel never offers it says which name it was looking for, which
is what would settle the question for a pilot row.

-}
selectedItemApproachButtonName : String
selectedItemApproachButtonName =
    "selectedItemApproach"


{-| Whether the Selected Item panel is showing the fleet commander's row.

Resolved through `fleetCommanderOverviewEntry` so that the arm, the status
clause and the memory update all ask it the same way -- and answering `False`
when there is no commander row at all is right for every reader: a panel
showing something else is not showing him.

-}
panelIsShowingTheFleetCommander : ReadingFromGameClient -> Bool
panelIsShowingTheFleetCommander readingFromGameClient =
    fleetCommanderOverviewEntry readingFromGameClient
        |> Maybe.map (selectedItemIsOverviewEntry readingFromGameClient)
        |> Maybe.withDefault False


{-| Whether the client is naming this ship's manoeuvre `Approach`.

The same question `ensureShipIsApproaching` asks before deciding it has nothing
to do, over a reading rather than a `ShipUI` so that the memory update can ask
it as well. An absent ship UI answers `False`, which is right for both readers:
nothing that is not in space is approaching anything.

**This is the only thing that counts as success**, and it is the client's own
word. `approachTheFleetCommander` never treats a dispatched click as a
manoeuvre, which is what makes a double click that turns out not to command
anything show up as a spent budget in the status line rather than as a bot that
believes it is keeping station.

-}
shipIsApproachingFromReading : ReadingFromGameClient -> Bool
shipIsApproachingFromReading readingFromGameClient =
    (readingFromGameClient.shipUI
        |> Maybe.andThen .indication
        |> Maybe.andThen .maneuverType
    )
        == Just EveOnline.ParseUserInterface.ManeuverApproach


{-| `shipUIIndicatesShipIsWarpingOrJumping` over a reading, for the same reason
as `shipIsApproachingFromReading`. Distinct from `shipWarpingFromReading`, which
answers about warping only and in three values; a ship in a jump tunnel is no
more able to start an orbit than one in warp.
-}
shipIsWarpingOrJumpingFromReading : ReadingFromGameClient -> Bool
shipIsWarpingOrJumpingFromReading readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map shipUIIndicatesShipIsWarpingOrJumping
        |> Maybe.withDefault False


{-| Take the acceleration gate the fleet's pocket needs, but only once the
overview is clear of rats -- taking it mid-fight abandons whatever the fleet
is still fighting and leaves the commander a ship short in the pocket this
bot just left. See #348.

**Narrower than `eve-online-saxrat`'s `activateAccelerationGateIfPresent` on
purpose.** Two things that bot needs and this one does not: distance triage
for a gate far enough away to be evidence something went wrong (a wingman
follows a fleet through a known pocket rather than hunting blind across a
whole system, so a gate this bot can see on the overview at all is one worth
taking), and the `unlessAlreadyClosingIn` approach guard around the press
(porting `shipApproachingTicks` for one click was more machinery than this is
worth carrying). What is ported is the shape that matters: press the Selected
Item panel's own button rather than a context-menu cascade, and bound how long
this bot goes on asking.

**Which of the two things holding it back is always named.** A single
"waiting" line covering both "no gate here" and "rats still on the grid" is
the shape #343's own review caught elsewhere in this file -- this answers
`Nothing` for the first, silently, exactly as every other arm in this decision
root does when it has nothing to do, and describes the second explicitly.

**#393 is the one thing that overrides the rats guard, and it is scoped to the
gate the commander called.** Absent a `Target` broadcast on a gate,
`gateMayBeTaken` is handed `calledByTheCommander = False` and #348's guard is
exactly what it was. This arm never sees the override: it selects the nearest
gate rather than the called one, and a called gate is taken by
`bringCalledTargetUnderFire`, which sits above this in the decision root.

-}
accelerationGateStep : BotDecisionContext -> Maybe DecisionPathNode
accelerationGateStep context =
    case nearestAccelerationGateOnOverview context.readingFromGameClient of
        Nothing ->
            Nothing

        Just gateEntry ->
            takeTheAccelerationGate context
                { gate = gateEntry, calledByTheCommander = False }


{-| Take the acceleration gate the commander broadcast a `Target` on, drones
first.

**The rats guard is overridden here and only here.** #348 refuses a gate while
rats are on the grid, because a wingman taking one mid-fight "abandons whatever
the fleet is still fighting and leaves the commander a ship short in the pocket
this bot just left". That guard exists to stop a wingman wandering off on its
own judgement; the FC calling the gate is the explicit instruction to send the
crew through, and there are occasions when a fleet must take a gate with rats
still up. So the call overrules it, and nothing else does.

**The drones come home first, and that is not optional.** `accelerationGateStep`
recalls nothing, which was survivable only while the guard required a clear
grid -- with rats up the drones are out essentially by construction, since
`dronesAssistTheCommander` is what puts them there. Taking a called gate without
recalling would abandon them every time, and CLAUDE.md records run 1 losing ten
drones to exactly that shape. The recall is `returnDronesToBay`, the one every
other departing arm already uses, rather than a second copy of it.

**And the recall is bounded, which is what keeps the FC's call from being
lost.** See `calledGateDroneRecall`: abandoning drones to make a called gate is
a real cost and an acceptable one, where abandoning the gate to wait on drones
that are not coming is not.

-}
takeTheCalledAccelerationGate :
    BotDecisionContext
    -> String
    -> OverviewWindowEntry
    -> Maybe DecisionPathNode
takeTheCalledAccelerationGate context calledTarget gateEntry =
    takeTheAccelerationGate context
        { gate = gateEntry, calledByTheCommander = True }
        |> Maybe.map
            (describeBranch
                ("The commander broadcast a Target on the acceleration gate '"
                    ++ calledTarget
                    ++ "' -- that is the fleet being sent through it, so take it."
                )
            )


{-| The gate this bot would act on this reading, and on whose authority.

One derivation with three readers -- this arm, the memory update's counters and
the status clause -- so they cannot disagree about which gate is being asked or
about whether the commander called it. A called gate wins over the nearest one,
which is the ordering the decision root already has structurally:
`actOnFleetBroadcast` is above `accelerationGateStep`, so a reading with a
called gate never reaches the nearest-gate arm.

-}
accelerationGateToAct : ReadingFromGameClient -> Maybe AccelerationGateToAct
accelerationGateToAct readingFromGameClient =
    case calledAccelerationGateFromReading readingFromGameClient of
        Just calledGate ->
            Just { gate = calledGate, calledByTheCommander = True }

        Nothing ->
            nearestAccelerationGateOnOverview readingFromGameClient
                |> Maybe.map (\gate -> { gate = gate, calledByTheCommander = False })


type alias AccelerationGateToAct =
    { gate : OverviewWindowEntry
    , calledByTheCommander : Bool
    }


{-| Whether this bot may take a gate on this reading -- #348's guard, and the
one exception to it.

A pure rule over two `Bool`s so a case can execute it, and one declaration so
the arm, the memory update and the status clause cannot hold three opinions
about when the guard applies. With `calledByTheCommander = False` it _is_ #348's
guard, unchanged.

-}
gateMayBeTaken : { ratsOnTheGrid : Bool, calledByTheCommander : Bool } -> Bool
gateMayBeTaken gateCase =
    gateCase.calledByTheCommander || not gateCase.ratsOnTheGrid


{-| The select-then-press sequence, shared by the called gate and the nearest
one, so there is one gate mechanism rather than two that can drift.
-}
takeTheAccelerationGate : BotDecisionContext -> AccelerationGateToAct -> Maybe DecisionPathNode
takeTheAccelerationGate context gateToTake =
    if
        not
            (gateMayBeTaken
                { ratsOnTheGrid =
                    not (List.isEmpty (getNamesOfRatsInOverview context.readingFromGameClient))
                , calledByTheCommander = gateToTake.calledByTheCommander
                }
            )
    then
        Just
            (describeBranch
                "An acceleration gate is on the overview, but rats are still on the grid -- staying to fight rather than taking it."
                waitForProgressInGame
            )

    else
        case
            calledGateDroneRecall
                { calledByTheCommander = gateToTake.calledByTheCommander
                , dronesAreInSpace = dronesAreInSpace context.readingFromGameClient
                , askedReadings = context.memory.calledGateRecallAskedReadings
                }
        of
            RecallTheDronesFirst ->
                case returnDronesToBay context of
                    Just recall ->
                        Just
                            (describeBranch
                                ("Holding the called acceleration gate until the drones are back -- "
                                    ++ String.fromInt context.memory.calledGateRecallAskedReadings
                                    ++ " of "
                                    ++ String.fromInt calledGateDroneRecallGiveUpReadings
                                    ++ " readings of recall so far."
                                )
                                recall
                            )

                    Nothing ->
                        pressTheAccelerationGate context gateToTake

            LeaveTheDronesBehind ->
                -- Named on every reading it declines, which is the other half
                -- of #11: a give-up that answers `Nothing` silently reads
                -- exactly like a bot that never had drones out, and #11's own
                -- first version fired on an equality test and so said nothing
                -- on any other reading.
                pressTheAccelerationGate context gateToTake
                    |> Maybe.map
                        (describeBranch
                            ("The drones have not answered "
                                ++ String.fromInt context.memory.calledGateRecallAskedReadings
                                ++ " readings of recall and are not coming back -- taking the called gate without them, because losing the commander's gate is worse than losing the drones."
                            )
                        )

            NoDroneRecallBeforeThisGate ->
                pressTheAccelerationGate context gateToTake


{-| Select the gate, then press the Selected Item panel's own Activate Gate.

The wording says which authority the press is on, because
`The overview is clear of rats` is **false** on a called gate taken mid-fight,
and a log claiming a clear grid on readings that had rats on it is worse than no
line at all.

-}
pressTheAccelerationGate : BotDecisionContext -> AccelerationGateToAct -> Maybe DecisionPathNode
pressTheAccelerationGate context gateToTake =
    let
        activateGateButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        activateGateButton =
            selectedItemButtonNamed context.readingFromGameClient "selectedItemActivateGate"

        waitForTheActivateButton : DecisionPathNode
        waitForTheActivateButton =
            describeBranch
                "The acceleration gate is selected but the panel offers no 'selectedItemActivateGate' yet."
                waitForProgressInGame
    in
    case
        accelerationGateActivationStep
            { panelShowsTheGate = selectedItemIsOverviewEntry context.readingFromGameClient gateToTake.gate
            , panelOffersActivateGate = activateGateButton /= Nothing
            , askedReadings = context.memory.gateAskedReadings
            }
    of
        GiveUpOnThisGate ->
            -- Hand the reading back rather than park the session --
            -- `askForHelpToGetUnstuck` dispatches nothing and
            -- waits, which is what cost saxrat run 18 three
            -- quarters of a session on a gate that was never going
            -- to open (#321's general lesson: a branch at the head
            -- of the tree with no bound owns the whole bot).
            -- `describeAccelerationGateAsk` carries the give-up in
            -- the status line on every reading instead.
            Nothing

        SelectTheGate ->
            Just
                (describeBranch
                    "I see an acceleration gate -- select it, so the panel's own Activate Gate acts on it."
                    (clickUiElementForNavigation gateToTake.gate.uiNode)
                )

        WaitForTheActivateButton ->
            Just waitForTheActivateButton

        PressActivateGate ->
            Just
                (activateGateButton
                    |> Maybe.map
                        (\button ->
                            describeBranch
                                (if gateToTake.calledByTheCommander then
                                    "The commander called this acceleration gate -- activate it and take the fleet through, rats on the grid or not."

                                 else
                                    "The overview is clear of rats -- activate the acceleration gate to move to the next pocket."
                                )
                                (clickUiElementForNavigation button)
                        )
                    |> Maybe.withDefault waitForTheActivateButton
                )


{-| Whether to hold a called gate for the drones, as three named answers over
three facts -- the shape `accelerationGateActivationStep` uses, so a case can
execute it.

**Scoped to the called gate.** With `calledByTheCommander = False` this always
answers `NoDroneRecallBeforeThisGate`, so the uncalled arm is exactly what it
was: #348's guard means its grid is clear, and adding a recall there is a
behaviour change with its own evidence to gather.

**The bound is what makes the recall safe rather than another way to lose the
gate.** A recall the client never answers must not hold the ship on the grid
indefinitely -- that is saxrat's own history, where Shift+R went out on every
reading for as long as the drones stayed in space and the callers took the
recall _instead of_ their own next step, so a ship whose drones never came home
never docked either. Abandoning drones to make a called gate is a certain,
bounded, recoverable cost; abandoning the commander's gate to wait on drones
that are not coming is not.

-}
calledGateDroneRecall :
    { calledByTheCommander : Bool, dronesAreInSpace : Bool, askedReadings : Int }
    -> CalledGateDroneRecall
calledGateDroneRecall recallCase =
    if not (recallCase.calledByTheCommander && recallCase.dronesAreInSpace) then
        NoDroneRecallBeforeThisGate

    else if calledGateDroneRecallHasBeenGivenUpOn recallCase.askedReadings then
        LeaveTheDronesBehind

    else
        RecallTheDronesFirst


type CalledGateDroneRecall
    = NoDroneRecallBeforeThisGate
    | RecallTheDronesFirst
    | LeaveTheDronesBehind


{-| Whether the budget for recalling the drones before a called gate is spent.
One comparison with three readers -- the rule, the counter and the status clause
-- so a give-up decided in one place and reported in another cannot disagree
about whether it happened.
-}
calledGateDroneRecallHasBeenGivenUpOn : Int -> Bool
calledGateDroneRecallHasBeenGivenUpOn askedReadings =
    calledGateDroneRecallGiveUpReadings < askedReadings


{-| How many readings to keep asking the drones home before taking the called
gate without them, taken unchanged from `eve-online-saxrat`'s
`droneRecallGiveUpTicks`.

**Copied rather than chosen**, because that is the only drone-recall number in
this repository with any evidence behind it, and CLAUDE.md records it having
never been reached in any recorded run of either bot that carries it -- a
give-up that names itself on every reading it declines, so zero is evidence
rather than silence. This bot has no corpus of its own for it: no wingman run
has ever recalled drones before a gate, because no wingman has ever taken a
called one.

**The tension is stated rather than hidden.** 60 readings is a long time to hold
an FC's gate -- a reading is one to eight seconds by this repo's own two figures
-- and the direction to move this on evidence is _down_, from a run that shows
what a recall this fleet's drones actually answer in. What is refused is moving
it on a guess in either direction: shorter abandons drones the client was about
to return, longer is the unbounded wait this exists to end.

-}
calledGateDroneRecallGiveUpReadings : Int
calledGateDroneRecallGiveUpReadings =
    60


{-| The recall counter after this reading -- saxrat's
`droneRecallUnansweredTicks` in one rule, over a record so a case can fold a
whole session through it.

Four cases, in this order, and each is a way it would otherwise be wrong:

  - **no drones in space** resets, because there is nothing to ask for;
  - **the count fell** resets, because a partial recall is the client answering
    and patience should start again;
  - **past the give-up** _holds_ rather than resetting, because giving up is
    what stops the asking and a reset would unwind it -- the ship would
    alternate forever between abandoning its drones and recalling them;
  - **the arm asked on this reading** advances, and anything else holds.

**It counts readings the arm asked on rather than every reading**, taken from
the shipped rule rather than restated beside it -- #102's defect is a counter
advanced by one condition and read by another. It over-counts only in the
direction #393 chose: an arm above the broadcast holding the tree spends budget
the recall did not use, which gives up on the drones sooner and takes the gate.

-}
calledGateRecallAskedReadingsAfter :
    { askedThisReading : Bool, dronesInSpaceNow : Int, dronesInSpaceBefore : Int, before : Int }
    -> Int
calledGateRecallAskedReadingsAfter counterCase =
    if counterCase.dronesInSpaceNow < 1 then
        0

    else if counterCase.dronesInSpaceNow < counterCase.dronesInSpaceBefore then
        0

    else if calledGateDroneRecallHasBeenGivenUpOn counterCase.before then
        counterCase.before

    else if counterCase.askedThisReading then
        counterCase.before + 1

    else
        counterCase.before


type AccelerationGateActivationStep
    = SelectTheGate
    | WaitForTheActivateButton
    | PressActivateGate
    | GiveUpOnThisGate


{-| A pure function over a record so a case can execute it, ported from
saxrat's `GateActivationCase` / `gateActivationStep` of the same shape.
-}
accelerationGateActivationStep :
    { panelShowsTheGate : Bool, panelOffersActivateGate : Bool, askedReadings : Int }
    -> AccelerationGateActivationStep
accelerationGateActivationStep gateCase =
    if accelerationGateHasBeenGivenUpOn gateCase.askedReadings then
        GiveUpOnThisGate

    else if not gateCase.panelShowsTheGate then
        SelectTheGate

    else if gateCase.panelOffersActivateGate then
        PressActivateGate

    else
        WaitForTheActivateButton


{-| Whether the budget for asking one gate to open has been spent. One
comparison with two readers -- the step rule and the status clause -- so a
give-up decided in one place and reported in another cannot disagree about
whether it happened.
-}
accelerationGateHasBeenGivenUpOn : Int -> Bool
accelerationGateHasBeenGivenUpOn askedReadings =
    accelerationGateRefusesThisShipTicks < askedReadings


{-| How many readings to keep asking a gate that is already selected before
giving up on it, taken unchanged from saxrat's `gateRefusesThisShipTicks` --
that bot's own corpus put a working gate's cost at 0 to 15 readings and a
genuinely stuck one past 335, so 40 sits inside the gap with clearance on both
sides. This bot has no corpus of its own yet; see WINGMAN.md.
-}
accelerationGateRefusesThisShipTicks : Int
accelerationGateRefusesThisShipTicks =
    40


{-| What the guns are doing, in one line.

Exists for the same reason `describeAccelerationGateAsk` does: `fireOnActiveTarget`
answers `Nothing` when it gives up, so without this the give-up would be
invisible -- a bot with a target locked and silent guns would read in the
status line exactly like a bot with nothing to shoot. That is the shape #343's
review caught, and the one that made this whole class of bug hard to see from
a console in the first place.

**It reports the rule's own answer, and the number it prints now means what it
says.** Before #389 this restated the arm's conditions in its own `if` chain
while a third restatement in `updateMemoryForNewReadingFromGame` advanced the
number -- three copies, and the counter's copy was the one that was wrong. Every
line here names a `WeaponsStep`, so a console reads the decision that was taken
rather than a description of it, and "N readings spent asking" counts only
readings on which this arm asked.

The bound is printed beside the count on the two lines that are still spending
it, because "5 readings" means nothing without the allowance beside it.

-}
describeWeaponsAsk : BotDecisionContext -> String
describeWeaponsAsk context =
    let
        spent : String
        spent =
            String.fromInt context.memory.weaponsAskedReadings
                ++ " of "
                ++ String.fromInt weaponsAskedReadingsBound
                ++ " readings spent asking one to activate."
    in
    case weaponsStepFromContext context of
        FriendlyFireHoldsTheTrigger ->
            "Weapons: HELD by the friendly fire guard."

        NoShipUIToFireFrom ->
            "Weapons: no ship UI in this reading, so nothing to fire with."

        NoTargetToFireOn ->
            "Weapons: nothing locked."

        GaveUpOnWeapons ->
            "Weapons: GAVE UP after "
                ++ String.fromInt context.memory.weaponsAskedReadings
                ++ " readings asking a weapon to come active on a locked target."

        AllWeaponsCycling ->
            "Weapons: target locked and every weapon cycling, " ++ spent

        ActivateAWeapon ->
            "Weapons: target locked, " ++ spent


{-| What the approach on the commander is doing, in one line.

Exists for the reason `describeWeaponsAsk` and `describeAccelerationGateAsk`
do: every answer `approachTheFleetCommander` gives other than "press it" is
`Nothing`, and from outside the decision tree a give-up, a commander this bot
cannot name, and a ship that is already approaching are the same silence.

**This line is where a first live run reports on what is unverified.** Nothing
in this repo has watched a double click on a _pilot's_ overview row command an
approach -- saxrat double clicks a rat's row for exactly this, but no run has
recorded `ManeuverApproach` coming back; the fall-back it degrades to is the
proven half, `eve-online-mission-runner`'s `selectedItemApproach`. So
`FELL BACK to the panel's Approach button` here is the measurement that would
swap the two, and `GAVE UP after N readings` is what it looks like when neither
works -- a spent budget and a named cause, rather than a bot that quietly
believes it is keeping station.

**It also names `orbit-fc-range` when an operator has set it**, because that
key no longer decides anything: `approachTheFleetCommander` does not drive the
Orbit flyout it used to name a rung of. A setting that silently does nothing is
the failure this clause exists to prevent, and deleting the key instead would
end a session that has it set (#161).

The commander's rendered distance is printed because an approach closes to the
client's own default approach distance rather than to anything this bot asks
for, so the distance is the only evidence available of where this ship actually
ended up.

-}
describeApproachFleetCommanderAsk : BotDecisionContext -> String
describeApproachFleetCommanderAsk context =
    let
        commanderEntry : Maybe OverviewWindowEntry
        commanderEntry =
            fleetCommanderOverviewEntry context.readingFromGameClient

        strayWindow : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
        strayWindow =
            windowOpenedOverTheClient context.readingFromGameClient

        askedReadings : Int
        askedReadings =
            context.memory.approachFleetCommanderAskedReadings

        spentOf : String
        spentOf =
            String.fromInt askedReadings
                ++ " of "
                ++ String.fromInt approachFleetCommanderDoubleClickAskedReadingsBound
                ++ " on the double click, "
                ++ String.fromInt approachFleetCommanderAskedReadingsBound
                ++ " in all."

        commanderDistance : String
        commanderDistance =
            commanderEntry
                |> Maybe.andThen .objectDistance
                |> Maybe.withDefault "an unread distance"

        -- #397. Printed on every reading the window is open, because from
        -- outside the tree a reading in which the approach outranked the fight
        -- and one in which it merely came last read identically -- and the
        -- window is the whole change.
        landingCloseClause : String
        landingCloseClause =
            if context.memory.closingOnTheCommanderSinceLanding then
                "CLOSING SINCE LANDING (this outranks the fight until the client"
                    ++ " names the manoeuvre 'Approach'), "

            else
                ""

        rangeSettingClause : String
        rangeSettingClause =
            if context.eventContext.botSettings.orbitFleetCommanderRange == defaultOrbitFleetCommanderRange then
                ""

            else
                " ('orbit-fc-range="
                    ++ context.eventContext.botSettings.orbitFleetCommanderRange
                    ++ "' is accepted and IGNORED: this bot commands an approach"
                    ++ " and no longer drives the Orbit menu that key named a rung of.)"
    in
    "Approach on the commander: "
        ++ landingCloseClause
        ++ (case
                approachFleetCommanderStep
                    { settingIsYes =
                        approachFleetCommanderIsAsked
                            { settingIsYes = context.eventContext.botSettings.orbitFleetCommander == PromptParser.Yes
                            , closingSinceLanding = context.memory.closingOnTheCommanderSinceLanding
                            }
                    , commanderOnGrid = commanderEntry /= Nothing
                    , shipIsWarpingOrJumping = shipIsWarpingOrJumpingFromReading context.readingFromGameClient
                    , shipIsApproaching = shipIsApproachingFromReading context.readingFromGameClient
                    , strayWindowIsOpen = strayWindow /= Nothing
                    , panelShowsTheCommander = panelIsShowingTheFleetCommander context.readingFromGameClient
                    , panelOffersApproach =
                        selectedItemButtonNamed context.readingFromGameClient selectedItemApproachButtonName /= Nothing
                    , askedReadings = askedReadings
                    }
            of
                ApproachFleetCommanderIsOff ->
                    "station-keeping off ('orbit-fc=no'). The close on landing"
                        ++ " is NOT governed by that key (#397) and still runs."

                NoCommanderOnGrid ->
                    case fleetCommanderNameFromFleetWindowHeader context.readingFromGameClient of
                        Nothing ->
                            "the fleet window's header names no commander, so there is nothing to approach."

                        Just commander ->
                            "'"
                                ++ commander
                                ++ "' has NO OVERVIEW ROW. Either they are not on this grid, or the"
                                ++ " active overview preset does not show fleet members -- this bot"
                                ++ " cannot tell those apart and cannot change the preset. See"
                                ++ " WINGMAN.md's setup section."

                ShipIsWarpingOrJumping ->
                    "the ship is warping or jumping."

                AlreadyApproaching ->
                    "approaching, commander at " ++ commanderDistance ++ "." ++ rangeSettingClause

                CloseAWindowLeftOverTheClient ->
                    "a '"
                        ++ (strayWindow
                                |> Maybe.map (.uiNode >> .pythonObjectTypeName)
                                |> Maybe.withDefault "?"
                           )
                        ++ "' is over the client while asking -- closing it. Readings spent: "
                        ++ spentOf

                ApproachByDoubleClick ->
                    "double clicking the commander's overview row, commander at "
                        ++ commanderDistance
                        ++ ". Readings spent: "
                        ++ spentOf
                        ++ rangeSettingClause

                SelectTheCommandersRow ->
                    "FELL BACK to the panel's Approach button after "
                        ++ String.fromInt approachFleetCommanderDoubleClickAskedReadingsBound
                        ++ " double clicks -- selecting the commander's row first. Readings spent: "
                        ++ spentOf

                WaitForTheApproachButton ->
                    "FELL BACK to the panel's Approach button, the commander's row is selected and"
                        ++ " the panel offers no '"
                        ++ selectedItemApproachButtonName
                        ++ "' yet. Readings spent: "
                        ++ spentOf

                PressTheApproachButton ->
                    "FELL BACK to the panel's Approach button after "
                        ++ String.fromInt approachFleetCommanderDoubleClickAskedReadingsBound
                        ++ " double clicks -- pressing it, commander at "
                        ++ commanderDistance
                        ++ ". Readings spent: "
                        ++ spentOf

                GaveUpOnTheApproach ->
                    "GAVE UP after "
                        ++ String.fromInt askedReadings
                        ++ " readings, the double click and the panel's Approach button both, with the client"
                        ++ " never naming the manoeuvre 'Approach'. Commander at "
                        ++ commanderDistance
                        ++ "."
                        ++ (case strayWindow of
                                Nothing ->
                                    ""

                                Just window ->
                                    " A '"
                                        ++ window.uiNode.pythonObjectTypeName
                                        ++ "' is still open over the client."
                           )
           )


{-| What the warp to a fleet-mate on this grid is doing, in one line.

Exists for the reason `describeWeaponsAsk`, `describeAccelerationGateAsk` and
`describeApproachFleetCommanderAsk` do, and #373 is the issue that proves the
need: `warpToFleetMateOnThisGrid` answers `Nothing` when it gives up, and from
outside the decision tree a spent budget and a grid with no fleet-mate on it
are the same silence. This is also the only place a run says which of the two
mechanisms it took, which is what would turn `warpToFleetMateOnThisGrid`'s
round bound into a measured one.

-}
describeFleetMateWarp : BotDecisionContext -> String
describeFleetMateWarp context =
    "Warp to a fleet-mate: "
        ++ (case
                fleetMateToWarpToOnThisGrid
                    { followFleetBroadcastFrom = context.eventContext.botSettings.followFleetBroadcastFrom
                    , recoveringFromRetreat = context.memory.recoveringFromRetreat
                    }
                    context.readingFromGameClient
            of
                Nothing ->
                    "nobody this ship is flying to has a row on this overview."

                Just pilot ->
                    let
                        askedReadings : Int
                        askedReadings =
                            context.memory.goToFleetMateWarpAskedReadings

                        spentOf : String
                        spentOf =
                            " Readings spent: "
                                ++ String.fromInt askedReadings
                                ++ " of "
                                ++ String.fromInt fleetMateWarpAskedReadingsBound
                                ++ "."
                    in
                    case
                        fleetMateWarpStep
                            { broadcastBannerNamesThisMate =
                                fleetMateBroadcastBannerElement
                                    context.eventContext.botSettings.followFleetBroadcastFrom
                                    pilot
                                    context.readingFromGameClient
                                    /= Nothing
                            , panelShowsTheMate =
                                overviewEntryForPilot pilot context.readingFromGameClient
                                    |> Maybe.map (selectedItemIsOverviewEntry context.readingFromGameClient)
                                    |> Maybe.withDefault False
                            , panelOffersWarpTo =
                                selectedItemButtonNamed context.readingFromGameClient "selectedItemWarpTo" /= Nothing
                            , askedReadings = askedReadings
                            }
                    of
                        GaveUpOnReachingTheMate ->
                            "GAVE UP after "
                                ++ String.fromInt askedReadings
                                ++ " readings asking to warp to '"
                                ++ pilot
                                ++ "', who is on this grid."

                        WarpToTheMateFromTheBroadcast ->
                            "'"
                                ++ pilot
                                ++ "' is broadcasting -- warping from the banner's own 'Fleet Member' menu."
                                ++ spentOf

                        SelectTheMate ->
                            "selecting '"
                                ++ pilot
                                ++ "''s overview row, so the panel's own Warp To acts on it."
                                ++ spentOf

                        WaitForTheMatesWarpButton ->
                            "'"
                                ++ pilot
                                ++ "' is selected and the panel offers no 'selectedItemWarpTo' yet."
                                ++ spentOf

                        PressWarpToTheMate ->
                            "pressing the panel's own Warp To at '"
                                ++ pilot
                                ++ "'."
                                ++ spentOf
           )


{-| Where "who is in this fleet" was answered from this reading, and what it
answered -- printed on every reading, whether or not anything is locked.

**This line is half of #367.** Its report was written on a 18,974-line run in
which `grep "is in this fleet"` returned nothing at all, and from outside
there was no way to tell whether the guard had never had a candidate or had
never had a fleet list to check one against. `fleetMemberNames` answers `[]`
for a shut window exactly as it does for a pilot flying alone, so the two
states are one line of log unless the source itself is named.

The Fleet window's absence is shouted rather than mentioned, because it is the
operator's own remedy: opening it is what lets this bot tell a fleetmate from
a stranger, and while it is shut the guns are refused on every pilot on the
overview.

**Since #380 the clause says which of the four answers the reading gave**,
through `describeFleetRosterVerdict`, because "the Fleet window is open and
lists 0 member rows" was printed on the reading Greta would have shot a
fleetmate on and read exactly like verification. The rows, the commander and
the chat icons are still all printed beside it: the verdict says whether the
list may be believed and those say what is in it.

-}
describeFleetMembership : BotDecisionContext -> String
describeFleetMembership context =
    let
        reading : ReadingFromGameClient
        reading =
            context.readingFromGameClient

        namesOrNone : List String -> String
        namesOrNone names =
            if List.isEmpty names then
                "none"

            else
                String.join ", " names

        memberRows : List String
        memberRows =
            fleetMemberNames reading

        chatFleetmates : List String
        chatFleetmates =
            fleetmateNamesFromLocalChat reading

        describeCommander : String
        describeCommander =
            case fleetCommanderNameFromFleetWindowHeader reading of
                Just fromHeader ->
                    "'" ++ fromHeader ++ "' (fleet window header)"

                Nothing ->
                    case List.head context.eventContext.botSettings.followFleetBroadcastFrom of
                        Just fromSetting ->
                            "'" ++ fromSetting ++ "' ('follow-fleet-broadcast-from', the header named nobody)"

                        Nothing ->
                            "NOT NAMED -- the header gave no answer and 'follow-fleet-broadcast-from' is unset"
    in
    "Fleet membership: "
        ++ describeFleetRosterVerdict
            (fleetRosterVerdict
                context.eventContext.botSettings.followFleetBroadcastFrom
                reading
            )
        ++ " Member rows: "
        ++ String.fromInt (List.length memberRows)
        ++ " ("
        ++ namesOrNone memberRows
        ++ "). Commander: "
        ++ describeCommander
        ++ ". Local chat's standing icons mark "
        ++ String.fromInt (List.length chatFleetmates)
        ++ ": "
        ++ namesOrNone chatFleetmates
        ++ "."


{-| The verdict in words, for the membership clause and -- through
`describeFleetRosterVerdictBriefly`, which this contains -- for the guard's own
`HOLDING FIRE` sentence.

One wording rather than two, because the two clauses are printed side by side
and a reader comparing them is entitled to assume they are talking about the
same reading. The remedy is named on every refusing answer, since the operator
opening the window or expanding its wings is what ends the refusal.

-}
describeFleetRosterVerdict : FleetRosterVerdict -> String
describeFleetRosterVerdict verdict =
    case verdict of
        RosterIsComplete _ ->
            "corroborated -- " ++ describeFleetRosterVerdictBriefly verdict ++ "."

        _ ->
            "NOT CORROBORATED -- "
                ++ describeFleetRosterVerdictBriefly verdict
                ++ ", so an empty or short member list would otherwise read as"
                ++ " 'nobody here is a fleetmate'. Open the Fleet window and expand"
                ++ " its wings and squads to fire on players again."


describeFleetRosterVerdictBriefly : FleetRosterVerdict -> String
describeFleetRosterVerdictBriefly verdict =
    case verdict of
        FleetWindowIsShut ->
            "the Fleet window is not open"

        FleetSizeNotStated ->
            "the Fleet window is open but its header states no fleet size"

        RosterIsShort { statedSize, resolvedPilots } ->
            "the Fleet window's header states "
                ++ String.fromInt statedSize
                ++ " pilots and only "
                ++ String.fromInt resolvedPilots
                ++ " could be resolved"

        RosterIsComplete { statedSize, resolvedPilots } ->
            "the Fleet window's header states "
                ++ String.fromInt statedSize
                ++ " pilots and "
                ++ String.fromInt resolvedPilots
                ++ " are resolved"


{-| What the friendly fire guard did with the lock bar this reading.

The other half of #367, and the reason it is separate from
`describeFleetMembership`: that line says what could be known, this one says
what was decided with it. Every answer but `UnlockAFleetPilot` leaves the
decision tree looking like a bot with nothing to do.

**Every refusal names the instrument that saw the pilot**, which is #390's half
of it. The guard reads two of them and they fail in opposite directions, so a
log that only said "held" would leave the next incident reasoning from silence
about which one was working -- the same reasoning-from-silence #367 was filed
on, one level down.

-}
describeFriendlyFireGuard : BotDecisionContext -> String
describeFriendlyFireGuard context =
    let
        askedReadings : Int
        askedReadings =
            context.memory.unlockFleetPilotAskedReadings
    in
    "Friendly fire guard: "
        ++ (case friendlyFireStepFromContext context of
                NothingIsLocked ->
                    "nothing is locked."

                UnlockAFleetPilot fleetPilot signal ->
                    if targetBarSawThePilot signal then
                        "'"
                            ++ fleetPilot
                            ++ "' is locked and is in this fleet -- UNLOCKING, guns held. Seen by "
                            ++ describeLockedPilotSignal signal
                            ++ ". Readings spent: "
                            ++ String.fromInt askedReadings
                            ++ " of "
                            ++ String.fromInt unlockFleetPilotAskedReadingsBound
                            ++ "."

                    else
                        "'"
                            ++ fleetPilot
                            ++ "' is locked and is in this fleet -- guns held. Seen by "
                            ++ describeLockedPilotSignal signal
                            ++ " alone, which names no target-bar entry to right-click,"
                            ++ " so there is nothing to unlock."

                GaveUpUnlockingAFleetPilot fleetPilot signal ->
                    "GAVE UP unlocking '"
                        ++ fleetPilot
                        ++ "' after "
                        ++ String.fromInt askedReadings
                        ++ " readings. Seen by "
                        ++ describeLockedPilotSignal signal
                        ++ ". The guns stay held for as long as that lock is there."

                HoldFireOnAnUnverifiedPilot pilot signal ->
                    "HOLDING FIRE on '"
                        ++ pilot
                        ++ "' -- a pilot on the overview, seen by "
                        ++ describeLockedPilotSignal signal
                        ++ ", and this bot cannot tell whether they are a fleetmate because "
                        ++ describeFleetRosterVerdictBriefly
                            (fleetRosterVerdict
                                context.eventContext.botSettings.followFleetBroadcastFrom
                                context.readingFromGameClient
                            )
                        ++ "."

                ClearToFire ->
                    String.fromInt (List.length context.readingFromGameClient.targets)
                        ++ " locked, none of them a fleet pilot -- clear to fire."
           )


describeLockedPilotSignal : LockedPilotSignal -> String
describeLockedPilotSignal signal =
    case signal of
        TargetBarLabels ->
            "the target bar's labels"

        OverviewRowIndicator ->
            "the overview row's lock indicator"

        BothSignals ->
            "the target bar's labels and the overview row's lock indicator"


{-| The acceleration-gate ask, for the status line -- printed on every reading
whether or not this bot is currently the one holding the tree, so a give-up
that already handed the turn back is still visible.
-}
describeAccelerationGateAsk : BotDecisionContext -> String
describeAccelerationGateAsk context =
    case accelerationGateToAct context.readingFromGameClient of
        Nothing ->
            "Acceleration gate: none on the overview."

        Just gateToTake ->
            let
                askedReadings : Int
                askedReadings =
                    context.memory.gateAskedReadings

                mayBeTaken : Bool
                mayBeTaken =
                    gateMayBeTaken
                        { ratsOnTheGrid =
                            not (List.isEmpty (getNamesOfRatsInOverview context.readingFromGameClient))
                        , calledByTheCommander = gateToTake.calledByTheCommander
                        }
            in
            "Acceleration gate: on the overview"
                ++ (if gateToTake.calledByTheCommander then
                        " and CALLED by the commander, "

                    else
                        ", "
                   )
                ++ (if not mayBeTaken then
                        "rats still on the grid -- not taking it."

                    else
                        (case
                            calledGateDroneRecall
                                { calledByTheCommander = gateToTake.calledByTheCommander
                                , dronesAreInSpace = dronesAreInSpace context.readingFromGameClient
                                , askedReadings = context.memory.calledGateRecallAskedReadings
                                }
                         of
                            RecallTheDronesFirst ->
                                "holding it for the drones ("
                                    ++ String.fromInt context.memory.calledGateRecallAskedReadings
                                    ++ " of "
                                    ++ String.fromInt calledGateDroneRecallGiveUpReadings
                                    ++ " readings of recall), "

                            LeaveTheDronesBehind ->
                                "DRONES GIVEN UP ON after "
                                    ++ String.fromInt context.memory.calledGateRecallAskedReadings
                                    ++ " readings of recall, "

                            NoDroneRecallBeforeThisGate ->
                                ""
                        )
                            ++ (if accelerationGateHasBeenGivenUpOn askedReadings then
                                    "GIVEN UP after "
                                        ++ String.fromInt askedReadings
                                        ++ " readings of asking."

                                else
                                    "readings spent asking: "
                                        ++ String.fromInt askedReadings
                                        ++ " of "
                                        ++ String.fromInt accelerationGateRefusesThisShipTicks
                                        ++ "."
                               )
                   )


{-| What the commander's `Target` broadcast named, for the status line.

**Printed on every reading a broadcast is up**, because the arm's answers here
are silences an operator cannot otherwise tell apart. A called gate that is not
drawn falls through to the drones and the guns, which reads exactly like no
broadcast at all; and a called name no overview row carries reads exactly like a
called gate whose banner text is not the overview's Name cell -- which is #393's
own unverified premise and the thing to watch on the first run that meets one.

**And since #395 it is the only thing that reports the give-up**, because that
one hands the reading back and a `Nothing` carries no decision line: without the
clause below, a bot that has stopped acting on a stale call and a bot that never
had one to act on print the same reading.

-}
describeCalledObject : BotDecisionContext -> String
describeCalledObject context =
    case fleetBroadcastBannerText context.readingFromGameClient |> Maybe.andThen targetBroadcastPilotName of
        Nothing ->
            "Called target: none on the banner."

        Just calledTarget ->
            let
                -- Bound once and handed to both clauses, so this function's
                -- read of the gone verdict stays the one read the status line
                -- makes of it.
                gone : Maybe CalledTargetGone
                gone =
                    context.memory.calledTargetGone
            in
            describeCalledObjectOnOverview
                calledTarget
                (calledObjectOnOverviewFromReading calledTarget context.readingFromGameClient)
                ++ describeCalledTargetGone calledTarget gone
                ++ (case
                        calledTargetTheLockIsWorkingOn
                            context.eventContext.botSettings.followFleetBroadcastFrom
                            gone
                            context.readingFromGameClient
                    of
                        Nothing ->
                            -- The lock is not this reading's question -- the
                            -- target is locked, or the call is a gate, a
                            -- fleetmate or one #395 has given up on -- and a
                            -- clause claiming a click on any of those would be
                            -- a decision this bot did not take.
                            ""

                        Just _ ->
                            describeCalledTargetLock
                                (bannerCtrlClickAskedReadings calledTarget context.memory.bannerCtrlClick)
                                (lockCalledTargetStepFromReading
                                    context.memory.bannerCtrlClick
                                    context.readingFromGameClient
                                    calledTarget
                                )
                   )


{-| The clause above, as a function of the name and the rule's own answer, so a
case executes what an operator reads rather than asserting a substring over the
branch. `describeWeaponsAsk`'s arrangement, for its reason.
-}
describeCalledObjectOnOverview : String -> CalledObjectOnOverview -> String
describeCalledObjectOnOverview calledTarget calledObject =
    "Called target '"
        ++ calledTarget
        ++ "': "
        ++ (case calledObject of
                CalledObjectIsAnAccelerationGate _ ->
                    "it is an ACCELERATION GATE, so this is the commander sending the fleet through rather than a call to shoot it -- taking it, rats on the grid or not."

                CalledGateIsNotDisplayed ->
                    "it is an ACCELERATION GATE, but its overview row is not drawn -- that row's region belongs to whatever was recycled into its place, so nothing here will click it."

                CalledObjectIsNotAGate ->
                    "an overview row names it and it is not an acceleration gate, so it is a target to shoot."

                CalledNameNamesNoOverviewRow ->
                    "NO OVERVIEW ROW names it, so nothing here can tell whether it is an acceleration gate and no context menu can be opened on it -- but the broadcast banner can still be ctrl-clicked, which is the case that mechanism exists for. It may be dead, this pilot's overview preset may not show it, or the banner's own wording may not be the overview's Name cell."
           )


{-| How long the current call has named nothing on the grid, and whether this
bot has stopped acting on it.

Rendered from the record rather than inline in `describeCalledObject` so a case
executes what an operator reads -- `describeWeaponsAsk`'s arrangement, and the
one #109 records a status clause passing a case while printing nothing at all.

The commonest reading has no such record and says nothing, so an ordinary call
is unaffected; the two that do are the whole of what #395 leaves an operator to
watch, since the give-up itself is a `Nothing` and cannot speak.

-}
describeCalledTargetGone : String -> Maybe CalledTargetGone -> String
describeCalledTargetGone calledTarget gone =
    case gone of
        Nothing ->
            ""

        Just goneTarget ->
            if goneTarget.calledTarget /= calledTarget then
                ""

            else if calledTargetHasBeenGivenUpOn calledTarget gone then
                " GIVEN UP ON after "
                    ++ String.fromInt goneTarget.readings
                    ++ " readings naming no row -- the banner never clears, so this call is left alone and the drones, the guns and the gate get their turn. A new broadcast starts this over."

            else
                " No row has named it for "
                    ++ String.fromInt goneTarget.readings
                    ++ " of "
                    ++ String.fromInt calledTargetGoneReadings
                    ++ " readings; past that this call is left alone."


{-| Which of the two mechanisms is being used to lock this call, and why.

**Rendered from the rule's own answer** rather than written inline in the status
line, so a case executes what an operator reads -- `describeWeaponsAsk`'s
arrangement, and the one #109 records a status clause passing a case while
printing nothing at all.

**Which path was taken is the whole point of the clause**, because #366 ships
with the client's answer to a banner ctrl-click unknown: a run that never leaves
the cascade and a run that never reaches it are the two things to tell apart on
the first run that meets a call, and from a decision line alone they read the
same. The count is printed beside the bound for the reason every other budget in
this file prints one -- a give-up whose arithmetic nobody can see is a give-up
nobody can size.

-}
describeCalledTargetLock : Int -> LockCalledTargetStep -> String
describeCalledTargetLock askedReadings step =
    " Lock: "
        ++ (case step of
                CtrlClickTheBroadcastBanner ->
                    "CTRL-CLICKING THE BROADCAST BANNER, asked on "
                        ++ String.fromInt askedReadings
                        ++ " of "
                        ++ String.fromInt bannerCtrlClickAskedReadingsBound
                        ++ " readings -- one dispatch, no context menu and no overview row needed."

                LockFromTheOverviewRow ->
                    if bannerCtrlClickHasBeenGivenUpOn askedReadings then
                        "THE BANNER CLICK DID NOT LOCK IT in "
                            ++ String.fromInt askedReadings
                            ++ " readings, so the overview row's own 'Lock Target' cascade has it instead. A new call starts the click over."

                    else
                        "no banner in this reading to click, so the overview row's own 'Lock Target' cascade has it."

                NoWayToLockTheCalledTarget ->
                    "NOTHING HERE CAN LOCK IT -- no broadcast banner to click and no overview row to open a menu on."
           )
