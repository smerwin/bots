{- EVE Online gas huffer

      This app is meant to harvest gas from a wormhole gas site, deposit it at a
      structure, and leave the moment anything else shows up on the grid. Since
      #461 the **harvesting** half of that works: it decides which site to hunt,
      warps to it, picks the cloud on the grid whose designation carries the
      highest trailing number, orbits it, locks it and runs both gas
      harvesters.

      Since #462 it also **watches the grid**: it refreshes the Directional
      Scanner on a cadence, and judges every reading against three independent
      triggers -- a rat on the overview by icon colour, a pilot on the overview
      who is not in the fleet, and a ship on D-Scan whose name does not carry
      `friendly-ship-tag`. `gridVerdict` is that answer and the status line
      carries it on every reading.

      Since #463 it **leaves**. A grid that does not read clean sends the ship to
      the first of three destinations it can reach -- a bookmark whose label
      starts with `retreat-bookmark-prefix`, else the overview row matching
      `home-structure-name`, else any bookmark at all at 100 km -- then activates
      a cloak if one is fitted, keeps refreshing D-Scan, and bounces between
      celestials at ranges drawn per attempt until the grid reads clean again. A
      reading the bot **cannot see** never counts as clean, so an evasion does
      not end on a shut D-Scan window or an unreadable row. If the grid never
      comes clean, the session ends with the ship wherever the last warp put it,
      which is a legitimate end to an evening in somebody else's wormhole.

      Since #464 it **deposits**. A Mining Hold that reads full sends the ship to
      the overview row matching `home-structure-name`, docks it with the Selected
      Item panel's own Dock button, drags the hold's contents into the
      structure's item hangar, and waits for the **client's own** `N item(s) was
      moved to your hangar` line before calling it done -- never for the gauge to
      read zero, which is the same reading whether the drag worked or moved
      nothing. Then it undocks and goes back to work, and #461 picks the site
      again. Nothing here cycles: a deposit that cannot be finished ends the
      session saying the hold is still full, because an operator empties one by
      hand in seconds and a bot looping on it wastes an evening.

      **The retreat outranks all of that**, and it is placed above the
      docked-or-in-space split rather than conditioned: a grid that stops reading
      clean takes the ship out of a docking run-in, and while docked it keeps the
      ship docked rather than undocking a full ship into somebody else's grid to
      finish an errand.

      Since #465 the **propulsion module survives every warp**, which is the
      last of #456 and the one that is about the ship rather than about the
      work. Speed is this hull's whole survival plan -- it has no guns and no
      tank worth the name -- so the module is switched on above the leaving, the
      deposit and the harvest alike, on every reading in space, and **nothing in
      this file ever switches one off**. That is the opposite of every other app
      here: they funnel their warps through
      `ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping` and this
      one has no such helper to reach. The status line says on every reading
      whether the module reads as running, because a bot that warps correctly
      with the module off looks exactly like one that is covered.

      **Seven sessions have now flown, and they separate the features rather
      than confirming all of them at once.** Runs 1-5 (pre-#465 builds) show
      `Harvest: orbiting; cloud locked; harvesters both cycling` for hundreds of
      readings apiece, and it was one of these runs that caught the harvester
      periodic-recheck oscillating a genuinely-cycling module off -- fixed as
      `harvesterLooksActiveByRamp` and merged in PR #486. Run 1 alone cleared
      several dozen short evasions (the `Evasion:` counter climbing to
      1-14/600 and dropping straight back to `not evading`), read named ships
      off D-Scan (`'GAS Clock'`, eight `'Scanner Probe'` rows) as well as many
      whose Name cell it could not read at all, and pressed the cloak hotkey
      blind (`Cloak up with its own hotkey`, 13 times) since the tooltip that
      would confirm a cloak has never once resolved in any recorded run -- see
      `cloakAmongFittedModules`. Run 6 --
      the first on the fully merged tree, `ce0571e8` -- never got that far in
      its short session: it spent the whole of it evading, `Grid: SOMETHING`
      firing three times against named D-Scan rows (`'Warrior I'`,
      `'Mining Drone I'`), and was stopped by hand at 83/600.

      **Deposit (#464) is the one feature that has been watched failing.** Run
      3's hold filled, the bot reported `depositing` toward `My Neighbor
      Tatara`, and the give-up ran its full 300 readings to the end with **zero
      drags dispatched** and the client never having said the transfer landed --
      the session ended exactly as `depositGiveUpReadings`' own doc comment
      describes, except it is no longer hypothetical. Zero drags means whatever
      failed did so before the hangar work even started -- the dock, most
      likely -- and that is the first thing the next run needs to watch rather
      than the confirmation line this doc comment used to worry about.

      **The propulsion-module reading (#465) has never once resolved to
      `running` on a live client.** Every recorded run that carries the clause
      prints `Propulsion module: CANNOT TELL` and never prints it again for the
      rest of that session (the status line's own change-only suppression), which
      means the middle-row read has come back empty on every reading anyone has
      looked at so far -- not confirmed off, just never confirmed at all. That is
      unchanged by the merge and is the next thing to check against a live client
      before trusting the clause either way.

      **The wormhole-chain-hop retreat has never fired in any recorded run** --
      every evasion seen so far has been a short one, and none of the three
      celestial-bounce destinations has ever been exhausted. What to watch on
      the next run is in the paragraphs below that still say so.

      Started under issue #459; the behaviour is #460 (which site to hunt), #461
      (the harvest loop), #462 (hostile detection), #463 (retreat, cloak and
      evade), #464 (deposit the hold when it fills) and #465 (the propulsion
      module surviving every warp).

      ## Setting up the Game Client

      This bot's perception is narrower than a person's, so the client has to be
      set up to show it what it needs. Three of the items below **cannot be
      enforced from inside the bot at all** and are marked as such: nothing in a
      reading can tell a client set up this way from one that is not, so a client
      set up differently produces a bot that looks like it is working.

      + Set the UI language to English. Every string this bot matches -- the
        probe scanner's Group column, the overview's Type column, the client's
        own game-log sentences -- is the English one.
      + Undock, and leave the overview, the probe scanner window and the
        Directional Scanner open.
      + **The probe scanner window must be open with its `Group` column
        visible.** That window's rows are read by matching each cell's
        horizontal position against the window's own header labels, so a hidden
        Group column is not a column the bot reads as empty -- it is a column
        that is not there, and every site then reads as ungrouped. A site the
        bot cannot identify is one it declines rather than warps to, so a
        scanner set up without that column hunts nothing at all. It says which
        of those two it is on every reading; see `describeSiteSearch`.
      + **Leave the Locations window open.** Two separate things need it, and the
        second is the one that keeps the ship. With no scanned row reading the
        hunted Group, this bot will hunt a bookmark whose name carries
        `Reservoir` -- the client's own naming for the wormhole gas sites
        (Ordinary/Sizeable Perimeter Reservoir, Vast/Bountiful Frontier
        Reservoir, Vital/Instrumental Core Reservoir). And **two of the three
        places it runs to when it leaves are bookmarks**, so a shut Locations
        window takes both of those rungs away and leaves only
        `home-structure-name`, which has to be on the overview to be usable.
        With that window shut there is no fallback, which is a different thing
        from having no such bookmark and reads differently in the status line.
      + **The overview must show gas clouds, with the Name and Type columns
        visible.** A harvestable cloud renders with its own designation in the
        Name column and the generic `Harvestable Cloud` in the Type column, and
        the bot needs both: the Type is what makes a row a cloud at all, and the
        Name is what `gas-cloud-name-prefix` is matched against and what carries
        the trailing number the site's clouds are ordered by.
      + **Leave the Directional Scanner window open, and set its range and angle
        wide enough to cover the grid.** Everything this bot knows about ships it
        cannot see on the overview comes from that window, and a reading with no
        such window is not a quiet grid -- it is a grid this bot cannot see, which
        it reports as `CANNOT TELL` and never as clean. Nothing here opens the
        window, sets its range or sets its angle; a scanner pointed at one degree
        of sky reads empty and reads exactly like a clean one.
      + **Bind the Directional Scanner's scan to `V`, which is the client's own
        default, and leave it bound.** The refresh this bot makes is that
        keypress and nothing else. **Nobody has watched it land** -- see
        `directionalScanHotkey` -- so a client whose scan sits on some other key
        is a bot whose D-Scan never refreshes, and what says so is the status
        line's own staleness clause rather than anything the client reports.
      + **Leave the Local chat window open.** It is the only thing in a reading
        that names the pilots in the system and says which of them are in the
        fleet, so an overview row is known to be a *player* only by its name
        appearing there. With that window shut this bot cannot tell a pilot's row
        from a rock's, and it says `CANNOT TELL` rather than reading the grid as
        clean -- see `pilotsOnTheOverviewNotInTheFleet`.
      + **Leave the inventory open with the ship's Mining Hold selected.** That
        window's capacity gauge is the only thing in a reading that says how full
        the hold is, and it belongs to whatever container the window has
        _selected_ -- so an inventory showing anything else is a hold this bot
        cannot read, and a hold it cannot read is one it never decides to deposit.
        That is the direction this fails in on purpose: the alternative would
        send the ship home on a session nobody had set up. It says which of the
        two it is on every reading; see `describeDeposit`. The bot re-selects the
        hold itself after a deposit, so this is a starting condition rather than
        something to keep watching.

        **The deposit itself needs no dock.** With the home structure on the
        grid and selected, the client offers an Access Dropbox on the Selected
        Item panel, and this bot drags each stack out of the Mining Hold into
        the window that opens and presses Transfer -- so the hold is emptied
        from space and the ship never enters the structure. It still has to
        *get* there: the button is on the Selected Item panel, so the structure
        has to be on this grid. Where the structure offers no dropbox, or the
        ship is not yet close enough, or the window is not one this bot can
        read, it docks and deposits the way it always did.
      + Set the overview to sort by distance with the nearest entry at the top.
      + In the ship UI, arrange the modules:
        + Put the gas harvesters in the **top** row, side by side.
        + Put the propulsion module **first in the middle row**.
        + Put anything that should simply keep running in the rest of the middle
          row.
        + Hide passive modules by disabling the check-box `Display Passive
          Modules`, so the rows the bot counts are the rows it can press.
      + **The orbit range needs no setup.** It used to: this list said the
        Selected Item panel's Orbit button inherits whatever range the client
        last used, that no command here could orbit at a *distance*, and that
        the operator therefore had to arrange it by hand. That was a true
        statement about this repository written down as a statement about the
        client. The cloud's own context menu offers `Orbit (5,000 m)`, and that
        entry opens a flyout of ranges of which `500 m` is one -- read live on
        2026-09-07. The bot commands the range in `orbit-range` (default
        `500 m`); see `orbitCascadeAt`.

        The client still reports an orbit that is too wide, as
        `deactivates without transfering ore to your cargo hold because your
        ship has strayed to a distance of ... beyond its mining range of ...`.
        **This bot reads that line and reports it, naming both distances, and
        does not act on it.** That is now a backstop against a range that is
        wrong for the fit rather than the only signal about a setup nobody could
        check -- and the repair is `orbit-range`, not a button pressed by hand.
        See `miningRangeRefusalFromGameLog`.
      + Name the bookmarks you are willing to be warped to so that they all
        start with the same prefix, and give that prefix to
        `retreat-bookmark-prefix`. Every bookmark matching it is a place this bot
        may run to unattended, **arrived at at 0 m**, so they want to be
        instadock-style bookmarks already placed for that.
      + **Have something on the overview at AU range wherever this bot works.**
        Once it is off the site it evades by warping between celestials, and the
        only thing it counts as one is an overview row whose Distance reads in
        AU -- which is what "off this grid" means and is the only property that
        matters when leaving. An overview preset that hides celestials leaves the
        evasion with nowhere to bounce to, and it says so rather than waiting
        quietly.
      + **A cloak, if the ship has one, is recognised only by its tooltip.** A
        module button carries no name of its own, so this bot hovers the modules
        it has not identified on the readings where it has nothing else to press,
        and looks for the client's own `Cloaking Device` in what comes back. That
        happens during quiet harvesting or not at all -- a session whose first
        hostile arrives in its first minute evades uncloaked. Nothing here needs
        the cloak in a particular slot, and a fit with no cloak in it evades
        without one on purpose; the status line says which of the three it is.

      ## Configuration Settings

      All settings are optional; you only need them where the default does not
      fit. Nothing here ships a default that names a structure, a corporation, a
      fleet or a system -- those are yours to write, and a bot that is given none
      of them names nowhere.

      + `anomaly-group` : the probe scanner's own `Group` column, for the sites
        this bot hunts. Defaults to `Gas Site`, which is the client's stock
        wording rather than anything about one wormhole. Matched against the
        Group cell, ignoring case and surrounding space, and whole unless it
        ends in `*` -- `anomaly-group=Gas*` takes anything whose Group starts
        that way. **A row whose Group cell this bot cannot read is declined**,
        never taken on the strength of its other columns: warping to a site
        nobody has identified is the expensive direction in a wormhole.
      + `anomaly-name` : the probe scanner's `Name` column, if you want to
        narrow further. **Unset means any name**, which is the useful default --
        the Group column is what says a site is a gas site, and the Name is the
        site's own designation. Set it and **both** have to hold: a row whose
        Group reads the hunted group but whose Name does not match is declined,
        and so is a row with no Name column to read. Same matching as
        `anomaly-group`, so a trailing `*` is a prefix.
      + `gas-cloud-name-prefix` : which clouds to harvest, matched against the
        overview's **Name** column. Unset means any harvestable cloud on the
        grid, which is the useful default -- a site's clouds differ by a
        trailing number rather than by kind. Set it to take only one family, and
        write it as the overview shows it: the Name column carries the cloud's
        own designation, not the generic `Harvestable Cloud` the Type column
        carries. Whichever clouds this leaves, the one taken is the one whose
        name carries the **highest trailing number** -- `Fullerite-C84` over
        `Fullerite-C50`, and `Fullerite-C100` over both, which is why the digits
        are parsed rather than the string sorted. See `trailingNumberFromName`.
      + `home-structure-name` : the overview name of the structure to deposit at,
        which is also the **second** place this bot will run to when it leaves.
        **No default** -- with none set, this bot has nowhere to deposit and one
        fewer place to retreat to, and the status line says so on every reading.
        Matched against the overview's Name column the way `anomaly-group` is
        matched against the scanner's Group: whole, ignoring case and surrounding
        space, with a trailing `*` meaning a prefix.
      + `retreat-bookmark-prefix` : the prefix marking bookmarks that are safe to
        run to, and the **first** place this bot leaves for. Defaults to `*`,
        which is a common convention rather than a claim about your bookmarks: a
        prefix is a pattern, and nothing here can tell you whether any bookmark
        actually matches it until a run reads the Locations window. Matched with
        `String.startsWith` against the **label** of a Locations row rather than
        against the whole row, which the client renders as the label and the
        folder joined -- so a folder named for your prefix does not make every
        bookmark in it a retreat target. Case is not folded: a marker you chose
        to be distinctive is one you can type consistently.
      + `friendly-ship-tag` : a substring marking a ship as one of yours. A ship
        whose name carries it reads friendly; **every other ship reads hostile,
        and so does every ship when this setting is unset.** That direction is
        deliberate and is not a default anyone should rely on being convenient:
        an unset tag means trust nobody, never trust everybody. Matched ignoring
        case, as a substring, so it can be a corporation ticker in brackets or a
        naming convention of your own.
      + `orbit-range` : the range to orbit a cloud at, as the client's own
        flyout writes it. Defaults to `500 m`. Must be one of the literals that
        flyout offers -- `500 m`, `1,000 m`, `2,500 m`, `5,000 m`, `7,500 m`,
        `10 km`, `15 km`, `20 km`, `25 km`, `30 km` -- including the comma,
        because the cascade matches the entry by equality. A value the flyout
        does not carry is a cascade that finds no entry and gives up, which the
        status line reports rather than silently orbiting at the client's
        default. See `orbitRangeMenuEntries`.
      + `dscan-interval-seconds` : how often to refresh the Directional Scanner.
        Defaults to 5. **This number is unmeasured** -- nothing has yet watched a
        ship arrive on this bot's D-Scan, so it is a starting point chosen to
        cost roughly one reading in ten rather than a figure derived from how
        long a hostile takes to arrive. It is a **floor** rather than a promise:
        this host stands down for five seconds after any *human* input, so a
        refresh can simply not go out, and what covers that is the staleness
        bound rather than the interval -- a scan older than
        `dscanStaleAfterIntervals` of these reads as *we do not know* and never
        as clean.
      + `bot-step-delay` : milliseconds between readings, e.g.
        `bot-step-delay=499`. Inherited from `eve-online-saxrat`'s own default
        rather than measured for this bot.

      When using more than one setting, start a new line for each setting in the
      text input field. Here is an example of a complete settings string -- the
      names in it are made up, and are there to show the shape rather than to be
      pasted:

      ```
   anomaly-group = Gas Site
   gas-cloud-name-prefix = Fullerite-
   home-structure-name = Example Refinery
   retreat-bookmark-prefix = *
   friendly-ship-tag = [EXMPL]
   dscan-interval-seconds = 5
      ```

-}
{-
   catalog-tags:eve-online,gas,harvesting,wormhole
-}


module Bot exposing
    ( State
    , botMain
    )

import BotLab.BotInterface_To_Host_2024_10_19 as InterfaceToHost
import Common.AppSettings as AppSettings
import Common.Basics exposing (stringContainsIgnoringCase)
import Common.DecisionPath exposing (describeBranch)
import Common.EffectOnWindow as EffectOnWindow exposing (MouseButton(..))
import Dict
import EveOnline.BotFramework
    exposing
        ( ReadingFromGameClient
        , ShipModulesMemory
        , menuCascadeCompleted
        , mouseClickOnUIElement
        , useMenuEntryInLastContextMenuInCascade
        , useMenuEntryWithTextContaining
        , useMenuEntryWithTextEqual
        )
import EveOnline.BotFrameworkSeparatingMemory
    exposing
        ( DecisionPathNode
        , EndDecisionPathStructure(..)
        , UpdateMemoryContext
        , askForHelpToGetUnstuck
        , branchDependingOnDockedOrInSpace
        , decideActionForCurrentStep
        , ensureInfoPanelLocationInfoIsExpanded
        , useContextMenuCascade
        , waitForProgressInGame
        )
import EveOnline.ParseUserInterface
import Json.Decode


{-| What this bot does with no settings at all.

Every value here is either the client's own stock wording (`anomaly-group`), a
convention that names nothing (`retreat-bookmark-prefix`), a number, or absent.
Nothing that identifies a structure, a corporation, a fleet or a system has a
default, and `run_gas_huffer.sh` passes no settings either, so an unconfigured
run of this bot names nowhere and trusts nobody.

-}
defaultBotSettings : BotSettings
defaultBotSettings =
    { anomalyGroup = "Gas Site"

    -- Unset means any name, and the asymmetry with `anomalyGroup` above is the
    -- point rather than an oversight: the Group column is what says a site is a
    -- gas site, so it carries a default, and the Name is the site's own
    -- designation, which nothing here can guess. See `anomalyVerdict` for why
    -- the two stay separate conditions rather than one.
    , anomalyName = Nothing

    -- Unset means any harvestable cloud, which is the widest useful answer and
    -- is safe in a way the tag below is not: the worst an unfiltered cloud list
    -- costs is harvesting the wrong gas, where an unfiltered *ship* list costs
    -- the ship.
    , gasCloudNamePrefix = Nothing

    -- No default, and there cannot be one: this names a structure in one
    -- wormhole belonging to one operator.
    , homeStructureName = Nothing
    , retreatBookmarkPrefix = "*"

    -- **The fail-closed one.** `Nothing` means every ship reads hostile -- see
    -- `hostileTrustFromSettings`, which is where that is decided, and
    -- `shipReadsFriendly`, which is the rule the rest of the bot will ask.
    , friendlyShipTag = Nothing
    , orbitRange = defaultOrbitRange
    , dscanIntervalSeconds = defaultDscanIntervalSeconds
    , botStepDelayMilliseconds = 499
    }


{-| How often the Directional Scanner is refreshed, absent a setting.

**Unmeasured, and stated as such rather than dressed up.** D-Scan is the only
instrument that sees a ship before it is on the overview, so the interval one
wants is as short as its cost allows -- but nobody has watched a hostile arrive
on this bot's D-Scan, and #458 records that no D-Scan row for a _ship_ has ever
been read here at all. Five seconds is roughly one reading in ten at the shipped
step delay, which is cheap enough to leave on and frequent enough to be worth
having; it is a starting point for #462 to replace with evidence, not a
threshold placed in a gap.

-}
defaultDscanIntervalSeconds : Int
defaultDscanIntervalSeconds =
    5


parseBotSettings : String -> Result String BotSettings
parseBotSettings =
    AppSettings.parseSimpleListOfAssignmentsSeparatedByNewlines
        ([ ( "anomaly-group"
           , valueTypeNonEmptyString
                (\group settings -> { settings | anomalyGroup = group })
           )
         , ( "anomaly-name"
           , valueTypeNonEmptyString
                (\name settings -> { settings | anomalyName = Just name })
           )
         , ( "gas-cloud-name-prefix"
           , valueTypeNonEmptyString
                (\prefix settings -> { settings | gasCloudNamePrefix = Just prefix })
           )
         , ( "home-structure-name"
           , valueTypeNonEmptyString
                (\name settings -> { settings | homeStructureName = Just name })
           )
         , ( "retreat-bookmark-prefix"
           , valueTypeNonEmptyString
                (\prefix settings -> { settings | retreatBookmarkPrefix = prefix })
           )
         , ( "friendly-ship-tag"
           , valueTypeNonEmptyString
                (\tag settings -> { settings | friendlyShipTag = Just tag })
           )
         , ( "orbit-range"
           , valueTypeNonEmptyString
                (\range settings -> { settings | orbitRange = range })
           )
         , ( "dscan-interval-seconds"
           , AppSettings.valueTypeInteger
                (\seconds settings -> { settings | dscanIntervalSeconds = seconds })
           )
         , ( "bot-step-delay"
           , AppSettings.valueTypeInteger
                (\delay settings -> { settings | botStepDelayMilliseconds = delay })
           )
         ]
            |> Dict.fromList
        )
        defaultBotSettings


{-| A setting that names one thing and is useless -- or dangerous -- empty.

The mission runner's PR #116 is the argument and it is copied here rather than
re-derived: an empty value already has two established meanings in this codebase
and neither can apply to an assignment whose whole value is empty.
`nonEmptySettingValue` reads an empty value as _unset_, which is how the ammo
swap is switched off from the web console without deleting the line, and
`splitSettingIntoNames` drops one because a trailing comma is how it gets
written by accident. Where the whole assigned value is empty there is nothing
left to read the intent from, so dropping it silently picks one meaning without
saying so -- this repo's signature failure.

**Every string setting this app has is guarded, and two of the five would be
actively dangerous unguarded.** `gas-cloud-name-prefix=` would make
`String.startsWith ""` true of every row on the grid, so the filter an operator
wrote to take one family of clouds would take every object there is;
`friendly-ship-tag=` would make `stringContainsIgnoringCase ""` true of every
ship name, which is the exact inversion of the fail-closed direction the tag
exists to hold -- "trust nobody" typed one keystroke short becomes "trust
everybody", silently, on a bot whose entire survival plan is to leave when it
sees a stranger.

The price is the one every other unusable value here already costs:
`BotFramework` answers a settings parse error with `InternalFinishSession`, so a
bad value typed into the web console mid-run ends the session rather than
quietly arming nothing.

-}
valueTypeNonEmptyString : (String -> BotSettings -> BotSettings) -> AppSettings.SettingValueType BotSettings
valueTypeNonEmptyString integrateSettingValue settingValueAsString =
    case String.trim settingValueAsString of
        "" ->
            Err emptySettingValueRejected

        trimmed ->
            Ok (integrateSettingValue trimmed)


{-| What an operator is told when a name setting is left empty. The framework
prepends the setting's own name, so this carries the reason and the fix.
-}
emptySettingValueRejected : String
emptySettingValueRejected =
    "this setting names one thing and was given nothing. Delete the line to leave it unset, or write the name after the '='."


type alias BotSettings =
    { anomalyGroup : String
    , anomalyName : Maybe String
    , gasCloudNamePrefix : Maybe String
    , homeStructureName : Maybe String
    , retreatBookmarkPrefix : String
    , friendlyShipTag : Maybe String
    , orbitRange : String
    , dscanIntervalSeconds : Int
    , botStepDelayMilliseconds : Int
    }


type alias State =
    EveOnline.BotFrameworkSeparatingMemory.StateIncludingFramework BotSettings BotMemory


{-| Everything this bot carries from one reading to the next.

Deliberately small, and every field here is something a single reading cannot
say. A reading's game-log entries are gone by the next reading, so a verdict
drawn from them has to be written here or it is seen once and then behaves
exactly as it did before -- the ammo swap's `loadRefusedByClient` is the worked
example, and `miningRangeRefusal` is this app's. The two counters are the same
argument about a repeat: how many readings in a row the bot has asked for
something the client has not answered is not a fact about this reading.

-}
type alias BotMemory =
    { readingsCount : Int
    , lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory

    -- How long the box in front of the bot has been there, and the one line
    -- said when the bot stops answering it. See `MessageBoxStandoff`.
    , messageBoxStandoff : Maybe MessageBoxStandoff
    , messageBoxLastChange : Maybe String

    -- The client's own statement that the orbit is too wide for the
    -- harvesters, carried forward with its age. Read by the status line and by
    -- no decision, deliberately -- see `miningRangeRefusalFromGameLog`.
    , miningRangeRefusal : Maybe MiningRangeRefusal
    , miningRangeLastChange : Maybe String

    -- How long the two things the harvest loop asks the client for have gone
    -- unanswered. Both bound a branch that would otherwise repeat forever on a
    -- hot path, which is #257's shape. See `harvestCountersAfterReading`.
    , harvestCounters : HarvestCounters

    -- How many presses of `Alt+F1` the client has left unanswered. Bounds
    -- `keepThePropulsionModuleRunning`, which sits above the retreat, so an
    -- unbounded version of it is a ship that never leaves a hostile grid. Reset
    -- outright the moment the module reads running. See
    -- `propulsionPressesAfterReading`.
    , propulsionPressesUnanswered : Int

    -- When the scan key last went out, and when a scan last came back. The
    -- second is what the grid verdict is allowed to believe, and it is here
    -- rather than derived from a reading because no reading says how old the
    -- rows in the D-Scan window are. See `dscanMemoryAfterReading`.
    , dscan : DscanMemory

    -- How long this evasion has run, how much of it was spent commanding a warp
    -- that did not start, and how long the cloak has gone unanswered. All three
    -- are things a single reading cannot say, and the first is what ends the
    -- session. See `evasionCountersAfterReading`.
    , evasion : EvasionCounters

    -- Said at the root on the one reading a commanded warp crosses
    -- `warpNotExecutingAlarmReadings` without ever taking, and on no other. The
    -- status line goes on carrying the count against the bound.
    , warpNotExecutingLastChange : Maybe String

    -- How many readings have been spent hovering module buttons whose tooltip
    -- is still unknown. Bounds `identifyTheModulesFitted`, which is the only
    -- thing in this app that can tell a cloak from a hardener.
    , modulesUnidentifiedReadings : Int

    -- The grid as it last read from a reading carrying a ship UI. A docked
    -- client will not answer a Directional Scan, so a docked reading's own
    -- verdict is a statement about the instrument rather than about the grid
    -- outside -- and the undock is judged on this instead. `Nothing` is a
    -- session that has never been in space, which reads as not clean.
    , lastGridVerdictInSpaceIsClean : Maybe Bool

    -- The dock the client has confirmed it is flying, and the evidence that it
    -- is still closing. What stops the dock being re-commanded every reading,
    -- which is what kept a mission runner 17 km off a station for eight
    -- minutes. See `DockingRunIn`.
    , dockingRunIn : Maybe DockingRunIn

    -- The deposit run under way, its own clock, and the client's own sentence
    -- saying the transfer landed. A reading's game-log entries are gone by the
    -- next reading, so the confirmation has to be latched here or it is seen
    -- once and the bot goes back to dragging. See `depositRunAfterReading`.
    , deposit : Maybe DepositRun

    -- How many wormholes this deposit trip has jumped trying to work back
    -- toward `home-structure-name`, and the solar system the ship was last
    -- known to be in. See `depositChainHopMemoryAfterReading`.
    , depositChainHop : DepositChainHopMemory
    }


{-| One message box, and how many consecutive readings it has survived.

The identity is the box's own words and buttons rather than its display region
-- see `messageBoxIdentity`. A box that changes its wording starts a fresh
count, which is the wanted direction: a dialog that is answering is not the
dialog this counter exists to give up on.

-}
type alias MessageBoxStandoff =
    { identity : String
    , readings : Int
    }


type alias BotDecisionContext =
    EveOnline.BotFrameworkSeparatingMemory.StepDecisionContext BotSettings BotMemory



-- Whom this bot is willing to share a grid with


{-| Which ships, if any, this bot reads as friendly.

One rule with two readers, which is what keeps the fail-closed direction from
being stated in one place and assumed in another. The status line asks it on
every reading through `describeHostileTrust`; #462's hostile detection will ask
it through `shipReadsFriendly` about each name the Directional Scanner and the
overview give it.

**`TrustNobody` is what an unset `friendly-ship-tag` means, and the asymmetry is
the whole point.** Wrong in that direction the bot leaves a site it could have
kept working, which costs a warp. Wrong in the other direction it keeps
harvesting beside a ship it has never seen before, which is what this bot's
entire survival plan exists to avoid -- and the failure would be silent, because
"nothing hostile on grid" is what the status line prints either way.

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

Matched as a substring and ignoring case, because the tag is a naming convention
rather than a name: a corporation ticker in brackets, a fleet marker, whatever
the operator writes. `TrustNobody` answers `False` for every name there is,
including the empty one -- and `valueTypeNonEmptyString` is what stops an empty
tag ever reaching `TrustShipsTagged`, where it would match every ship instead.

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
            "Friendly ships: those whose name carries '"
                ++ tag
                ++ "'; every other ship reads hostile."



-- Which site this bot would hunt


{-| The probe scanner's own column headers, named once each.

`ProbeScanResult.cellsTexts` is keyed by the header text of the column a cell
sits under, so these two strings are what every lookup and every sentence about
a lookup has to agree on. Written down once for #102's reason rather than
spelled at each site: a status line telling an operator to make the `Group`
column visible while the rule read some other key would present as a client that
is set up wrong, which is the one diagnosis that sends them nowhere near the bug.

-}
anomalyGroupColumn : String
anomalyGroupColumn =
    "Group"


anomalyNameColumn : String
anomalyNameColumn =
    "Name"


{-| The bookmark naming that stands in for a scan result.

`Reservoir` is the client's own word for the wormhole gas sites -- Ordinary and
Sizeable Perimeter Reservoir, Vast and Bountiful Frontier Reservoir, Vital and
Instrumental Core Reservoir -- so it is stock EVE terminology in exactly the
sense `Gas Site` is, and shipping it names nobody's wormhole, corporation or
bookmark folder. That is what keeps it a constant rather than a setting: #456's
rule is that anything identifying an _operator_ is a setting with no default in
code, and this identifies the game's own site family.

Matched as a substring ignoring case, because a bookmark's name is whatever the
operator typed around it -- `Reservoir 3`, `gas - vast frontier reservoir` --
where a probe scanner's Group cell is a field the client fills in.

-}
bookmarkedGasSiteMarker : String
bookmarkedGasSiteMarker =
    "Reservoir"


{-| Which sites this bot hunts, as the two independent conditions they are.

`anomaly-group` and `anomaly-name` name **different columns of the same row**,
and neither is derived from the other. That is #460's own emphasis and it is
worth saying why it is not merely tidy: folding them -- matching the name
against the Group cell, or letting a name match excuse a Group that does not
hold -- widens the filter in a direction nobody asked for, and the thing it
widens onto is "warp this ship into a site it has not identified".

`anomalyVerdict` keeps them as two entries in one list so that the independence
is structural rather than a promise a later edit can quietly break.

-}
type alias AnomalyFilter =
    { group : String
    , name : Maybe String
    }


anomalyFilterFromSettings : BotSettings -> AnomalyFilter
anomalyFilterFromSettings settings =
    { group = settings.anomalyGroup
    , name = settings.anomalyName
    }


describeAnomalyFilter : AnomalyFilter -> String
describeAnomalyFilter filter =
    anomalyGroupColumn
        ++ " '"
        ++ filter.group
        ++ "'"
        ++ (case filter.name of
                Nothing ->
                    " (any " ++ anomalyNameColumn ++ ")"

                Just name ->
                    " and " ++ anomalyNameColumn ++ " '" ++ name ++ "'"
           )


{-| What this bot makes of one probe-scanner row, and why it declined it.

**Three answers rather than two, and the middle one is the whole of #460.**
`Dict.get` answering `Nothing` for a column is the reading saying it _cannot
tell_ what this row is -- which is not the same fact as a cell that is there and
reads something else, and the two must not collapse. A site nobody has
identified is a site this ship would warp into blind, and in a wormhole that is
the expensive direction, so the unreadable column declines. It is
`loadRefusalFromGameLog`'s register applied to a column: absent evidence is
never dressed up as a finding.

Declining silently would only move the problem, though, which is why the column
rides on the answer. An operator watching a bot that hunts nothing has two very
different things to go and fix -- a scanner column they never made visible, or a
filter that names a group the sites here do not have -- and
`describeSiteSearch` can only tell them apart because this type does.

-}
type AnomalyVerdict
    = HuntThisAnomaly
    | ColumnIsNotInTheReading String
    | CellIsNotWhatIsHunted String String


{-| Every condition the filter puts on one row, asked in one place.

The list is what makes the two conditions independent rather than nested: one
entry per column, neither reading the other's cell, and a row is hunted only
where every entry declines to object. **An unset `anomaly-name` contributes no
entry at all**, which is what "unset means any name" has to mean -- not an entry
that always passes, since that is one edit away from an entry that passes
because it is comparing against the empty string.

`List.head` rather than every reason, because a status line wants one reason per
row and the first is the one to fix first: a `Group` column that is not there is
what stops the `Name` mattering.

-}
anomalyVerdict : AnomalyFilter -> Dict.Dict String String -> AnomalyVerdict
anomalyVerdict filter cellsTexts =
    let
        columnMustRead columnName wanted =
            case cellsTexts |> Dict.get columnName of
                Nothing ->
                    Just (ColumnIsNotInTheReading columnName)

                Just cellText ->
                    if siteCellMatches cellText wanted then
                        Nothing

                    else
                        Just (CellIsNotWhatIsHunted columnName cellText)
    in
    [ columnMustRead anomalyGroupColumn filter.group
    , filter.name |> Maybe.andThen (columnMustRead anomalyNameColumn)
    ]
        |> List.filterMap identity
        |> List.head
        |> Maybe.withDefault HuntThisAnomaly


{-| Whether one settings entry matches the cell the scanner shows.

`eve-online-saxrat`'s `anomalyNameMatches` (#188), ported: whole by default,
ignoring case and surrounding space, with a **trailing** `*` and only a trailing
one meaning a prefix. Exact stays the default for that file's reason -- widening
a site filter silently is how a bot ends up somewhere that kills it, and
`attack-object` records what an accidental substring cost once, which was a bot
firing at the wreck of the thing it had just killed.

One matcher for both columns rather than one each, because there is nothing
about a Group cell that wants different matching from a Name cell and two would
be two places to disagree. The shipped `Gas Site` carries no `*`, so the default
configuration is an exact, case-insensitive comparison.

-}
siteCellMatches : String -> String -> Bool
siteCellMatches cellText entry =
    let
        wanted =
            entry |> String.trim |> String.toLower

        found =
            cellText |> String.trim |> String.toLower
    in
    if String.endsWith "*" wanted then
        found |> String.startsWith (wanted |> String.dropRight 1 |> String.trimRight)

    else
        found == wanted


{-| The site this bot would take, and where it came from.

Two sources, in preference order, because they are not equally good evidence. A
scanned row carries the client's own `Group` cell, so the bot knows what it is
warping to; a bookmark carries only whatever the operator called it. The
bookmark is the fallback for the case #456 leaves open -- a site nobody has
scanned down this session -- and never outranks a row the scanner has classified.

-}
type SiteToHunt
    = ScannedAnomaly EveOnline.ParseUserInterface.ProbeScanResult
    | BookmarkedSite EveOnline.ParseUserInterface.LocationsWindowPlaceEntry


{-| The two windows the search reads, and nothing else.

A record of parsed windows rather than a whole `BotDecisionContext`, so that
`siteSearch` is a rule a case can hand a reading and execute. #106 is what the
other shape costs: a rule reachable only through a decision context is one
nothing can run, so it gets checked by being read instead, which is how a rule
that answers nothing passes for one that works.

-}
type alias SiteSearchReading =
    { probeScannerWindow : Maybe EveOnline.ParseUserInterface.ProbeScannerWindow
    , locationsWindow : Maybe EveOnline.ParseUserInterface.LocationsWindow
    }


{-| Everything one reading has to say about where this bot would go.

Both windows' _presence_ is carried separately from what they held, because
"the window is not open" and "the window is open and holds nothing that
matches" are different states wanting different fixes from the operator, and a
list that is empty for either reason cannot tell them apart.

-}
type alias SiteSearch =
    { filter : AnomalyFilter
    , probeScannerIsOpen : Bool
    , anomalyVerdicts : List AnomalyVerdict
    , locationsWindowIsOpen : Bool
    , bookmarkedSites : List String
    , hunted : Maybe SiteToHunt
    }


{-| The one declaration that decides where this bot would go, with two readers.

The decision branch and the status line both call it, through
`siteSearchFromContext`, and that is deliberate rather than incidental: #102 is
one fact settled in one place and read in another, and the way that fails here
would be a status line reporting a site the decision was not acting on. Two
callers of one pure function over one reading cannot disagree.

**Nothing here flies anywhere; `warpToTheHuntedSite` does.** This answers which
site, and #461's harvest loop takes the answer. The bookmark half of that is
`eve-online-mining-bot`'s `useContextMenuOnLocationWithMatchingName` reduced to
its locations-window arm -- `useContextMenuCascade` over the `PlaceEntry` whose
name matched -- rather than a second mechanism for the same job, which is the
kind of thing this codebase keeps having to reconcile later.

`anomalyVerdicts` keeps a verdict for **every** row rather than only the
declined ones, so that the status line can report a missing `Group` column on
the readings where some other row did match. A column absent from half the
scanner is worth saying whether or not the bot found something to do.

-}
siteSearch : AnomalyFilter -> SiteSearchReading -> SiteSearch
siteSearch filter reading =
    let
        isOpen window =
            window |> Maybe.map (always True) |> Maybe.withDefault False

        scanResults =
            reading.probeScannerWindow
                |> Maybe.map .scanResults
                |> Maybe.withDefault []

        verdicts =
            scanResults |> List.map (.cellsTexts >> anomalyVerdict filter)

        scannedAnomaly =
            List.map2 Tuple.pair scanResults verdicts
                |> List.filter (Tuple.second >> (==) HuntThisAnomaly)
                |> List.head
                |> Maybe.map (Tuple.first >> ScannedAnomaly)

        bookmarks =
            reading.locationsWindow
                |> Maybe.map .placeEntries
                |> Maybe.withDefault []
                |> List.filter
                    (.mainText >> stringContainsIgnoringCase bookmarkedGasSiteMarker)
    in
    { filter = filter
    , probeScannerIsOpen = isOpen reading.probeScannerWindow
    , anomalyVerdicts = verdicts
    , locationsWindowIsOpen = isOpen reading.locationsWindow
    , bookmarkedSites = bookmarks |> List.map .mainText
    , hunted =
        case scannedAnomaly of
            Just anomaly ->
                Just anomaly

            Nothing ->
                bookmarks |> List.head |> Maybe.map BookmarkedSite
    }


siteSearchFromContext : BotDecisionContext -> SiteSearch
siteSearchFromContext context =
    siteSearch (anomalyFilterFromSettings context.eventContext.botSettings)
        { probeScannerWindow = context.readingFromGameClient.probeScannerWindow
        , locationsWindow = context.readingFromGameClient.locationsWindow
        }


{-| What an operator reads about the hunt, on every reading.

Three clauses, because a bot that is hunting nothing has three separate things
that could be wrong with it and the operator fixes a different one for each.
Kept as three declarations over the one record rather than one long expression
so that a case can execute each of them on its own.

-}
describeSiteSearch : SiteSearch -> String
describeSiteSearch search =
    [ describeSiteHunted search
    , describeProbeScannerForHunting search
    , describeBookmarksForHunting search
    ]
        |> String.join " "


describeSiteHunted : SiteSearch -> String
describeSiteHunted search =
    case search.hunted of
        Just (ScannedAnomaly anomaly) ->
            "Site: hunting the scanned anomaly "
                ++ describeAnomalyIdentity anomaly
                ++ "."

        Just (BookmarkedSite bookmark) ->
            "Site: nothing scanned reads "
                ++ describeAnomalyFilter search.filter
                ++ ", so falling back to the bookmark '"
                ++ bookmark.mainText
                ++ "'."

        Nothing ->
            "Site: NOTHING TO HUNT."


{-| A scanned row named the way the scanner names it.

The ID first, because it is the one cell that tells two sites of the same kind
apart, and the Name after it where the column is there to read. Neither is
defaulted into a plausible-looking string: a row whose ID column is absent says
so, since an operator chasing a site by a name this bot invented is chasing
nothing.

-}
describeAnomalyIdentity : EveOnline.ParseUserInterface.ProbeScanResult -> String
describeAnomalyIdentity anomaly =
    let
        cell columnName =
            anomaly.cellsTexts |> Dict.get columnName
    in
    "'"
        ++ (cell "ID" |> Maybe.withDefault "<no ID column>")
        ++ "'"
        ++ (case cell anomalyNameColumn of
                Just name ->
                    " (" ++ name ++ ")"

                Nothing ->
                    ""
           )


describeProbeScannerForHunting : SiteSearch -> String
describeProbeScannerForHunting search =
    if not search.probeScannerIsOpen then
        "The probe scanner window is not open, so nothing can be scanned down at all -- see this bot's client-setup list."

    else if List.isEmpty search.anomalyVerdicts then
        "The probe scanner is open and shows no results."

    else
        "Probe scanner: "
            ++ String.fromInt
                (search.anomalyVerdicts
                    |> List.filter ((==) HuntThisAnomaly)
                    |> List.length
                )
            ++ " of "
            ++ String.fromInt (List.length search.anomalyVerdicts)
            ++ " result(s) read "
            ++ describeAnomalyFilter search.filter
            ++ "."
            ++ describeColumnsTheScannerDoesNotShow search


{-| The clause #460 exists for, said in the operator's own terms.

A run that hunts nothing because the `Group` column is hidden and a run that
hunts nothing because this wormhole holds no gas site read identically from
outside, and only one of them is fixed by touching the client. So the absent
column is named, counted, and told apart from a Group cell that simply says
something else.

Empty on a reading where every column was there, because a clause that appears
on every reading is one an operator stops seeing.

-}
describeColumnsTheScannerDoesNotShow : SiteSearch -> String
describeColumnsTheScannerDoesNotShow search =
    [ anomalyGroupColumn, anomalyNameColumn ]
        |> List.filterMap
            (\columnName ->
                case
                    search.anomalyVerdicts
                        |> List.filter ((==) (ColumnIsNotInTheReading columnName))
                        |> List.length
                of
                    0 ->
                        Nothing

                    absent ->
                        Just
                            (" NO '"
                                ++ columnName
                                ++ "' COLUMN on "
                                ++ String.fromInt absent
                                ++ " of "
                                ++ String.fromInt (List.length search.anomalyVerdicts)
                                ++ " result(s): this bot cannot tell what those sites are, so it declines them rather than warping to something it has not identified. Make that column visible in the probe scanner window."
                            )
            )
        |> String.join ""


describeBookmarksForHunting : SiteSearch -> String
describeBookmarksForHunting search =
    if not search.locationsWindowIsOpen then
        "The Locations window is not open, so there is no bookmark fallback -- which is a different thing from having no '"
            ++ bookmarkedGasSiteMarker
            ++ "' bookmark, and wants a different fix."

    else
        case List.length search.bookmarkedSites of
            0 ->
                "Locations: open, and no bookmark's name carries '"
                    ++ bookmarkedGasSiteMarker
                    ++ "'."

            count ->
                "Locations: "
                    ++ String.fromInt count
                    ++ " bookmark(s) whose name carries '"
                    ++ bookmarkedGasSiteMarker
                    ++ "'."



-- Which cloud on the grid this bot would harvest


{-| What the overview's **Type** column reads for a gas cloud.

Measured live on 2026-09-04, where a cloud renders as

    '-' | 'Harvestable Cloud' | 'Fullerite-C84' | 'Harvestable Cloud (Fullerite-C84)' | '833 m'

so the Type column carries this generic wording for every cloud in the site and
the **Name** column carries the cloud's own designation. That split is the whole
reason `gas-cloud-name-prefix` is matched against the Name while "is this a
cloud at all" is asked of the Type: the designation differs from site to site --
the operator's own spec said `Fullerite-N` and the grid said `Fullerite-C` --
and the Type does not.

**Matched as a substring**, which is the looser direction this codebase usually
refuses and is chosen here with the reason stated. `attack-object` records what
a substring would cost where a wider name contains a narrower one: a wreck's
Type is its owner's name with `Wreck` appended, so a substring rule there would
have had the bot open fire on the corpse of what it had just killed, forever,
since a wreck cannot die. There is no such pair here -- the wider strings this admits
are the client's own longer renderings of the same fact, `Harvestable Cloud
(Fullerite-C84)` being one of them in the very row above, and which of the two
an overview preset puts in the column an operator made visible is not something
a reading can say. What a wrong match costs is also different in kind: a lock
and a harvester cycle on something that yields nothing, reported by the hold's
own gauge, rather than a gun pointed at the wrong object.

-}
harvestableCloudTypeMarker : String
harvestableCloudTypeMarker =
    "Harvestable Cloud"


{-| Whether an overview row is really on screen.

The overview virtualises: every object in space has an entry in the UI tree, but
only the rows that fit are rendered, and the rest keep whatever position they
last held while being recycled. So a hidden entry reports a perfectly plausible
region pointing at a row that now belongs to something else, and clicking it is
worse than a no-op -- it acts on the wrong object. `_display` is what
distinguishes them; the region does not.

**This is the standing rule for every overview consumer in this repo** rather
than a precaution taken here, and #461 restates it because everything this bot
does on a grid starts from one of these rows: the click that selects the cloud
for the Selected Item panel's Orbit button, and the Ctrl+click that locks it. A
cloud chosen off a hidden row is a ship orbiting and locking whatever was
recycled into its place -- and the log would name the cloud throughout, because
the row the bot read is not the row the click landed on.

-}
overviewEntryIsDisplayed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
overviewEntryIsDisplayed entry =
    entry.uiNode.uiNode.dictEntriesOfInterest
        |> Dict.get "_display"
        |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.bool >> Result.toMaybe)
        |> Maybe.withDefault True


{-| The number a cloud's own designation ends in, where it ends in one.

**The digits are parsed; the string is not sorted.** `Fullerite-C84` has to beat
`Fullerite-C50`, and a lexical sort gets that pair right by luck -- `8` sorts
after `5`. It gets `Fullerite-C100` against `Fullerite-C84` wrong, because `1`
sorts before `8`, and the site holding a three-digit cloud is exactly the site
where taking the wrong one costs the most.

**A name ending in no digits answers `Nothing`, and `Nothing` is not zero.**
That is `loadRefusalFromGameLog`'s register applied to an ordering: a
designation this bot cannot rank is one it has no opinion about, where zero is
an opinion -- the lowest one available. Read as zero, a cloud named
`Harvestable Cloud` sorts behind every numbered cloud and is taken only when
there are none, which is the reading that would never take it **when it is the
only cloud on the grid**. `gasCloudOrder` ranks it last explicitly instead, so
it loses to anything numbered and still wins when nothing else is there.

-}
trailingNumberFromName : String -> Maybe Int
trailingNumberFromName name =
    let
        digitsFromTheEnd remaining collected =
            case remaining |> String.right 1 of
                "" ->
                    collected

                lastCharacter ->
                    if lastCharacter |> String.all Char.isDigit then
                        digitsFromTheEnd (remaining |> String.dropRight 1) (lastCharacter ++ collected)

                    else
                        collected
    in
    digitsFromTheEnd (String.trim name) "" |> String.toInt


{-| The order clouds are taken in: highest trailing number first, unrankable
last.

**This is the fallback order, used only among candidates nothing has already
claimed** -- see `gasCloudAlreadyClaimed` and `cloudSearch`'s own doc comment for
why a lock or a lock in progress outranks it.

A `comparable` for `List.sortBy` rather than a comparison written at the call
site, and a **pair** rather than one number, because the two facts being ordered
are of different kinds. The first element separates rankable from unrankable, so
nothing the second element can hold puts a name with no number ahead of a name
that has one; the second is the number negated, so the largest sorts first.
Folding the two -- ranking an unrankable name as `0`, or as a very large
negative -- is exactly what `trailingNumberFromName`'s doc comment refuses, in
the one place the refusal could be undone without changing that function at all.

A rule over the name alone, so a case can hand it a list of strings and read the
order back rather than assembling a reading to ask it.

-}
gasCloudOrder : String -> ( Int, Int )
gasCloudOrder name =
    case trailingNumberFromName name of
        Just number ->
            ( 0, negate number )

        Nothing ->
            ( 1, 0 )


{-| Whether the client already reads this cloud as locked or as locking.

`cloudSearch` asks this **before** the trailing-number order, which is the fix
for a real live failure (run 4, 2026-09-07): a site held `Fullerite-C84` and
`Fullerite-C50`, `gasCloudOrder` picked C84 for its higher trailing number, and
the bot spent the rest of the run asking the client to select and lock C84 while
C50 sat locked in the ship's own target bar the whole time -- confirmed live by
the operator watching the client, and never so much as looked at, because
`chosen` is re-derived fresh every reading with nothing remembering that a lock
was already held.

Both indications are read off the row being ranked, so this needs no memory of
its own and cannot go stale the way a remembered choice would: once the claimed
cloud is mined out or the ship leaves for a new site, it is simply gone from the
rows being ranked on the next reading, and the fallback order in `gasCloudOrder`
picks among whatever candidates are left -- there is no separate "forget the old
cloud" step to write or to get wrong.

-}
gasCloudAlreadyClaimed : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
gasCloudAlreadyClaimed entry =
    entry.commonIndications.targetedByMe || entry.commonIndications.targeting


{-| Whether one cloud's designation is one `gas-cloud-name-prefix` asks for.

A prefix rather than a substring or a whole match, which is what the setting's
name says and what the designations are shaped for: `Fullerite-` names a family
and the trailing number names the member. Compared trimmed and ignoring case,
for `siteCellMatches`' reasons. An unset prefix takes every cloud, and an
**empty** one can never reach here at all -- `valueTypeNonEmptyString` refuses
it, which matters more for this setting than for most, since `String.startsWith
""` is true of every row on the grid.

-}
gasCloudNameMatchesPrefix : Maybe String -> String -> Bool
gasCloudNameMatchesPrefix prefix name =
    case prefix of
        Nothing ->
            True

        Just wanted ->
            (name |> String.trim |> String.toLower)
                |> String.startsWith (wanted |> String.trim |> String.toLower)


{-| What one reading has to say about the clouds on this grid.

Every count here is a **reason a row was passed over**, kept separately rather
than folded into one number, because they are fixed in different places: rows
the client is not rendering are a scrolled overview, rows with no Name are an
overview column an operator never made visible, and rows the prefix declined are
a setting. A single "no cloud to harvest" would send them to the wrong one of
the three -- which is `describeSiteSearch`'s argument one window along.

`unrankableNames` is carried for the same reason and is not a decline: those
clouds are candidates, ranked last, and the count exists so that a run taking an
unnumbered cloud says so rather than looking like a run that ignored the
ordering.

`chosenIsAlreadyClaimed` is carried for the same reason as both of those: it is
what lets `describeCloudSearch` say _why_ `chosen` won, rather than always
crediting the trailing-number order when a lock already held is what actually
decided it.

-}
type alias CloudSearch =
    { prefix : Maybe String
    , cloudRowsInTheReading : Int
    , hiddenCloudRows : Int
    , namelessCloudRows : Int
    , declinedByThePrefix : Int
    , namesInTheOrderTheyWouldBeTaken : List String
    , unrankableNames : List String
    , chosen : Maybe EveOnline.ParseUserInterface.OverviewWindowEntry
    , chosenIsAlreadyClaimed : Bool
    }


{-| The one declaration that decides which cloud this bot harvests.

A rule over the prefix and the overview's rows rather than over a
`BotDecisionContext`, so a case can hand it really parsed rows and execute it.
#106 records what the other shape costs: a rule reachable only through a
decision context is one nothing can run, so it gets checked by being read, which
is how a rule that answers nothing passes for one that works.

Three readers -- the decision, the status line and
`updateMemoryForNewReadingFromGame`, through `cloudSearchFromReading`. That is
#102's shape, and the way it would fail here is a status line naming a cloud the
ship is not orbiting.

**A cloud the client already reads as locked or as locking outranks every other
candidate**, ahead of the trailing-number order `gasCloudOrder` alone would give.
Nothing here remembers _which_ cloud a previous reading chose -- `chosen` is
re-derived fresh from this reading's own rows every time, which is exactly what
let a real run (#485, live on 2026-09-07) pick `Fullerite-C84` over
`Fullerite-C50` by trailing number and spend the whole session asking the client
to select and lock C84, never once considering that C50 was already locked in
the ship's own target bar. `HarvestSituation.cloudReadsLocked` is asked only of
whichever cloud `chosen` names, so a choice that cannot see an existing lock can
never make use of one. See `gasCloudAlreadyClaimed` for why this needs no memory
of its own and cannot outlive the lock it is about.

-}
cloudSearch : Maybe String -> List EveOnline.ParseUserInterface.OverviewWindowEntry -> CloudSearch
cloudSearch prefix overviewEntries =
    let
        cloudRows =
            overviewEntries
                |> List.filter
                    (.objectType
                        >> Maybe.map (stringContainsIgnoringCase harvestableCloudTypeMarker)
                        >> Maybe.withDefault False
                    )

        displayedCloudRows =
            cloudRows |> List.filter overviewEntryIsDisplayed

        namedCloudRows =
            displayedCloudRows
                |> List.filterMap
                    (\entry -> entry.objectName |> Maybe.map (\name -> ( name, entry )))

        wanted =
            namedCloudRows
                |> List.filter (Tuple.first >> gasCloudNameMatchesPrefix prefix)
                |> List.sortBy
                    (\( name, entry ) ->
                        ( if gasCloudAlreadyClaimed entry then
                            0

                          else
                            1
                        , gasCloudOrder name
                        )
                    )

        wantedNames =
            wanted |> List.map Tuple.first
    in
    { prefix = prefix
    , cloudRowsInTheReading = List.length cloudRows
    , hiddenCloudRows = List.length cloudRows - List.length displayedCloudRows
    , namelessCloudRows = List.length displayedCloudRows - List.length namedCloudRows
    , declinedByThePrefix = List.length namedCloudRows - List.length wanted
    , namesInTheOrderTheyWouldBeTaken = wantedNames
    , unrankableNames = wantedNames |> List.filter (trailingNumberFromName >> (==) Nothing)
    , chosen = wanted |> List.head |> Maybe.map Tuple.second
    , chosenIsAlreadyClaimed =
        wanted
            |> List.head
            |> Maybe.map (Tuple.second >> gasCloudAlreadyClaimed)
            |> Maybe.withDefault False
    }


cloudSearchFromReading : BotSettings -> ReadingFromGameClient -> CloudSearch
cloudSearchFromReading settings readingFromGameClient =
    cloudSearch settings.gasCloudNamePrefix
        (readingFromGameClient.overviewWindows |> List.concatMap .entries)


{-| What an operator reads about the clouds, on every reading with a grid.

Says which cloud was chosen **and why it beat the others**, because "the highest
trailing number" is the one thing about this bot that is easy to get wrong
silently: a lexical sort agrees with the numeric one on most pairs, so a run
that had reverted to one would look correct until the day a site held a
three-digit cloud. Since #485 that reason can also be "already locked or
locking" -- see `gasCloudAlreadyClaimed` -- and the clause says which of the two
it was rather than always crediting the trailing number.

-}
describeCloudSearch : CloudSearch -> String
describeCloudSearch search =
    let
        passedOver =
            [ ( search.hiddenCloudRows
              , "not rendered by the client, so their positions belong to whatever was recycled into them"
              )
            , ( search.namelessCloudRows
              , "with no readable Name column -- the column both the ordering and 'gas-cloud-name-prefix' read"
              )
            , ( search.declinedByThePrefix
              , "named for something other than '"
                    ++ Maybe.withDefault "" search.prefix
                    ++ "'"
              )
            ]
                |> List.filter (Tuple.first >> (<) 0)
                |> List.map
                    (\( count, why ) -> String.fromInt count ++ " " ++ why)

        passedOverClause =
            if List.isEmpty passedOver then
                ""

            else
                " Passed over: " ++ String.join "; " passedOver ++ "."
    in
    (case search.chosen of
        Nothing ->
            "Clouds: NONE TO HARVEST out of "
                ++ String.fromInt search.cloudRowsInTheReading
                ++ " '"
                ++ harvestableCloudTypeMarker
                ++ "' row(s) on the overview."

        Just _ ->
            "Clouds: harvesting '"
                ++ (search.namesInTheOrderTheyWouldBeTaken |> List.head |> Maybe.withDefault "")
                ++ "', "
                ++ (if search.chosenIsAlreadyClaimed then
                        "already locked or locking"

                    else
                        "the highest trailing number"
                   )
                ++ " of "
                ++ String.fromInt (List.length search.namesInTheOrderTheyWouldBeTaken)
                ++ " candidate(s) ["
                ++ String.join ", " search.namesInTheOrderTheyWouldBeTaken
                ++ "]"
                ++ (if List.isEmpty search.unrankableNames then
                        "."

                    else
                        ", of which "
                            ++ String.fromInt (List.length search.unrankableNames)
                            ++ " carry no trailing number and are ranked last rather than as zero."
                   )
    )
        ++ passedOverClause



-- What the client says when the orbit is too wide for the harvesters


{-| The client's own account of an orbit the harvesters cannot reach across,
carried forward with its age.

The numbers are kept **as the client wrote them** rather than parsed into
metres. Nothing here does arithmetic on them; what they are for is an operator
reading a status line and going to fix the Orbit button, and a distance this bot
reformatted is one they cannot match against what the client told them.

-}
type alias MiningRangeRefusal =
    { strayedToMeters : String
    , miningRangeMeters : String
    , readingsSince : Int
    }


harvesterDeactivationMarker : String
harvesterDeactivationMarker =
    "deactivates without transfering ore"


harvesterStrayedMarker : String
harvesterStrayedMarker =
    "strayed to a distance of"


harvesterMiningRangeMarker : String
harvesterMiningRangeMarker =
    "beyond its mining range of"


{-| Whether a game-log entry is on the channel this bot reads.

`(notify)` is where the client puts its refusals, and it is the channel
`loadRefusalFromGameLog` already uses in two other apps here. Worth asking
rather than assuming: #41's locked-gate sentence arrives on `info` instead, and
a matcher pointed at the wrong channel is a guard that can never fire and looks
exactly like a client that never complains.

-}
gameLogEntryIsFromNotifyChannel : EveOnline.ParseUserInterface.GameLogEntry -> Bool
gameLogEntryIsFromNotifyChannel entry =
    entry.channel
        |> Maybe.map (stringContainsIgnoringCase "notify")
        |> Maybe.withDefault False


{-| The one thing that ever tells this bot its orbit is too wide, read and
**never acted on**.

The client writes, on `(notify)`:

    <harvester> deactivates without transfering ore to your cargo hold because
    your ship has strayed to a distance of 1628.94 m, beyond its mining range of
    1500.00 m.

so both numbers are there for the taking, and the temptation is to take them and
re-orbit closer. **Nothing here does, and that is the decision rather than an
omission.** No command in this repository orbits at a _distance_: the Selected
Item panel's Orbit button orbits at whatever range the client last used, and
that range is remembered by the client rather than stated in any reading. So a
bot acting on this line could only press the same button again, read the same
refusal again, and press again -- a bot that silently re-orbits forever, which is
the failure this repo keeps paying for. The repair is a client setting an
operator changes once, and what this rule owes them is the two numbers.

**Three substrings rather than one.** `deactivates without transfering ore` is
the client's own sentence, misspelling and all, and it is what makes this the
harvester's refusal rather than any other module's; the two markers below are
also what the numbers are sliced after, so an extraction can never succeed on a
sentence the matcher would have declined -- `gateKeyClosingMarker`'s
arrangement. A number that cannot be read declines the whole entry rather than
being defaulted, because a status line naming a distance this bot invented is
worse than one saying nothing.

-}
miningRangeRefusalFromGameLog : ReadingFromGameClient -> Maybe { strayedToMeters : String, miningRangeMeters : String }
miningRangeRefusalFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filterMap
            (\entry ->
                if stringContainsIgnoringCase harvesterDeactivationMarker entry.text then
                    Maybe.map2
                        (\strayed range ->
                            { strayedToMeters = strayed, miningRangeMeters = range }
                        )
                        (numberAfterMarker harvesterStrayedMarker entry.text)
                        (numberAfterMarker harvesterMiningRangeMarker entry.text)

                else
                    Nothing
            )
        |> List.head


{-| The number the client wrote straight after one of its own phrases.

Sliced out of the **lower-cased** text on both sides, so the marker can be
matched ignoring case without a second index into a differently cased string.
The characters taken are digits, `.` and `,` -- the client writes `1628.94` and
would write `11,628.94` -- and nothing else, so the trailing `m` stops it.

An empty result answers `Nothing` rather than `""`: a marker that matched with
no number after it is the client having written something this rule does not
understand, and reporting that as a distance is the fabrication
`miningRangeRefusalFromGameLog` exists not to make.

-}
numberAfterMarker : String -> String -> Maybe String
numberAfterMarker marker text =
    let
        lowered =
            String.toLower text
    in
    lowered
        |> String.indexes (String.toLower marker)
        |> List.head
        |> Maybe.andThen
            (\markerStart ->
                case
                    lowered
                        |> String.dropLeft (markerStart + String.length marker)
                        |> String.trimLeft
                        |> takeWhileNumeric
                of
                    "" ->
                        Nothing

                    number ->
                        Just number
            )


takeWhileNumeric : String -> String
takeWhileNumeric text =
    case text |> String.left 1 of
        "" ->
            ""

        firstCharacter ->
            if firstCharacter |> String.all (\character -> Char.isDigit character || character == '.' || character == ',') then
                firstCharacter ++ takeWhileNumeric (String.dropLeft 1 text)

            else
                ""


{-| The refusal as it stands after this reading.

A fresh sighting replaces whatever was there and resets the age; a reading with
none ages the one already held rather than dropping it, because the whole point
of writing it down is that the entry itself is gone by the next reading. Nothing
expires it within a session -- an expiry would be a number with no evidence
behind it, and the age already says how stale the sighting is, which is
`quickMessage`'s arrangement for the same problem.

-}
miningRangeRefusalAfterReading :
    { before : Maybe MiningRangeRefusal
    , refusalNow : Maybe { strayedToMeters : String, miningRangeMeters : String }
    }
    -> Maybe MiningRangeRefusal
miningRangeRefusalAfterReading { before, refusalNow } =
    case refusalNow of
        Just refusal ->
            Just
                { strayedToMeters = refusal.strayedToMeters
                , miningRangeMeters = refusal.miningRangeMeters
                , readingsSince = 0
                }

        Nothing ->
            before |> Maybe.map (\held -> { held | readingsSince = held.readingsSince + 1 })


{-| The clause an operator acts on, naming both distances.

Both, rather than the difference or a verdict, because the fix is a number they
type into the client and neither one alone is it. The age is printed for the
same reason `quickMessage`'s is: a refusal from four hundred readings ago and one
from this reading want very different responses, and a clause that carried the
sentence without the age reads identically for both.

-}
describeMiningRange : Maybe MiningRangeRefusal -> String
describeMiningRange refusal =
    case refusal of
        Nothing ->
            "Harvester range: the client has not complained about the orbit this session."

        Just present ->
            "HARVESTER OUT OF RANGE: the client says the ship strayed to "
                ++ present.strayedToMeters
                ++ " m, beyond a mining range of "
                ++ present.miningRangeMeters
                ++ " m ("
                ++ (if present.readingsSince == 0 then
                        "on this reading"

                    else
                        String.fromInt present.readingsSince ++ " reading(s) ago"
                   )
                ++ "). Nothing here can orbit at a distance, so this is reported and not corrected -- set the Orbit button's range by hand and restart."



-- Running the modules


{-| The keys held down together, as one press.

Written as the list of codes rather than as the effects, so `stepPressedExactly`
can compare what a step pressed against what this bot meant to press. That
comparison has to be exact rather than "contains", because `Alt+F1` and `F1` are
two different commands on this ship -- the propulsion module and the first
harvester -- and a settling window that could not tell them apart would let one
press suppress the other's.

-}
propulsionModuleHotkey : List EffectOnWindow.VirtualKeyCode
propulsionModuleHotkey =
    [ EffectOnWindow.vkey_MENU, EffectOnWindow.vkey_F1 ]


{-| The hotkey for one module in the ship UI's **top** row, by position.

With the default EVE keybinds F1-F4 activate the first four high-slot modules
directly, which is one effect where a click on the module button is a move and a
press with a settling window of its own. Only the first four get a hotkey; the
rest fall back to the button.

The index is the module's place in the row **sorted by x**, never its place in
the parser's list -- see `moduleButtonsLeftToRight`.

-}
topRowModuleHotkeyFromIndex : Int -> Maybe EffectOnWindow.VirtualKeyCode
topRowModuleHotkeyFromIndex index =
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


{-| One module row, in the order the client draws it.

**Sorted by x, never taken by index off the parsed list**, which is this repo's
standing rule about module rows: the parser drops any node whose display region
it cannot read, so a slot can leave and rejoin while nothing moves on screen,
and an index into that list then names a different module. It cost a live run a
click on a neighbouring module once.

It matters more here than it usually does. The two gas harvesters sit side by
side in the top row **sharing a `_name` and an icon texture**, measured on the
hull #456 was written from -- so position is not merely the safer identity, it
is the only one there is.

-}
moduleButtonsLeftToRight : List EveOnline.ParseUserInterface.ShipUIModuleButton -> List EveOnline.ParseUserInterface.ShipUIModuleButton
moduleButtonsLeftToRight =
    List.sortBy (.uiNode >> .totalDisplayRegion >> .x)


{-| Whether a module button says the module is doing something.

**This is the question #456 records as unsettled, answered from the corpus
rather than from a live read, and it is the weakest thing in this change.** The
issue asks for a live sample of a gas harvester being switched off and on --
nobody has watched one, every reading taken on 2026-09-04 was with both
harvesters already running -- and none was available when this was written. What
is available is #286's measurement of the same three dictionary entries over
**61,948 module observations** across 34 recorded runs of two other bots, and it
says two things that decide this without needing to know whether a harvester
behaves like a weapon or like a propulsion module:

  - `isInActiveState` is not a toggle at all. It is `not isDeactivating`, exact
    complements with no exceptions anywhere in that corpus, and it reads `True`
    for a module that is running **and** for a module that is off and idle. It
    is close to a constant, so a rule reading it as "switched on" would press a
    harvester that was already running -- and a module button is a toggle, so
    that press switches it **off**.
  - `ramp_active` is absent from the tree exactly when the `ShipModuleButtonRamps`
    widget does not exist, which is when the module is not cycling. On the
    20,095 observations where it is absent, nothing was running; it is created
    when a module starts and destroyed when it stops.

So the reading here is **the ramp widget's existence and not its value**: a
module whose `ramp_active` is present is cycling, whether this reading caught it
between cycles (`Just False`, which is what a weapon's duty cycle does) or in
one (`Just True`, which is what a latch does). That is the one answer that is
right whichever of the two a gas harvester turns out to be, which is what makes
it the safe thing to ship against an unsettled question.

**It fails towards not pressing.** A harvester this rule cannot tell is running
is one the bot leaves alone, so the cost of being wrong is a hold that does not
fill -- visible in the status line and in the gauge -- rather than a bot toggling
a module off and on forever, which is #12, #34, #35, #76 and #286 and is the
failure the issue names by number.

**#465 asks whether the propulsion module wants a different field, and the
answer is that it wants this same one read from the other end.** saxrat's
`deactivatePropulsionModuleBeforeWarping` reads `.isActive` and #465 is right
that it is correct to -- but `.isActive` **is** `ramp_active`, the very entry
this reads, so the two rules differ in which of its three values they act on
rather than in which field they consult. Each takes the half that is strong
evidence for its own press, and neither presses on the middle:

  - a _deactivation_ has to be sure the module is **on**, and `Just True` is the
    only value that says so. saxrat's rule presses on that and declines both
    `Just False` and an absent widget.
  - an _activation_ has to be sure it is **off**, and the widget being **absent**
    is the only value that says so -- 20,095 observations of it in #286 and not
    one of them a module that was running. This rule presses on that and
    declines both `Just False` and `Just True`.

So `Just False` is the value neither can read safely and neither acts on, and a
propulsion module ought never to produce it anyway: #35 watched a middle-slot
module go `True` at 60-70 s and stay there, which is a latch rather than a duty
cycle. **That measurement is from another hull on another bot**, though, and a
rule on this ship's survival path that is only safe while it holds is not one to
ship -- so the propulsion module reads through this declaration exactly as the
harvesters do, and #456's open question about the harvesters costs nothing here
in either direction.

-}
type ModuleRunningState
    = ModuleIsRunning
    | ModuleIsNotRunning


moduleRunningState : EveOnline.ParseUserInterface.ShipUIModuleButton -> ModuleRunningState
moduleRunningState moduleButton =
    case moduleButton.stateFromDictEntries.ramp_active of
        Just _ ->
            ModuleIsRunning

        Nothing ->
            ModuleIsNotRunning


{-| Whether the module's own ramp animation is visibly turning right now, read
straight off the two ramp sprites' rotation rather than off `ramp_active`.

**This is the evidence `KickTheHarvester` was missing.** Live on 2026-09-07:
`harvesterRecheckIntervalReadings` fires on a fixed 20-reading clock with no
corroborating evidence either way, so it presses a harvester's hotkey whenever
that clock runs out -- including on a harvester the client's own combat log
shows mining every few readings the whole time. The hotkey is a toggle, so that
press is indistinguishable from `moduleRunningState`'s own `ModuleIsRunning`
case, and pressing it is exactly the flicker #12/#34/#35/#76/#286 are about.
`moduleRunningState` itself is not the problem -- its absence-only reading is
the strong evidence an _activation_ needs, per the doc comment above -- the
problem is that the recheck has no equivalent strong evidence for the opposite
question, "is it safe to press this because it is genuinely idle".

`rampRotationMilli` is that evidence where it is available: it comes off the
`leftRamp`/`rightRamp` sprites' live rotation angle rather than the
`ramp_active` dictionary entry, so it can say the module is mid-cycle on a
reading where `ramp_active` itself has not been re-read as anything new. A
harvester genuinely running for the whole of a 20-reading window is spinning
for nearly all of it, so requiring this to read idle _at the recheck reading_
before pressing removes most of the exposure without adding a second counter.

**`eve-online-saxrat` has a declaration that reads almost like this one, named
`moduleIsActiveOrReloading`, and it is deliberately not copied whole.** That
one is `moduleButton.isActive || rampRotationMilli /= 0`, and it is also called
from nowhere -- confirmed by search, not by the doc comment there. `.isActive`
**is** `ramp_active`, the very field the paragraphs above this one spend three
bullet points establishing this app must read only through `moduleRunningState`'s
absence-only test: `Just True` is indistinguishable from a module mid-cycle
between ramps, and a rule that credits it as "definitely active" is #12's
mistake with a second entry point into the same field. `rampRotationMilli` is
the one term of saxrat's declaration that names evidence this reading cannot
already give some other way, so it is the only one taken.

-}
harvesterLooksActiveByRamp : EveOnline.ParseUserInterface.ShipUIModuleButton -> Bool
harvesterLooksActiveByRamp moduleButton =
    (moduleButton.rampRotationMilli |> Maybe.withDefault 0) /= 0


{-| The propulsion module, which the client-setup contract puts first in the
middle row.

`Nothing` is a middle row this reading could not read at all, and it declines
rather than defaulting: pressing `Alt+F1` at a ship whose modules are arranged
some other way is pressing whatever is bound there.

-}
propulsionModuleFromShipUI : EveOnline.ParseUserInterface.ShipUI -> Maybe EveOnline.ParseUserInterface.ShipUIModuleButton
propulsionModuleFromShipUI shipUI =
    shipUI.moduleButtonsRows.middle |> moduleButtonsLeftToRight |> List.head


harvesterModulesFromShipUI : EveOnline.ParseUserInterface.ShipUI -> List EveOnline.ParseUserInterface.ShipUIModuleButton
harvesterModulesFromShipUI shipUI =
    shipUI.moduleButtonsRows.top |> moduleButtonsLeftToRight


{-| The keys one press holds down, in the order a chord wants them.

Down in order and up in reverse, so a modifier is released after the key it
modifies -- which is the shape `Alt+F1` already has everywhere in this repo, and
the shape `cg_input`'s modifier stamping expects since PR #241.

-}
hotkeyEffects : List EffectOnWindow.VirtualKeyCode -> List EffectOnWindow.EffectOnWindowStruct
hotkeyEffects chord =
    (chord |> List.map EffectOnWindow.KeyDown)
        ++ (chord |> List.reverse |> List.map EffectOnWindow.KeyUp)


{-| Whether a dispatched step pressed **exactly** this chord and nothing else.

Equality on the step's own key-down sequence rather than "contains every key of
the chord", because `F1` is a subsequence of `Alt+F1` -- and a settling window
that answered `True` for the harvester's press when the propulsion module's went
out would suppress a press this bot meant to make, on a toggle, silently.

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


{-| Press a module's hotkey, unless this bot pressed the same one a moment ago.

**Every module hotkey on this ship is a toggle**, so a second press before the
client has shown the result of the first switches the module back off -- which
is `clickModuleButtonButWaitIfClickedInPreviousStep`'s reason, applied to the
key that stands in for the click. `moduleButtonClickSettlingSteps` is the same
window, taken from the framework rather than restated, so the two mechanisms
cannot come to disagree about how long a press takes to appear.

One declaration with two readers -- the propulsion module and each harvester --
because "how long a module press takes to show up" is one fact about the client
and two copies of it would be two places to retune.

-}
pressModuleHotkey : BotDecisionContext -> String -> List EffectOnWindow.VirtualKeyCode -> DecisionPathNode
pressModuleHotkey context describe chord =
    if chordPressedInSettlingWindow context chord then
        describeBranch
            "Already pressed that module hotkey in a previous step -- a module button is a toggle, so wait for the client to show the result rather than pressing it off again."
            waitForProgressInGame

    else
        describeBranch describe (decideActionForCurrentStep (hotkeyEffects chord))


{-| Whether this bot pressed this exact chord inside the settling window.

**One declaration with two readers**, and they want the same fact and opposite
answers to it: `pressModuleHotkey` waits the window out where the harvest loop
has nothing else to do with the reading, and `propulsionStep` falls through it
so that a retreat is never held up by a module press. Two copies of "how long a
press takes to show up" would be two places to retune, which is #102.

The window itself is `moduleButtonClickSettlingSteps`, taken from the framework
rather than restated, for the same reason.

-}
chordPressedInSettlingWindow : BotDecisionContext -> List EffectOnWindow.VirtualKeyCode -> Bool
chordPressedInSettlingWindow context chord =
    context.previousStepsEffects
        |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
        |> List.any (stepPressedExactly chord)



-- Keeping the propulsion module running


{-| How many presses the client may leave unanswered before the bot stops asking.

**A branch on the hot path that can act forever without progressing is the
failure this repository keeps a section on**, and this is one: a middle row
whose first module is not a propulsion module at all, or one that is offline or
out of capacitor, reads as not running on every reading of the session, and an
unbounded rule would press `Alt+F1` at it in front of every retreat, every
deposit and every harvest until somebody noticed. That is #257's shape, and it
would be the worst possible place to put it -- in front of the branch that gets
the ship off a hostile grid.

Six, and it is a relation rather than a measurement because no run of this app
exists to measure. The client answers a press by creating the
`ShipModuleButtonRamps` widget, which the next reading carries, and each press
is followed by a whole `moduleButtonClickSettlingSteps` window before another
goes out -- so six presses is six windows, an order of magnitude more than one
press that is going to land needs.

**The counter resets the moment the module reads running**, so this is not a
session latch: an ordinary run spends nothing, and a run that docks (which
switches modules off) gets its whole budget back on the reading after it
undocks. What latches, and correctly, is the fit this cannot work on -- a ship
with no propulsion module first in the middle row never resets, so it spends six
presses once and then gets on with the session.

What expiry costs is a ship that flies at its base speed, which is exactly the
state this app was in before #465 and which the status line names. What no bound
costs is a ship that never leaves.

-}
propulsionPressesBeforeGivingUp : Int
propulsionPressesBeforeGivingUp =
    6


{-| Everything the propulsion module rule decides on, as plain readable facts.

A record rather than a `BotDecisionContext`, for #106's reason and with more
riding on it than usual: this rule sits above the retreat, so a case that could
only reach it through a whole decision context would be a case that never
executed the one rule that can hold the ship on a hostile grid.

-}
type alias PropulsionSituation =
    { moduleReading : Maybe ModuleRunningState
    , pressedRecently : Bool
    , pressesUnanswered : Int
    }


{-| What this bot does about the propulsion module on one reading.

Five answers, and **only one of them presses anything** -- which is the property
#465 is about, since the module's hotkey is a toggle and every press that is not
aimed at a module reading _not running_ switches a running one off.

  - `TheModuleIsRunning` -- nothing to do, which is the ordinary reading.
  - `CannotTellWhetherItIsRunning` -- no ship UI in this reading, or a middle row
    it cannot read. **A toggle is never pressed on a guess**, so this declines,
    which also covers every docked reading by construction.
  - `WaitForTheLastPressToShow` -- a press went out inside the settling window
    and the client has not shown its result yet. Pressing again here is the
    module switched back off, which is `clickModuleButtonButWaitIfClickedInPreviousStep`'s
    own reason.
  - `GivenUpOnSwitchingItOn` -- see `propulsionPressesBeforeGivingUp`.
  - `SwitchItOn` -- the one press.

**Nothing here waits**: four of the five answers hand the reading straight back
to whatever would have had it, so a retreat is never delayed by this rule beyond
the single reading a press costs. That is the difference between this and
`pressModuleHotkey`, which waits its settling window out because the harvest loop
has nothing else to do with the reading.

-}
type PropulsionStep
    = TheModuleIsRunning
    | SwitchItOn
    | WaitForTheLastPressToShow
    | CannotTellWhetherItIsRunning
    | GivenUpOnSwitchingItOn


propulsionStep : PropulsionSituation -> PropulsionStep
propulsionStep situation =
    case situation.moduleReading of
        Nothing ->
            CannotTellWhetherItIsRunning

        Just ModuleIsRunning ->
            TheModuleIsRunning

        Just ModuleIsNotRunning ->
            if situation.pressedRecently then
                WaitForTheLastPressToShow

            else if propulsionPressesBeforeGivingUp <= situation.pressesUnanswered then
                GivenUpOnSwitchingItOn

            else
                SwitchItOn


propulsionSituationFromContext : BotDecisionContext -> PropulsionSituation
propulsionSituationFromContext context =
    { moduleReading =
        context.readingFromGameClient.shipUI
            |> Maybe.andThen propulsionModuleFromShipUI
            |> Maybe.map moduleRunningState
    , pressedRecently = chordPressedInSettlingWindow context propulsionModuleHotkey
    , pressesUnanswered = context.memory.propulsionPressesUnanswered
    }


{-| How many presses the client has left unanswered, after this reading.

Reset outright the moment the module reads running, which is what makes the
bound a bound on _one_ attempt to switch it on rather than a session budget --
see `propulsionPressesBeforeGivingUp`.

**A reading that could not read the module holds the count rather than clearing
it**, which is the rule #145 records paying for: a reset on a reading that did
not ask is what pins a counter at one forever, and here the readings that cannot
answer are the docked ones, which is precisely the stretch a deposit spends
before the module needs switching on again.

The press is read out of the **effects the bot dispatched** rather than out of
anything the client said, because what was asked for is knowable where what the
client did with it is not. Only the previous step is looked at, so one press
counts once however long the settling window is.

-}
propulsionPressesAfterReading : { pressDispatched : Bool, readsRunning : Bool } -> Int -> Int
propulsionPressesAfterReading answer before =
    if answer.readsRunning then
        0

    else if answer.pressDispatched then
        before + 1

    else
        before


{-| Switch the propulsion module on, wherever it is not running.

**This is #465.** The operator's reason for it is that a gas huffer's survival
plan is speed rather than tank, so the module is what keeps the ship alive if
rats spawn -- which makes the reading it matters most on the reading the ship is
about to leave a grid on, not the one it is harvesting on.

So it is placed **above** the leaving, the deposit and the harvest, and the cost
of that placement is stated rather than hidden: on the first reading of a retreat
where the module is off, one reading goes to the press instead of to the warp
cascade. That is one reading against a whole retreat flown at base speed, on a
hull whose whole answer to being shot at is not being there.

**There is exactly one controller for this button**, which is why the harvest
loop no longer has a propulsion stage of its own. Two branches pressing one
toggle is the flicker `manageMiddleRowModules` was split up to end, and here it
would be worse than a flicker: the harvest loop's copy would press _inside_ this
one's settling window, which is a press aimed at a module the client is in the
middle of switching on, on a toggle.

`Nothing` on four of the five answers, so a reading with nothing to do here falls
straight through to the work -- the shape every entry in
`generalSetupInUserInterface` has, and for the same reason.

-}
keepThePropulsionModuleRunning : BotDecisionContext -> Maybe DecisionPathNode
keepThePropulsionModuleRunning context =
    case propulsionStep (propulsionSituationFromContext context) of
        SwitchItOn ->
            Just
                (describeBranch
                    "The propulsion module does not read as running -- switch it on (Alt+F1) before anything else this reading. Speed is this hull's whole survival plan, so it goes on before the ship is asked to go anywhere."
                    (decideActionForCurrentStep (hotkeyEffects propulsionModuleHotkey))
                )

        _ ->
            Nothing


{-| What an operator reads about the propulsion module, on every reading.

#465 asks for this in those words: _say whether the module reads active on every
in-space reading_, because a gas huffer whose propulsion module is off is in a
worse position than one that never armed it, and an operator should be able to
see that at a glance rather than infer it from the ship's speed.

Printed on **every** reading rather than only while harvesting, which is the
change #465 makes to where this is said: the reading it matters most on is the
one the ship is leaving on, and until now the only place it appeared was the
harvest clause, which a reading with no cloud on the grid does not carry.

The last sentence is the standing fact rather than this reading's, and it is
here because it is the one an operator cannot check for themselves from a log:
nothing in this file ever switches the module off.

-}
describePropulsionModule : PropulsionSituation -> String
describePropulsionModule situation =
    let
        spent =
            String.fromInt situation.pressesUnanswered
                ++ "/"
                ++ String.fromInt propulsionPressesBeforeGivingUp
                ++ " presses unanswered"
    in
    "Propulsion module: "
        ++ (case propulsionStep situation of
                TheModuleIsRunning ->
                    "running"

                SwitchItOn ->
                    "NOT RUNNING -- pressing Alt+F1 at it this reading (" ++ spent ++ ")"

                WaitForTheLastPressToShow ->
                    "not running yet, and a press went out in the last few steps -- the button is a toggle, so this reading waits for the client to show the result rather than pressing it off again ("
                        ++ spent
                        ++ ")"

                CannotTellWhetherItIsRunning ->
                    "CANNOT TELL -- this reading carries no module in the middle row, which is every docked reading and, in space, a ship whose modules are not arranged the way the client-setup list asks. Not pressed at: a toggle pressed on a guess is a module switched off"

                GivenUpOnSwitchingItOn ->
                    "GIVEN UP ON: "
                        ++ String.fromInt situation.pressesUnanswered
                        ++ " presses went out and the client answered none of them, so this ship is flying at its base speed and nothing here will ask again until the module reads running. Check that the first module in the middle row is the propulsion module, and that it is online"
           )
        ++ ". Nothing in this bot ever switches it off (#465)."



-- The harvest loop


{-| How many readings the bot asks the Selected Item panel to show a cloud
before it stops asking.

The selection lands on the next reading when it lands at all, so ten is an order
of magnitude more than it should take. **It is not calibrated against a corpus**
-- no recorded run of this app exists at all -- and what the direction rests on
is what expiry costs: the reading is handed to the lock and the harvesters, so
the bot harvests without an orbit rather than clicking one overview row forever,
which is #257's shape on the hottest path this bot has.

-}
panelSelectGiveUpReadings : Int
panelSelectGiveUpReadings =
    10


{-| How many readings a lock may go unanswered before the bot stops asking for
it.

Larger than the selection's bound because a lock is the client's own asynchronous
action with a visible in-progress state, where a selection either lands on the
next reading or did not happen. Same argument for having one at all: without it
a cloud the client will not lock is a Ctrl+click dispatched on every reading for
the rest of the session, and the status line would say `harvesting` throughout.

-}
lockGiveUpReadings : Int
lockGiveUpReadings =
    20


{-| The counters bounding the things the harvest loop asks for.

Advanced in `updateMemoryForNewReadingFromGame`, which is the only place that
can write memory and the one place that never sees a decision -- so what they
count is the **client's** answer rather than the branch's activity, and they
therefore keep counting whatever else holds the tree. That is the half #102's
placement rule is about, and the comparison against them is asked inside
`harvestStep`, which is reached on every reading the ship is on a grid with a
cloud on it.

The first two reset outright on a reading where the client has answered, and
on any reading with no cloud chosen at all -- so a session that harvests forty
clouds starts from zero at each one. `harvestersKickedReadingsAgo` resets on
the same "no cloud chosen" edge and additionally the moment the lock is lost,
since it is a fact about _this_ lock rather than about the cloud-picking loop
-- see its own doc comment.

-}
type alias HarvestCounters =
    { panelSelectUnansweredReadings : Int
    , lockUnansweredReadings : Int
    , harvestersKickedReadingsAgo : List ( Int, Int )
    }


initHarvestCounters : HarvestCounters
initHarvestCounters =
    { panelSelectUnansweredReadings = 0, lockUnansweredReadings = 0, harvestersKickedReadingsAgo = [] }


{-| How long a forced press stands before this rule is willing to distrust
"reads as running" again for the same harvester, under the same lock.

Run 2, live on 2026-09-07: a one-shot version of this rule (kick once per lock,
never again) forced both harvesters once when the lock landed and then reported
`confirmed since this lock landed` for the rest of the lock's life -- while the
operator, watching the client, could see they were not actually cycling. The
one-shot design assumed `ramp_active` going stale was a fact about the _previous_
target that a fresh lock settles once and for all; it does not settle whether the
module keeps running for the rest of that lock, and this bot has no verified
field that says so on its own.

Bounded rather than continuous for the same reason the one-shot version was
one-shot at all: every press is a toggle, and a harvester that genuinely is
running is switched off by pressing it again. A short interval trades a
possible one-cycle interruption of a module that was fine for the alternative
this run just measured -- a harvester stuck off for the rest of a lock with
nothing left in this rule that will ever ask again.

20, matching `lockGiveUpReadings`' scale rather than a shorter number invented
for this: both are "how long before this rule stops taking a stale-looking
reading on faith", and nothing here has measured a harvester's own timing
closely enough to argue for a different figure.

**The clock alone turned out not to be enough.** Live on 2026-09-07, this
interval fired on its own schedule against a harvester the client's own combat
log showed mining every few readings throughout -- the toggle-flicker #12 and
its successors are about, landed on a module this rule itself calls running.
`harvesterLooksActiveByRamp` is the fix: the clock still bounds how long a
stale-looking reading is taken on faith, but it is only spent pressing a
harvester that also fails a live check of its ramp animation at the moment the
clock runs out, and it is reset early -- see `harvestCountersAfterReading` --
on any reading the ramp is seen turning, which is most readings of a harvester
that is genuinely fine.

-}
harvesterRecheckIntervalReadings : Int
harvesterRecheckIntervalReadings =
    20


{-| What one reading says about the two asks, in the terms the counters need.

A record rather than a reading, so a case can fold a whole session through
`harvestCountersAfterReading` and read the counters back.

`harvesterIndexJustKicked` is read out of the **effects the bot dispatched**
rather than out of which `HarvestStep` was taken, for `propulsionPressesAfterReading`'s
own reason: what was asked for is knowable from the previous step's effects
where what the decision function returned is not, once the decision for the
next reading is what is being computed. It answers the same way whether the
press came from `RunTheHarvester` (the module read as off) or `KickTheHarvester`
(it read as on but due for a recheck) -- either one restarts this index's own
clock towards its next recheck.

`harvesterIndicesLookingActiveByRamp` is the other way a clock restarts, and it
is read from the **current** reading rather than the previous step's effects,
because it is evidence about the module rather than about what this bot asked
for -- see `harvesterLooksActiveByRamp`.

-}
type alias HarvestAnswerFromClient =
    { cloudIsChosen : Bool
    , panelShowsTheCloud : Bool
    , cloudReadsLocked : Bool
    , harvesterIndexJustKicked : Maybe Int
    , harvesterIndicesLookingActiveByRamp : List Int
    }


harvestCountersAfterReading : HarvestAnswerFromClient -> HarvestCounters -> HarvestCounters
harvestCountersAfterReading answer counters =
    if not answer.cloudIsChosen then
        initHarvestCounters

    else
        { panelSelectUnansweredReadings =
            if answer.panelShowsTheCloud then
                0

            else
                counters.panelSelectUnansweredReadings + 1
        , lockUnansweredReadings =
            if answer.cloudReadsLocked then
                0

            else
                counters.lockUnansweredReadings + 1
        , harvestersKickedReadingsAgo =
            if not answer.cloudReadsLocked then
                []

            else
                let
                    aged =
                        counters.harvestersKickedReadingsAgo
                            |> List.map (Tuple.mapSecond ((+) 1))

                    confirmedFreshThisReading =
                        (answer.harvesterIndexJustKicked |> Maybe.map List.singleton |> Maybe.withDefault [])
                            ++ answer.harvesterIndicesLookingActiveByRamp
                            |> List.foldl
                                (\index unique ->
                                    if List.member index unique then
                                        unique

                                    else
                                        index :: unique
                                )
                                []
                in
                (confirmedFreshThisReading |> List.map (\index -> ( index, 0 )))
                    ++ (aged |> List.filter (\( index, _ ) -> not (List.member index confirmedFreshThisReading)))
        }


{-| Everything about a grid the harvest loop decides on, as plain readable facts.

A record rather than a `BotDecisionContext`, for #106's reason: this is the one
rule in this app that orders four separate commands, and a rule reachable only
through a decision context is one no case can execute -- so it would be checked
by being read, which is how a rule that does the right things in the wrong order
passes for one that works.

-}
type alias HarvestSituation =
    { shipIsOrbiting : Bool
    , panelShowsTheCloud : Bool
    , orbitButtonIsOffered : Bool
    , cloudReadsLocked : Bool
    , cloudReadsLocking : Bool
    , harvestersNotRunning : List Int
    , harvestersNeedingAKick : List Int
    , counters : HarvestCounters
    }


{-| What the bot commands next on a grid it is harvesting.

**One rule with the whole ordering in it**, rather than three branches each
deciding whether it is its turn. The order is the issue's own -- orbit the
cloud, lock it, run both harvesters -- and what makes it worth writing as one
rule is that every stage can _fail to be reachable_, and each of those has to
fall through to the next rather than holding the loop:

  - a panel that never comes to show the cloud expires and the bot harvests
    without an orbit,
  - a panel showing the cloud and offering no Orbit button is the ordinary
    contextual button set rather than a failure, and waits by falling through,
  - a lock the client will not grant expires, and then there is genuinely
    nothing left to command, because a harvester runs on the active target.

`NothingLeftToCommand` is therefore two different situations -- everything
running, and nothing left that can be tried -- which is why the status line
renders the _situation_ beside the step alone.

**The propulsion module was the first stage of this rule until #465 and is not
here any more.** It moved to `keepThePropulsionModuleRunning`, above the leaving
and the deposit as well as this, because the reading it matters most on is the
one the ship is leaving on rather than one it is harvesting on -- and once it is
asked there, a second copy here would be two branches pressing one toggle, the
second of them inside the first's settling window.

**`KickTheHarvester` is #456's other open question, closed the safe way rather
than guessed.** `moduleRunningState` treats the widget's `ramp_active` entry
being present **at all** as running, and only its absence as not -- deliberate,
per that declaration's own doc comment, because an activation must be sure the
module is off before pressing a toggle. Run 1, live on 2026-09-07: this bot
pressed a harvester's hotkey twice, in its first few readings, and then not
once more across the rest of a thousand-tick session, because `ramp_active`
never went absent again -- whether that is the client honestly reporting the
module still cycling, or the reading going stale the way a middle-slot module
did on another hull in #35, is exactly what #456 could not settle without a
live run, and now one has answered it by never restarting the harvester across
several evasion warps and re-locks, in a session the operator had to keep
retriggering by hand.

**A `ramp_active` reading from _before_ the current lock landed cannot be
evidence about the target under it now**, whichever of the two it is: a
harvester needs the active target to do anything, so nothing about it could
have been genuinely cycling on a cloud this ship had not yet locked. That is
the first moment this rule is allowed to distrust "reads as running", and
`harvestersKickedReadingsAgo` is what times it out: an index's clock starts the
reading its hotkey is actually dispatched, by `RunTheHarvester` or by this, and
runs until `harvesterRecheckIntervalReadings` -- so a harvester that genuinely
is running fine under this lock is left alone for that whole window rather than
toggled every reading, and one that has quietly stopped without `ramp_active`
ever clearing gets asked again rather than left stuck for the rest of the lock,
which is what a true one-shot version of this rule did in run 2. Both directions
are costs rather than certainties: pressing a module that was fine costs one of
its cycles, and waiting out the interval on one that had already stopped costs
up to that many readings of it doing nothing -- there is no reading available
here that tells the difference in advance.

-}
type HarvestStep
    = SelectTheCloud
    | PressTheOrbitButton
    | LockTheCloud
    | WaitForTheLockToLand
    | RunTheHarvester Int
    | KickTheHarvester Int
    | NothingLeftToCommand


harvestStep : HarvestSituation -> HarvestStep
harvestStep situation =
    if not situation.shipIsOrbiting && not situation.panelShowsTheCloud && situation.counters.panelSelectUnansweredReadings < panelSelectGiveUpReadings then
        SelectTheCloud

    else if not situation.shipIsOrbiting && situation.panelShowsTheCloud && situation.orbitButtonIsOffered then
        PressTheOrbitButton

    else if situation.cloudReadsLocked then
        case situation.harvestersNotRunning of
            index :: _ ->
                RunTheHarvester index

            [] ->
                case situation.harvestersNeedingAKick of
                    index :: _ ->
                        KickTheHarvester index

                    [] ->
                        NothingLeftToCommand

    else if situation.cloudReadsLocking then
        WaitForTheLockToLand

    else if situation.counters.lockUnansweredReadings < lockGiveUpReadings then
        LockTheCloud

    else
        NothingLeftToCommand


{-| Whether the Selected Item panel is showing this overview row.

Compared on **words** rather than as a substring, because a substring has cost
this codebase real bugs -- a rogue drone called a `Wrecker` contains `wreck` --
and the panel's own label carries decoration around the name.

The exposure it does not remove is stated rather than implied: two clouds of one
designation share a name, so a selection that landed on the neighbour reads as
correct. Every site measured for #456 carried clouds with distinct designations,
and the ordering this bot picks by is derived from those designations, so two
identically named rows would already be a site this rule has nothing to say
about.

-}
selectedItemIsOverviewEntry : ReadingFromGameClient -> EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
selectedItemIsOverviewEntry readingFromGameClient entry =
    case ( readingFromGameClient.selectedItemWindow, entry.objectName ) of
        ( Just window, Just name ) ->
            EveOnline.ParseUserInterface.getAllContainedDisplayTexts window.uiNode.uiNode
                |> List.any (containsWords name)

        _ ->
            False


{-| Whether `pattern` occurs in `text` as whole words rather than as a substring.

Whitespace is normalised and both sides padded, so a match can neither begin nor
end mid-word and a multi-word pattern still matches as a sequence.

-}
containsWords : String -> String -> Bool
containsWords pattern text =
    let
        padded value =
            " " ++ (value |> String.toLower |> String.words |> String.join " ") ++ " "
    in
    String.contains (padded pattern) (padded text)


{-| The Selected Item panel's Orbit button, by **both** the identifiers the
client carries for it.

The client writes an id on the node (`_name` / `_elementId`, which read alike on
every panel button this repo has ever pressed) and a `cmdName` beside it --
`selectedItemOrbit` and `CmdOrbitItem` name the same button -- so matching either
survives a rename of one. That is cheap insurance on a widget name, which is the
class of thing that has cost this repo whole sessions.

Found by name in the reading it is pressed in and **never by position**:
`selectedItemOrbit` was read live at x=1515 in one reading and x=1551 in another
moments later, because two buttons left the row and everything shifted.

-}
selectedItemOrbitButton : { elementId : String, cmdName : String }
selectedItemOrbitButton =
    { elementId = "selectedItemOrbit", cmdName = "CmdOrbitItem" }


selectedItemPanelButton :
    ReadingFromGameClient
    -> { elementId : String, cmdName : String }
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
                [ property "_name" node, property "_elementId" node ]
                    |> List.member (Just button.elementId)
                    |> (||) (property "cmdName" node == Just button.cmdName)
            )
        |> List.head


{-| The lock chord for one row: Ctrl held over a plain left click.

The row is filtered on `_display` before it ever reaches here -- see
`overviewEntryIsDisplayed` -- because this is a click at a screen position, and a
hidden row's position belongs to something else.

-}
lockChordForOverviewEntry : EveOnline.ParseUserInterface.OverviewWindowEntry -> List EffectOnWindow.EffectOnWindowStruct
lockChordForOverviewEntry overviewEntry =
    [ [ EffectOnWindow.KeyDown EffectOnWindow.vkey_CONTROL ]
    , overviewEntry.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault []
    , [ EffectOnWindow.KeyUp EffectOnWindow.vkey_CONTROL ]
    ]
        |> List.concat


harvestSituationFromContext :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> HarvestSituation
harvestSituationFromContext context shipUI cloud =
    { shipIsOrbiting =
        (shipUI.indication |> Maybe.andThen .maneuverType)
            == Just EveOnline.ParseUserInterface.ManeuverOrbit
    , panelShowsTheCloud = selectedItemIsOverviewEntry context.readingFromGameClient cloud
    , orbitButtonIsOffered =
        selectedItemPanelButton context.readingFromGameClient selectedItemOrbitButton /= Nothing
    , cloudReadsLocked = cloud.commonIndications.targetedByMe
    , cloudReadsLocking = cloud.commonIndications.targeting
    , harvestersNotRunning =
        harvesterModulesFromShipUI shipUI
            |> List.indexedMap Tuple.pair
            |> List.filter (Tuple.second >> moduleRunningState >> (==) ModuleIsNotRunning)
            |> List.map Tuple.first
    , harvestersNeedingAKick =
        harvesterModulesFromShipUI shipUI
            |> List.indexedMap Tuple.pair
            |> List.filter (Tuple.second >> moduleRunningState >> (==) ModuleIsRunning)
            -- Never kick a module whose ramp is visibly turning right now --
            -- see `harvesterLooksActiveByRamp`. Belt and braces alongside the
            -- clock reset in `harvestCountersAfterReading`: that reset keeps
            -- the clock from reaching the interval in the first place on an
            -- ordinary reading, and this keeps a kick from firing on the one
            -- reading the clock and a momentary ramp reading disagree.
            |> List.filter (Tuple.second >> harvesterLooksActiveByRamp >> not)
            |> List.map Tuple.first
            |> List.filter
                (\index ->
                    context.memory.harvestCounters.harvestersKickedReadingsAgo
                        |> List.filter (Tuple.first >> (==) index)
                        |> List.all (Tuple.second >> (<=) harvesterRecheckIntervalReadings)
                )
    , counters = context.memory.harvestCounters
    }


{-| Command whatever `harvestStep` says is next.

Nothing is decided here: this is the mapping from an answer onto the effects
that carry it out, kept apart from the rule so the ordering can be executed
without a client and the effects can be read without one.

-}
actOnTheHarvestStep :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> EveOnline.ParseUserInterface.OverviewWindowEntry
    -> HarvestSituation
    -> DecisionPathNode
actOnTheHarvestStep context shipUI cloud situation =
    let
        cloudName =
            cloud.objectName |> Maybe.withDefault "the cloud"
    in
    case harvestStep situation of
        SelectTheCloud ->
            describeBranch
                ("Select '" ++ cloudName ++ "', so the Selected Item panel's own Orbit button acts on it.")
                (decideActionForCurrentStep
                    (cloud.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault [])
                )

        PressTheOrbitButton ->
            describeBranch
                ("Orbit '" ++ cloudName ++ "' at " ++ context.eventContext.botSettings.orbitRange ++ ", commanded rather than inherited from the client's own default.")
                (useContextMenuCascade ( cloudName, cloud.uiNode )
                    (orbitCascadeAt context.eventContext.botSettings.orbitRange)
                    context
                )

        LockTheCloud ->
            describeBranch
                ("Lock '" ++ cloudName ++ "' (Ctrl+click its overview row) -- a harvester runs on the active target.")
                (decideActionForCurrentStep (lockChordForOverviewEntry cloud))

        WaitForTheLockToLand ->
            describeBranch
                ("The client is still locking '" ++ cloudName ++ "'.")
                waitForProgressInGame

        RunTheHarvester index ->
            case
                ( topRowModuleHotkeyFromIndex index
                , harvesterModulesFromShipUI shipUI |> List.drop index |> List.head
                )
            of
                ( Just keyCode, _ ) ->
                    pressModuleHotkey context
                        ("Run gas harvester "
                            ++ String.fromInt (index + 1)
                            ++ " on '"
                            ++ cloudName
                            ++ "' -- it does not read as cycling."
                        )
                        [ keyCode ]

                ( Nothing, Just moduleButton ) ->
                    describeBranch
                        ("Run gas harvester " ++ String.fromInt (index + 1) ++ " -- past the four the hotkeys reach, so click its button.")
                        (EveOnline.BotFrameworkSeparatingMemory.clickModuleButtonButWaitIfClickedInPreviousStep
                            context
                            moduleButton
                        )

                ( Nothing, Nothing ) ->
                    describeBranch
                        "The module row changed between reading it and pressing it -- ask again next reading."
                        waitForProgressInGame

        KickTheHarvester index ->
            case
                ( topRowModuleHotkeyFromIndex index
                , harvesterModulesFromShipUI shipUI |> List.drop index |> List.head
                )
            of
                ( Just keyCode, _ ) ->
                    pressModuleHotkey context
                        ("Run gas harvester "
                            ++ String.fromInt (index + 1)
                            ++ " on '"
                            ++ cloudName
                            ++ "' even though it reads as cycling -- due for a recheck ("
                            ++ String.fromInt harvesterRecheckIntervalReadings
                            ++ " readings since the last one), so the reading may be stale rather than the module still doing anything (#456)."
                        )
                        [ keyCode ]

                ( Nothing, Just moduleButton ) ->
                    describeBranch
                        ("Run gas harvester "
                            ++ String.fromInt (index + 1)
                            ++ " -- past the four the hotkeys reach, so click its button. It reads as cycling but is due for a recheck (#456)."
                        )
                        (EveOnline.BotFrameworkSeparatingMemory.clickModuleButtonButWaitIfClickedInPreviousStep
                            context
                            moduleButton
                        )

                ( Nothing, Nothing ) ->
                    describeBranch
                        "The module row changed between reading it and pressing it -- ask again next reading."
                        waitForProgressInGame

        NothingLeftToCommand ->
            describeBranch
                (describeHarvestSituation situation)
                (identifyTheModulesFitted context
                    |> Maybe.withDefault waitForProgressInGame
                )


{-| What the harvest loop is doing, and which of its stages it has given up on.

Printed on every reading with a cloud rather than only where something is wrong,
because the two states `NothingLeftToCommand` covers -- everything running, and
nothing left that can be tried -- are the same silence from outside, and only one
of them wants an operator.

-}
describeHarvestSituation : HarvestSituation -> String
describeHarvestSituation situation =
    let
        orbit =
            if situation.shipIsOrbiting then
                "orbiting"

            else if situation.counters.panelSelectUnansweredReadings >= panelSelectGiveUpReadings then
                "NOT ORBITING and GIVEN UP ON SELECTING the cloud after "
                    ++ String.fromInt panelSelectGiveUpReadings
                    ++ " readings -- harvesting without an orbit"

            else
                "not orbiting yet ("
                    ++ String.fromInt situation.counters.panelSelectUnansweredReadings
                    ++ "/"
                    ++ String.fromInt panelSelectGiveUpReadings
                    ++ " readings the panel has not shown the cloud)"

        lock =
            if situation.cloudReadsLocked then
                "locked"

            else if situation.cloudReadsLocking then
                "locking"

            else if situation.counters.lockUnansweredReadings >= lockGiveUpReadings then
                "NOT LOCKED and GIVEN UP ON after "
                    ++ String.fromInt lockGiveUpReadings
                    ++ " readings -- a harvester runs on the active target, so nothing is being harvested"

            else
                "not locked yet ("
                    ++ String.fromInt situation.counters.lockUnansweredReadings
                    ++ "/"
                    ++ String.fromInt lockGiveUpReadings
                    ++ ")"

        describeSlots slots =
            slots |> List.map (\index -> String.fromInt (index + 1)) |> String.join ", "

        harvesters =
            case ( situation.harvestersNotRunning, situation.harvestersNeedingAKick ) of
                ( [], [] ) ->
                    "both cycling, rechecked within the last "
                        ++ String.fromInt harvesterRecheckIntervalReadings
                        ++ " readings"

                ( [], needingKick ) ->
                    "both read as cycling, "
                        ++ String.fromInt (List.length needingKick)
                        ++ " due for a recheck (top-row slot(s) "
                        ++ describeSlots needingKick
                        ++ ")"

                ( notRunning, needingKick ) ->
                    String.fromInt (List.length notRunning)
                        ++ " not cycling (top-row slot(s) "
                        ++ describeSlots notRunning
                        ++ ")"
                        ++ (case needingKick of
                                [] ->
                                    ""

                                _ ->
                                    ", "
                                        ++ String.fromInt (List.length needingKick)
                                        ++ " more due for a recheck (slot(s) "
                                        ++ describeSlots needingKick
                                        ++ ")"
                           )
    in
    "Harvest: "
        ++ orbit
        ++ "; cloud "
        ++ lock
        ++ "; harvesters "
        ++ harvesters
        ++ "."



-- Getting to the site


{-| The top-level entry that opens the distance submenu, matched as a prefix.

Two levels, measured on this client for a bookmark. The top-level entry reads

    Warp to Within (0 m) | Align to | Show Info | Add Waypoint | Edit Location | Remove Location

and hovering the first opens a fixed submenu of `Within 0 m | Within 10 km |
Within 20 km | Within 30 km | Within 50 km | Within 70 km | Within 100 km | Set
Default`. A scanned anomaly's own menu takes the same two steps, which is what
lets one pair of literals drive both.

**Matched on the prefix and never on the whole string**, which is #463's own
emphasis and the one detail here that a plausible implementation gets wrong. The
parenthesised distance is the **client's current default**, so it moves: an
operator who takes `Within 100 km` once from any menu leaves this entry reading
`Warp to Within (100 km)` afterwards, and a rule comparing the whole string would
stop matching on a client that had been used by hand. The prefix is the part the
client writes for every bookmark and every scan result alike.

**A bookmark row's menu also varies by kind**: one measured row offered
`Approach Location` where another offered `Align to`. So the cascade matches the
entries it wants and ignores everything else rather than asserting a shape, which
is what `chooseEntry` does by construction -- but it is worth saying, because the
tempting alternative is to check the menu looks the way it was measured.

-}
warpToWithinMenuEntry : String
warpToWithinMenuEntry =
    "Warp to Within"


{-| A scan result's menu carries **two** entries this prefix matches, and they do
different things.

Read live on 2026-09-07, right-clicking a scanned site that is not on grid:

    Warp to Within 0 m | Warp to Within | Align to | Save Location... | Ignore Result | Ignore Other Results

`Warp to Within 0 m` warps when it is **clicked**. `Warp to Within` is the
submenu parent and opens a flyout when it is **hovered**. A bookmark's menu is
different again -- one entry reading `Warp to Within (0 m)`, with the client's
current default in parentheses, which is the submenu parent there.

So the prefix alone cannot say which kind of entry it has found, and the cascade
treats whatever it matches as a submenu parent: it hovers, and a hover on a
direct entry does nothing at all. That is #485's site warp -- 16 hovers and no
click.

`menuEntryIsTheWarpSubmenuParent` is what the cascade wants: the parent, and
never the direct entry beside it. The parenthesised distance still moves, so the
comparison is on the trimmed text with any parenthesised suffix removed rather
than on the whole string -- which is `warpToWithinMenuEntry`'s original argument,
kept, with the ambiguity it did not know about taken out.

-}
menuEntryOpensTheWarpDistanceSubmenu : String -> Bool
menuEntryOpensTheWarpDistanceSubmenu =
    menuEntryIsTheWarpSubmenuParent


menuEntryIsTheWarpSubmenuParent : String -> Bool
menuEntryIsTheWarpSubmenuParent entryText =
    menuEntryTextWithoutParenthesisedSuffix entryText == warpToWithinMenuEntry


{-| The entry text with a trailing parenthesised value removed, and trimmed.

`Orbit (5,000 m)` and `Warp to Within (0 m)` both carry the client's own current
default in that suffix, and it moves the moment an operator takes a different
distance by hand. Removing it is what lets a submenu parent be recognised by
equality rather than by a prefix that also matches its neighbours.

-}
menuEntryTextWithoutParenthesisedSuffix : String -> String
menuEntryTextWithoutParenthesisedSuffix entryText =
    case entryText |> String.trim |> String.split "(" of
        before :: _ ->
            String.trim before

        [] ->
            String.trim entryText


{-| The distance submenu's own entries, as the client writes them.

`Set Default` is deliberately **not** here. It is the eighth entry of that
submenu and it changes the client's own default rather than warping anywhere, so
a random pick over the whole menu -- which is what
`EveOnline.BotFramework.useRandomMenuEntry` would give -- would eventually press
it and quietly retune the client while warping nowhere.

Ordered as the client draws them, nearest first, so that a reader can see the
list is the measured one rather than a set. `warpAtZeroMenuEntry` and
`warpAt100KmMenuEntry` are members of it, which is asserted rather than left to
be noticed: three declarations that could come to disagree about what the client
writes are #102's defect, and here it would mean a retreat asking for a distance
the submenu does not offer.

-}
warpDistanceMenuEntries : List String
warpDistanceMenuEntries =
    [ "Within 0 m"
    , "Within 10 km"
    , "Within 20 km"
    , "Within 30 km"
    , "Within 50 km"
    , "Within 70 km"
    , "Within 100 km"
    ]


{-| Zero, which is what a site and a prepared bookmark both want.

A gas site is warped into to be harvested, and the clouds are what the ship has
to be next to; a bookmark carrying `retreat-bookmark-prefix` is an
instadock-style bookmark the operator has already placed for a 0 m arrival. Every
other distance in that submenu is a distance the ship then has to close by hand,
which this bot has no command for.

-}
warpAtZeroMenuEntry : String
warpAtZeroMenuEntry =
    "Within 0 m"


{-| A hundred kilometres, which is what an unknown bookmark wants.

#463's last-resort rung takes _any_ bookmark there is, and nothing here knows
what that bookmark is on top of -- a station, a gate, a wormhole, somebody's
tower. Landing 100 km off it is the one arrival that does not depend on knowing,
and it is a literal the client offers exactly, so the submenu match can be an
equality rather than a substring.

-}
warpAt100KmMenuEntry : String
warpAt100KmMenuEntry =
    "Within 100 km"


{-| Whether a scanned site is on this grid, read off the unit of its distance.

Ported from `eve-online-saxrat`'s `scanResultLooksLikeItIsOnGrid`, which reads
the **unit** rather than parsing a number -- and that is the whole of why it
works. `CLAUDE.md` records that an `AU` distance does not parse at all, and that
every consumer which tried turned the failure into a `999999` placeholder that
reads as _merely far away_ rather than as _not on this grid_.

Measured live on 2026-09-07: the site the ship was sitting on read `2,507 m`
while every other result read `3.62 AU`, `5.07 AU`, `3.88 AU`.

`Maybe Bool` and not `Bool`, deliberately. A `Distance` cell that is absent or
unreadable is **not** on grid, and it is also not licence to warp -- it is
unknown, and collapsing the two is how this bot would either strand itself on a
site it cannot see it is on, or warp at something it cannot see it is not. The
caller reads `Just True` and nothing else as "do not warp".

The test is a substring on `" m"`, which `" km"` also satisfies. That is
saxrat's own behaviour and it is correct here: both units mean on grid.

-}
scanResultIsOnGrid : EveOnline.ParseUserInterface.ProbeScanResult -> Maybe Bool
scanResultIsOnGrid =
    .cellsTexts
        >> Dict.get scanResultDistanceColumn
        >> Maybe.map (\text -> String.contains " m" text || String.contains " km" text)


scanResultDistanceColumn : String
scanResultDistanceColumn =
    "Distance"


{-| Orbit the cloud at a commanded range, rather than at whatever the client
last used.

`#456` said, and this file's own header said, that no command here can orbit at a
_distance_ -- that the Selected Item panel's Orbit button inherits the client's
default and that the range is therefore a client-setup requirement the operator
has to arrange by hand. **That was true of this repository and false of this
client**, and reading the menu is what settled it. Right-clicking a
`Harvestable Cloud` overview row on 2026-09-07:

    Approach | Orbit (5,000 m) | Look at | Track | Lock Target | Show Info | ...

and that entry opens a flyout:

    500 m | 1,000 m | 2,500 m | 5,000 m | 7,500 m | 10 km | 15 km | 20 km | 25 km | 30 km | Current 0 m | Set Default

So the range this bot needs is a literal the client offers, and commanding it
removes one of the three items the header lists as unenforceable -- the class of
requirement whose own framing is that getting it wrong "produces a bot that looks
like it is working". The harvesters' range refusal stays as the backstop rather
than as the only signal.

**The parent is matched with its parenthesised default removed**, for
`menuEntryTextWithoutParenthesisedSuffix`'s reason: `(5,000 m)` is the client's
current default and moves the moment anybody takes a different range by hand.

**The flyout opened to the _left_ of its parent** (x=1449 against the parent's
x=1557). Nothing here depends on that, since the cascade finds entries by text
rather than by position -- but a future change that starts reasoning about where
a submenu appears would be wrong about this one.

-}
orbitCascadeAt : String -> EveOnline.BotFramework.UseContextMenuCascadeNode
orbitCascadeAt rangeMenuEntry =
    useMenuEntryInLastContextMenuInCascade
        { describeChoice = "'" ++ orbitMenuEntry ++ "', ignoring the client's own default in parentheses"
        , chooseEntry =
            List.filter (.text >> menuEntryIsTheOrbitSubmenuParent) >> List.head
        }
        (useMenuEntryWithTextEqual rangeMenuEntry menuCascadeCompleted)


orbitMenuEntry : String
orbitMenuEntry =
    "Orbit"


menuEntryIsTheOrbitSubmenuParent : String -> Bool
menuEntryIsTheOrbitSubmenuParent entryText =
    menuEntryTextWithoutParenthesisedSuffix entryText == orbitMenuEntry


{-| The orbit flyout's own entries, as the client writes them, nearest first.

`Set Default` and `Current 0 m` are deliberately **not** here, for
`warpDistanceMenuEntries`' reason: the first retunes the client rather than
orbiting, and the second orbits at zero, which is not a range anybody asked for
and would put the ship inside the cloud rather than around it.

-}
orbitRangeMenuEntries : List String
orbitRangeMenuEntries =
    [ "500 m"
    , "1,000 m"
    , "2,500 m"
    , "5,000 m"
    , "7,500 m"
    , "10 km"
    , "15 km"
    , "20 km"
    , "25 km"
    , "30 km"
    ]


defaultOrbitRange : String
defaultOrbitRange =
    "500 m"


{-| Warp to a scanned site with the row's **own** warp button.

`ProbeScanResult.warpButton` is parsed on every reading and was read by nothing.
One click on it warped the ship, measured live on 2026-09-07:

    before:    0.0 m/s
    after 2s:  (Warping)  Establishing Warp Vector
    after 6s:  (Warping)  Warp Drive Active

It replaces a two-level context-menu cascade for this path, which matters beyond
being fewer steps. A cascade's hover and its click fall in **different readings**,
and #485 is the D-Scan refresh taking the reading in between -- every time,
because the refresh runs on its own interval and outranks the site branch. A
single click cannot be starved that way: there is no intermediate state for
another branch to interrupt.

**The bookmark half keeps its cascade**, because a `PlaceEntry` has no such
button and its menu genuinely is the two-level `Warp to Within (0 m)` ->
`Within 0 m` shape. So the retreat path remains exposed to the same starvation,
which is #485's other half and is not fixed here.

A row with no warp button falls back to the cascade rather than declining: the
button is absent on results that cannot be warped to at all, and the on-grid
guard above has already taken the case this bot meets in practice.

-}
warpToScanResult : BotDecisionContext -> EveOnline.ParseUserInterface.ProbeScanResult -> DecisionPathNode
warpToScanResult context anomaly =
    case anomaly.warpButton of
        Just button ->
            describeBranch
                "Click the scan result's own warp button -- one click, no menu to be interrupted between hovering and clicking."
                (decideActionForCurrentStep
                    (button |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault [])
                )

        Nothing ->
            describeBranch
                "This scan result carries no warp button, so take the context menu instead."
                (useContextMenuCascade ( "Scan result", anomaly.uiNode )
                    (warpCascadeWithin warpAtZeroMenuEntry)
                    context
                )


{-| The two-level cascade, at whichever distance the caller wants.

**One declaration with three readers** -- the hunt warp at zero, the retreat's
first two rungs at zero and its last at 100 km -- because the two levels are one
fact about this client and three copies of them would be three places to be wrong
about a menu that has already been measured once.

The distance is matched with `useMenuEntryWithTextEqual` rather than
`...TextContaining`, since every entry in that submenu is a literal the client
writes exactly and `Within 0 m` is a substring of nothing else there. The
top-level entry cannot be matched that way -- see `warpToWithinMenuEntry` -- so it
takes a custom choice, which is `useMenuEntryWithTextContaining`'s own shape with
the predicate swapped.

-}
warpCascadeWithin : String -> EveOnline.BotFramework.UseContextMenuCascadeNode
warpCascadeWithin distanceMenuEntry =
    useMenuEntryInLastContextMenuInCascade
        { describeChoice = "with text starting '" ++ warpToWithinMenuEntry ++ "'"
        , chooseEntry =
            List.filter (.text >> menuEntryOpensTheWarpDistanceSubmenu) >> List.head
        }
        (useMenuEntryWithTextEqual distanceMenuEntry menuCascadeCompleted)


{-| Warp to the site `siteSearch` chose.

**One cascade for both sources**, because the difference between them is which
node is right-clicked and nothing else. The bookmark half is
`eve-online-mining-bot`'s `useContextMenuOnLocationWithMatchingName` reduced to
the arm this bot needs: that function's whole locations-window branch is
`useContextMenuCascade ( placeEntry.mainText, placeEntry.uiNode )` over the
entry whose name matched, and `siteSearch` has already done the matching. Its
other two arms -- the overview row and the solar-system menu -- are ways of
finding a place this bot has not found in the Locations window, and it has no
use for either.

**Nothing deactivates the propulsion module on the way out, and that is #465.**
Every other bot here funnels its warps through
`ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`, and this one
must not: the propulsion module has to survive every warp this bot makes, so
there is no shared helper to reach and no branch that presses `Alt+F1` to switch
one off. `keepThePropulsionModuleRunning` is the only declaration in this file
that presses that key at all, it presses it only at a module reading _not
running_, and it is reached above this rather than through it.

That is asserted over every warp in this file rather than stated here, and over
the call graph rather than over this one declaration -- the shape #465 warns
about is a deactivation reached _through_ a warp helper as a courtesy, under a
name with no "deactivate" in it, which reading one branch would not catch.

-}
warpToTheHuntedSite : BotDecisionContext -> SiteToHunt -> DecisionPathNode
warpToTheHuntedSite context site =
    let
        warpMenu =
            warpCascadeWithin warpAtZeroMenuEntry
    in
    case site of
        ScannedAnomaly anomaly ->
            if scanResultIsOnGrid anomaly == Just True then
                -- #485: the ship is already here. Warping is not merely
                -- redundant, it cannot succeed and cannot self-correct: the
                -- client offers no warp entry at all on a result the ship is
                -- sitting on (measured live -- `Align to | Save Location... |
                -- Ignore Result | Ignore Other Results` and nothing else), so
                -- the cascade opens a menu, fails to find its entry, and starts
                -- over for as long as the ship stays. The clouds are on the
                -- overview the whole time.
                describeBranch
                    ("Already on grid with " ++ describeAnomalyIdentity anomaly ++ " -- nothing to warp to, so wait for a cloud rather than commanding a warp the client will not offer.")
                    waitForProgressInGame

            else
                describeBranch
                    ("Warp to the scanned anomaly " ++ describeAnomalyIdentity anomaly ++ ", at zero.")
                    (warpToScanResult context anomaly)

        BookmarkedSite bookmark ->
            describeBranch
                ("Warp to the bookmark '" ++ bookmark.mainText ++ "', at zero.")
                (useContextMenuCascade ( bookmark.mainText, bookmark.uiNode ) warpMenu context)



-- Whether anything on this grid means leave


{-| The overview's own icon colour for a rat, ported unchanged.

`eve-online-combat-anomaly-bot`, `eve-online-saxrat` and `eve-online-wingman`
all carry this identical predicate over `iconSpriteColorPercent`, and it is the
one thing in this file that identifies a hostile without an operator having
named anything: red against the white and yellow the client draws stargates and
the sun in. Live readings quoted in `CLAUDE.md` put every rat at
`{aPercent = 100, rPercent = 100, gPercent = 10, bPercent = 10}`.

**A row whose icon colour this reading cannot read answers `False`**, which is
the one place in this section where absent evidence does _not_ read as hostile,
and it is deliberate rather than an oversight. The colour is how a _rat_ is
recognised; a row it cannot be read for is not thereby a friendly row, it is a
row this trigger has nothing to say about -- and the other two triggers still
see it, because an unnamed row on the overview is exactly what
`pilotsOnTheOverviewNotInTheFleet` is unsure about and what D-Scan answers for
separately. Answering `True` instead would make every unreadable icon a rat, and
this bot would leave a site over a beacon.

-}
iconSpriteHasColorOfRat : EveOnline.ParseUserInterface.OverviewWindowEntry -> Bool
iconSpriteHasColorOfRat overviewEntry =
    case overviewEntry.iconSpriteColorPercent of
        Nothing ->
            False

        Just colorPercent ->
            (colorPercent.g * 3 < colorPercent.r)
                && (colorPercent.b * 3 < colorPercent.r)
                && (60 < colorPercent.r && 50 < colorPercent.a)


{-| The client's own words for a fleet-mate's icon in Local, ported unchanged.

Captured live on `FlagIconWithState` nodes inside `XmppChatUserEntry` rows and
recorded in `CLAUDE.md` under "Strings and identities read off a live client",
where it is also recorded that this hint is **not** on the overview row: five
rows were checked and none carried a `rightAlignedIconsHints` entry at all. That
is why fleet membership is asked of the chat row and matched onto the overview
row by name, rather than being read off the row this bot is judging.

-}
chatUserFleetmateMarker : String
chatUserFleetmateMarker =
    "Pilot is in your fleet"


{-| Whether Local says this pilot is one of ours.

`Nothing` is a chat row whose standing icon this reading could not resolve, and
it answers `False` -- a stranger. That is the fail-closed direction for this
particular question: read as a fleet-mate, an unresolvable row would take a
pilot **out** of the list this bot leaves over, which is the one mistake here
that costs the ship.

-}
chatUserIsKnownFleetmate : EveOnline.ParseUserInterface.ChatUserEntry -> Bool
chatUserIsKnownFleetmate chatUser =
    case chatUser.standingIconHint of
        Nothing ->
            False

        Just standingIconHint ->
            stringContainsIgnoringCase chatUserFleetmateMarker standingIconHint


{-| Every pilot on the overview who Local does not say is a fleet-mate.

`getNamesOfOtherPilotsInOverview`'s shape, from
`eve-online-combat-anomaly-bot`: the chat rows are what say a name belongs to a
_player_, so an overview row is a pilot exactly where its Name appears in Local,
and the fleet-mates are filtered out of that list before the match rather than
after it.

**Gas-huffing doctrine is trust nobody, so a blue who is not fleeted still means
leave** -- #456's own wording. Nothing here reads standings; a pilot is either in
this fleet, by the client's own hint, or they are a reason to go.

Compared trimmed and ignoring case, because the two sides are two renderings of
one name by two widgets and nothing guarantees the client capitalises them
alike.

-}
pilotsOnTheOverviewNotInTheFleet :
    List EveOnline.ParseUserInterface.ChatUserEntry
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
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


{-| Every rat on the overview, as rows rather than as names.

The rows rather than their names, because what fires this trigger is the icon
colour and a rat whose Name column is not visible fires it just the same -- so a
rule answering a list of names would have a nameless rat drop out of it
silently. `gridEvidenceFromReading` is what names them afterwards, and it writes
a sentence in place of a name it could not read rather than one fewer entry.

-}
ratsOnTheOverview :
    List EveOnline.ParseUserInterface.OverviewWindowEntry
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
ratsOnTheOverview =
    List.filter iconSpriteHasColorOfRat


{-| The Type cells that are not a ship, and the whole subtlety of trigger 3.

**A system's own structures sit on D-Scan permanently and carry no ship-naming
tag** -- the home structure this bot deposits at among them. So a rule of the
form "any untagged D-Scan entry is a threat" puts this bot into permanent
evasion in any inhabited system, retreating from furniture rather than from
threats, and #456 confirmed it live: with D-Scan widened, every row present was
a structure.

The filter is therefore on the **Type** column, against Upwell structure and
deployable hulls. That is public CCP game data in exactly the sense the rat
icon-colour rule above is: it identifies a class of object in the game and names
no corporation, alliance, system, structure or pilot, so it is a constant here
rather than one of #456's operator settings.

**Three groups, each with its own reason:**

  - the Upwell hulls, which is what the issue names. Matched as substrings, so a
    faction Fortizar (`'Moreau' Fortizar`) and an `Upwell Palatine Keepstar`
    are covered by the plain hull name rather than by a list of every variant.
  - `Mobile` as a family, because every deployable in the game is named that
    way -- Mobile Depot, Mobile Tractor Unit, Mobile Micro Jump Unit, the warp
    disruption bubbles -- and no ship hull is. One entry rather than a dozen that
    would go out of date the next time CCP ships one.
  - the harvestable cloud, which is **this bot's own reason for being there**.
    Whether a gas cloud appears on D-Scan at all is unverified; if it does not,
    this entry costs nothing, and if it does, leaving it out would have this bot
    read the cloud it is harvesting as an untagged ship and evade its own site
    forever. It is `harvestableCloudTypeMarker`, the same constant the overview
    rule reads, rather than the string written a second time.

**What is deliberately _not_ here is everything else that is not a ship.** A
fleet-mate's drones, a wreck and a jettisoned container all carry no ship tag and
would read as hostile. That is the safe direction -- an unnecessary retreat costs
a warp -- and widening this list is the direction that costs the ship, so nothing
goes in it without something that measured the string.

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
    , harvestableCloudTypeMarker
    ]


{-| Every drone group the client writes carries this word, and no ship hull does.

Run 6 evaded on two rows reading `Mining Drone I` and harvested nothing, which is
the probe defect one class wider: a drone is not a piloted ship, carries no ship
name to tag, and so reads hostile under the untagged rule. A fleetmate mining
beside this bot is enough to keep it evading for a session.

**Matched on the Type cell only**, which is what `dscanTypeIsNotAShip` is asked
about and is the property that makes this safe. A Type is the client's own group
name; a _Name_ is whatever a player typed. Matching `Drone` in a name would let
anybody who calls their ship `Dronebait` read as harmless to this bot, which is
the one direction this file refuses -- so it is deliberately not asked of the
name, unlike `dscanRowIsHarmlessProbe`, which has to ask both because a probe's
cells were never measured apart.

Every drone group contains it -- Light Scout Drone, Medium Scout Drone, Heavy
Attack Drone, Sentry Drone, Mining Drone, Salvage Drone, Logistic Drone,
Electronic Warfare Drone -- so one entry covers the family rather than a list of
hulls that goes stale the next time CCP ships one. That is `Mobile`'s argument
next door.

**`Fighter` is deliberately absent.** Carrier and supercarrier fighters are
`Light Fighter`, `Heavy Fighter` and `Support Fighter`, none of which carry this
word, and a fighter on grid means a capital is on grid -- which is the most
alarming thing this bot could see, not something to ignore.

**Unverified: a drone's Type cell has not been read.** The rows that provoked
this printed `Mining Drone I`, which is the Name; D-Scan held only a fleetmate by
the time the rule was written. If a drone's Type is empty or unreadable the row
falls through to the name and reads hostile -- the safe direction, and the same
one every other unreadable cell takes here.

-}
droneTypeMarker : String
droneTypeMarker =
    "Drone"


{-| Whether a D-Scan row's Type says it is not a ship.

Matched ignoring case as a substring, for `notAShipOnDscanTypeMarkers`' reasons.

**A Type cell this parser could not read is not a structure**, which is where
this rule fails closed: `dscanRowVerdict` reaches this with a `Maybe` and an
absent Type falls straight through to the ship branch, where an unreadable Name
then reads hostile. Defaulting the Type to `""` here would be the same collapse
one column along -- and `""` matches no marker, so it would happen to behave
today and would be one edit from a marker that matched everything.

-}
dscanTypeIsNotAShip : String -> Bool
dscanTypeIsNotAShip typeText =
    notAShipOnDscanTypeMarkers
        |> List.any (\marker -> stringContainsIgnoringCase marker typeText)


{-| A probe is not a ship -- **except a combat probe, which is a hunt in progress.**

Run 3, live on 2026-09-07, evaded on eight rows all reading `Scanner Probe` and
harvested nothing. Probes are deployable objects rather than ships and carry no
ship name to tag, so the untagged rule reads every one of them as hostile: this
bot could not work in any system where anybody's probes were out, **including
its own**, since the operator scans the site down before hunting it.

The operator's own rule, and the reason this is two predicates rather than one
more entry in the list above: _evading combat probes is good; evading scanner
probes is paranoid._ Core probes are somebody scanning signatures, which is
ordinary wormhole traffic. **Combat** probes are the thing that scans a ship
down, and a cloaked huffer's whole defence is not being found -- so they are
exactly what this bot should leave for, and they must not be swept up by a rule
written to ignore their harmless siblings.

**Both cells are tested, deliberately.** The live rows printed `Scanner Probe`
and nothing else, and with D-Scan empty by the time this was written there was no
reading to say whether that came from the Name column or the Type column. Asking
both is what makes the rule correct either way rather than correct if a guess
about column layout holds -- and it costs nothing, since no ship hull carries
either phrase.

**Unverified, and it is the half that matters:** no combat probe has been seen on
this bot's D-Scan, so `combatProbeMarker` is CCP's own naming for the item rather
than a string read off a reading. If it is wrong, this bot ignores the probes it
most needs to run from -- which is the direction this whole file otherwise
refuses, and it is accepted here only because the alternative measured live is a
bot that evades continuously and never harvests. **The first run that meets one
is what settles it**, and the status line prints every judged row's cells for
exactly that reason.

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


{-| The three cells of one D-Scan row, as a record a case can write out.

A record rather than `EveOnline.ParseUserInterface.DirectionalScanResult`,
which carries a `uiNode` nothing here reads and which no case could build
without a whole UI tree. `dscanSightingsFromWindow` is the one place the two
meet.

-}
type alias DscanSighting =
    { name : Maybe String
    , type_ : Maybe String
    , distance : Maybe String
    }


dscanSightingsFromWindow : EveOnline.ParseUserInterface.DirectionalScannerWindow -> List DscanSighting
dscanSightingsFromWindow window =
    window.scanResults
        |> List.map
            (\row -> { name = row.name, type_ = row.type_, distance = row.distance })


{-| What this bot makes of one row on D-Scan.

Three answers rather than two, and every one of them names what it read, because
this is the rule whose premise is least settled: **no row for a piloted ship has
ever been measured** (#458), so the first live run that meets one has to be able
to see, from the log alone, which of these three it produced and off which
cells.

-}
type DscanRowVerdict
    = RowIsNotAShip String
    | ShipIsOneOfOurs String
    | ShipIsHostile DscanHostileReason
    | RowCouldNotBeRead


{-| Why a row read hostile, which is two different things.

`ShipNameCouldNotBeRead` is the one #458 answers `Nothing` rather than `""`
precisely so this file can express -- a row whose Name cell the parser declined
to read, which is what a row of an unexpected shape produces. Collapsing it into
the other reason would lose the distinction on the reading that matters most: a
grid full of them is the parser meeting a shape nobody predicted, where a grid
full of the other is a grid full of strangers.

-}
type DscanHostileReason
    = ShipNameCarriesNoFriendlyTag String
    | ShipNameCouldNotBeRead


{-| The rule the whole of trigger 3 is, over one row.

**Absent evidence reads as hostile here, which inverts this repo's usual
direction**, and it is asserted rather than assumed at each of the places it
could be undone:

  - `friendly-ship-tag` unset makes `shipReadsFriendly` answer `False` for every
    name there is, so every ship reads hostile. That is `TrustNobody`, decided
    in `hostileTrustFromSettings` and read here rather than restated.
  - a Name cell the parser could not read, **with the Type cell readable**, is
    `Nothing` and answers hostile. It is **not** defaulted to `""`: an empty
    string carries no tag, so today's behaviour would be identical and the
    safety would be an accident of the tag never being empty -- and
    `valueTypeNonEmptyString` is the only thing keeping that true.
  - a Type cell the parser could not read, **with the Name cell readable**, is
    not a structure, so the row is judged as a ship.

The direction costs a warp when it is wrong and costs the ship when it is wrong
the other way, which is the whole of why it is this way round.

**Both cells unreadable is a fourth case, and it is not evidence of anything.**
Run 1, live on 2026-09-07: every reading that produced `ShipIsHostile
ShipNameCouldNotBeRead` for a real site's own scanner probes had `[<unreadable>
| <unreadable> | <unreadable>]` for **all three** cells, Distance included, and
landed on a reading logged `Last completed scan 0s ago` -- the row captured in
the instant between the refresh landing and the client finishing drawing the
new result text into it, not a ship of an unusual shape. The same probes read
correctly (`Type 'Sisters Core Scanner Probe'`, excluded) on the very next
scan. Treating a blank row as `ShipNameCouldNotBeRead` made the site's own
probes flip between harmless and hostile from one D-Scan refresh to the next,
which is what drove the ship to evade a clean grid and warp home over and over.

A Type cell that reads _something_ -- any text at all, matching no known marker
-- is still real evidence of an object out there, and stays hostile: that is
the case the two bullets above are about, and it is untouched. Only the reading
that produced **no cell text whatsoever** is reclassified, to `RowCouldNotBeRead`,
which `dscanHostileReason` answers `Nothing` for -- the same as a row this bot
has positively identified as harmless, but distinguished in the decision log
(`describeDscanRowVerdict`) so a grid that is genuinely full of unreadable rows
still reads differently from one with nothing on it at all.

-}
dscanRowVerdict : HostileTrust -> DscanSighting -> DscanRowVerdict
dscanRowVerdict trust row =
    if dscanRowIsHarmlessProbe { name = row.name, type_ = row.type_ } then
        -- Asked before the Type list and before the name, because a probe is
        -- identified by either cell and carries no ship name to tag. See
        -- `dscanRowIsHarmlessProbe`: a *combat* probe fails this and falls
        -- through to the ship branch below, which is the whole point of it.
        RowIsNotAShip (row.type_ |> Maybe.withDefault probeMarker)

    else
        case row.type_ |> Maybe.andThen structureTypeThatIsNotAShip of
            Just typeText ->
                RowIsNotAShip typeText

            Nothing ->
                case ( row.type_, row.name ) of
                    ( Nothing, Nothing ) ->
                        -- The whole row came back blank -- no cell said
                        -- anything at all, which is a reading that raced the
                        -- D-Scan refresh rather than a sighting of anything.
                        RowCouldNotBeRead

                    ( _, Nothing ) ->
                        ShipIsHostile ShipNameCouldNotBeRead

                    ( _, Just name ) ->
                        if shipReadsFriendly trust name then
                            ShipIsOneOfOurs name

                        else
                            ShipIsHostile (ShipNameCarriesNoFriendlyTag name)


structureTypeThatIsNotAShip : String -> Maybe String
structureTypeThatIsNotAShip typeText =
    if dscanTypeIsNotAShip typeText then
        Just typeText

    else
        Nothing


{-| What the Directional Scanner is telling this bot, including that it is not.

Four answers, and the three that are not `DscanWasRead` are the whole of #462's
"a reading with no D-Scan window at all is not a clean grid". **"We do not know"
must not read as safe**, which is how a bot concludes it is safe because nothing
answered -- so they are separate constructors rather than an empty row list, and
`gridVerdict` can neither read one as clean nor lose which of them it was.

-}
type DscanState
    = DscanWindowIsNotInTheReading
    | DscanHasNeverBeenScanned
    | DscanIsStale { secondsSinceScan : Int, staleAfterSeconds : Int }
    | DscanWasRead (List DscanRowVerdict)


{-| How many refresh intervals a scan may be old before it stops counting.

A **multiple of `dscan-interval-seconds` rather than a number**, so an operator
who lengthens the interval lengthens the bound with it and the argument cannot
drift away from the figure -- `messageBoxStandoffGiveUpReadings`' form for the
same reason.

Three, because that is the smallest bound a refresh can miss twice without
firing: the host stands down for five seconds after any human input, the ask goes
out again at the next interval, and a bound of one would report `CANNOT TELL`
every time somebody touched the mouse. What it does catch is a scan that has
stopped arriving at all -- a shut D-Scan window, a keybind that is not the one
this bot presses, a docked reading, or anything above this branch holding the
tree -- which is what makes it reachable rather than a bound nothing can meet.

-}
dscanStaleAfterIntervals : Int
dscanStaleAfterIntervals =
    3


dscanStaleAfterSeconds : Int -> Int
dscanStaleAfterSeconds intervalSeconds =
    intervalSeconds * dscanStaleAfterIntervals


{-| The D-Scan half of the verdict, over facts a case can write out.

Both `Maybe`s here are a distinct answer rather than an empty one.
`windowSightings` of `Nothing` is _no window in the reading_, where `Just []` is
a window that scanned and found nothing -- and the status line prints those two
differently, because collapsing them is the failure the issue names.
`secondsSinceScan` of `Nothing` is _no scan has completed this session_, which
is where every run starts and which is not the same fact as a scan that has gone
old.

-}
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

A record of plain facts rather than a `BotDecisionContext`, for #106's reason:
this is the rule the ship's survival rests on, and a rule reachable only through
a decision context is one no case can execute -- so it would be checked by being
read, which is how a rule that answers `clean` for the wrong reason passes for
one that works.

-}
type alias GridEvidence =
    { ratsOnOverview : List String
    , pilotsNotInTheFleet : List String
    , localChatIsReadable : Bool
    , dscan : DscanState
    }


{-| The verdict, and the two ways of not being clean.

**Three answers rather than two.** A grid this bot cannot see is not a grid it
may go on harvesting, and it is also not a grid it has seen a hostile on -- and
#463 needs to tell them apart to say why it is still evading. What neither of
them is is _clean_: `gridReadsClean` answers `True` for `GridIsClean` and for
nothing else, which is the one line the whole design rests on.

A hostile outranks a doubt where both are present, because the hostile is the
one an operator can act on and the doubt is already implied by it.

-}
type GridVerdict
    = GridIsClean
    | SomethingIsOnTheGrid (List String)
    | CannotTellWhetherTheGridIsClean (List String)


gridReadsClean : GridVerdict -> Bool
gridReadsClean verdict =
    verdict == GridIsClean


{-| The three triggers, and the doubts, asked in one place.

The reasons are strings because they are for an operator and for #463's own
decision line, and building them here rather than at the two call sites is
#102's rule: one fact settled once and read twice cannot come to disagree, and
the way it would fail here is a status line reporting a clean grid the retreat
was acting on.

-}
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


{-| The evidence this reading carries, assembled from the client.

The Local chat window is asked for through `EveOnline.BotFramework`'s own
`localChatWindowFromUserInterface` rather than by matching a window name here,
because that helper is what every other app in this repo uses for the same
question and a second spelling of "which window is Local" would be a second
place to be wrong.

**`overviewEntryIsDisplayed` is deliberately not applied here**, and it is the
one place in this app where a hidden overview row is read on purpose. That
filter exists because the overview virtualises and a hidden row's _region_
belongs to whatever was recycled into it -- so `cloudSearch`, which is choosing
something to click, must never see one. Nothing here clicks anything. What a
recycled row can do to this rule is contribute a stale name, and a stale name
this bot leaves over costs a warp where a row it declined to read costs the
ship. Same argument as everything else in this section, applied to the one
filter that runs the other way.

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
                |> EveOnline.BotFramework.localChatWindowFromUserInterface
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


{-| What an operator reads about the grid, on every reading.

Opens with the verdict, because it is the one line that says whether this ship
should still be here, and then prints the D-Scan rows **raw**.

**Printing every judged row's own three cells is #462's own requirement rather
than decoration.** No D-Scan row for a piloted ship has ever been read here: all
four rows measured for #458 were structures, and the dangerous direction is a
corporation ticker landing in the Name cell and matching the friendly tag. So
the first run that meets a ship has to settle the row's shape from the log
alone, which it can only do if the log carries what the parser made of each cell
-- including which cells it made nothing of, which is why an unreadable cell
prints in words rather than as a blank.

-}
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


{-| Every D-Scan row's cells exactly as the parser answered them.

Separate from `describeDscanRowVerdict` because the two say different things: one
is what this bot concluded and the other is what it concluded it _from_, and the
run that settles a ship's row shape needs the second. An unreadable cell prints
`<unreadable>` rather than an empty string, so a cell the parser declined and a
cell holding nothing cannot read alike in the one place that was built to keep
them apart.

-}
describeDscanSightings : List DscanSighting -> String
describeDscanSightings sightings =
    let
        cell =
            Maybe.withDefault "<unreadable>"
    in
    if List.isEmpty sightings then
        "D-Scan rows: none."

    else
        "D-Scan rows (Name | Type | Distance, as parsed): "
            ++ (sightings
                    |> List.map
                        (\sighting ->
                            "["
                                ++ cell sighting.name
                                ++ " | "
                                ++ cell sighting.type_
                                ++ " | "
                                ++ cell sighting.distance
                                ++ "]"
                        )
                    |> String.join " "
               )
            ++ "."


describeDscanSightingsFromReading : ReadingFromGameClient -> String
describeDscanSightingsFromReading readingFromGameClient =
    case readingFromGameClient.directionalScannerWindow of
        Nothing ->
            "D-Scan rows: no window in this reading."

        Just window ->
            describeDscanSightings (dscanSightingsFromWindow window)



-- Keeping the Directional Scanner fresh


{-| The keypress that refreshes the Directional Scanner.

`V` is the client's own default binding for the scan, and this bot presses it
and nothing else -- there is no click here, because the parser #458 built exposes
the window's rows and no button, and adding a button lookup would be an
eight-copy parser concern (#467) rather than a one-file edit.

**Nobody has watched this land.** The keypress is what #462 says the refresh is,
and the client's answer to it -- a scan that completes, and results that replace
the previous ones -- is not something a reading can distinguish from results that
were already there. What covers a key that is not bound is the staleness bound:
a client that never scans reports `CANNOT TELL` within
`dscanStaleAfterIntervals` intervals rather than reporting a clean grid, which
is the direction this has to fail in.

-}
directionalScanHotkey : List EffectOnWindow.VirtualKeyCode
directionalScanHotkey =
    [ EffectOnWindow.vkey_V ]


{-| When the last refresh went out, and when a scan last came back.

Two clocks rather than one, because they answer different questions and only one
of them is about safety. `lastRefreshAskedAtMilliseconds` paces the asking, which
is a cost question -- a refresh every reading would be a keypress every reading.
`lastScanAtMilliseconds` is what the verdict is allowed to believe, and it only
moves on a reading that had both an ask behind it and a window to read.

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


{-| The two clocks after this reading.

Written in `updateMemoryForNewReadingFromGame`, the one place that can write
memory and the one that never sees a decision -- so what it records is what the
previous step **dispatched** and what this reading **holds**, rather than what a
branch believed it was doing.

**What it cannot record is whether the client acted on the press**, and that is
stated here rather than left to be discovered. This host skips an input sequence
for five seconds after any human touch of the mouse or keyboard, and the bot is
not told; the client's D-Scan window goes on showing the previous scan's rows
either way. So `lastScanAtMilliseconds` is a moment the bot _asked_ and could
read the window afterwards, which makes the age it yields a **lower bound** on
the true age of those rows. Nothing in a reading can do better, and what a
smaller bound would buy is not more truth but more `CANNOT TELL`.

-}
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


{-| Whether it is time to press the scan key again.

**A floor rather than a schedule**, which is #462's own word for it. A refresh
that does not go out -- the host standing down for a human at the keyboard, the
tree held above this branch by a message box -- costs nothing here and is asked
for again at the next reading past the interval, because the comparison is
against when one last _went_ rather than against a tick the bot has to keep up
with.

Never having asked is due, which is what gets the first scan of a session out on
the first reading in space rather than an interval into it.

-}
dscanRefreshIsDue :
    { nowMilliseconds : Int, intervalSeconds : Int, dscan : DscanMemory }
    -> Bool
dscanRefreshIsDue { nowMilliseconds, intervalSeconds, dscan } =
    case dscan.lastRefreshAskedAtMilliseconds of
        Nothing ->
            True

        Just askedAt ->
            intervalSeconds * 1000 <= nowMilliseconds - askedAt


describeDscanCadence :
    { nowMilliseconds : Int, intervalSeconds : Int, dscan : DscanMemory }
    -> String
describeDscanCadence cadence =
    "D-Scan cadence: refreshing every "
        ++ String.fromInt cadence.intervalSeconds
        ++ "s (a floor, not a promise -- this host skips input for five seconds after any human touch), believing a scan for "
        ++ String.fromInt (dscanStaleAfterSeconds cadence.intervalSeconds)
        ++ "s. "
        ++ (case secondsSinceLastScan { nowMilliseconds = cadence.nowMilliseconds, dscan = cadence.dscan } of
                Nothing ->
                    "No scan has completed this session."

                Just seconds ->
                    "Last completed scan " ++ String.fromInt seconds ++ "s ago."
           )
        ++ (if dscanRefreshIsDue cadence then
                " A refresh is due now."

            else
                ""
           )



-- Where this bot goes when it leaves, and what it does once it is there


{-| The label half of a Locations row's text.

A `PlaceEntry`'s `mainText` is not a label: the client renders that window as a
grid and the parser takes the row's own text node, which arrives as the row's
cells joined by `<t>` tags -- `Label<t>Folder` on the rows measured for #457,
the same shape `parseLocationsWindowPlaceEntry`'s own comment quotes from the
2024 recording (`...<t>Refinery<t>0<t>Y5C-YD<t>...`).

So `retreat-bookmark-prefix` is matched against the **first** field and not
against the blob. Matching the blob would make the prefix match a folder name as
readily as a bookmark's own, which is a widening in the direction that decides
where this ship is sent unattended -- and it would also silently stop matching
the day the client puts another column in front.

A row carrying no tag at all is its own label, which is what makes this safe to
run over every row rather than only over the ones that look joined.

-}
bookmarkCellSeparator : String
bookmarkCellSeparator =
    "<t>"


bookmarkLabel : String -> String
bookmarkLabel mainText =
    mainText
        |> String.split bookmarkCellSeparator
        |> List.head
        |> Maybe.withDefault mainText
        |> String.trim


{-| Whether a bookmark's label starts with the operator's retreat prefix.

`String.startsWith` on the label, which is the issue's own wording and is
narrower than the `stringContainsIgnoringCase` this file uses for
`bookmarkedGasSiteMarker` one section up. The two are matched differently on
purpose: that one is the **client's** word for a site family and can sit
anywhere inside a name an operator typed around it, where this one is a marker
the operator puts at the front themselves, precisely so that a glance at the
Locations window says which bookmarks the bot may use.

Case is not folded, for the same reason. A prefix chosen to be distinctive --
`*` is the shipped default -- is one an operator can type consistently, and
folding case here would quietly admit a bookmark named `Safe` to a fleet that
marks its safes `safe-`.

-}
bookmarkLabelStartsWithPrefix : String -> String -> Bool
bookmarkLabelStartsWithPrefix prefix mainText =
    bookmarkLabel mainText |> String.startsWith prefix


{-| The three places this bot will run to, as the three different facts they are.

The order is #463's and the reasons are not interchangeable, which is why this is
a type rather than a list of candidates:

  - a **bookmark carrying `retreat-bookmark-prefix`** is a place the operator has
    said in advance is safe to arrive at unattended, and it is warped to at zero
    because instadock-style bookmarks are already placed for that;
  - the **home structure on the overview** is somewhere with a tether and a dock,
    warped to at zero for the same reason -- but it is second because it is a
    place the operator named for _depositing_ (#464) rather than for arriving at
    under somebody else's guns;
  - **any bookmark at all, at 100 km**, is the last resort and the range is the
    whole of the difference. Nothing here knows what that bookmark is on top of,
    so landing 100 km off it is the one arrival that does not depend on knowing.

`destination` is a `Maybe` and the reasons it is `Nothing` are carried beside it
rather than folded into it, for `AnomalyVerdict`'s reason one section up: an
operator watching a bot with nowhere to go fixes a different thing depending on
whether the Locations window is shut, no bookmark carries the prefix, or
`home-structure-name` names a structure that is not on this grid.

-}
type RetreatDestination
    = ToAPrefixedBookmark EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
    | ToTheHomeStructure EveOnline.ParseUserInterface.OverviewWindowEntry
    | ToAnyBookmarkAtAll EveOnline.ParseUserInterface.LocationsWindowPlaceEntry


{-| The two windows the retreat reads, and nothing else.

`SiteSearchReading`'s shape and for its reason: a record of parsed windows rather
than a whole `BotDecisionContext`, so `retreatSearch` is a rule a case can hand a
reading and execute (#106). The overview entries arrive already concatenated,
because which window a row came from decides nothing here.

-}
type alias RetreatSearchReading =
    { locationsWindow : Maybe EveOnline.ParseUserInterface.LocationsWindow
    , overviewEntries : List EveOnline.ParseUserInterface.OverviewWindowEntry
    }


type alias RetreatSearchSettings =
    { bookmarkPrefix : String
    , homeStructureName : Maybe String
    }


{-| Everything one reading has to say about where this ship would run to.

The window's _presence_ is carried apart from what it held, which is
`SiteSearch`'s rule and wants the same fix from an operator: a Locations window
that is shut and a Locations window holding no matching bookmark are different
states, and a list that is empty for either reason cannot tell them apart.

-}
type alias RetreatSearch =
    { settings : RetreatSearchSettings
    , locationsWindowIsOpen : Bool
    , bookmarksInTheWindow : Int
    , bookmarksCarryingThePrefix : List String
    , homeStructureRowsOnTheOverview : List String
    , destination : Maybe RetreatDestination
    }


{-| The one declaration that decides where this bot runs to, with two readers.

The decision and the status line both call it through `retreatSearchFromContext`
-- #102, and the way it fails here is a status line naming a bookmark the ship
was not sent to. The rungs are evaluated in order and the first that answers
wins; nothing below a rung that answered is looked at at all, because a fallback
that can outrank the thing it is a fallback for is not a fallback.

**The home-structure row is filtered on `_display` and the bookmarks are not**,
and that asymmetry is the overview's own. An overview row is a click at a screen
position and the overview virtualises, so a hidden row's region belongs to
whatever was recycled into it -- see `overviewEntryIsDisplayed`. A Locations row
is a row in a list the client is not recycling that way, and the parser drops any
node it cannot read a region for before this ever sees it.

`siteCellMatches` is what the home structure's name is matched with rather than a
second matcher written here: it is whole and case-insensitive with a trailing `*`
meaning a prefix, which is what `anomaly-group` already promises an operator, and
two spellings of "does this setting match this cell" would be two places to
disagree.

-}
retreatSearch : RetreatSearchSettings -> RetreatSearchReading -> RetreatSearch
retreatSearch settings reading =
    let
        bookmarks =
            reading.locationsWindow
                |> Maybe.map .placeEntries
                |> Maybe.withDefault []

        prefixed =
            bookmarks
                |> List.filter
                    (.mainText >> bookmarkLabelStartsWithPrefix settings.bookmarkPrefix)

        homeStructureRows =
            homeStructureRowsOnTheOverview settings.homeStructureName reading.overviewEntries
    in
    { settings = settings
    , locationsWindowIsOpen = reading.locationsWindow /= Nothing
    , bookmarksInTheWindow = List.length bookmarks
    , bookmarksCarryingThePrefix = prefixed |> List.map (.mainText >> bookmarkLabel)
    , homeStructureRowsOnTheOverview =
        homeStructureRows |> List.map (.objectName >> Maybe.withDefault "")
    , destination =
        [ prefixed |> List.head |> Maybe.map ToAPrefixedBookmark
        , homeStructureRows |> List.head |> Maybe.map ToTheHomeStructure
        , bookmarks |> List.head |> Maybe.map ToAnyBookmarkAtAll
        ]
            |> List.filterMap identity
            |> List.head
    }


{-| The overview rows that are the structure `home-structure-name` names.

**One declaration with two readers**, which is #102's rule and the way it would
fail here is the sharpest version of it this file has: the retreat's second rung
and the deposit's only destination are the same structure, so two spellings of
"which row is home" would be a bot that runs to one place when it is frightened
and flies to another when it is full, with both status clauses reading correctly.

Filtered on `_display` because both readers act on the row at a screen position
-- the retreat right-clicks it and the deposit selects it -- and the overview
virtualises, so a hidden row's region belongs to whatever was recycled into it.
See `overviewEntryIsDisplayed`.

`siteCellMatches` rather than a matcher written here, so this setting means what
`anomaly-group` already promises an operator: whole, ignoring case and
surrounding space, with a trailing `*` meaning a prefix.

**An unset setting answers `[]`** rather than taking the first structure it sees.
There is no default and there cannot be one -- it names a structure in one
wormhole belonging to one operator -- and a bot that guessed would dock a full
ship at somebody else's citadel.

-}
homeStructureRowsOnTheOverview :
    Maybe String
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
homeStructureRowsOnTheOverview homeStructureName overviewEntries =
    case homeStructureName of
        Nothing ->
            []

        Just name ->
            overviewEntries
                |> List.filter overviewEntryIsDisplayed
                |> List.filter
                    (\entry ->
                        entry.objectName
                            |> Maybe.map (\objectName -> siteCellMatches objectName name)
                            |> Maybe.withDefault False
                    )


{-| A bookmark in the Locations window carrying the home structure's own name.

The overview is where this bot docks from, but it is not the only place the
structure's name can appear: an operator who bookmarked the structure directly
gets a bookmark this bot can warp to at zero from anywhere in the same system,
without depending on the overview having rendered the structure at all. This is
what `depositChainHop` asks before it concludes there is genuinely nowhere to
run to and starts working a wormhole chain back toward known space.

Matched with `siteCellMatches` against `bookmarkLabel`, which is the same rule
`homeStructureRowsOnTheOverview` uses against the overview's Name column --
whole, ignoring case and surrounding space, with a trailing `*` meaning a
prefix -- so an operator's one setting means the same thing read off either
window.

-}
homeStructureBookmarkInLocations :
    Maybe String
    -> Maybe EveOnline.ParseUserInterface.LocationsWindow
    -> Maybe EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
homeStructureBookmarkInLocations homeStructureName locationsWindow =
    case homeStructureName of
        Nothing ->
            Nothing

        Just name ->
            locationsWindow
                |> Maybe.map .placeEntries
                |> Maybe.withDefault []
                |> List.filter (\entry -> siteCellMatches (bookmarkLabel entry.mainText) name)
                |> List.head


retreatSearchFromContext : BotDecisionContext -> RetreatSearch
retreatSearchFromContext context =
    let
        settings =
            context.eventContext.botSettings
    in
    retreatSearch
        { bookmarkPrefix = settings.retreatBookmarkPrefix
        , homeStructureName = settings.homeStructureName
        }
        { locationsWindow = context.readingFromGameClient.locationsWindow
        , overviewEntries =
            context.readingFromGameClient.overviewWindows |> List.concatMap .entries
        }


{-| What an operator reads about where this ship would go, on every reading.

Said whether or not anything is on the grid, which is the whole point of it being
here rather than inside the retreat: the reading an operator wants this sentence
on is the quiet one **before** a hostile arrives, while there is still time to
open the Locations window. `RETREAT NOT ARMED` was this clause's ancestor and
said the same thing about a bot that could not leave at all; what replaced it
says which of the three rungs this reading would take, and shouts on the one
reading where the answer is none of them.

-}
describeRetreatSearch : RetreatSearch -> String
describeRetreatSearch search =
    let
        homeClause =
            case search.settings.homeStructureName of
                Nothing ->
                    "'home-structure-name' is unset"

                Just name ->
                    "'" ++ name ++ "' is not a row on this overview"

        rung =
            case search.destination of
                Just (ToAPrefixedBookmark bookmark) ->
                    "to the bookmark '"
                        ++ bookmarkLabel bookmark.mainText
                        ++ "', which carries '"
                        ++ search.settings.bookmarkPrefix
                        ++ "', at "
                        ++ warpAtZeroMenuEntry
                        ++ "."

                Just (ToTheHomeStructure entry) ->
                    "no bookmark carries '"
                        ++ search.settings.bookmarkPrefix
                        ++ "', so to the home structure '"
                        ++ (entry.objectName |> Maybe.withDefault "")
                        ++ "' on the overview, at "
                        ++ warpAtZeroMenuEntry
                        ++ "."

                Just (ToAnyBookmarkAtAll bookmark) ->
                    "no prefixed bookmark and "
                        ++ homeClause
                        ++ ", so to '"
                        ++ bookmarkLabel bookmark.mainText
                        ++ "', which is simply the first bookmark there is, at "
                        ++ warpAt100KmMenuEntry
                        ++ "."

                Nothing ->
                    "NOWHERE TO RUN TO -- "
                        ++ (if search.locationsWindowIsOpen then
                                "the Locations window is open and holds "
                                    ++ String.fromInt search.bookmarksInTheWindow
                                    ++ " bookmark(s)"

                            else
                                "the Locations window is not open, so neither bookmark rung can be read at all"
                           )
                        ++ ", and "
                        ++ homeClause
                        ++ ". This ship's whole plan for anything arriving is to leave."
    in
    "Retreat: "
        ++ rung
        ++ " Locations: "
        ++ (if search.locationsWindowIsOpen then
                String.fromInt search.bookmarksInTheWindow
                    ++ " bookmark(s), "
                    ++ String.fromInt (List.length search.bookmarksCarryingThePrefix)
                    ++ " carrying '"
                    ++ search.settings.bookmarkPrefix
                    ++ "'"
                    ++ (if List.isEmpty search.bookmarksCarryingThePrefix then
                            "."

                        else
                            -- Named rather than counted, because the question an
                            -- operator asks of this clause is "why did it not
                            -- take mine", and a count cannot answer it. These
                            -- are labels rather than whole rows for
                            -- `bookmarkLabel`'s reason: a name they cannot find
                            -- in their own client is worse than none.
                            ": "
                                ++ String.join ", " search.bookmarksCarryingThePrefix
                                ++ "."
                       )

            else
                "window not open."
           )



-- The cloak, which may not be fitted at all


{-| What the client's own tooltip calls a cloak.

Stock EVE terminology in the sense `Gas Site`, `Reservoir` and
`Harvestable Cloud` are -- it is the game's own module group, shared by every
covert-ops and improved cloak there is -- so shipping it names nobody's fit, and
it is a constant rather than a setting under #456's rule.

Matched against the tooltip's texts because **nothing else in a reading says what
a module is.** A module button carries no name of its own: the two gas harvesters
on the hull #456 measured share a `_name` and an icon texture, which is why
`harvesterModulesFromShipUI` identifies them by row and position instead.
Position cannot answer this one -- a cloak can sit in any slot -- and the client
setup contract deliberately does not claim a row for it, because a contract
nothing can check produces a bot pressing whatever is bound where it expected a
cloak.

-}
cloakingDeviceTooltipMarker : String
cloakingDeviceTooltipMarker =
    "Cloaking Device"


{-| One fitted module, as the two facts the cloak rule needs about it.

A record of plain facts rather than a `ShipUIModuleButton` and a
`ShipModulesMemory`, so `cloakAmongFittedModules` is a rule a case can execute
(#106). `tooltipTexts` empty is _this module has not been identified yet_, which
is not the same fact as a module identified as something else, and the two are
told apart in the status line because they want different things from an
operator: patience, or a fit with no cloak in it.

-}
type alias FittedModule =
    { tooltipTexts : List String
    , runningState : ModuleRunningState
    }


{-| Whether this ship has a cloak, and whether it is already on.

**Four answers, and the two negative ones are deliberately not one.** #456
recorded this as unverified before any run had flown, and it still is --
**the tooltip has never once resolved live.** Every recorded run (1, 5, 6, on
three different builds) reads `NOT KNOWN YET -- 0 of 2 module(s) have had their
tooltip read` for as long as it is asked, and every one of them eventually
prints `NONE FITTED -- all 0 module(s) have been identified` -- zero, not "found
none among several" -- which is `moduleIdentificationGiveUpReadings` expiring
rather than a genuine search coming up empty. So whether this hull carries a
cloak is exactly as unverified as #456 left it; what is now confirmed live is
the speculative fallback beside it, `Cloak up with its own hotkey`, fired 13 and
14 times in runs 1 and 5 with no module ever identified -- pressing F3 blind
because an evasion is exactly when there is no quiet reading left to spend on a
hover, never because a cloak was confirmed present.

**Neither of them stalls the evasion**, which is the issue's own requirement:
`evasionStep` reads this and falls through to the celestial bounce for both, so a
fit with no cloak in it evades without one rather than waiting for a module that
does not exist.

-}
type CloakSearch
    = TheModulesAreNotIdentifiedYet { identified : Int, total : Int }
    | NoCloakAmongTheModulesIdentified Int
    | TheCloakIsAlreadyRunning
    | TheCloakIsFittedAndNotRunning Int


cloakAmongFittedModules : List FittedModule -> CloakSearch
cloakAmongFittedModules modules =
    let
        identified =
            modules |> List.filter (.tooltipTexts >> List.isEmpty >> not)

        byTooltip =
            modules
                |> List.indexedMap Tuple.pair
                |> List.filter
                    (Tuple.second
                        >> .tooltipTexts
                        >> List.any (stringContainsIgnoringCase cloakingDeviceTooltipMarker)
                    )
    in
    case byTooltip of
        ( index, cloak ) :: _ ->
            case cloak.runningState of
                ModuleIsRunning ->
                    TheCloakIsAlreadyRunning

                ModuleIsNotRunning ->
                    TheCloakIsFittedAndNotRunning index

        [] ->
            if List.length identified < List.length modules then
                TheModulesAreNotIdentifiedYet
                    { identified = List.length identified
                    , total = List.length modules
                    }

            else
                NoCloakAmongTheModulesIdentified (List.length modules)


{-| The cloak's own hotkey, which the operator states rather than the bot discovering.

**The tooltip hunt above is kept and asked first**, and this is the fallback --
which is the opposite of how it reads, so the reason matters. A tooltip is the
only thing in a reading that says _what a module is_, and it is right whatever
the fit. What it is not is _timely_: the hover happens only on readings with
nothing else to press, so run 3 reached its first evasion with `0 of 5 module(s)`
identified and evaded uncloaked -- and an evasion is exactly when the cloak is
wanted and exactly when there is no quiet reading to spend on a hover.

The operator's own keybinds -- scoops on `F1` and `F2`, cloak on `F3` -- make it
pressable on the first reading, with no discovery at all.

**A hotkey and not a module index**, which is the correction that matters here.
`ActivateTheCloak` indexes into `fittedModulesFromContext`, and that list is the
**whole ship** in the parser's own order -- so "the third top-row module" and
"index 2 of every module on the hull" are different modules the moment the fit
has anything above the top row. Pressing the key the operator bound says exactly
what was meant and cannot drift with the fit; the index route would have clicked
whatever happened to be third.

**It is a claim about one fit.** A ship with no cloak on `F3` presses whatever is
there on the reading it leaves. The tooltip rule is asked first precisely to
bound that: once a hover has identified a real cloak anywhere on the hull, the
tooltip answer wins and this is never reached. Measured against run 3's cost,
which was evading with no cloak at all.

-}
cloakHotkey : List EffectOnWindow.VirtualKeyCode
cloakHotkey =
    [ EffectOnWindow.vkey_F3 ]


{-| Every module button in the reading, paired with what has been learned of it.

**The whole ship rather than one row**, unlike everything else in this file that
reads module buttons: a cloak can be fitted anywhere, where the two harvesters
and the propulsion module are found by row because the client setup contract puts
those in known places. The order is the parser's own and is used only to index
back into this same list on this same reading, which is `RunTheHarvester`'s
arrangement and carries the same caveat -- an index into a module list is only
ever good for the reading it was taken from.

-}
fittedModulesFromContext : BotDecisionContext -> List ( EveOnline.ParseUserInterface.ShipUIModuleButton, FittedModule )
fittedModulesFromContext context =
    context.readingFromGameClient.shipUI
        |> Maybe.map .moduleButtons
        |> Maybe.withDefault []
        |> List.map
            (\moduleButton ->
                ( moduleButton
                , { tooltipTexts =
                        EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton
                            context.memory.shipModules
                            moduleButton
                            |> Maybe.map
                                (.allContainedDisplayTextsWithRegion >> List.map Tuple.first)
                            |> Maybe.withDefault []
                  , runningState = moduleRunningState moduleButton
                  }
                )
            )


cloakSearchFromContext : BotDecisionContext -> CloakSearch
cloakSearchFromContext context =
    fittedModulesFromContext context |> List.map Tuple.second |> cloakAmongFittedModules


describeCloak : CloakSearch -> String
describeCloak search =
    "Cloak: "
        ++ (case search of
                TheModulesAreNotIdentifiedYet counts ->
                    "NOT KNOWN YET -- "
                        ++ String.fromInt counts.identified
                        ++ " of "
                        ++ String.fromInt counts.total
                        ++ " module(s) have had their tooltip read, and a cloak is only ever recognised by its tooltip saying '"
                        ++ cloakingDeviceTooltipMarker
                        ++ "'. An evasion starting now runs without one."

                NoCloakAmongTheModulesIdentified total ->
                    "NONE FITTED -- all "
                        ++ String.fromInt total
                        ++ " module(s) have been identified and none is a '"
                        ++ cloakingDeviceTooltipMarker
                        ++ "'. Evading without one is what this bot then does, on purpose."

                TheCloakIsAlreadyRunning ->
                    "fitted, and running."

                TheCloakIsFittedAndNotRunning index ->
                    "fitted in module slot "
                        ++ String.fromInt (index + 1)
                        ++ ", and not running."
           )


{-| How many readings the bot may spend hovering modules it has not identified.

**Spent only on readings the bot had nothing else to press**, which is where this
is asked from -- `NothingLeftToCommand`, the harvest loop's steady state once the
ship orbits, the cloud is locked and both harvesters cycle. So the bound is not
protecting the harvest, which cannot be starved from there; it is protecting
against the one failure `eve-online-mining-bot` records for this mechanism, which
is a tooltip that never lands and a hover repeated for the rest of the session.

Large, because those readings are free and a tooltip needs a hover sustained
across two consecutive readings to be stored at all
(`integrateCurrentReadingsIntoShipModulesMemory`). Two hundred is roughly a
hundred seconds at the shipped step delay; a session that has not identified them
by then is one where the mechanism is not working, and `describeCloak` says so
rather than the bot going on hovering.

-}
moduleIdentificationGiveUpReadings : Int
moduleIdentificationGiveUpReadings =
    200


{-| Learn what is fitted, on the readings there is nothing else to do.

`readShipUIModuleButtonTooltipWhereNotYetInMemory` is the framework's own, used
unchanged by `eve-online-mining-bot` and `eve-online-warp-to-0-autopilot`, and it
is the only thing in this repo that can tell a cloak from a hardener.

**Placed below the harvest loop and above nothing**, which is a trade stated
rather than assumed. The mining bot records the cost: reached only where there is
otherwise nothing to do, this mechanism identified one of that ship's two mining
lasers in a whole session, because something always wanted the mouse. Here the
thing that would starve it is the harvest loop, and the harvest loop's steady
state is precisely the state with nothing to press -- so the readings exist.
What it means is that **a cloak is identified during the quiet readings or not at
all**: a session whose first hostile arrives in its first minute evades without
one and says so, and that is better than spending a retreat's readings hovering
modules.

-}
identifyTheModulesFitted : BotDecisionContext -> Maybe DecisionPathNode
identifyTheModulesFitted context =
    if moduleIdentificationGiveUpReadings <= context.memory.modulesUnidentifiedReadings then
        Nothing

    else
        EveOnline.BotFrameworkSeparatingMemory.readShipUIModuleButtonTooltipWhereNotYetInMemory
            context
            |> Maybe.map
                (describeBranch
                    ("Nothing left to command on this cloud, so spend the reading learning what is fitted -- a cloak is recognised only by its tooltip, and #463 needs one identified before a hostile arrives rather than after ("
                        ++ String.fromInt context.memory.modulesUnidentifiedReadings
                        ++ "/"
                        ++ String.fromInt moduleIdentificationGiveUpReadings
                        ++ " readings spent)."
                    )
                )



-- Leaving, and staying gone until the grid reads clean


{-| How many readings one escape choice stays put.

Ported from the mission runner's `runAwayCelestialStickyReadings`, with its
reason: a choice has to outlive the manoeuvre that acts on it, or the bot opens a
context menu on one celestial and finishes the cascade on whichever one the next
reading picked instead. That cascade is longer here than the mission runner's
two-click one -- a right-click, a hover that opens the distance submenu, and a
click -- so twelve readings is if anything tight rather than generous.

It also has to keep moving while the grid stays dirty, which is why the choice
rotates at all rather than being drawn once.

-}
evasionCelestialStickyReadings : Int
evasionCelestialStickyReadings =
    12


{-| How long a commanded warp may fail to happen before a person is told.

**Issue #141's number and #141's posture, ported.** That issue is the worked
example this one is told to follow: a mission-runner retreat decided on 36
consecutive readings with the ship never entering warp, on a grid it was being
shot on. Three full rotations of the escape choice is where the only
self-correction a retreat owns has been spent on three separate destinations and
the ship is still where it was.

Written as three rotations rather than as `36`, so that an operator who changes
one changes the other with it and the argument cannot drift away from the figure.
`dscanStaleAfterIntervals` has the same shape for the same reason.

**It reports and does not repair**, which is the half that matters here: the
branch that carries this line goes on commanding the warp. See
`describeWarpNotExecuting`.

-}
warpNotExecutingAlarmReadings : Int
warpNotExecutingAlarmReadings =
    evasionCelestialStickyReadings * 3


{-| The exact sentence the watchdog treats as an alarm, shared rather than spelt
twice.

`EveOnline.BotFrameworkSeparatingMemory.askForHelpToGetUnstuck` writes it and
`stall_watch.py` matches it as a substring of any log line, which is what turns
it into a screenshot of the client. Three copies of one string across two
languages is a coupling this repo pins with a test rather than remembers, and a
drift here is silent in the direction that looks like a healthy run -- the line
still prints and nothing escalates.

The framework's copy is not imported because that value is a `DecisionPathNode`
rather than the string inside it, and the module is vendored eight times:
exporting one more name from it would be eight edits to make a literal reachable
(#467). `eve-online-mission-runner` carries the same constant for the same
reason.

-}
askForHelpToGetUnstuckText : String
askForHelpToGetUnstuckText =
    "I am stuck here and need help to continue."


{-| The one line an operator gets when a commanded warp is not happening.

It says what was commanded and how often, that the cause is unknown, and **that
the bot is still commanding it** -- the last because a reader who has just been
told the bot is stuck would otherwise reasonably assume it had stopped trying,
and the whole argument for reporting rather than acting is that it has not.

The sentence is carried into this line rather than reached by branching to
`askForHelpToGetUnstuck`, because that leaf dispatches no effects. Taking it
would stop the retreat commanding the warp, and stopping cannot help a ship that
is still on a hostile grid.

The count is in readings and the sentence says so, because this file has two
units -- readings and decisions -- and a log is easiest to mis-read in the other
one.

-}
describeWarpNotExecuting : Int -> String
describeWarpNotExecuting readings =
    "RETREAT NOT EXECUTING: I have decided to leave on "
        ++ String.fromInt readings
        ++ " consecutive readings -- readings, not decisions -- and the ship has"
        ++ " not been in warp on any of them. The warp is being commanded and it"
        ++ " is not taking. I do not know why, this hull has no guns and no tank"
        ++ " worth the name, and I am still commanding it because stopping cannot"
        ++ " help. "
        ++ askForHelpToGetUnstuckText


warpNotExecutingAlarm : { before : Int, now : Int } -> Maybe String
warpNotExecutingAlarm readings =
    if
        (readings.before < warpNotExecutingAlarmReadings)
            && (warpNotExecutingAlarmReadings <= readings.now)
    then
        Just (describeWarpNotExecuting readings.now)

    else
        Nothing


{-| How many readings the cloak may be asked for before the bot stops asking.

A module button is a toggle, so a press that is not answered is either a client
that did not take it or a press that switched something **off** -- and either way
a bot pressing it once per reading for the rest of an evasion is the failure
`pressModuleHotkey`'s settling window exists to prevent, one step further out.

Larger than `moduleButtonClickSettlingSteps`, because a cloak has a real spool-up
and this counts readings the client has answered nothing on; small next to
`moduleIdentificationGiveUpReadings`, because the readings this one spends are
readings of an evasion rather than readings of a quiet grid. On expiry the
evasion carries on uncloaked, which is the same fall-through a fit with no cloak
in it takes.

-}
cloakGiveUpReadings : Int
cloakGiveUpReadings =
    20


{-| How long this bot will evade before deciding the wormhole is not worth it.

**A give-up that ends the session, which is a different animal from the one above
and is placed differently for PR #115's reason:** it bounds elapsed time and
belongs where nothing can decline to ask it, so it is asked from the head of the
decision root and the counter behind it advances in
`updateMemoryForNewReadingFromGame` on every reading whatever the tree is doing.
The mission runner's #102 and saxrat's #133 are both what happens when that
placement is got wrong -- run 30 took a counter to 10,811 against a bound of 200,
because something above the comparison held the tree.

**Ending is a legitimate outcome here and it is not one for the warp bound
above.** A wormhole with somebody living in it is a wormhole this bot has no work
in: ending with the ship cloaked at a safe is a fine place to leave it, and
better than bouncing celestials until the session clock runs out. That is the
opposite of the retreat warp's bound, where ending would leave a ship on a
hostile grid with nobody at the controls -- which is how the mission runner's
run 7 lost a ship.

Six hundred readings is fifty rotations of the escape choice and roughly five
minutes at the shipped `bot-step-delay` of 499 ms. **The bound itself has still
never fired live**, though the counter it bounds has been watched running twice:
run 1 cleared several dozen short evasions, the counter climbing to as little as
1 and as much as 14 before dropping straight back to `not evading` each time --
real recoveries, not a stuck grid -- and run 6 (the merged tree) took it to
83/600 before being stopped by hand, the grid never once reading clean in that
session. Neither run says anything about the upper end: what it rests on is
still what expiry costs, which is a session that stops with the ship safe -- so
it is set long enough that a hostile passing through does not end a run, and
short enough that a resident does.

-}
evasionGiveUpReadings : Int
evasionGiveUpReadings =
    evasionCelestialStickyReadings * 50


evasionOutOfTime : { readings : Int } -> Maybe String
evasionOutOfTime evasion =
    if evasionGiveUpReadings <= evasion.readings then
        Just
            ("Evaded for "
                ++ String.fromInt evasion.readings
                ++ " readings without the grid reading clean once, which is past the bound of "
                ++ String.fromInt evasionGiveUpReadings
                ++ ". A wormhole with somebody living in it is one this bot has no work in, so this is the end of the session rather than something to shout about: the ship is wherever the last evasion warp put it, cloaked if one is fitted. Nothing here is stuck -- there is nothing here to do."
            )

    else
        Nothing


{-| The counters bounding everything the leaving does.

Advanced in `updateMemoryForNewReadingFromGame`, which is the only place that can
write memory and the one place that never sees a decision -- so what they count
is the **client's** answer rather than the branch's activity, and they keep
counting whatever else holds the tree. That is the half #102's placement rule is
about.

`readings` and `warpUnexecutedReadings` count different things and it matters
which is which: the first is how long this evasion has run at all, which is what
ends the session, and the second is how many of those readings were spent
commanding a warp that did not start, which is what fetches a person. An evasion
that is warping between celestials perfectly happily runs the first up and keeps
the second at zero.

`longestWarpUnexecutedReadings` survives the reset, because a session whose worst
retreat is over must still be able to say how bad it was.

-}
type alias EvasionCounters =
    { readings : Int
    , warpUnexecutedReadings : Int
    , longestWarpUnexecutedReadings : Int
    , cloakUnansweredReadings : Int
    }


initEvasionCounters : EvasionCounters
initEvasionCounters =
    { readings = 0
    , warpUnexecutedReadings = 0
    , longestWarpUnexecutedReadings = 0
    , cloakUnansweredReadings = 0
    }


{-| What one reading says about the leaving, in the terms the counters need.

A record rather than a reading, so a case can fold a whole session through
`evasionCountersAfterReading` and read the counters back -- which is how the one
property this issue rests on gets executed rather than argued: a session of
dirty, dirty, cannot-tell, dirty, clean resets on the last reading and on no
earlier one.

`gridIsClean` is `gridReadsClean`'s answer and nothing else, so a reading the bot
**cannot see** never resets any of these. That is the same line the whole design
rests on, read here rather than restated.

**`docked` resets them too, and that is not a widening of "clean".** Everything
these counters bound is a ship trying to get off a grid: `readings` ends the
session because a wormhole somebody lives in is one this bot has no work in, and
`warpUnexecutedReadings` fetches a person because a commanded warp is not
happening. A docked ship is doing neither -- it is in the safest place there is,
which is the successful **end** of any evasion rather than a reading spent on
one -- and counting docked readings against either bound would end a session, or
raise an alarm, about a ship in no danger at all. What keeps a docked ship from
waiting forever is not this: it is `depositGiveUpReadings`, which is running
whenever there is anything for a docked ship to be doing.

-}
type alias EvasionAnswerFromClient =
    { gridIsClean : Bool
    , docked : Bool
    , shipIsWarping : Bool
    , cloakAnsweredTheAsk : Bool
    }


evasionCountersAfterReading : EvasionAnswerFromClient -> EvasionCounters -> EvasionCounters
evasionCountersAfterReading answer counters =
    if answer.docked || answer.gridIsClean then
        { initEvasionCounters
            | longestWarpUnexecutedReadings = counters.longestWarpUnexecutedReadings
        }

    else
        let
            warpUnexecuted =
                if answer.shipIsWarping then
                    0

                else
                    counters.warpUnexecutedReadings + 1
        in
        { readings = counters.readings + 1
        , warpUnexecutedReadings = warpUnexecuted
        , longestWarpUnexecutedReadings =
            max warpUnexecuted counters.longestWarpUnexecutedReadings
        , cloakUnansweredReadings =
            if answer.cloakAnsweredTheAsk then
                0

            else
                counters.cloakUnansweredReadings + 1
        }


{-| Everything the leaving decides on, as plain readable facts.

A record rather than a `BotDecisionContext`, for #106's reason and more sharply
here than anywhere else in this file: this is the rule that decides whether the
ship stays on a grid somebody else has arrived on, and a rule reachable only
through a decision context is one no case can execute -- so it would be checked
by being read, which is how a rule that resumes work on a reading the bot cannot
see passes for one that works.

`stillOnTheHarvestSite` is read off the overview rather than remembered, which is
`huntAndHarvest`'s own argument turned around: harvestable clouds exist only
inside a gas site, so a reading whose overview carries one is a reading taken on a
site and nothing has to remember having warped.

**`gridIsClean` is the grid as this bot last read it with a ship in space**,
which for every in-space reading is this one and for a docked reading is the one
before the ship went inside. That is not a convenience: a docked client will not
answer a Directional Scan at all, so a docked reading's scan goes stale by the
second, `gridVerdict` answers `CannotTellWhetherTheGridIsClean` -- correctly, and
for a grid the ship is not on -- and a bot judging the undock on it would dock
once and never come out. The reading that is genuinely about the grid outside is
the last one taken from it, which is the reading the dock was commanded from.

`Nothing` -- no reading with a ship UI this session -- reads as **not** clean,
which is #463's own line applied to a session that started docked: this bot
undocks into nothing it has never looked at.

-}
type alias EvasionSituation =
    { gridIsClean : Bool
    , docked : Bool
    , stillOnTheHarvestSite : Bool
    , shipIsWarping : Bool
    , destination : Maybe RetreatDestination
    , cloak : CloakSearch
    , celestialsOnTheOverview : Int
    , celestialRotation : Int
    , counters : EvasionCounters
    }


{-| What the bot does about a grid that does not read clean.

**One rule with the whole ordering in it**, `harvestStep`'s shape and for the
same reason: every stage here can fail to be reachable, and each has to fall
through to the next rather than holding the loop. The order is the issue's -- get
out, cloak, keep scanning, bounce celestials at random ranges -- with two things
in front of it that are not about leaving at all:

  - **a clean grid resumes work**, and it is asked first because it is the exit.
    `gridIsClean` is `gridReadsClean`'s answer, which is `True` for `GridIsClean`
    and for nothing else, so a grid the bot cannot see never ends an evasion.
    That is the line this whole issue rests on;
  - **a docked ship stays docked**, which is #464's ordering requirement and the
    reason this whole rule is asked above the docked-or-in-space split rather
    than inside its in-space arm. A station or structure is the safest place this
    hull can be, so there is nothing here to leave; what there is is an errand
    -- the deposit's undock, and the trip back to the site behind it -- and
    letting that outrank the retreat is what would send a full ship back out into
    somebody else's grid to finish it. Inverting the two compiles.
  - **a ship already in warp is left alone**, because re-commanding a warp that is
    going is how a cascade re-opens on every reading of a manoeuvre already doing
    what it was told. `huntAndHarvest` declines the hunt warp for the same reason.

Then:

  - **still on the site with somewhere to go** warps out, and this is the only
    rung that uses `retreatSearch`. Nowhere to go falls through rather than
    stopping: sitting on a hostile grid because no bookmark is named is worse than
    cloaking on it and worse again than bouncing off it;
  - **a cloak fitted and not running** is switched on, unless it has been asked
    for `cloakGiveUpReadings` readings and answered nothing. A fit with no cloak
    in it, once every module has been identified, falls straight through --
    which is #463's own requirement and the mutation it names. **A fit whose
    modules are not identified yet does not fall through the same way**: run 3
    evaded with `0 of 5` identified and no cloak, and the operator's own
    keybind presses the module by hotkey regardless of which slot a cloak
    turns out to be in, so `ActivateTheCloakByHotkey` presses it speculatively
    -- on the same `cloakGiveUpReadings` clock -- rather than leaving the ship
    uncloaked for however long identification takes. The tooltip answer still
    wins the moment it lands, at which point this reads as one of the other
    two cases;
  - **a celestial on the overview** is warped to, at a range drawn per attempt.
    Which celestial rotates with the reading count, so an evasion that is not
    working tries a different corner of the system;
  - **nothing left** is a grid with no celestial at AU range on the overview, and
    it says so rather than reading as a bot quietly waiting.

-}
type EvasionStep
    = TheGridReadsCleanSoResumeWork
    | StayDockedRatherThanUndockIntoIt
    | WaitForTheEvasionWarpToLand
    | WarpOutOfTheSite RetreatDestination
    | ActivateTheCloak Int
    | ActivateTheCloakByHotkey
    | WarpToACelestial Int
    | NothingLeftToLeaveWith


evasionStep : EvasionSituation -> EvasionStep
evasionStep situation =
    if situation.gridIsClean then
        TheGridReadsCleanSoResumeWork

    else if situation.docked then
        StayDockedRatherThanUndockIntoIt

    else if situation.shipIsWarping then
        WaitForTheEvasionWarpToLand

    else
        case ( situation.stillOnTheHarvestSite, situation.destination ) of
            ( True, Just destination ) ->
                WarpOutOfTheSite destination

            _ ->
                case situation.cloak of
                    TheCloakIsFittedAndNotRunning index ->
                        if situation.counters.cloakUnansweredReadings < cloakGiveUpReadings then
                            ActivateTheCloak index

                        else
                            bounceOffACelestial situation

                    TheModulesAreNotIdentifiedYet _ ->
                        -- Run 3 evaded here with `0 of 5` identified and no
                        -- cloak. The operator's keybind says F3 without any
                        -- discovery, so press it rather than leave uncloaked;
                        -- the tooltip answer above still wins once it lands.
                        if situation.counters.cloakUnansweredReadings < cloakGiveUpReadings then
                            ActivateTheCloakByHotkey

                        else
                            bounceOffACelestial situation

                    _ ->
                        bounceOffACelestial situation


bounceOffACelestial : EvasionSituation -> EvasionStep
bounceOffACelestial situation =
    if situation.celestialsOnTheOverview < 1 then
        NothingLeftToLeaveWith

    else
        WarpToACelestial
            (modBy situation.celestialsOnTheOverview
                (situation.celestialRotation // evasionCelestialStickyReadings)
            )


{-| Somewhere to bounce to: whatever the overview reports at AU range.

`eve-online-mission-runner`'s `escapeCelestialsOnOverview`, ported with its
reasons. Distance in AU means off this grid, which is the only property that
matters when leaving, and it is self-correcting -- arriving turns that entry into
a km-range one that no longer qualifies, so the next warp necessarily picks
somewhere else.

Deliberately **not** "anything whose name contains station", which is what killed
that bot's run 102: an `Angel Asteroid Outpost` carries the object type
`Asteroid Station - 1`, matched as a station, and the bot then waited 119 readings
for a Dock button that site scenery never offers.

Filtered on `_display`, because these rows are right-clicked and a hidden overview
row's region belongs to whatever was recycled into it.

-}
celestialsToBounceOffOnTheOverview : ReadingFromGameClient -> List EveOnline.ParseUserInterface.OverviewWindowEntry
celestialsToBounceOffOnTheOverview readingFromGameClient =
    readingFromGameClient.overviewWindows
        |> List.concatMap .entries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter
            (.objectDistance
                >> Maybe.map (String.toUpper >> String.contains "AU")
                >> Maybe.withDefault False
            )


evasionSituationFromContext : BotDecisionContext -> EvasionSituation
evasionSituationFromContext context =
    { gridIsClean =
        if context.readingFromGameClient.shipUI == Nothing then
            context.memory.lastGridVerdictInSpaceIsClean |> Maybe.withDefault False

        else
            gridReadsClean (gridVerdict (gridEvidenceFromContext context))
    , docked = context.readingFromGameClient.shipUI == Nothing
    , stillOnTheHarvestSite =
        0
            < (cloudSearchFromReading context.eventContext.botSettings
                context.readingFromGameClient
              ).cloudRowsInTheReading
    , shipIsWarping =
        context.readingFromGameClient.shipUI
            |> Maybe.map shipIsWarping
            |> Maybe.withDefault False
    , destination = (retreatSearchFromContext context).destination
    , cloak = cloakSearchFromContext context
    , celestialsOnTheOverview =
        celestialsToBounceOffOnTheOverview context.readingFromGameClient |> List.length
    , celestialRotation = context.memory.readingsCount
    , counters = context.memory.evasion
    }


{-| Command whatever `evasionStep` says is next, or decline so the harvest runs.

`Nothing` for the one answer that is not about leaving, which is the shape
`refreshTheDirectionalScanner` and every entry in `generalSetupInUserInterface`
has: a clean grid falls straight through to the work rather than being wrapped in
a branch announcing that the bot is not leaving.

Nothing is decided here. This is the mapping from an answer onto the effects that
carry it out, kept apart from the rule so that the ordering can be executed
without a client and the effects read without one.

-}
actOnTheEvasionStep : BotDecisionContext -> EvasionSituation -> Maybe DecisionPathNode
actOnTheEvasionStep context situation =
    case evasionStep situation of
        TheGridReadsCleanSoResumeWork ->
            Nothing

        StayDockedRatherThanUndockIntoIt ->
            Just
                (describeBranch
                    "The grid this ship would undock into did not read clean the last time anything looked at it from space, and a docked hull is the safest place there is -- stay put. Nothing here undocks a full ship to finish an errand (#464), and a docked client will not answer a Directional Scan, so this is the grid as it was read on the way in rather than a scan going stale inside a structure."
                    waitForProgressInGame
                )

        WaitForTheEvasionWarpToLand ->
            Just
                (describeBranch
                    "Leaving, and the ship is in warp -- wait for it to land rather than re-commanding a warp that is already going."
                    waitForProgressInGame
                )

        WarpOutOfTheSite destination ->
            Just (warpToTheRetreatDestination context destination)

        ActivateTheCloak index ->
            case fittedModulesFromContext context |> List.drop index |> List.head of
                Just ( moduleButton, _ ) ->
                    Just
                        (describeBranch
                            ("Cloak up -- module slot "
                                ++ String.fromInt (index + 1)
                                ++ " reads as a '"
                                ++ cloakingDeviceTooltipMarker
                                ++ "' and is not cycling ("
                                ++ String.fromInt situation.counters.cloakUnansweredReadings
                                ++ "/"
                                ++ String.fromInt cloakGiveUpReadings
                                ++ " readings it has been asked for and not answered)."
                            )
                            (EveOnline.BotFrameworkSeparatingMemory.clickModuleButtonButWaitIfClickedInPreviousStep
                                context
                                moduleButton
                            )
                        )

                Nothing ->
                    -- Unreachable: the index came from the same list on the same
                    -- reading. Says so rather than pretending, because a silent
                    -- wait here would be a branch reporting nothing and doing
                    -- nothing.
                    Just
                        (describeBranch
                            "The module row changed between reading it and pressing the cloak -- ask again next reading."
                            waitForProgressInGame
                        )

        ActivateTheCloakByHotkey ->
            Just
                (describeBranch
                    ("Cloak up with its own hotkey (F3) -- no module here has been identified by tooltip yet, and an evasion is exactly when there is no quiet reading to spend on a hover ("
                        ++ String.fromInt situation.counters.cloakUnansweredReadings
                        ++ "/"
                        ++ String.fromInt cloakGiveUpReadings
                        ++ " readings it has been asked for and not answered)."
                    )
                    (decideActionForCurrentStep (hotkeyEffects cloakHotkey))
                )

        WarpToACelestial index ->
            case celestialsToBounceOffOnTheOverview context.readingFromGameClient |> List.drop index |> List.head of
                Just celestial ->
                    Just (warpToACelestialAtARandomRange context celestial)

                Nothing ->
                    Just
                        (describeBranch
                            "The overview changed between choosing a celestial and warping to it -- ask again next reading."
                            waitForProgressInGame
                        )

        NothingLeftToLeaveWith ->
            Just
                (describeBranch
                    ("NOWHERE TO GO: the grid does not read clean, there is no retreat destination in this reading and nothing at AU range on the overview to bounce off. This hull has no guns and no tank worth the name, so there is nothing left to try. "
                        ++ askForHelpToGetUnstuckText
                    )
                    waitForProgressInGame
                )


{-| Warp out of the site, to whichever rung `retreatSearch` answered.

**One cascade for all three rungs**, because the difference between them is which
node is right-clicked and which distance is taken and nothing else --
`warpToTheHuntedSite`'s argument, which is why both of them build their menu with
`warpCascadeWithin` rather than spelling the two levels out.

`askForHelpToGetUnstuckText` rides on the description once the warp has been
commanded for `warpNotExecutingAlarmReadings` readings with the ship never in
warp, and **the branch still commands the warp**. See `describeWarpNotExecuting`
for why that sentence is carried rather than branched to.

-}
warpToTheRetreatDestination : BotDecisionContext -> RetreatDestination -> DecisionPathNode
warpToTheRetreatDestination context destination =
    let
        stillNotWarping =
            if warpNotExecutingAlarmReadings <= context.memory.evasion.warpUnexecutedReadings then
                " " ++ describeWarpNotExecuting context.memory.evasion.warpUnexecutedReadings

            else
                ""

        leave what target menuDistance =
            describeBranch
                ("Get out -- warp to " ++ what ++ " at " ++ menuDistance ++ "." ++ stillNotWarping)
                (useContextMenuCascade target (warpCascadeWithin menuDistance) context)
    in
    case destination of
        ToAPrefixedBookmark bookmark ->
            leave
                ("the bookmark '"
                    ++ bookmarkLabel bookmark.mainText
                    ++ "', which carries '"
                    ++ context.eventContext.botSettings.retreatBookmarkPrefix
                    ++ "'"
                )
                ( bookmark.mainText, bookmark.uiNode )
                warpAtZeroMenuEntry

        ToTheHomeStructure entry ->
            leave
                ("the home structure '"
                    ++ (entry.objectName |> Maybe.withDefault "")
                    ++ "' on the overview, no bookmark carrying '"
                    ++ context.eventContext.botSettings.retreatBookmarkPrefix
                    ++ "' being in the Locations window"
                )
                ( entry.objectName |> Maybe.withDefault "the home structure", entry.uiNode )
                warpAtZeroMenuEntry

        ToAnyBookmarkAtAll bookmark ->
            leave
                ("'"
                    ++ bookmarkLabel bookmark.mainText
                    ++ "', which is simply the first bookmark there is"
                )
                ( bookmark.mainText, bookmark.uiNode )
                warpAt100KmMenuEntry


{-| Bounce to a celestial, at a range drawn fresh for this attempt.

**Randomising the range is the point rather than a flourish**, which is #463's
own emphasis: a bot that always lands at the same spot on the same celestial is
trivially caught, and the client's own distance submenu is a ready-made set of
seven ranges to draw from.

The draw is from `randomIntegers`, the host's own supply, and it is made per
reading rather than held. That is safe because only one reading of the cascade
ever clicks a distance -- the earlier ones right-click the row and open the
submenu -- so a fresh draw cannot change a choice that has already been acted on.
`useRandomMenuEntry` is deliberately not used: it picks from every entry in the
menu, and one of the entries in this one is `Set Default`.

-}
warpToACelestialAtARandomRange : BotDecisionContext -> EveOnline.ParseUserInterface.OverviewWindowEntry -> DecisionPathNode
warpToACelestialAtARandomRange context celestial =
    let
        distance =
            warpDistanceMenuEntries
                |> Common.Basics.listElementAtWrappedIndex
                    (context.randomIntegers |> List.head |> Maybe.withDefault 0)
                |> Maybe.withDefault warpAt100KmMenuEntry

        name =
            celestial.objectName |> Maybe.withDefault "a celestial"
    in
    describeBranch
        ("Stay gone -- the grid still does not read clean, so bounce to '"
            ++ name
            ++ "' at "
            ++ distance
            ++ " (drawn for this attempt; a fixed range is a fixed landing spot)."
        )
        (useContextMenuCascade ( name, celestial.uiNode ) (warpCascadeWithin distance) context)


{-| What an operator reads about the leaving, on every reading.

Printed whether or not anything is on the grid, because the numbers it carries
are the ones an operator watches **climb**: a retreat approaching the alarm and
one that is merely slow read identically unless the bound is shown beside the
count. That is `describeRetreatLatencyFromProgress`'s own finding -- a first
version of that clause read the sentence out of the source instead, and a
mutation that dropped the bound from the count while leaving it in the sentence
survived it.

-}
describeEvasion : EvasionCounters -> String
describeEvasion counters =
    if counters.readings < 1 then
        "Evasion: not evading."
            ++ (if counters.longestWarpUnexecutedReadings < 1 then
                    ""

                else
                    " Worst this session: "
                        ++ String.fromInt counters.longestWarpUnexecutedReadings
                        ++ " consecutive readings deciding to leave with the ship not in warp."
               )

    else
        "Evasion: "
            ++ String.fromInt counters.readings
            ++ "/"
            ++ String.fromInt evasionGiveUpReadings
            ++ " readings the grid has not read clean, and the session ends at that bound with the ship wherever the last warp put it. "
            ++ (if counters.warpUnexecutedReadings < 1 then
                    "The ship is in warp."

                else
                    String.fromInt counters.warpUnexecutedReadings
                        ++ "/"
                        ++ String.fromInt warpNotExecutingAlarmReadings
                        ++ " consecutive readings deciding to leave with the ship not in warp"
                        ++ (if warpNotExecutingAlarmReadings <= counters.warpUnexecutedReadings then
                                " -- past the bound, and a person has been asked for."

                            else
                                "."
                           )
               )



-- Depositing the hold at the home structure


{-| The inventory sidebar row the hold this bot fills is drawn as.

**A Mining Hold on the measured hull rather than a generic cargo hold**, which
is #464's own first emphasis and the thing a plausible implementation gets
wrong. `readingFromGameClient.inventoryWindows` is a list, and each window's
`selectedContainerCapacityGauge` belongs to whichever container **that** window
has selected -- so a rule taking the first gauge it finds reads whatever the
client happened to draw first (a cargo hold, a wreck somebody opened, a
structure's hangar) and then deposits, or declines to, on the strength of a
number about some other container.

Matched as a substring and ignoring case, because the client's own longer
spellings of this row carry it (`General Mining Hold` is one) and because a
sidebar row is a phrase rather than a word.

-}
miningHoldTreeEntryText : String
miningHoldTreeEntryText =
    "mining hold"


{-| The node type the client draws the Mining Hold as while it is selected.

The sidebar row above is what a click aims at; this is what says the capacity
gauge in a window is **the hold's**. Both are needed and they answer different
questions -- a window lists the hold in its sidebar while showing the
structure's hangar on the right, which is exactly the state the drag happens in,
and only the second of those two facts may be read as a fill level.

Taken from the vendored parser rather than from a live client:
`parseInventoryWindow` recognises `ShipCargo`, `ShipDroneBay`,
`ShipGeneralMiningHold`, `StationItems`, `ShipFleetHangar` and
`StructureItemHangar`, and this is the only one of the six that is a mining
hold. **Nobody has read this hull's own type name**, so a build that spells it
differently makes every reading answer `HoldFillCannotBeRead`, no deposit is
ever decided, and the status line says so on every reading -- which is the
direction this is built to fail in rather than an accident of it.

-}
miningHoldContainerTypeName : String
miningHoldContainerTypeName =
    "ShipGeneralMiningHold"


{-| Why this ship no longer docks to deposit, and why the docked sequence is
still here.

#464 shipped a deposit that docks, and wrote down that the cheaper path had been
looked for and was not in the evidence. **Two of the four things it recorded have
since stopped being true**, which is the mechanism working rather than failing:

  - `selectedItemAccessDropbox` was _"a button nothing here has ever pressed"_.
    It has been pressed, on 2026-09-09 with a structure selected in space, and
    what it opens is `DropboxWnd` -- see `dropboxWindowTypeName` for the window
    and its parts. On 2026-09-10 the whole sequence was driven by hand on a
    loaded hold: select the structure, press the button, drag each stack onto
    `inputInfo`, press `transferBtn`. The client answered with
    `(notify) 2 items were moved to your hangar in <structure>`, the Mining
    Hold's gauge went to zero and the window reset.
  - _"the repository's only in-space unload requires an Orca or a Rorqual in
    fleet"_ was true of `eve-online-mining-bot` and is no longer true of the
    repository. It stays true of that bot, which is what the case now asserts.

**The two that still hold are the reason the docked path is kept.**
`parseInventoryWindow` still recognises exactly one structure container across
all eight vendored copies, and no reading here has ever carried it from an
undocked ship -- so the in-space transfer is not an inventory operation at all
and shares none of that machinery. And `eve-online-mining-bot` still docks.

**This removes the dock and not the trip.** The button is on the Selected Item
panel, so the structure has to be selected, so the ship has to be on its grid --
confirmed by the button's absence at a gas site in another system with a loaded
hold. What is removed is `DockingRunIn`, the lobby, the hangar and the undock.

**And #464's sequence is the fallback rather than dead code**, which #476 is
explicit about: a structure that offers no dropbox, a ship not yet close enough,
or a window this bot cannot read all fall through to `PressTheDockButton` and
the docked drag behind it. See `depositStep` for where each of those falls.


## The row itself

Matched by the sidebar row's text rather than by the `StructureItemHangar` node
type, because the drop target is a row to click and the type name only ever
appears on a container the window has already **selected** -- and the whole
point of the drag is that the hold is selected and the hangar is not.

Absent from every reading taken in space, which is what makes it a `Maybe` at
the call site rather than something to assert: an undocked ship has no
structure's hangar in its inventory, and a docked one that does not either is a
reading that says so in the decision log rather than a drag aimed at nothing.

-}
structureHangarTreeEntryText : String
structureHangarTreeEntryText =
    "item hangar"


{-| What the hold's own capacity gauge says, in the three forms it was measured
in plus the one every other reading gives.

`InvContCapacityGauge`, read on the hull #456 was measured on:

    0/12,500.0 m3                       empty
    12,500.0/12,500.0 m3                full
    (12,500.0) 12,500.0/12,500.0 m3     full, with a transfer in flight

**The parenthesised form is a transient and is its own answer**, which is
#464's second emphasis and the clause most easily lost.
`parseInventoryCapacityGaugeText` puts the bracketed number in `selected` and
the pair either side of the slash in `used` and `maximum`, so a rule looking
only at those two reads the transient as _full_ -- which is true of the reading,
is a fill level, and is precisely the wrong thing to act on, because a transfer
already in flight would then be answered by dragging again. It is therefore
asked **before** the used-against-maximum comparison, so that no ordering of the
remaining clauses can let it through as a level.

**`HoldFillCannotBeRead` is never read as full.** It is the ordinary answer on a
reading whose inventory has something else selected, and the fail direction is
chosen rather than inherited: an unreadable hold means this bot never decides to
deposit, which is exactly the behaviour it had before #464 and which the status
line shouts on every reading, where the other direction would fly the ship home
on every session whose inventory nobody set up.

`maximum <= used` is the honest limit rather than a full test, the same one
`droneBayFillFromCapacityGauge` states next door: the gauge is cubic metres
truncated to an integer and a gas cycle's own volume is not readable, so a hold
with 1 m3 free reads as having room while the next cycle will not fit. What
covers that is the harvester and the operator, not this.

-}
type HoldFill
    = HoldIsFull
    | HoldHasRoom
    | HoldTransferIsInFlight
    | HoldFillCannotBeRead


holdFillFromCapacityGauge :
    Maybe EveOnline.ParseUserInterface.InventoryWindowCapacityGauge
    -> HoldFill
holdFillFromCapacityGauge capacityGauge =
    case capacityGauge of
        Nothing ->
            HoldFillCannotBeRead

        Just gauge ->
            if gauge.selected /= Nothing then
                HoldTransferIsInFlight

            else
                case gauge.maximum of
                    Nothing ->
                        HoldFillCannotBeRead

                    Just maximum ->
                        if maximum <= gauge.used then
                            HoldIsFull

                        else
                            HoldHasRoom


selectedContainerTypeNameOfWindow : EveOnline.ParseUserInterface.InventoryWindow -> Maybe String
selectedContainerTypeNameOfWindow inventoryWindow =
    inventoryWindow.selectedContainerInventory
        |> Maybe.map (.uiNode >> .uiNode >> .pythonObjectTypeName)


holdIsTheSelectedContainer : EveOnline.ParseUserInterface.InventoryWindow -> Bool
holdIsTheSelectedContainer inventoryWindow =
    selectedContainerTypeNameOfWindow inventoryWindow
        == Just miningHoldContainerTypeName


{-| The hold's fill as this reading has it, or `HoldFillCannotBeRead`.

The gauge is asked of the window that has the **hold** selected and of no other,
which is `miningHoldContainerTypeName`'s whole reason. A reading where the
deposit has selected the structure's hangar to drag into therefore says nothing
about the hold, which is correct: the number on screen then belongs to the
hangar.

-}
holdFillFromReading : ReadingFromGameClient -> HoldFill
holdFillFromReading readingFromGameClient =
    case
        readingFromGameClient.inventoryWindows
            |> List.filter holdIsTheSelectedContainer
            |> List.head
    of
        Nothing ->
            HoldFillCannotBeRead

        Just inventoryWindow ->
            holdFillFromCapacityGauge
                (inventoryWindow.selectedContainerCapacityGauge
                    |> Maybe.andThen Result.toMaybe
                )


{-| A row in an inventory window's sidebar, found anywhere in that tree.

`eve-online-mission-runner`'s, ported with its reason: the ship's own holds hang
off the ship's entry rather than sitting beside it, so a search over the roots
alone finds neither the Mining Hold nor a docked structure's hangar.

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


{-| The items an inventory window is currently rendering, in either view.

Only the rendered ones: the list is virtualised, so a count from here is a
signal that there is something to drag and never a total of what is in the hold.

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


{-| The one inventory window this whole sequence works in, with the two rows it
clicks carried back beside it.

Picked by the window's **sidebar listing the Mining Hold**, rather than by
taking `List.head` of the windows, for `miningHoldTreeEntryText`'s reason. The
hangar row is a `Maybe` because it exists only while docked, and finding both
here is what makes the drag's source and target present by construction rather
than re-derived at the point of the drag, where a "nothing to drop it into"
branch would be unreachable and would read like a guard.

-}
type alias DepositInventory =
    { window : EveOnline.ParseUserInterface.InventoryWindow
    , holdTreeEntry : EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    , structureHangarTreeEntry : Maybe EveOnline.ParseUserInterface.InventoryWindowLeftTreeEntry
    }


depositInventoryFromReading : ReadingFromGameClient -> Maybe DepositInventory
depositInventoryFromReading readingFromGameClient =
    readingFromGameClient.inventoryWindows
        |> List.filterMap
            (\inventoryWindow ->
                inventoryWindow
                    |> inventoryTreeEntryWithText miningHoldTreeEntryText
                    |> Maybe.map
                        (\holdTreeEntry ->
                            { window = inventoryWindow
                            , holdTreeEntry = holdTreeEntry
                            , structureHangarTreeEntry =
                                inventoryWindow
                                    |> inventoryTreeEntryWithText structureHangarTreeEntryText
                            }
                        )
            )
        |> List.head


{-| The two substrings that make a `(notify)` line this bot's own deposit
confirmation.

**The client writes this sentence two ways, and #464's markers only read one of
them.** #456 recorded

    (notify) N item(s) was moved to your hangar in <system> - <structure>

and the live in-space transfer of 2026-09-10 produced

    (notify) 2 items were moved to your hangar in <structure>

-- plural verb, no system, and **no match** for `item(s) was moved`. So the
markers are widened to what both carry: `item`, and `moved to your hangar`. That
still declines the near miss two paragraphs down, which is a sentence about a
hangar carrying no item at all, and it is what the cases are asked about.

**The client's own line and not the gauge**, which is #464's third emphasis and
the one that costs the most to get wrong. A gauge reading zero because the drag
silently moved nothing and a gauge reading zero because the deposit worked are
the same reading -- the distinction #19 cost the standalone restock tool, and
the one `reload_drones.py` and the mission runner's `restockDroneBayWhileDocked`
each had to learn afterwards. So the gauge says **when to start** and the client
says **when it is done**, and neither is allowed to answer the other's question.

Two substrings rather than the whole sentence, `loadRefusalFromGameLog`'s shape
and for its reasons. The count, the system and the structure's name all sit
inside the line, so a whole-line match would be per-structure and would stop
matching the day an operator deposits somewhere else; and one substring is not
enough, because `to your hangar` alone takes any sentence about a hangar this
client ever writes.

The verdict is carried into `BotMemory` by `depositRunAfterReading`, because a
reading's game-log entries are gone by the next reading: a branch recognising
this where it acts on it would see the confirmation once and go straight back to
dragging.

-}
depositConfirmationMarkers : List String
depositConfirmationMarkers =
    [ "item", "moved to your hangar" ]


depositConfirmedInGameLog : ReadingFromGameClient -> Maybe String
depositConfirmedInGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                depositConfirmationMarkers
                    |> List.all (\marker -> stringContainsIgnoringCase marker entry.text)
            )
        |> List.head
        |> Maybe.map .text


{-| The client saying it has begun flying the ship to a docking perimeter, in
its own words.

    [ ... ] (notify) Setting course to docking perimeter

One constant rather than a literal at the match site, because the status line
and the waiting branch both quote it: a matcher that drifts from what the client
writes fails in the direction that looks like success -- nothing matches, the
latch never arms, and the bot goes back to re-commanding a dock with nothing
complaining.

-}
courseSetToDockingPerimeterMarker : String
courseSetToDockingPerimeterMarker =
    "Setting course to docking perimeter"


courseSetToDockingPerimeterFromGameLog : ReadingFromGameClient -> Maybe String
courseSetToDockingPerimeterFromGameLog readingFromGameClient =
    readingFromGameClient.gameLogEntriesSinceLastReading
        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\entry ->
                stringContainsIgnoringCase courseSetToDockingPerimeterMarker entry.text
            )
        |> List.head
        |> Maybe.map .text


{-| A docking run-in the client has confirmed it is flying, and the evidence
that it is still making progress.

**Ported from `eve-online-mission-runner`'s `DockingRunIn`, which #464 names by
name.** Docking is not a command that completes when it is issued: the client
answers a Dock by flying the ship to the structure's docking perimeter, and
during that run-in the ship looks, to every other instrument in a reading,
exactly like a ship that has been told nothing. That bot's run 27 is what it
costs -- the dock was commanded on 120 of the 121 readings between two accepted
course-settings, those two are **486 seconds** apart, which is the run-in's own
length, and a ship that had precisely enough time to arrive sat 17 km off a
station for eight minutes. **Commanding it again restarts it.**

The sentence is the only evidence a reading carries that a dock is under way.
`ShipManeuverType` has no docking member -- the parser knows Warp, Jump, Orbit,
Approach, Range and Align, and none of them is this -- the ship keeps its
ordinary UI, and the structure's overview row looks like any other. So the latch
is written in `updateMemoryForNewReadingFromGame`, for the reason every
game-log verdict here is: a reading's entries are gone by the next reading.

**What ends the wait is not a clock.** Eight minutes is hundreds of readings, an
order of magnitude past every settling window in this file, and a run-in's
length is set by a distance nobody chose. What bounds it instead is the run-in
_working_: `rangeToTheStructureMeters` holds the smallest range seen since the
course was set, and `readingsSinceCloser` counts how long it has been since that
fell. A ship that is closing gets as long as the distance requires; a ship that
has stopped closing gets `dockingRunInPatienceReadings` and then the command
again. That is `stall_watch.py`'s own question, unit and value, so the bot and
the watchdog watching it cannot disagree about what a stalled approach looks
like.

`dockCommands` is read by nothing that decides anything. It is the number this
whole guard is about, carried into the status line so a run says outright how
many times it restarted its own dock: a working one shows 1.

-}
type alias DockingRunIn =
    { rangeToTheStructureMeters : Maybe Int
    , readingsSinceCloser : Int
    , dockCommands : Int
    }


{-| How many readings a confirmed run-in may go without getting closer before
the bot commands the dock again.

**Not a budget for the run-in; a budget for the run-in showing nothing**, which
is the whole of the distinction. A clock would have to be picked against the
longest dock anybody might fly and there is no such number. So the run-in is
allowed as long as the range keeps falling, and this bounds only the case where
it has stopped: a command that was swallowed, a ship stopped by something, a
structure that left the overview.

Twenty readings, the same unit and the same value as `stall_watch.py`'s
`APPROACH_PATIENCE`, which was calibrated for exactly this question on exactly
this signal. Reusing its number rather than inventing one is what keeps the two
from disagreeing.

What it costs when it is wrong is stated rather than hidden, and it is wrong in
the permissive direction: a run-in this bot cannot measure gets one re-command
every twenty readings rather than one per reading.

-}
dockingRunInPatienceReadings : Int
dockingRunInPatienceReadings =
    20


{-| The docking run-in as it stands after this reading.

**Docked ends it.** The run-in finished, whatever it was doing, and a latch that
survived into the next undock would suppress the first Dock of the next trip.

**A fresh course-setting restarts it** rather than being ignored as already
latched: the client writes the line each time it accepts a Dock, so a second one
means a second run-in from wherever the ship now is, and the range to beat is
this reading's rather than the old one's. That also picks up a dock an operator
commanded by hand, which is the same run-in and equally not to be interrupted.

**Otherwise it is the falling-range test**, and an unreadable range counts as no
gain rather than as a reason to drop the latch -- see
`rangeToTheHomeStructureInMeters` for the three ways it can be `Nothing`, none
of which is evidence the ship is closing. The `( Just _, Nothing )` case is a
gain, because the reading now has something to measure against and the patience
should start from it rather than from a count already part-spent.

-}
dockingRunInAfterReading :
    { before : Maybe DockingRunIn
    , courseSetThisReading : Bool
    , rangeNow : Maybe Int
    , docked : Bool
    }
    -> Maybe DockingRunIn
dockingRunInAfterReading { before, courseSetThisReading, rangeNow, docked } =
    if docked then
        Nothing

    else if courseSetThisReading then
        Just
            { rangeToTheStructureMeters = rangeNow
            , readingsSinceCloser = 0
            , dockCommands = (before |> Maybe.map .dockCommands |> Maybe.withDefault 0) + 1
            }

    else
        before
            |> Maybe.andThen
                (\runIn ->
                    let
                        gotCloser =
                            case ( rangeNow, runIn.rangeToTheStructureMeters ) of
                                ( Just now, Just nearestSoFar ) ->
                                    now < nearestSoFar

                                ( Just _, Nothing ) ->
                                    True

                                _ ->
                                    False
                    in
                    if gotCloser then
                        Just
                            { runIn
                                | rangeToTheStructureMeters = rangeNow
                                , readingsSinceCloser = 0
                            }

                    else if runIn.readingsSinceCloser + 1 < dockingRunInPatienceReadings then
                        Just { runIn | readingsSinceCloser = runIn.readingsSinceCloser + 1 }

                    else
                        Nothing
                )


{-| What the bot says on every reading it declines to command the dock again.

Said every time rather than once, for the reason every declining branch in this
file says so every time: a stretch of readings where nothing happens is
otherwise indistinguishable from a bot that has fallen through to something
else. The range is what makes those readings distinguishable from each other,
which matters because `stall_watch.py` keys its circling test on the decision
text changing and would otherwise raise an alarm on a ship flying its run-in
perfectly.

-}
describeDockingRunIn : DockingRunIn -> String
describeDockingRunIn runIn =
    "The client is already flying this dock -- '"
        ++ courseSetToDockingPerimeterMarker
        ++ "' stands, at "
        ++ (runIn.rangeToTheStructureMeters
                |> Maybe.map (\meters -> String.fromInt meters ++ " m")
                |> Maybe.withDefault "a range this reading cannot say"
           )
        ++ ", "
        ++ String.fromInt runIn.readingsSinceCloser
        ++ " of "
        ++ String.fromInt dockingRunInPatienceReadings
        ++ " readings since it last got closer. Commanding it again would restart the run-in."


{-| How far the home structure is, where this reading can say.

`Nothing` covers a structure that is not on the overview, a row that is not
rendered, and a distance the parser could not read -- which includes an AU
distance, since `parseOverviewEntryDistanceInMetersFromText` answers `Err` for
one rather than a number that would read as merely far. None of the three is
evidence the ship is closing, so the run-in counts all of them as no gain, and
the worst that degrades to is one Dock per patience window.

The **smallest** of the matching rows, because a `home-structure-name` ending in
`*` can match more than one and the nearest is the one a dock would land at.

-}
rangeToTheHomeStructureInMeters : Maybe String -> ReadingFromGameClient -> Maybe Int
rangeToTheHomeStructureInMeters homeStructureName readingFromGameClient =
    homeStructureRowsOnTheOverview homeStructureName
        (readingFromGameClient.overviewWindows |> List.concatMap .entries)
        |> List.filterMap (.objectDistanceInMeters >> Result.toMaybe)
        |> List.minimum


{-| The Selected Item panel's Dock button, by both identifiers the client
carries for it.

`selectedItemOrbitButton`'s shape and for its reasons -- found by name in the
reading it is pressed in and never by position, and matched on either the node's
own id or the `cmdName` beside it so that a rename of one does not silently
stop the deposit. #456 read `selectedItemDock` off a live structure's panel;
`CmdDockAtItem` is the client's own command name for the same button and is the
insurance rather than the evidence.

-}
selectedItemDockButton : { elementId : String, cmdName : String }
selectedItemDockButton =
    { elementId = "selectedItemDock", cmdName = "CmdDockAtItem" }


{-| Whether the previous step pressed a mouse button at all.

The drag and the dialog's OK both need it. A repeat drag is not harmless -- it
can move part of a stack somewhere unintended while the first is still catching
up -- and a repeat OK is a second answer to a dialog that may already be gone,
which lands wherever the client has drawn something else. `pressModuleHotkey`
is the same guard for the keyboard; this is the mouse half of it.

Read from the effects the bot dispatched rather than from anything the client
says, because what was asked for is knowable where what the client did with it
is not.

-}
previousStepDispatchedAMouseButton : BotDecisionContext -> Bool
previousStepDispatchedAMouseButton context =
    context.previousStepsEffects
        |> List.head
        |> Maybe.withDefault []
        |> List.any
            (\effect ->
                case effect of
                    EffectOnWindow.ButtonDown _ ->
                        True

                    _ ->
                        False
            )


{-| Whether a dispatched step was a drag rather than a click.

**A move made while a button is held**, which is the one thing that separates
the two: `effectsForDragAndDrop` presses, moves and releases, and
`effectsMouseClickAtLocation` presses and releases without moving. Nothing else
in this app holds a button over a move, so the shape names the gesture and no
memory of what the branch decided is needed -- which matters because
`updateMemoryForNewReadingFromGame` is the only place that can write memory and
the one place that never sees a decision.

Counted rather than acted on: `DepositRun.drags` is what separates _the drag has
not gone out yet_ from _it went out and the client has said nothing_, which is
the pair an operator watching a deposit that is not finishing has to tell apart.

-}
stepDraggedSomething : List EffectOnWindow.EffectOnWindowStruct -> Bool
stepDraggedSomething effects =
    effects
        |> List.foldl
            (\effect ( holding, dragged ) ->
                case effect of
                    EffectOnWindow.ButtonDown _ ->
                        ( True, dragged )

                    EffectOnWindow.ButtonUp _ ->
                        ( False, dragged )

                    EffectOnWindow.MouseMoveTo _ ->
                        ( holding, dragged || holding )

                    _ ->
                        ( holding, dragged )
            )
            ( False, False )
        |> Tuple.second


{-| The one OK button on screen, whichever dialog it belongs to.

Not a `MessageBox`, so `closeMessageBox` never reaches it, and it carries no
name of its own either -- which leaves its label. `reload_drones.py` finds it
the same way.

**It cannot tell one dialog from another, and this file does not pretend it
can.** The confirmation a successful drag raises and the client's refusal of one
are both single-OK-button windows, which is the caveat #464 quotes from
`restockDroneBayWhileDocked`: clicking whichever OK is on screen and calling it
success reports a transfer that moved nothing. So the OK is clicked -- something
has to be, or the dialog sits over the client for the rest of the session -- and
**the click is never evidence of anything**. What says the transfer landed is
`depositConfirmedInGameLog` and nothing else.

Widest rather than first, so the click lands on the clickable box around the
label rather than on a nested fragment of it, and matched on the node's own
first visible text so that a window merely containing an OK somewhere below it
is not itself the button.

-}
okButtonInReading : ReadingFromGameClient -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
okButtonInReading readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (firstVisibleTextOfNode >> Maybe.map labelReadsOk >> Maybe.withDefault False)
        |> List.sortBy (.totalDisplayRegionVisible >> .width >> negate)
        |> List.head


firstVisibleTextOfNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Maybe String
firstVisibleTextOfNode node =
    node.uiNode
        |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
        |> List.map String.trim
        |> List.filter (String.isEmpty >> not)
        |> List.head


{-| Whether a label is the client's own `OK`, decorated or not.

Equality rather than a substring, because `OK` is a substring of a great many
sentences a dialog can carry, and the `>ok<` form because the client wraps a
button's label in its own tags -- which is the same pair `parseStationWindow`'s
`buttonFromDisplayText` matches on for the Undock button.

-}
labelReadsOk : String -> Bool
labelReadsOk text =
    let
        lowered =
            text |> String.toLower |> String.trim
    in
    (lowered == "ok") || String.contains ">ok<" lowered


{-| Drag an inventory item onto a sidebar row, taking hold of the item's icon.

`effectsForDragAndDrop` starts wherever it is told, and in the icon view the
centre of an `InvItem` box is where the icon meets the label under it --
`reload_drones.py` had to aim 25 px below the top of the box to get the icon,
and `dragFromItemIconOntoUiElement` in `eve-online-mission-runner` carries the
same offset. It is clamped to half the height so that a list-view row, which is
shorter than that, is still grabbed inside itself.

The host skips its own interleaved waits while a button is held -- otherwise EVE
reads a press followed by a pause as a click and the later motion as the cursor
wandering off -- so the waypoint in the middle is what makes this a drag rather
than a teleport.

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


{-| The node type of the window `selectedItemAccessDropbox` opens.

Read off a live client on 2026-09-09 with a structure selected in space, as a
diff against the whole tree taken before the press -- so the window being _new_
is established rather than assumed. It is captioned `Upwell Cargo Deposit` and
names its own destination.

-}
dropboxWindowTypeName : String
dropboxWindowTypeName =
    "DropboxWnd"


{-| The node type of the box a stack is dragged onto, inside the window.
-}
dropboxDropTargetTypeName : String
dropboxDropTargetTypeName =
    "TransferInputContainer"


{-| The container inside the drop target that holds what has been staged.

**This is what says how much is staged, and `numItemsLabel` is not** -- see
`dropboxItemCountLabelName`.

-}
dropboxStagedItemsContainerName : String
dropboxStagedItemsContainerName =
    "inputScroll"


{-| The button that commits the transfer.
-}
dropboxTransferButtonName : String
dropboxTransferButtonName =
    "transferBtn"


{-| The label naming the structure the transfer would go to, as
`Structure to transfer to:<structure>`.

Read before anything is committed, which is the whole reason this window is
better evidence than the docked flow's: the destination is stated on screen
rather than inferred from having clicked the right row.

-}
dropboxDestinationLabelName : String
dropboxDestinationLabelName =
    "transferToLabel"


{-| The label reading `N Items`, which is **not** a staged count.

Measured live on 2026-09-10 with a loaded hold: with the window open and nothing
dragged in it read `2 Items`, the hold's own two stacks, and after one stack was
staged it read `1 Item`. So it counts _down_ as staging succeeds, which is
exactly backwards from the obvious reading -- a rule taking it for "how much is
staged" concludes a successful drag failed.

It is printed in the status line and **nothing decides on it**. What decides is
`dropboxStagedItemsContainerName`'s own contents and the transfer button's
enabled state, which are two independent readings of the same fact.

-}
dropboxItemCountLabelName : String
dropboxItemCountLabelName =
    "numItemsLabel"


{-| The text the transfer button carries **only while it is disabled**.

Measured live: disabled the button carries two texts, `Nothing to transfer` and
`Transfer`; enabled it carries only `Transfer`. So the client states whether
pressing will do anything, and this bot reads that rather than pressing
hopefully.

-}
dropboxNothingToTransferMarker : String
dropboxNothingToTransferMarker =
    "Nothing to transfer"


{-| The client's own key for the range at which this window will transfer.

Read off `DropboxWnd` as `validRange: 10000.0`, and decoded as a **float**.
`getIntPropertyFromDictEntries` happens to answer this particular value too --
JSON has one number type and `10000.0` is integral, so `Json.Decode.int` takes
it -- so the two agree here and the choice is about the values nobody has read
yet. A structure stating a fractional range answers `Nothing` under `int`, and
`Nothing` from this field prints as `unreadable` beside a number the operator is
trying to check `dropboxTransferRangeMeters` against, which is the direction that
wastes a run.

**Nothing decides on it**: it is carried into the status line so that the first
run says whether `dropboxTransferRangeMeters` is the number this structure
states. The bot's own gate is the constant, deliberately, because the window has
to be open before this can be read at all.

-}
dropboxValidRangeKey : String
dropboxValidRangeKey =
    "validRange"


{-| How close the ship has to be before this bot will open the dropbox at all.

`10000` is the `validRange` the one structure that has been read stated for
itself, and **it is this bot's own gate rather than the client's**: the button
was pressed successfully at roughly 90 km in one recorded attempt, so the panel
offering it is not evidence the transfer would land. Rather than open a window
at a range whose transfer nobody has watched, the ship closes first -- which the
deposit was going to do anyway, since `PressTheDockButton` and
`WarpToTheHomeStructure` are what a reading outside this range falls through to.

**The range at which the panel stops offering the button is unmeasured**, and
this gate is deliberately tighter than any plausible answer to it, so that
question does not decide anything. A range the reading cannot say -- no row, a
virtualised row, an AU distance -- is not within range, so the bot falls back to
docking rather than opening a window it cannot place.

-}
dropboxTransferRangeMeters : Int
dropboxTransferRangeMeters =
    10000


{-| The Selected Item panel's Access Dropbox button, by the one identifier that
has ever been read for it.

`selectedItemDockButton` and `selectedItemOrbitButton` each carry two -- the
node's own id and the `cmdName` beside it -- so a rename of one does not stop
the branch. **No `cmdName` has ever been read for this button**, so there is no
second identifier here and the `cmdName` slot is filled with the same string the
elementId carries, which no node in the client answers to. That is stated rather
than dressed up as insurance: the match rests on `selectedItemAccessDropbox`
alone, and a client that renames it makes this branch fall through to the docked
deposit, which is the safe direction.

-}
selectedItemAccessDropboxElementId : String
selectedItemAccessDropboxElementId =
    "selectedItemAccessDropbox"


accessDropboxButtonInReading :
    ReadingFromGameClient
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
accessDropboxButtonInReading readingFromGameClient =
    selectedItemPanelButton readingFromGameClient
        { elementId = selectedItemAccessDropboxElementId
        , cmdName = selectedItemAccessDropboxElementId
        }


{-| The transfer window as this reading has it, with the parts the deposit acts
on found by name.

**No parser change was needed for any of this and none was made.**
`ParsedUserInterface` carries `uiTree` on every reading and this bot already
reaches for raw nodes that way in `okButtonInReading`, so every node here is
reachable with no edit to the vendored `EveOnline/ParseUserInterface.elm` --
which is byte-identical to `eve-online-wingman`'s and would be an eight-copy
concern (#467) rather than a one-file edit.

Every part is a `Maybe` and a window missing one is **not usable**, rather than
being acted on with the parts that were found: dragging into a window whose
transfer button this bot cannot see is staging a hold nothing will commit.

-}
type alias DropboxWindow =
    { uiNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , dropTarget : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , transferButton : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , closeControl : Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    , stagedItems : Int
    , transferReadsReady : Bool
    , destinationText : Maybe String
    , itemCountLabelText : Maybe String
    , validRangeMeters : Maybe Int
    }


dropboxWindowFromReading : ReadingFromGameClient -> Maybe DropboxWindow
dropboxWindowFromReading readingFromGameClient =
    readingFromGameClient.uiTree
        |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
        |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) dropboxWindowTypeName)
        |> List.head
        |> Maybe.map dropboxWindowFromNode


dropboxWindowFromNode : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> DropboxWindow
dropboxWindowFromNode window =
    let
        descendants =
            window |> EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion

        nodeNamed name =
            descendants
                |> List.filter
                    (.uiNode
                        >> EveOnline.ParseUserInterface.getNameFromDictEntries
                        >> (==) (Just name)
                    )
                |> List.head

        transferButton =
            nodeNamed dropboxTransferButtonName
    in
    { uiNode = window
    , dropTarget =
        descendants
            |> List.filter (.uiNode >> .pythonObjectTypeName >> (==) dropboxDropTargetTypeName)
            |> List.head
    , transferButton = transferButton
    , closeControl = dropboxCloseControl window descendants
    , stagedItems =
        nodeNamed dropboxStagedItemsContainerName
            |> Maybe.map EveOnline.ParseUserInterface.listDescendantsWithDisplayRegion
            |> Maybe.withDefault []
            |> List.filter nodeIsAnInventoryItem
            |> List.length
    , transferReadsReady =
        case transferButton of
            Nothing ->
                False

            Just button ->
                button.uiNode
                    |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
                    |> List.any (stringContainsIgnoringCase dropboxNothingToTransferMarker)
                    |> not
    , destinationText =
        nodeNamed dropboxDestinationLabelName |> Maybe.andThen firstVisibleTextOfNode
    , itemCountLabelText =
        nodeNamed dropboxItemCountLabelName |> Maybe.andThen firstVisibleTextOfNode
    , validRangeMeters =
        window.uiNode.dictEntriesOfInterest
            |> Dict.get dropboxValidRangeKey
            |> Maybe.andThen (Json.Decode.decodeValue Json.Decode.float >> Result.toMaybe)
            |> Maybe.map round
    }


{-| A stack rendered inside a container, by either of the two things the live
read showed one carrying.

The stacks in the hold were `InvItem` nodes whose `_name` read
`ItemEntry_30376`, and a staged stack renders inside `inputScroll`. Both are
matched because only one of them has been read on the staged side, and a client
that renders it as some third thing makes `stagedItems` answer `0` -- which
declines the transfer rather than committing one nothing verified, and says so
in the status line.

-}
nodeIsAnInventoryItem : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
nodeIsAnInventoryItem node =
    (node.uiNode.pythonObjectTypeName |> String.contains inventoryItemTypeNameFragment)
        || (node.uiNode
                |> EveOnline.ParseUserInterface.getNameFromDictEntries
                |> Maybe.map (String.startsWith inventoryItemNamePrefix)
                |> Maybe.withDefault False
           )


inventoryItemTypeNameFragment : String
inventoryItemTypeNameFragment =
    "InvItem"


inventoryItemNamePrefix : String
inventoryItemNamePrefix =
    "ItemEntry"


{-| Whatever this window offers that would shut it.

The parsed window controls first, then a button whose **only** visible text
reads `Cancel`. The second is narrowed to a node carrying one text because a row
container holding Cancel beside Transfer also has `Cancel` as its first text,
and clicking the centre of that row could land on Transfer -- which is the one
click on this window that must never happen by accident.

`Nothing` is a window this bot cannot close, and `depositRunAfterReading` reads
that: a run does not wait on a window nothing can shut.

-}
dropboxCloseControl :
    EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> List EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
    -> Maybe EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion
dropboxCloseControl window descendants =
    [ EveOnline.ParseUserInterface.parseWindowControlsFromWindow window
        |> Maybe.andThen .closeButton
    , descendants
        |> List.filter nodeReadsCancelAndNothingElse
        |> List.sortBy (.totalDisplayRegionVisible >> .width >> negate)
        |> List.head
    ]
        |> List.filterMap identity
        |> List.head


nodeReadsCancelAndNothingElse : EveOnline.ParseUserInterface.UITreeNodeWithDisplayRegion -> Bool
nodeReadsCancelAndNothingElse node =
    case
        node.uiNode
            |> EveOnline.ParseUserInterface.getAllContainedDisplayTexts
            |> List.map String.trim
            |> List.filter (String.isEmpty >> not)
    of
        [ onlyText ] ->
            labelReadsCancel onlyText

        _ ->
            False


labelReadsCancel : String -> Bool
labelReadsCancel text =
    let
        lowered =
            text |> String.toLower |> String.trim
    in
    (lowered == "cancel") || String.contains ">cancel<" lowered


{-| Whether the transfer window names the structure the panel is showing.

Matched against the **overview row's own name** rather than against
`home-structure-name`, for `selectedItemIsOverviewEntry`'s reason: the setting
may end in `*` and mean a prefix, where the question here is whether the window
and the panel are talking about the same object. `containsWords` is the same
whole-word matcher that question is already asked with elsewhere in this file,
and the colon in `Structure to transfer to:<structure>` is read as a separator
so the name is not glued to the word before it.

**A window that names nothing readable answers `False`**, which stops the
transfer rather than committing one nothing corroborated -- and the deposit says
so and waits, bounded by `depositGiveUpReadings`. That is the harsher of the two
available directions and is chosen: a window this bot cannot read is a client
shape it does not recognise, and the operator can see the label the status line
prints.

-}
dropboxNamesTheStructure : String -> DropboxWindow -> Bool
dropboxNamesTheStructure structureName dropbox =
    case dropbox.destinationText of
        Nothing ->
            False

        Just text ->
            containsWords structureName (text |> String.replace ":" " ")


{-| The overview's own word for a wormhole, matched against the Type column the
way `harvestableCloudTypeMarker` is matched against a cloud's.
-}
wormholeTypeMarker : String
wormholeTypeMarker =
    "Wormhole"


{-| The wormholes on this grid, filtered on `_display` for
`overviewEntryIsDisplayed`'s reason: `depositChainHop` right-clicks whichever
row this answers, and a hidden row's screen position belongs to whatever was
recycled into it.
-}
wormholeRowsOnTheOverview : List EveOnline.ParseUserInterface.OverviewWindowEntry -> List EveOnline.ParseUserInterface.OverviewWindowEntry
wormholeRowsOnTheOverview overviewEntries =
    overviewEntries
        |> List.filter overviewEntryIsDisplayed
        |> List.filter
            (.objectType
                >> Maybe.map (stringContainsIgnoringCase wormholeTypeMarker)
                >> Maybe.withDefault False
            )


{-| The menu text a wormhole's own jump entry is matched against.

A substring rather than the exact wording, because nobody has read a wormhole's
context menu on a live client here -- this app has never jumped one. `"jump"`
is the same width of net this codebase already uses for a stargate's own
`Jump Through Stargate` entry in the apps that have one, and it is chosen
narrow on purpose: a wormhole's menu also draws `Show Info`, `Warp to Within`
and the rest of the ordinary set, and none of them contain the word.

-}
jumpWormholeMenuEntry : String
jumpWormholeMenuEntry =
    "jump"


jumpWormholeCascade : EveOnline.BotFramework.UseContextMenuCascadeNode
jumpWormholeCascade =
    useMenuEntryWithTextContaining jumpWormholeMenuEntry menuCascadeCompleted


{-| How many wormholes this bot will jump looking for a way back to
`home-structure-name`, in one deposit trip.

Bounded because a chain that has gone wrong -- a bookmark that leads nowhere, a
wormhole that closed behind the ship, a chain this operator never walked in
this direction -- must not spend the whole of `depositGiveUpReadings` jumping
forever with the hold still full. Five, on the operator's own word: "can't
imagine we'll stray further than that" is not a measurement, and none exists
yet for a path nobody has flown, so this is a stated judgement call rather than
a number derived from a corpus, unlike almost every other bound in this file.

**This bounds hops, not readings.** `depositGiveUpReadings` (300, and asked
from the same place every other deposit failure is asked from) is still the
backstop that ends the session if the chain-hop machinery itself gets stuck
mid-hop -- waiting on a warp that never lands, a menu that never offers
`jump`. The two are independent for the reason #120 keeps guards independent
elsewhere in this codebase: a hop counter that never advances must not disarm
the reading-based bound underneath it.

-}
depositChainHopLimit : Int
depositChainHopLimit =
    5


{-| How many wormholes this trip has jumped, and where the ship was last known
to be.

A `DepositRun` counts readings; this counts **hops**, which is a different
question and wants a different clock -- seeing the same system on two
consecutive readings must not look like a hop, and a hop that takes many
readings (the docking-run-in shape, stretched across a whole warp and a jump)
must not go uncounted just because it was slow. The solar system's own name is
what says a hop landed: it is the one thing in a reading that changes if and
only if the ship is now somewhere else, where the ship's own screen position,
its speed and everything about the overview are exactly as true of a slow
warp that has not arrived as of a jump that has.

-}
type alias DepositChainHopMemory =
    { hopsMade : Int
    , lastSolarSystemName : Maybe String
    }


initDepositChainHopMemory : DepositChainHopMemory
initDepositChainHopMemory =
    { hopsMade = 0, lastSolarSystemName = Nothing }


{-| The chain-hop counters as they stand after this reading.

**Reset whenever there is no deposit run under way, and the moment the home
structure becomes reachable again** -- by either of `depositChainHop`'s own two
checks, on the overview or in Locations. A hop count left standing across two
different deposit trips would tell the second trip it had already spent hops
the first trip took, and a chain successfully finished is exactly the reading
this bot has no further use for the count on.

The first reading with no `lastSolarSystemName` to compare against can never
register a hop, deliberately: a hop is a **change**, and there is nothing yet
to have changed from.

-}
depositChainHopMemoryAfterReading :
    { runIsUnderWay : Bool
    , homeStructureIsReachable : Bool
    , currentSolarSystemName : Maybe String
    }
    -> DepositChainHopMemory
    -> DepositChainHopMemory
depositChainHopMemoryAfterReading answer memory =
    if not answer.runIsUnderWay || answer.homeStructureIsReachable then
        initDepositChainHopMemory

    else
        { hopsMade =
            case ( memory.lastSolarSystemName, answer.currentSolarSystemName ) of
                ( Just before, Just now ) ->
                    if before /= now then
                        memory.hopsMade + 1

                    else
                        memory.hopsMade

                _ ->
                    memory.hopsMade
        , lastSolarSystemName =
            case answer.currentSolarSystemName of
                Just now ->
                    Just now

                Nothing ->
                    memory.lastSolarSystemName
        }


{-| How long a deposit may take before the session ends with the hold still
full.

**A give-up that ends the session**, which is #464's own requirement and is why
it is asked from the head of the decision root beside the evasion's rather than
from inside the deposit -- PR #115's rule, and #102 and #133 are what happens
when that placement is got wrong. The counter behind it advances in
`updateMemoryForNewReadingFromGame` on every reading of the run whatever the
tree is doing, so a comparison asked only where the tree gets that far runs late
by however long something above it holds.

**Ending is the point rather than a last resort.** An operator empties a hold by
hand in seconds; a bot cycling on one -- warping to a structure it cannot dock
at, dragging into a hangar that is not there, answering a dialog that keeps
coming back -- wastes a session and reports itself busy throughout. So every way
a deposit can fail runs under this one clock and none of them can become a
second forever-loop.

Three hundred readings, written as fifteen patience windows so that an operator
who retunes one moves the other with it. **It has since fired live, on run 3,
and not for the reason this paragraph used to guess at.** The hold filled, the
bot reported `depositing` toward `My Neighbor Tatara`, the counter ran all the
way to 300/300, and the session ended exactly as described below -- but with
**zero drags dispatched** the whole time, which means whatever stopped this
deposit did so before the hangar work this paragraph was written to cover ever
started. The likeliest candidate is the dock itself; nothing here confirms that
yet, and it is what the next run needs to watch rather than the drag-and-confirm
step this bound was originally sized for.

-}
depositGiveUpReadings : Int
depositGiveUpReadings =
    dockingRunInPatienceReadings * 15


depositOutOfTime : { readings : Int } -> Maybe String
depositOutOfTime deposit =
    if depositGiveUpReadings <= deposit.readings then
        Just
            ("Tried to deposit the hold for "
                ++ String.fromInt deposit.readings
                ++ " readings without the client ever saying the transfer landed, which is past the bound of "
                ++ String.fromInt depositGiveUpReadings
                ++ ". THE HOLD IS STILL FULL. This is the end of the session rather than something to keep trying: an operator empties a hold by hand in seconds, and a bot cycling on one wastes an evening reporting itself busy. The status line's own deposit clause says which step it was on when it stopped."
            )

    else
        Nothing


{-| The deposit run under way, if there is one.

`Maybe` rather than a flag, because _no deposit is running_ and _a deposit is
running and has confirmed nothing_ are different facts and only the second
spends the bound.

`confirmation` is the client's own sentence rather than a `Bool`, so the status
line can quote what the client actually said. A reading's game-log entries are
gone by the next reading, which is why it is latched here rather than read where
it is acted on -- the ammo swap's `loadRefusedByClient` is the worked example
and #464 names the same rule.

`drags` is read by nothing that decides anything: it is the number that
separates _the drag has not gone out yet_ from _it went out and the client has
said nothing_, carried into the status line.

-}
type alias DepositRun =
    { readings : Int
    , confirmation : Maybe String
    , drags : Int
    }


{-| The deposit run as it stands after this reading.

**A full hold starts one**, and nothing else does. `HoldFillCannotBeRead` never
starts one, which is `holdFillFromCapacityGauge`'s chosen fail direction seen
from the other end, and `HoldTransferIsInFlight` never starts one either --
during a transfer the gauge is saying what it is doing rather than how full the
hold is.

**Only an in-space reading ends one**, and that is the clause the undock rests
on. After the client has confirmed the transfer the hold is empty and there is
still work to do -- re-select the hold, undock -- so a run that ended on the
confirmation would leave a ship sitting docked with nothing in the tree willing
to undock it. Ending on the first reading **outside** the structure means the
undock is part of the deposit and the run is over exactly when the ship is back
where #461 can pick a site again.

Two ways to end, and the second is the operator's: the client confirmed, or the
hold reads as having room while the ship is in space, which is a hold somebody
emptied by hand. A hold that cannot be read ends nothing, for the reason it
starts nothing.

**And a run does not end while the transfer window this bot opened is still on
the screen and still closable**, which is the one clause #476 adds. The in-space
deposit opens a 400x400 window over the client, and the reading that would
otherwise end the run -- the confirmation, or the hold reading empty in space --
is the same reading the window is finished with. Ending there would leave it
standing over every later reading of the session, and this bot clicks at screen
positions.

`dropboxWindowIsOpen` therefore means _open **and** carrying something this bot
could press to shut it_, never merely open. A window with no close control ends
the run exactly as it always did, so a window shape this bot does not recognise
can never strand a deposit -- and the one it does recognise is bounded by
`depositGiveUpReadings`, which ends the session naming what is still on screen.

-}
depositRunAfterReading :
    { before : Maybe DepositRun
    , holdFill : HoldFill
    , docked : Bool
    , confirmationNow : Maybe String
    , dragDispatched : Bool
    , dropboxWindowIsOpen : Bool
    }
    -> Maybe DepositRun
depositRunAfterReading answer =
    case answer.before of
        Nothing ->
            if answer.holdFill == HoldIsFull then
                Just
                    { readings = 1
                    , confirmation = answer.confirmationNow
                    , drags =
                        if answer.dragDispatched then
                            1

                        else
                            0
                    }

            else
                Nothing

        Just run ->
            let
                confirmation =
                    [ run.confirmation, answer.confirmationNow ]
                        |> List.filterMap identity
                        |> List.head
            in
            if
                not answer.docked
                    && ((confirmation /= Nothing) || (answer.holdFill == HoldHasRoom))
                    && not answer.dropboxWindowIsOpen
            then
                Nothing

            else
                Just
                    { readings = run.readings + 1
                    , confirmation = confirmation
                    , drags =
                        run.drags
                            + (if answer.dragDispatched then
                                1

                               else
                                0
                              )
                    }


{-| Everything the deposit decides on, as plain readable facts.

A record rather than a `BotDecisionContext`, for #106's reason and for the same
one `HarvestSituation` and `EvasionSituation` give: this rule orders a dozen
commands across two states the ship cannot be in at once, and a rule reachable
only through a decision context is one no case can execute -- so it would be
checked by being read, which is how a rule that does the right things in the
wrong order passes for one that works.

-}
type alias DepositSituation =
    { runIsUnderWay : Bool
    , docked : Bool
    , holdFill : HoldFill
    , confirmedByClient : Bool
    , shipIsWarping : Bool
    , dockingRunIn : Maybe DockingRunIn
    , homeStructureIsOnTheOverview : Bool
    , homeStructureBookmark : Maybe EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
    , panelShowsTheHomeStructure : Bool
    , dockButtonIsOffered : Bool
    , inventoryListsTheHold : Bool
    , holdIsTheSelectedContainer : Bool
    , structureHangarIsInTheInventory : Bool
    , itemsInTheHold : Int
    , okButtonIsOnScreen : Bool
    , chainHopBookmark : Maybe EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
    , wormholesOnTheOverview : List EveOnline.ParseUserInterface.OverviewWindowEntry
    , chainHopsMade : Int
    , accessDropboxButtonIsOffered : Bool
    , structureIsWithinDropboxRange : Bool
    , dropboxWindowIsOpen : Bool
    , dropboxNamesTheSelectedStructure : Bool
    , dropboxIsUsable : Bool
    , dropboxStagedItems : Int
    , dropboxTransferReadsReady : Bool
    }


{-| What the bot does next about a hold that has filled.

**One rule with the whole ordering in it**, `harvestStep`'s and `evasionStep`'s
shape and for the same reason: every stage can fail to be reachable and each has
to fall through or say so rather than holding the loop. The order is #464's own
sequence with two things in front of it that are not about depositing at all:

  - **no run under way** is the exit, asked first, and it is what lets the
    harvest run on every ordinary reading. `runIsUnderWay` is the latched
    `DepositRun` rather than a live look at the gauge, because the hold reads
    empty for the whole of the trip home after the transfer lands and the ship
    still has to undock;
  - **a transfer in flight** is waited through and never acted on, which is
    #464's second emphasis. It is asked above both halves because it can be
    read in either.

Docked, in order: the confirmation is what ends the work, and it re-selects the
hold before undocking so the gauge is readable again on the far side and the
next reading in space can end the run; an OK on screen is answered before
anything else is tried, because a dialog blocks the drag underneath it; then the
hangar, the hold, and the drag.

In space, in order: a ship in warp is left alone rather than re-commanded, which
is `huntAndHarvest`'s own argument; **then the transfer window, if one is open**;
then a confirmed docking run-in is waited on rather than restarted, which is
#464's fourth emphasis and the mission runner's run 27; then the structure is
selected, the dropbox is opened where the panel offers it and the ship is close
enough, docked at where the panel offers Dock, and warped to where it does not --
that last absence being the natural gate between the two, exactly as it is for
`dockAtDestinationStation`, since the Dock button is drawn only inside docking
range.

**The in-space transfer removes the dock and not the trip**, which is #476's own
correction of its framing. `selectedItemAccessDropbox` is on the Selected Item
panel, so the structure has to be _selected_, so it has to be on this grid --
verified by its absence at a gas site in another system. What the sequence
replaces is the run-in, the lobby, the hangar and the undock; the warp home is
the same warp.

**And the docked deposit is still the fallback, at three separate points.** A
structure whose panel offers no dropbox falls through to `PressTheDockButton`; a
ship too far out for `dropboxTransferRangeMeters` does too; and a window this
bot cannot read at all is said out loud and bounded rather than acted on. So
#464's sequence is what runs whenever this one cannot, which is the constraint
#476 carries over from it.

**What commits the transfer is two independent readings of the same fact**, and
neither of them is `numItemsLabel` -- see that constant for what it actually
counts, which is the hold rather than what is staged. `dropboxStagedItems` is
what `inputScroll` is holding and `dropboxTransferReadsReady` is the client's own
enabled state on the button, and both have to agree before anything is pressed.
The hold is drained into the window first and the transfer committed once, rather
than one transfer per stack, because a transfer per stack would end the run on
the first confirmation with stacks still in the hold.

**Nothing staged is a condition on closing the window, and it is there because
the hold's own gauge may be what drains as stacks are staged.** The live
sequence shows `numItemsLabel` counting _down_ while stacks go in, which is
consistent with a stack leaving the hold the moment it is staged -- and whether
the capacity gauge follows it is **unmeasured**. If it does, a hold reading
`HoldHasRoom` is what a half-staged window looks like, and closing there would
cancel the transfer with the ship's cargo sitting in a window about to be shut.
So the close waits until `inputScroll` is empty, which is true after the
transfer lands and false in the middle of staging, whichever way the gauge
behaves.

**A structure that is on neither the overview nor in Locations is not
necessarily unreachable, and `depositChainHop` is what that costs.** This ship
harvests in a wormhole, and a session that has wandered several systems from
its own home structure has nothing on either window to say where home even is
-- a `NowhereToDepositAt` that ends the session there would strand a full hold
for the rest of the evening on nothing worse than distance. So a structure
findable neither way sends the ship looking for a way back instead: warp to
the nearest bookmark carrying `retreat-bookmark-prefix` (the same instadock
convention `RetreatDestination` already uses, at the same zero), and where the
grid on arrival carries exactly one wormhole, jump it and ask the whole
question again from the new system. Two wormholes on one grid is declined
rather than guessed at -- see `ChainHopAmbiguousWormholes` -- and the whole
approach is abandoned after `depositChainHopLimit` hops, on the operator's own
word that the chain should not run longer than that.

Every state that cannot proceed answers a step that **says so**, rather than a
wait: `NowhereToDepositAt`, `NoInventoryListingTheHold`,
`NoStructureHangarInTheInventory` and `TheHoldShowsNothingToMove` are four
different things for an operator to fix and they are four different sentences.
All are bounded by `depositGiveUpReadings`, which ends the session; the
chain-hop steps carry the additional, tighter bound of `depositChainHopLimit`
hops before they give up on the chain and answer `NowhereToDepositAt` too.


## Unverified: any of this running, and three premises under it

No session of this bot has been run against a live client. The _sequence_ has
been driven by hand -- select, press, drag, drag, Transfer, and the client's own
confirmation -- so what is untested is this file driving it rather than the
mechanism itself.

Three things nobody has read, each named so a first run can settle it:

  - **The range at which the panel stops offering the button.** Both readings
    that had it were at 0 m and one press was made at roughly 90 km, which do
    not agree. `dropboxTransferRangeMeters` is this bot's own gate rather than
    the client's, deliberately tighter than any plausible answer, so the
    question does not decide anything here.
  - **Whether the hold's capacity gauge drains as stacks are staged.** See the
    staged clause on `CloseTheDropboxWindow` above for what it would cost.
  - **What a staged stack renders as.** The hold's own stacks are `InvItem`
    nodes named `ItemEntry_<id>` and `nodeIsAnInventoryItem` matches either;
    a client that draws a staged one as something else answers `0` staged,
    which declines the transfer rather than committing one nothing verified.

What to watch on the first run that fills a hold: the status line's `Dropbox:`
clause going from `no transfer window open` with a falling range, to `OPEN`
naming the structure, to `1` then `2 stack(s) staged` with the button turning
`READY`, and then gone. A run whose clause reads `no transfer window open,
panel offers none` at 0 m from the structure is a panel that does not offer this
button here, and it docks instead -- which costs nothing and is the direction
this fails in. The one to escalate on is `OPEN` naming a structure the operator
does not recognise.

-}
type DepositStep
    = TheHoldDoesNotNeedDepositing
    | WaitThroughTheTransfer
    | ReSelectTheHoldBeforeUndocking
    | Undock
    | ConfirmWhateverDialogIsOnScreen
    | NoStructureHangarInTheInventory
    | NoInventoryListingTheHold
    | SelectTheHold
    | TheHoldShowsNothingToMove
    | DragTheHoldIntoTheStructureHangar
    | WaitForTheWarpToLand
    | WaitForTheDockingRunIn DockingRunIn
    | NowhereToDepositAt
    | SelectTheHomeStructure
    | PressTheAccessDropboxButton
    | CloseTheDropboxWindow
    | TheDropboxWindowDoesNotNameTheSelectedStructure
    | TheDropboxWindowIsNotUsable
    | DragTheHoldIntoTheDropbox
    | PressTheTransferButton
    | TheDropboxHasNothingStagedToTransfer
    | PressTheDockButton
    | WarpToTheHomeStructure
    | WarpToTheHomeStructureBookmark EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
    | WarpToTheChainHopBookmark EveOnline.ParseUserInterface.LocationsWindowPlaceEntry
    | JumpTheChainHopWormhole EveOnline.ParseUserInterface.OverviewWindowEntry
    | ChainHopAmbiguousWormholes Int


depositStep : DepositSituation -> DepositStep
depositStep situation =
    if not situation.runIsUnderWay then
        TheHoldDoesNotNeedDepositing

    else if situation.holdFill == HoldTransferIsInFlight then
        WaitThroughTheTransfer

    else if situation.docked then
        if situation.confirmedByClient then
            if not situation.inventoryListsTheHold then
                Undock

            else if situation.holdIsTheSelectedContainer then
                Undock

            else
                ReSelectTheHoldBeforeUndocking

        else if situation.okButtonIsOnScreen then
            ConfirmWhateverDialogIsOnScreen

        else if not situation.inventoryListsTheHold then
            NoInventoryListingTheHold

        else if not situation.structureHangarIsInTheInventory then
            NoStructureHangarInTheInventory

        else if not situation.holdIsTheSelectedContainer then
            SelectTheHold

        else if situation.itemsInTheHold < 1 then
            TheHoldShowsNothingToMove

        else
            DragTheHoldIntoTheStructureHangar

    else if situation.shipIsWarping then
        WaitForTheWarpToLand

    else if situation.dropboxWindowIsOpen then
        if
            (situation.confirmedByClient || (situation.holdFill == HoldHasRoom))
                && (situation.dropboxStagedItems < 1)
        then
            CloseTheDropboxWindow

        else if not situation.dropboxNamesTheSelectedStructure then
            TheDropboxWindowDoesNotNameTheSelectedStructure

        else if not situation.dropboxIsUsable then
            TheDropboxWindowIsNotUsable

        else if not situation.inventoryListsTheHold then
            NoInventoryListingTheHold

        else if not situation.holdIsTheSelectedContainer then
            SelectTheHold

        else if 1 <= situation.itemsInTheHold then
            DragTheHoldIntoTheDropbox

        else if (1 <= situation.dropboxStagedItems) && situation.dropboxTransferReadsReady then
            PressTheTransferButton

        else
            TheDropboxHasNothingStagedToTransfer

    else
        case situation.dockingRunIn of
            Just runIn ->
                WaitForTheDockingRunIn runIn

            Nothing ->
                if situation.homeStructureIsOnTheOverview then
                    if not situation.panelShowsTheHomeStructure then
                        SelectTheHomeStructure

                    else if situation.accessDropboxButtonIsOffered && situation.structureIsWithinDropboxRange then
                        PressTheAccessDropboxButton

                    else if situation.dockButtonIsOffered then
                        PressTheDockButton

                    else
                        WarpToTheHomeStructure

                else if situation.homeStructureBookmark /= Nothing then
                    case situation.homeStructureBookmark of
                        Just bookmark ->
                            -- Found in Locations but not on this grid's
                            -- overview -- the ordinary warp-to-a-bookmark
                            -- path, at zero, the same as `warpToTheHuntedSite`'s
                            -- `BookmarkedSite` arm. Landing there should put
                            -- the structure on the overview, which the next
                            -- reading reads through the branch above.
                            WarpToTheHomeStructureBookmark bookmark

                        Nothing ->
                            -- Unreachable: guarded by the `/= Nothing` above.
                            NowhereToDepositAt

                else if depositChainHopLimit <= situation.chainHopsMade then
                    NowhereToDepositAt

                else
                    case situation.wormholesOnTheOverview of
                        [] ->
                            case situation.chainHopBookmark of
                                Just bookmark ->
                                    WarpToTheChainHopBookmark bookmark

                                Nothing ->
                                    NowhereToDepositAt

                        [ onlyWormhole ] ->
                            JumpTheChainHopWormhole onlyWormhole

                        several ->
                            ChainHopAmbiguousWormholes (List.length several)


depositSituationFromContext : BotDecisionContext -> DepositSituation
depositSituationFromContext context =
    let
        readingFromGameClient =
            context.readingFromGameClient

        inventory =
            depositInventoryFromReading readingFromGameClient

        homeStructureRow =
            homeStructureRowsOnTheOverview
                context.eventContext.botSettings.homeStructureName
                (readingFromGameClient.overviewWindows |> List.concatMap .entries)
                |> List.head

        settings =
            context.eventContext.botSettings

        dropbox =
            dropboxWindowFromReading readingFromGameClient
    in
    { runIsUnderWay = context.memory.deposit /= Nothing
    , docked = readingFromGameClient.shipUI == Nothing
    , holdFill = holdFillFromReading readingFromGameClient
    , confirmedByClient =
        (context.memory.deposit |> Maybe.andThen .confirmation) /= Nothing
    , shipIsWarping =
        readingFromGameClient.shipUI
            |> Maybe.map shipIsWarping
            |> Maybe.withDefault False
    , dockingRunIn = context.memory.dockingRunIn
    , homeStructureIsOnTheOverview = homeStructureRow /= Nothing
    , homeStructureBookmark =
        homeStructureBookmarkInLocations settings.homeStructureName readingFromGameClient.locationsWindow
    , panelShowsTheHomeStructure =
        homeStructureRow
            |> Maybe.map (selectedItemIsOverviewEntry readingFromGameClient)
            |> Maybe.withDefault False
    , dockButtonIsOffered =
        selectedItemPanelButton readingFromGameClient selectedItemDockButton /= Nothing
    , inventoryListsTheHold = inventory /= Nothing
    , holdIsTheSelectedContainer =
        inventory
            |> Maybe.map (.window >> holdIsTheSelectedContainer)
            |> Maybe.withDefault False
    , structureHangarIsInTheInventory =
        (inventory |> Maybe.andThen .structureHangarTreeEntry) /= Nothing
    , itemsInTheHold =
        inventory
            |> Maybe.map (.window >> inventoryItemsInView >> List.length)
            |> Maybe.withDefault 0
    , okButtonIsOnScreen = okButtonInReading readingFromGameClient /= Nothing
    , chainHopBookmark =
        readingFromGameClient.locationsWindow
            |> Maybe.map .placeEntries
            |> Maybe.withDefault []
            |> List.filter (.mainText >> bookmarkLabelStartsWithPrefix settings.retreatBookmarkPrefix)
            |> List.head
    , wormholesOnTheOverview =
        wormholeRowsOnTheOverview (readingFromGameClient.overviewWindows |> List.concatMap .entries)
    , chainHopsMade = context.memory.depositChainHop.hopsMade
    , accessDropboxButtonIsOffered =
        accessDropboxButtonInReading readingFromGameClient /= Nothing
    , structureIsWithinDropboxRange =
        rangeToTheHomeStructureInMeters settings.homeStructureName readingFromGameClient
            |> Maybe.map (\meters -> meters <= dropboxTransferRangeMeters)
            |> Maybe.withDefault False
    , dropboxWindowIsOpen = dropbox /= Nothing
    , dropboxNamesTheSelectedStructure =
        Maybe.map2 dropboxNamesTheStructure
            (homeStructureRow |> Maybe.andThen .objectName)
            dropbox
            |> Maybe.withDefault False
    , dropboxIsUsable =
        dropbox
            |> Maybe.map (\found -> (found.dropTarget /= Nothing) && (found.transferButton /= Nothing))
            |> Maybe.withDefault False
    , dropboxStagedItems = dropbox |> Maybe.map .stagedItems |> Maybe.withDefault 0
    , dropboxTransferReadsReady =
        dropbox |> Maybe.map .transferReadsReady |> Maybe.withDefault False
    }


{-| Command whatever `depositStep` says is next, or decline so the harvest runs.

`Nothing` for the one answer that is not about depositing, which is the shape
`refreshTheDirectionalScanner`, `actOnTheEvasionStep` and every entry in
`generalSetupInUserInterface` have: a hold that does not need emptying falls
straight through to the work rather than being wrapped in a branch announcing
that the bot is not depositing.

Nothing is decided here. This is the mapping from an answer onto the effects
that carry it out, kept apart from the rule so that the ordering can be executed
without a client and the effects read without one.

-}
actOnTheDepositStep : BotDecisionContext -> DepositSituation -> Maybe DecisionPathNode
actOnTheDepositStep context situation =
    let
        readingFromGameClient =
            context.readingFromGameClient

        inventory =
            depositInventoryFromReading readingFromGameClient

        dropbox =
            dropboxWindowFromReading readingFromGameClient

        homeStructureRow =
            homeStructureRowsOnTheOverview
                context.eventContext.botSettings.homeStructureName
                (readingFromGameClient.overviewWindows |> List.concatMap .entries)
                |> List.head

        structureName =
            homeStructureRow
                |> Maybe.andThen .objectName
                |> Maybe.withDefault "the home structure"

        clickOn description element =
            describeBranch description
                (decideActionForCurrentStep
                    (element |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault [])
                )

        unlessJustClicked description action =
            if previousStepDispatchedAMouseButton context then
                describeBranch
                    (description ++ " -- but the previous step already pressed the mouse, so wait for the reading to catch up rather than doing it twice.")
                    waitForProgressInGame

            else
                action

        treeEntryElement entry =
            entry.selectRegion |> Maybe.withDefault entry.uiNode
    in
    case depositStep situation of
        TheHoldDoesNotNeedDepositing ->
            Nothing

        WaitThroughTheTransfer ->
            Just
                (describeBranch
                    ("The hold's gauge is carrying its parenthesised form, which is the client saying a transfer is in flight rather than a fill level -- wait through it. See '"
                        ++ miningHoldTreeEntryText
                        ++ "' in the status line."
                    )
                    waitForProgressInGame
                )

        ReSelectTheHoldBeforeUndocking ->
            case inventory of
                Just found ->
                    Just
                        (unlessJustClicked
                            "The client says the transfer landed -- select the ship's Mining Hold again so its gauge is readable on the far side of the undock"
                            (clickOn
                                "The client says the transfer landed -- select the ship's Mining Hold again so its gauge is readable on the far side of the undock."
                                (treeEntryElement found.holdTreeEntry)
                            )
                        )

                Nothing ->
                    -- Unreachable: the step is only answered where the
                    -- situation said the inventory lists the hold, and the
                    -- situation was built from this reading.
                    Just
                        (describeBranch
                            "The inventory changed between reading it and selecting the hold -- ask again next reading."
                            waitForProgressInGame
                        )

        Undock ->
            Just (undockUsingTheStationWindow context)

        ConfirmWhateverDialogIsOnScreen ->
            case okButtonInReading readingFromGameClient of
                Just okButton ->
                    Just
                        (unlessJustClicked
                            "There is a dialog with an OK on screen -- answer it, which is not evidence of anything"
                            (clickOn
                                "There is a dialog with an OK on screen -- answer it. Whether it is the transfer's confirmation or the client's refusal of it, this click says nothing about either: what says the deposit landed is the client's own '(notify) ... moved to your hangar' line and nothing else."
                                okButton
                            )
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The dialog closed between reading it and answering it -- ask again next reading."
                            waitForProgressInGame
                        )

        NoInventoryListingTheHold ->
            Just
                (describeBranch
                    ("A full hold to deposit and no inventory window listing a '"
                        ++ miningHoldTreeEntryText
                        ++ "' -- there is nothing here to drag out of. Open the inventory on the ship's Mining Hold; the session ends at the deposit bound if it stays this way."
                    )
                    waitForProgressInGame
                )

        NoStructureHangarInTheInventory ->
            Just
                (describeBranch
                    ("Docked with a full hold and no '"
                        ++ structureHangarTreeEntryText
                        ++ "' row in the inventory to drop it into -- this structure may offer no hangar to this character, which is not something this bot can fix. The session ends at the deposit bound."
                    )
                    waitForProgressInGame
                )

        SelectTheHold ->
            case inventory of
                Just found ->
                    Just
                        (unlessJustClicked
                            "Select the ship's Mining Hold, so its own items are the ones in view to drag"
                            (clickOn
                                "Select the ship's Mining Hold, so its own items are the ones in view to drag and its own gauge is the one being read."
                                (treeEntryElement found.holdTreeEntry)
                            )
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The inventory changed between reading it and selecting the hold -- ask again next reading."
                            waitForProgressInGame
                        )

        TheHoldShowsNothingToMove ->
            Just
                (describeBranch
                    "The Mining Hold is selected and its gauge reads full, and the client is rendering no item in it to take hold of -- either the items view has not drawn yet or the gauge and the contents disagree. Nothing is dragged on a reading with nothing to drag; the session ends at the deposit bound if it stays this way."
                    waitForProgressInGame
                )

        DragTheHoldIntoTheStructureHangar ->
            case
                ( inventory |> Maybe.andThen .structureHangarTreeEntry
                , inventory |> Maybe.map (.window >> inventoryItemsInView) |> Maybe.withDefault []
                )
            of
                ( Just hangarEntry, item :: _ ) ->
                    Just
                        (unlessJustClicked
                            "Drag the Mining Hold's contents into the structure's item hangar"
                            (describeBranch
                                ("Drag the Mining Hold's contents into the structure's item hangar (drag "
                                    ++ String.fromInt
                                        ((context.memory.deposit |> Maybe.map .drags |> Maybe.withDefault 0) + 1)
                                    ++ " of this deposit). What says it landed is the client's own line, never the gauge."
                                )
                                (dragFromItemIconOntoUiElement item (treeEntryElement hangarEntry))
                            )
                        )

                _ ->
                    Just
                        (describeBranch
                            "The inventory changed between reading it and dragging out of it -- ask again next reading."
                            waitForProgressInGame
                        )

        WaitForTheWarpToLand ->
            Just
                (describeBranch
                    "On the way to deposit, and the ship is in warp -- wait for it to land rather than re-commanding a warp that is already going."
                    waitForProgressInGame
                )

        WaitForTheDockingRunIn runIn ->
            Just (describeBranch (describeDockingRunIn runIn) waitForProgressInGame)

        NowhereToDepositAt ->
            Just
                (describeBranch
                    ("The hold is full and "
                        ++ (case context.eventContext.botSettings.homeStructureName of
                                Nothing ->
                                    "'home-structure-name' is unset and has no default"

                                Just name ->
                                    "'" ++ name ++ "' is on neither this overview nor in Locations"
                           )
                        ++ (if depositChainHopLimit <= situation.chainHopsMade then
                                ", and the chain-hop fallback already spent all "
                                    ++ String.fromInt depositChainHopLimit
                                    ++ " of its wormhole jumps without finding it"

                            else if situation.chainHopBookmark == Nothing then
                                ", and there is no bookmark in Locations carrying '"
                                    ++ context.eventContext.botSettings.retreatBookmarkPrefix
                                    ++ "' to try a chain hop from either"

                            else
                                ""
                           )
                        ++ " -- nowhere to deposit from here. The session ends at the deposit bound with the hold still full."
                    )
                    waitForProgressInGame
                )

        SelectTheHomeStructure ->
            case homeStructureRow of
                Just row ->
                    Just
                        (clickOn
                            ("Select '" ++ structureName ++ "', so the Selected Item panel's own Dock button acts on it.")
                            row.uiNode
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The overview changed between choosing the home structure and selecting it -- ask again next reading."
                            waitForProgressInGame
                        )

        PressTheAccessDropboxButton ->
            case accessDropboxButtonInReading readingFromGameClient of
                Just dropboxButton ->
                    Just
                        (unlessJustClicked
                            ("Open the cargo deposit on '" ++ structureName ++ "' from the Selected Item panel")
                            (clickOn
                                ("Open the cargo deposit on '"
                                    ++ structureName
                                    ++ "' with the Selected Item panel's own '"
                                    ++ selectedItemAccessDropboxElementId
                                    ++ "'. This deposits the hold from space -- no dock, no lobby, no undock."
                                )
                                dropboxButton
                            )
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The Access Dropbox button left the panel between reading it and pressing it -- ask again next reading."
                            waitForProgressInGame
                        )

        CloseTheDropboxWindow ->
            case dropbox |> Maybe.andThen .closeControl of
                Just closeControl ->
                    Just
                        (unlessJustClicked
                            "The deposit is finished -- close the transfer window"
                            (clickOn
                                "The deposit is finished and the transfer window is still on screen -- close it, rather than leaving it over the client for the rest of the session."
                                closeControl
                            )
                        )

                Nothing ->
                    -- Unreachable: a window with no close control never holds
                    -- the run open, so `runIsUnderWay` is already false by the
                    -- time this reading is decided. See `depositRunAfterReading`.
                    Just
                        (describeBranch
                            "The transfer window changed between reading it and closing it -- ask again next reading."
                            waitForProgressInGame
                        )

        TheDropboxWindowDoesNotNameTheSelectedStructure ->
            Just
                (describeBranch
                    ("The transfer window is open and does not name '"
                        ++ structureName
                        ++ "' as where it would transfer to -- it says "
                        ++ (dropbox
                                |> Maybe.andThen .destinationText
                                |> Maybe.map (\text -> "'" ++ text ++ "'")
                                |> Maybe.withDefault "nothing this bot can read"
                           )
                        ++ ". Nothing is dragged or transferred on a reading that cannot corroborate the destination. The session ends at the deposit bound."
                    )
                    waitForProgressInGame
                )

        TheDropboxWindowIsNotUsable ->
            Just
                (describeBranch
                    ("The transfer window is open and this bot cannot find "
                        ++ (case dropbox |> Maybe.map (\found -> ( found.dropTarget, found.transferButton )) of
                                Just ( Nothing, _ ) ->
                                    "the '" ++ dropboxDropTargetTypeName ++ "' to drop items into"

                                Just ( _, Nothing ) ->
                                    "its '" ++ dropboxTransferButtonName ++ "'"

                                _ ->
                                    "the parts it needs"
                           )
                        ++ " -- staging a hold into a window nothing can commit would be worse than not starting. The session ends at the deposit bound."
                    )
                    waitForProgressInGame
                )

        DragTheHoldIntoTheDropbox ->
            case
                ( dropbox |> Maybe.andThen .dropTarget
                , inventory |> Maybe.map (.window >> inventoryItemsInView) |> Maybe.withDefault []
                )
            of
                ( Just dropTarget, item :: rest ) ->
                    Just
                        (unlessJustClicked
                            "Drag a stack out of the Mining Hold into the transfer window"
                            (describeBranch
                                ("Drag a stack out of the Mining Hold into the transfer window ("
                                    ++ String.fromInt (List.length rest)
                                    ++ " more stack(s) in view afterwards, "
                                    ++ String.fromInt (dropbox |> Maybe.map .stagedItems |> Maybe.withDefault 0)
                                    ++ " staged already). Each stack needs its own drag; the transfer is committed once the hold is drained."
                                )
                                (dragFromItemIconOntoUiElement item dropTarget)
                            )
                        )

                _ ->
                    Just
                        (describeBranch
                            "The inventory or the transfer window changed between reading it and dragging out of it -- ask again next reading."
                            waitForProgressInGame
                        )

        PressTheTransferButton ->
            case dropbox |> Maybe.andThen .transferButton of
                Just transferButton ->
                    Just
                        (unlessJustClicked
                            "Commit the transfer"
                            (clickOn
                                ("Commit the transfer of "
                                    ++ String.fromInt (dropbox |> Maybe.map .stagedItems |> Maybe.withDefault 0)
                                    ++ " staged stack(s) to '"
                                    ++ structureName
                                    ++ "'. The button reads ready, which is the client's own word for it, and the window says where it is going."
                                )
                                transferButton
                            )
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The transfer button left the window between reading it and pressing it -- ask again next reading."
                            waitForProgressInGame
                        )

        TheDropboxHasNothingStagedToTransfer ->
            Just
                (describeBranch
                    ("The Mining Hold shows nothing left to drag and the transfer window reports "
                        ++ String.fromInt (dropbox |> Maybe.map .stagedItems |> Maybe.withDefault 0)
                        ++ " staged stack(s) with its button reading "
                        ++ (if dropbox |> Maybe.map .transferReadsReady |> Maybe.withDefault False then
                                "ready"

                            else
                                "'" ++ dropboxNothingToTransferMarker ++ "'"
                           )
                        ++ " -- nothing is committed on a reading that cannot say something is staged. The session ends at the deposit bound if it stays this way."
                    )
                    waitForProgressInGame
                )

        PressTheDockButton ->
            case selectedItemPanelButton readingFromGameClient selectedItemDockButton of
                Just dockButton ->
                    Just
                        (clickOn
                            ("Dock at '"
                                ++ structureName
                                ++ "' with the Selected Item panel's own Dock button. Commanded once: the client answers by flying a run-in, and the next reading waits on it rather than asking again."
                            )
                            dockButton
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The Dock button left the panel between reading it and pressing it -- ask again next reading."
                            waitForProgressInGame
                        )

        WarpToTheHomeStructure ->
            case homeStructureRow of
                Just row ->
                    Just
                        (describeBranch
                            ("The hold is full -- warp to '"
                                ++ structureName
                                ++ "' at "
                                ++ warpAtZeroMenuEntry
                                ++ " to deposit it. The panel offers no '"
                                ++ selectedItemDockButton.elementId
                                ++ "', which is what says the structure is out of docking range."
                            )
                            (useContextMenuCascade ( structureName, row.uiNode )
                                (warpCascadeWithin warpAtZeroMenuEntry)
                                context
                            )
                        )

                Nothing ->
                    Just
                        (describeBranch
                            "The overview changed between choosing the home structure and warping to it -- ask again next reading."
                            waitForProgressInGame
                        )

        WarpToTheHomeStructureBookmark bookmark ->
            Just
                (describeBranch
                    ("The hold is full, and '"
                        ++ bookmarkLabel bookmark.mainText
                        ++ "' in Locations carries the home structure's own name -- warp to it at "
                        ++ warpAtZeroMenuEntry
                        ++ ", which is not on this grid's overview at all."
                    )
                    (useContextMenuCascade ( bookmarkLabel bookmark.mainText, bookmark.uiNode )
                        (warpCascadeWithin warpAtZeroMenuEntry)
                        context
                    )
                )

        WarpToTheChainHopBookmark bookmark ->
            Just
                (describeBranch
                    ("The hold is full and '"
                        ++ (context.eventContext.botSettings.homeStructureName |> Maybe.withDefault "the home structure")
                        ++ "' is on neither this overview nor in Locations -- warp to '"
                        ++ bookmarkLabel bookmark.mainText
                        ++ "', which carries '"
                        ++ context.eventContext.botSettings.retreatBookmarkPrefix
                        ++ "', at "
                        ++ warpAtZeroMenuEntry
                        ++ " and look there for a way back (hop "
                        ++ String.fromInt (situation.chainHopsMade + 1)
                        ++ " of "
                        ++ String.fromInt depositChainHopLimit
                        ++ ")."
                    )
                    (useContextMenuCascade ( bookmarkLabel bookmark.mainText, bookmark.uiNode )
                        (warpCascadeWithin warpAtZeroMenuEntry)
                        context
                    )
                )

        JumpTheChainHopWormhole wormhole ->
            let
                wormholeName =
                    wormhole.objectName |> Maybe.withDefault "the wormhole"
            in
            Just
                (describeBranch
                    ("The hold is full and there is exactly one wormhole on this grid -- jump '"
                        ++ wormholeName
                        ++ "' looking for a way back toward "
                        ++ (context.eventContext.botSettings.homeStructureName |> Maybe.withDefault "the home structure")
                        ++ " (hop "
                        ++ String.fromInt (situation.chainHopsMade + 1)
                        ++ " of "
                        ++ String.fromInt depositChainHopLimit
                        ++ ")."
                    )
                    (useContextMenuCascade ( wormholeName, wormhole.uiNode ) jumpWormholeCascade context)
                )

        ChainHopAmbiguousWormholes wormholeCount ->
            Just
                (describeBranch
                    ("The hold is full, "
                        ++ (context.eventContext.botSettings.homeStructureName |> Maybe.withDefault "the home structure")
                        ++ " is on neither this overview nor in Locations, and this grid carries "
                        ++ String.fromInt wormholeCount
                        ++ " wormholes rather than one -- declining to guess which one leads back rather than jumping the wrong way. An operator watching this reading can jump the right one by hand."
                    )
                    waitForProgressInGame
                )


{-| Leave the structure, using the client's own Undock button.

`eve-online-mission-runner`'s `undockUsingStationWindow`, ported with the guard
that matters: **the same button carries three labels in turn** -- `Undock` while
docked, then `Abort Undock`, then `Undocking...` -- and pressing either of the
last two cancels the undock already under way, which saxrat's run 43 turned into
10,310 readings of asking for help while docked and 20,486 clicks in between.
The vendored parser already answers that question, leaving `undockButton` empty
while `abortUndockButton` is present, so this reads the two rather than the
label.

An undock that never lands is bounded by `depositGiveUpReadings`, which ends the
session -- the deposit run is still under way until the ship is outside, so
every reading spent here spends the budget.

-}
undockUsingTheStationWindow : BotDecisionContext -> DecisionPathNode
undockUsingTheStationWindow context =
    case context.readingFromGameClient.stationWindow of
        Nothing ->
            describeBranch
                "The deposit is done and there is no station window in this reading to undock from. The session ends at the deposit bound if it stays this way."
                waitForProgressInGame

        Just stationWindow ->
            case ( stationWindow.undockButton, stationWindow.abortUndockButton ) of
                ( Just undockButton, Nothing ) ->
                    describeBranch
                        "The deposit is done and the hold is empty -- undock and go back to work. #461 picks a site again from the reading after this one."
                        (decideActionForCurrentStep
                            (mouseClickOnUIElement MouseButtonLeft undockButton
                                |> Result.withDefault []
                            )
                        )

                ( _, Just _ ) ->
                    describeBranch
                        "Already undocking -- the button in that slot now undoes the undock, so pressing it would cancel this one and start again."
                        waitForProgressInGame

                ( Nothing, Nothing ) ->
                    describeBranch
                        "The deposit is done and the station window offers no Undock button in this reading. The session ends at the deposit bound if it stays this way."
                        waitForProgressInGame


{-| What an operator reads about the hold and the deposit, on every reading.

Printed whether or not a deposit is running, because the reading an operator
wants the hold's own state on is the quiet one **while it is filling**: a hold
nobody can read is cheap to fix then -- open the inventory on the Mining Hold --
and it is the difference between a bot that will deposit and one that never
will, which is otherwise invisible until the hold is full and nothing happens.

The bound is printed beside the count rather than only in the give-up sentence,
which is `describeEvasion`'s own finding: a first version of that clause read
the sentence out of the source instead, and a mutation that dropped the bound
from the count while leaving it in the sentence survived it.

-}
describeDeposit :
    { holdFill : HoldFill
    , deposit : Maybe DepositRun
    , dockingRunIn : Maybe DockingRunIn
    , homeStructureName : Maybe String
    , depositChainHop : DepositChainHopMemory
    , dropbox : Maybe DropboxWindow
    , accessDropboxIsOffered : Bool
    , rangeToTheStructureMeters : Maybe Int
    }
    -> String
describeDeposit state =
    let
        hold =
            case state.holdFill of
                HoldFillCannotBeRead ->
                    "NOT READABLE -- no inventory window in this reading has the ship's Mining Hold selected, so nothing here knows how full it is and nothing will ever decide to deposit. Open the inventory on the Mining Hold"

                HoldHasRoom ->
                    "room for more"

                HoldIsFull ->
                    "FULL"

                HoldTransferIsInFlight ->
                    "carrying the parenthesised transient, which is a transfer in flight rather than a fill level -- waiting through it"

        run =
            case state.deposit of
                Nothing ->
                    "no deposit under way"

                Just deposit ->
                    "depositing, "
                        ++ String.fromInt deposit.readings
                        ++ "/"
                        ++ String.fromInt depositGiveUpReadings
                        ++ " readings and the session ends at that bound with the hold still full, "
                        ++ String.fromInt deposit.drags
                        ++ " drag(s) dispatched, "
                        ++ (case deposit.confirmation of
                                Nothing ->
                                    "and the client has not said the transfer landed"

                                Just confirmation ->
                                    "and the client said: '" ++ confirmation ++ "'"
                           )

        runIn =
            case state.dockingRunIn of
                Nothing ->
                    ""

                Just dockingRunIn ->
                    " Docking run-in: "
                        ++ String.fromInt dockingRunIn.dockCommands
                        ++ " dock command(s), "
                        ++ (dockingRunIn.rangeToTheStructureMeters
                                |> Maybe.map (\meters -> String.fromInt meters ++ " m")
                                |> Maybe.withDefault "range unreadable"
                           )
                        ++ ", "
                        ++ String.fromInt dockingRunIn.readingsSinceCloser
                        ++ "/"
                        ++ String.fromInt dockingRunInPatienceReadings
                        ++ " readings since it last got closer."

        chainHop =
            case state.deposit of
                Nothing ->
                    ""

                Just _ ->
                    if state.depositChainHop.hopsMade < 1 then
                        ""

                    else
                        " Chain hop: "
                            ++ String.fromInt state.depositChainHop.hopsMade
                            ++ "/"
                            ++ String.fromInt depositChainHopLimit
                            ++ " wormhole(s) jumped looking for a way back, last known system "
                            ++ (state.depositChainHop.lastSolarSystemName |> Maybe.withDefault "unreadable")
                            ++ "."

        dropbox =
            case state.dropbox of
                Nothing ->
                    " Dropbox: no transfer window open, panel "
                        ++ (if state.accessDropboxIsOffered then
                                "offers '" ++ selectedItemAccessDropboxElementId ++ "'"

                            else
                                "offers none"
                           )
                        ++ ", structure "
                        ++ (state.rangeToTheStructureMeters
                                |> Maybe.map (\meters -> String.fromInt meters ++ " m")
                                |> Maybe.withDefault "at a range this reading cannot say"
                           )
                        ++ " against the "
                        ++ String.fromInt dropboxTransferRangeMeters
                        ++ " m this bot will open it at."

                Just found ->
                    " Dropbox: OPEN, transferring to "
                        ++ (found.destinationText
                                |> Maybe.map (\text -> "'" ++ text ++ "'")
                                |> Maybe.withDefault "somewhere this bot cannot read"
                           )
                        ++ ", "
                        ++ String.fromInt found.stagedItems
                        ++ " stack(s) staged, button "
                        ++ (if found.transferReadsReady then
                                "READY"

                            else
                                "reading '" ++ dropboxNothingToTransferMarker ++ "'"
                           )
                        ++ ", "
                        ++ (if found.closeControl == Nothing then
                                "NO CLOSE CONTROL"

                            else
                                "closable"
                           )
                        ++ ", client's own "
                        ++ dropboxValidRangeKey
                        ++ " "
                        ++ (found.validRangeMeters
                                |> Maybe.map (\meters -> String.fromInt meters ++ " m")
                                |> Maybe.withDefault "unreadable"
                           )
                        ++ ". Its '"
                        ++ dropboxItemCountLabelName
                        ++ "' reads "
                        ++ (found.itemCountLabelText
                                |> Maybe.map (\text -> "'" ++ text ++ "'")
                                |> Maybe.withDefault "nothing"
                           )
                        ++ ", which counts the hold rather than what is staged (measured 2026-09-10) and which nothing decides on."
    in
    "Hold: "
        ++ hold
        ++ ". Deposit: "
        ++ run
        ++ ", at "
        ++ (state.homeStructureName
                |> Maybe.map (\name -> "'" ++ name ++ "'")
                |> Maybe.withDefault "nowhere named ('home-structure-name' is unset, so this bot cannot deposit at all)"
           )
        ++ "."
        ++ runIn
        ++ chainHop
        ++ dropbox



-- The decision tree


botMain : InterfaceToHost.BotConfig State
botMain =
    { init = EveOnline.BotFrameworkSeparatingMemory.initState initBotMemory
    , processEvent =
        EveOnline.BotFrameworkSeparatingMemory.processEvent
            { parseBotSettings = parseBotSettings
            , selectGameClientInstance = always EveOnline.BotFramework.selectGameClientInstanceWithTopmostWindow
            , updateMemoryForNewReadingFromGame = updateMemoryForNewReadingFromGame
            , statusTextFromDecisionContext = statusTextFromState
            , decideNextStep = gasHufferDecisionRoot
            }
    }


initBotMemory : BotMemory
initBotMemory =
    { readingsCount = 0
    , lastDockedStationNameFromInfoPanel = Nothing
    , shipModules = EveOnline.BotFramework.initShipModulesMemory
    , messageBoxStandoff = Nothing
    , messageBoxLastChange = Nothing
    , miningRangeRefusal = Nothing
    , miningRangeLastChange = Nothing
    , harvestCounters = initHarvestCounters
    , propulsionPressesUnanswered = 0
    , dscan = initDscanMemory
    , evasion = initEvasionCounters
    , warpNotExecutingLastChange = Nothing
    , modulesUnidentifiedReadings = 0
    , lastGridVerdictInSpaceIsClean = Nothing
    , dockingRunIn = Nothing
    , deposit = Nothing
    , depositChainHop = initDepositChainHopMemory
    }


{-| The root, and the one place anything the memory update concluded is said.

Each of these holds a message only on the reading its conclusion changed, so
this is one line per change with no separate "already reported" flag to get
wrong -- and they are said here rather than in the branches that learned them,
because the branch that learns a message box has been given up on is precisely
the branch that has just stopped running, and the harvester's own refusal is
read on readings the bot may be doing anything at all on.

-}
gasHufferDecisionRoot : BotDecisionContext -> DecisionPathNode
gasHufferDecisionRoot context =
    ([ context.memory.messageBoxLastChange
     , context.memory.miningRangeLastChange
     , context.memory.warpNotExecutingLastChange
     ]
        |> List.filterMap identity
        |> List.foldr describeBranch (gasHufferDecisionRootBeforeApplyingSettings context)
    )
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


{-| Everything above the docked-or-in-space split, headed by the one bound that
ends the session.

**`endSessionOnAnExpiredBound` is asked first, above the setup list**, which is
the mission runner's #102 and saxrat's #133 and is placement rather than
preference. The counter behind it advances in
`updateMemoryForNewReadingFromGame` on every reading whatever the bot is doing,
so a comparison asked only where the tree gets that far runs late by however long
something above it holds -- run 30 took one to 10,811 against a bound of 200,
because an undismissable window held `generalSetupInUserInterface` for three
hours and forty-four minutes. `closeMessageBox`'s standoff bounds that one known
starver here, but it is a bound on one of them rather than a guarantee about the
list, and this bound is asked whatever holds it.

PR #115's rule is what says both bounds belong here rather than beside the
branches that own them: **a give-up that ends the session bounds elapsed time and
belongs where nothing can decline to ask it; a give-up that declines an action
bounds effort and belongs where the action is.** Both of these end the session,
have no state to reach and no click to make, so nothing has a reason to be
placed over them. The three that decline an action -- the warp alarm, the cloak
and the docking run-in's patience -- are asked inside `evasionStep` and
`depositStep`, where the actions are.

**The scan, the leaving and the deposit are all asked above the
docked-or-in-space split**, and the ordering between them is what #464 is
emphatic about. The retreat outranks the deposit, so a grid that stops reading
clean takes the ship out of a docking run-in and keeps a docked ship docked
rather than undocking a full one into somebody else's grid to finish an errand.
Inverting the two compiles and reads perfectly well, which is why
`TheRetreatOutranksTheDepositTest` pins it rather than this paragraph. The split
below therefore decides one thing only: whether there is a grid to harvest.

-}
gasHufferDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
gasHufferDecisionRootBeforeApplyingSettings context =
    case endSessionOnAnExpiredBound context of
        Just expired ->
            expired

        Nothing ->
            generalSetupInUserInterface
                context.memory.messageBoxStandoff
                context.previousStepsEffects
                context.readingFromGameClient
                |> Maybe.withDefault (watchLeaveDepositOrHarvest context)


{-| The five things this bot does, in the order it does them.

Split out so the ordering is one expression a reader can take in at once, which
is what an ordering that decides whether a full ship undocks into a hostile grid
is worth.

**The propulsion module goes above the leaving, which is #465's placement and
the one entry here that is about the ship rather than about the work.** Speed is
this hull's whole survival plan, so the module is switched on before the ship is
asked to warp anywhere rather than after it has arrived -- and the cost of that
is one reading at the head of a retreat that begins with the module off, against
a whole retreat flown at base speed. It sits below the scan because the scan is
the instrument the leaving is decided on, and a scan skipped is a grid the bot
cannot see; four of `propulsionStep`'s five answers hand the reading straight
back, so this holds nothing up on any other reading.

-}
watchLeaveDepositOrHarvest : BotDecisionContext -> DecisionPathNode
watchLeaveDepositOrHarvest context =
    case refreshTheDirectionalScanner context of
        Just refresh ->
            refresh

        Nothing ->
            case keepThePropulsionModuleRunning context of
                Just switchItOn ->
                    switchItOn

                Nothing ->
                    leaveDepositOrHarvest context


{-| Whether the home structure has a row somewhere among this reading's raw
overview entries that is not currently `_display`ed.

The overview virtualises -- every object in the system has an entry in the UI
tree, but only the rows that fit on screen render, and the rest keep whatever
position they last held while recycled; see `overviewEntryIsDisplayed`.
`homeStructureRowsOnTheOverview` already declines a row in that state rather
than clicking whatever was recycled into its place, which is right, but on its
own it cannot tell a row that is genuinely absent from a row that is merely off
screen -- both read as "no row on this overview matching X". Gas huffer's own
first live deposit (run3, 2026-09-07) spent 286 of its 300-reading give-up
budget on exactly that: the ship never moved, so the row was never gone, only
unrendered, and it entered view on its own only once enough of the site's own
clutter (mined-out clouds, expired wrecks) fell off the sort order ahead of it
-- with 14 readings left to find, select, warp to, dock at and drag into before
the session gave up with the hold still full.

-}
homeStructureRowIsHiddenRatherThanAbsent :
    Maybe String
    -> List EveOnline.ParseUserInterface.OverviewWindowEntry
    -> Bool
homeStructureRowIsHiddenRatherThanAbsent homeStructureName overviewEntries =
    case homeStructureName of
        Nothing ->
            False

        Just name ->
            let
                matchingRows =
                    overviewEntries
                        |> List.filter
                            (\entry ->
                                entry.objectName
                                    |> Maybe.map (\objectName -> siteCellMatches objectName name)
                                    |> Maybe.withDefault False
                            )
            in
            (matchingRows |> List.isEmpty |> not)
                && (matchingRows |> List.all (overviewEntryIsDisplayed >> not))


{-| Turn the mouse wheel over the overview, a notch at a time, so a home
structure row that exists but is not rendered gets a chance to scroll into
view rather than waiting on the site's own clutter to fall away by itself.

`eve-online-mission-runner`'s `scrollOverviewToReveal` is the same mechanism
for the same reason, and the argument against computing a scrollbar position
from a row's rank by distance -- rows recycle, and hidden ones keep stale
positions -- does not change by moving apps, so this turns the wheel a fixed
notch and re-reads rather than aiming at a computed offset.

Reached only while a deposit is under way and the ship is in space, and only
when the structure is present-but-hidden rather than genuinely absent --
`NowhereToDepositAt`'s own sentence still fires, unchanged, once every row
naming the structure really is gone from a reading.

-}
scrollToRevealHiddenHomeStructureWhileDepositing : BotDecisionContext -> Maybe DecisionPathNode
scrollToRevealHiddenHomeStructureWhileDepositing context =
    if
        (context.memory.deposit == Nothing)
            || (context.readingFromGameClient.shipUI == Nothing)
    then
        Nothing

    else
        let
            homeStructureName =
                context.eventContext.botSettings.homeStructureName

            windowHidingIt =
                context.readingFromGameClient.overviewWindows
                    |> List.filter
                        (\overviewWindow ->
                            homeStructureRowIsHiddenRatherThanAbsent homeStructureName overviewWindow.entries
                        )
                    |> List.head
        in
        case windowHidingIt of
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

                    notches =
                        if 2 < roomBelow then
                            -homeStructureOverviewScrollNotchesPerStep

                        else
                            homeStructureOverviewScrollNotchesPerStep

                    scrollOver =
                        overviewWindow.uiNode.totalDisplayRegion
                            |> EveOnline.ParseUserInterface.centerFromDisplayRegion
                in
                Just
                    (describeBranch
                        ("The home structure has a row on this overview that is not currently rendered -- turn the wheel "
                            ++ (if notches < 0 then
                                    "down"

                                else
                                    "up"
                               )
                            ++ " over it rather than waiting on the site's own clutter to clear by itself."
                        )
                        (decideActionForCurrentStep
                            (EffectOnWindow.effectsMouseScrollAtLocation scrollOver notches)
                        )
                    )


{-| How far one scroll step turns the wheel while hunting for the home
structure. Small enough that the row is not skipped past between readings --
`eve-online-mission-runner`'s own `overviewScrollNotchesPerStep`.
-}
homeStructureOverviewScrollNotchesPerStep : Int
homeStructureOverviewScrollNotchesPerStep =
    3


{-| The three that are about the work, split out so the ordering above stays one
expression.

**The scroll for a hidden home structure is asked between the evasion and the
deposit**, above `actOnTheDepositStep` rather than inside it: `depositStep`'s
own `NowhereToDepositAt` is a rule executed in a repl over a plain record
(#106), and giving it a screen-position-dependent mouse gesture to decide would
put a client-only concern into the one part of this file that can be checked
without one. Below the evasion, because a grid that stops reading clean still
takes the ship out of turning a wheel exactly as it takes it out of a docking
run-in.

-}
leaveDepositOrHarvest : BotDecisionContext -> DecisionPathNode
leaveDepositOrHarvest context =
    case actOnTheEvasionStep context (evasionSituationFromContext context) of
        Just leaving ->
            describeBranch (describeRetreatSearch (retreatSearchFromContext context))
                (describeBranch (describeCloak (cloakSearchFromContext context)) leaving)

        Nothing ->
            case scrollToRevealHiddenHomeStructureWhileDepositing context of
                Just scrolling ->
                    scrolling

                Nothing ->
                    case actOnTheDepositStep context (depositSituationFromContext context) of
                        Just depositing ->
                            depositing

                        Nothing ->
                            branchDependingOnDockedOrInSpace
                                { ifDocked = describeBranch nothingToDoDockedYet waitForProgressInGame
                                , ifSeeShipUI = huntAndHarvest context
                                }
                                context


{-| End the session where one of the two bounds that end it has expired.

A `describeBranch` around `FinishSession` and nothing else -- no click, no wait,
no menu -- which is what makes it evaluable on any reading at all and is the
property the placement above depends on.

The evasion is asked first where both have expired, and the reason is the same
one that puts the retreat above the deposit one level down: the evasion's bound
is about a ship that cannot get off somebody else's grid, and the deposit's is
about an errand. An operator reading one sentence should read that one.

-}
endSessionOnAnExpiredBound : BotDecisionContext -> Maybe DecisionPathNode
endSessionOnAnExpiredBound context =
    [ evasionOutOfTime { readings = context.memory.evasion.readings }
    , depositOutOfTime
        { readings = context.memory.deposit |> Maybe.map .readings |> Maybe.withDefault 0 }
    ]
        |> List.filterMap identity
        |> List.head
        |> Maybe.map
            (\reason ->
                describeBranch reason
                    (Common.DecisionPath.endDecisionPath FinishSession)
            )


{-| The whole of what this bot does in space: find a cloud, or go where the
clouds are.

**The grid is what says the ship has arrived**, rather than anything about the
warp having completed. Harvestable clouds exist only inside a gas site, so a
reading whose overview carries one is a reading taken on a site -- which is the
same argument saxrat's gate branch makes about acceleration gates, and it needs
no memory of what the bot asked for. A ship still in warp reads no clouds and
falls through to the branch below, which is why the warp is declined outright on
a reading that says the ship is warping: the cascade would otherwise be
re-opened on every reading of a warp that is already going where it was told.

The site clause is printed above both, from the same `siteSearchFromContext`
call the status line makes, so the decision log and the status text cannot come
to disagree about which site was chosen.

**The scan, the leaving and the deposit are all asked before this** -- see
`watchLeaveDepositOrHarvest` -- so this is reached only on a reading whose grid
reads clean, whose hold does not need emptying, and which carries a ship UI.

-}
huntAndHarvest : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
huntAndHarvest context shipUI =
    harvestTheCloudsOnThisGrid context
        shipUI
        (siteSearchFromContext context)
        (cloudSearchFromReading context.eventContext.botSettings context.readingFromGameClient)


{-| The harvesting half, reached only on a reading whose grid reads clean.

Split out of `huntAndHarvest` when #463 put the leaving in front of it, so that
the two halves are two expressions rather than one nest -- the ordering is what
matters here and it should be readable in one screen.

-}
harvestTheCloudsOnThisGrid :
    BotDecisionContext
    -> EveOnline.ParseUserInterface.ShipUI
    -> SiteSearch
    -> CloudSearch
    -> DecisionPathNode
harvestTheCloudsOnThisGrid context shipUI site search =
    describeBranch
        (describeSiteSearch site)
        (describeBranch (describeCloudSearch search)
            (case search.chosen of
                Just cloud ->
                    actOnTheHarvestStep context
                        shipUI
                        cloud
                        (harvestSituationFromContext context shipUI cloud)

                Nothing ->
                    if shipIsWarping shipUI then
                        describeBranch "In warp -- wait for the grid the ship is going to." waitForProgressInGame

                    else
                        case site.hunted of
                            Just hunted ->
                                warpToTheHuntedSite context hunted

                            Nothing ->
                                describeBranch nothingToHuntInSpace waitForProgressInGame
            )
        )


{-| Press the scan key, where the interval says one is due.

`Nothing` rather than a branch that waits, so a reading with no refresh due falls
straight through to the work -- the shape every entry in
`generalSetupInUserInterface` has, for the same reason: a step on this hot path
that answered `Just` unconditionally would own the whole bot.

**Not asked at all on a reading with no ship UI**, which is a docked one. A
docked client answers no Directional Scan, so the keypress would go nowhere and
the reading spent on it would be spent for nothing; and the grid a docked ship
would be scanning is not the one it is on. What the evasion judges an undock on
instead is the last verdict taken from space -- see `EvasionSituation`.

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
                ("Refresh the Directional Scanner -- it is the only thing here that sees a ship before the overview does, and the last refresh went out at least "
                    ++ String.fromInt context.eventContext.botSettings.dscanIntervalSeconds
                    ++ "s ago."
                )
                (decideActionForCurrentStep (hotkeyEffects directionalScanHotkey))
            )

    else
        Nothing


shipIsWarping : EveOnline.ParseUserInterface.ShipUI -> Bool
shipIsWarping shipUI =
    (shipUI.indication |> Maybe.andThen .maneuverType)
        == Just EveOnline.ParseUserInterface.ManeuverWarp


{-| What the bot says while it has no behaviour, docked.

Said in words rather than left as a wait that looks like a bot thinking about
something. A branch that reports nothing and does nothing is indistinguishable
from a branch that is stuck, which is the whole of `/review-silent-success`; the
difference here is that the doing-nothing is deliberate, so it names itself and
names the issue that fills it in.

-}
nothingToDoDockedYet : String
nothingToDoDockedYet =
    "Docked with nothing to deposit and nothing to leave -- this bot undocks only to finish a deposit, so it is sitting still on purpose. Undock by hand to start it working; the client-setup list in this file's own header is what a run wants before that."


{-| What the bot says on a grid with no cloud and nowhere to go.

Named rather than left as a bare wait, for the reason above: this is the state a
bot that has quietly stopped working looks like from outside, so it says which
of the two it is and where the operator should look. `describeSiteSearch` has
already said _why_ nothing is hunted on the same reading.

-}
nothingToHuntInSpace : String
nothingToHuntInSpace =
    "In space with no harvestable cloud on the overview and no site to hunt -- nothing to warp to, so it is waiting on purpose. The grid reads clean on this reading and the hold does not need emptying, which are the only two reasons this wait is reached at all; anything arriving takes the ship out of it (#463) and a full hold takes it home (#464)."


{-| The things that have to be dealt with before any decision about the game.

**This list is evaluated above the docked-or-in-space split**, so anything in it
that can repeat forever freezes the whole bot rather than one branch -- the
mission runner's #101 and saxrat's #138. `closeMessageBox` carries a bound of
its own for exactly that reason and may not lose it.

`messageBoxStandoff` is passed down rather than read inside `closeMessageBox`
because it is not a fact about this reading: it is how many readings the box in
front of the bot has already survived, and only `BotMemory` can say.

-}
generalSetupInUserInterface :
    Maybe MessageBoxStandoff
    -> List (List EffectOnWindow.EffectOnWindowStruct)
    -> ReadingFromGameClient
    -> Maybe DecisionPathNode
generalSetupInUserInterface messageBoxStandoff previousStepsEffects readingFromGameClient =
    [ closeSystemSettingsMenu
    , closeMessageBox messageBoxStandoff
    , ensureInfoPanelLocationInfoIsExpanded previousStepsEffects
    ]
        |> List.filterMap
            (\maybeSetupDecisionFromGameReading ->
                maybeSetupDecisionFromGameReading readingFromGameClient
            )
        |> List.head


{-| Recovers from the game's own Settings/pause menu covering the whole screen.

Ported from `eve-online-saxrat`, which recorded it happening live, and **first
in the setup list here rather than merely present.** That placement is not
polish. EVE treats a naked Escape as "open the pause menu", this bot presses
Escape to clear a stray context menu and drives more cascades than most of them,
and once the menu is open it silently absorbs every click meant for the game
underneath -- so the symptom is "clicks are not landing", not "a menu is open",
and nothing else in the decision tree can recognise the state well enough to
close it. It cost the operator several minutes each time it happened while the
findings behind #456 were being gathered by hand.

It is also why `closeMessageBox`'s Escape rung is safe: this list answers with
its head, so a pause menu opened by that keypress on one reading is closed on
the next by the branch that exists for it, before anything else is tried.

Targets the close ('X') icon in the menu's own header rather than any of the
page-specific buttons in its footer. The header and its close button are common
to every page this menu can show, while the footer's buttons and their positions
are specific to whichever page happens to be open; saxrat's copy records the
live memory dump that established `closeMenuClick` as the stable, page-
independent element id, found by walking down from the `l_systemmenu` layer.

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


closeMessageBox : Maybe MessageBoxStandoff -> ReadingFromGameClient -> Maybe DecisionPathNode
closeMessageBox standoff readingFromGameClient =
    readingFromGameClient.messageBoxes
        |> List.head
        |> Maybe.andThen
            (\messageBox ->
                case messageBoxStandoffVerdictForBox standoff messageBox of
                    LeaveTheMessageBoxAlone ->
                        -- The whole of the ladder: `Nothing` here is what lets
                        -- the rest of the tree run. The box is still on the
                        -- screen and every branch below is now working around
                        -- it, which is worse than a closed box and
                        -- incomparably better than nothing running at all. The
                        -- give-up said so once at the root on the reading it
                        -- was reached, and the status line keeps saying so.
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


{-| What to do about the box in front of the bot, given how long it has been
there.

**The declining answer stays the default and that is not negotiable** -- the
mission runner's #54, and the reason the ladder starts where this branch always
did rather than at something cleverer. These dialogs guard destructive actions.
What the ladder adds is only what happens once the answer has demonstrably not
worked.

-}
type MessageBoxStandoffVerdict
    = AnswerTheMessageBox
    | PressEscapeAtTheMessageBox
    | LeaveTheMessageBoxAlone


{-| How many readings the ordinary answer gets before the escalation.

**60, and it rests on the mission runner's corpus rather than on this app's**,
which has none at all. What that bot measured transfers because the thing
measured is the client's rather than the bot's: the same widget, parsed by the
same `parseMessageBoxesFromUITreeRoot` matching on `pythonObjectTypeName` alone,
and dismissed by the same three options in the same order. Counting consecutive
readings with a box on the screen, its recovered runs give stretches of 6, 10,
11, 18, 20 and 44 readings and nothing else, while run 30's one box ran to
32,585. Nothing recorded lies between 44 and the incident, so 60 is placed in a
gap rather than cut through a distribution.

-}
messageBoxAnswersBeforeEscape : Int
messageBoxAnswersBeforeEscape =
    60


{-| How many readings the whole standoff gets before the bot stops answering.

Twice `messageBoxAnswersBeforeEscape`, so Escape gets exactly as long to work as
the answer it replaced -- written as a multiple so the argument cannot drift
away from the number.

-}
messageBoxStandoffGiveUpReadings : Int
messageBoxStandoffGiveUpReadings =
    messageBoxAnswersBeforeEscape * 2


{-| The ladder, over the standoff `updateMemoryForNewReadingFromGame` recorded.

**Escape is what this codebase already escalates with**, and it needs no focus.
**Ctrl+W is deliberately not in it**, though it is the client's own "close the
active window": it acts on the _focused_ window, and the loot window paid for
that lesson twice in another app -- hundreds of presses at an unfocused window,
closing nothing either time.

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
Lost modal inverts that: it carries a single `Quit` button, no `Close`/`OK` and
no `no_dialog_button`, so both recognising options miss and the answer falls
through to the window's own close control -- and on that box the declining
answer is the destructive one. saxrat run 22 lost its client to it six minutes
into an eight-hour tour. The escape rung is the same keypress by another route,
so both rungs are what this skips.

It is not a bound and it does not wait, because there is nothing to wait for: a
client with no server connection cannot be recovered by anything the bot can
press, and quitting takes it away from the operator who _can_ reconnect.

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
`Connection Lost` is the title and `connection to server was lost` the body. Two
substrings because a single common word would reach dialogs this must not
silence, and silencing a dialog is exactly how a bot stops answering something
it should.

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


{-| The declining answer, and the only answer this bot ever gives a dialog.

Three options in order, and none of them is an affirmative: a `Close` or `OK`
button, the `no_dialog_button` every language's "No" carries, and the window's
own close control for a dialog whose buttons this file does not recognise at
all. There is no accept path here at all, unlike saxrat's -- this bot joins no
fleet and takes no invitation.

-}
closeMessageBoxByDeclining : EveOnline.ParseUserInterface.MessageBox -> DecisionPathNode
closeMessageBoxByDeclining messageBox =
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

            {- Dismissal options in descending order of confidence. They
               deliberately never include a positive answer: these dialogs guard
               destructive actions, so the bot's automatic reply must always be
               the one that declines.

               1. A plain "Close"/"OK" acknowledgement.
               2. "No" on a confirmation dialog -- which has no Close/OK button
                  at all, so nothing above matches it. `no_dialog_button` is
                  stable across client languages.
               3. The window's own close ('X') control, for a dialog whose
                  buttons we do not recognise at all.
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
                -- Bounded by the standoff above rather than left to repeat:
                -- this branch sits in `generalSetupInUserInterface`, so an
                -- alarm raised here would hold the whole tree, and what stops
                -- it is `messageBoxStandoffGiveUpReadings` handing the tree
                -- back at 120 readings.
                describeBranch "I see no way to close this message box." askForHelpToGetUnstuck

            Just ( description, nodeToClick ) ->
                describeBranch ("Dismiss it using " ++ description ++ ".")
                    (decideActionForCurrentStep
                        (mouseClickOnUIElement MouseButtonLeft nodeToClick
                            |> Result.withDefault []
                        )
                    )
        )


{-| What a message box is, for the purpose of counting how long this one has
been in the way.

Its own display texts and its buttons, joined into one string -- deliberately
**not** its display region, which a widget re-rendered each reading can differ
in sub-pixel while looking identical, so a count keyed on it would never
accumulate at all.

The buttons carry their `_name` as well as their label, because the label is
what a person reads and the name is what this file acts on.

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


{-| The one line the operator gets when the bot stops answering a box.

Said once, at the root, on the reading the give-up is reached -- because the
verdict is settled in the memory update, which runs whatever the bot is doing,
and the branch that would otherwise say so is precisely the branch that has just
stopped running.

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


{-| How much of a box's identity a line prints.
-}
messageBoxGiveUpIdentityLength : Int
messageBoxGiveUpIdentityLength =
    200


{-| A box's identity, cut to what one line can carry.

One function for both readers rather than the cut written out twice, so the
give-up sentence and the status clause cannot come to disagree about how much of
a dialog an operator is shown.

-}
messageBoxIdentityForOperator : String -> String
messageBoxIdentityForOperator identity =
    if messageBoxGiveUpIdentityLength < String.length identity then
        String.left messageBoxGiveUpIdentityLength identity ++ "..."

    else
        identity


{-| The one clause on a reading that says a box is in front of the bot, and the
only thing that says which box.

Once the give-up is reached `closeMessageBox` answers `Nothing` and prints no
decision line at all, so nothing else on the reading mentions the box; and
`describeMessageBoxGivenUpOn`, which does name it, is written on the one reading
the count crosses the bound and on no other.

-}
describeMessageBoxStandoff : Maybe MessageBoxStandoff -> String
describeMessageBoxStandoff standoff =
    case standoff of
        Nothing ->
            ""

        Just present ->
            " Message box: "
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
_this_ box: a session that closes forty dialogs starts from zero at each one,
and only a box in front of the bot on every consecutive reading can accumulate
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



-- Memory and the status line


updateMemoryForNewReadingFromGame : UpdateMemoryContext BotSettings -> BotMemory -> BotMemory
updateMemoryForNewReadingFromGame context botMemoryBefore =
    let
        currentStationNameFromInfoPanel =
            context.readingFromGameClient.infoPanelContainer
                |> Maybe.andThen .infoPanelLocationInfo
                |> Maybe.andThen .expandedContent
                |> Maybe.andThen .currentStationName

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

        miningRangeRefusal =
            miningRangeRefusalAfterReading
                { before = botMemoryBefore.miningRangeRefusal
                , refusalNow = miningRangeRefusalFromGameLog context.readingFromGameClient
                }

        -- Said at the root on the reading a refusal arrives and on no other, so
        -- an operator gets one line per complaint rather than one per reading
        -- for the rest of the session. The status line keeps saying it, with
        -- its age.
        miningRangeLastChange =
            miningRangeRefusalFromGameLog context.readingFromGameClient
                |> Maybe.map
                    (\refusal ->
                        describeMiningRange
                            (Just
                                { strayedToMeters = refusal.strayedToMeters
                                , miningRangeMeters = refusal.miningRangeMeters
                                , readingsSince = 0
                                }
                            )
                    )

        -- The same `cloudSearch` the decision and the status line ask, so the
        -- counters cannot come to be about a cloud the bot was not working on.
        cloudChosen =
            (cloudSearchFromReading context.botSettings context.readingFromGameClient).chosen

        shipModules =
            botMemoryBefore.shipModules
                |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory
                    context.readingFromGameClient

        moduleButtons =
            context.readingFromGameClient.shipUI
                |> Maybe.map .moduleButtons
                |> Maybe.withDefault []

        -- The same `cloakAmongFittedModules` the decision and the status line
        -- ask, over the memory this reading has just written rather than the one
        -- before it -- so a tooltip that landed on this reading counts on this
        -- reading. #102: one rule, three readers.
        cloakNow =
            moduleButtons
                |> List.map
                    (\moduleButton ->
                        { tooltipTexts =
                            EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton
                                shipModules
                                moduleButton
                                |> Maybe.map
                                    (.allContainedDisplayTextsWithRegion >> List.map Tuple.first)
                                |> Maybe.withDefault []
                        , runningState = moduleRunningState moduleButton
                        }
                    )
                |> cloakAmongFittedModules

        docked =
            context.readingFromGameClient.shipUI == Nothing

        gridIsClean =
            gridReadsClean
                (gridVerdict
                    (gridEvidenceFromReading (hostileTrustFromSettings context.botSettings)
                        { secondsSinceScan =
                            secondsSinceLastScan
                                { nowMilliseconds = context.timeInMilliseconds
                                , dscan = botMemoryBefore.dscan
                                }
                        , staleAfterSeconds =
                            dscanStaleAfterSeconds context.botSettings.dscanIntervalSeconds
                        }
                        context.readingFromGameClient
                    )
                )

        evasion =
            evasionCountersAfterReading
                { gridIsClean = gridIsClean
                , docked = docked
                , shipIsWarping =
                    context.readingFromGameClient.shipUI
                        |> Maybe.map shipIsWarping
                        |> Maybe.withDefault False

                -- A fit with no cloak in it, and one whose modules are not
                -- identified yet, both count as answered: there is nothing being
                -- asked for, so there is nothing to bound.
                , cloakAnsweredTheAsk =
                    case cloakNow of
                        TheCloakIsFittedAndNotRunning _ ->
                            False

                        _ ->
                            True
                }
                botMemoryBefore.evasion

        -- Said at the root on the one reading the warp bound is crossed. The
        -- count only ever rises while one evasion runs, so the crossing happens
        -- once per evasion rather than once per reading past it.
        warpNotExecutingLastChange =
            warpNotExecutingAlarm
                { before = botMemoryBefore.evasion.warpUnexecutedReadings
                , now = evasion.warpUnexecutedReadings
                }

        -- The same `holdFillFromReading` the decision and the status line ask,
        -- so the run cannot come to be about a hold the bot was not looking at.
        -- #102: one rule, three readers.
        holdFill =
            holdFillFromReading context.readingFromGameClient

        -- The same reading `keepThePropulsionModuleRunning` and the status line
        -- take, through the same declaration, so the count cannot come to be
        -- about a module the decision was not looking at. #102: one rule, three
        -- readers.
        propulsionReading =
            context.readingFromGameClient.shipUI
                |> Maybe.andThen propulsionModuleFromShipUI
                |> Maybe.map moduleRunningState

        -- Read from the effects the bot dispatched rather than from anything
        -- the client says, because what was asked for is knowable where what
        -- the client did with it is not. A drag is the one gesture in this app
        -- that presses a button and then moves, so the shape is what names it.
        dragDispatched =
            context.previousStepsEffects
                |> List.head
                |> Maybe.map stepDraggedSomething
                |> Maybe.withDefault False

        -- Which harvester's hotkey the previous step actually pressed, read the
        -- same way `dragDispatched` is: off the effects dispatched rather than
        -- off which `HarvestStep` produced them, since only the effects say
        -- what was asked for. `[ 0, 1 ]` rather than deriving the indices from
        -- `harvesterModulesFromShipUI`, because this ship is fitted with two of
        -- them throughout this file ("run both harvesters") and a docked
        -- reading has no `shipUI` to derive them from at all -- the same reason
        -- `describeHarvestSituation` hardcodes "both" rather than a count.
        harvesterIndexJustKicked =
            [ 0, 1 ]
                |> List.filter
                    (\index ->
                        topRowModuleHotkeyFromIndex index
                            |> Maybe.map
                                (\keyCode ->
                                    context.previousStepsEffects
                                        |> List.head
                                        |> Maybe.map (stepPressedExactly [ keyCode ])
                                        |> Maybe.withDefault False
                                )
                            |> Maybe.withDefault False
                    )
                |> List.head

        -- Read off the current reading rather than the previous step's
        -- effects, because this is evidence about the module rather than
        -- about what this bot asked for -- see `harvesterLooksActiveByRamp`.
        -- `[ 0, 1 ]` for the same reason `harvesterIndexJustKicked` uses it: a
        -- docked reading has no `shipUI` to derive real indices from at all.
        harvesterIndicesLookingActiveByRamp =
            context.readingFromGameClient.shipUI
                |> Maybe.map harvesterModulesFromShipUI
                |> Maybe.withDefault []
                |> List.indexedMap Tuple.pair
                |> List.filter (Tuple.second >> harvesterLooksActiveByRamp)
                |> List.map Tuple.first

        -- Both of `depositChainHop`'s own reasons to run to somewhere -- see
        -- `homeStructureRowsOnTheOverview` and `homeStructureBookmarkInLocations`.
        homeStructureIsReachableForDeposit =
            (homeStructureRowsOnTheOverview context.botSettings.homeStructureName
                (context.readingFromGameClient.overviewWindows |> List.concatMap .entries)
                /= []
            )
                || (homeStructureBookmarkInLocations context.botSettings.homeStructureName
                        context.readingFromGameClient.locationsWindow
                        /= Nothing
                   )
    in
    { readingsCount = botMemoryBefore.readingsCount + 1
    , lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , shipModules = shipModules
    , messageBoxStandoff = messageBoxStandoff
    , messageBoxLastChange = messageBoxLastChange
    , miningRangeRefusal = miningRangeRefusal
    , miningRangeLastChange = miningRangeLastChange
    , harvestCounters =
        harvestCountersAfterReading
            { cloudIsChosen = cloudChosen /= Nothing
            , panelShowsTheCloud =
                cloudChosen
                    |> Maybe.map (selectedItemIsOverviewEntry context.readingFromGameClient)
                    |> Maybe.withDefault False
            , cloudReadsLocked =
                cloudChosen
                    |> Maybe.map (.commonIndications >> .targetedByMe)
                    |> Maybe.withDefault False
            , harvesterIndexJustKicked = harvesterIndexJustKicked
            , harvesterIndicesLookingActiveByRamp = harvesterIndicesLookingActiveByRamp
            }
            botMemoryBefore.harvestCounters
    , propulsionPressesUnanswered =
        propulsionPressesAfterReading
            { pressDispatched =
                context.previousStepsEffects
                    |> List.head
                    |> Maybe.map (stepPressedExactly propulsionModuleHotkey)
                    |> Maybe.withDefault False
            , readsRunning = propulsionReading == Just ModuleIsRunning
            }
            botMemoryBefore.propulsionPressesUnanswered
    , dscan =
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
    , evasion = evasion
    , warpNotExecutingLastChange = warpNotExecutingLastChange

    -- Advanced only on a reading that could have learned something and did not:
    -- a ship UI in the reading, and at least one module button whose tooltip is
    -- still unknown. So a docked session, or one whose modules are all
    -- identified, spends none of the budget.
    , modulesUnidentifiedReadings =
        if
            (moduleButtons |> List.isEmpty |> not)
                && (moduleButtons
                        |> List.any
                            (EveOnline.BotFramework.getModuleButtonTooltipFromModuleButton shipModules
                                >> (==) Nothing
                            )
                   )
        then
            botMemoryBefore.modulesUnidentifiedReadings + 1

        else
            botMemoryBefore.modulesUnidentifiedReadings
    , lastGridVerdictInSpaceIsClean =
        if docked then
            botMemoryBefore.lastGridVerdictInSpaceIsClean

        else
            Just gridIsClean
    , dockingRunIn =
        dockingRunInAfterReading
            { before = botMemoryBefore.dockingRunIn
            , courseSetThisReading =
                courseSetToDockingPerimeterFromGameLog context.readingFromGameClient /= Nothing
            , rangeNow =
                rangeToTheHomeStructureInMeters context.botSettings.homeStructureName
                    context.readingFromGameClient
            , docked = docked
            }
    , deposit =
        depositRunAfterReading
            { before = botMemoryBefore.deposit
            , holdFill = holdFill
            , docked = docked
            , confirmationNow = depositConfirmedInGameLog context.readingFromGameClient
            , dragDispatched = dragDispatched
            , dropboxWindowIsOpen =
                dropboxWindowFromReading context.readingFromGameClient
                    |> Maybe.andThen .closeControl
                    |> (/=) Nothing
            }
    , depositChainHop =
        depositChainHopMemoryAfterReading
            { runIsUnderWay = botMemoryBefore.deposit /= Nothing
            , homeStructureIsReachable = homeStructureIsReachableForDeposit
            , currentSolarSystemName =
                context.readingFromGameClient.infoPanelContainer
                    |> Maybe.andThen .infoPanelLocationInfo
                    |> Maybe.andThen .currentSolarSystemName
            }
            botMemoryBefore.depositChainHop
    }


{-| What an operator watching a run reads on every reading.

Deliberately opens with what the bot **cannot** do, because everything else here
is a bot that looks like it is working: it warps, orbits, locks, harvests,
notices and leaves, and a console reporting all of that while something under it
is inert would be a console reporting success. That is the failure this repo is
named after, and the marker has moved with each issue that closed one --
`SCAFFOLD ONLY`, then `HARVESTS BUT CANNOT LEAVE`, then `NOTICES BUT CANNOT
LEAVE`, then `LEAVES WITHOUT ITS PROPULSION MODULE`, and with #465 the last of
#456's behaviour is in.

**What is left is that none of it has ever run**, which is a weaker sentence
than the four it replaces and is the honest one: there is no recorded session of
this app at all, so every bound in it is a relation rather than a measurement
and every premise is one read taken on 2026-09-04 or a corpus from another bot.
A marker that named a missing feature was something an operator could not fix;
this one is, by flying it and reading the clauses below.

The retreat, cloak and propulsion clauses are printed on **every** reading rather
than only while they are being acted on, because the reading an operator wants
them on is the quiet one before anything arrives: a Locations window nobody
opened, a cloak nobody identified and a propulsion module that never came on are
all cheap to fix then and not fixable at all afterwards.

The harvest clause and the cloud clause are only printed where the reading has
them, since a docked reading has no grid and a clause an operator reads on every
reading regardless is a clause they stop seeing.

-}
statusTextFromState : BotDecisionContext -> String
statusTextFromState context =
    let
        settings =
            context.eventContext.botSettings

        cloudSearchNow =
            cloudSearchFromReading settings context.readingFromGameClient

        harvestClause =
            case ( context.readingFromGameClient.shipUI, cloudSearchNow.chosen ) of
                ( Just shipUI, Just cloud ) ->
                    [ describeCloudSearch cloudSearchNow
                    , describeHarvestSituation (harvestSituationFromContext context shipUI cloud)
                    ]

                ( Just _, Nothing ) ->
                    [ describeCloudSearch cloudSearchNow ]

                ( Nothing, _ ) ->
                    []
    in
    [ "FLOWN (runs 1-7): harvesting, D-Scan hostile detection and the evade/recover loop are confirmed live (runs 1-5 harvested for hundreds of readings apiece; run 1 alone cleared dozens of short evasions and read named ships off D-Scan). Deposit now tries the home structure from space first, falling back to #464's dock (#476) -- the deposit-from-space sequence has been driven by hand, but no full automated run has exercised it yet. The old dock-only path was watched failing outright: run 3 ran its 300-reading give-up to the end with zero drags dispatched, hold still full. The propulsion-module reading (#465) has answered CANNOT TELL on every live reading seen so far, never 'running'. The wormhole-chain-hop retreat has never fired live. Read the clauses below against that, not as instruments nobody has calibrated."
    , describePropulsionModule (propulsionSituationFromContext context)
    , describeGrid (gridEvidenceFromContext context)
    , describeDscanSightingsFromReading context.readingFromGameClient
    , describeDscanCadence
        { nowMilliseconds = context.eventContext.timeInMilliseconds
        , intervalSeconds = settings.dscanIntervalSeconds
        , dscan = context.memory.dscan
        }
    , describeSiteSearch (siteSearchFromContext context)
    ]
        ++ harvestClause
        ++ [ describeMiningRange context.memory.miningRangeRefusal
           , describeDeposit
                { holdFill = holdFillFromReading context.readingFromGameClient
                , deposit = context.memory.deposit
                , dockingRunIn = context.memory.dockingRunIn
                , homeStructureName = settings.homeStructureName
                , depositChainHop = context.memory.depositChainHop
                , dropbox = dropboxWindowFromReading context.readingFromGameClient
                , accessDropboxIsOffered =
                    accessDropboxButtonInReading context.readingFromGameClient /= Nothing
                , rangeToTheStructureMeters =
                    rangeToTheHomeStructureInMeters settings.homeStructureName
                        context.readingFromGameClient
                }
           , "Readings: "
                ++ String.fromInt context.memory.readingsCount
                ++ ". Site group: '"
                ++ settings.anomalyGroup
                ++ "'. Clouds: "
                ++ (case settings.gasCloudNamePrefix of
                        Nothing ->
                            "any harvestable cloud"

                        Just prefix ->
                            "those named '" ++ prefix ++ "...'"
                   )
                ++ "."
           , describeHostileTrust (hostileTrustFromSettings settings)
           , describeRetreatSearch (retreatSearchFromContext context)
           , describeCloak (cloakSearchFromContext context)
           , describeEvasion context.memory.evasion
                ++ describeMessageBoxStandoff context.memory.messageBoxStandoff
           ]
        |> String.join "\n"
