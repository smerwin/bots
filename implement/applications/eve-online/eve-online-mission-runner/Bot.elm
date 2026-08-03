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

   ## When the ship is lost

   A destroyed ship leaves the character in a capsule, still flying, on the
   same grid as whatever killed it -- and a capsule reads 100% shield and 100%
   armour, so nothing about the health line says anything is wrong. Run 7 kept
   running missions in one for its whole 86 readings, at 0.0 m/s among the pack
   that had just killed it, and a stationary pod in a hostile pocket is a
   podding, which costs the clone and its implants.

   The bot now recognises it from two signals and stops. Either the client's own
   `(notify)` line -- "The ship you are piloting does not have targeting systems
   installed", which only a capsule ever hears -- or the ship UI carrying no
   module buttons at all for several consecutive readings. Then it stops trying
   to fight, flies the pod to `home-station` (or to whatever station this system
   offers, if none is configured), docks, and **ends the session**, saying why.
   The run's remaining hours are worthless without a ship, and a ship loss is
   something the operator has to know about.

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

     **It is also not what covers a hostile the icon colour misses.** Anything
     the client's combat log names as having hit this ship inside
     `incomingDamageWindowSeconds` is a target for as long as that window holds
     it, with no setting involved -- see `isObjectShootingAtUs`. Listing rats
     here is unnecessary and, because this list never expires, worse than
     leaving them out.
   + `home-station` : Full name of the station to go back to when the drone bay
     has run dry, exactly as the client writes it -- e.g.
     `home-station=Amarr VIII (Oris) - Emperor Family Academy`. Without it the
     bot restocks wherever the mission chain happened to leave it, which is a
     station chosen by the agent and usually holds no drones at all. With it,
     the wind-down sets a route there, flies it, docks and restocks; if the ship
     is already there it just restocks. Give the whole name including the
     parentheses and hyphens: the bot never types this string, it types the part
     after the last " - " into the search bar and then matches this full name
     against the rows that come back. See `routeToStationByName`.

     It is also where the pod goes if the ship is destroyed -- see "When the
     ship is lost" below. Without it the pod docks at whatever station this
     system offers instead, which is worse but is still not sitting still among
     the rats that just killed the ship.
   + `drone-type` : Name of the drone to refill the drone bay with while the
     session winds down, as it appears in the station's item hangar -- e.g.
     `drone-type=Hobgoblin I`. Defaults to `Acolyte I`. Fit-specific, which is
     why it is a setting: the wrong name here does not misload anything, it
     just finds nothing in the hangar. The drone has to be in the root item
     hangar of the station the ship is parked in; sub-folders are not searched.
   + `short-range-ammo` / `long-range-ammo` : Names of the two charges to swap
     between as the current target's distance changes, as the weapon module's
     own right-click menu spells them -- e.g. `short-range-ammo=Scorch M`. The
     menu appends a quantity (`Multifrequency M [4]`), which the bot strips, so
     give the plain name. **Both are needed, or nothing happens at all**: with
     one charge type, or none, there is no swap to make and the bot leaves the
     guns alone rather than guessing. Wrong ammo still does damage, so this is
     an optimisation and doing nothing is always an acceptable outcome.

     Which charge is loaded is read from that same menu, which lists what the
     gun can be switched **to** and omits what is already in it -- so the
     charge that is *missing* is the one loaded. Nothing has to be recognised
     by name beyond the two given here, and no tooltip is involved.

     Note the bot switches the guns off to load, because the client refuses a
     load into a running module and says so only in its own game log, which the
     bot cannot read. That costs a few seconds of damage; it is bounded, and a
     weapon that will not go quiet keeps firing what it already has.
   + `ammo-swap-range` : Distance in meters at which to change over between the
     two charges -- shorter than this the short-range charge, beyond it the
     long-range one. Optional but **recommended**: without it the bot has to
     derive the crossover from the weapons' optimal ranges, which it can only
     read by resting the mouse on a module until a tooltip appears, and whether
     this client shows one at all is unverified. Setting this skips the hover
     entirely. Left unset and the tooltip never appearing, the swap says so and
     does nothing rather than picking a distance out of the air.
   + `orbit-in-combat`: Set this to 'yes' to orbit the target instead of keeping
     range or aligning.
   + `keep-at-range`: Set this to 'yes' to keep range from the target instead of
     orbiting or aligning.
   + `targeting-range`: Distance in meters at which the bot switches from
     locking a target to approaching it. Defaults to 66000. This is a starting
     value, not the last word: the bot narrows it during the session from the
     client's own answers -- the greatest distance at which a lock was accepted
     and the smallest at which one was provably refused -- and the setting is
     clamped between the two. Set it to pin the starting point; it still gives
     way to what the client has actually granted. See `lockRangeThresholdInMeters`.
   + `run-away-shield-hitpoints-threshold-percent` /
     `run-away-armor-hitpoints-threshold-percent`: Dock up when the ship drops
     below these. Disabled by default. Both read the ship's HUD gauges, which
     are not a reliable instrument -- see `plausibleHitpointsPercent` -- and on
     a shield-tanked hull the armour gauge cannot move until the shield is
     already gone, so armour alone is not a guard. Set the shield one.
   + `run-away-incoming-damage-threshold`: Dock up when the client's own combat
     log reports this much damage taken inside
     `incomingDamageWindowSeconds` (45 s). Defaults to 3500 and `-1` disables
     it. This is the retreat that needs no HUD gauge at all: the number comes
     from EVE's own log rather than from a widget read out of live memory. The
     default is calibrated for the hull flown on this account -- across sixteen
     recorded client sessions the worst 45-second window the ship *survived*
     was 3114, and the one it died in peaked at 4101 -- so re-derive it for a
     different hull rather than carrying it over.

   When using more than one setting, start a new line for each setting in the
   text input field. Here is an example of a complete settings string:

   ```
agent-name=Nehrnah Gorouyar
orbit-in-combat=yes
run-away-shield-hitpoints-threshold-percent=50
run-away-armor-hitpoints-threshold-percent=80
run-away-incoming-damage-threshold=3500
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
    , runAwayIncomingDamageThreshold = defaultRunAwayIncomingDamageThreshold
    , avoidRats = []
    , attackObjectNames = []
    , approachObjectNames = []
    , preferWreckNames = []
    , maxTargetCount = 4
    , botStepDelayMilliseconds = 499
    , orbitInCombat = AppSettings.No
    , keepAtRange = AppSettings.No
    , targetingRangeMeters = 66000
    , droneTypeName = "Acolyte I"
    , homeStationName = Nothing
    , shortRangeAmmoName = Nothing
    , longRangeAmmoName = Nothing
    , ammoSwapRangeMeters = Nothing
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
         , ( "run-away-incoming-damage-threshold"
           , AppSettings.valueTypeInteger (\threshold settings -> { settings | runAwayIncomingDamageThreshold = threshold })
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
         , ( "drone-type"
           , AppSettings.valueTypeString
                (\droneTypeName settings -> { settings | droneTypeName = String.trim droneTypeName })
           )
         , ( "home-station"
           , AppSettings.valueTypeString
                (\stationName settings -> { settings | homeStationName = nonEmptySettingValue stationName })
           )
         , ( "short-range-ammo"
           , AppSettings.valueTypeString
                (\ammoName settings -> { settings | shortRangeAmmoName = nonEmptySettingValue ammoName })
           )
         , ( "long-range-ammo"
           , AppSettings.valueTypeString
                (\ammoName settings -> { settings | longRangeAmmoName = nonEmptySettingValue ammoName })
           )
         , ( "ammo-swap-range"
           , AppSettings.valueTypeInteger
                (\rangeMeters settings -> { settings | ammoSwapRangeMeters = Just rangeMeters })
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
    , runAwayIncomingDamageThreshold : Int
    , avoidRats : List String
    , attackObjectNames : List String
    , approachObjectNames : List String
    , preferWreckNames : List String
    , maxTargetCount : Int
    , botStepDelayMilliseconds : Int
    , orbitInCombat : AppSettings.YesOrNo
    , keepAtRange : AppSettings.YesOrNo
    , targetingRangeMeters : Int
    , droneTypeName : String
    , homeStationName : Maybe String
    , shortRangeAmmoName : Maybe String
    , longRangeAmmoName : Maybe String
    , ammoSwapRangeMeters : Maybe Int
    }


{-| A setting whose absence has to be distinguishable from its being blank.

`short-range-ammo=` with nothing after it is how an operator turns the ammo swap
back off from the web console without deleting the line, and an empty string
would otherwise match every context-menu entry.
-}
nonEmptySettingValue : String -> Maybe String
nonEmptySettingValue value =
    case String.trim value of
        "" ->
            Nothing

        trimmed ->
            Just trimmed


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
    , unlootableWreckIds : List String
    , lootAllRefusedTicks : Int
    , lootWindowOutOfRangeTicks : Int
    , dronesInSpaceTicks : Int
    , dronesInSpaceCount : Int
    , droneRecallUnansweredTicks : Int
    , dockedWithCargoWantedTicks : Int
    , nothingToDoTicks : Int
    , lastObjectiveText : String
    , gateWithinReachTicks : Int
    , gateLockedForWantOfAnItem : Maybe String
    , siteAdmitsThisShip : Maybe Bool
    , clearingNotRequired : Bool
    , agentConversationWithoutTrackerTicks : Int
    , keepAtRangeUnconfirmedTicks : Int
    , orbitUnconfirmedTicks : Int
    , readingsCount : Int
    , lowestShieldPercentSinceHealthy : Int
    , lowestArmorPercentSinceHealthy : Int
    , incomingDamage : IncomingDamageMemory
    , droneBayOpenedFromShipCard : Bool
    , droneBayWillTakeNoMore : Bool
    , droneRestockLooksWithRoom : Int
    , droneRestockDragsDispatched : Int
    , droneBayEmptyLastSeen : Maybe Bool
    , shipLoss : Maybe ShipLossVerdict
    , shipUIWithoutModuleButtonsReadings : Int
    , lockAttempt : Maybe LockAttempt
    , lockProvenAtMeters : Maybe Int
    , lockRefusedAtMeters : Maybe Int
    , lockRangeLastChange : Maybe String
    , ammoSwap : AmmoSwapMemory
    }


{-| The bot's conclusion that the ship it is flying no longer exists, and how
many readings ago it reached it.

Latched, and never cleared inside a session. That is the cost asymmetry of #33
written into the type: a false positive parks the pod and ends the run early,
which costs the rest of the session; a false negative leaves a capsule sitting
among the rats that just killed the ship, which costs the clone and every
implant in it. Nothing here may un-conclude a loss on a later reading that
happens to look normal.

`readingsSince` is what bounds the recovery. It counts readings rather than
seconds because `bot-step-delay` moves the wall-clock length of a reading and
nothing in `UpdateMemoryContext` carries the session clock.

-}
type alias ShipLossVerdict =
    { reason : String
    , readingsSince : Int
    }


{-| What the client's combat log has said about incoming fire lately, and what
the HUD was reading while it said it.

A reading's `incomingDamageSinceLastReading` is gone by the next reading, like
every other part of the game-log channel, so a rolling window has to be written
down here -- `updateMemoryForNewReadingFromGame` is the only place that can, and
it is the one place that never sees a decision.

`samples` is newest first and holds only what falls inside
`incomingDamageWindowSeconds`. Each sample carries the hitpoints the HUD showed
on the same reading, because the two questions this memory answers are "how hard
are we being hit" and "is the instrument that is supposed to notice moving at
all", and the second is only answerable by looking at both together.

Each sample also carries the reading's own `topAttacker`, and the set of those
names across the window is what issue #40's target selection reads. Holding the
names *inside* `samples` rather than in a list of their own is what bounds and
clears them without a second rule: they are trimmed by the same clock, capped by
the same `incomingDamageSampleLimit`, and gone `incomingDamageWindowSeconds`
after the last hit -- which covers a rat dying, the ship warping out and a
pocket ending, in one condition none of which has to be detected separately.

`hostCarriesTheChannel` is the `Nothing`-versus-`Just` distinction from the
parser, kept so the status line can say when this whole guard is unarmed. A
host without the channel reports no damage, which reads exactly like a peaceful
grid, and that inference in the wrong direction is this repo's signature
failure.

`retreating` is the latch. See `runAwayIfLowHealth` for why the trip and the
release are different conditions rather than one threshold.
-}
type alias IncomingDamageMemory =
    { samples : List IncomingDamageSample
    , hostCarriesTheChannel : Bool
    , lastAttacker : Maybe String
    , retreating : Bool
    }


type alias IncomingDamageSample =
    { atMilliseconds : Int
    , damage : Int

    -- The plausible HUD reading on this same reading, or `Nothing` where there
    -- was none to believe -- no ship UI, or a value `plausibleHitpointsPercent`
    -- rejected. A `Nothing` is never counted as the gauge moving.
    , hitpoints : Maybe ( Int, Int )

    -- Who the client said hit hardest on this reading, kept per sample rather
    -- than only in `lastAttacker`, because the window of these names is what
    -- `namesOfRecentAttackers` hands to the target selection. See issue #40.
    , attacker : Maybe String
    }


{-| A lock the bot has asked the client for and that the client has not
answered yet.

Started from the effects of the step just dispatched rather than from the
decision that produced them, because only the effects are visible from
`updateMemoryForNewReadingFromGame` -- and the decision tree cannot write
memory. `handle` is what identifies the row across readings; see
`overviewEntryLockHandle` for why a screen position will not do.

`distanceInMeters` is the distance the row showed on the reading the attempt
started, and `targetsCount` the number of locked targets then. Both are needed
at the verdict, and both can have changed by the time it is rendered.
-}
type alias LockAttempt =
    { handle : String
    , distanceInMeters : Int
    , targetsCount : Int
    , readingsWaited : Int
    }


{-| Which end of the ammo pair a charge sits at. Never derived from a name --
only from the optimal range the charge produces, which is the one thing about it
the client actually reports.
-}
type AmmoRange
    = ShortRangeAmmo
    | LongRangeAmmo


{-| Everything the ammo swap knows, kept in one field so the rest of `BotMemory`
is untouched.

`chargeLoaded` is the primary reading and it comes from the weapon's own context
menu, which lists the charges the gun can be switched **to** and omits the one
already in it. Verified live: a weapon holding Radio M offered `Multifrequency M
[4]` and no Radio M at all. So the charge that is *absent* is the charge that is
loaded, and that answer needs no tooltip, no hover, and none of the sprites this
client does not have.

`optimalRangeInMeters` and the `optimalRangeSeen` pair are the secondary reading
and are now a refinement rather than the mechanism. A weapon's optimal range
moves with the charge in it, so it confirms the *effect* where menu membership
confirms only that the client changed its mind about what can be loaded -- and
the midpoint of the two is the crossover distance the swap uses when
`ammo-swap-range` is unset. They come from `weaponOptimalRangeFromHover`, which
may never answer on this client; `optimalRangeGivenUp` records that, and it
disables only this, not the swap.

`rangeVerdictTicks` counts consecutive readings the same verdict has gone
*unsatisfied*, and carries two guards at once. Below `ammoSwapDistanceHoldTicks`
it is target churn and nothing is done; above `ammoSwapVerdictGiveUpTicks` the
load has been commanded and the menu still offers the charge, so this attempt is
abandoned. It resets the moment the verdict is satisfied, so that a struggle
cannot leave a count behind for the next verdict to inherit.

`gunsSilencedTicks` is the one bound over the whole period the ship's guns are
switched off, counted from the reading the swap first told one to stop and
advanced on every reading until it lets go. It answers a question every waiting
state in this path has to answer -- *and what if this never comes?* -- once, for
all of them, rather than each remembering to. Issue #34 is what it is for: the
previous shape bounded one phase and left the next unbounded, and a ship sat
disarmed in a hostile pocket for 298 readings.

`verdictAbandoned` is the ordinary per-attempt give-up: the guns go back to
firing whatever is in them and the next change of range tries again. Failing to a
firing gun with the wrong ammo is always better than failing to a silent gun. The
one exception is that same silence deadline, which switches the swap off for the
session -- having disarmed the ship once and been unable to finish, doing it
again is not worth the ammo it might save.

`loadRefusedByClient` holds the client's own sentence when it says it discarded
the load, and it is kept because the entries it came from are not: a reading's
game log lines are gone by the next reading, so a branch that reads them and
records nothing sees a refusal once and then behaves exactly as it did before.
It is a shortcut to the same abandonment those bounds reach, not a new outcome --
what it changes is that the answer arrives on the reading the client gave it
rather than twenty-five readings later, and that the log can quote why.

`gunsCommandedThisVerdictAtX` is how the walk across a multi-gun row remembers
where it got to, keyed on each gun's `x` because the row is not a stable index
space. A gun goes in the list when its context menu was *opened*, which is the
bot asking rather than the client answering -- but unlike the previous design
each gun's own menu then says whether it carries the charge, so a gun that was
visited and did not take the load is visible rather than assumed. What is still
assumed is the guns before the last one: `verdictSatisfied` is decided on the
last gun's menu, so a load that silently failed on an earlier gun leaves that gun
on the old charge. The cost of being wrong is one weapon firing the charge it
already had.

`menuOpenOnGunAtX` is how the bot knows an open context menu is a weapon's, and
which weapon's: nothing in the menu itself says where it came from, but the bot
opened it and the previous step's effects say where it clicked.
-}
type alias AmmoSwapMemory =
    { chargeLoaded : Maybe AmmoRange
    , optimalRangeInMeters : Maybe Int
    , optimalRangeSeenLow : Maybe Int
    , optimalRangeSeenHigh : Maybe Int
    , rangeVerdict : Maybe AmmoRange
    , rangeVerdictTicks : Int
    , verdictSatisfied : Bool
    , verdictAbandoned : Bool
    , loadRefusedByClient : Maybe String
    , gunsSilencedTicks : Int
    , gunsCommandedThisVerdictAtX : List Int
    , menuOpenOnGunAtX : Maybe Int
    , hoverAwaitingTooltip : Bool
    , hoverUnansweredTicks : Int
    , optimalRangeGivenUp : Bool
    , givenUp : Maybe String
    }


initAmmoSwapMemory : AmmoSwapMemory
initAmmoSwapMemory =
    { chargeLoaded = Nothing
    , optimalRangeInMeters = Nothing
    , optimalRangeSeenLow = Nothing
    , optimalRangeSeenHigh = Nothing
    , rangeVerdict = Nothing
    , rangeVerdictTicks = 0
    , verdictSatisfied = False
    , verdictAbandoned = False
    , loadRefusedByClient = Nothing
    , gunsSilencedTicks = 0
    , gunsCommandedThisVerdictAtX = []
    , menuOpenOnGunAtX = Nothing
    , hoverAwaitingTooltip = False
    , hoverUnansweredTicks = 0
    , optimalRangeGivenUp = False
    , givenUp = Nothing
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory


missionBotDecisionRoot : BotDecisionContext -> DecisionPathNode
missionBotDecisionRoot context =
    -- A learned bound announces itself here, at the root, rather than in the
    -- branch that learned it -- the bounds move in `updateMemoryForNewReading-
    -- FromGame`, which runs on every reading whatever the bot is doing, and a
    -- self-adjusting number that adjusts silently is what made #7 take a whole
    -- session to diagnose. `lockRangeLastChange` holds a message only on the
    -- reading a bound actually moved, so this is one line per change.
    (case context.memory.lockRangeLastChange of
        Just lockRangeChange ->
            describeBranch lockRangeChange (missionBotDecisionRootBeforeApplyingSettings context)

        Nothing ->
            missionBotDecisionRootBeforeApplyingSettings context
    )
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


missionBotDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
missionBotDecisionRootBeforeApplyingSettings context =
    case
        -- The pod recovery sits above the wind-down, and above the
        -- docked-or-in-space split below, because a lost ship outranks both:
        -- there is no mission left to wind down from, and every branch that
        -- locks, shoots, approaches or loots lives under the split. See
        -- `recoverPodAfterShipLoss`. It is below `generalSetupInUserInterface`
        -- only because the pod still needs the location info panel expanded and
        -- stray menus cleared to travel at all.
        [ generalSetupInUserInterface context.readingFromGameClient
        , recoverPodAfterShipLoss context
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


{-| How long past the planned end to keep trying to dock before ending the
session in space instead.

Generous, because a legitimate trip home is a warp and a dock and can take a
couple of minutes. Bounded, because every way that trip fails previously ran
until something else stopped the session -- and the host only announces the
deadline, it does not enforce it.
-}
secondsPastSessionEndBeforeGivingUpOnDocking : Int
secondsPastSessionEndBeforeGivingUpOnDocking =
    120


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
                                if secondsRemaining <= dockedWindDownDeadlineSeconds context then
                                    -- Parked with the session over, so stop.
                                    -- The host only *announces* the deadline --
                                    -- it does not stop its own loop -- so a bot
                                    -- that just parks here ticks on forever.
                                    -- Observed running 2h11m past a 180-minute
                                    -- session, printing "Already docked. Stay
                                    -- put." 7,633 times.
                                    describeBranch
                                        (dockedWindDownFinishReason context)
                                        (Common.DecisionPath.endDecisionPath FinishSession)

                                else
                                    case goToHomeStationWhileDocked context of
                                        Just goHome ->
                                            goHome

                                        Nothing ->
                                            case maintenanceWhileDocked context of
                                                Just maintenance ->
                                                    maintenance

                                                Nothing ->
                                                    describeBranch "Already docked. Stay put." waitForProgressInGame

                            Just _ ->
                                if secondsRemaining <= -(windDownOverrunAllowanceSeconds context) then
                                    -- Still in space well past the deadline, so
                                    -- stop trying to park and end the session
                                    -- where we are.
                                    --
                                    -- Docking during wind-down fails in more
                                    -- ways than can be enumerated here, and each
                                    -- one previously ran until something else
                                    -- killed the session. Run 118 could not get
                                    -- its drones back and overran by five
                                    -- minutes. Run 121 was in Ebidan, a system
                                    -- with no station at all, and spent the
                                    -- whole window right-clicking for a
                                    -- "Stations" entry the menu cannot contain --
                                    -- 32 cascades, never docked, never finished.
                                    --
                                    -- This is the backstop for all of them: the
                                    -- session ending is what matters, and ending
                                    -- it undocked is worth more than not ending
                                    -- it. It does not repair the underlying
                                    -- cause, which is why it says what happened.
                                    describeBranch
                                        (inSpaceWindDownFinishReason context secondsRemaining)
                                        (Common.DecisionPath.endDecisionPath FinishSession)

                                else
                                    case goToHomeStationWhileInSpace context of
                                        Just goHome ->
                                            goHome

                                        Nothing ->
                                            returnDronesToBay context
                                                (dockAtStation
                                                    context.memory.lastDockedStationNameFromInfoPanel
                                                    context
                                                )
                        )
                    )



-- The home station


{-| How long past the planned session end a trip to the home station may run.

The trip is the one thing in the wind-down that legitimately takes longer than
the window it starts in: `secondsBeforeSessionEndToWindDown` is 200 seconds and
a couple of jumps plus a dock is several minutes. Rather than let it be cut off
halfway -- which strands the ship in space, the worst of both outcomes -- the
trip raises the overrun allowance that
`secondsPastSessionEndBeforeGivingUpOnDocking` normally sets.

Raising it is only safe because it stays a deadline. Issues #7 and #14 were both
the same shape: a wait with no end, which reads in the log exactly like a bot
working. This is a longer bound, not a missing one -- when it expires the
session *ends*, loudly, naming the station it never reached.
-}
homeStationTripSecondsPastSessionEnd : Int
homeStationTripSecondsPastSessionEnd =
    420


{-| How long past the planned session end the restock at the home station may
run, once the ship is actually there.

Much smaller than the trip's allowance, and for a different risk. The trip is
bounded because travel is slow; this is bounded because the restock is what has
to finish inside it, and the restock's own bound is a count of looks rather than
a clock (`droneRestockLooksBeforeGivingUp`). Sixty seconds is about ten
readings, which covers the three looks and two drags that budget allows.

Normally it is not spent: the grace ends as soon as the restock latches
`droneBayWillTakeNoMore`. The clock is what covers the case where no verdict
arrives -- a gauge this build renders differently, say -- since a look budget
that runs out ends the restock by *falling silent*, which on its own would leave
the session parked here until the deadline.
-}
homeStationRestockGraceSeconds : Int
homeStationRestockGraceSeconds =
    60


{-| The home station, when one is configured *and* there is a reason to go
there. Both halves are the trigger, so a bot whose bay still holds drones winds
down exactly as it did before this existed.

**The reason is an empty bay, where the restock's own reason is a bay that is
not full, and the two are deliberately different questions.**
`restockDroneBayWhileDocked` tops up 9 drones of 10 because it is standing in
the station already and the cost of acting is one drag. This decides whether to
abandon the wind-down, undock, fly several jumps and risk ending the session in
space -- and 9 of 10 is not worth that, while none of 10 is. The asymmetry is
in the cost of the action, not in the reading.

It is also what the instrument can say. `droneBayEmptyLastSeen` comes from the
drones window, the only view of the bay that exists in space, and that window
titles the bay group with a bare count and no capacity -- so fullness is not a
question an in-space reading can answer at all. See
`droneBayIsEmptyFromDronesWindow`.

`droneBayWillTakeNoMore` is #24's verdict from the *other* instrument, and is
respected here for the case it can arise in: a bay whose gauge already read
full, or a drop the client already refused, is not a reason to fly anywhere. It
resets on undock, so it never suppresses a trip decided in space.
-}
homeStationToGoTo : BotDecisionContext -> Maybe String
homeStationToGoTo context =
    case context.eventContext.botSettings.homeStationName of
        Nothing ->
            Nothing

        Just stationName ->
            if
                (context.memory.droneBayEmptyLastSeen == Just True)
                    && not context.memory.droneBayWillTakeNoMore
            then
                Just stationName

            else
                Nothing


{-| Which station the info panel says we are docked at, or Nothing when this
reading does not say.

Read live rather than from `lastDockedStationNameFromInfoPanel`, which is a
*last seen* and would happily name the previous station while docked at this
one -- and answering "yes, we are home" about the wrong station would restock in
the station that has no drones, which is the bug this whole feature is about.
`generalSetupInUserInterface` runs before the wind-down on every reading and
expands the location info panel, so the name is normally there.
-}
dockedStationNameFromInfoPanel : BotDecisionContext -> Maybe String
dockedStationNameFromInfoPanel context =
    context.readingFromGameClient.infoPanelContainer
        |> Maybe.andThen .infoPanelLocationInfo
        |> Maybe.andThen .expandedContent
        |> Maybe.andThen .currentStationName


{-| Whether the ship is docked at the home station, or Nothing when the reading
cannot say.

Three-valued on purpose. "I cannot tell" and "no" want opposite actions -- one
waits, the other undocks and flies away -- and collapsing them into a Bool means
picking one of those to do on no evidence.

The name is matched as an exact string, ignoring case and surrounding space, or
as the configured name appearing inside the panel's. Containment only in that
direction: the panel decorating the name with something extra should still
match, but a configured `Amarr` matching every station in the constellation
should not.
-}
dockedAtHomeStation : BotDecisionContext -> String -> Maybe Bool
dockedAtHomeStation context homeName =
    dockedStationNameFromInfoPanel context
        |> Maybe.map
            (\stationName ->
                let
                    normalise =
                        String.trim >> String.toLower
                in
                (normalise stationName == normalise homeName)
                    || stringContainsIgnoringCase (String.trim homeName) stationName
            )


{-| The overrun the wind-down allows itself while in space, in seconds past the
planned session end.
-}
windDownOverrunAllowanceSeconds : BotDecisionContext -> Int
windDownOverrunAllowanceSeconds context =
    case homeStationToGoTo context of
        Nothing ->
            secondsPastSessionEndBeforeGivingUpOnDocking

        Just _ ->
            homeStationTripSecondsPastSessionEnd


{-| The point at which a docked bot stops winding down and ends the session.

Normally the planned end itself. A ship that has reached its home station with
an empty bay gets `homeStationRestockGraceSeconds` past that, because arriving
and then finishing without restocking would waste the whole trip.
-}
dockedWindDownDeadlineSeconds : BotDecisionContext -> Int
dockedWindDownDeadlineSeconds context =
    if homeStationRestockGraceApplies context then
        -homeStationRestockGraceSeconds

    else
        0


{-| Whether the wind-down is being held open for a restock at the home station.
True only when there is a home station, the bay is known empty, and this is
that station -- so it can never extend a session that has nothing to gain by it.

It also stops being true the moment the restock latches `droneBayWillTakeNoMore`
(via `homeStationToGoTo`), so the grace ends on the restock's own verdict rather
than always running its full length. The clock is the backstop for the case
where no verdict arrives at all.
-}
homeStationRestockGraceApplies : BotDecisionContext -> Bool
homeStationRestockGraceApplies context =
    case homeStationToGoTo context of
        Nothing ->
            False

        Just stationName ->
            dockedAtHomeStation context stationName == Just True


{-| Why a docked bot is finishing, worded so the log alone says whether the trip
home succeeded, was never needed, or ran out of time.
-}
dockedWindDownFinishReason : BotDecisionContext -> String
dockedWindDownFinishReason context =
    case homeStationToGoTo context of
        Nothing ->
            "Session over and docked -- finish."

        Just stationName ->
            if dockedAtHomeStation context stationName == Just True then
                "Home station: docked at '"
                    ++ stationName
                    ++ "' with the restock grace spent -- finish here."

            else
                "Session over and docked -- finish. The drone bay is still empty and this is not '"
                    ++ stationName
                    ++ "'."


inSpaceWindDownFinishReason : BotDecisionContext -> Int -> String
inSpaceWindDownFinishReason context secondsRemaining =
    case homeStationToGoTo context of
        Nothing ->
            "Session ended "
                ++ String.fromInt -secondsRemaining
                ++ " seconds ago and I still have not docked -- stop here rather than keep trying."

        Just stationName ->
            "Home station: gave up -- the session ended "
                ++ String.fromInt -secondsRemaining
                ++ " seconds ago and I never reached '"
                ++ stationName
                ++ "'. Stopping here rather than flying on past the deadline."


{-| Head home while docked somewhere else: set the route first, undock second.

That order is the point. Setting a destination is the step that can fail -- the
station may not be in the search results, the results window may not open -- and
failing it while still docked costs nothing, where failing it after undocking
leaves the ship in space with the session ending. The search bar works from
inside a station, so nothing is gained by undocking first.

Returns Nothing when the ship is already home, which hands the reading to
`maintenanceWhileDocked` and its restock: "if already docked there, restock
without travelling".
-}
goToHomeStationWhileDocked : BotDecisionContext -> Maybe DecisionPathNode
goToHomeStationWhileDocked context =
    homeStationToGoTo context
        |> Maybe.andThen
            (\stationName ->
                case dockedAtHomeStation context stationName of
                    Just True ->
                        Nothing

                    Nothing ->
                        -- Not knowing where we are is a reason not to undock,
                        -- and no reason to skip the maintenance that was
                        -- happening here before this feature existed. Restocking
                        -- in the wrong station finds no drones and costs a few
                        -- readings; undocking towards a station we may already
                        -- be standing in costs the session.
                        Just
                            (describeBranch
                                ("Home station: the info panel does not name the station I am docked at, so I cannot tell whether it is '"
                                    ++ stationName
                                    ++ "' -- staying docked rather than undocking on a guess."
                                )
                                (maintenanceWhileDocked context
                                    |> Maybe.withDefault
                                        (describeBranch "Already docked. Stay put." waitForProgressInGame)
                                )
                            )

                    Just False ->
                        Just
                            (if homeStationRouteIsSet context stationName then
                                describeBranch
                                    ("Home station: the route to '"
                                        ++ stationName
                                        ++ "' is set -- undock and travel there."
                                    )
                                    (undockUsingStationWindow context)

                             else
                                describeBranch
                                    ("Home station: the drone bay is empty and this is not '"
                                        ++ stationName
                                        ++ "' -- set the route there before undocking."
                                    )
                                    (routeToStationByName context stationName)
                            )
            )


{-| Head home from space: set the route, then fly it gate by gate.

`jumpToNextSystem` is the same travel step the mission path uses, and it is what
docks at the far end too -- the route marker's own menu offers "Dock" once the
destination system is reached, which is why nothing here has to know the
difference between another jump and arrival.
-}
goToHomeStationWhileInSpace : BotDecisionContext -> Maybe DecisionPathNode
goToHomeStationWhileInSpace context =
    homeStationToGoTo context
        |> Maybe.map
            (\stationName ->
                travelToStationByName context
                    stationName
                    { whileSettingRoute =
                        "Home station: the drone bay is empty -- set the route to '"
                            ++ stationName
                            ++ "'."
                    , whileTravelling =
                        "Home station: travelling to '"
                            ++ stationName
                            ++ "' to restock the drone bay."
                    }
            )


{-| Set a route to a named station and fly it, gate by gate, until the route
marker's own menu offers "Dock" at the far end.

Split out of `goToHomeStationWhileInSpace` when #33's pod recovery needed the
same three steps for a different reason, so that there is one travel-and-dock
path in this bot rather than two that can drift apart. The caller supplies both
log lines because the *reason* differs and the decision log is where an operator
reads it -- "the drone bay is empty" and "the ship is gone" want completely
different words in front of the same mechanism.

`jumpToNextSystem` is what docks at the far end too, which is why nothing here
has to know the difference between another jump and arrival.

-}
travelToStationByName :
    BotDecisionContext
    -> String
    -> { whileSettingRoute : String, whileTravelling : String }
    -> DecisionPathNode
travelToStationByName context stationName describe =
    if homeStationRouteIsSet context stationName then
        case closeSearchResultsWhenRouteIsSet context of
            Just closeResults ->
                closeResults

            Nothing ->
                describeBranch describe.whileTravelling (jumpToNextSystem context)

    else
        describeBranch describe.whileSettingRoute (routeToStationByName context stationName)


{-| Whether the route currently set is *our* route home, rather than a leftover
from the mission the session was running.

The route panel says a destination exists; it does not say which one, and
nothing in a reading names it. Following the wrong route is not a visible
failure either -- the ship travels, docks, and the session ends in the wrong
station with every log line reading like success.

So the evidence is the window that set it: the `Station: Information` window for
the home station, which is what `routeToStationByName` clicks "Set Destination"
in and which nothing afterwards closes. Route panel plus that window is the
conjunction that only our own sequence produces.

**This is the seam an ESI backend replaces.** The travel-and-dock path below
asks route-setting exactly two questions -- "is the route mine" (here) and
"make it so" (`routeToStationByName`) -- and knows nothing else about how a
destination is originated. A backend that sets the destination by id answers the
first from its own result instead of from a window, and the undock, the jumps
and the dock are unchanged. That is not a swap anyone can make today, though:
`botlab_host` answers a `SetAutopilotDestinationRequest` (PR #23) but no bot can
issue one, because `OperateBotConfiguration` gives a decision no channel to the
volatile process at all -- only mouse, keys and scroll. Until that framework gap
is closed, the search bar is not an interim, it is the mechanism.
-}
homeStationRouteIsSet : BotDecisionContext -> String -> Bool
homeStationRouteIsSet context stationName =
    routeIsSet context
        && (stationInfoWindowForStation context stationName /= Nothing)



-- The ship is gone: recognising it, and getting the pod out


{-| How many consecutive in-space readings a ship UI with no module buttons at
all has to persist before it counts as a lost ship on its own.

Low, because of the asymmetry #33 is about: docking early costs the rest of the
session, and being wrong the other way costs the clone. Not one, because the
module row is not a stable index space -- `ParseUserInterface` drops any slot
whose display region it cannot read (see CLAUDE.md, "Ship modules"), so a single
reading finding none is a parse that may simply have missed, where three in a
row is the ship's shape having changed.

Three *readings*, not three decision lines -- the unit CLAUDE.md keeps a section
on, and the one `stall_watch.py` got wrong twice. This counter is stepped from
`updateMemoryForNewReadingFromGame`, which runs once per reading, so three of
them is roughly twenty-five seconds at the tick rate the recorded runs show
(run 57: 376 ticks in 3,025s).

-}
shipLossReadingsWithoutModulesBeforeVerdict : Int
shipLossReadingsWithoutModulesBeforeVerdict =
    3


{-| How many readings the pod recovery may run before the session ends anyway.

A pod that has been trying to reach a station for this long is not going to, and
an unbounded retry loop reads in the log exactly like a bot working -- issues #7
and #14 twice over. When it expires the session *ends*, naming the station the
pod never reached, so an operator finds out rather than discovering it later.

Calibrated in readings, at the eight seconds a reading the recorded runs
average -- so this is about twenty minutes of trying, against the roughly fifty
readings `homeStationTripSecondsPastSessionEnd` (420s) already budgets for the
same route, jumps and dock. Three times the headroom the trip that works needs.

-}
podRecoveryGiveUpReadings : Int
podRecoveryGiveUpReadings =
    150


{-| The client saying, in its own words, that the ship being flown cannot lock
anything -- which for this bot means the ship is gone and a capsule is in its
place.

**This is not a destruction announcement, and there is no such thing in this
client's log.** The whole of run 7's loss reads, in
`~/Documents/EVE/logs/Gamelogs`, as the last `(combat)` line at 04:26:59 and then
nothing until:

    [ 2026.08.03 04:27:33 ] (notify) The ship you are piloting does not have targeting systems installed.

repeated 173 times to the end of the run. Issue #33 expected EVE to state the
loss outright; it does not. What it states is the *consequence*, and only when
something asks the capsule to lock -- which this bot does on every reading it
sees a rat, so in the case that matters (a hostile pocket) the answer arrives
within a reading or two. It is silent for a pod drifting somewhere empty, which
is why it is not the only signal.

Two things make it usable anyway. It arrives on `(notify)`, which is carried:
the withheld channels are `(combat)` and `(bounty)`, and a destruction line, if
one existed, would almost certainly have been on `(combat)` and therefore
invisible to the bot. And it is the client asserting a fact about the hull rather
than the bot inferring one from a HUD sprite, which is what the hitpoint reading
of #32 turned out to be.

Matched on two substrings for #31's reason: the sentence has no variable part
today, but `targeting systems` alone would also match a rewording about a
*module*, and the pair pins the subject ("the ship you are piloting") to the
symptom.

`Nothing` and `Just []` are collapsed here, and that is safe only because of the
direction of the inference. Finding no such line is never read as the ship being
intact -- `shipUIHasNoModuleButtons` is the signal that works on a host carrying
no game log at all. Nothing anywhere may conclude "no loss was reported, so the
ship is fine", which is exactly the reading of an absent game log #30 built the
`Maybe` to prevent.

-}
shipLossFromGameLog : ReadingFromGameClient -> Maybe String
shipLossFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase "ship you are piloting" entry.text
                    && stringContainsIgnoringCase "does not have targeting systems" entry.text
            )
        |> List.head
        |> Maybe.map .text


{-| A ship UI that is showing, and carries no module buttons in any row.

The second signal, and the one that needs no game log. A capsule has no module
slots at all; every ship this bot is set up to fly has weapons in the top row and
hardeners in the middle, because its own setup instructions require them.

Run 7 logged `Middle-row modules: none.` on every one of its 724 in-space status
prints, across all 86 of its readings. Runs 1, 3, 5 and 8, all flying real ships,
logged it **zero** times between them -- 4,419 readings and 15,836 in-space
status prints, every one of which named a propulsion module. That is the
discrimination this rests on, and it is measured rather than assumed.

What is *inferred* rather than observed is the step from that row to this one.
The status line prints the middle row only, and the middle row is a subset of
`moduleButtons`, so a non-empty middle row proves `moduleButtons` was non-empty
on all 15,836 -- the direction that matters for false positives. The other
direction, a capsule having no module buttons in *any* row, follows from a
capsule having no slots to fit them in, and from run 7's own `ShipUI` text
carrying nothing behind its slots. If that turns out to be wrong on some client
the symptom is this signal never firing, and the game log's capsule refusal
carrying the whole load.

Note what is *not* used. The drones window disappearing was #33's third suggested
signal and it does not survive contact with the recordings: run 1 reported "No
drones" on 8,076 in-space readings while flying a perfectly good ship, so an
absent drones window says nothing about the hull. Nor are hitpoints used --
a capsule reads 100% shield and 100% armour, which is the reassuring-and-
meaningless line that made this failure invisible in the first place.

-}
shipUIHasNoModuleButtons : ReadingFromGameClient -> Bool
shipUIHasNoModuleButtons readingFromGameClient =
    case readingFromGameClient.shipUI of
        Nothing ->
            False

        Just shipUI ->
            List.isEmpty shipUI.moduleButtons


{-| The count of consecutive in-space readings whose ship UI carried no modules.

Reset by a reading that shows any module, and by docking -- a docked reading has
no ship UI at all and so is no evidence either way, and letting it count would
have every dock accumulate towards a verdict.

-}
shipUIWithoutModuleButtonsReadingsAfter : ReadingFromGameClient -> Int -> Int
shipUIWithoutModuleButtonsReadingsAfter readingFromGameClient countBefore =
    if shipUIHasNoModuleButtons readingFromGameClient then
        countBefore + 1

    else
        0


{-| The loss verdict for this reading: the one already latched, or a new one if
this reading is where it becomes clear.

Written from `updateMemoryForNewReadingFromGame` because it has to be. The game
log entries behind the first signal are gone by the next reading, so a branch
that read them and recorded nothing would see the loss once and then go back to
flying the mission -- which is precisely what #30's follow-up section warns
about, and the shape #31 already had to work around.

Latched: once set it is returned unchanged forever. See `ShipLossVerdict`.

-}
shipLossVerdictAfter :
    ReadingFromGameClient
    -> { withoutModulesReadings : Int, verdictBefore : Maybe ShipLossVerdict }
    -> Maybe ShipLossVerdict
shipLossVerdictAfter readingFromGameClient { withoutModulesReadings, verdictBefore } =
    case verdictBefore of
        Just latched ->
            Just { latched | readingsSince = latched.readingsSince + 1 }

        Nothing ->
            case shipLossFromGameLog readingFromGameClient of
                Just clientSentence ->
                    Just
                        { reason =
                            "the client said \""
                                ++ clientSentence
                                ++ "\", which only a capsule hears"
                        , readingsSince = 0
                        }

                Nothing ->
                    if shipLossReadingsWithoutModulesBeforeVerdict <= withoutModulesReadings then
                        Just
                            { reason =
                                "the ship UI has carried no modules at all for "
                                    ++ String.fromInt withoutModulesReadings
                                    ++ " readings, which is the shape of a capsule and not of any ship this bot flies"
                            , readingsSince = 0
                            }

                    else
                        Nothing


{-| Stop flying the mission and get the pod to a station, once the ship is gone.

Placed above the wind-down and above everything docked-or-in-space in
`missionBotDecisionRootBeforeApplyingSettings`, which is what makes "stop
fighting" structural rather than a list of things not to do: locking, module
activation, approach and looting all live below this branch and are simply never
reached. There is nothing aboard a capsule to fight with.

Four outcomes, and every one of them says in the decision log that the ship was
lost, because that is the one fact an operator has to be able to read back:

  - **Docked.** The pod is safe and the run is over. A ship loss is something the
    operator has to act on, and the session's remaining hours are worth nothing
    without a ship, so this ends the session rather than parking.
  - **In space with a `home-station`.** The same route-travel-dock path #16 built
    for the drone restock, via `travelToStationByName`.
  - **In space with no `home-station`.** `dockAtStation` off the surroundings
    menu, preferring the station last docked at. Weaker -- it can only reach a
    station in this system, and it says so -- but a pod docked anywhere beats a
    pod stationary in the pocket that just killed the ship.
  - **Out of time.** `podRecoveryGiveUpReadings` readings of trying, and the
    session ends saying so.

-}
recoverPodAfterShipLoss : BotDecisionContext -> Maybe DecisionPathNode
recoverPodAfterShipLoss context =
    context.memory.shipLoss
        |> Maybe.map
            (\shipLoss ->
                describeBranch
                    ("The ship is gone -- "
                        ++ shipLoss.reason
                        ++ ". Stop flying the mission and get the pod out ("
                        ++ String.fromInt shipLoss.readingsSince
                        ++ " readings since)."
                    )
                    (case context.readingFromGameClient.shipUI of
                        Nothing ->
                            describeBranch
                                ("The pod is docked at "
                                    ++ (dockedStationNameFromInfoPanel context
                                            |> Maybe.map (\name -> "'" ++ name ++ "'")
                                            |> Maybe.withDefault "a station"
                                       )
                                    ++ " and safe. Ending the session: there is no ship left to fly the mission with, and that is for the operator to fix."
                                )
                                (Common.DecisionPath.endDecisionPath FinishSession)

                        Just _ ->
                            if podRecoveryGiveUpReadings <= shipLoss.readingsSince then
                                describeBranch
                                    ("The pod has been trying to reach a station for "
                                        ++ String.fromInt shipLoss.readingsSince
                                        ++ " readings and has not got there. Ending the session in space rather than retrying forever -- the pod needs recovering by hand."
                                    )
                                    (Common.DecisionPath.endDecisionPath FinishSession)

                            else
                                case context.eventContext.botSettings.homeStationName of
                                    Just stationName ->
                                        travelToStationByName context
                                            stationName
                                            { whileSettingRoute =
                                                "Pod recovery: set the route to '"
                                                    ++ stationName
                                                    ++ "' before anything else."
                                            , whileTravelling =
                                                "Pod recovery: travelling to '"
                                                    ++ stationName
                                                    ++ "' to get the pod docked."
                                            }

                                    Nothing ->
                                        describeBranch
                                            ("Pod recovery: no 'home-station' is configured, so there is no station this pod can be routed to by name. Docking at whatever this system offers"
                                                ++ (context.memory.lastDockedStationNameFromInfoPanel
                                                        |> Maybe.map (\name -> ", preferring '" ++ name ++ "'")
                                                        |> Maybe.withDefault ""
                                                   )
                                                ++ " instead."
                                            )
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


{-| Work worth doing while parked in station, or Nothing to just sit there.

Called only from the wind-down branch, which is the one stretch where the bot is
docked and has already decided not to start another leg -- roughly 200 seconds
per session with the clock running out. Anything here is therefore free: it
cannot delay a mission, because there is no mission left to delay. That is also
the constraint. A maintenance task must be interruptible and must finish or give
up inside that window, and must never be placed anywhere the bot still has work
to do.

Each task states its own "already done" condition, because this branch is
re-entered on every reading for the whole window. A task that cannot tell it has
run would repeat for the rest of the session, which is both useless and exactly
the shape `stall_watch` calls a stall.

The order below never starves either task: the restock stops with
`droneRestockGiveUpSecondsBeforeSessionEnd` on the clock and the survey only
starts inside `agentSurveyWindowSeconds`, so their windows do not overlap.
-}
maintenanceWhileDocked : BotDecisionContext -> Maybe DecisionPathNode
maintenanceWhileDocked context =
    [ restockDroneBayWhileDocked context
    , surveyAgentsInStation context
    ]
        |> List.filterMap identity
        |> List.head


{-| Log every agent this station's panel knows about, once per session.

The point is finding agents worth moving to. The panel is not limited to agents
based here -- `agentLocation` carries a remote agent's system and jump count --
so this is a genuine survey of what is reachable, not just a list of the room
we are standing in. It reads what the parser already produces, so it needs no
new UI work; the Agency window, which reaches further than any one station's
panel, is the obvious next task to add here.

Reading only. It selects the Agents tab if that is needed to see the list, and
otherwise clicks nothing -- there is no mission running to disturb, but there is
also no reason to leave the client in a different state than we found it.
-}
surveyAgentsInStation : BotDecisionContext -> Maybe DecisionPathNode
surveyAgentsInStation context =
    -- Gated on the session clock, not on bot memory. The memory counter this
    -- used to rely on was consumed before the window ever opened: the bot docks
    -- to hand its last mission in, the Agents tab is up and populated for that
    -- whole conversation, and it then stays docked into wind-down without ever
    -- undocking -- so the reset never fired. Run 119 parked for 403 readings
    -- and printed nothing.
    --
    -- `UpdateMemoryContext` cannot see the session clock, but the decision can,
    -- so the window is defined here instead: the opening seconds of wind-down.
    -- That is self-limiting without any stored state, at the cost of repeating
    -- for those few readings rather than printing exactly once, and of missing
    -- the session entirely if the ship has not finished docking by then.
    if not (withinAgentSurveyWindow context) then
        Nothing

    else
        case context.readingFromGameClient.stationWindow of
            Nothing ->
                Nothing

            Just stationWindow ->
                case stationWindow.agentsTab of
                    Nothing ->
                        Nothing

                    Just agentsTab ->
                        if not agentsTab.isSelected then
                            Just
                                (describeBranch
                                    "Maintenance: open the station's Agents tab to survey them."
                                    (clickUiElement agentsTab.uiNode)
                                )

                        else if List.isEmpty stationWindow.agentEntries then
                            Nothing

                        else
                            Just
                                (describeBranch
                                    ("Maintenance: agents this station lists -- "
                                        ++ (stationWindow.agentEntries
                                                |> List.map describeStationAgentEntry
                                                |> String.join " | "
                                           )
                                    )
                                    waitForProgressInGame
                                )


{-| The last seconds before the session ends, which is when the survey runs.

At the *start* of wind-down the ship is still flying home -- run 120 spent that
stretch on "Head for a station and dock" and did not park until 144 of its 200
seconds were gone, so a window at that end was evaluated only while there was no
station window to read. The end of the clock is the one moment the ship is
reliably parked, because getting there is what wind-down is for.

Still nothing stored: the session clock alone decides, so there is no counter to
be consumed early and no dependence on whether the memory update runs before or
after the decision.
-}
withinAgentSurveyWindow : BotDecisionContext -> Bool
withinAgentSurveyWindow context =
    case secondsToSessionEnd context.eventContext of
        Nothing ->
            False

        Just secondsRemaining ->
            (0 < secondsRemaining) && (secondsRemaining <= agentSurveyWindowSeconds)


{-| How long the survey keeps printing. Readings come about twice a second, so
this is roughly twenty repeated lines -- under stall_watch's threshold of 40,
and the price of needing no stored state to stop. Wide enough that a slow tick
cannot step over the window entirely.
-}
agentSurveyWindowSeconds : Int
agentSurveyWindowSeconds =
    10


describeStationAgentEntry : EveOnline.ParseUserInterface.StationAgentEntry -> String
describeStationAgentEntry agentEntry =
    [ agentEntry.name |> Maybe.withDefault "(unnamed)"
    , agentEntry.agentType |> Maybe.withDefault "(type?)"
    , case agentEntry.agentLocation of
        Nothing ->
            "here"

        Just location ->
            if String.trim location |> String.isEmpty then
                "here"

            else
                String.trim location
    , if agentEntry.isAvailable then
        "available"

      else
        "not available"
    ]
        |> String.join ", "


{-| Refill the drone bay from this station's item hangar.

A port of `tools/macos-host/reload_drones.py`, which does this reliably but
drives the real mouse from outside the bot, so it can never run while a session
is up -- which is exactly when the bay runs dry. A run that loses its drones
ends with an empty bay, and the next run then starts empty too.

Every step is one of that tool's, and each of those earned its place by failing
without it:

  * **The bay is opened from the ship's own card in the Hangars/Ships panel**,
    never with Alt+C. The inventory an Alt+C opens looks identical in the UI
    tree and *silently refuses the drop*: the quantity dialog still appears and
    the items stay in the hangar, as if it had worked. No single reading tells
    the two apart, so the one moment that is evidence our own "Open Drone Bay"
    click landed -- the ship's drone bay showing as the selected container --
    is kept in memory until the ship undocks (`droneBayOpenedFromShipCard`).
  * **Widgets are found by type, not by text near them.** The card is a
    `ShipItemCard` and the filter box is the parser's `quickFilterInputBox`.
    Aiming at a fixed offset from a nearby label missed the card entirely, and
    searching for "Search" hit unrelated tabs -- three bugs in one session of
    the tool had that shape. The Hangars/Ships tabs are the one thing still
    found by text, and then only as an exact label on an `EveLabelMedium`.
  * **The quick filter is cleared before it is typed into**, or the previous
    text is appended, "Acolyte IAcolyte I" matches nothing, and that looks
    exactly like the typing having failed. `ensureQuickFilterText` is the same
    clear-then-type the courier load uses.
  * **The drag starts on the item's icon, not its label** -- the `InvItem` box
    covers both -- and it is a drag at all only because
    `EffectOnWindow.effectsForDragAndDrop` moves the pointer straight after the
    press, with `botlab_host` suppressing the framework's inter-effect wait
    while a button is held. Press, pause, then move reads as a click.
  * **The quantity dialog's default already fills the bay**, so it is accepted
    rather than typed into.

The tool also clicks empty viewport first, because closing windows leaves EVE
frontmost with nothing holding keyboard focus and no key then lands. The bot
does not need that step: every string it types is preceded, inside the same
effect sequence, by a click on the field being typed into -- which is what the
courier load does, and run 117 filtered, found and dragged in about six
readings that way.

Ordered by what a reading can *see*, the way `loadCourierCargo` is: which
container the inventory has selected decides the next step, so the sequence
converges without the bot having to remember where in it we are.

**What ends it is a look into the bay, and nothing else.** Docked, the drones
window does not exist, so the bay's contents are only readable as the selected
container of an inventory window -- which means they are only readable at the
two moments the sequence deliberately puts the bay there, before the first drag
and after each one. That is the whole of the fix for issue #15: the check that
used to sit here read the drones window, which is `Nothing` for every reading
this task ever sees, and so the task never ran once.

Looking after the drag rather than before it is what distinguishes a restock
from a refusal, and the refusal is real: the client answers a drop it will not
take with a "No room for more in destination container" window that carries an
OK button of its own (issue #19). Nothing else in the reading separates the two.

**Telling from the log whether it worked**: `Maintenance: drag ... (attempt 1)`
followed by one `select the ship's drone bay ... (look 2 of 3)` and then
silence is a restock that landed -- the bay was seen holding drones and the
task retired. A second attempt means the first look found nothing. The log
falling silent right after `look 3 of 3` is the give-up, and the drones window
after the session is still the last word on what is actually in there.

Every branch here also names what it saw rather than only what it wanted,
because the node type names it steers by (`ShipDroneBay`, `StationItems`) are
this client build's, and a name that is wrong on some future build would
otherwise look exactly like a slow client.
-}
restockDroneBayWhileDocked : BotDecisionContext -> Maybe DecisionPathNode
restockDroneBayWhileDocked context =
    if not (withinDroneRestockWindow context) then
        Nothing

    else if
        (0 < context.memory.droneRestockDragsDispatched)
            && dropIntoDroneBayWasRefused context.readingFromGameClient
    then
        -- Ahead of the "already done" check below, which the same reading has
        -- just latched: the dialog is ours and is dismissed rather than left
        -- sitting over the client for the rest of the session.
        Just (dismissRefusedDropIntoDroneBay context)

    else if context.memory.droneBayWillTakeNoMore then
        -- The "already done" condition, in the only two forms a docked reading
        -- can supply: the bay's own capacity gauge reading full, or the client
        -- having refused a drop into it.
        --
        -- Read from the bay, not from the drones window. That window does not
        -- exist while docked, which is the only state this task runs in, so
        -- the check that used to live here answered "not empty" on every
        -- reading and made the whole task unreachable -- issue #15. Nothing in
        -- a docked reading can be consulted before the bay is opened, so the
        -- first look happens after opening it and costs the readings that
        -- takes.
        Nothing

    else if droneRestockLooksBeforeGivingUp <= context.memory.droneRestockLooksWithRoom then
        -- Out of attempts, and deliberately silent from here. The alternative
        -- is a give-up line repeating for the rest of the window, and
        -- `stall_watch` counts readings rather than distinct lines, so that
        -- reads as a stall. Where this stopped is the last
        -- "look ... of N" line in the log.
        Nothing

    else if not context.memory.droneBayOpenedFromShipCard then
        Just (openDroneBayFromShipCard context)

    else
        case inventoryWindowShowingDroneBay context.readingFromGameClient of
            Nothing ->
                -- The bay was open a moment ago, since that is what set the
                -- memory flag, so this is the window having been closed since.
                Just (openDroneBayFromShipCard context)

            Just inventoryWindow ->
                Just
                    (restockDroneBayFromInventoryWindow
                        context
                        inventoryWindow.window
                        inventoryWindow.droneBayTreeEntry
                        context.eventContext.botSettings.droneTypeName
                    )


{-| The steps that run once the ship's drone bay has been opened from its card.

Each branch changes something the next reading can see. The station hangar has
to be the selected container before anything is dragged out of it, so a
reading that shows anything else selected only ever clicks the item hangar --
otherwise a filter typed against the ship's own cargo would come back empty and
be reported as "the station has no drones", which is a wrong answer rather than
a missing one.

The bay is looked at before and after every drag, and that is the only thing
that ever ends this task. The two counters say which of those the current
reading is for, because the station hangar stays selected across a drag and so
a reading cannot tell "about to drag" from "just dragged": one look precedes
each drag, so `dragsDispatched == looksWithRoom` means the drag for this round
has gone out and the bay is due another look, while one fewer means the drag
has not happened yet.

Looking after the drag is the point. A drop can be refused -- the client puts
up "No room for more in destination container", which carries an OK button of
its own (issue #19) -- and a refusal is indistinguishable from success in
everything except the bay's own gauge.

The look budget only bounds the paths that reach a drag. The dead ends below --
this station's hangar holding none of the drone, no item hangar in the
inventory at all -- still repeat their line until the clock closes the window,
because no drag ever happens to advance the count and nothing in a reading
distinguishes "filtered and found nothing" from "the container has not
rendered yet" well enough to latch on. They dispatch no input, and wind-down
repeats a line either way -- "Already docked. Stay put." is what fills that
window otherwise -- so this costs a differently-worded log and nothing else.
-}
restockDroneBayFromInventoryWindow :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    -> String
    -> DecisionPathNode
restockDroneBayFromInventoryWindow context inventoryWindow droneBayTreeEntry droneTypeName =
    let
        itemsInView =
            inventoryItemsInView inventoryWindow

        -- The first word, not the whole name: the same match
        -- `reload_drones.py` makes. An item cell renders the name with its
        -- quantity and can truncate it, so "Acolyte" survives a rendering that
        -- "Acolyte I" does not, and the quick filter has already narrowed the
        -- hangar to this drone anyway.
        droneNameNeedle =
            droneTypeName |> String.words |> List.head |> Maybe.withDefault droneTypeName

        matchingItem =
            itemsInView
                |> List.filter
                    (\itemNode ->
                        itemNode.uiNode
                            |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                            |> List.any (stringContainsIgnoringCase droneNameNeedle)
                    )
                |> List.head

        itemHangarTreeEntry =
            inventoryWindow |> inventoryTreeEntryWithText "item hangar"

        selectedContainerTypeName =
            selectedContainerTypeNameOfWindow inventoryWindow

        looksWithRoom =
            context.memory.droneRestockLooksWithRoom

        dragsDispatched =
            context.memory.droneRestockDragsDispatched
    in
    case okButtonInReading context.readingFromGameClient of
        -- Only reached once `restockDroneBayWhileDocked` has ruled out the
        -- refusal dialog, which carries an OK of its own that this cannot
        -- tell apart -- see `okButtonInReading`.
        Just acceptButton ->
            describeBranch
                "Maintenance: accept the quantity dialog, whose default already fills the drone bay."
                (clickUiElement acceptButton)

        Nothing ->
            if selectedContainerTypeName /= Just "ShipDroneBay" && looksWithRoom <= dragsDispatched then
                -- The drag for this round has gone out and the bay has not
                -- been looked at since. Nothing else in the reading says
                -- whether it landed, so go and look before dragging again.
                if previousStepClickedMouse context then
                    describeBranch
                        "Maintenance: I just clicked -- wait for the reading to catch up before deciding on the inventory again."
                        waitForProgressInGame

                else
                    describeBranch
                        ("Maintenance: dragged "
                            ++ String.fromInt dragsDispatched
                            ++ " time(s) -- select the ship's drone bay to read its capacity gauge (look "
                            ++ String.fromInt (looksWithRoom + 1)
                            ++ " of "
                            ++ String.fromInt droneRestockLooksBeforeGivingUp
                            ++ "; the log goes quiet here if it is the last one and the bay still has room)."
                        )
                        (clickUiElement (droneBayTreeEntry.selectRegion |> Maybe.withDefault droneBayTreeEntry.uiNode))

            else if selectedContainerTypeName /= Just "StationItems" then
                case itemHangarTreeEntry of
                    Nothing ->
                        describeBranch
                            "Maintenance: the inventory shows no item hangar to take drones out of -- give up on restocking."
                            waitForProgressInGame

                    Just itemHangar ->
                        if previousStepClickedMouse context then
                            describeBranch
                                "Maintenance: I just clicked -- wait for the reading to catch up before deciding on the inventory again."
                                waitForProgressInGame

                        else
                            describeBranch
                                ("Maintenance: select the station's item hangar (the inventory shows "
                                    ++ (selectedContainerTypeName |> Maybe.withDefault "nothing")
                                    ++ (case droneBayFillWhileSelected context.readingFromGameClient of
                                            -- The outcome of a look, printed
                                            -- where the look happens: the bay
                                            -- being selected here is the bot
                                            -- having just read its gauge and
                                            -- decided to go and fetch drones.
                                            Just fill ->
                                                ", with " ++ describeDroneBayFill fill

                                            Nothing ->
                                                ""
                                       )
                                    ++ ")."
                                )
                                (clickUiElement (itemHangar.selectRegion |> Maybe.withDefault itemHangar.uiNode))

            else
                case ensureQuickFilterText context inventoryWindow droneTypeName of
                    Just filterStep ->
                        filterStep

                    Nothing ->
                        case matchingItem of
                            Just itemNode ->
                                if previousStepClickedMouse context then
                                    -- A repeat drag is not harmless: it can
                                    -- move part of a stack somewhere
                                    -- unintended while the first drag is still
                                    -- catching up. Same wait the courier load
                                    -- takes.
                                    describeBranch
                                        "Maintenance: I just dragged -- wait for the reading to catch up before dragging again."
                                        waitForProgressInGame

                                else
                                    describeBranch
                                        ("Maintenance: drag '"
                                            ++ droneTypeName
                                            ++ "' from the item hangar into the ship's drone bay (attempt "
                                            ++ String.fromInt (dragsDispatched + 1)
                                            ++ ")."
                                        )
                                        (dragFromItemIconOntoUiElement itemNode
                                            (droneBayTreeEntry.selectRegion
                                                |> Maybe.withDefault droneBayTreeEntry.uiNode
                                            )
                                        )

                            Nothing ->
                                -- With the count in it, "the hangar has none"
                                -- can be told from "nothing is being read out
                                -- of this container at all", which look the
                                -- same from a bare sentence and want opposite
                                -- fixes.
                                describeBranch
                                    ("Maintenance: this station's item hangar holds no '"
                                        ++ droneTypeName
                                        ++ "' -- nothing to restock the drone bay with ("
                                        ++ String.fromInt (List.length itemsInView)
                                        ++ " item(s) in view under the filter)."
                                    )
                                    waitForProgressInGame


{-| Clear the dialog the client puts up when it will not take a drop, and say
so in the log.

The restock is already over by the time this runs -- the same reading latches
`droneBayWillTakeNoMore`, because a refusal is the client's own answer to
"will more fit", and a better one than the gauge. This exists so the dialog
does not sit over the client until it times out, and so the log carries the
refusal in its own words rather than as an accepted quantity dialog, which is
what it used to be reported as.
-}
dismissRefusedDropIntoDroneBay : BotDecisionContext -> DecisionPathNode
dismissRefusedDropIntoDroneBay context =
    if previousStepClickedMouse context then
        describeBranch
            "Maintenance: I just clicked -- wait for the reading to catch up before deciding on the dialog again."
            waitForProgressInGame

    else
        case okButtonInReading context.readingFromGameClient of
            Just okButton ->
                describeBranch
                    ("Maintenance: the client refused the drop -- '"
                        ++ dropRefusedDialogText
                        ++ " in destination container'. The drone bay will take no more, so dismiss this and stop restocking."
                    )
                    (clickUiElement okButton)

            Nothing ->
                describeBranch
                    ("Maintenance: the client refused the drop -- '"
                        ++ dropRefusedDialogText
                        ++ " in destination container' -- and shows no OK to dismiss it with. It closes itself; stop restocking either way."
                    )
                    waitForProgressInGame


{-| Right-click the ship's card and choose "Open Drone Bay".

The cards only exist while the station panel is showing them, so a reading
without one is answered by opening the tab that has them rather than by giving
up. `reload_drones.py` clicks "Hangars" and then "Ships" for the same reason;
here each click is one reading, and the next reading decides again from what it
sees.

The entry is matched on its whole text, and that is not a detail to relax: the
same menu carries "Open Cargohold" directly above it (all 14 entries were read
off a live client, issue #19), and a looser match lands on a container that
looks the same in the tree and silently takes the drop nowhere useful.

The first card is taken, which is what the tool does. The active ship is the
one card the panel shows under "Active", and nothing read so far distinguishes
the cards from each other -- so this is worth watching on a character with
several ships in the same hangar.
-}
openDroneBayFromShipCard : BotDecisionContext -> DecisionPathNode
openDroneBayFromShipCard context =
    case context.readingFromGameClient.shipItemCards |> List.head of
        Just shipCard ->
            describeBranch
                ("Maintenance: the drone bay is empty -- open it from the ship's own card ("
                    ++ (shipCard.mainText |> Maybe.withDefault "unnamed ship")
                    ++ "), the only place a drop into it is accepted. Inventory shows: "
                    -- What the inventory has selected, so that this step
                    -- repeating is diagnosable from the log rather than only
                    -- visible as repetition. The bay counting as open is the
                    -- container reading `ShipDroneBay`; if these lines keep
                    -- naming something else after the menu entry was clicked,
                    -- that is the name to check against the client, not a
                    -- click that did not land.
                    ++ describeSelectedContainers context.readingFromGameClient
                    ++ "."
                )
                (useContextMenuCascade
                    ( "ship card", shipCard.uiNode )
                    (useMenuEntryWithTextContaining "Open Drone Bay" menuCascadeCompleted)
                    context
                )

        Nothing ->
            case shipHangarTabToOpen context.readingFromGameClient of
                Just ( tabName, tabNode ) ->
                    if previousStepClickedMouse context then
                        describeBranch
                            "Maintenance: I just clicked a hangar tab -- wait for the reading to catch up."
                            waitForProgressInGame

                    else
                        describeBranch
                            ("Maintenance: no ship card in this reading -- open the '"
                                ++ tabName
                                ++ "' tab, which is where the cards are."
                            )
                            (clickUiElement tabNode)

                Nothing ->
                    describeBranch
                        "Maintenance: no ship card and no Hangars/Ships tab to reveal one -- give up on restocking the drone bay."
                        waitForProgressInGame


{-| The tab to click to bring the ship cards into view: "Ships" if the panel is
already showing that far, otherwise "Hangars" to get to it.
-}
shipHangarTabToOpen : ReadingFromGameClient -> Maybe ( String, EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion )
shipHangarTabToOpen readingFromGameClient =
    [ "Ships", "Hangars" ]
        |> List.filterMap
            (\tabName ->
                readingFromGameClient
                    |> widestNodeLabelledExactly { label = tabName, pythonObjectTypeName = Just "EveLabelMedium" }
                    |> Maybe.map (\node -> ( tabName, node ))
            )
        |> List.head


{-| How long before the session ends the restock stops trying.

The window is the wind-down branch itself -- docked, roughly 200 seconds on the
clock -- which at ~5.7s a reading is around 30 readings for a handful of steps.
This is the far end of it: enough left for the agent survey, and a bound that
needs no stored state, the same reason `withinAgentSurveyWindow` is written
against the clock.

It is the backstop, not the bound that matters. ~30 readings is *over*
`stall_watch`'s `CIRCLING_THRESHOLD` of 20, so a failure that repeats one
decision for the whole window does alarm -- what this originally claimed it
prevented. `droneRestockLooksBeforeGivingUp` is the bound that
actually stops the task, and it stops it by falling silent rather than by
repeating a give-up line.
-}
droneRestockGiveUpSecondsBeforeSessionEnd : Int
droneRestockGiveUpSecondsBeforeSessionEnd =
    30


{-| How many times the bot reads a drone bay that still has room before it
stops trying to fill it.

Counted in looks rather than in drags because a look is the only observation
that ends this task either way, and every drag is bracketed by two of them: the
sequence is look, drag, look, drag, look. Three therefore allows two drags and
still spends its last look confirming the second one, so a drop that was
refused -- which is indistinguishable from success everywhere except in the
bay's gauge (issue #19) -- costs two attempts rather than the whole window.

A look that cannot read the gauge counts too. It has to: the alternative is
looking forever at a bay whose capacity text this build renders differently,
and that is the shape of the bug this whole change exists to fix.

Bound in stored state, not on the clock, because the thing being bounded is a
drag: it moves items, and a repeat can split a stack while the first drag is
still catching up. The memory-counter trap `surveyAgentsInStation` documents
does not apply -- this counter only starts once our own "Open Drone Bay" has
landed, and nothing else in the bot ever selects that container.
-}
droneRestockLooksBeforeGivingUp : Int
droneRestockLooksBeforeGivingUp =
    3


withinDroneRestockWindow : BotDecisionContext -> Bool
withinDroneRestockWindow context =
    case secondsToSessionEnd context.eventContext of
        Nothing ->
            False

        Just secondsRemaining ->
            if homeStationRestockGraceApplies context then
                -- A ship that flew home for this arrives late by design, and
                -- the ordinary window has closed by then. The grace is the same
                -- bound the docked wind-down uses, so the restock and the
                -- session end together rather than one outliving the other.
                -homeStationRestockGraceSeconds < secondsRemaining

            else
                droneRestockGiveUpSecondsBeforeSessionEnd < secondsRemaining


{-| What a look into the ship's drone bay says about whether more will fit.
-}
type DroneBayFill
    = DroneBayFull
    | DroneBayHasRoom
    | DroneBayFillUnreadable


{-| Read the bay's fill state off its capacity gauge.

**Fullness, not emptiness.** The condition this answers is the restock's
"already done", and "holds something" is too weak for that -- a bay holding one
drone of ten reads as stocked and never gets topped up. The gauge is the only
thing in a reading that can tell the difference, and it is the same ground
truth `reload_drones.py` settled on.

The gauge itself is not a guess: `reload_drones.py` reads `50.0/50.0 m³` off
`InvContCapacityGauge` on this client build with the bay selected, and an
unlimited container such as the station hangar is exactly the case that reports
no maximum. This bot has the stronger handle of the two, since the parser names
the selected container (`ShipDroneBay`) where the tool had to infer it.

The two ways it declines to answer are both `Unreadable`: the gauge node
missing or unparsable, and `maximum` absent, which
`parseInventoryCapacityGaugeText` leaves `Nothing` unless the text carries a
`used / maximum` slash. Unreadable is treated as "act anyway" by the caller,
not as "already done" -- reading it the other way is precisely the mistake
issue #15 was: a condition that cannot see the bay must not conclude the work
is finished, or the task is dead in the state it exists for.

`maximum <= used` is the honest limit of this test, not a full one. The gauge
is in cubic metres truncated to an integer, and a drone's own volume is not
readable, so a bay with 1 m³ free reads as having room while a 5 m³ drone will
not fit. That case is what the refusal dialog and the bounded attempt count are
for.
-}
droneBayFillFromCapacityGauge : Maybe EveOnline.ParseUserInterface.InventoryWindowCapacityGauge -> DroneBayFill
droneBayFillFromCapacityGauge capacityGauge =
    case capacityGauge |> Maybe.andThen (\gauge -> gauge.maximum |> Maybe.map (Tuple.pair gauge.used)) of
        Nothing ->
            DroneBayFillUnreadable

        Just ( used, maximum ) ->
            if maximum <= used then
                DroneBayFull

            else
                DroneBayHasRoom


{-| The bay's fill state as an inventory window is showing it, or Nothing if no
window has the ship's drone bay selected -- which is not the same as the gauge
declining to answer.

Readable only while the bay *is* the selected container: the capacity gauge
belongs to whatever is selected, and the restock has to select the station
hangar to reach the drones. So the bay is looked at deliberately, at the
moments the sequence puts it there, and the verdict is latched into memory
rather than re-read when the drag comes around.
-}
droneBayFillWhileSelected : ReadingFromGameClient -> Maybe DroneBayFill
droneBayFillWhileSelected readingFromGameClient =
    readingFromGameClient.inventoryWindows
        |> List.filter (selectedContainerTypeNameOfWindow >> (==) (Just "ShipDroneBay"))
        |> List.head
        |> Maybe.map
            (.selectedContainerCapacityGauge
                >> Maybe.andThen Result.toMaybe
                >> droneBayFillFromCapacityGauge
            )


describeDroneBayFill : DroneBayFill -> String
describeDroneBayFill fill =
    case fill of
        DroneBayFull ->
            "full"

        DroneBayHasRoom ->
            "room for more"

        DroneBayFillUnreadable ->
            "a capacity gauge that does not say"


{-| Whether the drones window shows nothing at all in the ship's bay, or
Nothing when there is no drones window to ask.

**A second instrument, not a second opinion.** `droneBayFillWhileSelected`
above is the docked one: it reads the inventory's capacity gauge, and it is
only readable once the bot has deliberately opened the bay from the ship's
card. This is the in-space one, and the two never overlap -- the drones window
is absent while docked, and the inventory does not have the bay selected while
in space.

That is why both exist. The restock asks "will more fit" at a moment it has
itself arranged; the home trip asks "is it worth flying home" *before*
undocking, where nothing has opened the bay and nothing can, since the answer
is needed to decide whether to leave at all.

**Emptiness, not fullness, and that is forced rather than chosen.** The
drones window titles its bay group with a bare count on this build -- the
`(current/maximum)` form `parseQuantityFromDroneGroupTitleText` can read is
what the *in space* group carries, since that one is bandwidth-limited. With
no maximum there is no fullness to compute, so "nothing in the bay" is the
strongest thing an in-space reading can say. It is also the right threshold
for a trip: see `homeStationToGoTo`.

A bay with nothing in it may render no group at all, so a missing group counts
as empty, as does a group whose title carries no number. Both are the state
this feature exists for, and the cost of being wrong is a trip home to a bay
that turns out to have drones -- where the restock's own gauge then retires
the task on arrival.
-}
droneBayIsEmptyFromDronesWindow : ReadingFromGameClient -> Maybe Bool
droneBayIsEmptyFromDronesWindow readingFromGameClient =
    readingFromGameClient.dronesWindow
        |> Maybe.map
            (\dronesWindow ->
                case dronesWindow.droneGroupInBay of
                    Nothing ->
                        True

                    Just droneGroupInBay ->
                        (droneGroupInBay.header.quantityFromTitle
                            |> Maybe.map .current
                            |> Maybe.withDefault 0
                        )
                            < 1
            )


{-| The items an inventory window is currently rendering, whichever of the two
views it is in. Only the rendered ones: the list is virtualised at roughly 40
rows, so a count from here is a signal and never a total.
-}
inventoryItemsInView :
    EveOnline.ParseUserInterface.InventoryWindow
    -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
inventoryItemsInView inventoryWindow =
    case inventoryWindow.selectedContainerInventory |> Maybe.andThen .itemsView of
        Just (EveOnline.ParseUserInterface.InventoryItemsListView listView) ->
            listView.items |> List.map .uiNode

        Just (EveOnline.ParseUserInterface.InventoryItemsNotListView notListView) ->
            notListView.items

        Nothing ->
            []


{-| Whether the ship's own drone bay is the container an inventory window is
showing. The only evidence a reading carries that our "Open Drone Bay" on the
ship's card landed, since the bot selects that container nowhere else.
-}
droneBayIsSelectedContainer : ReadingFromGameClient -> Bool
droneBayIsSelectedContainer readingFromGameClient =
    selectedContainerTypeNames readingFromGameClient
        |> List.member "ShipDroneBay"


selectedContainerTypeNameOfWindow : EveOnline.ParseUserInterface.InventoryWindow -> Maybe String
selectedContainerTypeNameOfWindow inventoryWindow =
    inventoryWindow.selectedContainerInventory
        |> Maybe.map (.uiNode >> .uiNode >> .pythonObjectTypeName)


selectedContainerTypeNames : ReadingFromGameClient -> List String
selectedContainerTypeNames readingFromGameClient =
    readingFromGameClient.inventoryWindows
        |> List.filterMap selectedContainerTypeNameOfWindow


{-| What every open inventory window currently has selected, for the decision
log. The restock steers by these type names, so a step that repeats says which
name it is waiting for rather than leaving the operator to guess whether a
click failed to land or a name is wrong for this client build.
-}
describeSelectedContainers : ReadingFromGameClient -> String
describeSelectedContainers readingFromGameClient =
    case selectedContainerTypeNames readingFromGameClient of
        [] ->
            "no container selected in any inventory window"

        typeNames ->
            typeNames |> String.join ", "


{-| The inventory window to do the restock in: one that lists a drone bay at
all, preferring a window anchored to the active ship if the client opened a
separate one. Which of those happens is not known from a reading yet -- the
same client reuses the one window when a wreck is opened -- so this covers
both rather than assuming.

The drone bay's own sidebar row comes back with the window rather than being
looked up again inside the sequence. It is the drop target and the row the bot
clicks to look into the bay, and finding it here is what makes it present by
construction -- the version this replaces re-derived it and carried a
"no drone bay to drop it into" branch that this same filter had already made
unreachable.
-}
inventoryWindowShowingDroneBay :
    ReadingFromGameClient
    ->
        Maybe
            { window : EveOnline.ParseUserInterface.InventoryWindow
            , droneBayTreeEntry : EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
            }
inventoryWindowShowingDroneBay readingFromGameClient =
    let
        windowsShowingDroneBay =
            readingFromGameClient.inventoryWindows
                |> List.filterMap
                    (\window ->
                        window
                            |> inventoryTreeEntryWithText "drone bay"
                            |> Maybe.map
                                (\treeEntry -> { window = window, droneBayTreeEntry = treeEntry })
                    )
    in
    [ windowsShowingDroneBay
        |> List.filter (.window >> .uiNode >> .uiNode >> .pythonObjectTypeName >> (==) "ActiveShipCargo")
    , windowsShowingDroneBay
    ]
        |> List.concat
        |> List.head


{-| A row in the inventory's sidebar, found anywhere in that tree rather than
only among its roots -- the ship's own holds ("Drone Bay", and a wreck opened
mid-mission) hang off the ship's entry rather than sitting beside it.
-}
inventoryTreeEntryWithText :
    String
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
inventoryTreeEntryWithText text inventoryWindow =
    inventoryWindow.leftTreeEntries
        |> List.concatMap flattenInventoryTreeEntry
        |> List.filter (.text >> stringContainsIgnoringCase text)
        |> List.head


flattenInventoryTreeEntry :
    EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    -> List EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
flattenInventoryTreeEntry entry =
    entry
        :: (entry.children
                |> List.map EveOnline.ParseUserInterface.unwrapInventoryWindowLeftTreeEntryChild
                |> List.concatMap flattenInventoryTreeEntry
           )


{-| The one OK button on screen, whichever dialog it belongs to.

Not a `MessageBox`, so `closeMessageBox` does not reach it -- and it carries no
name of its own either, which leaves its label. `reload_drones.py` finds it the
same way.

**It cannot tell one dialog from another, and that mattered.** This used to be
called `quantityDialogAcceptButton` and was the first thing the restock checked
on every reading, so a refused drop -- which puts up its own dialog carrying
its own OK -- was clicked and logged as "accept the quantity dialog, whose
default already fills the drone bay". The action reported success and moved
nothing, which is the failure class this whole task was written to avoid
(issue #19). What separates the two dialogs is their text, so
`dropIntoDroneBayWasRefused` is asked first and this is only the button; the
name now says only what it can back up.
-}
okButtonInReading : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
okButtonInReading readingFromGameClient =
    [ "OK", "Ok" ]
        |> List.filterMap
            (\label ->
                readingFromGameClient
                    |> widestNodeLabelledExactly { label = label, pythonObjectTypeName = Nothing }
            )
        |> List.head


{-| Whether the client is showing its refusal of a drop into the drone bay.

Matched on the dialog's text, because that is the only thing separating it from
the quantity dialog that a successful drop raises -- both are windows with an
OK button, and `okButtonInReading` finds either. The wording was read off a live
client during a manual reload (issue #19): a `FormWnd` captioned "No room for
more in destination container", up for about four seconds before closing itself.

Only the stable half of that caption is matched, and against every text in the
reading rather than a scoped subtree. Scoping it would need a container this
dialog has been observed in, and one wrong guess there would answer "no refusal"
for a refusal plainly on screen -- the same reason `shipItemCards` is not scoped
to the panel that holds it.

A single live observation is all the evidence behind the wording. If the client
ever phrases it differently this reads as "not refused", which puts the restock
back on the bounded-attempts path rather than into a loop.
-}
dropIntoDroneBayWasRefused : ReadingFromGameClient -> Bool
dropIntoDroneBayWasRefused readingFromGameClient =
    readingFromGameClient.uiTree.uiNode
        |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
        |> List.any (stringContainsIgnoringCase dropRefusedDialogText)


dropRefusedDialogText : String
dropRefusedDialogText =
    "No room for more"


{-| The widest node whose first visible text is exactly this label.

`reload_drones.py`'s `labelled`, ported: exact rather than containing, so
"Ships" does not match "Ship Hangar", and widest so the click lands on the
clickable box around the text rather than on a nested fragment of it.

Blank texts are skipped and markup is stripped before comparing, the same two
things the tool's `texts_of` does. A label rendered as `<center>OK` is the same
label, and a node whose first text is empty would otherwise hide a real one
underneath it.
-}
widestNodeLabelledExactly :
    { label : String, pythonObjectTypeName : Maybe String }
    -> ReadingFromGameClient
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
widestNodeLabelledExactly config readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter
            (\node ->
                ((config.pythonObjectTypeName == Nothing)
                    || (config.pythonObjectTypeName == Just node.uiNode.pythonObjectTypeName)
                )
                    && (firstVisibleTextOfNode node == Just config.label)
            )
        |> List.sortBy (.totalDisplayRegionVisible >> .width >> negate)
        |> List.head


firstVisibleTextOfNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Maybe String
firstVisibleTextOfNode node =
    node.uiNode
        |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
        |> List.map (EveOnline.ParseUserInterface.stripHtmlTags >> String.trim)
        |> List.filter (String.isEmpty >> not)
        |> List.head


{-| Drag an inventory item onto a sidebar row, taking hold of the item's icon.

`dragAndDropUiElement` starts from the centre of the source, and in the icon
view that is where the icon meets the label under it -- one `InvItem` box
covers both, and `reload_drones.py` had to aim 25 px below the top of the box to
get the icon. The same offset is used here, clamped to half the height so that
a list-view row, which is shorter than that, is still grabbed inside itself.
-}
dragFromItemIconOntoUiElement :
    EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> DecisionPathNode
dragFromItemIconOntoUiElement itemElement targetElement =
    let
        itemRegion =
            itemElement.totalDisplayRegionVisible

        from =
            { x = itemRegion.x + (itemRegion.width // 2)
            , y = itemRegion.y + min itemIconOffsetFromTop (itemRegion.height // 2)
            }

        to =
            targetElement.totalDisplayRegionVisible
                |> EveOnline.ParseUserInterface.centerFromDisplayRegion
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


itemIconOffsetFromTop : Int
itemIconOffsetFromTop =
    25


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
                if not (nodeIsDisplayed button.uiNode.uiNode) then
                    -- The client keeps this button in the tree when it has no
                    -- travel step to offer, hiding it with `_display` False and
                    -- an empty label rather than removing it. Verified live on
                    -- "After The Seven (3 of 5)": the entry is expanded, the
                    -- objective renders, and the button is present, hidden and
                    -- unlabelled.
                    --
                    -- Nothing depended on this before, because the empty label
                    -- already fell through below. That is protection by
                    -- coincidence: a hidden button that kept a stale label
                    -- would be clicked, and clicking a control that is not on
                    -- screen is the same class of mistake as acting on an
                    -- overview row that is not rendered.
                    Nothing

                else
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
                        && not (List.member itemID context.memory.unlootableWreckIds)

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
                        |> List.sortBy overviewEntryDistanceOrFarInMeters
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
                                < (overviewEntryDistanceOrFarInMeters entry)
                        )
                    |> List.sortBy overviewEntryDistanceOrFarInMeters
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


{-| What the bot is currently trying to pick up off the grid, from either of the
two things that can ask for one.

The mission objective first, because it is the mission's own instruction, and
because a courier pickup names cargo the gate refusal never would. The gate key
second: it is only ever set while a gate has refused to open, and it is the
answer for the missions whose objective says nothing about cargo at all -- run
10's said only "You need to activate the Acceleration Gate".

They cannot both be live and mean different things at once in any observed case,
and if they ever are, the objective is the one the mission will actually clear on.

-}
itemToFetchFromTheGrid : BotDecisionContext -> Maybe String
itemToFetchFromTheGrid context =
    case courierCargoToLoad context of
        Just objectiveCargo ->
            Just objectiveCargo

        Nothing ->
            gateKeyWanted context


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

Since #44 the wanted item can also be the key a locked acceleration gate named,
which is why this asks `itemToFetchFromTheGrid` rather than the objective
directly -- see `gateKeyItemNameFromRefusal`.
-}
lootMissionItemFromContainerIfPresent : BotDecisionContext -> Maybe DecisionPathNode
lootMissionItemFromContainerIfPresent context =
    case itemToFetchFromTheGrid context of
        Nothing ->
            Nothing

        Just itemName ->
            case context.readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
                Just openLootWindow ->
                    Just
                        (describeBranch ("A container is open -- take the " ++ itemName ++ ".")
                            (case giveUpOnOpenContainerReason context of
                                Just reason ->
                                    -- Close it, do not merely stop acting on it.
                                    -- An open wreck loot window short-circuits
                                    -- the whole objective branch above, so
                                    -- waiting here hangs the bot on a container
                                    -- it has already decided to abandon.
                                    case openLootWindow.uiNode |> closeControlOfWindow of
                                        Just closeButton ->
                                            describeBranch (reason ++ " Close it and look elsewhere.")
                                                (clickUiElement closeButton)

                                        Nothing ->
                                            describeBranch
                                                (reason ++ " I cannot find its Close button to move on.")
                                                askForHelpToGetUnstuck

                                Nothing ->
                                    if not (shipIsWithinLootRange context.readingFromGameClient) then
                                        -- The window opens on the double click,
                                        -- not on arrival, and the client is still
                                        -- flying the ship over. Clicking now is
                                        -- refused outright with "You must be
                                        -- within 2500 meters of the container",
                                        -- which the bot cannot see and used to
                                        -- mistake for a completed loot.
                                        describeBranch
                                            ("Still on the way to the container -- wait until inside "
                                                ++ String.fromInt interactionRangeInMeters
                                                ++ " m before taking anything."
                                            )
                                            waitForProgressInGame

                                    else
                                        case openLootWindow.uiNode |> findUiElementWithText "Loot All" of
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
                                        overviewEntryDistanceOrFarInMeters containerEntry
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
                |> List.sortBy overviewEntryDistanceOrFarInMeters

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
                    case ensureQuickFilterText context inventoryWindow itemName of
                        Just filterStep ->
                            Just filterStep

                        Nothing ->
                            loadCourierCargoAfterFiltering
                                { itemName = itemName
                                , filterIsAlreadySet = quickFilterIsAlreadySet inventoryWindow itemName
                                , lookingAtACapacityLimitedContainer = lookingAtACapacityLimitedContainer
                                , itemHangarTreeEntry = itemHangarTreeEntry
                                }


{-| What the courier load does once the quick filter is set and the item is
still not in view: look in the station hangar rather than the hold we are
looking at, or give up.

Split out only so that `ensureQuickFilterText` can be shared with the drone
restock; the conditions are the ones that were here before. Note it still gives
up when the filter is *not* set and there is no filter box to set it with --
there is no step left to take then, and the caller reads that as "not loadable
here" and undocks.
-}
loadCourierCargoAfterFiltering :
    { itemName : String
    , filterIsAlreadySet : Bool
    , lookingAtACapacityLimitedContainer : Bool
    , itemHangarTreeEntry : Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    }
    -> Maybe DecisionPathNode
loadCourierCargoAfterFiltering { itemName, filterIsAlreadySet, lookingAtACapacityLimitedContainer, itemHangarTreeEntry } =
    if not filterIsAlreadySet then
        -- The filter still needs setting and there was no box to set it with,
        -- so there is no step left to take here.
        Nothing

    else if lookingAtACapacityLimitedContainer && itemHangarTreeEntry /= Nothing then
        -- Filtered, but looking at a hold with a capacity limit (the ship's
        -- own, most likely) rather than the station hangar, which reports no
        -- maximum. Switch once and let the next reading decide.
        itemHangarTreeEntry
            |> Maybe.map
                (\itemHangar ->
                    describeBranch
                        ("Look for '" ++ itemName ++ "' in the item hangar.")
                        (clickUiElement (itemHangar.selectRegion |> Maybe.withDefault itemHangar.uiNode))
                )

    else
        -- Filtered the station hangar and it is not there, so it is not
        -- something we can load here. Give up rather than loop: missions like
        -- "Get the Relic" want an item that is in a container out in space, and
        -- returning Nothing lets the caller undock and go find it.
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


{-| Get the inventory's quick filter reading the text we want, or Nothing if it
already does.

Shared by the courier load and the drone restock, because the trap it guards is
the same for both: the box keeps whatever was typed into it last, and typing
again appends, so "Acolyte IAcolyte I" matches nothing and looks exactly like
the typing having failed. Clearing is a click on the box's own Clear button --
see `quickFilterClearButton` for why no select-all shortcut works here.
-}
ensureQuickFilterText :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.InventoryWindow
    -> String
    -> Maybe DecisionPathNode
ensureQuickFilterText context inventoryWindow textToFilterFor =
    if quickFilterIsAlreadySet inventoryWindow textToFilterFor then
        Nothing

    else
        inventoryWindow.quickFilterInputBox
            |> Maybe.map
                (\filterBox ->
                    if previousStepClickedMouse context then
                        describeBranch
                            "I just clicked the quick-filter box -- wait for the reading to catch up before typing."
                            waitForProgressInGame

                    else
                        case
                            ( inventoryWindow.quickFilterText
                                |> Maybe.withDefault ""
                                |> String.trim
                                |> String.isEmpty
                            , quickFilterClearButton filterBox
                            )
                        of
                            ( False, Just clearButton ) ->
                                -- Whatever is in there is not what we want and
                                -- typing cannot replace it, so empty it first
                                -- and type on the next reading.
                                describeBranch
                                    "The quick filter holds something else -- clear it before typing."
                                    (clickUiElement clearButton)

                            _ ->
                                describeBranch
                                    ("Filter the inventory for '" ++ textToFilterFor ++ "'.")
                                    (decideActionForCurrentStep
                                        (List.concat
                                            [ mouseClickOnUIElement MouseButtonLeft filterBox
                                                |> Result.withDefault []
                                            , typeTextEffects textToFilterFor
                                            ]
                                        )
                                    )
                )


{-| Whether the quick filter already narrows the container down to what we are
looking for.

A prefix, not an exact match. Typing into this field drops characters:
"reports" lands as "report" every time it was tried live. Demanding the whole
string back meant the filter never looked set, so the bot retyped for the rest
of the session -- while the filter it had already typed was doing its job, since
the field is a substring match and "report" finds Reports perfectly well. Any
non-empty prefix is good enough to stop typing; an empty box or unrelated text
still is not.
-}
quickFilterIsAlreadySet : EveOnline.ParseUserInterface.InventoryWindow -> String -> Bool
quickFilterIsAlreadySet inventoryWindow textToFilterFor =
    inventoryWindow.quickFilterText
        |> Maybe.map
            (\current ->
                let
                    typed =
                        current |> String.trim |> String.toLower
                in
                not (String.isEmpty typed)
                    && String.startsWith typed (expectedQuickFilterText textToFilterFor)
            )
        |> Maybe.withDefault False


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


{-| The quick filter's own Clear button, so typing starts from an empty box.

No select-all shortcut works here, both tried live against this client. Control+A
is the macOS "move to start of line" binding, so the bot moved the caret and then
inserted: run 115's filter accumulated "reportreprrrr...reporteporteporte..."
across retries. Command+A is worse -- it does not select, and it leaves the field
swallowing every keystroke that follows, so run 116 typed 128 times and changed
the box by not one character.

Clearing by button is what actually works: verified live, 6,818 characters of
accumulated junk to empty in one click.

Identified by type rather than by label. It is a `ButtonIcon` whose text lives in
`_hint`, and `getDisplayText` reads only `_setText`/`_text`, so a text search
never matches it -- the same trap `closeControlOfWindow` documents. It is the one
`ButtonIcon` inside the filter box.
-}
quickFilterClearButton :
    EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
quickFilterClearButton filterBox =
    filterBox
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "ButtonIcon")
        |> List.head


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
            case
                if courierLoadHasHadLongEnough context then
                    Nothing

                else
                    courierCargoToLoad context |> Maybe.andThen (loadCourierCargoDescribed context)
            of
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
    previousStepsEffectsPressedMouse context.previousStepsEffects


{-| Split out from `previousStepClickedMouse` so that
`updateMemoryForNewReadingFromGame`, which gets the same effects but not a
decision context, can ask the same question.
-}
previousStepsEffectsPressedMouse : List (List EffectOnWindow.EffectOnWindowStruct) -> Bool
previousStepsEffectsPressedMouse previousStepsEffects =
    previousStepsEffects
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


{-| Whether the step just dispatched was a drag rather than a click.

The distinction is the pointer moving while a button is held, and it is exact
rather than a heuristic: `effectsMouseClickAtLocation` emits move, down, up and
never moves in between, while `effectsForDragAndDrop` always does -- that
prompt move is the whole reason a drag registers as one. So this separates the
restock's drag from every click it also issues into the same window, which
matters because the drag is the step that has to be counted and bounded.
-}
previousStepsEffectsDragged : List (List EffectOnWindow.EffectOnWindowStruct) -> Bool
previousStepsEffectsDragged previousStepsEffects =
    previousStepsEffects
        |> List.take 1
        |> List.any effectsMovePointerWhileButtonHeld


effectsMovePointerWhileButtonHeld : List EffectOnWindow.EffectOnWindowStruct -> Bool
effectsMovePointerWhileButtonHeld =
    List.foldl
        (\effect ( buttonIsHeld, hasMovedWhileHeld ) ->
            case effect of
                EffectOnWindow.ButtonDown _ ->
                    ( True, hasMovedWhileHeld )

                EffectOnWindow.ButtonUp _ ->
                    ( False, hasMovedWhileHeld )

                EffectOnWindow.MouseMoveTo _ ->
                    ( buttonIsHeld, hasMovedWhileHeld || buttonIsHeld )

                _ ->
                    ( buttonIsHeld, hasMovedWhileHeld )
        )
        ( False, False )
        >> Tuple.second


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
                    (returnDronesToBay context waitForProgressInGame)

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

**The one step that outranks the fight instead of following it is "Dock"**,
and `dockOutranksTheFight` is the whole of that exception -- see there for why
it is the only label that gets one, and for what still keeps the guns firing
after it appears.
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
    dockOutranksTheFight context
        (decideActionInCombat context seeUndockingComplete
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
                                                        if nothingToDoTicksBeforeCryingStuck < context.memory.nothingToDoTicks then
                                                            -- Waiting was the right first answer and the wrong
                                                            -- last one. This branch is the bottom of the tree:
                                                            -- nothing to shoot, no cargo it can find, no travel
                                                            -- step, no gate, no route, no configured object on
                                                            -- grid. If that has not changed in minutes, the
                                                            -- mission is not "catching up" and nothing here will
                                                            -- make it.
                                                            --
                                                            -- Two runs died in this branch without a word. Run
                                                            -- 114 sat in it for 14,111 decisions, 37% of the
                                                            -- session. Run 124 reached it with the tracker
                                                            -- offering no travel button at all and burned half
                                                            -- an hour. Neither raised an alarm, because waiting
                                                            -- looks identical whether the mission is a second
                                                            -- behind or permanently unreachable.
                                                            --
                                                            -- This does not rescue the mission -- it cannot, from
                                                            -- here. It converts a silently wasted session into
                                                            -- one that says so, which is what stall_watch
                                                            -- screenshots and reports.
                                                            -- Deliberately no reading count in the text. The
                                                            -- alarm repeats for as long as the state lasts, and
                                                            -- a counter in the message makes every repeat a
                                                            -- distinct line -- which defeats stall_watch's
                                                            -- dedupe and any log filter downstream. Run 126
                                                            -- emitted 151 unique variants of this one alarm.
                                                            describeBranch
                                                                ("Nothing to fight, no travel step, nothing on grid to approach, and over "
                                                                    ++ String.fromInt nothingToDoTicksBeforeCryingStuck
                                                                    ++ " readings of it -- this mission is not going to progress on its own."
                                                                )
                                                                askForHelpToGetUnstuck

                                                        else
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
        )


{-| Take the mission tracker's "Dock" step instead of clearing the field.

Once the travel button reads "Dock" and the objective carries no instruction,
the mission is over and the only thing being asked for is the trip back.
Whatever is still alive on the grid is optional, and killing it is uncompensated
risk: the site keeps producing rats, every extra minute on grid is more incoming
fire for no reward, and the time comes out of the next mission's session budget.

Run 11 is the measurement. The tracker read
`Illegal Activity (3 of 3) -- no instruction (next step: Dock)` on 77
consecutive in-space readings; 386 of the 453 decision blocks inside them went
to locking and shooting; and the first in-space click on that Dock button came
603 seconds -- just over ten minutes -- after the label first appeared, on the
first reading where the overview finally held zero rats. None of that was a
judgement the bot made. `decideActionInMissionPocket` wrapped the whole travel
branch in `decideActionInCombat`, so travel was the fallback reached only once
combat had nothing left to offer, and combat has something to offer for as long
as anything is alive.

**What still keeps the bot fighting after "Dock" appears**, since the point of
this branch is to stop:

  - **Anything warp disrupting the ship.** Docking is a warp, so a scrambler
    makes leaving impossible, and killing it is the only thing that restores the
    option -- `overviewEntryIsWarpDisruptingMe`'s own reason for existing, and
    the reason the combat path already sorts it to the front. This branch hands
    the fight back and says so, rather than clicking a Dock button that cannot
    work. It is the one case where being shot outranks leaving.
  - **Any other travel label.** "Undock", "Set Destination" and "Warp to
    Location" all appear mid-mission with work still to do, so they keep the old
    order. That is why the match is exact -- see `missionTravelStepIsDock`.
  - **An objective that still says something.** A tracker still carrying an
    instruction has not finished, whatever its travel button offers, so combat
    stays in front of it. The looting question is deliberately left alone: a
    wreck holding the mission item is not optional the way ordinary salvage is,
    and it deserves its own answer rather than being folded into this one. The
    one thing skipped that is not vacuous under "no instruction" is a gate key
    the *client* named (`gateKeyWanted`), and a gate key is only ever wanted for
    a pocket this mission no longer has to enter.
  - **A lost ship, and the retreats.** Both already sit above this and neither
    is touched. `recoverPodAfterShipLoss` answers `Just` on every reading its
    verdict exists and short-circuits the whole docked-or-in-space split, and
    `runAwayIfLowHealth` runs before `decideActionWhenInSpace` is called at all.
    So the damage-rate retreat still outranks this, which is the right way
    round: that one is the controller for "leave now, this is going badly", and
    this one is for "the job is done, go home". There is no second "leave now"
    here -- this branch presses the tracker's own button and owns no clock.

**Being shot, otherwise, does not keep the guns on.** That is a decision, not an
oversight. #40's rule -- whatever the client says is shooting this ship is a
valid target -- is untouched and still applies for as long as there is a fight
to be in; once the tracker says Dock, the answer to being shot is to leave,
which is what every retreat in this file already says. The recordings say the
trade is cheap: across those 77 readings the client's combat log reported any
incoming damage at all on 4 of them, at most 7 hitpoints in a 45-second window
against a threshold of 3500. The bot was not fighting for its life, it was
farming a field it had been told to leave. Were the damage real,
`runAwayIfLowHealth` would have taken the reading before this branch saw it.

**Drones leave through the existing recall**, never a second one: the click is
handed to `ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`,
exactly as the travel branch this hoists always did, so #7's lost drones and the
give-up that followed it both still apply, unchanged and un-duplicated.

Reachability. This runs on every reading that reaches
`decideActionInMissionPocket` -- in space, ship UI parsing, no ship-loss verdict
latched, no retreat running, no stray context menu, not in warp, no agent
conversation open, no middle-row module to manage -- and declines on all of them
but the ones described above. It cannot fire against a collapsed tracker: the
client removes the travel button from the tree along with the objectives, so
`missionTravelStep` is Nothing and `expandMissionTrackerIfCollapsed` gets its
turn under combat as before. And it clears itself, with no counter and nothing
latched: every condition is re-derived from the live reading, so the moment the
button stops reading "Dock" -- the ship docked, the mission moved on, the
tracker was collapsed -- the fight is the bot's job again on that same reading.
-}
dockOutranksTheFight : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
dockOutranksTheFight context ifTheFightIsStillOurs =
    case travelStepThatEndsTheFight context of
        Nothing ->
            ifTheFightIsStillOurs

        Just ( label, buttonNode ) ->
            case scramblerHoldingTheShipHere context of
                Just holdingUs ->
                    -- Said on every reading it declines, not once, for
                    -- `returnDronesToBay`'s reason: a branch that hands the
                    -- fight back has to be visible doing it, or the log reads
                    -- as though this change simply never fired.
                    describeBranch
                        ("The mission tracker says '"
                            ++ label
                            ++ "' and the objective asks for nothing more, but '"
                            ++ holdingUs
                            ++ "' is warp disrupting this ship -- nothing leaves until that is dead, so keep fighting."
                        )
                        ifTheFightIsStillOurs

                Nothing ->
                    describeBranch
                        ("The objective is complete and the mission tracker says '"
                            ++ label
                            ++ "' -- stop fighting and leave the rest of the field alone."
                        )
                        (ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping context
                            (clickMissionTravelButton context label buttonNode)
                        )


{-| The tracker's travel step, when it is the one that means the objective is
finished and only the trip home is left.

Both halves are needed. The label alone would disengage on a courier mission
whose delivery step is also a dock, and the empty objective alone would
disengage while the tracker still had a gate or a warp to offer.
-}
travelStepThatEndsTheFight :
    BotDecisionContext
    -> Maybe ( String, EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion )
travelStepThatEndsTheFight context =
    case missionInfoPanelEntry context of
        Nothing ->
            Nothing

        Just mission ->
            if not (missionHasNoOutstandingInstruction mission.instructionTexts) then
                Nothing

            else
                missionTravelStep context
                    |> Maybe.andThen
                        (\( label, buttonNode ) ->
                            if missionTravelStepIsDock label then
                                Just ( label, buttonNode )

                            else
                                Nothing
                        )


{-| Whether the tracker's travel label is the one that ends the mission.

Matched whole rather than as a substring, and this is the trap the whole change
turns on: **"Undock" contains "dock"**. It is the label the tracker shows at the
start of every single mission, so a substring rule would read the ship's own
departure as "the objective is complete" and disengage on the station ramp,
forever, with nothing to dock at. `labelUndoesStepInProgress` keeps "Abort
Undock" out of `missionTravelStep` already, but that is a different guard
answering a different question and cannot be leaned on for this one.

Trimmed and lowercased for `isObjectShootingAtUs`'s reason -- nothing here
should depend on the client's spacing or capitalisation staying put -- and
checked against the labels the recorded runs actually carry in
`tools/macos-host/tests/test_dock_outranks_the_fight.py`.
-}
missionTravelStepIsDock : String -> Bool
missionTravelStepIsDock label =
    (label |> String.trim |> String.toLower) == "dock"


{-| Whether the mission's objective has stopped asking for anything.

`instructionTexts` is the objective's own wording, and it is what every other
"what does this mission want" question in this file is already derived from:
`objectNamesToDestroy`, `objectNamesToCarry` and `objectNamesToApproach` are all
extracted from these strings, so an empty list means the mission names nothing
to kill, fetch or fly to. The status line prints the same thing, as "no
instruction", which is how run 11 reported it for the whole ten minutes.

Blank strings count as empty because a label the client rendered with no text is
not an instruction; `List.all` over an empty list is True, which is the intended
answer for a tracker whose objectives are all done.
-}
missionHasNoOutstandingInstruction : List String -> Bool
missionHasNoOutstandingInstruction instructionTexts =
    instructionTexts |> List.all (String.trim >> String.isEmpty)


{-| The first thing on the overview the client says is warp disrupting us, named
if it has a name.

The decision is the row's existence and never the name, because a row whose Name
cell the parser cannot read holds the ship just as firmly; the name is only for
the log line.

Deliberately **not** filtered by `overviewEntryIsDisplayed`, unlike anything
that clicks a row. That filter exists because a virtualised row's *position*
belongs to whatever was recycled into its place, and nothing here clicks
anything -- while a scrambler that has scrolled off the overview stops the ship
leaving exactly as well as one in view. Being wrong in this direction costs one
more fight, which is what the bot does today anyway.
-}
scramblerHoldingTheShipHere : BotDecisionContext -> Maybe String
scramblerHoldingTheShipHere context =
    context.readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsWarpDisruptingMe
        |> List.head
        |> Maybe.map (.objectName >> Maybe.withDefault "something the overview does not name")


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

{-| Every reason this bot has to stop fighting and leave.

Three, and they are deliberately not variations on one instrument.

**The two hitpoint thresholds** are the original guard and read the ship's HUD
gauges. They are the weakest of the three: the value is a float scraped out of a
widget in live memory (see `plausibleHitpointsPercent`), and on a shield-tanked
hull the armour gauge cannot move at all until the shield is spent -- across the
recorded runs the shield reached 9%, 12% and 44% while armour sat at exactly
100% in every one of thousands of samples. An armour threshold on such a hull is
not a conservative guard, it is a guard that fires after the tank is already
gone.

**The damage rate** needs no gauge at all. It is the client's own combat log,
summed by the host, and it answers the question the HUD is only a proxy for:
how fast is this ship being taken apart.

**The frozen reading.** A gauge that does not move while the ship absorbs
`damageThatMustMoveTheHitpointsReading` is not reporting the ship, and an
instrument that cannot answer is a reason to leave rather than a licence to
carry on. This is the guard for the shape issue #32 was filed about -- a reading
pinned at one value while damage lands -- and it is the one that needs saying
out loud, because "100%" and "no reading" look identical in a log and only one
of them means the ship is fine.

**A lost ship outranks all three of them**, and that is settled by placement
rather than by a condition here. `recoverPodAfterShipLoss` sits in
`missionBotDecisionRootBeforeApplyingSettings`'s pre-split list, and it answers
`Just` on every reading the verdict exists -- it is a bare `Maybe.map` over
`context.memory.shipLoss` -- so once #33's verdict latches, the whole
docked-or-in-space split below it is unreachable and this function is never
called again. That is the right order and not merely a convenient one: a retreat
manoeuvre is something a *ship* does, and the correct response to no longer
having one is #33's, which flies the pod home and ends the session saying why.
Warping a capsule between celestials would keep it alive and never finish.

The interaction that makes this worth stating rather than leaving to the layout:
a capsule *does* get shot, and being shot is exactly what arms the damage guard.
`updateIncomingDamageMemory` keeps running through a pod recovery, so the window
fills and the latch can set -- harmlessly, because nothing reads it from up
there, and usefully, because the status line still reports whether the pod is
under fire. The one case where this function speaks for a capsule at all is the
one where #33's verdict never arrives (both its signals missed), and there a
retreat is a strictly better fallback than run 7's alternative of sitting still
asking for locks. It is a fallback, not a second controller.

Reachability, since a compiling guard that can never fire is what shipped in
issue #12. All three are reached on every reading in space where the ship UI
parses and no ship-loss verdict has latched -- the same gate the original two
always had, plus the one above. The two damage-based ones additionally need
`incomingDamageSinceLastReading`, so on a host without the game log they are
unarmed -- which the status line says in as many words rather than leaving it to
be inferred from their silence. Against the recorded data: the damage threshold
would have fired in the session the ship was lost (peak 4101 in 45 s) and in
none of the fifteen it survived (worst 3114); the frozen-reading guard would not
have fired in any of the three runs whose gauge was live, where the most damage
absorbed during an unchanged reading was 595.
-}
runAwayIfLowHealth : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> Maybe DecisionPathNode
runAwayIfLowHealth context shipUI =
    let
        runAwayShieldThreshold =
            context.eventContext.botSettings.runAwayShieldHitpointsThresholdPercent

        incomingDamageThreshold =
            context.eventContext.botSettings.runAwayIncomingDamageThreshold

        damageInWindow =
            incomingDamageInWindow context.memory.incomingDamage

        describeAttacker =
            case context.memory.incomingDamage.lastAttacker of
                Nothing ->
                    ""

                Just attacker ->
                    ", hardest from '" ++ attacker ++ "'"

        describeWindow =
            (damageInWindow |> String.fromInt)
                ++ " hitpoints in the last "
                ++ (incomingDamageWindowSeconds |> String.fromInt)
                ++ " s"
                ++ describeAttacker

        runAwayFromIncomingDamage =
            describeBranch
                ("The client's combat log says we are taking "
                    ++ describeWindow
                    ++ " -- over the "
                    ++ (incomingDamageThreshold |> String.fromInt)
                    ++ " we are willing to sit through. Get out, whatever the HUD says."
                )
                (runAway context)

        runAwayFromAnInstrumentThatIsNotMoving =
            describeBranch
                ("We have absorbed "
                    ++ describeWindow
                    ++ " and the hitpoints reading has not moved off "
                    ++ (shipUI.hitpointsPercent.shield |> String.fromInt)
                    ++ "% shield / "
                    ++ (shipUI.hitpointsPercent.armor |> String.fromInt)
                    ++ "% armour for the whole window. That is not a reading, so it is no reason to stay. Get out."
                )
                (runAway context)

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

    else if context.memory.incomingDamage.retreating then
        -- The latch, not the live comparison. Set and released in
        -- updateIncomingDamageMemory, which is the only place that can hold a
        -- verdict across readings -- and holding it is the whole point: the
        -- moment the ship warps clear the window starts draining, so a live
        -- comparison would cancel its own retreat halfway through.
        Just runAwayFromIncomingDamage

    else if
        (damageThatMustMoveTheHitpointsReading <= damageInWindow)
            && (hitpointsReadingMovedInWindow context.memory.incomingDamage == Just False)
    then
        Just runAwayFromAnInstrumentThatIsNotMoving

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

        -- Issue #40: name what is in the list *only* because the client said it
        -- hit us. Without this an operator reading the decision log sees the bot
        -- engage something the overview does not colour as a rat and nothing
        -- names in the settings, with no way to tell learning from misfiring.
        -- Recomputed here rather than carried on the entry because
        -- `shouldAttackOverviewEntry` returns a Bool and widening it to report
        -- which disjunct matched would change every call site for one log line.
        entriesEngagedOnlyBecauseTheyShotUs =
            overviewEntriesToAttack
                |> List.filter
                    (\entry ->
                        isObjectShootingAtUs (objectNamesToAttack context).fromIncomingDamage entry
                            && not (iconSpriteHasColorOfRat entry)
                            && not (isObjectToAttackByName (objectNamesToAttack context) entry)
                    )

        describeShootingBack decision =
            case
                entriesEngagedOnlyBecauseTheyShotUs
                    |> List.filterMap .objectName
                    |> Common.Basics.listUnique
            of
                [] ->
                    decision

                names ->
                    describeBranch
                        ("Shooting back at "
                            ++ (names |> List.map (\name -> "'" ++ name ++ "'") |> String.join ", ")
                            ++ ": the client's combat log names it as having hit this ship in the last "
                            ++ (incomingDamageWindowSeconds |> String.fromInt)
                            ++ " s, and nothing else here marks it as a target."
                        )
                        decision

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
                |> List.sortBy overviewEntryDistanceOrFarInMeters

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

        -- The ammo swap sits in front of the fight rather than beside it: it
        -- declines on most readings and hands the fight straight on, and the
        -- readings where it does act are ones where firing this instant matters
        -- less than firing the right charge for the next minute.
        decisionToFight =
            ensureAmmoSuitsTargetRange context decisionToKillRats

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
        describeShootingBack (ensureShipIsOrbitingDecision |> Maybe.withDefault decisionToFight)

    else if context.eventContext.botSettings.keepAtRange == AppSettings.Yes then
        describeShootingBack (ensureShipIsKeepingRangeDecision |> Maybe.withDefault decisionToFight)

    else
        describeShootingBack decisionToFight


{-| How many readings to keep commanding a manoeuvre the client never confirms
before letting the ship get on with shooting instead.

Both keep-at-range and orbit report success only through the HUD's manoeuvre
indicator, and on this client `HudActionIndicationContainer` is often empty --
so `ManeuverRange`/`ManeuverOrbit` never arrives and the branch re-issues
forever. Run 111 spent a whole 180-minute session on the range one: 8,941
keypresses, no missions. Orbit is the same shape and now carries the same
locked-target check, so this counter is the last line of defence for both
rather than the only one for orbit.

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

        else if not (overviewEntryToOrbit |> overviewEntryIsTargetedOrTargeting) then
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

{-| How many consecutive readings the distance has to say the same thing before
the bot swaps ammo.

The "current target" is not a stable thing to measure: rats die, the next one is
promoted, and the distance jumps from 8 km to 40 km between two readings without
the ship or the fight changing. Acting on a single reading would therefore let
target churn drive the guns. This is the same guard as
`routeFirstMarkerUnchangedTicks`, applied to a number rather than a region.
-}
ammoSwapDistanceHoldTicks : Int
ammoSwapDistanceHoldTicks =
    4


{-| How many readings one verdict gets before the bot abandons that swap and
gets back to shooting.

This bounds **one attempt**, not the feature. That distinction is the correction
issue #27 forced. The number it replaces was fifty readings and it latched the
whole ammo swap off for the session, on the theory that a swap which never
confirms is a swap that cannot work here. What it was actually measuring was the
client discarding every load because the guns were active -- a transient,
fixable condition that it read as a permanent one, and then disabled the feature
over.

So a failed attempt now costs one verdict. The guns go back to firing whatever is
in them, and the next time the range calls for a change the bot tries again. Only
the two structural impossibilities latch for the session, because only they are
genuinely permanent: the ship carrying neither charge, and there being no
crossover distance to decide against.

Sized for the whole sequence on a multi-gun row -- silence the guns, then a menu
per gun, several readings each -- with enough headroom for one retry.
-}
ammoSwapVerdictGiveUpTicks : Int
ammoSwapVerdictGiveUpTicks =
    25


{-| How many readings the bot keeps hovering a weapon waiting for its tooltip
before deciding this client will not show one.

This used to disable the whole ammo swap, because the tooltip's `optimalRange`
was the only thing that said which charge was loaded. It is not any more -- the
weapon's own context menu says that, and says it without a hover -- so failing
here now costs only the *refinement*: the crossover distance the swap would
otherwise have derived from the two charges' optimal ranges. With
`ammo-swap-range` set, nothing is lost at all.

Small, because the bot holds the mouse still while it waits -- see
`hoverWeaponForOptimalRange` -- and holding still is holding off the rest of the
fight. It is also attempted at most twice a session: once per charge, after which
both optimal ranges are known and there is nothing left to learn.
-}
weaponTooltipUnansweredGiveUpTicks : Int
weaponTooltipUnansweredGiveUpTicks =
    5


{-| How long the swap may leave the ship's guns switched off, counted from the
reading it first told one to stop.

**One deadline over the whole silent period, not one per phase.** That is the
correction issue #34 forced, and the distinction is the whole point. The previous
version bounded *getting the guns quiet* and left the phase after it -- waiting
for the ramp to finish -- with no counter at all. Run 8 sat in that second phase
for 298 readings with the guns off and eleven hostiles on the overview, because
the branch that would have handed the fight back is downstream of the wedge: the
guns come back when the swap stops, and that branch was what stopped the swap
from ever stopping.

So this counts readings, unconditionally, from the first switch-off command until
the swap lets go. It is advanced by nothing more specific than "the swap is still
holding a verdict it has silenced the guns for", which is what makes it
structural: a phase added inside that window cannot escape it by forgetting to
count, and no reading of the module's own state can stall it, which matters
because those readings are exactly what turned out to be untrustworthy (#35).

**A weapon that will not go quiet keeps shooting the wrong charge.** Failing to a
firing gun with the wrong ammo is always better than failing to a silent gun.
Reaching this deadline means the ship was disarmed and the bot could not get it
back on its own schedule, so it is the one failure here that switches the whole
swap off for the session rather than just abandoning the attempt -- see
`ammoSwapVerdictGiveUpTicks` for why every other failure does the opposite.
Repeating a manoeuvre that disarms the ship, once it has demonstrably not worked,
is not an optimisation worth retrying.

Comfortably longer than the sequence needs -- a settle plus a cascade or two --
and comfortably shorter than `ammoSwapVerdictGiveUpTicks`, so that the dangerous
state is always the first one to time out.
-}
ammoSwapSilencedGiveUpTicks : Int
ammoSwapSilencedGiveUpTicks =
    20


{-| How many readings to let a switch-off settle before loading anyway.

A count, deliberately, and not a condition on the module. The condition this
replaces was "wait until the ramp stops turning", which is the wait that hung:
`rampRotationMilli` is derived from a widget the client creates and destroys
around a cycle, `isActive` reads `ramp_active`, and #35 measured `ramp_active`
reading `False` on a module that was switched **on**. A wait on a signal that may
never say what it is being asked is a wait that may never end, however patient.

A count always ends. And it can afford to be short, because the bot no longer has
to be *sure* the gun is quiet before trying: since #31 the client's own refusal
says when a load was thrown away, so an attempt made too early is answered in one
reading rather than guessed at. Being wrong costs a reading; waiting to be
certain cost run 8 nearly three hundred.
-}
ammoSwapSilenceSettleTicks : Int
ammoSwapSilenceSettleTicks =
    3


{-| How many entries a weapon's context menu must have before the bot will
believe what is missing from it.

The whole design reads the *absence* of a charge as proof that it is loaded, so
a menu caught half-built would say every charge is loaded at once. Verified live,
a weapon's menu carries seven entries; the five commands are there whatever is
loadable, so this is comfortably below any real menu and above a menu that has
not arrived.
-}
ammoSwapMenuEntriesBeforeTrusted : Int
ammoSwapMenuEntriesBeforeTrusted =
    3


{-| How far past the crossover distance the target has to be before the swap
fires, in meters.

A single threshold makes a target sitting near it swap on every reading. Two
thresholds fix that, and where the crossover is a *fixed* number -- the setting,
or the midpoint of the two optimal ranges -- any positive deadband is stable, so
a plain constant is enough.

That is worth saying because the first version of this needed an argument about
half the spread between the two charges' optimal ranges. It needed it because the
threshold there was the *currently loaded* charge's optimal range, so every swap
moved the threshold and could re-arm the opposite one. That case still exists,
but only as the bootstrap below, and it carries its own wider deadband.
-}
ammoSwapDeadbandMeters : Int
ammoSwapDeadbandMeters =
    3000


{-| The deadband used while the crossover is still the loaded charge's own
optimal range, in meters.

This is the one case where the threshold moves when the swap fires, so the
deadband has to cover it: after swapping to the long-range charge the optimal
becomes the higher number, and the short-range rule re-arms unless the deadband
is at least half the distance between the two. Half the spread is not knowable
before the second range has been seen -- that is the whole reason this case
exists -- so it is a fixed figure wide enough for the usual short/long spread of
a cruiser-sized weapon.

Worst case it costs one extra swap, after which both ranges are known, the
crossover becomes the fixed midpoint, and this is never used again.
-}
ammoSwapBootstrapDeadbandMeters : Int
ammoSwapBootstrapDeadbandMeters =
    20000


{-| Where the swap changes its mind, and how far past it a target has to be.

Three sources, in order, and which one answered matters enough to carry: the
deadband differs, and an operator reading the status line should be able to tell
a configured number from a derived one.

1.  **`ammo-swap-range`.** The only source that does not depend on a tooltip,
    and therefore the only one that works on a client that shows no module
    tooltip at all -- which this one may well be.
2.  **The midpoint of the two optimal ranges**, once both have been seen. The
    natural crossover: shoot the short-range charge inside it and the long-range
    charge outside. Fixed, so the ordinary deadband is enough.
3.  **The loaded charge's own optimal range**, when only one has been seen. This
    is the bootstrap, and it exists because otherwise the second range could
    never be learned: seeing it requires a swap, deciding a swap requires a
    crossover, and a crossover would require both ranges. One swap on this
    breaks the cycle, after which source 2 takes over for good.

`Nothing` is a real answer and is handled rather than defaulted: no setting and
no tooltip means the bot knows which charge is loaded but has nothing to say
about which one *should* be, so it does not swap and says so. Guessing a distance
would be worse than doing nothing, since wrong ammo still does damage.
-}
type alias AmmoSwapThreshold =
    { crossoverInMeters : Int
    , deadbandInMeters : Int
    , source : String
    }


ammoSwapThreshold : BotSettings -> AmmoSwapMemory -> Maybe AmmoSwapThreshold
ammoSwapThreshold botSettings ammoSwap =
    case botSettings.ammoSwapRangeMeters of
        Just fromSettings ->
            Just
                { crossoverInMeters = fromSettings
                , deadbandInMeters = ammoSwapDeadbandMeters
                , source = "the ammo-swap-range setting"
                }

        Nothing ->
            case ( ammoSwap.optimalRangeSeenLow, ammoSwap.optimalRangeSeenHigh ) of
                ( Just low, Just high ) ->
                    if low < high then
                        Just
                            { crossoverInMeters = (low + high) // 2
                            , deadbandInMeters = ammoSwapDeadbandMeters
                            , source = "the midpoint of the two optimal ranges seen"
                            }

                    else
                        ammoSwapBootstrapThreshold ammoSwap

                _ ->
                    ammoSwapBootstrapThreshold ammoSwap


ammoSwapBootstrapThreshold : AmmoSwapMemory -> Maybe AmmoSwapThreshold
ammoSwapBootstrapThreshold ammoSwap =
    ammoSwap.optimalRangeInMeters
        |> Maybe.map
            (\optimalRange ->
                { crossoverInMeters = optimalRange
                , deadbandInMeters = ammoSwapBootstrapDeadbandMeters
                , source = "the loaded charge's own optimal range, no second range seen yet"
                }
            )


{-| The client's own words for having discarded a load, if it said them since
the last reading.

Matched on the two parts of the sentence that do not vary. The weapon's name sits
between them -- `You cannot load or unload Focused Modulated Medium Energy Beam I
while it is active.` -- so a whole-line match would be per-fitting, and matching
`cannot` alone would catch every other refusal the client makes.

The channel is checked where the host gave one. A `Nothing` channel is a host
that did not say which, not a line without one, so it is judged on its text alone
rather than dropped.

Note what this does *not* do. `Nothing` from the game log and `Just []` are
collapsed here, and that is safe only because of the direction of the inference:
finding no refusal is never read as the load having been accepted. The menu is
what says that. Nothing anywhere may conclude "no refusal arrived, so it worked",
which is the reading of an absent game log that would put this repo's signature
bug back.
-}
loadRefusalFromGameLog : ReadingFromGameClient -> Maybe String
loadRefusalFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase "cannot load or unload" entry.text
                    && stringContainsIgnoringCase "while it is active" entry.text
            )
        |> List.head
        |> Maybe.map .text


gameLogEntryIsFromNotifyChannel : EveOnline.ParseUserInterface.GameLogEntry -> Bool
gameLogEntryIsFromNotifyChannel entry =
    case entry.channel of
        Nothing ->
            True

        Just channel ->
            (channel |> String.trim |> String.toLower) == "notify"


gameLogEntryIsFromInfoChannel : EveOnline.ParseUserInterface.GameLogEntry -> Bool
gameLogEntryIsFromInfoChannel entry =
    case entry.channel of
        Nothing ->
            True

        Just channel ->
            (channel |> String.trim |> String.toLower) == "info"


{-| The client saying this acceleration gate wants an item the ship is not
carrying, in its own words.

Run 10 pressed the panel's Activate on a gate 32 m away, nine times over two
minutes, and the client answered every one of them on the `info` channel:

    This gate is locked! To activate it, you need to have R.S. Officer's
    Passcard in your cargo hold. By all signs it will not be consumed upon use,
    so the only problem is to locate the thing!

The bot read none of it. The refusal also arrives as a message box, which
`closeMessageBox` dismissed as generic noise, so the whole exchange was a press,
a dismissal and another press -- until `gateWithinReachTicks` ran out and the
gate branch fell silent. See `activateAccelerationGateIfPresent`.

**Two substrings, and here the second one carries the whole distinction rather
than merely guarding a rewording.** The recorded game logs hold two different
sentences opening "This gate is locked!", and they want opposite responses:

    ... There are synchronized gate scramblers on all hostile entities in this
    area ... you must simply clear the vicinity of enemy ships.

That one is transient and the bot already answers it correctly by fighting; a
matcher on the exclamation alone would fire on it and stop a run that was about
to succeed. `in your cargo hold` is what separates a standing requirement the
bot cannot meet from a fight it is already winning, so it is not optional and
`This gate is locked` must never be matched on its own.

`Nothing` and `Just []` are collapsed, safely and in the same direction as
#31's and #33's matchers: finding no such line is never read as the gate being
open. What says the gate opened is the pocket changing.

-}
gateLockedForWantOfAnItemFromGameLog : ReadingFromGameClient -> Maybe String
gateLockedForWantOfAnItemFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromInfoChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase "gate is locked" entry.text
                    && stringContainsIgnoringCase gateKeyClosingMarker entry.text
            )
        |> List.head
        |> Maybe.map .text


{-| The key the locked gate is asking for, taken out of the client's sentence.

    ... you need to have R.S. Officer's Passcard in your cargo hold ...
                         ^^^^^^^^^^^^^^^^^^^^^^^

#41 stopped at reporting the refusal, on the grounds that the objective names no
cargo so the loot path had nothing to look for. Half of that was wrong: the
*client* names it, and the whole retrieval path -- `isLootableFor`,
`lootableHoldingMissionItem`, `scrollOverviewToReveal`, the `prefer-wreck`
setting -- already takes the item name as an argument. This is the missing
source of that argument, and nothing downstream of it is new. The passcard was
in a nearby wreck, and looting it by hand is what let run 10's mission continue.

**Bounded by the same literal the matcher pins**, not by a wider one.
`gateKeyClosingMarker` is the substring `gateLockedForWantOfAnItemFromGameLog`
already requires, so the extraction cannot succeed on a sentence the matcher
would not have accepted -- in particular the scrambled-gate refusal, which wants
a fight rather than an errand. The opening marker is the narrower of the two and
never appears alone in the corpus.

The name is returned exactly as the client wrote it, punctuation and all, and
handed to `isLootableFor` to match the same way every other item name is.
"R.S. Officer's Passcard" carries two periods and an apostrophe, and inventing a
second matching rule for them would be a rule with one observation behind it.
What that costs is worth naming: a plain substring match means the *named
container* branch only fires if an overview row literally contains the name, and
a wreck's row carries the dead ship's name instead -- so a key inside a wreck is
found by the blind wreck-opening branch, exactly as for every other mission item
that comes out of something destroyed.

-}
gateKeyItemNameFromRefusal : String -> Maybe String
gateKeyItemNameFromRefusal clientSentence =
    let
        lowercased =
            String.toLower clientSentence

        openingMarker =
            "you need to have "
    in
    String.indexes openingMarker lowercased
        |> List.head
        |> Maybe.andThen
            (\openingIndex ->
                let
                    nameStart =
                        openingIndex + String.length openingMarker
                in
                String.indexes gateKeyClosingMarker lowercased
                    |> List.filter ((<) nameStart)
                    |> List.head
                    |> Maybe.map (\nameEnd -> String.slice nameStart nameEnd clientSentence)
            )
        |> Maybe.map String.trim
        |> Maybe.andThen
            (\itemName ->
                if String.isEmpty itemName then
                    Nothing

                else
                    Just itemName
            )


{-| The right-hand edge of the item's name, and the substring that tells this
refusal from the one that opens itself. One definition for both jobs so they
cannot drift apart -- see `gateLockedForWantOfAnItemFromGameLog`.
-}
gateKeyClosingMarker : String
gateKeyClosingMarker =
    "in your cargo hold"


{-| The key a latched locked-gate refusal is asking for, if it named one.
-}
gateKeyWanted : BotDecisionContext -> Maybe String
gateKeyWanted context =
    context.memory.gateLockedForWantOfAnItem
        |> Maybe.andThen gateKeyItemNameFromRefusal


{-| Whether this weapon is running, and so whether the client will refuse to
load a charge into it.

EVE does not merely prefer an idle module. Run 5's own game log:
`You cannot load or unload Focused Modulated Medium Energy Beam I while it is
active.` -- and that refusal arrives only as a client `(notify)` line, which the
bot does not read. So a load commanded at a firing gun is discarded in silence,
and the confirmation that follows finds nothing changed because nothing happened.

`isActive` is `Nothing` when the module has never run, which
`inactiveModulesToActivateAlways` documents at length; treated as not firing
here, for the same reason it is treated as off there.

**Used to choose whether to press the switch-off, and for nothing else.** It was
also once used to decide whether the gun was *ready* to be loaded, together with
`rampRotationMilli`, and that is the pair of readings run 8 hung on: the counter
in front reset every time this flickered between cycles, and the wait behind it
never ended because the ramp never went quiet. #35 then measured `ramp_active` --
which is what this reads -- returning `False` on a module that was switched on.

So nothing here waits on either signal any more. Being wrong about this costs one
reading: the load is attempted anyway, and the client's own refusal (#31) says if
the gun was still running.
-}
weaponIsFiring : ShipUIModuleButton -> Bool
weaponIsFiring moduleButton =
    moduleButton.isActive == Just True


{-| The weapons, left to right.

Sorted by `x` rather than taken in list order, because the parser drops any
module button whose display region it cannot read -- so the row's index space is
not stable across readings even while nothing moves on screen, and indexing it
has clicked a neighbouring module live.
-}
weaponModuleButtonsLeftToRight : ReadingFromGameClient -> List ShipUIModuleButton
weaponModuleButtonsLeftToRight readingFromGameClient =
    readingFromGameClient.shipUI
        |> Maybe.map (.moduleButtonsRows >> .top)
        |> Maybe.withDefault []
        |> List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


{-| The distance to the target the guns are actually shooting at, in meters, or
nothing at all.

`Nothing` covers three different situations that all mean "do not swap": no
locked target is active, no overview row belongs to it, or the row shows a
distance in AU. That last one is the point. AU distances do not parse, and the
placeholder every other consumer falls back to (999999) reads as merely far,
which is precisely the input that would argue for long-range ammo. Nothing in AU
is in weapons range of anything, so it is excluded here rather than converted.
-}
activeTargetDistanceInMeters : ReadingFromGameClient -> Maybe Int
activeTargetDistanceInMeters readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsActiveTarget
        |> List.head
        |> Maybe.andThen (.objectDistanceInMeters >> Result.toMaybe)


{-| Strip the quantity a charge entry carries in a weapon's context menu.

Observed live: right-clicking a weapon holding Radio M offered
`Multifrequency M [4]`, twice. So an entry's text is the charge name plus a
count, and a setting naming the charge will never equal it.
-}
stripChargeQuantitySuffix : String -> String
stripChargeQuantitySuffix text =
    case text |> String.split "[" of
        beforeBracket :: _ :: _ ->
            String.trim beforeBracket

        _ ->
            String.trim text


{-| Whether a weapon's context menu offers this charge.

Exact match after stripping the quantity, because a substring test is a trap in
both directions -- `attack-object` learned that live, where `Warehouse` matched
a station's full name. The substring test is kept only as a fallback for a menu
where nothing matched exactly, so a client that formats the quantity differently
degrades rather than failing outright.

Duplicates need no handling beyond using `any`: the same charge is listed twice
in the one menu observed, and two entries for one charge must not read as two
different charges.
-}
weaponMenuOffersCharge : String -> List String -> Bool
weaponMenuOffersCharge chargeName entryTexts =
    let
        wantedNormalised : String
        wantedNormalised =
            chargeName |> String.trim |> String.toLower

        matchesAfterStrippingQuantity : String -> Bool
        matchesAfterStrippingQuantity entryText =
            (entryText |> stripChargeQuantitySuffix |> String.toLower) == wantedNormalised
    in
    if entryTexts |> List.any matchesAfterStrippingQuantity then
        True

    else
        entryTexts |> List.any (stringContainsIgnoringCase chargeName)


{-| Whether the step just executed moved the mouse onto this element and did
nothing else.

A hover is the whole of the tooltip request, so "we asked" and "we clicked" have
to be told apart: a click carries a `ButtonDown` in the same step. The region
test keeps the context-menu cascade's own hover over a submenu entry from being
read as a request for a module tooltip.
-}
previousStepHoveredElement : List (List EffectOnWindow.EffectOnWindowStruct) -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
previousStepHoveredElement previousStepsEffects element =
    case previousStepsEffects |> List.head of
        Nothing ->
            False

        Just effects ->
            (effects |> List.any (effectMovesMouseInto element.totalDisplayRegion))
                && not (effects |> List.any effectPressesAMouseButton)


{-| Whether the step just executed right-clicked this element -- which for a
module button is the bot opening its context menu, and so the one observable
sign that this gun has been visited.
-}
previousStepRightClickedElement : List (List EffectOnWindow.EffectOnWindowStruct) -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
previousStepRightClickedElement previousStepsEffects element =
    previousStepsEffects
        |> List.take 1
        |> List.any (\effects -> effectsRightClickElement effects element)


effectsRightClickElement : List EffectOnWindow.EffectOnWindowStruct -> EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
effectsRightClickElement effects element =
    (effects |> List.any (effectMovesMouseInto element.totalDisplayRegion))
        && (effects |> List.member (EffectOnWindow.ButtonDown MouseButtonRight))


effectMovesMouseInto : EveOnline.ParseUserInterface.DisplayRegion -> EffectOnWindow.EffectOnWindowStruct -> Bool
effectMovesMouseInto region effect =
    case effect of
        EffectOnWindow.MouseMoveTo location ->
            (region.x <= location.x)
                && (location.x <= region.x + region.width)
                && (region.y <= location.y)
                && (location.y <= region.y + region.height)

        _ ->
            False


effectMovesTheMouse : EffectOnWindow.EffectOnWindowStruct -> Bool
effectMovesTheMouse effect =
    case effect of
        EffectOnWindow.MouseMoveTo _ ->
            True

        _ ->
            False


effectPressesAMouseButton : EffectOnWindow.EffectOnWindowStruct -> Bool
effectPressesAMouseButton effect =
    case effect of
        EffectOnWindow.ButtonDown _ ->
            True

        _ ->
            False


{-| The optimal range the client is showing right now, if this reading's tooltip
is one the bot asked for.

`getModuleButtonTooltipFromModuleButton` is not used, deliberately. The framework
files a tooltip against a module button only when some button reports
`isHiliteVisible`, and on this client that sprite does not exist -- so its
dictionary stays empty no matter how long the mouse rests on a module. The bot
does not need the client to tell it which button the tooltip belongs to, though:
it chose to hover that button itself, and the previous step's effects say where
the mouse went.
-}
weaponOptimalRangeFromHover :
    List (List EffectOnWindow.EffectOnWindowStruct)
    -> ReadingFromGameClient
    -> Bool
    -> Maybe Int
weaponOptimalRangeFromHover previousStepsEffects readingFromGameClient hoverWasPending =
    let
        weWereHovering =
            hoverWasPending
                || (weaponModuleButtonsLeftToRight readingFromGameClient
                        |> List.any (.uiNode >> previousStepHoveredElement previousStepsEffects)
                   )
    in
    if not weWereHovering then
        Nothing

    else
        readingFromGameClient.moduleButtonTooltip
            |> Maybe.andThen .optimalRange
            |> Maybe.andThen (.inMeters >> Result.toMaybe)


updateAmmoSwapMemory : UpdateMemoryContext BotSettings -> AmmoSwapMemory -> AmmoSwapMemory
updateAmmoSwapMemory context memoryBefore =
    case ( context.botSettings.shortRangeAmmoName, context.botSettings.longRangeAmmoName ) of
        ( Just shortRangeAmmoName, Just longRangeAmmoName ) ->
            updateAmmoSwapMemoryWithChargeNames context
                { shortRangeAmmoName = shortRangeAmmoName, longRangeAmmoName = longRangeAmmoName }
                memoryBefore

        _ ->
            -- The swap is off, so nothing here means anything. Reset rather than
            -- freeze, so that turning it on from the web console mid-session
            -- starts from a clean state instead of one assembled before the
            -- charge names existed.
            initAmmoSwapMemory


updateAmmoSwapMemoryWithChargeNames :
    UpdateMemoryContext BotSettings
    -> { shortRangeAmmoName : String, longRangeAmmoName : String }
    -> AmmoSwapMemory
    -> AmmoSwapMemory
updateAmmoSwapMemoryWithChargeNames context chargeNames memoryBefore =
    let
        guns =
            weaponModuleButtonsLeftToRight context.readingFromGameClient

        gunJustRightClickedAtX =
            guns
                |> List.filter (.uiNode >> previousStepRightClickedElement context.previousStepsEffects)
                |> List.map (.uiNode >> .totalDisplayRegion >> .x)
                |> List.head

        -- Which gun the open context menu belongs to. The bot opened it, so it
        -- knows: nothing in the menu itself says which module it came from.
        menuOpenOnGunAtX =
            if context.readingFromGameClient.contextMenus |> List.isEmpty then
                Nothing

            else
                case gunJustRightClickedAtX of
                    Just justClicked ->
                        Just justClicked

                    Nothing ->
                        memoryBefore.menuOpenOnGunAtX

        weaponMenuEntryTexts =
            if menuOpenOnGunAtX == Nothing then
                []

            else
                context.readingFromGameClient.contextMenus
                    |> List.head
                    |> Maybe.map (.entries >> List.map .text)
                    |> Maybe.withDefault []

        menuWasRead =
            weaponMenuEntryTexts |> List.isEmpty |> not

        shortRangeOffered =
            weaponMenuOffersCharge chargeNames.shortRangeAmmoName weaponMenuEntryTexts

        longRangeOffered =
            weaponMenuOffersCharge chargeNames.longRangeAmmoName weaponMenuEntryTexts

        -- The menu lists what the gun can be switched *to*, so the charge that
        -- is absent is the charge that is in it. Verified live: a weapon holding
        -- Radio M offered Multifrequency M and not Radio M.
        --
        -- Both offered means some third charge is loaded, and neither means the
        -- ship is carrying neither -- handled separately below, because that one
        -- is worth saying rather than retrying.
        chargeLoaded =
            if not menuWasRead then
                memoryBefore.chargeLoaded

            else if shortRangeOffered && not longRangeOffered then
                Just LongRangeAmmo

            else if longRangeOffered && not shortRangeOffered then
                Just ShortRangeAmmo

            else
                Nothing

        -- A weapon's menu offering neither charge means the ship carries
        -- neither, which is worth saying rather than retrying for fifty
        -- readings. The entry count keeps a half-built menu from latching that
        -- for the session: the menu observed live had seven entries, and a
        -- weapon with no loadable charge at all still has Show Info, Unload to
        -- Cargo, the two auto- toggles and Clear group, so three is below any
        -- real menu and above an empty one.
        neitherChargeCarried =
            menuWasRead
                && (ammoSwapMenuEntriesBeforeTrusted <= List.length weaponMenuEntryTexts)
                && not shortRangeOffered
                && not longRangeOffered

        freshOptimalRange =
            weaponOptimalRangeFromHover
                context.previousStepsEffects
                context.readingFromGameClient
                memoryBefore.hoverAwaitingTooltip

        optimalRangeInMeters =
            if chargeLoaded /= memoryBefore.chargeLoaded then
                -- The number belongs to the charge that was in the gun, so a
                -- different charge makes it stale. Forgetting it is what sends
                -- the bot back to read the new one, which is how the second of
                -- the two optimal ranges is ever learned.
                freshOptimalRange

            else
                case freshOptimalRange of
                    Just fresh ->
                        Just fresh

                    Nothing ->
                        memoryBefore.optimalRangeInMeters

        optimalRangeSeenLow =
            [ memoryBefore.optimalRangeSeenLow, freshOptimalRange ]
                |> List.filterMap identity
                |> List.minimum

        optimalRangeSeenHigh =
            [ memoryBefore.optimalRangeSeenHigh, freshOptimalRange ]
                |> List.filterMap identity
                |> List.maximum

        threshold =
            ammoSwapThreshold context.botSettings
                { memoryBefore
                    | optimalRangeInMeters = optimalRangeInMeters
                    , optimalRangeSeenLow = optimalRangeSeenLow
                    , optimalRangeSeenHigh = optimalRangeSeenHigh
                }

        rangeVerdict =
            case ( threshold, activeTargetDistanceInMeters context.readingFromGameClient ) of
                ( Just crossover, Just distance ) ->
                    if crossover.crossoverInMeters + crossover.deadbandInMeters < distance then
                        Just LongRangeAmmo

                    else if distance < crossover.crossoverInMeters - crossover.deadbandInMeters then
                        Just ShortRangeAmmo

                    else
                        Nothing

                _ ->
                    Nothing

        verdictIsTheSameOneAsBefore =
            (rangeVerdict /= Nothing) && (rangeVerdict == memoryBefore.rangeVerdict)

        gunsCommandedBefore =
            if verdictIsTheSameOneAsBefore then
                memoryBefore.gunsCommandedThisVerdictAtX

            else
                []

        gunsCommandedThisVerdictAtX =
            case gunJustRightClickedAtX of
                Just justClicked ->
                    if gunsCommandedBefore |> List.member justClicked then
                        gunsCommandedBefore

                    else
                        justClicked :: gunsCommandedBefore

                Nothing ->
                    gunsCommandedBefore

        everyGunVisited =
            (guns |> List.isEmpty |> not)
                && (guns |> List.all (\gun -> gunsCommandedThisVerdictAtX |> List.member gun.uiNode.totalDisplayRegion.x))

        -- The swap is done when the last gun's own menu says so: the wanted
        -- charge has gone from the list, which is the client reporting the
        -- effect rather than the bot reporting its intent.
        --
        -- A verdict that arrives with the wanted charge already loaded is
        -- satisfied on the spot, without opening a menu to find that out. This
        -- matters more than it looks: the verdict re-arms every time a target's
        -- distance wanders back out through the deadband, and without this the
        -- bot would re-open every gun's menu, mid-fight, to be told nothing had
        -- changed. The evidence is the client's own last word about what is
        -- loaded, and nothing changes it but a load the bot performed.
        verdictSatisfied =
            if not verdictIsTheSameOneAsBefore then
                (chargeLoaded /= Nothing) && (chargeLoaded == rangeVerdict)

            else if everyGunVisited && menuWasRead && (chargeLoaded == rangeVerdict) then
                True

            else
                memoryBefore.verdictSatisfied

        -- Counts only the readings a verdict has gone *unsatisfied*, which is
        -- what the give-up is about. Reset rather than held once satisfied, so
        -- that a long struggle cannot leave a count behind for the next verdict
        -- to inherit and trip over.
        rangeVerdictTicks =
            if rangeVerdict == Nothing then
                0

            else if verdictSatisfied then
                0

            else if not verdictIsTheSameOneAsBefore then
                1

            else if memoryBefore.verdictAbandoned then
                memoryBefore.rangeVerdictTicks

            else
                memoryBefore.rangeVerdictTicks + 1

        -- Whether the swap has told a gun to stop for this verdict. The step's
        -- own effects, not the module's reported state: what the bot asked for
        -- is knowable, where what the client did with it turned out not to be.
        swapJustCommandedAGunOff =
            case context.previousStepsEffects |> List.head of
                Nothing ->
                    False

                Just effects ->
                    guns |> List.any (\gun -> doEffectsClickModuleButton gun effects)

        -- Readings since the guns were first told to stop, for this verdict.
        --
        -- **Nothing about the module can stall this.** That is the entire
        -- correction from #34, and the shape it replaces is worth keeping in
        -- view: the old counter reset whenever no gun *read* as firing, so a
        -- weapon flickering between cycles reset it every other reading and it
        -- never reached its bound at all. Run 8's log shows it stuck at "1 of 8"
        -- for all eight readings it was printed, and then the next phase, which
        -- had no counter, ran for 298. Two bugs wearing one coat: a counter that
        -- could not advance, in front of a state that did not count.
        --
        -- So the only inputs here are whether the swap is still holding the
        -- guns and whether the bot has asked. It advances on every reading in
        -- between, whatever the guns say about themselves.
        --
        -- Note what is deliberately *not* a reset: the verdict changing. A
        -- target drifting back across the deadband flips short to long with the
        -- guns still switched off, and a counter that restarted there would let
        -- a flickering distance hold the ship disarmed indefinitely -- the same
        -- bug in a different coat. Only the swap letting go clears it.
        gunsSilencedTicks =
            if rangeVerdict == Nothing then
                0

            else if verdictSatisfied then
                0

            else if memoryBefore.verdictAbandoned then
                -- The swap has let go, so the fight owns the guns again and this
                -- is no longer measuring anything. Reset here and nowhere else.
                0

            else if memoryBefore.gunsSilencedTicks > 0 then
                memoryBefore.gunsSilencedTicks + 1

            else if swapJustCommandedAGunOff then
                1

            else
                0

        -- The client's own account of having thrown the load away. Recorded
        -- rather than acted on where it is read, because the entries carrying it
        -- are gone by the next reading and this is the only place that can write
        -- memory.
        --
        -- Only while a verdict is live: this wording can only be answering a
        -- load, and the ammo swap is the only thing here that loads, but a
        -- refusal with nothing outstanding belongs to whoever provoked it.
        loadRefusedByClient =
            if rangeVerdict == Nothing then
                Nothing

            else if not verdictIsTheSameOneAsBefore then
                loadRefusalFromGameLog context.readingFromGameClient

            else
                case loadRefusalFromGameLog context.readingFromGameClient of
                    Just refusal ->
                        Just refusal

                    Nothing ->
                        memoryBefore.loadRefusedByClient

        -- Abandoning is per verdict and says nothing about the next one -- see
        -- ammoSwapVerdictGiveUpTicks. The guns go back to firing the moment this
        -- is set, because the branch hands the fight on.
        verdictAbandoned =
            if not verdictIsTheSameOneAsBefore then
                False

            else if verdictSatisfied then
                False

            else if loadRefusedByClient /= Nothing then
                -- The client has said the load was discarded, so waiting for the
                -- menu to confirm it is waiting for something that cannot
                -- happen. The same outcome the bounds below reach, arrived at on
                -- the reading the client answered instead of twenty-five
                -- readings later.
                True

            else if ammoSwapSilencedGiveUpTicks < gunsSilencedTicks then
                True

            else if ammoSwapVerdictGiveUpTicks < rangeVerdictTicks then
                True

            else
                memoryBefore.verdictAbandoned

        previousStepHoveredAWeapon =
            guns |> List.any (.uiNode >> previousStepHoveredElement context.previousStepsEffects)

        hoverAwaitingTooltip =
            if previousStepHoveredAWeapon then
                True

            else if freshOptimalRange /= Nothing then
                False

            else if context.previousStepsEffects |> List.head |> Maybe.withDefault [] |> List.any effectMovesTheMouse then
                -- Something else took the mouse, so the dwell that raises the
                -- tooltip has been interrupted and there is nothing left to wait
                -- for. Forgetting that we asked is what lets the bot ask again;
                -- carrying on waiting would spend the patience below on a hover
                -- that no longer exists.
                False

            else
                memoryBefore.hoverAwaitingTooltip

        hoverUnansweredTicks =
            if freshOptimalRange /= Nothing then
                0

            else if hoverAwaitingTooltip then
                memoryBefore.hoverUnansweredTicks + 1

            else
                -- Held rather than reset, for the reason droneRecallUnansweredTicks
                -- holds past its own threshold: the counter measures how long the
                -- bot has been asking, and a reading in which it did not ask is
                -- not evidence that the client answered.
                memoryBefore.hoverUnansweredTicks

        optimalRangeGivenUp =
            memoryBefore.optimalRangeGivenUp
                || (weaponTooltipUnansweredGiveUpTicks < hoverUnansweredTicks)

        givenUp =
            case memoryBefore.givenUp of
                Just reason ->
                    Just reason

                Nothing ->
                    if neitherChargeCarried then
                        Just
                            ("the weapon's own menu offers neither '"
                                ++ chargeNames.shortRangeAmmoName
                                ++ "' nor '"
                                ++ chargeNames.longRangeAmmoName
                                ++ "', so the ship is carrying neither and there is nothing to swap between"
                            )

                    else if ammoSwapSilencedGiveUpTicks < gunsSilencedTicks then
                        Just
                            ("the guns were switched off to load and were still not back "
                                ++ String.fromInt gunsSilencedTicks
                                ++ " readings later -- a disarmed ship is worse than the wrong charge, so this will not be attempted again this session"
                            )

                    else if optimalRangeGivenUp && (threshold == Nothing) then
                        Just
                            ("no crossover distance: 'ammo-swap-range' is not set and the weapon's tooltip never appeared, so there is no distance to swap at even though the menu says which charge is loaded"
                            )

                    else
                        -- A load that does not land is *not* here. It abandons
                        -- the one verdict (`verdictAbandoned`) and the guns go
                        -- back to shooting; only the two impossibilities above
                        -- are permanent enough to switch the feature off for the
                        -- session. Issue #27 is why: the old latch fired on a
                        -- client that was refusing every load because the guns
                        -- were active, which is a condition the bot can fix
                        -- rather than a client that cannot do this at all.
                        Nothing
    in
    { chargeLoaded = chargeLoaded
    , optimalRangeInMeters = optimalRangeInMeters
    , optimalRangeSeenLow = optimalRangeSeenLow
    , optimalRangeSeenHigh = optimalRangeSeenHigh
    , rangeVerdict = rangeVerdict
    , rangeVerdictTicks = rangeVerdictTicks
    , verdictSatisfied = verdictSatisfied
    , verdictAbandoned = verdictAbandoned
    , loadRefusedByClient = loadRefusedByClient
    , gunsSilencedTicks = gunsSilencedTicks
    , gunsCommandedThisVerdictAtX = gunsCommandedThisVerdictAtX
    , menuOpenOnGunAtX = menuOpenOnGunAtX
    , hoverAwaitingTooltip = hoverAwaitingTooltip
    , hoverUnansweredTicks = hoverUnansweredTicks
    , optimalRangeGivenUp = optimalRangeGivenUp
    , givenUp = givenUp
    }


{-| Load the charge that suits how far away the current target is, or get on
with the fight.

Takes the caller's next step rather than returning a `Maybe`, so that every
branch which declines to swap can still say why in the decision log while handing
the fight on -- the shape `returnDronesToBay` was changed to after #7, where a
give-up that only spoke on one exact reading ended up never speaking at all.

Off unless both `short-range-ammo` and `long-range-ammo` are set. Discovering the
pair by reading the menu is possible now that the menu is read at all, and is
still not done: the menu lists every charge the ship carries that fits, which is
not the same as the two the operator wants alternated, and picking two of them by
guess is a swap nobody asked for. Naming both is also the only way to be sure
there *is* a pair.
-}
ensureAmmoSuitsTargetRange : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
ensureAmmoSuitsTargetRange context nextStep =
    let
        ammoSwap =
            context.memory.ammoSwap

        guns =
            weaponModuleButtonsLeftToRight context.readingFromGameClient
    in
    case ( context.eventContext.botSettings.shortRangeAmmoName, context.eventContext.botSettings.longRangeAmmoName ) of
        ( Just shortRangeAmmoName, Just longRangeAmmoName ) ->
            case ammoSwap.givenUp of
                Just reason ->
                    describeBranch
                        ("Not swapping ammo any more: " ++ reason ++ " -- keep shooting with what is loaded.")
                        nextStep

                Nothing ->
                    if
                        (guns |> List.all weaponIsFiring |> not)
                            && not (ammoSwapIsActingOnAVerdict ammoSwap)
                    then
                        -- Get the guns going first. Opening a weapon's menu takes
                        -- the mouse and a load takes a gun offline -- both are
                        -- things to do to a ship that is already shooting, not to
                        -- one that has not started.
                        --
                        -- The second clause is what stops this becoming a flap.
                        -- Once the swap is under way it switches the guns off on
                        -- purpose, and bailing out here would hand the fight back
                        -- to the branch that switches them straight on again.
                        nextStep

                    else
                        case ( guns |> List.reverse |> List.head, activeTargetDistanceInMeters context.readingFromGameClient ) of
                            ( Nothing, _ ) ->
                                nextStep

                            ( _, Nothing ) ->
                                -- No active target, or its distance reads in AU
                                -- and does not parse. Either way there is no
                                -- number to decide on, and the placeholder the
                                -- rest of the bot uses for an unparsed distance
                                -- would argue for long-range ammo every time.
                                nextStep

                            ( Just referenceGun, Just distance ) ->
                                ensureAmmoSuitsTargetRangeWithGuns context
                                    { guns = guns
                                    , referenceGun = referenceGun
                                    , distance = distance
                                    , shortRangeAmmoName = shortRangeAmmoName
                                    , longRangeAmmoName = longRangeAmmoName
                                    }
                                    nextStep

        _ ->
            nextStep


{-| Whether the swap has taken charge of the guns for a verdict it is working
on.

While this holds, the ammo path keeps control even with every weapon switched
off, because it is the thing that switched them off. It stops holding the moment
the verdict is satisfied or abandoned, and the fight then switches them back on
by its ordinary route -- there is no separate re-activation step, and there
should not be one: the branch that already knows how to start a weapon on a
target is the right owner of that, and a second one would be two controllers for
the same button.
-}
ammoSwapIsActingOnAVerdict : AmmoSwapMemory -> Bool
ammoSwapIsActingOnAVerdict ammoSwap =
    (ammoSwap.rangeVerdict /= Nothing)
        && not ammoSwap.verdictSatisfied
        && not ammoSwap.verdictAbandoned
        && (ammoSwapDistanceHoldTicks <= ammoSwap.rangeVerdictTicks)


ensureAmmoSuitsTargetRangeWithGuns :
    BotDecisionContext
    ->
        { guns : List ShipUIModuleButton
        , referenceGun : ShipUIModuleButton
        , distance : Int
        , shortRangeAmmoName : String
        , longRangeAmmoName : String
        }
    -> DecisionPathNode
    -> DecisionPathNode
ensureAmmoSuitsTargetRangeWithGuns context fight nextStep =
    let
        ammoSwap =
            context.memory.ammoSwap

        gunWithMenuOpen =
            case ammoSwap.menuOpenOnGunAtX of
                Nothing ->
                    Nothing

                Just menuGunX ->
                    fight.guns
                        |> List.filter (\gun -> gun.uiNode.totalDisplayRegion.x == menuGunX)
                        |> List.head

        openMenuEntryTexts =
            if ammoSwap.menuOpenOnGunAtX == Nothing then
                []

            else
                context.readingFromGameClient.contextMenus
                    |> List.head
                    |> Maybe.map (.entries >> List.map .text)
                    |> Maybe.withDefault []

        gunsStillToVisit =
            fight.guns
                |> List.filter
                    (\gun ->
                        ammoSwap.gunsCommandedThisVerdictAtX
                            |> List.member gun.uiNode.totalDisplayRegion.x
                            |> not
                    )

        threshold =
            ammoSwapThreshold context.eventContext.botSettings ammoSwap

        -- Reading the optimal range is a refinement now, not the mechanism, and
        -- it is only worth the held mouse while it is the only thing that can
        -- answer. With `ammo-swap-range` set it never is; with the loaded
        -- charge's range already read there is nothing to add until the charge
        -- changes; and once the client has shown it has no tooltip there is
        -- nothing left to ask.
        stillWorthReadingTheOptimalRange =
            not ammoSwap.optimalRangeGivenUp
                && (context.eventContext.botSettings.ammoSwapRangeMeters == Nothing)
                && (ammoSwap.optimalRangeInMeters == Nothing)

        describeRanges =
            "target "
                ++ String.fromInt fight.distance
                ++ " m away, crossover "
                ++ (case threshold of
                        Just crossover ->
                            String.fromInt crossover.crossoverInMeters
                                ++ " m from "
                                ++ crossover.source

                        Nothing ->
                            "unknown"
                   )

        pressEscape =
            decideActionForCurrentStep
                [ EffectOnWindow.KeyDown EffectOnWindow.vkey_ESCAPE
                , EffectOnWindow.KeyUp EffectOnWindow.vkey_ESCAPE
                ]

        idle =
            if stillWorthReadingTheOptimalRange then
                hoverWeaponForOptimalRange context fight.referenceGun

            else
                nextStep
    in
    case ammoSwap.rangeVerdict of
        Nothing ->
            idle

        Just verdict ->
            let
                wantedChargeName =
                    case verdict of
                        ShortRangeAmmo ->
                            fight.shortRangeAmmoName

                        LongRangeAmmo ->
                            fight.longRangeAmmoName

                loadTheWantedCharge gun =
                    useContextMenuCascade
                        ( "weapon module", gun.uiNode )
                        (useMenuEntryWithTextContaining wantedChargeName menuCascadeCompleted)
                        context
            in
            if ammoSwap.verdictSatisfied then
                idle

            else if ammoSwap.verdictAbandoned then
                case ammoSwap.loadRefusedByClient of
                    Just refusal ->
                        -- The client's own sentence, quoted rather than
                        -- paraphrased. The whole value of reading its log is
                        -- that an operator sees what EVE said, not what the bot
                        -- made of it.
                        describeBranch
                            ("The client refused the load. It said: \""
                                ++ refusal
                                ++ "\" -- so '"
                                ++ wantedChargeName
                                ++ "' is not going in this time. Back to shooting with what is loaded; the next change of range tries again."
                            )
                            nextStep

                    Nothing ->
                        describeBranch
                            ("Gave up on loading '"
                                ++ wantedChargeName
                                ++ "' for this target ("
                                ++ describeRanges
                                ++ ") -- back to shooting with what is loaded, rather than standing here with the guns off. The next change of range tries again."
                            )
                            nextStep

            else if ammoSwap.rangeVerdictTicks < ammoSwapDistanceHoldTicks then
                describeBranch
                    ("The range wants '"
                        ++ wantedChargeName
                        ++ "' ("
                        ++ describeRanges
                        ++ "), but only for "
                        ++ String.fromInt ammoSwap.rangeVerdictTicks
                        ++ " reading(s) -- a target dying and being replaced looks exactly like this, so wait."
                    )
                    nextStep

            else
                case gunWithMenuOpen of
                    Just gunWithMenu ->
                        if not (weaponMenuOffersCharge wantedChargeName openMenuEntryTexts) then
                            -- The menu lists what the gun can switch *to*, so a
                            -- charge missing from it is the charge already in the
                            -- gun. That is the confirmation the whole design
                            -- turns on, and it needs no tooltip.
                            describeBranch
                                ("The menu does not offer '"
                                    ++ wantedChargeName
                                    ++ "', which is the client saying this weapon already has it -- close the menu."
                                )
                                pressEscape

                        else if ammoSwap.gunsSilencedTicks < 1 then
                            -- Reading the menu is free while the guns fire;
                            -- loading is not. Close it, so the module button is
                            -- not underneath it when the next branch switches
                            -- the gun off.
                            describeBranch
                                ("The menu offers '"
                                    ++ wantedChargeName
                                    ++ "', but nothing has told this weapon to stop yet and the client refuses a load into a running weapon -- close the menu and stop the gun first."
                                )
                                pressEscape

                        else if ammoSwap.gunsSilencedTicks <= ammoSwapSilenceSettleTicks then
                            -- Settling, on a count rather than on the module's
                            -- own account of itself. See ammoSwapSilenceSettleTicks:
                            -- the ramp reading this used to wait on may never
                            -- say what it is being asked, and run 8 waited 298
                            -- readings for it.
                            describeBranch
                                ("Told this weapon to stop "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilenceSettleTicks
                                    ++ " readings ago -- let the cycle end before loading '"
                                    ++ wantedChargeName
                                    ++ "'."
                                )
                                nextStep

                        else
                            -- Loaded without checking whether the gun reads
                            -- quiet, on purpose. The client answers that
                            -- question itself: a load into a running module
                            -- comes back as a refusal in the game log, which the
                            -- bot has read since #31, and one wasted reading is
                            -- a better price than a wait that cannot end.
                            describeBranch
                                ("The menu offers '"
                                    ++ wantedChargeName
                                    ++ "', so this weapon is not carrying it, and it has had "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " reading(s) to stop -- load it. "
                                    ++ describeRanges
                                    ++ "."
                                )
                                (loadTheWantedCharge gunWithMenu)

                    Nothing ->
                        if ammoSwap.gunsSilencedTicks < 1 then
                            case fight.guns |> List.filter weaponIsFiring |> List.head of
                                Just gunStillFiring ->
                                    -- Switch it off, once. The button is a
                                    -- toggle, so the settling window in
                                    -- clickModuleButtonButWaitIfClickedInPreviousStep
                                    -- is what keeps a second press from turning
                                    -- it straight back on -- and from here on
                                    -- `gunsSilencedTicks` is non-zero, so this
                                    -- branch is not revisited for this verdict
                                    -- however the module reports itself.
                                    --
                                    -- Everything after this point is inside the
                                    -- window `ammoSwapSilencedGiveUpTicks` bounds.
                                    describeBranch
                                        ("Stop this weapon before loading '"
                                            ++ wantedChargeName
                                            ++ "' -- the client refuses to load a charge into a module that is running, and says so only in its game log."
                                        )
                                        (clickModuleButtonButWaitIfClickedInPreviousStep context gunStillFiring)

                                Nothing ->
                                    -- Nothing reads as firing, so there is
                                    -- nothing to switch off and the load can be
                                    -- tried directly. If that reading was wrong
                                    -- -- and #35 gives real reason to think it
                                    -- can be -- the refusal says so.
                                    describeBranch
                                        ("No weapon reads as firing, so open one's menu to see whether it already carries '"
                                            ++ wantedChargeName
                                            ++ "'."
                                        )
                                        (loadTheWantedCharge
                                            (gunsStillToVisit |> List.head |> Maybe.withDefault fight.referenceGun)
                                        )

                        else if ammoSwap.gunsSilencedTicks <= ammoSwapSilenceSettleTicks then
                            describeBranch
                                ("Told the guns to stop "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilenceSettleTicks
                                    ++ " readings ago -- let the cycle end before loading '"
                                    ++ wantedChargeName
                                    ++ "'."
                                )
                                nextStep

                        else
                            case gunsStillToVisit |> List.head of
                                Just gunToVisit ->
                                    describeBranch
                                        ("Open this weapon's menu to see whether it already carries '"
                                            ++ wantedChargeName
                                            ++ "'. "
                                            ++ String.fromInt (List.length gunsStillToVisit)
                                            ++ " of "
                                            ++ String.fromInt (List.length fight.guns)
                                            ++ " weapon(s) still to check. Guns off for "
                                            ++ String.fromInt ammoSwap.gunsSilencedTicks
                                            ++ " of "
                                            ++ String.fromInt ammoSwapSilencedGiveUpTicks
                                            ++ " readings."
                                        )
                                        (loadTheWantedCharge gunToVisit)

                                Nothing ->
                                    -- Every gun has been visited and the swap is
                                    -- still not confirmed, so re-open the last
                                    -- one: its menu is where the answer is, and
                                    -- the charge having vanished from it is the
                                    -- only evidence a load landed.
                                    describeBranch
                                        ("Every weapon has been told to load '"
                                            ++ wantedChargeName
                                            ++ "' -- re-open the last one's menu to see whether it took. Guns off for "
                                            ++ String.fromInt ammoSwap.gunsSilencedTicks
                                            ++ " of "
                                            ++ String.fromInt ammoSwapSilencedGiveUpTicks
                                            ++ " readings."
                                        )
                                        (loadTheWantedCharge fight.referenceGun)


{-| Rest the mouse on a weapon module until the client shows its tooltip.

Issued once and then left strictly alone. A Photon UI flyout needs uninterrupted
dwell, so this does two things that look like doing nothing and are not. It does
not re-issue the same move on the next reading -- re-gliding to the same point
resets the dwell timer before it can accumulate, which is indistinguishable from
a tooltip that never appears. And while it waits it holds the whole decision
here rather than handing the fight on, because the fight is what would move the
mouse: a click on a target or an overview row ends the dwell just as surely.

Only reached while the crossover distance is still unknown, which means only
while `ammo-swap-range` is unset, and at most until
`weaponTooltipUnansweredGiveUpTicks` readings have gone by without an answer.
Holding costs less than it reads: guns and drones already engaged keep cycling
with no further input, so a few readings of issuing nothing is a few readings of
not *changing* anything, not a ceasefire.

Holding still could in principle age a pending lock attempt past
`lockAttemptReadingsBeforeVerdict` and have a lock the bot never gave a chance
recorded as a refusal. It cannot, and the reason is worth keeping if either side
is changed: a refusal is only counted with the target bar empty at both ends of
the attempt, and this branch is only reachable with an active target. Letting the
ammo path run without one would connect them.
-}
hoverWeaponForOptimalRange : BotDecisionContext -> ShipUIModuleButton -> DecisionPathNode
hoverWeaponForOptimalRange context referenceGun =
    if context.memory.ammoSwap.hoverAwaitingTooltip then
        describeBranch
            ("Holding still for the weapon's tooltip, which is the only way to work out a crossover distance without 'ammo-swap-range' ("
                ++ (context.memory.ammoSwap.hoverUnansweredTicks |> String.fromInt)
                ++ " of "
                ++ String.fromInt weaponTooltipUnansweredGiveUpTicks
                ++ " readings) -- the mouse is already resting on it, and moving anything ends the hover."
            )
            waitForProgressInGame

    else
        describeBranch
            "Rest the mouse on a weapon to read its optimal range, which is what a crossover distance can be derived from."
            (decideActionForCurrentStep
                (EveOnline.BotFramework.mouseMoveToUIElement referenceGun.uiNode)
            )


{-| Whether this host is carrying the client's game log at all.

Worth a place on the status line because "no refusal was reported" reads exactly
the same whether the client said nothing or nothing was listening -- and those
are the two answers `gameLogEntriesSinceLastReading` keeps apart on purpose. An
operator wondering why a refusal never appeared should not have to guess which
of the two they are looking at.
-}
describeGameLogAvailability : ReadingFromGameClient -> String
describeGameLogAvailability readingFromGameClient =
    case readingFromGameClient.gameLogEntriesSinceLastReading of
        Nothing ->
            "This host is not carrying the client's game log, so a refusal cannot be seen -- only inferred from the swap not confirming."

        Just entries ->
            "Game log carried, "
                ++ String.fromInt (List.length entries)
                ++ " line(s) this reading."


{-| The ammo swap's whole state on one line, so an operator can watch the charge
the client reports rather than trust the decision log's claim that it swapped.
-}
describeAmmoSwapState : BotDecisionContext -> String
describeAmmoSwapState context =
    let
        ammoSwap =
            context.memory.ammoSwap

        describeOptional label value =
            label ++ ": " ++ (value |> Maybe.map String.fromInt |> Maybe.withDefault "unknown")

        describeAmmoRange ammoRange =
            case ammoRange of
                Nothing ->
                    "unknown"

                Just ShortRangeAmmo ->
                    "short-range"

                Just LongRangeAmmo ->
                    "long-range"
    in
    case ( context.eventContext.botSettings.shortRangeAmmoName, context.eventContext.botSettings.longRangeAmmoName ) of
        ( Just _, Just _ ) ->
            case ammoSwap.givenUp of
                Just reason ->
                    "Ammo swap: given up -- " ++ reason ++ "."

                Nothing ->
                    "Ammo swap: loaded charge reads "
                        ++ describeAmmoRange ammoSwap.chargeLoaded
                        ++ ", crossover "
                        ++ (case ammoSwapThreshold context.eventContext.botSettings ammoSwap of
                                Just crossover ->
                                    String.fromInt crossover.crossoverInMeters
                                        ++ " m (+/-"
                                        ++ String.fromInt crossover.deadbandInMeters
                                        ++ ", from "
                                        ++ crossover.source
                                        ++ ")"

                                Nothing ->
                                    "unknown"
                           )
                        ++ ", "
                        ++ describeOptional "target distance" (activeTargetDistanceInMeters context.readingFromGameClient)
                        ++ " m, wants "
                        ++ describeAmmoRange ammoSwap.rangeVerdict
                        ++ " for "
                        ++ String.fromInt ammoSwap.rangeVerdictTicks
                        ++ " reading(s)"
                        ++ (if ammoSwap.verdictSatisfied then
                                " (satisfied)"

                            else if ammoSwap.verdictAbandoned then
                                (case ammoSwap.loadRefusedByClient of
                                    Just refusal ->
                                        " (the client refused it: \"" ++ refusal ++ "\")"

                                    Nothing ->
                                        " (gave up on this one, will try again on the next change of range)"
                                )

                            else if 0 < ammoSwap.gunsSilencedTicks then
                                -- The number an operator should be watching: how
                                -- long this ship has had its guns switched off.
                                " (GUNS OFF for "
                                    ++ String.fromInt ammoSwap.gunsSilencedTicks
                                    ++ " of "
                                    ++ String.fromInt ammoSwapSilencedGiveUpTicks
                                    ++ " readings)"

                            else
                                ""
                           )
                        ++ ". Optimal range "
                        ++ describeOptional "now" ammoSwap.optimalRangeInMeters
                        ++ " m ("
                        ++ describeOptional "seen low" ammoSwap.optimalRangeSeenLow
                        ++ ", "
                        ++ describeOptional "seen high" ammoSwap.optimalRangeSeenHigh
                        ++ "), tooltip unanswered "
                        ++ String.fromInt ammoSwap.hoverUnansweredTicks
                        ++ (if ammoSwap.optimalRangeGivenUp then
                                " (given up)"

                            else
                                ""
                           )
                        ++ ". "
                        ++ describeGameLogAvailability context.readingFromGameClient

        _ ->
            "Ammo swap: off (needs both short-range-ammo and long-range-ammo)."


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

{-| Whether the client is currently offering to take this gate.

The panel carries `selectedItemActivateGate` only while the gate is in range, so
its presence answers "are we close enough?" better than any distance we could
compute -- the overview's own distance lags the ship, which is what made a
threshold unreliable here and in the loot window.

Requires the panel to be showing this gate, because the button belongs to
whatever is selected; a button read while something else is selected would
activate that instead.
-}
gateCanBeActivatedNow : BotDecisionContext -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
gateCanBeActivatedNow context entry =
    selectedItemIsOverviewEntry context entry
        && selectedItemOffersActivateGate context.readingFromGameClient


{-| Whether the panel is offering to open a gate, whoever it is showing.

The half of `gateCanBeActivatedNow` that needs no decision context, so that
`updateMemoryForNewReadingFromGame` -- which never sees a decision -- can count
the readings on which the client made the offer and the gate did not open.

-}
selectedItemOffersActivateGate : ReadingFromGameClient -> Bool
selectedItemOffersActivateGate readingFromGameClient =
    readingFromGameClient.selectedItemWindow
        |> Maybe.map (.uiNode >> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion)
        |> Maybe.withDefault []
        |> List.any
            (\node ->
                (node.uiNode |> EveOnline.ParseUserInterface.getNameFromDictEntries)
                    == Just "selectedItemActivateGate"
            )


{-| Readings of drones sitting in space before the recall is treated as not
landing at all.

Shift+R is a bare keypress: there is nothing to aim it at and nothing in the
reading that says whether the client took it. So the only evidence available is
the drones still being out.

Generous because a fight legitimately keeps drones out for a long stretch, and
the cost of hitting it early is only one click.
-}
droneRecallFocusRecoveryTicks : Int
droneRecallFocusRecoveryTicks =
    20


{-| Unanswered readings -- see `droneRecallUnansweredTicks` -- before the drones
are written off and the ship is allowed to leave without them.

This is counted from the first recall the client did not answer, *not* from the
launch. Run 1 measured it from launch and lost all ten drones in two batches of
five: drones are deliberately left out for the whole fight, so any pocket
running longer than this threshold pushed the counter past it, after which
`returnDronesToBay` declined for the rest of the session and every warp
abandoned whatever was in space. Log evidence: 91 readings between the second
launch and the next warp, no recall decision among them, and five drones gone.

Nothing on the wind-down path depends on this being small any more --
`secondsPastSessionEndBeforeGivingUpOnDocking` ends the session whether or not
the drones ever come home -- so this can afford to be the patient bound it was
always described as.
-}
droneRecallGiveUpTicks : Int
droneRecallGiveUpTicks =
    60


{-| How far back to look for the bot having asked for a recall.

More than one step, because the focus-recovery branch below alternates click,
press, click, press -- so during a recall that is being pursued every reading,
only every other step carries the keypress. Short enough that a bot which has
gone back to fighting stops counting readings against a recall it is no longer
asking for.
-}
droneRecallAskedLookbackSteps : Int
droneRecallAskedLookbackSteps =
    3


dronesInSpaceCount : ReadingFromGameClient -> Int
dronesInSpaceCount readingFromGameClient =
    readingFromGameClient.dronesWindow
        |> Maybe.andThen .droneGroupInSpace
        |> Maybe.andThen (.header >> .quantityFromTitle)
        |> Maybe.map .current
        |> Maybe.withDefault 0


dronesAreInSpace : ReadingFromGameClient -> Bool
dronesAreInSpace readingFromGameClient =
    0 < dronesInSpaceCount readingFromGameClient


{-| Whether one of the last few steps pressed Shift+R at the drones.

`vkey_R` is used for nothing else in this bot, so the keypress alone identifies
the recall.
-}
recentStepAskedForDroneRecall : List (List EffectOnWindow.EffectOnWindowStruct) -> Bool
recentStepAskedForDroneRecall previousStepsEffects =
    previousStepsEffects
        |> List.take droneRecallAskedLookbackSteps
        |> List.any (List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_R))


{-| Get the drones in, and say what happened when it stops trying.

Takes what to do once there is nothing to recall rather than returning a
`Maybe`, so the branch that abandons the drones can still name itself in the
decision log while handing the step on. That branch previously returned nothing
at all, and only a separate branch testing the counter for *equality* with the
threshold ever said anything -- so the message landed only if the ship happened
to be warping on the single reading where the counter hit 60 exactly. In run 1
it never did: the give-up engaged mid-fight, silently, and the bot reported
nothing wrong while having disabled its own drone recall for the rest of the
session.
-}
returnDronesToBay : BotDecisionContext -> DecisionPathNode -> DecisionPathNode
returnDronesToBay context ifNothingToRecall =
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

                else if droneRecallGiveUpTicks < context.memory.droneRecallUnansweredTicks then
                    -- Stop asking, and go on with whatever the caller wanted to
                    -- do -- in the wind-down path that is docking, so giving up
                    -- ends the session with drones abandoned instead of never
                    -- ending at all. Run 118 held that path open for 150
                    -- readings and overran its session by five minutes, which
                    -- cost the whole remainder of the run; a set of drones does
                    -- not.
                    --
                    -- Said every time it declines, not once: an operator
                    -- reading the log has to be able to see that the ship is
                    -- leaving without its drones on purpose.
                    Just
                        (describeBranch
                            ("Drones have not answered "
                                ++ String.fromInt context.memory.droneRecallUnansweredTicks
                                ++ " readings of recall and will not come back -- leave without them so the ship can move on."
                            )
                            ifNothingToRecall
                        )

                else if
                    (droneRecallFocusRecoveryTicks < context.memory.dronesInSpaceTicks)
                        && not (previousStepClickedMouse context)
                then
                    -- Shift+R is a bare keypress with nothing to aim at, so it
                    -- does nothing at all when the client is not taking
                    -- keyboard input -- and nothing in the reading says so. The
                    -- decision looks identical whether the key landed or was
                    -- swallowed, which is how run 118 pressed it 150 times
                    -- while the drones sat in space.
                    --
                    -- Clicking inside the client first is the documented remedy
                    -- for exactly this: a window that ignored Ctrl+W took it
                    -- immediately after its title bar was clicked. The drone
                    -- group header is a real, addressable target inside the
                    -- window we are already acting on, and clicking it does
                    -- nothing but move focus.
                    --
                    -- Gated on not having just clicked, so this alternates
                    -- click, press, click, press rather than clicking forever.
                    Just
                        (describeBranch
                            "Drones are not coming back -- click the drones window to put keyboard focus back in the client, then press again."
                            (clickUiElement droneGroupInLocalSpace.header.uiNode)
                        )

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
        |> Maybe.withDefault ifNothingToRecall


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
                -- The panel is showing the right object but not the button we
                -- want. That is normal for a reading or two while the panel
                -- catches up, and never normal for long: these buttons appear
                -- with the selection, or depend on range, in which case waiting
                -- cannot produce them and something has to close the distance.
                --
                -- Bounded because the not-progressing alarm does not reach here.
                -- That one fires from the bottom of the decision tree, and this
                -- branch is several levels above it -- run 127 sat here for
                -- 11,964 decisions without tripping anything at all.
                if nothingToDoTicksBeforeCryingStuck < context.memory.nothingToDoTicks then
                    describeBranch
                        (description
                            ++ " -- the panel still offers no '"
                            ++ buttonName
                            ++ "' and the mission has not moved in a long time."
                        )
                        askForHelpToGetUnstuck

                else
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
                |> List.sortBy overviewEntryDistanceOrFarInMeters

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
            lockRangeThresholdInMeters context

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
        approachTheObject : String -> DecisionPathNode
        approachTheObject reason =
            if selectedItemIsOverviewEntry context overviewEntry then
                case selectedItemButtonNamed context "selectedItemApproach" of
                    Just approachButton ->
                        describeBranch
                            (reason ++ " Approach from the selected-item panel.")
                            (clickUiElement approachButton)

                    Nothing ->
                        describeBranch
                            (reason ++ " The selected-item panel offers no Approach.")
                            waitForProgressInGame

            else
                describeBranch
                    (reason ++ " Select it so the panel offers Approach.")
                    (clickUiElement overviewEntry.uiNode)
    in
    case overviewEntry.objectDistanceInMeters of
        Ok distanceInMeters ->
            if distanceInMeters <= targetingRange then
                if overviewEntry.commonIndications.targetedByMe || overviewEntry.commonIndications.targeting then
                    if lockAttemptIsSpent context overviewEntry then
                        -- The bound the wait below used to lack entirely: it
                        -- said "wait for completion" with nothing deciding when
                        -- the wait was over, so a lock the client accepted and
                        -- never finished would hold the ship still for the rest
                        -- of the session -- the same unbounded-wait shape as the
                        -- drone recall in #7, and one stall_watch reports as
                        -- circling rather than as a fault.
                        --
                        -- Worth knowing that both of today's callers filter
                        -- targeted and targeting rows out of their candidates
                        -- (see `overviewEntriesToLock`), so neither can reach
                        -- the wait as the tree stands. The bound is here anyway
                        -- because nothing in the function's signature says so,
                        -- and a caller that stops filtering would reinstate an
                        -- unbounded wait without touching this file's logic.
                        --
                        -- Approaching is the move because range is the most
                        -- likely reason a lock does not land, and closing
                        -- distance is safe whatever the real reason was.
                        describeBranch
                            ("Locking '"
                                ++ (overviewEntry.objectName |> Maybe.withDefault "the target")
                                ++ "' has not completed in "
                                ++ (lockAttemptReadingsBeforeVerdict |> String.fromInt)
                                ++ " readings -- stop waiting for it."
                            )
                            (approachTheObject
                                ("Object is "
                                    ++ (distanceInMeters |> String.fromInt)
                                    ++ " m away and the lock has not landed."
                                )
                            )

                    else
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
                approachTheObject
                    ("Object is not in range (" ++ (distanceInMeters |> String.fromInt) ++ " m away).")

        Err error ->
            describeBranch ("Failed to read the distance: " ++ error) askForHelpToGetUnstuck


{-| How many readings a lock the bot asked for gets to land before the outcome
is called.

Generous, because a legitimate lock is not instant -- a big ship locking a
small one takes seconds, and a reading is a couple of seconds -- and calling a
slow lock a refusal would teach the bot a range that is too short and make it
fly at rats it could have shot. A refusal, by contrast, is immediate: the
client answers an out-of-range lock at once and nothing about the row ever
changes, so waiting longer than necessary costs only how quickly the bounds
converge, never their correctness.
-}
lockAttemptReadingsBeforeVerdict : Int
lockAttemptReadingsBeforeVerdict =
    8


{-| Whether the lock the bot asked for on this row has run out its readings.

Stays true while the row is still there and still unanswered, because
`updateLockRangeLearning` holds a spent attempt at the bound rather than
dropping it. A verdict that moved a bound is announced once -- the bound is
monotone, so a second verdict on the same evidence moves nothing and says
nothing -- but the branch that stops waiting has to keep firing for as long as
there is a wait to stop.
-}
lockAttemptIsSpent : BotDecisionContext -> OverviewWindowEntry -> Bool
lockAttemptIsSpent context overviewEntry =
    case ( context.memory.lockAttempt, overviewEntryLockHandle (allOverviewEntries context.readingFromGameClient) overviewEntry ) of
        ( Just attempt, Just handle ) ->
            (attempt.handle == handle) && (lockAttemptReadingsBeforeVerdict <= attempt.readingsWaited)

        _ ->
            False


{-| The distance at which the bot switches from locking to approaching.

The `targeting-range` setting is a guess about the ship, and a wrong one is
costly both ways: too low and the bot flies at rats it could simply shoot, too
high and it spends readings asking for locks the client will never grant. The
client answers this question every time it accepts or refuses a lock, so the
setting is treated as a starting value and clamped into the interval the
client's own answers have established -- `[lockProvenAtMeters,
lockRefusedAtMeters)`, the same shape as the self-calibrated UI scale the host
derives per session rather than assuming.

With no evidence yet both bounds are `Nothing` and this is exactly the setting,
so nothing changes until something is learned. When the two contradict each
other -- possible after a refit, since the bounds are not reset mid-session --
the proven distance wins: a lock that completed is unambiguous evidence, where
a refusal is an inference from several conditions holding at once.
-}
lockRangeThresholdInMeters : BotDecisionContext -> Int
lockRangeThresholdInMeters context =
    let
        fromSetting : Int
        fromSetting =
            context.eventContext.botSettings.targetingRangeMeters

        loweredByRefusal : Int
        loweredByRefusal =
            case context.memory.lockRefusedAtMeters of
                Nothing ->
                    fromSetting

                Just refusedAt ->
                    min fromSetting (refusedAt - 1)
    in
    case context.memory.lockProvenAtMeters of
        Nothing ->
            loweredByRefusal

        Just provenAt ->
            max provenAt loweredByRefusal


allOverviewEntries : ReadingFromGameClient -> List OverviewWindowEntry
allOverviewEntries readingFromGameClient =
    readingFromGameClient.overviewWindows |> List.concatMap .entries


{-| A handle on an overview row that survives to the next reading, or nothing
when this row cannot be told apart from another.

Screen position answers "what did that click hit", but it cannot answer "is
this the same object as last reading": the overview re-sorts and virtualises,
so a position is about a row, not about an object, and matching a lock outcome
to the wrong object is exactly the mistake that would teach the bot a wrong
range. EVE's own `itemID` is the right answer where the row carries one.

Where it does not, the row's name is used, but only when no other row in the
overview shares it -- one of five identical rats says nothing about which one
the client answered. A pocket of same-named rats therefore yields no evidence
at all, which is the correct outcome rather than a guess.
-}
overviewEntryLockHandle : List OverviewWindowEntry -> OverviewWindowEntry -> Maybe String
overviewEntryLockHandle allEntries entry =
    case entry.objectItemID of
        Just itemID ->
            Just ("id:" ++ itemID)

        Nothing ->
            case entry.objectName of
                Nothing ->
                    Nothing

                Just name ->
                    if (allEntries |> List.filter (\other -> other.objectName == Just name) |> List.length) == 1 then
                        Just ("name:" ++ name)

                    else
                        Nothing


{-| The screen point a lock click went to, from the effects of one step.

The lock chord is Ctrl held over a plain left click
(`lockTargetFromOverviewEntry`), and it is the only place in this bot that
presses Ctrl without Shift -- `ctrlShiftClickUiElement`, the unlock, holds
both. So the modifiers alone identify the gesture, and the `MouseMoveTo` that
travels with every click carries where it went.

Reading the attempt out of the effects rather than out of the decision is not a
detour: `updateMemoryForNewReadingFromGame` is the only place that can write
memory, and it sees the previous steps' effects but not the decision that
produced them.
-}
lockClickLocationFromStepEffects : List EffectOnWindow.EffectOnWindowStruct -> Maybe EffectOnWindow.Location2d
lockClickLocationFromStepEffects effects =
    if
        (effects |> List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL))
            && not (effects |> List.member (EffectOnWindow.KeyDown EffectOnWindow.vkey_SHIFT))
    then
        effects
            |> List.filterMap
                (\effect ->
                    case effect of
                        EffectOnWindow.MouseMoveTo location ->
                            Just location

                        _ ->
                            Nothing
                )
            |> List.head

    else
        Nothing


locationIsInDisplayRegion : EffectOnWindow.Location2d -> EveOnline.ParseUserInterface.DisplayRegion -> Bool
locationIsInDisplayRegion location region =
    (region.x <= location.x)
        && (location.x < region.x + region.width)
        && (region.y <= location.y)
        && (location.y < region.y + region.height)


{-| What the two learned bounds and the pending attempt look like after this
reading.

Returned as one record rather than written field by field, so the whole of the
rule lives in one place and `updateMemoryForNewReadingFromGame` gains four
lines rather than four blocks that would each have to re-derive the others.
-}
type alias LockRangeLearning =
    { attempt : Maybe LockAttempt
    , provenAtMeters : Maybe Int
    , refusedAtMeters : Maybe Int
    , change : Maybe String
    }


{-| Move the lock-range bounds on what the client has just answered.

Two values, each moving in one direction only, so no oscillation is possible:
`lockProvenAtMeters` is the greatest distance at which a lock has succeeded and
only rises, `lockRefusedAtMeters` the smallest distance at which one has
provably failed and only falls.

Success is unambiguous -- a row that reads `targetedByMe` or `targeting` is the
client having accepted, and nothing else makes a row read that way. Failure is
not, which is why it takes all of the following at once:

  - the attempt has had `lockAttemptReadingsBeforeVerdict` readings to land, so
    a merely slow lock is not read as a refused one;
  - the row is still in the overview and still `_display`ed, so the object did
    not die and we are not looking at a different object recycled into that
    row;
  - the row still does not read as targeted or targeting;
  - and the target bar was empty at both ends of the attempt, which covers both
    "the count of locked targets did not go up" and "the ship had a slot to
    lock into".

That last one is what separates "too far" from "no free slot". An empty target
bar is the only thing a reading can say that *proves* a slot was free -- the
client's maximum is not in the reading at all, and "another target locked in
this engagement" does not prove it either, since locking the last one is
precisely what fills the ship up. Without this condition the number would
ratchet down every time the ship simply reached its limit. The price is that
only the first lock of an engagement can ever teach a refusal, which is also
the case that costs the most: everything on the grid out of reach, and the bot
asking for a lock it will never get, reading after reading.

The bot's own `attack-object` settings are not visible from here, so this does
not try to work out whether the row *should* have been locked. It only follows
the click the bot actually made, which also keeps it out of the way of whatever
the candidate selection in `decideActionInCombat` grows into.

The bounds are not reset within a session: `BotMemory` starts fresh with each
one, and the ship does not change mid-session in the way this bot flies.
-}
updateLockRangeLearning : UpdateMemoryContext BotSettings -> BotMemory -> LockRangeLearning
updateLockRangeLearning context botMemoryBefore =
    let
        entries : List OverviewWindowEntry
        entries =
            allOverviewEntries context.readingFromGameClient

        targetsCount : Int
        targetsCount =
            context.readingFromGameClient.targets |> List.length

        unchanged : LockRangeLearning
        unchanged =
            { attempt = botMemoryBefore.lockAttempt
            , provenAtMeters = botMemoryBefore.lockProvenAtMeters
            , refusedAtMeters = botMemoryBefore.lockRefusedAtMeters
            , change = Nothing
            }

        -- Nothing can be locked in warp or from inside a station, so an attempt
        -- that runs into either is abandoned rather than judged. The bot cannot
        -- *start* one there -- combat is gated on not warping in
        -- `decideActionWhenInSpace` -- but it can be halfway through one when
        -- the ship runs away from low health, and a lock nobody could have
        -- granted must not read as a lock the ship was too far away for.
        shipCannotLock : Bool
        shipCannotLock =
            case context.readingFromGameClient.shipUI of
                Nothing ->
                    True

                Just shipUI ->
                    shipUIIndicatesShipIsWarpingOrJumping shipUI

        -- The row the step just dispatched aimed its lock click at, if it did.
        -- Resolved by screen position against this reading, which is a reading
        -- later than the one the click was decided on -- and that is the right
        -- way round rather than a compromise: the client acted on whatever was
        -- rendered at that point, so if the overview re-sorted in between, the
        -- row found here is the row the click actually hit. Only rendered rows
        -- are considered, for the reason the whole overview section of CLAUDE.md
        -- exists: a hidden row's region belongs to whatever was recycled into
        -- it.
        entryJustClicked : Maybe OverviewWindowEntry
        entryJustClicked =
            context.previousStepsEffects
                |> List.head
                |> Maybe.andThen lockClickLocationFromStepEffects
                |> Maybe.andThen
                    (\location ->
                        entries
                            |> List.filter overviewEntryIsDisplayed
                            |> List.filter (\entry -> locationIsInDisplayRegion location entry.uiNode.totalDisplayRegion)
                            |> List.head
                    )

        attemptAfterClick : Maybe LockAttempt
        attemptAfterClick =
            case entryJustClicked of
                Nothing ->
                    botMemoryBefore.lockAttempt

                Just entry ->
                    case ( overviewEntryLockHandle entries entry, entry.objectDistanceInMeters ) of
                        ( Just handle, Ok distanceInMeters ) ->
                            case botMemoryBefore.lockAttempt of
                                Just pending ->
                                    if pending.handle == handle then
                                        -- The bot asking again for the same row
                                        -- is the same attempt, not a new one.
                                        Just pending

                                    else
                                        -- It has moved on to another row. The
                                        -- old attempt is abandoned rather than
                                        -- judged: nobody is waiting on it.
                                        Just
                                            { handle = handle
                                            , distanceInMeters = distanceInMeters
                                            , targetsCount = targetsCount
                                            , readingsWaited = 0
                                            }

                                Nothing ->
                                    Just
                                        { handle = handle
                                        , distanceInMeters = distanceInMeters
                                        , targetsCount = targetsCount
                                        , readingsWaited = 0
                                        }

                        _ ->
                            botMemoryBefore.lockAttempt
    in
    case attemptAfterClick of
        Nothing ->
            unchanged

        Just attempt ->
            let
                entryNow : Maybe OverviewWindowEntry
                entryNow =
                    if shipCannotLock then
                        Nothing

                    else
                        entries
                            |> List.filter overviewEntryIsDisplayed
                            |> List.filter (\entry -> overviewEntryLockHandle entries entry == Just attempt.handle)
                            |> List.head
            in
            case entryNow of
                Nothing ->
                    -- The row is gone or is no longer rendered, or the ship
                    -- cannot lock anything just now. It may have died, or
                    -- scrolled out of view, or the overview may have re-sorted
                    -- -- none of which says anything about range.
                    { unchanged | attempt = Nothing }

                Just entry ->
                    let
                        -- Held at the bound rather than allowed to run on, for
                        -- the same reason the drone give-up latches: the number
                        -- is shown to an operator, and one that climbs forever
                        -- while nothing is waiting on it reads as a fault.
                        attemptCarried : Maybe LockAttempt
                        attemptCarried =
                            Just
                                { attempt
                                    | readingsWaited =
                                        min lockAttemptReadingsBeforeVerdict (attempt.readingsWaited + 1)
                                }

                        -- The distance a bound moves to lies somewhere between
                        -- the reading the attempt started on and this one. Each
                        -- bound takes the end that makes the weaker claim -- the
                        -- smaller distance for the one that only rises, the
                        -- larger for the one that only falls -- so neither is
                        -- ever moved further than the evidence reaches.
                        distanceNow : Int
                        distanceNow =
                            entry.objectDistanceInMeters |> Result.withDefault attempt.distanceInMeters
                    in
                    if overviewEntryIsTargetedOrTargeting entry then
                        let
                            provenAt : Int
                            provenAt =
                                min attempt.distanceInMeters distanceNow

                            -- A completed lock ends the attempt. One still
                            -- spooling up does not: `targeting` is the client
                            -- having accepted the request, not having finished
                            -- it, and a lock that is accepted and never finishes
                            -- is exactly the wait this bound exists to end.
                            attemptAfter : Maybe LockAttempt
                            attemptAfter =
                                if entry.commonIndications.targetedByMe then
                                    Nothing

                                else
                                    attemptCarried
                        in
                        if provenAt > (botMemoryBefore.lockProvenAtMeters |> Maybe.withDefault 0) then
                            { attempt = attemptAfter
                            , provenAtMeters = Just provenAt
                            , refusedAtMeters = botMemoryBefore.lockRefusedAtMeters
                            , change =
                                Just
                                    ("Learned lock range: the client accepted a lock at "
                                        ++ (provenAt |> String.fromInt)
                                        ++ " m, further than anything locked before -- lock-proven-at rises from "
                                        ++ (botMemoryBefore.lockProvenAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "unset")
                                        ++ " to "
                                        ++ (provenAt |> String.fromInt)
                                        ++ " m."
                                    )
                            }

                        else
                            { unchanged | attempt = attemptAfter }

                    else if attempt.readingsWaited < lockAttemptReadingsBeforeVerdict then
                        { unchanged | attempt = attemptCarried }

                    else if (attempt.targetsCount /= 0) || (targetsCount /= 0) then
                        -- The ship held a locked target at one end of the
                        -- attempt or the other, so it may simply have had no free
                        -- slot -- and it may equally have locked something else
                        -- while this one was waiting. An empty target bar at both
                        -- ends is the one reading that rules out both at once,
                        -- and only then is a lock that never landed evidence
                        -- about range rather than about capacity.
                        { unchanged | attempt = attemptCarried }

                    else
                        let
                            refusedAt : Int
                            refusedAt =
                                max attempt.distanceInMeters distanceNow
                        in
                        if refusedAt < (botMemoryBefore.lockRefusedAtMeters |> Maybe.withDefault (refusedAt + 1)) then
                            { attempt = attemptCarried
                            , provenAtMeters = botMemoryBefore.lockProvenAtMeters
                            , refusedAtMeters = Just refusedAt
                            , change =
                                Just
                                    ("Learned lock range: '"
                                        ++ (entry.objectName |> Maybe.withDefault "a target")
                                        ++ "' at "
                                        ++ (refusedAt |> String.fromInt)
                                        ++ " m did not lock in "
                                        ++ (lockAttemptReadingsBeforeVerdict |> String.fromInt)
                                        ++ " readings with the target bar empty throughout -- lock-refused-at falls from "
                                        ++ (botMemoryBefore.lockRefusedAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "unset")
                                        ++ " to "
                                        ++ (refusedAt |> String.fromInt)
                                        ++ " m."
                                    )
                            }

                        else
                            -- The verdict stands, but the bound is already at
                            -- least this tight, so nothing moves and nothing is
                            -- said. That is what keeps the log line one per
                            -- change rather than one per reading, with no
                            -- separate "already reported" flag to get wrong.
                            { unchanged | attempt = attemptCarried }


{-| The lock-range bounds, for the status line.

Continuous rather than once-per-change, unlike the decision-log line: a number
the bot adjusts for itself is worth being able to read at any moment, not only
on the reading it moved. The pending attempt is here too, because a bot that
keeps clicking a lock it will never get shows up as an attempt sitting at the
verdict count long before either bound has anything to say.
-}
describeLockRange : BotDecisionContext -> String
describeLockRange context =
    "Lock range: "
        ++ (lockRangeThresholdInMeters context |> String.fromInt)
        ++ " m (setting "
        ++ (context.eventContext.botSettings.targetingRangeMeters |> String.fromInt)
        ++ ", proven "
        ++ (context.memory.lockProvenAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ", refused "
        ++ (context.memory.lockRefusedAtMeters |> Maybe.map String.fromInt |> Maybe.withDefault "-")
        ++ ", attempt "
        ++ (context.memory.lockAttempt
                |> Maybe.map (\attempt -> String.fromInt attempt.distanceInMeters ++ " m for " ++ String.fromInt attempt.readingsWaited ++ " readings")
                |> Maybe.withDefault "none"
           )
        ++ ")."





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
    , unlootableWreckIds = []
    , lootAllRefusedTicks = 0
    , lootWindowOutOfRangeTicks = 0
    , dronesInSpaceTicks = 0
    , dronesInSpaceCount = 0
    , droneRecallUnansweredTicks = 0
    , dockedWithCargoWantedTicks = 0
    , nothingToDoTicks = 0
    , lastObjectiveText = ""
    , gateWithinReachTicks = 0
    , gateLockedForWantOfAnItem = Nothing
    , siteAdmitsThisShip = Nothing
    , clearingNotRequired = False
    , agentConversationWithoutTrackerTicks = 0
    , keepAtRangeUnconfirmedTicks = 0
    , orbitUnconfirmedTicks = 0
    , readingsCount = 0
    , lowestShieldPercentSinceHealthy = 100
    , lowestArmorPercentSinceHealthy = 100
    , incomingDamage =
        { samples = []
        , hostCarriesTheChannel = False
        , lastAttacker = Nothing
        , retreating = False
        }
    , droneBayOpenedFromShipCard = False
    , droneBayWillTakeNoMore = False
    , droneRestockLooksWithRoom = 0
    , droneRestockDragsDispatched = 0
    , droneBayEmptyLastSeen = Nothing
    , shipLoss = Nothing
    , shipUIWithoutModuleButtonsReadings = 0
    , lockAttempt = Nothing
    , lockProvenAtMeters = Nothing
    , lockRefusedAtMeters = Nothing
    , lockRangeLastChange = Nothing
    , ammoSwap = initAmmoSwapMemory
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
                ++ " "
                ++ describeTopRowModuleDictState readingFromGameClient

        describeCurrentReading =
            case readingFromGameClient.shipUI of
                Nothing ->
                    [ "I do not see the ship UI. Looks like we are docked." ]

                Just shipUI ->
                    let
                        -- The raw gauge value is reported alongside "(not a
                        -- believable reading)" rather than instead of it,
                        -- because the raw value is what an operator sees and
                        -- reasons about. Issue #32 was filed partly on this
                        -- line printing "Shield: 385%" -- which the retreat
                        -- guard had already rejected and never acted on, while
                        -- the log gave every appearance that it had.
                        describeHitpoint name value =
                            name
                                ++ ": "
                                ++ (value |> String.fromInt)
                                ++ "%"
                                ++ (case plausibleHitpointsPercent value of
                                        Nothing ->
                                            " (not a believable reading -- ignored by the retreat guard)"

                                        Just _ ->
                                            ""
                                   )

                        describeShip =
                            describeHitpoint "Shield" shipUI.hitpointsPercent.shield
                                ++ "  "
                                ++ describeHitpoint "Armor" shipUI.hitpointsPercent.armor
                                ++ ". "
                                ++ describeIncomingDamage context

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
                                        ++ ". Out for "
                                        ++ (context.memory.dronesInSpaceTicks |> String.fromInt)
                                        ++ " readings, unanswered recall for "
                                        ++ (context.memory.droneRecallUnansweredTicks |> String.fromInt)
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
                    , [ describeRatsInOverview, describeCurrentTarget, describeLockRange context ]
                    , describeAccelerationGate context
                    , [ describeOverviewIndicationHints readingFromGameClient ]
                    , [ describeAmmoSwapState context ]
                    ]
                        |> List.map (String.join " ")
    in
    [ [ describePerformance ]
    , [ describeMenuAndSettlingCounters ]
    , [ describeHomeStation context ]
    , [ describeShipLoss context ]
    , describeCurrentReading
    ]
        |> List.concat
        |> String.join "\n"


{-| What the gate branch can see, and what it has decided about it.

Empty on a reading with no acceleration gate on the overview, which is most of
them; a gate branch with nothing to act on has nothing to report.

This exists because `activateAccelerationGateIfPresent`'s "the gate refuses this
ship" answer is a `Nothing` -- deliberately, so the caller's own fallbacks get
their turn -- and a `Nothing` cannot carry a decision line. Run 10 is what that
costs unreported: the branch gave up on a gate 32 m away and the log said only
"nothing to fight and no travel step offered", 1,325 times. The counter and the
verdict are named here every reading instead, so the give-up is visible while it
is happening rather than reconstructable afterwards.

The gate count is carried for its own reason. Two gates on one grid at very
different ranges is a real configuration, and the decision log alone could not
distinguish it from one gate.

-}
describeAccelerationGate : BotDecisionContext -> List String
describeAccelerationGate context =
    case accelerationGatesOnOverview context.readingFromGameClient of
        [] ->
            []

        gates ->
            [ "Acceleration gates on the overview: "
                ++ (gates
                        |> List.map
                            (\gate ->
                                (gate.objectName |> Maybe.withDefault "unnamed")
                                    ++ " at "
                                    ++ String.fromInt (overviewEntryDistanceOrFarInMeters gate)
                                    ++ " m"
                            )
                        |> String.join ", "
                   )
                ++ ". Offered and not opened for "
                ++ String.fromInt context.memory.gateWithinReachTicks
                ++ " of "
                ++ String.fromInt gateRefusesThisShipTicks
                ++ " readings"
                ++ (if gateRefusesThisShipTicks < context.memory.gateWithinReachTicks then
                        " -- the gate branch has given up and is declining to act."

                    else
                        "."
                   )
                ++ (case context.memory.gateLockedForWantOfAnItem of
                        Just clientSentence ->
                            " The client says it is locked: \""
                                ++ clientSentence
                                ++ "\" -- looking for '"
                                ++ (gateKeyWanted context |> Maybe.withDefault "nothing I could name")
                                ++ "'."

                        Nothing ->
                            ""
                   )
            ]


{-| Whether the bot thinks it still has a ship, on every reading rather than only
once it does not.

Carried continuously for the same reason `describeHomeStation` is: both inputs
are otherwise invisible. Whether the host is carrying the game log at all decides
whether the first of the two signals can ever fire, and "no capsule refusal was
seen" reads identically whether the client was silent or nothing was listening --
the distinction #30's `Maybe` exists to keep. The module counter shows the second
signal counting up, so a verdict that is about to arrive is visible before it
does rather than only in hindsight.

-}
describeShipLoss : BotDecisionContext -> String
describeShipLoss context =
    case context.memory.shipLoss of
        Just shipLoss ->
            "SHIP LOST: "
                ++ shipLoss.reason
                ++ " -- recovering the pod, "
                ++ String.fromInt shipLoss.readingsSince
                ++ " of "
                ++ String.fromInt podRecoveryGiveUpReadings
                ++ " readings spent."

        Nothing ->
            "Ship: intact as far as this reading can tell (no-module readings "
                ++ String.fromInt context.memory.shipUIWithoutModuleButtonsReadings
                ++ " of "
                ++ String.fromInt shipLossReadingsWithoutModulesBeforeVerdict
                ++ "). "
                ++ (case context.readingFromGameClient.gameLogEntriesSinceLastReading of
                        Nothing ->
                            "This host is not carrying the client's game log, so the capsule refusal cannot be seen at all and the module count is the only signal left."

                        Just _ ->
                            "The game log is carried, so the capsule refusal would be seen."
                   )


{-| The home station and whether the bot currently means to go there.

Carried continuously rather than only while the trip runs, because the two
inputs that decide it -- the setting and what the last reading that could see
the drone bay said -- are both invisible otherwise, and "the trip never
started" and "the trip finished" look identical in a decision log.
-}
describeHomeStation : BotDecisionContext -> String
describeHomeStation context =
    case context.eventContext.botSettings.homeStationName of
        Nothing ->
            "Home station: not set."

        Just stationName ->
            "Home station: '"
                ++ stationName
                ++ "' (drone bay last seen "
                ++ (case context.memory.droneBayEmptyLastSeen of
                        Nothing ->
                            "never -- no reading has shown the drones window yet"

                        Just True ->
                            "empty"

                        Just False ->
                            "stocked"
                   )
                ++ (case dockedAtHomeStation context stationName of
                        Just True ->
                            ", docked there"

                        Just False ->
                            ", docked elsewhere"

                        Nothing ->
                            ""
                   )
                ++ ")."


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


{-| The hint text behind the little icons on the right of each overview row.

Reported rather than acted on, and here for one specific reason: issue #40 says
run 10's two frigates showed "Pilot is webifying me", and **a webifier that
applies no damage produces no combat-log line at all**, so the attacker set in
`namesOfRecentAttackers` cannot see it. That case is not covered by this change
and this line is what would let it be.

The parser has carried `rightAlignedIconsHints` all along and
`commonIndications` reads exactly two literals out of it -- "is jamming me" and
"is warp disrupting me" -- both inherited from upstream. The webifier's literal
is not among them, and **it appears nowhere in the ten recorded runs**, because
nothing has ever printed these hints. Guessing at the string and matching it
would be a guard whose premise no evidence supports, which is how this repo
gets guards that quietly never fire. Printing them instead costs one status
line and turns the next run into the evidence a follow-up can be built on.

Capped and deduplicated: distinct strings across rendered rows only, since an
undisplayed row's contents belong to whatever was recycled into its place.
-}
describeOverviewIndicationHints : ReadingFromGameClient -> String
describeOverviewIndicationHints readingFromGameClient =
    case
        readingFromGameClient.overviewWindows
            |> List.concatMap .entries
            |> List.filter overviewEntryIsDisplayed
            |> List.concatMap .rightAlignedIconsHints
            |> Common.Basics.listUnique
            |> List.take 8
    of
        [] ->
            "Overview indications: none on any rendered row."

        hints ->
            "Overview indications: "
                ++ (hints |> List.map (\hint -> "'" ++ hint ++ "'") |> String.join ", ")
                ++ "."


{-| Whether to shoot this overview entry. Rats are recognised by their icon
colour, but some missions require destroying a structure -- a "Drone Silo" and
other Large Collidable Objects -- and those are neutral objects with no
hostile colouring at all, so no colour test will ever match them. They have to
be named explicitly via the `attack-object` setting.

Note the structure must also be *visible*: Large Collidable Objects are off by
default in the overview's type filters, and the bot can only act on what the
overview shows it.

The third disjunct is issue #40's: whatever the client says has been shooting
this ship. The first two require someone to have predicted the object -- the
sprite palette to cover it, or an operator to have named it -- and when both
miss, the failure is silent in the worst available direction: the bot reports
"nothing to fight" while its armour drains. This one is not a prediction. It is
the client's own statement that the object hit us, and it needs no
configuration. See `namesOfRecentAttackers`.

**This widens the set; it does not reorder it.** An entry that qualifies only
because it shot us enters the same list at its own distance rank and is subject
to every guard the other two are: `overviewEntryDistanceIsOnGrid` below (so an
AU distance is still excluded), `overviewEntryIsDisplayed` at the lock site (so
a virtualised row is still never clicked), and the scrambler-first sort in
`decideActionInCombat` (so being unable to *leave* still outranks being shot).
When the colour rule and this one agree they produce one entry, not two, and
nothing downstream can tell which disjunct matched. The one place that can, and
must, is `isObjectToAttackByName` -- see the note there.
-}
shouldAttackOverviewEntry : ObjectNamesToAttack -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
shouldAttackOverviewEntry namesToAttack overviewEntry =
    (iconSpriteHasColorOfRat overviewEntry
        || isObjectToAttackFromObjective namesToAttack.fromObjective overviewEntry
        || isObjectToAttackFromSettings namesToAttack.fromSettings overviewEntry
        || isObjectShootingAtUs namesToAttack.fromIncomingDamage overviewEntry
    )
        && overviewEntryDistanceIsOnGrid overviewEntry


{-| Whether the client's combat log has named this overview row as having hit us.

**The two strings are the same string.** Established against the recorded runs
rather than assumed: across all ten sessions the combat log names 37 distinct
attackers, and 33 of them appear byte for byte -- same case, same spacing, same
punctuation -- as an overview entry's Name, in the bot's own
`Lock target from overview entry '...'` and `Current target: ...` lines, which
read `objectName` directly. "Federation Navy Delta II Support Frigate",
"Tower Sentry Sansha I", "Kruul's Henchman", "R.S. Officer" and "Centii Savage"
all round-trip unchanged. Of the four that do not appear, three are rats the bot
never locked, so the log has no overview-side string for them at all; the fourth
is "Toxic Cloud Environment", which is the pocket's own damage cloud and has no
overview row to match -- the harmless case, since a name with no row engages
nothing.

**Matched exactly, not as a substring**, for `isObjectToAttackFromSettings`'s
reason and one of its own. A substring match on the attacker "Kruul" would
select "Kruul's Pleasure Hub" and "Kruul's Henchman", and a wreck's Type is its
owner's name with " Wreck" appended -- so substring matching would have the bot
open fire on the corpse of the thing that just stopped shooting it, forever,
since a wreck never dies. Exactness is what makes accepting the Type column safe
too. Comparison trims and lowercases, matching the setting's rule, so nothing
here depends on the client's capitalisation being stable.

Both columns are accepted for the same reason the other two matchers accept
both: which one carries the identifying label varies. The recorded evidence
above is for the Name column specifically -- no recorded line shows an
attacker's name in the Type column -- so Type is the unverified half of this,
and it is included because the failure it guards against (a row whose Name cell
is empty) is the silent one.
-}
isObjectShootingAtUs : List String -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
isObjectShootingAtUs attackerNames overviewEntry =
    let
        normalize =
            String.trim >> String.toLower

        labels =
            [ overviewEntry.objectName, overviewEntry.objectType ]
                |> List.filterMap identity
                |> List.map normalize
    in
    attackerNames
        |> List.any (\attackerName -> labels |> List.member (normalize attackerName))


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


{-| An overview entry's distance, or a placeholder standing for "too far to
act on" when the distance reads in AU and does not parse as meters. Sorting
with this is safe -- an unreadable distance simply sorts last -- but nothing
should treat the placeholder as a real number; gate on
`overviewEntryDistanceIsOnGrid` first wherever that matters.
-}
overviewEntryDistanceOrFarInMeters : EveOnline.ParseUserInterface.OverviewWindowEntry -> Int
overviewEntryDistanceOrFarInMeters overviewEntry =
    overviewEntry.objectDistanceInMeters |> Result.withDefault 999999


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
destruction target, whatever the settings list, and whatever the client says has
been shooting us. The objective is the primary source -- it already says which
structure the mission means -- and the `attack-object` setting stays as a manual
override for cases it does not cover.

The three are kept apart rather than concatenated because they are matched
differently and, more importantly, mean different things. See
`isObjectToAttackFromObjective`, `isObjectToAttackFromSettings` and
`isObjectShootingAtUs` for the matching, and `isObjectToAttackByName` for the
one decision that has to tell the third apart from the other two.
-}
type alias ObjectNamesToAttack =
    { fromObjective : List String
    , fromSettings : List String
    , fromIncomingDamage : List String
    }


objectNamesToAttack : BotDecisionContext -> ObjectNamesToAttack
objectNamesToAttack context =
    { fromObjective =
        missionInfoPanelEntry context
            |> Maybe.map .objectNamesToDestroy
            |> Maybe.withDefault []
    , fromSettings = context.eventContext.botSettings.attackObjectNames
    , fromIncomingDamage = namesOfRecentAttackers context.memory.incomingDamage
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
        |> List.sortBy overviewEntryDistanceOrFarInMeters
        |> List.filter (shouldAttackOverviewEntry namesToAttack)


{-| Targets this mission actually named, as opposed to hostiles that merely
happen to share the grid. Distinguished by *why* the entry matched: an
objective- or settings-named structure still has to die when the briefing says
clearing is optional, a wandering pirate does not.

**Issue #40's attackers are deliberately not here**, which is the one place the
widening in `shouldAttackOverviewEntry` stops. A briefing that says the pirates
need not be cleared is the client telling us, in writing, that the fight is not
the job -- and the bot has already lost two whole sessions to ignoring that:
run 102 spent over 400 combat decisions on a mission whose brief said not to
bother, and run 106 did the same on Recon while the objective asked for an
acceleration gate. A rat shooting at the ship on such a mission is exactly the
rat those briefings are about, so admitting it here would reinstate that failure
with a better excuse for it.

The cost is real and is not hidden: on an optional-clearing mission the bot will
now travel to the objective while being shot and will not shoot back. What
covers that is the damage-rate retreat -- see `runAwayIfLowHealth` -- not this,
and if the fire is light enough that the retreat never trips, taking it while
finishing the mission is the intended outcome rather than an oversight.
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


{-| The overview row the open loot window belongs to: the nearest one that can be
looted at all. That is necessarily the container just opened, since it is the only
one the bot ever opens.
-}
nearestLootableEntry : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
nearestLootableEntry readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter (\entry -> entry.objectItemID /= Nothing)
        |> List.sortBy overviewEntryDistanceOrFarInMeters
        |> List.head


{-| The mission's own objective text, for noticing that it has stopped changing.

The first version of this tried to decide from the overview whether there was
anything worth acting on, using `objectItemID` as the mark of a lootable wreck.
Every row has one -- stargates, stations, the sun -- so nothing was ever
"nothing", the counter reset on every reading, and the alarm it gated could not
fire at all. Run 125 sat in the branch for 7,442 decisions with the fix
supposedly in place.

What the reading can answer honestly is narrower: has the objective changed. A
mission that is progressing rewrites this -- a pocket clears, a step completes,
the cargo lands -- so text that is identical for hundreds of readings while the
ship is in space means nothing is happening. It does not have to distinguish
"nothing to do" from "busy", because the branch that consults it is only reached
when there is nothing to do.
-}
missionObjectiveText : ReadingFromGameClient -> String
missionObjectiveText readingFromGameClient =
    readingFromGameClient.agentMissionInfoPanelEntries
        |> List.concatMap .instructionTexts
        |> String.join " / "


{-| Readings at the bottom of the tree before the bot stops calling it waiting.

Generous -- a mission genuinely can take a while to catch up after a warp -- but
finite, because the two runs that died here waited for the rest of the session.
-}
nothingToDoTicksBeforeCryingStuck : Int
nothingToDoTicksBeforeCryingStuck =
    300


{-| Whether the hangar has had long enough to produce the mission's cargo.

Not every objective that says "you need X in your cargohold" means X is in this
station. "After The Seven (3 of 5)" wants Phenod's DNA, which comes out of a
deadspace encounter, and the tracker's own next step is Undock -- but the docked
branch tries the hangar first and, before this, never stopped. Run 123 spent 86
readings docked, cycling the inventory quick filter for an item that was never
going to be there, while the button that would have started the mission sat on
the info panel.

A load that can succeed succeeds quickly: run 117 filtered, found and dragged in
about six readings. So this is not a close call, and the generous bound costs
nothing when the cargo really is in the hangar.

Counted on the reading alone -- docked with the mission asking for cargo -- so
it resets the moment the ship undocks or the objective moves on.
-}
courierLoadHasHadLongEnough : BotDecisionContext -> Bool
courierLoadHasHadLongEnough context =
    courierLoadTicksBeforeGivingUpOnTheHangar < context.memory.dockedWithCargoWantedTicks


courierLoadTicksBeforeGivingUpOnTheHangar : Int
courierLoadTicksBeforeGivingUpOnTheHangar =
    40


{-| Docked, with the mission asking for cargo. The state the hangar search runs
in, counted so it cannot run forever.
-}
dockedWithCargoWanted : ReadingFromGameClient -> Bool
dockedWithCargoWanted readingFromGameClient =
    let
        isDocked =
            case readingFromGameClient.shipUI of
                Nothing ->
                    True

                Just _ ->
                    False
    in
    isDocked
        && (readingFromGameClient.agentMissionInfoPanelEntries
                |> List.concatMap .objectNamesToCarry
                |> List.isEmpty
                |> not
           )


{-| Whether the ship is close enough to take items out of the open container.

Run 113 is why this exists. A double click is "Open Cargo", and from outside range
the client opens the window immediately and flies the ship over -- so an open loot
window is not evidence of having arrived, and EVE said so 39 times in one run
("Cargo is too far away. Ship is on automatic approach to cargo."). The bot clicked
'Loot All' anyway on the reading the window appeared, and the client refused it 8
times out of 8 with "You must be within 2500 meters of the container to remove
items from it". Every wreck that run was left full.
-}
shipIsWithinLootRange : ReadingFromGameClient -> Bool
shipIsWithinLootRange readingFromGameClient =
    case nearestLootableEntry readingFromGameClient of
        Nothing ->
            False

        Just entry ->
            case entry.objectDistanceInMeters of
                Ok distance ->
                    distance <= interactionRangeInMeters

                Err _ ->
                    False


{-| Whether the open container reports itself empty.

The capacity gauge is the only honest answer to "did the loot work". The bot used
to record a wreck as looted the moment its window opened, which is the one moment
we have positive evidence it still holds something -- so a refused 'Loot All' was
remembered as a completed one and the wreck never looked at again. On run 113 that
lost the Blood Raider Personnel Transport carrying the mission's Militants.
-}
openContainerIsEmpty : EveOnline.ParseUserInterface.InventoryWindow -> Bool
openContainerIsEmpty lootWindow =
    case lootWindow.selectedContainerCapacityGauge of
        Just (Ok gauge) ->
            gauge.used <= 0

        _ ->
            False


{-| The open wreck loot window together with the overview id it belongs to.

Both halves are needed together and neither means anything without the other, so
the pairing is done once here rather than at each of the three call sites.
-}
openWreckLootWindowAndId : ReadingFromGameClient -> Maybe ( EveOnline.ParseUserInterface.InventoryWindow, String )
openWreckLootWindowAndId readingFromGameClient =
    case readingFromGameClient |> wreckLootWindowsFromReadingFromGameClient |> List.head of
        Nothing ->
            Nothing

        Just lootWindow ->
            readingFromGameClient
                |> nearestLootableEntry
                |> Maybe.andThen .objectItemID
                |> Maybe.map (\wreckId -> ( lootWindow, wreckId ))


{-| Readings with the container open and in range, its gauge still not empty,
before the bot writes the wreck off. Deliberately generous: the gauge lags the
client by a reading or two after a successful 'Loot All', and the cost of being
wrong here is abandoning a wreck that may hold the mission item.
-}
lootAllRefusedTicksBeforeGivingUp : Int
lootAllRefusedTicksBeforeGivingUp =
    12


{-| Readings with the container open and the ship still not in range before the
bot writes the wreck off. An approach across a pocket is legitimately long -- run
113 spent over a hundred readings covering 30 km -- so this only catches an
approach that is not happening at all.
-}
outOfRangeTicksBeforeGivingUp : Int
outOfRangeTicksBeforeGivingUp =
    250


{-| Why the bot should stop working on the container it has open, if it should.

Both counters are bounds on waiting, and each names a different failure, so the
log says which one happened rather than reporting a generic give-up.
-}
giveUpOnOpenContainerReason : BotDecisionContext -> Maybe String
giveUpOnOpenContainerReason context =
    if context.memory.lootAllRefusedTicks >= lootAllRefusedTicksBeforeGivingUp then
        Just
            ("'Loot All' has not emptied this container in "
                ++ String.fromInt context.memory.lootAllRefusedTicks
                ++ " readings within range."
            )

    else if context.memory.lootWindowOutOfRangeTicks >= outOfRangeTicksBeforeGivingUp then
        Just
            ("The ship has not reached this container in "
                ++ String.fromInt context.memory.lootWindowOutOfRangeTicks
                ++ " readings."
            )

    else
        Nothing


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
    accelerationGatesOnOverview readingFromGameClient
        |> List.any
            (\entry ->
                (overviewEntryDistanceOrFarInMeters entry)
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
    accelerationGatesOnOverview context.readingFromGameClient
        |> List.head
        |> Maybe.andThen
            (\accelerationGateEntry ->
                let
                    distanceInMeters =
                        overviewEntryDistanceOrFarInMeters accelerationGateEntry
                in
                if context.memory.gateLockedForWantOfAnItem /= Nothing then
                    Just <|
                    -- The client has said, in answer to this bot's own press,
                    -- that it will not open this gate without an item in the
                    -- hold. Pressing again is the press/refuse/dismiss loop run
                    -- 10 spent two minutes in.
                    --
                    -- **Reaching this branch means the search is already over.**
                    -- `lootMissionItemFromContainerIfPresent` is checked ahead
                    -- of the whole gate path in `decideActionInMissionPocket`,
                    -- and since #44 it is driven by the key the client named as
                    -- well as by the objective's own cargo -- so if anything on
                    -- the overview could still be holding it, that branch won
                    -- this reading and this one was never called. Arriving here
                    -- is the loot path answering "nothing left to open".
                    --
                    -- Checked before the range test rather than after it, so
                    -- the ship does not fly at a gate it has been told is shut.
                    -- Nothing is lost by that: only the nearest gate is ever
                    -- considered, and the verdict is cleared the moment the ship
                    -- leaves reach or empties a container.
                    --
                    -- Asking for help on one line from the client rather than
                    -- waiting for the bottom of the tree to notice. That give-up
                    -- did fire in run 10 and did its job -- but 20 minutes and
                    -- 1,325 readings later, and saying only that nothing was
                    -- happening. The client had said why on the first attempt.
                    describeBranch
                        ("This acceleration gate will not open for this ship, and the client said why: \""
                            ++ (context.memory.gateLockedForWantOfAnItem |> Maybe.withDefault "")
                            ++ "\" -- "
                            ++ (case gateKeyWanted context of
                                    Just itemName ->
                                        "and nothing left on the overview looks like it might hold '"
                                            ++ itemName
                                            ++ "'."

                                    Nothing ->
                                        -- The sentence matched but named nothing
                                        -- extractable, so there is no errand to
                                        -- run. Said differently from the case
                                        -- above, because "we looked and found
                                        -- nothing" and "we never had anything to
                                        -- look for" are different problems.
                                        "and it named no item this bot could pick out of that sentence."
                               )
                        )
                        askForHelpToGetUnstuck

                else if not (gateCanBeActivatedNow context accelerationGateEntry) then
                    Just <|
                    -- Approach until the client says we can take the gate, and
                    -- let *it* decide when that is. The panel only carries
                    -- `selectedItemActivateGate` while the gate is genuinely in
                    -- range, so the button's presence is the range test -- and
                    -- unlike a distance of our own it cannot be stale.
                    --
                    -- A distance threshold was the obvious alternative and it
                    -- does not work. The overview distance lags the ship's true
                    -- position: run 128 read "in reach" and shut the prop mod
                    -- down, and the panel still offered no button. It is the
                    -- same lag that had the loot window refusing "Loot All" with
                    -- "you must be within 2500 meters" while the reading said
                    -- 1,602 m. Tightening interactionRangeInMeters would only
                    -- move the guess; asking the client removes it.
                    --
                    -- Drones come home first: the gate fires with whatever is
                    -- still in space.
                    ensureDronesRecalledBeforeWarping context
                        (approachOverviewEntry context
                            ("The acceleration gate is "
                                ++ String.fromInt distanceInMeters
                                ++ " m away and the panel offers no Activate yet -- keep closing."
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
                    --
                    -- Declining without a decision line is the one thing this
                    -- may not do silently, and it did: run 10 landed here and
                    -- the log went on saying "nothing to fight and no travel
                    -- step" for 1,325 readings with no hint that a gate had been
                    -- given up on. `describeAccelerationGate` carries it in the
                    -- status line every reading instead, since saying it here
                    -- would mean returning a step and losing the fallbacks.
                    Nothing

                else
                    Just <|
                    ensureDronesRecalledBeforeWarping context
                        (activateGateOnOverviewEntry context
                            -- Says which gate. The bare version of this line was
                            -- printed 135 times in run 10 without ever revealing
                            -- that the overview held two acceleration gates at
                            -- very different ranges, which is what made the
                            -- diagnosis take a manual read of the client. The
                            -- distance deliberately does not read "N m away":
                            -- stall_watch treats that wording as an approach in
                            -- progress and a falling number as progress, and
                            -- nothing is approaching here.
                            (describeAccelerationGateChosen context accelerationGateEntry
                                ++ " -- D-click it to move to the next pocket."
                            )
                            accelerationGateEntry
                        )
            )


{-| Which gate the gate branch is acting on, for the decision log.
-}
describeAccelerationGateChosen :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> String
describeAccelerationGateChosen context entry =
    let
        gatesOnOverview =
            accelerationGatesOnOverview context.readingFromGameClient
    in
    "I see an acceleration gate ("
        ++ (entry.objectName |> Maybe.withDefault "unnamed")
        ++ ", "
        ++ String.fromInt (overviewEntryDistanceOrFarInMeters entry)
        ++ " m, nearest of "
        ++ String.fromInt (List.length gatesOnOverview)
        ++ " on the overview)"


{-| Every acceleration gate the overview is showing, nearest first.

Across all overview windows, because more than one is a supported setup and the
gates of a pocket are not obliged to share one.

-}
accelerationGatesOnOverview :
    ReadingFromGameClient
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
accelerationGatesOnOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter isAccelerationGate
        |> List.sortBy overviewEntryDistanceOrFarInMeters


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
            stationInfoWindowForStation context stationName
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
                                            -- No select-all first: neither
                                            -- Control+A nor Command+A selects in
                                            -- this client's fields, and Command+A
                                            -- additionally stops the field taking
                                            -- keystrokes at all. This one is
                                            -- normally opened empty.
                                            [ mouseClickOnUIElement MouseButtonLeft searchField
                                                |> Result.withDefault []
                                            , typeTextEffects query
                                            , [ EffectOnWindow.KeyDown EffectOnWindow.vkey_RETURN
                                              , EffectOnWindow.KeyUp EffectOnWindow.vkey_RETURN
                                              ]
                                            ]
                                        )
                                    )

                        Nothing ->
                            describeBranch "I do not see the search bar." askForHelpToGetUnstuck


{-| The `Station: Information` window a double-click on a search result opens,
for one particular station.

Split out of `routeToStationByName` because it is also the evidence that a route
was set by us rather than left over from a mission -- see
`homeStationRouteIsSet`. Matched on the name appearing anywhere in the window's
text, which is how the window titles itself; the tooltip trap does not apply
here, since that one is drawn outside the *results* window and is not an
`InfoWindow` at all.
-}
stationInfoWindowForStation : BotDecisionContext -> String -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
stationInfoWindowForStation context stationName =
    allUiNodesInReading context
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) "InfoWindow")
        |> List.filter
            (\window ->
                EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode
                    |> List.any (stringContainsIgnoringCase stationName)
            )
        |> List.head


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
    returnDronesToBay context ifReadyToWarp


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

The parser returns nonsense occasionally -- measured now across all eight
recorded runs, roughly one reading in a few hundred, with values like 1862%,
2307%, 7711%, -213%, and at the extremes 8362%, 302023%, 2132822% and
-1021821%. That used to cost a single wrong tick, because every check compared
the live value and the next reading corrected it. Latching the low-water mark
for the retreat changed the stakes: one bogus -213% is below even a disabled
threshold of -1, and `min` then holds it until the ship is docked or fully
healthy. Seen live within one run of the latch going in -- "Shield reached
-213% (now 70%), get out get out" -- so the two changes have to land together.

**Rejecting the impossible values is not the same as trusting the rest**, and
the run-8 case is the one to keep in mind: 95, 95, 95, then 2132822 for exactly
one reading, then 95 again. `ShipUI.hitpointsPercent` is
`gauge._lastValue * 100` read out of a widget in the client's live memory while
the client is mutating it, so a single garbage reading is a read landing on a
reallocated object -- and the same accident that produced 21328.22 could as
easily produce 0.42. A garbage value inside [0, 100] is indistinguishable from a
real one and this function cannot help with it. That is the argument for
`run-away-incoming-damage-threshold`, which reads a number the client states
outright rather than a float scraped off a sprite.
-}
plausibleHitpointsPercent : Int -> Maybe Int
plausibleHitpointsPercent value =
    if value < 0 || 100 < value then
        Nothing

    else
        Just value


{-| Hitpoints per `incomingDamageWindowSeconds` the ship will sit through.

On rather than disabled, unlike the two hitpoint thresholds, because a guard
shipped off is what issue #32 was: the launcher disabled the shield one, leaving
the armour gauge as the only instrument, and on this shield-tanked hull the
armour gauge cannot move until the tank is already gone.

3500 is measured, not chosen. Peak incoming damage in any 45-second window,
taken from the client's own timestamps across sixteen recorded sessions: the
worst any session the ship survived absorbed was 3114, and the session it was
lost in peaked at 4101. The margin either side is about 12%, which is the best
this data offers -- and it is a real separation rather than a comfortable one,
so a run that trips this guard is worth reading rather than assuming spurious.

**This number is about a hull, not about the game.** It is the tank of the ship
on this account. Flying anything else means re-deriving it, and the failure mode
of carrying it over is silent in the dangerous direction: on a bigger hull it
retreats from fights it would win, and on a smaller one it never fires.
-}
defaultRunAwayIncomingDamageThreshold : Int
defaultRunAwayIncomingDamageThreshold =
    3500


{-| How far back the incoming-damage retreat looks.

45 seconds, chosen from the recorded client logs rather than picked: it is where
the fatal engagement separates most cleanly from every engagement the ship
survived. Across sixteen recorded sessions the worst 45-second window a
surviving run absorbed was 3114 hitpoints; the session the ship died in peaked
at 4101. Shorter windows separate slightly better still in relative terms and
carry more noise; longer ones close the gap -- at four minutes it is 8689
against 9286, which no threshold could tell apart.
-}
incomingDamageWindowSeconds : Int
incomingDamageWindowSeconds =
    45


{-| Damage the HUD has to react to before its silence is treated as a fault.

The rule this serves: a gauge that does not move while the ship is being taken
apart is not a reading, and the correct response to an instrument that cannot
answer is to leave, not to keep fighting on its silence.

The number is what makes that rule safe rather than trigger-happy. A shield at
100% genuinely does not change by a whole percent for a small hit, and shields
regenerate, so brief stretches of an unchanged reading under light fire are
normal. Measured on the three recorded runs whose shield reading was live, the
most damage ever absorbed while the `(shield, armor)` pair stayed frozen was 595
hitpoints, over 21 seconds. 1500 is two and a half times that.

Deliberately below `run-away-incoming-damage-threshold`: a ship that can see
what is happening to it is given more room than one that cannot.
-}
damageThatMustMoveTheHitpointsReading : Int
damageThatMustMoveTheHitpointsReading =
    1500


{-| How many readings the window must hold before its silence means anything.

Without this, the first reading of a session is a window of one, which trivially
"has not changed", and a bot that undocked into a fight would retreat on its
first look. Four readings is roughly ten seconds here.
-}
readingsBeforeAFrozenHitpointsReadingCounts : Int
readingsBeforeAFrozenHitpointsReadingCounts =
    4


{-| A backstop on the window's length, not a policy.

The window is bounded by time, and 200 samples is far more than
`incomingDamageWindowSeconds` can hold at any tick rate this bot runs at. It
exists so a clock that jumps backwards cannot grow the list without limit.
-}
incomingDamageSampleLimit : Int
incomingDamageSampleLimit =
    200


{-| Total hitpoints taken in the window.
-}
incomingDamageInWindow : IncomingDamageMemory -> Int
incomingDamageInWindow memory =
    memory.samples |> List.map .damage |> List.sum


{-| Everything the client has named as having hit this ship inside the window.

**Issue #40.** The bot decided what to shoot from the overview's icon colour
plus whatever an operator had remembered to list in `attack-object`, so anything
matching neither was invisible to it -- including things actively shooting it,
and "nothing to fight" is what it prints either way. What is shooting the ship
is a valid target whether or not anyone predicted it, and the client says so on
every damage line it writes.

The gap is measured rather than assumed, and it is smaller than the issue
claims: of 1198 recorded readings taken under fire, 299 found no rat by icon
colour, and 26 of those sit at an acceleration gate absorbing 320-370 hitpoints
a window from something named "R.S. Officer". Whether that attacker had an
overview row is not knowable from a recording -- the bot prints the count, never
the rows. Run 10's long "Nothing to fight" stretch, which the issue attributes
here, took no damage at all and belongs to #41's locked gate.

The list is the window's `topAttacker` values, deduplicated. It is one name per
reading rather than every attacker in the reading, which is what the host
already aggregates -- and measured over the recorded runs that is enough:
accumulating the per-reading top attacker across a 45-second window recovers
**1674 of the 1717** attacker-name-in-window pairs the full set would have,
97.5%, because a reading is one to three seconds and a second attacker takes the
top slot within a few of them. Widening the host's aggregation to carry every
name would buy the remaining 2.5% at the cost of a list where a single string
is, and the names it misses are ones the icon-colour rule already covers.

Order is not meaningful and nothing reads it as a priority: see
`shouldAttackOverviewEntry`, where this is one disjunct of three and the
resulting list keeps its existing distance ordering.
-}
namesOfRecentAttackers : IncomingDamageMemory -> List String
namesOfRecentAttackers memory =
    memory.samples
        |> List.filterMap .attacker
        |> Common.Basics.listUnique


{-| Did the HUD's hitpoints reading move at all across the window?

Only a *believed* value counts as evidence of movement: two different `Just`
readings. A window of nothing but `Nothing` -- no ship UI, or every value
rejected as impossible -- has not moved, which is the conservative reading and
the intended one. So is a window mixing `Just 100` with `Nothing`.

`Nothing` here means the question cannot be asked yet, because the window is
still shorter than `readingsBeforeAFrozenHitpointsReadingCounts`.
-}
hitpointsReadingMovedInWindow : IncomingDamageMemory -> Maybe Bool
hitpointsReadingMovedInWindow memory =
    if List.length memory.samples < readingsBeforeAFrozenHitpointsReadingCounts then
        Nothing

    else
        Just
            (memory.samples
                |> List.filterMap .hitpoints
                |> Common.Basics.listUnique
                |> List.length
                |> (<) 1
            )


{-| The damage-rate guard, in the status line, every reading.

Whether the host carries the channel is reported first and unconditionally,
because "0 hitpoints in the last 45 s" reads exactly the same whether the grid
is quiet or nothing is watching -- and two guards below depend on the
difference. This follows the ammo swap's line for the same reason: a safety net
that is not armed has to say so, since its silence is otherwise indistinguishable
from its working.
-}
describeIncomingDamage : BotDecisionContext -> String
describeIncomingDamage context =
    let
        memory =
            context.memory.incomingDamage

        threshold =
            context.eventContext.botSettings.runAwayIncomingDamageThreshold
    in
    if not memory.hostCarriesTheChannel then
        "Incoming damage: this host is not carrying the client's combat log, so "
            ++ "the damage-rate retreat and the frozen-reading check are both unarmed."

    else
        "Incoming damage: "
            ++ (incomingDamageInWindow memory |> String.fromInt)
            ++ " hitpoints over the last "
            ++ (incomingDamageWindowSeconds |> String.fromInt)
            ++ " s in "
            ++ (List.length memory.samples |> String.fromInt)
            ++ " reading(s), threshold "
            ++ (if threshold < 0 then
                    "disabled"

                else
                    String.fromInt threshold
               )
            ++ (if memory.retreating then
                    ", RETREATING"

                else
                    ""
               )
            ++ ". Hitpoints reading moved in the window: "
            ++ (case hitpointsReadingMovedInWindow memory of
                    Nothing ->
                        "too few readings to say"

                    Just True ->
                        "yes"

                    Just False ->
                        "no"
               )
            ++ (case memory.lastAttacker of
                    Nothing ->
                        ""

                    Just attacker ->
                        ". Hardest hitter seen: '" ++ attacker ++ "'"
               )
            ++ "."
            -- Issue #40: the set the target selection is actually reading, not
            -- just the single hardest hitter above. Printed every reading and
            -- not only when it matches something, because the useful diagnosis
            -- on a run that fails this way is "the client named an attacker and
            -- no overview row carried that name", and a clause that appears only
            -- on success cannot say that.
            ++ (case namesOfRecentAttackers memory of
                    [] ->
                        " Attackers named in the window: none."

                    names ->
                        " Attackers named in the window: "
                            ++ (names |> List.map (\name -> "'" ++ name ++ "'") |> String.join ", ")
                            ++ " (any overview row with one of these names is a target)."
               )


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
threshold, so the re-arm level is a constant here while the trip level is a
setting read at the decision.
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


{-| Fold this reading's incoming fire into the rolling window.

Three things happen here and each has to happen here, because a reading's
`incomingDamageSinceLastReading` does not survive to the next one.

**The window is trimmed by the clock, not by a count.** Readings take between
one and three seconds depending on what the client is doing, so a window
measured in readings would be a window of wildly varying length, and the
threshold behind it was calibrated in seconds against the client's own
timestamps.

**`Nothing` from the parser is recorded as "no channel", never as "no damage".**
It leaves `samples` alone rather than appending a zero, so a host that does not
carry the channel accumulates an empty window and every guard below reads
"nothing is happening" -- which is the correct behaviour only because
`hostCarriesTheChannel` is what the status line reports, loudly, so an operator
can see the guard is unarmed instead of inferring safety from its silence.

**The latch is released by absence, not by recovery.** It trips when the window
is over the threshold and clears only when the window is completely empty -- no
hit at all for `incomingDamageWindowSeconds`. Trip and release are different
conditions on purpose: one threshold with the reading walking back and forth
across it is the flicker `runAwayRearmPercent` exists to prevent, and here there
is no "healthy" reading to re-arm against, only the fire having stopped.

The reading's `topAttacker` rides along on the sample rather than being
accumulated into a list of its own, so `namesOfRecentAttackers` inherits the
trimming above and needs no clearing rule -- see `IncomingDamageMemory`.
-}
updateIncomingDamageMemory : UpdateMemoryContext BotSettings -> IncomingDamageMemory -> IncomingDamageMemory
updateIncomingDamageMemory context memoryBefore =
    let
        hitpointsNow =
            context.readingFromGameClient.shipUI
                |> Maybe.andThen
                    (\shipUI ->
                        Maybe.map2 Tuple.pair
                            (plausibleHitpointsPercent shipUI.hitpointsPercent.shield)
                            (plausibleHitpointsPercent shipUI.hitpointsPercent.armor)
                    )

        keptSamples =
            memoryBefore.samples
                |> List.filter
                    (\sample ->
                        context.timeInMilliseconds - sample.atMilliseconds
                            < incomingDamageWindowSeconds * 1000
                    )
                |> List.take incomingDamageSampleLimit

        samples =
            case context.readingFromGameClient.incomingDamageSinceLastReading of
                Nothing ->
                    keptSamples

                Just reading ->
                    { atMilliseconds = context.timeInMilliseconds
                    , damage = reading.damage
                    , hitpoints = hitpointsNow
                    , attacker = reading.topAttacker
                    }
                        :: keptSamples

        updated =
            { samples = samples
            , hostCarriesTheChannel =
                context.readingFromGameClient.incomingDamageSinceLastReading /= Nothing
            , lastAttacker =
                case context.readingFromGameClient.incomingDamageSinceLastReading of
                    Just reading ->
                        case reading.topAttacker of
                            Just attacker ->
                                Just attacker

                            Nothing ->
                                memoryBefore.lastAttacker

                    Nothing ->
                        memoryBefore.lastAttacker
            , retreating = memoryBefore.retreating
            }

        damageInWindow =
            incomingDamageInWindow updated

        threshold =
            context.botSettings.runAwayIncomingDamageThreshold
    in
    { updated
        | retreating =
            if damageInWindow <= 0 then
                False

            else if 0 <= threshold && threshold <= damageInWindow then
                True

            else
                memoryBefore.retreating
    }


updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentContextMenuDepth =
            context.readingFromGameClient.contextMenus |> List.length

        dronesInSpaceCountNow =
            dronesInSpaceCount context.readingFromGameClient

        -- A container that has just been emptied, on this reading. Two fields
        -- read it: `lootedWreckIds` records which one, and the locked-gate
        -- verdict forgets itself, because the hold may now hold the key.
        containerEmptiedThisReading =
            case openWreckLootWindowAndId context.readingFromGameClient of
                Just ( lootWindow, wreckId ) ->
                    openContainerIsEmpty lootWindow
                        && not (List.member wreckId botMemoryBefore.lootedWreckIds)

                Nothing ->
                    False

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

        lockRangeLearning =
            updateLockRangeLearning context botMemoryBefore

        -- Only settled readings count as a look. The selected container
        -- renders empty for one reading while it is being switched (40 -> 0 ->
        -- 40 rendered rows, watched live), so a gauge read on the reading after
        -- a click can describe a container that is still arriving.
        settledDroneBayFill =
            if previousStepsEffectsPressedMouse context.previousStepsEffects then
                Nothing

            else
                droneBayFillWhileSelected context.readingFromGameClient

        shipUIWithoutModuleButtonsReadings =
            shipUIWithoutModuleButtonsReadingsAfter
                context.readingFromGameClient
                botMemoryBefore.shipUIWithoutModuleButtonsReadings
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
    , incomingDamage = updateIncomingDamageMemory context botMemoryBefore.incomingDamage
    , readingsCount = botMemoryBefore.readingsCount + 1
    , droneBayOpenedFromShipCard =
        -- Whether our own "Open Drone Bay" on the ship's card has landed since
        -- the ship docked. Nothing in a reading distinguishes the inventory
        -- opened that way from the one Alt+C opens, and only the first accepts
        -- a drop into the bay -- so the one moment that is evidence, the ship's
        -- drone bay showing as the selected container, is remembered until the
        -- ship undocks. The bot selects that container nowhere else, and the
        -- restock has to leave it to reach the item hangar, which is why the
        -- answer cannot simply be re-read when the drag comes around.
        if context.readingFromGameClient.shipUI /= Nothing then
            False

        else
            droneBayIsSelectedContainer context.readingFromGameClient
                || botMemoryBefore.droneBayOpenedFromShipCard
    , droneBayEmptyLastSeen =
        -- The last answer a reading was actually able to give about the bay,
        -- carried forward across the readings that cannot give one.
        --
        -- Written only from readings that can see the bay, so this is evidence
        -- rather than inference: in space the drones window is open (this
        -- bot's own setup instructions require it), so a run that loses its
        -- drones records `Just True` on the very next reading and carries it
        -- into the dock, which is where the home-station decision is made.
        -- `Nothing` means no reading this session ever saw the bay -- a session
        -- that never undocked -- and the home trip declines to guess.
        case droneBayIsEmptyFromDronesWindow context.readingFromGameClient of
            Nothing ->
                botMemoryBefore.droneBayEmptyLastSeen

            Just isEmpty ->
                Just isEmpty
    , shipUIWithoutModuleButtonsReadings = shipUIWithoutModuleButtonsReadings
    , shipLoss =
        -- Written here and nowhere else. The game log entries the first signal
        -- reads are gone by the next reading, and this is the only place that
        -- can write memory -- a branch that recognised the loss in the decision
        -- tree instead would see it once and forget it.
        shipLossVerdictAfter context.readingFromGameClient
            { withoutModulesReadings = shipUIWithoutModuleButtonsReadings
            , verdictBefore = botMemoryBefore.shipLoss
            }
    , ammoSwap = updateAmmoSwapMemory context botMemoryBefore.ammoSwap
    , droneBayWillTakeNoMore =
        -- The restock's "already done", in the two forms a docked reading can
        -- supply it: the bay's own capacity gauge reading full at a moment the
        -- bay was the selected container, or the client refusing a drop. The
        -- refusal is the stronger of the two -- it is the client answering the
        -- question directly, and it catches the case the gauge cannot, a bay
        -- with less free volume than one drone.
        --
        -- Latched because the restock has to select the station hangar to
        -- reach the drones, after which the bay is not readable at all.
        if context.readingFromGameClient.shipUI /= Nothing then
            False

        else
            (settledDroneBayFill == Just DroneBayFull)
                || ((0 < botMemoryBefore.droneRestockDragsDispatched)
                        && dropIntoDroneBayWasRefused context.readingFromGameClient
                   )
                || botMemoryBefore.droneBayWillTakeNoMore
    , droneRestockLooksWithRoom =
        -- Counts the readings that read the bay's gauge and did not find it
        -- full, which is what bounds the restock. A gauge that does not answer
        -- counts as a look for the same reason the caller acts on it: a
        -- condition that cannot see the bay must not be allowed to run the
        -- task forever any more than it may retire it.
        if context.readingFromGameClient.shipUI /= Nothing then
            0

        else if (settledDroneBayFill /= Nothing) && (settledDroneBayFill /= Just DroneBayFull) then
            botMemoryBefore.droneRestockLooksWithRoom + 1

        else
            botMemoryBefore.droneRestockLooksWithRoom
    , droneRestockDragsDispatched =
        -- Scoped to the restock by `droneBayOpenedFromShipCard`: the courier
        -- load drags too, but it runs during a mission leg, and this flag is
        -- only ever set by the restock's own "Open Drone Bay" during
        -- wind-down. A miscount could only end the restock early, never let it
        -- run longer.
        if context.readingFromGameClient.shipUI /= Nothing then
            0

        else if
            botMemoryBefore.droneBayOpenedFromShipCard
                && previousStepsEffectsDragged context.previousStepsEffects
        then
            botMemoryBefore.droneRestockDragsDispatched + 1

        else
            botMemoryBefore.droneRestockDragsDispatched
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
        -- ones already emptied by object id.
        --
        -- *Emptied*, not *opened*. This used to record the wreck as soon as its
        -- window appeared, which is precisely the moment we have evidence it
        -- still holds something. A 'Loot All' the client refused was then
        -- remembered as a completed one, and the wreck was filtered out of the
        -- candidate list forever. Run 113 lost the Blood Raider Personnel
        -- Transport holding the mission's Militants that way, and then waited
        -- out the rest of the session for an objective that could no longer
        -- clear. The capacity gauge is the honest signal: the container itself
        -- says what is left in it.
        --
        -- Capped so a long session cannot grow this without bound.
        case openWreckLootWindowAndId context.readingFromGameClient of
            Just ( _, wreckId ) ->
                if containerEmptiedThisReading then
                    wreckId :: botMemoryBefore.lootedWreckIds |> List.take 200

                else
                    botMemoryBefore.lootedWreckIds

            Nothing ->
                botMemoryBefore.lootedWreckIds
    , lootAllRefusedTicks =
        -- Readings with the container open, the ship in range, and the gauge
        -- still not reading empty. In the normal case this is one or two while
        -- the client catches up. It climbing means 'Loot All' is not working on
        -- this container for a reason the bot cannot see -- a full cargohold,
        -- say -- and `unlootableWreckIds` gives up on it rather than letting it
        -- hold the mission open indefinitely.
        case openWreckLootWindowAndId context.readingFromGameClient of
            Just ( lootWindow, _ ) ->
                if shipIsWithinLootRange context.readingFromGameClient && not (openContainerIsEmpty lootWindow) then
                    botMemoryBefore.lootAllRefusedTicks + 1

                else
                    0

            Nothing ->
                0
    , lastObjectiveText = missionObjectiveText context.readingFromGameClient
    , nothingToDoTicks =
        -- Readings in space with the objective text unchanged. Generous,
        -- because the branch that reads it is only reached when there is
        -- genuinely nothing to do -- so this does not have to tell waiting from
        -- fighting, only tell "the mission moved" from "it did not".
        if
            (context.readingFromGameClient.shipUI /= Nothing)
                && (missionObjectiveText context.readingFromGameClient /= "")
                && (missionObjectiveText context.readingFromGameClient == botMemoryBefore.lastObjectiveText)
        then
            botMemoryBefore.nothingToDoTicks + 1

        else
            0
    , dockedWithCargoWantedTicks =
        if dockedWithCargoWanted context.readingFromGameClient then
            botMemoryBefore.dockedWithCargoWantedTicks + 1

        else
            0
    , dronesInSpaceTicks =
        -- Consecutive readings with drones out, counted from the launch. This
        -- is "how long have they been out" and nothing more -- it says nothing
        -- about whether a recall is landing, because drones are deliberately
        -- left out for a whole fight. Only `droneRecallUnansweredTicks` below
        -- can tell those apart.
        if dronesAreInSpace context.readingFromGameClient then
            botMemoryBefore.dronesInSpaceTicks + 1

        else
            0
    , dronesInSpaceCount = dronesInSpaceCountNow
    , droneRecallUnansweredTicks =
        -- Consecutive readings in which the bot has asked for the drones back
        -- and the client has not answered. Only two things end it: the drones
        -- being home, and the in-space count falling at all -- a partial recall
        -- is the client answering, so the rest deserve the full patience again.
        --
        -- It also stops counting when the bot stops asking, so a fight it went
        -- back to fighting is not held against a recall nobody is making. Past
        -- the give-up threshold that has to become a hold rather than a reset:
        -- giving up is precisely what stops the asking, so a reset there would
        -- unwind the give-up two readings later and the ship would spend the
        -- rest of the session alternating between abandoning its drones and
        -- recalling them again.
        if dronesInSpaceCountNow < 1 then
            0

        else if dronesInSpaceCountNow < botMemoryBefore.dronesInSpaceCount then
            0

        else if droneRecallGiveUpTicks < botMemoryBefore.droneRecallUnansweredTicks then
            botMemoryBefore.droneRecallUnansweredTicks

        else if recentStepAskedForDroneRecall context.previousStepsEffects then
            botMemoryBefore.droneRecallUnansweredTicks + 1

        else
            0
    , lootWindowOutOfRangeTicks =
        -- The other half of the same bound. Waiting for the ship to arrive is
        -- correct, but only the client is steering, and if the approach never
        -- completes -- or the row leaves the overview entirely, which makes the
        -- range unanswerable -- the wait has to end somewhere. Generous, because
        -- a legitimate approach from the far side of a pocket is minutes of
        -- readings and cutting one short abandons a wreck for no reason.
        case openWreckLootWindowAndId context.readingFromGameClient of
            Just _ ->
                if shipIsWithinLootRange context.readingFromGameClient then
                    0

                else
                    botMemoryBefore.lootWindowOutOfRangeTicks + 1

            Nothing ->
                0
    , unlootableWreckIds =
        case openWreckLootWindowAndId context.readingFromGameClient of
            Just ( _, wreckId ) ->
                if
                    ((botMemoryBefore.lootAllRefusedTicks >= lootAllRefusedTicksBeforeGivingUp)
                        || (botMemoryBefore.lootWindowOutOfRangeTicks >= outOfRangeTicksBeforeGivingUp)
                    )
                        && not (List.member wreckId botMemoryBefore.unlootableWreckIds)
                then
                    wreckId :: botMemoryBefore.unlootableWreckIds |> List.take 200

                else
                    botMemoryBefore.unlootableWreckIds

            Nothing ->
                botMemoryBefore.unlootableWreckIds
    , gateWithinReachTicks =
        -- Readings in a row in which the client was offering to open the gate
        -- and it did not open. A gate normally takes a handful; a gate that
        -- refuses the ship never takes any, and there is no error dialog to
        -- notice -- see `missionNeedsADifferentShip`. Counting them is what
        -- turns that into something the bot can act on.
        --
        -- It counts the *offer*, not the proximity, and the difference is the
        -- same one `droneRecallUnansweredTicks` had to make: time spent near a
        -- gate is not evidence that the gate refuses the ship. This budget is
        -- spent by declining it, so anything else that keeps the ship parked
        -- there was spending it too -- a fight beside the gate lasts far longer
        -- than 40 readings, and the pocket that ends with a scrambled gate
        -- ("clear the vicinity of enemy ships") is precisely a long fight
        -- within `interactionRangeInMeters` of one. That would have exhausted
        -- the budget before the last rat died and left the gate permanently
        -- declined on a grid where it was about to work.
        --
        -- So a reading with the gate in reach but no Activate on the panel
        -- *holds* the count rather than resetting it: the message box run 10
        -- had to dismiss between every attempt is one of those, and a reset
        -- there is the shape that held `gunsSilencingTicks` at 1 forever.
        -- Leaving reach is what resets, since that is the ship no longer
        -- asking this gate for anything.
        if selectedItemOffersActivateGate context.readingFromGameClient then
            botMemoryBefore.gateWithinReachTicks + 1

        else if accelerationGateIsWithinReach context.readingFromGameClient then
            botMemoryBefore.gateWithinReachTicks

        else
            0
    , gateLockedForWantOfAnItem =
        -- The client's own sentence, kept from the reading it arrived on --
        -- a reading's game log entries are gone by the next one, and the
        -- branch that acts on this is several readings away from the press
        -- that provoked it.
        --
        -- Cleared when no gate is within reach, which is the same reset
        -- `gateWithinReachTicks` uses and for the same reason: it is the ship
        -- having left this gate. Latching it for the session instead would be
        -- wrong here in a way it is not for `shipLoss` -- that verdict ends the
        -- session, this one asks for help and the run continues, so a gate
        -- unlocked by hand in the next pocket must not still read as locked.
        --
        -- Cleared again the moment a container is emptied, which is what makes
        -- the retrieval a loop that ends rather than one verdict deciding the
        -- rest of the session. The bot has just taken everything out of
        -- something and the key may be aboard, so the gate is asked again --
        -- and if it is still locked the client says so again and this re-latches
        -- on *that* reading. Nothing is ever re-latched on the strength of a
        -- verdict formed before the loot.
        --
        -- That loop terminates for the reason `lootableHoldingMissionItem`
        -- documents: each container emptied drops out of the candidate list, so
        -- the search shrinks, and when it is empty the gate branch asks for help
        -- naming what it was looking for.
        --
        -- Reachable in both directions: it is set from a line the client writes
        -- in answer to the Activate press below, which only happens with the
        -- gate in reach, and cleared by the first reading after the ship leaves
        -- or the first container it empties.
        if
            not (accelerationGateIsWithinReach context.readingFromGameClient)
                || containerEmptiedThisReading
        then
            Nothing

        else
            case botMemoryBefore.gateLockedForWantOfAnItem of
                Just latched ->
                    Just latched

                Nothing ->
                    gateLockedForWantOfAnItemFromGameLog context.readingFromGameClient
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
    , lockAttempt = lockRangeLearning.attempt
    , lockProvenAtMeters = lockRangeLearning.provenAtMeters
    , lockRefusedAtMeters = lockRangeLearning.refusedAtMeters
    , lockRangeLastChange = lockRangeLearning.change
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

What #35 found is that the state is not missing, only elsewhere: twelve entries
on the button's own `dictEntriesOfInterest`, now parsed onto
`stateFromDictEntries`. `isInActiveState` is the one that means what this filter
wants -- it read `True` on all four modules across all 92 samples of a 240s
live sample, tracking switched-on, while `ramp_active` oscillated fourteen times
underneath it. It is **not** wired in here, because that sample is one window on
one fit and it never saw a module switch off, which is the state this filter
exists to detect. `describeTopRowModuleDictState` logs it every reading so the
next run settles that leg.
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


{-| What the guns say about themselves in their own dict entries, verbatim.

#35 found the module state the sprites do not carry sitting unread on every
module button. A 240s read-only sample of run 9 then measured most of what those
entries mean -- `ramp_active` is the gun's duty cycle and oscillates all through
a fight, `isInActiveState` is the switched-on flag -- and left one leg with no
observations at all: `isDeactivating` was never `True`, because nothing switched
a module off while the sampler ran. **This line exists to catch that leg**, on
the next run that performs an ammo swap, without anybody having to be watching.
The status line is what survives a run to be read back afterwards, which is how
`Middle-row modules: none.` turned out to be measurable across nine logs (#33).

**Nothing acts on any of it.** One 240s window on one fit is not a licence to
rewire a decision, and the field #34 hung on is the one still unobserved.

The top row is where the guns are (`shipUIModulesToActivateOnTarget`), and the
guns are what #34 hung waiting on, so it is the row worth the characters. The
other seven entries the parser reads are not printed: this line goes out
thousands of times a run, and `online`, `blinking`, `grey`, `quantity`,
`autoreload`, `autorepeat` and `isMaster` were each constant across all 92
samples.

`isInActiveState` is printed beside `ramp_active` rather than left out because
it is what makes `ramp_active` readable at all: a `False` there means "between
cycles" while the gun is on and "not running" once it is off, and only the
switched-on flag separates those two. The switch-off leg is exactly where they
disagree.

`-` is an entry that is **absent from the tree**, printed differently from `0`
and `F` on purpose. Absent and `False` are different facts here and both were
seen: no module carried `ramp_active` for the first ~60s of the sample, and
`waitingForActiveTarget` appeared on all four modules at once at 141s. A format
that collapsed them would drop the very transition worth recording. (An entry
present but undecodable also prints `-`; on this build every key seen decodes.)

-}
describeTopRowModuleDictState : ReadingFromGameClient -> String
describeTopRowModuleDictState readingFromGameClient =
    let
        describeFlag maybeFlag =
            case maybeFlag of
                Just True ->
                    "T"

                Just False ->
                    "F"

                Nothing ->
                    "-"

        describeNumber maybeNumber =
            case maybeNumber of
                Just number ->
                    String.fromInt number

                Nothing ->
                    "-"

        describeOne moduleButton =
            [ describeFlag moduleButton.stateFromDictEntries.ramp_active
            , describeFlag moduleButton.stateFromDictEntries.isInActiveState
            , describeFlag moduleButton.stateFromDictEntries.isDeactivating
            , describeNumber moduleButton.stateFromDictEntries.effect_activating
            , describeNumber moduleButton.stateFromDictEntries.waitingForActiveTarget
            ]
                |> String.join "/"
    in
    case readingFromGameClient.shipUI of
        Nothing ->
            "Top-row modules: no ship UI."

        Just shipUI ->
            case shipUI.moduleButtonsRows.top |> List.sortBy (.uiNode >> .totalDisplayRegion >> .x) of
                [] ->
                    "Top-row modules: none."

                topRowModules ->
                    "Top-row modules (ramp_active/isInActiveState/isDeactivating/effect_activating/waitingForActiveTarget): "
                        ++ (topRowModules |> List.map describeOne |> String.join ", ")
                        ++ "."


nothingFromIntIfGreaterThan : Int -> Int -> Maybe Int
nothingFromIntIfGreaterThan limit originalInt =
    if limit < originalInt then
        Nothing

    else
        Just originalInt
