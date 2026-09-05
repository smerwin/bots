{- EVE Online gas huffer -- HARVESTS BUT CANNOT LEAVE

      This app is meant to harvest gas from a wormhole gas site, deposit it at a
      structure, and leave the moment anything else shows up on the grid. Since
      #461 the **harvesting** half of that works: it decides which site to hunt,
      warps to it, picks the cloud on the grid whose designation carries the
      highest trailing number, orbits it, keeps the propulsion module running,
      locks it and runs both gas harvesters.

      **Nothing here watches the grid and nothing here retreats**, which is the
      one thing to be clear about before starting a run. Noticing a hostile is
      #462 and leaving is #463, so a session left unattended is a ship that will
      still be sitting on its cloud when somebody else warps in -- and it has no
      guns, no tank worth the name and no plan but to leave. Nor does it deposit
      the hold when that fills (#464), and nothing keeps the propulsion module on
      across a warp (#465). The status line says all of that on every reading
      rather than letting a bot that looks busy read as a bot that is covered.

      Started under issue #459; the behaviour is #460 (which site to hunt), #461
      (the harvest loop, here), #462 (hostile detection), #463 (retreat, cloak
      and evade), #464 (deposit the hold when it fills) and #465 (the propulsion
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
      + **Leave the Locations window open if you want the bookmark fallback.**
        With no scanned row reading the hunted Group, this bot will take a
        bookmark whose name carries `Reservoir` -- the client's own naming for
        the wormhole gas sites (Ordinary/Sizeable Perimeter Reservoir,
        Vast/Bountiful Frontier Reservoir, Vital/Instrumental Core Reservoir).
        With that window shut there is no fallback, which is a different thing
        from having no such bookmark and reads differently in the status line.
      + **The overview must show gas clouds, with the Name and Type columns
        visible.** A harvestable cloud renders with its own designation in the
        Name column and the generic `Harvestable Cloud` in the Type column, and
        the bot needs both: the Type is what makes a row a cloud at all, and the
        Name is what `gas-cloud-name-prefix` is matched against and what carries
        the trailing number the site's clouds are ordered by.
      + Set the overview to sort by distance with the nearest entry at the top.
      + In the ship UI, arrange the modules:
        + Put the gas harvesters in the **top** row, side by side.
        + Put the propulsion module **first in the middle row**.
        + Put anything that should simply keep running in the rest of the middle
          row.
        + Hide passive modules by disabling the check-box `Display Passive
          Modules`, so the rows the bot counts are the rows it can press.
      + **Set the Orbit button's distance by hand, once, before starting a run.**
        This is the one setup item with no way to check itself. Nothing in this
        repo can command an orbit *at a distance*: the Selected Item panel's
        Orbit button orbits at whatever range the **client** last used, and that
        range is remembered by the client rather than stated in any reading. So
        orbit something at the range you want by hand once, and the button will
        keep it. Get this wrong and the ship orbits outside harvester range,
        which the client reports as `deactivates without transfering ore to your
        cargo hold because your ship has strayed to a distance of ... beyond its
        mining range of ...` -- a game-log line, which is the only thing that
        will ever tell the bot the setup is wrong. **This bot reads that line and
        reports it, naming both distances, and does not act on it.** It cannot:
        the range it would have to orbit at is not something any command here can
        express, so the only repair is the one above, made by hand. See
        `miningRangeRefusalFromGameLog`.
      + Name the bookmarks you are willing to be warped to so that they all
        start with the same prefix, and give that prefix to
        `retreat-bookmark-prefix`. Every bookmark matching it is a place this bot
        may run to unattended.

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
        which is also the second place this bot will run to when it leaves. **No
        default** -- with none set, this bot has nowhere to deposit and one fewer
        place to retreat to, and the status line says so on every reading.
      + `retreat-bookmark-prefix` : the prefix marking bookmarks that are safe to
        run to. Defaults to `*`, which is a common convention rather than a
        claim about your bookmarks: a prefix is a pattern, and nothing here can
        tell you whether any bookmark actually matches it until a run reads the
        Locations window.
      + `friendly-ship-tag` : a substring marking a ship as one of yours. A ship
        whose name carries it reads friendly; **every other ship reads hostile,
        and so does every ship when this setting is unset.** That direction is
        deliberate and is not a default anyone should rely on being convenient:
        an unset tag means trust nobody, never trust everybody. Matched ignoring
        case, as a substring, so it can be a corporation ticker in brackets or a
        naming convention of your own.
      + `dscan-interval-seconds` : how often to refresh the Directional Scanner.
        Defaults to 5. **This number is unmeasured** -- nothing has yet watched a
        ship arrive on this bot's D-Scan, so it is a starting point chosen to
        cost roughly one reading in ten rather than a figure derived from how
        long a hostile takes to arrive.
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
        , useMenuEntryWithTextContaining
        )
import EveOnline.BotFrameworkSeparatingMemory
    exposing
        ( DecisionPathNode
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
                |> List.sortBy (Tuple.first >> gasCloudOrder)

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
three-digit cloud.

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
                ++ "', the highest trailing number of "
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
    if
        context.previousStepsEffects
            |> List.take EveOnline.BotFrameworkSeparatingMemory.moduleButtonClickSettlingSteps
            |> List.any (stepPressedExactly chord)
    then
        describeBranch
            "Already pressed that module hotkey in a previous step -- a module button is a toggle, so wait for the client to show the result rather than pressing it off again."
            waitForProgressInGame

    else
        describeBranch describe (decideActionForCurrentStep (hotkeyEffects chord))



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


{-| The two counters bounding the two things the harvest loop asks for.

Advanced in `updateMemoryForNewReadingFromGame`, which is the only place that
can write memory and the one place that never sees a decision -- so what they
count is the **client's** answer rather than the branch's activity, and they
therefore keep counting whatever else holds the tree. That is the half #102's
placement rule is about, and the comparison against them is asked inside
`harvestStep`, which is reached on every reading the ship is on a grid with a
cloud on it.

Both reset outright on a reading where the client has answered, and on any
reading with no cloud chosen at all -- so a session that harvests forty clouds
starts from zero at each one.

-}
type alias HarvestCounters =
    { panelSelectUnansweredReadings : Int
    , lockUnansweredReadings : Int
    }


initHarvestCounters : HarvestCounters
initHarvestCounters =
    { panelSelectUnansweredReadings = 0, lockUnansweredReadings = 0 }


{-| What one reading says about the two asks, in the terms the counters need.

A record rather than a reading, so a case can fold a whole session through
`harvestCountersAfterReading` and read the counters back.

-}
type alias HarvestAnswerFromClient =
    { cloudIsChosen : Bool
    , panelShowsTheCloud : Bool
    , cloudReadsLocked : Bool
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
        }


{-| Everything about a grid the harvest loop decides on, as plain readable facts.

A record rather than a `BotDecisionContext`, for #106's reason: this is the one
rule in this app that orders four separate commands, and a rule reachable only
through a decision context is one no case can execute -- so it would be checked
by being read, which is how a rule that does the right things in the wrong order
passes for one that works.

-}
type alias HarvestSituation =
    { propulsionModule : Maybe ModuleRunningState
    , shipIsOrbiting : Bool
    , panelShowsTheCloud : Bool
    , orbitButtonIsOffered : Bool
    , cloudReadsLocked : Bool
    , cloudReadsLocking : Bool
    , harvestersNotRunning : List Int
    , counters : HarvestCounters
    }


{-| What the bot commands next on a grid it is harvesting.

**One rule with the whole ordering in it**, rather than four branches each
deciding whether it is its turn. The order is the issue's own -- keep the
propulsion module running, orbit the cloud, lock it, run both harvesters -- and
what makes it worth writing as one rule is that every stage can _fail to be
reachable_, and each of those has to fall through to the next rather than
holding the loop:

  - a middle row this reading cannot read means no propulsion module to press,
  - a panel that never comes to show the cloud expires and the bot harvests
    without an orbit,
  - a panel showing the cloud and offering no Orbit button is the ordinary
    contextual button set rather than a failure, and waits by falling through,
  - a lock the client will not grant expires, and then there is genuinely
    nothing left to command, because a harvester runs on the active target.

`NothingLeftToCommand` is therefore two different situations -- everything
running, and nothing left that can be tried -- which is why the status line
renders the _situation_ beside the step rather than the step alone.

-}
type HarvestStep
    = SwitchThePropulsionModuleOn
    | SelectTheCloud
    | PressTheOrbitButton
    | LockTheCloud
    | WaitForTheLockToLand
    | RunTheHarvester Int
    | NothingLeftToCommand


harvestStep : HarvestSituation -> HarvestStep
harvestStep situation =
    if situation.propulsionModule == Just ModuleIsNotRunning then
        SwitchThePropulsionModuleOn

    else if not situation.shipIsOrbiting && not situation.panelShowsTheCloud && situation.counters.panelSelectUnansweredReadings < panelSelectGiveUpReadings then
        SelectTheCloud

    else if not situation.shipIsOrbiting && situation.panelShowsTheCloud && situation.orbitButtonIsOffered then
        PressTheOrbitButton

    else if situation.cloudReadsLocked then
        case situation.harvestersNotRunning of
            [] ->
                NothingLeftToCommand

            index :: _ ->
                RunTheHarvester index

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
    { propulsionModule = propulsionModuleFromShipUI shipUI |> Maybe.map moduleRunningState
    , shipIsOrbiting =
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
        SwitchThePropulsionModuleOn ->
            pressModuleHotkey context
                "The propulsion module does not read as running -- switch it on (Alt+F1)."
                propulsionModuleHotkey

        SelectTheCloud ->
            describeBranch
                ("Select '" ++ cloudName ++ "', so the Selected Item panel's own Orbit button acts on it.")
                (decideActionForCurrentStep
                    (cloud.uiNode |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault [])
                )

        PressTheOrbitButton ->
            case selectedItemPanelButton context.readingFromGameClient selectedItemOrbitButton of
                Just button ->
                    describeBranch
                        ("Orbit '" ++ cloudName ++ "' with the Selected Item panel's own button, at whatever range the client last used.")
                        (decideActionForCurrentStep
                            (button |> mouseClickOnUIElement MouseButtonLeft |> Result.withDefault [])
                        )

                Nothing ->
                    -- Unreachable: `harvestStep` only answers this where the
                    -- situation said the button was offered, and the situation
                    -- is built from the same reading. Says so rather than
                    -- pretending, because a silent wait here would be a branch
                    -- reporting nothing and doing nothing.
                    describeBranch
                        "The Orbit button left the panel between reading it and pressing it -- ask again next reading."
                        waitForProgressInGame

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

        NothingLeftToCommand ->
            describeBranch
                (describeHarvestSituation situation)
                waitForProgressInGame


{-| What the harvest loop is doing, and which of its stages it has given up on.

Printed on every reading with a cloud rather than only where something is wrong,
because the two states `NothingLeftToCommand` covers -- everything running, and
nothing left that can be tried -- are the same silence from outside, and only one
of them wants an operator.

-}
describeHarvestSituation : HarvestSituation -> String
describeHarvestSituation situation =
    let
        propulsion =
            case situation.propulsionModule of
                Nothing ->
                    "no module read in the middle row (see the client-setup list)"

                Just ModuleIsRunning ->
                    "running"

                Just ModuleIsNotRunning ->
                    "not running"

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

        harvesters =
            case situation.harvestersNotRunning of
                [] ->
                    "both cycling"

                notRunning ->
                    String.fromInt (List.length notRunning)
                        ++ " not cycling (top-row slot(s) "
                        ++ (notRunning |> List.map (\index -> String.fromInt (index + 1)) |> String.join ", ")
                        ++ ")"
    in
    "Harvest: propulsion module "
        ++ propulsion
        ++ "; "
        ++ orbit
        ++ "; cloud "
        ++ lock
        ++ "; harvesters "
        ++ harvesters
        ++ "."



-- Getting to the site


{-| The two menu entries a warp to zero takes, in both cascades this bot drives.

Two levels, measured on this client for a bookmark: the top-level entry reads
`Warp to Within (0 m)` -- carrying the client's _current default_ in those
brackets, which is why it is matched on the `to within` part and not whole --
and hovering it opens a fixed submenu of `Within 0 m | Within 10 km | ... |
Within 100 km`. A scanned anomaly's own menu takes the same two steps, which is
what lets one pair of literals drive both.

**Zero rather than a setting.** A gas site is warped into to be harvested, and
the clouds are what the ship has to be next to; every other distance in that
submenu is a distance the ship then has to close by hand, which this bot has no
command for. `retreat-bookmark-prefix`'s own fallback wants `Within 100 km` and
is #463's.

-}
warpToWithinMenuEntry : String
warpToWithinMenuEntry =
    "to within"


warpAtZeroMenuEntry : String
warpAtZeroMenuEntry =
    "Within 0 m"


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
one off. `SwitchThePropulsionModuleOn` is the only step in this file that
touches it, and it only ever switches it on.

-}
warpToTheHuntedSite : BotDecisionContext -> SiteToHunt -> DecisionPathNode
warpToTheHuntedSite context site =
    let
        warpMenu =
            useMenuEntryWithTextContaining warpToWithinMenuEntry
                (useMenuEntryWithTextContaining warpAtZeroMenuEntry menuCascadeCompleted)
    in
    case site of
        ScannedAnomaly anomaly ->
            describeBranch
                ("Warp to the scanned anomaly " ++ describeAnomalyIdentity anomaly ++ ", at zero.")
                (useContextMenuCascade ( "Scan result", anomaly.uiNode ) warpMenu context)

        BookmarkedSite bookmark ->
            describeBranch
                ("Warp to the bookmark '" ++ bookmark.mainText ++ "', at zero.")
                (useContextMenuCascade ( bookmark.mainText, bookmark.uiNode ) warpMenu context)


{-| How full the hold is, where a reading can say.

Read off whichever inventory window this reading carries a capacity gauge for.
**Nothing in this bot opens one and the client-setup list does not ask for one**,
so the ordinary answer today is that there is none -- which is said in those
words rather than reported as an empty hold. An operator watching a bot that
never deposits has to be able to tell a hold that is not filling from a hold
nobody is looking at, and #464 is what has to decide which of the two it wants:
`InvContCapacityGauge` read `0/12,500.0 m3` on the hull #456 was measured on,
and carries a transient `(12,500.0) 12,500.0/12,500.0 m3` form while a transfer
is in flight, which is a state to wait through rather than to act on.

-}
describeHoldFill : ReadingFromGameClient -> String
describeHoldFill readingFromGameClient =
    case
        readingFromGameClient.inventoryWindows
            |> List.filterMap .selectedContainerCapacityGauge
            |> List.filterMap Result.toMaybe
            |> List.head
    of
        Nothing ->
            "Hold: no inventory window with a readable capacity gauge in this reading, so nothing here knows how full it is."

        Just gauge ->
            "Hold: "
                ++ String.fromInt gauge.used
                ++ (case gauge.maximum of
                        Just maximum ->
                            "/" ++ String.fromInt maximum

                        Nothing ->
                            " (the gauge states no maximum)"
                   )
                ++ " -- nothing empties it yet, which is #464."



-- What would make this bot leave, and whether any of it is armed


{-| The two things a retreat needs: something that notices, and somewhere to go.

`attritionIsUnguarded`'s posture, adapted. That rule exists because the mission
runner's damage-window guard cannot see a ship being ground down, so a
configuration with both percentage thresholds off is uncovered while looking
fine. The same shape is worse here, because **this hull's survival plan is to
leave rather than to tank it**: there is no gauge to fall back on and no guns to
fight with, so a retreat that is not armed is not a weaker plan, it is no plan.

Read by the status line and by no decision, which is `quickMessage`'s posture
(#130) and is the right one while the thing being reported is a gap rather than
a signal.

-}
type alias RetreatCover =
    { hostileDetectionIsArmed : Bool
    , homeStructureName : Maybe String
    , retreatBookmarkPrefix : String
    }


retreatIsUnarmed : RetreatCover -> Bool
retreatIsUnarmed cover =
    not cover.hostileDetectionIsArmed || (cover.homeStructureName == Nothing)


{-| The cover clause, said on every reading.

**Reachability, since a guard that cannot fire is this repo's signature bug
(#15, #34, #42):** `hostileDetectionIsArmed` is `False` at its one call site
today because nothing in this app detects a hostile yet -- so this clause fires
on every reading of every run, which is exactly what it should do while that is
true, and it is the thing #462 flips. The other half is a real setting and is
false-able now: a run given no `home-structure-name` has one named destination
fewer, and a bookmark _prefix_ is a pattern rather than a place, so it is
deliberately not counted as a destination -- nothing here can say whether any
bookmark matches it until the Locations window is readable (#457).

-}
describeRetreatCover : RetreatCover -> String
describeRetreatCover cover =
    if retreatIsUnarmed cover then
        "RETREAT NOT ARMED: "
            ++ (if not cover.hostileDetectionIsArmed then
                    "nothing in this bot notices a hostile yet, so nothing can ever start a retreat. "

                else
                    ""
               )
            ++ (if cover.homeStructureName == Nothing then
                    "No 'home-structure-name' is set, so the only retreat destination named is the bookmark prefix '"
                        ++ cover.retreatBookmarkPrefix
                        ++ "', which is a pattern rather than a place. "

                else
                    ""
               )
            ++ "This ship's plan for anything arriving is to leave, and it cannot."

    else
        "Retreat: to a bookmark starting '"
            ++ cover.retreatBookmarkPrefix
            ++ "', else to '"
            ++ Maybe.withDefault "" cover.homeStructureName
            ++ "'."


retreatCoverFromContext : BotDecisionContext -> RetreatCover
retreatCoverFromContext context =
    { hostileDetectionIsArmed =
        -- Not a placeholder that could rot into a lie: nothing in this app
        -- reads the Directional Scanner or classifies an overview row, so
        -- there is nothing to ask. #462 is where this becomes a read, and the
        -- clause above is what an operator sees until it does.
        False
    , homeStructureName = context.eventContext.botSettings.homeStructureName
    , retreatBookmarkPrefix = context.eventContext.botSettings.retreatBookmarkPrefix
    }



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
     ]
        |> List.filterMap identity
        |> List.foldr describeBranch (gasHufferDecisionRootBeforeApplyingSettings context)
    )
        |> EveOnline.BotFrameworkSeparatingMemory.setMillisecondsToNextReadingFromGameBase
            context.eventContext.botSettings.botStepDelayMilliseconds


{-| Everything above the docked-or-in-space split, and what is deliberately not
here yet.

**There is no `endSessionOnAnExpiredBound` head, because there is no bound to
put in one.** The mission runner's #102 and saxrat's #133 both settled the shape
a give-up that _ends the session_ has to take: it is asked from the head of this
function, above the setup list, because the counter behind it advances in
`updateMemoryForNewReadingFromGame` on every reading whatever the bot is doing,
and a comparison asked only where the tree gets that far runs late by however
long something above it holds. Run 30 took one to 10,811 against a bound of 200.
Nothing here counts readings towards ending a session, so that head would be a
`Maybe.map` over nothing.

It is named rather than left out silently, because the first thing this app
grows that ends a session -- a pod recovery, or a retreat that gives up -- will
inherit the question and would otherwise inherit the wrong answer by default.
PR #115's rule is what decides it: **a give-up that ends the session bounds
elapsed time and belongs where nothing can decline to ask it; a give-up that
declines an action bounds effort and belongs where the action is.**

-}
gasHufferDecisionRootBeforeApplyingSettings : BotDecisionContext -> DecisionPathNode
gasHufferDecisionRootBeforeApplyingSettings context =
    generalSetupInUserInterface
        context.memory.messageBoxStandoff
        context.previousStepsEffects
        context.readingFromGameClient
        |> Maybe.withDefault
            (branchDependingOnDockedOrInSpace
                { ifDocked = describeBranch nothingToDoDockedYet waitForProgressInGame
                , ifSeeShipUI = huntAndHarvest context
                }
                context
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

-}
huntAndHarvest : BotDecisionContext -> EveOnline.ParseUserInterface.ShipUI -> DecisionPathNode
huntAndHarvest context shipUI =
    let
        site =
            siteSearchFromContext context

        search =
            cloudSearchFromReading context.eventContext.botSettings context.readingFromGameClient
    in
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
    "Docked. This bot has no docked behaviour yet -- depositing the hold is issue #464 -- so it is doing nothing on purpose."


{-| What the bot says on a grid with no cloud and nowhere to go.

Named rather than left as a bare wait, for the reason above: this is the state a
bot that has quietly stopped working looks like from outside, so it says which
of the two it is and where the operator should look. `describeSiteSearch` has
already said _why_ nothing is hunted on the same reading.

-}
nothingToHuntInSpace : String
nothingToHuntInSpace =
    "In space with no harvestable cloud on the overview and no site to hunt -- nothing to warp to, so it is waiting on purpose. Noticing a hostile is #462 and leaving is #463, and neither is here, so nothing about this wait is a safe place to leave a ship."


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
    in
    { readingsCount = botMemoryBefore.readingsCount + 1
    , lastDockedStationNameFromInfoPanel =
        [ currentStationNameFromInfoPanel, botMemoryBefore.lastDockedStationNameFromInfoPanel ]
            |> List.filterMap identity
            |> List.head
    , shipModules =
        botMemoryBefore.shipModules
            |> EveOnline.BotFramework.integrateCurrentReadingsIntoShipModulesMemory context.readingFromGameClient
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
            }
            botMemoryBefore.harvestCounters
    }


{-| What an operator watching a run reads on every reading.

Deliberately opens with what the bot **cannot** do, because everything else here
is a bot that looks like it is working: it warps, orbits, locks and harvests, and
a console reporting that while the ship has no way of noticing a stranger on the
grid would be a console reporting success for the half that is missing. That is
the failure this repo is named after, and the half that is missing is the one
that keeps the ship.

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
    [ "HARVESTS BUT CANNOT LEAVE: this bot warps to a gas site and harvests it, and it does not watch for anything arriving (#462), retreat (#463), deposit the hold (#464) or keep the propulsion module on across a warp (#465)."
    , describeSiteSearch (siteSearchFromContext context)
    ]
        ++ harvestClause
        ++ [ describeMiningRange context.memory.miningRangeRefusal
           , describeHoldFill context.readingFromGameClient
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
                ++ ". D-Scan every "
                ++ String.fromInt settings.dscanIntervalSeconds
                ++ "s."
           , describeHostileTrust (hostileTrustFromSettings settings)
           , describeRetreatCover (retreatCoverFromContext context)
           , "Deposit at: "
                ++ Maybe.withDefault "nowhere named ('home-structure-name' is unset)" settings.homeStructureName
                ++ "."
                ++ describeMessageBoxStandoff context.memory.messageBoxStandoff
           ]
        |> String.join "\n"
