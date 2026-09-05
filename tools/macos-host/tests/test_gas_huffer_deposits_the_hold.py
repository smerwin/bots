"""The gas huffer's deposit: home, dock, drag, and the client's own word for it.

Issue #464, under #456. #461 gave this bot a hold to fill and nothing that
empties one, so a full hold was a session that went on harvesting nothing. This
is the emptying, and four things about it are what the issue is emphatic about.

**The hold is a Mining Hold on the measured hull, not a generic cargo hold.**
`readingFromGameClient.inventoryWindows` is a list and each window's capacity
gauge belongs to whichever container *that* window has selected, so a rule taking
the first gauge it finds reads a number about some other container and then
deposits, or declines to, on the strength of it. Every gauge case here is asked
of a reading carrying two inventory windows, only one of which is the hold.

**The parenthesised gauge form is a transient shown while a transfer is in
flight, and it is not a fill level.** All three measured forms go through the
real `parseInventoryCapacityGaugeText` here, and the transient is asked for on
its own: read as a level it says *full*, which is true of the reading and is
exactly the wrong thing to act on, because a transfer already going would then
be answered by dragging again.

**The deposit is confirmed from the client's own `(notify)` line, never from the
gauge.** A gauge reading zero because the drag silently moved nothing and a
gauge reading zero because the deposit worked are the same reading, which is the
distinction #19 cost the standalone restock tool. So the matcher is asked about
the real recorded line, about a `(notify)` line that is not it, and about the
same words on a channel the bot does not read -- and the run is folded over a
session where the hold reads empty while docked and the client has said nothing,
which must not end it.

**The docking run-in is commanded once and waited on by the range falling.**
`eve-online-mission-runner`'s `DockingRunIn`, which #464 names: that bot's run 27
commanded Dock on 120 of 121 readings between two accepted course-settings, 486
seconds apart, and left a ship 17 km off a station for eight minutes. The rule is
folded over sessions here rather than asked once, because a rule that is right
for one reading and wrong across a session is the defect the shape prevents.

**And the ordering, which inverting compiles.** The retreat outranks the
deposit, above the docked-or-in-space split, so a grid that stops reading clean
takes the ship out of a docking run-in and keeps a docked ship docked rather than
undocking a full one into somebody else's grid to finish an errand.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`. Every inventory
window, sidebar row, capacity gauge, overview row, game-log entry, Selected Item
panel and station window they are asked about is built by running a UI tree
through the **real** `EveOnline.ParseUserInterface`, so what the cases assert on
is what the bot would have been handed. Where a case is about a combination no
single fixture can be in at once -- docked, with the transfer confirmed, and the
hold not selected -- the rule is handed the record it takes, which is why
`depositStep` takes one.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically from
outside, which is the shape `prerequisites.elm_json_literal` exists for.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs. Every
name in it is fictional, which is #456's rule.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import os
import re
import unittest

from prerequisites import ElmRepl, elm_json_literal, open_repl
from test_gas_huffer_scaffold import (
    GAS_HUFFER_DIR, bot_source, collapsed, node, top_level_declarations)

PREAMBLE = (
    "import Bot exposing (..)",
    "import Common.EffectOnWindow as EffectOnWindow",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
)

# The overview's own header row on this client, read off it on 2026-09-04 and
# quoted in #456.
OVERVIEW_COLUMNS = (
    ("Icon", 0, 40),
    ("Type", 40, 200),
    ("Name", 240, 200),
    ("Distance", 440, 120),
)

# Obviously fictional, which is #456's rule: nothing naming a real structure,
# system, corporation or character goes in this repository.
FICTIONAL_STRUCTURE = "Fictional IX - Example Refinery"
FICTIONAL_SYSTEM = "J000000"

# The three forms `InvContCapacityGauge` was measured in, quoted in #456 and
# #464. The third is the transient: the bracketed number is what
# `parseInventoryCapacityGaugeText` puts in `selected`, and the pair either side
# of the slash is what it puts in `used` and `maximum` -- so a rule looking at
# only those two reads it as full.
GAUGE_EMPTY = "0/12,500.0 m³"
GAUGE_FULL = "12,500.0/12,500.0 m³"
GAUGE_TRANSIENT = "(12,500.0) 12,500.0/12,500.0 m³"

# The client's own confirmation, as #464 records it. The count, the system and
# the structure are all inside the sentence, which is why the matcher is two
# substrings rather than the whole line.
CONFIRMATION_LINE = (
    "8 item(s) was moved to your hangar in %s - %s"
    % (FICTIONAL_SYSTEM, FICTIONAL_STRUCTURE))

# A `(notify)` line that is not it. The client writes this one about the
# harvesters and this file's own `miningRangeRefusalFromGameLog` reads it, so it
# is a sentence the bot really meets on the same channel on the same readings.
ANOTHER_NOTIFY_LINE = (
    "Gas Cloud Harvester I deactivates without transfering ore to your cargo"
    " hold because your ship has strayed to a distance of 1628.94 m, beyond its"
    " mining range of 1500.00 m.")

# The near miss: a sentence about a hangar that moved no items. One marker takes
# it and two do not.
A_SENTENCE_ABOUT_A_HANGAR = (
    "Your ship was moved to your hangar in %s - %s"
    % (FICTIONAL_SYSTEM, FICTIONAL_STRUCTURE))

COURSE_SET_LINE = "Setting course to docking perimeter"

_address = iter(range(2300000, 2999999))


def fresh_node(type_name, entries=None, children=(), region=None):
    return node(type_name, entries, children, region)


def label(text, region):
    return fresh_node("EveLabelMedium", {"_setText": text}, region=region)


# -- the inventory -----------------------------------------------------------


def capacity_gauge(text):
    """`InvContCapacityGauge`, carrying the gauge's own words.

    `parseInventoryWindow` finds the gauge by its type name containing
    `CapacityGauge` and then takes the **longest** display text under it, so the
    text has to sit on a descendant rather than on the gauge node itself for the
    fixture to be the shape the client draws.
    """
    return fresh_node("InvContCapacityGauge", {"_name": "capacityGauge"},
                      [label(text, (0, 0, 200, 14))],
                      region=(300, 60, 200, 14))


def tree_entry(text, top, children=()):
    """One sidebar row, in the shape `parseInventoryWindowTreeViewEntry` wants.

    The row's text is the topmost `topCont_` under it, so a child row nested
    inside a parent has to be drawn below it -- which is what the client does and
    what makes `Mining Hold` a child of the ship rather than a row beside it.
    """
    return fresh_node(
        "TreeViewEntryInventory", {"_name": "treeEntry"},
        [
            fresh_node("Container", {"_name": "topCont_" + text},
                       [label(text, (4, 2, 200, 16))],
                       region=(0, 0, 220, 20)),
        ] + list(children),
        region=(0, top, 220, 20 + 20 * len(children)))


def item(name, index=0):
    """One rendered item in the container's own items view."""
    return fresh_node("InvItem", {"_name": "invItem"},
                      [label(name, (2, 30, 60, 12))],
                      region=(index * 70, 0, 64, 64))


def inventory_window(tree_rows, gauge=None, selected_type=None, items=(),
                     window_type="InventoryPrimary", left=600):
    """One inventory window, with a sidebar, a selected container and a gauge.

    The selected container is the node `parseInventoryWindow` looks for under a
    `Container` whose `_name` carries `right`, and its **type name** is what
    `holdIsTheSelectedContainer` reads -- which is the whole of why a window can
    list the hold in its sidebar while showing something else on the right.
    """
    right_children = []
    if gauge is not None:
        right_children.append(capacity_gauge(gauge))
    if selected_type is not None:
        right_children.append(
            fresh_node(selected_type, {"_name": "selectedContainer"},
                       [item(name, index)
                        for index, name in enumerate(items)],
                       region=(0, 80, 400, 300)))
    return fresh_node(
        window_type, {"_name": "inventory"},
        [
            fresh_node("Container", {"_name": "leftSide"},
                       [tree_entry(text, index * 60, children)
                        for index, (text, children) in enumerate(tree_rows)],
                       region=(0, 40, 240, 400)),
            fresh_node("Container", {"_name": "rightSide"}, right_children,
                       region=(240, 40, 420, 400)),
        ],
        region=(left, 200, 660, 440))


def ship_inventory(gauge=GAUGE_EMPTY, selected="ShipGeneralMiningHold",
                   items=("Fullerite-C84",), docked=False):
    """The window the deposit works in, undocked or docked.

    Docked it also lists the structure's own hangar, which is the drop target and
    is absent from every reading taken in space -- so the two fixtures differ in
    exactly the way the client's own tree does.
    """
    rows = [("Example Hull", [tree_entry("Mining Hold", 20)])]
    if docked:
        rows.append((FICTIONAL_STRUCTURE, [tree_entry("Item Hangar", 20)]))
    return inventory_window(rows, gauge=gauge, selected_type=selected,
                            items=items)


def other_inventory(gauge="1/400.0 m³"):
    """A second window showing something that is not the hold.

    Drawn *first*, so a rule taking `List.head` of the windows -- or the first
    capacity gauge in the reading -- reads this one. That is the mistake #464
    names, and every gauge case below carries this window beside the hold's.
    """
    return inventory_window([("Example Hull", [tree_entry("Cargo Hold", 20)])],
                            gauge=gauge, selected_type="ShipCargo",
                            items=("Something Else",),
                            window_type="ActiveShipCargo", left=100)


# -- the overview, the panel, the station window and the game log ------------


def overview_row(cells, top, displayed=True):
    children = [
        fresh_node("SpaceObjectIcon", {"_name": "mainIcon"}, [],
                   region=(0, top, 32, 16)),
    ] + [
        label(cells[column], (x + 4, top, width - 8, 16))
        for column, x, width in OVERVIEW_COLUMNS if column in cells
    ]
    entries = {"_name": "overviewEntry"}
    if not displayed:
        entries["_display"] = False
    return fresh_node("OverviewScrollEntry", entries, children,
                      region=(0, top, 560, 16))


def overview_window(rows):
    headers = fresh_node("OverviewHeaders", {"_name": "headers"}, [
        label(column, (x, 60, width, 16))
        for column, x, width in OVERVIEW_COLUMNS
    ], region=(0, 60, 560, 16))
    scroll = fresh_node("OverviewScroll", {"_name": "scroll"}, [headers],
                        region=(0, 60, 560, 16))
    return fresh_node("OverviewWindow", {"_name": "overview"},
                      [scroll] + list(rows), region=(1200, 40, 560, 400))


def structure_row(name=FICTIONAL_STRUCTURE, distance="84 km", top=100,
                  displayed=True):
    return overview_row(
        {"Icon": "-", "Type": "Example Citadel", "Name": name,
         "Distance": distance}, top, displayed)


def selected_item_window(name, dock_button=True, by_cmd_name=False):
    """The Selected Item panel, with or without the Dock button.

    Its absence is what says the structure is out of docking range, which is the
    natural gate between the panel press and the warp -- the same shape
    `dockAtDestinationStation` uses in the mission runner.
    """
    children = [label(name, (10, 500, 200, 16))]
    if dock_button:
        entries = ({"cmdName": "CmdDockAtItem"} if by_cmd_name
                   else {"_name": "selectedItemDock"})
        children.append(fresh_node("ButtonIcon", entries, region=(20, 530, 32, 32)))
    return fresh_node("SelectedItemWnd", {"_name": "selectedItem"}, children,
                      region=(0, 480, 300, 120))


def station_window(label_text="Undock"):
    """`LobbyWnd`, with the one button that carries three labels in turn.

    `Undock` while docked, then `Abort Undock`, then `Undocking...` -- and the
    vendored parser answers the last two by leaving `undockButton` empty, which
    is what stops a press cancelling the undock already under way.
    """
    return fresh_node("LobbyWnd", {"_name": "lobby"}, [
        fresh_node("UndockButton", {"_name": "undockButton"},
                   [label(label_text, (4, 4, 120, 16))],
                   region=(40, 700, 120, 30)),
    ], region=(0, 660, 400, 100))


def game_log(lines):
    """The host's own synthetic node, as `botlab_host.py` appends it.

    A direct child of the root and carrying **no display region**, which is what
    keeps it invisible to every other parser in that module -- and what makes a
    fixture that got the shape wrong read as a host with no game log at all,
    which is `Nothing` rather than an empty list.
    """
    return {
        "pythonObjectAddress": str(next(_address)),
        "pythonObjectTypeName": "MacOsHostSyntheticGameLog",
        "dictEntriesOfInterest": {},
        "children": [
            {
                "pythonObjectAddress": str(next(_address)),
                "pythonObjectTypeName": "MacOsHostSyntheticGameLogEntry",
                "dictEntriesOfInterest": {
                    "timestamp": "2026.09.04 18:11:02",
                    "channel": channel,
                    "text": text,
                },
                "children": [],
            }
            for channel, text in lines
        ],
    }


def ok_dialog(label_text="OK"):
    """A dialog carrying one OK, which is what both the confirmation and the
    refusal look like."""
    return fresh_node("FormWnd", {"_name": "dialog"}, [
        label("Move 8 items?", (10, 10, 200, 16)),
        fresh_node("ButtonWrapper", {"_name": "okButton"},
                   [label(label_text, (4, 4, 40, 16))],
                   region=(60, 60, 60, 24)),
    ], region=(700, 400, 200, 100))


# -- the readings ------------------------------------------------------------


def tree_with(children):
    return fresh_node("UIRoot", {}, children, region=(0, 0, 1920, 1080))


def reading_binding(name, children):
    """A `let` binding of `name` to a real parsed reading."""
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree" % (
                name, elm_json_literal(tree_with(children))))


def deposit_run(readings=1, confirmation=None, drags=0):
    return "{ readings = %d, confirmation = %s, drags = %d }" % (
        readings,
        "Nothing" if confirmation is None else "(Just %s)"
        % json.dumps(confirmation),
        drags)


def run_in(range_meters=None, since_closer=0, dock_commands=1):
    return ("{ rangeToTheStructureMeters = %s, readingsSinceCloser = %d"
            ", dockCommands = %d }" % (
                "Nothing" if range_meters is None else "(Just %d)"
                % range_meters,
                since_closer, dock_commands))


def situation(under_way=True, docked=False, hold="HoldIsFull",
              confirmed=False, warping=False, docking_run_in="Nothing",
              structure_on_overview=True, panel_shows=True,
              dock_offered=False, lists_hold=True, hold_selected=True,
              hangar_in_inventory=True, items=1, ok_on_screen=False):
    """A `DepositSituation` written out, since it is a record of plain facts.

    Written here rather than derived from a reading on purpose: these cases are
    about the *combination*, including several no single fixture can be in at
    once -- docked, with the transfer confirmed, and the hold not selected --
    and `depositStep` takes the record precisely so they can be asked for
    directly. Every field that a reading *can* answer is separately executed
    off a real one in `TheFixturesReachTheParserTest` and the classes under it.
    """
    def flag(value):
        return "True" if value else "False"

    return ("{ runIsUnderWay = %s"
            ", docked = %s"
            ", holdFill = %s"
            ", confirmedByClient = %s"
            ", shipIsWarping = %s"
            ", dockingRunIn = %s"
            ", homeStructureIsOnTheOverview = %s"
            ", panelShowsTheHomeStructure = %s"
            ", dockButtonIsOffered = %s"
            ", inventoryListsTheHold = %s"
            ", holdIsTheSelectedContainer = %s"
            ", structureHangarIsInTheInventory = %s"
            ", itemsInTheHold = %d"
            ", okButtonIsOnScreen = %s }" % (
                flag(under_way), flag(docked), hold, flag(confirmed),
                flag(warping), docking_run_in, flag(structure_on_overview),
                flag(panel_shows), flag(dock_offered), flag(lists_hold),
                flag(hold_selected), flag(hangar_in_inventory), items,
                flag(ok_on_screen)))


def evasion_situation(clean=False, docked=False):
    """An `EvasionSituation` in the one shape this file asks about.

    #463's own file exercises the rest of it; what is asked here is the clause
    #464 added -- a docked ship, and whether the grid it would undock into read
    clean the last time anything looked at it from space. Everything else is
    left in the state that would otherwise send the ship somewhere, so a rule
    that stopped answering the docked case would fall through to a cloak or a
    celestial warp rather than to nothing.
    """
    return ("{ gridIsClean = %s"
            ", docked = %s"
            ", stillOnTheHarvestSite = True"
            ", shipIsWarping = False"
            ", destination = Nothing"
            ", cloak = (TheCloakIsFittedAndNotRunning 2)"
            ", celestialsOnTheOverview = 3"
            ", celestialRotation = 0"
            ", counters = { readings = 0, warpUnexecutedReadings = 0"
            ", longestWarpUnexecutedReadings = 0"
            ", cloakUnansweredReadings = 0 } }" % (
                "True" if clean else "False",
                "True" if docked else "False"))


# The arms of `actOnTheDepositStep`, in the order the `case` writes them, so a
# case can slice one arm out of the collapsed body. Slicing by the next arm's
# name rather than by the next `->` is what makes it a reader rather than a
# guess: every arm here contains a lambda or a `case` of its own.
DEPOSIT_ARMS = (
    "TheHoldDoesNotNeedDepositing",
    "WaitThroughTheTransfer",
    "ReSelectTheHoldBeforeUndocking",
    "Undock",
    "ConfirmWhateverDialogIsOnScreen",
    "NoInventoryListingTheHold",
    "NoStructureHangarInTheInventory",
    "SelectTheHold",
    "TheHoldShowsNothingToMove",
    "DragTheHoldIntoTheStructureHangar",
    "WaitForTheWarpToLand",
    "WaitForTheDockingRunIn",
    "NowhereToDepositAt",
    "SelectTheHomeStructure",
    "PressTheDockButton",
    "WarpToTheHomeStructure",
)


def _arm_start(body, name, after=0):
    """Where an arm begins, allowing for the payload some of them bind."""
    match = re.compile(r"\b%s( \w+)? ->" % re.escape(name)).search(body, after)
    if match is None:
        raise AssertionError("no arm named %s in the deposit's `case`" % name)
    return match.start()


def deposit_arm(body, name):
    """One arm of `actOnTheDepositStep`, out of its collapsed body.

    A missing name must never read as "nothing matched": that is the shape that
    makes a structural case pass having checked nothing.
    """
    index = DEPOSIT_ARMS.index(name)
    start = _arm_start(body, name)
    if index + 1 < len(DEPOSIT_ARMS):
        return body[start:_arm_start(body, DEPOSIT_ARMS[index + 1], start + 1)]
    return body[start:]


class DepositRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-deposit-repl-")
        kwargs.setdefault("app_dir", GAS_HUFFER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    def rendered(self, expressions, definitions=()):
        """Each answer rendered whole, constructor and payload.

        `Debug.toString` rather than a battery of equalities: one answer per
        question that names *which* constructor the rule gave and what it
        carried, so a rule answering the right constructor with the wrong
        payload fails rather than passing on whichever equality a case asked.
        """
        return self.strings(["Debug.toString (%s)" % expression
                             for expression in expressions],
                            definitions=list(definitions))


def repl():
    return open_repl(DepositRepl)


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a window, that it is there.

    Nearly every case below is of the form "the hold read full" or "the client
    said so", and a fixture that never decoded produces a reading with no
    inventory, no game log and no panel -- which answers `HoldFillCannotBeRead`
    and `Nothing` for the right-looking reason, silently and for the wrong one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_both_inventory_windows_come_back_with_their_gauges(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.inventoryWindows"
            " >> List.map (\\w -> ( selectedContainerTypeNameOfWindow w"
            " , w.selectedContainerCapacityGauge"
            " |> Maybe.andThen Result.toMaybe"
            " |> Maybe.map (\\g -> ( g.used, g.maximum, g.selected )) )))"
        ], definitions=[reading_binding("reading", [
            other_inventory(), ship_inventory(gauge=GAUGE_FULL)])])[0]
        self.assertEqual(
            printed,
            'Just [(Just "ShipCargo",Just (1,Just 400,Nothing)),'
            '(Just "ShipGeneralMiningHold",Just (12500,Just 12500,Nothing))]')

    def test_the_sidebar_rows_come_back_nested_the_way_the_client_draws_them(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.inventoryWindows"
            " >> List.concatMap .leftTreeEntries"
            " >> List.map (\\e -> ( e.text"
            " , e.children |> List.map (EveOnline.ParseUserInterface"
            ".unwrapInventoryWindowLeftTreeEntryChild >> .text) )))"
        ], definitions=[reading_binding(
            "reading", [ship_inventory(docked=True)])])[0]
        self.assertEqual(
            printed,
            'Just [("Example Hull",["Mining Hold"]),("%s",["Item Hangar"])]'
            % FICTIONAL_STRUCTURE)

    def test_the_hold_renders_an_item_to_take_hold_of(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.inventoryWindows"
            " >> List.map (inventoryItemsInView >> List.length))"
        ], definitions=[reading_binding("reading", [
            ship_inventory(items=("Fullerite-C84", "Fullerite-C50"))])])[0]
        self.assertEqual(printed, "Just [2]")

    def test_the_game_log_entries_come_back_with_their_channel(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.gameLogEntriesSinceLastReading"
            " >> Maybe.map (List.map (\\e -> ( e.channel, e.text ))))"
        ], definitions=[reading_binding("reading", [
            game_log([("notify", CONFIRMATION_LINE)])])])[0]
        self.assertEqual(
            printed,
            'Just (Just [(Just "notify",%s)])' % json.dumps(CONFIRMATION_LINE))

    def test_the_panel_the_station_window_and_the_overview_come_back(self):
        panel, undock, rows = self.repl.rendered([
            "reading |> Maybe.map (\\r ->"
            " selectedItemPanelButton r selectedItemDockButton /= Nothing)",
            "reading |> Maybe.map (.stationWindow"
            " >> Maybe.map (\\w -> ( w.undockButton /= Nothing"
            " , w.abortUndockButton /= Nothing )))",
            "reading |> Maybe.map (.overviewWindows"
            " >> List.concatMap .entries"
            " >> List.map (\\e -> ( e.objectName, e.objectDistanceInMeters )))",
        ], definitions=[reading_binding("reading", [
            selected_item_window(FICTIONAL_STRUCTURE),
            station_window(),
            overview_window([structure_row(distance="4,200 m")]),
        ])])
        self.assertEqual(panel, "Just True")
        self.assertEqual(undock, "Just (Just (True,False))")
        self.assertEqual(rows, 'Just [(Just "%s",Ok 4200)]'
                         % FICTIONAL_STRUCTURE)

    def test_a_dialog_with_an_ok_is_found_and_a_reading_without_one_is_not(self):
        with_ok, without = self.repl.rendered([
            "withDialog |> Maybe.map (okButtonInReading >> (/=) Nothing)",
            "withoutDialog |> Maybe.map (okButtonInReading >> (/=) Nothing)",
        ], definitions=[
            reading_binding("withDialog", [ok_dialog()]),
            reading_binding("withoutDialog", [ship_inventory()]),
        ])
        self.assertEqual(with_ok, "Just True")
        self.assertEqual(without, "Just False")


class TheGaugeIsReadInAllThreeMeasuredFormsTest(unittest.TestCase):
    """`InvContCapacityGauge`, in the three forms #456 measured plus the one
    every unset reading gives.

    The forms go through the **real** `parseInventoryCapacityGaugeText`, so what
    the rule is handed is what the parser makes of the client's own words rather
    than a record shaped by hand -- which is what makes the transient a
    measurement here rather than an assertion about a field.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fill(self, gauge_text):
        return self.repl.rendered([
            "EveOnline.ParseUserInterface.parseInventoryCapacityGaugeText %s"
            " |> Result.toMaybe |> holdFillFromCapacityGauge"
            % json.dumps(gauge_text, ensure_ascii=False)])[0]

    def test_the_empty_form_reads_as_having_room(self):
        self.assertEqual(self.fill(GAUGE_EMPTY), "HoldHasRoom")

    def test_the_full_form_reads_as_full(self):
        self.assertEqual(self.fill(GAUGE_FULL), "HoldIsFull")

    def test_the_transient_is_its_own_answer_and_not_a_fill_level(self):
        """The clause the whole design turns on.

        Read as a level the transient says *full*, which is true of the reading
        and is the wrong thing to act on: a transfer already in flight would be
        answered by dragging again. So it is asked above the used-against-maximum
        comparison, and the case beside it is what makes that discriminating --
        the same numbers without the bracket read `HoldIsFull`.
        """
        self.assertEqual(self.fill(GAUGE_TRANSIENT), "HoldTransferIsInFlight")
        self.assertEqual(self.fill(GAUGE_FULL), "HoldIsFull")

    def test_the_parser_really_separates_the_two_full_forms(self):
        """And it separates them in the field the rule reads.

        Without this the case above passes for a rule keyed on anything at all
        that happens to differ between the two strings.
        """
        printed = self.repl.rendered([
            "[ %s, %s ] |> List.map (EveOnline.ParseUserInterface"
            ".parseInventoryCapacityGaugeText >> Result.toMaybe"
            " >> Maybe.map (\\g -> ( g.used, g.maximum, g.selected )))"
            % (json.dumps(GAUGE_FULL, ensure_ascii=False),
               json.dumps(GAUGE_TRANSIENT, ensure_ascii=False))])[0]
        self.assertEqual(
            printed,
            "[Just (12500,Just 12500,Nothing),"
            "Just (12500,Just 12500,Just 12500)]")

    def test_a_gauge_with_no_maximum_cannot_be_read(self):
        """`parseInventoryCapacityGaugeText` answers a maximum of `Nothing` for a
        text with no slash in it, and a fill this bot cannot compute is one it
        never acts on."""
        self.assertEqual(self.fill("500.0 m³"), "HoldFillCannotBeRead")

    def test_an_unreadable_hold_is_never_read_as_full(self):
        """The fail direction, chosen rather than inherited.

        An unreadable hold means this bot never decides to deposit, which is the
        behaviour it had before #464 and which the status line shouts on every
        reading. The other direction would fly the ship home on every session
        whose inventory nobody set up.
        """
        for gauge_text in ("", "not a gauge at all", "m³"):
            with self.subTest(gauge_text):
                self.assertNotEqual(self.fill(gauge_text), "HoldIsFull")

    def test_the_boundary_between_room_and_full_is_where_it_says_it_is(self):
        printed = self.repl.rendered([
            "[ { used = 12499, maximum = Just 12500, selected = Nothing }"
            " , { used = 12500, maximum = Just 12500, selected = Nothing }"
            " , { used = 12501, maximum = Just 12500, selected = Nothing }"
            " ] |> List.map (Just >> holdFillFromCapacityGauge)"])[0]
        self.assertEqual(printed, "[HoldHasRoom,HoldIsFull,HoldIsFull]")


class TheHoldIsFoundByNameRatherThanTakenFirstTest(unittest.TestCase):
    """A Mining Hold, not whichever container the client drew first.

    Each window's capacity gauge belongs to whatever *that* window has selected,
    so a rule taking the first gauge in the reading reads a number about some
    other container. Every reading here carries two windows and the wrong one is
    drawn first.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fill(self, children):
        return self.repl.rendered([
            "reading |> Maybe.map holdFillFromReading"
        ], definitions=[reading_binding("reading", children)])[0]

    def test_the_hold_is_read_past_a_window_showing_something_else(self):
        self.assertEqual(
            self.fill([other_inventory(), ship_inventory(gauge=GAUGE_FULL)]),
            "Just HoldIsFull")

    def test_the_first_window_alone_would_have_answered_differently(self):
        """What makes the case above discriminating rather than lucky: the
        window drawn first has a gauge, it parses, and it says something else."""
        printed = self.repl.rendered([
            "reading |> Maybe.map (.inventoryWindows >> List.head"
            " >> Maybe.andThen .selectedContainerCapacityGauge"
            " >> Maybe.andThen Result.toMaybe >> Just"
            " >> Maybe.andThen identity >> Just"
            " >> Maybe.map holdFillFromCapacityGauge)"
        ], definitions=[reading_binding("reading", [
            other_inventory(), ship_inventory(gauge=GAUGE_FULL)])])[0]
        self.assertEqual(printed, "Just (Just HoldHasRoom)")

    def test_a_window_listing_the_hold_but_showing_the_hangar_says_nothing(self):
        """The state the drag happens in.

        The sidebar lists the Mining Hold and the right-hand side is the
        structure's hangar, so the gauge on screen is the hangar's. A rule that
        read it would take the structure's fill for the ship's.
        """
        self.assertEqual(
            self.fill([ship_inventory(gauge="4,000/1,000,000.0 m³",
                                      selected="StructureItemHangar",
                                      docked=True)]),
            "Just HoldFillCannotBeRead")

    def test_the_sidebar_row_is_found_by_name_at_any_depth(self):
        """`Mining Hold` hangs off the ship's own row rather than sitting beside
        it, so a search over the sidebar's roots alone finds neither it nor the
        structure's hangar."""
        printed = self.repl.rendered([
            "reading |> Maybe.map (depositInventoryFromReading"
            " >> Maybe.map (\\i -> ( i.holdTreeEntry.text"
            " , i.structureHangarTreeEntry |> Maybe.map .text )))"
        ], definitions=[reading_binding(
            "reading", [ship_inventory(docked=True)])])[0]
        self.assertEqual(printed,
                         'Just (Just ("Mining Hold",Just "Item Hangar"))')

    def test_a_window_with_no_mining_hold_row_is_not_the_deposit_window(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (depositInventoryFromReading >> (/=) Nothing)"
        ], definitions=[reading_binding("reading", [other_inventory()])])[0]
        self.assertEqual(printed, "Just False")

    def test_the_structure_hangar_row_is_absent_from_an_undocked_reading(self):
        """Which is why it is a `Maybe` at the call site rather than something
        asserted: an undocked ship has no structure's hangar in its inventory,
        and a docked reading that has none says so rather than dragging at
        nothing."""
        printed = self.repl.rendered([
            "reading |> Maybe.map (depositInventoryFromReading"
            " >> Maybe.map (.structureHangarTreeEntry >> (/=) Nothing))"
        ], definitions=[reading_binding(
            "reading", [ship_inventory(docked=False)])])[0]
        self.assertEqual(printed, "Just (Just False)")


class TheClientConfirmsTheDepositAndTheGaugeDoesNotTest(unittest.TestCase):
    """The `(notify)` line, against the real one and against lines that are not.

    A gauge reading zero because the drag silently moved nothing and a gauge
    reading zero because the deposit worked are the same reading, which is the
    distinction #19 cost the standalone restock tool. So the gauge says when to
    start and the client says when it is done, and neither answers the other's
    question.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def confirmation(self, lines):
        return self.repl.rendered([
            "reading |> Maybe.map depositConfirmedInGameLog"
        ], definitions=[reading_binding("reading", [game_log(lines)])])[0]

    def test_the_real_recorded_line_is_the_confirmation(self):
        self.assertEqual(self.confirmation([("notify", CONFIRMATION_LINE)]),
                         "Just (Just %s)" % json.dumps(CONFIRMATION_LINE))

    def test_a_notify_line_that_is_not_it_is_declined(self):
        """The client writes this one on the same channel on the same readings
        -- `miningRangeRefusalFromGameLog` reads it -- so it is a sentence this
        bot really meets rather than a string invented to fail."""
        self.assertEqual(
            self.confirmation([("notify", ANOTHER_NOTIFY_LINE)]),
            "Just Nothing")

    def test_one_marker_is_not_enough(self):
        """`to your hangar` alone takes any sentence about a hangar the client
        ever writes, which is why the matcher is a pair."""
        self.assertEqual(
            self.confirmation([("notify", A_SENTENCE_ABOUT_A_HANGAR)]),
            "Just Nothing")
        # And the near miss really does carry one of the two markers, or the
        # case above passes for a matcher keyed on anything at all.
        self.assertIn("to your hangar", A_SENTENCE_ABOUT_A_HANGAR)
        self.assertNotIn("item(s) was moved", A_SENTENCE_ABOUT_A_HANGAR)

    def test_the_channel_is_part_of_the_question(self):
        """`gameLogEntryIsFromNotifyChannel` is what this bot reads, and the
        same words on another channel are not the client telling this ship
        anything."""
        self.assertEqual(self.confirmation([("info", CONFIRMATION_LINE)]),
                         "Just Nothing")

    def test_the_confirmation_is_found_among_other_lines(self):
        self.assertEqual(
            self.confirmation([("notify", ANOTHER_NOTIFY_LINE),
                               ("notify", CONFIRMATION_LINE)]),
            "Just (Just %s)" % json.dumps(CONFIRMATION_LINE))

    def test_a_host_with_no_game_log_confirms_nothing(self):
        """`Nothing` from the channel is a host that does not carry it, and it
        is never read as a deposit that landed -- which is the direction that
        keeps a silent host from reporting success."""
        printed = self.repl.rendered([
            "reading |> Maybe.map depositConfirmedInGameLog"
        ], definitions=[reading_binding("reading", [ship_inventory()])])[0]
        self.assertEqual(printed, "Just Nothing")

    def test_an_empty_hold_while_docked_is_not_a_confirmation(self):
        """The whole of #464's third emphasis, executed.

        A run folded over readings that are docked with an empty hold and no
        client line does **not** end, because ending it there is exactly the
        inference the issue rules out: a drag that moved nothing empties no hold
        either, and a gauge reading zero for the two reasons is the same
        reading.
        """
        printed = self.repl.rendered([
            "List.foldl (\\( holdFill, confirmationNow ) before ->"
            " depositRunAfterReading { before = before, holdFill = holdFill"
            " , docked = True, confirmationNow = confirmationNow"
            " , dragDispatched = False })"
            " (Just %s)"
            " [ ( HoldHasRoom, Nothing ), ( HoldHasRoom, Nothing )"
            " , ( HoldHasRoom, Nothing ) ]" % deposit_run(readings=4)])[0]
        self.assertEqual(printed,
                         "Just { confirmation = Nothing, drags = 0"
                         ", readings = 7 }")


class TheDockingRunInIsCommandedOnceTest(unittest.TestCase):
    """`DockingRunIn`, ported from the mission runner and folded over sessions.

    That bot's run 27 commanded Dock on 120 of the 121 readings between two
    accepted course-settings, and those two are 486 seconds apart -- the run-in's
    own length. The bug is the repetition rather than the mechanism: a panel
    click repeated every reading restarts the perimeter run exactly as
    effectively as a cascade click did.

    What ends the wait is the run-in *working*, not a clock, so every case here
    is a fold rather than a single reading.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fold(self, before, readings):
        """`dockingRunInAfterReading` over a session of (course-set, range,
        docked) triples."""
        steps = ", ".join(
            "( %s, %s, %s )" % (
                "True" if course_set else "False",
                "Nothing" if range_now is None else "(Just %d)" % range_now,
                "True" if docked else "False")
            for course_set, range_now, docked in readings)
        return self.repl.rendered([
            "List.foldl (\\( courseSetThisReading, rangeNow, docked ) before ->"
            " dockingRunInAfterReading { before = before"
            " , courseSetThisReading = courseSetThisReading"
            " , rangeNow = rangeNow, docked = docked })"
            " %s [ %s ]" % (before, steps)])[0]

    def test_the_client_s_own_sentence_is_what_arms_it(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map courseSetToDockingPerimeterFromGameLog"
        ], definitions=[reading_binding("reading", [
            game_log([("notify", "Setting course to docking perimeter")])])])[0]
        self.assertEqual(printed,
                         'Just (Just "Setting course to docking perimeter")')
        # And the constant the status line quotes is the one the matcher uses,
        # so a drift cannot leave the two saying different things.
        self.assertIn(COURSE_SET_LINE,
                      collapsed(top_level_declarations(bot_source())[
                          "courseSetToDockingPerimeterMarker"]))

    def test_a_falling_range_survives_far_past_any_clock(self):
        """Eight minutes is hundreds of readings, and a structure 200 km off is
        a longer run-in and just as legitimate. So a ship that is closing gets
        as long as the distance requires."""
        printed = self.fold(
            "Nothing",
            [(True, 200000, False)]
            + [(False, 200000 - step * 500, False) for step in range(1, 300)])
        self.assertEqual(printed,
                         "Just { dockCommands = 1, rangeToTheStructureMeters ="
                         " Just 50500, readingsSinceCloser = 0 }")

    def test_the_patience_ends_it_and_one_reading_fewer_does_not(self):
        stalled = [(False, 17000, False)] * 20
        at_the_bound = self.fold("(Just %s)" % run_in(range_meters=17000),
                                 stalled)
        one_short = self.fold("(Just %s)" % run_in(range_meters=17000),
                              stalled[:-1])
        self.assertEqual(at_the_bound, "Nothing")
        self.assertEqual(
            one_short,
            "Just { dockCommands = 1, rangeToTheStructureMeters = Just 17000"
            ", readingsSinceCloser = 19 }")

    def test_the_bound_is_the_watchdog_s_own_number(self):
        """`stall_watch.py`'s `APPROACH_PATIENCE`, same question, same signal,
        same unit -- so the bot and the watchdog watching it cannot disagree
        about what a stalled approach looks like."""
        self.assertEqual(self.repl.rendered(
            ["dockingRunInPatienceReadings"])[0], "20")
        watchdog = os.path.join(os.path.dirname(GAS_HUFFER_DIR),
                                "..", "..", "..",
                                "tools", "macos-host", "stall_watch.py")
        with open(os.path.normpath(watchdog), encoding="utf-8") as handle:
            source = handle.read()
        match = re.search(r"^APPROACH_PATIENCE\s*=\s*(\d+)", source,
                          re.MULTILINE)
        self.assertIsNotNone(match, "stall_watch.py names no APPROACH_PATIENCE")
        self.assertEqual(match.group(1), "20")

    def test_a_growing_range_is_not_a_gain(self):
        printed = self.fold("(Just %s)" % run_in(range_meters=17000),
                            [(False, 17000 + step * 100, False)
                             for step in range(1, 6)])
        self.assertEqual(
            printed,
            "Just { dockCommands = 1, rangeToTheStructureMeters = Just 17000"
            ", readingsSinceCloser = 5 }")

    def test_an_unreadable_range_is_not_a_gain_either(self):
        """`Nothing` covers a structure that is not on the overview, a row that
        is not rendered, and an AU distance -- none of which is evidence the ship
        is closing. The worst that degrades to is one Dock per patience window
        rather than one per reading."""
        printed = self.fold("(Just %s)" % run_in(range_meters=17000),
                            [(False, None, False)] * 5)
        self.assertEqual(
            printed,
            "Just { dockCommands = 1, rangeToTheStructureMeters = Just 17000"
            ", readingsSinceCloser = 5 }")

    def test_a_range_arriving_where_there_was_none_starts_the_patience_over(self):
        printed = self.fold("(Just %s)" % run_in(since_closer=7),
                            [(False, 9000, False)])
        self.assertEqual(
            printed,
            "Just { dockCommands = 1, rangeToTheStructureMeters = Just 9000"
            ", readingsSinceCloser = 0 }")

    def test_docking_clears_the_latch(self):
        """A latch surviving into the next undock would suppress the first Dock
        of the next trip."""
        self.assertEqual(
            self.fold("(Just %s)" % run_in(range_meters=200), [(False, 0, True)]),
            "Nothing")

    def test_a_second_course_setting_restarts_it_and_is_counted(self):
        """The client writes the line each time it accepts a Dock, so a second
        one is a second run-in from wherever the ship now is -- and the count is
        what says how many times a run restarted its own dock. A working one
        shows 1."""
        printed = self.fold("(Just %s)" % run_in(range_meters=17000,
                                                 since_closer=9),
                            [(True, 42000, False)])
        self.assertEqual(
            printed,
            "Just { dockCommands = 2, rangeToTheStructureMeters = Just 42000"
            ", readingsSinceCloser = 0 }")

    def test_a_latched_run_in_is_waited_on_rather_than_re_commanded(self):
        """The half that matters: the rule above stops the latch from dropping,
        and this is what the latch does to the decision."""
        waiting, without = self.repl.rendered([
            "depositStep %s" % situation(docking_run_in="(Just %s)"
                                         % run_in(range_meters=17000),
                                         dock_offered=True),
            "depositStep %s" % situation(dock_offered=True),
        ])
        self.assertTrue(waiting.startswith("WaitForTheDockingRunIn"), waiting)
        self.assertEqual(without, "PressTheDockButton")

    def test_the_waiting_line_names_the_range_and_the_count(self):
        """`stall_watch.py` keys its circling test on the decision text
        changing, so a line that read the same at every range would raise an
        alarm on a ship flying its run-in perfectly."""
        printed, unreadable = self.repl.strings([
            "describeDockingRunIn %s" % run_in(range_meters=17000,
                                               since_closer=3),
            "describeDockingRunIn %s" % run_in(range_meters=None),
        ])
        self.assertIn(COURSE_SET_LINE, printed)
        self.assertIn("17000 m", printed)
        self.assertIn("3 of 20", printed)
        self.assertIn("restart", printed)
        self.assertIn("cannot say", unreadable)

    def test_the_range_is_the_home_structure_s_and_an_au_one_is_not_read(self):
        """An AU distance is an `Err` from the parser rather than a number that
        would read as merely far, and a hidden row's distance belongs to whatever
        was recycled into its place."""
        near, far, hidden, none = self.repl.rendered([
            "reading |> Maybe.map (rangeToTheHomeStructureInMeters (Just %s))"
            % json.dumps(FICTIONAL_STRUCTURE),
            "auReading |> Maybe.map (rangeToTheHomeStructureInMeters (Just %s))"
            % json.dumps(FICTIONAL_STRUCTURE),
            "hiddenReading"
            " |> Maybe.map (rangeToTheHomeStructureInMeters (Just %s))"
            % json.dumps(FICTIONAL_STRUCTURE),
            "reading |> Maybe.map (rangeToTheHomeStructureInMeters Nothing)",
        ], definitions=[
            reading_binding("reading", [overview_window([
                structure_row(distance="4,200 m")])]),
            reading_binding("auReading", [overview_window([
                structure_row(distance="1.4 AU")])]),
            reading_binding("hiddenReading", [overview_window([
                structure_row(distance="4,200 m", displayed=False)])]),
        ])
        self.assertEqual(near, "Just (Just 4200)")
        self.assertEqual(far, "Just Nothing")
        self.assertEqual(hidden, "Just Nothing")
        self.assertEqual(none, "Just Nothing")


class TheSequenceFoldedOverASessionTest(unittest.TestCase):
    """#464's own sequence, asked as one ordering rather than as branches.

    Warp to the home structure at 0 m, dock from the panel, open the hangar,
    drag, confirm, undock. Every stage can fail to be reachable, so each has to
    fall through or say so rather than holding the loop -- which is
    `harvestStep`'s and `evasionStep`'s shape in this file already.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def steps(self, situations):
        return self.repl.rendered(
            ["depositStep %s" % one for one in situations])

    def test_a_hold_that_does_not_need_emptying_falls_straight_through(self):
        """The exit, asked first, and it is what lets the harvest run on every
        ordinary reading."""
        self.assertEqual(
            self.steps([situation(under_way=False, hold="HoldHasRoom"),
                        situation(under_way=False, hold="HoldIsFull")]),
            ["TheHoldDoesNotNeedDepositing", "TheHoldDoesNotNeedDepositing"])

    def test_the_transient_is_waited_through_in_either_half(self):
        """Asked above both the docked and the in-space ladders, because the
        gauge can carry it in either."""
        self.assertEqual(
            self.steps([situation(hold="HoldTransferIsInFlight", docked=True),
                        situation(hold="HoldTransferIsInFlight", docked=False)]),
            ["WaitThroughTheTransfer", "WaitThroughTheTransfer"])

    def test_the_trip_out_is_warp_select_dock(self):
        """In space, in the order the ship flies it. The Dock button's absence is
        what says the structure is out of docking range, which is the natural
        gate between the warp and the press."""
        self.assertEqual(
            self.steps([
                situation(panel_shows=False, dock_offered=False),
                situation(panel_shows=True, dock_offered=False),
                situation(panel_shows=True, dock_offered=True),
            ]),
            ["SelectTheHomeStructure", "WarpToTheHomeStructure",
             "PressTheDockButton"])

    def test_a_ship_in_warp_is_left_alone(self):
        """Re-commanding a warp that is going is how a cascade re-opens on every
        reading of a manoeuvre already doing what it was told."""
        self.assertEqual(
            self.steps([situation(warping=True, panel_shows=False)]),
            ["WaitForTheWarpToLand"])

    def test_nowhere_to_deposit_says_so_rather_than_warping_at_nothing(self):
        self.assertEqual(
            self.steps([situation(structure_on_overview=False)]),
            ["NowhereToDepositAt"])

    def test_the_docked_half_is_hangar_hold_drag(self):
        self.assertEqual(
            self.steps([
                situation(docked=True, hangar_in_inventory=False),
                situation(docked=True, hold_selected=False),
                situation(docked=True, items=0),
                situation(docked=True),
            ]),
            ["NoStructureHangarInTheInventory", "SelectTheHold",
             "TheHoldShowsNothingToMove", "DragTheHoldIntoTheStructureHangar"])

    def test_a_dialog_is_answered_before_anything_else_is_tried(self):
        """Something has to answer it or it sits over the client for the rest of
        the session -- and the click is never evidence, because the confirmation
        and the client's refusal are both single-OK-button windows."""
        self.assertEqual(
            self.steps([situation(docked=True, ok_on_screen=True)]),
            ["ConfirmWhateverDialogIsOnScreen"])

    def test_the_confirmation_re_selects_the_hold_and_then_undocks(self):
        """Re-selecting is what makes the gauge readable on the far side of the
        undock, which is what ends the run on the first reading in space."""
        self.assertEqual(
            self.steps([
                situation(docked=True, confirmed=True, hold_selected=False),
                situation(docked=True, confirmed=True, hold_selected=True),
            ]),
            ["ReSelectTheHoldBeforeUndocking", "Undock"])

    def test_a_hold_that_reads_empty_with_no_client_line_goes_on_trying(self):
        """The issue's own named mutation, asked of the step rather than of the
        run: **success read from the gauge instead of the client's line**.

        A gauge reading zero because the drag silently moved nothing and a gauge
        reading zero because the deposit worked are the same reading, so a
        docked ship whose hold reads empty and whose client has said nothing is
        a ship that has not deposited anything -- and it must go on trying
        rather than undocking and reporting the trip done. The confirmed
        readings beside it are what make the pair discriminating: the same hold
        state, and only the client's line separates them.
        """
        self.assertEqual(
            self.steps([
                situation(docked=True, confirmed=False, hold="HoldHasRoom"),
                situation(docked=True, confirmed=False, hold="HoldHasRoom",
                          items=0),
                situation(docked=True, confirmed=True, hold="HoldHasRoom"),
            ]),
            ["DragTheHoldIntoTheStructureHangar", "TheHoldShowsNothingToMove",
             "Undock"])

    def test_a_confirmed_deposit_undocks_even_with_no_inventory_to_re_select(self):
        """The one place the re-selection is skipped rather than waited for: the
        transfer landed, the ship is safe to leave, and an inventory this reading
        cannot see is not a reason to sit in a structure."""
        self.assertEqual(
            self.steps([situation(docked=True, confirmed=True,
                                  lists_hold=False)]),
            ["Undock"])

    def test_the_whole_sequence_in_the_order_the_ship_flies_it(self):
        """The trip end to end, as one list, so that a rule doing the right
        things in the wrong order fails rather than passing case by case."""
        self.assertEqual(
            self.steps([
                # In space, hold full, structure across the grid.
                situation(panel_shows=False),
                situation(),
                situation(dock_offered=True),
                situation(docking_run_in="(Just %s)"
                          % run_in(range_meters=8000)),
                # Docked.
                situation(docked=True, hold_selected=False),
                situation(docked=True),
                situation(docked=True, ok_on_screen=True),
                situation(docked=True, confirmed=True, hold_selected=False),
                situation(docked=True, confirmed=True),
            ]),
            ["SelectTheHomeStructure", "WarpToTheHomeStructure",
             "PressTheDockButton", "WaitForTheDockingRunIn { dockCommands = 1"
             ", rangeToTheStructureMeters = Just 8000"
             ", readingsSinceCloser = 0 }",
             "SelectTheHold", "DragTheHoldIntoTheStructureHangar",
             "ConfirmWhateverDialogIsOnScreen",
             "ReSelectTheHoldBeforeUndocking", "Undock"])


class TheRunIsLatchedAndBoundedTest(unittest.TestCase):
    """`DepositRun`, folded over sessions rather than asked once.

    The trigger has to be latched rather than re-derived, because the hold reads
    empty for the whole of the trip home after the transfer lands and the ship
    still has to undock -- a run that ended on the confirmation would leave a
    ship sitting docked with nothing in the tree willing to undock it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fold(self, before, readings):
        """`depositRunAfterReading` over a session written as records.

        Records rather than tuples because Elm takes no tuple past three, and
        because what a reading says to this rule is four separate facts.
        """
        steps = ", ".join(
            "{ holdFill = %s, docked = %s, confirmationNow = %s"
            ", dragDispatched = %s }" % (
                hold,
                "True" if docked else "False",
                "Nothing" if confirmation is None
                else "(Just %s)" % json.dumps(confirmation),
                "True" if dragged else "False")
            for hold, docked, confirmation, dragged in readings)
        return self.repl.rendered([
            "List.foldl (\\reading before -> depositRunAfterReading"
            " { before = before, holdFill = reading.holdFill"
            " , docked = reading.docked"
            " , confirmationNow = reading.confirmationNow"
            " , dragDispatched = reading.dragDispatched })"
            " %s [ %s ]" % (before, steps)])[0]

    def test_only_a_full_hold_starts_a_run(self):
        for hold in ("HoldHasRoom", "HoldFillCannotBeRead",
                     "HoldTransferIsInFlight"):
            with self.subTest(hold):
                self.assertEqual(
                    self.fold("Nothing", [(hold, False, None, False)] * 5),
                    "Nothing")
        self.assertEqual(
            self.fold("Nothing", [("HoldIsFull", False, None, False)]),
            "Just { confirmation = Nothing, drags = 0, readings = 1 }")

    def test_the_run_survives_the_hold_reading_empty_while_docked(self):
        """The clause the undock rests on. After the transfer the hold is empty
        and there is still work to do."""
        self.assertEqual(
            self.fold("Nothing",
                      [("HoldIsFull", False, None, False),
                       ("HoldIsFull", True, None, False),
                       ("HoldIsFull", True, None, True),
                       ("HoldHasRoom", True, CONFIRMATION_LINE, False),
                       ("HoldHasRoom", True, None, False)]),
            "Just { confirmation = Just %s, drags = 1, readings = 5 }"
            % json.dumps(CONFIRMATION_LINE))

    def test_the_run_ends_on_the_first_reading_outside(self):
        """Which is exactly when the ship is back where #461 can pick a site
        again."""
        self.assertEqual(
            self.fold("(Just %s)" % deposit_run(readings=40,
                                                confirmation=CONFIRMATION_LINE,
                                                drags=1),
                      [("HoldHasRoom", False, None, False)]),
            "Nothing")

    def test_the_client_s_line_ends_the_run_where_the_gauge_cannot(self):
        """The other half of the same clause, and the one a sweep found open.

        The re-selection before the undock is a click like any other and it can
        fail to land, so the first reading in space can carry a confirmed
        transfer and a hold nobody can read. The run has to end there on the
        client's own line -- otherwise the ship goes back to work with a live
        deposit clock running underneath it and the session ends at the bound
        while the bot is harvesting perfectly well.
        """
        self.assertEqual(
            self.fold("(Just %s)" % deposit_run(readings=40,
                                                confirmation=CONFIRMATION_LINE),
                      [("HoldFillCannotBeRead", False, None, False)]),
            "Nothing")
        # And the confirmation arriving on the very reading the ship undocks on
        # is the same answer, since the two are latched together.
        self.assertEqual(
            self.fold("(Just %s)" % deposit_run(readings=40),
                      [("HoldFillCannotBeRead", False, CONFIRMATION_LINE,
                        False)]),
            "Nothing")

    def test_a_hold_somebody_emptied_by_hand_ends_it_too(self):
        self.assertEqual(
            self.fold("(Just %s)" % deposit_run(readings=12),
                      [("HoldHasRoom", False, None, False)]),
            "Nothing")

    def test_an_unreadable_hold_ends_nothing(self):
        """For the reason it starts nothing: a hold this reading cannot see says
        neither that the work is done nor that it is needed."""
        self.assertEqual(
            self.fold("(Just %s)" % deposit_run(readings=12),
                      [("HoldFillCannotBeRead", False, None, False)] * 3),
            "Just { confirmation = Nothing, drags = 0, readings = 15 }")

    def test_the_clock_runs_on_every_reading_of_the_run(self):
        """Counted in `updateMemoryForNewReadingFromGame`, which runs whatever
        the tree is doing -- so a bound asked only where the tree gets that far
        would run late by however long something above it holds. #102."""
        printed = self.fold(
            "Nothing",
            [("HoldIsFull", False, None, False)]
            + [("HoldIsFull", True, None, False)] * 299)
        self.assertEqual(printed,
                         "Just { confirmation = Nothing, drags = 0"
                         ", readings = 300 }")

    def test_the_session_ends_only_once_the_bound_is_reached(self):
        at_the_bound, one_short, far_past, none = self.repl.rendered([
            "depositOutOfTime { readings = 300 } /= Nothing",
            "depositOutOfTime { readings = 299 } /= Nothing",
            "depositOutOfTime { readings = 5000 } /= Nothing",
            "depositOutOfTime { readings = 0 } /= Nothing",
        ])
        self.assertEqual([at_the_bound, one_short, far_past, none],
                         ["True", "False", "True", "False"])

    def test_the_bound_is_written_as_patience_windows_rather_than_a_number(self):
        """So an operator who retunes one moves the other with it, and the
        argument cannot drift away from the figure."""
        body = collapsed(top_level_declarations(bot_source())[
            "depositGiveUpReadings"])
        self.assertIn("dockingRunInPatienceReadings * 15", body)
        self.assertEqual(self.repl.rendered(["depositGiveUpReadings"])[0], "300")

    def test_the_give_up_says_the_hold_is_still_full(self):
        """The one line an operator gets from a deposit that could not be
        finished, and what it has to carry is what they act on: an operator
        empties a hold by hand in seconds."""
        printed = self.repl.strings([
            "depositOutOfTime { readings = 300 }"
            " |> Maybe.withDefault \"<nothing>\""])[0]
        self.assertIn("300", printed)
        self.assertIn("HOLD IS STILL FULL", printed)
        self.assertIn("by hand", printed)
        self.assertIn(str(300), printed)

    def test_a_deposit_that_never_confirms_ends_the_session(self):
        """The issue's own case, end to end: a session of docked readings on
        which the client says nothing, the run's clock climbing, and the bound
        answering on the reading it is reached and not before."""
        run, at_the_bound, one_short = self.repl.rendered([
            "List.foldl (\\_ before -> depositRunAfterReading"
            " { before = before, holdFill = HoldIsFull, docked = True"
            " , confirmationNow = Nothing, dragDispatched = False })"
            " (Just %s) (List.range 1 299)" % deposit_run(readings=1),
            "List.foldl (\\_ before -> depositRunAfterReading"
            " { before = before, holdFill = HoldIsFull, docked = True"
            " , confirmationNow = Nothing, dragDispatched = False })"
            " (Just %s) (List.range 1 299)"
            " |> Maybe.andThen (\\r -> depositOutOfTime { readings = r.readings })"
            " |> (/=) Nothing" % deposit_run(readings=1),
            "List.foldl (\\_ before -> depositRunAfterReading"
            " { before = before, holdFill = HoldIsFull, docked = True"
            " , confirmationNow = Nothing, dragDispatched = False })"
            " (Just %s) (List.range 1 298)"
            " |> Maybe.andThen (\\r -> depositOutOfTime { readings = r.readings })"
            " |> (/=) Nothing" % deposit_run(readings=1),
        ])
        self.assertEqual(
            run, "Just { confirmation = Nothing, drags = 0, readings = 300 }")
        self.assertEqual(at_the_bound, "True")
        self.assertEqual(one_short, "False")

    def test_a_drag_is_told_from_a_click_by_the_shape_of_the_step(self):
        """`DepositRun.drags` is read by nothing that decides anything; it is
        what separates *the drag has not gone out* from *it went out and the
        client has said nothing*, which an operator watching a deposit that is
        not finishing has to tell apart."""
        dragged, clicked, keys, nothing = self.repl.rendered([
            "stepDraggedSomething (EffectOnWindow.effectsForDragAndDrop"
            " { startLocation = { x = 10, y = 10 }"
            " , mouseButton = EffectOnWindow.MouseButtonLeft"
            " , waypointsPositionsInBetween = [ { x = 20, y = 20 } ]"
            " , endLocation = { x = 30, y = 30 } })",
            "stepDraggedSomething (EffectOnWindow.effectsMouseClickAtLocation"
            " EffectOnWindow.MouseButtonLeft { x = 10, y = 10 })",
            "stepDraggedSomething (hotkeyEffects directionalScanHotkey)",
            "stepDraggedSomething []",
        ])
        self.assertEqual([dragged, clicked, keys, nothing],
                         ["True", "False", "False", "False"])


class TheRetreatOutranksTheDepositTest(unittest.TestCase):
    """The ordering #464 is emphatic about, and inverting it compiles.

    A hostile arriving mid-deposit -- while docking, or docked and undocking --
    must take the retreat rather than the errand. The mission runner places
    `recoverPodAfterShipLoss` above the docked-or-in-space split for the same
    reason, and this bot now places the whole leaving there.

    Two of these are executed and the rest are read out of the source, and the
    division is stated rather than blurred: `evasionStep` and `depositStep` are
    rules over records and are run, while `actOnTheEvasionStep`,
    `actOnTheDepositStep` and `watchLeaveDepositOrHarvest` take a whole
    `BotDecisionContext` -- #106's shape, which nothing can execute.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()
        cls.declarations = top_level_declarations(bot_source())

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_leaving_is_asked_before_the_deposit(self):
        body = collapsed(self.declarations["watchLeaveDepositOrHarvest"])
        self.assertIn("actOnTheEvasionStep", body)
        self.assertIn("actOnTheDepositStep", body)
        self.assertLess(body.index("actOnTheEvasionStep"),
                        body.index("actOnTheDepositStep"), body)

    def test_both_are_asked_above_the_docked_or_in_space_split(self):
        """Which is what makes the ordering reach a docked reading at all. Below
        the split the retreat would be in the in-space arm and a docked bot
        would undock to finish an errand with nothing able to stop it."""
        body = collapsed(self.declarations["watchLeaveDepositOrHarvest"])
        for above in ("actOnTheEvasionStep", "actOnTheDepositStep"):
            with self.subTest(above):
                self.assertLess(body.index(above),
                                body.index("branchDependingOnDockedOrInSpace"),
                                body)

    def test_a_docked_ship_stays_docked_while_the_grid_does_not_read_clean(self):
        """Executed: the retreat's answer to a docked reading, which is what
        outranks the deposit's undock."""
        dirty, clean, in_space = self.repl.rendered([
            "evasionStep %s" % evasion_situation(docked=True, clean=False),
            "evasionStep %s" % evasion_situation(docked=True, clean=True),
            "evasionStep %s" % evasion_situation(docked=False, clean=False),
        ])
        self.assertEqual(dirty, "StayDockedRatherThanUndockIntoIt")
        self.assertEqual(clean, "TheGridReadsCleanSoResumeWork")
        # And the in-space answer to the same grid is the one this bot has had
        # since #463, so the docked clause narrows rather than replaces it.
        self.assertEqual(in_space, "ActivateTheCloak 2")

    def test_the_deposit_would_have_undocked_on_that_same_reading(self):
        """What makes the case above an ordering rather than a coincidence: the
        deposit's answer to the same ship is `Undock`, so which of the two the
        bot takes is decided by placement and by nothing else."""
        self.assertEqual(
            self.repl.rendered([
                "depositStep %s" % situation(docked=True, confirmed=True)])[0],
            "Undock")

    def test_the_docked_answer_holds_the_tree_rather_than_declining(self):
        """`Nothing` from `actOnTheEvasionStep` is what lets the deposit run, so
        the docked answer has to be a `Just` -- read out of the source, since the
        function takes a whole decision context."""
        body = collapsed(self.declarations["actOnTheEvasionStep"])
        after = body.split("StayDockedRatherThanUndockIntoIt ->", 1)
        self.assertEqual(len(after), 2, body)
        arm = after[1].split("WaitForTheEvasionWarpToLand ->", 1)[0]
        self.assertIn("Just", arm)
        self.assertIn("waitForProgressInGame", arm)
        # And the one answer that does decline is the clean one, which is what
        # lets the deposit and the harvest run at all.
        clean = body.split("TheGridReadsCleanSoResumeWork ->", 1)[1].split(
            "StayDockedRatherThanUndockIntoIt ->", 1)[0]
        self.assertEqual(clean.strip(), "Nothing")

    def test_a_docked_reading_is_judged_on_the_grid_as_it_last_read(self):
        """A docked client answers no Directional Scan, so a docked reading's own
        verdict is a statement about the instrument rather than about the grid
        outside -- and a bot judging the undock on it would dock once and never
        come out."""
        body = collapsed(self.declarations["evasionSituationFromContext"])
        self.assertIn("context.memory.lastGridVerdictInSpaceIsClean"
                      " |> Maybe.withDefault False", body)
        update = collapsed(self.declarations[
            "updateMemoryForNewReadingFromGame"])
        self.assertIn("lastGridVerdictInSpaceIsClean = if docked then"
                      " botMemoryBefore.lastGridVerdictInSpaceIsClean"
                      " else Just gridIsClean", update)

    def test_a_session_that_has_never_been_in_space_does_not_undock(self):
        """`Nothing` reads as not clean, which is #463's own line applied to a
        session started docked: this bot undocks into nothing it has never
        looked at."""
        self.assertIn("Maybe.withDefault False",
                      collapsed(self.declarations[
                          "evasionSituationFromContext"]))

    def test_a_docked_reading_spends_neither_evasion_bound(self):
        """A docked ship is not evading, so counting docked readings against the
        session bound would end a session about a ship in no danger -- and
        against the warp alarm would fetch a person for one."""
        printed = self.repl.rendered([
            "List.foldl (\\docked counters -> evasionCountersAfterReading"
            " { gridIsClean = False, docked = docked, shipIsWarping = False"
            " , cloakAnsweredTheAsk = True } counters)"
            " initEvasionCounters"
            " (List.repeat 5 False ++ List.repeat 400 True)"])[0]
        self.assertEqual(printed,
                         "{ cloakUnansweredReadings = 0"
                         ", longestWarpUnexecutedReadings = 5"
                         ", readings = 0, warpUnexecutedReadings = 0 }")

    def test_the_scan_is_not_asked_of_a_docked_reading_either(self):
        """A docked client answers no scan, so the keypress would go nowhere and
        the reading would be spent for nothing."""
        body = collapsed(self.declarations["refreshTheDirectionalScanner"])
        self.assertIn("if context.readingFromGameClient.shipUI == Nothing then"
                      " Nothing", body)

    def test_the_deposit_never_reaches_past_the_leaving_on_its_own(self):
        """The inversion this whole class refuses, stated as a property of the
        source: nothing in the deposit consults the grid, so it cannot come to
        decide for itself that leaving is unnecessary."""
        for name in ("depositStep", "depositSituationFromContext",
                     "actOnTheDepositStep", "depositRunAfterReading"):
            with self.subTest(name):
                body = collapsed(self.declarations[name])
                for forbidden in ("gridVerdict", "gridReadsClean",
                                  "gridEvidence", "evasionStep"):
                    self.assertNotIn(forbidden, body)


class EveryClickingArmSaysWhatItIsWaitingForTest(unittest.TestCase):
    """A branch that declines and says nothing is indistinguishable from one
    that is stuck, which is `/review-silent-success` exactly.

    Every arm of the deposit that cannot proceed names what it saw rather than
    only what it wanted, because the node type names it steers by are this client
    build's and a name that is wrong on some future build would otherwise look
    exactly like a slow client.
    """

    def setUp(self):
        self.declarations = top_level_declarations(bot_source())
        self.body = collapsed(self.declarations["actOnTheDepositStep"])

    def test_the_dialog_arm_says_the_click_is_not_evidence(self):
        """The caveat #464 quotes from `restockDroneBayWhileDocked`: the
        confirmation and the refusal are both single-OK-button windows, so
        clicking whichever OK is on screen and calling it success reports a
        transfer that moved nothing."""
        self.assertIn("says nothing about either", self.body)
        self.assertIn("item(s) was moved to your hangar", self.body)

    def test_the_dead_ends_name_what_is_missing_and_what_ends_the_session(self):
        for phrase in ("no inventory window listing",
                       "row in the inventory to drop it into",
                       "nowhere to deposit from here",
                       "the client is rendering no item in it"):
            with self.subTest(phrase):
                self.assertIn(phrase, self.body)
        self.assertEqual(self.body.count("deposit bound"), 4, self.body)

    def test_the_drag_and_the_dialog_wait_for_the_previous_click_to_land(self):
        """A repeat drag can move part of a stack somewhere unintended while the
        first is still catching up, and a repeat OK lands wherever the client has
        drawn something else."""
        self.assertIn("unlessJustClicked", self.body)
        for arm in ("DragTheHoldIntoTheStructureHangar",
                    "ConfirmWhateverDialogIsOnScreen",
                    "SelectTheHold",
                    "ReSelectTheHoldBeforeUndocking"):
            with self.subTest(arm):
                self.assertIn("unlessJustClicked",
                              deposit_arm(self.body, arm))
        # And the arms that only wait, or that command a warp the cascade
        # machinery already paces, do not -- so this is a property of the
        # gestures that can be issued twice rather than a blanket wrapper.
        for arm in ("WarpToTheHomeStructure", "WaitForTheDockingRunIn"):
            with self.subTest(arm):
                self.assertNotIn("unlessJustClicked",
                                 deposit_arm(self.body, arm))

    def test_the_undock_reads_both_buttons_rather_than_the_label(self):
        """The same button carries `Undock`, then `Abort Undock`, then
        `Undocking...`, and pressing either of the last two cancels the undock
        already under way -- 20,486 clicks in saxrat's run 43."""
        body = collapsed(self.declarations["undockUsingTheStationWindow"])
        self.assertIn("stationWindow.undockButton", body)
        self.assertIn("stationWindow.abortUndockButton", body)
        self.assertIn("Already undocking", body)

    def test_the_warp_home_names_the_distance_it_takes(self):
        self.assertIn("warpAtZeroMenuEntry", self.body)
        self.assertIn("warpCascadeWithin", self.body)

    def test_the_dock_button_is_found_by_name_and_never_by_position(self):
        """`selectedItemOrbit` was read live at x=1515 in one reading and x=1551
        in another moments later, because two buttons left the row."""
        body = collapsed(self.declarations["selectedItemDockButton"])
        self.assertIn("selectedItemDock", body)
        self.assertIn("CmdDockAtItem", body)


class ThePanelIsPressedByNameEitherWayTest(unittest.TestCase):
    """Both identifiers the client carries for the Dock button, executed.

    Matching either survives a rename of one, which is cheap insurance on a
    widget name -- the class of thing that has cost this repo whole sessions.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_button_is_found_by_its_name_and_by_its_command_name(self):
        by_name, by_cmd, absent = self.repl.rendered([
            "byName |> Maybe.map (\\r ->"
            " selectedItemPanelButton r selectedItemDockButton /= Nothing)",
            "byCmd |> Maybe.map (\\r ->"
            " selectedItemPanelButton r selectedItemDockButton /= Nothing)",
            "noButton |> Maybe.map (\\r ->"
            " selectedItemPanelButton r selectedItemDockButton /= Nothing)",
        ], definitions=[
            reading_binding("byName", [selected_item_window(
                FICTIONAL_STRUCTURE)]),
            reading_binding("byCmd", [selected_item_window(
                FICTIONAL_STRUCTURE, by_cmd_name=True)]),
            reading_binding("noButton", [selected_item_window(
                FICTIONAL_STRUCTURE, dock_button=False)]),
        ])
        self.assertEqual([by_name, by_cmd, absent],
                         ["Just True", "Just True", "Just False"])

    def test_the_panel_is_matched_against_the_row_on_words(self):
        """`selectedItemIsOverviewEntry`, which the harvest loop already uses:
        compared on words rather than as a substring, because the panel's own
        label carries decoration around the name."""
        showing, showing_else = self.repl.rendered([
            "reading |> Maybe.map (\\r -> r.overviewWindows"
            " |> List.concatMap .entries |> List.head"
            " |> Maybe.map (selectedItemIsOverviewEntry r))",
            "other |> Maybe.map (\\r -> r.overviewWindows"
            " |> List.concatMap .entries |> List.head"
            " |> Maybe.map (selectedItemIsOverviewEntry r))",
        ], definitions=[
            reading_binding("reading", [
                overview_window([structure_row()]),
                selected_item_window(FICTIONAL_STRUCTURE)]),
            reading_binding("other", [
                overview_window([structure_row()]),
                selected_item_window("Somewhere Else Entirely")]),
        ])
        self.assertEqual(showing, "Just (Just True)")
        self.assertEqual(showing_else, "Just (Just False)")


class TheStatusLineSaysWhatTheHoldIsDoingTest(unittest.TestCase):
    """What an operator reads on every reading, whether or not a deposit is
    running.

    The reading they want the hold's own state on is the quiet one *while it is
    filling*: a hold nobody can read is cheap to fix then -- open the inventory
    on the Mining Hold -- and it is the difference between a bot that will
    deposit and one that never will, which is otherwise invisible until the hold
    is full and nothing happens.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def clause(self, hold="HoldHasRoom", deposit="Nothing",
               docking_run_in="Nothing", home=FICTIONAL_STRUCTURE):
        return self.repl.strings([
            "describeDeposit { holdFill = %s, deposit = %s"
            ", dockingRunIn = %s, homeStructureName = %s }" % (
                hold, deposit, docking_run_in,
                "Nothing" if home is None else "(Just %s)" % json.dumps(home))])[0]

    def test_an_unreadable_hold_shouts_and_says_what_to_do_about_it(self):
        printed = self.clause(hold="HoldFillCannotBeRead")
        self.assertIn("NOT READABLE", printed)
        self.assertIn("Mining Hold", printed)
        self.assertIn("will ever decide to deposit", printed)

    def test_the_transient_is_named_as_a_transient_rather_than_as_full(self):
        printed = self.clause(hold="HoldTransferIsInFlight")
        self.assertIn("transfer in flight", printed)
        self.assertNotIn("FULL", printed)

    def test_a_running_deposit_carries_its_count_against_the_bound(self):
        """The bound is printed beside the count rather than only in the give-up
        sentence, which is `describeEvasion`'s own finding: a mutation that
        dropped the bound from the count while leaving it in the sentence
        survived a case that read the sentence out of the source."""
        printed = self.clause(hold="HoldIsFull",
                              deposit="(Just %s)" % deposit_run(
                                  readings=42, drags=2))
        self.assertIn("42/300", printed)
        self.assertIn("2 drag(s)", printed)
        self.assertIn("has not said the transfer landed", printed)

    def test_the_client_s_own_words_are_quoted_once_it_has_said_them(self):
        printed = self.clause(
            hold="HoldHasRoom",
            deposit="(Just %s)" % deposit_run(
                readings=50, confirmation=CONFIRMATION_LINE, drags=1))
        self.assertIn(CONFIRMATION_LINE, printed)

    def test_the_docking_run_in_is_reported_with_its_count_and_range(self):
        printed = self.clause(hold="HoldIsFull",
                              deposit="(Just %s)" % deposit_run(readings=8),
                              docking_run_in="(Just %s)" % run_in(
                                  range_meters=17000, since_closer=3,
                                  dock_commands=1))
        self.assertIn("1 dock command(s)", printed)
        self.assertIn("17000 m", printed)
        self.assertIn("3/20", printed)

    def test_an_unset_home_structure_says_the_bot_cannot_deposit_at_all(self):
        printed = self.clause(home=None)
        self.assertIn("home-structure-name", printed)
        self.assertIn("cannot deposit at all", printed)

    def test_the_status_line_carries_the_clause(self):
        body = collapsed(top_level_declarations(bot_source())[
            "statusTextFromState"])
        self.assertIn("describeDeposit", body)
        self.assertIn("holdFillFromReading context.readingFromGameClient", body)


class TheRulesTakeRecordsRatherThanADecisionContextTest(unittest.TestCase):
    """#106: a rule reachable only through a decision context is one nothing can
    run, so it gets checked by being read -- which is how a rule that does the
    right things in the wrong order passes for one that works."""

    def setUp(self):
        self.declarations = top_level_declarations(bot_source())

    def test_every_rule_this_file_executes_takes_plain_facts(self):
        for rule in ("depositStep", "depositRunAfterReading",
                     "depositOutOfTime", "dockingRunInAfterReading",
                     "holdFillFromCapacityGauge", "describeDockingRunIn",
                     "describeDeposit", "stepDraggedSomething",
                     "homeStructureRowsOnTheOverview"):
            with self.subTest(rule):
                signature = collapsed(self.declarations[rule]).split(
                    " %s " % rule)[0]
                self.assertNotIn("BotDecisionContext", signature)

    def test_the_deposit_reads_the_one_home_structure_rule(self):
        """#102's sharpest instance here: the retreat's second rung and the
        deposit's only destination are the same structure, so two spellings of
        "which row is home" would be a bot that runs to one place when it is
        frightened and flies to another when it is full."""
        readers = [name for name, text in self.declarations.items()
                   if "homeStructureRowsOnTheOverview" in collapsed(text)
                   and name != "homeStructureRowsOnTheOverview"]
        self.assertEqual(
            sorted(readers),
            ["actOnTheDepositStep", "depositSituationFromContext",
             "rangeToTheHomeStructureInMeters", "retreatSearch"],
            readers)

    def test_the_gauge_is_read_in_one_place_and_asked_in_three(self):
        source = collapsed(bot_source())
        self.assertEqual(source.count("holdFillFromReading readingFromGameClient ="),
                         1)
        readers = [name for name, text in self.declarations.items()
                   if "holdFillFromReading" in collapsed(text)
                   and name != "holdFillFromReading"]
        self.assertEqual(
            sorted(readers),
            ["depositSituationFromContext", "statusTextFromState",
             "updateMemoryForNewReadingFromGame"],
            readers)

    def test_the_two_bounds_that_end_a_session_are_asked_at_the_head(self):
        head = collapsed(self.declarations[
            "gasHufferDecisionRootBeforeApplyingSettings"])
        self.assertIn("endSessionOnAnExpiredBound context", head)
        self.assertLess(head.index("endSessionOnAnExpiredBound"),
                        head.index("generalSetupInUserInterface"), head)
        body = collapsed(self.declarations["endSessionOnAnExpiredBound"])
        self.assertIn("evasionOutOfTime", body)
        self.assertIn("depositOutOfTime", body)
        self.assertLess(body.index("evasionOutOfTime"),
                        body.index("depositOutOfTime"), body)
        # And it still does nothing but end the session, which is what makes it
        # evaluable on any reading and is why nothing may be placed over it.
        for acting in ("decideActionForCurrentStep", "waitForProgressInGame",
                       "useContextMenuCascade", "askForHelpToGetUnstuck"):
            with self.subTest(acting):
                self.assertNotIn(acting, body)

    def test_the_bound_that_declines_an_action_stays_where_the_action_is(self):
        """PR #115's rule, both halves: the docking run-in's patience declines a
        re-command rather than ending anything, so it is asked inside the step
        rule."""
        self.assertIn("dockingRunInPatienceReadings",
                      collapsed(self.declarations["dockingRunInAfterReading"]))
        self.assertNotIn("dockingRunInPatienceReadings",
                         collapsed(self.declarations[
                             "endSessionOnAnExpiredBound"]))


class TheParserIsNotTouchedTest(unittest.TestCase):
    """This change reads the inventory the vendored parser already lifts and
    adds nothing.

    `EveOnline/ParseUserInterface.elm` is vendored once per app and the gas
    huffer's copy is byte-identical to `eve-online-wingman`'s. A deposit that
    needed a parser change would be an eight-copy concern (#467) rather than a
    one-file edit, so the absence of one is asserted rather than left to be
    noticed in review.
    """

    def test_the_vendored_parser_matches_wingman_byte_for_byte(self):
        apps = os.path.dirname(GAS_HUFFER_DIR)

        def parser(app):
            with open(os.path.join(apps, app, "EveOnline",
                                   "ParseUserInterface.elm"),
                      encoding="utf-8") as handle:
                return handle.read()

        self.assertEqual(parser("eve-online-gas-huffer"),
                         parser("eve-online-wingman"))

    def test_the_container_type_names_this_bot_steers_by_are_the_parser_s(self):
        """`ShipGeneralMiningHold` and `StructureItemHangar` are two of the six
        `parseInventoryWindow` recognises. Reading them out of the parser is what
        would go red on the day a vendored copy stopped carrying them, which is
        the direction this fails silently in."""
        with open(os.path.join(GAS_HUFFER_DIR, "EveOnline",
                               "ParseUserInterface.elm"),
                  encoding="utf-8") as handle:
            parser = handle.read()
        self.assertIn("ShipGeneralMiningHold", parser)
        self.assertIn("StructureItemHangar", parser)
        self.assertIn("ShipGeneralMiningHold",
                      collapsed(top_level_declarations(bot_source())[
                          "miningHoldContainerTypeName"]))


class WhyThisShipDocksAtAllTest(unittest.TestCase):
    """The cheaper path was looked for and is not in the evidence.

    Docking is the expensive and failure-prone half of #464 -- a run-in that
    kept a mission runner 17 km off a station for eight minutes, then the hangar
    work, then an undock -- so emptying the hold into the structure from space
    would remove all three. What follows is what was looked for, asserted as
    *relations* rather than as prose, so that **the day one of them stops being
    true the case goes red** and somebody is looking at the moment the evidence
    for a cheaper path arrives.
    """

    def setUp(self):
        self.apps = os.path.dirname(GAS_HUFFER_DIR)

    def read(self, *path):
        with open(os.path.join(self.apps, *path), encoding="utf-8") as handle:
            return handle.read()

    def each_app(self, *path):
        for app in sorted(os.listdir(self.apps)):
            if not app.startswith("eve-online-"):
                continue
            candidate = os.path.join(self.apps, app, *path)
            if os.path.exists(candidate):
                yield app, self.read(app, *path)

    def test_the_parsers_offer_one_structure_container_and_only_one(self):
        """And the same six in every vendored copy, so this is a property of
        the parser rather than of the gas huffer's own."""
        pattern = re.compile(
            r'\[\s*"ShipCargo"[^\]]*\]')
        found = {}
        for app, source in self.each_app("EveOnline", "ParseUserInterface.elm"):
            match = pattern.search(source)
            self.assertIsNotNone(match, app)
            found[app] = match.group(0)
        self.assertGreaterEqual(len(found), 6, found)
        self.assertEqual(len(set(found.values())), 1, found)
        types = re.findall(r'"([A-Za-z]+)"', next(iter(found.values())))
        self.assertEqual(
            [name for name in types if "Structure" in name],
            ["StructureItemHangar"], types)

    def test_the_bot_that_already_deposits_at_a_structure_docks_to_do_it(self):
        """`eve-online-mining-bot` concatenates `unload-structure-name` and
        `unload-station-name` into one list and sends both through
        `dockToUnloadOre`, so the app closest to this use case made the same
        choice with a working implementation behind it."""
        source = collapsed(self.read("eve-online-mining-bot", "Bot.elm"))
        self.assertIn("unloadStationNames , context.eventContext.botSettings"
                      ".unloadStructureNames", source)
        self.assertIn("dockToUnloadOre context = case"
                      " unloadStationOrStructureNames context", source)

    def test_its_only_in_space_unload_is_a_fleet_ship_rather_than_a_structure(self):
        """The repo's one hold-emptying that skips a dock, and what its own
        setting text says it needs."""
        source = self.read("eve-online-mining-bot", "Bot.elm")
        self.assertIn("fleet hangar", source)
        self.assertIn("you must be in a fleet with an orca or a rorqual",
                      source)
        in_space = collapsed(source).split(
            "inSpaceWithMiningHoldSelectedWithFleetHangar", 1)[1]
        self.assertIn("effectsForDragAndDrop", in_space)
        # And no decision anywhere reaches for a structure's hangar container.
        # Over the declaration *bodies* rather than the file, since this file's
        # own doc comment names the type while reading it nowhere -- a case that
        # read prose would be red the day the finding was written down.
        for app, bot in self.each_app("Bot.elm"):
            with self.subTest(app):
                for name, text in top_level_declarations(bot).items():
                    self.assertNotIn("StructureItemHangar", collapsed(text),
                                     "%s.%s" % (app, name))

    def test_the_one_lead_is_a_button_nothing_here_has_ever_pressed(self):
        """`selectedItemAccessDropbox` is on #456's measured structure panel and
        is the only button that could plausibly be an in-space access. This is
        the case that goes red the day somebody reads what it opens.

        Over the declaration bodies rather than the file, for the reason above:
        this bot's own doc comment names the button while pressing it nowhere,
        and that is the state being asserted rather than a violation of it.
        """
        for app, bot in self.each_app("Bot.elm"):
            with self.subTest(app):
                for name, text in top_level_declarations(bot).items():
                    self.assertNotIn("selectedItemAccessDropbox",
                                     collapsed(text), "%s.%s" % (app, name))

    def test_the_finding_is_written_down_where_the_next_reader_will_be(self):
        """Beside the drop target rather than in a pull request, because the
        next person to ask this question will be reading `Bot.elm`."""
        doc = bot_source().split("structureHangarTreeEntryText :", 1)[0].rsplit(
            "{-|", 1)[1]
        self.assertIn("selectedItemAccessDropbox", doc)
        self.assertIn("eve-online-mining-bot", doc)
        self.assertIn("undocked", doc)


class TheHeaderTellsAnOperatorWhatToOpenTest(unittest.TestCase):
    """The one setup item this change adds, and it cannot be enforced.

    Nothing in a reading can tell a client whose inventory is open on the Mining
    Hold from one whose inventory is shut, so the header is the only place it can
    be stated -- and the status line is what says which of the two a run is in.
    """

    def setUp(self):
        self.header = bot_source().split("\n-}", 1)[0]

    def test_the_inventory_is_named_as_a_client_setup_requirement(self):
        self.assertIn(
            "**Leave the inventory open with the ship's Mining Hold"
            " selected.**", self.header)

    def test_the_header_says_which_direction_it_fails_in(self):
        self.assertIn("never decides to deposit", self.header)

    def test_the_header_says_the_deposit_is_confirmed_by_the_client(self):
        self.assertIn("item(s) was\n      moved to your hangar", self.header)
        self.assertIn("never for the gauge to\n      read zero", self.header)


class TheMutationsThisFileCatches(unittest.TestCase):
    """Confirmed by mutation. Each of these was applied to `Bot.elm` and the
    named case failed; the list is here so a later reader can re-run them.

    The four the issue names by hand are 1, 2, 6 and 11.

    1.  **success read from the gauge instead of the client's line** --
        `depositStep` undocking on `holdFill == HoldHasRoom` rather than on
        `confirmedByClient`, which is what a drag that moved nothing also
        produces -- `TheSequenceFoldedOverASessionTest.test_a_hold_that_reads_
        empty_with_no_client_line_goes_on_trying` and
        `test_the_confirmation_re_selects_the_hold_and_then_undocks`.
    1b. the same inference one level down: `depositRunAfterReading` ending the
        run on the gauge alone, with the client's line dropped from the
        condition -- `TheClientConfirmsTheDepositAndTheGaugeDoesNotTest
        .test_an_empty_hold_while_docked_is_not_a_confirmation`,
        `TheRunIsLatchedAndBoundedTest.test_the_run_survives_the_hold_reading_
        empty_while_docked` and `test_the_client_s_line_ends_the_run_where_the_
        gauge_cannot`. **The last of those was written after a sweep**: the
        first version of this file asked only about a hold that could be read,
        so a run carrying a confirmation and an unreadable hold on the first
        reading in space did not end, and the session would have ended at the
        bound while the bot was harvesting perfectly well.
    2.  **the transient read as a fill level** -- the `selected /= Nothing`
        clause moved below the used-against-maximum comparison, or dropped --
        `TheGaugeIsReadInAllThreeMeasuredFormsTest.test_the_transient_is_its_own_
        answer_and_not_a_fill_level`, and `test_the_transient_is_named_as_a_
        transient_rather_than_as_full` beside it.
    3.  the transient collapsed into `HoldFillCannotBeRead`, which is the milder
        version of the same mistake and stops the deposit waiting through it --
        the same case.
    4.  `holdFillFromReading` taking `List.head` of the inventory windows rather
        than the one with the hold selected -- `TheHoldIsFoundByNameRatherThan
        TakenFirstTest.test_the_hold_is_read_past_a_window_showing_something_
        else`, with `test_the_first_window_alone_would_have_answered_differently`
        as the control that makes it discriminating.
    5.  `holdIsTheSelectedContainer` reading the *sidebar row* rather than the
        selected container's type name, so a window listing the hold while
        showing the structure's hangar reads the hangar's gauge as the ship's --
        `test_a_window_listing_the_hold_but_showing_the_hangar_says_nothing`.
    6.  **the dock re-commanded every reading** -- `depositStep` ignoring
        `situation.dockingRunIn`, and separately `dockingRunInAfterReading`
        answering `Nothing` on every reading -- `TheDockingRunInIsCommandedOnce
        Test.test_a_latched_run_in_is_waited_on_rather_than_re_commanded` and
        `test_a_falling_range_survives_far_past_any_clock`.
    7.  the patience comparison moved by one in either direction --
        `test_the_patience_ends_it_and_one_reading_fewer_does_not`.
    8.  `dockingRunInPatienceReadings` written as `1`, which is the fixed value
        beside the boundary pair -- the same case, and
        `test_the_bound_is_the_watchdog_s_own_number`.
    9.  a growing range counted as a gain, and an unreadable one counted as a
        gain -- `test_a_growing_range_is_not_a_gain` and
        `test_an_unreadable_range_is_not_a_gain_either`.
    10. docking not clearing the latch, so the first Dock of the next trip is
        suppressed -- `test_docking_clears_the_latch`.
    11. **the retreat placed below this branch** -- `watchLeaveDepositOrHarvest`
        asking `actOnTheDepositStep` first, and separately the whole chain put
        back inside `huntAndHarvest` so it is only reached in space --
        `TheRetreatOutranksTheDepositTest.test_the_leaving_is_asked_before_the_
        deposit` and `test_both_are_asked_above_the_docked_or_in_space_split`.
    12. `evasionStep`'s docked answer removed, so a docked ship cloaks and warps
        at celestials it cannot see -- `test_a_docked_ship_stays_docked_while_
        the_grid_does_not_read_clean`.
    13. the docked answer made `Nothing` in `actOnTheEvasionStep`, which is the
        subtle inversion: it compiles, the retreat is still "above" the deposit,
        and the undock happens anyway --
        `test_the_docked_answer_holds_the_tree_rather_than_declining`.
    14. the docked arm of `evasionSituationFromContext` defaulting to `True`, so
        a session that has never been in space undocks into a grid nobody has
        looked at -- `test_a_session_that_has_never_been_in_space_does_not_
        undock`.
    15. the docked arm reading the *live* verdict, which is the version that
        docks once and never comes out -- `test_a_docked_reading_is_judged_on_
        the_grid_as_it_last_read`.
    16. `evasionCountersAfterReading` no longer resetting on a docked reading,
        so a docked ship ends the session on the evasion's bound --
        `test_a_docked_reading_spends_neither_evasion_bound`.
    17. the scan asked of a docked reading -- `test_the_scan_is_not_asked_of_a_
        docked_reading_either`.
    18. one marker dropped from `depositConfirmationMarkers` -- `TheClient
        ConfirmsTheDepositAndTheGaugeDoesNotTest.test_one_marker_is_not_enough`.
    19. the channel filter dropped, so the same words on `info` confirm a
        deposit -- `test_the_channel_is_part_of_the_question`.
    20. `List.all` weakened to `List.any` over the markers, which is 18 by
        another route -- the same two cases.
    21. `depositOutOfTime`'s comparison moved by one --
        `TheRunIsLatchedAndBoundedTest.test_the_session_ends_only_once_the_bound_
        is_reached`.
    22. `depositGiveUpReadings` written as a bare `300` --
        `test_the_bound_is_written_as_patience_windows_rather_than_a_number`.
    23. the give-up dropping `THE HOLD IS STILL FULL`, which is the one thing an
        operator acts on -- `test_the_give_up_says_the_hold_is_still_full`.
    24. the deposit bound dropped from `endSessionOnAnExpiredBound`, so a deposit
        that cannot finish cycles for the rest of the session --
        `TheRulesTakeRecordsRatherThanADecisionContextTest.test_the_two_bounds_
        that_end_a_session_are_asked_at_the_head`.
    25. the deposit bound asked before the evasion's, so an operator whose ship
        is stuck on somebody else's grid reads about an errand -- the same case.
    26. `depositStep` dropping the `runIsUnderWay` exit and reading the gauge
        live instead, which leaves a ship docked after a confirmed transfer with
        nothing willing to undock it -- `TheSequenceFoldedOverASessionTest
        .test_the_confirmation_re_selects_the_hold_and_then_undocks` and
        `test_a_hold_that_does_not_need_emptying_falls_straight_through`.
    27. the docked ladder reordered so the drag is tried before the dialog is
        answered -- `test_a_dialog_is_answered_before_anything_else_is_tried`.
    28. `SelectTheHomeStructure` dropped so the panel is pressed while showing
        something else -- `test_the_trip_out_is_warp_select_dock`.
    29. the warp taken while the Dock button is offered, which restarts a run-in
        the client is already flying -- the same case.
    30. `unlessJustClicked` dropped from the drag -- `EveryClickingArmSaysWhat
        ItIsWaitingForTest.test_the_drag_and_the_dialog_wait_for_the_previous_
        click_to_land`.
    31. `stepDraggedSomething` answering `True` for an ordinary click, so the
        drag count means nothing -- `test_a_drag_is_told_from_a_click_by_the_
        shape_of_the_step`.
    32. the undock reading the button's label rather than the parser's two
        fields, which is saxrat's run 43 -- `test_the_undock_reads_both_buttons_
        rather_than_the_label`.
    33. the OK arm claiming the click is evidence the transfer landed --
        `test_the_dialog_arm_says_the_click_is_not_evidence`.
    34. a dead end left as a bare wait with no sentence --
        `test_the_dead_ends_name_what_is_missing_and_what_ends_the_session`.
    35. `homeStructureRowsOnTheOverview` given a second copy in the deposit, so
        the retreat and the deposit can name different structures --
        `TheRulesTakeRecordsRatherThanADecisionContextTest.test_the_deposit_
        reads_the_one_home_structure_rule`.
    36. the `_display` filter dropped from that rule --
        `test_the_range_is_the_home_structure_s_and_an_au_one_is_not_read`, and
        `test_gas_huffer_harvests_a_cloud`'s own filter case.
    37. `selectedItemDockButton` pointed at `selectedItemWarpTo`, or its
        `cmdName` dropped -- `ThePanelIsPressedByNameEitherWayTest
        .test_the_button_is_found_by_its_name_and_by_its_command_name`.
    38. `describeDeposit` printing the count without the bound --
        `test_a_running_deposit_carries_its_count_against_the_bound`.
    39. the unreadable hold reported as `0/0` rather than in words --
        `test_an_unreadable_hold_shouts_and_says_what_to_do_about_it`.
    40. the client-setup bullet removed from the header --
        `TheHeaderTellsAnOperatorWhatToOpenTest`.
    41. the whole scan/leave/deposit chain put back inside `huntAndHarvest`, so
        it is reached only in space and a docked bot undocks with nothing able
        to stop it -- `TheRetreatOutranksTheDepositTest.test_both_are_asked_
        above_the_docked_or_in_space_split`, and
        `test_gas_huffer_watches_the_grid`'s own ordering case.
    42. a decision reaching for `StructureItemHangar` or pressing
        `selectedItemAccessDropbox` -- `WhyThisShipDocksAtAllTest`, which is
        the finding rather than the behaviour: those two cases go red on the
        day the evidence for an in-space deposit arrives, which is exactly when
        somebody should be looking at this again.
    """

    def test_this_file_names_the_mutations_it_was_graded_against(self):
        self.assertGreaterEqual(
            self.__doc__.count("--"), 35,
            "the mutation list is the record of how these cases were graded")


if __name__ == "__main__":
    unittest.main()
