"""Mutation sweep for #464. Throwaway; not part of the suite.

Each entry names a mutation of `Bot.elm` and the case that must go red for it.
Run from `tools/macos-host/tests`. Restores `Bot.elm` with `git checkout --`
between mutations, so commit before running it.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__),
                                     "..", "..", ".."))
BOT = os.path.join(ROOT, "implement", "applications", "eve-online",
                   "eve-online-gas-huffer", "Bot.elm")
REL = os.path.relpath(BOT, ROOT)

MODULES = [
    "test_gas_huffer_deposits_the_hold",
    "test_gas_huffer_retreats_and_evades",
    "test_gas_huffer_watches_the_grid",
    "test_gas_huffer_harvests_a_cloud",
    "test_gas_huffer_scaffold",
    "test_gas_huffer_hunts_by_group",
]

MUTATIONS = [
    ("1 success read from the gauge instead of the client's line",
     [("""            if
                not answer.docked
                    && ((confirmation /= Nothing) || (answer.holdFill == HoldHasRoom))
            then""",
       """            if
                not answer.docked
                    && (answer.holdFill == HoldHasRoom)
            then""")]),
    ("1b the run ended by an empty hold while docked",
     [("""                not answer.docked
                    && ((confirmation /= Nothing) || (answer.holdFill == HoldHasRoom))""",
       """                (confirmation /= Nothing) || (answer.holdFill == HoldHasRoom)""")]),
    ("2 the transient read as a fill level",
     [("""            if gauge.selected /= Nothing then
                HoldTransferIsInFlight

            else
                case gauge.maximum of""",
       """            if False then
                HoldTransferIsInFlight

            else
                case gauge.maximum of""")]),
    ("3 the transient collapsed into HoldFillCannotBeRead",
     [("                HoldTransferIsInFlight\n",
       "                HoldFillCannotBeRead\n")]),
    ("4 the hold taken as the first inventory window",
     [("""        readingFromGameClient.inventoryWindows
            |> List.filter holdIsTheSelectedContainer
            |> List.head""",
       """        readingFromGameClient.inventoryWindows
            |> List.head""")]),
    ("5 the hold identified by its sidebar row rather than the container",
     [("""holdIsTheSelectedContainer inventoryWindow =
    selectedContainerTypeNameOfWindow inventoryWindow
        == Just miningHoldContainerTypeName""",
       """holdIsTheSelectedContainer inventoryWindow =
    inventoryTreeEntryWithText miningHoldTreeEntryText inventoryWindow /= Nothing""")]),
    ("6 the dock re-commanded every reading (step ignores the latch)",
     [("""        case situation.dockingRunIn of
            Just runIn ->
                WaitForTheDockingRunIn runIn

            Nothing ->""",
       """        case Nothing of
            Just runIn ->
                WaitForTheDockingRunIn runIn

            Nothing ->""")]),
    ("6b the run-in never latching",
     [("""    if docked then
        Nothing

    else if courseSetThisReading then""",
       """    if docked then
        Nothing

    else if False then""")]),
    ("7 the patience comparison moved by one",
     [("runIn.readingsSinceCloser + 1 < dockingRunInPatienceReadings",
       "runIn.readingsSinceCloser + 2 < dockingRunInPatienceReadings")]),
    ("8 dockingRunInPatienceReadings written as 1",
     [("""dockingRunInPatienceReadings : Int
dockingRunInPatienceReadings =
    20""",
       """dockingRunInPatienceReadings : Int
dockingRunInPatienceReadings =
    1""")]),
    ("9 a growing range counted as a gain",
     [("""                                ( Just now, Just nearestSoFar ) ->
                                    now < nearestSoFar""",
       """                                ( Just now, Just nearestSoFar ) ->
                                    now /= nearestSoFar""")]),
    ("9b an unreadable range counted as a gain",
     [("""                                ( Just _, Nothing ) ->
                                    True

                                _ ->
                                    False""",
       """                                ( Just _, Nothing ) ->
                                    True

                                _ ->
                                    True""")]),
    ("10 docking not clearing the latch",
     [("""dockingRunInAfterReading { before, courseSetThisReading, rangeNow, docked } =
    if docked then
        Nothing

    else if courseSetThisReading then""",
       """dockingRunInAfterReading { before, courseSetThisReading, rangeNow, docked } =
    if False then
        Nothing

    else if courseSetThisReading then""")]),
    ("11 the retreat placed below the deposit",
     [("""            case actOnTheEvasionStep context (evasionSituationFromContext context) of
                Just leaving ->
                    describeBranch (describeRetreatSearch (retreatSearchFromContext context))
                        (describeBranch (describeCloak (cloakSearchFromContext context)) leaving)

                Nothing ->
                    case actOnTheDepositStep context (depositSituationFromContext context) of
                        Just depositing ->
                            depositing

                        Nothing ->""",
       """            case actOnTheDepositStep context (depositSituationFromContext context) of
                Just depositing ->
                    depositing

                Nothing ->
                    case actOnTheEvasionStep context (evasionSituationFromContext context) of
                        Just leaving ->
                            describeBranch (describeRetreatSearch (retreatSearchFromContext context))
                                (describeBranch (describeCloak (cloakSearchFromContext context)) leaving)

                        Nothing ->""")]),
    ("11b the whole chain back inside the in-space arm",
     [("""                                { ifDocked = describeBranch nothingToDoDockedYet waitForProgressInGame
                                , ifSeeShipUI = huntAndHarvest context
                                }""",
       """                                { ifDocked = describeBranch nothingToDoDockedYet waitForProgressInGame
                                , ifSeeShipUI = huntAndHarvest context

                                -- moved back below the split
                                }""")],
     "skip"),
    ("12 the docked answer removed from evasionStep",
     [("""    else if situation.docked then
        StayDockedRatherThanUndockIntoIt

""", "")]),
    ("13 the docked answer declining rather than holding the tree",
     [("""        StayDockedRatherThanUndockIntoIt ->
            Just
                (describeBranch""",
       """        StayDockedRatherThanUndockIntoIt ->
            always Nothing
                (describeBranch""")]),
    ("14 the docked grid arm defaulting to clean",
     [("context.memory.lastGridVerdictInSpaceIsClean |> Maybe.withDefault False",
       "context.memory.lastGridVerdictInSpaceIsClean |> Maybe.withDefault True")]),
    ("15 the docked arm reading the live verdict",
     [("""        if context.readingFromGameClient.shipUI == Nothing then
            context.memory.lastGridVerdictInSpaceIsClean |> Maybe.withDefault False

        else
            gridReadsClean (gridVerdict (gridEvidenceFromContext context))""",
       """        gridReadsClean (gridVerdict (gridEvidenceFromContext context))""")]),
    ("16 the evasion counters no longer reset by a docked reading",
     [("    if answer.docked || answer.gridIsClean then",
       "    if answer.gridIsClean then")]),
    ("17 the scan asked of a docked reading",
     [("""    if context.readingFromGameClient.shipUI == Nothing then
        Nothing

    else if
        dscanRefreshIsDue""",
       """    if
        dscanRefreshIsDue""")]),
    ("18 one marker dropped from the confirmation",
     [("""    [ "item(s) was moved", "to your hangar" ]""",
       """    [ "to your hangar" ]""")]),
    ("19 the channel filter dropped from the confirmation",
     [("""        |> Maybe.withDefault []
        |> List.filter gameLogEntryIsFromNotifyChannel
        |> List.filter
            (\\entry ->
                depositConfirmationMarkers""",
       """        |> Maybe.withDefault []
        |> List.filter
            (\\entry ->
                depositConfirmationMarkers""")]),
    ("20 List.all weakened to List.any over the markers",
     [("""                depositConfirmationMarkers
                    |> List.all (\\marker -> stringContainsIgnoringCase marker entry.text)""",
       """                depositConfirmationMarkers
                    |> List.any (\\marker -> stringContainsIgnoringCase marker entry.text)""")]),
    ("21 depositOutOfTime's comparison moved by one",
     [("    if depositGiveUpReadings <= deposit.readings then",
       "    if depositGiveUpReadings < deposit.readings then")]),
    ("22 depositGiveUpReadings written as a bare number",
     [("""depositGiveUpReadings : Int
depositGiveUpReadings =
    dockingRunInPatienceReadings * 15""",
       """depositGiveUpReadings : Int
depositGiveUpReadings =
    300""")]),
    ("23 the give-up dropping THE HOLD IS STILL FULL",
     [(". THE HOLD IS STILL FULL. This is the end",
       ". This is the end")]),
    ("24 the deposit bound dropped from the head",
     [("""    [ evasionOutOfTime { readings = context.memory.evasion.readings }
    , depositOutOfTime
        { readings = context.memory.deposit |> Maybe.map .readings |> Maybe.withDefault 0 }
    ]""",
       """    [ evasionOutOfTime { readings = context.memory.evasion.readings }
    ]""")]),
    ("25 the deposit bound asked before the evasion's",
     [("""    [ evasionOutOfTime { readings = context.memory.evasion.readings }
    , depositOutOfTime
        { readings = context.memory.deposit |> Maybe.map .readings |> Maybe.withDefault 0 }
    ]""",
       """    [ depositOutOfTime
        { readings = context.memory.deposit |> Maybe.map .readings |> Maybe.withDefault 0 }
    , evasionOutOfTime { readings = context.memory.evasion.readings }
    ]""")]),
    ("26 the step reading the gauge live instead of the latched run",
     [("""    if not situation.runIsUnderWay then
        TheHoldDoesNotNeedDepositing""",
       """    if situation.holdFill /= HoldIsFull then
        TheHoldDoesNotNeedDepositing""")]),
    ("27 the drag tried before the dialog is answered",
     [("""        else if situation.okButtonIsOnScreen then
            ConfirmWhateverDialogIsOnScreen

        else if not situation.inventoryListsTheHold then""",
       """        else if not situation.inventoryListsTheHold then""")],
     "needs-tail"),
    ("28 the panel pressed without selecting the structure first",
     [("""                else if not situation.panelShowsTheHomeStructure then
                    SelectTheHomeStructure

                else if situation.dockButtonIsOffered then""",
       """                else if situation.dockButtonIsOffered then""")]),
    ("29 the warp taken while the Dock button is offered",
     [("""                else if situation.dockButtonIsOffered then
                    PressTheDockButton

                else
                    WarpToTheHomeStructure""",
       """                else if situation.dockButtonIsOffered then
                    WarpToTheHomeStructure

                else
                    PressTheDockButton""")]),
    ("30 unlessJustClicked dropped from the drag",
     [("""                        (unlessJustClicked
                            "Drag the Mining Hold's contents into the structure's item hangar"
                            (describeBranch""",
       """                        (identity
                            (describeBranch""")]),
    ("31 stepDraggedSomething answering True for an ordinary click",
     [("""                    EffectOnWindow.MouseMoveTo _ ->
                        ( holding, dragged || holding )""",
       """                    EffectOnWindow.MouseMoveTo _ ->
                        ( holding, True )""")]),
    ("32 the undock reading the label rather than the parser's two fields",
     [("""            case ( stationWindow.undockButton, stationWindow.abortUndockButton ) of
                ( Just undockButton, Nothing ) ->""",
       """            case ( stationWindow.undockButton, Nothing ) of
                ( Just undockButton, Nothing ) ->""")],
     "skip"),
    ("33 the OK arm claiming the click is evidence",
     [("Whether it is the transfer's confirmation or the client's refusal of it, this click says nothing about either: what says the deposit landed is the client's own '(notify) ... item(s) was moved to your hangar' line and nothing else.",
       "That is the transfer confirmed.")]),
    ("34 a dead end left as a bare wait",
     [("""                    ("Docked with a full hold and no '"
                        ++ structureHangarTreeEntryText
                        ++ "' row in the inventory to drop it into -- this structure may offer no hangar to this character, which is not something this bot can fix. The session ends at the deposit bound."
                    )""",
       '                    "Waiting."')]),
    ("35 a second copy of the home-structure rule in the deposit",
     [("""        homeStructureRow =
            homeStructureRowsOnTheOverview
                context.eventContext.botSettings.homeStructureName
                (readingFromGameClient.overviewWindows |> List.concatMap .entries)
                |> List.head
    in
    { runIsUnderWay = context.memory.deposit /= Nothing""",
       """        homeStructureRow =
            readingFromGameClient.overviewWindows
                |> List.concatMap .entries
                |> List.filter
                    (\\entry ->
                        entry.objectName
                            |> Maybe.map
                                (\\objectName ->
                                    context.eventContext.botSettings.homeStructureName
                                        |> Maybe.map (siteCellMatches objectName)
                                        |> Maybe.withDefault False
                                )
                            |> Maybe.withDefault False
                    )
                |> List.head
    in
    { runIsUnderWay = context.memory.deposit /= Nothing""")]),
    ("36 the _display filter dropped from the home-structure rule",
     [("""            overviewEntries
                |> List.filter overviewEntryIsDisplayed
                |> List.filter
                    (\\entry ->
                        entry.objectName
                            |> Maybe.map (\\objectName -> siteCellMatches objectName name)""",
       """            overviewEntries
                |> List.filter
                    (\\entry ->
                        entry.objectName
                            |> Maybe.map (\\objectName -> siteCellMatches objectName name)""")]),
    ("37 selectedItemDockButton pointed at the warp button",
     [("""    { elementId = "selectedItemDock", cmdName = "CmdDockAtItem" }""",
       """    { elementId = "selectedItemWarpTo", cmdName = "CmdWarpToItem" }""")]),
    ("37b the cmdName dropped so only the id matches",
     [("""    { elementId = "selectedItemDock", cmdName = "CmdDockAtItem" }""",
       """    { elementId = "selectedItemDock", cmdName = "selectedItemDock" }""")]),
    ("38 describeDeposit printing the count without the bound",
     [("""                        ++ String.fromInt deposit.readings
                        ++ "/"
                        ++ String.fromInt depositGiveUpReadings
                        ++ " readings and the session ends at that bound""",
       """                        ++ String.fromInt deposit.readings
                        ++ " readings and the session ends at the bound""")]),
    ("39 the unreadable hold reported as a number",
     [("""                HoldFillCannotBeRead ->
                    "NOT READABLE -- no inventory window in this reading has the ship's Mining Hold selected, so nothing here knows how full it is and nothing will ever decide to deposit. Open the inventory on the Mining Hold\"""",
       """                HoldFillCannotBeRead ->
                    "0/0\"""")]),
    ("40 the client-setup bullet removed from the header",
     [("      + **Leave the inventory open with the ship's Mining Hold selected.**",
       "      + Leave whatever windows you like open.")]),
]


def run_tests():
    proc = subprocess.run(
        [sys.executable, "-m", "unittest"] + MODULES,
        cwd=os.path.dirname(__file__),
        env=dict(os.environ, NO_COLOR="1"),
        capture_output=True, text=True)
    return proc.returncode, proc.stderr


def failing_names(stderr):
    return sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)",
                                 stderr, re.MULTILINE)))


def main():
    only = sys.argv[1:]
    for entry in MUTATIONS:
        name, edits = entry[0], entry[1]
        if only and not any(name.startswith(prefix) for prefix in only):
            continue
        with open(BOT, encoding="utf-8") as handle:
            source = handle.read()
        mutated = source
        applied = True
        for old, new in edits:
            if old not in mutated:
                print("%-70s COULD NOT APPLY" % name)
                applied = False
                break
            mutated = mutated.replace(old, new, 1)
        if not applied:
            continue
        with open(BOT, "w", encoding="utf-8") as handle:
            handle.write(mutated)
        code, stderr = run_tests()
        subprocess.run(["git", "checkout", "--", REL], cwd=ROOT, check=True)
        if code == 0:
            print("%-70s SURVIVED" % name)
        else:
            names = failing_names(stderr)
            if not names:
                print("%-70s DID NOT COMPILE / no named case" % name)
            else:
                print("%-70s killed by %d case(s): %s" % (
                    name, len(names),
                    ", ".join("%s.%s" % (cls.split(".")[-1], case)
                              for case, cls in names[:4])))


if __name__ == "__main__":
    main()
