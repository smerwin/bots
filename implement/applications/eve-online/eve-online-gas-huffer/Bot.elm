{- EVE Online gas huffer -- SCAFFOLD ONLY, it does not harvest anything yet

      This app is meant to harvest gas from a wormhole gas site, deposit it at a
      structure, and leave the moment anything else shows up on the grid. **Only
      the first step of that is here.** What is here is the app: its settings,
      the client-setup contract below, the two general-purpose recoveries every
      bot in this repo needs (the game's own Settings/pause menu, and a message
      box that will not close), and -- since #460 -- the rule that decides
      **which site this bot would hunt**, reported on every reading.

      **Nothing flies to that site yet**, which is the one thing to be clear
      about before reading further. #460 asked for the filter and for a status
      line saying why nothing is being hunted; taking the site is the harvest
      loop's, and the mechanism it should reuse is named on `siteSearch`.

      Started under issue #459; the behaviour is #460 (which site to hunt, here),
      #461 (the harvest loop), #462 (hostile detection), #463 (retreat, cloak and
      evade) and #464 (deposit the hold). Run today, this bot reads the client,
      keeps the two recoveries above armed, says which site it would hunt and why
      it would decline the rest, and does nothing else -- and it says so on every
      reading rather than looking busy.

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
        will ever tell the bot the setup is wrong.
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
        carries.
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
        , mouseClickOnUIElement
        )
import EveOnline.BotFrameworkSeparatingMemory
    exposing
        ( DecisionPathNode
        , UpdateMemoryContext
        , askForHelpToGetUnstuck
        , branchDependingOnDockedOrInSpace
        , decideActionForCurrentStep
        , ensureInfoPanelLocationInfoIsExpanded
        , waitForProgressInGame
        )
import EveOnline.ParseUserInterface


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

Deliberately small. A reading's game-log entries and quick messages are gone by
the next reading, so every verdict drawn from them has to be written here -- but
this app draws none yet, and a field nothing writes and nothing reads is #125's
shape. #461 through #464 each add what they need.

-}
type alias BotMemory =
    { readingsCount : Int
    , lastDockedStationNameFromInfoPanel : Maybe String
    , shipModules : ShipModulesMemory

    -- How long the box in front of the bot has been there, and the one line
    -- said when the bot stops answering it. See `MessageBoxStandoff`.
    , messageBoxStandoff : Maybe MessageBoxStandoff
    , messageBoxLastChange : Maybe String
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

**Nothing here flies anywhere.** #460 asked for the filter and for a status line
saying why nothing is being hunted, and that is what this is; taking the site
belongs to the harvest loop (#461). When it lands, the mechanism to reuse for
the bookmark half is `eve-online-mining-bot`'s
`useContextMenuOnLocationWithMatchingName`, which already drives a context menu
off a `LocationsWindowPlaceEntry` -- a second mechanism for that job is the kind
of thing this codebase keeps having to reconcile later.

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
            "Site: would hunt the scanned anomaly "
                ++ describeAnomalyIdentity anomaly
                ++ " (nothing warps to it yet -- that is #461)."

        Just (BookmarkedSite bookmark) ->
            "Site: nothing scanned reads "
                ++ describeAnomalyFilter search.filter
                ++ ", so falling back to the bookmark '"
                ++ bookmark.mainText
                ++ "' (nothing warps to it yet -- that is #461)."

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
    }


{-| The root, and the one place anything the memory update concluded is said.

`messageBoxLastChange` holds a message only on the reading its conclusion
changed, so this is one line per change with no separate "already reported" flag
to get wrong -- and it is said here rather than in the branch that learned it,
because the branch that learns a message box has been given up on is precisely
the branch that has just stopped running.

-}
gasHufferDecisionRoot : BotDecisionContext -> DecisionPathNode
gasHufferDecisionRoot context =
    ([ context.memory.messageBoxLastChange ]
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
                , ifSeeShipUI = \_ -> huntForASite context
                }
                context
            )


{-| Says which site it would take, and then takes none of them.

The decision line is the same sentence the status line carries, from the same
call, so the two cannot come to disagree about which site was chosen -- and it
is on the decision path rather than only in the status text because that is
where an operator reading a run looks for what the bot decided.

The wait underneath is unchanged and still says so in words. A branch that
reports nothing and does nothing is indistinguishable from a branch that is
stuck, which is `/review-silent-success` exactly; the difference here is that
the doing-nothing is deliberate and names the issue that fills it.

-}
huntForASite : BotDecisionContext -> DecisionPathNode
huntForASite context =
    describeBranch
        (describeSiteSearch (siteSearchFromContext context))
        (describeBranch nothingToDoInSpaceYet waitForProgressInGame)


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


nothingToDoInSpaceYet : String
nothingToDoInSpaceYet =
    "In space. Deciding which site to hunt is #460 and is done; nothing flies to it yet -- warping and harvesting are #461, noticing a hostile is #462, leaving is #463 -- so it is doing nothing on purpose."


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
    }


{-| What an operator watching a run reads on every reading.

Deliberately opens by saying the bot has no harvesting behaviour, because
everything else here is a bot that looks like it is working: it reads the
client, keeps two recoveries armed, and prints settings back. A console that did
not say so would be a console reporting success for a bot that does nothing,
which is the failure this repo is named after.

-}
statusTextFromState : BotDecisionContext -> String
statusTextFromState context =
    let
        settings =
            context.eventContext.botSettings
    in
    [ "SCAFFOLD ONLY: this bot decides which site to hunt and goes nowhere -- it does not warp, harvest, deposit, watch for hostiles or retreat yet (issues #461-#464)."
    , describeSiteSearch (siteSearchFromContext context)
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
