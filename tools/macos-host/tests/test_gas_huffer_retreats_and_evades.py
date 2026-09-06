"""The gas huffer's retreat: three destinations, a cloak, and staying gone.

Issue #463, under #456. #462 left this bot able to say on every reading whether
anything on the grid meant leave, and unable to leave. This is the leaving, and
six things about it are what the issue is emphatic about.

**Three destinations, in order, and the order is not interchangeable.** A
bookmark whose label starts with `retreat-bookmark-prefix`, else the overview row
matching `home-structure-name`, else any bookmark at all warped to at 100 km.
Each rung is asked here on a reading where the ones above it answer nothing, and
the fall-through between them is executed rather than argued -- a fallback that
can outrank the thing it is a fallback for is not a fallback.

**The `Warp to Within` prefix, never the whole string.** The parenthesised
distance in that entry is the client's *current default*, so an operator who
takes `Within 100 km` once by hand leaves the menu reading `Warp to Within (100
km)` afterwards. The cascade is driven against a real context menu the real
parser produced, carrying a different default from the one #463 measured, so a
rule comparing the whole string fails here rather than on a client somebody had
used.

**A bookmark's menu varies by kind**, and the cascade matches what it wants
rather than asserting a shape: one measured row offered `Approach Location` where
another offered `Align to`. A menu missing an expected entry answers `Err` and
the framework retries -- it does not wedge, and it does not pick something else.

**A cloak that is not fitted must not stall the evasion.** #456 records that
whether one is fitted at all is unverified: five modules were read on the
measured hull and none was identified as one. So `cloakAmongFittedModules`
answers four things and `evasionStep` falls through the two negative ones to the
celestial bounce.

**The row text is a `<t>`-joined blob**, Label then Folder, so the prefix match
is `String.startsWith` on the label portion. A folder named for the prefix does
not make every bookmark in it a retreat target.

**And the one this whole issue rests on: an evasion does not end on a reading the
bot cannot see.** `gridReadsClean` answers `True` for `GridIsClean` and for
nothing else, and both the step rule and the counters read that answer. The
counters are folded over whole sessions here rather than asked once, because a
rule that is right for one reading and wrong across a session is exactly the
defect that shape prevents.

## How these are checked

The rules are executed through the real `Bot.elm` in `elm repl`. Every Locations
row, every overview row and every context menu they are asked about is built by
running a UI tree through the **real** `EveOnline.ParseUserInterface`, so what
the cases assert on is what the bot would have been handed rather than a record
shaped by hand -- which also means a `RetreatDestination` here carries a
`uiNode` a click could really land on. Where a case is about a combination no
single fixture can be in at once -- a grid that is dirty, off the site, with a
cloak fitted and the client not answering it -- the rule is handed the record it
takes, which is why `evasionStep` takes one.

Every fixture is asserted to have *arrived* before anything is asked of it: a
tree that failed to decode and a rule that answered nothing read identically from
outside, which is the shape `prerequisites.elm_json_literal` exists for.

Confirmed by mutation, listed in `TheMutationsThisFileCatches`.

Nothing here reads a live game client, a running bot, or the recorded runs. Every
name in it is fictional, which is #456's rule.

    python3 -m unittest discover -s tools/macos-host/tests
"""
import json
import unittest

from prerequisites import ElmRepl, elm_json_literal, open_repl
from test_gas_huffer_scaffold import (
    GAS_HUFFER_DIR, bot_source, collapsed, node, top_level_declarations)

PREAMBLE = (
    "import Bot exposing (..)",
    "import EveOnline.MemoryReading",
    "import EveOnline.ParseUserInterface",
    "import EveOnline.BotFramework",
)

# The overview's own header row on this client, read off it on 2026-09-04 and
# quoted in #456. `parseListViewEntry` maps a cell to a header by asking which
# header's span the cell sits inside, so a fixture with no header row produces
# rows with no cells at all.
OVERVIEW_COLUMNS = (
    ("Icon", 0, 40),
    ("Type", 40, 200),
    ("Name", 240, 200),
    ("Distance", 440, 120),
)

# Obviously fictional, which is #456's rule: nothing naming a real bookmark,
# structure, system or corporation goes in this repository. The prefix is the
# shipped default, which names nobody's bookmarks either.
FICTIONAL_STRUCTURE = "Fictional IX - Example Refinery"
FICTIONAL_SAFE = "*example-safe"
FICTIONAL_FOLDER = "Example Folder"
FICTIONAL_PLAIN_BOOKMARK = "somewhere else entirely"

# The client's own separator between a Locations row's cells, quoted in
# `parseLocationsWindowPlaceEntry`'s comment from the 2024 recording:
# `...<t>Refinery<t>0<t>Y5C-YD<t>...`
CELL = "<t>"

_address = iter(range(1300000, 1999999))


def fresh_node(type_name, entries=None, children=(), region=None):
    return node(type_name, entries, children, region)


def label(text, region):
    return fresh_node("EveLabelMedium", {"_setText": text}, region=region)


# -- the Locations window ----------------------------------------------------


def place_entry(main_text, top):
    """One `PlaceEntry`, with its cells joined the way the client joins them.

    `parseLocationsWindowPlaceEntry` takes the row's **smallest** contained
    display text by area and calls that the whole row, so the fixture carries one
    label rather than a cell per column -- which is what the recording shows and
    what makes the `<t>` split necessary in the first place.
    """
    return fresh_node(
        "PlaceEntry", {"_name": "placeEntry"},
        [label(main_text, (4, top + 2, 240, 16))],
        region=(0, top, 260, 20))


def locations_window(rows):
    """The Locations window as *this* client renders it.

    `StandaloneBookmarkWnd` rather than `LocationsWindow`, which is #457: every
    vendored parser filtered the second name alone and answered `Nothing` on
    every reading while the window was open and populated.
    """
    return fresh_node("StandaloneBookmarkWnd", {"_name": "locations"},
                      list(rows), region=(40, 100, 260, 400))


def bookmark_rows(labels):
    return [place_entry(text, index * 20)
            for index, text in enumerate(labels)]


# -- the overview ------------------------------------------------------------


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


def structure_row(name=FICTIONAL_STRUCTURE, top=100, displayed=True):
    return overview_row(
        {"Icon": "-", "Type": "Example Citadel", "Name": name,
         "Distance": "84 km"}, top, displayed)


def celestial_row(name="Fictional VII", top=140, distance="4.2 AU"):
    """A row this bot counts as somewhere to bounce to.

    A Distance reading in **AU** is what "off this grid" means, and it is the
    only property `celestialsToBounceOffOnTheOverview` asks for.
    """
    return overview_row(
        {"Icon": "-", "Type": "Planet", "Name": name, "Distance": distance},
        top)


def cloud_row(name="Fullerite-C84", top=180):
    return overview_row(
        {"Icon": "-", "Type": "Harvestable Cloud", "Name": name,
         "Distance": "833 m"}, top)


# -- the context menus -------------------------------------------------------


def menu(entry_texts, left=600, top=200):
    """One context menu under the client's own `l_menu` layer.

    `parseContextMenusFromUITreeRoot` finds that layer among the root's *direct*
    children and takes its children as the menus, so both nodes are load-bearing
    and a fixture missing either parses to a reading with no menus at all --
    which is the state `getNextContextMenu` answers `Err` for, and which one case
    below is about telling apart from a menu that simply lacks an entry.
    """
    entries = [
        fresh_node("MenuEntry", {"_name": "menuEntry"},
                   [label(text, (2, index * 20 + 2, 200, 16))],
                   region=(left, top + index * 20, 200, 20))
        for index, text in enumerate(entry_texts)
    ]
    return fresh_node("Menu", {"_name": "menu"}, entries,
                      region=(left, top, 200, 20 * len(entry_texts)))


def menu_layer(menus):
    """The `l_menu` layer, given the menus in **cascade order** and reversed.

    `getNextContextMenu`'s own comment records why: *"the first/root node of the
    menu cascade we get in the reading from the game client is not the first in
    the list (inside `LayerCore` `l_menu`) but the last list item."* A fixture
    written in the order a reader expects therefore hands the cascade its
    submenu as the root, and every case then reads a rule that is looking in the
    wrong place -- which answers `Err` for a right-looking reason.
    """
    return fresh_node("LayerCore", {"_name": "l_menu"},
                      list(reversed(list(menus))),
                      region=(0, 0, 1920, 1080))


# The two top-level menus measured for #463, differing in the entry beside the
# warp -- one row offered `Approach Location` where another offered `Align to`.
# The distance in brackets is the client's own current default and is what a
# whole-string match would pin.
BOOKMARK_MENU_ALIGN = [
    "Warp to Within (0 m)", "Align to", "Show Info", "Add Waypoint",
    "Edit Location", "Remove Location",
]
BOOKMARK_MENU_APPROACH = [
    "Warp to Within (0 m)", "Approach Location", "Show Info", "Add Waypoint",
    "Edit Location", "Remove Location",
]

# The fixed distance submenu, in the order the client draws it. `Set Default` is
# the eighth entry and is what a random pick over the whole menu would eventually
# press.
DISTANCE_SUBMENU = [
    "Within 0 m", "Within 10 km", "Within 20 km", "Within 30 km",
    "Within 50 km", "Within 70 km", "Within 100 km", "Set Default",
]


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


def retreat_settings(prefix=None, home=None):
    return "{ bookmarkPrefix = %s, homeStructureName = %s }" % (
        json.dumps("*" if prefix is None else prefix),
        "Nothing" if home is None else "(Just %s)" % json.dumps(home))


def retreat_search_binding(name, reading, prefix=None, home=None):
    """A `RetreatSearch` built from a real parsed reading, or `Nothing`."""
    return ("%s = %s |> Maybe.map (\\r -> retreatSearch %s"
            " { locationsWindow = r.locationsWindow"
            ", overviewEntries = r.overviewWindows |> List.concatMap .entries"
            " })" % (name, reading, retreat_settings(prefix, home)))


def evasion_counters(readings=0, warp_unexecuted=0, longest=0, cloak=0):
    return ("{ readings = %d, warpUnexecutedReadings = %d"
            ", longestWarpUnexecutedReadings = %d"
            ", cloakUnansweredReadings = %d }" % (
                readings, warp_unexecuted, longest, cloak))


def situation(clean=False, docked=False, on_site=False, warping=False,
              destination="Nothing",
              cloak="(NoCloakAmongTheModulesIdentified 5)", celestials=3,
              rotation=0, counters=None):
    """An `EvasionSituation` written out, since it is a record of plain facts.

    Written here rather than derived from a reading on purpose: these cases are
    about the *combination*, including several no single fixture can be in at
    once -- a grid that is dirty, off the site, with a cloak fitted and the
    client not answering it -- and `evasionStep` takes the record precisely so
    they can be asked for directly.
    """
    return ("{ gridIsClean = %s"
            ", docked = %s"
            ", stillOnTheHarvestSite = %s"
            ", shipIsWarping = %s"
            ", destination = %s"
            ", cloak = %s"
            ", celestialsOnTheOverview = %d"
            ", celestialRotation = %d"
            ", counters = %s }" % (
                "True" if clean else "False",
                "True" if docked else "False",
                "True" if on_site else "False",
                "True" if warping else "False",
                destination, cloak, celestials, rotation,
                counters if counters is not None else evasion_counters()))


def fitted(tooltip=None, running=False):
    return "{ tooltipTexts = %s, runningState = %s }" % (
        "[]" if tooltip is None else "[ %s ]" % json.dumps(tooltip),
        "ModuleIsRunning" if running else "ModuleIsNotRunning")


def answer(clean=False, docked=False, warping=False, cloak_answered=True):
    return ("{ gridIsClean = %s, docked = %s, shipIsWarping = %s"
            ", cloakAnsweredTheAsk = %s }" % (
                "True" if clean else "False",
                "True" if docked else "False",
                "True" if warping else "False",
                "True" if cloak_answered else "False"))


class RetreatRepl(ElmRepl):
    def __init__(self, **kwargs):
        kwargs.setdefault("prefix", "gas-huffer-retreat-repl-")
        kwargs.setdefault("app_dir", GAS_HUFFER_DIR)
        kwargs.setdefault("preamble", PREAMBLE)
        super().__init__(**kwargs)

    def rendered(self, expressions, definitions=()):
        """Each answer rendered whole, constructor and payload.

        `Debug.toString` rather than a battery of equalities: one answer per
        question that names *which* constructor the rule gave and what it
        carried, so a rule answering the right constructor with the wrong payload
        fails rather than passing on whichever equality a case asked.
        """
        return self.strings(["Debug.toString (%s)" % expression
                             for expression in expressions],
                            definitions=list(definitions))


def repl():
    return open_repl(RetreatRepl)


class TheFixturesReachTheParserTest(unittest.TestCase):
    """Before anything is asked of a row, that it is there.

    Nearly every case below is of the form "this rung answered" or "that one did
    not", and a fixture that never decoded produces a reading with no Locations
    window and no overview -- which answers `NowhereToRunTo` for the
    right-looking reason, silently and for the wrong one.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_locations_rows_come_back_off_the_real_parser(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.locationsWindow"
            " >> Maybe.map (.placeEntries >> List.map .mainText))"
        ], definitions=[reading_binding("reading", [locations_window(
            bookmark_rows([FICTIONAL_SAFE + CELL + FICTIONAL_FOLDER,
                           FICTIONAL_PLAIN_BOOKMARK]))])])[0]
        self.assertEqual(
            printed,
            'Just (Just ["%s<t>%s","%s"])' % (
                FICTIONAL_SAFE, FICTIONAL_FOLDER, FICTIONAL_PLAIN_BOOKMARK))

    def test_the_overview_rows_come_back_with_their_cells(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.overviewWindows"
            " >> List.concatMap .entries"
            " >> List.map (\\e -> ( e.objectName, e.objectDistance )))"
        ], definitions=[reading_binding("reading", [overview_window([
            structure_row(),
            celestial_row("Fictional VII", 140, "4.2 AU"),
        ])])])[0]
        self.assertEqual(
            printed,
            'Just [(Just "%s",Just "84 km"),(Just "Fictional VII",'
            'Just "4.2 AU")]' % FICTIONAL_STRUCTURE)

    def test_the_context_menu_comes_back_with_its_entries(self):
        printed = self.repl.rendered([
            "reading |> Maybe.map (.contextMenus"
            " >> List.map (.entries >> List.map .text))"
        ], definitions=[reading_binding(
            "reading", [menu_layer([menu(BOOKMARK_MENU_ALIGN)])])])[0]
        self.assertEqual(
            printed,
            "Just [%s]" % json.dumps(BOOKMARK_MENU_ALIGN).replace(", ", ","))

    def test_a_two_level_cascade_arrives_root_first(self):
        """`menu_layer`'s reversal, executed -- without it every cascade case
        would be asking the rule about the submenu and reading `Err` back for a
        reason that has nothing to do with the rule."""
        printed = self.repl.rendered([
            "reading |> Maybe.map (.contextMenus >> List.reverse"
            " >> List.map (.entries >> List.head"
            " >> Maybe.map .text >> Maybe.withDefault \"\"))"
        ], definitions=[reading_binding("reading", [menu_layer([
            menu(BOOKMARK_MENU_ALIGN), menu(DISTANCE_SUBMENU, top=400),
        ])])])[0]
        self.assertEqual(printed, 'Just ["Warp to Within (0 m)","Within 0 m"]')


class TheLabelIsTheFirstCellTest(unittest.TestCase):
    """The prefix is matched against a label, not against the row's whole text.

    The client renders a Locations row as its cells joined by `<t>`, Label then
    Folder. Matching the blob would make a *folder* named for the prefix turn
    every bookmark in it into a retreat target -- a widening in the one direction
    that decides where this ship is sent unattended -- and it would stop matching
    the day the client puts another column in front.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_label_is_taken_from_in_front_of_the_separator(self):
        joined, plain, trailing = self.repl.strings([
            "bookmarkLabel %s" % json.dumps(
                FICTIONAL_SAFE + CELL + FICTIONAL_FOLDER),
            "bookmarkLabel %s" % json.dumps(FICTIONAL_PLAIN_BOOKMARK),
            "bookmarkLabel %s" % json.dumps("  " + FICTIONAL_SAFE + "  " + CELL),
        ])
        self.assertEqual(joined, FICTIONAL_SAFE)
        # A row carrying no separator at all is its own label, which is what
        # makes this safe to run over every row rather than only joined ones.
        self.assertEqual(plain, FICTIONAL_PLAIN_BOOKMARK)
        self.assertEqual(trailing, FICTIONAL_SAFE)

    def test_a_folder_named_for_the_prefix_is_not_a_retreat_target(self):
        """The widening this exists for: matching the blob, or matching it
        loosely.

        Both rows below carry the prefix *somewhere*, and only the first carries
        it where the operator put it. `String.startsWith` on the blob happens to
        agree with `String.startsWith` on the label for any prefix that does not
        itself span the separator, so what this case really separates is the
        `contains`-shaped widening -- which is the direction a later edit would
        take to "make it match more bookmarks".
        """
        answers = self.repl.evaluate([
            "bookmarkLabelStartsWithPrefix \"*\" %s" % json.dumps(
                FICTIONAL_SAFE + CELL + FICTIONAL_FOLDER),
            "bookmarkLabelStartsWithPrefix \"*\" %s" % json.dumps(
                FICTIONAL_PLAIN_BOOKMARK + CELL + "*" + FICTIONAL_FOLDER),
        ])
        self.assertEqual(answers, [True, False])

    def test_the_label_is_what_the_operator_is_shown_as_well(self):
        """`bookmarkLabel` has two readers and the second is the one a person
        acts on: the clause and the decision line both name the bookmark, and a
        blob printed there is a name nobody can find in their own client.

        Which is also what makes the split load-bearing rather than decorative --
        for a prefix that does not span the separator the *match* would answer
        the same either way, and the printed name would not.
        """
        printed = self.repl.strings([
            "describeRetreatSearch { settings ="
            " { bookmarkPrefix = \"*\", homeStructureName = Nothing }"
            ", locationsWindowIsOpen = True, bookmarksInTheWindow = 2"
            ", bookmarksCarryingThePrefix = [ bookmarkLabel %s ]"
            ", homeStructureRowsOnTheOverview = [], destination = Nothing }"
            % json.dumps(FICTIONAL_SAFE + CELL + FICTIONAL_FOLDER)])[0]
        self.assertIn(FICTIONAL_SAFE, printed)
        self.assertNotIn(FICTIONAL_FOLDER, printed)

    def test_the_prefix_is_matched_at_the_front_and_case_is_not_folded(self):
        """`String.startsWith`, which is narrower than the substring match this
        file uses for `bookmarkedGasSiteMarker` -- that one is the *client's* word
        for a site family and can sit anywhere, where this is a marker the
        operator puts at the front themselves."""
        front, middle, wrong_case = self.repl.evaluate([
            "bookmarkLabelStartsWithPrefix \"safe-\" \"safe-one\"",
            "bookmarkLabelStartsWithPrefix \"safe-\" \"my safe-one\"",
            "bookmarkLabelStartsWithPrefix \"safe-\" \"Safe-one\"",
        ])
        self.assertTrue(front)
        self.assertFalse(middle)
        self.assertFalse(wrong_case)


class TheThreeRungsAndTheFallThroughTest(unittest.TestCase):
    """Each destination on a reading where the ones above it answer nothing.

    The order is #463's and the reasons are not interchangeable: a prefixed
    bookmark is a place the operator said in advance was safe, the home structure
    is somewhere with a tether that they named for depositing, and any bookmark
    at 100 km is the last resort whose whole safety is the range. So each rung is
    asked with the rungs above it removed, and the rung *above* is asked beside
    it, since a rule that answered the third on every reading would pass a case
    that only ever asked the third.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def rung(self, children, prefix=None, home=None):
        """The clause an operator reads, which names the rung and its label.

        `describeRetreatSearch` rather than the constructor, because a
        `RetreatDestination` carries a whole parsed `uiNode` and printing one
        would be a page of tree per case -- and because the clause is what a
        person acts on, so executing it is worth more than executing a tag
        beside it. The three rungs say different things about themselves, which
        is what makes this discriminating: `to the bookmark`, `so to the home
        structure`, `simply the first bookmark there is`.
        """
        return self.repl.strings([
            "search |> Maybe.map describeRetreatSearch"
            " |> Maybe.withDefault \"<the fixture never arrived>\""
        ], definitions=[
            reading_binding("reading", children),
            retreat_search_binding("search", "reading", prefix, home),
        ])[0]

    def test_a_prefixed_bookmark_outranks_everything_beside_it(self):
        """The grid this rung has to win on carries all three answers at once."""
        printed = self.rung([
            locations_window(bookmark_rows(
                [FICTIONAL_PLAIN_BOOKMARK,
                 FICTIONAL_SAFE + CELL + FICTIONAL_FOLDER])),
            overview_window([structure_row()]),
        ], home=FICTIONAL_STRUCTURE)
        self.assertIn("to the bookmark '%s'" % FICTIONAL_SAFE, printed)
        self.assertIn("at Within 0 m", printed)
        self.assertNotIn(FICTIONAL_STRUCTURE, printed)
        self.assertNotIn(FICTIONAL_PLAIN_BOOKMARK, printed)
        # And the name is the label rather than the row, since a name an
        # operator cannot find in their own client is worse than none.
        self.assertNotIn(FICTIONAL_FOLDER, printed)

    def test_the_home_structure_is_taken_where_no_bookmark_carries_the_prefix(self):
        printed = self.rung([
            locations_window(bookmark_rows([FICTIONAL_PLAIN_BOOKMARK])),
            overview_window([structure_row()]),
        ], home=FICTIONAL_STRUCTURE)
        self.assertIn("so to the home structure '%s'" % FICTIONAL_STRUCTURE,
                      printed)
        self.assertIn("at Within 0 m", printed)
        self.assertNotIn("simply the first bookmark", printed)

    def test_any_bookmark_at_all_is_the_last_rung(self):
        """No prefixed bookmark and no home structure on this grid, which is the
        state the fallback exists for -- and the range is the whole difference,
        since nothing here knows what that bookmark is on top of."""
        printed = self.rung([
            locations_window(bookmark_rows([FICTIONAL_PLAIN_BOOKMARK])),
            overview_window([celestial_row()]),
        ], home=FICTIONAL_STRUCTURE)
        self.assertIn("simply the first bookmark there is", printed)
        self.assertIn("'%s'" % FICTIONAL_PLAIN_BOOKMARK, printed)
        self.assertIn("at Within 100 km", printed)

    def test_the_home_structure_is_not_taken_where_the_setting_is_unset(self):
        """`home-structure-name` has no default and cannot have one -- it names a
        structure in one wormhole belonging to one operator -- so an unset
        setting must decline rather than matching the first structure it sees."""
        printed = self.rung([overview_window([structure_row()])])
        self.assertIn("NOWHERE TO RUN TO", printed)
        self.assertNotIn(FICTIONAL_STRUCTURE, printed)

    def test_the_home_structure_name_is_matched_whole_rather_than_loosely(self):
        """`siteCellMatches`, which is what `anomaly-group` already promises an
        operator: whole and case-insensitive, with a trailing `*` meaning a
        prefix and nothing else widening it.

        The exactness is the half worth executing. `attack-object` records what a
        substring cost this codebase once -- a wreck's Type is its owner's name
        with `Wreck` appended, so the bot fired on the corpse of what it had just
        killed -- and here the cost is a retreat aimed at whatever structure
        happens to share a word with the one the operator named.
        """
        partial, exact, prefix, cased = [
            self.rung([overview_window([structure_row()])], home=home)
            for home in ("Example Refinery", FICTIONAL_STRUCTURE,
                         "Fictional IX*", FICTIONAL_STRUCTURE.upper())]
        self.assertIn("NOWHERE TO RUN TO", partial)
        self.assertIn("so to the home structure", exact)
        self.assertIn("so to the home structure", prefix)
        # Case is folded here and not on the bookmark prefix, and the difference
        # is deliberate: this is a name the *client* writes and an operator
        # copies, where the prefix is a marker they type themselves.
        self.assertIn("so to the home structure", cased)

    def test_a_hidden_home_structure_row_is_not_clicked(self):
        """The overview virtualises: a hidden row's region belongs to whatever
        was recycled into it, and this rung ends in a right-click at that
        region."""
        printed = self.rung([
            overview_window([structure_row(displayed=False)]),
        ], home=FICTIONAL_STRUCTURE)
        self.assertIn("NOWHERE TO RUN TO", printed)
        # The shown control, so the case is about `_display` rather than about
        # the fixture never having decoded.
        self.assertIn(
            "so to the home structure",
            self.rung([overview_window([structure_row()])],
                      home=FICTIONAL_STRUCTURE))

    def test_nothing_at_all_answers_nothing_rather_than_silently_doing_nothing(self):
        """The reading #463 names last: no window, no structure, no bookmark.

        What the case pins is that it is a distinct answer that says so, rather
        than a rung quietly picking something."""
        printed = self.rung([])
        self.assertIn("NOWHERE TO RUN TO", printed)
        self.assertIn("not open", printed)
        self.assertIn("whole plan for anything arriving is to leave", printed)

    def test_a_shut_locations_window_is_told_apart_from_an_empty_one(self):
        """Two states wanting different fixes from an operator, and a list that
        is empty for either reason cannot tell them apart."""
        printed = self.repl.rendered([
            "( shut, empty ) |> Tuple.mapBoth"
            " (Maybe.map (\\s -> ( s.locationsWindowIsOpen"
            ", s.bookmarksInTheWindow )))"
            " (Maybe.map (\\s -> ( s.locationsWindowIsOpen"
            ", s.bookmarksInTheWindow )))"
        ], definitions=[
            reading_binding("shutReading", []),
            reading_binding("emptyReading", [locations_window([])]),
            retreat_search_binding("shut", "shutReading"),
            retreat_search_binding("empty", "emptyReading"),
        ])[0]
        self.assertEqual(printed, "(Just (False,0),Just (True,0))")


class TheWarpMenuIsMatchedOnItsPrefixTest(unittest.TestCase):
    """The cascade, driven against real menus the real parser produced.

    `getNextContextMenu` is the framework's own reader: it takes the cascade node
    and a reading and answers what would be clicked. Asking it rather than
    inspecting the node is what makes these cases about the bot's own behaviour
    instead of about a predicate written beside it.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def chosen(self, menus, distance, depth=0):
        """What the cascade would click, or the `Err` it answers instead.

        `getNextContextMenu` is the framework's own reader over the cascade node
        and a whole reading, so this is the bot's real behaviour rather than a
        predicate re-derived beside it. The framework logs the entry's **own
        literal text** in the step description -- deliberately, since #145 found
        a case that passed on a search string while the press went to another
        button -- which is what makes the answer readable as "it chose this
        entry" rather than "it looked for this string".
        """
        return self.repl.rendered([
            "reading |> Maybe.map (\\r ->"
            " EveOnline.BotFramework.getNextContextMenu"
            " (warpCascadeWithin %s) r %d)"
            % (json.dumps(distance), depth)
        ], definitions=[reading_binding("reading", [menu_layer(menus)])])[0]

    def test_the_top_level_entry_is_found_by_its_prefix(self):
        printed = self.chosen([menu(BOOKMARK_MENU_ALIGN)],
                              "Within 0 m")
        self.assertIn("Warp to Within (0 m)", printed)
        self.assertIn("Ok", printed)

    def test_it_survives_a_different_parenthesised_default(self):
        """The whole reason the match is a prefix. An operator who takes
        `Within 100 km` once by hand leaves the client's default there, and a
        rule comparing the whole string stops matching from that moment on --
        silently, since a cascade that finds nothing waits and retries."""
        for default in ("Warp to Within (100 km)", "Warp to Within (30 km)"):
            with self.subTest(default):
                printed = self.chosen(
                    [menu([default] + BOOKMARK_MENU_ALIGN[1:])],
                    "Within 0 m")
                self.assertIn(default, printed)
                self.assertIn("Ok", printed)

    def test_the_menu_that_offers_approach_instead_of_align_is_read_the_same(self):
        """#463 measured two bookmark rows whose menus differ in that entry, so
        the cascade matches what it wants and ignores the rest rather than
        asserting a shape."""
        align = self.chosen([menu(BOOKMARK_MENU_ALIGN)], "Within 0 m")
        approach = self.chosen([menu(BOOKMARK_MENU_APPROACH)], "Within 0 m")
        self.assertEqual(align, approach)
        self.assertIn("Warp to Within (0 m)", align)

    def test_a_menu_missing_the_entry_answers_err_rather_than_wedging(self):
        """A menu the client drew without the entry -- or drew half of -- must
        not make the cascade pick something else. `Err` is what the framework
        answers by waiting a reading and then reopening, which is a retry rather
        than a wrong click."""
        printed = self.chosen(
            [menu(["Show Info", "Add Waypoint", "Remove Location"])],
            "Within 0 m")
        self.assertIn("Err", printed)
        self.assertIn("Warp to Within", printed)

    def test_the_submenu_distance_is_matched_exactly(self):
        """`Within 0 m` and `Within 100 km` are literals the client writes
        exactly, so the second level is an equality -- which is also what keeps
        `Within 0 m` from matching `Within 10 km` on a looser rule."""
        for distance in ("Within 0 m", "Within 100 km"):
            with self.subTest(distance):
                printed = self.chosen(
                    [menu(BOOKMARK_MENU_ALIGN), menu(DISTANCE_SUBMENU)],
                    distance, depth=1)
                self.assertIn("Ok", printed)
                self.assertIn(distance, printed)

    def test_the_submenu_missing_the_distance_answers_err(self):
        printed = self.chosen(
            [menu(BOOKMARK_MENU_ALIGN),
             menu([entry for entry in DISTANCE_SUBMENU
                   if entry != "Within 100 km"])],
            "Within 100 km", depth=1)
        self.assertIn("Err", printed)

    def test_set_default_is_not_one_of_the_distances_this_bot_draws_from(self):
        """It is the eighth entry of that submenu and it retunes the client
        rather than warping anywhere, so a random pick over the whole menu --
        which is what `useRandomMenuEntry` gives -- would eventually press it."""
        printed = self.repl.rendered(["warpDistanceMenuEntries"])[0]
        self.assertNotIn("Set Default", printed)
        for offered in DISTANCE_SUBMENU:
            if offered == "Set Default":
                continue
            with self.subTest(offered):
                self.assertIn(offered, printed)

    def test_both_named_distances_are_entries_the_client_offers(self):
        """Three declarations that could come to disagree about what the client
        writes is #102's defect, and here it would mean a retreat asking the
        submenu for a distance it does not have."""
        answers = self.repl.evaluate([
            "List.member warpAtZeroMenuEntry warpDistanceMenuEntries",
            "List.member warpAt100KmMenuEntry warpDistanceMenuEntries",
        ])
        self.assertEqual(answers, [True, True])


class TheCloakDegradesCleanlyTest(unittest.TestCase):
    """A cloak that is not fitted must keep the evasion moving.

    #456 records this as unverified: five modules were read on the measured hull
    and none was identified as one. So the rule answers four things and the two
    negative ones are deliberately not one -- an operator has to be able to tell
    a fit with no cloak in it from a session that has simply not hovered the
    modules yet, because only the second is worth waiting on.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def search(self, modules):
        return self.repl.rendered([
            "cloakAmongFittedModules [ %s ]" % ", ".join(modules)])[0]

    def test_a_fit_with_no_cloak_says_so_rather_than_waiting(self):
        self.assertEqual(
            self.search([fitted("Gas Cloud Harvester II"),
                         fitted("Gas Cloud Harvester II"),
                         fitted("50MN Microwarpdrive II", running=True)]),
            "NoCloakAmongTheModulesIdentified 3")

    def test_a_module_with_no_tooltip_yet_is_not_a_fit_with_no_cloak(self):
        self.assertEqual(
            self.search([fitted("Gas Cloud Harvester II"), fitted()]),
            "TheModulesAreNotIdentifiedYet { identified = 1, total = 2 }")

    def test_the_cloak_is_recognised_by_the_client_s_own_module_group(self):
        self.assertEqual(
            self.search([fitted("Gas Cloud Harvester II"),
                         fitted("Improved Cloaking Device II")]),
            "TheCloakIsFittedAndNotRunning 1")

    def test_a_cloak_already_running_is_not_asked_for_again(self):
        """A module button is a toggle, so pressing one that is already on
        switches it off -- which on a cloak is the worst available answer."""
        self.assertEqual(
            self.search([fitted("Covert Ops Cloaking Device II", running=True)]),
            "TheCloakIsAlreadyRunning")

    def test_the_marker_is_matched_ignoring_case_inside_a_longer_tooltip(self):
        """The tooltip carries the module's whole name and its attributes, so the
        group word sits inside a longer string; and the client's own casing is
        not something to depend on."""
        self.assertEqual(
            self.search([fitted("prototype cloaking device i -- 30s")]),
            "TheCloakIsFittedAndNotRunning 0")

    def test_neither_negative_answer_stalls_the_evasion(self):
        """The requirement #463 states in words, executed: no cloak found means
        keep evading without one, not wait for a module that does not exist."""
        for cloak in ("(NoCloakAmongTheModulesIdentified 5)",
                      "(TheModulesAreNotIdentifiedYet"
                      " { identified = 1, total = 5 })"):
            with self.subTest(cloak):
                self.assertEqual(
                    self.repl.rendered([
                        "evasionStep %s" % situation(cloak=cloak,
                                                     celestials=4)])[0],
                    "WarpToACelestial 0")

    def test_a_cloak_the_client_will_not_answer_is_given_up_on(self):
        """Every arm that clicks needs a bound. A cloak asked for and never
        answered would otherwise be a module button pressed once a reading for
        the rest of the evasion, on a toggle."""
        bound = self.repl.values(["cloakGiveUpReadings"], r"(\d+) : Int")[0]
        bound = int(bound)
        just_inside, just_past = self.repl.rendered([
            "evasionStep %s" % situation(
                cloak="(TheCloakIsFittedAndNotRunning 2)", celestials=4,
                counters=evasion_counters(readings=30, cloak=bound - 1)),
            "evasionStep %s" % situation(
                cloak="(TheCloakIsFittedAndNotRunning 2)", celestials=4,
                counters=evasion_counters(readings=30, cloak=bound)),
        ])
        self.assertEqual(just_inside, "ActivateTheCloak 2")
        self.assertEqual(just_past, "WarpToACelestial 0")
        # A fixed value either side, so a bound written as a constant that admits
        # everything cannot satisfy the boundary pair above.
        self.assertGreater(bound, 5)

    def test_the_identification_hover_is_bounded_and_spends_quiet_readings(self):
        """It is asked from `NothingLeftToCommand` -- the harvest loop's steady
        state -- so it starves nothing, and it is bounded anyway because a
        tooltip that never lands would otherwise be a hover repeated for the rest
        of the session."""
        body = collapsed(top_level_declarations(bot_source())[
            "identifyTheModulesFitted"])
        # The comparison's *form*, not the two names -- the branch prints both
        # of them in its own decision line, so a guard neutralised to `if False`
        # leaves a body that still mentions each and a substring check that
        # still passes. #109's status clause and #145's named button each cost
        # this repo one survived mutation for exactly that reason.
        self.assertIn(
            "if moduleIdentificationGiveUpReadings <="
            " context.memory.modulesUnidentifiedReadings then Nothing else",
            body)
        self.assertIn("readShipUIModuleButtonTooltipWhereNotYetInMemory", body)
        acting = collapsed(top_level_declarations(bot_source())[
            "actOnTheHarvestStep"])
        self.assertIn("NothingLeftToCommand", acting)
        self.assertIn("identifyTheModulesFitted context", acting)
        self.assertLess(acting.index("NothingLeftToCommand"),
                        acting.index("identifyTheModulesFitted"), acting)


class TheEvasionDoesNotEndOnAReadingItCannotSeeTest(unittest.TestCase):
    """The line the whole issue rests on, executed at both places that read it.

    `gridReadsClean` answers `True` for `GridIsClean` and for nothing else, so a
    grid this bot cannot see is not a grid it may go back to work on. Two things
    have to honour that: the step rule, which decides, and the counters, which
    decide when the session ends.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def folded(self, answers):
        """The counters folded over a whole session of readings.

        A rule that is right for one reading and wrong across a session is the
        defect this shape prevents, and it is exactly what "an evasion does not
        end on a reading the bot cannot see" is about.
        """
        return self.repl.rendered([
            "List.foldl evasionCountersAfterReading initEvasionCounters"
            " [ %s ]" % ", ".join(answers)])[0]

    def test_only_a_clean_grid_ends_an_evasion(self):
        """`dirty, dirty, cannot-tell, dirty, clean` resets on the last reading
        and on no earlier one. Every one of the first four is a reading the bot
        either saw something on or could not see at all, and only the fifth is
        `GridIsClean`."""
        self.assertEqual(
            self.folded([answer()] * 4 + [answer(clean=True)]),
            "{ cloakUnansweredReadings = 0, longestWarpUnexecutedReadings = 4"
            ", readings = 0, warpUnexecutedReadings = 0 }")

    def test_a_grid_the_bot_cannot_see_keeps_the_evasion_running(self):
        """The same five readings without the clean one. `gridIsClean` is
        `gridReadsClean`'s answer, so a `CannotTell` reading arrives here as
        `False` and the counter goes on climbing."""
        self.assertEqual(
            self.folded([answer()] * 5),
            "{ cloakUnansweredReadings = 0, longestWarpUnexecutedReadings = 5"
            ", readings = 5, warpUnexecutedReadings = 5 }")

    def test_the_cloak_counter_climbs_only_while_one_is_being_asked_for(self):
        """A fit with no cloak in it answers `cloakAnsweredTheAsk` -- there is
        nothing being asked for, so there is nothing to bound, and a counter
        climbing on a ship with no cloak would spend a budget on nothing."""
        self.assertEqual(
            self.folded([answer(cloak_answered=False)] * 3 + [answer()]),
            "{ cloakUnansweredReadings = 0, longestWarpUnexecutedReadings = 4"
            ", readings = 4, warpUnexecutedReadings = 4 }")
        self.assertEqual(
            self.folded([answer(cloak_answered=False)] * 3),
            "{ cloakUnansweredReadings = 3, longestWarpUnexecutedReadings = 3"
            ", readings = 3, warpUnexecutedReadings = 3 }")

    def test_the_step_rule_resumes_work_on_a_clean_grid_and_on_nothing_else(self):
        clean, dirty = self.repl.rendered([
            "evasionStep %s" % situation(clean=True, on_site=True),
            "evasionStep %s" % situation(on_site=True),
        ])
        self.assertEqual(clean, "TheGridReadsCleanSoResumeWork")
        self.assertNotEqual(dirty, "TheGridReadsCleanSoResumeWork")

    def test_the_warp_counter_resets_while_the_ship_is_in_warp(self):
        """A ship that is leaving is a retreat executing, however long the
        verdict stays latched afterwards -- so the alarm counts readings spent
        commanding a warp that did not start, not readings spent leaving."""
        self.assertEqual(
            self.folded([answer(), answer(), answer(warping=True), answer()]),
            "{ cloakUnansweredReadings = 0, longestWarpUnexecutedReadings = 2"
            ", readings = 4, warpUnexecutedReadings = 1 }")

    def test_the_worst_interval_survives_the_reset(self):
        """A session whose worst retreat is over must still be able to say how
        bad it was, which is what the status line reports on a quiet reading."""
        self.assertEqual(
            self.folded([answer()] * 3 + [answer(clean=True), answer()]),
            "{ cloakUnansweredReadings = 0, longestWarpUnexecutedReadings = 3"
            ", readings = 1, warpUnexecutedReadings = 1 }")

    def test_the_session_ends_only_once_the_bound_is_reached(self):
        bound = int(self.repl.values(["evasionGiveUpReadings"], r"(\d+) : Int")[0])
        just_inside, at_the_bound = self.repl.rendered([
            "evasionOutOfTime { readings = %d }" % (bound - 1),
            "evasionOutOfTime { readings = %d }" % bound,
        ])
        self.assertEqual(just_inside, "Nothing")
        self.assertIn("Just", at_the_bound)
        self.assertIn("no work in", at_the_bound)
        # A fixed value either side, so a bound cut to something that fires at
        # once cannot satisfy the boundary pair above.
        self.assertGreater(bound, 100)
        self.assertEqual(self.repl.rendered(
            ["evasionOutOfTime { readings = 0 }"])[0], "Nothing")

    def test_the_session_end_says_it_is_not_something_to_shout_about(self):
        """A wormhole with residents in it is a wormhole this bot has no work in,
        which is the opposite of the warp alarm one function along: ending with
        the ship cloaked at a safe is a fine outcome, and ending with the ship on
        a hostile grid is not."""
        printed = self.repl.strings([
            "evasionOutOfTime { readings = 100000 }"
            " |> Maybe.withDefault \"<none>\""])[0]
        self.assertIn("end of the session", printed)
        self.assertNotIn("I am stuck here", printed)


class TheOrderingOfTheLeavingTest(unittest.TestCase):
    """One rule with the whole ordering in it, `harvestStep`'s shape.

    Every stage can fail to be reachable and each has to fall through to the next
    rather than holding the loop, which is what these cases execute: the same
    situation with one thing removed at a time.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def step(self, **kwargs):
        return self.repl.rendered(["evasionStep %s" % situation(**kwargs)])[0]

    def test_a_ship_already_in_warp_is_left_alone(self):
        """Re-commanding a warp that is going is how a cascade re-opens on every
        reading of a manoeuvre already doing what it was told, and it is asked
        above every rung so that a destination the ship is already flying to
        cannot re-open one either."""
        printed = self.repl.rendered([
            "search |> Maybe.andThen .destination"
            " |> Maybe.map (\\d -> evasionStep %s)"
            % situation(warping=True, on_site=True, destination="(Just d)")
        ], definitions=[
            reading_binding("reading", [locations_window(
                bookmark_rows([FICTIONAL_SAFE]))]),
            retreat_search_binding("search", "reading"),
        ])[0]
        self.assertEqual(printed, "Just WaitForTheEvasionWarpToLand")

    def test_still_on_the_site_with_somewhere_to_go_warps_out(self):
        printed = self.repl.rendered([
            "search |> Maybe.andThen .destination"
            " |> Maybe.map (\\d -> evasionStep %s)"
            % situation(on_site=True, destination="(Just d)")
        ], definitions=[
            reading_binding("reading", [locations_window(
                bookmark_rows([FICTIONAL_SAFE]))]),
            retreat_search_binding("search", "reading"),
        ])[0]
        self.assertIn("WarpOutOfTheSite", printed)

    def test_nowhere_to_go_falls_through_rather_than_sitting_on_the_grid(self):
        """Sitting on a hostile grid because no bookmark is named is worse than
        cloaking on it and worse again than bouncing off it. The status line is
        what shouts `NOWHERE TO RUN TO`; the rule keeps the ship moving."""
        self.assertEqual(
            self.step(on_site=True,
                      cloak="(TheCloakIsFittedAndNotRunning 1)"),
            "ActivateTheCloak 1")

    def test_off_the_site_the_cloak_comes_before_the_bounce(self):
        self.assertEqual(
            self.step(cloak="(TheCloakIsFittedAndNotRunning 0)"),
            "ActivateTheCloak 0")

    def test_a_grid_with_nothing_at_au_range_says_so(self):
        """A branch that reports nothing and does nothing is indistinguishable
        from one that is stuck."""
        self.assertEqual(self.step(celestials=0), "NothingLeftToLeaveWith")

    def test_the_celestial_choice_rotates_rather_than_retrying_one(self):
        """A retreat that has not worked yet should try a different corner of the
        system, and the choice has to outlive the cascade that acts on it --
        which is a right-click, a hover and a click here rather than the mission
        runner's two clicks."""
        sticky = int(self.repl.values(
            ["evasionCelestialStickyReadings"], r"(\d+) : Int")[0])
        printed = self.repl.rendered([
            "evasionStep %s" % situation(celestials=3, rotation=rotation)
            for rotation in (0, sticky - 1, sticky, sticky * 3)
        ])
        self.assertEqual(printed, ["WarpToACelestial 0", "WarpToACelestial 0",
                                   "WarpToACelestial 1", "WarpToACelestial 0"])
        self.assertGreater(sticky, 3)


class TheWarpThatDoesNotTakeIsReportedAndStillCommandedTest(unittest.TestCase):
    """#141's posture, ported: report it loudly and go on commanding the warp.

    That issue is the worked example #463 names -- a retreat decided on 36
    consecutive readings with the ship never entering warp. Stopping cannot help
    a ship that is still on a hostile grid, so the sentence `stall_watch.py`
    answers with a screenshot is *carried into* the branch's description rather
    than reached by branching to `askForHelpToGetUnstuck`, which dispatches
    nothing.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_alarm_fires_once_on_the_reading_the_bound_is_crossed(self):
        bound = int(self.repl.values(
            ["warpNotExecutingAlarmReadings"], r"(\d+) : Int")[0])
        before, crossing, after = self.repl.rendered([
            "warpNotExecutingAlarm { before = %d, now = %d }"
            % (bound - 2, bound - 1),
            "warpNotExecutingAlarm { before = %d, now = %d }"
            % (bound - 1, bound),
            "warpNotExecutingAlarm { before = %d, now = %d }"
            % (bound, bound + 1),
        ])
        self.assertEqual(before, "Nothing")
        self.assertIn("Just", crossing)
        self.assertEqual(after, "Nothing")
        # A fixed value either side, so a bound of zero would not satisfy the
        # crossing pair above.
        self.assertGreater(bound, 10)

    def test_the_bound_is_written_as_rotations_of_the_escape_choice(self):
        """`dscanStaleAfterIntervals`' form, for its reason: an operator who
        changes one changes the other with it, and the argument cannot drift away
        from the figure."""
        body = collapsed(top_level_declarations(bot_source())[
            "warpNotExecutingAlarmReadings"])
        self.assertIn("evasionCelestialStickyReadings", body)
        sticky, bound = [int(value) for value in self.repl.values(
            ["evasionCelestialStickyReadings", "warpNotExecutingAlarmReadings"],
            r"(\d+) : Int")]
        self.assertEqual(bound, sticky * 3)

    def test_the_line_carries_the_watchdog_s_own_sentence(self):
        line, shared = self.repl.strings([
            "describeWarpNotExecuting 36",
            "askForHelpToGetUnstuckText",
        ])
        self.assertIn(shared, line)
        self.assertIn("RETREAT NOT EXECUTING", line)
        self.assertIn("36", line)
        # The count is in readings and the sentence says so, because this file
        # has two units and a log is easiest to mis-read in the other one.
        self.assertIn("readings, not decisions", line)
        # And that the bot has not stopped, which a reader who has just been told
        # it is stuck would otherwise reasonably assume.
        self.assertIn("still commanding it", line)

    def test_the_sentence_is_the_one_the_watchdog_matches(self):
        """Three copies of one string across two languages is a coupling this
        repo pins rather than remembers, and a drift here is silent in the
        direction that looks like a healthy run -- the line still prints and
        nothing escalates.

        The framework's copy is not imported because that value is a
        `DecisionPathNode` rather than the string inside it, and the module is
        vendored eight times: exporting one more name from it would be eight
        edits to make a literal reachable (#467).
        """
        import os

        shared = self.repl.strings(["askForHelpToGetUnstuckText"])[0]
        macos_host = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(macos_host, "stall_watch.py"),
                  encoding="utf-8") as handle:
            self.assertIn('STUCK_TEXT = "%s"' % shared, handle.read())
        with open(os.path.join(GAS_HUFFER_DIR, "EveOnline",
                               "BotFrameworkSeparatingMemory.elm"),
                  encoding="utf-8") as handle:
            self.assertIn('describeBranch "%s"' % shared, handle.read())

    def test_the_branch_carrying_it_still_commands_the_warp(self):
        """The mutation this exists for: branching to `askForHelpToGetUnstuck`,
        which dispatches no effects -- so taking it would stop the retreat
        commanding the warp, which is the one thing that must not happen while
        the ship is still in the pocket."""
        body = collapsed(top_level_declarations(bot_source())[
            "warpToTheRetreatDestination"])
        self.assertIn("describeWarpNotExecuting", body)
        self.assertIn("useContextMenuCascade target", body)
        self.assertNotIn("askForHelpToGetUnstuck ", body)
        self.assertNotIn("waitForProgressInGame", body)

    def test_the_alarm_is_said_at_the_root_where_nothing_can_decline_to_ask_it(self):
        """The counter advances in the memory update whatever the tree is doing,
        so the line goes out at the root beside the other two -- the branch that
        would otherwise carry it is one a message box above the split can hold."""
        root = collapsed(top_level_declarations(bot_source())[
            "gasHufferDecisionRoot"])
        self.assertIn("context.memory.warpNotExecutingLastChange", root)
        update = collapsed(top_level_declarations(bot_source())[
            "updateMemoryForNewReadingFromGame"])
        self.assertIn("warpNotExecutingAlarm", update)


class TheStatusLineSaysWhereItWouldGoAndWhatItIsWaitingForTest(unittest.TestCase):
    """Every arm that clicks names a bound and what it is waiting for.

    This repo has spent a week fixing unbounded retries and give-ups that lied
    about what was tried, so the clauses are executed rather than asserted by
    substring on the function that builds them -- a clause that printed nothing
    at all would satisfy the second.
    """

    @classmethod
    def setUpClass(cls):
        cls.repl = repl()

    @classmethod
    def tearDownClass(cls):
        cls.repl.close()

    def test_the_evasion_clause_carries_both_counts_against_their_bounds(self):
        quiet, evading, alarming = self.repl.strings([
            "describeEvasion %s" % evasion_counters(),
            "describeEvasion %s" % evasion_counters(readings=7,
                                                    warp_unexecuted=3),
            "describeEvasion %s" % evasion_counters(readings=90,
                                                    warp_unexecuted=90),
        ])
        self.assertIn("not evading", quiet)
        evasion_bound, warp_bound = self.repl.values(
            ["evasionGiveUpReadings", "warpNotExecutingAlarmReadings"],
            r"(\d+) : Int")
        self.assertIn("7/%s" % evasion_bound, evading)
        self.assertIn("3/%s" % warp_bound, evading)
        self.assertIn("past the bound", alarming)
        self.assertIn("a person has been asked for", alarming)

    def test_the_quiet_clause_still_reports_the_session_s_worst(self):
        printed = self.repl.strings([
            "describeEvasion %s" % evasion_counters(longest=12)])[0]
        self.assertIn("not evading", printed)
        self.assertIn("Worst this session: 12", printed)

    def test_the_cloak_clause_tells_the_three_states_apart(self):
        none, unknown, ready = self.repl.strings([
            "describeCloak (NoCloakAmongTheModulesIdentified 5)",
            "describeCloak (TheModulesAreNotIdentifiedYet"
            " { identified = 2, total = 5 })",
            "describeCloak (TheCloakIsFittedAndNotRunning 3)",
        ])
        self.assertIn("NONE FITTED", none)
        self.assertIn("on purpose", none)
        self.assertIn("NOT KNOWN YET", unknown)
        self.assertIn("2 of 5", unknown)
        self.assertIn("slot 4", ready)

    def test_nothing_left_to_leave_with_asks_for_a_person(self):
        """A grid that does not read clean with nowhere to go and nothing at AU
        range is the one state this bot genuinely cannot act on, so it says so in
        the watchdog's own words rather than waiting quietly."""
        body = collapsed(top_level_declarations(bot_source())[
            "actOnTheEvasionStep"])
        self.assertIn("NOWHERE TO GO", body)
        self.assertIn("askForHelpToGetUnstuckText", body)

    def test_every_clicking_arm_names_what_it_is_waiting_for(self):
        body = collapsed(top_level_declarations(bot_source())[
            "actOnTheEvasionStep"])
        for named in ("cloakGiveUpReadings", "warpNotExecutingAlarmReadings"):
            with self.subTest(named):
                self.assertIn(
                    named, body + collapsed(top_level_declarations(
                        bot_source())["warpToTheRetreatDestination"]))


class TheOneCascadeDrivesEveryWarpTest(unittest.TestCase):
    """One declaration with several readers, never a rule restated beside them.

    #102's rule, and the way it would fail here is a hunt warp and a retreat warp
    coming to disagree about what the client's menu says.
    """

    def setUp(self):
        self.declarations = top_level_declarations(bot_source())

    def test_the_two_levels_are_written_once(self):
        source = collapsed(bot_source())
        self.assertEqual(source.count("warpCascadeWithin distanceMenuEntry ="), 1)
        readers = [name for name, text in self.declarations.items()
                   if "warpCascadeWithin" in collapsed(text)
                   and name != "warpCascadeWithin"]
        self.assertEqual(
            sorted(readers),
            # #464's trip home is the fourth reader and joined for this rule's
            # own reason: the deposit warps to the same overview row the
            # retreat's second rung right-clicks, so a second copy of the two
            # menu levels would be a bot that arrives at 0 m when it is
            # frightened and somewhere else when it is full.
            ["actOnTheDepositStep", "warpToACelestialAtARandomRange",
             "warpToTheHuntedSite", "warpToTheRetreatDestination"],
            readers)

    def test_the_retreat_takes_zero_for_the_first_two_rungs_and_100km_for_the_last(self):
        body = collapsed(self.declarations["warpToTheRetreatDestination"])
        self.assertEqual(body.count("warpAtZeroMenuEntry"), 2)
        self.assertEqual(body.count("warpAt100KmMenuEntry"), 1)
        self.assertLess(body.index("ToAnyBookmarkAtAll"),
                        body.index("warpAt100KmMenuEntry"), body)

    def test_the_bounce_draws_its_range_rather_than_taking_a_fixed_one(self):
        """Randomising the range is the point -- a bot that always lands at the
        same spot on the same celestial is trivially caught."""
        body = collapsed(self.declarations["warpToACelestialAtARandomRange"])
        self.assertIn("context.randomIntegers", body)
        self.assertIn("warpDistanceMenuEntries", body)
        self.assertNotIn("useRandomMenuEntry", body)

    def test_the_rules_take_records_rather_than_a_decision_context(self):
        """#106: a rule reachable only through a decision context is one nothing
        can run, so it gets checked by being read -- which is how a rule that
        resumes work on a reading the bot cannot see passes for one that works."""
        for rule in ("retreatSearch", "evasionStep", "cloakAmongFittedModules",
                     "evasionCountersAfterReading", "evasionOutOfTime",
                     "warpNotExecutingAlarm", "bookmarkLabel"):
            with self.subTest(rule):
                signature = collapsed(self.declarations[rule]).split(
                    " %s " % rule)[0]
                self.assertNotIn("BotDecisionContext", signature)


class TheParserIsNotTouchedTest(unittest.TestCase):
    """This change reads the Locations rows #457 landed and adds nothing.

    `EveOnline/ParseUserInterface.elm` is vendored once per app and the gas
    huffer's copy is byte-identical to `eve-online-wingman`'s. A retreat that
    needed a parser change would be an eight-copy concern (#467) rather than a
    one-file edit, so the absence of one is asserted rather than left to be
    noticed in review.
    """

    def test_the_vendored_parser_matches_wingman_byte_for_byte(self):
        import os
        apps = os.path.dirname(GAS_HUFFER_DIR)

        def parser(app):
            with open(os.path.join(apps, app, "EveOnline",
                                   "ParseUserInterface.elm"),
                      encoding="utf-8") as handle:
                return handle.read()

        self.assertEqual(parser("eve-online-gas-huffer"),
                         parser("eve-online-wingman"))


class TheMutationsThisFileCatches(unittest.TestCase):
    """Confirmed by mutation. Each of these was applied to `Bot.elm` and the
    named case failed; the list is here so a later reader can re-run them.

    1.  `menuEntryOpensTheWarpDistanceSubmenu` comparing the whole string
        (`String.trim >> (==) "Warp to Within (0 m)"`) --
        `TheWarpMenuIsMatchedOnItsPrefixTest
        .test_it_survives_a_different_parenthesised_default`.
    2.  the prefix match written as `String.endsWith`, which is the plausible
        typo -- every case in that class, beginning with
        `test_the_top_level_entry_is_found_by_its_prefix`.
    3.  `warpCascadeWithin` ignoring its argument and always taking
        `warpAtZeroMenuEntry` -- `test_the_submenu_distance_is_matched_exactly`
        and `TheOneCascadeDrivesEveryWarpTest`.
    4.  `Set Default` added to `warpDistanceMenuEntries` --
        `test_set_default_is_not_one_of_the_distances_this_bot_draws_from`.
    5.  `warpAt100KmMenuEntry` written as `"Within 100km"` --
        `test_any_bookmark_at_all_is_the_last_rung` and
        `test_both_named_distances_are_entries_the_client_offers`.
    6.  `bookmarkLabel` not splitting, so the blob is what is matched *and*
        printed -- `TheLabelIsTheFirstCellTest
        .test_the_label_is_taken_from_in_front_of_the_separator` and
        `test_the_label_is_what_the_operator_is_shown_as_well`.
    7.  the prefix match weakened to `stringContainsIgnoringCase`, on the label
        or on the blob -- `test_the_prefix_is_matched_at_the_front_and_case_is_
        not_folded` and `test_a_folder_named_for_the_prefix_is_not_a_retreat_
        target`.
    8.  `retreatSearch`'s rungs reordered so any bookmark outranks a prefixed one
        -- `TheThreeRungsAndTheFallThroughTest
        .test_a_prefixed_bookmark_outranks_everything_beside_it`.
    9.  the home-structure name matched with `stringContainsIgnoringCase` rather
        than `siteCellMatches`, so a structure sharing a word with the one the
        operator named is warped to -- `test_the_home_structure_name_is_matched_
        whole_rather_than_loosely`.
    10. the `_display` filter dropped from the home-structure rung, so a
        virtualised row is right-clicked --
        `test_a_hidden_home_structure_row_is_not_clicked`, and
        `test_gas_huffer_harvests_a_cloud`'s own filter case.
    11. `locationsWindowIsOpen` pinned `True`, so a shut window reads as an empty
        one -- `test_a_shut_locations_window_is_told_apart_from_an_empty_one`.
    12. **`gridIsClean` in `evasionSituationFromContext` reading
        `CannotTellWhetherTheGridIsClean` as clean** (`gridVerdict evidence /=
        SomethingIsOnTheGrid []`-style) -- `TheEvasionDoesNotEndOnAReadingItCannot
        SeeTest.test_a_grid_the_bot_cannot_see_keeps_the_evasion_running` and
        `test_gas_huffer_watches_the_grid`'s `TheVerdictIsWhatDecidesToLeaveTest`.
        This is the mutation the whole issue rests on: it is invisible on a quiet
        grid and on a hostile one, and it shows up only where the D-Scan window
        is shut or a row is unreadable.
    13. `evasionCountersAfterReading` resetting on any reading rather than on a
        clean one -- `test_only_a_clean_grid_ends_an_evasion` and
        `test_a_grid_the_bot_cannot_see_keeps_the_evasion_running`.
    14. the warp counter not reset by a ship in warp, so a retreat that is
        working inflates the alarm -- `test_the_warp_counter_resets_while_the_
        ship_is_in_warp`.
    15. `longestWarpUnexecutedReadings` discarded on the reset --
        `test_the_worst_interval_survives_the_reset`.
    16. `evasionOutOfTime`'s comparison moved by one --
        `test_the_session_ends_only_once_the_bound_is_reached`.
    17. `evasionGiveUpReadings` written as `1`, which fires immediately -- same
        case, on the fixed value beside the boundary pair.
    18. **the cloak's two negative answers stalling** (`ActivateTheCloak` for
        `NoCloakAmongTheModulesIdentified`, or a wait) --
        `TheCloakDegradesCleanlyTest.test_neither_negative_answer_stalls_the_
        evasion`, which is #463's own named mutation.
    19. `TheModulesAreNotIdentifiedYet` collapsed into
        `NoCloakAmongTheModulesIdentified` --
        `test_a_module_with_no_tooltip_yet_is_not_a_fit_with_no_cloak`.
    20. the cloak matched with `String.contains` rather than
        `stringContainsIgnoringCase` -- `test_the_marker_is_matched_ignoring_
        case_inside_a_longer_tooltip`.
    21. `cloakGiveUpReadings`' comparison moved by one --
        `test_a_cloak_the_client_will_not_answer_is_given_up_on`.
    22. the identification hover asked above the harvest loop rather than from
        `NothingLeftToCommand` -- `test_the_identification_hover_is_bounded_and_
        spends_quiet_readings`.
    23. its guard neutralised to `if False`, so a tooltip that never lands is
        hovered for the rest of the session -- same case. **This one survived the
        first sweep**, and the hole was real: the branch prints both the counter
        and the bound in its own decision line, so a case asserting the two names
        appear passed on a guard that could not fire. The comparison's *form* is
        what is asserted now, which is the correction #109's status clause and
        #145's named button each made once already.
    24. `warpNotExecutingAlarm`'s crossing weakened to `<=`, so the line repeats
        -- `TheWarpThatDoesNotTakeIsReportedAndStillCommandedTest
        .test_the_alarm_fires_once_on_the_reading_the_bound_is_crossed`.
    25. `warpNotExecutingAlarmReadings` written as a bare `36` --
        `test_the_bound_is_written_as_rotations_of_the_escape_choice`.
    26. **the retreat branching to `askForHelpToGetUnstuck` rather than carrying
        the sentence**, so it stops commanding the warp --
        `test_the_branch_carrying_it_still_commands_the_warp`, which is #463's
        own named mutation.
    27. `askForHelpToGetUnstuckText` drifted from the watchdog's literal --
        `test_the_sentence_is_the_one_the_watchdog_matches`.
    28. the alarm dropped from the decision root, so it is never said --
        `test_the_alarm_is_said_at_the_root_where_nothing_can_decline_to_ask_it`.
    29. the celestial choice taken fresh every reading rather than rotating --
        `TheOrderingOfTheLeavingTest
        .test_the_celestial_choice_rotates_rather_than_retrying_one`.
    30. the bounce distance pinned to `warpAtZeroMenuEntry` rather than drawn --
        `TheOneCascadeDrivesEveryWarpTest
        .test_the_bounce_draws_its_range_rather_than_taking_a_fixed_one`. A bot
        that always lands at the same spot on the same celestial is trivially
        caught, which is #463's own reason for the draw.
    31. the fallback rung taking `warpAtZeroMenuEntry` instead of 100 km --
        `test_the_retreat_takes_zero_for_the_first_two_rungs_and_100km_for_the_
        last`, which is #463's own named mutation.
    32. a second copy of the two menu levels written out in
        `warpToTheRetreatDestination` -- `test_the_two_levels_are_written_once`.
    33. `evasionStep` re-commanding a warp the ship is already in --
        `test_a_ship_already_in_warp_is_left_alone`.
    34. the fall-through dropped so nowhere-to-go holds the loop --
        `test_nowhere_to_go_falls_through_rather_than_sitting_on_the_grid`.
    35. `NothingLeftToLeaveWith` answered as a silent wait --
        `TheStatusLineSaysWhereItWouldGoAndWhatItIsWaitingForTest
        .test_nothing_left_to_leave_with_asks_for_a_person`.
    36. `describeEvasion` printing the counts without their bounds --
        `test_the_evasion_clause_carries_both_counts_against_their_bounds`.
    """

    def test_this_file_names_the_mutations_it_was_graded_against(self):
        self.assertGreaterEqual(
            self.__doc__.count("--"), 30,
            "the mutation list is the record of how these cases were graded")


if __name__ == "__main__":
    unittest.main()
