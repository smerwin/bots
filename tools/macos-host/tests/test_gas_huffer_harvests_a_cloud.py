"""The gas huffer's harvest loop: pick a cloud, orbit it, lock it, run the
harvesters -- and report the one refusal it cannot act on.

Issue #461, under #456. #460 left the bot choosing a site and going nowhere;
this is the change that flies it, and four things in it are what the issue is
emphatic about.

**Clouds are ranked by their trailing digits, parsed -- not by the string,
sorted.** `Fullerite-C84` has to beat `Fullerite-C50`, which a lexical sort gets
right by luck, and `Fullerite-C100` has to beat `Fullerite-C84`, which it gets
wrong. Both pairs are asked below, and the second is the one a reverted
implementation fails.

**A name with no trailing number is unrankable, and unrankable is not zero.**
Read as zero it sorts behind every numbered cloud and is taken only when there
are none -- which is exactly the reading that would never take it *when it is
the only cloud on the grid*. `gasCloudOrder` ranks it last explicitly, so the
cases ask both halves: it loses to a numbered cloud, and it is still taken when
nothing else is there.

**`_display` is filtered before any row is acted on.** The overview virtualises,
so a hidden row's region points at whatever was recycled into its place, and
everything this bot does on a grid starts from a click on one of these rows --
the selection the Orbit button acts on, and the Ctrl+click that locks. This is
the standing rule for every overview consumer in this repo, and the case that
holds it here hides the *highest-numbered* cloud, so a filter that had been
dropped would take exactly the row it must not.

**The out-of-range refusal is reported and never corrected.** The client writes
`... deactivates without transfering ore ... strayed to a distance of 1628.94 m,
beyond its mining range of 1500.00 m` on `(notify)`, and the tempting thing to
do with it is re-orbit. Nothing here can: no command in this repository orbits
at a *distance*, so a bot acting on this line could only press the same button
and read the same refusal, forever, which is the failure this repo keeps paying
for. So the verdict is carried in `BotMemory` -- a reading's game-log entries are
gone by the next one -- and both numbers reach the status line.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`. Every overview
row, every module button and every game-log entry they are asked about is built
by running a UI tree through the **real** `EveOnline.ParseUserInterface`, with a
real overview header row and a real capacitor, so what the cases assert on is
what the bot would have been handed rather than a record shaped by hand.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically
from outside, which is the shape `prerequisites.elm_json_literal` exists for.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import re
import unittest

from prerequisites import ElmRepl, elm_json_literal, open_repl
from test_gas_huffer_scaffold import (
    GAS_HUFFER_DIR, block, bot_source, collapsed, node,
    top_level_declarations)

PREAMBLE = (
    "import Bot exposing (..)",
    "import Dict",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import Common.EffectOnWindow as EffectOnWindow",
)

# The overview's own header row on this client, read off it on 2026-09-04 and
# quoted in #456: a gas cloud renders as
#   '-' | 'Harvestable Cloud' | 'Fullerite-C84' | 'Harvestable Cloud (...)' | '833 m'
# The geometry is explicit because `parseListViewEntry` maps a cell to a header
# by asking which header's span the cell sits inside -- so a fixture with no
# header row produces rows with no cells at all, which is the state several of
# these cases spend their time distinguishing from a real answer.
OVERVIEW_COLUMNS = (
    ("Icon", 0, 40),
    ("Type", 40, 200),
    ("Name", 240, 200),
    ("Distance", 440, 120),
)

# The generic wording the Type column carries for every cloud in a site.
CLOUD_TYPE = "Harvestable Cloud"

# The client's own sentence, byte for byte from #456's live capture. The
# misspelling of "transfering" is the client's and is deliberately not tidied:
# it is what the matcher has to agree with.
MINING_RANGE_REFUSAL = (
    "Gas Cloud Harvester II deactivates without transfering ore to your cargo"
    " hold because your ship has strayed to a distance of 1628.94 m, beyond its"
    " mining range of 1500.00 m.")

# A `(notify)` line that is not it, so the matcher's three substrings are shown
# declining something rather than only accepting. Recorded: the client writes
# this one about a module being reloaded while it runs.
OTHER_NOTIFY_LINE = (
    "You cannot load or unload Gas Cloud Harvester II while it is active.")

# A `(notify)` line carrying **both** distance markers and not the harvester's
# own refusal. **Nobody has recorded this sentence** -- it is built to have the
# shape the first of the three substrings exists to decline, which is the only
# way to show that substring doing anything. Without it, a matcher that had
# dropped `deactivates without transfering ore` would pass every other case in
# this file, since nothing else the client says carries two distances.
ANOTHER_RANGE_LINE = (
    "Your tractor beam stops working because your ship has strayed to a"
    " distance of 22000.00 m, beyond its mining range of 20000.00 m.")


def label(text, region):
    return node("EveLabelMedium", {"_setText": text}, region=region)


def overview_row(cells, displayed=True, targeted=False, targeting=False):
    """One `OverviewScrollEntry`, with a cell only for the columns named.

    `displayed` writes the client's own `_display` entry, which is what
    `overviewEntryIsDisplayed` reads -- rather than removing the row, since the
    whole point is that a hidden row is *in* the tree with a plausible region.
    """
    entries = {"_name": "overviewEntry"}
    if not displayed:
        entries["_display"] = False
    y = 100 + overview_row.next_y
    overview_row.next_y += 20
    icon_children = []
    if targeted:
        icon_children.append(
            node("Sprite", {"_name": "targetedByMeIndicator"},
                 region=(2, y, 12, 12)))
    if targeting:
        icon_children.append(
            node("Sprite", {"_name": "targeting"}, region=(2, y, 12, 12)))
    children = [
        node("SpaceObjectIcon", {"_name": "mainIcon"}, icon_children,
             region=(0, y, 32, 16)),
    ] + [
        label(cells[column], (x + 4, y, width - 8, 16))
        for column, x, width in OVERVIEW_COLUMNS if column in cells
    ]
    return node("OverviewScrollEntry", entries, children,
                region=(0, y, 560, 16))


overview_row.next_y = 0


def overview_window(rows):
    """The overview, open, with a real header row over real rows.

    The header container is nested inside the scroll node because
    `parseOverviewWindow` looks for the headers *under* it, and the rows are
    siblings of the scroll rather than children of it -- `OverviewScrollEntry`
    itself contains the word `scroll`, so a row inside would otherwise be picked
    as the scroll node by a rule that takes the first match.
    """
    headers = node("OverviewHeaders", {"_name": "headers"}, [
        label(column, (x, 60, width, 16))
        for column, x, width in OVERVIEW_COLUMNS
    ], region=(0, 60, 560, 16))
    scroll = node("OverviewScroll", {"_name": "scroll"}, [headers],
                  region=(0, 60, 560, 16))
    return node("OverviewWindow", {"_name": "overview"},
                [scroll] + list(rows), region=(1200, 40, 560, 400))


def cloud(name, distance="833 m", type_text=CLOUD_TYPE, **kwargs):
    cells = {"Icon": "-", "Type": type_text, "Distance": distance}
    if name is not None:
        cells["Name"] = name
    return overview_row(cells, **kwargs)


def ship_ui(top_ramps=(True, True), middle_ramps=(True,), manoeuvre=None):
    """A ship UI with real module rows either side of a real capacitor.

    `groupShipUIModulesIntoRows` splits the rows by their vertical centre
    against the capacitor's, so the geometry here is what decides which row a
    module lands in -- and `None` in a ramp tuple leaves the `ramp_active` entry
    **out of the tree**, which is what a module that is not cycling looks like.
    """
    def slot(index, ramp, y):
        entries = {"_name": "moduleButton"}
        if ramp is not None:
            entries["ramp_active"] = ramp
        x = 100 + index * 40
        # The button's own region is (0, 0) inside the slot: a child's
        # `_displayX`/`_displayY` are offsets from its parent, and
        # `totalDisplayRegion` accumulates them -- which is what decides both
        # the row a module lands in and the order `moduleButtonsLeftToRight`
        # puts it in.
        return node("ShipSlot", {"_name": "slot"}, [
            node("ModuleButton", entries, region=(0, 0, 32, 32)),
        ], region=(x, y, 32, 32))

    gauges = [
        node("Sprite", {"_name": gauge, "_lastValue": 1.0},
             region=(10, 200, 8, 8))
        for gauge in ("structureGauge", "armorGauge", "shieldGauge")
    ]
    indication = []
    if manoeuvre is not None:
        indication = [
            node("Container", {"_name": "indicationContainer"},
                 [label(manoeuvre, (300, 300, 200, 16))],
                 region=(300, 300, 200, 16)),
        ]
    return node("ShipUI", {"_name": "shipUI"}, [
        node("CapacitorContainer", {"_name": "capacitor"},
             region=(0, 200, 200, 20)),
    ] + gauges + indication
        + [slot(index, ramp, 150) for index, ramp in enumerate(top_ramps)]
        + [slot(index, ramp, 200) for index, ramp in enumerate(middle_ramps)],
        region=(0, 100, 600, 200))


def selected_item_window(name):
    return node("SelectedItemWnd", {"_name": "selectedItem"}, [
        label(name, (10, 500, 200, 16)),
        node("ButtonIcon", {"_name": "selectedItemOrbit"},
             region=(20, 530, 32, 32)),
    ], region=(0, 480, 300, 120))


def game_log(lines):
    """The host's own synthetic node, as `botlab_host.py` appends it.

    A direct child of the root and carrying **no display region**, which is what
    keeps it invisible to every other parser in that module -- and what makes a
    fixture that got the shape wrong read as a host with no game log at all,
    which is `Nothing` rather than an empty list.
    """
    return {
        "pythonObjectAddress": str(next(_TREE_ADDRESS)),
        "pythonObjectTypeName": "MacOsHostSyntheticGameLog",
        "dictEntriesOfInterest": {},
        "children": [
            {
                "pythonObjectAddress": str(next(_TREE_ADDRESS)),
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


_TREE_ADDRESS = iter(range(300000, 699999))


def tree_with(children):
    return {
        "pythonObjectAddress": str(next(_TREE_ADDRESS)),
        "pythonObjectTypeName": "UIRoot",
        "dictEntriesOfInterest": {
            "_displayX": 0, "_displayY": 0,
            "_displayWidth": 1920, "_displayHeight": 1080,
        },
        "children": list(children),
    }


def reading_binding(name, children):
    """A `let` binding of `name` to a real parsed reading."""
    return ("%s = EveOnline.MemoryReading.decodeMemoryReadingFromString %s"
            " |> Result.toMaybe"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUITreeWithDisplayRegionFromUITree"
            " |> Maybe.map EveOnline.ParseUserInterface"
            ".parseUserInterfaceFromUITree" % (
                name, elm_json_literal(tree_with(children))))


def cloud_search_binding(name, reading, prefix=None):
    return ("%s = %s |> Maybe.map (\\parsed -> cloudSearch %s"
            " (parsed.overviewWindows |> List.concatMap .entries))" % (
                name, reading,
                "Nothing" if prefix is None else "(Just %s)" % json.dumps(prefix)))


def situation(propulsion="Just ModuleIsRunning", orbiting=True,
              panel_shows=True, orbit_button=True, locked=True,
              locking=False, harvesters_not_running="[]",
              panel_unanswered=0, lock_unanswered=0):
    """A `HarvestSituation` written out, since it is a record of plain facts.

    Written here rather than derived from a reading on purpose: what these cases
    are about is the **ordering** over the situations, including several a
    single fixture cannot be in at once, and `harvestStep` takes the record
    precisely so they can be asked for directly. `harvestSituationFromContext`
    is what builds one from a client, and it is read out of the source
    separately.
    """
    return ("{ propulsionModule = %s"
            ", shipIsOrbiting = %s"
            ", panelShowsTheCloud = %s"
            ", orbitButtonIsOffered = %s"
            ", cloudReadsLocked = %s"
            ", cloudReadsLocking = %s"
            ", harvestersNotRunning = %s"
            ", counters = { panelSelectUnansweredReadings = %d"
            ", lockUnansweredReadings = %d } }" % (
                propulsion, orbiting, panel_shows, orbit_button, locked,
                locking, harvesters_not_running,
                panel_unanswered, lock_unanswered))


class GasHufferRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-harvest-repl-")
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
    return open_repl(GasHufferRepl)


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a row, a module or a log line, that it is
    there.

    Nearly every case below is of the form "the rule declined this" or "the rule
    took that one", and a fixture that never decoded produces a reading with no
    overview, no ship UI and no game log -- which answers exactly the same way,
    for the wrong reason, silently.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_real_parser_keys_the_overview_cells_by_the_real_header_row(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.overviewWindows >> List.concatMap .entries"
            " >> List.map (\\entry -> ( entry.objectType, entry.objectName )))"
        ], definitions=[reading_binding(
            "reading", [overview_window([cloud("Fullerite-C84")])])])[0]
        self.assertEqual(
            printed,
            'Just [(Just "%s",Just "Fullerite-C84")]' % CLOUD_TYPE)

    def test_a_hidden_row_is_in_the_tree_with_a_plausible_region(self):
        """The state the `_display` filter is about, produced as the client
        produces it: the row is present and parsed, and only `_display` says
        it is not on screen."""
        rows, displayed = self.repl.rendered([
            "reading |> Maybe.map (.overviewWindows"
            " >> List.concatMap .entries >> List.length)",
            "reading |> Maybe.map (.overviewWindows"
            " >> List.concatMap .entries >> List.map overviewEntryIsDisplayed)",
        ], definitions=[reading_binding("reading", [overview_window([
            cloud("Fullerite-C84", displayed=False),
            cloud("Fullerite-C50"),
        ])])])
        self.assertEqual(rows, "Just 2")
        self.assertEqual(displayed, "Just [False,True]")

    def test_the_module_rows_come_back_either_side_of_the_capacitor(self):
        top, middle = self.repl.rendered([
            "reading |> Maybe.andThen .shipUI"
            " |> Maybe.map (harvesterModulesFromShipUI >> List.length)",
            "reading |> Maybe.andThen .shipUI"
            " |> Maybe.map (propulsionModuleFromShipUI >> (/=) Nothing)",
        ], definitions=[reading_binding("reading", [ship_ui()])])
        self.assertEqual(top, "Just 2")
        self.assertEqual(middle, "Just True")

    def test_the_lock_indicators_are_the_parsers_own_answer(self):
        """`cloudReadsLocked` and `cloudReadsLocking` are what the harvest rule
        orders the lock and the harvesters by, and they are two sprites under
        the row's own icon rather than anything this file could shape by hand.
        """
        printed = self.repl.rendered([
            "reading |> Maybe.map (.overviewWindows >> List.concatMap .entries"
            " >> List.map (\\entry -> ( entry.commonIndications.targetedByMe"
            ", entry.commonIndications.targeting )))"
        ], definitions=[reading_binding("reading", [overview_window([
            cloud("Fullerite-C84", targeted=True),
            cloud("Fullerite-C50", targeting=True),
            cloud("Fullerite-C10"),
        ])])])[0]
        self.assertEqual(printed,
                         "Just [(True,False),(False,True),(False,False)]")

    def test_the_game_log_arrives_as_entries_rather_than_as_nothing(self):
        """`Nothing` here is a host carrying no game log at all, which every
        matcher below would decline for a reason that is not the rule's."""
        printed = self.repl.rendered([
            "reading |> Maybe.map .gameLogEntriesSinceLastReading"
            " |> Maybe.map (Maybe.map (List.map .channel))"
        ], definitions=[reading_binding("reading", [
            game_log([("notify", MINING_RANGE_REFUSAL)])])])[0]
        self.assertEqual(printed, 'Just (Just [Just "notify"])')


class TheCloudTakenIsTheHighestTrailingNumberTest(unittest.TestCase):
    """#461's headline: parse the digits, do not sort the string.

    `Fullerite-C84` against `Fullerite-C50` is the pair the issue quotes off the
    live grid, and it is the pair a lexical sort gets right by accident.
    `Fullerite-C100` is the one that separates the two implementations.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def order_of(self, names):
        """The names sorted by the shipped rule, as the bot would take them."""
        return self.repl.rendered([
            "%s |> List.sortBy gasCloudOrder"
            % json.dumps(names).replace("[", "[ ").replace("]", " ]")
        ])[0]

    def test_the_trailing_digits_are_read_as_a_number(self):
        printed = self.repl.rendered([
            '[ trailingNumberFromName "Fullerite-C84"'
            ', trailingNumberFromName "Fullerite-C100"'
            ', trailingNumberFromName "Fullerite-C50"'
            ', trailingNumberFromName "Fullerite-C0" ]'
        ])[0]
        self.assertEqual(printed,
                         "[Just 84,Just 100,Just 50,Just 0]")

    def test_the_live_pair_is_ordered_the_way_the_issue_says(self):
        self.assertEqual(self.order_of(["Fullerite-C50", "Fullerite-C84"]),
                         '["Fullerite-C84","Fullerite-C50"]')

    def test_a_three_digit_suffix_beats_a_two_digit_one(self):
        """The case a lexical sort fails: `1` sorts before `8`."""
        self.assertEqual(
            self.order_of(["Fullerite-C84", "Fullerite-C100",
                           "Fullerite-C50"]),
            '["Fullerite-C100","Fullerite-C84","Fullerite-C50"]')

    def test_the_chosen_row_is_the_highest_numbered_one_on_a_real_grid(self):
        """End to end, over rows the real parser produced.

        The highest-numbered cloud is deliberately neither first nor last in
        the overview, so a rule answering about `List.head` alone fails.
        """
        chosen, order = self.repl.rendered([
            "search |> Maybe.andThen .chosen |> Maybe.andThen .objectName",
            "search |> Maybe.map .namesInTheOrderTheyWouldBeTaken",
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C50"),
                cloud("Fullerite-C100"),
                cloud("Fullerite-C84"),
            ])]),
            cloud_search_binding("search", "reading"),
        ])
        self.assertEqual(chosen, 'Just "Fullerite-C100"')
        self.assertEqual(
            order,
            'Just ["Fullerite-C100","Fullerite-C84","Fullerite-C50"]')

    def test_a_row_that_is_not_a_cloud_is_not_a_candidate(self):
        printed = self.repl.rendered([
            "search |> Maybe.map"
            " (\\s -> ( s.cloudRowsInTheReading"
            ", s.namesInTheOrderTheyWouldBeTaken ))",
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C84"),
                cloud("Sansha Battleship", type_text="Battleship"),
            ])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(printed, 'Just (1,["Fullerite-C84"])')

    def test_the_status_line_says_which_cloud_and_why(self):
        """A lexical sort agrees with the numeric one on most pairs, so a run
        that had reverted to one would look correct until the day a site held a
        three-digit cloud. The clause names the rule, not just the cloud."""
        clause = self.repl.strings([
            'Maybe.withDefault "<no reading>" (Maybe.map describeCloudSearch search)'
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C50"), cloud("Fullerite-C84")])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertIn("harvesting 'Fullerite-C84'", clause)
        self.assertIn("highest trailing number", clause)
        self.assertIn("2 candidate(s)", clause)


class ANameWithNoTrailingNumberIsUnrankableTest(unittest.TestCase):
    """Unrankable, and explicitly not zero.

    Read as zero, such a name sorts behind every numbered cloud and is taken
    only when there are none -- which is the reading that would never take it
    when it is the only cloud on the grid. Both halves are asked, because a rule
    answering `Just 0` passes the first on its own.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_an_unnumbered_name_answers_nothing_rather_than_zero(self):
        printed = self.repl.rendered([
            '[ trailingNumberFromName "Harvestable Cloud"'
            ', trailingNumberFromName ""'
            ', trailingNumberFromName "Fullerite" ]'
        ])[0]
        self.assertEqual(printed, "[Nothing,Nothing,Nothing]")

    def test_the_order_puts_it_behind_every_number_including_zero(self):
        """Zero is the discriminating neighbour: a rule reading an unrankable
        name as `0` would tie with `Fullerite-C0` and could sort either way."""
        printed = self.repl.rendered([
            '[ gasCloudOrder "Fullerite-C84"'
            ', gasCloudOrder "Fullerite-C0"'
            ', gasCloudOrder "Harvestable Cloud" ]'
        ])[0]
        self.assertEqual(printed, "[(0,-84),(0,0),(1,0)]")
        self.assertEqual(
            self.repl.rendered([
                '[ "Harvestable Cloud", "Fullerite-C0" ] |> List.sortBy gasCloudOrder'
            ])[0],
            '["Fullerite-C0","Harvestable Cloud"]')

    def test_it_is_still_taken_when_it_is_the_only_cloud_on_the_grid(self):
        """The half that reading it as zero would get wrong."""
        chosen = self.repl.rendered([
            "search |> Maybe.andThen .chosen |> Maybe.andThen .objectName",
        ], definitions=[
            reading_binding("reading",
                            [overview_window([cloud("Harvestable Cloud")])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(chosen, 'Just "Harvestable Cloud"')

    def test_a_numbered_cloud_beside_it_wins(self):
        chosen = self.repl.rendered([
            "search |> Maybe.andThen .chosen |> Maybe.andThen .objectName",
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Harvestable Cloud"), cloud("Fullerite-C50")])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(chosen, 'Just "Fullerite-C50"')

    def test_the_status_line_says_it_was_ranked_last_rather_than_as_zero(self):
        clause = self.repl.strings([
            'Maybe.withDefault "<no reading>" (Maybe.map describeCloudSearch search)'
        ], definitions=[
            reading_binding("reading",
                            [overview_window([cloud("Harvestable Cloud")])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertIn("ranked last rather than as zero", clause)

    def test_a_row_with_no_name_at_all_is_declined_and_counted(self):
        """Absent evidence declines: a row whose Name column is not there is
        one the ordering cannot rank and the prefix cannot be matched against,
        and it is separated from the prefix's own declines because the two are
        fixed in different places."""
        printed = self.repl.rendered([
            "search |> Maybe.map (\\s -> ( s.namelessCloudRows"
            ", s.namesInTheOrderTheyWouldBeTaken, s.chosen /= Nothing ))",
        ], definitions=[
            reading_binding("reading",
                            [overview_window([cloud(None)])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(printed, "Just (1,[],False)")


class AHiddenOverviewRowIsNeverActedOnTest(unittest.TestCase):
    """The standing rule for every overview consumer in this repo.

    The overview virtualises: a hidden row keeps a plausible region pointing at
    whatever was recycled into its place, so clicking it is worse than a no-op.
    Everything this bot does on a grid begins with a click on one of these rows
    -- the selection the Orbit button acts on, and the Ctrl+click that locks --
    and the log would name the cloud throughout, because the row the bot read is
    not the row the click landed on.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_hidden_row_is_passed_over_even_when_it_would_have_won(self):
        """The discriminating arrangement: the hidden cloud is the
        highest-numbered one, so a filter that had been dropped takes exactly
        the row it must not."""
        chosen, hidden = self.repl.rendered([
            "search |> Maybe.andThen .chosen |> Maybe.andThen .objectName",
            "search |> Maybe.map .hiddenCloudRows",
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C100", displayed=False),
                cloud("Fullerite-C50"),
            ])]),
            cloud_search_binding("search", "reading"),
        ])
        self.assertEqual(chosen, 'Just "Fullerite-C50"')
        self.assertEqual(hidden, "Just 1")

    def test_a_grid_of_nothing_but_hidden_clouds_harvests_nothing(self):
        printed = self.repl.rendered([
            "search |> Maybe.map (\\s -> ( s.cloudRowsInTheReading"
            ", s.hiddenCloudRows, s.chosen /= Nothing ))",
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C84", displayed=False),
                cloud("Fullerite-C50", displayed=False),
            ])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(printed, "Just (2,2,False)")

    def test_the_status_line_says_the_rows_were_hidden(self):
        clause = self.repl.strings([
            'Maybe.withDefault "<no reading>" (Maybe.map describeCloudSearch search)'
        ], definitions=[
            reading_binding("reading", [overview_window([
                cloud("Fullerite-C100", displayed=False),
                cloud("Fullerite-C50"),
            ])]),
            cloud_search_binding("search", "reading"),
        ])[0]
        self.assertIn("1 not rendered", clause)
        self.assertIn("recycled", clause)

    def test_a_row_with_no_display_entry_at_all_reads_as_shown(self):
        """The client writes `_display` only where it has something to say, and
        every recorded row that is on screen carries none -- so an absent entry
        must not be read as hidden, which would make every row invisible."""
        self.assertEqual(
            self.repl.rendered([
                "search |> Maybe.map (\\s -> ( s.hiddenCloudRows"
                ", s.chosen /= Nothing ))",
            ], definitions=[
                reading_binding("reading",
                                [overview_window([cloud("Fullerite-C84")])]),
                cloud_search_binding("search", "reading"),
            ])[0],
            "Just (0,True)")

    def test_the_filter_is_in_the_one_place_the_candidates_come_from(self):
        """Structural, because the cases above cannot see a second list of rows
        built somewhere else. Every overview row this bot **acts on** comes out
        of `cloudSearch`, and the filter is applied there.

        #462 added the second reader of the overview and it is deliberately
        *not* filtered, which is why this case names both rather than counting
        one. The two want opposite directions from a hidden row. `cloudSearch`
        is choosing something to click, and a hidden row's region belongs to
        whatever was recycled into it, so acting on one acts on the wrong
        object. `gridEvidenceFromReading` is choosing nothing: it asks whether
        anything on this grid means leave, a row it declined to read is a thing
        it would not have left over, and reading a recycled row's stale name is
        an unnecessary retreat rather than a click on a stranger's ship.
        """
        body = collapsed(block("cloudSearch"))
        self.assertIn("List.filter overviewEntryIsDisplayed", body)
        readers = [name for name, text in top_level_declarations(
            bot_source()).items()
            if ".overviewWindows" in collapsed(text)]
        self.assertEqual(
            readers, ["cloudSearchFromReading", "gridEvidenceFromReading"],
            readers)
        self.assertNotIn(
            "overviewEntryIsDisplayed",
            collapsed(block("gridEvidenceFromReading")))


class ThePrefixNarrowsWithoutReorderingTest(unittest.TestCase):
    """`gas-cloud-name-prefix`, and what an unset one means.

    Unset takes every harvestable cloud, which is the useful default; an empty
    one can never reach the rule at all, since `valueTypeNonEmptyString` refuses
    it -- and `String.startsWith ""` is true of every row on the grid, which is
    what makes that guard matter more here than for most settings.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def search(self, prefix, names):
        return self.repl.rendered([
            "search |> Maybe.map (\\s -> ( s.namesInTheOrderTheyWouldBeTaken"
            ", s.declinedByThePrefix ))",
        ], definitions=[
            reading_binding("reading",
                            [overview_window([cloud(name) for name in names])]),
            cloud_search_binding("search", "reading", prefix=prefix),
        ])[0]

    def test_an_unset_prefix_takes_every_cloud(self):
        self.assertEqual(
            self.search(None, ["Fullerite-C50", "Amber Cytoserocin"]),
            'Just (["Fullerite-C50","Amber Cytoserocin"],0)')

    def test_a_prefix_declines_what_is_not_named_for_it(self):
        self.assertEqual(
            self.search("Fullerite-", ["Fullerite-C50", "Amber Cytoserocin"]),
            'Just (["Fullerite-C50"],1)')

    def test_it_is_a_prefix_rather_than_a_substring(self):
        self.assertEqual(
            self.search("Fullerite", ["Gas Fullerite-C50"]),
            'Just ([],1)')

    def test_case_and_surrounding_space_do_not_decide_it(self):
        self.assertEqual(
            self.search("  fullerite-  ", ["Fullerite-C50"]),
            'Just (["Fullerite-C50"],0)')

    def test_the_prefix_does_not_change_the_order(self):
        self.assertEqual(
            self.search("Fullerite-",
                        ["Fullerite-C50", "Fullerite-C100", "Fullerite-C84"]),
            'Just (["Fullerite-C100","Fullerite-C84","Fullerite-C50"],0)')


class TheHarvesterRefusalIsReportedAndNeverActedOnTest(unittest.TestCase):
    """The out-of-range line: read, carried, said, and acted on by nothing.

    The client states both distances, so acting on them looks available -- and
    is not: no command in this repository orbits at a *distance*, so a bot
    acting on this line could only press the same button and read the same
    refusal, forever. What it owes the operator is the two numbers.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def refusal_from(self, lines):
        return self.repl.rendered([
            "reading |> Maybe.map miningRangeRefusalFromGameLog",
        ], definitions=[reading_binding("reading", [game_log(lines)])])[0]

    def test_the_real_recorded_line_gives_both_numbers(self):
        self.assertEqual(
            self.refusal_from([("notify", MINING_RANGE_REFUSAL)]),
            'Just (Just { miningRangeMeters = "1500.00"'
            ', strayedToMeters = "1628.94" })')

    def test_a_sentence_carrying_both_distances_is_still_not_it(self):
        """What the first of the three substrings is for.

        Nothing else the client is recorded saying carries two distances, so
        without a sentence of this shape that substring could be dropped and
        every other case here would still pass.
        """
        self.assertEqual(self.refusal_from([("notify", ANOTHER_RANGE_LINE)]),
                         "Just Nothing")

    def test_another_notify_line_is_not_it(self):
        """The same channel, the same module named, and declined -- so the
        matcher is reading the client's sentence rather than the channel."""
        self.assertEqual(self.refusal_from([("notify", OTHER_NOTIFY_LINE)]),
                         "Just Nothing")

    def test_the_same_sentence_on_another_channel_is_declined(self):
        """#41's lesson from the other side: which channel a sentence arrives
        on is a thing to check rather than assume."""
        self.assertEqual(self.refusal_from([("info", MINING_RANGE_REFUSAL)]),
                         "Just Nothing")

    def test_a_sentence_with_no_number_after_a_marker_declines_it_all(self):
        """A distance this bot invented is worse than one it does not print."""
        self.assertEqual(
            self.refusal_from([(
                "notify",
                "Gas Cloud Harvester II deactivates without transfering ore to"
                " your cargo hold because your ship has strayed to a distance"
                " of some way, beyond its mining range of 1500.00 m.")]),
            "Just Nothing")

    def test_a_host_carrying_no_game_log_answers_nothing_rather_than_no(self):
        """`Nothing` from the channel is "nobody is listening", and it must not
        read as "the client did not complain"."""
        self.assertEqual(
            self.repl.rendered([
                "reading |> Maybe.map miningRangeRefusalFromGameLog",
                "reading |> Maybe.map"
                " (.gameLogEntriesSinceLastReading >> (==) Nothing)",
            ], definitions=[reading_binding("reading", [])]),
            ["Just Nothing", "Just True"])

    def test_the_verdict_survives_the_readings_after_it_with_an_age(self):
        """The whole reason it is in `BotMemory`: the entry is gone by the next
        reading, so a branch that read it and wrote nothing down would see it
        once and behave exactly as it did before."""
        printed = self.repl.rendered([
            "[ Nothing, Nothing, Nothing ]"
            " |> List.foldl (\\now held -> miningRangeRefusalAfterReading"
            " { before = held, refusalNow = now }) afterTheLine"
        ], definitions=[
            "seen = { strayedToMeters = \"1628.94\""
            ", miningRangeMeters = \"1500.00\" }",
            "afterTheLine = miningRangeRefusalAfterReading"
            " { before = Nothing, refusalNow = Just seen }",
        ])[0]
        self.assertEqual(
            printed,
            'Just { miningRangeMeters = "1500.00", readingsSince = 3'
            ', strayedToMeters = "1628.94" }')

    def test_the_status_line_names_both_numbers(self):
        clause = self.repl.strings([
            "describeMiningRange (Just { strayedToMeters = \"1628.94\""
            ", miningRangeMeters = \"1500.00\", readingsSince = 0 })"
        ])[0]
        self.assertIn("1628.94", clause)
        self.assertIn("1500.00", clause)
        self.assertIn("on this reading", clause)
        self.assertIn("not corrected", clause)

    def test_the_clause_ages_rather_than_reading_as_current(self):
        clause = self.repl.strings([
            "describeMiningRange (Just { strayedToMeters = \"1628.94\""
            ", miningRangeMeters = \"1500.00\", readingsSince = 412 })"
        ])[0]
        self.assertIn("412 reading(s) ago", clause)

    def test_a_session_that_never_hears_it_says_that_instead(self):
        clause = self.repl.strings(["describeMiningRange Nothing"])[0]
        self.assertIn("has not complained", clause)
        self.assertNotIn("OUT OF RANGE", clause)

    def test_the_status_line_reads_the_memory_and_no_decision_reads_it(self):
        """Reported, never acted on. A branch consulting the refusal is the
        re-orbit this whole design refuses, so the readers are counted."""
        self.assertIn("describeMiningRange context.memory.miningRangeRefusal",
                      collapsed(block("statusTextFromState")))
        readers = [name for name, text in top_level_declarations(
            bot_source()).items()
            if "miningRangeRefusal" in collapsed(text)]
        self.assertEqual(
            sorted(readers),
            ["initBotMemory", "miningRangeRefusalAfterReading",
             "miningRangeRefusalFromGameLog", "statusTextFromState",
             "updateMemoryForNewReadingFromGame"],
            readers)

    def test_nothing_orbits_on_the_strength_of_it(self):
        """The specific mutation: the harvest loop re-commanding an orbit
        because the client said the last one was too wide."""
        for name in ("harvestStep", "harvestSituationFromContext",
                     "actOnTheHarvestStep"):
            with self.subTest(name):
                self.assertNotIn("miningRange", collapsed(block(name)))


class TheHarvestLoopCommandsThingsInOrderTest(unittest.TestCase):
    """One rule with the whole ordering in it, executed rather than read.

    The order is the issue's own -- keep the propulsion module running, orbit
    the cloud, lock it, run both harvesters -- and what makes it worth writing
    as one rule is that every stage can fail to be reachable and each of those
    has to fall through to the next rather than holding the loop.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["harvestStep %s" % situation(**kwargs)])[0]

    def test_the_propulsion_module_comes_first(self):
        self.assertEqual(
            self.step(propulsion="Just ModuleIsNotRunning", orbiting=False,
                      locked=False, harvesters_not_running="[ 0, 1 ]"),
            "SwitchThePropulsionModuleOn")

    def test_a_running_propulsion_module_is_left_alone(self):
        """It is a toggle, so a press aimed at a module that is already on
        switches it off -- which is the failure #465 depends on not happening."""
        self.assertEqual(
            self.step(propulsion="Just ModuleIsRunning", orbiting=False,
                      panel_shows=False),
            "SelectTheCloud")

    def test_a_middle_row_this_reading_cannot_read_is_not_pressed_at(self):
        """Absent evidence declines: pressing Alt+F1 at a ship whose modules
        are arranged some other way presses whatever is bound there."""
        self.assertEqual(
            self.step(propulsion="Nothing", orbiting=False,
                      panel_shows=False),
            "SelectTheCloud")

    def test_the_orbit_is_a_selection_and_then_a_press(self):
        self.assertEqual(self.step(orbiting=False, panel_shows=False),
                         "SelectTheCloud")
        self.assertEqual(self.step(orbiting=False, panel_shows=True),
                         "PressTheOrbitButton")

    def test_a_ship_already_orbiting_is_not_re_commanded(self):
        """Re-issuing a manoeuvre restarts it, which is what the docking run-in
        cost another bot eight minutes of."""
        self.assertEqual(self.step(orbiting=True, locked=False),
                         "LockTheCloud")

    def test_a_panel_offering_no_orbit_button_falls_through_rather_than_waits(self):
        """The panel's button set is contextual, so absence is normal. The
        reading goes to the lock rather than being spent on a button that may
        simply not belong to this object."""
        self.assertEqual(
            self.step(orbiting=False, panel_shows=True, orbit_button=False,
                      locked=False),
            "LockTheCloud")

    def test_the_selection_is_bounded_and_expiry_harvests_without_an_orbit(self):
        """#257's shape on the hottest path this bot has: a panel that never
        comes to show the cloud would otherwise be clicked at forever."""
        self.assertEqual(
            self.step(orbiting=False, panel_shows=False, locked=False,
                      panel_unanswered=9),
            "SelectTheCloud")
        self.assertEqual(
            self.step(orbiting=False, panel_shows=False, locked=False,
                      panel_unanswered=10),
            "LockTheCloud")

    def test_the_lock_comes_before_the_harvesters(self):
        """A harvester runs on the active target, so running one before the
        lock lands is a press that achieves nothing."""
        self.assertEqual(
            self.step(locked=False, harvesters_not_running="[ 0, 1 ]"),
            "LockTheCloud")

    def test_a_lock_in_progress_is_waited_for_rather_than_re_asked(self):
        self.assertEqual(
            self.step(locked=False, locking=True,
                      harvesters_not_running="[ 0, 1 ]"),
            "WaitForTheLockToLand")

    def test_the_lock_is_bounded_too(self):
        self.assertEqual(
            self.step(locked=False, lock_unanswered=19), "LockTheCloud")
        self.assertEqual(
            self.step(locked=False, lock_unanswered=20,
                      harvesters_not_running="[ 0, 1 ]"),
            "NothingLeftToCommand")

    def test_each_harvester_that_is_not_cycling_is_run_in_turn(self):
        self.assertEqual(self.step(harvesters_not_running="[ 0, 1 ]"),
                         "RunTheHarvester 0")
        self.assertEqual(self.step(harvesters_not_running="[ 1 ]"),
                         "RunTheHarvester 1")

    def test_a_grid_with_everything_running_commands_nothing(self):
        self.assertEqual(self.step(), "NothingLeftToCommand")

    def test_the_status_clause_tells_the_two_silences_apart(self):
        """`NothingLeftToCommand` covers both "everything is running" and
        "nothing left that can be tried", which are the same silence from
        outside and want very different things from an operator."""
        running, given_up = self.repl.strings([
            "describeHarvestSituation %s" % situation(),
            "describeHarvestSituation %s" % situation(
                locked=False, lock_unanswered=20,
                harvesters_not_running="[ 0, 1 ]"),
        ])
        self.assertIn("both cycling", running)
        self.assertNotIn("GIVEN UP", running)
        self.assertIn("GIVEN UP ON", given_up)
        self.assertIn("nothing is being harvested", given_up)


class TheCountersAreAboutTheClientsAnswerTest(unittest.TestCase):
    """Both bounds count readings the client has not answered on.

    Advanced in `updateMemoryForNewReadingFromGame`, which is the only place
    that can write memory and the one place that never sees a decision -- so
    they keep counting whatever else holds the tree, which is #102's own
    placement argument. Folded over sessions here rather than asked once,
    because a counter that is right for one reading and wrong across a session
    is the defect this shape prevents.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def fold(self, answers):
        return self.repl.rendered([
            "[ %s ] |> List.foldl harvestCountersAfterReading"
            " initHarvestCounters" % ", ".join(answers)])[0]

    @staticmethod
    def answer(chosen=True, panel=False, locked=False):
        return ("{ cloudIsChosen = %s, panelShowsTheCloud = %s"
                ", cloudReadsLocked = %s }" % (chosen, panel, locked))

    def test_both_climb_while_the_client_says_nothing(self):
        self.assertEqual(
            self.fold([self.answer()] * 3),
            "{ lockUnansweredReadings = 3, panelSelectUnansweredReadings = 3 }")

    def test_each_resets_on_the_answer_it_is_waiting_for(self):
        self.assertEqual(
            self.fold([self.answer()] * 3 + [self.answer(panel=True)]),
            "{ lockUnansweredReadings = 4, panelSelectUnansweredReadings = 0 }")
        self.assertEqual(
            self.fold([self.answer()] * 3 + [self.answer(locked=True)]),
            "{ lockUnansweredReadings = 0, panelSelectUnansweredReadings = 4 }")

    def test_a_reading_with_no_cloud_starts_the_next_one_from_zero(self):
        """A session that harvests forty clouds counts each one on its own."""
        self.assertEqual(
            self.fold([self.answer()] * 5 + [self.answer(chosen=False)]),
            "{ lockUnansweredReadings = 0, panelSelectUnansweredReadings = 0 }")

    def test_the_memory_update_asks_the_same_cloud_search_the_decision_does(self):
        """#102: one fact settled in one place. The way this fails is a counter
        bounding an ask about a cloud the bot was not working on."""
        body = collapsed(block("updateMemoryForNewReadingFromGame"))
        self.assertIn("cloudSearchFromReading", body)
        self.assertIn("harvestCountersAfterReading", body)
        callers = [name for name, text in top_level_declarations(
            bot_source()).items()
            if "cloudSearch " in collapsed(text) and name != "cloudSearch"]
        self.assertEqual(callers, ["cloudSearchFromReading"], callers)

    def test_the_counters_advance_where_nothing_can_decline_to_advance_them(self):
        """The half #102 is about: the counter and the comparison are on two
        different schedules unless the counter is unconditional."""
        self.assertIn("harvestCounters", collapsed(
            block("updateMemoryForNewReadingFromGame")))
        self.assertNotIn("harvestCountersAfterReading",
                         collapsed(block("harvestStep")))


class TheModuleReadingIsTheRampWidgetsExistenceTest(unittest.TestCase):
    """The one question #456 records as unsettled, answered the safe way.

    Nobody has watched a gas harvester switch off and on, so whether it behaves
    like a weapon (a duty cycle, where `isActive` flickers false mid-cycle) or
    like a propulsion module (a real latch) is unknown. What #286 measured over
    61,948 observations settles it without needing to know: `ramp_active` is
    absent exactly when the `ShipModuleButtonRamps` widget does not exist, which
    is when the module is not cycling -- so the widget's *existence* is the one
    answer that is right whichever the harvester turns out to be.

    It fails towards not pressing, which is the direction that matters: a module
    button is a toggle, so a press aimed at one already running switches it off.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def states(self, top_ramps):
        return self.repl.rendered([
            "reading |> Maybe.andThen .shipUI"
            " |> Maybe.map (harvesterModulesFromShipUI"
            " >> List.map moduleRunningState)",
        ], definitions=[reading_binding(
            "reading", [ship_ui(top_ramps=top_ramps)])])[0]

    def test_a_module_with_a_ramp_widget_reads_as_running(self):
        self.assertEqual(self.states((True, True)),
                         "Just [ModuleIsRunning,ModuleIsRunning]")

    def test_a_ramp_reading_false_still_reads_as_running(self):
        """`Just False` is a weapon between cycles, which is a module that is
        on. Reading it as off is what makes a toggle oscillate."""
        self.assertEqual(self.states((False, False)),
                         "Just [ModuleIsRunning,ModuleIsRunning]")

    def test_a_module_with_no_ramp_widget_reads_as_not_running(self):
        self.assertEqual(self.states((None, None)),
                         "Just [ModuleIsNotRunning,ModuleIsNotRunning]")

    def test_the_two_harvesters_are_told_apart_by_position(self):
        """They share a `_name` and an icon texture on the measured hull, so
        position is not the safer identity -- it is the only one there is."""
        self.assertEqual(self.states((None, True)),
                         "Just [ModuleIsNotRunning,ModuleIsRunning]")
        self.assertIn("List.sortBy (.uiNode >> .totalDisplayRegion >> .x)",
                      collapsed(block("moduleButtonsLeftToRight")))

    def test_both_rows_are_read_through_the_one_sort(self):
        for name in ("harvesterModulesFromShipUI", "propulsionModuleFromShipUI"):
            with self.subTest(name):
                self.assertIn("moduleButtonsLeftToRight",
                              collapsed(block(name)))

    def test_nothing_reads_is_active_or_is_in_active_state(self):
        """#286: `isInActiveState` is `not isDeactivating` and is close to a
        constant, and `isActive` is the duty cycle under another name. A rule
        reading either as "switched on" presses a running harvester."""
        bodies = " ".join(collapsed(text) for text
                          in top_level_declarations(bot_source()).values())
        for field in (".isActive", "isInActiveState", "isDeactivating"):
            with self.subTest(field):
                self.assertNotIn(field, bodies)


class ThePropulsionModuleIsOnlyEverSwitchedOnTest(unittest.TestCase):
    """#465, held from the day the warp arrived rather than from the day it is
    written.

    Every other bot here funnels its warps through
    `ensureDronesRecalledAndPropulsionModuleDeactivatedBeforeWarping`, and this
    one must not: the propulsion module has to survive every warp this bot
    makes. So there is no shared helper to reach, and the one press that touches
    it only ever switches it on.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_no_declaration_deactivates_it_before_a_warp(self):
        """The shared helper every other bot in this repo funnels its warps
        through is not reachable from here, by not existing here.

        Read over the declaration names as well as their bodies, since what has
        to be absent is a *step*: a branch that presses the module's own hotkey
        to switch it off, whatever it is called.
        """
        # Over the declaration *bodies*, with their doc comments stripped:
        # `warpToTheHuntedSite`'s own comment names the helper it refuses to
        # reach, and a case that read that as code would be red from the day it
        # was written.
        bodies = " ".join(collapsed(text) for text
                          in top_level_declarations(bot_source()).values())
        for forbidden in ("ensureDronesRecalledAndPropulsionModuleDeactivated",
                          "deactivatePropulsionModule",
                          "SwitchThePropulsionModuleOff"):
            with self.subTest(forbidden):
                self.assertNotIn(forbidden, bodies)

    def test_the_warp_reaches_the_cascade_with_nothing_in_front_of_it(self):
        body = collapsed(block("warpToTheHuntedSite"))
        for helper in ("ensureDronesRecalled", "PropulsionModule",
                       "propulsionModule"):
            with self.subTest(helper):
                self.assertNotIn(helper, body)

    def test_the_one_press_that_touches_it_is_the_switch_on(self):
        pressers = [name for name, text in top_level_declarations(
            bot_source()).items()
            if "propulsionModuleHotkey" in collapsed(text)]
        self.assertEqual(sorted(pressers),
                         ["actOnTheHarvestStep", "propulsionModuleHotkey"],
                         pressers)
        self.assertIn("SwitchThePropulsionModuleOn",
                      collapsed(block("actOnTheHarvestStep")))

    def test_the_chord_is_alt_f1_and_a_bare_f1_is_a_different_press(self):
        """`F1` is a subsequence of `Alt+F1`, so a settling window that could
        not tell them apart would let the harvester's press suppress the
        propulsion module's -- on a toggle, silently."""
        alt_f1, f1, mismatch = self.repl.rendered([
            "stepPressedExactly propulsionModuleHotkey"
            " (hotkeyEffects propulsionModuleHotkey)",
            "stepPressedExactly [ EffectOnWindow.vkey_F1 ]"
            " (hotkeyEffects [ EffectOnWindow.vkey_F1 ])",
            "stepPressedExactly [ EffectOnWindow.vkey_F1 ]"
            " (hotkeyEffects propulsionModuleHotkey)",
        ])
        self.assertEqual([alt_f1, f1, mismatch], ["True", "True", "False"])

    def test_the_chord_releases_in_reverse(self):
        self.assertEqual(
            self.repl.rendered(["hotkeyEffects propulsionModuleHotkey"])[0],
            "[KeyDown (VirtualKeyCodeFromInt 18),KeyDown"
            " (VirtualKeyCodeFromInt 112),KeyUp (VirtualKeyCodeFromInt 112)"
            ",KeyUp (VirtualKeyCodeFromInt 18)]")


class TheGridIsWhatSaysTheShipHasArrivedTest(unittest.TestCase):
    """Harvest where there is a cloud, warp where there is not.

    Harvestable clouds exist only inside a gas site, so a reading whose overview
    carries one is a reading taken on a site -- the same argument saxrat's gate
    branch makes about acceleration gates, and it needs no memory of what the
    bot asked for.
    """

    def test_the_in_space_branch_harvests_before_it_warps(self):
        body = collapsed(block("huntAndHarvest"))
        for named in ("actOnTheHarvestStep", "warpToTheHuntedSite"):
            with self.subTest(named):
                self.assertIn(named, body)
        self.assertLess(body.index("actOnTheHarvestStep"),
                        body.index("warpToTheHuntedSite"), body)

    def test_a_ship_in_warp_is_not_sent_warping_again(self):
        """Re-opening the cascade on every reading of a warp that is already
        going where it was told is the repeat this declines."""
        body = collapsed(block("huntAndHarvest"))
        self.assertIn("shipIsWarping shipUI", body)
        self.assertIn("warpToTheHuntedSite", body)
        self.assertLess(body.index("shipIsWarping shipUI"),
                        body.index("warpToTheHuntedSite"), body)

    def test_the_site_clause_is_the_same_call_the_status_line_makes(self):
        self.assertIn("siteSearchFromContext", collapsed(block("huntAndHarvest")))
        self.assertIn("cloudSearchFromReading",
                      collapsed(block("statusTextFromState")))


class TheMutationsThisFileCatches(unittest.TestCase):
    """The list, so that a later reader can re-run them rather than trust it.

    Each of these fails at least one named case above. They are recorded rather
    than executed -- this suite has no mutation runner -- and the count is what
    the PR body quotes.

    1. the clouds sorted lexically by name rather than by their trailing digits,
       which is #461's headline and which only `Fullerite-C100` separates.
    2. `trailingNumberFromName` reading an unrankable name as `Just 0`, so a
       cloud with no number can never be taken when it is the only one there.
    3. `gasCloudOrder` folding the pair into one number, which is the same
       failure reachable without touching the parse.
    4. the ordering reversed, so the lowest-numbered cloud is taken.
    5. the `_display` filter dropped from `cloudSearch`, so a hidden row is
       acted on -- and the case that catches it hides the winning cloud.
    6. an absent `_display` entry read as hidden, so every row disappears.
    7. a row with no Name column defaulted to the empty name rather than
       declined.
    8. `gasCloudNameMatchesPrefix` weakened to `String.contains`.
    9. the cloud Type test dropped, so any overview row is a candidate.
    10. `moduleRunningState` reading `ramp_active` as `Just True` only, so a
        harvester between cycles reads as off and is toggled off.
    11. `moduleRunningState` reading `isInActiveState`, which #286 measured to
        be `not isDeactivating` and close to a constant.
    12. the module rows taken by list index rather than sorted by x.
    13. the propulsion module pressed whatever it reads, which is the toggle
        this bot must never make.
    14. a `deactivate before warping` step reintroduced in front of the warp.
    15. `stepPressedExactly` weakened to "contains every key of the chord", so
        `F1` and `Alt+F1` suppress each other's settling window.
    16. the harvesters run before the lock, so they press at no active target.
    17. the orbit re-commanded on a ship already orbiting.
    18. either give-up bound removed, so a panel or a lock the client never
        answers is asked for forever.
    19. either give-up bound moved by one.
    20. the counters advanced only on readings the harvest branch was reached,
        which is #102's attempt-counting shape.
    21. the counters not reset on a reading with no cloud, so one session's
        clouds share a budget.
    22. the mining-range matcher losing the `deactivates without transfering
        ore` clause, so any `(notify)` line naming two distances matches.
    23. the matcher moved to the `info` channel, where the client does not write
        it.
    24. a marker matched with no number after it reported as a distance.
    25. the refusal not written to `BotMemory`, so it is seen once and gone.
    26. the refusal's age never advancing, so a stale sighting reads as current.
    27. the status line dropping one of the two distances.
    28. a decision branch consulting the refusal, which is the re-orbit this
        whole design refuses.
    29. the warp reached without checking whether the ship is already warping.
    30. the harvest branch placed after the warp, so a ship on a grid warps
        again instead of harvesting.
    """

    def test_the_list_is_a_list(self):
        """`\\s*` rather than `\\s+`: Python 3.13 dedents a docstring at compile
        time, so the numbered lines reach here at column zero on a new
        interpreter and indented on an old one."""
        mutations = re.findall(r"^\s*\d+\. ", self.__doc__, re.M)
        self.assertEqual(
            len(mutations), 30,
            "the mutation list is not the length the PR body quotes")


if __name__ == "__main__":
    unittest.main()
